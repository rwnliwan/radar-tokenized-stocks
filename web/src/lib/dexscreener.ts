/* DexScreener pair-page links, chain-aware (M11 fix ronde review
 * DeepSeek Radar 2026-11-13).
 *
 * The ticker page used to hardcode `dexscreener.com/solana/<pair>` for
 * every venue — 71/106 pools are not Solana, so 67% of the links
 * opened the wrong chain. The slug now comes from the pool's own
 * `chain` value (the DexScreener `chainId` stored in `pools.chain`).
 *
 * Slugs verified 13 Nov 2026:
 * - solana / base / bsc / ethereum / hyperliquid — DexScreener's own
 *   chain pages (dexscreener.com/<slug>/...).
 * - robinhood — DexScreener lists Robinhood Chain (chain id 4663);
 *   its chain page is dexscreener.com/robinhood (e.g. /gainers/robinhood).
 * - bnb is an alias: coverage rows spell the chain "bnb" while pool
 *   rows carry the DexScreener chainId "bsc" — both map to "bsc".
 *
 * Chains with NO DexScreener page (e.g. elysium — not live, 0 pools —
 * or any future unknown slug) return null: the caller renders "—"
 * instead of a wrong-chain link. Never guess a slug. */
const DEXSCREENER_CHAIN_SLUGS: Record<string, string> = {
  solana: "solana",
  base: "base",
  bsc: "bsc",
  bnb: "bsc",
  ethereum: "ethereum",
  hyperliquid: "hyperliquid",
  robinhood: "robinhood",
};

/** Pair-page URL for a pool, or null when the chain has no
 *  DexScreener page (or the pair address is missing). */
export function dexScreenerPairUrl(
  chain: string | null | undefined,
  pairAddress: string | null | undefined,
): string | null {
  if (!chain || !pairAddress) return null;
  const slug = DEXSCREENER_CHAIN_SLUGS[chain.trim().toLowerCase()];
  if (!slug) return null;
  return `https://dexscreener.com/${slug}/${pairAddress}`;
}
