# Evaluasi Radar pasca-testing-week (2–8 Nov 2026)

**Tanggal laporan:** 8 Nov 2026, ~03:05 WITA (Septian tidur; hasil untuk pagi).
**Ruang lingkup:** analisis + laporan saja. Tidak ada kode, ambang, jadwal, atau
keputusan yang diubah. Semua angka di bawah ini dibaca dari sumber (log, DB,
API, halaman publik), bukan ditebak.

## Ringkasan eksekutif

**Verdict: TEKNIS LULUS, KOMERSIAL NOL.**

| Dimensi | Hasil |
|---|---|
| QA harian post-fix | **7/7 PASS** (10/10 checks tiap hari) |
| Burn Turso | **OK** — 43,6 jt reads (8,7% dari 500 jt), proyeksi ~193 jt/bln |
| Poller + API + dashboard | Sehat (data segar 1–5 mnt, 35/35 pool, dashboard 200) |
| Alert bot | Jalan benar; 83 alert tercatat sepanjang sejarah (52 redemption, 30 spread, 1 batch) |
| Insiden Hrana 000 | 3 kejadian total (maks 1/hari), tidak ada sejak 7 Nov 19:56 |
| Pengguna Telegram | **2 anggota/kanal** (bot + pemilik; 0 pengguna eksternal terukur) |
| Waitlist | **0 pendaftar** |
| Pengumuman | Masih DITAHAN (belum ada ke pengguna lain) |

Sistemnya bekerja. Yang belum ada adalah **pengguna**. Gerbang A1 (19 Des 2026)
mensyaratkan ≥200 pengguna TG aktif — dari 0 pengguna eksternal hari ini,
itu berarti ~200 pengguna dalam 6 minggu tanpa satu pun kanal distribusi yang
jalan. Itulah keputusan terbesar yang menunggu Septian, bukan perbaikan teknis.

**Satu koreksi penting atas catatan sebelumnya:** pengiriman 13 alert redemption
7 Nov 13:36 dalam "format lama" **BUKAN anomali dan BUKAN bug**. Format itu
benar untuk tipe alert-nya (penjelasan lengkap di §3.2). Laporan anomali
closewave yang masih PENDING ke Septian sebaiknya TIDAK dikirim dalam bentuk
semula — yang benar adalah koreksi ini.

---

## 1. QA harian post-fix: 7/7 PASS

`qa_post_fix.py` (10 checks: universe 13 ticker, 35 pool aktif, snapshot &
deviasi segar <20 mnt, poller cycle OK, API 200 + 13 ticker + field valid +
ts segar, bot --once rc=0).

| Hari | Tanggal | Hasil |
|---|---|---|
| 1–4 | 2–5 Nov | PASS — periode QA 2–5 Nov dinyatakan SELESAI 5 Nov (FINAL, 10/10) |
| 5/7 | 6 Nov 11:46 | PASS 10/10 (data umur 5,1 mnt) |
| 6/7 | 7 Nov 11:46 | PASS 10/10 (data umur 0,8 mnt) |
| 7/7 | 8 Nov **02:57** | **PASS 10/10** (data umur 1,2 mnt, ts 2026-11-07T18:56:00Z) |

Catatan jujur: run hari ke-7 di atas adalah run yang saya lakukan sendiri
pukul 02:57 WITA untuk evaluasi ini — slot terjadwal harian (11:46 WITA)
belum tiba saat laporan ditulis. Isinya sama persis dengan run terjadwal
(`qa_post_fix.py`, exit 0). JSON lengkap:

```json
{"verdict": "PASS", "checked_at_utc": "2026-11-07T18:57:13.247940+00:00",
 "results": [
  {"name": "universe_13_tickers", "ok": true, "detail": "n=13"},
  {"name": "active_pools_35", "ok": true, "detail": "n=35"},
  {"name": "snapshots_fresh_lt20m", "ok": true, "detail": "age=1.2m ts=2026-11-07T18:56:00Z"},
  {"name": "deviations_fresh_lt20m", "ok": true, "detail": "age=1.2m ts=2026-11-07T18:56:00Z"},
  {"name": "poller_last_cycle_ok", "ok": true, "detail": "cycles_ok=1 age=1.2m"},
  {"name": "api_200", "ok": true, "detail": "http=200"},
  {"name": "api_13_tickers", "ok": true, "detail": "n=13"},
  {"name": "api_fields_valid", "ok": true, "detail": "dev_bps+ticker present"},
  {"name": "api_latest_ts_fresh", "ok": true, "detail": "age=1.2m"},
  {"name": "bot_once_no_eval_error", "ok": true, "detail": "rc=0"}]}
```

