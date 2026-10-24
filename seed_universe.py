"""Seed universe + pools from verify_universe_out.json (live-checked).

Rules (design §1.1/§1.3, §5.2):
- Only tickers with tier 1 or 2 (passed >=$500k total + >=2 venues).
- Only pools with liquidity >= $100,000 at verification time are tracked
  (the §5.2 alert-qualifying threshold). This keeps snapshots within the
  §2.2 write budget; sub-threshold pairs are listed in
  universe_excluded.md, not silently dropped.
- Idempotent: DELETEs existing universe/pools rows for the seeded tickers
  first, then re-inserts (safe to re-run after a re-verification).
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, '.')
from turso_client import pipeline, query

LIQ_MIN = 100000.0
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

out = json.load(open("verify_universe_out.json"))
passing = [c for c in out["candidates"] if c.get("tier") in (1, 2)]
print(f"passing tickers: {len(passing)}")

stmts = []
for c in passing:
    sym = c["symbol"]
    underlying = sym[:-1] if sym.endswith("x") else sym
    token_json = json.dumps({"solana": c["token_address"]})
    notes = (
        f"Live-verified {NOW[:10]} via DexScreener search: "
        f"total_liq=${c['total_liquidity_usd']:,.0f}, venues={c['venues']}, "
        f"token={c['token_name']}."
    )
    stmts.append(("DELETE FROM pools WHERE ticker_id = ?", [sym]))
    stmts.append(("DELETE FROM universe WHERE ticker_id = ?", [sym]))
    stmts.append((
        "INSERT INTO universe (ticker_id, underlying, issuer, legal_type,"
        " tier, status, token_addresses, notes, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        [sym, underlying, "xStocks", "wrapper", c["tier"], "active",
         token_json, notes, NOW, NOW],
    ))
    n_pools = 0
    for p in c["pools"]:
        if p["liquidity_usd"] < LIQ_MIN:
            continue
        pool_id = f"{p['chain']}:{p['pair_address']}"
        stmts.append((
            "INSERT INTO pools (pool_id, ticker_id, chain, dex, pair_address,"
            " quote_token, is_active, min_liquidity_usd) VALUES (?,?,?,?,?,?,?,?)",
            [pool_id, sym, p["chain"], p["dex"], p["pair_address"],
             p["quote"], 1, LIQ_MIN],
        ))
        n_pools += 1
    print(f"  {sym} tier {c['tier']}: {n_pools} tracked pools")

# Documented (not live-observed) redemption baseline for xStocks.
stmts.append(("DELETE FROM redemption_windows WHERE issuer = 'xStocks'", None))
stmts.append((
    "INSERT INTO redemption_windows (issuer, asset, status, window_note,"
    " observed_at, source, next_open_at) VALUES (?,?,?,?,?,?,?)",
    ["xStocks", "ALL", "unknown",
     "Documented schedule (research 24 Okt): xStocks redemption 5 days/week,"
     " KYC-gated; per-asset live status NOT yet observed by an automated"
     " source. This row is documentation, not a live observation.",
     NOW, "DESAIN §1.1 / riset 24 Okt (dokumentasi, bukan observasi live)",
     None],
))
pipeline(stmts)
print("seeded OK")
print("universe:", query("SELECT ticker_id, tier, status FROM universe ORDER BY tier, ticker_id"))
print("pools:", query("SELECT COUNT(*) AS n FROM pools")[0])
print("pools by ticker:", query(
    "SELECT ticker_id, COUNT(*) AS n FROM pools GROUP BY ticker_id ORDER BY ticker_id"))
