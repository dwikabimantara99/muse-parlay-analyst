# LAPORAN TAHAP 3 LANGKAH 1 — Otak NBA

Tanggal: 2026-11-22. Repo: `muse-parlay-analyst`, branch `main`.
Blueprint §5, §5a, §5c, §5d + DECISIONS.md (termasuk keputusan user
2026-11-22: profil bettor konservatif, arah mesin, perluasan Otak NBA,
pelajaran Thunder, prinsip psikologi market, dan koreksi tangga
Polymarket).

## 1. Ringkasan

Otak NBA sudah jadi sebagai modul: dari satu laga, mesin mengambil data
nyata (statistik tim, pemain, cedera, form, H2H, istirahat/B2B), lalu
mensimulasikan laga itu **100.000x** dan menilai semua pasar (moneyline,
spread, total Under/Over) dari SATU hasil simulasi yang sama. Parameter
model **dikalibrasi dari 2.701 laga nyata** (bukan ditebak), lalu diuji
ke 150 laga lama: peluang kandang-menang terkalibrasi baik dan punya
skill nyata (Brier 0,1859 vs 0,2436 angka dasar), sementara peluang
Under pada bantalan +8 rata-rata cocok tapi tidak membedakan antar laga
— temuannya penting dan dijelaskan di §4.

| Angka kunci | Nilai |
|---|---|
| Tes | **613, semua lulus** (sebelum langkah ini: 406) |
| Simulasi 100.000x per laga | **~1,7–1,9 detik** (slate 10 laga ≈ 18 detik) |
| Fit parameter | n = 2.701 laga (2024-25, 2025-26, 2026-27 parsial) |
| Backtest | 150 laga, 0 dilewati, 278 detik (~4,6 menit) |
| Brier kandang-menang | 0,1859 (angka dasar 0,2436; tebakan 50% 0,2500) |
| Brier Under (median+8) | 0,2306 (angka dasar 0,2304 — model tidak membedakan) |
| Brier pasar | DATA_INCOMPLETE (tidak ada harga pasar historis) |
| Kredit Odds API dipakai langkah ini | **0** (semua sumber gratis tanpa key) |
| Config | playstyle.yaml v4 → v5 |

**Yang belum:** Otak NBA sudah jadi sebagai modul dan teruji, tapi
**belum tersambung ke `cli.py analyze`** — perintah analisis masih
memakai alur slate Tahap 2b. Penyambungan ujung-ke-ujung (data →
simulasi → pasar → laporan) adalah pekerjaan langkah 2/3. Parameter
hasil fit sudah masuk config tapi **menunggu persetujuan user (D12)**
sebelum dipakai tiket nyata. Dua ambang baru masih NILAI AWAL yang
belum dikalibrasi (§11).

## 2. Yang dibangun

### 2.1 Lapisan data — `ingest/nba_brain.py` (baru) + perluasan fetcher

Perakit `fetch_match_inputs(home, away, game_date)` menggabungkan
fetcher yang sudah ada menjadi satu paket input siap model untuk SATU
laga. Setiap datum mencatat tier + sumber + waktu (aturan B); data
gagal → field None/kosong + nama field di `missing`, bukan ditebak.

| Isi paket | Sumber |
|---|---|
| Statistik tim musim + 10 laga terakhir (ORtg, DRtg, Net, Pace) | stats.nba.com tier 1 (baru: `fetch_league_games` + `fetch_team_advanced_stats`); fallback BBRef tier 2 (musim saja) |
| Rating pemain: BPM × menit per pemain inti | BBRef tier 2 (baru: `fetch_player_advanced`) |
| Form 5 laga terakhir, rekor kandang/tandang + rata-rata poin | game log stats.nba.com |
| H2H 5 pertemuan terakhir | game log musim yang sama |
| Hari istirahat + flag back-to-back | tanggal kalender dari game log |
| Ketinggian Denver/Utah | fakta arena (DEN/UTA) |
| Cedera (OUT/DOUBTFUL/QUESTIONABLE/PROBABLE/AVAILABLE) | PDF resmi NBA tier 1 + Rotowire tier 2, cross-check 2 sumber (B2); konflik dicatat, status tier 1 menang |
| Rata-rata liga (pace, ORtg) | dari statistik musim |
| Bendera turnamen (NBA Cup/Playoff) | **None — tidak ada sumber yang bisa menentukannya; tanggal tidak ditebak** |

Daftar pemain per tim: 8 pemain bermenit terbanyak **+ semua pemain
cedera** (walau di luar 8 besar) — perbaikan koordinator saat
integrasi, lihat §12.

