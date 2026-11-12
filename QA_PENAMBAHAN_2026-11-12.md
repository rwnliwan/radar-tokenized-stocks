# QA Penambahan Radar — 5 Fitur + Multichain — 12 November 2026

**Waktu QA:** Kamis 12 Nov 2026, ±21:00–21:25 WITA (13:00–13:25 UTC).
**Pelaksana:** subagent forward-test + QA (bukan Chief).
**Ruang lingkup:** kode penambahan 12 Nov 2026 (poller F1–F4, dashboard,
api/worker `/api/coverage`, web, skema) + seed multichain (bukan kode
saya — hanya diverifikasi dari disk/live).
**Aturan file:** saya HANYA menulis file baru (`forward_paper.py`,
`forward_paper_trades.json`, `FORWARD_TEST_2026-11-12.md`, file ini).
Tidak ada file lain yang saya sentuh.

> **Ringkasan eksekutif — DUA temuan kritis, jangan dilewatkan.**
> 1. **PIPELINE LIVE MATI sejak 12:46 UTC (20:46 WITA).** Kode poller
>     baru sudah jalan di cron TAPI migrasi
>     `migrations/2026-11-12-penambahan.sql` belum diterapkan ke Turso
>     live: `deviations` tanpa kolom `exit_score`, tabel
>     `perp_snapshots`/`monday_gap`/`liquidation_watch` tidak ada.
>     Setiap siklus gagal; `deviations` beku sejak 12:41 UTC. Lebih
>     buruk: **kegagalan ini DISEMBUNYIKAN dari gerbang freshness** —
>     tiap siklus gagal tetap menulis satu baris `poller_health`
>     `cycles_ok=1` palsu (pipeline Hrana tidak atomik), sehingga bot,
>     dashboard, dan API mengira Radar sehat. Detail §2.
> 2. **Lonjakan reads +14,18 jt dalam ±52 menit** (20:23 → 21:15 WITA),
>     dua burst ~200–450 rb/mnt, proyeksi kumulatif naik 165,5J →
>     201,8J (40,4% limit). Berhenti mendadak setelah 21:15 (0 reads
>     dalam 2 menit idle). Atribusi belum terpecahkan — detail §5.

## 1. Keadaan repo (verifikasi disk)

`git status --short` + `git diff --stat` (13:15 UTC):

- **15 file berubah, +2.542 / −92 baris** (belum commit):
  `api/worker.js`, `dashboard/app.py`, `dashboard/i18n.py`,
  `dashboard/logic.py`, `dashboard/risk.py`, `dashboard/turso_read.py`,
  `poller.py` (+862 baris), `schema.sql`,
  `web/src/app/HomeClient.tsx`, `web/src/app/methodology/page.tsx`,
  `web/src/app/ticker/[id]/page.tsx`, `web/src/lib/api.ts`,
  `web/src/lib/csv.ts`, `web/src/lib/i18n.ts`, `web/src/lib/risk.ts`.
- **File baru (untracked)** dari ronde hari ini:
  `DESAIN_PENAMBAHAN_2026-11-12.md`, `KUOTA_PENAMBAHAN_2026-11-12.md`,
  `SEED_MULTICHAIN_2026-11-12.md`, `VERIFIKASI_MULTICHAIN_2026-11-12.md`,
  `BACKTEST_ALERT_2026-11-12.md`, `RADAR-X-HYPERLIQUID-2026-11-12.md`,
  `migrations/2026-11-12-penambahan.sql`, `seed_multichain.py`,
  `verify_multichain.py`, `check_elysium_weekly.py`,
  `qa/test_coverage_2026-11-12.mjs`, `MULTICHAIN_POLLER_2026-11-12.md`
  (ditulis agen sibling selama sesi QA ini),
  `review/` (direktori, muncul selama sesi ini),
  `forward_paper.py`, `forward_paper_trades.json`,
  `FORWARD_TEST_2026-11-12.md`, file ini.
- **Tidak berubah:** `bot.py` (lihat §4.1 — tipe alert baru belum
  dibangun). `schema.sql` BERUBAH (mencerminkan migrasi §3.1–§3.4).
