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
from logic import best_exit_venues, fmt_wita, freshness_status, parse_ts
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
  Menlo, monospace; font-size: clamp(44px, 7vw, 76px); font-weight: 500;
  line-height: 1.05; color: #C2410C; }
.depth-num { color: #0F766E; font-family: 'IBM Plex Mono', ui-monospace,
  SFMono-Regular, Menlo, monospace; }
.depth-rule { border-top: 3px solid #0F766E; margin: 10px 0 2px 0; }
div.stButton > button { border-color: #E5E0D8; color: #16130F;
  transition: border-color .2s ease, color .2s ease; }
div.stButton > button:hover { border-color: #C2410C; color: #C2410C; }
[data-testid="stMetricValue"] { font-size: 36px !important; }
@media (max-width: 640px) { .wordmark { font-size: 22px; } }
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
def get_spark_data(hours):
    """Hourly-average deviation per ticker over the window (sparkline fuel).

    Hourly buckets keep the read volume bounded (~168 points/ticker for
    7 days) instead of one row per 5-minute cycle.
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    rows = query(
        "SELECT strftime('%Y-%m-%dT%H:00:00Z', ts) AS ts, "
        "AVG(dev_vs_median_pct) AS dev FROM deviations "
        "WHERE ticker_id = ? AND ts >= ? "
        "AND dev_vs_median_pct IS NOT NULL GROUP BY ts ORDER BY ts ASC",
        [ticker, cutoff],
    )
    return [(r["ts"], float(r["dev"])) for r in rows if r.get("dev") is not None]


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
        "SELECT issuer, asset, status, window_note, observed_at, source, "
        "next_open_at FROM redemption_windows WHERE issuer = ? "
        "ORDER BY observed_at DESC LIMIT 1",
        [issuer],
    )
    return rows[0] if rows else None


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


def tint_dev(series):
    """Single-accent tint for the deviation column: burnt orange whose
    opacity scales with |deviation| (percent units), capped at 0.85."""
    out = []
    for v in series:
        try:
            a = min(abs(float(v)) / 2.0, 0.85)
        except (TypeError, ValueError):
            a = 0.0
        out.append(f"background-color: rgba(194, 65, 12, {a:.2f})"
                   if a > 0.02 else "")
    return out


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
    st.markdown("---")
    st.subheader(t(lang, "policy_title"))
    st.markdown(t(lang, "policy_text").replace("\n", "\n\n"))
    st.subheader(t(lang, "donate_title"))
    st.markdown(t(lang, "donate_note"))
    qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "donate_qr.png")
    if os.path.exists(qr_path):
        st.image(qr_path, width=220)
    st.code(DONATE_ADDRESS)
    st.markdown(f"[{t(lang, 'donate_pay_link')}]({DONATE_PAY_URL})")
    st.markdown(f"[{t(lang, 'linkedin_label')}]({LINKEDIN_URL})")
    st.caption(t(lang, "disclaimer"))
    st.caption(t(lang, "footer_note"))


def render_risk_breakdown(lang, score):
    """Weekend risk score with per-component values (experimental label
    lives in the section title key itself)."""
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
                     else f"{labels[k]}: {t(lang, 'risk_excluded')}")
    st.markdown(f"**{t(lang, 'risk_total_label')}: {score['total']:.1f} / "
                f"{score['max_possible']:.0f}** (method {score['method_version']})")
    st.markdown(" · ".join(parts))
    if score["partial"]:
        st.info(t(lang, "risk_partial"))
    st.caption(t(lang, "risk_method"))


def render_pulse(lang, latest):
    """v2 live pulse: largest current |deviation| as hero numbers.

    Uses the same latest-deviations dict as the table — never invented.
    Depth is shown in disciplined teal; the deviation hero stays orange.
    """
    st.subheader(t(lang, "pulse_title"))
    with_dev = [(tid, d) for tid, d in latest.items()
                if d.get("dev_vs_median_pct") is not None]
    if not with_dev:
        st.markdown(t(lang, "pulse_no_data"))
        return
    tid, d = max(with_dev, key=lambda kv: abs(kv[1]["dev_vs_median_pct"]))
    dev = float(d["dev_vs_median_pct"])
    st.markdown(f'<div class="hero-num">{dev:+.2f}%</div>',
                unsafe_allow_html=True)
    st.markdown(f"**{tid}** — {t(lang, 'pulse_biggest')}")
    depth = d.get("qualifying_depth_usd")
    pools = d.get("pools_used")
    st.markdown(
        f"{t(lang, 'col_depth')}: "
        f"<span class=\"depth-num\">${depth:,.2f}</span>"
        if depth is not None else
        f"{t(lang, 'col_depth')}: —",
        unsafe_allow_html=True)
    st.markdown(
        f"{pools} {t(lang, 'col_pools')} · "
        f"{t(lang, 'pulse_asof', time=fmt_wita(d.get('ts'), lang))}")


def render_dev_map(lang, latest):
    """v2 deviation map: Altair scatter (native, no custom JavaScript).

    x = deviation vs median (%), y = qualifying depth (log scale),
    bubble size = pools, color = |deviation| on the burnt-orange scale.
    HONESTY RULE: tickers with NULL deviation (single pool) are NEVER
    plotted at x=0 — that would fake a zero deviation. They appear as
    a dimmed list below with the reason stated. Bubble click navigates
    via Altair on_select with a change-guard (mirrors the table guard);
    the selectbox + button below is the guaranteed fallback.
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
        df = pd.DataFrame(plotted)
        pick = alt.selection_point(fields=["ticker"], name="pick")
        chart = alt.Chart(df).mark_circle().encode(
            x=alt.X("dev:Q", title=t(lang, "map_x")),
            y=alt.Y("depth:Q", scale=alt.Scale(type="log"),
                    title=t(lang, "map_y"),
                    axis=alt.Axis(titleColor="#0F766E")),
            size=alt.Size("pools:Q", title=t(lang, "col_pools"),
                          scale=alt.Scale(range=[60, 420])),
            color=alt.Color("absdev:Q",
                            scale=alt.Scale(range=["#FBE9DF", "#C2410C"]),
                            legend=None),
            tooltip=[alt.Tooltip("ticker:N"),
                     alt.Tooltip("dev:Q", format="+.2f"),
                     alt.Tooltip("depth:Q", format="$,.0f"),
                     alt.Tooltip("pools:Q")],
        ).properties(height=380).add_params(pick)
        st.altair_chart(chart, width="stretch",
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
            st.rerun()
    if nodata:
        st.markdown(f"**{t(lang, 'map_nodata_title')}**")
        st.markdown(t(lang, "map_nodata_note"))
        st.markdown(", ".join(sorted(nodata)))
    pick_ticker = st.selectbox(t(lang, "map_select"),
                               sorted(latest.keys()), key="map_pick")
    if st.button(t(lang, "map_open"), key="map_open_btn"):
        st.session_state["page"] = "ticker"
        st.session_state["ticker_target"] = pick_ticker
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
    st.markdown(t(lang, "story_event", ticker=tid, dev=f"{dev:+.2f}%",
                            time=fmt_wita(top["ts"], lang)))
    depth = top.get("qualifying_depth_usd")
    st.markdown(t(lang, "story_depth",
                        depth=f"${depth:,.2f}" if depth is not None else "—"))
    now_dev = latest.get(tid, {}).get("dev_vs_median_pct")
    st.markdown(t(lang, "story_now", ticker=tid,
                            dev=f"{now_dev:+.2f}%"
                            if now_dev is not None else "—"))
    series = get_chart_series(tid, 168)
    if len(series) >= 2:
        sdf = pd.DataFrame(
            {"ts": pd.to_datetime([s[0] for s in series]),
             t(lang, "dev_median"): [s[1] for s in series]}).set_index("ts")
        st.line_chart(sdf, width="stretch")
        st.caption(t(lang, "story_chart"))


# ---------------------------------------------------------------- session
if "page" not in st.session_state:
    st.session_state.page = "home"
# Language is read from the persisted selectbox value BEFORE the widget
# is rendered, so nav labels switch in the same run as the toggle.
lang = "id" if st.session_state.get("lang_select", "EN") == "ID" else "en"
st.session_state.lang = lang

# ---------------------------------------------------------------- header
col_word, col_live, col_lang = st.columns([2, 2, 1])
with col_word:
    st.markdown(f'<div class="wordmark">{t(lang, "wordmark")}</div>',
                unsafe_allow_html=True)
with col_live:
    live_time = None
    try:
        _h = get_health(os.environ.get("RADAR_TEST_HEALTH_JSON", ""))
        _s = freshness_status(_h, datetime.now(timezone.utc))
        _dt = parse_ts(_s["last_ts"]) if _s["last_ts"] else None
        if _dt is not None:
            _w = _dt.astimezone(ZoneInfo("Asia/Makassar"))
            live_time = f"{_w.hour:02d}:{_w.minute:02d} WITA"
    except Exception:
        live_time = None
    _live_txt = (f'<span class="livedot"></span> {t(lang, "live_label")} · {live_time}'
                 if live_time else
                 f'<span class="livedot"></span> {t(lang, "live_label")}')
    st.markdown(_live_txt, unsafe_allow_html=True)
with col_lang:
    st.selectbox(t(lang, "lang_label"), ["EN", "ID"],
                 index=0 if lang == "en" else 1, key="lang_select")
    # Re-derive: the widget state above already reflects the new choice
    # on the rerun triggered by the toggle, so `lang` is current.

# ---------------------------------------------------------------- nav
nav_c1, nav_c2, nav_c3 = st.columns(3)
with nav_c1:
    if st.button(t(lang, "nav_home"), key="nav_home_btn"):
        st.session_state.page = "home"
with nav_c2:
    if st.button(t(lang, "nav_ticker"), key="nav_ticker_btn"):
        st.session_state.page = "ticker"
with nav_c3:
    if st.button(t(lang, "nav_waitlist"), key="nav_waitlist_btn"):
        st.session_state.page = "waitlist"
page = st.session_state.get("page", "home")

render_freshness(lang)
fcol, _ = st.columns([1, 4])
with fcol:
    if st.button(t(lang, "refresh_button"), key="refresh_btn"):
        st.cache_data.clear()
        st.rerun()


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
    sort_choice = st.selectbox(
        t(lang, "sort_label"), ["dev", "depth", "name"],
        format_func=lambda v: {"dev": t(lang, "sort_dev"),
                               "depth": t(lang, "sort_depth"),
                               "name": t(lang, "sort_name")}[v],
        key=f"home_sort_{lang}")
    tier_choice = st.selectbox(
        t(lang, "tier_filter"), ["all", "1", "2"],
        format_func=lambda v: t(lang, "tier_all") if v == "all"
        else f"{t(lang, 'meta_tier')} {v}",
        key=f"home_tier_{lang}")
    window_choice = st.selectbox(
        t(lang, "window_label"), [24, 168],
        format_func=lambda v: t(lang, "window_24h") if v == 24
        else t(lang, "window_7d"),
        key=f"home_window_{lang}")

    uni = {u["ticker_id"]: u for u in get_universe()}
    latest = get_latest_deviations()
    sparks = get_spark_data(window_choice)
    items = []
    for tid, d in latest.items():
        u = uni.get(tid, {})
        if tier_choice != "all" and str(u.get("tier")) != tier_choice:
            continue
        items.append({
            "ticker": tid, "tier": u.get("tier"),
            "price": d.get("depth_weighted_price"),
            "dev": d.get("dev_vs_median_pct"),
            "depth": d.get("qualifying_depth_usd"),
            "pools": d.get("pools_used"),
            "spark": sparks.get(tid, []),
            "updated": fmt_wita(d.get("ts"), lang),
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
        df = pd.DataFrame([{
            t(lang, "col_ticker"): r["ticker"],
            t(lang, "col_tier"): r["tier"],
            t(lang, "col_price"): r["price"],
            t(lang, "col_dev"): r["dev"],
            t(lang, "col_depth"): r["depth"],
            t(lang, "col_pools"): r["pools"],
            t(lang, "col_spark"): r["spark"],
            t(lang, "col_updated"): r["updated"],
        } for r in items])
        styled = df.style.apply(tint_dev, subset=[t(lang, "col_dev")])
        st.dataframe(
            styled,
            column_config={
                t(lang, "col_ticker"): st.column_config.TextColumn(t(lang, "col_ticker")),
                t(lang, "col_price"): st.column_config.NumberColumn(t(lang, "col_price"), format="$%.2f"),
                t(lang, "col_dev"): st.column_config.NumberColumn(t(lang, "col_dev"), format="%+.2f"),
                t(lang, "col_depth"): st.column_config.NumberColumn(t(lang, "col_depth"), format="$%.2f"),
                t(lang, "col_pools"): st.column_config.NumberColumn(t(lang, "col_pools"), format="%d"),
                t(lang, "col_spark"): st.column_config.LineChartColumn(t(lang, "col_spark")),
                t(lang, "col_updated"): st.column_config.TextColumn(t(lang, "col_updated")),
            },
            selection_mode="single-row", on_select="rerun",
            key="home_table", width="stretch", hide_index=True)
        st.caption(t(lang, "home_table_note"))
        st.caption(t(lang, "home_table_hint"))
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
                st.rerun()
        elif not rows_sel:
            st.session_state["_home_last_sel"] = []
    else:
        st.markdown(t(lang, "no_data"))


if page == "home":
    st.markdown(f"**{t(lang, 'app_tagline')}**")
    st.markdown(t(lang, "landing_line"))
    latest_home = get_latest_deviations()
    render_pulse(lang, latest_home)
    render_dev_map(lang, latest_home)
    st.subheader(t(lang, "heatmap_title"))
    home_table_block(lang)
    render_weekly_story(lang, latest_home)

    uni = {u["ticker_id"]: u for u in get_universe()}
    latest = get_latest_deviations()
    with_dev = [(tid, d) for tid, d in latest.items()
                if d.get("dev_vs_median_pct") is not None]
    with_depth = [(tid, d) for tid, d in latest.items()
                  if d.get("qualifying_depth_usd") is not None]
    mcol, ncol = st.columns(2)
    with mcol:
        st.subheader(t(lang, "movers_title"))
        st.caption(t(lang, "movers_note"))
        movers = sorted(with_dev, key=lambda kv: abs(kv[1]["dev_vs_median_pct"]),
                        reverse=True)[:3]
        if movers:
            st.dataframe(pd.DataFrame([{
                t(lang, "col_ticker"): tid,
                t(lang, "col_dev"): d["dev_vs_median_pct"],
                t(lang, "col_depth"): d.get("qualifying_depth_usd"),
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
                t(lang, "col_dev"): d.get("dev_vs_median_pct"),
                t(lang, "col_depth"): d["qualifying_depth_usd"],
            } for tid, d in narrow]), width="stretch", hide_index=True)
        else:
            st.markdown(t(lang, "no_data"))

    st.subheader(t(lang, "coverage_title"))
    st.info(t(lang, "coverage_text"))
    st.caption(t(lang, "coverage_short"))

    if market_is_open(datetime.now(timezone.utc)):
        st.info(t(lang, "market_open"))
    else:
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
        scored.sort(key=lambda kv: kv[1]["total"], reverse=True)
        if scored:
            def _comp(v):
                return f"{v:.1f}" if v is not None else t(lang, "risk_excluded")
            st.dataframe(pd.DataFrame([{
                t(lang, "col_ticker"): tid,
                t(lang, "risk_total_label"): f"{s['total']:.1f} / {s['max_possible']:.0f}",
                t(lang, "risk_dev_label"): _comp(s["components"]["deviation"]),
                t(lang, "risk_depth_label"): _comp(s["components"]["depth"]),
                t(lang, "risk_red_label"): _comp(s["components"]["redemption"]),
                t(lang, "risk_por_label"): _comp(s["components"]["por"]),
            } for tid, s in scored[:3]]), width="stretch", hide_index=True)
            st.caption(t(lang, "risk_method"))
        else:
            st.markdown(t(lang, "no_data"))

    if st.button(t(lang, "waitlist_cta"), key="home_cta_btn"):
        st.session_state.page = "waitlist"
        st.rerun()


# ---------------------------------------------------------------- ticker
elif page == "ticker":
    uni = get_universe()
    tickers = [u["ticker_id"] for u in uni]
    if not tickers:
        st.markdown(t(lang, "no_data"))
    else:
        target = st.session_state.pop("ticker_target", None)
        if target in tickers:
            st.session_state["ticker_select"] = target
        ticker = st.selectbox(t(lang, "ticker_select"), tickers,
                              key="ticker_select")
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
                st.metric(t(lang, "dev_median"),
                          f"{dev:+.2f}%" if dev is not None else "—")
            with c3:
                st.metric(t(lang, "dev_close"), t(lang, "close_pending"))
            st.info(t(lang, "close_note"))
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
        if len(series) >= 2:
            cdf = pd.DataFrame(
                {"ts": pd.to_datetime([s[0] for s in series]),
                 t(lang, "dev_median"): [s[1] for s in series]}).set_index("ts")
            st.line_chart(cdf, width="stretch")
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
                    t(lang, "col_price_usd"): v.get("price_usd"),
                    t(lang, "col_reserve"): reserve,
                    t(lang, "col_vol"): v.get("volume_24h_usd"),
                    t(lang, "col_status"): status,
                    t(lang, "col_updated"): fmt_wita(v.get("ts"), lang),
                    t(lang, "dex_link_label"): (
                        f"https://dexscreener.com/solana/{pair}" if pair else None),
                })
            st.dataframe(
                pd.DataFrame(vrows),
                column_config={
                    t(lang, "col_price_usd"): st.column_config.NumberColumn(
                        t(lang, "col_price_usd"), format="$%.2f"),
                    t(lang, "col_reserve"): st.column_config.NumberColumn(
                        t(lang, "col_reserve"), format="$%.2f"),
                    t(lang, "col_vol"): st.column_config.NumberColumn(
                        t(lang, "col_vol"), format="$%.2f"),
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
            st.metric(t(lang, "spread_label"),
                      f"{spread:+.2f}%" if spread is not None else "—")
            st.caption(t(lang, "spread_note"))
        else:
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
                    t(lang, "alert_col_threshold"): a.get("threshold_pct"),
                    t(lang, "alert_col_dev"): a.get("dev_at_alert_pct"),
                    t(lang, "alert_col_depth"): a.get("depth_at_alert_usd"),
                    t(lang, "alert_col_message"): a.get("message_text"),
                    t(lang, "alert_col_outcome"): a.get("outcome"),
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
            if red.get("window_note"):
                st.markdown(red["window_note"])
            if (red.get("status") or "").lower() == "unknown":
                st.info(t(lang, "redemption_doc_note"))
            st.markdown(f"{t(lang, 'obs_label')}: {fmt_wita(red.get('observed_at'), lang)}")
            if red.get("source"):
                st.markdown(f"{t(lang, 'source_label')}: {red['source']}")
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
        others = [x for x in tickers if x != ticker]
        chosen = st.multiselect(t(lang, "compare_select"), others,
                                max_selections=2, key="compare_select")
        frames = []
        for name in [ticker] + list(chosen):
            pts = get_chart_series(name, hours)
            if pts:
                frames.append(pd.Series(
                    {pd.to_datetime(ts): v for ts, v in pts}, name=name))
        if frames:
            wide = pd.concat(frames, axis=1).sort_index()
            st.line_chart(wide, width="stretch")
        else:
            st.markdown(t(lang, "no_data"))

# ---------------------------------------------------------------- waitlist
elif page == "waitlist":
    st.subheader(t(lang, "waitlist_title"))
    st.markdown(t(lang, "waitlist_intro"))
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

render_footer(lang)
