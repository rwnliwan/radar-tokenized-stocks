"""Bot dry-run test: 3 scenarios, §5.6 format checks, forbidden words.

Runs `python3 bot.py --dry-run` (no network, no token access) and asserts:
- 3 scenarios each fire >= 1 message;
- every message has a ticker-page link + disclaimer;
- spread message has venue + depth + reference;
- redemption message has status; PoR message has feed age;
- NO forbidden word appears (word-boundary, case-insensitive):
  aman, disarankan, beli, jual, safe, recommended, buy, sell.
"""
import re
import subprocess
import sys

FORBIDDEN = ["aman", "disarankan", "beli", "jual",
             "safe", "recommended", "buy", "sell"]


def main():
    r = subprocess.run(
        [sys.executable, "bot.py", "--dry-run"],
        cwd="/home/hatch/workspace/radar-tokenized-stocks",
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, f"dry-run exit {r.returncode}: {r.stderr[:500]}"
    out = r.stdout
    assert "custom.radar-telegram" not in out, "dry-run must not touch token entry"
    scenarios = re.split(r"=== scenario: ", out)[1:]
    assert len(scenarios) == 3, f"expected 3 scenarios, got {len(scenarios)}"
    for sc in scenarios:
        name, _, body = sc.partition("===\n")
        messages = [m for m in body.split("---\n") if m.strip()]
        assert messages, f"scenario {name!r} fired no message"
        for m in messages:
            assert "https://radar.omdanny.site/" in m, f"missing ticker link in {name}"
            assert "Not financial advice" in m, f"missing disclaimer in {name}"
            assert "$" in m, f"missing money figure in {name}"
            for w in FORBIDDEN:
                assert not re.search(rf"\b{w}\b", m, re.IGNORECASE), \
                    f"forbidden word {w!r} in {name}: {m[:200]}"
        if name.startswith("spread"):
            assert "raydium" in body.lower() and "orca" in body.lower()
            assert "Spread:" in body and "Depth-weighted" in body
        if name.startswith("redemption"):
            assert "closed" in body.lower()
            assert "Depth-weighted price" in body  # §5.6: every alert carries price+depth
        if name.startswith("PoR"):
            assert "96.0" in body and "hours" in body
            assert "Depth-weighted price" in body
    print("BOT DRY-RUN TEST: PASS (3 scenarios, format + forbidden-words OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
