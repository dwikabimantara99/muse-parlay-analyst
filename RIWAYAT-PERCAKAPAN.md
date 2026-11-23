# RIWAYAT PERCAKAPAN — Mesin Analis Parlay (Muse)

**Dokumen ini untuk:** AI lain (atau manusia) yang perlu memahami arah
percakapan ini — dari awal sampai sekarang — tanpa membaca seluruh chat.
**Bukan ringkasan cerita:** dokumen ini memuat konteks, keputusan,
KODE (nama file/fungsi/kunci config), dan ANGKA penting, semuanya
dengan sumber. Bila sebuah angka tidak bisa dilacak ke sumber, dokumen
ini menulis `UNKNOWN`, bukan menebak.

**Rentang:** 20 November 2026 → Selasa 24 November 2026 ~05:00 WIB.
**Chat:** side chat "Mesin Agent Baru"
(`chat_id d49a2e73-4493-4f2e-8cc6-b43e370f3dc5`).
**Repo:** `~/workspace/projects/muse-parlay-analyst/` — GitHub PRIVATE
`dwikabimantara99/muse-parlay-analyst`, branch `main`.
**Keadaan repo saat dokumen ini ditulis:** main @ `f54ac49`
(52 commit), config **v18.1**, **2111 tes** (stdlib `unittest`,
semua lulus), ruff + black bersih.
**Sumber dokumen ini:** riwayat chat di atas + `DECISIONS.md`
(1.727 baris, sumber kebenaran keputusan) + `LAPORAN-SELURUH-PEKERJAAN.md`
+ `LAPORAN-V18.md` + `LAPORAN-V18-1.md` + `LAPORAN-PERBAIKAN-PASCA-DENVER.md`
+ `REKAP-MESIN-UNTUK-GEMINI.md` + `REFERENSI-AUDIT-GEMINI-V18.md` +
`REFERENSI-PATCH-V18-1-GEMINI.md` + `REFERENSI-GEMINI-2026-11-23.md` +
`config/playstyle.yaml` (v18.1). Blueprint asli:
`workspace/user/files/Blueprint_Mesin_Analis_Parlay__Muse.md`.

---

## 1. Identitas proyek & cara kerja chat ini

### 1.1 Apa yang dibangun

**muse-parlay-analyst** — mesin analis parlay NBA + sepak bola dengan
alur kerja terkunci. **BUKAN bot otomatis:** user bertanya / meminta
analisis, mesin menganalisis (data + simulasi + berita), meracik
**Tiket Asuransi** + **Tiket Utama**, user memasang tiket sendiri
secara manual di **jup.ag**. Mesin tidak pernah memegang dana dan
tidak pernah memesan apa pun (Jupiter: READ-ONLY, hanya endpoint GET).

