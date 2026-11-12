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

// Per-ticker staleness threshold (fix ronde 7, M1): the SAME 15-min
// bound as healthSummary, applied to each ticker's OWN deviations
// row instead of the global poller verdict. A ticker whose row is
// older than this (or missing/unparseable) is stale even when the
// poller as a whole is fresh.
const TICKER_STALE_MIN = 15;

function tickerFreshness(devTs) {
  const parsed = devTs != null ? Date.parse(devTs) : NaN;
  const ageMin = Number.isFinite(parsed)
    ? (Date.now() - parsed) / 60000
    : null;
  // GG-15 (fix ronde 8, P2-M1): a future timestamp is stale, never
  // fresh. The old code clamped the age to 0 (Math.max(0, ...)), so a
  // future dev_ts read as fresh until wall-clock time passed it. A
  // negative age is reported as-is, so the anomaly stays visible.
  const stale = ageMin == null || ageMin < 0 || ageMin > TICKER_STALE_MIN;
  return {
    dev_ts: devTs ?? null,
    dev_age_min: ageMin != null ? Math.round(ageMin * 10) / 10 : null,
    stale,
  };
}

// Re-evaluate freshness of an already-built /api/latest payload at
// serve time (fix ronde 7, S1): a 60 s edge-cache HIT used to return
// the previously computed meta.fresh/meta.stale verbatim, so a
// response cached just before the 15-min boundary could be served as
// fresh up to 60 s past it. Recomputing from the stored timestamps
// (last_success_ts + per-ticker dev_ts) costs no DB read and bounds
// the overshoot to zero.
function reevaluateFreshness(payload) {
  const meta = payload.meta || {};
  const parsed =
    meta.last_success_ts != null ? Date.parse(meta.last_success_ts) : NaN;
  const ageMin = Number.isFinite(parsed) ? (Date.now() - parsed) / 60000 : null;
  // GG-15 (fix ronde 8, P2-M1): a future last_success_ts is stale.
  const stale = ageMin == null || ageMin < 0 || ageMin > 15 || (meta.failed_streak ?? 0) >= 2;
  const tickers = (payload.tickers || []).map((t) => {
    const tf = tickerFreshness(t.dev_ts ?? null);
    return { ...t, dev_age_min: tf.dev_age_min, stale: tf.stale };
  });
  return {
    ...payload,
    tickers,
    meta: {
      ...meta,
      age_minutes: ageMin != null ? Math.round(ageMin * 10) / 10 : null,
      stale,
      fresh: !stale,
      stale_tickers: tickers.filter((t) => t.stale).map((t) => t.ticker),
    },
  };
}

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

