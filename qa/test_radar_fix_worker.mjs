// Radar fix tests — ronde review DeepSeek 2026-11-13 (worker.js only).
//
// Runs api/worker.js for real (dynamic import of a .mjs copy) with
// global fetch stubbed to canned Hrana pipeline responses and
// caches.default stubbed in-memory. No network, no token, no Turso.
// The stub/harness is copied from qa/test_r9_worker.mjs.
//
// - M1 (prioritas tertinggi): the ticker regex accepts every live
//   suffix — X (xStocks), C (coinbase), B (bstocks), R (robinhood) —
//   on /api/ticker AND /api/history, and still rejects empty /
//   malformed tickers with 400. A well-formed but unknown ticker
//   still 404s on /api/ticker (universe check untouched).
// - M12: /api/coverage never lists the same chain in live and
//   pending. Fixture: multichain live (solana + base + bsc + robinhood)
//   leaves only ethereum/elysium/hyperliquid pending. The bsc/bnb
//   spelling alias is covered: live pools say "bsc", the verdict
//   table says "bnb" — the same chain must still be filtered out.
// - M5: /api/latest + /api/ticker carry exit_score_components
//   (INTEGER 0-5) when the column exists; null (never a fabricated
//   count) when the column is absent from the DB.
//
// Usage: node qa/test_radar_fix_worker.mjs  (exit 0 = PASS)
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const FAILURES = [];
function check(name, ok, detail = "") {
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? ` — ${detail}` : ""));
  if (!ok) FAILURES.push(name);
}

