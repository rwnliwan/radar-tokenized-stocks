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
  ADAPTATION: the schema has no close-time column, so
  the design's "closing within <=24h" rule cannot be computed live
  yet; it needs a future next_close_at column. The dry-run scenario
  demonstrates the intended <=24h message format with synthetic data.
- PoR: latest feed age > 72h (or last update older than 72h).
- Stale data gate (design §7.1): when the last successful poller
  cycle is older than 30 minutes, NO new alerts are sent (an admin
  "poller troubled" alert needs a configured admin destination,
  which does not exist yet — the condition is logged, not sent).

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
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
NYSE_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def is_nyse_day(dt_et):
    return dt_et.weekday() < 5 and dt_et.strftime("%Y-%m-%d") not in NYSE_HOLIDAYS


def is_market_open(now_utc):
    et = now_utc.astimezone(ET)
    if not is_nyse_day(et):
        return False
    return (et.hour, et.minute) >= (9, 30) and (et.hour, et.minute) < (16, 0)


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
SEND_DELAY_S = 2  # ACC 25 Okt: short pause between alert sends (was back-to-back)


def evaluate_alerts(tickers_data, market_open):
    """tickers_data: list of dicts with keys:
    ticker, issuer, venues [{dex, price, reserve}], dw, dev_med, depth,
    pools_used, median, redemption_status, redemption_note, next_open_at,
    por_age_hours, por_last_update.
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
        status = (d.get("redemption_status") or "").lower()
        if status in ("closed", "gated"):
            alerts.append({
                "type": "redemption", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "status": status,
                "next_open_at": d.get("next_open_at"),
                "closes_within_24h": d.get("closes_within_24h", False),
                "dw": d.get("dw"), "depth": depth,
                "pools_used": d.get("pools_used"),
            })
        elif status == "paused":
            alerts.append({
                "type": "redemption_paused", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "status": status,
                "next_open_at": d.get("next_open_at"),
                "closes_within_24h": d.get("closes_within_24h", False),
                "dw": d.get("dw"), "depth": depth,
                "pools_used": d.get("pools_used"),
            })
        age = d.get("por_age_hours")
        if age is not None and age > POR_STALE_HOURS:
            alerts.append({
                "type": "por", "ticker": d["ticker"],
                "issuer": d.get("issuer"), "age_hours": round(age, 1),
                "last_update": d.get("por_last_update"),
                "dw": d.get("dw"), "depth": depth,
                "pools_used": d.get("pools_used"),
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
        "por_head": "🟡 PROOF-OF-RESERVE STALE — {ticker} ({issuer})",
        "por_body": ("PoR feed age: {age:.1f} hours (threshold {thr:.0f}h) · "
                    "Last update: {upd}\n"
                    "Depth-weighted price: {dw_s} · "
                    "Qualifying depth: {depth_s} across {n_s} pools\n"
                    "Reserves freshness for this issuer is not confirmed."),
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
        "por_head": "🟡 PROOF-OF-RESERVE BASI — {ticker} ({issuer})",
        "por_body": ("Umur feed PoR: {age:.1f} jam (ambang {thr:.0f} jam) · "
                    "Pembaruan terakhir: {upd}\n"
                    "Harga tertimbang kedalaman: {dw_s} · "
                    "Kedalaman lolos: {depth_s} di {n_s} pool\n"
                    "Kesegaran cadangan issuer ini tidak terkonfirmasi."),
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
        snap[iss] = db_query(
            "SELECT status, window_note, next_open_at, observed_at "
            "FROM redemption_windows WHERE issuer = ? "
            "ORDER BY observed_at DESC LIMIT 5000", [iss])
    return snap


def load_live_tickers(red_rows_by_issuer=None):
    uni = db_query(
        "SELECT ticker_id, issuer FROM universe ORDER BY tier, ticker_id")
    latest = {}
    # LIMIT 500 capacity note (fix ronde 5, N5): 13 tickers x ~38 cycles
    # (~3.2h at the 5-min cadence) — the newest row per ticker always
    # survives inside the window. Revisit if the universe grows a lot.
    rows = db_query(
        "SELECT ticker_id, ts, depth_weighted_price, dev_vs_median_pct, "
        "qualifying_depth_usd, pools_used FROM deviations "
        "ORDER BY ts DESC, id DESC LIMIT 500")
    for r in rows:
        if r["ticker_id"] not in latest:
            latest[r["ticker_id"]] = r
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
        # or its age exceeds the same STALE_MINUTES the global gate
        # uses. evaluate_alerts skips spread/deviation alerts for such
        # tickers (redemption/PoR alerts do not depend on the dev row
        # and still fire).
        dev_ts = d.get("ts")
        dev_age_min = None
        if dev_ts:
            parsed = parse_ts(dev_ts)
            if parsed is not None:
                dev_age_min = (datetime.now(UTC) - parsed).total_seconds() / 60.0
        dev_stale = dev_ts is None or dev_age_min is None or dev_age_min > STALE_MINUTES
        out.append({
            "ticker": tid, "issuer": u["issuer"], "venues": venues,
            "dw": d.get("depth_weighted_price"),
            "dev_med": d.get("dev_vs_median_pct"),
            "depth": d.get("qualifying_depth_usd"),
            "pools_used": d.get("pools_used"), "median": median,
            "dev_ts": dev_ts, "dev_age_min": dev_age_min,
            "dev_stale": dev_stale,
            "redemption_status": red["status"] if red else None,
            "redemption_note": red["window_note"] if red else None,
            "next_open_at": red["next_open_at"] if red else None,
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
            return (now_utc - last).total_seconds() / 60.0
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
ALERT_FALLBACK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".alert_sent_fallback.jsonl")


def _fallback_markers():
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
    except OSError:
        return []


def _fallback_suppressed(alert, channel, window_start=None):
    """True iff a fallback marker shows this (ticker, type, channel)
    was already delivered: within the last 24h, or (redemption) since
    the current window began."""
    now = datetime.now(UTC)
    for m in _fallback_markers():
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
    _append_fallback(alert, channel, alert_ts)
    return False


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
    db_execute(
        "INSERT INTO alert_log (ticker_id, alert_ts, alert_type, threshold_pct, "
        "dev_at_alert_pct, depth_at_alert_usd, message_text, outcome, "
        "outcome_ts, closed_below_threshold_ts, channel) VALUES (?,?,?,?,?,?,?,'pending',NULL,NULL,?)",
        [alert["ticker"], alert_ts, alert["type"],
         alert.get("spread_pct") if alert["type"] == "spread"
         else alert.get("dev_pct") if alert["type"] == "deviation_high" else None,
         alert.get("spread_pct") if alert["type"] == "spread"
         else alert.get("dev_pct") if alert["type"] == "deviation_high" else None,
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
    por_data = {
        "ticker": "NVDAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 180.50, "reserve": 4000000.0}],
        "dw": 180.50, "dev_med": 0.20, "depth": 4000000.0,
        "pools_used": 1, "median": 180.50,
        "redemption_status": "open", "por_age_hours": 96.0,
        "por_last_update": "2026-10-20T11:00:00Z",
    }
    scenarios = [
        ("spread (market open)", [spread_data], True),
        ("redemption <=24h (synthetic)", [red_data], False),
        ("PoR stale >72h (synthetic)", [por_data], False),
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
    - S5: the recorded alert_ts is the DELIVERY time of that channel
      (captured per send), not the pass-start time — the 24h dedup
      period is no longer shortened by the pass duration, and a
      redemption alert can no longer be recorded with a timestamp
      before its own window's first observation.
    - S8: the dedup key is "lang:chat_id", not the bare language, so
      replacing a destination mid-period does not suppress the new one.
    """
    sent = 0
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
            # S5: delivery time, captured per channel.
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            record_alert_safe(alert, format_alert(alert, "en"), ts,
                              channel=channel_key)
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


