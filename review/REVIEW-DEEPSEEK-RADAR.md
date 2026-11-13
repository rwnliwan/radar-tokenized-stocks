# REVIEW DEEPSEEK RADAR — Penambahan 12 Nov 2026
# Laporan gabungan + VERIFIKASI INDUK (Chief)
# Dibuat: 13 Nov 2026 ~01:05 WITA. Mentah:
#   ~/workspace/radar-tokenized-stocks/review/review_deepseek_radar_raw.txt
#   (dikirim oleh agen stream Radar, temp 0,2, max-tokens 12000)

## Vonis DeepSeek: skor 5/10 — REVISE (tanpa rollback)
- (a) rumus & ambang 5 | (b) skema & migrasi 6 | (c) kuota & performa 4 |
  (d) kejujuran web/banner 5 | (e) testing & bukti 4
- Total: **13 MUST-FIX / 14 SHOULD-FIX / 5 NIT = 32 temuan**

## Hasil verifikasi induk (Chief) — 31/32 BENAR, 1 noise
Semua temuan dicek ke sumber: grep kode + skema, hitung ulang, cek live
(Worker API, Turso live, /api/coverage). Satu temuan TIDAK terverifikasi
(S3 — kutipan komentar salah).

### MUST-FIX — semua BENAR
- **M1 BENAR (LIVE)** — `api/worker.js:1129,1137` regex `^[A-Z0-9]+X$`.
  Cek live: `TSLAr` → HTTP 400, `NVDAc` → HTTP 400, `TSLAx` → HTTP 200.
  30/43 ticker (semua non-X: c/B/r) mengembalikan 400.
- **M2 BENAR** — `poller.py:1116` `mon_open = ...13:30:00Z` hardcode.
  DST AS 2026 berakhir 1 Nov; NYSE buka 16 Nov (EST) = 14:30 UTC.
  Prediksi pertama 16 Nov akan mengambil harga ~08:30 ET (1 jam sebelum open).
- **M3 BENAR** — `poller.py:1035` `COUNT(*)` baris (bukan akhir pekan),
  `:723` `calib = 5*min(calibrated,5)`. Dengan 43 ticker, 1 akhir pekan →
  s.d. 43 baris → calib = 25 (maks) setelah SATU akhir pekan. Seharusnya
  `COUNT(DISTINCT week_start)`.
- **M4 BENAR (LIVE)** — `poller.py:751` `_latest_redemption_status`:
  `SELECT status FROM redemption_windows ORDER BY observed_at DESC LIMIT 1`
  tanpa `WHERE issuer`. Cek live: baris terbaru = xStocks 'open'
  (16:46 UTC); bstocks 'unknown' 13:42. Artinya SEMUA ticker (termasuk
  NVDAc/TSLAB/TSLAr yang status sebenarnya 'unknown') memakai status
  redemption xStocks.
- **M5 BENAR (kode; nuansa live)** — `components_present` dihitung di
  `poller.py:689` tapi TIDAK ditulis; `schema.sql` deviations hanya punya
  `exit_score` + `exit_score_version`. Desain §2.3 mewajibkan komponen
  disimpan/ditampilkan. Nuansa: cek live 0 baris exit_score ≥ 99,9 — kasus
  skor parsial 100,0 (harness) BELUM terjadi live. Fix tetap wajib.
- **M6 BENAR** — `poller.py:665-668` ambang 0,01%/0,10% dipakai pada rate
  HOURLY apa adanya (komentar kode sendiri mengakui hourly). Ambang desain
  per-8-jam setara 0,00125%/0,0125% per jam → komponen praktis selalu 0.
  Perlu revisi tertulis bertanggal (bukan penalaan diam-diam).
- **M7 BENAR (mekanisme)** — `schema.sql`: TIDAK ada indeks pada
  `poller_health`; `poller.py` cek idempotensi `COUNT(*) ... WHERE
  cycle_ts = ?` tiap siklus = full scan. Row count live: 6.183 (DeepSeek
  pakai 6.079 — sudah tumbuh). Angka reads (65 jt/bln) adalah estimasi
  orde-besar, bukan hitung pasti.
- **M8 BENAR (mekanisme)** — `schema.sql` hanya
  `idx_deviations_ticker_ts`; TIDAK ada indeks `(ts)`. Query `ORDER BY ts
  DESC` tanpa WHERE (worker `loadLatest`, dashboard) = scan + sort.
  Deviations live: 79.964 baris (DeepSeek pakai 76.767).