// Price-sanity guard — the SAME rule as the poller guard, bot.py
// guarded_venues and qa_harness.py: with >=3 venues, drop prices
// deviating >25% from the cross-venue median; <3 venues = no consensus,
// guard skipped; if the exclusion would empty the set, fall back to all.
// Added 2026-11-08 (Q6 vote A, 3-0; ACC Septian 10:40): before this,
// crossVenueSpread used raw ticks, so one bad tick (SPYx $0.1044 on
// 2026-11-06, reserve $1.24M) showed a 100.041% spread on the web and
// fed the "caution" verdict, while the poller had already excluded that
// pool from dw. The Telegram alert side was fixed the same day in bot.py.
function median(values) {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function guardedPrices(prices) {
  if (prices.length < 3) return prices;
  const med = median(prices);
  if (!med) return prices;
  const kept = prices.filter((p) => Math.abs(p - med) / med <= 0.25);
  return kept.length ? kept : prices;
}

function crossVenueSpread(venues, dw) {
  const prices = venues
    .filter((v) => v.price_usd != null && (v.reserve_usd || 0) >= LIQ_MIN)
    .map((v) => v.price_usd);
  if (prices.length < 2 || !dw) return null;
  const guarded = guardedPrices(prices);
  return ((Math.max(...guarded) - Math.min(...guarded)) / dw) * 100;
}

// PoR effective age (fix ronde 6, S-new-8): the stored age_hours is
// written by the hourly poller job, so if that job fails repeatedly
// the stored value freezes — possibly below the 72h alert threshold
// while last_update_ts is already older than 72h. The effective age
// is the max of the stored age and the age recomputed live from
// last_update_ts. Same rule as bot.py load_live_tickers and
// dashboard/logic.py por_effective_age_hours. Returns null when
// neither source yields an age.
function porEffectiveAge(por) {
  if (!por) return null;
  let eff = por.age_hours != null ? Number(por.age_hours) : null;
  if (eff != null && !Number.isFinite(eff)) eff = null;
  if (por.last_update_ts) {
    const parsed = Date.parse(por.last_update_ts);
    if (Number.isFinite(parsed)) {
      // GG-15 (fix ronde 8): a future last_update is not evidence of
      // age 0 — it is ignored, so the stored age stands (or null
      // stays null). The old code clamped the live age to 0.
      const liveMs = Date.now() - parsed;
      if (liveMs >= 0) {
        const live = liveMs / 3600000;
        eff = eff == null ? live : Math.max(eff, live);
      }
    }
  }
  return eff;
}

// Shared freshness contract (fix ronde 5, M4): ONE definition used by
// /api/health, /api/latest meta, dashboard/logic.py freshness_status,
// and (with its own 30-min gate) the Telegram bot's stale gate.
// Input: newest-first poller_health rows {cycle_ts, cycles_ok}.
// Age is anchored on the last SUCCESSFUL cycle (cycles_ok = 1): a
// failed cycle writes a fresh-timestamped row, so anchoring on the
// newest row understates data age — the old /api/health did exactly
// that, and the old bot gate was blind the same way. stale = no success
// ever, or age > 15 min, or >= 2 consecutive failed cycles.
function healthSummary(health) {
  let failedStreak = 0;
  let lastSuccessTs = null;
  let cyclesOk = null;
  if (health.length) {
    cyclesOk = health[0].cycles_ok;
    for (const h of health) {
      if (Number(h.cycles_ok) === 1) {
        lastSuccessTs = h.cycle_ts;
        break;
      }
      failedStreak += 1;
    }
  }
  // S-new-3 (fix ronde 6): a malformed last_success_ts must read as
  // stale, never as fresh. Date.parse returns NaN on garbage, and
  // NaN is neither null nor > 15, so the old code returned
  // stale: false + age_minutes: null — self-contradictory, and the
  // opposite of dashboard/logic.py freshness_status (parse failure
  // -> None -> stale) and bot.py load_health_age_minutes. A
  // non-finite parse is now treated exactly like "no success ever".
  const parsed =
    lastSuccessTs != null ? Date.parse(lastSuccessTs) : NaN;
  const ageMin = Number.isFinite(parsed)
    ? (Date.now() - parsed) / 60000
    : null;
  // GG-15 (fix ronde 8, P2-M1): a future last_success_ts is stale.
  // The S-new-3 comment above fixed the malformed-past direction;
  // the malformed-future direction is its mirror.
  const stale = ageMin == null || ageMin < 0 || ageMin > 15 || failedStreak >= 2;
  return {
    cycles_ok: cyclesOk,
    failed_streak: failedStreak,
    last_success_ts: lastSuccessTs,
    age_minutes: ageMin != null ? Math.round(ageMin * 10) / 10 : null,
    stale,
    fresh: !stale,
  };
}

async function loadLatest(env) {
  // Gap R9 (CSV pools_excluded): /api/latest rows carry the column
  // the poller writes, probed via PRAGMA like loadTicker (the column
  // is declared in schema.sql since fix ronde 9, P1-4 — the probe
  // keeps a fresh DB without it from failing the whole endpoint).
  // Same probe pattern covers the 2026-11-12 additions: exit_score /
  // exit_score_version columns on deviations and the perp_snapshots
  // table. While the migration has not run, both read as null and the
  // frontends render "not available yet" — never 0.
  let hasExcluded = false;
  let hasExitScore = false;
  let hasExitVersion = false;
  try {
    const [pragma] = await pipeline(env, [["PRAGMA table_info(deviations)"]]);
    const cols = rowsOf(pragma).map((c) => c.name);
    hasExcluded = cols.includes("pools_excluded");
    hasExitScore = cols.includes("exit_score");
    hasExitVersion = cols.includes("exit_score_version");
  } catch {
    hasExcluded = false;
    hasExitScore = false;
    hasExitVersion = false;
  }
  // Separate probe (separate try): a failure here must never poison
  // the column flags above — a missing/unreadable perp table only
  // means "no perp data", it must not also drop pools_excluded.
  let hasPerp = false;
  try {
    const [perpCheck] = await pipeline(env, [
      ["SELECT 1 AS x FROM sqlite_master WHERE type = 'table' "
        + "AND name = 'perp_snapshots' LIMIT 1"],
    ]);
    hasPerp = rowsOf(perpCheck).length > 0;
  } catch {
    hasPerp = false;
  }
  const devSql =
    "SELECT ticker_id, ts, depth_weighted_price, dev_vs_median_pct, " +
    "qualifying_depth_usd, pools_used" +
    (hasExcluded ? ", pools_excluded" : "") +
    (hasExitScore ? ", exit_score" : "") +
    (hasExitVersion ? ", exit_score_version" : "") +
    " FROM deviations " +
    // LIMIT 500 capacity (fix ronde 5, N5): 13 tickers x ~38 cycles
    // (~3.2h at the 5-min cadence) — the newest row per ticker
    // always survives inside the window. Revisit if the universe
    // grows a lot.
    "ORDER BY ts DESC, id DESC LIMIT 500";
  // The perp statement is appended only when the table exists, so a
  // DB without the migration keeps the exact 8-statement shape.
  const latestStmts = [
    ["SELECT ticker_id, issuer, tier FROM universe ORDER BY tier, ticker_id"],
    [devSql],
    [
      "SELECT issuer, status, window_note_en, next_open_at, observed_at " +
        "FROM redemption_windows ORDER BY observed_at DESC LIMIT 20",
    ],
    [
      "SELECT issuer, age_hours, last_update_ts, checked_at " +
        "FROM por_feeds ORDER BY checked_at DESC LIMIT 20",
    ],
    [
      // P2-M2 (fix ronde 8): anchor each ticker to ITS OWN latest
      // snapshot, not the global latest. The old
      // s.ts = (SELECT MAX(ts) FROM snapshots) dropped Tier 2 tickers
      // (AAPLx, MSFTx) in the 4-of-5 minutes when only the tight-loop
      // Tier 1 tickers had a snapshot at the global minute — they lost
      // venues and sometimes vanished from /api/latest entirely. The
      // 2026-10-30 read-burn premise ("all pools written in one batch
      // ts") never held for Tier 2, which the poller writes only on
      // 5-minute marks. The derived table scans only the last 2 h
      // via idx_snapshots_ts, grouped by ticker — bounded, not the
      // old per-row correlated scan.
      "SELECT p.ticker_id, p.dex, s.price_usd, s.reserve_usd " +
        "FROM pools p JOIN snapshots s ON s.pool_id = p.pool_id " +
        "JOIN (SELECT p2.ticker_id AS tid, MAX(s2.ts) AS mts " +
        "FROM pools p2 JOIN snapshots s2 ON s2.pool_id = p2.pool_id " +
        "WHERE s2.ts >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-2 hours') " +
        "GROUP BY p2.ticker_id) latest " +
        "ON latest.tid = p.ticker_id AND s.ts = latest.mts " +
        "WHERE p.is_active = 1 " +
        "ORDER BY s.reserve_usd DESC",
    ],
    [
      // P2-M2 (fix ronde 8): same per-ticker anchor as above — the
      // old COUNT at the single global MAX(ts) dipped to ~25/35 on
      // off-minutes because Tier 2 pools had no snapshot at that
      // minute. A pool counts as live when it has a snapshot at its
      // own ticker's latest ts within the last 2 h.
      "SELECT (SELECT COUNT(*) FROM pools WHERE is_active = 1) AS total, " +
        "COUNT(DISTINCT s.pool_id) AS live FROM snapshots s " +
        "JOIN pools p ON p.pool_id = s.pool_id " +
        "JOIN (SELECT p2.ticker_id AS tid, MAX(s2.ts) AS mts " +
        "FROM pools p2 JOIN snapshots s2 ON s2.pool_id = p2.pool_id " +
        "WHERE s2.ts >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-2 hours') " +
        "GROUP BY p2.ticker_id) latest " +
        "ON latest.tid = p.ticker_id AND s.ts = latest.mts " +
        "WHERE p.is_active = 1",
    ],
    ["SELECT cycle_ts, cycles_ok FROM poller_health ORDER BY id DESC LIMIT 12"],
    [
      "SELECT ticker_id, ts, dev_vs_median_pct FROM deviations " +
        "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour') " +
        "AND dev_vs_median_pct IS NOT NULL " +
        "ORDER BY ticker_id, ts",
    ],
  ];
  if (hasPerp) {
    // Latest-only via idx_perp_ticker_ts, same first-per-ticker
    // fold as deviations (LIMIT 200 covers the 10 perp tickers for
    // ~100 minutes at the 5-min cadence).
    latestStmts.push([
      "SELECT ticker_id, ts, perp_px, funding, oi FROM perp_snapshots "
        + "ORDER BY ts DESC LIMIT 200",
    ]);
  }
  const latestRes = await pipeline(env, latestStmts);
  const [uniR, devR, redR, porR, snapR, venuesLiveR, healthR, seriesR] =
    latestRes;
  const perpR = hasPerp ? latestRes[8] : null;

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
  // Latest perp snapshot per ticker (first row wins — the query is
  // ts-DESC). Absent entirely when the table does not exist yet.
  const perpByTicker = {};
  if (perpR) {
    for (const r of rowsOf(perpR)) {
      if (!(r.ticker_id in perpByTicker)) perpByTicker[r.ticker_id] = r;
    }
  }
  const vl = rowsOf(venuesLiveR)[0] || {};
  const health = rowsOf(healthR);
  const hs = healthSummary(health);

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
    // M1 (fix ronde 7): per-ticker staleness — the global health
    // verdict in meta must NOT be the only freshness signal. A ticker
    // whose own deviations row stopped updating while the poller
    // stayed healthy for the other 12 used to be served as fresh for
    // up to ~3.2 h (the LIMIT 500 window). Each row now carries its
    // own dev_ts / dev_age_min / stale, and meta lists stale tickers.
    const tf = tickerFreshness(d.ts ?? null);
    // Exit Score / perp are nullable by design: null means "not
    // available yet" (no column / no snapshot), never 0.
    const perp = perpByTicker[u.ticker_id] || null;
    const perpDev =
      perp && perp.perp_px != null && dw
        ? ((perp.perp_px - dw) / dw) * 100
        : null;
    return {
      ticker: u.ticker_id,
      tier: u.tier,
      issuer: u.issuer,
      dw_price: dw,
      dev_pct: dev,
      dev_bps: bps,
      dev_ts: tf.dev_ts,
      dev_age_min: tf.dev_age_min,
      stale: tf.stale,
      best_price: best ? best.price_usd : null,
      best_dex: best ? best.dex : null,
      spread_pct: crossVenueSpread(venuesByTicker[u.ticker_id] || [], dw),
      depth_usd: d.qualifying_depth_usd ?? null,
      pools_used: d.pools_used ?? null,
      pools_excluded: hasExcluded ? (d.pools_excluded ?? null) : null,
      exit_score: hasExitScore ? (d.exit_score ?? null) : null,
      exit_score_version: hasExitVersion
        ? (d.exit_score_version ?? null)
        : null,
      perp_px: perp ? (perp.perp_px ?? null) : null,
      perp_dev_pct: perpDev,
      perp_funding: perp ? (perp.funding ?? null) : null,
      perp_oi: perp ? (perp.oi ?? null) : null,
      perp_ts: perp ? (perp.ts ?? null) : null,
      redemption_status: red ? String(red.status).toLowerCase() : null,
      redemption_next_open: red ? red.next_open_at : null,
      redemption_note_en: red ? red.window_note_en : null,
      por_age_hours: porEffectiveAge(por),
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
      poller_last_cycle: health.length ? health[0].cycle_ts : null,
      // Freshness contract (M4): same fields as /api/health.
      cycles_ok: hs.cycles_ok,
      failed_streak: hs.failed_streak,
      last_success_ts: hs.last_success_ts,
      stale: hs.stale,
      fresh: hs.fresh,
      stale_tickers: tickers.filter((t) => t.stale).map((t) => t.ticker),
    },
  };
}