Pasar utama user: **Alt Under NBA** (total poin di bawah garis yang
jauh di atas garis pasar). User menghindari moneyline ("seperti
lempar koin") kecuali fakta/data sangat kuat.

### 1.2 Siapa siapa

| Peran | Siapa | Catatan |
|---|---|---|
| **User** | Pemilik proyek, bettor konservatif | Bicara Bahasa Indonesia sehari-hari, tanpa jargon. Nama asli UNKNOWN (pseudonim yang dia pilih untuk akun Odds API: "jokowi" — BUKAN nama asli). Tidak terlalu membaca bahasa teknis — laporan harus bahasa sederhana. Menjawab keputusan lewat teks (mengabaikan widget pilihan). |
| **Muse** | Agen utama di chat ini | Membangun + menjalankan mesin di balik layar, membawa fakta ke chat. Memverifikasi INDEPENDEN dari disk setiap hasil build (commit, tes, angka dihitung tangan) sebelum melapor. |
| **Claude** | **AUDITOR** | User TIDAK lagi memakai Claude sebagai perantara (sejak 22 Nov). User meneruskan laporan Muse ke Claude, lalu membawa kembali temuannya. Claude menemukan cacat nyata berkali-kali (fit/validasi, hitung-ganda pemain absen, bantalan, dll). |
| **Gemini** | **Analis senior** user | Analis parlay user sebelum mesin ini ada. Membawa user menang, "tidak pernah kalah sampai 23 Nov" (kata user). User sangat mempercayai sarannya ("klo itu dari saran gemini yang sudah berpengalam aku setuju"). Gemini TIDAK punya mesin — mengandalkan ingatan + perhitungan yang tidak bisa dilacak. Perannya di proyek ini: penasihat desain + auditor eksternal; jawabannya selalu DIVERIFIKASI Muse dari data sebelum dipakai. |

### 1.3 Cara kerja yang disepakati

- **Diskusi di chat ini seperti bicara dengan LLM biasa** (cepat,
  santai, "bro"), tapi di belakangnya ada mesin yang menjawab FAKTA
  (angka dari kode, bukan dari ingatan LLM).
- **Build dikerjakan koordinator subagent** (satu koordinator per
  langkah, ≤3 worker), lalu Muse memverifikasi independen dari disk
  sebelum melapor. Pola fail-first: perbaikan dibuktikan dengan tes
  yang gagal di kode lama dan lulus di kode baru.
- **Keputusan user dicatat di `DECISIONS.md`** — bila DECISIONS.md
  dan blueprint berbeda, DECISIONS.md yang berlaku.
- **Perubahan ambang/parameter mengikuti pola D12:** mesin hanya
  MENGUSULKAN, user yang menyetujui. Mesin TIDAK PERNAH mengubah
  parameter sendiri.
- **Visi user (dengan kata-katanya sendiri, 22 Nov):** "kasih satu
  laga (mis. Pistons vs Hawks), mesin langsung analisis — data NBA
  valid, rating pemain, statistik tim, proyeksi total over, news,
  siapa diragukan tampil, arah market, kisaran bursa, 5 laga terakhir
  tiap tim, 5 pertemuan terakhir, riwayat kandang-tandang, semua
  indikator — lalu uji nyata simulasi 100.000 pertandingan."
- **Visi terbaru (23 Nov 06:33 WIB):** yang penting adalah **data
  live real-time saat dibutuhkan, racikan objektif berbasis data,
  analisis + berita SEBELUM pasang**. Belajar sendiri (self-learning)
  BUKAN prioritas lagi; mesin jalan 24 jam tidak penting; **mesin
  bola DIKESAMPINGKAN dulu** (fokus NBA). Alasan user membangun mesin
  (23 Nov 06:21): analisis Gemini sudah bagus, tapi "tidak efisien,
  gw harus nyuruh dia satu persatu dulu analisis" + langganan
  berbayar + kalau sesi chat hilang harus melatih lagi dari awal.

---

## 2. Garis waktu per hari

### 2.1 Kamis 20 Nov 2026 — Fondasi + probe + API key

- **Tahap 1 (fondasi) selesai + review LULUS (22:01 WIB).**
  Struktur repo, `config/playstyle.yaml` + `config/sources.yaml`,
  `SOP.md` (alur 10 langkah), 5 skema JSON, ledger SQLite
  (`cli.py log/recap`), README Indonesia, CI GitHub Actions.
  Keputusan review: aturan ledger (VOID/PUSH/CASHOUT), sumber data
  berjenjang (B1–B4), jawaban D2–D14 (lihat §3 + §8).
- **Jupiter:** portal `developers.jup.ag` ternyata TIDAK memakai
  login wallet (OAuth Google/GitHub atau email+kode). Wallet Solana
  khusus sempat dibuat (pubkey
  `CzFEgpBYhU4andHc4RJJHxTcRgDUYKsUtZQUbFEKRj1m`, saldo 0, 0 tx)
  lalu **DIHAPUS 22:23 WIB dengan `shred -u`** atas perintah user —
  tidak pernah didanai, jangan dibuat ulang. API key dari user
  (22:22 WIB), disimpan HANYA di `.env` sebagai `JUPITER_API_KEY`
  (mode 600, gitignored); tes keyed 1 panggilan HTTP 200.
  Aturan K1–K4 + P1–P4 (pembanding independen) dicatat.
- **Tahap 2a — probe 13 sumber (22:37 WIB):** 44 request.
  PAKAI 8, CADANGAN 3, JANGAN 2. **FotMob DITOLAK** (ToS melarang
  scraping), **Sofascore DITOLAK** (3×403), Understat maintenance.
  Koreksi urutan: stats.nba.com UTAMA statistik NBA; JSON resmi
  Premier League UTAMA EPL. D4 terjawab: Official NBA Injury Report
  di `official.nba.com`, PDF per 15 menit terverifikasi.
- **Odds API — signup sendiri (22:47–22:54 WIB):** Gmail user
  (`cskepto@gmail.com`) terhubung tapi tidak ada email Odds API.
  Atas izin user, agen mendaftar sendiri paket Starter FREE
  (500 kredit/bulan), nama depan "jokowi", captcha diselesaikan
  agen; key tiba 22:53, disimpan HANYA di `.env` sebagai
  `ODDS_API_KEY`. Verifikasi 1 panggilan: HTTP 200, 9 event NBA,
  Pinnacle tersedia, sisa 499/500. Batas operasional diubah ke 500
  (peringatan 80% = 400).
- **Probe tambahan 1–5 (22:57 WIB):** ESPN odds PAKAI untuk bola
  saja (NBA 0 odds); Kalshi sports PAKAI (moneyline cocok 100%,
  field harga `*_dollars`, pakai bid/ask bukan `last_price`);
  `jup_markup` median 0,5¢ (jup.ag hampir tidak menambah biaya);
  football-data.co.uk BOLEH dengan syarat (unduhan 1× per musim,
  CSV lokal di `data/` gitignored, kalibrasi musim ≤ 2024/25);
  Understat masih maintenance → cek harian otomatis aktif
  (hook `understat-daily-check`, diam kecuali situs kembali).

### 2.2 Jumat 21 Nov 2026 — Fetcher + peran harga pasar + putusan jup.ag (yang keliru)

- **Tahap 2b selesai (~00:12 WIB, commit `5cb229c`, 399 tes):**
  13 fetcher di `ingest/`, `cli.py analyze` tersambung,
  `engine/devig.py`. Demo slate nyata: NBA 3/3 OK (6 moneyline,
  6/6 punya p_market via `odds_api_devig`); EPL 3/3 HOLD (cedera
  1 sumber, aturan B2 butuh 2 — fail-closed, bukan gagal fetch).
  FPL API ditemukan sebagai kandidat sumber cedera bola — BELUM
  diratifikasi (FPL = status fantasy, bukan laporan medis; dan
  ratifikasi saja tidak membuat EPL OK karena sumber kedua masih
  hilang).
- **Peran harga pasar (05:14 WIB, commit `6724d34`, 406 tes):**
  prinsip user — harga pasar adalah PENGUAT + ALAT CEK HARGA,
  bukan hakim. Laporan menampilkan p_model | p_pasar (+sumber) |
  p_akhir, w=0,3. Label DISKON (EV ≥ +2%) / WAJAR (−2% s.d. +2%) /
  MAHAL (EV < −2%). **MAHAL tidak lagi dicoret otomatis** (filter
  EV < −2% dihapus); MAHAL tetap di luar Asuransi kecuali diminta
  eksplisit, boleh masuk Utama berlabel. |model − pasar| > 8 poin
  → bagian wajib "Kenapa beda?". w ditentukan data (kalibrasi
  Brier tiap 50 kaki; kenaikan w butuh persetujuan user).
- **Putusan jup.ag 09:00 WIB (SALAH — dikoreksi 22 Nov):** 5
  pemindaian penuh (5.116–5.214 event) menemukan spread 0, total 0
  untuk NBA — disimpulkan "Alt Under NBA tidak bisa lewat jup.ag".
  Penyebab kesalahan (baru ketahuan 22 Nov): pemindai hanya membaca
  API jup.ag `/events` (daftar) yang hanya menampilkan 2 moneyline
  per event.
- **Kalshi sebagai venue — groundwork (09:08–12:10 WIB):** garis
  ADA (KXNBATOTAL: 14 event, 406 pasar, 29 garis/event langkah
  2 poin, semua ber-harga bid/ask; Under = sisi No pasar Over).
  **Indonesia TIDAK dibatasi** (Member Agreement §VI, 55 restricted
  jurisdictions tidak memuat Indonesia). Fee taker:
  roundup(0,07 × C × P × (1−P)) — 50¢ → 3,5%; 80¢ → 1,4%;
  90¢ → 0,7%. UNKNOWN: KYC dari Indonesia, maker fee KXNBATOTAL,
  legalitas menurut hukum Indonesia. Setelah koreksi 22 Nov,
  Kalshi tidak lagi satu-satunya jalan — venue utama = jup.ag.

### 2.3 Sabtu 22 Nov 2026 — Profil bettor + Tahap 3 + koreksi besar jup.ag

- **Profil bettor + arah mesin (diskusi langsung, user tidak lagi
  memakai Claude sebagai perantara):** konservatif — Asuransi x2–2,5;
  Utama "agresif" versi user = tumpuk kaki 75–85¢ sampai x3–x4,
  x5 bila data sangat optimis, x3,5 sudah sangat disyukuri; x9–x10
  hiburan saja; hindari moneyline. Bukti gaya pagi itu: dua kombo
  5 kaki semua Under MENANG (+$50,85 total). Arah mesin: tanpa mode
  kertas 2–4 minggu (uji statistik saja: Monte Carlo 100.000x +
  backtest + kalibrasi + uji kepekaan); analisis on-demand (tanpa
  cek rutin); **cek ulang sebelum submit WAJIB** (parlay tidak bisa
  dibatalkan); laporan lengkap + tanya-jawab situasional; pantauan
  live saat laga jalan (bukan peringatan pra-laga); belajar sendiri
  diizinkan tapi bukan keharusan.
- **Urutan bangun disetujui (18:54 WIB):** 1 otak NBA, 2 cek ulang
  pra-submit, 3 laporan + tanya-jawab, 4 pantauan live, 5 otak bola,
  6 belajar sendiri. Perluasan Otak NBA: simulasi real-time +
  skenario skuad arbitrer + baca bursa & deteksi pergerakan agresif.
  **Pelajaran Thunder (Nov 2026):** user pasang Thunder Under 227.5
  di 75¢; sebelum tip-off bergerak ke 71¢ karena news yang tidak
  diketahui user; tiket kalah. Pergerakan 4¢ > ambang sharp move 3¢
  — mesin wajib memperingatkan sebelum submit.
- **KOREKSI BESAR (19:15 WIB):** user membuktikan lewat screenshot
  + URL (POLY-1338695) bahwa **pasar spread/total NBA ADA di
  jup.ag** — putusan 21 Nov SALAH. Terverifikasi live: event
  Polymarket `nba-det-atl-2026-11-22` = 283 pasar, total O/U 31
  garis 199.5–255.5; Alt Under U235.5 = 71¢, U239.5 = 80¢; volume
  garis jauh TIPIS ($5–11) → cek bid/ask + likuiditas, bukan harga
  terakhir. Akibat: (1) Alt Under BISA lewat jup.ag; (2) klaim
  "kombo Under pasti bukan dari jup.ag" DICABUT; (3) arsitektur:
  tangga total/spread dari Polymarket gamma API per event (slug),
  BUKAN API jup.ag; P2 TETAP (Polymarket bukan pembanding untuk
  pasar asal Polymarket). Bukti: `out/jup_event_POLY-1338695.json`
  + `out/poly_event_det_atl.json`.
- **Prinsip baru:** bursa dibaca sebagai **psikologi market/bandar**,
  bukan sekadar pembanding harga — mesin wajib cross-check rasa
  "aman" model ke garis market.
- **Tahap 3 Langkah 1 — Otak NBA (commit `151b2c5`, 613 tes):**
  simulasi 100.000x (Student-t, OT, skenario skuad BPM × menit,
  B2B, altitude, flag turnamen). Fit 2.701 laga: sigma_total
  18,2198, sigma_margin 13,8168, home 1,6552, B2B −1,596,
  t_nu 34,5. **D12 DISETUJUI user 19:57 WIB** (setelah auditor
  meninjau). Auditor menemukan 4 temuan — SEMUA BENAR: (1) validasi
  terlalu optimis (rating musim penuh = "melihat masa depan");
  (2) hitung-ganda pemain absen (Duren, BPM 8,8, OUT sejak ~8 Nov,
  dihitung ganda ~1,4 poin); (3) bantalan Under (+8 → P 0,66–0,67;
  +12 → 0,74); (4) cek silang cedera NBA 1 sumber (Rotowire
  paywall — ESPN cedera BEKERJA, 110 cedera → sumber kedua).
- **Patch 1b (commit `634b050`, 707 tes):** validasi rolling
  point-in-time (Brier jujur 0,1983 vs 0,1859 optimis); replacement
  level BPM −2,0 + koreksi tumpang-tindih last10; **bantalan
  Asuransi dari target peluang 74%** (titipan user 20:06 —
  "jangan dikunci +12, tapi dihitung dari target peluang 74%");
  ESPN cedera = sumber kedua. **Adopsi nilai rolling (20:36 WIB):**
  sigma_total 18,9868, sigma_margin 14,4307, home 1,6639,
  B2B −1,5164, t_nu 35,0; altitude TIDAK diadopsi (rolling −0,399
  adalah noise, SE 1,14; tetap −0,0105). **Aturan condong-ke-market:**
  |median model − garis market| > 5,0 tanpa alasan konkret →
  Asuransi pakai probabilitas market; < 74% → tidak lolos.
  Patch 1c dilebur ke Langkah 2 (keputusan user 20:41 WIB).
- **Tahap 3 Langkah 2 — Cek ulang pra-submit + 5 aturan
  (commit `5b987a2`, 849 tes):** artefak `nba_analysis`
  (`engine/nba_analysis.py`, skema v1); `cli.py recheck`
  (verdict TETAP_OK / PERHATIAN / JANGAN_PASANG /
  DATA_INCOMPLETE + GO/NO-GO tiket; exit 0/1/2). Kelima aturan
  terpasang + teruji (rolling, ketersediaan OUT apapun alasan,
  shrinkage menit+BPM K=10, spread dari market + fallback +12,
  condong-ke-market). Koreksi Kalshi: garis total NBA Kalshi
  SAMA PERSIS dengan Polymarket (199,5–255,5 langkah 2 poin).
  Probe DunkAPI (tanpa signup): garis penutupan ADA sejak Jul 2020,
  uji 150 laga ≈ 150 kredit gratis — **signup menunggu user
  (masih terbuka sampai sekarang)**. Verifikasi live DET@ATL:
  recheck NO-GO (Asuransi U233,5 JANGAN_PASANG via
  condong-ke-market, harga market 68–68,5% < 74%).
- **Tahap 3 Langkah 3 — Laporan + tanya-jawab + peracik tiket
  (commit `411f604`, 966 tes):** profil Utama jadi config
  (3,0–5,0, target lunak 4,0); peracik (`engine/ticket_composer.py`)
  — garis Asuransi dan Utama untuk laga yang sama HARUS berbeda;
  condong-ke-market berlaku; hanya Alt Under yang diracik.
  Uji live 7 laga: Utama x3,1847 terracik (EV +8,57%);
  Asuransi TIDAK (hanya 2 kaki lolos, maks x1,65). Pertanyaan
  terbuka: **min_leg_prob 0,74 gate keras vs lunak** (kaki DEN@CHI
  0,7352 gugur) — masih terbuka (mungkin sudah moot di v18).
- **Tahap 3 Langkah 4 — Pantauan live (commit `51ebbc5`,
  1088 tes):** `cli.py pantau` (scoreboard + summary ESPN,
  proyeksi pace-based blend, deteksi anomali 3 jenis, status
  AMAN/WASPADA/TERANCAM/MENANG/KALAH). Pemetaan singkatan ESPN
  (GS→GSW, NY→NYK, NO→NOP, SA→SAS, UTAH→UTA, WSH→WAS).
  Replay 5 laga: 4 MENANG 1 KALAH. **Belum pernah diuji pada laga
  yang benar-benar berjalan** (hutang — baru teruji 23 Nov pagi).
- **Tahap 3 Langkah 5 — Otak bola (commit `015a708`, 1207 tes):**
  Dixon-Coles TANPA_XG, fit 3 musim (1.140 laga/liga). Fit
  MENUNGGU persetujuan user (D12): EPL rho −0,003, home/away
  1,6892/1,4062; LaLiga rho +0,024, 1,4679/1,1310. Validasi jujur:
  skill hanya 1X2 (z −2,61 / −3,04); O/U 2.5 tidak ada skill;
  BTTS LaLiga gagal signifikan. **Cedera bola: 0 sumber** → semua
  laga bola HOLD. **Mesin bola DIKESAMPINGKAN sejak 23 Nov.**
- **Tahap 3 Langkah 6 — Belajar sendiri (commit `e880cc9`,
  1308 tes, config v12):** kalibrasi w tiap 50 kaki (rekomendasi
  saja — TIDAK PERNAH diterapkan otomatis), usulan belajar
  4 aturan (selalu menunggu persetujuan), `cli.py belajar`.
  Belum ada satu pun hasil nyata saat itu.
- **LAPORAN-SELURUH-PEKERJAAN.md** ditulis (commit `b5c01b4` +
  `137ffea`) — laporan ini SUDAH BASI per 23 Nov (berhenti di
  Tahap 3); RIWAYAT ini menggantikannya sebagai peta lengkap.

### 2.4 Minggu 23 Nov 2026 — Racik fix, insiden Denver, lalu rebuild v14→v18.1

Hari paling panjang. Pagi: racik fix + analisis Gemini + **insiden
Denver (2 tiket $30 kalah)**. Sore: lima build berturut-turut
(v14 → v15 → v16 → v17 → v18 → v18.1), semua dipicu pelajaran dari
insiden itu.

**Racik fix (selesai 05:10 WIB, commit `5b24c73`+`32cfd41`,
config v13, 1395 tes).** User menemukan 3 cacat nyata sendiri
(04:05 WIB) — semua terbukti benar: (1) garis terbalik (Asuransi
233,5 < Utama 237,5 di DET@ATL — Asuransi harusnya di ATAS Utama);
(2) tidak ada naik tangga (line 233,5 dipilih padahal 237,5 juga
memenuhi ≥0,74 dengan p 0,7614 vs 0,7409); (3) tidak ada peringatan
bila Utama tidak terlindungi. Perbaikan: bantalan adaptif (formula
di §8.4 — mengganti +8/+12 yang kaku), seleksi harga dulu (Utama
dulu, lalu Asuransi ketat di atasnya), lantai 75¢, naik tangga,
volume tipis = gate keras Asuransi, peringatan Utama-tanpa-lindung.
Aturan WAJAR (user): "Wajar" = jarak antara titik acuan analisis
dan garis tempat harga duduk; +8 TIDAK kaku — mesin menghitung
bantalan per laga. **Filosofi racik yang ditetapkan:** mesin adalah
analis yang menilai per laga, bukan mesin aturan kaku.

**Analisis mendalam cara Gemini meracik (06:21 WIB, commit
`af46d5a`, 0 kode diubah).** User meneruskan transkrip lengkap
Gemini (6 laga) ke chat. Kesimpulan: **salin STRUKTUR KERJA
Gemini, bukan mesin hitungnya.** Struktur yang disalin: bedah
multi-skenario per laga, seleksi kaki dari edge dulu, audit kaki
terlemah, Asuransi sengaja tidak memuat kaki berisiko, kesadaran
waktu. Alasan mesin hitungnya tidak disalin: probabilitas per kaki
Gemini tidak bisa dilacak ke perhitungan apa pun; EV Asuransinya
dihitung dengan basis yang salah (+69,7% di 2,24x mentah vs +64,5%
yang benar di 2,17x nyata); probabilitasnya bergeser antar jawaban.
**Ketegangan konsep yang belum terjawab:** Gemini memperlakukan
selisih model-vs-market sebagai PELUANG; mesin memperlakukannya
sebagai KECURIGAAN (condong-ke-market, ambang selisih 5,0
dipertahankan — ±3–4 dari Gemini TIDAK diadopsi tanpa uji historis
DunkAPI). Lihat `REFERENSI-GEMINI-2026-11-23.md` untuk angka
lengkap (vonis 6 laga, racikan, debat, kode tiket).

**INSIDEN DENVER (pagi 23 Nov) — titik balik seluruh percakapan.**
User memasang 2 tiket nyata total $30 (berdasar racikan Gemini):

- **Asuransi 2,17x, $15** (kode `1g1URyNC1l`): OKC U242.5,
  DEN U252.5, DAL U240.5, BOS U225.5.
- **Utama 3,72x, $15** (kode `D3pDLoyL4V`): OKC U238.5,
  DEN U250.5, DAL U238.5, ORL U235.5, IND U230.5, BOS U223.5.
  (User menambah IND sendiri melawan saran Gemini, buru-buru
  3 menit sebelum tip-off.)

Audit mesin pra-laga: Asuransi peluang gabungan 58,0%, EV +25,9%;
Utama 34,8%, EV +29,3%; **DEN kaki terlemah** (84,5%, edge +2,5%);
ORL satu-satunya overpay (−4,7%).
**HASIL: KEDUA TIKET KALAH.** DEN@CHI selesai 296 (overtime) —
43,5 di atas garis Asuransi, 45,5 di atas garis Utama. 3 poin
42-dari-90 (47%), 126 poin dari 3 poin saja. 8 dari 10 kaki lain
menang. $30 hilang. User (06:12 WIB): "jadi 30 dolarku udah hilang
yaa ini" — dan Gemini mengaku salah memasukkan DEN ke Asuransi
(padahal sejak awal sudah dilabeli KUNING).
Pelajaran yang dirumuskan user sendiri (08:14 WIB): "nah ini lah
bro guna nya mesin, untuk benar2 melihat analisis secara mendalam,
dan menjadi dasar agar tidak bias. aku sudah tanya ke gemini kenapa
dia menyarankan pertandingan ini ke asuransi, dia menjawab bahwa
dia memang salah." Lima pelajaran mesin: (1) label tanpa gate cuma
kata-kata — DEN lolos semua gate mesin pra-laga, gate butuh aturan
edge minimum; (2) kaki terlemah menentukan tiket — audit mesin
sudah menandai DEN terlemah tapi tidak bertindak; (3) sim tidak
punya skenario ekor (banjir 3 poin) — deviasi +28 di luar dunia
model; (4) modul audit tiket nyata sebelum pasang BELUM ADA —
andai ada, kaki DEN akan dicek ke gate volume; (5) proyeksi live
butuh blend median pra-laga. Gemini menyarankan JANGAN mengejar
$30 di hari yang sama — user setuju. Tiket diselesaikan di ledger
(R4, 11:11 WIB): keduanya LOSS −$15; 10 kaki, 8 menang — 10 kaki
NYATA pertama modul belajar.

**Fondasi harga & pengali (08:19 WIB — MENGGANTIKAN target
racik-fix).** Kata-kata user: "aku lebih baik beli kaki diharga
mahal misal 89c dan itu dalam perhitungan statistik adalah angka
yang bisa diterima, dan beli asuransi di 94c pun aku gak ada
masalah. yang penting semua tiket lolos, dan racikan nya asuransi
ada di x2 atau lebih dikit, dan tiket utama ada di x3 atau lebih
dikit. jadi keberuntungan jika analisis menunjukan bisa tembus x4
sampe x5." → **Tidak ada price cap**; harga mahal boleh asal
statistik mengizinkan; target Asuransi x2 atau lebih dikit, Utama
x3 atau lebih dikit; x4–x5 keberuntungan. Prioritas utama: SEMUA
tiket lolos. Analisis mendalam sebelum pasang harus menjawab per
laga: apakah masing-masing tim akan sangat-sangat panas? Bila
panas, apakah harga 82¢ bisa tembus? Apakah 94¢ bisa tembus?

**Perbaikan pasca-Denver (selesai 08:48 WIB, commit `11ed42e`+
`8fbae0a`, config v14, 1481 tes):** 5 item — (1) audit tiket
sebelum pasang (`cli.py audit`; tiket Asuransi nyata user → NO-GO,
DEN JANGAN_PASANG); (2) skenario panas (banjir FT + banjir 3P +
setan; DEN di 82¢: banjir FT 54,3% GAGAL; di 94¢: 76,6% LOLOS;
garis tahan-banjir Asuransi 264,5 @94¢ — yang ternyata tetap kalah
31,5 poin hari itu, karena banjir hari itu di atas p99);
(3) gate edge minimum 3,5% untuk Asuransi (proposal D12);
(4) fondasi v14 (pengali baru); (5) pantau blend (median pra-laga).
Bug pantau diperbaiki 09:22 (commit `5350315`, fail-first): kaki
yang total berjalannya sudah lewat garis kini langsung KALAH,
bukan TERANCAM.

**Aturan keras + 3 build (selesai 10:16 WIB, commit `c361a04`+
`1315ad5`+`a84a249`, config v15, 1537 tes).** Lima aturan keras
diusulkan; gate banjir Asuransi (R1) disetujui user. R1: kaki
Asuransi wajib lolos skenario banjir (P ≥ 74% di bawah banjir,
bukan hanya normal). R2: laga berisiko hanya di Utama, tidak
pernah di Asuransi. R3: jangan isi tiket demi pengali. R4: setiap
hasil tiket masuk ledger untuk kalibrasi. R5: blacklist POLA, bukan
tim (edge kecil + rapuh-banjir + volume tipis). Build yang
dijalankan 09:47: (1) gate banjir Asuransi (DEN U252.5 kini ditolak
54% di bawah banjir; garis tahan-banjirnya 264,5 @94¢ dilewati
karena tipis); (2) skenario "setan" deviasi maksimal — sebagai
DETEKSI, bukan gate (setan_points 18,07 dari 243 laga selesai,
maks 40 tiga-poin-per-laga); (3) sharp-move bukan diskon (kasus
Thunder: beli 75¢, jatuh ke 71¢ 1 jam sebelum tip-off, Gemini
bilang "diskon", Under-nya jebol — penurunan tajam menjelang
tip-off adalah PERINGATAN, bukan diskon; gerak 2¢ tetap DISKON,
3¢ ditekan).
**Koreksi user 09:52 WIB** (durable): skenario setan BUKAN gate
keras — gate keras Asuransi tetap banjir p90 + edge + volume +
min_leg_prob (batas ketat yang MASUK AKAL; bukan semua laga
dianggap anomali). Kaki lolos gate banjir boleh dipasang di harga
tinggi walau rapuh-setan, asal risikonya TERLIHAT; bila setan
datang, "kalah dengan terhormat". Strategi: tumpuk BANYAK kaki di
harga tinggi asal tiap kaki fundamental kuat.
**Koreksi harga 10:14 WIB** (koreksi kedua): 89–94¢ adalah
HIPERBOLA, BUKAN target — jangan dorong semua kaki ke sana, jangan
ada logika "prefer harga tinggi". Prinsip: **HARGA MENGIKUTI
STATISTIK** — tiap kaki masuk akal secara statistik + lolos semua
uji + tahan anomali; garis dipilih = termurah yang lolos SEMUA
gate, naik hanya bila gate gagal di bawah. Kendala matematika:
dengan sedikit laga (mis. 5), semua kaki di 80¢+ tidak bisa
mencapai x2/x3 — komposer menyeimbangkan harga vs target pengali.
**Temuan struktural build ini:** di slate nyata 10 kaki, gate
banjir + edge bersama-sama lolos 0/10 — gate banjir mendorong
harga ke 89–94¢ di mana edge mengecil secara mekanis; bahkan satu
kaki yang lolos banjir (OKC) gagal edge +1,3% vs batas 3,5%.
Nilai banjir p90 di config (13,54/17,54) ternyata terkontaminasi
4 laga live — nilai bersih 8,50/12,52 (config sengaja tidak diubah
saat itu; dikoreksi di v17).

**Prinsip skip-dari-awal (10:22 WIB):** laga yang anomali/tidak
masuk akal dari awal, atau berpotensi overtime, di-skip dari KEDUA
tiket — pertahanan adalah SELEKSI, bukan harga (bukti: final
Denver 296 menembus bahkan garis 94¢). User meminta pertanyaan
gate dalam bahasa sederhana — dia tidak paham istilah teknis.
**Jawaban gate 10:31 WIB — TETAP KETAT, lewat equilibrium:**
mesin harus menghitung titik equilibrium per kaki — sweet spot di
mana distribusi normal bilang kaki itu paling baik (ilustrasi
user: Asuransi sekitar 85¢, Utama 75–78¢); anomali ekstrem boleh
menyeret harga ke 94¢, tapi titik pasang duduk di distribusi
normal; laga tanpa equilibrium sama sekali (seperti Denver)
di-skip dari awal.
**Inventaris jujur mesin (saat ditantang user "apakah mesin
benar-benar menghitung semua yang dibutuhkan"):** mesin PUNYA
statistik tim (musim + 10 terakhir, disesuaikan lawan), laporan
pemain (BPM × menit + pengganti + shrinkage), form5, kandang/tandang,
istirahat/B2B, altitude, cedera 2 sumber, simulasi 100.000x,
peluang OT, garis pasar, volume, banjir/setan. Mesin TIDAK PUNYA:
news sama sekali (lubang nyata — kasus Thunder adalah news),
3 poin per tim/per pemain di simulasi, bentuk ekor per laga
(satu sigma global), titik equilibrium itu sendiri (komposer
mengambil garis termurah yang lolos), dan peluang OT dihitung tapi
tidak dipakai di seleksi.
**Perintah build 10:41 WIB:** kelima gap dibangun sekaligus —
equilibrium, skip-dari-awal, news, ekor 3P per laga, OT di seleksi
— news sebagai bahan pasang (cedera, berita tim, penguat argumen;
berita buruk = bahan baca + analisis), dan SEMUA laga dilaporkan
termasuk yang di-skip beserta alasannya.

**Penyempurnaan mesin / perfection build (selesai 11:21 WIB,
commit `05dcf4b`+`be7371f`, config v16, 1698 tes):**
equilibrium = max-ER di antara garis lolos-gate, p_final dihitung
ulang di garis baru (EQ Utama 10/10 di 75–78,5¢ — cocok dengan
intuisi user; EQ Asuransi 0/10 — gate pengikat: volume 7, edge 2,
banjir 1); skip-dari-awal (3 pemicu termasuk pola Denver + OT
tinggi ≥ 0,028 AWAL); modul news (`ingest/news_nba.py`, JSON ESPN
PAKAI, konteks saja, tidak pernah jadi angka); ekor 3P per laga =
HASIL NULL (slope −0,3364, t=−0,17, R²=0 — laju 3PA TIDAK
mempengaruhi ekor; banjir DEN adalah lonjakan dalam-laga, 3PA
pra-laga persentil ke-29); OT di seleksi.

**Build v17 (selesai + terverifikasi 13:25 WIB, commit `c1c641e`+
`9c8a0c2`, config v17, 1806 tes):** sistem vonis (9 demerit
indikator-Denver + 4 pemicu keras; HIJAU = 0 demerit); veto keras
(rim protector OUT terkonfirmasi + garis ≥235 ATAU pace ≥102 →
KUNING, blokir kedua tiket); tanpa-kaki-kembar di komposer;
equilibrium Asuransi safety-first; setan per pemain (total setan
DEN@CHI 274,14, diverifikasi tangan; 3P% terbaik liga 54,1% Cam
Spencer; kedua kaki DEN ditandai rapuh P≈0,12–0,13; aktual 296
tetap di atas setan — setan menandai kerapuhan, bukan memprediksi);
pergeseran banjir bersih (8,50/12,52); deviasi dilaporkan sebagai
poin di atas garis pasar. Vonis di slate uji: **HIJAU 0 /
MENENGAH 2 (DAL, BOS) / KUNING 8**; veto menyala 3 baris (DEN
verif via Claxton ✓, OKC ×2 via Holmgren — false positive, kaki
OKC menang). **Asuransi TETAP 0/10** (hanya OKC lolos banjir tapi
gagal edge +1,3% < 3,5%). Celah wiring ditemukan+diperbaiki:
`nba_analysis.py` Tahap 5c mengisi `setan_pemain` (tanpa itu
analyze fallback ke setan generik). Peta rim protector: top-2 BPG
per tim (GP ≥3, MP ≥15, BLK ≥0,8). Koreksi Mara: Aday Mara ADALAH
pemain rotasi OKC (16 laga, 22,4 mpg, 1,7 BPG, rim protector #2
OKC); ketidakhadirannya di laga itu tetap UNVERIFIED.

**Keluhan bias user (13:33 WIB) — titik balik kedua:** "bro tapi
ini hasilnya sangat2 bias bro, semua ditandai kuning alih2 ada yang
lolos, coba gini deh bro buat pertanyaan, dan kamu pertama harus
jujur dulu dengan mesin kamu. setelah itu buat pertanyaan dan minta
audit kepada gemini..." Kritik jujur Muse (disampaikan + di rekap
§5): (1) mesin dibangun dari SATU kekalahan — melihat Denver di
mana-mana; (2) HIJAU = 0 demerit adalah standar KESEMPURNAAN,
bukan standar taruhan (volume garis jauh selalu tipis — sifat
pasar); (3) demerit menghitung-ganda fakta berkorelasi; (4) ambang
adalah tebakan AWAL, tidak pernah dikalibrasi (bukti: 5 dari 6
laga KUNING menang). Yang mesin lakukan dengan BENAR: menangkap
Denver, setan per pemain, tanpa-kembar, audit jujur, sim solid,
fail-closed. Rekap disampaikan: `REKAP-MESIN-UNTUK-GEMINI.md`
(333 baris, commit `e174069`) dengan 10 pertanyaan audit untuk
Gemini.

**Audit Gemini atas v17 + proposal v18 (diterima 13:47 WIB,
`REFERENSI-AUDIT-GEMINI-V18.md`, commit `ad2cfa0`).** Muse
memverifikasi matematikanya — SEMUA klaim kunci BENAR: deadlock
Asuransi (garis tahan-banjir = +24,86 di atas median; t(0,74,35)=
0,6498; 3 aturan bersama mengunci Asuransi di 0/10); bias edge
datar di ekor (angka edge konsisten dengan harga ASK); jendela
selisih terjepit 4,0–5,0; **miskalibrasi OT — P(OT) sim dibatasi
2,74% di spread 0, jadi pemicu keras 2,8% hanya mendeteksi noise
Monte Carlo (OT NBA nyata ~5,5–6%)**. Klasifikasi slate Gemini:
HIJAU BOS/OKC/ORL, MENENGAH DAL/IND (TUNGGU_LINEUP), KUNING hanya
DEN — koheren dengan hasil. Proposal v18: EV ≥ −1% mengganti edge
datar; banjir 70%/65%; Asuransi p_final 0,82 + p_market 0,80;
veto AND + filter posisi; HIJAU = 0 veto + ≤1 demerit + ≥1 rem
(5 rem: pertahanan Top-10 / pace Bottom-12 / pencetak besar OUT
kedua tim / paint utuh + blowout |spread| ≥8,5 atau FTr rendah /
selaras-market); volume → gate eksekusi berbasis stake; cap setan
min(50%, musim%+12pp); gate waktu TUNGGU_LINEUP; OT empiris;
short-circuit pemindaian jup.ag untuk laga veto; tampilan 3 lapis
+ kalimat "skenario kematian". Tes penerimaan: 5 target.

**4 keputusan user atas v18 (13:57–13:59 WIB):**
(1) Target Asuransi TETAP x2 (TOLAK minimum 1,80x Gemini;
`must_cover_total_stake` tetap) — "x2 satu satunya jalan yang bisa
selamatin modal kita"; cari laga yang benar-benar pasti menang.
(2) Banjir 70%/65% + EV ≥ −1% DISETUJUI.
(3) Minimum p_final Utama 0,74 DISETUJUI (harus tetap mencapai
x3–x5; "bukan uji ketat ketatan, tapi mencari kaki paling masuk
akal" — Denver tidak masuk akal dari awal tapi tetap dimasukkan;
Gemini dan Muse sama-sama mengakuinya).
(4) Veto AND DISETUJUI eksplisit 13:59 ("pake AND yang diusulkan
gemini, aku setuju") setelah penjelasan Muse dengan kata sederhana;
ambang 232,0/100,5 ditandai AWAL (difit dari 2 titik data — risiko
overfitting).

**Build v18 (selesai + terverifikasi 15:30 WIB, commit `e31c487`,
config v18, 2003 tes):** 10 item Gemini dibangun. Vonis:
**HIJAU 5 / MENENGAH 0 / KUNING 1 / TUNGGU 4** (v17: 0/2/8);
EQ 10/10 kedua tiket; false positive **0/5** (v17: 4/5); DEN
tertangkap via veto AND (verif KUNING; live TUNGGU_LINEUP); OKC
lolos (garis 231,5 < 232,0). Penerimaan: T3+T4 lolos; T1+T5 lolos
fungsional/dirumuskan ulang (T5: pemindaian jup.ag tingkat slate,
tidak bisa short-circuit per laga; hemat terukur 6,85 dtk/laga);
**T2 GAGAL jujur — tidak ada tiket terbentuk (maks x1,36 Asuransi /
x1,85 Utama)**. Revisi koordinator (menunggu keberatan): gate
eksekusi = likuiditas ≥ $30 + spread ≤ 5,0¢ + ask nyata (BUKAN
volume kumulatif — bukti: DET U239.5 bid 79/ask 82, likuiditas
$36.580, volume kumulatif $5, diblokir gate volume padahal order
$15 terisi; dampak EQ Asuransi 3/10 → 10/10); sisa HIJAU mengalir
ke Utama; CDF efektif Vegas kanonis (shrinkage 0,5).
**Temuan utama: penghalang sekarang adalah JUMLAH KAKI, bukan
ambang** — skip pola Denver memblokir 4/7 laga live, 3 di antaranya
(OKC, ORL, IND) MENANG di garis EQ; kondisi (4) skip masih memakai
edge datar lama < 3,5%. Keterbatasan: peta rim hanya 21/30
(9 hilang: ATL, DET, GSW, HOU, IND, LAC, NYK, ORL, PHX — 3 laga
besok buta-veto); HIJAU DAL di ujung pisau (DRtg 112,8 vs batas
112,9); demerit foul belum teruji di data nyata (FTr None di
artefak 22 Nov); skip keras OT DORMAN (p empiris = 0,0575 ×
exp(−spread²/(2×14,4307²)), maks 0,0575 < ambang 0,085).

**Review Gemini atas v18 + spesifikasi v18.1 (diterima 15:42 WIB,
`REFERENSI-PATCH-V18-1-GEMINI.md`, commit `a6a0d93`).** Gemini
setuju 100% memperbaiki skip_awal + menyetujui semua keputusan
koordinator v18 (§5.1–§5.10, §6(B); prior OT 0,0575 TIDAK BOLEH
berubah tanpa data fit). **Temuan kritis baru — "jebakan plafon
88,5¢":** safety-first di dalam band 80–89¢ selalu memilih plafon
(P_final monotonik terhadap harga); Muse memverifikasi tabel
pengali Gemini PERSIS (88,5¢ butuh 7 kaki untuk x2; 86¢ → 5;
84¢ → 5; 82¢ → 4). Solusi TANPA melonggarkan gate: equilibrium
mengembalikan SEMUA garis valid; komposer memilih kombinasi yang
memaksimalkan peluang gabungan P_final di dalam [2,00x, 2,50x],
fallback dilaporkan [1,80x, 1,99x]. Patch #1 perbaikan skip: edge →
EV < −1%; "tipis" → cek_eksekusi; setan pemain; pagar
anti-redundansi (skip menyala hanya bila rapuh-setan P_setan < 0,55
DAN total market ≥ 232,0 DAN tidak ada garis valid lolos
banjir+setan). Patch #3 peta rim 30/30 (diagnosa kode BBRef vs NBA
PHO/PHX dll + normalisasi nama; tier fallback terukur top-1 C/PF,
min ≥18, BLK ≥ 0,7, berlabel `tier: "fallback"`). Patch #4 filter
kesegaran: OUT dihitung sebagai penyebab cedera segar hanya bila
GP ≥ 3 musim ini (absen jangka panjang seperti Haliburton sudah
terhitung di harga). Patch #5: pulihkan MENENGAH (evaluasi
tail_fragility di garis referensi standar ~82¢, bukan plafon
88,5¢) + simetri D7 (mp ≥ 15,0 di KEDUA jalur USG dan BPM).
5 kriteria penerimaan (§4).

