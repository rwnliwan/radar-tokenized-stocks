# Pertanyaan Terbuka untuk DeepSeek

Daftar ini WAJIB dijawab satu per satu di hasil review (lihat
`README.md` §3.3 butir 7). Tiap jawaban harus berisi vonis:
**terjawab / tidak bisa dijawab dari data ini / butuh verifikasi live**,
plus bukti (file, angka, hitung ulang) bila ada.

---

## Q1. Funding 8 jam vs hourly — satuan komponen funding Exit Score benar?

Desain §2.3 komponen 4 memakai "|funding 8 jam|": ≤ 0,01% → 0;
≥ 0,10% → 15; linear di antaranya. Implementasi `poller.py`
(`exit_score_v1`, komentar di kode): Hyperliquid menerbitkan funding
**per funding interval (hourly)** — bukan per 8 jam — dan ambang
desain diterapkan ke `|funding| × 100` sebagai persen **tanpa konversi
diam-diam** ("no silent conversion").

- Apakah ambang 0,01%/0,10% itu benar untuk rate **per jam**?
  Bila rate yang diterbitkan sebenarnya per jam, apakah ambang yang
  dikalibrasi untuk "8 jam" menjadi 8× terlalu ketat (rate per jam
  yang wajar ~1/8 dari rate 8 jam)? Atau apakah label "8 jam" di
  desain memang salah dan yang dimaksud adalah rate per interval
  apa adanya?
- Bukti yang tersedia: harness `/tmp/test_penambahan.py` menguji
  funding 0,0001 → 0,0 poin dan 0,001 → 15,0 poin; `run_cycle_perp`
  live 12 Nov: funding terisi di semua 10 baris (nilai aktual tidak
  dicatat di paket ini — reviewer boleh meminta/membaca dari
  `perp_snapshots` bila sudah ada, atau dari API Hyperliquid live).
- Vonis yang diminta: (a) satuan yang benar, (b) apakah ambang
  0,01%/0,10% harus dikoreksi (dan ke angka berapa), atau (c) apakah
  label desain saja yang harus diperbaiki ("per interval", bukan
  "8 jam").

## Q2. Oracle lag yang tidak bisa diukur — apa yang terjadi pada ambang F4?

Desain §2.4 menetapkan PERINGATAN bila `oracle_lag_s` > 120 dtk dan
KRITIS bila > 600 dtk. Implementasi: kolom `oracle_lag_s` **tidak ada**
di `liquidation_watch` (migrasi + `schema.sql`) karena endpoint info
publik Hyperliquid tidak menerbitkan timestamp oracle — lag tidak bisa
diukur dari sana. `liquidation_status()` menerima `oracle_lag_s=None`
dan mengujinya hanya sebagai parameter di harness.

- Apakah Liquidation Guard masih bermakna dengan hanya dua ukuran
  (divergensi mark-vs-oracle + jarak likuidasi — yang terakhir pun
  selalu NULL sampai sumber terverifikasi)? Atau guard ini pada v1
  praktis hanya mengukur divergensi?
- Apakah ada sumber publik lain untuk umur data oracle (mis. endpoint
  lain, header, atau `time` di respons) yang bisa dipakai — atau
  ambang lag harus dihapus dari desain lewat revisi tertulis?
- Apakah label "eksperimental" + admin-only sudah cukup untuk
  menutupi kekosongan ini, atau guard harus dinyatakan "belum berfungsi
  penuh" di web sampai lag bisa diukur?

## Q3. Duplikasi Exit Score — `poller.py` vs `dashboard/risk.py`, mana yang kanonis?

Desain §4.3 menempatkan fungsi murni `exit_score(...)`,
`monday_gap_predict(...)`, `liquidation_status(...)` di
`dashboard/risk.py` (mengikuti pola `weekend_risk_score`).
Implementasi: ketiga fungsi itu hidup di **`poller.py`**
(`exit_score_v1`, `monday_gap_predict`, `liquidation_status`),
sementara `dashboard/risk.py` hanya mendapat `exit_score_band()`
(pemetaan skor tersimpan → band low/medium/high, +23 baris).

- Apakah ini duplikasi yang berbahaya (dua tempat yang bisa berbeda
  rumus), atau pemisahan yang sah (poller menghitung + menyimpan,
  dashboard hanya menampilkan)?
