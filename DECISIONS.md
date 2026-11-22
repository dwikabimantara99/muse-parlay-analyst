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
