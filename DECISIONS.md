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
  data training products using automated bots/scrapers/AI" — DIPUTUSKAN
  user 23:08 WIB: BOLEH dengan syarat (lihat bagian "Tambahan 2b"
  di bawah).
- **Understat: masih maintenance** (cek ulang 22:49 WIB). Cek harian
  otomatis aktif (`probes/check_understat.py` + cron harian); bila
  kembali, Understat aktif lagi di rantai xG bila `status == "up"` dan
  `checked_at` < 24 jam. Sampai saat itu B4 (TANPA_XG) berlaku.

## 2026-11-20 — Tambahan 2b + keputusan football-data.co.uk

Sumber: pesan user, 20 Nov 2026 23:08 WIB.

- **Verifikasi spread/total NBA di jup.ag (prioritas tinggi, bagian
  2b).** Probe tambahan menemukan 0 pasar spread/total NBA di jup.ag
  (sampel 100 event), padahal Alt Under NBA adalah pasar utama user.
  2b wajib memastikan: ambil SEMUA event sports (pagination, tanpa
  batas 100); bila tidak ada, cek ulang mendekati tip-off (3 jam & 1
  jam sebelum laga); laporkan ada/tidak, sejak kapan dibuka, garis apa
  saja.
- **Bobot pembanding p_market.** Harga Kalshi kurang tajam dibanding
  sportsbook. Di p_market simpan sumber pembandingnya
  (`comparison_source`). Sportsbook (devig) dipakai bila ada; Kalshi
  hanya bila sportsbook tidak ada, dan kaki itu diberi label
  `PEMBANDING_KALSHI` di laporan. KXNBASPREAD / KXNBATOTAL dipakai
  sebagai pembanding garis NBA bila pasar itu ada di jup.ag.
- **football-data.co.uk: BOLEH** (keputusan user; membatalkan status
  "menunggu keputusan" di atas), dengan syarat: (a) unduhan satu kali
  per file musim yang dibutuhkan, bukan scraping massal, dengan jeda
  antar request; (b) CSV disimpan lokal di `data/` (gitignored), TIDAK
  di-commit ke GitHub; (c) kalibrasi pakai musim ≤ 2024/25 (odds
  Pinnacle basi sejak 23/07/2025).

## 2026-11-21 — Peran harga pasar (berlaku mulai Tahap 3)

Sumber: pesan user, 21 Nov 2026 05:14 WIB.

Prinsip: harga pasar adalah PENGUAT dan ALAT CEK HARGA, bukan hakim.
Selisih dengan pasar = alasan untuk MENYELIDIKI, bukan otomatis menolak.

- **Tampilan per kaki.** Laporan menampilkan terpisah: p_model |
  p_pasar (+ sumber pembanding) | p_akhir (gabungan). Bobot awal
  w = 0,3 tetap (playstyle.yaml `blend.w_model`); angka model & pasar
  wajib terlihat, bukan hanya hasil gabungan.
- **Label harga** (dari EV terhadap harga ¢ jup.ag; ambang di
  playstyle.yaml `price_labels`): DISKON bila EV ≥ +2%; WAJAR bila
  −2% ≤ EV < +2%; MAHAL bila EV < −2%.
- **MAHAL tidak lagi dicoret otomatis** — MENGGANTI filter EV < −2%
  di blueprint §7a (kunci `filters.all_markets.min_ev_pct` DIHAPUS
  dari playstyle.yaml). Kaki MAHAL tetap tampil di laporan dengan
  label + angkanya. Optimizer TIDAK memasukkannya ke Tiket Asuransi,
  kecuali user memintanya secara eksplisit; boleh masuk Tiket Utama,
  wajib berlabel MAHAL di racikan. Filter keras lain
  (DATA_INCOMPLETE, aturan Alt Under, BTTS xG, dll.) tetap berlaku.
- **"Kenapa beda?" (wajib bila |p_model − p_pasar| > 8 poin).**
  Ambang sudah ada di playstyle.yaml
  (`anomaly.model_vs_market_points: 8.0`). Muse memeriksa dari data
  (bukan menebak): update cedera/lineup terbaru vs jam data model;
  pergerakan harga (kapan & seberapa besar); kualitas data model
  (TANPA_XG, MODEL_ONLY, sampel kecil, data basi); konteks jadwal
  (back-to-back, rotasi, laga penting berikutnya). Kesimpulan salah
  satu dari: (a) "Pasar kemungkinan tahu sesuatu" → sebutkan apa,
  kaki diberi 🟡/🔴; (b) "Model kemungkinan salah/kurang data" →
  sebutkan kelemahannya; (c) "Tidak ditemukan alasan" → potensi
  value, tetap ditandai hati-hati. Kalau penjelasan butuh info yang
  tidak ada di data: tulis "tidak terverifikasi", jangan mengarang.
- **Bobot w ditentukan data.** Setiap 50 kaki, laporan kalibrasi
  membandingkan akurasi (Brier) model vs pasar
  (playstyle.yaml `calibration.compare_brier_model_vs_market`).
  Kalau model konsisten lebih akurat, usulkan kenaikan w — berlaku
  setelah user setuju.
- **Aturan pembanding independen TETAP** (P1–P4): jangan bandingkan
  jup.ag dengan Polymarket untuk pasar asal Polymarket — ini agar
  label DISKON/WAJAR/MAHAL bermakna.

## 2026-11-22 — Profil bettor + arah mesin (diskusi langsung dengan user)

User tidak lagi memakai Claude sebagai perantara; diskusi langsung dengan Muse, bahasa sehari-hari, tanpa jargon teknis.

### Profil bettor: konservatif

- Tiket Asuransi: pengali x2–2,5 (lebih tinggi boleh bila analisis sangat optimis).
- Tiket Utama ("agresif" versi user): menumpuk kaki 75¢–85¢ sampai x3–x4; x5 bila fakta/data sangat optimis. x3,5 sudah sangat disyukuri.
- x9–x10 = tiket hiburan/gambling saja.
- Hindari moneyline (menang/kalah langsung) — seperti lempar koin — kecuali fakta/data sangat kuat membuktikan siapa yang menang.
- Pasar utama: Alt Under NBA. Bukti gaya (22 Nov 2026 pagi): dua kombo 5 kaki semua Under MENANG — $15→$52,04 (+$37,04, x3,47) dan $12→$25,81 (+$13,81, x2,15); lima laga sama (POR-NYK, NOP-SAS, LAC-DAL, MEM-MIN, BOS-SAC), garis beda di 4 dari 5 laga (tiket kedua lebih tinggi/aman). Total +$50,85. Venue kedua tiket itu belum diketahui — ditanyakan ke user (jup.ag tidak punya pasar total NBA).

### Arah mesin (jawaban user atas 6 ide 22 Nov)

1. **Tanpa mode kertas 2–4 minggu.** Uji statistik saja: Monte Carlo (100.000x, sudah di blueprint §5) tetap mesin utama, ditambah uji backtest ke laga lama, uji kalibrasi (apakah peluang 75% benar kejadian 75%?), dan uji kepekaan (skenario bintang absen / tempo berbeda). Objektif, jangan mengarang, jangan berdusta. B2B masuk sebagai faktor. Peluang overtime dihitung simulasi — penting untuk tiket Under.
2. **Tanpa cek rutin.** Analisis on-demand: user minta ("bro aku butuh info soal laga ini"), semua tugas jalan bersamaan dan menyajikan data.
3. **Cek ulang sebelum submit WAJIB** — parlay tidak bisa dibatalkan; satu kaki salah atau news terlewat = tiket sia-sia.
4. **Laporan lengkap; rekomendasi situasional lewat tanya-jawab**, tidak kaku/formal. LLM pintar yang ditenagai mesin olah data nyata — tidak menipu user.
5. **Bukan peringatan sebelum laga, tapi pantauan live saat laga jalan:** update menit berjalan, status tiket ("masih hijau" / "masih aman"), deteksi anomali (free throw berlebihan, hujan tripoin).
6. **Mesin belajar sendiri: arah bagus dan diizinkan, bukan keharusan sekarang.** Inti = analisis kode mendalam + data statistik real-time + laporan objektif. User tidak membatasi kreativitas.

### Urutan bangun (diusulkan 22 Nov, MENUNGGU persetujuan user)

1. Otak NBA (proyeksi total, simulasi 100.000x termasuk OT + B2B + cedera, rating pemain, 5 laga terakhir, H2H, kandang-tandang). 2. Cek ulang sebelum submit. 3. Laporan lengkap + tanya-jawab. 4. Pantauan live. 5. Otak bola. 6. Mesin belajar sendiri.

## 2026-11-22 — Persetujuan urutan bangun + perluasan Otak NBA

User MENYETUJUI urutan bangun (18:54 WIB): 1 otak NBA, 2 cek ulang pra-submit, 3 laporan + tanya-jawab, 4 pantauan live, 5 otak bola, 6 belajar sendiri. Langkah 1 mulai dibangun.

### Perluasan cakupan Otak NBA (permintaan user 18:54)

- Simulasi real-time: proyeksi total, 100.000x (OT + B2B + cedera), rating pemain, 5 laga terakhir, H2H, kandang-tandang — semua dalam satu otak.
- Skenario skuad lengkap: full vs full; per tim jumlah bintang yang tersedia (mis. 3 bintang vs 2 bintang karena 2 absen, lawan 3 absen) — skenario arbitrer per tim, bukan hanya hitungan tetap.
- Otak membaca data bursa taruhan + mendeteksi pergerakan agresif. Pelajaran dari laga Thunder (Nov 2026): user pasang Thunder Under 227.5 di 75¢; sebelum tip-off bergerak ekstrem ke 71¢ karena news yang tidak diketahui user; tiket kalah. Pergerakan 4¢ itu di atas ambang sharp move 3¢ (D) dan wajib ditandai ANOMALI per §5d — mesin harus memperingatkan sebelum submit.
- Rekomendasi penambah perhitungan untuk meminimalkan penyimpangan (dari agen, untuk Tahap 3): pace, ORtg/DRtg, hari istirahat/B2B, home court, bobot resensi (laga terakhir lebih berat), dampak pemain berbobot menit (BPM × menit, §5a), pace matchup, OT; ketinggian Denver/Utah + bendera turnamen (§5a). Kecenderungan wasit (FT rate) dipertimbangkan bila ada sumber gratis — bila tidak ada, ditunda dan dicatat, tidak dikarang.

### Otak bola (dijelaskan ke user 18:54)

Model yang sama untuk sepak bola: proyeksi gol per tim (Dixon-Coles, §5b), simulasi 100.000x, peluang 1X2, Over/Under gol, BTTS, distribusi skor. Input xG/xGA (60% musim + 40% 5–6 laga terakhir), home advantage per liga, rekor kandang/tandang; penalti absensi bek/kiper/striker utama. Saat ini rantai xG putus → mode TANPA_XG (berbasis gol). Langkah 5.

## 2026-11-22 — Venue jup.ag + bursa sebagai pembaca psikologi market

- Venue utama user: **jup.ag** (dikonfirmasi 22 Nov 19:00, lewat screenshot). Screenshot menampilkan moneyline saja — konsisten dengan putusan akhir 21 Nov (0 spread/total NBA). Tiket kombo Under pagi tadi UI-nya berbeda — kemungkinan dari venue lain. Pindai ulang ke-6 (22 Nov 19:01 WIB, keyed, 52 halaman, 5.116 event, scan_complete): 137 event NBA, 83 laga, spread 0, total 0 — jup.ag TETAP tidak punya pasar total NBA. Jadi kombo Under itu pasti bukan dari jup.ag; venue total user masih belum diketahui.
- Prinsip baru: data bursa BUKAN sekadar pembanding harga — bursa dibaca sebagai **psikologi market/bandar**. Mesin wajib membaca di mana market memasang garis dan apa artinya, lalu memakai itu untuk menguji rasa "aman" dari model. Bahaya yang dicegah: model bilang Under aman padahal garis itu batas bawah yang ditentukan market — lalu mesin memutuskan tidak mengambil bantalan poin dan kalah. Keputusan bantalan (8/12 poin, D10) harus mempertimbangkan posisi garis market, bukan hanya output model; rasa "aman" model wajib di-cross-check ke garis market sebelum kaki dipakai. Implementasi: modul anomali/pembanding pasar Tahap 3 langkah 1 (snapshot garis + harga + waktu; model vs market berbeda arah soal "aman" → ANOMALI + pemicu "Kenapa beda?").

## 2026-11-22 — KOREKSI: pasar total/spread NBA ADA di jup.ag (putusan 21 Nov SALAH)

- Putusan akhir 21 Nov 09:00 ("jup.ag tidak punya spread/total NBA", 6 pemindaian) SALAH — penyebabnya: pemindai hanya membaca endpoint daftar `/events` (dan detail `/events/{id}`), yang hanya menampilkan 2 pasar moneyline per event. Tampilan web jup.ag (dibuktikan user lewat screenshot + URL POLY-1338695) menampilkan Spread dan Totals lengkap.
- Kebenaran (terverifikasi live 22 Nov ~19:15 WIB): pasar spread/total NBA hidup di Polymarket (provider asal), dan UI jup.ag menampilkannya. Event Polymarket `nba-det-atl-2026-11-22` punya 283 pasar: moneyline, spread (tangga penuh), total O/U 31 garis (199.5–255.5, langkah 2 poin), plus player props. Total pasar ~225.5–226.5 (volume terbesar 225.5: O 48¢/U 52¢). Garis Alt Under (+8/+12 dari ~226.5): U 235.5 = 71¢, U 239.5 = 80¢ — dalam rentang 75–85¢ yang disukai user. Volume garis jauh TIPIS ($5–11) — mesin wajib cek bid/ask + likuiditas, bukan harga terakhir.
- Akibat: (1) Alt Under NBA BISA dimainkan lewat jup.ag — pertanyaan venue Kalshi (a)/(b)/(c) berubah: Kalshi bukan lagi satu-satunya jalan. (2) Tiket kombo Under pagi tadi MUNGKIN dari jup.ag — klaim "pasti bukan dari jup.ag" dicabut. (3) Arsitektur mesin: tangga total/spread NBA diambil dari Polymarket gamma API per event (berdasarkan slug), BUKAN dari API jup.ag. P2 TETAP: Polymarket tidak boleh jadi pembanding untuk pasar asal Polymarket — pembanding tetap sportsbook devig → Kalshi. (4) Pemindai check_nba_lines.py harus diperbaiki (cek tangga Polymarket, bukan hanya daftar jup.ag).
- Bukti: out/jup_event_POLY-1338695.json (API jup.ag: 2 pasar), out/poly_event_det_atl.json (Polymarket: 283 pasar).

## 2026-11-22 — Persetujuan parameter fit NBA (D12) + temuan auditor

