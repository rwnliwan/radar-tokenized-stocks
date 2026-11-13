# Desain Penambahan Radar Tokenized Stocks — 12 November 2026

**Status:** DESAIN untuk dinilai Septian. Bukan instruksi pembangunan, bukan ACC deploy.
Disusun 12 November 2026, sesudah ACC Septian 12 Nov 2026 20:22 WITA (5 fitur +
multichain top 10–13 per issuer + penjelasan web + testing real).
**Aturan yang mengikat dokumen ini:** tidak ada pembangunan (kode, migrasi DB, cron)
sebelum desain ini dinilai; tidak ada deploy live sebelum ACC deploy tersendiri;
ambang lama TIDAK diubah; fitur yang ada TIDAK dihapus.

**Dokumen induk yang dirujuk (tidak diulang isinya):**
- `~/workspace/research_notes/radar-rwa-flagship-20261024/DESAIN_TEKNIS_TAHAP1_DRAF.md`
  (desain awal + amendemen A1–A8 + Revisi 24–25 Okt 2026) — disebut "desain awal".
- `~/workspace/research_notes/radar-tokenized-chains-dex-20261112-1139/report.md`
  (riset multi-chain 12 Nov 2026, semua klaim berlabel live 12 Nov 2026 atau
  UNVERIFIED) — disebut "riset 12 Nov".
- Repo `~/workspace/radar-tokenized-stocks`: `schema.sql`, `poller.py` (857 baris),
  `bot.py`, `dashboard/logic.py`, `dashboard/risk.py`, `dashboard/turso_read.py`,
  `dashboard/app.py`, `api/worker.js`, `web/` — disebut "repo saat ini".

**Konvensi penanda (sama seperti desain awal):**
- **PRE-REGISTERED** = ambang/rumus dikunci di muka, SEBELUM analisis data yang
  bersangkutan, mengikuti doktrin Septian (desain awal Revisi 24 Okt butir 4,
  sama seperti gerbang Fraud Triage). Perubahan sesudahnya hanya lewat revisi
  tertulis bertanggal dengan alasan, bukan penalaan diam-diam atas hasil.
- **eksperimental** = tampil di semua permukaan dengan label itu sampai kalibrasi
  selesai (minimal 8 akhir pekan data teramati, sama seperti `weekend_risk_v1`
  desain awal §5.5).
- **UNVERIFIED** = belum dibuktikan live; wajib verifikasi sebelum masuk universe
  atau sebelum dipakai sebagai dasar alert.

---

## 1. Ringkasan scope yang di-ACC Septian 12 Nov 2026 20:22 WITA

Keputusan Septian (20:22 WITA): **ACC bangun 5 fitur + semua issuer top 10–13 per
issuer + penjelasan web. Testing real: backtest alert lama dari data tersimpan
(blockchain/Turso) + forward test paper via data mainnet.**

### 1.1 Lima fitur (F1–F5)

