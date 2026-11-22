# Laporan Tahap 3 Langkah 5 — Otak Bola (Sepak Bola)

Tanggal: 2026-11-22. Commit: (diisi koordinator saat commit).
Status: **SELESAI** — 1207 tes lulus (1088 baseline + 119 baru),
ruff + black bersih, Odds API 0 kredit. **Nilai fit MENUNGGU
persetujuan user** (pola D12) — belum ditulis ke `playstyle.yaml`
sebagai parameter berjalan.

## 1. Ringkasan

Keluarga model kedua mesin ini sudah dibangun: sepak bola dengan
Dixon-Coles berbasis GOL (mode TANPA_XG — rantai xG masih putus,
Understat maintenance). Yang selesai: fit parameter dari 1.140 laga
per liga + validasi out-of-sample rolling, mesin simulasi 100.000x,
ingest bola (PL resmi + ESPN), artefak analisis bola, wiring ke
`analyze` + laporan + tanya-jawab + peracik tiket (dengan penegakan
TANPA_XG), dan contoh live Liverpool vs Manchester United.

Hasil jujur yang paling penting:

1. **Model punya skill nyata pada 1X2** (Brier mengalahkan
   klimatologi signifikan di EPL dan LaLiga, holdout + rolling).
   **Tidak punya skill pada Over/Under 2.5** (z ≈ 0), dan **GAGAL
   pada BTTS LaLiga** (lebih buruk dari klimatologi, z +2,14 —
   penyebab teridentifikasi: pergeseran regime BTTS).
2. **Rho ≈ 0, bukan −0,13 seperti literatur klasik.** Skor 0-0
   empiris justru lebih jarang dari Poisson independen.
3. **Semua laga bola saat ini HOLD** — bukan karena modelnya, tapi
   karena **0 sumber cedera** (ESPN kosong, PL tidak punya halaman
   cedera, FPL belum diratifikasi user) sehingga B2 tidak terpenuhi,
   ditambah fit yang belum disetujui. Ini fail-closed yang benar,
   bukan kegagalan.
4. **Koreksi rumus defence** (temuan pekerja C, diverifikasi
   koordinator dari file fit): rumus di tugas tertulis terbalik;
   yang benar defence = kebocoran. Tanpa koreksi, contoh live
   memberi Man Utd 50% menang di Anfield (vs market 23%).

## 2. Apa yang dibangun

- **Fit + validasi** (`scripts/fit_soccer_params.py`,
  `scripts/validate_soccer_model.py`, `ingest/football_data.py`,
  `LAPORAN-FIT-BOLA.md`): MLE Dixon-Coles pure Python (tanpa
  numpy/scipy — tidak ada di venv), holdout musim penuh + rolling
  point-in-time 38 ronde. Data: 9 CSV football-data.co.uk di
  `data/` (gitignored) — EPL 2022/23–2026/27, LaLiga 2022/23–
  2025/26; hanya kolom hasil (FTHG/FTAG), odds Pinnacle tidak
  dibaca (stale sejak 23/07/2025).
- **Mesin simulasi** (`engine/football_sim.py`, ditulis ulang dari
  stub): Dixon-Coles 100.000x, seed deterministik, runtime 0,73
  detik. Pasar: 1X2, O/U 0.5–8.5 (diperluas koordinator dari
  1.5/2.5/3.5 — lihat §8), BTTS. Output valid terhadap
  `schemas/simulation.schema.json` (tidak diubah — sudah mendukung
  `sport: football`).
- **Ingest bola** (`ingest/soccer_brain.py`): statistik dari hasil
  PL resmi (musim + 6 terakhir, form5, H2H, kandang-tandang),
  attack/defence ternormalisasi (60% musim + 40% 6 terakhir,
  berbasis gol), audit sumber cedera.
- **Analisis bola** (`engine/soccer_analysis.py`,
  `schemas/soccer_analysis.schema.json`): `build_soccer_analysis`
  mengikuti pola `build_nba_analysis` — kaki 1X2/O-U/BTTS dengan
  p_model/p_pasar/p_akhir (blend w=0,3), label DISKON/WAJAR/MAHAL,
  label TANPA_XG + ambang +5 + dilarang Asuransi, status
  OK/HOLD/DATA_INCOMPLETE.
- **Wiring**: `cli.py` (`_lampirkan_soccer_analysis`),
  `engine/ticket_composer.py` (penegakan TANPA_XG berbasis flag),
  `engine/qa.py` (2 intent bola), `report/nba_report.py`
  (`_LaporanBola` + `build/render_soccer_report`),
  `config/playstyle.yaml` v10→11 (section `soccer:`, liga yang
  didukung hanya EPL; `dixon_coles_rho` /
  `home_advantage_by_league` / `absence_penalty` tetap null).

