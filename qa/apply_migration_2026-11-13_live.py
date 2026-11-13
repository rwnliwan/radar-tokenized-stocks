"""Apply migrations/2026-11-13-radar-fix.sql to Turso LIVE via Hrana.

Same PRAGMA-guarded, re-runnable plan as qa/apply_migration_2026-11-13.py
(local sqlite): ALTERs are skipped when the column already exists,
CREATE INDEX IF NOT EXISTS is safe to re-run. This is the live path the
local runner deliberately refuses; it exists because the local runner's
docstring says live application is "a separate, manual step (Hrana
pipeline with the same PRAGMA checks)".

ACC: Septian 08:27 WITA 13 Nov 2026 — deploy fix Radar mengikuti
rekomendasi Chief (migrasi -> Worker -> web -> dashboard -> poller+seed).

Usage:
    python3 qa/apply_migration_2026-11-13_live.py --check
        # plan only: report RUN/SKIP per statement, write nothing.
    python3 qa/apply_migration_2026-11-13_live.py --live --yes
        # apply the RUN statements to live Turso, then verify all 7
        # objects exist. Requires BOTH flags (accident guard).

DDL runs through its own curl call with a 600s timeout (index creation
on the live deviations table can outlast turso_client's 60s default);
reads (plan + verify) use turso_client. The token value is never
printed, logged, or written to disk.
"""
import json
import subprocess
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks")
import turso_client  # noqa: E402
from turso_client import query  # noqa: E402

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
MIGRATION = f"{ROOT}/migrations/2026-11-13-radar-fix.sql"

sys.path.insert(0, f"{ROOT}/qa")
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "apply_local", f"{ROOT}/qa/apply_migration_2026-11-13.py")
apply_local = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_local)

EXPECTED_COLUMNS = {
    "deviations": {"exit_score_components"},
    "perp_snapshots": {"perp_px_source"},
}
EXPECTED_INDEXES = {
    "idx_poller_health_cycle_ts",
    "idx_deviations_ts",
    "idx_perp_snapshots_ts",
    "idx_deviations_ticker_nocase_ts",
    "idx_perp_ticker_nocase_ts",
}


def live_state():
    cols = {}
    for tbl in EXPECTED_COLUMNS:
        cols[tbl] = {r["name"] for r in query(
            f"SELECT name FROM pragma_table_info('{tbl}')")}
    indexes = {r["name"] for r in query(
        "SELECT name FROM sqlite_master WHERE type = 'index'")}
    return cols, indexes


def plan(stmts, cols, indexes):
    out = []
    for sql in stmts:
        m = apply_local.ALTER_RE.match(sql)
        if m:
            table, column = m.group(1), m.group(2)
            if column in cols.get(table, set()):
                out.append((sql, f"skip: column {table}.{column} exists"))
            else:
                out.append((sql, "run"))
            continue
        m = apply_local.INDEX_RE.match(sql)
        if m:
            idx = m.group(1)
            out.append((sql, "skip: index exists" if idx in indexes else "run"))
            continue
        raise ValueError(f"unsupported statement: {sql[:80]!r}")
    return out


def ddl(sql):
    """Execute one DDL statement against live Turso (600s timeout)."""
    body = json.dumps({"requests": [{"type": "execute",
                                     "stmt": {"sql": sql}}]})
    r = subprocess.run(
        ["curl", "-s", "-w", "\nHTTP:%{http_code}", "--max-time", "600",
         "-X", "POST", turso_client.URL,
         "-H", "Authorization: Bearer " + turso_client._token(),
         "-H", "Content-Type: application/json", "-d", body],
        capture_output=True, text=True)
    out = r.stdout
    http = None
    if "\nHTTP:" in out:
        out, http = out.rsplit("\nHTTP:", 1)
        http = http.strip()
    if http != "200":
        raise RuntimeError(f"Hrana HTTP {http}: {out[:300]}")
    data = json.loads(out)
    res = data.get("results", [{}])[0]
    if res.get("type") == "error":
        err = res.get("error", {})
        raise RuntimeError(f"Hrana DDL failed: {err.get('message', err)}")
    return True


def main():
    live = "--live" in sys.argv
    check = "--check" in sys.argv
    yes = "--yes" in sys.argv
    if live and not yes:
        print("REFUSED: --live requires --yes (accident guard).", file=sys.stderr)
        return 2
    if not live and not check:
        print("Usage: --check (plan only) or --live --yes (apply).",
              file=sys.stderr)
        return 2
    with open(MIGRATION) as f:
        stmts = apply_local.split_statements(f.read())
    cols, indexes = live_state()
    steps = plan(stmts, cols, indexes)
    ran, skipped = 0, 0
    for sql, action in steps:
        first = " ".join(sql.split())[:100]
        if action == "run":
            if live:
                ddl(sql)
                print(f"RUN  {first}")
            else:
                print(f"WOULD RUN  {first}")
            ran += 1
        else:
            print(f"SKIP ({action[6:]})  {first}")
            skipped += 1
    print(f"{'would apply' if not live else 'applied'}: "
          f"{ran} run, {skipped} skipped, {len(steps)} total.")
    if live:
        cols2, indexes2 = live_state()
        missing = []
        for tbl, want in EXPECTED_COLUMNS.items():
            for c in want:
                if c not in cols2.get(tbl, set()):
                    missing.append(f"column {tbl}.{c}")
        for ix in EXPECTED_INDEXES:
            if ix not in indexes2:
                missing.append(f"index {ix}")
        if missing:
            print(f"VERIFY FAILED — still missing: {missing}", file=sys.stderr)
            return 1
        print("VERIFY OK — all 7 objects present (2 columns + 5 indexes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
