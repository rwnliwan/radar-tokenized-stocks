"""Radar fix ronde review DeepSeek 2026-11-13 — schema + migrasi + seed.

Tests M5/M7/M8/S1/S2/N4 (schema + migration) and M9/S13 (seed UPSERT),
all on LOCAL sqlite copies in a temp dir. Never touches a repo .db,
never touches Turso live, no network.

  (a) migrations/2026-11-13-radar-fix.sql applies 2x without error
      (via qa/apply_migration_2026-11-13.py; 2nd run = all SKIPPED).
  (b) After migration: exit_score_components + perp_px_source exist;
      both new indexes exist.
  (c) EXPLAIN QUERY PLAN uses the new indexes for the M7 idempotency
      COUNT(*) and the M8 ORDER BY ts DESC (no full-table scan, no
      temp B-tree sort); the pre-migration plan is shown as the
      negative control (full SCAN).
  (d) Seed UPSERT: build_statements run 2x on a seeded copy — no
      rows lost, no duplicates, created_at preserved; a ticker that
      drops out of the seed becomes status='inactive' (pools
      is_active=0, redemption row status='inactive' with observed_at
      untouched); no DELETE statement is ever emitted.
  (e) Fresh DB from schema.sql: monday_gap.outcome CHECK rejects
      values outside pending/accurate/inaccurate. Documented
      limitation, asserted here: the CHECK cannot be added to an
      already-migrated DB (SQLite ALTER cannot add CHECK), so a
      bogus outcome is still accepted there until a rebuild.

Usage: python3 qa/test_radar_fix_schema.py  (exit 0 = PASS)
"""
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import seed_multichain  # noqa: E402

SCHEMA = os.path.join(ROOT, "schema.sql")
MIGRATION_RUNNER = os.path.join(
    ROOT, "qa", "apply_migration_2026-11-13.py")

FAILURES = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name + (f": {detail}" if detail else ""))


def read_schema():
    with open(SCHEMA) as f:
        return f.read()


def old_schema_sql():
    """schema.sql with the 2026-11-13 additions stripped, i.e. the
    pre-migration database. Each strip is asserted so schema drift
    fails loudly instead of silently testing the new schema."""
    sql = read_schema()
    strips = [
        ("  exit_score_components INTEGER,\n", "exit_score_components"),
        ("  perp_px_source TEXT,\n", "perp_px_source"),
        ("CREATE INDEX IF NOT EXISTS idx_deviations_ts "
         "ON deviations(ts);\n", "idx_deviations_ts"),
        ("CREATE INDEX IF NOT EXISTS idx_poller_health_cycle_ts "
         "ON poller_health(cycle_ts);\n", "idx_poller_health_cycle_ts"),
        ("CREATE INDEX IF NOT EXISTS idx_perp_snapshots_ts "
         "ON perp_snapshots(ts);\n", "idx_perp_snapshots_ts"),
        ("CREATE INDEX IF NOT EXISTS idx_deviations_ticker_nocase_ts "
         "ON deviations(ticker_id COLLATE NOCASE, ts);\n",
         "idx_deviations_ticker_nocase_ts"),
        ("CREATE INDEX IF NOT EXISTS idx_perp_ticker_nocase_ts "
         "ON perp_snapshots(ticker_id COLLATE NOCASE, ts);\n",
         "idx_perp_ticker_nocase_ts"),
    ]
    for frag, label in strips:
        assert sql.count(frag) == 1, f"old-schema strip failed: {label}"
        sql = sql.replace(frag, "")
    frag = ("  outcome TEXT CHECK (outcome IN "
            "('pending', 'accurate', 'inaccurate')),\n")
    assert sql.count(frag) == 1, "old-schema strip failed: outcome CHECK"
    sql = sql.replace(frag, "  outcome TEXT,\n")
    return sql


def build_db(path, sql_text):
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(sql_text)
    conn.commit()
    return conn


def run_runner(db_path, extra=None):
    cmd = [sys.executable, MIGRATION_RUNNER, "--db", db_path]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True)


def plan_lines(conn, sql, params=()):
    return [r[3] for r in conn.execute(
        "EXPLAIN QUERY PLAN " + sql, params)]


