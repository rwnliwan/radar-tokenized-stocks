"""Spread bad-tick guard test (Q6 vote A, 3-0 — fix 2026-11-08).

Replicates the 2026-11-06 incident with fixtures copied VERBATIM from
Turso (snapshots + deviations rows read 2026-11-08; see comments):

- SPYx 2026-11-06T19:06:00Z: one pool quoted $0.1044 (reserve
  $1,239,492.48) against four siblings at $742.85–$744.099. The
  poller price-sanity guard excluded it (poller_health gap_note
  "price-guard excluded pool(s): SPYx:1", deviations pools_excluded=1,
  dw=$743.648...), but the bot's spread check used the RAW venues and
  fired a 100.041% spread alert (alert_log 2026-11-06T19:06:32Z).
  From the fixture values the raw formula gives 100.047% — 0.006pp
  above the logged 100.041% (the live pass read dw/venues at
  19:06:32Z; the fixture is the 19:06:00Z snapshot row). The
  difference is immaterial: the fixture reproduces a ~100% false
  spread, and after the fix the guarded spread is 0.168% (< 1%).
- NVDAx 2026-11-06T19:11:00Z: genuine spread alert, 4.426% in
  alert_log (19:11:35Z). From the fixture values the formula gives
  4.424% (0.002pp below the logged value, same read-time note as
  above). The low pool ($179.55, reserve $96,257) deviates only
  4.27% from the cross-venue median, so the 25% guard keeps it and
  the genuine alert MUST still fire.

Pure + offline: only bot.evaluate_alerts / bot.guarded_venues are
called — no DB, no network, no token, no Telegram send.
Thresholds are NOT changed here: SPREAD_THRESHOLD stays 1.0%,
DEV_HIGH 3.0%, dedup 24h, stale gate 30 min (all asserted only
indirectly — this file tests the guard, not the thresholds).

Usage: python3 qa/test_spread_guard.py  (exit 0 = PASS)
"""
import statistics
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks")
import bot  # noqa: E402  (token is lazy; import touches no vault/DB)

FAILURES = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def raw_spread(venues, dw):
    prices = [v["price"] for v in venues]
    return (max(prices) - min(prices)) / dw * 100.0


# --- Fixtures: verbatim Turso values, 2026-11-06 -----------------------
# SPYx, cycle 2026-11-06T19:06:00Z (5 active pools; deviations row:
# dw=743.6480584737494, dev=-0.031986289061839014, depth=3060957.12,
# pools_used=4, pools_excluded=1).
SPYX_1906 = {
    "ticker": "SPYx", "issuer": "xStocks",
    "venues": [
        {"dex": "raydium", "price": 743.76, "reserve": 1993295.48},
        {"dex": "raydium", "price": 744.012, "reserve": 360556.18},
        {"dex": "raydium", "price": 0.1044, "reserve": 1239492.48},
        {"dex": "raydium", "price": 742.85, "reserve": 539004.9},
        {"dex": "orca", "price": 744.099, "reserve": 168100.56},
    ],
    "dw": 743.6480584737494, "dev_med": -0.031986289061839014,
    "depth": 3060957.12, "pools_used": 4, "median": 743.76,
    "redemption_status": "open", "por_age_hours": 6.0,
}
# NVDAx, cycle 2026-11-06T19:11:00Z (6 active pools; deviations row:
# dw=187.82412248448196, dev=0.058132000363294266, depth=3122274.87,
# pools_used=4, pools_excluded=0). Note the $179.55 pool (reserve
# $96,257 < $100k) is NOT a poller qualifying pool. Before fix ronde 5
# (M2) the bot's venue list never filtered on reserve, so that pool set
# the low and the 4.426% spread alert fired. After M2 the bot uses the
# same qualifying population as the poller, so this fixture NO LONGER
# fires (qualifying-only spread 0.325%) — the alert was driven by a
# non-qualifying pool. The genuine-alert coverage moves to
# NVDAX_QUAL below, where the low pool qualifies.
NVDAX_1911 = {
    "ticker": "NVDAx", "issuer": "xStocks",
    "venues": [
        {"dex": "raydium", "price": 187.25, "reserve": 131476.02},
        {"dex": "raydium", "price": 187.86, "reserve": 2629385.98},
        {"dex": "raydium", "price": 187.57, "reserve": 109721.01},
        {"dex": "orca", "price": 187.86, "reserve": 251691.86},
        {"dex": "orca", "price": 179.55, "reserve": 96257.05},
        {"dex": "meteora", "price": 187.55, "reserve": 93400.45},
    ],
    "dw": 187.82412248448196, "dev_med": 0.058132000363294266,
    "depth": 3122274.87, "pools_used": 4, "median": 187.56,
    "redemption_status": "open", "por_age_hours": 6.0,
}
# NVDAX_QUAL: same prices as NVDAX_1911, but the $179.55 low pool now
# qualifies (reserve $150,000 >= $100k). The meteora pool ($93,400)
# stays sub-$100k and is filtered out, so 5 qualifying venues remain
# and the genuine 4.424% spread still fires on qualifying pools only.
NVDAX_QUAL = {
    "ticker": "NVDAx", "issuer": "xStocks",
    "venues": [
        {"dex": "raydium", "price": 187.25, "reserve": 131476.02},
        {"dex": "raydium", "price": 187.86, "reserve": 2629385.98},
        {"dex": "raydium", "price": 187.57, "reserve": 109721.01},
        {"dex": "orca", "price": 187.86, "reserve": 251691.86},
        {"dex": "orca", "price": 179.55, "reserve": 150000.0},
        {"dex": "meteora", "price": 187.55, "reserve": 93400.45},
    ],
    "dw": 187.82412248448196, "dev_med": 0.058132000363294266,
    "depth": 3122274.87, "pools_used": 4, "median": 187.56,
    "redemption_status": "open", "por_age_hours": 6.0,
}


