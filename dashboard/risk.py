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

Calibration counter (gap R8 P2-G1, built 2026-11-09): the "8
weekends" claim previously had no counter or state anywhere, so the
label could never transition on repository-visible evidence. The
counter below is the missing capability — it counts distinct
weekends (Saturday-anchored) with at least one observed data day,
from actual data dates. It does NOT change the score or its formula;
it only reports progress toward 8, and the label stays experimental
until the count reaches 8. Data starts 2026-10-24 (a Saturday), so
the first observed weekend is 2026-10-24/25.
"""
from datetime import date, datetime, timedelta

METHOD_VERSION = "weekend_risk_v1"

DATA_START_DATE = date(2026, 10, 24)
CALIBRATION_WEEKENDS_REQUIRED = 8

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


# M5 (fix ronde review DeepSeek Radar, 2026-11-13): a stored Exit Score
# is only shown with a firm band when at least 3 of its 5 components
# were present (deviations.exit_score_components, added by the
# migration). Fewer than 3 — or a missing column (None, migration not
# run yet) — means the score is PARTIAL: the number is shown with a
# "partial" label and NO low/medium/high band, so a rescaled score
# from 1-2 components is never read as a full verdict. Mirrors the
# Worker's handling (api/worker.js: absent column -> null).
EXIT_SCORE_FULL_COMPONENTS = 3
EXIT_SCORE_TOTAL_COMPONENTS = 5


def exit_score_partial(components_present):
    """True when a stored exit score must be shown as partial (M5):
    fewer than EXIT_SCORE_FULL_COMPONENTS of the 5 components present,
    or the components column does not exist yet (None), or an
    unparseable value. Never raises."""
    if components_present is None:
        return True
    try:
        return int(components_present) < EXIT_SCORE_FULL_COMPONENTS
    except (TypeError, ValueError):
        return True


# --- Exit Score bands (design §2.3, display only) --------------------
# The score itself is computed by the poller and stored in
# deviations.exit_score + exit_score_version; this helper only maps a
# STORED score to its display band. Bands are labels, not advice:
# 0-39 "low exit pressure", 40-69 "medium", 70-100 "high". None (or a
# value outside 0-100) maps to None — a missing score is never shown
# as 0, and an impossible score is never banded.
def exit_score_band(score):
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s < 0 or s > 100:
        return None
    if s < 40:
        return "low"
    if s < 70:
        return "medium"
    return "high"


# --- Calibration counter (gap R8 P2-G1) --------------------------------
def _as_date(value):
    """Coerce a date / datetime / 'YYYY-MM-DD' (or ISO datetime) string
    to a date, or None when unparseable. Pure, never raises."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(
                text.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def weekend_key(d):
    """The Saturday that starts the weekend containing date `d`
    (Saturday/Sunday only; returns None for weekdays)."""
    if d is None or d.weekday() < 5:
        return None
    return d - timedelta(days=d.weekday() - 5)


def calibration_progress(observed_dates, now=None):
    """Progress toward the >= 8 weekends calibration of the weekend
    risk score, counted from ACTUAL observed data dates (e.g. the
    distinct successful-cycle dates in poller_health).

    `observed_dates`: iterable of date / datetime / ISO-string days
    with data. A weekend counts when at least one Saturday or Sunday
    in it is observed; Sat+Sun of one weekend count as ONE weekend
    (weekend_days_observed reports the day count separately).

    Dates before DATA_START_DATE (no data can exist) and dates after
    `now` (future-dated rows must not inflate the count) are ignored,
    as are unparseable values. Never raises.

    Returns {"weekends_observed", "weekend_days_observed", "required",
    "remaining", "calibrated", "progress_pct", "data_start",
    "observed_weekends": [ISO Saturdays, sorted]}. The score stays
    experimental until calibrated is True; this function never changes
    the score itself.
    """
    now_d = _as_date(now) if now is not None else date.today()
    weekends = set()
    days = set()
    for raw in observed_dates or []:
        d = _as_date(raw)
        if d is None:
            continue
        if d < DATA_START_DATE:
            continue
        if now_d is not None and d > now_d:
            continue
        if d.weekday() < 5:
            continue
        days.add(d)
        key = d - timedelta(days=d.weekday() - 5)
        weekends.add(key)
    observed = sorted(weekends)
    n = len(observed)
    return {
        "weekends_observed": n,
        "weekend_days_observed": len(days),
        "required": CALIBRATION_WEEKENDS_REQUIRED,
        "remaining": max(CALIBRATION_WEEKENDS_REQUIRED - n, 0),
        "calibrated": n >= CALIBRATION_WEEKENDS_REQUIRED,
        "progress_pct": round(
            min(n / CALIBRATION_WEEKENDS_REQUIRED, 1.0) * 100.0, 1),
        "data_start": DATA_START_DATE.isoformat(),
        "observed_weekends": [d.isoformat() for d in observed],
    }
