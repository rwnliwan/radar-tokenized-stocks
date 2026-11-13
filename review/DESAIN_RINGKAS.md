# Ringkasan Desain Penambahan Radar — 12 Nov 2026

Sumber utama: `DESAIN_PENAMBAHAN_2026-11-12.md` (desain lengkap).
File ini hanya ringkasan agar reviewer cepat masuk konteks; bila ada
selisih, dokumen desain lengkap yang berlaku.

**ACC Septian 12 Nov 2026 20:22 WITA:** bangun 5 fitur + semua issuer
top 10–13 per issuer + penjelasan web. Testing real: backtest alert lama
dari data tersimpan (blockchain/Turso) + forward test paper via data
mainnet. **Bukan ACC deploy** — deploy butuh ACC tersendiri.

Aturan yang mengikat: tidak ada pembangunan sebelum desain dinilai;
ambang lama TIDAK diubah; fitur yang ada TIDAK dihapus.

---

## 1. Lima fitur (F1–F5)

| # | Fitur | Inti |
|---|---|---|
| F1 | **Perp 3-leg** (`perp_3leg_v1`, Hyperliquid XYZ) | Kaki ketiga: harga perp Hyperliquid XYZ vs harga spot tokenized (Radar) vs acuan saham. Alert bila perp menyimpang dari tokenized ≥ 1,0%. Perp adalah DATA, bukan tempat trading — tidak ada order, tidak ada posisi. Hanya 10 dari 13 ticker lama yang punya perp live (SPY/QQQ/GLD tidak ada → ditampilkan "tidak ada perp", bukan nol). |
| F2 | **Monday Gap Predictor** (`monday_gap_v1`) — label "eksperimental" | Prediksi gap buka Senin + skor confidence 0–100, dihitung tiap Minggu malam. Rumus: `gap_pred_pct = 0,6 × D + 0,4 × R` (dibatasi ±10%), D = deviasi akhir pekan terakhir Minggu, R = drift harga token Jumat tutup → Minggu malam. Tepat bila arah benar DAN \|gap aktual − prediksi\| ≤ 1,0 poin persen. Target arah benar ≥ 50% (lebih rendah dari 60% karena ini prakiraan, bukan deteksi — dikunci di muka). |
| F3 | **Exit Score 0–100** (`exit_score_v2`) | Satu angka per ticker per siklus dari 5 komponen (total 100). Disimpan sebagai KOLOM di `deviations`, bukan tabel baru (+0 writes). Band tampilan: 0–39 "Tekanan keluar rendah", 40–69 "sedang", 70–100 "tinggi". Bahasa faktual — tidak ada kata "jual"/"keluar sekarang". Alert `exit_high` bila skor ≥ 70 (1×/ticker/24 jam). |
| F4 | **Liquidation Guard** (`liq_guard_v1`) — label "eksperimental" | Monitor divergensi mark-vs-oracle + jarak ke harga likuidasi acuan, per jam (bukan per 5 menit). PERINGATAN bila divergensi ≥ 1,0% ATAU `distance_pct` ≤ 10%; KRITIS bila ≥ 3,0% / ≤ 5%. Ambang lag oracle DICABUT (revisi 13 Nov 2026): endpoint publik Hyperliquid tidak mempublikasikan timestamp oracle, jadi lag tidak terukur — cabang lag tidak pernah menyala. v1 admin-only (tidak ada alert Telegram publik). `liq_px_estimate` NULL sampai sumber level likuidasi terverifikasi — tidak pernah difabrikasi. |
| F5 | **Bukti nilai** (alert-accuracy audit) | Penilaian hasil alert otomatis + publik dari `alert_log` + replay akhir pekan lama. Definisi "alert tepat" §5.4 dipertahankan (deviasi kembali < 0,5% sebelum bursa AS buka Senin berikutnya untuk alert akhir pekan, atau dalam 24 jam untuk alert hari kerja). Target akurasi awal ≥ 60% untuk alert deviasi/perp/exit. Bukti ditampilkan publik per ticker + halaman metodologi (n, n tepat, % — dapat dihitung ulang dari `alert_log`). |

