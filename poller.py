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

Penambahan 2026-11-12 (DESAIN_PENAMBAHAN_2026-11-12.md §§2-4; thresholds
PRE-REGISTERED, unchanged):
- F1 Perp 3-leg: run_cycle_perp() every 5 min, ONE Hyperliquid info call
  (allMids dex xyz) + metaAndAssetCtxs dex xyz for funding/OI/mark/oracle;
  writes perp_snapshots (10 tickers; SPY/QQQ/GLD have no xyz perp — no
  rows, never fabricated). A Hyperliquid failure is recorded in the same
  cycle's poller_health gap_note (never a separate cycles_ok=0 row: the
  freshness contract in bot.py/api/worker.js counts consecutive failed
  rows, so a perp row would mark Radar stale) and never breaks the
  DexScreener cycle.
- F3 Exit Score (exit_score_v1): computed per ticker in run_cycle() and
  stored as deviations.exit_score + exit_score_version (+0 writes).
  Partial normalization follows dashboard/risk.py: a component without
  data is NOT counted and NOT zeroed.
- F4 Liquidation Guard: run_hourly_liquidation() on the hourly slot;
  liq_px_estimate is ALWAYS NULL (no verified public liquidation-level
  source) and oracle lag is unmeasurable from the public info endpoints
  (no oracle timestamp published), so status is driven by mark-vs-oracle
  divergence (+ distance when available).
- F2 Monday Gap: run_weekly_monday_gap() predicts Sunday >=22:00 UTC
  (one row per ticker per week) and fills outcomes Monday from indexed
  deviations reads. Outcomes are never guessed; a row stays 'pending'
  until both prices exist.
- F5 (bukti nilai): no outcome is written by this poller to alert_log.
  The alert_log outcome columns already exist in schema.sql and can be
  filled by a closer that computes from indexed deviations/snapshots —
  that closer lives in bot.py, not here.
Deploy order: apply migrations/2026-11-12-penambahan.sql to live Turso
BEFORE deploying this poller — the deviations INSERT now references
exit_score, and every cycle would fail on a DB without the column.

Multichain 2026-11-12 (SEED_MULTICHAIN_2026-11-12.md; thresholds
PRE-REGISTERED, unchanged — LIQ_MIN $100k, depth gate $250k, alert 1.0%):
- run_cycle() fetches DexScreener in ONE batch per chain (Solana +
  Base + BSC + Robinhood), each chunked at 30 addresses, instead of one
  mixed batch: 13 Solana + 30 multichain addresses would overflow the
  /tokens 30-address cap AND the ~30-pair response cap. A failed Solana
  batch still fails the cycle (old behavior); a failed non-Solana chain
  only leaves its pools missing + a gap_note (isolation, like perp).
- The seed set (30 tickers, 115 pools, verify 2026-11-12T12:50:30Z) is
  embedded as MULTICHAIN_SEED for --dry-run-multichain ONLY, because
  seed --live has NOT run yet — the live DB has 0 multichain rows, so a
  DB-driven dry run would measure nothing. Live cycles read pools from
  Turso (seeded rows), never from MULTICHAIN_SEED.
- Robinhood ticker suffix 'r' (TSLAr, NVDAr, ...) is PROVISIONAL —
  SEED_MULTICHAIN §6: confirm with Chief before the first live seed.
  It is used here only so the dry-run ticker_ids match the seed file.
- --dry-run-multichain: live DexScreener reads per new chain + the same
  LIQ_MIN / price-guard / depth-gate math as run_cycle, 0 Turso writes.
- --dry-run: one DB-driven cycle (run_cycle dry_run=True) with 0 Turso
  writes; multichain tickers appear in it only after seed --live.
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
# 2028 list is the official NYSE Group calendar (announced 2025-12-23):
# 9 closures — New Year's Day 2028 falls on a Saturday and is NOT
# observed, so there is no January 2028 closure. The calendar must
# cover through the end of NEXT year (qa/test_r8_fix.py S11 trips when
# it does not); the same set is duplicated in bot.py, dashboard/logic.py
# and web/src/lib/format.ts, and the guard asserts all four identical.
NYSE_HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    # 2028 (NYSE Group calendar: MLK Jan 17, Presidents Feb 21,
    # Good Friday Apr 14, Memorial May 29, Juneteenth Jun 19,
    # Independence Day Jul 4, Labor Day Sep 4, Thanksgiving Nov 23,
    # Christmas Dec 25)
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
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


def next_schedule_close_utc(now_utc):
    """00:00 ET at the end of the current open run, as a UTC 'Z' string.

    The schedule model is "open all day on NYSE business days"
    (redemption_schedule_status), so the window closes at midnight ET
    ending the last NYSE business day before a weekend / NYSE holiday:
    Friday -> Saturday 00:00 ET; the day before a holiday -> 00:00 ET
    of the holiday itself. Only meaningful when the schedule status is
    open; callers pass None (not this value) for closed/paused. This
    is SCHEDULE-DERIVED, not a published issuer close-time — the same
    honesty level as the status itself. Pure: no I/O. (Gap R7, built
    2026-11-09: the advance "closing within 24h" alert's close-time
    comes from this helper, not from any new external source.)"""
    d = now_utc.astimezone(ET).date()
    while is_nyse_day(datetime(d.year, d.month, d.day, tzinfo=ET)):
        d += timedelta(days=1)
    close_et = datetime(d.year, d.month, d.day, 0, 0, tzinfo=ET)
    return close_et.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            # GG-13 (fix ronde 8, M2): a parsed response with no usable
            # account data is an ERROR, not a successful "unchecked"
            # read. The old code returned (None, None, "") here, so the
            # caller counted the mint as checked-and-unpaused.
            if not val.get("data"):
                err = "empty account data"
                time.sleep(3)
                continue
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
    paused_list, supply_now, checked, rpc_errors = [], {}, set(), 0
    total_mints = len(XSTOCKS_MINTS)
    for tick, mint in XSTOCKS_MINTS.items():
        paused, supply, err = solana_mint_info(mint)
        if err:
            rpc_errors += 1
            if rpc_errors >= 3 and not checked and not paused_list:
                break  # RPC looks down; stop hammering, schedule-only row.
            continue
        # GG-13 (fix ronde 8, M2): a mint counts as CHECKED only when
        # the read returned usable data (a pause verdict or a supply).
        # A (None, None, "") read — parsed but empty — is unchecked,
        # never "checked-and-unpaused". A None supply is not stored,
        # so it can never count as a spurious supply change.
        if paused is not None or supply is not None:
            checked.add(tick)
        if supply is not None:
            supply_now[tick] = supply
        if paused:
            paused_list.append(tick)
        time.sleep(0.2)
    onchain_ok = bool(checked)
    status = "paused" if paused_list else sched
    prev = state.get("last_mint_supply") or {}
    changed = sorted(t for t, s in supply_now.items()
                     if t in prev and s is not None and prev[t] != s)
    new_baseline = sorted(t for t in supply_now if t not in prev)
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
        unchecked = total_mints - len(checked)
        note_en += (f" On-chain: {len(paused_list)} paused of "
                    f"{len(checked)}/{total_mints} mints checked "
                    f"({unchecked} unchecked); "
                    f"supply changes: {', '.join(changed) if changed else 'none'}.")
        note_id += (f" On-chain: {len(paused_list)} dijeda dari "
                    f"{len(checked)}/{total_mints} mint diperiksa "
                    f"({unchecked} belum diperiksa); "
                    f"perubahan supply: {', '.join(changed) if changed else 'tidak ada'}.")
        if unchecked:
            # GG-13: partial coverage must SAY it is partial — the
            # unchecked mints' pause status is unknown, never "0 paused".
            note_en += (f" Pause status unknown for {unchecked} mint(s).")
            note_id += (f" Status jeda tidak diketahui untuk {unchecked} mint.")
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
    # S8 (fix ronde 8): the supply baseline mutates ONLY after the
    # write lands. The old code mutated it before the write, so a
    # failed write still consumed the new baseline and the next hour's
    # supply-change comparison silently lost one cycle.
    if not dry_run:
        state["last_mint_supply"] = supply_now
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
        # GG-13 / GG-15 (fix ronde 8, M3): a timestamp that is
        # unparseable OR in the future is NOT usable freshness evidence
        # — the token is missing from the age, not silently dropped.
        # The old code dropped such tokens without even listing them.
        if dt and dt <= now_utc:
            stamps.append((dt, rec["timestamp"]))
        else:
            missing.append(tick)
    if not stamps:
        return "hourly PoR fetch failed: no usable token timestamps"
    oldest_dt, oldest_ts = min(stamps)
    age = max(0.0, round((now_utc - oldest_dt).total_seconds() / 3600, 1))
    cycle_ts = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # GG-13: the issuer row carries its coverage, so the age is never
    # read as "all 13 tokens" when only some contributed. The note
    # surfaces on the ticker detail page (por_note) via the Worker.
    cov_note = None
    if missing:
        cov_note = (f"coverage {len(stamps)}/{len(XSTOCKS_MINTS)} tokens; "
                    f"missing from freshness age: {', '.join(sorted(missing))}")
    row = ["xStocks", POR_API_BASE, oldest_ts, age, cov_note, cycle_ts]
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


# ======================================================================
# Penambahan 2026-11-12 (DESAIN §§2-4) — F1 perp, F3 exit score,
# F4 liquidation guard, F2 monday gap. Thresholds PRE-REGISTERED.
# ======================================================================

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
EXIT_SCORE_VERSION = "exit_score_v1"
MONDAY_GAP_VERSION = "monday_gap_v1"

# Radar ticker_id -> Hyperliquid xyz market symbol. Verified live
# 2026-11-12: all 10 present in allMids/metaAndAssetCtxs dex xyz;
# SPY/QQQ/GLD are NOT listed there — they get no perp rows, never a
# fabricated price. (The xyz dex lists ~144 markets; only these 10
# map to Radar tickers.)
XYZ_PERP = {
    "TSLAx": "TSLA", "NVDAx": "NVDA", "AAPLx": "AAPL", "MSFTx": "MSFT",
    "METAx": "META", "GOOGLx": "GOOGL", "COINx": "COIN", "MSTRx": "MSTR",
    "HOODx": "HOOD", "CRCLx": "CRCL",
}
XYZ_PERP_SYMBOLS = set(XYZ_PERP.values())


