"""Grouped redemption_closing_soon sends (Septian, 13 Nov 2026, opsi 1)
+ grouped 'redemption' (closed/gated) sends (Septian 👍 same day).

13 xStocks tickers share one redemption window, so the advance alert
fired as 13 separate messages per channel (26 messages on 13 Nov
13:01 WITA) — and the closed-window alert would do the same when the
window closes. Now both go out as ONE summary message per channel:
header + close time + tickers comma-separated + the schedule-derived
note. Readable, not a wall of text.

- (A) format_grouped_closing_soon EN + ID: header with count, close
  time shown, all tickers on one comma-separated line, schedule note
  present, NO per-ticker prices (no "depth-weighted" anywhere), site
  link + disclaimer footer; singular "1 ticker" in EN; empty list
  raises ValueError; earliest close wins when close times differ.
- (B) partition_closing_soon: only closing_soon is grouped; every
  other type stays in rest, order preserved.
- (C) send_closing_soon_group (mocked send/record/suppression):
  13 alerts -> 1 send per channel, 13 alert_log rows per channel,
  one shared alert_ts for the whole event; per-ticker 24h dedup is
  per-channel (a ticker suppressed for EN only still goes out on ID);
  a channel with everything suppressed gets nothing; empty batch
  sends nothing; stale gate stops remaining channels; a failed send
  records nothing for that channel; a failed record still counts the
  send (GG-32 rule) and prints the not-recorded warning.

Pure + stubbed only: no network, no token, no Telegram send, no
production reads/writes. Run: python3 qa/test_closing_soon_group.py
(exit 0 = PASS).
"""
import io
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
sys.path.insert(0, ROOT)
import bot  # noqa: E402  (token is lazy; import touches no vault/DB)

FAILURES = []
UTC = timezone.utc
TICKERS_13 = ["AAPLx", "COINx", "CRCLx", "GLDx", "GOOGLx", "HOODx",
              "METAx", "MSFTx", "MSTRx", "NVDAx", "QQQx", "SPYx", "TSLAx"]
CHANNELS = [("en", -1003867845895), ("id", -1004471605253)]
CLOSE = "2026-11-14T05:00:00Z"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def closing_alert(ticker, close=CLOSE, issuer="xStocks"):
    return {"type": "redemption_closing_soon", "ticker": ticker,
            "issuer": issuer, "status": "open",
            "next_close_at": close, "closes_within_24h": True,
            "dw": 400.0, "depth": 1000000.0, "pools_used": 2}


# ---------------- (A) format ----------------
a13 = [closing_alert(t) for t in TICKERS_13]
en = bot.format_grouped_closing_soon(a13, "en")
check("EN header counts 13 tickers",
      "REDEMPTION CLOSING SOON — xStocks (13 tickers)" in en, en.split("\n")[0])
check("EN shows close time", "14 Nov 2026" in en and "13:00" in en, en.split("\n")[2])
check("EN lists all 13 tickers on one line",
      all(t in en for t in TICKERS_13) and
      len([l for l in en.split("\n") if "AAPLx" in l]) == 1)
check("EN has schedule note, no per-ticker prices",
      "schedule" in en and "depth-weighted" not in en and "Qualifying depth" not in en)
check("EN footer: site link + disclaimer",
      "https://radar.omdanny.site" in en and "Not financial advice" in en)
check("EN short: under 12 lines", len(en.split("\n")) <= 12, f"{len(en.splitlines())} lines")

idd = bot.format_grouped_closing_soon(a13, "id")
check("ID header counts 13 ticker",
      "REDEMPTION SEGERA TUTUP — xStocks (13 ticker)" in idd, idd.split("\n")[0])
check("ID shows close time + ticker line",
      "14 Nov 2026" in idd and "Ticker: AAPLx" in idd)
check("ID has schedule note, no per-ticker prices",
      "jadwal resmi" in idd and "tertimbang kedalaman" not in idd)

