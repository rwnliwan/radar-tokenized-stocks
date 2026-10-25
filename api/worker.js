/**
 * radar-api — read-only JSON API for the Exit Radar Next.js frontend.
 *
 * Reads ONLY from the Turso database the poller writes to (db
 * `radar-tokenized-stocks`). No writes, no schema changes, no auth
 * gate: this data is already public on the Streamlit dashboard.
 *
 * Secrets: TURSO_AUTH_TOKEN is a Worker secret (never in code).
 * The Turso hostname is public (it already appears in the repo's
 * Python clients) and is hardcoded here.
 *
 * Transport: Hrana v2 pipeline, one POST carrying all SELECTs for an
 * endpoint, so a status flip mid-load cannot split one response
 * (the same race that split the first Telegram batch, 2026-10-25:
 * program-wide rows are read in the same pipeline as per-ticker rows).
 */

const HOST = "radar-tokenized-stocks-trisaktipan.aws-ap-northeast-1.turso.io";
const HRANA = `https://${HOST}/v2/pipeline`;
const LIQ_MIN = 100000;

function encArg(v) {
  if (v === null || v === undefined) return { type: "null" };
  if (typeof v === "number")
    return Number.isInteger(v)
      ? { type: "integer", value: String(v) }
      : { type: "float", value: v };
  return { type: "text", value: String(v) };
}

async function pipeline(env, stmts) {
  const res = await fetch(HRANA, {
    method: "POST",
    headers: {
      Authorization: "Bearer " + env.TURSO_AUTH_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      requests: stmts.map(([sql, args]) => {
        const stmt = { sql };
        if (args) stmt.args = args.map(encArg);
        return { type: "execute", stmt };
      }),
    }),
  });
  if (!res.ok) throw new Error("Hrana HTTP " + res.status);
  const data = await res.json();
  const out = [];
  for (const r of data.results || []) {
    if (r.type === "error")
      throw new Error("Hrana: " + (r.error?.message || "statement failed"));
    const resp = r.response || {};
    out.push(resp.type === "execute" ? resp.result || {} : resp);
  }
  return out;
}

function rowsOf(result) {
  const cols = (result.cols || []).map((c) => c.name);
  return (result.rows || []).map((row) => {
    const d = {};
    cols.forEach((name, i) => {
      const cell = row[i];
      d[name] = cell && typeof cell === "object" ? cell.value ?? null : null;
    });
    return d;
  });
}

function firstPerTicker(devRows) {
  const latest = {};
  for (const r of devRows) {
    if (!(r.ticker_id in latest)) latest[r.ticker_id] = r;
  }
  return latest;
}

function crossVenueSpread(venues, dw) {
  const prices = venues
    .filter((v) => v.price_usd != null && (v.reserve_usd || 0) >= LIQ_MIN)
    .map((v) => v.price_usd);
  if (prices.length < 2 || !dw) return null;
  return ((Math.max(...prices) - Math.min(...prices)) / dw) * 100;
}