- Lock file `.bot_alert.lock` + `poller.lock` (0 byte, runtime) — bukan
  perubahan kode.

## 2. TEMUAN KRITIS — migrasi belum live, poller gagal, freshness buta

### 2.1 Bukti (live readback Turso, 13:0x UTC)

| Pemeriksaan | Hasil |
|---|---|
| `MAX(ts)` snapshots | `2026-11-12T12:56:00Z` — masih masuk tiap siklus |
| `MAX(ts)` deviations | `2026-11-12T12:41:00Z` — **beku 30+ menit** |
| `PRAGMA table_info(deviations)` | 13 kolom, **tanpa `exit_score` / `exit_score_version`** |
| Tabel `perp_snapshots` | **tidak ada** |
| Tabel `monday_gap` | **tidak ada** |
| Tabel `liquidation_watch` | **tidak ada** |
| `logs/poller-cron.log` | Siklus OK terakhir 12:41 UTC; sejak 12:46 UTC tiap siklus: `CYCLE … FAIL final pipeline: Hrana statement 35 failed: SQLite error: table deviations has no column named exit_score`. PERP: `no such table: perp_snapshots` (12:51, 12:56, 13:11 UTC). |
| `state.json` | `last_perp_failed_at: 2026-11-12T12:56:00Z`, **tanpa `last_perp_check`** (perp belum pernah sukses sekali pun). |

Mekanisme: `run_cycle` merakit SATU pipeline Hrana berisi 35 INSERT
snapshots + 13 INSERT deviations + 1 heartbeat `poller_health`.
Statement ke-35 (INSERT deviations pertama) gagal karena kolom tak
ada — tetapi pipeline Hrana **tidak atomik dan tidak berhenti**:
statement 0–34 (snapshots) sudah ter-commit, lalu handler `except`
menulis heartbeat gagal `cycles_ok=0`. Jadi snapshots tetap jalan,
deviations + heartbeat sukses hilang.

### 2.2 Kegagalan disembunyikan: heartbeat `cycles_ok=1` palsu

`poller_health` per `cycle_ts` sejak 12:46 UTC (verifikasi
`GROUP BY cycle_ts, cycles_ok`):

| cycle_ts | baris ok=0 | baris ok=1 |
|---|---|---|
| 12:31, 12:36, 12:41 | 0 | 1 (asli) |
| 12:46, 12:51, 12:56, 13:01 | 1 | **1 (palsu)** |

Baris `ok=1` itu berasal dari pipeline yang sama yang gagal — INSERT
heartbeat (statement terakhir pipeline) tetap dieksekusi meski INSERT
deviations sebelumnya gagal. Akibatnya semua gerbang yang membaca
"cycles_ok=1 terakhir" mengira Radar sehat:

- `bot.py::load_health_age_minutes` — "menit sejak siklus sukses
  terakhir" membaca `ok=1` palsu → gerbang global 30-menit LOLOS
  (baru gerbang per-ticker `dev_stale` yang masih memblokir alert
  harga — itu yang menyelamatkan `bot --once` di §3.4 dari mengirim
  alert dari data basi).
- `dashboard/logic.py::freshness_status` — `last_success_ts` = ts
  siklus gagal → dashboard TIDAK menampilkan banner stale.
  Bukti: `test_apptest.py` mencetak "live freshness: fresh, no
  banner (as expected)" pada 13:07–13:09 UTC, padahal deviations
  sudah 27 menit tua. Tes itu PASS — dan verdict "fresh"-nya
  sendiri tertipu heartbeat palsu.
- `api/worker.js::healthSummary` — sama (membaca `cycles_ok`).

Ini properti struktural pipeline (sudah ada sejak ronde 8 — GG-16/M1
mengasumsikan heartbeat sukses = siklus sukses), yang baru TERBUKTI
salah ketika INSERT deviations pertama kali gagal. Perbaikan butuh
keputusan Chief (mis. heartbeat sukses ditulis pipeline TERPISAH
hanya bila deviations sukses, atau gerbang freshness memakai
`MAX(ts)` deviations, bukan `cycles_ok`). Saya TIDAK memperbaikinya
(di luar izin file saya + butuh ACC — ini perubahan perilaku live).