async function loadHealthMeta(env) {
  // 2026-11-04 read-burn fix: /api/health (dipoll UptimeRobot tiap ~5 mnt)
  // dulu memanggil loadLatest() penuh (~40K reads: scan 1 jam deviations
  // 39K baris index). Health cuma butuh sinyal freshness -> satu pipeline
  // murah (~200 reads). Bentuk JSON response TIDAK berubah — kecuali
  // penambahan field kontrak freshness (M4, 2026-11-08): cycles_ok,
  // failed_streak, last_success_ts, stale (lihat healthSummary).
  const [r, hR] = await pipeline(env, [
    [
      "SELECT (SELECT MAX(ts) FROM snapshots) AS latest_ts, " +
        "(SELECT COUNT(*) FROM pools WHERE is_active = 1) AS total, " +
        // P2-M2 (fix ronde 8): per-ticker anchor, as in loadLatest —
        // the old COUNT at the single global MAX(ts) dipped on
        // off-minutes when Tier 2 pools had no snapshot at that minute.
        "(SELECT COUNT(DISTINCT s.pool_id) FROM snapshots s " +
        "JOIN pools p ON p.pool_id = s.pool_id " +
        "JOIN (SELECT p2.ticker_id AS tid, MAX(s2.ts) AS mts " +
        "FROM pools p2 JOIN snapshots s2 ON s2.pool_id = p2.pool_id " +
        "WHERE s2.ts >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-2 hours') " +
        "GROUP BY p2.ticker_id) latest " +
        "ON latest.tid = p.ticker_id AND s.ts = latest.mts " +
        "WHERE p.is_active = 1) AS live, " +
        "(SELECT cycle_ts FROM poller_health ORDER BY id DESC LIMIT 1) AS plc",
    ],
    ["SELECT cycle_ts, cycles_ok FROM poller_health ORDER BY id DESC LIMIT 12"],
  ]);
  const row = rowsOf(r)[0] || {};
  const hs = healthSummary(rowsOf(hR));
  return {
    latest_ts: row.latest_ts || null,
    venues_live: row.live != null ? Number(row.live) : 0,
    venues_total: row.total != null ? Number(row.total) : 0,
    poller_last_cycle: row.plc || null,
    cycles_ok: hs.cycles_ok,
    failed_streak: hs.failed_streak,
    last_success_ts: hs.last_success_ts,
    age_minutes: hs.age_minutes,
    stale: hs.stale,
    fresh: hs.fresh,
  };
}

