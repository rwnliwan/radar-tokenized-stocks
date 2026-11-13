// M11 (fix ronde review DeepSeek Radar): DexScreener pair links must
// be chain-aware — the old code hardcoded dexscreener.com/solana/ for
// every pool (71/106 pools are not Solana). Tests the mapping in
// web/src/lib/dexscreener.ts against sample pools for every chain the
// Radar seeds or displays, plus the no-link fallbacks.
//
// Usage: node qa/test_dexscreener_links.mjs  (exit 0 = PASS)
// Requires Node >= 22.18 (type stripping imports dexscreener.ts directly).
import { dexScreenerPairUrl } from "../web/src/lib/dexscreener.ts";

const FAILURES = [];
function check(name, ok, detail = "") {
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? ` — ${detail}` : ""));
  if (!ok) FAILURES.push(name);
}

const PAIR = "0xAbC1230000000000000000000000000000000000";
// [chain as stored in pools.chain, expected URL slug or null]
const CASES = [
  ["solana", "solana"], // xStocks (legacy)
  ["base", "base"], // Coinbase
  ["bsc", "bsc"], // bStocks (DexScreener chainId)
  ["bnb", "bsc"], // alias: coverage rows spell it "bnb"
  ["robinhood", "robinhood"], // Robinhood Chain (id 4663, listed by DexScreener)
  ["ethereum", "ethereum"],
  ["hyperliquid", "hyperliquid"],
  ["SOLANA", "solana"], // case-insensitive
  ["Base", "base"],
  ["elysium", null], // no DexScreener page — must NOT link anywhere
  ["unknown-chain", null], // future chain — no guessed slug, no link
  [null, null],
  ["", null],
];

for (const [chain, slug] of CASES) {
  const got = dexScreenerPairUrl(chain, PAIR);
  const want = slug ? `https://dexscreener.com/${slug}/${PAIR}` : null;
  check(`dexScreenerPairUrl(${JSON.stringify(chain)})`, got === want, `got ${got}`);
}

// No pair address → no link, whatever the chain.
check(
  "missing pair_address → null",
  dexScreenerPairUrl("solana", null) === null &&
    dexScreenerPairUrl("solana", "") === null,
);

// Old bug, locked: a Base pool must NEVER get a /solana/ URL.
check(
  "no /solana/ URL for a non-Solana pool",
  !String(dexScreenerPairUrl("base", PAIR)).includes("/solana/") &&
    !String(dexScreenerPairUrl("bsc", PAIR)).includes("/solana/") &&
    !String(dexScreenerPairUrl("robinhood", PAIR)).includes("/solana/"),
);

if (FAILURES.length) {
  console.error(`\n${FAILURES.length} FAILURE(S): ${FAILURES.join(", ")}`);
  process.exit(1);
}
console.log(`\nAll ${CASES.length + 2} link cases PASS (web/src/lib/dexscreener.ts).`);
