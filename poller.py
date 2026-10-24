"""Radar Tokenized Stocks — poller Tahap 1 (desain §§2-3, 5, 7).

Rhythm (design §3.1):
- Baseline 5 min, 24/7 (cron triggers every 5 min; one cycle per invocation).
- Tight window: 1-min cycles for Tier 1 during +/-30 min around NYSE open
  (09:30 ET) and close (16:00 ET) on NYSE trading days. Tier 2 stays on the
  5-min rhythm inside the window (minute % 5 == 0). The poller loops
  internally during the window; cron is only the trigger. Overlap is
  prevented by a non-blocking flock (the flock is the real mutex).
- Redemption & PoR: hourly slot (design §3.1: every 60 min). No automated
  source is configured yet, so the slot records that fact in poller_health
  instead of fabricating rows (see HOURLY note below).
- Equity close: once per NYSE day after close. No licensed equity source
  is configured (median-only mode per parent decision), so the slot only
  records that fact; dev_vs_close_pct stays NULL.

Writes (design §2.1): snapshots per tracked pool, deviations per ticker
(depth-weighted price over pools with reserve_usd >= $100,000; median
cross-venue deviation NULL when < 2 qualifying pools; method
'v1-median-only'), heartbeat row per cycle in poller_health.
NO Telegram sends (bot is a later phase). NO paywall code. NO non-MVP
products. All DB times UTC. Raw responses archived one gzip per cycle
under raw/YYYY-MM-DD/HHMMSS.json.gz (90-day retention, design §2.3).

DexScreener batching (design §3.2, claim from independent
implementations, not official docs): /latest/dex/tokens/{up to 30
addresses} in ONE request. The poller verifies coverage every cycle:
pairs returned are matched to tracked pools; any tracked pool missing
from the batch response is fetched per-token as fallback, and the
fallback is recorded in the heartbeat gap_note.

Failure handling (design §3.2/§7.2): exponential backoff on 429/5xx
(5s, 10s, 20s); a failed cycle is a recorded gap in poller_health, never
a blind retry storm. Never logs the Turso token.
"""
import fcntl
import gzip
import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turso_client import pipeline, query  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE, "raw")
LOCK_PATH = os.path.join(BASE, "poller.lock")
STATE_PATH = os.path.join(BASE, "state.json")
DEX = "https://api.dexscreener.com/latest/dex/tokens/{}"
LIQ_MIN = 100000.0
ET = ZoneInfo("America/New_York")
UTC = timezone.utc

# NYSE holidays (full closes). 2026 list is the NYSE calendar; 2027 list
# follows the same pattern (observed dates). Review annually.
NYSE_HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def log(msg):
    print(f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}", flush=True)


def is_nyse_day(dt_et):
    return dt_et.weekday() < 5 and dt_et.strftime("%Y-%m-%d") not in NYSE_HOLIDAYS


def in_tight_window(now_utc):
    """True if now falls in +/-30 min around 09:30 or 16:00 ET on a trading day."""
    et = now_utc.astimezone(ET)
    if not is_nyse_day(et):
        return False
    day = et.date()
    for h, m in ((9, 30), (16, 0)):
        center = datetime(day.year, day.month, day.day, h, m, tzinfo=ET)
        if center - timedelta(minutes=30) <= et <= center + timedelta(minutes=30):
            return True
    return False


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


def dex_fetch(url):
    """GET with 429/5xx backoff. Returns (pairs_list, http_code, err)."""
    last_err = ""
    for attempt in range(3):
        r = subprocess.run(
            ["curl", "-s", "-w", "\nHTTP:%{http_code}", "--max-time", "30", url],
            capture_output=True, text=True,
        )
        out = r.stdout
        code = None
        if "\nHTTP:" in out:
            out, code = out.rsplit("\nHTTP:", 1)
            code = code.strip()
        if code == "200":
            try:
                data = json.loads(out)
                return data.get("pairs") or [], code, ""
            except Exception as e:
                return [], code, f"bad json: {e}"
        last_err = f"http {code}"
        if code in ("429", "500", "502", "503") or r.returncode != 0:
            time.sleep(5 * (2 ** attempt))
            continue
        return [], code, last_err
    return [], "429", f"backoff exhausted ({last_err})"


