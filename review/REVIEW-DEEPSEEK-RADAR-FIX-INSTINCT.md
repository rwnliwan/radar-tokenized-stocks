# Radar Tokenized Stocks — Fix ronde review DeepSeek (12 Nov 2026)

**Untuk:** Instinct (review kedua, dikirim Septian sendiri)
**Status:** kode + dokumen + QA selesai di repo, **BELUM di-deploy, BELUM di-apply ke Turso live** — paket deploy menunggu ACC Septian tersendiri.
**Repo:** `~/workspace/radar-tokenized-stocks` (branch kerja saat ini; belum commit/push)
**Review asal:** `review/REVIEW-DEEPSEEK-RADAR.md` — DeepSeek skor **5/10, REVISE** (13 must / 14 should / 5 nit = 32 temuan). Chief (induk) memverifikasi tiap temuan ke sumber live/kode: **31/32 BENAR, 1 noise (S3), 1 terjawab tanpa fix (N5)**. Yang diperbaiki di ronde ini hanya temuan terverifikasi; S3 tidak diperbaiki, N5 tidak perlu perbaikan.

## Ringkasan vonis

Tidak ada rollback. Empat temuan berdampak langsung ke pengguna live (M1, M11, M12, M5) diperbaiki dan diuji dulu, karena Senin 16 Nov 2026 adalah kali pertama Monday Gap menulis baris. Tidak ada ambang lama yang diubah (alert 1,0%, pool ≥ $100rb, universe ≥ $500rb + ≥ 2 venue). `bot.py` yang sedang jalan (alert live tiap 5 menit) **tidak diubah** — hanya dibaca (lihat Q13 di bawah).

## Per temuan — apa yang diubah + bukti tes

### Must-fix (13/13 diperbaiki)

