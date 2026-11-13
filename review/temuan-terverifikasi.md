# Temuan DeepSeek Radar 12 Nov 2026 — TERVERIFIKASI (masuk ronde fix)

**Sumber:** `review/review_deepseek_radar_raw.txt` (vonis REVISE, skor 5/10) — tiap temuan di bawah sudah diverifikasi Chief ke sumber (kode, dokumen, hitung ulang, cek live, EXPLAIN lokal). Bukti lengkap per temuan: `review/HASIL_DEEPSEEK_2026-11-12.md`.
**Aturan:** hanya temuan di file ini yang masuk fix. Noise dicatat di HASIL_DEEPSEEK §7 dan TIDAK diperbaiki.
**Perintah Septian 00:01 WITA 13 Nov:** yang memang salah diperbaiki dulu, baru kabari Septian singkat + file .md untuk review Instinct.

## MUST-FIX (13) — urutan yang disarankan

1. **M1 — Regex ticker Worker menolak semua ticker multichain.** `api/worker.js:1129,1137` `/^[A-Z0-9]+X$/` → ganti `^[A-Z0-9]{2,12}$` + validasi keberadaan lewat `universe`. Fixture QA: tiap ticker di `universe`, `/api/ticker` harus 200. (Live: TSLAr → 400, TSLAx → 200.)
2. **M4 — Redemption Exit Score bocor antar-issuer.** `poller.py:751-752` tambah `WHERE issuer = ...` (map issuer per ticker dari `universe`); perbaiki juga `dashboard/app.py:406-415` `get_redemption_latest` (docstring "one xStocks rule" sudah salah).
3. **M2 — Monday Gap 13:30 UTC hardcode.** `poller.py:1116` hitung `mon_open` dari `ZoneInfo("America/New_York")` (NY open 16 Nov 2026 = 14:30 UTC).
4. **M3 — Kalibrasi Monday Gap menghitung baris, bukan akhir pekan.** `poller.py:1035` → `COUNT(DISTINCT week_start)`. Guard: `calib == 5 * distinct_weekends`.
5. **M5 — `components_present` tidak disimpan.** Tambah kolom `exit_score_components INTEGER` (migrasi baru, bukan edit migrasi lama) + isi dari `_sc["components_present"]`; `exit_score_band(score, components)` → `None` bila `components < 3`; alert `exit_high` syaratkan `components >= 3`. (Bukti: "parsial 1 komponen → 25/25 = 100,0" — `review/HASIL_TEST.md:165`.)
6. **M7 + M8 — Dua indeks (kuota).** `CREATE INDEX idx_health_cycle ON poller_health(cycle_ts)` (+ `idx_health_ok_cycle`), `CREATE INDEX idx_deviations_ts ON deviations(ts)`; `ORDER BY ts DESC, id DESC` → `ORDER BY ts DESC` di `loadLatest`. Verifikasi `EXPLAIN QUERY PLAN` → tanpa `SCAN`.
7. **M9 — Seed UPSERT, bukan DELETE.** `seed_multichain.py:125-126,169`: ganti DELETE+INSERT dengan `UPDATE universe SET status='inactive'` / `UPDATE pools SET is_active=0` + INSERT/UPDATE yang lolos. (Tidak ada `PRAGMA foreign_keys` — cabang yatim yang berlaku.)
8. **M10 — Startup guard poller.** `poller.py::main()`: cek `PRAGMA table_info(deviations)` + `sqlite_master` untuk 3 tabel baru sebelum siklus pertama; bila kurang → log + `sys.exit(2)` "jalankan migrasi 2026-11-12 dulu".
9. **M11 — Link DEX hardcode `/solana/`.** `web/src/app/ticker/[id]/page.tsx:428`, `dashboard/app.py:1760` → `https://dexscreener.com/${chain}/${pair}` dari `v.chain`. Test: host path == `pool.chain` per venue.
10. **M12 — Filter tabel pending.** `dashboard/logic.py::build_coverage` + `api/worker.js::loadCoverage`: buang baris pending yang chain-nya sudah live; perbarui teks token sesuai jumlah yang benar-benar di-seed.
11. **M6 — Funding 8× terlalu ketat.** Revisi tertulis bertanggal (bukan patch diam-diam): ambang → ≤0,00125% → 0, ≥0,0125% → 15; **atau** relabel "per interval" + penjelasan. Keputusan Chief + Septian.
12. **M13 — Lisensi DexScreener.** Keputusan tertulis Septian sebelum ekspansi berikutnya: (a) cek ToS primer, (b) bila ambigu — sembunyikan chain baru di balik flag, atau (c) tampilkan hanya agregat turunan. (`CHECKLIST_QA.md` F5 BELUM DILAKUKAN.)
13. **S1 (naik kelas dari SHOULD karena P0) — Migrasi self-idempotent.** Bungkus dua `ALTER TABLE` (`migrations/2026-11-12-penambahan.sql:72-73`) dalam runner yang membaca `pragma_table_info` (pola `migrations/2026-11-09-pools-excluded.sql`).

## SHOULD-FIX (14)

