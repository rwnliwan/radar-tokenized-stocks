/* Types for the radar-api Worker (see ../api/worker.js). */

export type TickerRow = {
  ticker: string;
  tier: number | null;
  issuer: string;
  dw_price: number | null;
  dev_pct: number | null;
  dev_bps: number | null;
  best_price: number | null;
  best_dex: string | null;
  spread_pct: number | null;
  depth_usd: number | null;
  pools_used: number | null;
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
  };
};

export async function fetchLatest(signal?: AbortSignal): Promise<LatestResponse> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) throw new Error("API base URL is not configured");
  const res = await fetch(`${base}/api/latest`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`API HTTP ${res.status}`);
  return (await res.json()) as LatestResponse;
}