---

## 2. Threshold PRE-REGISTERED (dikunci sebelum analisis data)

### 2.1 Ambang lama — DIPERTAHANKAN tanpa perubahan
| Ambang | Nilai |
|---|---|
| Alert deviasi | \|dev\| ≥ **1,0%** |
| Pool ikut hitungan | `reserve_usd` ≥ **$100 rb** |
| Alert butuh total kedalaman lolos | ≥ **$250 rb** (+ ≥ 2 pool untuk antar-venue) |
| Universe lolos | total kedalaman ≥ **$500 rb** + **≥ 2 venue** |
| PoR basi | umur feed > **72 jam** |
| Deviasi prioritas tinggi | ≥ **3%** |
| Target akurasi awal | ≥ **60%** (8 minggu pertama) |

### 2.2 F1 — Perp 3-leg
- `dev_perp_vs_token_pct = (perp_px − dw) / dw × 100` (dw = harga tertimbang kedalaman Radar).
- Alert `perp_deviation` bila \|dev\| ≥ **1,0%**; prioritas tinggi ≥ 3,0%.
- Gate: total kedalaman spot lolos ≥ $250 rb + snapshot perp segar (≤ 15 menit; bila basi, tidak ada alert perp). Dedup 24 jam per (ticker, tipe, channel).

### 2.3 F2 — Monday Gap, confidence 0–100
| Komponen | Bobot | Rumus |
|---|---|---|
| Kualitas data akhir pekan | 0–30 | `pools_used` ≥ 3 dan depth ≥ $1 jt → 30; = 2 atau depth $250 rb–$1 jt → 15; selain itu → 0 |
| Konsistensi arah | 0–25 | D dan R searah → 25; berlawanan → 0 |
| Spread antar-venue kecil | 0–20 | spread Minggu ≤ 0,5% → 20; 0,5–1,0% → 10; > 1,0% → 0 |
| Riwayat kalibrasi | 0–25 | +5 per akhir pekan terkalibrasi sebelumnya, maks 25 setelah 5 akhir pekan |

Label confidence: Rendah < 40 · Sedang 40–69 · Tinggi ≥ 70. Label
"eksperimental" sampai ≥ 8 akhir pekan terkalibrasi.

### 2.4 F3 — Exit Score, total 100
| # | Komponen | Bobot maks | Rumus |
|---|---|---|---|
| 1 | Deviasi | 30 | \|dev_vs_median_pct\| × 10 poin per 1%, dibatasi 30 (≥ 3% → 30) |
| 2 | Depth menipis | 25 | r = `qualifying_depth_usd / median_depth_7hari`; r ≥ 1,0 → 0; r ≤ 0,5 → 25; di antaranya linear `25 × (1,0 − r) / 0,5` |
| 3 | Redemption window | 20 | Tutup ≤ 24 jam → 20; ≤ 72 jam → 10; gated → 10; buka → 0; unknown → komponen TIDAK dihitung |
| 4 | Funding ekstrem | 15 | \|funding per jam\|: ≤ 0,00125% → 0; ≥ 0,0125% → 15; di antaranya linear. Ticker tanpa perp → TIDAK dihitung |
| 5 | OI melonjak | 10 | Kenaikan OI 24 jam: ≤ 0% → 0; ≥ +20% → 10; linear. Ticker tanpa perp → TIDAK dihitung |

**Normalisasi (mengikuti pola `risk.py` `weekend_risk_score` v3.2):**
komponen yang datanya tidak ada TIDAK dihitung dan TIDAK dinolkan —
skor = `total_komponen_tersedia / maks_komponen_tersedia × 100`,
dibulatkan 1 desimal. Jumlah komponen tersedia + versinya selalu
disimpan/ditampilkan bersama skor (skor parsial harus kelihatan parsial).
Perubahan rumus menaikkan versi (`exit_score_v2`, dst.); skor lama tidak
ditulis ulang.

