# LAPORAN FIT BOLA — Dixon-Coles (Tahap 3 Langkah 5)

Tanggal: 2026-11-22. Pekerja A (fit + validasi model bola).

> **STATUS: MENUNGGU persetujuan user.** Nilai fit di bawah ini
> DILAPORKAN, bukan diterapkan. `config/playstyle.yaml` TIDAK diubah
> oleh pekerjaan ini — `dixon_coles_rho` dan
> `home_advantage_by_league` tetap `null` sampai user menyetujui.

Hasil lengkap: `out/fit_soccer_params.json`,
`out/validation_soccer.json`, `out/validation_soccer_rolling.json`
(ketiganya gitignored — bukan bagian repo).

## 1. Ringkasan — nilai yang diajukan untuk persetujuan

Fit gabungan 3 musim (2022/23–2024/25, 1.140 laga per liga):

| Parameter | EPL | LaLiga |
|---|---|---|
| rho (Dixon-Coles) | −0,003 | +0,024 |
| avg_home_goals | 1,6892 | 1,4679 |
| avg_away_goals | 1,4062 | 1,1310 |
| home_advantage_ratio (kandang/tandang) | 1,2013 | 1,2978 |
| loglik | −3385,11 | −3130,93 |
| sapuan / konvergen | 5 / ya | 5 / ya |

Kekuatan tim (attack/defence, rata-rata 1) ada lengkap per tim per
musim di JSON — contoh EPL gabungan: attack tertinggi Man City 1,5666,
Liverpool 1,4851, Arsenal 1,4804; terendah Southampton 0,5824,
Sheffield United 0,6528. Defence terkuat (nilai kecil = kuat) Arsenal
0,5871, Man City 0,6176; terlemah Sheffield United 1,6470, Luton
1,3663. LaLiga: attack tertinggi Barcelona 1,7481, Real Madrid 1,6695;
defence terkuat Real Madrid 0,6687, Barcelona 0,6930.

**Validasi (musim 2025/26, 380 laga): model punya skill nyata pada
1X2, TIDAK punya skill pada Over/Under 2.5, dan GAGAL pada BTTS
LaLiga.** Detail di §5–§6.

## 2. Data

Sumber: football-data.co.uk, sesuai keputusan user (DECISIONS.md
2026-11-20): satu kali unduh per file musim, jeda antar unduhan,
disimpan lokal di `data/` (gitignored), TIDAK di-commit. Diunduh
2026-11-22 (redirect www → non-www diikuti dengan `curl -L`).

| File | Musim | Laga | Rentang tanggal | Dipakai untuk |
|---|---|---|---|---|
| E0_2223.csv | 2022/23 | 380 | 05/08/2022–28/05/2023 | fit |
| E0_2324.csv | 2023/24 | 380 | 11/08/2023–19/05/2024 | fit |
| E0_2425.csv | 2024/25 | 380 | 16/08/2024–25/05/2025 | fit |
| E0_2526.csv | 2025/26 | 380 | 15/08/2025–24/05/2026 | holdout + rolling |
| E0_2627.csv | 2026/27 | 100 | 21/08/2026–08/11/2026 | fit parsial (contoh live) |
| SP1_2223.csv | 2022/23 | 380 | 12/08/2022–04/06/2023 | fit |
| SP1_2324.csv | 2023/24 | 380 | 11/08/2023–26/05/2024 | fit |
| SP1_2425.csv | 2024/25 | 380 | 15/08/2024–25/05/2025 | fit |
| SP1_2526.csv | 2025/26 | 380 | 15/08/2025–24/05/2026 | holdout + rolling |

**Hanya kolom HASIL (FTHG/FTAG) yang dipakai.** Kolom odds Pinnacle
TIDAK dibaca sama sekali — situs memperingatkan odds Pinnacle
"systematically out of date" sejak 23/07/2025. Akibatnya Brier PASAR
adalah DATA_INCOMPLETE di semua validasi (tidak ada pembanding pasar
yang bisa dipakai). Semua file: 0 baris tanpa skor; 20 tim per file.