**User memilih fallback (b) (15:52 WIB):** fallback = OPSI YANG
DILAPORKAN (bukan diracik otomatis, bukan NO BET) dengan pengali +
peluang gabungan P_final + detail per kaki + alasan tidak mencapai
x2; keputusan pasang/tidak adalah miliknya. Target Asuransi tetap
[2,00x, 2,50x]. Filosofi "pasti menang" (kata-kata user): "aku
pilih b, karna gk mungkin no bet hanya karna gagal menemukan
kombinasi pertandingan yang mustahil dipenuhi banyak anomali. karna
secara nyata gk mungkin 5 atau 4 tiket di harga 82c hangus secara
bersamaan... yang pasti menang itu bukan yang posisinya mustagil
di capai, tapi untuk sampai kesana butuh penyimpangan yang cukup
tinggi. jadi aku ingin asuransi didudukin oleh kaki2 yang secara
perhitungan masuk akal dan tetap aman dan tebal dari penyimpangan."
→ "Pasti menang" = BUKAN posisi mustahil, tapi posisi yang
membutuhkan penyimpangan TINGGI untuk jebol. Anomali ekstrem =
risiko yang diterima ("kalah dengan terhormat"). Bahkan 99¢ pun
tidak akan menyelamatkan Denver yang dipasang 1 menit sebelum
tip-off → pertahanan adalah seleksi + bantalan tebal, bukan harga.
Dia TIDAK mau penghindaran brutal/kaku — dia mau MEMASANG dengan
risiko ditekan serendah mungkin.

