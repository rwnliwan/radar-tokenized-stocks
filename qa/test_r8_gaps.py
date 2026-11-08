"""Round-8 GAP tests (Terra r8 Radar: P1-G1, P1-G2, P2-G1, P2-G2).

Pure + monkeypatched-DB only: no network, no token, no Telegram send,
no production reads/writes. Run: python3 qa/test_r8_gaps.py (exit 0 = PASS)

- P1-G1 (vs-close roadmap label): NOT built — no licensed feed exists
  and none is fabricated. Locked here instead: the roadmap label must
  stay present and honest on web + dashboard, EN + ID. If the label
  disappears from either surface, this guard fails.
- P1-G2 (admin destination for a troubled poller): RADAR_ADMIN_CHAT_ID.
  (a) unset -> log only, no send, no crash; (b) set -> one ops message
  to the admin chat (never to the public EN/ID channels — this helper
  only ever sends to the admin id); (c) second call inside 60 min ->
  throttled, no resend; (d) after the cooldown -> resends; (e) a send
  failure -> False, no state saved, no crash (next pass retries).
- P2-G1 (calibration counter for the "8 weekends" claim):
  distinct Sat-anchored weekends counted from actual observed dates;
  Sat+Sun of one weekend = ONE weekend; pre-start / future /
  unparseable dates ignored; calibrated only at >= 8. The score
  formula itself is unchanged (locked by test_r8_fix / spread guard).
- P2-G2 (fallback-file replay into alert_log): (a) replay success ->
  rows land with the marker's own alert_ts + file pruned; (b) DB
  failure -> file intact, pass continues (no raise); (c) replay twice
  -> no duplicate rows (WHERE NOT EXISTS on the delivery key);
  (d) unreadable fallback file -> abort, file untouched, no raise;
  (e) malformed marker -> kept in the file, never silently dropped.

Thresholds are NOT changed here (stale gate 30 min, admin cooldown
60 min is a NEW ops throttle, not a market threshold; risk score
formula, dedup 24h, spread/dev thresholds untouched).
"""
import json
import os
import re
import sys
import tempfile
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


def _write_markers(path, markers):
    with open(path, "w", encoding="utf-8") as f:
        for m in markers:
            f.write(json.dumps(m) + "\n")


