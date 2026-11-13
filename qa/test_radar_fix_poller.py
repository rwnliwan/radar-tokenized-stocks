"""Fix-round tests: DeepSeek Radar review, poller.py only (2026-11-13).

Pure + stubbed + local-sqlite-copy only: no network, no token, no
Telegram send, no live DB reads/writes. Every DB here is a throwaway
sqlite copy built in a temp dir from schema.sql (+ the two new
columns, as the companion migration migrations/2026-11-13-radar-fix.sql
will add them live — this file does NOT apply anything to Turso).

Coverage (one section per finding; thresholds UNCHANGED — alert 1.0%,
pool >= $100k, universe >= $500k + >= 2 venues):
- M2  Monday open is 14:30 UTC in EST (not 13:30 EDT).
- M3  calibration counts DISTINCT week_start, not rows.
- M4  redemption status is per issuer (WHERE issuer = ?).
- M5  deviations.exit_score_components is written.
- S2  perp_px_source tags 'mark' vs 'mid'.
- S6  liquidation state is refreshed on EVERY exit path.
- S7  missed week is reported MISSED; fill_outcomes is bounded to
      the last 8 weeks.
- S8  'closed' redemption scales by hours to next open (not a
      constant 20).
- S14 OI 24h-ago is ONE batched query per cycle.
- N3  7-day median older than 7 days is not used.
- M10 startup guard passes on a complete schema, fails (exit 2)
      on an incomplete one.

Usage: python3 qa/test_radar_fix_poller.py  (exit 0 = PASS)
"""
import contextlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks")
import poller  # noqa: E402

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
UTC = timezone.utc
FAILURES = []
PATCHED = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def patch(obj, name, value):
    PATCHED.append((obj, name, getattr(obj, name)))
    setattr(obj, name, value)


