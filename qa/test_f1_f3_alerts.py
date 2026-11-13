"""F1 (perp_deviation) + F3 (exit_high) alert paths (built 2026-11-13,
Septian ACC "Bangun aja").

DESAIN §2.2 (F1): alert |perp_px - dw| / dw >= 1.0%, high priority
>= 3.0%; gates: spot depth >= $250k + perp snapshot fresh (<= 15 min);
fires any time (perp trades 24/7). Deviation formula is the same as
api/worker.js perp_dev_pct.
DESAIN §2.4 (F3): exit_score (0-100 scale, exit_score_v2) >= 70,
1x/ticker/24h. M5 rule: fires only when exit_score_components >= 3 —
a partial score never fires "high" (live proof: TSLAB 82.0 on 1
component, 2026-11-13).

- (A) evaluate_alerts F1: below/at/above threshold, high-priority
  boundary, negative deviation, stale perp, missing perp, depth gate,
  dev_stale, missing dw, market-closed still fires, legacy dicts
  without perp keys do not crash or fire.
- (B) evaluate_alerts F3: score boundary 70.0, just-below, partial
  scores (comp 1 and 2, incl. the live TSLAB case), full scores,
  missing score/components, dev_stale.
- (C) format_alert EN + ID for both types: numbers, thresholds,
  components/version shown; factual language — no "sell"/"buy" in EN,
  no "jual"/"beli" in ID.
- (D) record_alert: perp records dev_pct, exit records the score
  (0-100); spread/deviation_high mapping unchanged.
- (E) load_live_tickers (stubbed DB): the live path actually populates
  perp_px/perp_fresh/exit_score/exit_score_components.
- (F) Dedup is the standard 24h per-channel rule (NOT once-per-window)
  for both new types.

Pure + stubbed-DB only: no network, no token, no Telegram send, no
production reads/writes. Run: python3 qa/test_f1_f3_alerts.py
(exit 0 = PASS).
"""
import os
import sys
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


def base_ticker(**over):
    d = {
        "ticker": "TSLAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 400.10, "reserve": 3000000.0}],
        "dw": 400.16, "dev_med": 0.10, "depth": 3000000.0,
        "pools_used": 2, "median": 400.13,
        "redemption_status": "open", "por_age_hours": 6.0,
        "perp_px": 400.16, "perp_px_source": "mark",
        "perp_ts": "2026-11-13T02:20:00Z", "perp_age_min": 4.0,
        "perp_fresh": True,
        "exit_score": 10.0, "exit_score_components": 4,
        "exit_score_version": "exit_score_v2",
    }
    d.update(over)
    return d


def of_type(alerts, t, ticker="TSLAx"):
    return [a for a in alerts if a["type"] == t and a["ticker"] == ticker]


# ---------------- (A) F1 evaluate_alerts ----------------
# below threshold: +0.50% -> none
a = bot.evaluate_alerts([base_ticker(perp_px=402.16)], False)
check("F1 below threshold +0.50% fires nothing",
      not of_type(a, "perp_deviation"), f"got {a}")
# 0.9996% (rounds to 1.000 at 3 decimals) -> STILL none: the threshold
# compares the unrounded value, so rounding never promotes an alert
a = bot.evaluate_alerts([base_ticker(perp_px=404.16)], False)
check("F1 +0.9996% fires nothing (no rounding promotion)",
      not of_type(a, "perp_deviation"), f"got {a}")
# just above threshold: +1.01% -> fires, normal priority.
# (Exact-boundary 1.0000000% is NOT asserted: in float arithmetic
# (404.1616-400.16)/400.16*100 computes to 0.99999... < 1.0, so the
# unrounded comparison — the same convention as spread/deviation_high
# — does not fire it. Real market data never lands exactly on the
# boundary; just-above/just-below is the meaningful contract.)
a = bot.evaluate_alerts([base_ticker(perp_px=404.2016)], False)
p = of_type(a, "perp_deviation")
check("F1 just above threshold +1.01% fires, normal priority",
      len(p) == 1 and p[0]["dev_pct"] == 1.01 and p[0]["high_priority"] is False,
      f"got {p}")
