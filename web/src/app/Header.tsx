"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { t, type Lang } from "../lib/i18n";

export default function Header({
  lang,
  onLangChange,
  active,
  right,
}: {
  lang: Lang;
  onLangChange: (l: Lang) => void;
  active: "home" | "tickers" | "methodology";
  right?: ReactNode;
}) {
  const item = (href: string, label: string, isActive: boolean) =>
    isActive ? <b>{label}</b> : <Link href={href}>{label}</Link>;
  return (
    <header>
      <div className="logo">
        <Link href="/" style={{ color: "inherit", textDecoration: "none" }}>
          EXIT <b>RADAR</b>
        </Link>
      </div>
      <nav aria-label="Primary">
        {item("/", t(lang, "nav_home"), active === "home")}
        {item("/ticker", t(lang, "nav_ticker"), active === "tickers")}
        {item("/methodology", t(lang, "nav_methodology"), active === "methodology")}
        <a href="/#waitlist">{t(lang, "nav_waitlist")}</a>
      </nav>
      <div className="live">
        <span className="dot" aria-hidden="true" />
        <span>{t(lang, "live_label")}</span>
        {right}
        <span className="lang" role="group" aria-label={t(lang, "lang_label")}>
          <button type="button" aria-pressed={lang === "en"} onClick={() => onLangChange("en")}>
            EN
          </button>
          <button type="button" aria-pressed={lang === "id"} onClick={() => onLangChange("id")}>
            ID
          </button>
        </span>
      </div>
    </header>
  );
}
