// Round-9 Worker tests (Radar fix ronde 9: gap CSV pools_excluded).
//
// Runs api/worker.js for real (dynamic import of a .mjs copy) with
// global fetch stubbed to canned Hrana pipeline responses and
// caches.default stubbed in-memory. No network, no token, no Turso.
// The stub/harness is copied from qa/test_r8_worker.mjs (which keeps
// locking P2-M1/P2-M2/S14/S15/GG-13); this file adds only the R9
// pools_excluded coverage:
//
// - Gap CSV (P1-c): /api/latest rows carry pools_excluded (probed via
//   PRAGMA, like loadTicker) and /api/ticker carries it too. When the
//   probe says the column is absent, /api/latest rows carry null
//   (never a fabricated 0) and the endpoint still returns 200.
// - GG-34 regression: the loadLatest deviations SELECT actually names
//   pools_excluded (the drift P1-4 fixed in schema.sql + migration).
//
// Usage: node qa/test_r9_worker.mjs  (exit 0 = PASS)
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
const T_TIER2 = iso(-4 * 60 * 1000); // last 5-min mark (tight-window off-minute)
const T_CYCLE = iso(-2 * 60 * 1000);
const T_FUTURE = iso(60 * 60 * 1000);
const T_STALE = iso(-200 * 60 * 1000);

// --- Hrana stub -------------------------------------------------------
function mkResult(dicts) {
  if (!dicts.length) return { cols: [], rows: [] };
  const keys = Object.keys(dicts[0]);
  return {
    cols: keys.map((k) => ({ name: k })),
    rows: dicts.map((d) => keys.map((k) => ({ value: d[k] ?? null }))),
  };
}

