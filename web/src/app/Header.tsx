"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { t, u, type Lang } from "../lib/i18n";

type Theme = "dark" | "light";

/* v2: theme state lives here (all pages render Header). Default dark;
   stored choice in localStorage; layout's inline script applies it
   before first paint so there is no flash. */
function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>("dark");
  useEffect(() => {
    try {
      const s = localStorage.getItem("exit-radar-theme");
      if (s === "light" || s === "dark") {
        setTheme(s);
        document.documentElement.setAttribute("data-theme", s);
      } else {
        document.documentElement.setAttribute("data-theme", "dark");
      }
    } catch {
      /* private mode: stay dark */
    }
  }, []);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem("exit-radar-theme", next);
    } catch {
      /* ignore */
    }
    document.documentElement.setAttribute("data-theme", next);
  };
  return [theme, toggle];
}

export default function Header({
  lang,
  onLangChange,
  active,
  right,
}: {
  lang: Lang;
  onLangChange: (l: Lang) => void;
  active: "home" | "tickers" | "methodology" | "waitlist" | "donate";
  right?: ReactNode;
}) {
  const [theme, toggleTheme] = useTheme();
  const item = (href: string, label: string, isActive: boolean) =>
    isActive ? (
      <span className="active" aria-current="page">
        {label}
      </span>
    ) : (
      <Link href={href}>{label}</Link>
    );
  return (
    <header>
      <div className="logo">
        <Link href="/" style={{ color: "inherit", textDecoration: "none" }}>
          EXIT <b>RADAR</b>
        </Link>
      </div>
      <nav className="navseg" aria-label="Primary">
        {item("/", t(lang, "nav_home"), active === "home")}
        {item("/ticker", t(lang, "nav_ticker"), active === "tickers")}
        {item("/methodology", t(lang, "nav_methodology"), active === "methodology")}
        {item("/waitlist", t(lang, "nav_waitlist"), active === "waitlist")}
        {item("/donate", u(lang, "nav_donate"), active === "donate")}
      </nav>
      <div className="live">
        <span className="dot" aria-hidden="true" />
        <span>{t(lang, "live_label")}</span>
        {right}
        <button
          type="button"
          className="iconbtn"
          onClick={toggleTheme}
          aria-label={
            theme === "dark" ? u(lang, "theme_to_light") : u(lang, "theme_to_dark")
          }
          title={theme === "dark" ? u(lang, "theme_to_light") : u(lang, "theme_to_dark")}
        >
          <svg className="icon-sun" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
          </svg>
          <svg className="icon-moon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        </button>
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
