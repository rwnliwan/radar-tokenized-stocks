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

    # --- R6: S-new-8 PoR backstop, S-new-9 cycle anchor, S-new-10
    # per-channel dedup, S-new-5 stale re-check ----------------------
    def _ts_hours(hours_ago, now):
        return (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

    orig_query2, orig_execute, orig_send = bot.db_query, bot.db_execute, bot.send_message
    try:
        # S-new-8a: stored age frozen at 6h, but last_update 100h ago
        # -> effective age ~100h, PoR alert fires.
        snap_args = {}
        def fake_query_por(sql, args=None):
            if "FROM universe ORDER BY" in sql:
                return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
            if "FROM deviations" in sql:
                return [{"ticker_id": "TSLAx", "ts": _ts(5, now),
                         "depth_weighted_price": 100.5,
                         "dev_vs_median_pct": 0.1,
                         "qualifying_depth_usd": 600000.0, "pools_used": 3}]
            if "FROM redemption_windows" in sql:
                return []
            if "FROM por_feeds" in sql:
                return [{"age_hours": 6.0,
                         "last_update_ts": _ts_hours(100, now)}]
            if "FROM pools p JOIN snapshots" in sql:
                snap_args["args"] = args
                snap_args["sql"] = sql
                return [{"dex": "raydium", "price_usd": 100.0, "reserve_usd": 200000.0}]
            raise AssertionError(f"unexpected SQL: {sql[:80]}")
        bot.db_query = fake_query_por
        tickers = bot.load_live_tickers()
        check("S-new-8 frozen stored age (6h) is overridden by last_update (100h)",
              tickers and tickers[0]["por_age_hours"] is not None
              and abs(tickers[0]["por_age_hours"] - 100.0) < 0.1,
              f"por_age={tickers[0]['por_age_hours'] if tickers else None}")
        pors = [a for a in bot.evaluate_alerts(tickers, False) if a["type"] == "por"]
        check("S-new-8 backstop fires the PoR alert (age ~100h > 72h)",
              len(pors) == 1, f"alerts={pors}")
        # S-new-9: the snapshot query is anchored to the deviations ts.
        check("S-new-9 snapshot query binds the deviations cycle ts",
              _ts(5, now) in (snap_args.get("args") or []),
              f"snapshot args={snap_args.get('args')}")

        # S-new-8b: stored age 96h with a 1h-old last_update stays 96h.
        def fake_query_por2(sql, args=None):
            if "FROM por_feeds" in sql:
                return [{"age_hours": 96.0,
                         "last_update_ts": _ts_hours(1, now)}]
            return fake_query_por(sql, args)
        bot.db_query = fake_query_por2
        tickers = bot.load_live_tickers()
        check("S-new-8 stored age wins when it is the larger (96h vs 1h)",
              tickers and abs(tickers[0]["por_age_hours"] - 96.0) < 0.1,
              f"por_age={tickers[0]['por_age_hours'] if tickers else None}")

        # S-new-5: the send-time re-check reads the gate live.
        bot.db_query = lambda sql, args=None: [
            {"cycle_ts": _ts(4, now), "cycles_ok": 1}]
        check("S-new-5 fresh success (4 min) -> still fresh",
              bot.data_still_fresh() is True)
        bot.db_query = lambda sql, args=None: [
            {"cycle_ts": _ts(35, now), "cycles_ok": 1}]
        check("S-new-5 last success 35 min ago -> NOT fresh",
              bot.data_still_fresh() is False)
        bot.db_query = lambda sql, args=None: []
        check("S-new-5 no health rows -> NOT fresh",
              bot.data_still_fresh() is False)

        # S-new-10: per-channel dedup + per-channel record.
        recorded = []
        def fake_query_log(sql, args=None):
            if "FROM alert_log" in sql:
                if "channel" in sql:
                    ch = args[-1]
                    n = sum(1 for r in recorded
                            if r["channel"] == ch or r["channel"] is None)
                else:
                    n = len(recorded)
                return [{"n": n}]
            return [{"n": 0}]
        def fake_execute_log(sql, args=None):
            recorded.append({"channel": args[7] if len(args) > 7 else None,
                             "ticker": args[0], "type": args[2]})
        bot.db_query = fake_query_log
        bot.db_execute = fake_execute_log
        alert = {"type": "deviation_high", "ticker": "TSLAx",
                 "issuer": "xStocks", "dev_pct": 3.5, "dw": 100.0,
                 "median": 100.0, "depth": 3000000.0, "pools_used": 2}
        check("S-new-10 no rows yet -> not suppressed for either channel",
              bot.suppression_reason(alert, {}, channel="en") is None
              and bot.suppression_reason(alert, {}, channel="id") is None)
        # Legacy NULL row suppresses every channel (transition rule).
        recorded.append({"channel": None, "ticker": "TSLAx", "type": "deviation_high"})
        check("S-new-10 legacy NULL row still suppresses both channels",
              bot.suppression_reason(alert, {}, channel="en") == "dedup 24h"
              and bot.suppression_reason(alert, {}, channel="id") == "dedup 24h")
        recorded.clear()
        # record_alert stores the channel as the 8th arg.
        captured = {}
        bot.db_execute = lambda sql, args=None: captured.update(sql=sql, args=args)
        bot.record_alert(alert, "TEXT", "2026-11-08T12:00:00Z", channel="en")
        check("S-new-10 record_alert stores channel='en'",
              "channel" in captured["sql"] and captured["args"][7] == "en",
              f"args={captured['args']}")
        # send_alert_channels: ID fails -> only EN recorded; next pass
        # retries ID only; third pass sends nothing.
        bot.db_execute = fake_execute_log
        sent_log = []
        def fake_send(chat_id, text, dry_run=False):
            lang = "en" if chat_id == "1" else "id"
            sent_log.append(lang)
            if lang == "id" and not getattr(fake_send, "id_ok", False):
                raise RuntimeError("simulated ID send failure")
            return {"ok": True}
        bot.send_message = fake_send
        channels = [("en", "1"), ("id", "2")]
        n1 = bot.send_alert_channels(alert, channels, {}, now, delay_s=0)
        check("S-new-10 failed ID channel is NOT recorded (EN only)",
              n1 == 1 and [r["channel"] for r in recorded] == ["en"],
              f"sent={n1} recorded={recorded}")
        fake_send.id_ok = True
        n2 = bot.send_alert_channels(alert, channels, {}, now, delay_s=0)
        check("S-new-10 next pass retries ID only (EN skipped, not re-sent)",
              n2 == 1 and [r["channel"] for r in recorded] == ["en", "id"]
              and sent_log.count("en") == 1,
              f"sent={n2} recorded={recorded} sends={sent_log}")
        n3 = bot.send_alert_channels(alert, channels, {}, now, delay_s=0)
        check("S-new-10 third pass sends nothing (both channels recorded)",
              n3 == 0, f"sent={n3}")
    finally:
        bot.db_query, bot.db_execute, bot.send_message = orig_query2, orig_execute, orig_send

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("R5 FIX TEST: PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
