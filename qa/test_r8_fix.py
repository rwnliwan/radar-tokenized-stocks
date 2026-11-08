"""Round-8 fix tests (Terra r8 Radar: 6 must + 16 should).

Pure + monkeypatched-DB only: no network, no token, no Telegram send,
no production reads/writes. The Worker-side items (P2-M1 freshness,
P2-M2 Tier 2 anchoring, S14/S15 runtime contract) are covered by
qa/test_r8_worker.mjs (Node, stubbed Hrana fetch).

Guard-gap locks (perintah Septian 00:23 + 00:53 — self-learning loop):
every class below is locked at the CLASS level (general pattern), not
just the one string/case that surfaced in round 8. Where a guard can
honestly only lock the specific case, the limitation is stated in the
check name / module docstring of the section.

- GG-13 (partial coverage reported as complete): any hourly job whose
  coverage is < 100% MUST say "unknown" for the unchecked part — in the
  stored note, never a bare "0/13". Locked for redemption (M2), PoR
  (M3, incl. unparseable AND future timestamps), and the poller's
  empty-account RPC case.
- GG-15 (one-directional freshness): freshness MUST be tested in BOTH
  directions — a timestamp in the future is stale, never fresh — for
  EVERY timestamp consumer: bot dev rows, bot health age, dashboard
  freshness_status, poller PoR stamps (Worker side in test_r8_worker).
- GG-16 (fail-open / silent failure): every failure path MUST fail
  closed or shout. Locked: empty poller cycle writes cycles_ok=0
  (M1); lock-file open failure raises instead of masquerading as
  contention and --once exits nonzero (M4); unreadable fallback file
  is None (not "empty") and shouts (S9); a delivery recorded nowhere
  returns lost (S9); a final-pipeline failure still attempts a failure
  heartbeat and returns False instead of raising away silently (S10).
- S1: one alert event shares ONE alert_ts across channels.
- S2: per-ticker staleness uses the 15-min bound (same as the web);
  the 30-min global gate is unchanged.
- S3: stale price fields are dropped (render "—") from redemption/PoR
  alerts instead of being printed as if fresh.
- S4: a failed command reply is NOT consumed — the offset advances
  only after a successful send, so the next pass retries it.
- S5: per-token fallback is deduplicated by token address; dex_fetch
  retries every 5xx and reports the real last code, never a hardcoded
  "429".
- S6: fallback markers are pruned (non-redemption > 48h, redemption
  > 30d) so the file cannot grow without bound.
- S7: a redemption window longer than the 5000-row history is anchored
  to its TRUE start (boundary query), not the oldest returned row.
- S8: the supply baseline mutates only after a successful write, and
  the shared hourly clock advances only when BOTH hourly jobs
  succeed (retry after 15 min on failure, not every cycle).
- S11: the NYSE holiday calendar must cover through the end of NEXT
  year (tripwire: this guard starts failing the year the calendar
  needs its annual review) and must be IDENTICAL in all four copies
  (poller, bot, dashboard logic, web format.ts).
- S12: market-open is holiday-aware on the dashboard (logic.py, the
  pure home — app.py only imports it) and on the web (format.ts,
  exercised here via esbuild); the methodology limitation clause no
  longer claims holidays are untracked.
- S13: the dashboard waitlist cap is enforced INSIDE the atomic
  INSERT (same as the Worker); rows_written==0 is disambiguated into
  idempotent-duplicate vs rate-limited.
- S14/S15: web/src/lib/api.ts declares AlertRow.channel and
  LatestResponse.meta.stale_tickers; `npx tsc --noEmit` passes.
- S16: the dashboard coverage line says PoR is LIVE (as on the web);
  the coming-soon list no longer claims the PoR feed is unconnected.

Thresholds are NOT changed here (spread 1.0%, dev 3.0%, depth $250k,
dedup 24h, stale gate 30 min, per-ticker stale 15 min, PoR 72h).

Usage: python3 qa/test_r8_fix.py  (exit 0 = PASS)
"""
import ast
import contextlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks")
sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
import bot  # noqa: E402  (token is lazy; import touches no vault/DB)
import poller  # noqa: E402
import logic as dash_logic  # noqa: E402
import turso_read  # noqa: E402
from turso_read import INSERT_WAITLIST_SQL, insert_waitlist  # noqa: E402

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
UTC = timezone.utc
FAILURES = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _ts(minutes_ago, now, future=False):
    dt = now + timedelta(minutes=minutes_ago) if future else now - timedelta(minutes=minutes_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_holiday_set_from_py(path):
    src = open(path, encoding="utf-8").read()
    m = re.search(r"NYSE_HOLIDAYS\s*=\s*(\{[^}]*\})", src, re.S)
    if not m:
        return None
    return set(ast.literal_eval(m.group(1)))


def _parse_holiday_set_from_ts(path):
    src = open(path, encoding="utf-8").read()
    m = re.search(r"NYSE_HOLIDAYS[^=]*=\s*new Set\(\[(.*?)\]\)", src, re.S)
    if not m:
        return None
    return set(re.findall(r'"(\d{4}-\d{2}-\d{2})"', m.group(1)))


def main():
    now = datetime.now(UTC).replace(microsecond=0)
    tmp = tempfile.mkdtemp(prefix="r8_radar_")

    # =====================================================================
    # GG-13 / M2 — redemption: partial on-chain coverage says "unknown"
    # =====================================================================
    captured = {}

    def cap_pipeline(stmts):
        captured.setdefault("stmts", []).extend(stmts)
        return [{} for _ in stmts]

    orig_pipeline = poller.pipeline
    orig_mint = poller.solana_mint_info
    try:
        poller.pipeline = cap_pipeline
        # Case A: every mint returns parsed-but-empty (None, None, "").
        poller.solana_mint_info = lambda mint: (None, None, "")
        state = {}
        frag = poller.run_hourly_redemption(now, state)
        row = captured["stmts"][-1][1]
        note_en = row[4]
        check("GG13/M2 all-empty RPC: note says pause status unknown",
              "unknown" in note_en.lower(), f"note={note_en!r}")
        check("GG13/M2 all-empty RPC: no bare '0/13 mints paused' claim",
              "0/13" not in note_en, f"note={note_en!r}")
        # Case B: 11 checked, 2 empty; one empty mint had a previous
        # supply, which must NOT count as a spurious supply change.
        checked_ticks = list(poller.XSTOCKS_MINTS)[:11]
        empty_ticks = list(poller.XSTOCKS_MINTS)[11:]

        def mixed_mint(mint):
            tick = [t for t, m in poller.XSTOCKS_MINTS.items() if m == mint][0]
            if tick in checked_ticks:
                return False, "100", ""
            return None, None, "empty account data"

        poller.solana_mint_info = mixed_mint
        captured["stmts"] = []
        state = {"last_mint_supply": {empty_ticks[0]: "999"}}
        frag = poller.run_hourly_redemption(now, state)
        row = captured["stmts"][-1][1]
        note_en = row[4]
        check("GG13/M2 partial RPC: note says unknown for unchecked mints",
              "unknown" in note_en.lower() and "2 unchecked" in note_en,
              f"note={note_en!r}")
        check("GG13/M2 partial RPC: denominator is checked count, not 13",
              "of 11" in note_en and "/13 mints paused" not in note_en,
              f"note={note_en!r}")
        check("GG13/M2 partial RPC: None supply is not a supply change",
              "supply changes: none" in note_en, f"note={note_en!r}")
        check("GG13/M2 partial RPC: gap fragment reports partial failure",
              "partial failure" in frag, f"frag={frag!r}")
        # Case C: solana_mint_info itself — a parsed-but-empty account
        # is an ERROR, not a successful "unchecked" read.
        poller.solana_mint_info = orig_mint
        def fake_curl_empty(*a, **k):
            class R:
                stdout = json.dumps({"result": {"value": {}}})
                returncode = 0
            return R()

        def fake_curl_ok(*a, **k):
            class R:
                stdout = json.dumps({"result": {"value": {"data": {"parsed": {"info": {
                    "supply": "123",
                    "extensions": [{"extension": "pausableConfig",
                                    "state": {"paused": True}}]}}}}}})
                returncode = 0
            return R()

        with mock.patch("subprocess.run", fake_curl_empty):
            with mock.patch("time.sleep", lambda *a, **k: None):
                p, s, e = poller.solana_mint_info("mint")
        check("GG13/M2 empty account data is an error, not a clean read",
              p is None and s is None and e != "", f"err={e!r}")
        with mock.patch("subprocess.run", fake_curl_ok):
            p, s, e = poller.solana_mint_info("mint")
        check("GG13/M2 real paused mint still parses (True, supply)",
              p is True and s == "123" and e == "", f"got={(p, s, e)}")
    finally:
        poller.pipeline = orig_pipeline
        poller.solana_mint_info = orig_mint

    # =====================================================================
    # GG-13 / M3 — PoR: partial coverage (fetch fail, bad ts, FUTURE ts)
    # =====================================================================
    orig_por = poller.por_symbol_info
    try:
        poller.pipeline = cap_pipeline
        good_ts = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        ticks = list(poller.XSTOCKS_MINTS)
        fail_tick, bad_tick, future_tick = ticks[11], ticks[12], ticks[10]
        future_ts = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        def por_stub(symbol):
            if symbol == fail_tick:
                return None, "boom"
            if symbol == bad_tick:
                return {"symbol": symbol, "timestamp": "not-a-date",
                        "sharesHeld": "1", "circulatingSupply": "1"}, ""
            if symbol == future_tick:
                return {"symbol": symbol, "timestamp": future_ts,
                        "sharesHeld": "1", "circulatingSupply": "1"}, ""
            return {"symbol": symbol, "timestamp": good_ts,
                    "sharesHeld": "1", "circulatingSupply": "1"}, ""

        poller.por_symbol_info = por_stub
        with mock.patch("time.sleep", lambda *a, **k: None):
            captured["stmts"] = []
            frag = poller.run_hourly_por(now, {})
        por_row = captured["stmts"][0][1]
        cov_note = por_row[4] or ""
        check("GG13/M3 PoR row carries a coverage note (not None)",
              por_row[4] is not None and "10/13" in cov_note, f"note={cov_note!r}")
        check("GG13/M3 PoR note names every token missing from the age",
              all(t in cov_note for t in (fail_tick, bad_tick, future_tick)),
              f"note={cov_note!r}")
        check("GG13/M3 future timestamp is unusable (does not set the age)",
              por_row[2] == good_ts, f"oldest_ts={por_row[2]!r}")
        check("GG13/M3 gap fragment lists the missing tokens",
              all(t in frag for t in (fail_tick, bad_tick, future_tick)),
              f"frag={frag!r}")
        tok_rows = captured["stmts"][1:]
        check("GG13/M3 per-token rows cover only responding tokens",
              len(tok_rows) == 12, f"n={len(tok_rows)}")
    finally:
        poller.pipeline = orig_pipeline
        poller.por_symbol_info = orig_por

    # =====================================================================
    # GG-15 — freshness is two-directional, in EVERY consumer
    # =====================================================================
    # Bot dev rows: future ts is stale.
    def fake_query_future(sql, args=None):
        if "FROM universe ORDER BY" in sql:
            return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
        if "FROM deviations" in sql:
            return [{"ticker_id": "TSLAx", "ts": _ts(60, now, future=True),
                     "depth_weighted_price": 100.5, "dev_vs_median_pct": 3.5,
                     "qualifying_depth_usd": 600000.0, "pools_used": 3}]
        if "FROM redemption_windows" in sql:
            return [{"status": "open", "window_note": None, "next_open_at": None}]
        if "FROM por_feeds" in sql:
            return []
        if "FROM pools p JOIN snapshots" in sql:
            return [{"dex": "raydium", "price_usd": 100.0, "reserve_usd": 200000.0},
                    {"dex": "orca", "price_usd": 110.0, "reserve_usd": 200000.0}]
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    orig_query = bot.db_query
    try:
        bot.db_query = fake_query_future
        tickers = bot.load_live_tickers()
        t = tickers[0]
        check("GG15 bot: future dev ts is dev_stale (never fresh)",
              t["dev_stale"] is True, f"dev_age_min={t['dev_age_min']}")
        check("GG15 bot: future dev ts fires NO spread/deviation alert",
              not [a for a in bot.evaluate_alerts(tickers, True)
                   if a["type"] in ("spread", "deviation_high")],
              f"alerts={bot.evaluate_alerts(tickers, True)}")
        # Bot health age: future last success is stale (None).
        bot.db_query = lambda sql, args=None: [
            {"cycle_ts": _ts(60, now, future=True), "cycles_ok": 1}]
        check("GG15 bot: future last-success cycle reads as stale (None)",
              bot.load_health_age_minutes(now) is None,
              f"age={bot.load_health_age_minutes(now)}")
        # Bot PoR live age: a future last_update must not zero the age.
        def fake_query_por_future(sql, args=None):
            if "FROM universe ORDER BY" in sql:
                return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
            if "FROM deviations" in sql:
                return [{"ticker_id": "TSLAx", "ts": _ts(5, now),
                         "depth_weighted_price": 100.5, "dev_vs_median_pct": 0.35,
                         "qualifying_depth_usd": 600000.0, "pools_used": 3}]
            if "FROM redemption_windows" in sql:
                return [{"status": "open", "window_note": None, "next_open_at": None}]
            if "FROM por_feeds" in sql:
                return [{"age_hours": None,
                         "last_update_ts": _ts(120, now, future=True)}]
            if "FROM pools p JOIN snapshots" in sql:
                return [{"dex": "raydium", "price_usd": 100.0, "reserve_usd": 200000.0}]
            raise AssertionError(f"unexpected SQL: {sql[:80]}")

        bot.db_query = fake_query_por_future
        t_por = bot.load_live_tickers()[0]
        check("GG15 bot: future PoR last_update does not zero the age",
              t_por["por_age_hours"] is None,
              f"por_age_hours={t_por['por_age_hours']!r}")
    finally:
        bot.db_query = orig_query

    # Dashboard freshness_status: future last success is stale.
    fut_rows = [{"cycle_ts": _ts(60, now, future=True), "cycles_ok": 1}]
    fs = dash_logic.freshness_status(fut_rows, now)
    check("GG15 dashboard: future last-success cycle is stale",
          fs["stale"] is True, f"age_min={fs['age_min']}")
    past_rows = [{"cycle_ts": _ts(200, now), "cycles_ok": 1}]
    fs2 = dash_logic.freshness_status(past_rows, now)
    check("GG15 dashboard: 200-min-old last success is stale (past dir.)",
          fs2["stale"] is True, f"age_min={fs2['age_min']}")
    fresh_rows = [{"cycle_ts": _ts(5, now), "cycles_ok": 1}]
    fs3 = dash_logic.freshness_status(fresh_rows, now)
    check("GG15 dashboard: 5-min-old last success stays fresh",
          fs3["stale"] is False, f"age_min={fs3['age_min']}")
    # Dashboard PoR effective age: future last_update does not zero age.
    eff = dash_logic.por_effective_age_hours(
        None, _ts(60, now, future=True), now)
    check("GG15 dashboard: future PoR last_update with no stored age is unknown",
          eff is None, f"eff={eff}")
    eff2 = dash_logic.por_effective_age_hours(
        10.0, _ts(60, now, future=True), now)
    check("GG15 dashboard: future PoR last_update keeps stored age",
          eff2 is not None and abs(eff2 - 10.0) < 1e-9, f"eff={eff2}")

    # =====================================================================
    # GG-16 / M1 — an empty poller cycle writes cycles_ok=0, returns False
    # =====================================================================
    def _cycle_stubs(pools, uni_rows, dex_pairs, hourly_state):
        def q(sql, args=None):
            if "FROM poller_health" in sql:
                return []
            if "FROM pools JOIN universe" in sql:
                return pools
            if "token_addresses FROM universe" in sql:
                return uni_rows
            raise AssertionError(f"unexpected SQL: {sql[:80]}")
        return q

    pools1 = [{"pool_id": "p1", "ticker_id": "TSLAx", "chain": "solana",
               "dex": "raydium", "pair_address": "PAIR1", "tier": 1}]
    uni1 = [{"ticker_id": "TSLAx",
             "token_addresses": json.dumps({"solana": "TOKEN1"})}]
    orig_q, orig_dex = poller.query, poller.dex_fetch
    orig_load, orig_save = poller.load_state, poller.save_state
    orig_base, orig_raw = poller.BASE, poller.RAW_DIR
    try:
        poller.query = _cycle_stubs(pools1, uni1, [], {"last_hourly_check": now.isoformat()})
        poller.dex_fetch = lambda url: ([], "200", "")
        poller.load_state = lambda: {"last_hourly_check": now.isoformat()}
        poller.save_state = lambda s: None
        poller.BASE = tmp
        poller.RAW_DIR = os.path.join(tmp, "raw")
        captured["stmts"] = []
        poller.pipeline = cap_pipeline
        with mock.patch("time.sleep", lambda *a, **k: None):
            ok = poller.run_cycle(now)
        hb = captured["stmts"][-1][1]
        check("GG16/M1 empty cycle returns False (not success)",
              ok is False, f"ok={ok}")
        check("GG16/M1 empty cycle heartbeat is cycles_ok=0",
              hb[2] == 0, f"heartbeat={hb}")
        check("GG16/M1 empty cycle writes no snapshots/deviations",
              len(captured["stmts"]) == 1, f"n_stmts={len(captured['stmts'])}")
        # S10: a failing final pipeline still attempts a failure
        # heartbeat and returns False instead of raising away.
        poller.dex_fetch = lambda url: (
            [{"pairAddress": "PAIR1", "priceUsd": "100",
              "liquidity": {"usd": 200000.0, "base": 1, "quote": 1},
              "volume": {"h24": 1}}], "200", "")
        calls = {"n": 0}

        def failing_pipeline(stmts):
            calls["n"] += 1
            raise RuntimeError("simulated Turso failure")

        poller.pipeline = failing_pipeline
        with mock.patch("time.sleep", lambda *a, **k: None):
            try:
                ok2 = poller.run_cycle(now)
            except RuntimeError:
                # Pre-fix behaviour: the failure escapes instead of
                # attempting a failure heartbeat. Record it, don't crash.
                ok2 = "raised"
        check("GG16/S10 final-pipeline failure returns False (not raise)",
              ok2 is False, f"ok={ok2}")
        check("GG16/S10 final-pipeline failure attempts a failure heartbeat",
              calls["n"] >= 2, f"pipeline_calls={calls['n']}")
    finally:
        poller.query, poller.dex_fetch = orig_q, orig_dex
        poller.load_state, poller.save_state = orig_load, orig_save
        poller.BASE, poller.RAW_DIR = orig_base, orig_raw
        poller.pipeline = orig_pipeline

    # =====================================================================
    # GG-16 / M4 — lock open failure raises; contention still returns None
    # =====================================================================
    orig_lock_path = bot.ALERT_LOCK_PATH
    try:
        tmp_lock = os.path.join(tmp, ".bot_alert.lock")
        bot.ALERT_LOCK_PATH = tmp_lock
        l1 = bot.acquire_alert_lock()
        check("GG16/M4 first acquire succeeds (tmp lock)", l1 is not None)
        l2 = bot.acquire_alert_lock()
        check("GG16/M4 contention still returns None (not raise)", l2 is None)
        bot.release_alert_lock(l1)
        l3 = bot.acquire_alert_lock()
        check("GG16/M4 acquire succeeds again after release", l3 is not None)
        bot.release_alert_lock(l3)
        # Open failure: lock path is a directory.
        bot.ALERT_LOCK_PATH = tmp  # a directory, not a file
        raised = False
        try:
            bot.acquire_alert_lock()
        except bot.AlertLockError:
            raised = True
        check("GG16/M4 open() failure RAISES AlertLockError (not None)",
              raised, "acquire returned None instead of raising")
        # --once must exit nonzero on lock failure (fail-closed, never 0).
        orig_tg = bot.tg_api
        orig_send = bot.send_message
        orig_health = bot.load_health_age_minutes
        try:
            bot.tg_api = lambda method, params: {"result": []}
            bot.send_message = lambda cid, text, dry_run=False: {"ok": True}
            bot.load_health_age_minutes = lambda now_utc: 999.0  # stale gate
            off = os.path.join(tmp, ".bot_updates.json")
            old_argv = sys.argv
            sys.argv = ["bot.py", "--once", "--offset-file", off]
            try:
                rc = bot.main()
            finally:
                sys.argv = old_argv
            check("GG16/M4 --once exits NONZERO on lock open failure",
                  rc != 0, f"rc={rc}")
        finally:
            bot.tg_api, bot.send_message = orig_tg, orig_send
            bot.load_health_age_minutes = orig_health
    finally:
        bot.ALERT_LOCK_PATH = orig_lock_path

    # =====================================================================
    # GG-16 / S9 — fallback file failures shout; a lost record is lost
    # =====================================================================
    orig_fb = bot.ALERT_FALLBACK_PATH
    try:
        bot.ALERT_FALLBACK_PATH = tmp  # a directory: unreadable/unwritable
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            markers = bot._fallback_markers()
        check("GG16/S9 unreadable fallback file returns None (not [])",
              markers is None, f"markers={markers!r}")
        check("GG16/S9 unreadable fallback file SHOUTS (loud log)",
              "FAILED" in buf.getvalue(), f"out={buf.getvalue()!r}")
        check("GG16/S9 unknown fallback state does not suppress sends",
              bot._fallback_suppressed(
                  {"ticker": "TSLAx", "type": "deviation_high"}, "en:1") is False)
        orig_exec = bot.db_execute
        try:
            bot.db_execute = lambda sql, args=None: (_ for _ in ()).throw(
                RuntimeError("simulated Turso write failure"))
            with mock.patch("time.sleep", lambda *a, **k: None):
                buf2 = io.StringIO()
                with contextlib.redirect_stdout(buf2):
                    res = bot.record_alert_safe(
                        {"ticker": "TSLAx", "type": "deviation_high"},
                        "msg", "2026-11-09T00:00:00Z", channel="en:1")
            check("GG16/S9 record lost everywhere returns False (lost)",
                  res is False, f"res={res!r}")
            check("GG16/S9 lost record SHOUTS (not silent)",
                  "LOST" in buf2.getvalue(), f"out={buf2.getvalue()!r}")
        finally:
            bot.db_execute = orig_exec
    finally:
        bot.ALERT_FALLBACK_PATH = orig_fb

    # =====================================================================
    # S1 — one alert event shares ONE alert_ts across channels
    # =====================================================================
    fb_path = os.path.join(tmp, ".alert_sent_fallback.jsonl")
    bot.ALERT_FALLBACK_PATH = fb_path
    orig_q2, orig_exec2, orig_send2, orig_fresh = (
        bot.db_query, bot.db_execute, bot.send_message, bot.data_still_fresh)
    try:
        recorded = []
        bot.db_query = lambda sql, args=None: [{"n": 0}]
        bot.db_execute = lambda sql, args=None: recorded.append(
            {"channel": args[7] if len(args) > 7 else None,
             "alert_ts": args[1]})
        bot.send_message = lambda cid, text, dry_run=False: {"ok": True}
        bot.data_still_fresh = lambda: True
        alert = {"type": "deviation_high", "ticker": "TSLAx", "issuer": "xStocks",
                 "dev_pct": 3.5, "dw": 100.0, "median": 100.0,
                 "depth": 3000000.0, "pools_used": 2}
        n = bot.send_alert_channels(alert, [("en", "1"), ("id", "2")], {}, now, delay_s=0)
        check("S1 both channels sent", n == 2, f"sent={n}")
        ts_set = {r["alert_ts"] for r in recorded}
        check("S1 EN+ID rows share ONE alert_ts (feed dedup key holds)",
              len(ts_set) == 1, f"alert_ts values={ts_set}")
    finally:
        bot.db_query, bot.db_execute = orig_q2, orig_exec2
        bot.send_message, bot.data_still_fresh = orig_send2, orig_fresh
        bot.ALERT_FALLBACK_PATH = orig_fb

    # =====================================================================
    # S2 — per-ticker staleness uses the 15-min bound; global gate is 30
    # =====================================================================
    def fake_query_20min(sql, args=None):
        if "FROM universe ORDER BY" in sql:
            return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
        if "FROM deviations" in sql:
            return [{"ticker_id": "TSLAx", "ts": _ts(20, now),
                     "depth_weighted_price": 100.5, "dev_vs_median_pct": 3.5,
                     "qualifying_depth_usd": 600000.0, "pools_used": 3}]
        if "FROM redemption_windows" in sql:
            return [{"status": "open", "window_note": None, "next_open_at": None}]
        if "FROM por_feeds" in sql:
            return []
        if "FROM pools p JOIN snapshots" in sql:
            return [{"dex": "raydium", "price_usd": 100.0, "reserve_usd": 200000.0},
                    {"dex": "orca", "price_usd": 110.0, "reserve_usd": 200000.0}]
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    try:
        bot.db_query = fake_query_20min
        tickers = bot.load_live_tickers()
        check("S2 20-min-old ticker IS dev_stale (web: stale at 15)",
              tickers[0]["dev_stale"] is True,
              f"dev_age_min={tickers[0]['dev_age_min']}")
        check("S2 20-min-old ticker fires NO spread/deviation alert",
              not [a for a in bot.evaluate_alerts(tickers, True)
                   if a["type"] in ("spread", "deviation_high")])
        bot.db_query = lambda sql, args=None: [
            {"cycle_ts": _ts(20, now), "cycles_ok": 1}]
        age = bot.load_health_age_minutes(now)
        check("S2 global gate is still 30 min (20-min-old poller is fresh)",
              age is not None and age <= 30.0, f"age={age}")
    finally:
        bot.db_query = orig_query

    # =====================================================================
    # S3 — stale price fields are dropped from redemption/PoR alerts
    # =====================================================================
    stale_ticker = {
        "ticker": "SPYx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 500.0, "reserve": 3000000.0}],
        "dw": 500.0, "dev_med": 0.10, "depth": 3000000.0,
        "pools_used": 1, "median": 500.0, "dev_stale": True,
        "redemption_status": "closed", "next_open_at": None,
        "por_age_hours": 96.0, "por_last_update": "2026-10-20T11:00:00Z",
    }
    alerts = bot.evaluate_alerts([stale_ticker], False)
    red = [a for a in alerts if a["type"] == "redemption"]
    por = [a for a in alerts if a["type"] == "por"]
    check("S3 stale ticker still fires redemption (not dev-based)",
          len(red) == 1, f"alerts={alerts}")
    check("S3 redemption alert carries NO stale price (dw None)",
          red and red[0].get("dw") is None, f"red={red}")
    check("S3 PoR alert carries NO stale price (dw None)",
          por and por[0].get("dw") is None, f"por={por}")
    if red:
        body = bot.format_alert(red[0], "en")
        check("S3 redemption message renders '—', not the stale price",
              "$500" not in body and "—" in body, f"body={body!r}")

    # =====================================================================
    # S4 — a failed command reply is NOT consumed (offset retries it)
    # =====================================================================
    orig_tg, orig_send = bot.tg_api, bot.send_message
    orig_health = bot.load_health_age_minutes
    try:
        updates = [
            {"update_id": 101, "message": {"chat": {"id": 11}, "text": "/help"}},
            {"update_id": 102, "message": {"chat": {"id": 22}, "text": "/help"}},
        ]
        calls = {"tg": 0, "send": 0, "fail_once": True}
        bot.tg_api = lambda method, params: (calls.__setitem__("tg", calls["tg"] + 1),
                                             {"result": list(updates)})[1]
        bot.load_health_age_minutes = lambda now_utc: 999.0  # stale gate: skip alerts

        def flaky_send(cid, text, dry_run=False):
            calls["send"] += 1
            if calls["fail_once"]:
                calls["fail_once"] = False
                raise RuntimeError("simulated Telegram failure")
            return {"ok": True}

        bot.send_message = flaky_send
        bot.ALERT_LOCK_PATH = os.path.join(tmp, ".bot_alert2.lock")
        off = os.path.join(tmp, ".bot_updates_s4.json")
        old_argv = sys.argv
        try:
            sys.argv = ["bot.py", "--once", "--offset-file", off]
            rc1 = bot.main()
            saved1 = json.load(open(off))
            sys.argv = ["bot.py", "--once", "--offset-file", off]
            rc2 = bot.main()
            saved2 = json.load(open(off))
        finally:
            sys.argv = old_argv
        check("S4 run 1: failed reply is NOT consumed (offset stays None)",
              saved1.get("offset") is None, f"saved={saved1}")
        check("S4 run 2: retried reply succeeds, offset advances past both",
              saved2.get("offset") == 103, f"saved={saved2}")
        check("S4 the failed update was actually retried (3 sends total)",
              calls["send"] == 3, f"sends={calls['send']}")
    finally:
        bot.tg_api, bot.send_message = orig_tg, orig_send
        bot.load_health_age_minutes = orig_health
        bot.ALERT_LOCK_PATH = orig_lock_path

    # =====================================================================
    # S5 — fallback deduplicated by token; dex_fetch retries any 5xx
    # =====================================================================
    try:
        pools2 = [
            {"pool_id": "p1", "ticker_id": "TSLAx", "chain": "solana",
             "dex": "raydium", "pair_address": "PAIR1", "tier": 1},
            {"pool_id": "p2", "ticker_id": "TSLAx", "chain": "solana",
             "dex": "orca", "pair_address": "PAIR2", "tier": 1},
        ]
        poller.query = _cycle_stubs(pools2, uni1, [], {})
        poller.load_state = lambda: {"last_hourly_check": now.isoformat()}
        poller.save_state = lambda s: None
        poller.BASE = tmp
        poller.RAW_DIR = os.path.join(tmp, "raw")
        captured["stmts"] = []
        poller.pipeline = cap_pipeline
        fb_calls = []
        dex_calls = {"n": 0}

        def dex_stub(url):
            dex_calls["n"] += 1
            if dex_calls["n"] == 1:
                return [], "200", ""  # batch: empty 200
            fb_calls.append(url)
            return [{"pairAddress": "PAIR1", "priceUsd": "100",
                     "liquidity": {"usd": 200000.0, "base": 1, "quote": 1},
                     "volume": {"h24": 1}},
                    {"pairAddress": "PAIR2", "priceUsd": "101",
                     "liquidity": {"usd": 200000.0, "base": 1, "quote": 1},
                     "volume": {"h24": 1}}], "200", ""

        poller.dex_fetch = dex_stub
        with mock.patch("time.sleep", lambda *a, **k: None):
            ok = poller.run_cycle(now)
        check("S5 fallback fetches once per DISTINCT token address",
              len(fb_calls) == 1, f"fallback_calls={fb_calls}")
        check("S5 both pools still get snapshots after deduped fallback",
              ok is True, f"ok={ok}")
        # dex_fetch: 504 (a 5xx outside 500/502/503) is retried, and
        # exhaustion reports the REAL last code, never hardcoded "429".
        poller.dex_fetch = orig_dex
        attempts = {"n": 0}

        class FakeResp:
            def __init__(self):
                self.stdout = "…\nHTTP:504"
                self.returncode = 0

        def fake_504(*a, **k):
            attempts["n"] += 1
            return FakeResp()

        with mock.patch("subprocess.run", fake_504):
            with mock.patch("time.sleep", lambda *a, **k: None):
                pairs, code, err = poller.dex_fetch("https://example.invalid/x")
        check("S5 dex_fetch retries a 504 three times",
              attempts["n"] == 3, f"attempts={attempts['n']}")
        check("S5 dex_fetch reports the real code '504', not '429'",
              code == "504", f"code={code!r} err={err!r}")
    finally:
        poller.query, poller.dex_fetch = orig_q, orig_dex
        poller.load_state, poller.save_state = orig_load, orig_save
        poller.BASE, poller.RAW_DIR = orig_base, orig_raw
        poller.pipeline = orig_pipeline

    # =====================================================================
    # S6 — fallback markers are pruned (file cannot grow without bound)
    # =====================================================================
    fb2 = os.path.join(tmp, ".alert_fb2.jsonl")
    bot.ALERT_FALLBACK_PATH = fb2
    try:
        old_nonred = (now - timedelta(hours=49)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_red = (now - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
        keep_red = (now - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(fb2, "w", encoding="utf-8") as f:
            for m in [
                {"ticker": "OLD1", "type": "deviation_high", "channel": "en:1",
                 "alert_ts": old_nonred},
                {"ticker": "OLD2", "type": "redemption", "channel": "en:1",
                 "alert_ts": old_red},
                {"ticker": "KEEP1", "type": "redemption", "channel": "en:1",
                 "alert_ts": keep_red},
                {"ticker": "KEEP2", "type": "deviation_high", "channel": "en:1",
                 "alert_ts": recent},
            ]:
                f.write(json.dumps(m) + "\n")
        bot._append_fallback(
            {"ticker": "NEW", "type": "spread"}, "en:1",
            now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        kept = {m["ticker"] for m in bot._fallback_markers()}
        check("S6 pruning drops 49h-old non-redemption markers",
              "OLD1" not in kept, f"kept={kept}")
        check("S6 pruning drops 31d-old redemption markers",
              "OLD2" not in kept, f"kept={kept}")
        check("S6 pruning keeps 8d-old redemption + recent markers",
              {"KEEP1", "KEEP2", "NEW"} <= kept, f"kept={kept}")
    finally:
        bot.ALERT_FALLBACK_PATH = orig_fb

    # =====================================================================
    # S7 — a window longer than 5000 rows anchors to its TRUE start
    # =====================================================================
    true_start = (now - timedelta(hours=5100)).strftime("%Y-%m-%dT%H:%M:%SZ")
    boundary = (now - timedelta(hours=5101)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows5000 = [{"status": "closed", "window_note": None,
                 "next_open_at": None,
                 "observed_at": (now - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")}
                for i in range(5000)]

    def fake_query_window(sql, args=None):
        if "DISTINCT issuer" in sql:
            return [{"issuer": "xStocks"}]
        if "MAX(observed_at)" in sql:
            return [{"m": boundary}]
        if "ORDER BY observed_at ASC LIMIT 1" in sql:
            return [{"status": "closed", "observed_at": true_start}]
        if "LIMIT 5000" in sql:
            return list(rows5000)
        if "FROM alert_log" in sql:
            return [{"n": 1}]
        if "FROM universe WHERE ticker_id" in sql:
            return [{"issuer": "xStocks"}]
        raise AssertionError(f"unexpected SQL: {sql[:100]}")

    try:
        bot.db_query = fake_query_window
        snap = bot.snapshot_redemption_rows()
        start = bot.window_start_from_rows(
            snap["xStocks"], ("closed", "gated"))
        check("S7 snapshot anchors a >5000-row window to its TRUE start",
              start == true_start, f"start={start}")
        check("S7 snapshot still holds the 5000 fetched rows (+1 marker)",
              len(snap["xStocks"]) == 5001, f"n={len(snap['xStocks'])}")
        # The no-snapshot path (alerted_in_current_window re-querying)
        # gets the same true start, not the oldest returned row.
        hit = bot.alerted_in_current_window(
            "TSLAx", "redemption", ("closed", "gated"), red_rows=None,
            channel=None)
        check("S7 re-queried path also uses the true window start",
              hit is True, f"hit={hit}")
    finally:
        bot.db_query = orig_query

    # =====================================================================
    # S8 — baseline + hourly clock move only on successful writes
    # =====================================================================
    try:
        poller.pipeline = lambda stmts: (_ for _ in ()).throw(
            RuntimeError("simulated Turso failure"))
        state = {"last_mint_supply": {"TSLAx": "100"}}
        poller.solana_mint_info = lambda mint: (False, "200", "")
        with mock.patch("time.sleep", lambda *a, **k: None):
            frag = poller.run_hourly_redemption(now, state)
        check("S8 failed redemption write does NOT mutate the baseline",
              state.get("last_mint_supply") == {"TSLAx": "100"},
              f"state={state}")
        check("S8 failed redemption write returns a failure fragment",
              "failed" in frag, f"frag={frag!r}")
        # run_cycle: clock advances only when BOTH hourly jobs succeed.
        saved = {}

        def save_cap(s):
            saved.clear()
            saved.update(s)

        poller.pipeline = cap_pipeline
        poller.load_state = lambda: {}
        poller.save_state = save_cap
        poller.query = _cycle_stubs(pools1, uni1, [], {})
        poller.dex_fetch = lambda url: (
            [{"pairAddress": "PAIR1", "priceUsd": "100",
              "liquidity": {"usd": 200000.0, "base": 1, "quote": 1},
              "volume": {"h24": 1}}], "200", "")
        poller.BASE = tmp
        poller.RAW_DIR = os.path.join(tmp, "raw")
        orig_red, orig_por = poller.run_hourly_redemption, poller.run_hourly_por
        try:
            poller.run_hourly_redemption = lambda *a, **k: "hourly redemption write failed: x"
            poller.run_hourly_por = lambda *a, **k: ""
            captured["stmts"] = []
            with mock.patch("time.sleep", lambda *a, **k: None):
                poller.run_cycle(now)
            check("S8 clock does NOT advance when redemption fails",
                  "last_hourly_check" not in saved, f"saved={saved}")
            check("S8 failed attempt IS recorded (15-min retry backoff)",
                  "last_hourly_failed_at" in saved, f"saved={saved}")
            poller.run_hourly_redemption = lambda *a, **k: ""
            poller.run_hourly_por = lambda *a, **k: ""
            saved.clear()
            with mock.patch("time.sleep", lambda *a, **k: None):
                poller.run_cycle(now)
            check("S8 clock advances when BOTH hourly jobs succeed",
                  "last_hourly_check" in saved, f"saved={saved}")
            check("S8 success clears the failed-attempt marker",
                  "last_hourly_failed_at" not in saved, f"saved={saved}")
        finally:
            poller.run_hourly_redemption, poller.run_hourly_por = orig_red, orig_por
    finally:
        poller.pipeline = orig_pipeline
        poller.solana_mint_info = orig_mint
        poller.load_state, poller.save_state = orig_load, orig_save
        poller.query, poller.dex_fetch = orig_q, orig_dex
        poller.BASE, poller.RAW_DIR = orig_base, orig_raw

    # =====================================================================
    # S11 — holiday calendar: covers through next year, identical in all
    # four copies (poller, bot, dashboard logic, web format.ts).
    # Tripwire: this check starts failing the year the calendar needs
    # its annual review (max year must be >= current year + 1).
    # =====================================================================
    sets = {
        "poller": _parse_holiday_set_from_py(os.path.join(ROOT, "poller.py")),
        "bot": _parse_holiday_set_from_py(os.path.join(ROOT, "bot.py")),
        "dashboard": _parse_holiday_set_from_py(
            os.path.join(ROOT, "dashboard", "logic.py")),
        "web": _parse_holiday_set_from_ts(
            os.path.join(ROOT, "web", "src", "lib", "format.ts")),
    }
    ref = sets["poller"]
    check("S11 holiday sets are IDENTICAL in all four copies",
          ref is not None and all(s is not None and s == ref for s in sets.values()),
          {k: ("MISSING" if v is None else sorted(v)) for k, v in sets.items() if v != ref})
    max_year = max((int(d[:4]) for d in ref), default=None) if ref else None
    check("S11 calendar covers through the end of NEXT year",
          max_year is not None and max_year >= now.year + 1,
          f"max_year={max_year} now={now.year}")
    check("S11 2028 has the 9 official NYSE closures (no NYD observed)",
          ref is not None
          and len([d for d in ref if d.startswith("2028-")]) == 9
          and "2028-01-01" not in ref,
          f"2028={sorted(d for d in ref if d.startswith('2028-')) if ref else None}")
    check("S11 Thanksgiving 2026-11-26 is a holiday in every copy",
          all(s is not None and "2026-11-26" in s for s in sets.values()))

    # =====================================================================
    # S12 — market-open is holiday-aware (dashboard + web) + honest text
    # =====================================================================
    mio = getattr(dash_logic, "market_is_open", None)
    check("S12 dashboard: Thanksgiving 2026-11-26 (market hours) is CLOSED",
          mio is not None and mio(
              datetime(2026, 11, 26, 15, 0, tzinfo=UTC)) is False,
          "market_is_open missing from logic.py" if mio is None else "")
    check("S12 dashboard: normal Wed 2026-11-25 (market hours) is OPEN",
          mio is not None and mio(
              datetime(2026, 11, 25, 15, 0, tzinfo=UTC)) is True)
    check("S12 dashboard: Saturday is CLOSED",
          mio is not None and mio(
              datetime(2026, 11, 28, 15, 0, tzinfo=UTC)) is False)
    # Web: bundle format.ts with esbuild and exercise marketIsOpen.
    web_out = os.path.join(tmp, "format.cjs")
    esb = subprocess.run(
        [os.path.join(ROOT, "web", "node_modules", ".bin", "esbuild"),
         os.path.join(ROOT, "web", "src", "lib", "format.ts"),
         "--bundle", "--format=cjs", "--platform=node",
         f"--outfile={web_out}", "--log-level=error"],
        capture_output=True, text=True)
    check("S12 web: format.ts bundles with esbuild", esb.returncode == 0,
          esb.stderr[:200])
    if esb.returncode == 0:
        probe = ("const { marketIsOpen } = require(%r);"
                 "console.log(JSON.stringify(["
                 "marketIsOpen(new Date('2026-11-26T15:00:00Z')),"
                 "marketIsOpen(new Date('2026-11-25T15:00:00Z')),"
                 "marketIsOpen(new Date('2026-11-28T15:00:00Z'))]));" % web_out)
        r = subprocess.run(["node", "-e", probe], capture_output=True, text=True)
        got = json.loads(r.stdout) if r.returncode == 0 else None
        check("S12 web: Thanksgiving CLOSED, normal Wed OPEN, Sat CLOSED",
              got == [False, True, False], f"got={got} err={r.stderr[:200]}")
    # Methodology text must no longer claim holidays are untracked.
    for label, path in (("web-EN", os.path.join(ROOT, "web", "src", "lib", "i18n.ts")),
                        ("dash-EN", os.path.join(ROOT, "dashboard", "i18n.py"))):
        src = open(path, encoding="utf-8").read()
        check(f"S12 {label}: methodology no longer says holidays untracked",
              "NOT distinguished" not in src and "not tracked" not in src
              and "tidak dilacak" not in src,
              "stale holiday limitation clause still present")
    check("S12 dash: market_open label no longer says holidays not tracked",
          "exchange holidays not tracked" not in open(
              os.path.join(ROOT, "dashboard", "i18n.py"), encoding="utf-8").read())

    # =====================================================================
    # S13 — dashboard waitlist cap is atomic in the INSERT (Worker parity)
    # =====================================================================
    check("S13 INSERT enforces the hourly cap INSIDE the statement",
          "COUNT(*) FROM waitlist" in INSERT_WAITLIST_SQL
          and "WAITLIST_HOURLY_CAP" not in INSERT_WAITLIST_SQL
          and "< ?" in INSERT_WAITLIST_SQL
          and "NOT EXISTS" in INSERT_WAITLIST_SQL,
          f"sql={INSERT_WAITLIST_SQL[:200]}")
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE waitlist (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " contact TEXT, position_size_usd TEXT, venues TEXT,"
        " willing_price TEXT, created_at TEXT NOT NULL, consent INTEGER NOT NULL DEFAULT 0)")
    try:
        hour_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        for i in range(500):
            con.execute(INSERT_WAITLIST_SQL,
                        (f"user{i}", "$100", "Raydium", None,
                         hour_ts, 1, 500, f"user{i}"))
        cur = con.execute(INSERT_WAITLIST_SQL,
                          ("user500", "$100", "Raydium", None,
                           hour_ts, 1, 500, "user500"))
    except Exception as e:
        # Pre-fix SQL takes 7 args / has no atomic cap: record, don't crash.
        check("S13 501st insert inside the hour is refused by the SQL itself",
              False, f"SQL error (pre-fix shape?): {e}")
        cur = None
    if cur is not None:
        check("S13 501st insert inside the hour is refused by the SQL itself",
              cur.rowcount == 0, f"rowcount={cur.rowcount}")
    n = con.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    check("S13 table still holds exactly 500 rows after refused insert",
          n == 500, f"n={n}")
    # insert_waitlist disambiguation: rows_written 0 + existing -> None;
    # rows_written 0 + absent -> rate limited.
    orig_pipe, orig_qfn = turso_read._pipeline, turso_read.query
    try:
        turso_read._pipeline = lambda stmts: [{"rows_written": 0,
                                               "last_insert_rowid": None}]
        turso_read.query = lambda sql, args=None: (
            [{"n": 0}] if "COUNT(*)" in sql else [{"id": 3}])
        good = dict(contact="valid_user", position_size_usd="$100",
                    venues="Raydium", willing_price=None,
                    created_at="2026-11-08T10:00:00Z", consent=1)
        check("S13 rows_written 0 + existing contact = idempotent None",
              insert_waitlist(**good) is None)
        turso_read.query = lambda sql, args=None: []
        raised = False
        try:
            insert_waitlist(**good)
        except ValueError as e:
            raised = "rate limited" in str(e)
        check("S13 rows_written 0 + absent contact = rate limited",
              raised)
    finally:
        turso_read._pipeline, turso_read.query = orig_pipe, orig_qfn

    # =====================================================================
    # S14/S15 — web API types declare the fields the Worker returns
    # =====================================================================
    api_ts = open(os.path.join(ROOT, "web", "src", "lib", "api.ts"),
                  encoding="utf-8").read()
    m_alert = re.search(r"export type AlertRow = \{(.*?)\};", api_ts, re.S)
    m_meta = re.search(r"export type LatestResponse = \{(.*?)\n\};", api_ts, re.S)
    check("S14 AlertRow declares channel",
          m_alert is not None and "channel" in m_alert.group(1),
          "AlertRow has no channel field")
    check("S15 LatestResponse.meta declares stale_tickers",
          m_meta is not None and "stale_tickers" in m_meta.group(1),
          "meta has no stale_tickers field")
    tsc = subprocess.run(
        [os.path.join(ROOT, "web", "node_modules", ".bin", "tsc"), "--noEmit"],
        cwd=os.path.join(ROOT, "web"), capture_output=True, text=True)
    check("S14/S15 web `tsc --noEmit` passes", tsc.returncode == 0,
          (tsc.stdout + tsc.stderr)[:300])

    # =====================================================================
    # S16 — dashboard coverage line says PoR is LIVE (as on the web)
    # =====================================================================
    sys.path.insert(0, os.path.join(ROOT, "dashboard"))
    import i18n as dash_i18n  # noqa: E402
    for lang in ("en", "id"):
        line = dash_i18n.STR[lang]["coverage_live_line"]
        low = line.lower()
        # The line must not claim PoR itself is unavailable: "PoR ...
        # not (yet) available" in one sentence is the false claim.
        # ("Vs-close is not yet available" in its own sentence is
        # correct and stays.)
        bad = re.search(r"proof-of-reserve[^.]*?(not yet available|belum tersedia)", low)
        check(f"S16 dashboard [{lang}]: coverage line says PoR is live",
              "proof-of-reserve" in low and bad is None,
              f"line={line!r}")
        coming = dash_i18n.STR[lang]["coming_text"]
        check(f"S16 dashboard [{lang}]: coming-soon no longer lists PoR",
              "PoR feed" not in coming and "Feed PoR" not in coming,
              f"coming={coming!r}")

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("R8 FIX TEST (part 1): PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