Verifikasi live (2026-11-22 ~19:07 WIB, UTA vs DAL): ok=True, ~10
detik, 7 request; yang hilang hanya bendera turnamen (by design).
Catatan jujur: Rotowire hari itu hanya mengembalikan 5 baris
seliga (paywall), jadi cross-check cedera B2 sering praktis hanya
1 sumber (PDF) — dicatat, bukan disembunyikan.

### 2.2 Model — `engine/nba_sim.py` (tulis ulang) + `engine/markets.py`

- **Proyeksi:** pace laga + poin per tim dari rating tim yang
  disesuaikan kekuatan lawan dan resensi (60% musim + 40% 10 laga
  terakhir — asumsi awal, belum difit), home advantage, penalti B2B,
  ketinggian, dampak pemain absen (BPM × menit/48 × bpm_scale).
- **Sebaran Student-t** dengan σ hasil fit (§3). Derajat bebas hasil
  fit ν = 34,5 — praktis nyaris normal; ekor tebal tidak terukur
  kuat di level laga (lihat LAPORAN-FIT-NBA.md §4).
- **Simulasi 100.000x** (stdlib saja, tanpa numpy): margin + total
  per iterasi; **OT 5 menit bila seri** setelah 48 menit (peluang OT
  dilaporkan — penting untuk Alt Under); semua pasar dinilai dari
  satu hasil simulasi yang sama (§5). Output valid terhadap
  `schemas/simulation.schema.json`.
- **Skenario skuad** (§5a): `full` (semua sehat, hipotetis),
  `missing_1` / `missing_2` / `missing_4` (pemain inti absen
  tambahan di atas yang sudah OUT), `doubtful_out` — plus skenario
  arbitrer per tim (vektor ketersediaan pemain inti). Common random
  numbers antar skenario (D6) agar perbandingannya tidak berisik.
- **Script:** `scripts/simulate_nba_game.py` (satu laga dari data
  nyata), `scripts/fit_nba_params.py` (fit parameter).

### 2.3 Pembanding pasar + deteksi anomali — `engine/devig.py` + `engine/anomaly.py` (baru)

- `blend`: p_akhir = w·p_model + (1−w)·p_pasar, w = 0,3 dari config;
  MODEL_ONLY bila p_market tidak ada (p_akhir = p_model).
- `evaluate_leg`: menggabungkan blend + label DISKON/WAJAR/MAHAL
  (`engine/price_labels.py`) + semua cek anomali dalam satu
  penilaian kaki.
- Snapshot harga + waktu (`PriceSnapshots`, file
  `out/price_snapshots.json`): pergerakan tajam **≥ 3¢** sejak
  snapshot pertama → ANOMALI (D9). **Fixture pelajaran Thunder:
  75¢ → 71¢ (4¢) ditandai** — diuji di dua tempat.
- `check_jup_vs_market`: selisih harga jup.ag vs pasar lain > 4 poin
  → ANOMALI (§5d).
- `check_model_vs_market`: selisih model vs pasar > 8 poin → pemicu
  wajib "Kenapa beda?" (keputusan 2026-11-21).
- `kalshi_effective_price_cents`: koreksi fee taker Kalshi ke harga
  efektif sebelum label harga (rumus resmi Kalshi 0,07×C×P×(1−P);
  mis. No 80¢ → biaya efektif $0,8112).
- Perangkap float di ambang (0,75−0,71 = 0,040000000000000036)
  ditangani dengan pembulatan 9 desimal sebelum perbandingan.

P1–P4 tetap: p_market TIDAK BOLEH dari provider yang sama dengan
asal pasar jup.ag; urutan pembanding sportsbook devig → ESPN odds
devig → Kalshi; Polymarket bukan pembanding untuk pasar asal
Polymarket.

### 2.4 Cek garis market (psikologi market) — `engine/anomaly.py`

Lihat §8 untuk prinsipnya. Implementasi:

- `MarketLineSnapshots` (file `out/market_line_snapshots.json`):
  mencatat garis market + harga + waktu snapshot.
- `check_total_line_vs_model`: |median proyeksi − garis market| >
  5,0 poin → ANOMALI `total_line_vs_model`.
- `check_cushion_vs_market`: bantalan model lolos D10 (8/12 poin)
  tapi bantalan terhadap garis market tidak → ANOMALI
  `cushion_tidak_dikonfirmasi_market`.
- `check_under_safety`: putusan gabungan + ANOMALI
  `model_optimis_harga_melawan` bila model optimis Under (≥ 0,70)
  tapi harga bergerak melawan ≥ 3¢.

Ambang 5,0 poin dan 0,70 adalah NILAI AWAL yang belum
dikalibrasi (§11).

