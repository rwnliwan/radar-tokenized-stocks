#!/usr/bin/env python3
"""Forward test PAPER — Radar Tokenized Stocks (sprint, 2026-11-12).

Read-only against mainnet (DexScreener + Hyperliquid) and read-only
latest-only queries against Turso. NO trading, NO gas, NO real money,
NO writes to Turso. Every paper decision is appended to the LOCAL file
forward_paper_trades.json next to this script (never to Turso).

PRE-REGISTERED paper rules (sprint-scoped, written BEFORE the first
observation below — they are NOT the desain §5.4 alert-accuracy rules,
they are the paper-trade open/close rules for this sprint):
  OPEN  a paper "would-exit" when exit_score_v1 >= 70
        OR |dev_perp_vs_token_pct| >= 1.0%   (same 1.0% as DESAIN §2.1)
  CLOSE an open paper trade when, in a LATER observation,
        dev_vs_median_pct (fresh spot) < 0.5% AND exit_score < 40
        (mirrors the §5.4 "kembali < 0,5%" notion; both must hold).
  A trade that never meets the close rule inside the sprint window
  stays OPEN — it is reported as open, never silently closed and
  never scored as a win/loss.

WHAT THIS SPRINT IS (honest scope):
  * Sprint duration is MINUTES (3 observations ~4-5 min apart), NOT
    the 4 weeks DESAIN §5.2 requires. It proves the PIPE (live legs ->
    score -> paper record -> re-evaluation), not the accuracy of any
    signal. Accuracy needs >= 4 weekends of observations.
  * Monday Gap is NOT evaluated today: prediction fires only Sunday
    >= 22:00 UTC and outcome fill only Monday (poller.py
    run_weekly_monday_gap). Today is Thursday 2026-11-12. The script
    records monday_gap = not_due instead of inventing a prediction.
  * OI-change component of exit_score is NOT counted in this sprint:
    it needs perp_snapshots rows from 24h ago and that table does not
    exist live yet (migration 2026-11-12-penambahan.sql not applied —
    see FORWARD_TEST_2026-11-12.md). The score is honestly partial.
  * Spot leg is FRESH (live DexScreener batch, same aggregation as
    poller.run_cycle: LIQ_MIN filter + 25% cross-pool guard). The
    deviations leg in Turso is STALE since 2026-11-12T12:41:00Z
    (same migration failure); the script reads the latest deviations
    row only to REPORT the staleness, never as the live price.

Usage: python3 forward_paper.py [--observation]
  One run = one observation. Run it repeatedly (cron/manual) and the
  JSON ledger accumulates observations; open trades are re-evaluated
  on every run. Exit 0 = observation recorded.
"""

import json
import os
import statistics
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(BASE, "forward_paper_trades.json")
sys.path.insert(0, BASE)

import poller  # noqa: E402  (reuse pure fns + live fetchers; no writes)

UTC = timezone.utc

EXIT_OPEN = 70.0        # DESAIN §2.3 alert threshold
EXIT_CLOSE = 40.0       # sprint rule: clearly cooled down
PERP_OPEN_PCT = 1.0     # DESAIN §2.1
DEV_CLOSE_PCT = 0.5     # DESAIN §5.4 "kembali < 0,5%"


