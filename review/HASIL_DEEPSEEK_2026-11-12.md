# Hasil Review DeepSeek — Penambahan Radar 12 Nov 2026 + Verifikasi Chief

**Tanggal kirim:** 13 Nov 2026 ~00:00 WITA (kirim ulang; pengiriman pertama 12 Nov 23:14 WITA mati kena restart VM)
**Tanggal review kembali:** 13 Nov 2026 ~00:05 WITA
**Model:** `deepseek-v4.1-flash` via Kelontong AI (`custom.kelontong`), temp 0,2, max-tokens 12000, streaming
**Prompt:** `review/review_radar_deepseek_prompt.txt` (601.107 byte, ~150 ribu token estimasi)
**Output mentah:** `review/review_deepseek_radar_raw.txt` (41.393 byte, 357 baris) — durasi panggilan ±206 detik, EXIT=0
**Koin:** sisa 38,9 coin per cek Septian sendiri 23:57 WITA 12 Nov (sebelum pengiriman ini). Biaya pengiriman ini **tidak dapat diketahui** — helper tidak punya endpoint cek saldo dan respons streaming tidak melaporkan usage. Satu pengiriman saja; panggilan duplikat dari induk sempat jalan bersamaan dan dimatikan (PID 3497) supaya tidak bakar koin 2×.
**Aturan:** Chief (induk) arbiter akhir. Temuan di bawah ini sudah diverifikasi satu per satu ke sumber (grep/baca file, hitung ulang, cek live, EXPLAIN lokal). Hanya yang TER VERIFIKASI yang masuk daftar fix (`temuan-terverifikasi.md`).

## 1. Vonis DeepSeek

**Skor keseluruhan: 5/10 — REVISE** (tidak perlu rollback; perbaikan bedah, tapi 4 di antaranya menyangkut data/UX yang sudah tayang live).

| Area | Skor DeepSeek |
|---|---|
| (a) Kebenaran rumus & ambang | 5 |
| (b) Skema & migrasi | 6 |
| (c) Kuota & performa | 4 |
| (d) Kejujuran web/banner | 5 |
| (e) Testing & bukti | 4 |

**Penilaian Chief atas vonis:** vonis REVISE didukung bukti — 13/13 MUST-FIX terverifikasi, termasuk 4 cacat yang berdampak langsung ke pengguna live hari ini (M1, M5, M11, M12). Tidak ada satu pun yang memerlukan rollback deploy (DeepSeek sendiri menyatakan itu).

## 2. MUST-FIX (M1–M13) — semua 13 TER VERIFIKASI