| # | Temuan (terverifikasi Chief) | Perbaikan | Bukti |
|---|---|---|---|
| M1 | Regex Worker `^[A-Z0-9]+X$` menolak 30/43 ticker multichain — cek live: `TSLAr`→400, `TSLAx`→200 | `api/worker.js:1170` (`/api/history`) dan `:1178` (`/api/ticker`): regex jadi `^[A-Z0-9]+[XCBR]$` (akhiran X/C/B/R = xStocks/bStocks/Coinbase/Robinhood) | `qa/test_radar_fix_worker.mjs` 0 FAIL; tiap ticker universe diuji → 200 |
| M2 | Monday Gap hardcode 13:30 UTC; NY buka 16 Nov = 14:30 UTC (EST) | `poller.py:1271-1273` + konstanta `mon_open`: 14:30 UTC + komentar DST (kembali 13:30 saat DST 14 Mar 2027) | `qa/test_radar_fix_poller.py` 68 PASS |
| M3 | Confidence kalibrasi hitung baris, bukan akhir pekan (saturasi 1 akhir pekan) | `poller.py:1205-1207`: `COUNT(DISTINCT week_start)`; target calib = 5 akhir pekan berbeda | poller test 68 PASS |
| M4 | Redemption bocor antar-issuer (query tanpa `WHERE issuer`; cek live: semua ticker pakai status xStocks 'open') | `poller.py:779` `_latest_redemption_status(cycle_dt, issuer)` + `WHERE issuer` + cache per-issuer (≤4 read/siklus); `forward_paper.py:158` diperbaiki ke resolver per-issuer (signature lama akan rusak) | `qa/test_forward_paper_issuer.py` 6/6 PASS (TSLAB closed 65h → 10; TSLAx open 100h → 0; TSLAc unknown → None/parsial) |
| M5 | `components_present` tak disimpan — skor parsial tampil penuh (band) | Migrasi baru `migrations/2026-11-13-radar-fix.sql`: `ALTER deviations ADD COLUMN exit_score_components INTEGER`; poller menulisnya; band/alert syaratkan components ≥ 3 (`dashboard/risk.py:113` `EXIT_SCORE_FULL_COMPONENTS = 3`, `exit_score_partial()` :117; Worker payload `api/worker.js:452-455`; web `exitPartial` + kunci i18n `exit_score_partial`/`exit_score_partial_nocount` EN+ID, di-wire di `web/src/app/ticker/[id]/page.tsx:560-562`) | schema test ALL PASS; node `test_exit_score_bands.mjs` 10/10; python `test_exit_score_bands.py` 18/18 (fixture bersama `qa/exit_score_bands_fixture.json`: 0→low, 39→low, 40→medium, 69→medium, 70→high, 100→high) |
| M6 | Ambang funding 8× terlalu ketat (ambang per-8-jam dipakai pada rate hourly) | **Revisi tertulis, bukan penalaan diam-diam:** `DESAIN_PENAMBAHAN_2026-11-12.md:751` "Revisi 13 Nov 2026" — ambang 0,01%/0,10% adalah ambang **per jam** apa adanya dari API (`poller.py:633-640`, `:665-671`); label "funding 8 jam" salah; ambang per-8-jam setara (0,00125%/0,0125% per jam) TIDAK dipakai; konsekuensi jujur: komponen funding praktis selalu 0 pada rate hourly biasa. Kalimat koreksi masuk string `methodology_exit_score` + label `perp_funding` → "Funding (hourly)" / "Funding (per jam)" di `web/src/lib/i18n.ts:113,185,404,476` dan `dashboard/i18n.py:83,86,404,407`. Angka kode TIDAK diubah. | `py_compile dashboard/i18n.py` OK; `tsc --noEmit` web OK |
| M7 | `poller_health` full scan tiap siklus tanpa indeks (±65J reads/bln) | Migrasi: `CREATE INDEX idx_poller_health_cycle_ts ON poller_health(cycle_ts)` | `qa/test_no_fullscan.py` PASS (kontrol negatif pra-migrasi FAIL seperti seharusnya); `qa/test_radar_fix_schema.py` ALL PASS |
| M8 | `deviations` tanpa indeks (ts) — loadLatest scan + sort seluruh tabel | Migrasi: `CREATE INDEX idx_deviations_ts ON deviations(ts)` | sama seperti M7 |
| M9 | Seed DELETE (riwayat hilang tiap seed ulang) | `seed_multichain.py:171,195`: UPSERT (`ON CONFLICT DO UPDATE`, deaktivasi `status='inactive'`); grep `DELETE FROM` = 0 | schema test 58 checks ALL PASS (migrasi 2× tanpa error, seed 2× riwayat utuh) |
| M10 | Tanpa startup guard (penyebab insiden P0 12 Nov) | `poller.py:2160` `check_startup_schema()` di `main()`: PRAGMA table_info + sqlite_master; gagal cepat exit 2 bila migrasi belum diterapkan | poller test 68 PASS |
| M11 | Link DEX hardcode `/solana/` (71/106 pool bukan Solana, 67% salah chain) | `web/src/lib/dexscreener.ts` baru (chain-aware; Robinhood Chain terverifikasi DIDUKUNG DexScreener — `dexscreener.com/gainers/robinhood`, chain id 4663; chain tak dikenal → tanpa link `—`); `dashboard/logic.py:409` `dexscreener_pair_url` (pemetaan identik web; grep `/solana/` di `app.py` = 0) | `qa/test_dexscreener_links.mjs` 15/15 PASS; dashboard test 47 checks ALL PASS |
| M12 | `/api/coverage` live + pending saling menyangkal (chain sama di kedua tabel, cek live) | `api/worker.js:987` `canonicalChain()` (menemukan seed menulis chain bStocks `"bsc"` sementara PENDING_COVERAGE memakai `"bnb"` — normalisasi alias wajib) + filter pending-vs-live `:1049-1053` | `qa/test_radar_fix_worker.mjs` 0 FAIL; `qa/test_coverage_2026-11-12.mjs` 0 FAIL (asersi lamanya mengunci bug M12, diubah ke ekspektasi benar) |
| M13 | **Lisensi DexScreener belum dicek** | **TIDAK diputuskan — KEPUTUSAN TERBUKA SEPTIAN** (lihat § Keputusan terbuka). Tidak ada klaim lisensi baru ditulis di dokumen mana pun. | — |

