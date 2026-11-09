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

/** Signed fixed-point without negative zero: a tiny negative that rounds
 *  to zero renders "+0.0", not "-0.0" (AAPLx showed "-0.0" bps). Only the
 *  negative-zero string changes; every other value keeps toFixed rounding.
 *  F2 (fix ronde 9, GG-17 central): a negative value rendered at RUNTIME
 *  uses U+2212 (minus sign), never ASCII hyphen-minus — toFixed emits
 *  "-" and the old code returned it verbatim. */
export function fmtSigned(n: number, digits: number): string {
  const s = n.toFixed(digits);
  const zero = "0." + "0".repeat(digits);
  if (s === "-" + zero) return "+" + zero;
  const body = s.startsWith("-") ? "−" + s.slice(1) : s;
  return `${n >= 0 ? "+" : ""}${body}`;
}

export function fmtSigned1(n: number | null | undefined): string {
  if (n == null) return "—";
  return fmtSigned(n, 1);
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  // F2 (fix ronde 9, GG-17): same U+2212 rule as fmtSigned — a
  // negative percent renders "−0.05%", never "-0.05%".
  const s = n.toFixed(2);
  return `${s.startsWith("-") ? "−" + s.slice(1) : s}%`;
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

// NYSE holidays (full closes). Same set as poller.py / bot.py /
// dashboard/logic.py — qa/test_r8_fix.py S11 asserts all four
// identical. 2028 is the official NYSE Group calendar (announced
// 2025-12-23): 9 closures; New Year's Day 2028 falls on a Saturday
// and is NOT observed. Review annually.
export const NYSE_HOLIDAYS = new Set([
  "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
  "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
  "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
  "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
  "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
  "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
]);

/** NYSE regular schedule, Mon–Fri 09:30–16:00 America/New_York.
 *  S12 (fix ronde 8): exchange holidays ARE tracked now — on a NYSE
 *  holiday the market reads closed, agreeing with the bot's
 *  holiday-aware gate and the dashboard. */
export function marketIsOpen(now: Date = new Date()): boolean {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const wd = get("weekday");
  if (wd === "Sat" || wd === "Sun") return false;
  const ymd = `${get("year")}-${get("month")}-${get("day")}`;
  if (NYSE_HOLIDAYS.has(ymd)) return false;
  const mins = Number(get("hour")) * 60 + Number(get("minute"));
  return mins >= 9 * 60 + 30 && mins < 16 * 60;
}