| ID | Vonis verifikasi | Bukti singkat |
|---|---|---|
| M1 | **TER VERIFIKASI** — live | `api/worker.js:1129,1137` regex `/^[A-Z0-9]+X$/` di `/api/history` + `/api/ticker`. Cek live: `/api/ticker?ticker=TSLAr` → **400** (`{"error":"ticker required..."}`), TSLAx → 200, `/api/history?ticker=TSLAr` → 400. DB live: sufiks B=8, c=9, r=13, x=13 → **30/43 ticker** ditolak. |
| M2 | **TER VERIFIKASI** | `poller.py:1116` `mon.strftime("%Y-%m-%dT13:30:00Z")`. Python ZoneInfo: NY 09:30 16 Nov 2026 = **14:30 UTC**; 13:30 UTC = 08:30 EST. DST AS berakhir 1 Nov 2026. |
| M3 | **TER VERIFIKASI** | `poller.py:1035` `COUNT(*)` baris `monday_gap` outcome judged → `calibrated_weekends`; `:723` `calib = 5 * min(n, 5)`. 13 ticker XSTOCKS → 1 akhir pekan langsung `calib = 25`. Seharusnya `COUNT(DISTINCT week_start)`. |
| M4 | **TER VERIFIKASI** — saat ini laten | `poller.py:751-752` `_latest_redemption_status` tanpa `WHERE issuer`; dipakai untuk semua ticker (`:1659`). `seed_multichain.py:171-176` menulis baris `unknown` per issuer baru. Cek live: 3 baris terbaru saat ini xStocks `open` (job hourly sudah menimpa) — kontaminasi menggigit tiap re-seed sampai hourly berikutnya (±55 mnt). `dashboard/app.py:406-409` docstring "one xStocks rule for all products". |
| M5 | **TER VERIFIKASI** | `poller.py:1697-1698` hanya `score_100` + version yang ditulis; `schema.sql` `deviations` hanya punya `exit_score` + `exit_score_version` (tanpa kolom komponen). Desain §2.3:187 menuntut komponen "disimpan/ditampilkan bersama skor". Kutipan harness di `review/HASIL_TEST.md:165`: "parsial 1 komponen → 25/25 = 100,0 parsial". `dashboard/risk.py:112` band hanya terima skor; `HomeClient.tsx:757` render tanpa penyebut. Alert ≥70 hanya ada di desain/metodologi, **tidak** di `bot.py`. |
| M6 | **TER VERIFIKASI** | Ambang 0,01%/0,10% diterapkan ke rate **hourly** apa adanya (`poller.py:665-671`); desain melabeli "funding 8 jam" (`DESAIN:180`, `:263`). Komentar kode sendiri mengakui (`:637-638`). Hitung ulang: 0,10%/jam = 2,4%/hari ≈ 876%/tahun — komponen praktis mati. |
| M7 | **TER VERIFIKASI** | `poller.py:1526` `COUNT(*) FROM poller_health WHERE cycle_ts=? AND cycles_ok=1`, tanpa indeks di `schema.sql`. EXPLAIN lokal: `SCAN poller_health`. `dashboard/app.py:167-175` `get_observed_dates` juga SCAN (docstring-nya salah klaim "indexed on cycle_ts"). Hitung ulang: 6.079 × 356 = 2,16 jt/hari = 65 jt/bln. |
| M8 | **TER VERIFIKASI** | Tidak ada indeks `deviations(ts)`; `api/worker.js:289` `loadLatest` `ORDER BY ts DESC LIMIT 500` tanpa WHERE (idem `turso_read.py:285`, `app.py:233,267`). EXPLAIN lokal: `SCAN deviations USING COVERING INDEX` + `USE TEMP B-TREE FOR ORDER BY` → ±77 rb reads per panggilan saat cache dingin. |
| M9 | **TER VERIFIKASI** | `seed_multichain.py:125-126` `DELETE FROM pools/universe WHERE ticker_id=?`, `:169` DELETE redemption_windows. `schema.sql` 5 tabel `REFERENCES universe(ticker_id)`; **tidak ada `PRAGMA foreign_keys` di mana pun** → cabang yatim (bukan gagal FK) yang berlaku. |
| M10 | **TER VERIFIKASI** | Tidak ada guard startup (`PRAGMA table_info`/`sqlite_master`/`sys.exit(2)` — grep kosong). P0 12 Nov 20:46–21:21 WITA adalah bukti nyatanya. |
| M11 | **TER VERIFIKASI** | Hardcode `dexscreener.com/solana/` di `web/src/app/ticker/[id]/page.tsx:428` dan `dashboard/app.py:1760`. Live 35/106 pool Solana → **67% link salah chain**. |
| M12 | **TER VERIFIKASI** | `PENDING_COVERAGE` dikembalikan verbatim (`dashboard/logic.py:370`, `api/worker.js:1013`) tanpa filter chain yang sudah live. Teks basi: "NVDAc (verified); MSTRc, SNDKc + 10 more (to verify)" padahal 9 ticker Coinbase sudah di-seed; "TSLA, NVDA, SPY (verified); 10 more" padahal 13 Robinhood sudah di-seed. Mitigasi yang ada (label "not yet polled" + tanggal vonis) tidak memperbaiki angka yang salah. |
| M13 | **TER VERIFIKASI** | `review/CHECKLIST_QA.md:80` F5 "BELUM DILAKUKAN". Larangan resale/redistribusi tercatat di `VERIFIKASI_MULTICHAIN_2026-11-12.md:417-419` + `SEED_MULTICHAIN_2026-11-12.md:263`. Display publik chain baru sudah live → keputusan Septian sebelum ekspansi berikutnya. |

