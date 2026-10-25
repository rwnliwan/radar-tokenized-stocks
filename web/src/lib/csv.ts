/* Pure CSV builder for the homepage export (no DOM inside, so it is
 * unit-testable with node). Columns are raw analyst numbers, mirroring
 * the Streamlit v3.2 CSV export — not the on-screen display strings. */
import type { TickerRow } from "./api";

function cell(v: string | number | null | undefined): string {
  if (v == null) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

export function buildCsv(rows: TickerRow[]): string {
  const header = [
    "ticker",
    "tier",
    "dw_price",
    "dev_bps",
    "spread_pct",
    "depth_usd",
    "pools_used",
    "redemption_status",
    "por_age_hours",
    "status",
    "change_1h_bps",
  ];
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push(
      [
        cell(r.ticker),
        cell(r.tier),
        cell(r.dw_price),
        cell(r.dev_bps),
        cell(r.spread_pct),
        cell(r.depth_usd),
        cell(r.pools_used),
        cell(r.redemption_status),
        cell(r.por_age_hours),
        cell(r.status),
        cell(r.change_1h_bps),
      ].join(","),
    );
  }
  return lines.join("\n") + "\n";
}
