-- Migration 2026-11-13 (fix ronde review DeepSeek Radar, 2026-11-13).
-- Findings fixed here (see review/REVIEW-DEEPSEEK-RADAR.md, all
-- verified by Chief): M5, M7, M8, S1, S2 — plus S9 follow-up (3 extra
-- indexes, added by the coordinator after qa/test_no_fullscan.py
-- proved 4 remaining scans on the schema above). Nothing here changes
-- any existing row; nothing is deleted.
--
-- NOCASE indexes: worker.js per-ticker queries use
-- `ticker_id = ? COLLATE NOCASE`, which cannot use a BINARY
-- (ticker_id, ts) index. The alternative (case normalization in
-- worker.js code) would change query semantics; the NOCASE index
-- keeps behavior identical. Trade-off: each extra index raises the
-- write multiplier (one more index maintained per inserted row) —
-- accepted: these are the hot read paths (every /api/ticker hit),
-- and the write volume is small (deviations ~15k rows/day,
-- perp_snapshots ~3.5k rows/day).
--
-- APPLY ONLY WITH SEPTIAN ACC (do NOT run blindly, do NOT run on
-- live Turso without ACC). Order: apply to live Turso BEFORE
-- deploying code that reads the new columns/indexes.
--
-- RE-RUNNABLE (S1): every statement below is safe to run twice.
-- - CREATE INDEX IF NOT EXISTS: SQLite skips it when the index
--   already exists.
-- - ALTER TABLE ... ADD COLUMN: SQLite has NO "ADD COLUMN IF NOT
--   EXISTS", so a bare re-run fails with "duplicate column name".
--   Do NOT feed this file raw to sqlite3 / Hrana twice. Apply it
--   ONLY through qa/apply_migration_2026-11-13.py, which checks
--   PRAGMA table_info(<table>) before each ALTER and skips columns
--   that already exist (same pattern as
--   migrations/2026-11-09-pools-excluded.sql and
--   migrations/2026-11-12-penambahan.sql, whose ALTERs were
--   PRAGMA-guarded by hand). The runner is the idempotent path;
--   this file is the canonical record of WHAT changes.
-- - N4 (monday_gap.outcome CHECK) is NOT in this file: SQLite
--   cannot ADD a CHECK constraint to an existing table via ALTER
--   TABLE (only a table rebuild can do that — NOT attempted on
--   live). The CHECK lives in schema.sql for fresh databases;
--   for the live DB, enforcement until a rebuild is the poller's
--   fixed value set ('pending' / 'accurate' / 'inaccurate',
--   poller.py _monday_gap_fill_outcomes) — documented, not silent.
--
-- Verify after applying (local sqlite copy):
--   python3 qa/test_radar_fix_schema.py   (runs this migration 2x,
--   checks columns + indexes + EXPLAIN QUERY PLAN)

-- M5 — deviations.exit_score_components: how many of the 5 exit-score
-- components were computable for this row (poller computes
-- components_present but never stored it; a partial 100.0 could not
-- be told apart from a full one). Written by the poller; NULL = the
-- score was not computed for this row.
ALTER TABLE deviations ADD COLUMN exit_score_components INTEGER;

-- S2 — perp_snapshots.perp_px_source: 'mark' | 'mid'. perp_px is
-- documented as the mark price, but the poller falls back to mid
-- when mark is unavailable; the fallback was unmarked per row.
-- Written by the poller; NULL = recorded before the column existed.
ALTER TABLE perp_snapshots ADD COLUMN perp_px_source TEXT;

-- M7 — index for the poller's per-cycle idempotency check
-- (COUNT(*) FROM poller_health WHERE cycle_ts = ?), which previously
-- full-scanned the table every cycle.
CREATE INDEX IF NOT EXISTS idx_poller_health_cycle_ts ON poller_health(cycle_ts);

-- M8 — index for ORDER BY ts DESC without WHERE (worker loadLatest,
-- dashboard), which previously scanned + sorted all deviations rows.
CREATE INDEX IF NOT EXISTS idx_deviations_ts ON deviations(ts);

-- S9 follow-up — worker.js:359 perp latest (ORDER BY ts DESC LIMIT 200)
-- scanned + sorted perp_snapshots (no ts index).
CREATE INDEX IF NOT EXISTS idx_perp_snapshots_ts ON perp_snapshots(ts);

-- S9 follow-up — worker.js per-ticker queries (:614, :680, :699) use
-- COLLATE NOCASE, which cannot use the BINARY (ticker_id, ts) indexes.
CREATE INDEX IF NOT EXISTS idx_deviations_ticker_nocase_ts ON deviations(ticker_id COLLATE NOCASE, ts);
CREATE INDEX IF NOT EXISTS idx_perp_ticker_nocase_ts ON perp_snapshots(ticker_id COLLATE NOCASE, ts);
