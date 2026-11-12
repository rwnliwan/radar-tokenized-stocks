# Backtest Alert Radar Tokenized Stocks — 2026-11-12

**Tanggal analisis:** 12 Nov 2026, ~20:40 WITA (data dibaca live sampai 12:21 UTC / 20:21 WITA).
**Ruang lingkup:** READ-ONLY terhadap database live Turso. Tidak ada tulis/ubah ke Turso,
tidak ada outcome palsu ditulis ke `alert_log`, tidak ada deploy.
**Acuan definisi:** `DESAIN_TEKNIS_TAHAP1_DRAF.md` §5.3–§5.4 (ambang alert ≥ 1,0%;
"alert tepat" = deviasi tertimbang kembali < 0,5% sebelum bursa AS buka Senin
berikutnya untuk alert akhir pekan, atau dalam 24 jam untuk alert hari kerja;
target akurasi awal ≥ 60%).

## Ringkasan headline

| Angka | Nilai |
|---|---|
| Total baris `alert_log` | **97 baris = 90 event** (7 event tercatat 2×, satu per channel `en`/`id`) |
| Event deviasi (spread + deviation_high) | **37 event** (semua tipe `spread`; `deviation_high` = 0) |
| TEPAT (rekonstruksi spread dari snapshots) | **32** |
| TIDAK TEPAT | **0** |
| Belum tertutup / tidak bisa dinilai | **5** (semua GOOGLx — lihat §3.3) |
| **Akurasi = tepat / (tepat + tidak tepat)** | **32/32 = 100%** di antara yang bisa dinilai |
| Pangsa TEPAT dari semua alert deviasi | 32/37 = **86,5%** |
| Target §5.4 (≥ 60%) | **TERPENUHI** di antara yang bisa dinilai — dengan caveat di §4 |

**Catatan paling penting (baca dulu):** §5.4 **tidak bisa diterapkan apa adanya dari
tabel `deviations` saja** — `dev_vs_close_pct` NULL di 100% baris (76.767/76.767),
dan `dev_vs_median_pct` < 0,5% di 99,97% siklus sehingga uji proxy-nya vakum
(§3.1). Angka akurasi di atas berasal dari **rekonstruksi spread (hi−lo)/dw
dari tabel `snapshots`** per siklus dalam jendela 24 jam (§3.2) — satu-satunya
pengukuran yang setia pada arti §5.4 untuk alert spread. Uji proxy dari
`deviations` saya tampilkan juga (§3.1) supaya transparan **mengapa ia dibuang**,
bukan sebagai akurasi.

---

## 1. Periode data yang tersedia

| Tabel | Baris pertama | Baris terakhir | Jumlah | Keterangan |
|---|---|---|---|---|
| `deviations` | 2026-10-24T11:11:00Z | 2026-11-12T12:21:00Z | **76.767 baris** (13 ticker) | 6.079 siklus poller |
| `alert_log` | 2026-10-25T01:52:00Z | 2026-11-11T18:27:24Z | **97 baris = 90 event** | alert pertama = `redemption_batch` (ticker `ALL`) |
| `poller_health` | 2026-10-24T11:11:00Z | 2026-11-12T12:21:00Z | **6.079 siklus** | 1 baris per siklus |

Periode efektif: **24 Okt – 12 Nov 2026 (19 hari + 1 jam)**, 6.079 siklus poller
(kadensi dasar ~5 menit; ditambah burst 1 menit pada jam buka/tutup bursa di hari
kerja — lihat §5.4). Jumlah siklus = 6.079.

Cakupan harian `deviations` (baris per ticker per hari; 13 ticker):

| Hari | Baris/ticker | Catatan |
|---|---|---|
| 24 Okt | 155 | hari pertama, mulai 11:11 UTC |
| 25 Okt | 288 | Minggu, kadensi 5 mnt |
| 26–29 Okt | 381–385 | hari kerja (5 mnt + burst 1 mnt) |
| 30 Okt | 88 | **outage mulai 07:16 UTC** |
| 31 Okt | **0** | **tidak ada data sama sekali** (outage) |
| 1 Nov | 247 | pulih 03:27 UTC |
| 2–6 Nov | 372–384 | hari kerja |
| 7–8 Nov | 287–288 | akhir pekan |
| 9–11 Nov | 381–383 | hari kerja |
| 12 Nov | 150 | parsial, sampai 12:21 UTC |

