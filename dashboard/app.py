"""Radar Tokenized Stocks — public dashboard (presentation rewrite).

ACC design (2026-10-24) + v2 delta "Radar hidup": anti-AI-slop
editorial template, paper-light theme, burnt-orange accent for
deviation/signal + disciplined deep teal for depth/exit elements ONLY
(no green/red, no third color, no gradients), native Streamlit
interactivity ONLY (no custom JavaScript, no custom components —
inline <script> does not execute in Streamlit; Altair ships with
Streamlit and is not a new dependency). All user-facing strings come
from i18n.py; all pure logic from logic.py / risk.py; all Turso access
from turso_read.py (SELECT-only reads + the single waitlist INSERT).
Data layer untouched — this file is presentation only.

Test-only hook: env RADAR_TEST_HEALTH_JSON, when set to a JSON list of
{cycle_ts, cycles_ok} rows, replaces the live poller_health read so the
stale banner can be tested without touching production data. It is
off by default.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import altair as alt
import pandas as pd
import streamlit as st

from i18n import (DONATE_ADDRESS, DONATE_PAY_URL, LINKEDIN_URL,
                  SIZE_BUCKETS, t)
from logic import (best_exit_venues, fmt_abbr, fmt_wita, freshness_status,
                   parse_ts)
from risk import weekend_risk_score
from turso_read import insert_waitlist, query

st.set_page_config(page_title=t("en", "app_title"), layout="wide")

LIQ_MIN = 100000.0
DEPTH_FLOOR = 250000.0
ET = ZoneInfo("America/New_York")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,600;6..72,700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
.stApp { background-color: #FAF8F5; color: #16130F; }
h1, h2, h3 { font-family: 'Newsreader', Georgia, serif !important; color: #16130F; }
.wordmark { font-family: 'Newsreader', Georgia, serif; font-size: 28px;
  font-weight: 700; letter-spacing: 0.04em; color: #16130F; line-height: 1.1; }
[data-testid="stMetricValue"] { font-family: 'IBM Plex Mono', ui-monospace,
  SFMono-Regular, Menlo, monospace !important; }
.card { border: 1px solid #E5E0D8; border-radius: 10px; padding: 14px 16px;
  background: #FFFFFF; margin-bottom: 12px; }
.livedot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #C2410C; margin-right: 6px; vertical-align: middle;
  animation: pulse-dot 2s ease-in-out infinite; }
@keyframes pulse-dot { 0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.45; transform: scale(1.4); } }
.accent { color: #C2410C; }
.hero-num { font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular,
  Menlo, monospace; font-size: clamp(32px, 11vw, 76px); font-weight: 500;
  line-height: 1.05; color: #C2410C; max-width: 100%;
  overflow-wrap: anywhere; }
.depth-num { color: #0F766E; font-family: 'IBM Plex Mono', ui-monospace,
  SFMono-Regular, Menlo, monospace; }
.depth-rule { border-top: 3px solid #0F766E; margin: 10px 0 2px 0; }
div.stButton > button { border-color: #E5E0D8; color: #16130F;
  transition: border-color .2s ease, color .2s ease; }
div.stButton > button:hover { border-color: #C2410C; color: #C2410C; }
[data-testid="stMetricValue"] { font-size: 36px !important; }
@media (max-width: 640px) { .wordmark { font-size: 22px; } }
.header-rule { border-top: 2px solid #16130F; margin: 2px 0 14px 0; }
.page-end { height: 36px; }
.stApp a { color: #16130F !important; text-decoration: underline;
  text-decoration-color: #C2410C; text-underline-offset: 2px; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stToolbar"] { visibility: hidden; }
[data-testid="stDeployButton"] { visibility: hidden; }
[data-testid="stDecoration"] { visibility: hidden; }
/* v3.1 responsive: Streamlit columns do NOT stack by themselves — without
   this, header/nav/filters/movers/footer stay squeezed side by side on
   phones instead of stacking. The 768px breakpoint is the task's spec. */
.radar-header { display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 6px 16px; max-width: 100%; }
.radar-live { white-space: nowrap; font-size: 14px; color: #6B655C; }
img { max-width: 100%; height: auto; }
[data-testid="stDataFrame"] { min-width: 0; }
[data-testid="stVegaLiteChart"] { min-width: 0; max-width: 100%; }
@media (max-width: 768px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
  [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    flex: 1 1 100% !important; min-width: 0 !important;
    max-width: 100% !important; }
  .radar-header { flex-direction: column; align-items: flex-start; gap: 2px; }
  .wordmark { font-size: 22px; }
}
/* v3.2 desktop nav shrink-wrap: the nav block is the 4th child of the
   main vertical block on EVERY page (1st = CSS markdown container,
   2nd = header columns, 3rd = header-rule markdown, 4th = nav) —
   verified by local DOM inspection 2026-10-25. flex:0 0 auto ALONE
   did NOT collapse the columns: Streamlit pins each column's WIDTH
   in its own stylesheet (ratio widths), which flex-basis:auto
   honours, so columns stayed at uniform 135px. The collapse needs
   width:auto on the column AND fit-content on its inner vertical
   block (proven live 2026-10-25: columns 61/65/70/106px = button
   widths, spacer 0, buttons adjacent). Scoped to min-width 769px so
   it can never fight the 768px stacking rule, and scoped to
   stMainBlockContainer so nested vertical blocks (fragments,
   containers) are untouched. If this selector ever stops matching,
   the nav simply falls back to the v3.1 spread layout — it cannot
   break anything else. */
@media (min-width: 769px) {
  div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] > div:nth-child(4) > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    flex: 0 0 auto !important; max-width: none !important;
    min-width: 0 !important; width: auto !important;
  }
  div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] > div:nth-child(4) > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {
    width: fit-content !important; min-width: 0 !important;
  }
}
.kpi-value { font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular,
  Menlo, monospace; font-size: 26px; font-weight: 500; line-height: 1.15;
  color: #16130F; }
.kpi-sub { font-size: 13px; color: #6B655C; line-height: 1.35; }
/* v3.1 Cloud chrome: stAppDeployButton is the 1.66.1 deploy/manage button
   testid (proven in the installed frontend bundle — the old
   stDeployButton name no longer matches, which is why v3 missed it). */
[data-testid="stAppDeployButton"] { display: none !important; }
/* Best-effort, UNVERIFIED against live DOM: the creator avatar is
   Cloud-injected (absent from local boots and from the 1.66.1 frontend
   bundle). Parent's live DOM diagnostic 2026-10-25 proved it lives in
   the parent document as a sibling of the app iframe, so app CSS cannot
   reach it — these rules are retained as harmless no-ops only. */
a[aria-label="App Creator Avatar"] { display: none !important; }
img[alt="App Creator Avatar"] { display: none !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- data
@st.cache_data(ttl=60)
def get_health(override_json=""):
    if override_json:
        import json
        return json.loads(override_json)
    return query(
        "SELECT cycle_ts, cycles_ok, gap_note FROM poller_health "
        "ORDER BY id DESC LIMIT 5"
    )


@st.cache_data(ttl=300)
def get_universe():
    return query(
        "SELECT ticker_id, underlying, issuer, legal_type, tier, status "
        "FROM universe ORDER BY tier, ticker_id"
    )


@st.cache_data(ttl=300)
def get_latest_deviations():
    # Test-only hook: env RADAR_TEST_LATEST_JSON, when set to a JSON
    # {ticker: row} object, replaces the live read (mirrors the
    # RADAR_TEST_HEALTH_JSON hook). Lets AppTest execute branches that
    # need specific data (e.g. a map outlier) without touching Turso.
    # Off by default.
    override = os.environ.get("RADAR_TEST_LATEST_JSON", "")
    if override:
        import json
        try:
            return json.loads(override)
        except (TypeError, ValueError):
            pass
    rows = query(
        "SELECT ticker_id, ts, depth_weighted_price, dev_vs_close_pct, "
        "dev_vs_median_pct, qualifying_depth_usd, pools_used, method_version "
        "FROM deviations ORDER BY ts DESC, id DESC LIMIT 500"
    )
    seen = {}
    for r in rows:
        if r["ticker_id"] not in seen:
            seen[r["ticker_id"]] = r
    return seen


@st.cache_data(ttl=300)
def get_pools_excluded():
    """Latest pools_excluded per ticker — defensive by design.

    The column is added separately from this file; if it is missing
    (or the query fails) this returns {} and the ticker-page note
    simply does not render. Never raises. Values arrive as strings
    from Hrana, so coerce to int ('0' is truthy — it must not leak
    through as a visible zero-count note).

    Test-only hook: env RADAR_TEST_POOLS_EXCLUDED_JSON, when set to a
    JSON {ticker: count} object, replaces the live read (mirrors the
    RADAR_TEST_HEALTH_JSON hook). Off by default.
    """
    override = os.environ.get("RADAR_TEST_POOLS_EXCLUDED_JSON", "")
    if override:
        import json
        try:
            raw = json.loads(override)
            return {k: int(v) for k, v in raw.items()}
        except (TypeError, ValueError):
            return {}
    try:
        rows = query(
            "SELECT ticker_id, pools_excluded FROM deviations "
            "ORDER BY ts DESC, id DESC LIMIT 500"
        )
    except Exception:
        return {}
    out = {}
    for r in rows:
        if r["ticker_id"] not in out:
            try:
                out[r["ticker_id"]] = int(r.get("pools_excluded") or 0)
            except (TypeError, ValueError):
                out[r["ticker_id"]] = 0
    return out


@st.cache_data(ttl=300)
def get_spark_data(hours):
    """Deviation series per ticker over the window (sparkline + change
    column fuel).

    Hourly buckets keep the read volume bounded (~168 points/ticker for
    7 days). For sub-day windows (the v3.2 1h option) hourly buckets
    would collapse to a single point, so hours < 24 reads per-cycle
    rows instead (~12 cycles/ticker for 1h — still bounded).
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if hours >= 24:
        rows = query(
            "SELECT ticker_id, strftime('%Y-%m-%dT%H:00:00Z', ts) AS bucket, "
            "AVG(dev_vs_median_pct) AS dev FROM deviations "
            "WHERE ts >= ? AND dev_vs_median_pct IS NOT NULL "
            "GROUP BY ticker_id, bucket ORDER BY bucket ASC",
            [cutoff],
        )
        out = {}
        for r in rows:
            if r.get("dev") is not None:
                out.setdefault(r["ticker_id"], []).append(float(r["dev"]))
        return out
    rows = query(
        "SELECT ticker_id, ts, dev_vs_median_pct AS dev FROM deviations "
        "WHERE ts >= ? AND dev_vs_median_pct IS NOT NULL "
        "ORDER BY ts ASC LIMIT 2000",
        [cutoff],
    )
    out = {}
    for r in rows:
        if r.get("dev") is not None:
            out.setdefault(r["ticker_id"], []).append(float(r["dev"]))
    return out


