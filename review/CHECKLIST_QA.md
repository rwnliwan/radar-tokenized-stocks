# Checklist QA — Sebelum Deploy Penambahan Radar 12 Nov 2026

Checklist ini harus **lolos semua** sebelum deploy. Satu butir FAIL =
deploy ditahan. Acuan: `DESAIN_PENAMBAHAN_2026-11-12.md` §5.4 (guard
yang sudah ada + guard baru), §6.3 (larangan full-scan), §7.1 (ACC),
dan temuan paket review ini.

**Status saat paket disusun (12 Nov 2026 ±21:05 WITA):** sebagian besar
butir di bawah ini **BELUM terverifikasi lolos** — lihat kolom "Status
saat paket disusun". Checklist ini adalah daftar kerja, bukan bukti
lolos. Jangan deploy berdasarkan checklist ini sebelum tiap butir
dicentang dengan bukti (perintah + output).

---

## A. Gerbang ACC (tidak jalan tanpa ACC eksplisit)

| # | Butir | Status saat paket disusun |
|---|---|---|
| A1 | ACC Septian atas **desain** (bukan hanya ACC bangun) | ACC bangun 20:22 WITA ada; ACC desain sebagai dokumen — konfirmasi Chief |
| A2 | ACC Septian atas **deploy live** (sesudah build + QA lolos + review DeepSeek) — kabari dia DULU sebelum deploy update besar | BELUM — deploy belum boleh jalan |
| A3 | ACC Septian atas **seed live** (`RADAR_SEED_CONFIRM=ACC-2026-11-12`) — tanpa ini `seed_multichain.py --live` menolak (exit 2, terverifikasi) | BELUM — 0 baris baru di Turso (read-back terverifikasi) |
| A4 | ACC Septian atas **cron Elysium mingguan** (`check_elysium_weekly.py`, Minggu 09:46 WITA) — di mana jalan, siapa menerima hasil | BELUM — cron belum dibuat |
| A5 | ACC Septian atas **publikasi alert baru** (`perp_deviation`, `exit_high`) — tayang publik sejak hari pertama (label eksperimental) atau admin-only dulu selama forward test 4 minggu? (Rekomendasi induk: admin-only dulu) | BELUM — dan lihat D4: `bot.py` belum berubah, jadi alert ini belum ada |
| A6 | ACC Septian atas **pengiriman `liquidation_watch` ke publik** setelah kalibrasi (v1 admin-only) | BELUM |

## B. Migrasi & skema (urutan adalah gerbang)

| # | Butir | Status saat paket disusun |
|---|---|---|
| B1 | **Migrasi dulu, baru poller.** `migrations/2026-11-12-penambahan.sql` diterapkan ke Turso live SEBELUM poller baru deploy (INSERT `deviations` baru merujuk `exit_score` — poller duluan = gagal tiap siklus) | BELUM — migrasi belum dijalankan |
| B2 | Migrasi idempotent: `CREATE TABLE/INDEX IF NOT EXISTS` jalan 2× tanpa error; dua `ALTER TABLE` hanya bila `PRAGMA table_info(deviations)` belum memuat kolomnya (cek dulu — ALTER gagal bila kolom sudah ada) | TERUJI di sqlite lokal (harness 84 PASS) — BELUM di Turso live |
| B3 | `PRAGMA table_info(deviations)` memuat `exit_score` + `exit_score_version`; ketiga tabel baru ada dengan indeksnya | BELUM (live) — teruji lokal |
| B4 | `schema.sql` cocok dengan hasil migrasi (satu sumber kebenaran) | Kode cocok (diff +54) — verifikasi live menyusul B1 |
| B5 | Tidak ada kolom yang ditulis tanpa sumber: `liq_px_estimate`/`distance_pct` tetap NULL; `funding`/`oi` NULL bila API tidak menerbitkannya; ticker tanpa perp (SPY/QQQ/GLD) tidak punya baris `perp_snapshots` | TERUJI di harness live-read (10 baris perp, tanpa SPY/QQQ/GLD; liq/distance selalu NULL) |

## C. Guard QA repo (desain §5.4 — guard lama + guard baru)