def _read_markers(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class FakeDB:
    """Simulates alert_log as a set of (ticker, alert_ts, type, channel)
    plus the WHERE NOT EXISTS semantics of REPLAY_ALERT_SQL."""

    def __init__(self, fail=False):
        self.rows = set()
        self.calls = []
        self.fail = fail

    def execute(self, sql, args=None):
        self.calls.append((sql, list(args or [])))
        if self.fail:
            raise RuntimeError("simulated Turso outage")
        key = (args[0], args[1], args[2], args[4])
        self.rows.add(key)
        return None


def main():
    now = datetime(2026, 11, 9, 2, 0, 0, tzinfo=UTC)
    tmp = tempfile.mkdtemp(prefix="r8gaps_")
    fallback_path = os.path.join(tmp, ".alert_sent_fallback.jsonl")
    state_path = os.path.join(tmp, ".admin_poller_alert.json")
    orig_fallback = bot.ALERT_FALLBACK_PATH
    orig_state = bot.ADMIN_ALERT_STATE_PATH
    bot.ALERT_FALLBACK_PATH = fallback_path
    bot.ADMIN_ALERT_STATE_PATH = state_path
    orig_admin_env = os.environ.get("RADAR_ADMIN_CHAT_ID")
    if "RADAR_ADMIN_CHAT_ID" in os.environ:
        del os.environ["RADAR_ADMIN_CHAT_ID"]
    try:
        # ================================================================
        # P1-G1 — roadmap label must stay on web + dashboard (EN + ID)
        # ================================================================
        web_i18n = open(os.path.join(ROOT, "web/src/lib/i18n.ts"),
                        encoding="utf-8").read()
        check("G1 web [en]: vs-close labelled roadmap, license-pending",
              "Deviation vs stock close is NOT live yet — roadmap, needs a close-price feed license." in web_i18n)
        check("G1 web [id]: vs-close labelled roadmap, license-pending",
              "Deviasi vs close saham BELUM live — roadmap, butuh lisensi feed harga close." in web_i18n)
        sys.path.insert(0, os.path.join(ROOT, "dashboard"))
        import i18n as dash_i18n  # noqa: E402
        for lang in ("en", "id"):
            thr = dash_i18n.STR[lang]["methodology_thresholds"]
            check(f"G1 dashboard [{lang}]: vs-close labelled roadmap",
                  "roadmap" in thr.lower() and "not live yet" in thr.lower()
                  if lang == "en" else "roadmap" in thr.lower(),
                  f"thr={thr[:80]!r}")
            check(f"G1 dashboard [{lang}]: close_note keeps median as reference",
                  "cross-venue median" in dash_i18n.STR[lang]["close_note"]
                  if lang == "en" else "median lintas-venue" in dash_i18n.STR[lang]["close_note"])

        # ================================================================
        # P1-G2 — admin destination for a troubled poller
        # ================================================================
        sent = []

        def fake_send(chat_id, text):
            sent.append((chat_id, text))
            return {"ok": True}

        # (a) No admin configured -> log only, no send, no crash.
        ok = bot.notify_admin_poller_troubled(45, now=now, state_path=state_path,
                                              sender=fake_send)
        check("G2 no-config: logged only, no send, returns False",
              ok is False and sent == [])
        check("G2 no-config: no state file created",
              not os.path.exists(state_path))

        # (b) Configured -> one message to the ADMIN chat id.
        os.environ["RADAR_ADMIN_CHAT_ID"] = "-100999"
        ok = bot.notify_admin_poller_troubled(45, now=now, state_path=state_path,
                                              sender=fake_send)
        check("G2 configured: message sent to admin chat",
              ok is True and len(sent) == 1 and sent[0][0] == "-100999",
              f"sent={sent!r}")
        check("G2 configured: message names the stale age",
              "45 min" in sent[0][1] and "POLLER TROUBLED" in sent[0][1])
        check("G2 configured: state file records the notification",
              os.path.exists(state_path))

        # (c) Second call inside the 60-min cooldown -> throttled.
        ok = bot.notify_admin_poller_troubled(
            50, now=now + timedelta(minutes=10), state_path=state_path,
            sender=fake_send)
        check("G2 cooldown: second call within 60 min throttled",
              ok is False and len(sent) == 1)

        # (d) After the cooldown -> resends.
        ok = bot.notify_admin_poller_troubled(
            90, now=now + timedelta(minutes=61), state_path=state_path,
            sender=fake_send)
        check("G2 cooldown: call after 60 min resends",
              ok is True and len(sent) == 2 and "90 min" in sent[1][1])

        # (e) Send failure -> False, state untouched, no crash.
        def failing_send(chat_id, text):
            raise RuntimeError("simulated Telegram failure")

        before = open(state_path, encoding="utf-8").read()
        ok = bot.notify_admin_poller_troubled(
            120, now=now + timedelta(minutes=200), state_path=state_path,
            sender=failing_send)
        after = open(state_path, encoding="utf-8").read()
        check("G2 send failure: returns False, no crash, state kept",
              ok is False and before == after and len(sent) == 2)
        check("G2 admin_chat_id: blank env counts as unconfigured",
              (os.environ.__setitem__("RADAR_ADMIN_CHAT_ID", "   "),
               bot.admin_chat_id() is None)[1])
        del os.environ["RADAR_ADMIN_CHAT_ID"]

        # ================================================================
        # P2-G1 — calibration counter
        # ================================================================
        from risk import (CALIBRATION_WEEKENDS_REQUIRED,  # noqa: E402
                          calibration_progress, weekend_key)
        from datetime import date as _date  # noqa: E402
        check("G3 weekend_key: Sat/Sun map to their Saturday",
              weekend_key(_date(2026, 10, 24)) == _date(2026, 10, 24)
              and weekend_key(_date(2026, 10, 25)) == _date(2026, 10, 24))
        check("G3 weekend_key: weekday returns None",
              weekend_key(_date(2026, 10, 26)) is None)
        p = calibration_progress(
            ["2026-10-24", "2026-10-25", "2026-10-31", "2026-11-01",
             "2026-11-07", "2026-11-08"], now="2026-11-09")
        check("G3 counter: 3 weekends from 6 weekend days (9 Nov)",
              p["weekends_observed"] == 3 and p["weekend_days_observed"] == 6
              and p["required"] == 8 and p["remaining"] == 5
              and p["calibrated"] is False and p["progress_pct"] == 37.5,
              f"p={p}")
        p1 = calibration_progress(["2026-10-24"], now="2026-11-09")
        check("G3 counter: Sat alone counts its weekend (1/8)",
              p1["weekends_observed"] == 1 and p1["remaining"] == 7)
        p_dup = calibration_progress(
            ["2026-10-24", "2026-10-24T05:00:00Z", "2026-10-25"],
            now="2026-11-09")
        check("G3 counter: duplicate days do not inflate weekends",
              p_dup["weekends_observed"] == 1
              and p_dup["weekend_days_observed"] == 2)
        p_bad = calibration_progress(
            ["2026-10-23", "2026-10-26", "2026-12-25", "bogus", None, "",
             "2026-10-24"], now="2026-11-09")
        check("G3 counter: pre-start/weekday/future/garbage ignored",
              p_bad["weekends_observed"] == 1
              and p_bad["weekend_days_observed"] == 1, f"p={p_bad}")
        many = []
        for sat in ["2026-10-24", "2026-10-31", "2026-11-07", "2026-11-14",
                    "2026-11-21", "2026-11-28", "2026-12-05", "2026-12-12"]:
            many.append(sat)
        p8 = calibration_progress(many, now="2026-12-13")
        check("G3 counter: 8 weekends -> calibrated, remaining 0",
              p8["weekends_observed"] == 8 and p8["calibrated"] is True
              and p8["remaining"] == 0 and p8["progress_pct"] == 100.0)
        check("G3 constant: required stays 8",
              CALIBRATION_WEEKENDS_REQUIRED == 8)
        for lang in ("en", "id"):
            check(f"G3 i18n [{lang}]: calibration progress key exists",
                  "risk_calibration_progress" in dash_i18n.STR[lang]
                  and "{n}" in dash_i18n.STR[lang]["risk_calibration_progress"])
            check(f"G3 i18n [{lang}]: calibrated key exists",
                  "risk_calibrated" in dash_i18n.STR[lang])

        # ================================================================
        # P2-G2 — fallback-file replay into alert_log
        # ================================================================
        marker = {"ticker": "TSLAx", "type": "deviation_high",
                  "channel": "en:1", "alert_ts": "2026-11-08T10:00:00Z"}
        marker2 = {"ticker": "SPYx", "type": "spread",
                   "channel": "id:2", "alert_ts": "2026-11-08T10:05:00Z"}

        # (a) Replay success -> rows land, file pruned.
        _write_markers(fallback_path, [marker, marker2])
        db = FakeDB()
        res = bot.replay_fallback_alerts(db_execute_fn=db.execute)
        check("G4 replay success: both markers replayed",
              res["replayed"] == 2 and res["failed"] == 0 and res["kept"] == 0,
              f"res={res}")
        check("G4 replay success: rows keyed by delivery identity",
              ("TSLAx", "2026-11-08T10:00:00Z", "deviation_high", "en:1") in db.rows
              and ("SPYx", "2026-11-08T10:05:00Z", "spread", "id:2") in db.rows)
        check("G4 replay success: original alert_ts preserved (not re-stamped)",
              all(a[1] in ("2026-11-08T10:00:00Z", "2026-11-08T10:05:00Z")
                  for _, a in db.calls))
        check("G4 replay success: fallback file pruned to empty",
              _read_markers(fallback_path) == [])
        check("G4 replay SQL: guarded by WHERE NOT EXISTS on delivery key",
              any("NOT EXISTS" in sql and "ticker_id = ?" in sql
                  for sql, _ in db.calls))

        # (c) Replay twice -> no duplicates (idempotent).
        _write_markers(fallback_path, [marker, marker2])
        res2 = bot.replay_fallback_alerts(db_execute_fn=db.execute)
        check("G4 replay twice: no duplicate rows",
              res2["replayed"] == 2 and len(db.rows) == 2,
              f"res={res2} rows={len(db.rows)}")
        check("G4 replay twice: file pruned again",
              _read_markers(fallback_path) == [])

        # (b) DB failure -> file intact, no raise, pass continues.
        _write_markers(fallback_path, [marker, marker2])
        db_down = FakeDB(fail=True)
        res3 = bot.replay_fallback_alerts(db_execute_fn=db_down.execute)
        check("G4 DB failure: returns failed counts, no raise",
              res3["replayed"] == 0 and res3["failed"] == 2 and res3["kept"] == 2,
              f"res={res3}")
        check("G4 DB failure: fallback file untouched",
              _read_markers(fallback_path) == [marker, marker2])

        # (e) Malformed marker -> kept, never silently dropped.
        bad = {"ticker": "TSLAx", "type": "deviation_high",
               "channel": "en:1", "alert_ts": "not-a-date"}
        _write_markers(fallback_path, [marker, bad])
        db2 = FakeDB()
        res4 = bot.replay_fallback_alerts(db_execute_fn=db2.execute)
        check("G4 malformed marker: kept in file, good marker replayed",
              res4["replayed"] == 1 and res4["failed"] == 1
              and _read_markers(fallback_path) == [bad], f"res={res4}")

        # (d) Unreadable fallback file -> abort, untouched, no raise.
        orig_markers = bot._fallback_markers
        bot._fallback_markers = lambda: None
        try:
            res5 = bot.replay_fallback_alerts(db_execute_fn=db2.execute)
        finally:
            bot._fallback_markers = orig_markers
        check("G4 unreadable file: aborts without raising, file untouched",
              res5 == {"replayed": 0, "failed": 0, "kept": 0}
              and _read_markers(fallback_path) == [bad], f"res={res5}")

        # Empty file -> clean no-op.
        _write_markers(fallback_path, [])
        res6 = bot.replay_fallback_alerts(db_execute_fn=db2.execute)
        check("G4 empty file: clean no-op",
              res6 == {"replayed": 0, "failed": 0, "kept": 0})
    finally:
        bot.ALERT_FALLBACK_PATH = orig_fallback
        bot.ADMIN_ALERT_STATE_PATH = orig_state
        if orig_admin_env is None:
            os.environ.pop("RADAR_ADMIN_CHAT_ID", None)
        else:
            os.environ["RADAR_ADMIN_CHAT_ID"] = orig_admin_env

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("R8 GAPS TEST: PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
