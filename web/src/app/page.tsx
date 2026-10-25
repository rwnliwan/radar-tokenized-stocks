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

  /* v3.1 (opsi A, ACC Septian 25 Okt): DEX verdict from THREE signals, not
     deviation alone — a low deviation must not certify an exit when the
     spread is wide or depth is thin. Danger comes only from deviation
     (≥100 bps, the established tier); spread ≥1% and depth <$250k demote
     to caution at most — no invented thresholds. Missing signals are
     skipped, never zeroed. Redemption and PoR stay out of this verdict
     and are shown separately (stat strip below). */
  const worstSpread = useMemo(() => {
    let w: TickerRow | null = null;
    for (const r of data?.tickers ?? []) {
      if (r.spread_pct == null) continue;
      if (!w || r.spread_pct > (w.spread_pct ?? 0)) w = r;
    }
    return w;
  }, [data]);
  const minDepth = useMemo(() => {
    let m: TickerRow | null = null;
    for (const r of data?.tickers ?? []) {
      if (r.depth_usd == null) continue;
      if (!m || r.depth_usd < (m.depth_usd ?? Infinity)) m = r;
    }
    return m;
  }, [data]);
  const verdict = useMemo(() => {
    const wd = worst != null ? Math.abs(worst.dev_bps ?? 0) : null;
    if (wd == null && worstSpread == null && minDepth == null) return null;
    if (wd != null && wd >= 100) return "danger";
    if (
      (wd != null && wd >= 50) ||
      (worstSpread != null && (worstSpread.spread_pct ?? 0) >= 1) ||
      (minDepth != null && (minDepth.depth_usd ?? Infinity) < 250000)
    )
      return "caution";
    return "safe";
  }, [worst, worstSpread, minDepth]);
  const verdictText =
    verdict == null
      ? "—"
      : verdict === "safe"
        ? u(lang, "verdict_safe")
        : verdict === "caution"
          ? u(lang, "verdict_caution")
          : u(lang, "verdict_danger");
  const verdictFacts: string[] = [];
  if (worst)
    verdictFacts.push(
      `${u(lang, "verdict_dev_worst")}: ${worst.ticker} ${fmtSigned1(worst.dev_bps)} bps`,
    );
  if (worstSpread)
    verdictFacts.push(
      `${u(lang, "verdict_spread_worst")}: ${worstSpread.ticker} ${worstSpread.spread_pct?.toFixed(2)}%`,
    );
  if (minDepth)
    verdictFacts.push(
      `${u(lang, "verdict_depth_min")}: ${minDepth.ticker} ${fmtDepth(minDepth.depth_usd)}`,
    );
  /* Coverage honesty (QA 25 Okt): the verdict skips tickers without a
     deviation, so say so in the card itself, counted live. */
  if (data)
    verdictFacts.push(
      u(lang, "verdict_coverage")
        .replace("{n}", String(data.tickers.filter((r) => r.dev_bps != null).length))
        .replace("{total}", String(data.tickers.length)),
    );
  const blips = useMemo(() => {
    const list = (data?.tickers ?? [])
      .filter((r) => r.dev_bps != null)
      .sort((a, b) => Math.abs(b.dev_bps ?? 0) - Math.abs(a.dev_bps ?? 0));
    /* Real deviations cluster near the center (all <50 bps on calm days),
       so the top-4 labels would collide. Keep at most 4 labels, dropping
       any label whose center lands within 45px of an already-placed one. */
    const placed: { x: number; y: number }[] = [];
    return list.map((r, i) => {
      const a = Math.min(Math.abs(r.dev_bps ?? 0), 100);
      const rad = 22 + (a / 100) * 86;
      const ang = (i * 137.5 * Math.PI) / 180;
      const cx = 120 + rad * Math.cos(ang);
      const cy = 120 + rad * Math.sin(ang);
      const fill =
        r.status === "alert" ? "#f87171" : r.status === "watch" ? "#fb923c" : "#4ade80";
      const lx = Math.max(30, Math.min(210, cx));
      const ly = cy <= 120 ? cy + 18 : cy - 12;
      let label = i < 4;
      if (label) {
        for (const p of placed) {
          if (Math.hypot(lx - p.x, ly - p.y) < 45) {
            label = false;
            break;
          }
        }
      }
      if (label) placed.push({ x: lx, y: ly });
      return { ticker: r.ticker, cx, cy, fill, label, lx, ly };
    });
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
          <div className="scope-hero" aria-hidden="true">
            <div className="skel" style={{ width: 240, height: 240, borderRadius: "50%" }} />
            <div style={{ flex: 1 }}>
              <div className="skel" style={{ width: 160 }} />
              <div className="skel" style={{ width: 220, height: 30, margin: "10px 0" }} />
              <div className="skel" style={{ width: 200, height: 14 }} />
            </div>
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
          <div className="scope-hero">
            <div className="scope">
              <svg
                width="240"
                height="240"
                viewBox="0 0 240 240"
                role="img"
                aria-label={u(lang, "scope_label")}
              >
                <circle cx="120" cy="120" r="112" fill="none" stroke="#fbbf24" strokeWidth="1.5" opacity=".8" />
                <circle cx="120" cy="120" r="78" fill="none" stroke="#8ba190" strokeWidth="1" opacity=".5" />
                <circle cx="120" cy="120" r="44" fill="none" stroke="#8ba190" strokeWidth="1" opacity=".5" />
                <line x1="120" y1="8" x2="120" y2="232" stroke="#8ba190" strokeWidth="1" opacity=".35" />
                <line x1="8" y1="120" x2="232" y2="120" stroke="#8ba190" strokeWidth="1" opacity=".35" />
                <g className="sweep">
                  <path d="M120 120 L120 14 A106 106 0 0 1 195 45 Z" fill="#fbbf24" opacity=".28" />
                  <line x1="120" y1="120" x2="120" y2="14" stroke="#fbbf24" strokeWidth="2" />
                </g>
                <circle cx="120" cy="120" r="4" fill="#fbbf24" />
                {blips.map((b) => (
                  <g key={b.ticker}>
                    <circle cx={b.cx} cy={b.cy} r={b.label ? 6 : 4} fill={b.fill} />
                    {b.label && (
                      <text
                        x={b.lx}
                        y={b.ly}
                        textAnchor="middle"
                        fill={b.fill}
                        fontSize="11"
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {b.ticker}
                      </text>
                    )}
                  </g>
                ))}
              </svg>
            </div>
            <div className="verdict">
              <div className="lbl">{u(lang, "verdict_label")}</div>
              <div className={`vtext ${verdict ?? ""}`}>{verdictText}</div>
              <div className="worst">{worst ? fmtSigned1(worst.dev_bps) + " bps" : "—"}</div>
              <div className="sub">
                {verdictFacts.length ? verdictFacts.join(" · ") : t(lang, "no_data")}
              </div>
              <div className="rule">{u(lang, "verdict_rule")}</div>
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

          <div className="tg-card">
            <svg className="tg-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" /></svg>
            <div className="tg-text">
              <b>{u(lang, "tg_card_title")}</b>
              <p>{u(lang, "tg_card_note")}</p>
              <div className="tg-btns">
                <a className="btn tg-btn" href="https://t.me/exitradar_en" target="_blank" rel="noreferrer">{u(lang, "tg_ch_en")}</a>
                <a className="btn tg-btn" href="https://t.me/exitradar_in" target="_blank" rel="noreferrer">{u(lang, "tg_ch_id")}</a>
              </div>
            </div>
          </div>

          <div className="foot">
            {u(lang, "method_short")}
            <br />
            {t(lang, "disclaimer")} {t(lang, "footer_note")}
            <br />
            <a href="https://www.linkedin.com/in/septian-panjaya">
              {t(lang, "linkedin_label")}
            </a>
            <br />
            Telegram: <a href="https://t.me/exitradar_en">EN</a> · <a href="https://t.me/exitradar_in">ID</a>
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
