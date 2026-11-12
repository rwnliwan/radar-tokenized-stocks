# Hasil Test — Penambahan Radar 12 Nov 2026

Disusun 12 Nov 2026 ±21:05 WITA dari dokumen sumber + pengujian ulang
yang dijalankan saat penyusunan paket (read-only; tidak ada tulis ke
Turso live, tidak ada deploy). Angka di sini adalah apa yang terukur —
bukan klaim.

---

## 1. Backtest alert (dari `BACKTEST_ALERT_2026-11-12.md`)

**Tanggal analisis:** 12 Nov 2026 ~20:40 WITA, data live sampai
12:21 UTC / 20:21 WITA. **Read-only** terhadap Turso live. Tidak ada
tulis/ubah, tidak ada outcome palsu ke `alert_log`, tidak ada deploy.
Acuan: desain awal §5.3–§5.4 (ambang ≥ 1,0%; "alert tepat" = deviasi
tertimbang kembali < 0,5% sebelum bursa AS buka Senin berikutnya untuk
alert akhir pekan, atau dalam 24 jam untuk alert hari kerja; target
akurasi awal ≥ 60%).

### 1.1 Headline

| Angka | Nilai |
|---|---|
| Total baris `alert_log` | **97 baris = 90 event** (7 event tercatat 2×, satu per channel `en`/`id`) |
| Event deviasi (spread + deviation_high) | **37 event** (semua tipe `spread`; `deviation_high` = 0) |
| TEPAT (rekonstruksi spread dari snapshots) | **32** |
| TIDAK TEPAT | **0** |
| Belum tertutup / tidak bisa dinilai | **5** (semua GOOGLx) |
| Akurasi = tepat / (tepat + tidak tepat) | **32/32 = 100%** di antara yang bisa dinilai |
| Pangsa TEPAT dari semua alert deviasi | 32/37 = **86,5%** |
| Target §5.4 (≥ 60%) | **TERPENUHI** di antara yang bisa dinilai — dengan caveat §1.3 |

Periode data: 24 Okt – 12 Nov 2026 (19 hari + 1 jam), 6.079 siklus
poller, 76.767 baris `deviations` (13 ticker). Cocok silang dengan
testing week 2–8 Nov: **83 alert s.d. 8 Nov cocok persis** dengan
`EVALUASI-TESTING-WEEK-2026-11-08.md` (52 redemption + 30 spread +
1 batch); sejak 8 Nov +14 baris = 7 event spread baru. `waitlist` = 0
baris (dihitung ulang hari itu) — 0 pengguna eksternal konsisten.

Per ticker (event spread): SPYx 12, GOOGLx 6, NVDAx 6, GLDx 4, CRCLx 3,
MSTRx 2, QQQx 2, TSLAx 2. Nol: AAPLx, COINx, HOODx, METAx, MSFTx
(COINx/HOODx/METAx masing-masing hanya 1 pool sehingga spread
antar-venue tidak mungkin terjadi).

Waktu menutup (32 TEPAT): median **4,5 menit**; 20/32 ≤ 10 menit;
28/32 ≤ 30 menit. Distribusi besar spread saat alert: 1,0–1,5% = 28
event; 1,5–3% = 5; ≥ 3% = 4 (NVDAx 7,894%, NVDAx 4,426%, GLDx 4,367%,
SPYx 100,041%).

### 1.2 Cara penilaian (dua lapis — hanya lapis 2 yang dipakai)

- **Lapis 1 — §5.4 apa adanya dari tabel `deviations`: TIDAK BISA
  DINILAI, dibuang dengan alasan.** `dev_vs_close_pct` NULL di
  76.767/76.767 baris (100%) — mode median-only, tidak ada sumber equity
  berlisensi. `dev_vs_median_pct` NULL di 32,7% baris; dari 51.672 baris
  non-NULL, < 0,5% di 51.655 (99,97%), ≥ 1,0% di 0 baris. Uji proxy naif
  dari kolom ini menghasilkan 32 TEPAT / 5 TIDAK TEPAT — **dibuang**,
  karena besaran itu < 0,5% di 99,97% siklus apa pun (TEPAT hampir
  otomatis) dan kelima "TIDAK TEPAT" itu GOOGLx yang jendelanya berisi
  0 baris non-NULL (data kosong salah dibaca sebagai gagal menutup).
- **Lapis 2 — rekonstruksi spread dari `snapshots` (yang dipakai).**
  Per event spread, spread (hi−lo)/dw per siklus dalam jendela 24 jam
  dari `snapshots`: pool lolos = `reserve_usd` ≥ $100rb, butuh ≥ 2 pool
  lolos per siklus, dw = rata-rata harga dibobot reserve. Hasil:
  **TEPAT 32, TIDAK TEPAT 0, tidak bisa dinilai 5.**