# +1.80% -> fires, normal priority, carries perp_px/source/age
a = bot.evaluate_alerts([base_ticker(perp_px=407.36)], False)
p = of_type(a, "perp_deviation")
check("F1 +1.80% fires with perp fields",
      len(p) == 1 and abs(p[0]["dev_pct"] - 1.8) < 0.01
      and p[0]["perp_px"] == 407.36 and p[0]["perp_px_source"] == "mark"
      and p[0]["perp_age_min"] == 4.0 and p[0]["high_priority"] is False,
      f"got {p}")
# just above the high boundary: +3.01% -> fires, HIGH priority
# (same float-boundary note as the +1.01% test above)
a = bot.evaluate_alerts([base_ticker(perp_px=412.2048)], False)
p = of_type(a, "perp_deviation")
check("F1 just above high boundary +3.01% fires HIGH priority",
      len(p) == 1 and p[0]["dev_pct"] == 3.01 and p[0]["high_priority"] is True,
      f"got {p}")
# +3.50% -> fires, HIGH priority
a = bot.evaluate_alerts([base_ticker(perp_px=414.17)], False)
p = of_type(a, "perp_deviation")
check("F1 +3.50% fires HIGH priority",
      len(p) == 1 and p[0]["high_priority"] is True, f"got {p}")
# negative deviation -1.50% -> fires on |dev|
# (394.1576 = 400.16 * 0.985 exactly)
a = bot.evaluate_alerts([base_ticker(perp_px=394.1576)], False)
p = of_type(a, "perp_deviation")
check("F1 -1.50% fires on |dev|",
      len(p) == 1 and p[0]["dev_pct"] == -1.5 and p[0]["high_priority"] is False,
      f"got {p}")
# stale perp snapshot -> none (even at +5%)
a = bot.evaluate_alerts([base_ticker(perp_px=420.17, perp_fresh=False,
                                     perp_age_min=22.0)], False)
check("F1 stale perp (22 min) fires nothing",
      not of_type(a, "perp_deviation"), f"got {a}")
# missing perp -> none
a = bot.evaluate_alerts([base_ticker(perp_px=None, perp_fresh=False,
                                     perp_age_min=None)], False)
check("F1 no perp fires nothing",
      not of_type(a, "perp_deviation"), f"got {a}")
# depth below $250k -> none
a = bot.evaluate_alerts([base_ticker(perp_px=407.36, depth=200000.0)], False)
check("F1 depth $200k fires nothing",
      not of_type(a, "perp_deviation"), f"got {a}")
# depth exactly $250k -> fires (boundary inclusive)
a = bot.evaluate_alerts([base_ticker(perp_px=407.36, depth=250000.0)], False)
check("F1 depth exactly $250k fires",
      len(of_type(a, "perp_deviation")) == 1, f"got {a}")
# dev_stale -> none (dw is hours-old)
d = base_ticker(perp_px=407.36)
d["dev_stale"] = True
a = bot.evaluate_alerts([d], False)
check("F1 dev_stale fires nothing",
      not of_type(a, "perp_deviation"), f"got {a}")
# dw missing -> none (no division by zero / no alert)
a = bot.evaluate_alerts([base_ticker(perp_px=407.36, dw=None)], False)
check("F1 dw None fires nothing",
      not of_type(a, "perp_deviation"), f"got {a}")
# market closed -> STILL fires (perp trades 24/7)
a = bot.evaluate_alerts([base_ticker(perp_px=407.36)], False)
check("F1 fires while market closed",
      len(of_type(a, "perp_deviation")) == 1, f"got {a}")
# legacy dict without any perp keys -> no crash, no F1 alert
legacy = {k: v for k, v in base_ticker().items()
          if not k.startswith("perp_")}
a = bot.evaluate_alerts([legacy], True)
check("F1 legacy dict (no perp keys) safe",
      not of_type(a, "perp_deviation"), f"got {a}")

# ---------------- (B) F3 evaluate_alerts ----------------
# exactly 70.0, 3 components -> fires (boundary inclusive)
a = bot.evaluate_alerts([base_ticker(exit_score=70.0,
                                     exit_score_components=3)], False)
e = of_type(a, "exit_high")
check("F3 70.0 with 3 components fires",
      len(e) == 1 and e[0]["score"] == 70.0 and e[0]["components"] == 3,
      f"got {e}")
# 69.9, 5 components -> none
a = bot.evaluate_alerts([base_ticker(exit_score=69.9,
                                     exit_score_components=5)], False)
