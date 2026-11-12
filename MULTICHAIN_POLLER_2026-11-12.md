# Poller Multichain Radar Tokenized Stocks — 12 November 2026

**Status:** IMPLEMENTASI SELESAI di `poller.py` (fetch + 2 flag dry-run) +
diuji dry-run. **BELUM LIVE:** seed `--live` belum ACC, poller multichain
belum jalan di cron (lihat §6).
**Repo:** `~/workspace/radar-tokenized-stocks`. Hanya 2 file yang
disentuh/dibuat ronde ini: `poller.py` (diubah) + file ini (baru).
`dashboard/`, `bot.py`, `schema.sql`, `api/`, `web/`, `seed_*.py` TIDAK
disentuh. Ambang TIDAK diubah: pool ≥ $100rb (`LIQ_MIN`), depth lolos
≥ $250rb, alert ≥ 1,0% — semua dipertahankan dari desain awal.

**Acuan:** `DESAIN_PENAMBAHAN_2026-11-12.md` §1.2/§3.5/§4.1/§6,
`SEED_MULTICHAIN_2026-11-12.md`, `KUOTA_PENAMBAHAN_2026-11-12.md`,
`seed_multichain.py`, `verify_multichain.py`,
`verify_multichain_out.json` (verified `2026-11-12T12:50:30Z`).

---

## 1. Desain fetch per chain

### 1.1 Kenapa satu batch per chain (bukan satu batch campuran)

Pola lama (Solana saja): SATU request
`/latest/dex/tokens/{13 alamat}` per siklus. Pola itu TIDAK bisa
diperpanjang ke 43 alamat (13 Solana + 30 multichain) karena endpoint
`/tokens` membatasi **30 alamat per request** DAN mengembalikan
**maksimal ~30 pair per respons** (terbukti di dry-run §4: tiap batch
chain mengembalikan tepat 30 pair — Base 15 pool, BSC 24 pool,
Robinhood 76 pool, masing-masing terpotong di 30).

`run_cycle()` kini memanggil `fetch_dex_batches_by_chain()`:
satu batch per chain, tiap batch di-chunk ≤ 30 alamat (hari ini 1
request/chain — Base 9 alamat, BSC 8, Robinhood 13, Solana 13).
Chain per ticker diambil dari `pools.chain` (baris seed membawa
`base`/`bsc`/`robinhood`; baris Solana membawa `solana`).

```text
per siklus 5 menit (di luar tight window):
  Solana    1 batch  (13 alamat)
  Base      1 batch  ( 9 alamat)
  BSC       1 batch  ( 8 alamat)
  Robinhood 1 batch  (13 alamat)
```

### 1.2 Fallback per-token (pola lama, dipakai ulang — bukan ditulis baru)

Logika coverage check + fallback lama dipindah utuh ke helper
`fill_missing_pools()` dan dipakai `run_cycle()` maupun dry-run:
(1) retry case-insensitive dulu (casing alamat); (2) fetch per-token
`/latest/dex/tokens/{alamat}` — SEKALI per alamat token yang berbeda,
bukan sekali per pool yang hilang (S5 fix ronde 8: beberapa pool
berbagi satu token). Fallback inilah yang menyelamatkan pool yang
terpotong batas 30-pair: dry-run §4 membuktikan 17 request fallback
mengembalikan SEMUA pool yang hilang dari batch (115/115 matched).

### 1.3 Isolasi kegagalan (mengikuti pola perp F1)

- Batch **Solana gagal → siklus GAGAL** seperti dulu (`cycles_ok=0`,
  `failed_sources=dexscreener`). Perilaku lama dipertahankan.
- Batch **chain baru gagal → siklus tetap jalan**, pool chain itu
  hilang siklus ini + dicatat di `gap_note`
  (`dexscreener chain batch failed: <chain>: <err>`). Tidak ada
  `poller_health` terpisah untuk chain baru (alasan sama seperti perp:
  baris `cycles_ok=0` akan menandai Radar basi di bot/API).
