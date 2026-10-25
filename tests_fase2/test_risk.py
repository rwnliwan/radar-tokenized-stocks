"""Weekend risk score v1 test (design §5.5 + documented mappings)."""
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
from risk import weekend_risk_score  # noqa: E402


def main():
    # Calm: no dev, deep pools, open redemption, fresh PoR -> 0.
    s = weekend_risk_score(0.0, 5_000_000.0, "open", 0.0)
    assert s["total"] == 0.0 and s["max_possible"] == 100.0 and not s["partial"]
    # Dev cap: 5% -> 40 (not 50).
    s = weekend_risk_score(5.0, 5_000_000.0, "open", 0.0)
    assert s["components"]["deviation"] == 40.0
    # Depth: floor 250k -> 25; full 2.5M -> 0.
    assert weekend_risk_score(0.0, 100_000.0, "open", 0.0)["components"]["depth"] == 25.0
    assert weekend_risk_score(0.0, 2_500_000.0, "open", 0.0)["components"]["depth"] == 0.0
    # Redemption mapping + PoR cap.
    assert weekend_risk_score(0.0, 5_000_000.0, "closed", 0.0)["components"]["redemption"] == 20.0
    assert weekend_risk_score(0.0, 5_000_000.0, "gated", 0.0)["components"]["redemption"] == 10.0
    assert weekend_risk_score(0.0, 5_000_000.0, "open", 100.0)["components"]["por"] == 15.0
    # Unknown redemption + PoR -> excluded (partial, max 65), not zeroed.
    s = weekend_risk_score(1.0, 1_000_000.0, "unknown", None)
    assert s["partial"] and s["max_possible"] == 65.0
    assert s["components"]["redemption"] is None and s["components"]["por"] is None
    assert s["total"] == 26.7  # dev 10.0 + depth 16.7 (linear 250k..2.5M)
    print("RISK TEST: PASS (caps, mappings, partial-score handling)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
