"""EXIT RADAR QA harness — recompute every published number from source.

Chain verified: poller.py (DexScreener -> deviations/snapshots) ->
api/worker.js (/api/latest, /api/ticker) -> web display.
This script checks links (a) and (b); the browser check covers (c).

Formulas replicated verbatim (do NOT "improve" them here — a mismatch
between this file and poller.py / worker.js / lib/risk.ts IS the finding):
- qualifying pool: latest snapshot per pool, price not null, reserve >= $100k
- guard: >=3 qualifying pools -> drop prices >25% from the cross-pool
  median; excluded pools contribute neither price nor depth; if the
  exclusion empties the set, fall back to all qualifying pools
- dw = sum(price*reserve)/sum(reserve) over kept pools
- median = statistics.median(kept prices), None when <2 kept pools
- dev_pct = (dw - median)/median*100 ; dev_bps = dev_pct*100
- depth = sum(kept reserves); pools_used = len(kept)
- Worker spread_pct = (max-min)/dw*100 over qualifying pools (NO guard)
- Worker status: |bps|>100 alert, >50 watch, else ok, null -> na
- verdict (option A, ACC 25 Okt): danger iff worst |bps|>=100; caution
  iff worst |bps|>=50 or worst spread>=1% or min depth<$250k; else safe
- weekend score (lib/risk.ts): dev |pct|*10 cap 40; depth 25 at <=$250k,
  0 at >=$2.5M, linear between; redemption closed 20 / gated 10 /
  open 0 / unknown excluded; PoR 15*age/72 cap 15, None excluded;
  score_100 = total/max_possible*100 over PRESENT components only.

Usage: .venv/bin/python qa_harness.py  (reads Turso via turso_client,
Worker via curl — urllib is blocked to workers.dev from this VM).
Exit 0 = all checks pass, 1 = any FAIL (warnings never fail the run).
"""

import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from turso_client import query  # noqa: E402

WORKER = "https://radar-api.rwnliwan.workers.dev"
LIQ_MIN = 100_000
DEPTH_FLOOR = 250_000
DEPTH_FULL = 2_500_000
REL_TOL = 1e-9

FAILS = []
WARNS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def warn(name, detail=""):
    print("WARN " + name + (f" — {detail}" if detail else ""))
    WARNS.append(name)


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= REL_TOL * max(1.0, abs(a), abs(b))


def I(v):
    # turso_client returns INTEGER columns as strings (Hrana format).
    return None if v is None else int(v)


def wcurl(path):
    r = subprocess.run(
        ["curl", "-s", "--max-time", "40", WORKER + path],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"curl {path} failed")
    return json.loads(r.stdout)


def weekend_score(dev_pct, depth, red_status, por_age):
    dev = None if dev_pct is None else round(min(max(abs(dev_pct) * 10, 0), 40), 1)
    dep = None
    if depth is not None:
        if depth <= DEPTH_FLOOR:
            dep = 25
        elif depth >= DEPTH_FULL:
            dep = 0
        else:
            dep = round(25 * (1 - (depth - DEPTH_FLOOR) / (DEPTH_FULL - DEPTH_FLOOR)), 1)
    red_map = {"closed": 20, "gated": 10, "open": 0}
    red = None if red_status is None else red_map.get(str(red_status).strip().lower())
    por = None
    if por_age is not None:
        por = 15 if por_age >= 72 else round((15 * max(por_age, 0)) / 72, 1)
    comps = {"deviation": dev, "depth": dep, "redemption": red, "por": por}
    maxima = {"deviation": 40, "depth": 25, "redemption": 20, "por": 15}
    avail = [k for k, v in comps.items() if v is not None]
    total = round(sum(comps[k] for k in avail) * 10) / 10
    maxp = sum(maxima[k] for k in avail)
    score = round(total / maxp * 1000) / 10 if maxp else None
    return {"components": comps, "score_100": score, "present": len(avail)}


