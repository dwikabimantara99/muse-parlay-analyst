# LAPORAN — Vonis Per Laga + Setan Per Pemain + Perbaikan Asuransi

**Tanggal:** 2026-11-23 (sore WIB) · **Repo:** muse-parlay-analyst, branch main ·
**Config:** v16 → **v17** · **Suite:** **1806 tes OK** (baseline 1698 + 108 baru) ·
**Kredit Odds API:** 0 · **Commit:** `PENDING` (diisi koordinator setelah commit)

Build ini menjawab pelajaran insiden Denver 23 Nov (total akhir 296, OT,
42 tripoin — kedua tiket nyata user kalah karena satu kaki yang sama ada
di kedua tiket). Perintah user 12:38 WIB: gate TETAP KETAT; tanpa kaki
kembar; Asuransi safety-first; setan per pemain; betulkan banjir ke data
bersih; penyimpangan dilaporkan vs garis bandar.

Laporan per pekerja (detail penuh): `LAPORAN-VONIS.md` (worker A),
`LAPORAN-ASURANSI-BARU.md` (worker B), `LAPORAN-SETAN-PEMAIN.md`
(worker C). Laporan ini mensintesis — bukan menempel — ketiganya, plus
pekerjaan integrasi koordinator (§8).

> **TEMUAN UTAMA — dibaca dulu, jangan dilewati:** setelah SEMUA
> perbaikan ini (vonis, veto, tanpa-kembar, safety-first, banjir bersih,
> setan per pemain), **Asuransi TETAP tidak terbentuk di slate uji**
> (EQ Asuransi 0/10; gate banjir 1/8 lolos). Penghalang kini: volume
> 8 baris + edge 2 baris. Volume SATU-SATUNYA penghalang hanya di 1/10
> baris — melonggarkan ambang $100 saja TIDAK akan membentuk Asuransi.
> Ini temuan, bukan kegagalan: mesin bekerja persis seperti yang
> diperintahkan (tetap ketat). Bila besok pagi Asuransi juga tidak
> terbentuk dari 10 laga, itu mesin yang bekerja, bukan mesin yang
> rusak — dan keputusan atas opsi yang tersisa (terima / turunkan edge /
> longgarkan thin) tetap di tangan user. TIDAK ADA yang dilonggarkan
> diam-diam di build ini.

## 1. Sistem vonis per laga — `engine/vonis.py`

Mesin kini menghitung vonis per laga NBA dari DATA, bukan perasaan:
**HIJAU** (sehat → kandidat Asuransi), **MENENGAH_HIJAU** (cukup sehat →
kandidat Utama), **KUNING** (lempar koin → skip dari kedua tiket).
Vonis + alasannya tampil di laporan untuk SEMUA laga.

**Aturan persis** (ambang di config section `vonis:`, semua INITIAL
dengan rencana kalibrasi di komentar): sistem demerit atas 9 indikator
pelajaran Denver — edge kecil (< 2,5%), P banjir lemah (< 74%),
P setan lemah (< 65%), volume tipis (< $100), volume tidak diketahui,
gap model-vs-pasar kecil (< 4,0 poin) / besar (> 8,0 poin), sinyal ekor
gemuk (garis Asuransi ≥ 10 poin dari total pasar DAN harga ≤ 85¢),
total tinggi (garis bandar ≥ 235,0) — plus 4 pemicu keras yang langsung
KUNING: data tidak cukup, OT tinggi (≥ 0,028), edge tidak positif, dan
**veto rim protector**. HIJAU = 0 demerit; MENENGAH_HIJAU = 1–4;
KUNING = > 4 atau pemicu keras. Semua indikator dibaca di garis Asuransi
(prioritas a–f: equilibrium Asuransi → garis tahan-banjir tidak-tipis →
kaki Asuransi artefak → equilibrium Utama → kaki Utama artefak →
garis acuan).