async function loadHistory(env, ticker, window) {
  const hours = window === "7d" ? 168 : window === "24h" ? 24 : 1;
  let sql;
  if (hours >= 24) {
    sql =
      "SELECT ticker_id, strftime('%Y-%m-%dT%H:00:00Z', ts) AS bucket, " +
      "AVG(dev_vs_median_pct) AS dev FROM deviations " +
      "WHERE ticker_id = ? COLLATE NOCASE AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-" + hours + " hours') " +
      "AND dev_vs_median_pct IS NOT NULL " +
      "GROUP BY ticker_id, bucket ORDER BY bucket ASC";
  } else {
    sql =
      "SELECT ticker_id, ts, dev_vs_median_pct AS dev FROM deviations " +
      "WHERE ticker_id = ? COLLATE NOCASE AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour') " +
      "AND dev_vs_median_pct IS NOT NULL ORDER BY ts ASC";
  }
  const [res] = await pipeline(env, [[sql, [ticker]]]);
  const points = rowsOf(res).map((r) => ({
    ts: r.ts || r.bucket,
    dev_bps: r.dev != null ? r.dev * 100 : null,
  }));
  return { ticker, window, points };
}

async function loadTicker(env, ticker) {
  // pools_excluded is declared in schema.sql (fix ronde 9, P1-4 —
  // the live DB already had it via an undocumented ALTER). Probe
  // first so a fresh DB without the column cannot fail the main
  // pipeline. Same probe covers the 2026-11-12 additions: the
  // exit_score columns and the perp_snapshots table — absent means
  // null fields, never a fabricated score.
  let hasExcluded = false;
  let hasExitScore = false;
  let hasExitVersion = false;
  try {
    const [pragma] = await pipeline(env, [["PRAGMA table_info(deviations)"]]);
    const cols = rowsOf(pragma).map((c) => c.name);
    hasExcluded = cols.includes("pools_excluded");
    hasExitScore = cols.includes("exit_score");
    hasExitVersion = cols.includes("exit_score_version");
  } catch {
    hasExcluded = false;
    hasExitScore = false;
    hasExitVersion = false;
  }
  // Separate probe (separate try): a failure here must never poison
  // the column flags above (see loadLatest).
  let hasPerp = false;
  try {
    const [perpCheck] = await pipeline(env, [
      ["SELECT 1 AS x FROM sqlite_master WHERE type = 'table' "
        + "AND name = 'perp_snapshots' LIMIT 1"],
    ]);
    hasPerp = rowsOf(perpCheck).length > 0;
  } catch {
    hasPerp = false;
  }
  const anchor = (hours) => [
    "SELECT dev_vs_median_pct FROM deviations WHERE ticker_id = ? COLLATE NOCASE " +
      "AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-" + hours + " hours') " +
      "AND dev_vs_median_pct IS NOT NULL ORDER BY ts ASC LIMIT 1",
    [ticker],
  ];
  // Stage 1: everything except the per-pool snapshots — in particular
  // the latest deviations row, whose ts anchors stage 2.
  const stage1 = [
    [
      "SELECT ticker_id, issuer, underlying, legal_type, tier FROM universe " +
        "WHERE ticker_id = ? COLLATE NOCASE",
      [ticker],
    ],
    [
      "SELECT ts, depth_weighted_price, dev_vs_median_pct, qualifying_depth_usd, " +
        "pools_used" +
        (hasExitScore ? ", exit_score" : "") +
        (hasExitVersion ? ", exit_score_version" : "") +
        " FROM deviations WHERE ticker_id = ? COLLATE NOCASE " +
        "ORDER BY ts DESC, id DESC LIMIT 1",
      [ticker],
    ],
    [
      "SELECT status, window_note, window_note_en, observed_at, source, next_open_at " +
        "FROM redemption_windows " +
        "WHERE issuer = (SELECT issuer FROM universe WHERE ticker_id = ? COLLATE NOCASE) " +
        "ORDER BY observed_at DESC LIMIT 1",
      [ticker],
    ],
    [
      "SELECT feed_address, last_update_ts, age_hours, reserves_vs_supply_note " +
        "FROM por_feeds " +
        "WHERE issuer = (SELECT issuer FROM universe WHERE ticker_id = ? COLLATE NOCASE) " +
        "ORDER BY checked_at DESC LIMIT 1",
      [ticker],
    ],
    [
      "SELECT ts, dev_vs_median_pct FROM deviations WHERE ticker_id = ? COLLATE NOCASE " +
        "AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour') " +
        "AND dev_vs_median_pct IS NOT NULL ORDER BY ts ASC",
      [ticker],
    ],
    anchor(1),
    anchor(24),
    anchor(168),
    // S9 (fix ronde 7): the detail response carries the canonical
    // global health verdict itself, so the page never has to decide
    // fresh/stale from snapshot age when its /api/health fetch fails.
    ["SELECT cycle_ts, cycles_ok FROM poller_health ORDER BY id DESC LIMIT 12"],
  ];
  const res1 = await pipeline(env, stage1);
  const uni = rowsOf(res1[0])[0];
  if (!uni) return null;
  const d = rowsOf(res1[1])[0] || {};
  const red = rowsOf(res1[2])[0] || null;
  const por = rowsOf(res1[3])[0] || null;
  const series = rowsOf(res1[4]).map((s) => s.dev_vs_median_pct);
  const firstOf = (i) => {
    const r = rowsOf(res1[i])[0];
    return r ? r.dev_vs_median_pct : null;
  };
  const hs = healthSummary(rowsOf(res1[8]));
  // Stage 2: per-pool snapshots anchored to the SAME cycle ts as the
  // deviations row (S6, fix ronde 7 — same mixed-cycle pattern
  // S-new-9 fixed in the bot). The old per-pool MAX(ts) combined
  // another cycle's venue prices with this cycle's depth-weighted
  // price. When there is no deviations row (no ts to anchor on),
  // fall back to the old per-pool MAX(ts) pattern.
  const devTs = d.ts ?? null;
  const venueSql = devTs
    ? "SELECT p.dex, p.chain, p.pair_address, s.price_usd, s.reserve_usd, " +
      "s.volume_24h_usd, s.ts FROM pools p JOIN snapshots s ON s.pool_id = p.pool_id " +
      "WHERE p.ticker_id = ? COLLATE NOCASE AND p.is_active = 1 " +
      "AND s.ts = ? " +
      "ORDER BY s.reserve_usd DESC"
    : "SELECT p.dex, p.chain, p.pair_address, s.price_usd, s.reserve_usd, " +
      "s.volume_24h_usd, s.ts FROM pools p JOIN snapshots s ON s.pool_id = p.pool_id " +
      "WHERE p.ticker_id = ? COLLATE NOCASE AND p.is_active = 1 " +
      "AND s.ts = (SELECT MAX(ts) FROM snapshots s2 WHERE s2.pool_id = p.pool_id) " +
      "ORDER BY s.reserve_usd DESC";
  const venueArgs = devTs ? [ticker, devTs] : [ticker];
  const stage2 = [[venueSql, venueArgs]];
  if (hasExcluded) {
    stage2.push([
      "SELECT pools_excluded FROM deviations WHERE ticker_id = ? COLLATE NOCASE " +
        "ORDER BY ts DESC, id DESC LIMIT 1",
      [ticker],
    ]);
  }
  // PoR v2: latest per-token snapshot.
  const tokIdx = stage2.length;
  stage2.push([
    "SELECT ts, shares_held, circulating_supply FROM por_token_snapshots " +
      "WHERE ticker_id = ? COLLATE NOCASE ORDER BY checked_at DESC, id DESC LIMIT 1",
    [ticker],
  ]);
  // Perp 3-leg: latest snapshot for this ticker, latest-only via
  // idx_perp_ticker_ts. Appended only when the table exists.
  let perpIdx = -1;
  if (hasPerp) {
    perpIdx = stage2.length;
    stage2.push([
      "SELECT ts, perp_px, funding, oi FROM perp_snapshots "
        + "WHERE ticker_id = ? COLLATE NOCASE ORDER BY ts DESC LIMIT 1",
      [ticker],
    ]);
  }
  const res2 = await pipeline(env, stage2);
  const venues = rowsOf(res2[0]).map((v) => ({
    dex: v.dex,
    chain: v.chain,
    pair_address: v.pair_address,
    price_usd: v.price_usd,
    reserve_usd: v.reserve_usd,
    volume_24h_usd: v.volume_24h_usd,
    ts: v.ts,
    qualifies: v.reserve_usd != null && v.reserve_usd >= LIQ_MIN,
  }));
  const tok = rowsOf(res2[tokIdx])[0] || null;
  const dw = d.depth_weighted_price ?? null;
  // Perp 3-leg (2026-11-12): null when the table is missing, no
  // snapshot was ever written, or this ticker has no perp market —
  // all three render as "not available yet", never 0.
  const perp = perpIdx >= 0 ? rowsOf(res2[perpIdx])[0] || null : null;
  const perpDev =
    perp && perp.perp_px != null && dw
      ? ((perp.perp_px - dw) / dw) * 100
      : null;
  const dev = d.dev_vs_median_pct ?? null;
  const bps = dev != null ? dev * 100 : null;
  const change = (anchorVal) =>
    anchorVal != null && dev != null ? (dev - anchorVal) * 100 : null;
  const status =
    bps == null ? "na" : Math.abs(bps) > 100 ? "alert" : Math.abs(bps) > 50 ? "watch" : "ok";
  const best = venues.filter((v) => v.qualifies && v.price_usd != null)[0] || null;
  // M1 (fix ronde 7): per-ticker staleness, same 15-min bound as
  // loadLatest; health_* is the canonical global verdict (S9).
  const tf = tickerFreshness(devTs);
  return {
    ticker: uni.ticker_id,
    issuer: uni.issuer,
    underlying: uni.underlying,
    legal_type: uni.legal_type,
    tier: uni.tier,
    dw_price: dw,
    dev_pct: dev,
    dev_bps: bps,
    dev_ts: tf.dev_ts,
    dev_age_min: tf.dev_age_min,
    stale: tf.stale,
    health_stale: hs.stale,
    health_fresh: hs.fresh,
    health_last_success_ts: hs.last_success_ts,
    health_failed_streak: hs.failed_streak,
    best_price: best ? best.price_usd : null,
    best_dex: best ? best.dex : null,
    spread_pct: crossVenueSpread(venues, dw),
    depth_usd: d.qualifying_depth_usd ?? null,
    pools_used: d.pools_used ?? null,
    pools_excluded: hasExcluded ? (rowsOf(res2[1])[0]?.pools_excluded ?? 0) : 0,
    exit_score: hasExitScore ? (d.exit_score ?? null) : null,
    exit_score_version: hasExitVersion
      ? (d.exit_score_version ?? null)
      : null,
    perp_px: perp ? (perp.perp_px ?? null) : null,
    perp_dev_pct: perpDev,
    perp_funding: perp ? (perp.funding ?? null) : null,
    perp_oi: perp ? (perp.oi ?? null) : null,
    perp_ts: perp ? (perp.ts ?? null) : null,
    redemption_status: red ? String(red.status).toLowerCase() : null,
    redemption_next_open: red ? red.next_open_at : null,
    redemption_note_en: red ? red.window_note_en : null,
    redemption_note: red ? red.window_note : null,
    redemption_observed_at: red ? red.observed_at : null,
    redemption_source: red ? red.source : null,
    por_age_hours: porEffectiveAge(por),
    por_last_update: por ? por.last_update_ts : null,
    por_feed_address: por ? por.feed_address : null,
    por_note: por ? por.reserves_vs_supply_note : null,
    por_shares_held: tok ? tok.shares_held : null,
    por_supply: tok ? tok.circulating_supply : null,
    por_token_last_update: tok ? tok.ts : null,
    spark_bps: series.slice(-12).map((v) => v * 100),
    change_1h_bps: change(firstOf(5)),
    change_24h_bps: change(firstOf(6)),
    change_7d_bps: change(firstOf(7)),
    status,
    venues,
    latest_ts: d.ts ?? null,
  };
}

