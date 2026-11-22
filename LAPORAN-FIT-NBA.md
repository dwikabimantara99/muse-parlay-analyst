# LAPORAN FIT NBA — Otak NBA Tahap 3 Langkah 1

Tanggal: 2026-11-22. Bahasa: Indonesia. Semua angka dari kode Python
(`scripts/fit_nba_params.py`); tidak ada angka karangan.

> **Status persetujuan (D12):** nilai-nilai di bawah ini adalah HASIL FIT
> dari data historis dan SUDAH dimasukkan ke `config/playstyle.yaml`
> (v4) sesuai perintah kerja — tetapi **berlaku setelah user setujui**.
> Laporan ini adalah bahan persetujuan itu.
>
> **Re-fit out-of-sample (patch 1b, §12):** fit + backtest diulang
> dengan rating rolling point-in-time. Pergeseran parameter TIDAK
> MATERIAL menurut ambang pelaporan §12 (sigma +4,4%/+4,2% < 10%;
> home/B2B berubah < 0,5 poin) — nilai D12 di §1 tetap yang berlaku,
> `playstyle.yaml` TIDAK diubah. Brier jujur kandang-menang adalah
> 0,1983 (bukan 0,1859).

## 1. Ringkasan hasil fit

| Parameter | Nilai fit | Bukti (n, SE/metode) |
|---|---|---|
| sigma_margin_points | **13,8168** | std residual margin, n=2701 |
| sigma_total_points | **18,2198** | std residual total, n=2701 |
| sigma_points (ringkasan) | 18,2198 | = sigma total (pasar utama Alt Under) |
| home_advantage_points | **1,6552** | intersep regresi OLS, n=2701, SE 0,27, slope 0,94, R² 0,27 |
| back_to_back_penalty_points | **−1,596** | selisih residual B2B vs tidak, n_b2b=974, SE 0,41 |
| altitude_adjustment_points | **−0,0105** | selisih residual DEN/UTA vs lainnya, n_alt=180, SE 1,10 — praktis NOL |
| t_nu | **34,5** | grid MLE 3–50; profil DATAR (lihat §4) |

Hasil lengkap (JSON): `out/fit_nba_params.json` (gitignored).
Data mentah: `data/nba_history/` (gitignored).

## 2. Sumber data + periode

- **Game log:** stats.nba.com leaguegamefinder via
  `ingest.stats_nba.fetch_league_games` (kontrak worker data).
  2701 laga: 2024-25 penuh (1230), 2025-26 penuh (1230), 2026-27
  parsial (241, 22 Okt 2026 s.d. 21 Nov 2026). 0 laga dilewati.
- **Rating tim:** Basketball-Reference via
  `ingest.bbref.fetch_team_advanced` — ORtg/DRtg/NetRtg/Pace musim
  penuh per tim (30 tim × 3 musim).
- **Reproduksibilitas:** fit dijalankan DUA kali lewat dua jalur
  pengambilan game log yang independen (loader scratch leaguegamefinder
  langsung, lalu jalur kontrak `fetch_league_games`) — **keenam
  parameter identik sampai 4 desimal**.

## 3. Metode fit

(a) **Proyeksi.** Setiap laga historis diproyeksikan dengan rumus yang
SAMA PERSIS dengan `engine.nba_sim.project_points` (ORtg vs DRtg
lawan, pace rata-rata kedua tim), memakai rating musim penuh BBRef.
(b) **Sigma.** sigma_margin & sigma_total = simpangan baku residual
(aktual − proyeksi).
(c) **Home advantage.** Intersep regresi OLS: margin_aktual ~ a + b ×
selisih_net_rating.
(d) **Back-to-back.** Selisih rata-rata residual poin tim B2B vs tidak
B2B. B2B = tim main sehari sebelumnya (dari tanggal game log).
Nilai BERTANDA (negatif = tim B2B mencetak lebih sedikit); sim
MENAMBAHKAN nilai ini ke poin tim B2B.
(e) **Altitude.** Selisih rata-rata residual margin laga kandang
DEN/UTA vs kandang lainnya.
(f) **Derajat bebas t.** Grid MLE atas residual terstandarisasi
gabungan (margin + total), grid 3,0–50,0 langkah 0,5. Kurtosis lebih
sampel dilaporkan sebagai cek silang.