## 3. SHOULD-FIX (S1–S14) — 13 terverifikasi, 1 sebagian

| ID | Vonis verifikasi | Bukti singkat |
|---|---|---|
| S1 | **TER VERIFIKASI** | `migrations/2026-11-12-penambahan.sql:72-73` dua `ALTER TABLE` tanpa guard → jalan kedua `duplicate column name`. 7 CREATE memakai `IF NOT EXISTS`. |
| S2 | **TER VERIFIKASI** | `poller.py:592` fallback `mark_px` → mid; tidak ada kolom `px_source` di `perp_snapshots`. `DESAIN:116,262` mendokumentasikan `perp_px` sebagai "harga mark Hyperliquid XYZ". |
| S3 | **TER VERIFIKASI-SEBAGIAN** (lokasi salah kutip) | Frasa "per interval 8 jam" **tidak ada** di `schema.sql` maupun migrasi (komentar di sana tidak menyebut satuan itu). Frasa itu ada di **`DESAIN_PENAMBAHAN_2026-11-12.md:263`** (kutipan skema di dokumen desain) + tabel §2.2 `:180`. Cacat kata nyata, lokasi yang dikutip DeepSeek salah. |
| S4 | **TER VERIFIKASI** | `poller.py:943` `liquidation_status(div, None, None)`; tidak ada kolom `oracle_lag_s` (sengaja, `schema.sql:96`, migrasi `:38`); desain §2.4 tetap menyatakan ambang 120/600 dtk (`DESAIN:218,221`); `CHECKLIST_QA.md:59` D5 "BELUM ADA". |
| S5 | **TER VERIFIKASI** | `dashboard/app.py:439-447` `get_venues_live` memakai `MAX(ts)` global; `api/worker.js:304,326,491` sudah memakai per-ticker anchor (P2-M2 ronde 8). |
| S6 | **TER VERIFIKASI** | `run_hourly_liquidation`: early return `if not ctxs` / `if not rows` terjadi **sebelum** `state["liquidation_alert_tickers"] = alert_now` (`poller.py:968`); cabang follow-up `:1788` membaca state basi. |
| S7 | **TER VERIFIKASI** | Prediksi hanya `wd==6 and hour>=22` (`:1169`); tidak ada catatan minggu terlewat; `_monday_gap_fill_outcomes` membaca **semua** `pending` tanpa batas umur (`:1100-1101`, docstring "never guessed"). |
| S8 | **TER VERIFIKASI** | `_exit_redemption_component`: `closed` → 20.0 (`poller.py:619-620`); akhir pekan semua `closed` → komponen 20 seragam. |
| S9 | **TER VERIFIKASI** | `qa/test_coverage_2026-11-12.mjs:139-141` hanya grep `COUNT(*)` pada 4 tabel; lolos dari M7 (COUNT(*) `poller_health`) dan M8 (`ORDER BY ... LIMIT` tanpa COUNT(*)). |
| S10 | **TER VERIFIKASI** | `/tmp/test_penambahan.py` sudah tidak ada (VM restart menghapus /tmp). `CHECKLIST_QA.md` C2/C3/C6/C7/C8/C9 "BELUM ADA di repo"; hanya 1 file guard baru (`test_coverage_2026-11-12.mjs`). |
| S11 | **TER VERIFIKASI** | `BACKTEST_ALERT_2026-11-12.md:16,70-71`: 37 event semua `spread`, `deviation_high`=0; tidak ada backtest `perp_deviation`/`exit_high` (bot.py belum berubah). |
| S12 | **TER VERIFIKASI** | Ketiga estimasi memakai 288 siklus/hari; data backtest: hari kerja 381–385, akhir pekan 287–288 → rata-rata (5×383+2×288)/7 ≈ **356/hari** → understate 23,6%. KUOTA menghitung perp 2× (skenario b + c = 673.920) padahal perp hanya 10 ticker total; desain melewatkan Robinhood (`DESAIN:617-618` hanya Base + BNB). Hitung ulang Chief (konvensi M dokumen): snapshots 106×356×30×3 = 3.396.240 + deviations 43×356×30×2 = 918.480 + perp 10×356×30×3 = 320.400 + por 61.920 + liq 14.400 ≈ **4,71 jt/bln (47%)** — cocok dengan angka DeepSeek ≈4,7 jt. Varian 71 pool ≈ 3,6 jt (36%) — cocok. |
| S13 | **TER VERIFIKASI** | `seed_multichain.py:171-176` INSERT `redemption_windows` tanpa `window_note_en`; `dashboard/app.py:1922` merender `window_note_en` untuk pengguna EN → kosong untuk 3 issuer baru (versi ID terisi). |
| S14 | **TER VERIFIKASI** | `_oi_24h_ago` (`poller.py:788-797`) satu query per ticker di dalam loop (`:1692`): 10 × 356 = 3.560 round-trip/hari di jalur kritis. Dampaknya latensi serial (query terindeks, reads kecil), bukan reads. |

