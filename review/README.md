# Paket Review DeepSeek — Penambahan Radar Tokenized Stocks (12 Nov 2026)

**Status paket:** SIAP DIKIRIM — tetapi **JANGAN dijalankan dulu.**
Paket ini hanya disiapkan. Pengiriman ke DeepSeek (via Kelontong AI) dilakukan
nanti, **hanya atas perintah eksplisit Septian** (koin Kelontong hemat).
Disusun 12 Nov 2026 ±21:05 WITA oleh penyusun paket (subagent), tanpa
memanggil API AI apa pun dan tanpa mengubah satu baris kode pun di luar
folder `review/` ini.

**Repo:** `~/workspace/radar-tokenized-stocks`
**Cakupan review:** penambahan 12 Nov 2026 — 5 fitur (F1–F5) + multichain
(Base/Coinbase, BNB/bStocks, Robinhood Chain) + penjelasan web + testing.
**Bukan cakupan:** fitur MVP lama yang sudah live (kecuali bila penambahan
ini merusaknya — regresi tetap temuan yang sah).

---

## 1. Isi paket (6 file)

| File | Isi |
|---|---|
| `README.md` (file ini) | Cara menjalankan review + aturan arbiter + format output |
| `DESAIN_RINGKAS.md` | Ringkasan desain: 5 fitur, threshold pre-registered, skema baru |
| `DIFF_RINGKAS.md` | Daftar file berubah (git diff) + ringkasan per file + file kunci + penyimpangan dari desain yang sudah terlihat |
| `HASIL_TEST.md` | Backtest, forward test (belum tersedia), QA, angka Turso sebelum/sesudah |
| `PERTANYAAN_TERBUKA.md` | Daftar pertanyaan terbuka yang wajib dijawab reviewer |
| `CHECKLIST_QA.md` | Checklist yang harus lolos sebelum deploy |

---

## 2. Input yang harus dibaca reviewer (urut baca yang disarankan)

1. `DESAIN_RINGKAS.md` + `DIFF_RINGKAS.md` (paket ini) — peta jalan.
2. Dokumen sumber di repo (baca penuh, bukan ringkasan):
   - `DESAIN_PENAMBAHAN_2026-11-12.md` — desain lengkap + semua ambang pre-registered
   - `BACKTEST_ALERT_2026-11-12.md` — backtest alert + caveat
   - `VERIFIKASI_MULTICHAIN_2026-11-12.md` — verifikasi live multichain + vonis per issuer
   - `KUOTA_PENAMBAHAN_2026-11-12.md` — anggaran kuota Turso per skenario
   - `SEED_MULTICHAIN_2026-11-12.md` — hasil seed dry-run + temuan metode
3. Kode (file kunci — lihat `DIFF_RINGKAS.md` §3):
   `poller.py`, `schema.sql`, `migrations/2026-11-12-penambahan.sql`,
   `seed_multichain.py`, `verify_multichain.py` (di disk, git-ignored),
   `dashboard/risk.py`, `dashboard/logic.py`, `dashboard/turso_read.py`,
   `dashboard/app.py`, `api/worker.js`, `web/src/app/ticker/[id]/page.tsx`,
   `web/src/app/HomeClient.tsx`, `web/src/lib/api.ts`, `web/src/lib/risk.ts`.
4. `HASIL_TEST.md` + `PERTANYAAN_TERBUKA.md` (paket ini) — bukti uji + pertanyaan.
5. Referensi bila perlu (di luar paket, jangan dibaca bila tidak perlu):
   `~/workspace/research_notes/radar-rwa-flagship-20261024/DESAIN_TEKNIS_TAHAP1_DRAF.md`
   (desain awal §1.1, §2.2, §5.3–§5.4, §6.4, §11) dan
   `~/workspace/research_notes/radar-tokenized-chains-dex-20261112-1139/report.md`
   (riset multi-chain 12 Nov 2026).

**Catatan sumber data:** semua angka likuiditas/harga di dokumen sumber
adalah potret live 12 Nov 2026 (±20:24–21:00 WITA) dari API publik gratis
(DexScreener, Hyperliquid). Angka bergerak — reviewer TIDAK perlu
memverifikasi ulang angka live kecuali untuk menilai vonis yang bergantung
padanya (mis. TSLAon, CRCLc — lihat `PERTANYAAN_TERBUKA.md`).

---

## 3. Output yang diharapkan dari DeepSeek

Mengikuti pola review DeepSeek sebelumnya (MLF/Learn): temuan per kategori,
skor, dan klasifikasi tingkat. Format yang diminta:

### 3.1 Skor keseluruhan (1–10) + vonis satu baris
Skor untuk **penambahan ini sebagai satu paket** (bukan per file), plus vonis:
`APPROVE` / `APPROVE-WITH-FIXES` / `REVISE` (tolak sampai diperbaiki).
Beri skor terpisah per area bila berguna: (a) kebenaran rumus & ambang,
(b) skema & migrasi, (c) kuota & performa, (d) kejujuran web/banner,
(e) testing & bukti.

### 3.2 Temuan per kategori
Tiap temuan WAJIB berisi:
- **ID** (mis. `M1`, `S1`, `N1` — lanjutkan penomoran dari 1),
- **Kategori:** rumus/ambang · skema/migrasi · kuota/reads · keamanan data
  (fabrikasi/NULL) · bahasa/UX · testing/bukti · lisensi · inkonsistensi
  desain-vs-kode,
