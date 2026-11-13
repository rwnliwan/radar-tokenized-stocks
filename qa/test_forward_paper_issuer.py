#!/usr/bin/env python3
"""QA: forward_paper.py resolves redemption status PER ISSUER (M4 fix).

Regression test for the fix-round change of poller._latest_redemption_status
(now requires `issuer`): forward_paper.observe() used to call it once with a
single shared status for ALL tickers (the M4 leak, class). It must now
resolve per ticker's own issuer (cached per distinct issuer) and record
redemption_status_by_issuer in the observation.

All live legs are stubbed; no network, no Turso, no ledger writes.
Run: python3 qa/test_forward_paper_issuer.py
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import poller  # noqa: E402
import forward_paper as fp  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not cond else ""))


def main():
    # --- stubs ---
    universe = [
        {"ticker_id": "TSLAx", "issuer": "xStocks"},
        {"ticker_id": "TSLAc", "issuer": "coinbase"},
        {"ticker_id": "TSLAB", "issuer": "bstocks"},
    ]
    red_calls = []

    def fake_query(sql):
        assert "FROM universe" in sql, sql
        return universe

    def fake_red_status(now, issuer):
        red_calls.append(issuer)
        return {"xStocks": ("open", 100.0),
                "coinbase": ("unknown", None),
                "bstocks": ("closed", 65.0)}[issuer]

    spot = {
        "TSLAx": {"dw": 100.0, "dev_vs_median_pct": 0.5,
                  "depth_usd": 600000.0, "pools_used": 3},
        "TSLAc": {"dw": 100.0, "dev_vs_median_pct": 0.5,
                  "depth_usd": 600000.0, "pools_used": 3},
        "TSLAB": {"dw": 100.0, "dev_vs_median_pct": 0.5,
                  "depth_usd": 600000.0, "pools_used": 3},
        # Ticker in spot but NOT in universe -> unknown issuer.
        "ORPHANx": {"dw": 100.0, "dev_vs_median_pct": 0.5,
                    "depth_usd": 600000.0, "pools_used": 3},
    }

    poller.query = fake_query
    poller._latest_redemption_status = fake_red_status
    fp._fresh_spot = lambda: (spot, 0)
    poller.fetch_xyz_market_data = lambda: ({}, None)
    poller.fetch_xyz_ctxs = lambda: ({}, None)
    poller._latest_deviations_row = lambda t, *a: None

    obs = fp.observe()

    check("redemption resolved once per distinct issuer (not per ticker, "
          "not once total)",
          sorted(red_calls) == ["bstocks", "coinbase", "xStocks"],
          f"calls={red_calls}")
    check("obs records per-issuer map, no single shared status",
          obs.get("redemption_status_by_issuer") ==
          {"bstocks": "closed", "coinbase": "unknown", "xStocks": "open"}
          and "redemption_status" not in obs,
          f"map={obs.get('redemption_status_by_issuer')}")
    t = obs["tickers"]
    check("TSLAB uses its own issuer status (closed 65h -> redemption 10)",
          t["TSLAB"]["exit_components"]["redemption"] == 10.0,
          f"got={t['TSLAB']['exit_components'].get('redemption')}")
    check("TSLAx uses xStocks status (open, close 100h away -> redemption 0)",
          t["TSLAx"]["exit_components"]["redemption"] == 0.0,
          f"got={t['TSLAx']['exit_components'].get('redemption')}")
    check("TSLAc uses coinbase status (unknown -> redemption None, partial)",
          t["TSLAc"]["exit_components"]["redemption"] is None
          and t["TSLAc"]["exit_partial"] is True,
          f"got={t['TSLAc']['exit_components'].get('redemption')}")
    check("unknown-issuer ticker falls back to (None, None), no crash",
          t["ORPHANx"]["exit_components"]["redemption"] is None
          and t["ORPHANx"]["exit_partial"] is True,
          f"got={t['ORPHANx']['exit_components'].get('redemption')}")

    failed = [c for c in CHECKS if not c[1]]
    print(f"\nSUMMARY: {len(failed)} FAIL — "
          f"{'FORWARD-PAPER ISSUER TEST: PASS' if not failed else 'FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