- Fallback per-token yang gagal dihitung (`fallback_errors`) dan
  dicatat di `gap_note`, tidak menggagalkan siklus.

### 1.4 Yang TIDAK berubah di `run_cycle()`

- Sumber pool tetap Turso (`pools JOIN universe WHERE is_active = 1`);
  alamat token tetap `token_addresses` JSON (satu chain per ticker:
  `{"base": ...}` / `{"bsc": ...}` / `{"robinhood": ...}`).
- Filter tier di tight window (Tier 2 hanya di menit kelipatan 5)
  berlaku untuk SEMUA chain, bukan hanya Solana.
- Filter `LIQ_MIN`, price-sanity guard >25% (hanya bila ≥3 pool),
  `depth_weighted_price`, `dev_vs_median_pct`, exit score F3, arsip
  mentah `raw/` — semuanya tidak berubah. Arsip mentah kini mencatat
  tambahan `dex_requests`, `fallback_requests`, `chains`,
  `chain_errors` di meta (kompatibel mundur: `batch_addresses` dan
  `pairs` tetap ada).
- Sampai seed `--live` jalan, `pools` TIDAK berisi baris multichain —
  siklus live hari ini berperilaku PERSIS seperti sebelum ronde ini
  (1 batch Solana + fallback). Multichain aktif dengan sendirinya
  begitu baris seed ada di Turso; tidak ada switch konfigurasi.

### 1.5 `MULTICHAIN_SEED` — hanya untuk dry-run, BUKAN untuk live

Seed set (30 ticker, 115 pool) di-embed di `poller.py` sebagai
`MULTICHAIN_SEED` — tuple per ticker
`(chain, issuer, token_address, tier, [(pair_address, dex), ...])`,
di-generate dari `/tmp/verify_multichain_out.json` via
`seed_multichain.trackable_pools` + cap 13/issuer (0 pool ter-drop),
BUKAN diketik tangan. Aturan pakainya:

- **Hanya** `--dry-run-multichain` yang membacanya. Alasannya: seed
  `--live` BELUM jalan — Turso live berisi 0 baris multichain — jadi
  dry-run berbasis DB akan mengukur kekosongan, bukan fetch.
- **Siklus live TIDAK PERNAH membaca `MULTICHAIN_SEED`** — ia membaca
  `pools` dari Turso. Bila seed set berubah, regenerate dict ini
  (jangan hand-edit); siklus live ikut seed terbaru otomatis lewat DB.
- Sufiks Robinhood **`r`** (`TSLAr`, `NVDAr`, …) adalah PROVISIONAL
  (SEED_MULTICHAIN §6 — desain hanya menetapkan `c`/`B`, bukan sufiks
  Robinhood). Dipakai di sini supaya `ticker_id` dry-run sama dengan
  file seed. **Keputusan terbuka — konfirmasi Chief sebelum live
  pertama.** Bila Chief memilih `TSLA-RH` atau lainnya, yang berubah
  hanya seed + dict ini, bukan logika fetch.

---

## 2. Hitungan request DexScreener per siklus

Batas DexScreener: **300 req/menit**. Angka di bawah ini adalah hasil
UKUR (dry-run §4, 12 Nov 2026 ±21:04 WITA), bukan asumsi.

| Komponen per siklus 5 menit | Tipikal (terukur) | Worst-case |
|---|---|---|
| Solana: 1 batch + fallback | 1 + 6 = **7** (dry-run `--dry-run` 12 Nov 13:03 UTC) | 1 + 13 (semua alamat fallback) |
| Base: 1 batch + fallback | 1 + ~2 (bagian dari 17 di bawah) | 1 + 9 |
| BSC: 1 batch + fallback | 1 + ~4 (bagian dari 17 di bawah) | 1 + 8 |
| Robinhood: 1 batch + fallback | 1 + ~11 (bagian dari 17 di bawah) | 1 + 13 |
| **Multichain total** | **3 batch + 17 fallback = 20** | 3 + 30 = 33 |
| **Total DexScreener / siklus** | **27** | **47** |
| Hyperliquid (bukan DexScreener) | 2 (`allMids` + `metaAndAssetCtxs`) | 2 |

