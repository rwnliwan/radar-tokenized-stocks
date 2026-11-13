# Kuota Turso — Penambahan 5 Fitur + Multi-Chain (Base, BNB)

**Tanggal cek:** 2026-11-12 20:23 WITA (via `turso_usage_check.py`, Platform API — tanpa query DB, 0 reads)
**Repo:** `~/workspace/radar-tokenized-stocks`
**Acuan skill:** `quota_burn_budgeting` — hitung burn dulu (scan × frekuensi × pertumbuhan), jangan klaim aman tanpa hitungan tertulis. Ambang aksi **80%** limit: bila proyeksi >80%, mitigasi dimulai sekarang, bukan saat blokir mendarat.

---

## 1. Angka Turso saat ini (2026-11-12 20:23 WITA)

| Dimensi | Aktual | Limit free tier | % limit |
|---|---|---|---|
| Rows read (kumulatif Nov) | **63.541.222** | 500.000.000 | **12,7%** |
| Rows written (kumulatif Nov) | **801.650** | 10.000.000 | **8,0%** |
| Storage | **76,3 MB** | ~9 GB (perlu verifikasi dashboard) | ~0,8% |
| Rate reads | ~1.100–1.200/mnt (cek 19:30 & 19:54) | — | — |
| Proyeksi reads bulanan | **~52J rate-basis** / 165,5J kumulatif | 500J | **~10% / 33%** |
| Verdict script | **OK** (basis=cumul) | | |

**Catatan penting soal dua proyeksi reads yang berbeda:**

- **Kumulatif 165,5J** = 63,5J ÷ 11,85 hari × 30. Angka ini **tercemar spike 9 Nov** (log: +10,57J reads dalam 1 hari, rate 7.336/mnt — legacy query; lihat `usage-api-log.md` 2026-11-09 09:56). Bukan laju berjalan.
- **Rate-basis ~52J** = ~1.200/mnt × 43.200 mnt/bln. Ini laju berjalan 11–12 Nov (proyeksi rate di log: 46,7J pada 19:30; 55,6J pada 09:56). **Ini angka yang dipakai sebagai baseline di bawah** — sesuai skill: laju aktual adalah kebenaran, bukan proyeksi kumulatif yang tercemar spike.
- Delta cek 20:23 = 0 karena cek identik sudah jalan menit sebelumnya (angka sama persis 63.541.222) — bukan laju nol.

### Baseline berjalan (laju aktual, 11–12 Nov)

- **Writes:** 11 Nov 09:56 → 12 Nov 09:56 = 703.821 → 776.684 = **72.863/hari**; 12 Nov 09:56 → 19:30 = 776.684 → 799.277 = 22.593 / 9,57 jam ≈ **56.700/hari**. Rata-rata pakai **65.000/hari** → **1.950.000/bln = 19,5% limit writes**.
- **Reads:** ~1.200/mnt → 1.728.000/hari → **~51,8J/bln = 10,4% limit reads**.
- **Storage:** 38,8 MB (4 Nov) → 76,3 MB (12 Nov) = +37,5 MB / 8 hari = **4,7 MB/hari → +141 MB/bln → ~217 MB akhir Nov**. Naik linear — retensi/agregasi §2.2 (snapshots mentah 30 hari → hourly) **belum terbukti menahan laju ini**; wajib dicek sebelum tambah chain.

### Fakta ground-truth dari poller live (bukan asumsi)

- `logs/poller-cron.log` 12 Nov: tiap siklus 5-menit menulis **`snapshots=35, deviations=13`** → universe saat ini **13 ticker, 35 pool aktif Solana** (cocok dengan `state.json`: 13 underlying `last_mint_supply`).
- Siklus: 288/hari baseline (5 menit, 24/7). Jendela rapat 1-menit (§2.2: +480 siklus/hari kerja) **belum dihitung di skenario bawah** — semua hitungan memakai baseline 288 saja; bila jendela rapat diaktifkan untuk chain baru, kalikan lagi.

### Konvensi hitungan (bisa diulang)