Detail rumus ada di docstring `scripts/fit_nba_params.py` dan
`engine/nba_sim.py`.

## 4. Bukti statistik residual

- **Model membantu, bukan merusak.** Std mentah margin 16,16 dan total
  19,88 (rata-rata total 229,20; n=2701). Setelah proyeksi dari rating:
  std residual margin 13,82 dan total 18,22. Regresi margin ~ net
  rating: slope 0,94, R² 0,27.
- **Home advantage konsisten dua cara.** Intersep regresi 1,6552;
  cek silang rata-rata residual margin 1,6549 — cocok sampai 3 desimal.
  Nilai 1,66 poin lebih kecil dari angka historis ~2,5–3,0; data
  2024–2026 memang menunjukkan home advantage yang mengecil.
- **B2B signifikan.** Penalti −1,596 dengan SE 0,41 (t ≈ −3,9):
  tim B2B mencetak ~1,6 poin lebih sedikit. Rata-rata residual tim
  B2B −0,71 vs tidak B2B +0,89.
- **Altitude tidak terukur.** DEN/UTA kandang residual margin 1,645 vs
  kandang lain 1,656 — selisih −0,01 dengan SE 1,10. Tidak ada efek
  ketinggian tambahan yang terukur di luar home advantage umum pada
  sampel ini. Nilai fit −0,0105 dipakai apa adanya (efeknya nol
  praktis); klaim "Denver sulit ditaklukkan di kandang" TIDAK
  didukung data ini sebagai efek DI LUAR kualitas tim + HA umum.
- **Derajat bebas t: profil DATAR.** Log-likelihood: ν=10 → −7703,2;
  ν=20 → −7687,5; ν=30 → −7686,0; ν=34,5 → −7685,9 (maks);
  ν=50 → −7686,2; ν=100 → −7687,3. Kurtosis lebih gabungan hanya
  0,17 (ν implisit kurtosis 39,6). Artinya: residual NYARIS NORMAL —
  ekor tebal yang diasumsikan blueprint §5a TIDAK terukur kuat di
  level laga (masuk akal: skor adalah jumlah ~200 possession, CLT
  membuat sebarannya mendekati normal). Nilai 34,5 praktis setara
  normal. Bila user/reviewer ingin ekor yang lebih tebal sebagai
  pilihan konservatif yang disengaja, itu keputusan terpisah — BUKAN
  hasil fit, dan tidak saya karang ke sini.
- **Mean residual total +1,205: itu OT, bukan bias model.** Proyeksi
  adalah 48 menit regulasi, sedangkan skor aktual mencakup OT. Dengan
  ~5,5% laga masuk OT dan ~22 poin per OT, ekspektasinya ≈ +1,2 —
  persis yang teramati. Konsekuensi: sigma_total 18,22 sedikit
  mencakup varians OT (regulasi saja ≈ 17,5); sim menangani OT
  terpisah, jadi pemakaian 18,22 untuk noise regulasi sedikit
  konservatif untuk Under (peluang Under sedikit lebih kecil dari
  seharusnya). Koreksi eksak butuh flag OT per laga — tidak ada di
  leaguegamefinder (lihat §6).

## 5. Asumsi yang BELUM difit (daftar eksplisit)

Nilai-nilai ini ada di config sebagai ASUMSI AWAL yang didokumentasikan,
BUKAN hasil fit. Jangan diklaim sudah difit:

1. **Recency 60% musim / 40% last10** (`simulation.nba.recency`) —
   mengikuti pola §5b bola. Fit butuh rating rolling per tanggal laga.
2. **bpm_scale 1,0** — tidak ada literatur internal; dampak pemain =
   BPM × menit/48 × 1,0.
3. **tournament_adjustment_points 0,0** — belum ada data; flag turnamen
   saat ini tidak mengubah proyeksi.
4. **Pembagian home advantage / altitude / turnamen setengah-setengah**
   (+HA/2 kandang, −HA/2 tandang; total tidak berubah) — pilihan desain,
   bukan hasil fit.
5. **Skala noise OT × √(5/48)** (varians sebanding durasi) — asumsi.
6. **ot_max_periods 5** — batas pencegah loop, bukan parameter fit.
7. **Pace laga = rata-rata pace kedua tim** — pilihan rumus (bukan
   pace liga + deviasi); konsisten antara fit dan sim.

