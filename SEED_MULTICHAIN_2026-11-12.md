# Seed Multichain Radar Tokenized Stocks — 12 November 2026

**Waktu cek:** Kamis, 12 November 2026, ±20:36–21:00 WITA (12:36–13:00 UTC).
Verifikasi final: `verified_at_utc 2026-11-12T12:50:30Z`.
**Metode:** DexScreener API publik gratis (search + token-pairs), via `curl`
(urllib rusak lewat egress proxy — konvensi repo). Tanpa login, tanpa tulis
ke Turso. Pola sama seperti `verify_universe.py`, dengan tiga perbaikan
metode yang ditemukan selama ronde ini (lihat §5).
**Aturan Radar (§1.1):** total likuiditas gabungan ≥ $500.000 **DAN**
≥ 2 venue DEX. Tier 1 (§1.3): total ≥ $1 jt **DAN** volume 24j > 0 di
≥ 2 venue. Cap per issuer: maksimal 13 ticker (ACC Septian 12 Nov 20:22).

**Yang TIDAK masuk ronde ini (sesuai tugas):** Ethereum+Ondo (GAGAL —
`communityV3` bukan venue, vonis VERIFIKASI_MULTICHAIN_2026-11-12 §1e),
Elysium (belum aktif), Dinari/Securitize/Swarm/Backpack/Gate
(permissioned/RFQ/CEX-only), Hyperliquid spot wrapped (monitor saja).

## 1. Ringkasan vonis

| Issuer / chain | Diperiksa | Lolos aturan | Di-seed (cap 13) | Pool ≥ $100rb di-seed |
|---|---|---|---|---|
| Base + Coinbase | 42 simbol | **9** (6 T1 + 3 T2) | 9 | 15 |
| BNB + bStocks | 43 simbol | **8** (6 T1 + 2 T2) | 8 | 24 |
| Robinhood Chain + Robinhood | 42 simbol | **16** (14 T1 + 2 T2) | 13 (top by likuiditas) | 76 |
| **Total** | **127** | **33** | **30 ticker** | **115 pool** |

Kedalaman terlacak (qualDepth, jumlah pool ≥ $100rb yang di-seed):
Coinbase $12.405.400 · bStocks $21.097.586 · Robinhood $43.439.096 ·
**total ±$76,9 jt**.

Sebelumnya terverifikasi di VERIFIKASI_MULTICHAIN_2026-11-12 dan
dikonfirmasi ulang di sini: NVDAc $2.511.254 (dulu $2.486.872), TSLAB
$1.919.395 (dulu $1.920.721), TSLA/NVDA/SPY Robinhood $2.257.539 /
$7.188.145 / $8.096.925 (dulu $2.256.273 / $7.163.296 / $8.011.325).
Angka bergerak — ini data hidup, bukan angka beku.

## 2. Ticker LOLOS — yang di-seed (dry-run)

### 2a. Base + Coinbase — 9 ticker (semua di-seed)

| Ticker | Tier | Total liq | Venue | Pool ≥ $100rb | Token (kanonis) |
|---|---|---|---|---|---|
| NVDAc | 1 | $2.511.254 | 7 | 3 | NVIDIA Corporation `0xb200…08108C` |
| GOOGLc | 1 | $2.045.655 | 6 | 2 | Alphabet Inc. `0xb200…74f58B7` |
| AMZNc | 1 | $1.908.998 | 4 | 1 | Amazon.com Inc. `0xb200…483C2E8` |
| SNDKc | 1 | $1.785.306 | 4 | 1 | Sandisk Corporation `0xb200…a10c5` |
| MSTRc | 1 | $1.392.156 | 6 | 3 | Strategy Inc. `0xb200…92883d` |
| METAc | 1 | $1.009.639 | 6 | 2 | Meta Platforms Inc. `0xb200…61707C` |
| AAPLc | 2 | $727.045 | 5 | 1 | Apple Inc. `0xb200…1fb` |
| MSFTc | 2 | $582.084 | 3 | 1 | Microsoft Corporation `0xB200…3872B` |
| TSLAc | 2 | $533.364 | 3 | 1 | Tesla Inc. `0xb200…430cD0` |

