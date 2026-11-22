# Laporan Seluruh Pekerjaan — muse-parlay-analyst

**Tanggal:** 22 November 2026
**Untuk:** dibaca user, sebagai peta lengkap apa yang sudah dibangun — sebelum membangun lanjut sesuai keinginan user.
**Status repo:** `main` @ `6724d34`, sudah push, tree bersih. **406 tes, semua lulus.** ~19.100 baris kode Python.

---

## 1. Apa yang sedang kita bangun

**muse-parlay-analyst** — mesin analis parlay NBA + sepak bola dengan alur kerja terkunci. BUKAN bot otomatis: user mengirim daftar laga, mesin menganalisis dan meracik Tiket Asuransi + Tiket Utama, user memasang tiket sendiri secara manual (di jup.ag; Kalshi masih dalam pertimbangan sebagai venue Alt Under).

Spesifikasi resmi: `Blueprint_Mesin_Analis_Parlay__Muse.md`. Keputusan-keputusan setelah blueprint dicatat di `DECISIONS.md` (bila bertentangan, DECISIONS.md menang). Repo GitHub privat: `dwikabimantara99/muse-parlay-analyst`.

### Aturan main yang tidak bisa dilanggar

1. Semua angka (probabilitas, simulasi, EV, pengali) harus dari kode Python; LLM tidak boleh mengarang angka.
2. Data gagal diambil = laga ditandai `DATA_INCOMPLETE`, tidak boleh masuk tiket; tidak pernah mengisi data kosong dengan tebakan.
3. Hanya sumber data gratis; API key di `.env`, tidak pernah di-commit, tidak pernah ditampilkan.
4. Semua ambang & default strategi hanya di `config/playstyle.yaml`.
5. Satu pintu masuk: `cli.py` (analyze / recheck / log / recap).
6. Setiap modul wajib punya tes.
7. Jupiter: mesin READ-ONLY — hanya GET `/events`, `/events/search`, `/events/{id}`, `/markets/{id}`. Tidak pernah order, tidak pernah menggerakkan dana.
8. Pembanding harga harus independen: `p_market` tidak boleh dari provider yang sama dengan asal pasar jup.ag (P1–P4).

---

## 2. Tahap 1 — Fondasi (20 Nov, 21:48–22:11 WIB) — SELESAI, review LULUS

- Struktur repo: `cli.py`, `config.py`, `ingest/`, `engine/`, `optimizer/`, `ledger/`, `validate/`, `critic/`, `report/`, `schemas/`, `tests/`, `probes/`, `examples/`.
- `config/playstyle.yaml` (semua ambang strategi) + `config/sources.yaml` (daftar sumber data).
- `SOP.md` (alur kerja 10 langkah), 5 skema JSON (slate, match_data, simulation, leg, ticket).
- Ledger SQLite + `cli.py log` / `recap` untuk mencatat hasil tiket nyata.
- Laporan: `LAPORAN-TAHAP-1.md`.

### Keputusan review Tahap 1 (22:01 WIB, di DECISIONS.md)

- **A. Ledger:** kaki VOID/PUSH dikeluarkan dan pengali tiket dihitung ulang dari sisa kaki (semua VOID → tiket VOID); hasil CASHOUT + kolom `cashout_amount`; validasi konsistensi (WIN dengan kaki LOSS ditolak); migrasi otomatis untuk DB lama.
- **B. Sumber data berjenjang (MENGGANTIKAN blueprint §4):** Tier 1 resmi (nba.com, laporan cedera resmi NBA, situs liga), Tier 2 agregator (ESPN, BBRef, dll.), Tier 3 hanya bila Tier 1–2 tidak punya. Cedera/lineup wajib cross-check minimal 2 sumber; setiap data mencatat tier + sumber + waktu.
- **D. Jawaban pertanyaan Tahap 1:** MODEL_ONLY (p_final = p_model, ambang +5 poin lebih ketat, maks 1/tiket, dilarang di Asuransi); TANPA_XG (Dixon-Coles berbasis gol, +5 poin lebih ketat, dilarang di Asuransi); EV kaki = p_final × (100/harga¢) − 1; pengali kombo = Π(100/harga) × (1 − 0,055); EV tiket = P(menang, sim gabungan) × pengali − 1; pergerakan tajam ≥ 3¢; bantalan Alt Under ≥ 8 poin (≥ 12 bila spread ≤ 2,5); pemain kunci = GK utama, 2 CB menit terbanyak, xG+xA tertinggi, siapa pun ≥ 70% menit; parameter simulasi wajib difit dari data historis 2–3 musim, tidak pernah ditebak; split stake default 50/50; USDC = USD 1:1.
- **E. Standar kode:** `pyproject.toml`, ruff + black, type hints, docstring, hook pre-commit, conventional commits, CI GitHub Actions (Python 3.11 + 3.12 — run pertama SUKSES), README berbahasa Indonesia.