## 2. Semua alert di `alert_log`

### 2.1 Per tipe (baris vs event)

| Tipe | Baris | Event | Keterangan |
|---|---|---|---|
| `redemption` | 52 | 52 | 4× penutupan akhir pekan × 13 ticker (25 Okt, 26 Okt, 1 Nov, 7 Nov) |
| `redemption_batch` | 1 | 1 | ticker `ALL`, 25 Okt 01:52 UTC |
| `spread` | 44 | **37** | 7 event pasca-8 Nov tercatat 2 baris (channel `en` + `id`) |
| `deviation_high` | 0 | 0 | **belum pernah terpicu** |
| `por` | 0 | 0 | belum pernah terpicu |
| `redemption_paused` | 0 | 0 | belum pernah terpicu |
| **Total** | **97** | **90** | |

### 2.2 Per ticker (event deviasi / spread saja)

| Ticker | Event spread | Ticker | Event spread |
|---|---|---|---|
| SPYx | 12 | CRCLx | 3 |
| GOOGLx | 6 | MSTRx | 2 |
| NVDAx | 6 | QQQx | 2 |
| GLDx | 4 | TSLAx | 2 |

Nol event spread: AAPLx, COINx, HOODx, METAx, MSFTx. COINx/HOODx/METAx
masing-masing hanya punya **1 pool** sehingga spread antar-venue tidak mungkin
terjadi; AAPLx/MSFTx punya 2 pool tetapi tidak pernah melewati ambang.

### 2.3 Per minggu (Senin–Minggu, UTC)

| Minggu mulai | Baris | Event | Rincian event |
|---|---|---|---|
| 19 Okt 2026 | 14 | 14 | 13 redemption + 1 batch (semua 25 Okt) |
| 26 Okt 2026 | 34 | 34 | 26 redemption (26 Okt + 1 Nov) + 8 spread |
| 2 Nov 2026 | 35 | 35 | 13 redemption (7 Nov) + 22 spread |
| 9 Nov 2026 | 14 | 7 | 7 spread (tiap event 2 baris channel) |
| **Total** | **97** | **90** | |

Per hari (spread, baris): 26 Okt 2, 27 Okt 1, 28 Okt 2, 29 Okt 3, 2 Nov 3,
3 Nov 1, 4 Nov 8, 5 Nov 7, 6 Nov 3, 9 Nov 4, 10 Nov 6, 11 Nov 4.

### 2.4 Cocokkan dengan testing week (2–8 Nov 2026)

- **83 alert total s.d. 8 Nov: COCOK PERSIS.** Jumlah baris s.d. 8 Nov =
  14 + 34 + 35 = 83, sama dengan `EVALUASI-TESTING-WEEK-2026-11-08.md`
  (52 redemption + 30 spread + 1 batch). Rincian harian 2–8 Nov juga cocok
  persis (2 Nov 3, 3 Nov 1, 4 Nov 8, 5 Nov 7, 6 Nov 3 spread; 7 Nov 13 redemption).
- **Sejak 8 Nov: +14 baris = 7 event spread baru** (9 Nov 2, 10 Nov 3, 11 Nov 2
  event; tiap event 2 baris `en`+`id`).
- **0 pengguna eksternal: konsisten dengan data.** `waitlist` = **0 baris**
  (dihitung ulang hari ini). Jumlah anggota kanal Telegram tidak saya cek ulang
  di ronde ini (butuh token bot Telegram — di luar skop query Turso ini);
  evaluasi 8 Nov mencatat 2 anggota/kanal (bot + pemilik).

## 3. Penilaian outcome tiap alert deviasi

Semua 37 event deviasi adalah tipe `spread` dan semuanya terjadi pada **hari
kerja saat bursa buka** (konstruksi bot: spread hanya dievaluasi saat
`market_open`). Karena itu aturan yang berlaku untuk semuanya adalah cabang
"hari kerja" §5.4: kembali < 0,5% dalam **24 jam** sejak alert. **Cabang
"akhir pekan → Senin buka" tidak pernah terpakai** — tidak ada satu pun alert
deviasi akhir pekan dalam data.

