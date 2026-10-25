"""i18n test: EN/ID key parity + real translations (not fallbacks)."""
import os
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
from i18n import STR, t  # noqa: E402

PROSE_KEYS = ["app_tagline", "landing_line", "coverage_text", "close_note",
              "risk_method", "waitlist_intro", "donate_note", "disclaimer",
              "policy_text", "f_error", "stale_banner"]


def main():
    en, idn = STR["en"], STR["id"]
    assert set(en) == set(idn), (
        f"key mismatch: EN-only={sorted(set(en) - set(idn))} "
        f"ID-only={sorted(set(idn) - set(en))}")
    for k in PROSE_KEYS:
        assert en[k] != idn[k], f"key {k!r} not actually translated"
    assert t("id", "freshness", time="T", mins=3) == \
        "Terakhir diperbarui: T (3 menit lalu)"
    assert t("en", "freshness", time="T", mins=3) == \
        "Last updated: T (3 min ago)"
    assert t("xx", "no_data") == "No data yet."  # unknown lang -> EN fallback
    print(f"I18N TEST: PASS ({len(en)} keys, parity + translations OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
