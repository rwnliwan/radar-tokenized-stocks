# Forward Test PAPER — Radar Tokenized Stocks (Sprint) — 12 November 2026

**Waktu:** Kamis 12 Nov 2026, 21:03–21:13 WITA (13:03–13:13 UTC).
**Pelaksana:** subagent forward-test + QA (bukan Chief).
**Repo:** `~/workspace/radar-tokenized-stocks`
**Skrip:** `forward_paper.py` · **Ledger lokal:** `forward_paper_trades.json`
(Turso TIDAK pernah ditulis oleh forward test ini.)

> **Baca dulu — ini SPRINT, bukan forward test 4 minggu.**
> DESAIN §5.2 mensyaratkan forward test paper minimal 4 minggu (ideal 8)
> dengan ≥ 4 akhir pekan. Yang dijalankan di sini adalah **sprint 10 menit,
> 3 observasi** — tujuannya membuktikan PIPA (kaki live → skor → catatan
> kertas → evaluasi ulang), BUKAN mengukur akurasi sinyal apa pun. Tidak
> ada angka akurasi di laporan ini, karena tidak ada yang bisa diukur
> dalam 10 menit. Siapa pun yang mengutip laporan ini sebagai "forward
> test selesai" sedang salah baca.

## 1. Metode

### 1.1 Dry-run mode poller.py (read-only, tanpa tulis)

| Mode | Ada? | Hasil |
|---|---|---|
| `--dry-run-perp` (F1) | ya | **PASS** — 10/10 ticker, exit 0. Mark + funding + OI semua terisi. Funding \|rate\| ≤ 0,0047% (komponen funding Exit Score = 0 untuk semua ticker). |
| `--dry-run-liquidation` (F4) | ya | **PASS** — 10/10 ticker, exit 0, **0 alert** (warning/critical). Divergensi mark-vs-oracle ≤ 0,094% (terbesar NVDAx). `liq_px_estimate` NULL di semua baris — sesuai desain §2.4 (belum ada sumber level likuidasi terverifikasi; tidak difabrikasi). |
| `--dry-run-monday-gap` (F2) | ya | **PASS (no-op)** — exit 0, tidak mencetak apa pun. Benar: prediksi hanya menyala Minggu ≥ 22:00 UTC, outcome fill hanya Senin; hari ini Kamis. Bukan kegagalan. |
| `--dry-run-hourly` | ya | **PASS** — redemption `open`, PoR age 5,8 jam (feed 07:11 UTC), 13/13 token. |
| `--dry-run-multichain` | **TIDAK ADA** | Tidak ada flag itu di `poller.py` (grep: hanya `--dry-run-hourly/perp/liquidation/monday-gap`). **Tidak dijalankan** — menjalankan `poller.py` dengan flag tak dikenal akan jatuh ke `main()` dan menjalankan SIKLUS LIVE (tulis ke Turso), jadi sengaja tidak dicoba. |

### 1.2 `forward_paper.py` — observasi paper trade

Aturan paper **PRE-REGISTERED di header skrip sebelum observasi pertama**
(bukan ditala dari hasil):

- **OPEN** "would-exit" bila `exit_score_v1 ≥ 70` ATAU
  `|dev_perp_vs_token_pct| ≥ 1,0%` (ambang desain §2.1/§2.3).
- **CLOSE** bila pada observasi BERIKUTNYA `dev_vs_median_pct < 0,5%`
  DAN `exit_score < 40` (cerminan §5.4 "kembali < 0,5%").
- Trade yang tidak memenuhi aturan close dalam jendela sprint tetap
  **OPEN** — dilaporkan terbuka, tidak pernah ditutup diam-diam dan
  tidak pernah dinilai menang/kalah.

Kaki data per observasi (semua live, read-only):

- **Spot (fresh):** batch DexScreener live, agregasi sama seperti
  `run_cycle` (filter `LIQ_MIN` $100 rb + guard 25% cross-pool median).
  Termasuk fallback per-token seperti `run_cycle` (S5) — observasi 1
  sempat hanya 10/13 ticker karena batch DexScreener terpotong (~30
  pair); fallback ditambahkan, observasi 2–3 penuh 13/13.
