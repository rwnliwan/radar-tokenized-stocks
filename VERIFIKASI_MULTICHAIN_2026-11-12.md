# Verifikasi Live Multichain Radar Tokenized Stocks

**Tanggal/jam cek:** Kamis, 12 November 2026, ±20:24–20:30 WITA (12:24–12:30 UTC).
**Metode:** API publik gratis, tanpa login/kredensial, tanpa tulis ke Turso.
Pola sama seperti `verify_universe.py`: DexScreener search per simbol, hanya pair
dengan `baseToken.symbol` sama persis, token kanonis = alamat dengan total
likuiditas terbesar (menyingkirkan token impostor). Semua fetch via `curl`
(urllib rusak lewat egress proxy — konvensi repo). Harga acuan saat cek:
TSLA ±$389, NVDA ±$160,5, SPY ±$758, AAPL ±$355, GOOGL ±$300.

**Aturan Radar (§1.1):** total likuiditas gabungan ≥ $500.000 **DAN** ≥ 2 venue DEX.
Tier 1 (§1.3): total ≥ $1 jt **DAN** volume 24j > 0 di ≥ 2 venue. Pool yang
dihitung per ticker: semua pair token kanonis (pool < $100rb dicantumkan tapi
tidak mengubah vonis).

**Sumber API yang dipakai**
- DexScreener search: `https://api.dexscreener.com/latest/dex/search?q=<simbol>`
- DexScreener token-pairs: `https://api.dexscreener.com/latest/dex/tokens/<alamat>`
- DexScreener pair detail: `https://api.dexscreener.com/latest/dex/pairs/<chain>/<pair>`
- Hyperliquid: `POST https://api.hyperliquid.xyz/info` (`spotMeta`, `l2Book`)
- RPC Ethereum publik (hanya baca): `https://ethereum.publicnode.com`,
  `https://eth.drpc.org` (`eth_call`: `factory()`, `fee()`, `getPool()`, `slot0()`)
- Blockscout Ethereum: `https://eth.blockscout.com/api?module=contract&action=getsourcecode&address=<alamat>`

---

## 1. Ethereum + Ondo — VONIS: GAGAL (venue ke-2 tidak terverifikasi)

### 1a. TSLAon — `0xf6b1117ec07684D3958caD8BEb1b302bfD21103f`
Total likuiditas **$6.964.809** (9 pair) — di atas $500rb, TAPI:

| Chain | DEX (dexId) | Pair | Quote | Liq USD | Vol 24j USD | Harga |
|---|---|---|---|---|---|---|
| ethereum | communityV3 | `0xF2006D44339E5C2c479d450a97884d4E20D028AD` | USDC | $5.010.902 | $394.484 | $386,90 |
| ethereum | communityV3 | `0x49b7b66457297f9E0E763BBb151B6DB0c149E988` | USDC | $1.890.138 | $165.929 | $388,84 |
| ethereum | uniswap | `0x31227b50eCCDC9C589826AA2D9E7C5619B1895Da` | USDC | $56.481 | $5.851 | $388,09 |
| ethereum | communityV3 | `0xfd62Ce2489f37B9357CD1Aa66a33351580B33231` | USDC | $2.609 | $72 | $389,21 |
| ethereum | uniswap | `0xCBc44d015166f693eDE658A533191D39DBc4bAC1` | USDC | $2.426 | $512 | $390,36 |
| ethereum | communityV3 | `0x52757BD6B226b50a75aC4Aec553Db7F338E841A7` | USDC | $982 | $72 | $382,27 |
| ethereum | uniswap | `0xba7e7e0bdbacd89f7254c07517e949b09f7a24c82dac6f43b01d0db6a8ac4cc2` | USDC | $697 | $55 | $390,11 |
| ethereum | communityV3 | `0xbcD5a4823C3B3faF81EECEfd3b37E1185419E9Ee` | USDC | $364 | $5.123 | $388,59 |
| ethereum | uniswap | `0x828ce5b86489c5fe6a15cf6be20c0880a260244a9e5bae11317044ad2567cc00` | USDC | $208 | $11 | $386,15 |

Venue yang **teridentifikasi**: hanya Uniswap (±$60rb). Sisanya (±$6,90 jt)
berlabel `communityV3` — lihat §1e. **Vonis: GAGAL** di bawah pembacaan ketat
aturan (1 venue teridentifikasi). Bila `communityV3` dihitung sebagai venue,
totalnya lolos — tapi lihat red flag di §1e sebelum memutuskan begitu.