Alamat lengkap ada di `verify_multichain_out.json` (tidak dicetak penuh di
sini agar laporan tetap terbaca; semua berawalan `0xb200…`, pola token B20
Coinbase).

### 2b. BNB Chain + bStocks — 8 ticker (semua di-seed)

| Ticker | Tier | Total liq | Venue | Pool ≥ $100rb | Token (kanonis) |
|---|---|---|---|---|---|
| NVDAB | 1 | $6.338.004 | 4 | 6 | NVIDIA (bStocks Tokenized Stock) `0x02Fc…7436` |
| SPCXB | 1 | $3.980.537 | 5 | 4 | SpaceX `0xbe9D…03E1` |
| QQQB | 1 | $3.206.808 | 4 | 5 | Invesco QQQ `0x2058…efc7` |
| GOOGLB | 1 | $2.635.655 | 3 | 2 | Alphabet Inc. `0x3F53…3238` |
| BABAB | 1 | $2.271.815 | 3 | 1 | Alibaba Group Holding Limited `0x4eF9…ff4ec` |
| TSLAB | 1 | $1.919.395 | 3 | 2 | Tesla, Inc. `0x5b19…292f` |
| CRCLB | 2 | $852.216 | 3 | 2 | Circle Internet Group Tokenized bStocks `0x80f3…fC0` |
| AAPLB | 2 | $800.537 | 3 | 2 | Apple `0x431a…89b7A` |

### 2c. Robinhood Chain + Robinhood — 13 ticker di-seed (dari 16 yang lolos)

Ticker_id yang di-seed memakai sufiks **`r`** (mis. `TSLAr`) — lihat §6,
butuh konfirmasi Chief sebelum live pertama.

| # | Ticker_id | Tier | Total liq | Venue | Pool ≥ $100rb |
|---|---|---|---|---|---|
| 1 | SPYr | 1 | $8.096.925 | 10 | 11 |
| 2 | NVDAr | 1 | $7.188.145 | 9 | 11 |
| 3 | GLDr | 1 | $5.060.385 | 5 | 7 |
| 4 | MSTRr | 1 | $4.439.999 | 6 | 7 |
| 5 | METAr | 1 | $3.721.428 | 7 | 7 |
| 6 | QQQR | 1 | $3.652.701 | 5 | 5 |
| 7 | CRCLr | 1 | $3.604.776 | 6 | 5 |
| 8 | GOOGLr | 1 | $2.750.143 | 8 | 5 |
| 9 | TSLAr | 1 | $2.257.539 | 7 | 6 |
| 10 | COINr | 1 | $1.510.648 | 5 | 3 |
| 11 | AAPLr | 1 | $1.504.667 | 9 | 4 |
| 12 | PLTRr | 1 | $1.277.773 | 7 | 2 |
| 13 | AMDr | 1 | $1.113.991 | 4 | 3 |

**Lolos aturan tapi DI LUAR cap 13 — TIDAK di-seed (cap-excluded):**
AMZNr T1 $1.110.250 · MSFTr T2 $785.562 · INTCr T2 $593.426.
Mereka tetap tercatat di `verify_multichain_out.json`; bila cap dilonggarkan
atau salah satu dari 13 besar gugur di verifikasi ulang, ketiganya adalah
cadangan pertama (urutan itu).

## 3. Ticker TIDAK LOLOS — alasan

### 3a. Delapan ticker baru Robinhood Chain (28 Okt 2026) — SEMUANYA GAGAL

| Ticker | Total liq | Venue | Alasan |
|---|---|---|---|
| JPM | $0 | 0 | Tidak ada pair DEX (alamat kanonis `0x07c4…409e` dari yTokenize; token-pairs 0 pair; yTokenize mencatat size $49,8 rb — itu bukan likuiditas pool DEX) |
| V | $8.045 | 1 | Token asli "Visa • Robinhood Token" `0x9BFF…d551`: 1 pair Uniswap saja |
| PYPL | $12.597 | 1 | 1 venue (Uniswap) |
| MCD | $52.231 | 2 | Token asli "McDonald's • Robinhood Token" `0x2fda…ce20`: $52.231 — lihat jebakan impostor di §5 |
| DIS | $13.034 | 2 | Di bawah $500rb |
| UBER | $9.455 | 1 | Di bawah $500rb; 1 venue |
| GDX | $14.064 | 1 | Di bawah $500rb; 1 venue |
| BMNR | $203.042 | 2 | Di bawah $500rb |