const seenSql = [];
function route(sql, args) {
  seenSql.push(sql);
  if (sql.includes("PRAGMA table_info")) {
    if (globalThis.__NO_EXCLUDED) return mkResult([]);
    return mkResult([{ name: "pools_excluded" }]);
  }
  if (sql.includes("SELECT pools_excluded FROM deviations")) {
    return mkResult([{ pools_excluded: 1 }]);
  }
  if (sql.includes("FROM universe ORDER BY")) {
    return mkResult([
      { ticker_id: "TSLAx", issuer: "xStocks", tier: 1 },
      { ticker_id: "SPYx", issuer: "xStocks", tier: 1 },
      { ticker_id: "AAPLx", issuer: "xStocks", tier: 2 },
    ]);
  }
  // NOTE: route order matters — the loadTicker por/redemption queries
  // contain a "FROM universe WHERE ticker_id" SUBQUERY, so the por /
  // redemption branches must be checked BEFORE the universe branch.
  if (sql.includes("FROM redemption_windows ORDER BY observed_at DESC LIMIT 20")) return mkResult([]);
  if (sql.includes("FROM redemption_windows")) {
    return mkResult([{ status: "open", window_note: null, window_note_en: null, observed_at: T_FRESH, source: "x", next_open_at: null }]);
  }
  if (sql.includes("FROM por_feeds ORDER BY checked_at DESC LIMIT 20")) return mkResult([]);
  if (sql.includes("FROM por_feeds")) {
    // Detail path: NO stored age, last_update 2h in the FUTURE.
    // Pre-fix porEffectiveAge zeroed this to 0 (fresh); post-fix it
    // is unknown (null) — a future timestamp is not evidence of age 0.
    return mkResult([{ feed_address: "x", last_update_ts: T_FUTURE, age_hours: null, reserves_vs_supply_note: "coverage 10/13 tokens; missing from freshness age: AAPLx" }]);
  }
  if (sql.includes("FROM universe WHERE ticker_id")) {
    return mkResult([{ ticker_id: "TSLAx", issuer: "xStocks", underlying: "TSLA", legal_type: "stock", tier: 1 }]);
  }
  if (sql.includes("FROM deviations ORDER BY ts DESC")) {
    // SPYx carries the FUTURE dev ts (P2-M1); AAPLx the 5-min-mark ts.
    return mkResult([
      { ticker_id: "TSLAx", ts: T_FRESH, depth_weighted_price: 100.5, dev_vs_median_pct: 0.001, qualifying_depth_usd: 600000, pools_used: 3, pools_excluded: 1 },
      { ticker_id: "SPYx", ts: globalThis.__SPY_FUTURE ? T_FUTURE : T_STALE, depth_weighted_price: 100.0, dev_vs_median_pct: 0.035, qualifying_depth_usd: 600000, pools_used: 3, pools_excluded: 0 },
      { ticker_id: "AAPLx", ts: T_TIER2, depth_weighted_price: 200.0, dev_vs_median_pct: 0.002, qualifying_depth_usd: 600000, pools_used: 2, pools_excluded: 2 },
    ]);
  }
  if (sql.includes("FROM deviations WHERE ticker_id") && sql.includes("ORDER BY ts DESC")) {
    return mkResult([
      { ts: T_FRESH, depth_weighted_price: 100.5, dev_vs_median_pct: 0.001, qualifying_depth_usd: 600000, pools_used: 3, pools_excluded: 1 },
    ]);
  }
  if (sql.includes("COUNT(DISTINCT")) {
    return mkResult([{ total: 6, live: 6 }]);
  }
  if (sql.includes("FROM pools p JOIN snapshots")) {
    // Per-ticker-latest dataset: every ticker's venues at ITS OWN
    // latest ts (what the fixed SQL returns in production). Under the
    // old global-MAX join, AAPLx would have no rows on off-minutes.
    return mkResult([
      { ticker_id: "TSLAx", dex: "raydium", price_usd: 100.0, reserve_usd: 200000 },
      { ticker_id: "TSLAx", dex: "orca", price_usd: 101.0, reserve_usd: 200000 },
      { ticker_id: "SPYx", dex: "raydium", price_usd: 100.0, reserve_usd: 200000 },
      { ticker_id: "SPYx", dex: "orca", price_usd: 101.0, reserve_usd: 200000 },
      { ticker_id: "AAPLx", dex: "raydium", price_usd: 200.0, reserve_usd: 200000 },
      { ticker_id: "AAPLx", dex: "orca", price_usd: 201.0, reserve_usd: 200000 },
    ]);
  }
  if (sql.includes("FROM poller_health")) {
    if (globalThis.__HEALTH_FUTURE) {
      return mkResult([{ cycle_ts: T_FUTURE, cycles_ok: 1 }]);
    }
    return mkResult([{ cycle_ts: T_CYCLE, cycles_ok: 1 }]);
  }
  if (sql.includes("FROM deviations WHERE ts >=")) {
    return mkResult([
      { ticker_id: "TSLAx", ts: T_FRESH, dev_vs_median_pct: 0.001 },
      { ticker_id: "AAPLx", ts: T_TIER2, dev_vs_median_pct: 0.002 },
    ]);
  }
  if (sql.includes("FROM deviations WHERE ticker_id") && sql.includes("ORDER BY ts ASC")) {
    if (sql.includes("LIMIT 1")) return mkResult([{ dev_vs_median_pct: 0.001 }]);
    return mkResult([{ ts: T_FRESH, dev_vs_median_pct: 0.001 }]);
  }
  if (sql.includes("por_token_snapshots")) return mkResult([]);
  if (sql.includes("FROM alert_log")) {
    const all = [
      { id: 1, ticker_id: "TSLAx", alert_ts: T_FRESH, alert_type: "deviation_high", channel: "en", figure: 3.5 },
      { id: 2, ticker_id: "TSLAx", alert_ts: T_FRESH, alert_type: "deviation_high", channel: "id", figure: 3.5 },
    ];
    if (sql.includes("GROUP BY ticker_id, alert_ts, alert_type")) {
      const kept = new Map();
      for (const r of all) {
        const k = `${r.ticker_id}|${r.alert_ts}|${r.alert_type}`;
        if (!kept.has(k) || r.id < kept.get(k).id) kept.set(k, r);
      }
      return mkResult([...kept.values()]);
    }
    return mkResult(all);
  }
  if (sql.includes("MAX(ts) FROM snapshots")) {
    // loadHealthMeta latest_ts subquery.
    return mkResult([{ latest_ts: T_CYCLE, total: 6, live: 6, plc: T_CYCLE }]);
  }
  throw new Error("unstubbed SQL: " + sql.slice(0, 100));
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
const tmp = mkdtempSync(join(tmpdir(), "r9-worker-"));
const mjsPath = join(tmp, "worker.mjs");
writeFileSync(mjsPath, readFileSync(new URL("../api/worker.js", import.meta.url), "utf8"));
const worker = (await import(mjsPath)).default;
const env = { TURSO_AUTH_TOKEN: "x" };const ctx = { waitUntil: () => {} };

async function get(path, opts = {}) {
  const res = await worker.fetch(new Request(`https://api.test${path}`, opts), env, ctx);
  return { status: res.status, headers: res.headers, body: await res.json().catch(() => null) };
}

// --- GG-15 / P2-M1: future timestamps are stale ------------------------
{
  globalThis.__SPY_FUTURE = true;
  const { status, body } = await get("/api/latest");
  check("P2-M1 /api/latest 200", status === 200, `status=${status}`);
  const by = Object.fromEntries(body.tickers.map((t) => [t.ticker, t]));
  check("P2-M1 future dev ts is stale (never fresh)",
    by.SPYx.stale === true, `stale=${by.SPYx.stale} age=${by.SPYx.dev_age_min}`);
  check("P2-M1 future dev ts reports a negative age (visible anomaly)",
    by.SPYx.dev_age_min < 0, `age=${by.SPYx.dev_age_min}`);
  check("P2-M1 meta.stale_tickers lists the future-dated ticker",
    (body.meta.stale_tickers || []).includes("SPYx"),
    JSON.stringify(body.meta.stale_tickers));
  check("P2-M1 fresh ticker stays fresh beside it",
    by.TSLAx.stale === false, `stale=${by.TSLAx.stale}`);
  delete globalThis.__SPY_FUTURE;

  // Global health: a future last_success_ts is stale.
  globalThis.__HEALTH_FUTURE = true;
  const h = await get("/api/health");
  check("P2-M1 /api/health 200 with future last success", h.status === 200, `status=${h.status}`);
  check("P2-M1 future last_success_ts reads stale, not fresh",
    h.body.stale === true && h.body.fresh === false, JSON.stringify(h.body));
  delete globalThis.__HEALTH_FUTURE;
  const h2 = await get("/api/health");
  check("P2-M1 normal last success stays fresh",
    h2.body.stale === false && h2.body.fresh === true, JSON.stringify(h2.body));

  // Cache HIT re-evaluation with future timestamps.
  const cached = cacheStore.get("https://api.test/api/latest");
  const payload = await cached.json();
  payload.meta.last_success_ts = T_FUTURE;
  payload.meta.stale = false;
  payload.meta.fresh = true;
  payload.tickers.find((t) => t.ticker === "TSLAx").dev_ts = T_FUTURE;
  cacheStore.set(
    "https://api.test/api/latest",
    new Response(JSON.stringify(payload), { headers: { "Content-Type": "application/json" } }),
  );
  const hit = await get("/api/latest");
  check("P2-M1 cache HIT with future timestamps reads stale",
    hit.body.meta.stale === true && hit.body.meta.fresh === false,
    JSON.stringify(hit.body.meta));
  check("P2-M1 cache HIT marks the future-dated ticker stale",
    hit.body.tickers.find((t) => t.ticker === "TSLAx").stale === true);
}

// --- P2-M2: Tier 2 keeps its venues on tight-window off-minutes -------
{
  // The stubbed cache returns the same Response object (real edge
  // cache clones per match); the tampered HIT payload above is already
  // consumed, so force a MISS for this block.
  cacheStore.delete("https://api.test/api/latest");
  seenSql.length = 0;
  const { status, body } = await get("/api/latest");
  check("P2-M2 /api/latest 200", status === 200, `status=${status}`);
  const snapSql = seenSql.find((s) => s.includes("FROM pools p JOIN snapshots"));
  check("P2-M2 snapshot SQL has NO global-MAX(ts) join",
    snapSql && !snapSql.includes("s.ts = (SELECT MAX(ts) FROM snapshots)"),
    snapSql?.slice(0, 160));
  check("P2-M2 snapshot SQL anchors per ticker (per-ticker MAX)",
    snapSql && /MAX\(s2\.ts\)/.test(snapSql) && snapSql.includes("GROUP BY"),
    snapSql?.slice(0, 200));
  const by = Object.fromEntries(body.tickers.map((t) => [t.ticker, t]));
  check("P2-M2 Tier 2 (AAPLx) keeps venues at its 5-min-mark ts",
    by.AAPLx.best_price === 200.0 && by.AAPLx.spread_pct != null,
    `best=${by.AAPLx.best_price} spread=${by.AAPLx.spread_pct}`);
  check("P2-M2 venues_live counts all pools (no Tier 2 dip)",
    body.meta.venues_live === 6 && body.meta.venues_total === 6,
    `live=${body.meta.venues_live} total=${body.meta.venues_total}`);
}

// --- S14/S15 runtime contract ------------------------------------------
{
  const { status, body } = await get("/api/alerts");
  check("S14 /api/alerts 200", status === 200, `status=${status}`);
  check("S14 feed rows carry a channel",
    body.alerts.length > 0 && body.alerts.every((a) => typeof a.channel === "string"),
    JSON.stringify(body.alerts));
  const latest = await get("/api/latest");
  check("S15 /api/latest meta carries stale_tickers (array)",
    Array.isArray(latest.body.meta.stale_tickers),
    JSON.stringify(latest.body.meta.stale_tickers));
}

// --- Gap CSV: pools_excluded reaches /api/latest + /api/ticker ---
{
  cacheStore.delete("https://api.test/api/latest");
  seenSql.length = 0;
  const { status, body } = await get("/api/latest");
  check("GapCSV /api/latest 200", status === 200, `status=${status}`);
  const by = Object.fromEntries(body.tickers.map((t) => [t.ticker, t]));
  check("GapCSV /api/latest rows carry pools_excluded values",
    by.TSLAx.pools_excluded === 1 && by.SPYx.pools_excluded === 0 &&
    by.AAPLx.pools_excluded === 2,
    JSON.stringify(body.tickers.map((t) => [t.ticker, t.pools_excluded])));
  const devSql = seenSql.find((s) => s.includes("FROM deviations ORDER BY ts DESC"));
  check("GapCSV loadLatest deviations SELECT names pools_excluded",
    devSql && devSql.includes("pools_excluded"), devSql?.slice(0, 200));
  const det = await get("/api/ticker?ticker=TSLAx");
  check("GapCSV /api/ticker 200", det.status === 200, `status=${det.status}`);
  check("GapCSV /api/ticker carries pools_excluded",
    det.body.pools_excluded === 1, `pools_excluded=${det.body.pools_excluded}`);
}

// --- Gap CSV: column absent from the DB -> null, never fabricated ---
{
  globalThis.__NO_EXCLUDED = true;
  cacheStore.delete("https://api.test/api/latest");
  const { status, body } = await get("/api/latest");
  check("GapCSV-no-col /api/latest 200", status === 200, `status=${status}`);
  check("GapCSV-no-col rows carry pools_excluded null (not a fake 0)",
    body.tickers.every((t) => t.pools_excluded === null),
    JSON.stringify(body.tickers.map((t) => [t.ticker, t.pools_excluded])));
  const det = await get("/api/ticker?ticker=TSLAx");
  check("GapCSV-no-col /api/ticker still carries pools_excluded 0 (loadTicker contract)",
    det.body.pools_excluded === 0, `pools_excluded=${det.body.pools_excluded}`);
  delete globalThis.__NO_EXCLUDED;
}

console.log(`\nSUMMARY: ${FAILURES.length} FAIL — ` +
  (FAILURES.length ? `FAILED: ${FAILURES}` : "R9 WORKER TEST: PASS"));
process.exit(FAILURES.length ? 1 : 0);