async function loadLatest(env) {
  const [
    uniR,
    devR,
    redR,
    porR,
    snapR,
    venuesLiveR,
    healthR,
    seriesR,
  ] = await pipeline(env, [
    ["SELECT ticker_id, issuer, tier FROM universe ORDER BY tier, ticker_id"],
    [
      "SELECT ticker_id, ts, depth_weighted_price, dev_vs_median_pct, " +
        "qualifying_depth_usd, pools_used FROM deviations " +
        "ORDER BY ts DESC, id DESC LIMIT 500",
    ],
    [
      "SELECT issuer, status, window_note_en, next_open_at, observed_at " +
        "FROM redemption_windows ORDER BY observed_at DESC LIMIT 20",
    ],
    [
      "SELECT issuer, age_hours, last_update_ts, checked_at " +
        "FROM por_feeds ORDER BY checked_at DESC LIMIT 20",
    ],
    [
      "SELECT p.ticker_id, p.dex, s.price_usd, s.reserve_usd " +
        "FROM pools p JOIN snapshots s ON s.pool_id = p.pool_id " +
        "WHERE p.is_active = 1 AND s.ts = (SELECT MAX(ts) FROM snapshots s2 " +
        "WHERE s2.pool_id = p.pool_id) ORDER BY s.reserve_usd DESC",
    ],
    [
      "SELECT (SELECT COUNT(*) FROM pools WHERE is_active = 1) AS total, " +
        "COUNT(DISTINCT pool_id) AS live FROM snapshots " +
        "WHERE ts = (SELECT MAX(ts) FROM snapshots)",
    ],
    ["SELECT cycle_ts, cycles_ok FROM poller_health ORDER BY id DESC LIMIT 1"],
    [
      "SELECT ticker_id, ts, dev_vs_median_pct FROM deviations " +
        "WHERE ts >= datetime('now', '-1 hour') AND dev_vs_median_pct IS NOT NULL " +
        "ORDER BY ticker_id, ts",
    ],
  ]);

  const uni = rowsOf(uniR);
  const latest = firstPerTicker(rowsOf(devR));
  const redByIssuer = {};
  for (const r of rowsOf(redR)) {
    if (!(r.issuer in redByIssuer)) redByIssuer[r.issuer] = r;
  }
  const porByIssuer = {};
  for (const r of rowsOf(porR)) {
    if (!(r.issuer in porByIssuer)) porByIssuer[r.issuer] = r;
  }
  const venuesByTicker = {};
  for (const r of rowsOf(snapR)) {
    (venuesByTicker[r.ticker_id] ||= []).push(r);
  }
  const seriesByTicker = {};
  for (const r of rowsOf(seriesR)) {
    (seriesByTicker[r.ticker_id] ||= []).push(r);
  }
  const vl = rowsOf(venuesLiveR)[0] || {};
  const health = rowsOf(healthR)[0] || null;

  let latestTs = null;
  const tickers = uni.map((u) => {
    const d = latest[u.ticker_id] || {};
    const dw = d.depth_weighted_price ?? null;
    const dev = d.dev_vs_median_pct ?? null;
    const bps = dev != null ? dev * 100 : null;
    const vlist = (venuesByTicker[u.ticker_id] || []).filter(
      (v) => v.price_usd != null && (v.reserve_usd || 0) >= LIQ_MIN,
    );
    const best = vlist[0] || null;
    const red = redByIssuer[u.issuer] || null;
    const por = porByIssuer[u.issuer] || null;
    const series = (seriesByTicker[u.ticker_id] || []).map((s) => s.dev_vs_median_pct);
    const spark = series.slice(-12);
    const change =
      series.length >= 2 ? (series[series.length - 1] - series[0]) * 100 : null;
    if (d.ts && (!latestTs || d.ts > latestTs)) latestTs = d.ts;
    const status =
      bps == null ? "na" : Math.abs(bps) > 100 ? "alert" : Math.abs(bps) > 50 ? "watch" : "ok";
    return {
      ticker: u.ticker_id,
      tier: u.tier,
      issuer: u.issuer,
      dw_price: dw,
      dev_pct: dev,
      dev_bps: bps,
      best_price: best ? best.price_usd : null,
      best_dex: best ? best.dex : null,
      spread_pct: crossVenueSpread(venuesByTicker[u.ticker_id] || [], dw),
      depth_usd: d.qualifying_depth_usd ?? null,
      pools_used: d.pools_used ?? null,
      redemption_status: red ? String(red.status).toLowerCase() : null,
      redemption_next_open: red ? red.next_open_at : null,
      redemption_note_en: red ? red.window_note_en : null,
      por_age_hours: por ? por.age_hours : null,
      por_last_update: por ? por.last_update_ts : null,
      spark_bps: spark.map((v) => v * 100),
      change_1h_bps: change,
      status,
    };
  });

  return {
    tickers,
    meta: {
      latest_ts: latestTs,
      venues_live: vl.live != null ? Number(vl.live) : 0,
      venues_total: vl.total != null ? Number(vl.total) : 0,
      poller_last_cycle: health ? health.cycle_ts : null,
    },
  };
}

async function loadHistory(env, ticker, window) {
  const hours = window === "7d" ? 168 : window === "24h" ? 24 : 1;
  let sql;
  if (hours >= 24) {
    sql =
      "SELECT ticker_id, strftime('%Y-%m-%dT%H:00:00Z', ts) AS bucket, " +
      "AVG(dev_vs_median_pct) AS dev FROM deviations " +
      "WHERE ticker_id = ? AND ts >= datetime('now', '-" + hours + " hours') " +
      "AND dev_vs_median_pct IS NOT NULL " +
      "GROUP BY ticker_id, bucket ORDER BY bucket ASC";
  } else {
    sql =
      "SELECT ticker_id, ts, dev_vs_median_pct AS dev FROM deviations " +
      "WHERE ticker_id = ? AND ts >= datetime('now', '-1 hour') " +
      "AND dev_vs_median_pct IS NOT NULL ORDER BY ts ASC";
  }
  const [res] = await pipeline(env, [[sql, [ticker]]]);
  const points = rowsOf(res).map((r) => ({
    ts: r.ts || r.bucket,
    dev_bps: r.dev != null ? r.dev * 100 : null,
  }));
  return { ticker, window, points };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Cache-Control": "no-store",
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return json({}, 204);
    try {
      if (url.pathname === "/api/latest") {
        return json(await loadLatest(env));
      }
      if (url.pathname === "/api/history") {
        const ticker = (url.searchParams.get("ticker") || "").toUpperCase();
        const window = url.searchParams.get("window") || "1h";
        if (!ticker || !/^[A-Z0-9]+X$/.test(ticker))
          return json({ error: "ticker required, e.g. ?ticker=TSLAx" }, 400);
        if (!["1h", "24h", "7d"].includes(window))
          return json({ error: "window must be 1h, 24h or 7d" }, 400);
        return json(await loadHistory(env, ticker, window));
      }
      if (url.pathname === "/api/health") {
        const { meta } = await loadLatest(env);
        const ageMin = meta.latest_ts
          ? (Date.now() - Date.parse(meta.latest_ts)) / 60000
          : null;
        return json({
          latest_ts: meta.latest_ts,
          poller_last_cycle: meta.poller_last_cycle,
          age_minutes: ageMin != null ? Math.round(ageMin * 10) / 10 : null,
          fresh: ageMin != null && ageMin <= 15,
          venues_live: meta.venues_live,
          venues_total: meta.venues_total,
        });
      }
      return json({ error: "unknown route; see /api/latest, /api/history, /api/health" }, 404);
    } catch (e) {
      return json({ error: "upstream read failed" }, 502);
    }
  },
};