Tidak ada satu pun hari yang FAIL selama minggu testing. Optimasi burn
pasca-insiden 30 Okt terbukti aman: tidak ada data hilang, web + alert jalan
normal 7 hari berturut-turut.

---

## 2. Burn Turso: OK, jauh dari ambang

Dibaca segar via `turso_usage_check.py` (Platform API `api.turso.tech`,
angka yang sama dengan dashboard) pada **8 Nov 02:55 WITA**:

| Metrik | Nilai |
|---|---|
| Rows read kumulatif | **43.631.847 (8,7% dari limit 500 jt)** |
| Rows written | 484.437 (4,8% dari 10 jt) |
| Storage | 55,4 MB |
| Laju saat ini | 560 reads/mnt |
| Proyeksi bulanan | **~192,8 jt (kumulatif) / ~24,2 jt (basis laju)** |
| Verdict | **OK** |

Tren (dari `usage-api-log.md`): 28,7 jt (3 Nov) → 39,8 jt (4 Nov) → 41,5 jt
(5 Nov) → 42,5 jt (6 Nov) → 43,1 jt (7 Nov) → 43,6 jt (8 Nov). Laju harian
kini ~0,5–0,9 jt reads/hari — jauh di bawah laju pra-insiden. Ambang WARN
(>400 jt) dan DANGER (>450 jt) tidak terancam di bulan ini dengan pola pakai
saat ini.

Catatan housekeeping: `burn-log.md` (format lama) terakhir diisi 3 Nov dan
sudah tidak dipakai — monitor harian kini mencatat ke `usage-api-log.md`
(termasuk entri 8 Nov 02:55 dari run saya). Sebaiknya salah satu dipensiunkan
supaya tidak ada dua sumber yang membingungkan; bukan blocker.

---

## 3. Alert bot

### 3.1 Riwayat pengiriman (dari `alert_log`, dibaca langsung dari DB)

| Tanggal | Jenis | Jumlah |
|---|---|---|
| 26 Okt | redemption 13, spread 2 | 15 |
| 27 Okt | spread 1 | 1 |
| 28 Okt | spread 2 | 2 |
| 29 Okt | spread 3 | 3 |
| 1 Nov | redemption 13 | 13 |
| 2 Nov | spread 3 | 3 |
| 3 Nov | spread 1 | 1 |
| 4 Nov | spread 8 | 8 |
| 5 Nov | spread 7 | 7 |
| 6 Nov | spread 3 | 3 |
| 7 Nov | **redemption 13** | 13 |
| **Total sepanjang sejarah** | **redemption 52, spread 30, redemption_batch 1** | **83** |

Tidak pernah ada alert `deviation_high`, `por` (PoR basi), atau
`redemption_paused` — ambang-ambang itu belum pernah terpicu.

Semua pass bot 8 Nov 00:01–02:57 WITA: exit 0, **0 alert terkirim**,
0 error (18 entri "alerts sent: 0" di log harian; run QA saya 02:57 juga
rc=0). Sesuai aturan: diam bila 0 alert.

### 3.2 Closewave 7 Nov 13:36 — yang sebenarnya terjadi (KOREKSI)

Fakta dari DB (`redemption_windows` + `alert_log`):

- Jendela redemption **terbuka** 6 Nov 20:16 UTC s.d. 7 Nov 04:33 UTC.
- Berubah menjadi **tertutup** pada **7 Nov 05:31 UTC (13:31 WITA)** —
  penutupan akhir pekan yang terjadwal.