Juga gagal di Robinhood Chain: TSM $659.723 — total di atas $500rb tapi
**hanya 1 venue** (Uniswap); COST $424.958, LLY $307.287, AVGO $263.914
(1 venue), NFLX $191.980, BABA $108.808, HOOD $33.804 (1 venue), SHOP
$27.294, MRVL $24.611 (1 venue), QCOM $18.723 (1 venue), XOM $4.148
(1 venue); $0 / tidak ada pair: WMT, BAC, UNH, ABBV, SPOT, ARM, NVO.

### 3b. Base + Coinbase — gagal (33 simbol)

Di bawah $500rb: PLTRc $385.203 · AMDc $323.984 · NFLXc $279.426 ·
INTCc $231.493 · MRVLc $224.019 (1 venue) · AVGOc $219.535 ·
NVOc $46.004 · ARMc $10.535 · LLYc $12.304 · PYPLc $391 (1 venue) ·
CRCLc $12.653 (1 venue — pool Aero-nya susut dari $221.864 ke $12.653
dalam ±1 jam antara dua tarikan; pasar tipis bergerak cepat).
Tidak ada pair sama sekali: JPMc, HOODc, COINc, SPYc, QQQc, GLDc, BABAc,
DISc, Vc, MCDc, UBERc, XOMc, COSTc, WMTc, BACc, UNHc, ABBVc, QCOMc,
TSMc, SHOPc, SPOTc, GMc.

Catatan: 20 token Coinbase berpola alamat B20 (`0xb200…`) teridentifikasi,
bukan 13 seperti dicatat Dromos 12 Nov — selisih 7 token kemungkinan
peluncuran susulan / tidak tercatat di Dromos. Tidak mengubah vonis:
ke-11 token tipis itu semuanya gagal ambang.

### 3c. BNB Chain + bStocks — gagal (35 simbol)

Di bawah $500rb: **SPYB $353.725** (4 venue — gagal total; ini koreksi
penting: angka lama $778rb dari tarikan pertama ternyata mengandung pair
quote-side, lihat §5) · MSFTB $255.409 · METAB $220.232 · HOODB $198.221 ·
AMZNB $169.347 · NFLXB $164.122 (1 venue) · BMNRB $162.224 (1 venue) ·
INTCB $135.723 · TSMB $125.978 (1 venue) · MRVLB $40.776 (1 venue) ·
LLYB $3.127 (1 venue) · COINB $2.198 (1 venue) · AMDB $184 ·
PYPLB $0 (1 pair $0).
Tidak ada pair sama sekali: AVGOB, JPMB, PLTRB, GLDB, DISB, VB, MCDB,
UBERB, XOMB, COSTB, WMTB, BACB, UNHB, ABBVB, QCOMB, SHOPB, SPOTB, ARMB,
NVOB, GMB, GDXB. (bStocks mengklaim 104 produk — sebagian besar produk
itu tidak punya pool DEX sama sekali.)

## 4. Yang di-seed ke Turso: BELUM ADA — butuh ACC

**Tidak satu baris pun ditulis ke Turso live dalam ronde ini.**
Bukti: `seed_multichain.py --live` tanpa ACC ditolak (exit 2); read-back
`SELECT COUNT(*) FROM universe WHERE issuer IN
('coinbase','bstocks','robinhood')` = **0**, pools = **0**.

Yang sudah diuji dan siap:
- `verify_multichain.py` — jalan penuh 12 Nov 2026, exit 0, 33/127 lolos,
  output JSON di `/tmp/verify_multichain_out.json` (bukan di repo — output
  runbook mingguan, bukan file repo).
- `seed_multichain.py --dry-run` — jalan, exit 0: **30 ticker, 115 pool,
  151 INSERT + 63 DELETE** (30 universe + 115 pools + 3 redemption_windows
  + 3 por_feeds; DELETE 2×30 universe/pools + 3 redemption). SQL lengkap
  tercetak di dry-run; 0 pool ≥ $100rb ter-drop (semua pool lolos saringan
  venue bernama + quote bukan simbol sendiri).