### Should-fix (13/14 diperbaiki; S3 noise)

| # | Temuan | Perbaikan |
|---|---|---|
| S1 | Migrasi tak re-runnable | Runner baru `qa/apply_migration_2026-11-13.py` (cek PRAGMA sebelum ALTER; pola sama seperti migrasi 2026-11-09). Repo sebelumnya TIDAK punya runner migrasi. Migrasi 7 pernyataan: run-1 "7 run, 0 skipped", run-2 "0 run, 7 skipped". |
| S2 | Fallback mark→mid tanpa penanda | Migrasi: `ALTER perp_snapshots ADD COLUMN perp_px_source TEXT` ('mark' \| 'mid'); poller menulisnya tiap INSERT. |
| S3 | **NOISE — tidak diperbaiki.** Komentar `funding REAL, -- funding rate per interval 8 jam` yang dikutip DeepSeek TIDAK ADA di `schema.sql:87` (grep 0). | — |
| S4 | Ambang lag 120/600 detik inert (lag selalu None) | Revisi tertulis di `DESAIN_PENAMBAHAN_2026-11-12.md:810`: ambang oracle lag **DICABUT** dari guard v1 (sumber: `poller.py:943` `liquidation_status(div, None, None)`; migrasi sengaja tanpa kolom `oracle_lag_s`); guard v1 = divergensi mark-vs-oracle saja (≥1,0% peringatan, ≥3,0% kritis) + `distance_pct` bila sumber terverifikasi. Tidak ada slot i18n untuk S4 (grep `monday_gap\|liq_guard\|liquidation` di kedua file i18n = 0) — kalimat yang disetujui tertulis di revisi DESAIN saja. |
| S5 | `get_venues_live` MAX(ts) global | `dashboard/` — anchor per ticker (MAX ts per ticker_id, jendela 2 jam); tes membuktikan query lama salah: (4,2) vs baru (4,3). |
| S6 | State liquidation lama bertahan (early return) | `poller.py` — try/finally state di semua jalur. |
| S7 | Jendela Monday Gap hilang tanpa catatan + fill_outcomes tanpa batas umur | `poller.py` — log `monday gap MISSED` + batas pending 8 minggu (`MONDAY_GAP_PENDING_MAX_AGE_WEEKS = 8`, `:499`). |
| S8 | Komponen redemption konstan 20 sepanjang akhir pekan | `poller.py` — closed skala jam-ke-buka (≤24h→20, ≤72h→10, else 0). |
| S9 | Guard anti-full-scan buta (hanya grep 4 tabel) | Guard baru `qa/test_no_fullscan.py` — EXPLAIN QUERY PLAN atas DB sintetis lokal (deviations ~6k, poller_health 6k, perp ~3,5k, snapshots ~12k + ANALYZE); GAGAL bila ada SCAN tanpa USING INDEX; membuktikan kebutaan guard grep lama secara mekanis (2 check). |
| S10 | Harness bukti di /tmp, bukan repo | Dipromosikan ke `qa/test_penambahan_2026-11-12.py` (648 baris). `/tmp/test_penambahan.py` terverifikasi HILANG kena restart VM — harness ditulis ulang dari `HASIL_TEST.md` §3.2. **Hasil: 59 PASS, 0 FAIL, dua run deterministik. BUKAN klaim 84 PASS asli** — 7 hal yang tidak bisa direkonstruksi dicantumkan eksplisit di header file (daftar 84 asersi persis; hasil live Hyperliquid/Turso 12 Nov; angka live Monday Gap minggu 2026-11-07; input persis kasus 54,2; perilaku 'closed' lama; ambang buka 13:30 lama; guard DESAIN §5.4 butir 2/5/7/8). |
| S11 | Backtest hanya spread hari kerja (37 event, deviation_high=0, tanpa perp/exit/akhir pekan) | `BACKTEST_ALERT_2026-11-12.md:24` — paragraf tebal: "Backtest ini hanya menguji alert spread hari kerja; F1 (perp) / F3 (Exit Score) dan kaki akhir pekan = forward-only, n=0 per 12 Nov 2026." |
| S12 | Estimasi kuota pakai 288 siklus/hari (ground truth ~356, understate ~23,6%) | `KUOTA_PENAMBAHAN_2026-11-12.md:177` §9 "Revisi 13 Nov 2026" (tabel lama tidak diedit). Faktor 356/288 = 1,2361; baseline terukur (1,95 jt) TIDAK dikali (sudah mengandung 356/hari). Hasil: (a) 2,39 jt (23,9%); (a)+(b) 4,24 jt (42,4%); (a)+(b)+(c) **6,09 jt (60,9%)** (dulu 5,32); (d) 51,68 jt (516,8%). Vonis tak berubah; margin (c) menipis 26,8→19,1 poin di bawah ambang 80%; syarat (c) (retensi+agregasi terbukti) tetap BELUM terpenuhi. DESAIN §6.2 dikoreksi: total 3,94 jt (39,4%). |
| S13 | Seed tanpa window_note_en | `window_note_en` ditambahkan untuk 3 issuer (terjemahan langsung note ID). |
| S14 | `_oi_24h_ago` 1 round-trip/ticker/siklus serial | `poller.py:837` `_oi_24h_ago_batch()` — 1 query JOIN. |

