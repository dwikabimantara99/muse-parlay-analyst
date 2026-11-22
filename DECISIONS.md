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