| # | Butir | Status saat paket disusun |
|---|---|---|
| C1 | Guard lama tetap lolos (tidak ada yang dimatikan): `qa_harness.py`, `qa_post_fix.py`, `tests_fase2/` (bot alerts, dashboard data, freshness, i18n, redemption schedule, risk, trial components, waitlist SQL), `qa/test_spread_guard.py`, semua `qa/test_r*_fix.py` | BELUM DIJALANKAN ULANG saat paket disusun — tidak ada bukti run terbaru |
| C2 | **Guard baru 1 — jumlah bobot:** komponen Exit Score = 100 (30+25+20+15+10) dan confidence Monday Gap = 100 (30+25+20+25) — tes unit di `risk.py` | BELUM ADA di repo (hanya teruji di harness scratch `/tmp`) |
| C3 | **Guard baru 2 — ambang alert:** perp 0,99% → tidak ada alert; 1,00% → alert; exit_score 69 → tidak ada alert; 70 → alert | BELUM ADA di repo — dan `bot.py` belum berubah (D4), jadi tidak ada yang bisa dites |
| C4 | **Guard baru 3 — skema:** lihat B2/B3 | TERUJI lokal, BELUM live |
| C5 | **Guard baru 4 — anti full-scan (§6.3):** grep kode baru — tidak ada `COUNT(*)` / `SELECT *` ke `snapshots` / `deviations` / `perp_snapshots` / `liquidation_watch` di jalur cron/dashboard/API | LOLOS — `qa/test_coverage_2026-11-12.mjs` (15 PASS) + harness (grep `poller.py`) |
| C6 | **Guard baru 5 — multichain gate:** tiap ticker baru wajib membawa bukti total depth ≥ $500 rb + ≥ 2 venue (seed dengan ticker di bawah ambang → ditolak, tercatat di `universe_excluded.md`) | BELUM ADA di repo (verifikasi manual di dokumen seed; `universe_excluded.md` belum diperbarui dengan Ondo/Robinhood/Elysium) |
| C7 | **Guard baru 6 — Monday Gap:** tepat 1 baris per ticker per minggu (jalankan `run_weekly_monday_gap` 2× untuk minggu yang sama → tetap 1 baris per ticker) | TERUJI di harness (2× run → 2 baris) — BELUM ADA di repo |
| C8 | **Guard baru 7 — bahasa:** tidak ada kata "aman"/"disarankan"/"beli"/"jual" di pesan alert baru dan panel baru (ID maupun EN) | BELUM ADA di repo (belum ada pesan alert baru — lihat D4) |
| C9 | **Guard baru 8 — retensi:** agregasi per jam mencakup `perp_snapshots` (baris mentah > 30 hari teragregasi + terhapus, dicatat di `poller_health`) | BELUM ADA di repo (belum ada data > 30 hari) |

## D. Kelengkapan build (penyimpangan diff — harus dijawab sebelum deploy)

| # | Butir | Status saat paket disusun |
|---|---|---|
| D1 | `bot.py`: `perp_deviation` + `exit_high` di `evaluate_alerts()`, `format_alert()` baru, gabungan perp di `load_live_tickers()` — atau penjelasan tertulis bila sengaja ditunda | **BELUM ADA — `bot.py` tidak berubah sama sekali** |
| D2 | Poller multichain: alamat token per (chain, issuer, ticker) + batch per chain (Base/BNB/Robinhood) — atau penjelasan tertulis bila sengaja ditunda | **BELUM ADA — poller masih Solana-only** |
| D3 | Route API desain §4.4 (`/api/perp`, `/api/exit-score`, `/api/monday-gap`, `series=` di `/api/history`) — atau keputusan tertulis bahwa `/api/coverage` + perluasan `/api/latest` menggantikannya | **TIDAK ADA** — pengganti (`/api/coverage` + `/api/latest`) sudah dibangun; keputusan tertulis belum ada |
| D4 | Metodologi web: seksi `monday_gap_v1` + `liq_guard_v1` di halaman metodologi (rumus + bobot + cara hitung ulang) | **BELUM ADA** — hanya seksi `exit_score` + `perp` (dan isinya di string i18n, belum dinilai) |
| D5 | `oracle_lag_s`: keputusan tertulis — hapus ambang lag dari desain (§2.4) lewat revisi bertanggal, atau sumber ukur lag ditemukan | **BELUM ADA** — kolom dihilangkan diam-diam dari skema (komentar kode ada, revisi desain belum ada) |
| D6 | Konvensi ticker Robinhood diputuskan Chief: sufiks `r` (`TSLAr`) vs `TSLA-RH` | **BELUM** — seed memakai `r`, butuh konfirmasi sebelum live pertama |

## E. Seed & universe

| # | Butir | Status saat paket disusun |
|---|---|---|
| E1 | Seed `--live` hanya dengan ACC (A3) + nilai env `RADAR_SEED_CONFIRM` | Siap — penolakan tanpa ACC terverifikasi (exit 2) |
| E2 | Tiap ticker yang di-seed lolos gerbang §1.1 (total ≥ $500 rb + ≥ 2 venue) dengan angka live, bukan angka dated (NVDAB/SPYB 20 Sep 2026 tidak boleh dipakai) | Terverifikasi di dokumen (33 lolos dari 127; SPYB dikoreksi GAGAL $353.725 base-side) |
| E3 | Yang gagal masuk `universe_excluded.md` beserta alasannya (Ondo/Ethereum, Robinhood Chain — bila belum masuk — Elysium, Hyperliquid spot wrapped, + semua FAIL riset 12 Nov) | BELUM — `universe_excluded.md` belum diperbarui |
| E4 | Ticker dekat garis ambang (TSLAc $533.364, MSFTc $582.084, AAPLc $727.045) dijadwalkan verifikasi ulang mingguan; seed idempotent (DELETE + INSERT ulang per ticker) | Rencana ada; jadwal belum dibuat |
| E5 | Opsi hemat diputuskan Chief: seed 115 pool penuh (≈ +3,5 jt writes/bln) atau `--max-pools-per-ticker 3` (71 pool, ≈ +2,4 jt/bln) | BELUM DIPUTUSKAN |

