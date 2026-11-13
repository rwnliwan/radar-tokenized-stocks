"""Radar Tokenized Stocks — Telegram bot (MVP, free tier).

Alert rules (design §5.3, adapted where the schema forces it — see
notes below):
- Market OPEN: inter-venue spread (max-min)/depth-weighted >= 1.0%,
  qualifying depth >= $250k, >= 2 qualifying pools. Spread is
  evaluated on price-sanity-guarded venues (same >25%-from-median,
  >=3-pool rule as the poller guard; fix 2026-11-08, Q6 vote A 3-0):
  a pool the guard excluded cannot set hi/lo.
- Any time: |dev vs cross-venue median| >= 3.0% -> HIGH priority
  deviation alert. Median basis is labeled as such: vs-close is NULL
  in median-only mode (license pending), so no vs-close alert fires.
- Redemption: live rule fires on latest status closed/gated/paused.
  PER-TICKER (un-batched 2026-10-25, Septian's call): one message
  per ticker PER CLOSED WINDOW (rule B, ACC 2026-10-25): a closed
  weekend is 13 messages per channel, with NO daily re-fire while
  the window stays closed.
  ADAPTATION (gap R7, BUILT 2026-11-09): the design's "closing
  within <=24h" rule IS live now, as a distinct alert type
  'redemption_closing_soon'. There is still no issuer-published
  close-time feed — the close-time is DERIVED from the same official
  24/5 schedule + NYSE calendar that already drives the live status
  (next_schedule_close_utc: 00:00 ET ending the last NYSE business
  day before a weekend/holiday), so it carries the same
  schedule-derived honesty label, never presented as issuer
  confirmation. It fires while the status is still open and the
  derived close is <=24h away (typically Fridays and days before a
  NYSE holiday), once per 24h per channel (standard dedup, NOT the
  once-per-window rule — no window exists yet), and never suppresses
  the later closed-window alert (different alert type).
- PoR: latest feed age > 72h (or last update older than 72h).
- F1 perp_deviation (built 2026-11-13, DESAIN §2.2): |perp_px - dw| / dw
  >= 1.0% (high priority >= 3.0%), spot depth >= $250k, perp snapshot
  fresh (<= 15 min). Perp trades 24/7, so this fires any time, not
  only when the market is open. The deviation is computed live from
  perp_snapshots.perp_px and the deviations dw — the same formula as
  api/worker.js perp_dev_pct. No stored perp-deviation column exists.
- F3 exit_high (built 2026-11-13, DESAIN §2.4): deviations.exit_score
  (0-100 scale, exit_score_v2) >= 70, 1x/ticker/24h. M5 rule: fires
  only when exit_score_components >= 3 — a partial score never fires
  'high' (live proof: TSLAB 82.0 on 1 component, 2026-11-13).
  Factual language only, never 'sell'/'exit now'.
- Stale data gate (design §7.1): when the last successful poller
  cycle is older than 30 minutes, NO new alerts are sent. The admin
  "poller troubled" alert goes to the configured admin destination
  (RADAR_ADMIN_CHAT_ID; gap R8 P1-G2, built 2026-11-09): at most one
  message per hour per stale episode, and only a log line when no
  admin destination is configured — never to the public EN/ID
  channels.

Dedup: for non-redemption types, same (ticker, alert_type) is not
re-sent within a true 24h of a logged alert (any outcome).
Redemption types instead use once-per-window: suppressed while an
alert for the same ticker+type exists since the current closed
window began (see alerted_in_current_window). SINGLE-SNAPSHOT RULE
(2026-10-26): one pass reads redemption_windows ONCE
(snapshot_redemption_rows) and shares that snapshot between
evaluation and dedup. Previously each side queried separately; a
poller commit landing between the two reads made evaluation see
'closed' while dedup saw 'no live window', re-firing 13 redemption
alerts on 2026-10-26 after the window had opened. Never re-query
redemption status inside the suppression path. Precision (fix ronde 5):
the snapshot is one query PER ISSUER in sequence, not one atomic
database snapshot — a poller commit between two issuer queries can
still split status ACROSS issuers. What the rule guarantees is that
evaluation and dedup agree on the same rows; it does not guarantee
the window is still closed by the time a message is sent. Redemption dedups per
ticker: ('TSLAx', 'redemption') and ('TSLAx', 'redemption_paused')
are DISTINCT keys, so a recorded closed alert never suppresses a
paused alert for the same ticker (and vice versa). Paused is HIGH
priority: red head marker, same severity vocabulary as the
deviation_high alert.
Accuracy outcomes (§5.4) are evaluated
by a later job, not here; new rows start as 'pending'.

BOT TOKEN: lazy-loaded from vault entry "custom.radar-telegram"
ONLY inside send_message() on the live path. Dry-run and live
evaluation NEVER touch the token. If the entry is missing, live
sending fails fast with a clear message — the token does not exist
yet (Septian creates the bot via BotFather). No token value is ever
printed, logged, or written anywhere. No placeholder token is used.

TICKER_PAGE_BASE is the live public-site base URL
(https://radar.omdanny.site); alert links point at the real
/ticker/<ticker> route (web/src/app/ticker/[id]/page.tsx).
"""
import argparse
import fcntl
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard"))
from i18n import DONATE_PAY_URL, t as _t  # noqa: E402  (pure strings, no Streamlit import)

# --- Turso (DB token: vault custom.turso-radar; same pattern as poller) ---
TURSO_HOST = "radar-tokenized-stocks-trisaktipan.aws-ap-northeast-1.turso.io"
TURSO_URL = f"https://{TURSO_HOST}/v2/pipeline"
for _p in (
    "/opt/hatch/workflow-skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/templates/skill/bin",
):
    if os.path.exists(os.path.join(_p, "dynamic_credentials.py")):
        sys.path.insert(0, _p)
        break

_DB_TOKEN = None


def _db_token():
    global _DB_TOKEN
    if _DB_TOKEN is None:
        from dynamic_credentials import dynamic_credential_entry
        entry = dynamic_credential_entry("custom.turso-radar")
        _DB_TOKEN = entry.get("surrogate") or entry.get("value")
        if not _DB_TOKEN:
            raise RuntimeError("no token in vault entry custom.turso-radar")
    return _DB_TOKEN


def _enc(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def _db_pipeline(stmts):
    reqs = []
    for sql, args in stmts:
        stmt = {"sql": sql}
        if args is not None:
            stmt["args"] = [_enc(a) for a in args]
        reqs.append({"type": "execute", "stmt": stmt})
    body = json.dumps({"requests": reqs}).encode()
    r = subprocess.run(
        ["curl", "-s", "-w", "\nHTTP:%{http_code}", "--max-time", "60",
         "-X", "POST", TURSO_URL,
         "-H", "Authorization: Bearer " + _db_token(),
         "-H", "Content-Type: application/json",
         "-d", body.decode()],
        capture_output=True, text=True,
    )
    out = r.stdout
    http = None
    if "\nHTTP:" in out:
        out, http = out.rsplit("\nHTTP:", 1)
        http = http.strip()
    if http != "200":
        raise RuntimeError(f"Hrana HTTP {http}")
    data = json.loads(out)
    unwrapped = []
    for i, res in enumerate(data.get("results", [])):
        if res.get("type") == "error":
            raise RuntimeError(f"Hrana statement {i} failed")
        resp = res.get("response", {})
        unwrapped.append(resp.get("result", {}) if resp.get("type") == "execute" else resp)
    return unwrapped


def _rows(result):
    cols = [c["name"] for c in result.get("cols", [])]
    out = []
    for row in result.get("rows", []):
        d = {}
        for name, cell in zip(cols, row):
            d[name] = cell.get("value") if isinstance(cell, dict) else None
        out.append(d)
    return out


def db_query(sql, args=None):
    return _rows(_db_pipeline([(sql, args)])[0])


def db_execute(sql, args=None):
    return _db_pipeline([(sql, args)])[0]


# --- Telegram token (lazy, live path only) ---
class BotTokenMissing(Exception):
    pass


def get_bot_token():
    """Called ONLY by send_message() on the live path. Never in dry-run."""
    try:
        from dynamic_credentials import dynamic_credential_entry
        entry = dynamic_credential_entry("custom.radar-telegram")
        tok = entry.get("surrogate") or entry.get("value")
    except Exception:
        tok = None
    if not tok:
        raise BotTokenMissing(
            "Telegram bot token not configured: vault entry "
            "custom.radar-telegram is missing. Live sending is pending "
            "until Septian creates the bot via BotFather and stores its token."
        )
    return tok


def send_message(chat_id, text, dry_run=False):
    """Dry-run prints to stdout and never touches the token or network."""
    if dry_run:
        print(f"[DRY-RUN] to {chat_id}:\n{text}")
        return {"dry_run": True}
    token = get_bot_token()
    payload = json.dumps({
        "chat_id": chat_id, "text": text,
        "disable_web_page_preview": True,
    })
    # curl, NOT urllib: urllib times out to api.telegram.org through this
    # VM's egress proxy (verified 2026-10-25: two 30s timeouts), while
    # curl succeeds in ~2s. Same pattern as _db_pipeline above.
    r = subprocess.run(
        ["curl", "-s", "--max-time", "30",
         f"https://api.telegram.org/bot{token}/sendMessage",
         "-H", "Content-Type: application/json",
         "-d", payload],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(
            f"Telegram send transport failure (curl rc={r.returncode})")
    if not data.get("ok"):
        raise RuntimeError(f"Telegram send error: {data}")
    return data


def tg_api(method, params):
    """Telegram Bot API call via curl (urllib times out via this VM's proxy)."""
    token = get_bot_token()
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://api.telegram.org/bot{token}/{method}"
    if qs:
        url += "?" + qs
    r = subprocess.run(["curl", "-s", "--max-time", "40", url],
                       capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f"Telegram API transport failure ({method})")
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error ({method}): {data}")
    return data


def load_update_state(path):
    try:
        with open(path) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def save_update_state(path, offset, lang_by_chat):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"offset": offset,
                   "lang": {str(k): v for k, v in lang_by_chat.items()}}, f)
    os.replace(tmp, path)


def default_offset_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".bot_updates.json")


# --- Market calendar (same NYSE list as the poller) ---
# 2028 list is the official NYSE Group calendar (announced 2025-12-23):
# 9 closures — New Year's Day 2028 falls on a Saturday and is NOT
# observed. The set must be IDENTICAL in poller.py, bot.py,
# dashboard/logic.py and web/src/lib/format.ts (qa/test_r8_fix.py S11).
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
NYSE_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
}


def is_nyse_day(dt_et):
    return dt_et.weekday() < 5 and dt_et.strftime("%Y-%m-%d") not in NYSE_HOLIDAYS


def is_market_open(now_utc):
    et = now_utc.astimezone(ET)
    if not is_nyse_day(et):
        return False
    return (et.hour, et.minute) >= (9, 30) and (et.hour, et.minute) < (16, 0)


def next_schedule_close_utc(now_utc):
    """00:00 ET at the end of the current open run, as a UTC 'Z' string.

    Mirror of poller.next_schedule_close_utc (same schedule model:
    open all day on NYSE business days, so the window closes at
    midnight ET ending the last NYSE business day before a weekend /
    NYSE holiday). Only meaningful when the schedule status is open;
    callers pass None (not this value) for closed/paused. Pure: no I/O.
    The two copies are locked to agree by qa/test_r7_gap_close_alert.py
    (same pattern as the S11 holiday-set identity guard)."""
    d = now_utc.astimezone(ET).date()
    while is_nyse_day(datetime(d.year, d.month, d.day, tzinfo=ET)):
        d += timedelta(days=1)
    close_et = datetime(d.year, d.month, d.day, 0, 0, tzinfo=ET)
    return close_et.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def closes_within_24h(now_utc, close_utc=None):
    """True iff the derived schedule close is >0h and <=24h away.

    close_utc defaults to next_schedule_close_utc(now_utc). Pure."""
    if close_utc is None:
        close_utc = next_schedule_close_utc(now_utc)
    close = parse_ts(close_utc)
    if close is None:
        return False
    delta_h = (close - now_utc).total_seconds() / 3600.0
    return 0.0 < delta_h <= 24.0