@st.cache_data(ttl=300)
def get_chart_series(ticker, hours):
    """Deviation series for one ticker: per-cycle for 24h, hourly
    average for 7d/30d (same bounding rationale as get_spark_data)."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if hours <= 24:
        rows = query(
            "SELECT ts, dev_vs_median_pct FROM deviations "
            "WHERE ticker_id = ? AND ts >= ? "
            "AND dev_vs_median_pct IS NOT NULL ORDER BY ts ASC LIMIT 400",
            [ticker, cutoff],
        )
        return [(r["ts"], float(r["dev_vs_median_pct"])) for r in rows]
    # v3 fix: the bucket alias MUST NOT be named 'ts' — SQLite resolves
    # GROUP BY ts to the input column deviations.ts (per-cycle rows,
    # 60 rows with 6 repeated bucket labels, as seen live), not to the
    # strftime alias. Aliasing it 'bucket' (no such input column) makes
    # GROUP BY aggregate truly hourly.
    rows = query(
        "SELECT strftime('%Y-%m-%dT%H:00:00Z', ts) AS bucket, "
        "AVG(dev_vs_median_pct) AS dev FROM deviations "
        "WHERE ticker_id = ? AND ts >= ? "
        "AND dev_vs_median_pct IS NOT NULL GROUP BY bucket ORDER BY bucket ASC",
        [ticker, cutoff],
    )
    return [(r["bucket"], float(r["dev"])) for r in rows if r.get("dev") is not None]


@st.cache_data(ttl=300)
def get_sim_history(ticker):
    """30-day per-cycle deviations for the threshold simulator."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return query(
        "SELECT dev_vs_median_pct, qualifying_depth_usd, pools_used "
        "FROM deviations WHERE ticker_id = ? AND ts >= ? "
        "AND dev_vs_median_pct IS NOT NULL ORDER BY ts ASC LIMIT 9000",
        [ticker, cutoff],
    )


@st.cache_data(ttl=300)
def get_weekly_top():
    """Largest |deviation| event of the last 7 days (single row).

    Editorial fuel for the weekly story — computed from data, never
    hand-written. Returns None when no non-null deviation exists.
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = query(
        "SELECT ticker_id, ts, dev_vs_median_pct, qualifying_depth_usd, "
        "pools_used FROM deviations WHERE ts >= ? "
        "AND dev_vs_median_pct IS NOT NULL "
        "ORDER BY ABS(dev_vs_median_pct) DESC LIMIT 1",
        [cutoff],
    )
    return rows[0] if rows else None


@st.cache_data(ttl=300)
def get_venue_latest(ticker):
    return query(
        "SELECT p.pool_id, p.dex, p.chain, p.pair_address, p.quote_token, "
        "s.price_usd, s.reserve_usd, s.volume_24h_usd, s.ts "
        "FROM pools p JOIN snapshots s ON s.pool_id = p.pool_id "
        "WHERE p.ticker_id = ? AND p.is_active = 1 "
        "AND s.ts = (SELECT MAX(ts) FROM snapshots s2 WHERE s2.pool_id = p.pool_id) "
        "ORDER BY s.reserve_usd DESC",
        [ticker],
    )


@st.cache_data(ttl=300)
def get_redemption(issuer):
    rows = query(
        "SELECT issuer, asset, status, window_note, window_note_en, "
        "observed_at, source, next_open_at FROM redemption_windows "
        "WHERE issuer = ? ORDER BY observed_at DESC LIMIT 1",
        [issuer],
    )
    return rows[0] if rows else None


@st.cache_data(ttl=300)
def get_all_venues_latest():
    """Latest snapshot per active pool, all tickers, ONE query.

    The v3.2 master table needs a venue-best price + spread per ticker;
    one grouped read beats 13 per-ticker reads (same cache TTL)."""
    rows = query(
        "SELECT p.ticker_id, p.dex, p.chain, s.price_usd, s.reserve_usd "
        "FROM pools p JOIN snapshots s ON s.pool_id = p.pool_id "
        "WHERE p.is_active = 1 "
        "AND s.ts = (SELECT MAX(ts) FROM snapshots s2 "
        "WHERE s2.pool_id = p.pool_id) "
        "ORDER BY s.reserve_usd DESC"
    )
    out = {}
    for r in rows:
        out.setdefault(r["ticker_id"], []).append(r)
    return out


@st.cache_data(ttl=300)
def get_venues_live():
    """Pools reporting in the latest snapshot cycle vs active pools.

    Returns {live, total}. One query; the KPI strip's 'venues live'."""
    rows = query(
        "SELECT (SELECT COUNT(*) FROM pools WHERE is_active = 1) AS total, "
        "COUNT(DISTINCT pool_id) AS live FROM snapshots "
        "WHERE ts = (SELECT MAX(ts) FROM snapshots)"
    )
    if rows:
        try:
            return {"live": int(rows[0].get("live") or 0),
                    "total": int(rows[0].get("total") or 0)}
        except (TypeError, ValueError):
            pass
    return {"live": 0, "total": 0}


@st.cache_data(ttl=300)
def get_redemption_summary():
    """{open, total} across redemption_windows rows (KPI strip)."""
    rows = query(
        "SELECT status, COUNT(*) AS n FROM redemption_windows GROUP BY status"
    )
    total = 0
    opened = 0
    for r in rows:
        try:
            n = int(r.get("n") or 0)
        except (TypeError, ValueError):
            n = 0
        total += n
        if (r.get("status") or "").lower() == "open":
            opened += n
    return {"open": opened, "total": total}


@st.cache_data(ttl=300)
def get_por(issuer):
    rows = query(
        "SELECT issuer, feed_address, last_update_ts, age_hours, "
        "reserves_vs_supply_note, checked_at FROM por_feeds WHERE issuer = ? "
        "ORDER BY checked_at DESC LIMIT 1",
        [issuer],
    )
    return rows[0] if rows else None


@st.cache_data(ttl=300)
def get_alerts(ticker):
    return query(
        "SELECT alert_ts, alert_type, threshold_pct, dev_at_alert_pct, "
        "depth_at_alert_usd, message_text, outcome FROM alert_log "
        "WHERE ticker_id = ? ORDER BY alert_ts DESC LIMIT 20",
        [ticker],
    )


# ---------------------------------------------------------------- helpers
def market_is_open(now_utc):
    """NYSE regular schedule (Mon–Fri 09:30–16:00 America/New_York).

    Exchange holidays are NOT tracked — the status strings say so.
    """
    ny = now_utc.astimezone(ET)
    if ny.weekday() >= 5:
        return False
    mins = ny.hour * 60 + ny.minute
    return 9 * 60 + 30 <= mins < 16 * 60


def cross_venue_spread(venues, dw_price):
    """(max - min qualifying venue price) / depth-weighted price, in %."""
    prices = [float(v["price_usd"]) for v in venues
              if v.get("price_usd") is not None
              and (v.get("reserve_usd") or 0) >= LIQ_MIN]
    if len(prices) < 2 or not dw_price:
        return None
    return (max(prices) - min(prices)) / float(dw_price) * 100.0


def tint_dev(series, divisor=2.0):
    """Single-accent tint for the deviation column: burnt orange whose
    opacity scales with |deviation|, capped at 0.85.
    Accepts display strings ('+0.24', '-25.97', '—') as well as
    numbers — the tables now store formatted strings, not raw floats.
    divisor converts the column's unit to percent: 2.0 for percent
    columns, 200.0 for basis-point columns (100 bps = 1%)."""
    out = []
    for v in series:
        try:
            a = min(abs(float(str(v).replace("%", "").replace("+", ""))) / divisor, 0.85)
        except (TypeError, ValueError):
            a = 0.0
        out.append(f"background-color: rgba(194, 65, 12, {a:.2f})"
                   if a > 0.02 else "")
    return out