- Bila suatu hari dashboard perlu menghitung ulang skor dari data
  mentah (mis. replay/backtest), dari mana rumus kanonisnya diambil?
- Apakah `exit_score_band` di `risk.py` dan band di desain §2.3
  (0–39/40–69/70–100) konsisten — dan apakah batas band 40/70 yang
  sama dengan ambang alert 70 menimbulkan kebingungan (skor 70 =
  "tinggi" sekaligus memicu alert)?

## Q4. Konvensi ticker Robinhood — sufiks `r` vs `TSLA-RH`?

`seed_multichain.py` memakai sufiks **`r`** (`TSLAr`, `NVDAr`, …)
mengikuti pola `c`/`B` di desain §3.5 (`NVDAc`, `TSLAB`). Desain
tidak menetapkan sufiks Robinhood. Alternatif yang dicatat di
`SEED_MULTICHAIN_2026-11-12.md` §4: **`TSLA-RH`**.

- Mana yang lebih benar/konsisten dengan konvensi yang sudah ada
  (`x` = xStocks Solana, `c` = Coinbase Base, `B` = bStocks BNB)?
  Apakah `r` berisiko bentrok dengan arti lain (mis. dibaca sebagai
  "Robinhood" vs "r" lain)? Apakah `TSLA-RH` (dengan tanda hubung)
  berisiko merusak parsing `ticker_id` di poller/dashboard/API yang
  selama ini memakai sufiks 1 huruf?
- Keputusan ini butuh konfirmasi Chief sebelum live pertama — reviewer
  diminta memberi rekomendasi beralasan, bukan sekadar memilih.

## Q5. Selisih estimasi kuota — desain vs kuota vs seed, mana yang benar?

Tiga dokumen memberi tiga angka tambahan writes/bulan yang berbeda:

| Sumber | Tambahan/bulan | Total proyeksi |
|---|---|---|
| Desain §6.2 | +2,1 jt | ≈ 3,4 jt/bln (34%) |
| `KUOTA_PENAMBAHAN_2026-11-12.md` (a)+(b)+(c) | +3,37 jt (0,357 + 1,507 + 1,507) | 5,32 jt/bln (53,2%) |
| `SEED_MULTICHAIN_2026-11-12.md` §4 | +3,5 jt (115 pool, bukan 59) | ±4,8 jt/bln (48%) — dari baseline 1,3 jt, bukan 1,95 jt |

Penyebab selisih yang sudah diketahui: desain mengasumsikan ±2,5
pool/ticker (Base 32 + BNB 27 pool); realita seed: Robinhood rata-rata
5,8 pool ≥ $100rb/ticker → 115 pool total; baseline desain 1,3 jt/bln
vs baseline laju aktual 1,95 jt/bln; pengali indeks M=3 untuk
snapshot-style vs M=2 untuk tabel kecil.

- Hitung ulang dengan asumsi yang sama: mana dari ketiga angka itu
  yang benar untuk skenario (a)+(b)+(c)? Apakah selisihnya hanya soal
  asumsi pool/ticker, atau ada kesalahan hitung di salah satu dokumen?
- Apakah skenario (c) (53,2% atau 48%) masih "AMAN BERSYARAT" — dan
  apakah syaratnya (retensi 30 hari + agregasi hourly terbukti jalan)
  sudah terpenuhi hari ini? (Bukti: storage naik 4,7 MB/hari tanpa
  bukti agregasi menahan — lihat `HASIL_TEST.md` §4.)
- Apakah opsi hemat `--max-pools-per-ticker 3` (71 pool, ≈ +2,4 jt/bln
  → total ±3,7 jt/bln, 37%) lebih tepat sebagai default seed daripada
  115 pool penuh?

## Q6. Selisih angka TSLAon — $0,77 jt (riset pagi) vs $6,96 jt (verifikasi sore)?

