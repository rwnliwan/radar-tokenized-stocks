# Gerbang A1 & G0 Tahap 2 — Radar Tokenized Stocks

**Status: DITETAPKAN 8 Nov 2026** melalui vote 6 keputusan (Septian,
09:15 WITA): Q4 A (2–1, Kimi penentu) untuk angka A1, Q5 B (3–0 bulat)
untuk definisi G0. Tally suara:
`~/workspace/kelontong-review/reviews4/vote-6-tally.md` (di luar repo
ini). Evaluasi yang melandasi: `EVALUASI-TESTING-WEEK-2026-11-08.md`
(§5 pengguna, §6.1–6.2 A1/G0, §3.3 bad-tick).

## 1. Gerbang A1 — evaluasi akhir 19 Des 2026

Jangkar: snapshot pertama poller `2026-10-24T11:11:00Z` (= 19:11 WITA);
evaluasi akhir jatuh pada akhir Minggu ke-8 sejak tanggal itu
(`BUILD_LOG.md` § atas).

| # | Kriteria | Ambang |
|---|---|---|
| 1 | Pelanggan Telegram aktif | ≥ 200 |
| 2 | Retensi 30 hari | ≥ 30% |
| 3 | Pernyataan akan bayar (will-pay) | ≥ 10 |
| 4 | Calon B2B | ≥ 1 |

**Konsekuensi: nol di semua kriteria = pivot / berhenti.** Tidak ada
ambang parsial yang menyelamatkan — gerbang ini lolos-atau-gagal
sebagai satu paket pada 19 Des 2026.

### Catatan kejujuran (wajib dibaca)

Angka-angka di atas **sebelumnya hanya ada di catatan induk**.
Evaluasi 8 Nov 2026 (§6.1) menyatakan terus terang: grep seluruh repo
Radar + folder goal TIDAK menemukan satu pun dokumen yang menuliskan
kriteria A1 ini. Saya verifikasi ulang 8 Nov 2026 sebelum menulis
dokumen ini — grep `200 pelanggan`, `retensi 30`, `akan bayar`,
`calon B2B`, dan `G0` di semua `*.md` repo menghasilkan NOL di luar
file evaluasi itu sendiri (yang saat itu belum ter-commit). Angka ini
kini ditetapkan RESMI per vote Q4 A (8 Nov 2026) dan dokumen ini
adalah lokasi kanonisnya. Mengubah angka setelah tanggal ini tanpa
bukti baru = menggeser gawang (alasan suara A: jangkar 24 Okt;
deepseek memilih C — tunda penetapan sampai G0 memberi data — kalah
1–2).

### Baseline saat penetapan (8 Nov 2026, evaluasi §5)

| Metrik | Nilai |
|---|---|
| Anggota kanal Telegram EN / ID | 2 / 2 (bot + pemilik; 0 pengguna eksternal) |
| Pendaftar waitlist | 0 |
| Pernyataan akan bayar | 0 |
| Calon B2B | 0 |
| Pengumuman ke publik | DITAHAN (belum pernah) |

Dari 0 pengguna eksternal ke ≥200 dalam 6 minggu tanpa satu pun kanal
distribusi yang jalan — itulah keputusan terbesar yang menunggu, bukan
perbaikan teknis (evaluasi: TEKNIS LULUS 7/7 QA, KOMERSIAL NOL).

## 2. G0 Tahap 2 — GO + bukti permintaan minimal (opsi B)

**Definisi: GO untuk Tahap 2 (pengumuman + akuisisi pengguna), dengan
syarat bukti permintaan minimal TERPENUHI DULU — ≥10 pendaftar
waitlist ATAU ≥5 pengguna Telegram eksternal dari lingkaran dekat —
sebelum pengumuman massal. Target ~23 Nov 2026.**