- Varian hemat: `--max-pools-per-ticker 3` → **71 pool** (44 pool ter-drop
  sebagai "beyond cap") — lihat §6 butir 3.
- `--live` tanpa `RADAR_SEED_CONFIRM=ACC-2026-11-12` → REFUSED, exit 2.

**Yang masih butuh keputusan / pekerjaan sebelum live (di luar scope saya):**
1. **ACC Septian** untuk seed live (nilai env `RADAR_SEED_CONFIRM`).
2. **Konvensi ticker_id Robinhood** — saya pakai sufiks `r` (`TSLAr`,
   `NVDAr`, …) mengikuti pola `c`/`B` di desain §3.5; desain tidak
   menetapkan sufiks Robinhood. Alternatif: `TSLA-RH`. Konfirmasi Chief
   sebelum live pertama.
3. **Anggaran tulis membengkak vs estimasi desain** — desain §6.2
   mengasumsikan ±2,5 pool/ticker (Base 32 + BNB 27 pool ≈ +1,5 jt
   writes/bln). Realita: Robinhood rata-rata 5,8 pool ≥ $100rb/ticker
   → **115 pool ≈ +3,5 jt writes/bln** (snapshots ±994 rb baris ×3
   indeks ≈ 2,98 jt + deviations 30 ticker ≈ 0,52 jt), vs estimasi
   desain +2,1 jt. Baseline 1,3 jt → total ±4,8 jt/bln dari 10 jt
   (48%). Opsi: seed semua 115 pool, atau `--max-pools-per-ticker 3`
   (71 pool ≈ +2,4 jt/bln → total ±3,7 jt/bln, 37%). Keputusan Chief.
4. **Poller belum mendukung chain baru.** `poller.py` saat ini hanya
   Solana/xStocks (`XSTOCKS_MINTS`); perubahan §4.1 desain (alamat token
   per chain/issuer, batch per chain) belum dibangun — itu pekerjaan
   terpisah, bukan file saya. Seed saja TIDAK memulai polling.
5. **Ticker dekat garis ambang — verifikasi ulang mingguan wajib:**
   TSLAc $533.364 (hanya +6,7% di atas $500rb), MSFTc $582.084,
   INTCr $593.426 (cap-excluded), AAPLc $727.045. Bila gugur minggu
   depan, seed berikutnya harus menonaktifkannya (skrip seed idempotent:
   DELETE + INSERT ulang per ticker).

## 5. Temuan metode — tiga koreksi yang masuk ke skrip

1. **Token-pairs menghitung pair quote-side (temuan terbesar).**
   Endpoint `token-pairs` mengembalikan pair di mana token menjadi BASE
   **atau QUOTE**. Versi pertama skrip ini menjumlah semuanya — total
   membengkak sampai ±60%: SPYB tampak $778rb (Tier 2), padahal base-side
   saja $354rb (GAGAL); SPCXB $6,28 jt → $3,98 jt; QQQB $5,16 jt →
   $3,21 jt; GLD Robinhood $6,23 jt → $5,06 jt. Buktinya: pair
   MarsCoin/SPCXB ($1,01 jt, harga $0,039 — itu harga MarsCoin, bukan
   SPCXB) dan GLDSTN/GLD ($435rb). **Perbaikan:** hanya pair dengan
   `baseToken.address == alamat kanonis` yang dihitung — di
   `verify_multichain.py::base_side_pairs`. Semua angka di laporan ini
   sudah base-side saja.
2. **Impostor mengalahkan token asli bila hanya pakai likuiditas terbesar.**
   Simbol `MCD` di Robinhood Chain: token terbesar adalah "Meridian
   Capital" ($829.220, 1 venue), bukan McDonald's. Token asli McDonald's
   `0x2fda…ce20` hanya $52.231. **Perbaikan:** pemilihan kanonis
   memprioritaskan petunjuk issuer (Coinbase: alamat `0xb200…`; Robinhood:
   nama mengandung "Robinhood Token"); bila tak ada yang cocok, beri
   peringatan "manual review". Untuk bStocks tidak ada petunjuk yang
   andal — kanonis = likuiditas terbesar, dan token lain dicatat sebagai
   peringatan.
