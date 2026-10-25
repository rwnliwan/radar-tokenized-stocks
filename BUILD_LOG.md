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

## Stage 2 — ticker pages, history charts, methodology, waitlist, CSV (2026-10-25)

- `api/worker.js` — dua endpoint baru, tanpa ubah skema:
  `GET /api/ticker?ticker=X` (satu pipeline Hrana: meta universe +
  deviasi terbaru + venue per-pool + redemption + PoR + spark 12 siklus
  + change 1h/24h/7d + pools_excluded defensif via PRAGMA) dan
  `POST /api/waitlist` (satu-satunya write baru; INSERT...SELECT...
  WHERE NOT EXISTS atomik = dedup case-insensitive; validasi mirror
  Streamlit + length caps; cap global 500 insert/jam; CORS POST
  terbuka + header Content-Type — form ini publik seperti di
  Streamlit, kontrolnya validasi + dedup + cap, tanpa Turnstile
  atau servis baru). Secret TURSO_AUTH_TOKEN TIDAK disentuh
  (masih terpasang; `wrangler secret list` hanya nama).
- `web/` — route baru: `/ticker` (indeks 13 ticker), `/ticker/[id]`
  (dynamic, edge runtime — next-on-pages menolak dynamic route
  tanpa `export const runtime = 'edge'`; build pertama gagal di
  titik ini, diperbaiki + rebuild), `/methodology` (10 paragraf
  methodology_* verbatim EN+ID). Halaman ticker meniru blok
  Streamlit: metrik utama (dw/dev vs median/vs close pending),
  chart riwayat SVG (tanpa lib chart: segmen putus di gap >2,5x
  interval median, garis nol, hover readout), tabel venue
  (dex/chain/harga/cadangan/vol24h/status/link DexScreener),
  blok status bursa (buka → spread; tutup → skor risiko akhir
  pekan v1 port verbatim dari dashboard/risk.py incl. banker's
  rounding Python), kartu redemption + PoR, change 1h/24h/7d +
  sparkline. Detail homepage kini Link ke halaman ticker
  (panel inline dihapus; nit Stage 1 tertutup — copy tip kini
  benar). CSV: tombol unduh tabel tampil (filter+sort aktif),
  angka mentah analis, builder murni ter-unit-test (header,
  null→kosong, escaping koma/kutip lolos).
- i18n PARITAS PENUH: STR web = dashboard/i18n.py verbatim —
  234 kunci EN + 234 kunci ID, 0 hilang, 0 lebih, 0 beda nilai
  (generator /tmp/gen_i18n.py; Stage 1 68 kunci subset penuh di
  dalamnya). UI F-ONLY dipisah (label ticker/chart/waitlist baru).
- Yang TIDAK di-port (di luar daftar item-1, kandidat tahap
  lanjut): alert log ticker, threshold simulator, compare overlay,
  tabel best-exit-by-size. Ambang/status/semantik TIDAK berubah.

### Tambahan di luar scope (latitud — relevan, bisa diveto)
1. Halaman indeks `/ticker` — alasan: nav "Ticker" butuh landing
   page; tanpa ini link nav tidak punya tujuan.

### BUG FIX (bukti, bukan klaim — keduanya memengaruhi angka live)
1. Filter jendela 1 jam Stage 1 SALAH: `ts >= datetime('now',
   '-1 hour')` membandingkan teks format-T ("2026-10-25T...")
   dengan format-spasi ("2026-10-25 ...") — 'T' > ' ' sehingga
   semua baris hari ini lolos: 559 baris vs 143 baris yang benar
   (strftime T-format). Akibat: change_1h homepage sebenarnya
   change-sejak-awal-hari, dan /api/history 1h mengembalikan
   seharian. Diperbaiki di loadLatest seriesR + loadHistory +
   semua query jendela baru (strftime '%Y-%m-%dT%H:%M:%SZ').
   Nilai change_1h berubah sesudah fix — itu koreksi, bukan
   regresi.