## 4. NIT (N1–N5) — 3 terverifikasi, 2 sebagian

| ID | Vonis verifikasi | Bukti singkat |
|---|---|---|
| N1 | **TER VERIFIKASI-SEBAGIAN** | Band 40/70 diduplikasi di **2** tempat (`dashboard/risk.py:109`, `web/src/lib/risk.ts:84-85`) tanpa fixture bersama. Klaim "tempat ketiga di bot.py" **salah** — `bot.py` tidak mengandung `exit_score` sama sekali (alert 70 hanya ada di desain/metodologi). |
| N2 | **TER VERIFIKASI** | `dashboard/turso_read.py:300-315` `get_perp_latest` tanpa filter kesegaran (baris terbaru berapa pun umurnya); `dashboard/app.py:1843-1852` menghitung `_dev_pt` tanpa label basi. (Poller `_latest_perp_by_ticker` menyaring 15 menit — panel tidak.) |
| N3 | **TER VERIFIKASI** | `refresh_median_depth_7d` hanya mengiterasi ticker yang dilewatkan pemanggil (`poller.py:802-810`, `for t in tickers`); `median_depth_7d_date` adalah tanggal global, bukan umur per ticker. |
| N4 | **TER VERIFIKASI** | Tidak ada `CHECK` pada `monday_gap.outcome` di skema/migrasi (grep kosong). |
| N5 | **TER VERIFIKASI-SEBAGIAN** (defeknya beda dari yang ditulis) | `coverage_live_line` **ADA** di `dashboard/i18n.py:181,503` dan isinya generik/benar (bukan hardcode Solana) — DeepSeek tidak bisa menilainya karena tidak ada di paket. Defek nyatanya: **`coverage_short` basi** ("13 xStocks tickers across 35 Solana DEX pools", `i18n.py:180,502`, `web/src/lib/i18n.ts:70,360`) dan **masih dipakai sebagai fallback** (`dashboard/app.py:551`, `HomeClient.tsx:156,175`). |

## 5. Jawaban Q1–Q14 (PERTANYAAN_TERBUKA)

