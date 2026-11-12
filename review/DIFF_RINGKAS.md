# Ringkasan Diff — Penambahan Radar 12 Nov 2026

Diukur 12 Nov 2026 ±21:00 WITA. Repo `~/workspace/radar-tokenized-stocks`,
HEAD `b902323` ("Radar fix ronde 9…"). Semua perubahan di bawah ini
**belum di-commit** (working tree). Tidak ada deploy yang jalan dari
perubahan ini.

---

## 1. `git diff --stat` (verbatim)

```
 api/worker.js                    | 291 ++++++++++++-
 dashboard/app.py                 | 194 ++++++++-
 dashboard/i18n.py                | 102 +++++
 dashboard/logic.py               | 157 +++++++
 dashboard/risk.py                |  23 ++
 dashboard/turso_read.py          |  99 +++++
 poller.py                        | 862 ++++++++++++++++++++++++++++++++++++++-
 schema.sql                       |  54 +++
 web/src/app/HomeClient.tsx       | 133 +++++-
 web/src/app/methodology/page.tsx |   2 +
 web/src/app/ticker/[id]/page.tsx | 125 +++++-
 web/src/lib/api.ts               |  65 +++++
 web/src/lib/csv.ts               |   2 +
 web/src/lib/i18n.ts              |  92 +++++
 web/src/lib/risk.ts              |  13 ++++
 15 files changed, 2180 insertions(+), 34 deletions(-)
```

## 2. `git status --short` (verbatim, diringkas)

**Modified (15 file, sama seperti §1):** `api/worker.js`,
`dashboard/app.py`, `dashboard/i18n.py`, `dashboard/logic.py`,
`dashboard/risk.py`, `dashboard/turso_read.py`, `poller.py`,
`schema.sql`, `web/src/app/HomeClient.tsx`,
`web/src/app/methodology/page.tsx`,
`web/src/app/ticker/[id]/page.tsx`, `web/src/lib/api.ts`,
`web/src/lib/csv.ts`, `web/src/lib/i18n.ts`, `web/src/lib/risk.ts`.

**Untracked baru (terkait penambahan ini):**
- `migrations/2026-11-12-penambahan.sql` — migrasi (§3.1–§3.4 desain)
- `seed_multichain.py` — seed multichain (dry-run default; `--live`
  hanya dengan `RADAR_SEED_CONFIRM=ACC-2026-11-12`)
- `verify_multichain.py` — verifikasi ulang live per ticker
  (**ada di disk, tapi git-ignored** oleh pola `verify_*.py` di
  `.gitignore:12` — sengaja tidak di-commit; reviewer baca dari disk)
- `check_elysium_weekly.py` — cek mingguan Elysium + Hyperliquid spot
  (read-only, exit 0 bila cek berjalan, 2 bila ambil data gagal)
- `qa/test_coverage_2026-11-12.mjs` — tes route `/api/coverage` +
  guard anti full-scan
- Dokumen: `DESAIN_PENAMBAHAN_2026-11-12.md`,
  `BACKTEST_ALERT_2026-11-12.md`, `VERIFIKASI_MULTICHAIN_2026-11-12.md`,
  `KUOTA_PENAMBAHAN_2026-11-12.md`, `SEED_MULTICHAIN_2026-11-12.md`
  (juga `RADAR-X-HYPERLIQUID-2026-11-12.md` — catatan video TikTok,
  bukan bagian penambahan ini)

**Tidak terkait / abaikan:** `.bot_alert.lock` (file lock runtime).

---

## 3. Ringkasan perubahan per file

### 3.1 `poller.py` (+862) — INTI F1–F4
- Baru: `HL_INFO_URL`, `XYZ_PERP` (10 market `xyz:*`), `fetch_xyz_ctxs()`,
  `fetch_xyz_mids()`, `fetch_xyz_market_data()` — baca Hyperliquid info API
  (`allMids`/`metaAndAssetCtxs` dex xyz), read-only, via `hl_post()`.
- Baru: `exit_score_v1()` + `_exit_redemption_component()` — rumus §2.3
  desain (5 komponen, normalisasi parsial, versi `'exit_score_v1'`);
  `monday_gap_predict()` — rumus §2.2 (gap + confidence + label);
  `liquidation_status()` — status ok/warning/critical §2.4.