def parse_ts(iso):
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
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


# --- Alert evaluation (pure: data in, alert dicts out) ---
# Live public ticker pages: https://radar.omdanny.site/ticker/<ticker>
TICKER_PAGE_BASE = "https://radar.omdanny.site"
SPREAD_THRESHOLD = 1.0
DEV_HIGH_THRESHOLD = 3.0
# F1 (perp 3-leg, DESAIN §2.2, built 2026-11-13): alert at |dev| >= 1.0%,
# high priority at >= 3.0%.
PERP_DEV_THRESHOLD = 1.0
PERP_DEV_HIGH_THRESHOLD = 3.0
# F1 perp-snapshot freshness gate (<= 15 min). Same 15-min bound as
# TICKER_STALE_MINUTES / the Worker, but a different gate: this is the
# age of the perp snapshot itself, not of the deviations row.
PERP_FRESH_MINUTES = 15.0
# F3 (exit_high, DESAIN §2.4, built 2026-11-13): alert at score >= 70
# on the 0-100 scale. M5 rule: the band — and the alert — only exist
# when >= 3 of the 5 components were present.
EXIT_HIGH_THRESHOLD = 70.0
EXIT_SCORE_MIN_COMPONENTS = 3
PRICE_GUARD_MAX_DEV = 0.25  # poller price-sanity guard: drop prices >25% from median


def guarded_venues(venues):
    """Price-sanity-guarded venue list — the SAME rule as the poller
    guard (poller.py run_cycle, 2026-10-24): with >=3 venues, drop any
    venue whose price deviates >25% from the cross-venue median;
    excluded venues contribute neither price nor depth. With <3 venues
    no consensus exists, so the guard is skipped (same documented
    limitation as the poller). If exclusion would empty the list, fall
    back to all venues. Pure: no I/O.
    Why this exists: the poller applies the guard to dw/deviation
    only — snapshots still store the raw tick, and
    load_live_tickers reads those raw snapshots. Until 2026-11-08
    the spread check used the raw venues, so one bad tick (SPYx
    $0.1044 on 2026-11-06 19:06 UTC, reserve $1.24M) fired a
    100.041% spread alert while the poller had already excluded that
    pool from dw (guard=SPYx:1). From 2026-11-08 (Q6 vote A, 3-0)
    evaluate_alerts runs the spread check on guarded_venues, so a
    guarded-out pool cannot set hi/lo."""
    if len(venues) < 3:
        return list(venues)
    prices = [v["price"] for v in venues]
    med = statistics.median(prices)
    if not med:
        return list(venues)
    kept = [v for v in venues
            if abs(v["price"] - med) / med <= PRICE_GUARD_MAX_DEV]
    return kept if kept else list(venues)


DEPTH_MIN = 250000.0
LIQ_MIN = 100000.0  # qualifying pool: reserve >= $100k (same as poller
# LIQ_MIN and api/worker.js LIQ_MIN). Fix ronde 5 (M2): the spread
# check used to run on ALL active pools regardless of reserve, while
# dw/depth/dev come from the poller, which only uses qualifying pools.
POR_STALE_HOURS = 72.0
DEDUP_HOURS = 24.0
STALE_MINUTES = 30.0
# S2 (fix ronde 8): per-ticker staleness uses the SAME 15-min bound as
# the Worker (TICKER_STALE_MIN) and the dashboard — a ticker 20 min old
# used to be "stale" on the web yet still eligible for bot alerts. The
# 30-min global stale gate above is unchanged; only the per-ticker
# bound aligns. No threshold value changes: 15 and 30 were both already
# decided numbers, on different surfaces.
TICKER_STALE_MINUTES = 15.0
SEND_DELAY_S = 2  # ACC 25 Okt: short pause between alert sends (was back-to-back)


def evaluate_alerts(tickers_data, market_open):
    """tickers_data: list of dicts with keys:
    ticker, issuer, venues [{dex, price, reserve}], dw, dev_med, depth,
    pools_used, median, redemption_status, redemption_note, next_open_at,
    por_age_hours, por_last_update.
    F1 keys (optional): perp_px, perp_px_source, perp_ts, perp_age_min,
    perp_fresh (computed by load_live_tickers).
    F3 keys (optional): exit_score, exit_score_components,
    exit_score_version (from the deviations row).
    Returns list of alert dicts (no I/O, no sends).
    Redemption alerts are PER-TICKER (un-batched 2026-10-25): one
    alert per ticker with status closed/gated (type 'redemption')
    or paused (type 'redemption_paused', a distinct dedup key so a
    closed alert never suppresses a paused alert for the same
    ticker). Other alert types stay per-ticker as before."""
    alerts = []
    for d in tickers_data:
        # M1 (fix ronde 7): a ticker whose own deviations row is stale
        # must not fire spread/deviation alerts on hours-old dw/dev —
        # even when the poller as a whole is healthy. Redemption and
        # PoR alerts below do not depend on the dev row, so they still
        # fire for such a ticker.
        dev_stale = bool(d.get("dev_stale"))
        # Qualifying venues only (fix ronde 5, M2): same population the
        # poller uses for dw/dev (reserve >= LIQ_MIN), then the 25%
        # price-sanity guard. A sub-$100k pool can no longer set hi/lo.
        venues = [v for v in d.get("venues", [])
                  if v.get("price") is not None and v.get("reserve") is not None
                  and v["reserve"] >= LIQ_MIN]
        depth = d.get("depth")
        # Spread is evaluated on price-sanity-guarded venues (see
        # guarded_venues): a pool the poller guard excluded must not
        # set hi/lo. Threshold, depth gate, dedup, stale gate and
        # alert format are unchanged.
        guarded = guarded_venues(venues)
        if not dev_stale and market_open and len(guarded) >= 2 and depth is not None and depth >= DEPTH_MIN:
            prices = [v["price"] for v in guarded]
            dw = d.get("dw")
            if dw:
                spread = (max(prices) - min(prices)) / dw * 100.0
                if spread >= SPREAD_THRESHOLD:
                    hi = max(guarded, key=lambda v: v["price"])
                    lo = min(guarded, key=lambda v: v["price"])
                    alerts.append({
                        "type": "spread", "ticker": d["ticker"],
                        "issuer": d.get("issuer"),
                        "spread_pct": round(spread, 3),
                        "high_venue": hi, "low_venue": lo,
                        "dw": dw, "median": statistics.median(prices),
                        "depth": depth, "pools_used": len(guarded),
                    })
        dev = d.get("dev_med")
        if not dev_stale and dev is not None and abs(dev) >= DEV_HIGH_THRESHOLD:
            alerts.append({
                "type": "deviation_high", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "dev_pct": round(dev, 3),
                "dw": d.get("dw"), "median": d.get("median"),
                "depth": depth, "pools_used": d.get("pools_used"),
            })
        # F1 (perp 3-leg, DESAIN §2.2, built 2026-11-13):
        # dev_perp_vs_token_pct = (perp_px - dw) / dw * 100 — the same
        # formula as api/worker.js perp_dev_pct. Alert at |dev| >= 1.0%,
        # high priority at >= 3.0%. Gates: spot qualifying depth >= $250k,
        # perp snapshot fresh (<= 15 min, precomputed as perp_fresh by
        # load_live_tickers), and the dev row itself fresh (dev_stale
        # suppresses — the dw the deviation is measured against would be
        # hours-old otherwise). No market-open condition: perp trades
        # 24/7, and the weekend is exactly when perp-vs-tokenized
        # divergence matters. No pool-count gate: DESAIN §2.2 states
        # only depth + freshness for F1 (the >= 2-pool rule is for the
        # inter-venue spread alert). Dedup: standard 24h per
        # (ticker, type, channel) via suppression_reason.
        perp_px = d.get("perp_px")
        if (not dev_stale and perp_px is not None and d.get("perp_fresh")
                and d.get("dw") and depth is not None and depth >= DEPTH_MIN):
            perp_dev = (perp_px - d["dw"]) / d["dw"] * 100.0
            if abs(perp_dev) >= PERP_DEV_THRESHOLD:
                alerts.append({
                    "type": "perp_deviation", "ticker": d["ticker"],
                    "issuer": d.get("issuer"), "dev_pct": round(perp_dev, 3),
                    "high_priority": abs(perp_dev) >= PERP_DEV_HIGH_THRESHOLD,
                    "perp_px": perp_px, "perp_px_source": d.get("perp_px_source"),
                    "perp_age_min": d.get("perp_age_min"),
                    "dw": d.get("dw"), "median": d.get("median"),
                    "depth": depth, "pools_used": d.get("pools_used"),
                })
        # F3 (exit_high, DESAIN §2.4, built 2026-11-13): exit_score on
        # the 0-100 scale >= 70, 1x/ticker/24h (standard dedup, same as
        # the other non-redemption types). M5 rule: the band — and the
        # alert — only exist when >= 3 of the 5 components were present;
        # a partial score never fires "high". Live proof 2026-11-13:
        # TSLAB scored 82.0 on 1 component and must NOT alert. dev_stale
        # suppresses: the score rides the dev row, so a stale row's
        # score is hours-old evidence.
        score = d.get("exit_score")
        ncomp = d.get("exit_score_components")
        if (not dev_stale and score is not None and ncomp is not None
                and ncomp >= EXIT_SCORE_MIN_COMPONENTS
                and score >= EXIT_HIGH_THRESHOLD):
            alerts.append({
                "type": "exit_high", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "score": round(float(score), 1),
                "components": ncomp, "version": d.get("exit_score_version"),
                "dev_pct": d.get("dev_med"),
                "dw": d.get("dw"), "median": d.get("median"),
                "depth": depth, "pools_used": d.get("pools_used"),
            })
        # S3 (fix ronde 8): redemption/PoR alerts do not depend on the
        # dev row, so they still fire for a stale ticker — but they
        # must NOT carry its hours-old price/depth as if fresh. When
        # dev_stale, those fields are None and format_alert renders
        # "—" (same "missing renders as —" rule as fix ronde 5, S2).
        stale_price = (None, None, None) if dev_stale else (
            d.get("dw"), depth, d.get("pools_used"))
        status = (d.get("redemption_status") or "").lower()
        if status in ("closed", "gated"):
            alerts.append({
                "type": "redemption", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "status": status,
                "next_open_at": d.get("next_open_at"),
                "closes_within_24h": d.get("closes_within_24h", False),
                "dw": stale_price[0], "depth": stale_price[1],
                "pools_used": stale_price[2],
            })
        elif status == "paused":
            alerts.append({
                "type": "redemption_paused", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "status": status,
                "next_open_at": d.get("next_open_at"),
                "closes_within_24h": d.get("closes_within_24h", False),
                "dw": stale_price[0], "depth": stale_price[1],
                "pools_used": stale_price[2],
            })
        elif status == "open" and d.get("closes_within_24h"):
            # Gap R7 (built 2026-11-09): advance warning while the
            # window is still OPEN and the derived close is <=24h away.
            # Distinct type 'redemption_closing_soon' so its 24h dedup
            # (standard, per-channel — NOT once-per-window) never
            # suppresses the later closed-window 'redemption' alert.
            alerts.append({
                "type": "redemption_closing_soon", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "status": status,
                "next_close_at": d.get("next_close_at"),
                "closes_within_24h": True,
                "dw": stale_price[0], "depth": stale_price[1],
                "pools_used": stale_price[2],
            })
        age = d.get("por_age_hours")
        if age is not None and age > POR_STALE_HOURS:
            alerts.append({
                "type": "por", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "age_hours": round(age, 1),
                "last_update": d.get("por_last_update"),
                "dw": stale_price[0], "depth": stale_price[1],
                "pools_used": stale_price[2],
            })
    # Note: the DB window_note is Indonesian, so it is NOT carried
    # into messages; format_alert uses a fixed language-appropriate
    # sentence per channel instead, so EN never leaks ID text.
    return alerts


