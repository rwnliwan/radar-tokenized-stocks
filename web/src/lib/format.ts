/* Shared formatters (moved verbatim from the Stage 1 homepage). */
import type { Lang } from "./i18n";
import { t } from "./i18n";

export type Status = "ok" | "watch" | "alert" | "na";

export function statusLabel(lang: Lang, s: Status): string {
  if (s === "ok") return t(lang, "status_ok");
  if (s === "watch") return t(lang, "status_watch");
  if (s === "alert") return t(lang, "status_alert");
  return "—";
}

export function redLabel(lang: Lang, s: string | null): string {
  if (s === "open") return t(lang, "red_status_open");
  if (s === "closed") return t(lang, "red_status_closed");
  if (s === "gated") return t(lang, "red_status_gated");
  if (s === "paused") return t(lang, "red_status_paused");
  return t(lang, "redemption_unknown");
}

export function redPill(s: string | null): string {
  if (s === "open") return "open";
  if (s === "closed") return "closed";
  if (s === "gated") return "gated";
  if (s === "paused") return "paused";
  return "na";
}

export const BLOCKS = "▁▂▃▄▅▆▇█";

export function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "—";
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtDepth(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
}

export function fmtSigned1(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}`;
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n.toFixed(2)}%`;
}

/** PoR age: minutes below one hour (rows would otherwise all read 0h,
 *  since the hourly poller fetches every token in one slot), hours above. */
export function fmtAge(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  return `${Math.round(hours)}h`;
}

export function sparkBlocks(series: number[]): string {
  if (series.length < 2) return "—";
  const lo = Math.min(...series);
  const hi = Math.max(...series);
  if (hi === lo) return "▅".repeat(series.length);
  return series
    .map((v) => BLOCKS[Math.min(7, Math.floor(((v - lo) / (hi - lo)) * 7))])
    .join("");
}

export function fmtWITA(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const locale = lang === "id" ? "id-ID" : "en-GB";
  return (
    new Intl.DateTimeFormat(locale, {
      timeZone: "Asia/Makassar",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d) + " WITA"
  );
}

/** NYSE regular schedule, Mon–Fri 09:30–16:00 America/New_York.
 *  Exchange holidays are NOT tracked — the same documented limitation
 *  as the Streamlit dashboard's market_is_open. */
export function marketIsOpen(now: Date = new Date()): boolean {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const wd = get("weekday");
  if (wd === "Sat" || wd === "Sun") return false;
  const mins = Number(get("hour")) * 60 + Number(get("minute"));
  return mins >= 9 * 60 + 30 && mins < 16 * 60;
}
