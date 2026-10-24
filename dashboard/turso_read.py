"""Read client for the Radar dashboard + waitlist writer.

Self-contained copy of the proven Phase-1 Hrana transport (curl), so the
dashboard does not depend on poller files. Auth: token ONLY from
(1) vault entry "custom.turso-radar" (surrogate) at runtime,
(2) Streamlit secrets (Cloud deploy), (3) env TURSO_AUTH_TOKEN
(explicit local override). The token value is NEVER printed, logged,
written to a file, or included in any exception message.

Read path is SELECT-only by construction (query() rejects anything
else). The single write allowed is the fixed waitlist INSERT
(insert_waitlist); the dashboard writes nothing else to Turso.
"""
import json
import os
import re
import subprocess
import sys

HOST = "radar-tokenized-stocks-trisaktipan.aws-ap-northeast-1.turso.io"
URL = f"https://{HOST}/v2/pipeline"

INSERT_WAITLIST_SQL = (
    "INSERT INTO waitlist (contact, position_size_usd, venues,"
    " willing_price, created_at, consent) VALUES (?,?,?,?,?,?)"
)

for _p in (
    "/opt/hatch/workflow-skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/templates/skill/bin",
):
    if os.path.exists(os.path.join(_p, "dynamic_credentials.py")):
        sys.path.insert(0, _p)
        break

_TOKEN = None


def _vault_token():
    try:
        from dynamic_credentials import dynamic_credential_entry
        entry = dynamic_credential_entry("custom.turso-radar")
        return entry.get("surrogate") or entry.get("value")
    except Exception:
        return None


def _secrets_token():
    try:
        import streamlit as st
        v = st.secrets.get("TURSO_AUTH_TOKEN")
        return v or None
    except Exception:
        return None


def _token():
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = _vault_token() or _secrets_token() or os.environ.get("TURSO_AUTH_TOKEN")
        if not _TOKEN:
            raise RuntimeError("no Turso token available (vault/secrets/env)")
    return _TOKEN


def enc_arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def _pipeline(stmts):
    requests = []
    for sql, args in stmts:
        stmt = {"sql": sql}
        if args is not None:
            stmt["args"] = [enc_arg(a) for a in args]
        requests.append({"type": "execute", "stmt": stmt})
    body = json.dumps({"requests": requests})
    r = subprocess.run(
        ["curl", "-s", "-w", "\nHTTP:%{http_code}", "--max-time", "60",
         "-X", "POST", URL,
         "-H", "Authorization: Bearer " + _token(),
         "-H", "Content-Type: application/json",
         "-d", body],
        capture_output=True, text=True,
    )
    out = r.stdout
    http = None
    if "\nHTTP:" in out:
        out, http = out.rsplit("\nHTTP:", 1)
        http = http.strip()
    if http != "200":
        raise RuntimeError(f"Hrana HTTP {http}")
    data = json.loads(out)
    results = data.get("results", [])
    unwrapped = []
    for i, res in enumerate(results):
        if res.get("type") == "error":
            err = res.get("error", {})
            raise RuntimeError(
                f"Hrana statement {i} failed: {err.get('message', err)}"
            )
        resp = res.get("response", {})
        unwrapped.append(resp.get("result", {}) if resp.get("type") == "execute" else resp)
    return unwrapped


def _rows(result):
    cols = [c["name"] for c in result.get("cols", [])]
    out = []
    for row in result.get("rows", []):
        d = {}
        for name, cell in zip(cols, row):
            d[name] = cell.get("value") if isinstance(cell, dict) else None
        out.append(d)
    return out


def query(sql, args=None):
    """SELECT-only read. Raises ValueError on non-SELECT statements."""
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()
    if ";" in s or not re.match(r"(?i)^SELECT\b", s):
        raise ValueError("query() accepts single SELECT statements only")
    return _rows(_pipeline([(sql, args)])[0])


def insert_waitlist(contact, position_size_usd, venues, willing_price,
                    created_at, consent):
    """The dashboard's only write. Validates required fields first."""
    if not (contact or "").strip():
        raise ValueError("contact is required")
    if not (position_size_usd or "").strip():
        raise ValueError("position_size_usd is required")
    if not (venues or "").strip():
        raise ValueError("venues is required")
    if int(consent) != 1:
        raise ValueError("consent is required")
    res = _pipeline([(INSERT_WAITLIST_SQL, [
        contact.strip(), position_size_usd.strip(), venues.strip(),
        (willing_price or "").strip() or None, created_at, 1,
    ])])[0]
    return res.get("last_insert_rowid")