# --- Message formatting (§5.6: venue + depth + reference + link + disclaimer) ---
BOT_STR = {
    "en": {
        "spread_head": "🔴 SPREAD — {ticker} ({issuer})",
        "spread_body": ("Highest venue: {hi_dex} ${hi_price:,.2f} · "
                        "Lowest venue: {lo_dex} ${lo_price:,.2f}\n"
                        "Depth-weighted price: {dw_s} · Spread: {spread:.2f}% "
                        "(threshold {thr:.1f}%)\n"
                        "Qualifying depth: {depth_s} across {n_s} pools · "
                        "Reference: cross-venue median {median_s}"),
        "dev_head": "🟠 HIGH DEVIATION — {ticker} ({issuer})",
        "dev_body": ("Depth-weighted price: {dw_s} · "
                    "Deviation vs cross-venue median: {dev:+.2f}% "
                    "(high-priority threshold {thr:.1f}%)\n"
                    "Qualifying depth: {depth_s} across {n_s} pools · "
                    "Reference: cross-venue median {median_s} · "
                    "Note: vs-close is unavailable (data license pending), "
                    "so this alert uses the median basis."),
        "red_head": "🟡 REDEMPTION — {ticker} ({issuer})",
        "red_paused_head": "🔴 REDEMPTION PAUSED — {ticker} ({issuer})",
        "red_body": ("Redemption window: {status}\n"
                    "Next opening: {nxt}\n"
                    "\n"
                    "Price (depth-weighted): {dw_s}\n"
                    "Qualifying depth: {depth_s} across {n_s} pools\n"
                    "\n"
                    "{note}"),
        "red_batch_status_closed": "closed",
        "red_batch_status_gated": "gated",
        "red_batch_within24h": "within 24h",
        "red_batch_note": ("Status derived from the official 24/5 schedule "
                           "and NYSE calendar — not confirmed live by the issuer."),
        "red_batch_paused_priority": ("High priority: on-chain pause detected — "
                                      "redemption is halted regardless of schedule."),
        "red_batch_status_paused": "paused (on-chain)",
        "red_batch_paused_note": ("Pause detected on-chain via the mint pausable "
                                  "flag — not confirmed live by the issuer. "
                                  "Redemption stays halted until the pause is lifted."),
        "red_closing_head": "🟡 REDEMPTION CLOSING SOON — {ticker} ({issuer})",
        "red_closing_body": ("Redemption window closes: {close}\n"
                             "(within 24h — schedule-derived close time)\n"
                             "\n"
                             "Price (depth-weighted): {dw_s}\n"
                             "Qualifying depth: {depth_s} across {n_s} pools\n"
                             "\n"
                             "{note}"),
        "por_head": "🟡 PROOF-OF-RESERVE STALE — {ticker} ({issuer})",
        "por_body": ("PoR feed age: {age:.1f} hours (threshold {thr:.0f}h) · "
                    "Last update: {upd}\n"
                    "Depth-weighted price: {dw_s} · "
                    "Qualifying depth: {depth_s} across {n_s} pools\n"
                    "Reserves freshness for this issuer is not confirmed."),
        "perp_head": "🟠 PERP DEVIATION — {ticker} ({issuer})",
        "perp_head_high": "🔴 PERP DEVIATION — HIGH PRIORITY — {ticker} ({issuer})",
        "perp_body": ("Perp price (Hyperliquid XYZ, {source}): {perp_s} · "
                      "Depth-weighted tokenized price: {dw_s}\n"
                      "Deviation perp vs tokenized: {dev:+.2f}% "
                      "(threshold {thr:.1f}%){high_note}\n"
                      "Qualifying depth: {depth_s} across {n_s} pools · "
                      "Perp snapshot age: {age} (fresh ≤ 15 min)\n"
                      "Note: perp is market data from Hyperliquid XYZ, "
                      "not a trading venue — no order or position."),
        "perp_high_note": " — high priority (≥ 3.0%)",
        "exit_head": "🟠 EXIT SCORE HIGH — {ticker} ({issuer})",
        "exit_body": ("Exit Score: {score:.1f} (band high 70–100; "
                      "{n} of 5 components; {ver})\n"
                      "Depth-weighted price: {dw_s} · "
                      "Deviation vs median: {dev} · "
                      "Qualifying depth: {depth_s} across {n_s} pools\n"
                      "Note: factual reading only — a high score "
                      "describes current conditions."),
        "disclaimer": "Not financial advice. Prices are market data, not recommendations.",
    },
    "id": {
        "spread_head": "🔴 SPREAD — {ticker} ({issuer})",
        "spread_body": ("Venue tertinggi: {hi_dex} ${hi_price:,.2f} · "
                        "Venue terendah: {lo_dex} ${lo_price:,.2f}\n"
                        "Harga tertimbang kedalaman: {dw_s} · Spread: {spread:.2f}% "
                        "(ambang {thr:.1f}%)\n"
                        "Kedalaman lolos: {depth_s} di {n_s} pool · "
                        "Acuan: median lintas-venue {median_s}"),
        "dev_head": "🟠 DEVIASI TINGGI — {ticker} ({issuer})",
        "dev_body": ("Harga tertimbang kedalaman: {dw_s} · "
                    "Deviasi vs median lintas-venue: {dev:+.2f}% "
                    "(ambang prioritas tinggi {thr:.1f}%)\n"
                    "Kedalaman lolos: {depth_s} di {n_s} pool · "
                    "Acuan: median lintas-venue {median_s} · "
                    "Catatan: vs-close belum tersedia (lisensi menunggu), "
                    "jadi alert ini memakai basis median."),
        "red_head": "🟡 REDEMPTION — {ticker} ({issuer})",
        "red_paused_head": "🔴 REDEMPTION DIJEDA — {ticker} ({issuer})",
        "red_body": ("Status jendela redemption: {status}\n"
                    "Pembukaan berikutnya: {nxt}\n"
                    "\n"
                    "Harga (tertimbang kedalaman): {dw_s}\n"
                    "Kedalaman lolos: {depth_s} di {n_s} pool\n"
                    "\n"
                    "{note}"),
        "red_batch_status_closed": "tutup",
        "red_batch_status_gated": "terbatas (KYC)",
        "red_batch_within24h": "dalam 24 jam",
        "red_batch_note": ("Status dihitung dari jadwal resmi 24/5 "
                           "dan kalender NYSE — bukan konfirmasi live dari issuer."),
        "red_batch_paused_priority": ("Prioritas tinggi: jeda on-chain terdeteksi — "
                                      "redemption berhenti apa pun jadwalnya."),
        "red_batch_status_paused": "dijeda (on-chain)",
        "red_batch_paused_note": ("Jeda terdeteksi on-chain lewat flag pausable "
                                  "mint — bukan konfirmasi live dari issuer. "
                                  "Redemption tetap berhenti sampai jeda dicabut."),
        "red_closing_head": "🟡 REDEMPTION SEGERA TUTUP — {ticker} ({issuer})",
        "red_closing_body": ("Jendela redemption tutup: {close}\n"
                             "(dalam 24 jam — waktu tutup turunan jadwal)\n"
                             "\n"
                             "Harga (tertimbang kedalaman): {dw_s}\n"
                             "Kedalaman lolos: {depth_s} di {n_s} pool\n"
                             "\n"
                             "{note}"),
        "por_head": "🟡 PROOF-OF-RESERVE BASI — {ticker} ({issuer})",
        "por_body": ("Umur feed PoR: {age:.1f} jam (ambang {thr:.0f} jam) · "
                    "Pembaruan terakhir: {upd}\n"
                    "Harga tertimbang kedalaman: {dw_s} · "
                    "Kedalaman lolos: {depth_s} di {n_s} pool\n"
                    "Kesegaran cadangan issuer ini tidak terkonfirmasi."),
        "perp_head": "🟠 DEVIASI PERP — {ticker} ({issuer})",
        "perp_head_high": "🔴 DEVIASI PERP — PRIORITAS TINGGI — {ticker} ({issuer})",
        "perp_body": ("Harga perp (Hyperliquid XYZ, {source}): {perp_s} · "
                      "Harga tokenized tertimbang kedalaman: {dw_s}\n"
                      "Deviasi perp vs tokenized: {dev:+.2f}% "
                      "(ambang {thr:.1f}%){high_note}\n"
                      "Kedalaman lolos: {depth_s} di {n_s} pool · "
                      "Umur snapshot perp: {age} (segar ≤ 15 mnt)\n"
                      "Catatan: perp adalah data pasar dari Hyperliquid XYZ, "
                      "bukan tempat trading — tidak ada order atau posisi."),
        "perp_high_note": " — prioritas tinggi (≥ 3,0%)",
        "exit_head": "🟠 SKOR EXIT TINGGI — {ticker} ({issuer})",
        "exit_body": ("Skor Exit: {score:.1f} (band tinggi 70–100; "
                      "{n} dari 5 komponen; {ver})\n"
                      "Harga tertimbang kedalaman: {dw_s} · "
                      "Deviasi vs median: {dev} · "
                      "Kedalaman lolos: {depth_s} di {n_s} pool\n"
                      "Catatan: hanya pembacaan faktual — skor tinggi "
                      "menggambarkan kondisi saat ini."),
        "disclaimer": "Bukan nasihat keuangan. Harga adalah data pasar, bukan rekomendasi.",
    },
}


def _fmt_money(x):
    return f"{float(x):,.2f}"


def _usd(x):
    """'$1,234.56' for a price, '—' when the value is missing (fix ronde 5,
    S2: missing data must never render as $0.00 — 'unavailable' is not zero)."""
    return f"${float(x):,.2f}" if x is not None else "—"


def _usd0(x):
    """'$1,234,567' for a depth, '—' when missing."""
    return f"${float(x):,.0f}" if x is not None else "—"


def _count(x):
    return str(x) if x is not None else "—"


def _signed_pct(x):
    """'+1.23%' for a deviation, '—' when missing (same missing-renders-
    as-— rule as _usd). Used where the value may legitimately be None
    (F3 exit_high carries dev_med only when the dev row has one)."""
    return f"{float(x):+.2f}%" if x is not None else "—"


def _perp_age_txt(age_min):
    """'4.0 min' for a perp snapshot age, '—' when unknown."""
    return f"{float(age_min):.1f} min" if age_min is not None else "—"


# --- WITA rendering for next-opening (alert format, ACC 25 Okt 2026) ---
_DAY_ID = {"Mon": "Sen", "Tue": "Sel", "Wed": "Rab", "Thu": "Kam",
           "Fri": "Jum", "Sat": "Sab", "Sun": "Min"}
_MON_ID = {"Jan": "Jan", "Feb": "Feb", "Mar": "Mar", "Apr": "Apr",
           "May": "Mei", "Jun": "Jun", "Jul": "Jul", "Aug": "Agu",
           "Sep": "Sep", "Oct": "Okt", "Nov": "Nov", "Dec": "Des"}
_WITA = ZoneInfo("Asia/Makassar")