def acquire_alert_lock():
    """Return an open lock-file handle holding an exclusive flock, or
    None when another alert pass already holds it."""
    try:
        fh = open(ALERT_LOCK_PATH, "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except (OSError, IOError):
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
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat_id = (msg.get("chat") or {}).get("id")
                text = msg.get("text") or ""
                if not chat_id or not text.startswith("/"):
                    continue
                reply, new_lang = handle_command(
                    text, lang_by_chat.get(chat_id, "en"))
                lang_by_chat[chat_id] = new_lang
                try:
                    send_message(chat_id, reply)
                    print(f"command reply sent to {chat_id}: {text}")
                except Exception as e:
                    print(f"command reply failed ({chat_id}): {e}")
        except Exception as e:
            print(f"updates error: {type(e).__name__}: {e}")
        save_update_state(offset_path, offset, lang_by_chat)
        # 2) One alert pass (same gates as the live loop).
        # S3 (fix ronde 7): take the single-pass lock first — an
        # overlapping pass skips its alert evaluation entirely instead
        # of double-sending. The lock is released even on error.
        lock = acquire_alert_lock()
        if lock is None:
            print("ALERT LOCK: another alert pass is running — skipping this pass.")
            return 0
        now = datetime.now(UTC)
        try:
            age = load_health_age_minutes(now)
            if age is None or age > STALE_MINUTES:
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
                lock = acquire_alert_lock()
                if lock is None:
                    print("ALERT LOCK: another alert pass is running — "
                          "skipping this evaluation.")
                    lock = None
                try:
                    if lock is None:
                        pass
                    elif (age := load_health_age_minutes(now)) is None or age > STALE_MINUTES:
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
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    chat_id = (msg.get("chat") or {}).get("id")
                    text = msg.get("text") or ""
                    if not chat_id or not text.startswith("/"):
                        continue
                    reply, new_lang = handle_command(
                        text, lang_by_chat.get(chat_id, "en"))
                    lang_by_chat[chat_id] = new_lang
                    send_message(chat_id, reply)
            except Exception as e:
                print(f"poll error: {type(e).__name__}")
                time.sleep(5)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
