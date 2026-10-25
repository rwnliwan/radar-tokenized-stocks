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