Artinya: aksi distribusi kecil dulu (lingkaran dekat / waitlist),
bukan pengumuman massal langsung. Bukti permintaan minimal membuktikan
ada yang mau, sebelum kredibilitas pengumuman dihabiskan. Tinjauan
Minggu 4 (~21 Nov 2026) menilai: jumlah pengguna TG eksternal,
retensi, feedback atas alert yang benar-benar diterima, burn Turso
bulanan, dan ada/tidaknya pernyataan akan bayar / calon B2B. Bila
Tahap 2 belum jalan sampai 21 Nov, tinjauan itu hanya akan mengulang
angka 8 Nov (0 pengguna) — tanggal 21 Nov hanya bermakna bila ada
aksi distribusi di antaranya.

### Opsi yang ditolak

| Opsi | Isi | Alasan ditolak |
|---|---|---|
| **A — GO teknis saja** | QA 7/7 PASS + burn OK + tanpa insiden P1 selama testing week | Terlalu longgar untuk produk yang alertnya belum pernah dilihat pengguna sungguhan. Saat diputuskan, format `redemption_paused` (🔴) belum pernah terpicu live sehingga belum terverifikasi, dan spread-alert masih bisa terpicu tick buruk (§3.3 evaluasi). G0 hampir pasti lolos hari itu juga (semua syarat teknis sudah terpenuhi). |
| **C — GO = A1 mini** | Opsi B + ambang traksi parsial menuju A1 (mis. ≥50 pengguna aktif) | Menjebak deadlock: traksi tidak akan datang tanpa pengumuman, sementara pengumuman ditahan sampai ada traksi. Paling ketat, praktis menunda Tahap 2 sampai ada traksi yang tidak bisa muncul. |

## 3. Prasyarat teknis sebelum pengumuman (Q6 A, 3–0)

Perbaiki spread-alert bad-tick SEBELUM pengumuman — diputuskan
bersamaan dengan G0 (vote Q6 A, 3–0 bulat).

- **Status: SELESAI 8 Nov 2026.** `bot.py`: evaluasi spread kini
  memakai venue yang sudah lolos price-sanity guard
  (`guarded_venues()`, aturan sama dengan guard poller sejak 24 Okt:
  ≥3 pool → buang harga yang menyimpang >25% dari median
  lintas-pool). Ambang spread ≥1,0% / |dev| ≥3,0%, dedup 24 jam,
  stale gate 30 menit, dan format alert TIDAK berubah.
- **Bukti:** `qa/test_spread_guard.py` (18 checks, PASS) — fixture
  verbatim Turso 6 Nov: tick buruk SPYx $0,1044 (spread mentah
  100,047% ≈ 100,041% yang tercatat di `alert_log`) TIDAK lagi
  memicu alert (spread pasca-guard 0,168%); alert spread asli NVDAx
  4,426% (6 Nov 19:11 UTC) TETAP terpicu pada saat itu (4,424% dari
  fixture) — SEBELUM M2 (ronde 5). Pasca-M2 alert historis itu TIDAK
  lagi menyala (spread khusus-pool-lolos 0,325%); yang tetap menyala
  adalah fixture `NVDAX_QUAL` (4,424%) — lihat §4.
- **Masih belum terverifikasi live:** jalur `redemption_paused`
  (0 baris di `alert_log` sepanjang sejarah) — hanya akan teruji bila
  suatu hari ada jeda on-chain sungguhan, atau diuji dengan simulasi
  (butuh keputusan terpisah). Bukan blocker G0, tapi jangan klaim
  format 🔴 sudah teruji.

## 4. Kontrak freshness tunggal + populasi qualifying (fix ronde 5, 8 Nov 2026)

Review ronde 5 (Terra) menemukan tiga permukaan memakai definisi
berbeda untuk data "segar" dan venue "lolos". Sejak fix ini berlaku
SATU kontrak bersama — ambang TIDAK berubah (alert spread ≥1,0%,
|dev| ≥3,0%, dedup 24 jam, stale gate bot 30 menit, guard 25%).

