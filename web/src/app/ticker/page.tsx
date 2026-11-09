"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Header from "../Header";
import { DevBar, StatusBlip } from "../BlipBar";
import { fetchHealth, fetchLatest, type HealthResponse, type LatestResponse } from "../../lib/api";
import { fmtSigned1, fmtUsd, fmtWITA, statusLabel } from "../../lib/format";
import { t, u, type Lang } from "../../lib/i18n";

export default function TickerIndex() {
  const [lang, setLang] = useState<Lang>("en");
  const [data, setData] = useState<LatestResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const s = localStorage.getItem("exit-radar-lang");
      if (s === "id" || s === "en") setLang(s);
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchLatest());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
    // Gap G5 (round 6): same /api/health freshness verdict as the
    // homepage (M4 contract). A failed health fetch must NOT keep a
    // previous verdict (S-new-6 pattern): clearing lets the meta /
    // snapshot-age fallback below speak.
    try {
      setHealth(await fetchHealth());
    } catch {
      setHealth(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleLang = (l: Lang) => {
    setLang(l);
    try {
      localStorage.setItem("exit-radar-lang", l);
    } catch {
      /* ignore */
    }
  };

  const rows = [...(data?.tickers ?? [])].sort((a, b) => a.ticker.localeCompare(b.ticker));

  // Gap G5: same stale verdict as the homepage — prefer the Worker's
  // /api/health verdict, then /api/latest meta, then snapshot age
  // (STALE_MIN = 15, same threshold as healthSummary / HomeClient).
  const latestTs = data?.meta.latest_ts ?? null;
  const ageMin =
    latestTs != null
      ? Math.round((Date.now() - Date.parse(latestTs)) / 60000)
      : null;
  const healthStale = health?.stale ?? data?.meta.stale ?? null;
  // GG-31 (fix ronde 9): a NEGATIVE age (future latest_ts) is stale,
  // never fresh — the old Math.max(0, ...) clamp hid it as "just now".
  const stale =
    healthStale != null ? healthStale : ageMin != null && (ageMin < 0 || ageMin > 15);
  const staleTime = health?.last_success_ts ?? latestTs;

  return (
    <div className="wrap">
      <Header lang={lang} onLangChange={toggleLang} active="tickers" />
      {stale && staleTime && (
        <div className="banner" role="status">
          {t(lang, "stale_banner", { time: fmtWITA(staleTime, lang) })}
        </div>
      )}
      {stale && !staleTime && (
        <div className="banner" role="status">
          {t(lang, "stale_banner_notime")}
        </div>
      )}
      <h2>{t(lang, "ticker_select")}</h2>
      {loading && !data && <p className="hint">{t(lang, "loading")}</p>}
      {error && (
        <div className="errorbox" role="alert">
          {u(lang, "load_error")}{" "}
          <button type="button" onClick={load}>
            {u(lang, "retry")}
          </button>
        </div>
      )}
      {data && (
        <div className="tblwrap tick-tbl">
          <table>
            <thead>
              <tr>
                <th>{t(lang, "col_ticker")}</th>
                <th>{t(lang, "col_tier")}</th>
                <th>{t(lang, "dw_price")}</th>
                <th>{t(lang, "col_dev_bps")}</th>
                <th>{t(lang, "col_status")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker}>
                  <td className="tk">
                    <StatusBlip status={r.status} />
                    <Link href={`/ticker/${r.ticker}`}>
                      <b>{r.ticker}</b>
                    </Link>
                  </td>
                  <td>{r.tier ?? "—"}</td>
                  <td className="num">{fmtUsd(r.dw_price)}</td>
                  <td className="num dev">
                    {fmtSigned1(r.dev_bps)}
                    <DevBar devBps={r.dev_bps} status={r.status} />
                  </td>
                  <td>
                    <span className={`pill ${r.status}`}>{statusLabel(lang, r.status)}</span>
                    {/* M1 (fix ronde 7): a ticker whose own deviations
                        row is stale is flagged per-row — the global
                        banner alone cannot say which ticker is old. */}
                    {r.stale && (
                      <span className="pill stale"> {t(lang, "ticker_stale")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="foot">
        {t(lang, "disclaimer")} {t(lang, "footer_note")}
        <br />
        <a href="https://www.linkedin.com/in/septian-panjaya">{t(lang, "linkedin_label")}</a>
        <br />
        Telegram: <a href="https://t.me/exitradar_en">EN</a> · <a href="https://t.me/exitradar_in">ID</a>
      </div>
    </div>
  );
}
