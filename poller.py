"""Radar Tokenized Stocks — poller Tahap 1 (desain §§2-3, 5, 7).

Rhythm (design §3.1):
- Baseline 5 min, 24/7 (cron triggers every 5 min; one cycle per invocation).
- Tight window: 1-min cycles for Tier 1 during +/-30 min around NYSE open
  (09:30 ET) and close (16:00 ET) on NYSE trading days. Tier 2 stays on the
  5-min rhythm inside the window (minute % 5 == 0). The poller loops
  internally during the window; cron is only the trigger. Overlap is
  prevented by a non-blocking flock (the flock is the real mutex).
- Redemption & PoR: hourly slot (design §3.1: every 60 min). Redemption
  is observed since Wave 3 (A+B, ACC'd): schedule-derived status from
  the official xStocks 24/5 rule + NYSE calendar, with an hourly
  on-chain pause/supply check over the 13 mints via PUBLIC Solana RPC
  (no keys). PoR is observed since v1 (ACC'd): hourly freshness from
  the public xStocks PoR API (no keys), one issuer-level row, age set
  by the stalest token.
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


# --- Redemption window A+B (Wave 3, ACC'd) ---
# A: schedule-derived status from the official xStocks 24/5 rule +
# NYSE calendar (CONSERVATIVE: open = NYSE business day, all day;
# closed = weekend / NYSE holiday). This is a schedule computation,
# NEVER presented as live issuer confirmation (the dashboard carries
# the honest label; see redemption_window_note in i18n.py).
# B: hourly on-chain exception monitor over the 13 xStocks mints via
# PUBLIC Solana RPC only (no keys, no signup): pausableConfig pause
# flag (verified present on all 13 mints 2026-10-25, all unpaused)
# + supply. If NO mint had Pausable, the pause detector would be
# dropped entirely — it is kept only because step-0 verified it.
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
XSTOCKS_MINTS = {
    "TSLAx": "XsDoVfqeBukxuZHWhdvWHBhgEHjGNst4MLodqsJHzoB",
    "NVDAx": "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh",
    "METAx": "Xsa62P5mvPszXL1krVUnU5ar38bBSVcWAB6fmPCo5Zu",
    "GOOGLx": "XsCPL9dNWBMvFtTmwcCA5v3xWPSMEBCszbQdiLLq6aN",
    "MSTRx": "XsP7xzNPvEHS1m6qfanPUGjNmdnmsLKEoNAnHjdxxyZ",
    "SPYx": "XsoCS1TfEyfFhfvj8EtZ528L3CaKBDBRqRapnBbDF2W",
    "QQQx": "Xs8S1uUs1zvS2p7iwtsG3b6fkhpvmwz4GYU3gWAmWHZ",
    "CRCLx": "XsueG8BtpquVJX9LVLLEGuViXUungE6WmK5YZ3p3bd1",
    "HOODx": "XsvNBAYkrDRNhA7wPHQfX3ZUXZyZLdnCQDfHZ56bzpg",
    "COINx": "Xs7ZdzSHLU9ftNJsii5fCeJhoRWSC32SQGzGQtePxNu",
    "GLDx": "Xsv9hRk1z5ystj9MhnA7Lq4vjSsLwzL2nxrwmwtD3re",
    "AAPLx": "XsbEhLAtcf6HdfpFZ5xEMdqW8nfAvcsP5bdudRLJzJp",
    "MSFTx": "XspzcW1PRtgf6Wj92HCiZdjzKCyFekVD8P5Ueh3dRMX",
}


def redemption_schedule_status(now_utc):
    """'open' on NYSE business days, 'closed' otherwise (24/5 rule)."""
    return "open" if is_nyse_day(now_utc.astimezone(ET)) else "closed"


def next_nyse_open_utc(now_utc):
    """00:00 ET of the next NYSE business day, as a UTC 'Z' string.

    Only meaningful when the schedule status is closed; callers pass
    None (not this value) for open/paused."""
    d = now_utc.astimezone(ET).date() + timedelta(days=1)
    while not is_nyse_day(datetime(d.year, d.month, d.day, tzinfo=ET)):
        d += timedelta(days=1)
    nxt_et = datetime(d.year, d.month, d.day, 0, 0, tzinfo=ET)
    return nxt_et.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def solana_mint_info(mint):
    """(paused_or_None, supply_or_None, err_or_None) via public RPC.

    paused is True/False only when a pausableConfig extension is
    actually present on-chain; None means unknown (no extension, or
    the read failed). Never raises, never fabricates."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                       "params": [mint, {"encoding": "jsonParsed"}]})
    err = ""
    for _attempt in range(2):
        r = subprocess.run(
            ["curl", "-s", "--max-time", "10", "-X", "POST",
             "-H", "Content-Type: application/json", "-d", body, SOLANA_RPC],
            capture_output=True, text=True)
        try:
            val = (json.loads(r.stdout).get("result") or {}).get("value") or {}
            info = (val.get("data") or {}).get("parsed", {}).get("info", {})
            paused = None
            for e in info.get("extensions") or []:
                if e.get("extension") == "pausableConfig":
                    paused = bool((e.get("state") or {}).get("paused"))
            return paused, info.get("supply"), ""
        except Exception as e:
            err = f"rpc error: {e}"
            time.sleep(3)
    return None, None, err