def main():
    uni = query("SELECT ticker_id, issuer, tier FROM universe ORDER BY tier, ticker_id")
    tickers = [r["ticker_id"] for r in uni]
    check("universe == 13 tickers", len(tickers) == 13, f"got {len(tickers)}")
    pools = query("SELECT pool_id, ticker_id, dex FROM pools WHERE is_active = 1")
    check("active pools == 35", len(pools) == 35, f"got {len(pools)}")

    max_ts = query("SELECT MAX(ts) AS t FROM deviations")[0]["t"]
    dev_rows = query(
        "SELECT ticker_id, depth_weighted_price, dev_vs_median_pct, "
        "dev_vs_close_pct, qualifying_depth_usd, pools_used, pools_excluded "
        f"FROM deviations WHERE ts = '{max_ts}'"
    )
    dev_by = {r["ticker_id"]: r for r in dev_rows}
    check("deviations row for every ticker at latest cycle", set(dev_by) == set(tickers),
          f"missing: {sorted(set(tickers) - set(dev_by))}")
    check("dev_vs_close NULL everywhere (median-only, license pending)",
          all(r["dev_vs_close_pct"] is None for r in dev_rows))

    # Poller scope (NOT latest-per-pool): only pools returned in THIS cycle
    # carry that cycle's ts. A pool missing from a cycle keeps an older
    # snapshot but contributes nothing to that cycle's deviation.
    snaps = query(
        "SELECT p.ticker_id, p.dex, s.price_usd, s.reserve_usd FROM pools p "
        "JOIN snapshots s ON s.pool_id = p.pool_id WHERE p.is_active = 1 "
        f"AND s.ts = '{max_ts}'"
    )
    by_ticker = {}
    for s in snaps:
        by_ticker.setdefault(s["ticker_id"], []).append(s)

    latest = wcurl("/api/latest")
    w_by = {t["ticker"]: t for t in latest["tickers"]}
    meta = latest["meta"]
    check("Worker serves 13 tickers", len(latest["tickers"]) == 13)
    check("Worker venues_live == venues_total == 35",
          meta["venues_live"] == 35 and meta["venues_total"] == 35,
          f"live={meta['venues_live']} total={meta['venues_total']}")
    age_min = (datetime.now(timezone.utc) - datetime.fromisoformat(
        meta["latest_ts"].replace("Z", "+00:00"))).total_seconds() / 60
    if age_min <= 15:
        check("Worker latest_ts fresh (<=15 min)", True, f"{age_min:.1f} min old")
    else:
        warn("Worker latest_ts stale", f"{age_min:.1f} min old")
    check("Worker latest_ts == deviations MAX(ts)", meta["latest_ts"] == max_ts,
          f"worker={meta['latest_ts']} db={max_ts}")

    red_rows = query("SELECT issuer, status, next_open_at FROM redemption_windows "
                     "ORDER BY observed_at DESC LIMIT 20")
    red_by = {}
    for r in red_rows:
        red_by.setdefault(r["issuer"], r)
    issuer_of = {r["ticker_id"]: r["issuer"] for r in uni}

    verdict_inputs = []
    for tk in tickers:
        q = [(s["price_usd"], s["reserve_usd"]) for s in by_ticker.get(tk, [])
             if s["price_usd"] is not None and (s["reserve_usd"] or 0) >= LIQ_MIN]
        kept, n_ex = q, 0
        if len(q) >= 3:
            med_all = statistics.median([p for p, _ in q])
            if med_all:
                kept = [(p, r) for p, r in q if abs(p - med_all) / med_all <= 0.25]
                n_ex = len(q) - len(kept)
                if not kept:
                    kept, n_ex = q, 0
        depth = sum(r for _, r in kept)
        dw = sum(p * r for p, r in kept) / depth if depth else None
        prices = [p for p, _ in kept]
        median = statistics.median(prices) if len(prices) >= 2 else None
        dev = ((dw - median) / median * 100.0) if (median and dw) else None
        d = dev_by[tk]
        ok = (close(dw, d["depth_weighted_price"]) and close(dev, d["dev_vs_median_pct"])
              and close(depth, d["qualifying_depth_usd"])
              and len(kept) == I(d["pools_used"]) and n_ex == I(d["pools_excluded"]))
        check(f"recompute {tk} (dw/dev/depth/pools/excluded)", ok,
              f"dw={dw} dev={dev} depth={depth} used={len(kept)} ex={n_ex} "
              f"vs db dw={d['depth_weighted_price']} dev={d['dev_vs_median_pct']} "
              f"depth={d['qualifying_depth_usd']} used={d['pools_used']} ex={d['pools_excluded']}")
        w = w_by[tk]
        okw = (close(w["dw_price"], d["depth_weighted_price"])
               and close(w["dev_pct"], d["dev_vs_median_pct"])
               and close(w["depth_usd"], d["qualifying_depth_usd"])
               and I(w["pools_used"]) == I(d["pools_used"]))
        check(f"Worker matches DB {tk}", okw)
        bps = dev * 100 if dev is not None else None
        exp_status = ("na" if bps is None else "alert" if abs(bps) > 100
                      else "watch" if abs(bps) > 50 else "ok")
        check(f"Worker status {tk}", w["status"] == exp_status,
              f"worker={w['status']} expected={exp_status} bps={bps}")
        qprices = [p for p, _ in q]
        exp_spread = ((max(qprices) - min(qprices)) / dw * 100
                      if len(qprices) >= 2 and dw else None)
        check(f"Worker spread {tk}", close(w["spread_pct"], exp_spread),
              f"worker={w['spread_pct']} recomputed={exp_spread}")
        qsorted = sorted(q, key=lambda pr: -pr[1])
        exp_best = qsorted[0] if qsorted else (None, None)
        dex_of_best = None
        if qsorted:
            for s in by_ticker.get(tk, []):
                if s["price_usd"] == exp_best[0] and s["reserve_usd"] == exp_best[1]:
                    dex_of_best = s["dex"]
                    break
        check(f"Worker best pool {tk}",
              close(w["best_price"], exp_best[0]) and w["best_dex"] == dex_of_best,
              f"worker={w['best_price']}@{w['best_dex']} expected={exp_best[0]}@{dex_of_best}")
        red = red_by.get(issuer_of[tk])
        exp_red = str(red["status"]).lower() if red else None
        check(f"Worker redemption {tk}", w["redemption_status"] == exp_red,
              f"worker={w['redemption_status']} db={exp_red}")
        check(f"Worker PoR age None {tk} (no feeds connected)",
              w["por_age_hours"] is None, f"got {w['por_age_hours']}")
        ws = weekend_score(dev, depth, exp_red, None)
        verdict_inputs.append((tk, bps, w["spread_pct"], depth, ws))
        print(f"  INFO {tk}: verdict-inputs bps={bps} spread={w['spread_pct']} "
              f"depth={depth} weekend={ws['score_100']} ({ws['present']}/4) "
              f"comps={ws['components']}")
        if bps is None:
            check(f"null-dev ticker status na {tk}", w["status"] == "na",
                  f"worker={w['status']}")

    if isinstance(latest["tickers"][0]["pools_used"], str):
        warn("Worker serves pools_used as STRING, not number",
             "frontend never renders it, so no display impact")
    worst = max((v for v in verdict_inputs if v[1] is not None), key=lambda v: abs(v[1]))
    wspread = max((v for v in verdict_inputs if v[2] is not None), key=lambda v: v[2])
    mindep = min((v for v in verdict_inputs if v[3] is not None), key=lambda v: v[3])
    wd = abs(worst[1])
    verdict = ("danger" if wd >= 100 else "caution" if (wd >= 50 or wspread[2] >= 1
               or mindep[3] < 250000) else "safe")
    print(f"  INFO verdict: {verdict} (worst dev {worst[0]} {worst[1]:.3f} bps, "
          f"worst spread {wspread[0]} {wspread[2]:.2f}%, thinnest {mindep[0]} "
          f"${mindep[3]:,.0f})")
    print(f"  INFO expected weekend scores: " +
          ", ".join(f"{tk}={ws['score_100']}({ws['present']}/4)"
                    for tk, _, _, _, ws in verdict_inputs))

    # History: 24h/7d return HOURLY AVG buckets, 1h returns raw points.
    hist = wcurl("/api/history?ticker=GOOGLx&window=7d")
    pts = hist["points"]
    check("history GOOGLx non-empty + ordered + hourly buckets", len(pts) > 0
          and all(pts[i]["ts"] <= pts[i + 1]["ts"] for i in range(len(pts) - 1))
          and all(p["ts"].endswith(":00:00Z") for p in pts),
          f"{len(pts)} points")
    if pts:
        last_bucket = pts[-1]["ts"][:13]
        rows = query("SELECT dev_vs_median_pct FROM deviations WHERE ticker_id='GOOGLx' "
                     f"AND substr(ts, 1, 13) = '{last_bucket}' "
                     "AND dev_vs_median_pct IS NOT NULL")
        avg = sum(r["dev_vs_median_pct"] for r in rows) / len(rows) if rows else None
        check("history last bucket == hourly AVG of deviations",
              avg is not None and close(pts[-1]["dev_bps"], avg * 100),
              f"hist={pts[-1]['dev_bps']} recomputed avg={avg * 100 if avg else None} "
              f"from {len(rows)} rows")
    hist1 = wcurl("/api/history?ticker=GOOGLx&window=1h")
    pts1 = hist1["points"]
    if pts1:
        last_nonnull = query("SELECT dev_vs_median_pct FROM deviations WHERE ticker_id='GOOGLx' "
                             "AND dev_vs_median_pct IS NOT NULL "
                             "ORDER BY ts DESC, id DESC LIMIT 1")[0]["dev_vs_median_pct"]
        check("history 1h last point == latest non-null dev GOOGLx",
              close(pts1[-1]["dev_bps"], last_nonnull * 100),
              f"hist={pts1[-1]['dev_bps']} db={last_nonnull * 100}")

    # Detail: re-read the DB row AFTER fetching, retry once on a cycle race.
    for _attempt in range(2):
        det = wcurl("/api/ticker?ticker=GOOGLx")
        row = query("SELECT depth_weighted_price, dev_vs_median_pct FROM deviations "
                    "WHERE ticker_id='GOOGLx' ORDER BY ts DESC, id DESC LIMIT 1")[0]
        if (close(det["dw_price"], row["depth_weighted_price"])
                and close(det["dev_pct"], row["dev_vs_median_pct"])):
            break
    check("ticker detail GOOGLx matches latest row",
          close(det["dw_price"], row["depth_weighted_price"])
          and close(det["dev_pct"], row["dev_vs_median_pct"]),
          f"dw={det['dw_price']} dev={det['dev_pct']} vs db dw={row['depth_weighted_price']} "
          f"dev={row['dev_vs_median_pct']}")

    print(f"\nSUMMARY: {len(FAILS)} FAIL, {len(WARNS)} WARN")
    if FAILS:
        print("FAILED:", ", ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