Konteks regime gol (gol per laga): EPL 2,85 → 3,28 → 2,93 → 2,75
(2022/23 → 2025/26); LaLiga 2,51 → 2,65 → 2,62 → 2,70. Musim
2023/24 EPL sangat subur (3,28 gol/laga, Over 2.5 mencapai 64,7%) —
angka gabungan 3 musim meratakan regime yang berbeda ini (§8).

## 3. Metode

**Model — SAMA PERSIS dengan `engine/football_sim.py` (pekerja B):**

- lam_kandang = attack_kandang × defence_tandang × avg_home_goals
- lam_tandang = attack_tandang × defence_kandang × avg_away_goals
- Koreksi tau Dixon-Coles untuk skor rendah: tau(0,0) = 1 −
  lam_k×lam_t×rho; tau(1,0) = 1 + lam_t×rho; tau(0,1) = 1 +
  lam_k×rho; tau(1,1) = 1 − rho; tau = 1 untuk skor lain.
- attack/defence dinormalisasi rata-rata (aritmetik) 1 per liga-musim.
- Home advantage dilaporkan sebagai rasio avg_home/avg_away, bukan
  parameter bebas terpisah.
- Grid peluang 0–10 gol per tim, dinormalisasi setelah pemotongan —
  sama seperti mesin sim. Konsistensi ini DIUJI: peluang analitik
  skrip fit cocok dengan simulasi Monte Carlo engine (20.000 iterasi)
  dalam ±0,02 (tes `test_konsisten_dengan_engine_football_sim`).

**Estimasi.** Maximum likelihood atas log-likelihood Dixon-Coles
(Poisson × tau). Catatan: keempat suku koreksi tau MENJUMLAH NOL atas
grid skor penuh (suku (0,0),(1,0),(0,1),(1,1) saling meniadakan
persis), jadi likelihood ini adalah likelihood eksak dari distribusi
yang dipakai mesin sim — satu-satunya selisih adalah pemotongan mesin
di 10 gol (ekor < 1e-4).

**Optimasi (pure Python stdlib — tanpa numpy/scipy, keduanya tidak
ada di venv).** Coordinate ascent atas log-attack/log-defence tiap
tim (golden-section per koordinat; hanya laga yang melibatkan tim itu
yang dihitung ulang) + pencarian grid rho (kasar −0,40–0,40 langkah
0,01, lalu halus ±0,01 langkah 0,001) atas laga skor-rendah saja.
Setelah tiap sapuan, log-parameter di-centering dengan avg goals
menyerap faktor skala yang sama — lambda TIDAK berubah oleh langkah
ini. Di akhir, attack/defence dinormalisasi ke rata-rata aritmetik 1
dengan avg goals dikoreksi faktor yang sama persis. Konvergen bila
perbaikan loglik satu sapuan < 1e-7 × (1 + |loglik|).

**Cakupan fit.** Per liga: (i) fit per musim, (ii) fit GABUNGAN atas
3 musim (satu rho bersama; satu kekuatan per tim lintas musim —
kekuatan "rata-rata 3 musim"), (iii) fit parsial musim berjalan
untuk contoh live (label jelas "parsial"). Runtime fit total ~3 detik.

**Validasi.** (a) Holdout musim penuh: fit ≤2024/25 → prediksi semua
380 laga 2025/26. (b) Rolling point-in-time (pola 1b — pelajaran dari
kesalahan look-ahead langkah 1 NBA): musim 2025/26 dibagi 38 ronde
(10 laga/ronde, urut tanggal); untuk ronde r, fit HANYA dari laga
dengan tanggal < tanggal pertama ronde r, lalu prediksi ronde r.
Warm start dari fit ronde sebelumnya. Klimatologi tiap ronde juga
point-in-time. Sifat point-in-time DIUJI: fit ronde 1 rolling sama
persis dengan fit langsung atas data latih saja. Runtime validasi
total ~43 detik (jauh di bawah batas 10 menit).