def run_cycle(cycle_dt):
    """One polling cycle. Returns True on success."""
    cycle_ts = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Idempotency: skip if this minute already has a successful heartbeat.
    done = query(
        "SELECT COUNT(*) AS n FROM poller_health "
        "WHERE cycle_ts = ? AND cycles_ok = 1",
        [cycle_ts],
    )
    if done and int(done[0]["n"]) > 0:
        log(f"CYCLE {cycle_ts} SKIP already-ok")
        return True

    tight = in_tight_window(cycle_dt)
    pools = query(
        "SELECT pool_id, ticker_id, chain, dex, pair_address, tier "
        "FROM pools JOIN universe USING (ticker_id) WHERE is_active = 1"
    )
    # Tier filter: in a tight window, Tier 2 only on 5-min marks.
    if tight and cycle_dt.minute % 5 != 0:
        pools = [p for p in pools if int(p["tier"]) == 1]
    tickers = sorted({p["ticker_id"] for p in pools})

    # Token addresses for the batch call.
    uni = query("SELECT ticker_id, token_addresses FROM universe")
    addr_by_ticker = {}
    for u in uni:
        try:
            addrs = json.loads(u["token_addresses"] or "{}")
        except Exception:
            addrs = {}
        if addrs:
            addr_by_ticker[u["ticker_id"]] = next(iter(addrs.values()))
    batch_addrs = [addr_by_ticker[t] for t in tickers if t in addr_by_ticker]

    pairs, code, err = dex_fetch(DEX.format(",".join(batch_addrs)))
    fallback_used = False
    if err:
        log(f"CYCLE {cycle_ts} FAIL dexscreener {err}")
        pipeline([(
            "INSERT INTO poller_health (cycle_ts, cycles_expected, cycles_ok,"
            " failed_sources, gap_note) VALUES (?,?,?,?,?)",
            [cycle_ts, 1, 0, "dexscreener",
             f"dexscreener fetch failed: {err}"],
        )])
        return False

    by_pair = {}
    for p in pairs:
        by_pair[p.get("pairAddress")] = p
    # Coverage check: batch claim verification + per-token fallback.
    missing = [pl for pl in pools if pl["pair_address"] not in by_pair]
    if missing:
        # Case-insensitive retry first (address casing), then per-token fetch.
        lower = {k.lower(): v for k, v in by_pair.items()}
        still = [pl for pl in missing if pl["pair_address"].lower() not in lower]
        for pl in missing:
            if pl["pair_address"].lower() in lower:
                by_pair[pl["pair_address"]] = lower[pl["pair_address"].lower()]
        if still:
            fallback_used = True
            for pl in still:
                addr = addr_by_ticker.get(pl["ticker_id"])
                if not addr:
                    continue
                tp, _c, _e = dex_fetch(DEX.format(addr))
                for p in tp:
                    if p.get("pairAddress") == pl["pair_address"]:
                        by_pair[pl["pair_address"]] = p
                        break

    # Archive raw response (batch response; fallback pairs noted in meta).
    os.makedirs(os.path.join(RAW_DIR, cycle_dt.strftime("%Y-%m-%d")), exist_ok=True)
    raw_ref = os.path.join(
        "raw", cycle_dt.strftime("%Y-%m-%d"),
        cycle_dt.strftime("%H%M%S") + ".json.gz",
    )
    with gzip.open(os.path.join(BASE, raw_ref), "wt", encoding="utf-8") as f:
        json.dump({
            "cycle_ts": cycle_ts, "tight_window": tight,
            "batch_addresses": len(batch_addrs),
            "pairs_returned": len(pairs), "fallback_used": fallback_used,
            "pairs": pairs,
        }, f)

    stmts = []
    per_ticker = {}
    n_snap = 0
    missing_now = []
    for pl in pools:
        p = by_pair.get(pl["pair_address"])
        if not p:
            missing_now.append(pl["pool_id"])
            continue
        liq = p.get("liquidity") or {}
        vol = p.get("volume") or {}
        try:
            price = float(p["priceUsd"]) if p.get("priceUsd") else None
        except (TypeError, ValueError):
            price = None
        reserve = liq.get("usd")
        stmts.append((
            "INSERT INTO snapshots (pool_id, ts, price_usd, reserve_usd,"
            " reserve_token, reserve_quote, volume_24h_usd, source, raw_ref)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [pl["pool_id"], cycle_ts, price, reserve, liq.get("base"),
             liq.get("quote"), vol.get("h24"), "dexscreener", raw_ref],
        ))
        n_snap += 1
        if price is not None and reserve is not None and reserve >= LIQ_MIN:
            per_ticker.setdefault(pl["ticker_id"], []).append((price, reserve))

    guard_notes = []
    for ticker, lst in per_ticker.items():
        # Price-sanity guard (2026-10-24: SPYx showed -25.9% from ONE bad
        # upstream quote, $0.10 vs ~$762 on 4 sibling pools, reserve intact).
        # With >=3 qualifying pools, drop prices deviating >25% from the
        # cross-pool median; excluded pools contribute neither price nor
        # depth. With <3 pools no consensus exists, so the guard is skipped
        # (documented limitation). Fallback to lst if exclusion empties kept.
        kept, n_excluded = lst, 0
        if len(lst) >= 3:
            med_all = statistics.median([pr for pr, _ in lst])
            if med_all:
                kept = [(pr, r) for pr, r in lst
                        if abs(pr - med_all) / med_all <= 0.25]
                n_excluded = len(lst) - len(kept)
                if not kept:
                    kept, n_excluded = lst, 0
        if n_excluded:
            guard_notes.append(f"{ticker}:{n_excluded}")
        depth = sum(r for _, r in kept)
        dw = sum(pr * r for pr, r in kept) / depth if depth else None
        prices = [pr for pr, _ in kept]
        median = statistics.median(prices) if len(prices) >= 2 else None
        dev_med = ((dw - median) / median * 100.0) if (median and dw) else None
        stmts.append((
            "INSERT INTO deviations (ticker_id, ts, depth_weighted_price,"
            " dev_vs_close_pct, dev_vs_median_pct, qualifying_depth_usd,"
            " pools_used, pools_excluded, redemption_status, por_age_hours,"
            " weekend_risk_score, method_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [ticker, cycle_ts, dw, None, dev_med, depth, len(kept),
             n_excluded, None, None, None, "v1-median-only"],
        ))

    # Hourly slot: redemption & PoR (no automated source configured yet).
    state = load_state()
    gap_bits = []
    if guard_notes:
        gap_bits.append(f"price-guard excluded pool(s): {', '.join(guard_notes)}")
    if fallback_used:
        gap_bits.append("dexscreener batch incomplete; per-token fallback used")
    if missing_now:
        gap_bits.append(f"{len(missing_now)} tracked pools missing from response")
    now_iso = cycle_dt.isoformat()
    last_hourly = state.get("last_hourly_check")
    if (not last_hourly
            or (cycle_dt - datetime.fromisoformat(last_hourly)).total_seconds() >= 55 * 60):
        gap_bits.append(
            "hourly: redemption/por automated source not configured "
            "(documented baseline only; no rows fabricated)")
        state["last_hourly_check"] = now_iso
    # Equity-close slot: once per NYSE day after 16:30 ET (median-only mode).
    et = cycle_dt.astimezone(ET)
    if is_nyse_day(et) and (et.hour, et.minute) >= (16, 30):
        if state.get("last_equity_note_date") != et.strftime("%Y-%m-%d"):
            gap_bits.append(
                "equity-close: no licensed equity source configured "
                "(median-only mode; dev_vs_close_pct NULL)")
            state["last_equity_note_date"] = et.strftime("%Y-%m-%d")
    save_state(state)

    stmts.append((
        "INSERT INTO poller_health (cycle_ts, cycles_expected, cycles_ok,"
        " failed_sources, gap_note) VALUES (?,?,?,?,?)",
        [cycle_ts, 1, 1, None, "; ".join(gap_bits) if gap_bits else None],
    ))
    pipeline(stmts)
    log(f"CYCLE {cycle_ts} OK tight={tight} snapshots={n_snap} "
        f"deviations={len(per_ticker)} missing={len(missing_now)} "
        f"fallback={fallback_used} "
        f"guard={';'.join(guard_notes) if guard_notes else '-'}")
    return True