def spreads(data):
    return [a for a in bot.evaluate_alerts([data], True) if a["type"] == "spread"]


def main():
    # 0) Thresholds untouched (guard test must not smuggle a change).
    check("thresholds unchanged (spread 1.0 / dev 3.0 / depth 250k)",
          bot.SPREAD_THRESHOLD == 1.0 and bot.DEV_HIGH_THRESHOLD == 3.0
          and bot.DEPTH_MIN == 250000.0 and bot.DEDUP_HOURS == 24.0
          and bot.STALE_MINUTES == 30.0,
          f"spread={bot.SPREAD_THRESHOLD} dev={bot.DEV_HIGH_THRESHOLD} "
          f"depth={bot.DEPTH_MIN} dedup={bot.DEDUP_HOURS}h "
          f"stale={bot.STALE_MINUTES}m")

    # 1) Fixture validity: raw formula on SPYx reproduces the incident.
    raw = raw_spread(SPYX_1906["venues"], SPYX_1906["dw"])
    check("fixture reproduces incident (raw SPYx spread ~100.041%)",
          abs(raw - 100.041) < 0.01, f"raw={raw:.3f}% (logged 100.041%)")

    # 2) Guard drops exactly the bad pool, keeps the other four.
    kept = bot.guarded_venues(SPYX_1906["venues"])
    check("guard excludes the $0.1044 pool only",
          len(kept) == 4 and all(v["price"] != 0.1044 for v in kept)
          and sorted(v["price"] for v in kept) == [742.85, 743.76, 744.012, 744.099],
          f"kept={[v['price'] for v in kept]}")
    check("guarded SPYx spread is 0.168% (< 1% threshold)",
          abs(raw_spread(kept, SPYX_1906["dw"]) - 0.168) < 0.001,
          f"guarded={raw_spread(kept, SPYX_1906['dw']):.3f}%")

    # 3) THE FIX: no false SPYx spread alert anymore.
    check("SPYx 19:06 false alert NO LONGER fires",
          spreads(SPYX_1906) == [], f"alerts={spreads(SPYX_1906)}")

    # 4) Fixture validity: raw formula on NVDAx reproduces the real alert.
    raw_nv = raw_spread(NVDAX_1911["venues"], NVDAX_1911["dw"])
    check("fixture reproduces real alert (raw NVDAx spread ~4.426%)",
          abs(raw_nv - 4.426) < 0.01, f"raw={raw_nv:.3f}% (logged 4.426%)")

    # 5) Guard keeps all six NVDAx venues (low pool only 4.27% off median).
    kept_nv = bot.guarded_venues(NVDAX_1911["venues"])
    med_nv = statistics.median([v["price"] for v in NVDAX_1911["venues"]])
    check("guard keeps all NVDAx venues (low pool 4.27% off median)",
          len(kept_nv) == 6, f"kept={len(kept_nv)} median={med_nv}")

    # 6) M2 (fix ronde 5): the ORIGINAL NVDAx alert no longer fires —
    # its low pool ($179.55, reserve $96,257) is below LIQ_MIN, so it is
    # not a qualifying pool; the qualifying-only spread is 0.325% (< 1%).
    # The genuine alert is preserved on qualifying pools (NVDAX_QUAL).
    check("NVDAx 19:11 original NO LONGER fires (low pool sub-$100k, M2)",
          spreads(NVDAX_1911) == [], f"alerts={spreads(NVDAX_1911)}")
    check("NVDAx qualifying-only spread is 0.325% (< 1%)",
          abs((187.86 - 187.25) / NVDAX_1911["dw"] * 100.0 - 0.325) < 0.001,
          f"qual spread={(187.86 - 187.25) / NVDAX_1911['dw'] * 100.0:.3f}%")
    nv = spreads(NVDAX_QUAL)
    check("NVDAx genuine alert STILL fires on qualifying pools",
          len(nv) == 1, f"alerts={nv}")
    if nv:
        check("NVDAx spread value 4.424% (>= 1.0%)",
              nv[0]["spread_pct"] == 4.424, f"got {nv[0]['spread_pct']}")
        check("NVDAx hi/lo are the real venues (187.86 raydium / 179.55 orca)",
              nv[0]["high_venue"]["price"] == 187.86
              and nv[0]["low_venue"]["price"] == 179.55
              and nv[0]["low_venue"]["dex"] == "orca",
              f"hi={nv[0]['high_venue']} lo={nv[0]['low_venue']}")
        check("NVDAx pools_used counts qualifying guarded venues (5)",
              nv[0]["pools_used"] == 5, f"got {nv[0]['pools_used']}")

    # 7) Guard is skipped with <3 venues (same limitation as poller):
    # a 2-venue 1.006% spread (existing test_bot_alerts scenario) fires.
    two = {
        "ticker": "TSLAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 371.16, "reserve": 2380000.0},
                   {"dex": "orca", "price": 374.90, "reserve": 500000.0}],
        "dw": 371.81, "dev_med": 0.35, "depth": 2880000.0,
        "pools_used": 2, "median": 373.03,
        "redemption_status": "open", "por_age_hours": 6.0,
    }
    t = spreads(two)
    check("2-venue spread still fires (guard skipped, <3 pools)",
          len(t) == 1 and t[0]["spread_pct"] == 1.006, f"alerts={t}")
    check("guarded_venues returns 2-venue list unchanged",
          bot.guarded_venues(two["venues"]) == two["venues"])

    # 8) Other alert paths do not depend on raw venue prices:
    # deviation uses dev_med from the (guarded) deviations row, so a
    # bad tick in venues cannot fake it — and a real dev_med still fires.
    bad_dev = dict(SPYX_1906, dev_med=-0.032)
    check("bad tick alone does NOT fake a deviation alert",
          [a for a in bot.evaluate_alerts([bad_dev], True)
           if a["type"] == "deviation_high"] == [])
    real_dev = dict(SPYX_1906, dev_med=3.5)
    check("real dev_med 3.5% still fires deviation_high",
          len([a for a in bot.evaluate_alerts([real_dev], True)
               if a["type"] == "deviation_high"]) == 1)
    # Redemption / PoR ignore venue prices entirely.
    red = dict(SPYX_1906, redemption_status="closed",
               next_open_at="2026-11-09T04:00:00Z")
    check("redemption still fires with bad tick present",
          len([a for a in bot.evaluate_alerts([red], True)
               if a["type"] == "redemption"]) == 1)
    por = dict(SPYX_1906, por_age_hours=96.0,
               por_last_update="2026-11-02T11:00:00Z")
    check("PoR stale still fires with bad tick present",
          len([a for a in bot.evaluate_alerts([por], True)
               if a["type"] == "por"]) == 1)
    # Market closed: no spread alert even for a genuine spread.
    check("no spread alert when market closed",
          bot.evaluate_alerts([NVDAX_1911], False) == [])

    # 9) Ronde 6, M-new-1: the DASHBOARD spread (dashboard/logic.py
    # cross_venue_spread, imported by dashboard/app.py — the master
    # table and the ticker detail page both go through it) must apply
    # the SAME 25%-from-median guard as bot/Worker. The dashboard
    # used to compute the raw spread here: SPYx showed ~100% while
    # bot/Worker showed 0.168%.
    sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
    import logic  # noqa: E402
    def dash_venues(data):
        return [{"price_usd": v["price"], "reserve_usd": v["reserve"]}
                for v in data["venues"]]
    spy_dash = logic.cross_venue_spread(dash_venues(SPYX_1906), SPYX_1906["dw"])
    check("dashboard SPYx spread is 0.168% (guarded, not ~100%)",
          spy_dash is not None and abs(spy_dash - 0.168) < 0.001,
          f"dashboard={spy_dash}")
    nv_dash = logic.cross_venue_spread(dash_venues(NVDAX_1911), NVDAX_1911["dw"])
    check("dashboard NVDAx qualifying-only spread is 0.325%",
          nv_dash is not None and abs(nv_dash - 0.325) < 0.001,
          f"dashboard={nv_dash}")
    check("dashboard spread matches bot guarded spread (SPYx)",
          spy_dash is not None
          and abs(spy_dash - raw_spread(kept, SPYX_1906["dw"])) < 0.001,
          f"dashboard={spy_dash} bot-guarded={raw_spread(kept, SPYX_1906['dw']):.3f}%")
    two_dash = logic.cross_venue_spread(dash_venues(two), two["dw"])
    check("dashboard 2-venue spread still fires (guard skipped, <3)",
          two_dash is not None and abs(two_dash - 1.006) < 0.001,
          f"dashboard={two_dash}")
    check("dashboard spread None with <2 qualifying venues",
          logic.cross_venue_spread(
              [{"price_usd": 100.0, "reserve_usd": 200000.0}], 100.0) is None)
    check("dashboard spread None with no dw",
          logic.cross_venue_spread(dash_venues(SPYX_1906), None) is None)

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("SPREAD GUARD TEST: PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