### 2.3 Yang belum dibangun (desain §4 vs repo)

| Desain | Status di repo |
|---|---|
| §4.1 poller: alamat per-chain, `run_cycle_perp`, `run_hourly_liquidation`, `run_weekly_monday_gap`, Exit Score di INSERT deviations | **Ada di `poller.py`** (tapi tidak bisa jalan live sebelum migrasi — §2.1). Multichain di poller: **belum** — `XSTOCKS_MINTS` masih Solana-only (dokumen sibling `MULTICHAIN_POLLER_2026-11-12.md` mencatat pekerjaan itu berjalan terpisah). |
| §4.2 bot: `perp_deviation`, `exit_high` | **TIDAK ADA — `bot.py` tidak berubah sama sekali** (grep `perp_deviation\|exit_high` = 0 hit). Alert publik baru belum dibangun; `liquidation_watch` admin-only juga belum ada jalurnya. |
| §4.3 dashboard/risk.py: `exit_score()`, `monday_gap_predict()`, `liquidation_status()` | **Hanya `exit_score_band()` yang ditambah** (23 baris). Fungsi murni itu hanya ada di `poller.py`; dashboard membaca skor tersimpan. Penyimpangan dari desain §4.3 (fungsional setara bila skor tersimpan — tapi duplikasi logika poller-vs-dashboard tidak terjadi karena dashboard tidak menghitung ulang). |
| §4.4 worker: `/api/perp`, `/api/exit-score`, `/api/monday-gap` | **TIDAK ADA.** Hanya `/api/coverage` baru + `/api/latest` + `/api/ticker` yang membaca kolom/tabel baru secara defensif (probe `exit_score` + `perp_snapshots` bila ada). |
| §4.5 web: panel Exit Score / Perp 3-leg / Monday Gap / Liquidation Guard | **Ada** (HomeClient, ticker page, `lib/risk.ts`, `lib/api.ts`, i18n) — panel membaca field yang belum pernah terisi live (semua NULL sampai migrasi + poller jalan). |
| §3 migrasi + schema.sql | File migrasi ada; `schema.sql` diperbarui; **belum diterapkan ke Turso live** (§2.1). |

## 3. Hasil guard

### 3.1 Kompilasi & guard baru — PASS

| Guard | Hasil |
|---|---|
| `python3 -m py_compile poller.py dashboard/app.py dashboard/logic.py dashboard/turso_read.py seed_multichain.py verify_multichain.py check_elysium_weekly.py forward_paper.py` | **PASS** |
| `node --check api/worker.js` + `redirect-worker/worker.js` | **PASS** |
| `node qa/test_coverage_2026-11-12.mjs` | **PASS — 14/14, 0 FAIL** (`/api/coverage` 200, 1 grup live Solana 13 ticker/35 pool, `only_solana_xstocks` true, 6 pending verdicts cocok dengan `logic.py`, seeded-Base flip, anti full-scan: no `SELECT *`, no `COUNT(*)` atas snapshots/deviations/perp_snapshots/liquidation_watch). |
| `web tsc --noEmit` (di dalam test_r9) | **PASS** |

### 3.2 tests_fase2 + qa (skrip standalone, exit code dicatat)

Dijalankan dengan Python sistem kecuali yang berketerangan `.venv`
(`test_trial_components` + `test_apptest` butuh `.venv` — Python
sistem tidak punya `st_aggrid`).