## F. Kuota & performa

| # | Butir | Status saat paket disusun |
|---|---|---|
| F1 | Retensi `snapshots` 30 hari + agregasi `snapshots_hourly` **terbukti jalan** sebelum chain baru live (storage naik 4,7 MB/hari tanpa bukti penahan) | BELUM TERBUKTI |
| F2 | Checkpoint usage hari ke-2, ke-4, ke-7 setelah chain baru live (`turso_usage_check.py`); bila laju writes memproyeksikan >80% (8J/bln), mitigasi hari itu juga (perp 5→15 mnt, bekukan chain terbaru, percepat agregasi) | Jadwal belum dibuat (belum ada chain live) |
| F3 | Semua bacaan dashboard/bot/API latest-only via indeks — tidak ada query baru yang memindai `snapshots` | LOLOS untuk kode baru (C5) |
| F4 | Lonjakan reads +7,40J (12 Nov 20:23→±21:00 WITA, rate 208.541/mnt) dijelaskan penyebabnya sebelum deploy (cek `usage-api-log.md`, `logs/poller-cron.log`) | **BELUM DIJELASKAN** — lihat `HASIL_TEST.md` §4 + `PERTANYAAN_TERBUKA.md` Q12 |
| F5 | Lisensi DexScreener dicek dari ToS primer sebelum display publik chain baru (desain §7.2 butir 7) | BELUM DILAKUKAN |

## G. Bahasa, kejujuran & cakupan web

| # | Butir | Status saat paket disusun |
|---|---|---|
| G1 | Tidak ada kata "beli"/"jual"/"aman"/"disarankan" di pesan alert baru dan panel baru (ID maupun EN) | BELUM ADA yang bisa dites (C8) |
| G2 | Banner cakupan jujur: hanya Solana + xStocks yang live hari ini; Base/BNB/Robinhood "terverifikasi, belum live" (bukan "live"); Ondo "gagal", Elysium "belum aktif", Hyperliquid spot "monitor saja" — di semua permukaan (web + dashboard + API `/api/coverage`) | Teruji di tes coverage (pending list 6 vonis cocok) — verifikasi visual web belum dilakukan |
| G3 | Label "eksperimental" tampil di semua permukaan untuk F2 + F4 (dan alert publik baru selama forward test) | Belum diverifikasi visual |
| G4 | Skor parsial kelihatan parsial: jumlah komponen tersedia + versi selalu ditampilkan bersama Exit Score / Monday Gap (tidak ada skor parsial yang tampil sebagai skor penuh) | Teruji di harness (flag `partial`) — verifikasi visual belum dilakukan |
| G5 | Nilai NULL dirender "tidak tersedia"/"—", bukan 0 (exit_score, perp, funding, liq) | Teruji di worker (`/api/latest` nullable) + `exit_score_band(None)` → None — verifikasi visual belum dilakukan |

## H. Testing & bukti

| # | Butir | Status saat paket disusun |
|---|---|---|
| H1 | Backtest dibaca dengan caveat (§1.3 `HASIL_TEST.md`): angka 100% tidak diklaim sebagai akurasi akhir pekan; kaki akhir pekan masih 0/0 | Dokumen backtest sudah jujur soal ini — Chief memastikan tidak ada klaim yang melebih-lebihkan di web |
| H2 | Forward test dirancang + dimulai (file `FORWARD_TEST_2026-11-12.md` belum ada — dibuat saat forward test berjalan, bukan sebelumnya) | BELUM — wajar, karena fitur belum live |
| H3 | Review DeepSeek selesai + tiap temuan terverifikasi Chief (temuan = usulan; hanya yang terverifikasi masuk fix; noise dicatat, tidak diperbaiki) | BELUM — paket review ini baru disiapkan, belum dikirim |
| H4 | Temuan DeepSeek terverifikasi yang string-lockable → fixture guard QA di ronde fix yang sama (aturan standing) | Menunggu H3 |
| H5 | Tidak ada fitur/lesson yang dihapus dalam build ini (aturan standing anti-hapus; hanya Septian yang boleh memerintahkan penghapusan) | Terverifikasi dari diff: 2.180 insertions, 34 deletions — deletions hanya penyesuaian baris lama, bukan penghapusan fitur (reviewer diminta mengonfirmasi) |

## I. Deploy

| # | Butir | Status saat paket disusun |
|---|---|---|
| I1 | Semua butir A–H di atas lolos (atau dicatat sebagai pengecualian tertulis dengan alasan + tanggal oleh Chief) | BELUM |
| I2 | ACC deploy tersendiri dari Septian (A2) | BELUM |
| I3 | Setelah deploy: verifikasi live (halaman per ticker, `/api/latest`, `/api/coverage`, banner cakupan) + cek Turso hari ke-2/4/7 (F2) | Menunggu deploy |
