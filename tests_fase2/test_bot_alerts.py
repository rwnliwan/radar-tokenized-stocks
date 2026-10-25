"""Bot per-ticker redemption test: one message per ticker (un-batch
decision 2026-10-25, Septian's call — supersedes the Wave-3 batching).

Pure + monkeypatched-DB only: no network, no token access, no prod
writes. Covers:
- 13 closed tickers -> exactly 13 'redemption' alerts, one per
  ticker, NO batch type, NO 'ALL' key;
- EN + ID formats render in their own languages (no ID leak into EN);
- forbidden words still pass on both messages;
- mixed statuses (closed + gated) -> per-ticker alerts with their
  own status each; gated renders 'terbatas (KYC)' in ID;
- single ticker -> one alert, formats correctly;
- empty group -> no alert; 'paused' IS a trigger with its own
  per-ticker type ('redemption_paused') and dedup key;
- per-ticker dedup key (ticker, 'redemption') suppresses repeats
  within 24h, and record_alert writes one row per ticker;
- paused: a recorded closed alert for a ticker does NOT suppress a
  paused alert for the same ticker (distinct keys); a recorded
  paused alert DOES suppress a repeat paused alert; EN+ID render
  with high-priority marker, no leaks, no forbidden words.
"""
import re
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks")
import bot  # noqa: E402  (token is lazy; import touches no vault/DB)

FORBIDDEN = ["aman", "disarankan", "beli", "jual",
             "safe", "recommended", "buy", "sell"]

TICKERS_13 = ["TSLAx", "NVDAx", "METAx", "GOOGLx", "MSTRx", "SPYx",
              "QQQx", "CRCLx", "HOODx", "COINx", "GLDx", "AAPLx", "MSFTx"]
NEXT_OPEN = "2026-10-26T04:00:00Z"


def mk(ticker, status="closed", dw=500.0, depth=3000000.0, pools=1):
    return {
        "ticker": ticker, "issuer": "xStocks", "venues": [],
        "dw": dw, "dev_med": 0.10, "depth": depth, "pools_used": pools,
        "median": dw, "redemption_status": status,
        "redemption_note": "Dari jadwal: akhir pekan/hari libur NYSE -> tutup.",
        "next_open_at": NEXT_OPEN if status == "closed" else None,
        "por_age_hours": None,
    }


def reds(alerts):
    return [a for a in alerts if a["type"] == "redemption"]


def paused(alerts):
    return [a for a in alerts if a["type"] == "redemption_paused"]


def check_forbidden(msg, where):
    for w in FORBIDDEN:
        assert not re.search(rf"\b{w}\b", msg, re.IGNORECASE), \
            f"forbidden word {w!r} in {where}: {msg[:200]}"