- Alert terkirim **05:36:31 UTC (13:36 WITA)**, 5 menit setelah jendela
  tutup yang baru dimulai — tepat sesuai aturan dedup B ("sekali per
  jendela tutup", ACC 25 Okt): alert pertama dari jendela yang baru.
- Bukan penutupan baru dari issuer, bukan re-fire, bukan kedaluwarsa
  dedup 24 jam. Pass 06:56 WITA yang "ter-suppress" terjadi saat jendela
  masih TERBUKA (belum ada jendela tutup yang hidup) — bukan karena dedup.

**Soal format — tidak ada anomali.** Kode `bot.py` punya DUA tipe alert
redemption yang berbeda:

| Tipe | Pemicu | Header yang dipakai kode |
|---|---|---|
| `redemption` | jendela tutup terjadwal (status closed/gated) | 🟡 `REDEMPTION — {ticker}` |
| `redemption_paused` | jeda on-chain terdeteksi (flag pausable mint) | 🔴 `REDEMPTION PAUSED / DIJEDA — {ticker}` |

13 alert 13:36 bertipe `redemption` → header 🟡 adalah **format yang benar
menurut kode**. Header 🔴 hanya untuk tipe `redemption_paused`, yang
**belum pernah sekalipun terpicu (0 baris di `alert_log`)** karena tidak
pernah ada jeda on-chain yang terdeteksi. Jadi format baru itu belum
terverifikasi live — bukan karena bug, melainkan karena kondisi pemicunya
belum pernah terjadi.

Satu lagi: di dalam kode pun **tidak ada format "2-baris"**. `format_alert`
menyusun pesan yang sama untuk kedua tipe (header + body multi-baris +
tautan ticker + disclaimer); tipe paused hanya menambah satu baris prioritas
di atas body. Ekspektasi "format baru 2-baris" tidak cocok dengan kode yang
ada. Bila Septian menginginkan pesan yang benar-benar 2 baris, itu adalah
perubahan desain baru, bukan verifikasi atas yang sudah dibangun.

**Implikasi:** laporan anomali closewave yang masih PENDING jangan dikirim
apa adanya. Yang perlu disampaikan ke Septian adalah koreksi ini: tidak ada
yang salah pada 13:36; yang belum teruji adalah jalur `redemption_paused`,
dan ia hanya akan teruji bila suatu hari ada jeda on-chain sungguhan (atau
diuji dengan simulasi — yang butuh keputusan terpisah, bukan dijalankan
diam-diam).

### 3.3 Observasi: spread alert masih bisa terpicu tick buruk

- Alert spread terakhir: 6 Nov 19:11 UTC (NVDAx 4,426%). Termasuk di
  antaranya **SPYx 100,041% pada 6 Nov 19:06 UTC** — nilai yang secara
  jelas berasal dari tick buruk satu pool.
- Pada siklus yang sama, poller mencatat `guard=SPYx:1` — price-sanity
  guard (sejak 24 Okt) sudah mengecualikan 1 pool SPYx yang buruk dari
  harga tertimbang-kedalaman.
- Artinya: guard melindungi harga/deviasi yang ditampilkan, tetapi
  **evaluasi spread (hi/lo venue) masih memakai harga mentah** sehingga
  tick buruk tetap bisa memicu alert spread. Ini bukan insiden (alert
  terkirim, tidak ada yang rusak), tetapi kandidat perbaikan sebelum
  pengumuman: evaluasi spread sebaiknya memakai harga yang sudah
  di-guard, atau diberi sanity-cap. Perlu keputusan Septian (perubahan
  logika alert = perubahan ambang/semantik).

---

## 4. Insiden Hrana HTTP 000

| Kejadian | Sub-sistem | Dampak |
|---|---|---|
| 2 Nov ~19:41 UTC | poller (`poller-cron.log`) | 1×, siklus berikutnya normal |
| 3 Nov ~14:55 UTC | poller | 1×, siklus berikutnya normal |
| **7 Nov 19:56 WITA** | **bot alerts pass** | 1×, 8 pass berikutnya (20:01–20:36) normal |

Total 3 kejadian, **maksimal 1 per hari** — ambang eskalasi (3+ kali/hari)
tidak pernah tercapai. Tidak ada kejadian sejak 7 Nov 19:56: semua pass bot
8 Nov 00:01–02:57 normal (rc=0), poller cycle terakhir 18:51 UTC 7 Nov OK,
dan `grep` seluruh log tidak menemukan `Hrana HTTP 000` lain.

Kesimpulan investigasi 7 Nov tetap berlaku: 000 = klien Hrana gagal membuka
koneksi HTTP ke endpoint Turso (tanpa respons sama sekali) — blip sesaat
jalur jaringan/proxy egress, bukan kuota, bukan token, bukan restart VM,
bukan perubahan kode. Dampak nol (tidak ada alert hilang; 13 redemption
sudah terkirim 13:36). Tidak ada perbaikan kode yang dibutuhkan; job
self-heal lewat retry otomatis pass berikutnya.

---

## 5. Pengguna, retensi, dan traksi komersial

Diukur langsung, 8 Nov ~03:00 WITA:

| Metrik | Nilai | Sumber |
|---|---|---|
| Anggota kanal EN (`t.me/exitradar_en`, -1003867845895) | **2** | `getChatMemberCount` via Bot API |
| Anggota kanal ID (`t.me/exitradar_in`, -1004471605253) | **2** | `getChatMemberCount` via Bot API |
| Pendaftar waitlist | **0** | tabel `waitlist` di Turso (0 baris) |
| Pernyataan "akan bayar" | **0** (tidak ada bukti di log/DB manapun) | — |
| Calon B2B | **0** (tidak ada bukti di log/DB manapun) | — |
| Pengumuman ke publik | **DITAHAN** (belum pernah) | keputusan Septian |

Angka "2" hampir pasti = bot itu sendiri + pemilik. Artinya **tidak ada
satu pun pengguna eksternal yang terukur** — bukan hanya di bawah target,
melainkan nol. Halaman publik `t.me/exitradar_en` / `_in` bisa dibuka
(deskripsi + tautan dashboard tampil), tetapi tidak menampilkan jumlah
subscriber; angka di atas berasal dari Bot API, bukan dari halaman.

Konteks: Septian sendiri sudah menyatakan 8 Nov 01:36, "Radar aja belum
beres, kita blum bsa ksih ke user lain" — selaras dengan temuan ini. Sistem
siap secara teknis; yang belum siap adalah distribusi.

---

## 6. Tinjauan Minggu 4 (~21 Nov) dan G0 Tahap 2 (~23 Nov)

### 6.1 Yang tertulis vs yang tidak

- **Gerbang A1 (19 Des 2026) TERTULIS:** jangkar 24 Okt 2026 (snapshot
  pertama poller), evaluasi akhir Minggu ke-8. Kriteria yang tercatat di
  catatan induk: ≥200 pelanggan TG aktif, retensi 30 hari ≥30%, ≥10
  pernyataan akan bayar, ≥1 calon B2B; nol = pivot/berhenti.
  **Peringatan jujur:** saya grep seluruh repo Radar + folder goal dan
  TIDAK menemukan dokumen yang menuliskan angka-angka kriteria A1 ini —
  sumbernya hanya catatan induk. Mohon Septian konfirmasi angkanya sebelum
  dipakai sebagai gerbang resmi.
- **"G0 Tahap 2" TIDAK PUNYA definisi tertulis.** Grep `G0` di semua
  dokumen Radar menghasilkan NOL. "Tahap 2" yang muncul di dokumen adalah
  fase build dashboard (sudah live) — bukan gerbang. Label "G0 Tahap 2"
  berasal dari catatan induk sendiri. **Saya tidak mengarang definisinya.**

### 6.2 Opsi definisi G0 untuk diputuskan Septian

G0 paling masuk akal dibaca sebagai **"GO untuk Tahap 2 (pengumuman +
akuisisi pengguna)"** — kebalikan dari pivot/berhenti. Tiga opsi kriteria:

| Opsi | Isi | Konsekuensi |
|---|---|---|
| **A — GO teknis saja** | QA 7/7 PASS + burn OK + tidak ada insiden P1 selama testing week | G0 hampir pasti lolos (semua sudah terpenuhi hari ini). Tahap 2 = umumkan + cari pengguna. Risiko: mengumumkan produk yang belum teruji format `redemption_paused` dan spread-alert bad-tick (§3.3). |
| **B — GO + bukti permintaan** | A + minimal 1 sinyal permintaan nyata (mis. ≥10 pendaftar waitlist, atau ≥5 pengguna TG eksternal dari lingkaran dekat) | Butuh aksi distribusi kecil dulu (bukan pengumuman massal). Paling seimbang: membuktikan ada yang mau, sebelum menghabiskan kredibilitas pengumuman. |
| **C — GO = A1 mini** | A + ambang traksi parsial menuju A1 (mis. ≥50 pengguna aktif) | Paling ketat; praktis menunda Tahap 2 sampai ada traksi — tapi traksi tidak akan datang tanpa pengumuman. Berisiko deadlock. |

Rekomendasi saya (bukan keputusan): **opsi B**. Opsi A terlalu longgar
untuk produk yang alertnya belum pernah dilihat pengguna sungguhan; opsi C
menjebak diri sendiri.

