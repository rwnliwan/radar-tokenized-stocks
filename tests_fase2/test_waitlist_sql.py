"""Waitlist INSERT validation WITHOUT touching production Turso.

Runs the dashboard's exact INSERT statement (imported from
turso_read) against an in-memory SQLite database built from the
schema's waitlist table, then verifies the row. This proves SQL
correctness; the live write itself is deliberately never test-fired
against production (it would insert a junk row).
"""
import sqlite3
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
from turso_read import INSERT_WAITLIST_SQL  # noqa: E402


def main():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE waitlist (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " contact TEXT, position_size_usd TEXT, venues TEXT,"
        " willing_price TEXT, created_at TEXT NOT NULL, consent INTEGER NOT NULL DEFAULT 0)"
    )
    cur = con.execute(INSERT_WAITLIST_SQL, (
        "test-telegram-user", "$100–$1,000", "Raydium / xStocks",
        None, "2026-10-24T11:00:00Z", 1))
    assert cur.lastrowid == 1
    row = con.execute("SELECT contact, position_size_usd, venues, "
                      "willing_price, consent FROM waitlist").fetchone()
    assert row == ("test-telegram-user", "$100–$1,000", "Raydium / xStocks", None, 1), row
    print("WAITLIST SQL TEST: PASS (exact INSERT runs, row verified, prod untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
