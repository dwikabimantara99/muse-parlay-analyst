# DECISIONS.md — Keputusan setelah Blueprint

Pelengkap resmi Blueprint Mesin Analis Parlay (Muse). Setiap keputusan user
yang mengubah, menggantikan, atau menambah blueprint dicatat di sini dengan
tanggal dan sumbernya. **Kalau DECISIONS.md dan blueprint berbeda, yang
berlaku adalah DECISIONS.md** (keputusan yang lebih baru).

Aturan pencatatan: keputusan ditulis apa adanya dari pesan user. Tafsiran
agen atas keputusan yang ambigu dicatat terpisah di bagian "Tafsiran agen"
dan berlaku sampai user menolaknya.

---

## 2026-11-20 — Review Tahap 1: LULUS + keputusan lanjutan

Sumber: pesan review user, 20 Nov 2026 22:01 WIB. Tahap 1 dinyatakan LULUS.
Urutan kerja yang ditetapkan: A → C → E → laporan → tunggu persetujuan → F.

### A. Perbaikan ledger

- **A1. Kaki VOID/PUSH di dalam parlay:** kaki itu dikeluarkan, pengali tiket
  dihitung ulang dari kaki sisanya (rumus D8). Tiket tidak otomatis VOID.
- **A2. Hasil CASHOUT:** ditambah sebagai hasil tiket, dengan kolom
  `cashout_amount`. Untung/rugi = cashout_amount − modal.

Tafsiran agen (berlaku sampai ditolak user):

- **A-T1.** Kalau SEMUA kaki VOID/PUSH, tidak ada kaki tersisa untuk dihitung
  ulang — tiket menjadi VOID (modal kembali utuh), kecuali hasilnya CASHOUT
  yang dihormati apa adanya.
- **A-T2.** Spread untuk hitung ulang pengali: pakai `combo_spread_pct` tiket
  bila ada; kalau tiket memakai pengali asli jup.ag (spread null), pakai
  default `combo.spread_cut_pct` dari playstyle.yaml.
- **A-T3.** Pengali hitung ulang BISA ≤ 1 pada kasus ekstrem (satu kaki
  favorit berat tersisa). Itu hasil hitung yang jujur, bukan kesalahan —
  CHECK database dilonggarkan ke `multiplier > 0` (skema input tiket tetap
  menuntut pengali awal > 1).
- **A-T4.** Hasil tiket yang bertentangan dengan hasil kaki ditolak
  (WIN tapi ada kaki LOSS; LOSS tapi semua kaki yang selesai WIN).
  Pengali awal selalu disimpan di `multiplier_original` sebagai jejak audit.

### B. Aturan sumber data (MENGGANTIKAN blueprint §4)

Jangan terpaku ke satu-dua situs. Cari sumber terbaik dengan urutan prioritas:

- **Jenjang 1 — RESMI:** penyelenggara kompetisinya langsung.
  NBA: nba.com (jadwal, statistik, live data) + Official NBA Injury Report.
  Bola: situs/data resmi liga atau penyelenggara (Premier League, UEFA,
  LaLiga, Serie A, Bundesliga, Ligue 1, dst.; FIFA untuk laga timnas).
- **Jenjang 2 — agregator besar terpercaya:** ESPN, Sofascore, FotMob,
  Understat (xG), Basketball-Reference.
- **Jenjang 3 — sumber valid lain,** hanya kalau jenjang 1–2 tidak punya.

Aturan:

- **B1.** Selalu pakai jenjang tertinggi yang tersedia. Catat jenjang +
  sumber + jam di setiap data.
- **B2.** Cedera & lineup wajib dicek silang minimal 2 sumber. Kalau beda,
  tampilkan keduanya, jangan pilih diam-diam.
- **B3.** Scraping boleh: jeda antar request, cache, User-Agent jelas,
  patuhi batas situs. Semua sumber mati → DATA_INCOMPLETE.
- **B4. xG bola:** sumber resmi kalau ada → Understat → Sofascore/FotMob.
  Tidak ada xG → Dixon-Coles berbasis gol, label TANPA_XG, ambang +5 poin
  lebih ketat, dilarang masuk Tiket Asuransi.

