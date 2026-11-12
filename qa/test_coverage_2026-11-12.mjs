// Coverage route tests (penambahan 2026-11-12, DESAIN §4.4/§6.4).
//
// Runs api/worker.js for real (dynamic import of a .mjs copy) with
// global fetch stubbed to canned Hrana pipeline responses. No
// network, no token, no Turso. Covers ONLY the new /api/coverage
// contract — /api/latest + /api/ticker exit-score/perp fields are
// covered live by the harness in /tmp (see the implementation
// report) and by the existing R7/R8/R9 stub tests for regressions.
//
// - /api/coverage 200: live groups are DERIVED from the pools rows
//   (Solana-only today: 13 tickers, 35 pools, only_solana_xstocks
//   true); the pending list is the 6 dated 12 Nov 2026 verdicts.
// - Seeded Base pools flip only_solana_xstocks to false and add a
//   second live group — the banner must never be hardcoded.
// - Pending rows match dashboard/logic.py PENDING_COVERAGE
//   (chain/issuer/verdict/reason_key) — the two lists must not drift.
// - Anti full-scan guard (§6.3): no SELECT * / COUNT(*) over the big
//   tables anywhere in the new statements.
//
// Usage: node qa/test_coverage_2026-11-12.mjs  (exit 0 = PASS)
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const FAILURES = [];
function check(name, ok, detail = "") {
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? ` — ${detail}` : ""));
  if (!ok) FAILURES.push(name);
}

function mkResult(dicts) {
  if (!dicts.length) return { cols: [], rows: [] };
  const keys = Object.keys(dicts[0]);
  return {
    cols: keys.map((k) => ({ name: k })),
    rows: dicts.map((d) => keys.map((k) => ({ value: d[k] ?? null }))),
  };
}

// 13 xStocks tickers x pools (Raydium 27 / Orca 7 / Meteora 1 = 35).
const TICKERS = ["AAPLx", "COINx", "CRCLx", "GLDx", "GOOGLx", "HOODx",
  "METAx", "MSFTx", "MSTRx", "NVDAx", "QQQx", "SPYx", "TSLAx"];
function solanaPoolRows() {
  const rows = [];
  const dexes = [...Array(27).fill("raydium"), ...Array(7).fill("orca"), "meteora"];
  let i = 0;
  for (const dex of dexes) {
    rows.push({ chain: "solana", dex, ticker_id: TICKERS[i % 13], issuer: "xStocks" });
    i += 1;
  }
  return rows;
}

const EXPECTED_PENDING = [
  ["base", "coinbase", "verified", "cov_reason_base"],
  ["bnb", "bstocks", "verified", "cov_reason_bnb"],
  ["robinhood", "robinhood", "verified", "cov_reason_robinhood"],
  ["ethereum", "ondo", "failed", "cov_reason_ondo"],
  ["elysium", "xstocks", "not_active", "cov_reason_elysium"],
  ["hyperliquid", "xstocks-wrapped", "monitor", "cov_reason_hyperliquid"],
];

globalThis.fetch = async (url, opts) => {
  const body = JSON.parse(opts.body);
  const results = body.requests.map((r) => {
    const sql = r.stmt.sql;
    if (sql.includes("FROM pools p JOIN universe u")) {
      const rows = solanaPoolRows();
      if (globalThis.__SEED_BASE) {
        rows.push({ chain: "base", dex: "aerodrome", ticker_id: "NVDAc", issuer: "coinbase" });
        rows.push({ chain: "base", dex: "uniswap", ticker_id: "NVDAc", issuer: "coinbase" });
      }
      return { response: { type: "execute", result: mkResult(rows) } };
    }
    return { response: { type: "execute", result: mkResult([]) } };
  });
  return new Response(JSON.stringify({ results }), { status: 200 });
};

globalThis.caches = {
  default: { match: async () => null, put: async () => {} },
};

const tmp = mkdtempSync(join(tmpdir(), "coverage-worker-"));
const mjsPath = join(tmp, "worker.mjs");
writeFileSync(mjsPath, readFileSync(new URL("../api/worker.js", import.meta.url), "utf8"));
const worker = (await import(mjsPath)).default;
const env = { TURSO_AUTH_TOKEN: "test-token" };

async function get(path) {
  const res = await worker.fetch(new Request("https://api.test" + path), env, {});
  return { status: res.status, body: await res.json() };
}

// --- Solana-only (today's live state) ---------------------------------
const cov = await get("/api/coverage");
check("/api/coverage 200", cov.status === 200, `status=${cov.status}`);
check("one live group: solana/xstocks",
  cov.body.live.length === 1
    && cov.body.live[0].chain === "solana"
    && cov.body.live[0].issuer === "xstocks",
  JSON.stringify(cov.body.live));
check("live group: 13 tickers, 35 pools",
  cov.body.live_tickers === 13 && cov.body.live_pools === 35
    && cov.body.live[0].tickers.length === 13
    && cov.body.live[0].dexes.join(",") === "meteora,orca,raydium",
  `tickers=${cov.body.live_tickers} pools=${cov.body.live_pools}`);
check("only_solana_xstocks true while Solana-only",
  cov.body.only_solana_xstocks === true);
check("verdict_date is 2026-11-12", cov.body.verdict_date === "2026-11-12");
check("pending: 6 dated verdicts, matching dashboard logic.py",
  cov.body.pending.length === 6
    && EXPECTED_PENDING.every(([chain, issuer, verdict, reason_key], i) => {
      const p = cov.body.pending[i];
      return p.chain === chain && p.issuer === issuer
        && p.verdict === verdict && p.reason_key === reason_key
        && typeof p.chain_display === "string"
        && typeof p.issuer_display === "string";
    }),
  JSON.stringify(cov.body.pending.map((p) => [p.chain, p.verdict])));

// --- Base seeded: the banner must flip by itself ----------------------
globalThis.__SEED_BASE = true;
const cov2 = await get("/api/coverage");
check("seeded Base: only_solana_xstocks false",
  cov2.body.only_solana_xstocks === false);
check("seeded Base: 2 live groups, Base has NVDAc",
  cov2.body.live.length === 2
    && cov2.body.live.some((g) => g.chain === "base"
      && g.issuer === "coinbase"
      && g.tickers.join(",") === "NVDAc" && g.pools === 2),
  JSON.stringify(cov2.body.live.map((g) => [g.chain, g.tickers, g.pools])));
check("seeded Base: pending list unchanged",
  cov2.body.pending.length === 6);

// --- Anti full-scan guard (§6.3) ---------------------------------------
const src = readFileSync(new URL("../api/worker.js", import.meta.url), "utf8");
check("no SELECT * in worker.js", !/SELECT\s+\*/i.test(src));
for (const tbl of ["snapshots", "deviations", "perp_snapshots", "liquidation_watch"]) {
  check(`no COUNT(*) over ${tbl}`,
    !new RegExp(`COUNT\\(\\*\\)\\s+FROM\\s+${tbl}`, "i").test(src));
}

console.log(`\nSUMMARY: ${FAILURES.length} FAIL — ${FAILURES.length ? "FAILED: " + FAILURES.join(",") : "COVERAGE TEST: PASS"}`);
process.exit(FAILURES.length ? 1 : 0);
