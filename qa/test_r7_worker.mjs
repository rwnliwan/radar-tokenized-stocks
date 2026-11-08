// Round-7 Worker tests (Terra r7 Radar: M1, S1, S6, S7, N1).
//
// Runs api/worker.js for real (dynamic import of a .mjs copy — the repo
// file is a Worker module) with global fetch stubbed to canned Hrana
// pipeline responses and caches.default stubbed in-memory. No network,
// no token, no Turso.
//
// - M1: /api/latest marks a ticker stale from its OWN deviations row
//   (200 min old) while meta stays globally fresh; meta.stale_tickers
//   lists it. /api/ticker reports the same per-ticker stale flag even
//   when global health is fresh.
// - S1: a /api/latest edge-cache HIT is re-validated from timestamps —
//   a cached body claiming fresh with last_success_ts 16 min ago is
//   served as stale, not fresh.
// - S6: /api/ticker anchors per-pool snapshots to the deviations ts
//   (the venue SQL binds the dev ts, not per-pool MAX(ts)).
// - S7: /api/alerts deduplicates one event delivered to EN + ID into
//   a single feed entry.
// - N1: POST /api/waitlist with a JSON null body returns 400, not 502.
//
// Usage: node qa/test_r7_worker.mjs  (exit 0 = PASS)
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const FAILURES = [];
function check(name, ok, detail = "") {
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? ` — ${detail}` : ""));
  if (!ok) FAILURES.push(name);
}