### 1.3 Caveat — BACA SEBELUM MEMAKAI ANGKA 100%

1. **Akurasi 100% menyanjung (flattering), 3 alasan:** (a) 2 alert
   tick-buruk ikut terhitung TEPAT (SPYx 100,041% pada 6 Nov — harga
   buruk bertahan berjam-jam sebelum terkoreksi; jendela SPYx 11 Nov
   mengandung spread rekonstruksi sampai 128,7% dari tick buruk);
   (b) 5 alert GOOGLx yang tidak bisa dinilai keluar dari penyebut;
   (c) n = 32 masih kecil untuk 8 minggu pertama (periode ini baru
   ~3 minggu).
2. **Kaki akhir pekan §5.3/§5.4 belum teruji sama sekali:**
   `deviation_high` (ambang implementasi 3,0% atas `dev_vs_median` di
   `bot.py`) tidak pernah terpicu — dan memang tidak mungkin terpicu
   karena `dev_vs_median` tidak pernah mencapai 1,0% di 76.767 baris.
   Semua 37 alert terjadi pada hari kerja saat bursa buka. Akurasi
   "alert deviasi" akhir pekan masih kosong (0/0) dan **tidak boleh
   dibaca dari angka 100% ini**.
3. **5 alert GOOGLx tidak bisa dinilai (83% dari alert GOOGLx):** di
   seluruh jendela 24 jam, kurang dari 2 pool GOOGLx yang lolos pada
   setiap siklus (pool tipis `solana:3P1P…` ber-reserve $80.913–86.364
   sepanjang 379 siklus — di bawah ambang $100rb — sementara pool
   satunya $1,45–1,51 jt). Bila kelima itu seandainya TIDAK TEPAT semua,
   akurasi menjadi 32/37 = 86,5% — tetap di atas target.
4. **Ambang 1,0% terlihat longgar secara substantif (observasi, bukan
   usulan perubahan):** 28/37 alert (76%) hanya 1,0–1,5%, dan 28/32 yang
   TEPAT menutup dalam ≤ 30 menit (median 4,5 menit) — pola konsisten
   dengan noise venue sesaat, bukan dislokasi yang bertahan. Tidak ada
   pemicu §5.3 untuk menaikkan ambang (> 50% alert tidak akurat —
   teramati 0%) maupun menurunkannya (tidak ada alert 4 minggu —
   teramati 37 alert dalam 3 minggu).
5. **Rekonstruksi tidak mereplikasi price-sanity guard 25% bot**
   (pool mana yang di-guard tidak tersimpan per siklus) — spread
   rekonstruksi bisa melebihi angka bot saat ada tick buruk. Arah
   biasnya konservatif untuk TEPAT.
6. **Celah data:** outage besar 30 Okt 07:16 → 1 Nov 03:27 UTC
   (44 jam 11 mnt; 31 Okt nol baris untuk semua ticker); AAPLx & MSFTx
   kehilangan burst 1-menit hari kerja (4.949 baris vs 6.079 ticker
   lain — absen 14:01–14:59 dan 20:31–21:29 UTC tiap hari kerja;
   penyebab tidak diselidiki, di luar skop read-only).
7. **Kolom yang menyesatkan:** `threshold_pct` TIDAK berisi ambang —
   pada ke-44 baris spread, `threshold_pct` == `dev_at_alert_pct`
   persis (bot mengisi keduanya dari spread yang sama). `outcome` =
   `'pending'` di 97/97 baris; `outcome_ts` dan
   `closed_below_threshold_ts` NULL di 97/97 — tidak ada outcome
   tersimpan yang bisa dipakai; semua penilaian dihitung fresh dan
   **tidak ditulis kembali ke `alert_log`**.
8. **Biaya backtest:** ±220 rb rows read (~0,04% dari limit bulanan
   500 jt) — ronde 1 ±19,6 rb + agregat `deviations` ±153 rb; ronde 2
   53.170 baris `snapshots` + ±15 rb baris kecil. Tidak ada `COUNT(*)` /
   `SELECT *` full-scan ke `snapshots`.

---

## 2. Forward test — BELUM TERSEDIA saat paket disusun

**File `FORWARD_TEST_2026-11-12.md` belum ada di repo saat paket ini
disusun (12 Nov 2026 ±21:00 WITA). Jangan fabrikasi hasilnya.**