### Jupiter & API key (C)

- Portal developers.jup.ag TIDAK memakai login wallet (OAuth Google/GitHub atau email + kode). Probe keyless dari VM: HTTP 200, tidak ada blokir wilayah.
- Dompet Solana khusus sempat dibuat untuk signup, lalu **DIHAPUS 22:23 WIB** (`shred -u`) atas perintah user — tidak pernah didanai, 0 transaksi.
- API key dari user (22:22 WIB), disimpan HANYA di `.env` (mode 600, gitignored). Keyed mode 1 RPS + rate limiter + cache; bila key gagal → fallback keyless 0,5 RPS + lapor. Aturan K1–K4 di DECISIONS.md.

### Aturan pembanding harga independen (P1–P4)

- Setiap pasar jup.ag mencatat provider asalnya (`jup_provider`); `p_market` tidak boleh dari provider yang sama.
- Urutan pembanding: sportsbook (Odds API, devig) → ESPN odds (devig) → Kalshi. Polymarket BUKAN pembanding untuk pasar asal Polymarket.
- Kalshi hanya dipakai bila sportsbook tidak ada, dan kaki itu dilabeli `PEMBANDING_KALSHI` di laporan.

---

## 3. Tahap 2a — Probe 13 sumber data (20 Nov, 22:37 WIB) — SELESAI

44 request ke 13 sumber. Bukti JSON di `probes/out/`, laporan `probes/HASIL-PROBE-2A.md`.

| Putusan | Sumber |
|---|---|
| **PAKAI (8)** | Jupiter (keyed), Polymarket, Kalshi, ESPN, BBRef, Official NBA Injury Report, Rotowire, FotMob* |
| **CADANGAN (3)** | Odds API (401, butuh key), stats.nba.com (bekerja, hanya CDN 403), situs resmi liga (hanya JSON EPL) |
| **JANGAN (2)** | Understat (maintenance), Sofascore (3×403) |

Temuan penting:

- **Semua 5.720 pasar olahraga jup.ag yang disampel berasal dari Polymarket, 0 dari Kalshi** — jadi pembanding independen utama adalah sportsbook via Odds API (devig).
- **D4 terjawab:** Official NBA Injury Report ada di `official.nba.com`, PDF per 15 menit terverifikasi HTTP 200.
- Rantai xG putus sementara (Understat maintenance + Sofascore diblokir) → aturan TANPA_XG berlaku sampai ada sumber xG yang sah.

### Keputusan user 22:42 WIB

1. **FotMob DITOLAK** (ToS melarang scraping otomatis) → masuk daftar `rejected` di sources.yaml v3. Sofascore juga ditolak. Bola jalan TANPA_XG.
2. **stats.nba.com = UTAMA** statistik NBA (ESPN cadangan); **JSON resmi Premier League = UTAMA** EPL (ESPN cadangan).
3. sources.yaml menjadi v3; rantai xG tinggal resmi → Understat.

### ODDS_API_KEY — signup sendiri (20 Nov, 22:47–22:54 WIB)

- Gmail terhubung (cskepto@gmail.com), tapi TIDAK ada email Odds API di kotak masuk. User mengizinkan agen mendaftar sendiri dengan Gmail itu, membaca kode verifikasi dari email pribadi, dan menyelesaikan captcha.
- Signup selesai 22:53: paket Starter FREE (500 kredit/bulan), nama depan **"jokowi"** (nama samaran pilihan user — bukan nama asli user), tanpa password, tanpa pembayaran.
- Key tiba via email 22:53, disimpan HANYA di `.env`. Verifikasi 22:54 (1 panggilan): HTTP 200, 9 event NBA, 23 bookmaker termasuk Pinnacle, 1 kredit/panggilan, sisa 499/500.
- **Batas diubah ke 500** atas keputusan user (peringatan 80% = 400).

