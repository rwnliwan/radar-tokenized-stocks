"""Bot redemption-batch test: one message per status group, never
one message per ticker (Wave-3 follow-up to the batching decision).

Pure + monkeypatched-DB only: no network, no token access, no prod
writes. Covers:
- 13 closed tickers -> exactly 1 redemption_batch alert listing all 13;
- EN + ID formats render in their own languages (no ID leak into EN);
- forbidden words still pass on both messages;
- mixed statuses (closed + gated) -> separate batches per status;
- single ticker -> one-item batch formats correctly;
- empty group -> no alert; 'paused' IS a trigger with its own batch
  type ('redemption_batch_paused') and dedup key;
- batch dedup key ('ALL', 'redemption_batch') suppresses repeats
  within 24h, and record_alert writes one row for the batch;
- paused batch: a recorded closed batch does NOT suppress a paused
  batch (distinct keys); a recorded paused batch DOES suppress a
  repeat paused batch; EN+ID render with high-priority marker, no
  leaks, no forbidden words.
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


def batches(alerts):
    return [a for a in alerts if a["type"] == "redemption_batch"]


def paused_batches(alerts):
    return [a for a in alerts if a["type"] == "redemption_batch_paused"]


def check_forbidden(msg, where):
    for w in FORBIDDEN:
        assert not re.search(rf"\b{w}\b", msg, re.IGNORECASE), \
            f"forbidden word {w!r} in {where}: {msg[:200]}"


def main():
    # 1) 13 closed -> exactly 1 batch listing all 13, no per-ticker redemption.
    data = [mk(t, dw=100.0 + i) for i, t in enumerate(TICKERS_13)]
    alerts = bot.evaluate_alerts(data, False)
    b = batches(alerts)
    assert len(b) == 1, f"expected 1 batch, got {len(b)}: {alerts}"
    assert b[0]["ticker"] == "ALL" and b[0]["status"] == "closed"
    assert b[0]["tickers"] == TICKERS_13, f"batch tickers: {b[0]['tickers']}"
    assert not [a for a in alerts if a["type"] == "redemption"], \
        "per-ticker redemption alerts must no longer be emitted"
    assert len(b[0]["members"]) == 13

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
    assert types == ["deviation_high", "por", "redemption_batch", "spread"], \
        f"unexpected alert types: {types}"
    assert batches(alerts)[0]["tickers"] == TICKERS_13[:3]

    # 3) EN format: all tickers, next opening, EN note/disclaimer, no ID leak.
    msg_en = bot.format_alert(b[0], "en")
    for t in TICKERS_13:
        assert t in msg_en, f"missing ticker {t} in EN batch"
    assert "Next opening: 2026-10-26T04:00:00Z" in msg_en
    assert "not confirmed live by the issuer" in msg_en
    assert "Not financial advice" in msg_en
    assert "https://radar.omdanny.site/" in msg_en
    assert "Status dihitung dari jadwal" not in msg_en, "ID note leaked into EN"
    assert "Bukan nasihat keuangan" not in msg_en, "ID disclaimer leaked into EN"
    assert "Dari jadwal" not in msg_en, "DB window_note leaked into EN"
    assert "Depth-weighted price" in msg_en
    assert len(msg_en) < 4096, f"EN batch too long: {len(msg_en)}"
    check_forbidden(msg_en, "EN batch")

    # 4) ID format: all tickers, ID note/disclaimer, no EN leak.
    msg_id = bot.format_alert(b[0], "id")
    for t in TICKERS_13:
        assert t in msg_id, f"missing ticker {t} in ID batch"
    assert "Pembukaan berikutnya: 2026-10-26T04:00:00Z" in msg_id
    assert "bukan konfirmasi live dari issuer" in msg_id
    assert "Bukan nasihat keuangan" in msg_id
    assert "Not financial advice" not in msg_id, "EN disclaimer leaked into ID"
    assert "Harga tertimbang kedalaman" in msg_id
    assert len(msg_id) < 4096, f"ID batch too long: {len(msg_id)}"
    check_forbidden(msg_id, "ID batch")

    # 5) Mixed statuses -> separate batches per status.
    data = [mk(t) for t in TICKERS_13[:12]]
    gated = mk("MSFTx", status="gated")
    gated["next_open_at"] = None
    alerts = bot.evaluate_alerts(data + [gated], False)
    b = batches(alerts)
    assert len(b) == 2, f"expected 2 batches, got {len(b)}"
    by_status = {x["status"]: x for x in b}
    assert by_status["closed"]["tickers"] == TICKERS_13[:12]
    assert by_status["gated"]["tickers"] == ["MSFTx"]
    assert "terbatas (KYC)" in bot.format_alert(by_status["gated"], "id")

    # 6) Single ticker -> one-item batch, formats correctly.
    alerts = bot.evaluate_alerts([mk("SPYx")], False)
    b = batches(alerts)
    assert len(b) == 1 and b[0]["tickers"] == ["SPYx"]
    single_en = bot.format_alert(b[0], "en")
    assert "SPYx" in single_en and "closed" in single_en
    assert "Next opening: 2026-10-26T04:00:00Z" in single_en

    # 7) next_open_at fallback: within-24h, then dash.
    w24 = mk("SPYx")
    w24["next_open_at"] = None
    w24["closes_within_24h"] = True
    b = batches(bot.evaluate_alerts([w24], False))
    assert "within 24h" in bot.format_alert(b[0], "en")
    assert "dalam 24 jam" in bot.format_alert(b[0], "id")
    none_open = mk("SPYx")
    none_open["next_open_at"] = None
    b = batches(bot.evaluate_alerts([none_open], False))
    assert "Next opening: —" in bot.format_alert(b[0], "en")

    # 8) Empty group -> no alert; open/unknown still no alert.
    assert batches(bot.evaluate_alerts([mk("SPYx", status="open")], False)) == []
    assert bot.evaluate_alerts([mk("SPYx", status="unknown")], False) == []

    # 9) Dedup mechanism (monkeypatched DB, zero prod reads/writes).
    orig_query, orig_execute = bot.db_query, bot.db_execute
    try:
        calls = {}

        def fake_query(sql, args=None):
            calls["query"] = (sql, args)
            return [{"n": 1}]

        bot.db_query = fake_query
        assert bot.recent_alert_exists("ALL", "redemption_batch") is True
        assert calls["query"][1][0] == "ALL"
        assert calls["query"][1][1] == "redemption_batch"

        bot.db_query = lambda sql, args=None: [{"n": 0}]
        assert bot.recent_alert_exists("ALL", "redemption_batch") is False

        captured = {}

        def fake_execute(sql, args=None):
            captured["sql"] = sql
            captured["args"] = args

        bot.db_execute = fake_execute
        batch = batches(bot.evaluate_alerts([mk(t) for t in TICKERS_13], False))[0]
        bot.record_alert(batch, "BATCH TEXT", "2026-10-25T01:30:00Z")
        assert captured["args"][0] == "ALL", f"recorded ticker: {captured['args'][0]}"
        assert captured["args"][2] == "redemption_batch"
        assert captured["args"][1] == "2026-10-25T01:30:00Z"
    finally:
        bot.db_query, bot.db_execute = orig_query, orig_execute

    # 10) Paused: own batch type, high-priority render, dedup independence.
    pdata = [mk(t, status="paused", dw=100.0 + i) for i, t in enumerate(TICKERS_13)]
    alerts = bot.evaluate_alerts(pdata, False)
    pb = paused_batches(alerts)
    assert len(pb) == 1, f"expected 1 paused batch, got {len(pb)}"
    assert pb[0]["ticker"] == "ALL" and pb[0]["status"] == "paused"
    assert pb[0]["type"] == "redemption_batch_paused"
    assert pb[0]["tickers"] == TICKERS_13
    assert batches(alerts) == [], "paused must not emit a plain redemption_batch"
    # Single paused ticker -> one-item paused batch.
    single = paused_batches(bot.evaluate_alerts([mk("SPYx", status="paused")], False))
    assert len(single) == 1 and single[0]["tickers"] == ["SPYx"]

    # 10a) EN render: priority marker, paused status/note, no ID leak.
    msg_en = bot.format_alert(pb[0], "en")
    assert msg_en.splitlines()[0] == "🔴 REDEMPTION PAUSED — 13 tickers (xStocks)"
    assert "High priority: on-chain pause detected" in msg_en
    assert "paused (on-chain)" in msg_en
    assert "not confirmed live by the issuer" in msg_en
    assert "Next opening: —" in msg_en
    assert "Redemption stays halted until the pause is lifted." in msg_en
    for t in TICKERS_13:
        assert t in msg_en, f"missing ticker {t} in EN paused batch"
    assert "Prioritas tinggi" not in msg_en, "ID priority leaked into EN"
    assert "dijeda" not in msg_en, "ID status leaked into EN"
    assert "Dari jadwal" not in msg_en, "DB window_note leaked into EN"
    assert len(msg_en) < 4096
    check_forbidden(msg_en, "EN paused batch")

    # 10b) ID render: priority marker, paused status/note, no EN leak.
    msg_id = bot.format_alert(pb[0], "id")
    assert msg_id.splitlines()[0] == "🔴 REDEMPTION DIJEDA — 13 ticker (xStocks)"
    assert "Prioritas tinggi: jeda on-chain terdeteksi" in msg_id
    assert "dijeda (on-chain)" in msg_id
    assert "bukan konfirmasi live dari issuer" in msg_id
    assert "Redemption tetap berhenti sampai jeda dicabut." in msg_id
    assert "High priority" not in msg_id, "EN priority leaked into ID"
    assert "Not financial advice" not in msg_id, "EN disclaimer leaked into ID"
    assert len(msg_id) < 4096
    check_forbidden(msg_id, "ID paused batch")

    # 10c) Mixed closed + paused -> two batches, correct membership/types.
    cdata = [mk(t) for t in TICKERS_13[:12]]
    pdata1 = mk("MSFTx", status="paused")
    alerts = bot.evaluate_alerts(cdata + [pdata1], False)
    assert len(batches(alerts)) == 1
    assert batches(alerts)[0]["tickers"] == TICKERS_13[:12]
    assert len(paused_batches(alerts)) == 1
    assert paused_batches(alerts)[0]["tickers"] == ["MSFTx"]

    # 10d) Dedup independence (monkeypatched DB, zero prod reads/writes).
    orig_query, orig_execute = bot.db_query, bot.db_execute
    try:
        def fake_query(sql, args=None):
            # Closed batch recorded; paused batch NOT recorded.
            if args and args[1] == "redemption_batch_paused":
                return [{"n": 0}]
            return [{"n": 1}]

        bot.db_query = fake_query
        assert bot.recent_alert_exists("ALL", "redemption_batch") is True
        assert bot.recent_alert_exists("ALL", "redemption_batch_paused") is False, \
            "closed batch must NOT suppress a paused batch (distinct keys)"

        bot.db_query = lambda sql, args=None: [{"n": 1}]
        assert bot.recent_alert_exists("ALL", "redemption_batch_paused") is True, \
            "recorded paused batch must suppress a repeat paused batch"

        captured = {}

        def fake_execute(sql, args=None):
            captured["args"] = args

        bot.db_execute = fake_execute
        bot.record_alert(pb[0], "PAUSED TEXT", "2026-10-25T02:00:00Z")
        assert captured["args"][0] == "ALL"
        assert captured["args"][2] == "redemption_batch_paused"
        assert captured["args"][1] == "2026-10-25T02:00:00Z"
    finally:
        bot.db_query, bot.db_execute = orig_query, orig_execute

    print("BOT BATCH TEST: PASS (13->1 batch, EN+ID, mixed/single/empty, paused type+dedup independence)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