- **Tingkat:** `MUST-FIX` (salah secara faktual / membahayakan data /
  melanggar aturan standing — wajib diperbaiki sebelum deploy),
  `SHOULD-FIX` (lemah tapi tidak fatal — perbaiki di ronde fix yang sama
  bila terverifikasi), `NIT` (kecil: penamaan, teks, kerapian),
- **Bukti:** kutip file + baris/angka yang tepat (bukan kesan umum).
  Bila temuan berupa angka, tunjukkan hitung ulangnya.
- **Perbaikan yang diusulkan:** konkret (rumus/angka/teks pengganti),
  bukan "perlu ditinjau".

### 3.3 Hal yang secara eksplisit diminta diperiksa
1. **Rumus §2.2–§2.3 desain** — apakah bobot Exit Score (30+25+20+15+10)
   dan confidence Monday Gap (30+25+20+25) masuk akal? Apakah normalisasi
   parsialnya jujur (skor parsial tidak disamarkan sebagai skor penuh)?
   Apakah komponen funding memakai satuan yang benar (lihat
   `PERTANYAAN_TERBUKA.md` Q1)?
2. **Ambang §2.4 desain** — apakah 120/600 detik dan 1%/3% tepat untuk
   oracle Hyperliquid, mengingat `oracle_lag_s` ternyata TIDAK bisa diukur
   dari endpoint publik (lihat `DIFF_RINGKAS.md` §4, penyimpangan D1)?
3. **Estimasi kuota §6 desain vs `KUOTA_PENAMBAHAN_2026-11-12.md` vs
   `SEED_MULTICHAIN_2026-11-12.md` §4** — apakah pengali indeks dan
   hitungan pool baru realistis? Mana dari ketiga angka itu yang benar
   (lihat `PERTANYAAN_TERBUKA.md` Q5)?
4. **Skema & migrasi** — apakah migrasi idempotent? Apakah urutan
   migrasi-dulu-baru-poller dihormati? Apakah ada kolom yang ditulis
   tanpa sumber (fabrikasi)?
5. **Kejujuran tampilan** — apakah banner cakupan, label "eksperimental",
   dan klaim metodologi di web/dashboard jujur terhadap status nyata
   (mis. hanya Solana yang live; Base/BNB/Robinhood belum di-seed)?
6. **Testing** — apakah backtest membuktikan apa yang diklaimnya
   (lihat caveat di `HASIL_TEST.md`)? Apakah forward test dirancang
   cukup untuk menguji kaki yang belum teruji (akhir pekan, perp)?
7. **Jawaban atas semua pertanyaan di `PERTANYAAN_TERBUKA.md`** — satu
   per satu, dengan vonis (terjawab / tidak bisa dijawab dari data ini /
   butuh verifikasi live).

### 3.4 Yang TIDAK diminta
- Jangan mengusulkan perubahan ambang lama (§2 desain: alert 1,0%,
  pool ≥ $100rb, universe ≥ $500rb + ≥ 2 venue) — ambang lama TIDAK
  berubah; usulan perubahan ambang hanya dicatat sebagai observasi,
  bukan must-fix.
- Jangan mengusulkan fitur baru di luar 5 fitur + multichain ini.
- Jangan menulis kode. Reviewer hanya menilai; perbaikan dikerjakan
  Chief (induk) setelah verifikasi.

---

## 4. Aturan arbiter — BACA INI DULU

**Chief (induk) adalah arbiter akhir.** Keputusan Septian 12 Nov 2026
20:24 WITA (aturan standing): temuan review DeepSeek adalah **USULAN,
bukan perintah**. Hanya temuan yang **terverifikasi ke sumber** (hitung
ulang dari data/notebook, grep, baca file, cek live) yang masuk fix;
temuan yang salah/noise dicatat sebagai noise dan **TIDAK diperbaiki**.

Aturan turunan untuk ronde fix (standing rule MLF/Learn):
- Setiap temuan terverifikasi yang string-lockable → fixture guard QA
  di ronde fix yang sama.
- Setiap temuan terverifikasi yang semantik → kelas review di ronde fix.
- Tidak ada penghapusan course/lesson/fitur yang sudah ada — hanya
  Septian yang boleh memerintahkan penghapusan.

Reviewer (DeepSeek) TIDAK perlu tahu atau menilai aturan ini — ini
catatan proses untuk Chief. Dicantumkan di sini supaya paket ini
self-contained dan tidak ada yang salah paham soal siapa memutuskan.

---

## 5. Cara mengirim (nanti, atas perintah Septian)

1. Septian memberi perintah kirim (ACC) — **tanpa itu, paket ini diam
   di folder `review/`**.
2. Chief mengirim isi paket (6 file ini + file sumber yang dirujuk)
   ke DeepSeek via Kelontong AI, dengan instruksi output §3 di atas.
3. Hasil review kembali ke Chief → Chief verifikasi tiap temuan ke
   sumber → fix terverifikasi → QA guard → deploy (butuh ACC deploy
   tersendiri dari Septian).
4. Biaya: review DeepSeek via Kelontong — pakai pola hemat yang sama
   seperti review MLF (satu pengiriman, bukan bolak-balik).

**Larangan:** jangan jalankan Kelontong/DeepSeek dari paket ini sendiri;
jangan deploy apa pun; jangan menulis ke Turso live; jangan ubah file
di luar folder `review/`.
