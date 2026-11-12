#!/usr/bin/env python3
"""Cek mingguan Elysium + xStocks — read-only, API publik gratis.

Memeriksa apakah tokenized stocks xStocks sudah punya pool DEX di Elysium
(Kinetiq L2, chain 99901, mainnet 9 Nov 2026) dan apakah sudah lolos aturan
Radar (total likuiditas >= $500rb DAN >= 2 venue DEX DAN pool >= $100rb).

Sumber:
  - DexScreener public API (tanpa key): search per simbol xStocks, filter
    chainId == "elysium", plus token-pairs untuk alamat EVM TSLAx.
  - Hyperliquid public API (tanpa key): spotMeta + l2Book untuk wrapped
    xStocks (@702 NVDAX, @703 SPYX, @712 TSLAX, @713 AAPLX) sebagai konteks
    — book spot Hyperliquid BUKAN kaki Radar, hanya monitor.

Tidak menulis ke database apa pun, tidak memakai kredensial.
Menggunakan curl (bukan urllib) karena egress proxy merusak urllib
(konvensi repo radar-tokenized-stocks).

Penggunaan:  python3 check_elysium_weekly.py [--json]
Exit code: 0 bila cek berjalan sampai selesai (apa pun vonisnya),
           2 bila pengambilan data gagal.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

SEARCH = "https://api.dexscreener.com/latest/dex/search?q={}"
TOKEN_PAIRS = "https://api.dexscreener.com/latest/dex/tokens/{}"
HL_INFO = "https://api.hyperliquid.xyz/info"

# Simbol xStocks yang dicari di Elysium (13 ticker universe Radar Solana).
XSTOCK_SYMBOLS = [
    "TSLAx", "NVDAx", "AAPLx", "MSFTx", "METAx", "GOOGLx",
    "MSTRx", "SPYx", "QQQx", "CRCLx", "HOODx", "COINx", "GLDx",
]
# Alamat EVM TSLAx (dipakai semua chain EVM incl. Elysium bila ada).
TSLAX_EVM = "0x8aD3c73F833d3F9A523aB01476625F269aEB7Cf0"
# Wrapped xStocks di Hyperliquid spot (coin -> label).
HL_SPOT = {"@702": "NVDAX", "@703": "SPYX", "@712": "TSLAX", "@713": "AAPLX"}

MIN_TOTAL_LIQ = 500_000
MIN_POOL_LIQ = 100_000
MIN_VENUES = 2


def curl_json(url, post_data=None):
    cmd = ["curl", "-s", "--max-time", "30"]
    if post_data is not None:
        cmd += ["-X", "POST", "-H", "Content-Type: application/json",
                "-d", json.dumps(post_data)]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl gagal untuk {url}: {r.stderr[:200]}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"respons bukan JSON dari {url}: {r.stdout[:200]}")


def check_elysium():
    """Return (per_symbol, total_pairs, total_liq, venues, biggest_pool)."""
    per_symbol = {}
    for sym in XSTOCK_SYMBOLS:
        data = curl_json(SEARCH.format(sym))
        pairs = [p for p in (data.get("pairs") or [])
                 if p.get("chainId") == "elysium"
                 and (p.get("baseToken") or {}).get("symbol") == sym]
        tot = sum((p.get("liquidity") or {}).get("usd") or 0 for p in pairs)
        per_symbol[sym] = {"pairs": len(pairs), "total_liq": round(tot, 2)}
        time.sleep(0.3)
    # Cross-check via token-pairs untuk alamat EVM TSLAx.
    data = curl_json(TOKEN_PAIRS.format(TSLAX_EVM))
    evm_elysium = [p for p in (data.get("pairs") or [])
                   if p.get("chainId") == "elysium"]
    all_pairs = []
    for sym in XSTOCK_SYMBOLS:
        data = curl_json(SEARCH.format(sym))
        all_pairs += [p for p in (data.get("pairs") or [])
                      if p.get("chainId") == "elysium"
                      and (p.get("baseToken") or {}).get("symbol") == sym]
        time.sleep(0.2)
    total_liq = sum((p.get("liquidity") or {}).get("usd") or 0 for p in all_pairs)
    n_with_liq = sum(1 for p in all_pairs
                     if ((p.get("liquidity") or {}).get("usd") or 0) > 0)
    venues = {p.get("dexId") for p in all_pairs
              if ((p.get("liquidity") or {}).get("usd") or 0) > 0}
    qualifying = [p for p in all_pairs
                  if ((p.get("liquidity") or {}).get("usd") or 0) >= MIN_POOL_LIQ]
    biggest = None
    for p in all_pairs:
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if biggest is None or liq > biggest["liq"]:
            biggest = {"dex": p.get("dexId"), "pair": p.get("pairAddress"),
                       "symbol": (p.get("baseToken") or {}).get("symbol"),
                       "liq": round(liq, 2),
                       "vol24": round((p.get("volume") or {}).get("h24") or 0, 2)}
    return {
        "per_symbol": per_symbol,
        "n_pairs": len(all_pairs),
        "n_pairs_with_liquidity": n_with_liq,
        "total_liq": round(total_liq, 2),
        "venues": sorted(venues),
        "n_venues": len(venues),
        "n_pools_ge_100k": len(qualifying),
        "biggest_pool": biggest,
        "evm_tslax_elysium_pairs": len(evm_elysium),
    }


def check_hyperliquid_spot():
    """Book spot wrapped xStocks: ada/tidak, ada ask atau tidak, harga wajar?"""
    out = {}
    for coin, label in HL_SPOT.items():
        try:
            book = curl_json(HL_INFO, {"type": "l2Book", "coin": coin})
            bids, asks = book.get("levels", [[], []])
            best_bid = bids[0] if bids else None
            best_ask = asks[0] if asks else None
            out[coin] = {
                "label": label,
                "has_bids": bool(bids),
                "has_asks": bool(asks),
                "best_bid": best_bid,
                "best_ask": best_ask,
            }
        except Exception as e:  # noqa: BLE001 - satu coin gagal != cek gagal
            out[coin] = {"label": label, "error": str(e)[:120]}
        time.sleep(0.2)
    return out


def verdict(elysium):
    # "Belum aktif" = tidak ada satu pun pair berlikuiditas (pair $0 tidak
    # dihitung sebagai pasar hidup — terbukti 12 Nov 2026: 1 pair GOOGLx
    # di Elysium tapi liq $0, harga absurd).
    if elysium["n_pairs_with_liquidity"] == 0:
        return "belum aktif"
    if (elysium["total_liq"] >= MIN_TOTAL_LIQ
            and elysium["n_venues"] >= MIN_VENUES
            and elysium["n_pools_ge_100k"] >= 1):
        return "aktif — lolos aturan"
    return "aktif — belum lolos"


def main():
    as_json = "--json" in sys.argv
    now = datetime.now(timezone.utc)
    try:
        elysium = check_elysium()
        hl = check_hyperliquid_spot()
    except Exception as e:  # noqa: BLE001 - laporkan gagal ambil data
        print(f"GAGAL ambil data: {e}", file=sys.stderr)
        return 2
    v = verdict(elysium)
    result = {
        "checked_at_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
        "checked_at_wita": (now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
                            + " UTC (tambah 8 jam = WITA)"),
        "elysium": elysium,
        "hyperliquid_spot_books": hl,
        "verdict": v,
    }
    if as_json:
        print(json.dumps(result, indent=1))
        return 0
    print(f"Cek mingguan Elysium + xStocks — {now.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"Elysium: {elysium['n_pairs']} pair xStocks "
          f"({elysium['n_pairs_with_liquidity']} berlikuiditas), "
          f"total likuiditas ${elysium['total_liq']:,.0f}, "
          f"venue: {elysium['n_venues']} {elysium['venues'] or '-'}")
    for sym, info in elysium["per_symbol"].items():
        if info["pairs"]:
            print(f"  {sym}: {info['pairs']} pair, ${info['total_liq']:,.0f}")
    bp = elysium["biggest_pool"]
    if bp:
        print(f"Pool terbesar: {bp['symbol']} di {bp['dex']} "
              f"({bp['pair']}) liq ${bp['liq']:,.0f} vol24 ${bp['vol24']:,.0f}")
    else:
        print("Pool terbesar: - (tidak ada pool)")
    print(f"Cross-check token-pairs TSLAx EVM: "
          f"{elysium['evm_tslax_elysium_pairs']} pair di Elysium")
    print("Hyperliquid spot (wrapped xStocks, konteks saja — bukan kaki Radar):")
    for coin, b in hl.items():
        if "error" in b:
            print(f"  {coin} {b['label']}: ERROR {b['error']}")
        else:
            bb = b["best_bid"]["px"] if b["best_bid"] else "-"
            ba = b["best_ask"]["px"] if b["best_ask"] else "- (TIDAK ADA ASK)"
            print(f"  {coin} {b['label']}: bid terbaik {bb}, ask terbaik {ba}")
    print(f"VONIS: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