const NOW = Date.now();
const iso = (msAgo) => new Date(NOW - msAgo).toISOString().replace(/\.\d{3}Z$/, "Z");
const T_FRESH = iso(5 * 60 * 1000);
const T_STALE = iso(200 * 60 * 1000);
const T_CYCLE = iso(2 * 60 * 1000);

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
  if (sql.includes("PRAGMA table_info")) return mkResult([]);
  if (sql.includes("FROM universe ORDER BY")) {
    return mkResult([
      { ticker_id: "TSLAx", issuer: "xStocks", tier: 1 },
      { ticker_id: "SPYx", issuer: "xStocks", tier: 1 },
    ]);
  }
  if (sql.includes("FROM universe WHERE ticker_id")) {
    return mkResult([{ ticker_id: "TSLAx", issuer: "xStocks", underlying: "TSLA", legal_type: "stock", tier: 1 }]);
  }
  if (sql.includes("FROM deviations ORDER BY ts DESC")) {
    return mkResult([
      { ticker_id: "TSLAx", ts: T_FRESH, depth_weighted_price: 100.5, dev_vs_median_pct: 0.001, qualifying_depth_usd: 600000, pools_used: 3 },
      { ticker_id: "SPYx", ts: T_STALE, depth_weighted_price: 100.0, dev_vs_median_pct: 0.035, qualifying_depth_usd: 600000, pools_used: 3 },
    ]);
  }
  if (sql.includes("FROM deviations WHERE ticker_id") && sql.includes("ORDER BY ts DESC")) {
    // loadTicker latest deviation row: fresh for the S6 test, stale when
    // the test flips the fixture via globalThis.__DEV_TS.
    return mkResult([
      { ts: globalThis.__DEV_TS ?? T_FRESH, depth_weighted_price: 100.5, dev_vs_median_pct: 0.001, qualifying_depth_usd: 600000, pools_used: 3 },
    ]);
  }
  if (sql.includes("FROM redemption_windows ORDER BY observed_at DESC LIMIT 20")) return mkResult([]);
  if (sql.includes("FROM redemption_windows")) {
    return mkResult([{ status: "open", window_note: null, window_note_en: null, observed_at: T_FRESH, source: "x", next_open_at: null }]);
  }
  if (sql.includes("FROM por_feeds ORDER BY checked_at DESC LIMIT 20")) return mkResult([]);
  if (sql.includes("FROM por_feeds")) return mkResult([]);
  if (sql.includes("FROM pools p JOIN snapshots")) {
    return mkResult([
      { ticker_id: "TSLAx", dex: "raydium", price_usd: 100.0, reserve_usd: 200000 },
      { ticker_id: "TSLAx", dex: "orca", price_usd: 101.0, reserve_usd: 200000 },
      { ticker_id: "SPYx", dex: "raydium", price_usd: 100.0, reserve_usd: 200000 },
    ]);
  }
  // P2-M2 (fix ronde 8): venues_live now counts pools at each
  // ticker's own latest snapshot — the SQL qualifies the column
  // (s.pool_id) because pools and snapshots both carry pool_id.
  if (sql.includes("COUNT(DISTINCT s.pool_id) AS live") || sql.includes("COUNT(DISTINCT pool_id) AS live")) {
    return mkResult([{ total: 4, live: 4 }]);
  }
  if (sql.includes("FROM poller_health")) {
    return mkResult([{ cycle_ts: T_CYCLE, cycles_ok: 1 }]);
  }
  if (sql.includes("FROM deviations WHERE ts >=")) {
    return mkResult([
      { ticker_id: "TSLAx", ts: T_FRESH, dev_vs_median_pct: 0.001 },
      { ticker_id: "SPYx", ts: T_STALE, dev_vs_median_pct: 0.035 },
    ]);
  }
  if (sql.includes("FROM deviations WHERE ticker_id") && sql.includes("ORDER BY ts ASC")) {
    if (sql.includes("LIMIT 1")) return mkResult([{ dev_vs_median_pct: 0.001 }]);
    return mkResult([{ ts: T_FRESH, dev_vs_median_pct: 0.001 }]);
  }
  if (sql.includes("por_token_snapshots")) return mkResult([]);
  if (sql.includes("FROM alert_log")) {
    // The stub is a fake DB: simulate the MIN(id) GROUP BY dedup the
    // SQL performs, keeping the lowest-id row per event.
    const all = [
      { id: 1, ticker_id: "TSLAx", alert_ts: T_FRESH, alert_type: "deviation_high", channel: "en", figure: 3.5 },
      { id: 2, ticker_id: "TSLAx", alert_ts: T_FRESH, alert_type: "deviation_high", channel: "id", figure: 3.5 },
      { id: 3, ticker_id: "SPYx", alert_ts: T_STALE, alert_type: "spread", channel: "en", figure: 4.4 },
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
const tmp = mkdtempSync(join(tmpdir(), "r7-worker-"));
const mjsPath = join(tmp, "worker.mjs");
writeFileSync(mjsPath, readFileSync(new URL("../api/worker.js", import.meta.url), "utf8"));
const worker = (await import(mjsPath)).default;
const env = { TURSO_AUTH_TOKEN: "test-token" };
const ctx = { waitUntil: () => {} };

async function get(path, opts = {}) {
  const res = await worker.fetch(new Request(`https://api.test${path}`, opts), env, ctx);
  return { status: res.status, headers: res.headers, body: await res.json().catch(() => null) };
}

// --- M1: /api/latest per-ticker staleness ------------------------------
{
  const { status, body } = await get("/api/latest");
  check("M1 /api/latest 200", status === 200, `status=${status}`);
  check("M1 meta stays globally fresh (poller healthy)",
    body.meta.fresh === true && body.meta.stale === false,
    JSON.stringify(body.meta));
  const by = Object.fromEntries(body.tickers.map((t) => [t.ticker, t]));
  check("M1 fresh ticker is not stale (dev 5 min old)",
    by.TSLAx.stale === false, `stale=${by.TSLAx.stale} age=${by.TSLAx.dev_age_min}`);
  check("M1 stale ticker IS stale (dev 200 min old, global fresh)",
    by.SPYx.stale === true && Math.abs(by.SPYx.dev_age_min - 200) < 1,
    `stale=${by.SPYx.stale} age=${by.SPYx.dev_age_min}`);
  check("M1 meta.stale_tickers lists only the stale ticker",
    JSON.stringify(body.meta.stale_tickers) === JSON.stringify(["SPYx"]),
    JSON.stringify(body.meta.stale_tickers));
  check("M1 stale ticker keeps its values (flagged, not hidden)",
    by.SPYx.dw_price === 100.0 && Math.abs(by.SPYx.dev_bps - 3.5) < 1e-9,
    `dw=${by.SPYx.dw_price} bps=${by.SPYx.dev_bps}`);
}

// --- S1: cache HIT re-validates freshness ------------------------------
{
  // The first /api/latest above was a MISS and is cached. Craft a HIT
  // body that claims fresh with last_success_ts 16 min ago (as if
  // cached just before the boundary) and serve it from the cache.
  const cached = cacheStore.get("https://api.test/api/latest");
  const payload = await cached.json();
  payload.meta.last_success_ts = iso(16 * 60 * 1000);
  payload.meta.stale = false;
  payload.meta.fresh = true;
  cacheStore.set(
    "https://api.test/api/latest",
    new Response(JSON.stringify(payload), { headers: { "Content-Type": "application/json" } }),
  );
  const { status, headers, body } = await get("/api/latest");
  check("S1 cache HIT 200 + X-Edge-Cache HIT",
    status === 200 && headers.get("X-Edge-Cache") === "HIT",
    `status=${status} cache=${headers.get("X-Edge-Cache")}`);
  check("S1 HIT re-validates: 16-min-old last success reads stale, not fresh",
    body.meta.stale === true && body.meta.fresh === false,
    JSON.stringify(body.meta));
  check("S1 HIT keeps per-ticker stale flags (SPYx stale, TSLAx fresh)",
    body.tickers.find((t) => t.ticker === "SPYx").stale === true &&
      body.tickers.find((t) => t.ticker === "TSLAx").stale === false);
}

// --- S6 + M1 detail: /api/ticker ---------------------------------------
{
  seenSql.length = 0;
  const { status, body } = await get("/api/ticker?ticker=TSLAx");
  check("S6 /api/ticker 200", status === 200, `status=${status}`);
  const venueSql = seenSql.find((s) => s.includes("FROM pools p JOIN snapshots"));
  check("S6 venue SQL binds the deviations ts (no per-pool MAX)",
    venueSql && venueSql.includes("AND s.ts = ?") && !venueSql.includes("MAX(ts) FROM snapshots s2"),
    venueSql?.slice(0, 120));
  check("S6 detail carries the canonical global health verdict",
    body.health_stale === false && body.health_fresh === true,
    `health_stale=${body.health_stale}`);
  check("S6 detail dev is fresh (5 min old)", body.stale === false && body.dev_ts === T_FRESH,
    `stale=${body.stale} dev_ts=${body.dev_ts}`);

  // M1 detail: a 200-min-old deviation row reads stale even though
  // global health is fresh.
  globalThis.__DEV_TS = T_STALE;
  const staleDetail = (await get("/api/ticker?ticker=TSLAx")).body;
  check("M1 detail stale flag is per-ticker (old dev, fresh health)",
    staleDetail.stale === true && staleDetail.health_stale === false,
    `stale=${staleDetail.stale} health_stale=${staleDetail.health_stale}`);
  delete globalThis.__DEV_TS;
}

// --- S7: /api/alerts dedup --------------------------------------------
{
  seenSql.length = 0;
  const { status, body } = await get("/api/alerts");
  check("S7 /api/alerts 200", status === 200, `status=${status}`);
  check("S7 feed SQL dedupes by event (MIN(id) GROUP BY ticker/ts/type)",
    seenSql.some((s) => s.includes("MIN(id)") && s.includes("GROUP BY ticker_id, alert_ts, alert_type")),
    seenSql.find((s) => s.includes("FROM alert_log"))?.slice(0, 120));
  check("S7 EN+ID delivery of one event is a single feed entry",
    body.alerts.length === 2, `n=${body.alerts.length} ${JSON.stringify(body.alerts)}`);
  check("S7 deduped entry keeps a channel",
    body.alerts.find((a) => a.type === "deviation_high").channel === "en");
}

// --- N1: waitlist null body --------------------------------------------
{
  const res = await worker.fetch(
    new Request("https://api.test/api/waitlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "null",
    }),
    env,
    ctx,
  );
  check("N1 JSON null waitlist body returns 400 (not 502)",
    res.status === 400, `status=${res.status}`);
  const resArr = await worker.fetch(
    new Request("https://api.test/api/waitlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "[1,2]",
    }),
    env,
    ctx,
  );
  check("N1 JSON array waitlist body returns 400", resArr.status === 400, `status=${resArr.status}`);
}

console.log(`\nSUMMARY: ${FAILURES.length} FAIL — ` +
  (FAILURES.length ? `FAILED: ${FAILURES}` : "R7 WORKER TEST: PASS"));
process.exit(FAILURES.length ? 1 : 0);