### Probe tambahan 1–5 (20 Nov, 22:57 WIB) — laporan `probes/HASIL-PROBE-TAMBAHAN.md`

1. **ESPN odds: PAKAI untuk bola saja.** EPL 7/7 dengan garis DraftKings lengkap; NBA 0 odds di mana pun → urutan pembanding NBA: Odds API → Kalshi.
2. **Kalshi sports: PAKAI.** Moneyline cocok 100% di liga yang dicakup (NBA 20/20, EPL 15/15, LaLiga 9/9); spread EPL 40/100 garis, total 60/90 garis. Harga memakai field `*_dollars`; pakai bid/ask, BUKAN last_price (bisa "0.0000").
3. **jup_markup: median 0,5¢** (11/11 cocok, rata-rata 0,68¢, maks 1,5¢) — jup.ag hampir tidak menambah biaya di atas Polymarket.
4. **football-data.co.uk: PAKAI dengan catatan.** CSV EPL 2526 + 2425 terverifikasi (380 baris, kolom Pinnacle lengkap). Pinnacle "systematically out of date" sejak 23/07/2025 → kalibrasi pakai musim ≤ 2024/25. **Keputusan user 23:08: BOLEH** — unduhan satu kali per file musim, CSV lokal di `data/` (gitignored, tidak di-commit).
5. **Understat: masih maintenance.** Cek harian AKTIF via hook `understat-daily-check` (poll 24 jam; diam kecuali situs kembali). Understat baru masuk rantai xG bila status `up` dan dicek < 24 jam lalu.

---

## 4. Tahap 2b — Fetcher + demo slate (21 Nov, ~00:12 WIB) — SELESAI

Commit `5cb229c`, 399 tes saat itu. Laporan: `LAPORAN-TAHAP-2B.md`.

- **`ingest/` — 13 fetcher:** jupiter, odds_api, kalshi, polymarket, espn, stats_nba, nba_injury_pdf, rotowire, bbref, premier_league, understat + `common.py`, `matching.py`, `slate.py`, `check_nba_lines.py`. Dokumentasi integrasi di `ingest/README.md`.
- **`cli.py analyze`** tersambung (langkah SOP 2–3).
- **`engine/devig.py`** — `american_to_decimal` + `devig` (untuk p_market dari odds sportsbook). `blend` masih stub Tahap 3.

### Demo slate nyata

- **NBA (3 laga: Wizards–Bulls, Hornets–Hawks, Suns–Jazz): 3 OK.** 6 pasar moneyline, 6/6 punya p_market (semua `odds_api_devig`), jup_markup 0,5¢. Odds API: 1 panggilan, 3 kredit.
- **EPL (3 laga: Man City–Fulham, Chelsea–Leeds, Newcastle–Arsenal): 3 HOLD.** Cedera hanya dari 1 sumber, aturan B2 butuh 2 — mesin bekerja fail-closed, BUKAN gagal fetch. 3 TANPA_XG (Understat maintenance). 126 pasar, 69 punya p_market (Odds API 9, ESPN 8, Kalshi 52 — semuanya berlabel PEMBANDING_KALSHI).

### FPL API — sumber baru, BELUM diratifikasi

Koordinator menemukan `fantasy.premierleague.com/api/bootstrap-static/` (672 pemain, 20 tim, status a/u/i/d/s) karena endpoint cedera ESPN selalu kosong dan Rotowire gratis mengabaikan filter liga. Diusulkan sebagai tier 1. **Catatan jujur:** FPL adalah status ketersediaan fantasy, bukan laporan medis cedera; ratifikasi saja TIDAK membuat EPL OK — sumber cedera kedua masih belum ada. **Menunggu keputusan user.**

### Temuan integrasi (di `ingest/README.md`)

- Opener keep-alive bersama: `Connection: close` urllib + proxy VM memotong respons jup.ag 50–70%.
- Rate limiter dibagi per modul (Kalshi sempat 429).
- Disambiguasi laga ganda berdasarkan waktu terdekat (bug rematch Suns–Jazz).
- `jup_markup` fallback midpoint menyesatkan di pasar ilikuid — Tahap 3 WAJIB menandai/mengabaikannya.