| # | Fitur | Status di desain awal | Inti penambahan ini |
|---|---|---|---|
| F1 | **Perp 3-leg** (Hyperliquid XYZ) | Baru — bukan di desain awal | Kaki ketiga: harga perp Hyperliquid XYZ vs harga spot tokenized (Radar) vs acuan saham. Alert bila perp menyimpang dari tokenized ≥ 1,0%. Perp adalah DATA, bukan tempat trading Radar — tidak ada order, tidak ada posisi. |
| F2 | **Monday Gap Predictor** | Baru — turunan Laporan Senin (produk #5) | Prediksi gap buka Senin + skor confidence 0–100, dihitung tiap Minggu malam dari data akhir pekan. Label "eksperimental". |
| F3 | **Exit Score 0–100** (`exit_score_v1`) | Produk #7 "Indeks Pintu Keluar" (non-MVP, 10–15 jam) kini di-ACC untuk dibangun | Satu angka per ticker per siklus dari 5 komponen (total 100). Disimpan sebagai KOLOM di `deviations`, bukan tabel baru. |
| F4 | **Liquidation Guard** | Produk #6 "Weekend Liquidation Guard" (non-MVP, 10–15 jam) kini di-ACC untuk dibangun | Monitor oracle lag + divergensi mark-vs-oracle + jarak ke harga likuidasi acuan. Label "eksperimental". |
| F5 | **Bukti nilai** (alert-accuracy audit) | Produk #8 "Replay Dislokasi" (sebagian) + bukti gerbang A1 | Penilaian hasil alert secara otomatis dan publik dari `alert_log` + replay akhir pekan lama; target akurasi awal ≥ 60% (desain awal §5.4). |

### 1.2 Multichain — top 10–13 per issuer

Universe lama (Solana + xStocks, 13 ticker, 35 pool ≥ $100 rb) **tetap**.
Ditambah, per issuer **maksimal 13 ticker** dan tiap ticker tetap wajib lolos
aturan universe desain awal §1.1 (**total kedalaman gabungan ≥ $500 rb DAN
≥ 2 venue DEX** — ambang ini TIDAK berubah):

| Chain + issuer | Vonis riset 12 Nov | Keputusan penambahan ini |
|---|---|---|
| Base + Coinbase (13 token) | **PASS** — NVDAc ≈ $3,3 jt, 4 venue (Aero/Aerodrome/Uniswap/Nami), live 12 Nov | **MASUK.** Verifikasi per ticker sebelum poller jalan (cap 13). |
| BNB Chain + bStocks (104 produk) | **PASS** — TSLAB ≈ $2,35 jt, PancakeSwap + Uniswap, live 12 Nov | **MASUK, top 10–13 saja.** Tiap ticker diverifikasi satu-per-satu (§1.1); angka NVDAB/SPYB hanya ada versi 20 Sep 2026 (dated) → tidak boleh dipakai sebagai bukti lolos. |
| Solana + xStocks | **PASS — sudah di Radar** | **TETAP.** Tidak ada perubahan. |
| Ethereum + Ondo | NEEDS ONE VERIFICATION — TSLAon ≈ $0,77 jt tapi venue ke-2 "Community v3" belum terverifikasi sebagai DEX independen | **BELUM MASUK.** Satu verifikasi dulu (identitas Community v3 + total lintas ticker). Bila lolos, masuk lewat revisi tertulis, bukan diam-diam. |
| Robinhood Chain + Robinhood | NEEDS ONE VERIFICATION — volume besar, likuiditas per ticker belum terverifikasi live | **BELUM MASUK.** Satu tarikan DexScreener token-pairs per ticker top (TSLA/NVDA/SPY) dulu. |
| Elysium + xStocks | NOT READY — diumumkan 9 Nov, tidak ada pool ditemukan 12 Nov | **JANGAN DIBANGUN.** Hanya skrip cek mingguan (§3.5, §4.8). |
| Hyperliquid spot wrapped xStocks | Di luar riset 12 Nov; token wrapped, bukan spot tokenized dengan redemption | **MONITOR SAJA, bukan kaki Radar.** Tidak masuk hitungan deviasi, alert, maupun universe. |
| Ethereum/BNB + xStocks; Solana/BNB + Ondo; Dinari; Securitize; Swarm; Backpack; Reality/Bitget; Superstate; Gate | FAIL — tipis / permissioned / RFQ / CEX-only / tidak ada pool | **TIDAK MASUK.** Dicatat di `universe_excluded.md` beserta alasannya. |

### 1.3 Penjelasan web

Web (`web/` + `dashboard/app.py`) WAJIB menjelaskan, dwibahasa ID/EN (desain awal
Revisi 24 Okt butir 2):
- chain, platform/DEX, dan issuer tiap ticker (lencana per ticker, bukan satu
  catatan kaki global);
- status cakupan saat ini: chain+issuer apa yang tercakup, apa yang belum, dan
  mengapa (pernyataan cakupan desain awal §6.4 diperluas dari "cakupan DEX" menjadi
  "cakupan chain × issuer × DEX");
- metodologi berversi tiap skor baru (`exit_score_v1`, `monday_gap_v1`,
  `perp_3leg_v1`, `liq_guard_v1`) + label "eksperimental" di mana berlaku;
- disclaimer yang sama seperti desain awal §5.6/§11: bukan nasihat keuangan,
  tidak ada kata "aman"/"disarankan"/"beli"/"jual".

### 1.4 Testing real (disetujui Septian)

- **Backtest** alert lama dari data tersimpan (Turso + arsip mentah `raw/`, retensi
  90 hari, desain awal §2.3) — replay, bukan cerita.
- **Forward test paper** via data mainnet read-only — **tanpa trading, tanpa gas,
  tanpa uang real**. Keputusan "would exit" dicatat sebagai kertas, hasilnya
  dinilai setelahnya (§5).
- Gerbang A1 (evaluasi Minggu ke-8, 19 Des 2026 — ≥ 200 pengguna TG aktif,
  retensi ≥ 30%, ≥ 10 will-pay, ≥ 1 calon B2B) **tidak berubah** oleh penambahan
  ini; fitur baru tidak menggeser ambang A1.

---

## 2. Threshold PRE-REGISTERED

Semua ambang di bawah ini dikunci SEBELUM analisis data yang bersangkutan.
Ambang lama dipertahankan tanpa perubahan:

| Ambang lama (desain awal) | Nilai | Status |
|---|---|---|
| Alert deviasi (§5.3) | \|dev\| ≥ **1,0%** | DIPERTAHANKAN |
| Pool ikut hitungan (§5.2) | `reserve_usd` ≥ **$100 rb** | DIPERTAHANKAN |
| Alert butuh total kedalaman lolos (§5.2) | ≥ **$250 rb** (+ ≥ 2 pool untuk antar-venue) | DIPERTAHANKAN |
| Universe lolos (§1.1) | total kedalaman ≥ **$500 rb** + **≥ 2 venue** | DIPERTAHANKAN |
| PoR basi (§5.3) | umur feed > **72 jam** | DIPERTAHANKAN |
| Deviasi prioritas tinggi (§5.3) | ≥ **3%** | DIPERTAHANKAN |
| Definisi "alert tepat" (§5.4) | deviasi kembali < **0,5%** sebelum bursa AS buka Senin berikutnya (alert akhir pekan) atau dalam **24 jam** (alert hari kerja) | DIPERTAHANKAN |
| Target akurasi awal (§5.4) | ≥ **60%** pada 8 minggu pertama | DIPERTAHANKAN (untuk alert deviasi/perp/exit, lihat §2.5) |

### 2.1 F1 — Perp 3-leg (Hyperliquid XYZ), `perp_3leg_v1`

Tiga kaki per ticker (hanya untuk 10 dari 13 ticker lama yang perps-nya live di
Hyperliquid mainnet per riset 12 Nov; SPY/QQQ/GLD tidak ada perp-nya → tidak
punya kaki perp, dan itu ditampilkan sebagai "tidak ada perp", bukan nol):
1. **Spot tokenized** — harga tertimbang kedalaman Radar (`depth_weighted_price`).
2. **Perp XYZ** — harga mark Hyperliquid (`perp_px` di `perp_snapshots`).
3. **Acuan saham** — close terakhir / median lintas-venue (mode median-only
   sampai lisensi display vs-close selesai, desain awal §4.2).

Deviasi yang dihitung tiap siklus (5 menit, sama seperti siklus spot):
- `dev_perp_vs_token_pct = (perp_px − dw) / dw × 100`
- `dev_perp_vs_ref_pct` (bila acuan tersedia) — dicatat, tidak memicu alert
  sendiri pada v1.

**Ambang alert PRE-REGISTERED:**
- Alert tipe `perp_deviation` bila **|dev_perp_vs_token_pct| ≥ 1,0%** — sama
  dengan ambang deviasi (§5.3), sengaja disamakan agar satu angka ambang berlaku
  untuk semua deviasi harga.
- Alert prioritas tinggi bila |dev| ≥ 3,0% (sama seperti §5.3).
- Gate yang sama seperti alert deviasi: total kedalaman spot yang lolos ≥ $250 rb
  dan perp snapshot segar (≤ 15 menit; bila basi, tidak ada alert perp — diam
  lebih baik daripada alert dari data basi, desain awal §7.1).
- Dedup: 24 jam per (ticker, tipe, channel), sama seperti `DEDUP_HOURS = 24`
  di `bot.py`.
- Hasil alert dinilai dengan definisi "alert tepat" §5.4 yang sama.

### 2.2 F2 — Monday Gap Predictor, `monday_gap_v1` — label "eksperimental"

Dihitung **sekali per minggu**, Minggu malam (setelah tutup sesi tokenized
Minggu, sebelum buka AS Senin), satu baris per ticker di `monday_gap`
(13 baris/minggu, §3.4).

**Rumus prediksi (PRE-REGISTERED):**
```
gap_pred_pct = 0,6 × D + 0,4 × R        (dibatasi ±10%)
D = deviasi akhir pekan, dev_vs_median_pct terakhir Minggu (%)
R = drift harga token Jumat tutup → Minggu malam, (P_Minggu − P_Jumat) / P_Jumat × 100 (%)
```
Tanda positif = prediksi buka Senin di ATAS harga token Minggu (gap naik);
negatif = sebaliknya. Ini prediksi arah + besaran, bukan kepastian.

**Skor confidence 0–100 (PRE-REGISTERED, total 100):**

| Komponen | Bobot | Rumus |
|---|---|---|
| Kualitas data akhir pekan | 0–30 | `pools_used` ≥ 3 dan depth ≥ $1 jt → 30; `pools_used` = 2 atau depth $250 rb–$1 jt → 15; selain itu → 0 |
| Konsistensi arah | 0–25 | D dan R searah (tanda sama) → 25; berlawanan → 0 |
| Spread antar-venue kecil | 0–20 | spread Minggu ≤ 0,5% → 20; 0,5–1,0% → 10; > 1,0% → 0 |
| Riwayat kalibrasi | 0–25 | +5 per akhir pekan terkalibrasi sebelumnya (prediksi vs aktual sudah dinilai), maks 25 setelah 5 akhir pekan |

**Label confidence:** Rendah < 40 · Sedang 40–69 · Tinggi ≥ 70.
**Label wajib:** "eksperimental" di semua permukaan sampai ≥ 8 akhir pekan
terkalibrasi (bar yang sama dengan `weekend_risk_v1`, desain awal §5.5).
**Penilaian hasil (PRE-REGISTERED):** prediksi dinyatakan **tepat** bila arah
(tanda) benar DAN |gap aktual Senin − gap_pred_pct| ≤ 1,0 poin persen.
Target awal: arah benar ≥ **50%** — lebih rendah dari 60% (§5.4) karena ini
prakiraan, bukan deteksi; angka 50% dikunci di muka dengan alasan ini, bukan
diturunkan dari hasil.

### 2.3 F3 — Exit Score 0–100, `exit_score_v1`

Dihitung tiap siklus per ticker, disimpan di kolom `deviations.exit_score` +
`exit_score_version` (§3.3). Rumus PRE-REGISTERED, total 100:

| # | Komponen | Bobot maks | Rumus (0 s.d. bobot maks) |
|---|---|---|---|
| 1 | Deviasi | 30 | \|dev_vs_median_pct\| × 10 poin per 1%, dibatasi 30 (≥ 3% → 30). Sama seperti komponen deviasi `weekend_risk_v1`. |
| 2 | Depth menipis | 25 | Rasio `r = qualifying_depth_usd / median_depth_7hari` (median depth 7 hari terakhir per ticker, dari `deviations`): r ≥ 1,0 → 0; r ≤ 0,5 → 25; di antaranya linear `25 × (1,0 − r) / 0,5`. |
| 3 | Redemption window | 20 | Redemption tutup ≤ 24 jam → 20; tutup ≤ 72 jam → 10; gated → 10; buka → 0; unknown → komponen TIDAK dihitung (lihat normalisasi di bawah). |
| 4 | Funding ekstrem | 15 | \|funding 8 jam\| perps (dari `perp_snapshots` terbaru): ≤ 0,01% → 0; ≥ 0,10% → 15; di antaranya linear. Ticker tanpa perp → komponen TIDAK dihitung. |
| 5 | OI melonjak | 10 | Kenaikan OI 24 jam (dari `perp_snapshots`): ≤ 0% → 0; ≥ +20% → 10; di antaranya linear. Ticker tanpa perp → komponen TIDAK dihitung. |

**Normalisasi (mengikuti pola `risk.py` `weekend_risk_score` v3.2):** komponen
yang datanya tidak ada (redemption unknown, ticker tanpa perp) TIDAK dihitung
dan TIDAK dinolkan — skor = `total_komponen_tersedia / maks_komponen_tersedia
× 100`, dibulatkan 1 desimal. Jumlah komponen tersedia + versinya selalu
disimpan/ditampilkan bersama skor (skor parsial harus kelihatan parsial).
Perubahan rumus menaikkan versi (`exit_score_v2`, dst.) dan dicatat — skor
lama tidak ditulis ulang.

**Band tampilan (bukan rekomendasi — bahasa faktual, desain awal §11):**
0–39 "Tekanan keluar rendah" · 40–69 "Tekanan keluar sedang" ·
70–100 "Tekanan keluar tinggi". Tidak ada kata "jual"/"keluar sekarang".

**Alert (PRE-REGISTERED):** `exit_score` ≥ **70** → satu alert tipe
`exit_high` per ticker per 24 jam (dedup sama seperti alert lain). Hasilnya
dinilai dengan definisi "alert tepat" §5.4 yang sama (deviasi kembali < 0,5%
dalam jendela itu).

### 2.4 F4 — Liquidation Guard, `liq_guard_v1` — label "eksperimental"

Monitor per ticker per jam (bukan per siklus 5 menit — likuidasi adalah risiko
lambat, bukan sinyal menit-per-menit), disimpan di `liquidation_watch` (§3.2).
Sumber: Hyperliquid info API (mark price + oracle price, read-only).

**Yang diukur (PRE-REGISTERED):**
- `oracle_lag_s` = umur data oracle saat dibaca (detik).
- Divergensi mark-vs-oracle = `|mark_px − oracle_px| / oracle_px × 100`.
- `liq_px_estimate` + `distance_pct` = jarak harga mark saat ini ke harga
  likuidasi acuan **HANYA bila** ada sumber level likuidasi terverifikasi
  (data likuidasi publik Hyperliquid). **Bila sumber itu belum terverifikasi,
  kedua kolom NULL dan guard turun ke dua ukuran di atas saja — tidak pernah
  difabrikasi.** (Kejujuran ini PRE-REGISTERED: guard yang separuh kosong dan
  jujur lebih baik daripada angka likuidasi karangan.)

**Ambang alert (PRE-REGISTERED):**
- **PERINGATAN** (`liquidation_watch`, bukan alert Telegram publik pada v1 —
  admin-only dulu selama forward test, §5.3) bila `oracle_lag_s` > **120 detik**
  ATAU divergensi mark-vs-oracle ≥ **1,0%** ATAU `distance_pct` ≤ **10%**
  (bila tersedia).
- **KRITIS** bila `oracle_lag_s` > **600 detik** ATAU divergensi ≥ **3,0%**
  ATAU `distance_pct` ≤ **5%** (bila tersedia).
- Label "eksperimental" di semua permukaan sampai 8 akhir pekan observasi.
- Guard ini TIDAK tahu posisi pengguna — ia memonitor kondisi pasar/oracle,
  bukan akun siapa pun. Itu ditulis di web.

### 2.5 F5 — Bukti nilai (alert-accuracy audit)

- Definisi "alert tepat" §5.4 DIPERTAHANKAN tanpa perubahan, dan kini berlaku
  untuk semua tipe alert: `deviation`, `spread`, `deviation_high`,
  `perp_deviation`, `exit_high` (likuidasi guard dinilai terpisah, §2.4 —
  ia bukan alert deviasi).
- Target akurasi awal **≥ 60%** (desain awal §5.4) untuk alert deviasi/perp/
  exit pada 8 minggu pertama sesudah tiap tipe aktif. Bila di bawah itu,
  ambang tipe itu ditinjau naik — lewat revisi tertulis, bukan diam-diam.
- Monday Gap dinilai dengan aturannya sendiri (§2.2, target arah ≥ 50%).
- Bukti ditampilkan publik: halaman per ticker + halaman metodologi memuat
  hitungan akurasi (n alert, n tepat, %) yang dapat dihitung ulang siapa pun
  dari `alert_log` — sama seperti janji desain awal §5.4.
- Laporan Senin (produk #5) menjadi tempat narasi bukti ini tiap minggu.

---

## 3. Skema data

Semua waktu UTC (ISO 8601), mengikuti `schema.sql` saat ini. Migrasi direncanakan
sebagai SATU file `migrations/2026-11-12-penambahan.sql` (idempotent,
`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN` dengan pengecekan
kolom — mengikuti pola migrasi 2026-11-09 `pools-excluded`), dan `schema.sql`
diperbarui agar cocok dengan hasil migrasi (satu sumber kebenaran).

### 3.1 Tabel baru — `perp_snapshots`

Satu baris per ticker per siklus 5 menit (baseline saja — TIDAK ikut jendela
rapat 1 menit; perp adalah konfirmasi, bukan pemicu menit-per-menit).

```sql
CREATE TABLE IF NOT EXISTS perp_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  ts TEXT NOT NULL,
  perp_px REAL,            -- harga mark Hyperliquid XYZ (USD)
  funding REAL,            -- funding rate per interval 8 jam, apa adanya dari API
  oi REAL,                 -- open interest (USD)
  dex TEXT NOT NULL DEFAULT 'xyz'
);
CREATE INDEX IF NOT EXISTS idx_perp_ticker_ts ON perp_snapshots(ticker_id, ts);
```

Hanya 10 ticker yang punya perp XYZ (SPY/QQQ/GLD tidak ada) → ±10 baris/siklus.
Retensi: mentah 30 hari lalu diagregasi per jam (pola `snapshots_hourly`,
desain awal §2.2); baris mentah dihapus dan dicatat di `poller_health`.

### 3.2 Tabel baru — `liquidation_watch`

Satu baris per ticker per jam dalam kondisi normal; baris tambahan per 5 menit
HANYA selama kondisi PERINGATAN/KRITIS (§2.4) masih aktif (bounded — lihat §6).

```sql
CREATE TABLE IF NOT EXISTS liquidation_watch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  ts TEXT NOT NULL,
  oracle_px REAL,          -- harga oracle Hyperliquid (USD)
  mark_px REAL,            -- harga mark Hyperliquid (USD)
  liq_px_estimate REAL,    -- NULL bila sumber level likuidasi belum terverifikasi (§2.4)
  distance_pct REAL,       -- NULL bila liq_px_estimate NULL
  source TEXT NOT NULL     -- mis. 'hyperliquid-info'
);
CREATE INDEX IF NOT EXISTS idx_liqwatch_ticker_ts ON liquidation_watch(ticker_id, ts);
```

Volume kecil; dipertahankan penuh (seperti `deviations`/`alert_log`).

### 3.3 Exit Score JADI KOLOM di `deviations` — bukan tabel baru

```sql
ALTER TABLE deviations ADD COLUMN exit_score REAL;              -- NULL bila belum dihitung
ALTER TABLE deviations ADD COLUMN exit_score_version TEXT;      -- 'exit_score_v1' bila terisi
```

**+0 writes.** Skor ditulis bersama baris `deviations` yang memang sudah ditulis
tiap siklus — tidak ada INSERT tambahan, tidak ada tabel baru, tidak ada job
baru. Ini keputusan desain yang disengaja (alasan kuota, §6): satu-satunya
fitur dari lima yang biaya tulisnya nol.

### 3.4 Monday Gap — DIPILIH: tabel `monday_gap` (bukan reuse kolom `weekend_risk_score`)

```sql
CREATE TABLE IF NOT EXISTS monday_gap (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker_id TEXT NOT NULL REFERENCES universe(ticker_id),
  week_start TEXT NOT NULL,        -- tanggal Sabtu awal akhir pekan itu (YYYY-MM-DD)
  gap_pred_pct REAL NOT NULL,      -- prediksi §2.2
  confidence REAL NOT NULL,        -- skor confidence 0-100 §2.2
  method_version TEXT NOT NULL DEFAULT 'monday_gap_v1',
  outcome_gap_pct REAL,            -- gap aktual Senin (diisi Senin pagi)
  outcome TEXT,                    -- pending / accurate / inaccurate
  outcome_ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_monday_gap_ticker_week ON monday_gap(ticker_id, week_start);
```

**Alasan memilih tabel baru (bukan reuse `weekend_risk_score` di `deviations`):**
1. **Semantik berbeda, frekuensi berbeda.** `weekend_risk_score` adalah skor
   risiko per SIKLUS (288 baris/ticker/hari) dengan kalibrasi 8-akhir-pekan dan
   riwayat yang sudah berjalan sejak 24 Okt; menimpanya dengan prediksi mingguan
   akan merusak riwayat kalibrasi itu dan membingungkan dua angka yang artinya
   beda. `monday_gap` adalah SATU prediksi per ticker per minggu (13 baris/
   minggu untuk seluruh universe lama; ~26 baris/minggu sesudah multichain).
2. **Kuota dapat diabaikan.** 13–26 baris/minggu ≈ 700–1.400 baris/tahun —
   0,01% dari batas tulis. Argumen "hemat tabel" tidak berlaku di sini; yang
   hemat adalah tidak menulis prediksi mingguan 288×/hari ke kolom siklus.
3. **Auditabilitas.** Satu baris = satu prediksi + satu hasil Senin. Hitungan
   akurasi arah (§2.2) adalah `COUNT` atas tabel kecil ini, bukan scan
   `deviations`.

### 3.5 Multichain — perluasan `universe` / `pools` (tanpa tabel baru)

- `universe.token_addresses` (JSON per chain) sudah mendukung multi-chain
  secara struktur — diisi alamat Base (Coinbase, sufiks `c`) dan BNB
  (bStocks, sufiks `B`) per ticker; `universe.issuer` membedakan
  `coinbase` / `bstocks`; `pools.chain`/`pools.dex` membedakan venue
  (Aerodrome/Uniswap/Base; PancakeSwap/Uniswap/BNB).
- `redemption_windows` + `por_feeds` diperluas per issuer baru (baris per
  issuer, bukan per ticker — volume kecil):
  - Coinbase: mint/redeem in-kind hanya untuk authorised participants,
    retail lewat secondary market; **tidak ada PoR publik ditemukan**
    (riset 12 Nov) → `por_feeds` untuk Coinbase dicatat `unknown` dengan
    catatan sumber, bukan diisi angka.
  - bStocks: convert 1:1 via Binance brokerage, < 1 detik; atestasi
    diterbitkan (detail UNVERIFIED) → `redemption_windows` dicatat dari
    sumber primer saat implementasi; PoR dicatat `unknown` sampai
    diverifikasi.
- **Ethereum + Ondo dan Robinhood Chain HANYA setelah verifikasi live lolos**
  (§1.2) — sampai saat itu tidak ada baris universe/pools untuk keduanya.
- **Hyperliquid spot wrapped xStocks MONITOR SAJA:** tidak masuk `universe`/
  `pools`; bila dipantau, hanya sebagai catatan di `universe_excluded.md`
  (alasan: token wrapped, bukan kaki Radar).
- **Elysium JANGAN DIBANGUN:** tidak ada tabel, tidak ada poller, tidak ada
  baris universe. Hanya skrip cek mingguan (§4.8) yang menulis log file.

### 3.6 Yang TIDAK berubah di skema

`snapshots`, `equity_refs`, `redemption_windows`, `por_feeds`,
`por_token_snapshots`, `alert_log`, `poller_health`, `waitlist` — struktur
tetap. `alert_log.alert_type` hanya mendapat nilai baru (`perp_deviation`,
`exit_high`, `liquidation_watch`) — tidak ada kolom baru. Retensi §2.2 desain
awal tetap berlaku dan diperluas ke `perp_snapshots` (§3.1).

---

## 4. Perubahan per file (daftar konkret — tanpa menulis kodenya)

Urutan bangun yang disarankan: skema (§3) → poller → bot → dashboard/logic →
api/worker → web → QA (§5.4). MVP yang sudah ada tetap jalan di setiap tahap
(tidak ada big-bang yang mematikan Radar).

### 4.1 `poller.py`

- `XSTOCKS_MINTS` → struktur alamat token umum per (chain, issuer, ticker)
  (Base/Coinbase, BNB/bStocks, Solana/xStocks); `run_cycle()` batch
  DexScreener tetap 1 request per 30 alamat, kini per chain bila alamat
  lintas chain tidak dapat dicampur dalam satu panggilan token (verifikasi
  saat implementasi; fallback = 1 batch per chain).
- `run_cycle()` — hitung `exit_score` + `exit_score_version` per ticker dari
  input siklus itu (deviasi, depth + median depth 7 hari dari `deviations`
  latest-only, redemption terbaru, perp terbaru) dan sertakan kedua kolom
  itu dalam INSERT `deviations` yang sudah ada. Komponen yang datanya tidak
  ada → NULL (normalisasi §2.3). **Tidak ada INSERT baru di siklus spot.**
- Baru: `run_cycle_perp()` — baca Hyperliquid info API (read-only;
  `allMids`/`metaAndAssetCtxs` untuk market `xyz:*`) tiap 5 menit, tulis
  `perp_snapshots`. Gagal baca → catat di `poller_health`, tidak
  menggagalkan siklus spot (isolasi seperti pola hourly redemption/PoR).
- Baru: `run_hourly_liquidation()` — slot per jam (menempel pada jam
  `_hourly_due` yang sudah ada): baca mark + oracle, tulis
  `liquidation_watch`; bila kondisi PERINGATAN/KRITIS, tulis tambahan per
  5 menit sampai kondisi reda. `liq_px_estimate` NULL sampai sumber level
  likuidasi terverifikasi (§2.4).
- Baru: `run_weekly_monday_gap()` — job Minggu malam: baca `deviations`
  latest-only akhir pekan per ticker, hitung §2.2, tulis 1 baris per ticker
  ke `monday_gap`; Senin pagi: isi `outcome_gap_pct` + `outcome` dari gap
  aktual (dibanding harga token Minggu malam).
- `LIQ_MIN = 100000.0`, ambang depth, dan price-sanity guard 25% TIDAK
  berubah. `state.json` mendapat kunci jam/minggu baru (`last_perp_check`,
  `last_monday_gap_week`) mengikuti pola `last_hourly_check`.

### 4.2 `bot.py`

- `evaluate_alerts()` — tipe baru: `perp_deviation` (|dev perp vs tokenized|
  ≥ 1,0%, §2.1) dan `exit_high` (exit_score ≥ 70, §2.3). Keduanya memakai
  gate kesegaran + depth yang sama seperti alert deviasi; `dev_stale` tetap
  memblokir alert berbasis harga basi.
- `load_live_tickers()` — gabung (latest-only, terindeks) `perp_snapshots`
  terbaru + `exit_score` terbaru per ticker ke `tickers_data`; ticker tanpa
  perp mendapat `perp = None` (dirender "—", bukan 0).
- `format_alert()` — format pesan baru untuk `perp_deviation` (tiga kaki:
  spot / perp / acuan + funding + OI saat itu) dan `exit_high` (skor +
  5 komponen + versi + disclaimer). Bahasa tetap faktual (§11 desain awal).
- `record_alert_safe()` / `record_alert()` / `recent_alert_exists()` —
  tidak berubah kecuali nilai `alert_type` baru diizinkan; dedup 24 jam
  per (ticker, tipe, channel) berlaku untuk tipe baru.
- `liquidation_watch` TIDAK mengirim alert Telegram publik pada v1 —
  admin-only selama forward test (§5.3); pengiriman publik butuh ACC
  tersendiri setelah kalibrasi.
- `SPREAD_THRESHOLD = 1.0`, `DEV_HIGH_THRESHOLD = 3.0`, `DEPTH_MIN = 250000.0`,
  `LIQ_MIN`, `DEDUP_HOURS = 24` TIDAK berubah.

### 4.3 `dashboard/logic.py` + `dashboard/risk.py` + `dashboard/turso_read.py` + `dashboard/app.py`

- `dashboard/risk.py` (baru, fungsi murni tanpa I/O — mengikuti pola
  `weekend_risk_score`):
  - `exit_score(dev_pct, depth_ratio, redemption_status, funding, oi_change_24h)`
    → dict komponen + total + maks + `score_100` + `components_present` +
    `method_version = "exit_score_v1"`.
  - `monday_gap_predict(D, R, pools_used, depth, spread, calibrated_weekends)`
    → `(gap_pred_pct, confidence, label)` sesuai §2.2.
  - `liquidation_status(oracle_lag_s, divergence_pct, distance_pct)`
    → `ok / warning / critical` sesuai §2.4.
- `dashboard/logic.py` — helper baca terbaru untuk skor/gap/guard (tanpa
  hitungan baru di sini); `best_exit_venues()` TIDAK berubah.
- `dashboard/turso_read.py` — fungsi baru, SEMUA latest-only via indeks
  `(ticker_id, ts)` + `ORDER BY ts DESC LIMIT 1` (lihat larangan §6.3):
  `get_latest_exit_scores()`, `get_perp_latest(ticker)`,
  `get_monday_gap(week_start)`, `get_liquidation_latest(ticker)`,
  `get_alert_accuracy()` (baca `alert_log` kecil + `monday_gap` kecil).
- `dashboard/app.py` — kartu/panel baru di halaman per ticker:
  Exit Score (angka + 5 batang komponen + versi + "berapa komponen tersedia"),
  Perp 3-leg (spot vs perp vs acuan + funding + OI), Monday Gap Predictor
  (prediksi + confidence + label "eksperimental"), Liquidation Guard
  (status + oracle lag + divergensi + jarak likuidasi/NULL); peta panas
  mendapat kolom Exit Score; pernyataan cakupan (§6.4 desain awal) diperluas
  ke chain × issuer × DEX + daftar "belum tercakup" beserta alasan.

### 4.4 `api/worker.js`

- Route baru (mengikuti pola `/api/latest` — snapshot konsisten + cache):
  `/api/perp` (perp terbaru per ticker), `/api/exit-score` (exit_score
  terbaru per ticker), `/api/monday-gap` (prediksi minggu berjalan).
- `/api/latest` diperluas (backward-compatible, kolom nullable baru):
  `exit_score`, `exit_score_version`, `perp_dev_pct`, `perp_px`.
- `/api/history` mendapat parameter `series=perp|exit_score` (opsional;
  default tidak berubah).
- `/api/health` + `/api/alerts` TIDAK berubah. Tidak ada auth baru.
- Kontrak kesegaran (§6.3 desain awal) berlaku untuk route baru: bila data
  perp/guard basi, respons menandainya basi, bukan menyembunyikannya.

### 4.5 `web/` (Next.js)

- `src/lib/api.ts` — fetcher baru untuk `/api/perp`, `/api/exit-score`,
  `/api/monday-gap` (mengikuti pola fetcher yang sudah ada).
- `src/lib/risk.ts` — perluas: format Exit Score + komponen, format
  Monday Gap + confidence, format status Liquidation Guard.
- `src/app/ticker/[id]/page.tsx` + `Chart.tsx` — panel baru yang sama
  seperti §4.3 (Exit Score, Perp 3-leg, Monday Gap, Liquidation Guard).
- `src/app/page.tsx` (`HomeClient.tsx`) — kolom Exit Score di daftar
  ticker + lencana chain/issuer/DEX per ticker.
- `src/app/methodology/page.tsx` — metodologi berversi baru:
  `exit_score_v1`, `monday_gap_v1`, `perp_3leg_v1`, `liq_guard_v1`,
  termasuk rumus + bobot + label eksperimental + cara menghitung ulang
  akurasi dari log publik.
- `src/lib/i18n.ts` — string ID/EN untuk semua label baru (dwibahasa,
  desain awal Revisi 24 Okt butir 2).

### 4.6 File pendukung

- `schema.sql` — tambah §3.1–§3.4 (agar cocok dengan migrasi).
- `migrations/2026-11-12-penambahan.sql` — migrasi baru (idempotent).
- `seed_universe.py` / `verify_universe.py` — dukung chain Base/BNB +
  issuer Coinbase/bStocks; tiap ticker baru wajib lolos gerbang §1.1
  SEBELUM `is_active = 1`; yang gagal masuk `universe_excluded.md`.
- `universe_excluded.md` — tambah: Ondo/Ethereum (menunggu verifikasi
  Community v3), Robinhood Chain (menunggu verifikasi likuiditas),
  Elysium (tidak ada pool), Hyperliquid spot wrapped (monitor saja),
  + semua yang FAIL di riset 12 Nov beserta alasannya.
- Baru: `scripts/check_elysium.py` — cek mingguan read-only (DexScreener
  chain Elysium: ada/tidak pool xStocks + angka bila ada); output
  `logs/elysium-check-YYYY-MM-DD.md`; TIDAK menulis ke Turso (kecuali
  satu baris `poller_health` bila pool tiba-tiba muncul — sebagai sinyal,
  bukan sebagai data universe).
- `turso_usage_check.py` — tidak berubah; tetap sumber angka kuota §6.

### 4.7 Yang TIDAK disentuh

`dashboard/i18n.py` (kecuali penambahan string — tanpa perubahan struktur),
`redirect-worker/`, `api/deploy_worker.py`, `api/wrangler.toml`, skema
`tabel lama`, cron yang sudah ada, dan semua fitur MVP yang berjalan.

---

## 5. Rencana testing

Prinsip: **bukti dulu, klaim kemudian.** Tidak ada fitur yang dinyatakan
"berfungsi" sebelum lolos §5.1–§5.4. Testing tidak memakai uang real, tidak
membuka posisi, tidak membayar gas.

### 5.1 Backtest — replay dari data tersimpan

Sumber: Turso (`deviations`, `snapshots`, `alert_log` sejak 24 Okt 2026) +
arsip mentah `raw/` (retensi 90 hari, desain awal §2.3) + data mainnet publik
(Hyperliquid candles/funding history bila tersedia lewat endpoint publik).

| Yang di-replay | Cara | Kriteria lolos |
|---|---|---|
| Exit Score v1 atas akhir pekan lama | Hitung ulang `exit_score_v1` dari `deviations` tersimpan (deviasi + depth tersedia penuh; redemption/PoR dari `redemption_windows`/`por_feeds`; funding/OI HANYA bila arsip perp tersedia — bila tidak, skor parsial dan DICATAT parsial, tidak pernah diimputasi diam-diam) | Skor dapat dihitung untuk ≥ 90% baris `deviations` akhir pekan; komponen yang hilang terdokumentasi per baris |
| Monday Gap atas akhir pekan lama | Prediksi §2.2 dihitung dari data Jumat–Minggu tiap akhir pekan sejak 24 Okt (n kecil — 3 akhir pekan penuh: 24–25 Okt, 31 Okt–1 Nov, 7–8 Nov — plus 14–15 Nov bila sudah lewat) vs gap aktual Senin | Laporan menyebut n secara eksplisit; tidak ada cherry-picking (semua akhir pekan yang datanya lengkap ikut dihitung, yang tidak lengkap dicatat alasannya) |
| Perp 3-leg | Bila histori mark/funding Hyperliquid tersedia via endpoint publik, replay deviasi perp-vs-tokenized atas `deviations` tersimpan; bila TIDAK tersedia, backtest perp dinyatakan TIDAK MUNGKIN dan diganti forward test penuh (§5.2) — kejujuran ini dicatat, bukan ditutup-tutupi | Salah satu: replay selesai dengan n + akurasi, ATAU pernyataan tertulis "tidak ada histori publik → forward-only" |
| Alert lama (§5.4) | Nilai ulang SEMUA alert `alert_log` sejak 24 Okt dengan definisi §5.4 (83 alert pada testing week — teknis lolos, komersial 0 pengguna; angka ini baseline, bukan target) | Akurasi terhitung + dapat diverifikasi dari `alert_log` (n, n tepat, %) |

### 5.2 Forward test paper — mainnet read-only

- **Durasi:** minimal 4 minggu sejak semua fitur live (ideal 8 minggu —
  menyamai jendela kalibrasi `weekend_risk_v1`); mencakup ≥ 4 akhir pekan.
- **Cara:** poller + bot + dashboard jalan dengan data mainnet live; setiap
  kali kondisi "would exit" terpenuhi (exit_score ≥ 70, atau alert
  `perp_deviation`/`exit_high`), sistem mencatat baris kertas (waktu,
  ticker, skor/komponen, "keputusan kertas: keluar") — **tidak ada order,
  tidak ada posisi, tidak ada gas, tidak ada uang real**.
- **Penilaian (PRE-REGISTERED, §2.5):** akurasi alert (deviasi/perp/exit)
  ≥ 60% dengan definisi §5.4; Monday Gap arah benar ≥ 50%; Liquidation
  Guard: NOL alert KRITIS yang disebabkan data oracle basi (bila ada,
  itu bug, bukan sinyal — diperbaiki, bukan dihitung sebagai "tepat").
- **Selama forward test:** alert `liquidation_watch` admin-only (§4.2);
  alert publik baru (`perp_deviation`, `exit_high`) tayang dengan label
  eksperimental di pesannya sampai kalibrasi selesai.
- **Hasil ditulis** sebagai laporan (angka + n + tanggal) sebelum keputusan
  "lanjut / ubah ambang / hentikan fitur" — keputusan itu ACC Septian.

### 5.3 Batasan testing (yang TIDAK dilakukan)

- Tidak ada trading dengan uang real dalam bentuk apa pun (termasuk "coba
  kecil dulu").
- Tidak ada posisi Hyperliquid (long/short) atas nama proyek atau Septian.
- Tidak ada penulisan on-chain (tidak ada mint/burn/approve).
- Tidak ada backfill data yang difabrikasi: komponen yang tidak ada datanya
  tetap NULL + skor parsial.

### 5.4 QA guard yang harus lolos (sebelum deploy)

Guard yang sudah ada (wajib tetap lolos — tidak ada yang dimatikan):
`qa_harness.py`, `qa_post_fix.py`, `tests_fase2/` (bot alerts, dashboard
data, freshness, i18n, redemption schedule, risk, trial components,
waitlist SQL), `qa/test_spread_guard.py`, dan semua `qa/test_r*_fix.py`.

Guard baru (ditambah di ronde fix yang sama, mengikuti aturan standing
"tiap temuan masuk QA"):
1. **Jumlah bobot:** komponen Exit Score = 100 (30+25+20+15+10) dan
   komponen confidence Monday Gap = 100 (30+25+20+25) — tes unit di
   `risk.py` (bila bobot berubah tanpa total 100 → FAIL).
2. **Ambang alert:** perp 0,99% → tidak ada alert; 1,00% → alert
   (tes `evaluate_alerts` dengan data sintetis); exit_score 69 → tidak
   ada alert; 70 → alert.
3. **Skema:** migrasi `2026-11-12-penambahan.sql` idempotent (jalan 2×
   tanpa error) + `PRAGMA table_info(deviations)` memuat `exit_score` /
   `exit_score_version` + ketiga tabel baru ada dengan indeksnya.
4. **Anti full-scan (§6.3):** grep atas kode baru — tidak ada `COUNT(*)`
   atau `SELECT *` ke `snapshots` / `deviations` / `perp_snapshots` /
   `liquidation_watch` di jalur cron/dashboard/API (kecuali tes yang
   memang menguji larangan itu).
5. **Multichain gate:** tiap ticker baru di `seed_universe.py` wajib
   membawa bukti total depth ≥ $500 rb + ≥ 2 venue (tes: seed dengan
   ticker di bawah ambang → ditolak, tercatat di `universe_excluded.md`).
6. **Monday Gap:** tepat 1 baris per ticker per minggu (tes: jalankan
   `run_weekly_monday_gap` 2× untuk minggu yang sama → tetap 1 baris
   per ticker, bukan duplikat).
7. **Bahasa:** tidak ada kata "aman"/"disarankan"/"beli"/"jual" di pesan
   alert baru dan panel baru (ID maupun EN) — tes string seperti guard
   yang sudah ada.
8. **Retensi:** agregasi per jam mencakup `perp_snapshots` (tes: baris
   mentah > 30 hari teragregasi + terhapus, dicatat di `poller_health`).

---

## 6. Anggaran kuota kasar

**Acuan 12 Nov 2026 (dashboard Turso, via `turso_usage_check.py`):**
reads kumulatif **63,5 jt / 500 jt (12,7%)**, writes kumulatif
**801.650 / 10 jt (8,0%)**, storage **76,3 MB**.
Catatan dari pantauan induk: proyeksi berbasis laju (rate-basis) 46,7 jt
reads/bulan masih OK, tetapi proyeksi kumulatif 165,9 jt reads — spike awal
November adalah risiko utama (Okt 30 lalu DB sempat terblokir). **Reads,
bukan writes, adalah constraint yang mengikat.** Semua estimasi di bawah
ini memakai pengali indeks 3× untuk `snapshots` (desain awal §2.2) dan 2×
untuk tabel baru berindeks tunggal — angka kasar, ditandai [estimasi].

### 6.1 Baseline saat ini (untuk perbandingan)

- Writes kumulatif 801.650 dalam ±19 hari sejak 24 Okt ≈ **±42 rb/hari
  ≈ 1,3 jt/bulan** (snapshots 35 pool + deviations 13 ticker + health).
- Ini SUDAH termasuk pengali indeks Turso (angka dashboard, bukan hitungan
  baris mentah).

### 6.2 Writes tambahan per fitur (per bulan, [estimasi])

| Penambahan | Hitungan | Tambahan/bulan |
|---|---|---|
| Chain baru: Base + Coinbase, 13 ticker × ±2,5 pool ≈ 32 pool | 32 × 288 siklus × 30 hari ≈ 276 rb baris × 3 (indeks) | ≈ **+0,8 jt** |
| Chain baru: BNB + bStocks, top 11 ticker × ±2,5 pool ≈ 27 pool | 27 × 288 × 30 ≈ 233 rb baris × 3 | ≈ **+0,7 jt** |
| Deviations tambahan (24 ticker baru) | 24 × 288 × 30 ≈ 207 rb baris × 2 | ≈ **+0,4 jt** |
| F1 `perp_snapshots` (10 ticker, 5 menit, tanpa tight window) | 10 × 288 × 30 ≈ 86 rb baris × 2 | ≈ **+0,2 jt** |
| F4 `liquidation_watch` (per jam + event saat bahaya) | 13 × 24 × 30 ≈ 9 rb + event (bounded, maks 13 × 288 × hari-bahaya) | ≈ **+0,02 jt** (tipikal; worst-case satu minggu bahaya penuh ≈ +0,1 jt) |
| F2 `monday_gap` | 13–26 baris/minggu | ≈ **+0,0001 jt** (diabaikan) |
| F3 Exit Score (kolom di `deviations`) | — | **+0** |
| **Total tambahan** | | **≈ +2,1 jt/bulan** |
| **Total proyeksi (baseline 1,3 + tambahan 2,1)** | | **≈ 3,4 jt/bulan dari 10 jt (34%)** — headroom ±3× |

### 6.3 Reads — aturan keras (lebih penting dari writes)

- Reads kumulatif sudah 12,7% pada 12 Nov dengan proyeksi kumulatif 165,9 jt
  (33%) — spike adalah risikonya, bukan laju harian normal. Karena itu:
- **LARANGAN: tidak ada query full-scan baru.** Dilarang menambah
  `COUNT(*)` / `SELECT *` ke `snapshots`, `deviations`, `perp_snapshots`,
  atau `liquidation_watch` di jalur cron, dashboard, maupun API.
  (Pelajaran 2026-11-03: satu `COUNT(*)` tanpa indeks yang cocok = 23.249
  rows_read untuk satu query cek.)
- **Semua baca latest-only via indeks `(ticker_id, ts)`** dengan
  `ORDER BY ts DESC LIMIT 1` (atau `LIMIT N` kecil untuk grafik — grafik
  membaca `deviations`/agregat jam, bukan `snapshots` mentah).
- **Cek usage hanya via `turso_usage_check.py`** (Platform API, 0 rows_read)
  atau `poller_health` × rata-rata baris/siklus — bukan query ke tabel besar.
- Route API baru (§4.4) membaca latest-only + cache yang sama seperti
  `/api/latest`; dashboard memakai `@st.cache_data(ttl=300)` yang sudah ada.
- Estimasi kenaikan reads dari fitur baru: **< 5% dari laju saat ini**
  (beberapa query latest-only per load dashboard/API) — kecil, tetapi
  tetap dipantau mingguan lewat `turso_usage_check.py`; bila proyeksi
  kumulatif melewati 80% dari batas (400 jt reads), Septian dikabari dan
  penambahan berikutnya ditahan (aturan standing insiden Turso 2026-11-01).

### 6.4 Storage

- `snapshots` tetap dominan: +59 pool × 288/hari × ±120 byte ≈ **±2 MB/hari
  mentah ≈ 60 MB/bulan** sebelum agregasi/retensi 30 hari (§2.2) — retensi
  dan agregasi per jam WAJIB mencakup pool baru sejak hari pertama, atau
  storage tumbuh tanpa batas.
- `perp_snapshots` ±86 rb baris/bulan ≈ ±10 MB/bulan sebelum agregasi.
- `liquidation_watch` + `monday_gap` dapat diabaikan (< 1 MB/tahun).
- Total storage saat ini 76,3 MB dari batas 5 GB (pengalaman proyek Brain;
  angka tier gratis wajib cek ulang di dashboard Turso saat implementasi —
  desain awal §2) — storage BUKAN constraint dalam 12 bulan ke depan bila
  retensi jalan.

---

## 7. Pertanyaan terbuka + yang butuh ACC Septian

### 7.1 Butuh ACC Septian (tidak jalan tanpa ACC eksplisit)

1. **ACC desain ini** — sebelum satu baris kode pun ditulis (aturan
   desain awal: tidak ada pembangunan sebelum ACC desain).
2. **ACC deploy live** — sesudah build + QA §5.4 lolos + review DeepSeek
   (§7.2). Aturan Septian: kabari dia DULU sebelum deploy update besar.
3. **ACC cron Elysium mingguan** (`scripts/check_elysium.py`) — di mana
   jalan (VM yang sama dengan poller?) dan siapa yang menerima hasilnya
   (log file saja, atau kabar ke Septian bila pool tiba-tiba muncul?).
4. **ACC publikasi alert baru** — `perp_deviation` dan `exit_high` boleh
   tayang ke kanal Telegram publik sejak hari pertama (dengan label
   eksperimental), atau admin-only dulu selama forward test 4 minggu?
   (Rekomendasi induk: admin-only dulu; keputusan Septian.)
5. **ACC pengiriman `liquidation_watch` ke publik** — setelah kalibrasi
   (§4.2: v1 admin-only).

### 7.2 Review DeepSeek (sesuai standing rule MLF/Learn — tiap ronde review,
### temuan WAJIB masuk QA di ronde fix yang sama)

- Review desain ini oleh DeepSeek (reviewer utama) SEBELUM pembangunan:
  periksa rumus §2.2–§2.3 (apakah bobotnya masuk akal? apakah normalisasi
  parsialnya jujur?), ambang §2.4 (apakah 120/600 detik dan 1%/3% tepat
  untuk oracle Hyperliquid?), dan estimasi kuota §6 (apakah pengali indeks
  dan hitungan pool baru realistis?).
- Temuan DeepSeek adalah USULAN, bukan perintah — Chief (induk) adalah
  arbiter akhir: hanya temuan yang terverifikasi ke sumber yang masuk fix;
  temuan yang salah/noise dicatat sebagai noise dan TIDAK diperbaiki
  (keputusan Septian 12 Nov 2026 20:24 WITA). Temuan terverifikasi yang
  string-lockable → fixture guard QA (§5.4); yang semantik → kelas
  review di ronde fix.

### 7.3 Pertanyaan terbuka (hanya Septian / verifikasi live yang bisa menjawab)

1. **Histori Hyperliquid:** apakah endpoint publik menyediakan histori
   mark/funding/OI cukup panjang untuk backtest perp (§5.1)? Bila tidak,
   backtest perp resmi dinyatakan forward-only.
2. **Sumber level likuidasi:** apakah ada sumber publik terverifikasi untuk
   `liq_px_estimate` (§2.4)? Bila tidak ada, guard tetap jalan dengan dua
   ukuran (lag + divergensi) dan kolom likuidasi tetap NULL.
3. **Ondo/Ethereum — identitas "Community v3":** DEX independen atau label
   agregator/fork Uniswap v3? (Satu verifikasi, riset 12 Nov §4.)
4. **Robinhood Chain — likuiditas per ticker:** tarikan DexScreener
   token-pairs per ticker top (TSLA/NVDA/SPY) — berapa total + berapa venue?
5. **Coinbase redemption/PoR:** sumber primer apa untuk status redemption
   Coinbase (AP-only) dan apakah ada PoR publik? (Riset 12 Nov: tidak ada
   PoR publik ditemukan.)
6. **bStocks top ticker:** di luar TSLAB, ticker mana yang lolos §1.1
   dengan angka live (bukan angka 20 Sep 2026)?
7. **Lisensi DexScreener:** klausul larangan resale/redistribusi dan
   "produk kompetitor" (riset 12 Nov §7b) — apakah Radar read-only internal
   + display publik atas data Base/BNB masuk dalam lisensi? Cek ToS primer
   sebelum display publik chain baru (tugas minggu pertama, desain awal
   §4.2 butir 3 — berlaku ulang untuk chain baru).
8. **Rate limit Hyperliquid info API:** berapa batas baca publiknya, dan
   apakah polling 5 menit × 10 market + per jam oracle aman di bawahnya?
9. **OKXICE (launch 23 Nov 2026):** apakah venue ini akan menawarkan pool
   DEX publik (maka masuk radar verifikasi berikutnya) atau venue
   permissioned (maka tidak)? — pantau, bukan asumsi.
10. **Bahasa panel baru:** dwibahasa ID/EN mengikuti desain awal, atau ada
    preferensi lain untuk istilah baru (mis. "Exit Score" diterjemahkan
    atau dipertahankan)?

---

## 8. Catatan penutup — yang TIDAK berubah

- Ambang lama (§2 tabel atas) TIDAK berubah. Fitur yang ada TIDAK dihapus.
  Monetisasi tetap DIPARKIR (desain awal Revisi 25 Okt butir 2): Tahap 1
  tanpa penjualan; free tier permanen; open-core (kode Apache-2.0, dataset
  terkunci 5 gerbang).
- Gerbang A1 (19 Des 2026) TIDAK berubah. Laporan Senin tetap manual.
- Doktrin yang sama berlaku untuk semua yang baru di sini: **ambang dan rumus
  didefinisikan di awal, dinilai apa adanya; perubahan hanya lewat revisi
  tertulis bertanggal.** Bila angka di dokumen ini ternyata salah setelah data
  masuk, yang diubah adalah dokumennya (dengan alasan + tanggal) — bukan
  angkanya diam-diam.

---

*Dokumen ini DESAIN. Perubahan apa pun sesudah penilaian Septian dicatat
sebagai revisi bertanggal di bawah baris ini, bukan dengan mengedit diam-diam
bagian yang sudah dinilai.*

---

## Revisi 13 Nov 2026 — ronde fix review DeepSeek Radar (temuan M6 + S4, terverifikasi Chief)

Temuan DeepSeek M6 dan S4 keduanya BENAR (verifikasi Chief di
`review/REVIEW-DEEPSEEK-RADAR.md`). Revisi ini memperbaiki DOKUMEN — angka
di kode (`poller.py`) TIDAK diubah: bukan penalaan diam-diam. Bila suatu hari
ambang di bawah ini memang diubah, itu revisi tertulis baru + versi skor baru.

### M6 — Ambang funding Exit Score adalah ambang PER-JAM, bukan per 8 jam

**Yang salah di dokumen ini:** §2.3 komponen 4 menulis "`|funding 8 jam|`"
dan §3.1 memberi komentar skema "`funding rate per interval 8 jam`". Kedua
label itu SALAH.

**Fakta (sumber: `poller.py:633-640` docstring `exit_score_v1`,
`:665-671`, dan `:536-538` docstring `fetch_xyz_ctxs`):** `funding` yang
disimpan di `perp_snapshots` adalah rate desimal **apa adanya dari API
Hyperliquid (metaAndAssetCtxs), yaitu rate per funding interval — per jam**.
Ambang §2.3 (≤ 0,01% → 0; ≥ 0,10% → 15; linear di antaranya) diterapkan
pada `|funding| × 100` **tanpa pengali ×8** — kode tidak pernah mengalikan 8,
dan komentar kode sendiri mencatat pemetaan ini sebagai pertanyaan
interpretasi terbuka, bukan sesuatu yang diselesaikan diam-diam dengan
aritmetika.

**Koreksi yang berlaku mulai revisi ini:**

1. Ambang 0,01%/0,10% adalah ambang **per jam** (per-interval sebagaimana
   dilaporkan API). Ambang per 8 jam yang setara — 0,00125%/0,0125% per jam —
   **TIDAK dipakai** dan tidak boleh dipakai diam-diam.
2. **Konsekuensi jujur:** funding hourly biasa (≈ 0,0001 desimal = 0,01%
   per jam, atau lebih kecil) memberi komponen 0,0. Hanya funding hourly
   ≥ 0,10% (0,001 desimal — rate satu jam yang sangat ekstrem) yang memberi
   15 penuh. **Dalam praktiknya komponen funding hampir selalu 0** — skor
   Exit Score hampir tidak pernah mendapat poin dari funding. Ini sifat
   ambang yang kini didokumentasikan apa adanya, bukan bug yang diperbaiki
   diam-diam.
3. Label "funding 8 jam" di §2.3 dan komentar skema §3.1 dicabut oleh revisi
   ini (teks lama di atas TIDAK diedit diam-diam — koreksi ini yang berlaku).

**Kalimat web (diterapkan 13 Nov 2026 ke string i18n `methodology_exit_score`
di `web/src/lib/i18n.ts` dan `dashboard/i18n.py`, EN + ID, sebagai kalimat
koreksi yang ditambahkan di akhir string — bukan edit diam-diam):**

- EN: "Correction 13 Nov 2026: the funding thresholds (0.01% → 0; 0.10% →
  15) apply to the HOURLY rate exactly as published by the Hyperliquid API,
  not to an 8-hour rate — the design's '8h funding' label was wrong. The
  equivalent 8-hour thresholds (0.00125%/0.0125% per hour) are NOT used. In
  practice the funding component is almost always 0 at ordinary hourly
  rates."
- ID: "Koreksi 13 Nov 2026: ambang funding (0,01% → 0; 0,10% → 15) berlaku
  atas rate PER JAM apa adanya dari API Hyperliquid, bukan rate 8 jam —
  label 'funding 8 jam' di desain salah. Ambang setara per 8 jam
  (0,00125%/0,0125% per jam) TIDAK dipakai. Dalam praktik komponen funding
  hampir selalu 0 pada rate hourly biasa."

Label penampil nilai funding (`perp_funding`, tampil sebagai persen dari
nilai apa adanya tanpa pengali — `page.tsx:613` `perp_funding * 100`,
`dashboard/app.py:1922` `{_fund:.4%}`) ikut dikoreksi dari "Funding (8h)" /
"Funding (8 jam)" menjadi "Funding (hourly)" / "Funding (per jam)".

### Revisi 13 Nov 2026 (2) — ambang funding setara per-8-jam + exit_score_v2
(keputusan Septian 08:27 WITA, mengikuti rekomendasi Chief; kalibrasi live
Chief 13 Nov 2026 ~08:30 WITA)

Revisi ini MENGGANTIKAN butir 1–2 koreksi M6 pada revisi di atas (ambang
per-jam 0,01%/0,10% + "komponen funding hampir selalu 0"). Ambang lama
tersebut terbukti ~8× terlalu ketat: rate yang dilaporkan API Hyperliquid
adalah rate PER JAM, sementara ambang 0,01%/0,10% dirancang untuk rate
per 8 jam.

**Kalibrasi (Chief, 13 Nov 2026, 235 pasar perp Hyperliquid via
metaAndAssetCtxs):** median |funding| per jam = 0,00125%; hanya 2 dari 235
pasar ≥ 0,0125% per jam. Ambang baru di bawah ini menempatkan median tepat
di kaki bawah (0 poin) dan hanya ~1% pasar di plafon (15 poin) —
terkalibrasi wajar, sementara ambang lama (0,01%/0,10% per jam) memberi 0
pada hampir semua pasar.

**Yang berlaku mulai revisi ini (`exit_score_v2`):**

1. Ambang komponen funding: |funding| per jam ≤ 0,00125% → 0 poin;
   ≥ 0,0125% → 15 poin; di antaranya linear
   `15 × (pct − 0,00125) / 0,01125`. Bobot komponen tetap 15; rumus
   komponen lain TIDAK berubah.
2. Versi skor naik ke `exit_score_v2` (`poller.py: EXIT_SCORE_VERSION`,
   fungsi `exit_score_v2`). Skor v1 yang sudah tersimpan TIDAK ditulis
   ulang — versi selalu ditampilkan bersama skor, jadi v1 dan v2 tetap
   bisa dibedakan di riwayat.
3. Kalimat metodologi di web/dashboard diperbarui ke ambang + kalibrasi
   baru (string i18n `methodology_exit_score`, EN + ID).
4. Label nilai funding tetap "Funding (hourly)" / "Funding (per jam)" —
   rate-nya memang per jam; yang berubah hanya ambangnya.

### S4 — Ambang oracle lag 120/600 detik DICABUT dari guard v1

**Yang salah di dokumen ini:** §2.4 menetapkan ambang PERINGATAN
"`oracle_lag_s` > 120 detik" dan KRITIS "`oracle_lag_s` > 600 detik".

**Fakta (sumber: `poller.py:730-745` `liquidation_status`,
`:943` `liquidation_status(div, None, None)`, dan komentar migrasi
`migrations/2026-11-12-penambahan.sql`):** `liquidation_status()` memang
menerima `oracle_lag_s`, tetapi satu-satunya pemanggil,
`run_hourly_liquidation`, selalu memanggilnya dengan lag `None` — karena
endpoint publik Hyperliquid (metaAndAssetCtxs) **tidak mempublikasikan
timestamp oracle**, sehingga umur data oracle tidak bisa diukur dari
endpoint publik. Migrasi sengaja TIDAK membuat kolom `oracle_lag_s`
("There is deliberately NO oracle_lag_s column").

**Koreksi yang berlaku mulai revisi ini:**

1. Ambang lag 120/600 detik **DICABUT dari guard v1** — keduanya inert
   (tidak pernah bisa terpicu karena lag selalu `None`) dan tidak boleh
   tampil sebagai ambang aktif di permukaan mana pun.
2. Guard v1 = **divergensi mark-vs-oracle saja**: PERINGATAN bila divergensi
   ≥ 1,0%, KRITIS bila divergensi ≥ 3,0% — ditambah `distance_pct`
   (PERINGATAN ≤ 10%, KRITIS ≤ 5%) **bila** sumber level likuidasi
   terverifikasi; saat ini `liq_px_estimate`/`distance_pct` NULL (sumber
   belum terverifikasi, §2.4) sehingga guard v1 efektif hanya divergensi.
3. Bila suatu hari sumber timestamp oracle terverifikasi, ambang lag dapat
   dihidupkan kembali lewat revisi tertulis baru — bukan dengan mengisi lag
   karangan.

**Kalimat web (disetujui 13 Nov 2026, BELUM diterapkan — tidak ada slot
i18n-nya):** tidak ada string metodologi `monday_gap_v1`/`liq_guard_v1` di
`web/src/lib/i18n.ts` maupun `dashboard/i18n.py` (verifikasi: grep
`monday_gap|liq_guard|liquidation` di kedua file = 0 hasil; sama dengan
jawaban Q11 review). Kalimat di bawah ini adalah teks yang disetujui untuk
dipakai saat slot metodologi itu dibuat; TIDAK diterapkan ke string mana pun
dalam ronde ini karena slotnya tidak ada — jangan mengarang slot baru.

- EN: "Liquidation Guard (liq_guard_v1). The v1 guard watches the
  mark-vs-oracle divergence only: warning at 1.0%, critical at 3.0%. The
  120/600-second oracle-lag thresholds from the 12 Nov design were removed
  on 13 Nov 2026: the public Hyperliquid endpoints publish no oracle
  timestamp, so oracle lag cannot be measured and the thresholds could
  never fire. Distance to the liquidation level is shown only if a verified
  public liquidation-level source exists; until then it stays empty, never
  invented."
- ID: "Liquidation Guard (liq_guard_v1). Guard v1 hanya memantau divergensi
  mark-vs-oracle: peringatan pada 1,0%, kritis pada 3,0%. Ambang oracle-lag
  120/600 detik dari desain 12 Nov DICABUT pada 13 Nov 2026: endpoint publik
  Hyperliquid tidak mempublikasikan timestamp oracle sehingga lag oracle
  tidak bisa diukur dan ambang itu tidak pernah bisa terpicu. Jarak ke harga
  likuidasi hanya ditampilkan bila ada sumber level likuidasi publik yang
  terverifikasi; sampai saat itu kolomnya kosong, tidak pernah dikarang."