- **Pengali indeks tulis (M):** 1 baris INSERT dihitung Turso lebih dari 1 unit tulis karena indeks. Desain §2.2 memakai **3×** untuk `snapshots` (PK + 2 indeks). Dipakai di sini: **M=3** untuk tabel snapshot-style (PK + ≥2 indeks), **M=2** untuk tabel kecil (PK + 1 indeks `(ticker_id, ts)` atau sejenis). Ini konservatif dan konsisten dengan §2.2.
- **Ukuran baris:** ~120 byte/baris (asumsi §2.2) untuk hitungan storage.
- **Bulan:** 30 hari. Siklus: 288/hari. Jam: 24/hari.
- **Baseline writes/bln = 1.950.000 (19,5%)** dan **baseline reads/bln = ~51,8J (10,4%)** dipakai di semua skenario — bukan angka desain §2.2 (956rb baris mentah/bln untuk 25 ticker/50 pool), karena laju aktual sudah termasuk semua tabel + pola nyata poller.

---

## 2. Skenario (a) — 5 fitur saja, Solana saja

| Fitur | Rumus | Baris/bln | M | Unit tulis/bln |
|---|---|---|---|---|
| `perp_snapshots` | 13 ticker × 288 siklus/hari × 30 hari | 112.320 | 3 | **336.960** |
| Exit Score | kolom baru di `deviations` — +0 baris | 0 | — | **0** |
| Monday Gap | 13 ticker × 1/hari × 30 hari | 390 | 2 | **780** |
| Liquidation Guard (hourly) | 13 ticker × 24 jam/hari × 30 hari | 9.360 | 2 | **18.720** |
| Bukti nilai (`alert_log`) | ~5 alert/hari × 30 hari (1 insert + 1 update outcome) | 150 | 2 | **300** |
| **Total tambahan (a)** | | | | **≈ 356.760 ≈ 357rb/bln = 3,6% limit** |

- **Total writes proyeksi (baseline + a) = 1.950.000 + 357.000 = 2.307.000/bln = 23,1% dari 10J.** ✅ **AMAN** (jauh di bawah ambang 80% = 8J).
- **Reads:** `perp_snapshots` dibaca latest-only via indeks `(ticker_id, ts)` — 13 baris per muat dashboard. Bahkan 1.000 muat/hari = 13.000 reads/hari = 0,39J/bln (+0,08%). **+0 besar: reads ≈ 52J/bln = 10,4%.** ✅
- **Storage:** perp 112.320 baris × 120 B = **13,5 MB/bln** (steady-state bila retensi 30 hari jalan); Liq Guard 9.360 × 120 B = 1,1 MB/bln (volume kecil, dipertahankan penuh seperti `deviations`/`alert_log` per §2.2). Total +~15 MB/bln. ✅

---

## 3. Skenario (b) — (a) + Base + Coinbase, 13 token

Asumsi (sesuai tugas): total pool baru **~35** (NVDAc ~4–6 pool; rata-rata ~2,7 pool/ticker — sama seperti Solana sekarang: 35 pool / 13 ticker). Satu chain baru = satu salinan pola Solana.

| Tabel | Rumus | Baris/bln | M | Unit tulis/bln |
|---|---|---|---|---|
| `snapshots` | 35 pool × 288 × 30 | 302.400 | 3 | **907.200** |
| `deviations` | 13 ticker × 288 × 30 | 112.320 | 2 | **224.640** |
| `perp_snapshots` | 13 ticker × 288 × 30 | 112.320 | 3 | **336.960** |
| `por_token_snapshots` (hourly) | 13 ticker × 24 × 30 | 9.360 | 2 | **18.720** |
| Monday Gap | 13 × 30 | 390 | 2 | **780** |
| Liquidation Guard | 13 × 24 × 30 | 9.360 | 2 | **18.720** |
| **Total tambahan (b)** | | | | **≈ 1.507.020 ≈ 1,51J/bln = 15,1% limit** |

- **Total writes proyeksi (baseline + a + b) = 1.950.000 + 357.000 + 1.507.000 = 3.814.000/bln = 38,1% dari 10J.** ✅ **AMAN.**
- **Reads:** bacaan latest-only naik proporsional dengan pool yang dibaca dashboard (35 → 70 pool). Asumsi konservatif +50% laju reads → ~78J/bln = **15,6%.** ✅ (Bukan +0 harfiah, tapi tetap kecil karena latest-only via indeks — lihat §6.)
- **Storage:** snapshots +302.400 × 120 B = 36,3 MB/bln + perp 13,5 MB/bln → **+~50 MB/bln steady-state** (dengan retensi 30 hari). ✅