### 2.5 Tangga Polymarket (harga venue) — `ingest/polymarket.py` + `scripts/fetch_poly_ladder.py`

Lihat §7 untuk koreksinya. Implementasi: slug NBA
(`nba-{away}-{home}-{YYYY-MM-DD}`, tanggal Eastern), ambil event
dari Polymarket gamma API, uraikan tangga spread/total/moneyline
per (garis, sisi) dengan bid/ask/mid, volume, flag `thin`, dan
estimasi harga jup.ag (mid + markup tipikal 0,5¢). Harga Under =
komplemen harga Over (1 − mid Over); `last_cents` dicatat tapi
tidak pernah jadi harga utama di pasar tipis. Tidak ada kunci
`p_market` di mana pun di modul ini (penjaga P2).

`check_nba_lines.py` diperbaiki (tindak lanjut §7): `has_spread` /
`has_total` kini jup.ag ATAU Polymarket, angka jup.ag saja tetap
disimpan terpisah.

### 2.6 Validasi — `engine/validation.py` (baru) + `scripts/validate_nba_model.py` (baru)

Fungsi murni: `reliability_buckets`, `brier_score`,
`calibration_summary`. Runner CLI: backtest N laga (default 150:
50 terbaru per musim) pada 100.000x penuh + kalibrasi + uji
kepekaan. Hasil lengkap: `out/validation_nba.json` (gitignored).
Lihat §4.

### 2.7 Config — `config/playstyle.yaml` v4 → v5

- Bagian baru `market_line_check` (total_gap_points 5,0;
  min_model_under_prob 0,70 — NILAI AWAL, belum dikalibrasi).
- Bagian baru `polymarket_ladder` (min_volume_usd 100,0 — heuristik
  awal).
- `fees.jup_typical_markup_cents: 0.5` (median terukur, probe
  tambahan 3).
- `fees`, `market_line_check`, `polymarket_ladder` ditambahkan ke
  REQUIRED_PLAYSTYLE_SECTIONS di `config.py` (fail-closed: config
  tanpa bagian ini ditolak).
- Nilai hasil fit tetap di `simulation.nba` dengan komentar
  provenance + status menunggu persetujuan user (D12).

## 3. Hasil fit parameter (D12 — menunggu persetujuan user)

Laporan lengkap: **LAPORAN-FIT-NBA.md**. Script:
`scripts/fit_nba_params.py`; bukti: `out/fit_nba_params.json`;
data: `data/nba_history/` (gitignored).

**Sumber + periode:** 2.701 laga — 2024-25 penuh (1.230), 2025-26
penuh (1.230), 2026-27 parsial (241 s.d. 21 Nov 2026); game log
stats.nba.com leaguegamefinder + rating musim penuh
Basketball-Reference. Koordinator mereproduksi fit secara independen:
semua 6 parameter cocok sampai 4 desimal.

| Parameter | Nilai fit | Keterangan |
|---|---|---|
| sigma_margin_points | 13,8168 | std residual margin, n=2701 |
| sigma_total_points | 18,2198 | std residual total, n=2701 |
| home_advantage_points | 1,6552 | intersep OLS margin (SE 0,27; R² 0,27) |
| back_to_back_penalty_points | −1,596 | n_b2b=974, SE 0,41 — signifikan |
| altitude_adjustment_points | −0,0105 | n_alt=180, SE 1,10 — praktis NOL |
| t_nu (derajat bebas Student-t) | 34,5 | grid MLE 3–50; profil datar 20–100; kurtosis lebih 0,17 → residual nyaris normal |

**Asumsi yang BELUM difit** (eksplisit di config + laporan fit):
resensi 60/40, bpm_scale 1,0, penyesuaian turnamen 0,0, pembagian
home advantage setengah-setengah, skala noise OT √(5/48),
ot_max_periods 5.

**Keterbatasan fit:** (1) bias look-ahead — rating musim penuh
"melihat masa depan", sigma sedikit underestimate; perbaikan
(rating rolling) adalah pekerjaan lanjutan; (2) sigma_total
mencakup varians OT (regulasi saja ≈ 17,5 — efeknya konservatif
untuk Under); (3) ν tidak teridentifikasi tajam; (4) altitude n
kecil — efek ±1 poin tidak terdeteksi.

**Bug yang ditemukan & diperbaiki selama fit** (dengan tes
regresi): rumus proyeksi terbalik (tertangkap OLEH DATA NYATA —
tes sintetis tidak menangkap karena generator memakai rumus yang
sama, sirkular); Jacobian hilang di log-likelihood Student-t;
`_ambil_teratas(jumlah=0)` mengambil 1 nama; "Los Angeles
Clippers" hilang dari peta tricode (179 laga terlewat di fit
pertama).

