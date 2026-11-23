# LAPORAN SETAN PER PEMAIN — Demon 3 Poin Berbasis Data Pemain

Tanggal: 2026-11-23. Bahasa: Indonesia. Semua angka dari kode Python
(`engine/setan_pemain.py`, `ingest/pemain_3p.py`,
`scripts/verifikasi_setan_pemain.py`); tidak ada angka karangan.
Worker C; koordinator mengintegrasi + commit. TIDAK ADA commit dari
worker ini.

> **Kesimpulan satu kalimat:** setan per pemain bekerja dan menandai
> kedua kaki DEN@CHI sebagai rapuh — total setan **274,14** (deviasi
> **+37,64** dari garis bandar 236,5; **+23,07** di atas setan umum
> 251,07), P setan 13,0%/11,8% untuk kaki U252,5/U250,5 — tapi
> levelnya SENSITIF terhadap ambang percobaan minimum % terbaik liga
> (ambang 50 → 54,1% Cam Spencer → 274,14; ambang 75 → 47,2% Jamal
> Murray → 260,21; ambang 150 → 37,6% → 240,83, tidak lagi
> menandai kaki) — vonis "rapuh" kokoh untuk ambang 25–100, levelnya
> yang bergerak.

## 1. Ringkasan

| Item | Hasil |
|---|---|
| Total setan pemain DEN@CHI (live) | **274,14** (geser +41,14 dari median 233,0) |
| Deviasi vs garis bandar 236,5 | **+37,64** |
| Kaki U252,5 (Asuransi) | **RAPUH** — flag_setan_pemain True, p_setan_pemain 0,1298 |
| Kaki U250,5 (Utama) | **RAPUH** — flag_setan_pemain True, p_setan_pemain 0,1184 |
| Setan umum (pembanding) | 251,07 (median + 18,07); pemain +23,07 di atasnya |
| Total aktual | 296 — setan pemain TIDAK menutupinya (+21,86 di bawah aktual), sesuai tugasnya: menandai kerapuhan, bukan memprediksi banjir |
| % 3P terbaik liga dipakai | **54,1% — Cam Spencer (MEM)**, 61,2 percobaan total, 17 laga (stats.nba.com; BBRef sepakat persis) |
| Percobaan yang diharapkan | 67,30/laga (DEN 32,10 + CHI 35,20; 22 pemain rotasi yang main) |
| Point-in-time (data BBRef s.d. 21 Nov) | 273,03 — hanya −1,11 dari 274,14 (kontaminasi look-ahead kecil) |
| Perkiraan kasar koordinator (~258) | Terlampaui +16,14 — penyebabnya: % terbaik liga sebenarnya 54,1%, bukan ~45% (lihat §4.3) |
| Tes baru | **34 tes** (`tests/test_setan_pemain.py`), semua lulus |
| Kredit Odds API | 0 |

Hasil lengkap (JSON, gitignored): `out/verifikasi_setan_pemain.json`.
Script verifikasi: `scripts/verifikasi_setan_pemain.py`.

## 2. Sumber data + verifikasi ketersediaan

Kedua sumber GRATIS, terverifikasi live 2026-11-23 dari VM ini
(0 kredit Odds API). Satu tarikan mencakup SELURUH liga (bukan satu
tim), sehingga % terbaik liga dihitung dari data yang sama.

| Sumber | Status | Endpoint / halaman | Isi |
|---|---|---|---|
| stats.nba.com (jenjang 1, UTAMA) | ✅ 200, 474 pemain | `leaguedashplayerstats`, MeasureType=Base, PerMode=PerGame | PLAYER_NAME, TEAM_ABBREVIATION, GP, MIN, FG3A, FG3M, FG3_PCT per laga |
| Basketball-Reference (jenjang 2, FALLBACK) | ✅ 200, 478 pemain | `leagues/NBA_2027_per_game.html`, tabel id=`per_game_stats` (ADA di HTML mentah) | name_display, team_name_abbr, games, mp_per_g, fg3_per_g, fg3a_per_g, fg3_pct |

