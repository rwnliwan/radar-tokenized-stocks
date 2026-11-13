"""Harness penambahan Radar 2026-11-12 — PROMOSI dari /tmp (S10, fix ronde
review DeepSeek Radar 2026-11-13).

Asal: /tmp/test_penambahan.py (harness scratch builder, HASIL_TEST.md
§3.2) HILANG kena restart VM 12 Nov ~23:55 WITA — file tidak ada
(verifikasi: `ls /tmp/test_penambahan.py` = No such file). Harness ini
ditulis ulang dari HASIL_TEST.md §3.2 + klaim 84 PASS-nya. File ini
adalah file repo (qa/test_penambahan_2026-11-12.py), bukan scratch.

CARA JALAN (semua lokal, tidak ada tulis ke Turso live, tidak ada
deploy, tidak ada network):
  - Fungsi murni poller.py (exit_score_v2, monday_gap_predict,
    liquidation_status) diuji langsung dari import.
  - Semua yang butuh DB (migrasi, INSERT deviations, median depth,
    run_weekly_monday_gap) berjalan atas salinan sqlite LOKAL di temp
    dir, dengan poller.query / poller.pipeline di-monkeypatch ke sqlite
    itu. Tidak ada .db repo yang dibaca/diubah.
  - run_cycle_perp / run_hourly_liquidation berjalan dry-run dengan
    hl_post di-monkeypatch ke payload Hyperliquid CANNED (fixture
    bentuk-asli, bukan panggilan jaringan). Tidak ada panggilan live.

Yang TIDAK bisa direkonstruksi dari HASIL_TEST.md (dinyatakan eksplisit
— jangan mengarang penggantinya):
  1. Daftar 84 asersi persis aslinya. HASIL_TEST §3.2 hanya memberi
     deskripsi per kelompok + nilai kunci (total 54,2; parsial 25/25 =
     100,0; funding 0,0000125 -> 0,0 / 0,00005 -> 5,0 / 0,000125 -> 15,0; monday gap dasar
     1,04/75,0 'Tinggi'; dst.), bukan daftar asersi satu-per-satu.
     Harness ini menguji SEMUA nilai kunci itu (dengan input yang
     diturunkan dari kode poller.py saat ini — lihat butir 4), tetapi
     jumlah totalnya TIDAK 84 dan TIDAK BOLEH diklaim 84. Hitungan
     harness ini dilaporkan apa adanya di akhir run.
  2. Hasil live run_cycle_perp / run_hourly_liquidation atas API
     Hyperliquid + Turso live 12 Nov 2026 ~21:05 WITA (10 baris, funding
     terisi semua, tanpa SPY/QQQ/GLD; 10 baris, liq/distance selalu NULL,
     source hyperliquid-info). Data live saat itu tidak tersimpan di
     repo dan tidak bisa diputar ulang. Yang diuji di sini: jalur kode
     yang sama (fetch -> siklus -> dry-run print) dengan payload canned
     berbentuk sama; angka live 12 Nov dikutip sebagai bentuk yang
     diharapkan, bukan direproduksi dari data live.
  3. Hasil live run_weekly_monday_gap minggu 2026-11-07 atas data live
     (2 prediksi: NVDAx 0,93% confidence 15,0; TSLAx 1,22% confidence
     75,0; outcome keduanya "accurate"). Data deviations/snapshots live
     minggu itu tidak ada di repo. Yang diuji di sini: fungsi yang sama
     (predict -> idempotensi 2x -> fill outcome -> fill 2x no-op) atas
     data sintetis lokal dengan struktur yang sama (2 ticker berdata
     dari 13, 11 ticker ter-skip); nilai prediksi sintetis (TSLAx 1,12 /
     65,0; NVDAx 0,94 / 50,0) adalah hasil hitung dari data sintetis
     itu, BUKAN klaim mereproduksi angka live 12 Nov.
  4. Input persis kasus "total penuh 54,2/100". HASIL_TEST hanya
     mencatat totalnya, bukan inputnya. Input di sini diturunkan dari
     kode saat ini (dev 2,0%; depth r=0,8; redemption 'gated'; funding
     0,00005; OI +18,4% -> 20,0+10,0+10,0+5,0+9,2 = 54,2) dan
     diverifikasi fungsi mengembalikan 54,2 — input aslinya mungkin
     berbeda.
  5. Perilaku 'closed' redemption pada skor: HASIL_TEST §3.2 mencatat
     "batas redemption" dari kode 12 Nov (closed -> 20,0 konstan).
     Sejak itu S8 (fix ronde review DeepSeek, 13 Nov, worker lain)
     mengubahnya: 'closed' kini diskalakan jam-ke-next-open (<=24 jam
     -> 20; <=72 jam -> 10; else 0; jam tak diketahui -> None).
     Harness ini menguji perilaku kode SAAT INI (S8), bukan perilaku
     12 Nov — perbedaan ini dicatat, bukan disembunyikan.
  6. Ambang buka Senin di fill outcome: HASIL_TEST memakai 13:30 UTC
     (EDT). M2 (fix ronde review DeepSeek, 13 Nov) mengubahnya ke
     14:30 UTC (EST — DST AS berakhir 1 Nov 2026). Tes fill di sini
     memakai baris Senin >= 14:30 UTC.
  7. Butir guard DESAIN §5.4 yang TIDAK ada di harness asli dan TIDAK
     ditambahkan di sini (di luar rekonstruksi §3.2): ambang alert sisi
     bot (evaluate_alerts 0,99/1,00; exit 69/70 — bot.py, bukan
     poller.py); multichain gate (#5 — kini diliput
     qa/test_radar_fix_schema.py untuk M9); guard bahasa (#7); guard
     retensi (#8). Anti full-scan (#4) di sini hanya grep historis
     atas poller.py; gerbang yang benar adalah qa/test_no_fullscan.py
     (EXPLAIN QUERY PLAN, S9).

Usage: python3 qa/test_penambahan_2026-11-12.py   (exit 0 = PASS)
"""
import ast
import contextlib
import io
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import poller  # noqa: E402