---

## 4. Skenario (c) — (a) + (b) + BNB + bStocks TOP 10–13 saja

Satu chain lagi dengan bentuk yang sama (13 ticker, ~35 pool): tambahan = skenario (b) = **1,51J/bln = 15,1%**.

- **Total writes proyeksi (baseline + a + b + c) = 1.950.000 + 357.000 + 1.507.000 + 1.507.000 = 5.321.000/bln = 53,2% dari 10J.** ✅ **AMAN, dengan syarat** (di bawah ambang 80%, tapi sudah melewati setengah limit).
- **Reads:** asumsi +100% vs baseline (3 chain total) → ~104J/bln = **20,8%.** ✅
- **Storage:** +~50 MB/bln lagi → steady-state total ~+100 MB/bln di atas baseline; proyeksi akhir Nov ~217 MB + pertumbuhan chain baru. ✅ (jauh dari ~9 GB, tapi retensi wajib jalan — lihat §7).

**Syarat wajib sebelum (c) live:**

1. Retensi `snapshots` 30 hari + agregasi `snapshots_hourly` (§2.2) **terbukti jalan** — storage naik 4,7 MB/hari hari ini tanpa bukti agregasi menahan; tambah 2 chain melipatgandakan laju masuk.
2. Checkpoint usage hari ke-2, ke-4, ke-7 setelah chain baru live (`turso_usage_check.py`); bila laju writes aktual memproyeksikan >80% (8J/bln), mitigasi dimulai saat itu juga (turunkan frekuensi perp ke 15 menit, atau bekukan chain ketiga).
3. Semua bacaan dashboard/bot latest-only via indeks (lihat §6) — tidak ada query baru yang memindai `snapshots`.

---

## 5. Skenario (d) — JANGAN: semua 104 bStocks + semua 430 Ondo

Hitungan dengan rumus yang sama (baseline 288 siklus/hari, belum termasuk jendela rapat 1-menit — angka riil lebih besar lagi).

### d1. bStocks — 104 ticker, asumsi 2 pool/ticker = 208 pool

| Tabel | Rumus | Baris/bln | M | Unit tulis/bln |
|---|---|---|---|---|
| `snapshots` | 208 × 288 × 30 | 1.797.120 | 3 | 5.391.360 |
| `deviations` | 104 × 288 × 30 | 898.560 | 2 | 1.797.120 |
| `perp_snapshots` | 104 × 288 × 30 | 898.560 | 3 | 2.695.680 |
| `por_token_snapshots` | 104 × 24 × 30 | 74.880 | 2 | 149.760 |
| **Subtotal bStocks** | | | | **≈ 10.033.920 ≈ 10,0J/bln = 100% limit** |

**bStocks penuh saja sudah menghabiskan 100% limit writes — sebelum baseline dihitung.** Baseline (1,95J) + bStocks (10,03J) = **11,98J = 119,8% → JEBOL.**

### d2. Ondo — 430 produk, asumsi konservatif 1 pool/produk = 430 pool

| Tabel | Rumus | Baris/bln | M | Unit tulis/bln |
|---|---|---|---|---|
| `snapshots` | 430 × 288 × 30 | 3.715.200 | 3 | 11.145.600 |
| `deviations` | 430 × 288 × 30 | 3.715.200 | 2 | 7.430.400 |
| `perp_snapshots` | 430 × 288 × 30 | 3.715.200 | 3 | 11.145.600 |
| `por_token_snapshots` | 430 × 24 × 30 | 309.600 | 2 | 619.200 |
| **Subtotal Ondo** | | | | **≈ 30.340.800 ≈ 30,3J/bln = 303% limit** |

### d. Total