const NOW = Date.now();
const iso = (ms) => new Date(NOW + ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const T_FRESH = iso(-5 * 60 * 1000);
const T_CYCLE = iso(-2 * 60 * 1000);

// --- Hrana stub -------------------------------------------------------
function mkResult(dicts) {
  if (!dicts.length) return { cols: [], rows: [] };
  const keys = Object.keys(dicts[0]);
  return {
    cols: keys.map((k) => ({ name: k })),
    rows: dicts.map((d) => keys.map((k) => ({ value: d[k] ?? null }))),
  };
}

const KNOWN = new Set(["TSLAX", "TSLAC", "TSLAB", "TSLAR", "NVDAC", "CRCLR"]);
const ISSUER_OF = {
  TSLAX: "xStocks",
  TSLAC: "coinbase",
  TSLAB: "bstocks",
  TSLAR: "robinhood",
  NVDAC: "coinbase",
  CRCLR: "robinhood",
};

function devDetailRow(comps) {
  const r = {
    ts: T_FRESH,
    depth_weighted_price: 100.5,
    dev_vs_median_pct: 0.001,
    qualifying_depth_usd: 600000,
    pools_used: 3,
    exit_score: 80.0,
    exit_score_version: "exit_score_v2",
  };
  if (!globalThis.__NO_EXIT_COMPONENTS) r.exit_score_components = comps;
  return r;
}

function coverageRows() {
  const rows = [
    { chain: "solana", dex: "raydium", ticker_id: "TSLAx", issuer: "xStocks" },
    { chain: "solana", dex: "orca", ticker_id: "NVDAx", issuer: "xStocks" },
  ];
  if (globalThis.__COVERAGE === "multichain") {
    rows.push(
      { chain: "base", dex: "aerodrome", ticker_id: "NVDAc", issuer: "coinbase" },
      // Live pools spell the BNB chain "bsc"; the pending verdict
      // table spells it "bnb". The filter must treat them as one.
      { chain: "bsc", dex: "pancakeswap", ticker_id: "TSLAB", issuer: "bstocks" },
      { chain: "robinhood", dex: "uniswap", ticker_id: "TSLAr", issuer: "robinhood" },
    );
  }
  return rows;
}

const seenSql = [];
function route(sql, args) {
  seenSql.push(sql);
  if (sql.includes("PRAGMA table_info")) {
    const cols = [
      { name: "pools_excluded" },
      { name: "exit_score" },
      { name: "exit_score_version" },
    ];
    if (!globalThis.__NO_EXIT_COMPONENTS) cols.push({ name: "exit_score_components" });
    return mkResult(cols);
  }
  if (sql.includes("sqlite_master")) return mkResult([]);
  if (sql.includes("FROM pools p JOIN universe u")) {
    return mkResult(coverageRows());
  }
  if (sql.includes("FROM universe ORDER BY")) {
    return mkResult([
      { ticker_id: "TSLAx", issuer: "xStocks", tier: 1 },
      { ticker_id: "TSLAc", issuer: "coinbase", tier: 1 },
      { ticker_id: "TSLAB", issuer: "bstocks", tier: 1 },
      { ticker_id: "TSLAr", issuer: "robinhood", tier: 1 },
      { ticker_id: "NVDAc", issuer: "coinbase", tier: 1 },
      { ticker_id: "CRCLr", issuer: "robinhood", tier: 2 },
    ]);
  }
  // NOTE: route order matters — the loadTicker por/redemption queries
  // contain a "FROM universe WHERE ticker_id" SUBQUERY, so the por /
  // redemption branches must be checked BEFORE the universe branch.
  if (sql.includes("FROM redemption_windows ORDER BY observed_at DESC LIMIT 20")) return mkResult([]);
  if (sql.includes("FROM redemption_windows")) return mkResult([]);
  if (sql.includes("FROM por_feeds ORDER BY checked_at DESC LIMIT 20")) return mkResult([]);
  if (sql.includes("FROM por_feeds")) return mkResult([]);
  if (sql.includes("FROM universe WHERE ticker_id")) {
    const t = (args && args[0]) || "";
    if (!KNOWN.has(t)) return mkResult([]);
    return mkResult([{
      ticker_id: t,
      issuer: ISSUER_OF[t],
      underlying: t.replace(/[XCBR]$/, ""),
      legal_type: "stock",
      tier: 1,
    }]);
  }
  if (sql.includes("SELECT pools_excluded FROM deviations")) {
    return mkResult([{ pools_excluded: 1 }]);
  }
  if (sql.includes("FROM deviations WHERE ticker_id") && sql.includes("ORDER BY ts DESC")) {
    return mkResult([devDetailRow(4)]);
  }
  if (sql.includes("FROM deviations ORDER BY ts DESC")) {
    return mkResult([
      { ticker_id: "TSLAx", ...devDetailRow(4) },
      { ticker_id: "TSLAc", ...devDetailRow(5) },
      { ticker_id: "NVDAc", ...devDetailRow(3) },
    ]);
  }
  if (sql.includes("GROUP BY ticker_id, bucket")) {
    // History never checks the universe, so the stub is the only
    // thing that can return an empty series for an unknown ticker.
    if (!KNOWN.has(args[0])) return mkResult([]);
    return mkResult([{ ticker_id: args[0], bucket: "2026-11-13T00:00:00Z", dev: 0.001 }]);
  }
  if (sql.includes("FROM deviations WHERE ts >=")) {
    return mkResult([{ ticker_id: "TSLAx", ts: T_FRESH, dev_vs_median_pct: 0.001 }]);
  }
  if (sql.includes("AS dev")) {
    // /api/history 1h branch (dev_vs_median_pct AS dev).
    if (!KNOWN.has(args[0])) return mkResult([]);
    return mkResult([{ ticker_id: args[0], ts: T_FRESH, dev: 0.001 }]);
  }
  if (sql.includes("FROM deviations WHERE ticker_id") && sql.includes("ORDER BY ts ASC")) {
    if (sql.includes("LIMIT 1")) return mkResult([{ dev_vs_median_pct: 0.001 }]);
    return mkResult([{ ts: T_FRESH, dev_vs_median_pct: 0.001 }]);
  }
  if (sql.includes("COUNT(DISTINCT")) {
    return mkResult([{ total: 6, live: 6 }]);
  }
  if (sql.includes("FROM pools p JOIN snapshots")) {
    return mkResult([
      { ticker_id: "TSLAx", dex: "raydium", price_usd: 100.0, reserve_usd: 200000 },
      { ticker_id: "TSLAx", dex: "orca", price_usd: 101.0, reserve_usd: 200000 },
      { ticker_id: "TSLAc", dex: "aerodrome", price_usd: 100.0, reserve_usd: 200000 },
      { ticker_id: "NVDAc", dex: "aerodrome", price_usd: 100.0, reserve_usd: 200000 },
    ]);
  }
  if (sql.includes("FROM poller_health")) {
    return mkResult([{ cycle_ts: T_CYCLE, cycles_ok: 1 }]);
  }
  if (sql.includes("por_token_snapshots")) return mkResult([]);
  throw new Error("unstubbed SQL: " + sql.slice(0, 120));
}

globalThis.fetch = async (url, opts) => {
  const body = JSON.parse(opts.body);
  const results = body.requests.map((r) => {
    const sql = r.stmt.sql;
    const args = (r.stmt.args || []).map((a) => a.value);
    return { response: { type: "execute", result: route(sql, args) } };
  });
  return new Response(JSON.stringify({ results }), { status: 200 });
};

// --- caches stub ------------------------------------------------------
const cacheStore = new Map();
globalThis.caches = {
  default: {
    match: async (req) => cacheStore.get(req.url) ?? null,
    put: async (req, res) => {
      cacheStore.set(req.url, res);
    },
  },
};

// --- load the Worker module (as .mjs) ----------------------------------
const tmp = mkdtempSync(join(tmpdir(), "radar-fix-worker-"));
const mjsPath = join(tmp, "worker.mjs");
writeFileSync(mjsPath, readFileSync(new URL("../api/worker.js", import.meta.url), "utf8"));
const worker = (await import(mjsPath)).default;
const env = { TURSO_AUTH_TOKEN: "x" };
const ctx = { waitUntil: () => {} };

async function get(path, opts = {}) {
  const res = await worker.fetch(new Request(`https://api.test${path}`, opts), env, ctx);
  return { status: res.status, headers: res.headers, body: await res.json().catch(() => null) };
}

// --- M1: every live suffix accepted on /api/ticker + /api/history -----
{
  const ACCEPT = ["TSLAx", "TSLAc", "TSLAB", "TSLAr", "NVDAc", "CRCLr"];
  for (const t of ACCEPT) {
    const det = await get(`/api/ticker?ticker=${t}`);
    check(`M1 /api/ticker accepts ${t}`,
      det.status === 200 && det.body.ticker === t.toUpperCase(),
      `status=${det.status} ticker=${det.body?.ticker}`);
    const hist = await get(`/api/history?ticker=${t}&window=1h`);
    check(`M1 /api/history accepts ${t}`,
      hist.status === 200 && Array.isArray(hist.body.points),
      `status=${hist.status}`);
  }
  const REJECT = ["", "TSLA", "TSLAZ", "TSLA$", "X"];
  for (const t of REJECT) {
    const det = await get(`/api/ticker?ticker=${encodeURIComponent(t)}`);
    check(`M1 /api/ticker rejects ${JSON.stringify(t)} with 400`,
      det.status === 400, `status=${det.status}`);
    const hist = await get(`/api/history?ticker=${encodeURIComponent(t)}&window=1h`);
    check(`M1 /api/history rejects ${JSON.stringify(t)} with 400`,
      hist.status === 400, `status=${hist.status}`);
  }
  // Well-formed but not in the universe: still 404, not 400 —
  // the regex is format-only, existence stays the universe's job.
  const unknown = await get("/api/ticker?ticker=FOOX");
  check("M1 /api/ticker unknown well-formed ticker still 404",
    unknown.status === 404, `status=${unknown.status}`);
  const histUnknown = await get("/api/history?ticker=FOOX&window=24h");
  check("M1 /api/history unknown well-formed ticker still 200 (empty series)",
    histUnknown.status === 200 && Array.isArray(histUnknown.body.points)
      && histUnknown.body.points.length === 0,
    `status=${histUnknown.status} points=${JSON.stringify(histUnknown.body.points)}`);
}

// --- M12: live and pending never share a chain -------------------------
{
  // Solana-only live: nothing overlaps, all 6 verdicts stay pending.
  globalThis.__COVERAGE = "solana";
  const cov = await get("/api/coverage");
  check("M12 solana-only /api/coverage 200", cov.status === 200, `status=${cov.status}`);
  check("M12 solana-only: pending still holds all 6 verdicts",
    cov.body.pending.length === 6,
    JSON.stringify(cov.body.pending.map((p) => p.chain)));

  // Multichain live: base + bsc + robinhood go live, so their pending
  // rows must drop (bsc live must drop the "bnb" verdict row too).
  globalThis.__COVERAGE = "multichain";
  const cov2 = await get("/api/coverage");
  check("M12 multichain /api/coverage 200", cov2.status === 200, `status=${cov2.status}`);
  const liveChains = cov2.body.live.map((g) => g.chain);
  check("M12 multichain: live has solana, base, bsc, robinhood",
    ["solana", "base", "bsc", "robinhood"].every((c) => liveChains.includes(c)),
    JSON.stringify(liveChains));
  const pendChains = cov2.body.pending.map((p) => p.chain);
  check("M12 multichain: pending drops to ethereum/elysium/hyperliquid only",
    cov2.body.pending.length === 3
      && ["ethereum", "elysium", "hyperliquid"].every((c) => pendChains.includes(c)),
    JSON.stringify(pendChains));
  check("M12 multichain: no pending chain is live (incl. bnb alias of bsc)",
    !pendChains.some((c) => ["base", "bnb", "bsc", "robinhood", "solana"].includes(c)),
    JSON.stringify(pendChains));
  check("M12 multichain: only_solana_xstocks false",
    cov2.body.only_solana_xstocks === false);
  delete globalThis.__COVERAGE;
}

// --- M5: exit_score_components forwarded when present, null when not ---
{
  cacheStore.delete("https://api.test/api/latest");
  seenSql.length = 0;
  const latest = await get("/api/latest");
  check("M5 /api/latest 200", latest.status === 200, `status=${latest.status}`);
  const by = Object.fromEntries(latest.body.tickers.map((t) => [t.ticker, t]));
  check("M5 /api/latest rows carry exit_score_components (INTEGER 0-5)",
    by.TSLAx.exit_score_components === 4
      && by.TSLAc.exit_score_components === 5
      && by.NVDAc.exit_score_components === 3
      && [by.TSLAx, by.TSLAc, by.NVDAc].every((t) =>
        Number.isInteger(t.exit_score_components)
        && t.exit_score_components >= 0 && t.exit_score_components <= 5),
    JSON.stringify(latest.body.tickers.map((t) => [t.ticker, t.exit_score_components])));
  const devSql = seenSql.find((s) => s.includes("FROM deviations ORDER BY ts DESC"));
  check("M5 loadLatest deviations SELECT names exit_score_components",
    devSql && devSql.includes("exit_score_components"), devSql?.slice(0, 200));
  const det = await get("/api/ticker?ticker=TSLAx");
  check("M5 /api/ticker 200", det.status === 200, `status=${det.status}`);
  check("M5 /api/ticker carries exit_score_components",
    det.body.exit_score_components === 4,
    `exit_score_components=${det.body.exit_score_components}`);
  const detSql = seenSql.find((s) =>
    s.includes("FROM deviations WHERE ticker_id") && s.includes("ORDER BY ts DESC"));
  check("M5 loadTicker deviations SELECT names exit_score_components",
    detSql && detSql.includes("exit_score_components"), detSql?.slice(0, 200));
}

{
  // Column absent from the DB (migration not yet applied): null,
  // never a fabricated count — on both endpoints.
  globalThis.__NO_EXIT_COMPONENTS = true;
  cacheStore.delete("https://api.test/api/latest");
  const latest = await get("/api/latest");
  check("M5-no-col /api/latest 200", latest.status === 200, `status=${latest.status}`);
  check("M5-no-col /api/latest rows carry exit_score_components null",
    latest.body.tickers.every((t) => t.exit_score_components === null),
    JSON.stringify(latest.body.tickers.map((t) => [t.ticker, t.exit_score_components])));
  const det = await get("/api/ticker?ticker=TSLAx");
  check("M5-no-col /api/ticker carries exit_score_components null",
    det.body.exit_score_components === null,
    `exit_score_components=${det.body.exit_score_components}`);
  delete globalThis.__NO_EXIT_COMPONENTS;
}

console.log(`\nSUMMARY: ${FAILURES.length} FAIL — ` +
  (FAILURES.length ? `FAILED: ${FAILURES}` : "RADAR FIX WORKER TEST: PASS"));
process.exit(FAILURES.length ? 1 : 0);