| Tes | Hasil | Catatan |
|---|---|---|
| tests_fase2/test_risk.py | **PASS** | |
| tests_fase2/test_freshness.py | **PASS** | |
| tests_fase2/test_redemption_schedule.py | **PASS** | |
| tests_fase2/test_i18n.py | **PASS** (284 keys) | |
| tests_fase2/test_waitlist_sql.py | **PASS** | |
| tests_fase2/test_trial_components.py | **PASS** (via `.venv`) | Gagal dulu dengan Python sistem (`ModuleNotFoundError: st_aggrid`) — masalah interpreter, bukan kode. |
| tests_fase2/test_bot_dryrun.py | **PASS** | |
| tests_fase2/test_bot_alerts.py | **PASS** | |
| tests_fase2/test_dashboard_data.py | **PASS** | live reads: universe=13, deviations tickers=13, snapshots=208.243, latest health 13:01 UTC (ok=0). |
| tests_fase2/test_apptest.py | **PASS** (via `.venv`) | Dengan caveat §2.2: verdict "live fresh" tertipu heartbeat palsu. |
| tests_fase2/server_boot.sh | **PASS** | HTTP 200, body mengandung "streamlit" ×3. |
| qa/test_spread_guard.py | **PASS** (0 FAIL) | |
| qa/test_r5_fix.py | **PASS** (0 FAIL) | |
| qa/test_r7_fix.py | **PASS** (0 FAIL) | |
| qa/test_r7_gap_close_alert.py | **PASS** (0 FAIL) | |
| qa/test_r7_worker.mjs | **PASS** (0 FAIL) | |
| qa/test_r8_fix.py | **PASS** (0 FAIL) | |
| qa/test_r8_gaps.py | **PASS** (0 FAIL) | |
| qa/test_r8_worker.mjs | **PASS** (0 FAIL) | |
| qa/test_r9_fix.py | **FAIL — 4 checks** | §3.3 — keempatnya disebabkan perubahan hari ini. |
| qa/test_r9_worker.mjs | **PASS** (0 FAIL) | |

### 3.3 test_r9_fix.py — 4 FAIL, semua dari perubahan hari ini

Diverifikasi satu-per-satu terhadap HEAD (`git show HEAD:`):

1. **GG30 "table still shows the stale pill" — REGRESI.**
   Di HEAD, `<tbody>` pertama `HomeClient.tsx` mengandung
   `ticker_stale`; di worktree TIDAK (file masih punya 2 kemunculan
   `ticker_stale`, tapi di blok lain; kini ada 3 tag `<tbody>` —
   tabel baru menempati yang pertama). Restrukturisasi tabel hari
   ini memindahkan/menghilangkan pil stale dari tabel utama.
2. **GG31 registry timestamp-consumer — kode baru belum terdaftar.**
   Situs tak dikenal semuanya di `poller.py` baru: `_latest_redemption_status`
   (l.764), `_perp_due` (l.843–854). Keduanya tidak ada di HEAD.
   Guard ronde-9 ini mensyaratkan tiap situs pemakai timestamp
   didaftarkan — ronde ini tidak mendaftarkannya.
3. **GG32 bare `run_cycle()` tanpa komentar 'heartbeat' — REGRESI
   jarak komentar.** Panggilan `run_cycle(now, …)` l.2001: 15 baris
   di atasnya tidak lagi mengandung kata "heartbeat" karena komentar
   F1 yang disisipkan hari ini mendorong komentar S10 ronde-8 keluar
   dari jendela 15 baris. Di HEAD, panggilan yang sama lolos karena
   komentar S10 masih dalam jendela. Bukan perubahan logika — tapi
   guard-nya gagal.
4. **F2 ASCII-hyphen+digit di string i18n — string baru.**
   Hit: `"Venue ke-2 (communityV3) belum terverifikasi sebagai DEX
   independen; …"` di `dashboard/i18n.py:384` dan
   `web/src/lib/i18n.ts:385`. Tidak ada di HEAD. ("ke-2" memakai
   hyphen ASCII + digit — yang dilarang guard F2 karena dirender
   dengan minus U+2212.)

Keempatnya adalah temuan ronde ini yang WAJIB masuk QA ronde fix
(aturan standing) — dicatat di sini; saya tidak mengubah
`qa/test_r9_fix.py` maupun file sumbernya (di luar izin file saya).

### 3.4 qa_harness.py + qa_post_fix.py — FAIL dengan signature beku

**`qa_harness.py` (live worker vs live DB): rc=1 — 89 PASS, 32 FAIL**
(di kedua run; jumlah per-kategori stabil).

