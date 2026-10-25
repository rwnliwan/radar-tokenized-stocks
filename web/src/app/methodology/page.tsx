"use client";

import { Fragment, useEffect, useState } from "react";
import Header from "../Header";
import { t, u, type Lang } from "../../lib/i18n";
import { fetchAlerts, type AlertRow } from "../../lib/api";
import { fmtWITA } from "../../lib/format";

// Sections group the 10 approved methodology paragraphs under headings so
// the page scans instead of reading as one wall of text. Paragraph wording
// is untouched; only the structure around it changed (package 1+2+3:
// jump-link index + threshold table + 30-second summary on top).
// List rendering below (limits/human/sources/coming/thresholds) only
// re-flows the SAME words into <ol>/<ul> items at render time: the i18n strings are
// not edited, so a future regen cannot silently revert the structure,
// and any parse mismatch falls back to the plain paragraph.

// Strip a sentence-final period when a sentence becomes a list item
// (list items carry no trailing period; the words themselves stay).
function stripFinalDot(s: string): string {
  return s.endsWith(".") ? s.slice(0, -1) : s;
}

function renderMethod(key: string, text: string, lang: Lang) {
  const plain = <p className="method">{text}</p>;
  if (key === "methodology_limits") {
    // "Limitations. (1) ... (2) ... (6) ..." -> lead line + numbered list.
    const parts = text.split(/(?=\(\d+\)\s)/);
    if (parts.length < 2) return plain;
    const lead = parts[0].trim();
    const items = parts
      .slice(1)
      .map((p) => stripFinalDot(p.replace(/^\(\d+\)\s*/, "").trim()));
    if (!lead || items.some((i) => !i)) return plain;
    return (
      <>
        <p className="method">{lead}</p>
        <ol className="method-list">
          {items.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ol>
      </>
    );
  }
  if (key === "methodology_human") {
    // "Intro. Human: A; B; C; D. Automated: e, f, g, h, and i. Trailing..."
    // -> intro + two labeled lists + trailing prose, all words kept.
    const humanLabel = lang === "id" ? "Manusia:" : "Human:";
    const autoLabel = lang === "id" ? "Otomatis:" : "Automated:";
    const hi = text.indexOf(humanLabel);
    const ai = text.indexOf(autoLabel);
    if (hi < 0 || ai < 0 || ai <= hi) return plain;
    const intro = text.slice(0, hi).trim();
    const humanPart = text.slice(hi + humanLabel.length, ai).trim();
    const rest = text.slice(ai + autoLabel.length);
    const dot = rest.indexOf(". ");
    if (dot < 0) return plain;
    const autoPart = rest.slice(0, dot);
    const trailing = rest.slice(dot + 1).trim();
    const humanItems = humanPart
      .split(";")
      .map((s) => stripFinalDot(s.trim()));
    const autoItems = autoPart.split(",").map((s) => s.trim());
    if (
      !intro ||
      humanItems.some((i) => !i) ||
      autoItems.some((i) => !i) ||
      !trailing
    )
      return plain;
    return (
      <>
        <p className="method">{intro}</p>
        <p className="method-label">{humanLabel}</p>
        <ul className="method-list">
          {humanItems.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
        <p className="method-label">{autoLabel}</p>
        <ul className="method-list">
          {autoItems.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
        <p className="method">{trailing}</p>
      </>
    );
  }
  if (key === "methodology_sources") {
    // Retention sentence "kept 30 days, then hourly for 12 months, then
    // daily" -> lead line + 3-item list; surrounding sentences stay prose.
    const lead = lang === "id" ? "Snapshot mentah disimpan" : "Raw snapshots are kept";
    const li = text.indexOf(lead);
    if (li < 0) return plain;
    const after = text.slice(li + lead.length);
    const dot = after.indexOf(". ");
    if (dot < 0) return plain;
    const items = after
      .slice(0, dot)
      .split(",")
      .map((s) => s.trim());
    const suffix = after.slice(dot + 1).trim();
    const prefix = text.slice(0, li).trim();
    if (items.some((i) => !i) || !suffix) return plain;
    return (
      <>
        {prefix && <p className="method">{prefix}</p>}
        <p className="method">{lead}:</p>
        <ul className="method-list">
          {items.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
        <p className="method">{suffix}</p>
      </>
    );
  }
  if (key === "methodology_coming") {
    // First sentence "Coming soon (...): A; B; C." -> lead + 3-item list;
    // the remaining sentences stay prose.
    const lead =
      lang === "id"
        ? "Segera hadir (belum terhubung):"
        : "Coming soon (not yet connected):";
    if (!text.startsWith(lead)) return plain;
    const rest = text.slice(lead.length).trim();
    const dot = rest.indexOf(". ");
    if (dot < 0) return plain;
    const items = rest
      .slice(0, dot)
      .split(";")
      .map((s) => s.trim());
    const remainder = rest.slice(dot + 1).trim();
    if (items.some((i) => !i) || !remainder) return plain;
    return (
      <>
        <p className="method">{lead}</p>
        <ul className="method-list">
          {items.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
        <p className="method">{remainder}</p>
      </>
    );
  }
  if (key === "methodology_thresholds") {
    // One dense paragraph, three rules -> three labeled lists, same words.
    // Sentences: [display rule, display note, bot triggers; priority,
    // weekend formula, experimental note]. Any parse mismatch -> plain.
    const parts = text.split(". ");
    if (parts.length !== 5) return plain;
    const labels =
      lang === "id"
        ? ["Kolom Status (tampilan saja)", "Alert bot (terpisah)", "Skor risiko akhir pekan"]
        : ["Status column (display-only)", "Bot alerts (separate)", "Weekend risk score"];
    const stripLead = (s: string, label: string) =>
      s.startsWith(label + ": ") ? s.slice(label.length + 2) : null;
    const d0 = stripLead(parts[0], labels[0]);
    const bot = stripLead(parts[2], labels[1])?.split("; ");
    const w0 = stripLead(parts[3], labels[2]);
    if (d0 == null || bot == null || bot.length !== 2 || w0 == null) return plain;
    const groups: [string, string[]][] = [
      [labels[0], [d0, parts[1]]],
      [labels[1], bot],
      [labels[2], [w0, stripFinalDot(parts[4])]],
    ];
    if (groups.some(([, items]) => items.some((i) => !i))) return plain;
    return (
      <>
        {groups.map(([label, items]) => (
          <Fragment key={label}>
            <p className="method-label">{label}</p>
            <ul className="method-list">
              {items.map((it, i) => (
                <li key={i}>{it}</li>
              ))}
            </ul>
          </Fragment>
        ))}
      </>
    );
  }
  return plain;
}
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
  { id: "alerts", heading: "method_h_alerts", keys: [] },
];

// Live alert history (ACC design): 30 latest rows from /api/alerts.
// Unknown recorded types render as-is (legacy batch rows); rows without a
// valid ticker page (e.g. the aggregate 'ALL' batch key) get no link.
// NOTE: DB tickers are mixed-case ('TSLAx'), so the check must allow a
// lowercase x — unlike the Worker's uppercased param check.
const TICKER_RE = /^[A-Z0-9]+x$/;

const HIST_TYPE_KEYS: Record<string, string> = {
  spread: "hist_type_spread",
  deviation_high: "hist_type_deviation",
  redemption: "hist_type_redemption",
  redemption_paused: "hist_type_redemption_paused",
  por: "hist_type_por",
};

function fmtFigure(v: number | null, lang: Lang): string {
  if (v == null) return "—";
  const locale = lang === "id" ? "id-ID" : "en-GB";
  return (
    new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      signDisplay: "exceptZero",
    }).format(v) + "%"
  );
}

function AlertHistory({ lang }: { lang: Lang }) {
  const [rows, setRows] = useState<AlertRow[] | null>(null);
  useEffect(() => {
    let live = true;
    fetchAlerts()
      .then((d) => {
        if (live) setRows(d.alerts);
      })
      .catch(() => {
        /* leave null: no misleading empty state on fetch failure */
      });
    return () => {
      live = false;
    };
  }, []);
  if (rows === null) return null;
  if (rows.length === 0) return <p className="method">{u(lang, "hist_empty")}</p>;
  return (
    <div className="tblwrap">
      <table className="thresh">
        <thead>
          <tr>
            <th>{u(lang, "hist_col_time")}</th>
            <th>{u(lang, "hist_col_ticker")}</th>
            <th>{u(lang, "hist_col_type")}</th>
            <th>{u(lang, "hist_col_figure")}</th>
            <th>{u(lang, "hist_col_detail")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const valid = TICKER_RE.test(r.ticker);
            const label = HIST_TYPE_KEYS[r.type];
            return (
              <tr key={`${r.ts}-${r.ticker}-${i}`}>
                <td>{fmtWITA(r.ts, lang)}</td>
                <td>{r.ticker}</td>
                <td>{label ? u(lang, label) : r.type}</td>
                <td>{fmtFigure(r.figure, lang)}</td>
                <td>
                  {valid ? (
                    <a href={`/ticker/${r.ticker}`}>{u(lang, "hist_col_detail")}</a>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

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
    <div className="wrap">
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
          {s.id === "alerts" ? (
            <AlertHistory lang={lang} />
          ) : (
            s.keys.map((k) => (
              <Fragment key={k}>{renderMethod(k, t(lang, k), lang)}</Fragment>
            ))
          )}
        </section>
      ))}
      <hr />
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