def _fresh_spot():
    """Live DexScreener batch -> {ticker: {dw, dev_vs_median_pct,
    depth_usd, pools_used}} — same aggregation as run_cycle."""
    pools = poller.query(
        "SELECT pool_id, ticker_id, chain, dex, pair_address, tier "
        "FROM pools JOIN universe USING (ticker_id) WHERE is_active = 1")
    uni = poller.query("SELECT ticker_id, token_addresses FROM universe")
    addr_by_ticker = {}
    for u in uni:
        try:
            addrs = json.loads(u["token_addresses"] or "{}")
        except Exception:
            addrs = {}
        if addrs:
            addr_by_ticker[u["ticker_id"]] = next(iter(addrs.values()))
    tickers = sorted({p["ticker_id"] for p in pools})
    batch = [addr_by_ticker[t] for t in tickers if t in addr_by_ticker]
    pairs, _code, err = poller.dex_fetch(poller.DEX.format(",".join(batch)))
    if err:
        raise RuntimeError(f"dexscreener fetch failed: {err}")
    by_pair = {p.get("pairAddress"): p for p in pairs}
    # Same fallback as run_cycle (S5): the batch answer is capped (~30
    # pairs) and routinely omits a few pools; fetch once per DISTINCT
    # missing token address instead of dropping those tickers.
    missing = [pl for pl in pools if pl["pair_address"] not in by_pair]
    lower = {k.lower(): v for k, v in by_pair.items()}
    for pl in missing:
        if pl["pair_address"].lower() in lower:
            by_pair[pl["pair_address"]] = lower[pl["pair_address"].lower()]
    still = [pl for pl in pools if pl["pair_address"] not in by_pair]
    fallback_addrs = {}
    for pl in still:
        a = addr_by_ticker.get(pl["ticker_id"])
        if a:
            fallback_addrs.setdefault(a, []).append(pl)
    fallback_used = 0
    for addr, _pls in fallback_addrs.items():
        tp, _c, _e = poller.dex_fetch(poller.DEX.format(addr))
        if _e:
            continue
        fallback_used += 1
        for p in tp:
            by_pair.setdefault(p.get("pairAddress"), p)
    per_ticker = {}
    for pl in pools:
        p = by_pair.get(pl["pair_address"])
        if not p:
            continue
        try:
            price = float(p["priceUsd"]) if p.get("priceUsd") else None
        except (TypeError, ValueError):
            price = None
        reserve = (p.get("liquidity") or {}).get("usd")
        if price is not None and reserve is not None \
                and reserve >= poller.LIQ_MIN:
            per_ticker.setdefault(pl["ticker_id"], []).append((price, reserve))
    out = {}
    for ticker, lst in per_ticker.items():
        kept, n_ex = lst, 0
        if len(lst) >= 3:
            med_all = statistics.median([pr for pr, _ in lst])
            if med_all:
                kept = [(pr, r) for pr, r in lst
                        if abs(pr - med_all) / med_all <= 0.25]
                n_ex = len(lst) - len(kept)
                if not kept:
                    kept, n_ex = lst, 0
        depth = sum(r for _, r in kept)
        dw = sum(pr * r for pr, r in kept) / depth if depth else None
        prices = [pr for pr, _ in kept]
        median = statistics.median(prices) if len(prices) >= 2 else None
        dev_med = ((dw - median) / median * 100.0) \
            if (median and dw) else None
        out[ticker] = {"dw": dw, "dev_vs_median_pct": dev_med,
                       "depth_usd": depth, "pools_used": len(kept),
                       "pools_excluded_guard": n_ex}
    return out, fallback_used


def observe():
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fresh spot leg (live DexScreener).
    spot, fallback_used = _fresh_spot()

    # Live perp leg (Hyperliquid xyz, read-only).
    perp_data, perp_err = poller.fetch_xyz_market_data()
    ctxs, _ctx_err = poller.fetch_xyz_ctxs()

    # Redemption status (1 latest-only row) + median depth from
    # state.json (computed by the poller today; 0 Turso reads).
    red_status, red_close_h = poller._latest_redemption_status(now)
    try:
        with open(os.path.join(BASE, "state.json")) as f:
            state = json.load(f)
    except Exception:
        state = {}
    median7d = state.get("median_depth_7d") or {}

    # Stale-leg report: latest deviations row per ticker (1 row each).
    stale = {}
    for t in sorted(spot):
        row = poller._latest_deviations_row(t, "2026-11-12T00:00:00Z")
        stale[t] = row.get("ts") if row else None

    tickers = {}
    for ticker in sorted(spot):
        s = spot[ticker]
        p = (perp_data or {}).get(ticker)
        perp_px = p.get("perp_px") if p else None
        funding = p.get("funding") if p else None
        dev_perp = ((perp_px - s["dw"]) / s["dw"] * 100.0
                    if (perp_px and s["dw"]) else None)
        # OI 24h-ago needs perp_snapshots (missing live) -> None ->
        # component not counted, never zero-filled (DESAIN §2.3).
        oi_chg = None
        if p and p.get("oi_usd") is not None:
            try:
                old = poller._oi_24h_ago(ticker, now)
                if old:
                    oi_chg = (p["oi_usd"] - old) / old * 100.0
            except Exception:
                oi_chg = None
        sc = poller.exit_score_v1(s["dev_vs_median_pct"], s["depth_usd"],
                                  median7d.get(ticker), red_status,
                                  red_close_h, funding, oi_chg)
        # Liquidation guard from live mark vs oracle.
        c = (ctxs or {}).get(ticker) or {}
        mark, oracle = c.get("mark_px"), c.get("oracle_px")
        div = (abs(mark - oracle) / oracle * 100.0
               if (mark and oracle) else None)
        liq = poller.liquidation_status(div, None, None)
        tickers[ticker] = {
            "dw_fresh": s["dw"],
            "dev_vs_median_pct": s["dev_vs_median_pct"],
            "depth_usd": s["depth_usd"],
            "pools_used": s["pools_used"],
            "perp_px": perp_px,
            "dev_perp_vs_token_pct": dev_perp,
            "funding": funding,
            "oi_change_24h_pct": oi_chg,
            "exit_score": sc["score_100"],
            "exit_components": sc["components"],
            "exit_components_present": sc["components_present"],
            "exit_partial": sc["partial"],
            "liq_divergence_pct": div,
            "liq_status": liq,
            "deviations_latest_ts": stale.get(ticker),
        }

    obs = {
        "ts": now_iso,
        "weekday": now.strftime("%A"),
        "dex_fallback_tokens": fallback_used,
        "perp_error": perp_err,
        "redemption_status": red_status,
        "median_depth_7d_date": state.get("median_depth_7d_date"),
        "monday_gap": {"status": "not_due",
                       "reason": "prediction fires Sunday >=22:00 UTC, "
                                 "outcome fill Monday; today is Thursday",
                       "next_due": "2026-11-15T22:00:00Z"},
        "tickers": tickers,
    }
    return obs