def fmt_usd(v, decimals=2):
    """'$4,875,369.02' or '—' for None (audit: no raw floats in tables)."""
    if v is None:
        return "—"
    try:
        return f"${float(v):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def fmt_dev(v, pct=False):
    """Deviation cells: '+0.24' / '-25.97' / '0.00' (no sign on a value
    that rounds to zero — the audit's '-0.00'/' +0.00' complaint).

    pct=True appends '%' for standalone figures (pulse hero, metrics,
    story lines) where no column header carries the unit.
    """
    if v is None:
        return "—"
    try:
        r = round(float(v), 2)
    except (TypeError, ValueError):
        return "—"
    if r == 0:
        return "0.00%" if pct else "0.00"
    return f"{r:+.2f}%" if pct else f"{r:+.2f}"


def fmt_signed1(v):
    """Signed 1-decimal figure (bps columns, KPI card), with the same
    zero rule as fmt_dev: a value rounding to zero shows '0.0' with
    NO sign. Without this, a -0.04 change renders as '-0.0' — the
    signed-zero class of bug the v3 audit flagged in dev cells."""
    if v is None:
        return "—"
    try:
        r = round(float(v), 1)
    except (TypeError, ValueError):
        return "—"
    return "0.0" if r == 0 else f"{r:+.1f}"


_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def spark_text(series, width=32):
    """Unicode sparkline for a numeric series; '—' when empty.

    Text cells (unlike LineChartColumn) never clip at cell edges and
    render an explicit dash for missing data instead of a blank cell.
    Long series are evenly sampled to at most `width` characters.
    """
    vals = [float(x) for x in (series or []) if x is not None]
    if not vals:
        return "—"
    if len(vals) > width:
        step = len(vals) / float(width)
        vals = [vals[int(i * step)] for i in range(width)]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return "▅" * len(vals)
    out = []
    for x in vals:
        idx = int((x - lo) / (hi - lo) * 7.999)
        out.append(_SPARK_CHARS[idx])
    return "".join(out)


def row_ticker(displayed_tickers, row_idx):
    """Pure helper: map a clicked home-table row index to its ticker."""
    if row_idx is None or row_idx < 0 or row_idx >= len(displayed_tickers):
        return None
    return displayed_tickers[row_idx]


def render_freshness(lang):
    health = get_health(os.environ.get("RADAR_TEST_HEALTH_JSON", ""))
    stt = freshness_status(health, datetime.now(timezone.utc))
    if stt["last_ts"]:
        if stt["age_min"] is not None and stt["age_min"] < 1:
            msg = t(lang, "freshness_now", time=fmt_wita(stt["last_ts"], lang))
        else:
            mins = int(stt["age_min"]) if stt["age_min"] is not None else 0
            msg = t(lang, "freshness", time=fmt_wita(stt["last_ts"], lang), mins=mins)
    else:
        msg = t(lang, "no_data")
    st.markdown(f"**{msg}**")
    if stt["stale"]:
        st.warning(
            t(lang, "stale_banner",
              time=fmt_wita(stt["last_ts"], lang) if stt["last_ts"] else "—")
        )
    return stt


def render_footer(lang):
    """Footer v3: QR + text side by side (2 columns), the wallet
    address in its own copyable block with a line break BEFORE the
    'donations do not unlock features' sentence (the audit's run-on
    sentence), links in ink with an orange underline (not bright blue),
    and bottom padding that closes the page."""
    st.markdown("---")
    st.subheader(t(lang, "policy_title"))
    st.markdown(t(lang, "policy_text").replace("\n", "\n\n"))
    st.subheader(t(lang, "donate_title"))
    qcol, tcol = st.columns([1, 3], gap="medium")
    with qcol:
        qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "assets", "donate_qr.png")
        if os.path.exists(qr_path):
            st.image(qr_path, width=220)
    with tcol:
        st.markdown(t(lang, "donate_send"))
        st.code(DONATE_ADDRESS)
        st.markdown(t(lang, "donate_nofeatures"))
        st.markdown(f"[{t(lang, 'donate_pay_link')}]({DONATE_PAY_URL})")
        st.markdown(f"[{t(lang, 'linkedin_label')}]({LINKEDIN_URL})")
    st.caption(t(lang, "disclaimer"))
    st.caption(t(lang, "footer_note"))
    st.markdown('<div class="page-end"></div>', unsafe_allow_html=True)


def render_risk_breakdown(lang, score):
    """Weekend risk score with per-component values (experimental label
    lives in the section title key itself). v3.2: the headline number
    is the NORMALIZED 0–100 score (raw totals are not comparable across
    tickers with different missing components); a partial score always
    names how many of the 4 components are present."""
    comp = score["components"]
    labels = {
        "deviation": t(lang, "risk_dev_label"),
        "depth": t(lang, "risk_depth_label"),
        "redemption": t(lang, "risk_red_label"),
        "por": t(lang, "risk_por_label"),
    }
    parts = []
    for k in ("deviation", "depth", "redemption", "por"):
        v = comp[k]
        parts.append(f"{labels[k]}: {v:.1f}" if v is not None
                     else f"{labels[k]}: —")
    # Wave 1: the Total cell carries its component count in-line, so a
    # partial score can never be read as a complete one.
    if score["score_100"] is None:
        _total_txt = "—"
    elif score["partial"]:
        _total_txt = (f"{score['score_100']:.1f} "
                      f"({score['components_present']}/4)")
    else:
        _total_txt = f"{score['score_100']:.1f}"
    st.markdown(f"**{t(lang, 'risk_total_100')}: {_total_txt}** "
                f"(method {score['method_version']})")
    st.markdown(" · ".join(parts))
    if score["partial"]:
        st.info(t(lang, "risk_partial_n", n=score["components_present"]))
    st.caption(t(lang, "risk_method"))


def render_kpi_strip(lang, latest):
    """v3.2 KPI strip: worst deviation, venues live, PoR stale,
    redemption open. Cards use abbreviated numbers; tables keep the
    full comma format. PoR shows '—' (no feed connected) and
    redemption shows 'Unknown' (Wave 1: the old '0/1' headline read as
    'confirmed closed' while the status is actually unknown) — never
    invented values."""
    def _card(label, value, sub):
        st.markdown(
            f'<div class="card"><div class="kpi-sub">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-sub">{sub}</div></div>',
            unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4, gap="small")
    with_dev = [(tid, d) for tid, d in latest.items()
                if d.get("dev_vs_median_pct") is not None]
    with k1:
        if with_dev:
            tid, d = max(with_dev,
                         key=lambda kv: abs(kv[1]["dev_vs_median_pct"]))
            bps = float(d["dev_vs_median_pct"]) * 100.0
            _card(t(lang, "kpi_worst"), f"{fmt_signed1(bps)} bps",
                  t(lang, "kpi_worst_sub", ticker=tid,
                    depth=fmt_abbr(d.get("qualifying_depth_usd"))))
        else:
            _card(t(lang, "kpi_worst"), "—", t(lang, "pulse_no_data"))
    vl = get_venues_live()
    with k2:
        _card(t(lang, "kpi_venues"), f"{vl['live']}/{vl['total']}",
              t(lang, "kpi_venues_sub"))
    with k3:
        _card(t(lang, "kpi_por"), "—", t(lang, "kpi_por_sub"))
    with k4:
        # Wave 1: headline is 'Unknown', not '0/1'. The sub stays
        # truthful (documented only, no live status).
        _card(t(lang, "kpi_redemption"), t(lang, "redemption_unknown"),
              t(lang, "kpi_redemption_sub"))


def render_comparison_bars(lang, latest):
    """v3.2 comparison chart: one diverging bar chart of all 13
    deviations (bps) on one axis, coloured by published status
    thresholds (single orange family: pale = OK, mid = Watch,
    full = Alert). Tooltip carries venue, price, depth, PoR age,
    timestamp. Single-pool tickers have no deviation and are listed
    below, never plotted at zero."""
    st.subheader(t(lang, "bars_title"))
    st.markdown(t(lang, "bars_note"))
    venues_all = get_all_venues_latest()
    rows, nodata = [], []
    for tid, d in latest.items():
        dev = d.get("dev_vs_median_pct")
        if dev is None:
            nodata.append(tid)
            continue
        bps = float(dev) * 100.0
        status = ("alert" if abs(bps) > 100
                  else "watch" if abs(bps) > 50 else "ok")
        vlist = venues_all.get(tid, [])
        best_dex = vlist[0].get("dex") if vlist else "—"
        rows.append({
            "ticker": tid, "bps": bps, "status": status,
            "status_label": t(lang, "status_" + status),
            "venue": best_dex,
            "price": (f"${float(d['depth_weighted_price']):,.2f}"
                      if d.get("depth_weighted_price") is not None else "—"),
            "depth": fmt_usd(d.get("qualifying_depth_usd")),
            "por": t(lang, "por_not_published"),
            "ts": fmt_wita(d.get("ts"), lang),
        })
    if rows:
        bdf = pd.DataFrame(rows)
        bchart = alt.Chart(bdf).mark_bar().encode(
            x=alt.X("bps:Q", title=t(lang, "col_dev_bps")),
            y=alt.Y("ticker:N", sort="-x", title=None),
            color=alt.Color("status:N",
                            scale=alt.Scale(
                                domain=["ok", "watch", "alert"],
                                range=["#D8D2C8", "#E07B4A", "#C2410C"]),
                            legend=None),
            tooltip=[alt.Tooltip("ticker:N"),
                     alt.Tooltip("bps:Q", format="+.1f"),
                     alt.Tooltip("status_label:N"),
                     alt.Tooltip("venue:N"),
                     alt.Tooltip("price:N"),
                     alt.Tooltip("depth:N"),
                     alt.Tooltip("por:N"),
                     alt.Tooltip("ts:N")],
        )
        st.altair_chart(bchart.properties(height=320), width="stretch")
    if nodata:
        st.caption(f"{t(lang, 'bars_nodata')} {', '.join(sorted(nodata))}")