Laju rata-rata: 27 request / 5 menit = **~5,4 req/menit** (tipikal).
Burst terburuk: 47 request dalam satu siklus (~25 detik kerja fetch
di dry-run) ≈ **~113 req/menit** — masih **di bawah 300/menit**
dengan headroom ~2,7×. Kasus patologis (SEMUA request gagal +
retry backoff 3×) bisa menembus batas sesaat, tapi itu berarti
DexScreener-nya sendiri sedang down — bukan laju normal.

**Keputusan: interval chain baru TETAP 5 menit** (sama seperti Solana).
Tidak perlu naik ke 10 menit, tidak perlu kurangi fallback — anggaran
aman dengan margin besar. Yang mengikat adalah kuota tulis Turso (§3),
bukan rate DexScreener.

**Catatan tight window (1 menit, ±30 menit open/close NYSE):** di
jendela rapat, siklus jalan tiap menit — batch tetap 4 + fallback
(hanya Tier 1 di menit non-kelipatan-5). Perkiraan ~20 request/menit
di jendela rapat — tetap jauh di bawah 300/menit. Satu hal yang
dipantau (§5 butir 3): fetch multichain memakan ~23 detik di dry-run;
bila satu siklus rapat melebihi 60 detik, iterasi menit berikutnya
mulai telat (loop internal, bukan flock) — pantau `poller-cron.log`
di jendela rapat pertama setelah live.

---

## 3. Hitungan writes tambahan (angka pool NYATA — 115 pool)

Bukan asumsi desain §6.2 (±2,5 pool/ticker → 59 pool). Realita seed:
**115 pool** (Base 15 + BSC 24 + Robinhood 76), 30 ticker.
Rumus sama seperti `KUOTA_PENAMBAHAN_2026-11-12.md`: 288 siklus/hari,
30 hari/bulan, pengali indeks M=3 untuk `snapshots` (PK + 2 indeks),
M=2 untuk `deviations` (PK + 1 indeks). Jendela rapat 1-menit BELUM
dihitung (sama seperti dokumen kuota — angka riil lebih besar lagi
bila Tier 1 multichain ikut jendela rapat).

| Tabel | Rumus (115 pool / 30 ticker) | Baris/bln | M | Unit tulis/bln |
|---|---|---|---|---|
| `snapshots` | 115 × 288 × 30 | 993.600 | 3 | **2.980.800** |
| `deviations` | 30 × 288 × 30 | 259.200 | 2 | **518.400** |
| `poller_health` | 1/siklus, sudah ada (tidak bertambah per chain) | 0 | — | **0** |
| `perp_snapshots` | 0 — ticker multichain TIDAK punya perp XYZ (`XYZ_PERP` hanya memetakan 10 ticker Solana) | 0 | — | **0** |
| `monday_gap` | 30/minggu ≈ 130/bln | ~130 | 2 | ~260 (diabaikan) |
| `liquidation_watch` | 0 — guard hanya membaca `metaAndAssetCtxs` dex xyz (Solana saja) | 0 | — | **0** |
| **Total tambahan multichain** | | | | **≈ +3,50 jt/bln (35,0% limit)** |

Perbandingan dengan estimasi desain §6.2 (+2,1 jt/bln untuk 59 pool):
realita **+3,5 jt/bln — 67% lebih besar**, persis seperti peringatan
SEED_MULTICHAIN §4 butir 3 (Robinhood rata-rata 5,8 pool/ticker,
bukan 2,5). Total proyeksi:

| Skenario | Writes/bln | % dari 10 jt |
|---|---|---|
| Baseline berjalan (KUOTA §1, laju aktual) | 1,95 jt | 19,5% |
| + 5 fitur Solana (KUOTA skenario a) | +0,36 jt → 2,31 jt | 23,1% |
| + multichain 115 pool (ronde ini) | +3,50 jt → **5,81 jt** | **58,1%** |
| Ambang aksi standing (80%) | 8,00 jt | 80% |

**Vonis: AMAN dengan syarat** — 58,1% masih di bawah ambang aksi 80%,
tapi sudah melewati setengah limit; TIDAK ada ruang untuk chain
ke-4 tanpa mitigasi. Syarat (dari KUOTA §4/§7, berlaku ulang):
retensi `snapshots` 30 hari + agregasi `snapshots_hourly` terbukti
jalan SEBELUM multichain live, dan checkpoint usage hari ke-2/4/7
setelah live (`turso_usage_check.py`); bila proyeksi rate-basis
melewati 80%, mitigasi hari itu juga (bekukan chain terbaru dulu).

**Varian hemat** (bila Chief memilih `--max-pools-per-ticker 3`,
71 pool — SEED_MULTICHAIN §4): snapshots 71 × 288 × 30 = 613.440
× 3 = 1.840.320 + deviations 518.400 = **+2,36 jt/bln** → total
**4,67 jt/bln (46,7%)**. Keputusan ada di Chief; poller tidak
memihak — ia mem-poll apa pun yang ada di `pools`.

**Reads:** poller TIDAK menambah query berat. `pools`/`universe`
dibaca penuh tiap siklus seperti dulu (tabel kecil: 43 ticker /
150 pool setelah seed — trivial). Tambahan riil: refresh median
depth 7 hari — 1 query/ticker/hari, ≤2.016 baris → worst-case
30 × 2.016 ≈ 60 rb baris/hari ≈ 1,8 jt/bln ≈ **0,4% limit reads**.
Dashboard/bot tetap latest-only via indeks (aturan keras KUOTA §6).

**Storage:** inflow snapshots 993.600 baris/bln × ~120 B ≈
**119 MB/bln** (gross); steady-state dengan retensi 30 hari ≈
+119 MB snapshots + ~31 MB deviations ≈ **+150 MB** di atas
baseline 76,3 MB. Jauh dari ~9 GB — BUKAN constraint bila retensi
jalan (KUOTA §1: laju storage hari ini +4,7 MB/hari TANPA bukti
retensi menahan — cek dulu sebelum live).

---

## 4. Hasil dry-run (12 November 2026)

### 4.1 `--dry-run-multichain` — 12 Nov 2026 ±21:04 WITA (13:04 UTC)

Perintah: `python3 poller.py --dry-run-multichain` (exit 0, 23 detik).
Log lengkap: `/tmp/dryrun_multichain_20261112.log` (ephemeral — angka
ringkasnya di bawah ini; log repo TIDAK ditulis agar tidak mengotori
`raw/`).

| Ukuran | Hasil |
|---|---|
| Chain di-fetch | base, bsc, robinhood (3 batch) |
| DexScreener batch requests | **3** (1/chain) |
| Pairs kembali dari batch | **90** (= 30/chain — bukti batas ~30 pair/respons) |
| Fallback per-token requests | **17** (0 error) |
| **Total DexScreener requests** | **20** |
| Ticker kembali (punya data) | **30/30** |
| Pool matched ke seed | **115/115** |
| Pool lolos `LIQ_MIN` ≥ $100rb | **115/115** |
| Ticker depth ≥ $250rb (gate alert) | **30/30** |
| Ticker ≥ 2 pool qualifying (median terhitung) | **24/30** (6 ticker hanya 1 pool: AAPLc, AMZNc, BABAB, MSFTc, SNDKc, TSLAc — `dev_vs_median` NULL untuk mereka, sama seperti perilaku Solana) |
| Kandidat alert `\|dev\| ≥ 1%` + depth + ≥2 pool | **2** (lihat §5 butir 1–2) |