**Catatan selisih vs riset pagi:** report.md pagi ini mencatat TSLAon ±$0,77 jt
(Community v3 $0,50 jt + $0,19 jt, Uniswap $0,07 jt). Angka saya sekarang
persis **10×** di kedua pool besar ($5,01 jt + $1,89 jt), sementara angka
Uniswap cocok ($0,07 jt vs $0,06 jt). Kemungkinan besar riset pagi salah baca
desimal; angka di sini diukur langsung dari API dan dikonfirmasi halaman
DexScreener pair (`Liquidity, $5.0M`, crawl 12:24 UTC). Tetap dicatat sebagai
selisih yang belum bisa dipastikan penyebabnya.

### 1b. NVDAon — `0x2D1F7226Bd1F780AF6B9A49DCC0aE00E8Df4bDEE`
Total **$406.432** (16 pair) — **di bawah $500rb → GAGAL** (sebelum soal venue).

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| communityV3 | `0x6eE97deA63C77D1aeE3f403BFF4aD1dEF3Fb6683` | USDC | $134.891 | $23.403 |
| communityV3 | `0xb92d54C177925832014391FF2d8d079473c530C9` | USDC | $99.816 | $2.146 |
| uniswap | `0xa9a6651fba74df1aab94065ffaabe750d6ed835b94a9e28925ec79beec2d5f73` | USDC | $50.663 | $13.813 |
| uniswap | `0xc9b4bC7C15423FCFe6B75aB5118bA773945A3A46` | USDC | $46.384 | $12.611 |
| communityV3 | `0xFD4414D70D3d5C3f21D59f75bd1cdD86fAFA7d9C` | USDC | $30.060 | $3.573 |
| communityV3 | `0xD79A68214Bc04890Bb23aDae3A27C0F8F53fE02e` | USDC | $29.368 | $6.342 |
| (10 pair lain, semua < $7rb: uniswap USDC/USDT/ZIK/sUSDe) | | | ±$15.251 | |

### 1c. SPYon — `0xFeDC5f4a6c38211c1338aa411018DFAf26612c08`
Total **$112.125** (4 pair) — **GAGAL** (di bawah $500rb, 1 venue).

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| uniswap | `0x5638bbDE046EC2EFC7C8f3fd8DC5A9A1016f7EEB` | USDC | $92.743 | $7.929 |
| uniswap | `0x7108e2a45472143df9b723298cb0dde0550ce02cff3af71a3ef60f20aa1a0ae6` | ETH | $14.049 | $853 |
| uniswap | `0x1761695c6931d748ef8cfacce8cec47e2a01ab722ca1ffed68b35b0b1230254d` | XAUt | $5.020 | $1.033 |
| uniswap | `0xcf15b6adefd126e73c810aee0fc7f4f8d9a43fd7cdfb3bcb7c16a45876f12a23` | PAXG | $313 | $33 |

### 1d. AAPLON — `0x14c3abF95Cb9C93a8b82C1CdCB76D72Cb87b2d4c`
Total **$25.651** (5 pair) — **GAGAL** (di bawah $500rb).

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| uniswap | `0xad82C9EB065a5CFed71DB087e4a52C8a09c69921` | USDC | $25.546 | $2.314 |
| communityV3 | `0x0d56FfD59b46B237dc66D94c9EcC6Bcd610490dc` | MUon | $105 | $8 |
| (3 pair uniswap $0: ZCX/IBOB/FSTOCK2) | | | $0 | $0 |

### 1e. Penyelidikan `communityV3` — identitas venue ke-2

**Fakta on-chain (via `eth_call` ke RPC publik, terverifikasi langsung):**
- Pool besar TSLAon `0xF2006D44…`: `factory()` =
  `0x00a38533c68327aBE0Cc265436e036066E2D6B38`; `fee()` = **20000 (2%)**;
  `slot0()` hidup, harga $386,90 (wajar vs saham ±$389).
- Pool besar ke-2 `0x49b7b664…`: `factory()` sama; `fee()` = 0x3a98 = **15000 (1,5%)**.
- Factory resmi Uniswap V3 (`0x1F98431c8aD98523631AE4a59f267346ea31F984`):
  `getPool(TSLAon, USDC, 500)` = `0x02f7e3a9…`, `3000` = `0xcbc44d01…`,
  `10000` = `0x31227b50…` — persis ketiga pair berlabel `uniswap` di atas.
  Factory resmi **tidak** mengandung pool `communityV3` mana pun.