## 4. Validasi: backtest, kalibrasi, dan uji kepekaan

**Metode.** Backtest memakai data historis yang sama dengan fit:
subset 150 laga — 50 laga terbaru per musim (2024-25, 2025-26,
2026-27), tanggal 8 April 2025 s.d. 21 November 2026 — masing-masing
disimulasikan penuh 100.000x, base case saja, dengan seed
deterministik per laga. Dua event dinilai: (i) kandang menang,
(ii) Under pada median+8 poin (bantalan Alt Under). Waktu tempuh:
278,2 detik (~4,6 menit), 0 laga dilewati. Script:
`scripts/validate_nba_model.py`; hasil lengkap:
`out/validation_nba.json`. Angka di bawah ini dari validasi yang
dijalankan ULANG saat integrasi (setelah perbaikan §12); backtest
mereproduksi persis (deterministik), uji kepekaan memakai input
segar.

### 4.1 Kalibrasi kandang menang — terkalibrasi baik, model punya skill nyata

Rata-rata prediksi 0,560 vs frekuensi aktual 0,580: selisih −2,0
poin, jauh di dalam noise (SE frekuensi pada n=150 adalah ±4,0
poin). Di tiap bucket, mean prediksi dan frekuensi aktual
berdekatan; penyimpangan terbesar (bucket 0,5–0,6: prediksi 0,546
vs aktual 0,633, n=30) masih dalam 1 SE. Tidak ada pola
overconfident atau underconfident yang sistematis pada sampel ini.
Brier model **0,1859**, jauh lebih baik dari Brier klimatologi
(selalu memprediksi angka dasar 0,58: 0,2436) dan dari tebakan 50%
(0,2500) — model membedakan laga yang mudah dan sulit ditebak,
bukan sekadar menebak angka dasar.

| Bucket | n | Mean prediksi | Frekuensi aktual |
|---|---|---|---|
| 0,0–0,1 | 4 | 0,064 | 0,250 |
| 0,1–0,2 | 6 | 0,146 | 0,000 |
| 0,2–0,3 | 10 | 0,255 | 0,200 |
| 0,3–0,4 | 21 | 0,358 | 0,333 |
| 0,4–0,5 | 15 | 0,451 | 0,467 |
| 0,5–0,6 | 30 | 0,546 | 0,633 |
| 0,6–0,7 | 19 | 0,654 | 0,684 |
| 0,7–0,8 | 14 | 0,740 | 0,714 |
| 0,8–0,9 | 23 | 0,845 | 0,870 |
| 0,9–1,0 | 8 | 0,921 | 1,000 |

### 4.2 Kalibrasi Under (median+8) — rata-rata cocok, tapi model tidak membedakan antar laga

Rata-rata prediksi 0,657 vs frekuensi aktual 0,640: selisih +1,7
poin, juga dalam noise (SE ±3,9 poin) — tidak bisa disimpulkan
overconfident. Namun temuan pentingnya lain: peluang Under hampir
tidak bervariasi antar laga (rentang 0,646–0,671; semua 150 laga di
satu bucket 0,6–0,7), karena sigma_total adalah satu parameter
global dan garis selalu median+8. Akibatnya Brier model **0,2306**
praktis sama dengan Brier klimatologi (**0,2304**): pada event ini
model tidak menambah kemampuan membedakan laga mana yang lebih
mungkin Under, di luar angka dasar 64%. Kalibrasi hanya teruji di
satu titik (~66%), bukan di rentang peluang. Ini bukan berarti
proyeksi totalnya salah — median totallah yang menentukan garis —
tapi untuk Alt Under, **yang membedakan satu laga dari laga lain
adalah median proyeksi vs garis pasar, bukan peluang Under model
pada garis median+8**. Temuan ini memperkuat §8: cek garis market
adalah alat yang membedakan, bukan peluang Under mentah.

**Brier pasar: DATA_INCOMPLETE** (tidak ada harga pasar historis),
jadi perbandingan model vs pasar belum bisa dilakukan.

### 4.3 Uji kepekaan (DET @ ATL, 22 November 2026; garis basis 230,0; median basis 222,0)

