"""Round-5 fix tests (Terra r5 Radar: M1, S1, S2).

Pure + monkeypatched-DB only: no network, no token, no Telegram send,
no production reads/writes.

- M1: load_health_age_minutes anchors on the last SUCCESSFUL poller
  cycle (cycles_ok = 1), not the newest row. The poller writes a
  fresh-timestamped cycles_ok = 0 row on every failed fetch, so the old
  anchor made the 30-min stale gate blind during repeated failures.
- S1: load_live_tickers reports the median of the SAME population the
  poller uses for dev_med — qualifying pools (reserve >= $100k) after
  the 25% price-sanity guard — not a median over raw snapshots.
- S2: format_alert renders a missing price/depth/pool-count as "—",
  never as $0.00 / $0 / 0 pools.

Thresholds are NOT changed here (spread 1.0%, dev 3.0%, depth $250k,
dedup 24h, stale gate 30 min).

Usage: python3 qa/test_r5_fix.py  (exit 0 = PASS)
"""
import sys
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


def main():
    now = datetime.now(UTC).replace(microsecond=0)
    orig_query = bot.db_query
    try:
        # --- M1: stale gate anchors on last SUCCESS -------------------
        # Newest rows failed (5 and 10 min ago); last success 35 min ago.
        rows = [
            {"cycle_ts": _ts(5, now), "cycles_ok": 0},
            {"cycle_ts": _ts(10, now), "cycles_ok": 0},
            {"cycle_ts": _ts(35, now), "cycles_ok": 1},
        ]
        bot.db_query = lambda sql, args=None: rows
        age = bot.load_health_age_minutes(now)
        check("M1 age anchors on last success (35 min, not 5)",
              age is not None and abs(age - 35.0) < 0.01, f"age={age}")
        check("M1 gate would fire (35 > 30)",
              age is not None and age > bot.STALE_MINUTES, f"age={age}")

        # All recent rows failed -> None (callers treat as stale).
        bot.db_query = lambda sql, args=None: [
            {"cycle_ts": _ts(5, now), "cycles_ok": 0},
            {"cycle_ts": _ts(10, now), "cycles_ok": 0},
        ]
        check("M1 no success in window -> None (stale)",
              bot.load_health_age_minutes(now) is None)

        # Newest row successful -> age of that row (unchanged behaviour).
        bot.db_query = lambda sql, args=None: [
            {"cycle_ts": _ts(4, now), "cycles_ok": 1},
        ]
        age = bot.load_health_age_minutes(now)
        check("M1 fresh success reads 4 min",
              age is not None and abs(age - 4.0) < 0.01, f"age={age}")

        # --- S1: median from qualifying + guarded population ----------
        def fake_query(sql, args=None):
            if "FROM universe ORDER BY" in sql:
                return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
            if "FROM deviations" in sql:
                return [{"ticker_id": "TSLAx", "ts": _ts(5, now),
                         "depth_weighted_price": 100.5,
                         "dev_vs_median_pct": 3.5,
                         "qualifying_depth_usd": 600000.0, "pools_used": 3}]
            if "FROM redemption_windows" in sql:
                return []
            if "FROM por_feeds" in sql:
                return []
            if "FROM pools p JOIN snapshots" in sql:
                # 100/101/200 at $200k each (qualifying) + 50 at $10k
                # (sub-$100k, must not move the median). Guard drops 200.
                return [
                    {"dex": "raydium", "price_usd": 100.0, "reserve_usd": 200000.0},
                    {"dex": "raydium", "price_usd": 101.0, "reserve_usd": 200000.0},
                    {"dex": "raydium", "price_usd": 200.0, "reserve_usd": 200000.0},
                    {"dex": "orca", "price_usd": 50.0, "reserve_usd": 10000.0},
                ]
            raise AssertionError(f"unexpected SQL: {sql[:80]}")

        bot.db_query = fake_query
        tickers = bot.load_live_tickers()
        check("S1 load returns one ticker", len(tickers) == 1, f"got {len(tickers)}")
        t = tickers[0]
        check("S1 venues exclude sub-$100k pool",
              len(t["venues"]) == 3, f"venues={t['venues']}")
        check("S1 median is guarded qualifying median (100.5, not raw 101)",
              t["median"] == 100.5, f"median={t['median']}")
        alerts = bot.evaluate_alerts(tickers, False)
        devs = [a for a in alerts if a["type"] == "deviation_high"]
        check("S1 deviation alert carries the poller-consistent median",
              len(devs) == 1 and devs[0]["median"] == 100.5,
              f"alerts={devs}")
    finally:
        bot.db_query = orig_query

    # --- S2: missing values render as "—", never $0.00 ---------------
    red = {"type": "redemption", "ticker": "SPYx", "issuer": "xStocks",
           "status": "closed", "next_open_at": None,
           "closes_within_24h": False,
           "dw": None, "depth": None, "pools_used": None}
    msg = bot.format_alert(red, "en")
    check("S2 redemption with no price/depth shows —, not $0.00",
          "$0.00" not in msg and "—" in msg and "0 pools" not in msg, msg.splitlines()[4:6])
    dev = {"type": "deviation_high", "ticker": "NVDAx", "issuer": "xStocks",
           "dev_pct": 3.5, "dw": None, "median": None,
           "depth": None, "pools_used": None}
    msg = bot.format_alert(dev, "en")
    check("S2 deviation with no price/depth shows —, not $0.00",
          "$0.00" not in msg and "—" in msg, msg.splitlines()[2:4])
    por = {"type": "por", "ticker": "METAx", "issuer": "xStocks",
           "age_hours": 96.0, "last_update": None,
           "dw": None, "depth": None, "pools_used": None}
    msg = bot.format_alert(por, "en")
    check("S2 PoR with no price/depth shows —, not $0.00",
          "$0.00" not in msg and "—" in msg, msg.splitlines()[2:4])
    # And present values still render as money (no regression).
    red2 = dict(red, dw=500.10, depth=3000000.0, pools_used=1)
    msg2 = bot.format_alert(red2, "en")
    check("S2 present values still render ($500.10 / 3,000,000 / 1 pool)",
          "$500.10" in msg2 and "$3,000,000" in msg2 and "1 pools" in msg2)

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("R5 FIX TEST: PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