**Build v18.1 (selesai + terverifikasi 16:36 WIB, commit `9d52646`,
docs `d509252`, config v18.1, 2111 tes, ruff+black bersih,
0 kredit):** 5 patch + fallback (b). Penerimaan **4/5**: K1 lolos
fungsional (DEN diblokir kedua baris; OKC/ORL/IND bebas pola);
K3 lolos (peta rim **30/30**, 9 tim fallback = tepat 9 tim yang
hilang); K4 lolos (GP==0 tidak memicu; kontrol GP=10 memicu);
K5 lolos (nol regresi); **K2 GAGAL literal — tiket x2 tetap tidak
terbentuk di slate uji (maks x1,86, 4 kaki; garis termurah lolos
gate 83¢) TAPI fallback DILAPORKAN sesuai desain (b): x1,8015,
peluang gabungan 0,5107 (konservatif — pakai decision_prob;
Π p_final = 0,5402), 4 kaki (BOS 227.5 @83¢, DAL 242.5 @84¢,
DET 243.5 @85.5¢, ORL 241.5 @88¢), semua lolos 100% gate**.
Utama maks x2,30 (naik dari x1,85). Perbaikan jebakan plafon
TERBUKTI di fixture: v18 x1,54 (tanpa tiket) → v18.1 **x2,04**
(4 kaki @82,5¢, peluang gabungan 0,7476); runtime komposer 0,07
detik (DP atas bucket log-pengali).
**Temuan utama: pola Denver kini menyala 0/10** — kondisinya
(2)/(3)/(4) dibangun di atas premis era v16 (garis jauh tipis +
edge datar) yang sudah dibatalkan pengukuran v18 sendiri (orderbook
market-maker dalam, EV ≈ impas); S1 menyala 10/10 baris (tidak
membedakan DEN — ORL memenuhi LEBIH BANYAK kondisi daripada DEN).
DEN tetap diblokir secara fungsional (veto + TUNGGU_LINEUP). Pola
butuh DESAIN ULANG berprinsip — pengukuran v18.1 dikirim ke Gemini
untuk iterasi (BUKAN penghalang besok). Keputusan koordinator
menunggu keberatan: batas 6 kaki DIPERTAHANKAN per spesifikasi;
nama kunci `joint_p_final` menyesatkan (nilainya Π decision_prob —
benar + konservatif; follow-up ganti nama kecil); Haliburton punya
GP=4 di artefak nyata (+ missed_last10: 10) sehingga filter GP≥3
TIDAK mengecualikannya — follow-up: aturan 14 hari/missed_last10
(mempengaruhi laga IND; IND main besok vs OKC); garis referensi
tail_fragility difilter cek_eksekusi (menghindari garis sampah
U117.5); kondisi pagar (3) tahan-setan = P_setan ≥ 0,55 (AWAL).
Keterbatasan: artefak uji tidak punya blok setan_pemain/veto (jalur
pemain + blok veto hanya diuji fixture); pagar tidak pernah
diterapkan di slate uji (bukti fixture saja); MENENGAH 0/10 di
slate ini; demerit foul belum teruji di data nyata; veto bergantung
data cedera SEGAR. Laporan: `LAPORAN-V18-1.md` (+ laporan worker
A/B/C).

**v18.1 DIBEKUKAN + batas 6 kaki DIPERTAHANKAN (user 16:44 WIB):**
"v18.1 oke banget, langsung pakai buat besok pagi (nggak usah
diubah lagi malam ini). Soal usulan naik ke 8 kaki, aku tahan dulu
di 6 kaki — soalnya hitungan 60% vs 52% itu pakai asumsi 0,93^7
(+4,5% edge di ekor 88,5¢ per kaki) yang nggak realistis; di vig
pasar nyata dan keunggulan model yang sama, nambah jadi 7–8 kaki
justru kena akumulasi spread per kaki dan bakal memakan jatah laga
Tiket Utama (karena aturan tanpa kaki kembar)." Usulan 8 kaki
(koordinator, perbandingan 0,93^7 vs 0,85^4) DITOLAK — asumsi edge
ekor +4,5% adalah kekeliruan edge-datar yang sama yang sudah
dibunuh audit Gemini. Muse mengakui: perbandingan itu disajikan
tanpa menangkap asumsi yang tidak realistis.
**Daftar iterasi v18.2 (user, SETELAH hasil live besok — bukan
malam itu):** (1) pindahkan `_DP_MAKS_KAKI` ke config, tetap 6
(atau evaluasi ulang setelah data ledger); (2) kesegaran cedera
GP ≥ 3 DAN missed_last10 ≤ 5 (kasus Haliburton: GP=4 tapi
missed_last10=10 → dikecualikan); (3) ganti nama joint_p_final →
joint_p_keputusan; (4) desain ulang skip_awal khusus menangkap
ledakan total-tinggi + risiko volume 3P + P_setan < 0,55 (tidak
mengulang cek EV/eksekusi). Dicatat di DECISIONS.md
(commit `6a616dc`).