## 6. Keterbatasan

1. **Bias look-ahead (yang terbesar).** Rating musim penuh "melihat masa
   depan" — rating dihitung dari semua laga musim itu, termasuk laga
   yang diproyeksikan. Akibatnya residual sedikit TERLALU KECIL dan
   sigma sedikit underestimate. Perbaikan: rating rolling sampai
   sebelum tanggal laga (pekerjaan lanjutan, butuh game log per tim
   + hitung rating berjalan).
2. **OT tercampur di sigma_total** (lihat §4). Regulasi saja ≈ 17,5.
3. **ν tidak teridentifikasi tajam** (profil datar 20–100).
4. **Altitude n kecil** (180 laga kandang DEN/UTA; SE 1,10) — efek
   kecil (±1 poin) tidak akan terdeteksi.
5. **B2B dari tanggal kalender saja** — tidak membedakan B2B kandang /
   tandang / perjalanan jauh.
6. **Pemain yang tidak ada di tabel BBRef tidak bisa dinilai
   absennya.** Perbaikan koordinator saat integrasi Langkah 1:
   `nba_brain` kini memasukkan semua pemain cedera ke daftar pemain
   walau di luar 8 besar (tes regresi
   `test_pemain_cedera_di_luar_top8_tetap_masuk`) — pada contoh §9,
   catatan "dampak 0" turun dari 7 menjadi 3 pemain. Yang tersisa
   (Henri Veesaar, Mouhamed Gueye, Ugonna Onyenso) memang tidak ada
   di tabel advanced BBRef (rookie/cadangan tanpa baris statistik),
   jadi dampaknya tetap dihitung 0 + dicatat di
   `inputs_summary.notes`. Ini batasan data input, bukan model.
7. **Backtest kalibrasi peluang — SUDAH DIBUAT saat integrasi
   Langkah 1** (pekerja validasi): 150 laga, Brier kandang-menang
   0,1859 vs klimatologi 0,2436; Under median+8 rata-rata cocok
   tapi tidak membedakan antar laga (Brier 0,2306 ≈ klimatologi
   0,2304). Hasil lengkap: `out/validation_nba.json` +
   LAPORAN-TAHAP-3-LANGKAH-1.md §validasi.

## 7. Bug yang ditemukan & diperbaiki selama pekerjaan ini

1. **Tanda rumus proyeksi TERBALIK (bug terbesar).** Rumus awal
   `off + (lg − def_lawan)` membuat tim mencetak LEBIH SEDIKIT
   melawan pertahanan buruk — margin proyeksi menjadi selisih
   (off+def), bukan selisih net rating. Tertangkap OLEH FIT DATA
   NYATA: sigma margin 16,63 (lebih buruk dari std mentah 16,16!)
   dan altitude −8,33 yang tidak masuk akal. Setelah perbaikan
   (`off + (def_lawan − lg)`): sigma 13,82, altitude −0,01.
   Pelajaran: tes sintetis TIDAK menangkap bug ini karena generator
   sintetis memakai rumus yang sama (sirkular) — data nyata yang
   menangkapnya. Ditambah tes regresi
   `test_margin_proyeksi_sama_dengan_selisih_net_rating`.
2. **Jacobian hilang di log-likelihood Student-t.** Residual
   terstandar (varians 1) butuh t yang diskalakan; tanpa suku
   log(c), MLE bias ke ν besar (tes sintetis: 13,5 vs benar 6,0).
   Setelah perbaikan, tes sintetis memulihkan ν dalam [4, 10].
3. **`_ambil_teratas` dengan jumlah=0 mengambil 1 nama.**
   Skenario missing_1 keliru mengeluarkan 1 pemain tandang juga.
   Tertangkap tes skenario (missing_1 == missing_2 persis).
4. **Nama BBRef "Los Angeles Clippers"** tidak ada di peta tricode
   (saya hanya punya "LA Clippers") — 179 laga terlewat di fit
   pertama. Setelah perbaikan: 2701/2701 laga dipakai.

## 8. Waktu tempuh 100.000x per laga (ukur nyata)

Diukur di VM ini (simulasi penuh: base case + 5 skenario skuad,
100.000 iterasi tiap skenario, seed berbeda):

