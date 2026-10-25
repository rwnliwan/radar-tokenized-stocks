"""Wave 3: redemption schedule logic (pure — no DB, no network).

Covers the conservative 24/5 definition: open = NYSE business day
(all day, ET date governs, NOT the UTC date); closed = weekend /
NYSE holiday. Also covers next_nyse_open_utc (00:00 ET of the next
NYSE business day, rendered as UTC).
"""
import os
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/radar-tokenized-stocks"
sys.path.insert(0, ROOT)

from poller import (  # noqa: E402
    next_nyse_open_utc, redemption_schedule_status)

UTC = timezone.utc


def dt(iso):
    return datetime.fromisoformat(iso)


def main():
    ok = True

    def check(name, got, exp):
        nonlocal ok
        mark = "OK " if got == exp else "FAIL"
        if got != exp:
            ok = False
        print(f"{mark} {name}: got={got} expected={exp}")

    # Schedule status (ET date governs).
    check("Sat 2026-10-24", redemption_schedule_status(dt("2026-10-24T12:00:00+00:00")), "closed")
    check("Sun 2026-10-25", redemption_schedule_status(dt("2026-10-25T12:00:00+00:00")), "closed")
    check("Mon 2026-10-26 midday", redemption_schedule_status(dt("2026-10-26T12:00:00+00:00")), "open")
    check("Mon 02:00Z = Sun 22:00 ET", redemption_schedule_status(dt("2026-10-26T02:00:00+00:00")), "closed")
    check("Mon 05:00Z = Mon 01:00 ET", redemption_schedule_status(dt("2026-10-26T05:00:00+00:00")), "open")
    check("Christmas 2026 (NYSE holiday)", redemption_schedule_status(dt("2026-12-25T12:00:00+00:00")), "closed")
    check("Sat 2026-12-26", redemption_schedule_status(dt("2026-12-26T12:00:00+00:00")), "closed")
    check("Mon 2026-12-28", redemption_schedule_status(dt("2026-12-28T12:00:00+00:00")), "open")

    # Next open (00:00 ET next business day, as UTC).
    check("next open from Sat Oct 24", next_nyse_open_utc(dt("2026-10-24T12:00:00+00:00")), "2026-10-26T04:00:00Z")
    check("next open from Sun Oct 25", next_nyse_open_utc(dt("2026-10-25T12:00:00+00:00")), "2026-10-26T04:00:00Z")
    check("next open from Christmas", next_nyse_open_utc(dt("2026-12-25T12:00:00+00:00")), "2026-12-28T05:00:00Z")

    print("REDEMPTION SCHEDULE TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