one = bot.format_grouped_closing_soon([closing_alert("TSLAx")], "en")
check("EN singular is '1 ticker' not '1 tickers'",
      "(1 ticker)" in one and "(1 tickers)" not in one)
one_id = bot.format_grouped_closing_soon([closing_alert("TSLAx")], "id")
check("ID singular is '1 ticker'", "(1 ticker)" in one_id)

try:
    bot.format_grouped_closing_soon([], "en")
    check("empty batch raises ValueError", False, "no raise")
except ValueError:
    check("empty batch raises ValueError", True)

mixed_close = [closing_alert("AAPLx", "2026-11-14T05:00:00Z"),
               closing_alert("TSLAx", "2026-11-14T03:00:00Z")]
early_txt = bot.format_grouped_closing_soon(mixed_close, "en")
check("earliest close wins when times differ",
      "11:00" in early_txt and "13:00" not in early_txt,
      "03:00Z -> 11:00 WITA, later 05:00Z -> 13:00 WITA must not appear")
no_close = [dict(closing_alert("TSLAx"), next_close_at=None)]
check("missing close falls back to 'within 24h', never fabricated",
      "within 24h" in bot.format_grouped_closing_soon(no_close, "en"))

# ---------------- (A2) format_grouped_redemption ----------------
NEXT_OPEN = "2026-11-16T13:00:00Z"


def closed_alert(ticker, status="closed", nxt=NEXT_OPEN, issuer="xStocks"):
    return {"type": "redemption", "ticker": ticker, "issuer": issuer,
            "status": status, "next_open_at": nxt, "closes_within_24h": False,
            "dw": 400.0, "depth": 1000000.0, "pools_used": 2}


c13 = [closed_alert(t) for t in TICKERS_13]
cen = bot.format_grouped_redemption(c13, "en")
check("closed EN header counts 13 tickers",
      "REDEMPTION CLOSED — xStocks (13 tickers)" in cen, cen.split("\n")[0])
check("closed EN shows status + next opening",
      "Status: closed" in cen and "16 Nov 2026" in cen and "21:00" in cen)
check("closed EN lists all 13 tickers, no per-ticker prices",
      all(t in cen for t in TICKERS_13) and "depth-weighted" not in cen)
check("closed EN footer: site link + disclaimer",
      "https://radar.omdanny.site" in cen and "Not financial advice" in cen)
check("closed EN short: under 12 lines", len(cen.split("\n")) <= 12,
      f"{len(cen.splitlines())} lines")
cid = bot.format_grouped_redemption(c13, "id")
check("closed ID header + status + opening",
      "REDEMPTION TUTUP — xStocks (13 ticker)" in cid and
      "Status: tutup" in cid and "Pembukaan berikutnya:" in cid and
      "16 Nov 2026" in cid)
check("closed ID lists tickers, no per-ticker prices",
      "Ticker: AAPLx" in cid and "tertimbang kedalaman" not in cid)
gated_en = bot.format_grouped_redemption([closed_alert("TSLAx", "gated")], "en")
check("gated status renders 'gated' in EN", "Status: gated" in gated_en)
gated_id = bot.format_grouped_redemption([closed_alert("TSLAx", "gated")], "id")
check("gated status renders 'terbatas (KYC)' in ID",
      "Status: terbatas (KYC)" in gated_id)
try:
    bot.format_grouped_redemption([], "en")
    check("closed empty batch raises ValueError", False, "no raise")
except ValueError:
    check("closed empty batch raises ValueError", True)
mixed_open = [closed_alert("AAPLx", nxt="2026-11-16T13:00:00Z"),
              closed_alert("TSLAx", nxt="2026-11-16T11:00:00Z")]
early_open = bot.format_grouped_redemption(mixed_open, "en")
check("closed earliest opening wins when times differ",
      "19:00" in early_open and "21:00" not in early_open,
      "11:00Z -> 19:00 WITA, later 13:00Z -> 21:00 WITA must not appear")
