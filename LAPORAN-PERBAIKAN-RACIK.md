# Laporan Perbaikan Racik — Mesin Analis (bukan aturan kaku)

**Tanggal:** 23 November 2026 (04:31–05:45 WIB)
**Commit:** `5b24c73` (main, 23 November 2026)
**Config:** playstyle.yaml v13
**Kredit Odds API dipakai:** 0

## 1. Kenapa perbaikan ini ada

Tanggal 23 November 2026 pukul 04:05 WIB, user menemukan 3 cacat di cara
mesin meracik tiket (dari laporan DET@ATL dan slate 7 laga 22 November):

1. **Garis terbalik** — Asuransi 233,5 ternyata LEBIH RENDAH dari Utama
   237,5. Kalau garis itu kalah, kedua tiket mati bersamaan. Asuransi
   tidak lebih aman dari Utama.
2. **Tidak ada naik tangga** — bila garis Asuransi ditolak karena harga
   market di bawah lantai, mesin langsung menyerah ("cari garis Asuransi
   lain") alih-alih mencoba garis yang lebih tinggi di tangga yang sama.
3. **Tidak ada peringatan Utama tak terlindungi** — Utama terracik tanpa
   Asuransi, tapi ringkasan hanya bilang "Asuransi tidak diracik" tanpa
   peringatan.

Lalu user merumuskan ulang filosofinya (04:15 + 04:25 + 04:31 WIB), dan
filosofi itu yang berlaku — menggantikan proposal perbaikan 3 poin yang
sempit:

- Mulai dari **garis bandar**: kenapa bandar pilih garis itu; mesin cek
  pakai statistik apakah harga itu **wajar atau di bawah wajar**.
- **Bantalan tidak kaku**: +8 cuma istilah user. Mesin menghitung
  bantalan per laga dari statistik laga. Utama boleh ke 82¢ bila laga
  butuh lebih aman. Yang kaku: Utama harus tembus x3+.
- **Ekonomi dua tiket**: modal $10+$10=$20. Asuransi x2,0 = impas,
  x2,5 = untung $5 walau Utama hangus. Dua tiket harus beneran beda:
  satu agresif (Utama x3+, sampai x5 bila mesin beneran yakin), satu
  konservatif (Asuransi lebih tebal, >x2,5).
- Bantalan lahir dari **cerita laga** (dua tim penyerang terbaik,
  sama-sama 240+ di 5 laga terakhir → +12 lebih aman walau 82¢), dan
  mesin **menjelaskan alasannya dengan kata-kata biasa**.
- Yang terpenting adalah **mesin statistiknya** — bukan banyaknya aturan.

Perbaikan ini membangun lapisan analis DI ATAS engine yang sudah ada
(sim NBA/bola + ingest). Engine tidak di-rebuild.

## 2. Apa yang berubah

### 2.1 Penilaian "wajar" (baru) — `engine/analis.py`

Setiap laga, artefak analisis kini mencatat `analisis_wajar`:

- garis market (garis bandar), acuan sim (median 100.000x simulasi),
- garis + harga kaki Utama, jarak (garis harga − acuan),
- bantalan yang dibutuhkan (dari bantalan adaptif),
- penilaian: **wajar** bila jarak ≥ bantalan yang dibutuhkan,
  **di_bawah_wajar** bila tidak, **tidak_terverifikasi** bila data
  kurang — plus penjelasan kata-kata biasa.

Contoh penjelasan yang ditulis mesin (DET@ATL):

> "Acuan analisis 219 poin (garis bandar 225,5); harga 76¢ duduk di
> garis 237,5 — jaraknya 18,5 poin dari acuan, sementara statistik
> meminta bantalan 9,36 poin; jadi harga ini wajar — garisnya memberi
> bantalan yang diminta statistik."

Laporan kini punya bagian baru **"Garis bandar — wajar atau tidak?"**
tepat setelah Ringkasan.

### 2.2 Bantalan adaptif — menggantikan +8/+12 kaku

`engine/analis.py::bantalan_adaptif` menghitung bantalan per laga:

```
bantalan = clamp(std_sim × 0,42 + (ortg_rata − ortg_liga) × 0,5
                 + (total_5laga − total_musim) × 0,25, min 4, maks 20)
```

- **std_sim** = simpangan baku total dari simulasi 100.000x (sebaran
  skor laga itu sendiri).
- **ortg** = kekuatan serang kedua tim vs rata-rata liga.
- **form skor** = rata-rata total 5 laga terakhir vs rata-rata musim.

Angka 0,42 dipilih supaya laga biasa (std ~19, sesuai sigma_total fit
18,99) memberi ~8 poin = acuan user; 8 poin ≈ 0,42σ → P(Under) ≈ 0,66,
sejalan dengan target Utama 65%. **Bobot-bobot ini NILAI AWAL yang
belum dikalibrasi** — menunggu uji data (lihat §6).

Bantalan boleh di bawah +8 bila statistik membenarkan (dengan alasan
tercatat), dan wajib di atas +8 bila laga menuntut. Contoh live:
OKC@MIA 11,14 (di atas 8), DEN@CHI 7,14 dan BOS@GSW 6,02 (di bawah 8).
Alasan tiap bantalan dicatat kata-kata biasa dan tampil di laporan.

Yang dihapus: bantalan +8/+12 kaku, lantai market+8, bantalan spread
(spread tidak lagi memengaruhi bantalan maupun anomali — kunci-kunci
config lama yang mati sudah dibersihkan).

### 2.3 Pemilihan kaki dari harga — Utama dulu, lalu Asuransi

Urutan baru di `engine/nba_analysis.py` (Tahap 4): hitung bantalan
adaptif → pilih garis **Utama** dulu → pilih garis **Asuransi** =
garis terkecil yang memenuhi syarat DAN **strictly di atas garis
Utama** (`garis_di_atas`). Garis terbalik kini tidak mungkin terjadi
dari seleksi.

- Kaki Utama: harga estimasi jup.ag **≥ 75¢** (boleh naik ke 81–82¢
  bila laga butuh lebih aman — OKC@MIA live: Utama 244,5 @ 82¢).
- Kaki Asuransi: harga **≥ 75¢** juga, garis lebih tinggi dari Utama.
- Target peluang model tetap: Asuransi 74%, Utama 65%.
- Peracik menegakkan lantai harga sebagai pertahanan lapis kedua
  (kaki di bawah 75¢ dicoret, alasan tercatat).

### 2.4 Naik tangga + volume

Bila garis awal ditolak (harga di bawah 75¢, peluang model di bawah
target, atau volume tipis), mesin **naik anak tangga berikutnya**
sampai lolos — bukan menyerah. Setiap kenaikan dicatat di field
`climb` (`from_line`, `to_line`, `rungs`, `reason`) dan dijelaskan
di laporan ("dari 235,5 ke 237,5 karena harga di bawah minimum").

**Volume tipis (volume < min_volume_usd $100) = penghalang KERAS
untuk Asuransi** — garis yang tidak bisa dibeli bukan asuransi.
Untuk Utama, garis tipis boleh masuk tapi ditandai flag VOLUME_TIPIS
+ peringatan di warnings[] + ringkasan.

Perbaikan teknis yang mendasarinya: `_parse_tangga` kini meneruskan
`volume_usd` + `thin` ke cushion (sebelumnya dibuang — itu sebabnya
Utama diam-diam memakai garis tipis 237,5 vol $6,3 di DET@ATL).
Volume yang tidak tercatat di tangga dianggap tipis (fail-closed).

### 2.5 Peringatan Utama tak terlindungi

Bila Tiket Utama terracik tanpa Tiket Asuransi, warnings[] + ringkasan
kini WAJIB memuat:

> "Tiket Utama tidak terlindungi — Tiket Asuransi tidak terbentuk
> ({alasan Asuransi}). Kalau Tiket Utama kalah, tidak ada uang yang
> kembali dari Asuransi."

Kasus 22 November (tickets JSON dengan warnings kosong) direproduksi
sebagai tes dan kini memicu peringatan ini. Laporan juga menampilkan
peringatan tingkat laga bila Utama meets tapi Asuransi tidak.

### 2.6 Target pengali

- **Asuransi: 2,5–3,0** (naik dari 2,20–2,50). Batas atas 3,0 adalah
  **USULAN** (menunggu keberatan): 2,5–3,0 tidak tumpang tindih dengan
  Utama 3,0–5,0 sehingga kedua tiket selalu beda peran.
- **Utama: 3,0–5,0** (tetap), target lunak ≤ 4,0 (tetap).

### 2.7 Kriteria "yakin" untuk x5 — dan perbaikan preferensi

x5 di Utama hanya bila mesin **beneran yakin**. Kriteria "yakin"
(USULAN, menunggu keberatan): SEMUA kaki p_final ≥ 0,75
(`tickets.main.yakin_min_leg_prob`, kini di config) DAN semua kaki
putusan recheck TETAP_OK (tanpa recheck = tidak yakin) DAN tidak ada
anomali di laga kaki-kakinya. Di mode agresif (perintah eksplisit user
per malam), kriteria ini tidak berlaku.

**Temuan struktural + perbaikan koordinator (integrasi Tahap 4):**
pekerja B menemukan bahwa dengan lantai 75¢, subset di atas 4,0
selalu punya sub-subset yang masuk target lunak (buang kaki
termurah) — jadi preferensi lama (lunak selalu menang) membuat gate
yakin TIDAK PERNAH mengubah hasil dan x5 tidak pernah terjadi.
Koordinator mengubah preferensi di `_pilih_subset`: **subset yakin
di atas target lunak kini DIUTAMAKAN atas subset lunak** (di kelas
yakin, peluang menang didahulukan, lalu pengali lebih besar).
Perilaku mode agresif tidak diubah (lunak tetap diutamakan di sana).
Perubahan ini adalah keputusan koordinator integrasi — menunggu
keberatan user/reviewer. Dua tes menguncinya: 6 laga @75/80 semua
yakin → Utama 4,98x (6 kaki); satu kaki tidak yakin → Utama 3,73x
(5 kaki, lunak).

### 2.8 Yang TIDAK berubah

- **Aturan condong-ke-market TETAP berlaku** (keputusan user) —
  penilaian "wajar" adalah lapisan tambahan, bukan pengganti.
  Recheck + peracik tetap memakai probabilitas market untuk Asuransi
  bila selisih median vs garis market > 5,0 tanpa alasan konkret.
- **min_leg_prob TIDAK diubah** (0,74 Asuransi / 0,65 Utama) — masih
  menunggu keputusan user (gate keras vs preferensi lunak).
- Pesan recheck lama "cari garis Asuransi lain — ..." diganti:
  "jangan pasang kaki Asuransi garis 233.5 — mesin sudah menaikkan
  garis ke anak tangga yang lebih aman, tapi harga marketnya tetap di
  bawah ambang Asuransi (74%)".

## 3. Contoh sebelum/sesudah — DET@ATL 2026-11-22

Dihitung offline dari artefak + tangga tersimpan
(`scripts/bandingkan_racik.py`, 0 kredit; output:
`out/perbandingan_racik_det_atl_tahap4.txt`).

| | SEBELUM (aturan lama) | SESUDAH (Tahap 4) |
|---|---|---|
| Bantalan | +8/+12 kaku (spread) | **+9,36 adaptif** (std 19,46; ORtg 113,1/114,8 vs liga 113,3; form 231 vs musim 227,5) |
| **Utama** | 237,5 @ 75,5¢ (jup 76¢), p 83,0%, vol **$6 TIPIS** | **237,5 @ 75,5¢ (jup 76¢), p 83,0%, vol $6 TIPIS** — garis sama, tapi kini naik tangga 235,5→237,5 karena harga minimum (dan tipisnya kini TERLIHAT sebagai peringatan, bukan diam-diam) |
| **Asuransi** | 233,5 @ 68¢ (jup 68,5¢), p 77,2%, vol $270 — **di bawah Utama** | **249,5 @ 92,5¢ (jup 93¢), p 93,9%, vol $141** — naik 5 anak tangga dari 239,5 karena volume tipis (penghalang keras) — **di atas Utama** |
| Penilaian wajar | — (tidak ada) | **WAJAR** — acuan 219, garis harga 237,5, jarak 18,5 ≥ bantalan 9,36 |

Perubahan terbesar: Asuransi melonjak 233,5 → 249,5 karena semua
garis 239,5–247,5 tipis dan dilewati. Ini konsekuensi langsung dari
"volume tipis = penghalang keras Asuransi".

**Catatan koreksi atas premis tugas:** saat tugas ditulis, tangga
DET@ATL yang dibaca main agent menunjukkan tidak ada garis yang lolos
harga ≥74¢ DAN volume ≥$100. Pemeriksaan penuh tangga ternyata
menunjukkan 249,5 Under bervolume **$141 (tidak tipis)**, jup 93¢ —
jadi Asuransi BISA terbentuk dengan naik tangga. Premis "tidak ada
garis yang lolos" salah; mesin baru membuktikannya dengan naik tangga.

**Tegangan desain (terbuka, menunggu keberatan):** kaki Asuransi 93¢
hanya menyumbang ~1,075x ke pengali — membuat target x2,5 Asuransi
sangat berat. Naik tangga saat ini TIDAK punya batas harga atas.
Apakah pendakian perlu batas harga (mis. berhenti bila harga terlalu
tinggi sehingga pengali tidak tercapai) adalah pertanyaan desain yang
belum diputuskan — koordinator tidak memutuskan sendiri.

## 4. Verifikasi live — slate nyata 22 November 2026

Slate 3 laga yang belum mulai saat dijalankan (~05:25 WIB 23 Nov):
OKC@MIA, DEN@CHI (19:00 ET), BOS@GSW (20:30 ET). DET@ATL dikecualikan
karena sedang LIVE. Perintah: `analyze --tanpa-odds-api` (~6,7 menit,
exit 0), lalu `recheck` + `racik` + `laporan`. **0 kredit Odds API.**
Artefak: `out/analysis_verif_tahap4_2026-11-22.json`,
`out/recheck_verif_tahap4_OKC@MIA_2026-11-22.json`,
`out/tickets_verif_tahap4_2026-11-22.json`.

| Laga | Status | Bantalan | Utama | Asuransi | Wajar |
|---|---|---|---|---|---|
| OKC@MIA | OK | 11,14 | 244,5 @ 82¢ (jup 82,5), p 89,4%, vol $21 TIPIS | 250,5 @ 89¢ (jup 89,5), p 93,9%, vol $227, naik 246,5→250,5 (volume tipis) | WAJAR (24,5 vs 11,14) |
| DEN@CHI | HOLD | 7,14 | 250,5 @ 78¢ (jup 78,5), p 81,8%, vol $6 TIPIS, naik 244,5→250,5 (harga minimum) | **gagal**: `tidak_ada_garis_lolos: volume_tipis` | WAJAR (17,5 vs 7,14) |
| BOS@GSW | HOLD | 6,02 | 223,5 @ 77¢ (jup 77,5), p 86,1%, vol tidak tercatat TIPIS, naik 217,5→223,5 (harga minimum) | **gagal**: `tidak_ada_garis_lolos: volume_tipis` | WAJAR (20,5 vs 6,02) |

- Bantalan adaptif bervariasi per laga (11,14 / 7,14 / 6,02 — dua di
  bawah 8, satu di atas), sesuai filosofi "bukan +8 kaku".
- Asuransi gagal di 2/3 laga karena penghalang volume tipis —
  fail-closed bekerja jujur, bukan dipaksakan.
- **Recheck** OKC@MIA: **GO** (Asuransi PERHATIAN condong_ke_market,
  Utama TETAP_OK). Recheck kini memakai modul cushion + analis ASLI
  (bukan stub) — diverifikasi end-to-end.
- **Racik**: tidak ada tiket (hanya 1 laga OK → pengali Utama maks
  x1,15 < x3; laga HOLD dikecualikan) — exit 1, perilaku benar.
  Alasan tercatat jujur: Asuransi maks x1,06, Utama maks x1,15.
- **Laporan** kedua laga dirender benar, termasuk peringatan
  Utama-tanpa-Asuransi tingkat laga di DEN@CHI.

## 5. Verifikasi

- **Suite penuh: 1.395 tes, semua OK** (dari 1.308 di Tahap 3).
  Modul baru: `test_analis.py`; modul ditulis ulang: `test_cushion.py`;
  wiring Tahap 4: 10 tes baru di `test_nba_analysis.py`, 7 baru di
  `test_report_nba.py`; peracik: 79 tes; recheck: 79 tes.
- **ruff check + black bersih** (yang dijalankan hook pre-commit).
  `ruff format --check` menandai 25 file repo-wide (termasuk 5 file
  tugas ini) — perbedaan black-vs-ruff-format yang sudah ada di
  banyak file lama (cli.py, nba_sim.py, qa.py, dsb.); repo standard
  adalah black dan hook tidak menjalankan `ruff format`, jadi ini
  bukan blocker.
- **Angka kunci dihitung ulang dengan tangan oleh koordinator:**
  bantalan DET@ATL 9,36 (19,46×0,42 + 0,65×0,5 + 3,5×0,25 = 9,37 ≈
  9,36 pembulatan); Utama 237,5 dari maks(219; 225,5)+9,36 = 234,86
  → garis 235,5 lalu naik karena harga 72¢ < 75¢; Asuransi 249,5
  dari 239,5 naik 5 anak tangga (239,5–247,5 semua tipis, 249,5 vol
  $141); pengali yakin 4,9778 ((100/75)⁵ × (100/80) × 0,945).
- **Verifikasi independen dari disk:** koordinator menjalankan ulang
  `scripts/bandingkan_racik.py` (output cocok dengan laporan pekerja),
  membaca artefak live (`analysis_verif`, `tickets_verif`,
  `recheck_verif`) dan mengonfirmasi semua angka §4, menjalankan
  ulang tes modul tiap pekerja (A: 147/147, B: 158/158, C: 76/76),
  dan memeriksa skema (field baru opsional — artefak lama tetap
  valid).
- **0 kredit Odds API** dipakai di seluruh pekerjaan ini.

## 6. Keterbatasan jujur

1. **Bobot bantalan adaptif belum dikalibrasi.** 0,42 / 0,5 / 0,25
   adalah nilai awal yang dipilih supaya laga biasa memberi ~8 poin.
   Apakah bobot ini benar-benar memprediksi sebaran skor lebih baik
   dari +8 kaku — BELUM DIUJI. Uji historis (DunkAPI, masih menunggu
   persetujuan signup) yang bisa menjawab.
2. **Naik tangga tanpa batas harga.** Kaki Asuransi bisa naik sampai
   93¢ (hanya ~1,075x). Target x2,5 Asuransi menjadi sangat berat
   bila banyak kaki naik tinggi. Apakah perlu batas harga — belum
   diputuskan (lihat §3).
3. **Asuransi sering gagal di live.** 2/3 laga verifikasi gagal
   karena volume tipis. Penghalang volume + lantai p74 + harga 75¢
   bersama-sama sangat ketat. Apakah ini yang diinginkan, atau perlu
   pelonggaran, adalah keputusan user.
4. **Volume tangga Polymarket tipis di garis jauh.** Garis 239,5–247,5
   DET@ATL bervolume $5–$93. Mesin hanya membaca volume tercatat;
   apakah volume itu cukup untuk membeli $10 tanpa menggerakkan harga
   — belum diuji.
5. **ORtg musim penuh dipakai untuk bantalan** (pilihan wiring:
   musim lebih stabil dari last10). Bila analis minta last10, ini
   bisa diubah — keputusan terbuka.
6. **Lantai harga tidak berlaku untuk kaki bola** (moneyline bola
   bukan proksi bantalan; menerapkannya akan membunuh seluruh jalur
   Utama bola tanpa keputusan user). Pengecualian ini menunggu
   keberatan.
7. **Peringatan racik tampil dua kali** (ringkasan + loop PERINGATAN)
   — perilaku lama dari Langkah 3, bukan dari perbaikan ini; bila
   ingin dirapikan, itu tugas terpisah.
8. **P_model garis di luar jangkauan persentil** memakai interpolasi
   persentil (p50/p74/p75/p95) dengan `p_source` tercatat; garis di
   atas p75 memakai batas bawah 0,75 — cukup untuk lolos uji peluang,
   tapi bukan estimasi titik.
9. **Tidak ada modul berita** (hutang lama): berita non-cedera
   (mis. pelatih, motivasi) tetap tidak terdeteksi.

## 7. Keputusan desain yang menunggu keberatan user/reviewer

1. **Batas atas Asuransi 3,0** (USULAN — alasan: tidak tumpang
   tindih dengan Utama).
2. **Kriteria "yakin"** (p_final ≥ 0,75 + TETAP_OK + tanpa anomali)
   dan **pengecualian mode agresif** (USULAN).
3. **Preferensi yakin di atas lunak** (keputusan koordinator
   integrasi — tanpa ini x5 tidak pernah terjadi).
4. **Pertanyaan batas harga pendakian** (§3, §6.2) — belum diputuskan.
5. **Pengecualian lantai harga untuk kaki bola** (§6.6).
6. **ORtg musim vs last10** untuk bantalan (§6.5).
7. **Bobot bantalan adaptif** (nilai awal, belum kalibrasi — §6.1).

## 8. File yang berubah

- Baru: `engine/analis.py`, `scripts/bandingkan_racik.py`,
  `tests/test_analis.py`, `LAPORAN-PERBAIKAN-RACIK.md` (file ini).
- Diubah: `engine/cushion.py` (ditulis ulang), `engine/nba_analysis.py`
  (wiring Tahap 4), `engine/recheck.py` (kaki resim signature baru),
  `engine/ticket_composer.py` (lantai harga, volume, urutan garis,
  peringatan, kriteria yakin + preferensi), `engine/anomaly.py`
  (cek bantalan tanpa spread), `report/nba_report.py` (bagian garis
  bandar + alasan bantalan + peringatan laga), `config/playstyle.yaml`
  (v13: section `analis`, Asuransi 2,5–3,0, `yakin_min_leg_prob`),
  `config.py` (section wajib `analis`), `schemas/nba_analysis.schema.json`
  + `schemas/ticket.schema.json` (field baru, semua opsional),
  tes-tes terkait, `DECISIONS.md` (bagian baru).

## 9. Hutang yang tetap terbuka (dari langkah sebelumnya)

- Persetujuan fit bola (rho pooled vs 0) — menunggu user.
- Ratifikasi FPL + sumber cedera bola kedua — menunggu user.
- Signup DunkAPI (gratis, tanpa kartu) untuk uji historis
  model-vs-market — menunggu persetujuan user.
- `min_leg_prob` 0,74: gate keras atau preferensi lunak — menunggu user.
- Kenaikan w (bila modul belajar mengusulkan) — menunggu user.
