"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Header from "../Header";
import { DevBar, StatusBlip } from "../BlipBar";
import { fetchLatest, type LatestResponse } from "../../lib/api";
import { fmtSigned1, fmtUsd, statusLabel } from "../../lib/format";
import { t, u, type Lang } from "../../lib/i18n";

export default function TickerIndex() {
  const [lang, setLang] = useState<Lang>("en");
  const [data, setData] = useState<LatestResponse | null>(null);
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

  return (
    <div className="wrap">
      <Header lang={lang} onLangChange={toggleLang} active="tickers" />
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