2. Case-sensitivity ticker: handler meng-uppercase param
   ("TSLAx"→"TSLAX") sementara ticker_id tersimpan mixed-case —
   SQLite BINARY collation → /api/ticker 404 untuk semua ticker
   (ditemukan saat uji live pertama). Diperbaiki dengan
   `COLLATE NOCASE` di 10 perbandingan ticker_id (juga
   memperbaiki /api/history Stage 1 yang punya bug sama).

### Verifikasi yang sudah dilakukan (bukan klaim)
- tsc --noEmit bersih; next build + next-on-pages OK (route /
  + /ticker statis + /ticker/[id] edge; "Exceeds maximum" = 0;
  output .vercel/output/static 2,8 MB diverifikasi di disk).
- Worker deploy (Version a21806ff); Pages deploy → produksi 200
  (home + /ticker/TSLAx + /methodology + /ticker).
- /api/ticker TSLAx + GOOGLx = Turso persis (dw, bps, depth,
  pools, ts, jumlah venue — semua cocok).
- History 1h GOOGLx = 12 titik 02:46→03:41Z (jendela benar);
  24h/7d TSLAx = 17 titik per-jam (identik saat ini karena
  riwayat baru ~17 jam — akan divergen seiring waktu).
- Waitlist: POST alamat uji → {ok, already:false} + baris tepat
  (consent=1); POST ulang beda kapitalisasi → already:true +
  tetap 1 baris; POST tanpa consent → 400 + tanpa baris; baris
  uji DIHAPUS + terbukti 0 sisa (tabel kembali 0 baris).
- i18n 234/234, grep hsurr bersih, git show: hanya api/ +
  web/ + BUILD_LOG berubah (poller/bot/dashboard/schema/cron/
  DNS/route/UptimeRobot/Telegram tak tersentuh).
- Batasan diketahui: chart riwayat 7d baru selebar riwayat yang
  ada (~17 jam); halaman ticker belum punya alert log /
  simulator / compare (lihat di atas).

## Hotfix — Stage 2 browser check failed: 2 root causes (parent fix, 2026-10-25)

- Gejala: cek browser tahap 2 (03:48–03:50 UTC) gagal total — semua
  halaman data hanya "Could not load live data", padahal curl ke
  Worker lolos. Hanya /methodology (statis) yang tampil.
- Akar 1 (utama): build Pages tahap 2 kehilangan
  NEXT_PUBLIC_RADAR_API_BASE — chunk homepage membaca
  `a.env.NEXT_PUBLIC_RADAR_API_BASE` saat runtime dan nilainya
  undefined (grep chunk: 0 kemunculan "radar-api"; satu-satunya URL
  https adalah LinkedIn). Semua fetch client-side melempar "API base
  URL is not configured" SEBELUM request jaringan. Stage 1 punya var
  ini ter-inline benar; Stage 2 rebuild tanpa var di env build.
  Perbaikan: rebuild dengan NEXT_PUBLIC_RADAR_API_BASE=
  https://radar-api.rwnliwan.workers.dev eksplisit + guard `prebuild`
  di web/package.json (build GAGAL cepat bila var tidak diset —
  insiden ini tidak boleh terulang diam-diam).
- Akar 2: handler OPTIONS Worker melempar error 1101 — `json({},
  204)` mengirim body "{}" dengan status 204, dan konstruktor
  Response menolak body pada status null-body. Akibat: SEMUA
  preflight gagal, termasuk POST waitlist dari browser (yang selalu
  preflight karena Content-Type: application/json). Perbaikan:
  OPTIONS kini mengembalikan `new Response(null, {status: 204,
  headers CORS})`.
- Verifikasi hotfix: OPTIONS → 204 + header CORS; chunk homepage
  baru mengandung URL Worker; cek browser ulang daftar tahap 2.