SCHEMA = os.path.join(ROOT, "schema.sql")
MIGRATION_2026_11_12 = os.path.join(
    ROOT, "migrations", "2026-11-12-penambahan.sql")
POLLER_SRC = os.path.join(ROOT, "poller.py")

FAILURES = []
PASSES = [0]


def check(name, cond, detail=""):
    if cond:
        PASSES[0] += 1
        print("PASS " + name)
    else:
        print("FAIL " + name + (f" — {detail}" if detail else ""))
        FAILURES.append(name + (f": {detail}" if detail else ""))


# ----------------------------------------------------------------------
# Local sqlite plumbing: poller.query / poller.pipeline -> sqlite3.
# ----------------------------------------------------------------------
class LocalDB:
    def __init__(self, path, sql_text):
        if os.path.exists(path):
            os.remove(path)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(sql_text)
        self.conn.commit()

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def pipeline(self, stmts):
        for sql, params in stmts:
            self.conn.execute(sql, params)
        self.conn.commit()

    def close(self):
        self.conn.close()


def read_schema():
    with open(SCHEMA) as f:
        return f.read()


def pre_penambahan_schema():
    """schema.sql dengan tambahan 2026-11-12 dilucuti (tabel
    perp_snapshots / liquidation_watch / monday_gap + kolom exit_score
    / exit_score_version). Tiap pelucutan ditegaskan (count == 1)
    supaya drift skema gagal keras, bukan diam-diam menguji skema baru.
    Tambahan 2026-11-13 (exit_score_components, perp_px_source,
    idx_deviations_ts, idx_poller_health_cycle_ts, CHECK outcome,
    idx_deviations_ticker_nocase_ts) SENGAJA dipertahankan: migrasi
    2026-11-12 tidak menyentuhnya. Pengecualian: dua indeks
    perp_snapshots 2026-11-13 (idx_perp_snapshots_ts,
    idx_perp_ticker_nocase_ts) ikut dilucuti bersama span F1 —
    tabelnya tidak ada sebelum penambahan, jadi CREATE INDEX-nya
    gagal bila dipertahankan."""
    sql = read_schema()
    spans = [
        ("  -- F3 (penambahan 2026-11-12",
         "  exit_score_version TEXT,\n"),
        ("-- F1 (penambahan 2026-11-12",
         "CREATE INDEX IF NOT EXISTS idx_perp_ticker_nocase_ts "
         "ON perp_snapshots(ticker_id COLLATE NOCASE, ts);\n"),
        ("-- F4 (penambahan 2026-11-12",
         "CREATE INDEX IF NOT EXISTS idx_liqwatch_ticker_ts "
         "ON liquidation_watch(ticker_id, ts);\n"),
        ("-- F2 (penambahan 2026-11-12",
         "CREATE INDEX IF NOT EXISTS idx_monday_gap_ticker_week "
         "ON monday_gap(ticker_id, week_start);\n"),
    ]
    for start, end in spans:
        assert sql.count(start) == 1, f"strip failed (start): {start!r}"
        assert sql.count(end) == 1, f"strip failed (end): {end!r}"
        i, j = sql.index(start), sql.index(end) + len(end)
        assert i < j, "strip span inverted"
        sql = sql[:i] + sql[j:]
    return sql