def render_coming_soon(lang):
    """v3.2: one compact 'coming soon' summary. The per-place honest
    labels (license note, doc note, por_none, alertlog_empty) all stay
    where they are — this list never hides missing data behind itself."""
    st.subheader(t(lang, "coming_title"))
    st.markdown(t(lang, "coming_text"))


def render_methodology(lang):
    """v3.2 Methodology page: definitions, thresholds, sources,
    limitations, the human-checked definition, and coming-soon items.
    Each body paragraph is self-contained (it opens with its topic),
    so no extra section-title keys are needed."""
    st.subheader(t(lang, "methodology_title"))
    st.markdown(t(lang, "methodology_intro"))
    for key in ("methodology_dev", "methodology_spread",
                "methodology_depth", "methodology_por",
                "methodology_redemption", "methodology_thresholds",
                "methodology_sources", "methodology_limits",
                "methodology_human", "methodology_coming"):
        st.markdown("---")
        st.markdown(t(lang, key))


def render_dev_map(lang, latest):
    """v2 deviation map: Altair scatter (native, no custom JavaScript).

    x = deviation vs median (%), y = qualifying depth (log scale),
    bubble size = pools, color = |deviation| on the burnt-orange scale.
    HONESTY RULE: tickers with NULL deviation (single pool) are NEVER
    plotted at x=0 — that would fake a zero deviation. They appear as
    a dimmed list below with the reason stated. Bubble click navigates
    via Altair on_select with a change-guard (mirrors the table guard);
    the selectbox + button below is the guaranteed fallback.
    v3.1: the 3 largest-|dev| bubbles carry on-chart ticker labels.
    """
    st.subheader(t(lang, "map_title"))
    st.markdown(t(lang, "map_note"))
    plotted, nodata = [], []
    for tid, d in latest.items():
        dev = d.get("dev_vs_median_pct")
        depth = d.get("qualifying_depth_usd")
        if dev is not None and depth:
            plotted.append({"ticker": tid, "dev": float(dev),
                            "absdev": abs(float(dev)),
                            "depth": float(depth),
                            "pools": int(d.get("pools_used") or 0)})
        elif dev is None:
            nodata.append(tid)
    if plotted:
        # v3.2 fixed axis: the domain is ALWAYS ±1% (review: auto-scale
        # re-ranged every refresh, invalidating cross-time comparison).
        # Tickers beyond it are labeled at the clamped edge with their
        # true deviation instead of being plotted off-scale.
        CLAMP = 1.0
        in_range = [p for p in plotted if abs(p["dev"]) <= CLAMP]
        offscale = [p for p in plotted if abs(p["dev"]) > CLAMP]
        domain = [-CLAMP, CLAMP]
        df = pd.DataFrame(in_range)
        pick = alt.selection_point(fields=["ticker"], name="pick")
        circles = alt.Chart(df).mark_circle(stroke="#16130F",
                                            strokeWidth=0.5).encode(
            x=alt.X("dev:Q", title=t(lang, "map_x"),
                    scale=alt.Scale(domain=domain)),
            y=alt.Y("depth:Q", scale=alt.Scale(type="log"),
                    title=t(lang, "map_y"),
                    axis=alt.Axis(titleColor="#0F766E")),
            size=alt.Size("pools:Q", title=t(lang, "col_pools"),
                          scale=alt.Scale(range=[60, 420])),
            color=alt.Color("absdev:Q",
                            scale=alt.Scale(range=["#F6C9B8", "#C2410C"]),
                            legend=None),
            tooltip=[alt.Tooltip("ticker:N"),
                     alt.Tooltip("dev:Q", format="+.2f"),
                     alt.Tooltip("depth:Q", format="$,.0f"),
                     alt.Tooltip("pools:Q")],
        ).add_params(pick)
        layers = [circles]
        # v3.1: ticker labels on the bubbles (top 3 by |dev| only —
        # labeling all 10 would collide where bubbles cluster near 0,
        # especially on narrow screens; every bubble keeps its tooltip).
        top_lab = sorted(in_range, key=lambda p: p["absdev"],
                         reverse=True)[:3]
        layers.append(
            alt.Chart(pd.DataFrame([
                {"x": p["dev"], "depth": p["depth"], "label": p["ticker"]}
                for p in top_lab])).mark_text(
                size=11, fontWeight="bold", color="#16130F",
                dx=8, dy=-8).encode(
                x=alt.X("x:Q", scale=alt.Scale(domain=domain)),
                y=alt.Y("depth:Q", scale=alt.Scale(type="log")),
                text="label:N"))
        if offscale:
            for side, al, dx in (("pos", "right", -8), ("neg", "left", 8)):
                rows = []
                for p in offscale:
                    if (side == "pos") != (p["dev"] > 0):
                        continue
                    edge = CLAMP if p["dev"] > 0 else -CLAMP
                    rows.append({
                        "x": edge, "depth": p["depth"],
                        "label": f"{p['ticker']} "
                                 f"{fmt_dev(p['dev'], pct=True)} "
                                 f"{'→' if p['dev'] > 0 else '←'}",
                    })
                if rows:
                    layers.append(
                        alt.Chart(pd.DataFrame(rows)).mark_text(
                            color="#C2410C", fontWeight="bold", size=12,
                            align=al, dx=dx).encode(
                            x=alt.X("x:Q", scale=alt.Scale(domain=domain)),
                            y=alt.Y("depth:Q", scale=alt.Scale(type="log")),
                            text="label:N"))
        chart = layers[0]
        for extra in layers[1:]:
            chart = chart + extra
        st.altair_chart(chart.properties(height=380), width="stretch",
                        on_select="rerun", key="devmap")
        sel = st.session_state.get("devmap")
        chosen = None
        if isinstance(sel, dict):
            for v in (sel.get("selection") or {}).values():
                if (isinstance(v, list) and v
                        and isinstance(v[0], dict) and v[0].get("ticker")):
                    chosen = v[0]["ticker"]
                    break
        last = st.session_state.get("_map_last_sel")
        if chosen and chosen != last and chosen in latest:
            st.session_state["_map_last_sel"] = chosen
            st.session_state["page"] = "ticker"
            st.session_state["ticker_target"] = chosen
            try:
                st.query_params["ticker"] = chosen
            except Exception:
                pass
            st.rerun()
        if offscale:
            st.caption(t(lang, "map_clamp_note"))
    if nodata:
        st.markdown(f"**{t(lang, 'map_nodata_title')}**")
        st.markdown(t(lang, "map_nodata_note"))
        st.markdown(", ".join(sorted(nodata)))
    pcol, bcol = st.columns([3, 1], gap="small")
    with pcol:
        pick_ticker = st.selectbox(t(lang, "map_select"),
                                   sorted(latest.keys()), key="map_pick")
    with bcol:
        # Spacer matches the selectbox label height so the button sits
        # level with the input, not above it.
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button(t(lang, "map_open"), key="map_open_btn"):
            st.session_state["page"] = "ticker"
            st.session_state["ticker_target"] = pick_ticker
            try:
                st.query_params["ticker"] = pick_ticker
            except Exception:
                pass
            st.rerun()


def render_weekly_story(lang, latest):
    """v2 editorial weekly story — computed from data, never hand-written.

    Three factual lines: the week's largest |deviation| event, depth at
    the time, and where that ticker stands now — plus its 7-day chart.
    A calm week (no event >= 1%) is stated honestly first, with the
    week's largest sub-threshold event as context, not as a scare.
    """
    st.subheader(t(lang, "story_title"))
    top = get_weekly_top()
    if top is None:
        st.markdown(t(lang, "story_calm"))
        return
    dev = float(top["dev_vs_median_pct"])
    tid = top["ticker_id"]
    if abs(dev) < 1.0:
        st.markdown(t(lang, "story_calm"))
    st.markdown(t(lang, "story_event", ticker=tid, dev=fmt_dev(dev, pct=True),
                            time=fmt_wita(top["ts"], lang)))
    depth = top.get("qualifying_depth_usd")
    st.markdown(t(lang, "story_depth", depth=fmt_usd(depth)))
    now_dev = latest.get(tid, {}).get("dev_vs_median_pct")
    st.markdown(t(lang, "story_now", ticker=tid,
                            dev=fmt_dev(now_dev, pct=True)))
    # 7-day series is hourly-averaged by get_chart_series (hours > 24
    # branch). Plain Altair, deliberately NOT .interactive(): wheel
    # scrolling must move the page, never zoom the chart (audit).
    series = get_chart_series(tid, 168)
    if len(series) >= 2:
        sdf = pd.DataFrame(
            {"ts": pd.to_datetime([s[0] for s in series]),
             "dev": [s[1] for s in series]})
        schart = alt.Chart(sdf).mark_line(color="#C2410C").encode(
            x=alt.X("ts:T", title=None),
            y=alt.Y("dev:Q", title=t(lang, "dev_median")))
        st.altair_chart(schart, width="stretch")
        # v3.2 dynamic caption: the poller only started 24 Oct 19:11
        # WITA, so a fixed "last 7 days" overpromises while history is
        # shorter — the caption states the ACTUAL range + hours covered.
        first_ts = parse_ts(series[0][0])
        last_ts = parse_ts(series[-1][0])
        if first_ts is not None and last_ts is not None:
            hours = max(1, round((last_ts - first_ts).total_seconds() / 3600))
            st.caption(t(lang, "story_chart_range",
                         start=fmt_wita(series[0][0], lang),
                         end=fmt_wita(series[-1][0], lang), hours=hours))
        else:
            st.caption(t(lang, "story_chart"))