**Revisi 13 Nov 2026 (`exit_score_v2`, review DeepSeek M6):** ambang
funding ditulis untuk rate per-8-jam padahal Hyperliquid
mempublikasikan rate PER JAM — ambang lama (0,01%/0,10% per jam) ~8×
terlalu ketat, komponen praktis selalu 0. Ambang baru adalah setara
per-8-jam: |funding| per jam ≤ 0,00125% → 0; ≥ 0,0125% → 15; linear
di antaranya. Kalibrasi live 13 Nov 2026 (235 pasar perp Hyperliquid):
median |funding|/jam = 0,00125%, hanya 2/235 ≥ 0,0125%. Ambang lag
oracle DICABUT pada revisi yang sama (S4): tidak ada timestamp oracle
di endpoint publik, jadi lag tidak terukur.

**Tampilan (opsi B, 13 Nov 2026 — display saja, definisi tidak berubah):**
beranda + halaman ticker menampilkan skor parsial dengan jumlah
komponennya (n/5) + badge "Skor parsial"; band TIDAK ditampilkan untuk
skor parsial (aturan M5). Bila jumlah tersimpan cocok dengan komponen
yang bisa disimpulkan dari baris `/api/latest` (self-check), tooltip
badge menyebut komponen yang hilang + alasannya: "tanpa pasar perp"
(ticker tidak punya pasar perp Hyperliquid XYZ — struktural, 34 ticker),
"feed perp basi" (snapshot ada tapi > 15 menit), "riwayat perp <24 jam"
(OI butuh snapshot ≥ 24 jam; feed mulai 12 Nov 2026 13:32 UTC, jadi OI
tidak bisa ada sebelum 13 Nov 13:32 UTC), "status redemption tidak
diterbitkan issuer" (hanya xStocks yang menerbitkan status; issuer lain
"unknown" permanen). Bila jumlah tersimpan ≠ jumlah yang disimpulkan
(mis. AMZNr: tersimpan 1, disimpulkan 2 — median depth 7 hari belum
ada), hanya jumlah tersimpan yang ditampilkan, tanpa nama komponen.

### 2.5 F4 — Liquidation Guard
Lihat §1 F4 di atas. Guard TIDAK tahu posisi pengguna — ia memonitor
kondisi pasar/oracle, bukan akun siapa pun (ditulis di web).

### 2.6 F5 — Penilaian
Definisi "alert tepat" §5.4 berlaku untuk semua tipe alert:
`deviation`, `spread`, `deviation_high`, `perp_deviation`, `exit_high`
(liquidation guard dinilai terpisah — ia bukan alert deviasi). Bila
akurasi di bawah 60%, ambang tipe itu ditinjau naik — lewat revisi
tertulis, bukan diam-diam.

---

## 3. Multichain — top 10–13 per issuer (aturan universe TIDAK berubah)

Universe lama (Solana + xStocks, 13 ticker, 35 pool ≥ $100 rb) **tetap**.
Per issuer maksimal 13 ticker; tiap ticker tetap wajib lolos
**total kedalaman ≥ $500 rb DAN ≥ 2 venue DEX**.

