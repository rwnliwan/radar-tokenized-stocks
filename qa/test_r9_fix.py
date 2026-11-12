"""Round-9 fix tests (Radar: 1 must / 4 should / 5 nit / 2 gap).

Pure + stubbed only: no network, no token, no Telegram send, no live
DB reads/writes (the live PRAGMA for P1-4 is a manual pre-fix step,
recorded in the fix report — this file asserts the REPO side only:
schema.sql + migration).

Guard-gap locks (perintah Septian 00:23 + 00:53 — self-learning loop).
Every class below is locked at the CLASS level (general pattern),
not just the one string/case that surfaced in round 9. Where a guard
can honestly only lock the specific case, the limitation is stated
in the section docstring.

- GG-30 (freshness single-path; R9 P1-1 + P1-3): EVERY render path
  that shows a verdict / live deviation must survive "fetch failed
  repeatedly + old verdict retained" and must exclude stale tickers
  — table, bar chart, radar blips, verdict hero, row cards, detail
  page. R6 S-new-6 fixed HomeClient only; R7 M1 fixed the bar chart
  only; both times the sibling path was missed.
- GG-31 (future timestamps; R9 P2-1, lanjutan GG-15): the list of
  timestamp consumers is DERIVED FROM GREP (fromisoformat /
  Date.parse / age comparisons / total_seconds) over the whole repo,
  never a hand-written list — _hourly_due was missed in R8 exactly
  because the list was hand-written. Any grep site whose enclosing
  function is not in the registry FAILS, forcing triage.
- GG-32 (ignored return values; R9 P2-2, lanjutan GG-16): EVERY
  bool-returning function in bot.py / poller.py / dashboard/*.py
  has all its call sites checked for use of the value. A bare call
  fails unless it is in the KNOWN_BARE registry with a comment at
  the call site explaining why the outcome is recorded elsewhere.
- GG-34 (schema drift; R9 P1-4): every column in an INSERT column
  list (strict, per-table) and every column in a SELECT list
  (union-attributed over the statement's tables) must be declared
  in schema.sql OR migrations/ (ADD COLUMN). A column the code
  writes but the schema never declares fails.
- GG-17 central (F2 runtime; Terra-new R-1): a negative number
  rendered at RUNTIME must start with U+2212, not ASCII hyphen —
  fmtSigned/fmtSigned1/fmtPct are exercised through the real
  formatter, not grepped. LIMITATION (honest): prose literals in
  i18n.ts are scanned for ASCII-hyphen+digit, and the dashboard is
  covered only through fmt_abbr (its one signed-capable renderer);
  any future signed dashboard renderer needs its own F2 case.
- GG-15 strengthened (one-directional freshness): _hourly_due with
  a FUTURE last/failed stamp is due (never suppressed), and the
  three web ageMin fallbacks treat a negative age as stale, never
  as "just now" / fresh.

Thresholds are NOT changed here (spread 1.0%, dev 3.0%, depth $250k,
dedup 24h, stale gate 30 min, per-ticker stale 15 min, PoR 72h).
Gate A1 numbers and methodology Option A are untouched.

Usage: python3 qa/test_r9_fix.py  (exit 0 = PASS)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks")
sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
import bot  # noqa: E402
import poller  # noqa: E402
import logic as dash_logic  # noqa: E402
import risk as dash_risk  # noqa: E402

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
UTC = timezone.utc
FAILURES = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def block(src, start_marker, end_marker):
    i = src.find(start_marker)
    if i < 0:
        return ""
    j = src.find(end_marker, i)
    return src[i:] if j < 0 else src[i:j]


def main():
    now = datetime.now(UTC).replace(microsecond=0)
    tmp = tempfile.mkdtemp(prefix="r9_radar_")

    # =====================================================================
    # GG-30 — freshness: every render path, not just the reported one
    # =====================================================================
    home = read("web/src/app/HomeClient.tsx")
    detail = read("web/src/app/ticker/[id]/page.tsx")

    blips = block(home, "const blips = useMemo", "}, [data]);")
    check("GG30 radar blips exclude stale tickers (P1-3)",
          "!r.stale" in blips and "dev_bps != null" in blips,
          blips[:160].replace("\n", " "))
    plotted = block(home, "const plotted = useMemo", "}, [rows]);")
    check("GG30 bar chart still excludes stale tickers (R7 M1 holds)",
          "!r.stale" in plotted, plotted[:160].replace("\n", " "))
    worst = block(home, "const worst = useMemo", "}, [data]);")
    check("GG30 verdict hero (worst dev) skips stale tickers",
          "r.stale" in worst, worst[:200].replace("\n", " "))
    worst_spread = block(home, "const worstSpread = useMemo", "}, [data]);")
    check("GG30 verdict hero (worst spread) skips stale tickers",
          "r.stale" in worst_spread, worst_spread[:200].replace("\n", " "))
    min_depth = block(home, "const minDepth = useMemo", "}, [data]);")
    check("GG30 verdict hero (min depth) skips stale tickers",
          "r.stale" in min_depth, min_depth[:200].replace("\n", " "))
    # Every dev_bps filter in HomeClient either excludes stale or is
    # itself the stale/not-plotted list — or chains off `plotted`,
    # which already excludes stale (asserted above).
    filters = re.findall(
        r"(\w+)\s*\.filter\(\(r\) => ([^)]+)\)", home)
    bad_filters = [(recv, f) for recv, f in filters
                   if "dev_bps" in f and "stale" not in f
                   and recv != "plotted"]
    check("GG30 every dev_bps filter in HomeClient mentions stale",
          not bad_filters, f"filters without stale: {bad_filters}")
    rowcards = block(home, '<div className="rowcards">', "{rows.length === 0")
    check("GG30 row cards show the stale pill (same as the table)",
          "ticker_stale" in rowcards, "no ticker_stale in rowcards block")
    # GG-30: the MAIN ticker table's tbody — not the first <tbody> in
    # the file (the coverage table added 2026-11-12 sits above it).
    main_tbl = home.find('exit_score_col')
    table = block(home[main_tbl:], "<tbody>", "</tbody>")
    check("GG30 table still shows the stale pill",
          "ticker_stale" in table)

    # Detail page (P1-1, opsi b): a retained detail must NEVER let its
    # old health_stale outrank a live /api/health verdict, and a
    # failed health fetch while old detail is shown forces stale +
    # shows a failure indicator.
    check("GG30 detail tracks whether the shown detail is retained "
          "after a failed fetch (detailFailed flag)",
          re.search(r"detailFailed|detailRetained|retainedDetail", detail)
          is not None)
    check("GG30 detail tracks a failed health fetch (healthFailed flag)",
          "healthFailed" in detail)
    stale_expr = re.search(r"const stale = (.*?);", detail, re.S)
    stale_line = stale_expr.group(1) if stale_expr else ""
    check("GG30 detail stale verdict prefers live health when the "
          "detail is retained",
          ("detailFailed" in stale_line or "retained" in stale_line.lower())
          and "health" in stale_line,
          f"stale expr: {stale_line[:160]}")
    check("GG30 detail stale verdict forces stale when the health "
          "fetch failed",
          "healthFailed" in stale_line, f"stale expr: {stale_line[:160]}")
    check("GG30 detail shows a failure indicator while old detail is "
          "kept (error && detail renders an errorbox)",
          re.search(r"\{error && detail &&", detail) is not None)
    check("GG30 detail shows a failure indicator when the health "
          "fetch failed (healthFailed && detail)",
          re.search(r"\{healthFailed && detail &&", detail) is not None)
    check("GG30 detail no longer takes detail.health_stale as the "
          "unconditional first verdict (the old one-line form is gone)",
          re.search(r"const healthStale = detail\?\.health_stale", detail) is None)

    # =====================================================================
    # GG-31 — future timestamps: grep-derived consumer registry
    # =====================================================================
    # Registry: (relative path, enclosing function) -> how a future
    # timestamp is handled there. The scanner below derives the site
    # list from grep; ANY site not in this registry FAILS.
    KNOWN_TS = {
        ("bot.py", "py:parse_ts"): "definition only; callers decide",
        ("bot.py", "py:closes_within_24h"): "future expected; requires 0h < delta <= 24h",
        ("bot.py", "py:fmt_next_open"): "renders a FUTURE date (next open); not an age",
        ("bot.py", "py:evaluate_alerts"): "stored por_age_hours only; negative age cannot trip >72h",
        ("bot.py", "py:load_live_tickers"): "future dev ts -> dev_stale; future PoR last_update ignored",
        ("bot.py", "py:load_health_age_minutes"): "future last success -> None (stale)",
        ("bot.py", "py:_prune_fallback_markers"): "future marker kept/suppressing (fail-closed for sends)",
        ("bot.py", "py:_fallback_suppressed"): "future marker suppresses (fail-closed for sends)",
        ("bot.py", "py:notify_admin_poller_troubled"): "future state ignored; throttle never suppresses on a future stamp",
        ("bot.py", "py:data_still_fresh"): "delegates to load_health_age_minutes (None -> False)",
        ("bot.py", "py:main"): "delegates to load_health_age_minutes (None/age>30 -> stale gate)",
        ("poller.py", "py:parse_por_ts"): "definition; caller filters future (dt <= now_utc)",
        ("poller.py", "py:run_hourly_por"): "future tokens excluded before oldest() (dt <= now_utc); max(0,..) unreachable for future",
        ("poller.py", "py:_hourly_due"): "future last/failed stamp -> DUE (never suppresses the slot)",
        ("poller.py", "py:main"): "test fixture (in_tight_window) + sleep clamp; not a freshness verdict",
        ("dashboard/logic.py", "py:parse_ts"): "definition only; callers decide",
        ("dashboard/logic.py", "py:freshness_status"): "future last success -> stale (age_min < 0)",
        ("dashboard/logic.py", "py:por_effective_age_hours"): "future last_update ignored; stored age stands",
        ("dashboard/risk.py", "py:por_component"): "stored age_hours only; negative age cannot trip >=72h",
        ("dashboard/risk.py", "py:_as_date"): "definition; calibration_progress ignores dates after now",
        ("dashboard/app.py", "py:render_weekly_story"): "display span (last-first); not a freshness verdict",
        ("api/worker.js", "js:tickerFreshness"): "future dev_ts -> stale (ageMin < 0)",
        ("api/worker.js", "js:reevaluateFreshness"): "future last_success_ts -> stale (ageMin < 0)",
        ("api/worker.js", "js:porEffectiveAge"): "future last_update ignored; stored age stands",
        ("api/worker.js", "js:healthSummary"): "future last_success_ts -> stale (ageMin < 0)",
        ("web/src/app/Header.tsx", "js:autoFresh"): "future autoTs -> no freshness claim (renders nothing)",
        ("web/src/app/HomeClient.tsx", "js:ageMin"): "negative age -> stale fallback (ageMin < 0)",
        ("web/src/app/HomeClient.tsx", "js:stale"): "negative age -> stale fallback (ageMin < 0)",
        ("web/src/app/HomeClient.tsx", "js:freshnessText"): "negative age never reads 'just now'",
        ("web/src/app/ticker/page.tsx", "js:ageMin"): "negative age -> stale fallback (ageMin < 0)",
        ("web/src/app/ticker/page.tsx", "js:stale"): "negative age -> stale fallback (ageMin < 0)",
        ("web/src/app/ticker/[id]/page.tsx", "js:latestAgeMin"): "future latest_ts -> plain time, never '0 min ago'",
        ("web/src/app/ticker/Chart.tsx", "js:model"): "plot only; points are drawn at their own ts, no freshness verdict",
    }
    AGE_PATTERNS = [
        re.compile(r"fromisoformat"),
        re.compile(r"Date\.parse"),
        re.compile(r"\b(age\w*|live_age|since_min|delta_h)\s*(?:<|>|<=|>=|==|!=)"),
        re.compile(r"total_seconds\(\)"),
    ]
    SKIP_PREFIXES = ("#", "//", "*", "-", '"""', '"', ">")
    scan_roots = ["bot.py", "poller.py", "dashboard/logic.py",
                  "dashboard/risk.py", "dashboard/app.py",
                  "dashboard/turso_read.py", "api/worker.js", "web/src"]
    unknown_ts = []
    seen_ts = set()
    for root in scan_roots:
        files = []
        if os.path.isdir(os.path.join(ROOT, root)):
            for dp, dn, fn in os.walk(os.path.join(ROOT, root)):
                dn[:] = [d for d in dn
                         if d not in ("node_modules", "__pycache__", ".next",
                                      ".vercel", "assets")]
                files += [os.path.join(dp, f) for f in fn
                          if f.endswith((".py", ".ts", ".tsx", ".js"))]
        else:
            files = [os.path.join(ROOT, root)]
        for fp in files:
            rel = os.path.relpath(fp, ROOT)
            lines = open(fp, encoding="utf-8", errors="ignore").read().splitlines()
            func = "?"
            in_doc = False
            for i, ln in enumerate(lines, 1):
                if ln.count('"""') % 2 or ln.count("'''") % 2:
                    in_doc = not in_doc
                m = re.match(r"\s*def (\w+)", ln)
                if m:
                    func = "py:" + m.group(1)
                if fp.endswith(".js"):
                    # Plain .js (worker.js): functions are top-level;
                    # consts inside them are NOT contexts.
                    m2 = re.match(r"\s*(?:export )?(?:async )?function (\w+)", ln)
                    if m2:
                        func = "js:" + m2.group(1)
                elif fp.endswith((".ts", ".tsx")):
                    # TSX component body: 2-space consts are contexts
                    # (ageMin, stale, freshnessText, model, autoFresh);
                    # deeper consts (inside callbacks) are not.
                    m2 = (re.match(r"\s*(?:export )?(?:default )?(?:async )?function (\w+)", ln)
                          or re.match(r"  const (\w+)\s*=", ln))
                    if m2:
                        func = "js:" + m2.group(1)
                stripped = ln.strip()
                if in_doc or stripped.startswith(SKIP_PREFIXES):
                    continue
                if any(p.search(ln) for p in AGE_PATTERNS):
                    key = (rel, func)
                    seen_ts.add(key)
                    if key not in KNOWN_TS:
                        unknown_ts.append(f"{rel}:{i} [{func}] {stripped[:100]}")
    check("GG31 grep-derived timestamp-consumer registry covers "
          "EVERY site (no unregistered consumer)",
          not unknown_ts, f"unknown: {unknown_ts[:6]}")
    missing_reg = [k for k in KNOWN_TS if k not in seen_ts]
    check("GG31 registry has no stale entries (every entry still "
          "exists in the grep)",
          not missing_reg, f"stale registry entries: {missing_reg}")

    # Behavioral: _hourly_due (P2-1 — the R8 miss).
    fut = (now + timedelta(hours=2)).isoformat()
    past_recent = (now - timedelta(minutes=10)).isoformat()
    check("GG31/GG15 _hourly_due: FUTURE last_hourly_check is DUE "
          "(never suppresses the slot)",
          poller._hourly_due(now, {"last_hourly_check": fut}) is True)
    check("GG31/GG15 _hourly_due: FUTURE last_hourly_failed_at is DUE "
          "(no 15-min backoff from a future stamp)",
          poller._hourly_due(
              now, {"last_hourly_check": (now - timedelta(hours=2)).isoformat(),
                    "last_hourly_failed_at": fut}) is True)
    check("GG31 _hourly_due: recent successful run still suppresses",
          poller._hourly_due(now, {"last_hourly_check": past_recent}) is False)
    check("GG31 _hourly_due: unparseable stamp is DUE (fail-open "
          "towards running, as before)",
          poller._hourly_due(now, {"last_hourly_check": "not-a-date"}) is True)
    # Behavioral: the other age consumers, future direction.
    orig_q = bot.db_query
    try:
        bot.db_query = lambda sql, args=None: [
            {"cycle_ts": (now + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "cycles_ok": 1}]
        check("GG31 bot load_health_age_minutes: future last success "
              "reads stale (None)",
              bot.load_health_age_minutes(now) is None)
    finally:
        bot.db_query = orig_q
    fs = dash_logic.freshness_status(
        [{"cycle_ts": (now + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "cycles_ok": 1}], now)
    check("GG31 dashboard freshness_status: future last success is stale",
          fs["stale"] is True, f"age_min={fs['age_min']}")
    check("GG31 dashboard por_effective_age_hours: future last_update "
          "with no stored age is unknown",
          dash_logic.por_effective_age_hours(
              None, (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), now) is None)
    cal = dash_risk.calibration_progress(
        [(now + timedelta(days=30)).date()], now=now.date())
    check("GG31 calibration_progress: a future weekend date does not "
          "inflate the count",
          cal["weekends_observed"] == 0, f"cal={cal}")
    # Worker source: every freshness function handles ageMin < 0.
    worker = read("api/worker.js")
    for fn in ("tickerFreshness", "reevaluateFreshness", "healthSummary"):
        fn_src = block(worker, f"function {fn}(", "\n}\n")
        check(f"GG31 worker {fn}: future age reads stale (ageMin < 0)",
              "ageMin < 0" in fn_src, fn_src[:120].replace("\n", " "))
    por_fn = block(worker, "function porEffectiveAge(", "\n}\n")
    check("GG31 worker porEffectiveAge: future last_update ignored "
          "(liveMs >= 0 guard)",
          "liveMs >= 0" in por_fn)
    # Web source: negative ages never read fresh.
    check("GG31 HomeClient stale fallback treats a negative age as stale",
          "ageMin < 0" in home)
    check("GG31 HomeClient never renders 'just now' for a negative age",
          not re.search(r"ageMin <= 0", home))
    ticker_idx = read("web/src/app/ticker/page.tsx")
    check("GG31 ticker index stale fallback treats a negative age as stale",
          "ageMin < 0" in ticker_idx)
    check("GG31 detail header never clamps a future latest_ts to '0 min'",
          "Math.max(0, Math.round((Date.now() - Date.parse(detail.latest_ts))" not in detail)
    header = read("web/src/app/Header.tsx")
    check("GG31 Header auto-freshness makes no claim for a future ts",
          re.search(r"m < 0", header) is not None)

    # =====================================================================
    # GG-32 — return values of status functions must be used
    # =====================================================================
    # Bool-returning defs in bot.py / poller.py / dashboard/*.py.
    BOOL_DEFS = {}
    for rel in ("bot.py", "poller.py", "dashboard/logic.py",
                "dashboard/risk.py", "dashboard/turso_read.py",
                "dashboard/app.py"):
        lines = read(rel).splitlines()
        cur = None
        body = []
        for ln in lines:
            m = re.match(r"def (\w+)", ln)
            if m:
                if cur and any(re.search(r"return (True|False)\b", b) for b in body):
                    BOOL_DEFS.setdefault(cur, []).append(rel)
                cur, body = m.group(1), []
            elif cur is not None:
                body.append(ln)
        if cur and any(re.search(r"return (True|False)\b", b) for b in body):
            BOOL_DEFS.setdefault(cur, []).append(rel)
    # Bare calls that are allowed ONLY with a comment at the call site
    # explaining where the outcome is recorded instead.
    KNOWN_BARE = {
        # poller run_cycle: the outcome IS the poller_health heartbeat
        # (cycles_ok 0/1); the loop deliberately continues, and an
        # uncaught exception still exits 1 (S10, fix ronde 8).
        ("poller.py", "run_cycle"): "heartbeat",
    }
    bare_violations = []
    for name, def_files in BOOL_DEFS.items():
        for rel in ("bot.py", "poller.py", "dashboard/logic.py",
                    "dashboard/risk.py", "dashboard/turso_read.py",
                    "dashboard/app.py"):
            lines = read(rel).splitlines()
            in_def = False
            in_doc = False
            for idx, ln in enumerate(lines):
                if ln.count('"""') % 2 or ln.count("'''") % 2:
                    in_doc = not in_doc
                if in_doc:
                    continue
                if re.match(r"def (\w+)", ln):
                    in_def = ln.strip().startswith(f"def {name}(")
                    continue
                if in_def:
                    continue
                if not re.search(rf"(?<![\w.]){re.escape(name)}\s*\(", ln):
                    continue
                if ln.strip().startswith(("#", "def ", "class ")):
                    continue
                # Gather the (possibly multi-line) statement.
                stmt_lines = [ln]
                depth = ln.count("(") - ln.count(")")
                j = idx
                while depth > 0 and j + 1 < len(lines):
                    j += 1
                    stmt_lines.append(lines[j])
                    depth += lines[j].count("(") - lines[j].count(")")
                stmt = " ".join(s.strip() for s in stmt_lines)
                before = stmt.split(name + "(", 1)[0]
                # Used if the call sits in a condition, assignment,
                # return, assert, or nested inside another call /
                # f-string (its value is displayed) — `(` or `,` before
                # it means it is an argument, not a bare statement.
                used = bool(re.search(
                    r"(if|elif|while|return|assert|=|and |or |not |\(|,)",
                    before))
                if used:
                    continue
                key = (rel, name)
                if key in KNOWN_BARE:
                    near = "\n".join(lines[max(0, idx - 15):idx + 1])
                    if KNOWN_BARE[key] in near:
                        continue
                    bare_violations.append(
                        f"{rel}:{idx + 1} bare {name}() without the "
                        f"'{KNOWN_BARE[key]}' comment")
                else:
                    bare_violations.append(
                        f"{rel}:{idx + 1} bare {name}() — return value ignored: {stmt[:100]}")
    check("GG32 every bool-returning function call uses its value "
          "(or is a documented bare call)",
          not bare_violations, f"violations: {bare_violations[:6]}")
    # The two R9 cases, spelled out.
    bot_src = read("bot.py")
    check("GG32 P2-2: _save_admin_alert_state return value is checked "
          "by the caller",
          re.search(r"=\s*_save_admin_alert_state\(", bot_src) is not None,
          "caller still calls it bare")
    # The caller lives inside notify_admin_poller_troubled: a failed
    # write must be logged as a throttle that may not hold.
    _notify = block(bot_src, "def notify_admin_poller_troubled(", "\n# --- Dry-run")
    check("GG32 P2-2: a failed admin-state write is logged as a "
          "throttle that may not hold (not silently claimed)",
          "throttle" in _notify.lower() and "may not hold" in _notify.lower()
          or ("not hold" in _notify.lower() and "throttle" in _notify.lower()),
          "caller does not say the throttle may not hold")
    rec_call = re.search(r"record_alert_safe\((.*?)\)", bot_src, re.S)
    check("GG32: record_alert_safe return value is captured by the caller",
          re.search(r"=\s*record_alert_safe\(", bot_src) is not None)
    # S5 docstring (P2-3): no longer claims per-channel delivery time.
    send_fn = block(bot_src, "def send_alert_channels(", "\n# --- Single-pass lock")
    check("GG32/P2-3 docstring S5 no longer says 'captured per send'",
          "captured per send" not in send_fn)
    check("GG32/P2-3 docstring S5 says ONE shared alert_ts (S1)",
          "ONE alert_ts" in send_fn or "one alert_ts" in send_fn.lower())

    # =====================================================================
    # GG-34 — schema drift: every column the code touches must be declared
    # =====================================================================
    def parse_schema():
        declared = {}
        # Strip `--` comments first: a comment line (or trailing
        # comment) otherwise swallows the next column — the
        # window_note_en comment once hid observed_at from this parser.
        schema = "\n".join(
            re.sub(r"\s*--.*$", "", ln) for ln in read("schema.sql").splitlines())
        for m in re.finditer(
                r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);",
                schema, re.S):
            cols = set()
            for part in m.group(2).split(",\n"):
                tok = part.strip().split()
                if not tok:
                    continue
                if tok[0].upper() in ("PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"):
                    continue
                cols.add(tok[0].strip("`\""))
            declared[m.group(1)] = cols
        mig_dir = os.path.join(ROOT, "migrations")
        for fn in sorted(os.listdir(mig_dir)):
            if not fn.endswith(".sql"):
                continue
            for m in re.finditer(
                    r"ALTER TABLE (\w+)\s+ADD COLUMN (\w+)",
                    open(os.path.join(mig_dir, fn), encoding="utf-8").read(), re.I):
                declared.setdefault(m.group(1), set()).add(m.group(2))
        return declared

    DECLARED = parse_schema()
    SQL_KW = {
        "select", "from", "where", "and", "or", "not", "null", "true", "false",
        "as", "on", "join", "left", "right", "inner", "outer", "group", "by",
        "order", "asc", "desc", "limit", "offset", "distinct", "case", "when",
        "then", "else", "end", "in", "is", "like", "between", "exists", "union",
        "all", "count", "max", "min", "avg", "sum", "strftime", "now", "coalesce",
        "ifnull", "lower", "trim", "abs", "round", "cast", "collate", "nocase",
        "values", "insert", "into", "update", "set", "delete", "create", "table",
        "index", "pragma", "rowid",
    }

    SQL_CONT = r"(?:SELECT|INSERT|JOIN|WHERE|AND|OR|ORDER|GROUP|LIMIT|VALUES|ON|FROM)\b"

    def join_js_strings(text):
        # Collapse "..." + "..." concatenations AND implicit adjacent
        # literals ("a" "b" on consecutive lines, the Python/SQL idiom
        # in bot.py) so SQL parses whole. The bare newline-join only
        # fires when the next literal starts with a SQL keyword, so
        # unrelated dict/message literals are never merged.
        prev = None
        while prev != text:
            prev = text
            text = re.sub(r'"\s*\+\s*\n\s*"', "", text)
            text = re.sub(r"'\s*\+\s*\n\s*'", "", text)
            text = re.sub(r'"\s*\+\s*"', "", text)
            # The seam is closing-quote + newline + opening-quote:
            # deleting it (not replacing with one quote) merges the
            # two literals into one string.
            text = re.sub(r'"\s*\n\s*"(?=' + SQL_CONT + ")", "", text)
            text = re.sub(r"'\s*\n\s*'(?=" + SQL_CONT + ")", "", text)
            # Column-list continuations: the previous literal ends in
            # `(` or `,` (an INSERT list split across lines) and the
            # next literal starts with a column name, not a keyword.
            text = re.sub(r"([(,])\s*\"\s*\n\s*\"", r"\1", text)
            text = re.sub(r"([(,])\s*'\s*\n\s*'", r"\1", text)
        return text

    def sql_literals(rel):
        text = read(rel)
        text = join_js_strings(text)
        lits = re.findall(r'"([^"]*(?:SELECT|INSERT)[^"]*)"', text, re.I | re.S)
        lits += re.findall(r"'([^']*(?:SELECT|INSERT)[^']*)'", text, re.I | re.S)
        return lits

    def stmt_tables_and_aliases(sql):
        noq = re.sub(r"'[^']*'", "''", sql)
        tables = set(re.findall(r"(?:FROM|JOIN)\s+(\w+)", noq, re.I))
        aliases = set()
        for m in re.finditer(
                r"(?:FROM|JOIN)\s+\w+\s+(?:AS\s+)?(\w+)", noq, re.I):
            aliases.add(m.group(1).lower())
        for m in re.finditer(r"\)\s*(?:AS\s+)?(\w+)\s+(?:ON|WHERE|ORDER|GROUP|LIMIT|JOIN|\)|$)",
                             noq, re.I):
            aliases.add(m.group(1).lower())
        return tables, aliases

    def select_columns(sql):
        """(columns, aliases) referenced by every SELECT in one literal."""
        noq = re.sub(r"'[^']*'", "''", sql)
        cols, aliases = set(), set()
        for m in re.finditer(r"SELECT\s+(.+?)\s+FROM\b", noq, re.I | re.S):
            sel = m.group(1)
            items, depth, cur = [], 0, ""
            for ch in sel:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if ch == "," and depth == 0:
                    items.append(cur)
                    cur = ""
                else:
                    cur += ch
            if cur.strip():
                items.append(cur)
            for it in items:
                it = it.strip()
                am = re.search(r"\bAS\s+(\w+)\s*$", it, re.I)
                if am:
                    aliases.add(am.group(1).lower())
                    it = it[:am.start()].strip()
                if it == "*":
                    continue
                fm = re.match(r"(\w+)\s*\((.*)\)\s*$", it, re.S)
                if fm:
                    inner = fm.group(2)
                    for tok in re.findall(r"([A-Za-z_][\w]*)(?:\.([A-Za-z_][\w]*))?", inner):
                        name = tok[1] or tok[0]
                        if name.lower() not in SQL_KW:
                            cols.add(name)
                    continue
                cm = re.match(r"(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)\s*$", it)
                if cm and cm.group(1).lower() not in SQL_KW:
                    cols.add(cm.group(1))
        return cols, aliases

    drift = []
    for rel in ("bot.py", "poller.py", "dashboard/turso_read.py",
                "dashboard/logic.py", "dashboard/app.py", "api/worker.js"):
        for sql in sql_literals(rel):
            # INSERT column lists: strict, per-table.
            for m in re.finditer(r"INSERT INTO\s+(\w+)\s*\(([^)]+)\)", sql, re.I):
                tbl, cols = m.group(1), [c.strip() for c in m.group(2).split(",")]
                have = DECLARED.get(tbl, set())
                for c in cols:
                    if c not in have:
                        drift.append(f"{rel} INSERT {tbl}.{c} not in schema/migrations")
            # SELECT columns: union over the statement's tables.
            tables, taliases = stmt_tables_and_aliases(sql)
            if not tables:
                continue
            cols, saliases = select_columns(sql)
            have = set()
            for t in tables:
                have |= DECLARED.get(t, set())
            allow = taliases | saliases | SQL_KW
            for c in cols:
                if c.lower() in allow:
                    continue
                if c not in have:
                    drift.append(
                        f"{rel} SELECT {c} (tables {sorted(tables)}) not in schema/migrations")
    check("GG34 no code column is missing from schema.sql/migrations",
          not drift, f"drift: {drift[:8]}")
    check("GG34 P1-4: pools_excluded IS declared for deviations",
          "pools_excluded" in DECLARED.get("deviations", set()),
          f"deviations cols: {sorted(DECLARED.get('deviations', set()))}")
    mig = os.path.join(ROOT, "migrations", "2026-11-09-pools-excluded.sql")
    check("GG34 P1-4: a migration documents the pools_excluded column",
          os.path.exists(mig) and "pools_excluded" in open(mig, encoding="utf-8").read())

    # =====================================================================
    # GG-17 / F2 runtime — negative numbers render U+2212, not ASCII "-"
    # =====================================================================
    esbuild = os.path.join(ROOT, "web", "node_modules", ".bin", "esbuild")
    fmt_out = os.path.join(tmp, "format.cjs")
    esb = subprocess.run(
        [esbuild, os.path.join(ROOT, "web", "src", "lib", "format.ts"),
         "--bundle", "--format=cjs", "--platform=node",
         f"--outfile={fmt_out}", "--log-level=error"],
        capture_output=True, text=True)
    check("F2 format.ts bundles with esbuild", esb.returncode == 0, esb.stderr[:200])
    if esb.returncode == 0:
        probe = (
            "const f = require(%r);"
            "console.log(JSON.stringify({"
            "neg: f.fmtSigned(-12.34, 2), neg1: f.fmtSigned1(-12.34),"
            "negPct: f.fmtPct(-0.05), pos: f.fmtSigned(1.5, 2),"
            "negZero: f.fmtSigned(-0.001, 1), zero: f.fmtSigned(0, 2)"
            "}));" % fmt_out)
        r = subprocess.run(["node", "-e", probe], capture_output=True, text=True)
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        minus = "\u2212"
        check("F2 fmtSigned(-12.34) starts with U+2212, not ASCII '-'",
              got.get("neg", "").startswith(minus), f"got={got}")
        check("F2 fmtSigned1(-12.34) starts with U+2212",
              got.get("neg1", "").startswith(minus), f"got={got}")
        check("F2 fmtPct(-0.05) uses U+2212",
              got.get("negPct", "").startswith(minus), f"got={got}")
        check("F2 fmtSigned keeps '+' for positives",
              got.get("pos") == "+1.50", f"got={got}")
        check("F2 negative zero still renders '+0.0' (AAPLx rule holds)",
              got.get("negZero") == "+0.0", f"got={got}")
        check("F2 zero renders '+0.00'",
              got.get("zero") == "+0.00", f"got={got}")
    i18n_src = read("web/src/lib/i18n.ts")
    ascii_minus = re.findall(r'"[^"]*-\d[^"]*"', i18n_src)
    check("F2 no ASCII-hyphen+digit literal in i18n strings",
          not ascii_minus, f"hits: {ascii_minus[:4]}")
    # Dashboard: fmt_abbr is the one signed-capable renderer — a
    # negative value must carry U+2212, not ASCII hyphen.
    check("F2 dashboard fmt_abbr renders a negative with U+2212",
          dash_logic.fmt_abbr(-1400000.0) == "$\u22121.40M",
          f"got={dash_logic.fmt_abbr(-1400000.0)!r}")
    check("F2 dashboard fmt_abbr keeps positives unchanged",
          dash_logic.fmt_abbr(1400000.0) == "$1.40M",
          f"got={dash_logic.fmt_abbr(1400000.0)!r}")

    # =====================================================================
    # Fix verification — P1-6, gaps, nits
    # =====================================================================
    check("P1-6 detail PoR age uses fmtAge (rounded, like home)",
          "fmtAge(detail.por_age_hours)" in detail)
    check("P1-6 detail PoR age carries the 72h stale/fresh label",
          ("por_age_stale" in detail and "por_age_fresh" in detail
           and "72" in detail),
          "no por_age_stale/fresh label near the detail PoR age")
    check("Gap por_note IS rendered on the detail page",
          "detail.por_note" in detail)
    check("Gap CSV: buildCsv header includes pools_excluded",
          "pools_excluded" in read("web/src/lib/csv.ts"))
    api_ts = read("web/src/lib/api.ts")
    check("Gap CSV: TickerRow declares pools_excluded (API contract)",
          "pools_excluded" in api_ts)
    check("Gap CSV: Worker loadLatest returns pools_excluded per row",
          "pools_excluded" in block(worker, "async function loadLatest(", "\n}\n"))
    # CSV runtime: bundle csv.ts and build one row.
    csv_out = os.path.join(tmp, "csv.cjs")
    esb2 = subprocess.run(
        [esbuild, os.path.join(ROOT, "web", "src", "lib", "csv.ts"),
         "--bundle", "--format=cjs", "--platform=node",
         f"--outfile={csv_out}", "--log-level=error"],
        capture_output=True, text=True)
    check("Gap CSV csv.ts bundles with esbuild", esb2.returncode == 0,
          esb2.stderr[:200])
    if esb2.returncode == 0:
        probe2 = (
            "const { buildCsv } = require(%r);"
            "console.log(buildCsv([{ticker:'TSLAx',tier:1,dw_price:100.5,"
            "dev_bps:-12.3,spread_pct:0.4,depth_usd:600000,pools_used:3,"
            "pools_excluded:1,redemption_status:'open',por_age_hours:6,"
            "status:'ok',change_1h_bps:-1.2}]));" % csv_out)
        r2 = subprocess.run(["node", "-e", probe2], capture_output=True, text=True)
        lines = r2.stdout.strip().split("\n") if r2.returncode == 0 else []
        check("Gap CSV header has pools_excluded after pools_used",
              len(lines) == 2 and "pools_used,pools_excluded" in lines[0],
              f"out={r2.stdout[:200]!r} err={r2.stderr[:200]}")
        check("Gap CSV row carries the pools_excluded value (1)",
              len(lines) == 2 and lines[1].split(",")[7] == "1",
              f"row={lines[1] if len(lines) == 2 else ''!r}")
    # P1-2: one find for redemption status + next open.
    red_block = block(home, "const redStatus", "const porMaxAge")
    check("P1-2 home redemption status + next-open come from ONE find",
          red_block.count(".find(") <= 1 and "redemption" in red_block.lower(),
          f"finds in block: {red_block.count('.find(')}")
    check("P1-2 the single redemption find is shared (one memo)",
          re.search(r"const red\w* = useMemo", home) is not None
          or "redemption" in block(home, "const red", "const porMaxAge"))
    # P1-8: partial-gate consequence written down.
    gate = read("GATE-A1-G0.md")
    check("P1-8 GATE doc states the partial-failure consequence explicitly",
          re.search(r"[Pp]arsial.*[Gg]agal|[Gg]agal.*[Pp]arsial", gate) is not None
          and "pivot" in gate.lower())
    # tsc still passes after all web edits.
    tsc = subprocess.run(
        [os.path.join(ROOT, "web", "node_modules", ".bin", "tsc"), "--noEmit"],
        cwd=os.path.join(ROOT, "web"), capture_output=True, text=True)
    check("web `tsc --noEmit` passes", tsc.returncode == 0,
          (tsc.stdout + tsc.stderr)[:300])

    print(f"\nSUMMARY: {len(FAILURES)} FAIL — "
          + ("R9 FIX TEST: PASS" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
