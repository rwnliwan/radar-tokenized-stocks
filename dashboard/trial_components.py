"""Trial components (2026-10-25): AG Grid home table + ECharts bars.

Pure builders (no Streamlit calls, no I/O) so they are unit-testable
without running the app. The JsCode renderers below run inside the
AG Grid component iframe — app-level inline <script> is still not
used anywhere. The deviation tint mirrors the old Styler formula
(tint_dev, divisor 200 for basis-point columns: opacity =
min(|bps| / 200, 0.85), applied only above 0.02).
"""

from st_aggrid import GridOptionsBuilder, JsCode as AgJsCode

from i18n import t

_DETAIL_RENDERER = AgJsCode("""
class DetailLinkRenderer {
  init(params) {
    this.eGui = document.createElement('a');
    this.eGui.innerText = params.value;
    this.eGui.href = params.data._detail_url;
    this.eGui.style.color = '#16130F';
    this.eGui.style.textDecoration = 'underline';
    this.eGui.style.textDecorationColor = '#C2410C';
    this.eGui.style.textUnderlineOffset = '2px';
  }
  getGui() { return this.eGui; }
  refresh(params) { return false; }
}
""")

_DEPTH_BAR_RENDERER = AgJsCode("""
class DepthBarRenderer {
  init(params) {
    const max = params.data._depth_max > 0 ? params.data._depth_max : 1;
    const pct = Math.max(0, Math.min(100, (params.value / max) * 100));
    this.eGui = document.createElement('div');
    this.eGui.style.width = '100%';
    this.eGui.style.height = '100%';
    this.eGui.style.display = 'flex';
    this.eGui.style.alignItems = 'center';
    const bar = document.createElement('div');
    bar.style.height = '14px';
    bar.style.width = pct + '%';
    bar.style.backgroundColor = '#0F766E';
    this.eGui.appendChild(bar);
  }
  getGui() { return this.eGui; }
  refresh(params) { return false; }
}
""")

_DEV_TINT_STYLE = AgJsCode("""
function(params) {
  const v = params.data._bps_num;
  if (v === null || v === undefined || isNaN(v)) { return {}; }
  const a = Math.min(Math.abs(v) / 200.0, 0.85);
  if (a <= 0.02) { return {}; }
  return { backgroundColor: 'rgba(194, 65, 12, ' + a.toFixed(2) + ')' };
}
""")

# PoR column stays dimmed (Wave 3 note carried over from the Styler
# version): it repeats "Not published" on every row, while redemption
# now carries live values and must never be dimmed.
_POR_DIM = {"color": "#8a8580"}

_HELPER_COLUMNS = ("_bps_num", "_depth_num", "_depth_max", "_detail_url")


def build_home_grid_options(grid_df, lang):
    """AG Grid options for the home master table.

    grid_df carries the display columns (same labels and values as the
    old st.dataframe version) plus hidden numeric helpers: _bps_num
    (deviation tint), _depth_num/_depth_max (depth bar scaling),
    _detail_url (Detail link target). Native sorting/filtering on,
    single-row selection, streamlit theme (set by the caller).
    """
    gb = GridOptionsBuilder.from_dataframe(grid_df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_column(t(lang, "col_dev_bps"), cellStyle=_DEV_TINT_STYLE)
    gb.configure_column(t(lang, "col_depth_bar"),
                        cellRenderer=_DEPTH_BAR_RENDERER)
    gb.configure_column(t(lang, "detail_link"),
                        cellRenderer=_DETAIL_RENDERER)
    gb.configure_column(t(lang, "por_age_label"), cellStyle=_POR_DIM)
    for helper in _HELPER_COLUMNS:
        gb.configure_column(helper, hide=True)
    return gb.build()


_STATUS_COLORS = {"ok": "#D8D2C8", "watch": "#E07B4A", "alert": "#C2410C"}


def build_bars_options(rows, lo, hi, lang):
    """ECharts options for the diverging deviation bars.

    rows are the render_comparison_bars dicts (ticker, bps, status,
    status_label, venue, price, depth, por, ts). Categories are
    bps-descending with the axis inverted so the largest bar sits on
    top (the old Altair sort="-x"). Each bar carries its own tooltip
    formatter string, so no JavaScript function is needed to show
    venue/price/depth/PoR/timestamp.
    """
    ordered = sorted(rows, key=lambda r: r["bps"], reverse=True)
    data = []
    for r in ordered:
        tip = "<br/>".join([
            r["ticker"],
            f"{t(lang, 'col_dev_bps')}: {r['bps']:+.1f}",
            f"{t(lang, 'col_status')}: {r['status_label']}",
            f"{t(lang, 'col_dex')}: {r['venue']}",
            f"{t(lang, 'col_price_usd')}: {r['price']}",
            f"{t(lang, 'col_depth')}: {r['depth']}",
            f"{t(lang, 'por_age_label')}: {r['por']}",
            f"{t(lang, 'col_updated')}: {r['ts']}",
        ])
        data.append({
            "value": round(r["bps"], 1),
            "itemStyle": {"color": _STATUS_COLORS.get(r["status"], "#D8D2C8")},
            "tooltip": {"formatter": tip},
        })
    return {
        "tooltip": {"trigger": "item"},
        "grid": {"left": "60px", "right": "30px", "top": "10px",
                 "bottom": "10px", "containLabel": True},
        "xAxis": {"type": "value", "min": lo, "max": hi,
                  "name": t(lang, "col_dev_bps")},
        "yAxis": {"type": "category",
                  "data": [r["ticker"] for r in ordered], "inverse": True},
        "series": [{"type": "bar", "data": data}],
    }