- Factory misterius `getPool(TSLAon, USDC, 10000)` = `0xfd62ce24…`,
  `20000` = `0xF2006D44…` — pool `communityV3` berasal dari factory ini.
- Blockscout: factory `0x00a38533…` terverifikasi sebagai
  **ContractName `UniswapV3Factory`, compiler v0.7.6** — klon verbatim factory
  Uniswap V3 (bukan factory resmi). `owner()` mengembalikan `0x0`.
- Factory di-deploy **3 Sep 2026** (tx
  `0xa739d72a2edcfd501b1bd55858a202dfb5208080270505ba26d706a4616ba63e`,
  ts 1788426299) oleh EOA `0xa534276ae729ea7c93ae8b02b7fd54f2c07bf409`
  (tanpa label/identitas yang bisa diverifikasi); deployer lalu memanggil
  `enableFeeAmount` untuk tier non-standar (termasuk 2% dan 2,56%).
- DexScreener sendiri **tidak mengenalinya sebagai DEX bernama**: pair lain
  dari factory yang sama tampil sebagai **"Unknown DEX — See DEX Listing
  Factory: 0x00a38533…"** (mis. NBISon
  `0xf2ba6be3759acff84e43df369e900a7f898e20a0`).
- Tidak ditemukan merek, frontend, router, atau dokumentasi untuk factory ini
  (pencarian web 12 Nov 2026). Label `HLDEXP` di cuplikan DexScreener BUKAN
  nama DEX — itu gabungan label tautan UI `HLD` (holders) + `EXP` (explorer).

**Red flag tambahan pada pool `communityV3` TSLAon:**
- Fee 2% / 1,5% — jauh di atas tier standar Uniswap (0,01%/0,05%/0,3%/1%);
  mahal untuk market-making saham tokenized.
- Arus 24j satu arah: pool $5,01 jt mencatat **27 buys, 0 sells**,
  vol $394.484; harga tetap wajar ($386,90) tapi tidak ada penjualan sama sekali.
- Likuiditas 10× lipat vs catatan riset pagi yang sama hari (§1a).

**Kesimpulan §1e: `communityV3` = label generik DexScreener untuk pool dari
klon factory Uniswap V3 anonim, tanpa identitas DEX yang bisa diverifikasi.
BUKAN venue independen yang terverifikasi. Jangan dihitung sebagai venue ke-2
dalam aturan Radar.** Pool-nya nyata on-chain (kontrak `UniswapV3Pool` asli,
harga wajar), tapi "venue"-nya tidak bisa dibuktikan independen dari Uniswap —
dan bisa saja satu deployer/market-maker yang sama.

---

## 2. Robinhood Chain — VONIS: LOLOS, ketiganya Tier 1

Token kanonis diverifikasi dari nama + harga wajar (TSLA ±$389, NVDA ±$160,
SPY ±$758). Ada token impostor bernama mirip dengan harga absurd — lihat
catatan per ticker; yang dipakai hanya token kanonis (likuiditas terbesar).

### 2a. TSLA (Robinhood) — `0x322F0929c4625eD5bAd873c95208D54E1c003b2d`
"**Tesla • Robinhood Token**". Total **$2.256.273** (25 pair).
Venue: **uniswap + metric (2 venue)**. **LOLOS — Tier 1.**

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| uniswap | `0xA953CA88ff430e9487c60cA34d757414f4efdA07` | WETH | $519.683 | $69.147 |
| uniswap | `0xf4ACdAEEB7022862A763C9B1B885e11191c889E3` | USDG | $454.902 | $201.452 |
| uniswap | `0x8517f8071ae5b831b738052f12125e8e3d6c158b78728aa44ce3b25e5104d32e` | USDG | $404.372 | $125.551 |
| uniswap | `0x3ea70ce0b34473692549f97e630a1d82dc05cea94fa55f81b50f10c8c6d8186f` | SPY | $254.791 | $457.113 |
| metric | `0x99932C7660dD58cf19f0e82e97F288d88d033480` | USDG | $212.862 | $392.650 |
| uniswap | `0x0927698e8716bbb958a2cde0fc4f31d7a2b9a5b0ee1e501dc15e29788277dfa2` | SPCX | $112.150 | $134.152 |
| uniswap | `0xd5effce87036cd858146c0c15fa825c231a9de1843200ca108e431e431331e8e` | USDG | $70.982 | $51.886 |
| uniswap | `0xb2a6d67bf3fc511d11cac788a531655f5a7b60cd31c8ff386f0476121741e751` | ETH | $66.458 | $3.092 |
| uniswap | `0xa821b3724b451b22476c5347471b2a96d185b86af8760f226273e34ab4b2b8a0` | SPY | $62.216 | $24.112 |
| (+ 16 pair kecil, total ±$97rb) | | | | |