- Baru: `run_cycle_perp()` (5 menit, tulis `perp_snapshots`; gagal baca →
  catat di `poller_health`, tidak menggagalkan siklus spot),
  `run_hourly_liquidation()` (per jam; tambahan per 5 menit hanya saat
  warning/kritis), `run_weekly_monday_gap()` + `_monday_gap_predict()` +
  `_monday_gap_fill_outcomes()` (1 baris/ticker/minggu; isi outcome Senin
  pagi), `refresh_median_depth_7d()` (median depth 7 hari untuk komponen
  depth Exit Score), `_latest_perp_by_ticker()`, `_oi_24h_ago()`,
  `_latest_deviations_row()`, `_sunday_spread_pct()`.
- `run_cycle()` — hitung Exit Score per ticker dan sertakan `exit_score` +
  `exit_score_version` dalam INSERT `deviations` yang sudah ada (14 kolom).
- **Tidak ada** dukungan chain baru di diff ini: tidak ada
  Base/BNB/Coinbase/bStocks/Robinhood dalam perubahan `poller.py`
  (grep hanya menemukan `oi_base`/`baseline` yang tidak terkait).
  `XSTOCKS_MINTS` masih Solana-only — lihat penyimpangan D5 di §4.

### 3.2 `schema.sql` (+54) — skema §3 desain
- `deviations` + kolom `exit_score REAL`, `exit_score_version TEXT`.
- Tabel baru `perp_snapshots`, `liquidation_watch`, `monday_gap`
  (masing-masing + indeks `(ticker_id, ts)` / `(ticker_id, week_start)`),
  persis seperti desain §3.1–§3.4.

### 3.3 `migrations/2026-11-12-penambahan.sql` (baru)
- Satu file migrasi idempotent (klaim): `CREATE TABLE/INDEX IF NOT EXISTS`
  untuk ketiga tabel; dua `ALTER TABLE deviations ADD COLUMN` yang
  **GAGAL bila kolom sudah ada** — header file memerintahkan cek
  `PRAGMA table_info(deviations)` dulu (pola migrasi 2026-11-09).
- Header menegaskan urutan: **migrasi dulu, baru poller** — INSERT
  `deviations` baru merujuk `exit_score`, jadi poller yang deploy duluan
  akan gagal tiap siklus.
- **Penyimpangan dari desain (§4 D1):** TIDAK ada kolom `oracle_lag_s`
  di `liquidation_watch` — komentar file: endpoint info publik
  Hyperliquid tidak menerbitkan timestamp oracle, jadi lag tidak bisa
  diukur. `liq_px_estimate`/`distance_pct` selalu NULL sampai sumber
  level likuidasi terverifikasi.

### 3.4 `seed_multichain.py` (baru, untracked)
- Baca `verify_multichain_out.json`, terapkan tier + cap 13/issuer +
  saringan pool trackable, cetak SQL (`--dry-run`, default) atau eksekusi
  (`--live`, hanya dengan `RADAR_SEED_CONFIRM=ACC-2026-11-12`).
- Opsi `--max-pools-per-ticker N` (varian hemat: N=3 → 71 pool).
- Ikut menulis baris dokumentasi `redemption_windows` + `por_feeds`
  (status `unknown`) per issuer baru.
- Dry-run terverifikasi: **30 ticker, 115 pool, 151 INSERT + 63 DELETE**;
  `--live` tanpa ACC ditolak (exit 2); read-back Turso: 0 baris baru
  untuk issuer coinbase/bstocks/robinhood.

### 3.5 `verify_multichain.py` (baru, git-ignored — baca dari disk)
- Verifikasi ulang live per ticker (search + token-pairs **base-side
  saja**, petunjuk issuer, override alamat, flag `truncated`).
- Tiga perbaikan metode vs ronde pertama (lihat
  `SEED_MULTICHAIN_2026-11-12.md` §5): (1) token-pairs menghitung pair
  quote-side — diperbaiki ke base-side saja; (2) impostor mengalahkan
  token asli bila hanya pakai likuiditas terbesar — diperbaiki dengan
  petunjuk issuer; (3) search tidak andal untuk simbol pendek — diperbaiki
  dengan `KNOWN_ADDRESSES` + guard `isinstance`.
- Read-only, tanpa kredensial; aman dijalankan mingguan.

### 3.6 `check_elysium_weekly.py` (baru, untracked)
- Cek mingguan read-only: 13 simbol xStocks di Elysium (DexScreener) +
  cross-check token-pairs TSLAx EVM + book spot Hyperliquid @702/@703/
  @712/@713. Vonis: `belum aktif` / `aktif — lolos aturan` /
  `aktif — belum lolos` (pair $0 tidak dihitung aktif).
- Uji coba 12 Nov 12:29 UTC, exit 0: **belum aktif** (1 pair GOOGLx,
  liq $0; TSLAX/AAPLX tanpa ask).