check("F3 69.9 with 5 components fires nothing",
      not of_type(a, "exit_high"), f"got {a}")
# LIVE CASE: TSLAB 82.0 on 1 component -> must NOT fire
a = bot.evaluate_alerts([base_ticker(ticker="TSLAB", exit_score=82.0,
                                     exit_score_components=1)], False)
check("F3 TSLAB live case 82.0/1 comp fires nothing",
      not of_type(a, "exit_high", "TSLAB"), f"got {a}")
# 82.0 on 2 components -> must NOT fire
a = bot.evaluate_alerts([base_ticker(exit_score=82.0,
                                     exit_score_components=2)], False)
check("F3 82.0/2 comp fires nothing",
      not of_type(a, "exit_high"), f"got {a}")
# 75.0 on 3 components -> fires, carries version + dev
a = bot.evaluate_alerts([base_ticker(exit_score=75.0,
                                     exit_score_components=3, dev_med=2.1)], False)
e = of_type(a, "exit_high")
check("F3 75.0/3 comp fires with version+dev",
      len(e) == 1 and e[0]["version"] == "exit_score_v2"
      and e[0]["dev_pct"] == 2.1, f"got {e}")
# 100.0 on 5 components -> fires
a = bot.evaluate_alerts([base_ticker(exit_score=100.0,
                                     exit_score_components=5)], False)
check("F3 100.0/5 comp fires",
      len(of_type(a, "exit_high")) == 1, f"got {a}")
# missing score -> none
a = bot.evaluate_alerts([base_ticker(exit_score=None,
                                     exit_score_components=5)], False)
check("F3 score None fires nothing",
      not of_type(a, "exit_high"), f"got {a}")
# missing components -> none (cannot prove full score)
a = bot.evaluate_alerts([base_ticker(exit_score=80.0,
                                     exit_score_components=None)], False)
check("F3 components None fires nothing",
      not of_type(a, "exit_high"), f"got {a}")
# dev_stale -> none (score rides the dev row)
d = base_ticker(exit_score=80.0, exit_score_components=5)
d["dev_stale"] = True
a = bot.evaluate_alerts([d], False)
check("F3 dev_stale fires nothing",
      not of_type(a, "exit_high"), f"got {a}")
# legacy dict without exit keys -> no crash, no F3 alert
legacy = {k: v for k, v in base_ticker().items()
          if not k.startswith("exit_")}
a = bot.evaluate_alerts([legacy], True)
check("F3 legacy dict (no exit keys) safe",
      not of_type(a, "exit_high"), f"got {a}")

# ---------------- (C) format_alert EN + ID ----------------
perp_alert = of_type(bot.evaluate_alerts(
    [base_ticker(perp_px=407.36)], False), "perp_deviation")[0]
en = bot.format_alert(perp_alert, "en")
check("F1 EN text: numbers + threshold + source",
      "+1.80%" in en and "1.0%" in en and "mark" in en
      and "Hyperliquid XYZ" in en and "407.36" in en, en.split("\n")[2][:120])
check("F1 EN text: no sell/buy language",
      "sell" not in en.lower() and "buy" not in en.lower(), en.split("\n")[0])
idn = bot.format_alert(perp_alert, "id")
check("F1 ID text: numbers + ambang",
      "+1.80%" in idn and "ambang 1.0%" in idn and "Hyperliquid XYZ" in idn,
      idn.split("\n")[2][:120])
check("F1 ID text: no jual/beli language",
      "jual" not in idn.lower() and "beli" not in idn.lower(), idn.split("\n")[0])
high_alert = of_type(bot.evaluate_alerts(
    [base_ticker(perp_px=414.17)], False), "perp_deviation")[0]
check("F1 HIGH text marks priority EN+ID",
      "HIGH PRIORITY" in bot.format_alert(high_alert, "en")
      and "PRIORITAS TINGGI" in bot.format_alert(high_alert, "id"), "")
exit_alert = of_type(bot.evaluate_alerts(
    [base_ticker(exit_score=74.5, exit_score_components=4)], False),
    "exit_high")[0]
en = bot.format_alert(exit_alert, "en")
check("F3 EN text: score + band + components + version",
      "74.5" in en and "70" in en and "4 of 5" in en
      and "exit_score_v2" in en, en.split("\n")[2][:140])
