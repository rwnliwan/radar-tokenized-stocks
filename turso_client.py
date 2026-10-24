"""Hrana HTTP client for the Radar Turso database.

Auth: token ONLY via dynamic_credentials entry "custom.turso-radar"
(surrogate) at runtime. This module never prints, logs, or writes the
token value anywhere. Transport is curl (proven through this VM's egress
proxy); urllib is avoided for API calls per workspace lessons.

Hrana v2 pipeline: POST https://<host>/v2/pipeline with
{"requests":[{"type":"execute","stmt":{"sql":...,"args":[...]}}]}.
Arg encoding: text -> {"type":"text","value":str},
float -> {"type":"float","value":number},
int -> {"type":"integer","value":str(int)} (integers travel as strings),
None -> {"type":"null"}.
"""
import json
import os
import subprocess
import sys

HOST = "radar-tokenized-stocks-trisaktipan.aws-ap-northeast-1.turso.io"
URL = f"https://{HOST}/v2/pipeline"

for _p in (
    "/opt/hatch/workflow-skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/templates/skill/bin",
):
    if os.path.exists(os.path.join(_p, "dynamic_credentials.py")):
        sys.path.insert(0, _p)
        break
else:
    raise RuntimeError("dynamic_credentials module not found")

from dynamic_credentials import dynamic_credential_entry  # noqa: E402

_TOKEN = None


def _token():
    global _TOKEN
    if _TOKEN is None:
        entry = dynamic_credential_entry("custom.turso-radar")
        _TOKEN = entry.get("surrogate") or entry.get("value")
        if not _TOKEN:
            raise RuntimeError("no token in vault entry custom.turso-radar")
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


def execute(sql, args=None):
    """Run one statement; returns the result dict (or raises on error)."""
    results = pipeline([(sql, args)])
    return results[0]


def pipeline(stmts):
    """Run a list of (sql, args|None); returns list of result dicts.

    Raises RuntimeError if the HTTP call fails or any statement errors.
    The token value is never included in any exception message.
    """
    requests = []
    for sql, args in stmts:
        stmt = {"sql": sql}
        if args is not None:
            stmt["args"] = [enc_arg(a) for a in args]
        requests.append({"type": "execute", "stmt": stmt})
    body = json.dumps({"requests": requests})
    r = subprocess.run(
        [
            "curl", "-s", "-w", "\nHTTP:%{http_code}",
            "--max-time", "60",
            "-X", "POST", URL,
            "-H", "Authorization: Bearer " + _token(),
            "-H", "Content-Type: application/json",
            "-d", body,
        ],
        capture_output=True, text=True,
    )
    out = r.stdout
    http = None
    if "\nHTTP:" in out:
        out, http = out.rsplit("\nHTTP:", 1)
        http = http.strip()
    if http != "200":
        raise RuntimeError(f"Hrana HTTP {http}: {out[:300]}")
    data = json.loads(out)
    results = data.get("results", [])
    for i, res in enumerate(results):
        if res.get("type") == "error":
            err = res.get("error", {})
            raise RuntimeError(
                f"Hrana statement {i} failed: {err.get('message', err)}"
            )
    # Unwrap: response {"type": "execute", "result": {...}} -> result dict,
    # so rows()/query() see cols/rows directly.
    unwrapped = []
    for res in results:
        resp = res.get("response", {})
        if resp.get("type") == "execute":
            unwrapped.append(resp.get("result", {}))
        else:
            unwrapped.append(resp)
    return unwrapped


def rows(result):
    """Convert a Hrana execute response to a list of dicts."""
    cols = [c["name"] for c in result.get("cols", [])]
    out = []
    for row in result.get("rows", []):
        d = {}
        for name, cell in zip(cols, row):
            d[name] = cell.get("value") if isinstance(cell, dict) else None
        out.append(d)
    return out


def query(sql, args=None):
    return rows(execute(sql, args))
