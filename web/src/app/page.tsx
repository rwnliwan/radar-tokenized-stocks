"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import Header from "./Header";
import { fetchLatest, type LatestResponse, type TickerRow } from "../lib/api";
import { buildCsv } from "../lib/csv";
import {
  fmtDepth,
  fmtPct,
  fmtSigned1,
  fmtUsd,
  fmtWITA,
  redLabel,
  redPill,
  sparkBlocks,
  statusLabel,
} from "../lib/format";
import { t, u, type Lang } from "../lib/i18n";

const STALE_MIN = 15;
const POLL_MS = 60000;

type SortKey = "dev" | "depth" | "name" | "price" | "change";

export default function Home() {
  const [lang, setLang] = useState<Lang>("en");
  const [data, setData] = useState<LatestResponse | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("dev");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [tier, setTier] = useState<"all" | "1" | "2">("all");
  const [scale, setScale] = useState<"zoomed" | "fixed">("zoomed");
  const [, setTick] = useState(0);

  useEffect(() => {
    try {
      const s = localStorage.getItem("exit-radar-lang");
      if (s === "id" || s === "en") setLang(s);
    } catch {
      /* private mode: stay on default */
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await fetchLatest();
      setData(d);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (cancelled) return;
      await load();
    };
    run();
    const id = setInterval(run, POLL_MS);
    const tickId = setInterval(() => setTick((x) => x + 1), 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
      clearInterval(tickId);
    };
  }, [load]);

  const toggleLang = (l: Lang) => {
    setLang(l);
    try {
      localStorage.setItem("exit-radar-lang", l);
    } catch {
      /* ignore */
    }
  };

  const rows = useMemo(() => {
    if (!data) return [];
    const list = data.tickers.filter(
      (r) => tier === "all" || String(r.tier) === tier,
    );
    const by: Record<SortKey, (r: TickerRow) => number> = {
      dev: (r) => (r.dev_bps != null ? Math.abs(r.dev_bps) : -1),
      depth: (r) => (r.depth_usd ?? -1),
      name: (r) => 0,
      price: (r) => (r.dw_price ?? -1),
      change: (r) => (r.change_1h_bps ?? -99999),
    };
    return [...list].sort((a, b) => {
      if (sortKey === "name") {
        const c = a.ticker.localeCompare(b.ticker);
        return sortDir === "asc" ? c : -c;
      }
      const c = by[sortKey](a) - by[sortKey](b);
      return sortDir === "asc" ? c : -c;
    });
  }, [data, tier, sortKey, sortDir]);

  const worst = useMemo(() => {
    if (!data) return null;
    let w: TickerRow | null = null;
    for (const r of data.tickers) {
      if (r.dev_bps == null) continue;
      if (!w || Math.abs(r.dev_bps) > Math.abs(w.dev_bps ?? 0)) w = r;
    }
    return w;
  }, [data]);

  const maxDepth = useMemo(
    () => Math.max(0, ...(data?.tickers.map((r) => r.depth_usd ?? 0) ?? [0])),
    [data],
  );

  const latestTs = data?.meta.latest_ts ?? null;
  const ageMin = latestTs
    ? Math.round((Date.now() - Date.parse(latestTs)) / 60000)
    : null;
  const stale = ageMin != null && ageMin > STALE_MIN;

  const redStatus = useMemo(() => {
    const found = data?.tickers.find((r) => r.redemption_status != null);
    return found?.redemption_status ?? null;
  }, [data]);
  const redNextOpen = useMemo(() => {
    const found = data?.tickers.find((r) => r.redemption_next_open != null);
    return found?.redemption_next_open ?? null;
  }, [data]);
  const porMaxAge = useMemo(() => {
    const ages = (data?.tickers ?? [])
      .map((r) => r.por_age_hours)
      .filter((a): a is number => a != null);
    return ages.length ? Math.max(...ages) : null;
  }, [data]);

  const plotted = useMemo(
    () => rows.filter((r) => r.dev_bps != null).sort((a, b) => (b.dev_bps ?? 0) - (a.dev_bps ?? 0)),
    [rows],
  );
  const notPlotted = useMemo(
    () => rows.filter((r) => r.dev_bps == null).map((r) => r.ticker),
    [rows],
  );
  const barsRange = useMemo(() => {
    if (!plotted.length) return { lo: -100, hi: 100 };
    if (scale === "fixed") return { lo: -100, hi: 100 };
    const vals = plotted.map((r) => r.dev_bps ?? 0);
    return { lo: Math.min(...vals, 0) - 5, hi: Math.max(...vals, 0) + 5 };
  }, [plotted, scale]);
  const zeroPct =
    barsRange.hi === barsRange.lo
      ? 50
      : ((0 - barsRange.lo) / (barsRange.hi - barsRange.lo)) * 100;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  };

  const sortHead = (key: SortKey, label: string, thClass?: string) => {
    const active = sortKey === key;
    return (
      <th
        className={thClass}
        aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      >
        <button
          type="button"
          className="sortbtn"
          onClick={() => toggleSort(key)}
          aria-label={
            active ? `${label}, ${u(lang, sortDir === "asc" ? "dir_asc" : "dir_desc")}` : label
          }
        >
          {label} {active && <span className="ind">{sortDir === "asc" ? "▲" : "▼"}</span>}
        </button>
      </th>
    );
  };

  const downloadCsv = () => {
    const blob = new Blob([buildCsv(rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = u(lang, "csv_filename");
    a.click();
    URL.revokeObjectURL(url);
  };

  const freshnessText = latestTs
    ? ageMin != null && ageMin <= 0
      ? t(lang, "freshness_now", { time: fmtWITA(latestTs, lang) })
      : t(lang, "freshness", { time: fmtWITA(latestTs, lang), mins: ageMin ?? 0 })
    : t(lang, "loading");

  return (
    <div className="wrap">
      <Header lang={lang} onLangChange={toggleLang} active="home" right={<span>{freshnessText}</span>} />

      {stale && latestTs && (
        <div className="banner" role="status">
          {t(lang, "stale_banner", { time: fmtWITA(latestTs, lang) })}
        </div>
      )}
      {error && data && (
        <div className="errorbox" role="alert">
          {u(lang, "load_error")}{" "}
          <button type="button" onClick={load}>
            {u(lang, "retry")}
          </button>
        </div>
      )}

      {!data && loading && (
        <div aria-busy="true" aria-label={t(lang, "loading")}>
          <div className="hero-band" aria-hidden="true">
            <div>
              <div className="skel" style={{ width: 120 }} />
              <div className="skel" style={{ width: 180, height: 38, margin: "10px 0" }} />
            </div>
            <div className="skel" style={{ width: 200, height: 14 }} />
          </div>
          <div className="statstrip" aria-hidden="true">
            <div className="skel" style={{ width: 140, height: 14 }} />
            <div className="skel" style={{ width: 120, height: 14 }} />
            <div className="skel" style={{ width: 160, height: 14 }} />
          </div>
          <p className="hint">{t(lang, "loading")}</p>
        </div>
      )}

      {data && (
        <>
          <div className="hero-band">
            <div>
              <div className="lbl">{t(lang, "kpi_worst")}</div>
              <div className="big">{worst ? fmtSigned1(worst.dev_bps) + " bps" : "—"}</div>
            </div>
            <div className="sub">
              {worst
                ? t(lang, "kpi_worst_sub", {
                    ticker: worst.ticker,
                    depth: fmtDepth(worst.depth_usd),
                  })
                : t(lang, "no_data")}
            </div>
          </div>
          <div className="statstrip">
            <span>
              {data.tickers.length} {t(lang, "nav_ticker")} ·{" "}
              <b>
                {data.meta.venues_live}/{data.meta.venues_total}
              </b>{" "}
              {t(lang, "kpi_venues_sub")}
            </span>
            <span>
              {t(lang, "kpi_por")}:{" "}
              <b>{porMaxAge != null ? `${Math.round(porMaxAge)}h` : "—"}</b>{" "}
              {porMaxAge != null ? u(lang, "por_stale_sub") : t(lang, "kpi_por_sub")}
            </span>
            <span>
              {t(lang, "kpi_redemption")}: <b>{redLabel(lang, redStatus)}</b>{" "}
              {redStatus === "paused"
                ? t(lang, "kpi_redemption_sub_paused")
                : redStatus != null
                  ? t(lang, "kpi_redemption_sub_live")
                  : t(lang, "kpi_redemption_sub")}
              {redNextOpen && redStatus !== "open" && (
                <>
                  {" · "}
                  {t(lang, "next_open_label")}: {fmtWITA(redNextOpen, lang)}
                </>
              )}
            </span>
          </div>

          <div className="cover">
            <b>{t(lang, "coverage_live_line")}</b>
            <br />
            {t(lang, "coverage_short")}
          </div>

          <h2>{t(lang, "heatmap_title")}</h2>
          <div className="controls">
            <span className="lbl">{t(lang, "sort_label")}:</span>
            <span className="seg" role="group" aria-label={t(lang, "sort_label")}>
              <button
                type="button"
                aria-pressed={sortKey === "dev"}
                onClick={() => {
                  setSortKey("dev");
                  setSortDir("desc");
                }}
              >
                {t(lang, "sort_dev")}
              </button>
              <button
                type="button"
                aria-pressed={sortKey === "depth"}
                onClick={() => {
                  setSortKey("depth");
                  setSortDir("desc");
                }}
              >
                {t(lang, "sort_depth")}
              </button>
              <button
                type="button"
                aria-pressed={sortKey === "name"}
                onClick={() => {
                  setSortKey("name");
                  setSortDir("asc");
                }}
              >
                {t(lang, "sort_name")}
              </button>
            </span>
            <span className="lbl">{t(lang, "tier_filter")}:</span>
            <span className="seg" role="group" aria-label={t(lang, "tier_filter")}>
              <button type="button" aria-pressed={tier === "all"} onClick={() => setTier("all")}>
                {t(lang, "tier_all")}
              </button>
              <button type="button" aria-pressed={tier === "1"} onClick={() => setTier("1")}>
                Tier 1
              </button>
              <button type="button" aria-pressed={tier === "2"} onClick={() => setTier("2")}>
                Tier 2
              </button>
            </span>
            <button type="button" className="refresh" onClick={load} disabled={loading}>
              {loading ? t(lang, "refresh_updating") : t(lang, "refresh_button")}
            </button>
            <button type="button" className="refresh" onClick={downloadCsv}>
              {t(lang, "download_csv")}
            </button>
          </div>
          <p className="hint">
            {t(lang, "home_table_note_cycle")} {t(lang, "home_table_hint")}{" "}
            {u(lang, "auto_refresh")}.
          </p>

          <div className="tblwrap home-tbl">
            <table>
              <thead>
                <tr>
                  {sortHead("name", t(lang, "col_ticker"))}
                  <th className="hide-s">{t(lang, "col_tier")}</th>
                  {sortHead("price", t(lang, "dw_price"))}
                  {sortHead("dev", t(lang, "col_dev_bps"))}
                  <th className="hide-s">{t(lang, "col_spread")}</th>
                  {sortHead("depth", t(lang, "col_depth10k"))}
                  <th className="hide-m">{t(lang, "col_depth_bar")}</th>
                  <th className="hide-s">{t(lang, "redemption_title")}</th>
                  <th className="hide-s">{t(lang, "por_age_label")}</th>
                  <th>{t(lang, "col_status")}</th>
                  {sortHead(
                    "change",
                    t(lang, "col_change", { window: t(lang, "window_1h") }),
                    "hide-s",
                  )}
                  <th className="hide-s">{t(lang, "col_spark")}</th>
                  <th>{t(lang, "detail_link")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const alpha =
                    r.dev_bps != null ? Math.min(Math.abs(r.dev_bps) / 100, 0.5) : 0;
                  const tint =
                    r.dev_bps != null ? { background: `rgba(224,123,74,${alpha.toFixed(2)})` } : {};
                  return (
                    <tr key={r.ticker}>
                      <td className="tk">
                        <Link href={`/ticker/${r.ticker}`}>
                          <b>{r.ticker}</b>
                        </Link>
                      </td>
                      <td className="hide-s">{r.tier ?? "—"}</td>
                      <td className="num">{fmtUsd(r.dw_price)}</td>
                      <td className="num dev" style={tint}>
                        {fmtSigned1(r.dev_bps)}
                      </td>
                      <td className="num hide-s">{fmtPct(r.spread_pct)}</td>
                      <td className="num hide-s">{fmtDepth(r.depth_usd)}</td>
                      <td className="hide-m">
                        <div className="dbar">
                          <i
                            style={{
                              width: `${maxDepth > 0 ? ((r.depth_usd ?? 0) / maxDepth) * 100 : 0}%`,
                            }}
                          />
                        </div>
                      </td>
                      <td className="hide-s">
                        <span className={`pill ${redPill(r.redemption_status)}`}>
                          {redLabel(lang, r.redemption_status)}
                        </span>
                      </td>
                      <td className="dim hide-s">
                        {r.por_age_hours != null
                          ? `${Math.round(r.por_age_hours)}h`
                          : t(lang, "por_not_published")}
                      </td>
                      <td>
                        <span className={`pill ${r.status}`}>
                          {statusLabel(lang, r.status)}
                        </span>
                      </td>
                      <td
                        className={`num hide-s ${r.change_1h_bps != null && r.change_1h_bps < 0 ? "neg" : r.change_1h_bps != null && r.change_1h_bps > 0 ? "pos" : ""}`}
                      >
                        {fmtSigned1(r.change_1h_bps)}
                      </td>
                      <td className="spark hide-s">{sparkBlocks(r.spark_bps)}</td>
                      <td>
                        <Link className="detailbtn" href={`/ticker/${r.ticker}`}>
                          {t(lang, "detail_link")} →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="rowcards">
            {rows.map((r) => (
              <div className="rc" key={r.ticker}>
                <div className="top">
                  <Link href={`/ticker/${r.ticker}`}>
                    <b>{r.ticker}</b>
                  </Link>
                  <span className={`pill ${r.status}`}>
                    {statusLabel(lang, r.status)}
                  </span>
                </div>
                <div className="mid">
                  <span className="num">{fmtUsd(r.dw_price)}</span>
                  <span className="spark">{sparkBlocks(r.spark_bps)}</span>
                  <span className="num">
                    <b>{fmtSigned1(r.dev_bps)} bps</b>
                  </span>
                </div>
                <div className="mid">
                  <span className="dim">
                    {t(lang, "col_depth10k")}: {fmtDepth(r.depth_usd)}
                  </span>
                  <Link className="detailbtn" href={`/ticker/${r.ticker}`}>
                    {t(lang, "detail_link")} →
                  </Link>
                </div>
              </div>
            ))}
          </div>
          {rows.length === 0 && <p className="hint">{t(lang, "no_data")}</p>}

          <h2>{t(lang, "bars_title")}</h2>
          <div className="controls">
            <span className="lbl">{t(lang, "bars_scale_label")}:</span>
            <span className="seg" role="group" aria-label={t(lang, "bars_scale_label")}>
              <button
                type="button"
                aria-pressed={scale === "zoomed"}
                onClick={() => setScale("zoomed")}
              >
                {t(lang, "bars_scale_zoomed")}
              </button>
              <button
                type="button"
                aria-pressed={scale === "fixed"}
                onClick={() => setScale("fixed")}
              >
                {t(lang, "bars_scale_fixed")}
              </button>
            </span>
          </div>
          <div className="chart">
            {plotted.map((r) => {
              const v = r.dev_bps ?? 0;
              const pct = ((v - barsRange.lo) / (barsRange.hi - barsRange.lo)) * 100;
              const left = v < 0 ? pct : zeroPct;
              const width = v < 0 ? zeroPct - pct : pct - zeroPct;
              return (
                <div className="brow" key={r.ticker}>
                  <span className="bt">{r.ticker}</span>
                  <span className="btrack">
                    <i
                      className={r.status === "na" ? "" : r.status}
                      style={{ left: `${left.toFixed(1)}%`, width: `${Math.max(width, 0).toFixed(1)}%` }}
                    />
                    <b className="zero" style={{ left: `${zeroPct.toFixed(1)}%` }} />
                  </span>
                  <span className="bv">{fmtSigned1(r.dev_bps)}</span>
                </div>
              );
            })}
            <div className="axis">
              <span>{Math.round(barsRange.lo)} bps</span>
              <span>0</span>
              <span>{Math.round(barsRange.hi)} bps</span>
            </div>
            <p className="hint" style={{ margin: "10px 0 0" }}>
              {t(lang, "bars_note")}{" "}
              {t(lang, "bars_range", {
                lo: fmtSigned1(barsRange.lo),
                hi: fmtSigned1(barsRange.hi),
              })}
              {scale === "fixed" &&
                plotted.some((r) => Math.abs(r.dev_bps ?? 0) > 100) && (
                  <>
                    {" "}
                    {t(lang, "bars_clipped", {
                      tickers: plotted
                        .filter((r) => Math.abs(r.dev_bps ?? 0) > 100)
                        .map((r) => r.ticker)
                        .join(", "),
                    })}
                  </>
                )}
              {notPlotted.length > 0 && (
                <>
                  <br />
                  {t(lang, "bars_nodata")} {notPlotted.join(", ")}.
                </>
              )}
            </p>
          </div>

          <div className="foot">
            {u(lang, "method_short")}
            <br />
            {t(lang, "disclaimer")} {t(lang, "footer_note")}
            <br />
            <a href="https://www.linkedin.com/in/septian-panjaya">
              {t(lang, "linkedin_label")}
            </a>
          </div>
        </>
      )}

      {!data && error && (
        <div className="errorbox" role="alert">
          {u(lang, "load_error")}{" "}
          <button type="button" onClick={load}>
            {u(lang, "retry")}
          </button>
        </div>
      )}
    </div>
  );
}