**Uji coba preview v18.1 slate 24 Nov (perintah user 16:47 WIB;
jalan 16:58 WIB):** analyze hanya **3m33s** untuk 10 laga (jauh
di bawah perkiraan ~35 menit), 0 kredit Odds API (--tanpa-odds-api).
Vonis: **HIJAU 3 (OKC, PHX, LAC) / MENENGAH 2 (POR, UTA) /
KUNING 4 (MEM, MIL, BKN karena data; CLE veto) / TUNGGU 1 (SAS —
Wembanyama Questionable, BPM +14,2)**. **TIDAK ADA tiket + TIDAK
ADA fallback** (Utama maks x1,13) — penyebab: 8/10 laga HOLD +
1 DATA_INCOMPLETE (CLE) + hanya UTA OK. Akar HOLD: (a) konflik
cedera PDF vs ESPN (11 pemain); (b) **INKONSISTENSI DUA JALUR —
pembuat kaki artefak legacy masih memakai gate volume kumulatif
lama (≥$100) sementara equilibrium v18 memakai likuiditas+spread**
→ `volume_tipis` di 8 laga; TIDAK memperbaiki diri sendiri —
kandidat v18.2 / pertanyaan Gemini; (c) Kalshi tidak memberi
p_market untuk 4 laga (MEM, MIL, BKN, SAS — fetch OK, pencocokan
garis gagal) → jalan besok DENGAN Odds API. Yang BEKERJA: veto
AND menangkap CLE@CHI (Mobley OUT 2 sumber + 240,5 + 103,03);
cek Vegas menyusutkan median mentah OKC@IND 200,0 → 210,75
(selisih 21,5 poin — anomali terbesar); demerit foul teruji di
data nyata pertama kali (POR 0,321 / UTA 0,318 ≥ p80 0,308);
setan pemain OK di 9 laga; log bersih. CACAT PEMBANGUN (v18.2):
build_slate mengembalikan DUPLIKAT BKN@MIN (11 baris untuk 10
laga); output build_slate tidak bisa langsung masuk analyze
(skema menolak kunci ekstra). File:
`out/slate_preview_2026-11-24.json`,
`out/analysis_preview_2026-11-24.json`,
`out/tickets_preview_2026-11-24.json`,
`out/laporan_preview_2026-11-24.txt` (2.527 baris). Dicatat
(commit `c0cea5f`).

**Pertanyaan Gemini disiapkan (proaktif, disampaikan 17:07 WIB):**
teks copy-paste menanyakan apakah pembuat kaki harus disatukan ke
cek_eksekusi dan gate volume kumulatif dibuang, dengan bukti
DET U239.5 (bid 79/ask 82, likuiditas $36.580, volume kumulatif
$5 — order $15 tetap terisi).

**Jawaban Gemini soal gate volume + 5 temuan preview (user
teruskan 18:55 WIB; DIVERIFIKASI Muse dari laporan/artefak
preview, BUKAN diterima begitu saja):** (1) Gemini SETUJU PENUH —
pembuat kaki harus disatukan ke cek_eksekusi; gate volume kumulatif
≥$100 harus DIHAPUS sebagai pemblokir (diturunkan ke catatan L3);
"bug split-brain"; mengklaim masih akan memblokir kaki Asuransi di
OKC/MEM/MIL/BKN/SAS besok pagi bahkan dengan Odds API. 4 risiko
yang harus dijaga di cek_eksekusi v18.2: (a) likuiditas agregat
vs top-of-book — bila ask_depth (dalam +2¢ dari ask terbaik)
ada, wajib ≥ 2× stake ($30); bila hanya likuiditas_gamma agregat,
naikkan lantai ke **$250–$500**; (b) cek kewarasan monotonisitas
tangga — ask(L) ≥ ask(L−2) − 1¢; (c) book satu sisi — bid > 0
dan ask < 0,99 eksplisit; (d) kalibrasi max_spread 5,0¢ dari
catatan isi nyata besok pagi. (Catatan: ringkasan "siap kirim"
Gemini hanya mencantumkan 3 risiko — yang ke-4 (kalibrasi spread)
ada di teks utama.) (2) **Kontradiksi HIJAU-tanpa-EQ-Asuransi —
DIKONFIRMASI PERSIS**: PHX + LAC dinilai HIJAU padahal EQ Asuransi
= None (PHX terbaik U257.5 @91¢ EV −1,6%; LAC U250.5 @93.5¢
EV −10,8%); vonis fallback ke garis EQ Utama (banjir FT 57,9% /
41,7%). Aturan v18.2: tanpa EQ Asuransi valid, vonis maks
MENENGAH. (3) **HOLD konflik cedera pemain pinggiran —
DIKONFIRMASI** (Grant Nelson, Bryce McGowens, Adem Bona, Dean
Wade, Collin Murray-Boyles, Jaylon Tyson); aturan v18.2: konflik
bintang (mp ≥15 & BPM ≥+1,0, atau OUT vs AVAILABLE) memicu HOLD;
konflik kecil PROBABLE (Official NBA, tier 1) vs QUESTIONABLE
(ESPN, tier 2) menjadi catatan L3 (tier 1 menang). (4) **Bug
parser PDF ("row leak") — DIKONFIRMASI VERBATIM 4/4:** "NOT YET
SUBMITTED" dari laga lain bocor ke komentar pemain (Murray-Boyles
OKC@IND, Ernest Udeh Jr. Chicago Bulls, Austin Reaves
DET@ORL/BOS@WAS/DAL@DEN, Ben Simmons UTA@LAL); bukti korolari:
Laporan Cedera Resmi NBA untuk OKC@IND memang BELUM DISERAHKAN
saat preview. (5) **Misteri OKC@IND −21,5 — BUKTI DIKONFIRMASI,
MEKANISME HIPOTESIS**: total model 199,1 (laporan: IND 102,1 +
OKC 97,0) vs median sim mentah 200,0 (blok Vegas) — dua kuantitas
berbeda, bukan kontradiksi; 13 pemain absen/diragukan (daftar
persis termasuk Haliburton/Holmgren/Jalen Williams); "out for
Sunday's game against the Heat" basi dari ESPN dikonfirmasi
verbatim (SGA, Mara, Caruso, Jaylin Williams, Topic, McConnell).
Hitung-ganda cedera jangka panjang (sudah di rating tim, lalu
dikurangi lagi via BPM) + DBPM defender elit memotong proyeksi
total = HIPOTESIS YANG MASUK AKAL dari Gemini, butuh investigasi
desain v18.2 (BELUM terbukti). "Skenario semua-tersedia ~220" =
perkiraan Gemini, BUKAN angka mesin (laporan tidak punya skenario
semua-tersedia). (6) **Bug tampilan DIKONFIRMASI**: pemenang H2H
terbalik di 4 laga (TOR 121–107 MIL ditulis MIL menang; CHI
115–126 CLE ditulis CHI; LAL 132–123 UTA ditulis UTA; SAC 103–130
SAS ditulis SAC — plus hitungan menang/kalah salah); flag "Bermain
di kota dataran tinggi" menyala di Utah (tandang) di UTA@LAL yang
dimainkan di Los Angeles (flag harus soal LOKASI LAGA, bukan kota
kandang tim tandang). H2H tidak memengaruhi vonis, jadi ini bug
tampilan/kepercayaan. **Rencana besok (disepakati dengan Gemini):**
tetap jalan v18.1 + Odds API dulu; bila kaki Asuransi masih
diblokir volume_tipis, evaluasi bersama dari angka Equilibrium
Asuransi sebelum mengeksekusi v18.2. Gemini menawarkan cross-check
laporan segar (~05:30–06:15 WIB) — angka EQ Asuransi + status
laporan cedera final — sebelum user klik pasang di jup.ag.
Dicatat di DECISIONS.md (commit `aca2971`).

### 2.5 Selasa 24 Nov 2026 — Analisis segar 04:23 WIB, tidak ada tiket, recheck dijadwalkan

**Slate hari ini (US Senin 23 Nov; scoreboard ESPN terverifikasi
live 23 Nov):** 07:00 MEM@CHA, POR@PHI · 07:30 OKC@IND, MIL@TOR,
BKN@MIN · 08:00 CLE@CHI, PHX@NOP · 08:30 LAC@HOU · 10:00 UTA@LAL,
SAS@SAC. (Rabu 25 Nov pagi: hanya 3 laga — DET@ORL, BOS@WSH,
DAL@DEN.)

**User membatalkan jadwal 05:00 dan memerintahkan jalan segar
SEKARANG (04:23 WIB):** "muse batalkan jam jadwal jam 05.00
sekarang coba cek data realtime sekarang, ada info apa dan kaki2
mana yang akan kita pasang?" Cron `slate-selasa-05-00` (runonce
2026-11-24T05:00:00, owner goal:new-agent-machine) **DIHAPUS**.
Analisis segar v18.1 jalan DENGAN Odds API (analyze 4m23s,
Odds API 1 panggilan / 3 kredit, **sisa 484/500**).

**Hasil analisis segar (terverifikasi, dilaporkan ke user 04:35
WIB): TIDAK ADA TIKET + TIDAK ADA FALLBACK** (Utama maks x1,17 —
hanya UTA lolos). Vonis: **HIJAU 2 (PHX, LAC) / MENENGAH 1 (UTA)
/ KUNING 4 (MEM, MIL, BKN, CLE) / TUNGGU 3 (POR, OKC, SAS)**.
Status: 7 HOLD + 1 DATA_INCOMPLETE (CLE, veto) + 2 OK (BKN
MODEL_ONLY tanpa jangkar pasar; UTA). INFO BARU vs preview:
**Shai Gilgeous-Alexander KEMBALI BERMAIN** (tidak ada di daftar
cedera OKC); selisih OKC menyusut 21,5 → 14,5 (median 200,0 →
209,0; garis pasar 221,5 → 223,5) dengan **TIDAK ADA shrinkage
Vegas kali ini** (selisih kini punya penjelasan cedera); Laporan
Cedera Resmi NBA OKC@IND KINI SUDAH DISERAHKAN; BKN HOLD → OK
(konflik Nelson teratasi, volume_tipis hilang — tapi MODEL_ONLY);
konflik teratasi: Dieng, Nelson, McGowens, Murphy III; konflik
baru: Jalen Smith (CLE); masih menahan: Miller, Bona/Brown/Wade,
Murray-Boyles, Tyson, Zion. **Embiid (POR, USG 29%) + Siakam
(OKC, USG 28%) Questionable** — baru di data segar. PHX KEHILANGAN
EQ Utamanya (EV terbaik −3,2%; EQ Asuransi memburuk −1,6% →
−3,2%) — kontradiksi HIJAU Gemini MASIH ADA. EQ Asuransi LAC
−10,8% → −10,9%. **SEPERTI DIPREDIKSI GEMINI: volume_tipis MASIH
memblokir 7 laga** (MEM, POR, OKC, MIL, PHX, LAC, SAS) — Odds API
TIDAK memperbaikinya; 4 laga MASIH tanpa jangkar pasar (MEM, MIL,
BKN, SAS) — Odds API fetch untuk 10 laga tapi hanya 5 laga yang
kakinya punya p_market (bandar belum memasang total di 4 laga itu
pada jam tersebut); veto CLE tetap menyala (garis 240,5 → 239,5;
Mobley OUT + pace 103,03); bug H2H + altitude masih ada.
**KANDIDAT LIVE UNTUK RECHECK (angka EQ saja, BUKAN tiket):**
OKC EQ Asuransi VALID (U245.5 @88.5¢, p_final 90,3%, EV 1,02) +
EQ Utama (U237.5 @77¢, p 81,7%, EV 1,06) — diblokir Siakam
Questionable + volume_tipis; UTA EQ Asuransi valid (U244.5 @86.5¢,
p_final 86,6%, EV 1,00) tapi vonis MENENGAH (→ Utama saja); POR
hampir lolos (terbaik U251.5 @86.5¢ EV −1,2% vs minimum −1,0%).
Insiden build slate: dedupe pertama salah (kunci (None,None)
meruntuhkan 11 laga jadi 1) — dibangun ulang dengan dedupe
match_id, 10 laga unik terverifikasi; bukti mentah 11 baris di
`out/slate_enriched_2026-11-24_raw.json`. File:
`out/analysis_2026-11-24.json` (1,8 MB),
`out/tickets_2026-11-24.json`, `out/laporan_2026-11-24.txt`
(2.516 baris), `out/analyze_2026-11-24.log` (0 error). Dicatat di
DECISIONS.md (commit `f54ac49`).