- **18 FAIL "Worker spread / best pool"** (spread 8: CRCLx, GLDx,
  MSTRx, NVDAx, SPYx, TSLAx, AAPLx, MSFTx; best pool 10: CRCLx,
  GLDx, GOOGLx, HOODx, METAx, MSTRx, NVDAx, QQQx, SPYx, TSLAx):
  worker menyajikan harga dari `deviations` beku 12:41 UTC (mis. GOOGLx
  292,85 vs hitung-ulang dari snapshots segar 293,38; GLDx 361,056
  vs 361,22; CRCLx 64,45 vs 64,47) sementara harness menghitung
  ulang dari snapshots yang masih masuk. **Ini efek langsung
  insiden §2.1**, bukan regresi kode worker (worker live adalah
  build lama; `worker.js` baru belum di-deploy).
- **13 FAIL "Worker PoR age (feeds connected)"**: worker=5,99 vs
  db=5,9 (selisih 0,09 jam ≈ 5 menit — drift cache-vs-live).
  Kemungkinan besar toleransi/cache yang sudah ada sebelumnya;
  TIDAK bisa saya pisahkan dari insiden ini tanpa satu run harness
  saat data segar. Dicatat sebagai belum teratribusi.
- **1 FAIL "alerts endpoint mirrors alert_log"**: jumlah baris sama
  (30=30) tapi urutan/isi tidak cocok. Penyebab terverifikasi:
  endpoint mengembalikan 30 EVENT (dedup), sedangkan query DB
  harness mengambil 30 BARIS mentah termasuk duplikat channel
  en/id per event (7 event pasca-8 Nov tercatat 2× — lihat
  backtest §2.1). **Contract mismatch harness-vs-endpoint yang
  sudah ada sebelumnya**, tidak terkait insiden hari ini.

**`qa_post_fix.py`: verdict FAIL — 3 dari 10 checks gagal:**

| Check | Hasil | Detail |
|---|---|---|
| `universe_13_tickers`, `active_pools_35`, `snapshots_fresh_lt20m` (age 1,6 mnt) | PASS | |
| `deviations_fresh_lt20m` | **FAIL** | age 31,6 mnt, ts 12:41 UTC — insiden §2.1 |
| `poller_last_cycle_ok` | **FAIL** | cycles_ok=0 — insiden §2.1 |
| `api_200`, `api_13_tickers`, `api_fields_valid` | PASS | |
| `api_latest_ts_fresh` | **FAIL** | age 31,6 mnt — insiden §2.1 |
| `bot_once_no_eval_error` | PASS | rc=0 — dan **tidak ada alert Telegram yang terkirim** selama QA ini (gerbang per-ticker `dev_stale` memblokir alert harga dari data basi; tidak ada event redemption/PoR yang jatuh tempo). |

## 4. Rekonsiliasi kuota (satu angka, dari ground truth)

Tiga estimasi beredar: desain **±3,4J writes/bln**, subagent kuota
**5,32J/bln**, seed multichain **±4,8J/bln**. Hitung ulang dari ground
truth nyata (bukan asumsi):

- **Pool:** 35 Solana (log poller: `snapshots=35` per siklus) + 115
  baru (15 Base + 24 BNB + 76 Robinhood, seed multichain) = **150 pool**.
- **Ticker:** 13 + 30 = **43 ticker**.
- **Siklus:** 288/hari (5 menit) × 30 hari. **Pengali indeks:** M=3
  snapshots (PK + 2 indeks, desain awal §2.2), M=2 deviations
  (PK + 1 indeks) — konvensi yang sama dipakai ketiga dokumen.

### 4.1 Angka rekonsiliasi

| Komponen | Hitungan | Unit tulis/bln |
|---|---|---|
| snapshots | 150 × 288 × 30 baris × 3 | 3.888.000 |
| deviations | 43 × 288 × 30 baris × 2 | 743.040 |
| **R — snapshots+deviations saja** | | **4.631.040 ≈ 4,63J (46,3%)** |
| + perp (10 market XYZ, sesuai kode — bukan per-ticker) | 10 × 288 × 30 × 3 | 259.200 |
| + liquidation guard (10 ticker XYZ, per jam) | 10 × 24 × 30 × 2 | 14.400 |
| + por hourly (43 ticker) | 43 × 24 × 30 × 2 | 61.920 |
| + monday_gap + poller_health | ~18.000 | 17.652 |
| **R+ — total fitur, basis 288 siklus** | | **≈ 4.984.000 ≈ 5,0J (49,8%)** |