- Run 1: 1,815 dtk; run 2: 1,734 dtk; run 3: 1,854 dtk.
- **≈ 1,7–1,9 detik per laga** (rata-rata ~1,8 dtk).
- Satu slate 10 laga ≈ 18 detik. Tidak ada masalah kecepatan.

## 9. Contoh output simulasi SATU laga nyata

Laga: **DET @ ATL, 2026-11-22** (musim 2026-27). Input NYATA dari
`ingest.nba_brain.fetch_match_inputs` (stats.nba.com tier 1 +
BBRef + injury report). File lengkap:
`examples/simulation_nba_ATL_DET_2026-11-22.json` (valid terhadap
`schemas/simulation.schema.json`). Dijalankan lewat
`scripts/simulate_nba_game.py ATL DET 2026-11-22`.

Input kunci: ATL off 113,1 / def 110,4 / pace 103,11 (musim);
DET off 114,8 / def 109,4 / pace 98,17. DET tim lebih kuat
(net +5,4 vs +2,7). Cedera: DET kehilangan Jalen Duren (BPM 8,8)
dan Duncan Robinson (BPM 2,6) — keduanya OUT; ATL kehilangan
CJ McCollum (BPM −0,6) — OUT.

Hasil base case (100.000x, seed acak). Angka di bawah ini dari
contoh yang DIREGENERASI saat integrasi Langkah 1, setelah
perbaikan `nba_brain` (§6 butir 6): 4 pemain OUT yang semula
dihitung 0 kini masuk hitungan (kebanyakan BPM negatif — pemain
cadangan — sehingga absennya justru MENAIKKAN proyeksi timnya;
total naik 218,28 → 221,95).

- Proyeksi: DET 108,54 – 113,41 ATL (total 221,95; margin +4,87).
- Moneyline: kandang 64,1%, tandang 35,9%.
- Garis default (median total 223 → garis 222): Under 47,9% /
  Over 50,0% (sisanya ~2,1% tepat di garis = push).
- Distribusi total: mean 222,68; std 18,73; median 223; p5 192;
  p95 254.
- **Peluang OT: 2,6%.**
- Skenario skuad (moneyline kandang): full 46,1% (DET favorit bila
  semua sehat) → base 64,1% → missing_1 (Dyson Daniels absen)
  58,8% → missing_2 (+ Cade Cunningham absen) 70,4% →
  missing_4 72,0% → doubtful_out 66,3%. Arah semua skenario benar:
  absennya bintang DET (Duren, Robinson) adalah alasan ATL favorit
  di base case padahal DET tim lebih kuat; absennya bintang ATL
  (Daniels) menurunkan peluang kandang dari base.

## 10. Keputusan desain (menunggu objeksi reviewer)

- **D1 — missing_N per tim** (bukan gabungan): missing_1 = teratas
  kandang; missing_2 = teratas kandang + teratas tandang; missing_4 =
  2 teratas tiap tim. missing_N selalu di atas pemain yang sudah OUT.
- **D2 — "inti teratas" = dampak (BPM × menit) terbesar**, bukan menit
  terbanyak.
- **D3 — "full" = semua pemain inti bermain**, termasuk yang OUT
  (hipotesis kekuatan penuh); markets utama = base case (OUT absen).
- **D4 — sigma_points = sigma total** (ringkasan satu angka); mesin
  memakai sigma_margin_points & sigma_total_points.
- **D5 — t_nu = 34,5 dari fit** (praktis normal), bukan nilai ekor
  tebal yang diasumsikan. Lihat §4.
- **D6 — noise yang sama untuk semua skenario** (common random
  numbers): perbedaan antar skenario murni dari skenarionya.

## 11. File yang diubah/dibuat (Langkah 1, pekerja model)

- `engine/nba_sim.py` (tulis ulang), `engine/markets.py` (tulis ulang)
- `scripts/fit_nba_params.py` (baru), `scripts/simulate_nba_game.py` (baru)
- `config/playstyle.yaml` (v3→4, nilai fit, kunci baru, bagian `fees:`)
- `tests/test_nba_sim.py`, `tests/test_markets.py`, `tests/test_fit_nba.py`
  (baru); `tests/test_stubs.py`, `tests/test_config.py` (disesuaikan)
- `LAPORAN-FIT-NBA.md` (file ini)
- `examples/simulation_nba_ATL_DET_2026-11-22.json` (contoh nyata)

