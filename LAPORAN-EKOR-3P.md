# LAPORAN EKOR 3 POIN PER LAGA — Item 4 Build Penyempurnaan Mesin

Tanggal: 2026-11-23. Bahasa: Indonesia. Semua angka dari kode Python
(`scripts/fit_ekor_3p.py`, `scripts/verifikasi_ekor_3p.py`); tidak ada
angka karangan. Worker C; koordinator mengintegrasi + commit.

> **Kesimpulan satu kalimat:** data 2.466 laga TIDAK mendukung klaim
> "laga dua tim penembak tripoin ekornya lebih gemuk" — efek laju 3PA
> gabungan pada varians residual total tidak terukur (slope −0,34 ±
> 1,97, t=−0,17), sehingga **slope aktif yang dipakai sim = 0,0**
> (sigma global, sama seperti model lama). Mesin penskalaan per laga
> dibangun + dites dan siap dipakai bila kalibrasi ulang nanti
> menemukan efek yang signifikan.

## 1. Ringkasan

| Item | Hasil |
|---|---|
| Metode yang dipilih | (a) regresi varians: `sigma_total_laga² = sigma_global² + slope × (3PA_gabung − pusat)`, dijepit [0,5×, 2,0×] sigma global |
| Slope fit (regresi utama) | **−0,3364** (SE 1,9697, t=−0,17, CI95 [−4,20, +3,53], R²=0,0000) — TIDAK SIGNIFIKAN |
| Slope aktif di sim | **0,0** (mengikuti preseden altitude: nilai fit dalam noise tidak diadopsi) |
| Pusat (3PA gabungan rata-rata liga) | **74,54** (FIT, n=2.466, sd 5,30) |
| Jepit sigma | 0,5× / 2,0× — PILIHAN DESAIN (bukan fit), menunggu keberatan |
| Slope binomial teoritis | +2,0689 (pembanding, bukan fit) — berada DALAM CI95 fit |
| DEN@CHI model baru vs lama | **IDENTIK** (slope 0): median 233, P(Under 252,5) 84,72% — model baru TIDAK melihat DEN lebih berisiko |
| OKC@MIA model baru vs lama | **IDENTIK**: median 220, P(Under 252,5) 95,04% — laga normal tidak terganggu |
| Tes | 35 tes baru (`tests/test_ekor_3p.py`) + 4 tes baru nba_brain; full suite 1.627 tes, 3 gagal — ketiganya BUKAN dari pekerjaan ini (lihat §9) |
| Kredit Odds API | 0 |

Hasil lengkap (JSON, gitignored): `out/fit_ekor_3p.json`,
`out/verifikasi_ekor_3p.json`. Data mentah FG3A:
`data/nba_history/fg3a_*.json` (gitignored).

## 2. Masalah + hipotesis

Sim memakai satu `sigma_total` global (18,9868) untuk semua laga.
Hipotesis yang diuji: laga dua tim penembak tripoin punya ekor total
lebih gemuk, karena poin tripoin (3 poin per percobaan, peluang masuk
~36%) lebih bervariasi daripada poin dua angka. DEN@CHI 22 Nov 2026
adalah pemicu: median pra-laga 233, total akhir 296 (OT), 42 tripoin
masuk dari 90 percobaan (DEN 17-35, CHI 25-55); model lama memberi
P(Under 252,5) normal 84,47% — laga itu terlihat cukup aman.

Mekanisme binomial memberi prediksi kuantitatif: varians poin tripoin
per 1 percobaan tambahan = 9 × p(1−p) ≈ 9 × 0,3581 × 0,6419 =
**+2,0689** poin² per 3PA gabungan. Bila mekanisme itu menembus penuh
ke varians residual total, regresi `resid_total² ~ 3PA_gabung` harus
memberi slope ≈ +2,07. Itu yang diuji — bukan sekadar "apakah ada
efek", tapi "apakah efek sebesar prediksi teori ada".

## 3. Data

- **Game log + residual:** sama seperti fit NBA yang ada
  (`data/nba_history/games_all.json`, 2.701 laga 2024-25 s.d.
  2026-27) dengan **rating rolling point-in-time** (dipakai ulang dari
  `scripts/fit_nba_params.py`) — tidak ada look-ahead bias: rating
  maupun laju 3PA hanya memakai laga SEBELUM tanggal laga yang
  diproyeksikan.