### Kredit Odds API

13 kredit terpakai, sisa **487/500** (per laporan koordinator — 4 terverifikasi dari bukti: verifikasi 1 + demo NBA 3 + demo EPL 0 cache; ~9 sisanya panggilan pengembangan tanpa catatan per panggilan). Panggilan nyata berikutnya akan mengonfirmasi saldo dari header respons.

---

## 5. Keputusan peran harga pasar (21 Nov, 05:14 WIB) — SUDAH DIIMPLEMENTASI

Commit `6724d34`, 406 tes. Prinsip user: **harga pasar adalah PENGUAT dan ALAT CEK HARGA, bukan hakim.** Selisih dengan pasar = alasan MENYELIDIKI, bukan otomatis menolak.

1. Laporan menampilkan per kaki, terpisah: **p_model | p_pasar (+ sumber pembanding) | p_akhir**. Bobot awal w = 0,3 tetap.
2. **Label harga (dari EV terhadap harga ¢ jup.ag):** DISKON EV ≥ +2%; WAJAR −2% s.d. +2%; MAHAL EV < −2%. Ambang di playstyle.yaml v3; logika di `engine/price_labels.py`.
3. **MAHAL TIDAK lagi dicoret otomatis** (MENGGANTI filter EV < −2% di §7a — `min_ev_pct` DIHAPUS): tetap tampil di laporan berlabel MAHAL; optimizer TIDAK memasukkannya ke Tiket Asuransi kecuali user minta eksplisit; boleh masuk Tiket Utama, wajib berlabel MAHAL. Filter keras lain (DATA_INCOMPLETE, aturan Alt Under, BTTS xG, dll.) tetap berlaku.
4. **|model − pasar| > 8 poin → bagian WAJIB "Kenapa beda?"** di laporan: cek update cedera/lineup terbaru vs jam data model, pergerakan harga, kualitas data model, konteks jadwal. Kesimpulan salah satu dari: (a) "Pasar kemungkinan tahu sesuatu" → sebutkan apa, kaki 🟡/🔴; (b) "Model kemungkinan salah/kurang data"; (c) "Tidak ditemukan alasan" → potensi value, tetap ditandai hati-hati. Bila penjelasan butuh info yang tidak ada: tulis "tidak terverifikasi", jangan mengarang.
5. **w ditentukan data:** tiap 50 kaki, laporan kalibrasi membandingkan akurasi (Brier) model vs pasar; kenaikan w hanya setelah user setuju.
6. Aturan pembanding independen P1–P4 TETAP.

---

## 6. Temuan pasar: jup.ag vs Kalshi

### jup.ag — PUTUSAN AKHIR (21 Nov, 09:00 WIB): TIDAK ADA pasar spread/total NBA

Lima pemindaian penuh (baseline + cek ulang 04:00, 06:00, 07:00, 09:00 WIB mendekati tip-off): 5.116 / 5.113 / 5.214 / 5.211 / 5.163 event, semua 99 laga NBA, **spread 0, total 0** — tiap laga hanya 2 pasar moneyline. Bukti: `examples/nba_lines_check_2026-11-20.json` + `out/nba_lines_recheck_2026-11-21_*.json`.

**Artinya: Alt Under NBA — pasar utama user — tidak bisa dimainkan lewat jup.ag saat ini.**

**KOREKSI 22 Nov 19:15 WIB — putusan di atas SALAH.** User membuktikan lewat screenshot + URL bahwa pasar spread/total NBA ADA di jup.ag. Penyebab: pemindai hanya membaca endpoint daftar API jup.ag (yang hanya menampilkan 2 moneyline per laga); spread/total-nya hidup di Polymarket (provider asal), yang dirender UI jup.ag. Terverifikasi live: event Polymarket `nba-det-atl-2026-11-22` = 283 pasar, total 31 garis 199,5–255,5. **Alt Under NBA BISA lewat jup.ag.** Arsitektur diperbaiki: tangga total/spread diambil dari Polymarket gamma per event. Detail: DECISIONS.md + LAPORAN-TAHAP-3-LANGKAH-1.md.

