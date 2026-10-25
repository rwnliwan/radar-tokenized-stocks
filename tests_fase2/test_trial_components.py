"""Trial components test (2026-10-25): AG Grid options + ECharts options.

Pure builders from dashboard/trial_components.py — no Streamlit run,
no Turso, no network. Asserts the trial preserves the old table/chart
contract in BOTH languages: same display columns, hidden numeric
helpers, deviation tint, depth-bar and Detail-link renderers,
single-row selection, bps-descending bars with status colors and
full tooltips.
"""
import sys

sys.path.insert(0, "/home/hatch/workspace/radar-tokenized-stocks/dashboard")
import pandas as pd  # noqa: E402
from i18n import t  # noqa: E402
from trial_components import (  # noqa: E402
    build_bars_options, build_home_grid_options)


def _grid_df(lang):
    return pd.DataFrame([{
        t(lang, "col_ticker"): "TSLAx",
        t(lang, "col_tier"): "1",
        t(lang, "col_best_price"): "$371.55 (Raydium)",
        t(lang, "col_dev_bps"): "+12.3",
        t(lang, "col_spread"): "+0.10%",
        t(lang, "col_depth10k"): "$2,937,468",
        t(lang, "col_depth_bar"): 2937468.0,
        t(lang, "redemption_title"): "Closed",
        t(lang, "por_age_label"): "Not published",
        t(lang, "col_status"): "OK",
        t(lang, "col_change", window="1h"): "+1.2",
        t(lang, "col_spark"): "▁▃▅▇",
        t(lang, "detail_link"): "Detail",
        "_bps_num": 12.3, "_depth_num": 2937468.0,
        "_depth_max": 6116895.0, "_detail_url": "?ticker=TSLAx",
    }])


def main():
    for lang in ("en", "id"):
        df = _grid_df(lang)
        opts = build_home_grid_options(df, lang)
        defs = {c["field"]: c for c in opts["columnDefs"]}
        display = [c for c in defs if not c.startswith("_")]
        assert display == [
            t(lang, "col_ticker"), t(lang, "col_tier"),
            t(lang, "col_best_price"), t(lang, "col_dev_bps"),
            t(lang, "col_spread"), t(lang, "col_depth10k"),
            t(lang, "col_depth_bar"), t(lang, "redemption_title"),
            t(lang, "por_age_label"), t(lang, "col_status"),
            t(lang, "col_change", window="1h"), t(lang, "col_spark"),
            t(lang, "detail_link")], display
        for helper in ("_bps_num", "_depth_num", "_depth_max", "_detail_url"):
            assert defs[helper].get("hide") is True, helper
        assert "cellStyle" in defs[t(lang, "col_dev_bps")], "dev tint missing"
        assert "cellRenderer" in defs[t(lang, "col_depth_bar")], \
            "bar renderer missing"
        assert "cellRenderer" in defs[t(lang, "detail_link")], \
            "link renderer missing"
        assert defs[t(lang, "por_age_label")].get("cellStyle") == {
            "color": "#8a8580"}
        assert opts.get("rowSelection") == "single", opts.get("rowSelection")
    # Bars: bps-descending categories, status colors, full tooltips.
    rows = [
        {"ticker": "B", "bps": -80.0, "status": "watch",
         "status_label": "Watch", "venue": "Raydium", "price": "$1.00",
         "depth": "$100", "por": "Not published", "ts": "now"},
        {"ticker": "A", "bps": 150.0, "status": "alert",
         "status_label": "Alert", "venue": "Orca", "price": "$2.00",
         "depth": "$200", "por": "Not published", "ts": "now"},
        {"ticker": "C", "bps": 5.0, "status": "ok",
         "status_label": "OK", "venue": "Meteora", "price": "$3.00",
         "depth": "$300", "por": "Not published", "ts": "now"},
    ]
    bo = build_bars_options(rows, -100.0, 100.0, "en")
    # bps-descending: A (150) > C (5) > B (-80).
    assert bo["yAxis"]["data"] == ["A", "C", "B"], bo["yAxis"]["data"]
    assert bo["yAxis"]["inverse"] is True
    assert bo["xAxis"]["min"] == -100.0 and bo["xAxis"]["max"] == 100.0
    data = bo["series"][0]["data"]
    assert [d["itemStyle"]["color"] for d in data] == [
        "#C2410C", "#D8D2C8", "#E07B4A"], data
    tip = data[2]["tooltip"]["formatter"]
    for needle in ("B", "-80.0", "Watch", "Raydium", "$1.00", "$100",
                   "Not published", "now"):
        assert needle in tip, (needle, tip)
    print("TRIAL COMPONENTS TEST: PASS (grid options + bars options OK)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