| Variasi | Median total | Δ median | P(Under @ garis sendiri) | P(Under @ garis basis 230) | ML kandang |
|---|---|---|---|---|---|
| Basis | 222,0 | 0,0 | 0,649 | 0,649 | 0,639 |
| Bintang absen (Dyson Daniels + Cade Cunningham) | 216,0 | −6,0 | 0,654 | 0,764 | 0,702 |
| Pace +2 kedua tim | 227,0 | +5,0 | 0,660 | 0,559 | 0,637 |
| Pace −2 kedua tim | 218,0 | −4,0 | 0,658 | 0,734 | 0,641 |
| sigma_total +20% (18,22→21,86) | 222,0 | 0,0 | 0,626 | 0,626 | 0,639 |
| sigma_total −20% (18,22→14,58) | 222,0 | 0,0 | 0,685 | 0,685 | 0,639 |
| Tanpa penalti B2B | — | — | — | — | dilewati: laga ini bukan B2B untuk kedua tim |

Median total paling sensitif ke bintang absen (−6,0 poin) dan pace
(±2 pace kedua tim: +5,0/−4,0 poin). Sigma_total ±20% tidak
mengubah median sama sekali — sesuai teori, sigma hanya mengubah
sebaran — tapi mengubah P(Under) menjadi 0,626 (+20%) dan 0,685
(−20%). Pada garis yang sama (230), bintang absen menaikkan
P(Under) dari 0,649 menjadi 0,764 (+11,5 poin) dan pace −2
menaikkannya menjadi 0,734 (+8,5 poin): **input pace dan cedera
jauh lebih menentukan peluang Alt Under daripada sigma**.
Sebaliknya, P(Under pada garis median+8 sendiri) hampir tidak
berubah antar variasi lokasi (0,649–0,660), karena garis ikut
bergeser dengan median — bantalan 8 poin memberi peluang ~65%
secara stabil; yang berubah dengan lokasi adalah garisnya, bukan
peluangnya.

### 4.4 Keterbatasan yang berlaku untuk semua angka di atas

1. Bias look-ahead: rating musim penuh "melihat masa depan", sama
   seperti fit.
2. Statistik 10 laga terakhir per tanggal tidak tersedia untuk laga
   lama, jadi backtest memakai statistik musim saja (resensi 60/40
   tidak beroperasi).
3. Cedera per tanggal tidak tersedia, jadi backtest tanpa
   penyesuaian pemain absen.
4. B2B hanya dari tanggal kalender.
5. sigma_total mencakup varians OT, sedikit konservatif untuk Under.
6. Dengan n=150, tiap bucket kalibrasi berisi sedikit laga — hasil
   ini gambaran, bukan bukti kalibrasi.

## 5. Waktu tempuh 100.000x per laga

Diukur di VM ini (simulasi penuh: base case + 5 skenario skuad,
100.000 iterasi tiap skenario):

- Run 1: 1,815 dtk; run 2: 1,734 dtk; run 3: 1,854 dtk;
  contoh regenerasi §6: 1,7 dtk.
- **≈ 1,7–1,9 detik per laga** (rata-rata ~1,8 dtk).
- Satu slate 10 laga ≈ 18 detik. Tidak ada masalah kecepatan.
- Pengambilan data satu laga (`fetch_match_inputs`): ~10 detik,
  7 request (verifikasi live UTA vs DAL).
- Backtest 150 laga (2 pass 100.000x per laga): 278 detik.

## 6. Contoh output simulasi satu laga nyata

Laga: **DET @ ATL, 2026-11-22** (musim 2026-27). Input NYATA dari
`ingest.nba_brain.fetch_match_inputs`. File lengkap:
`examples/simulation_nba_ATL_DET_2026-11-22.json` (valid terhadap
`schemas/simulation.schema.json`). Dijalankan lewat
`scripts/simulate_nba_game.py ATL DET 2026-11-22`. Angka di bawah
ini dari contoh yang diregenerasi saat integrasi, setelah perbaikan
§12 (total naik 218,28 → 221,95 karena 4 pemain OUT yang semula
dihitung 0 kini masuk hitungan).

Input kunci: ATL off 113,1 / def 110,4 / pace 103,11 (musim); DET
off 114,8 / def 109,4 / pace 98,17. DET tim lebih kuat (net +5,4 vs
+2,7). Cedera: DET kehilangan Jalen Duren (BPM 8,8) dan Duncan
Robinson (BPM 2,6) — keduanya OUT; ATL kehilangan CJ McCollum
(BPM −0,6) — OUT. Total 10 pemain OUT di kedua tim.

Hasil base case (100.000x, seed acak):

- Proyeksi: DET 108,54 – 113,41 ATL (total 221,95; margin +4,87).
- Moneyline: kandang 64,1%, tandang 35,9%.
- Garis default (median total 223 → garis 222): Under 47,9% /
  Over 50,0% (sisanya ~2,1% tepat di garis = push).
- Distribusi total: mean 222,68; std 18,73; median 223; p5 192;
  p25 210; p75 235; p95 254.