- **Tambahan (d) = 10,03J + 30,34J ≈ 40,4J/bln = 404% limit.**
- **Total proyeksi = 1,95J + 40,4J ≈ 42,3J/bln = 423% dari 10J → JEBOL ~4,2×.** Database terblokir sebelum tengah bulan; semua chain ikut mati.
- **Storage (d):** snapshots 5,5J baris/bln × 120 B = **~663 MB/bln** laju masuk — retensi 30 hari tidak menyelamatkan karena yang jebol duluan adalah writes, bukan storage.
- **Reads (d):** latest-only pun 638 pool × muat dashboard tetap kecil, TAPI satu query agregasi/backtest yang menyentuh `snapshots` tanpa indeks pada 5,5J baris/bulan = puluhan juta reads sekali jalan. Risiko reads justru dari satu kueri ceroboh, bukan dari poller.
- Catatan: asumsi 1 pool/produk Ondo itu konservatif — banyak produk Ondo bahkan tidak punya pool likuid ≥$100rb, jadi angka riil produk yang lolos aturan bisa lebih kecil; tapi **bStocks saja sudah jebol**, jadi skenario penuh gugur tanpa perlu asumsi Ondo yang presisi. Jalan yang benar: TOP 10–13 per issuer (skenario c), bukan semua produk.

---

## 6. Aturan keras — larangan full-scan

Aturan ini berlaku untuk **semua** skenario, dan makin penting tiap kali chain/ticker bertambah:

1. **DILARANG** `COUNT(*)` / `SELECT *` ke `snapshots` (dan `perp_snapshots`, `deviations`) tanpa `WHERE` terindeks + `LIMIT`. Satu `COUNT(*)` full-table pada `snapshots` yang sudah berisi jutaan baris = jutaan reads sekali jalan — itu sendiri bisa membakar proyeksi bulanan.
2. **Butuh jumlah baris?** Pakai angka `rows_written` dari Platform API (`turso_usage_check.py`) sebagai proksi, dan nyatakan itu. Jangan query DB untuk menghitung.
3. **Bacaan dashboard/bot WAJIB latest-only via indeks:** `WHERE pool_id = ? ORDER BY ts DESC LIMIT 1` (memakai `idx_snapshots_pool_ts`) atau `WHERE ticker_id = ? ORDER BY ts DESC LIMIT N` (`idx_deviations_ticker_ts`). Tidak ada `ORDER BY ts` tanpa filter pool/ticker; tidak ada rentang waktu lebar tanpa `LIMIT`.
4. **Backtest/agregasi** hanya dari `snapshots_hourly`/`snapshots_daily` (agregat), bukan dari `snapshots` mentah. Bila butuh hitung ulang dari mentah, jalankan di salinan lokal (arsip `raw/*.json.gz` di VM), bukan di Turso live.
5. **Query baru apa pun** yang menyentuh tabel snapshot wajib diuji dulu di salinan lokal dengan `EXPLAIN` / hitungan rows-scanned tertulis sebelum deploy — sesuai skill: scan × frekuensi × pertumbuhan.

---

## 7. Rekomendasi

| Skenario | Writes/bln | % limit | Reads/bln | Verdict |
|---|---|---|---|---|
| Baseline hari ini | 1,95J | 19,5% | ~52J (10,4%) | OK |
| (a) 5 fitur, Solana saja | 2,31J | **23,1%** | ~52J (10,4%) | ✅ **AMAN — jalan sekarang** |
| (a)+(b) + Base/Coinbase 13 | 3,81J | **38,1%** | ~78J (15,6%) | ✅ **AMAN — jalan setelah (a) stabil** |
| (a)+(b)+(c) + BNB/bStocks TOP 13 | 5,32J | **53,2%** | ~104J (20,8%) | ✅ **AMAN BERSYARAT** — retensi 30 hari + agregasi hourly terbukti jalan dulu; checkpoint hari 2/4/7 |
| (d) 104 bStocks + 430 Ondo penuh | 42,3J | **423%** | — | ❌ **JANGAN — jebol 4,2×; bStocks saja sudah 120%** |

**Urutan yang direkomendasikan:**

1. **(a) sekarang** — 5 fitur Solana saja: +357rb writes/bln (+3,6 poin). Risiko kuota nyaris nol.
2. **(b) setelah (a) stabil 1 minggu** — Base+Coinbase 13 token: total 38,1%. Cek usage hari ke-2/4/7.
3. **(c) hanya bila (1) retensi 30 hari + agregasi `snapshots_hourly` terbukti jalan** (storage hari ini naik 4,7 MB/hari tanpa bukti penahan) **dan (2)** laju aktual (b) sesuai proyeksi. Total 53,2% — masih di bawah ambang aksi 80%, tapi tidak ada ruang untuk chain ke-4 tanpa agregasi/retensi lebih agresif (mis. perp 15-menit, atau snapshots_daily lebih dini).
4. **(d) tidak pernah dalam bentuk penuh.** Bila suatu hari cakupan bStocks/Ondo mau diperluas, jalannya adalah menaikkan TOP-N bertahap (13 → 25 → 50) dengan hitungan ulang per kenaikan, atau memindahkan snapshot mentah ke storage murah (arsip VM / R2) dan hanya menyimpan agregat di Turso.