Yang direncanakan (desain §5.2): minimal 4 minggu sejak semua fitur
live (ideal 8 minggu), ≥ 4 akhir pekan, mainnet read-only, tanpa
trading/gas/uang real; setiap kondisi "would exit" dicatat sebagai
kertas; penilaian pre-registered (akurasi alert ≥ 60%; Monday Gap arah
≥ 50%; Liquidation Guard NOL alert KRITIS dari data oracle basi).
Selama forward test: `liquidation_watch` admin-only; alert publik baru
dengan label eksperimental.

**Yang sudah bisa dicatat sebagai sinyal awal (bukan forward test):**
harness scratch `/tmp/test_penambahan.py` menjalankan
`run_weekly_monday_gap` atas minggu 2026-11-07 (data live): hanya
**2 prediksi dari 13 ticker** (NVDAx 0,93% confidence 15,0;
TSLAx 1,22% confidence 75,0); 11 ticker ter-skip (tidak ada D —
`dev_vs_median` NULL, termasuk semua ticker 1-pool). Outcome Senin
keduanya terisi "accurate" (aktual NVDAx 0,62%; TSLAx 0,78% — selisih
dari prediksi ≤ 1,0 poin persen, sesuai aturan §2.2). n = 2 — bukan
bukti kalibrasi; yang penting adalah sinyal cakupannya: Monday Gap
akan kosong untuk sebagian besar ticker bila D tidak tersedia.
Idempotensi terverifikasi: jalankan 2× untuk minggu yang sama → tetap
2 baris (bukan duplikat); isi outcome 2× → no-op.

---

## 3. Hasil QA (dijalankan saat penyusunan paket)

### 3.1 Tes repo — `qa/test_coverage_2026-11-12.mjs`
Perintah: `node qa/test_coverage_2026-11-12.mjs` (12 Nov 2026 ±21:00 WITA).
**Hasil: 15 PASS, 0 FAIL — COVERAGE TEST: PASS.**
Yang terliput: 1 grup live Solana-only (13 ticker, 35 pool,
`only_solana_xstocks: true`); flip grup saat Base di-seed (2 grup,
NVDAc muncul); pending list 6 vonis cocok dengan
`PENDING_COVERAGE` di `dashboard/logic.py`; tidak ada `SELECT *` di
`worker.js`; tidak ada `COUNT(*)` atas `snapshots` / `deviations` /
`perp_snapshots` / `liquidation_watch`.

### 3.2 Harness scratch — `/tmp/test_penambahan.py` (BUKAN file repo)
Harness builder (lokal sqlite + baca live Hyperliquid publik saja;
tidak ada tulis ke Turso live). Dijalankan 2× saat penyusunan paket,
hasil sama.
**Hasil: 84 PASS, 0 FAIL.**
Yang terliput: fungsi murni `exit_score_v1` (total penuh 54,2/100;
parsial 1 komponen → 25/25 = 100,0 parsial; tanpa komponen → None;
caps; batas redemption; funding 0,0001 → 0,0 / 0,001 → 15,0;
bobot jumlah 100), `monday_gap_predict` (dasar 1,04/75,0 'Tinggi';
tanda berlawanan; cap kalibrasi; clamp ±10; bobot jumlah 100),
`liquidation_status` (batas divergensi 1,0/3,0; jarak 5,0/10,0;
lag 120/600 — diuji sebagai parameter, bukan dari API),
`run_cycle_perp` live (10 baris, funding terisi semua, tanpa
SPY/QQQ/GLD), `run_hourly_liquidation` live (10 baris, liq/distance
selalu NULL, source `hyperliquid-info`), `run_weekly_monday_gap`
(lihat §2 di atas), migrasi di sqlite lokal (ALTER 2×, 3 tabel +
indeks), INSERT `deviations` 14 kolom (roundtrip exit_score 54,2),
median depth 7 hari (dry-run), guard anti full-scan atas `poller.py`
(tidak ada `SELECT *` / `COUNT(*)` atas 4 tabel besar).

**Catatan kejujuran:** harness ini scratch di `/tmp` (ephemeral,
bukan file repo, tidak di-commit). DeepSeek boleh memakainya sebagai
bukti builder, bukan sebagai guard QA repo — guard repo yang baru
hanya `qa/test_coverage_2026-11-12.mjs` (§3.1). Guard QA baru §5.4
desain (8 butir) sebagian besar belum ada di repo (lihat
`DIFF_RINGKAS.md` §4 D7).

### 3.3 Kompilasi
`python3 -m py_compile poller.py seed_multichain.py
verify_multichain.py check_elysium_weekly.py` — **OK** (12 Nov 2026
±21:00 WITA).

