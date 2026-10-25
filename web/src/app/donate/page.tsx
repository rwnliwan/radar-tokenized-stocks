"use client";

import { useEffect, useState } from "react";
import Header from "../Header";
import { t, u, type Lang } from "../../lib/i18n";

/* Project donation wallet — the single source for the copy button and
   the QR code. Must match the address inside donate_note in lib/i18n.ts.
   USDC on Solana, static (no amount — the donor chooses). */
const ADDR = "6GvKCpEYqjzLQqu6WLedwWArhBi33CDRh4UPpPQa2qnv";
const PAY_URL = `solana:${ADDR}?label=EXIT%20RADAR`;

export default function DonatePage() {
  const [lang, setLang] = useState<Lang>("en");
  const [copied, setCopied] = useState(false);

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

  const copyAddr = async () => {
    try {
      await navigator.clipboard.writeText(ADDR);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable: the address stays selectable as text */
    }
  };

  return (
    <div className="wrap">
      <Header lang={lang} onLangChange={toggleLang} active="donate" />
      <h1>{t(lang, "donate_title")}</h1>
      <p>{t(lang, "donate_send")}</p>
      <div className="donate-addr">
        <span className="num">{ADDR}</span>
        <button type="button" className="refresh" onClick={copyAddr}>
          {copied ? u(lang, "copied_label") : u(lang, "copy_label")}
        </button>
      </div>
      <div className="qrbox">
        <img src="/donate-qr.png" alt={u(lang, "donate_qr_alt")} width={220} height={220} />
      </div>
      <p>
        <a href={PAY_URL}>{t(lang, "donate_pay_link")}</a>
      </p>
      <p>{t(lang, "donate_nofeatures")}</p>
      <p className="hint">{u(lang, "donate_verify")}</p>
      <hr />
      <div className="foot">
        {t(lang, "disclaimer")} {t(lang, "footer_note")}
        <br />
        <a href="https://www.linkedin.com/in/septian-panjaya">{t(lang, "linkedin_label")}</a>
      </div>
    </div>
  );
}
