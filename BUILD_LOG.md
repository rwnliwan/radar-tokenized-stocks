# Radar Tokenized Stocks — Build Log Tahap 1 (poller + skema)

**Tanggal bangun:** Sabtu 24 Okt 2026. **Jangkar gerbang Minggu ke-8:**
snapshot pertama `2026-10-24T11:11:00Z` (= 19:11 WITA). Evaluasi A1
jatuh pada akhir Minggu ke-8 sejak tanggal ini (dihitung dari hari
pertama poller menulis snapshots ke DB produksi, desain §9).

## Yang dibangun
- `schema.sql` — 10 tabel desain §2.1, terverifikasi via readback
  (PRAGMA per tabel + sqlite_master: 16 objek = 10 tabel + sqlite_sequence
  + 3 indeks desain + 2 autoindex PK).
- `turso_client.py` — Hrana via curl, token hanya dari vault
  `custom.turso-radar` (surrogate) saat runtime; tidak pernah dicetak.
- `verify_universe.py` + `verify_universe_out.json` — verifikasi live 43
  kandidat via DexScreener search.
- `seed_universe.py` — seed universe + pools (idempotent).
- `poller.py` — baseline 5 menit; loop 1 menit Tier 1 di jendela rapat
  (±30 menit sekitar 09:30 & 16:00 ET, hari bursa NYSE, zona
  America/New_York); Tier 2 tetap 5 menit; slot per-jam redemption/PoR;
  slot close harian; arsip gzip per siklus; heartbeat per siklus; flock
  anti-overlap; backoff eksponensial 429.
- Cron `radar-poller` — interval 5 menit, timeout 4500 dtk, silent
  (hanya log ke `logs/poller-cron.log` + daily log bila gagal).
- `universe_excluded.md` — universe final + daftar tidak tercakup beralasan.

## Universe final: 13 ticker (bukan 20–30)
- Tier 1 (11): TSLAx, NVDAx, METAx, GOOGLx, MSTRx, SPYx, QQQx, CRCLx,
  HOODx, COINx, GLDx. Tier 2 (2): AAPLx, MSFTx. Semua xStocks (wrapper),
  Solana, 35 pool yang dilacak (likuiditas >= $100 rb).
- 30 dari 43 kandidat gagal kriteria (lihat universe_excluded.md).
  Sesuai desain §1.3, ambang TIDAK diturunkan; perluasan menunggu
  verifikasi berikutnya.

## Temuan & penyimpangan dari desain (jujur)
1. **Batching DexScreener TERBUKTI TIDAK PENUH.** Satu request
   `/tokens/` dengan 13 alamat diterima (HTTP 200), tetapi respons
   DIBATASI 30 pair — 5 dari 35 pool tidak kembali. Per-token fetch
   mengembalikan pool yang hilang (terverifikasi untuk ke-5-nya).
   Poller memakai batch-first + fallback per-token, dan mencatat
   pemakaian fallback di `poller_health.gap_note` tiap siklus.
   Hitungan desain "1 request/siklus" menjadi "1 + ≤5 request/siklus"
   — tetap jauh di bawah limit 300/menit.
2. **Bug klien saya (diperbaiki).** `turso_client.py` versi awal
   mengembalikan wrapper respons Hrana, bukan result — `query()`
   mengembalikan [] walau tabel ada. Diperbaiki (unwrap
   response.result); semua readback final memakai klien yang sudah
   diperbaiki + verifikasi silang via skrip curl independen.
3. **Pool di bawah $100 rb TIDAK disimpan di snapshots** (desain §5.2
   tertulis "tetap disimpan"). Alasan: ~200 pair akan menembus anggaran
   tulis §2.2 (35 pool ≈ 2 jt writes/bln; 200 pool ≈ 11+ jt/bln).
4. **Redemption/PoR otomatis BELUM terhubung.** Tidak ada sumber
   otomatis yang terverifikasi untuk status live redemption maupun
   alamat feed PoR Chainlink per issuer. Slot per-jam mencatat fakta
   ini di `gap_note`; tidak ada baris palsu yang ditulis.
   `redemption_windows` hanya berisi 1 baris dokumentasi xStocks
   (status `unknown`, jadwal terdokumentasi 5 hari/minggu, KYC).
   Ini pekerjaan fase berikutnya (verifikasi sumber issuer).