**Veto rim protector** (temuan Gemini, TERVERIFIKASI dari data mesin):
rim protector utama OUT terkonfirmasi (2 sumber) + garis pasar tinggi
(≥ 235,0) ATAU pace tinggi (≥ 102,0) → veto menyala → KUNING, tidak
bisa dikalahkan skor EV simulasi. Definisi rim protector dari data:
per tim maksimal 2 pemain rotasi (GP ≥ 3, MP ≥ 15, BLK ≥ 0,8), urut
BPG — diturunkan dari stats.nba.com ke `config/rim_protector_2026-27.json`
(30/30 tim, check-in). Top-1 BPG GAGAL di data: pemimpin blok CHI adalah
Jalen Smith (1,1), bukan Claxton (1,0) — selisih satu blok per 10 laga,
di dalam noise. Veto memblokir KEDUA tiket (vonis KUNING) — pembacaan
yang lebih ketat dari brief ("minimal tidak masuk Asuransi"); menunggu
keberatan (§9).

**Kasus uji wajib:** DEN@CHI verif → KUNING (pemicu veto: Nic Claxton
OUT + garis 236,5 + pace 103,22) + ketujuh demerit. Laga sehat → HIJAU
dibuktikan di fixture SINTETIS (tidak ada laga slate yang HIJAU setelah
veto — OKC verif, satu-satunya kandidat 0-demerit, kena veto Chet
Holmgren 3,0 BPG OUT + pace MIA 102,19; nilai fixture DIUKUR lalu
dibekukan: edge +8,2%, P banjir 94,5%, P setan 68,4%, gap +7,0).

**Distribusi vonis di slate uji** (10 baris, 7 live + 3 verif 22 Nov,
0 error; tidak ada artefak analysis 23 Nov): **HIJAU 0 /
MENENGAH_HIJAU 2 (DAL@UTA, BOS@GSW live) / KUNING 8**; veto menyala
3 baris. Vonis menambah nilai di luar skip_awal pada BOS verif + OKC
verif (keduanya tidak kena skip_awal, tapi KUNING menurut vonis).
Catatan jujur: di slate ini veto melewatkan 1 pemenang (OKC, final 236)
sambil menangkap 1 pecundang (DEN, final 296) — pola yang konsisten
dengan kekhawatiran "terlalu ketat", tapi 10 baris bukan bukti kalibrasi;
yang membuktikan adalah ledger hasil settled.

**Wiring:** komposer `_kumpulkan_kandidat` saja — KUNING yang
DIEVALUASI dikeluarkan dari kedua tiket (alasan tercatat di `coret`);
kandidat membawa `vonis` + `vonis_alasan`. KUNING-karena-data TIDAK
dikeluarkan (gate per kaki tetap fail-closed sendiri) — keputusan yang
menunggu keberatan. Laporan: bagian `_bagian_vonis` baru (sesudah
Berita, sebelum Market) + veto ditampilkan MENONJOL. Urutan section
sudah benar (Cedera ke-7 → Vonis ke-9 → Kaki ke-11); tidak diubah.

**Tiga prinsip** (diverifikasi dari kode, bukan klaim): garis dari
volatilitas dulu baru cek harga (equilibrium); NO BET otomatis bila
filter keras menyisakan terlalu sedikit laga — TAPI "turunkan target"
TIDAK otomatis di kode (hanya user yang bisa menurunkan target);
exchange-first (tangga Polymarket riil dulu, sim mengevaluasi di
garis itu).

## 2. Aturan tanpa kaki kembar — komposer

Satu `match_id` tidak boleh muncul di kedua tiket. Aturan lama "garis
berbeda" DIGANTI total. Alokasi berdasarkan vonis (`_alokasikan_laga`):
HIJAU → Asuransi saja; menengah-hijau → Utama saja; KUNING dievaluasi
→ skip keduanya; tanpa vonis → **tanpa preferensi** (PENYIMPANGAN
terdokumentasi dari brief — menandai semua tanpa-vonis sebagai
menengah-hijau akan membuang SEMUA kandidat Asuransi dan membuat
Asuransi tidak pernah terbentuk). Disjoint ditegakkan juga di tingkat
subset (Asuransi dipilih dulu; kandidat Utama yang laganya sudah masuk
Asuransi dibuang). Fail-closed: tiket yang tidak mencapai target
pengali karena pembagian ini tidak terbentuk.

