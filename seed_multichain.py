"""Seed multichain universe + pools from verify_multichain_out.json.

Reads the LIVE verification output of verify_multichain.py and builds the
INSERTs for the three new issuer groups (Coinbase/Base, bStocks/BNB,
Robinhood/Robinhood Chain). Follows seed_universe.py (Solana xStocks)
conventions, EXCEPT the write pattern: UPSERT, never DELETE (fix
ronde review DeepSeek Radar 2026-11-13, M9 — the old DELETE-then-
INSERT per ticker wiped/orphaned history on every weekly re-seed).
Only pools with liquidity >= $100,000 at verification time are
tracked (design §5.2).

Rules (design §1.1/§1.3, DESAIN_PENAMBAHAN_2026-11-12 §1.2):
- Only tickers with tier 1 or 2 (total >= $500k + >= 2 venues).
- At most CAP_PER_ISSUER tickers per issuer (default 13, the ACC'd cap),
  ranked by total liquidity at verification time. Tickers that pass the
  rule but fall outside the cap are listed as CAP-EXCLUDED, not seeded.
- A pool is seeded only if it is TRACKABLE: liquidity >= $100k AND the
  venue is a NAMED dex (dexId starting "0x" is an unnamed contract, not
  a verified venue — same lesson as communityV3) AND the quote token is
  not the base token itself (quote == symbol means an ambiguous /
  copycat quote; priceUsd cannot be trusted). Dropped pools are listed
  in the dry-run summary, not silently dropped.
- Ticker IDs: Coinbase keeps its DexScreener symbol (NVDAc), bStocks
  keeps its symbol (TSLAB), Robinhood takes its plain symbol + "r"
  (TSLAr) — the "r" suffix is a PROPOSAL (design doc fixes "c" and "B"
  but no Robinhood suffix); confirm before first live seed.
- Redemption / PoR rows are DOCUMENTATION, not live observation
  (design §3.5): all three issuers get status "unknown" with a note of
  the documented mechanism. No PoR feed is claimed for any of them.

UPSERT semantics (M9):
- universe / pools: INSERT ... ON CONFLICT DO UPDATE (created_at is
  preserved on conflict; a re-seeded ticker is re-activated, never
  re-created). NOT INSERT OR REPLACE — REPLACE deletes the conflicting
  row first, which is the history loss this fix removes.
- A ticker of a seed-managed issuer (coinbase/bstocks/robinhood) that
  is absent from the new seed is marked status='inactive' (NOT
  deleted); its pools get is_active=0. History rows (deviations,
  snapshots) keep pointing at the ticker.
- redemption_windows: UPDATE the existing (issuer, 'ALL') row if
  present, else INSERT ... WHERE NOT EXISTS; an issuer that drops
  out of the seed gets status='inactive' with its observed_at
  UNTOUCHED (so it never becomes the "latest" row for the poller's
  global latest-redemption read) and the marking time written into
  the note text instead. Only the three seed-managed issuers are
  ever touched — xStocks rows are owned by seed_universe.py/poller.

SAFETY: --dry-run is the DEFAULT. It prints the SQL + summary and writes
nothing to Turso. --live executes via turso_client.pipeline ONLY when the
environment variable RADAR_SEED_CONFIRM is set to the exact value
"ACC-2026-11-12" (Septian's ACC for this seed, dated). Without it, --live
refuses. Never run --live without that ACC.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, '.')

LIQ_MIN = 100000.0
CAP_PER_ISSUER = 13
LIVE_CONFIRM = "ACC-2026-11-12"

ISSUER_META = {
    "coinbase": {
        "chain": "base",
        "redemption_note": (
            "Documented (riset 12 Nov): mint/redeem in-kind near-instant "
            "for authorised participants only; retail via secondary "
            "market. No public PoR found — backing via Alpaca custody + "
            "Chainlink price feeds (UNVERIFIED beyond that)."),
        # S13: EN twin of redemption_note (window_note_en) — direct
        # translation, no status invented beyond the ID note.
        "redemption_note_en": (
            "Documented (research 12 Nov): mint/redeem in-kind "
            "near-instant for authorised participants only; retail via "
            "secondary market. No public PoR found — backing via Alpaca "
            "custody + Chainlink price feeds (UNVERIFIED beyond that)."),
        "por_note": "unknown — no public PoR found (riset 12 Nov 2026).",
    },
    "bstocks": {
        "chain": "bsc",
        "redemption_note": (
            "Documented (riset 12 Nov): convert Binance brokerage share "
            "<-> bStock 1:1, zero fee, <1s (eligible users); on-chain "
            "mint/burn on deposit/redemption. Attestation published "
            "(detail UNVERIFIED)."),
        "redemption_note_en": (
            "Documented (research 12 Nov): convert Binance brokerage "
            "share <-> bStock 1:1, zero fee, <1s (eligible users); "
            "on-chain mint/burn on deposit/redemption. Attestation "
            "published (detail UNVERIFIED)."),
        "por_note": ("unknown — attestation published per tracker "
                     "(detail UNVERIFIED); no live PoR feed checked."),
    },
    "robinhood": {
        "chain": "robinhood",
        "redemption_note": (
            "Documented (riset 12 Nov): redeemable for cash via "
            "authorised participants; redemption in underlying securities "
            "is roadmap / future date. No public PoR found."),
        "redemption_note_en": (
            "Documented (research 12 Nov): redeemable for cash via "
            "authorised participants; redemption in underlying "
            "securities is roadmap / future date. No public PoR found."),
        "por_note": "unknown — no public PoR found (riset 12 Nov 2026).",
    },
}


def trackable_pools(candidate, max_pools=None):
    """Pools worth tracking: >= LIQ_MIN, named dex, quote != base symbol."""
    clean, dropped = [], []
    for p in candidate.get("pools", []):
        if p["liquidity_usd"] < LIQ_MIN:
            continue
        if (p["dex"] or "").startswith("0x"):
            dropped.append((p, "unnamed venue (dexId is a raw address)"))
            continue
        if p["quote"] == candidate["symbol"]:
            dropped.append((p, "quote token == base symbol (ambiguous)"))
            continue
        clean.append(p)
    clean.sort(key=lambda x: x["liquidity_usd"], reverse=True)
    if max_pools is not None and len(clean) > max_pools:
        dropped += [(p, f"beyond --max-pools-per-ticker {max_pools}")
                    for p in clean[max_pools:]]
        clean = clean[:max_pools]
    return clean, dropped


def build_statements(data, max_pools=None):
    """Return (statements, report) from verify_multichain_out.json data."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    verified_at = data.get("verified_at_utc", "?")
    by_issuer = {}
    for c in data.get("candidates", []):
        if c.get("tier") in (1, 2):
            by_issuer.setdefault(c["issuer"], []).append(c)
    stmts = []
    report = {"seeded": [], "cap_excluded": [], "failed": [],
              "dropped_pools": [], "issuers": sorted(by_issuer),
              "inactive_issuers": []}
    seeded_tickers, seeded_pool_ids = [], []
    for issuer, cands in sorted(by_issuer.items()):
        cands.sort(key=lambda x: -x["total_liquidity_usd"])
        for c in cands[:CAP_PER_ISSUER]:
            sym = c["ticker_id"]
            chain = ISSUER_META[issuer]["chain"]
            token_json = json.dumps({chain: c["token_address"]})
            notes = (
                f"Live-verified {verified_at[:10]} via DexScreener "
                f"(verify_multichain.py): total_liq="
                f"${c['total_liquidity_usd']:,.0f}, "
                f"venues={c['venues']} (named {c.get('named_venues', '?')}), "
                f"token={c.get('token_name')}."
            )
            if c.get("truncated"):
                notes += (" NOTE: token-pairs hit the 30-pair API cap — "
                          "total is a lower bound.")
            seeded_tickers.append(sym)
            # M9: UPSERT, never DELETE. On conflict the row is updated
            # in place (status back to 'active', notes refreshed);
            # created_at is preserved, so history keeps its anchor.
            stmts.append((
                "INSERT INTO universe (ticker_id, underlying, issuer, "
                "legal_type, tier, status, token_addresses, notes, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(ticker_id) DO UPDATE SET "
                "underlying=excluded.underlying, "
                "issuer=excluded.issuer, legal_type=excluded.legal_type, "
                "tier=excluded.tier, status='active', "
                "token_addresses=excluded.token_addresses, "
                "notes=excluded.notes, updated_at=excluded.updated_at",
                [sym, c["underlying"], issuer, "wrapper", c["tier"],
                 "active", token_json, notes, now, now],
            ))
            clean, dropped = trackable_pools(c, max_pools)
            for p in dropped:
                report["dropped_pools"].append(
                    (sym, p[0]["dex"], p[0]["pair_address"],
                     round(p[0]["liquidity_usd"]), p[1]))
            n_pools = 0
            for p in clean:
                pool_id = f"{p['chain']}:{p['pair_address']}"
                seeded_pool_ids.append(pool_id)
                # M9: UPSERT; a pool that returns to the seed is
                # re-activated (is_active=1), never re-created.
                stmts.append((
                    "INSERT INTO pools (pool_id, ticker_id, chain, dex, "
                    "pair_address, quote_token, is_active, "
                    "min_liquidity_usd) VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(pool_id) DO UPDATE SET "
                    "ticker_id=excluded.ticker_id, chain=excluded.chain, "
                    "dex=excluded.dex, "
                    "pair_address=excluded.pair_address, "
                    "quote_token=excluded.quote_token, is_active=1, "
                    "min_liquidity_usd=excluded.min_liquidity_usd",
                    [pool_id, sym, p["chain"], p["dex"], p["pair_address"],
                     p["quote"], 1, LIQ_MIN],
                ))
                n_pools += 1
            report["seeded"].append(
                (sym, issuer, c["tier"], round(c["total_liquidity_usd"]),
                 c["venues"], n_pools,
                 round(sum(p["liquidity_usd"] for p in clean))))
        for c in cands[CAP_PER_ISSUER:]:
            report["cap_excluded"].append(
                (c["ticker_id"], issuer, c["tier"],
                 round(c["total_liquidity_usd"]),
                 "passes rule but outside top-13 cap for issuer"))
    for c in data.get("candidates", []):
        if not c.get("tier"):
            report["failed"].append(
                (c.get("ticker_id") or c["symbol"], c.get("issuer", "?"),
                 "; ".join(c.get("fail_reasons",
                                 [c.get("reason", "?")]))))
    # M9: tickers / pools of the three seed-managed issuers that are
    # NOT in this seed are deactivated, never deleted — history rows
    # (deviations, snapshots) keep pointing at them. Only emitted
    # when this seed actually seeded something: an empty seed (total
    # verification failure) must not mass-deactivate on its own.
    if seeded_tickers:
        tick_ph = ",".join("?" for _ in seeded_tickers)
        stmts.append((
            "UPDATE universe SET status='inactive', updated_at=? "
            "WHERE issuer IN ('coinbase','bstocks','robinhood') "
            f"AND ticker_id NOT IN ({tick_ph}) AND status <> 'inactive'",
            [now] + seeded_tickers,
        ))
    if seeded_pool_ids:
        pool_ph = ",".join("?" for _ in seeded_pool_ids)
        stmts.append((
            "UPDATE pools SET is_active=0 "
            f"WHERE pool_id NOT IN ({pool_ph}) AND ticker_id IN "
            "(SELECT ticker_id FROM universe "
            "WHERE issuer IN ('coinbase','bstocks','robinhood'))",
            seeded_pool_ids,
        ))
    # Documented (not live-observed) redemption + PoR rows per new issuer.
    for issuer in sorted(by_issuer):
        meta = ISSUER_META[issuer]
        # M9: UPDATE the existing (issuer, 'ALL') row if present,
        # INSERT only if absent — the old DELETE+INSERT destroyed the
        # row's history on every re-seed. S13: window_note_en included.
        stmts.append((
            "UPDATE redemption_windows SET status=?, window_note=?, "
            "window_note_en=?, observed_at=?, source=?, next_open_at=? "
            "WHERE issuer=? AND asset='ALL'",
            ["unknown", meta["redemption_note"],
             meta["redemption_note_en"], now,
             "DESAIN §3.5 / riset 12 Nov (dokumentasi, bukan observasi live)",
             None, issuer],
        ))
        stmts.append((
            "INSERT INTO redemption_windows (issuer, asset, status, "
            "window_note, window_note_en, observed_at, source, "
            "next_open_at) SELECT ?, 'ALL', ?, ?, ?, ?, ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM redemption_windows "
            "WHERE issuer=? AND asset='ALL')",
            [issuer, "unknown", meta["redemption_note"],
             meta["redemption_note_en"], now,
             "DESAIN §3.5 / riset 12 Nov (dokumentasi, bukan observasi live)",
             None, issuer],
        ))
        stmts.append((
            "INSERT INTO por_feeds (issuer, feed_address, last_update_ts, "
            "age_hours, reserves_vs_supply_note, checked_at) "
            "VALUES (?,?,?,?,?,?)",
            [issuer, None, None, None, meta["por_note"], now],
        ))
    # M9: a seed-managed issuer that drops out of this seed entirely
    # gets its redemption row marked inactive — NOT deleted. Its
    # observed_at is deliberately UNTOUCHED so the row never becomes
    # the "latest" row for the poller's global latest-redemption
    # read; the marking time goes into the note text instead.
    for issuer in sorted(set(ISSUER_META) - set(by_issuer)):
        report["inactive_issuers"].append(issuer)
        stmts.append((
            "UPDATE redemption_windows SET status='inactive', "
            "window_note=?, window_note_en=? "
            "WHERE issuer=? AND asset='ALL' AND status <> 'inactive'",
            [f"Issuer tidak lagi masuk seed multichain "
             f"(ditandai inactive {now}); baris dipertahankan untuk riwayat.",
             f"Issuer no longer in the multichain seed "
             f"(marked inactive {now}); row retained for history.",
             issuer],
        ))
    return stmts, report