def main():
    # 1) 13 closed -> exactly 13 per-ticker alerts, no batch, no ALL.
    data = [mk(t, dw=100.0 + i) for i, t in enumerate(TICKERS_13)]
    alerts = bot.evaluate_alerts(data, False)
    r = reds(alerts)
    assert len(r) == 13, f"expected 13 redemption alerts, got {len(r)}: {alerts}"
    assert [a["ticker"] for a in r] == TICKERS_13
    assert all(a["status"] == "closed" for a in r)
    assert not [a for a in alerts if a["type"] in
                ("redemption_batch", "redemption_batch_paused")], \
        "batch types must no longer be emitted"
    assert not [a for a in alerts if a["ticker"] == "ALL"], \
        "no 'ALL' ticker key anymore"

    # 2) Scope: spread / deviation_high / PoR stay per-ticker, untouched.
    spread_t = {
        "ticker": "TSLAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 371.16, "reserve": 2380000.0},
                   {"dex": "orca", "price": 374.90, "reserve": 500000.0}],
        "dw": 371.81, "dev_med": 0.35, "depth": 2880000.0,
        "pools_used": 2, "median": 373.03,
        "redemption_status": "open", "por_age_hours": 6.0,
    }
    dev_t = mk("NVDAx", status="open", dw=180.5)
    dev_t["dev_med"] = 3.5
    por_t = mk("METAx", status="open", dw=200.0)
    por_t["por_age_hours"] = 96.0
    por_t["por_last_update"] = "2026-10-20T11:00:00Z"
    mixed = [spread_t, dev_t, por_t] + [mk(t) for t in TICKERS_13[:3]]
    alerts = bot.evaluate_alerts(mixed, True)
    types = sorted(a["type"] for a in alerts)
    assert types == ["deviation_high", "por", "redemption", "redemption",
                     "redemption", "spread"], f"unexpected alert types: {types}"
    assert [a["ticker"] for a in reds(alerts)] == TICKERS_13[:3]

    # 3) EN format: per-ticker head, status, next opening, EN note /
    # disclaimer, ticker link, no ID leak.
    msg_en = bot.format_alert(r[0], "en")
    assert msg_en.splitlines()[0] == "🟡 REDEMPTION — TSLAx (xStocks)"
    assert "Redemption window: closed" in msg_en
    assert "Next opening: Mon 26 Oct 2026, 12:00 WITA" in msg_en
    assert "not confirmed live by the issuer" in msg_en
    assert "Not financial advice" in msg_en
    assert "https://radar.omdanny.site/TSLAx" in msg_en
    assert "Status dihitung dari jadwal" not in msg_en, "ID note leaked into EN"
    assert "Bukan nasihat keuangan" not in msg_en, "ID disclaimer leaked into EN"
    assert "Dari jadwal" not in msg_en, "DB window_note leaked into EN"
    assert "Price (depth-weighted)" in msg_en
    assert "\n\n" in msg_en, "sections must be blank-line separated"
    assert "Tracked venues" not in msg_en, "redundant venues line removed"
    assert len(msg_en) < 4096, f"EN message too long: {len(msg_en)}"
    check_forbidden(msg_en, "EN redemption")

    # 4) ID format: per-ticker head, ID status, ID note/disclaimer, no EN leak.
    msg_id = bot.format_alert(r[0], "id")
    assert msg_id.splitlines()[0] == "🟡 REDEMPTION — TSLAx (xStocks)"
    assert "Status jendela redemption: tutup" in msg_id
    assert "Pembukaan berikutnya: Sen 26 Okt 2026, 12:00 WITA" in msg_id
    assert "bukan konfirmasi live dari issuer" in msg_id
    assert "Bukan nasihat keuangan" in msg_id
    assert "Not financial advice" not in msg_id, "EN disclaimer leaked into ID"
    assert "Harga (tertimbang kedalaman)" in msg_id
    assert "Venue yang dilacak" not in msg_id, "redundant venues line removed"
    assert len(msg_id) < 4096, f"ID message too long: {len(msg_id)}"
    check_forbidden(msg_id, "ID redemption")

    # 5) Mixed statuses -> per-ticker alerts each carrying its own status.
    data = [mk(t) for t in TICKERS_13[:12]]
    gated = mk("MSFTx", status="gated")
    gated["next_open_at"] = None
    alerts = bot.evaluate_alerts(data + [gated], False)
    r = reds(alerts)
    assert len(r) == 13, f"expected 13 alerts, got {len(r)}"
    by_ticker = {a["ticker"]: a for a in r}
    assert by_ticker["MSFTx"]["status"] == "gated"
    assert all(by_ticker[t]["status"] == "closed" for t in TICKERS_13[:12])
    assert "terbatas (KYC)" in bot.format_alert(by_ticker["MSFTx"], "id")

    # 6) Single ticker -> one alert, formats correctly.
    alerts = bot.evaluate_alerts([mk("SPYx")], False)
    r = reds(alerts)
    assert len(r) == 1 and r[0]["ticker"] == "SPYx"
    single_en = bot.format_alert(r[0], "en")
    assert "SPYx" in single_en and "closed" in single_en
    assert "Next opening: Mon 26 Oct 2026, 12:00 WITA" in single_en

    # 7) next_open_at fallback: within-24h, then dash.
    w24 = mk("SPYx")
    w24["next_open_at"] = None
    w24["closes_within_24h"] = True
    r = reds(bot.evaluate_alerts([w24], False))
    assert "within 24h" in bot.format_alert(r[0], "en")
    assert "dalam 24 jam" in bot.format_alert(r[0], "id")
    none_open = mk("SPYx")
    none_open["next_open_at"] = None
    r = reds(bot.evaluate_alerts([none_open], False))
    assert "Next opening: —" in bot.format_alert(r[0], "en")

    # 8) Empty group -> no alert; open/unknown still no alert.
    assert reds(bot.evaluate_alerts([mk("SPYx", status="open")], False)) == []
    assert bot.evaluate_alerts([mk("SPYx", status="unknown")], False) == []

    # 9) Dedup mechanism (monkeypatched DB, zero prod reads/writes).
    orig_query, orig_execute = bot.db_query, bot.db_execute
    try:
        calls = {}

        def fake_query(sql, args=None):
            calls["query"] = (sql, args)
            return [{"n": 1}]

        bot.db_query = fake_query
        assert bot.recent_alert_exists("TSLAx", "redemption") is True
        assert calls["query"][1][0] == "TSLAx"
        assert calls["query"][1][1] == "redemption"

        bot.db_query = lambda sql, args=None: [{"n": 0}]
        assert bot.recent_alert_exists("TSLAx", "redemption") is False

        captured = {}

        def fake_execute(sql, args=None):
            captured["sql"] = sql
            captured["args"] = args

        bot.db_execute = fake_execute
        one = reds(bot.evaluate_alerts([mk("TSLAx")], False))[0]
        bot.record_alert(one, "PER-TICKER TEXT", "2026-10-25T01:30:00Z")
        assert captured["args"][0] == "TSLAx", f"recorded ticker: {captured['args'][0]}"
        assert captured["args"][2] == "redemption"
        assert captured["args"][1] == "2026-10-25T01:30:00Z"
    finally:
        bot.db_query, bot.db_execute = orig_query, orig_execute

    # 10) Paused: own per-ticker type, high-priority render, dedup independence.
    pdata = [mk(t, status="paused", dw=100.0 + i) for i, t in enumerate(TICKERS_13)]
    alerts = bot.evaluate_alerts(pdata, False)
    pb = paused(alerts)
    assert len(pb) == 13, f"expected 13 paused alerts, got {len(pb)}"
    assert [a["ticker"] for a in pb] == TICKERS_13
    assert all(a["status"] == "paused" for a in pb)
    assert reds(alerts) == [], "paused must not emit a plain redemption alert"
    # Single paused ticker -> one paused alert.
    single = paused(bot.evaluate_alerts([mk("SPYx", status="paused")], False))
    assert len(single) == 1 and single[0]["ticker"] == "SPYx"

    # 10a) EN render: priority marker, paused status/note, no ID leak.
    msg_en = bot.format_alert(pb[0], "en")
    assert msg_en.splitlines()[0] == "🔴 REDEMPTION PAUSED — TSLAx (xStocks)"
    assert "High priority: on-chain pause detected" in msg_en
    assert "paused (on-chain)" in msg_en
    assert "not confirmed live by the issuer" in msg_en
    assert "Redemption stays halted until the pause is lifted." in msg_en
    assert "Prioritas tinggi" not in msg_en, "ID priority leaked into EN"
    assert "dijeda" not in msg_en, "ID status leaked into EN"
    assert "Dari jadwal" not in msg_en, "DB window_note leaked into EN"
    assert len(msg_en) < 4096
    check_forbidden(msg_en, "EN paused")

    # 10b) ID render: priority marker, paused status/note, no EN leak.
    msg_id = bot.format_alert(pb[0], "id")
    assert msg_id.splitlines()[0] == "🔴 REDEMPTION DIJEDA — TSLAx (xStocks)"
    assert "Prioritas tinggi: jeda on-chain terdeteksi" in msg_id
    assert "dijeda (on-chain)" in msg_id
    assert "bukan konfirmasi live dari issuer" in msg_id
    assert "Redemption tetap berhenti sampai jeda dicabut." in msg_id
    assert "High priority" not in msg_id, "EN priority leaked into ID"
    assert "Not financial advice" not in msg_id, "EN disclaimer leaked into ID"
    assert len(msg_id) < 4096
    check_forbidden(msg_id, "ID paused")

    # 10c) Mixed closed + paused -> 12 redemption + 1 redemption_paused.
    cdata = [mk(t) for t in TICKERS_13[:12]]
    pdata1 = mk("MSFTx", status="paused")
    alerts = bot.evaluate_alerts(cdata + [pdata1], False)
    assert len(reds(alerts)) == 12
    assert len(paused(alerts)) == 1
    assert paused(alerts)[0]["ticker"] == "MSFTx"

    # 10d) Dedup independence (monkeypatched DB, zero prod reads/writes).
    orig_query, orig_execute = bot.db_query, bot.db_execute
    try:
        def fake_query(sql, args=None):
            # Closed alert recorded; paused alert NOT recorded.
            if args and args[1] == "redemption_paused":
                return [{"n": 0}]
            return [{"n": 1}]

        bot.db_query = fake_query
        assert bot.recent_alert_exists("TSLAx", "redemption") is True
        assert bot.recent_alert_exists("TSLAx", "redemption_paused") is False, \
            "closed alert must NOT suppress a paused alert (distinct keys)"

        bot.db_query = lambda sql, args=None: [{"n": 1}]
        assert bot.recent_alert_exists("TSLAx", "redemption_paused") is True, \
            "recorded paused alert must suppress a repeat paused alert"

        captured = {}

        def fake_execute(sql, args=None):
            captured["args"] = args

        bot.db_execute = fake_execute
        bot.record_alert(pb[0], "PAUSED TEXT", "2026-10-25T02:00:00Z")
        assert captured["args"][0] == "TSLAx"
        assert captured["args"][2] == "redemption_paused"
        assert captured["args"][1] == "2026-10-25T02:00:00Z"
    finally:
        bot.db_query, bot.db_execute = orig_query, orig_execute

    print("BOT ALERT TEST: PASS (13->13 per-ticker, EN+ID, mixed/single/empty, paused type+dedup independence)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
