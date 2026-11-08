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
  4,426% (6 Nov 19:11 UTC) TETAP terpicu (4,424% dari fixture).
- **Masih belum terverifikasi live:** jalur `redemption_paused`
  (0 baris di `alert_log` sepanjang sejarah) — hanya akan teruji bila
  suatu hari ada jeda on-chain sungguhan, atau diuji dengan simulasi
  (butuh keputusan terpisah). Bukan blocker G0, tapi jangan klaim
  format 🔴 sudah teruji.