- **Laju 3PA:** FG3A/FG3M/FGA per tim per laga diekstrak dari respons
  mentah leaguegamefinder di DiskCache `out/cache/` (kunci = SHA-256
  URL; **TTL sengaja diabaikan** — snapshot historis; fallback fetch
  langsung bila cache tidak ada, tanpa kunci API, 0 kredit Odds).
  Laga berjalan di snapshot (WL kosong — 8 baris di snapshot 22 Nov,
  termasuk DEN@CHI sendiri) **dilewati**, bukan dipakai setengah
  jalan.
- **Dipakai:** 2.466 laga; dilewati 235 laga (awal musim — salah satu
  tim belum 5 laga sebelumnya, ambang `MIN_LAGA_UNTUK_LAJU = 5`) dan
  0 laga tanpa rolling.
- **Laju 3PA gabungan:** rata-rata 74,54, sd 5,30, rentang 59,4–95,2.
- **Catatan lingkungan:** `stats.nba.com` TIDAK dapat dijangkau dari
  VM ini saat fit (curl timeout); seluruh angka di atas berasal dari
  cache + file ekstrak lokal, bukan fetch baru.

## 4. Metode fit

`scripts/fit_ekor_3p.py` (mirip struktur `fit_nba_params.py`):

1. Untuk tiap laga historis: proyeksi total dari rating rolling
   (rumus sama persis dengan `engine.nba_sim.project_points`) →
   `resid_total` = total aktual − total proyeksi.
2. Laju 3PA point-in-time tiap tim = rata-rata FG3A per laga dari
   semua laga SEBELUM tanggal laga (min 5 laga). Juga dihitung 3P%,
   sd 3PM, share 3PA, dan varians binomial tersirat per tim.
3. **Regresi utama:** OLS `resid_total² ~ a + b × 3PA_gabung`.
   Kriteria signifikansi: |t| ≥ 2,0 (keputusan desain, menunggu
   keberatan — lihat §8).
4. **Uji ketahanan:** regresi yang sama pada varians margin,
   |residual| total/margin, 3P% gabungan, sd 3PM gabungan, share 3PA,
   varians binomial tersirat, max/min 3PA tim; tabel kuartil 3PA
   (sd + ekor atas residual per kuartil); slope per musim.
5. **Verdict:** `SIGNIFIKAN` bila |t| ≥ 2,0 (slope aktif =
   slope fit); `TIDAK_SIGNIFIKAN` bila tidak (slope aktif = 0,0);
   `DATA_TIDAK_CUKUP` bila n < 100.

## 5. Bukti data: HASIL NOL (null result)

### 5.1 Regresi utama

| Regresi | Slope | SE | t | CI95 | R² |
|---|---|---|---|---|---|
| **resid_total² ~ 3PA_gabung (UTAMA)** | **−0,3364** | 1,9697 | **−0,17** | [−4,20, +3,53] | 0,0000 |
| resid_margin² ~ 3PA_gabung | −0,0882 | 1,2064 | −0,07 | [−2,45, +2,28] | 0,0000 |
| \|resid_total\| ~ 3PA_gabung | +0,0068 | 0,0436 | +0,16 | [−0,08, +0,09] | 0,0000 |
| \|resid_margin\| ~ 3PA_gabung | +0,0024 | 0,0342 | +0,07 | [−0,06, +0,07] | 0,0000 |
| resid_total² ~ 3P%_gabungan | −175,81 | 730,70 | −0,24 | [−1607,98, +1256,37] | 0,0000 |
| resid_total² ~ sd_3PM_gabung | +10,64 | 14,00 | +0,76 | [−16,79, +38,07] | 0,0002 |
| resid_total² ~ share_3PA | −229,36 | 356,12 | −0,64 | [−927,37, +468,64] | 0,0002 |
| resid_total² ~ var_3P_binomial | −0,1947 | 0,9019 | −0,22 | [−1,96, +1,57] | 0,0000 |
| resid_total² ~ max(3PA_tim) | −0,1226 | 3,0959 | −0,04 | [−6,19, +5,95] | 0,0000 |
| resid_total² ~ min(3PA_tim) | −0,9991 | 3,6764 | −0,27 | [−8,20, +6,21] | 0,0000 |