## 3. Fit + validasi

Nilai fit gabungan 3 musim (2022/23–2024/25, 1.140 laga/liga)
— **diajukan untuk persetujuan user, belum berlaku**:

| Parameter | EPL | LaLiga |
|---|---|---|
| rho (Dixon-Coles) | −0,003 | +0,024 |
| avg_home_goals | 1,6892 | 1,4679 |
| avg_away_goals | 1,4062 | 1,1310 |
| home_advantage_ratio | 1,2013 | 1,2978 |
| loglik / konvergen | −3385,11 / ya | −3130,93 / ya |

Detail lengkap (attack/defence per tim per musim) di
`out/fit_soccer_params.json` (gitignored) + `LAPORAN-FIT-BOLA.md`.

**Validasi holdout musim penuh 2025/26 (380 laga)** — fit dari
≤2024/25, uji pada musim yang belum pernah dilihat:

| Metrik | EPL | LaLiga |
|---|---|---|
| Brier 1X2 model vs klimatologi vs 1/3 | **0,6218** vs 0,6563 vs 0,6667 (z −2,61) | **0,5917** vs 0,6318 vs 0,6667 (z −3,04) |
| Brier O/U 2.5 model vs klimatologi | 0,2482 vs 0,2484 (z −0,05) | 0,2518 vs 0,2506 (z +0,20) |
| Brier BTTS model vs klimatologi | 0,2457 vs 0,2464 (z −0,22) | **0,2580 vs 0,2484 (z +2,14 — model lebih buruk)** |
| Akurasi 1X2 argmax / O/U | 47,1% / 56,3% | 51,6% / 55,0% |

**Validasi rolling point-in-time** (38 ronde, 76 refit, semua
konvergen) mengonfirmasi holdout: Brier 1X2 EPL 0,6194
(z −2,74), LaLiga 0,5870 (z −3,19); O/U tetap z ≈ 0.

**Penilaian (jujur):** skill nyata hanya pada 1X2. O/U tidak
membeda-bedakan laga subur vs seret lebih baik dari frekuensi
dasar — paralel dengan temuan Under NBA. Kegagalan BTTS LaLiga
dijelaskan pergeseran regime (BTTS LaLiga naik 0,503→0,566 antar
musim sementara fit gabungan terkunci di 0,513); jendela
expanding beradaptasi terlalu lambat. Perbaikan (bobot resensi /
jendela geser) adalah pekerjaan lanjutan, bukan diputuskan di
sini. Satu musim uji (380 laga) adalah gambaran, bukan bukti.
Brier pasar DATA_INCOMPLETE (tidak ada harga historis valid).

**Rho ≈ 0:** skor 0-0 empiris 4,39% justru LEBIH JARANG dari
prediksi Poisson independen (5,30%); loglik di rho=−0,13 lebih
buruk 5,08 poin; selang profil ~95% ≈ [−0,10, +0,08]. Rho
teridentifikasi lemah; nilai per musim berganti tanda (noise).
Pilihan rho gabungan vs rho=0 diserahkan ke user/reviewer.

**Keunggulan kandang EPL menurun:** rasio 1,34 → 1,22 → 1,06
per musim. Fit parsial 2026/27 (n=100) noisy seperti
diperkirakan (mis. defence Arsenal 0,368) — sengaja TIDAK
dipakai builder (hanya pooled 3 musim).

## 4. Mesin simulasi

`engine/football_sim.py::simulate(inputs, params, cfg, seed,
iterations)` — parameter dilewat eksplisit (rho, avg_home_goals,
avg_away_goals, league, fit_version), TIDAK membaca
`simulation.football` dari config (nilainya null sampai user
menyetujui fit). Rumus: λ_kandang = attack_kandang ×
defence_tandang × avg_home_goals; λ_tandang = attack_tandang ×
defence_kandang × avg_away_goals; koreksi tau() standar untuk
skor (0-0),(1-0),(0-1),(1-1); PMF gabungan gol 0..10
dinormalisasi lalu disampling. Validasi ketat (attack/defence
> 0, rho dalam [−0,5, 0,5] + keempat tau() > 0, iterations ≥ 1);
fail-closed bila output sendiri tidak valid vs skema.