def apply_guarded_migration(conn, migration_path):
    """Terapkan migrasi 2026-11-12 dengan pola PRAGMA-guarded (cek
    PRAGMA table_info sebelum tiap ALTER; lewati kolom yang sudah
    ada) — pola yang sama dengan qa/apply_migration_2026-11-13.py.
    Mengembalikan (run, skipped)."""
    text = open(migration_path).read()
    # Buang baris komentar DULU (header migrasi mengandung ';' di
    # dalam komentar — split ';' sebelum ini memecah komentar jadi
    # fragmen SQL palsu).
    code_lines = [ln for ln in text.splitlines()
                  if not ln.strip().startswith("--")]
    code = "\n".join(code_lines)
    run, skipped = 0, 0
    for stmt in [s.strip() for s in code.split(";") if s.strip()]:
        clean = stmt.strip()
        m = re.match(r"ALTER TABLE (\w+) ADD COLUMN (\w+)",
                     clean, re.IGNORECASE)
        if m:
            table, col = m.group(1), m.group(2)
            cols = {r[1] for r in conn.execute(
                f"PRAGMA table_info({table})")}
            if col in cols:
                skipped += 1
                continue
        conn.execute(clean)
        run += 1
    conn.commit()
    return run, skipped


# ----------------------------------------------------------------------
# A. exit_score_v2 (pure) — HASIL_TEST §3.2
# ----------------------------------------------------------------------
def test_exit_score():
    f = poller.exit_score_v2
    # Total penuh 54,2/100 (input diturunkan dari kode — lihat header
    # butir 4): 20,0 + 10,0 + 10,0 + 5,0 + 9,2.
    r = f(2.0, 800000.0, 1000000.0, "gated", None, 0.00005, 18.4)
    check("exit_score: total penuh 54,2/100",
          r["total"] == 54.2 and r["score_100"] == 54.2
          and r["max_possible"] == 100.0
          and r["components_present"] == 5 and not r["partial"],
          str(r))
    check("exit_score: komponen total penuh = 20+10+10+5+9,2",
          r["components"] == {"deviation": 20.0, "depth": 10.0,
                              "redemption": 10.0, "funding": 5.0,
                              "oi": 9.2}, str(r["components"]))
    # Parsial 1 komponen -> 25/25 = 100,0 parsial.
    r = f(None, 100.0, 1000.0, None, None, None, None)
    check("exit_score: parsial 1 komponen -> 25/25 = 100,0",
          r["total"] == 25.0 and r["max_possible"] == 25.0
          and r["score_100"] == 100.0 and r["partial"]
          and r["components_present"] == 1, str(r))
    # Tanpa komponen -> None.
    r = f(None, None, None, None, None, None, None)
    check("exit_score: tanpa komponen -> None",
          r["score_100"] is None and r["max_possible"] == 0
          and r["components_present"] == 0, str(r))
    # Funding v2 (ambang setara per-8-jam, Revisi 13 Nov 2026 (2)):
    # 0,0000125 -> 0,0 / 0,00005 -> 5,0 / 0,0001 -> 11,7 / 0,000125 -> 15,0.
    r = f(0.0, 1000000.0, 1000000.0, "open", 100.0, 0.0000125, 0.0)
    check("exit_score: funding 0,0000125 -> 0,0",
          r["components"]["funding"] == 0.0, str(r["components"]))
    r = f(0.0, 1000000.0, 1000000.0, "open", 100.0, 0.00005, 0.0)
    check("exit_score: funding 0,00005 -> 5,0",
          r["components"]["funding"] == 5.0, str(r["components"]))
    r = f(0.0, 1000000.0, 1000000.0, "open", 100.0, 0.0001, 0.0)
    check("exit_score: funding 0,0001 -> 11,7",
          r["components"]["funding"] == 11.7, str(r["components"]))
    r = f(0.0, 1000000.0, 1000000.0, "open", 100.0, 0.000125, 0.0)
    check("exit_score: funding 0,000125 -> 15,0",
          r["components"]["funding"] == 15.0, str(r["components"]))
    # Caps.
    r = f(5.0, 100.0, 1000.0, "open", 100.0, 0.001, 25.0)
    check("exit_score: caps (dev 5% -> 30; oi 25% -> 10; depth r<=0,5 -> 25)",
          r["components"]["deviation"] == 30.0
          and r["components"]["oi"] == 10.0
          and r["components"]["depth"] == 25.0, str(r["components"]))
    # Batas redemption (perilaku S8 saat ini — lihat header butir 5).
    cases = [(("closed", 2.0), 20.0), (("closed", 55.0), 10.0),
             (("closed", 100.0), 0.0), (("closed", None), None),
             (("open", 24.0), 20.0), (("open", 72.0), 10.0),
             (("open", 100.0), 0.0), (("open", None), None),
             (("gated", None), 10.0), (("paused", None), 10.0),
             (("unknown", None), None), ((None, None), None)]
    ok = all(poller._exit_redemption_component(s, h) == want
             for (s, h), want in cases)
    check("exit_score: batas redemption (closed skala jam-ke-buka, S8)",
          ok, str([(s, h, poller._exit_redemption_component(s, h))
                   for (s, h), _ in cases]))
    # Bobot jumlah 100.
    check("exit_score: bobot jumlah 100 (30+25+20+15+10)",
          30.0 + 25.0 + 20.0 + 15.0 + 10.0 == 100.0)
    check("exit_score: method_version exit_score_v2",
          f(1.0, 1000000.0, 1000000.0, "open", 100.0, 0.0001, 0.0)
          ["method_version"] == "exit_score_v2")