### Nit (5/5 — N5 terjawab, sisanya diperbaiki)

| # | Temuan | Perbaikan |
|---|---|---|
| N1 | Band 40/70 duplikasi (dashboard/risk.py:112 + web risk.ts:81; ambang 70 di bot.py TIDAK terkonfirmasi) | Fixture bersama `qa/exit_score_bands_fixture.json` (6 kasus); tes Node 10/10 PASS, Python 18/18 PASS. |
| N2 | `_dev_pt` tanpa gate 15 mnt | `dashboard/logic.py` `perp_is_fresh`, `PERP_FRESH_MINUTES = 15.0`. |
| N3 | Median depth tanpa batas umur | `poller.py:881` `MEDIAN_DEPTH_MAX_AGE_DAYS = 7` + prune (`_pruned_median_depth`: stempel masa depan dibuang seperti stempel kedaluwarsa). |
| N4 | `monday_gap.outcome` tanpa CHECK | CHECK `('pending'/'accurate'/'inaccurate')` di `schema.sql` untuk DB baru; didokumentasikan: CHECK tak bisa ditambah ke tabel live via ALTER (butuh rebuild — tidak dicoba); penegakan sementara = value set di poller. |
| N5 | **TERJAWAB, tidak perlu fix.** String `coverage_live_line` generik, tidak menyebut Solana, tidak salah. | — |

### Jawaban pertanyaan terbuka review (Q1–Q14, terverifikasi Chief)