| Chain + issuer | Vonis riset 12 Nov | Keputusan desain |
|---|---|---|
| Base + Coinbase (13 token) | PASS — NVDAc ≈ $3,3 jt, 4 venue, live 12 Nov | **MASUK.** Verifikasi per ticker sebelum poller jalan (cap 13) |
| BNB Chain + bStocks (104 produk) | PASS — TSLAB ≈ $2,35 jt, PancakeSwap + Uniswap, live 12 Nov | **MASUK, top 10–13 saja.** Angka NVDAB/SPYB versi 20 Sep 2026 (dated) tidak boleh dipakai sebagai bukti lolos |
| Solana + xStocks | PASS — sudah di Radar | **TETAP.** Tidak ada perubahan |
| Ethereum + Ondo | NEEDS ONE VERIFICATION — TSLAon ≈ $0,77 jt tapi venue ke-2 "Community v3" belum terverifikasi sebagai DEX independen | **BELUM MASUK.** Satu verifikasi dulu; bila lolos, masuk lewat revisi tertulis |
| Robinhood Chain + Robinhood | NEEDS ONE VERIFICATION — volume besar, likuiditas per ticker belum terverifikasi live | **BELUM MASUK.** Satu tarikan DexScreener token-pairs per ticker top (TSLA/NVDA/SPY) dulu |
| Elysium + xStocks | NOT READY — diumumkan 9 Nov, tidak ada pool ditemukan 12 Nov | **JANGAN DIBANGUN.** Hanya skrip cek mingguan |
| Hyperliquid spot wrapped xStocks | Di luar riset; token wrapped, bukan spot tokenized dengan redemption | **MONITOR SAJA, bukan kaki Radar** |
| Ethereum/BNB + xStocks; Solana/BNB + Ondo; Dinari; Securitize; Swarm; Backpack; Reality/Bitget; Superstate; Gate | FAIL — tipis / permissioned / RFQ / CEX-only / tidak ada pool | **TIDAK MASUK.** Dicatat di `universe_excluded.md` |

**Hasil verifikasi live 12 Nov (lihat `VERIFIKASI_MULTICHAIN_2026-11-12.md`):**
Ondo/Ethereum GAGAL (venue ke-2 `communityV3` = klon factory Uniswap V3
anonim, bukan DEX terverifikasi); Robinhood Chain LOLOS Tier 1 (TSLA
$2,26 jt, NVDA $7,16 jt, SPY $8,01 jt); Elysium BELUM AKTIF (0 pool
berlikuiditas); Hyperliquid spot MONITOR SAJA (TSLAX/AAPLX tanpa ask).

**Hasil seed dry-run (lihat `SEED_MULTICHAIN_2026-11-12.md`):**
127 simbol diperiksa → 33 lolos aturan → **30 ticker di-seed (cap 13/
issuer), 115 pool ≥ $100 rb**, kedalaman terlacak ±$76,9 jt
(Coinbase 9 ticker/15 pool; bStocks 8/24; Robinhood 13/76).
**Belum satu baris pun ditulis ke Turso live** — seed `--live` butuh
`RADAR_SEED_CONFIRM=ACC-2026-11-12` (ACC Septian).

---

## 4. Skema baru (satu migrasi: `migrations/2026-11-12-penambahan.sql`)

| Objek | Isi |
|---|---|
| Tabel baru `perp_snapshots` | 1 baris/ticker/siklus 5 menit: `perp_px`, `funding` (rate per interval — per jam, apa adanya dari API), `oi` (USD), `dex` default `'xyz'`. Retensi mentah 30 hari → agregasi per jam. Indeks `(ticker_id, ts)` |
| Tabel baru `liquidation_watch` | 1 baris/ticker/jam normal; tambahan per 5 menit HANYA selama PERINGATAN/KRITIS. `oracle_px`, `mark_px`, `liq_px_estimate` (NULL sampai sumber terverifikasi), `distance_pct` (NULL bila liq NULL), `source`. Indeks `(ticker_id, ts)` |
| Kolom baru di `deviations` | `exit_score REAL` + `exit_score_version TEXT` (saat ini `exit_score_v2`, sejak revisi 13 Nov 2026). +0 writes — ikut INSERT `deviations` yang sudah ada |
| Tabel baru `monday_gap` | 1 baris/ticker/minggu (`week_start` = Sabtu): `gap_pred_pct`, `confidence`, `method_version` default `'monday_gap_v1'`, `outcome_gap_pct`, `outcome` (pending/accurate/inaccurate), `outcome_ts`. Indeks `(ticker_id, week_start)` |

Tidak berubah: `snapshots`, `equity_refs`, `redemption_windows`,
`por_feeds`, `por_token_snapshots`, `alert_log`, `poller_health`,
`waitlist`. `alert_log.alert_type` hanya mendapat nilai baru
(`perp_deviation`, `exit_high`, `liquidation_watch`).

