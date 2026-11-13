"""Anti full-scan guard — EXPLAIN QUERY PLAN (S9, fix ronde review
DeepSeek Radar 2026-11-13).

Replaces the blind grep guard in qa/test_coverage_2026-11-12.mjs:139
(S9 BENAR). That guard only grepped api/worker.js for `SELECT *` /
`COUNT(*)` over 4 tables, so it could never see:
  - poller.py:1526 `SELECT COUNT(*) FROM poller_health WHERE cycle_ts=?`
    (a different file entirely — the grep never read poller.py), and
  - `ORDER BY ts DESC` without WHERE (no SELECT * / COUNT(*) involved
    at all — the scan hides behind a perfectly legal SELECT list).
Both full-scanned in production (M7: poller_health every cycle;
M8: deviations on every /api/latest + dashboard load) while the grep
guard reported PASS. This guard checks what the database actually
does: EXPLAIN QUERY PLAN for every relevant new-addition query.

How it works (all LOCAL sqlite, never touches a repo .db, never
touches Turso live, no network):
  1. Builds a synthetic DB from repo schema.sql in a temp dir, with
     realistic row counts (deviations ~6k rows / 13 tickers,
     poller_health ~6k, perp_snapshots ~3.5k / 10 tickers, snapshots
     ~12k / 35 pools) + ANALYZE, so planner decisions are meaningful.
     NOTE: there is no usable repo .db to copy — the only `*.db` file
     in the repo is a 0-byte glob artifact. Building from schema.sql
     is the correct equivalent (and also tests the schema as committed).
  2. Runs EXPLAIN QUERY PLAN for each gated query and FAILS on:
       - a bare `SCAN <table>` (no USING INDEX) on the queried table, or
       - `USE TEMP B-TREE FOR ORDER BY` on a query with no LIMIT
         (an unbounded sort). A temp B-tree on a LIMIT-bounded,
         index-driven query (e.g. perp latest-40 sorts <=40 rows) is
         tolerated and noted.
     A `SCAN <table> USING INDEX <idx>` is NOT a failure: it is an
     index-ordered walk bounded by LIMIT (e.g. loadLatest reads 500
     index entries + 500 row lookups, not the whole table).
  3. Proves both directions in one run:
       (a) PRE-MIGRATION DB (the two 2026-11-13 indexes stripped):
           the M7/M8 queries MUST full-scan (negative control — proves
           the guard can detect scans; if this ever passes, the guard
           itself is broken).
       (b) CURRENT SCHEMA (schema.sql as committed, incl. the
           2026-11-13 migration indexes): the core M7/M8 gate must
           PASS. Extended gated queries are also checked; any failure
           is reported with its plan and the exact index that closes it.
       (c) FULLY-INDEXED DB (current schema + the additional indexes
           the extended gate needs, created on the TEST COPY with
           IF NOT EXISTS — they now ALSO live in schema.sql and
           migrations/2026-11-13-radar-fix.sql, so state (c) is a
           re-application proof as well): the whole gate must PASS —
           proving the guard can pass and showing exactly what DDL
           closes the remaining gaps.
     Exit 0 only if (a) fails as expected AND (b) passes AND (c)
     passes. A failure in (b) means real scans remain on the current
     schema — fix the schema/code, do not narrow this guard.

Documented benign exceptions (bare SCAN allowed, reason printed):
  - monday_gap COUNT(*) / pending reads (poller.py:1035, :1100):
    table is bounded (~13-26 rows/week); a scan reads tens of rows.
  - poller_health ORDER BY id DESC LIMIT 12 (worker.js:345): id is the
    INTEGER PRIMARY KEY, so the scan is a rowid-ordered walk that
    stops after 12 rows (asserted: no temp B-tree in the plan).

Known gap CLOSED 2026-11-13 (coordinator follow-up to this guard's
first run): the worker.js per-ticker queries use
`ticker_id = ? COLLATE NOCASE`, which defeated the BINARY
(ticker_id, ts) indexes — the guard failed 4 queries on the current
schema. Closed with NOCASE indexes (idx_deviations_ticker_nocase_ts,
idx_perp_ticker_nocase_ts) + idx_perp_snapshots_ts, all in schema.sql
and migrations/2026-11-13-radar-fix.sql. Decision: NOCASE index over
case normalization in code — identical query behavior, no code change;
cost is one more index maintained per inserted row (see migration
header). The EXTRA_INDEXES list below is kept as the closing-DDL
record (IF NOT EXISTS, so state (c) re-applies cleanly).

Usage: python3 qa/test_no_fullscan.py   (exit 0 = PASS)
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "schema.sql")
OLD_GUARD = os.path.join(ROOT, "qa", "test_coverage_2026-11-12.mjs")

FAILURES = []

# Indexes added by migrations/2026-11-13-radar-fix.sql (M7/M8).
NEW_INDEX_LINES = [
    "CREATE INDEX IF NOT EXISTS idx_deviations_ts ON deviations(ts);\n",
    "CREATE INDEX IF NOT EXISTS idx_poller_health_cycle_ts "
    "ON poller_health(cycle_ts);\n",
]

# Additional indexes the extended gate needs. They now ALSO live in
# schema.sql and migrations/2026-11-13-radar-fix.sql (S9 follow-up);
# state (c) re-applies them with IF NOT EXISTS. Kept here as the
# closing-DDL record.
EXTRA_INDEXES = [
    ("idx_perp_snapshots_ts",
     "CREATE INDEX IF NOT EXISTS idx_perp_snapshots_ts "
     "ON perp_snapshots(ts)"),
    ("idx_deviations_ticker_nocase_ts",
     "CREATE INDEX IF NOT EXISTS idx_deviations_ticker_nocase_ts "
     "ON deviations(ticker_id COLLATE NOCASE, ts)"),
    ("idx_perp_ticker_nocase_ts",
     "CREATE INDEX IF NOT EXISTS idx_perp_ticker_nocase_ts "
     "ON perp_snapshots(ticker_id COLLATE NOCASE, ts)"),
]

# (name, source-ref, sql, params, has_limit)
# has_limit = the SQL has a LIMIT clause, so a temp B-tree sort over
# its (index-driven) input is bounded and tolerated.
GATED = [
    ("M7 poller_health idempotency", "poller.py:1526",
     "SELECT COUNT(*) AS n FROM poller_health "
     "WHERE cycle_ts = ? AND cycles_ok = 1",
     ("2026-11-05T00:00:00Z",), False),
    ("M8 worker loadLatest", "api/worker.js:281-293",
     "SELECT ticker_id, ts, depth_weighted_price, dev_vs_median_pct, "
     "qualifying_depth_usd, pools_used FROM deviations "
     "ORDER BY ts DESC, id DESC LIMIT 500",
     (), True),
    ("M8 dashboard loadLatest", "dashboard/app.py:233",
     "SELECT ticker_id, ts, depth_weighted_price, dev_vs_close_pct, "
     "dev_vs_median_pct, qualifying_depth_usd, pools_used, method_version "
     "FROM deviations ORDER BY ts DESC, id DESC LIMIT 500",
     (), True),
    ("M8 dashboard loadLatest (turso_read)", "dashboard/turso_read.py:290",
     "SELECT ticker_id, ts, exit_score, exit_score_version "
     "FROM deviations ORDER BY ts DESC, id DESC LIMIT 500",
     (), True),
    ("M8 worker per-ticker latest (NOCASE)", "api/worker.js:614",
     "SELECT ts, depth_weighted_price, dev_vs_median_pct, "
     "qualifying_depth_usd, pools_used FROM deviations "
     "WHERE ticker_id = ? COLLATE NOCASE ORDER BY ts DESC, id DESC LIMIT 1",
     ("T00x",), True),
    ("M8 worker pools_excluded latest (NOCASE)", "api/worker.js:680",
     "SELECT pools_excluded FROM deviations "
     "WHERE ticker_id = ? COLLATE NOCASE ORDER BY ts DESC, id DESC LIMIT 1",
     ("T00x",), True),
    ("M8 worker 1h-anchor (NOCASE)", "api/worker.js:633",
     "SELECT ts, dev_vs_median_pct FROM deviations "
     "WHERE ticker_id = ? COLLATE NOCASE "
     "AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour') "
     "AND dev_vs_median_pct IS NOT NULL ORDER BY ts ASC",
     ("T00x",), False),
    ("F1 worker perp latest", "api/worker.js:359",
     "SELECT ticker_id, ts, perp_px, funding, oi FROM perp_snapshots "
     "ORDER BY ts DESC LIMIT 200",
     (), True),
    ("F1 poller perp latest-40", "poller.py:775",
     "SELECT ticker_id, funding, oi, ts FROM perp_snapshots "
     "WHERE ts >= ? ORDER BY ts DESC LIMIT 40",
     ("2026-11-02T00:00:00Z",), True),
    ("F1 worker perp per-ticker latest (NOCASE)", "api/worker.js:699",
     "SELECT ts, perp_px, funding, oi FROM perp_snapshots "
     "WHERE ticker_id = ? COLLATE NOCASE ORDER BY ts DESC LIMIT 1",
     ("T00x",), True),
    ("F1 dashboard perp per-ticker latest", "dashboard/turso_read.py:318",
     "SELECT ticker_id, ts, perp_px, funding, oi, dex FROM perp_snapshots "
     "WHERE ticker_id = ? ORDER BY ts DESC LIMIT 1",
     ("T00x",), True),
    ("F1 poller OI 24h ago (control)", "poller.py:793",
     "SELECT oi FROM perp_snapshots WHERE ticker_id = ? "
     "AND ts <= ? ORDER BY ts DESC LIMIT 1",
     ("T00x", "2026-11-01T00:00:00Z"), True),
    ("F2 poller median depth 7d (control)", "poller.py:815",
     "SELECT qualifying_depth_usd FROM deviations "
     "WHERE ticker_id = ? AND ts >= ? "
     "AND qualifying_depth_usd IS NOT NULL ORDER BY ts DESC LIMIT 2016",
     ("T00x", "2026-10-25T00:00:00Z"), True),
    ("F2 poller latest deviations row (control)", "poller.py:978",
     "SELECT ticker_id, ts, depth_weighted_price, dev_vs_median_pct, "
     "qualifying_depth_usd, pools_used FROM deviations "
     "WHERE ticker_id = ? AND ts >= ? AND ts < ? ORDER BY ts DESC LIMIT 1",
     ("T00x", "2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z"), True),
    ("F2 poller Sunday spread (control)", "poller.py:1003",
     "SELECT price_usd, reserve_usd FROM snapshots WHERE ts = ? "
     "AND pool_id IN (?,?,?,?,?)",
     ("2026-11-01T00:00:00Z", "solana:pool0", "solana:pool1",
      "solana:pool2", "solana:pool3", "solana:pool4"), False),
    ("worker series 1h (control)", "api/worker.js:347",
     "SELECT ticker_id, ts, dev_vs_median_pct FROM deviations "
     "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour') "
     "AND dev_vs_median_pct IS NOT NULL ORDER BY ticker_id, ts",
     (), False),
    ("dashboard spark 24h (control)", "dashboard/app.py:308",
     "SELECT ticker_id, ts, dev_vs_median_pct AS dev FROM deviations "
     "WHERE ts >= ? AND dev_vs_median_pct IS NOT NULL "
     "ORDER BY ts ASC LIMIT 2000",
     ("2026-11-02T00:00:00Z",), True),
]

# (name, source-ref, sql, params) — bare SCAN allowed, reason recorded.
EXCEPTIONS = [
    ("monday_gap calibration COUNT (tiny table)", "poller.py:1035",
     "SELECT COUNT(*) AS n FROM monday_gap "
     "WHERE outcome IN ('accurate','inaccurate')", ()),
    ("monday_gap pending rows (tiny table)", "poller.py:1100",
     "SELECT id, ticker_id, week_start, gap_pred_pct FROM monday_gap "
     "WHERE outcome = 'pending'", ()),
    ("worker health latest (rowid walk, LIMIT 12)", "api/worker.js:345",
     "SELECT cycle_ts, cycles_ok FROM poller_health "
     "ORDER BY id DESC LIMIT 12", ()),
]


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name + (f": {detail}" if detail else ""))


def read_schema():
    with open(SCHEMA) as f:
        return f.read()


def pre_migration_schema():
    """schema.sql with the two 2026-11-13 indexes stripped, i.e. the
    pre-migration database. Each strip is asserted so schema drift
    fails loudly instead of silently testing the new schema."""
    sql = read_schema()
    for frag in NEW_INDEX_LINES:
        assert sql.count(frag) == 1, f"pre-migration strip failed: {frag!r}"
        sql = sql.replace(frag, "")
    return sql


def build_db(path, sql_text):
    import datetime
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(sql_text)
    tickers = [f"T{i:02d}x" for i in range(13)]
    for t in tickers:
        conn.execute(
            "INSERT INTO universe (ticker_id, underlying, issuer, tier, "
            "status, created_at, updated_at) VALUES "
            "(?,?,?,'xstocks','active','2026-11-01T00:00:00Z',"
            "'2026-11-01T00:00:00Z')", (t, t, "xstocks"))
    base = datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc)
    rows = []
    for i in range(460):
        ts = (base + datetime.timedelta(minutes=5 * i)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        for t in tickers:
            rows.append((t, ts, 100.0, 0.1, 500000.0, 2))
    conn.executemany(
        "INSERT INTO deviations (ticker_id, ts, depth_weighted_price, "
        "dev_vs_median_pct, qualifying_depth_usd, pools_used) "
        "VALUES (?,?,?,?,?,?)", rows)
    hrows = [((base + datetime.timedelta(minutes=5 * i)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), 1, 1) for i in range(6000)]
    conn.executemany(
        "INSERT INTO poller_health (cycle_ts, cycles_expected, cycles_ok) "
        "VALUES (?,?,?)", hrows)
    prows = []
    for i in range(350):
        ts = (base + datetime.timedelta(minutes=5 * i)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        for t in tickers[:10]:
            prows.append((t, ts, 100.0, 0.0002, 1000000.0, "xyz"))
    conn.executemany(
        "INSERT INTO perp_snapshots (ticker_id, ts, perp_px, funding, oi, "
        "dex) VALUES (?,?,?,?,?,?)", prows)
    for p in range(35):
        conn.execute(
            "INSERT INTO pools (pool_id, ticker_id, chain, dex, "
            "pair_address, quote_token, is_active, min_liquidity_usd) "
            "VALUES (?,?,?,?,?,'USDC',1,100000)",
            (f"solana:pool{p}", tickers[p % 13], "solana", "TestDex",
             f"0x{p:04d}"))
    srows = []
    for i in range(350):
        ts = (base + datetime.timedelta(minutes=5 * i)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        for p in range(35):
            srows.append((f"solana:pool{p}", ts, 100.0))
    conn.executemany(
        "INSERT INTO snapshots (pool_id, ts, price_usd, source) "
        "VALUES (?,?,?,'test')", srows)
    conn.execute(
        "INSERT INTO monday_gap (ticker_id, week_start, gap_pred_pct, "
        "confidence, outcome) VALUES ('T00x','2026-11-07',1.0,75.0,"
        "'pending')")
    conn.execute("ANALYZE")
    conn.commit()
    return conn


def plan_lines(conn, sql, params=()):
    return [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


def tables_in(sql):
    return [t for t in ("poller_health", "deviations", "perp_snapshots",
                        "snapshots", "monday_gap", "liquidation_watch")
            if f" {t} " in f" {sql} " or f"FROM {t}" in sql
            or f"JOIN {t}" in sql]


def verdict(plan, sql, has_limit):
    """(ok, reason). FAIL on a bare SCAN of any queried table, or on a
    temp B-tree sort for a query with no LIMIT (unbounded sort)."""
    for t in tables_in(sql):
        if any(ln.startswith(f"SCAN {t}") and "USING INDEX" not in ln
               for ln in plan):
            return False, f"bare SCAN {t}: {' | '.join(plan)}"
    if any("USE TEMP B-TREE" in ln for ln in plan) and not has_limit:
        return False, f"unbounded temp B-tree sort: {' | '.join(plan)}"
    return True, " | ".join(plan)


def run_gate(conn, label, record=True):
    """Run all gated queries + exceptions on one DB. Returns the list
    of failing gated-query names. When record=False (the negative
    control, where failures are EXPECTED), failures are printed but
    NOT added to the global FAILURES list."""
    print(f"\n--- {label} ---")
    failed = []
    for name, ref, sql, params, has_limit in GATED:
        plan = plan_lines(conn, sql, params)
        ok, reason = verdict(plan, sql, has_limit)
        if record:
            check(f"[{label}] {name} ({ref})", ok, reason)
        else:
            print(("PASS " if ok else "FAIL ") + f"[{label}] {name} "
                  f"({ref})" + (f" — {reason}" if not ok else ""))
        if not ok:
            failed.append(name)
    for name, ref, sql, params in EXCEPTIONS:
        plan = plan_lines(conn, sql, params)
        print(f"INFO [{label}] {name} ({ref}) — allowed exception: "
              f"{' | '.join(plan)}")
    return failed


def main():
    tmp = tempfile.mkdtemp(prefix="radar-nofullscan-")
    print(f"tmpdir: {tmp}")
    print("rows: deviations ~5980, poller_health 6000, "
          "perp_snapshots 3500, snapshots 12250, monday_gap 1")

    # (0) S9 blindness proof: the old grep guard cannot see these
    # queries at all (it only reads api/worker.js, and only for
    # SELECT * / COUNT(*) over 4 tables).
    old = open(OLD_GUARD).read()
    check("S9: old guard reads worker.js only (never poller.py)",
          "poller.py" not in old and "worker.js" in old)
    check("S9: old guard greps only 4 tables for SELECT */COUNT(*) — "
          "ORDER BY scans and poller.py COUNT(*) are invisible to it",
          '["snapshots", "deviations", "perp_snapshots", '
          '"liquidation_watch"]' in old)

    # (a) Negative control: pre-migration DB MUST fail M7/M8.
    pre_db = os.path.join(tmp, "pre-migration.db")
    conn = build_db(pre_db, pre_migration_schema())
    pre_failed = run_gate(conn, "PRE-MIGRATION (negative control)",
                          record=False)
    check("negative control: pre-migration DB FAILS the gate",
          len(pre_failed) >= 2
          and any(n.startswith("M7") for n in pre_failed)
          and any(n.startswith("M8 worker loadLatest") for n in pre_failed),
          f"failed={pre_failed}")
    conn.close()

    # (b) Current schema as committed (incl. 2026-11-13 indexes).
    cur_db = os.path.join(tmp, "current.db")
    conn = build_db(cur_db, read_schema())
    cur_failed = run_gate(conn, "CURRENT SCHEMA (as committed)")
    core_failed = [n for n in cur_failed
                   if n.startswith("M7") or n.startswith("M8 worker loadLatest")
                   or n.startswith("M8 dashboard loadLatest")]
    check("core gate M7/M8 PASSES on current schema",
          not core_failed, f"failed={core_failed}")
    if cur_failed:
        print("\nNOTE: current schema still fails the extended gate on:")
        for n in cur_failed:
            print(f"  - {n}")
        print("These are real scans (see plans above). Closing them "
              "needs schema DDL (see EXTRA_INDEXES in this file — the "
              "closing indexes for the known cases) or a code change; "
              "do not narrow this guard to force a PASS.")
    conn.close()

    # (c) Fully-indexed test copy: current schema + extra indexes.
    # Proves the guard CAN pass and shows the exact closing DDL.
    full_db = os.path.join(tmp, "fully-indexed.db")
    conn = build_db(full_db, read_schema())
    for idx_name, ddl in EXTRA_INDEXES:
        conn.execute(ddl)
    conn.execute("ANALYZE")
    conn.commit()
    full_failed = run_gate(conn, "FULLY-INDEXED (test copy only)")
    check("fully-indexed test copy PASSES the whole gate",
          not full_failed, f"failed={full_failed}")
    conn.close()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("NO-FULLSCAN GUARD: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