- Proposal cron Minggu 09:46 WITA **BELUM dibuat — butuh ACC Septian**.

### 3.7 `dashboard/risk.py` (+23)
- Hanya `exit_score_band(score)` — memetakan skor TERSIMPAN ke band
  low (< 40) / medium (40–69) / high (≥ 70); `None` atau di luar 0–100
  → `None` (skor hilang tidak pernah ditampilkan sebagai 0).
- **Bukan** implementasi rumus: `exit_score_v1`, `monday_gap_predict`,
  `liquidation_status` hidup di `poller.py` (§3.1), bukan di `risk.py`
  seperti yang ditulis desain §4.3. Lihat pertanyaan Q3 di
  `PERTANYAAN_TERBUKA.md` (mana yang kanonis).

### 3.8 `dashboard/logic.py` (+157) + `dashboard/turso_read.py` (+99)
- `logic.py`: `get_coverage()`, `build_coverage(pool_rows)`,
  `get_exit_scores()`, `get_perp(ticker)`, `coverage_short_line()`,
  `render_coverage()`, `display_chain()`, `display_issuer()`.
  `PENDING_COVERAGE` — 6 vonis bertanggal 12 Nov 2026
  (base/bnb/robinhood `verified`; ethereum `failed`; elysium
  `not_active`; hyperliquid `monitor`).
- `turso_read.py`: `get_coverage_pools()`, `get_latest_exit_scores()`,
  `get_perp_latest(ticker)` — semua latest-only via indeks +
  `ORDER BY ts DESC LIMIT 1`; helper `_pragma_table_info()` /
  `_table_exists()` agar dashboard tetap jalan sebelum migrasi
  (kolom/tabel yang belum ada dibaca sebagai null, bukan error).

### 3.9 `dashboard/app.py` (+194) + `dashboard/i18n.py` (+102)
- Panel baru per ticker: Exit Score (angka + komponen + versi +
  "berapa komponen tersedia"), Perp 3-leg, Monday Gap Predictor,
  Liquidation Guard; kolom Exit Score di peta panas; pernyataan cakupan
  diperluas ke chain × issuer × DEX + daftar "belum tercakup" beserta
  alasan; string ID/EN baru di `i18n.py`.

### 3.10 `api/worker.js` (+291)
- **Route baru `/api/coverage`** — grup live diturunkan dari baris pools
  (Solana-only hari ini: 13 ticker, 35 pool, `only_solana_xstocks: true`);
  pending list = 6 vonis bertanggal; banner tidak pernah di-hardcode.
- **`/api/latest` diperluas (backward-compatible, kolom nullable):**
  `exit_score`, `exit_score_version`, `perp_dev_pct`, `perp_px` —
  statement perp hanya ditambahkan bila tabel `perp_snapshots` ada
  (probe `sqlite_master` + probe kolom `PRAGMA` terpisah agar DB tanpa
  migrasi tetap berbentuk 8-statement yang sama). Null = "belum tersedia",
  bukan 0.
- **Penyimpangan dari desain (§4 D2):** route terpisah `/api/perp`,
  `/api/exit-score`, `/api/monday-gap` dan parameter
  `series=perp|exit_score` di `/api/history` **tidak ada di diff ini**.
  `/api/health` + `/api/alerts` tidak berubah.

### 3.11 `web/` (+433 total)
- `web/src/lib/api.ts` (+65) — fetcher baru (mengikuti pola fetcher
  yang sudah ada); `web/src/lib/risk.ts` (+13) — format Exit Score /
  Monday Gap / Liquidation Guard; `web/src/lib/i18n.ts` (+92) —
  string ID/EN label baru; `web/src/lib/csv.ts` (+2).
- `web/src/app/ticker/[id]/page.tsx` (+125) + `web/src/app/HomeClient.tsx`
  (+133) — panel baru yang sama seperti §3.9 + kolom Exit Score di
  daftar ticker + lencana chain/issuer/DEX per ticker.
- `web/src/app/methodology/page.tsx` (+2) — hanya 2 baris: entri seksi
  `exit_score` + `perp` di daftar `SECTIONS`; **teks metodologi
  sebenarnya hidup di string i18n** (`web/src/lib/i18n.ts`), bukan di
  file ini. Reviewer harus menilai isi metodologi dari i18n, bukan dari
  page.tsx. Belum ada seksi metodologi `monday_gap_v1` / `liq_guard_v1`
  di daftar `SECTIONS` — lihat pertanyaan Q11.