Temuan probe:
- **stats.nba.com BISA dijangkau sekarang** (berbeda dengan saat fit
  ekor 3P, ketika curl timeout — LAPORAN-EKOR-3P.md §3). Karena
  riwayat tidak stabil itulah fallback BBRef tetap diimplementasikan
  (`fetch_pemain_3p` mencoba stats.nba.com dulu, lalu BBRef; sumber
  yang dipakai tercatat di `extra["source_used"]`).
- **BBRef tertinggal satu laga**: GP tiap pemain DEN/CHI di BBRef
  tepat 1 lebih sedikit dari stats.nba.com (laga 22 Nov belum masuk
  saat ditarik). Kebetulan yang berguna: data BBRef menjadi
  perkiraan pra-laga yang jujur (§4.2). Efeknya kecil pada demon
  (−1,11 poin) tetapi mengubah komposisi rotasi CHI: Jordan Hawkins
  10,1 mpg (stats.nba.com) vs 9,6 mpg (BBRef) — di BBRef ia jatuh di
  bawah ambang rotasi 10,0 dan dikeluarkan.
- **Cross-check sumber**: DEN identik (11 pemain rotasi, 32,7
  percobaan di kedua sumber). CHI: 15 pemain / 49,1 percobaan
  (stats.nba.com) vs 14 / 45,2 (BBRef) — selisihnya hampir seluruhnya
  Hawkins + laga 22 Nov yang belum masuk BBRef. % terbaik liga
  identik di kedua sumber (Cam Spencer 54,1%).
- **Nama pemain tidak selalu sama antar sumber**: "DaRon Holmes II"
  (stats.nba.com) vs "DaRon Holmes" (BBRef). Filter absen memakai
  pencocokan nama persis; nama yang tidak cocok dicatat (bukan
  error). Di kasus ini tanpa dampak (2,4 mpg — di bawah ambang
  rotasi). Lihat batasan §10.
- **Status ketersediaan (main/absen) TIDAK ada di kedua sumber** —
  keduanya hanya statistik musim berjalan. Ketersediaan diambil dari
  data cedera artefak analisis (`engine/setan_pemain.py:
  pemain_absen_dari_artefak`, membaca `injuries.entries` status OUT
  + daftar cedera tingkat slate); bila data cedera tidak tersedia,
  satu-satunya proksi adalah menit (ambang rotasi) — dicatat di
  hasil. Tidak ada tebakan ketersediaan yang diisi.

Keputusan modul: modul BARU `ingest/pemain_3p.py`, bukan perluasan
`ingest/player_gamelog.py` — player_gamelog adalah halaman game log
PER PEMAIN (untuk `missed_last10`), sedangkan yang dibutuhkan di sini
adalah statistik per laga SELURUH LIGA dari halaman yang berbeda
(leaguedashplayerstats / per_game). Mencampurnya akan mengaburkan
kontrak kedua modul.

Cache + rate limit mengikuti modul ingest lain: stats.nba.com TTL
10 menit + jeda 1 dtk (sama seperti `ingest/stats_nba.py`); BBRef
TTL 6 jam + jeda 4 dtk lewat client bersama `ingest.bbref`
(limiter yang SAMA — request semua modul BBRef tetap terjeda satu
sama lain).

## 3. Rumus persis

