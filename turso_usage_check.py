"""Turso usage checker for radar-tokenized-stocks via Platform API.

Reads ACTUAL cumulative usage (rows_read / rows_written / storage) from
https://api.turso.tech — the same numbers the dashboard shows. No DB
queries, so this costs zero rows_read.

Auth: platform token ONLY via dynamic_credentials entry
"custom.turso-platform" (surrogate) at runtime. Never prints the token.

Log: ~/workspace/goals/radar-tokenized-stocks-kabar-berkala/hidden_files/usage-api-log.md
Columns: timestamp WITA | reads | written | storage MB | delta_reads |
rate/min | month projection (M) | verdict

Exit: prints verdict OK / WARN / DANGER + numbers to stdout.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

for _p in (
    "/opt/hatch/workflow-skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/bin/",
):
    if os.path.exists(os.path.join(_p, "dynamic_credentials.py")):
        sys.path.insert(0, _p)
        break
else:
    raise RuntimeError("dynamic_credentials module not found")

from dynamic_credentials import dynamic_credential_entry  # noqa: E402

ORG = "trisaktipan"
DB = "radar-tokenized-stocks"
LIMIT_READS = 500_000_000
LIMIT_WRITES = 10_000_000
LOG = os.path.expanduser(
    "~/workspace/goals/radar-tokenized-stocks-kabar-berkala/"
    "hidden_files/usage-api-log.md"
)
WITA = timezone(timedelta(hours=8))


def _token():
    e = dynamic_credential_entry("custom.turso-platform")
    tok = e.get("surrogate") or e.get("value")
    if not tok:
        raise RuntimeError("no token in vault entry custom.turso-platform")
    return tok


def fetch_usage():
    r = subprocess.run(
        ["curl", "-s", "--max-time", "30",
         f"https://api.turso.tech/v1/organizations/{ORG}/databases/{DB}/usage",
         "-H", "Authorization: Bearer " + _token()],
        capture_output=True, text=True,
    )
    d = json.loads(r.stdout)
    return d["database"]["usage"]


def last_log():
    if not os.path.exists(LOG):
        return None
    with open(LOG) as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if not lines:
        return None
    parts = lines[-1].split("|")
    try:
        return {
            "ts": datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M WITA").replace(tzinfo=WITA),
            "reads": int(parts[1].strip()),
        }
    except Exception:
        return None


def main():
    now = datetime.now(WITA)
    u = fetch_usage()
    reads = int(u["rows_read"])
    written = int(u["rows_written"])
    storage_mb = round(int(u["storage_bytes"]) / 1e6, 1)

    prev = last_log()
    if prev:
        mins = max((now - prev["ts"]).total_seconds() / 60.0, 0.01)
        delta = reads - prev["reads"]
        rate = delta / mins
        gap_h = mins / 60.0
    else:
        delta, rate, gap_h = 0, 0.0, 0.0

    # Month projection. Prefer RATE-based (current pace) when the previous
    # sample is >= 2h old — it self-corrects after one-off burn spikes
    # (e.g. legacy queries on Nov 1 morning). Fall back to cumulative pace
    # early in the month when no usable previous sample exists.
    # Quota reset: Nov 1 00:00 UTC.
    month_start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    days = max((now.astimezone(timezone.utc) - month_start).total_seconds() / 86400.0, 0.05)
    proj_cumul = reads / days * 30.0
    if gap_h >= 2:
        proj = rate * 43200.0
        basis = "rate"
    else:
        proj = proj_cumul
        basis = "cumul"
    proj_m = round(proj / 1e6, 1)
    proj_cumul_m = round(proj_cumul / 1e6, 1)

    if proj > 450_000_000:
        verdict = "DANGER"
    elif proj > 400_000_000:
        verdict = "WARN"
    else:
        verdict = "OK"

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if not os.path.exists(LOG):
        with open(LOG, "w") as f:
            f.write("# Turso usage (Platform API, angka aktual dashboard)\n")
            f.write("# ts WITA | reads | written | storage MB | delta_reads | "
                    "rate/min | proj/bln (M) | verdict\n")
    with open(LOG, "a") as f:
        f.write(f"{now.strftime('%Y-%m-%d %H:%M')} WITA | {reads} | {written} | "
                f"{storage_mb} | {delta} | {rate:.0f} | {proj_m}({basis}) | {verdict}\n")

    pct = reads / LIMIT_READS * 100
    print(f"verdict={verdict} (basis={basis})")
    print(f"reads={reads} ({pct:.1f}% dari limit 500J) | "
          f"written={written} ({written/LIMIT_WRITES*100:.1f}% dari 10J) | "
          f"storage={storage_mb} MB")
    print(f"delta_sejak_cek_terakhir={delta} | rate={rate:.0f}/mnt | "
          f"proyeksi_bulanan={proj_m}J (kumulatif: {proj_cumul_m}J)")


if __name__ == "__main__":
    main()