def load_ledger():
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            return json.load(f)
    return {"created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rules": {
                "open": "exit_score >= 70 OR |dev_perp_vs_token_pct| >= 1.0",
                "close": "later obs: dev_vs_median_pct < 0.5 AND exit_score < 40",
                "scope": "sprint minutes, NOT the 4-week forward test "
                         "(DESAIN §5.2); 0 closed in a minutes window is "
                         "expected, not a result"},
            "observations": [], "paper_trades": []}


def main():
    obs = observe()
    led = load_ledger()
    led["observations"].append(obs)

    opened, closed = [], []
    for ticker, t in obs["tickers"].items():
        reasons = []
        if t["exit_score"] is not None and t["exit_score"] >= EXIT_OPEN:
            reasons.append(f"exit_score {t['exit_score']} >= 70")
        if t["dev_perp_vs_token_pct"] is not None \
                and abs(t["dev_perp_vs_token_pct"]) >= PERP_OPEN_PCT:
            reasons.append(
                f"|dev_perp_vs_token| {t['dev_perp_vs_token_pct']:.3f}% >= 1.0%")
        already_open = any(tr["ticker"] == ticker
                           and tr["status"] == "open"
                           for tr in led["paper_trades"])
        if reasons and not already_open:
            tr = {"ticker": ticker, "status": "open",
                  "opened_ts": obs["ts"], "open_reason": "; ".join(reasons),
                  "open_exit_score": t["exit_score"],
                  "open_dev_perp_vs_token_pct": t["dev_perp_vs_token_pct"],
                  "open_dw": t["dw_fresh"], "open_perp_px": t["perp_px"],
                  "closed_ts": None, "close_reason": None,
                  "close_exit_score": None, "close_dev_vs_median_pct": None,
                  "close_dw": None, "outcome": None}
            led["paper_trades"].append(tr)
            opened.append(ticker)

    for tr in led["paper_trades"]:
        if tr["status"] != "open":
            continue
        t = obs["tickers"].get(tr["ticker"])
        if not t:
            continue
        if (t["dev_vs_median_pct"] is not None
                and abs(t["dev_vs_median_pct"]) < DEV_CLOSE_PCT
                and t["exit_score"] is not None
                and t["exit_score"] < EXIT_CLOSE):
            tr["status"] = "closed"
            tr["closed_ts"] = obs["ts"]
            tr["close_reason"] = (
                f"dev_vs_median {t['dev_vs_median_pct']:.3f}% < 0.5% and "
                f"exit_score {t['exit_score']} < 40")
            tr["close_exit_score"] = t["exit_score"]
            tr["close_dev_vs_median_pct"] = t["dev_vs_median_pct"]
            tr["close_dw"] = t["dw_fresh"]
            tr["outcome"] = "closed_in_window"
            closed.append(tr["ticker"])

    with open(LEDGER, "w") as f:
        json.dump(led, f, indent=2)

    n_open = sum(1 for tr in led["paper_trades"] if tr["status"] == "open")
    n_closed = sum(1 for tr in led["paper_trades"]
                   if tr["status"] == "closed")
    print(f"FORWARD-PAPER obs={obs['ts']} tickers={len(obs['tickers'])} "
          f"perp_err={obs['perp_error'] or '-'} "
          f"opened_now={opened or '-'} closed_now={closed or '-'} "
          f"total_open={n_open} total_closed={n_closed}")
    for ticker, t in sorted(obs["tickers"].items()):
        print(f"  {ticker}: dw={t['dw_fresh']:.2f} "
              f"dev_med={t['dev_vs_median_pct'] if t['dev_vs_median_pct'] is None else round(t['dev_vs_median_pct'], 3)} "
              f"perp={t['perp_px']} "
              f"dev_perp={t['dev_perp_vs_token_pct'] if t['dev_perp_vs_token_pct'] is None else round(t['dev_perp_vs_token_pct'], 3)} "
              f"exit={t['exit_score']} (partial={t['exit_partial']}, "
              f"n_comp={t['exit_components_present']}/5) "
              f"liq={t['liq_status']} dev_ts={t['deviations_latest_ts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