- **Peluang OT: 2,6%.**
- Skenario skuad (moneyline kandang): full 46,1% (DET favorit bila
  semua sehat) → base 64,1% → missing_1 (Dyson Daniels absen)
  58,8% → missing_2 (+ Cade Cunningham absen) 70,4% → missing_4
  72,0% → doubtful_out 66,3%. Arah semua skenario benar: absennya
  bintang DET (Duren, Robinson) adalah alasan ATL favorit di base
  case padahal DET tim lebih kuat; absennya bintang ATL (Daniels)
  menurunkan peluang kandang dari base.

**Cross-check ke garis market (§8):** median model 223,0 vs garis
utama market 225,5 (§7) → selisih 2,5 poin, di bawah ambang 5,0 —
tidak ada ANOMALI `total_line_vs_model` pada laga ini. (Dengan
median pra-perbaikan 219,0, selisihnya 6,5 poin dan cek ini akan
menandai ANOMALI — ilustrasi mengapa perbaikan §12 penting.)

## 7. Koreksi besar: tangga total/spread NBA ada di Polymarket, bukan di API jup.ag

Putusan 21 November 2026 ("jup.ag tidak punya spread/total NBA",
dari 5 pemindaian penuh API jup.ag) **SALAH — dicabut**. Penyebab:
pemindai hanya membaca API jup.ag (`/events` + `/events/{id}`)
yang hanya menampilkan 2 pasar moneyline per event. UI jup.ag
menampilkan spread + total lengkap — pasarnya hidup di Polymarket
(provider asal) dan UI jup.ag menampilkannya. User yang menemukan
ini lewat screenshot + URL POLY-1338695 (22 Nov ~19:15 WIB);
koordinator memverifikasi live.

Bukti (file di `out/`, gitignored): `out/jup_event_POLY-1338695.json`
→ 2 pasar moneyline; `out/poly_event_det_atl.json` → event
Polymarket `nba-det-atl-2026-11-22` (Pistons vs Hawks), **283
pasar: 31 garis total O/U 199,5–255,5 (langkah 2 poin), 33 spread,
2 moneyline**. Tangga yang dipakai langkah ini:
`out/poly_ladder_nba-det-atl-2026-11-22.json`.

| Garis (DET @ ATL) | Harga Under (mid) | Estimasi jup.ag | Volume | Thin? |
|---|---|---|---|---|
| 225,5 (garis utama) | 52,5¢ (bid/ask 52/53) | 53,0¢ | $44.033 | tidak |
| 235,5 (Alt Under) | 71,0¢ | 71,5¢ | $9,48 | ya |
| 237,5 (Alt Under) | 75,5¢ | 76,0¢ | $6,30 | ya |
| 239,5 (Alt Under) | 80,5¢ | 81,0¢ | $5,00 | ya |

**Akibat:** (1) Alt Under NBA BISA lewat jup.ag — keputusan venue
Kalshi (a)/(b)/(c) berubah, Kalshi bukan lagi satu-satunya jalan;
(2) arsitektur: tangga total/spread dari Polymarket gamma API per
event (berdasarkan slug), BUKAN API jup.ag; (3) P2 TETAP: tangga
Polymarket adalah HARGA VENUE (yang dilihat user di UI jup.ag +
~0,5¢ markup), bukan pembanding — p_market tetap sportsbook devig →
Kalshi; (4) volume garis Alt Under jauh sangat tipis ($5–11) —
modul pasar wajib cek bid/ask + likuiditas, jangan pakai last_price
mentah di pasar tipis.

Catatan: slug memakai tanggal laga Eastern (bukan WIB/UTC). Tipe
pasar baru `team_totals` (29 pasar di event ini) saat ini
dikecualikan — perlu keputusan bila mau dipakai (§10).

## 8. Prinsip baru: bursa dibaca sebagai psikologi market/bandar

Dari user (22 Nov 19:00 WIB): data bursa BUKAN sekadar pembanding
harga — bursa dibaca sebagai psikologi market/bandar. Mesin wajib
membaca DI MANA market memasang garis dan apa artinya, lalu memakai
itu untuk menguji rasa "aman" dari model. Bahaya yang harus
dicegah: model bilang Under aman, padahal garis itu adalah batas
bawah yang ditentukan market — lalu mesin memutuskan TIDAK mengambil
bantalan poin (cushion Alt Under) dan kalah. Maka: keputusan
bantalan (8/12 poin, D10) harus mempertimbangkan posisi garis
market, bukan hanya output model; rasa "aman" model wajib
di-cross-check ke garis market sebelum kaki dipakai.

