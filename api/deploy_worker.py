"""Deploy the radar-api Worker to Cloudflare.

The Cloudflare token is read from the secure vault (surrogate) and passed
to wrangler ONLY through the child process environment. It is never
printed, logged, or written to disk by this script.
"""
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

for _p in (
    "/opt/hatch/workflow-skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/bin/",
    "/opt/muse/skills/custom-connector-setup/templates/skill/bin",
):
    if os.path.exists(os.path.join(_p, "dynamic_credentials.py")):
        sys.path.insert(0, _p)
        break
else:
    raise SystemExit("dynamic_credentials module not found")

from dynamic_credentials import dynamic_credential_entry  # noqa: E402

tok = dynamic_credential_entry("custom.cloudflare")["surrogate"]
env = dict(os.environ)
env["CLOUDFLARE_API_TOKEN"] = tok
r = subprocess.run(
    [os.path.join(_ROOT, "web", "node_modules", ".bin", "wrangler"), "deploy"],
    cwd=_HERE,
    env=env,
)
sys.exit(r.returncode)