### 2b. NVDA (Robinhood) — `0xd0601CE157Db5bdC3162BbaC2a2C8aF5320D9EEC`
"**NVIDIA • Robinhood Token**". Total **$7.163.296** (27 pair).
Venue: **uniswap + aero + metric + ramses (4 venue)**. **LOLOS — Tier 1.**

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| uniswap | `0xd4EB21209C4D6093f80B5b84f5C45cc093EA14a3` | USDG | $1.974.152 | $9.890.693 |
| uniswap | `0x62AB521f71431f78ac374CdbadC6cda3c8916b6C` | WETH | $1.125.425 | $11.895.796 |
| uniswap | `0xda14bf8a87711e1f30dbe620f2df3fdf371f7503f1a72202d15631f657651ec0` | SPY | $637.452 | $2.354.704 |
| uniswap | `0xC0Be1cb0f674D9737C72B2A63fC542361185b807` | WETH | $634.376 | $1.365.118 |
| aero | `0xA1513DA56f71b83D98124D645828A14a191b8010` | USDG | $469.618 | $1.088.170 |
| metric | `0xBc6426CdBCE142dfbff33303dc0923509f61eedc` | USDG | $451.000 | $2.237.312 |
| uniswap | `0x3bb34a44f1b2b5f32c034c38a53065a521a47b199700fa9bd19d60985ff24bf1` | USDG | $419.869 | $235.448 |
| uniswap | `0xa95b1fbdccb15d2b07509b980f63adab8a94303b1781f5ebc53b72942d12ddc1` | ORBIO | $409.594 | $38.307 |
| uniswap | `0x7990aad9e8fb048f49a155a7df5603db0366f0657035b78eb4196395cccb3dcd` | USDG | $217.863 | $178.612 |
| uniswap | `0xbc732a1a0baabce2574ec2bca24fccad8e2c38a061a37cefc17a2fd12809394f` | SPY | $204.039 | $6.495 |
| ramses | `0xdac1904D823F7d6bcAaF431ceEe40c934fEd321b` | USDG | $120.998 | $691.024 |
| uniswap | `0x71f9660f9535e3e81d720696a58ea80274da8b2c6eb7c3acb22611d977439a5c` | ETH | $96.730 | $602.653 |
| (+ 15 pair kecil, total ±$402rb) | | | | |