- **Perp:** `fetch_xyz_market_data()` live (Hyperliquid xyz).
- **Redemption:** 1 baris latest-only dari Turso.
  `median_depth_7d` dibaca dari `state.json` (dihitung poller hari ini)
  — 0 reads Turso.
- **Monday Gap:** dicatat `not_due` di semua observasi (Kamis; prediksi
  baru jatuh tempo Minggu 15 Nov 2026 ≥ 22:00 UTC).
- **Deviations Turso:** HANYA dibaca untuk melaporkan staleness — lihat
  caveat §3.1 (beku sejak 12:41 UTC).

Biaya baca per observasi: ~65 baris latest-only (pools + universe +
13× latest deviations + 1 redemption). Dapat diabaikan.

## 2. Hasil — 3 observasi, 10 menit

| Observasi (UTC) | Ticker tercakup | Exit Score (min–maks) | dev_perp_vs_token (min–maks) | Paper trade dibuka | Ditutup |
|---|---|---|---|---|---|
| 13:03 | 10/13 (tanpa fallback) | 11,7 – 22,9 | −0,706% – −0,007% | 0 | 0 |
| 13:08 | 13/13 | 11,2 – 22,9 | **−1,175%** – −0,043% | **1 (HOODx)** | 0 |
| 13:13 | 13/13 | 12,3 – 23,1 | −0,772% – +0,288% | 0 | 0 |
| **Total sprint** | | | | **1 dibuka, 0 tertutup, 1 masih terbuka** | |

### 2.1 Satu-satunya paper trade: HOODx

- **Dibuka:** 13:08 UTC. Alasan: `|dev_perp_vs_token| = −1,175% ≥ 1,0%`
  (perp 81,58 vs spot dw 82,55). Exit Score saat itu hanya 16,7
  ("tekanan keluar rendah") — pemicu murni dari kaki perp, bukan dari
  Exit Score.
- **Status akhir sprint: MASIH TERBUKA.** Observasi 13:13: dev_perp
  menyempit ke −0,717%, tapi aturan close tidak terpenuhi (dan tidak
  bisa terpenuhi untuk HOODx — lihat §3.4).
- **Ini bukan sinyal beli/jual.** Ini satu baris kertas yang menunggu
  observasi berikutnya. Tidak ada kesimpulan akurasi yang bisa ditarik
  dari 1 trade terbuka dalam 10 menit.

### 2.2 Exit Score — semua "rendah"

Semua skor 11,2–23,1 (band 0–39 "tekanan keluar rendah"), di semua
observasi. Komposisi tipikal (contoh NVDAx 13:03): deviasi 0,5 +
depth 0,0 + redemption 10,0 + funding 0,0 + OI tidak-terhitung.
Redemption = 10 di semua ticker karena penutupan Jumat 16:00 ET
berada ≤ 72 jam lagi (aturan desain §2.3). Funding = 0 di semua
ticker (funding Hyperliquid malam ini nyaris nol). **Tidak ada satu
pun ticker yang menyentuh ambang alert 70.**

### 2.3 Liquidation Guard — semua OK

Semua ticker `ok` di ketiga observasi; 0 warning, 0 critical.
Divergensi mark-vs-oracle terbesar 0,094%. `distance_pct` NULL di
mana-mana (sesuai desain — sumber level likuidasi belum terverifikasi).

### 2.4 Monday Gap — tidak teruji

Bukan gagal, bukan lolos: **tidak jatuh tempo.** Prediksi pertama
yang bisa dinilai baru ada Minggu 15 Nov malam, hasilnya Senin
16 Nov pagi. Forward test 4 minggu yang sesungguhnya baru bisa
menilai Monday Gap setelah ≥ 4 akhir pekan — sprint ini menilai 0.

## 3. Caveat — baca sebelum memakai angka di atas

### 3.1 Kaki deviations Turso BEKU sejak 12:41 UTC (insiden live)