def uses_index(plan, index_name):
    return any(f"USING INDEX {index_name}" in ln
               or f"USING COVERING INDEX {index_name}" in ln
               for ln in plan)


def has_bare_scan(plan, table):
    # A bare "SCAN <table>" with no USING INDEX = full-table scan.
    return any(ln.startswith(f"SCAN {table}")
               and "USING INDEX" not in ln for ln in plan)


def has_temp_btree(plan):
    return any("USE TEMP B-TREE" in ln for ln in plan)


def exec_stmts(conn, stmts):
    for sql, args in stmts:
        conn.execute(sql, args)
    conn.commit()


def synth_data(tickers):
    """Minimal verify_multichain_out.json-shaped data.

    tickers: {ticker_id: (issuer, underlying, [pool_suffixes])}.
    A pool_suffix makes pool_id f"{chain}:{pair}"; each pool has
    $200k liquidity on a named dex, quote != symbol."""
    chain = {"coinbase": "base", "bstocks": "bsc", "robinhood": "robinhood"}
    cands = []
    for tid, (issuer, underlying, pools) in tickers.items():
        cands.append({
            "ticker_id": tid, "symbol": tid, "issuer": issuer,
            "underlying": underlying, "tier": 1,
            "total_liquidity_usd": 200000.0 * max(len(pools), 1),
            "venues": 2, "named_venues": 2,
            "token_address": "0x" + "ab" * 20,
            "token_name": underlying,
            "pools": [{
                "liquidity_usd": 200000.0, "dex": "TestDex",
                "chain": chain[issuer], "pair_address": f"0xpair{s}",
                "quote": "USDC",
            } for s in pools],
        })
    return {"verified_at_utc": "2026-11-12T12:00:00Z",
            "candidates": cands}


def seed_history(conn):
    """Pre-existing rows a re-seed must NOT destroy."""
    conn.execute(
        "INSERT INTO universe (ticker_id, underlying, issuer, "
        "legal_type, tier, status, token_addresses, notes, created_at, "
        "updated_at) VALUES ('TSLAc','Tesla, Inc.','coinbase','wrapper',"
        "1,'active','{}','seeded 12 Nov','2026-11-12T00:00:00Z',"
        "'2026-11-12T00:00:00Z')")
    conn.execute(
        "INSERT INTO universe (ticker_id, underlying, issuer, "
        "legal_type, tier, status, token_addresses, notes, created_at, "
        "updated_at) VALUES ('TSLAB','Tesla, Inc.','bstocks','wrapper',"
        "1,'active','{}','seeded 12 Nov','2026-11-12T00:00:00Z',"
        "'2026-11-12T00:00:00Z')")
    conn.execute(
        "INSERT INTO pools (pool_id, ticker_id, chain, dex, "
        "pair_address, quote_token, is_active, min_liquidity_usd) "
        "VALUES ('base:0xpairA','TSLAc','base','TestDex','0xpairA',"
        "'USDC',1,100000)")
    conn.execute(
        "INSERT INTO pools (pool_id, ticker_id, chain, dex, "
        "pair_address, quote_token, is_active, min_liquidity_usd) "
        "VALUES ('bsc:0xpairB','TSLAB','bsc','TestDex','0xpairB',"
        "'USDC',1,100000)")
    conn.execute(
        "INSERT INTO deviations (ticker_id, ts, depth_weighted_price) "
        "VALUES ('TSLAc','2026-11-12T10:00:00Z',250.0)")
    conn.execute(
        "INSERT INTO deviations (ticker_id, ts, depth_weighted_price) "
        "VALUES ('TSLAB','2026-11-12T10:00:00Z',250.0)")
    conn.execute(
        "INSERT INTO snapshots (pool_id, ts, price_usd, source) "
        "VALUES ('base:0xpairA','2026-11-12T10:00:00Z',250.0,'test')")
    conn.execute(
        "INSERT INTO redemption_windows (issuer, asset, status, "
        "window_note, window_note_en, observed_at, source, next_open_at) "
        "VALUES ('coinbase','ALL','unknown','old note',NULL,"
        "'2026-11-12T00:00:00Z','old','')")
    conn.execute(
        "INSERT INTO redemption_windows (issuer, asset, status, "
        "window_note, window_note_en, observed_at, source, next_open_at) "
        "VALUES ('bstocks','ALL','unknown','old note',NULL,"
        "'2026-11-12T00:00:00Z','old','')")
    conn.commit()