**Recheck kloter 07:00 DIJADWALKAN (proaktif, terverifikasi via
cron.view, disampaikan ke user 04:45 WIB):** cron
`recheck-kloter-0700-24-nov`, runonce **2026-11-24T06:25:00
Asia/Jakarta**, owner goal:new-agent-machine, delivery ke chat
ini. Isi: `cli.py recheck` untuk MEM@CHA + POR@PHI dengan laporan
cedera final (~30 menit sebelum tip-off) — fokus Embiid
Questionable + konflik Brandon Miller + apakah volume_tipis /
jangkar pasar membaik; bila ada vonis/status berubah, jalan ulang
racik dengan `--recheck` (stake-total 30) ke
`out/tickets_2026-11-24.json`; audit bila tiket terbentuk; lapor
vonis akhir + apakah tiket kini terbentuk (pengali, kaki, peluang
gabungan) atau tetap TIDAK ADA + saran keputusan (pasang/tunggu/
skip) dalam Bahasa Indonesia sederhana; TANPA commit; TANPA kredit
Odds API kecuali recheck membutuhkannya (catat bila dipakai).
Kloter berikutnya (07:30+) ditangani saat user kembali atau setelah
hasil recheck pertama.
**Peringatan jujur yang sudah disampaikan ke user:** volume_tipis
di garis jauh tidak mungkin membaik sendiri sebelum tip-off.

**Permintaan dokumen ini (05:00 WIB):** "bro buatkan.md
percakapan kita dari awal sampe terakhir sekarang juga, dan berikan
etimasi kapan kira2 selesainya. dan masukan juga code2 dan
konteks2 penting agar bisa dibaca AI lain arah percapakan nya ini
kemana" — dokumen ini adalah jawabannya.

---

## 3. Aturan user yang tidak bisa dilanggar

### 3.1 Sembilan aturan kerja

1. **Semua angka dari kode Python** — probabilitas, simulasi, EV,
   pengali. LLM TIDAK BOLEH mengarang/memperkirakan angka.
2. **Fetch data gagal = laga ditandai `DATA_INCOMPLETE`, tidak
   bisa masuk tiket.** Data kosong TIDAK PERNAH diisi tebakan.
3. **Hanya sumber data gratis.** API key di `.env`, tidak pernah
   di-commit, tidak pernah ditampilkan.
4. **Semua ambang & default strategi hanya di
   `config/playstyle.yaml`.** (Pengecualian yang diketahui:
   `_DP_MAKS_KAKI` = 6 masih konstanta kode — masuk daftar v18.2.)
5. **Satu pintu masuk: `cli.py`** — analyze / recheck / log /
   recap / laporan / tanya / racik / pantau / belajar / audit.
6. **Setiap modul wajib punya tes** (stdlib `unittest`; pytest
   tidak terpasang). Pre-commit hook menjalankan ruff + black +
   suite penuh — tunggu, JANGAN `--no-verify`.
7. **Jupiter: mesin READ-ONLY** — hanya endpoint GET. TIDAK PERNAH
   order/claim/apa pun yang menggerakkan dana.
8. **Kunci Jupiter + Odds API: HANYA di repo `.env`** (mode 600,
   gitignored); nilai tidak pernah direproduksi di mana pun.
   Mode keyed Jupiter 1 RPS + cache; fallback tanpa key 0,5 RPS.
9. **Belajar sendiri: mesin TIDAK PERNAH menerapkan perubahan
   parameter/ambang sendiri** — mengusulkan, user menyetujui
   (pola D12). (Prioritasnya dilonggarkan user 23 Nov 06:33 —
   belajar BUKAN prioritas lagi.)

### 3.2 Filosofi taruhan user (kumulatif, dengan kata-katanya sendiri)

- **Bettor konservatif.** Asuransi ~x2 (harus menutup total stake);
  Utama "agresif" versi dia = tumpuk banyak kaki 75–85¢ ke
  **x3–x4, x5 hanya bila data sangat optimis; x3,5 sudah berkah**;
  x9–x10 hiburan saja. Hindari moneyline kecuali fakta/data sangat
  kuat membuktikan pemenang.
- **Fondasi (23 Nov 08:19, menggantikan target pengali lama):**
  harga MAHAL boleh — kaki 89¢, Asuransi 94¢ pun tidak masalah
  asal statistik bilang bisa diterima; **TIDAK ADA price cap**;
  lantai 75¢ tetap. Target: Asuransi x2 atau lebih dikit, Utama
  x3 atau lebih dikit; x4–x5 KEBERUNTUNGAN bila analisis
  menunjukkan bisa tembus, bukan target. **Prioritas utama: SEMUA
  tiket lolos.**
- **Harga mengikuti statistik (10:14 WIB):** 89–94¢ adalah
  HIPERBOLA, bukan target — jangan dorong semua kaki ke sana,
  jangan ada logika "prefer harga tinggi". Pilih garis TERMURAH
  yang lolos SEMUA gate; naik hanya bila gate gagal di bawah.
- **Aturan TANPA-KAKI-KEMBAR (12:20 WIB):** satu laga TIDAK BOLEH
  muncul di kedua tiket (menggantikan "laga sama boleh, garis
  berbeda").
- **Skip-dari-awal (10:22 WIB):** laga anomali/tidak masuk akal
  dari awal, atau berpotensi overtime, di-skip dari KEDUA tiket —
  pertahanan adalah SELEKSI, bukan harga.
- **Equilibrium (10:31 WIB):** gate TETAP KETAT, dibingkai sebagai
  equilibrium — mesin menghitung sweet spot per kaki dari
  distribusi normal (ilustrasi user: Asuransi ~85¢, Utama 75–78¢);
  laga tanpa equilibrium sama sekali (seperti Denver) di-skip dari
  awal.
- **"Pasti menang" (15:52 WIB):** "yang pasti menang itu bukan
  yang posisinya mustagil di capai, tapi untuk sampai kesana butuh
  penyimpangan yang cukup tinggi. jadi aku ingin asuransi
  didudukin oleh kaki2 yang secara perhitungan masuk akal dan
  tetap aman dan tebal dari penyimpangan." Anomali ekstrem =
  risiko yang diterima — "kalah dengan terhormat".
- **Proses:** jangan paksa laga yang tip-off-nya mepet masuk
  tiket; analisis harus selesai ~30 menit sebelum tip-off
  (diusulkan Muse + independen oleh Gemini; belum disetujui
  eksplisit). Mulai analisis ~05:00–05:30 WIB. Laporkan SEMUA laga
  termasuk yang di-skip dengan alasannya.
- **Sejarah taruhan user** (screenshot, dihitung tangan 23 Nov
  12:20 WIB): 18 tiket 15–23 Nov, **10 menang, 8 kalah, net
  +$169,66 dari $223 stake (+76% ROI)**. Klaim user (13:06 WIB):
  **winrate Gemini benar-benar 90%** — hanya kalah 23 Nov;
  Asuransi selalu menyelamatkan posisinya sebelumnya. (Catatan:
  screenshot mencampur olahraga + tiket non-Gemini; 90% adalah
  soal tiket/pasangan yang dipandu Gemini.) 23 Nov adalah pertama
  kalinya kedua tiket dalam satu pasangan kalah bersamaan.
- **Kepercayaan pada statistik:** "statistik gak bisa bohong"
  (DECISIONS.md). User percaya data + statistik + berita; hindari
  kesalahan sekecil apa pun seperti Gemini. User menghitung ulang
  angka kunci sendiri dan menemukan cacat nyata (3 cacat racik
  04:05 WIB, koreksi jup.ag 22 Nov, asumsi 0,93^7 yang tidak
  realistis 16:44 WIB).
- **Tidak mau aturan brutal/kaku:** "gak seteknis dan seribet
  peraturan2 lu sama claude. yang paling penting disini adalah
  mesin penghitung statistiknya, dan mesin real yang bener2 bisa
  menghitung dan mengolah semua data dari internet, dari data
  valid, dari bursa taruhan..." (23 Nov 06:21 WIB, terpotong di
  chat). Mesin harus BENAR-BENAR JALAN dan bisa didiskusikan
  seperti LLM biasa.

---

## 4. Evolusi mesin

### 4.1 Peta versi

| Versi | Kapan | Tes | Commit utama | Isi |
|---|---|---|---|---|
| Tahap 1 | 20 Nov | — | (fondasi) | Struktur, config, SOP, skema, ledger |
| Tahap 2a | 20 Nov | — | (probe) | 13 sumber diprobe, 44 request |
| Tahap 2b | 21 Nov | 399 | `5cb229c` | 13 fetcher, analyze tersambung, devig |
| Harga pasar | 21 Nov | 406 | `6724d34` | DISKON/WAJAR/MAHAL, blend w=0,3 |
| T3 L1–L6 | 22 Nov | 613→1308 | `151b2c5`→`e880cc9` | Otak NBA, recheck, laporan+racik, pantau, otak bola, belajar |
| v13 racik fix | 23 Nov 05:10 | 1395 | `5b24c73` | Bantalan adaptif, harga-dulu, lantai 75¢ |
| v14 pasca-Denver | 23 Nov 08:48 | 1481 | `11ed42e` | Audit tiket, skenario panas, gate edge, fondasi baru, pantau blend |
| v15 aturan keras | 23 Nov 10:16 | 1537 | `c361a04` | Gate banjir Asuransi, setan (deteksi), sharp-move ≠ diskon |
| v16 penyempurnaan | 23 Nov 11:21 | 1698 | `05dcf4b` | Equilibrium, skip-dari-awal, news, ekor 3P (NULL), OT di seleksi |
| v17 vonis | 23 Nov 13:25 | 1806 | `c1c641e` | Vonis 9 demerit, veto rim, tanpa-kembar, setan per pemain, banjir bersih |
| v18 rebuild Gemini | 23 Nov 15:30 | 2003 | `e31c487` | EV ≥ −1%, banjir 70/65, veto AND, HIJAU baru, gate eksekusi |
| **v18.1** | **23 Nov 16:36** | **2111** | **`9d52646`** | **Skip EV, komposer valid_lines, fallback (b), rim 30/30, filter kesegaran, garis referensi tail** |

### 4.2 Gate & ambang yang berlaku SEKARANG (config v18.1)

Sumber: `config/playstyle.yaml` (meta.version "18.1"), dibaca
24 Nov. Semua di bawah ini adalah nilai config saat ini, bukan
nilai lama.

**Otak NBA (fit rolling, 2.701 laga):** sigma_total 18,9868;
sigma_margin 14,4307; home 1,6639; B2B −1,5164; t_nu 35,0;
altitude −0,0105 (dipertahankan; nilai rolling −0,399 adalah
noise). Replacement level BPM −2,0; shrinkage K=10. Simulasi
100.000x, Student-t.

**Asuransi:** p_final ≥ 0,82 (`min_leg_prob`); p_market ≥ 0,80;
banjir 3P ≥ 70% / FT ≥ 65% (pergeseran bersih 8,50 / 12,52);
EV ≥ −1% (`max_negative_ev_pct: -1.0`); gate eksekusi
(likuiditas ≥ $30 = 2× stake via `min_liquidity_multiplier: 2.0`
+ `liquidity_hard_min_usd: 25.0`, spread ≤ 5,0¢ AWAL, ask nyata);
band 80–89¢; komposer memaksimalkan Π decision_prob di
[2,00x, 2,50x]; fallback DILAPORKAN [1,80x, 1,99x]
(`target_multiplier_fallback_min: 1.80`); `must_cover_total_stake:
true`; maks 6 kaki (`_DP_MAKS_KAKI` — konstanta kode, BUKAN di
config).

**Utama:** p_final ≥ 0,74; EV ≥ −2%; banjir hanya peringatan;
band 76–84¢; max-ER dengan tie-break keamanan (selisih ER <
0,015); pengali 3,0–5,0, target lunak ≤ 3,5;
`yakin_min_leg_prob: 0.75`.

**Veto AND:** rim protector OUT (2 sumber) + garis pasar ≥ 232,0
DAN pace proyeksi ≥ 100,5 → blokir KEDUA tiket; parsial (satu
kondisi) = peringatan + bantalan wajib +3
(`veto_parsial_bantalan_points: 3.0`). Definisi rim protector:
posisi C/PF/F-C/C-F (dari BBRef — stats.nba.com TIDAK punya kolom
posisi), min 18 mpg, BLK ≥ 1,0 primer / ≥ 0,7 tier fallback
(berlabel), min 3 laga, maks 2 per tim. Peta rim 30/30
(`data/rim_protectors.json`).

**Vonis:** HIJAU = 0 veto + ≤1 demerit + ≥1 rem; MENENGAH ≤3;
KUNING ≥4 atau veto. Demerit (v18): kerapuhan ekor (banjir 3P <
0,72 atau FT < 0,67 di garis referensi ≥82¢ yang lolos
cek_eksekusi), total tinggi ≥235, selisih tak-terjelaskan >8,0,
ekor gemuk (≥+16 DAN ≤80¢), lingkungan foul tinggi (FTr ≥ p80
0,308111; ftr_p50 0,274398 — FIT), spread ketat ≤3,0. Rem:
DRtg Top-10 ≤ 112,9, pace Bottom-12 ≤ 98,91, pencetak USG ≥25%
OUT, blowout |spread| ≥ 8,5, selaras-market (selisih ≤5,0 dan
total ≤228,0).

