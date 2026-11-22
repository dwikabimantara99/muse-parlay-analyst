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

### Kalshi sebagai venue Alt Under — groundwork selesai (21 Nov, 09:08–12:10 WIB)

**Garisnya ADA (terverifikasi live, bukti `out/kalshi_alt_total_2026-11-21.json`):** KXNBATOTAL — 14 event, 406 pasar, 29 garis/event (langkah 2 poin), 29/29 ber-harga bid/ask. Under = sisi No dari pasar Over yang sama. Tangga garis menutup bantalan Alt Under 8/12 poin.

**GEO — Indonesia TIDAK dibatasi.** Member Agreement Kalshi dibaca LANGSUNG (PDF "SMS update 10.1.26"), §VI: daftar 55 Restricted Jurisdictions tidak memuat Indonesia; kata "Indonesia" tidak muncul di seluruh dokumen. Nuansa: §VI hanya membatasi trading Event Contracts, bukan keanggotaan/akses non-trading; Kalshi berhak menolak/mencabut akses atas kebijakannya — tidak-dibatasi ≠ jaminan diterima saat signup.

**KYC:** nama legal, tanggal lahir, alamat (bukan PO box), foto live paspor/SIM via aplikasi; bisa diminta bukti alamat/pekerjaan/sumber dana. Apakah KYC/aplikasi berfungsi dari Indonesia **BELUM terverifikasi**.

**FEE (Fee Schedule resmi, berlaku 7 Juli 2026):** taker = roundup(0,07 × C × P × (1−P)); tanpa fee settlement/membership. Sebagai % modal: 50¢ → 3,5%; 80¢ → 1,4%; 90¢ → 0,7%; 30¢ → 4,9%. Maker 0,0175 hanya untuk seri terdaftar — KXNBATOTAL kemungkinan gratis, belum dikonfirmasi. Deposit: kartu debit (fee maks 2%), wire min $1.000, kripto; min $10. Penarikan HANYA kartu debit/kripto.

**MATEMATIKA — cocok dengan rumus mesin:** Under = sisi No pasar Over, harga No ≈ 1 − harga Yes, EV D7 berlaku dengan harga_¢ = harga No. **TAMBAHAN WAJIB Tahap 3:** fee taker harus masuk ke harga efektif sebelum label DISKON/WAJAR/MAHAL dipakai. Contoh: No 80¢ → biaya efektif $0,8112, pengali bersih 1,2328x vs 1,25x kotor. Kaki Alt Under umumnya harga No ~75–85¢ sehingga fee ~1,05–1,75% modal — masih di bawah ambang DISKON +2% tapi memakan sebagian besar edge; pada 50¢ fee 3,5% sudah melampaui ambang DISKON. Tanpa koreksi fee, label DISKON bisa menyesatkan.

**Yang masih UNKNOWN:** (ii) KYC dari Indonesia; (iii) maker fee spesifik KXNBATOTAL; (iv) legalitas menurut hukum Indonesia ("not restricted" Kalshi ≠ legal lokal). Semua terjawab oleh percobaan signup gratis (tanpa deposit) bila user memilih menjajaki Kalshi.

**Keputusan venue BELUM dibuat** — pilihan: (a) jajaki Kalshi, (b) tetap jup.ag-only, (c) tidak buru-buru.

---

## 7. Keadaan mesin sekarang

### Yang sudah bisa dilakukan

- Mengambil data slate NBA/EPL dari 13 sumber (dengan cache, rate limit, pencocokan laga).
- Menghitung p_market (devig sportsbook / ESPN odds / Kalshi), jup_markup, dan menandai sumber pembanding.
- Menandai laga DATA_INCOMPLETE / HOLD / TANPA_XG secara fail-closed (tidak pernah menebak).
- Mencatat tiket ke ledger (termasuk VOID/PUSH dan CASHOUT) dan membuat rekap.
- Menjalankan 406 tes dalam ~6 detik; CI GitHub Actions hijau.

### Yang BELUM bisa dilakukan (pekerjaan Tahap 3)

- Model simulasi: proyeksi total NBA, Dixon-Coles sepak bola — parameternya wajib difit dari data historis (football-data.co.uk sudah diizinkan, musim ≤ 2024/25) dan disetujui user.
- `blend` (gabungan p_model + p_pasar, w = 0,3) + tampilan p_model | p_pasar | p_akhir.
- Optimizer tiket (Asuransi + Utama) dengan aturan MAHAL.
- Laporan "Kenapa beda?" dan kalibrasi Brier tiap 50 kaki.
- `lineup` selalu null (belum ada fetcher lineup); `nba_player_impact` belum ada fetcher.
- Integrasi Kalshi sebagai sumber pasar (bila user memilih a).

### Yang berjalan di latar belakang

- Hook cek harian Understat (poll 24 jam; diam kecuali situs kembali). Tidak ada cron aktif lain — 4 cron cek ulang jup.ag sudah selesai tugasnya.

---

## 8. Yang menunggu keputusan user

1. **Venue Kalshi** — (a) jajaki, (b) tetap jup.ag-only, (c) tidak buru-buru.
2. **Ratifikasi FPL** sebagai sumber cedera bola tier 1 (masuk sources.yaml atau tidak).
3. **Sumber cedera bola kedua** — EPL tetap HOLD sampai ada (Tahap 3).
4. **Mulai Tahap 3?** — termasuk apakah Kalshi masuk sebagai sumber pasar.

---

## 9. Peta file penting

| File | Isi |
|---|---|
| `DECISIONS.md` | Semua keputusan setelah blueprint (sumber kebenaran kedua setelah blueprint) |
| `SOP.md` | Alur kerja 10 langkah |
| `config/playstyle.yaml` v3 | Semua ambang & default strategi |
| `config/sources.yaml` v3 | Daftar sumber data + aturan pemakaian |
| `LAPORAN-TAHAP-1.md`, `LAPORAN-TAHAP-2B.md` | Laporan per tahap |
| `probes/HASIL-PROBE-2A.md`, `probes/HASIL-PROBE-TAMBAHAN.md` | Laporan probe |
| `ingest/` | 13 fetcher + slate + pencocokan |
| `engine/` | devig, price_labels, sim (stub Tahap 3) |
| `ledger/` | Penyimpanan tiket SQLite + rekap |
| `examples/` | Demo slate NBA/EPL + contoh tiket |
| `out/`, `probes/out/` | Bukti JSON (hasil probe, pemindaian jup.ag, Kalshi) |
| `.env` (gitignored, mode 600) | JUPITER_API_KEY + ODDS_API_KEY — tidak pernah di-commit |

## 10. Angka kunci

- 14 commit (20 Nov 21:48 → 21 Nov 05:16), semua sudah push ke GitHub privat.
- 406 tes, semua lulus, ~6 detik. CI hijau (Python 3.11 + 3.12).
- ~19.100 baris kode Python (termasuk tes).
- Odds API: 13/500 kredit terpakai (sisa 487 — konfirmasi dari header pada panggilan berikutnya).
- 5 pemindaian penuh jup.ag: 0 pasar spread/total NBA. 1 pemindaian Kalshi: 406 pasar total NBA.
