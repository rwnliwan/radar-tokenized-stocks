"use client";

import { useEffect, useState } from "react";
import Header from "../Header";
import WaitlistForm from "../WaitlistForm";
import { t, u, type Lang } from "../../lib/i18n";

/* Waitlist as its own tab (moved off the homepage 2026-10-25: the old
   /#waitlist anchor sent every page back to the homepage). Same form and
   same backend list as before — only the location changed. */
export default function WaitlistPage() {
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
      <Header lang={lang} onLangChange={toggleLang} active="waitlist" />
      <h1>{t(lang, "waitlist_title")}</h1>
      <p>{t(lang, "waitlist_intro")}</p>
      <p className="hint">{u(lang, "waitlist_section_note")}</p>
      <WaitlistForm lang={lang} />
      <hr />
      <div className="foot">
        {t(lang, "disclaimer")} {t(lang, "footer_note")}
        <br />
        <a href="https://www.linkedin.com/in/septian-panjaya">{t(lang, "linkedin_label")}</a>
      </div>
    </div>
  );
}