**Lainnya:** OT empiris p = 0,0575 × exp(−spread²/(2×14,4307²));
skip keras 0,085 DORMAN (maks p empiris 0,0575). Setan per pemain:
cap min(50%, 3P% musim + 12pp); setan_points 18,07. TUNGGU_LINEUP:
bintang (USG ≥24% atau BPM ≥+2,0, mp ≥ 15,0 di kedua jalur)
Questionable. Blend w_model 0,3; urutan pembanding
odds_api_devig → espn_odds_devig → kalshi; label harga DISKON
EV ≥+2% / MAHAL EV <−2%; ambang anomali: jup-vs-market 4,0,
model-vs-market 8,0, sharp move ≥3¢; bantalan adaptif =
clamp(std_sim × 0,42 + (ORtg−liga) × 0,5 + (total_5laga −
total_musim) × 0,25, min 4, maks 20); potongan kombo 5,5%.

**Rumus kunci:** EV kaki = p_final × (100/harga¢) − 1. Pengali
kombo = Π(100/harga¢) × (1 − 0,055). Potongan kombo nyata jup.ag
yang terukur dari tiket user: 3,12% + 4,13% (n=2) — asumsi mesin
5,5% KONSERVATIF.

### 4.3 Temuan pengukuran yang membentuk mesin (semua dari data)

- **Deadlock Asuransi v17:** 3 aturan (banjir + edge datar 3,5%
  + volume kumulatif) bersama mengunci Asuransi di 0/10; garis
  tahan-banjir = +24,86 di atas median (t(0,74,35)=0,6498).
- **Jebakan plafon 88,5¢ (v18):** safety-first dalam band selalu
  memilih plafon; 88,5¢ butuh 7 kaki untuk x2 (86¢ → 5; 84¢ → 5;
  82¢ → 4) — diverifikasi persis dari tabel Gemini.