- **S2** — Kolom `px_source TEXT` (`mark`/`mid`) di `perp_snapshots`, atau jangan fallback (tulis `perp_px NULL`).
- **S3 (sebagian)** — Perbaiki label satuan di **`DESAIN_PENAMBAHAN_2026-11-12.md:180,263`** ("funding 8 jam" → "per funding interval (hourly)"); bukan di `schema.sql`/migrasi (di sana frasa itu tidak ada).
- **S4** — Revisi desain bertanggal yang mencabut ambang lag 120/600 dtk + kalimat di web: "v1 mengukur divergensi mark-vs-oracle saja; umur oracle tidak terukur dari endpoint publik".
- **S5** — Port pola per-ticker anchor `worker.js` (P2-M2) ke `dashboard/app.py::get_venues_live`, atau hapus KPI itu dan ambil dari `/api/health`.
- **S6** — Reset `state["liquidation_alert_tickers"] = {}` di setiap jalur gagal `run_hourly_liquidation`, atau simpan `{"tickers", "ts"}` dan anggap kosong bila `ts` > 2 jam.
- **S7** — Cabang `wd == 0`: bila minggu lalu terlewat, tulis `gap_note`; `outcome='unvaluable'` setelah 7 hari.
- **S8** — Dokumentasikan keterbatasan v1 (komponen redemption = "pintu tertutup", bukan gradien), atau bedakan `closed` dengan sisa jam sampai Senin.
- **S9** — Guard anti-full-scan baru: jalankan `EXPLAIN QUERY PLAN` tiap query baru pada salinan DB, gagal bila ada `SCAN <tabel>` tanpa `USING INDEX`.
- **S10** — Promosikan harness ke `qa/test_penambahan_2026-11-12.py` (saat ini hanya di /tmp yang sudah hilang kena restart VM).
- **S11** — Satu paragraf tertulis: "backtest ini hanya menguji alert spread hari kerja; F1/F3 dan kaki akhir pekan = forward-only, n=0 per 12 Nov".
- **S12** — Hitung ulang kuota dengan 356 siklus/hari (≈4,7 jt writes/bln, 47%); varian 71 pool (≈3,6 jt, 36%) sebagai default.
- **S13** — Isi `window_note_en` di seed dari `ISSUER_META` versi EN (atau tambah pasangan EN).
- **S14** — Satu query gabungan OI-24h untuk semua ticker, atau cache OI-24h di `state.json` sekali per jam.

## NIT (5)

- **N1 (sebagian)** — Fixture string-lock untuk batas band 40/70 di `dashboard/risk.py` + `web/src/lib/risk.ts` (2 tempat; klaim tempat ketiga di `bot.py` salah — tidak ada).
- **N2** — Label "basi" pada deviasi perp di UI bila `perp_ts` > 15 menit (`dashboard/app.py`, `page.tsx`).
- **N3** — `median_depth_7d_date` per ticker, atau hitung ulang semua ticker universe sekali sehari.
- **N4** — `CHECK (outcome IN ('pending','accurate','inaccurate'))` di migrasi berikutnya.
- **N5 (diperbaiki rumusannya)** — Perbarui string `coverage_short` yang basi ("13 xStocks / 35 Solana") atau hapus fallback statisnya; `coverage_live_line` sudah benar dan tidak perlu diubah.

## Addendum verifikasi (temuan baru, masuk fix juga)

- **V1 — Teks metodologi mengklaim alert yang tidak ada.** `web/src/lib/i18n.ts:184-185`: "Scores of 70 or above also raise one alert" + "an alert fires when |deviation| reaches 1.0%" — keduanya belum ada di `bot.py`. Perbaiki teks + hapus status basi "no scores stored yet" / "no perp snapshots stored yet".
- **V2 — Docstring `get_observed_dates` salah klaim indeks** (`dashboard/app.py:170` "indexed on cycle_ts") — perbaiki komentar (indeksnya ditambah di M7).
- **V3 — M4 + M9 diperbaiki bersama** sebelum re-verify mingguan pertama (jendela kontaminasi M4 hanya terbuka tiap re-seed).

## QA guard yang wajib ditambah di ronde fix yang sama (aturan standing)

- Fixture: regex ticker Worker menerima semua sufiks universe (M1); `calib == 5 * distinct_weekends` (M3); `exit_score_components` tersimpan + band None bila < 3 komponen (M5); link DEX == chain pool (M11); pending terfilter bila chain live (M12); band 40/70 konsisten 2 tempat (N1).
- Guard EXPLAIN QUERY PLAN anti-SCAN (S9).
- Catatan: temuan yang string-lockable → fixture guard; yang semantik → kelas review. Tidak ada penghapusan fitur yang sudah ada.

## Yang TIDAK masuk fix (noise)

Lihat `HASIL_DEEPSEEK_2026-11-12.md` §7: recalc #18 (115 vs 106), Q14 "2–5/minggu" (benar ≈9–10), S3 lokasi kutip, N1 tempat ketiga bot.py, N5 sebagaimana ditulis. **Jangan diperbaiki, jangan dijadikan guard.**