### 3.1 Lapisan 1 — §5.4 apa adanya dari tabel `deviations`: TIDAK BISA DINILAI

Dua kolom deviasi di `deviations`:

| Kolom | Isi | Temuan |
|---|---|---|
| `dev_vs_close_pct` | deviasi vs close saham | **NULL di 76.767/76.767 baris (100%)** — mode median-only; tidak ada sumber equity berlisensi (dikonfirmasi `gap_note` poller_health: "equity-close: no licensed equity source configured (median-only mode; dev_vs_close_pct NULL)") |
| `dev_vs_median_pct` | (dw − median)/median | NULL di 25.095/76.767 baris (32,7%); dari 51.672 baris non-NULL, **< 0,5% di 51.655 (99,97%)**, 0,5–1,0% di 17 baris, **≥ 1,0% di 0 baris** |

NULL `dev_vs_median_pct` per ticker: COINx 6.079/6.079, HOODx 6.079/6.079,
METAx 6.079/6.079 (ticker 1-pool — median antar-venue tidak terdefinisi),
GOOGLx 5.709/6.079 (93,9%), QQQx 1.124/6.079, GLDx 25/6.079, lainnya 0.

**Konsekuensi:** besaran yang disebut §5.4 ("deviasi tertimbang") tidak ada di
tabel ini — `dev_vs_close_pct` kosong total, dan `dev_vs_median_pct` bukan
spread yang memicu alert (spread = (hi−lo)/dw; `dev_vs_median` = (dw−median)/
median — dua besaran berbeda; buktinya `dev_vs_median` tidak pernah ≥ 1,0%
padahal 37 alert spread ≥ 1,0% terpicu).

Uji proxy naif ("|dev_vs_median| < 0,5% dalam jendela") menghasilkan
32 TEPAT / 5 TIDAK TEPAT — **angka ini saya BUANG dan tidak saya pakai sebagai
akurasi**, karena: (a) besaran itu < 0,5% di 99,97% siklus apa pun, jadi
"TEPAT" hampir otomatis dan tidak membedakan apa-apa; (b) kelima "TIDAK TEPAT"
itu semuanya GOOGLx yang jendelanya berisi **0 (nol) baris non-NULL**
— data kosong yang salah dibaca sebagai gagal menutup. Proxy ini tidak valid.

### 3.2 Lapisan 2 — rekonstruksi spread dari `snapshots` (penilaian yang dipakai)

Untuk tiap event spread, saya hitung ulang spread (hi−lo)/dw per siklus dalam
jendela (alert_ts, alert_ts+24 jam] dari `snapshots`: pool lolos = `reserve_usd`
≥ US$100rb (§5.2), butuh ≥ 2 pool lolos per siklus, dw = rata-rata harga
dibobot reserve. TEPAT = ada siklus dengan spread rekonstruksi < 0,5% dalam
jendela; TIDAK TEPAT = semua siklus terpakai ≥ 0,5%; tidak bisa dinilai =
tidak ada satu pun siklus dengan ≥ 2 pool lolos dalam jendela.

**Hasil: TEPAT 32, TIDAK TEPAT 0, tidak bisa dinilai 5.**