`VERIFIKASI_MULTICHAIN_2026-11-12.md` §1a: riset pagi (report.md)
mencatat TSLAon ±$0,77 jt (Community v3 $0,50 jt + $0,19 jt, Uniswap
$0,07 jt); verifikasi sore mengukur **$6.964.809** — persis **10×** di
kedua pool besar ($5,01 jt + $1,89 jt), sementara angka Uniswap cocok
($0,07 jt vs $0,06 jt). Penjelasan sementara di dokumen: "kemungkinan
besar riset pagi salah baca desimal" — dikonfirmasi halaman DexScreener
pair (`Liquidity, $5.0M`, crawl 12:24 UTC) — tetapi "tetap dicatat
sebagai selisih yang belum bisa dipastikan penyebabnya".

- Apakah penjelasan "salah baca desimal" cukup, atau ada kemungkinan
  lain (mis. likuiditas benar-benar naik 10× dalam sehari — mis. pool
  $5,01 jt mencatat 27 buys, 0 sells, vol $394.484 dalam 24 jam)?
- Apakah selisih ini mengubah vonis GAGAL untuk TSLAon? (Vonis gagal
  karena venue ke-2 tidak terverifikasi — bukan karena total. Bila
  totalnya memang $6,96 jt, apakah godaan untuk menghitung
  `communityV3` sebagai venue menjadi lebih besar — dan apakah itu
  dibenarkan?)
- Pelajaran metode: apakah ada guard yang mencegah salah baca desimal
  seperti ini terulang di verifikasi berikutnya (mis. cek silang
  halaman pair vs API)?

## Q7. CRCLc susut $221rb → $12,7rb dalam 1 jam — apa artinya untuk ambang?

`SEED_MULTICHAIN_2026-11-12.md` §3b: CRCLc (Base/Coinbase) pool Aero-nya
susut dari **$221.864 ke $12.653 dalam ±1 jam** antara dua tarikan;
vonis: gagal (1 venue, di bawah $500rb). Dokumen mencatat "pasar tipis
bergerak cepat".

- Apakah ini bukti bahwa verifikasi satu-tarikan (snapshot) tidak cukup
  untuk ticker dekat garis ambang — dan apakah ticker yang lolos tipis
  (TSLAc $533.364, hanya +6,7% di atas $500rb; MSFTc $582.084; AAPLc
  $727.045) berisiko gugur dalam hitungan jam setelah di-seed?
- Apakah aturan verifikasi ulang mingguan (yang direncanakan) cukup,
  atau ticker dekat garis butuh verifikasi ulang harian / ambang
  pengaman (mis. hanya seed bila ≥ $600rb)?
- Apakah CRCLc sendiri seharusnya dipantau (bila likuiditasnya kembali
  di atas ambang, apakah ia otomatis kandidat — atau butuh verifikasi
  penuh ulang)?

## Q8. Venue "communityV3" — apakah vonis GAGAL untuk Ondo sudah final?

`VERIFIKASI_MULTICHAIN_2026-11-12.md` §1e: `communityV3` = label
generik DexScreener untuk pool dari klon factory Uniswap V3 anonim
(`0x00a38533…`, deploy 3 Sep 2026 oleh EOA tanpa label, fee 2%/1,5%,
owner `0x0`, tidak ada merek/frontend/router/dokumentasi; DexScreener
sendiri menampilkan pair lain dari factory yang sama sebagai
"Unknown DEX"). Vonis: **BUKAN venue independen yang terverifikasi —
jangan dihitung sebagai venue ke-2**. TSLAon GAGAL (hanya Uniswap
±$60rb teridentifikasi); NVDAon/SPYon/AAPLON gagal total juga.

- Apakah bukti on-chain ini cukup untuk vonis final — atau ada
  pemeriksaan yang kurang (mis. apakah ada router/frontend bernama
  yang memakai factory ini yang belum ditemukan karena pencarian web
  12 Nov tidak menemukannya)?
- Bila suatu hari ada frontend bernama yang terbukti memakai factory
  ini, apa syarat bukti minimum untuk meninjau ulang vonis (dokumen
  §9 mencatat kemungkinan ini — apakah syaratnya cukup jelas)?
- Apakah pool `communityV3` yang "nyata on-chain, harga wajar" tapi
  venue-nya anonim seharusnya tetap dihitung dalam `qualifying_depth`
  bila ticker itu lolos lewat venue lain — atau pool anonim harus
  selalu dikeluarkan dari hitungan (seperti pool venue tanpa nama
  `0x…` yang di-drop seed di §5 butir 4)?