def main():
    tmp = tempfile.mkdtemp(prefix="radar-fix-qa-")
    print(f"tmpdir: {tmp}")

    # ---- (a/b/c) migration on a pre-migration DB ----
    old_db = os.path.join(tmp, "old.db")
    conn = build_db(old_db, old_schema_sql())
    cols = {r[1] for r in conn.execute("PRAGMA table_info(deviations)")}
    check("pre-migration DB lacks exit_score_components",
          "exit_score_components" not in cols)
    # (c) negative control: pre-migration plans full-scan.
    conn.execute(
        "INSERT INTO poller_health (cycle_ts, cycles_expected, "
        "cycles_ok) VALUES ('2026-11-13T00:00:00Z', 10, 10)")
    conn.execute(
        "INSERT INTO universe (ticker_id, underlying, issuer, tier, "
        "status, created_at, updated_at) VALUES ('TSLAx','Tesla, Inc.',"
        "'xstocks',1,'active','2026-11-12T00:00:00Z','2026-11-12T00:00:00Z')")
    conn.execute(
        "INSERT INTO deviations (ticker_id, ts) VALUES "
        "('TSLAx','2026-11-13T00:00:00Z')")
    conn.commit()
    plan = plan_lines(conn, "SELECT COUNT(*) FROM poller_health "
                            "WHERE cycle_ts = ?",
                      ("2026-11-13T00:00:00Z",))
    check("pre-migration M7 query full-scans (negative control)",
          has_bare_scan(plan, "poller_health"), " | ".join(plan))
    plan = plan_lines(conn, "SELECT * FROM deviations "
                            "ORDER BY ts DESC LIMIT 1")
    check("pre-migration M8 query full-scans (negative control)",
          has_bare_scan(plan, "deviations"), " | ".join(plan))
    conn.close()

    r = run_runner(old_db, ["--check"])
    check("runner --check exits 0", r.returncode == 0, r.stderr)
    check("runner --check reports 7 to run",
          "7 run, 0 skipped" in r.stdout, r.stdout.strip())
    conn = sqlite3.connect(old_db)
    cols = {x[1] for x in conn.execute("PRAGMA table_info(deviations)")}
    check("runner --check writes nothing",
          "exit_score_components" not in cols)
    conn.close()

    r1 = run_runner(old_db)
    check("migration 1st run exits 0", r1.returncode == 0, r1.stderr)
    check("migration 1st run applies 7 statements",
          "7 run, 0 skipped" in r1.stdout, r1.stdout.strip())
    r2 = run_runner(old_db)
    check("migration 2nd run exits 0 (re-runnable, S1)",
          r2.returncode == 0, r2.stderr)
    check("migration 2nd run skips all 7 (no duplicate-column error)",
          "0 run, 7 skipped" in r2.stdout and
          "duplicate column" not in r2.stderr.lower(),
          r2.stdout.strip() + r2.stderr)

    conn = sqlite3.connect(old_db)
    cols = {x[1] for x in conn.execute("PRAGMA table_info(deviations)")}
    check("(b) exit_score_components exists after migration",
          "exit_score_components" in cols)
    pcols = {x[1] for x in
             conn.execute("PRAGMA table_info(perp_snapshots)")}
    check("(b) perp_px_source exists after migration",
          "perp_px_source" in pcols)
    idx = {x[0] for x in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    check("(b) idx_poller_health_cycle_ts exists",
          "idx_poller_health_cycle_ts" in idx)
    check("(b) idx_deviations_ts exists", "idx_deviations_ts" in idx)
    check("(b) idx_perp_snapshots_ts exists (S9 follow-up)",
          "idx_perp_snapshots_ts" in idx)
    check("(b) idx_deviations_ticker_nocase_ts exists (S9 follow-up)",
          "idx_deviations_ticker_nocase_ts" in idx)
    check("(b) idx_perp_ticker_nocase_ts exists (S9 follow-up)",
          "idx_perp_ticker_nocase_ts" in idx)
    # (c) post-migration plans use the indexes.
    plan = plan_lines(conn, "SELECT COUNT(*) FROM poller_health "
                            "WHERE cycle_ts = ?",
                      ("2026-11-13T00:00:00Z",))
    check("(c) M7 COUNT(*) uses idx_poller_health_cycle_ts",
          uses_index(plan, "idx_poller_health_cycle_ts"),
          " | ".join(plan))
    check("(c) M7 COUNT(*) has no bare table scan",
          not has_bare_scan(plan, "poller_health"), " | ".join(plan))
    plan = plan_lines(conn, "SELECT * FROM deviations "
                            "ORDER BY ts DESC LIMIT 1")
    check("(c) M8 ORDER BY ts DESC uses idx_deviations_ts",
          uses_index(plan, "idx_deviations_ts"), " | ".join(plan))
    check("(c) M8 ORDER BY ts DESC has no bare table scan",
          not has_bare_scan(plan, "deviations"), " | ".join(plan))
    check("(c) M8 ORDER BY ts DESC needs no temp B-tree sort",
          not has_temp_btree(plan), " | ".join(plan))
    plan = plan_lines(conn, "SELECT * FROM perp_snapshots "
                            "ORDER BY ts DESC LIMIT 200")
    check("(c) S9 perp latest uses idx_perp_snapshots_ts",
          uses_index(plan, "idx_perp_snapshots_ts"), " | ".join(plan))
    check("(c) S9 perp latest has no bare table scan",
          not has_bare_scan(plan, "perp_snapshots"), " | ".join(plan))
    plan = plan_lines(conn, "SELECT * FROM deviations WHERE "
                            "ticker_id = ? COLLATE NOCASE ORDER BY ts DESC "
                            "LIMIT 1", ("TSLAx",))
    check("(c) S9 NOCASE per-ticker uses idx_deviations_ticker_nocase_ts",
          uses_index(plan, "idx_deviations_ticker_nocase_ts"),
          " | ".join(plan))
    check("(c) S9 NOCASE per-ticker has no bare table scan",
          not has_bare_scan(plan, "deviations"), " | ".join(plan))
    plan = plan_lines(conn, "SELECT * FROM perp_snapshots WHERE "
                            "ticker_id = ? COLLATE NOCASE ORDER BY ts DESC "
                            "LIMIT 1", ("TSLAx",))
    check("(c) S9 NOCASE perp per-ticker uses idx_perp_ticker_nocase_ts",
          uses_index(plan, "idx_perp_ticker_nocase_ts"),
          " | ".join(plan))
    # (e-limitation) migrated old DB has no CHECK — bogus accepted.
    conn.execute(
        "INSERT INTO monday_gap (ticker_id, week_start, gap_pred_pct, "
        "confidence, outcome) VALUES ('TSLAx','2026-11-14',1.0,50,"
        "'bogus')")
    conn.commit()
    check("(e) migrated old DB still accepts bogus outcome "
          "(CHECK needs rebuild — documented limitation)",
          conn.execute("SELECT COUNT(*) FROM monday_gap "
                       "WHERE outcome='bogus'").fetchone()[0] == 1)
    conn.close()

    # ---- (e) CHECK on a fresh DB from new schema.sql ----
    fresh_db = os.path.join(tmp, "fresh.db")
    conn = build_db(fresh_db, read_schema())
    conn.execute(
        "INSERT INTO monday_gap (ticker_id, week_start, gap_pred_pct, "
        "confidence, outcome) VALUES ('TSLAx','2026-11-14',1.0,50,"
        "'pending')")
    conn.execute(
        "INSERT INTO monday_gap (ticker_id, week_start, gap_pred_pct, "
        "confidence, outcome) VALUES ('TSLAx','2026-11-07',1.0,50,"
        "'accurate')")
    conn.execute(
        "INSERT INTO monday_gap (ticker_id, week_start, gap_pred_pct, "
        "confidence, outcome) VALUES ('TSLAx','2026-10-31',1.0,50,"
        "'inaccurate')")
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO monday_gap (ticker_id, week_start, "
            "gap_pred_pct, confidence, outcome) VALUES "
            "('TSLAx','2026-11-21',1.0,50,'bogus')")
        conn.commit()
        check("(e) CHECK rejects outcome='bogus' on fresh schema", False,
              "insert succeeded")
    except sqlite3.IntegrityError:
        conn.rollback()
        check("(e) CHECK rejects outcome='bogus' on fresh schema", True)
    n_ok = conn.execute("SELECT COUNT(*) FROM monday_gap "
                        "WHERE outcome IN ('pending','accurate',"
                        "'inaccurate')").fetchone()[0]
    check("(e) pending/accurate/inaccurate all accepted", n_ok == 3,
          f"n={n_ok}")
    conn.close()

    # ---- (d) seed UPSERT, 2 runs + dropout run ----
    seed_db = os.path.join(tmp, "seed.db")
    conn = build_db(seed_db, read_schema())
    seed_history(conn)

    v1 = synth_data({
        "TSLAc": ("coinbase", "Tesla, Inc.", ["A"]),
        "NVDAc": ("coinbase", "NVIDIA Corporation", ["C"]),
        "TSLAB": ("bstocks", "Tesla, Inc.", ["B"]),
    })
    stmts1, rep1 = seed_multichain.build_statements(v1)
    check("(d) seed emits no DELETE statement",
          not any(s.strip().upper().startswith("DELETE")
                  for s, _ in stmts1))
    exec_stmts(conn, stmts1)
    n_uni = conn.execute("SELECT COUNT(*) FROM universe").fetchone()[0]
    check("(d) run 1: 3 universe rows (2 pre-seeded + NVDAc)",
          n_uni == 3, f"n={n_uni}")
    n_pool = conn.execute("SELECT COUNT(*) FROM pools").fetchone()[0]
    check("(d) run 1: 3 pools (2 pre-seeded + NVDAc pool)",
          n_pool == 3, f"n={n_pool}")
    created = conn.execute("SELECT created_at FROM universe "
                           "WHERE ticker_id='TSLAc'").fetchone()[0]
    check("(d) run 1: TSLAc created_at preserved",
          created == "2026-11-12T00:00:00Z", created)
    hist = conn.execute("SELECT COUNT(*) FROM deviations "
                        "WHERE ticker_id='TSLAc'").fetchone()[0]
    check("(d) run 1: deviations history survives", hist == 1)
    hist = conn.execute("SELECT COUNT(*) FROM snapshots "
                        "WHERE pool_id='base:0xpairA'").fetchone()[0]
    check("(d) run 1: snapshots history survives", hist == 1)
    n_red = conn.execute("SELECT COUNT(*) FROM redemption_windows "
                         "WHERE issuer='coinbase'").fetchone()[0]
    check("(d) run 1: coinbase redemption row NOT duplicated",
          n_red == 1, f"n={n_red}")
    note_en = conn.execute("SELECT window_note_en FROM "
                           "redemption_windows WHERE issuer='coinbase'"
                           ).fetchone()[0]
    check("(d/S13) coinbase window_note_en present + honest",
          note_en and "authorised participants" in note_en
          and "UNVERIFIED" in note_en, str(note_en)[:80])
    note_en_b = conn.execute("SELECT window_note_en FROM "
                             "redemption_windows WHERE issuer='bstocks'"
                             ).fetchone()[0]
    check("(d/S13) bstocks window_note_en present + honest",
          note_en_b and "1:1, zero fee" in note_en_b
          and "UNVERIFIED" in note_en_b, str(note_en_b)[:80])

    exec_stmts(conn, seed_multichain.build_statements(v1)[0])
    n_uni2 = conn.execute("SELECT COUNT(*) FROM universe").fetchone()[0]
    n_pool2 = conn.execute("SELECT COUNT(*) FROM pools").fetchone()[0]
    n_red2 = conn.execute("SELECT COUNT(*) FROM redemption_windows "
                          "WHERE issuer='coinbase'").fetchone()[0]
    check("(d) run 2 (same seed): no duplicate universe rows",
          n_uni2 == 3, f"n={n_uni2}")
    check("(d) run 2 (same seed): no duplicate pools",
          n_pool2 == 3, f"n={n_pool2}")
    check("(d) run 2 (same seed): no duplicate redemption rows",
          n_red2 == 1, f"n={n_red2}")
    created2 = conn.execute("SELECT created_at FROM universe "
                            "WHERE ticker_id='TSLAc'").fetchone()[0]
    check("(d) run 2: TSLAc created_at still preserved",
          created2 == "2026-11-12T00:00:00Z", created2)
    # bstocks is still in the seed at this point, so its redemption
    # row was legitimately refreshed (observed_at=now) by run 1/2.
    # Record it: the dropout run must NOT bump it again.
    obs_bstocks_v1 = conn.execute("SELECT observed_at FROM "
                                  "redemption_windows WHERE issuer='bstocks'"
                                  ).fetchone()[0]

    # v2: NVDAc + TSLAB drop out; bstocks leaves the seed entirely.
    v2 = synth_data({
        "TSLAc": ("coinbase", "Tesla, Inc.", ["A"]),
        "TSLAr": ("robinhood", "Tesla, Inc.", ["R"]),
    })
    stmts2, rep2 = seed_multichain.build_statements(v2)
    check("(d) dropout run emits no DELETE statement",
          not any(s.strip().upper().startswith("DELETE")
                  for s, _ in stmts2))
    check("(d) dropout run flags bstocks as inactive issuer",
          rep2["inactive_issuers"] == ["bstocks"],
          str(rep2["inactive_issuers"]))
    exec_stmts(conn, stmts2)
    st = dict(conn.execute("SELECT ticker_id, status FROM universe "
                           "WHERE issuer IN ('coinbase','bstocks',"
                           "'robinhood')").fetchall())
    check("(d) dropped NVDAc marked inactive, not deleted",
          st.get("NVDAc") == "inactive", str(st))
    check("(d) dropped TSLAB marked inactive, not deleted",
          st.get("TSLAB") == "inactive", str(st))
    check("(d) kept TSLAc stays active",
          st.get("TSLAc") == "active", str(st))
    check("(d) new TSLAr seeded active",
          st.get("TSLAr") == "active", str(st))
    pa = conn.execute("SELECT is_active FROM pools "
                      "WHERE pool_id='bsc:0xpairB'").fetchone()[0]
    check("(d) dropped TSLAB pool is_active=0, row kept", pa == 0)
    pa = conn.execute("SELECT is_active FROM pools "
                      "WHERE pool_id='base:0xpairA'").fetchone()[0]
    check("(d) kept TSLAc pool stays is_active=1", pa == 1)
    hist = conn.execute("SELECT COUNT(*) FROM deviations "
                        "WHERE ticker_id='TSLAB'").fetchone()[0]
    check("(d) dropout run: dropped ticker's deviations history "
          "survives", hist == 1, f"n={hist}")
    hist = conn.execute("SELECT COUNT(*) FROM snapshots "
                        "WHERE pool_id='base:0xpairA'").fetchone()[0]
    check("(d) dropout run: snapshots history survives", hist == 1)
    row = conn.execute("SELECT status, observed_at FROM "
                       "redemption_windows WHERE issuer='bstocks'"
                       ).fetchone()
    check("(d) bstocks redemption row marked inactive, not deleted",
          row[0] == "inactive", str(row))
    check("(d) bstocks redemption observed_at untouched by the "
          "inactive-marking itself (never becomes the poller's "
          "'latest' row)",
          row[1] == obs_bstocks_v1, str(row))
    note_en_r = conn.execute("SELECT window_note_en FROM "
                             "redemption_windows WHERE issuer='robinhood'"
                             ).fetchone()[0]
    check("(d/S13) robinhood window_note_en present + honest",
          note_en_r and "roadmap" in note_en_r
          and "No public PoR found" in note_en_r, str(note_en_r)[:80])
    conn.close()

    # ---- runner refuses non-local targets ----
    r = run_runner("https://example.invalid/x.db")
    check("runner refuses URL target", r.returncode == 2, r.stdout)
    r = run_runner(os.path.join(tmp, "nope.txt"))
    check("runner refuses non-.db target", r.returncode == 2, r.stdout)

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