Rumus disetujui user 2026-11-23 12:38 WIB (DECISIONS.md "Jawaban 4
pertanyaan" poin 2–3):

**Demon per pemain** = percobaan 3P per laganya × % 3P TERBAIK liga
musim ini.

**Percobaan yang diharapkan** (bukan jumlah naif seluruh roster):
- Pemain OUT (data cedera artefak) → 0 percobaan.
- Pemain di luar rotasi (menit/laga < `ambang_menit_rotasi` = 10,0)
  → tidak dihitung.
- Pemain rotasi yang main → percobaan = fg3a per laga musim ini
  (per laga yang DIMAINKAN pemain — basis kekuatan penuh, lihat
  §3.1).

**Per tim**:
- poin 3P normal = Σ (percobaan × % 3P pemain × 3)
- poin 3P setan = Σ (percobaan × % terbaik liga × 3)

**Per laga**:
- total_setan = median_total − poin_3P_normal_kedua_tim +
  poin_3P_setan_kedua_tim
- geser_setan_pemain = total_setan − median_total
- deviasi vs garis bandar = total_setan − garis bandar (None bila
  garis bandar tidak ada)
- P setan per kaki = CDF_sim(garis_kaki − geser_setan_pemain)
  (dihitung di `engine/stress.py`, cara yang sama seperti skenario
  banjir/setan umum — interpolasi linear, dijepit ke ujung CDF)
- flag_setan_pemain = total_setan > garis kaki

**% terbaik liga**: % tertinggi di antara pemain dengan total
percobaan 3P musim ini ≥ `pct_terbaik_min_total_3pa` = 50 (INITIAL).
Seri % → total percobaan lebih besar menang; seri penuh → nama
pertama menurut abjad (deterministik).

### 3.1 Basis kekuatan penuh (keputusan desain, baca baik-baik)

fg3a per laga di kedua sumber adalah per laga yang DIMAINKAN pemain,
bukan per laga tim. Pemain yang absen di sebagian laga musim ini
(tapi main malam ini) menyumbang rata-rata per laganya secara penuh.
Itu BENAR untuk ekspektasi malam ini bila ia main — dan jumlahnya
berjalan DI ATAS rata-rata 3PA tim per laga musim ini (yang meratakan
laga-laga saat pemain itu absen). TIDAK ada penskalaan rasio
laga-dimainkan/laga-tim: rumus yang disetujui user berkata
"percobaan 3 poin per laganya", dan penskalaan itu akan
bertentangan dengan rumus tersebut (juga akan meremehkan bintang
yang baru sembuh dari cedera). Konsekuensi yang terukur di DEN@CHI:
tanpa pengeluaran pemain OUT, basis kekuatan penuh berjalan ~10
percobaan di atas rata-rata tim pra-laga 71,59; SETELAH pengeluaran
OUT (Wilson 7,1 + Powell 6,8 percobaan/laga), percobaan yang
diharapkan justru 67,30 — DI BAWAH 71,59. Perbandingan ini
menunjukkan pengeluaran OUT bekerja lebih keras daripada efek basis
kekuatan penuh di laga ini.

### 3.2 Status epistemik (bukan prediksi)

Regresi ekor 3P (LAPORAN-EKOR-3P.md, n=2.466) menemukan laju 3PA
TIDAK memengaruhi ekor total (slope −0,3364, t=−0,17). Setan per
pemain TIDAK bertentangan dengan hasil itu: ia BUKAN prediksi, ia
UJI STRESS (batas atas) — "kalau SEMUA pemain rotasi kedua tim
menembak sebaik penembak terbaik liga dalam satu laga yang sama,
totalnya bisa sampai berapa?" Nilainya dipakai sebagai DETEKSI
kerapuhan, bukan sebagai peluang terjadinya. Tidak ada klaim bahwa
skenario itu mungkin atau akan terjadi — dan faktanya, di DEN@CHI,
banjir aktual (42 tripoin masuk) MELAMPAUI skenario setan (36,4
tripoin masuk tersirat: 109,23 poin ÷ 3) karena banjir aktual JUGA
menaikkan JUMLAH percobaan (90 vs 67,3 yang diharapkan), yang tidak
dimodelkan setan per pemain (lihat batasan §10).

## 4. Bukti verifikasi DEN@CHI

Metode: inputs pra-laga ASLI dari
`out/analysis_verif_tahap4_2026-11-22.json` (median 233,0; garis
bandar 236,5; CDF sim) + data pemain live + 8 pemain OUT dari
artefak. Script: `scripts/verifikasi_setan_pemain.py`.

### 4.1 Angka-angka

| | DEN (tandang) | CHI (kandang) | Gabungan |
|---|---|---|---|
| Pemain rotasi yang main | 10 | 12 | 22 |
| Pemain OUT dikeluarkan | 3 (Hopkins, Whitmore, Holmes II) | 4 (Wilson, Powell, Claxton, Sellers) | 7 |
| Pemain di luar rotasi | 3 | 1 | 4 |
| Percobaan 3P diharapkan | 32,10 | 35,20 | **67,30** |
| Poin 3P normal | 34,28 | 33,81 | 68,09 |
| Poin 3P setan (@54,1%) | 52,10 | 57,13 | 109,23 |
| Selisih setan vs normal | +17,82 | +23,32 | +41,14 |

Total setan = 233,0 − 68,09 + 109,23 = **274,14**. Geser +41,14.
Deviasi vs garis bandar 236,5 = **+37,64**.

Top 5 kontributor (selisih poin setan vs normal): DEN — Aaron
Gordon +3,10; Nikola Jokić +3,01; Cameron Johnson +2,89; Christian
Braun +2,79; Jamal Murray +1,47. CHI — Matas Buzelis +3,17; Leonard
Miller +2,66; Jordan Hawkins +2,56; Isaac Okoro +2,55; Josh Giddey
+2,55.

Catatan penting: dua penembak terbesar CHI sedang OUT (Caleb Wilson
7,1 percobaan/laga + Norman Powell 6,8) — 13,9 percobaan dikeluarkan
dengan benar. Ironisnya banjir aktual justru datang dari pemain
peran (Buzelis, Hield, Jalen Smith) — persis yang ditangkap demon
ini: pemain peran yang menembak sebaik penembak terbaik liga.

### 4.2 Kedua kaki ter-flag rapuh — dan point-in-time

| Kaki | Garis | flag_setan_pemain (total 274,14 > garis) | p_setan_pemain | flag_setan (P-based) |
|---|---|---|---|---|
| Asuransi U252,5 @82¢ | 252,5 | **True** | 0,1298 | True |
| Utama U250,5 @79¢ | 250,5 | **True** | 0,1184 | True |

Perbandingan dengan setan UMUM (geser 18,07): P setan umum 0,5315 /
0,4915 — kedua kaki juga ter-flag, tapi demon pemain berkata jauh
lebih keras (P ~12–13% vs ~49–53%). Garis tahan-setan pemain: TIDAK
ADA di tangga (garis tertinggi tangga pun P(Under)-nya < target di
geser +41,14) — bandingkan dengan garis tahan-setan umum 264,5 @94¢
(Asuransi) / 258,5 (Utama).

**Point-in-time**: demon dari data BBRef (s.d. 21 Nov, sebelum laga)
= **273,03** (geser +40,03; deviasi +36,53) — hanya **−1,11** dari
274,14. Kontaminasi look-ahead (data stats.nba.com mencakup laga itu
sendiri) kecil dan TIDAK mengubah vonis apa pun: kedua kaki tetap
rapuh dengan margin +20,5 poin ke garis terendah.

### 4.3 Kenapa jauh dari perkiraan kasar koordinator (~258)?

Perkiraan koordinator memakai % terbaik liga ~45%. Fakta dari data:
% terbaik liga (ambang 50 percobaan) adalah **54,1%** (Cam Spencer,
MEM, 61,2 percobaan). Selisih 9,1 poin persentase × 67,30 percobaan
× 3 poin ≈ **+18,4 poin** pada total setan — hampir seluruh selisih
274,14 vs ~258. Dua efek kecil lain: percobaan yang diharapkan 67,30
(di bawah perkiraan 71,6 karena pengeluaran OUT — efek −2,5 poin)
dan % normal gabungan ~33,7% (sedikit di bawah asumsi implisit).
Jadi perkiraan koordinator bukan salah arah — hanya asumsi % terbaik
liganya yang terlalu rendah. Pada % 47,2% (ambang 75), total setan
adalah 260,21 — dekat dengan perkiraan ~258. Tidak ada angka yang
dipaksa cocok; selisihnya dijelaskan oleh data.

## 5. Perbandingan setan pemain vs setan umum (slate 22 Nov)

| Laga | Median | Garis bandar | Setan umum | Setan pemain | Selisih | Deviasi pemain vs bandar |
|---|---|---|---|---|---|---|
| DEN@CHI | 233,0 | 236,5 | 251,07 | **274,14** | +23,07 | +37,64 |
| OKC@MIA | 220,0 | 231,5 | 238,07 | **259,36** | +21,29 | +27,86 |
| BOS@GSW | 203,0 | 210,5 | 221,07 | **244,69** | +23,62 | +34,19 |

Pola konsisten di ketiga laga: setan pemain berjalan **+21 s.d.
+24 poin** di atas setan umum. Penyebabnya struktural: % terbaik
liga 54,1% jauh di atas % tim (~34–36%), dan ~67–75 percobaan yang
diharapkan mengalikan selisih itu. Pada ambang 75 (47,2%), selisih
ini menyusut menjadi ~+9–10 poin. Implikasi: demon pemain adalah
detektor kerapuhan yang JAUH lebih keras daripada demon umum — dan
kerasnya itu sebagian besar ditentukan satu angka (54,1% Cam
Spencer, 61 percobaan). Lihat sensitivitas §6.

## 6. Sensitivitas ambang % terbaik liga (DEN@CHI)

| Ambang total 3PA | % terbaik | Pemain | Total setan | Kaki U252,5/U250,5 rapuh? |
|---|---|---|---|---|
| 25 | 62,1% | Moritz Wagner (BKN, 28,5 perc.) | 290,29 | Ya |
| **50 (INITIAL, dipakai)** | **54,1%** | **Cam Spencer (MEM, 61,2 perc.)** | **274,14** | **Ya** |
| 75 | 47,2% | Jamal Murray (DEN, 106,5 perc.) | 260,21 | Ya |
| 100 | 47,2% | Jamal Murray (DEN, 106,5 perc.) | 260,21 | Ya |
| 150 | 37,6% | Luka Dončić (LAL, 196,5 perc.) | 240,83 | **Tidak** |

Vonis "rapuh" kokoh untuk ambang 25–100; pada ambang 150 (hanya 4
pemain lolos) % terbaik jatuh ke 37,6% — nyaris rata-rata liga —
dan demon kehilangan fungsinya sebagai uji stress. Ambang 50 dipilih
sebagai INITIAL karena memberi sampel yang berarti (~3 percobaan/
laga selama musim berjalan) dengan kumpulan kandidat yang luas (174
pemain). Rencana kalibrasi tercatat di komentar config: tinjau tiap
~20 laga liga; pertimbangkan ambang yang tumbuh mengikuti musim
(mis. ~3,5 percobaan × jumlah laga tim); ajukan perubahan ke user
seperti D12 bila ambang mengubah vonis kerapuhan di slate uji.

## 7. Perubahan kode

| File | Perubahan |
|---|---|
| `ingest/pemain_3p.py` | BARU — fetch + parse stats.nba.com (utama) & BBRef per-game (fallback), skema pemain 3P yang sama; cache + rate limit seperti modul ingest lain. |
| `engine/setan_pemain.py` | BARU — `pct_terbaik_liga`, `pemain_absen_dari_artefak`, `hitung_setan_pemain` (rumus §3 + rincian per tim + top 5 kontributor). |
| `engine/stress.py` | WIRING — `skenario_panas` menerima `setan_pemain=` (atau `analysis["setan_pemain"]`); bila data tersedia + enabled, skenario setan memakai geser pemain + field per kaki `total_setan_pemain`, `deviasi_setan_pemain_dari_garis_bandar`, `p_setan_pemain`, `flag_setan_pemain`; bila tidak, fallback setan umum + catatan. Banjir 3P/FT TIDAK disentuh. |
| `config/playstyle.yaml` | Section BARU `setan_pemain:` di AKHIR file (enabled, pct_terbaik_min_total_3pa 50 INITIAL, ambang_menit_rotasi 10.0 INITIAL, komentar + rencana kalibrasi). `version` tetap 16; section lain TIDAK disentuh. |
| `scripts/verifikasi_setan_pemain.py` | BARU — verifikasi live DEN@CHI + cross-check BBRef + point-in-time + sensitivitas ambang + perbandingan slate. Output `out/verifikasi_setan_pemain.json` (gitignored). |
| `tests/test_setan_pemain.py` | BARU — 34 tes (lihat §8). |

File yang TIDAK disentuh sesuai tugas: `report/nba_report.py`
(worker lain yang merender field baru), `engine/nba_sim.py`,
`DECISIONS.md`, dan file worker lain.

## 8. Tes

- **Baru:** `tests/test_setan_pemain.py` — **34 tes**: parse
  stats.nba.com (4: skema, baris tanpa nama/tim dilewati, kolom
  wajib hilang, resultSet hilang); parse BBRef (4: kolom `_per_g` +
  slug + pemetaan tricode BRK→BKN, tabel hilang, tabel dalam
  komentar, kolom wajib hilang); % terbaik liga (4: ambang menyaring
  sampel kecil, seri → total percobaan lebih besar, tidak ada
  kandidat, ambang negatif); pemain absen (3: bentuk entries, bentuk
  daftar slate, tanpa blok cedera); rumus (8: hitung tangan lengkap
  245,3, OUT tidak dihitung, tanpa info cedera dicatat, garis None,
  pemain tanpa data dilewati + dicatat, daftar kosong, tidak ada
  kandidat %, config hilang); wiring stress (9: dipakai, fallback
  tanpa data, fallback data rusak dicatat, data dari analysis dict,
  argumen menang atas analysis, dinonaktifkan di config, section
  hilang kompatibel, enabled hilang → ConfigError, garis bandar
  tidak ada → deviasi None); DEN@CHI end-to-end (2: total + rincian
  dari fixture nilai asli, kedua kaki nyata di-flag rapuh pada CDF
  artefak — dilewati bila artefak tidak ada).
- **Targeted:** `test_setan_pemain` + `test_stress` + `test_config`
  + `test_ticket_audit` + `test_ticket_composer` = **270 tes, OK**
  pada keadaan HANYA perubahan worker ini (lihat §9 soal keadaan
  working tree gabungan).
- **Baseline sebelum pekerjaan:** full suite 1.698 tes, OK.
- **Lint:** ruff + black bersih pada semua file yang dibuat/diubah
  worker ini (termasuk script verifikasi).

## 9. Catatan penting untuk koordinator: working tree gabungan

Working tree dipakai BERSAMA worker lain yang sedang bekerja
paralel (vonis, equilibrium, tanpa-kaki-kembar, report). Dua hal
yang harus koordinator tahu:

1. **Kegagalan tes di tree gabungan BUKAN dari pekerjaan ini.**
   Pada tree gabungan saat ini, `test_ticket_audit` +
   `test_ticket_composer` gagal (29 failures + 7 errors) karena
   perubahan worker lain yang sedang berjalan
   (`engine/ticket_composer.py` aturan tanpa-kaki-kembar +
   `engine/equilibrium.py`). Bukti isolasi: dengan HANYA perubahan
   worker ini (file worker lain di-stash sementara), 270 tes
   targeted LULUS SEMUA (§8). Baseline murni HEAD juga hijau
   (155 tes audit+composer OK).
2. **Stash `stash@{0}` JANGAN dihapus sembarangan.** Saat menguji
   isolasi di atas, worker ini me-stash file worker lain; saat
   mengembalikan, `git stash pop` gagal karena worker lain
   mengubah `engine/ticket_composer.py` di tengah jalan. Keadaan
   akhir yang SUDAH dipulihkan: `engine/equilibrium.py` dikembalikan
   dari stash (identik dengan versi stash — terverifikasi),
   `engine/vonis.py` dikembalikan ke tempatnya (sempat tertinggal
   di /tmp karena rantai `&&` putus saat stash pop gagal — SUDAH
   diperbaiki, 31.965 byte), `config/playstyle.yaml` dikembalikan
   dari backup (section `vonis:` + `setan_pemain:` utuh, version
   16). Yang TERSISA di `stash@{0}`: versi LAMA
   `engine/ticket_composer.py` worker vonis (diff 351 baris,
   termasuk `_alokasikan_laga`) yang BERBEDA dari versi di disk
   sekarang (diff 33 baris, integrasi vonis di
   `_kumpulkan_kandidat`). Koordinator harus memutuskan bersama
   worker vonis: apakah versi stash itu pekerjaan yang hilang dan
   harus dikembalikan, atau versi disk adalah pengerjaan ulang yang
   disengaja. Worker ini TIDAK menyentuh isi stash itu lagi.

## 10. Keputusan desain yang menunggu keberatan

1. **Ambang % terbaik liga 50 total percobaan (INITIAL)** — lihat
   sensitivitas §6. Nilai ini yang paling menentukan level demon.
2. **Ambang menit rotasi 10,0 (INITIAL)** — batas kasar rotasi vs
   bangku dalam; belum diukur sensitivitasnya (rencana: ukur pada
   ambang 5/8/10/12 menit di slate uji).
3. **Basis kekuatan penuh tanpa penskalaan rasio laga** (§3.1) —
   mengikuti rumus user secara harfiah; alternatifnya (kalikan
   fg3a dengan games_played/team_games) ditolak karena meremehkan
   pemain yang baru sembuh + bertentangan dengan "percobaan 3 poin
   per laganya".
4. **Section `setan_pemain` opsional di `skenario_panas`**
   (hilang → enabled default True + fallback bila tanpa data;
   nilai yang ADA tapi tidak valid → ConfigError) — mengikuti
   preseden `ekor_3p`, demi kompatibilitas fixture lama.
   Sebaliknya, `hitung_setan_pemain` MEWAJIBKAN ambang via
   get_value (ConfigError bila hilang) — komputasi tidak boleh
   jalan tanpa angka yang diputuskan.
5. **Geser setan pemain negatif TIDAK dijepit ke 0** — kasus
   patologis (tim sudah menembak di atas % terbaik yang memenuhi
   ambang) dipakai apa adanya + dicatat, bukan disembunyikan.
6. **Top kontributor diurutkan selisih poin** (setan − normal),
   bukan poin setan mentah — yang mendorong demon adalah pemain
   yang % normalnya RENDAH tapi percobaannya banyak (mis. Aaron
   Gordon +3,10 di atas Jamal Murray +1,47 meski Murray menembak
   7,1 percobaan/laga).
7. **Field tambahan `flag_setan_pemain`** di luar 3 field yang
   diminta tugas (total, deviasi, p) — karena pertanyaan verifikasi
   ("total setan > garis?") adalah perbandingan langsung, bukan
   berbasis P; field ini yang dibaca worker report untuk flag
   rapuh.

## 11. Batasan jujur

- **Demon tidak memodelkan lonjakan JUMLAH percobaan.** Banjir
  DEN@CHI adalah lonjakan percobaan (90 vs 67,3 yang diharapkan)
  + lonjakan akurasi (46,7% vs ~33,7%). Setan per pemain hanya
  menaikkan AKURASI ke 54,1% pada percobaan yang diharapkan — total
  274,14 tetap 21,86 di bawah aktual 296. Itu sesuai desain (uji
  stress akurasi), tapi jangan dibaca sebagai "batas atas total".
- **% terbaik liga adalah satu observasi yang berisik.** Cam
  Spencer 54,1% dari 61 percobaan (SE ≈ 6,4 poin persentase) —
  kemungkinan besar sebagian keberuntungan awal musim. Demon
  memakai angka observasi apa adanya (sesuai perintah user:
  "fakta dari data"), tanpa shrinkage. Bila Spencer mendingin,
  demon ikut turun — itu fitur (mengikuti data), bukan bug.
- **P setan pemain di geser besar memakai CDF yang jarang.**
  Pada geser +41,14, x = garis − geser jatuh di daerah CDF
  tersimpan yang jarang (artefak DEN@CHI melompat dari 135,5
  langsung ke 210,5) — P 0,1184 untuk U250,5 adalah interpolasi
  linear sepanjang 75 poin dan KASAR. Flag (total > garis) adalah
  sinyal yang kokoh; P adalah indikasi. (Keterbatasan yang sama
  berlaku untuk semua skenario stress di repo ini, hanya lebih
  terasa di geser besar.)
- **Pencocokan nama pemain persis.** Varian nama antar sumber
  (sufiks II/Jr., aksen) bisa lolos dari filter absen; nama yang
  tidak cocok dicatat. Artefak cedera memakai nama laporan cedera
  resmi NBA (cocok dengan stats.nba.com); risiko terbesar bila
  sumbernya BBRef (fallback). Normalisasi nama adalah pekerjaan
  lanjutan, bukan bagian build ini.
- **Status QUESTIONABLE/PROBABLE dihitung main.** Hanya status OUT
  (dan padanannya: Inactive, DNP) yang dikeluarkan. Pemain yang
  akhirnya DNP padahal PROBABLE ikut terhitung penuh — demon
  sedikit overstated ke arah menandai kerapuhan (arah yang aman
  untuk uji stress).
- **Data point-in-time tidak sempurna.** Verifikasi utama memakai
  data stats.nba.com yang mencakup laga itu sendiri; perkiraan
  point-in-time memakai BBRef yang tertinggal satu laga (bukan
  rekonstruksi box-score per pemain). Selisihnya kecil (−1,11)
  dan vonis tidak berubah, tapi angka 274,14 secara teknis
  mengandung ~1 poin look-ahead.
- **Setan pemain tidak terhubung ke pipeline analisis.** Build ini
  menyediakan ingest + engine + wiring `skenario_panas`; pemanggilan
  fetch + hitung dari pipeline (mis. `nba_analysis` / CLI) adalah
  urusan koordinator/integrasi — `skenario_panas` tanpa data pemain
  tetap memakai setan umum seperti sebelumnya (tidak ada perilaku
  yang berubah diam-diam).

## 12. Ringkasan hasil

- **Hasil:** setan per pemain selesai + terverifikasi live — DEN@CHI
  274,14 (deviasi +37,64 vs garis bandar), kedua kaki nyata
  ter-flag rapuh; point-in-time 273,03 (−1,11); slate 3 laga:
  pemain +21 s.d. +24 di atas setan umum; vonis rapuh kokoh untuk
  ambang % terbaik 25–100.
- **File yang diubah/dibuat:** `ingest/pemain_3p.py` (BARU),
  `engine/setan_pemain.py` (BARU), `engine/stress.py` (wiring),
  `config/playstyle.yaml` (section `setan_pemain:` baru, version
  tetap 16), `scripts/verifikasi_setan_pemain.py` (BARU),
  `tests/test_setan_pemain.py` (BARU), `LAPORAN-SETAN-PEMAIN.md`
  (laporan ini). TIDAK ADA commit (koordinator yang commit).
- **Tes baru:** 34 tes, semua lulus; targeted 270 tes OK (isolasi);
  baseline full suite 1.698 tes OK sebelum pekerjaan.
- **Status ruff/black:** bersih pada semua file yang dibuat/diubah
  worker ini.
- **Kredit Odds API:** 0. Sumber: stats.nba.com + BBRef (gratis).