| # | Alert (UTC) | Ticker | Spread saat alert | Spread < 0,5% pertama | Selang | Verdict |
|---|---|---|---|---|---|---|
| 1 | 26 Okt 13:46 | GOOGLx | 1,348% | 26 Okt 18:31 | 4 jam 44 mnt | TEPAT |
| 2 | 26 Okt 15:16 | SPYx | 1,304% | 26 Okt 15:56 | 39 mnt | TEPAT |
| 3 | 27 Okt 16:06 | SPYx | 1,053% | 27 Okt 16:36 | 30 mnt | TEPAT |
| 4 | 28 Okt 13:51 | NVDAx | 1,132% | 28 Okt 13:58 | 7 mnt | TEPAT |
| 5 | 28 Okt 17:56 | SPYx | 1,054% | 28 Okt 18:11 | 15 mnt | TEPAT |
| 6 | 29 Okt 13:36 | GOOGLx | 1,389% | — | — | **tidak bisa dinilai** (§3.3) |
| 7 | 29 Okt 14:01 | NVDAx | 7,894% | 29 Okt 14:06 | 5 mnt | TEPAT |
| 8 | 29 Okt 17:59 | SPYx | 1,003% | 29 Okt 18:01 | 2 mnt | TEPAT |
| 9 | 2 Nov 14:57 | GOOGLx | 1,027% | — | — | **tidak bisa dinilai** (§3.3) |
| 10 | 2 Nov 16:01 | SPYx | 1,011% | 2 Nov 16:16 | 15 mnt | TEPAT |
| 11 | 2 Nov 17:41 | GLDx | 1,012% | 2 Nov 17:51 | 10 mnt | TEPAT |
| 12 | 3 Nov 16:01 | SPYx | 1,070% | 3 Nov 16:31 | 30 mnt | TEPAT |
| 13 | 4 Nov 14:31 | GOOGLx | 1,001% | — | — | **tidak bisa dinilai** (§3.3) |
| 14 | 4 Nov 14:46 | NVDAx | 1,560% | 4 Nov 15:11 | 25 mnt | TEPAT |
| 15 | 4 Nov 14:51 | GLDx | 1,093% | 4 Nov 14:53 | 2 mnt | TEPAT |
| 16 | 4 Nov 15:11 | CRCLx | 1,994% | 4 Nov 15:16 | 5 mnt | TEPAT |
| 17 | 4 Nov 15:11 | MSTRx | 2,169% | 4 Nov 15:16 | 5 mnt | TEPAT |
| 18 | 4 Nov 15:11 | QQQx | 2,143% | 4 Nov 15:16 | 5 mnt | TEPAT |
| 19 | 4 Nov 15:11 | TSLAx | 2,208% | 4 Nov 15:16 | 5 mnt | TEPAT |
| 20 | 4 Nov 16:41 | SPYx | 1,110% | 4 Nov 17:01 | 20 mnt | TEPAT |
| 21 | 5 Nov 14:46 | GOOGLx | 1,115% | — | — | **tidak bisa dinilai** (§3.3) |
| 22 | 5 Nov 15:01 | GLDx | 1,104% | 5 Nov 15:02 | < 1 mnt | TEPAT |
| 23 | 5 Nov 15:11 | CRCLx | 1,068% | 5 Nov 15:16 | 5 mnt | TEPAT |
| 24 | 5 Nov 15:11 | NVDAx | 1,113% | 5 Nov 15:16 | 5 mnt | TEPAT |
| 25 | 5 Nov 15:11 | TSLAx | 1,107% | 5 Nov 15:16 | 5 mnt | TEPAT |
| 26 | 5 Nov 16:21 | QQQx | 1,199% | 5 Nov 16:26 | 5 mnt | TEPAT |
| 27 | 5 Nov 17:46 | SPYx | 1,374% | 5 Nov 17:51 | 5 mnt | TEPAT |
| 28 | 6 Nov 15:41 | GOOGLx | 1,142% | — | — | **tidak bisa dinilai** (§3.3) |
| 29 | 6 Nov 19:06 | SPYx | **100,041%** | 7 Nov 06:41 | 11 jam 35 mnt | TEPAT* |
| 30 | 6 Nov 19:11 | NVDAx | 4,426% | 6 Nov 19:16 | 5 mnt | TEPAT |
| 31 | 9 Nov 14:32 | SPYx | 1,003% | 9 Nov 14:43 | 11 mnt | TEPAT |
| 32 | 9 Nov 18:02 | GLDx | 4,367% | 9 Nov 18:06 | 4 mnt | TEPAT |
| 33 | 10 Nov 14:42 | MSTRx | 1,043% | 10 Nov 14:43 | < 1 mnt | TEPAT |
| 34 | 10 Nov 14:42 | NVDAx | 1,074% | 10 Nov 14:43 | < 1 mnt | TEPAT |
| 35 | 10 Nov 16:32 | SPYx | 1,172% | 10 Nov 16:51 | 19 mnt | TEPAT |
| 36 | 11 Nov 15:37 | CRCLx | 1,312% | 11 Nov 15:41 | 4 mnt | TEPAT |
| 37 | 11 Nov 18:27 | SPYx | 1,048% | 11 Nov 19:31 | 1 jam 4 mnt | TEPAT |