const WAITLIST_HOURLY_CAP = 500;

// Origins allowed to POST /api/waitlist from a browser. GET routes stay
// Access-Control-Allow-Origin: * (the data is intentionally public).
const WAITLIST_ORIGINS = [
  "https://radar.omdanny.site",
  "https://exit-radar.pages.dev",
];

async function handleWaitlist(request, env) {
  let body;
  try {
    const text = await request.text();
    if (text.length > 10000) return json({ error: "payload too large" }, 413);
    body = JSON.parse(text);
  } catch {
    return json({ error: "invalid JSON" }, 400);
  }
  // N1 (fix ronde 7): JSON.parse("null") succeeds, so a JSON null
  // body used to reach `body.contact` and throw a TypeError, which
  // the outer catch turned into a 502 "upstream read failed". A null
  // / array / non-object body is a client error: 400, not 502.
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "invalid JSON" }, 400);
  }
  // Reject cross-site browser POSTs outright: CORS alone would only hide
  // the response while the row still got inserted. No-Origin requests
  // (curl, non-browser) still pass — CORS cannot tell them apart, and
  // the zone rate limit is the abuse backstop for those.
  const origin = request.headers.get("Origin") || "";
  if (origin && !WAITLIST_ORIGINS.includes(origin)) {
    return json({ error: "forbidden origin" }, 403);
  }
  const contact = typeof body.contact === "string" ? body.contact.trim() : "";
  const position = typeof body.position === "string" ? body.position.trim() : "";
  const venues = typeof body.venues === "string" ? body.venues.trim() : "";
  const price = typeof body.price === "string" ? body.price.trim() : "";
  // Honeypot: the form renders an empty hidden "website" field no human
  // ever sees. A filled value means an autofill bot — reject generically
  // (never name the honeypot in the error).
  const website = typeof body.website === "string" ? body.website.trim() : "";
  // Contact must be reachable: an email address, or a Telegram username
  // (5–32 chars, letters/digits/underscore, optional leading @). Mirrors
  // the waitlist form's client-side check; the server check is the one
  // that keeps garbage out of the table.
  function validContact(c) {
    if (c.startsWith("@")) return /^[A-Za-z0-9_]{5,32}$/.test(c.slice(1));
    if (c.includes("@")) return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c);
    return /^[A-Za-z0-9_]{5,32}$/.test(c);
  }
  // Mirror the form validation (required contact/position/venues +
  // consent) plus length caps so one submission cannot bloat the table.
  if (
    website !== "" ||
    !contact ||
    contact.length > 200 ||
    !position ||
    position.length > 100 ||
    !venues ||
    venues.length > 300 ||
    price.length > 100 ||
    body.consent !== true
  ) {
    return json({ error: "validation failed" }, 400);
  }
  if (!validContact(contact)) {
    return json({ error: "invalid contact" }, 400);
  }
  const norm = contact.toLowerCase();
  const nowIso = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  // Hourly cap uses the strftime T-format window: created_at is stored
  // T-format, and datetime('now') returns space-format, which would
  // compare wrong (same class of bug as the Stage 1 series filter).
  //
  // S-new-2 (fix ronde 6): the cap used to be checked in a SEPARATE
  // pipeline before the INSERT, so two simultaneous submits for
  // DIFFERENT contacts could both read a count < 500 and both get
  // in — the cap was not atomic. The cap is now enforced INSIDE the
  // single INSERT statement itself (a D1 statement executes
  // atomically): the row is written only if the hourly count is
  // still below the cap AND the contact is not already listed.
  // rows_written === 0 is then disambiguated below: an existing
  // contact means an idempotent duplicate success, anything else
  // means the cap was hit (429). The dedup stays atomic exactly as
  // before (WHERE NOT EXISTS on the same statement).
  const [insRes] = await pipeline(env, [
    [
      "INSERT INTO waitlist (contact, position_size_usd, venues, willing_price, " +
        "created_at, consent) SELECT ?, ?, ?, ?, ?, ? WHERE " +
        "(SELECT COUNT(*) FROM waitlist WHERE created_at >= " +
        "strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour')) < ? " +
        "AND NOT EXISTS " +
        "(SELECT 1 FROM waitlist WHERE LOWER(TRIM(contact)) = ?)",
      [contact, position, venues, price || null, nowIso, 1,
       WAITLIST_HOURLY_CAP, norm],
    ],
  ]);
  if (insRes && insRes.rows_written === 0) {
    // The INSERT wrote nothing: either the contact already exists
    // (idempotent success) or the hourly cap was hit (rate limited).
    // One follow-up read decides which — the cap itself was already
    // enforced atomically above, so this read cannot admit a 501st row.
    const [existRes] = await pipeline(env, [
      ["SELECT id FROM waitlist WHERE LOWER(TRIM(contact)) = ? LIMIT 1", [norm]],
    ]);
    if (rowsOf(existRes).length) return json({ ok: true, already: true });
    return json({ error: "rate limited" }, 429);
  }
  return json({ ok: true, already: false });
}