### Kalshi sebagai venue Alt Under — groundwork selesai (21 Nov, 09:08–12:10 WIB)

**Garisnya ADA (terverifikasi live, bukti `out/kalshi_alt_total_2026-11-21.json`):** KXNBATOTAL — 14 event, 406 pasar, 29 garis/event (langkah 2 poin), 29/29 ber-harga bid/ask. Under = sisi No dari pasar Over yang sama. Tangga garis menutup bantalan Alt Under 8/12 poin.

**GEO — Indonesia TIDAK dibatasi.** Member Agreement Kalshi dibaca LANGSUNG (PDF "SMS update 10.1.26"), §VI: daftar 55 Restricted Jurisdictions tidak memuat Indonesia; kata "Indonesia" tidak muncul di seluruh dokumen. Nuansa: §VI hanya membatasi trading Event Contracts, bukan keanggotaan/akses non-trading; Kalshi berhak menolak/mencabut akses atas kebijakannya — tidak-dibatasi ≠ jaminan diterima saat signup.

**KYC:** nama legal, tanggal lahir, alamat (bukan PO box), foto live paspor/SIM via aplikasi; bisa diminta bukti alamat/pekerjaan/sumber dana. Apakah KYC/aplikasi berfungsi dari Indonesia **BELUM terverifikasi**.

**FEE (Fee Schedule resmi, berlaku 7 Juli 2026):** taker = roundup(0,07 × C × P × (1−P)); tanpa fee settlement/membership. Sebagai % modal: 50¢ → 3,5%; 80¢ → 1,4%; 90¢ → 0,7%; 30¢ → 4,9%. Maker 0,0175 hanya untuk seri terdaftar — KXNBATOTAL kemungkinan gratis, belum dikonfirmasi. Deposit: kartu debit (fee maks 2%), wire min $1.000, kripto; min $10. Penarikan HANYA kartu debit/kripto.

**MATEMATIKA — cocok dengan rumus mesin:** Under = sisi No pasar Over, harga No ≈ 1 − harga Yes, EV D7 berlaku dengan harga_¢ = harga No. **TAMBAHAN WAJIB Tahap 3:** fee taker harus masuk ke harga efektif sebelum label DISKON/WAJAR/MAHAL dipakai. Contoh: No 80¢ → biaya efektif $0,8112, pengali bersih 1,2328x vs 1,25x kotor. Kaki Alt Under umumnya harga No ~75–85¢ sehingga fee ~1,05–1,75% modal — masih di bawah ambang DISKON +2% tapi memakan sebagian besar edge; pada 50¢ fee 3,5% sudah melampaui ambang DISKON. Tanpa koreksi fee, label DISKON bisa menyesatkan.

**Yang masih UNKNOWN:** (ii) KYC dari Indonesia; (iii) maker fee spesifik KXNBATOTAL; (iv) legalitas menurut hukum Indonesia ("not restricted" Kalshi ≠ legal lokal). Semua terjawab oleh percobaan signup gratis (tanpa deposit) bila user memilih menjajaki Kalshi.

**Keputusan venue** — setelah koreksi di atas, Kalshi tidak lagi satu-satunya jalan; venue utama = jup.ag (dikonfirmasi user 22 Nov 19:00 WIB). Groundwork Kalshi tetap tersimpan sebagai cadangan.

---

## 7. Tahap 3 — Otak + cek ulang + laporan + pantauan + bola + belajar (22 Nov) — SELESAI DIBANGUN

Urutan bangun disetujui user 22 Nov 18:54 WIB. Enam langkah, semua selesai dan terverifikasi independen oleh main agent dari disk (tes, lint, angka kunci dihitung tangan):

### Langkah 1 — Otak NBA (commit 151b2c5, 613 tes)

Simulasi 100.000x per laga (Student-t, OT 5 menit, skenario skuad BPM × menit, B2B, altitude, flag turnamen). Fit dari 2.701 laga: sigma_total 18,22, sigma_margin 13,82, home 1,66, B2B −1,60, t_nu 34,5. Validasi: Brier home-win 0,1859 vs tebakan dasar 0,2436 (skill nyata); Under median+8 tidak membeda-bedakan laga (Brier ≈ tebakan dasar).

### Patch 1b — Perbaikan 4 temuan auditor (commit 634b050, 707 tes)

