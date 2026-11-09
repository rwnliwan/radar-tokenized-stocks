"""Pure dashboard logic (no Streamlit, no I/O) — unit-testable.

Freshness (design §6.3, unified contract 2026-11-08, fix ronde 5 M4):
stale when the last SUCCESSFUL poller cycle is older than 15 minutes
OR the last 2 cycles both failed. The age is anchored on the last
success, never on a failed cycle's timestamp — a failed cycle writes
a fresh-timestamped row, so anchoring on it would understate how old
the data really is. The same contract (age since last success,
failed_streak, stale) is exposed by /api/health and used by the public
frontend; the Telegram bot uses the same age with its own 30-min gate.
WITA = UTC + 8 (Asia/Makassar has no DST).
Best exit venue (design §6.1.8): deepest qualifying pool per size,
flagged when the size exceeds 5% of that pool's reserve. This is an
estimate from depth, never an execution promise.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LIQ_MIN = 100000.0  # qualifying pool: reserve >= $100k (same as poller
# LIQ_MIN, bot.py LIQ_MIN, api/worker.js LIQ_MIN).

# NYSE holidays (full closes). Same set as poller.py / bot.py /
# web/src/lib/format.ts — qa/test_r8_fix.py S11 asserts all four
# identical. 2028 is the official NYSE Group calendar (announced
# 2025-12-23): 9 closures; New Year's Day 2028 falls on a Saturday
# and is NOT observed. Review annually; the S11 guard trips when the
# calendar no longer covers through the end of next year.
NYSE_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
}

ET = ZoneInfo("America/New_York")


def is_nyse_day(dt_et):
    return dt_et.weekday() < 5 and dt_et.strftime("%Y-%m-%d") not in NYSE_HOLIDAYS


def market_is_open(now_utc):
    """NYSE regular schedule, Mon–Fri 09:30–16:00 America/New_York.

    S12 (fix ronde 8): exchange holidays ARE tracked now (moved here
    from app.py so the pure logic is unit-testable). The old version
    was weekday-only, so on Thanksgiving the dashboard said "market
    open" while the bot's holiday-aware gate sent no spread alerts.
    """
    ny = now_utc.astimezone(ET)
    if not is_nyse_day(ny):
        return False
    mins = ny.hour * 60 + ny.minute
    return 9 * 60 + 30 <= mins < 16 * 60

WITA = timezone(timedelta(hours=8))
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
             "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def parse_ts(iso):
    """Parse an ISO-8601 UTC timestamp ('...Z' or with offset) to aware UTC."""
    if iso is None:
        return None
    s = str(iso).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt_wita(iso, lang="en"):
    """'24 Oct 2026 19:11 WITA' (en) / '24 Okt 2026 19:11 WITA' (id).

    The space between time and zone is a non-breaking space (U+00A0)
    so the two can never collapse or wrap apart in rendering ('23:36
    WITA' must read as one stamp, never '23:36WITA').
    """
    dt = parse_ts(iso)
    if dt is None:
        return "—"
    w = dt.astimezone(WITA)
    months = MONTHS_ID if lang == "id" else MONTHS_EN
    return (f"{w.day} {months[w.month - 1]} {w.year} "
            f"{w.hour:02d}:{w.minute:02d} WITA")


def freshness_status(health_rows, now_utc):
    """health_rows: newest-first list of {cycle_ts, cycles_ok}.

    Returns {last_ts, last_cycle_ts, last_success_ts, age_min,
    failed_streak, stale}. last_ts is the last SUCCESSFUL cycle's ts
    (the honest "last updated" stamp); last_cycle_ts is the newest row
    whatever its outcome. Empty input, or no success at all -> stale
    (no heartbeat / no trustworthy data).
    """
    if not health_rows:
        return {"last_ts": None, "last_cycle_ts": None, "last_success_ts": None,
                "age_min": None, "failed_streak": 0, "stale": True}
    last_cycle_ts = parse_ts(health_rows[0].get("cycle_ts"))
    streak = 0
    last_success = None
    for row in health_rows:
        try:
            ok = int(row.get("cycles_ok") or 0)
        except (TypeError, ValueError):
            ok = 0
        if ok == 1:
            last_success = parse_ts(row.get("cycle_ts"))
            break
        streak += 1
    if last_success is None:
        return {"last_ts": None,
                "last_cycle_ts": health_rows[0].get("cycle_ts"),
                "last_success_ts": None, "age_min": None,
                "failed_streak": streak, "stale": True}
    age_min = (now_utc - last_success).total_seconds() / 60.0
    # GG-15 (fix ronde 8, P2-M1 dashboard half): a last-success
    # timestamp in the FUTURE is stale, never fresh — a negative age
    # used to pass the `age_min > 15` test and read as fresh.
    stale = age_min < 0 or age_min > 15.0 or streak >= 2
    last_success_ts = None
    for row in health_rows:
        try:
            ok = int(row.get("cycles_ok") or 0)
        except (TypeError, ValueError):
            ok = 0
        if ok == 1:
            last_success_ts = row.get("cycle_ts")
            break
    return {"last_ts": last_success_ts,
            "last_cycle_ts": health_rows[0].get("cycle_ts"),
            "last_success_ts": last_success_ts, "age_min": age_min,
            "failed_streak": streak, "stale": stale}


def fmt_abbr(v):
    """'$1.40M' / '$312K' / '$2.38B' or '—' for None. KPI cards only —
    tables keep the full comma format (v3 rule).

    F2 (fix ronde 9, GG-17): a negative value renders U+2212, never
    ASCII hyphen-minus. The magnitude test already used abs(); the
    formatted value itself did not — '$-1.40M' until this fix.
    """
    if v is None:
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(x) >= 1e9:
        s = f"${x / 1e9:,.2f}B"
    elif abs(x) >= 1e6:
        s = f"${x / 1e6:,.2f}M"
    elif abs(x) >= 1e3:
        s = f"${x / 1e3:,.0f}K"
    else:
        s = f"${x:,.0f}"
    return s.replace("-", "−")


PRICE_GUARD_MAX_DEV = 0.25  # price-sanity guard: drop prices >25%
# from the cross-venue median (same rule as the poller guard,
# bot.py guarded_venues, api/worker.js guardedPrices).


def guarded_prices(prices):
    """Prices after the 25%-from-median guard — the SAME rule as the
    poller guard (poller.py run_cycle), bot.py guarded_venues and
    api/worker.js guardedPrices: with >=3 prices, drop any price
    deviating >25% from the cross-venue median; with <3 prices no
    consensus exists, so the guard is skipped. If exclusion would
    empty the list, fall back to all prices. Pure: no I/O."""
    if len(prices) < 3:
        return list(prices)
    import statistics
    med = statistics.median(prices)
    if not med:
        return list(prices)
    kept = [p for p in prices
            if abs(p - med) / med <= PRICE_GUARD_MAX_DEV]
    return kept if kept else list(prices)


def cross_venue_spread(venues, dw_price):
    """(max - min qualifying venue price) / depth-weighted price, in %.

    Fix ronde 6 (M-new-1): the dashboard Streamlit app computed this
    WITHOUT the 25%-from-median guard the bot and Worker already use,
    so one bad tick on a qualifying pool (SPYx $0.1044, reserve
    $1.24M, 6 Nov 2026) showed ~100% here while bot/Worker showed
    0.168%. The spread is now computed on guarded_prices, mirroring
    api/worker.js crossVenueSpread exactly: qualifying filter
    (reserve >= LIQ_MIN) first, then the guard. Used by the master
    table and the ticker detail page (both go through this function).
    """
    prices = [float(v["price_usd"]) for v in venues
              if v.get("price_usd") is not None
              and (v.get("reserve_usd") or 0) >= LIQ_MIN]
    if len(prices) < 2 or not dw_price:
        return None
    guarded = guarded_prices(prices)
    return (max(guarded) - min(guarded)) / float(dw_price) * 100.0


def por_effective_age_hours(age_hours, last_update_ts, now_utc):
    """PoR age that cannot freeze below the truth (fix ronde 6,
    S-new-8): the stored age_hours is written by the hourly poller
    job, so if that job fails repeatedly the stored value freezes —
    possibly below the 72h alert threshold while last_update_ts is
    already older than 72h. The effective age is the max of the
    stored age and the age recomputed live from last_update_ts.
    Returns None when neither source yields an age."""
    eff = None
    try:
        eff = float(age_hours) if age_hours is not None else None
    except (TypeError, ValueError):
        eff = None
    if last_update_ts:
        lu = parse_ts(last_update_ts)
        if lu is not None:
            live = (now_utc - lu).total_seconds() / 3600.0
            # GG-15 (fix ronde 8): a FUTURE last_update is not evidence
            # of age 0 — it is ignored, so the stored age stands (or
            # None stays None). The old code clamped it to 0.0.
            if live >= 0:
                if eff is None:
                    eff = max(0.0, live)
                else:
                    eff = max(eff, live)
    return eff


def best_exit_venues(venue_rows, sizes=(1000, 5000, 10000)):
    """venue_rows: latest snapshot per pool with reserve_usd + dex + price.

    Returns one row per size: deepest QUALIFYING pool (reserve_usd >=
    LIQ_MIN, $100k — fix ronde 5, M3), flagged when size > 5% of its
    reserve. No qualifying pool -> [] (caller shows 'no data'): a
    sub-$100k pool must never be crowned "best exit venue" while the
    Worker reports best_price null for the same ticker.
    """
    usable = [v for v in venue_rows
              if v.get("reserve_usd") is not None and v.get("price_usd") is not None
              and float(v["reserve_usd"]) >= LIQ_MIN]
    if not usable:
        return []
    best = max(usable, key=lambda v: float(v["reserve_usd"]))
    out = []
    for size in sizes:
        reserve = float(best["reserve_usd"])
        out.append({
            "size_usd": size,
            "dex": best.get("dex"),
            "chain": best.get("chain"),
            "price_usd": best.get("price_usd"),
            "reserve_usd": reserve,
            "depth_warning": size > 0.05 * reserve,
        })
    return out