**Kasus uji wajib:** di slate uji nyata kedua tiket tidak terbentuk,
jadi cek disjoint di artefak nyata bersifat VAKUM — disjoint DIBUKTIKAN
di slate sintetis (satu laga bagus untuk kedua tiket hanya masuk
Asuransi; 4 laga → Asuransi terbentuk, Utama None tanpa memaksa ulang
laga; alokasi vonis end-to-end 9 laga disjoint). Laporan ini tidak
mengklaim lebih dari itu.

## 3. Equilibrium Asuransi safety-first — `engine/equilibrium.py`

Mode pemilihan equilibrium per tiket di config
(`mode_insurance: safety_first`, `mode_main: max_er`; mode hilang /
tidak dikenal → ConfigError, fail-closed). **Asuransi = p_final
TERTINGGI** di antara garis yang lolos semua gate (paling aman);
Utama TETAP max-ER (p_final × 100/harga). Kendala pengali x2 tetap di
komposer — tidak ada optimasi gabungan: garis paling aman adalah yang
paling mahal, jadi Asuransi butuh LEBIH BANYAK kaki untuk mencapai x2
(contoh fixture: kaki @92,5¢ butuh ~10 kaki untuk x2).

**Kasus uji wajib (OKC verif):** Asuransi TIDAK ADA — garis terbaik
yang lolos banjir + volume (U250,5 @89,5¢, p_final 0,908) gagal edge
(+1,3% < 3,5%); Utama ADA — U240,5 @75,5¢, p_final 0,788828,
ER 1,044805 (koordinator memverifikasi hitungan ER dengan tangan:
0,788828 × 100/75,5 = 1,0448 ✓). Perbedaan MODE dibuktikan di fixture
sintetis: safety-first U250,5 @92,5¢ (p_final 0,999612) vs max-er
U242,5 @84,5¢ (ER 1,1446). Safety-first TIDAK melonggarkan gate:
garis paling aman pun harus lolos semua gate.

## 4. Setan per pemain — `engine/setan_pemain.py` + `ingest/pemain_3p.py`

Setan umum (+18,07 untuk semua laga) DIGANTI setan PER TIM dari data
pemain, sesuai rumus yang disetujui user 12:38 WIB: demon per pemain =
percobaan 3P per laganya × % 3P TERBAIK liga musim ini; percobaan yang
DIHARAPKAN memperhitungkan siapa yang benar-benar main (pemain OUT →
0; di luar rotasi, < 10 menit/laga → tidak dihitung). Total setan tim =
(total normal − poin 3P normal) + poin 3P setan. Semua pemain yang
terdaftar dan rotasi, bukan cuma 5 starter.

**Sumber (GRATIS, terverifikasi live):** stats.nba.com
`leaguedashplayerstats` (utama, 474 pemain) + BBRef per-game
(fallback, 478 pemain). Satu tarikan mencakup seluruh liga. Status
main/absen TIDAK ada di kedua sumber — ketersediaan dari data cedera
artefak; bila tidak ada, satu-satunya proksi adalah menit (dicatat).

**Verifikasi wajib DEN@CHI** (inputs pra-laga asli artefak verif:
median 233,0; garis bandar 236,5; 7 pemain OUT dikeluarkan termasuk
Wilson 7,1 + Powell 6,8 percobaan/laga):

| | DEN | CHI | Gabungan |
|---|---|---|---|
| Pemain rotasi yang main | 10 | 12 | 22 |
| Percobaan 3P diharapkan | 32,10 | 35,20 | **67,30** |
| Poin 3P normal | 34,28 | 33,81 | 68,09 |
| Poin 3P setan (@54,1%) | 52,10 | 57,13 | 109,23 |

