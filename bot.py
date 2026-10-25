"""Radar Tokenized Stocks — Telegram bot (MVP, free tier).

Alert rules (design §5.3, adapted where the schema forces it — see
notes below):
- Market OPEN: inter-venue spread (max-min)/depth-weighted >= 1.0%,
  qualifying depth >= $250k, >= 2 qualifying pools.
- Any time: |dev vs cross-venue median| >= 3.0% -> HIGH priority
  deviation alert. Median basis is labeled as such: vs-close is NULL
  in median-only mode (license pending), so no vs-close alert fires.
- Redemption: live rule fires on latest status closed/gated/paused
  (24h dedup). PER-TICKER (un-batched 2026-10-25, Septian's call):
  one message per ticker — a closed Sunday is 13 messages per
  channel per day (24h dedup re-fires daily while closed).
  ADAPTATION: the schema has no close-time column, so
  the design's "closing within <=24h" rule cannot be computed live
  yet; it needs a future next_close_at column. The dry-run scenario
  demonstrates the intended <=24h message format with synthetic data.
- PoR: latest feed age > 72h (or last update older than 72h).
- Stale data gate (design §7.1): when the last successful poller
  cycle is older than 30 minutes, NO new alerts are sent (an admin
  "poller troubled" alert needs a configured admin destination,
  which does not exist yet — the condition is logged, not sent).

Dedup: same (ticker, alert_type) is not re-sent within 24h of a
logged alert (any outcome). Redemption dedups per ticker:
('TSLAx', 'redemption') and ('TSLAx', 'redemption_paused') are
DISTINCT keys, so a recorded closed alert never suppresses a
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

TICKER_PAGE_BASE is the INTENDED subdomain URL pattern
(https://radar.omdanny.site/<ticker>). It activates only when the
subdomain decision lands (see BUILD_LOG_FASE2.md); until then the
link in dry-run messages is a template, not a live page.
"""
import argparse
import json
import os
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
TICKER_PAGE_BASE = "https://radar.omdanny.site"  # intended; pending subdomain decision
SPREAD_THRESHOLD = 1.0
DEV_HIGH_THRESHOLD = 3.0
DEPTH_MIN = 250000.0
POR_STALE_HOURS = 72.0
DEDUP_HOURS = 24.0
STALE_MINUTES = 30.0


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
        venues = [v for v in d.get("venues", [])
                  if v.get("price") is not None and v.get("reserve") is not None]
        depth = d.get("depth")
        if market_open and len(venues) >= 2 and depth is not None and depth >= DEPTH_MIN:
            prices = [v["price"] for v in venues]
            dw = d.get("dw")
            if dw:
                spread = (max(prices) - min(prices)) / dw * 100.0
                if spread >= SPREAD_THRESHOLD:
                    hi = max(venues, key=lambda v: v["price"])
                    lo = min(venues, key=lambda v: v["price"])
                    alerts.append({
                        "type": "spread", "ticker": d["ticker"],
                        "issuer": d.get("issuer"),
                        "spread_pct": round(spread, 3),
                        "high_venue": hi, "low_venue": lo,
                        "dw": dw, "median": d.get("median"),
                        "depth": depth, "pools_used": len(venues),
                    })
        dev = d.get("dev_med")
        if dev is not None and abs(dev) >= DEV_HIGH_THRESHOLD:
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
                        "Depth-weighted price: ${dw:,.2f} · Spread: {spread:.2f}% "
                        "(threshold {thr:.1f}%)\n"
                        "Qualifying depth: ${depth:,.0f} across {n} pools · "
                        "Reference: cross-venue median ${median:,.2f}"),
        "dev_head": "🟠 HIGH DEVIATION — {ticker} ({issuer})",
        "dev_body": ("Depth-weighted price: ${dw:,.2f} · "
                    "Deviation vs cross-venue median: {dev:+.2f}% "
                    "(high-priority threshold {thr:.1f}%)\n"
                    "Qualifying depth: ${depth:,.0f} across {n} pools · "
                    "Reference: cross-venue median ${median:,.2f} · "
                    "Note: vs-close is unavailable (data license pending), "
                    "so this alert uses the median basis."),
        "red_head": "🟡 REDEMPTION — {ticker} ({issuer})",
        "red_paused_head": "🔴 REDEMPTION PAUSED — {ticker} ({issuer})",
        "red_body": ("Redemption window status: {status}\n"
                    "Depth-weighted price: ${dw:,.2f} · "
                    "Qualifying depth: ${depth:,.0f} across {n} pools\n"
                    "{note}\n"
                    "Next opening: {nxt}\n"
                    "Tracked venues for this ticker are listed on its page."),
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
                    "Depth-weighted price: ${dw:,.2f} · "
                    "Qualifying depth: ${depth:,.0f} across {n} pools\n"
                    "Reserves freshness for this issuer is not confirmed."),
        "disclaimer": "Not financial advice. Prices are market data, not recommendations.",
    },
    "id": {
        "spread_head": "🔴 SPREAD — {ticker} ({issuer})",
        "spread_body": ("Venue tertinggi: {hi_dex} ${hi_price:,.2f} · "
                        "Venue terendah: {lo_dex} ${lo_price:,.2f}\n"
                        "Harga tertimbang kedalaman: ${dw:,.2f} · Spread: {spread:.2f}% "
                        "(ambang {thr:.1f}%)\n"
                        "Kedalaman lolos: ${depth:,.0f} di {n} pool · "
                        "Acuan: median lintas-venue ${median:,.2f}"),
        "dev_head": "🟠 DEVIASI TINGGI — {ticker} ({issuer})",
        "dev_body": ("Harga tertimbang kedalaman: ${dw:,.2f} · "
                    "Deviasi vs median lintas-venue: {dev:+.2f}% "
                    "(ambang prioritas tinggi {thr:.1f}%)\n"
                    "Kedalaman lolos: ${depth:,.0f} di {n} pool · "
                    "Acuan: median lintas-venue ${median:,.2f} · "
                    "Catatan: vs-close belum tersedia (lisensi menunggu), "
                    "jadi alert ini memakai basis median."),
        "red_head": "🟡 REDEMPTION — {ticker} ({issuer})",
        "red_paused_head": "🔴 REDEMPTION DIJEDA — {ticker} ({issuer})",
        "red_body": ("Status jendela redemption: {status}\n"
                    "Harga tertimbang kedalaman: ${dw:,.2f} · "
                    "Kedalaman lolos: ${depth:,.0f} di {n} pool\n"
                    "{note}\n"
                    "Pembukaan berikutnya: {nxt}\n"
                    "Venue yang dilacak untuk ticker ini ada di halamannya."),
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
                    "Harga tertimbang kedalaman: ${dw:,.2f} · "
                    "Kedalaman lolos: ${depth:,.0f} di {n} pool\n"
                    "Kesegaran cadangan issuer ini tidak terkonfirmasi."),
        "disclaimer": "Bukan nasihat keuangan. Harga adalah data pasar, bukan rekomendasi.",
    },
}


