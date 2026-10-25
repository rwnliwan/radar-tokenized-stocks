"""Dashboard live-read test (task test (a), data layer).

Reads live Turso through the dashboard's own client and prints counts.
Fails loudly on any read error — a pass here plus the server-boot
test together prove the app serves real data, not mocks.
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
from turso_read import query  # noqa: E402


def main():
    uni = query("SELECT COUNT(*) AS n FROM universe")
    assert int(uni[0]["n"]) == 13, uni
    health = query("SELECT cycle_ts, cycles_ok FROM poller_health "
                   "ORDER BY id DESC LIMIT 1")
    assert health, "no poller_health rows"
    devs = query("SELECT COUNT(DISTINCT ticker_id) AS n FROM deviations")
    assert int(devs[0]["n"]) == 13, devs
    snaps = query("SELECT COUNT(*) AS n FROM snapshots")
    print(f"universe={uni[0]['n']} tickers, deviations tickers={devs[0]['n']}, "
          f"snapshots={snaps[0]['n']}, latest health={health[0]['cycle_ts']} "
          f"(ok={health[0]['cycles_ok']})")
    age = (datetime.now(timezone.utc)
           - datetime.fromisoformat(health[0]["cycle_ts"].replace("Z", "+00:00"))).total_seconds() / 60
    print(f"health age: {age:.1f} min")
    print("DASHBOARD DATA TEST: PASS (live reads OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