### C. Jupiter API — daftar sendiri

- **C1.** Buat wallet Solana BARU khusus untuk login Developer Portal
  Jupiter. Wallet ini TIDAK BOLEH diisi dana dan tidak berhubungan dengan
  wallet user.
- **C2.** Daftar, ambil API key gratis, simpan di `.env` (`JUPITER_API_KEY`).
  Kunci wallet disimpan di luar repo. Keduanya wajib masuk `.gitignore`.
- **C3.** Mesin ini HANYA MEMBACA data. DILARANG memanggil endpoint order,
  execute, atau apa pun yang memindahkan dana.
- **C4.** Kalau pendaftaran butuh verifikasi email/captcha/hal yang tidak
  bisa dikerjakan agen: berhenti dan laporkan. Jangan cari jalan pintas.
- **C5.** Cek: apakah `sportsMarketType` dan `line`/`handicap` memberi pasar
  spread, total, BTTS? Apakah VM kena batas region?

**Hasil pengecekan C (2026-11-20):**

- **Pasar: YA.** Probe keyless 100 event sports dari VM: `sportsMarketType`
  mencakup `moneyline`, `spreads` (620 pasar), `totals` (558),
  `both_teams_to_score` (30), plus `first_half_spreads`,
  `first_half_totals`, `second_half_totals`, `handicap`. `sportsLine`
  membawa garisnya (misal spread `-1.5`, total `2.5`).
- **Region: TIDAK ADA BLOKIR.** API keyless (tanpa key, 0,5 RPS) menjawab
  HTTP 200 dari VM.
- **Wallet baru dibuat** (C1): pubkey
  `CzFEgpBYhU4andHc4RJJHxTcRgDUYKsUtZQUbFEKRj1m`, kunci di
  `~/.config/muse-parlay-analyst/jupiter-portal-wallet.json` (mode 600, di
  luar repo). Terverifikasi di mainnet: saldo 0 lamport, 0 transaksi.
- **Portal TIDAK memakai login wallet.** Pendaftaran di
  `developers.jup.ag/sign-up` menawarkan Google/GitHub OAuth atau email +
  kode verifikasi, dengan tantangan Cloudflare "Verify you are human".
  Sesuai C4, pendaftaran DIHENTIKAN dan dilaporkan ke user: butuh tindakan
  user (daftar sendiri lalu serahkan API key, atau tunjukkan email dan
  selesaikan verifikasi + tantangan Cloudflare). Sementara itu Tahap 2
  bisa memakai akses keyless (0,5 RPS); API key menaikkan batas ke 1 RPS.
- **Wallet DIHAPUS (2026-11-20 22:23 WIB).** Wallet yang dibuat untuk
  pendaftaran tidak dipakai lagi (portal tidak memakai login wallet).
  File kunci `~/.config/muse-parlay-analyst/jupiter-portal-wallet.json`
  sudah dihapus dengan `shred -u` atas perintah user. Wallet itu tidak
  pernah diisi dana (saldo 0, 0 transaksi) dan tidak pernah dipakai untuk
  apa pun. Pubkey-nya tetap tercatat di atas hanya sebagai jejak audit.

## 2026-11-20 — Jupiter API key (user menyerahkan key)

Sumber: pesan user, 20 Nov 2026 22:22 WIB.

- **K1.** API key disimpan HANYA di `.env` (`JUPITER_API_KEY`). Nilai key
  tidak pernah ditampilkan di log, laporan, README, commit, atau pesan
  Telegram. `.env` masuk `.gitignore` (mode 600) dan tidak pernah di-commit.
- **K2.** Mode keyed: 1 RPS. Wajib ada rate limiter + cache supaya tidak
  pernah melewati batas. Kalau key ditolak/gagal → fallback ke keyless
  (0,5 RPS) dan laporkan.
- **K3.** Mesin HANYA MEMBACA data (C3 tetap berlaku): endpoint yang boleh
  dipakai hanya GET baca (`/events`, `/events/search`, `/events/{id}`,
  `/markets/{id}`). DILARANG `POST /orders`, `DELETE /positions`,
  `/claim`, dan apa pun yang memindahkan dana.