check("F3 EN text: no sell/buy/exit-now language",
      "sell" not in en.lower() and "buy" not in en.lower()
      and "exit now" not in en.lower(), en.split("\n")[0])
idn = bot.format_alert(exit_alert, "id")
check("F3 ID text: score + band + components",
      "74.5" in idn and "70" in idn and "4 dari 5" in idn,
      idn.split("\n")[2][:140])
check("F3 ID text: no jual/beli language",
      "jual" not in idn.lower() and "beli" not in idn.lower(), idn.split("\n")[0])
# missing dev_med renders as —, never crashes
no_dev = of_type(bot.evaluate_alerts(
    [base_ticker(exit_score=74.5, exit_score_components=4, dev_med=None)],
    False), "exit_high")[0]
check("F3 missing dev_med renders —",
      "—" in bot.format_alert(no_dev, "en"), "")

# ---------------- (D) record_alert mapping ----------------
captured = {}
orig_execute = bot.db_execute


def fake_execute(sql, args=None):
    captured.setdefault("calls", []).append((sql, args))
    return {}


bot.db_execute = fake_execute
try:
    bot.record_alert(perp_alert, "msg-perp", "2026-11-13T02:30:00Z",
                     channel="en:-1")
    sql, args = captured["calls"][-1]
    check("record_alert perp: threshold+dev = dev_pct",
          args[3] == perp_alert["dev_pct"]
          and args[4] == perp_alert["dev_pct"], f"args={args}")
    bot.record_alert(exit_alert, "msg-exit", "2026-11-13T02:30:00Z",
                     channel="en:-1")
    sql, args = captured["calls"][-1]
    check("record_alert exit: threshold+dev = score",
          args[3] == 74.5 and args[4] == 74.5, f"args={args}")
    spread_alert = bot.evaluate_alerts([{
        "ticker": "TSLAx", "issuer": "xStocks",
        "venues": [{"dex": "raydium", "price": 371.16, "reserve": 2380000.0},
                   {"dex": "orca", "price": 374.90, "reserve": 500000.0}],
        "dw": 371.81, "dev_med": 0.35, "depth": 2880000.0,
        "pools_used": 2, "median": 373.03,
        "redemption_status": "open", "por_age_hours": 6.0,
    }], True)
    bot.record_alert(spread_alert[0], "msg-spread", "2026-11-13T02:30:00Z",
                     channel="en:-1")
    sql, args = captured["calls"][-1]
    check("record_alert spread unchanged (spread_pct)",
          args[3] == spread_alert[0]["spread_pct"]
          and args[4] == spread_alert[0]["spread_pct"], f"args={args}")
finally:
    bot.db_execute = orig_execute

# ---------------- (E) load_live_tickers (stubbed DB) ----------------
NOW = datetime(2026, 11, 13, 2, 30, tzinfo=UTC)
REAL_NOW = datetime.now(UTC)