**Total setan = 233,0 − 68,09 + 109,23 = 274,14** (geser +41,14 dari
median; deviasi **+37,64 dari garis bandar 236,5**; **+23,07 di atas
setan umum 251,07**). Kedua kaki nyata ter-flag RAPUH: U252,5
p_setan_pemain 0,1298; U250,5 p_setan_pemain 0,1184. Total aktual 296
tetap di atas demon (+21,86) — sesuai desain: demon menandai
kerapuhan, bukan memprediksi banjir (banjir aktual juga menaikkan
JUMLAH percobaan, 90 vs 67,3 — tidak dimodelkan demon ini).

% terbaik liga adalah **54,1% (Cam Spencer, MEM, 61,2 percobaan)** —
bukan ~45% seperti perkiraan kasar koordinator (~258); selisih itu
menjelaskan hampir seluruh perbedaan 274,14 vs ~258. **Sensitivitas
ambang** (`pct_terbaik_min_total_3pa`, INITIAL 50): ambang 25 → 290,29;
50 → 274,14; 75/100 → 260,21 (Jamal Murray 47,2%); 150 → 240,83
(tidak lagi rapuh). Vonis "rapuh" kokoh untuk ambang 25–100; levelnya
yang bergerak. Point-in-time (data BBRef s.d. 21 Nov): 273,03 — hanya
−1,11 (look-ahead kecil, vonis tidak berubah). Di slate 3 laga, setan
pemain konsisten +21 s.d. +24 di atas setan umum.

**Wiring ke pipeline** — ditemukan + diperbaiki koordinator saat
integrasi (laporan C §11 memang menyerahkannya ke koordinator): lihat
§8.1.

## 5. Koreksi geser banjir ke data bersih — config

KOREKSI kontaminasi yang disetujui user 12:38 WIB (bukan pelonggaran):
`stress.banjir_3p_points` 13,54 → **8,50**; `stress.banjir_ft_points`
17,54 → **12,52**; `setan_points` 18,07 TIDAK berubah. Derivasi
terverifikasi: 3P (33,00−26,7901)×1,3681 = 8,50; FT (52,00−38,1646)×
0,9047 = 12,52 (dataset bersih n=243, tanpa 4 laga berjalan).

**Dampak terukur:** garis tahan banjir turun ~5–6 poin (DEN live
266,5 → 260,5; DEN verif 264,5 → 258,5); hasil skip TIDAK BERUBAH
di semua 10 baris; gate banjir kini 1/8 lolos (hanya OKC verif,
82,1% — naik dari 74,65%); EQ Asuransi tetap 0/10. Koreksi ini
membuktikan banjir BUKAN penghalang utama Asuransi — penghalangnya
volume + edge.

## 6. Penyimpangan vs garis bandar + transparansi volume — laporan

- Semua pelaporan banjir/setan/stress kini menyatakan penyimpangan
  sebagai poin di atas garis bandar: "Kalau laga memanas, total poin
  naik dari garis bandar 225,5: banjir tripoin +8,50 poin; banjir
  lemparan bebas +12,52 poin; …" + "Garis tahan banjir itu 16 poin di
  atas garis bandar 225,5." Setan per pemain dirender bila ada datanya:
  "Setan per pemain (kalau semua pemain panas bareng): total bisa
  sampai 261,5 poin, 36 poin di atas garis bandar 225,5."
- Volume PER GARIS dijelaskan di laporan: "volume satu laga tersebar
  di ratusan garis, sehingga garis yang jauh dari garis bandar hanya
  ditawar segelintir orang dan harganya kurang bisa dipercaya."
  **Ambang $100 TETAP** (tidak diubah).
- **Pengukuran volume sebagai penghalang:** volume adalah SATU-SATUNYA
  penghalang di **1/10 baris** (BOS live U223,5 @76,5¢, edge +3,58%,
  volume TIDAK TERCATAT — bukan $0; edge-nya hanya 0,08 poin di atas
  ambang 3,5%). Di 7 baris lain volume gagal BERSAMA gate lain — jadi
  melonggarkan ambang $100 saja tidak akan membentuk Asuransi di slate
  ini.

## 7. Pengukuran gabungan di slate uji — Asuransi tetap tidak terbentuk