Semua uji varians memberi t di bawah 1 — bukan cuma regresi utama.
Slope binomial teoritis +2,07 berada DALAM CI95 regresi utama, jadi
data tidak bisa membedakan "tidak ada efek" dari "efek sebesar teori";
yang bisa dikatakan: estimasi titik ≈ 0 dan efeknya, bila ada, di
bawah daya deteksi 2.466 laga.

### 5.2 Tabel kuartil — sebaran DATAR, ekor atas justru lebih tipis

| Kuartil 3PA gabungan | n | 3PA rata-rata | sd resid_total | p95 resid_total | p99 resid_total | P(\|resid\| > 30) |
|---|---|---|---|---|---|---|
| Q1 rendah | 617 | 68,05 | 19,12 | 36,4 | 49,6 | 12,3% |
| Q2 | 616 | 72,72 | 18,69 | 33,2 | 44,6 | 10,6% |
| Q3 | 616 | 75,93 | 18,73 | 32,9 | 49,2 | 10,1% |
| Q4 tinggi | 617 | 81,47 | 19,01 | 31,2 | 44,3 | 11,4% |

Bila hipotesis benar, Q4 harus punya sd dan ekor atas JELAS lebih
besar dari Q1. Kenyataannya sd datar (19,12 → 19,01) dan ekor atas
Q4 justru lebih tipis (p95 31,2 vs 36,4; p99 44,3 vs 49,6).

### 5.3 Slope per musim tidak stabil

| Musim | n | Slope | t |
|---|---|---|---|
| 2024-25 | 1.152 | −0,89 | −0,32 |
| 2025-26 | 1.151 | +2,90 | +0,97 |
| 2026-27 (parsial) | 163 | −16,03 | −2,17 |

Tanda slope berubah tiap musim — pola khas noise, bukan efek nyata.
Nilai 2026-27 (t=−2,17) berasal dari n=163 saja dan arahnya NEGATIF
(berlawanan dengan hipotesis); tidak dipakai sebagai bukti apa pun.

### 5.4 Temuan samping (TIDAK diimplementasikan — di luar ruang lingkup)

Ada efek MEAN yang signifikan: `resid_total ~ 3PA_gabung` memberi
slope **−0,2087** (SE 0,0717, **t=−2,91**, R²=0,0034) — laga 3PA
tinggi cenderung mencetak total SEDIKIT lebih rendah dari proyeksi
model (sekitar −2,1 poin per +10 3PA gabungan). Efek ini bertahan
saat mengontrol proyeksi total + pace (b=−0,183, t=−2,58). Ini
adalah soal KALIBRASI MEAN proyeksi, bukan soal ekor/varians, dan
bukan tugas item ini — dicatat untuk pekerjaan lanjutan, bukan
dimasukkan ke sim. (Temuan samping kedua, juga di luar lingkup:
`resid ~ pace` b=+2,34, t=8,54 — pace juga salah kalibrasi.)

## 6. Parameter baru (config `ekor_3p:`)

Ditambahkan di `config/playstyle.yaml` (section baru `ekor_3p:`;
baris `version:` TIDAK diubah — koordinator yang bump ke v16):

| Kunci | Nilai | Status |
|---|---|---|
| `slope_aktif` | 0,0 | FIT → TIDAK SIGNIFIKAN → 0,0 (preseden altitude) |
| `tiga_pa_gabungan_rata_liga` | 74,54 | FIT (rata-rata sampel, n=2.466) |
| `sigma_min_faktor` | 0,5 | PILIHAN DESAIN (bukan fit) — menunggu keberatan |
| `sigma_max_faktor` | 2,0 | PILIHAN DESAIN (bukan fit) — menunggu keberatan |

Slope fit (−0,3364 ± 1,97) dicatat di KOMENTAR config, bukan sebagai
kunci aktif — sengaja, supaya tidak ada yang mengaktifkannya tanpa
keputusan sadar.

**Rencana kalibrasi** (juga tercatat di `out/fit_ekor_3p.json`):
jalankan ulang `scripts/fit_ekor_3p.py` tiap akhir musim (n bertambah
~1.230 laga/musim) dan saat ada cukup laga musim berjalan; bila |t|
regresi utama ≥ 2,0, ajukan slope fit sebagai `slope_aktif` ke user
(seperti D12). Bila efek tetap tidak terukur setelah n ≥ 5.000,
pertimbangkan menutup hipotesis laju-3PA dan mengalihkan perhatian ke
prediktor ekor lain (mis. volatilitas pace per laga atau 3P% lawan).

## 7. Perubahan kode