def run_hourly_redemption(cycle_dt, state, dry_run=False):
    """One hourly redemption observation (Wave 3 A+B).

    Writes ONE row to redemption_windows (existing table — no schema
    migration) in its own pipeline call, so a failure here never breaks
    the deviation cycle. Supply baselines live in state.json (no new
    table). Returns a gap_note fragment ('' when unremarkable).
    With dry_run=True nothing is written and the row is printed."""
    sched = redemption_schedule_status(cycle_dt)
    paused_list, supply_now, rpc_errors = [], {}, 0
    for tick, mint in XSTOCKS_MINTS.items():
        paused, supply, err = solana_mint_info(mint)
        if err:
            rpc_errors += 1
            if rpc_errors >= 3 and not supply_now and not paused_list:
                break  # RPC looks down; stop hammering, schedule-only row.
            continue
        supply_now[tick] = supply
        if paused:
            paused_list.append(tick)
        time.sleep(0.2)
    onchain_ok = bool(supply_now)
    status = "paused" if paused_list else sched
    prev = state.get("last_mint_supply") or {}
    changed = sorted(t for t, s in supply_now.items()
                     if t in prev and prev[t] != s)
    new_baseline = sorted(t for t in supply_now if t not in prev)
    if not dry_run:
        state["last_mint_supply"] = supply_now
    nxt = next_nyse_open_utc(cycle_dt) if status == "closed" else None
    if status == "paused":
        note_en = (f"Schedule-derived: {sched}; ON-CHAIN PAUSE on "
                   f"{', '.join(paused_list)} overrides to paused.")
        note_id = (f"Dari jadwal: {sched}; JEDA ON-CHAIN pada "
                   f"{', '.join(paused_list)} mengesampingkan menjadi dijeda.")
    elif sched == "open":
        note_en = "Schedule-derived: NYSE business day → open."
        note_id = "Dari jadwal: hari kerja NYSE → buka."
    else:
        note_en = "Schedule-derived: weekend/NYSE holiday → closed."
        note_id = "Dari jadwal: akhir pekan/hari libur NYSE → tutup."
    if onchain_ok:
        note_en += (f" On-chain: {len(paused_list)}/13 mints paused; "
                    f"supply changes: {', '.join(changed) if changed else 'none'}.")
        note_id += (f" On-chain: {len(paused_list)}/13 mint dijeda; "
                    f"perubahan supply: {', '.join(changed) if changed else 'tidak ada'}.")
    else:
        note_en += (" On-chain check unavailable this hour (RPC error); "
                    "pause status unknown.")
        note_id += (" Pemeriksaan on-chain tidak tersedia jam ini (galat RPC); "
                    "status jeda tidak diketahui.")
    cycle_ts = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    row = ["xStocks", "ALL", status, note_id, note_en, cycle_ts,
           "xStocks 24/5 schedule + Solana RPC (public)", nxt]
    if dry_run:
        print(f"DRY-RUN status={status} sched={sched} "
              f"paused={paused_list or '-'} rpc_errors={rpc_errors}")
        print(f"DRY-RUN row={row}")
        print(f"DRY-RUN supply_changed={changed or '-'} "
              f"baseline_new={new_baseline or '-'}")
        return ""
    try:
        pipeline([(
            "INSERT INTO redemption_windows (issuer, asset, status, window_note,"
            " window_note_en, observed_at, source, next_open_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            row,
        )])
    except Exception as e:
        log(f"HOURLY redemption write FAILED: {e}")
        return f"hourly redemption write failed: {e}"
    log(f"HOURLY redemption status={status} sched={sched} "
        f"paused={paused_list or '-'} rpc_errors={rpc_errors} "
        f"supply_changed={changed or '-'} baseline_new={new_baseline or '-'}")
    if paused_list:
        return f"redemption PAUSED on-chain: {', '.join(paused_list)}"
    if rpc_errors:
        return (f"hourly redemption on-chain check partial failure "
                f"({rpc_errors} mint reads failed)")
    return ""


POR_API_BASE = "https://api.xstocks.fi/api/v2/public/proof-of-reserves"


