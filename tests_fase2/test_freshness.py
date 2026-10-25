"""Freshness logic test (design §6.3): stale iff age > 15 min OR
2 consecutive failed cycles. Pure functions, no I/O."""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
from logic import freshness_status  # noqa: E402

UTC = timezone.utc


def rows(specs, now):
    return [{"cycle_ts": (now - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "cycles_ok": ok} for m, ok in specs]


def main():
    # Truncate to whole seconds: timestamps are second-precision, so an
    # untruncated `now` would make the exact 15-minute boundary read as
    # 15min + epsilon and flip stale — a test artifact, not logic.
    now = datetime.now(UTC).replace(microsecond=0)
    assert freshness_status(rows([(5, 1)], now), now)["stale"] is False
    assert freshness_status(rows([(20, 1)], now), now)["stale"] is True  # age > 15
    assert freshness_status(rows([(15, 1)], now), now)["stale"] is False  # boundary
    assert freshness_status(rows([(5, 0), (10, 0)], now), now)["stale"] is True
    assert freshness_status(rows([(5, 0), (10, 1)], now), now)["stale"] is False
    assert freshness_status([], now)["stale"] is True  # no heartbeat at all
    print("FRESHNESS TEST: PASS (6 cases incl. 15-min boundary)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