def main():
    if "--test-windows" in sys.argv:
        cases = [
            # (UTC iso, expected tight?) — Oct 24 2026 is Saturday.
            ("2026-10-24T11:00:00+00:00", False),  # Sat
            ("2026-10-26T13:00:00+00:00", True),   # Mon 09:00 ET (open-30)
            ("2026-10-26T13:29:00+00:00", True),   # Mon 09:29 ET
            ("2026-10-26T14:00:00+00:00", True),   # Mon 10:00 ET (open+30)
            ("2026-10-26T14:01:00+00:00", False),  # Mon 10:01 ET
            ("2026-10-26T19:30:00+00:00", True),   # Mon 15:30 ET (close-30)
            ("2026-10-26T20:30:00+00:00", True),   # Mon 16:30 ET (close+30)
            ("2026-10-26T20:31:00+00:00", False),  # Mon 16:31 ET
            ("2026-10-26T12:59:00+00:00", False),  # Mon 08:59 ET
            ("2026-12-25T14:00:00+00:00", False),  # Christmas (NYSE holiday)
            ("2026-11-01T14:00:00+00:00", False),  # Sunday
        ]
        ok = True
        for iso, exp in cases:
            dt = datetime.fromisoformat(iso)
            got = in_tight_window(dt)
            mark = "OK " if got == exp else "FAIL"
            if got != exp:
                ok = False
            print(f"{mark} {iso} ET={dt.astimezone(ET).strftime('%a %H:%M')} "
                  f"tight={got} expected={exp}")
        print("WINDOWS TEST:", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    lock_f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("LOCKED another poller instance is running; exit")
        return 0
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    if in_tight_window(now):
        # Loop every minute until the window ends (max 75 min safety).
        deadline = now + timedelta(minutes=75)
        while datetime.now(UTC) < deadline:
            cur = datetime.now(UTC).replace(second=0, microsecond=0)
            if not in_tight_window(cur):
                break
            run_cycle(cur)
            nxt = (datetime.now(UTC).replace(second=0, microsecond=0)
                   + timedelta(minutes=1))
            time.sleep(max(0, (nxt - datetime.now(UTC)).total_seconds()) + 1)
        log("TIGHT LOOP done")
    else:
        run_cycle(now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