## 4. Hasil fit

### 4.1 Per musim

| Liga | Musim | rho | avg_home | avg_away | rasio kandang |
|---|---|---|---|---|---|
| EPL | 2022/23 | +0,059 | 1,6313 | 1,2163 | 1,3413 |
| EPL | 2023/24 | −0,020 | 1,7953 | 1,4751 | 1,2171 |
| EPL | 2024/25 | −0,034 | 1,5091 | 1,4172 | 1,0648 |
| EPL | **gabungan** | **−0,003** | **1,6892** | **1,4062** | **1,2013** |
| LaLiga | 2022/23 | +0,097 | 1,4552 | 1,0579 | 1,3756 |
| LaLiga | 2023/24 | −0,082 | 1,4809 | 1,1579 | 1,2789 |
| LaLiga | 2024/25 | +0,056 | 1,4530 | 1,1661 | 1,2460 |
| LaLiga | **gabungan** | **+0,024** | **1,4679** | **1,1310** | **1,2978** |

### 4.2 Temuan 1 — rho ≈ 0, BUKAN −0,13 seperti literatur klasik

Nilai rho Dixon-Coles di literatur EPL klasik sekitar −0,13. Fit ini
menemukan rho gabungan −0,003 (EPL) dan +0,024 (LaLiga), dengan
rho per musim yang berganti tanda antar musim. Ini BUKAN bug —
diverifikasi dua cara:

- **Frekuensi empiris.** Pada 1.140 laga EPL fit, skor 0-0 terjadi
  4,39% — LEBIH JARANG dari prediksi Poisson independen (5,30%).
  Pola klasik Dixon-Coles (0-0 dan 1-1 berlebih, 1-0/0-1 kurang)
  TIDAK ADA pada data EPL 2022–25; yang ada justru kebalikannya
  untuk 0-0.
- **Profil loglik.** Dengan kekuatan hasil fit, loglik pada rho =
  −0,003 adalah −3385,11; pada rho = −0,13 (nilai literatur) adalah
  −3390,19 — lebih buruk 5,08 poin. Selang kira-kira 95% dari profil
  loglik adalah sekitar [−0,10, +0,08]: mencakup 0, TIDAK mencakup
  −0,13. Profilnya datar di dekat 0 (rho = −0,05 hanya lebih buruk
  0,69 poin) — rho teridentifikasi LEMAH, jadi nilai per musim yang
  berganti tanda itu wajar: noise, bukan sinyal.

**Implikasi:** koreksi tau hampir tidak berpengaruh pada data modern
ini. Nilai yang diajukan untuk config adalah rho gabungan (−0,003
EPL / +0,024 LaLiga) — atau, sama jujurnya, rho = 0 (Poisson
independen). Keputusan ini diserahkan ke user/reviewer; mesin sim
menerima kedua nilai itu tanpa masalah.

### 4.3 Temuan 2 — keunggulan kandang EPL MENURUN

Rasio kandang EPL per musim: 1,34 → 1,22 → 1,06. Sejalan dengan
frekuensi menang kandang: 48,4% → 46,1% → 40,8% → 42,6%
(2025/26). Nilai gabungan 1,20 meratakan tren menurun ini — bila tren
berlanjut, rasio gabungan sedikit TERLALU TINGGI untuk musim
berjalan. LaLiga stabil (1,38 → 1,28 → 1,25).

### 4.4 Fit parsial musim berjalan 2026/27 (EPL, contoh live)

n = 100 laga (21/08–08/11/2026): rho +0,091, avg_home 1,5639,
avg_away 1,2266. Kekuatannya NOISY seperti diperkirakan — contoh:
attack Brighton 1,8747, defence Arsenal 0,3680, defence Crystal
Palace 1,8207. Nilai-nilai ekstrem ini adalah artefak ~10 laga per
tim, BUKAN estimasi stabil. Label "parsial" ada di JSON.
LaLiga parsial: DATA_INCOMPLETE (file SP1_2627 tidak diunduh —
contoh live di tugas ini hanya EPL).

