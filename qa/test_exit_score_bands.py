"""N1: shared Exit Score band fixture test (fix ronde review DeepSeek
Radar, 2026-11-13).

Loads qa/exit_score_bands_fixture.json and tests dashboard/risk.py
exit_score_band against EVERY case in the fixture. The web worker
tests web/src/lib/risk.ts exitScoreBand against the SAME fixture —
the structure is frozen, both sides must agree on every boundary.

Bands (design §2.3, display only): 0-39 low, 40-69 medium, 70-100
high. Labels are the exact return values of exit_score_band.

Usage: python3 qa/test_exit_score_bands.py  (exit 0 = PASS)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "dashboard"))

from risk import exit_score_band  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "exit_score_bands_fixture.json")

FAILURES = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    with open(FIXTURE) as f:
        fixture = json.load(f)

    # The fixture must carry exactly the six boundary cases the task
    # specifies; a silently shrunk fixture must fail, not pass.
    cases = fixture["cases"]
    check("fixture has 6 cases",
          len(cases) == 6, f"got {len(cases)}")
    check("fixture cases are the specified boundaries",
          [(c["score"], c["band"]) for c in cases] == [
              (0, "low"), (39, "low"), (40, "medium"),
              (69, "medium"), (70, "high"), (100, "high"),
          ], str([(c["score"], c["band"]) for c in cases]))

    # Every declared band range must contain its cases, and the
    # ranges must tile 0-100 with no gaps or overlaps.
    bands = fixture["bands"]
    check("band ranges tile 0-100",
          bands == {"low": [0, 39], "medium": [40, 69], "high": [70, 100]},
          str(bands))

    for c in cases:
        got = exit_score_band(c["score"])
        check(f"score {c['score']} -> {c['band']}",
              got == c["band"], f"got {got!r}")
        lo, hi = bands[c["band"]]
        check(f"score {c['score']} inside declared {c['band']} range",
              lo <= c["score"] <= hi, f"range {lo}-{hi}")

    # Guards outside the fixture (risk.py contract, unchanged):
    # None / out-of-range never band as 0.
    check("None -> None", exit_score_band(None) is None)
    check("-1 -> None", exit_score_band(-1) is None)
    check("101 -> None", exit_score_band(101) is None)

    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nALL PASS")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
