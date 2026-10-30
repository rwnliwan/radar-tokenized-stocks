#!/usr/bin/env python3
"""Post-fix QA for the 2026-10-30 Turso read-burn optimization.

Read-only checks + one bot --once evaluation. Run daily for a few days after
the 2026-11-01 recovery to prove: no data loss, web API healthy, alert
pipeline evaluates normally.

Exit 0 = ALL PASS. Exit 1 = at least one FAIL (details in JSON on stdout).
"""
import datetime
import json
import subprocess
import sys

API = "https://api.omdanny.site"
CHAT_EN = "-1003867845895"
CHAT_ID = "-1004471605253"
ROOT = "/home/hatch/workspace/radar-tokenized-stocks"

results = []


def check(name, ok, detail=""):
    results.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
    return ok


def db_query(sql):
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from turso_client import query;"
        f"import json; print(json.dumps(query({sql!r})))"
    )
    r = subprocess.run(
        [".venv/bin/python", "-c", code],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-200:])
    return json.loads(r.stdout)


def curl_json(url, timeout=40):
    r = subprocess.run(
        ["curl", "--max-time", str(timeout), "-s", "-w", "\n%{http_code}", url],
        capture_output=True, text=True, timeout=timeout + 10)
    body, _, code = r.stdout.rpartition("\n")
    return int(code.strip() or 0), body


def parse_ts(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    all_ok = True

    # 1. DB readable + universe intact (13 tickers, 35 active pools)
    try:
        n_tick = int(db_query("SELECT COUNT(*) AS n FROM universe")[0]["n"])
        n_pool = int(db_query(
            "SELECT COUNT(*) AS n FROM pools WHERE is_active = 1")[0]["n"])
        all_ok &= check("universe_13_tickers", n_tick == 13, f"n={n_tick}")
        all_ok &= check("active_pools_35", n_pool == 35, f"n={n_pool}")
    except Exception as e:
        all_ok &= check("db_readable", False, e)

    # 2. Data freshness: poller resumed writing after unblock
    try:
        s_ts = db_query("SELECT MAX(ts) AS m FROM snapshots")[0]["m"]
        d_ts = db_query("SELECT MAX(ts) AS m FROM deviations")[0]["m"]
        s_age = (now - parse_ts(s_ts)).total_seconds() / 60 if parse_ts(s_ts) else 1e9
        d_age = (now - parse_ts(d_ts)).total_seconds() / 60 if parse_ts(d_ts) else 1e9
        all_ok &= check("snapshots_fresh_lt20m", s_age < 20, f"age={s_age:.1f}m ts={s_ts}")
        all_ok &= check("deviations_fresh_lt20m", d_age < 20, f"age={d_age:.1f}m ts={d_ts}")
    except Exception as e:
        all_ok &= check("freshness", False, e)

    # 3. Poller health: last cycle ok
    try:
        h = db_query(
            "SELECT cycle_ts, cycles_ok FROM poller_health ORDER BY id DESC LIMIT 1")[0]
        h_age = (now - parse_ts(h["cycle_ts"])).total_seconds() / 60 if parse_ts(h["cycle_ts"]) else 1e9
        all_ok &= check("poller_last_cycle_ok",
                        int(h["cycles_ok"]) == 1 and h_age < 20,
                        f"cycles_ok={h['cycles_ok']} age={h_age:.1f}m")
    except Exception as e:
        all_ok &= check("poller_health", False, e)

    # 4. Web API: /api/latest 200, 13 tickers, fields present, latest_ts fresh
    try:
        code, body = curl_json(API + "/api/latest")
        data = json.loads(body) if code == 200 else {}
        tickers = data.get("tickers", [])
        ok_n = len(tickers) == 13
        ok_fields = all(t.get("dev_bps") is not None and t.get("ticker") for t in tickers)
        lts = parse_ts((data.get("meta") or {}).get("latest_ts"))
        lts_age = (now - lts).total_seconds() / 60 if lts else 1e9
        all_ok &= check("api_200", code == 200, f"http={code}")
        all_ok &= check("api_13_tickers", ok_n, f"n={len(tickers)}")
        all_ok &= check("api_fields_valid", ok_fields, "dev_bps+ticker present" if ok_fields else "missing fields")
        all_ok &= check("api_latest_ts_fresh", lts_age < 20, f"age={lts_age:.1f}m")
    except Exception as e:
        all_ok &= check("api_latest", False, e)

    # 5. Alert pipeline: bot --once evaluates without error
    # (genuine alerts may send per the code's own thresholds/dedup; no test sends)
    try:
        r = subprocess.run(
            ["python3", "bot.py", "--once", "--offset-file",
             "/home/hatch/workspace/goals/radar-tokenized-stocks-kabar-berkala/hidden_files/bot_updates.json"],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
            env={"PATH": "/usr/bin:/bin",
                 "RADAR_ALERT_CHAT_ID_EN": CHAT_EN,
                 "RADAR_ALERT_CHAT_ID_ID": CHAT_ID})
        err = "evaluation error" in (r.stdout + r.stderr).lower()
        all_ok &= check("bot_once_no_eval_error",
                        r.returncode == 0 and not err,
                        f"rc={r.returncode}" + (" EVAL_ERROR" if err else ""))
    except Exception as e:
        all_ok &= check("bot_once", False, e)

    verdict = "PASS" if all(results) else "FAIL"
    print(json.dumps({"verdict": verdict,
                      "checked_at_utc": now.isoformat(),
                      "results": results}, indent=1))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