\* No. 29 (SPYx 100,041%) adalah alert tick-buruk yang sudah dicatat evaluasi
8 Nov: rekonstruksi tanpa price-guard membaca spread 140,6% pada siklus
pertama sesudah alert, dan harga buruk itu bertahan berjam-jam sebelum
terkoreksi. Di bawah aturan §5.4 ia tetap terhitung TEPAT (menutup < 0,5%
dalam 24 jam), tetapi secara substansi ia bukan dislokasi nyata — lihat §4.

Waktu menutup (32 TEPAT): median **4,5 menit**; 20/32 ≤ 10 menit; 28/32
≤ 30 menit; 29/32 ≤ 60 menit. Tiga yang lambat: SPYx 11 Nov (64 mnt),
GOOGLx 26 Okt (284 mnt), SPYx 6 Nov (694 mnt, tick buruk).

Distribusi besar spread saat alert (37 event): 1,0–1,5% = 28 event; 1,5–3% = 5;
≥ 3% = 4 (NVDAx 7,894%, NVDAx 4,426%, GLDx 4,367%, SPYx 100,041%).

### 3.3 Yang tidak bisa dinilai — 5 event, semuanya GOOGLx

| Alert | Alasan (terverifikasi dari data) |
|---|---|
| 29 Okt 13:36 (1,389%), 2 Nov 14:57 (1,027%), 4 Nov 14:31 (1,001%), 5 Nov 14:46 (1,115%), 6 Nov 15:41 (1,142%) | Di seluruh jendela 24 jam, **kurang dari 2 pool GOOGLx yang lolos** (reserve ≥ US$100rb) pada setiap siklus, sehingga spread tidak terdefinisi. Dicek langsung: pada jendela 2 Nov, pool tipis GOOGLx (`solana:3P1P…`) ber-reserve **US$80.913–86.364 sepanjang 379 siklus** — di bawah ambang US$100rb — sementara pool satunya US$1,45–1,51 jt. Hanya 1 pool lolos → spread tidak bisa dihitung. `dev_vs_median_pct` GOOGLx juga NULL di seluruh kelima jendela (0 baris non-NULL dari 279–385 baris). |

Implikasinya: **5 dari 6 alert GOOGLx (83%) tidak bisa divalidasi sama sekali**
— alertnya terpicu pada momen ketika pool kedua sedang berada di sekitar
garis ambang, lalu pool itu jatuh di bawah ambang dan tidak kembali selama
24 jam. Ini bukan kegagalan alertnya, melainkan keterbatasan data: ticker
dengan 2 pool yang satu tipis tidak punya cukup jejak untuk backtest.

### 3.4 Akurasi vs target

- **Akurasi (definisi §5.4) = 32 / (32 + 0) = 100%** — di antara alert yang
  bisa dinilai. Target awal ≥ 60% pada 8 minggu pertama: **TERPENUHI**.
- Tetapi penyebutnya kecil (n = 32) dan 5/37 (13,5%) alert tidak masuk
  penyebut karena tidak bisa dinilai. Bila kelima GOOGLx itu seandainya
  TIDAK TEPAT semua, akurasi menjadi 32/37 = 86,5% — tetap di atas target.
  Bila dihitung terhadap semua 37 event, pangsa TEPAT = 86,5%.
- Sensitivitas terhadap jendela: dengan batas menutup 1 jam (bukan 24 jam),
  29/32 tetap TEPAT (90,6%) — kesimpulan tidak bergantung pada jendela
  24 jam yang longgar.

## 4. Apakah ambang 1,0% terlihat terlalu longgar / ketat?

**Observasi saja — TIDAK ada usulan perubahan ambang.** Perubahan ambang
hanya lewat revisi tertulis Septian (§5.3, amendemen A7).

