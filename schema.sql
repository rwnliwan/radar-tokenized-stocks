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
  redemption_status TEXT,
  por_age_hours REAL,
  weekend_risk_score REAL,
  method_version TEXT NOT NULL DEFAULT 'v1-median-only'
);
CREATE INDEX IF NOT EXISTS idx_deviations_ticker_ts ON deviations(ticker_id, ts);

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
  closed_below_threshold_ts TEXT
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