- **K4.** Tes key: satu panggilan keyed berhasil 2026-11-20 22:23 WIB
  (HTTP 200, 2 event sports).

## 2026-11-20 — Aturan pembanding harga independen

Sumber: pesan user, 20 Nov 2026 22:22 WIB.

- **P1.** Untuk setiap pasar jup.ag, catat provider asalnya (Polymarket /
  Kalshi / lainnya) — field `jup_provider` di skema kaki dan ledger.
- **P2.** `p_market` TIDAK BOLEH diambil dari provider yang sama dengan
  asal pasar jup.ag itu (itu harga yang sama, bukan pembanding).
- **P3.** Pembanding sah: provider prediction market yang lain + sportsbook
  (devig via The Odds API).
- **P4.** Aturan ini dicatat di `playstyle.yaml` (bagian `comparison`) dan
  diuji di `tests/test_config.py`. Penegakan di kode (menolak p_market
  dari provider yang sama) dibangun di Tahap 3 bersama mesin devig/blend,
  dengan tesnya sendiri.

### D. Jawaban pertanyaan Tahap 1

- **D2. p_market kosong:** pakai sportsbook (The Odds API, devig). Tetap
  tidak ada → MODEL_ONLY: p_akhir = p_model, ambang +5 poin lebih ketat,
  maks 1 kaki MODEL_ONLY per tiket, dilarang masuk Tiket Asuransi.
- **D3. The Odds API:** cache 30 menit, maks 2 panggilan per analisis,
  hanya pasar yang ada di slate, region `eu` (Pinnacle). Batas 500
  kredit/bulan, peringatan di 80%. (Dikoreksi dari 450 pada 2026-11-20:
  kuota akun terverifikasi 500/bulan dari header API; user memutuskan
  memakai 500.)
- **D4. Injury Report NBA:** cari URL resmi & jadwal update-nya sendiri di
  nba.com, verifikasi, jangan diasumsikan.
- **D7. EV per kaki** = p_akhir × (100 / harga_¢) − 1.
- **D8. Pengali kombo** = Π(100 / harga_¢_i) × (1 − 0,055). Pengali asli
  dari jup.ag (kalau user kirim) yang dipakai, selisihnya disimpan untuk
  kalibrasi spread. EV tiket = P(tiket menang, simulasi gabungan) ×
  pengali − 1.
- **D9. Harga bergerak tajam** = berubah ≥ 3¢ sejak pengambilan pertama.
- **D10. Bantalan Alt Under** = garis Alt Under − median proyeksi total
  ≥ 8 poin (≥ 12 poin kalau spread ≤ 2,5).
- **D11. Pemain kunci bola** = kiper utama, 2 bek tengah dengan menit
  terbanyak, pemain xG+xA terbanyak, dan siapa pun dengan menit ≥ 70%
  musim ini.
- **D12. Parameter simulasi TIDAK boleh ditebak.** Fit dari data historis
  2–3 musim (NBA: margin & total; bola: Dixon-Coles per liga, rho via
  MLE). Laporkan hasil fit + backtest, berlaku setelah user setujui.
- **D13. Modal default 50/50,** bisa diubah lewat chat.
- **D14. USDC dicatat sebagai USD 1:1.**

Tafsiran agen (berlaku sampai ditolak user):

- **D-T1. "+5 poin lebih ketat"** (B4, D2) diartikan sebagai: ambang peluang
  minimum naik 5 poin untuk kaki berlabel itu — misal moneyline 65% → 70%,
  min peluang kaki Asuransi 74% → 79%, Utama 65% → 70%. Ambang EV −2%
  TIDAK berubah (bukan ambang peluang). Kalau user bermaksud lain
  (misal EV juga +5 poin), sampaikan.
- **D-T2.** Batas 450 kredit/bulan The Odds API (D3) dicatat di
  `sources.yaml` (konfigurasi operasional per sumber), bukan di
  playstyle.yaml, karena bukan ambang strategi.