| File | Perubahan |
|---|---|
| `ingest/bbref.py` | `_parse_totals_team_once` juga membaca kolom `fg3` (tripoin masuk): menambah `fg3_per_game` + `fg3_pct` (dihitung fg3/fg3a dari total mentah). `fg3` TIDAK wajib — kolom hilang → None, 3PA tetap mengalir. |
| `ingest/nba_brain.py` | Blok tim mendapat `tembakan_3p` (fg3a/fg3 per laga, 3P%, games, source, tier, time) dari `fetch_team_shooting_baselines` — halaman BBRef yang SAMA dengan `fetch_team_advanced`, cache 6 jam, biasanya 0 request tambahan. Fetch ini enrichment (seperti `players_musim_lalu`): tidak menambah `n_ok`, tidak memengaruhi `ok`. Gagal → `tembakan_3p: null` + dicatat di `missing` (DATA_INCOMPLETE, bukan tebakan). Data MENTAH season-to-date tanpa shrinkage (seperti `bpm_raw`/`mp_raw`); `games` menunjukkan seberapa awal musimnya. |
| `engine/nba_sim.py` | `ENGINE_VERSION` 1.1.0 → **1.2.0** (kapabilitas baru, perilaku default sama). `simulate()` menghitung sigma total PER LAGA dari laju 3PA gabungan bila section ada + slope ≠ 0 + data kedua tim ada; bila tidak, fallback ke sigma global dengan `sumber_sigma` yang TERCATAT (`per_laga`, `global_slope_nol`, `global_tanpa_data_3pa`, `global_tanpa_config`) + catatan di `inputs_summary.notes`. `inputs_summary` mendapat `sigma_total_global_points` + dict `ekor_3p` lengkap. Config ekor tidak valid → `ValueError` (gagal keras, bukan diam-diam); section hilang → global + catatan (kompatibel dengan fixture tes lama). Tidak ada perubahan skema (`inputs_summary` membolehkan properti tambahan). |
| `scripts/fit_ekor_3p.py` | BARU — script fit (§4). |
| `scripts/verifikasi_ekor_3p.py` | BARU — verifikasi DEN + OKC (§8). |
| `tests/test_ekor_3p.py` | BARU — 35 tes (lihat §9). |
| `tests/test_ingest_nba_brain.py` | SHOOTING fixture + patch default; `test_kontrak_lengkap` sources 7→8; `test_semua_sumber_gagal` 7→8 fetch; 2 tes shrinkage memetakan `tembakan_3p` ke pemanggilan langsung `_build_team_block`; kelas `TestTembakan3p` baru (4 tes). |

File yang TIDAK disentuh sesuai tugas: `DECISIONS.md`,
`engine/ticket_composer.py`, `engine/equilibrium.py`,
`ingest/news_nba.py`, `engine/nba_analysis.py`, `engine/recheck.py`,
`report/`.

## 8. Verifikasi wajib: DEN@CHI + OKC@MIA

Metode: inputs pra-laga ASLI dari
`out/analysis_verif_tahap4_2026-11-22.json` (sim 22 Nov 21:57 UTC —
run yang sama dengan audit tiket nyata) + blok `tembakan_3p`
point-in-time (laga sebelum 22 Nov). 100.000 iterasi, seed 20261122.
Reproduksi tervalidasi: skenario "lama" mereproduksi median historis
DEN (233,0) persis dan P(Under 252,5) 0,8472 vs historis 0,84474
(dalam noise Monte Carlo); OKC median 220,0 persis, P 0,9504 vs
0,95067.

### 8.1 DEN@CHI — 3PA gabungan pra-laga 71,59 (DEN 30,86 + CHI 40,73)

DEN adalah tim 3PA RENDAH (persentil ke-29 gabungan). Banjir yang
terjadi adalah lonjakan percobaan DALAM laga (90 vs ~72 yang
diharapkan) + lonjakan akurasi (46,7% vs ~33% gabungan musim) —
bukan sesuatu yang bisa diprediksi laju 3PA musim berjalan.

