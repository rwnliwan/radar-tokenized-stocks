"""Streamlit AppTest: language toggle on 2 pages + stale banner.

Runs the real app.py headlessly (live Turso reads, no writes):
1. Default run is English (wordmark, tagline, coverage header).
2. Language selectbox -> ID: Indonesian strings appear.
3. Ticker page in ID: Indonesian block labels appear.
4. Waitlist page renders the form (labels only — NEVER submitted,
   so no production row is written).
5. Stale banner: appears with a stale RADAR_TEST_HEALTH_JSON
   override, absent with a fresh override.
6. Live run: stale banner absent only if live health is actually
   fresh; otherwise that assertion is skipped with a printed note
   (live conditions must not fail the suite).

Modernized 2026-10-25 for the v3.2 UI: the app has no st.title
(the title lives only in set_page_config, which AppTest's title
collection does not expose), so the default-render assertion checks
the rendered wordmark instead; navigation uses the nav buttons
(nav_home_btn / nav_ticker_btn / nav_waitlist_btn /
nav_methodology_btn), not the old nav radio.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
os.chdir(ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402


def all_text(at):
    parts = []
    for coll in (at.title, at.header, at.subheader, at.markdown, at.caption,
                 at.info, at.warning, at.success, at.error):
        try:
            for el in coll:
                v = getattr(el, "value", None)
                if v:
                    parts.append(str(v))
        except Exception:
            pass
    # Widget labels live on the widgets themselves, not in markdown.
    for coll in (at.text_input, at.selectbox, at.checkbox, at.radio, at.button):
        try:
            for el in coll:
                label = getattr(el, "label", None)
                if label:
                    parts.append(str(label))
        except Exception:
            pass
    return "\n".join(parts)


def fresh_app():
    os.environ.pop("RADAR_TEST_HEALTH_JSON", None)
    return AppTest.from_file(os.path.join(ROOT, "dashboard/app.py"), default_timeout=180)


def main():
    # 1. Default EN run.
    at = fresh_app()
    at.run()
    assert not at.exception, f"app raised: {at.exception}"
    txt = all_text(at)
    # No st.title in the app: the title lives only in
    # set_page_config(page_title=...), which AppTest's title
    # collection does not expose. The observable equivalent is the
    # rendered wordmark header (present on every page).
    assert "EXIT RADAR" in txt
    assert "Deviation & redemption radar" in txt
    assert "DEX coverage" in txt
    # 6. Live freshness assertion (conditional on live reality).
    from turso_read import query
    live = query("SELECT cycle_ts, cycles_ok FROM poller_health "
                 "ORDER BY id DESC LIMIT 2")
    live_fresh = False
    if live:
        last = datetime.fromisoformat(live[0]["cycle_ts"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - last).total_seconds() / 60
        failed = sum(1 for r in live if int(r["cycles_ok"] or 0) == 0)
        live_fresh = age <= 15 and failed < 2
    if live_fresh:
        assert "Data may be stale" not in txt, "stale banner on fresh live data"
        print("live freshness: fresh, no banner (as expected)")
    else:
        print("live freshness: NOT fresh at test time — banner assertion skipped")
    # 2. Toggle to ID (Home page).
    at.selectbox(key="lang_select").set_value("ID")
    at.run()
    assert not at.exception, f"app raised after lang switch: {at.exception}"
    txt = all_text(at)
    assert "Radar deviasi & redemption" in txt
    assert "Cakupan DEX" in txt
    # 3. Ticker page in ID (v3.2+: nav is buttons, not a radio;
    # clicking sets session_state.page and the same run renders it).
    at.button(key="nav_ticker_btn").click()
    at.run()
    assert not at.exception, f"app raised on ticker page: {at.exception}"
    at.selectbox(key="ticker_select").set_value("TSLAx")
    at.run()
    assert not at.exception, f"app raised on TSLAx: {at.exception}"
    txt = all_text(at)
    assert "Deviasi utama" in txt
    assert "Skor risiko akhir pekan (eksperimental)" in txt
    # 4. Waitlist page renders the form (never submitted).
    at.button(key="nav_waitlist_btn").click()
    at.run()
    assert not at.exception, f"app raised on waitlist page: {at.exception}"
    txt = all_text(at)
    assert "Kontak (Telegram atau email)" in txt
    assert "Gabung daftar tunggu" in txt
    # 5a. Stale override -> banner appears.
    now = datetime.now(timezone.utc)
    stale = [{"cycle_ts": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "cycles_ok": 1}]
    os.environ["RADAR_TEST_HEALTH_JSON"] = json.dumps(stale)
    at2 = AppTest.from_file(os.path.join(ROOT, "dashboard/app.py"), default_timeout=180)
    at2.run()
    assert not at2.exception, f"app raised (stale override): {at2.exception}"
    assert "Data may be stale" in all_text(at2), "stale banner missing on stale override"
    # 5b. Fresh override -> banner absent.
    fresh = [{"cycle_ts": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "cycles_ok": 1}]
    os.environ["RADAR_TEST_HEALTH_JSON"] = json.dumps(fresh)
    at3 = AppTest.from_file(os.path.join(ROOT, "dashboard/app.py"), default_timeout=180)
    at3.run()
    assert not at3.exception, f"app raised (fresh override): {at3.exception}"
    assert "Data may be stale" not in all_text(at3), "stale banner on fresh override"
    os.environ.pop("RADAR_TEST_HEALTH_JSON", None)
    print("APPTEST: PASS (EN default, ID toggle, ticker page, waitlist render, "
          "stale banner on/off)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
