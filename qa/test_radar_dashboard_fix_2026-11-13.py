"""Dashboard-side tests for the DeepSeek Radar review fix round
(2026-11-13): M11, S5, N2, M5.

Pure + local-sqlite only: no network, no Turso token, no live reads.
Streamlit is NOT imported (it is not installed in this VM): the SQL
under test is read out of dashboard/app.py with `ast`, and the pure
helpers are imported from dashboard/logic.py and dashboard/risk.py.
turso_read.get_latest_exit_scores is exercised with a stubbed
_pipeline (canned Hrana-shaped results), never a real connection.

- M11: dexscreener_pair_url maps every pool.chain value to the right
  DexScreener slug (same map as web/src/lib/dexscreener.ts); an
  unknown chain (e.g. elysium) or a missing pair yields None — no
  link, never a guessed/wrong-chain link.
- S5: VENUES_LIVE_SQL (dashboard/app.py) anchors each ticker to ITS
  OWN latest snapshot within the last 2 h. Fixture: ticker A reports
  at T-5m (2 pools), ticker B at T-60m (1 pool), ticker C at T-180m
  (1 pool, outside the 2 h window). The OLD global-MAX(ts) query
  counts only A (2/4); the fixed query counts A+B (3/4).
- N2: perp_is_fresh — a perp snapshot is usable only when 0-15 min
  old; future-dated / unparseable / missing timestamps are stale.
- M5: exit_score_partial — a stored score is partial when fewer
  than 3 of 5 components are present, or the components column does
  not exist yet (None). get_latest_exit_scores reads
  exit_score_components when the column exists and returns None for
  it (never crashes) when it does not.

Thresholds are NOT changed here (alert 1.0%, pool >= $100k,
universe >= $500k + >= 2 venues, perp freshness 15 min per N2).

Usage: python3 qa/test_radar_dashboard_fix_2026-11-13.py (exit 0 = PASS)
"""
import ast
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

REPO = "/home/hatch/workspace/radar-tokenized-stocks"
sys.path.insert(0, os.path.join(REPO, "dashboard"))

from logic import dexscreener_pair_url, perp_is_fresh  # noqa: E402
from risk import exit_score_partial  # noqa: E402
import turso_read  # noqa: E402

FAILURES = []
UTC = timezone.utc


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _ts(minutes_ago, now):
    return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- M11 ---------------------------------------------------------------
def test_m11():
    cases = [
        ("solana", "PAIR1", "https://dexscreener.com/solana/PAIR1"),
        ("base", "PAIR2", "https://dexscreener.com/base/PAIR2"),
        ("bsc", "PAIR3", "https://dexscreener.com/bsc/PAIR3"),
        ("bnb", "PAIR3", "https://dexscreener.com/bsc/PAIR3"),
        ("ethereum", "PAIR4", "https://dexscreener.com/ethereum/PAIR4"),
        ("hyperliquid", "PAIR5",
         "https://dexscreener.com/hyperliquid/PAIR5"),
        ("robinhood", "PAIR6", "https://dexscreener.com/robinhood/PAIR6"),
        ("SOLANA", "PAIR1", "https://dexscreener.com/solana/PAIR1"),
        (" Base ", "PAIR2", "https://dexscreener.com/base/PAIR2"),
    ]
    for chain, pair, want in cases:
        got = dexscreener_pair_url(chain, pair)
        check(f"M11 {chain!r} -> {want}", got == want, f"got {got!r}")
    for chain, pair in [("elysium", "PAIR7"), ("unknown-chain", "PAIR8"),
                        (None, "PAIR9"), ("solana", None),
                        ("solana", ""), ("", "PAIR1")]:
        got = dexscreener_pair_url(chain, pair)
        check(f"M11 {chain!r}/{pair!r} -> None (no link, never guessed)",
              got is None, f"got {got!r}")


# --- S5 ----------------------------------------------------------------
def _venues_live_sql():
    """The exact SQL string shipped in dashboard/app.py, read from
    source (no Streamlit import)."""
    with open(os.path.join(REPO, "dashboard", "app.py")) as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "VENUES_LIVE_SQL":
                    return ast.literal_eval(node.value)
    raise AssertionError("VENUES_LIVE_SQL not found in dashboard/app.py")


OLD_VENUES_LIVE_SQL = (
    "SELECT (SELECT COUNT(*) FROM pools WHERE is_active = 1) AS total, "
    "COUNT(DISTINCT pool_id) AS live FROM snapshots "
    "WHERE ts = (SELECT MAX(ts) FROM snapshots)"
)


def test_s5():
    now = datetime.now(UTC).replace(microsecond=0)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE pools (pool_id TEXT, ticker_id TEXT,"
               " is_active INTEGER)")
    db.execute("CREATE TABLE snapshots (pool_id TEXT, ts TEXT)")
    pools = [("p1", "A", 1), ("p2", "A", 1), ("p3", "B", 1),
             ("p4", "C", 1), ("p5", "A", 0)]  # p5 inactive: not in total
    snaps = [("p1", _ts(5, now)), ("p2", _ts(5, now)),
             ("p1", _ts(65, now)),  # stale row for p1: must not double-count
             ("p3", _ts(60, now)),  # B's own latest, within 2 h
             ("p4", _ts(180, now))]  # C's latest, outside the 2 h window
    db.executemany("INSERT INTO pools VALUES (?,?,?)", pools)
    db.executemany("INSERT INTO snapshots VALUES (?,?)", snaps)
    sql = _venues_live_sql()
    check("S5 SQL has no global MAX(ts) anchor",
          "MAX(ts) FROM snapshots)" not in sql, sql[:80])
    row = db.execute(sql).fetchone()
    check("S5 fixed query: live=3 total=4 (A 2 pools + B 1; C too old)",
          row == (4, 3), f"got {row}")
    old = db.execute(OLD_VENUES_LIVE_SQL).fetchone()
    check("S5 old query would say live=2 (bug reproduced on fixture)",
          old == (4, 2), f"got {old}")
    db.close()


