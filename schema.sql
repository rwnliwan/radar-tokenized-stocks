-- Radar Tokenized Stocks — schema Tahap 1 (desain §2.1).
-- Semua waktu UTC (ISO 8601). Diterapkan via Hrana /v2/pipeline.
-- Catatan: snapshots_hourly / snapshots_daily dibuat oleh job agregasi
-- mingguan (retensi §2.2), bukan bagian skema awal ini.

CREATE TABLE IF NOT EXISTS universe (
  ticker_id TEXT PRIMARY KEY,
  underlying TEXT NOT NULL,
  issuer TEXT NOT NULL,
  legal_type TEXT,
  tier INTEGER NOT NULL,
  status TEXT NOT NULL,
  token_addresses TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pools (
  pool_id TEXT PRIMARY KEY,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  chain TEXT NOT NULL,
  dex TEXT NOT NULL,
  pair_address TEXT NOT NULL,
  quote_token TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  min_liquidity_usd REAL NOT NULL DEFAULT 100000
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pool_id TEXT NOT NULL REFERENCES pools(pool_id),
  ts TEXT NOT NULL,
  price_usd REAL,
  reserve_usd REAL,
  reserve_token REAL,
  reserve_quote REAL,
  volume_24h_usd REAL,
  source TEXT NOT NULL,
  raw_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_pool_ts ON snapshots(pool_id, ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);

CREATE TABLE IF NOT EXISTS equity_refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  underlying TEXT NOT NULL,
  ts TEXT NOT NULL,
  ref_type TEXT NOT NULL,
  price_usd REAL,
  source TEXT,
  corporate_action_note TEXT
);

CREATE TABLE IF NOT EXISTS deviations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  ts TEXT NOT NULL,
  depth_weighted_price REAL,
  dev_vs_close_pct REAL,
  dev_vs_median_pct REAL,
  qualifying_depth_usd REAL,
  pools_used INTEGER,
  pools_excluded INTEGER NOT NULL DEFAULT 0, -- written by the poller price-guard since 2026-10-24; declared here in fix ronde 9 (P1-4) after live PRAGMA verification 2026-11-09 (cid 12, INTEGER NOT NULL DEFAULT 0 — the live DB already had it via an undocumented ALTER; see migrations/2026-11-09-pools-excluded.sql)
  redemption_status TEXT,
  por_age_hours REAL,
  weekend_risk_score REAL,
  -- F3 (penambahan 2026-11-12, DESAIN §2.3/§3.3): exit_score_v1, written
  -- by the poller with the deviations row (+0 writes). NULL when no
  -- component could be computed. Live ALTER via
  -- migrations/2026-11-12-penambahan.sql (check PRAGMA first).
  exit_score REAL,
  exit_score_version TEXT,
  method_version TEXT NOT NULL DEFAULT 'v1-median-only'
);
CREATE INDEX IF NOT EXISTS idx_deviations_ticker_ts ON deviations(ticker_id, ts);

-- F1 (penambahan 2026-11-12, DESAIN §3.1): Hyperliquid XYZ perp snapshots,
-- one row per ticker per 5-min cycle. Only the 10 tickers with a live XYZ
-- perp (SPY/QQQ/GLD: no rows, never fabricated). funding/oi NULL when
-- the API does not publish them.
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

-- F4 (penambahan 2026-11-12, DESAIN §3.2): Liquidation Guard, one row per
-- ticker per hour (extra 5-min rows only while warning/critical).
-- liq_px_estimate ALWAYS NULL until a public liquidation-level source is
-- verified — never fabricated. No oracle_lag_s column: the public info
-- endpoints publish no oracle timestamp, so lag is unmeasurable.
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

-- F2 (penambahan 2026-11-12, DESAIN §3.4): Monday Gap Predictor, ONE row
-- per ticker per week (week_start = Saturday). outcome stays 'pending'
-- until Monday's actual gap is computed — never guessed.
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

CREATE TABLE IF NOT EXISTS redemption_windows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issuer TEXT NOT NULL,
  asset TEXT NOT NULL,
  status TEXT NOT NULL,
  window_note TEXT,
  window_note_en TEXT, -- EN twin of window_note (added 2026-10-25; live ALTER, backfilled row id=1)
  observed_at TEXT NOT NULL,
  source TEXT,
  next_open_at TEXT
);

CREATE TABLE IF NOT EXISTS por_feeds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issuer TEXT NOT NULL,
  feed_address TEXT,
  last_update_ts TEXT,
  age_hours REAL,
  reserves_vs_supply_note TEXT,
  checked_at TEXT NOT NULL
);

-- PoR v2 (ACC'd): per-token snapshots from the same hourly API responses
-- that feed por_feeds. Numbers stored as TEXT exactly as the API
-- publishes them (no float rounding); holdings kept for audit only.
CREATE TABLE IF NOT EXISTS por_token_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  shares_held TEXT,
  circulating_supply TEXT,
  holdings_json TEXT,
  checked_at TEXT NOT NULL
);

-- NOTE (Wave 3, 2026-10-25): alert_log.ticker_id deliberately has NO
-- REFERENCES universe(ticker_id). The log legitimately records aggregate
-- keys such as 'ALL' for batched alerts, which are not universe rows;
-- the FK made every batch record fail (first live batch, 2026-10-25).
-- pools/deviations keep their FK: they only ever carry real tickers.
CREATE TABLE IF NOT EXISTS alert_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL,
  alert_ts TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  threshold_pct REAL,
  dev_at_alert_pct REAL,
  depth_at_alert_usd REAL,
  message_text TEXT,
  outcome TEXT,
  outcome_ts TEXT,
  closed_below_threshold_ts TEXT,
  -- channel ('en'/'id', fix ronde 6 S-new-10, 2026-11-08): one row per
  -- (alert, channel) delivery, so a failed channel is not suppressed
  -- by another channel's success. NULL = recorded before the column
  -- existed; dedup counts NULL rows as suppressing every channel.
  channel TEXT
);

CREATE TABLE IF NOT EXISTS poller_health (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_ts TEXT NOT NULL,
  cycles_expected INTEGER NOT NULL,
  cycles_ok INTEGER NOT NULL,
  failed_sources TEXT,
  gap_note TEXT
);

CREATE TABLE IF NOT EXISTS waitlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact TEXT,
  position_size_usd TEXT,
  venues TEXT,
  willing_price TEXT,
  created_at TEXT NOT NULL,
  consent INTEGER NOT NULL DEFAULT 0
);