- **Pola Denver mati (v18.1):** menyala 0/10; premisnya (garis
  jauh tipis + edge datar) sudah dibatalkan pengukuran v18
  sendiri. Butuh desain ulang berprinsip (item v18.2 #4).
- **Gate volume split-brain (23–24 Nov):** pembuat kaki artefak
  legacy masih memakai volume kumulatif ≥$100 sementara
  equilibrium memakai likuiditas+spread → volume_tipis memblokir
  7 laga di analisis segar 24 Nov, PERSIS seperti prediksi Gemini.
  Bukti kunci: DET U239.5 bid 79/ask 82, likuiditas $36.580,
  volume kumulatif $5 — order $15 terisi.
- **Ekor 3P per laga = NULL:** laju 3PA tidak mempengaruhi ekor
  (slope −0,3364, t=−0,17, R²=0). Banjir DEN adalah lonjakan
  dalam-laga.
- **OT sim miskalibrasi:** cap 2,74% di spread 0 vs OT NBA nyata
  ~5,5–6%; prior empiris 0,0575 (BUKAN hasil fit — jangan diubah
  tanpa data fit).

---

## 5. Peran Gemini & Claude

### 5.1 Gemini — analis senior, penasihat desain, auditor eksternal

Gemini BUKAN bagian dari mesin — ia adalah analis LLM yang user
pakai sebelum mesin ini ada, dan tetap menjadi penasihat yang
sangat dipercaya user. Kontribusinya yang tercatat:

1. **Racikan 23 Nov pagi** (transkrip lengkap di
   `REFERENSI-GEMINI-2026-11-23.md`): 6 laga, bedah multi-skenario,
   2 tiket yang dipasang user ($30) — keduanya kalah karena DEN.
   Gemini MENGAKUI salah memasukkan DEN ke Asuransi (sudah dilabeli
   KUNING sejak awal). Pelajaran yang diambil: label tanpa gate
   cuma kata-kata.
2. **Audit arsitektur v17 + proposal v18** (13:47 WIB,
   `REFERENSI-AUDIT-GEMINI-V18.md`): membuktikan deadlock Asuransi
   secara matematis, menemukan bias edge datar di ekor,
   miskalibrasi OT, dan mengusulkan 10 item v18 — semuanya
   diverifikasi Muse dari data sebelum dibangun.
3. **Review v18 + spesifikasi v18.1** (15:42 WIB,
   `REFERENSI-PATCH-V18-1-GEMINI.md`): menemukan jebakan plafon
   88,5¢ (tabel pengali diverifikasi persis), 5 patch dengan
   kriteria penerimaan.
4. **Jawaban gate volume + 5 temuan preview** (18:55 WIB): setuju
   penuh menyatukan pembuat kaki ke cek_eksekusi; 4 risiko yang
   harus dijaga; kontradiksi HIJAU-tanpa-EQ-Asuransi; HOLD konflik
   pemain pinggiran; bug parser PDF "row leak"; hipotesis
   hitung-ganda cedera OKC@IND; bug tampilan H2H + altitude.
   Semua diverifikasi Muse dari artefak sebelum dicatat.
5. **Cross-check laporan segar** (~05:30–06:15 WIB, 24 Nov):
   Gemini menawarkan memeriksa laporan segar sebelum user pasang
   di jup.ag — user diminta meneruskan
   `out/laporan_2026-11-24.txt` ke Gemini.

**Aturan main dengan Gemini:** jawabannya SELALU diverifikasi
Muse dari data/artefak sebelum dipakai (contoh: klaim "Mara
adalah pemain Net" SALAH — Mara rotasi OKC; "skenario
semua-tersedia ~220" adalah perkiraan Gemini, bukan angka mesin).
Perbedaan konsep yang belum terjawab: Gemini melihat selisih
model-vs-market sebagai PELUANG; mesin melihatnya sebagai
KECURIGAAN (condong-ke-market). Uji historis DunkAPI yang akan
menjawabnya — signup masih menunggu user.

### 5.2 Claude — auditor

User meneruskan laporan Muse ke Claude dan membawa kembali
temuannya. Claude menemukan cacat nyata berkali-kali (validasi
optimis, hitung-ganda pemain absen, bantalan, dll — semua
terbukti benar dan diperbaiki). Claude TIDAK lagi menjadi
perantara komunikasi (sejak 22 Nov) — user bicara langsung
dengan Muse.

---

## 6. Keadaan terkini (Selasa 24 Nov 2026 ~05:00 WIB)

- **v18.1 DIBEKUKAN.** Tidak ada perubahan kode/config sampai
  hasil live hari ini terlihat. Batas 6 kaki DIPERTAHANKAN
  (alasan user: asumsi 0,93^7 tidak realistis — lihat §2.4).
- **Analisis segar 04:23 WIB TIDAK menghasilkan tiket.**
  Jawaban mesin sejauh ini hari ini: NO BET. Vonis: HIJAU 2
  (PHX, LAC) / MENENGAH 1 (UTA) / KUNING 4 (MEM, MIL, BKN, CLE)
  / TUNGGU 3 (POR, OKC, SAS). 7 HOLD + 1 DATA_INCOMPLETE (CLE,
  veto) + 2 OK. Utama maks x1,17.
- **volume_tipis MASIH memblokir 7 laga**, persis seperti
  prediksi Gemini — Odds API tidak memperbaikinya. Ini adalah
  temuan live terpenting hari ini: gate volume kumulatif di
  pembuat kaki artefak adalah bug split-brain yang harus
  diperbaiki di v18.2 (item #5).
- **Kandidat recheck:** OKC (EQ Asuransi VALID U245.5 @88.5¢,
  p_final 90,3%, EV 1,02 — diblokir Siakam Questionable +
  volume_tipis), UTA (EQ Asuransi valid U244.5 @86.5¢, p 86,6%,
  EV 1,00 — vonis MENENGAH, Utama saja), POR (hampir lolos,
  EV −1,2% vs minimum −1,0%).
- **Recheck kloter 07:00 dijadwalkan 06:25 WIB** (cron
  `recheck-kloter-0700-24-nov`, runonce, owner
  goal:new-agent-machine): recheck MEM@CHA + POR@PHI, racik ulang
  bila vonis berubah, audit bila tiket terbentuk, lapor ke chat
  ini. Cron 05:00 (`slate-selasa-05-00`) DIBATALKAN atas perintah
  user 04:23 WIB.
- **Odds API: 484/500 kredit tersisa** (16 terpakai: 13 sebelum
  24 Nov + 3 di analisis segar).
- **Gemini menunggu laporan segar** untuk cross-check
  (~05:30–06:15 WIB) sebelum user memasang apa pun di jup.ag.
- **Ledger:** 2 tiket nyata 23 Nov diselesaikan (keduanya LOSS
  −$15; 10 kaki, 8 menang) — 10 kaki nyata pertama modul belajar.
- **Hook aktif:** `understat-daily-check` (cek harian Understat;
  diam kecuali situs kembali).
- **Tidak ada proses/loop yang berjalan.** Tidak ada cron lain
  yang aktif selain recheck 06:25.

---

## 7. Daftar iterasi v18.2 + pertanyaan terbuka

### 7.1 Daftar iterasi v18.2 (11 item, dari DECISIONS.md — SETELAH hasil live hari ini)

1. Pindahkan `_DP_MAKS_KAKI` ke config, tetap 6 (evaluasi ulang
   setelah data ledger).
2. Kesegaran cedera: GP ≥ 3 DAN missed_last10 ≤ 5 (kasus
   Haliburton: GP=4 tapi missed_last10=10 → dikecualikan).
3. Ganti nama `joint_p_final` → `joint_p_keputusan` (nilainya
   Π decision_prob — benar + konservatif, namanya menyesatkan).
4. Desain ulang skip_awal: khusus menangkap ledakan total-tinggi
   + risiko volume 3P + P_setan < 0,55 (tidak mengulang cek
   EV/eksekusi). Pengukuran v18.1 dikirim ke Gemini untuk iterasi.
5. Satukan pembuat kaki artefak ke cek_eksekusi + 4 risiko Gemini
   (ask_depth ≥ 2× stake atau lantai likuiditas agregat $250–$500;
   monotonisitas tangga ask(L) ≥ ask(L−2) − 1¢; bid > 0 dan
   ask < 0,99; kalibrasi max_spread 5,0¢ dari isi nyata);
   volume kumulatif menjadi info L3 saja.
6. Tanpa EQ Asuransi valid → vonis maks MENENGAH (tidak pernah
   HIJAU).
7. Filter konflik cedera: konflik bintang (mp ≥15 & BPM ≥+1,0,
   atau OUT vs AVAILABLE) memicu HOLD; konflik kecil
   PROBABLE-vs-QUESTIONABLE menjadi catatan L3 (tier 1 menang).
8. Perbaiki parser PDF ("NOT YET SUBMITTED" row leak).
9. Selidiki hitung-ganda cedera + DBPM defender elit (OKC@IND) —
   hipotesis, belum terbukti.
10. Perbaiki pemenang H2H terbalik + flag altitude (lokasi laga,
    bukan kota kandang tim tandang).
11. Pembangun slate: duplikat BKN@MIN + output build_slate tidak
    langsung bisa masuk analyze.

### 7.2 Pertanyaan terbuka (tidak memblokir hari ini)

- **Signup DunkAPI** — membuka uji historis model-vs-market
  (termasuk validasi veto AND-vs-OR, anchoring threshold,
  ketegangan edge-vs-condong-ke-market). Gratis, tanpa kartu;
  uji 150 laga ≈ 150 kredit via rute per-hari. Belum dijawab
  sejak 22 Nov.
- **Keputusan venue Kalshi** — menjadi moot setelah koreksi
  jup.ag (Kalshi tetap pembanding saja); KYC dari Indonesia +
  legalitas menurut hukum Indonesia UNKNOWN.
- **min_leg_prob keras vs lunak** — belum dijawab sejak 22 Nov
  (mungkin sudah moot di v18 — cek sebelum mengangkat lagi).
- **Aturan proses 30-menit-sebelum-tip-off** — diusulkan, belum
  disetujui eksplisit; Gemini independen mengusulkan hal sama.
- **Label tipe laga** (wawasan user 15:52 WIB 23 Nov, item
  mendatang): laga CHI sudah bisa diketahui sebelumnya sebagai
  pace cepat + pemain panas + sedikit garbage time + kedua tim
  main terbuka — mesin harus melabeli TIPE laga di laporan
  (bahan sudah ada: pace + spread + OT).
- **DIPARKIR (bola):** persetujuan fit Dixon-Coles (D12);
  ratifikasi FPL + sumber cedera bola kedua. FPL API ada di kode
  (`ingest/premier_league.py::fetch_injuries_fpl`, TIDAK di
  sources.yaml; FPL = status ketersediaan fantasy, bukan laporan
  medis).
- **Hutang kerja:** fetch H2H hanya mencakup gamelog musim
  berjalan (H2H DEN@CHI kosong — vonis tidak boleh bergantung
  H2H sampai diperbaiki); 18 tiket historis user tidak bisa
  masuk ledger tanpa detail per kaki (tawaran masih berlaku);
  peta rim protector butuh refresh mingguan (tanpa peringatan
  basi); efek rata-rata ekor 3P (t=−2,91) ditemukan tapi belum
  diimplementasikan; kunci stress belum terhubung ke
  `nba_analysis.py` (laporan menghitung on the fly).

---

## 8. Peta kode (untuk AI yang akan melanjutkan)

### 8.1 Struktur repo

```
muse-parlay-analyst/
├── cli.py                    # SATU pintu masuk (10 subcommand)
├── config/
│   ├── playstyle.yaml        # SEMUA ambang & default strategi (v18.1)
│   └── sources.yaml          # Sumber data + tier
├── engine/                   # Otak: sim, gate, vonis, komposer, belajar
├── ingest/                   # Fetcher per sumber
├── data/                     # CSV lokal (gitignored) + rim_protectors.json
├── out/                      # Artefak runtime (gitignored, /out/ root saja)
├── probes/out/               # Bukti probe (DI-COMMIT)
├── tests/                    # 2111 tes (stdlib unittest)
├── DECISIONS.md              # Sumber kebenaran keputusan (1.727 baris)
├── LAPORAN-*.md              # Laporan build per tahap
├── REFERENSI-*.md            # Referensi Gemini (audit, patch, racikan)
├── REKAP-MESIN-UNTUK-GEMINI.md
└── RIWAYAT-PERCAKAPAN.md     # Dokumen ini
```

### 8.2 Modul kunci

| Modul | Peran |
|---|---|
| `cli.py` | analyze / recheck / log / recap / laporan / tanya / racik / pantau / belajar / audit |
| `engine/nba_sim.py` | Simulasi 100.000x (Student-t, OT, skenario skuad) |
| `engine/nba_analysis.py` | Artefak `nba_analysis` (skema v1); Tahap 5c mengisi `setan_pemain` |
| `engine/vegas.py` | Cek Vegas (condong-ke-market, shrinkage 0,5) |
| `engine/equilibrium.py` | Equilibrium per kaki (max-ER + semua garis valid) |
| `engine/ticket_composer.py` | Komposer DP atas bucket log-pengali; `_DP_MAKS_KAKI` = 6 (konstanta kode) |
| `engine/vonis.py` | Sistem vonis (demerit + rem + veto) |
| `engine/skip_awal.py` | Skip-dari-awal (pola Denver — kini 0/10, butuh desain ulang) |
| `engine/setan_pemain.py` | Setan per pemain (cap min(50%, musim%+12pp)) |
| `engine/stress.py` | Skenario panas (banjir 3P/FT, setan) |
| `engine/ticket_audit.py` | Audit tiket nyata sebelum pasang (`cli.py audit`) |
| `engine/ot_empiris.py` | OT empiris (prior 0,0575 — JANGAN ubah tanpa data fit) |
| `engine/cushion.py` | Bantalan adaptif |
| `engine/devig.py` | Devig odds sportsbook → p_market |
| `engine/learning.py` + `engine/calibration.py` + `engine/proposals.py` | Belajar sendiri (usulan saja, tidak pernah auto-terapkan) |
| `engine/recheck.py` | Cek ulang pra-submit (GO/NO-GO, exit 0/1/2) |
| `engine/live_status.py` + `engine/live_anomaly.py` | Pantau live (blend median pra-laga) |
| `engine/qa.py` | Tanya-jawab atas laporan |
| `ingest/polymarket.py` | Tangga total/spread per event (gamma API, slug `nba-{away}-{home}-{date}`) |
| `ingest/jupiter.py` | Harga jup.ag (READ-ONLY, GET saja; 1 RPS keyed + cache) |
| `ingest/odds_api.py` | Odds API (500 kredit/bulan; sisa 484) |
| `ingest/kalshi.py` | Kalshi (pembanding saja; field `*_dollars`, bid/ask) |
| `ingest/nba_injury_pdf.py` | PDF Laporan Cedera Resmi NBA (BUG row leak — item v18.2 #8) |
| `ingest/news_nba.py` | News ESPN JSON (konteks saja, tidak pernah jadi angka) |
| `ingest/stats_nba.py` + `ingest/bbref.py` | Statistik NBA + BBRef (posisi pemain; tabel BBRef di dalam komentar HTML `<!-- -->`) |
| `ingest/slate.py` | Pembangun slate (BUG duplikat + skema — item v18.2 #11) |
| `ingest/common.py` | Opener keep-alive bersama (proxy VM memotong api.jup.ag ~50–70% tanpa ini) |

### 8.3 Kunci config penting (playstyle.yaml v18.1)

`meta.version: "18.1"` · `tickets.insurance` (min_leg_prob 0,82,
min_market_prob 0,80, max_negative_ev_pct −1,0, target 2,00–2,50,
fallback_min 1,80, must_cover_total_stake true) ·
`tickets.main` (min_leg_prob 0,74, max_negative_ev_pct −2,0,
multiplier 3,0–5,0, target_multiplier_max 3,5) ·
`execution` (min_liquidity_multiplier 2,0, liquidity_hard_min_usd
25,0, max_spread_cents 5,0) · `blend` (w_model 0,3) ·
`comparison` (odds_api_devig → espn_odds_devig → kalshi) ·
`price_labels` (DISKON ≥+2%, MAHAL <−2%) · `anomaly`
(jup-vs-market 4,0, model-vs-market 8,0, sharp_move 3¢) ·
`stress` (banjir_3p_points 8,50, banjir_ft_points 12,52,
setan_points 18,07) · `equilibrium` · `skip_awal` · `vonis`
(demerit + rem) · `ot_seleksi` (prior 0,0575, skip 0,085) ·
`setan_pemain` · `simulation` (fit rolling) ·
`veto_parsial_bantalan_points: 3.0`.

### 8.4 Rumus yang dipakai mesin

- EV kaki = p_final × (100 / harga¢) − 1.
- Pengali kombo = Π(100 / harga¢) × (1 − 0,055).
- Bantalan adaptif = clamp(std_sim × 0,42 + (ORtg − ORtg_liga) ×
  0,5 + (total_5laga − total_musim) × 0,25, min 4, maks 20).
- OT empiris: p = 0,0575 × exp(−spread² / (2 × 14,4307²)).
- p_akhir = w × p_model + (1−w) × p_pasar, w = 0,3 (blend).
- p_market dari odds sportsbook via devig (menghapus vig);
  jup.ag "Chance" = 1/pengali (tidak ada info independen).
- CDF efektif Vegas: shrinkage 0,5 (setengah jarak ke garis
  pasar) — kanonis sejak v18.

### 8.5 Gotcha lingkungan (agar AI berikutnya tidak tersandung)

- `export PATH="$HOME/.venvs/parlay-tools/bin:$PATH"` sebelum
  python3 (venv menutupi python sistem; venv punya pyyaml +
  jsonschema). Bila tes gagal ModuleNotFoundError tepat setelah
  export PATH, cek python mana yang pertama — jangan sentuh kode.
- Pre-commit hook menjalankan ruff + black + suite penuh
  (~55 dtk, teramati sampai ~3 menit); commit bisa diblokir file
  agen lain yang belum selesai di tree yang sama — tunggu, JANGAN
  `--no-verify`. Baris "error:" yang diharapkan di stderr hook
  adalah output tes jalur-error. Worker TIDAK BOLEH `git stash`
  di tree bersama (insiden v17).
- `.gitignore`: `/out/` (root saja) — JSON pengukuran
  (`out/ukur_v18.json`, `out/ukur_v18_1.json`, dll) adalah state
  runtime lokal, tidak di-commit; bukti `probes/out/*.json`
  DI-COMMIT.
- urllib `Connection: close` + proxy VM memotong api.jup.ag
  ~50–70% → opener keep-alive bersama di `ingest/common.py`;
  RateLimiter bersama per modul (Kalshi 429 bila tidak).
- stats.nba.com bekerja dari VM tapi lambat/rawan timeout; tabel
  BBRef di dalam komentar HTML (strip `<!--`/`-->`); tabel gamelog
  id `player_game_log_reg`.
- ESPN scoreboard: `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD`
  — tanggal adalah tanggal AS; laga tanggal AS D bermain D+1 pagi
  WIB. Summary: `.../nba/summary?event=<id>` untuk boxscore.
  Pemetaan tricode: GS→GSW, NY→NYK, NO→NOP, SA→SAS, UTAH→UTA,
  WSH→WAS.
- Gmail connector: `/opt/hatch/bin/hatch_gws_cli gmail...`
  dengan `--account 92da00c71bfc401cb42a215efaec417d` eksplisit.
- Pola koordinator yang bekerja: SATU koordinator subagent per
  langkah dengan brief Indonesia mandiri yang detail; koordinator
  memakai ≤3 worker, memverifikasi dari disk, commit + push;
  agen utama lalu memverifikasi INDEPENDEN dari disk (commit/
  remote/tree, suite penuh, lint, nilai config, angka kunci
  dihitung tangan, JSON pengukuran) sebelum melapor. Koreksi
  user di tengah build lewat `subagent.send` dengan
  `interrupt: true`.
- Pelajaran pengiriman ganda (23 Nov 11:10–11:15 WIB): tiga job
  terjadwal menyampaikan hasil penyelesaian tiket yang SAMA;
  laporkan sekali, diam pada duplikat. Cek apa yang sudah
  didengar user sebelum menyampaikan handoff.
- **Jangan pernah menyalin nilai API key / rahasia** — hanya nama
  variabel `.env`-nya (`JUPITER_API_KEY`, `ODDS_API_KEY`).

---

## 9. ARAH PERCAKAPAN — ke mana ini menuju

Percakapan ini menuju **mesin analis parlay yang benar-benar
bisa dipercaya untuk menjawab FAKTA sebelum user memasang
tiket** — bukan mesin aturan kaku, bukan LLM yang mengarang
angka, dan bukan bot otomatis. User memasang sendiri; mesin
memberi analisis, berita, simulasi, dan racikan yang bisa
dipertanggungjawabkan angkanya.

**Langkah terdekat (hari ini, 24 Nov):**

1. **Hasil live hari ini** — recheck kloter 07:00 (06:25 WIB),
   lalu kloter berikutnya. Apakah ada tiket yang terbentuk?
   Apakah volume_tipis membaik? Apakah OKC/UTA/POR lolos?
   Gemini cross-check laporan segar sebelum user pasang.
2. **Keputusan pasang/tidak adalah milik user** — mesin
   melaporkan (termasuk fallback (b) bila tiket x2 tidak
   terbentuk: pengali + peluang gabungan + detail kaki + alasan).
   Bila tidak ada tiket, jawabannya NO BET — dan itu jawaban
   yang sah, bukan kegagalan.

**Langkah berikutnya (setelah hasil live terlihat):**

3. **Evaluasi + build v18.2** — 11 item di §7.1, dengan prioritas
   tertinggi: menyatukan pembuat kaki ke cek_eksekusi (bug
   split-brain yang memblokir 7 laga hari ini), filter konflik
   cedera, dan desain ulang skip_awal. Pengukuran v18.1 dikirim
   ke Gemini untuk iterasi pola Denver.
4. **Kalibrasi dari data nyata** — ambang-ambang yang masih AWAL
   (veto 232,0/100,5, spread 5,0¢, pagar setan 0,55) harus
   dikalibrasi dari hasil ledger, bukan dari tebakan. 10 kaki
   nyata pertama sudah masuk ledger; setiap hasil tiket masuk
   ledger (R4).
5. **Uji historis DunkAPI** (bila user menyetujui signup) —
   menjawab ketegangan konsep terakhir: selisih model-vs-market
   itu peluang atau kecurigaan? Dan memvalidasi veto AND-vs-OR.

**Visi jangka panjang (kata-kata user sendiri):** mesin yang
menjawab FAKTA, bukan hanya data internet — data live real-time
saat dibutuhkan, analisis + berita sebelum pasang, diskusi
secepat LLM mana pun, racikan objektif berbasis data. Sepak bola
dikesampingkan sampai mesin NBA terbukti. Belajar sendiri bukan
prioritas; yang penting mesinnya jalan dan benar.

**Prinsip yang tidak berubah:** angka dari kode, bukan dari
ingatan; data gagal = DATA_INCOMPLETE, bukan tebakan; ambang
hanya berubah atas persetujuan user; pertahanan adalah seleksi,
bukan harga; dan bila prosesnya benar tapi anomali ekstrem
datang juga — "kalah dengan terhormat".

---

*Dokumen dibuat 24 Nov 2026 ~05:00 WIB atas permintaan user.
Sumber: riwayat chat "Mesin Agent Baru" 20–24 Nov 2026 +
DECISIONS.md + laporan build repo. Bila ada angka yang meragukan,
periksa sumbernya — jangan percaya dokumen ini begitu saja.*
