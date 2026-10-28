/* Server page for SSR homepage (ACC 28 Okt 2026): fetch the latest snapshot
   on the server so the first HTML already contains the table (no client
   fetch waterfall). Page cached 60s (same freshness as the /api/latest edge
   cache); client polling in HomeClient keeps open tabs fresh. On any fetch
   failure initialData is null and HomeClient falls back to its client fetch. */
import HomeClient from "./HomeClient";
import type { LatestResponse } from "../lib/api";

export const revalidate = 60;

async function getInitialData(): Promise<LatestResponse | null> {
  const base = process.env.NEXT_PUBLIC_RADAR_API_BASE;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/api/latest`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return (await res.json()) as LatestResponse;
  } catch {
    return null;
  }
}

export default async function Home() {
  const initialData = await getInitialData();
  return <HomeClient initialData={initialData} />;
}