### Freshness (umur + failed streak)
- Definisi: `last_success_ts` = cycle_ts baris `poller_health`
  terbaru dengan `cycles_ok = 1`; `age_min` = menit sejak
  `last_success_ts` (null bila belum pernah sukses);
  `failed_streak` = jumlah baris `cycles_ok = 0` berturut-turut dari
  yang terbaru; `stale` = `age_min` null ATAU `age_min > 15` ATAU
  `failed_streak >= 2`.
- Dipakai di: `dashboard/logic.py: freshness_status` (umur kini
  berjangkar sukses terakhir, bukan baris terbaru — baris gagal
  bertimestamp segar sebelumnya menyembunyikan umur data);
  `api/worker.js: healthSummary` → `/api/health` (field baru:
  `cycles_ok`, `failed_streak`, `last_success_ts`, `stale`; field lama
  dipertahankan) dan meta `/api/latest` (field yang sama);
  frontend publik `web/src/app/HomeClient.tsx` (memanggil
  `/api/health` tiap poll 60 detik; fallback ke meta `/api/latest`,
  lalu ke umur snapshot bila health tak terjangkau).
- Bot Telegram memakai umur yang sama (`bot.py:
  load_health_age_minutes` berjangkar sukses terakhir) dengan
  gerbangnya sendiri 30 menit. Sengaja TIDAK memicu gate pada
  `failed_streak >= 2` saja: itu akan menurunkan ambang efektif
  menjadi ~10 menit pada kadensi 5 menit — ambang 30 menit adalah
  keputusan Septian dan tidak diubah.

### Populasi qualifying (reserve ≥ $100k + guard 25%)
- `LIQ_MIN = $100.000` kini ditegakkan di semua tempat yang menghitung
  dari venue: poller (sumber aturan), `bot.py` (query snapshot +
  `evaluate_alerts`), `api/worker.js` (`crossVenueSpread`, best pool),
  `dashboard/logic.py: best_exit_venues` (tanpa pool lolos → []),
  `dashboard/app.py: cross_venue_spread`.
- Median alert deviasi = median harga pool lolos SETELAH guard 25%
  (`bot.py: load_live_tickers`) — median yang sama dengan yang
  dipakai poller untuk `dev_med`, bukan median snapshot mentah.
- Konsekuensi tercatat: alert spread NVDAx 6 Nov 19:11 (4,426%)
  didorong pool $179,55 dengan reserve $96.257 (< $100k) — setelah
  M2 alert itu TIDAK akan menyala lagi (spread khusus-pool-lolos
  0,325%); alert asli pada pool lolos tetap menyala (fixture
  `NVDAX_QUAL`, 4,424%). Test guard diperbarui untuk ini:
  `qa/test_spread_guard.py` kini 20 checks (dari 18).

### Waitlist: satu jalur validasi + dedup
- Submit dashboard Streamlit kini lewat Worker `/api/waitlist` dulu
  (validasi format kontak, batas panjang, cap 500/jam, dedup atomik
  `WHERE NOT EXISTS`); bila Worker tak terjangkau, fallback ke
  `dashboard/turso_read.py: insert_waitlist`, yang kini menegakkan
  aturan IDENTIK di dalam proses — jadi tidak ada lagi jalur tulis
  yang bisa menduplikasi kontak dan mencemari angka bukti G0.
  Penolakan validasi (400) bersifat final, tidak di-fallback.

### Gap ronde 8 (9 Nov 2026): admin destination, calibration counter, fallback replay
- **Admin destination (P1-G2, gap sejak R7 — kini dibangun).** Satu
  env baru `RADAR_ADMIN_CHAT_ID` (chat Telegram admin/ops, BUKAN
  kanal publik EN/ID): bila terkonfigurasi, bot mengirim alert
  "poller troubled" saat stale gate (> 30 menit tanpa siklus sukses)
  tersandung, maks. 1 pesan/jam (state di `.admin_poller_alert.json`,
  di samping bot.py). Bila tidak terkonfigurasi, kondisi itu tetap
  hanya di-log seperti sebelumnya — dan tidak ada alert ops yang
  pernah dikirim ke kanal publik. Kegagalan kirim tidak memblokir
  pass alert pasar. Tanpa nilai env ini di cron, tidak ada yang
  berubah secara perilaku.