# ----------------------------------------------------------------------
# B. monday_gap_predict (pure) — HASIL_TEST §3.2
# ----------------------------------------------------------------------
def test_monday_gap_predict():
    f = poller.monday_gap_predict
    # Dasar 1,04/75,0 'Tinggi' (D=1,2; R=0,8; pools 3; depth 1,5 jt;
    # spread 0,4; kalibrasi 0).
    gap, conf, label = f(1.2, 0.8, 3, 1500000, 0.4, 0)
    check("monday_gap: dasar 1,04/75,0 'Tinggi'",
          gap == 1.04 and conf == 75.0 and label == "Tinggi",
          f"{gap}/{conf}/{label}")
    # Tanda berlawanan.
    gap, conf, label = f(1.2, -0.8, 3, 1500000, 0.4, 0)
    check("monday_gap: tanda berlawanan -> gap 0,40, conf 50,0 'Sedang'",
          gap == 0.4 and conf == 50.0 and label == "Sedang",
          f"{gap}/{conf}/{label}")
    # Cap kalibrasi (10 akhir pekan dinilai -> tetap 25 poin).
    gap, conf, label = f(1.2, 0.8, 3, 1500000, 0.4, 10)
    check("monday_gap: cap kalibrasi -> conf 100,0",
          conf == 100.0 and label == "Tinggi", f"{conf}/{label}")
    # Clamp +/-10.
    check("monday_gap: clamp +10",
          f(20, 20, 3, 1500000, 0.4, 0)[0] == 10.0)
    check("monday_gap: clamp -10",
          f(-20, -20, 3, 1500000, 0.4, 0)[0] == -10.0)
    # Spread None -> komponen spread 0 (bukan renormalisasi).
    gap, conf, label = f(1.2, 0.8, 3, 1500000, None, 0)
    check("monday_gap: spread None -> conf 55,0 'Sedang'",
          conf == 55.0 and label == "Sedang", f"{conf}/{label}")
    # Bobot confidence jumlah 100 (30+25+20+25).
    check("monday_gap: bobot confidence jumlah 100",
          30 + 25 + 20 + 25 == 100)