### 3.4 Yang BELUM diuji / tidak ada hasilnya saat paket disusun
- **Forward test** (§2 di atas) — belum ada.
- **QA guard §5.4 desain butir 1, 2, 3, 5, 6, 7, 8** — tidak ada file
  tesnya di repo (bobot=100, ambang 0,99/1,00 & 69/70, idempotensi
  migrasi di repo, gate multichain, 1-baris/minggu di repo, bahasa,
  retensi perp). Hanya butir 4 (anti full-scan) yang terliput.
- **Tes web/Next.js** — tidak ada hasil build/test web di paket ini;
  tidak dijalankan saat penyusunan (di luar skop penyusun paket).
- **`qa_harness.py`, `qa_post_fix.py`, `tests_fase2/`** (guard lama) —
  tidak dijalankan ulang saat penyusunan paket; desain memerintahkan
  semuanya wajib tetap lolos, tetapi tidak ada bukti run terbaru di
  paket ini. Chief/DeepSeek harus meminta bukti run sebelum deploy.
- **Migrasi ke Turso live** — belum dijalankan (butuh ACC); yang
  teruji hanya migrasi di sqlite lokal (§3.2).
- **Seed live** — belum dijalankan (butuh ACC); yang teruji hanya
  dry-run (30 ticker / 115 pool, exit 0) + penolakan `--live` tanpa
  ACC (exit 2) + read-back 0 baris baru.

---

## 4. Angka Turso sebelum/sesudah

Sumber: `turso_usage_check.py` (Platform API, 0 rows_read) + dokumen
kuota. "Sesudah" di sini = sesudah build selesai, SEBELUM migrasi/
seed/deploy apa pun (belum ada yang live).

| Waktu cek | Reads kumulatif | Writes kumulatif | Storage | Keterangan |
|---|---|---|---|---|
| 12 Nov 2026 20:23 WITA (dokumen kuota) | 63.541.222 (12,7% dari 500J) | 801.650 (8,0% dari 10J) | 76,3 MB | Baseline desain §6; rate reads ~1.100–1.200/mnt; proyeksi rate-basis ~52J/bln; proyeksi kumulatif 165,5J (tercemar spike 9 Nov +10,57J dalam 1 hari) |
| 12 Nov 2026 ±21:00 WITA (saat paket disusun) | **70.944.094 (14,2%)** | **802.722 (8,0%)** | **76,4 MB** | verdict=OK (basis=cumul); delta sejak cek terakhir **+7.402.872 reads**, rate 208.541/mnt, proyeksi 184,4J |

**Dua hal yang harus dibaca dari angka "sesudah":**
1. **Writes nyaris datar (+1.072)** — konsisten dengan fakta bahwa
   tidak ada seed/migrasi/poller baru yang live. Tidak ada bukti
   penambahan ini sudah menulis apa pun ke Turso.
2. **Reads melonjak +7,40J dalam ±35 menit (rate 208.541/mnt)** —
   **penyebabnya belum diidentifikasi saat paket disusun.**
   Bukan dari backtest (±220 rb rows) dan bukan dari
   `turso_usage_check.py` sendiri (Platform API, 0 reads). Chief perlu
   mengecek `usage-api-log.md` / `logs/poller-cron.log` sebelum
   menyimpulkan apa pun. Angka ini dicatat apa adanya di sini —
   **bukan** untuk dipakai DeepSeek sebagai bukti beban penambahan
   (penambahan belum live), melainkan sebagai pertanyaan terbuka soal
   kesehatan kuota (lihat `PERTANYAAN_TERBUKA.md` Q12).

**Proyeksi yang berlaku (dari `KUOTA_PENAMBAHAN_2026-11-12.md`,
laju aktual 11–12 Nov):** baseline writes 1,95J/bln (19,5%), reads
~51,8J/bln (10,4%). Skenario: (a) 5 fitur saja → 2,31J (23,1%) AMAN;
(a)+(b) +Base → 3,81J (38,1%) AMAN; (a)+(b)+(c) +BNB top 13 → 5,32J
(53,2%) AMAN BERSYARAT (retensi 30 hari + agregasi hourly terbukti
jalan dulu; checkpoint hari 2/4/7); (d) penuh → 42,3J (423%) JEBOL.
Storage naik 4,7 MB/hari (38,8 MB 4 Nov → 76,3 MB 12 Nov) — retensi/
agregasi §2.2 **belum terbukti menahan laju ini**; wajib dicek sebelum
tambah chain.