Tes baru: 42 (markets 14, nba_sim 18, fit 10). Suite penuh:
559 tes, SEMUA LOLOS (exit 0, 2026-11-22) — termasuk tes worker
paralel (blend + data). TIDAK commit — koordinator yang commit.

## 12. Re-fit out-of-sample — rating rolling point-in-time (patch 1b, temuan auditor 1)

Tanggal: 2026-11-22. Nilai §1 di atas TETAP terlihat dan tetap yang
berlaku (D12); bagian ini adalah re-fit pembanding, BUKAN pengganti.
`config/playstyle.yaml` TIDAK diubah oleh pekerjaan ini.

### 12.1 Metode rolling (persis)

- **Sumber box score.** `data/nba_history/games_all.json` ternyata
  HANYA menyimpan poin (tanpa FGA/FTA/OREB/TOV) — tidak cukup untuk
  possessions. Jalan keluar: respons MENTAH endpoint leaguegamefinder
  yang sama (sudah dipakai `fetch_league_games`) ternyata memuat
  kolom box score lengkap (FGA, FTA, OREB, TOV, PTS, MIN) — parser
  kontrak hanya membuangnya. Skrip fit kini mem-parse respons mentah
  itu sendiri (`parse_boxscores_leaguegamefinder`, 3 panggilan
  keyless gratis, 0 kredit Odds API), di-cache ke
  `data/nba_history/boxscores_{musim}.json` (+ `boxscores_all.json`).
  Hasil: 5.402 record (2.701 laga × 2 tim) — 0 laga tanpa box score.
- **Possessions (Dean Oliver).** POSS = FGA + 0,44×FTA − OREB + TOV.
  off_rtg = 100×PTS/POSS sendiri; def_rtg = 100×PTS_lawan/POSS_lawan;
  pace = 240×POSS/MIN_tim (POSS per 48 menit; MIN_tim = jumlah menit
  pemain, 240 untuk laga regulasi; OT ditangani rumus karena MIN
  ikut membesar).
- **Point-in-time.** Untuk tiap laga, rating tiap tim dihitung HANYA
  dari laga SEBELUM tanggal laga itu. Proses berjalan tanggal demi
  tanggal: snapshot rating semua laga tanggal itu DULU, baru update
  state dengan box score tanggal itu — box score satu tanggal tidak
  pernah memengaruhi laga tanggal yang sama. Laga setelah tanggal
  uji tidak memengaruhi rating (dibuktikan tes).
- **Keputusan desain (D-R1 s.d. D-R5):**
  - D-R1 — **Prior = rating BBRef musim SEBELUMNYA** untuk tim itu
    (data masa lalu, bukan look-ahead). Untuk 2024-25, priornya
    rating BBRef 2023-24 (di-fetch sekali, di-cache ke
    `ratings_bbref_2023-24.json`).
  - D-R2 — **Shrinkage awal musim:** rating =
    (n×observasi + K×prior)/(n+K), K = 10 laga. n=0 → prior persis;
    n=10 → 50/50; n=82 → ~89% observasi. K=10 adalah pilihan desain
    yang didokumentasikan (bukan hasil fit).
  - D-R3 — **Last10 di-shrink ke rating MUSIM** (bukan ke prior):
    hirarki prior → musim → last10, agar prior musim lalu tidak
    dihitung ganda di komponen last10.
  - D-R4 — **Jendela reset tiap musim** (musim-berjalan + last10-
    berjalan hanya dalam musim yang sama); carryover antar musim
    hanya lewat prior D-R1.
  - D-R5 — **Rata-rata liga (lg_avg) juga point-in-time:** rata-rata
    off_rtg efektif ke-30 tim pada tanggal laga itu (tim yang belum
    main menyumbang priornya). Rating efektif yang masuk
    `project_points` = gabungan 60% musim + 40% last10 (bobot
    recency dari config — SAMA seperti yang dipakai sim).
- **Catatan perbandingan yang jujur.** Fit rolling berbeda dari fit
  v1 dalam DUA hal sekaligus: (a) rating point-in-time (bukan musim
  penuh), dan (b) bobot resensi 60/40 kini BEROPERASI (v1 memakai
  100% rating musim penuh karena last10 per tanggal tidak ada).
  Keduanya adalah perbaikan menuju "mengukur persis rumus yang
  dipakai mesin", tetapi selisih angka di bawah adalah efek gabungan
  keduanya, bukan efek (a) saja.

