/* Exit Score partial inference for the homepage (opsi B, 2026-11-13).
   Same 5-component model as the poller's exit_score_v2 (total 100),
   re-derived from one /api/latest row so the homepage can show WHY a
   score is partial — never from a new score computation. The stored
   score itself is never recomputed or rescaled here.
   RULE: the inferred present-count MUST equal the stored
   exit_score_components (self-check, see inferExitScoreComponents).
   On any mismatch — or when the stored count is null — the caller
   shows only the stored count ("n of 5 components") and NEVER names
   a missing component. */

export type ExitScoreComponentId =
  | "deviation"
  | "depth"
  | "redemption"
  | "funding"
  | "oi";

export type ExitScoreMissingReason =
  | "no_data"
  | "no_perp_market"
  | "stale_perp_feed"
  | "oi_history_short"
  | "redemption_unknown";

export type ExitScoreMissing = {
  id: ExitScoreComponentId;
  reason: ExitScoreMissingReason;
};

export type ExitScorePartialInfo = {
  /** Stored component count, coerced (Turso INTEGERs arrive as strings). */
  stored: number | null;
  /** Components present per the inference rules below. */
  inferred: number;
  /** True only when stored != null && stored === inferred. Only then
      may the caller name the missing components. */
  verified: boolean;
  present: ExitScoreComponentId[];
  missing: ExitScoreMissing[];
};

/* A perp snapshot counts as fresh when it is within 15 minutes of the
   row's own deviation timestamp — the same <=15 min window the poller
   applies in _latest_perp_by_ticker when sourcing funding/OI for the
   stored score (poller.py, F3 comment). An unparseable timestamp is
   never fresh. */
export const PERP_FRESH_MS = 15 * 60 * 1000;

/* OI needs a perp snapshot >=24h old (the poller compares current OI
   against _oi_24h_ago_batch). The Hyperliquid XYZ perp feed started
   2026-11-12T13:32:00Z — Turso MIN(ts) over perp_snapshots, verified
   13 Nov 2026 — so before 2026-11-13T13:32:00Z no ticker can have
   24h of perp history and the OI component is always absent, even
   when perp_oi itself is non-null. */
export const PERP_OI_HISTORY_CUTOFF_MS = Date.parse("2026-11-13T13:32:00Z");

const REDEMPTION_KNOWN = new Set(["open", "closed", "paused", "gated"]);

/* The Worker returns the newest perp snapshot WITHOUT a freshness
   filter, so perp_ts == null means no perp row ever existed for this
   ticker (no perp market), not merely a stale feed. */
function parseTs(s: string | null | undefined): number | null {
  if (!s) return null;
  const ms = Date.parse(s);
  return Number.isFinite(ms) ? ms : null;
}

/* Turso returns INTEGER columns as strings over the wire; the Worker
   may pass the value through unconverted, so accept both. */
function coerceComponents(v: number | string | null | undefined): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/* Only the fields the inference reads; TickerRow (and TickerDetail)
   are both assignable. */
export type ExitScoreRow = {
  dev_pct: number | null;
  dev_bps: number | null;
  depth_usd: number | null;
  redemption_status: string | null;
  perp_funding: number | null;
  perp_oi: number | null;
  perp_ts: string | null;
  dev_ts: string | null;
  exit_score_components: number | string | null;
};

export function inferExitScoreComponents(
  row: ExitScoreRow,
  nowMs: number = Date.now(),
): ExitScorePartialInfo {
  const present: ExitScoreComponentId[] = [];
  const missing: ExitScoreMissing[] = [];

  // 1. Deviation — present when either deviation reading exists.
  if (row.dev_pct != null || row.dev_bps != null) present.push("deviation");
  else missing.push({ id: "deviation", reason: "no_data" });

  // 2. Depth — present when qualifying depth exists. The poller also
  // needs the 7-day median (absent for brand-new tickers, e.g. AMZNr,
  // whose stored count is 1 while this rule infers 2); that gap is
  // caught by the self-check below, never guessed here.
  if (row.depth_usd != null) present.push("depth");
  else missing.push({ id: "depth", reason: "no_data" });

  // 3. Redemption — present when the issuer publishes a known status.
  const red = (row.redemption_status ?? "").trim().toLowerCase();
  if (REDEMPTION_KNOWN.has(red)) present.push("redemption");
  else missing.push({ id: "redemption", reason: "redemption_unknown" });

  // 4. Funding + 5. OI share the latest perp snapshot.
  const perpMs = parseTs(row.perp_ts);
  const devMs = parseTs(row.dev_ts);
  const perpFresh =
    perpMs != null && devMs != null && Math.abs(perpMs - devMs) <= PERP_FRESH_MS;

  if (row.perp_funding != null && perpFresh) {
    present.push("funding");
  } else {
    missing.push({
      id: "funding",
      reason:
        row.perp_ts == null
          ? "no_perp_market"
          : !perpFresh
            ? "stale_perp_feed"
            : "no_data",
    });
  }

  if (row.perp_oi != null && nowMs >= PERP_OI_HISTORY_CUTOFF_MS) {
    present.push("oi");
  } else {
    missing.push({
      id: "oi",
      reason:
        row.perp_ts == null
          ? "no_perp_market"
          : !perpFresh
            ? "stale_perp_feed"
            : nowMs < PERP_OI_HISTORY_CUTOFF_MS
              ? "oi_history_short"
              : "no_data",
    });
  }

  const stored = coerceComponents(row.exit_score_components);
  const inferred = present.length;
  return {
    stored,
    inferred,
    verified: stored != null && stored === inferred,
    present,
    missing,
  };
}
