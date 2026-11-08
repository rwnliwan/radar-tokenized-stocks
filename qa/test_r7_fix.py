"""Round-7 fix tests (Terra r7 Radar: M1, M2, S1-S9, N1).

Pure + monkeypatched-DB only: no network, no token, no Telegram send,
no production reads/writes. The Worker-side items (M1 API fields, S1
cache revalidation, S6 cycle anchor, S7 feed dedup, N1 null body) are
covered by qa/test_r7_worker.mjs (Node, stubbed Hrana fetch).

- M1: per-ticker staleness. A ticker whose own deviations row is old
  (> STALE_MINUTES) must not fire spread/deviation alerts on stale
  dw/dev, even when the poller as a whole is healthy. Redemption/PoR
  alerts (which do not depend on the dev row) still fire.
- M2: send-then-record. When the Turso record fails AFTER a Telegram
  send (3 retries exhausted), the delivery is written to the local
  fallback file and the next pass must NOT re-send it.
- S2: the stale gate is re-checked before EACH channel send.
- S3: overlapping alert passes are serialized by the flock.
- S4: redemption windows longer than 500 hourly rows still dedup.
- S5: the recorded alert_ts is the delivery time, not pass-start time.
- S8: the dedup key is "lang:chat_id", not the bare language.

Thresholds are NOT changed here (spread 1.0%, dev 3.0%, depth $250k,
dedup 24h, stale gate 30 min, per-ticker stale 15 min on the Worker).

Usage: python3 qa/test_r7_fix.py  (exit 0 = PASS)
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks")
import bot  # noqa: E402  (token is lazy; import touches no vault/DB)

FAILURES = []
UTC = timezone.utc


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _ts(minutes_ago, now):
    return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _alert_dev(ticker="TSLAx"):
    return {"type": "deviation_high", "ticker": ticker, "issuer": "xStocks",
            "dev_pct": 3.5, "dw": 100.0, "median": 100.0,
            "depth": 3000000.0, "pools_used": 2}


def main():
    now = datetime.now(UTC).replace(microsecond=0)

    # --- M1: per-ticker staleness in load + evaluate -----------------
    def fake_query_m1(sql, args=None):
        if "FROM universe ORDER BY" in sql:
            return [{"ticker_id": "TSLAx", "issuer": "xStocks"},
                    {"ticker_id": "SPYx", "issuer": "xStocks"},
                    {"ticker_id": "NVDAx", "issuer": "xStocks"}]
        if "FROM deviations" in sql:
            # TSLAx fresh (5 min), SPYx stale (200 min), NVDAx absent.
            return [{"ticker_id": "TSLAx", "ts": _ts(5, now),
                     "depth_weighted_price": 100.5,
                     "dev_vs_median_pct": 3.5,
                     "qualifying_depth_usd": 600000.0, "pools_used": 3},
                    {"ticker_id": "SPYx", "ts": _ts(200, now),
                     "depth_weighted_price": 100.0,
                     "dev_vs_median_pct": 3.5,
                     "qualifying_depth_usd": 600000.0, "pools_used": 3}]
        if "FROM redemption_windows" in sql:
            return [{"status": "closed", "window_note": None,
                     "next_open_at": None}]
        if "FROM por_feeds" in sql:
            return []
        if "FROM pools p JOIN snapshots" in sql:
            # Venues with a 10% spread — would fire if evaluated.
            return [{"dex": "raydium", "price_usd": 100.0, "reserve_usd": 200000.0},
                    {"dex": "orca", "price_usd": 110.0, "reserve_usd": 200000.0}]
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    orig_query = bot.db_query
    try:
        bot.db_query = fake_query_m1
        tickers = bot.load_live_tickers()
        by = {t["ticker"]: t for t in tickers}
        check("M1 fresh ticker is not dev_stale (5 min old)",
              by["TSLAx"]["dev_stale"] is False,
              f"dev_stale={by['TSLAx']['dev_stale']}")
        check("M1 stale ticker IS dev_stale (200 min old)",
              by["SPYx"]["dev_stale"] is True,
              f"dev_stale={by['SPYx']['dev_stale']} age={by['SPYx']['dev_age_min']}")
        check("M1 ticker with no deviations row IS dev_stale",
              by["NVDAx"]["dev_stale"] is True,
              f"dev_stale={by['NVDAx']['dev_stale']}")
        alerts = bot.evaluate_alerts(tickers, True)
        types = {(a["ticker"], a["type"]) for a in alerts}
        check("M1 fresh ticker still fires deviation_high",
              ("TSLAx", "deviation_high") in types, f"alerts={types}")
        check("M1 stale ticker fires NO spread alert on old data",
              ("SPYx", "spread") not in types, f"alerts={types}")
        check("M1 stale ticker fires NO deviation alert on old data",
              ("SPYx", "deviation_high") not in types, f"alerts={types}")
        check("M1 stale ticker STILL fires redemption (not dev-based)",
              ("SPYx", "redemption") in types, f"alerts={types}")
        check("M1 no-row ticker fires NO spread/deviation, redemption only",
              ("NVDAx", "spread") not in types
              and ("NVDAx", "deviation_high") not in types
              and ("NVDAx", "redemption") in types, f"alerts={types}")
    finally:
        bot.db_query = orig_query

    # --- M2 / S2 / S5 / S8: delivery paths (fallback file in tmp) ----
    tmp = tempfile.mkdtemp(prefix="r7_radar_")
    fb_path = os.path.join(tmp, ".alert_sent_fallback.jsonl")
    orig_fb = bot.ALERT_FALLBACK_PATH
    bot.ALERT_FALLBACK_PATH = fb_path
    orig_query2, orig_execute, orig_send, orig_fresh = (
        bot.db_query, bot.db_execute, bot.send_message, bot.data_still_fresh)
    try:
        recorded = []
        sends = []

        def fake_query_log(sql, args=None):
            if "FROM alert_log" in sql:
                ch = args[-1] if "channel" in sql else None
                n = sum(1 for r in recorded
                        if ch is None or r["channel"] == ch or r["channel"] is None)
                return [{"n": n}]
            return [{"n": 0}]

        bot.db_query = fake_query_log
        bot.send_message = lambda cid, text, dry_run=False: sends.append(cid) or {"ok": True}
        bot.data_still_fresh = lambda: True

        # M2: record ALWAYS fails after a successful send.
        attempts = {"n": 0}

        def failing_execute(sql, args=None):
            attempts["n"] += 1
            raise RuntimeError("simulated Turso write failure")

        bot.db_execute = failing_execute
        alert = _alert_dev()
        n1 = bot.send_alert_channels(alert, [("en", "1")], {}, now, delay_s=0)
        check("M2 send still counts as sent when record fails (Telegram got it)",
              n1 == 1 and sends == ["1"], f"sent={n1} sends={sends}")
        check("M2 record retried 3x before giving up",
              attempts["n"] == 3, f"attempts={attempts['n']}")
        markers = bot._fallback_markers()
        check("M2 failed record lands in the fallback file (channel en:1)",
              len(markers) == 1 and markers[0]["channel"] == "en:1"
              and markers[0]["ticker"] == "TSLAx"
              and markers[0]["type"] == "deviation_high",
              f"markers={markers}")
        n2 = bot.send_alert_channels(alert, [("en", "1")], {}, now, delay_s=0)
        check("M2 next pass does NOT re-send (fallback suppresses)",
              n2 == 0 and sends == ["1"], f"sent={n2} sends={sends}")
        check("M2 fallback suppression_reason is 'dedup 24h'",
              bot.suppression_reason(alert, {}, channel="en:1") == "dedup 24h")

        # M2 (redemption): fallback marker inside the current window
        # suppresses with "same window", not just 24h.
        red_alert = {"type": "redemption", "ticker": "SPYx", "issuer": "xStocks",
                     "status": "closed", "next_open_at": None,
                     "closes_within_24h": False, "dw": 500.0,
                     "depth": 3000000.0, "pools_used": 1}
        window_start = _ts(120, now)
        red_snapshot = {"xStocks": [{"status": "closed", "observed_at": window_start}]}
        n3 = bot.send_alert_channels(red_alert, [("en", "1")], red_snapshot, now, delay_s=0)
        check("M2 redemption send counts as sent when record fails",
              n3 == 1, f"sent={n3}")
        check("M2 redemption fallback suppresses as 'same window'",
              bot.suppression_reason(red_alert, red_snapshot, channel="en:1") == "same window")

        # S8: a different destination is NOT suppressed by the old one.
        check("S8 new destination is not suppressed by old destination's row",
              bot.suppression_reason(alert, {}, channel="en:999") is None)
        check("S8 old destination stays suppressed",
              bot.suppression_reason(alert, {}, channel="en:1") == "dedup 24h")

        # S2: gate goes stale between the EN and ID sends.
        os.remove(fb_path)
        sends.clear()
        attempts["n"] = 0
        bot.db_execute = lambda sql, args=None: recorded.append(
            {"channel": args[7] if len(args) > 7 else None})
        fresh_calls = {"n": 0}

        def fresh_then_stale():
            fresh_calls["n"] += 1
            return fresh_calls["n"] == 1

        bot.data_still_fresh = fresh_then_stale
        n4 = bot.send_alert_channels(alert, [("en", "1"), ("id", "2")], {}, now, delay_s=0)
        check("S2 only the first channel sends once the gate goes stale",
              n4 == 1 and sends == ["1"], f"sent={n4} sends={sends}")
        check("S2 only the sent channel is recorded (composite key en:1)",
              [r["channel"] for r in recorded] == ["en:1"],
              f"recorded={recorded}")

        # S5: recorded ts is the delivery time, not the pass-start time.
        recorded.clear()
        sends.clear()
        bot.data_still_fresh = lambda: True
        stale_now = now - timedelta(hours=3)
        n5 = bot.send_alert_channels(alert, [("en", "1")], {}, stale_now, delay_s=0)
        check("S5 one channel sent with a 3h-old pass-start now",
              n5 == 1, f"sent={n5}")
        # The recorded alert_ts is captured by the fake db_execute via
        # record_alert's args[1]; re-derive it from the last call.
        # (fake above appends only channel; re-run with a capturing fn.)
        captured = {}

        def capturing_execute(sql, args=None):
            captured["alert_ts"] = args[1]
            recorded.append({"channel": args[7] if len(args) > 7 else None})

        bot.db_execute = capturing_execute
        bot.send_alert_channels(alert, [("id", "2")], {}, stale_now, delay_s=0)
        ts = bot.parse_ts(captured.get("alert_ts"))
        age_s = abs((datetime.now(UTC) - ts).total_seconds()) if ts else None
        check("S5 recorded alert_ts is delivery time (seconds old, not 3h)",
              age_s is not None and age_s < 120,
              f"alert_ts={captured.get('alert_ts')} age_s={age_s}")
    finally:
        bot.db_query, bot.db_execute, bot.send_message = orig_query2, orig_execute, orig_send
        bot.data_still_fresh = orig_fresh
        bot.ALERT_FALLBACK_PATH = orig_fb

    # --- S3: single-pass lock ----------------------------------------
    lock1 = bot.acquire_alert_lock()
    check("S3 first acquire succeeds", lock1 is not None)
    lock2 = bot.acquire_alert_lock()
    check("S3 second acquire fails while first is held", lock2 is None)
    bot.release_alert_lock(lock1)
    lock3 = bot.acquire_alert_lock()
    check("S3 acquire succeeds again after release", lock3 is not None)
    bot.release_alert_lock(lock3)
    try:
        os.remove(bot.ALERT_LOCK_PATH)
    except OSError:
        pass

    # --- S4: redemption window beyond 500 hourly rows -----------------
    rows = [{"status": "closed",
             "observed_at": (now - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")}
            for i in range(600)]
    start = bot.window_start_from_rows(rows, ("closed", "gated"))
    check("S4 window start found across 600 hourly rows (~25 days)",
          start == rows[-1]["observed_at"], f"start={start}")
    seen_sql = {}

    def fake_query_window(sql, args=None):
        seen_sql["sql"] = sql
        if "DISTINCT issuer" in sql:
            return [{"issuer": "xStocks"}]
        return rows

    bot.db_query = fake_query_window
    try:
        snap = bot.snapshot_redemption_rows()
        check("S4 snapshot query uses LIMIT 5000 (not 500)",
              "LIMIT 5000" in seen_sql.get("sql", ""), f"sql={seen_sql.get('sql')}")
        check("S4 snapshot holds all 600 rows for the issuer",
              len(snap.get("xStocks", [])) == 600, f"n={len(snap.get('xStocks', []))}")
    finally:
        bot.db_query = orig_query

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("R7 FIX TEST: PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