| Q | Vonis verifikasi | Ringkasan |
|---|---|---|
| Q1 funding | **TER VERIFIKASI** | Satuan benar per interval (hourly); ambang 8× terlalu ketat (M6). |
| Q2 oracle lag | **TER VERIFIKASI** | Guard v1 satu ukuran saja (S4). Klaim "tidak ada timestamp oracle di endpoint info" konsisten dengan probe Hyperliquid 12 Nov (field yang terlihat: funding/OI/oraclePx/markPx, tanpa timestamp). |
| Q3 duplikasi Exit Score | **TER VERIFIKASI** | Bukan duplikasi berbahaya (rumus hanya di `poller.py`); yang perlu dikunci batas 40/70 (N1). |
| Q4 sufiks `r` | **TER VERIFIKASI** | Pertahankan `r`; regex Worker yang harus diperbaiki (M1). |
| Q5 selisih kuota | **TER VERIFIKASI** | SEED paling dekat; benar ≈4,7 jt/bln (47%); varian 71 pool ≈3,6 jt (36%) lebih tepat sebagai default. |
| Q6 TSLAon 10× | **TER VERIFIKASI** | `VERIFIKASI_MULTICHAIN:34,44,49-51`: $5,01 jt + $1,89 jt vs $0,50 jt + $0,19 jt → 10,0×; Uniswap cocok. Vonis GAGAL tidak berubah (soal venue). |
| Q7 CRCLc | **TER VERIFIKASI** | `SEED:123,268`: $221.864 → $12.653. Rekomendasi cek harian untuk ticker ±20% dari ambang adalah usulan DeepSeek, bukan aturan yang sudah ada. |
| Q8 communityV3 | **TER VERIFIKASI** | `VERIFIKASI:93-104`: factory klon UniswapV3Factory terverifikasi, `owner()=0x0`, `fee()=20000` (2%). Vonis final. |
| Q9 turnover Robinhood | **TER VERIFIKASI** (substansi) | Turnover >10× adalah flag, bukan gate; aturan §1.1 benar. Angka pasangan spesifik NVDA/WETH ($11,9 jt vs $1,13 jt) tidak dicek ulang ke DexScreener live — berasal dari laporan riset. |
| Q10 lisensi | **TER VERIFIKASI** (sebagai "tidak bisa dijawab") | Tidak ada teks ToS di paket; M13. |
| Q11 metodologi web | **TER VERIFIKASI** | `methodology/page.tsx:188-200` SECTIONS hanya `exit_score` + `perp`; tidak ada `monday_gap_v1`/`liq_guard_v1`. Catatan: string `methodology_exit_score`/`methodology_perp` **ada** di repo (`web/src/lib/i18n.ts:184-185`) dan memuat rumus+bobot — DeepSeek tidak bisa menilainya dari paket (lihat addendum V1). |
| Q12 lonjakan reads | **TER VERIFIKASI-SEBAGIAN** | Mekanisme kandidat #1 terkonfirmasi: tombol Refresh → `st.cache_data.clear()` (`dashboard/app.py:1201,1215`) + full scan M7/M8. **Atribusi angka pasti (±50 klik ≈ 14 jt) belum terbukti** — burst juga bertepatan dengan QA/backtest/deploy. Kandidat #2 (M7) terkonfirmasi kodenya. |
| Q13 F1/F3 alert & poller | **TER VERIFIKASI** | D5 selesai (poller multichain live 106 snapshot/siklus). D4 belum: `bot.py` tidak berubah, `CHECKLIST_QA.md:55` D1 "BELUM ADA". F1/F3 display-only sampai ada bukti `bot.py`. |
| Q14 Monday Gap 2/13 | **TER VERIFIKASI-SEBAGIAN** (arah benar, angka salah) | Desain §3.4 "~26 baris/minggu" **salah** (`DESAIN:330`) — kode hanya mengiterasi `XSTOCKS_MINTS` (13 ticker). Realistis **≈9–10/minggu** (13 − COINx/HOODx/METAx 1-pool − GOOGLx yang flapping), **bukan 2–5** seperti hitungan DeepSeek (DeepSeek keliru memasukkan ticker issuer baru yang memang tidak diiterasi F2). 8 akhir pekan → ±72–80 prediksi, bukan 16–40. Tidak ada catatan kelayakan F2 di web (tidak ada seksi monday_gap). |

## 6. Tabel hitung ulang DeepSeek (§4) — verifikasi