## Q9. Likuiditas Robinhood — volume tinggi vs likuiditas, apakah ada yang janggal?

`VERIFIKASI_MULTICHAIN_2026-11-12.md` §2: volume 24j Robinhood Chain
sangat tinggi vs likuiditas — mis. NVDA ±$30 jt vol vs $7,16 jt liq
(turnover > 1×/hari; satu pair Uniswap NVDA/WETH vol $11,9 jt vs liq
$1,13 jt — > 10×). Dokumen mencatat "konsisten dengan laporan
Bitquery/ByKaranteli (volume besar Oktober 2026), tapi turnover >
1×/hari patut dipantau; bukan alasan gagal karena aturan hanya soal
likuiditas + venue".

- Apakah turnover setinggi itu (terutama > 10× pada satu pair) adalah
  sinyal yang harus diselidiki sebelum seed — mis. wash trading,
  arbitrase berulang, atau sekadar pasar yang sangat aktif?
- Apakah aturan Radar (§1.1 — hanya likuiditas + venue) memang sudah
  cukup, atau volume/turnover ekstrem seharusnya menjadi flag
  (bukan gagal, tapi "perlu pantau") dalam seed?
- Apakah angka-angka ini memengaruhi estimasi kuota (pool Robinhood
  76 pool ≥ $100rb — terbanyak dari ketiga issuer — dengan volume
  tinggi, apakah frekuensi polling 5 menit masih tepat)?

## Q10. Lisensi DexScreener untuk chain baru — apakah display publik Base/BNB/Robinhood melanggar ToS?

Desain §7.2 butir 7 + `VERIFIKASI_MULTICHAIN_2026-11-12.md` §9 +
`SEED_MULTICHAIN_2026-11-12.md` §7: DexScreener melarang
resale/redistribusi dan "produk kompetitor" (report.md §7b). Tugas
cek ToS primer sebelum display publik chain baru ditandai sebagai
"tugas minggu pertama" (desain awal §4.2 butir 3 — berlaku ulang untuk
chain baru). **Cek itu belum dilakukan saat paket disusun.**

- Apakah Radar (read-only internal + display publik atas data
  Base/BNB/Robinhood) masuk dalam larangan tersebut? Apa batas
  pastinya antara "menggunakan API publik untuk analisis internal"
  dan "redistribusi"?
- Bila display publik berisiko: apakah solusinya menampilkan agregat/
  turunan saja (bukan data mentah DexScreener), menunda display chain
  baru sampai lisensi jelas, atau meminta izin tertulis?
- Apakah penyimpanan data DexScreener ke Turso (`snapshots` per 5 menit,
  retensi 30 hari) sendiri sudah merupakan redistribusi/penyimpanan
  yang dilarang — dan apakah ini berlaku juga untuk data Solana yang
  sudah live sejak 24 Okt?

## Q11. Metodologi web — apakah skor baru benar-benar dijelaskan?

Desain §4.5 memerintahkan halaman metodologi memuat metodologi
berversi `exit_score_v1`, `monday_gap_v1`, `perp_3leg_v1`,
`liq_guard_v1` (rumus + bobot + label eksperimental + cara menghitung
ulang akurasi dari log publik). Realita di diff: `methodology/page.tsx`
hanya +2 baris (entri seksi `exit_score` + `perp`); teks metodologi
hidup di string i18n; **tidak ada seksi `monday_gap_v1` /
`liq_guard_v1` di daftar `SECTIONS`**.

- Apakah isi string i18n (ID + EN) untuk `exit_score` dan `perp`
  sudah memuat rumus + bobot + cara hitung ulang yang diperintahkan
  desain — atau hanya label singkat?
- Apakah ketiadaan seksi Monday Gap dan Liquidation Guard di halaman
  metodologi melanggar desain §4.5 (fitur ditampilkan di dashboard
  tapi metodologinya tidak dijelaskan)?
- Apakah banner cakupan (route `/api/coverage` + `PENDING_COVERAGE`)
  jujur hari ini — mis. apakah Base/BNB/Robinhood yang berstatus
  `verified` di pending list bisa disalahbaca sebagai "sudah live"
  padahal belum di-seed?