- **M9 BENAR** — `seed_multichain.py:125-126` `DELETE FROM pools/universe
  WHERE ticker_id = ?` (plus :169 redemption_windows). Re-seed mingguan
  akan menghapus/mengyatimkan riwayat.
- **M10 BENAR** — tidak ada startup guard (tidak ada `PRAGMA
  table_info`/`sqlite_master` di `poller.py::main()`); hanya komentar
  di header migrasi. Inilah penyebab P0 12 Nov (20:46–21:21).
- **M11 BENAR** — `web/src/app/ticker/[id]/page.tsx:428` dan
  `dashboard/app.py:1760` hardcode `dexscreener.com/solana/`; 71/106 pool
  bukan Solana (67% link salah chain).
- **M12 BENAR (LIVE)** — `/api/coverage` mengembalikan live
  (base/coinbase 9, bsc/bstocks 8, robinhood 13, solana/xstocks 13) DAN
  pending untuk chain yang SAMA (base/bnb/robinhood "verified"). Dua tabel
  saling menyangkal, live.
- **M13 BENAR — KEPUTUSAN SEPTIAN, bukan fix kode** — `CHECKLIST_QA.md`
  F5: "BELUM DILAKUKAN". ToS DexScreener belum dibaca; display publik
  chain baru sudah tayang. Koordinator fix TIDAK memutuskan ini; masuk
  .md untuk Instinct + laporan ke Septian sebagai keputusan terbuka.

### SHOULD-FIX — 13/14 BENAR, 1 noise
- **S1 BENAR** — migrasi: dua `ALTER TABLE deviations ADD COLUMN`
  telanjang (hanya komentar "Run ONLY if PRAGMA..."); jalan kedua →
  `duplicate column name`.
- **S2 BENAR** — `poller.py:592` fallback mark→mid tanpa penanda baris
  (`perp_px` didokumentasikan sebagai mark).
- **S3 NOISE (tidak terverifikasi)** — DeepSeek mengutip komentar
  `schema.sql`: `funding REAL, -- funding rate per interval 8 jam`.
  Komentar itu TIDAK ADA: `schema.sql:87` hanya `funding REAL,` tanpa
  komentar; migrasi sama. JANGAN perbaiki S3 terpisah; substansi
  kebingungan satuan ditangani M6.
- **S4 BENAR** — `poller.py:943` `liquidation_status(div, None, None)`:
  lag selalu None; ambang 120/600 detik inert; perlu revisi desain
  bertanggal + kalimat web.
- **S5 BENAR** — `dashboard/app.py:439-447` `get_venues_live` memakai
  `WHERE ts = (SELECT MAX(ts) FROM snapshots)` global (Worker sudah
  perbaiki pola ini).
- **S6 BENAR** — `run_hourly_liquidation`: early `return frag` (sebelum
  `:968` `state["liquidation_alert_tickers"] = alert_now`) membuat state
  lama bertahan.
- **S7 BENAR** — `poller.py:1169` `wd == 6 and hour >= 22`; bila poller
  mati di jendela itu minggu hilang tanpa catatan; `:1100-1101`
  fill_outcomes membaca SEMUA pending tanpa batas umur.
- **S8 BENAR** — `poller.py:619-620` `closed → 20.0`: komponen redemption
  konstan 20 sepanjang akhir pekan (tidak mendiskriminasi).
- **S9 BENAR** — `qa/test_coverage_2026-11-12.mjs:139` hanya grep 4 tabel;
  full-scan `poller_health` (M7) + `deviations` (M8) lolos.
- **S10 BENAR** — harness `/tmp/test_penambahan.py` (HASIL_TEST.md
  :133/:159) BUKAN file repo; `qa/test_penambahan_2026-11-12.py` tidak ada.
- **S11 BENAR** — `BACKTEST_ALERT_2026-11-12.md:16,117`: 37 event semua
  tipe `spread` hari kerja; `deviation_high` = 0; tidak ada backtest
  `perp_deviation`/`exit_high`/akhir pekan.
- **S12 BENAR** — ketiga dokumen memakai 288 siklus/hari (DESAIN :617/:651,
  KUOTA :35/:41/:50); ground truth ~356 siklus/hari (6.079 siklus /
  17,2 hari). Semua estimasi understate ~23,6%.
- **S13 BENAR** — `seed_multichain.py:171-172` INSERT
  redemption_windows tanpa kolom `window_note_en` (pengguna EN tidak
  melihat catatan untuk 3 issuer baru).