### E. GitHub private + kode rapi + README cantik

- **E1.** Buat repo GitHub PRIVATE `muse-parlay-analyst`, push semua commit.
- **E2.** Rapikan kode sebelum Tahap 2, pertahankan standarnya:
  `pyproject.toml`, format otomatis (ruff + black), type hints, docstring
  di setiap fungsi publik, nama file/fungsi konsisten, tidak ada kode mati
  atau file sampah, pre-commit hook supaya rapi terus.
- **E3.** README.md Bahasa Indonesia, tampilan profesional: judul +
  deskripsi singkat, badge (Python, tests, license/private), diagram
  arsitektur (Mermaid), alur kerja 10 langkah, peta folder, cara instal &
  menjalankan, perintah CLI, aturan anti-halusinasi, status tahapan
  (✅/🚧), disclaimer risiko taruhan.
- **E4.** Commit message rapi dan jelas (format conventional commits).

### F. Tahap 2

- **F1 (2a) PROBE dulu:** satu script probe per sumber (termasuk Jupiter).
  Cek: bisa diakses dari VM? format? batas? pasar apa yang tersedia?
  Kirim tabel hasil probe ke user SEBELUM membangun penarik data lengkap.
- **F2 (2b):** penarik data + validasi sesuai aturan B.
- **F3.** Selesai kalau 1 slate NBA + 1 slate bola nyata bisa ditarik
  lengkap dengan sumber, jenjang, dan jamnya.

## 2026-11-20 — Probe 2a diterima + koreksi urutan sumber

Sumber: pesan user, 20 Nov 2026 22:42 WIB. Tabel probe 2a diterima
(PAKAI 8, CADANGAN 3, JANGAN 2; 44 request ke 13 sumber).

- **FotMob DITOLAK.** Ketentuan layanannya melarang pengambilan otomatis
  tanpa izin. Dihapus dari `sources.yaml`, pindah ke daftar `rejected`
  dengan alasan. Bola jalan dengan aturan B4 (TANPA_XG) sampai ada sumber
  xG yang sah.
- **Sofascore DITOLAK.** Probe 2a (diterima user): 3/3 HTTP 403, tantangan
  bot aktif dari VM; tidak ada cara akses sah. Masuk daftar `rejected`
  sampai ada cara akses sah.
- **Understat: maintenance sementara.** Dicek ulang di probe tambahan;
  pengecekan otomatis harian ditambahkan — kalau kembali, otomatis aktif
  lagi di rantai xG.
- **Koreksi urutan sumber (aturan B — jenjang tertinggi yang tersedia
  wajib dipakai):** stats.nba.com UTAMA untuk statistik NBA (probe 2a:
  bekerja dari VM), ESPN cadangan. JSON resmi Premier League UTAMA untuk
  EPL (jadwal, lineup, cedera kalau tersedia), ESPN cadangan.
- **Urutan pembanding p_market:** sportsbook (Odds API, devig) → ESPN
  odds (devig) → Kalshi. Polymarket TIDAK dipakai sebagai pembanding
  untuk pasar jup.ag yang berasal dari Polymarket (P2). ESPN odds menunggu
  konfirmasi probe tambahan 1. Urutan dicatat di `playstyle.yaml`
  (bagian `comparison`, kunci `order`).
- **D4 TERJAWAB:** Official NBA Injury Report di
  `official.nba.com/nba-injury-report-2026-27-season/`, PDF per 15 menit
  di `ak-static.cms.nba.com/referee/injury/` (terverifikasi probe 2a).
- **jup_markup:** selisih harga jup.ag vs midpoint orderbook Polymarket
  untuk pasar yang sama. Ini BUKAN edge — ini mengukur biaya tambahan
  jup.ag. Diukur di probe tambahan 3, dicatat per pasar.
- **Probe tambahan 1–5 (kecil, sebelum 2b):** (1) ESPN odds — apakah
  scoreboard/summary ESPN memuat garis sportsbook + provider-nya;
  (2) Kalshi sports — petakan pasar NBA & bola, seberapa sering cocok
  dengan pasar jup.ag di slate hari ini; (3) jup_markup vs Polymarket
  CLOB; (4) football-data.co.uk — CSV historis (hasil + odds Pinnacle)
  untuk kalibrasi Tahap 3, bukan data live; (5) Understat cek ulang +
  cek harian otomatis.