# ----------------------------------------------------------------------
# C. liquidation_status (pure) — HASIL_TEST §3.2
# ----------------------------------------------------------------------
def test_liquidation_status():
    f = poller.liquidation_status
    # Batas divergensi 1,0/3,0.
    check("liq: divergensi 0,5 -> ok", f(0.5, None) == "ok")
    check("liq: divergensi 1,0 -> warning", f(1.0, None) == "warning")
    check("liq: divergensi 3,0 -> critical", f(3.0, None) == "critical")
    # Jarak 5,0/10,0.
    check("liq: distance 10,0 -> warning",
          f(None, 10.0) == "warning")
    check("liq: distance 5,0 -> critical",
          f(None, 5.0) == "critical")
    # Lag 120/600 — diuji sebagai parameter, bukan dari API (S4: lag
    # tidak bisa diukur dari endpoint publik; pemanggil memakai None).
    check("liq: lag 120 -> ok (batas ketat, >120)",
          f(None, None, 120) == "ok")
    check("liq: lag 121 -> warning", f(None, None, 121) == "warning")
    check("liq: lag 600 -> warning (batas ketat, >600)",
          f(None, None, 600) == "warning")
    check("liq: lag 601 -> critical", f(None, None, 601) == "critical")
    check("liq: lag None -> tidak pernah memicu",
          f(None, None, None) == "ok")


# ----------------------------------------------------------------------
# D. Migrasi di sqlite lokal — HASIL_TEST §3.2
# ----------------------------------------------------------------------
def test_migration(tmp):
    db = LocalDB(os.path.join(tmp, "mig.db"), pre_penambahan_schema())
    conn = db.conn
    check("migrasi: pra-migrasi tidak punya perp_snapshots",
          conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE "
                       "type='table' AND name='perp_snapshots'"
                       ).fetchone()[0] == 0)
    check("migrasi: pra-migrasi tidak punya liquidation_watch",
          conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE "
                       "type='table' AND name='liquidation_watch'"
                       ).fetchone()[0] == 0)
    check("migrasi: pra-migrasi tidak punya monday_gap",
          conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE "
                       "type='table' AND name='monday_gap'"
                       ).fetchone()[0] == 0)
    check("migrasi: pra-migrasi deviations tanpa exit_score",
          "exit_score" not in {r[1] for r in conn.execute(
              "PRAGMA table_info(deviations)")})
    # Terapkan sekali (bare — sama seperti berkas migrasi).
    conn.executescript(open(MIGRATION_2026_11_12).read())
    conn.commit()
    for tbl in ("perp_snapshots", "liquidation_watch", "monday_gap"):
        check(f"migrasi: tabel {tbl} ada setelah migrasi",
              conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE "
                           f"type='table' AND name='{tbl}'"
                           ).fetchone()[0] == 1)
    for idx in ("idx_perp_ticker_ts", "idx_liqwatch_ticker_ts",
                "idx_monday_gap_ticker_week"):
        check(f"migrasi: indeks {idx} ada",
              conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE "
                           f"type='index' AND name='{idx}'"
                           ).fetchone()[0] == 1)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(deviations)")}
    check("migrasi: deviations punya exit_score + exit_score_version",
          "exit_score" in cols and "exit_score_version" in cols)
    # S1: bare run ke-2 GAGAL (duplicate column) — mekanisme yang
    # didokumentasikan; jalur idempotent adalah PRAGMA-guarded.
    try:
        conn.executescript(open(MIGRATION_2026_11_12).read())
        conn.commit()
        check("migrasi (S1): bare run ke-2 GAGAL duplicate column", False,
              "run ke-2 sukses — S1 tidak ter-reproduksi")
    except sqlite3.OperationalError as e:
        check("migrasi (S1): bare run ke-2 GAGAL duplicate column",
              "duplicate column" in str(e).lower(), str(e))
        conn.rollback()
    run, skipped = apply_guarded_migration(conn, MIGRATION_2026_11_12)
    check("migrasi: PRAGMA-guarded re-run tanpa error (2 ALTER di-skip)",
          run == 6 and skipped == 2, f"run={run} skipped={skipped}")
    return db


# ----------------------------------------------------------------------
# E. INSERT deviations 14 kolom — HASIL_TEST §3.2
# ----------------------------------------------------------------------
def test_deviations_insert(db):
    conn = db.conn
    conn.execute(
        "INSERT INTO deviations (id, ticker_id, ts, depth_weighted_price,"
        " dev_vs_close_pct, dev_vs_median_pct, qualifying_depth_usd,"
        " pools_used, pools_excluded, redemption_status, por_age_hours,"
        " weekend_risk_score, exit_score, exit_score_version)"
        " VALUES (NULL,'TSLAx','2026-11-08T22:00:00Z',101.0,NULL,1.2,"
        " 1500000.0,3,0,'gated',NULL,NULL,54.2,'exit_score_v2')")
    conn.commit()
    row = conn.execute("SELECT exit_score, exit_score_version FROM "
                       "deviations WHERE ticker_id='TSLAx'").fetchone()
    check("deviations: INSERT 14 kolom roundtrip exit_score 54,2",
          row is not None and row[0] == 54.2
          and row[1] == "exit_score_v2", str(row))