def render_sql(stmts):
    """Render (sql, args) pairs as readable SQL with literal values."""
    def lit(v):
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return repr(v)
        return "'" + str(v).replace("'", "''") + "'"
    lines = ["-- seed_multichain.py --dry-run output",
             "-- NO statements were executed. Review, then run with --live",
             "-- only after Septian's ACC (see module docstring).", ""]
    for sql, args in stmts:
        out, i = [], 0
        for ch in sql:
            if ch == "?" and args is not None and i < len(args):
                out.append(lit(args[i]))
                i += 1
            else:
                out.append(ch)
        lines.append("".join(out) + ";")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", default="verify_multichain_out.json",
                    help="verify_multichain.py output JSON "
                         "(default: %(default)s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print SQL + summary, write nothing (default)")
    ap.add_argument("--live", action="store_true",
                    help="execute against Turso (requires "
                         "RADAR_SEED_CONFIRM=ACC-2026-11-12 in env)")
    ap.add_argument("--max-pools-per-ticker", type=int, default=None,
                    help="cap tracked pools per ticker (default: all "
                         "trackable >= $100k pools)")
    args = ap.parse_args()
    with open(args.input) as f:
        data = json.load(f)
    stmts, report = build_statements(data, args.max_pools_per_ticker)
    n_tickers = len(report["seeded"])
    n_pools = sum(r[5] for r in report["seeded"])
    print(f"verified_at: {data.get('verified_at_utc', '?')}")
    print(f"tickers to seed: {n_tickers} "
          f"({len(report['cap_excluded'])} cap-excluded, "
          f"{len(report['failed'])} failed rule)")
    print(f"pools to track: {n_pools} "
          f"({len(report['dropped_pools'])} >= $100k pools dropped: "
          "unnamed venue / ambiguous quote / over cap)")
    for sym, issuer, tier, tot, venues, npl, qd in report["seeded"]:
        print(f"  SEED {sym:8s} {issuer:10s} T{tier} "
              f"total=${tot:>12,} venues={venues} "
              f"pools={npl} qualDepth=${qd:,}")
    for sym, issuer, tier, tot, why in report["cap_excluded"]:
        print(f"  CAP-EXCLUDE {sym:8s} {issuer:10s} T{tier} "
              f"total=${tot:>12,} — {why}")
    for issuer in report["inactive_issuers"]:
        print(f"  INACTIVE-ISSUER {issuer}: no longer in this seed — "
              f"its redemption_windows row will be marked "
              f"status='inactive' (not deleted)")
    if n_tickers:
        print(f"  DEACTIVATE: managed-issuer tickers/pools absent from "
              f"this seed will be marked inactive (not deleted)")
    for sym, dex, pair, liq, why in report["dropped_pools"]:
        print(f"  DROP-POOL {sym:8s} {dex} {pair[:12]}… "
              f"${liq:>10,} — {why}")
    if args.live:
        if os.environ.get("RADAR_SEED_CONFIRM") != LIVE_CONFIRM:
            print("REFUSED: --live requires RADAR_SEED_CONFIRM="
                  f"{LIVE_CONFIRM} in the environment (Septian's ACC). "
                  "Nothing was written.", file=sys.stderr)
            sys.exit(2)
        from turso_client import pipeline, query
        pipeline(stmts)
        print("seeded OK (live)")
        print("universe:", query(
            "SELECT ticker_id, issuer, tier, status FROM universe "
            "WHERE issuer IN ('coinbase','bstocks','robinhood') "
            "ORDER BY issuer, ticker_id"))
        print("pools:", query(
            "SELECT COUNT(*) AS n FROM pools WHERE ticker_id IN "
            "(SELECT ticker_id FROM universe WHERE issuer IN "
            "('coinbase','bstocks','robinhood'))")[0])
    else:
        print()
        print(render_sql(stmts))


if __name__ == "__main__":
    main()