def restore_all():
    while PATCHED:
        obj, name, value = PATCHED.pop()
        setattr(obj, name, value)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def make_db(extra_sql=""):
    """Throwaway local sqlite copy: schema.sql (+ the two new columns
    and two new indexes, as migrations/2026-11-13-radar-fix.sql adds
    them live — this file does NOT apply anything to Turso).
    schema.sql already declares the new columns/indexes (fresh-DB
    record of the same migration), so the ALTERs below run only when
    the column is absent, like the migration runner does."""
    tmp = tempfile.mkdtemp(prefix="radar_fix_")
    path = os.path.join(tmp, "radar.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(read("schema.sql"))
    for tbl, col, decl in (
            ("deviations", "exit_score_components", "INTEGER"),
            ("perp_snapshots", "perp_px_source", "TEXT")):
        have = {r["name"] for r in conn.execute(
            f"SELECT name FROM pragma_table_info('{tbl}')")}
        if col not in have:
            conn.execute(
                f"ALTER TABLE {tbl} ADD COLUMN {col} {decl}")
    conn.executescript(
        "CREATE INDEX IF NOT EXISTS idx_poller_health_cycle_ts"
        " ON poller_health(cycle_ts);"
        "CREATE INDEX IF NOT EXISTS idx_deviations_ts"
        " ON deviations(ts);"
        + extra_sql)
    conn.commit()
    return conn


def sqlite_query(conn):
    """A poller.query-compatible read over a local sqlite conn."""
    def q(sql, args=None):
        cur = conn.execute(sql, args or [])
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    return q


def recording_pipeline(conn, captured):
    """A poller.pipeline-compatible write: records + executes locally."""
    def pipe(stmts):
        captured.extend(stmts)
        for sql, args in stmts:
            conn.execute(sql, args or [])
        conn.commit()
        return [{} for _ in stmts]
    return pipe


def dev_row(ticker, ts, dw):
    return {"ticker_id": ticker, "ts": ts, "depth_weighted_price": dw,
            "dev_vs_median_pct": 1.0, "qualifying_depth_usd": 3000000.0,
            "pools_used": 3}


def main():
    now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)  # Fri, 07:00 ET
    poller_src = read("poller.py")

    try:
        # =================================================================
        # M2 — Monday open 14:30 UTC (EST), not 13:30 (EDT)
        # =================================================================
        check("M2 fill uses 14:30 UTC for the Monday open",
              'mon.strftime("%Y-%m-%dT14:30:00Z")' in poller_src)
        check("M2 no 13:30 open remains in executable code",
              'mon.strftime("%Y-%m-%dT13:30:00Z")' not in poller_src)
        check("M2 dated EST comment explains the window + Mar 2027 flip",
              "EST" in poller_src and "14 Mar 2027" in poller_src
              and "13:30" in poller_src)
        conn = make_db()
        try:
            conn.execute(
                "INSERT INTO monday_gap (id, ticker_id, week_start,"
                " gap_pred_pct, confidence, method_version, outcome)"
                " VALUES (1, 'TSLAx', '2026-11-14', 10.0, 50.0,"
                " 'monday_gap_v1', 'pending')")
            for ts, dw in (("2026-11-15T22:00:00Z", 100.0),   # Sunday
                           ("2026-11-16T14:00:00Z", 101.0),   # Mon 14:00 (< 14:30)
                           ("2026-11-16T15:00:00Z", 110.0)):  # Mon 15:00
                r = dev_row("TSLAx", ts, dw)
                conn.execute(
                    "INSERT INTO deviations (ticker_id, ts,"
                    " depth_weighted_price, dev_vs_median_pct,"
                    " qualifying_depth_usd, pools_used)"
                    " VALUES (?,?,?,?,?,?)",
                    [r["ticker_id"], r["ts"], r["depth_weighted_price"],
                     r["dev_vs_median_pct"], r["qualifying_depth_usd"],
                     r["pools_used"]])
            conn.commit()
            captured = []
            patch(poller, "query", sqlite_query(conn))
            patch(poller, "pipeline", recording_pipeline(conn, captured))
            mon = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
            frag = poller._monday_gap_fill_outcomes(mon, {})
            updates = [a for s, a in captured if s.startswith("UPDATE monday_gap")]
            check("M2 Monday actual uses the first dw AT/AFTER 14:30 "
                  "(15:00 dw 110, not 14:00 dw 101)",
                  len(updates) == 1 and updates[0][0] == 10.0
                  and updates[0][1] == "accurate",
                  f"updates={updates} frag={frag!r}")
        finally:
            conn.close()
            restore_all()

        # =================================================================
        # M3 — calibration counts DISTINCT week_start, not rows
        # =================================================================
        conn = make_db()
        try:
            for i in range(43):  # ONE weekend, 43 tickers -> 43 rows
                conn.execute(
                    "INSERT INTO monday_gap (ticker_id, week_start,"
                    " gap_pred_pct, confidence, method_version, outcome)"
                    " VALUES (?, '2026-11-07', 1.0, 50.0,"
                    " 'monday_gap_v1', 'accurate')", [f"T{i:02d}"])
            for i in range(2):  # a second judged weekend, 2 rows
                conn.execute(
                    "INSERT INTO monday_gap (ticker_id, week_start,"
                    " gap_pred_pct, confidence, method_version, outcome)"
                    " VALUES (?, '2026-10-31', 1.0, 50.0,"
                    " 'monday_gap_v1', 'accurate')", [f"U{i:02d}"])
            conn.commit()
            captured = []
            patch(poller, "query", sqlite_query(conn))
            patch(poller, "pipeline", recording_pipeline(conn, captured))
            patch(poller, "_latest_deviations_row",
                  lambda ticker, ts_from, ts_to=None: {
                      "depth_weighted_price": 100.0,
                      "dev_vs_median_pct": 1.0,
                      "qualifying_depth_usd": 3000000.0,
                      "pools_used": 3, "ts": "2026-11-15T22:00:00Z"})
            patch(poller, "_sunday_spread_pct", lambda ticker, sunday_ts: 0.1)
            calib_seen, conf_seen = [], []
            orig_mgp = poller.monday_gap_predict

            def wrap_mgp(*a, **k):
                calib_seen.append(a[5])
                out = orig_mgp(*a, **k)
                conf_seen.append(out[1])
                return out

            patch(poller, "monday_gap_predict", wrap_mgp)
            sun = datetime(2026, 11, 15, 22, 30, tzinfo=UTC)
            frag = poller._monday_gap_predict(sun, {})
            check("M3 calibration is 2 DISTINCT weekends, not 45 rows",
                  calib_seen and all(c == 2 for c in calib_seen),
                  f"calibrated_weekends seen={sorted(set(calib_seen))}")
            check("M3 confidence uses 5*2=10 calibration points "
                  "(30 quality + 0 direction + 20 spread + 10 calib = 60)",
                  conf_seen and all(c == 60.0 for c in conf_seen),
                  f"conf={sorted(set(conf_seen))}")
            check("M3 one prediction row per xStocks ticker (13)",
                  len([s for s, _ in captured
                       if s.startswith("INSERT INTO monday_gap")]) == 13,
                  f"inserts={len(captured)} frag={frag!r}")
        finally:
            conn.close()
            restore_all()

        # =================================================================
        # M4 — redemption status is per issuer
        # =================================================================
        conn = make_db()
        try:
            for issuer, status, obs in (
                    ("xStocks", "open", "2026-11-13T16:46:00Z"),
                    ("bstocks", "unknown", "2026-11-13T13:42:00Z"),
                    ("robinhood", "closed", "2026-11-13T10:00:00Z")):
                conn.execute(
                    "INSERT INTO redemption_windows (issuer, asset, status,"
                    " observed_at) VALUES (?, 'ALL', ?, ?)",
                    [issuer, status, obs])
            conn.commit()
            patch(poller, "query", sqlite_query(conn))
            st_x, close_x = poller._latest_redemption_status(now, "xStocks")
            st_b, close_b = poller._latest_redemption_status(now, "bstocks")
            st_r, close_r = poller._latest_redemption_status(now, "robinhood")
            st_none, _ = poller._latest_redemption_status(now, "coinbase")
            check("M4 xStocks reads its OWN latest row ('open')",
                  st_x == "open", f"got={st_x!r}")
            check("M4 bstocks reads its OWN latest row ('unknown'), "
                  "not the newer xStocks 'open'",
                  st_b == "unknown", f"got={st_b!r}")
            check("M4 robinhood reads its OWN latest row ('closed')",
                  st_r == "closed", f"got={st_r!r}")
            check("M4 an issuer with no rows reads None (never borrowed)",
                  st_none is None, f"got={st_none!r}")
            check("M4 open close-in-hours is ~17h (Fri 12:00 UTC -> "
                  "Sat 00:00 ET)",
                  close_x is not None and 16.0 < close_x < 18.0,
                  f"close_h={close_x}")
            check("M4 closed hours-to-next-open is ~65h (Fri 12:00 UTC "
                  "-> Mon 00:00 ET)",
                  close_r is not None and 64.0 < close_r < 66.0,
                  f"close_h={close_r}")
            check("M4 unknown status carries no close hours",
                  close_b is None, f"close_h={close_b}")
            check("M4 the query filters by issuer (WHERE issuer = ?)",
                  "WHERE issuer = ?" in poller_src)
        finally:
            conn.close()
            restore_all()

        # =================================================================
        # M5 + M4-threading + S14-use — one stubbed run_cycle
        # =================================================================
        tmp = tempfile.mkdtemp(prefix="radar_fix_cycle_")
        orig_base, orig_raw = poller.BASE, poller.RAW_DIR
        orig_load, orig_save = poller.load_state, poller.save_state
        try:
            poller.BASE = tmp
            poller.RAW_DIR = os.path.join(tmp, "raw")
            poller.load_state = lambda: {}
            saved = {}
            poller.save_state = lambda s: saved.update(s)
            pools = [
                {"pool_id": "p1", "ticker_id": "TSLAx", "chain": "solana",
                 "dex": "raydium", "pair_address": "PAIR1", "tier": 1},
                {"pool_id": "p2", "ticker_id": "NVDAx", "chain": "solana",
                 "dex": "orca", "pair_address": "PAIR2", "tier": 1},
                {"pool_id": "p3", "ticker_id": "TSLAc", "chain": "base",
                 "dex": "aero", "pair_address": "PAIR3", "tier": 1},
            ]
            uni = [
                {"ticker_id": "TSLAx", "issuer": "xStocks",
                 "token_addresses": json.dumps({"solana": "TOK1"})},
                {"ticker_id": "NVDAx", "issuer": "xStocks",
                 "token_addresses": json.dumps({"solana": "TOK2"})},
                {"ticker_id": "TSLAc", "issuer": "coinbase",
                 "token_addresses": json.dumps({"base": "TOK3"})},
            ]
            pairs = {
                "PAIR1": {"pairAddress": "PAIR1", "priceUsd": "100",
                          "liquidity": {"usd": 200000.0, "base": 1, "quote": 1},
                          "volume": {"h24": 1}},
                "PAIR2": {"pairAddress": "PAIR2", "priceUsd": "200",
                          "liquidity": {"usd": 200000.0, "base": 1, "quote": 1},
                          "volume": {"h24": 1}},
                "PAIR3": {"pairAddress": "PAIR3", "priceUsd": "300",
                          "liquidity": {"usd": 200000.0, "base": 1, "quote": 1},
                          "volume": {"h24": 1}},
            }

            def q_cycle(sql, args=None):
                if "FROM poller_health" in sql:
                    return [{"n": 0}]
                if "FROM pools JOIN universe" in sql:
                    return list(pools)
                if "token_addresses FROM universe" in sql:
                    return list(uni)
                if "FROM redemption_windows" in sql:
                    return [{"status": "open"}] if args and args[0] == "xStocks" \
                        else [{"status": "unknown"}]
                if "FROM deviations" in sql or "FROM perp_snapshots" in sql:
                    return []
                raise AssertionError(f"unexpected SQL in run_cycle: {sql[:90]}")

            patch(poller, "query", q_cycle)
            captured = []
            patch(poller, "pipeline",
                  lambda stmts: (captured.extend(stmts),
                                 [{} for _ in stmts])[1])
            patch(poller, "dex_fetch",
                  lambda url: ([pairs[k] for k in ("PAIR1", "PAIR2", "PAIR3")],
                               "200", ""))
            patch(poller, "run_hourly_redemption", lambda *a, **k: "")
            patch(poller, "run_hourly_por", lambda *a, **k: "")
            patch(poller, "run_hourly_liquidation", lambda *a, **k: "")
            patch(poller, "run_weekly_monday_gap", lambda *a, **k: "")
            red_calls = []
            orig_red = poller._latest_redemption_status

            def red_wrap(cycle_dt, issuer):
                red_calls.append(issuer)
                return orig_red(cycle_dt, issuer)

            patch(poller, "_latest_redemption_status", red_wrap)
            batch_calls = []
            orig_batch = poller._oi_24h_ago_batch

            def batch_wrap(tickers, cycle_dt):
                batch_calls.append(list(tickers))
                return orig_batch(tickers, cycle_dt)

            patch(poller, "_oi_24h_ago_batch", batch_wrap)

            def no_singular(*a, **k):
                raise AssertionError(
                    "_oi_24h_ago (singular) must not be called by run_cycle")

            patch(poller, "_oi_24h_ago", no_singular)
            ok = poller.run_cycle(now)
            dev_stmts = [(s, a) for s, a in captured
                         if s.startswith("INSERT INTO deviations")]
            by_ticker = {a[0]: (s, a) for s, a in dev_stmts}
            check("M5 run_cycle succeeds on the stubbed cycle",
                  ok is True, f"ok={ok}")
            check("M5 deviations INSERT lists exit_score_components",
                  all("exit_score_components" in s for s, _ in dev_stmts)
                  and len(dev_stmts) == 3, f"n={len(dev_stmts)}")
            check("M5 deviations rows carry 15 values (components is #14)",
                  all(len(a) == 15 for _, a in dev_stmts),
                  f"lens={[len(a) for _, a in dev_stmts]}")
            # One qualifying pool per ticker -> dev None, depth median
            # None, funding/OI None; only the redemption component can
            # be present. xStocks 'open' -> 1; coinbase 'unknown' -> 0.
            check("M5 xStocks tickers write components_present=1 "
                  "(redemption only) with score 100.0",
                  by_ticker["TSLAx"][1][13] == 1
                  and by_ticker["TSLAx"][1][11] == 100.0
                  and by_ticker["NVDAx"][1][13] == 1,
                  f"TSLAx={by_ticker.get('TSLAx', (None, []))[1]}")
            check("M5 coinbase ticker writes components_present=0 and "
                  "score NULL (unknown redemption is not counted)",
                  by_ticker["TSLAc"][1][13] == 0
                  and by_ticker["TSLAc"][1][11] is None,
                  f"TSLAc={by_ticker.get('TSLAc', (None, []))[1]}")
            check("M4 run_cycle resolves redemption ONCE per distinct "
                  "issuer (xStocks x1 despite 2 tickers, coinbase x1)",
                  sorted(red_calls) == ["coinbase", "xStocks"],
                  f"calls={red_calls}")
            check("S14 run_cycle uses the batch OI lookup exactly once "
                  "and never the singular one",
                  len(batch_calls) == 1 and batch_calls[0] == [],
                  f"batch_calls={batch_calls}")
        finally:
            poller.BASE, poller.RAW_DIR = orig_base, orig_raw
            poller.load_state, poller.save_state = orig_load, orig_save
            restore_all()

        # =================================================================
        # S2 — perp_px_source 'mark' vs 'mid'
        # =================================================================
        try:
            captured = []
            patch(poller, "pipeline",
                  lambda stmts: (captured.extend(stmts),
                                 [{} for _ in stmts])[1])
            patch(poller, "fetch_xyz_market_data", lambda: ({
                "TSLAx": {"perp_px": 100.0, "funding": 0.001,
                          "oi_usd": 1000.0, "mark_px": 100.0,
                          "oracle_px": 99.0},
                "NVDAx": {"perp_px": 200.0, "funding": None,
                          "oi_usd": None, "mark_px": None,
                          "oracle_px": None}}, ""))
            state = {}
            frag = poller.run_cycle_perp(now, state)
            perp_stmts = [(s, a) for s, a in captured
                          if s.startswith("INSERT INTO perp_snapshots")]
            by_ticker = {a[0]: a for _, a in perp_stmts}
            check("S2 perp rows list the perp_px_source column",
                  all("perp_px_source" in s for s, _ in perp_stmts)
                  and len(perp_stmts) == 2, f"n={len(perp_stmts)}")
            check("S2 mark price is tagged 'mark'",
                  by_ticker.get("TSLAx", [None] * 7)[6] == "mark",
                  f"TSLAx={by_ticker.get('TSLAx')}")
            check("S2 mid fallback is tagged 'mid'",
                  by_ticker.get("NVDAx", [None] * 7)[6] == "mid",
                  f"NVDAx={by_ticker.get('NVDAx')}")
            check("S2 perp cycle still succeeds", frag == "", f"frag={frag!r}")
        finally:
            restore_all()

        # =================================================================
        # S6 — liquidation state refreshed on EVERY exit path
        # =================================================================
        try:
            patch(poller, "pipeline", lambda stmts: [{} for _ in stmts])
            # (a) ctxs unavailable -> stale set is CLEARED, not kept.
            patch(poller, "fetch_xyz_ctxs", lambda: ({}, "boom"))
            state = {"liquidation_alert_tickers": {"TSLAx": "critical"}}
            frag = poller.run_hourly_liquidation(now, state)
            check("S6 ctxs failure clears the stale alert set",
                  state.get("liquidation_alert_tickers") == {},
                  f"state={state} frag={frag!r}")
            check("S6 ctxs failure still returns a fragment",
                  "unavailable" in frag, f"frag={frag!r}")
            # (b) ctxs present but no market has mark+oracle -> cleared.
            patch(poller, "fetch_xyz_ctxs", lambda: (
                {"TSLAx": {"mark_px": None, "oracle_px": 100.0}}, ""))
            state = {"liquidation_alert_tickers": {"TSLAx": "warning"}}
            frag = poller.run_hourly_liquidation(now, state)
            check("S6 no-rows path clears the stale alert set",
                  state.get("liquidation_alert_tickers") == {},
                  f"state={state} frag={frag!r}")
            # (c) write failure -> cleared.
            patch(poller, "fetch_xyz_ctxs", lambda: (
                {"TSLAx": {"mark_px": 100.0, "oracle_px": 100.0}}, ""))
            patch(poller, "pipeline",
                  lambda stmts: (_ for _ in ()).throw(
                      RuntimeError("simulated Turso failure")))
            state = {"liquidation_alert_tickers": {"TSLAx": "critical"}}
            frag = poller.run_hourly_liquidation(now, state)
            check("S6 write failure clears the stale alert set",
                  state.get("liquidation_alert_tickers") == {},
                  f"state={state} frag={frag!r}")
            # (d) success with a real warning/critical -> state SET.
            patch(poller, "pipeline", lambda stmts: [{} for _ in stmts])
            patch(poller, "fetch_xyz_ctxs", lambda: (
                {"TSLAx": {"mark_px": 103.0, "oracle_px": 100.0}}, ""))
            state = {}
            frag = poller.run_hourly_liquidation(now, state)
            check("S6 success still sets the alert set (critical at "
                  "3% divergence)",
                  state.get("liquidation_alert_tickers") == {"TSLAx": "critical"},
                  f"state={state} frag={frag!r}")
            # (e) dry-run never touches state.
            patch(poller, "fetch_xyz_ctxs", lambda: ({}, "boom"))
            state = {"liquidation_alert_tickers": {"TSLAx": "critical"}}
            poller.run_hourly_liquidation(now, state, dry_run=True)
            check("S6 dry-run leaves state untouched",
                  state.get("liquidation_alert_tickers") == {"TSLAx": "critical"},
                  f"state={state}")
        finally:
            restore_all()

        # =================================================================
        # S7 — missed week reported; fill bounded to the last 8 weeks
        # =================================================================
        conn = make_db()
        try:
            captured = []
            patch(poller, "query", sqlite_query(conn))
            patch(poller, "pipeline", recording_pipeline(conn, captured))
            mon = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                frag = poller._monday_gap_fill_outcomes(mon, {})
            check("S7(a) a week with NO prediction row returns a MISSED "
                  "fragment naming the week_start",
                  "MISSED" in frag and "2026-11-14" in frag,
                  f"frag={frag!r}")
            check("S7(a) the missed week is logged as an explicit WARNING",
                  "WARNING" in buf.getvalue()
                  and "MISSED" in buf.getvalue(),
                  f"out={buf.getvalue()[:200]!r}")
            # (b) recent pending fills; 9-week-old pending does NOT.
            for gid, ticker, week, pred in (
                    (1, "TSLAx", "2026-11-14", 1.0),
                    (2, "NVDAx", "2026-09-12", 2.0)):
                conn.execute(
                    "INSERT INTO monday_gap (id, ticker_id, week_start,"
                    " gap_pred_pct, confidence, method_version, outcome)"
                    " VALUES (?, ?, ?, ?, 50.0, 'monday_gap_v1', 'pending')",
                    [gid, ticker, week, pred])
            for ticker, ts, dw in (
                    ("TSLAx", "2026-11-15T22:00:00Z", 100.0),
                    ("TSLAx", "2026-11-16T15:00:00Z", 102.0),
                    ("NVDAx", "2026-09-13T22:00:00Z", 100.0),
                    ("NVDAx", "2026-09-14T15:00:00Z", 105.0)):
                r = dev_row(ticker, ts, dw)
                conn.execute(
                    "INSERT INTO deviations (ticker_id, ts,"
                    " depth_weighted_price, dev_vs_median_pct,"
                    " qualifying_depth_usd, pools_used)"
                    " VALUES (?,?,?,?,?,?)",
                    [r["ticker_id"], r["ts"], r["depth_weighted_price"],
                     r["dev_vs_median_pct"], r["qualifying_depth_usd"],
                     r["pools_used"]])
            conn.commit()
            captured.clear()
            frag = poller._monday_gap_fill_outcomes(mon, {})
            updates = [a for s, a in captured if s.startswith("UPDATE monday_gap")]
            check("S7(b) the recent pending row IS filled (actual 2.0%, "
                  "accurate vs pred 1.0)",
                  len(updates) == 1 and updates[0][3] == 1
                  and updates[0][0] == 2.0 and updates[0][1] == "accurate",
                  f"updates={updates}")
            check("S7(b) the 9-week-old pending row is NOT filled "
                  "(outside the 8-week bound, even though fillable)",
                  all(a[3] != 2 for a in updates),
                  f"updates={updates}")
            check("S7(b) no MISSED fragment when the week HAS rows",
                  frag == "", f"frag={frag!r}")
            check("S7(b) the 8-week bound is a named constant with a "
                  "reason in its comment",
                  poller.MONDAY_GAP_PENDING_MAX_AGE_WEEKS == 8
                  and "8 weeks" in poller_src)
        finally:
            conn.close()
            restore_all()

        # =================================================================
        # S8 — 'closed' redemption scales by hours to next open
        # =================================================================
        comp = poller._exit_redemption_component
        check("S8 closed, open in 2h -> 20 (Sunday-night close)",
              comp("closed", 2.0) == 20.0)
        check("S8 closed, open in 24h -> 20 (boundary)",
              comp("closed", 24.0) == 20.0)
        check("S8 closed, open in 55h -> 10 (Friday-night close)",
              comp("closed", 55.0) == 10.0)
        check("S8 closed, open in 72h -> 10 (boundary)",
              comp("closed", 72.0) == 10.0)
        check("S8 closed, open in 100h -> 0 (long-holiday close)",
              comp("closed", 100.0) == 0.0)
        check("S8 closed with unknown hours is NOT counted (None)",
              comp("closed", None) is None)
        check("S8 open branch is unchanged (<=24h -> 20)",
              comp("open", 10.0) == 20.0 and comp("open", 100.0) == 0.0)
        sc = poller.exit_score_v2(0.0, 1000000.0, 1000000.0,
                                  "closed", 2.0, None, None)
        check("S8 exit_score_v2: Sunday-night closed contributes 20",
              sc["components"]["redemption"] == 20.0,
              f"comps={sc['components']}")
        sc2 = poller.exit_score_v2(0.0, 1000000.0, 1000000.0,
                                   "closed", 100.0, None, None)
        check("S8 exit_score_v2: long-holiday closed contributes 0",
              sc2["components"]["redemption"] == 0.0,
              f"comps={sc2['components']}")

        # =================================================================
        # S14 — ONE batched OI 24h-ago query per cycle
        # =================================================================
        conn = make_db()
        try:
            for ticker, ts, oi in (
                    ("TSLAx", "2026-11-12T11:00:00Z", 1000.0),
                    ("TSLAx", "2026-11-12T11:55:00Z", 1100.0),
                    ("TSLAx", "2026-11-12T12:00:00Z", 1200.0),
                    ("TSLAx", "2026-11-12T13:00:00Z", 1300.0),
                    ("NVDAx", "2026-11-11T12:00:00Z", 500.0),
                    ("NVDAx", "2026-11-12T10:00:00Z", 600.0),
                    ("AAPLx", "2026-11-12T13:00:00Z", 700.0)):
                conn.execute(
                    "INSERT INTO perp_snapshots (ticker_id, ts, oi)"
                    " VALUES (?, ?, ?)", [ticker, ts, oi])
            conn.commit()
            calls = []
            base_q = sqlite_query(conn)

            def counting_q(sql, args=None):
                calls.append(sql)
                return base_q(sql, args)

            patch(poller, "query", counting_q)
            got = poller._oi_24h_ago_batch(
                ["TSLAx", "NVDAx", "AAPLx"], now)
            check("S14 one query serves three tickers (not three)",
                  len(calls) == 1, f"queries={len(calls)}")
            check("S14 latest row at/before the 24h cutoff wins per "
                  "ticker (TSLAx 1200 @12:00, NVDAx 600)",
                  got == {"TSLAx": 1200.0, "NVDAx": 600.0}, f"got={got}")
            check("S14 a ticker with no row at/before the cutoff is "
                  "absent (AAPLx: no OI component, not zeroed)",
                  "AAPLx" not in got)
            calls.clear()
            check("S14 empty ticker list issues no query",
                  poller._oi_24h_ago_batch([], now) == {}
                  and calls == [])
            check("S14 single-ticker wrapper still works (forward_paper)",
                  poller._oi_24h_ago("TSLAx", now) == 1200.0)
        finally:
            conn.close()
            restore_all()

        # =================================================================
        # N3 — 7-day median age bound
        # =================================================================
        try:
            def raising_q(sql, args=None):
                raise AssertionError(
                    "median refresh must not query on the same-day path")

            # (1) same-day cache: 8-day-old entry pruned, fresh kept,
            #     no DB read at all.
            state1 = {
                "median_depth_7d": {"OLD": 100.0, "FRESH": 200.0},
                "median_depth_7d_date": "2026-11-13",
                "median_depth_7d_ts": {
                    "OLD": "2026-11-05T12:00:00Z",
                    "FRESH": "2026-11-12T12:00:00Z"},
            }
            patch(poller, "query", raising_q)
            got1 = poller.refresh_median_depth_7d(state1, now, ["FRESH"])
            check("N3 an 8-day-old median is dropped from the same-day "
                  "cache (fresh entry kept, no recompute read)",
                  got1 == {"FRESH": 200.0}, f"got={got1}")
            check("N3 the prune is persisted to state",
                  state1.get("median_depth_7d") == {"FRESH": 200.0},
                  f"state={state1.get('median_depth_7d')}")
            restore_all()
            # (2) rebuild: a fresh ABSENT ticker's median is kept.
            patch(poller, "query", lambda sql, args=None: (
                [{"qualifying_depth_usd": v} for v in (10.0, 20.0, 30.0)]
                if args and args[0] == "A" else []))
            state2 = {
                "median_depth_7d": {"ABSENT": 500.0},
                "median_depth_7d_date": "2026-11-12",
                "median_depth_7d_ts": {"ABSENT": "2026-11-11T12:00:00Z"},
            }
            got2 = poller.refresh_median_depth_7d(state2, now, ["A"])
            check("N3 rebuild keeps a fresh median for a ticker absent "
                  "this cycle (ABSENT, 2 days old)",
                  got2.get("ABSENT") == 500.0 and got2.get("A") == 20.0,
                  f"got={got2}")
            check("N3 rebuild stamps the new median with today",
                  state2.get("median_depth_7d_date") == "2026-11-13"
                  and state2.get("median_depth_7d_ts", {}).get("A")
                  == "2026-11-13T12:00:00Z",
                  f"state={state2}")
            # (3) legacy state (no per-ticker stamps, date 8 days old):
            #     the undated median is stale and dropped.
            patch(poller, "query", lambda sql, args=None: [])
            state3 = {"median_depth_7d": {"X": 1.0},
                      "median_depth_7d_date": "2026-11-05"}
            got3 = poller.refresh_median_depth_7d(state3, now, ["A"])
            check("N3 legacy state: a median dated 8 days ago is stale "
                  "and dropped (return is {}, not the old value)",
                  got3 == {}, f"got={got3}")
            # (4) legacy state, date today: age falls back to the date.
            state4 = {"median_depth_7d": {"X": 1.0},
                      "median_depth_7d_date": "2026-11-13"}
            got4 = poller.refresh_median_depth_7d(state4, now, ["X"])
            check("N3 legacy state dated today is still fresh (date "
                  "fallback, no stamps needed)",
                  got4 == {"X": 1.0}, f"got={got4}")
            # (5) a stamp in the FUTURE is stale, never fresh (GG-15
            # direction): it is dropped like an over-age median.
            state5 = {
                "median_depth_7d": {"FUT": 9.0, "OK": 8.0},
                "median_depth_7d_date": "2026-11-13",
                "median_depth_7d_ts": {
                    "FUT": "2026-11-15T12:00:00Z",
                    "OK": "2026-11-12T12:00:00Z"},
            }
            got5 = poller.refresh_median_depth_7d(state5, now, ["OK"])
            check("N3 a future-dated median stamp is dropped (stale, "
                  "never fresh)",
                  got5 == {"OK": 8.0}, f"got={got5}")
            check("N3 the bound is a named 7-day constant",
                  poller.MEDIAN_DEPTH_MAX_AGE_DAYS == 7)
        finally:
            restore_all()

        # =================================================================
        # M10 — startup guard: complete schema passes, incomplete fails
        # =================================================================
        conn = make_db()
        try:
            patch(poller, "query", sqlite_query(conn))
            check("M10 guard PASSES on a complete schema (incl. the two "
                  "new columns)",
                  poller.check_startup_schema() == [],
                  f"missing={poller.check_startup_schema()}")
        finally:
            conn.close()
            restore_all()
        # Rebuild a PRE-migration DB: schema.sql now declares the new
        # columns/indexes too (fresh-DB record of the same migration),
        # so drop them back out to simulate "migration not applied".
        tmp = tempfile.mkdtemp(prefix="radar_fix_premig_")
        pre = sqlite3.connect(os.path.join(tmp, "radar.db"))
        pre.row_factory = sqlite3.Row
        pre.executescript(read("schema.sql"))
        pre.executescript(
            "ALTER TABLE deviations DROP COLUMN exit_score_components;"
            "ALTER TABLE perp_snapshots DROP COLUMN perp_px_source;"
            "DROP INDEX IF EXISTS idx_deviations_ts;"
            "DROP INDEX IF EXISTS idx_poller_health_cycle_ts;")
        pre.commit()
        try:
            patch(poller, "query", sqlite_query(pre))
            missing = poller.check_startup_schema()
            check("M10 guard FAILS naming both new columns on a "
                  "pre-migration schema",
                  "column deviations.exit_score_components" in missing
                  and "column perp_snapshots.perp_px_source" in missing,
                  f"missing={missing}")
            check("M10 guard FAILS naming both new indexes (M7/M8) on "
                  "a pre-migration schema",
                  "index idx_deviations_ts" in missing
                  and "index idx_poller_health_cycle_ts" in missing,
                  f"missing={missing}")
            check("M10 guard does not false-positive the old columns",
                  "column deviations.exit_score" not in missing
                  and "column deviations.exit_score_version" not in missing,
                  f"missing={missing}")
            old_argv = sys.argv
            sys.argv = ["poller.py"]
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), \
                        contextlib.redirect_stderr(buf):
                    rc = poller.main()
                check("M10 main() exits 2 (fail fast) on an incomplete "
                      "schema, before any cycle",
                      rc == 2, f"rc={rc}")
                check("M10 the failure names the migration to apply",
                      "2026-11-13-radar-fix.sql" in buf.getvalue(),
                      f"out={buf.getvalue()[:200]!r}")
            finally:
                sys.argv = old_argv
        finally:
            pre.close()
            restore_all()
        # A missing table is also caught (complete schema, then drop
        # one table — make_db handles the already-declared columns).
        no_tbl = make_db()
        no_tbl.execute("DROP TABLE liquidation_watch;")
        no_tbl.commit()
        try:
            patch(poller, "query", sqlite_query(no_tbl))
            missing = poller.check_startup_schema()
            check("M10 guard FAILS naming a missing table",
                  "table liquidation_watch" in missing,
                  f"missing={missing}")
        finally:
            no_tbl.close()
            restore_all()
        # main() proceeds past the guard on a complete schema.
        conn = make_db()
        try:
            patch(poller, "query", sqlite_query(conn))
            patch(poller, "in_tight_window", lambda dt: False)
            patch(poller, "_maybe_run_perp", lambda dt: "")
            patch(poller, "run_cycle", lambda *a, **k: True)
            tmp_lock = os.path.join(tempfile.mkdtemp(prefix="radar_fix_lock_"),
                                   "poller.lock")
            patch(poller, "LOCK_PATH", tmp_lock)
            old_argv = sys.argv
            sys.argv = ["poller.py"]
            try:
                rc = poller.main()
            finally:
                sys.argv = old_argv
            check("M10 main() proceeds (exit 0) on a complete schema",
                  rc == 0, f"rc={rc}")
        finally:
            conn.close()
            restore_all()
    finally:
        restore_all()

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("RADAR FIX POLLER TEST: PASS" if not FAILURES
             else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