# ----------------------------------------------------------------------
# F. Median depth 7 hari (dry-run) — HASIL_TEST §3.2
# ----------------------------------------------------------------------
def test_median_depth(db):
    conn = db.conn
    for i, depth in enumerate([100.0, 200.0, 300.0, 400.0, 500.0]):
        conn.execute(
            "INSERT INTO deviations (ticker_id, ts, depth_weighted_price,"
            " dev_vs_median_pct, qualifying_depth_usd, pools_used)"
            " VALUES ('T00x',?,101.0,1.2,?,3)",
            (f"2026-11-0{2 + i}T20:00:00Z", depth))
    conn.commit()
    old_query, old_pipeline = poller.query, poller.pipeline
    poller.query, poller.pipeline = db.query, db.pipeline
    try:
        med = poller.refresh_median_depth_7d(
            {}, datetime(2026, 11, 8, 22, 30, tzinfo=timezone.utc),
            ["T00x"], dry_run=True)
    finally:
        poller.query, poller.pipeline = old_query, old_pipeline
    check("median depth 7d: dry-run median 300,0 dari [100..500]",
          med.get("T00x") == 300.0, str(med))


# ----------------------------------------------------------------------
# G/H. run_cycle_perp + run_hourly_liquidation (dry-run, canned hl_post)
# ----------------------------------------------------------------------
CANNED_SYMBOLS = ["TSLA", "NVDA", "AAPL", "MSFT", "META",
                  "GOOGL", "COIN", "MSTR", "HOOD", "CRCL"]


def canned_hl_post(payload):
    if payload.get("type") == "metaAndAssetCtxs":
        meta = {"universe": [{"name": f"xyz:{s}"}
                             for s in CANNED_SYMBOLS]}
        ctxs = [{"markPx": "450.0", "oraclePx": "449.5",
                 "funding": "0.0001", "openInterest": "1000"}
                for _ in CANNED_SYMBOLS]
        return [meta, ctxs], ""
    if payload.get("type") == "allMids":
        return {f"xyz:{s}": "450.0" for s in CANNED_SYMBOLS}, ""
    return None, f"canned: unknown type {payload.get('type')}"


def test_perp_and_liquidation():
    old = poller.hl_post
    poller.hl_post = canned_hl_post
    try:
        data, err = poller.fetch_xyz_market_data()
        check("perp: fetch canned -> 10 ticker",
              len(data) == 10 and set(data) == set(poller.XYZ_PERP),
              f"n={len(data)} err={err}")
        check("perp: funding terisi semua (10/10)",
              all(d.get("funding") is not None for d in data.values()))
        check("perp: tanpa SPY/QQQ/GLD (tidak ada perp XYZ)",
              not ({"SPYx", "QQQx", "GLDx"} & set(data)))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            frag = poller.run_cycle_perp(
                datetime(2026, 11, 8, 22, 30, tzinfo=timezone.utc),
                {}, dry_run=True)
        out = buf.getvalue()
        check("perp: dry-run cycle 10/10 baris",
              "DRY-RUN perp tickers=10/10" in out and frag == "",
              out.strip().splitlines()[:1])
        check("perp: dry-run mencetak 10 baris row",
              out.count("DRY-RUN perp row=") == 10,
              f"rows={out.count('DRY-RUN perp row=')}")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            frag = poller.run_hourly_liquidation(
                datetime(2026, 11, 8, 22, 30, tzinfo=timezone.utc),
                {}, dry_run=True)
        out = buf.getvalue()
        rows = []
        for ln in out.splitlines():
            if ln.startswith("DRY-RUN liquidation row="):
                rows.append(ast.literal_eval(
                    ln.split("row=", 1)[1]))
        check("liquidation: dry-run 10 baris",
              "DRY-RUN liquidation tickers=10/10" in out and frag == "",
              out.strip().splitlines()[:1])
        check("liquidation: liq/distance selalu NULL",
              len(rows) == 10
              and all(r[4] is None and r[5] is None for r in rows),
              str(rows[:2]))
        check("liquidation: source hyperliquid-info",
              len(rows) == 10
              and all(r[6] == "hyperliquid-info" for r in rows))
        check("liquidation: tanpa alert (divergensi ~0,11% < 1,0%)",
              "alert=-" in out, out.strip().splitlines()[:1])
    finally:
        poller.hl_post = old