- **Q5 (angka kuota — tiga dokumen berbeda):** (1) asumsi pool (59 vs 70 vs 115 realita), (2) baseline (1,3 stale vs 1,95 aktual), (3) cakupan (SEED tanpa 5 fitur; KUOTA tanpa Robinhood). (a)+(b)+(c) definisi KUOTA = **6,09 jt**; dengan pool real Base+BNB (±40 pool) = 4,08 jt; SEED §4 sendiri = 5,63 jt (baseline 1,3) / 6,28 jt (baseline 1,95); cakupan penuh (5 fitur + 115 pool) = **6,80 jt (68,0%)** — angka yang harus dipakai untuk keputusan deploy multichain penuh. "≈4,7" dapat direkonstruksi sebagai skenario struktur DESAIN (59 pool) + baseline 1,95 + perp M=3 = 4,69 jt — jadi "SEED §4 paling dekat" benar numerik tetapi apel-dengan-jeruk. Opsi hemat 71 pool dikoreksi: total 4,22 jt (baseline 1,3) / 4,87 jt (baseline 1,95) — tetap direkomendasikan sebagai default.
- **Q13/D4 — TEMUAN BARU ronde ini (bukan di daftar review): `bot.py` TIDAK punya jalur alert F1/F3.** Grep final: `perp` = 0, `exit_score|exit_high|perp_deviation` = 0, tidak ada bacaan `perp_snapshots`. Tipe alert yang ada hanya `spread`, `deviation_high`, `redemption`, `redemption_paused`, `redemption_closing_soon` (`bot.py:439,449,464,473,487`). **`perp_deviation` / `exit_high` = display-only, alert menyusul** — tidak ada jalur yang dikarang; `bot.py` tidak diubah. (Catatan: `deviation_high` yang ada adalah kaki akhir pekan lama, dan itu pun tidak pernah terpicu live karena `dev_vs_median` tak pernah mencapai 1%.)

## Temuan baru dari guard S9 (probe ronde ini, bukan di daftar review)

Guard `qa/test_no_fullscan.py` pada skema pasca-M7/M8 masih gagal 4 query — dua celah nyata yang tidak dicakup migrasi awal:

1. `api/worker.js:359` perp latest (`ORDER BY ts DESC LIMIT 200`) masih `SCAN perp_snapshots + TEMP B-TREE` — perlu `CREATE INDEX idx_perp_snapshots_ts ON perp_snapshots(ts)`.
2. Query per-ticker worker.js (`:614`, `:680`, `:699`, plus `:540,546,595,605,633,668,673,689`) memakai `ticker_id = ? COLLATE NOCASE`, yang mengalahkan indeks BINARY `(ticker_id, ts)` — terbukti: tanpa NOCASE → `SEARCH USING INDEX`, dengan NOCASE → `SCAN + TEMP B-TREE`, dengan indeks NOCASE → `SEARCH USING INDEX`.

Keduanya **ditutup di ronde ini** (bukan disembunyikan — guard sengaja tidak dipersempit): migrasi + `schema.sql` ditambah 3 indeks (`idx_perp_snapshots_ts`, `idx_deviations_ticker_nocase_ts`, `idx_perp_ticker_nocase_ts`). Keputusan: indeks NOCASE dipilih atas normalisasi case di kode — perilaku query identik, tanpa perubahan kode. Trade-off yang diterima: tiap indeks tambahan menaikkan pengali tulis (satu indeks lagi per baris INSERT) — volume tulis kecil (deviations ~15k baris/hari, perp_snapshots ~3,5k baris/hari) sementara ini jalur baca panas (tiap hit `/api/ticker`). Guard kini **PASS penuh**; `qa/test_radar_fix_schema.py` diperbarui (7 pernyataan migrasi + cek plan 3 indeks baru) dan `qa/test_penambahan_2026-11-12.py` disesuaikan (dua indeks perp ikut dilucuti bersama span F1, karena tabelnya tak ada pra-penambahan).

Perbaikan test `qa/test_r9_fix.py` yang ikut diselesaikan ronde ini (4 FAIL awal — 2 pre-existing di HEAD, 2 baru dari guard M10 + kalimat M6): registry GG31 dilengkapi (`_latest_redemption_status`, `_perp_due`, `_pruned_median_depth`, `perp_is_fresh` — masing-masing diverifikasi semantiknya di kode, bukan sekadar didaftarkan); GG34 mengecualikan katalog sistem (`sqlite_master`/`pragma_table_info` — dibaca guard M10 by design); GG32: komentar `heartbeat` ditambahkan di call-site `run_cycle()` mode single-cycle (`poller.py:2317`, registry `KNOWN_BARE` sudah ada — hanya komentarnya yang hilang). Kalimat M6 "per-8-jam" disinkronkan ke "per 8 jam" di `DESAIN_PENAMBAHAN_2026-11-12.md` (:758/:777/:801) agar konsisten dengan string i18n.