(1) Validasi rolling point-in-time (Brier home-win 0,1983 — v1 terlalu optimis, skill tetap nyata). (2) Replacement level −2,0 + koreksi tumpang-tindih absensi (Duren: double-count 1,4 poin — angka auditor tepat). (3) Bantalan Asuransi dari target peluang 74% (bukan +12 kaku — titipan user). (4) Cedera NBA dari ESPN (110 cedera) + PDF resmi — B2 terpenuhi; Rotowire turun ke cadangan (paywall).

### Langkah 2 — Cek ulang pra-submit + 5 aturan (commit 5b987a2, 849 tes)

`cli.py recheck`: fetch segar (cedera + tangga harga), sim ulang bila material, verdict per kaki TETAP_OK/PERHATIAN/JANGAN_PASANG + GO/NO-GO tiket. Kelima aturan terpasang + teruji: adopsi nilai rolling (sigma_total 18,99), lapisan ketersediaan (OUT apapun alasannya → absen), shrinkage menit+BPM ke musim lalu (K=10), spread dari tangga market (fallback +12), aturan condong-ke-market (selisih >5 poin tanpa alasan konkret → pakai probabilitas market; <74% → tidak lolos Asuransi). Bukti: fixture istirahat mendadak 45 menit sebelum tip-off tertangkap. Probe DunkAPI (tanpa signup): garis penutupan ADA sejak Juli 2020, uji 150 laga ≈ 150 kredit gratis — signup menunggu user.

### Langkah 3 — Laporan + tanya-jawab + peracik tiket (commit 411f604, 966 tes)

Laporan 17 bagian Bahasa Indonesia sehari-hari; tanya-jawab 6 jenis pertanyaan (termasuk "bagaimana jika X absen" via sim ulang 20.000x); peracik Asuransi + Utama (garis berbeda wajib per laga, condong-ke-market berlaku). Uji live 7 laga: Utama x3,1847 terracik (4 kaki Under, EV +8,57% — hitungan tangan cocok persis); Asuransi TIDAK diracik (hanya 2 kaki lolos, pengali maks x1,65 < target x2,20 — mesin menolak memaksa). Pertanyaan terbuka: min_leg_prob 0,74 gate keras vs lunak (kaki DEN@CHI 0,7352 gugur).

### Langkah 4 — Pantauan live dalam laga (commit 51ebbc5, 1088 tes)

Umpan skor live ESPN + status tiket AMAN/WASPADA/TERANCAM/MENANG/KALAH + flag risiko OT + deteksi anomali (hujan 3PT, FT berlebihan, laju skor tinggi). Proyeksi total akhir pace-based (blend w=menit_lalu/48 — dihitung tangan cocok persis). Replay 5 laga selesai: 4 MENANG 1 KALAH. Belum pernah diuji pada laga yang benar-benar berjalan (hutang).

### Langkah 5 — Otak bola (commit 015a708, 1207 tes)

Dixon-Coles (TANPA_XG), fit 3 musim (1.140 laga/liga), holdout + rolling 38 ronde. Fit MENUNGGU persetujuan user: EPL rho −0,003, home/away 1,6892/1,4062; LaLiga rho +0,024, 1,4679/1,1310. Validasi jujur: skill hanya 1X2 (z −2,61 / −3,04); O/U 2.5 tidak ada skill; BTTS LaLiga gagal signifikan (regime shift). Contoh live Liverpool-Man Utd: HOLD (fail-closed benar). Rumus defence terbalik ditangkap sebelum dipakai. Penghambat terbesar: 0 sumber cedera bola → semua laga bola HOLD.

### Langkah 6 — Belajar sendiri (commit e880cc9, 1308 tes)

Pelacakan hasil dari ledger (Brier per pasar, EV terealisasi vs prediksi), kalibrasi w tiap 50 kaki (rekomendasi saja — TIDAK PERNAH diterapkan otomatis, selalu butuh persetujuan user), usulan belajar 4 aturan (selalu status menunggu_persetujuan), `cli.py belajar`. Replay backtest NBA: cek silang Brier cocok persis (moneyline 0,198308, Under 0,219926). Belum ada satu pun hasil nyata — semua angka belajar hari ini replay/sintetis.