def fake_query(sql, args=None):
    if "FROM universe ORDER BY tier" in sql:
        return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
    if "FROM deviations" in sql:
        return [{"ticker_id": "TSLAx",
                 "ts": (REAL_NOW - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "depth_weighted_price": 400.16,
                 "dev_vs_median_pct": 0.10,
                 "qualifying_depth_usd": 3000000.0, "pools_used": 2,
                 "exit_score": 74.5, "exit_score_version": "exit_score_v2",
                 "exit_score_components": 4}]
    if "FROM perp_snapshots" in sql:
        return [{"ticker_id": "TSLAx",
                 "ts": (NOW - timedelta(minutes=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "perp_px": 407.36, "perp_px_source": "mark"}]
    if "FROM redemption_windows" in sql:
        return [{"status": "open", "window_note": None, "next_open_at": None}]
    if "FROM por_feeds" in sql:
        return [{"age_hours": 6.0,
                 "last_update_ts": (REAL_NOW - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
    if "FROM pools p" in sql:
        return [{"dex": "raydium", "price_usd": 400.10, "reserve_usd": 3000000.0}]
    raise AssertionError(f"unexpected query: {sql[:100]}")


orig_query = bot.db_query
bot.db_query = fake_query
try:
    tickers = bot.load_live_tickers(now_utc=NOW)
finally:
    bot.db_query = orig_query
check("load_live_tickers returns 1 ticker", len(tickers) == 1,
      f"got {len(tickers)}")
t = tickers[0] if tickers else {}
check("load_live_tickers populates perp fields",
      t.get("perp_px") == 407.36 and t.get("perp_px_source") == "mark"
      and t.get("perp_fresh") is True
      and abs(t.get("perp_age_min", -1) - 4.0) < 0.01, f"got {t}")
check("load_live_tickers populates exit fields",
      t.get("exit_score") == 74.5 and t.get("exit_score_components") == 4
      and t.get("exit_score_version") == "exit_score_v2", f"got {t}")
check("load_live_tickers row evaluates to BOTH new alerts",
      [a["type"] for a in bot.evaluate_alerts(tickers, False)]
      == ["perp_deviation", "exit_high"],
      f"got {bot.evaluate_alerts(tickers, False)}")

# (E2) REGRESSION — live Turso returns INTEGER columns as STRINGS
# (hrana protocol): exit_score_components arrives as "4", and a bare
# `>= 3` on it raised TypeError in --evaluate-live before the fix.
# load_live_tickers must coerce it to int (same int() pattern as
# load_health_age_minutes' cycles_ok).


def fake_query_strcomp(sql, args=None):
    if "FROM universe ORDER BY" in sql:
        return [{"ticker_id": "TSLAx", "issuer": "xStocks"}]
    if "FROM deviations" in sql:
        return [{"ticker_id": "TSLAx",
                 "ts": (REAL_NOW - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "depth_weighted_price": 400.16,
                 "dev_vs_median_pct": 0.10,
                 "qualifying_depth_usd": 3000000.0, "pools_used": 2,
                 "exit_score": 74.5, "exit_score_version": "exit_score_v2",
                 "exit_score_components": "4"}]
    if "FROM perp_snapshots" in sql:
        return []
    if "FROM redemption_windows" in sql:
        return [{"status": "open", "window_note": None, "next_open_at": None}]
    if "FROM por_feeds" in sql:
        return [{"age_hours": 6.0,
                 "last_update_ts": (REAL_NOW - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
    if "FROM pools p" in sql:
        return [{"dex": "raydium", "price_usd": 400.10, "reserve_usd": 3000000.0}]
    raise AssertionError(f"unexpected query: {sql[:100]}")


bot.db_query = fake_query_strcomp
try:
    tickers_s = bot.load_live_tickers(now_utc=NOW)
finally:
    bot.db_query = orig_query
check("load_live_tickers coerces string components '4' to int 4",
      tickers_s and tickers_s[0].get("exit_score_components") == 4
      and isinstance(tickers_s[0].get("exit_score_components"), int),
      f"got {tickers_s[0].get('exit_score_components') if tickers_s else None!r}")
check("string components still evaluate to exit_high (no TypeError)",
      [a["type"] for a in bot.evaluate_alerts(tickers_s, False)] == ["exit_high"],
      f"got {bot.evaluate_alerts(tickers_s, False)}")

# ---------------- (F) dedup: standard 24h, not window rule ----------------
check("new types use 24h dedup (not window rule)",
      "perp_deviation" not in bot.REDEMPTION_WINDOW_STATUSES
      and "exit_high" not in bot.REDEMPTION_WINDOW_STATUSES, "")


def fake_query_dedup(sql, args=None):
    if "FROM alert_log" in sql:
        return [{"n": fake_query_dedup.n}]
    raise AssertionError(f"unexpected query: {sql[:100]}")


fake_query_dedup.n = 0
bot.db_query = fake_query_dedup
try:
    reason = bot.suppression_reason(perp_alert, channel="en:-1")
    check("dedup: no prior row -> may fire", reason is None, f"got {reason}")
    fake_query_dedup.n = 1
    reason = bot.suppression_reason(perp_alert, channel="en:-1")
    check("dedup: prior row <24h -> suppressed",
          reason == "dedup 24h", f"got {reason}")
    reason = bot.suppression_reason(exit_alert, channel="en:-1")
    check("dedup: exit_high prior row <24h -> suppressed",
          reason == "dedup 24h", f"got {reason}")
finally:
    bot.db_query = orig_query

print()
if FAILURES:
    print(f"FAILURES: {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