### 6.3 Isi tinjauan Minggu 4 (~21 Nov)

Checkpoint 4 minggu setelah minggu testing. Yang sebaiknya dinilai saat itu
(bila Tahap 2 jalan): jumlah pengguna TG eksternal, retensi, feedback
pengguna atas alert yang benar-benar diterima (termasuk apakah ada yang
menerima `redemption_paused` / spread alert), burn Turso bulanan, dan
apakah ada pernyataan akan bayar / calon B2B. Bila Tahap 2 belum jalan
sampai 21 Nov, tinjauan itu hanya akan mengulang angka hari ini (0
pengguna) — jadi tanggal 21 Nov hanya bermakna bila ada aksi distribusi
di antaranya.

---

## 7. Rekomendasi (prioritas)

1. **Putuskan pengumuman / distribusi — ini blocker sebenarnya.**
   Teknis sudah lulus 7/7; tanpa pengguna, evaluasi A1 19 Des tidak punya
   bahan. Opsi B (§6.2) sebagai jalan tengah: uji permintaan kecil dulu
   (lingkaran dekat / waitlist) sebelum pengumuman massal.
2. **Sampaikan koreksi format closewave ke Septian** (bukan laporan
   anomali): 13:36 benar; `redemption_paused` belum pernah terpicu;
   tidak ada format 2-baris di kode. Ini menutup item PENDING sejak
   7 Nov 14:19.
3. **Perbaiki spread-alert bad-tick (§3.3)** sebelum pengumuman —
   evaluasi spread memakai harga yang sudah di-guard (butuh ACC Septian
   karena ini perubahan logika alert).
4. **Tetapkan definisi G0 + konfirmasi angka A1** bersama Septian
   sebelum 23 Nov; jangan biarkan gerbang diputuskan dari catatan yang
   tidak terdokumentasi.
5. **Lanjutkan monitoring apa adanya:** QA harian + burn 10:00 + bot
   /5 mnt. Tidak ada yang perlu diubah dari cadence ini. Jadwalkan
   run QA 11:46 hari ini (8 Nov) tetap jalan sebagai penutup formal
   minggu testing, meski run evaluasi 02:57 sudah PASS.
6. **Housekeeping kecil:** pensiunkan `burn-log.md` (terakhir 3 Nov)
   karena monitor kini mencatat ke `usage-api-log.md`.

Yang TIDAK saya rekomendasikan: pivot atau berhenti. Tidak ada bukti
produknya rusak — yang belum terbukti adalah ada orang yang menginginkannya,
dan itu hanya bisa dijawab dengan mengumumkannya.

---

## 8. Batasan & sumber

- QA hari ke-7/7 saya jalankan pukul 02:57 WITA (bukan slot terjadwal
  11:46) — hasilnya PASS dan metodenya identik, tetapi penutup formal
  minggu testing tetap run 11:46 hari ini.
- Kriteria A1 (200 pengguna, retensi 30%, 10 will-pay, 1 B2B) tidak
  ditemukan dokumennya di repo — dikutip dari catatan induk, perlu
  konfirmasi Septian.
- Jumlah anggota Telegram via `getChatMemberCount` (Bot API, token vault
  `custom.radar-telegram`, tidak pernah dicetak). Angka 2/kanal hampir
  pasti termasuk bot + pemilik; tidak ada cara membedakan tanpa daftar
  anggota (bot tidak bisa melihat daftar itu).
- Halaman `t.me/exitradar_en` / `_in` tidak menampilkan jumlah subscriber
  pada teks yang bisa diambil.
- Tidak ada `deviation_high` / `por` / `redemption_paused` yang pernah
  terpicu — ambang-ambang itu belum teruji live sama sekali.
- Sumber: `logs/poller-cron.log`, `qa_post_fix.py` (run 8 Nov 02:57,
  exit 0), `turso_usage_check.py` (run 8 Nov 02:55), `bot.py`
  (format_alert, dedup rule B), `alert_log` + `redemption_windows` +
  `waitlist` (query langsung Turso), `api.omdanny.site/api/health`,
  `radar.omdanny.site` (200), `~/memory/2026-11-07.md` (QA hari 5–6,
  investigasi Hrana), `~/memory/2026-11-08.md` (pass bot 8 Nov),
  `BUILD_LOG.md` (jangkar A1 24 Okt).
