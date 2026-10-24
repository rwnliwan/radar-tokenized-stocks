# Radar Tokenized Stocks

A public radar for **tokenized stocks**: price deviation versus the underlying
share and across venues, liquidity per venue, redemption-window status,
proof-of-reserve freshness, and exit-ability — in one place, for holders and
DeFi users who cannot simply "just avoid" weekend and off-hours exposure.

- **Bilingual:** English (default) + Bahasa Indonesia toggle.
- **Free forever, donation-supported.** No paywall on the dashboard or basic
  alerts. Monetization is parked until the system and its user base are ready.
- **Open code, gated dataset.** The code is open source (Apache-2.0); bulk
  dataset/API access stays gated until the project's data gates are met.

> Not financial advice. Prices are market data, not recommendations.

## Live status (honest, as of 24 October 2026)

- **Poller: live.** 5-minute polling, 24/7 — 13 xStocks tickers, 35 pools
  (Solana), snapshots + deviations + heartbeat written to Turso.
- **Dashboard: ready to deploy** (Streamlit app in `dashboard/`).
- **Telegram bot: waiting on its token** — the bot code is here (`bot.py`,
  dry-run and live-evaluation modes work without a token); live sending
  starts once the bot token is configured.
- **Deviation basis: cross-venue median only.** Deviation versus the equity
  close is intentionally `NULL` until a public-display data licence is
  secured — no licensed price is shown without one.
- **Redemption / proof-of-reserve automation: pending.** What is not yet
  observed from a verified automatic source is shown as unknown, never
  fabricated.

## Coverage

13 tickers verified live against the universe criteria (dominant issuer,
combined depth ≥ $500,000, ≥ 2 DEX venues, observed redemption, reference
price available): TSLAx, NVDAx, METAx, GOOGLx, MSTRx, SPYx, QQQx, CRCLx,
HOODx, COINx, GLDx (Tier 1) and AAPLx, MSFTx (Tier 2) — all xStocks on
Solana. Candidates that failed, with reasons, are listed in
`universe_excluded.md`.

## Repository layout

- `poller.py` — DexScreener polling → Turso (5-minute baseline, 1-minute
  tight window around US market open/close on weekdays, hourly
  redemption/PoR checks).
- `turso_client.py` — Hrana HTTP client for Turso.
- `schema.sql` — the 10 tables (universe, pools, snapshots, equity_refs,
  deviations, redemption_windows, por_feeds, alert_log, poller_health,
  waitlist).
- `seed_universe.py` — seeds the verified universe + pools.
- `dashboard/` — Streamlit dashboard (ticker pages, heatmap, waitlist form).
- `bot.py` — Telegram bot (alerts, language choice, donation info).

## Run it

```bash
# Dashboard
streamlit run dashboard/app.py

# Bot: dry-run (no sending), live evaluation (no sending), live
python bot.py --dry-run
python bot.py --evaluate-live
python bot.py --live
```

Configuration (Turso database URL + auth token, Telegram bot token) is kept
out of this repository. **Never commit tokens.**

## Licence

Apache-2.0 (see `LICENSE`).

## Author

Author's LinkedIn: https://www.linkedin.com/in/septian-panjaya