3. **Search DexScreener tidak andal untuk simbol pendek/umum.**
   `q=JPM` mengembalikan 30 pair yang didominasi chain lain + satu pair
   sampah; `q=V` melempar error (baseToken berupa string). **Perbaikan:**
   `KNOWN_ADDRESSES` — JPM `0x07c4…409e`, V `0x9BFF…d551`, MCD
   `0x2fda…ce20` (sumber: yTokenize + pencarian nama DexScreener) —
   diverifikasi langsung via token-pairs. Ditambah guard `isinstance`
   di semua akses `baseToken`.
4. **Batas 30 pair + venue tanpa nama.** Token-pairs mengembalikan maks
   30 baris — bila 30 baris kembali, total adalah **batas bawah** dan
   pool ≥ $100rb bisa tersembunyi di luar potongan (ditandai
   `truncated` per ticker; 25 dari 33 ticker lolos terkena). DexId
   berupa alamat mentah `0x…` (mis. pool NVDAB $531rb di
   `0xB6aC…`) adalah venue tanpa nama — bukan venue terverifikasi
   (pelajaran yang sama seperti `communityV3`); seed men-drop pool
   semacam itu, dan semua ticker lolos tetap punya ≥ 2 venue bernama
   tanpa mereka.

## 6. File yang dibuat (hanya 3 file baru — tidak ada file lain disentuh)

- [`seed_multichain.py`](sandbox:/workspace/radar-tokenized-stocks/seed_multichain.py) —
  baca `verify_multichain_out.json`, terapkan tier + cap 13/issuer +
  saringan pool trackable, cetak SQL (`--dry-run`, default) atau eksekusi
  (`--live`, hanya dengan `RADAR_SEED_CONFIRM=ACC-2026-11-12`).
  Opsi `--max-pools-per-ticker N`. Ikut menulis baris dokumentasi
  `redemption_windows` + `por_feeds` (status `unknown`) per issuer baru.
- [`verify_multichain.py`](sandbox:/workspace/radar-tokenized-stocks/verify_multichain.py) —
  verifikasi ulang live per ticker (search + token-pairs base-side,
  petunjuk issuer, override alamat, flag truncated). Read-only, tanpa
  kredensial; aman dijalankan mingguan:
  `python3 verify_multichain.py --out /tmp/verify_multichain_out.json`.
  Mendukung `--group` dan `--symbols` untuk cek sebagian.
- `SEED_MULTICHAIN_2026-11-12.md` — laporan ini.

Uji yang dijalankan: `python3 -m py_compile` kedua skrip (OK);
`verify_multichain.py` penuh (exit 0, 127 kandidat, 33 lolos);
`seed_multichain.py --dry-run` (exit 0, 30 ticker / 115 pool);
`--dry-run --max-pools-per-ticker 3` (71 pool); `--live` tanpa ACC
(REFUSED, exit 2) + read-back Turso 0 baris baru.

## 7. Yang tidak bisa diverifikasi / catatan

- Token Ondo di Robinhood Chain (15 saham/ETF per PR Ondo 5 Nov):
  tidak ditemukan sebagai token kanonis terpisah dalam ronde ini —
  semua simbol yang dicek kanonisnya bernama "Robinhood Token".
  Alamat Ondo di chain ini (mis. TSLAon `0xb197…4309`, truncated di
  report.md) tidak diverifikasi; status UNVERIFIED.
- Ethereum+Ondo tidak dicek ulang (vonis GAGAL sudah final di
  VERIFIKASI_MULTICHAIN_2026-11-12); Elysium tidak dicek ulang
  (0 pool berlikuiditas, pantau via `check_elysium_weekly.py`).
- Lisensi DexScreener (larangan resale/redistribusi + produk kompetitor,
  report.md §7b) tetap berlaku bila data ini ditampilkan/disimpan di
  Radar publik — cek ToS primer sebelum display publik chain baru
  (tugas minggu pertama, desain §7.2 butir 7).
- Angka likuiditas bergerak antar tarikan dalam hitungan menit
  (mis. SPY Robinhood $7,97 jt → $8,10 jt; CRCLc $221rb → $12,7rb).
  Angka di laporan ini adalah potret 12 Nov 2026 ±20:50 WITA.