### 12.2 Perbandingan parameter (v1 disetujui vs rolling)

n = 2.701 laga di kedua fit; 0 laga dilewati di fit rolling
(0 tanpa prior, 0 tanpa lg_avg).

| Parameter | v1 (D12, disetujui) | Rolling | Selisih | Selisih % |
|---|---|---|---|---|
| sigma_margin_points | 13,8168 | 14,4307 | +0,6139 | +4,44% |
| sigma_total_points | 18,2198 | 18,9868 | +0,7670 | +4,21% |
| home_advantage_points | 1,6552 | 1,6639 | +0,0087 | +0,53% |
| back_to_back_penalty_points | −1,596 | −1,5164 | +0,0796 | +4,99% |
| altitude_adjustment_points | −0,0105 | −0,4094 | −0,3989 | — |
| t_nu | 34,5 | 35,0 | +0,5 | +1,45% |

Bukti pendukung rolling: slope regresi net rating 0,8786 (v1 0,9406),
R² 0,2069 (v1 0,2696), SE intersep 0,277 (v1 0,2658); B2B
mean_residual −0,5236 vs +0,9928, SE selisih 0,4303 (v1: −0,7057 vs
+0,8903, SE 0,4144); altitude SE selisih 1,1399 — nilai −0,4094 masih
dalam noise (tetap "praktis nol", seperti v1); t_nu loglik −7686,5,
kurtosis lebih 0,1612 (v1: −7685,9 / 0,1684). Mean residual total
+1,4388 (v1 +1,205) — masih konsisten dengan efek OT (§4).

Hasil lengkap: `out/fit_nba_params_rolling.json` (gitignored);
hasil v1 diamankan ke `out/fit_nba_params_v1.json` (file lama
`out/fit_nba_params.json` tetap utuh).

### 12.3 Penilaian materialitas — TIDAK MATERIAL

Ambang pelaporan (bukan keputusan): material bila sigma berubah
>10% ATAU home/B2B berubah >0,5 poin.

- Sigma margin +4,44% (< 10%), sigma total +4,21% (< 10%).
- Home berubah +0,0087 poin (< 0,5); B2B berubah +0,0796 poin
  (< 0,5).
- Altitude berubah −0,3989 poin tetapi TIDAK masuk kriteria
  materialitas, dan nilainya tetap dalam noise (SE 1,14).

**Verdict: TIDAK MATERIAL — tidak ada penanda "menunggu persetujuan
ulang user".** Nilai D12 di §1 tetap yang berlaku di
`playstyle.yaml`. Arah pergeseran sesuai dugaan auditor: sigma
rolling LEBIH BESAR (residual tidak lagi diperkecil look-ahead) —
v1 memang sedikit underestimate, sebesar ~4–4,5%, bukan kesalahan
orde besar. Apakah nilai rolling (sigma 18,99) sebaiknya diadopsi
menggantikan nilai D12 (sigma 18,22) adalah keputusan user/reviewer
terpisah — pekerjaan ini hanya menyajikan angkanya.

### 12.4 Backtest ulang dengan rating rolling (subset SAMA)

Subset identik dengan run v1 (150 laga, 50 terbaru/musim —
game_id diverifikasi SAMA persis), seed sama, config sama
(parameter D12), base case saja. Waktu backtest 284,0 dtk.
Hasil lengkap: `out/validation_nba_rolling.json`; v1 diamankan ke
`out/validation_nba_v1.json`.

| Event | Brier v1 | Brier rolling | Selisih |
|---|---|---|---|
| Kandang menang | 0,185911 | 0,198308 | +0,012397 (+6,67%) |
| Under (median+8) | 0,230642 | 0,219926 | −0,010716 |

- **Kandang menang: Brier jujur 0,1983.** Mean prediksi hampir sama
  (0,5605 vs 0,5597), frekuensi aktual sama (0,58) — event ini
  tidak bergantung model, jadi perbandingannya bersih. Temuan
  auditor TERKONFIRMASI: v1 memang agak optimis (0,1859 → 0,1983).
  Tetapi skill nyata TETAP ADA: Brier 0,1983 masih jauh di bawah
  klimatologi 0,2436.