Slate uji yang sama (10 baris, 7 live + 3 verif 22 Nov; tidak ada
artefak analysis 23 Nov). Skrip: `scripts/ukur_asuransi_baru.py` →
`out/ukur_asuransi_baru.json` (koordinator menjalankan ulang —
ringkasan terproduksi persis sama).

| Ukuran | Hasil |
|---|---|
| Gate banjir kaki artefak Asuransi (geser bersih) | **1 lolos / 7 gagal** (8 dihitung; 2 baris HOLD tanpa kaki Asuransi) |
| Equilibrium Asuransi (safety-first) | **0 ada / 10 tidak ada** |
| Equilibrium Utama (max-er) | **10 ada / 0 tidak ada** |
| Vonis | 8 KUNING, 2 menengah-hijau, **0 HIJAU** |
| Racik default (vonis aktif) | Asuransi tidak terbentuk (0 kandidat); Utama tidak terbentuk (maks x1,22 — hanya DAL) |
| Racik tanpa vonis | Asuransi tidak terbentuk; Utama maks x1,62 (DAL + OKC verif) |

Temuan struktural LAPORAN-ATURAN-KERAS §5 BERTAHAN: satu-satunya baris
yang lolos banjir (OKC verif) gagal edge (+1,3% < 3,5%). Vonis mengubah
Utama (x1,22 vs x1,62 — selisihnya satu kaki OKC live yang di-VETO),
bukan Asuransi — Asuransi 0 kandidat di semua varian; gate-lah
penghalangnya, bukan vonis. **0 HIJAU berarti alokasi HIJAU → Asuransi
belum pernah teruji di data nyata** — hanya di fixture sintetis.

## 8. Pekerjaan integrasi koordinator

### 8.1 CELAH WIRING — ditemukan + diperbaiki sebelum commit

`engine/stress.skenario_panas` sudah membaca `analysis["setan_pemain"]`
bila ada, tapi **TIDAK ADA pemanggil produksi yang mengisi blok itu**
— analyze tidak pernah mengambil data pemain, jadi dalam jalan nyata
besok pagi demon akan selalu fallback ke setan umum +18,07 dan laporan
tidak pernah menampilkan total setan per pemain. Koordinator menutup
celah ini:

- `engine/nba_analysis.py` **Tahap 5c** (mengikuti pola berita Tahap
  5b): ambil data pemain 3P se-liga + hitung demon per laga +
  lampirkan blok `setan_pemain` ke artefak. Gagal → blok "gagal" +
  `missing`, artefak tetap jalan, `skenario_panas` fallback ke setan
  umum. `enabled: false` → blok "nonaktif" tanpa fetch.
- `ingest/pemain_3p.py`: `fetch_pemain_3p_cached` — cache satu-proses
  per musim (satu tarikan mencakup semua tim; tanpa cache, slate 10
  laga = 10 tarikan stats.nba.com). Hanya hasil OK yang di-cache.
- `schemas/nba_analysis.schema.json`: properti opsional `setan_pemain`
  (format_version tetap 1, mengikuti preseden `news`).
- **16 tes baru** (`tests/test_setan_pemain_wiring.py`): skenario_panas
  memakai blok artefak tanpa kwarg; fallback tanpa blok; blok gagal
  tidak dipakai; hitung blok tangan (226,35 / 225,60 dengan pemain OUT
  dikeluarkan); nonaktif tanpa fetch; median None; musim dari tanggal;
  cache (1 tarikan untuk 2 panggilan; gagal tidak di-cache); skema
  menerima blok ok + gagal.

### 8.2 Rekonsiliasi stash

Insiden stash worker C (pop gagal di tengah sesi) meninggalkan
`stash@{0}` berisi `ticket_composer.py` lama. Koordinator mengekstrak
versi stash ke /tmp dan membandingkannya dengan disk: `equilibrium.py`
stash IDENTIK dengan disk (0 baris beda); `ticket_composer.py` sama
himpunan fungsinya, 46 baris beda — semuanya PENAMBAHAN di disk
(wiring vonis worker A). Tidak ada isi stash yang hilang dari disk →
stash di-`drop`; `git stash list` kini kosong. Pelajaran yang dicatat:
worker TIDAK BOLEH memakai `git stash` di tree bersama.