Impostor: `0xA3284897ad7c8FED700b04f573Cf64E4f6c10f2c` (" NVIDIA Robinhood
Token", spasi di depan) — $490.989, harga $0,0006137 (absurd), vol 24j $0.
**Bukan** token kanonis; abaikan.

### 2c. SPY (Robinhood) — `0x117cc2133c37B721F49dE2A7a74833232B3B4C0C`
"**SPDR S&P 500 ETF Trust • Robinhood Token**". Total **$8.011.325** (25 pair).
Venue: **uniswap + aero + metric + ramses + giga (5 venue)**. **LOLOS — Tier 1.**

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| uniswap | `0xfe2a80bb5618fd14984b92ca6d45bf5ba67443ddb1435e28b2e48df2fc1526cd` | USDG | $2.655.714 | $490.483 |
| uniswap | `0xe5923c8a8be481ec89a2ca784a2bbfa4235de6d88f92260fd66b660c4babf907` | USDG | $1.114.753 | $1.713.649 |
| uniswap | `0x8674c1c5544f3c9563565b5d4bd5916701d90b3559b072acf7cef5b4fc5b8dcd` | USDG | $1.007.736 | $399.444 |
| uniswap | `0xDDCBBa3666f578E3F09516f21Ff85BFee859AB5e` | WETH | $844.663 | $1.719.607 |
| uniswap | `0x509c6c6826ef06e0e29f24f18d9389533c52358a3b385d99a67a2afbb07f23c6` | ETH | $599.542 | $196.589 |
| aero | `0x05aFb8E895e77Ce70F79056137eA606b05BF5abD` | WETH | $382.896 | $2.461.513 |
| uniswap | `0xa7Bb1AC63BBaB0C44316E6c8C455213441689167` | USDG | $273.688 | $234.379 |
| metric | `0x13783E80F95DC9Fc10622451a3eE755593F0E666` | USDG | $229.017 | $485.363 |
| uniswap | `0xe1ae6a4c6ccc9f037389a8d50a4f577bde1a9fe01d85d88ecbbd39955ce53288` | USDG | $222.064 | $1.507.881 |
| ramses | `0x38453c115607463Ac284820Ce959831042f3Df4E` | USDG | $211.747 | $1.043.155 |
| aero | `0x4A9b7cCBa4a3CD9Ee604AfA95d3DfA77D0d593e5` | USDG | $182.135 | $935.931 |
| giga | `0xaBE817Af4fE3420152Ab1464a45dc971e7EaaeAE` | USDG | $44.679 | $162.728 |
| (+ 13 pair kecil, total ±$243rb) | | | | |

Token kedua `0xe8340a24EB85da7630558d211E1aaEEE1D7F626B` (nama sama, $386.787,
harga $0,0004297, vol 24j $2) — bukan kanonis; abaikan.

**Catatan Robinhood:** volume 24j sangat tinggi vs likuiditas (mis. NVDA
±$30 jt vol vs $7,16 jt liq) — konsisten dengan laporan Bitquery/ByKaranteli
di report.md (volume besar Oktober 2026), tapi turnover > 1×/hari patut
dipantau; bukan alasan gagal karena aturan hanya soal likuiditas + venue.

---

## 3. Hyperliquid spot (wrapped xStocks) — VONIS: MONITOR SAJA (terkonfirmasi)

`POST https://api.hyperliquid.xyz/info` — `spotMeta`: universe spot 351 pair.
Token: 845 = NVDAX ("Wrapped NVIDIA xStock"), 846 = SPYX ("Wrapped SP500
xStock"), 855 = TSLAX ("Wrapped Tesla xStock"), 856 = AAPLX ("Wrapped Apple
xStock"). Universe: `@702` = NVDAX, `@703` = SPYX, `@712` = TSLAX,
`@713` = AAPLX (semua `isCanonical: false`, quote USDC).

`l2Book` (12 Nov 2026 ±20:26 WITA; dicek ulang ±20:29 WITA, angka bergerak
sedikit — data hidup):

| Coin | Label | Best bid | Best ask | Spread | Keadaan book |
|---|---|---|---|---|---|
| @712 | TSLAX | $256,0 × 0,04 lalu $10 × 100 | **TIDAK ADA** | — | **Tidak ada pasar**: 0 ask; bid absurd (wajar ±$389) |
| @702 | NVDAX | $160,75 × 69,76 | $161,02 × 2,0 | ±0,17% | Nyata tapi tipis; depth tampak puluhan $rb |
| @703 | SPYX | $761,99 × 0,14 | $764,69 × 2,0 | ±0,35% | Nyata tapi tipis; depth tampak puluhan $rb |
| @713 | AAPLX | $10,0 × 1,0 | **TIDAK ADA** | — | **Tidak ada pasar**: 0 ask; bid absurd (wajar ±$355) |

**Vonis: MONITOR SAJA — terkonfirmasi, dan lebih tajam dari draf awal:**
bukan sekadar "book tipis" — TSLAX dan AAPLX **tidak punya sisi ask sama
sekali** (tidak bisa dibeli di harga berapa pun), sementara NVDAX/SPYX punya
book nyata tapi tipis (kedalaman tampak puluhan ribu dolar, bukan jutaan).
Bukan kaki Radar. Tetap dipantau via `check_elysium_weekly.py` (bagian
Hyperliquid) untuk melihat bila suatu saat book-nya menjadi dalam.

---

## 4. Elysium + xStocks — VONIS: BELUM AKTIF

- DexScreener search `TSLAx` filter `chainId=elysium`: **0 pair**.
- DexScreener `token-pairs` alamat EVM TSLAx
  `0x8aD3c73F833d3F9A523aB01476625F269aEB7Cf0`: 1 pair total, semuanya
  Ethereum, **0 di Elysium**.
- Cek menyeluruh 13 simbol xStocks (`check_elysium_weekly.py`, 12:29 UTC):
  **1 pair** ditemukan — GOOGLx/Uniswap v4
  `0x012b0cbd305f5c76a653a3c69ebcf988913f7c1f8368cfce2cd1cd5a4382d624`,
  base `0x23eFCE82A970900E76904fD026Ec7Bf249f03794` ("Alphabet xStock"),
  quote HYPE, dibuat 11 Nov 2026 — **tapi likuiditas $0** (field liquidity
  tidak ada), harga $0,000003015 (absurd; GOOGL wajar ±$300), FDV $3.016,
  vol 24j $1.050 (16 buys / 19 sells — debu). Bukan pasar hidup.
- **Vonis: BELUM AKTIF — 0 pool berlikuiditas.** Pengumuman "day-one"
  9 Nov 2026 belum menjelma jadi pasar. JANGAN bangun integrasi Elysium;
  pantau mingguan saja (skrip di bawah).

---

## 5. Verifikasi ulang singkat: Base + Coinbase dan BNB + bStocks

Satu ticker per issuer, diukur ulang hari ini (12 Nov 2026 ±20:25 WITA):

### 5a. NVDAc (Base) — `0xb20000000000000000000078ee7ce2fE4908108C`
"**NVIDIA Corporation**". Total **$2.486.872** (27 pair; pagi ini report.md
±$3,3 jt — bergerak, tetap jauh di atas ambang). Venue: **aero + aerodrome +
uniswap + nami (4 venue)**. **LOLOS — Tier 1.**

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| aero | `0xF668e21993f0ACd7ab00BB1cFbAeD0df28A3C8EC` | USDC | $1.660.318 | $10.024.411 |
| aerodrome | `0x853F5f1B92b16714Fe6CDA67CAad0856B83C7ab9` | USDC | $396.685 | $74.002 |
| uniswap | `0xe82fa069a5e01a6dc36c6736b5de4f721d726291b080c69b48e21b9c5a11a2ad` | USDC | $163.285 | $45 |
| aero | `0xCe56168C09f4B7FCa30523822C48008705C01156` | WETH | $83.276 | $1.360.178 |
| uniswap | `0xb21769526e3a0814752628ec6c6e08efc883a025a18c64ee3ad376aa67728a18` | USDC | $64.202 | $4.028 |
| uniswap | `0xc8c52ec416fe9d3b6e70a2e4ccde7cece3b8318d109a1aa1bbc7e0980c4fe985` | USDC | $34.764 | $284 |
| nami | `0x337beA70489CD71a8C3951C1Aa49C637b4b9B122` | USDC | $20.751 | $297.717 |
| (+ 20 pair kecil, total ±$64rb) | | | | |

Impostor: `0x345c77838a623A2128a00509f977A973CE2f5f43` ("NVIDIA Curenncy"
[sic]) — $522.735, harga $0,0006969. Bukan token kanonis; abaikan.

### 5b. TSLAB (BNB Chain) — `0x5b1910eAaD6450E50f816082Aa078C41F10C292f`
"**Tesla, Inc.**". Total **$1.920.721** (11 pair; pagi ini report.md ±$2,35 jt
— bergerak, tetap jauh di atas ambang). Venue: **pancakeswap + metric +
uniswap (3 venue)**. **LOLOS — Tier 1.**

| DEX | Pair | Quote | Liq USD | Vol 24j |
|---|---|---|---|---|
| pancakeswap | `0xB0f5E5400E8F0F7C242F2b7740C004f020579c41` | USDT | $1.652.728 | $803.128 |
| metric | `0xf449D597cef44FCb9fDbA861427d066C585C450d` | USDT | $101.814 | $288.403 |
| uniswap | `0x53C6291d0A5A02C76CedfA1b8F57A8ac3762F7a9` | USDT | $47.450 | $125.327 |
| pancakeswap | `0x162d64349c57ff06ad69551870F0414F694e6491` | WBNB | $45.247 | $130.795 |
| pancakeswap | `0x613eBCfCf41749571d659A0BF3E2C0032Fd4859E` | USDT | $44.857 | $5.691 |
| pancakeswap | `0x787F3EbB965a7c5484D08B143809d8c4B043cD45` | WBNB | $15.796 | $10.202 |
| metric | `0xA9a11a80857A1151E8d8d4eDD3C98815C74836Fb` | USDT | $10.815 | $6.017 |
| (+ 4 pair kecil, total ±$2rb) | | | | |

Impostor: `0xcD0eA1001d9AeB998A5A9C52862c7840f5c4689B` ("Tesla Tokenized
bStocks") — liq $0. Bukan kanonis; abaikan.

### 5c. Catatan sampingan: TSLAx Solana (universe lama)
Dari pencarian yang sama: TSLAx Solana total **$3.337.968** (Raydium USDC
$2.296.650, vol $1.525.162) — kaki lama Radar sehat. Anomali kecil: pair
Meteora TSLAx/SPCX ($464.095 liq) menampilkan harga $3.876.453,92 — harga
sintetis rusak karena quote SPCX, vol 24j hanya $58; bukan temuan baru,
dicatat saja.

---

## 6. Daftar top ticker yang direkomendasikan per issuer

Status: ✅ = terverifikasi live 12 Nov 2026 (angka di atas); ⏳ = kandidat
dari report.md, likuiditas pool-nya **belum** diverifikasi per ticker —
wajib cek DexScreener per ticker sebelum masuk Radar (jangan jadikan angka
report.md sebagai bukti lolos).

### 6a. Base + Coinbase Tokenized Stocks (13 token, Dromos 12 Nov 2026)

| # | Ticker | Status | Catatan |
|---|---|---|---|
| 1 | NVDAc | ✅ LOLOS Tier 1 | $2.486.872, 4 venue (§5a) |
| 2 | MSTRc | ⏳ prioritas verifikasi | Top-3 Dromos by tokenized value |
| 3 | SNDKc | ⏳ prioritas verifikasi | Top-3 Dromos by tokenized value |
| 4–13 | (10 token Coinbase lain) | ⏳ perlu enumerasi | Daftar lengkap dari Dromos/Coinbase token list, lalu cek per ticker |

### 6b. BNB Chain + Binance bStocks (104 produk, RWA.xyz 3 Nov 2026)

| # | Ticker | Status | Catatan |
|---|---|---|---|
| 1 | TSLAB | ✅ LOLOS Tier 1 | $1.920.721, 3 venue (§5b) |
| 2 | NVDAB | ⏳ prioritas verifikasi | $3,67 jt, 13 pool — angka 20 Sep 2026 (cleansky), sudah kedaluwarsa |
| 3 | SPYB | ⏳ prioritas verifikasi | Alamat `0x7138…82d8` (report.md §2, truncated) |
| 4 | SPCXB | ⏳ prioritas verifikasi | Alamat `0xbe9d…03e1` (report.md §2, truncated) |
| 5 | QQQB | ⏳ prioritas verifikasi | Alamat `0x2058…efc7` (report.md §2, truncated) |
| 6–13 | (ticker bStocks lain, mis. AAPLB/MSFTB) | ⏳ perlu enumerasi | Dari daftar 104 produk, lalu cek per ticker |

### 6c. Robinhood Chain + Robinhood Stock Tokens (baru — dari §2)

| # | Ticker | Status | Catatan |
|---|---|---|---|
| 1 | SPY (Robinhood) | ✅ LOLOS Tier 1 | $8.011.325, 5 venue |
| 2 | NVDA (Robinhood) | ✅ LOLOS Tier 1 | $7.163.296, 4 venue |
| 3 | TSLA (Robinhood) | ✅ LOLOS Tier 1 | $2.256.273, 2 venue |
| 4–13 | (JPM/V/PYPL/MCD/DIS/UBER/GDX/BMNR + Ondo 15 token di Robinhood Chain) | ⏳ perlu cek per ticker | Delapan ticker baru 28 Okt 2026 (AltcoinBuzz, report.md §6); Ondo menambah 15 saham/ETF di chain ini — ticker + alamat dari yTokenize/DexScreener |

### 6d. Yang TIDAK direkomendasikan (dari verifikasi ini)
- **Ethereum + Ondo (TSLAon/NVDAon/SPYon/AAPLON):** gagal — venue ke-2
  (`communityV3`) tidak terverifikasi sebagai DEX independen; NVDAon/SPYon/
  AAPLON juga gagal total likuiditas.
- **Elysium + xStocks:** belum aktif — 0 pool berlikuiditas.
- **Hyperliquid spot wrapped xStocks:** monitor saja — bukan kaki Radar
  (TSLAX/AAPLX tanpa ask; NVDAX/SPYX tipis).

---

## 7. Ringkasan vonis

| Kelompok | Vonis |
|---|---|
| Ethereum + Ondo (TSLAon) | **GAGAL** — total $6,96 jt tapi hanya 1 venue teridentifikasi (Uniswap ±$60rb); `communityV3` = klon factory Uniswap V3 anonim, UNVERIFIED sebagai DEX independen |
| Ethereum + Ondo (NVDAon/SPYon/AAPLON) | **GAGAL** — total $406rb / $112rb / $26rb < $500rb |
| Robinhood Chain (TSLA/NVDA/SPY) | **LOLOS Tier 1** — $2,26 jt / $7,16 jt / $8,01 jt, 2–5 venue |
| Hyperliquid spot (TSLAX/NVDAX/SPYX/AAPLX) | **MONITOR SAJA (terkonfirmasi)** — TSLAX/AAPLX tanpa ask; NVDAX/SPYX book nyata tapi tipis |
| Elysium + xStocks | **BELUM AKTIF** — 1 pair GOOGLx ditemukan tapi liq $0 |
| Base + Coinbase (NVDAc) | **LOLOS Tier 1** — $2,49 jt, 4 venue (verifikasi ulang) |
| BNB + bStocks (TSLAB) | **LOLOS Tier 1** — $1,92 jt, 3 venue (verifikasi ulang) |

**Ticker yang lolos dari verifikasi ini:** TSLA/NVDA/SPY (Robinhood Chain),
NVDAc (Base), TSLAB (BNB). Ditambah universe lama Solana xStocks (13 ticker)
yang tidak diuji ulang di sini kecuali TSLAx (sehat, §5c).

---

## 8. Skrip cek mingguan Elysium + proposal cron

Skrip: [`check_elysium_weekly.py`](./check_elysium_weekly.py) — read-only,
API publik DexScreener + Hyperliquid, tanpa kredensial, tanpa tulis DB.
Cek 13 simbol xStocks di Elysium + cross-check token-pairs TSLAx EVM +
book spot Hyperliquid @702/@703/@712/@713. Vonis: `belum aktif` /
`aktif — lolos aturan` / `aktif — belum lolos` (pair $0 tidak dihitung aktif).
Exit 0 bila cek berjalan (apa pun vonisnya), 2 bila ambil data gagal.

**Uji coba 12 Nov 2026 12:29 UTC (20:29 WITA), exit 0:**
```
Cek mingguan Elysium + xStocks — 2026-11-12 12:29 UTC
Elysium: 1 pair xStocks (0 berlikuiditas), total likuiditas $0, venue: 0 -
  GOOGLx: 1 pair, $0
Pool terbesar: GOOGLx di uniswap (0x012b0cbd305f5c76a653a3c69ebcf988913f7c1f8368cfce2cd1cd5a4382d624) liq $0 vol24 $1,050
Cross-check token-pairs TSLAx EVM: 0 pair di Elysium
Hyperliquid spot (wrapped xStocks, konteks saja — bukan kaki Radar):
  @702 NVDAX: bid terbaik 160.37, ask terbaik 160.61
  @703 SPYX: bid terbaik 762.04, ask terbaik 764.29
  @712 TSLAX: bid terbaik 256.0, ask terbaik - (TIDAK ADA ASK)
  @713 AAPLX: bid terbaik 10.0, ask terbaik - (TIDAK ADA ASK)
VONIS: belum aktif
```

**Proposal cron (BELUM dibuat — butuh ACC Septian):** Minggu **09:46 WITA**,
bareng kabar berkala Radar. Perintah:
`python3 ~/workspace/radar-tokenized-stocks/check_elysium_weekly.py`
— output dibaca, bila vonis berubah dari `belum aktif` → kabari Septian
(vonis `aktif — lolos aturan` = sinyal untuk evaluasi integrasi Elysium;
`aktif — belum lolos` = pantau terus). Tidak ada tulis DB, tidak ada
kredensial, jadi cron ini aman dari sisi biaya/kuota (DexScreener ±27
request/menit, jauh di bawah batas 300/menit).

---

## 9. Yang tidak bisa diverifikasi / catatan

- Identitas deployer factory `0x00a38533…` (EOA `0xa534276a…`): tidak ada
  label Etherscan/Blockscout yang bisa dibaca tanpa API key; tidak dicoba
  lebih jauh — status UNVERIFIED sudah cukup untuk vonis.
- Apakah ada router/frontend yang mengarah ke factory `0x00a38533…`:
  tidak ditemukan lewat pencarian web; bila suatu hari ada frontend bernama
  yang terbukti memakai factory ini, vonis TSLAon bisa ditinjau ulang.
- Per-ticker pool liq untuk 10 token Coinbase lain dan bStocks di luar
  TSLAB: belum dicek (butuh enumerasi + 1 search DexScreener per ticker).
- Lisensi: DexScreener melarang resale/redistribusi dan produk kompetitor
  (report.md §7b) — tetap berlaku bila data ini ditampilkan/disimpan di
  Radar publik; cek lisensi sebelum dipakai di permukaan publik.
