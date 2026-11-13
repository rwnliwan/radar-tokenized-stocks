"""Apply migrations/2026-11-13-radar-fix.sql to a LOCAL sqlite copy.

Re-runnable (S1, fix ronde review DeepSeek Radar 2026-11-13): the
migration's ALTER TABLE ... ADD COLUMN statements have no SQLite
"IF NOT EXISTS" form, so a bare re-run fails with "duplicate column
name". This runner checks PRAGMA table_info(<table>) before each
ALTER and skips columns that already exist; CREATE INDEX IF NOT
EXISTS statements run as-is (SQLite skips existing indexes).

Usage (local sqlite ONLY — never Turso live, never a URL):
    python3 qa/apply_migration_2026-11-13.py --db /tmp/radar-copy.db
    python3 qa/apply_migration_2026-11-13.py --db /tmp/radar-copy.db --check
        # --check: report what would change, write nothing.

Run it twice on the same copy: the second run must exit 0 with
every statement reported SKIPPED. Live Turso application still
needs Septian's ACC and is a separate, manual step (Hrana pipeline
with the same PRAGMA checks); this script refuses anything that is
not a local .db file.
"""
import argparse
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(ROOT, "migrations", "2026-11-13-radar-fix.sql")

ALTER_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE)
INDEX_RE = re.compile(
    r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+ON\s+(\w+)",
    re.IGNORECASE)


def split_statements(sql_text):
    """Strip full-line comments, split on ';'. The migration file
    holds only ALTER / CREATE INDEX statements (no string literals
    containing ';'), so a plain split is exact here."""
    lines = [ln for ln in sql_text.splitlines()
             if not ln.strip().startswith("--")]
    stmts = [s.strip() for s in "\n".join(lines).split(";")]
    return [s for s in stmts if s]


def plan(conn, stmts):
    """Return [(sql, action)] where action is 'run' or 'skip: <why>'."""
    out = []
    for sql in stmts:
        m = ALTER_RE.match(sql)
        if m:
            table, column = m.group(1), m.group(2)
            cols = {r[1] for r in conn.execute(
                f"PRAGMA table_info({table})")}
            if column in cols:
                out.append((sql, f"skip: column {table}.{column} exists"))
            else:
                out.append((sql, "run"))
            continue
        m = INDEX_RE.match(sql)
        if m:
            idx = m.group(1)
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' "
                "AND name=?", (idx,)).fetchone()
            out.append((sql, "skip: index exists" if exists else "run"))
            continue
        raise ValueError(f"unsupported statement for this runner: {sql[:80]!r}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True,
                    help="path to a LOCAL sqlite .db copy (never Turso)")
    ap.add_argument("--check", action="store_true",
                    help="report what would change, write nothing")
    args = ap.parse_args()
    if args.db.startswith(("http://", "https://", "libsql://")):
        print("REFUSED: --db must be a local file, not a URL.", file=sys.stderr)
        return 2
    if not args.db.endswith(".db"):
        print("REFUSED: --db must be a local .db file.", file=sys.stderr)
        return 2
    if not os.path.isfile(args.db):
        print(f"REFUSED: no such file: {args.db} (copy a .db first; "
              "fresh DBs are built from schema.sql).", file=sys.stderr)
        return 2
    with open(MIGRATION) as f:
        stmts = split_statements(f.read())
    conn = sqlite3.connect(args.db)
    try:
        steps = plan(conn, stmts)
        ran, skipped = 0, 0
        for sql, action in steps:
            first = " ".join(sql.split())[:100]
            if action == "run":
                if not args.check:
                    conn.execute(sql)
                print(f"RUN  {first}")
                ran += 1
            else:
                print(f"SKIP ({action[6:]})  {first}")
                skipped += 1
        if not args.check:
            conn.commit()
        print(f"{'would apply' if args.check else 'applied'}: "
              f"{ran} run, {skipped} skipped, {len(steps)} total.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