// Coverage (2026-11-12): live rows are derived from the pools
// actually polled in Turso — chain x issuer x DEX, grouped. The
// PENDING rows are the one-off live-verification verdicts of 12 Nov
// 2026 (VERIFIKASI_MULTICHAIN_2026-11-12.md), reference data that is
// always dated and never presented as live: a chain moves to `live`
// only after its pools are seeded in Turso and polled. The
// only_solana_xstocks flag is derived the same way, so frontends
// never hardcode "only Solana".
const COVERAGE_VERDICT_DATE = "2026-11-12";
const DISPLAY_CHAINS = {
  solana: "Solana",
  base: "Base",
  bnb: "BNB Chain",
  robinhood: "Robinhood Chain",
  ethereum: "Ethereum",
  elysium: "Elysium",
  hyperliquid: "Hyperliquid",
};
const DISPLAY_ISSUERS = {
  xstocks: "xStocks",
  coinbase: "Coinbase",
  bstocks: "bStocks",
  robinhood: "Robinhood",
  ondo: "Ondo",
  "xstocks-wrapped": "xStocks (wrapped)",
};
const PENDING_COVERAGE = [
  {
    chain: "base",
    issuer: "coinbase",
    platforms: "Aerodrome / Uniswap / Nami",
    tokens: "NVDAc (verified); MSTRc, SNDKc + 10 more (to verify)",
    verdict: "verified",
    reason_key: "cov_reason_base",
  },
  {
    chain: "bnb",
    issuer: "bstocks",
    platforms: "PancakeSwap / Uniswap / Metric",
    tokens: "TSLAB (verified); NVDAB, SPYB, QQQB + more (to verify)",
    verdict: "verified",
    reason_key: "cov_reason_bnb",
  },
  {
    chain: "robinhood",
    issuer: "robinhood",
    platforms: "Uniswap / Aerodrome / Metric / Ramses",
    tokens: "TSLA, NVDA, SPY (verified); 10 more (to verify)",
    verdict: "verified",
    reason_key: "cov_reason_robinhood",
  },
  {
    chain: "ethereum",
    issuer: "ondo",
    platforms: "Uniswap",
    tokens: "TSLAon, NVDAon, SPYon, AAPLON",
    verdict: "failed",
    reason_key: "cov_reason_ondo",
  },
  {
    chain: "elysium",
    issuer: "xstocks",
    platforms: "—",
    tokens: "TSLAx + 12 more (announced)",
    verdict: "not_active",
    reason_key: "cov_reason_elysium",
  },
  {
    chain: "hyperliquid",
    issuer: "xstocks-wrapped",
    platforms: "Hyperliquid spot",
    tokens: "TSLAX, NVDAX, SPYX, AAPLX (wrapped)",
    verdict: "monitor",
    reason_key: "cov_reason_hyperliquid",
  },
];

