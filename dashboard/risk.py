"""Weekend risk score v1 (design §5.5) — pure functions, no I/O.

Formula (documented interpretation where the design leaves a gap):
- deviation component: |dev_pct| * 10 points, capped at 40.
  Input is |dev_vs_median_pct| in median-only mode (vs-close is NULL
  until the data license is resolved); the caller MUST label this.
- depth component: 0 at qualifying depth >= $2.5M, 25 at <= $250k
  (the §5.2 alert floor), linear in between. Thinner = higher.
- redemption component: closed = 20, gated = 10, open = 0,
  unknown/None = NOT counted (excluded, not zeroed).
- PoR component: age >= 72h = 15, else linear 15 * age / 72.
  None = NOT counted (excluded, not zeroed).
Total = sum of available components; max_possible = sum of the maxima
of available components (65 when redemption + PoR are both unknown).
v3.2 normalizes to 0-100 (score_100 = total / max_possible * 100) so
tickers with different missing components are comparable — the raw
total / max_possible pair is kept for backward compatibility, and a
partial score always reports how many of the 4 components are present.
The score is ALWAYS labeled "experimental" until calibrated on >= 8
weekends (design §5.5). Method version: weekend_risk_v1.
"""
METHOD_VERSION = "weekend_risk_v1"

DEPTH_FLOOR = 250_000.0
DEPTH_FULL = 2_500_000.0


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def dev_component(dev_pct):
    if dev_pct is None:
        return None
    return round(_clamp(abs(dev_pct) * 10.0, 0.0, 40.0), 1)


def depth_component(depth_usd):
    if depth_usd is None:
        return None
    if depth_usd <= DEPTH_FLOOR:
        return 25.0
    if depth_usd >= DEPTH_FULL:
        return 0.0
    return round(25.0 * (1.0 - (depth_usd - DEPTH_FLOOR) / (DEPTH_FULL - DEPTH_FLOOR)), 1)


def redemption_component(status):
    mapping = {"closed": 20.0, "gated": 10.0, "open": 0.0}
    if status is None:
        return None
    return mapping.get(str(status).strip().lower())


def por_component(age_hours):
    if age_hours is None:
        return None
    if age_hours >= 72.0:
        return 15.0
    return round(15.0 * max(age_hours, 0.0) / 72.0, 1)


def weekend_risk_score(dev_pct, depth_usd, redemption_status, por_age_hours):
    """Returns dict with components, total, max_possible, the 0-100
    normalized score, component counts, and the partial flag."""
    comps = {
        "deviation": dev_component(dev_pct),
        "depth": depth_component(depth_usd),
        "redemption": redemption_component(redemption_status),
        "por": por_component(por_age_hours),
    }
    maxima = {"deviation": 40.0, "depth": 25.0, "redemption": 20.0, "por": 15.0}
    avail = {k: v for k, v in comps.items() if v is not None}
    total = round(sum(avail.values()), 1)
    max_possible = sum(maxima[k] for k in avail)
    score_100 = (round(total / max_possible * 100.0, 1)
                 if max_possible else None)
    return {
        "components": comps,
        "total": total,
        "max_possible": max_possible,
        "score_100": score_100,
        "components_present": len(avail),
        "components_total": 4,
        "partial": len(avail) < 4,
        "method_version": METHOD_VERSION,
    }
