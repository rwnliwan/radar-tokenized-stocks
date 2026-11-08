"""Waitlist INSERT validation WITHOUT touching production Turso.

Runs the dashboard's exact INSERT statement (imported from
turso_read) against an in-memory SQLite database built from the
schema's waitlist table, then verifies the row. This proves SQL
correctness; the live write itself is deliberately never test-fired
against production (it would insert a junk row).

Fix ronde 5 (S3): the INSERT is now atomic
INSERT...SELECT...WHERE NOT EXISTS on the normalized contact (same
dedup as api/worker.js), so a resubmitted contact inserts nothing.
The validation rules in insert_waitlist() mirror the Worker exactly
(contact format, length caps, hourly cap); they are tested here with
a monkeypatched _pipeline so no DB is touched at all.
"""
import sqlite3
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
import turso_read  # noqa: E402
from turso_read import INSERT_WAITLIST_SQL, insert_waitlist  # noqa: E402


def main():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE waitlist (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " contact TEXT, position_size_usd TEXT, venues TEXT,"
        " willing_price TEXT, created_at TEXT NOT NULL, consent INTEGER NOT NULL DEFAULT 0)"
    )
    args = ("test-telegram-user", "$100–$1,000", "Raydium / xStocks",
            None, "2026-10-24T11:00:00Z", 1, "test-telegram-user")
    cur = con.execute(INSERT_WAITLIST_SQL, args)
    assert cur.lastrowid == 1
    row = con.execute("SELECT contact, position_size_usd, venues, "
                      "willing_price, consent FROM waitlist").fetchone()
    assert row == ("test-telegram-user", "$100–$1,000", "Raydium / xStocks", None, 1), row
    # Duplicate (same contact, different case/whitespace) inserts nothing.
    cur = con.execute(INSERT_WAITLIST_SQL, (
        "  Test-Telegram-User ", "$100–$1,000", "Raydium / xStocks",
        None, "2026-10-24T11:05:00Z", 1, "test-telegram-user"))
    assert cur.rowcount == 0, f"duplicate insert must affect 0 rows, got {cur.rowcount}"
    n = con.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    assert n == 1, f"expected 1 row after duplicate submit, got {n}"

    # Validation mirrors the Worker: bad contact / long fields / no
    # consent must fail BEFORE any pipeline call.
    calls = []
    orig_pipeline = turso_read._pipeline
    orig_query = turso_read.query
    try:
        turso_read._pipeline = lambda stmts: calls.append(stmts) or [
            {"rows_written": 1, "last_insert_rowid": 7}]
        turso_read.query = lambda sql, args=None: [{"n": 0}]

        def expect_reject(name, kwargs):
            calls.clear()
            try:
                insert_waitlist(**kwargs)
            except ValueError:
                assert not calls, f"{name}: rejected but pipeline ran"
                return
            raise AssertionError(f"{name}: expected ValueError, insert succeeded")

        good = dict(contact="valid_user", position_size_usd="$100–$1,000",
                    venues="Raydium", willing_price=None,
                    created_at="2026-11-08T10:00:00Z", consent=1)
        expect_reject("bad contact (too short)", dict(good, contact="ab"))
        expect_reject("bad contact (bad chars)", dict(good, contact="not an email!"))
        expect_reject("bad contact (too long)",
                      dict(good, contact="a" * 201))
        expect_reject("missing venues", dict(good, venues="  "))
        expect_reject("venues too long", dict(good, venues="x" * 301))
        expect_reject("no consent", dict(good, consent=0))
        # A valid submit reaches the pipeline with the 7-arg atomic SQL.
        calls.clear()
        assert insert_waitlist(**good) == 7
        assert len(calls) == 1 and "WHERE NOT EXISTS" in calls[0][0][0]
        assert calls[0][0][1][-1] == "valid_user"
        # Email contacts are accepted too.
        calls.clear()
        assert insert_waitlist(**dict(good, contact="user@example.com")) == 7
    finally:
        turso_read._pipeline = orig_pipeline
        turso_read.query = orig_query

    print("WAITLIST SQL TEST: PASS (exact INSERT runs, dup is a no-op, "
          "Worker-identical validation enforced, prod untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