5. **Equity close BELUM terhubung (median-only mode).** Tidak ada
   sumber saham berlisensi yang dikonfigurasi (sesuai keputusan parent:
   publik median-only sampai lisensi display ada). `dev_vs_close_pct`
   = NULL di semua baris; `equity_refs` kosong.
6. **Ondo berubah dari riset pagi.** Riset pagi menyebut likuiditas DEX
   Ondo $0–9,9 rb; verifikasi live menemukan 1 pool Uniswap/Ethereum
   per ticker ($8,4–23,8 jt, quote WETH) — tetap GAGAL kriteria >= 2
   venue, jadi tetap tidak tercakup.
7. **Angka tier gratis Turso (5 GB / 10 jt writes/bln) BELUM
   terverifikasi ulang di dashboard** (desain §2 memintanya). Estimasi
   dengan 35 pool: ±154 rb baris/minggu, ±670 rb/bln mentah, ±2 jt
   writes/bln dengan pengali indeks 3x — di bawah 10 jt bila angka itu
   benar.

## Uji yang lolos
- Window logic (simulasi waktu, 11 kasus incl. libur NYSE & akhir
  pekan): 11/11 PASS. Hari ini Sabtu → tidak ada jendela rapat live;
  sesuai instruksi, jendela hanya diuji lewat simulasi.
- Live 2 siklus penuh: 11:11 & 11:12 UTC, masing-masing 35 snapshot +
  13 baris deviations, 0 pool hilang, 2 heartbeat OK, 2 arsip gzip.
- TSLAx pool Raydium terdalam $2.377.760 — cocok dengan bukti live
  riset pagi ($2,38 jt); konfirmasi token kanonis kuat.

## Yang BELUM dibangun (fase berikutnya, sesuai tugas)
Dashboard Streamlit, bot Telegram, landing/waitlist, agregasi retensi
(snapshots_hourly/daily + job mingguan), monitor eksternal (dead-man
switch), sumber redemption/PoR otomatis, sumber equity close berlisensi.
Tidak ada kode paywall, tidak ada produk non-MVP.

## Tahap 1 migrasi — Next.js + Worker API (25 Okt 2026, Stage 1 SAJA)

**Status: kode + deploy SELESAI, data BELUM MENYALA — satu blocker kredensial
(lihat butir 5). Streamlit tetap live; radar.omdanny.site TIDAK disentuh;
poller/bot/skema/cron/DNS/UptimeRobot/Telegram TIDAK disentuh.**