- **ODDS_API_KEY:** user memerintahkan pengambilan key dari email,
  simpan hanya di `.env` (aturan sama seperti K1–K4), verifikasi 1
  panggilan + catat kredit yang terpakai per panggilan. Gmail terhubung
  22:47 WIB (cskepto@gmail.com) tapi tidak ada email Odds API di
  mailbox itu — akun Odds API user dibuat bukan dengan gmail ini.
  Atas izin user (22:50 WIB), agen mendaftar sendiri paket Starter
  FREE pakai cskepto@gmail.com, nama depan "jokowi" (pilihan user),
  captcha diselesaikan agen; tidak ada password/pembayaran. Email key
  tiba 22:53 WIB dari team@the-odds-api.com; key disimpan HANYA di
  `.env` (mode 600, gitignored) — nilainya tidak pernah ditampilkan.
  Verifikasi 1 panggilan 22:54 WIB: HTTP 200, NBA h2h region eu,
  9 event, Pinnacle tersedia. Kredit: **1 kredit/panggilan** untuk
  endpoint ini; sisa **499/500** (total kuota akun ini 500/bulan —
  D3/sources.yaml sudah dikoreksi dari 450 ke 500 atas keputusan user
  22:55 WIB).

## 2026-11-20 — Hasil probe tambahan (2a lanjutan)

Sumber: probe tambahan 1–5, 20 Nov 2026 22:57 WIB (40 request baru).

- **ESPN odds: PAKAI untuk bola saja.** Garis sportsbook ada di
  scoreboard EPL (7/7, DraftKings lengkap ML+spread+total; summary
  tambah Bet 365 ML desimal) tapi TIDAK ADA untuk NBA (scoreboard 0/4
  + 0/6, summary `odds: []`). Implikasi: untuk NBA, urutan pembanding
  adalah Odds API → Kalshi (ESPN odds dilewati).
- **Kalshi sports: PAKAI.** Moneyline tercocokkan 100% di liga yang
  dicakup (NBA 20/20, EPL 15/15, LaLiga 9/9); EPL spread 40/100 garis,
  total 60/90 garis. Catatan fetcher: field harga bernama `*_dollars`
  (bukan `yes_bid`/`yes_ask`); pakai bid/ask, bukan `last_price` (bisa
  0.0000). Pencocokan butuh normalisasi nama (Kalshi: kota/nama
  singkat; jup.ag: julukan/nama resmi).
- **jup_markup: median 0,5¢** (11/11 pasar tercocokkan, mean 0,68¢,
  max 1,5¢ Chelsea −1.5 spread) — praktis setengah spread Polymarket;
  jup.ag hampir tidak menambah biaya. Catatan: harga jup.ag dari cache
  ±1 jam lebih tua dari midpoint; fetcher 2b/3 harus mengambil keduanya
  sedekat mungkin.
- **football-data.co.uk: PAKAI dengan catatan.** CSV EPL 2025/26 +
  2024/25 terverifikasi (380 baris, kolom Pinnacle lengkap).
  (a) Situs memperingatkan odds Pinnacle "systematically out of date"
  sejak 23/07/2025 — kalibrasi Tahap 3 pakai musim selesai sebelum
  tanggal itu (mis. 2024/25) atau validasi dulu. (b) Ketentuan pakai
  membatasi data untuk "private individuals only, NOT commercial or
  data training products using automated bots/scrapers/AI" — pemakaian
  untuk proyek pribadi ini MENUNGGU KEPUTUSAN USER.
- **Understat: masih maintenance** (cek ulang 22:49 WIB). Cek harian
  otomatis aktif (`probes/check_understat.py` + cron harian); bila
  kembali, Understat aktif lagi di rantai xG bila `status == "up"` dan
  `checked_at` < 24 jam. Sampai saat itu B4 (TANPA_XG) berlaku.