**Ambang aksi 80% (8J writes / 400J reads):** bila proyeksi rate-basis melewati 80% di checkpoint mana pun, mitigasi dimulai hari itu juga — urutan mitigasi: (1) turunkan frekuensi `perp_snapshots` 5 → 15 menit (hemat ~224rb/bln per chain), (2) bekukan chain terbaru, (3) percepat agregasi + hapus mentah lebih dini. Jangan tunggu blokir.

---

## 8. Jejak verifikasi

- Cek Platform API: `python3 turso_usage_check.py` 2026-11-12 20:23 WITA → `verdict=OK (basis=cumul)`, reads=63.541.222 (12,7%), written=801.650 (8,0%), storage=76,3 MB, proyeksi kumulatif 165,5J (tercemar spike 9 Nov — lihat §1). Log lengkap: `~/workspace/goals/radar-tokenized-stocks-kabar-berkala/hidden_files/usage-api-log.md`.
- Ground-truth poller: `logs/poller-cron.log` 12 Nov — `snapshots=35, deviations=13` per siklus 5-menit.
- Desain acuan: `~/workspace/research_notes/radar-rwa-flagship-20261024/DESAIN_TEKNIS_TAHAP1_DRAF.md` §2.2 (50 pool → 956rb baris mentah/bln, pengali indeks 3×) dan §3.1 (jadwal polling).
- Tidak ada tulis ke Turso, tidak ada perubahan poller/dashboard, tidak ada deploy dalam penyusunan file ini. Jumlah baris tidak dihitung via `COUNT(*)` — memakai proksi `rows_written` Platform API + log poller.

---

## 9. Revisi 13 Nov 2026 — koreksi siklus 288 -> 356/hari (S12 + Q5, terverifikasi Chief)

Temuan S12 BENAR: ketiga dokumen (DESAIN §6, dokumen ini, SEED §4)
memakai 288 siklus/hari, padahal ground truth ~356 siklus/hari
(6.079 siklus / 17,2 hari, HASIL_TEST.md §1.1). Semua estimasi
understate ~23,6%. Revisi ini menghitung ulang dengan angka yang sama
di dokumen ini — tabel §2–§5 di atas TIDAK diedit diam-diam; angka
koreksi yang berlaku ada di sini.

### Metode (bisa diikuti ulang)

- **Faktor koreksi: 356/288 = 1,2361.** Catatan ketelitian: 6.079/17,2
  = 353,4 (bukan persis 356) — 356 adalah angka yang dipakai review,
  sedikit membulat ke atas; memakai 353,4 memberi faktor 1,227 dan
  tidak mengubah satu vonis pun di bawah ini.
- **Baseline TIDAK dikali faktor.** Baseline dokumen ini (1,95 jt/bln)
  dan baseline DESAIN (1,3 jt/bln) adalah UKURAN laju tulis aktual
  (writes/hari dari dashboard Turso), bukan hitungan dari 288 — laju
  itu sudah mengandung siklus 356/hari. Mengalinya lagi dengan 1,236
  adalah double-counting (dan justru itulah yang menghasilkan angka
  "4,7" yang keliru bila diterapkan ke total — lihat jawaban Q5).
- **Yang dikali faktor hanya tambahan yang diturunkan dari siklus:**
  snapshots, deviations, perp_snapshots (per siklus 5 menit).
  Yang TIDAK dikali: liquidation guard, por_token_snapshots (per jam),
  monday_gap (per minggu), alert_log (per kejadian) — semuanya
  dihitung ulang dari rumusnya, bukan dari faktor kasar.
- Pengali indeks M dan asumsi lain (pool/ticker per skenario) TIDAK
  diubah — koreksi ini hanya soal jumlah siklus.

### Angka koreksi per skenario (dokumen ini, asumsi sama, 356 siklus/hari)