| # | Hasil verifikasi |
|---|---|
| 1–2 (bobot 100/100) | ✅ cocok (maxima `exit_score_v1`; confidence `monday_gap_predict`). |
| 3–5 (backtest 32/32, 97=90, 76.767) | ✅ cocok dengan `BACKTEST_ALERT_2026-11-12.md` §1 + headline (11×6.079 + 2×4.949 = 76.767 ✓). |
| 6 (356 siklus/hari) | ✅ cocok — hitung ulang dari tabel harian backtest: (5×383 + 2×288)/7 ≈ 356. |
| 7 (writes ≈4,7 jt) | ✅ cocok — hitung ulang Chief ≈4,71 jt (lihat S12). Catatan: pengali indeks M adalah konvensi dokumen yang belum terbukti terhadap cara Turso menghitung; dengan M=2 untuk perp totalnya ≈4,6 jt — kesimpulan tidak berubah. |
| 8 (perp KUOTA 2× lipat) | ✅ cocok — KUOTA menghitung 336.960 per skenario chain (b + c); benar 10×356×30×3 = 320.400. |
| 9 (reads 194 jt) | ⚠️ **aritmetika benar, interpretasi perlu caveat** — 77,7 jt/12 hari = 6,475 jt/hari = 194 jt/bln ✓, tapi angka itu memuat burst QA/backtest/deploy (bukan steady-state; laju tenang 11–12 Nov ≈52 jt). Proyeksi kumulatif log 23:58 sudah 225,1 jt. |
| 10–11 (reads M7/M8) | ✅ cocok (6.079×356 = 2,16 jt/hari; 6.079×288 = 1,75 jt/hari per proses dashboard). |
| 12 (loadLatest full scan) | ✅ cocok — EXPLAIN lokal: SCAN + TEMP B-TREE. |
| 13 (kalibrasi 25) | ✅ cocok. |
| 14 (funding 8×) | ✅ cocok. |
| 15 (13:30 vs 14:30) | ✅ cocok (ZoneInfo). |
| 16 (30 ticker ditolak) | ✅ cocok — dibuktikan live (400) + hitungan sufiks DB. |
| 17 (link benar 33%) | ✅ cocok — 35/106. |
| 18 (115 vs 106 pool) | ❌ **NOISE — perbandingan salah**: 115 adalah pool multichain dry-run; 106 adalah **total** snapshot/siklus (35 Solana + 71 multichain varian hemat). Selisih sebenarnya 115 − 71 = **44 pool, dan sudah dijelaskan** di `SEED_MULTICHAIN:164,177-181` (varian hemat `--max-pools-per-ticker 3`). |
| 19 (prediksi/minggu) | ⚠️ **arah benar, angka salah** — desain 26 salah; realistis ≈9–10, bukan 2–5 (lihat Q14). |
| 20 (guard §5.4: 1 dari 8) | ✅ cocok (hanya C5 `test_coverage_2026-11-12.mjs` di repo). |
| 21–22 (106 snapshot, 20 baris liq) | ✅ cocok dengan log poller + deploy (10 ticker × 2 jam). |
| 23 (TSLAon 10×) | ✅ cocok (lihat Q6). |
| 24 (biaya backtest 241 rb) | ✅ cocok — komponen di `BACKTEST:362-364`: 19,6 rb + 153 rb + 53.170 + 15 rb = 240.770. |

Daftar "yang saya periksa dan TIDAK laporkan" (DeepSeek §2 akhir) — spot-check Chief: bobot ✅, `oi_usd = oi_base × markPx` ✅ (`poller.py:558`), seed `--live` guard exit 2 ✅ (`seed_multichain.py:249-255`), cap waitlist 500/jam atomik ✅ (`api/worker.js:848-870`), `only_solana_xstocks` diturunkan dari data ✅ (`dashboard/logic.py:376-378`). Tidak ditemukan fabrikasi di daftar itu.

## 7. NOISE / SALAH (dicatat, TIDAK diperbaiki)

