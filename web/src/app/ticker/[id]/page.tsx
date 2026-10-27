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
  fmtSigned,
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

// PoR v2 numbers: API publishes them as strings; format locale-aware,
// falling back to the raw string when unparseable (never invent a value).
function fmtPorNum(v: string, digits: number, lang: Lang): string {
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return new Intl.NumberFormat(lang === "id" ? "id-ID" : "en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

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

          <h2 className="sec">{t(lang, "block_dev")}</h2>
          <div className="metrics metrics-3">
            <div className="metric">
              <small>{t(lang, "dw_price")}</small>
              <div className="v">{fmtUsd(detail.dw_price)}</div>
            </div>
            <div className="metric">
              <small>{t(lang, "dev_median")}</small>
              <div className="v">
                {detail.dev_pct != null ? `${fmtSigned(detail.dev_pct, 3)}%` : "—"}
              </div>
              <div className="s">
                {detail.dev_bps != null ? `${fmtSigned1(detail.dev_bps)} bps` : ""}{" "}
                <span className={`pill ${detail.status}`}>{statusLabel(lang, detail.status)}</span>
              </div>
              {detail.dev_pct == null && (
                <div className="s">{t(lang, "detail_no_median")}</div>
              )}
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

          <h2 className="sec">{t(lang, "chart_title")}</h2>
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
              hourly={window !== "1h"}
            />
          ) : (
            <p className="hint">{t(lang, "no_data")}</p>
          )}
          <p className="hint">{t(lang, "chart_note")}</p>

          <h2 className="sec">{t(lang, "venue_title")}</h2>
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
              <p className="hint tbl-note">{u(lang, "venues_note")}</p>
            </>
          ) : (
            <p className="hint">{t(lang, "no_data")}</p>
          )}

          {marketOpen ? (
            <>
              <h2 className="sec">{t(lang, "market_title")}</h2>
              <p>{t(lang, "market_open")}</p>
              <div className="metrics metrics-1">
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
              <h2 className="sec">{t(lang, "risk_title")}</h2>
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
                    {/* Signature: weekend score as a segmented bar (mockup).
                        Segment widths = component maxima; fill = value;
                        a full segment reads orange. Numbers stay in the
                        line below; formula stays behind the disclosure. */}
                    <div className="scorebar" aria-hidden="true">
                      {(
                        [
                          { key: "deviation", max: 40, label: t(lang, "risk_dev_label") },
                          { key: "depth", max: 25, label: t(lang, "risk_depth_label") },
                          { key: "redemption", max: 20, label: t(lang, "risk_red_label") },
                          { key: "por", max: 15, label: t(lang, "risk_por_label") },
                        ] as const
                      ).map(({ key, max, label }) => {
                        const v = risk.components[key];
                        const full = v != null && v >= max;
                        return (
                          <div
                            key={key}
                            className={`sseg${full ? " risk" : ""}`}
                            style={{ flex: max }}
                            title={`${label}: ${v != null ? v.toFixed(1) : "—"} / ${max}`}
                          >
                            <i style={{ width: v != null ? `${(v / max) * 100}%` : "0%" }} />
                          </div>
                        );
                      })}
                    </div>
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
                    <details className="risk-details">
                      <summary>{u(lang, "risk_method_toggle")}</summary>
                      <p className="hint">{t(lang, "risk_method")}</p>
                    </details>
                  </>
                )
              )}
            </>
          )}

          <h2 className="sec">{t(lang, "redemption_title")}</h2>
          {detail.redemption_status != null ? (
            <section className="redcard">
              <div className="redcard-head">
                <span className={`pill ${redPill(detail.redemption_status)}`}>
                  {redLabel(lang, detail.redemption_status)}
                </span>
                {detail.redemption_next_open && (
                  <span className="redcard-next">
                    {t(lang, "next_open_label")}: {fmtWITA(detail.redemption_next_open, lang)}
                  </span>
                )}
              </div>
              {detail.redemption_next_open && (
                <>
                  <div className="redcard-timeline" aria-hidden="true">
                    <span className="redcard-dot now" />
                    <span className="redcard-line" />
                    <span className="redcard-dot next" />
                  </div>
                  <div className="redcard-timeline-labels">
                    <span>{redLabel(lang, detail.redemption_status)}</span>
                    <span>{t(lang, "next_open_label")}</span>
                  </div>
                </>
              )}
              <div className="redcard-rows">
                <p>
                  <b>{t(lang, "obs_label")}:</b>{" "}
                  {fmtWITA(detail.redemption_observed_at, lang)}
                </p>
                {detail.redemption_source && (
                  <p>
                    <b>{t(lang, "source_label")}:</b>{" "}
                    {lang === "en" && detail.redemption_source === KNOWN_ID_SOURCE
                      ? KNOWN_ID_SOURCE_EN
                      : detail.redemption_source}
                  </p>
                )}
              </div>
              {["open", "closed", "paused"].includes(detail.redemption_status) && (
                <p className="small">{t(lang, "redemption_window_note")}</p>
              )}
              {(() => {
                const note = lang === "en" ? detail.redemption_note_en : detail.redemption_note;
                return note ? <p className="small">{note}</p> : null;
              })()}
              {detail.redemption_status === "unknown" && (
                <p className="small">{t(lang, "redemption_doc_note")}</p>
              )}
              <div className="redcard-por">
                <b>{t(lang, "por_title")}:</b>{" "}
                {detail.por_age_hours != null ? (
                  <>
                    {t(lang, "por_age_label")}: {detail.por_age_hours} h
                  </>
                ) : (
                  <>{t(lang, "por_none")}</>
                )}
                {detail.por_shares_held != null && detail.por_supply != null && (
                  <div>
                    {u(lang, "por_shares_label")}: {fmtPorNum(detail.por_shares_held, 0, lang)} ·{" "}
                    {u(lang, "por_supply_label")}: {fmtPorNum(detail.por_supply, 2, lang)}
                  </div>
                )}
              </div>
            </section>
          ) : (
            <p>{t(lang, "redemption_unknown")}</p>
          )}



          <h2 className="sec">{u(lang, "change_title")}</h2>
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

          <div className="foot-sweep" aria-hidden="true">
            <svg width="100%" height="14" viewBox="0 0 1180 14" preserveAspectRatio="none">
              <path
                d="M0 14 Q 590 -10 1180 14"
                fill="none"
                style={{ stroke: "var(--accent)" }}
                strokeWidth="1.5"
                opacity=".7"
              />
            </svg>
          </div>
          <div className="foot">
            {t(lang, "disclaimer")} {t(lang, "footer_note")}
            <br />
            <a href="https://www.linkedin.com/in/septian-panjaya">{t(lang, "linkedin_label")}</a>
            <br />
            Telegram: <a href="https://t.me/exitradar_en">EN</a> · <a href="https://t.me/exitradar_in">ID</a>
          </div>
        </>
      )}
    </div>
  );
}