**Perluasan multichain tanpa tabel baru:** `universe.token_addresses`
(JSON per chain) + `universe.issuer` (`coinbase`/`bstocks`/`robinhood`);
`pools.chain`/`pools.dex` membedakan venue; `redemption_windows` +
`por_feeds` diperluas per issuer (Coinbase PoR = `unknown`, bukan angka;
bStocks atestasi UNVERIFIED).

---

## 5. Penjelasan web (wajib, dwibahasa ID/EN)

Web (`web/` + `dashboard/app.py`) WAJIB menjelaskan:
- chain, platform/DEX, dan issuer tiap ticker (lencana per ticker);
- status cakupan saat ini: chain+issuer apa yang tercakup, apa yang
  belum, dan mengapa (pernyataan cakupan diperluas dari "cakupan DEX"
  menjadi "cakupan chain × issuer × DEX");
- metodologi berversi tiap skor baru (`exit_score_v1`, `monday_gap_v1`,
  `perp_3leg_v1`, `liq_guard_v1`) + label "eksperimental" di mana berlaku;
- disclaimer yang sama seperti desain awal §5.6/§11: bukan nasihat
  keuangan, tidak ada kata "aman"/"disarankan"/"beli"/"jual".

---

## 6. Testing (disetujui Septian)

- **Backtest** alert lama dari data tersimpan (Turso + arsip mentah
  `raw/`, retensi 90 hari) — replay, bukan cerita. Lihat
  `BACKTEST_ALERT_2026-11-12.md` dan `HASIL_TEST.md` paket ini.
- **Forward test paper** via data mainnet read-only — tanpa trading,
  tanpa gas, tanpa uang real. Minimal 4 minggu (ideal 8 minggu),
  ≥ 4 akhir pekan. Setiap kondisi "would exit" dicatat sebagai kertas.
  Penilaian pre-registered: akurasi alert ≥ 60%; Monday Gap arah benar
  ≥ 50%; Liquidation Guard: NOL alert KRITIS palsu dari data basi
  (bila ada = bug, bukan sinyal). Selama forward test, alert
  `liquidation_watch` admin-only; alert publik baru tayang dengan label
  eksperimental sampai kalibrasi selesai.
- Gerbang A1 (evaluasi Minggu ke-8, 19 Des 2026 — ≥ 200 pengguna TG
  aktif, retensi ≥ 30%, ≥ 10 will-pay, ≥ 1 calon B2B) **tidak berubah**.

---

## 7. Kuota (ringkas — detail di `KUOTA_PENAMBAHAN_2026-11-12.md`)

Acuan 12 Nov 20:23 WITA: reads kumulatif 63,5 jt/500 jt (12,7%),
writes 801.650/10 jt (8,0%), storage 76,3 MB. Reads, bukan writes,
adalah constraint yang mengikat (spike awal Nov adalah risiko utama;
30 Okt DB sempat terblokir).

Estimasi desain §6.2: tambahan ≈ +2,1 jt writes/bln → total ≈ 3,4 jt/bln
(34%). Estimasi ulang di `KUOTA_PENAMBAHAN_2026-11-12.md` (laju aktual):
(a) 5 fitur saja → 2,31 jt/bln (23,1%); (a)+(b) +Base → 3,81 jt (38,1%);
(a)+(b)+(c) +BNB top 13 → 5,32 jt (53,2%, AMAN BERSYARAT — retensi 30
hari + agregasi hourly terbukti jalan dulu, checkpoint hari 2/4/7);
(d) 104 bStocks + 430 Ondo penuh → 42,3 jt (423%) JEBOL — jangan.

**Aturan keras §6.3:** tidak ada query full-scan baru (`COUNT(*)` /
`SELECT *` ke `snapshots`/`deviations`/`perp_snapshots`/
`liquidation_watch` di jalur cron/dashboard/API). Semua baca latest-only
via indeks `(ticker_id, ts)` + `ORDER BY ts DESC LIMIT 1`.