- **Under: hati-hati membaca angka ini.** Brier membaik 0,2306 →
  0,2199, TETAPI frekuensi aktual ikut berubah (0,64 → 0,6733)
  karena garis Under (median model + 8) bergeser mengikuti median
  model yang baru — event yang dinilai TIDAK identik antar run.
  Yang TIDAK berubah: model tetap tidak membedakan antar laga
  untuk Under (semua 150 prediksi jatuh dalam satu bucket
  [0,6–0,7), mean 0,659) dan Brier model praktis SAMA dengan
  klimatologi (rolling: 0,2199 vs klim 0,2200; v1: 0,2306 vs klim
  0,2304). Jadi "perbaikan" Brier Under terutama mencerminkan
  garis yang bergeser, BUKAN skill baru — kesimpulan v1 §6 butir 7
  tetap berlaku: yang membedakan Alt Under adalah median model vs
  garis market, bukan P(Under) model.
- **Uji kepekaan di JSON rolling** memakai engine 1.1.0 (patch 1b
  perbaikan 2, replacement level) — basis berubah vs v1 (median
  222 → 218, proyeksi 221,95 → 217,22) KARENA engine, bukan karena
  rolling. Bintang teratas yang dipilih (Daniels/Cunningham) sama
  di kedua run; rumus dampak baru (sinkronisasi §12.6) memilih
  bintang yang sama pada inputs ini, jadi JSON rolling tidak
  terpengaruh urutan pekerjaan.
- **Keterbatasan yang TETAP ADA:** cedera per tanggal untuk laga
  historis tetap tidak tersedia — backtest tetap tanpa penyesuaian
  pemain absen (last10 di sini adalah last10 STATISTIK TIM, bukan
  skuad). Brier pasar tetap DATA_INCOMPLETE (tidak ada harga pasar
  historis). B2B tetap dari tanggal kalender saja. Sigma_total
  tetap mencakup varians OT (§4).

### 12.5 Tes baru (patch 1b)

`tests/test_fit_nba.py` +15 tes (10 → 25), `tests/test_validation.py`
+9 tes (15 → 24, termasuk 4 tes sinkronisasi §12.6): kebenaran rating rolling pada
game log sintetis (nilai hitung tangan — possessions, off/def/pace,
shrinkage musim + last10, gabungan efektif, lg_avg), sifat
point-in-time (laga setelah tanggal uji dan box score tanggal yang
sama TIDAK memengaruhi rating; laga setelahnya BOLEH memengaruhi
laga berikutnya), determinisme, parsing box score mentah (termasuk
anomali MATCHUP), fit-dengan-rolling ujung-ke-ujung, backtest
rolling kecil + determinisme + laga tanpa rolling dilewati.
Backtest penuh (150 laga, 100.000x) BUKAN bagian suite — itu run
skrip. Suite tertarget: 49 tes, SEMUA LOLOS; ruff + black bersih.

### 12.6 Sinkronisasi rumus dampak pemain (tugas tambahan pekerja perbaikan 2)

`scripts/validate_nba_model.py` punya salinan `_dampak_pemain`
sendiri (rumus lama: BPM × menit/48 × skala) yang dipakai
pemeringkatan bintang uji kepekaan. Salinan itu kini DELEGASI ke
`engine.nba_sim._dampak_pemain` (rumus tunggal di engine — TIDAK
ada lagi duplikasi rumus di skrip; bila engine berubah signature,
skrip gagal loud, bukan diam-diam memakai rumus lama):
dampak = (BPM − bpm_replacement) × (mp/48) × bpm_scale ×
faktor_overlap, bpm_replacement = −2,0 (dari config),
faktor_overlap = 1 − w_last10 × missed_last10/10 dengan w_last10
ternormalisasi (0,4) dan missed_last10 None → faktor 1,0.
`jalankan_kepekaan` membaca bpm_replacement + bobot recency dari
config (dinormalisasi seperti `simulate()`). Perubahan ini TIDAK
mengubah hasil backtest (tidak ada cedera di input historis) —
hanya konsistensi pemeringkatan bintang uji kepekaan. Tes:
wrapper identik dengan fungsi engine untuk 7 kasus (termasuk
missed None/invalid, BPM/menit hilang), nilai hitung tangan,
dan satu kasus pembeda peringkat (rumus lama memilih Y, rumus
baru memilih X).