**Koreksi jendela rapat (R++):** laju aktual hari kerja
381–385 baris/ticker/hari (bukan 288) karena burst 1-menit
buka/tutup bursa. Faktor mingguan = (5×383 + 2×288)/(7×288) ≈
**1,2356** pada tabel per-siklus. R++ = (4.631.040 + 259.200) ×
1,2356 + ~94.000 ≈ **6.136.000 ≈ 6,1J/bln (61,4%)**.

**Validasi model terhadap laju aktual:** baseline hari ini
±65.000 writes/hari. Model basis-288 memprediksi ±48.000/hari;
dengan faktor jendela rapat ±59.000/hari — model menjelaskan
±91%, residu ±9% (alert_log, baris redemption/PoR, heartbeat
gagal, dsb.). Model ini dapat dipercaya ±10%.

**Sensitivitas yang mengubah vonis:** bila `perp_snapshots`
ditulis per-ticker (43) bukan per-market (10) — keputusan yang
belum dikunci di desain — tambahannya +855.360/bln: R+ menjadi
±5,84J dan R++ **±7,19J (71,9%)**, dekat ke ambang aksi 80% (8J).
Keputusan perp-per-market vs per-ticker harus dikunci Chief
sebelum chain baru live.

### 4.2 Vonis: mana yang paling dekat?

| Estimasi | Nilai | Selisih vs R+ (5,0J) | Selisih vs R++ (6,1J) | Kenapa meleset |
|---|---|---|---|---|
| **Desain §6.2** | 3,4J | −32% | −44% | Paling jauh. Baseline 1,3J (hitungan baris mentah desain awal, bukan laju aktual 1,95J); pool baru hanya 59 (32 Base + 27 BNB — **Robinhood tidak masuk sama sekali**); tanpa jendela rapat. |
| **Subagent kuota** | **5,32J** | **+7%** | −13% | **Paling dekat untuk TOTAL.** Baseline rate-based benar (1,95J). Meleset sebagian karena pool baru diasumsikan 70 (35+35) vs 115 aktual (−45 pool ≈ −1,17J snapshots) — tapi kelebihan itu hampir tertutup oleh overcount perp per-ticker baru (+0,67J) dan por per-chain. Dua kesalahan berlawanan tanda yang saling meniadakan. |
| **Seed multichain** | 4,8J | −4% | −21% | **Paling tepat untuk hitungan pool.** Kenaikan snapshots+deviations 3,5J-nya persis sama dengan hitung-ulang saya (2,98J + 0,52J); selisih vs R (4,63J) hanya baseline (1,3J vs 1,13J basis-288). Tapi sebagai proyeksi TOTAL ia meremehkan: tanpa fitur (+0,35J) dan tanpa jendela rapat (+1,15J). |

**Kesimpulan:** total jujur = **±5,0J/bln (50%) di atas kertas,
±6,1J/bln (61%) dengan kadensi produksi yang benar-benar berjalan**
— masih di bawah ambang aksi 80%, tapi headroom lebih tipis dari
yang disiratkan ketiga estimasi. Dan setelah §5, yang mengikat
bukan writes melainkan **reads**.

## 5. Turso sesudah + lonjakan reads (angka Platform API)

`turso_usage_check.py` (Platform API, 0 rows_read):

| Cek (WITA) | Reads | Written | Storage | Proyeksi kumulatif |
|---|---|---|---|---|
| Baseline awal 20:23 | 63.541.222 (12,7%) | 801.650 (8,0%) | 76,3 MB | 165,5J |
| 20:59 (cek saya) | 70.944.094 (14,2%) | 802.722 | 76,4 MB | 184,4J |
| 21:15 (cek saya) | 77.725.948 (15,5%) | 803.339 | 76,5 MB | 201,8J |
| 21:17–21:19 (cek saya, 2×) | 77.727.976 (15,5%) | 803.339 (8,0%) | 76,5 MB | 201,8J |
| **Total sesi ini** | **+14.186.754 reads** | +1.689 writes | +0,2 MB | 165,5J → **201,8J (40,4%)** |