Tes (20): determinisme seed, 1X2 ≈ 1, O/U + BTTS komplementer,
kasus dikenal rho=0 + simetris cocok hitungan tangan Poisson
independen (delta 0,01), efek tau pada P(0-0) cocok nilai
analitik. Konsistensi peluang analitik vs Monte Carlo engine
diuji pekerja A (±0,02 pada 20.000 iterasi).

Keterbatasan: `squad_scenarios` selalu kosong (pemodelan
absensi pemain bola belum ada); gol dibatasi 0..10 per tim
(ekor Poisson diabaikan, PMF dinormalisasi — untuk λ ≤ ~3
peluang terpotong < 1e-4 per tim).

## 5. Ingest bola + sumber cedera

`ingest/soccer_brain.py::fetch_match_inputs` mengikuti kontrak
`nba_brain`: blok home/away (statistik musim + 6 terakhir,
form5, H2H, kandang-tandang), attack/defence, audit sumber
cedera, daftar `missing`. Sumber: Premier League official JSON
(tier 1) + ESPN (cadangan). H2H hanya musim berjalan (contoh
live: H2H kosong — pertemuan pertama musim ini).

**Audit sumber cedera bola (verifikasi live 2026-11-22):**

| Sumber | Hasil |
|---|---|
| ESPN soccer injuries (eng.1) | Hidup, KOSONG (0 entri) — terkonfirmasi ulang, sama seperti 2b |
| ESPN esp.1 | ~kosong |
| Premier League official | Tidak ada endpoint/halaman cedera (`/injuries` → 404) |
| Fantasy Premier League API | Hidup, tapi TIDAK dipakai — belum diratifikasi user |

**Hasil: 0 sumber → status cedera selalu tidak terkonfirmasi →
semua laga bola HOLD (B2).** Jejak audit tercatat di tiap
artefak (`injury_sources_checked`). B2 tidak dilonggarkan.
Bahkan bila FPL diratifikasi nanti, sumber kedua masih hilang
— EPL tetap HOLD sampai sumber kedua ditemukan.

## 6. Contoh live — Liverpool vs Manchester United, 2026-11-22

Kickoff 23:30 WIB. Artefak:
`examples/analysis_soccer_liverpool_manchester-united_2026-11-22.json`
(diregenerasi koordinator setelah perluasan GARIS_TOTAL; 0 kredit
Odds API; skema valid).

**Status HOLD** (jujur, bukan gagal): `injuries_tidak_terkonfirmasi`
+ `cedera_kurang_dari_2_sumber` + `fit_belum_disetujui`.

Input nyata PL: LIV 10 laga 5-3-2 (GF 1,4/GA 1,0), MUN 10 laga
1-5-4 (GF 1,4/GA 1,9); attack/defence 1,01/0,75 vs 0,96/1,45;
liga 107 laga, rata-rata 1,3692 gol per tim per laga. Sim nyata
100.000 iterasi (seed 7): median total 3,0, mean 3,48.

- **1X2 model: Liverpool 69,2% / seri 17,3% / United 13,5%**
  (λ 2,47 vs 1,01). Market: Liverpool ~54% — model 15 poin lebih
  bullish. **Belum ada ambang "Kenapa beda?" untuk bola**, jadi
  selisih ini tidak memicu aturan apa pun (bandingkan NBA: ambang
  8 poin). Ini hutang, bukan fitur.
- **22 kaki, semua punya p_model** setelah perluasan GARIS_TOTAL
  (sebelumnya 12 dari 22 tanpa p_model): 3 1X2 + 18 total 0.5–8.5
  + BTTS. Contoh: Under 4.5 @ 77,0¢ p_final 75,4% (MAHAL, EV
  −2,0%); Under 5.5 @ 89,0¢ p_final 87,8% (WAJAR, EV −1,4%).
  p_market None untuk garis 6.5–8.5 (tidak ada pembanding) →
  p_final = p_model (MODEL_ONLY untuk kaki itu).
- Peracik menolak kedua tiket secara fail-closed (live HOLD
  ditolak; fixture hanya mencapai pengali x1,11 < target x3,0).
- QA menjawab peluang (69,2/17,3/13,5%) dan kabar pemain "belum
  terkonfirmasi"; intent lain menjawab jujur "belum bisa saya
  jawab untuk laga bola".

Contoh fixture (`examples/analysis_soccer_fixture_lengkap.json`,
jalur OK): status OK, missing kosong, 22 kaki/22 memenuhi,
semua bagian fixture dilabeli (inputs, sim, fit approved=True
fiktif; harga jup.ag NYATA yang sama dengan contoh live).

