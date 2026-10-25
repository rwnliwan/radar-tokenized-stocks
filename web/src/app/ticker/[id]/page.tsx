"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import Header from "../../Header";
import HistoryChart from "../Chart";
import {
  fetchHistory,
  fetchTicker,
  type HistoryPoint,
  type TickerDetail,
} from "../../../lib/api";
import {
  fmtDepth,
  fmtPct,
  fmtSigned1,
  fmtUsd,
  fmtWITA,
  marketIsOpen,
  redLabel,
  redPill,
  sparkBlocks,
  statusLabel,
} from "../../../lib/format";
import { t, u, type Lang } from "../../../lib/i18n";
import { weekendRiskScore } from "../../../lib/risk";

type Window = "1h" | "24h" | "7d";

// next-on-pages serves dynamic routes on the Edge Runtime only.
export const runtime = "edge";

const KNOWN_ID_SOURCE =
  "DESAIN §1.1 / riset 24 Okt (dokumentasi, bukan observasi live)";
const KNOWN_ID_SOURCE_EN =
  "Design §1.1 / 24 Oct research (documentation, not a live observation)";

export default function TickerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const ticker = id.toUpperCase();
  const [lang, setLang] = useState<Lang>("en");
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [window, setWindow] = useState<Window>("24h");
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [histLoading, setHistLoading] = useState(true);

  useEffect(() => {
    try {
      const s = localStorage.getItem("exit-radar-lang");
      if (s === "id" || s === "en") setLang(s);
    } catch {
      /* ignore */
    }
  }, []);

  const loadDetail = useCallback(async () => {
    setLoading(true);
    try {
      setDetail(await fetchTicker(ticker));
      setNotFound(false);
      setError(false);
    } catch (e) {
      if (e instanceof Error && e.message === "NOT_FOUND") setNotFound(true);
      else setError(true);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  const loadHistory = useCallback(async () => {
    setHistLoading(true);
    try {
      setHistory(await fetchHistory(ticker, window));
    } catch {
      setHistory([]);
    } finally {
      setHistLoading(false);
    }
  }, [ticker, window]);

  useEffect(() => {
    loadDetail();
    const idInt = setInterval(loadDetail, 60000);
    return () => clearInterval(idInt);
  }, [loadDetail]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const toggleLang = (l: Lang) => {
    setLang(l);
    try {
      localStorage.setItem("exit-radar-lang", l);
    } catch {
      /* ignore */
    }
  };

  const refreshAll = () => {
    loadDetail();
    loadHistory();
  };

  const windowLabel = (w: Window) =>
    w === "1h" ? u(lang, "chart_window_1h") : t(lang, w === "24h" ? "chart_window_24h" : "chart_window_7d");

  const risk =
    detail != null
      ? weekendRiskScore(detail.dev_pct, detail.depth_usd, detail.redemption_status, detail.por_age_hours)
      : null;
  const marketOpen = marketIsOpen();

  return (
    <div className="wrap">
      <Header
        lang={lang}
        onLangChange={toggleLang}
        active="tickers"
        right={
          detail?.latest_ts ? (
            <span>
              {t(lang, "freshness", {
                time: fmtWITA(detail.latest_ts, lang),
                mins: Math.max(0, Math.round((Date.now() - Date.parse(detail.latest_ts)) / 60000)),
              })}
            </span>
          ) : undefined
        }
      />

      {loading && !detail && !notFound && <p className="hint">{t(lang, "loading_ticker")}</p>}
      {notFound && (
        <div className="errorbox" role="alert">
          {u(lang, "ticker_not_found")}{" "}
          <Link href="/ticker">{u(lang, "ticker_back_home")}</Link>
        </div>
      )}
      {error && !detail && (
        <div className="errorbox" role="alert">
          {u(lang, "load_error")}{" "}
          <button type="button" onClick={loadDetail}>
            {u(lang, "retry")}
          </button>
        </div>
      )}

      {detail && (
        <>
          <h1>
            {detail.ticker} ({detail.issuer})
          </h1>
          <p className="meta">
            {t(lang, "meta_underlying")}: {detail.underlying ?? "—"} ·{" "}
            {t(lang, "meta_legal")}: {detail.legal_type ?? "—"} · {t(lang, "meta_tier")}{" "}
            {detail.tier ?? "—"} · {t(lang, "meta_coverage")}: DEX Solana
          </p>
          <div className="cover">{t(lang, "coverage_short")}</div>

          <h2>{t(lang, "block_dev")}</h2>
          <div className="metrics">
            <div className="metric">
              <small>{t(lang, "dw_price")}</small>
              <div className="v">{fmtUsd(detail.dw_price)}</div>
            </div>
            <div className="metric">
              <small>{t(lang, "dev_median")}</small>
              <div className="v">
                {detail.dev_pct != null ? `${detail.dev_pct >= 0 ? "+" : ""}${detail.dev_pct.toFixed(3)}%` : "—"}
              </div>
              <div className="s">
                {detail.dev_bps != null ? `${fmtSigned1(detail.dev_bps)} bps` : ""}{" "}
                <span className={`pill ${detail.status}`}>{statusLabel(lang, detail.status)}</span>
              </div>
            </div>
            <div className="metric">
              <small>{t(lang, "dev_close")}</small>
              <div className="v">{t(lang, "close_pending_short")}</div>
            </div>
          </div>
          <p className="hint">{t(lang, "close_note")}</p>
          {detail.pools_excluded > 0 && (
            <p className="hint">{t(lang, "pools_excluded_note", { n: detail.pools_excluded })}</p>
          )}

          <h2>{t(lang, "chart_title")}</h2>
          <div className="controls">
            <span className="lbl">{t(lang, "chart_window")}:</span>
            <span className="seg" role="group" aria-label={t(lang, "chart_window")}>
              {(["1h", "24h", "7d"] as Window[]).map((w) => (
                <button
                  key={w}
                  type="button"
                  aria-pressed={window === w}
                  onClick={() => setWindow(w)}
                >
                  {windowLabel(w)}
                </button>
              ))}
            </span>
            <button type="button" className="refresh" onClick={refreshAll}>
              {t(lang, "refresh_button")}
            </button>
          </div>
          {histLoading ? (
            <p className="hint">{t(lang, "loading")}</p>
          ) : history.filter((p) => p.dev_bps != null).length >= 2 ? (
            <HistoryChart
              points={history}
              lang={lang}
              label={`${detail.ticker} ${t(lang, "chart_title")}`}
            />
          ) : (
            <p className="hint">{t(lang, "no_data")}</p>
          )}
          <p className="hint">{t(lang, "chart_note")}</p>

          <h2>{t(lang, "venue_title")}</h2>
          {detail.venues.length ? (
            <>
              <div className="tblwrap">
                <table>
                  <thead>
                    <tr>
                      <th>{t(lang, "col_dex")}</th>
                      <th>{t(lang, "col_chain")}</th>
                      <th>{t(lang, "col_price_usd")}</th>
                      <th>{t(lang, "col_reserve")}</th>
                      <th className="hide-s">{t(lang, "col_vol")}</th>
                      <th>{t(lang, "col_status")}</th>
                      <th className="hide-s">{t(lang, "col_updated")}</th>
                      <th>{t(lang, "dex_link_label")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.venues.map((v) => (
                      <tr key={`${v.dex}-${v.pair_address ?? v.ts ?? ""}`}>
                        <td>{v.dex}</td>
                        <td>{v.chain}</td>
                        <td className="num">{fmtUsd(v.price_usd)}</td>
                        <td className="num">{fmtUsd(v.reserve_usd)}</td>
                        <td className="num hide-s">{fmtUsd(v.volume_24h_usd)}</td>
                        <td>
                          {v.qualifies ? t(lang, "venue_status_ok") : t(lang, "venue_status_below")}
                        </td>
                        <td className="hide-s">{fmtWITA(v.ts, lang)}</td>
                        <td>
                          {v.pair_address ? (
                            <a
                              href={`https://dexscreener.com/solana/${v.pair_address}`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {t(lang, "dex_link_label")}
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="hint">{u(lang, "venues_note")}</p>
            </>
          ) : (
            <p className="hint">{t(lang, "no_data")}</p>
          )}

          {marketOpen ? (
            <>
              <h2>{t(lang, "market_title")}</h2>
              <p>{t(lang, "market_open")}</p>
              <div className="metrics">
                <div className="metric">
                  <small>{t(lang, "spread_label")}</small>
                  <div className="v">
                    {detail.spread_pct != null ? `${detail.spread_pct.toFixed(2)}%` : "—"}
                  </div>
                </div>
              </div>
              <p className="hint">{t(lang, "spread_note")}</p>
            </>
          ) : (
            <>
              <p className="hint">{t(lang, "market_closed_headline")}</p>
              <h2>{t(lang, "risk_title")}</h2>
              {detail.dev_pct == null && detail.depth_usd == null ? (
                <p className="hint">{t(lang, "risk_unavailable")}</p>
              ) : (
                risk && (
                  <>
                    <p>
                      <b>
                        {t(lang, "risk_total_100")}:{" "}
                        {risk.score_100 == null
                          ? "—"
                          : `${risk.score_100.toFixed(1)}${risk.partial ? ` (${risk.components_present}/4)` : ""}`}
                      </b>{" "}
                      ({u(lang, "risk_method_short")})
                    </p>
                    <p>
                      {t(lang, "risk_dev_label")}:{" "}
                      {risk.components.deviation != null ? risk.components.deviation.toFixed(1) : "—"} ·{" "}
                      {t(lang, "risk_depth_label")}:{" "}
                      {risk.components.depth != null ? risk.components.depth.toFixed(1) : "—"} ·{" "}
                      {t(lang, "risk_red_label")}:{" "}
                      {risk.components.redemption != null ? risk.components.redemption.toFixed(1) : "—"} ·{" "}
                      {t(lang, "risk_por_label")}:{" "}
                      {risk.components.por != null ? risk.components.por.toFixed(1) : "—"}
                    </p>
                    {risk.partial && (
                      <p className="hint">
                        {t(lang, "risk_partial_n", { n: risk.components_present })}
                      </p>
                    )}
                    <p className="hint">{t(lang, "risk_method")}</p>
                  </>
                )
              )}
            </>
          )}

          <h2>{t(lang, "redemption_title")}</h2>
          {detail.redemption_status != null ? (
            <>
              <p>
                <b>{t(lang, "col_status")}:</b> {redLabel(lang, detail.redemption_status)}{" "}
                <span className={`pill ${redPill(detail.redemption_status)}`}>
                  {redLabel(lang, detail.redemption_status)}
                </span>
              </p>
              {["open", "closed", "paused"].includes(detail.redemption_status) && (
                <p>{t(lang, "redemption_window_note")}</p>
              )}
              {(() => {
                const note = lang === "en" ? detail.redemption_note_en : detail.redemption_note;
                return note ? <p>{note}</p> : null;
              })()}
              {detail.redemption_status === "unknown" && <p>{t(lang, "redemption_doc_note")}</p>}
              <p>
                {t(lang, "obs_label")}: {fmtWITA(detail.redemption_observed_at, lang)}
              </p>
              {detail.redemption_source && (
                <p>
                  {t(lang, "source_label")}:{" "}
                  {lang === "en" && detail.redemption_source === KNOWN_ID_SOURCE
                    ? KNOWN_ID_SOURCE_EN
                    : detail.redemption_source}
                </p>
              )}
              {detail.redemption_next_open && (
                <p>
                  {t(lang, "next_open_label")}: {fmtWITA(detail.redemption_next_open, lang)}
                </p>
              )}
            </>
          ) : (
            <p>{t(lang, "redemption_unknown")}</p>
          )}

          <h2>{t(lang, "por_title")}</h2>
          {detail.por_age_hours != null || detail.por_last_update || detail.por_feed_address ? (
            <>
              {detail.por_age_hours != null && (
                <p>
                  {t(lang, "por_age_label")}: {detail.por_age_hours} h
                </p>
              )}
              {detail.por_last_update && (
                <p>
                  {t(lang, "por_last_label")}: {fmtWITA(detail.por_last_update, lang)}
                </p>
              )}
              {detail.por_feed_address && (
                <p>
                  {t(lang, "por_feed_label")}: {detail.por_feed_address}
                </p>
              )}
              {detail.por_note && <p>{detail.por_note}</p>}
            </>
          ) : (
            <p>{t(lang, "por_none")}</p>
          )}

          <h2>
            {t(lang, "col_change", { window: t(lang, "window_1h") })} ·{" "}
            {t(lang, "col_change", { window: t(lang, "window_24h") })} ·{" "}
            {t(lang, "col_change", { window: t(lang, "window_7d") })}
          </h2>
          <div className="metrics">
            <div className="metric">
              <small>{t(lang, "col_change", { window: t(lang, "window_1h") })}</small>
              <div className="v">{fmtSigned1(detail.change_1h_bps)}</div>
            </div>
            <div className="metric">
              <small>{t(lang, "col_change", { window: t(lang, "window_24h") })}</small>
              <div className="v">{fmtSigned1(detail.change_24h_bps)}</div>
            </div>
            <div className="metric">
              <small>{t(lang, "col_change", { window: t(lang, "window_7d") })}</small>
              <div className="v">{fmtSigned1(detail.change_7d_bps)}</div>
            </div>
            <div className="metric">
              <small>{t(lang, "col_spark")}</small>
              <div className="v spark">{sparkBlocks(detail.spark_bps)}</div>
              <div className="s">
                {t(lang, "col_depth10k")}: {fmtDepth(detail.depth_usd)} ·{" "}
                {t(lang, "col_spread")}: {fmtPct(detail.spread_pct)}
              </div>
            </div>
          </div>

          <div className="foot">
            {t(lang, "disclaimer")} {t(lang, "footer_note")}
            <br />
            <a href="https://www.linkedin.com/in/septian-panjaya">{t(lang, "linkedin_label")}</a>
          </div>
        </>
      )}
    </div>
  );
}