Verdict script tetap **OK** (basis kumulatif < 400J). Tetapi:

- **Burst 1 — 20:24→20:59:** +7.402.872 reads (±208.541/mnt).
  Bertepatan dengan ronde backtest (baca live Turso) + ronde
  seed/verify. Hipotesis aritmetika (BELUM terbukti): 37 jendela
  alert × satu full-scan snapshots (±208 rb baris) ≈ 7,7J —
  cocok dengan besarnya burst, tapi query backtest tidak ada di
  depan saya, jadi ini hipotesis, bukan vonis.
- **Burst 2 — 21:00→21:15:** +6.781.854 reads (±448.244/mnt).
  Bertepatan dengan baterai QA saya (apptest 6× load headless,
  harness ×2, post_fix ×2, server_boot ×2) + pekerjaan sibling
  multichain yang bersamaan. Burn BERHENTI mendadak setelah 21:15:
  2 menit idle = 0 reads; menit sebelumnya +2.028 reads.
- **Yang sudah saya periksa dan BUKAN penyebabnya:** dua query
  agregat yang paling dicurigai TERBUKTI memakai indeks
  (`EXPLAIN QUERY PLAN`, 0 reads): query venues-live worker
  (`COUNT(DISTINCT …) FROM snapshots … WHERE ts ≥ now−2h`) memakai
  `idx_snapshots_ts` (SEARCH, ±840 baris jendela 2 jam), dan query
  home dashboard (`… WHERE ts = (SELECT MAX(ts) FROM snapshots)`)
  juga SEARCH via `idx_snapshots_ts` (±35 baris). Semua query
  snapshot lain di worker/app yang saya grep juga berindeks.
  Query langsung saya sendiri semuanya latest-only/kecil (ratusan
  baris).
- **Atribusi: BELUM TERPECAHKAN.** Turso tidak menyediakan
  akuntansi per-query; satu-satunya cara memisahkan adalah
  isolasi sebelum/sesudah per skrip (cek usage, jalankan SATU
  skrip berat, cek lagi). Selama QA ini tidak dilakukan karena
  baterai dijalankan berurutan tanpa cek di antaranya.
- **Angka darurat (jujur):** bila laju burst 448 rb/mnt berlanjut,
  sisa headroom (500J − 77,7J = 422J) habis dalam ±15,7 jam.
  Burst-nya sudah berhenti, jadi ini bukan proyeksi — tapi ini
  menunjukkan satu kueri ceroboh (atau satu ronde QA tanpa
  isolasi) bisa menghabiskan bulan November. Aturan standing
  (larangan full-scan, cek usage berkala) berlaku lebih ketat:
  **jangan jalankan harness/apptest/backtest bersamaan dengan
  pekerjaan live-DB agen lain tanpa cek usage sebelum/sesudah.**

Catatan writes: +1.689 sejak baseline — TERDEPRESI karena
deviations + heartbeat sukses tidak tertulis (§2.1); hanya
snapshots + heartbeat gagal yang masuk.

## 6. Yang TIDAK saya lakukan / tidak teruji

