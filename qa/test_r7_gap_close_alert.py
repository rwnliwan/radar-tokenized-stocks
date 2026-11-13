"""Round-7 GAP test: advance redemption-close alert (gap R7 #2).

The bot used to document that it lacked the close-time field needed
for the design's "closing within 24h" rule, and closes_within_24h was
only ever True in the synthetic dry-run scenario — load_live_tickers
never set it. Gap R7 is now BUILT (2026-11-09): the close-time is
DERIVED from the same official 24/5 schedule + NYSE calendar that
already drives the live redemption status
(next_schedule_close_utc: 00:00 ET ending the last NYSE business day
before a weekend / NYSE holiday). No new external source is invented;
the close carries the same schedule-derived honesty label as the
status itself.

- (A) next_schedule_close_utc / closes_within_24h (bot): Friday ->
  Saturday 00:00 ET; day-before-holiday -> 00:00 ET of the holiday;
  Thursday -> still >24h away; the 24h boundary is inclusive (Friday
  00:00 ET exactly = 24h -> True).
- (B) bot and poller helpers agree on a battery of dates (same
  pattern as the S11 holiday-set identity guard — the two copies must
  never drift apart).
- (C) evaluate_alerts: open + closes-soon -> exactly one
  'redemption_closing_soon' alert; open + not-soon -> none; closed /
  paused -> only the closed/paused alert, never a closing-soon one;
  a dev-stale ticker still gets the advance alert (redemption alerts
  do not depend on the dev row, fix ronde 8 S3) with no stale price.
- (D) format_alert EN + ID: shows the formatted close instant and
  the schedule-derived note; missing next_close_at falls back to the
  bare "within 24h" text, never a fabricated time.
- (E) Dedup is the standard 24h per-channel rule (NOT once-per-window:
  no window exists yet), so the advance alert can never suppress the
  later closed-window 'redemption' alert (different alert type).
- (F) load_live_tickers (stubbed DB): the live path actually populates
  closes_within_24h / next_close_at — True on a Friday, False on a
  Monday, None/False when already closed.
- (G) Honest labels stay on web + dashboard (methodology_thresholds
  EN + ID), the alert-history type is labelled on both surfaces, the
  old "cannot be computed live yet" docstring claim is gone, and the
  GATE doc records the build.
- (H) --dry-run shows the new scenario.

Pure + stubbed-DB only: no network, no token, no Telegram send, no
production reads/writes. Run: python3 qa/test_r7_gap_close_alert.py
(exit 0 = PASS).
"""
import io
import os
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
sys.path.insert(0, ROOT)
import bot  # noqa: E402  (token is lazy; import touches no vault/DB)

FAILURES = []
UTC = timezone.utc


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def base_ticker(status="open", closes=False, next_close=None, dev_stale=False):
    d = {
        "ticker": "SPYx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 500.10, "reserve": 3000000.0}],
        "dw": 500.10, "dev_med": 0.10, "depth": 3000000.0,
        "pools_used": 1, "median": 500.10,
        "redemption_status": status,
        "next_open_at": None, "closes_within_24h": closes,
        "next_close_at": next_close, "por_age_hours": 6.0,
    }
    if dev_stale:
        d["dev_stale"] = True
    return d