### Yang dibangun
- `api/` — Worker `radar-api` (https://radar-api.rwnliwan.workers.dev),
  read-only atas Turso `radar-tokenized-stocks`, TANPA tulis/skema:
  `GET /api/latest` (13 ticker: dw price, dev bps vs median, spread,
  qualifying depth, pools used, redemption status + next open, PoR age,
  sparkline 12 siklus, change 1h, status), `GET /api/history?ticker=X
  &window=1h|24h|7d` (per-cycle untuk 1h, rata-rata per-jam untuk 24h/7d),
  `GET /api/health` (latest_ts + age + fresh<=15 mnt + venues live).
  CORS GET terbuka (data ini sudah publik di dashboard Streamlit).
  Satu pipeline Hrana per endpoint — baris program-wide dibaca dalam
  pipeline yang sama dengan baris per-ticker (pelajaran race batch
  pertama 25 Okt: tidak ada flip status di tengah load).
- `web/` — Next.js App Router (next 15.5.2, react 19.3.0,
  @cloudflare/next-on-pages 1.13.16, wrangler 4.149.0 — dipin dari versi
  Learn; npm awal gagal eresolve karena wrangler 4.152.0 minta
  workers-types ^5 vs next-on-pages ^4, diselesaikan dengan pin 4.149.0
  + --legacy-peer-deps; workers-types hanya tipe, tidak memengaruhi
  runtime). Homepage SAJA, meniru mockup yang di-ACC: strip KPI 4 kartu,
  coverage line jujur, tabel master 13 baris, chart batang divergen
  (CSS, tanpa lib chart — cukup untuk Stage 1), footer + LinkedIn.
  Fetch client-side dari Worker + refresh 60 dtk + tombol Refresh +
  banner stale >15 mnt; EN default + toggle ID persisten (localStorage);
  68 kunci i18n di-port verbatim dari dashboard/i18n.py (subset homepage).
  Standar anti-slop: skeleton loading, header sticky, indikator sort
  ▲/▼ + aria-sort, semua kontrol <button> (keyboard + focus-visible),
  tanpa gradien/emoji/dekorasi; kolom sekunder di HP masuk ke panel
  detail per-baris yang bisa dibuka (bukan sekadar hilang).

### Tambahan di luar scope Stage 1 (latitud Septian 25 Okt — relevan, bisa diveto)
1. Kontrol sort (dev/depth/nama) + filter tier — alasan: kontrol yang
   sama ada di homepage Streamlit; user menemukan deviasi terburuk
   dalam satu ketuk.
2. Panel detail per-baris (klik Detail) — alasan: di HP kolom sekunder
   runtuh ke detail, bukan hilang; dan data per-ticker tercapai satu
   ketuk selagi halaman ticker baru ada di Tahap 2.
3. Kolom harga utama = depth-weighted price (mockup), venue-best +
   dex pindah ke panel detail — alasan: sesuai visual mockup yang
   di-ACC; kedua angka tetap tampil, tidak ada yang disembunyikan.

### Yang TIDAK diubah (batas keras)
Ambang/status/semantik data: Watch >50 bps, Alert >100 bps
(display-only), spread = (max-min)/dw, depth = qualifying depth,
dev bps = dev_vs_median_pct × 100 — semua meniru dashboard persis.
Tidak ada threshold baru, tidak ada status baru.

### 5. BLOCKER — token vault TIDAK BISA dipakai dari Worker (butuh token Turso asli)
`dynamic_credential_entry("custom.turso-radar")` mengembalikan surrogate
`hsurr:*` yang HANYA ditukar ke kredensial asli oleh Sentinel/authd
pada request keluar dari VM (docstring modul itu sendiri). Worker jalan
di edge Cloudflare, di luar lapisan itu — Hrana menerima string hsurr
mentah → `400 {"error":"JWT error: InvalidToken"}`.
Bukti: (a) 8 statement + token yang sama dari VM (Node/curl) → HTTP 200
semua OK; (b) dari Worker bahkan `SELECT 1` minimal → 400 InvalidToken;
(c) dua jalur set secret (wrangler secret put + API langsung) hasil
sama; (d) tidak ada berkas env radar lokal (hanya brain-batch &
siskamling-digital di ~/.config/turso/).
PEMBuka: Septian membuat token Turso baru (dashboard/CLI Turso) khusus
Worker lalu diserahkan via jalur aman → satu perintah set
`TURSO_AUTH_TOKEN` menghidupkan seluruh rantai TANPA ubah kode.
Worker + frontend sudah ter-deploy dan akan langsung menampilkan data
begitu token asli terpasang.

### Verifikasi yang sudah dilakukan (bukan klaim)
- Worker: deploy OK (Version 28ff39a3), endpoint kembali 502 generik
  "upstream read failed" (perilaku benar saat token belum valid);
  diagnostik sementara sudah DIHAPUS + redeploy bersih (route __diag
  kini 404 JSON).
- Pages produksi https://exit-radar.pages.dev → HTTP 200, shell
  "EXIT RADAR" + "Loading live data…", chunk live mengandung
  radar-api.rwnliwan.workers.dev (API base ter-inline benar).
- Build: next build OK (route / statis, first load 109 kB);
  next-on-pages OK (.vercel/output/static 1,2 MB, index.html ada,
  grep "Exceeds maximum" = 0).
- Grep secret bersih di api/ + web/src (tanpa hsurr:, tanpa JWT).
- git status: hanya api/ + web/ yang baru; poller.py, bot.py,
  dashboard/, schema.sql, cron, redirect-worker TIDAK berubah.

### Yang MASIH menunggu (parent)
- Cek browser Pages: render tabel/bar, toggle ID persisten, refresh,
  expand baris di HP — nilai REAL belum bisa tampil sebelum blocker
  token di atas beres (yang tampil sekarang: skeleton → error state
  jujur "Could not load live data" + Retry, tanpa angka palsu).
- Catatan: npm memberi peringatan next@15.5.2 punya kerentanan
  (CVE-2025-66478) — versi ini dipertahankan karena menyamai Learn
  sesuai brief; keputusan upgrade di tangan parent/Septian.