Kedalaman terlacak saat dry-run (qualDepth, pool ≥ $100rb):
Base ~$11,9 jt · BSC ~$19,9 jt · Robinhood ~$40,7 jt · **total ~$72,5 jt**
(vs $76,9 jt saat seed ±20:50 WITA — angka bergerak, pasar hidup;
TSLAc qualDepth $475.370 vs $465.262 saat seed — stabil, masih di atas
gate alert $250rb).

Per-ticker (depth, dw, dev): `CRCLB dev -30,45%`, `GOOGLB dev -1,06%`,
sisanya |dev| < 0,25% (NVDAc +0,20%, SPYr +0,14%, COINr +0,19%,
GOOGLr +0,09%, TSLAr +0,02%, NVDAr -0,07%, dst.). Harga lintas
chain konsisten: NVDA $160,66–$162,17 · TSLA $386,71–$387,90 ·
GOOGL $292,75–$303,14 · AAPL $356,86–$357,73 · MSTR $115,22–$115,55.

### 4.2 `--dry-run` (biasa) — 12 Nov 2026 13:03 UTC

Perintah: `python3 poller.py --dry-run` (exit 0, 13 detik).
Log: `/tmp/dryrun_plain_20261112.log`.

```text
DRY-RUN CYCLE 2026-11-12T13:03:00Z OK tight=False
  snapshots_would_write=35 deviations_would_write=13
  missing=0 fallback=True dex_requests=7 chain_errors=- guard=-
```

35 snapshot / 13 deviasi = SAMA PERSIS dengan ground-truth poller
live (`logs/poller-cron.log`: `snapshots=35, deviations=13`) — jalur
DB-driven tidak berubah oleh refactor fetch. `dex_requests=7`
(1 batch Solana + 6 fallback per-token — pola lama yang sama;
estimasi tugas "1+≤5" adalah perkiraan, aktual hari ini 6).
Multichain TIDAK muncul di sini (benar: seed belum live, 0 baris di
DB) — untuk seed set pakai `--dry-run-multichain`.

### 4.3 Bukti 0 tulis

- `state.json` mtime tetap 13:01 (siklus cron live terakhir) —
  TIDAK tersentuh dry-run 13:03/13:04.
- TIDAK ada file `raw/2026-11-12/1303*.json.gz` (menit dry-run).
- `python3 -m py_compile poller.py` OK (sebelum dan sesudah edit).
- Poller penuh TIDAK dijalankan; TIDAK ada tulis ke Turso live;
  TIDAK ada deploy.

---

## 5. Temuan — untuk Chief (bukan untuk diperbaiki diam-diam)

1. **CRCLB dev −30,45% hampir pasti BUKAN dislokasi nyata.**
   Dua pool qualifying-nya berlawanan arah: PancakeSwap $64,53
   (liq $677rb) vs venue **`metric` $201,05** (liq $173rb).
   Lima pool kecil lain ($64–$67) sepakat di ~$65. Venue `metric`
   mengutip ~3,1× harga pasar — kemungkinan quote basi/salah, bukan
   harga CRCL. Karena CRCLB hanya punya **2 pool qualifying**,
   price-sanity guard >25% TIDAK jalan (guard butuh ≥3 pool —
   keterbatasan yang sudah didokumentasikan di `run_cycle`).
   **Implikasi live:** ticker ini akan menghasilkan `dev_vs_median`
   ≈ −30% dan (bila bot menilai) alert `deviation` palsu tiap siklus
   sampai pool `metric` itu dibersihkan/dikeluarkan. **Opsi untuk
   Chief:** (a) drop pool `metric` CRCLB di seed (bukan keputusan
   poller — seed milik ronde seed, perlu revisi seed), atau
   (b) terima alert palsu sebagai noise yang diketahui, atau
   (c) perpanjang guard ke kasus 2-pool (perubahan logika — butuh
   desain, BUKAN di ronde ini). Dicatat di sini, TIDAK diubah.