# ----------------------------------------------------------------------
# I. run_weekly_monday_gap atas data sintetis lokal — HASIL_TEST §2/§3.2
# ----------------------------------------------------------------------
def seed_monday_gap_data(db):
    conn = db.conn
    for t in ("TSLAx", "NVDAx"):
        conn.execute(
            "INSERT INTO universe (ticker_id, underlying, issuer, tier,"
            " status, created_at, updated_at) VALUES "
            "(?,?,'xstocks',1,'active','2026-11-01T00:00:00Z',"
            "'2026-11-01T00:00:00Z')", (t, t))
    pools = [("solana:p1", "TSLAx"), ("solana:p2", "TSLAx"),
             ("solana:p3", "NVDAx"), ("solana:p4", "NVDAx")]
    for pid, t in pools:
        conn.execute(
            "INSERT INTO pools (pool_id, ticker_id, chain, dex,"
            " pair_address, quote_token, is_active, min_liquidity_usd)"
            " VALUES (?,?,'solana','TestDex','0xpair','USDC',1,100000)",
            (pid, t))
    # Jumat 2026-11-06 20:00 (fri) + Minggu 2026-11-08 22:00 (sun).
    dev_rows = [
        ("TSLAx", "2026-11-06T20:00:00Z", 100.0, None, None, None),
        ("NVDAx", "2026-11-06T20:00:00Z", 200.0, None, None, None),
        ("TSLAx", "2026-11-08T22:00:00Z", 101.0, 1.2, 1500000.0, 3),
        ("NVDAx", "2026-11-08T22:00:00Z", 202.0, 0.9, 500000.0, 2),
    ]
    for t, ts, dw, dev, depth, pools_used in dev_rows:
        conn.execute(
            "INSERT INTO deviations (ticker_id, ts, depth_weighted_price,"
            " dev_vs_median_pct, qualifying_depth_usd, pools_used)"
            " VALUES (?,?,?,?,?,?)", (t, ts, dw, dev, depth, pools_used))
    # Spread Minggu 22:00: 2 pool per ticker, reserve >= $100rb.
    snap_rows = [
        ("solana:p1", "2026-11-08T22:00:00Z", 100.5, 600000.0),
        ("solana:p2", "2026-11-08T22:00:00Z", 101.5, 600000.0),
        ("solana:p3", "2026-11-08T22:00:00Z", 201.0, 300000.0),
        ("solana:p4", "2026-11-08T22:00:00Z", 203.0, 300000.0),
    ]
    for pid, ts, px, reserve in snap_rows:
        conn.execute(
            "INSERT INTO snapshots (pool_id, ts, price_usd, reserve_usd,"
            " source) VALUES (?,?,?,?,'test')", (pid, ts, px, reserve))
    # Senin 2026-11-09 14:30 UTC (M2: buka NYSE EST) untuk fill outcome.
    for t, dw in (("TSLAx", 101.5), ("NVDAx", 200.0)):
        conn.execute(
            "INSERT INTO deviations (ticker_id, ts, depth_weighted_price,"
            " dev_vs_median_pct, qualifying_depth_usd, pools_used)"
            " VALUES (?, '2026-11-09T14:30:00Z', ?, NULL, NULL, NULL)",
            (t, dw))
    conn.commit()