### 8.3 Referensi basi + bump versi

- `engine/stress.py`: teks docstring + runtime `_DASAR_BANJIR_3P` /
  `_DASAR_BANJIR_FT` masih mengutip nilai tercemar lama (13,54/17,54,
  n=247) — diperbarui ke nilai bersih (8,50/12,52, n=243) + status
  koreksi (SUDAH diterapkan, bukan menunggu).
- Klaim worker B bahwa docstring `engine/vonis.py` mengutip "geser
  17,54" DIPERIKSA dan SALAH — `vonis.py` sudah menyebut 12,52;
  tidak ada perbaikan yang dibutuhkan.
- Config v16 → **v17** (+ vonis + veto + tanpa-kembar + safety-first
  + setan per pemain + koreksi banjir); tes pin versi diperbarui.

## 9. Keputusan desain yang menunggu keberatan

1. Veto memblokir KEDUA tiket (bukan hanya Asuransi).
2. Veto tidak dievaluasi → tidak menyala (bukan fail-closed-KUNING).
3. KUNING-karena-data tidak dikeluarkan komposer.
4. Tanpa vonis = tanpa preferensi (bukan menengah-hijau).
5. Safety-first = max p_final per kaki; kendala x2 tetap di komposer
   (tanpa optimasi gabungan keamanan-vs-pengali).
6. Edge terbaik sebagai indikator level-laga (maks atas semua kaki +
   equilibrium), bukan hanya di garis Asuransi.
7. Batas demerit 4|5 (IND kasus batas: demerit ke-5 gap_besar +8,91
   vs ambang 8,0).
8. Veto top-2 + GP ≥ 3 + BLK ≥ 0,8 (menamai guard di tim lemah;
   melewatkan pemain 0–2 laga seperti Duren).
9. Pace veto = pace musim tim tercepat (bukan pace laga sim / last10).
10. `total_tinggi` sebagai indikator sekunder yang belum terbukti
    (1 demerit; hapus bila kalibrasi menunjukkan tidak ada hubungan).
11. Ambang setan per pemain: `pct_terbaik_min_total_3pa` 50 + ambang
    menit rotasi 10,0 (keduanya INITIAL; level demon paling sensitif
    terhadap ambang 50 — lihat §4).
12. Basis kekuatan penuh tanpa penskalaan rasio laga (§3.1 laporan C).
13. Section `setan_pemain` opsional di `skenario_panas` (hilang →
    enabled default True + fallback bila tanpa data).
14. Pemetaan rim protector di `config/` (karena `/data/`
    di-`.gitignore`).
15. Fixture DEN diperlakukan berbeda di dua file tes (test_equilibrium
    ditulis ulang ke realita baru; test_ticket_composer dikalibrasi
    ulang supaya kasus "DEN ditolak gate banjir" tetap teruji).

## 10. Batasan jujur + utang

- **Sampel FIT kecil (10 baris, 1 slate).** Semua ambang vonis INITIAL;
  distribusi 0/2/8 adalah gambaran, bukan bukti. Kalibrasi hanya dari
  hasil settled di ledger.
- **Asuransi tetap tidak terbentuk** (§7) — build ini memperbaiki
  mekanisme, bukan hasilnya di slate ini. Opsi yang tersisa (terima /
  turunkan edge 3,5% / longgarkan thin / banjir moderat untuk gate
  Asuransi) adalah keputusan user.
- **Disjoint + alokasi HIJAU hanya terbukti di fixture sintetis**
  (slate nyata vakum; 0 HIJAU).
- **Veto bergantung pada ketepatan waktu kabar cedera** (DEN live
  tidak kena veto — snapshot dibuat sebelum Claxton OUT diumumkan)
  dan pada **kesegaran pemetaan** (segarkan mingguan; tidak ada
  peringatan basi otomatis).
