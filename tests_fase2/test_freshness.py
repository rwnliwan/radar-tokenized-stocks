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
    # Fix ronde 5 (M4): age anchors on the LAST SUCCESS, not the newest
    # row — a failed cycle's fresh timestamp must not hide data age.
    st = freshness_status(rows([(5, 0), (10, 1)], now), now)
    assert st["age_min"] == 10.0, f"age anchors on success: {st['age_min']}"
    assert st["last_ts"] == rows([(5, 0), (10, 1)], now)[1]["cycle_ts"]
    assert st["failed_streak"] == 1
    st = freshness_status(rows([(5, 0), (10, 0), (20, 1)], now), now)
    assert st["stale"] is True, "last success 20 min ago -> stale"
    assert st["age_min"] == 20.0 and st["failed_streak"] == 2
    st = freshness_status(rows([(5, 0), (10, 0)], now), now)
    assert st["age_min"] is None and st["last_ts"] is None, "no success -> no age"
    print("FRESHNESS TEST: PASS (6 cases incl. 15-min boundary + last-success anchor)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