2. **GOOGLB dev −1,06% adalah kandidat alert yang sah** (2 pool,
   depth $2,45 jt): di atas ambang 1,0% dengan depth lolos. Bila
   poller live sudah jalan saat angka ini teramati, bot akan
   menilai alert `deviation` untuk GOOGLB. Bukan bug — ini sinyal
   yang memang dicari Radar.
3. **Tight window: fetch multichain ~23 detik/siklus.** Dalam loop
   1-menit, siklus yang melebihi 60 detik membuat iterasi berikut
   telat (bukan gagal — loop internal, bukan flock). Pantau
   `poller-cron.log` di jendela rapat pertama setelah live; bila
   siklus rapat rutin telat, opsinya: batasi fallback di jendela
   rapat, atau keluarkan chain baru dari jendela rapat (Tier 1
   multichain tetap 5-menit). Belum diputuskan — pantau dulu.
4. **Exit Score komponen redemption untuk ticker multichain saat ini
   TIDAK mengenal issuer.** `_latest_redemption_status()` membaca
   SATU baris `redemption_windows` terbaru tanpa filter issuer —
   untuk ticker Coinbase/bStocks/Robinhood, komponen redemption
   akan memakai status xStocks (atau baris `unknown` issuer baru,
   tergantung mana yang terbaru). Komponen funding/OI sudah benar
   (ticker multichain tidak punya perp → komponen TIDAK dihitung,
   skor parsial — sesuai normalisasi §2.3). **Sebelum exit_score
   multichain dipakai sebagai dasar alert `exit_high`, perlu
   lookup redemption per-issuer** — itu perubahan logika exit
   score, di luar scope ronde ini; dicatat sebagai pekerjaan
   lanjutan, bukan diperbaiki diam-diam di sini.
5. **Fallback 17 request/siklus adalah konsekuensi batas 30-pair,
   bukan inefisiensi.** Robinhood saja punya 76 pool; satu batch
   TIDAK MUNGKIN mengembalikan semuanya. Mengurangi fallback =
   kehilangan pool = deviasi dari data yang lebih tipis. Anggaran
   (§2) masih jauh di bawah batas, jadi fallback penuh dipertahankan.

---

## 6. Yang BELUM selesai

1. **Seed `--live` BELUM ACC.** `seed_multichain.py --live` butuh
   `RADAR_SEED_CONFIRM=ACC-2026-11-12` (ACC Septian). Tanpa itu,
   Turso tetap 0 baris multichain dan poller ini tidak mem-poll
   apa pun yang baru. Verifikasi pasca-seed yang ditunggu:
   `universe` 30 baris baru + `pools` 115 baris baru.
2. **Poller multichain BELUM jalan di cron.** Kode sudah di
   `poller.py`, tapi cron yang berjalan masih memanggil poller yang
   sama — ia baru mem-poll multichain SETELAH seed live (otomatis,
   tanpa deploy ulang poller, karena sumber pool adalah DB). Yang
   masih butuh ACC/aksi terpisah: deploy file `poller.py` ini ke
   tempat cron berjalan (bila cron memakai salinan lain), lalu
   pantau 2–3 siklus pertama + jendela rapat pertama.
3. **Keputusan terbuka:** (a) sufiks Robinhood `r` vs alternatif
   (mis. `TSLA-RH`) — konfirmasi Chief sebelum live pertama (§1.5);
   (b) seed semua 115 pool vs `--max-pools-per-ticker 3` (71 pool,
   total 46,7% vs 58,1% — §3); (c) nasib pool `metric` CRCLB (§5.1);
   (d) lookup redemption per-issuer untuk exit score (§5.4).
4. **Retensi/agregasi `snapshots` 30 hari + `snapshots_hourly`
   BELUM terbukti jalan** (KUOTA §1/§7) — syarat sebelum multichain
   live, bukan hanya rekomendasi. Storage naik 4,7 MB/hari hari ini
   tanpa bukti penahan.
