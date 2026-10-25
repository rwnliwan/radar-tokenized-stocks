"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { t, u, type Lang } from "../lib/i18n";
import { fetchLatest } from "../lib/api";
import { fmtWITA } from "../lib/format";

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
  // Last-update text used to render inline here; its varying length made
  // the wrapping header row change height between pages and as the
  // relative minutes ticked up. It now lives behind a fixed-size "?"
  // button: the header row stays the same size, and the text appears
  // in an overlay that never moves layout. Closes on outside click / Escape.
  const [showFresh, setShowFresh] = useState(false);
  const freshRef = useRef<HTMLSpanElement>(null);
  /* "?" on EVERY page (2026-10-25): home and ticker detail pass `right`
     from their own data fetch; every other page gets its freshness here,
     from the same /api/latest timestamp, so no menu is left without it.
     On fetch failure the button simply stays hidden rather than showing
     a wrong time. */
  const [autoTs, setAutoTs] = useState<string | null>(null);
  useEffect(() => {
    if (right) return;
    let on = true;
    fetchLatest()
      .then((d) => {
        if (on) setAutoTs(d.meta.latest_ts);
      })
      .catch(() => {});
    return () => {
      on = false;
    };
  }, [right]);
  const autoFresh =
    autoTs != null
      ? (() => {
          const m = Math.round((Date.now() - Date.parse(autoTs)) / 60000);
          return m <= 0
            ? t(lang, "freshness_now", { time: fmtWITA(autoTs, lang) })
            : t(lang, "freshness", { time: fmtWITA(autoTs, lang), mins: m });
        })()
      : null;
  const freshContent = right ?? (autoFresh ? <span>{autoFresh}</span> : null);
  useEffect(() => {
    if (!showFresh) return;
    const onDoc = (e: MouseEvent) => {
      if (freshRef.current && !freshRef.current.contains(e.target as Node))
        setShowFresh(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowFresh(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [showFresh]);
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
        <Link
          href="/"
          style={{
            color: "inherit",
            textDecoration: "none",
            display: "inline-flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <svg width="30" height="30" viewBox="0 0 40 40" aria-hidden="true">
            <circle cx="20" cy="20" r="18" fill="none" stroke="#fbbf24" strokeWidth="2" />
            <circle cx="20" cy="20" r="11" fill="none" stroke="#fbbf24" strokeWidth="1" opacity=".55" />
            <circle cx="20" cy="20" r="4" fill="none" stroke="#fbbf24" strokeWidth="1" opacity=".55" />
            <path d="M20 20 L20 4 A16 16 0 0 1 31 9 Z" fill="#fbbf24" opacity=".45" />
            <circle cx="27" cy="14" r="2.6" fill="#fbbf24" />
            <circle cx="13" cy="26" r="2.2" fill="#4ade80" />
          </svg>
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
        {freshContent && (
          <span className="fresh-wrap" ref={freshRef}>
            <button
              type="button"
              className="iconbtn qbtn"
              onClick={() => setShowFresh((v) => !v)}
              aria-expanded={showFresh}
              aria-label={u(lang, "last_update_show")}
              title={u(lang, "last_update_show")}
            >
              ?
            </button>
            {showFresh && <span className="fresh-pop">{freshContent}</span>}
          </span>
        )}
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