Catatan: Arsenal vs Chelsea TIDAK ADA di jadwal EPL 2026-11-22
(hanya Hull–Brighton + LIV–MUN) — contoh sim pekerja B
(ARS–CHE) murni sintetis, dilabeli begitu.

## 7. Wiring ke alur

- **Analyze**: `cli.py analyze` melampirkan `soccer_analysis` per
  laga bola (mengikuti `_lampirkan_nba_analysis`); gagal total →
  artefak minimal DATA_INCOMPLETE, slate tetap jalan. Terverifikasi
  ujung-ke-ujung: `analyze --tanpa-odds-api` → `soccer_analysis:
  HOLD` terlampir, 0 kredit.
- **Peracik tiket**: penegakan TANPA_XG berbasis flag kaki
  (`no_xg`/`banned_from_insurance`) — kaki TANPA_XG tidak pernah
  masuk Asuransi sekalipun artefaknya salah memberi tiket
  "insurance"; ambang peluang minimum naik 5 poin
  (`no_xg.threshold_penalty_points` dari config). 6 tes baru.
- **Tanya-jawab**: intent `peluang_laga` + `kabar_pemain`
  berfungsi untuk bola; intent lain menjawab jujur belum
  tersedia (tidak crash, tidak mengarang angka).
- **Laporan**: `_LaporanBola` + `build/render_soccer_report` —
  judul + status TANPA_XG, ringkasan, data, kaki. Narasi bola
  lengkap (taktik, pemain kunci, anomali bola, "Kenapa beda?"
  bola) = hutang.
- **CLI `laporan`/`tanya`/`racik` belum diperluas ke artefak
  bola** (hanya `analyze` yang diwajibkan langkah 5; fungsi
  qa/report/composer bola sudah berfungsi dan teruji langsung).

## 8. Keputusan koordinator (integrasi)

1. **Koreksi rumus defence — DIRATIFIKASI.** Rumus di tugas
   (`defence = rata-rata_liga / laju_kebobolan`) tertulis
   terbalik: itu kekuatan, bukan kebocoran, dan berlawanan
   dengan fit pekerja A + sim pekerja B (Dixon-Coles standar:
   λ = attack × defence_lawan × avg, defence = kebocoran).
   Bukti dari file fit (koordinator memeriksa langsung):
   Arsenal 2024/25 defence 0,617 (paling rapat), Southampton
   1,506 (paling bocor). Dampak terukur: rumus salah memberi
   Man Utd 50% menang di Anfield (vs market 23%); rumus benar
   memberi Liverpool 69,2% / seri 17,3% / United 13,5%.
   Pekerja C memakai rumus benar dan mendokumentasikannya di
   docstring `soccer_brain.py`. Ini mengubah angka — menunggu
   keberatan reviewer.
2. **Perluasan GARIS_TOTAL 0.5–8.5.** Sim pekerja B hanya
   menghitung total 1.5/2.5/3.5; contoh live menunjukkan market
   menawarkan 0.5–8.5, sehingga 12 dari 22 kaki tidak punya
   p_model (termasuk Alt Under dalam, pasar utama user).
   Perluasan bersifat mekanis (peluang tiap garis dari PMF yang
   sama, tanpa biaya berarti) — koordinator mengubah
   `GARIS_TOTAL`, memperbarui docstring + tes, dan
   meregenerasi ketiga contoh. Setelah perluasan: semua 22 kaki
   punya p_model di kedua contoh. Menunggu keberatan reviewer.
3. **`tests/test_stubs.py`**: entri `football_sim` dihapus dari
   daftar STUBS (wajib — stub test menuntut NotImplementedError;
   mengikuti pola `nba_sim`/`devig` yang sudah didokumentasikan
   di file itu).
4. **`tests/test_config.py`**: pin versi 10→11 + 1 tes section
   soccer (konsekuensi paksa bump versi yang diperintahkan).
5. **LaLiga**: fit + validasi penuh BERHASIL (pipeline generik
   pekerja A), tapi ingest LaLiga tidak didukung — builder
   menolak liga selain EPL. LaLiga parsial 2026/27 (SP1_2627)
   tidak diunduh (DATA_INCOMPLETE di JSON fit).

## 9. Keterbatasan (jujur)

- **Tidak ada sumber cedera bola** → semua laga bola HOLD (B2).
  Ini penghambat terbesar otak bola, bukan modelnya.
- **Fit belum disetujui** → artefak bola maksimal HOLD sampai
  user menyetujui nilai §3.