- **Tidak ada pemicu §5.3 untuk menaikkan ambang:** pemicu naik adalah
  "> 50% alert tidak akurat" — yang teramati 0% tidak akurat di antara yang
  bisa dinilai. **Tidak ada pemicu untuk menurunkan ambang:** pemicu turun
  adalah "tidak ada alert sama sekali selama 4 minggu" — yang teramati 37
  alert dalam 3 minggu, ada di setiap minggu.
- **Tetapi ambang ini terlihat longgar dalam arti substantif:** 28/37 alert
  (76%) hanya 1,0–1,5%, dan 28/32 yang TEPAT menutup dalam ≤ 30 menit
  (median 4,5 menit). Polanya konsisten dengan **noise venue sesaat**
  (satu venue sempat melenceng lalu kembali), bukan dislokasi yang bertahan.
  Artinya alert 1,0% saat ini lebih banyak menangkap kedipan mikrostruktur
  daripada peluang keluar yang bermakna — itu observasi tentang *arti*
  alertnya, bukan vonis bahwa ambangnya salah.
- **Akurasi 100% ini menyanjung (flattering) karena 3 hal:** (a) 2 alert
  tick-buruk ikut terhitung TEPAT (SPYx 100,041% pada 6 Nov; jendela
  SPYx 11 Nov mengandung spread rekonstruksi sampai 128,7% dari tick
  buruk — alertnya sendiri 1,048%); (b) 5 alert GOOGLx yang tidak bisa
  dinilai keluar dari penyebut; (c) n = 32 masih kecil untuk 8 minggu
  pertama (periode ini baru ~3 minggu).
- **Kaki akhir pekan §5.3/§5.4 belum teruji sama sekali:** `deviation_high`
  (ambang implementasi 3,0% atas `dev_vs_median` di `bot.py`, bukan 1,0% vs
  close seperti draf) tidak pernah terpicu — dan memang tidak mungkin
  terpicu dari data ini karena `dev_vs_median` tidak pernah mencapai 1,0%
  di 76.767 baris. Jadi backtest ini **hanya menguji kaki spread (bursa
  buka)**, bukan kaki deviasi-vs-close akhir pekan. Akurasi "alert deviasi"
  akhir pekan masih kosong (0/0) dan tidak boleh dibaca dari angka 100% ini.

## 5. Temuan data

### 5.1 Duplikat

- **Tidak ada baris duplikat eksak** (GROUP BY ticker, alert_ts, alert_type,
  channel HAVING COUNT > 1 = 0 baris).
- Yang menyerupai duplikat: **7 event spread pasca-8 Nov tercatat 2 baris
  masing-masing** (channel `en:-1003867845895` + `id:-1004471605253`) — ini
  **by design** sejak migrasi 2026-11-08 (satu baris per channel delivery).
  Akibatnya `COUNT(*)` = 97 melebih-lebihkan jumlah event (90). 83 baris
  sebelum 8 Nov ber-channel NULL.
- 1 baris berticker `ALL` (`redemption_batch`, 25 Okt 01:52, id = 1) — sah
  menurut skema (alert_log.ticker_id sengaja tanpa FK agar `ALL` bisa dicatat).

### 5.2 Kolom yang menyesatkan / kosong

- **`threshold_pct` TIDAK berisi ambang.** Pada ke-44 baris spread,
  `threshold_pct` == `dev_at_alert_pct` persis (0 baris berbeda; 36 nilai
  distinct 1,001–100,041). Kolom ini menyimpan ulang spread yang teramati,
  bukan ambang 1,0%. Siapa pun yang membaca `threshold_pct` sebagai "ambang
  saat alert" akan salah baca. Penyebab di kode: `bot.py` mengisi kedua kolom
  dari `spread_pct`/`dev_pct` yang sama. (Bukan temuan baru yang saya
  perbaiki — hanya dicatat.)
- **`dev_at_alert_pct` NULL di semua 53 baris redemption/batch** — by design
  (alert jadwal, bukan harga). Semua 44 baris spread memilikinya.
- **Kolom outcome tidak pernah diisi bot:** `outcome` = `'pending'` di
  97/97 baris; `outcome_ts` dan `closed_below_threshold_ts` NULL di 97/97
  baris. Jadi tidak ada satu pun outcome tersimpan yang bisa dipakai —
  semua penilaian di §3 dihitung fresh di ronde ini, dan **tidak saya
  tulis kembali ke `alert_log`** (read-only).