| Skenario | Tambahan dikoreksi | Total dikoreksi | Dulu (288) | Vonis |
|---|---|---|---|---|
| (a) 5 fitur, Solana saja | 436.320/bln (0,44 jt) | **2,39 jt/bln (23,9%)** | 2,31 jt (23,1%) | ✅ AMAN |
| (a)+(b) + Base/Coinbase 13 | 1.853.820/bln (1,85 jt) | **4,24 jt/bln (42,4%)** | 3,81 jt (38,1%) | ✅ AMAN |
| (a)+(b)+(c) + BNB/bStocks TOP 13 | 1.853.820/bln (1,85 jt) | **6,09 jt/bln (60,9%)** | 5,32 jt (53,2%) | ✅ AMAN BERSYARAT |
| (d) 104 bStocks + 430 Ondo penuh | 49.726.080/bln (49,73 jt) | **51,68 jt/bln (516,8%)** | 42,3 jt (423%) | ❌ JANGAN |

Perhitungan (a): perp 13×356×30 = 138.840 baris ×3 = 416.520;
monday gap 13×30×2 = 780; liq 13×24×30×2 = 18.720; alert_log
150×2 = 300; total 436.320. Perhitungan (b): snapshots
35×356×30 = 373.800 ×3 = 1.121.400; deviations 13×356×30 =
138.840 ×2 = 277.680; perp 138.840 ×3 = 416.520; por
13×24×30×2 = 18.720; monday gap 780; liq 18.720; total 1.853.820.
Skenario (c) = (b) (satu chain lagi bentuk sama). Skenario (d):
bStocks 12.367.680 + Ondo 37.358.400 = 49.726.080.

**Vonis tidak berubah, margin menipis.** Semua skenario yang tadinya
AMAN tetap di bawah ambang aksi 80% (8 jt/bln); (d) tetap JEBOL.
Tetapi (c) kini 60,9% — hanya 19,1 poin di bawah ambang aksi,
bukan 26,8 poin seperti diklaim semula. Syarat (c) — retensi 30 hari
+ agregasi hourly TERBUKTI jalan — tetap berlaku dan tetap BELUM
terpenuhi (storage naik 4,7 MB/hari tanpa bukti agregasi menahan,
HASIL_TEST.md §4); (c) tidak boleh live sebelum syarat itu terbukti.

### Koreksi DESAIN §6.2 (angka yang sama, 356 siklus/hari)

Tambahan DESAIN (Base 32 pool + BNB 27 pool + deviations 24 ticker +
perp 10 ticker + liq): 1.025.280 + 865.080 + 512.640 + 213.600 +
18.720 = 2.636.100 ≈ **2,64 jt/bln** (dulu 2,1 jt). Total dengan
baseline DESAIN sendiri (1,3 jt): **3,94 jt/bln (39,4%)** (dulu
3,4 jt / 34%). Dengan baseline laju aktual (1,95 jt): **4,59 jt/bln
(45,9%)**.

### Jawaban Q5 (review/PERTANYAAN_TERBUKA.md) — hitung ulang

**Mengapa tiga dokumen berbeda? Bukan satu kesalahan hitung, melainkan
tiga perbedaan asumsi yang menumpuk:**

1. **Jumlah pool/ticker:** DESAIN §6.2 mengasumsikan 59 pool / 24
   ticker (Base 32 + BNB 27); dokumen ini mengasumsikan 70 pool / 26
   ticker (35 + 35); SEED §4 memakai realita 115 pool / 30 ticker
   (Robinhood rata-rata 5,8 pool/ticker).
2. **Baseline:** DESAIN 1,3 jt/bln (rata-rata kumulatif 19 hari,
   termasuk 44 jam outage 30 Okt–1 Nov — stale/rendah) vs dokumen
   ini 1,95 jt/bln (laju aktual 11–12 Nov — benar untuk saat ini).
3. **Cakupan:** SEED §4 TIDAK memasukkan 5 fitur (hanya
   snapshots+deviations multichain); DESAIN/dokumen ini memasukkan
   5 fitur; dokumen ini TIDAK memasukkan Robinhood (chain ke-4 —
   tidak ada di skenario (a)/(b)/(c)).

**Angka benar per skenario (hitung ulang saya, langkah di atas):**