### 4.5 Cek konsistensi

- Rata-rata attack = rata-rata defence = 1,0000 (normalisasi persis).
- avg_home hasil fit vs rata-rata sampel: EPL 1,6892 vs 1,6491
  (selisih 2,4%) — selisih ini WAJAR: MLE menetapkan avg goals =
  total gol / Σ(α×β atas jadwal), dan rata-rata produk α×β atas
  jadwal tidak persis 1 karena korelasi kekuatan–jadwal lintas musim
  (tim promosi/degradasi membuat jadwal gabungan tidak seimbang).
- Cek silang independen: fit holdout di skrip validasi (kode yang
  sama, dijalankan terpisah) menghasilkan rho dan avg_home yang
  IDENTIK dengan JSON fit (selisih rho 0,0 kedua liga).
- Pemulihan parameter sintetis: pada data sintetis dengan rho benar
  −0,12, fit memulihkan rho dalam ±0,10 dan kekuatan dalam ±0,25
  (tes otomatis).

## 5. Validasi holdout — musim penuh 2025/26

Fit ≤2024/25 → prediksi 380 laga. Brier lebih kecil = lebih baik.
Selisih = model − klimatologi (negatif = model lebih baik); z dari
uji t berpasangan per laga (|z| > 2 ≈ signifikan 5%).

### EPL

| Metrik | Model | Klimatologi | Tebakan 1/3 | Selisih (z) |
|---|---|---|---|---|
| Brier 1X2 | **0,6218** | 0,6563 | 0,6667 | −0,0344 (−2,61) |
| Brier O/U 2.5 | 0,2482 | 0,2484 | — | −0,0002 (−0,05) |
| Brier BTTS | 0,2457 | 0,2464 | — | −0,0007 (−0,22) |
| Akurasi 1X2 (argmax) | 47,1% | — | — | — |
| Akurasi O/U 2.5 | 56,3% | — | — | — |

Kalibrasi: O/U mean prediksi 0,574 vs aktual 0,550 (sedikit
over-prediksi — musim fit lebih subur daripada musim uji); BTTS
0,563 vs 0,561 (terkalibrasi baik). 38 laga melibatkan tim yang
tidak ada di data fit (Sunderland, 38 laga — diprediksi 1,0).

### LaLiga

| Metrik | Model | Klimatologi | Tebakan 1/3 | Selisih (z) |
|---|---|---|---|---|
| Brier 1X2 | **0,5917** | 0,6318 | 0,6667 | −0,0401 (−3,04) |
| Brier O/U 2.5 | 0,2518 | 0,2506 | — | +0,0011 (+0,20) |
| Brier BTTS | 0,2580 | 0,2484 | — | **+0,0096 (+2,14)** |
| Akurasi 1X2 (argmax) | 51,6% | — | — | — |
| Akurasi O/U 2.5 | 55,0% | — | — | — |

Kalibrasi BTTS LaLiga BURUK: mean prediksi 0,474 vs frekuensi aktual
0,566. Penyebabnya teridentifikasi (§7): musim 2025/26 LaLiga lebih
subur (BTTS 0,566) daripada periode fit (BTTS 0,513), dan fit
gabungan yang didominasi data lama tidak mengejar pergeseran itu.
74 laga melibatkan tim promosi tanpa sejarah (Levante + Oviedo).

## 6. Validasi rolling — point-in-time, 38 ronde

| Liga | Metrik | Model | Klimatologi | Selisih (z) |
|---|---|---|---|---|
| EPL | Brier 1X2 | **0,6194** | 0,6560 | −0,0366 (−2,74) |
| EPL | Brier O/U 2.5 | 0,2481 | 0,2483 | −0,0002 (−0,04) |
| EPL | Brier BTTS | 0,2451 | 0,2465 | −0,0014 (−0,37) |
| LaLiga | Brier 1X2 | **0,5870** | 0,6317 | −0,0447 (−3,19) |
| LaLiga | Brier O/U 2.5 | 0,2508 | 0,2507 | +0,0001 (+0,02) |
| LaLiga | Brier BTTS | 0,2536 | 0,2480 | +0,0057 (+1,05) |