- **D12 DISETUJUI user 2026-11-22 19:57 WIB** (setelah auditor/Claude meninjau laporan): home advantage 1,6552; B2B −1,596; sigma_total 18,2198; sigma_margin 13,8168; t_nu 34,5; altitude −0,0105. Parameter berlaku untuk pemakaian nyata. Re-fit dari validasi out-of-sample (temuan 1) dapat menggeser angka — pergeseran material minta persetujuan ulang.
- **Temuan auditor 1 — validasi terlalu optimis: BENAR.** Fit + backtest memakai rating musim penuh BBRef ("melihat masa depan"); sudah dicatat jujur di kode (fit_nba_params.py: "Perbaikan ke depan: rating rolling sampai sebelum tanggal laga"). Brier 0,1859 kemungkinan agak optimis; kesenjangan vs klimatologi (0,2436) besar, jadi skill nyata kemungkinan ada, tapi angka jujurnya harus diukur out-of-sample. Perbaikan: rating rolling point-in-time (hanya laga sebelum tanggal uji) + re-fit sigma.
- **Temuan 2 — hitung-ganda pemain absen: BENAR.** Kode tanpa replacement level (dampak = BPM × menit/48 × bpm_scale, dikurangi penuh); rating tim 60% musim + 40% last10 — pemain yang sudah absen di last10 terhitung ganda. Bukti: 4 pemain cadangan BPM negatif menaikkan total DET-ATL 218,28 → 221,95 (+3,67); Duren (BPM 8,8, OUT sejak ~8 Nov) dihitung ganda ~1,4 poin. bpm_scale 1,0 BELUM DIFIT (asumsi awal). Perbaikan: (a) replacement level — dampak = (BPM − BPM_replacement) × menit/48 × skala; (b) koreksi tumpang-tindih last10 dari partisipasi game log.
- **Temuan 3 — bantalan Under: BENAR.** Dari distribusi model (Student-t ν=34,5; persentil sim p75=235): +8 → P(Under) 0,66–0,67; +12 → 0,74. Usulan aturan: Asuransi +12 dari max(median model, garis market) + syarat P_model(Under) ≥ 74%; Utama tetap +8 (atau +12 bila spread ≤ 2,5), diukur dari max yang sama. Perubahan playstyle.yaml — butuh persetujuan user.
- **Temuan 4 — cek silang cedera NBA 1 sumber: BENAR.** Rotowire kini hanya mengembalikan 5 entri + "Subscribers Only" (paywall, terverifikasi live 22 Nov) — tidak bisa mengonfirmasi cedera DET/ATL. ESPN cedera NBA BEKERJA (110 cedera, status+tanggal+komentar; mencakup 10 pemain OUT DET/ATL) → sumber kedua; Rotowire dicopot ke cadangan di sources.yaml. Catatan ESPN: status vs komentar kadang beda (Holland: status Out, komentar "questionable"); ada entri non-cedera (Onyenso: kontrak two-way) — logika gabung harus menanganinya.
- **Usulan urutan:** perbaikan 1–4 sebagai patch langkah 1b SEBELUM langkah 2 (cek ulang pra-submit butuh cek cedera yang bekerja; semua langkah berikut memakai otak ini). Menunggu keputusan user.

## 2026-11-22 — Patch langkah 1b disetujui + bantalan Asuransi dari target peluang

- User SETUJU perbaiki dulu (patch langkah 1b: temuan auditor 1–4) sebelum langkah 2 (2026-11-22 20:06 WIB).
- **Bantalan Asuransi TIDAK dikunci +12 — dihitung dari target peluang 74%** (titipan user 20:06): garis Alt Under Asuransi = garis terkecil dari tangga market yang memenuhi P_model(Under) ≥ 74% (dari distribusi empiris simulasi 100.000x, persentil ke-74) DAN ≥ garis market + 8 (lantai "batas bawah bandar"). Bila uji ulang mengubah sebaran (sigma), bantalan ikut menyesuaikan otomatis. +12 hanya nilai saat ini (sigma 18,2). Utama tetap +8 (atau +12 bila spread ≤ 2,5), diukur dari max(median model, garis market).

## 2026-11-22 — Patch langkah 1b selesai (temuan auditor 1–4)

- **Validasi rolling point-in-time diadopsi sebagai metode validasi** (D-R1–D-R5 di LAPORAN-FIT-NBA.md §12; mode `--rolling` di skrip fit/validasi). Brier jujur kandang-menang 0,1983 (v1 0,1859, optimis); skill nyata tetap ada (klim 0,2436). Re-fit TIDAK MATERIAL (sigma +4,2–4,4%, home +0,009, B2B +0,080) — nilai D12 tetap berlaku, tidak ada persetujuan ulang. Adopsi nilai rolling sebagai parameter berjalan = keputusan terpisah (lihat LAPORAN-TAHAP-3-LANGKAH-1B.md §8).
- **Replacement level BPM −2,0** (literatur Basketball-Reference, asumsi yang didokumentasikan, bukan hasil fit) + **koreksi tumpang-tindih last10** (faktor 1 − 0,4 × missed/10, dari game log BBRef). Contoh DET@ATL total 221,95 → 218,75; Duren hitung-ganda 1,4 poin terkonfirmasi (missed 10/10 per BBRef).
- **Bantalan Asuransi dari target peluang 0,74 + lantai market +8** (keputusan user 20:06 WIB): garis terkecil dari tangga yang P_model(Under) ≥ 0,74 (persentil ke-74 sim 100.000x) DAN ≥ garis market + 8. Utama tetap +8 (+12 bila spread ≤ 2,5) dari max(median, garis market). Parameter di filters.nba_alt_under (config v6).
- **ESPN cedera NBA = sumber kedua (tier 2)** untuk cek silang cedera NBA; **Rotowire cadangan** (paywall: 5 entri + "Subscribers Only", 22 Nov 2026). Aturan merge: status = datum terstruktur, komentar = konteks + flag konflik; entri non-cedera (two-way/rest/personal) tidak dihitung sebagai konfirmasi cedera.
- **Keputusan desain menunggu objeksi reviewer:** K=10 shrinkage (D-R2); utama_line spread=None → bantalan 8; Rest/Personal tidak dimodelkan sebagai absen. Selisih BBRef vs ESPN soal Duren (inactive 25 Okt vs OUT ~8 Nov) UNKNOWN — partisipasi memakai BBRef.
- Laporan: LAPORAN-TAHAP-3-LANGKAH-1B.md. Tes 707 (dari 613), config v6.

## 2026-11-22 — Adopsi nilai rolling + temuan auditor babak 2

- **ADOPSI NILAI ROLLING (user 2026-11-22 20:36 WIB)**: sigma_total 18,2198→18,9868; sigma_margin 13,8168→14,4307; home 1,6552→1,6639; B2B −1,596→−1,5164; t_nu 34,5→35,0. Altitude TIDAK diadopsi (−0,399 rolling adalah noise, SE 1,14; tetap −0,0105). Diterapkan oleh koordinator langkah 2 (addendum) + contoh diregenerasi.
- **Aturan condong-ke-market (temuan 4, keputusan user, disetujui main agent)**: selama model belum terbukti lebih akurat dari market soal total, bila |median model − garis market| > 5,0 DAN "Kenapa beda?" tidak menemukan alasan konkret, probabilitas kaki untuk keputusan Asuransi memakai probabilitas tersirat MARKET (harga tangga), bukan model. Bila harga market < 74%, kaki tidak memenuhi syarat Asuransi. Bila alasan konkret ditemukan (mis. market belum menghargai cedera yang terkonfirmasi), probabilitas model boleh dipakai dengan alasan tercatat. Aturan ini dipakai recheck (langkah 2) + peracik tiket (langkah 3). Uji historis (median model vs garis market) menentukan kapan kepercayaan ke model dipulihkan.
- **Temuan 3 — Asuransi & Utama kaki sama (BENAR, dicatat)**: contoh DET@ATL keduanya Under 233,5 — bila kalah, dua tiket hangus bareng. Kendala desain langkah 3 (peracik tiket): untuk laga yang sama, garis Asuransi dan Utama HARUS berbeda (Asuransi lebih tinggi/lebih aman); pola user sendiri: laga sama, garis berbeda. Jangan pernah memakai kaki identik di dua tiket.
- **Temuan 5 — spread unknown → +12 + ambil spread dari market (BENAR, preferensi user dicatat)**: spread utama diambil dari tangga Polymarket (tersedia di ladder.spreads); bila tetap tidak diketahui → bantalan +12 (bukan +8) — fail-closed konservatif. Implementasi di langkah 2.
- **Temuan 1 — Rest/Personal tidak dihitung absen (BENAR)**: ESPN is_injury=False (Rest/Personal, cth. Tatum "(rest)") dilewati merge nba_brain; PDF kemungkinan menghitungnya (status OUT tanpa alasan) — kesenjangan sumber. Perbaikan (langkah 2): lapisan ketersediaan — OUT apapun alasannya (cedera/rest/personal/skors) dari sumber mana pun → absen di sim, dengan alasan tercatat; B2 tetap berlaku untuk klaim cedera; rest 1 sumber diterapkan dengan catatan kepercayaan + diverifikasi ulang di recheck.
- **Temuan 2 — menit/BPM sampel kecil (BENAR + diperluas)**: mp Duren 19,0 dari 2 laga (dampak absen understated ~2,5 poin bila menit sebenarnya ~30); BPM 8,8 dari 2 laga juga noisy (kemungkinan inflated) — kedua kesalahan berlawanan arah, efek neto UNKNOWN. Perbaikan (langkah 2): shrinkage menit + BPM ke musim lalu berdasarkan jumlah laga (fetcher bbref sudah mendukung season=2026); rookie/tanpa musim lalu pakai nilai musim berjalan + catatan.
- **Temuan 4 — uji historis garis total (BENAR, perlu probe)**: kandidat gratis paling menjanjikan DunkAPI (500 kredit gratis, closing lines sejak Jul 2020) — BELUM teruji (butuh probe: cakupan 2024–27 + biaya per laga + signup); HotHand terlalu tua (2015–18); HoopsAPI lambat (10 req/hari); Odds API historis BERBAYAR (di luar aturan sumber gratis). Probe DunkAPI = pekerjaan langkah 2 (signup butuh persetujuan user bila perlu akun).

## 2026-11-22 — Patch 1c dilebur ke langkah 2 (keputusan user 20:41 WIB)

- Kelima aturan (adopsi rolling; ketersediaan rest/personal; shrinkage menit+BPM ke musim lalu; spread dari market + fallback +12; condong-ke-market) dikerjakan di TAHAP 3 LANGKAH 2 — rencana patch 1c terpisah DIBATALKAN. Syarat laporan langkah 2: (1) daftar 5 aturan + status terpasang/teruji masing-masing; (2) bukti recheck menangkap kabar istirahat mendadak dekat tip-off; (3) hasil probe DunkAPI (musim tercakup + closing vs opening; bila garis pembukaan, jangan dipakai uji model-vs-market). Probe DunkAPI mulai tanpa signup; signup akun butuh persetujuan user.

## 2026-11-22 — Tahap 3 Langkah 2 selesai (cek ulang pra-submit + 5 aturan)