### Verifikasi hotfix (2026-10-25, lanjutan)
- Deploy Pages PERTAMA salah direktori: `.vercel/output` (bukan
  `.vercel/output/static`) → produksi 404 + chunk campur (bukti:
  chunk cb09f7 tak dikenal, /ticker & /methodology 404, padahal
  preview deploy juga 404). Pelajaran permanen: next-on-pages
  WAJIB deploy `.vercel/output/static` (di sanalah _worker.js
  tinggal; rute dinamis /ticker/[id] tidak di-prerender, jadi
  tanpa worker rute itu tidak bisa tampil).
- Deploy Ulang `.vercel/output/static` → Worker ter-compile
  ("Compiled Worker successfully", _routes.json ter-upload).
  Setelah jeda propagasi ~35 dtk, produksi BENAR: / 200 + chunk
  homepage baru page-99d1b6ea89de5737.js (mengandung URL Worker),
  /ticker 200, /ticker/TSLAx 200, /methodology 200.
  Cek browser ulang daftar tahap 2 menyusul deploy ini.

## Hotfix 2 — display bugs from Stage 2 browser re-check (parent fix, 2026-10-25)

- CSV TERVERIFIKASI (bukan bug): berkas unduhan browser (2 KB)
  dibaca induk — header ticker,tier,dw_price,dev_bps,spread_pct,
  depth_usd,pools_used,redemption_status,por_age_hours,status,
  change_1h_bps + 13 baris nilai live (GOOGLx -42,19 bps, TSLAx
  0,52 bps; single-pool kosong di dev/spread/change). Browser
  hanya tidak bisa menampilkan isi berkas.
- Chart 7d BUKAN bug: /api/history 7d dan 24h mengembalikan 17
  titik identik (24 Okt 11:00Z → 25 Okt 03:00Z) karena riwayat baru
  ~17 jam — keduanya divergen seiring riwayat tumbuh. Metodologi
  sudah menyatakan data mulai 24 Okt 2026.
- BUG NYATA 1 — persen headline kartu ticker 100x terlalu besar:
  `dev_pct * 100` padahal dev_pct sudah dalam satuan persen
  (0,0053 = 0,0053% = 0,53 bps) → tampil "+0,52%" berdampingan
  "+0,5 bps" (0,52% = 52 bps). Skor risiko TIDAK kena (risk.ts
  memakai rumus risk.py verbatim: |dev_pct|*10 cap 40).
  Perbaikan: headline persen = dev_pct.toFixed(3) + "%"
  (0,001% = 0,1 bp resolusi; konsisten dengan bps).
- BUG KECIL 2 — label "Last:" chart hardcoded Inggris → kunci
  UI chart_last ("Last:" / "Terakhir:").
- POLES 3 — identifier internal "weekend_risk_v1" tampil di halaman
  publik (2 tempat) → label manusia "Weekend exit-risk method v1"
  / "Metode risiko akhir pekan v1" (nilai risk_method port + kunci
  UI risk_method_short baru; dashboard Streamlit tidak diubah).

### Verifikasi hotfix 2 (2026-10-25, browser tertarget + grep chunk)
- Deploy hotfix 2 (Worker bundle + _routes.json) → produksi /,
  /ticker/TSLAx, /methodology semua 200.
- Browser tertarget LOLOS 3/3: (1) persen vs bps konsisten —
  TSLAx +0,009% / +0,9 bps, GOOGLx -0,422% / -42,2 bps
  (data 12:21 WITA); (2) readout chart ID "Terakhir: +0,5 bps";
  (3) label metode manusia EN+ID, "weekend_risk_v1" tidak
  ditemukan di teks tampil. Grep chunk build induk: string baru
  ada, "weekend_risk_v1" nol di semua chunk (termasuk source).
- Status tahap 2: LIVE & TERVERIFIKASI PENUH (cek browser
  daftar lengkap + hotfix 1 + hotfix 2). Sisa untuk vonis Septian
  di HP/laptop: collapse mobile (tool browser tidak bisa resize —
  desktop masih scroll horizontal) + penilaian visual keseluruhan.
  Tahap 3 cutover menunggu ACC terpisah.

