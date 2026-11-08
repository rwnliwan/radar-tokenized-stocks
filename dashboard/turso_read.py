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
    " willing_price, created_at, consent) SELECT ?, ?, ?, ?, ?, ?"
    # S13 (fix ronde 8): the hourly cap is enforced INSIDE this single
    # INSERT, exactly like the Worker (/api/waitlist, fix ronde 6
    # S-new-2). The old code checked the cap in a separate COUNT read
    # first, so concurrent dashboard submissions could all observe a
    # count below 500 and exceed the cap — and its docstring claim of
    # "SAME guarantees as the Worker" was false for concurrent writes.
    " WHERE (SELECT COUNT(*) FROM waitlist WHERE created_at >= "
    "strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour')) < ?"
    " AND NOT EXISTS (SELECT 1 FROM waitlist"
    " WHERE LOWER(TRIM(contact)) = ?)"
)

WAITLIST_HOURLY_CAP = 500  # same cap as api/worker.js


def valid_contact(contact):
    """Worker-identical contact rule (api/worker.js validContact): an
    email address, or a Telegram username (5-32 chars, letters/digits/
    underscore, optional leading @)."""
    import re
    c = (contact or "").strip()
    if c.startswith("@"):
        return bool(re.match(r"^[A-Za-z0-9_]{5,32}$", c[1:]))
    if "@" in c:
        return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", c))
    return bool(re.match(r"^[A-Za-z0-9_]{5,32}$", c))

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
    """The dashboard's only write.

    Enforces the SAME guarantees as the Worker (/api/waitlist,
    api/worker.js handleWaitlist) — fix ronde 5, S3. Before this fix
    the Streamlit path did required-field checks only, so a resubmitted
    contact created a duplicate row and garbage contacts polluted the
    waitlist count (a G0 evidence number). Now: contact format, length
    caps, hourly cap (500), and an atomic INSERT...WHERE NOT EXISTS
    dedup on the normalized contact, identical to the Worker.
    S13 (fix ronde 8): the hourly cap is enforced INSIDE the INSERT
    itself (a single statement executes atomically), not in a separate
    COUNT read before it — concurrent submissions can no longer all
    observe a count below 500 and slip past the cap.
    Returns the new row id, or None when the contact was already listed
    (idempotent success — the caller still shows the success message).
    Raises ValueError("rate limited") when the hourly cap was hit.
    """
    contact = (contact or "").strip()
    position_size_usd = (position_size_usd or "").strip()
    venues = (venues or "").strip()
    willing_price = (willing_price or "").strip() or None
    if not contact:
        raise ValueError("contact is required")
    if len(contact) > 200 or not valid_contact(contact):
        raise ValueError("invalid contact")
    if not position_size_usd:
        raise ValueError("position_size_usd is required")
    if len(position_size_usd) > 100:
        raise ValueError("position_size_usd too long")
    if not venues:
        raise ValueError("venues is required")
    if len(venues) > 300:
        raise ValueError("venues too long")
    if willing_price is not None and len(willing_price) > 100:
        raise ValueError("willing_price too long")
    if int(consent) != 1:
        raise ValueError("consent is required")
    # S13: no separate COUNT read — the cap is enforced atomically
    # inside INSERT_WAITLIST_SQL below (see its comment). A pre-check
    # here would reintroduce the race the atomic INSERT closes.
    res = _pipeline([(INSERT_WAITLIST_SQL, [
        contact, position_size_usd, venues,
        willing_price, created_at, 1, WAITLIST_HOURLY_CAP, contact.lower(),
    ])])[0]
    # rows_written == 0 means the atomic statement admitted nothing:
    # either the contact already exists (idempotent success) or the
    # hourly cap was hit (rate limited). One follow-up read decides
    # which — the cap itself was already enforced atomically above,
    # so this read cannot admit a 501st row.
    if isinstance(res, dict) and res.get("rows_written") == 0:
        existing = query(
            "SELECT id FROM waitlist WHERE LOWER(TRIM(contact)) = ? LIMIT 1",
            [contact.lower()])
        if existing:
            return None
        raise ValueError("rate limited")
    return res.get("last_insert_rowid") if isinstance(res, dict) else None
