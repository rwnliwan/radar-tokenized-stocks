"use client";

/* Signature identity (ACC 2026-10-25): status blip + deviation range bar
   from mockup-desain-signature.html. All values come from props (live
   API data) — nothing is hardcoded. */

type StatusClass = "ok" | "watch" | "alert" | "na";

function statusClass(status: string): StatusClass {
  return status === "ok" || status === "watch" || status === "alert" ? status : "na";
}

/** Status-colored dot shown before a ticker. */
export function StatusBlip({ status }: { status: string }) {
  return <span className={`blip ${statusClass(status)}`} aria-hidden="true" />;
}

/** 64px deviation range bar: zero line center, ±100 bps scale, blip at
   the (capped) deviation. Renders nothing when deviation is null. */
export function DevBar({ devBps, status }: { devBps: number | null; status: string }) {
  if (devBps == null) return null;
  const capped = Math.max(-100, Math.min(100, devBps));
  const left = 50 + capped / 2;
  const cls = statusClass(status);
  return (
    <span className="blip-bar" aria-hidden="true">
      <i className={cls === "na" ? "ok" : cls} style={{ left: `${left}%` }} />
    </span>
  );
}

/** Small SVG trend sparkline from per-cycle deviation values (live API
   spark_bps). Geometry ported from mockup-desain-vnext.html: 72x22,
   min/max normalized, last-point dot, status-colored. Renders a dash
   when fewer than 2 points exist — never fabricates a trend. */
export function Sparkline({
  series,
  status,
}: {
  series: number[] | null | undefined;
  status: string;
}) {
  if (!series || series.length < 2)
    return (
      <span className="spark-empty" aria-hidden="true">
        —
      </span>
    );
  const w = 72;
  const h = 22;
  const lo = Math.min(...series);
  const hi = Math.max(...series);
  const span = hi - lo || 1;
  const pts = series
    .map(
      (v, i) =>
        `${((i / (series.length - 1)) * w).toFixed(1)},${(h - 3 - ((v - lo) / span) * (h - 6)).toFixed(1)}`,
    )
    .join(" ");
  const last = pts.split(" ").pop()!.split(",");
  const cls = statusClass(status);
  const color =
    cls === "alert"
      ? "var(--red)"
      : cls === "watch"
        ? "var(--orange)"
        : cls === "na"
          ? "var(--muted)"
          : "var(--green)";
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill={color} />
    </svg>
  );
}