### 5.3 Celah data (`poller_health`, `deviations`)

- **Outage besar 30 Okt 07:16 → 1 Nov 03:27 UTC (44 jam 11 mnt)** — satu-satunya
  celah > 10 menit dalam 6.079 siklus; 31 Okt nol baris untuk semua ticker.
  Dua celah kecil 4 Nov 19:26→19:39 dan 19:39→19:51 UTC (±12–13 mnt).
  Di luar itu `cycles_ok` == `cycles_expected` di **semua 6.079 siklus**
  (0 siklus gagal tercatat).
- `gap_note` paling umum: "dexscreener batch incomplete; per-token fallback
  used" di 5.009/6.079 siklus (82%) — catatan standing, bukan kegagalan.
  Lainnya: "1 tracked pools missing from response" (281 siklus),
  price-guard mengecualikan pool SPYx:1 (730+ siklus) dan GLDx:1 (2 siklus),
  "hourly PoR missing tokens" (28 siklus, NVDAx/METAx/HOODx/COINx),
  "redemption/por automated source not configured" (15 siklus),
  "equity-close: no licensed equity source configured" (10 siklus).
- **AAPLx & MSFTx kehilangan burst 1-menit hari kerja:** masing-masing
  4.949 baris vs 6.079 baris ticker lain (defisit 1.130 baris). Polanya
  sistematis: tiap hari kerja mereka absen pada **14:01–14:59 UTC dan
  20:31–21:29 UTC** (±95 baris/hari) — persis dua jendela burst kadensi
  1 menit (jam buka dan jam penutupan bursa AS); di luar itu kadensi 5 menit
  mereka lengkap. Akhir pekan tidak ada defisit. Tidak berdampak pada
  backtest ini (tidak ada alert spread AAPLx/MSFTx), tetapi cakupan deviasi
  kedua ticker itu lebih kasar tepat di jam-jam paling volatil. Penyebabnya
  tidak saya selidiki (di luar skop read-only ini).
- **Outage 30 Okt–1 Nov memotong jendela 3 alert 29 Okt** (jendela mereka
  hanya berisi 207–279 baris deviations vs ~380 normal) — ketiganya tetap
  bisa dinilai karena datanya cukup sebelum outage.

## 6. Metodologi, query, dan batasan

### 6.1 Cara kerja

1. Baca `schema.sql` + §5.3–§5.4 draf desain + logika alert `bot.py`
   (ambang implementasi: `SPREAD_THRESHOLD = 1.0`, `DEV_HIGH_THRESHOLD = 3.0`
   atas `dev_vs_median_pct`; spread hanya saat bursa buka; dedup 24 jam).
2. Tarik `alert_log` lengkap (97 baris), `deviations` agregat + per ticker,
   `poller_health` lengkap (6.079 baris — dibaca penuh karena kecil,
   lalu diagregat lokal), distribusi |dev| per ticker.
3. Nilai outcome dua lapis (§3.1 proxy `deviations` → dibuang dengan alasan;
   §3.2 rekonstruksi spread dari `snapshots` → dipakai).
4. Rekonstruksi: per event, per pool ticker itu, `snapshots` dalam jendela
   24 jam via indeks `(pool_id, ts)`, LIMIT 400 per pool; kelompokkan per
   siklus; pool lolos bila `reserve_usd` ≥ US$100rb; spread = (hi−lo)/dw.
5. Cek silang: total testing week vs `EVALUASI-TESTING-WEEK-2026-11-08.md`,
   `waitlist`, kolom outcome tersimpan, duplikat eksak.

### 6.2 Query yang dipakai (nama skrip/file, tanpa kredensial)

- Skrip kerja (scratch, di `/tmp`, bukan di repo):
  `/tmp/backtest_radar.py` (ronde 1: alert_log, deviations, poller_health,
  distribusi, uji proxy) dan `/tmp/backtest_radar2.py` (ronde 2: pools,
  rekonstruksi spread dari snapshots, cek GOOGLx, cek AAPLx/MSFTx).
  Output mentahnya: `/tmp/backtest_radar.json`, `/tmp/backtest_radar2.json`.