- **Tidak menerapkan migrasi ke Turso live** (tulis skema live =
  di luar izin file + butuh keputusan Chief; ini blocker #1).
- **Tidak mengedit** `poller.py`, `bot.py`, `dashboard/`, `api/`,
  `web/`, `schema.sql`, `seed_*.py` — semua temuan di atas
  dilaporkan, bukan diperbaiki.
- **Tidak deploy** apa pun (worker live = build lama).
- **Tidak mengirim** alert Telegram (0 kiriman selama QA ini).
- **Tidak menjalankan** `check_elysium_weekly.py` (cek mingguan,
  bukan bagian ronde ini) dan `poller.py --test-windows`
  (tidak relevan dengan penambahan).
- **Tidak teruji:** Monday Gap end-to-end (baru jatuh tempo Minggu
  15 Nov), alert `perp_deviation`/`exit_high` (belum ada di bot),
  retensi/agregasi `perp_snapshots` 30-hari (belum ada data),
  idempotensi migrasi 2× (belum bisa — migrasi belum jalan 1×
  pun di live), seed live multichain (masih butuh ACC Septian;
  read-back 0 baris baru — sesuai laporan seed).

## 7. Daftar perbaikan yang harus diputuskan Chief (bukan saya)

1. **Terapkan migrasi 2026-11-12-penambahan.sql ke Turso live**,
   lalu verifikasi siklus OK + `perp_snapshots` terisi. Sampai
   itu terjadi, semua fitur F1–F4 mati di live dan dashboard/API
   menyajikan data beku.
2. **Perbaiki heartbeat palsu (§2.2)** — heartbeat sukses jangan
   satu pipeline dengan data; atau gerbang freshness memakai
   `MAX(ts)` deviations. Sampai diperbaiki, JANGAN percaya
   "fresh" dari dashboard/bot/API.
3. **Empat FAIL test_r9 (§3.3)** masuk ronde fix yang sama
   (GG30 pil stale di tabel, GG31 daftarkan situs timestamp baru,
   GG32 kembalikan kata "heartbeat" dalam 15 baris di atas
   `run_cycle(now)`, F2 ganti "ke-2" tanpa hyphen ASCII).
4. **Bangun alert bot F1/F3 + route worker §4.4** yang belum ada,
   atau nyatakan resmi ditunda.
5. **Kunci perp per-market vs per-ticker** (§4.1) sebelum chain
   baru live — selisihnya ±1J writes/bln.
6. **Isolasi QA berat:** cek usage sebelum/sesudah tiap skrip
   berat (harness/apptest/backtest) sampai sumber burst §5
   teridentifikasi.

## 8. File laporan

- `QA_PENAMBAHAN_2026-11-12.md` — file ini.
- `FORWARD_TEST_2026-11-12.md` — forward test sprint (3 observasi,
  1 paper trade HOODx terbuka, 0 tertutup).
- `forward_paper.py` + `forward_paper_trades.json` — skrip +
  ledger observasi paper.
- Bukti mentah: `/tmp/qa_harness_out.txt` (harness lengkap),
  `/tmp/qa_post_fix_out.json`, `/tmp/forward_obs23.log`,
  log usage di
  `~/workspace/goals/radar-tokenized-stocks-kabar-berkala/hidden_files/usage-api-log.md`.

## 9. Cek ulang pasca-revert P0 (induk, 2026-11-12 21:23–21:30 WITA)

- Pipeline pulih: siklus cron 13:26 UTC OK (35 snapshot, 13 deviasi) — revert `poller.py` ke HEAD terbukti tahan, bukan cuma siklus manual.
- `qa/test_r9_fix.py`: **0 FAIL** (was 4). GG31/GG32 hilang sendiri setelah revert (signature insiden). GG30: locator test diperbaiki — tbody pertama kini tabel cakupan (baru 12 Nov), bukan tabel utama; test kini menarget tbody tabel utama via `exit_score_col` (bukan pelonggaran ambang: tabel utama tetap menunjukkan stale pill, baris 765). F2: "Venue ke-2" → "Venue kedua" di `dashboard/i18n.py` + `web/src/lib/i18n.ts` (2 file).
- `qa_post_fix.py`: **verdict PASS** (was FAIL: `deviations_fresh_lt20m`, `poller_last_cycle_ok`, `api_latest_ts_fresh` — semua signature insiden).
- `qa_harness.py`: 32 → **14 FAIL**. Yang hilang: 18 spread/best-pool (signature harga beku). Yang tersisa, keduanya pola lama (bukan dari build hari ini): 13× Worker PoR age (contoh TSLAx worker=6,29 jam vs db=5,9 jam — selisih ~24 menit, drift cache hourly; perlu keputusan: longgarkan toleransi atau worker baca fresh) + 1× alerts endpoint mirrors alert_log (30 baris dua-duanya, baris pertama beda — mismatch dedup/ordering lama).
- Sisa gap sebelum deploy: bot.py belum berubah (alert `perp_deviation`/`exit_high` belum ada); route `/api/perp`, `/api/exit-score`, `/api/monday-gap` belum ada; forward test penuh 4 minggu belum jalan.