def _fmt_money(x):
    return f"{float(x):,.2f}"


def format_alert(alert, lang="en"):
    s = BOT_STR.get(lang, BOT_STR["en"])
    link = f"{TICKER_PAGE_BASE}/{alert['ticker']}"
    if alert["type"] == "spread":
        head = s["spread_head"].format(ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["spread_body"].format(
            hi_dex=alert["high_venue"]["dex"], hi_price=alert["high_venue"]["price"],
            lo_dex=alert["low_venue"]["dex"], lo_price=alert["low_venue"]["price"],
            dw=alert["dw"], spread=alert["spread_pct"], thr=SPREAD_THRESHOLD,
            depth=alert["depth"], n=alert["pools_used"], median=alert["median"])
    elif alert["type"] == "deviation_high":
        head = s["dev_head"].format(ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["dev_body"].format(
            dw=alert["dw"], dev=alert["dev_pct"], thr=DEV_HIGH_THRESHOLD,
            depth=alert["depth"] or 0, n=alert["pools_used"] or 0,
            median=alert["median"])
    elif alert["type"] in ("redemption", "redemption_paused"):
        paused = alert["type"] == "redemption_paused"
        head = (s["red_paused_head"] if paused else s["red_head"]).format(
            ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        status_txt = (s["red_batch_status_paused"] if paused
                      else s.get("red_batch_status_" + alert["status"],
                                 alert["status"]))
        note = s["red_batch_paused_note"] if paused else s["red_batch_note"]
        nxt = alert.get("next_open_at") or (
            s["red_batch_within24h"] if alert.get("closes_within_24h") else "—")
        body = s["red_body"].format(
            status=status_txt, note=note, nxt=nxt,
            dw=alert.get("dw") or 0, depth=alert.get("depth") or 0,
            n=alert.get("pools_used") or 0)
        if paused:
            body = s["red_batch_paused_priority"] + "\n" + body
    elif alert["type"] == "por":
        head = s["por_head"].format(ticker=alert["ticker"], issuer=alert.get("issuer") or "—")
        body = s["por_body"].format(
            age=alert["age_hours"], thr=POR_STALE_HOURS,
            upd=alert.get("last_update") or "—",
            dw=alert.get("dw") or 0, depth=alert.get("depth") or 0,
            n=alert.get("pools_used") or 0)
    else:
        raise ValueError(f"unknown alert type {alert['type']}")
    return f"{head}\n{body}\n{link}\n{s['disclaimer']}"


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
def load_live_tickers():
    uni = db_query(
        "SELECT ticker_id, issuer FROM universe ORDER BY tier, ticker_id")
    latest = {}
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
    red_by_issuer = {}
    por_by_issuer = {}
    for iss in {u["issuer"] for u in uni}:
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
        snaps = db_query(
            "SELECT p.dex, s.price_usd, s.reserve_usd FROM pools p "
            "JOIN snapshots s ON s.pool_id = p.pool_id "
            "WHERE p.ticker_id = ? AND p.is_active = 1 "
            "AND s.ts = (SELECT MAX(ts) FROM snapshots s2 WHERE s2.pool_id = p.pool_id)",
            [tid])
        venues = [{"dex": s["dex"], "price": s["price_usd"], "reserve": s["reserve_usd"]}
                  for s in snaps
                  if s["price_usd"] is not None and s["reserve_usd"] is not None]
        prices = sorted(v["price"] for v in venues)
        median = None
        if len(prices) >= 2:
            m = len(prices) // 2
            median = prices[m] if len(prices) % 2 == 1 else (prices[m - 1] + prices[m]) / 2
        red = red_by_issuer.get(u["issuer"])
        por = por_by_issuer.get(u["issuer"])
        out.append({
            "ticker": tid, "issuer": u["issuer"], "venues": venues,
            "dw": d.get("depth_weighted_price"),
            "dev_med": d.get("dev_vs_median_pct"),
            "depth": d.get("qualifying_depth_usd"),
            "pools_used": d.get("pools_used"), "median": median,
            "redemption_status": red["status"] if red else None,
            "redemption_note": red["window_note"] if red else None,
            "next_open_at": red["next_open_at"] if red else None,
            "por_age_hours": por["age_hours"] if por else None,
            "por_last_update": por["last_update_ts"] if por else None,
        })
    return out


def load_health_age_minutes(now_utc):
    rows = db_query(
        "SELECT cycle_ts, cycles_ok FROM poller_health ORDER BY id DESC LIMIT 5")
    if not rows:
        return None
    last = parse_ts(rows[0]["cycle_ts"])
    if last is None:
        return None
    return (now_utc - last).total_seconds() / 60.0


def recent_alert_exists(ticker, alert_type, hours=DEDUP_HOURS):
    rows = db_query(
        "SELECT COUNT(*) AS n FROM alert_log WHERE ticker_id = ? "
        "AND alert_type = ? AND alert_ts >= datetime('now', ?)",
        [ticker, alert_type, f"-{int(hours)} hours"])
    return bool(rows and int(rows[0]["n"]) > 0)


def record_alert(alert, message_text, alert_ts):
    db_execute(
        "INSERT INTO alert_log (ticker_id, alert_ts, alert_type, threshold_pct, "
        "dev_at_alert_pct, depth_at_alert_usd, message_text, outcome, "
        "outcome_ts, closed_below_threshold_ts) VALUES (?,?,?,?,?,?,?,'pending',NULL,NULL)",
        [alert["ticker"], alert_ts, alert["type"],
         alert.get("spread_pct") if alert["type"] == "spread"
         else alert.get("dev_pct") if alert["type"] == "deviation_high" else None,
         alert.get("spread_pct") if alert["type"] == "spread"
         else alert.get("dev_pct") if alert["type"] == "deviation_high" else None,
         alert.get("depth"), message_text],
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
        if age is not None and age > STALE_MINUTES:
            print("STALE GATE: data older than 30 min — no alerts would be sent.")
            return 0
        tickers = load_live_tickers()
        alerts = evaluate_alerts(tickers, is_market_open(now))
        print(f"market open (ET): {is_market_open(now)}")
        print(f"alerts that would fire: {len(alerts)}")
        for a in alerts:
            dup = recent_alert_exists(a["ticker"], a["type"])
            print(f"--- {a['type']} {a['ticker']} (dedup suppressed: {dup}) ---")
            if not dup:
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
        now = datetime.now(UTC)
        try:
            age = load_health_age_minutes(now)
            if age is None or age > STALE_MINUTES:
                print("STALE GATE: skipping alert evaluation (no fresh data).")
                return 0
            tickers = load_live_tickers()
            channels = alert_channels()
            sent = 0
            for a in evaluate_alerts(tickers, is_market_open(now)):
                if recent_alert_exists(a["ticker"], a["type"]):
                    print(f"ALERT suppressed (dedup 24h): "
                          f"{a['type']} {a['ticker']}")
                    continue
                if not channels:
                    print(f"ALERT (no channel configured, not sent): "
                          f"{a['type']} {a['ticker']}")
                    continue
                sent_any = False
                for lang, cid in channels:
                    try:
                        send_message(cid, format_alert(a, lang))
                        sent_any = True
                        print(f"ALERT sent ({lang}): "
                              f"{a['type']} {a['ticker']}")
                    except Exception as e:
                        print(f"ALERT send failed ({lang}): "
                              f"{a['type']} {a['ticker']}: {e}")
                if sent_any:
                    record_alert(a, format_alert(a, "en"),
                                 now.strftime("%Y-%m-%dT%H:%M:%SZ"))
                    sent += 1
            print(f"once done: alerts sent: {sent}")
        except Exception as e:
            print(f"evaluation error: {type(e).__name__}: {e}")
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
                try:
                    age = load_health_age_minutes(now)
                    if age is None or age > STALE_MINUTES:
                        print("STALE GATE: skipping alert evaluation (no fresh data).")
                    else:
                        tickers = load_live_tickers()
                        channels = alert_channels()
                        for a in evaluate_alerts(tickers, is_market_open(now)):
                            if recent_alert_exists(a["ticker"], a["type"]):
                                print(f"ALERT suppressed (dedup 24h): "
                                      f"{a['type']} {a['ticker']}")
                                continue
                            if not channels:
                                # No alert channel configured yet: log only.
                                # Nothing is recorded in alert_log for an
                                # alert that was never sent.
                                print(f"ALERT (no channel configured, not sent): "
                                      f"{a['type']} {a['ticker']}")
                                continue
                            sent_any = False
                            for lang, cid in channels:
                                text = format_alert(a, lang)
                                try:
                                    send_message(cid, text)
                                    sent_any = True
                                    print(f"ALERT sent ({lang}): "
                                          f"{a['type']} {a['ticker']}")
                                except Exception as e:
                                    print(f"ALERT send failed ({lang}): "
                                          f"{a['type']} {a['ticker']}: {e}")
                            if sent_any:
                                # One alert_log row per alert (not per
                                # channel); the stored text is the EN one.
                                record_alert(
                                    a, format_alert(a, "en"),
                                    now.strftime("%Y-%m-%dT%H:%M:%SZ"))
                except Exception as e:
                    print(f"evaluation error: {type(e).__name__}: {e}")
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