def por_symbol_info(symbol):
    """(record_or_None, err_or_None) via the public xStocks PoR API.
    No auth, no key. Never raises, never fabricates."""
    url = f"{POR_API_BASE}/{symbol}"
    err = ""
    for _attempt in range(2):
        r = subprocess.run(
            ["curl", "-s", "--max-time", "15", url],
            capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if d.get("symbol") == symbol and d.get("timestamp"):
                return d, ""
            err = f"unexpected payload for {symbol}"
        except Exception as e:
            err = f"PoR API error: {e}"
        time.sleep(3)
    return None, err


def parse_por_ts(ts):
    """ISO 8601 with millis + Z -> aware UTC datetime (None on failure)."""
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except Exception:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None


def run_hourly_por(cycle_dt, state, dry_run=False):
    """One hourly PoR observation (v1, ACC'd): freshness only.

    Fetches the public xStocks PoR API per symbol (13 requests, no auth)
    — the list endpoint paginates and page 1 holds none of our 13
    tickers, so per-symbol calls are the reliable shape. Writes ONE
    issuer-level row to por_feeds (existing table — no schema
    migration) in its own pipeline call, so a failure here never breaks
    the deviation cycle. Age is set by the STALEST token, not the
    average, so one stale token alone trips the 72h bot trigger.
    With dry_run=True nothing is written and the row is printed.
    Returns a gap_note fragment ('' when unremarkable)."""
    now_utc = datetime.now(UTC)
    recs, missing = {}, []
    for tick in XSTOCKS_MINTS:
        rec, _err = por_symbol_info(tick)
        if rec:
            recs[tick] = rec
        else:
            missing.append(tick)
        time.sleep(0.2)
    stamps = []
    for tick, rec in recs.items():
        dt = parse_por_ts(rec["timestamp"])
        if dt:
            stamps.append((dt, rec["timestamp"]))
    if not stamps:
        return "hourly PoR fetch failed: no usable token timestamps"
    oldest_dt, oldest_ts = min(stamps)
    age = max(0.0, round((now_utc - oldest_dt).total_seconds() / 3600, 1))
    cycle_ts = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    row = ["xStocks", POR_API_BASE, oldest_ts, age, None, cycle_ts]
    # v2: per-token rows from the SAME responses (no extra API calls).
    # Numbers stored as TEXT exactly as published (no float rounding).
    tok_rows = [
        [tick, rec["timestamp"], rec.get("sharesHeld"),
         rec.get("circulatingSupply"),
         json.dumps(rec.get("holdings")) if rec.get("holdings") is not None else None,
         cycle_ts]
        for tick, rec in recs.items()
    ]
    if dry_run:
        print(f"DRY-RUN por tokens={len(recs)}/13 missing={missing or '-'} "
              f"oldest={oldest_ts} age_h={age}")
        print(f"DRY-RUN row={row}")
        print(f"DRY-RUN token rows={len(tok_rows)}")
        return ""
    stmts = [(
        "INSERT INTO por_feeds (issuer, feed_address, last_update_ts,"
        " age_hours, reserves_vs_supply_note, checked_at)"
        " VALUES (?,?,?,?,?,?)",
        row,
    )]
    stmts += [(
        "INSERT INTO por_token_snapshots (ticker_id, ts, shares_held,"
        " circulating_supply, holdings_json, checked_at)"
        " VALUES (?,?,?,?,?,?)",
        trow,
    ) for trow in tok_rows]
    try:
        pipeline(stmts)
    except Exception as e:
        log(f"HOURLY PoR write FAILED: {e}")
        return f"hourly PoR write failed: {e}"
    log(f"HOURLY PoR tokens={len(recs)}/13 missing={missing or '-'} "
        f"oldest={oldest_ts} age_h={age} token_rows={len(tok_rows)}")
    if missing:
        return f"hourly PoR missing tokens: {', '.join(missing)}"
    return ""


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

    # Hourly slot: redemption & PoR (both automated since Wave 3 / PoR v1).
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
        # Wave 3: real hourly redemption observation (schedule + on-chain).
        # A failure here must never break the deviation cycle, so the
        # hourly write lives in its own pipeline call inside
        # run_hourly_redemption; only its gap fragment lands here.
        try:
            _frag = run_hourly_redemption(cycle_dt, state)
            if _frag:
                gap_bits.append(_frag)
        except Exception as _e:
            gap_bits.append(f"hourly redemption failed: {_e}")
        # PoR v1 (ACC'd): same isolation pattern as redemption.
        try:
            _frag = run_hourly_por(cycle_dt, state)
            if _frag:
                gap_bits.append(_frag)
        except Exception as _e:
            gap_bits.append(f"hourly PoR failed: {_e}")
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
    if "--dry-run-hourly" in sys.argv:
        # Wave 3 verification: compute one hourly redemption observation
        # (live public-RPC reads) and print it WITHOUT writing anything.
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        run_hourly_redemption(now, {}, dry_run=True)
        run_hourly_por(now, {}, dry_run=True)
        return 0
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
