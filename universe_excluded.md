# Universe final Tahap 1 + daftar TIDAK TERCAPUP

Verifikasi likuiditas live via DexScreener search, Sabtu 24 Okt 2026 (pagi WITA). Kriteria mengikat desain §1.1: kedalaman gabungan >= $500.000 DAN >= 2 venue DEX. Tier 1 (§1.3): >= $1 jt + volume harian di >= 2 venue. Ambang TIDAK diturunkan untuk mengejar 20.

## Universe final: 13 ticker (11 Tier 1 + 2 Tier 2)

- TSLAx — Tier 1, total $3,063,874, 4 venue, token XsDoVfqeBukx… (Solana)
- NVDAx — Tier 1, total $4,199,099, 4 venue, token Xsc9qvGR1efV… (Solana)
- AAPLx — Tier 2, total $665,905, 4 venue, token XsbEhLAtcf6H… (Solana)
- MSFTx — Tier 2, total $901,002, 3 venue, token XspzcW1PRtgf… (Solana)
- METAx — Tier 1, total $1,063,074, 3 venue, token Xsa62P5mvPsz… (Solana)
- GOOGLx — Tier 1, total $1,690,379, 4 venue, token XsCPL9dNWBMv… (Solana)
- MSTRx — Tier 1, total $1,959,249, 4 venue, token XsP7xzNPvEHS… (Solana)
- SPYx — Tier 1, total $5,150,913, 4 venue, token XsoCS1TfEyfF… (Solana)
- QQQx — Tier 1, total $2,461,435, 4 venue, token Xs8S1uUs1zvS… (Solana)
- CRCLx — Tier 1, total $6,169,210, 4 venue, token XsueG8BtpquV… (Solana)
- HOODx — Tier 1, total $1,380,597, 3 venue, token XsvNBAYkrDRN… (Solana)
- COINx — Tier 1, total $1,588,402, 4 venue, token Xs7ZdzSHLU9f… (Solana)
- GLDx — Tier 1, total $1,347,926, 3 venue, token Xsv9hRk1z5ys… (Solana)

## Tidak tercakup (30 kandidat diperiksa, gagal kriteria)

- AMZNx: $389,475, 3 venue — total liquidity $389,475 < $500,000
- NFLXx: $16,354, 1 venue — total liquidity $16,354 < $500,000; only 1 venue(s) with liquidity
- PLTRx: $304,595, 3 venue — total liquidity $304,595 < $500,000
- AMDx: $5,789, 3 venue — total liquidity $5,789 < $500,000
- AVGOx: $238,098, 3 venue — total liquidity $238,098 < $500,000
- JPMx: $2,457, 1 venue — total liquidity $2,457 < $500,000; only 1 venue(s) with liquidity
- BABAx: $0, 0 venue — no pairs with exact symbol
- TSLAon: $8,464,016, 1 venue — only 1 venue(s) with liquidity
- NVDAon: $12,304,168, 1 venue — only 1 venue(s) with liquidity
- SPYon: $23,836,489, 1 venue — only 1 venue(s) with liquidity
- LLYx: $5,937, 1 venue — total liquidity $5,937 < $500,000; only 1 venue(s) with liquidity
- UNHx: $13,025, 2 venue — total liquidity $13,025 < $500,000
- COSTx: $0, 0 venue — no pairs with exact symbol
- WMTx: $9,179, 2 venue — total liquidity $9,179 < $500,000
- BACx: $0, 0 venue — no pairs with exact symbol
- XOMx: $23,940, 3 venue — total liquidity $23,940 < $500,000
- ABBVx: $0, 0 venue — no pairs with exact symbol
- CRMx: $248, 1 venue — total liquidity $248 < $500,000; only 1 venue(s) with liquidity
- QCOMx: $0, 0 venue — no pairs with exact symbol
- MUx: $1,987, 2 venue — total liquidity $1,987 < $500,000
- UBERx: $0, 0 venue — no pairs with exact symbol
- TSMx: $7,305, 1 venue — total liquidity $7,305 < $500,000; only 1 venue(s) with liquidity
- DIAx: $0, 0 venue — no pairs with exact symbol
- IWMx: $0, 0 venue — no pairs with exact symbol
- SPOTx: $0, 0 venue — no pairs with exact symbol
- SHOPx: $0, 0 venue — no pairs with exact symbol
- INTCx: $77,424, 1 venue — total liquidity $77,424 < $500,000; only 1 venue(s) with liquidity
- ARMx: $0, 0 venue — no pairs with exact symbol
- MRVLx: $1,275, 2 venue — total liquidity $1,275 < $500,000
- NVOx: $4,654, 1 venue — total liquidity $4,654 < $500,000; only 1 venue(s) with liquidity

## Catatan khusus

- Ondo (TSLAon/NVDAon/SPYon): likuiditas BESAR ($8,4–23,8 jt) tapi hanya 1 venue (Uniswap/Ethereum, quote WETH) — gagal kriteria >= 2 venue DEX. Berbeda dengan riset pagi (likuiditas DEX $0–9,9 rb): pool Uniswap ini tidak tertangkap riset pagi, tapi tetap gagal kriteria venue.
- TSLAx: pool Raydium terdalam $2.377.760 — cocok dengan bukti live riset pagi ($2,38 jt). Konfirmasi token kanonis kuat.
- Pool yang dilacak per ticker: hanya pair dengan likuiditas >= $100.000 (ambang §5.2) = 35 pool. Pair di bawah ambang TIDAK disimpan di snapshots (penyimpangan dari §5.2 yang tertulis 'tetap disimpan', demi anggaran tulis §2.2: ~200 pair akan menembus 10 jt writes/bln; 35 pool ≈ 2 jt writes/bln).
- Target 20–30 ticker TIDAK tercapai (13 lolos dari 43 kandidat). Sesuai §1.3, universe dimulai dari yang lolos saja; perluasan menunggu verifikasi berikutnya, bukan penurunan ambang.
