"use client";

import { useEffect, useState } from "react";
import Header from "../Header";
import { t, type Lang } from "../../lib/i18n";

const METHOD_KEYS = [
  "methodology_dev",
  "methodology_spread",
  "methodology_depth",
  "methodology_por",
  "methodology_redemption",
  "methodology_thresholds",
  "methodology_sources",
  "methodology_limits",
  "methodology_human",
  "methodology_coming",
] as const;

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
    <div className="wrap">
      <Header lang={lang} onLangChange={toggleLang} active="methodology" />
      <h1>{t(lang, "methodology_title")}</h1>
      <p className="method-intro">{t(lang, "methodology_intro")}</p>
      {METHOD_KEYS.map((k) => (
        <div key={k}>
          <hr />
          <p className="method">{t(lang, k)}</p>
        </div>
      ))}
      <div className="foot">
        {t(lang, "disclaimer")} {t(lang, "footer_note")}
        <br />
        <a href="https://www.linkedin.com/in/septian-panjaya">{t(lang, "linkedin_label")}</a>
      </div>
    </div>
  );
}