## Q12. Lonjakan reads Turso +7,40J dalam ±35 menit (12 Nov malam) — apa penyebabnya?

`HASIL_TEST.md` §4: reads kumulatif naik 63.541.222 (20:23 WITA) →
70.944.094 (±21:00 WITA), **+7.402.872 reads, rate 208.541/mnt**,
sementara writes hanya +1.072 (konsisten: tidak ada seed/migrasi live).
Bukan dari backtest (±220 rb rows) dan bukan dari
`turso_usage_check.py` (Platform API, 0 reads). Penyebab belum
diidentifikasi saat paket disusun.

- Dari pola yang diketahui (spike 9 Nov +10,57J dalam 1 hari, rate
  7.336/mnt — legacy query; pelajaran 2026-11-03: satu `COUNT(*)` tanpa
  indeks = 23.249 rows_read), apakah lonjakan ini konsisten dengan
  satu query ceroboh / satu proses yang memindai `snapshots` — atau
  dengan pola lain?
- Apakah lonjakan ini mengubah proyeksi kuota skenario (a)–(c) (yang
  memakai laju ~1.200/mnt → ~52J/bln)? Bila rate 208.541/mnt bertahan
  sejam saja, berapa tambahannya?
- Tindakan apa yang harus dilakukan Chief sebelum deploy (cek
  `usage-api-log.md`, `logs/poller-cron.log`, audit query terbaru) —
  dan apakah deploy harus ditahan sampai penyebabnya jelas?

---

## Q13. (Tambahan, dari penyimpangan diff) Alert F1/F3 dan polling multichain — apakah paket ini sebenarnya belum lengkap?

Dua penyimpangan terbesar di `DIFF_RINGKAS.md` §4:

- **D4 — `bot.py` tidak berubah sama sekali.** Desain §4.2 memerintahkan
  `perp_deviation` dan `exit_high` di `evaluate_alerts()`,
  `format_alert()` baru, dan gabungan perp di `load_live_tickers()`.
  Tanpa itu, apakah F1/F3 hanya "dihitung dan ditampilkan" tapi tidak
  pernah menjadi alert? Apakah paket ini layak disebut "5 fitur selesai"
  bila 2 dari 5 fitur tidak punya jalur alert?
- **D5 — poller masih Solana-only.** Desain §4.1 memerintahkan alamat
  token per (chain, issuer, ticker) + batch per chain. Tanpa itu,
  apakah seed 30 ticker multichain (115 pool) hanya akan menjadi baris
  mati di `universe`/`pools` yang tidak pernah di-polling?
- Vonis yang diminta: apakah kedua pekerjaan ini (a) memang belum
  dibangun dan harus menjadi must-fix sebelum deploy, (b) sengaja
  ditunda ke tahap berikutnya (dan bila ya, apakah desain/penamaan
  "penambahan selesai" menyesatkan), atau (c) ada di tempat lain yang
  tidak tertangkap diff (tunjukkan file + barisnya)?

## Q14. (Tambahan) Monday Gap hanya 2 dari 13 prediksi — apakah F2 berfungsi?

Harness menjalankan `run_weekly_monday_gap` atas minggu 2026-11-07:
**2 prediksi (NVDAx, TSLAx), 11 ticker ter-skip** karena D
(`dev_vs_median_pct`) tidak tersedia — termasuk semua ticker 1-pool
(COINx/HOODx/METAx, NULL di 100% baris) dan GOOGLx (NULL 93,9%).

- Apakah F2 dirancang dengan sadar hanya untuk ticker yang punya
  `dev_vs_median` — dan apakah itu dikomunikasikan di web (prediksi
  kosong untuk 11/13 ticker bukan bug, melainkan keterbatasan data)?
- Apakah ada definisi D alternatif untuk ticker 1-pool (mis. deviasi
  vs harga token Jumat sendiri, atau spread vs acuan) — atau F2 memang
  tidak berlaku untuk mereka?
- Dengan n prediksi sekecil ini per minggu, apakah target kalibrasi
  "8 akhir pekan" (§2.2) realistis — berapa prediksi yang akan
  terkumpul dalam 8 minggu bila hanya ~2/minggu (16 prediksi total)?