- **O/U tidak punya skill, BTTS LaLiga gagal** (§3) — model
  belum terbukti untuk pasar total/BTTS; nilai (bila ada) harus
  datang dari median model vs garis market, bukan P(Over) model.
- **Tidak ada ambang "Kenapa beda?" untuk bola** — selisih model
  69% vs market 54% di contoh live tidak memicu apa pun.
- **Tidak ada pemodelan absensi pemain bola** (squad_scenarios
  kosong; `absence_penalty` null); tidak ada penyesuaian jadwal
  padat/motivasi.
- **Tim yang belum pernah kebobolan → defence 0,0 → sim menolak
  (ValueError) → analisis DATA_INCOMPLETE** (fail-closed, bukan
  crash). Lantai/shrinkage sampel kecil untuk bola belum ada —
  keluarga yang sama dengan shrinkage menit+BPM NBA (langkah 2).
- **Tim promosi** tanpa sejarah di data fit diprediksi dengan
  attack = defence = 1,0 (rata-rata liga).
- **H2H hanya musim berjalan**; kekuatan tim fit adalah gabungan
  lintas musim (skuad berubah antar musim).
- **Satu musim uji** (380 laga) adalah gambaran, bukan bukti.
- **Brier pasar DATA_INCOMPLETE** (odds Pinnacle stale).

## 10. Hutang ke langkah 6 + keputusan menunggu

**Menunggu user:**
1. **Persetujuan nilai fit (§3)** — adopsi rho/avg goals ke
   `playstyle.yaml` atau tidak; termasuk pilihan rho gabungan
   vs rho = 0.
2. **Ratifikasi FPL** (masih belum dijawab sejak 2b) — dan
   sumber cedera bola KEDUA (masih belum ada kandidat).
3. **Signup DunkAPI** (dari langkah 2 §7) — untuk uji historis
   model-vs-market dengan garis penutupan; juga akan memberi
   Brier pasar untuk bola.

**Menunggu keberatan reviewer:** koreksi rumus defence (§8.1),
perluasan GARIS_TOTAL (§8.2).

**Hutang ke langkah 6 / lanjutan:**
- Recheck bola: BELUM DIDEFINISIKAN (kontrak recheck NBA tidak
  berlaku — tanpa sumber cedera segar, tanpa tangga Polymarket
  bola).
- CLI `laporan`/`tanya`/`racik` untuk artefak bola.
- Narasi bola lengkap + ambang "Kenapa beda?" bola.
- Ingest LaLiga (fit sudah ada; fetcher belum).
- Bobot resensi / jendela geser untuk fit (pelajaran BTTS
  LaLiga); validasi musim uji tambahan.
- Pemodelan absensi pemain bola + lantai/shrinkage sampel kecil.
- H2H lintas musim; file SP1_2627 bila contoh live LaLiga
  dibutuhkan.
- Dari langkah 4 §10 (belum dikerjakan): pengecekan ulang
  `pantau` saat laga NBA benar-benar berjalan (termasuk OT);
  kalibrasi ambang status/anomali atas data PAPER; pertanyaan
  `min_leg_prob` keras vs lunak.

## 11. File yang berubah

Baru: `scripts/fit_soccer_params.py`,
`scripts/validate_soccer_model.py`, `ingest/football_data.py`,
`ingest/soccer_brain.py`, `engine/soccer_analysis.py`,
`schemas/soccer_analysis.schema.json`,
`tests/test_soccer_fit.py`, `tests/test_football_sim.py`,
`tests/test_soccer_brain.py`, `tests/test_soccer_analysis.py`,
`tests/test_soccer_qa_report.py`,
`tests/fixtures/soccer_sim_ars_che_inputs.json`,
`examples/simulation_soccer_ARS_CHE_2026-11-22.json`,
`examples/analysis_soccer_liverpool_manchester-united_2026-11-22.json`,
`examples/analysis_soccer_fixture_lengkap.json`,
`LAPORAN-FIT-BOLA.md`, laporan ini.
Diubah: `engine/football_sim.py` (tulis ulang dari stub +
perluasan GARIS_TOTAL koordinator), `cli.py`,
`engine/ticket_composer.py`, `engine/qa.py`,
`report/nba_report.py`, `config/playstyle.yaml` (v11),
`tests/test_stubs.py`, `tests/test_config.py`,
`tests/test_ticket_composer.py`, `DECISIONS.md`.
Tidak ada `.env`, `data/`, `out/`, atau cache yang di-commit.
Data fit/validasi (`data/*.csv`, `out/fit_soccer_params.json`,
`out/validation_soccer*.json`) adalah runtime state, gitignored.
