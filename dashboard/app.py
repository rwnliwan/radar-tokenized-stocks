"""Radar Tokenized Stocks — public dashboard (MVP, free forever).

Bilingual EN (default) + ID toggle in the header. All strings come from
i18n.py; all pure logic from logic.py / risk.py; all Turso access from
turso_read.py (SELECT-only reads + the single waitlist INSERT).

Test-only hook: env RADAR_TEST_HEALTH_JSON, when set to a JSON list of
{cycle_ts, cycles_ok} rows, replaces the live poller_health read so the
stale banner can be tested without touching production data. It is
off by default and documented in BUILD_LOG_FASE2.md.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st

from i18n import SIZE_BUCKETS, t
from logic import best_exit_venues, fmt_wita, freshness_status
from risk import weekend_risk_score
from turso_read import insert_waitlist, query

st.set_page_config(page_title="Radar Tokenized Stocks", layout="wide")

LIQ_MIN = 100000.0

# ---------------------------------------------------------------- header
col_title, col_lang = st.columns([4, 1])
with col_title:
    st.title("Radar Tokenized Stocks")
with col_lang:
    lang_choice = st.selectbox("Language / Bahasa", ["EN", "ID"], key="lang_select")
lang = "id" if lang_choice == "ID" else "en"

st.caption(t(lang, "app_tagline"))
st.markdown(t(lang, "landing_line"))

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


@st.cache_data(ttl=60)
def get_universe():
    return query(
        "SELECT ticker_id, underlying, issuer, legal_type, tier, status "
        "FROM universe ORDER BY tier, ticker_id"
    )


@st.cache_data(ttl=60)
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


@st.cache_data(ttl=60)
def get_ticker_history(ticker):
    return query(
        "SELECT ts, dev_vs_median_pct, depth_weighted_price FROM deviations "
        "WHERE ticker_id = ? ORDER BY ts ASC LIMIT 1000",
        [ticker],
    )


@st.cache_data(ttl=60)
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


@st.cache_data(ttl=60)
def get_redemption(issuer):
    rows = query(
        "SELECT issuer, asset, status, window_note, observed_at, source, "
        "next_open_at FROM redemption_windows WHERE issuer = ? "
        "ORDER BY observed_at DESC LIMIT 1",
        [issuer],
    )
    return rows[0] if rows else None


@st.cache_data(ttl=60)
def get_por(issuer):
    rows = query(
        "SELECT issuer, feed_address, last_update_ts, age_hours, "
        "reserves_vs_supply_note, checked_at FROM por_feeds WHERE issuer = ? "
        "ORDER BY checked_at DESC LIMIT 1",
        [issuer],
    )
    return rows[0] if rows else None


@st.cache_data(ttl=60)
def get_alerts(ticker):
    return query(
        "SELECT alert_ts, alert_type, threshold_pct, dev_at_alert_pct, "
        "depth_at_alert_usd, message_text, outcome FROM alert_log "
        "WHERE ticker_id = ? ORDER BY alert_ts DESC LIMIT 20",
        [ticker],
    )


def render_freshness():
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


def render_footer():
    st.markdown("---")
    st.subheader(t(lang, "policy_title"))
    st.markdown(t(lang, "policy_text").replace("\n", "\n\n"))
    st.subheader(t(lang, "donate_title"))
    st.markdown(t(lang, "donate_note"))
    st.caption(t(lang, "disclaimer"))
    st.caption(t(lang, "footer_note"))


# ---------------------------------------------------------------- nav
page = st.sidebar.radio(
    "Radar",
    [t(lang, "nav_home"), t(lang, "nav_ticker"), t(lang, "nav_waitlist")],
    key="nav",
)

render_freshness()

# ---------------------------------------------------------------- home
if page == t(lang, "nav_home"):
    st.subheader(t(lang, "coverage_title"))
    st.info(t(lang, "coverage_text"))
    st.subheader(t(lang, "heatmap_title"))
    st.caption(t(lang, "heatmap_note"))
    uni = {u["ticker_id"]: u for u in get_universe()}
    latest = get_latest_deviations()
    rows = []
    for tid, d in sorted(latest.items()):
        u = uni.get(tid, {})
        dev = d.get("dev_vs_median_pct")
        rows.append({
            t(lang, "col_ticker"): tid,
            t(lang, "col_tier"): u.get("tier"),
            t(lang, "col_price"): d.get("depth_weighted_price"),
            t(lang, "col_dev"): dev,
            t(lang, "col_depth"): d.get("qualifying_depth_usd"),
            t(lang, "col_pools"): d.get("pools_used"),
            t(lang, "col_updated"): fmt_wita(d.get("ts"), lang),
        })
    if rows:
        df = pd.DataFrame(rows)
        try:
            styled = df.style.background_gradient(
                subset=[t(lang, "col_dev")], cmap="coolwarm", vmin=-2, vmax=2
            ).format({
                t(lang, "col_price"): "${:.2f}",
                t(lang, "col_dev"): "{:+.2f}",
                t(lang, "col_depth"): "${:,.0f}",
            })
            st.dataframe(styled, width="stretch")
        except Exception:
            st.dataframe(df, width="stretch")
    else:
        st.markdown(t(lang, "no_data"))

# ---------------------------------------------------------------- ticker
elif page == t(lang, "nav_ticker"):
    uni = get_universe()
    tickers = [u["ticker_id"] for u in uni]
    if not tickers:
        st.markdown(t(lang, "no_data"))
    else:
        ticker = st.selectbox(t(lang, "ticker_select"), tickers, key="ticker_select")
        u = next(x for x in uni if x["ticker_id"] == ticker)
        latest = get_latest_deviations().get(ticker)
        st.header(f"{ticker} ({u.get('issuer')})")
        st.markdown(
            f"Underlying: {u.get('underlying')} · "
            f"Legal type: {u.get('legal_type') or '—'} · "
            f"Tier {u.get('tier')} · {t(lang, 'coverage_title')}: DEX Solana"
        )
        # 1-2. header + main deviation card
        st.subheader(t(lang, "block_dev"))
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
        hist = get_ticker_history(ticker)
        if len(hist) >= 2:
            hdf = pd.DataFrame([
                {"ts": pd.to_datetime(h["ts"]),
                 t(lang, "dev_median"): h.get("dev_vs_median_pct")}
                for h in hist if h.get("dev_vs_median_pct") is not None
            ])
            if len(hdf) >= 2:
                st.line_chart(hdf.set_index("ts"), width="stretch")
            else:
                st.markdown(t(lang, "no_data"))
        else:
            st.markdown(t(lang, "no_data"))
        st.caption(t(lang, "chart_note"))
        # 4. venue table
        st.subheader(t(lang, "venue_title"))
        venues = get_venue_latest(ticker)
        if venues:
            vrows = []
            for v in venues:
                reserve = v.get("reserve_usd")
                status = (t(lang, "venue_status_ok") if reserve is not None
                          and reserve >= LIQ_MIN else t(lang, "venue_status_below"))
                vrows.append({
                    "DEX": v.get("dex"), "Chain": v.get("chain"),
                    "Price": v.get("price_usd"), "Reserve": reserve,
                    "Vol 24h": v.get("volume_24h_usd"),
                    "Status": status,
                    "Updated": fmt_wita(v.get("ts"), lang),
                })
            st.dataframe(pd.DataFrame(vrows), width="stretch")
        else:
            st.markdown(t(lang, "no_data"))
        # 5. redemption card
        st.subheader(t(lang, "redemption_title"))
        red = get_redemption(u.get("issuer"))
        if red:
            st.markdown(f"**Status:** {red.get('status') or t(lang, 'redemption_unknown')}")
            if red.get("window_note"):
                st.markdown(red["window_note"])
            if (red.get("status") or "").lower() == "unknown":
                st.info(t(lang, "redemption_doc_note"))
            st.markdown(f"Observed: {fmt_wita(red.get('observed_at'), lang)}")
            if red.get("source"):
                st.markdown(f"Source: {red['source']}")
            if red.get("next_open_at"):
                st.markdown(f"Next open: {fmt_wita(red['next_open_at'], lang)}")
        else:
            st.markdown(t(lang, "redemption_unknown"))
        # 6. PoR card
        st.subheader(t(lang, "por_title"))
        por = get_por(u.get("issuer"))
        if por:
            st.markdown(f"Age: {por.get('age_hours')} h" if por.get("age_hours") is not None
                        else t(lang, "por_none"))
            if por.get("last_update_ts"):
                st.markdown(f"Last update: {fmt_wita(por['last_update_ts'], lang)}")
            if por.get("feed_address"):
                st.markdown(f"Feed: {por['feed_address']}")
            if por.get("reserves_vs_supply_note"):
                st.markdown(por["reserves_vs_supply_note"])
        else:
            st.markdown(t(lang, "por_none"))
        # 7. weekend risk score (computed for display; never written back)
        st.subheader(t(lang, "risk_title"))
        dev_med = latest.get("dev_vs_median_pct") if latest else None
        depth = latest.get("qualifying_depth_usd") if latest else None
        red_status = red.get("status") if red else None
        por_age = por.get("age_hours") if por else None
        score = weekend_risk_score(dev_med, depth, red_status, por_age)
        st.markdown(f"**{score['total']:.0f} / {score['max_possible']:.0f}** "
                    f"(method {score['method_version']})")
        comp = score["components"]
        st.markdown(
            f"deviation: {comp['deviation']} · depth: {comp['depth']} · "
            f"redemption: {comp['redemption']} · PoR: {comp['por']}"
        )
        if score["partial"]:
            st.info(t(lang, "risk_partial"))
        st.caption(t(lang, "risk_method"))
        # 8. best exit venue by size
        st.subheader(t(lang, "exit_title"))
        exits = best_exit_venues(venues)
        if exits:
            erows = []
            for e in exits:
                erows.append({
                    "Size": f"${e['size_usd']:,}",
                    "Venue": f"{e['dex']} ({e['chain']})",
                    "Price": f"${e['price_usd']:,.2f}",
                    "Reserve": f"${e['reserve_usd']:,.0f}",
                    "Note": t(lang, "exit_flag") if e["depth_warning"] else "",
                })
            st.dataframe(pd.DataFrame(erows), width="stretch")
        else:
            st.markdown(t(lang, "no_data"))
        st.caption(t(lang, "exit_note"))
        # 9. ticker alert log
        st.subheader(t(lang, "alertlog_title"))
        alerts = get_alerts(ticker)
        if alerts:
            st.dataframe(pd.DataFrame(alerts), width="stretch")
        else:
            st.markdown(t(lang, "alertlog_empty"))

# ---------------------------------------------------------------- waitlist
elif page == t(lang, "nav_waitlist"):
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
            except Exception as e:
                print(f"waitlist insert failed: {type(e).__name__}")
                st.error(t(lang, "f_error_save"))

render_footer()