- Akses DB hanya lewat `turso_client.py` repo (Hrana `/v2/pipeline` via curl;
  token dari vault via `dynamic_credentials` entri `custom.turso-radar`).
  Token tidak pernah dicetak/ditulis di mana pun.
- Query terindeks yang dipakai: `alert_log` full (kecil); `deviations`
  `MIN/MAX/COUNT` + `GROUP BY ticker_id` + `WHERE ticker_id = ?` (indeks
  `(ticker_id, ts)`) + jendela per alert `WHERE ticker_id = ? AND ts > ? AND
  ts <= ? ORDER BY ts LIMIT 500`; `poller_health` full (6.079 baris, kecil);
  `snapshots` hanya `WHERE pool_id = ? AND ts > ? AND ts <= ? LIMIT 400`
  (indeks `(pool_id, ts)`). **Tidak ada `COUNT(*)` / `SELECT *` full-scan ke
  `snapshots`.**
- Estimasi rows read: ronde 1 ±19,6 rb baris dikembalikan + pemindaian
  agregat `deviations` ±153 rb baris (COUNT + bucket per ticker via indeks);
  ronde 2: **53.170 baris `snapshots`** + ±15 rb baris kecil lainnya.
  Total ±**220 rb rows read** (~0,04% dari limit bulanan 500 jt) — jauh di
  bawah ambang. Tidak ada satu pun tulis ke Turso.

### 6.3 Batasan — apa yang TIDAK dicek

- **Rekonstruksi tidak mereplikasi price-sanity guard 25% bot** (pool mana
  yang di-guard tidak tersimpan per siklus; `deviations.pools_excluded`
  hanya hitungan). Akibatnya spread rekonstruksi bisa melebihi angka bot
  saat ada tick buruk (SPYx 6 Nov: 140,6% vs 100,041% alert). Arah biasnya
  konservatif untuk TEPAT (spread tanpa guard lebih lama ≥ 0,5%).
- **Kaki akhir pekan tidak teruji** (0 alert `deviation_high`; 0 alert
  deviasi akhir pekan; `dev_vs_close_pct` kosong total).
- **Outcome dihitung dari data pasar on-chain saja** — tidak ada verifikasi
  ke harga saham acuan (tidak ada sumber equity berlisensi) dan tidak ada
  penilaian apakah pengguna akan benar-benar bisa keluar di harga itu
  (likuiditas saat eksekusi, slippage, jadwal redemption).
- **Dedup tidak diaudit mendalam:** hanya dicek tidak ada duplikat eksak;
  logika dedup 24 jam bot tidak diuji ulang dari log.
- **Anggota kanal Telegram tidak dihitung ulang** di ronde ini; angka
  "0 pengguna eksternal" mengandalkan evaluasi 8 Nov + `waitlist` = 0
  yang dihitung ulang hari ini.
- **Bukan audit kode bot** — hanya membaca logika ambang/dedup seperlunya
  untuk memetakan definisi; tidak ada review menyeluruh `bot.py`/`poller.py`.
- **Periode baru ~3 minggu** (target §5.4 bicara 8 minggu pertama) — angka
  ini interim, bukan vonis akhir 8 minggu.

### 6.4 Temuan yang perlu keputusan Septian (bukan saya)

1. Kolom `threshold_pct` menyimpan spread, bukan ambang — perlu diputuskan
   apakah diperbaiki pengisiannya (dan apakah 44 baris lama dikoreksi).
2. Kolom `outcome`/`closed_below_threshold_ts` tidak pernah diisi bot —
   perlu diputuskan apakah hasil backtest ini (atau proses otomatis)
   boleh menulis outcome ke `alert_log`. **Saya tidak menulisnya.**
3. Ambang 1,0% — tidak ada usulan perubahan dari saya; bila Septian menilai
   observasi §4 cukup untuk revisi, itu butuh revisi tertulis (§5.3).
4. GOOGLx: 5/6 alertnya tidak bisa divalidasi karena pool tipis — perlu
   diputuskan apakah alert untuk ticker 2-pool-tipis tetap diterbitkan
   dengan jejak validasi yang lemah seperti ini.