Implementasi di langkah ini (§2.4): catat garis market + harga +
waktu snapshot; bila model dan market berbeda arah soal "aman"
(mis. model sangat optimis Under tapi garis market sudah di batas
bawah / harga bergerak melawan), tandai ANOMALI + masuk pemicu
"Kenapa beda?". Validasi §4.2 memperkuat prinsip ini: peluang
Under model pada median+8 hampir tidak membedakan antar laga, jadi
yang membedakan adalah median proyeksi vs garis market — persis
yang dicek modul ini.

Ilustrasi Thunder (HIPOTETIS untuk garisnya — yang FAKTA hanya
pergerakan harga 75¢→71¢): bila model optimis Under tapi garis
market sudah di batas bawah, cek `check_cushion_vs_market` akan
menandai `cushion_tidak_dikonfirmasi_market`. Garis market Thunder
yang sebenarnya tidak diketahui — jangan dikutip sebagai fakta.

## 9. Faktor yang dimasukkan vs ditunda

| Faktor | Status | Alasan / sumber |
|---|---|---|
| ORtg/DRtg/Pace musim + last10 | Masuk | stats.nba.com tier 1 (+ fallback BBRef musim) |
| Rating pemain (BPM × menit) | Masuk | BBRef tier 2 |
| Form 5 laga, H2H 5 laga, rekor kandang/tandang | Masuk | game log stats.nba.com |
| Istirahat/B2B | Masuk | tanggal kalender; penalti −1,596 HASIL FIT |
| Ketinggian DEN/UTA | Masuk (efek ≈ 0) | HASIL FIT −0,0105 (SE 1,10) — tidak ada efek tambahan terukur |
| OT 5 menit + peluang OT | Masuk | §5a; peluang OT contoh 2,6% |
| Skenario skuad (full/missing_N/doubtful/arbitrer) | Masuk | §5a |
| Cedera dari 2 sumber | Masuk | PDF resmi + Rotowire (B2); Rotowire sering hanya 1 sumber efektif |
| Bendera turnamen | Ditunda (None) | Tidak ada sumber yang bisa menentukannya; tanggal tidak ditebak |
| Kecenderungan wasit (FT rate) | Ditunda | Belum ada sumber gratis yang terverifikasi; tidak difabrikasi |
| Penyesuaian kekuatan lawan eksplisit | Sebagian | Implisit lewat rumus proyeksi (off vs def lawan); tidak ada penyesuaian jadwal terpisah |
| Bobot resensi 60/40 | Masuk sebagai asumsi | BELUM difit — mengikuti pola §5b bola |
| bpm_scale 1,0 | Masuk sebagai asumsi | BELUM difit — tidak ada literatur internal |
| Rating rolling (tanpa look-ahead) | Ditunda | Pekerjaan lanjutan; butuh game log per tim + hitung rating berjalan |
| Harga pasar historis (Brier pasar) | DATA_INCOMPLETE | Tidak ada harga pasar historis untuk laga backtest |

## 10. Yang BELUM dibangun (di luar langkah 1)

- **Langkah 2–6** (sesuai urutan yang disetujui user 2026-11-22):
  cek ulang pra-submit, laporan lengkap + tanya-jawab, pantauan
  live, otak bola, belajar sendiri.
- **Penyambungan ujung-ke-ujung:** modul Otak NBA belum tersambung
  ke `cli.py analyze` (perintah masih memakai alur slate Tahap 2b);
  tangga Polymarket belum tersambung ke slate.
- **Tipe pasar `team_totals`** (total per tim) — dikecualikan dari
  tangga; perlu keputusan user bila mau dipakai.
- **Rating rolling** untuk menghilangkan bias look-ahead (§9).
- **Harga pasar historis** untuk Brier pasar — sumbernya belum ada.
- **Kalibrasi ambang baru** (§11) — menunggu data PAPER + keputusan
  user.
- **FPL sebagai sumber cedera bola tier 1** — masih menunggu
  ratifikasi user (tidak terkait NBA, dicatat di sini agar tidak
  hilang).
- **Keputusan venue Kalshi** (a)/(b)/(c) — tidak pernah dijawab;
  kini sebagian moot setelah §7, tapi keputusan venue itu sendiri
  tetap terbuka.

## 11. Keputusan & ambang yang menunggu persetujuan

1. **Persetujuan fit (D12):** nilai fit di `simulation.nba`
   berlaku untuk tiket nyata hanya setelah user setuju.
2. **Ambang `market_line_check`** (total_gap_points 5,0;
   min_model_under_prob 0,70): NILAI AWAL, belum dikalibrasi.
