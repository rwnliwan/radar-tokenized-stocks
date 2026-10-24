"""Bilingual strings (EN default, ID toggle). All user-facing product
text lives here from day one — no hardcoded second app.

The conflict-of-interest text (policy_text) is the design §11 text:
Indonesian is verbatim from the design; English is a faithful
translation of the same five points.
"""
DONATE_ADDRESS = "6GvKCpEYqjzLQqu6WLedwWArhBi33CDRh4UPpPQa2qnv"
DONATE_PAY_URL = (
    "solana:" + DONATE_ADDRESS
    + "?label=Radar%20Tokenized%20Stocks&message=Support%20development"
)
STR = {
    "en": {
        "app_title": "Radar Tokenized Stocks",
        "app_tagline": "Deviation & redemption radar for tokenized stocks — free, public, human-verified data.",
        "landing_line": "One radar for the question every tokenized-stock holder faces on weekends: can I still get out, and at what price?",
        "nav_home": "Home",
        "nav_ticker": "Ticker",
        "nav_waitlist": "Waitlist",
        "lang_label": "Language / Bahasa",
        "freshness": "Last updated: {time} ({mins} min ago)",
        "freshness_now": "Last updated: {time} (just now)",
        "stale_banner": "Data may be stale — last successful poller run {time}. Alerts are paused until fresh data returns.",
        "coverage_title": "DEX coverage",
        "coverage_text": (
            "This radar covers tokenized stocks traded on Solana DEXs: 13 xStocks tickers "
            "across 35 pools (Raydium, Orca, Meteora). It does NOT fully cover: bStocks "
            "(mostly on Binance, a CEX); Ondo tickers (deep single-venue Uniswap pools, "
            "failing the >=2 DEX venues rule); Securitize/Superstate (allowlisted "
            "registered shares, no deep DEX venue found). A market-share percentage is "
            "not published: no verified total-market denominator is available yet. "
            "A different number — verification pass rate: 13 of 43 checked candidates "
            "passed the criteria."
        ),
        "heatmap_title": "All tickers — latest deviation",
        "heatmap_note": "Reads the deviations table (latest row per ticker), not raw snapshots. Choose a ticker on the Ticker page for detail.",
        "col_ticker": "Ticker",
        "col_tier": "Tier",
        "col_price": "Depth-weighted price",
        "col_dev": "Dev vs median %",
        "col_depth": "Qualifying depth",
        "col_pools": "Pools",
        "col_updated": "Updated",
        "ticker_select": "Choose ticker",
        "block_dev": "Main deviation",
        "dw_price": "Depth-weighted price",
        "dev_median": "Deviation vs cross-venue median",
        "dev_close": "Deviation vs stock close",
        "close_pending": "Awaiting data-license resolution",
        "close_note": "vs-close figures are shown publicly only after a written public-display license is verified. Until then, the public reference is the cross-venue median.",
        "chart_title": "Deviation history (vs cross-venue median)",
        "chart_note": "From the deviations table. vs-close series unavailable (license pending). Gaps are shown as gaps, never interpolated for calculations.",
        "venue_title": "Venues",
        "venue_status_ok": "qualifies",
        "venue_status_below": "below alert threshold",
        "redemption_title": "Redemption",
        "redemption_unknown": "Unknown",
        "redemption_doc_note": "Documented schedule: 5 days/week + KYC (xStocks). No automated live source connected yet — no status is fabricated.",
        "por_title": "Proof-of-reserve freshness",
        "por_none": "No verified PoR feed connected yet.",
        "risk_title": "Weekend risk score (experimental)",
        "risk_method": "Method weekend_risk_v1: deviation (0–40) + depth (0–25) + redemption (0–20) + PoR age (0–15). Experimental until calibrated on >=8 weekends. Deviation component uses the cross-venue median while vs-close is license-pending.",
        "risk_partial": "Partial score — redemption and PoR components not yet connected, so they are excluded (not zeroed).",
        "exit_title": "Best exit venue by size",
        "exit_note": "Estimate from pool depth, not an execution promise. Full free-size calculator is a later product, not this MVP.",
        "exit_flag": "depth warning: size > 5% of pool reserve",
        "alertlog_title": "Ticker alert history",
        "alertlog_empty": "No alerts recorded yet.",
        "waitlist_title": "Join the waitlist",
        "waitlist_intro": "One short form. We use it to learn who this radar serves — never sold, never shared.",
        "f_contact": "Contact (Telegram or email)",
        "f_position": "Your tokenized-stock position size",
        "f_venues": "Where do you hold them? (venue / issuer)",
        "f_price": "Price you would consider for future premium features (optional)",
        "f_consent": "I agree to be contacted again about this project",
        "f_submit": "Join waitlist",
        "f_success": "Thanks — you are on the waitlist.",
        "f_error": "Please fill in contact, position size, venue/issuer, and tick the consent box.",
        "f_error_save": "Could not save — please try again in a moment.",
        "donate_title": "Support development — voluntary donation",
        "donate_note": "Send USDC on Solana (Solana Pay) to:\n6GvKCpEYqjzLQqu6WLedwWArhBi33CDRh4UPpPQa2qnv\nDonations do not unlock any features.",
        "disclaimer": "Not financial advice. Prices are market data, not recommendations.",
        "policy_title": "Signal & conflict-of-interest policy",
        "policy_text": (
            "1. If the project operator trades the same dislocation that is alerted, "
            "that fact is disclosed in the same channel.\n"
            "2. Public alerts are never held back, altered, or accelerated for "
            "personal positions.\n"
            "3. Personal execution on a dislocation happens only after its public "
            "alert is published.\n"
            "4. If data, an alert, or an index turns out wrong, the correction is "
            "published in the same place as the original error.\n"
            "5. Our language is factual: we do not use the words 'safe', "
            "'recommended', 'buy', or 'sell'. Our scores and indices use open, "
            "versioned methodology, with disclaimers. This is not financial advice."
        ),
        "footer_note": "Free forever: public dashboard + basic alerts. No paywall.",
        "no_data": "No data yet.",
        "loading": "Loading live data…",
    },
    "id": {
        "app_title": "Radar Tokenized Stocks",
        "app_tagline": "Radar deviasi & redemption untuk tokenized stocks — gratis, publik, data terverifikasi manusia.",
        "landing_line": "Satu radar untuk pertanyaan yang dihadapi setiap pemegang tokenized stock di akhir pekan: apakah saya masih bisa keluar, dan di harga berapa?",
        "nav_home": "Beranda",
        "nav_ticker": "Ticker",
        "nav_waitlist": "Daftar Tunggu",
        "lang_label": "Language / Bahasa",
        "freshness": "Terakhir diperbarui: {time} ({mins} menit lalu)",
        "freshness_now": "Terakhir diperbarui: {time} (baru saja)",
        "stale_banner": "Data mungkin basi — poller terakhir berhasil {time}. Alert dijeda sampai data segar kembali.",
        "coverage_title": "Cakupan DEX",
        "coverage_text": (
            "Radar ini mencakup tokenized stocks yang diperdagangkan di DEX Solana: "
            "13 ticker xStocks di 35 pool (Raydium, Orca, Meteora). TIDAK tercakup "
            "penuh: bStocks (sebagian besar di Binance, CEX); ticker Ondo (pool "
            "Uniswap single-venue yang dalam, gagal aturan >=2 venue DEX); "
            "Securitize/Superstate (saham terdaftar allowlist, tidak ditemukan venue "
            "DEX yang dalam). Persentase pangsa pasar tidak diterbitkan: belum ada "
            "denominator total pasar yang terverifikasi. Angka berbeda — tingkat "
            "lolos verifikasi: 13 dari 43 kandidat yang diperiksa lolos kriteria."
        ),
        "heatmap_title": "Semua ticker — deviasi terbaru",
        "heatmap_note": "Membaca tabel deviations (baris terbaru per ticker), bukan snapshots mentah. Pilih ticker di halaman Ticker untuk detail.",
        "col_ticker": "Ticker",
        "col_tier": "Tier",
        "col_price": "Harga tertimbang kedalaman",
        "col_dev": "Dev vs median %",
        "col_depth": "Kedalaman lolos",
        "col_pools": "Pool",
        "col_updated": "Diperbarui",
        "ticker_select": "Pilih ticker",
        "block_dev": "Deviasi utama",
        "dw_price": "Harga tertimbang kedalaman",
        "dev_median": "Deviasi vs median lintas-venue",
        "dev_close": "Deviasi vs close saham",
        "close_pending": "Menunggu penyelesaian lisensi data",
        "close_note": "Angka vs-close baru tampil publik setelah lisensi display publik terverifikasi tertulis. Sampai saat itu, acuan publik adalah median lintas-venue.",
        "chart_title": "Riwayat deviasi (vs median lintas-venue)",
        "chart_note": "Dari tabel deviations. Seri vs-close belum tersedia (lisensi menunggu). Celah tampil sebagai celah, tidak pernah diinterpolasi untuk hitungan.",
        "venue_title": "Venue",
        "venue_status_ok": "lolos",
        "venue_status_below": "di bawah ambang alert",
        "redemption_title": "Redemption",
        "redemption_unknown": "Belum diketahui",
        "redemption_doc_note": "Jadwal terdokumentasi: 5 hari/minggu + KYC (xStocks). Belum ada sumber otomatis live — tidak ada status yang dikarang.",
        "por_title": "Kesegaran proof-of-reserve",
        "por_none": "Belum ada feed PoR terverifikasi yang terhubung.",
        "risk_title": "Skor risiko akhir pekan (eksperimental)",
        "risk_method": "Metode weekend_risk_v1: deviasi (0–40) + kedalaman (0–25) + redemption (0–20) + umur PoR (0–15). Eksperimental sampai terkalibrasi >=8 akhir pekan. Komponen deviasi memakai median lintas-venue selama vs-close menunggu lisensi.",
        "risk_partial": "Skor parsial — komponen redemption dan PoR belum terhubung, sehingga dikeluarkan (bukan dinolkan).",
        "exit_title": "Venue keluar terbaik per ukuran",
        "exit_note": "Estimasi dari kedalaman pool, bukan janji eksekusi. Kalkulator ukuran bebas penuh adalah produk lanjutan, bukan MVP ini.",
        "exit_flag": "peringatan kedalaman: ukuran > 5% cadangan pool",
        "alertlog_title": "Riwayat alert ticker",
        "alertlog_empty": "Belum ada alert tercatat.",
        "waitlist_title": "Gabung daftar tunggu",
        "waitlist_intro": "Satu formulir singkat. Kami memakainya untuk memahami siapa yang dilayani radar ini — tidak pernah dijual, tidak pernah dibagikan.",
        "f_contact": "Kontak (Telegram atau email)",
        "f_position": "Ukuran posisi tokenized stock Anda",
        "f_venues": "Di mana Anda menyimpannya? (venue / issuer)",
        "f_price": "Harga yang Anda pertimbangkan untuk fitur premium mendatang (opsional)",
        "f_consent": "Saya setuju dihubungi lagi tentang proyek ini",
        "f_submit": "Gabung daftar tunggu",
        "f_success": "Terima kasih — Anda masuk daftar tunggu.",
        "f_error": "Mohon isi kontak, ukuran posisi, venue/issuer, dan centang kotak persetujuan.",
        "f_error_save": "Gagal menyimpan — silakan coba lagi sebentar lagi.",
        "donate_title": "Dukung pengembangan — donasi sukarela",
        "donate_note": "Kirim USDC di Solana (Solana Pay) ke:\n6GvKCpEYqjzLQqu6WLedwWArhBi33CDRh4UPpPQa2qnv\nDonasi tidak membuka fitur apa pun.",
        "disclaimer": "Bukan nasihat keuangan. Harga adalah data pasar, bukan rekomendasi.",
        "policy_title": "Kebijakan sinyal & konflik kepentingan",
        "policy_text": (
            "1. Bila pengelola proyek memperdagangkan dislokasi yang sama dengan "
            "yang di-alert-kan, fakta itu diungkap di kanal yang sama.\n"
            "2. Alert publik tidak pernah ditahan, diubah, atau dipercepat demi "
            "posisi pribadi.\n"
            "3. Eksekusi pribadi atas suatu dislokasi hanya dilakukan sesudah "
            "alert publiknya terbit.\n"
            "4. Bila data, alert, atau indeks ternyata salah, koreksi diterbitkan "
            "di tempat yang sama dengan kesalahan awal.\n"
            "5. Bahasa kami faktual: kami tidak memakai kata 'aman', "
            "'disarankan', 'beli', atau 'jual'. Skor dan indeks kami "
            "bermetodologi terbuka, berversi, dan ber-disclaimer. Ini bukan "
            "nasihat keuangan."
        ),
        "footer_note": "Gratis permanen: dashboard publik + alert dasar. Tanpa paywall.",
        "no_data": "Belum ada data.",
        "loading": "Memuat data live…",
    },
}

SIZE_BUCKETS = ["<$100", "$100–$1,000", "$1,000–$10,000", ">$10,000"]


def t(lang, key, **fmt):
    """Look up a string; falls back to English, then to the key itself."""
    d = STR.get(lang, STR["en"])
    s = d.get(key)
    if s is None:
        s = STR["en"].get(key, key)
    return s.format(**fmt) if fmt else s