def _fnum(v):
    """float(v) or None — Hyperliquid returns numbers as strings."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def hl_post(payload):
    """POST to the public Hyperliquid info API (read-only, no key).
    Same backoff shape as dex_fetch: 3 attempts, 5s/10s/20s on
    429/5xx/transport failure. Returns (data_or_None, err_str).
    Never raises, never logs credentials (there are none)."""
    body = json.dumps(payload)
    last_err, last_code = "", None
    for attempt in range(3):
        r = subprocess.run(
            ["curl", "-s", "-w", "\nHTTP:%{http_code}", "--max-time", "20",
             "-X", "POST", "-H", "Content-Type: application/json",
             "-d", body, HL_INFO_URL],
            capture_output=True, text=True)
        out = r.stdout
        code = None
        if "\nHTTP:" in out:
            out, code = out.rsplit("\nHTTP:", 1)
            code = code.strip()
        if code == "200":
            try:
                return json.loads(out), ""
            except Exception as e:
                return None, f"bad json: {e}"
        last_code = code
        last_err = f"http {code}"
        if code == "429" or (code and code.startswith("5")) or r.returncode != 0:
            time.sleep(5 * (2 ** attempt))
            continue
        return None, last_err
    return None, f"backoff exhausted ({last_err or last_code or 'timeout'})"


def fetch_xyz_ctxs():
    """({ticker: {mark_px, oracle_px, funding, oi_usd}}, err_str) from
    metaAndAssetCtxs dex xyz. funding is the rate exactly as published
    (decimal fraction per funding interval); oi is converted to USD
    (openInterest is published in base units: oi_usd = oi x markPx).
    No oracle timestamp is published, so oracle lag is unmeasurable
    from this endpoint — callers must not invent one."""
    data, err = hl_post({"type": "metaAndAssetCtxs", "dex": "xyz"})
    if err or not isinstance(data, list) or len(data) != 2:
        return {}, err or "unexpected metaAndAssetCtxs payload"
    meta, ctxs = data
    universe = (meta or {}).get("universe") or []
    out = {}
    for i, u in enumerate(universe):
        name = (u or {}).get("name") or ""
        sym = name[4:] if name.startswith("xyz:") else name
        if sym not in XYZ_PERP_SYMBOLS or i >= len(ctxs):
            continue
        ctx = ctxs[i] or {}
        mark = _fnum(ctx.get("markPx"))
        oracle = _fnum(ctx.get("oraclePx"))
        funding = _fnum(ctx.get("funding"))
        oi_base = _fnum(ctx.get("openInterest"))
        oi_usd = (oi_base * mark) if (oi_base is not None and mark) else None
        ticker = next(t for t, s in XYZ_PERP.items() if s == sym)
        out[ticker] = {"mark_px": mark, "oracle_px": oracle,
                       "funding": funding, "oi_usd": oi_usd}
    return out, ""


def fetch_xyz_mids():
    """({ticker: mid_px}, err_str) from allMids dex xyz."""
    data, err = hl_post({"type": "allMids", "dex": "xyz"})
    if err or not isinstance(data, dict):
        return {}, err or "unexpected allMids payload"
    out = {}
    for ticker, sym in XYZ_PERP.items():
        px = _fnum(data.get(f"xyz:{sym}"))
        if px is not None:
            out[ticker] = px
    return out, ""


def fetch_xyz_market_data():
    """({ticker: {perp_px, funding, oi_usd, mark_px, oracle_px}}, err).
    perp_px is the MARK price from assetCtxs when available, else the
    allMids mid (same market, same second) as fallback; funding/OI are
    NULL when metaAndAssetCtxs is unavailable — never fabricated.
    err is '' on full success, a 'partial: ...' note when degraded but
    usable, and set with empty data on total failure."""
    ctxs, ctx_err = fetch_xyz_ctxs()
    mids, mids_err = fetch_xyz_mids()
    if not ctxs and not mids:
        return {}, f"hyperliquid info failed (ctxs: {ctx_err or '?'}; mids: {mids_err or '?'})"
    out = {}
    for ticker in sorted(XYZ_PERP):
        c = ctxs.get(ticker) or {}
        perp = c.get("mark_px") if c.get("mark_px") is not None else mids.get(ticker)
        if perp is None:
            continue  # market absent from both responses: no row, never fabricated
        out[ticker] = {"perp_px": perp, "funding": c.get("funding"),
                       "oi_usd": c.get("oi_usd"), "mark_px": c.get("mark_px"),
                       "oracle_px": c.get("oracle_px")}
    err = ""
    if ctx_err:
        err = (f"partial: metaAndAssetCtxs unavailable ({ctx_err}); "
               f"perp_px from allMids, funding/OI NULL")
    elif mids_err:
        err = (f"partial: allMids unavailable ({mids_err}); "
               f"perp_px from markPx only")
    return out, err


# --- F3 Exit Score (pure, no I/O — mirrors dashboard/risk.py style) ---
def _exit_redemption_component(status, close_in_hours):
    """Redemption window component (max 20). 'closed' = redemption
    unavailable now -> 20. 'open' scores by time until the schedule-
    derived close (next_schedule_close_utc): <=24h -> 20, <=72h -> 10,
    else 0. 'paused'/'gated' -> 10. Unknown/None -> NOT counted."""
    if status is None:
        return None
    s = str(status).strip().lower()
    if s in ("paused", "gated"):
        return 10.0
    if s == "closed":
        return 20.0
    if s == "open":
        if close_in_hours is None:
            return None
        if close_in_hours <= 24.0:
            return 20.0
        if close_in_hours <= 72.0:
            return 10.0
        return 0.0
    return None


def exit_score_v1(dev_pct, depth_usd, median_depth_7d, redemption_status,
                  redemption_close_in_hours, funding, oi_change_24h_pct):
    """Exit Score v1 (DESAIN §2.3, total 100). Pure function.
    funding is the published decimal fraction (per funding interval);
    the design thresholds apply to |funding| x 100 as a percent —
    NOTE: Hyperliquid publishes the rate per funding interval (hourly),
    while the design labels the component 'funding 8 jam'; no silent
    x8 scaling is applied — that mapping is an open interpretation
    question for Chief, not something to resolve by arithmetic here.
    Components without data are NOT counted and NOT zeroed (same
    partial normalization as weekend_risk_score v3.2): score_100 =
    total / max_possible x 100 over available components only.
    Returns dict with components, total, max_possible, score_100
    (None when NO component is available), components_present and
    method_version."""
    comps = {}
    comps["deviation"] = (round(min(abs(dev_pct) * 10.0, 30.0), 1)
                          if dev_pct is not None else None)
    if depth_usd is None or median_depth_7d is None or not median_depth_7d:
        comps["depth"] = None
    else:
        r = depth_usd / median_depth_7d
        if r >= 1.0:
            comps["depth"] = 0.0
        elif r <= 0.5:
            comps["depth"] = 25.0
        else:
            comps["depth"] = round(25.0 * (1.0 - r) / 0.5, 1)
    comps["redemption"] = _exit_redemption_component(
        redemption_status, redemption_close_in_hours)
    if funding is None:
        comps["funding"] = None
    else:
        pct = abs(funding) * 100.0
        if pct <= 0.01:
            comps["funding"] = 0.0
        elif pct >= 0.10:
            comps["funding"] = 15.0
        else:
            comps["funding"] = round(15.0 * (pct - 0.01) / 0.09, 1)
    if oi_change_24h_pct is None:
        comps["oi"] = None
    else:
        if oi_change_24h_pct <= 0.0:
            comps["oi"] = 0.0
        elif oi_change_24h_pct >= 20.0:
            comps["oi"] = 10.0
        else:
            comps["oi"] = round(10.0 * oi_change_24h_pct / 20.0, 1)
    maxima = {"deviation": 30.0, "depth": 25.0, "redemption": 20.0,
              "funding": 15.0, "oi": 10.0}
    avail = {k: v for k, v in comps.items() if v is not None}
    total = round(sum(avail.values()), 1)
    max_possible = sum(maxima[k] for k in avail)
    score_100 = (round(total / max_possible * 100.0, 1)
                 if max_possible else None)
    return {"components": comps, "total": total, "max_possible": max_possible,
            "score_100": score_100, "components_present": len(avail),
            "components_total": 5, "partial": len(avail) < 5,
            "method_version": EXIT_SCORE_VERSION}


# --- F2 Monday Gap (pure, no I/O) ---
def monday_gap_predict(D, R, pools_used, depth_usd, spread_pct,
                       calibrated_weekends):
    """Monday Gap v1 (DESAIN §2.2). D = weekend deviation % (last Sunday),
    R = Friday-close -> Sunday-night drift %. Returns
    (gap_pred_pct, confidence, label). gap is clamped to +/-10%.
    Confidence (total 100): data quality 30 / direction 25 / spread 20 /
    calibration 25 (+5 per judged weekend, max 25). A missing spread
    scores 0 on that component (missing data lowers confidence — it is
    NOT renormalized away). Labels: <40 Rendah, 40-69 Sedang, >=70 Tinggi.
    The 'eksperimental' label itself is a display concern, not returned."""
    gap = round(max(-10.0, min(10.0, 0.6 * D + 0.4 * R)), 2)
    if (pools_used is not None and depth_usd is not None
            and pools_used >= 3 and depth_usd >= 1_000_000):
        quality = 30
    elif pools_used == 2 or (depth_usd is not None
                             and 250_000 <= depth_usd < 1_000_000):
        quality = 15
    else:
        quality = 0
    direction = 25 if ((D > 0 and R > 0) or (D < 0 and R < 0)) else 0
    if spread_pct is None:
        spread_pts = 0
    elif spread_pct <= 0.5:
        spread_pts = 20
    elif spread_pct <= 1.0:
        spread_pts = 10
    else:
        spread_pts = 0
    calib = 5 * max(0, min(int(calibrated_weekends or 0), 5))
    conf = float(quality + direction + spread_pts + calib)
    label = "Tinggi" if conf >= 70 else ("Sedang" if conf >= 40 else "Rendah")
    return gap, conf, label


# --- F4 Liquidation Guard status (pure, no I/O) ---
def liquidation_status(divergence_pct, distance_pct, oracle_lag_s=None):
    """ok / warning / critical per DESAIN §2.4. oracle_lag_s None =
    unmeasurable (no oracle timestamp is published) — it never triggers.
    distance_pct None (liq_px_estimate NULL) — it never triggers."""
    crit = ((oracle_lag_s is not None and oracle_lag_s > 600)
            or (divergence_pct is not None and divergence_pct >= 3.0)
            or (distance_pct is not None and distance_pct <= 5.0))
    if crit:
        return "critical"
    warn = ((oracle_lag_s is not None and oracle_lag_s > 120)
            or (divergence_pct is not None and divergence_pct >= 1.0)
            or (distance_pct is not None and distance_pct <= 10.0))
    return "warning" if warn else "ok"


# --- F3 cycle inputs (latest-only, bounded reads; never raise) ---
def _latest_redemption_status(cycle_dt):
    """(status_or_None, close_in_hours_or_None) from the latest
    redemption_windows row (1 row). close hours come from the pure
    schedule helper when status is 'open'."""
    try:
        rows = query("SELECT status FROM redemption_windows "
                     "ORDER BY observed_at DESC LIMIT 1")
    except Exception:
        return None, None
    if not rows:
        return None, None
    status = rows[0].get("status")
    close_h = None
    if isinstance(status, str) and status.strip().lower() == "open":
        try:
            close_dt = datetime.strptime(
                next_schedule_close_utc(cycle_dt), "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=UTC)
            close_h = (close_dt - cycle_dt).total_seconds() / 3600.0
        except Exception:
            close_h = None
    return status, close_h


def _latest_perp_by_ticker(cycle_dt):
    """{ticker: {funding, oi, ts}} from perp rows fresh within 15 min
    (the §2.1 freshness gate). Latest row per ticker wins. <=40 rows."""
    fresh_since = (cycle_dt - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = query("SELECT ticker_id, funding, oi, ts FROM perp_snapshots "
                     "WHERE ts >= ? ORDER BY ts DESC LIMIT 40", [fresh_since])
    except Exception:
        return {}
    out = {}
    for r in rows:
        t = r.get("ticker_id")
        if t and t not in out:
            out[t] = {"funding": r.get("funding"), "oi": r.get("oi"),
                      "ts": r.get("ts")}
    return out


def _oi_24h_ago(ticker, cycle_dt):
    """OI (USD) at/before 24h ago — latest row, 1 row — or None when no
    such row exists (component then not counted, not zeroed)."""
    cutoff = (cycle_dt - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = query("SELECT oi FROM perp_snapshots WHERE ticker_id = ? "
                     "AND ts <= ? ORDER BY ts DESC LIMIT 1", [ticker, cutoff])
    except Exception:
        return None
    if rows and rows[0].get("oi") is not None:
        return rows[0]["oi"]
    return None


def refresh_median_depth_7d(state, cycle_dt, tickers, dry_run=False):
    """Refresh state['median_depth_7d'] {ticker: median} once per day.
    Bounded: <=2016 latest rows per ticker (~7 days at the 5-min
    baseline cadence; tight-window bursts shorten the window a little).
    On failure the old cache is kept (or stays absent — the depth
    component is then not counted). Never raises; dry_run prints."""
    today = cycle_dt.strftime("%Y-%m-%d")
    if state.get("median_depth_7d_date") == today and state.get("median_depth_7d"):
        return state.get("median_depth_7d") or {}
    since = (cycle_dt - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    med = {}
    for t in tickers:
        try:
            rows = query("SELECT qualifying_depth_usd FROM deviations "
                         "WHERE ticker_id = ? AND ts >= ? "
                         "AND qualifying_depth_usd IS NOT NULL "
                         "ORDER BY ts DESC LIMIT 2016", [t, since])
        except Exception as e:
            log(f"MEDIAN-DEPTH refresh {t} unavailable: {e}")
            continue
        vals = [r["qualifying_depth_usd"] for r in rows
                if r.get("qualifying_depth_usd") is not None]
        if vals:
            med[t] = round(statistics.median(vals), 2)
    if dry_run:
        print(f"DRY-RUN median_depth_7d date={today} tickers={len(med)} {med}")
        return med
    if med:
        state["median_depth_7d"] = med
        state["median_depth_7d_date"] = today
        log(f"MEDIAN-DEPTH refreshed {len(med)} tickers for {today}")
    return med


def _perp_due(cycle_dt, state):
    """True when the 5-min perp slot should run: 5 min after the last
    SUCCESSFUL perp cycle; a failed attempt backs off 5 min (mirror of
    _hourly_due: future-dated stamps are due, never 'recent')."""
    last = state.get("last_perp_check")
    if last:
        try:
            age = (cycle_dt - datetime.fromisoformat(last)).total_seconds()
        except (TypeError, ValueError):
            age = None
        if age is not None and 0 <= age < 5 * 60:
            return False
    failed_at = state.get("last_perp_failed_at")
    if failed_at:
        try:
            age_f = (cycle_dt - datetime.fromisoformat(failed_at)).total_seconds()
        except (TypeError, ValueError):
            age_f = None
        if age_f is not None and 0 <= age_f < 5 * 60:
            return False
    return True


def run_cycle_perp(cycle_dt, state, dry_run=False):
    """One 5-min perp snapshot cycle (F1, perp_3leg_v1).

    ONE allMids call + ONE metaAndAssetCtxs call per cycle (both dex
    xyz, read-only). Writes one perp_snapshots row per ticker that has
    a price (10 max); a market absent from both responses gets NO row.
    funding/OI are NULL when metaAndAssetCtxs is unavailable.
    Returns a gap-note fragment ('' when quiet). Never raises.
    Failure accounting (deliberate): the fragment is recorded in the
    SAME cycle's poller_health gap_note by the caller (run_cycle via
    extra_gap_notes) — this function NEVER inserts its own
    poller_health row, because the freshness contract (bot.py
    load_health_age_minutes, api/worker.js healthSummary) counts
    consecutive cycles_ok=0 rows, and a perp row would mark Radar
    stale during a Hyperliquid outage even while DexScreener is fine.
    With dry_run=True nothing is written and rows are printed."""
    cycle_ts = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    data, err = fetch_xyz_market_data()
    if not data:
        frag = f"hyperliquid perp unavailable: {err}"
        if dry_run:
            print(f"DRY-RUN perp: {frag}")
            return frag
        state["last_perp_failed_at"] = cycle_dt.isoformat()
        log(f"PERP {cycle_ts} {frag}")
        return frag
    rows = [[t, cycle_ts, d["perp_px"], d.get("funding"), d.get("oi_usd"), "xyz"]
            for t, d in sorted(data.items())]
    if dry_run:
        print(f"DRY-RUN perp tickers={len(rows)}/10 err={err or '-'}")
        for r in rows:
            print(f"DRY-RUN perp row={r}")
        return ""
    try:
        pipeline([(
            "INSERT INTO perp_snapshots (ticker_id, ts, perp_px, funding,"
            " oi, dex) VALUES (?,?,?,?,?,?)",
            r,
        ) for r in rows])
    except Exception as e:
        frag = f"hyperliquid perp write unavailable: {e}"
        state["last_perp_failed_at"] = cycle_dt.isoformat()
        log(f"PERP {cycle_ts} {frag}")
        return frag
    state["last_perp_check"] = cycle_dt.isoformat()
    state.pop("last_perp_failed_at", None)
    missing = sorted(set(XYZ_PERP) - set(data))
    log(f"PERP {cycle_ts} OK tickers={len(rows)} "
        f"funding_null={sum(1 for d in data.values() if d.get('funding') is None)} "
        f"missing={missing or '-'}"
        + (f" note={err}" if err else ""))
    return ""


def run_hourly_liquidation(cycle_dt, state, dry_run=False):
    """One hourly liquidation-guard observation (F4, liq_guard_v1).

    Reads mark + oracle from metaAndAssetCtxs dex xyz. liq_px_estimate
    is ALWAYS NULL (no verified public source for liquidation levels,
    §2.4) and distance_pct NULL with it — never fabricated. Oracle lag
    is NOT measurable (no oracle timestamp published), so status is
    driven by mark-vs-oracle divergence only. Writes one row per ticker
    to liquidation_watch and refreshes state['liquidation_alert_tickers']
    ({ticker: warning|critical}) which drives the 5-min follow-up in
    run_cycle while a condition is active. Returns a gap fragment
    ('' when quiet) — the wording deliberately avoids 'failed' so a
    liquidation outage never holds back the shared hourly clock in
    run_cycle (redemption/PoR are the clock's owners). Never raises."""
    cycle_ts = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    ctxs, err = fetch_xyz_ctxs()
    if not ctxs:
        frag = f"hourly liquidation unavailable: hyperliquid ctxs error ({err or 'empty'})"
        if dry_run:
            print(f"DRY-RUN liquidation: {frag}")
            return frag
        log(f"HOURLY liquidation {frag}")
        return frag
    rows, alert_now = [], {}
    for ticker in sorted(XYZ_PERP):
        d = ctxs.get(ticker)
        if not d or d.get("mark_px") is None or d.get("oracle_px") is None:
            continue
        mark, oracle = d["mark_px"], d["oracle_px"]
        div = abs(mark - oracle) / oracle * 100.0 if oracle else None
        st = liquidation_status(div, None, None)
        if st in ("warning", "critical"):
            alert_now[ticker] = st
        rows.append([ticker, cycle_ts, oracle, mark, None, None,
                     "hyperliquid-info"])
    if dry_run:
        print(f"DRY-RUN liquidation tickers={len(rows)}/10 "
              f"alert={alert_now or '-'}")
        for r in rows:
            print(f"DRY-RUN liquidation row={r}")
        return ""
    if not rows:
        frag = "hourly liquidation unavailable: no xyz market had mark+oracle"
        log(f"HOURLY liquidation {frag}")
        return frag
    try:
        pipeline([(
            "INSERT INTO liquidation_watch (ticker_id, ts, oracle_px,"
            " mark_px, liq_px_estimate, distance_pct, source)"
            " VALUES (?,?,?,?,?,?,?)",
            r,
        ) for r in rows])
    except Exception as e:
        log(f"HOURLY liquidation write FAILED: {e}")
        return f"hourly liquidation write unavailable: {e}"
    state["liquidation_alert_tickers"] = alert_now
    log(f"HOURLY liquidation tickers={len(rows)} alert={alert_now or '-'}")
    return ""


# --- F2 Monday Gap helpers (latest-only, indexed reads; never raise) ---
def _latest_deviations_row(ticker, ts_from, ts_to=None):
    """Latest deviations row for ticker in [ts_from, ts_to), or None."""
    try:
        if ts_to:
            rows = query("SELECT ticker_id, ts, depth_weighted_price,"
                         " dev_vs_median_pct, qualifying_depth_usd,"
                         " pools_used FROM deviations WHERE ticker_id = ?"
                         " AND ts >= ? AND ts < ? ORDER BY ts DESC LIMIT 1",
                         [ticker, ts_from, ts_to])
        else:
            rows = query("SELECT ticker_id, ts, depth_weighted_price,"
                         " dev_vs_median_pct, qualifying_depth_usd,"
                         " pools_used FROM deviations WHERE ticker_id = ?"
                         " AND ts >= ? ORDER BY ts DESC LIMIT 1",
                         [ticker, ts_from])
    except Exception:
        return None
    return rows[0] if rows else None


def _sunday_spread_pct(ticker, sunday_ts):
    """Cross-venue spread (hi-lo)/dw % from snapshots at one cycle ts,
    or None when < 2 qualifying pools have rows there."""
    try:
        pools = query("SELECT pool_id FROM pools WHERE ticker_id = ? "
                      "AND is_active = 1", [ticker])
        if not pools:
            return None
        ids = [p["pool_id"] for p in pools]
        q = ("SELECT price_usd, reserve_usd FROM snapshots WHERE ts = ? "
             "AND pool_id IN (%s)" % ",".join("?" * len(ids)))
        rows = query(q, [sunday_ts] + ids)
    except Exception:
        return None
    kept = [(r["price_usd"], r["reserve_usd"]) for r in rows
            if r.get("price_usd") is not None
            and r.get("reserve_usd") is not None
            and r["reserve_usd"] >= LIQ_MIN]
    if len(kept) < 2:
        return None
    depth = sum(r for _, r in kept)
    dw = sum(p * r for p, r in kept) / depth if depth else None
    if not dw:
        return None
    return ((max(p for p, _ in kept) - min(p for p, _ in kept)) / dw * 100.0)


def _monday_gap_predict(cycle_dt, state, dry_run=False):
    """Sunday-night prediction branch. week_start = the Saturday that
    starts this weekend. Idempotent: a state guard plus an existing-row
    check mean a second run for the same week writes nothing."""
    sat = cycle_dt.date() - timedelta(days=1)
    week_start = sat.strftime("%Y-%m-%d")
    if not dry_run and state.get("last_monday_gap_week") == week_start:
        return ""
    sun_start = cycle_dt.date().strftime("%Y-%m-%dT00:00:00Z")
    mon_start = (cycle_dt.date() + timedelta(days=1)).strftime(
        "%Y-%m-%dT00:00:00Z")
    fri_start = (sat - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    fri_end = sat.strftime("%Y-%m-%dT00:00:00Z")
    try:
        _c = query("SELECT COUNT(*) AS n FROM monday_gap "
                   "WHERE outcome IN ('accurate','inaccurate')")
        calibrated = int(_c[0]["n"]) if _c else 0
    except Exception as e:
        return f"monday gap unavailable: calibration count error ({e})"
    rows, skipped = [], []
    for ticker in sorted(XSTOCKS_MINTS):
        # Sunday row is bounded to Sunday itself ([Sun 00:00, Mon 00:00)):
        # an unbounded "latest since Sunday" would pick up a Monday row
        # on any replayed/late run and silently predict from Monday data.
        sun = _latest_deviations_row(ticker, sun_start, mon_start)
        fri = _latest_deviations_row(ticker, fri_start, fri_end)
        if (not sun or not fri
                or sun.get("depth_weighted_price") is None
                or fri.get("depth_weighted_price") is None
                or sun.get("dev_vs_median_pct") is None
                or not fri["depth_weighted_price"]):
            skipped.append(ticker)
            continue
        D = sun["dev_vs_median_pct"]
        R = ((sun["depth_weighted_price"] - fri["depth_weighted_price"])
             / fri["depth_weighted_price"] * 100.0)
        spread = _sunday_spread_pct(ticker, sun["ts"])
        gap, conf, _label = monday_gap_predict(
            D, R, sun.get("pools_used"), sun.get("qualifying_depth_usd"),
            spread, calibrated)
        try:
            ex = query("SELECT id FROM monday_gap WHERE ticker_id = ? "
                       "AND week_start = ?", [ticker, week_start])
        except Exception as e:
            return f"monday gap unavailable: existing-row check error ({e})"
        if ex:
            continue
        rows.append([ticker, week_start, gap, conf, MONDAY_GAP_VERSION,
                     None, "pending", None])
    if dry_run:
        print(f"DRY-RUN monday_gap week_start={week_start} "
              f"predictions={len(rows)} skipped={skipped or '-'}")
        for r in rows:
            print(f"DRY-RUN monday_gap row={r}")
        return ""
    if rows:
        try:
            pipeline([(
                "INSERT INTO monday_gap (ticker_id, week_start,"
                " gap_pred_pct, confidence, method_version,"
                " outcome_gap_pct, outcome, outcome_ts)"
                " VALUES (?,?,?,?,?,?,?,?)",
                r,
            ) for r in rows])
        except Exception as e:
            log(f"WEEKLY monday_gap write FAILED: {e}")
            return f"monday gap write unavailable: {e}"
    state["last_monday_gap_week"] = week_start
    log(f"WEEKLY monday_gap week_start={week_start} "
        f"predictions={len(rows)} skipped={skipped or '-'}")
    return ""


def _monday_gap_fill_outcomes(cycle_dt, state, dry_run=False):
    """Monday outcome branch. For each 'pending' row: actual gap =
    (first Monday dw at/after 13:30 UTC - Sunday-night dw) / Sunday dw.
    Accurate iff the sign matches AND |actual - pred| <= 1.0 pp (§2.2).
    A row stays 'pending' until both prices exist — never guessed."""
    try:
        pending = query("SELECT id, ticker_id, week_start, gap_pred_pct "
                        "FROM monday_gap WHERE outcome = 'pending'")
    except Exception as e:
        return f"monday gap outcome unavailable: pending-rows read error ({e})"
    if not pending:
        return ""
    filled, waiting = [], []
    for row in pending:
        try:
            sat = datetime.strptime(row["week_start"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            waiting.append(row.get("ticker_id"))
            continue
        sun, mon = sat + timedelta(days=1), sat + timedelta(days=2)
        sun_start = sun.strftime("%Y-%m-%dT00:00:00Z")
        mon_start = mon.strftime("%Y-%m-%dT00:00:00Z")
        mon_open = mon.strftime("%Y-%m-%dT13:30:00Z")
        sun_row = _latest_deviations_row(row["ticker_id"], sun_start, mon_start)
        if not sun_row or sun_row.get("depth_weighted_price") is None:
            waiting.append(row["ticker_id"])
            continue
        try:
            mon_rows = query("SELECT depth_weighted_price FROM deviations "
                             "WHERE ticker_id = ? AND ts >= ? "
                             "ORDER BY ts ASC LIMIT 1",
                             [row["ticker_id"], mon_open])
        except Exception:
            waiting.append(row["ticker_id"])
            continue
        if not mon_rows or mon_rows[0].get("depth_weighted_price") is None:
            waiting.append(row["ticker_id"])
            continue
        p_sun = sun_row["depth_weighted_price"]
        p_mon = mon_rows[0]["depth_weighted_price"]
        actual = (p_mon - p_sun) / p_sun * 100.0
        pred = row["gap_pred_pct"]
        same_sign = ((actual > 0 and pred > 0) or (actual < 0 and pred < 0)
                     or (actual == 0 and pred == 0))
        ok = same_sign and abs(actual - pred) <= 1.0
        filled.append([round(actual, 2), "accurate" if ok else "inaccurate",
                       cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), row["id"]])
    if dry_run:
        print(f"DRY-RUN monday_gap outcomes: fill={len(filled)} "
              f"waiting={waiting or '-'}")
        for f in filled:
            print(f"DRY-RUN monday_gap outcome={f}")
        return ""
    for f in filled:
        try:
            pipeline([(
                "UPDATE monday_gap SET outcome_gap_pct = ?, outcome = ?,"
                " outcome_ts = ? WHERE id = ?",
                f,
            )])
        except Exception as e:
            log(f"WEEKLY monday_gap outcome write FAILED id={f[3]}: {e}")
    if filled:
        log(f"WEEKLY monday_gap outcomes filled={len(filled)} "
            f"waiting={waiting or '-'}")
    return ""


def run_weekly_monday_gap(cycle_dt, state, dry_run=False):
    """Weekly Monday Gap (F2, monday_gap_v1): predict Sunday >= 22:00 UTC
    (after the tokenized Sunday session, before the US Monday open),
    fill outcomes Monday. Other days: no-op. Never raises; returns a
    gap fragment ('' when quiet). The 'eksperimental' label is a display
    concern (dashboard/web), not stored here beyond method_version."""
    wd = cycle_dt.weekday()  # Mon=0 ... Sun=6, UTC
    if wd == 6 and cycle_dt.hour >= 22:
        return _monday_gap_predict(cycle_dt, state, dry_run)
    if wd == 0:
        return _monday_gap_fill_outcomes(cycle_dt, state, dry_run)
    return ""


def _maybe_run_perp(cycle_dt):
    """Perp 5-min cycle, isolated from the DexScreener cycle: never
    raises. Runs BEFORE run_cycle in main() so a Hyperliquid failure
    can be recorded in the SAME cycle's poller_health gap_note (via
    the returned fragment) instead of its own health row — see
    run_cycle_perp. Returns the fragment ('' when quiet)."""
    try:
        st = load_state()
        if _perp_due(cycle_dt, st):
            frag = run_cycle_perp(cycle_dt, st)
            save_state(st)
            return frag
    except Exception as e:
        log(f"PERP CYCLE FAILED (uncaught, isolated): {e}")
        return f"hyperliquid perp cycle unavailable: {e}"
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
    """GET with 429/5xx backoff. Returns (pairs_list, http_code, err).

    S5 (fix ronde 8): retries cover 429 and EVERY 5xx (the old list
    429/500/502/503 missed e.g. 504/520s), and backoff exhaustion
    reports the REAL last code — the old code returned a hardcoded
    "429" even for transport timeouts, mislabelling the failure."""
    last_err = ""
    last_code = None
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
        last_code = code
        last_err = f"http {code}"
        if code == "429" or (code and code.startswith("5")) or r.returncode != 0:
            time.sleep(5 * (2 ** attempt))
            continue
        return [], code, last_err
    return [], last_code or "timeout", f"backoff exhausted ({last_err})"


# ======================================================================
# Multichain 2026-11-12 (SEED_MULTICHAIN_2026-11-12.md) — Base/Coinbase,
# BNB/bStocks, Robinhood Chain/Robinhood. Thresholds UNCHANGED
# (LIQ_MIN $100k, depth gate $250k, alert 1.0%).
# ======================================================================

# Seed set (dry-run only) — generated from /tmp/verify_multichain_out.json
# (verified 2026-11-12T12:50:30Z) via seed_multichain.trackable_pools +
# cap 13/issuer: 30 tickers, 115 pools (Base 15, BSC 24, Robinhood 76).
# Tuple per ticker: (chain, issuer, token_address, tier,
# [(pair_address, dex), ...]). Live cycles NEVER read this — they
# read pools from Turso after seed --live. Regenerate (never hand-
# edit) if the seed set changes.
MULTICHAIN_SEED = {
    "AAPLB": ("bsc", "bstocks", "0x431a3BEE82E2ca41e49895CbECE5bB0F76A89b7A", 2, [("0xe9b9998B2EC5430D2246c7f1F8D9f298c97D7365", "pancakeswap"), ("0x755f5baA43f692550AA46Be662240eEb99Ae7502", "metric")]),
    "AAPLc": ("base", "coinbase", "0xb200000000000000000000C2e324d24d7eEcd1fb", 2, [("0xF5FCB9CDAFcE67d50AfEf298F88E709d2B946BA6", "aero")]),
    "AAPLr": ("robinhood", "robinhood", "0xaF3D76f1834A1d425780943C99Ea8A608f8a93f9", 1, [("0xeab0adac76db99a233ed077ca6be7a3f708baee6f98b17df69f7e1a07d1dc2e4", "uniswap"), ("0xc748f4671a867db48b552f6b7650bf3255e05f80f00e3f7aad1b17ccb7898fdb", "uniswap"), ("0x8bb3514e2204E1cDF3Ac149EFEe7Ff04D91B719f", "uniswap"), ("0xAae0d815EE56e4092a5E5C2911E676Fea50B2d6D", "uniswap")]),
    "AMDr": ("robinhood", "robinhood", "0x86923f96303D656E4aa86D9d42D1e57ad2023fdC", 1, [("0xe6e17efdbdd916526293cf1b509171be4ffb04f47c4a5fe1a7367acdaa6ffd82", "uniswap"), ("0x48D284A2A4d3DC1b3Da08231Fe44317e7e7Aa51f", "uniswap"), ("0xde9f85fdd9e05a943a52f2c69ffafe3064a3287df03d02c9b431bc92d4781274", "uniswap")]),
    "AMZNc": ("base", "coinbase", "0xb200000000000000000000d9192b6B456483C2E8", 1, [("0x532e0F46d1e528507FC9454d5847C231f23bDDf6", "aero")]),
    "BABAB": ("bsc", "bstocks", "0x4eF9d3062c7F6ebA4AAE4990c5036598C6eff4ec", 1, [("0xfD95CB1391999006Eb91797a7c62acFe88b20292", "pancakeswap")]),
    "COINr": ("robinhood", "robinhood", "0x6330D8C3178a418788dF01a47479c0ce7CCF450b", 1, [("0x007a13fa152f6dc383cad20a8eaab4e1e2538b606936eae2a424f8aa47d6db31", "uniswap"), ("0x6707aeAc7D0e519B083219d27BB427364363183A", "uniswap"), ("0x7B549013a6b9943814e99f7286ACBf41793Aefd8", "sushiswap")]),
    "CRCLB": ("bsc", "bstocks", "0x80f3D493EBCe97e343c53D29a137942416B4ffC0", 2, [("0x29967c54c5Bf12E8158c8894376064b30ebaB297", "pancakeswap"), ("0xdC2b2F96bC1eb01E7286C688d5354e081AF188C4", "metric")]),
    "CRCLr": ("robinhood", "robinhood", "0xdF0992E440dD0be65BD8439b609d6D4366bf1CB5", 1, [("0x654E4143e82a5824445Ade0824351C2A9ACD95a8", "uniswap"), ("0x6d9af55c4cb0d740dc5237e8fe2d60e017412fb1af4e2d81e948124797e56748", "uniswap"), ("0x10906975ba92bce9209431984d3e3e4b0eac706db274e8d1a29358331a555987", "uniswap"), ("0x628c98ab436ee34a6a7decd606242890582591bdf7c9a35d90e0d08021c31ea0", "uniswap"), ("0x9C2a17cf6a763416dDD77Eaa1C612FF0ab8Be33D", "sushiswap")]),
    "GLDr": ("robinhood", "robinhood", "0xC9a981FEE1F9DEc688bb123ccDeCc63D0deBFC4e", 1, [("0x7A6A053eCCf1446A2633E05aA6D40D09381997ec", "uniswap"), ("0xfe281bbfa9aa658c1aa9c2ad1b0c62c4286f96c7cb1074296b54e869935a7a3a", "uniswap"), ("0xBA2f1ed4cEB2169D538d1e614D847E83C5A55913", "uniswap"), ("0x98996e833EA35EC17c3645Ca7b6Dd40d188564C4", "uniswap"), ("0x26250bA84465454bc731F710E46F1f32b167d66B", "uniswap"), ("0x17e5BD3aB5F33FBe2e1dC40d6580Be42C86e38aD", "aero"), ("0x9896AF2F6fED9939aCc87637b973b6484E6619D8", "ramses")]),
    "GOOGLB": ("bsc", "bstocks", "0x3F53De71c126BdaBAe20f9cD64848d317f6C3238", 1, [("0x89001D846f7CA36EE089F73eEFC25657E1798144", "pancakeswap"), ("0xebf6E16Dcc834B714b991cD21E551130B35E74FA", "uniswap")]),
    "GOOGLc": ("base", "coinbase", "0xb2000000000000000000002D0BA3164cc74f58B7", 1, [("0x16c70F04C3080a127486Cdf5a4C33c066bBF47C3", "aero"), ("0xB1987CAD1682841b4b641d50E520777eC5Ab5542", "aerodrome")]),
    "GOOGLr": ("robinhood", "robinhood", "0x2e0847E8910a9732eB3fb1bb4b70a580ADAD4FE3", 1, [("0x2eB3eC0c7e94F83aF3458dE5f907a9910932A6B5", "metric"), ("0x6d0f67069596c7ef9d1ce6981c1b6dbcd9a91b0c5393aebe9dd07c35e412df30", "uniswap"), ("0x34D0dC122CF9A8Eb296fC5e0D3A233625D7d19b7", "uniswap"), ("0xd4ecb79fdc521d7725d22b33ed43cb4e47aa96bfad76aa29577e3151f723ac5e", "uniswap"), ("0x8c2B4303fA0B99d07A5D3E9411497A277e65b673", "uniswap")]),
    "METAc": ("base", "coinbase", "0xb2000000000000000000008bC8786B856E61707C", 1, [("0xd072410fa13D242e1d53721Bcf7AF02e3455DC96", "aero"), ("0xEAF57753BC382E0324a1D43F72E7027705a2273E", "aerodrome")]),
    "METAr": ("robinhood", "robinhood", "0xc0D6457C16Cc70d6790Dd43521C899C87ce02f35", 1, [("0x5875d407a42965b0e768c8925cea290e06fa50603ef34fc99eb92a1050e6ae36", "uniswap"), ("0x8dc0387af606d84be8e4c2fc1da7bdc6d467337e9f3e075113f968922a190847", "uniswap"), ("0x90CABdA18279BBB3D935989aF807b08B0e8CeC61", "metric"), ("0xa4BdB396a69617eb7F70E2cc1EF526f7340b1B0d", "uniswap"), ("0x107a7Cb40d8665360ba10E59471Af06150A50922", "uniswap"), ("0x09B8dE3DeD768478376D98FBBe80d09AE8e6cD3c", "aero"), ("0x960f79D8DfEC7F2F0C1b24CdAC6BB9Df1371C6e2", "ramses")]),
    "MSFTc": ("base", "coinbase", "0xB200000000000000000000Ab99cFa739E253872B", 2, [("0x2740C0faAb738F6e346e545fDE02aEF9B1A01ee7", "aero")]),
    "MSTRc": ("base", "coinbase", "0xb2000000000000000000004884b426556b92883d", 1, [("0x66DCd42E6314B287110922AE36cB2a8bdEECc153", "aero"), ("0x988B949de9d3A3d2172F22C19694c7a5148c9E87", "aero"), ("0x8b27f626ab668197000BC722A1012022CAeD10E2", "aerodrome")]),
    "MSTRr": ("robinhood", "robinhood", "0xec262a75e413fAfD0dF80480274532C79D42da09", 1, [("0x319bac87e616a89e241c10aeb8afd4892a852cdd8b373cd9765ecddc40b87cfe", "uniswap"), ("0x1dae69f15c48eef452c79360cc8df58f5d5c3c1e6324ff8777d58c1feb053cdc", "uniswap"), ("0x70504a6FafdbfB75fE971FAA4dD716e79aC5624c", "uniswap"), ("0x17578C0e0D15da44f31677263114F71aE76653EA", "uniswap"), ("0xc105b8300ff65d750a0e4e63c7a879e20504069b770713464a5315e797735326", "uniswap"), ("0x6f8Dc7122B56017c46892F91D38d871acf787f9b", "uniswap"), ("0x93AF1dfBa0F8c904acB30B3D353Dc3670CB8D6DE", "giga")]),
    "NVDAB": ("bsc", "bstocks", "0x02Fca66C1D1aFB4E2A7884261eB00F63598a7436", 1, [("0x8FB4243b553aC29BA088aCf00B9B7dA24bD6690C", "pancakeswap"), ("0x720117A6D678ef37cf9792df051da87f5809d117", "metric"), ("0xCC2bFfaeC373a6004bb6cCc8a62Cdd66061f7C6a", "pancakeswap"), ("0x18d52270d09AB842c87acd45977dCF64a82FA4ad", "pancakeswap"), ("0xdEbed59510885E29CE1D3DA0e5412d49D21f0354", "pancakeswap"), ("0xDD9d5164CcBc57bE377a964Fc064135b03D06177", "uniswap")]),
    "NVDAc": ("base", "coinbase", "0xb20000000000000000000078ee7ce2fE4908108C", 1, [("0xF668e21993f0ACd7ab00BB1cFbAeD0df28A3C8EC", "aero"), ("0x853F5f1B92b16714Fe6CDA67CAad0856B83C7ab9", "aerodrome"), ("0xe82fa069a5e01a6dc36c6736b5de4f721d726291b080c69b48e21b9c5a11a2ad", "uniswap")]),
    "NVDAr": ("robinhood", "robinhood", "0xd0601CE157Db5bdC3162BbaC2a2C8aF5320D9EEC", 1, [("0xd4EB21209C4D6093f80B5b84f5C45cc093EA14a3", "uniswap"), ("0x62AB521f71431f78ac374CdbadC6cda3c8916b6C", "uniswap"), ("0xda14bf8a87711e1f30dbe620f2df3fdf371f7503f1a72202d15631f657651ec0", "uniswap"), ("0xC0Be1cb0f674D9737C72B2A63fC542361185b807", "uniswap"), ("0xA1513DA56f71b83D98124D645828A14a191b8010", "aero"), ("0xBc6426CdBCE142dfbff33303dc0923509f61eedc", "metric"), ("0x3bb34a44f1b2b5f32c034c38a53065a521a47b199700fa9bd19d60985ff24bf1", "uniswap"), ("0xa95b1fbdccb15d2b07509b980f63adab8a94303b1781f5ebc53b72942d12ddc1", "uniswap"), ("0x7990aad9e8fb048f49a155a7df5603db0366f0657035b78eb4196395cccb3dcd", "uniswap"), ("0xbc732a1a0baabce2574ec2bca24fccad8e2c38a061a37cefc17a2fd12809394f", "uniswap"), ("0xdac1904D823F7d6bcAaF431ceEe40c934fEd321b", "ramses")]),
    "PLTRr": ("robinhood", "robinhood", "0x894E1EC2D74FFE5AEF8Dc8A9e84686acCB964F2A", 1, [("0xee430ee1003e1985e1828a01b9a20dad67ad4302994fe2abb4a173de4ac54623", "uniswap"), ("0xb8d9b6b622bb03dd06d95790553f327710a73d85d845a59fa9e652638ca96ae6", "uniswap")]),
    "QQQB": ("bsc", "bstocks", "0x205812CdBed920aFf76C6580abD681a46D11efc7", 1, [("0x47BC06722295AC316A569EEF87aC32FAA455F441", "pancakeswap"), ("0xff2857Eef9563e92e9be9550989A80878d97676D", "metric"), ("0x7C84F9943Ec82cf2233c97A7Ee417f18bD2eC295", "pancakeswap"), ("0xfC4E77248b76feFc27c4CAc7151A2EE5B5cC590e", "uniswap"), ("0xe531fcb1F5a195de7608B9F4f9518544C2cdB693", "pancakeswap")]),
    "QQQr": ("robinhood", "robinhood", "0xD5f3879160bc7c32ebb4dC785F8a4F505888de68", 1, [("0x8493982435e4273028008cd181c84c0d6a548f96792fdb5acddcbb6a8c82d305", "uniswap"), ("0xD60A5d14dB690B7Afad71F76B108071D7175597d", "uniswap"), ("0xA40D00a55d43bA2d188039DCF88bD68f4F133E78", "uniswap"), ("0x74f5f207a1038C08F9980579a50D2719bfC15774", "metric"), ("0xf38009b348295f907c1f2e22aba84d731de3b7360d312881df1c206e85ea3b0b", "uniswap")]),
    "SNDKc": ("base", "coinbase", "0xb200000000000000000000397293Cb8cda9a10c5", 1, [("0x2836e062a3fe75943a7F4A552E2365b98E414E75", "aero")]),
    "SPCXB": ("bsc", "bstocks", "0xbe9D156892E55e7154BcD3cB0FEA677F9D3103E1", 1, [("0x66faaD27cf481f82d0089ec8156B3AA3636010C7", "pancakeswap"), ("0x977DaFFC095b33872E2741c19568925015C35b4d", "pancakeswap"), ("0x51A45A72Cc96CA3bA615E25e80a6Af2740ae2E2d", "uniswap"), ("0xce31C907A579f63Bb809bA01E462cdc44d7FA930", "metric")]),
    "SPYr": ("robinhood", "robinhood", "0x117cc2133c37B721F49dE2A7a74833232B3B4C0C", 1, [("0xfe2a80bb5618fd14984b92ca6d45bf5ba67443ddb1435e28b2e48df2fc1526cd", "uniswap"), ("0xe5923c8a8be481ec89a2ca784a2bbfa4235de6d88f92260fd66b660c4babf907", "uniswap"), ("0x8674c1c5544f3c9563565b5d4bd5916701d90b3559b072acf7cef5b4fc5b8dcd", "uniswap"), ("0xDDCBBa3666f578E3F09516f21Ff85BFee859AB5e", "uniswap"), ("0x509c6c6826ef06e0e29f24f18d9389533c52358a3b385d99a67a2afbb07f23c6", "uniswap"), ("0x05aFb8E895e77Ce70F79056137eA606b05BF5abD", "aero"), ("0x13783E80F95DC9Fc10622451a3eE755593F0E666", "metric"), ("0xa7Bb1AC63BBaB0C44316E6c8C455213441689167", "uniswap"), ("0xe1ae6a4c6ccc9f037389a8d50a4f577bde1a9fe01d85d88ecbbd39955ce53288", "uniswap"), ("0x38453c115607463Ac284820Ce959831042f3Df4E", "ramses"), ("0x4A9b7cCBa4a3CD9Ee604AfA95d3DfA77D0d593e5", "aero")]),
    "TSLAB": ("bsc", "bstocks", "0x5b1910eAaD6450E50f816082Aa078C41F10C292f", 1, [("0xB0f5E5400E8F0F7C242F2b7740C004f020579c41", "pancakeswap"), ("0xf449D597cef44FCb9fDbA861427d066C585C450d", "metric")]),
    "TSLAc": ("base", "coinbase", "0xb2000000000000000000001e800a7f5189430cD0", 2, [("0x7A33000372f3F028f074182CCb9d16cBEEfBF920", "aero")]),
    "TSLAr": ("robinhood", "robinhood", "0x322F0929c4625eD5bAd873c95208D54E1c003b2d", 1, [("0xA953CA88ff430e9487c60cA34d757414f4efdA07", "uniswap"), ("0xf4ACdAEEB7022862A763C9B1B885e11191c889E3", "uniswap"), ("0x8517f8071ae5b831b738052f12125e8e3d6c158b78728aa44ce3b25e5104d32e", "uniswap"), ("0x3ea70ce0b34473692549f97e630a1d82dc05cea94fa55f81b50f10c8c6d8186f", "uniswap"), ("0x99932C7660dD58cf19f0e82e97F288d88d033480", "metric"), ("0x0927698e8716bbb958a2cde0fc4f31d7a2b9a5b0ee1e501dc15e29788277dfa2", "uniswap")]),
}

def _chunks(lst, n=30):
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def fetch_dex_batches_by_chain(addrs_by_chain):
    """One DexScreener /tokens batch per chain (<=30 addresses/call).

    Returns (pairs, n_requests, chain_errors). pairs is the combined
    list of pair dicts from all successful chains. A failed chain is
    recorded in chain_errors {chain: err} and contributes no pairs —
    the caller decides whether that fails the cycle (Solana: yes, old
    behavior) or only leaves a gap note (other chains). A chain with
    several 30-address chunks stops at the first failed chunk (no
    hammering). Never raises."""
    pairs, n_requests, chain_errors = [], 0, {}
    for chain in sorted(addrs_by_chain):
        for chunk in _chunks(addrs_by_chain[chain], 30):
            n_requests += 1
            cp, _code, err = dex_fetch(DEX.format(",".join(chunk)))
            if err:
                chain_errors[chain] = err
                break
            pairs.extend(cp)
    return pairs, n_requests, chain_errors


def fill_missing_pools(by_pair, pools, addr_by_ticker):
    """Coverage check for pools missing from DexScreener batch response(s).

    First a case-insensitive retry (address casing), then a per-token
    fallback fetch — once per DISTINCT token address, not once per
    missing pool (S5 fix ronde 8: several pools share one token).
    Mutates by_pair in place. Returns (fallback_used, fallback_requests,
    fallback_errors). Never raises."""
    missing = [pl for pl in pools if pl["pair_address"] not in by_pair]
    if not missing:
        return False, 0, 0
    lower = {k.lower(): v for k, v in by_pair.items()}
    still = [pl for pl in missing if pl["pair_address"].lower() not in lower]
    for pl in missing:
        if pl["pair_address"].lower() in lower:
            by_pair[pl["pair_address"]] = lower[pl["pair_address"].lower()]
    if not still:
        return False, 0, 0
    by_addr = {}
    for pl in still:
        addr = addr_by_ticker.get(pl["ticker_id"])
        if addr:
            by_addr.setdefault(addr, []).append(pl)
    fallback_requests, fallback_errors = 0, 0
    for addr, pls in by_addr.items():
        fallback_requests += 1
        tp, _c, _e = dex_fetch(DEX.format(addr))
        if _e:
            fallback_errors += 1
            continue
        for p in tp:
            for pl in pls:
                if p.get("pairAddress") == pl["pair_address"]:
                    by_pair[pl["pair_address"]] = p
                    break
    return True, fallback_requests, fallback_errors


def _multichain_ticker_summary(lst):
    """Per-ticker math — MIRROR of the run_cycle deviations loop
    (LIQ_MIN filter, >25% price-sanity guard with >=3 pools, depth-
    weighted price, cross-venue median, dev_vs_median). Keep in sync
    with run_cycle; this copy exists so the dry run can run WITHOUT
    touching Turso or state. Returns dict with dw, dev_med, depth,
    pools_used, n_excluded (dev_med None when <2 qualifying pools)."""
    kept, n_excluded = lst, 0
    if len(lst) >= 3:
        med_all = statistics.median([pr for pr, _ in lst])
        if med_all:
            kept = [(pr, r) for pr, r in lst
                    if abs(pr - med_all) / med_all <= 0.25]
            n_excluded = len(lst) - len(kept)
            if not kept:
                kept, n_excluded = lst, 0
    depth = sum(r for _, r in kept)
    dw = sum(pr * r for pr, r in kept) / depth if depth else None
    prices = [pr for pr, _ in kept]
    median = statistics.median(prices) if len(prices) >= 2 else None
    dev_med = ((dw - median) / median * 100.0) if (median and dw) else None
    return {"dw": dw, "dev_med": dev_med, "depth": depth,
            "pools_used": len(kept), "n_excluded": n_excluded}


def run_multichain_dry_run():
    """--dry-run-multichain: one live DexScreener read per NEW chain
    (Base 9 addrs, BSC 8, Robinhood 13) over the EMBEDDED seed set
    (30 tickers, 115 pools), then the same LIQ_MIN / price-guard /
    depth-gate math as run_cycle. 0 Turso writes, 0 state writes, no
    raw archive, no hourly/perp jobs. Returns exit code (0 = data
    returned for at least one chain)."""
    pools, addr_by_ticker = [], {}
    for ticker in sorted(MULTICHAIN_SEED):
        chain, _issuer, addr, tier, plist = MULTICHAIN_SEED[ticker]
        addr_by_ticker[ticker] = addr
        for pair_address, dex in plist:
            pools.append({"pool_id": f"{chain}:{pair_address}",
                          "ticker_id": ticker, "chain": chain, "dex": dex,
                          "pair_address": pair_address, "tier": tier})
    addrs_by_chain = {}
    for t in sorted(addr_by_ticker):
        addrs_by_chain.setdefault(MULTICHAIN_SEED[t][0], []).append(
            addr_by_ticker[t])
    pairs, dex_requests, chain_errors = fetch_dex_batches_by_chain(
        addrs_by_chain)
    print(f"DRY-RUN-MULTICHAIN chains={sorted(addrs_by_chain)} "
          f"tickers={len(addr_by_ticker)} seeded_pools={len(pools)} "
          f"dex_batch_requests={dex_requests} "
          f"chain_errors={chain_errors or '-'} "
          f"pairs_returned={len(pairs)}")
    if chain_errors and not pairs:
        print("DRY-RUN-MULTICHAIN FAIL: no DexScreener data returned")
        return 1
    by_pair = {}
    for p in pairs:
        by_pair[p.get("pairAddress")] = p
    fallback_used, fallback_requests, fallback_errors = fill_missing_pools(
        by_pair, pools, addr_by_ticker)
    print(f"DRY-RUN-MULTICHAIN fallback_used={fallback_used} "
          f"fallback_requests={fallback_requests} "
          f"fallback_errors={fallback_errors} "
          f"total_dex_requests={dex_requests + fallback_requests}")
    per_ticker, n_matched, n_qual = {}, 0, 0
    for pl in pools:
        p = by_pair.get(pl["pair_address"])
        if not p:
            continue
        n_matched += 1
        liq = p.get("liquidity") or {}
        try:
            price = float(p["priceUsd"]) if p.get("priceUsd") else None
        except (TypeError, ValueError):
            price = None
        reserve = liq.get("usd")
        if price is not None and reserve is not None and reserve >= LIQ_MIN:
            n_qual += 1
            per_ticker.setdefault(pl["ticker_id"], []).append((price, reserve))
    n_depth_gate = n_two_pool = n_alert_cand = 0
    print("DRY-RUN-MULTICHAIN per-ticker "
          "(pools matched/seeded, qualifying>=100k, depth, dw, dev%):")
    for ticker in sorted(MULTICHAIN_SEED):
        chain = MULTICHAIN_SEED[ticker][0]
        seeded = len(MULTICHAIN_SEED[ticker][4])
        matched = sum(1 for pl in pools
                      if pl["ticker_id"] == ticker
                      and pl["pair_address"] in by_pair)
        s = _multichain_ticker_summary(per_ticker.get(ticker, []))
        depth_ok = s["depth"] is not None and s["depth"] >= 250000.0
        two_pool = s["pools_used"] >= 2
        if depth_ok:
            n_depth_gate += 1
        if two_pool:
            n_two_pool += 1
        if depth_ok and two_pool and s["dev_med"] is not None \
                and abs(s["dev_med"]) >= 1.0:
            n_alert_cand += 1
        dw = f"${s['dw']:,.2f}" if s["dw"] else "-"
        dev = f"{s['dev_med']:+.2f}%" if s["dev_med"] is not None else "-"
        print(f"  {ticker:8s} {chain:9s} pools {matched}/{seeded} "
              f"qual={s['pools_used']} depth=${s['depth']:>12,.0f} dw={dw} "
              f"dev={dev} depth_gate={'Y' if depth_ok else 'n'}"
              f"{' guard_excl=' + str(s['n_excluded']) if s['n_excluded'] else ''}")
    n_tickers_seen = len(per_ticker)
    print(f"DRY-RUN-MULTICHAIN TOTAL tickers_with_data={n_tickers_seen}/30 "
          f"pools_matched={n_matched}/115 pools_qualifying>={LIQ_MIN:,.0f}"
          f"={n_qual} tickers_depth>=250k={n_depth_gate} "
          f"tickers_>=2pools={n_two_pool} "
          f"alert_candidates(|dev|>=1%+depth+2pools)={n_alert_cand}")
    return 0


def _hourly_due(cycle_dt, state):
    """True when the hourly redemption/PoR slot should run.

    S8 (fix ronde 8): the slot is due 55 min after the last SUCCESSFUL
    hourly run. A failed attempt does not make it due again at once —
    it backs off 15 min — so a persistently failing RPC cannot make
    every 5-min cycle pay the full hourly cost, while a transient
    failure is still retried soon instead of waiting out the hour."""
    last = state.get("last_hourly_check")
    if last:
        try:
            age_last = (cycle_dt - datetime.fromisoformat(last)).total_seconds()
        except (TypeError, ValueError):
            age_last = None
        # GG-31 (fix ronde 9, P2-1): a FUTURE last stamp is due, never
        # "recent" — the old `age_last < 55*60` was also true for a
        # negative age, so a future-dated state suppressed the slot.
        if age_last is not None and 0 <= age_last < 55 * 60:
            return False
    failed_at = state.get("last_hourly_failed_at")
    if failed_at:
        try:
            age_f = (cycle_dt - datetime.fromisoformat(failed_at)).total_seconds()
        except (TypeError, ValueError):
            age_f = None
        # GG-31: same mirror direction — a future failed-at stamp does
        # not earn the 15-min backoff.
        if age_f is not None and 0 <= age_f < 15 * 60:
            return False
    return True


def run_cycle(cycle_dt, extra_gap_notes=None, dry_run=False):
    """One polling cycle. Returns True on success.
    extra_gap_notes: fragments from isolated jobs (e.g. the perp cycle,
    which runs before this cycle in main()) to record in this cycle's
    poller_health gap_note — they never affect cycles_ok.
    dry_run=True (--dry-run): live DexScreener reads + full computation,
    but ZERO Turso writes (no snapshots/deviations/health rows), no raw
    archive, no hourly/perp/liquidation/monday-gap jobs, no state save.
    Turso READS still happen (pools, universe, latest redemption/perp,
    median depth) — reads, not writes."""
    cycle_ts = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Idempotency: skip if this minute already has a successful heartbeat.
    # (Skipped in dry-run: a dry run must compute even if a live cycle
    # already succeeded this minute, and must never be mistaken for one.)
    if not dry_run:
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

    # Multichain (2026-11-12): ONE DexScreener batch per chain, not one
    # mixed batch. The /tokens endpoint caps at 30 addresses per call
    # AND returns at most ~30 pairs per response; 13 Solana + 30
    # multichain addresses in one call would overflow both caps, and a
    # per-chain batch keeps a truncated response attributable to its
    # chain. Chain per ticker comes from pools.chain (seeded rows carry
    # base/bsc/robinhood; Solana rows carry solana).
    addrs_by_chain = {}
    for t in tickers:
        addr = addr_by_ticker.get(t)
        if not addr:
            continue
        chain = next((p["chain"] for p in pools if p["ticker_id"] == t),
                     "solana")
        addrs_by_chain.setdefault(chain, [])
        if addr not in addrs_by_chain[chain]:
            addrs_by_chain[chain].append(addr)
    pairs, dex_requests, chain_errors = fetch_dex_batches_by_chain(
        addrs_by_chain)
    fallback_used = False
    if "solana" in chain_errors:
        # Old behavior preserved: a failed Solana batch fails the cycle.
        err = chain_errors["solana"]
        log(f"CYCLE {cycle_ts} FAIL dexscreener {err}")
        if dry_run:
            print(f"DRY-RUN CYCLE {cycle_ts} FAIL dexscreener {err}")
            return False
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
    # Coverage check: batch claim verification + per-token fallback
    # (once per DISTINCT token address — see fill_missing_pools).
    fallback_used, fallback_requests, fallback_errors = fill_missing_pools(
        by_pair, pools, addr_by_ticker)

    # Archive raw response (batch responses; fallback pairs noted in meta).
    # Skipped in dry-run (no local writes either — dry-run prints only).
    if dry_run:
        raw_ref = "dry-run"
    else:
        os.makedirs(os.path.join(RAW_DIR, cycle_dt.strftime("%Y-%m-%d")), exist_ok=True)
        raw_ref = os.path.join(
            "raw", cycle_dt.strftime("%Y-%m-%d"),
            cycle_dt.strftime("%H%M%S") + ".json.gz",
        )
        with gzip.open(os.path.join(BASE, raw_ref), "wt", encoding="utf-8") as f:
            json.dump({
                "cycle_ts": cycle_ts, "tight_window": tight,
                "batch_addresses": len(batch_addrs),
                "dex_requests": dex_requests,
                "fallback_requests": fallback_requests,
                "chains": sorted(addrs_by_chain),
                "chain_errors": chain_errors or None,
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
    # F3 (exit_score_v1, DESAIN §2.3): inputs gathered once per cycle,
    # latest-only, bounded reads. A failure here never breaks the cycle
    # — the affected component is simply not counted (partial score).
    # state is loaded here (earlier than the old hourly-slot load) so
    # the median-depth cache is available before the deviations loop.
    state = load_state()
    try:
        refresh_median_depth_7d(state, cycle_dt, list(per_ticker.keys()))
    except Exception as _e:
        log(f"MEDIAN-DEPTH refresh unavailable: {_e}")
    red_status, red_close_h = _latest_redemption_status(cycle_dt)
    perp_now = _latest_perp_by_ticker(cycle_dt)
    median7d = state.get("median_depth_7d") or {}
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
        # F3: exit_score_v1 rides this row (+0 writes). Funding/OI come
        # from the latest fresh perp snapshot (<=15 min); OI change is
        # vs 24h ago. Missing inputs -> partial score, never zero-filled.
        _p = perp_now.get(ticker)
        _funding = _p.get("funding") if _p else None
        _oi_chg = None
        if _p and _p.get("oi") is not None:
            _oi_old = _oi_24h_ago(ticker, cycle_dt)
            if _oi_old:
                _oi_chg = (_p["oi"] - _oi_old) / _oi_old * 100.0
        _sc = exit_score_v1(dev_med, depth, median7d.get(ticker),
                            red_status, red_close_h, _funding, _oi_chg)
        _exit = _sc["score_100"]
        _exit_ver = _sc["method_version"] if _exit is not None else None
        stmts.append((
            "INSERT INTO deviations (ticker_id, ts, depth_weighted_price,"
            " dev_vs_close_pct, dev_vs_median_pct, qualifying_depth_usd,"
            " pools_used, pools_excluded, redemption_status, por_age_hours,"
            " weekend_risk_score, exit_score, exit_score_version,"
            " method_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [ticker, cycle_ts, dw, None, dev_med, depth, len(kept),
             n_excluded, None, None, None, _exit, _exit_ver,
             "v1-median-only"],
        ))

    # Hourly slot: redemption & PoR (both automated since Wave 3 / PoR v1).
    # state was already loaded above (F3 inputs); do NOT reload here.
    gap_bits = []
    if extra_gap_notes:
        gap_bits.extend([g for g in extra_gap_notes if g])
    if chain_errors:
        # Non-Solana only here (a Solana error returned early above):
        # that chain's pools stay missing this cycle; the Solana cycle
        # itself still succeeds. Isolation, like the perp cycle.
        gap_bits.append("dexscreener chain batch failed: " + "; ".join(
            f"{c}: {e}" for c, e in sorted(chain_errors.items())))
    if guard_notes:
        gap_bits.append(f"price-guard excluded pool(s): {', '.join(guard_notes)}")
    if fallback_used:
        gap_bits.append("dexscreener batch incomplete; per-token fallback used")
    if fallback_errors:
        gap_bits.append(f"per-token fallback errors: {fallback_errors} token(s)")
    if missing_now:
        gap_bits.append(f"{len(missing_now)} tracked pools missing from response")
    now_iso = cycle_dt.isoformat()
    _hourly_ran = False
    if dry_run:
        log(f"CYCLE {cycle_ts} DRY-RUN hourly slot skipped "
            f"(use --dry-run-hourly for redemption/PoR)")
    elif _hourly_due(cycle_dt, state):
        _hourly_ran = True
        # Wave 3: real hourly redemption observation (schedule + on-chain).
        # A failure here must never break the deviation cycle, so the
        # hourly write lives in its own pipeline call inside
        # run_hourly_redemption; only its gap fragment lands here.
        hourly_failed = False
        try:
            _frag = run_hourly_redemption(cycle_dt, state)
            if _frag:
                gap_bits.append(_frag)
                # Only a FAILURE fragment holds the clock back. An
                # informational fragment (on-chain PAUSE observed,
                # partial coverage honestly recorded) is a successful
                # observation — the clock advances.
                if "failed" in _frag:
                    hourly_failed = True
        except Exception as _e:
            gap_bits.append(f"hourly redemption failed: {_e}")
            hourly_failed = True
        # PoR v1 (ACC'd): same isolation pattern as redemption.
        try:
            _frag = run_hourly_por(cycle_dt, state)
            if _frag:
                gap_bits.append(_frag)
                if "failed" in _frag:
                    hourly_failed = True
        except Exception as _e:
            gap_bits.append(f"hourly PoR failed: {_e}")
            hourly_failed = True
        # F4 (penambahan 2026-11-12): liquidation guard rides the same
        # hourly slot. It NEVER holds the shared clock back — its
        # fragments deliberately avoid the word 'failed' (see
        # run_hourly_liquidation), so hourly_failed is untouched here.
        try:
            _frag = run_hourly_liquidation(cycle_dt, state)
            if _frag:
                gap_bits.append(_frag)
        except Exception as _e:
            gap_bits.append(f"hourly liquidation unavailable: {_e}")
        # S8 (fix ronde 8): the shared hourly clock advances ONLY when
        # BOTH hourly jobs succeeded. The old code advanced it
        # unconditionally, so a failed hour silently waited out the
        # next 55 min; a failed attempt instead backs off 15 min
        # (see _hourly_due) and is retried.
        if hourly_failed:
            state["last_hourly_failed_at"] = now_iso
        else:
            state["last_hourly_check"] = now_iso
            state.pop("last_hourly_failed_at", None)
    # F4 follow-up (DESAIN §3.2): while any ticker is warning/critical,
    # re-observe every 5 min until the condition clears. Bounded: only
    # while the alert set is non-empty, only on 5-min marks, and never
    # in the same cycle the hourly slot already observed (no double row).
    if (state.get("liquidation_alert_tickers") and not _hourly_ran
            and not dry_run and cycle_dt.minute % 5 == 0):
        try:
            _frag = run_hourly_liquidation(cycle_dt, state)
            if _frag:
                gap_bits.append(_frag)
        except Exception as _e:
            gap_bits.append(f"hourly liquidation follow-up unavailable: {_e}")
    # F2 (penambahan 2026-11-12): Monday Gap prediction (Sun >=22:00 UTC)
    # + outcome fill (Mon). No-op on other days; never breaks the cycle.
    # Skipped in dry-run (it writes monday_gap rows).
    if not dry_run:
        try:
            _frag = run_weekly_monday_gap(cycle_dt, state)
            if _frag:
                gap_bits.append(_frag)
        except Exception as _e:
            gap_bits.append(f"weekly monday gap unavailable: {_e}")
    # Equity-close slot: once per NYSE day after 16:30 ET (median-only mode).
    et = cycle_dt.astimezone(ET)
    if is_nyse_day(et) and (et.hour, et.minute) >= (16, 30):
        if state.get("last_equity_note_date") != et.strftime("%Y-%m-%d"):
            gap_bits.append(
                "equity-close: no licensed equity source configured "
                "(median-only mode; dev_vs_close_pct NULL)")
            state["last_equity_note_date"] = et.strftime("%Y-%m-%d")
    if not dry_run:
        save_state(state)

    # GG-16 / M1 (fix ronde 8): a cycle that wrote ZERO snapshots and
    # ZERO deviations is a FAILED cycle, never a success heartbeat. The
    # old code wrote cycles_ok=1 unconditionally here, so an HTTP 200
    # with no pairs refreshed the global freshness verdict forever
    # (healthSummary / the bot's 30-min gate look only at cycle_ts
    # and cycles_ok — nothing downstream reads gap_note).
    if n_snap == 0 and not per_ticker:
        gap_bits.append("empty response: no snapshots or deviations written")
        if dry_run:
            print(f"DRY-RUN CYCLE {cycle_ts} FAIL empty response: "
                  f"no snapshots or deviations written")
            return False
        try:
            pipeline([(
                "INSERT INTO poller_health (cycle_ts, cycles_expected, cycles_ok,"
                " failed_sources, gap_note) VALUES (?,?,?,?,?)",
                [cycle_ts, 1, 0, "dexscreener",
                 "; ".join(gap_bits) if gap_bits else None],
            )])
        except Exception as e:
            log(f"CYCLE {cycle_ts} FAIL empty response + heartbeat write "
                f"failed: {e}")
        log(f"CYCLE {cycle_ts} FAIL empty response: no snapshots or "
            f"deviations written")
        return False

    if dry_run:
        # No Turso writes: print what WOULD have been written instead
        # of the final pipeline (snapshots + deviations + health row).
        print(f"DRY-RUN CYCLE {cycle_ts} OK tight={tight} "
              f"snapshots_would_write={n_snap} "
              f"deviations_would_write={len(per_ticker)} "
              f"missing={len(missing_now)} fallback={fallback_used} "
              f"dex_requests={dex_requests + fallback_requests} "
              f"chain_errors={chain_errors or '-'} "
              f"guard={';'.join(guard_notes) if guard_notes else '-'}")
        return True
    stmts.append((
        "INSERT INTO poller_health (cycle_ts, cycles_expected, cycles_ok,"
        " failed_sources, gap_note) VALUES (?,?,?,?,?)",
        [cycle_ts, 1, 1, None, "; ".join(gap_bits) if gap_bits else None],
    ))
    try:
        pipeline(stmts)
    except Exception as e:
        # S10 (fix ronde 8): a failing final write still attempts a
        # FAILURE heartbeat, so the cycle is visible as failed instead
        # of vanishing with no heartbeat row at all.
        log(f"CYCLE {cycle_ts} FAIL final pipeline: {e}")
        try:
            pipeline([(
                "INSERT INTO poller_health (cycle_ts, cycles_expected, cycles_ok,"
                " failed_sources, gap_note) VALUES (?,?,?,?,?)",
                [cycle_ts, 1, 0, "turso",
                 f"final pipeline failed: {e}"
                 + ("; " + "; ".join(gap_bits) if gap_bits else "")],
            )])
        except Exception as e2:
            log(f"CYCLE {cycle_ts} FAIL failure heartbeat also failed: {e2}")
        return False
    log(f"CYCLE {cycle_ts} OK tight={tight} snapshots={n_snap} "
        f"deviations={len(per_ticker)} missing={len(missing_now)} "
        f"fallback={fallback_used} dex_req={dex_requests + fallback_requests} "
        f"chain_errors={chain_errors or '-'} "
        f"guard={';'.join(guard_notes) if guard_notes else '-'}")
    return True


def main():
    if "--dry-run-multichain" in sys.argv:
        # Multichain 2026-11-12: one live DexScreener read per NEW chain
        # (Base, BSC, Robinhood) over the embedded seed set + the same
        # LIQ_MIN / price-guard / depth-gate math as run_cycle.
        # 0 Turso writes, 0 state writes. No lock needed (nothing shared
        # is written).
        return run_multichain_dry_run()
    if "--dry-run" in sys.argv:
        # Plain dry run: one DB-driven cycle (run_cycle dry_run=True) —
        # live DexScreener reads + full computation, 0 Turso writes, no
        # lock, no perp cycle (use --dry-run-perp for that), no hourly
        # jobs (use --dry-run-hourly). Multichain tickers appear here
        # only AFTER seed --live has written their pools to Turso; until
        # then use --dry-run-multichain for the seed set.
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        ok = run_cycle(now, dry_run=True)
        if ok:
            print("DRY-RUN done: 0 Turso writes (snapshots/deviations/"
                  "health NOT written). Multichain tickers appear here "
                  "only after seed --live; see --dry-run-multichain.")
        return 0 if ok else 1
    if "--dry-run-hourly" in sys.argv:
        # Wave 3 verification: compute one hourly redemption observation
        # (live public-RPC reads) and print it WITHOUT writing anything.
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        run_hourly_redemption(now, {}, dry_run=True)
        run_hourly_por(now, {}, dry_run=True)
        return 0
    if "--dry-run-perp" in sys.argv:
        # Penambahan 2026-11-12 (F1): one live Hyperliquid read
        # (allMids + metaAndAssetCtxs dex xyz) and print the rows that
        # WOULD be written to perp_snapshots. No Turso writes.
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        run_cycle_perp(now, {}, dry_run=True)
        return 0
    if "--dry-run-liquidation" in sys.argv:
        # Penambahan 2026-11-12 (F4): one live mark+oracle read and
        # print the rows that WOULD be written to liquidation_watch.
        # No Turso writes.
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        run_hourly_liquidation(now, {}, dry_run=True)
        return 0
    if "--dry-run-monday-gap" in sys.argv:
        # Penambahan 2026-11-12 (F2): run the weekly job for the CURRENT
        # moment and print what it WOULD write. Prediction only fires
        # Sunday >=22:00 UTC, outcome fill only Monday; other days this
        # prints nothing and exits 0. No Turso writes.
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        frag = run_weekly_monday_gap(now, {}, dry_run=True)
        if frag:
            print(f"DRY-RUN monday_gap: {frag}")
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
            # S10 (fix ronde 8): an uncaught cycle failure used to kill
            # the whole tight-window loop with no failure heartbeat.
            # A failed minute is logged and skipped; the loop continues
            # to the next minute (run_cycle itself writes a failure
            # heartbeat for the failures it catches).
            # F1: perp runs BEFORE the DexScreener cycle so a Hyperliquid
            # failure lands in this cycle's gap_note (never its own
            # health row — see run_cycle_perp). Never raises.
            perp_frag = _maybe_run_perp(cur)
            try:
                run_cycle(cur, extra_gap_notes=[perp_frag] if perp_frag else None)
            except Exception as e:
                log(f"TIGHT CYCLE {cur.strftime('%Y-%m-%dT%H:%M:%SZ')} "
                    f"FAILED (uncaught, continuing): {e}")
            nxt = (datetime.now(UTC).replace(second=0, microsecond=0)
                   + timedelta(minutes=1))
            time.sleep(max(0, (nxt - datetime.now(UTC)).total_seconds()) + 1)
        log("TIGHT LOOP done")
    else:
        # F1: perp runs BEFORE the DexScreener cycle (see tight loop).
        perp_frag = _maybe_run_perp(now)
        try:
            run_cycle(now, extra_gap_notes=[perp_frag] if perp_frag else None)
        except Exception as e:
            log(f"CYCLE FAILED (uncaught): {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