no_open = [dict(closed_alert("TSLAx"), next_open_at=None)]
no_open_txt = bot.format_grouped_redemption(no_open, "en")
check("closed missing opening shows '—', never a fabricated time",
      "Next opening: —" in no_open_txt and "2026" not in no_open_txt)

# ---------------- (B2) partition_redemption ----------------
groups, rest2 = bot.partition_redemption(
    [closed_alert("AAPLx"), closed_alert("TSLAx", "gated"),
     closing_alert("SPYx"), closed_alert("COINx"),
     {"type": "redemption", "ticker": "FOOx", "issuer": "bStocks",
      "status": "closed", "next_open_at": NEXT_OPEN}])
check("partition_redemption splits by (issuer, status)",
      len(groups) == 3 and
      sorted(len(g) for g in groups) == [1, 1, 2] and
      rest2 == [closing_alert("SPYx")])
check("partition_redemption of empty list is empty",
      bot.partition_redemption([]) == ([], []))

# ---------------- (B) partition ----------------
perp = {"type": "perp_deviation", "ticker": "COINx"}
exit_a = {"type": "exit_high", "ticker": "TSLAB"}
closing, rest = bot.partition_closing_soon(
    [closing_alert("AAPLx"), perp, closing_alert("TSLAx"), exit_a])
check("partition groups only closing_soon",
      [a["ticker"] for a in closing] == ["AAPLx", "TSLAx"] and rest == [perp, exit_a])
check("partition of empty list is empty", bot.partition_closing_soon([]) == ([], []))

# ---------------- (C) send group (mocked) ----------------
sends = []
records = []


def fake_send(cid, text):
    sends.append((cid, text))


def fake_record(alert, text, ts, channel=None):
    records.append((alert["ticker"], text, ts, channel))
    return True


suppressed = set()


def fake_suppression(alert, red_rows=None, channel=None):
    return "dedup 24h" if (alert["ticker"], channel) in suppressed else None


