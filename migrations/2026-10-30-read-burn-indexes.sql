-- Migration 2026-10-30: read-burn fix (Turso 500M rows-read/month limit hit)
-- Context: Top Queries 2026-10-30 showed full-table scans burning ~85M rows/day:
--   1. pools JOIN snapshots with correlated MAX(ts) subquery -> 207.5K reads/run
--      (fixed by query rewrite in api/worker.js WITH latest ... GROUP BY pool_id;
--       this migration only adds the supporting indexes)
--   2. deviations ORDER BY ts DESC, id DESC LIMIT 500 -> 50.98K reads/run
--   3. deviations 1h sparkline WHERE ts >= ... -> 25.49K reads/run
--   4. poller_health COUNT(*) WHERE cycle_ts = ? -> 2.02K reads/run (full scan)
--   5. redemption_windows / por_feeds ORDER BY ... LIMIT n -> ~250 reads/run each
-- Run AFTER the Turso quota unblock (2026-11-01): reads are blocked until then,
-- and CREATE INDEX itself scans the table. Verify with EXPLAIN QUERY PLAN after.
-- Expected result: /api/latest origin hit drops from ~284K reads to ~2-3K reads.

CREATE INDEX IF NOT EXISTS idx_deviations_ts_id
  ON deviations(ts DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_poller_health_cycle_ts
  ON poller_health(cycle_ts);

CREATE INDEX IF NOT EXISTS idx_redemption_windows_issuer_obs
  ON redemption_windows(issuer, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_por_feeds_checked_at
  ON por_feeds(checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_por_feeds_issuer_checked
  ON por_feeds(issuer, checked_at DESC);