async function loadCoverage(env) {
  // The pools table is tiny (35 rows live): one grouped read, no
  // big-table scan (the §6.3 read-burn rule).
  const [poolsR] = await pipeline(env, [
    [
      "SELECT p.chain AS chain, p.dex AS dex, p.ticker_id AS ticker_id, "
        + "u.issuer AS issuer FROM pools p "
        + "JOIN universe u ON u.ticker_id = p.ticker_id "
        + "WHERE p.is_active = 1",
    ],
  ]);
  const groups = new Map();
  const tickers = new Set();
  for (const r of rowsOf(poolsR)) {
    const chain = String(r.chain || "").trim().toLowerCase();
    const issuer = String(r.issuer || "").trim().toLowerCase();
    if (!chain || !issuer) continue;
    const key = chain + "|" + issuer;
    if (!groups.has(key)) {
      groups.set(key, {
        chain,
        chain_display: DISPLAY_CHAINS[chain] || chain,
        issuer,
        issuer_display: DISPLAY_ISSUERS[issuer] || issuer,
        dexes: new Set(),
        tickers: new Set(),
        pools: 0,
        status: "live",
      });
    }
    const g = groups.get(key);
    if (r.dex) g.dexes.add(String(r.dex));
    if (r.ticker_id) {
      g.tickers.add(String(r.ticker_id));
      tickers.add(String(r.ticker_id));
    }
    g.pools += 1;
  }
  const live = [...groups.values()]
    .map((g) => ({
      ...g,
      dexes: [...g.dexes].sort(),
      tickers: [...g.tickers].sort(),
    }))
    .sort((a, b) =>
      a.chain === b.chain
        ? a.issuer.localeCompare(b.issuer)
        : a.chain.localeCompare(b.chain),
    );
  const chains = new Set(live.map((g) => g.chain));
  const issuers = new Set(live.map((g) => g.issuer));
  return {
    live,
    pending: PENDING_COVERAGE.map((p) => ({
      ...p,
      chain_display: DISPLAY_CHAINS[p.chain] || p.chain,
      issuer_display: DISPLAY_ISSUERS[p.issuer] || p.issuer,
    })),
    verdict_date: COVERAGE_VERDICT_DATE,
    live_tickers: tickers.size,
    live_pools: live.reduce((s, g) => s + g.pools, 0),
    only_solana_xstocks:
      live.length > 0 &&
      chains.size === 1 &&
      chains.has("solana") &&
      issuers.size === 1 &&
      issuers.has("xstocks"),
    generated_at: new Date().toISOString(),
  };
}