def test_monday_gap_week(db):
    old_query, old_pipeline = poller.query, poller.pipeline
    poller.query, poller.pipeline = db.query, db.pipeline
    try:
        sun = datetime(2026, 11, 8, 22, 30, tzinfo=timezone.utc)
        mon = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        state = {}
        frag = poller.run_weekly_monday_gap(sun, state)
        check("monday_gap: predict menulis 2 baris (dari 13 ticker)",
              db.conn.execute("SELECT COUNT(*) FROM monday_gap"
                              ).fetchone()[0] == 2, f"frag={frag}")
        row = db.conn.execute(
            "SELECT gap_pred_pct, confidence FROM monday_gap "
            "WHERE ticker_id='TSLAx'").fetchone()
        check("monday_gap: TSLAx prediksi 1,12 / 65,0",
              row == (1.12, 65.0), str(row))
        row = db.conn.execute(
            "SELECT gap_pred_pct, confidence FROM monday_gap "
            "WHERE ticker_id='NVDAx'").fetchone()
        check("monday_gap: NVDAx prediksi 0,94 / 50,0",
              row == (0.94, 50.0), str(row))
        # Idempotensi: state sama -> no-op; state baru -> cek baris
        # yang ada -> tetap 2 baris, bukan duplikat.
        poller.run_weekly_monday_gap(sun, state)
        n1 = db.conn.execute("SELECT COUNT(*) FROM monday_gap"
                             ).fetchone()[0]
        poller.run_weekly_monday_gap(sun, {})
        n2 = db.conn.execute("SELECT COUNT(*) FROM monday_gap"
                             ).fetchone()[0]
        check("monday_gap: jalankan 2x minggu sama -> tetap 2 baris",
              n1 == 2 and n2 == 2, f"n1={n1} n2={n2}")
        # Fill outcome Senin (M2: ambang buka 14:30 UTC).
        frag = poller.run_weekly_monday_gap(mon, {})
        rows = db.conn.execute(
            "SELECT ticker_id, outcome_gap_pct, outcome FROM monday_gap "
            "ORDER BY ticker_id").fetchall()
        check("monday_gap: fill outcome TSLAx accurate "
              "(aktual +0,50 vs prediksi 1,12)",
              ("NVDAx", -0.99, "inaccurate") in rows
              and ("TSLAx", 0.5, "accurate") in rows,
              f"frag={frag} rows={rows}")
        # Isi outcome 2x -> no-op.
        poller.run_weekly_monday_gap(mon, {})
        rows2 = db.conn.execute(
            "SELECT ticker_id, outcome_gap_pct, outcome FROM monday_gap "
            "ORDER BY ticker_id").fetchall()
        check("monday_gap: isi outcome 2x -> no-op",
              rows2 == rows, f"rows2={rows2}")
    finally:
        poller.query, poller.pipeline = old_query, old_pipeline


# ----------------------------------------------------------------------
# J. Guard anti full-scan historis atas poller.py — HASIL_TEST §3.2
# (grep ini yang dibuktikan buta oleh S9; gerbang yang benar adalah
# qa/test_no_fullscan.py. Dipertahankan di sini hanya sebagai cek
# kontinuitas terhadap klaim harness asli.)
# ----------------------------------------------------------------------
def test_antifullscan_grep():
    src = open(POLLER_SRC).read()
    check("anti-fullscan (grep historis): tidak ada SELECT * di poller.py",
          not re.search(r"SELECT\s+\*", src, re.IGNORECASE))
    check("anti-fullscan (grep historis): tidak ada COUNT(*) atas 4 "
          "tabel besar di poller.py",
          not re.search(r"COUNT\(\*\)\s+FROM\s+(snapshots|deviations|"
                        r"perp_snapshots|liquidation_watch)",
                        src, re.IGNORECASE))


def main():
    tmp = tempfile.mkdtemp(prefix="radar-penambahan-qa-")
    print(f"tmpdir: {tmp}")
    print("CATATAN: /tmp/test_penambahan.py asli HILANG (restart VM); "
          "harness ini rekonstruksi dari HASIL_TEST.md §3.2 — "
          "bukan file aslinya, bukan 84 asersi aslinya.")
    test_exit_score()
    test_monday_gap_predict()
    test_liquidation_status()
    mig_db = test_migration(tmp)
    test_deviations_insert(mig_db)
    mig_db.close()

    main_db = LocalDB(os.path.join(tmp, "main.db"), read_schema())
    test_median_depth(main_db)
    test_perp_and_liquidation()
    seed_monday_gap_data(main_db)
    test_monday_gap_week(main_db)
    main_db.close()

    test_antifullscan_grep()

    print()
    print(f"TOTAL: {PASSES[0]} PASS, {len(FAILURES)} FAIL "
          f"(harness rekonstruksi — BUKAN klaim 84 PASS asli)")
    if FAILURES:
        print("FAIL:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PENAMBAHAN HARNESS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