# ---------------------------------------------------------------- session
if "page" not in st.session_state:
    st.session_state.page = "home"
# Language is read from the persisted selectbox value BEFORE the widget
# is rendered, so nav labels switch in the same run as the toggle.
lang = "id" if st.session_state.get("lang_select", "EN") == "ID" else "en"
st.session_state.lang = lang

# v3.2 deep links: a table "Detail" link points at ?ticker=XXX. On a
# fresh session (full reload) with that param, route to the ticker
# page. The _qp_applied guard stops a stale param from yanking the
# user back after they navigate away with a nav button (nav buttons
# also clear the params). The read is guarded: AppTest / restricted
# runtimes without query-param support must never break the app.
try:
    _qp_ticker = st.query_params.get("ticker")
except Exception:
    _qp_ticker = None
if _qp_ticker and st.session_state.get("_qp_applied") != _qp_ticker:
    try:
        _qp_valid = {u["ticker_id"] for u in get_universe()}
    except Exception:
        _qp_valid = set()
    if _qp_ticker in _qp_valid:
        st.session_state.page = "ticker"
        st.session_state["ticker_select"] = _qp_ticker
        st.session_state["_qp_applied"] = _qp_ticker

# ---------------------------------------------------------------- header
# Header v3.1: wordmark + LIVE as ONE HTML block (tight, never stretched
# across the row the way three columns were). The language selectbox MUST
# stay a Streamlit widget — HTML cannot change session state without
# JavaScript, which is forbidden — so it sits in a narrow adjacent
# column; the 768px media query stacks header + language on narrow
# screens (wordmark on top, LIVE + language below it).
hdr_html, hdr_lang = st.columns([4, 1], gap="small")
with hdr_html:
    live_time = None
    try:
        _h = get_health(os.environ.get("RADAR_TEST_HEALTH_JSON", ""))
        _s = freshness_status(_h, datetime.now(timezone.utc))
        _dt = parse_ts(_s["last_ts"]) if _s["last_ts"] else None
        if _dt is not None:
            _w = _dt.astimezone(ZoneInfo("Asia/Makassar"))
            live_time = f"{_w.hour:02d}:{_w.minute:02d} WITA"
    except Exception:
        live_time = None
    _live_txt = (f'<span class="livedot"></span> {t(lang, "live_label")} · {live_time}'
                 if live_time else
                 f'<span class="livedot"></span> {t(lang, "live_label")}')
    st.markdown(f'<div class="radar-header"><span class="wordmark">{t(lang, "wordmark")}</span><span class="radar-live">{_live_txt}</span></div>',
                unsafe_allow_html=True)
with hdr_lang:
    st.selectbox(t(lang, "lang_label"), ["EN", "ID"],
                 index=0 if lang == "en" else 1, key="lang_select")
    # Re-derive: the widget state above already reflects the new choice
    # on the rerun triggered by the toggle, so `lang` is current.