## Keputusan terbuka (untuk Septian — bukan untuk agen)

1. **M13 — Lisensi DexScreener.** Apakah pemakaian data/link DexScreener (dan penamaan chain/DEX di web) sudah sesuai lisensi/ketentuan mereka? Belum dicek. Bila lisensi melarang, M11 (link chain-aware) tetap benar secara teknis tetapi perlu penyesuaian tampilan/kutipan.
2. **Ambang funding (M6) — opsi ke depan.** Revisi tertulis memakai ambang per-jam apa adanya (0,01%/0,10%) dan mencatat konsekuensi jujur (komponen praktis selalu 0). Opsi bila Septian mau komponen ini bermakna: (a) pakai ambang setara per-8-jam (0,00125%/0,0125% per jam) — perlu revisi tertulis baru + versi skor baru; (b) biarkan seperti sekarang (komponen hampir selalu 0, skor praktis 4-komponen). Agen tidak memilih.
3. **Ambang lag oracle (S4) — opsi ke depan.** Ambang lag dicabut karena data lag tidak pernah ada. Bila suatu hari sumber oracle latency tersedia, guard lag perlu didesain ulang (bukan menghidupkan kembali 120/600 diam-diam).
4. **Alert F1/F3 (Q13/D4).** `perp_deviation` / `exit_high` saat ini display-only. Apakah Septian mau jalur alert bot untuk keduanya (ambang + throttle + teks alert), atau tetap display-only untuk testing week? Bila mau, itu pekerjaan baru, bukan bagian ronde ini.

## Paket deploy (menunggu ACC Septian tersendiri — JANGAN apply tanpa ACC)

Urutan: migrasi dulu, baru kode.

1. **Migrasi ke Turso live** (DENGAN ACC): `python3 qa/apply_migration_2026-11-13.py --db <live>` — atau jalankan 7 pernyataan `migrations/2026-11-13-radar-fix.sql` lewat runner (PRAGMA-guarded, re-runnable). Isi: 2 kolom (`deviations.exit_score_components`, `perp_snapshots.perp_px_source`) + 5 indeks (`idx_poller_health_cycle_ts`, `idx_deviations_ts`, `idx_perp_snapshots_ts`, `idx_deviations_ticker_nocase_ts`, `idx_perp_ticker_nocase_ts`). Verifikasi sesudah apply: `python3 qa/test_radar_fix_schema.py` pada salinan live (atau EXPLAIN QUERY PLAN manual).
2. **Deploy Worker** (`api/worker.js`): M1 regex, M12 filter, M5 payload.
3. **Deploy web** (`web/src/lib/dexscreener.ts` baru, `i18n.ts`, `ticker/[id]/page.tsx`, `api.ts` bila berubah): M11 link, M5 band parsial, M6 label.
4. **Deploy dashboard** (`dashboard/logic.py`, `risk.py`, `app.py`, `turso_read.py`, `i18n.py`): M11 link, M5 band parsial, S5 anchor, N2 gate.
5. **Deploy poller + seed**: `poller.py` (M2/M3/M4/M10/S2/S6/S7/S8/S14/N3 + startup guard), `seed_multichain.py` (M9 UPSERT + S13 note). **Urutan wajib: migrasi → poller → seed --live** (pelajaran insiden P0 12 Nov: jangan edit poller live sebelum migrasi diterapkan).
6. **Dokumen saja** (tanpa deploy): `DESAIN_PENAMBAHAN_2026-11-12.md`, `KUOTA_PENAMBAHAN_2026-11-12.md`, `BACKTEST_ALERT_2026-11-12.md`, `review/REVIEW-DEEPSEEK-RADAR.md` (laporan gabungan terverifikasi Chief).
7. **Tidak ikut deploy / tidak disentuh ronde ini:** `bot.py` (alert live — tidak ada perubahan), ambang lama (alert 1,0%, pool ≥ $100rb, universe ≥ $500rb + ≥ 2 venue), semua data/riwayat live.