# --- N2 ----------------------------------------------------------------
def test_n2():
    now = datetime.now(UTC).replace(microsecond=0)
    cases = [
        (_ts(0, now), True, "now"),
        (_ts(5, now), True, "5 min ago"),
        (_ts(14, now), True, "14 min ago"),
        (_ts(15, now), True, "15 min ago (boundary, inclusive)"),
        ((now - timedelta(minutes=15, seconds=59)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"), False, "15 min 59 s ago"),
        (_ts(16, now), False, "16 min ago"),
        (_ts(180, now), False, "3 h ago"),
        ((now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         False, "5 min in the future"),
        (None, False, "missing ts"),
        ("not-a-timestamp", False, "unparseable ts"),
        ("", False, "empty ts"),
    ]
    for ts, want, label in cases:
        got = perp_is_fresh(ts, now=now)
        check(f"N2 perp_is_fresh {label} -> {want}", got is want,
              f"got {got!r}")
    # Default `now` (no arg) must not raise and must accept a fresh ts.
    check("N2 perp_is_fresh default now works",
          perp_is_fresh(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
          is True)


# --- M5 ----------------------------------------------------------------
def test_m5_partial():
    cases = [(None, True, "column missing (None)"),
             (0, True, "0 components"), (1, True, "1 component"),
             (2, True, "2 components"), (3, False, "3 components"),
             (4, False, "4 components"), (5, False, "5 components"),
             ("bad", True, "unparseable value")]
    for value, want, label in cases:
        got = exit_score_partial(value)
        check(f"M5 exit_score_partial {label} -> {want}", got is want,
              f"got {got!r}")


def _hrana_result(col_names, rows):
    """Canned _pipeline result: {cols:[{name}], rows:[[{'value'}]]}."""
    return {"cols": [{"name": c} for c in col_names],
            "rows": [[{"value": v} for v in row] for row in rows]}


def test_m5_turso_read():
    orig_pipeline = turso_read._pipeline
    try:
        # Scenario 1: migration applied — column exists.
        def fake_with_components(stmts):
            out = []
            for sql, _args in stmts:
                if sql.startswith("PRAGMA"):
                    out.append(_hrana_result(
                        ["name"],
                        [["id"], ["ticker_id"], ["ts"], ["exit_score"],
                         ["exit_score_version"], ["exit_score_components"]]))
                else:
                    out.append(_hrana_result(
                        ["ticker_id", "ts", "exit_score",
                         "exit_score_version", "exit_score_components"],
                        [["TSLAx", "2026-11-13T00:30:00Z", 85.0, "exit_score_v2", 2],
                         ["TSLAx", "2026-11-13T00:25:00Z", 40.0, "exit_score_v2", 5],
                         ["NVDAc", "2026-11-13T00:30:00Z", 20.0, "exit_score_v2", 4]]))
            return out
        turso_read._pipeline = fake_with_components
        res = turso_read.get_latest_exit_scores()
        check("M5 reader returns components=2 for TSLAx (latest row wins)",
              res.get("TSLAx", {}).get("exit_score_components") == 2,
              str(res.get("TSLAx")))
        check("M5 reader returns score 85.0 for TSLAx",
              res.get("TSLAx", {}).get("exit_score") == 85.0,
              str(res.get("TSLAx")))
        check("M5 reader returns components=4 for NVDAc",
              res.get("NVDAc", {}).get("exit_score_components") == 4,
              str(res.get("NVDAc")))
        check("M5 TSLAx score is partial (2 < 3)",
              exit_score_partial(res["TSLAx"]["exit_score_components"]) is True)
        check("M5 NVDAc score is full (4 >= 3)",
              exit_score_partial(res["NVDAc"]["exit_score_components"]) is False)

        # Scenario 2: migration NOT run — no exit_score_components col.
        def fake_without_components(stmts):
            out = []
            for sql, _args in stmts:
                if sql.startswith("PRAGMA"):
                    out.append(_hrana_result(
                        ["name"],
                        [["id"], ["ticker_id"], ["ts"], ["exit_score"],
                         ["exit_score_version"]]))
                else:
                    out.append(_hrana_result(
                        ["ticker_id", "ts", "exit_score", "exit_score_version"],
                        [["TSLAx", "2026-11-13T00:30:00Z", 85.0,
                          "exit_score_v2"]]))
            return out
        turso_read._pipeline = fake_without_components
        res = turso_read.get_latest_exit_scores()
        check("M5 reader without column: components is None, no crash",
              res.get("TSLAx", {}).get("exit_score_components") is None,
              str(res.get("TSLAx")))
        check("M5 reader without column: score still read",
              res.get("TSLAx", {}).get("exit_score") == 85.0,
              str(res.get("TSLAx")))
        check("M5 missing column treated as partial",
              exit_score_partial(res["TSLAx"]["exit_score_components"])
              is True)

        # Scenario 3: no exit_score column at all (pre-migration DB).
        def fake_no_score(stmts):
            return [_hrana_result(["name"],
                                  [["id"], ["ticker_id"], ["ts"]])]
        turso_read._pipeline = fake_no_score
        check("M5 reader without exit_score column returns {}",
              turso_read.get_latest_exit_scores() == {})
    finally:
        turso_read._pipeline = orig_pipeline


def main():
    test_m11()
    test_s5()
    test_n2()
    test_m5_partial()
    test_m5_turso_read()
    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nALL PASS")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