3. **Ambang `polymarket_ladder.min_volume_usd` (100,0):**
   HEURISTIK AWAL — volume Gamma kumulatif, ukuran kasar.
4. **Keputusan desain D1–D6** (LAPORAN-FIT-NBA.md §10) —
   menunggu objeksi reviewer:
   - D1: missing_N per tim (missing_1 = teratas kandang; missing_2 =
     teratas kandang + teratas tandang; missing_4 = 2 tiap tim),
     selalu di atas pemain yang sudah OUT.
   - D2: "pemain inti teratas" = dampak BPM×menit terbesar.
   - D3: "full" = kekuatan penuh hipotetis termasuk pemain OUT;
     pasar utama = base case (OUT absen).
   - D4: sigma_points = sigma total (ringkasan satu angka).
   - D5: t_nu 34,5 dari fit (nyaris normal, bukan ekor tebal
     seperti asumsi awal blueprint).
   - D6: common random numbers antar skenario.

## 12. Perbaikan koordinator saat integrasi

1. **Pemain cedera di luar 8 besar** (`ingest/nba_brain.py`):
   daftar pemain semula hanya 8 besar — pada contoh DET@ATL, 7
   dari 10 pemain OUT tidak punya data BPM/menit sehingga dampak
   absennya dihitung 0. Sekarang semua pemain cedera dimasukkan
   (tes regresi `test_pemain_cedera_di_luar_top8_tetap_masuk`);
   catatan "dampak 0" turun dari 7 menjadi 3 pemain — yang tersisa
   memang tidak ada di tabel BBRef. Contoh diregenerasi: total
   218,28 → 221,95; LAPORAN-FIT-NBA.md §6–§9 diperbarui.
2. **Config:** bagian `market_line_check`, `polymarket_ladder`,
   dan `fees.jup_typical_markup_cents` ditambahkan ke
   playstyle.yaml v5 + REQUIRED_PLAYSTYLE_SECTIONS (fail-closed),
   beserta 3 tes config baru.
3. **Validasi dijalankan ulang** setelah perbaikan (1): backtest
   mereproduksi persis (deterministik); uji kepekaan memakai input
   segar (§4.3).
4. **Verifikasi independen koordinator:** fit direproduksi persis
   (6/6 parameter); angka kalibrasi dihitung ulang dari 150 record
   per laga (Brier/mean/frekuensi cocok sampai 4 desimal); tangga
   Polymarket diverifikasi live (31 garis total, 33 spread;
   U 235,5 = 71,0¢, U 239,5 = 80,5¢); suite penuh + ruff/black
   bersih.

## 13. File yang diubah/dibuat + tes

**Tes: 613, semua lulus** (sebelum langkah ini: 406). Ruff + black
bersih di semua file langkah ini. Semua angka dari kode; tidak ada
panggilan Odds API (0 kredit) dan tidak ada data yang ditebak.

Baru: `ingest/nba_brain.py`, `engine/anomaly.py`,
`engine/validation.py`, `scripts/fit_nba_params.py`,
`scripts/simulate_nba_game.py`, `scripts/fetch_poly_ladder.py`,
`scripts/validate_nba_model.py`, `tests/test_anomaly.py`,
`tests/test_validation.py`, `tests/test_nba_sim.py`,
`tests/test_markets.py`, `tests/test_fit_nba.py`,
`tests/test_ingest_nba_brain.py`, `tests/test_polymarket_ladder.py`,
`tests/fixtures/polymarket_ladder/det_atl_sample.json`,
`examples/simulation_nba_ATL_DET_2026-11-22.json`,
`LAPORAN-FIT-NBA.md`, laporan ini.

Diubah: `engine/nba_sim.py` (tulis ulang), `engine/markets.py`,
`engine/devig.py` (blend), `ingest/stats_nba.py`,
`ingest/bbref.py`, `ingest/polymarket.py`,
`ingest/check_nba_lines.py`, `ingest/README.md`, `config.py`,
`config/playstyle.yaml` (v4 → v5), `tests/test_config.py`,
`tests/test_devig.py`, `tests/test_ingest_stats_nba.py`,
`tests/test_ingest_bbref.py`,
`tests/test_ingest_check_nba_lines.py`, `tests/test_stubs.py`
(3 stub dihapus karena sudah diimplementasi).

Bukti (gitignored, tidak di-commit): `out/fit_nba_params.json`,
`out/validation_nba.json`,
`out/sensitivity_inputs_det_atl.json`,
`out/poly_ladder_nba-det-atl-2026-11-22.json`,
`out/jup_event_POLY-1338695.json`, `out/poly_event_det_atl.json`,
`data/nba_history/` (game log + rating 3 musim).