### 3.12 `qa/test_coverage_2026-11-12.mjs` (baru)
- Tes route `/api/coverage` dengan `api/worker.js` dijalankan sungguhan
  (dynamic import atas salinan .mjs) + fetch stub canned Hrana; tanpa
  network/token/Turso. Mencakup: 1 grup live Solana-only, flip grup
  saat Base di-seed, pending list cocok dengan `PENDING_COVERAGE`
  `logic.py` (anti-drift), guard anti full-scan (tidak ada `SELECT *` /
  `COUNT(*)` atas tabel besar di statement baru).
- Hasil saat paket disusun: **15 PASS, 0 FAIL** (lihat `HASIL_TEST.md`).

---

## 4. Penyimpangan dari desain yang SUDAH terlihat (untuk DeepSeek)

Ini bukan vonis — ini daftar yang harus diperiksa reviewer, karena
Chief hanya menerima temuan yang terverifikasi:

| # | Penyimpangan | Desain yang dirujuk | Bukti di diff |
|---|---|---|---|
| D1 | `oracle_lag_s` TIDAK ada di skema — ambang lag 120/600 dtk (§2.4) tidak bisa ditegakkan dari endpoint publik | §2.4, §3.2 | `migrations/2026-11-12-penambahan.sql` (komentar eksplisit) + `liquidation_status(..., oracle_lag_s=None)` di `poller.py` |
| D2 | Tidak ada route `/api/perp`, `/api/exit-score`, `/api/monday-gap`; tidak ada `series=` di `/api/history`. Sebagai gantinya: `/api/coverage` baru + `/api/latest` diperluas | §4.4 | `git diff -- api/worker.js` (hanya route `/api/coverage` yang baru) |
| D3 | Rumus murni (`exit_score_v1`, `monday_gap_predict`, `liquidation_status`) hidup di `poller.py`, bukan di `dashboard/risk.py` (yang hanya punya `exit_score_band`) | §4.3 | `git diff -- dashboard/risk.py` (+23, hanya band) vs `poller.py` (+862) |
| D4 | **`bot.py` TIDAK BERUBAH SAMA SEKALI** — tidak ada `perp_deviation` / `exit_high` di `evaluate_alerts()`, tidak ada `format_alert()` baru, tidak ada gabungan `perp_snapshots` di `load_live_tickers()`. Alert F1/F3 tampaknya belum dibangun | §4.2 | `git diff --stat` (bot.py tidak ada) — dikonfirmasi `git diff --stat -- bot.py` kosong |
| D5 | **Poller masih Solana-only** — tidak ada alamat Base/BNB/Robinhood, tidak ada batch per chain. Seed saja tidak memulai polling | §3.5, §4.1 | grep diff `poller.py` untuk base/bnb/coinbase/bstocks/robinhood: nihil |
| D6 | Metodologi web: `methodology/page.tsx` hanya +2 baris (entri seksi); isi metodologi di string i18n; tidak ada seksi `monday_gap_v1` / `liq_guard_v1` di `SECTIONS` | §4.5 | `git diff -- web/src/app/methodology/page.tsx` |
| D7 | Guard QA baru §5.4 (8 butir) sebagian besar belum terlihat: hanya guard anti full-scan yang terliput (`qa/test_coverage_2026-11-12.mjs` + harness scratch `/tmp/test_penambahan.py` — bukan file repo). Tidak ada tes bobot=100, ambang 0,99/1,00, 69/70, idempotensi migrasi, gate multichain, 1-baris/minggu, atau bahasa di repo | §5.4 | `git status` (hanya 1 file QA baru) |

---

## 5. File kunci yang WAJIB dibaca reviewer

Urutan baca yang disarankan (dari yang paling menentukan):

1. `poller.py` (diff +862) — semua rumus + job baru F1–F4.
2. `migrations/2026-11-12-penambahan.sql` + `schema.sql` (diff +54) — skema.
3. `seed_multichain.py` + `verify_multichain.py` — gerbang multichain.
4. `dashboard/logic.py`, `dashboard/turso_read.py`, `dashboard/risk.py` — baca + tampilan.
5. `api/worker.js` (diff +291) — route coverage + perluasan `/api/latest`.
6. `web/src/app/ticker/[id]/page.tsx`, `web/src/app/HomeClient.tsx`,
   `web/src/lib/api.ts`, `web/src/lib/i18n.ts` — permukaan web.
7. `qa/test_coverage_2026-11-12.mjs` — satu-satunya guard QA baru di repo.
8. `check_elysium_weekly.py` — skrip pantau (bukan fitur live).
9. `bot.py` — **baca untuk mengonfirmasi D4**: apakah alert F1/F3 memang
   belum ada, atau ada di jalur lain yang tidak tertangkap diff.