- **Setan pemain tidak memodelkan lonjakan JUMLAH percobaan**
  (hanya akurasi); % terbaik liga adalah satu observasi berisik
  (Cam Spencer 54,1% dari 61 percobaan, SE ≈ 6,4 pp) tanpa shrinkage;
  P setan di geser besar memakai interpolasi CDF yang kasar
  (flag total > garis adalah sinyal kokoh, P hanya indikasi);
  pencocokan nama pemain persis (varian sufiks/aksen bisa lolos
  filter absen); QUESTIONABLE/PROBABLE dihitung main.
- **UTANG — fetch H2H:** vonis tidak bergantung H2H sama sekali
  (data H2H mesin kosong untuk DEN@CHI). Klaim H2H 248–257 (Gemini)
  tidak dipakai dan tidak bisa diverifikasi.
- **"Turunkan target" tidak otomatis di kode** (hanya NO BET yang
  otomatis). **Banjir dan setan berkorelasi** (keduanya menggeser CDF
  yang sama) tapi tetap dihitung terpisah karena user menamai keduanya
  sebagai indikator Denver yang berbeda. **Vonis menilai ANALISIS,
  bukan laga abstrak** — vonis yang benar kemarin bisa salah hari ini
  bila datanya berubah.
- **Tidak diubah (sesuai brief):** ambang gate 5,0 + lean-to-market;
  ambang volume $100; tidak ada kredit Odds API (0).

## 11. Ringkasan hasil

| Item | Status |
|---|---|
| 1. Sistem vonis + veto rim protector | SELESAI — 41 tes; distribusi 0/2/8; veto 3 baris |
| 2. Tanpa kaki kembar + alokasi vonis | SELESAI — disjoint subset + alokasi; 5 tes |
| 3. Equilibrium Asuransi safety-first | SELESAI — mode per tiket; 8 tes |
| 4. Setan per pemain | SELESAI — DEN@CHI 274,14, kedua kaki rapuh; 34 tes |
| 5. Koreksi geser banjir (8,50 / 12,52) | SELESAI — config + komentar koreksi |
| 6. Deviasi vs garis bandar | SELESAI — laporan |
| 7. Transparansi volume + pengukuran | SELESAI — volume satu-satunya penghalang 1/10 |
| Wiring setan → analyze (koordinator) | SELESAI — Tahap 5c + cache + skema; 16 tes |
| Suite | **1806 tes OK** (1698 + 41 + 34 + 17 + 16) |
| Ruff (lint) + black | BERSIH (179 file) |
| Odds API | 0 kredit |

**File yang dibuat/diubah:** `engine/vonis.py` (BARU),
`engine/setan_pemain.py` (BARU), `ingest/pemain_3p.py` (BARU),
`config/rim_protector_2026-27.json` (BARU, check-in),
`scripts/fetch_rim_protector.py` (BARU), `scripts/ukur_vonis.py`
(BARU), `scripts/ukur_asuransi_baru.py` (BARU),
`scripts/verifikasi_setan_pemain.py` (BARU),
`tests/test_vonis.py` (BARU, 41), `tests/test_setan_pemain.py`
(BARU, 34), `tests/test_setan_pemain_wiring.py` (BARU, 16),
`config/playstyle.yaml` (v17: section `vonis:` + `setan_pemain:` +
mode equilibrium + geser banjir bersih),
`engine/ticket_composer.py` (vonis + tanpa-kembar),
`engine/equilibrium.py` (mode safety-first + `nilai_semua_garis`),
`engine/stress.py` (wiring setan pemain + teks banjir bersih),
`engine/nba_analysis.py` (Tahap 5c setan per pemain),
`report/nba_report.py` (bagian vonis + deviasi + volume),
`schemas/nba_analysis.schema.json` (properti opsional
`setan_pemain`), 6 file tes diperbarui (geser bersih + aturan baru),
`DECISIONS.md` (catatan implementasi), `LAPORAN-VONIS.md`,
`LAPORAN-ASURANSI-BARU.md`, `LAPORAN-SETAN-PEMAIN.md`,
`LAPORAN-VONIS-SETAN-PEMAIN.md` (laporan ini).
