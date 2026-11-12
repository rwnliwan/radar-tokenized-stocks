-- Migration 2026-11-12 (penambahan Radar, DESAIN_PENAMBAHAN_2026-11-12.md §3):
-- perp_snapshots (F1), liquidation_watch (F4), monday_gap (F2),
-- + exit_score / exit_score_version columns on deviations (F3).
-- Thresholds and formulas are PRE-REGISTERED in the design doc; this file
-- only creates the storage. Nothing here changes existing tables' rows.
--
-- APPLY ONLY WITH SEPTIAN ACC (do NOT run blindly). Order matters:
-- apply this migration to live Turso BEFORE deploying the poller that
-- writes these tables/columns — the new deviations INSERT references
-- exit_score, so a poller deployed first would fail every cycle.
--
-- Idempotency: CREATE TABLE / CREATE INDEX IF NOT EXISTS run cleanly
-- twice. The two ALTERs FAIL if the column already exists — check first:
--   SELECT name FROM pragma_table_info('deviations');
-- and run each ALTER only when its column is absent (same pattern as
-- migrations/2026-11-09-pools-excluded.sql).

-- F1 — Perp 3-leg snapshots: one row per ticker per 5-min cycle.
-- Only the 10 tickers with a live Hyperliquid XYZ perp (SPY/QQQ/GLD have
-- none — verified live 2026-11-12 — so they get NO rows, never a
-- fabricated price). funding / oi are NULL when the API does not
-- publish them; never fabricated.
CREATE TABLE IF NOT EXISTS perp_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  ts TEXT NOT NULL,
  perp_px REAL,
  funding REAL,
  oi REAL,
  dex TEXT NOT NULL DEFAULT 'xyz'
);
CREATE INDEX IF NOT EXISTS idx_perp_ticker_ts ON perp_snapshots(ticker_id, ts);

-- F4 — Liquidation Guard: one row per ticker per hour in normal
-- conditions; extra rows every 5 min only while warning/critical.
-- liq_px_estimate is ALWAYS NULL until a public liquidation-level source
-- is verified (§2.4) — never fabricated. distance_pct is NULL with it.
-- There is deliberately NO oracle_lag_s column: the public Hyperliquid
-- info endpoints publish no oracle timestamp, so lag is unmeasurable
-- from them (see poller.py run_hourly_liquidation).
CREATE TABLE IF NOT EXISTS liquidation_watch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  ts TEXT NOT NULL,
  oracle_px REAL,
  mark_px REAL,
  liq_px_estimate REAL,
  distance_pct REAL,
  source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_liqwatch_ticker_ts ON liquidation_watch(ticker_id, ts);

-- F2 — Monday Gap Predictor: ONE row per ticker per week (Saturday-anchored
-- week_start). outcome stays 'pending' until Monday's actual gap is
-- computed from indexed deviations reads — never guessed.
CREATE TABLE IF NOT EXISTS monday_gap (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  week_start TEXT NOT NULL,
  gap_pred_pct REAL NOT NULL,
  confidence REAL NOT NULL,
  method_version TEXT NOT NULL DEFAULT 'monday_gap_v1',
  outcome_gap_pct REAL,
  outcome TEXT,
  outcome_ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_monday_gap_ticker_week ON monday_gap(ticker_id, week_start);

-- F3 — Exit Score lives as COLUMNS on deviations (no new table, +0 writes:
-- the score rides the deviations row the cycle already writes).
-- Run ONLY if PRAGMA table_info(deviations) lacks the column.
ALTER TABLE deviations ADD COLUMN exit_score REAL;
ALTER TABLE deviations ADD COLUMN exit_score_version TEXT;
