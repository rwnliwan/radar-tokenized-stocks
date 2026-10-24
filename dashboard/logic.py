"""Pure dashboard logic (no Streamlit, no I/O) — unit-testable.

Freshness (design §6.3): stale when the last successful poller cycle
is older than 15 minutes OR the last 2 cycles both failed.
WITA = UTC + 8 (Asia/Makassar has no DST).
Best exit venue (design §6.1.8): deepest qualifying pool per size,
flagged when the size exceeds 5% of that pool's reserve. This is an
estimate from depth, never an execution promise.
"""
from datetime import datetime, timedelta, timezone

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
    """'24 Oct 2026 19:11 WITA' (en) / '24 Okt 2026 19:11 WITA' (id)."""
    dt = parse_ts(iso)
    if dt is None:
        return "—"
    w = dt.astimezone(WITA)
    months = MONTHS_ID if lang == "id" else MONTHS_EN
    return f"{w.day} {months[w.month - 1]} {w.year} {w.hour:02d}:{w.minute:02d} WITA"


def freshness_status(health_rows, now_utc):
    """health_rows: newest-first list of {cycle_ts, cycles_ok}.

    Returns {last_ts, age_min, failed_streak, stale}.
    Empty input -> stale (no heartbeat at all).
    """
    if not health_rows:
        return {"last_ts": None, "age_min": None, "failed_streak": 0, "stale": True}
    last_ts = parse_ts(health_rows[0].get("cycle_ts"))
    if last_ts is None:
        return {"last_ts": None, "age_min": None, "failed_streak": 0, "stale": True}
    age_min = (now_utc - last_ts).total_seconds() / 60.0
    streak = 0
    for row in health_rows:
        try:
            ok = int(row.get("cycles_ok") or 0)
        except (TypeError, ValueError):
            ok = 0
        if ok == 1:
            break
        streak += 1
    stale = age_min > 15.0 or streak >= 2
    return {"last_ts": health_rows[0].get("cycle_ts"), "age_min": age_min,
            "failed_streak": streak, "stale": stale}


def best_exit_venues(venue_rows, sizes=(1000, 5000, 10000)):
    """venue_rows: latest snapshot per pool with reserve_usd + dex + price.

    Returns one row per size: deepest pool, flagged when size > 5% of
    its reserve. Empty input -> [] (caller shows 'no data').
    """
    usable = [v for v in venue_rows
              if v.get("reserve_usd") is not None and v.get("price_usd") is not None]
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