- **Calibration counter (P2-G1 — kini dibangun).** Skor risiko akhir
  pekan tetap "experimental" sampai terkalibrasi pada >= 8 akhir
  pekan; kini ada counter-nya (`dashboard/risk.py:
  calibration_progress`, dihitung dari tanggal siklus sukses di
  `poller_health`, satu akhir pekan = pasangan Sab–Min yang teramati
  ≥ 1 hari). Progres tampil di dashboard (strip home + breakdown
  ticker). Rumus/skor TIDAK berubah. Per 9 Nov 2026: 3/8 akhir pekan
  teramati (24–25 Okt, 31 Okt–1 Nov, 7–8 Nov) — klaim belum jatuh
  tempo, bukan kesalahan.
- **Fallback replay (P2-G2 — kini dibangun).** Setiap pass alert
  (yang memegang lock) menjalankan `replay_fallback_alerts()`:
  marker di `.alert_sent_fallback.jsonl` dimasukkan kembali ke
  `alert_log` dengan kunci dedup yang sama (ticker, alert_ts, type,
  channel) via `WHERE NOT EXISTS`, sehingga delivery fallback
  akhirnya muncul di feed `/api/alerts`. Idempotent (replay dua kali
  = tanpa duplikat); gagal replay = marker tetap di file + pass
  lanjut normal; file hanya dipangkas untuk marker yang sudah
  mendarat. Pesan asli tidak tersimpan di marker, jadi baris replay
  memakai placeholder eksplisit, bukan teks yang dikarang.
- **Vs-close (P1-G1 — TIDAK dibangun, sudah tertutup).** Label
  roadmap vs-close sudah ada dan jujur di web + dashboard (EN+ID:
  methodology_thresholds, close_note, coverage_short) — tidak ada
  yang bisa dibangun tanpa lisensi feed; tidak ada feed yang
  dikarang.

### Gap ronde 7 (9 Nov 2026): advance redemption-close alert — DIBANGUN
- **Advance redemption-close alert (gap R7 #2 — kini dibangun).** Tipe
  alert baru `redemption_closing_soon`: menyala saat status masih open
  dan waktu tutup <= 24 jam lagi. TIDAK ada sumber close-time baru —
  waktu tutup diturunkan dari jadwal resmi 24/5 + kalender NYSE yang
  sudah dipakai status live (`poller.next_schedule_close_utc` /
  `bot.next_schedule_close_utc`: 00:00 ET di akhir hari kerja NYSE
  terakhir sebelum akhir pekan/hari libur; Jumat -> Sabtu 00:00 ET,
  hari sebelum libur -> 00:00 ET hari libur itu). Labelnya jujur di
  pesan ("schedule-derived close time") dan di methodology_thresholds
  web + dashboard (EN+ID, byte-identik). Dedup 24 jam standar per
  channel (BUKAN once-per-window — belum ada window saat alert ini
  menyala), dan tipe berbeda dari `redemption` sehingga alert ini
  tidak pernah menekan alert jendela-tutup yang menyusul. Ambang lain
  TIDAK berubah (spread >= 1,0%, |dev| >= 3,0%, dedup 24 jam, stale
  gate 30 menit). Field `closes_within_24h` kini terisi dari data live
  di `load_live_tickers` (sebelumnya hanya True di skenario dry-run
  sintetis). Catatan batas: waktu tutup ini turunan jadwal, BUKAN
  konfirmasi live issuer — sama seperti status redemption itu sendiri.