Rolling sedikit LEBIH BAIK daripada holdout pada 1X2 di kedua liga
(data lebih segar membantu) — tetapi kesimpulan O/U dan BTTS TIDAK
berubah: O/U seri dengan klimatologi, BTTS LaLiga tetap lebih buruk
(z turun dari +2,14 menjadi +1,05 karena data musim berjalan sedikit
membantu, tetapi tidak cukup). Rho rolling: EPL −0,041 s.d. −0,002
(ronde 1 −0,003 → ronde 38 −0,038); LaLiga +0,002 s.d. +0,024 —
tetap dekat nol. Semua 76 refit konvergen (3–5 sapuan per ronde
berkat warm start). Hanya 1–2 laga per liga yang masih melibatkan
tim tak dikenal (laga pertama tim promosi — setelah itu mereka masuk
data latih).

## 7. Penilaian — apa yang terbukti, apa yang tidak

1. **1X2: skill NYATA.** Model mengalahkan klimatologi secara
   signifikan di kedua liga dan kedua mode validasi (z −2,6 s.d.
   −3,2), dan jauh di atas tebakan 1/3. Ini bukti terbaik dari
   pekerjaan ini.
2. **Over/Under 2.5: TIDAK ADA skill di atas klimatologi.** z ≈ 0 di
   keempat run. Model tidak membedakan laga subur vs seret lebih
   baik daripada frekuensi dasar. Untuk pasar total, nilai model
   (bila ada) harus datang dari perbandingan median model vs garis
   market — BUKAN dari P(Over) model. Temuan ini paralel dengan
   kesimpulan NBA (§12.4 LAPORAN-FIT-NBA.md untuk Under).
3. **BTTS: EPL seri, LaLiga GAGAL.** Kegagalan LaLiga dijelaskan
   oleh pergeseran regime: BTTS LaLiga naik terus 0,503 → 0,495 →
   0,542 → 0,566, sementara fit gabungan terkunci di 0,513. Jendela
   expanding yang didominasi 1.140 laga lama beradaptasi terlalu
   lambat — BTTS rolling pun masih under-prediksi (0,469 vs 0,566).
   Ini kelemahan DESAIN (bobot sama untuk semua musim), bukan
   kesalahan kode — perbaikannya (bobot resensi / jendela geser)
   adalah pekerjaan lanjutan, BUKAN diputuskan di sini.
4. **Satu musim uji (380 laga) adalah gambaran, bukan bukti.**
   Selisih Brier 1X2 sekitar 2–3 SE — meyakinkan tetapi tidak
   luar biasa. Klaim yang lebih kuat butuh lebih banyak musim uji.
5. **Rolling mengonfirmasi holdout** (bukan membatalkannya): tidak
   ada tanda look-ahead — Brier rolling sedikit lebih baik karena
   data lebih segar, arah yang diharapkan, bukan yang mencurigakan.

## 8. Keterbatasan (jujur)

- **Kekuatan gabungan = rata-rata 3 musim.** Skuad berubah antar
  musim; kekuatan gabungan sudah agak basi untuk tim yang banyak
  berubah. Per-musim di JSON menunjukkan pergeserannya.
- **Bobot sama untuk semua musim.** Fit tidak memberi bobot lebih
  pada musim terbaru — ini yang menyebabkan kegagalan BTTS LaLiga
  (§7.3). Bobot resensi adalah pekerjaan lanjutan.
- **Tim promosi = 1,0.** Tim tanpa sejarah di data fit diprediksi
  dengan attack = defence = 1,0 (rata-rata liga). Di holdout ini
  memengaruhi 38 laga EPL dan 74 laga LaLiga.