async function loadAlerts(env) {
  // S7 (fix ronde 7): one alert_log row is written PER CHANNEL since
  // ronde 6, so an EN+ID delivery appeared twice as indistinguishable
  // entries and consumed 2 of the 30 feed slots. Deduplicate by event
  // identity (ticker, alert_ts, alert_type) — keep the earliest row
  // per event (MIN(id)) and report its channel. The feed now shows
  // up to 30 distinct events.
  const [res] = await pipeline(env, [
    [
      "SELECT ticker_id, alert_ts, alert_type, channel, " +
        "COALESCE(dev_at_alert_pct, threshold_pct) AS figure " +
        "FROM alert_log WHERE id IN (SELECT MIN(id) FROM alert_log " +
        "GROUP BY ticker_id, alert_ts, alert_type) " +
        "ORDER BY alert_ts DESC, id ASC LIMIT 30",
      [],
    ],
  ]);
  return {
    alerts: rowsOf(res).map((r) => ({
      ticker: r.ticker_id,
      ts: r.alert_ts,
      type: r.alert_type,
      channel: r.channel ?? null,
      figure: r.figure != null ? Number(r.figure) : null,
    })),
  };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Cache-Control": "no-store",
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      // 204 must have a NULL body: new Response with a body + status 204
      // throws (this was error 1101 on every preflight, which broke the
      // waitlist POST from browsers). CORS headers still required.
      // Preflight: echo back ONLY an allowlisted waitlist origin. CORS
      // alone never stops a cross-site POST from executing (it only hides
      // the response), so handleWaitlist also rejects non-allowlisted
      // browser Origins outright; this just stops the browser earlier.
      const origin = request.headers.get("Origin") || "";
      const headers = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        Vary: "Origin",
      };
      if (WAITLIST_ORIGINS.includes(origin)) {
        headers["Access-Control-Allow-Origin"] = origin;
      }
      return new Response(null, { status: 204, headers });
    }
    try {
      if (url.pathname === "/api/latest") {
        // Edge cache (60s, GET only): the poller refreshes the underlying
        // data every 5 minutes, so a 60s-old snapshot is not meaningfully
        // staler — and repeat loads skip the full Turso pipeline, which
        // cost 1.3-1.9s per request (2026-10-27 baseline). X-Edge-Cache
        // marks HIT/MISS for verification. Other routes stay uncached.
        if (request.method === "GET") {
          const cache = caches.default;
          const cached = await cache.match(request);
          if (cached) {
            // S1 (fix ronde 7): a HIT must NOT return the cached
            // meta.fresh/meta.stale verbatim — the verdict may have
            // crossed the 15-min boundary inside the 60 s cache
            // window. Re-evaluate from the stored timestamps (no DB
            // read); the cached rows themselves stay as-is.
            const hitPayload = reevaluateFreshness(await cached.json());
            const hit = json(hitPayload);
            hit.headers.set("X-Edge-Cache", "HIT");
            return hit;
          }
          const fresh = json(await loadLatest(env));
          const toCache = new Response(fresh.body, fresh);
          toCache.headers.set("Cache-Control", "public, max-age=60");
          toCache.headers.set("X-Edge-Cache", "MISS");
          const put = cache.put(request, toCache.clone());
          if (ctx && ctx.waitUntil) ctx.waitUntil(put);
          else await put;
          return toCache;
        }
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
      if (url.pathname === "/api/ticker") {
        const ticker = (url.searchParams.get("ticker") || "").toUpperCase();
        if (!ticker || !/^[A-Z0-9]+X$/.test(ticker))
          return json({ error: "ticker required, e.g. ?ticker=TSLAx" }, 400);
        const detail = await loadTicker(env, ticker);
        if (!detail) return json({ error: "ticker not found" }, 404);
        return json(detail);
      }
      if (url.pathname === "/api/waitlist") {
        if (request.method !== "POST")
          return json({ error: "POST only" }, 405);
        return handleWaitlist(request, env);
      }
      if (url.pathname === "/api/coverage") {
        return json(await loadCoverage(env));
      }
      if (url.pathname === "/api/alerts") {
        return json(await loadAlerts(env));
      }
      if (url.pathname === "/api/health") {
        const meta = await loadHealthMeta(env);
        return json({
          latest_ts: meta.latest_ts,
          poller_last_cycle: meta.poller_last_cycle,
          age_minutes: meta.age_minutes,
          fresh: meta.fresh,
          stale: meta.stale,
          cycles_ok: meta.cycles_ok,
          failed_streak: meta.failed_streak,
          last_success_ts: meta.last_success_ts,
          venues_live: meta.venues_live,
          venues_total: meta.venues_total,
        });
      }
      return json({ error: "unknown route; see /api/latest, /api/coverage, /api/history, /api/alerts, /api/health" }, 404);
    } catch (e) {
      return json({ error: "upstream read failed" }, 502);
    }
  },
};
