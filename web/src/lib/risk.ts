/* Weekend risk score v1 — verbatim port of dashboard/risk.py.
 * Formula: deviation |dev_pct|*10 capped 40; depth 0 at >=$2.5M, 25 at
 * <=$250k, linear between; redemption closed=20, gated=10, open=0,
 * unknown/None excluded (not zeroed); PoR 15*age/72 capped 15, None
 * excluded. Total normalized to 0-100 over available maxima.
 * ALWAYS labeled "experimental" until calibrated on >= 8 weekends. */
export type RiskScore = {
  components: {
    deviation: number | null;
    depth: number | null;
    redemption: number | null;
    por: number | null;
  };
  total: number;
  max_possible: number;
  score_100: number | null;
  components_present: number;
  partial: boolean;
};

const DEPTH_FLOOR = 250_000;
const DEPTH_FULL = 2_500_000;

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

/** Python round(x, 1) semantics (banker's rounding) — JS Math.round
 *  is half-up and would differ by 0.1 on exact .05 boundaries. */
function pyRound1(x: number): number {
  const m = x * 10;
  const f = Math.floor(m);
  const diff = m - f;
  if (diff > 0.5) return (f + 1) / 10;
  if (diff < 0.5) return f / 10;
  return (f % 2 === 0 ? f : f + 1) / 10;
}

export function weekendRiskScore(
  devPct: number | null,
  depthUsd: number | null,
  redemptionStatus: string | null,
  porAgeHours: number | null,
): RiskScore {
  const deviation = devPct == null ? null : pyRound1(clamp(Math.abs(devPct) * 10, 0, 40));
  let depth: number | null = null;
  if (depthUsd != null) {
    if (depthUsd <= DEPTH_FLOOR) depth = 25;
    else if (depthUsd >= DEPTH_FULL) depth = 0;
    else depth = pyRound1(25 * (1 - (depthUsd - DEPTH_FLOOR) / (DEPTH_FULL - DEPTH_FLOOR)));
  }
  const redMap: Record<string, number> = { closed: 20, gated: 10, open: 0 };
  const redemption =
    redemptionStatus == null ? null : (redMap[redemptionStatus.trim().toLowerCase()] ?? null);
  const por =
    porAgeHours == null
      ? null
      : porAgeHours >= 72
        ? 15
        : pyRound1((15 * Math.max(porAgeHours, 0)) / 72);
  const comps = { deviation, depth, redemption, por };
  const maxima = { deviation: 40, depth: 25, redemption: 20, por: 15 };
  const avail = (Object.keys(comps) as (keyof typeof comps)[]).filter((k) => comps[k] != null);
  const total = Math.round(avail.reduce((s, k) => s + (comps[k] ?? 0), 0) * 10) / 10;
  const maxPossible = avail.reduce((s, k) => s + maxima[k], 0);
  return {
    components: comps,
    total,
    max_possible: maxPossible,
    score_100: maxPossible ? Math.round((total / maxPossible) * 1000) / 10 : null,
    components_present: avail.length,
    partial: avail.length < 4,
  };
}
