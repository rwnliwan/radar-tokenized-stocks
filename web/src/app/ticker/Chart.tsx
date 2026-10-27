"use client";

import { useMemo, useState } from "react";
import { fmtSigned1, fmtWITA } from "../../lib/format";
import { u, type Lang } from "../../lib/i18n";
import type { HistoryPoint } from "../../lib/api";

const W = 640;
const H = 260;
const PL = 56;
const PR = 12;
const PT = 12;
const PB = 28;

/** Clean SVG line chart (no chart library): gaps stay gaps, never bridged.
 *  Segments break where the time gap exceeds 2.5x the median interval —
 *  the same honesty rule as the dashboard's "gaps are shown as gaps". */
export default function HistoryChart({
  points,
  lang,
  label,
  hourly,
}: {
  points: HistoryPoint[];
  lang: Lang;
  label: string;
  hourly?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);

  const model = useMemo(() => {
    const pts = points
      .filter((p) => p.dev_bps != null && !Number.isNaN(Date.parse(p.ts)))
      .map((p) => ({ t: Date.parse(p.ts), ts: p.ts, v: p.dev_bps as number }))
      .sort((a, b) => a.t - b.t);
    if (pts.length < 2) return null;
    const gaps: number[] = [];
    for (let i = 1; i < pts.length; i++) gaps.push(pts[i].t - pts[i - 1].t);
    const sorted = [...gaps].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)] || 0;
    const breakAt = median > 0 ? median * 2.5 : Infinity;
    const segments: typeof pts[] = [];
    let cur = [pts[0]];
    for (let i = 1; i < pts.length; i++) {
      if (pts[i].t - pts[i - 1].t > breakAt) {
        segments.push(cur);
        cur = [pts[i]];
      } else cur.push(pts[i]);
    }
    segments.push(cur);
    const vals = pts.map((p) => p.v);
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    const pad = (hi - lo) * 0.1 || 1;
    lo -= pad;
    hi += pad;
    const t0 = pts[0].t;
    const t1 = pts[pts.length - 1].t;
    const span = t1 - t0 || 1;
    const X = (t: number) => PL + ((t - t0) / span) * (W - PL - PR);
    const Y = (v: number) => PT + ((hi - v) / (hi - lo)) * (H - PT - PB);
    return { pts, segments, lo, hi, X, Y };
  }, [points]);

  if (!model) return null;
  const { pts, segments, lo, hi, X, Y } = model;
  const gridVals = [0, 1, 2, 3].map((i) => lo + ((hi - lo) * i) / 3);
  const fmtTime = (ts: string) => {
    const d = new Date(ts);
    return new Intl.DateTimeFormat(lang === "id" ? "id-ID" : "en-GB", {
      timeZone: "Asia/Makassar",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
  };
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bestD = Infinity;
    pts.forEach((p, i) => {
      const d = Math.abs(X(p.t) - x);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    setHover(best);
  };
  const hp = hover != null ? pts[hover] : null;

  return (
    <div className="hchart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={label}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {gridVals.map((v, i) => (
          <g key={i}>
            <line x1={PL} x2={W - PR} y1={Y(v)} y2={Y(v)} className="grid" />
            <text x={PL - 6} y={Y(v) + 4} className="ax" textAnchor="end">
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        {lo < 0 && hi > 0 && (
          <line x1={PL} x2={W - PR} y1={Y(0)} y2={Y(0)} className="zero" />
        )}
        {segments.map((seg, i) => (
          <polyline
            key={i}
            points={seg.map((p) => `${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join(" ")}
            className="line"
          />
        ))}
        {hp && (
          <g>
            <line x1={X(hp.t)} x2={X(hp.t)} y1={PT} y2={H - PB} className="hoverline" />
            <circle cx={X(hp.t)} cy={Y(hp.v)} r={4} className="hoverdot" />
          </g>
        )}
        <text x={PL} y={H - 6} className="ax">
          {fmtTime(pts[0].ts)}
        </text>
        <text x={W - PR} y={H - 6} className="ax" textAnchor="end">
          {fmtTime(pts[pts.length - 1].ts)}
        </text>
      </svg>
      <div className="hchart-tip" aria-live="off">
        {hp
          ? `${fmtWITA(hp.ts, lang)} · ${fmtSigned1(hp.v)} bps`
          : `${u(lang, hourly ? "chart_last_hourly" : "chart_last")} ${fmtSigned1(pts[pts.length - 1].v)} bps`}
      </div>
    </div>
  );
}