---

## 8. Keadaan mesin sekarang

### Yang sudah bisa dilakukan

- Analisis NBA lengkap on-demand: data tim + pemain + cedera 2 sumber + proyeksi + simulasi 100.000x + garis Asuransi/Utama + harga market + anomali.
- Cek ulang pra-submit (GO/NO-GO) + peracik tiket Asuransi/Utama + laporan lengkap + tanya-jawab + pantauan live + loop belajar.
- Analisis bola (EPL): sim 100.000x 1X2/O-U/BTTS — tapi semua laga HOLD sampai sumber cedera + persetujuan fit selesai.
- Menandai DATA_INCOMPLETE / HOLD fail-closed (tidak pernah menebak); ledger tiket + rekap; 1.308 tes lulus; CI hijau.

### Yang BELUM bisa / masih hutang

- Tiket bola (butuh sumber cedera + fit disetujui); recheck bola; narasi bola + ambang "Kenapa beda?" bola; ingest LaLiga; pantauan live saat laga NBA berjalan (belum teruji); kalibrasi ambang live; berita non-cedera belum terdeteksi.
- Model belum terbukti lebih akurat dari market soal total — aturan condong-ke-market tetap berlaku sampai uji DunkAPI menjawab.

### Yang berjalan di latar belakang

- Hook cek harian Understat (poll 24 jam; diam kecuali situs kembali). Tidak ada cron aktif lain.

---

## 9. Yang menunggu keputusan user

1. **Persetujuan fit bola (D12)** — rho gabungan vs rho = 0.
2. **Ratifikasi FPL** sebagai sumber cedera bola tier 1 + **sumber cedera bola kedua** (belum ada kandidat).
3. **Signup DunkAPI** (gratis, tanpa kartu) — membuka uji historis model-vs-market.
4. **min_leg_prob 0,74: gate keras atau anjuran.**
5. **Kenaikan w** — kapan pun modul belajar mengusulkan w baru (saat ini belum ada usulan).

Menunggu keberatan reviewer: koreksi rumus defence, perluasan GARIS_TOTAL, BPM_replacement −2,0, shrinkage K=10.

---

## 10. Peta file penting

| File | Isi |
|---|---|
| `DECISIONS.md` | Semua keputusan setelah blueprint (sumber kebenaran kedua setelah blueprint) |
| `SOP.md` | Alur kerja 10 langkah |
| `config/playstyle.yaml` v12 | Semua ambang & default strategi |
| `config/sources.yaml` | Daftar sumber data + aturan pemakaian |
| `LAPORAN-TAHAP-1.md`, `LAPORAN-TAHAP-2B.md`, `LAPORAN-TAHAP-3-LANGKAH-1/1B/2/3/4/5/6.md` | Laporan per tahap |
| `LAPORAN-FIT-NBA.md`, `LAPORAN-FIT-BOLA.md` | Laporan fit parameter |
| `probes/HASIL-PROBE-2A.md`, `probes/HASIL-PROBE-TAMBAHAN.md` | Laporan probe |
| `ingest/` | Fetcher + slate + pencocokan + otak NBA/bola + live |
| `engine/` | devig, price_labels, sim NBA/bola, recheck, peracik, QA, pantauan, belajar |
| `report/` | Laporan laga + laporan belajar |
| `ledger/` | Penyimpanan tiket SQLite + rekap |
| `examples/` | Demo slate + contoh laporan + contoh tiket |
| `out/`, `probes/out/` | Bukti JSON (fit, validasi, analisis, recheck, tiket) |
| `.env` (gitignored, mode 600) | JUPITER_API_KEY + ODDS_API_KEY — tidak pernah di-commit |

## 11. Angka kunci

- 27 commit (20 Nov 21:48 → 22 Nov 23:00 WIB), semua sudah push ke GitHub privat.
- 1.308 tes, semua lulus, ~24 detik. CI hijau (Python 3.11 + 3.12).
- ~62.300 baris kode Python (termasuk tes).
- Odds API: 13/500 kredit terpakai (sisa 487 — Tahap 3 langkah 1–6 memakai 0 kredit).
- jup.ag: total NBA ADA via Polymarket (283 pasar/event, 31 garis total). Kalshi: 406 pasar total NBA (cadangan).