Migrasi `migrations/2026-11-12-penambahan.sql` **belum diterapkan ke
Turso live**: `deviations` tidak punya kolom `exit_score`,
`perp_snapshots` / `monday_gap` / `liquidation_watch` tidak ada.
Akibatnya sejak siklus 12:46 UTC setiap siklus poller GAGAL di final
pipeline (detail lengkap di `QA_PENAMBAHAN_2026-11-12.md` §2).
Forward test ini memakai spot FRESH dari DexScreener justru karena
kaki Turso-nya beku — skor di atas dihitung dari data live, bukan
dari `deviations`. Bila migrasi sudah diterapkan, angka-angka ini
harus dihitung ulang dari jalur normal (dan kemungkinan tidak berubah
banyak — tapi itu klaim yang harus dibuktikan, bukan diasumsikan).

### 3.2 Komponen OI tidak terhitung (skor parsial, jujur)

Komponen OI Exit Score butuh `perp_snapshots` 24 jam lalu — tabelnya
tidak ada (lihat §3.1) — jadi komponen OI = NULL di semua ticker,
skor dinormalisasi atas 4 (atau 3/2) komponen yang tersedia, sesuai
desain §2.3. Semua skor di §2 adalah **skor parsial** dan dicatat
begitu di ledger (`partial=true`, `n_comp=2–4/5`).

### 3.3 Deviasi vs close tidak ada (median-only)

`dev_vs_close_pct` NULL (mode median-only, tanpa sumber equity
berlisensi) — sama seperti temuan backtest. Forward test ini tidak
menilai kaki deviasi-vs-close sama sekali.

### 3.4 Aturan close tidak bisa menutup ticker 1-pool

Aturan close mensyaratkan `dev_vs_median_pct < 0,5%`, tetapi ticker
1-pool (COINx, HOODx) dan ticker yang median-nya NULL (GOOGLx,
METAx, QQQx di observasi ini) tidak punya `dev_vs_median_pct` —
kondisinya tidak pernah benar. HOODx yang terbuka di §2.1 tidak
akan pernah tertutup oleh aturan ini. Ini **cacat aturan sprint**,
dicatat di sini dan TIDAK diperbaiki diam-diam setelah melihat
hasil (mengubah aturan sesudah observasi = penalaan). Forward test
4 minggu wajib memakai aturan close yang menangani `dev=None`
(mis. tutup bila `|dev_perp| < 0,5%`) — diputuskan Chief sebelum
ronde itu dimulai.

### 3.5 Observasi 1 hanya 10/13 ticker

Sebelum fallback ditambahkan, COINx/CRCLx/HOODx hilang karena batch
DexScreener mengembalikan ~30 pair (5 pool tidak ikut). Observasi 1
tetap disimpan apa adanya di ledger (bukan dihapus/diulang) — jejak
bahwa fallback itu perlu.

## 4. Yang belum teruji (untuk forward test 4 minggu)

- Akurasi alert `perp_deviation` / `exit_high` (butuh n alert + jendela
  24 jam per alert; sprint ini menghasilkan 1 kandidat, 0 tertutup).
- Monday Gap: arah benar ≥ 50% (butuh ≥ 4 akhir pekan).
- Liquidation Guard: 0 alert KRITIS akibat oracle basi (butuh observasi
  berjalan; sprint ini 0 alert apa pun).
- Exit Score ≥ 70: belum pernah teramati (semua skor < 24).
- Perilaku akhir pekan (deviasi akhir pekan, redemption tutup) — sprint
  ini hari kerja, siang.
- Semua hal di atas mensyaratkan migrasi diterapkan dulu (§3.1) dan
  poller + bot baru benar-benar berjalan live.

## 5. File

- `forward_paper.py` — skrip observasi (baru; satu-satunya file kode
  baru dari ronde ini).
- `forward_paper_trades.json` — ledger lokal (3 observasi + 1 trade
  terbuka; TIDAK ada di Turso).
- `FORWARD_TEST_2026-11-12.md` — laporan ini.