## Tahap 3 cutover — dimulai 2026-10-25 (ACC Septian 12:31 WITA)

- Probe Cloudflare: zona omdanny.site (a57727663b674706db051ec75e063da9,
  active, Free); Worker route radar.omdanny.site/* -> radar-redirect
  (id a0aee7b77b854abebca611ae860417cc) MASIH aktif; Pages
  exit-radar belum punya custom domain.
- Pages custom domain BERHASIL via API: radar.omdanny.site ditambahkan
  ke proyek exit-radar (id 83993300-e721-43e3-8b7f-d748a2035084,
  status initializing, verifikasi pending — aktif setelah DNS
  mengarah ke Pages).
- BLOKIR API (bukan bug): token custom.cloudflare TIDAK punya scope
  DNS (GET dns_records -> 10000 Authentication error) -> CNAME
  radar HANYA bisa diubah Septian via dashboard. Route Worker JUGA
  TIDAK dihapus induk dulu: menghapus route selagi DNS masih ke
  radar-redirect akan membuat subdomain tanpa pelayan (break).
  Urutan aman: (1) Pages domain [SELESAI via API], (2) Septian
  ubah CNAME radar -> exit-radar.pages.dev (Proxied) di dashboard
  DNS, (3) Septian hapus route radar.omdanny.site/*,
  (4) induk verifikasi (Pages 200 + deep link /TSLAx, tanpa 302
  Streamlit), (5) Septian pindah monitor UptimeRobot.
- Rollback (bila cutover bermasalah): CNAME kembali ke
  radar-redirect.rwnliwan.workers.dev + route dihidupkan lagi
  (keduanya via dashboard); Streamlit tetap live sebagai fallback.

## Perbaikan metodologi — teks "numpuk" (feedback Septian 2026-10-25)

- Keluhan: halaman /methodology = intro + 10 paragraf panjang yang
  hanya dipisah <hr /> — tembok teks tanpa hierarki.
- Perbaikan (struktur saja, kata paragraf TIDAK diubah): 10 paragraf
  dikelompokkan ke 9 seksi berjudul (Deviasi & spread [2 paragraf],
  Kedalaman, Redemption, Proof of reserve, Status & alert, Sumber &
  data, Batasan, Metodologi diperiksa manusia, Segera hadir) via
  kunci UI method_h_* EN+ID; lebar baca dipersempit ke 820px;
  spasi antar-seksi 38px, antar-paragraf 16px; <hr /> hanya sebelum
  footer. Berlaku di Pages sekarang; ikut ke radar.omdanny.site
  setelah cutover (deployment yang sama).

## Perbaikan layout mobile halaman ticker (feedback Septian 2026-10-25)

- Keluhan (screenshot COINx di HP): kotak Main deviation tidak sama
  besar/tidak seimbang + teks area merah "tumpuk" (terpotong di tepi
  kanan). Vonis: "design kamu bisa lebih baik dari ini".
- Diagnosis (satu akar, banyak gejala): .metrics memakai grid 4 kolom
  untuk SEMUA blok ticker — Main deviation (3 kartu) menyisakan 1
  kolom kosong, di HP jadi 2 kolom + 1 kartu yatim; blok spread
  (1 kartu) menyisakan 3 kolom kosong. Kartu grid default
  min-width:auto sehingga label panjang ("DEVIATION VS
  CROSS-VENUE MEDIAN") memaksa grid lebih lebar dari layar HP ->
  SELURUH halaman meluber, semua teks tampak terpotong di tepi.
  Tabel venue sendiri tidak bersalah (sudah di .tblwrap scroll
  internal); chart SVG sudah width:100%.
- Perbaikan: varian grid per jumlah kartu — metrics-3 (3 kolom
  desktop, 1 kolom penuh + konten tengah di HP) untuk Main
  deviation; metrics-1 (penuh) untuk blok spread; blok Changes
  (4 kartu) tetap grid 4/2x2 yang memang seimbang. .metric
  ditambah min-width:0 + overflow-wrap agar label melipat, bukan
  memaksa lebar. Kata/nilai tidak diubah.

### Verifikasi metodologi (browser, 2026-10-25)
- LOLOS: 9 judul seksi EN persis (Deviation & spread, Depth,
  Redemption, Proof of reserve, Status & alerts, Sources & data,
  Limitations, Human-checked methodology, Coming soon) + ID persis
  (Deviasi & spread, Kedalaman, Redemption, Proof of reserve,
  Status & alert, Sumber & data, Batasan, Metodologi diperiksa
  manusia, Segera hadir); kalimat pembuka intro + paragraf pertama
  seksi deviasi utuh (kata tidak berubah); layout terbaca sebagai
  seksi terpisah, tanpa overflow/clipping.

### Verifikasi cutover — BELUM EFEKTIF (2 jalur independen, 2026-10-25)
- Jalur curl induk + jalur browser independen SAMA-SAMA mendapat
  halaman placeholder Cloudflare di radar.omdanny.site ("There is
  nothing here yet" / "If you expect something to be here, it may
  take some time." / "Powered by CLOUDFLARE") — BUKAN dashboard,
  BUKAN redirect Streamlit. URL tetap di radar.omdanny.site.
- State API terkonfirmasi: route Worker radar SUDAH terhapus (hanya
  kantor tersisa); custom domain Pages status ACTIVE. Satu-satunya
  bagian yang tidak bisa dibaca induk: isi record CNAME radar
  (API DNS ditolak token; DNS publik menyembunyikan target karena
  Proxied). Penyebab paling mungkin: target CNAME belum mengarah
  ke exit-radar.pages.dev (edit belum tersimpan / record keliru),
  bukan propagasi (sudah >10 menit sejak domain dibuat; dua jalur
  sepakat). Langkah berikut: Septian membaca balik target CNAME
  dari dashboard. Rollback bila perlu: CNAME kembali ke
  radar-redirect.rwnliwan.workers.dev + route dihidupkan lagi.

### Verifikasi ticker mobile (browser, 2026-10-25)
- Desktop LOLOS: Main deviation 3 kolom sama besar (Depth-weighted
  $163,84 / dev median — / vs-close License pending); halaman muat
  viewport tanpa scroll horizontal; paragraf utuh di dalam kolom
  (vs-close note, risk, redemption lengkap); tabel venue muat
  frame di desktop; nilai + risk 72,4 (2/4) + redemption Closed
  + next open 26 Okt 12:00 WITA semua tampil.
- BATAS ALAT: browser tidak bisa emulasi viewport HP (~390px) —
  cek mobile (kartu susun penuh + tengah, tanpa meluber, tabel
  scroll internal) TIDAK bisa dilakukan dari tool; CSS mobile
  sudah terverifikasi ada di build (metrics-3 1 kolom + tengah).
  Vonis HP Septian yang menentukan (halaman yang sama: COINx).
  Blok spread 1-kartu absen karena bursa tutup — sesuai desain,
  bukan kegagalan.

### Koreksi: DNS benar, "dua jalur" ternyata satu jalur (2026-10-25)
- Screenshot DNS Septian: radar CNAME -> exit-radar.pages.dev,
  Proxied — BENAR. Dugaan target salah DICABUT.
- API Pages: domain radar.omdanny.site ter-alias ke deployment
  produksi terbaru 7c91fe69 (success) — sisi Pages BENAR.
- KOREKSI PENTING: curl induk + browser task SAMA-SAMA lewat
  egress VM yang sama (proxy + PoP LAX yang sama) — jadi keduanya
  sepakat BUKAN bukti kegagalan global; keduanya hanya membuktikan
  jalur VM masih melihat placeholder. Jalur independen yang benar:
  HP Septian + server UptimeRobot. Pelajaran: klaim "dua jalur
  independen" wajib memeriksa apakah egress-nya memang berbeda.
- Status dari jalur VM: radar.omdanny.site masih 404 (12:50 WITA);
  deployment preview 7c91fe69.pages.dev 200 (shell SPA — grep
  "All tickers" 0 normal untuk SPA, bukan bukti error).
  Penentu: hasil buka HP Septian + status monitor UptimeRobot.

### Recheck pasca pasang-ulang domain (2026-10-25 12:58 WITA)
- Domain baru (id 18435cec) status ACTIVE + verifikasi ACTIVE,
  tapi jalur VM MASIH 404. Pasang ulang saja tidak memperbaiki.
- Cek Page Rules / Ruleset TERBLOKIR token (9109/10000) — tidak
  bisa disingkirkan dari sisi induk; bukan tersangka utama.
- Langkah berikut (butuh action Septian, sesuai permintaannya):
  toggle CNAME radar Proxied -> DNS-only, tunggu ~1 menit, cek
  dari HP. Alasan: memisahkan apakah tepi proxy zona yang menelan
  request vs binding Pages yang rusak. Aman + reversibel (satu
  klik kembali ke Proxied).

## Padding landscape HP 16px (feedback Septian 2026-10-25)
- Keluhan: padding 20px terasa agak lebar saat landscape; portrait
  sudah ok. Perbaikan: media query (orientation: landscape) +
  max-width 950px -> .wrap padding 16px; portrait + desktop tidak
  tersentuh. Dipilih 16px (dari usulan 15/16 — nilai standar).

## CUTOVER SELESAI — DNS-only adalah perbaikan (2026-10-25 13:02 WITA)
- Bukti: setelah Septian toggle CNAME radar Proxied -> DNS-only,
  radar.omdanny.site LANGSUNG 200 (shell Next.js) + deep link
  /ticker/TSLAx 200 — dari jalur curl induk. Diagnosis final:
  tepi proxy zona TIDAK merutekan hostname ke binding Pages
  (placeholder "nothing here yet"), padahal DNS benar, domain
  Pages ACTIVE + ter-alias, route Worker terhapus. DNS-only
  (langsung ke Pages) bekerja sempurna.
- Keputusan: PERTAHANKAN DNS-only. HTTPS tetap jalan (sertifikat
  Pages sendiri, Google); yang hilang vs Proxied hanya fitur
  level zona (WAF/analytics hostname) — tidak relevan untuk situs
  statis Pages (edge + DDoS Pages sendiri sudah cukup). Jangan
  kembalikan ke Proxied tanpa alasan (akan kembali placeholder).
- Pelajaran: untuk Pages custom domain di zona ini, Proxied BISA
  gagal routing ke binding Pages — bila placeholder muncul padahal
  semua state benar, toggle DNS-only adalah diagnostik + perbaikan
  pertama, bukan terakhir.

### Verifikasi render cutover (browser, 2026-10-25 13:02 WITA)
- LOLOS PENUH di radar.omdanny.site: homepage "All tickers —
  latest deviation", worst -44,6 bps GOOGLx · depth $1,36M,
  13 baris, LIVE, last updated 13:01 WITA, 35/35 venue; Detail
  TSLAx -> halaman ticker asli ($371,81; +3,2 bps / +0,032% OK;
  chart; 4 venue; redemption Closed); URL tetap di
  radar.omdanny.site/ticker/TSLAx (tanpa redirect); tanpa
  placeholder/error. Cutover DINYATAKAN SELESAI.

### Konfirmasi penutup cutover (Septian, 2026-10-25 13:04 WITA)
- Monitor UptimeRobot Exit Radar: UP. radar.omdanny.site bisa
  diakses dari HP Septian. Cutover TUNTAS di semua jalur (curl
  VM, render browser, HP, UptimeRobot). Sisa hanya deploy padding.