5. **Bot/dashboard/API/web BELUM diubah untuk multichain** (di luar
   scope tugas ini — hanya `poller.py` yang boleh diubah). Setelah
   seed + poller live, ticker multichain akan punya `snapshots`/
   `deviations` tapi belum tentu tampil/benar di permukaan lain
   (lencana chain/issuer, peringatan exit score parsial, dsb.) —
   itu pekerjaan ronde berikutnya (DESAIN §4.2–§4.5).
6. **Verifikasi ulang mingguan ticker dekat ambang** (SEED §4.5):
   TSLAc total $533rb (+6,7% di atas $500rb saat seed), MSFTc $582rb,
   AAPLc $727rb. Dry-run ini hanya mengukur pool ≥ $100rb (TSLAc
   qualDepth $475.370) — BUKAN total universe, jadi tidak bisa
   menyatakan TSLAc gugur/bertahan dari angka ini; verifikasi ulang
   tetap lewat `verify_multichain.py`. Bila gugur minggu depan, seed
   berikutnya harus menonaktifkannya (seed idempotent: DELETE +
   INSERT ulang).

---

## 7. Perubahan kode (`poller.py` saja)

- **Docstring modul:** paragraf multichain (desain, `MULTICHAIN_SEED`,
  sufiks `r` provisional, kedua flag dry-run).
- **`MULTICHAIN_SEED`** (baru): dict seed set 30 ticker / 115 pool,
  di-generate dari `verify_multichain_out.json` — hanya dipakai
  `--dry-run-multichain`, tidak pernah oleh siklus live.
- **`fetch_dex_batches_by_chain()`** (baru): satu batch DexScreener
  per chain (chunk ≤30 alamat); mengembalikan
  `(pairs, n_requests, chain_errors)`.
- **`fill_missing_pools()`** (baru): coverage check + fallback
  per-token — logika LAMA dipindah utuh dari `run_cycle()` (termasuk
  komentar S5), tanpa perubahan perilaku.
- **`_multichain_ticker_summary()`** (baru): cermin murni
  (pure, tanpa I/O) dari matematika per-ticker `run_cycle()` untuk
  dry-run — diberi label "mirror, keep in sync".
- **`run_multichain_dry_run()`** (baru): `--dry-run-multichain`.
- **`run_cycle(..., dry_run=False)`**: fetch per-chain (ganti satu
  batch campuran); gagal Solana = gagal siklus (lama); gagal chain
  baru = gap note; arsip mentah mencatat `dex_requests`/
  `chain_errors`; SEMUA titik tulis dijaga `dry_run` (idempotency
  check dilewati, arsip dilewati, hourly dilewati, monday-gap
  dilewati, liquidation follow-up dilewati, `save_state` dilewati,
  pipeline akhir diganti print ringkasan).
- **`main()`**: flag baru `--dry-run-multichain` dan `--dry-run`
  (keduanya return sebelum lock — tidak ada yang ditulis, tidak
  perlu mutex). Flag lama (`--dry-run-hourly`, `--dry-run-perp`,
  `--dry-run-liquidation`, `--dry-run-monday-gap`,
  `--test-windows`) TIDAK diubah.
- **TIDAK diubah:** `XSTOCKS_MINTS`, `run_cycle_perp()`,
  `run_hourly_redemption()`, `run_hourly_por()`,
  `run_hourly_liquidation()`, `run_weekly_monday_gap()`,
  `exit_score_v1()`, `monday_gap_predict()`,
  `liquidation_status()`, `dex_fetch()`, ambang apa pun, dan
  seluruh logika per-ticker di `run_cycle()` (hanya bagian fetch
  dan penjaga tulis yang berubah).

---

*Dokumen ini laporan implementasi ronde poller multichain 12 Nov 2026.
Perubahan sesudah ini dicatat sebagai revisi bertanggal di bawah baris
ini, bukan dengan mengedit diam-diam bagian yang sudah dinilai.*