def main():
    # ================================================================
    # (A) Close helper (bot)
    # ================================================================
    check("A close Fri Nov 6 -> Sat 00:00 ET (05:00Z)",
          bot.next_schedule_close_utc(dt("2026-11-06T12:00:00Z")) == "2026-11-07T05:00:00Z")
    check("A close Thu Nov 5 -> Sat 00:00 ET",
          bot.next_schedule_close_utc(dt("2026-11-05T12:00:00Z")) == "2026-11-07T05:00:00Z")
    check("A close Wed before Thanksgiving -> Thu 00:00 ET",
          bot.next_schedule_close_utc(dt("2026-11-25T12:00:00Z")) == "2026-11-26T05:00:00Z")
    check("A close Thu before Good Friday -> Fri 00:00 ET",
          bot.next_schedule_close_utc(dt("2026-04-02T12:00:00Z")) == "2026-04-03T04:00:00Z")
    check("A close Mon Oct 26 -> Sat 00:00 ET (EDT)",
          bot.next_schedule_close_utc(dt("2026-10-26T12:00:00Z")) == "2026-10-31T04:00:00Z")
    check("A within: Fri 12:00 UTC (07:00 ET) -> True (17h to close)",
          bot.closes_within_24h(dt("2026-11-06T12:00:00Z")) is True)
    check("A within: Fri 00:00 ET exactly -> True (boundary, 24h inclusive)",
          bot.closes_within_24h(dt("2026-11-06T05:00:00Z")) is True)
    check("A within: Fri 23:00 ET -> True (1h to close)",
          bot.closes_within_24h(dt("2026-11-07T04:00:00Z")) is True)
    check("A within: Thu 23:00 ET -> False (25h to close)",
          bot.closes_within_24h(dt("2026-11-06T04:00:00Z")) is False)
    check("A within: Mon midday -> False (days to close)",
          bot.closes_within_24h(dt("2026-11-09T12:00:00Z")) is False)
    check("A within: Wed before Thanksgiving midday -> True",
          bot.closes_within_24h(dt("2026-11-25T12:00:00Z")) is True)
    check("A within: Sat (already closed) -> False, never True on stale close",
          bot.closes_within_24h(dt("2026-11-07T12:00:00Z")) is False)

    # ================================================================
    # (B) bot vs poller agreement
    # ================================================================
    try:
        import poller  # noqa: E402
        battery = [
            "2026-10-24T12:00:00Z", "2026-10-26T12:00:00Z",
            "2026-11-05T12:00:00Z", "2026-11-06T12:00:00Z",
            "2026-11-06T05:00:00Z", "2026-11-07T04:00:00Z",
            "2026-11-09T12:00:00Z", "2026-11-25T12:00:00Z",
            "2026-04-02T12:00:00Z", "2026-12-24T12:00:00Z",
            "2026-12-25T12:00:00Z", "2027-07-02T12:00:00Z",
            "2028-01-17T12:00:00Z",
        ]
        agree = all(
            bot.next_schedule_close_utc(dt(x)) == poller.next_schedule_close_utc(dt(x))
            for x in battery)
        check("B bot/poller next_schedule_close_utc agree (13 dates)",
              agree)
        check("B bot/poller holiday sets identical",
              bot.NYSE_HOLIDAYS == poller.NYSE_HOLIDAYS)
    except Exception as e:
        check(f"B poller import/agreement (raised {type(e).__name__}: {e})", False)

    # ================================================================
    # (C) evaluate_alerts
    # ================================================================
    a = bot.evaluate_alerts(
        [base_ticker("open", True, "2026-11-07T05:00:00Z")], False)
    check("C open+soon: exactly one closing_soon alert",
          len(a) == 1 and a[0]["type"] == "redemption_closing_soon",
          f"got={[x['type'] for x in a]}")
    check("C open+soon: next_close_at preserved",
          a and a[0].get("next_close_at") == "2026-11-07T05:00:00Z")
    check("C open+soon: closes_within_24h carried True",
          a and a[0].get("closes_within_24h") is True)
    check("C open+not-soon: no alert",
          bot.evaluate_alerts([base_ticker("open", False, None)], False) == [])
    check("C closed+soon-flag: redemption only, no closing_soon",
          [x["type"] for x in bot.evaluate_alerts(
              [base_ticker("closed", True, None)], False)] == ["redemption"])
    check("C paused: redemption_paused only, no closing_soon",
          [x["type"] for x in bot.evaluate_alerts(
              [base_ticker("paused", True, None)], False)] == ["redemption_paused"])
    check("C gated: redemption only, no closing_soon",
          [x["type"] for x in bot.evaluate_alerts(
              [base_ticker("gated", True, None)], False)] == ["redemption"])
    stale = bot.evaluate_alerts(
        [base_ticker("open", True, "2026-11-07T05:00:00Z", dev_stale=True)], False)
    check("C dev-stale ticker still gets closing_soon (no dev dependency)",
          len(stale) == 1 and stale[0]["type"] == "redemption_closing_soon")
    check("C dev-stale closing_soon carries no stale price/depth",
          stale and stale[0].get("dw") is None and stale[0].get("depth") is None)
    both = bot.evaluate_alerts(
        [dict(base_ticker("open", True, "2026-11-07T05:00:00Z"), dev_med=3.5)], False)
    check("C dev-high + closing-soon are independent alerts",
          sorted(x["type"] for x in both) == ["deviation_high", "redemption_closing_soon"],
          f"got={[x['type'] for x in both]}")

    # ================================================================
    # (D) format_alert EN + ID
    # ================================================================
    alert = {"type": "redemption_closing_soon", "ticker": "SPYx",
             "issuer": "xStocks", "status": "open",
             "next_close_at": "2026-11-07T05:00:00Z",
             "closes_within_24h": True,
             "dw": 500.10, "depth": 3000000.0, "pools_used": 1}
    en = bot.format_alert(alert, "en")
    check("D EN: head names closing soon",
          "REDEMPTION CLOSING SOON" in en)
    check("D EN: close instant formatted (Sat 07 Nov 2026, 13:00 WITA)",
          "Sat 07 Nov 2026, 13:00 WITA" in en, f"got={en!r}")
    check("D EN: schedule-derived honesty note present",
          "schedule" in en.lower() and "not confirmed live by the issuer" in en)
    check("D EN: says within 24h, never claims issuer confirmation",
          "within 24h" in en and "issuer-confirmed" not in en)
    idn = bot.format_alert(alert, "id")
    check("D ID: head names closing soon",
          "REDEMPTION SEGERA TUTUP" in idn)
    check("D ID: close instant formatted (Sab 07 Nov 2026, 13:00 WITA)",
          "Sab 07 Nov 2026, 13:00 WITA" in idn, f"got={idn!r}")
    check("D ID: schedule-derived honesty note present",
          "jadwal resmi 24/5" in idn and "bukan konfirmasi live dari issuer" in idn)
    no_close = dict(alert, next_close_at=None)
    check("D EN fallback: missing close -> bare 'within 24h', no invented time",
          "within 24h" in bot.format_alert(no_close, "en")
          and "2026" not in bot.format_alert(no_close, "en"))
    check("D ID fallback: missing close -> bare 'dalam 24 jam'",
          "dalam 24 jam" in bot.format_alert(no_close, "id"))

    # ================================================================
    # (E) Dedup: standard 24h per-channel, NOT once-per-window
    # ================================================================
    check("E closing_soon is NOT a once-per-window type",
          "redemption_closing_soon" not in bot.REDEMPTION_WINDOW_STATUSES)
    orig_recent = bot.recent_alert_exists
    orig_fb = bot._fallback_suppressed
    try:
        bot._fallback_suppressed = lambda alert, channel, window_start=None: False
        bot.recent_alert_exists = lambda *a, **k: True
        check("E recent 24h row -> suppressed as 'dedup 24h'",
              bot.suppression_reason(alert, channel="en:1") == "dedup 24h")
        bot.recent_alert_exists = lambda *a, **k: False
        check("E no recent row -> may fire (None)",
              bot.suppression_reason(alert, channel="en:1") is None)
    finally:
        bot.recent_alert_exists = orig_recent
        bot._fallback_suppressed = orig_fb

    # ================================================================
    # (F) load_live_tickers (stubbed DB) populates the field for real
    # ================================================================
    real_now = datetime.now(UTC)
    dev_ts = real_now.strftime("%Y-%m-%dT%H:%M:%SZ")
    por_ts = (real_now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    red_status = {"status": "open"}

    def stub_db(sql, args=None):
        if "FROM universe" in sql:
            return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
        if "FROM deviations" in sql:
            return [{"ticker_id": "TSLAx", "ts": dev_ts,
                     "depth_weighted_price": 500.10,
                     "dev_vs_median_pct": 0.10,
                     "qualifying_depth_usd": 3000000.0, "pools_used": 1}]
        if "redemption_windows" in sql:
            return [{"status": red_status["status"], "window_note": None,
                     "next_open_at": None}]
        if "por_feeds" in sql:
            return [{"age_hours": 6.0, "last_update_ts": por_ts}]
        if "JOIN snapshots" in sql:
            return [{"dex": "raydium", "price_usd": 500.10,
                     "reserve_usd": 3000000.0}]
        if "FROM perp_snapshots" in sql:
            return []  # F1/F3 build 2026-11-13: no perp rows in this stub
        raise AssertionError(f"unexpected SQL in stub: {sql[:80]}")

    orig_db = bot.db_query
    try:
        bot.db_query = stub_db
        fri = bot.load_live_tickers(now_utc=dt("2026-11-06T12:00:00Z"))
        check("F Friday live load: closes_within_24h True from real data",
              len(fri) == 1 and fri[0]["closes_within_24h"] is True,
              f"got={fri}")
        check("F Friday live load: next_close_at = Sat 00:00 ET",
              fri and fri[0]["next_close_at"] == "2026-11-07T05:00:00Z")
        mon = bot.load_live_tickers(now_utc=dt("2026-11-09T12:00:00Z"))
        check("F Monday live load: closes_within_24h False",
              len(mon) == 1 and mon[0]["closes_within_24h"] is False)
        check("F Monday live load: next_close_at is the Saturday close",
              mon and mon[0]["next_close_at"] == "2026-11-14T05:00:00Z")
        red_status["status"] = "closed"
        closed = bot.load_live_tickers(now_utc=dt("2026-11-06T12:00:00Z"))
        check("F closed live load: no close field (None/False)",
              closed and closed[0]["closes_within_24h"] is False
              and closed[0]["next_close_at"] is None)
    finally:
        bot.db_query = orig_db
        red_status["status"] = "open"

    # ================================================================
    # (G) Honest labels on web + dashboard; docstring + GATE record
    # ================================================================
    web_i18n = open(os.path.join(ROOT, "web/src/lib/i18n.ts"),
                    encoding="utf-8").read()
    check("G web [en]: methodology lists closing-within-24h (schedule-derived)",
          "redemption window closing within 24h (schedule-derived close time)" in web_i18n)
    check("G web [id]: methodology lists closing-within-24h (turunan jadwal)",
          "jendela redemption tutup dalam 24 jam (waktu tutup turunan jadwal)" in web_i18n)
    sys.path.insert(0, os.path.join(ROOT, "dashboard"))
    import i18n as dash_i18n  # noqa: E402
    for lang in ("en", "id"):
        thr = dash_i18n.STR[lang]["methodology_thresholds"]
        check(f"G dashboard [{lang}]: methodology lists closing-within-24h",
              "closing within 24h" in thr if lang == "en"
              else "tutup dalam 24 jam" in thr)
        check(f"G dashboard [{lang}]: alert-type key for closing soon exists",
              "alert_type_redemption_closing" in dash_i18n.STR[lang])
    check("G web: history key for closing soon exists (EN + ID)",
          web_i18n.count("hist_type_redemption_closing") == 2)
    page = open(os.path.join(ROOT, "web/src/app/methodology/page.tsx"),
                encoding="utf-8").read()
    check("G web: history map routes redemption_closing_soon",
          'redemption_closing_soon: "hist_type_redemption_closing"' in page)
    app_py = open(os.path.join(ROOT, "dashboard/app.py"),
                  encoding="utf-8").read()
    check("G dashboard: alert-log map routes redemption_closing_soon",
          '"redemption_closing_soon": t(lang, "alert_type_redemption_closing")' in app_py)
    bot_src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    check("G bot: old 'cannot be computed live yet' claim is gone",
          "cannot be computed live" not in bot_src)
    check("G bot: docstring records the R7 build",
          "redemption_closing_soon" in bot_src
          and "gap r7" in bot_src.lower())
    gate = open(os.path.join(ROOT, "GATE-A1-G0.md"), encoding="utf-8").read()
    check("G GATE doc records the R7 advance-alert build",
          "redemption_closing_soon" in gate and "Gap ronde 7" in gate)

    # ================================================================
    # (H) dry-run shows the new scenario
    # ================================================================
    buf = io.StringIO()
    with redirect_stdout(buf):
        bot.dry_run_scenarios()
    out = buf.getvalue()
    check("H dry-run: closing-soon scenario present",
          "redemption closing within 24h (schedule-derived)" in out)
    check("H dry-run: closing-soon message renders",
          "REDEMPTION CLOSING SOON" in out and "Sat 07 Nov 2026, 13:00 WITA" in out)

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("R7 CLOSE-ALERT TEST: PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