def fmt_next_open(nxt, lang="en"):
    """ISO UTC ('2026-10-26T04:00:00Z') -> 'Mon 26 Oct 2026, 12:00 WITA'
    (ID: 'Sen 26 Okt 2026, 12:00 WITA'). Non-ISO fallbacks pass through."""
    try:
        dt = datetime.fromisoformat(nxt.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return nxt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    s = dt.astimezone(_WITA).strftime("%a %d %b %Y, %H:%M WITA")
    if lang == "id":
        for en, idn in {**_DAY_ID, **_MON_ID}.items():
            s = s.replace(en, idn)
    return s


def format_alert(alert, lang="en"):
    s = BOT_STR.get(lang, BOT_STR["en"])
    link = f"{TICKER_PAGE_BASE}/ticker/{alert['ticker']}"
    if alert["type"] == "spread":
        head = s["spread_head"].format(ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["spread_body"].format(
            hi_dex=alert["high_venue"]["dex"], hi_price=alert["high_venue"]["price"],
            lo_dex=alert["low_venue"]["dex"], lo_price=alert["low_venue"]["price"],
            dw_s=_usd(alert["dw"]), spread=alert["spread_pct"], thr=SPREAD_THRESHOLD,
            depth_s=_usd0(alert["depth"]), n_s=_count(alert["pools_used"]),
            median_s=_usd(alert["median"]))
    elif alert["type"] == "deviation_high":
        head = s["dev_head"].format(ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["dev_body"].format(
            dw_s=_usd(alert["dw"]), dev=alert["dev_pct"], thr=DEV_HIGH_THRESHOLD,
            depth_s=_usd0(alert["depth"]), n_s=_count(alert["pools_used"]),
            median_s=_usd(alert["median"]))
    elif alert["type"] in ("redemption", "redemption_paused"):
        paused = alert["type"] == "redemption_paused"
        head = (s["red_paused_head"] if paused else s["red_head"]).format(
            ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        status_txt = (s["red_batch_status_paused"] if paused
                      else s.get("red_batch_status_" + alert["status"],
                                 alert["status"]))
        note = s["red_batch_paused_note"] if paused else s["red_batch_note"]
        nxt = fmt_next_open(alert.get("next_open_at") or (
            s["red_batch_within24h"] if alert.get("closes_within_24h") else "—"),
            lang)
        body = s["red_body"].format(
            status=status_txt, note=note, nxt=nxt,
            dw_s=_usd(alert.get("dw")), depth_s=_usd0(alert.get("depth")),
            n_s=_count(alert.get("pools_used")))
        if paused:
            body = s["red_batch_paused_priority"] + "\n\n" + body
    elif alert["type"] == "redemption_closing_soon":
        # Gap R7 (built 2026-11-09): advance warning, still open.
        # next_close_at is schedule-derived (see next_schedule_close_utc);
        # the note is the same schedule-derived honesty label as the
        # closed-window alert. Falls back to "within 24h" only when the
        # close instant is missing (never fabricated).
        head = s["red_closing_head"].format(
            ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        close = fmt_next_open(alert.get("next_close_at") or (
            s["red_batch_within24h"] if alert.get("closes_within_24h") else "—"),
            lang)
        body = s["red_closing_body"].format(
            close=close, note=s["red_batch_note"],
            dw_s=_usd(alert.get("dw")), depth_s=_usd0(alert.get("depth")),
            n_s=_count(alert.get("pools_used")))
    elif alert["type"] == "perp_deviation":
        high = bool(alert.get("high_priority"))
        head = (s["perp_head_high"] if high else s["perp_head"]).format(
            ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["perp_body"].format(
            source=alert.get("perp_px_source") or "—",
            perp_s=_usd(alert.get("perp_px")),
            dw_s=_usd(alert.get("dw")), dev=alert["dev_pct"],
            thr=PERP_DEV_THRESHOLD,
            high_note=s["perp_high_note"] if high else "",
            depth_s=_usd0(alert.get("depth")), n_s=_count(alert.get("pools_used")),
            age=_perp_age_txt(alert.get("perp_age_min")))
    elif alert["type"] == "exit_high":
        head = s["exit_head"].format(
            ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["exit_body"].format(
            score=alert["score"], n=_count(alert.get("components")),
            ver=alert.get("version") or "—",
            dw_s=_usd(alert.get("dw")), dev=_signed_pct(alert.get("dev_pct")),
            depth_s=_usd0(alert.get("depth")), n_s=_count(alert.get("pools_used")))
    elif alert["type"] == "por":
        head = s["por_head"].format(ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["por_body"].format(
            age=alert["age_hours"], thr=POR_STALE_HOURS,
            upd=alert.get("last_update") or "—",
            dw_s=_usd(alert.get("dw")), depth_s=_usd0(alert.get("depth")),
            n_s=_count(alert.get("pools_used")))
    else:
        raise ValueError(f"unknown alert type {alert['type']}")
    return f"{head}\n\n{body}\n\n{link}\n\n{s['disclaimer']}"


# --- Commands (pure: text + lang in, reply + lang out) ---
def handle_command(text, lang="en"):
    cmd = (text or "").strip().lower()
    if cmd == "/start":
        return (
            "Radar Tokenized Stocks — deviation & redemption radar.\n"
            "Choose your language / Pilih bahasa:\n"
            "/en — English\n/id — Bahasa Indonesia",
            lang,
        )
    if cmd == "/en":
        return ("Language set to English. Use /help to see commands.", "en")
    if cmd == "/id":
        return ("Bahasa diatur ke Indonesia. Gunakan /help untuk melihat perintah.", "id")
    if cmd == "/donate":
        return (f"{_t(lang, 'donate_title')}\n{_t(lang, 'donate_note')}\nPay link: {DONATE_PAY_URL}", lang)
    if cmd == "/help":
        if lang == "id":
            return ("Perintah: /start (pilih bahasa), /en, /id, /donate, /help.", lang)
        return ("Commands: /start (choose language), /en, /id, /donate, /help.", lang)
    if lang == "id":
        return ("Perintah tidak dikenal. Gunakan /help.", lang)
    return ("Unknown command. Use /help.", lang)


# --- Live data assembly (reads only; no sends, no writes) ---
def _extend_window_rows(issuer, rows):
    """S7 (fix ronde 8): when the fetched history hits the 5000-row
    LIMIT while still inside a window, the true window start is OLDER
    than the oldest returned row. Find it with two bounded queries:
    the most recent row that breaks ANY window, then the first row of
    the current run after it. That row (with its true status) is
    appended as the synthetic oldest row, so window_start_from_rows
    walks to the true start instead of the truncated one. Returns the
    (possibly extended) rows. Best-effort: any error leaves the rows
    unchanged (the old 5000-row bound applies). Limitation: when the
    window predates ALL recorded history there is no breaking row, so
    no true start exists in the data — the oldest returned row stays
    the anchor."""
    if len(rows) < 5000:
        return rows
    try:
        b = db_query(
            "SELECT MAX(observed_at) AS m FROM redemption_windows "
            "WHERE issuer = ? AND status NOT IN ('closed','gated','paused')",
            [issuer])
        boundary = b[0]["m"] if b and b[0].get("m") else None
        if boundary is None:
            return rows
        f = db_query(
            "SELECT status, observed_at FROM redemption_windows "
            "WHERE issuer = ? AND observed_at > ? "
            "ORDER BY observed_at ASC LIMIT 1",
            [issuer, boundary])
        if not f:
            return rows
        first = f[0]
        if first["observed_at"] < rows[-1]["observed_at"]:
            rows = list(rows) + [{
                "status": first["status"],
                "window_note": None, "next_open_at": None,
                "observed_at": first["observed_at"],
            }]
    except Exception as e:
        print(f"WINDOW EXTEND FAILED ({issuer}): {e}")
    return rows


def snapshot_redemption_rows():
    """One redemption_windows snapshot per pass, shared by evaluation
    and dedup (see SINGLE-SNAPSHOT RULE in the module docstring).
    Returns {issuer: [rows DESC by observed_at]}. Sharing one snapshot
    between evaluation and dedup prevents the 2026-10-26 race (eval saw
    'closed' while dedup saw 'no live window'). Precision: this is one
    query PER ISSUER in sequence, not one atomic database snapshot — a
    poller commit between two issuer queries can still split status
    across issuers, and a window can end after the snapshot is read."""
    snap = {}
    for r in db_query("SELECT DISTINCT issuer FROM universe"):
        iss = r["issuer"]
        rows = db_query(
            "SELECT status, window_note, next_open_at, observed_at "
            "FROM redemption_windows WHERE issuer = ? "
            "ORDER BY observed_at DESC LIMIT 5000", [iss])
        snap[iss] = _extend_window_rows(iss, rows)
    return snap


def load_live_tickers(red_rows_by_issuer=None, now_utc=None):
    # now_utc is injectable for tests (gap R7 guard stubs a Friday to
    # prove the close field goes True); live callers leave it None.
    now = now_utc or datetime.now(UTC)
    uni = db_query(
        "SELECT ticker_id, issuer FROM universe ORDER BY tier, ticker_id")
    latest = {}
    # LIMIT 500 capacity note (fix ronde 5, N5): 13 tickers x ~38 cycles
    # (~3.2h at the 5-min cadence) — the newest row per ticker always
    # survives inside the window. Revisit if the universe grows a lot.
    rows = db_query(
        "SELECT ticker_id, ts, depth_weighted_price, dev_vs_median_pct, "
        "qualifying_depth_usd, pools_used, exit_score, exit_score_version, "
        "exit_score_components FROM deviations "
        "ORDER BY ts DESC, id DESC LIMIT 500")
    for r in rows:
        if r["ticker_id"] not in latest:
            latest[r["ticker_id"]] = r
    # F1 (perp 3-leg, built 2026-11-13): latest perp snapshot per ticker,
    # one query (same newest-per-ticker pattern as the deviations rows
    # above). The poller writes one perp_snapshots row per ticker per
    # cycle under the same cycle_ts, so the freshest row is the current
    # cycle's; age is checked per ticker below (perp_fresh).
    perp_latest = {}
    prows = db_query(
        "SELECT ticker_id, ts, perp_px, perp_px_source FROM perp_snapshots "
        "ORDER BY ts DESC LIMIT 200")
    for r in prows:
        if r["ticker_id"] not in perp_latest:
            perp_latest[r["ticker_id"]] = r
    # Snapshot the program-wide rows ONCE before the per-ticker loop.
    # Querying them inside the loop lets a status flip mid-load split
    # one batch: proven 2026-10-25, the first hourly redemption row
    # landed mid-loop, so the first 3 tickers read 'unknown' and missed
    # the first batch while the other 10 read 'closed'.
    # When the caller passes red_rows_by_issuer, that snapshot is
    # reused here AND by dedup, so the whole pass agrees on one status
    # (2026-10-26 race: separate reads straddled a poller commit).
    red_by_issuer = {}
    por_by_issuer = {}
    for iss in {u["issuer"] for u in uni}:
        if red_rows_by_issuer is not None and iss in red_rows_by_issuer:
            red_rows = red_rows_by_issuer[iss]
        else:
            red_rows = db_query(
                "SELECT status, window_note, next_open_at FROM redemption_windows "
                "WHERE issuer = ? ORDER BY observed_at DESC LIMIT 1", [iss])
        red_by_issuer[iss] = red_rows[0] if red_rows else None
        por_rows = db_query(
            "SELECT age_hours, last_update_ts FROM por_feeds "
            "WHERE issuer = ? ORDER BY checked_at DESC LIMIT 1", [iss])
        por_by_issuer[iss] = por_rows[0] if por_rows else None
    out = []
    for u in uni:
        tid = u["ticker_id"]
        d = latest.get(tid) or {}
        # S-new-9 (fix ronde 6): anchor the per-pool snapshots to the
        # SAME cycle ts as the deviations row they are combined with.
        # The old per-pool MAX(ts) let a poller commit landing between
        # the deviations read and the snapshot read mix two cycles
        # (prices from cycle N+1 against dw/dev from cycle N). The
        # poller writes every pool of a cycle under one batch ts, so
        # s.ts = <deviations ts> reads exactly that cycle's pools. When
        # there is no deviations row (no ts to anchor on), fall back to
        # the old per-pool MAX(ts) pattern.
        cycle_ts = d.get("ts")
        if cycle_ts:
            snaps = db_query(
                "SELECT p.dex, s.price_usd, s.reserve_usd FROM pools p "
                "JOIN snapshots s ON s.pool_id = p.pool_id "
                "WHERE p.ticker_id = ? AND p.is_active = 1 "
                "AND s.reserve_usd >= ? "
                "AND s.ts = ?",
                [tid, LIQ_MIN, cycle_ts])
        else:
            snaps = db_query(
                "SELECT p.dex, s.price_usd, s.reserve_usd FROM pools p "
                "JOIN snapshots s ON s.pool_id = p.pool_id "
                "WHERE p.ticker_id = ? AND p.is_active = 1 "
                "AND s.reserve_usd >= ? "
                "AND s.ts = (SELECT MAX(ts) FROM snapshots s2 WHERE s2.pool_id = p.pool_id)",
                [tid, LIQ_MIN])
        venues = [{"dex": s["dex"], "price": s["price_usd"], "reserve": s["reserve_usd"]}
                  for s in snaps
                  if s["price_usd"] is not None and s["reserve_usd"] is not None
                  and s["reserve_usd"] >= LIQ_MIN]
        # Median for the deviation alert (fix ronde 5, S1): the median of
        # the SAME population the poller used for dev_med — qualifying
        # pools after the 25% price-sanity guard — not a re-computed
        # median over raw snapshots. guarded_venues mirrors the poller
        # guard exactly (>=3 venues, >25% from median dropped, <3 = skip).
        guarded = guarded_venues(venues)
        gprices = sorted(v["price"] for v in guarded)
        median = None
        if len(gprices) >= 2:
            m = len(gprices) // 2
            median = gprices[m] if len(gprices) % 2 == 1 else (gprices[m - 1] + gprices[m]) / 2
        red = red_by_issuer.get(u["issuer"])
        por = por_by_issuer.get(u["issuer"])
        # Gap R7 (built 2026-11-09): the live close field. While the
        # schedule status is open, the close instant is derived from
        # the same NYSE calendar (next_schedule_close_utc) and the
        # <=24h flag from it — this is what makes closes_within_24h
        # True on real data, not only in the dry-run scenario. When
        # the status is closed/gated/paused there is no upcoming close
        # to warn about (the closed/paused alert fires instead).
        _red_status = (red["status"] if red else None)
        if _red_status and str(_red_status).lower() == "open":
            _next_close = next_schedule_close_utc(now)
            _closes_soon = closes_within_24h(now, _next_close)
        else:
            _next_close, _closes_soon = None, False
        # S-new-8 (fix ronde 6): PoR age backstop. age_hours is written
        # by the hourly poller job, so if that job fails repeatedly the
        # stored value freezes — possibly below the 72h threshold while
        # last_update_ts is already older than 72h. The effective age
        # is the max of the stored age and the age recomputed live from
        # last_update_ts (which is already loaded, but was unused).
        # This makes the module docstring's "(or last update older than
        # 72h)" true in evaluate_alerts. Same rule as api/worker.js
        # porEffectiveAge and dashboard/logic.py por_effective_age_hours.
        por_age = por["age_hours"] if por else None
        por_last = por["last_update_ts"] if por else None
        if por_last:
            lu = parse_ts(por_last)
            if lu is not None:
                live_age = (datetime.now(UTC) - lu).total_seconds() / 3600.0
                # GG-15 (fix ronde 8, P2-M1 bot half): a FUTURE
                # last_update is not evidence of age 0 — it is ignored,
                # so the stored age stands (or None stays None).
                if live_age >= 0:
                    if por_age is None:
                        por_age = max(0.0, live_age)
                    else:
                        try:
                            por_age = max(float(por_age), live_age)
                        except (TypeError, ValueError):
                            por_age = max(0.0, live_age)
        # M1 (fix ronde 7): per-ticker staleness. The global stale gate
        # (load_health_age_minutes) only knows whether the POLLER is
        # healthy; a ticker whose own deviations row stopped updating
        # while other tickers kept flowing would still be evaluated
        # and alerted on hours-old dw/dev. dev_stale is True when the
        # ticker has no deviations row at all, its ts is unparseable,
        # its ts is in the FUTURE (GG-15, fix ronde 8 — a negative age
        # is not fresh), or its age exceeds TICKER_STALE_MINUTES.
        # S2 (fix ronde 8): the per-ticker bound is 15 min, the same
        # as the Worker's TICKER_STALE_MIN — the old code used the
        # 30-min global gate here, so a 20-min-old ticker was stale on
        # the web yet still alertable by the bot.
        dev_ts = d.get("ts")
        dev_age_min = None
        if dev_ts:
            parsed = parse_ts(dev_ts)
            if parsed is not None:
                dev_age_min = (datetime.now(UTC) - parsed).total_seconds() / 60.0
        dev_stale = (dev_ts is None or dev_age_min is None
                     or dev_age_min < 0 or dev_age_min > TICKER_STALE_MINUTES)
        # F1: perp snapshot freshness (DESAIN §2.2 gate, <= 15 min).
        # Uses the injectable `now` (not datetime.now) so tests can stub
        # it; a future-dated snapshot is not fresh (GG-15 pattern, same
        # as dev_stale above). perp_px None (ticker has no perp) is
        # never fresh — it simply has no perp leg, not a stale one.
        _perp = perp_latest.get(tid) or {}
        _perp_ts = _perp.get("ts")
        _perp_age = None
        if _perp_ts:
            _pp = parse_ts(_perp_ts)
            if _pp is not None:
                _perp_age = (now - _pp).total_seconds() / 60.0
        perp_fresh = (_perp.get("perp_px") is not None and _perp_age is not None
                      and 0 <= _perp_age <= PERP_FRESH_MINUTES)
        # F3: coerce the exit-score fields to numbers. Turso's hrana
        # protocol returns INTEGER columns as STRINGS (REAL columns come
        # back as floats) — the live DB returns exit_score_components
        # as "4", and a bare `>= 3` comparison on it raises TypeError
        # (proven by --evaluate-live 2026-11-13). Same int() pattern as
        # load_health_age_minutes' cycles_ok. Unparseable -> None (the
        # alert simply does not fire, never a crash).
        _exit_score = d.get("exit_score")
        try:
            _exit_score = (float(_exit_score)
                           if _exit_score is not None else None)
        except (TypeError, ValueError):
            _exit_score = None
        _exit_ncomp = d.get("exit_score_components")
        try:
            _exit_ncomp = (int(_exit_ncomp)
                           if _exit_ncomp is not None else None)
        except (TypeError, ValueError):
            _exit_ncomp = None
        out.append({
            "ticker": tid, "issuer": u["issuer"], "venues": venues,
            "dw": d.get("depth_weighted_price"),
            "dev_med": d.get("dev_vs_median_pct"),
            "depth": d.get("qualifying_depth_usd"),
            "pools_used": d.get("pools_used"), "median": median,
            "dev_ts": dev_ts, "dev_age_min": dev_age_min,
            "dev_stale": dev_stale,
            "perp_px": _perp.get("perp_px"),
            "perp_px_source": _perp.get("perp_px_source"),
            "perp_ts": _perp_ts, "perp_age_min": _perp_age,
            "perp_fresh": perp_fresh,
            "exit_score": _exit_score,
            "exit_score_components": _exit_ncomp,
            "exit_score_version": d.get("exit_score_version"),
            "redemption_status": red["status"] if red else None,
            "redemption_note": red["window_note"] if red else None,
            "next_open_at": red["next_open_at"] if red else None,
            "closes_within_24h": _closes_soon,
            "next_close_at": _next_close,
            "por_age_hours": por_age,
            "por_last_update": por_last,
        })
    return out


def load_health_age_minutes(now_utc):
    """Minutes since the last SUCCESSFUL poller cycle (cycles_ok = 1).

    Fix ronde 5 (M1): the old code anchored on the newest poller_health
    row whatever its cycles_ok — and the poller writes a fresh-timestamped
    cycles_ok = 0 row on every failed DexScreener fetch, so during a
    repeated failure the age always read ~0-5 min and the 30-min stale
    gate could never fire. Anchoring on the last success makes the gate
    fire once no successful cycle has landed for 30 minutes.
    Returns None when no successful cycle exists in the last 12 rows
    (callers treat None as stale — no trustworthy data at all).
    Deliberately NOT tripping on a failed streak alone: the 30-minute
    threshold is Septian-decided, and a streak >= 2 trip would silently
    lower it to ~10 min at the 5-min cadence.
    """
    rows = db_query(
        "SELECT cycle_ts, cycles_ok FROM poller_health ORDER BY id DESC LIMIT 12")
    if not rows:
        return None
    for r in rows:
        try:
            ok = int(r.get("cycles_ok") or 0)
        except (TypeError, ValueError):
            ok = 0
        if ok == 1:
            last = parse_ts(r.get("cycle_ts"))
            if last is None:
                return None
            # GG-15 (fix ronde 8, P2-M1 bot half): a last-success
            # timestamp in the FUTURE is not "0 minutes old" — the age
            # is untrustworthy, so this reads as stale (None), exactly
            # like "no successful cycle at all".
            age = (now_utc - last).total_seconds() / 60.0
            if age < 0:
                return None
            return age
    return None


def recent_alert_exists(ticker, alert_type, hours=DEDUP_HOURS, channel=None):
    """True iff an alert for (ticker, alert_type) was logged within the
    last `hours` hours. With channel given (fix ronde 6, S-new-10),
    the check is per-channel: a row counts only if it was recorded
    for THAT channel — or for no channel (channel IS NULL, i.e. rows
    written before the channel column existed, which suppressed every
    channel under the old rule; counting them preserves the old
    behaviour for pre-fix rows instead of re-firing them once per
    channel after the migration).

    NOTE 2026-10-25: the comparison MUST normalize alert_ts through
    datetime(). A raw string comparison against datetime('now', ...)
    ('YYYY-MM-DD HH:MM:SS', space separator) is broken for ISO
    alert_ts ('...T...Z'): 'T' > ' ' makes any alert on the cutoff's
    calendar date count as recent, stretching dedup to ~41h instead
    of 24h. datetime() parses both formats, giving a true window."""
    sql = (
        "SELECT COUNT(*) AS n FROM alert_log WHERE ticker_id = ? "
        "AND alert_type = ? AND datetime(alert_ts) >= datetime('now', ?)")
    args = [ticker, alert_type, f"-{int(hours)} hours"]
    if channel is not None:
        sql += " AND (channel = ? OR channel IS NULL)"
        args.append(channel)
    rows = db_query(sql, args)
    return bool(rows and int(rows[0]["n"]) > 0)


# Redemption dedup rule B (ACC 2026-10-25, Septian's call): once per
# closed window — NOT daily. A redemption alert fires only if no alert
# for the same ticker+type exists since the current closed window began.
REDEMPTION_WINDOW_STATUSES = {
    "redemption": ("closed", "gated"),
    "redemption_paused": ("paused",),
}


def window_start_from_rows(rows, statuses):
    """Pure helper: rows = redemption_windows rows ordered by observed_at
    DESC (dicts with status/observed_at). Returns the observed_at of the
    first row of the current continuous run in `statuses`, or None when
    the latest row is not in `statuses` (no live window of that kind)."""
    if not rows:
        return None
    if str(rows[0]["status"]).lower() not in statuses:
        return None
    start = rows[0]["observed_at"]
    for r in rows[1:]:
        if str(r["status"]).lower() in statuses:
            start = r["observed_at"]
        else:
            break
    return start


def alerted_in_current_window(ticker, alert_type, statuses, red_rows=None,
                              channel=None):
    """True iff an alert for (ticker, alert_type) was already logged since
    the current window (of `statuses`) began. False when no such window
    is live — so the first alert of a new window always fires.
    When red_rows (the pass snapshot) is given, the window is computed
    from it, never re-queried: re-querying here is what let the
    2026-10-26 pass fire on a window that had already opened.
    With channel given (fix ronde 6, S-new-10), the check is
    per-channel (same transition rule as recent_alert_exists: rows
    with channel IS NULL count for every channel)."""
    if red_rows is None:
        issuer_rows = db_query(
            "SELECT issuer FROM universe WHERE ticker_id = ? COLLATE NOCASE",
            [ticker])
        if not issuer_rows:
            return False
        rows = db_query(
            "SELECT status, observed_at FROM redemption_windows "
            "WHERE issuer = ? ORDER BY observed_at DESC LIMIT 5000",
            [issuer_rows[0]["issuer"]])
        rows = _extend_window_rows(issuer_rows[0]["issuer"], rows)
    else:
        rows = red_rows
    start = window_start_from_rows(rows, statuses)
    if start is None:
        return False
    sql = (
        "SELECT COUNT(*) AS n FROM alert_log WHERE ticker_id = ? "
        "AND alert_type = ? AND datetime(alert_ts) >= datetime(?)")
    args = [ticker, alert_type, start]
    if channel is not None:
        sql += " AND (channel = ? OR channel IS NULL)"
        args.append(channel)
    hits = db_query(sql, args)
    return bool(hits and int(hits[0]["n"]) > 0)


# --- Alert-delivery dedup fallback (fix ronde 7, M2) -----------------
# record_alert writes to Turso AFTER the Telegram send. If that write
# fails (Turso outage), the old code had no dedup row at all, so the
# next pass re-sent the same alert — including once-per-window
# redemption alerts, violating rule B. record_alert_safe retries the
# write 3x; if it still fails, the delivery is recorded in a LOCAL
# JSONL marker file next to bot.py, and suppression_reason consults
# that file exactly like alert_log. A marker never expires by itself:
# the 24h / window-start comparisons below bound it, same as the DB.
# Gap R8 P2-G2: when Turso is reachable again, replay_fallback_alerts
# (called at the start of every alert pass) inserts the markers into
# alert_log under WHERE NOT EXISTS, so the deliveries finally appear
# in the Worker /api/alerts feed — and the file is pruned of them.
ALERT_FALLBACK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".alert_sent_fallback.jsonl")


def _fallback_markers():
    """Markers from the local fallback file.

    Returns [] when the file does not exist yet, or None when the file
    cannot be read at all. GG-16 / S9 (fix ronde 8): an unreadable
    file is UNKNOWN, never "empty" — the old code returned [] on any
    OSError, silently lifting suppression exactly when the filesystem
    was broken."""
    try:
        with open(ALERT_FALLBACK_PATH, "r", encoding="utf-8") as f:
            out = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
            return out
    except FileNotFoundError:
        return []
    except OSError as e:
        print(f"ALERT FALLBACK READ FAILED ({ALERT_FALLBACK_PATH}): {e} "
              f"— suppression state UNKNOWN, treating as not suppressed")
        return None


# S6 (fix ronde 8): the fallback file is append-only by design, so it
# is pruned on every append. Non-redemption markers live 48h (the 24h
# dedup + margin); redemption markers live 30 days (a closed window is
# days long; the DB alert_log is the primary record — the fallback
# only matters while Turso writes fail).
_FALLBACK_PRUNE_NONRED_HOURS = 48
_FALLBACK_PRUNE_RED_DAYS = 30


def _prune_fallback_markers(markers, now=None):
    """Drop markers whose suppression window is long past (pure)."""
    now = now or datetime.now(UTC)
    kept = []
    for m in markers:
        ts = parse_ts(m.get("alert_ts"))
        if ts is None:
            continue
        age_h = (now - ts).total_seconds() / 3600.0
        if m.get("type") in REDEMPTION_WINDOW_STATUSES:
            if age_h <= _FALLBACK_PRUNE_RED_DAYS * 24:
                kept.append(m)
        elif age_h <= _FALLBACK_PRUNE_NONRED_HOURS:
            kept.append(m)
    return kept


def _fallback_suppressed(alert, channel, window_start=None):
    """True iff a fallback marker shows this (ticker, type, channel)
    was already delivered: within the last 24h, or (redemption) since
    the current window began. False when the markers cannot be read
    (unknown state — see _fallback_markers); the read failure itself
    is already shouted there."""
    now = datetime.now(UTC)
    markers = _fallback_markers()
    if markers is None:
        return False
    for m in markers:
        if (m.get("ticker") != alert["ticker"]
                or m.get("type") != alert["type"]
                or m.get("channel") != channel):
            continue
        ts = parse_ts(m.get("alert_ts"))
        if ts is None:
            continue
        if window_start is not None:
            start = parse_ts(window_start)
            if start is not None and ts >= start:
                return True
        elif (now - ts).total_seconds() <= DEDUP_HOURS * 3600:
            return True
    return False


def _append_fallback(alert, channel, alert_ts):
    try:
        # S6: prune stale markers before appending, so the file cannot
        # grow without bound. Pruning is best-effort — an unreadable
        # file (markers None) just skips the prune, the append below
        # still tries and reports its own failure.
        markers = _fallback_markers()
        if markers is not None:
            kept = _prune_fallback_markers(markers)
            if len(kept) != len(markers):
                with open(ALERT_FALLBACK_PATH, "w", encoding="utf-8") as f:
                    for m in kept:
                        f.write(json.dumps(m) + "\n")
        with open(ALERT_FALLBACK_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ticker": alert["ticker"], "type": alert["type"],
                "channel": channel, "alert_ts": alert_ts,
            }) + "\n")
        return True
    except OSError as e:
        print(f"ALERT FALLBACK WRITE FAILED: {e}")
        return False


def record_alert_safe(alert, message_text, alert_ts, channel=None):
    """Record a delivery, retrying the Turso write 3x. Returns True
    when the DB row landed. When all retries fail, the delivery is
    recorded in the local fallback file instead (see above) so the
    next pass still suppresses it — a sent alert is NEVER re-sent
    just because its log write failed. Returns False in that case
    (caller still counts the channel as sent: Telegram got it)."""
    last_exc = None
    for attempt in range(3):
        try:
            record_alert(alert, message_text, alert_ts, channel=channel)
            return True
        except Exception as e:
            last_exc = e
            if attempt < 2:
                time.sleep(0.5)
    print(f"ALERT RECORD FAILED after 3 attempts "
          f"({alert['type']} {alert['ticker']} -> {channel}): {last_exc}")
    if _append_fallback(alert, channel, alert_ts):
        return False
    # S9 (fix ronde 8): the delivery is now recorded NOWHERE — say so
    # loudly. The caller still counts the channel as sent (Telegram
    # got it), but the next pass cannot suppress it, so it may re-send.
    print(f"ALERT RECORD LOST ({alert['type']} {alert['ticker']} -> "
          f"{channel}): DB write failed AND fallback file unwritable — "
          f"dedup NOT guaranteed, this alert may re-send next pass.")
    return False


# --- Fallback-file replay (gap R8 P2-G2) -------------------------------
# Deliveries recorded ONLY in the local fallback file (Turso writes
# failed) never appear in the Worker /api/alerts feed, which reads
# alert_log only. When Turso is reachable again, the next alert pass
# replays the file: each marker is inserted into alert_log with the
# SAME (ticker, alert_ts, alert_type, channel) it was delivered with,
# guarded by WHERE NOT EXISTS on that key, so a replay is idempotent
# — running it twice, or replaying after a partial file rewrite,
# can never duplicate a row. The original message text is NOT in the
# marker (only the delivery identity is), so replayed rows carry an
# explicit placeholder instead of a fabricated message.
# Replay NEVER blocks the normal alert pass: it runs at pass start,
# catches everything, and a failed marker simply stays in the file
# for the next pass. Only markers that landed are removed from the
# file (atomic tmp+replace rewrite); malformed markers are kept and
# logged, never silently dropped.
REPLAYED_FALLBACK_MESSAGE = (
    "[replayed from local fallback file — original message text "
    "unavailable; delivery identity (ticker/time/type/channel) "
    "preserved]")

REPLAY_ALERT_SQL = (
    "INSERT INTO alert_log (ticker_id, alert_ts, alert_type, "
    "threshold_pct, dev_at_alert_pct, depth_at_alert_usd, message_text, "
    "outcome, outcome_ts, closed_below_threshold_ts, channel) "
    "SELECT ?, ?, ?, NULL, NULL, NULL, ?, 'pending', NULL, NULL, ? "
    "WHERE NOT EXISTS (SELECT 1 FROM alert_log WHERE ticker_id = ? "
    "AND alert_ts = ? AND alert_type = ? "
    "AND (channel = ? OR (channel IS NULL AND ? IS NULL)))")


def replay_fallback_alerts(db_execute_fn=None):
    """Replay fallback-file markers into alert_log. Returns a dict
    {replayed, failed, kept}: replayed = rows inserted (or already
    present — NOT EXISTS makes a re-run a no-op), failed = markers
    that could not be written (kept in the file), kept = markers left
    in the file afterwards. Never raises.
    """
    try:
        markers = _fallback_markers()
    except Exception as e:
        print(f"ALERT REPLAY ABORTED: fallback read failed: "
              f"{type(e).__name__}: {e}")
        return {"replayed": 0, "failed": 0, "kept": 0}
    if markers is None:
        # Unreadable file = unknown state (GG-16): do not touch it,
        # do not claim anything was replayed.
        print("ALERT REPLAY ABORTED: fallback file unreadable — "
              "suppression state unknown, file left untouched.")
        return {"replayed": 0, "failed": 0, "kept": 0}
    if not markers:
        return {"replayed": 0, "failed": 0, "kept": 0}
    execute = db_execute_fn or db_execute
    replayed, failed, kept_markers = 0, 0, []
    for m in markers:
        ticker = m.get("ticker")
        alert_ts = m.get("alert_ts")
        alert_type = m.get("type")
        channel = m.get("channel")
        if (not ticker or not alert_type or parse_ts(alert_ts) is None):
            print(f"ALERT REPLAY: skipping malformed marker (kept): {m!r}")
            failed += 1
            kept_markers.append(m)
            continue
        args = [ticker, alert_ts, alert_type, REPLAYED_FALLBACK_MESSAGE,
                channel, ticker, alert_ts, alert_type, channel, channel]
        try:
            execute(REPLAY_ALERT_SQL, args)
            replayed += 1
        except Exception as e:
            print(f"ALERT REPLAY FAILED ({alert_type} {ticker} -> "
                  f"{channel}): {type(e).__name__}: {e} — marker kept.")
            failed += 1
            kept_markers.append(m)
    if replayed:
        try:
            tmp = ALERT_FALLBACK_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for m in kept_markers:
                    f.write(json.dumps(m) + "\n")
            os.replace(tmp, ALERT_FALLBACK_PATH)
            print(f"ALERT REPLAY: {replayed} marker(s) replayed into "
                  f"alert_log, {len(kept_markers)} kept in fallback file.")
        except OSError as e:
            # Rows are already in alert_log; the file still holds them,
            # but the next replay is a NOT EXISTS no-op, so no dup risk.
            print(f"ALERT REPLAY: {replayed} row(s) landed but fallback "
                  f"file could not be pruned ({e}) — next replay is a "
                  f"no-op by dedup key, no duplicates possible.")
            kept_markers = markers
    elif failed:
        print(f"ALERT REPLAY: 0 replayed, {failed} marker(s) kept — "
              f"fallback file untouched, normal pass continues.")
    return {"replayed": replayed, "failed": failed,
            "kept": len(kept_markers)}


def suppression_reason(alert, red_rows_by_issuer=None, channel=None):
    """None when the alert may fire, else a short reason string.
    Redemption types use the once-per-window rule; all other types use
    the true 24h dedup. When the pass snapshot is given, dedup uses it
    (the same rows evaluation used) instead of re-querying.
    With channel given (fix ronde 6, S-new-10), the check is
    per-channel: an alert already sent to the EN channel does not
    suppress the ID channel (and vice versa).
    M2 (fix ronde 7): the local fallback file is consulted too, so a
    delivery whose Turso record failed still suppresses the next pass.
    S8 (fix ronde 7): the channel key is "lang:chat_id", not the bare
    language — replacing a destination mid-dedup-period no longer
    suppresses delivery to the new chat. (One-time transition cost:
    rows recorded under the old bare-language key do not suppress the
    new composite key, so an alert may fire once per channel right
    after this upgrade; legacy NULL rows still suppress everything.)"""
    statuses = REDEMPTION_WINDOW_STATUSES.get(alert["type"])
    if statuses is not None:
        rows = None
        if red_rows_by_issuer is not None:
            rows = red_rows_by_issuer.get(alert.get("issuer"))
        if channel is not None:
            if rows is not None:
                start = window_start_from_rows(rows, statuses)
            else:
                start = None
                try:
                    issuer_rows = db_query(
                        "SELECT issuer FROM universe WHERE ticker_id = ? COLLATE NOCASE",
                        [alert["ticker"]])
                    if issuer_rows:
                        wrows = db_query(
                            "SELECT status, observed_at FROM redemption_windows "
                            "WHERE issuer = ? ORDER BY observed_at DESC LIMIT 5000",
                            [issuer_rows[0]["issuer"]])
                        start = window_start_from_rows(wrows, statuses)
                except Exception:
                    start = None
            if start is not None and _fallback_suppressed(alert, channel, start):
                return "same window"
        if alerted_in_current_window(alert["ticker"], alert["type"], statuses, rows,
                                     channel=channel):
            return "same window"
        return None
    if channel is not None and _fallback_suppressed(alert, channel):
        return "dedup 24h"
    if recent_alert_exists(alert["ticker"], alert["type"], channel=channel):
        return "dedup 24h"
    return None


def record_alert(alert, message_text, alert_ts, channel=None):
    """One alert_log row per (alert, channel) delivery (fix ronde 6,
    S-new-10): the channel that received the alert is recorded, so a
    failed channel is not suppressed by another channel's success.
    channel=None keeps the old call shape (tests / callers that do not
    pass a channel); such rows count as suppressing every channel
    (see recent_alert_exists) until the migration backfills nothing —
    new live sends always pass their channel."""
    # Observed value at alert time, in both columns (the existing
    # convention: threshold_pct/dev_at_alert_pct carry the observed
    # value, not the threshold constant — the F5 accuracy audit reads
    # dev_at_alert_pct). F1 perp_deviation records dev_pct; F3
    # exit_high records the score (0-100 scale).
    _obs = (alert.get("spread_pct") if alert["type"] == "spread"
            else alert.get("dev_pct") if alert["type"] in (
                "deviation_high", "perp_deviation")
            else alert.get("score") if alert["type"] == "exit_high"
            else None)
    db_execute(
        "INSERT INTO alert_log (ticker_id, alert_ts, alert_type, threshold_pct, "
        "dev_at_alert_pct, depth_at_alert_usd, message_text, outcome, "
        "outcome_ts, closed_below_threshold_ts, channel) VALUES (?,?,?,?,?,?,?,'pending',NULL,NULL,?)",
        [alert["ticker"], alert_ts, alert["type"],
         _obs, _obs,
         alert.get("depth"), message_text, channel],
    )


def alert_channels():
    """(lang, chat_id) pairs for broadcast alerts.

    Two slots (EN + ID channels, fixed language per channel):
    RADAR_ALERT_CHAT_ID_EN, RADAR_ALERT_CHAT_ID_ID. The legacy single
    RADAR_ALERT_CHAT_ID still works as the EN channel when the new
    vars are absent, so an old invocation keeps working.
    """
    channels = []
    en = os.environ.get("RADAR_ALERT_CHAT_ID_EN") or os.environ.get("RADAR_ALERT_CHAT_ID")
    idn = os.environ.get("RADAR_ALERT_CHAT_ID_ID")
    if en:
        channels.append(("en", en))
    if idn:
        channels.append(("id", idn))
    return channels


# --- Admin destination for a troubled poller (gap R8 P1-G2) -----------
# The stale gate (no successful poller cycle for > 30 min) used to be
# logged only: there was no configured destination for an ops alert,
# and the public EN/ID channels must never receive ops noise. One new
# env var, RADAR_ADMIN_CHAT_ID (a Telegram chat id, e.g. Septian's own
# chat with the bot, or a private ops group): when set, the bot sends
# at most ONE "poller troubled" message per hour while the gate is
# tripped; when unset, the condition is logged only, exactly as before.
# The cooldown state lives in a small JSON file next to bot.py (same
# pattern as .bot_updates.json); a missing/corrupt state file means
# "never notified", never a crash. Sending to the admin never blocks
# or changes the market-alert pass: a send failure is logged and the
# state is left untouched, so the next pass retries.
ADMIN_CHAT_ID_ENV = "RADAR_ADMIN_CHAT_ID"
ADMIN_POLLER_ALERT_COOLDOWN_MINUTES = 60

ADMIN_ALERT_STATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".admin_poller_alert.json")


def admin_chat_id():
    """Configured admin destination, or None when not configured."""
    v = os.environ.get(ADMIN_CHAT_ID_ENV)
    return v.strip() if v and v.strip() else None


def _load_admin_alert_state(state_path=None):
    path = state_path or ADMIN_ALERT_STATE_PATH
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        if isinstance(state, dict):
            return state
    except (OSError, ValueError):
        pass
    return {}


def _save_admin_alert_state(state, state_path=None):
    path = state_path or ADMIN_ALERT_STATE_PATH
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
        return True
    except OSError as e:
        print(f"ADMIN ALERT STATE WRITE FAILED ({path}): {e}")
        return False


def notify_admin_poller_troubled(age_minutes, now=None, state_path=None,
                                 sender=None):
    """Send the ops alert for a tripped stale gate, at most once per
    ADMIN_POLLER_ALERT_COOLDOWN_MINUTES. Returns True only when a
    message was actually sent. `age_minutes` may be None (no successful
    cycle ever). `sender` defaults to send_message; tests inject a fake.
    Never raises: every failure mode logs and returns False.
    """
    now = now or datetime.now(UTC)
    chat_id = admin_chat_id()
    if not chat_id:
        print("POLLER TROUBLED (no admin destination configured — "
              "logged only; set RADAR_ADMIN_CHAT_ID to receive ops alerts).")
        return False
    try:
        state = _load_admin_alert_state(state_path)
        last = parse_ts(state.get("last_poller_troubled_at"))
        if last is not None:
            since_min = (now - last).total_seconds() / 60.0
            # GG-31 (fix ronde 9): a FUTURE-dated state stamp never
            # suppresses the alert — only a real elapsed time inside
            # the cooldown does. A negative since_min means the state
            # is untrustworthy, not "just notified".
            if 0 <= since_min < ADMIN_POLLER_ALERT_COOLDOWN_MINUTES:
                print(f"POLLER TROUBLED (admin already notified "
                      f"{since_min:.0f} min ago — throttled).")
                return False
        age_txt = (f"{age_minutes:.0f} min" if age_minutes is not None
                   else "never")
        text = (
            "⚠️ RADAR POLLER TROUBLED — last successful cycle "
            f"{age_txt} ago (stale gate > 30 min). No market alerts are "
            "being sent until fresh data returns. Check the poller/cron."
        )
        send = sender or send_message
        send(chat_id, text)
        # GG-32 (fix ronde 9, P2-2): the state-write return value was
        # ignored — a failed write silently voided the "max 1/hour"
        # promise (the next pass would resend). A failure is now
        # shouted: the throttle may not hold after a restart.
        state_saved = _save_admin_alert_state(
            {"last_poller_troubled_at":
             now.strftime("%Y-%m-%dT%H:%M:%SZ")}, state_path)
        if not state_saved:
            print("POLLER TROUBLED admin alert sent, BUT the throttle "
                  "state could NOT be saved — the 1/hour throttle may "
                  "not hold after a restart; the next pass may resend.")
        print(f"POLLER TROUBLED alert sent to admin ({chat_id}).")
        return True
    except Exception as e:
        print(f"POLLER TROUBLED admin alert failed: "
              f"{type(e).__name__}: {e}")
        return False


# --- Dry-run scenarios (synthetic inputs, clearly labeled) ---
def dry_run_scenarios():
    spread_data = {
        "ticker": "TSLAx", "issuer": "xStocks",
        "venues": [
            {"dex": "raydium", "price": 371.16, "reserve": 2380000.0},
            {"dex": "orca", "price": 374.90, "reserve": 500000.0},
        ],
        "dw": 371.81, "dev_med": 0.35, "depth": 2880000.0,
        "pools_used": 2, "median": 373.03,
        "redemption_status": "open", "por_age_hours": 6.0,
    }
    red_data = {
        "ticker": "SPYx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 500.10, "reserve": 3000000.0}],
        "dw": 500.10, "dev_med": 0.10, "depth": 3000000.0,
        "pools_used": 1, "median": 500.10,
        "redemption_status": "closed",
        "redemption_note": "Window closes within 24h (synthetic scenario).",
        "next_open_at": None, "closes_within_24h": True,
        "por_age_hours": 6.0,
    }
    closing_data = {
        "ticker": "NVDAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 180.50, "reserve": 4000000.0}],
        "dw": 180.50, "dev_med": 0.20, "depth": 4000000.0,
        "pools_used": 1, "median": 180.50,
        "redemption_status": "open",
        "next_open_at": None, "closes_within_24h": True,
        "next_close_at": "2026-11-07T05:00:00Z",
        "por_age_hours": 6.0,
    }
    por_data = {
        "ticker": "NVDAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 180.50, "reserve": 4000000.0}],
        "dw": 180.50, "dev_med": 0.20, "depth": 4000000.0,
        "pools_used": 1, "median": 180.50,
        "redemption_status": "open", "por_age_hours": 96.0,
        "por_last_update": "2026-10-20T11:00:00Z",
    }
    # F1 (built 2026-11-13): perp +1.80% vs tokenized, fresh snapshot,
    # market closed (perp trades 24/7, so this fires any time).
    perp_data = {
        "ticker": "TSLAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 400.10, "reserve": 3000000.0}],
        "dw": 400.16, "dev_med": 0.10, "depth": 3000000.0,
        "pools_used": 2, "median": 400.13,
        "redemption_status": "open", "por_age_hours": 6.0,
        "perp_px": 407.36, "perp_px_source": "mark",
        "perp_ts": "2026-11-13T02:20:00Z", "perp_age_min": 4.0,
        "perp_fresh": True,
    }
    # F3 (built 2026-11-13): Exit Score 74.5 on 4/5 components — full
    # enough to band (and alert) as high.
    exit_data = {
        "ticker": "CRCLx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 63.78, "reserve": 5000000.0}],
        "dw": 63.78, "dev_med": 2.10, "depth": 4800000.0,
        "pools_used": 3, "median": 63.80,
        "redemption_status": "open", "por_age_hours": 6.0,
        "exit_score": 74.5, "exit_score_components": 4,
        "exit_score_version": "exit_score_v2",
    }
    scenarios = [
        ("spread (market open)", [spread_data], True),
        ("redemption <=24h (synthetic)", [red_data], False),
        ("redemption closing within 24h (schedule-derived)", [closing_data], False),
        ("PoR stale >72h (synthetic)", [por_data], False),
        ("perp deviation +1.80% (synthetic)", [perp_data], False),
        ("exit score high 74.5, 4/5 components (synthetic)", [exit_data], False),
    ]
    for name, data, mopen in scenarios:
        alerts = evaluate_alerts(data, mopen)
        print(f"=== scenario: {name} ===")
        for a in alerts:
            print(format_alert(a, "en"))
            print("---")
        if not alerts:
            print("(no alert fired — check scenario inputs)")
        print()


# --- Alert delivery (live paths share this) ---
def data_still_fresh():
    """Re-check the 30-min stale gate at send time (fix ronde 6,
    S-new-5): the gate used to be checked only once at pass start,
    so a pass that began fresh could keep sending for up to ~52s
    past the boundary (13 alerts x 2 channels x 2s). Callers re-check
    before each alert; the residual drift is then at most one alert's
    own sends (~4s on the --once path, ~0s on --live, which has no
    inter-send delay). One extra poller_health read per alert."""
    age = load_health_age_minutes(datetime.now(UTC))
    return age is not None and age <= STALE_MINUTES


def send_alert_channels(alert, channels, red_snapshot, now, delay_s=0):
    """Send one alert to every channel that has not already received
    it, and record one alert_log row PER CHANNEL that was sent to
    (fix ronde 6, S-new-10). Returns the number of channels sent to.

    The old code recorded a single row when ANY channel succeeded, so
    a channel whose send failed was still dedup-suppressed for 24h
    (or the whole redemption window) and never got the alert. Now a
    failed channel is simply not recorded, so the next pass retries
    that channel only; a channel that already has a row is skipped
    (per-channel suppression_reason), never re-sent.

    Fix ronde 7:
    - M2: the record goes through record_alert_safe (3 retries, then
      a local fallback marker) — a successful send is never re-sent
      just because its Turso log write failed.
    - S2: the 30-min stale gate is re-checked before EACH channel
      send, not once per alert: the residual drift is now at most one
      send (~2 s + one Telegram round-trip), not one alert's two sends.
    - S5: the recorded alert_ts is ONE shared timestamp per alert
      EVENT (S1, fix ronde 8 — the first channel's delivery time,
      shared by every channel), not a per-channel delivery time.
      The old bullet claimed a per-channel delivery time, which
      contradicted S1; the 24h dedup period is shortened by at most
      the inter-channel delay (~2 s), negligible against 24h / a
      redemption window, and a redemption alert can no longer be
      recorded with a timestamp before its own window's first
      observation.
    - S8: the dedup key is "lang:chat_id", not the bare language, so
      replacing a destination mid-period does not suppress the new one.
    """
    sent = 0
    # S1 (fix ronde 8): ONE alert_ts per alert EVENT, shared by every
    # channel. The old code captured the delivery time per channel, so
    # on the --once cron path (2 s between sends) the EN and ID rows
    # were >= 2 s apart and never grouped under the /api/alerts dedup
    # key (ticker, alert_ts, alert_type) — one event consumed 2 of the
    # 30 feed slots. The shared ts is the FIRST channel's delivery
    # time (still a delivery time, per S5); the dedup period is
    # shortened by at most the inter-channel delay (~2 s), negligible
    # against 24h / a redemption window.
    shared_ts = None
    for lang, cid in channels:
        channel_key = f"{lang}:{cid}"
        if suppression_reason(alert, red_snapshot, channel=channel_key):
            print(f"ALERT already sent to {lang} channel, skipping: "
                  f"{alert['type']} {alert['ticker']}")
            continue
        # S2: re-check the stale gate before each channel send.
        if not data_still_fresh():
            print("STALE GATE (re-check): data went stale mid-alert — "
                  "stopping remaining channel sends.")
            break
        try:
            send_message(cid, format_alert(alert, lang))
            if shared_ts is None:
                shared_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            # GG-32 (fix ronde 9): the record result was ignored — a
            # False means the row did NOT land in alert_log (it is in
            # the fallback file at best, lost at worst). The channel
            # still counts as sent (Telegram got it, per the
            # record_alert_safe contract), but the feed will only show
            # it after the fallback replay, and a LOST record may
            # re-send next pass — say so instead of staying silent.
            recorded = record_alert_safe(alert, format_alert(alert, "en"), shared_ts,
                                         channel=channel_key)
            if not recorded:
                print(f"ALERT sent but NOT recorded in alert_log "
                      f"({lang}): {alert['type']} {alert['ticker']} — "
                      f"feed shows it only after fallback replay.")
            sent += 1
            print(f"ALERT sent ({lang}): {alert['type']} {alert['ticker']}")
        except Exception as e:
            print(f"ALERT send failed ({lang}): "
                  f"{alert['type']} {alert['ticker']}: {e}")
        if delay_s:
            time.sleep(delay_s)
    return sent


# --- Single-pass lock (fix ronde 7, S3) -------------------------------
# Two overlapping bot passes (--once overlapping --live, or two --once
# runs from a hung cron) can both observe "no prior row" and both
# send the same alert. The poller's flock does not cover the bot.
# One exclusive non-blocking flock on a lock file next to bot.py
# serializes alert passes: a pass that cannot take the lock skips
# its alert evaluation entirely (commands/replies are unaffected —
# the lock only wraps the alert pass). The lock is held only for the
# duration of one pass (~1 min); a stale lock file left by a killed
# process is harmless because flock releases on process exit.
ALERT_LOCK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".bot_alert.lock")


class AlertLockError(Exception):
    """The alert lock file cannot be opened at all (permissions,
    filesystem, read-only mount). Distinct from lock CONTENTION
    (another pass holds the flock), which still returns None."""


def acquire_alert_lock():
    """Return an open lock-file handle holding an exclusive flock, or
    None when another alert pass already holds it.

    GG-16 / M4 (fix ronde 8): an open() failure used to return None —
    exactly like contention — so ANY filesystem failure silently
    disabled ALL alerting while every log line blamed a phantom
    overlapping pass and --once exited 0. An open failure now RAISES
    AlertLockError; only flock contention returns None."""
    try:
        fh = open(ALERT_LOCK_PATH, "w")
    except OSError as e:
        raise AlertLockError(
            f"cannot open alert lock file {ALERT_LOCK_PATH}: {e}")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        try:
            fh.close()
        except Exception:
            pass
        return None


def release_alert_lock(fh):
    if fh is None:
        return
    try:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--evaluate-live", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--once", action="store_true",
                    help="one alert pass for cron: drain commands, then "
                    "evaluate + send once, then exit")
    ap.add_argument("--offset-file", default=None,
                    help="getUpdates offset state file "
                    "(default: .bot_updates.json next to bot.py)")
    args = ap.parse_args()
    if args.dry_run:
        dry_run_scenarios()
        return 0
    if args.evaluate_live:
        now = datetime.now(UTC)
        age = load_health_age_minutes(now)
        print(f"health age minutes: {age}")
        if age is None or age > STALE_MINUTES:
            print("STALE GATE: data older than 30 min — no alerts would be sent.")
            return 0
        red_snapshot = snapshot_redemption_rows()
        tickers = load_live_tickers(red_snapshot)
        alerts = evaluate_alerts(tickers, is_market_open(now))
        print(f"market open (ET): {is_market_open(now)}")
        print(f"alerts that would fire: {len(alerts)}")
        for a in alerts:
            reason = suppression_reason(a, red_snapshot)
            print(f"--- {a['type']} {a['ticker']} (suppressed: {reason}) ---")
            if not reason:
                print(format_alert(a, "en"))
        return 0
    if args.once:
        offset_path = args.offset_file or default_offset_path()
        state = load_update_state(offset_path)
        offset = state.get("offset")
        lang_by_chat = {int(k): v for k, v in
                         (state.get("lang") or {}).items()
                         if str(k).lstrip("-").isdigit()}
        # 1) Drain queued commands (replies work even on stale data).
        try:
            params = {"timeout": 10}
            if offset:
                params["offset"] = offset
            data = tg_api("getUpdates", params)
            for upd in data.get("result", []):
                uid = upd["update_id"]
                msg = upd.get("message") or {}
                chat_id = (msg.get("chat") or {}).get("id")
                text = msg.get("text") or ""
                if not chat_id or not text.startswith("/"):
                    # Nothing to reply to — consume it.
                    offset = uid + 1
                    continue
                reply, new_lang = handle_command(
                    text, lang_by_chat.get(chat_id, "en"))
                lang_by_chat[chat_id] = new_lang
                try:
                    send_message(chat_id, reply)
                    print(f"command reply sent to {chat_id}: {text}")
                except Exception as e:
                    # S4 (fix ronde 8): a failed reply is NOT consumed.
                    # The offset stays at this update, so the next poll
                    # retries it; the rest of the batch is deferred, not
                    # lost — their ids are above the saved offset.
                    print(f"command reply failed ({chat_id}): {e} "
                          f"— stopping batch, will retry next poll.")
                    break
                offset = uid + 1
        except Exception as e:
            print(f"updates error: {type(e).__name__}: {e}")
        save_update_state(offset_path, offset, lang_by_chat)
        # 2) One alert pass (same gates as the live loop).
        # S3 (fix ronde 7): take the single-pass lock first — an
        # overlapping pass skips its alert evaluation entirely instead
        # of double-sending. The lock is released even on error.
        # M4 (fix ronde 8): a lock-file OPEN failure is not contention
        # — abort the pass with a nonzero exit (fail-closed), never 0.
        try:
            lock = acquire_alert_lock()
        except AlertLockError as e:
            print(f"ALERT LOCK ERROR: {e} — aborting pass (fail-closed).")
            return 2
        if lock is None:
            print("ALERT LOCK: another alert pass is running — skipping this pass.")
            return 0
        now = datetime.now(UTC)
        try:
            # Gap R8 P2-G2: replay fallback-file deliveries into
            # alert_log now that Turso may be reachable again. Best
            # effort — it never raises and never blocks the pass.
            replay_fallback_alerts()
            age = load_health_age_minutes(now)
            if age is None or age > STALE_MINUTES:
                # Gap R8 P1-G2: the stale gate trips — tell the admin
                # (once/hour max) instead of only logging it.
                # GG-32 (fix ronde 9): the return value is captured —
                # False means no message went out (no destination,
                # throttled, or failed); the outcome is already logged
                # inside, and the pass continues regardless.
                admin_notified = notify_admin_poller_troubled(age, now=now)
                print("STALE GATE: skipping alert evaluation (no fresh data).")
                return 0
            red_snapshot = snapshot_redemption_rows()
            tickers = load_live_tickers(red_snapshot)
            channels = alert_channels()
            sent = 0
            for a in evaluate_alerts(tickers, is_market_open(now)):
                if not channels:
                    print(f"ALERT (no channel configured, not sent): "
                          f"{a['type']} {a['ticker']}")
                    continue
                # S-new-5 (fix ronde 6): re-check the stale gate before
                # each alert — the pass-start check alone lets sends
                # continue up to ~52s past the 30-min boundary.
                if not data_still_fresh():
                    print("STALE GATE (re-check): data went stale "
                          "mid-pass — stopping sends.")
                    break
                if send_alert_channels(a, channels, red_snapshot, now,
                                       delay_s=SEND_DELAY_S):
                    sent += 1
            print(f"once done: alerts sent: {sent}")
        except Exception as e:
            print(f"evaluation error: {type(e).__name__}: {e}")
        finally:
            release_alert_lock(lock)
        return 0
    if args.live:
        # Fail fast when the bot token is missing — never loop blind.
        try:
            get_bot_token()
        except BotTokenMissing as e:
            print(f"Cannot start live bot: {e}")
            return 2
        print("Live bot polling started (Ctrl-C to stop).")
        lang_by_chat = {}
        offset = None
        last_eval = 0.0
        while True:
            now = datetime.now(UTC)
            if time.time() - last_eval >= 300:
                last_eval = time.time()
                # S3 (fix ronde 7): single-pass lock (see --once).
                # M4 (fix ronde 8): an open failure is not contention —
                # log it loudly and skip this evaluation round; the
                # command loop below keeps running.
                lock_error = False
                try:
                    lock = acquire_alert_lock()
                except AlertLockError as e:
                    print(f"ALERT LOCK ERROR: {e} — skipping this evaluation.")
                    lock = None
                    lock_error = True
                if lock is None and not lock_error:
                    print("ALERT LOCK: another alert pass is running — "
                          "skipping this evaluation.")
                if lock is not None:
                    # Gap R8 P2-G2: best-effort fallback replay at the
                    # start of every evaluation round that holds the
                    # lock (fresh or stale — surfacing past deliveries
                    # does not depend on current freshness). Never
                    # raises, never blocks the round.
                    replay_fallback_alerts()
                try:
                    if lock is None:
                        pass
                    elif (age := load_health_age_minutes(now)) is None or age > STALE_MINUTES:
                        # Gap R8 P1-G2: the stale gate trips — tell the
                        # admin (once/hour max) instead of only logging.
                        # GG-32 (fix ronde 9): return value captured —
                        # see the --once path above.
                        admin_notified = notify_admin_poller_troubled(age, now=now)
                        print("STALE GATE: skipping alert evaluation (no fresh data).")
                    else:
                        red_snapshot = snapshot_redemption_rows()
                        tickers = load_live_tickers(red_snapshot)
                        channels = alert_channels()
                        for a in evaluate_alerts(tickers, is_market_open(now)):
                            if not channels:
                                # No alert channel configured yet: log only.
                                # Nothing is recorded in alert_log for an
                                # alert that was never sent.
                                print(f"ALERT (no channel configured, not sent): "
                                      f"{a['type']} {a['ticker']}")
                                continue
                            # S-new-5 (fix ronde 6): re-check the stale
                            # gate before each alert (see --once).
                            if not data_still_fresh():
                                print("STALE GATE (re-check): data went "
                                      "stale mid-pass — stopping sends.")
                                break
                            send_alert_channels(a, channels, red_snapshot,
                                                now)
                except Exception as e:
                    print(f"evaluation error: {type(e).__name__}: {e}")
                finally:
                    release_alert_lock(lock)
            # Long-poll updates (30s) for commands.
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset
                data = tg_api("getUpdates", params)
                for upd in data.get("result", []):
                    uid = upd["update_id"]
                    msg = upd.get("message") or {}
                    chat_id = (msg.get("chat") or {}).get("id")
                    text = msg.get("text") or ""
                    if not chat_id or not text.startswith("/"):
                        offset = uid + 1
                        continue
                    reply, new_lang = handle_command(
                        text, lang_by_chat.get(chat_id, "en"))
                    lang_by_chat[chat_id] = new_lang
                    try:
                        send_message(chat_id, reply)
                    except Exception as e:
                        # S4 (fix ronde 8): same rule as --once — a
                        # failed reply is not consumed; the next poll
                        # retries from this update_id.
                        print(f"command reply failed ({chat_id}): {e} "
                              f"— stopping batch, will retry next poll.")
                        offset = uid
                        break
                    offset = uid + 1
            except Exception as e:
                print(f"poll error: {type(e).__name__}")
                time.sleep(5)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
