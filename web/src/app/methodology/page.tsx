"use client";

import { useEffect, useState } from "react";
import Header from "../Header";
import { t, u, type Lang } from "../../lib/i18n";

// Sections group the 10 approved methodology paragraphs under headings so
// the page scans instead of reading as one wall of text. Paragraph wording
// is untouched; only the structure around it changed (package 1+2+3:
// jump-link index + threshold table + 30-second summary on top).
const SECTIONS: { id: string; heading: string; keys: string[] }[] = [
  { id: "dev", heading: "method_h_dev", keys: ["methodology_dev", "methodology_spread"] },
  { id: "depth", heading: "method_h_depth", keys: ["methodology_depth"] },
  { id: "redemption", heading: "method_h_redemption", keys: ["methodology_redemption"] },
  { id: "por", heading: "method_h_por", keys: ["methodology_por"] },
  { id: "status", heading: "method_h_status", keys: ["methodology_thresholds"] },
  { id: "sources", heading: "method_h_sources", keys: ["methodology_sources"] },
  { id: "limits", heading: "method_h_limits", keys: ["methodology_limits"] },
  { id: "human", heading: "method_h_human", keys: ["methodology_human"] },
  { id: "coming", heading: "method_h_coming", keys: ["methodology_coming"] },
];

// Threshold table rows: values copied from the approved paragraphs below
// (display thresholds, bot alert thresholds, depth/pool floors) — no new
// numbers introduced here.
const THRESH_ROWS: { label: string; value: string }[] = [
  { label: "thresh_watch", value: "thresh_watch_v" },
  { label: "thresh_alert", value: "thresh_alert_v" },
  { label: "thresh_devclose", value: "thresh_devclose_v" },
  { label: "thresh_spread", value: "thresh_spread_v" },
  { label: "thresh_redemption", value: "thresh_redemption_v" },
  { label: "thresh_por", value: "thresh_por_v" },
  { label: "thresh_depth", value: "thresh_depth_v" },
  { label: "thresh_pool", value: "thresh_pool_v" },
];

export default function MethodologyPage() {
  const [lang, setLang] = useState<Lang>("en");

  useEffect(() => {
    try {
      const s = localStorage.getItem("exit-radar-lang");
      if (s === "id" || s === "en") setLang(s);
    } catch {
      /* ignore */
    }
  }, []);

  const toggleLang = (l: Lang) => {
    setLang(l);
    try {
      localStorage.setItem("exit-radar-lang", l);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="wrap method-wrap">
      <Header lang={lang} onLangChange={toggleLang} active="methodology" />
      <h1>{t(lang, "methodology_title")}</h1>
      <p className="method-intro">{t(lang, "methodology_intro")}</p>
      <nav className="method-toc" aria-label={u(lang, "toc_label")}>
        <span className="toc-label">{u(lang, "toc_label")}:</span>
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`}>
            {u(lang, s.heading)}
          </a>
        ))}
      </nav>
      <div className="method-summary">
        <b>{u(lang, "summary_title")}</b>
        <p>{u(lang, "summary_text")}</p>
      </div>
      <h2 className="thresh-title">{u(lang, "thresh_title")}</h2>
      <div className="tblwrap">
        <table className="thresh">
          <thead>
            <tr>
              <th>{u(lang, "thresh_col_item")}</th>
              <th>{u(lang, "thresh_col_value")}</th>
            </tr>
          </thead>
          <tbody>
            {THRESH_ROWS.map((r) => (
              <tr key={r.label}>
                <td>{u(lang, r.label)}</td>
                <td className="num">{u(lang, r.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {SECTIONS.map((s) => (
        <section key={s.heading} id={s.id} className="method-section">
          <h2>{u(lang, s.heading)}</h2>
          {s.keys.map((k) => (
            <p key={k} className="method">
              {t(lang, k)}
            </p>
          ))}
        </section>
      ))}
      <hr />
      <div className="foot">
        {t(lang, "disclaimer")} {t(lang, "footer_note")}
        <br />
        <a href="https://www.linkedin.com/in/septian-panjaya">{t(lang, "linkedin_label")}</a>
      </div>
    </div>
  );
}