| Skenario | sigma | median | std | p95 | P(U 252,5) | P(≥ 264,5) | P(≥ 296) | P(U 252,5 \| banjir) |
|---|---|---|---|---|---|---|---|---|
| lama | 18,99 | 233,0 | 19,40 | 265,0 | 0,8472 | 0,0522 | 0,0013 | 0,6266 |
| **baru_produksi** | 18,99 | 233,0 | 19,40 | 265,0 | 0,8472 | 0,0522 | 0,0013 | 0,6266 |
| kontrafaktual_binomial (+2,07) | 18,83 | 233,0 | 19,24 | 265,0 | 0,8488 | 0,0508 | 0,0014 | 0,6275 |
| kontrafaktual_fit (−0,34) | 19,01 | 233,0 | 19,42 | 265,0 | 0,8467 | 0,0522 | 0,0014 | 0,6266 |
| sintetis_3pa_tinggi (gabungan 90, binomial) | 19,81 | 233,0 | 20,23 | 266,0 | 0,8371 | 0,0592 | 0,0017 | 0,6222 |

**Vonis:** model baru TIDAK melihat DEN lebih berisiko — angka
produksi identik dengan model lama (slope 0). Bahkan kontrafaktual
binomial membuat DEN terlihat SEDIKIT LEBIH AMAN (3PA gabungannya di
bawah rata-rata liga). Baris sintetis membuktikan mesin penskalaan
bekerja ke arah yang dimaksud (sigma naik, P(Under) turun) bila
suatu laga memang ber-3PA tinggi. DEN tidak bisa ditangkap model
3PA-rate — pertahanannya adalah seleksi + gate banjir/edge/volume,
bukan ekor 3P.

### 8.2 OKC@MIA (laga normal) — 3PA gabungan 72,61; total aktual 236

| Skenario | sigma | median | std | p95 | P(U 252,5) | P(≥ 264,5) | P(≥ 296) | P(U 252,5 \| banjir) |
|---|---|---|---|---|---|---|---|---|
| lama | 18,99 | 220,0 | 19,35 | 252,0 | 0,9504 | 0,0130 | 0,0002 | 0,8321 |
| **baru_produksi** | 18,99 | 220,0 | 19,35 | 252,0 | 0,9504 | 0,0130 | 0,0002 | 0,8321 |
| kontrafaktual_binomial | 18,88 | 220,0 | 19,26 | 252,0 | 0,9513 | 0,0124 | 0,0002 | 0,8327 |
| kontrafaktual_fit | 19,00 | 220,0 | 19,37 | 252,0 | 0,9500 | 0,0130 | 0,0002 | 0,8320 |

Model baru tidak mengacaukan laga biasa: angka produksi identik
dengan model lama.

## 9. Tes

- **Baru:** `tests/test_ekor_3p.py` — 35 tes: OLS (pemulihan slope
  diketahui, gagal pada n<3 / varians x=0); parse FG3A (laga berjalan
  dilewati, resultSet hilang → ValueError, baris tanpa angka
  dilewati); laju point-in-time (laga tanggal yang sama tidak masuk,
  ambang min 5 laga, nilai hitung tangan); fit ujung-ke-ujung pada
  data sintetis (slope benar 2,0 dipulihkan + verdict SIGNIFIKAN;
  slope 0 → TIDAK_SIGNIFIKAN + slope aktif 0,0; n kecil →
  DATA_TIDAK_CUKUP); config ekor + rumus sigma (nilai hitung tangan,
  jepit 0,5×/2,0×, nilai tidak valid → ValueError); integrasi
  `simulate()` (sigma membesar pada laju tinggi, slope 0 identik
  dengan model lama pada seed sama, fallback tercatat, validasi
  skema, determinisme); parser fg3 BBRef (dengan/tanpa kolom fg3,
  fg3a=0, fixture lama tetap terbaca).
- **Diubah:** `tests/test_ingest_nba_brain.py` — 4 tes baru
  `TestTembakan3p` + penyesuaian fixture (sumber 7→8, fetch 7→8)
  yang DIDOKUMENTASIKAN di komentar tes. Tidak ada tes yang dihapus.
- **Targeted:** `test_ekor_3p` + `test_ingest_nba_brain` +
  `test_nba_sim` + `test_fit_nba` + `test_config` +
  `test_live_anomaly` = **216 tes, OK**.