- (a)+(b)+(c) seperti didefinisikan dokumen ini (Base+BNB, 70 pool /
  26 ticker): **6,09 jt/bln (60,9%)** — bukan 5,32. Tetap AMAN
  BERSYARAT.
- (a)+(b)+(c) dengan jumlah pool REAL Base+BNB dari SEED (§4:
  115 pool total − Robinhood ±75 pool = ±40 pool / 17 ticker):
  tambahan (b)+(c) = 1.694.700; total **4,08 jt/bln (40,8%)** —
  lebih murah dari estimasi dokumen ini, karena realita Base+BNB
  hanya ±40 pool, bukan 70.
- **SEED §4 (30 ticker / 115 pool, tanpa 5 fitur):** tambahan
  4.325.400 (snapshots 115×356×30×3 = 3.684.600 + deviations
  30×356×30×2 = 640.800); total dengan baseline SEED sendiri (1,3):
  **5,63 jt/bln (56,3%)** — bukan 4,8 jt (48%); dengan baseline
  laju aktual (1,95): **6,28 jt/bln (62,8%)**.
- **Cakupan penuh yang sebenarnya (5 fitur + 30 ticker / 115 pool
  semua issuer):** baseline 1,95 + (a) 0,44 + multichain 4,41 =
  **6,80 jt/bln (68,0%)** — masih di bawah 80%, tetapi margin hanya
  12 poin. Inilah angka yang harus dipakai untuk keputusan deploy
  multichain penuh, bukan 4,8 jt SEED.

**Tentang angka "≈4,7 jt/bln" di review:** angka itu DAPAT
direkonstruksi, tetapi bukan dari skenario SEED — melainkan dari
skenario struktur DESAIN (59 pool / 24 ticker) + baseline laju
aktual 1,95 + perp M=3 (konvensi dokumen ini): tambahan 2.742.120
(1.025.280 + 865.080 + 512.640 + 320.400 + 18.720); total
1,95 + 2,74 = **4,69 jt/bln ≈ 4,7 (46,9%)**. Jadi "SEED §4 paling
dekat" benar secara numerik (4,8 vs 4,7), tetapi perbandingannya
apel-dengan-jeruk: 4,7 memakai asumsi pool DESAIN (59), sementara
SEED §4 memakai pool realita (115) — dengan pool realita, total
yang benar adalah 5,63–6,28 jt (tanpa 5 fitur) atau 6,80 jt
(dengan 5 fitur). Review tidak salah arah — hanya angka
pembandingnya memakai struktur yang berbeda; koreksi ini yang
berlaku.

**Apakah (c) masih "AMAN BERSYARAT"?** Ya — di semua varian
hitungan ulang (40,8%–68,0%) masih di bawah ambang aksi 80%.
Tetapi syaratnya (retensi + agregasi terbukti) BELUM terpenuhi,
dan pada cakupan penuh margin hanya 12 poin: satu spike seperti
9 Nov (+10,57 jt reads/hari — sisi reads, bukan writes) atau
satu query ceroboh sudah cukup untuk memakan margin itu. (c)
tetap jalan hanya setelah checkpoint hari 2/4/7 membuktikan laju
aktual sesuai proyeksi.

**Apakah opsi hemat `--max-pools-per-ticker 3` (71 pool) lebih tepat
sebagai default?** Ya. Hitung ulang 356 siklus: tambahan
2.915.640 (snapshots 71×356×30×3 = 2.274.840 + deviations
30×356×30×2 = 640.800); total **4,22 jt/bln (42,2%)** dengan
baseline 1,3, atau **4,87 jt/bln (48,7%)** dengan baseline 1,95 —
vs 5,63/6,28 jt untuk 115 pool penuh. Hemat ±1,4 jt/bln (±14 poin
limit) dengan mengorbankan 44 pool tipis. Rekomendasi: default seed
71 pool; naikkan ke 115 hanya bila checkpoint membuktikan laju
aktual sesuai proyeksi.

Catatan kecil: hitungan (a) di atas memakai 13 ticker untuk perp
(mengikuti asumsi dokumen ini); hanya 10 ticker yang punya perp
XYZ — memakai 10 ticker menurunkan (a) sebesar ±0,10 jt/bln
(96.120 writes). Tidak material; dicatat agar tidak dikira
kesalahan hitung bila ada yang menghitung ulang dengan 10.