- **Tidak ada cedera/absensi, jadwal padat, motivasi, atau cuaca.**
  Model hanya membaca skor historis.
- **Rho satu nilai per liga.** Korelasi skor rendah diasumsikan sama
  untuk semua pasangan tim; dan rho teridentifikasi lemah (§4.2).
- **Keunggulan kandang gabungan meratakan tren.** Rasio EPL menurun
  antar musim (§4.3); nilai gabungan bisa sedikit terlalu tinggi
  untuk musim berjalan.
- **Brier pasar DATA_INCOMPLETE.** Tidak ada pembanding pasar —
  odds Pinnacle di CSV stale sejak 23/07/2025 dan sengaja tidak
  dipakai.
- **Fit parsial 2026/27 noisy.** ~10 laga per tim — hanya contoh
  live, bukan estimasi stabil (§4.4).
- **LaLiga parsial tidak ada.** File SP1_2627 tidak diunduh (contoh
  live di tugas ini hanya EPL).

## 9. Tes

`tests/test_soccer_fit.py`: **23 tes baru, SEMUA LOLOS** (3,1 detik):

- Loader CSV: format tanggal DD/MM/YYYY + DD/MM/YY, BOM, baris
  tanpa skor dilewati + dihitung, file/kolom hilang ditolak, liga
  tidak dikenal ditolak.
- Tau: nilai hitung tangan keempat skor rendah + tau = 1 di luar
  itu; grid peluang berjumlah 1; massa grid ~1; simetri; tau tidak
  valid ditolak.
- Konsistensi dengan engine pekerja B: peluang analitik vs simulasi
  Monte Carlo `football_sim` (20.000 iterasi, ±0,02).
- Fit: pemulihan parameter benar pada data sintetis (rho ±0,10,
  kekuatan ±0,25), normalisasi rata-rata 1 persis, rho dalam batas
  + tau positif, loglik meningkat, determinisme, warm start =
  cold start (hasil sama, sapuan ≤), data tidak cukup ditolak,
  tim tak dikenal → 1,0.
- Validasi: Brier 1X2 hitung tangan (termasuk tebakan 1/3 = 2/3
  persis), frekuensi dasar hitung tangan, bagi ronde urut tanggal,
  metrik pada fixture, holdout sintetis ujung-ke-ujung, dan
  **sifat point-in-time rolling** (fit ronde 1 = fit langsung atas
  data latih saja).

Suite penuh: **23 tes pekerja A semuanya hijau.** Suite penuh saat
pemeriksaan terakhir (1.154 tes) memiliki kegagalan HANYA di
`test_ticket_composer` (2 tes: korelasi laga sama + versi config 11
vs 10) dan — pada run berikutnya, setelah pekerja lain mendaratkan
kode baru — `test_soccer_analysis` (7 tes error/gagal). Keduanya
adalah pekerjaan pekerja lain yang sedang berjalan paralel di repo
yang sama (file-file itu bukan milik pekerja A dan tidak disentuh);
jumlah tes/kegagalan suite berubah antar run karena mereka
mendaratkan kode saat pekerjaan ini berjalan. Ruff + black bersih
untuk keempat file pekerja A.

## 10. Hutang / tindak lanjut (bukan diputuskan di sini)

1. **Keputusan user:** adopsi nilai §1 ke `playstyle.yaml` atau
   tidak — termasuk pilihan rho gabungan vs rho = 0 (§4.2).
2. **Bobot resensi / jendela geser** untuk fit agar mengejar
   pergeseran regime gol (pelajaran dari BTTS LaLiga, §7.3).
3. **File SP1_2627** bila contoh live LaLiga dibutuhkan.
4. **Brier pasar** bila ada sumber harga historis yang valid
   (bukan Pinnacle stale).
5. **Validasi musim uji tambahan** (mis. holdout 2024/25 dari fit
   ≤2023/24) untuk memperkuat bukti 1X2 di luar satu musim.