- **S14 BENAR** — `poller.py:788,1692` `_oi_24h_ago` = 1 round-trip per
  ticker per siklus, serial (10 ticker × 356 siklus = 3.560/hari).

### NIT
- **N1 BENAR (sebagian)** — band 40/70 diduplikasi di `dashboard/risk.py
  :112` dan `web/src/lib/risk.ts:81` (tanpa fixture bersama). Kaki ketiga
  (bot.py ambang 70) TIDAK terkonfirmasi — grep `exit_high|exit_score.*70`
  di `bot.py` = 0 hasil; sejalan dengan Q13 (jalur alert F1/F3 belum
  terbukti ada di bot.py). Fix: fixture bersama untuk 2 implementasi band.
- **N2 BENAR** — `dashboard/app.py:1847` hitung `_dev_pt` dari `perp_px`
  tanpa gate kesegaran 15 menit (poller menyaring, UI tidak).
- **N3 BENAR** — `refresh_median_depth_7d(state, cycle_dt, tickers)`:
  hanya ticker yang ada di siklus itu; ticker absen memakai median lama
  tanpa batas umur.
- **N4 BENAR** — `monday_gap.outcome TEXT` tanpa CHECK (schema.sql).
- **N5 TERJAWAB, tidak perlu fix** — string `coverage_live_line` ADA di
  `dashboard/i18n.py:181,503` dan `web/src/lib/i18n.ts:69,359`, isinya
  generik ("Live today: DEX deviation, schedule-derived redemption
  status, and hourly proof-of-reserve token snapshots. Vs-close is not
  yet available.") — tidak menyebut Solana, tidak salah; info chain
  dibawa baris dinamis. Tidak ada perbaikan.

### Jawaban Q1–Q14 (verifikasi Chief atas jawaban DeepSeek)
Q1 funding: benar (per-interval hourly; ambang 8× terlalu ketat → M6).
Q2 oracle lag: benar (guard v1 = divergensi saja). Q3 duplikasi Exit
Score: benar (bukan duplikasi berbahaya). Q4 sufiks `r`: benar
(pertahankan `r`; regex M1 dulu). Q5 kuota: benar arahnya (SEED §4
paling dekat; angka benar ≈4,7 jt/bln perlu hitung ulang koordinator
dengan 356 siklus). Q6 TSLAon 10×: pola konsisten (5,01+1,89 vs
0,50+0,19) — plausibel salah-desimal; vonis GAGAL tetap (venue).
Q7 CRCLc: benar (verifikasi satu tarikan tidak cukup). Q8 communityV3:
benar (factory klon, owner 0x0). Q9 turnover: benar (flag, bukan gate).
Q10 lisensi: tidak bisa dijawab dari data ini — M13 (keputusan Septian).
Q11 metodologi web: benar (tidak ada seksi monday_gap_v1/liq_guard_v1).
Q12 burst +14,19 jt: hipotesis (Refresh dashboard clear semua cache)
masuk akal; fix mekanis M7/M8/S9; atribusi pasti butuh cek usage log.
Q13 F1/F3 alert & poller multichain: benar (D5 selesai; D4 bot.py tidak
terbukti — bot.py tidak ada di paket review). Q14 Monday Gap 2/13:
benar (hanya ticker ≥2 pool; realistis 2–5 prediksi/minggu, bukan ~26).

### Urutan perbaikan (DeepSeek, disetujui Chief)
1. M1 (regex) — 3 baris, membuka 30 halaman ticker rusak.
2. M4 + M2 + M3 — tiga perbaikan satu baris (pre-registered).
3. M5 (kolom `exit_score_components` + gate band/alert) — migrasi baru.
4. M7/M8 (dua indeks) + S9 (guard EXPLAIN QUERY PLAN).
5. M9 (seed UPSERT) — cegah kehilangan riwayat re-verify mingguan.
6. M10 (startup guard) + S1 (migrasi re-runnable).
7. M11 (link chain) + M12 (filter pending).
8. M6 + S4 — revisi desain bertanggal (keputusan Chief + Septian).
9. M13 — keputusan Septian (TIDAK diputuskan koordinator).
10. S10/S11 (harness → repo; pernyataan forward-only).
S2, S5, S6, S7, S8, S13, S14, N1–N4 ikut ronde yang sama.
S3 TIDAK diperbaiki (noise). N5 tidak perlu perbaikan.
Empat berdampak pengguna (M1/M11/M12/M5) didahulukan sebelum 16 Nov.