- **Full suite:** **1.627 tes, 3 gagal** — ketiganya di
  `tests.test_ticket_composer.TestGateBanjirAsuransi`
  (`test_garis_tahan_banjir_dipakai_bila_tidak_thin`,
  `test_garis_tahan_banjir_thin_skip_meski_garis_atas_tebal`,
  `test_racik_penuh_dengan_kaki_naik_garis`). Kegagalan: alasan naik
  garis `reason: 'equilibrium'` vs yang diharapkan `'banjir'` —
  berasal dari perubahan worker equilibrium di
  `engine/ticket_composer.py`, BUKAN dari pekerjaan ini. Bukti:
  dengan file-file saya dikembalikan ke HEAD (sim/brain/bbref murni
  HEAD, config + kode worker lain tetap), ketiga tes itu TETAP gagal.
  File saya sudah dikembalikan penuh setelah eksperimen itu (90 tes
  ekor/brain OK setelah restore). Perbaikan ketiga tes itu adalah
  urusan worker equilibrium / koordinator — saya tidak menyentuhnya
  (file worker lain).
- **Lint:** ruff + black bersih pada semua file yang diubah/dibuat.

## 10. Keputusan desain yang menunggu keberatan

1. **Slope aktif 0,0** (bukan slope fit −0,34): mengikuti preseden
   altitude di repo ini — nilai fit yang berada dalam noise tidak
   diadopsi. Alternatifnya mengadopsi slope fit negatif (yang akan
   membuat laga 3PA tinggi terlihat SEDIKIT LEBIH AMAN — arah yang
   berlawanan dengan intuisi dan tidak signifikan) — ditolak.
2. **Jepit sigma 0,5×/2,0×**: pilihan desain, bukan fit. Menjaga
   sigma tidak pernah menjadi negatif/tak masuk akal pada slope
   ekstrem di masa depan.
3. **Ambang signifikansi |t| ≥ 2,0**: konvensi standar (~p<0,05),
   bukan fit.
4. **`MIN_LAGA_UNTUK_LAJU = 5`**: laju 3PA butuh minimal 5 laga
   sebelumnya; laga awal musim dilewati dari fit (235 laga). Nilai 5
   adalah pilihan desain (menyeimbangkan noise awal musim vs
   kehilangan data).
5. **Data mentah tanpa shrinkage di `tembakan_3p`**: laju
   season-to-date disimpan apa adanya (seperti `bpm_raw`); noise
   awal musim terlihat lewat field `games`. Tidak ada penyusutan ke
   rata-rata liga.
6. **Section `ekor_3p` opsional di kode** (hilang → sigma global +
   catatan): demi kompatibilitas fixture tes lama. Nilai yang ADA
   tapi tidak valid → `ValueError` (gagal keras).
7. **Efek mean (t=−2,91) TIDAK diimplementasikan**: di luar ruang
   lingkup item ini (ekor/varians, bukan kalibrasi mean). Dilaporkan
   untuk pekerjaan lanjutan.

## 11. Batasan jujur

- **Daya deteksi:** pada n=2.466, CI95 slope [−4,20, +3,53] masih
  mencakup slope binomial teoritis +2,07. Hasil nol ini membuktikan
  "efek tidak terukur pada data ini", BUKAN "efek tidak ada".
  Kalibrasi ulang pada n ≥ 5.000 bisa mengubah verdict.
- **Laju 3PA tidak memprediksi banjir dalam laga:** banjir DEN
  adalah lonjakan percobaan (90 vs ~72) + akurasi (46,7% vs ~33%)
  DALAM laga. Model laju musim berjalan, seberapa pun baiknya, tidak
  bisa menangkap itu. Pertahanan terhadap banjir tetap gate
  banjir/edge/volume + seleksi laga.
- **Laju awal musim berisik:** di awal musim (5–15 laga), laju
  season-to-date masih berisik; tidak ada shrinkage. Bila slope
  aktif suatu hari ≠ 0, noise ini ikut masuk sigma.
- **Residual fit tidak mengandung cedera:** sama seperti fit dasar
  NBA — proyeksi rolling tidak tahu siapa yang cedera pada laga
  historis. Bila cedera berkorelasi dengan laju 3PA, slope bisa bias
  (arah bias tidak diketahui).
- **Hanya varians total yang dimodelkan:** sigma margin tidak
  disesuaikan per laga (uji varians margin juga nol, t=−0,07).
- **Satu global sigma untuk bentuk ekor lain:** model ini hanya
  menskala sigma Student-t; tidak mengubah derajat kebebasan (t_nu)
  per laga. Bila ekor 3P mengubah BENTUK (bukan hanya lebar)
  sebaran, model ini tidak menangkapnya — tetapi data tidak memberi
  alasan untuk model bentuk yang lebih rumit.