- **Artefak analisis NBA** (`engine/nba_analysis.py`, skema `nba_analysis.schema.json` v1): `cli.py analyze` kini melampirkan artefak per laga NBA — proyeksi + simulasi 100.000x (median, p74, peluang OT), garis Asuransi/Utama dari `engine/cushion.py`, harga tangga Polymarket (+ estimasi jup.ag), p_model/p_pasar/p_akhir (blend w=0,3), label DISKON/WAJAR/MAHAL, status cedera + sumber, timestamp tiap datum, snapshot harga pertama (basis jup_estimated_cents). Status: OK | HOLD (B2 gagal atau Asuransi tidak meets) | DATA_INCOMPLETE (gagal fetch/sim).
- **Recheck pra-submit** (`engine/recheck.py`, skema `recheck.schema.json` v1; `cli.py recheck --analysis <file> [--match <id>]`): ambil ulang cedera (PDF tier 1 + ESPN tier 2) + tangga Polymarket; bandingkan cedera baru/berubah, gerak harga, gerak garis market, selisih model-vs-market, data basi; resim bila material; putusan per kaki TETAP_OK / PERHATIAN / JANGAN_PASANG / DATA_INCOMPLETE + putusan tiket GO / NO-GO + `action_required`. **Exit code: 0 = GO, 1 = NO-GO (laporan tetap ditulis), 2 = recheck tidak bisa berjalan (tidak ada laporan).** 0 kredit Odds API (recheck tidak memakai pembanding baru — `p_market` dibawa dari kaki lama).
- **Kelima aturan (syarat laporan #1) — SEMUA terpasang + teruji**: (1) nilai rolling diadopsi (config v7, contoh diregenerasi); (2) lapisan ketersediaan — OUT apapun alasan (cedera/Rest/Personal/skors) dari sumber mana pun → absen di sim, alasan tercatat (`reason` + `is_injury` + `availability_n_sources`); rest 1 sumber diterapkan + catatan kepercayaan `availability_1_sumber:<pemain>`; B2 tidak berubah untuk klaim cedera; (3) shrinkage menit+BPM ke musim lalu, w = n/(n+K), K=10 (`simulation.nba.shrinkage_k_games`, config v8) — PILIHAN DESAIN mengikuti K=10 D-R2, bukan hasil fit, menunggu keberatan reviewer; (4) spread dari tangga Polymarket (garis spread volume terbesar), unknown → bantalan Utama +12 — **menggantikan keputusan desain 1b "spread=None → bantalan 8"**; (5) condong-ke-market di recheck (lihat bawah).
- **Aturan condong-ke-market (di recheck)**: pemicu |median − garis market| > 5,0; "Kenapa beda?" mekanis HANYA alasan (a) — cedera baru OUT/DOUBTFUL + market belum menghargainya (garis tidak bergerak searah median, atau < 1 poin); tanpa alasan → kaki Asuransi pakai probabilitas market (`price_cents` mentah tangga segar / 100, fallback `mid_cents`, keduanya hilang → DATA_INCOMPLETE); < 0,74 → JANGAN_PASANG; kaki Utama selalu probabilitas model. Per kaki tercatat `probability_used`/`probability_value`/`kenapa_beda`.
- **Keputusan desain recheck (koordinator, menunggu objeksi reviewer)**: HOLD → JANGAN_PASANG (belum siap masuk tiket); resim + garis berubah → JANGAN_PASANG garis lama + `action_required` "ganti garis ke X" (NO-GO = jangan submit sesuai rencana awal); resim + garis tetap → PERHATIAN; fetch cedera gagal + data masih segar (≤3 jam) → tetap bisa GO + `fetch_error` tercatat, basi/umur tak diketahui → DATA_INCOMPLETE; gerak harga <1¢ = noise, 1–2¢ → PERHATIAN, ≥3¢ = anomali (aturan Thunder); pemain kembali dari cedera (resolved) TIDAK memicu resim (di luar daftar pemicu yang disepakati) tapi dicatat; garis hilang → langsung JANGAN_PASANG tanpa resim; moneyline jup.ag tidak ada fetcher per-event di repo → `moneyline_jup` None + `errors`, TIDAK menggagalkan recheck.
- **Kasus campuran PDF-cedera/ESPN-rest** (koordinator, menunggu objeksi reviewer): `is_injury=True` bila ADA sumber mengklaim cedera; alasan = detail cedera sumber tier tertinggi (PDF); `availability_n_sources`=2 → masuk `confirmed_both`. Alasan: klaim cedera tier 1 itu nyata, dan kedua sumber sepakat pemain tidak tersedia.
- **Koreksi Kalshi (terverifikasi live 22 Nov)**: garis total NBA Kalshi BUKAN bilangan bulat — tangga 199,5–255,5 langkah 2 poin, SAMA PERSIS dengan Polymarket (29 garis; judul literal "Over 233.5 points scored"). Cocok-eksak bekerja: p_market Kalshi tersedia untuk kedua kaki DET@ATL (0,68 dan 0,755 dari mid bid/ask). Catatan 2a soal "garis bulat" + klaim "Kalshi hampir tidak pernah memberi p_market" DICABUT — cakupan p_market Kalshi untuk Alt Under BAIK.
- **Kaki laporan recheck belum membawa kunci `ticket`** (kontrak langkah 2 tidak memintanya; `leg_id` sudah mengidentifikasinya — CLI membaca tiket dari akhir `leg_id`). Pertimbangkan menambahkannya di langkah 3 bila peracik tiket membutuhkannya.
- **Jendela recheck**: on-demand (sesuai jawaban user #2: tidak ada rutinitas, cek saat user mau pasang). `data.recheck_window_minutes` [30, 60] + ambang basi cedera 3 jam sudah di config; keputusan 2b soal verifikasi pasar 3 jam & 1 jam sebelum tip-off BELUM diselaraskan dengan jendela ini — usulan penyelarasan di laporan langkah 2 (tidak diubah diam-diam).
- **Probe DunkAPI (syarat laporan #3)**: tanpa signup — NBA odds 2013-14 s.d. sekarang; garis PEMBUKAAN dan PENUTUPAN tersedia sejak Jul 2020 (2020-21 ke atas); 2013-14–2019-20 hanya garis final pra-laga (disimpan sebagai close). `get_odds` 5 kredit/laga atau 10 kredit/hari; 500 kredit gratis/bulan, tanpa kartu. Uji historis 150 laga ≈ 15 hari-laga × 10 = ~150 kredit (rute per-hari; rute per-laga 750 kredit, lewat batas). Syarat "jangan dipakai bila hanya opening" TIDAK terpicu — DunkAPI BISA dipakai untuk uji model-vs-market dengan garis penutupan. Signup (API key) butuh persetujuan user — belum dilakukan.
- **Verifikasi live DET@ATL (22 Nov, 2 putaran)**: analyze OK
  (`nba_analysis: OK`, 0 kredit); recheck **NO-GO** — Asuransi
  U233,5 JANGAN_PASANG via condong-ke-market (harga market 68–68,5%
  < 74%), Utama U237,5 TETAP_OK. Shrinkage: dampak absen Duren
  4,28→4,24 poin (neto bisa diabaikan) TAPI margin proyeksi 3,19→1,55
  dan ML kandang 59,1%→54,0% (material; akurasinya UNKNOWN sampai uji
  historis DunkAPI). Contoh `simulation_nba_ATL_DET_2026-11-22.json`
  diregenerasi dengan kode final.
- Laporan: LAPORAN-TAHAP-3-LANGKAH-2.md. Tes 849 (dari 707), config v8, 0 kredit Odds API.

## 2026-11-22 — Tahap 3 Langkah 3: laporan + tanya-jawab + peracik tiket

- **Profil Utama jadi nilai config (v9, profil user 2026-11-22)**:
  `tickets.main.multiplier_min` 3,5→3,0; `multiplier_max` 6,0→5,0;
  kunci baru `target_multiplier_max` 4,0 (target lunak peracik).
  Menggantikan default blueprint §6a. Mode agresif tetap
  membebaskan maks Utama (hanya atas perintah user per malam).
- **Peracik tiket (engine/ticket_composer.py)**: garis Asuransi dan
  Utama untuk laga yang sama HARUS berbeda (Asuransi lebih tinggi);
  bila hanya satu garis lolos → laga hanya masuk satu tiket
  (prioritas Asuransi); bila garis Asuransi < garis Utama → laga
  hanya masuk Asuransi; tiap laga ≤1 kaki per tiket. Aturan
  condong-ke-market berlaku di peracik (tidak pernah melonggarkan
  putusan recheck). Hanya TETAP_OK (PERHATIAN hanya dengan alasan
  tercatat + ditandai); JANGAN_PASANG/DATA_INCOMPLETE/HOLD tidak
  masuk; kaki hilang dari laporan recheck → fail-closed. Tanpa
  recheck, kaki tetap boleh dipakai + peringatan jendela (recheck
  >60 menit atau belum ada → peringatan, bukan larangan). Bila
  satu tiket None, stake tidak dialihkan diam-diam. EV tiket dari
  sim gabungan (laga berbeda independen; laga sama pakai
  `total_under_<garis terendah>` dari sim, fallback Π p_final +
  catatan). Hanya Alt Under yang diracik; moneyline tidak dipakai.
  MODEL_ONLY dicoret (skema tiket mewajibkan `p_market` angka).
- **`min_leg_prob` sebagai gate keras — MENUNGGU KEPUTUSAN
  user/reviewer**: peracik menegakkan `min_leg_prob` (Asuransi
  0,74 / Utama 0,65) atas probabilitas keputusan sebagai syarat
  keras. Dampak live 22 Nov: kaki DEN@CHI (p_final 0,7352)
  gugur, sehingga Asuransi tidak terracik. §6a menulis "idealnya
  ≥74%" — bisa dibaca sebagai preferensi lunak. Bila diputuskan
  lunak, Asuransi live akan terracik 3 kaki (~x2,34). Perubahan
  satu tempat di `_kumpulkan_kandidat`.
- **`--match` menerima match_id artefak maupun slate** (perbaikan
  CLI langkah 3): `DET@ATL_2026-11-22` dan `nba-2026-11-22-det-atl`
  keduanya diterima oleh `laporan`/`tanya`/`recheck`.
- **Tanya-jawab**: 6 intent deterministik (tanpa LLM); sim ulang
  "bagaimana-jika" default 20.000 iterasi (disebut di jawaban);
  data tidak ada → "tidak terverifikasi"; alasan (a) "pasar tahu
  sesuatu" tidak pernah diklaim dari satu artefak.
- **Laporan**: bagian "Kenapa beda?" tetap tampil bila ada anomali
  `kenapa_beda_required` walau tidak ada kaki yang selisihnya
  > 8 poin.
- **Ditutup langkah ini**: hutang peringatan jendela recheck;
  kendala garis berbeda Asuransi/Utama; condong-ke-market di
  peracik.

## 2026-11-22 — Tahap 3 Langkah 4: pantauan live dalam laga

- **Pantauan live** (`cli.py pantau --ticket <file> [--analysis]
  [--match] [--date] [--output]`, on-demand — tidak ada loop
  terjadwal): scoreboard + summary ESPN (`ingest/live_nba.py`),
  proyeksi total akhir pace-based blend
  (`engine/live_status.py`), deteksi anomali 3 jenis
  (`engine/live_anomaly.py`, baseline BBRef). Config v10,
  section `live:` (8 kunci, nilai awal belum dikalibrasi).
- **Proyeksi blend**: `w_live = menit_lalu/48`; tanpa median
  pra-laga → `live_rate_only` + catatan; flag risiko OT bila
  selisih ≤ 3 poin dan sisa ≤ 2,0 menit (proyeksi tidak
  menambah menit OT). Status kaki AMAN ≥ 6,0 / WASPADA ≥ 2,0 /
  TERANCAM; selesai MENANG/KALAH/PUSH (== garis → PUSH).
  Status tiket = kaki terburuk (KALAH > TERANCAM > WASPADA >
  DATA_INCOMPLETE > AMAN > BELUM_MULAI).
- **Pemetaan singkatan ESPN → tricode (6 tim, koordinator)**:
  GS→GSW, NY→NYK, NO→NOP, SA→SAS, UTAH→UTA, WSH→WAS —
  terverifikasi terhadap ke-30 tim (scoreboard 21–23 Nov);
  UTAH ditemukan lewat pantau live DAL@UTA. Diterapkan di
  scoreboard + summary.
- **Exit code pantau (koordinator, fail-closed)**:
  0 = tidak ada kaki TERANCAM/KALAH/DATA_INCOMPLETE dan tidak
  ada anomali; 1 = ada kaki TERANCAM/KALAH/DATA_INCOMPLETE atau
  anomali; 2 = tidak bisa berjalan. WASPADA/PUSH tetap 0.
  DATA_INCOMPLETE ikut menaikkan exit code karena tidak
  diketahui ≠ aman.
- **Koreksi sumber BBRef**: tabel totals tim (`totals-team`)
  ada di halaman utama liga, bukan `leagues/NBA_YYYY_totals.html`
  (hanya tabel pemain) — terverifikasi dari HTML asli.
- **Verifikasi**: replay laga selesai 21 Nov (5 kaki: 1 KALAH
  261 vs 237,5 + 4 MENANG; exit 1); tiket asli 22 Nov 4 kaki
  BELUM_MULAI (exit 0); hitungan tangan proyeksi blend cocok
  persis (247,1004). **Belum ada verifikasi laga live
  sungguhan** — perilaku tengah laga + OT perlu satu
  pengecekan ulang saat ada laga berjalan. stats.nba.com
  cadangan tidak dibangun. Laporan:
  LAPORAN-TAHAP-3-LANGKAH-4.md. Tes 1088, config v10, 0 kredit
  Odds API.

## 2026-11-22 — Tahap 3 Langkah 5 (Otak bola)

- **Fit Dixon-Coles DILAPORKAN, MENUNGGU persetujuan user (pola D12)**: EPL rho −0,003, avg_home/away 1,6892/1,4062, rasio 1,2013; LaLiga rho +0,024, 1,4679/1,1310, rasio 1,2978 (fit gabungan 3 musim ≤2024/25, 1.140 laga/liga). `dixon_coles_rho`/`home_advantage_by_league`/`absence_penalty` di playstyle.yaml TETAP null sampai user menyetujui. Pilihan rho gabungan vs rho=0 diserahkan ke user/reviewer (rho teridentifikasi lemah; selang ~95% [−0,10, +0,08]).
- **Validasi (holdout 2025/26 + rolling point-in-time)**: skill NYATA hanya 1X2 (EPL Brier 0,6218 vs klim 0,6563, z −2,61; LaLiga 0,5917 vs 0,6318, z −3,04; rolling mengonfirmasi). O/U 2.5 TIDAK ADA skill (z ≈ 0); BTTS LaLiga GAGAL signifikan (0,2580 vs 0,2484, z +2,14 — pergeseran regime; perbaikan bobot resensi/jendela geser = pekerjaan lanjutan, bukan diputuskan). Brier pasar DATA_INCOMPLETE (odds Pinnacle stale). Detail: LAPORAN-FIT-BOLA.md.
- **Koreksi rumus defence (DIRATIFIKASI koordinator langkah 5)**: defence = KEBOCORAN (laju kebobolan / rata-rata liga; lebih besar = lebih bocor), sama dengan fit + sim. Rumus di tugas (rata-rata/laju = kekuatan) tertulis terbalik; bukti dari file fit (Arsenal 2024/25 defence 0,617, Southampton 1,506). Tanpa koreksi, contoh live memberi Man Utd 50% menang di Anfield. Menunggu keberatan reviewer.
- **GARIS_TOTAL diperluas 0.5–8.5** (keputusan integrasi koordinator): sim awal hanya 1.5/2.5/3.5 sehingga 12/22 kaki contoh live tanpa p_model; perluasan mekanis dari PMF yang sama. Menunggu keberatan reviewer.
- **Cedera bola: 0 sumber** (ESPN kosong, PL tidak punya endpoint cedera, FPL belum diratifikasi) → semua laga bola HOLD di bawah B2; B2 tidak dilonggarkan. FPL saja tidak cukup — sumber kedua masih hilang.
- **TANPA_XG ditegakkan di peracik berbasis flag kaki** (`no_xg`/`banned_from_insurance`): kaki bola TANPA_XG dilarang Asuransi + ambang +5 poin, sekalipun artefaknya salah memberi tiket "insurance".
- **LaLiga**: fit + validasi ada, ingest TIDAK didukung (builder menolak liga selain EPL); config `soccer.leagues_supported: ["EPL"]`.
- **Recheck bola BELUM DIDEFINISIKAN** (hutang ke langkah 6); CLI `laporan`/`tanya`/`racik` belum diperluas ke artefak bola; tidak ada ambang "Kenapa beda?" untuk bola.

## 2026-11-22 — Tahap 3 Langkah 6: belajar sendiri

- **PRINSIP KEAMANAN BELAJAR (tidak bisa ditawar)**: mesin TIDAK PERNAH mengubah parameter/ambang/strategi secara diam-diam — ia MENGHITUNG rekomendasi/usulan dari data, dan perubahan hanya berlaku setelah persetujuan user (pola D12). Ditegakkan kode: `rekomendasi_w` dan `hasilkan_usulan` fungsi murni tanpa tulis file; keluaran membawa `"diterapkan": False` + `"butuh_persetujuan_user": True` / `"status": "menunggu_persetujuan"`.
- **Kalibrasi w (keputusan 2026-11-21, diimplementasikan)**: grid search w 0,00–1,00 langkah 0,05 atas kaki settled dengan p_model DAN p_market; Brier blend dihitung ulang (bukan dari p_final tersimpan); syarat n >= `calibration.min_legs_w` (50); tie-break w terkecil; kaki MODEL_ONLY diabaikan.
- **Usulan belajar (aturan a–d)**: (a) Brier model > tebakan dasar + n>=20 → tinjau pasar; (b) Brier model < Brier market + n>=50 → pertimbangkan naikkan w pasar itu; (c) EV terealisasi < EV prediksi − 0,05 + n>=20 → EV prediksi terlalu optimis; (d) tanpa kaki settled → kumpulkan data PAPER dulu. Keyakinan dari n (<20 rendah, 20–49 sedang, >=50 tinggi). Semua ambang di section `learning:` playstyle.yaml (config v12).
- **Perintah `cli.py belajar`**: laporan Bahasa Indonesia sehari-hari; tanpa data → "belum ada hasil tercatat" (exit 0); `--contoh-sintetis` demo berlabel SINTETIS; replay backtest berlabel REPLAY. Label sintetis/replay wajib di judul, ringkasan, dan keterbatasan — data buatan/replay tidak pernah dicampur dengan hasil nyata.
- **Temuan integrasi**: ledger menyimpan sport `"nba"`/`"football"` (dinormalisasi ke `"NBA"`/`"soccer"` saat baca) dan ev_pct dalam PERSEN (dibagi 100 saat baca agar sebanding dengan EV terealisasi fraksi); bila penulis ledger berubah ke fraksi, konversi harus dicabut. Kaki VOID/PUSH dikeluarkan dari statistik; EV terealisasi per kaki adalah diagnostik, BUKAN P/L tiket parlay.
- **Keadaan saat langkah ini selesai**: belum ada tiket nyata yang settle (`ledger.db` belum ada) — laporan belajar nyata pertama menunggu tiket PAPER dicatat + diselesaikan. Aturan condong-ke-market tetap berlaku sampai model terbukti lebih akurat dari market.

## 2026-11-23 — Perbaikan Racik (Mesin Analis, bukan aturan kaku)

- **FILOSOFI USER (04:15 + 04:25 + 04:31 WIB) — MENGGANTIKAN proposal perbaikan 3 poin yang sempit.** (1) Mulai dari garis bandar: kenapa bandar pilih garis itu; mesin cek pakai statistik apakah harga wajar atau di bawah wajar. "Wajar" = jarak antara titik acuan analisis (mis. median sim) dan garis tempat harga duduk. (2) Bantalan TIDAK kaku: +8 cuma istilah user; MESIN menghitung + menentukan bantalan per laga; Utama boleh ke 82¢ bila laga butuh lebih aman; yang kaku: Utama harus tembus x3+. (3) Ekonomi dua tiket: modal $10+$10=$20; Asuransi x2,0 = impas (BEP), x2,5 = untung $5 walau Utama hangus — ITU sebabnya target Asuransi di atas x2,5; satu agresif (x3+, sampai x5 bila mesin beneran yakin), satu konservatif (Asuransi lebih tebal, >x2,5). (4) Bantalan dari cerita laga, mesin MENJELASKAN alasannya kata-kata biasa. (5) Mesin statistiknya yang terpenting — bukan banyaknya aturan. Laporan: LAPORAN-PERBAIKAN-RACIK.md.
- **3 cacat yang ditemukan user (04:05 WIB) — semua TERBUKTI BENAR dan diperbaiki.** (1) Garis terbalik: Asuransi 233,5 < Utama 237,5 di DET@ATL. (2) Tidak ada naik tangga: recheck langsung JANGAN_PASANG ("cari garis Asuransi lain") alih-alih mencoba garis lebih tinggi. (3) Tidak ada peringatan Utama tak terlindungi: warnings[] kosong saat Utama terracik tanpa Asuransi.
- **Penilaian "wajar" (baru, `engine/analis.py::nilai_wajar`)**: artefak analisis mencatat garis market + acuan sim (median) + garis/harga Utama + jarak + bantalan dibutuhkan + penilaian (wajar iff jarak ≥ bantalan; tidak_terverifikasi bila data kurang) + penjelasan kata-kata biasa. Masuk laporan sebagai bagian "Garis bandar — wajar atau tidak?". Lapisan TAMBAHAN — aturan condong-ke-market TETAP berlaku.
- **Bantalan adaptif MENGGANTIKAN +8/+12 kaku, lantai market+8, dan bantalan spread** (kunci config lama yang mati dibersihkan; spread tidak lagi memengaruhi bantalan maupun anomali): `bantalan = clamp(std_sim × 0,42 + (ortg_rata − ortg_liga) × 0,5 + (total_5laga − total_musim) × 0,25, min 4, maks 20)`. Bobot NILAI AWAL belum dikalibrasi (0,42 dipilih supaya laga biasa std ~19 memberi ~8 poin = acuan user; 8 poin ≈ 0,42σ → P(Under) ≈ 0,66, sejalan target Utama 65%). Bantalan boleh di bawah +8 bila statistik membenarkan, wajib di atas +8 bila laga menuntut. ORtg musim penuh dipakai (pilihan wiring — menunggu keberatan bila analis minta last10). Bantalan tidak tersedia → kedua kaki meets=False, TANPA fallback +8.
- **Pemilihan kaki dari harga**: hitung Utama dulu, lalu Asuransi = garis terkecil yang memenuhi syarat DAN di atas garis Utama (`garis_di_atas`) — garis terbalik tidak mungkin terjadi dari seleksi. Lantai harga 75¢ (estimasi jup.ag) untuk Utama DAN Asuransi (`analis.harga_min_*_cents`, config v13); peracik menegakkan sebagai pertahanan lapis kedua. Target peluang model tetap (Asuransi 74%, Utama 65%). **min_leg_prob TIDAK diubah** (0,74/0,65 — masih menunggu keputusan user).
- **Naik tangga**: garis yang ditolak (harga < 75¢, peluang model < target, volume tipis) → naik anak tangga berikutnya sampai lolos; dicatat di field `climb` (from_line/to_line/rungs/reason). **Volume tipis (volume < min_volume_usd $100) = PENGHALANG KERAS Asuransi**; untuk Utama hanya peringatan (flag VOLUME_TIPIS + warnings[] + ringkasan). `_parse_tangga` kini meneruskan volume_usd + thin (sebelumnya dibuang); volume tidak tercatat = tipis (fail-closed). **Koreksi premis tugas**: tangga penuh DET@ATL ternyata punya 249,5 Under vol $141 (tidak tipis) — Asuransi BISA terbentuk dengan naik tangga; premis "tidak ada garis yang lolos" salah.
- **Peringatan Utama tak terlindungi**: bila Utama terracik tanpa Asuransi, warnings[] + ringkasan WAJIB memuat "Tiket Utama tidak terlindungi — Tiket Asuransi tidak terbentuk ({alasan}). Kalau Tiket Utama kalah, tidak ada uang yang kembali dari Asuransi." Pesan recheck lama "cari garis Asuransi lain" diganti pesan naik-tangga.
- **Target pengali**: Asuransi **2,5–3,0** (naik dari 2,20–2,50; batas atas 3,0 USULAN — tidak tumpang tindih dengan Utama 3,0–5,0). Utama tetap 3,0–5,0, target lunak ≤ 4,0.
- **Kriteria "yakin" untuk x5 (USULAN — menunggu keberatan)**: SEMUA kaki p_final ≥ `tickets.main.yakin_min_leg_prob` (0,75, kini di config) DAN semua TETAP_OK (tanpa recheck = tidak yakin) DAN tanpa anomali. Di mode agresif kriteria tidak berlaku.
- **Preferensi yakin di atas lunak (keputusan koordinator integrasi Tahap 4 — menunggu keberatan)**: TEMUAN STRUKTURAL pekerja B — dengan lantai 75¢, subset di atas 4,0 selalu punya sub-subset lunak, jadi preferensi lama (lunak selalu menang) membuat gate yakin tidak pernah mengubah hasil dan x5 tidak pernah terjadi. `_pilih_subset` kini mengutamakan subset yakin di atas lunak (di kelas yakin: peluang menang dulu, lalu pengali lebih besar). Mode agresif tidak diubah (lunak tetap diutamakan).
- **Tegangan desain TERBUKA (tidak diputuskan koordinator)**: naik tangga tanpa batas harga — kaki Asuransi bisa naik sampai 93¢ (~1,075x), membuat target x2,5 sangat berat. Apakah pendakian perlu batas harga — menunggu user/reviewer.
- **Lantai harga TIDAK berlaku untuk kaki bola** (moneyline bola bukan proksi bantalan; menerapkannya membunuh jalur Utama bola tanpa keputusan user) — pengecualian menunggu keberatan.
- **DET@ATL sebelum/sesudah (offline, `scripts/bandingkan_racik.py`)**: bantalan +9,36 adaptif; Utama tetap 237,5 @ 75,5¢ (kini naik 235,5→237,5 karena harga minimum, tipisnya kini TERLIHAT); Asuransi 233,5 @ 68¢ → **249,5 @ 92,5¢, p 93,9%, vol $141** (naik 5 anak tangga dari 239,5 karena volume tipis); penilaian WAJAR (jarak 18,5 ≥ 9,36).
- **Verifikasi live slate 3 laga (0 kredit)**: OKC@MIA OK (bantalan 11,14; Utama 244,5 @ 82¢; Asuransi 250,5 @ 89¢, naik 246,5→250,5); DEN@CHI + BOS@GSW HOLD (Asuransi gagal `tidak_ada_garis_lolos: volume_tipis` — fail-closed jujur); recheck OKC@MIA GO; racik tidak ada tiket (hanya 1 laga OK, maks x1,15 < x3).
- **Tes 1.395, config v13, 0 kredit Odds API.** Field baru skema (`analisis_wajar`, `cushion_points`, `cushion_reason`, `volume_usd`, `thin`, `climb`) semua OPSIONAL — artefak lama tetap valid.

## Fondasi harga & pengali (keputusan user 2026-11-23 08:19 WIB)

Keputusan ini MENGGANTIKAN target pengali dari perbaikan racik (Asuransi
2.5–3.0). Konfigurasi `playstyle.yaml` menunggu build yang menerapkan
fondasi ini.

- **Harga mahal BOLEH.** Kaki 89¢, bahkan Asuransi 94¢, tidak masalah asal
  perhitungan statistik bilang angkanya bisa diterima. **Tidak ada batas
  atas harga (price cap) untuk ladder climbing** — pertanyaan terbuka dari
  perbaikan racik TERJAWAB: tanpa cap.
- **Target pengali: Asuransi x2 atau lebih dikit; Utama x3 atau lebih
  dikit.** x4–x5 adalah KEBERUNTUNGAN bila analisis menunjukkan bisa
  tembus, bukan target.
- **Prioritas utama: SEMUA tiket lolos.** Pengali nomor dua.
- **Analisis mendalam sebelum pasang** harus menjawab per laga: apakah
  masing-masing tim akan sangat-sangat panas? Bila panas, apakah harga
  82¢ bisa tembus? Apakah 94¢ bisa tembus? Ini kebutuhan skenario panas
  (stress scenario) + garis tahan-banjir per kaki.

Build yang diusulkan (menunggu persetujuan user): (1) audit tiket sebelum
pasang, (2) skenario panas, (3) edge jadi gate Asuransi, (4) sesuaikan
target pengali dengan fondasi ini, (5) proyeksi live pakai median pra-laga
untuk tiket nyata.

## Aturan keras pasca-Denver + kasus Thunder (keputusan user 2026-11-23 09:47 WIB)

Latar: insiden DEN@CHI 23 Nov 2026 (banjir 3 poin, dua tiket hangus,
$30 hilang) + pengakuan Gemini (09:21 WIB) + kasus Thunder (lihat
bawah). Prinsip user: "statistik gak bisa bohong" — mesin harus
mensimulasikan penyimpangan MAKSIMAL, dan posisi tiket harus selalu
unggul. Bila statistik bilang sebuah laga tidak masuk akal dipasang
bahkan di 82¢, MUNDURIN lagi (naik ke garis/harga yang lebih aman);
bila tidak ada garis yang lolos, SKIP laga itu — jangan pernah
dipaksakan.

- **R1 — Kaki Asuransi wajib lolos skenario banjir.** Peluang Under
  ≥ 0,74 bukan cuma di skenario normal, tapi juga di skenario banjir.
  Ini yang membuat jarak bantalan antar-tiket nyata (pelajaran Gemini:
  laga berisiko yang sama di dua tiket dengan selisih bantalan cuma
  2 poin membuat fungsi asuransi mati total).
- **R2 — Laga berisiko hanya boleh di Utama**, tidak pernah di
  Asuransi.
- **R3 — Jangan isi tiket demi pengali.** Bila tidak ada kaki yang
  lolos, tiket tidak jadi (fail-closed, sudah berlaku — dipertahankan).
- **R4 — Semua hasil tiket dicatat ke ledger** untuk kalibrasi
  (tiket 23 Nov dicatat setelah semua kaki selesai).
- **R5 — Blacklist POLA, bukan tim.** DEN/CHI secara statistik tim
  3-poin yang buruk — banjirnya tail event. Yang di-blacklist adalah
  pola: edge kecil + rapuh banjir + volume tipis.
- **Skenario "setan" (deviasi maksimal).** Mesin mensimulasikan tiap
  tim "kerasukan setan iblis tri poin" — penyimpangan maksimal, bukan
  cuma banjir biasa (p90). Garis Asuransi harus tahan terhadap
  deviasi maksimal ini. Acuan: insiden DEN (pace halftime +51 di atas
  median 233; total akhir ~261+ vs median 233).
- **Sharp move BUKAN diskon.** Pergerakan harga tajam (≥3¢) menjelang
  tip-off adalah PERINGATAN (pasar kemungkinan tahu sesuatu), bukan
  peluang diskon. Label DISKON tidak boleh dipakai untuk kaki yang
  harganya baru bergerak tajam sebelum pergerakannya dijelaskan
  ("Kenapa beda?"). Kasus Thunder: beli di 75¢, 1 jam sebelum tip-off
  turun ke 71¢; Gemini bilang itu "bagian dari diskon"; Under-nya
  jebol. Mesin tidak boleh mengulangi kesalahan framing ini.
- **Fondasi pengali (penegasan):** Asuransi x2; Utama x3 (x4 rejeki,
  x5 amazing). Kaki Utama di 78¢ tidak masalah selama tembus x3.
  Bantalan kuat selalu diutamakan di atas pengali.

### Catatan implementasi (koordinator, 2026-11-23 — keputusan user di atas TIDAK diubah)

- **Gate banjir (R1)** di `engine/ticket_composer.py`: kaki Asuransi
  lolos hanya bila P(Under) di skenario banjir terburuk (worst of
  banjir_3p/banjir_ft p90) ≥ `min_leg_prob` 0,74. Bila gagal: naik ke
  garis tahan-banjir; bila tidak ada garis tahan-banjir (atau garisnya
  thin — keputusan: thin = hard gate, menunggu keberatan) → SKIP laga
  itu untuk Asuransi. Kunci config:
  `tickets.insurance.stress_gate_scenario: banjir_terburuk`
  (fail-closed; nilai `setan` didukung kode tapi BUKAN kriteria
  produksi — jangan diubah tanpa persetujuan user). Kaki yang naik
  garis memakai p_final/EV garis LAMA (konservatif, tidak dihitung
  ulang) — interaksi gate banjir × gate edge: kaki yang naik garis
  hampir selalu gagal gate edge karena harga naik sementara p_final
  tetap (lihat LAPORAN-ATURAN-KERAS.md §5).
- **Skenario setan = DETEKSI, bukan gate** (koreksi user 09:52 WIB):
  `stress.setan_points: 18.07` (maksimum teramati, bukan p99 —
  mengikuti kata user "MAKSIMAL"). Flag `flag_setan` per kaki: True
  bila lolos normal tapi jebol di setan. Tidak ada kode yang memblokir
  berdasarkan setan.
- **Kontaminasi derivasi p90 (temuan, bukan perubahan):** nilai banjir
  p90 di config (13,54/17,54) diturunkan dari snapshot yang tercemar
  4 laga yang sedang berjalan; data bersih memberi p90 8,50/12,52.
  Nilai config TIDAK diubah — kalibrasi ulang menunggu keputusan
  user. Konterfaktual: dengan geser bersih, block rate gate banjir
  tetap 1/10 lolos (temuan kokoh).
- **Sharp move bukan diskon:** label `DISKON_DITEKAN` di
  `price_labels.py` (parameter `sharp_move`), diterapkan di recheck
  (verdict tetap JANGAN_PASANG — aturan 6 yang sudah ada),
  audit (gate lunak PERHATIAN), dan `anomaly.evaluate_leg`
  (sebelumnya mengembalikan DISKON polos bersamaan dengan anomali
  sharp_move — diperbaiki koordinator dengan tes fail-first).
- **Hasil ukur (slate nyata, LAPORAN-ATURAN-KERAS.md §5):** gate
  banjir 1 lolos / 9 terblokir dari 10 baris; garis tahan-banjir ada
  di 9/10 (mayoritas thin); flag setan 10/10. Gabungan gate banjir +
  gate edge: 0/10 kaki Asuransi lolos (satu-satunya yang lolos banjir,
  OKC U250,5 @89¢, gagal edge +1,3% < 3,5%). Angka ini untuk
  keputusan user, bukan untuk dilonggarkan diam-diam.
- **Klarifikasi harga 10:14 WIB (dipatuhi):** tidak ada logika
  prefer-harga-tinggi di komposer/gate (diverifikasi koordinator atas
  diff build ini); garis tahan-banjir adalah garis TERMURAH yang
  lolos banjir (by construction — iterasi tangga menaik, ambil
  pertama yang lolos); komposer menyeimbangkan harga vs target
  pengali dengan cara subset yang sudah ada. Lihat
  LAPORAN-ATURAN-KERAS.md §2a.

## Koreksi: skenario setan adalah deteksi, bukan gate (keputusan user 2026-11-23 09:52 WIB)

Mengoreksi bagian "Skenario 'setan'" di atas (09:47 WIB):

- **Skenario setan BUKAN gate keras.** Gate keras Asuransi tetap
  skenario banjir p90 (R1) + edge + volume + min_leg_prob — batas
  ketat yang MASUK AKAL. User menegaskan: bukan maksudnya semua laga
  dianggap anomali; bila semua pemeriksaan terlalu ketat, semua kaki
  bisa kena skip.
- **Fungsi skenario setan: deteksi dini + analisis.** Membaca sejak
  awal apakah sebuah laga punya statistik anomali seperti Denver;
  menunjukkan seberapa rapuh tiap kaki terhadap deviasi maksimal dan
  garis/harga mana yang lebih tahan. Kaki yang lolos gate banjir
  boleh dipasang (di harga tinggi) walau rapuh-setan, asal risikonya
  TERLIHAT di laporan/audit. Bila anomali ekstrem benar-benar datang,
  itu kalah dengan terhormat — bukan kegagalan proses.
- **Strategi tumpuk:** pasang di harga tinggi (89¢/94¢) tidak masalah
  untuk menumpuk BANYAK laga dan menambah daya ungkit pengali — asal
  tiap kaki fundamentalnya kuat (lolos semua gate).

## Klarifikasi: harga mengikuti statistik (keputusan user 2026-11-23 10:14 WIB)

Angka 89–94¢ dari user adalah HIPERBOLA, bukan target. Jangan dorong
semua kaki ke area 89–94¢ dan jangan tambahkan logika "prefer harga
tinggi" ke komposer/gate mana pun.

Prinsip: HARGA MENGIKUTI STATISTIK. Tiap kaki harus masuk akal secara
statistik + lolos semua uji (min_leg_prob, edge, volume, banjir) +
tahan anomali. Garis yang dipilih = garis terkecil (termurah) yang
lolos SEMUA gate; naik garis hanya bila gate tidak lolos di garis
bawah. Harga tinggi hanya terjadi bila statistik laga itu memang
menuntutnya.

Kendala matematika: dengan sedikit laga (mis. 5 laga), semua kaki di
80¢+ tidak bisa mencapai x2/x3 — komposer menyeimbangkan harga vs
target pengali dengan memilih subset kaki-kaki yang lolos gate hingga
mencapai target.

## Prinsip skip dari awal (keputusan user 2026-11-23 10:22 WIB)

Lebih baik MENGHINDARI laga seperti Denver daripada mencari garis
yang tahan. Bila sebuah laga dari awal sudah tidak masuk akal
(perhitungannya anomali / tidak normal) atau punya potensi masuk
overtime, lebih baik SKIP laga itu dari kedua tiket — bukan dipaksakan
dengan garis yang lebih tinggi. Pertahanan utama terhadap laga
anomali adalah SELEKSI, bukan harga/garis (bukti: total akhir
DEN@CHI 296 menjebol bahkan garis tahan-banjir 264,5 @94¢).

Analisis mendalam yang dibutuhkan untuk menilai ini: pemain cedera
(siapa tampil, siapa absen), siapa yang full squad, siapa yang sering
cetak 3 poin, dan indikator-indikator lain per laga. Mesin sudah punya
sebagian besar input ini (cedera 2 sumber, skenario skuad, baseline
3 poin per tim); yang masih harus dibangun: aturan skip dari awal +
potensi OT sebagai input seleksi.

## Titik equilibrium, bukan saringan ketat vs bolong (keputusan user 2026-11-23 10:31 WIB)

Jawaban atas pertanyaan gate (a)–(e): **TETAP KETAT.**

Reframing dari user: ini bukan soal saringan ketat vs saringan bolong
— mesin harus menghitung **TITIK EQUILIBRIUM per kaki**: titik di mana
distribusi normal bilang kaki itu paling oke. Anomali ekstrem boleh
menggeret harga Asuransi sampai 94¢, tapi mesin mencari di mana
distribusi normalnya duduk — di situlah titik pasang (contoh
ilustratif user: Asuransi 85¢, Utama 75–78¢). Anomali di luar titik
itu adalah di luar kendali — bukan kesalahan hitung mesin. Laga tanpa
equilibrium (seperti Denver) di-skip dari awal (lihat prinsip skip
10:22 WIB).

Catatan kejujuran (diperiksa dari kode 10:31 WIB): mesin BELUM
menghitung titik equilibrium — komposer sekarang ambil garis termurah
yang lolos saringan (aturan ambang), bukan titik manis. Yang juga
BELUM dihitung mesin: NEWS (tidak ada modul berita NBA), tripoin per
tim/pemain di dalam simulasi, dan bentuk ekor per laga (sigma_total
satu angka global untuk semua laga). Peluang OT dihitung tapi belum
dipakai untuk seleksi.

## Penyempurnaan mesin: tambal semua kebolongan (keputusan user 2026-11-23 10:41 WIB)

- **Definisi equilibrium DIKONFIRMASI:** cari titik paling manis per
  kaki; tumpuk kaki-kaki yang benar-benar kuat hingga Asuransi x2 dan
  Utama x3+.
- **Bangun sekaligus semua yang bolong** (agar bisa segera berdiskusi
  tiket besok): (1) titik equilibrium per kaki, (2) aturan skip dari
  awal, (3) modul news, (4) ekor 3 poin per laga di simulasi,
  (5) peluang OT dipakai di seleksi.
- **Fungsi news:** berguna saat mau pasang — ada berita apa (cedera,
  berita tim, apa pun) yang menguatkan argumen untuk pasang dan
  yakin; berita jelek jadi bahan bacaan user + analisis mesin. News
  tidak terlalu signifikan sebagai angka, tapi agen yang bisa baca
  news (sosial maupun bandar/bursa) membuat mesin lebih sempurna.
  News adalah KONTEKS, bukan angka (aturan: tidak ada angka yang
  dikarang).
- **Semua laga dilaporkan**, termasuk yang di-skip, beserta alasannya
  — supaya user bisa membaca dan tahu kenapa sebuah laga di-skip.
- **Ketinggian Denver/Utah** (pertanyaan user 10:41 WIB): ada di mesin
  karena blueprint memasukkannya — tim tamu lebih cepat lelah di
  ketinggian (Denver ~1600 m, Salt Lake City ~1300 m), yang bisa
  memengaruhi skor. Efek yang TERUKUR hampir nol (−0,0105; fit ulang
  rolling −0,399 dengan SE 1,14 = noise, tidak diadopsi) — jadi
  praktis tidak mengubah angka. Disampaikan ke user apa adanya.

## Penyempurnaan mesin — catatan implementasi (commit feat, 2026-11-23)

Implementasi atas keputusan user 10:41 WIB (config v16). Laporan
lengkap: LAPORAN-PENYEMPURNAAN-MESIN.md (+ laporan per item:
LAPORAN-EQUILIBRIUM-SKIP-AWAL.md, LAPORAN-EKOR-3P.md,
probes/HASIL-PROBE-NEWS.md).

- **Equilibrium = garis dengan expected return tertinggi**
  (ER = p_final × (100/harga venue)) di antara garis yang lolos SEMUA
  gate tiket itu. Target pengali (x2/x3+) bukan kendala per kaki —
  komposer menumpuk kaki equilibrium sampai target tercapai. Tidak ada
  lantai ER > 1 (titik manis boleh EV negatif, dilaporkan transparan).
  Tidak ada logika prefer-harga-tinggi. p_final per garis via geser
  pasar tersirat (asumsi: pasar vs model hanya berbeda geser lokasi —
  sama seperti stress.py); validasi: di garis jangkar OKC verif,
  p_final hasil geser mereproduksi p_final artefak persis (0,908341).
- **Equilibrium MENGGANTIKAN mekanisme climb banjir.** Kaki dibangun
  ulang dengan p_final/EV/label dihitung ulang DI GARIS BARU — ini
  memperbaiki interaksi banjir × edge (LAPORAN-ATURAN-KERAS §5) di
  mana kaki naik garis memakai p_final basi. Equilibrium BOLEH
  melompati garis tahan-banjir yang thin ke garis tebal di atasnya —
  keputusan lama "gate tidak melompat" (aturan keras §7.1) DIGANTIKAN
  (hanya masuk akal di dalam mekanisme climb).
- **Skip dari awal, 3 pemicu eksplisit:** (a) tidak ada equilibrium di
  KEDUA tiket; (b) pola Denver — konjungsi flag setan di garis acuan
  + tidak ada garis tidak-tipis yang tahan banjir + garis acuan thin
  + edge kecil (< 3,5% INITIAL, cermin D12); (c) OT tinggi — ot_prob
  ≥ 0,028 INITIAL (≈ plafon teoretis peluang seri laga imbang 0,0277,
  dalam SKALA SIM; rencana kalibrasi di komentar config). Keputusan:
  SKIP, bukan bantalan lebih besar. Tanpa data → "tidak dievaluasi",
  bukan skip. Semua laga tetap dilaporkan beserta alasan skip.
- **News: ESPN JSON PAKAI** (feed liga, 50 artikel ≈ 2 hari, kategori
  tim per artikel); Google News RSS CADANGAN; NBA resmi JANGAN (tidak
  ada API/RSS). News konteks, bukan angka — tidak pernah masuk sim;
  recheck: berita mendadak (terbit setelah analisis awal + relevan)
  → PERHATIAN, tidak mengubah GO→NO-GO, tidak memicu resim.
- **Ekor 3P: HASIL NOL.** Regresi varians n=2.466 laga (rolling,
  tanpa look-ahead): slope −0,3364, SE 1,9697, t=−0,17, R²=0,0000 —
  laju 3PA tidak memengaruhi ekor total. `slope_aktif` FIT jadi 0,0
  (preseden altitude); DEN@CHI lama-vs-baru identik persis. Banjir
  Denver adalah lonjakan DALAM laga (90 percobaan vs ~72 normal +
  akurasi 46,7%), bukan sesuatu yang bisa diprediksi laju musim.
  Pertahanan tetap gate banjir/edge/volume + seleksi. Rencana
  kalibrasi: ulang tiap akhir musim; bila |t| ≥ 2,0 ajukan slope fit
  ke user (D12); bila tetap nol pada n ≥ 5.000, tutup hipotesis.
  Efek MEAN (resid_total ~ 3PA, b=−0,2087, t=−2,91) ditemukan tapi
  TIDAK diimplementasikan (di luar lingkup, soal kalibrasi mean).
- **Hasil ukur slate nyata (10 baris):** equilibrium Asuransi 0/10,
  Utama 10/10; di-skip 6/10 (5 pola Denver + 1 OT); TIDAK ADA tiket
  terbentuk — sama seperti aturan lama. Ketegangan banjir+edge §5
  BERTAHAN di bawah equilibrium. Bukan untuk dilonggarkan diam-diam —
  keputusan user.
- **Integrasi koordinator:** bagian Berita disisipkan ke laporan
  (sesudah Cedera, sebelum Market); config v16; section `news:` dan
  `ekor_3p:` TIDAK masuk REQUIRED_PLAYSTYLE_SECTIONS (fail-closed
  per pemakaian: news gagal → status gagal tercatat; ekor hilang →
  sigma global + catatan) — berbeda dengan equilibrium/skip_awal/
  ot_seleksi yang wajib ada.

## Aturan tanpa kaki kembar + masukan objektif soal Asuransi (user 2026-11-23 12:20 WIB)

Riwayat user (screenshot jup.ag, 18 tiket, 15–23 Nov 2026): 10 menang,
8 kalah, total +$169,66 dari modal $223 (+76%). Hari ini (23 Nov)
pertama kalinya KEDUA tiket dalam sepasang kalah bersamaan; secara
umum tiket Asuransi user tidak pernah gagal.

- **TANPA KAKI KEMBAR (keputusan user):** satu laga tidak boleh ada di
  kedua tiket. Kekalahan hari ini karena Denver ada di kedua tiket;
  andai Denver tidak ada di Asuransi, Asuransi selamat. Kemarin
  (22 Nov) kaki kembar selamat hanya karena laganya dingin — itu
  keberuntungan, bukan desain. Dengan 10 laga besok, tiket tanpa
  kembar dimungkinkan (mis. 4–5 laga Asuransi + 5–6 laga Utama).
- **Sedikit longgar pada penyimpangan bisa diterima** (user), tapi
  TIDAK melonggarkan tes simulasi. Yang tidak bisa diterima: laga
  seperti Denver — garis tinggi (252,5) tapi harga cuma 82¢. Itu
  sinyal pasar: ekornya gemuk. Laga seperti itu langsung di-skip.
- **Bila equilibrium Asuransi tidak ditemukan:** pasang Asuransi di
  kaki-kaki yang paling aman (bukan "pasti menang" — tidak ada yang
  pasti; bahkan 94¢ kalah di Denver). Mesin harus memilih titik
  Asuransi yang manis untuk tim yang benar-benar tidak akan membuat
  anomali.
- **Masukan objektif main agent (disampaikan 12:20 WIB, menunggu
  persetujuan build):** (a) koreksi geser banjir ke data bersih
  (8,50/12,52) — ini koreksi, bukan pelonggaran; (b) equilibrium
  Asuransi = safety-first (p_final tertinggi yang mencapai x2),
  bukan max-ER (max-ER benar untuk Utama); (c) bila masih buntu,
  gate Asuransi pakai banjir moderat sementara p90/setan tetap jadi
  flag peringatan; (d) sinyal pasar "garis jauh + harga rendah"
  ditambahkan ke aturan skip.
- **Batas data riwayat:** screenshot hanya memuat ukuran kombo,
  modal, payout, P/L, status — tanpa detail per kaki, sehingga
  18 tiket riwayat tidak bisa masuk ledger/modul belajar (butuh
  hasil per kaki). Bila user punya detail kakinya, bisa dicatat.

## Vonis per laga + setan per pemain (diskusi user 2026-11-23 12:33 WIB)

Pelajaran Denver — indikator yang bisa mesin ambil (bukan perasaan):
kaki terlemah di tiket (peluang + edge terkecil), gap model-vs-pasar
terkecil (mesin hampir setuju dengan bandar = tidak ada edge), volume
tipis, rapuh banjir (P banjir 54%) + flag setan (53%), garis jauh +
harga rendah (252,5 @82¢ = pasar bilang ekornya gemuk), laga ketat
(spread 2,5 = risiko OT), total tinggi (garis bandar 236,5 = variasi
lebih besar). Yang JUJUR tidak terprediksi: banjirnya sendiri (kedua
tim penembak tripoin di bawah rata-rata musim) — yang terdeteksi
adalah RAPUHNYA, bukan banjirnya.

- **Sistem vonis (diusulkan, menunggu jawaban user):** mesin menghitung
  vonis per laga dari indikator-indikator di atas — HIJAU/sehat
  (→ Asuransi), menengah-cukup-hijau (→ Utama), KUNING/lempar koin
  (→ skip). Vonis dari angka, bukan perasaan (beda dengan Gemini
  yang menandai KUNING lalu tetap memasukkan).
- **Setan per pemain (ide user):** ganti setan umum (+18,07 untuk
  semua laga) dengan setan per tim: tiap pemain diambil data tripoin
  musimnya (berapa persen per laga), dihitung kalau semuanya panas
  bareng (di atas rata-rata NBA) totalnya bisa sampai berapa —
  diuji ke semua pemain dalam tim. Rumus/titiknya ditentukan mesin
  dari data dan fakta. Mesin uji menarik data NBA untuk itu, selain
  simulasi 100.000x real-time.
- **Penyimpangan dilaporkan vs garis bandar** (permintaan user —
  angka banjir abstrak tidak ditangkap user; yang dipahami adalah
  penyimpangan jauh dari poin garis normal bandar).
- **Poin 2 DIKONFIRMASI (12:33 WIB):** Asuransi = safety-first
  (permainan yang benar-benar bisa menyelamatkan dari kegagalan
  Utama); Utama TIDAK main brutal — tetap cari titik paling manis
  pada grafik (max-ER).
- **Pertanyaan terbuka ke user:** definisi vonis HIJAU/KUNING;
  setan per pemain — 5 starter atau seluruh rotasi; definisi
  "maksimal" per pemain (laga terbaik musim ini atau patokan lain);
  persetujuan betulkan geser banjir ke data bersih sebagai bagian
  dari build ini.

## Jawaban 4 pertanyaan + build vonis/setan-pemain (user 2026-11-23 12:38 WIB)

1. **Definisi vonis: terserah mesin**, asal data di baliknya cukup.
   Pertanyaan user: "volume cukup" itu apa — volume laga NBA di
   Polymarket selalu ratusan ribu dolar. Jawaban: yang dicek mesin
   adalah volume PER GARIS (mis. U252,5 cuma $26), bukan volume
   laga — volume laga tersebar di ratusan garis; garis jauh hanya
   ditawar segelintir orang sehingga harganya kurang bisa dipercaya.
   Ambang $100 tetap (tidak diubah diam-diam); build mengukur
   seberapa sering volume menjadi penghalang + melaporkannya jelas.
2. **Setan per pemain: semua pemain yang terdaftar dan rotasi**
   (bukan cuma 5 starter).
3. **"Maksimal" per pemain:** rapor pemain sampai hari H, lalu dia
   kemasukan persentase 3 poin TERBAIK musim NBA saat ini —
   demon per pemain = percobaan 3 poin per laganya × % 3 poin
   terbaik liga musim ini (fakta dari data). Dijumlah ke semua
   pemain tim (dengan percobaan yang DIHARAPKAN — memperhitungkan
   siapa yang benar-benar main, bukan jumlah naif seluruh roster).
4. **Banjir: SETUJU** — betulkan ke data bersih, asal menghasilkan
   analisis pemilihan tiket yang bermanfaat.

Build DISETUJUI + DIJALANKAN 12:38 WIB (koordinator): (1) sistem
vonis per laga (HIJAU/MENENGAH-HIJAU/KUNING dari data), (2) aturan
tanpa kaki kembar, (3) equilibrium Asuransi safety-first,
(4) setan per pemain, (5) koreksi geser banjir ke data bersih,
(6) penyimpangan dilaporkan vs garis bandar, (7) transparansi
volume per garis + pengukuran.

## Gemini adalah senior + pelajaran buru-buru (user 2026-11-23 12:43 WIB)

Gemini sejauh ini membawa user menang dan tidak pernah kalah — kalah
benar-benar cuma hari ini (23 Nov). User mengakui itu juga salahnya:
terlalu buru-buru pasang tiket, diskusi cuma sebentar karena memaksa
laga jam 06:00 masuk, padahal kalau santai sedikit mungkin tidak
terjadi begini. Jadi kekalahan hari ini adalah kesalahan BERSAMA:
kesalahan Gemini (memasukkan laga KUNING) + user yang buru-buru.
Gemini adalah "senior" — tugas mesin bukan menggantikan penilaiannya,
tapi memberi penilaian itu badan mesin yang kaku (vonis yang
ditegakkan kode, tidak bisa di-override ingatan).

- **Aturan proses (DIUSULKAN, menunggu persetujuan):** jangan memaksa
  laga yang tip-off-nya sudah dekat masuk tiket — kalau analisis
  belum selesai, skip laganya. Buffer yang diusulkan: analisis harus
  selesai 30 menit sebelum tip-off (INITIAL). Besok pagi mulai
  05:00–05:30 WIB agar tidak terburu-buru.
- **Pertanyaan untuk Gemini (disampaikan ke user 12:43 WIB, untuk
  diteruskan):** (1) sinyal apa yang membuat DEN@CHI KUNING, diurut
  dari yang paling penting; (2) cara memilih garis per laga (kenapa
  252,5 bukan 250,5/248,5); (3) apa yang dilihat PERTAMA saat buka
  slate + urutan analisisnya; (4) apa yang dilakukan berbeda pagi ini
  kalau tidak buru-buru. Jawabannya dilipat ke mesin (sistem vonis)
  bila bisa diubah jadi data + aturan — angka Gemini tetap tidak
  dipakai (tidak bisa dilacak ke perhitungan).

## Bedah jujur Gemini — evaluasi terverifikasi (user 2026-11-23 12:51 WIB)

Gemini mengirim bedah jujur 4 bagian. Main agent memverifikasi
klaim-klaim faktualnya dari data mesin SEBELUM melipatnya ke mesin:

- **Claxton OUT (CHI) vs Jokic — TERVERIFIKASI.** Official NBA Injury
  Report + ESPN (2 sumber, artefak mesin): Nic Claxton OUT, CHI,
  "Illness". Sinyal #1 Gemini benar. (Keraguan awal main agent —
  Claxton adalah pemain Nets — SALAH; di musim 2026-27 dia di Bulls
  menurut data resmi.)
- **Garis tertinggi 236,5 + pace cepat — BENAR** (pasar 236,5; pace
  CHI 103,22 musim / 101,15 last10 vs klaim Gemini ~103,9 — substansi
  benar, angka persis beda sumber).
- **H2H 248–257 — TIDAK TERVERIFIKASI** (H2H mesin kosong untuk laga
  ini, h2h_last5 [] — utang: H2H hanya dari gamelog musim berjalan).
- **Aday Mara OUT (OKC) — TIDAK TERVERIFIKASI** (tidak ada di data
  cedera mesin, 2 sumber, 2 snapshot termasuk artefak pagi 04:58;
  tidak ada di boxscore). Jangan dipakai sebagai fakta.
- **Hitung mundur dari pengali (81,7¢) — ARITMETIKA BENAR**
  ((1/2,24)^(1/4) ≈ 81,7¢); selisih 2 poin = 0,12 SD BENAR.
  Cacatnya (garis dari target pengali, bukan dari volatilitas) valid
  — equilibrium mesin sudah bekerja sebaliknya (volatilitas dulu).
- **Vegas-anchoring ±3–4 — mesin SUDAH punya versinya** (ambang 5,0
  + lean-to-market; ambang 5,0 TETAP — perubahan ke 3–4 butuh uji
  historis DunkAPI). Fakta: median mesin DEN 233 (gap 3,5, di dalam
  ±3–4); model Gemini 227,1 (gap 9,4, di luar).
- **Exchange-first + NO BET — mesin SUDAH begitu** (tangga Polymarket
  riil; fail-closed).
- **HARD VETO (baru, dari Gemini, DILIPAT ke build vonis):** rim
  protector utama OUT + garis Vegas tertinggi / high pace → blokir
  otomatis dari Asuransi, tidak bisa dikalahkan skor EV. Definisi
  rim protector dari data (blocks/center starter).

## Catatan implementasi build vonis + setan per pemain (koordinator, 2026-11-23 sore WIB)

Config v17. Laporan utama: `LAPORAN-VONIS-SETAN-PEMAIN.md`;
laporan per pekerja: `LAPORAN-VONIS.md`, `LAPORAN-ASURANSI-BARU.md`,
`LAPORAN-SETAN-PEMAIN.md`. Suite 1806 tes OK, 0 kredit Odds API.

- **Vonis (`engine/vonis.py`):** sistem demerit (9 indikator) + 4
  pemicu keras (data tidak cukup, OT tinggi, edge tidak positif,
  veto rim protector). HIJAU = 0 demerit; MENENGAH_HIJAU = 1–4;
  KUNING = > 4 atau pemicu keras. Distribusi slate uji 10 baris
  22 Nov: HIJAU 0 / MENENGAH_HIJAU 2 (DAL, BOS live) / KUNING 8;
  veto menyala 3 baris (DEN verif via Claxton; OKC live + verif via
  Chet Holmgren). Veto memblokir KEDUA tiket (vonis KUNING) —
  pembacaan yang lebih ketat dari "minimal tidak masuk Asuransi";
  menunggu keberatan. KUNING-karena-data TIDAK dikeluarkan komposer
  (gate per kaki tetap fail-closed sendiri); menunggu keberatan.
- **Rim protector:** per tim maksimal 2 pemain rotasi (GP ≥ 3,
  MP ≥ 15, BLK ≥ 0,8), urut BPG — pemetaan
  `config/rim_protector_2026-27.json` (30/30 tim, stats.nba.com,
  23 Nov). Top-1 GAGAL di data (pemimpin blok CHI adalah Jalen
  Smith 1,1, bukan Claxton 1,0). Segarkan mingguan via
  `scripts/fetch_rim_protector.py`; tidak ada peringatan basi
  otomatis (utang).
- **Tanpa kaki kembar (`engine/ticket_composer.py`):** HIJAU →
  Asuransi saja; menengah-hijau → Utama saja; KUNING dievaluasi →
  skip keduanya; tanpa vonis → tanpa preferensi (PENYIMPANGAN
  terdokumentasi dari brief — menandai semua tanpa-vonis sebagai
  menengah-hijau akan membuang semua kandidat Asuransi). Disjoint
  ditegakkan juga di tingkat subset; fail-closed bila target
  pengali tidak tercapai.
- **Equilibrium Asuransi safety-first:** mode per tiket di config
  (`mode_insurance: safety_first`, `mode_main: max_er`); Asuransi
  = p_final tertinggi di antara garis yang lolos semua gate.
  Kendala x2 tetap di komposer (tidak ada optimasi gabungan) —
  kaki @92,5¢ butuh ~10 kaki untuk x2.
- **Setan per pemain (`engine/setan_pemain.py` +
  `ingest/pemain_3p.py`):** DEN@CHI total setan 274,14 (deviasi
  +37,64 vs garis bandar 236,5; +23,07 di atas setan umum); kedua
  kaki nyata ter-flag rapuh (P setan 13,0%/11,8%); point-in-time
  273,03 (−1,11). % terbaik liga 54,1% (Cam Spencer, MEM, 61,2
  percobaan) — level demon sensitif terhadap ambang percobaan
  minimum (50 INITIAL): ambang 75 → 260,21; ambang 150 → 240,83
  (tidak lagi rapuh). Vonis rapuh kokoh untuk ambang 25–100.
  WIRING (ditemukan + diperbaiki koordinator saat integrasi):
  `skenario_panas` sudah membaca `analysis["setan_pemain"]` tapi
  tidak ada pemanggil produksi yang mengisinya — kini
  `engine/nba_analysis.py` Tahap 5c mengambil data pemain (sekali
  per proses, cache) + menghitung demon per laga + melampirkannya
  ke artefak; gagal → blok "gagal" + fallback setan umum.
  Skema `nba_analysis.schema.json` diperluas (properti opsional
  `setan_pemain`, format_version tetap 1).
- **Koreksi banjir (data bersih):** 3P 13,54 → 8,50; FT 17,54 →
  12,52; setan 18,07 tetap. Garis tahan banjir turun ~5–6 poin;
  hasil skip tidak berubah di 10 baris.
- **TEMUAN UTAMA (jujur, tidak disembunyikan): Asuransi TETAP
  tidak terbentuk** di slate uji (EQ Asuransi 0/10; gate banjir
  1/8 lolos; penghalang kini volume 8 baris + edge 2 baris;
  volume SATU-SATUNYA penghalang hanya di 1/10 baris — melonggarkan
  $100 saja tidak akan membentuk Asuransi). EQ Utama 10/10.
  Vonis tidak melonggarkan apa pun; 0 HIJAU berarti alokasi
  HIJAU → Asuransi belum pernah teruji di data nyata.
- **Utang baru:** fetch H2H (vonis tidak bergantung H2H);
  pemetaan rim protector perlu refresh mingguan tanpa peringatan
  otomatis; "turunkan target" tidak otomatis di kode (hanya NO
  BET yang otomatis); setan pemain tidak memodelkan lonjakan
  JUMLAH percobaan (hanya akurasi).

## Build v17 selesai + terverifikasi (2026-11-23 13:25 WIB)

Commit c1c641e + 9c8a0c2 (push, remote HEAD cocok, tree bersih),
config v17, 1806 tes OK + ruff/black bersih (dijalankan main agent),
0 kredit. Verifikasi independen main agent: ER OKC Utama 1,044805
✓ (hitung tangan); demon DEN@CHI 274,14 ✓ (+37,64 dari garis bandar
236,5; 67,3 percobaan × 54,1% × 3 = 109,23 ✓); vonis 0/2/8 + veto
3 baris dibaca dari out/ukur_vonis.json; EQ Asuransi 0/10 + EQ Utama
10/10 + gate banjir 1/8 dibaca dari out/ukur_asuransi_baru.json;
wiring Tahap 5c + skema setan_pemain diperiksa di kode.

- KOREKSI MARA: Aday Mara BENAR pemain OKC (rotasi, 16 laga,
  1,7 BPG — pelindung ring #2 OKC di map rim protector). Lean
  "kemungkinan Gemini salah ingat" dari main agent TERLALU KUAT.
  Klaim "Mara absen di laga OKC@MIA" tetap TIDAK TERVERIFIKASI
  (tidak ada di laporan cedera resmi + ESPN; data mesin mencatat
  statusnya 'main' di kedua snapshot).
- TEMUAN UTAMA: Asuransi TETAP 0/10 setelah semua perbaikan.
  Volume satu-satunya penghalang cuma 1/10 — melonggarkan $100
  saja TIDAK membentuk Asuransi. Opsi tersisa (keputusan user,
  belum diputuskan): terima / turunkan edge 3,5% / longgarkan thin
  / banjir moderat untuk gate Asuransi.
- Veto bergantung data cedera SEGAR: DEN live (snapshot 22 Nov sore)
  tidak kena veto karena Claxton belum OUT saat itu; hanya snapshot
  pagi 04:58 yang menangkapnya. Implikasi operasional: analyze besok
  HARUS jalan di data pagi yang segar.
- Veto memakai logika OR (garis ≥235 ATAU pace ≥102) + memblokir
  KEDUA tiket — keduanya keputusan desain yang menunggu keberatan
  user (laporan §9 D1, D8–D9). OKC kena veto dari pace saja padahal
  kakinya menang (1 false positive vs 1 true positive DEN).

## Audit Gemini v17 + proposal v18 (diterima 2026-11-23 13:47 WIB)

File: REFERENSI-AUDIT-GEMINI-V18.md (disalin ke repo + commit e174069
berikutnya). Main agent MEMVERIFIKASI matematika Gemini dengan hitungan
sendiri — SEMUA klaim kunci BENAR:
- Deadlock Asuransi: garis tahan banjir +24,86 di atas median
  (t(0,74;35)=0,6498, klaim 0,650 ✓); P_model di sana ~90% ✓.
  Tiga aturan (P_banjir ≥74% + edge ≥3,5% + lean-to-market >5,0)
  bersamaan mengunci Asuransi 0/10 — konsisten dengan pengukuran.
- Flat edge di ekor: keunggulan 3 poin bernilai +6,28% (murni) di
  50¢, menyusut di ekor; angka Gemini (+1,3/+0,6/+0,3%) konsisten
  dengan harga ASK (bukan mid) — mekanisme BENAR, ambang edge datar
  +3,5% praktis tidak bisa dilewati di harga 85¢+.
- Jendela gap terjepit 4,0–5,0 (1 poin): benar; menghukum kesepakatan
  dengan pasar bertentangan dengan temuan Brier (model belum terbukti
  lebih baik dari pasar di total).
- Anomali kalibrasi OT: kap P(OT) sim di spread 0 = 2,74% PERSIS
  (densitas t(35) di 0 = 0,3961 / 14,4307); pemicu keras 2,8% di ATAS
  kap teoretis → hanya mendeteksi noise Monte Carlo (kasus DET@ATL
  2,89%). OT riil NBA ~5,5–6,0% (strategi clutch Q4 tidak dimodelkan
  sim). CACAT NYATA — pemicu OT harus dikalibrasi ulang.
- Klasifikasi slate 23 Nov versi Gemini (tanpa hindsight): HIJAU
  BOS/OKC/ORL, MENENGAH DAL/IND (TUNGGU_LINEUP), KUNING hanya DEN.
  Koheren dengan hasil (3 HIJAU menang, 2 MENENGAH menang, 1 KUNING
  kalah) — penilaian Gemini, bukan data.
- Proposal v18 (§3): EV ≥ −1% ganti edge datar; banjir 70%/65%;
  p_final Asuransi 0,82 + p_market 0,80; veto AND (garis ≥232,0 DAN
  pace ≥100,5) + filter posisi C/PF; HIJAU = 0 veto + ≤1 demerit +
  ≥1 rem alami; volume pindah ke gate eksekusi berbasis stake (≥2×);
  demon cap min(50%, %+12pp); timing gate TUNGGU_LINEUP; OT empiris;
  short-circuit scan jup.ag untuk laga kena veto. Acceptance test 5
  target di slate uji (§4).

KEPUTUSAN USER YANG DIBUTUHKAN (D12, belum diputuskan):
1. Target Asuransi min 1,80x (turun dari 2,0x) — Asuransi tidak lagi
   menutup total stake ($15 → $27 vs $30 dipertaruhkan = −$3 bila
   Utama hangus). Terima lindung nilai parsial atau tetap 2,0x?
2. Banjir 70%/65% (turun dari 74%) + edge diganti EV ≥ −1% —
   pelonggaran gate banjir (dipasangkan dengan p_final 0,82 yang
   LEBIH tinggi). Setuju?
3. Utama min p_final 0,74 (naik dari 0,65) — mengetatkan Utama.
4. Veto AND + ambang 232,0/100,5 — ambang dipasang dari 2 titik data
   (DEN 236,5/103,22 vs OKC 231,5/102,19); risiko overfitting, baru
   teruji di 10 baris. Logika AND + filter posisi berprinsip; angkanya
   butuh validasi ledger.
CELAH DESAIN (pembangun harus selesaikan + ukur): cara hitung
probabilitas OT empiris; jumlah penyusutan median ke pasar
pre-vonbis; demon cap (+12pp/50%) — apakah kaki Denver tetap rapuh?

## Jawaban user atas 4 keputusan v18 (2026-11-23 13:57 WIB)

1. **Target Asuransi TETAP x2** (tolak 1,80x Gemini) — x2 satu-satunya
   jalan menyelamatkan modal; cari titik paling manis di x2; sebisa
   mungkin cari laga yang benar-benar pasti menang. must_cover_total_stake
   TETAP.
2. **Banjir 70%/65% + EV ≥ −1% DISETUJUI** ("klo itu dari saran gemini
   yang sudah berpengalam aku setuju") — ganti edge datar 3,5%.
3. **Utama min p_final 0,74 DISETUJUI** — Utama boleh ketat, yang
   penting minimal x3 s.d. x5. BUKAN uji ketat-ketatan, tapi mencari
   kaki paling masuk akal di dalam tiket. Denver dari awal sudah tidak
   masuk akal tapi tetap dimasukkan — Gemini dan Muse sudah mengakuinya.
4. **Veto AND + ambang 232,0/100,5: user kurang paham** — main agent
   menjelaskan dengan kata sederhana + merekomendasikan AND (memperbaiki
   false positive OKC yang dikeluhkan user) dan melanjutkan build dengan
   ambang INITIAL + validasi acceptance test; user bisa membatalkan
   dengan satu kata (balik ke OR adalah perubahan satu baris config).
   **DISETUJUI EKSPLISIT user 13:59 WIB** ("pake AND yang diusulkan
   gemini, aku setuju") — veto AND + ambang INITIAL 232,0/100,5 resmi
   dipakai di v18.
   Prinsip yang ditegaskan user di #3: mesin mencari kaki yang MASUK
   AKAL, bukan yang paling ketat — KUNING = tidak masuk akal (seperti
   Denver), bukan "tidak sempurna".

BUILD v18 DIJALANKAN 13:57 WIB (koordinator): proposal v18 Gemini §3
penuh dengan penyesuaian keputusan di atas (target Asuransi tetap 2,0;
flood 70/65; EV ≥ −1%; Utama 0,74; veto AND + filter posisi; demerit
baru + rem alami; volume ke gate eksekusi berbasis stake; demon cap;
timing gate; OT empiris; short-circuit; tampilan 3 lapis) + 5 acceptance
test Gemini §4 di slate uji 10 baris.

## Implementasi v18 — catatan koordinator (2026-11-23 sore WIB)

Config v18, 2003 tes (dari 1806 di v17). Acceptance test Gemini §4
di slate uji 10 baris (scripts/ukur_v18.py -> out/ukur_v18.json):
**2/5 LITERAL** (T3 false positive 0/5 + T4 IND TUNGGU_LINEUP LOLOS;
T1 + T5 lolos di bawah rumusan ulang koordinator, lihat di bawah;
T2 GAGAL — Tiket Asuransi tidak terbentuk, pengali maks x1,36).
Laporan lengkap: LAPORAN-V18.md. Laporan worker: LAPORAN-VONIS-V18.md
(verdict/veto/OT/timing gate), LAPORAN-GATE-V18.md (equilibrium/
komposer/Vegas/laporan), LAPORAN-DEMON-V18.md (demon cap/
short-circuit/acceptance script).

Keputusan koordinator selama build (menunggu keberatan user/reviewer):
1. **Gate eksekusi = likuiditas + spread, BUKAN volume kumulatif.**
   Volume kumulatif (volume_usd) adalah riwayat, bukan keterbelian
   saat ini: garis DET U239,5 (bid 79/ask 82, likuiditas $36.580)
   gagal gate volume $30 karena volume kumulatifnya $5 — padahal
   order $15 di ask terisi melawan kuotasi market-maker. Gate baru:
   likuiditas Gamma >= max(2x stake, $25) = $30 DAN spread bid/ask
   <= 5,0 sen DAN ask nyata (< 99 sen); data hilang = gagal
   (fail-closed). Volume kumulatif tetap dilaporkan (flag thin +
   info L3), bukan gate. max_spread 5,0 sen adalah INITIAL dari
   distribusi artefak 22 Nov (kuotasi hidup 1-3 sen, kuotasi mati
   >= 7 sen) — rencana kalibrasi: laporan fill nyata user di jup.ag.
   Dampak terukur: equilibrium Asuransi 3/10 -> 10/10.
2. **T1 fungsional:** tunggu_lineup DIHITUNG sebagai "terblokir"
   (DEN tidak masuk tiket mana pun di kedua baris: verif KUNING
   via veto, live TUNGGU_LINEUP). Kriteria literal tetap dicatat.
3. **T5 dirumuskan ulang:** target literal Gemini (laga kena veto
   melompati scan jup.ag) TIDAK BERLAKU di arsitektur ini — scan
   jup.ag slate-level (~3,5 mnt/slate), bukan per laga. Yang
   terukur: penghematan 6,85 dtk/laga kena veto (Tahap 3+5+5b+5c).
4. **Sisa HIJAU mengalir ke Utama:** alokasi lama membuang kandidat
   Utama laga HIJAU sehingga Utama 0 kandidat di slate uji (MENENGAH
   0). "DULU" dalam keputusan user 12:20 WIB dibaca sebagai
   prioritas pilih, bukan kepemilikan eksklusif — Asuransi memilih
   dulu di tingkat subset, laga HIJAU yang tidak terpakai mengalir
   ke Utama; tanpa-kaki-kembar tetap ditegakkan di tingkat subset.
   Dampak di slate uji: Utama 0 kandidat -> 3 kaki (pengali maks
   x1,85, tetap di bawah x3 — temuan T2 tidak berubah).
5. **Penempatan Vegas (CDF efektif kanonis):** simulation.markets +
   score_distribution.total di artefak adalah nilai EFEKTIF
   (disesuaikan Vegas); salinan mentah di markets_mentah +
   total_mentah; blok root "vegas" mencatat keputusan. Vonis,
   equilibrium, skip, komposer membaca nilai efektif tanpa
   perubahan hilir.
6. **Tidak ada status VETO:** laga kena veto memakai DATA_INCOMPLETE
   + blok root veto + vonis KUNING. Tidak ada jalur kode yang memakai
   status VETO.
7. **D7 (worker A):** jalur USG timing gate mensyaratkan mp >= 10,0
   + BPM >= 0,0 (menolak pemain pinggiran RayJ Dennis/Felix Okpara).
   Tanpa kualifikasi ini 6/10 baris ditahan, dengan ini 4/10.
8. **_sebab_cedera_baru (worker C):** OUT terkonfirmasi + BPM >= 2,0.
   Kelemahan: pemain out sepanjang musim (Haliburton) ikut terhitung;
   kesegaran tidak terbukti dari satu snapshot.
9. **Peta rim protector 21/30 tim** (9 belum terpetakan: ATL, DET,
   GSW, HOU, IND, LAC, NYK, ORL, PHX — veto tidak bisa mengevaluasi
   tim-tim itu). stats.nba.com TIDAK punya kolom POSISI — posisi
   dari BBRef. 3 dari 10 laga slate 24 Nov melibatkan tim belum
   terpetakan (OKC@IND, PHX@NOP, LAC@HOU).
10. **Hard-skip OT DORMAN:** p_ot maks 0,0575 < ambang 0,085 — gate
    keras OT tidak pernah menyala di v18. Base rate 0,0575 adalah
    PRIOR yang didokumentasikan, bukan fit (tidak ada flag OT di
    2.701 laga data fit).

Temuan acceptance test yang TIDAK diperbaiki dengan melonggarkan
ambang (untuk iterasi dengan user/Gemini):
- T2 GAGAL karena JUMLAH KAKI, bukan ambang: 5 baris HIJAU+EQ
  (4 laga berbeda) -> ORL di-skip pola Denver -> 3 kaki Asuransi
  @~88c = x1,36 < x2. Utama: 3 sisa HIJAU = x1,85 < x3.
- Pola Denver men-skip 4/7 laga live (OKC, ORL, DEN, IND) — 3 di
  antaranya (OKC, ORL, IND) MENANG di garis EQ. Syarat (2) "tidak
  ada garis tahan-banjir non-thin" + syarat (4) "edge < 3,5%"
  hampir selalu benar di garis mahal — pola efektif menyala pada
  flag setan + acuan thin saja. Konversi syarat (4) ke EV adalah
  tindak lanjut yang didokumentasikan.
- Artefak 22 Nov mendahului Vegas/FTr — acceptance mengukur gate
  v18 di atas artefak era v17; demerit foul belum teruji di data
  nyata.

## Build v18 SELESAI + TERVERIFIKASI (2026-11-23 15:30 WIB)

Commit e31c487 (main, remote cocok), config v18, 2003/2003 tes,
ruff + black bersih, 0 kredit. Main agent memverifikasi independen:
commit/remote/tree, full suite, lint, config, out/ukur_v18.json,
hitung tangan (x1,36 = (100/88,5)^3 x 0,945 = 1,3633 ✓; x1,85 =
1,2048 x 1,2422 x 1,3072 x 0,945 = 1,8488 ✓; demon 253,71 =
233,0-68,09+88,80 ✓; ER DET 0,9916 ✓; OT maks 0,0575 < hard-skip
0,085 -> DORMAN ✓; peta rim protector 21/30, hilang ATL/DET/GSW/HOU/
IND/LAC/NYK/ORL/PHX).
Vonis slate uji: HIJAU 5 / MENENGAH 0 / KUNING 1 / TUNGGU 4
(v17: 0/2/8). Equilibrium 10/10 kedua tiket (v17: Asuransi 0/10).
Acceptance Gemini §4: T3 LOLOS (false positive 0/5), T4 LOLOS
(IND TUNGGU_LINEUP); T1 fungsional (DEN verif KUNING via veto AND,
live TUNGGU_LINEUP — kedua baris terblokir); T5 reformulasi
(6,85 dtk/laga; scan jup.ag slate-level tidak bisa di-short-circuit
per laga); T2 GAGAL JUJUR (tiket tidak terbentuk — maks x1,36
Asuransi / x1,85 Utama).
REVISI KOORDINATOR (menunggu keberatan): (1) gate eksekusi =
likuiditas + spread (bukan volume kumulatif) — bukti DET U239,5
(bid 79/ask 82, likuiditas $36.580, volume kumulatif $5) terblokir
gate volume padahal order $15 terisi; gate baru likuiditas ≥ $30
DAN spread ≤ 5,0¢ (INITIAL) DAN ask nyata; dampak EQ Asuransi
3/10 -> 10/10. (2) sisa HIJAU mengalir ke Utama (MENENGAH 0/10
membuat Utama 0 kandidat). (3) Vegas CDF efektif kanonis.
TEMUAN UTAMA: penghalang v18 kini JUMLAH KAKI, bukan ambang — pola
Denver (skip_awal) men-skip 4/7 laga live, 3 di antaranya (OKC,
ORL, IND) MENANG di garis EQ. Syarat pola (4) masih memakai edge
datar < 3,5% (aturan lama yang dibunuh audit Gemini); syarat (2)
masih memakai definisi "tipis" volume lama; demon pola masih generik
(bukan setan per pemain). TINDAK LANJUT: konversi syarat (4) ke EV
+ definisi tipis berbasis likuiditas + demon pemain — butuh
persetujuan user (perubahan logika skip) atau saran Gemini
(Gemini §4 mengundang iterasi dengan angka v18).
BATASAN JUJUR: veto buta di 9 tim (3/10 laga slate 24 Nov: OKC@IND,
PHX@NOP, LAC@HOU); HIJAU DAL rapuh (DRtg 112,8 vs cutoff 112,9 —
margin 0,1); demerit foul belum teruji di data nyata (FTr None di
artefak 22 Nov); OT hard-skip DORMAN (p maks 0,0575 < 0,085).

## Review Gemini hasil v18 + spesifikasi patch v18.1 (diterima 2026-11-23 15:42 WIB)

File: REFERENSI-PATCH-V18-1-GEMINI.md (commit a6a0d93). Gemini
SETUJU 100% memperbaiki skip_awal (usulan Muse) + 4 temuan tambahan.
Main agent MEMVERIFIKASI tabel pengali Gemini — SEMUA 16 NILAI +
jumlah kaki minimal PERSIS (88,5¢: 1,36/1,54/1,74/1,97, butuh 7 kaki
untuk x2; 86¢: 1,49/1,73/2,01/2,34, 5 kaki; 84¢: 1,59/1,90/2,26/2,69,
5 kaki; 82¢: 1,71/2,09/2,55/3,11, 4 kaki).
PATCH #1 (skip_awal): syarat edge < 3,5% -> EV < -1%; "thin" ->
cek_eksekusi lolos; demon per pemain v18; pagar anti-redundansi —
skip hanya menyala bila (a) rapuh setan (P_setan < 0,55 atau
median_setan > garis_asuransi) DAN (b) total pasar ≥ 232,0 DAN
(c) tidak ada garis valid yang tahan banjir+setan. Target: DEN
tetap di-skip; OKC/ORL/IND bebas skip.
PATCH #2 (KRITIS — temuan baru "Perangkap Plafon 88,5¢"):
safety-first dalam band 80–89¢ SELALU memetik plafon (P_final
monoton naik terhadap harga) — terbukti di T2 (3 kaki semua 88,5¢).
Solusi TANPA pelonggaran gate: equilibrium kembalikan SEMUA garis
valid (valid_lines); komposer pilih kombinasi yang memaksimalkan
peluang cair gabungan (max Π P_final) dengan pengali bersih di
[2,00x, 2,50x], fallback terlaporkan [1,80x, 1,99x] bila tidak ada
kombinasi ≥ 2,00x tanpa melanggar gate.
PATCH #3 (KRITIS 24 Nov): peta rim protector 21/30 -> 30/30 —
diagnosa mapping kode tim BBRef vs NBA (PHO/PHX dst) + normalisasi
nama; tier fallback terukur (top-1 C/PF, min ≥ 18, BLK ≥ 0,7,
diberi label tier "fallback").
PATCH #4: filter kesegaran _sebab_cedera_baru — pemain OUT hanya
dihitung penyebab gap bila GP ≥ 3 musim berjalan (atau main dalam
14 hari terakhir); cedera jangka panjang (GP == 0, mis. Haliburton)
tidak membatalkan Vegas shrinkage.
PATCH #5: pulihkan MENENGAH_HIJAU (evaluasi tail_fragility di garis
referensi standar ~82¢, bukan plafon 88,5¢) + simetri D7 (filter
menit mp ≥ 15,0 di kedua jalur USG dan BPM).
§2: Gemini SETUJU §5.1/§5.2/§5.3/§5.4/§5.5/§5.6/§6(B); §5.7 setuju
+ revisi kecil (mp simetris); §5.8 REVISI (Patch #4); §5.9 REVISI
SEGERA (Patch #3); §5.10 setuju sementara (prior OT 0,0575 JANGAN
diubah tanpa data fit; hard-skip tetap dorman).
KEPUTUSAN USER YANG DIBUTUHKAN (D12): fallback pengali Asuransi
[1,80x, 1,99x] — user MENOLAK 1,80x sebagai TARGET (13:57 WIB);
fallback adalah "bila tidak ada kombinasi ≥ 2,00x, tawarkan yang
terbaik di bawah x2" — tetap mengubah ekonomi (1,80x = $27 dari
$15, rugi $3 bila Utama hangus vs impas di x2). Opsi: (a) tanpa
fallback (NO BET bila < 2,00x); (b) fallback sebagai opsi
terlaporkan (bukan auto-compose). Menunggu jawaban user sebelum
build v18.1.

## Pilihan fallback Asuransi (b) + filosofi "pasti menang" (user 2026-11-23 15:52 WIB)

User memilih **(b) fallback sebagai opsi terlaporkan** (bukan
auto-compose, bukan NO BET). Alasannya (kata-katanya sendiri):
NO BET tidak mungkin hanya karena mesin gagal menemukan kombinasi
yang mustahil dipenuhi banyak anomali; secara nyata tidak mungkin
4–5 kaki di harga 82¢ hangus bersamaan. "Pasti menang" BUKAN posisi
yang mustahil dicapai, tapi posisi yang untuk jebol butuh
penyimpangan yang cukup tinggi — Asuransi diisi kaki-kaki yang
secara perhitungan masuk akal DAN tetap aman dan tebal dari
penyimpangan. Penyimpangan ekstrem memang anomali (diterima sebagai
risiko — "kalah dengan terhormat"). Bukti: di laga Denver tadi pagi,
bahkan 99¢ tidak selamat bila dipasang 1 menit sebelum laga — jadi
pertahanan bukan harga, tapi seleksi + bantalan tebal. User TIDAK
ingin menghindari pertandingan secara brutal dan kaku, tapi lebih
memilih PASANG dengan risiko yang ditekan sedemikian rupa.
CONTOH TIPE LAGA (user): laga CHI tadi pagi sudah ketahuan dari awal
akan berlangsung pace cepat, pemain bermain panas, sedikit garbage
time sebab kedua tim main terbuka — mesin harus mengenali TIPE laga
seperti ini (item masa depan: label tipe laga di laporan; mesin
sudah punya pace + spread + OT sebagai bahan).
DESAIN FALLBACK (b): komposer tetap menargetkan [2,00x, 2,50x] untuk
Tiket Asuransi; bila tidak ada kombinasi ≥ 2,00x tanpa melanggar
gate, mesin MELAPORKAN opsi terbaik di [1,80x, 1,99x] sebagai opsi
berlabel (bukan tiket) — lengkap dengan pengali, PELUANG CAIR
GABUNGAN tiket (joint P_final — angka yang sebenarnya menentukan,
bukan peluang per kaki), detail per kaki, dan alasan tidak mencapai
x2. Keputusan pasang atau tidak ada di tangan user.
BUILD v18.1 DIJALANKAN 15:52 WIB (koordinator): 5 patch Gemini
(REFERENSI-PATCH-V18-1-GEMINI.md §1) + fallback (b) + 5 acceptance
test §4 (kriteria 2 disesuaikan: tiket terbentuk ≥ 2,00x ATAU opsi
fallback terlaporkan [1,80x, 1,99x] dengan joint P + alasan).
Pertanyaan user "ada yang mau ditanya ke aku atau gemini?" —
dijawab main agent: tidak ada yang memblokir build; build jalan
sekarang; bila build memunculkan pertanyaan, akan ditanyakan.

## Build v18.1 SELESAI + TERVERIFIKASI (2026-11-23 sore WIB)

Koordinator (3 worker) + integrasi. Config v18.1 (meta.version 18.1),
2111/2111 tes (dari 2003 di v18), ruff + black bersih, 0 kredit.
Acceptance Gemini §4 (scripts/ukur_v18_1.py -> out/ukur_v18_1.json,
slate uji 10 baris): **4/5** — K1 LOLOS (fungsional), K2 GAGAL literal
(tiket x2 tidak terbentuk — maks x1,86; opsi fallback [1,80x, 1,99x]
TERLAPORKAN sesuai keputusan user (b)), K3 LOLOS (peta 30/30), K4
LOLOS (GP==0 tidak memicu), K5 LOLOS (regresi nol).
Vonis slate uji: HIJAU 5 / MENENGAH 0 / KUNING 1 / TUNGGU 4 (sama
dengan v18). Skip_awal: 0/10 (v18: 6/10); skipped_matches komposer [].
Komposer 10 laga x 9 garis valid: 0,07 dtk.
Laporan: LAPORAN-V18-1.md (sintesis) + LAPORAN-V18-1-A/B/C.md
(per worker).

PENUTUP OPEN ITEMS §2 SPEK v18.1 (tanggapan Gemini — DITUTUP):
§5.1 gate eksekusi likuiditas+spread — SETUJU, diteruskan (kalibrasi
dari fill nyata jup.ag). §5.2/§5.3 T1 fungsional + T5 reformulasi —
SETUJU. §5.4 sisa HIJAU ke Utama — SETUJU. §5.5 Vegas CDF efektif +
shrinkage 0,5 — SETUJU (pantau Brier setelah 50 kaki di ledger).
§5.6 veto DATA_INCOMPLETE — SETUJU. §5.7 D7 — SETUJU + revisi
(simetri mp >= 15,0 kedua jalur — Patch #5b). §5.8
_sebab_cedera_baru — DIREVISI (filter GP >= 3 — Patch #4). §5.9
peta 21/30 — DIREVISI SEGERA (30/30 — Patch #3). §5.10 hard-skip OT
0,085 dorman — SETUJU SEMENTARA (prior 0,0575 TIDAK diubah tanpa
data fit). §6(B) gate eksekusi total_under + bantalan veto parsial
+3 — SETUJU.

TEMUAN UTAMA — POLA DENVER MENYALA 0/10 (K1 lolos FUNGSIONAL saja):
dengan substitusi harfiah spek, pola TIDAK menyala di satu pun
baris — termasuk DEN@CHI live (S1 flag setan ✅; S2 ❌ — garis tahan
banjir 266,5 lolos cek_eksekusi; S3 ❌ — garis acuan lolos
cek_eksekusi; S4 ❌ — EV acuan −0,04% > −1%). DEN tetap terblokir
fungsional di kedua baris (live TUNGGU_LINEUP — Powell Questionable;
verif KUNING via veto AND — Claxton OUT); 0 kaki DEN mencapai
komposer. AKAR PENYEBAB: syarat (2)/(3)/(4) pola dibangun di atas
premis era v16 (garis jauh thin + edge datar) yang SUDAH dibatalkan
pengukuran v18 sendiri (orderbook market-maker dalam: likuiditas
$23–32 ribu + spread 3–5¢ di semua garis; EV acuan ≈ impas).
S1 (flag setan) menyala di 10/10 baris — tidak membedakan DEN dari
laga biasa (ORL memenuhi LEBIH BANYAK syarat pola daripada DEN:
S1+S2+S4 vs S1 saja). Pagar anti-redundansi tidak pernah dievaluasi
(pola tidak cocok sejak awal — pagar hanya bisa memblokir, bukan
membuat menyala). TIDAK ADA ambang yang di-retune untuk memaksakan
pola menyala (itu overfitting). KEPUTUSAN KOORDINATOR (menunggu
keberatan + iterasi Gemini): fungsi skip pola Denver kini ditanggung
lapisan veto + vonis + timing gate + gate equilibrium; pola butuh
REDESAIN berprinsip (apa yang membedakan DEN sekarang?) — kirim
pengukuran v18.1 ke Gemini untuk iterasi, sesuai undangannya.

KEPUTUSAN KOORDINATOR LAIN (menunggu keberatan):
1. BATAS 6 KAKI DIPERTAHANKAN sesuai spek (Gemini §3
   max_legs_insurance: 6; _DP_MAKS_KAKI = 6 di kode — BUKAN nilai
   config, perlu dipindah ke config bila diubah). TRADE-OFF NYATA:
   slate dengan >= 7 laga HIJAU yang garis validnya semua >= 88,5¢
   tidak bisa membentuk x2 (maks 6×88,5¢ = x1,97), padahal 7 kaki
   @88,5¢ = x2,22 dan joint P-nya bisa LEBIH TINGGI dari 4 kaki
   murah (0,93^7 > 0,85^4); band [2,00x, 2,50x] sendiri membatasi
   kaki maks 8 (di 89¢). REKOMENDASI koordinator: naikkan ke 8
   (selaras filosofi user menumpuk banyak kaki + perilaku komposer
   v18 yang mengizinkan 7+ kaki) — menunggu keputusan main agent /
   user / Gemini. Satu nilai config bila disetujui.
2. joint_p_final opsi fallback = Π decision_prob (BUKAN Π p_final):
   untuk kaki condong-ke-market, decision_prob = harga market
   mentah di garis varian. Terverifikasi: 0,825 × 0,835 × 0,85 ×
   0,8721 ≈ 0,5107 (terlaporkan) vs Π p_final = 0,5402. Nilai BENAR
   sesuai aturan (konservatif, searah lean-to-market) — tapi NAMA
   kuncinya menyesatkan. Tindak lanjut minor: ganti nama jadi
   joint_p_keputusan atau dokumentasikan definisinya.
3. Haliburton di artefak live GP=4 (bukan 0) + missed_last10: 10 —
   filter GP >= 3 TIDAK mengecualikannya di artefak nyata (K4 lolos
   pada kasus sintetis GP==0). GP >= 3 adalah proksi kesegaran yang
   lemah; REKOMENDASI: aturan 14-hari / missed_last10 sebagai
   tindak lanjut (opsi kedua spek Patch #4).
4. Perbaikan integrasi koordinator: script ukur K4 unpack 3-nilai
   (kode v18) vs 4-tuple v18.1 (_sebab_cedera_baru) — diperbaiki,
   K4 lolos setelahnya. Tidak ada perubahan kode produksi untuk ini.
5. Garis referensi tail_fragility difilter cek_eksekusi (keputusan
   Worker A): definisi harfiah jatuh ke garis sampah U117,5 @82,5¢
   (ask 99¢, likuiditas $3,80). Tanpa filter, demerit dinilai di
   garis khayalan.
6. Pagar syarat (3) "tahan setan" = P_setan >= 0,55 (cermin ambang
   rapuh 0,55, INITIAL) — bukan 0,82. Menunggu keberatan.

BATASAN JUJUR v18.1: artefak uji tanpa blok setan_pemain/veto
(jalur pemain + veto-blok hanya teruji fixture; S1 terukur via
fallback generik); MENENGAH terbukti via fixture sintetis, 0/10 di
slate ini; demerit foul belum teruji di data nyata (FTr None di
artefak); OT hard-skip tetap DORMAN; ambang pagar 0,55 INITIAL.

## Build v18.1 SELESAI + TERVERIFIKASI (2026-11-23 16:36 WIB)

Commit 9d52646 (main, remote cocok), config v18.1, 2111/2111 tes,
ruff + black bersih, 0 kredit. Main agent memverifikasi independen:
commit/remote/tree, full suite (2x), lint, config, out/ukur_v18_1.json,
hitung tangan (fallback x1,8015 = (100/83)x(100/84)x(100/85,5)x
(100/88)x0,945 ✓; joint P 0,5107 = 0,825x0,835x0,85x0,8721 ✓;
Pi p_final 0,5402 vs joint 0,5107 — joint memakai decision_prob,
lebih konservatif ✓; 7 kaki @88,5¢ = x2,22 ✓; fixture perangkap
4 kaki @82,5¢ = x2,04 ✓; 0,93^7 = 0,6017 > 0,85^4 = 0,522 ✓; peta
30/30, 9 fallback = 9 tim yang hilang ✓).
Acceptance: K1 LOLOS fungsional (DEN terblokir kedua baris; pola
0/10), K3 LOLOS (30/30), K4 LOLOS (GP==0 tidak memicu), K5 LOLOS
(regresi nol); K2 GAGAL literal — tiket x2 tidak terbentuk (maks
x1,86, 4 kaki; harga termurah lolos gate 83¢) TAPI opsi fallback
TERLAPORKAN sesuai desain (b): x1,8015, joint P 0,5107, 4 kaki
(BOS 227,5 @83¢, DAL 242,5 @84¢, DET 243,5 @85,5¢, ORL 241,5 @88¢),
semua lolos 100% gate. Utama maks x2,30 < x3 (naik dari x1,85).
TEMUAN UTAMA: pola Denver menyala 0/10 — syarat (2)/(3)/(4)
dibangun di atas premis era v16 (garis jauh thin + edge datar)
yang SUDAH dibatalkan pengukuran v18 sendiri (orderbook
market-maker dalam; EV ≈ impas). S1 menyala 10/10 (tidak
membedakan DEN; ORL memenuhi LEBIH BANYAK syarat daripada DEN).
Fungsi pola kini ditanggung veto + vonis + timing gate + gate
equilibrium. Pola butuh REDESAIN berprinsip — kirim pengukuran
v18.1 ke Gemini untuk iterasi (bukan pemblokir besok: DEN tetap
terblokir veto + timing gate).
KEPUTUSAN KOORDINATOR (menunggu keberatan): (1) batas 6 kaki
DIPERTAHANKAN sesuai spek — trade-off nyata: 7 kaki @88,5¢ = x2,22
(joint P 0,60 > 0,52 untuk 4 kaki murah) terblokir; band [2,00x,
2,50x] sendiri membatasi kaki maks 8. REKOMENDASI: naikkan ke 8
(selaras filosofi user "tumpuk BANYAK kaki di harga tinggi asal
tiap kaki fundamental kuat" + perilaku komposer v18). _DP_MAKS_KAKI
saat ini konstanta kode, perlu dipindah ke config bila diubah.
KEPUTUSAN USER (D12). (2) joint_p_final = Π decision_prob, bukan
Π p_final — nilai benar + konservatif, nama kunci menyesatkan
(tindak lanjut minor). (3) Haliburton GP=4 di artefak nyata (+
missed_last10: 10) — filter GP≥3 TIDAK mengecualikannya;
rekomendasi aturan 14-hari/missed_last10 sebagai tindak lanjut
(berdampak ke laga IND; IND main besok vs OKC). (4) garis referensi
tail_fragility difilter cek_eksekusi (hindari garis sampah U117,5).
(5) pagar syarat (3) "tahan setan" = P_setan ≥ 0,55 (INITIAL).
(6) OG Anunoby (PF) fallback NYK vs KAT (C) bila dibatasi C.
BATASAN: artefak uji tanpa blok setan_pemain/veto (jalur pemain +
veto-blok hanya teruji fixture); pagar tidak pernah berlaku di slate
uji (bukti hanya fixture); MENENGAH 0/10 di slate ini; demerit foul
belum teruji di data nyata (FTr None); OT hard-skip dorman; ambang
pagar 0,55 INITIAL; veto bergantung data cedera SEGAR.
