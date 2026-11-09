/* Types for the radar-api Worker (see ../api/worker.js). */

export type TickerRow = {
  ticker: string;
  tier: number | null;
  issuer: string;
  dw_price: number | null;
  dev_pct: number | null;
  dev_bps: number | null;
  // M1 (fix ronde 7): per-ticker freshness — the row's own deviations
  // timestamp, not just the global poller verdict in meta.
  dev_ts: string | null;
  dev_age_min?: number | null;
  stale: boolean;
  best_price: number | null;
  best_dex: string | null;
  spread_pct: number | null;
  depth_usd: number | null;
  pools_used: number | null;
  // Gap R9: the Worker returns pools_excluded per row (loadLatest);
  // null when the column is absent from the DB.
  pools_excluded: number | null;
  redemption_status: string | null;
  redemption_next_open: string | null;
  redemption_note_en: string | null;
  por_age_hours: number | null;
  por_last_update: string | null;
  spark_bps: number[];
  change_1h_bps: number | null;
  status: "ok" | "watch" | "alert" | "na";
};

export type LatestResponse = {
  tickers: TickerRow[];
  meta: {
    latest_ts: string | null;
    venues_live: number;
    venues_total: number;
    poller_last_cycle: string | null;
    // Freshness contract (fix ronde 5, M4): mirrored from /api/health.
    cycles_ok?: number | null;
    failed_streak?: number;
    last_success_ts?: string | null;
    stale?: boolean;
    fresh?: boolean;
    // S15 (fix ronde 8): the Worker returns stale_tickers in meta.
    stale_tickers?: string[];
  };
};

export async function fetchLatest(signal?: AbortSignal): Promise<LatestResponse> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) throw new Error("API base URL is not configured");
  const res = await fetch(`${base}/api/latest`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`API HTTP ${res.status}`);
  return (await res.json()) as LatestResponse;
}

export type HealthResponse = {
  latest_ts: string | null;
  poller_last_cycle: string | null;
  age_minutes: number | null;
  fresh: boolean;
  stale: boolean;
  cycles_ok: number | null;
  failed_streak: number;
  last_success_ts: string | null;
  venues_live: number;
  venues_total: number;
};

/* Freshness contract (fix ronde 5, M4): the homepage banner uses the
   Worker's /api/health verdict (age since last SUCCESSFUL cycle +
   failed streak), not a locally computed snapshot age. */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) throw new Error("API base URL is not configured");
  const res = await fetch(`${base}/api/health`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`API HTTP ${res.status}`);
  return (await res.json()) as HealthResponse;
}

export type AlertRow = {
  ticker: string;
  ts: string;
  type: string;
  // S14 (fix ronde 8): the Worker returns the delivery channel per
  // feed row (since R7); the type now declares it.
  channel: string | null;
  figure: number | null;
};

export type AlertsResponse = {
  alerts: AlertRow[];
};

export async function fetchAlerts(signal?: AbortSignal): Promise<AlertsResponse> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) throw new Error("API base URL is not configured");
  const res = await fetch(`${base}/api/alerts`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`API HTTP ${res.status}`);
  return (await res.json()) as AlertsResponse;
}

export type VenueRow = {
  dex: string;
  chain: string;
  pair_address: string | null;
  price_usd: number | null;
  reserve_usd: number | null;
  volume_24h_usd: number | null;
  ts: string | null;
  qualifies: boolean;
};

export type TickerDetail = {
  ticker: string;
  issuer: string;
  underlying: string | null;
  legal_type: string | null;
  tier: number | null;
  dw_price: number | null;
  dev_pct: number | null;
  dev_bps: number | null;
  // M1 (fix ronde 7): per-ticker freshness + S9: the canonical global
  // health verdict, carried by the detail response itself.
  dev_ts: string | null;
  dev_age_min: number | null;
  stale: boolean;
  health_stale: boolean | null;
  health_fresh: boolean | null;
  health_last_success_ts: string | null;
  health_failed_streak: number | null;
  best_price: number | null;
  best_dex: string | null;
  spread_pct: number | null;
  depth_usd: number | null;
  pools_used: number | null;
  pools_excluded: number;
  redemption_status: string | null;
  redemption_next_open: string | null;
  redemption_note_en: string | null;
  redemption_note: string | null;
  redemption_observed_at: string | null;
  redemption_source: string | null;
  por_age_hours: number | null;
  por_last_update: string | null;
  por_feed_address: string | null;
  por_note: string | null;
  por_shares_held: string | null;
  por_supply: string | null;
  por_token_last_update: string | null;
  spark_bps: number[];
  change_1h_bps: number | null;
  change_24h_bps: number | null;
  change_7d_bps: number | null;
  status: "ok" | "watch" | "alert" | "na";
  venues: VenueRow[];
  latest_ts: string | null;
};

export async function fetchTicker(
  ticker: string,
  signal?: AbortSignal,
): Promise<TickerDetail> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) throw new Error("API base URL is not configured");
  const res = await fetch(`${base}/api/ticker?ticker=${encodeURIComponent(ticker)}`, {
    cache: "no-store",
    signal,
  });
  if (res.status === 404) throw new Error("NOT_FOUND");
  if (!res.ok) throw new Error(`API HTTP ${res.status}`);
  return (await res.json()) as TickerDetail;
}

export type HistoryPoint = { ts: string; dev_bps: number | null };

export async function fetchHistory(
  ticker: string,
  window: "1h" | "24h" | "7d",
  signal?: AbortSignal,
): Promise<HistoryPoint[]> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) throw new Error("API base URL is not configured");
  const res = await fetch(
    `${base}/api/history?ticker=${encodeURIComponent(ticker)}&window=${window}`,
    { cache: "no-store", signal },
  );
  if (!res.ok) throw new Error(`API HTTP ${res.status}`);
  const d = (await res.json()) as { points: HistoryPoint[] };
  return d.points;
}

export type WaitlistPayload = {
  contact: string;
  position: string;
  venues: string;
  price?: string;
  consent: true;
  /** Honeypot: always "" from the real form; a filled value is a bot. */
  website?: string;
};

export type WaitlistResult = { ok: true; already: boolean };

export async function postWaitlist(p: WaitlistPayload): Promise<WaitlistResult> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) throw new Error("API base URL is not configured");
  const res = await fetch(`${base}/api/waitlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  });
  const d = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    already?: boolean;
    error?: string;
  };
  if (!res.ok || !d.ok) throw new Error(d.error || `API HTTP ${res.status}`);
  return { ok: true, already: !!d.already };
}