st.markdown('<div class="header-rule"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- nav
# v3.2: four buttons (Methodology joins). The desktop shrink-wrap CSS
# sizes these columns to their buttons; the spacer takes the rest.
nav_c1, nav_c2, nav_c3, nav_c4, _nsp = st.columns([1, 1, 1, 1, 4],
                                                  gap="small")
with nav_c1:
    if st.button(t(lang, "nav_home"), key="nav_home_btn"):
        st.session_state.page = "home"
        try:
            st.query_params.clear()
        except Exception:
            pass
with nav_c2:
    if st.button(t(lang, "nav_ticker"), key="nav_ticker_btn"):
        st.session_state.page = "ticker"
        try:
            st.query_params.clear()
        except Exception:
            pass
with nav_c3:
    if st.button(t(lang, "nav_waitlist"), key="nav_waitlist_btn"):
        st.session_state.page = "waitlist"
        try:
            st.query_params.clear()
        except Exception:
            pass
with nav_c4:
    if st.button(t(lang, "nav_methodology"), key="nav_methodology_btn"):
        st.session_state.page = "methodology"
        try:
            st.query_params.clear()
        except Exception:
            pass
page = st.session_state.get("page", "home")

render_freshness(lang)
fcol, _ = st.columns([1, 4])
with fcol:
    if st.button(t(lang, "refresh_button"), key="refresh_btn"):
        # v3.2 refresh feedback (review: the button "felt broken"
        # because nothing visibly changed on a 5-minute cache cycle).
        # Capture the pre-clear cycle, clear, show "updating…" in this
        # run's output, then rerun: the run after shows whether data
        # actually advanced or was already latest (with the cycle
        # explanation) instead of silent nothing.
        try:
            _old_h = get_health(os.environ.get("RADAR_TEST_HEALTH_JSON", ""))
            _old_st = freshness_status(_old_h, datetime.now(timezone.utc))
            _old_ts = _old_st.get("last_ts")
        except Exception:
            _old_ts = None
        st.session_state["refresh_state"] = {"old": _old_ts}
        st.cache_data.clear()
        st.info(t(lang, "refresh_updating"))
        st.rerun()
# Result message for the run AFTER a refresh click (flag cleared after
# rendering, so it shows once and vanishes on the next rerun).
if st.session_state.get("refresh_state"):
    _rs = st.session_state.pop("refresh_state")
    try:
        _new_h = get_health(os.environ.get("RADAR_TEST_HEALTH_JSON", ""))
        _new_st = freshness_status(_new_h, datetime.now(timezone.utc))
        _new_ts = _new_st.get("last_ts")
    except Exception:
        _new_ts = None
    if _new_ts and _new_ts != _rs.get("old"):
        st.success(t(lang, "refresh_updated",
                     time=fmt_wita(_new_ts, lang)))
    else:
        st.info(t(lang, "refresh_latest",
                  time=fmt_wita(_new_ts, lang) if _new_ts else "—"))


# ---------------------------------------------------------------- home
@st.fragment(run_every=300)
def home_table_block(lang):
    """Home ticker table: auto-refreshes every 5 minutes (the poller
    cadence) WITHOUT resetting the user's sort/filter/window choices,
    because those widgets live inside the fragment. Row click navigates
    to the ticker page; the guard below fires only when the selection
    actually changes, so returning home never re-navigates by itself."""
    # Widget keys are language-scoped: Streamlit reuses a keyed widget's
    # rendered labels across reruns, so a bare key would keep showing the
    # previous language's formatted values after a toggle. Scoping the key
    # by lang forces fresh widgets (and fresh labels) on toggle, while
    # timer refreshes within one language keep the user's choices.
    # v3: the three filters share ONE row (not three stacked full-width
    # rows) and the table stores display strings, not raw floats — so
    # AppTest and the browser see exactly the same formatted values.
    f1, f2, f3 = st.columns(3, gap="small")
    with f1:
        sort_choice = st.selectbox(
            t(lang, "sort_label"), ["dev", "depth", "name"],
            format_func=lambda v: {"dev": t(lang, "sort_dev"),
                                   "depth": t(lang, "sort_depth"),
                                   "name": t(lang, "sort_name")}[v],
            key=f"home_sort_{lang}")
    with f2:
        tier_choice = st.selectbox(
            t(lang, "tier_filter"), ["all", "1", "2"],
            format_func=lambda v: t(lang, "tier_all") if v == "all"
            else f"{t(lang, 'meta_tier')} {v}",
            key=f"home_tier_{lang}")
    with f3:
        window_choice = st.selectbox(
            t(lang, "window_label"), [1, 24, 168],
            format_func=lambda v: {1: t(lang, "window_1h"),
                                   24: t(lang, "window_24h"),
                                   168: t(lang, "window_7d")}[v],
            key=f"home_window_{lang}")

    uni = {u["ticker_id"]: u for u in get_universe()}
    latest = get_latest_deviations()
    sparks = get_spark_data(window_choice)
    venues_all = get_all_venues_latest()
    issuers = sorted({u.get("issuer") for u in uni.values() if u.get("issuer")})
    red_map = {iss: get_redemption(iss) for iss in issuers}
    win_label = {1: "1h", 24: "24h", 168: "7d"}[window_choice]
    items = []
    for tid, d in latest.items():
        u = uni.get(tid, {})
        if tier_choice != "all" and str(u.get("tier")) != tier_choice:
            continue
        # Venue-best = deepest qualifying pool (ordered by reserve DESC
        # in get_all_venues_latest); spread needs the same venue list.
        vlist = [v for v in venues_all.get(tid, [])
                 if v.get("price_usd") is not None
                 and (v.get("reserve_usd") or 0) >= LIQ_MIN]
        best = vlist[0] if vlist else None
        dw = d.get("depth_weighted_price")
        spread = cross_venue_spread(vlist, dw)
        red = red_map.get(u.get("issuer"))
        red_status = (red.get("status") or "").lower() if red else ""
        series = sparks.get(tid, [])
        change_bps = ((series[-1] - series[0]) * 100.0
                      if len(series) >= 2 else None)
        dev = d.get("dev_vs_median_pct")
        bps = float(dev) * 100.0 if dev is not None else None
        status = ("—" if bps is None else
                  "alert" if abs(bps) > 100 else
                  "watch" if abs(bps) > 50 else "ok")
        items.append({
            "ticker": tid, "tier": u.get("tier"),
            "best_price": best.get("price_usd") if best else None,
            "best_dex": best.get("dex") if best else None,
            "dev": dev, "bps": bps, "spread": spread,
            "depth": d.get("qualifying_depth_usd"),
            "pools": d.get("pools_used"),
            "redemption": red_status,
            "change": change_bps, "status": status,
            "spark": series,
        })
    if sort_choice == "dev":
        items.sort(key=lambda r: abs(r["dev"]) if r["dev"] is not None else -1,
                   reverse=True)
    elif sort_choice == "depth":
        items.sort(key=lambda r: r["depth"] if r["depth"] is not None else -1,
                   reverse=True)
    else:
        items.sort(key=lambda r: r["ticker"])
    tickers = [r["ticker"] for r in items]
    if items:
        # No Updated column (v3): freshness already lives in the header
        # "Last updated" line — the column only repeated one identical
        # timestamp 13 times. None never renders as the string "None".
        # v3.2 columns: bps deviation (tint divisor 200, since 100 bps
        # = 1%), spread, Depth $10k + depth bar, redemption, PoR age
        # ("Not published" — no feed exists), published status, window
        # change (header carries the window), sparkline (blocks kept:
        # LineChartColumn renders empty cells blank for missing series,
        # losing v3's explicit dash — see B10 note), Detail link.
        _red_txt = {"open": t(lang, "red_status_open"),
                    "closed": t(lang, "red_status_closed"),
                    "gated": t(lang, "red_status_gated"),
                    "unknown": t(lang, "redemption_unknown")}
        _max_depth = max([r["depth"] for r in items
                          if r["depth"] is not None], default=0)
        df = pd.DataFrame([{
            t(lang, "col_ticker"): r["ticker"],
            t(lang, "col_tier"): (r["tier"] if r["tier"] is not None else "—"),
            t(lang, "col_best_price"): (
                f"{fmt_usd(r['best_price'])} ({r['best_dex']})"
                if r["best_price"] is not None else "—"),
            t(lang, "col_dev_bps"): (
                fmt_signed1(r["bps"]) if r["bps"] is not None else "—"),
            t(lang, "col_spread"): fmt_dev(r["spread"], pct=True),
            t(lang, "col_depth10k"): fmt_usd(r["depth"]),
            t(lang, "col_depth_bar"): (
                [float(r["depth"])] if r["depth"] is not None else []),
            t(lang, "redemption_title"): _red_txt.get(
                r["redemption"], t(lang, "redemption_unknown")),
            t(lang, "por_age_label"): t(lang, "por_not_published"),
            t(lang, "col_status"): (
                t(lang, "status_" + r["status"]) if r["status"] != "—"
                else "—"),
            t(lang, "col_change", window=win_label): (
                fmt_signed1(r["change"]) if r["change"] is not None else "—"),
            t(lang, "col_spark"): spark_text(r["spark"]),
            t(lang, "detail_link"): f"?ticker={r['ticker']}",
        } for r in items])
        styled = df.style.apply(
            lambda s: tint_dev(s, divisor=200.0),
            subset=[t(lang, "col_dev_bps")])
        # Wave 1: the two repeated missing-data label columns stay
        # visible (never deleted) but dimmed, so they no longer shout
        # as loud as real data. What is missing is summarized in the
        # coverage line under the headline (fix 3).
        styled = styled.set_properties(
            subset=[t(lang, "redemption_title"), t(lang, "por_age_label")],
            color="#8a8580")
        st.dataframe(
            styled,
            column_config={
                t(lang, "col_depth_bar"): st.column_config.BarChartColumn(
                    t(lang, "col_depth_bar"), y_min=0,
                    y_max=_max_depth if _max_depth else 1),
                t(lang, "detail_link"): st.column_config.LinkColumn(
                    t(lang, "detail_link"),
                    display_text=t(lang, "detail_link")),
            },
            selection_mode="single-row", on_select="rerun",
            key="home_table", width="stretch", hide_index=True)
        st.caption(t(lang, "home_table_note") if window_choice >= 24
                   else t(lang, "home_table_note_cycle"))
        st.caption(t(lang, "home_table_hint"))
        # v3.2 CSV export of the CURRENTLY DISPLAYED table (same
        # filter + sort order as the dataframe above), numeric values
        # for analysts (the on-screen table keeps display strings).
        _csv = pd.DataFrame([{
            "ticker": r["ticker"], "tier": r["tier"],
            "venue_best_price": r["best_price"],
            "venue_best_dex": r["best_dex"],
            "dev_bps": r["bps"], "spread_pct": r["spread"],
            "depth_usd": r["depth"],
            "redemption": r["redemption"],
            "por_age": t(lang, "por_not_published"),
            "status": r["status"],
            "change_bps": r["change"],
        } for r in items])
        st.download_button(t(lang, "download_csv"),
                           _csv.to_csv(index=False),
                           file_name="exit-radar.csv", mime="text/csv",
                           key=f"home_csv_{lang}")
        sel = st.session_state.get("home_table")
        rows_sel = []
        if isinstance(sel, dict):
            rows_sel = ((sel.get("selection") or {}).get("rows") or [])
        last_sel = st.session_state.get("_home_last_sel", [])
        if rows_sel and list(rows_sel) != list(last_sel):
            st.session_state["_home_last_sel"] = list(rows_sel)
            chosen = row_ticker(tickers, rows_sel[0])
            if chosen:
                st.session_state["page"] = "ticker"
                st.session_state["ticker_target"] = chosen
                try:
                    st.query_params["ticker"] = chosen
                except Exception:
                    pass
                st.rerun()
        elif not rows_sel:
            st.session_state["_home_last_sel"] = []
    else:
        st.markdown(t(lang, "no_data"))


if page == "home":
    st.markdown(f"**{t(lang, 'app_tagline')}**")
    st.markdown(t(lang, "landing_line"))
    # Wave 1: one honest coverage line directly under the headline —
    # what is live today vs what is not yet available. This is also
    # the summary for the dimmed missing-data columns (fix 4).
    st.markdown(t(lang, "coverage_live_line"))
    latest_home = get_latest_deviations()
    # v3.2: the KPI strip replaces the v2 pulse hero (same worst-deviation
    # content now lives in card 1, plus venues/PoR/redemption — no
    # duplicate hero number on the page).
    render_kpi_strip(lang, latest_home)
    render_dev_map(lang, latest_home)
    st.subheader(t(lang, "heatmap_title"))
    home_table_block(lang)
    render_comparison_bars(lang, latest_home)
    render_weekly_story(lang, latest_home)

    uni = {u["ticker_id"]: u for u in get_universe()}
    latest = get_latest_deviations()
    with_dev = [(tid, d) for tid, d in latest.items()
                if d.get("dev_vs_median_pct") is not None]
    with_depth = [(tid, d) for tid, d in latest.items()
                  if d.get("qualifying_depth_usd") is not None]
    # v3: identical structure in both columns (teal rule above BOTH
    # headings) so the two tables start at the same height — the audit's
    # single stray rule made the right column sit visibly lower.
    mcol, ncol = st.columns(2)
    with mcol:
        st.markdown('<div class="depth-rule"></div>', unsafe_allow_html=True)
        st.subheader(t(lang, "movers_title"))
        st.caption(t(lang, "movers_note"))
        movers = sorted(with_dev, key=lambda kv: abs(kv[1]["dev_vs_median_pct"]),
                        reverse=True)[:3]
        if movers:
            st.dataframe(pd.DataFrame([{
                t(lang, "col_ticker"): tid,
                t(lang, "col_dev"): fmt_dev(d["dev_vs_median_pct"]),
                t(lang, "col_depth"): fmt_usd(d.get("qualifying_depth_usd")),
            } for tid, d in movers]), width="stretch", hide_index=True)
        else:
            st.markdown(t(lang, "no_data"))
    with ncol:
        st.markdown('<div class="depth-rule"></div>', unsafe_allow_html=True)
        st.subheader(t(lang, "narrowest_title"))
        st.caption(t(lang, "narrowest_note"))
        narrow = sorted(with_depth,
                        key=lambda kv: kv[1]["qualifying_depth_usd"])[:3]
        if narrow:
            st.dataframe(pd.DataFrame([{
                t(lang, "col_ticker"): tid,
                t(lang, "col_dev"): fmt_dev(d.get("dev_vs_median_pct")),
                t(lang, "col_depth"): fmt_usd(d["qualifying_depth_usd"]),
            } for tid, d in narrow]), width="stretch", hide_index=True)
        else:
            st.markdown(t(lang, "no_data"))

    st.subheader(t(lang, "coverage_title"))
    st.info(t(lang, "coverage_text"))
    render_coming_soon(lang)

    if market_is_open(datetime.now(timezone.utc)):
        st.info(t(lang, "market_open"))
    else:
        # v3.2 market-status headline (review: a closed market with
        # trading tokens needs its expectation set in one line, before
        # the risk strip — not buried in it).
        st.info(t(lang, "market_closed_headline"))
        st.subheader(t(lang, "risk_strip_title"))
        issuers = sorted({u.get("issuer") for u in uni.values() if u.get("issuer")})
        red_map = {iss: get_redemption(iss) for iss in issuers}
        por_map = {iss: get_por(iss) for iss in issuers}
        scored = []
        for tid, d in latest.items():
            u = uni.get(tid, {})
            red = red_map.get(u.get("issuer"))
            por = por_map.get(u.get("issuer"))
            s = weekend_risk_score(
                d.get("dev_vs_median_pct"), d.get("qualifying_depth_usd"),
                red.get("status") if red else None,
                por.get("age_hours") if por else None)
            scored.append((tid, s))
        # Wave 1: rank ONLY tickers with >= 2 of 4 components. The
        # normalized score rescales a 1-component ticker to 100, so a
        # 1/4 ticker (live: METAx 74.0) topped the ranking — a
        # structurally misleading rank, not a labeling issue. Withheld
        # tickers are listed unranked below; their components still
        # display on their ticker pages (render_risk_breakdown).
        ranked = [kv for kv in scored
                  if kv[1]["components_present"] >= 2]
        unranked = [(tid, s["components_present"]) for tid, s in scored
                    if s["components_present"] < 2]
        ranked.sort(key=lambda kv: (kv[1]["score_100"] if kv[1]["score_100"] is not None else -1),
                    reverse=True)
        if ranked:
            # v3: excluded components show '—' in the cells; the
            # explanation lives in ONE footnote below, not repeated
            # across two columns six times (audit).
            def _comp(v):
                return f"{v:.1f}" if v is not None else "—"

            def _total(s):
                if s["score_100"] is None:
                    return "—"
                if s["partial"]:
                    return (f"{s['score_100']:.1f} "
                            f"({s['components_present']}/4)")
                return f"{s['score_100']:.1f}"
            st.dataframe(pd.DataFrame([{
                t(lang, "col_ticker"): tid,
                t(lang, "risk_total_100"): _total(s),
                t(lang, "risk_dev_label"): _comp(s["components"]["deviation"]),
                t(lang, "risk_depth_label"): _comp(s["components"]["depth"]),
                t(lang, "risk_red_label"): _comp(s["components"]["redemption"]),
                t(lang, "risk_por_label"): _comp(s["components"]["por"]),
            } for tid, s in ranked[:3]]), width="stretch", hide_index=True)
            _shown = ranked[:3]
            _partial = [(tid, s["components_present"])
                        for tid, s in _shown if s["partial"]]
            if _partial:
                st.caption(t(lang, "risk_partial_list",
                               items=", ".join(f"{tid} ({n}/4)"
                                               for tid, n in _partial)))
            if any(v is None for _, s in _shown
                   for v in s["components"].values()):
                st.caption(t(lang, "risk_footnote"))
            st.caption(t(lang, "risk_method"))
        if unranked:
            st.caption(t(lang, "risk_unranked",
                           items=", ".join(f"{tid} ({n}/4)"
                                           for tid, n in unranked)))
        if not scored:
            st.markdown(t(lang, "no_data"))

    if st.button(t(lang, "waitlist_cta"), key="home_cta_btn"):
        st.session_state.page = "waitlist"
        st.rerun()


# ---------------------------------------------------------------- ticker
elif page == "ticker":
    uni = get_universe()
    # v3.2 alphabetical dropdown (review: Tier 2 AAPLx/MSFTx sorted
    # last); tier is shown as a flag in the label, not via ordering.
    _tier_of = {u["ticker_id"]: u.get("tier") for u in uni}
    tickers = sorted(_tier_of.keys())
    if not tickers:
        st.markdown(t(lang, "no_data"))
    else:
        target = st.session_state.pop("ticker_target", None)
        if target in tickers:
            st.session_state["ticker_select"] = target
        ticker = st.selectbox(
            t(lang, "ticker_select"), tickers,
            format_func=lambda tid: (
                f"{tid} · {t(lang, 'meta_tier')} {_tier_of.get(tid)}"
                if _tier_of.get(tid) is not None else tid),
            key="ticker_select")
        # v3.2 stale-ticker guard (review: navigating tickers briefly
        # rendered the PREVIOUS ticker's numbers — for price data that
        # is a trust-fatal flash). Streamlit shows the previous run's
        # output until a new run completes, so the run that changes
        # tickers must do NO data reads: it renders only a spinner and
        # reruns. The stale window shrinks from "however long the data
        # reads take" to "one query-free run", and the first newly
        # rendered content is a spinner, never the old ticker's numbers.
        # (Zero stale frames are impossible in Streamlit's model — the
        # previous output always persists until a run completes — so
        # this minimizes, and de-stales, that window; it cannot erase
        # it entirely.)
        if ticker != st.session_state.get("_ticker_rendered"):
            st.session_state["_ticker_rendered"] = ticker
            with st.spinner(t(lang, "loading_ticker")):
                pass
            st.rerun()
        u = next(x for x in uni if x["ticker_id"] == ticker)
        latest = get_latest_deviations().get(ticker)
        st.header(f"{ticker} ({u.get('issuer')})")
        st.markdown(
            f"{t(lang, 'meta_underlying')}: {u.get('underlying')} · "
            f"{t(lang, 'meta_legal')}: {u.get('legal_type') or '—'} · "
            f"{t(lang, 'meta_tier')} {u.get('tier')} · "
            f"{t(lang, 'meta_coverage')}: DEX Solana"
        )
        st.info(t(lang, "coverage_short"))
        # 1-2. header + main deviation card
        st.subheader(t(lang, "block_dev"))
        venues = get_venue_latest(ticker)
        if latest:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric(t(lang, "dw_price"),
                          f"${latest['depth_weighted_price']:,.2f}"
                          if latest.get("depth_weighted_price") is not None else "—")
            with c2:
                dev = latest.get("dev_vs_median_pct")
                st.metric(t(lang, "dev_median"), fmt_dev(dev, pct=True))
            with c3:
                # v3.2 short metric value (review: "Awaiting
                # data-license res…" truncated in the metric); the full
                # explanation stays in close_note below.
                st.metric(t(lang, "dev_close"), t(lang, "close_pending_short"))
            st.info(t(lang, "close_note"))
            # v3 data-quality note: pools excluded from the deviation
            # calculation (unreasonable quotes). Defensive: absent when
            # the column is missing or the count is zero.
            excl = get_pools_excluded().get(ticker, 0)
            if excl and excl > 0:
                st.info(t(lang, "pools_excluded_note", n=excl))
        else:
            st.markdown(t(lang, "no_data"))
        # 3. deviation chart
        st.subheader(t(lang, "chart_title"))
        window = st.radio(
            t(lang, "chart_window"), ["24h", "7d", "30d"],
            format_func=lambda v: {"24h": t(lang, "chart_window_24h"),
                                   "7d": t(lang, "chart_window_7d"),
                                   "30d": t(lang, "chart_window_30d")}[v],
            horizontal=True, key="chart_window")
        hours = {"24h": 24, "7d": 168, "30d": 720}[window]
        series = get_chart_series(ticker, hours)
        # Plain Altair, deliberately NOT .interactive(): wheel scrolling
        # must move the page, never zoom the chart (audit).
        if len(series) >= 2:
            cdf = pd.DataFrame(
                {"ts": pd.to_datetime([s[0] for s in series]),
                 "dev": [s[1] for s in series]})
            cchart = alt.Chart(cdf).mark_line(color="#C2410C").encode(
                x=alt.X("ts:T", title=None),
                y=alt.Y("dev:Q", title=t(lang, "dev_median")))
            st.altair_chart(cchart, width="stretch")
        else:
            st.markdown(t(lang, "no_data"))
        st.caption(t(lang, "chart_note"))
        # 4. venue table
        st.subheader(t(lang, "venue_title"))
        if venues:
            vrows = []
            for v in venues:
                reserve = v.get("reserve_usd")
                status = (t(lang, "venue_status_ok") if reserve is not None
                          and reserve >= LIQ_MIN else t(lang, "venue_status_below"))
                pair = v.get("pair_address")
                vrows.append({
                    t(lang, "col_dex"): v.get("dex"),
                    t(lang, "col_chain"): v.get("chain"),
                    t(lang, "col_price_usd"): fmt_usd(v.get("price_usd")),
                    t(lang, "col_reserve"): fmt_usd(reserve),
                    t(lang, "col_vol"): fmt_usd(v.get("volume_24h_usd")),
                    t(lang, "col_status"): status,
                    t(lang, "col_updated"): fmt_wita(v.get("ts"), lang),
                    t(lang, "dex_link_label"): (
                        f"https://dexscreener.com/solana/{pair}" if pair else None),
                })
            st.dataframe(
                pd.DataFrame(vrows),
                column_config={
                    t(lang, "dex_link_label"): st.column_config.LinkColumn(
                        t(lang, "dex_link_label"),
                        display_text=t(lang, "dex_link_label")),
                },
                width="stretch", hide_index=True)
        else:
            st.markdown(t(lang, "no_data"))
        # 5. best exit venue by size (original 9-block structure, kept)
        st.markdown('<div class="depth-rule"></div>', unsafe_allow_html=True)
        st.subheader(t(lang, "exit_title"))
        exits = best_exit_venues(venues)
        if exits:
            erows = []
            for e in exits:
                erows.append({
                    t(lang, "col_size"): f"${e['size_usd']:,}",
                    t(lang, "col_venue"): f"{e['dex']} ({e['chain']})",
                    t(lang, "col_price_usd"): f"${e['price_usd']:,.2f}",
                    t(lang, "col_reserve"): f"${e['reserve_usd']:,.0f}",
                    t(lang, "col_note"): t(lang, "exit_flag") if e["depth_warning"] else "",
                })
            st.dataframe(pd.DataFrame(erows), width="stretch", hide_index=True)
        else:
            st.markdown(t(lang, "no_data"))
        st.caption(t(lang, "exit_note"))
        # 6. weekend risk (closed) OR market status + live spread (open)
        red = get_redemption(u.get("issuer"))
        por = get_por(u.get("issuer"))
        if market_is_open(datetime.now(timezone.utc)):
            st.subheader(t(lang, "market_title"))
            st.markdown(t(lang, "market_open"))
            dw = latest.get("depth_weighted_price") if latest else None
            spread = cross_venue_spread(venues, dw)
            st.metric(t(lang, "spread_label"), fmt_dev(spread, pct=True))
            st.caption(t(lang, "spread_note"))
        else:
            # v3.2 market-status headline on the ticker page too.
            st.info(t(lang, "market_closed_headline"))
            st.subheader(t(lang, "risk_title"))
            dev_med = latest.get("dev_vs_median_pct") if latest else None
            depth = latest.get("qualifying_depth_usd") if latest else None
            red_status = red.get("status") if red else None
            por_age = por.get("age_hours") if por else None
            if dev_med is None and depth is None:
                st.markdown(t(lang, "risk_unavailable"))
            else:
                render_risk_breakdown(
                    lang, weekend_risk_score(dev_med, depth, red_status, por_age))
        # 7. ticker alert log
        st.subheader(t(lang, "alertlog_title"))
        alerts = get_alerts(ticker)
        if alerts:
            type_map = {"spread": t(lang, "alert_type_spread"),
                        "redemption": t(lang, "alert_type_redemption"),
                        "por": t(lang, "alert_type_por"),
                        "close": t(lang, "alert_type_close")}
            arows = []
            for a in alerts:
                arows.append({
                    t(lang, "alert_col_time"): fmt_wita(a.get("alert_ts"), lang),
                    t(lang, "alert_col_type"): type_map.get(
                        (a.get("alert_type") or "").lower(),
                        a.get("alert_type") or "—"),
                    t(lang, "alert_col_threshold"): fmt_dev(a.get("threshold_pct")),
                    t(lang, "alert_col_dev"): fmt_dev(a.get("dev_at_alert_pct")),
                    t(lang, "alert_col_depth"): fmt_usd(a.get("depth_at_alert_usd")),
                    t(lang, "alert_col_message"): a.get("message_text") or "—",
                    t(lang, "alert_col_outcome"): a.get("outcome") or "—",
                })
            st.dataframe(pd.DataFrame(arows), width="stretch", hide_index=True)
        else:
            st.markdown(t(lang, "alertlog_empty"))
        # 8. redemption card
        st.subheader(t(lang, "redemption_title"))
        if red:
            _status_map = {"open": t(lang, "red_status_open"),
                           "closed": t(lang, "red_status_closed"),
                           "gated": t(lang, "red_status_gated"),
                           "unknown": t(lang, "redemption_unknown")}
            _raw_status = (red.get("status") or "").lower()
            _status_txt = _status_map.get(
                _raw_status,
                red.get("status") or t(lang, "redemption_unknown"))
            st.markdown(f"**{t(lang, 'col_status')}:** {_status_txt}")
            # v3.2 per-language note (review: EN mode leaked the
            # Indonesian note). EN uses the migrated window_note_en
            # column; when it is absent, NO note renders in EN mode —
            # falling back to the Indonesian text would reintroduce
            # the leak. The source line gets the same treatment: the
            # one known Indonesian source string is translated in
            # presentation (the DB row itself is read-only here);
            # unknown sources render as stored.
            _note = (red.get("window_note_en") if lang == "en"
                     else red.get("window_note"))
            if _note:
                st.markdown(_note)
            if (red.get("status") or "").lower() == "unknown":
                st.info(t(lang, "redemption_doc_note"))
            st.markdown(f"{t(lang, 'obs_label')}: {fmt_wita(red.get('observed_at'), lang)}")
            if red.get("source"):
                _src = red["source"]
                if lang == "en" and _src == (
                        "DESAIN §1.1 / riset 24 Okt (dokumentasi, "
                        "bukan observasi live)"):
                    _src = ("Design §1.1 / 24 Oct research "
                            "(documentation, not a live observation)")
                st.markdown(f"{t(lang, 'source_label')}: {_src}")
            if red.get("next_open_at"):
                st.markdown(f"{t(lang, 'next_open_label')}: "
                            f"{fmt_wita(red['next_open_at'], lang)}")
        else:
            st.markdown(t(lang, "redemption_unknown"))
        # 9. PoR card
        st.subheader(t(lang, "por_title"))
        if por:
            if por.get("age_hours") is not None:
                st.markdown(f"{t(lang, 'por_age_label')}: {por['age_hours']} h")
            else:
                st.markdown(t(lang, "por_none"))
            if por.get("last_update_ts"):
                st.markdown(f"{t(lang, 'por_last_label')}: "
                            f"{fmt_wita(por['last_update_ts'], lang)}")
            if por.get("feed_address"):
                st.markdown(f"{t(lang, 'por_feed_label')}: {por['feed_address']}")
            if por.get("reserves_vs_supply_note"):
                st.markdown(por["reserves_vs_supply_note"])
        else:
            st.markdown(t(lang, "por_none"))
        # 10. threshold simulator (historical simulation, not a prediction)
        st.subheader(t(lang, "sim_title"))
        st.markdown(t(lang, "sim_note"))
        thr = st.slider(t(lang, "sim_slider"), 0.5, 5.0, 1.0, 0.5,
                        format="%.1f%%", key="sim_slider")
        hist = get_sim_history(ticker)
        if hist:
            n_hit = sum(
                1 for r in hist
                if abs(float(r["dev_vs_median_pct"])) >= thr
                and (r.get("qualifying_depth_usd") or 0) >= DEPTH_FLOOR
                and (r.get("pools_used") or 0) >= 2)
            st.markdown(t(lang, "sim_result", threshold=f"{thr:.1f}",
                                n=n_hit, total=len(hist)))
        else:
            st.markdown(t(lang, "sim_no_data"))
        # 11. compare tickers (overlay, same chart window)
        st.subheader(t(lang, "compare_title"))
        st.markdown(t(lang, "compare_note"))
        others = sorted([x for x in tickers if x != ticker])
        chosen = st.multiselect(
            t(lang, "compare_select"), others,
            format_func=lambda tid: (
                f"{tid} · {t(lang, 'meta_tier')} {_tier_of.get(tid)}"
                if _tier_of.get(tid) is not None else tid),
            max_selections=2, key="compare_select")
        frames = []
        for name in [ticker] + list(chosen):
            pts = get_chart_series(name, hours)
            if pts:
                frames.append(pd.Series(
                    {pd.to_datetime(ts): v for ts, v in pts}, name=name))
        if frames:
            wide = pd.concat(frames, axis=1).sort_index()
            # Long form for one Altair overlay (plain, not interactive —
            # same wheel-scroll rule as every other chart here). NaNs
            # stay in place so lines break at gaps instead of bridging.
            long = wide.reset_index().melt(
                id_vars="index", var_name="ticker", value_name="dev")
            ochart = alt.Chart(long).mark_line().encode(
                x=alt.X("index:T", title=None),
                y=alt.Y("dev:Q", title=t(lang, "dev_median")),
                color=alt.Color("ticker:N", legend=alt.Legend(title=None)))
            st.altair_chart(ochart, width="stretch")
        else:
            st.markdown(t(lang, "no_data"))

# ---------------------------------------------------------------- waitlist
elif page == "waitlist":
    st.subheader(t(lang, "waitlist_title"))
    st.markdown(t(lang, "waitlist_intro"))
    # v3.2 privacy paragraph (review: "never sold, never shared" alone
    # is not a privacy note) + a real route to the Methodology page.
    st.markdown(t(lang, "waitlist_privacy"))
    if st.button(t(lang, "waitlist_methodology_btn"),
                 key="waitlist_methodology_btn"):
        st.session_state.page = "methodology"
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()
    with st.form("waitlist_form"):
        contact = st.text_input(t(lang, "f_contact"), key="wl_contact")
        position = st.selectbox(t(lang, "f_position"), SIZE_BUCKETS, key="wl_position")
        venues = st.text_input(t(lang, "f_venues"), key="wl_venues")
        price = st.text_input(t(lang, "f_price"), key="wl_price")
        consent = st.checkbox(t(lang, "f_consent"), key="wl_consent")
        submitted = st.form_submit_button(t(lang, "f_submit"), key="wl_submit")
    if submitted:
        if not contact.strip() or not venues.strip() or not consent:
            st.error(t(lang, "f_error"))
        else:
            try:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                insert_waitlist(contact, position, venues, price or None, now, 1)
                st.success(t(lang, "f_success"))
                st.markdown(t(lang, "f_success_detail"))
            except Exception as e:
                print(f"waitlist insert failed: {type(e).__name__}")
                st.error(t(lang, "f_error_save"))

# ---------------------------------------------------------------- methodology
elif page == "methodology":
    render_methodology(lang)

render_footer(lang)