orig_send, orig_record = bot.send_message, bot.record_alert_safe
orig_suppr, orig_fresh = bot.suppression_reason, bot.data_still_fresh
bot.send_message = fake_send
bot.record_alert_safe = fake_record
bot.suppression_reason = fake_suppression
bot.data_still_fresh = lambda: True
try:
    # 13 alerts -> 1 send per channel, 13 rows per channel, one shared ts
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_closing_soon_group(a13, CHANNELS, None, datetime.now(UTC))
    check("13 alerts -> 2 channel sends (not 26)",
          n == 2 and len(sends) == 2, f"sent={n} sends={len(sends)}")
    check("one grouped text per channel, tickers listed",
          all(all(t in txt for t in TICKERS_13) for _, txt in sends))
    check("26 record rows (13 tickers x 2 channels)", len(records) == 26,
          f"rows={len(records)}")
    check("one shared alert_ts for the whole event",
          len({r[2] for r in records}) == 1)
    check("recorded text is the grouped EN text, not per-ticker format",
          all(r[1] == bot.format_grouped_closing_soon(a13, "en") for r in records))
    check("EN rows on en channel, ID rows on id channel",
          sorted({r[3] for r in records}) ==
          ["en:-1003867845895", "id:-1004471605253"])

    # dedup is per-channel: suppress TSLAx for EN only
    suppressed.add(("TSLAx", "en:-1003867845895"))
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_closing_soon_group(a13, CHANNELS, None, datetime.now(UTC))
    en_txt = [t for c, t in sends if c == -1003867845895][0]
    id_txt = [t for c, t in sends if c == -1004471605253][0]
    check("dedup per-channel: EN group drops TSLAx, ID keeps it",
          "TSLAx" not in en_txt and "TSLAx" in id_txt and
          "(12 tickers)" in en_txt and "(13 ticker)" in id_txt)
    check("dedup per-channel: 12 EN rows, 13 ID rows",
          len([r for r in records if r[3].startswith("en:")]) == 12 and
          len([r for r in records if r[3].startswith("id:")]) == 13)
    suppressed.clear()

    # everything suppressed for ID -> ID gets nothing, EN still sends
    for t in TICKERS_13:
        suppressed.add((t, "id:-1004471605253"))
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_closing_soon_group(a13, CHANNELS, None, datetime.now(UTC))
    check("fully suppressed channel gets no send",
          n == 1 and len(sends) == 1 and sends[0][0] == -1003867845895)
    check("fully suppressed channel gets no rows",
          len(records) == 13 and all(r[3].startswith("en:") for r in records))
    suppressed.clear()

    # empty batch -> 0, no sends
    sends.clear()
    records.clear()
    check("empty batch sends nothing",
          bot.send_closing_soon_group([], CHANNELS, None, datetime.now(UTC)) == 0
          and not sends and not records)

    # stale gate: fresh fails before first channel -> nothing sent
    bot.data_still_fresh = lambda: False
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_closing_soon_group(a13, CHANNELS, None, datetime.now(UTC))
    check("stale gate stops all sends", n == 0 and not sends and not records)
    bot.data_still_fresh = lambda: True

    # send failure on ID: EN sent + recorded, ID not recorded
    def fail_id(cid, text):
        if cid == -1004471605253:
            raise RuntimeError("telegram down")
        sends.append((cid, text))
    bot.send_message = fail_id
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_closing_soon_group(a13, CHANNELS, None, datetime.now(UTC))
    check("failed channel is not recorded, other channel unaffected",
          n == 1 and len(sends) == 1 and len(records) == 13 and
          all(r[3].startswith("en:") for r in records))
    bot.send_message = fake_send

    # record failure: send still counts (GG-32), warning printed
    bot.record_alert_safe = lambda *a, **k: False
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_closing_soon_group(a13, CHANNELS, None, datetime.now(UTC))
    check("record failure still counts the send, warns",
          n == 2 and "NOT recorded" in f.getvalue())
    bot.record_alert_safe = fake_record

    # ---------------- (C2) send_redemption_group ----------------
    # 13 closed alerts -> 1 send per channel, 26 rows, one shared ts
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_redemption_group(c13, CHANNELS, None, datetime.now(UTC))
    check("closed 13 alerts -> 2 channel sends (not 26)",
          n == 2 and len(sends) == 2, f"sent={n} sends={len(sends)}")
    check("closed one grouped text per channel, tickers listed",
          all(all(t in txt for t in TICKERS_13) for _, txt in sends))
    check("closed 26 record rows, one shared alert_ts",
          len(records) == 26 and len({r[2] for r in records}) == 1,
          f"rows={len(records)}")
    check("closed recorded text is the grouped EN text",
          all(r[1] == bot.format_grouped_redemption(c13, "en") for r in records))

    # window-dedup suppression ("same window") excludes per-channel too
    suppressed.add(("TSLAx", "en:-1003867845895"))
    sends.clear()
    records.clear()
    f = io.StringIO()
    with redirect_stdout(f):
        n = bot.send_redemption_group(c13, CHANNELS, None, datetime.now(UTC))
    en_txt = [t for c, t in sends if c == -1003867845895][0]
    check("closed window-dedup per-channel: EN drops TSLAx",
          "TSLAx" not in en_txt and "(12 tickers)" in en_txt and
          len([r for r in records if r[3].startswith("en:")]) == 12)
    suppressed.clear()
    sends.clear()
    records.clear()
    check("closed empty batch sends nothing",
          bot.send_redemption_group([], CHANNELS, None, datetime.now(UTC)) == 0
          and not sends and not records)
finally:
    bot.send_message, bot.record_alert_safe = orig_send, orig_record
    bot.suppression_reason, bot.data_still_fresh = orig_suppr, orig_fresh

print()
if FAILURES:
    print(f"FAILURES: {len(FAILURES)}")
    for name in FAILURES:
        print(" - " + name)
    sys.exit(1)
print("ALL PASS")