| # | Klaim DeepSeek | Alasan + bukti |
|---|---|---|
| N-A | Recalc #18: "seed dry-run 115 pool vs live 106 (9 pool hilang, tak dijelaskan)" | Perbandingan apel-vs-jeruk (lihat §6 #18). Live multichain = 71 pool (varian hemat), 35 + 71 = 106 total. Selisih 44 pool dijelaskan di SEED doc. |
| N-B | Q14: "prediksi realistis ≈ 2–5/minggu; 8 akhir pekan → 16–40 prediksi" | Salah hitung. F2 hanya mengiterasi `XSTOCKS_MINTS` (13); yang gugur hanya ticker 1-pool (COINx/HOODx/METAx + GOOGLx flapping) → ≈9–10/minggu; 8 minggu → ±72–80. |
| N-C | S3: komentar "per interval 8 jam" ada di `schema.sql`/migrasi | Tidak ada di kedua file itu; frasa tersebut ada di `DESAIN:263`. (Cacat katanya nyata — masuk fix sebagai S3-sebagian.) |
| N-D | N1: "batas 40/70 ada di 3 tempat, termasuk ambang alert 70 di bot.py" | `bot.py` tidak mengandung `exit_score` sama sekali. Duplikasi nyata hanya 2 tempat. |
| N-E | N5 (sebagaimana ditulis): "`coverage_live_line` tidak ada di paket → tidak bisa diverifikasi" | Bukan defek kode: string itu ada (`i18n.py:181,503`) dan isinya benar. Defek nyatanya adalah `coverage_short` basi di jalur fallback (diklasifikasi ulang di §4 N5). |

## 8. Addendum — temuan baru dari proses verifikasi (bukan dari DeepSeek)

- **V1 — Teks metodologi mengklaim alert yang tidak ada + status basi.** `web/src/lib/i18n.ts:184-185` `methodology_exit_score`: "Scores of 70 or above also raise one alert per ticker per 24 hours"; `methodology_perp`: "an alert fires when |deviation| reaches 1.0%". Keduanya **tidak ada di `bot.py`** (D1 BELUM ADA). Kedua string juga masih berkata "no scores stored yet" / "no perp snapshots stored yet" — basi sejak deploy (skor + snapshot sudah tersimpan). Perlu diperbaiki di ronde fix (teks + status).
- **V2 — Docstring `get_observed_dates` salah klaim indeks.** `dashboard/app.py:170`: "indexed on cycle_ts" — tidak ada indeks `poller_health` di `schema.sql`. Perbaiki komentar + tambah indeks (M7).
- **V3 — M4 saat ini laten, bukan aktif.** Baris `redemption_windows` terbaru live adalah xStocks `open` (15:51 UTC 12 Nov). Jendela kontaminasi hanya tiap re-seed — karena itu M9 (seed UPSERT) dan M4 harus diperbaiki bersama sebelum re-verify mingguan pertama.

## 9. Urutan perbaikan yang disarankan (DeepSeek §5, didukung verifikasi)

Sama dengan urutan DeepSeek, dengan dua koreksi: M1+M4+M2+M3 dulu (satu baris tiap temuan), lalu M5, M7/M8+S9, M9, M10+S1, M11+M12, M6+S4 (revisi desain bertanggal — keputusan Chief + Septian), M13 (keputusan Septian), S10/S11. Empat yang berdampak langsung ke pengguna (M1, M11, M12, M5) sebaiknya masuk sebelum akhir pekan 16 Nov — karena 16 Nov adalah kali pertama Monday Gap menulis baris, dan M2/M3 akan langsung mencemari outcome pertamanya. Daftar fix lengkap: `temuan-terverifikasi.md`.

**Catatan proses (perintah Septian 00:01 WITA 13 Nov):** temuan terverifikasi diperbaiki dulu, baru kabari Septian singkat + file .md untuk di-review Instinct. Rantai DeepSeek → Instinct hanya untuk Radar fitur baru; MLF tetap DeepSeek + Luna.