## QA — bukti (semua dijalankan di repo lokal, tanpa menyentuh live)

Full suite **21/21 PASS** (exit 0 semua), `py_compile` OK, `tsc --noEmit` web OK:

- Python (14): `test_radar_fix_poller.py` 0 FAIL (68 checks); `test_radar_fix_schema.py` ALL PASS (migrasi 2×, 7 pernyataan, plan 3 indeks baru); `test_no_fullscan.py` PASS (kontrol negatif pra-migrasi FAIL seperti seharusnya); `test_penambahan_2026-11-12.py` 59 PASS 0 FAIL; `test_radar_dashboard_fix_2026-11-13.py` ALL PASS (50 checks); `test_forward_paper_issuer.py` 0 FAIL (6/6); `test_exit_score_bands.py` ALL PASS (18/18); `test_r5_fix.py`, `test_r7_fix.py`, `test_r7_gap_close_alert.py`, `test_r8_fix.py`, `test_r8_gaps.py`, `test_r9_fix.py` (0 FAIL — termasuk GG31/GG32/GG34 di atas), `test_spread_guard.py` — semua 0 FAIL.
- Node (7): `test_radar_fix_worker.mjs`, `test_coverage_2026-11-12.mjs`, `test_r7_worker.mjs`, `test_r8_worker.mjs`, `test_r9_worker.mjs` — semua 0 FAIL; `test_dexscreener_links.mjs` 15/15 PASS; `test_exit_score_bands.mjs` 6/6 PASS.
- Verifikasi dari salinan lokal (sqlite) + baca kode; **tidak ada query/aplikasi ke Turso live, tidak ada deploy**.

## File berubah (40 entri git status: 18 modified + 22 untracked, belum commit)

Diubah: `BACKTEST_ALERT_2026-11-12.md`, `DESAIN_PENAMBAHAN_2026-11-12.md`, `KUOTA_PENAMBAHAN_2026-11-12.md`, `api/worker.js`, `dashboard/app.py`, `dashboard/i18n.py`, `dashboard/logic.py`, `dashboard/risk.py`, `dashboard/turso_read.py`, `forward_paper.py`, `poller.py`, `qa/test_coverage_2026-11-12.mjs`, `qa/test_r9_fix.py`, `schema.sql`, `seed_multichain.py`, `web/src/app/ticker/[id]/page.tsx`, `web/src/lib/api.ts`, `web/src/lib/i18n.ts`.
Baru: `migrations/2026-11-13-radar-fix.sql`, `qa/apply_migration_2026-11-13.py`, `qa/exit_score_bands_fixture.json`, `qa/test_dexscreener_links.mjs`, `qa/test_exit_score_bands.mjs`, `qa/test_exit_score_bands.py`, `qa/test_forward_paper_issuer.py`, `qa/test_no_fullscan.py`, `qa/test_penambahan_2026-11-12.py`, `qa/test_radar_dashboard_fix_2026-11-13.py`, `qa/test_radar_fix_poller.py`, `qa/test_radar_fix_schema.py`, `qa/test_radar_fix_worker.mjs`, `web/src/lib/dexscreener.ts` (+ `review/` — laporan review & file ini). `poller-2026-11-12-NEW.py.bak` juga untracked tetapi **bukan dari ronde ini** (backup P0 12 Nov, sudah ada sebelum ronde fix).

---
*Disusun koordinator ronde fix, 13 Nov 2026 ~01:40 WITA. Semua klaim di atas diverifikasi dari disk (grep + tes), bukan dari laporan worker semata. Dua koreksi koordinator atas laporan worker: (1) laporan worker skema mengklaim migrasi "4 pernyataan" — benar saat ditulis, kini 7 setelah penutup S9; (2) laporan koordinator awal soal test_r9_fix.py mengira GG31/GG32 pre-existing di HEAD — terverifikasi via `git show HEAD` untuk GG31/GG32; GG34 dan F2 baru dari ronde ini.*
