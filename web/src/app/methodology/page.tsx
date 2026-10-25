"use client";

import { useEffect, useState } from "react";
import Header from "../Header";
import { t, u, type Lang } from "../../lib/i18n";

// Sections group the 10 approved methodology paragraphs under headings so
// the page scans instead of reading as one wall of text. Paragraph wording
// is untouched; only the structure around it changed.
const SECTIONS: { heading: string; keys: string[] }[] = [
  { heading: "method_h_dev", keys: ["methodology_dev", "methodology_spread"] },
  { heading: "method_h_depth", keys: ["methodology_depth"] },
  { heading: "method_h_redemption", keys: ["methodology_redemption"] },
  { heading: "method_h_por", keys: ["methodology_por"] },
  { heading: "method_h_status", keys: ["methodology_thresholds"] },
  { heading: "method_h_sources", keys: ["methodology_sources"] },
  { heading: "method_h_limits", keys: ["methodology_limits"] },
  { heading: "method_h_human", keys: ["methodology_human"] },
  { heading: "method_h_coming", keys: ["methodology_coming"] },
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
      {SECTIONS.map((s) => (
        <section key={s.heading} className="method-section">
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
