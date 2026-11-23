# Laporan: Titik Equilibrium + Skip dari Awal + Peluang OT di Seleksi

Build penyempurnaan mesin, item 1, 2, 5 (keputusan user 2026-11-23
10:22 + 10:31 + 10:41 WIB). Worker A; koordinator mengintegrasi +
commit. Config masih v15 (koordinator yang bump ke v16).

Bukti ukur: `scripts/ukur_equilibrium.py` →
`out/ukur_equilibrium.json` (gitignored, seperti
`out/ukur_gate_banjir.json`). 0 kredit Odds API. Full suite 1696 tes
OK (termasuk tes worker lain yang sedang berjalan di working tree
yang sama; tes baru build ini 69: 32 equilibrium + 25 skip_awal +
4 integrasi komposer + 5 laporan + 3 config).

## 1. Ringkasan

- **Titik equilibrium** (`engine/equilibrium.py`, baru): per laga per
  tiket, di antara garis tangga yang lolos SEMUA gate tiket itu,
  pilih yang memaksimalkan expected return
  ER = p_final × (100 / harga venue). Menggantikan aturan
  garis-termurah-yang-lolos + mekanisme climb banjir.
- **Skip dari awal** (`engine/skip_awal.py`, baru): 3 pemicu —
  (a) tidak ada equilibrium di kedua tiket, (b) pola Denver
  (konjungsi 4 syarat eksplisit), (c) potensi OT tinggi. Skip +
  alasan tampil di komposer (`skipped_matches` + ringkasan) dan di
  laporan (spanduk Ringkasan + bagian baru). SEMUA laga tetap
  dilaporkan, termasuk yang di-skip.
- **Hasil ukur slate nyata 22 Nov (10 baris):** equilibrium Asuransi
  0/10, Utama 10/10; di-skip 6/10 (5 pola Denver + 1 OT); TIDAK ADA
  tiket yang terbentuk — sama seperti aturan lama — tapi
  komposisinya berubah (lihat §5). Temuan banjir+edge
  LAPORAN-ATURAN-KERAS §5 BERTAHAN di bawah equilibrium: Asuransi
  tetap tidak terbentuk, kini dengan diagnosis per baris.

## 2. Definisi titik equilibrium (dan alasannya)

**Definisi.** Titik equilibrium satu kaki = garis tangga Under dengan
expected return tertinggi di antara garis yang lolos SEMUA gate tiket
itu. ER = p_final × (100 / harga venue) = pembayaran harapan per $1
yang dipasang sendiri (ER = 1 + EV). Seri ER (< 1e-9) → p_final lebih
besar → garis lebih kecil.

**Kenapa max-ER, bukan garis termurah.** Aturan lama memilih garis
termurah yang lolos ambang — lolos filter, tapi belum tentu titik
paling manis: garis sedikit lebih mahal bisa jauh lebih mungkin
menang (atau sebaliknya, garis lebih murah bisa bernilai lebih
baik). Contoh nyata: OKC verif Utama — equilibrium U240,5 @75,5¢
(ER 1,0448) vs kaki artefak U244,5 @82,5¢ (ER 1,0207): LEBIH MURAH
dan bernilai lebih baik. Contoh sebaliknya: fixture 224/5 Utama —
garis termurah yang lolos 234,5 @76,5¢ (ER 0,88) vs equilibrium
238,5 @80,5¢ (ER 1,20): sedikit lebih mahal, jauh lebih mungkin
menang. Target pengali tiket (x2/x3+) BUKAN kendala per kaki —
komposer menumpuk kaki-kaki equilibrium sampai target tercapai.

**Tidak ada lantai ER > 1.** Max-ER adalah yang terbaik yang
tersedia; bila titik paling manis pun EV negatif, itu dilaporkan
apa adanya (ORL live Utama: ER 0,9889) dan viabilitas dinilai di
level tiket oleh komposer. Keputusan desain (menunggu keberatan).

**Gate per tiket (kunci config lama dipakai ulang).** Asuransi:
min_leg_prob 0,74 + lantai harga 75¢ + banjir (p_banjir_terburuk ≥
0,74) + tidak thin + edge ≥ 3,5% + bukan MAHAL. Utama: min_leg_prob
0,65 + lantai 75¢ saja (thin boleh, tanpa gate banjir/edge — aturan
lama dipertahankan). Gate banjir komposer tetap berjalan di atas
equilibrium sebagai pertahanan berlapis (lolos by construction pada
kaki equilibrium).

**p_final per garis via geser pasar tersirat (implied shift).**
Artefak hanya membawa p_market untuk dua kaki artefak (dari Kalshi
di garis yang SAMA persis); tangga Kalshi tidak tersimpan — jadi
p_market per garis tidak bisa dibaca langsung. Yang dilakukan:
geser δ = garis jangkar − CDF⁻¹(p_market jangkar); lalu
p_market(garis) = CDF(garis − δ); p_final = blend w=0,3. Asumsi
(terdokumentasi di kode): pasar dan model hanya berbeda GESER
LOKASI — asumsi yang sama dengan `engine/stress.py` untuk banjir.
P2 dihormati: sumber pembanding tetap Kalshi (jangkarnya);
Polymarket dipakai hanya sebagai HARGA, tidak pernah sebagai
p_market. Jangkar = kaki artefak bergaris + ber-p_market, utamakan
tiket yang sama, bila tidak ada pakai tiket lain (geser adalah sifat
laga). Validasi: di garis jangkar OKC verif, p_final hasil geser
mereproduksi p_final kaki artefak PERSIS (0,908341, selisih 0,0).

**"Tidak dihitung" vs "tidak ada".** Tanpa CDF / tangga / jangkar →
`dihitung=False` → komposer memakai kaki artefak apa adanya
(equilibrium adalah upgrade seleksi, bukan gate ketersediaan data).
Dihitung + tidak ada garis yang lolos → kaki ditolak dengan alasan
diagnostik yang menamai gate yang mengikat (urutan diagnosis:
peluang → lantai_harga → banjir → volume → edge → label), memakai
ulang token lama (`tidak_ada_garis_tahan_banjir`, `volume tipis`,
`edge_kecil`) supaya jejak audit tetap nyambung.

**Kaki equilibrium dibangun ulang** (`rakit_kaki_equilibrium`):
p_model/p_market/p_final/EV/label dihitung ulang DI GARIS BARU —
ini MEMPERBAIKI interaksi banjir × edge LAPORAN-ATURAN-KERAS §5
(kaki naik garis tidak lagi memakai p_final basi). `leg_id` TIDAK
berubah (recheck tetap cocok, pola yang sama dengan climb lama).
Climb dicatat dengan reason `"equilibrium"` (dirangkai dengan climb
lama bila ada, mis. `volume_tipis+equilibrium`). Bila garis
equilibrium == garis artefak, kaki artefak dipakai utuh (tanpa
selisih pembulatan).

**Perubahan perilaku yang disengaja (menggantikan keputusan lama).**
(1) Equilibrium MENGGANTIKAN mekanisme climb banjir (flood climb
tidak lagi dipakai; gate banjir komposer tetap sebagai pertahanan
berlapis). (2) Equilibrium BOLEH melompati garis tahan-banjir yang
thin ke garis tebal di atasnya — keputusan lama "gate tidak
melompat" (LAPORAN-ATURAN-KERAS §7.1) digantikan, karena keputusan
itu hanya masuk akal di dalam mekanisme climb; equilibrium menilai
SEMUA garis. Thin tetap hard gate Asuransi: garis thin sendiri
tidak pernah dipilih. 3 tes komposer diperbarui dengan alasan
terdokumentasi di komentar tes (lihat §7).

## 3. Aturan skip dari awal

Satu pemicu positif cukup untuk skip dari KEDUA tiket:

**(a) `tidak_ada_equilibrium`** — equilibrium TIDAK ADA di kedua
tiket (dihitung sungguh-sungguh, bukan gagal hitung). Satu tiket
punya equilibrium → tidak skip via (a). Keputusan desain (menunggu
keberatan).

**(b) `pola_denver`** — KONJUNGSI 4 syarat, semua harus benar:
1. `flag_setan` pada garis acuan: P normal ≥ target Asuransi (0,74)
   tapi P setan < target;
2. tidak ada garis TIDAK-TIPIS yang tahan banjir pada target
   Asuransi ("rapuh banjir di semua garis wajar" — garis wajar =
   garis yang bisa dibeli, yaitu tidak thin);
3. garis acuan thin;
4. edge kecil pada garis acuan: edge implied (p_final − harga venue)
   < `skip_awal.pola_denver.edge_kecil_pct` = **3,5 INITIAL**
   (cermin proposal D12; rencana kalibrasi §8).

Garis acuan = garis tangga Under TERENDAH dengan P normal ≥ target
Asuransi (pada tangga monoton naik, ini sekaligus yang termurah).
"Volume tipis" dioperasionalkan di (2)+(3).

**(c) `ot_tinggi`** — ot_probability sim ≥
`ot_seleksi.skip_ot_prob` = **0,028 INITIAL**. KEPUTUSAN: SKIP,
bukan bantalan lebih besar — OT menambah loncatan diskret ~20+ poin
yang SUDAH dimodelkan sim dalam distribusi total; risiko sisa
adalah model MEREMEHKAN OT (nilai sim 1,7–2,9% vs laju OT historis
NBA ~5–6%), yang tidak bisa diperbaiki oleh bantalan yang dihitung
dari model yang sama. Ambang 0,028 ≈ plafon teoretis peluang seri
laga imbang di bawah sigma_margin hasil fit
(1/(14,4307·√(2π)) ≈ 0,0277) — hanya laga yang praktis imbang yang
kena skip. Ambang ini dalam SKALA SIM, bukan skala historis:
ambang 5% dalam skala sim tidak akan pernah memicu.

**KEJUJURAN:** DEN@CHI (yang benar-benar masuk OT) punya ot_prob
sim hanya 2,36%/2,13% — TIDAK kena aturan OT. Denver ditangkap
pola_denver, bukan aturan OT.

**Tanpa data → "tidak dievaluasi", BUKAN skip.** Skip adalah klaim
positif soal laga; bila CDF/tangga/jangkar tidak ada, pola +
equilibrium tidak bisa dinilai (alasan tercatat). Gate per kaki
tetap fail-closed seperti sebelumnya. Pengecualian: OT bisa dinilai
sendiri tanpa CDF/tangga (bila ot_prob ada, laga bisa di-skip via
(c) saja).

**Flag config** `equilibrium.enabled` / `skip_awal.enabled`
(default True bila hilang; non-bool → ConfigError) untuk pengukuran
A/B + rollback; dimatikan = perilaku lama persis (dibuktikan tes
integrasi §7).

## 4. Kasus uji wajib

### 4.1 DEN@CHI — di-skip (pola Denver)

- Live: equilibrium Asuransi TIDAK ADA (gate mengikat volume —
  satu-satunya garis tahan banjir U266,5 @94¢ thin); equilibrium
  Utama ADA (U250,5 @76,5¢, p_final 0,7675, ER 1,0033).
- Verif: sama — Asuransi tidak ada (volume; garis tahan 264,5 @94,5¢
  thin, 2 garis); Utama ADA (U250,5 @78,5¢, ER 1,0127).
- **Presisi penting:** skip DEN datang dari **pola_denver (b)**,
  BUKAN dari (a) — karena equilibrium Utama ADA. Frasa tugas
  "tidak ada equilibrium → skip" benar hanya untuk Asuransi.
  Keempat syarat pola benar di kedua artefak (live: acuan U248,5
  @72¢ thin, P normal 75,9% vs P setan 40,5%, edge +1,5%).
- OT DEN (2,36%/2,13%) di bawah ambang — aturan OT tidak menangkap
  Denver (lihat §3).

### 4.2 OKC@MIA verif — equilibrium ada, tidak di-skip

- Equilibrium Utama: **U240,5 @75,5¢, p_final 0,789, ER 1,0448**,
  tidak thin — dipilih karena ER tertinggi di antara 10 garis yang
  lolos (vs kaki artefak U244,5 @82,5¢, ER 1,0207). Lebih murah DAN
  bernilai lebih baik; komposer memakainya (pengali maks Utama
  verif naik x1,15 → x1,25).
- Equilibrium Asuransi: tidak ada — gate mengikat EDGE (garis
  terbaik yang lolos banjir + volume U250,5 @89,5¢ edge +1,3% <
  minimum 3,5%).
- OKC verif TIDAK di-skip (kontrol normal): garis tahan banjir
  tidak thin ADA (U250,5) dan edge acuan tidak kecil (+5,49%).

## 5. Hasil ukur slate nyata (10 baris yang sama dengan ukur_gate_banjir)

| Laga | EQ Asuransi | EQ Utama | OT | Skip |
|---|---|---|---|---|
| DET@ATL live | tidak ada (edge) | U237,5 @76,5¢ ER 1,0152 | 2,89% | ot_tinggi |
| OKC@MIA live | tidak ada (volume) | U244,5 @77¢ ER 1,0004 | 2,64% | pola_denver |
| ORL@WAS live | tidak ada (banjir) | U241,5 @88¢ ER 0,9889 | 2,60% | pola_denver |
| DEN@CHI live | tidak ada (volume) | U250,5 @76,5¢ ER 1,0033 | 2,36% | pola_denver |
| DAL@UTA live | tidak ada (volume) | U238,5 @77,5¢ ER 1,0367 | 2,70% | — |
| IND@NYK live | tidak ada (volume) | U226,5 @75¢ ER 1,0258 | 1,70% | pola_denver |
| BOS@GSW live | tidak ada (volume) | U223,5 @76,5¢ ER 1,0468 | 2,49% | — |
| OKC@MIA verif | tidak ada (edge) | U240,5 @75,5¢ ER 1,0448 | 1,90% | — |
| DEN@CHI verif | tidak ada (volume) | U250,5 @78,5¢ ER 1,0127 | 2,13% | pola_denver |
| BOS@GSW verif | tidak ada (volume) | U223,5 @77,5¢ ER 1,0242 | 2,21% | — |

Gate mengikat Asuransi: volume 7, edge 2, banjir 1. Tidak ada baris
yang skip via (a) — semua baris punya equilibrium Utama.

**Racik per slate (baru vs lama):**

| Slate | Aturan | Asuransi | Utama | Di-skip |
|---|---|---|---|---|
| live 22 Nov (7 laga, 7 OK) | baru | tidak terbentuk [0 kandidat] | tidak terbentuk [2 kandidat, maks x1,59] | 5 |
| live 22 Nov | lama | tidak terbentuk [0 kandidat] | tidak terbentuk [2 kandidat, maks x1,59] | 0 |
| verif tahap 4 (3 laga, 1 OK) | baru | tidak terbentuk [0 kandidat] | tidak terbentuk [1 kandidat, maks x1,25] | 0 |
| verif tahap 4 | lama | tidak terbentuk [0 kandidat] | tidak terbentuk [1 kandidat, maks x1,15] | 0 |

Tidak ada tiket terbentuk di kedua aturan — tapi komposisinya
berbeda dan lebih jujur: aturan baru menukar DET (skip OT) dengan
BOS (equilibrium menyelamatkan kaki artefak U219,5 di bawah lantai
ke U223,5 @76,5¢) di slate live, dan memakai garis equilibrium
OKC yang lebih bernilai di slate verif (x1,25 vs x1,15).

**Margin tipis (sensitivitas ambang — laporkan apa adanya):**
- DET OT 2,89% vs ambang 2,8% — margin 0,09 poin.
- DAL selamat dari pola hanya karena edge acuan +4,66% vs ambang
  3,5% (syarat lain benar semua); BOS live +6,87% + acuan tidak
  thin.
- `flag_setan` pada garis acuan benar di SEMUA 10 baris — syarat
  (1) lemah sendirian; daya beda pola datang dari (2)+(3)+(4).

## 6. Laporan: semua laga dilaporkan

`report/nba_report.py`: bagian baru "Titik equilibrium dan skip
dari awal" (vonis skip + alasan, titik equilibrium per tiket,
baris OT, detail syarat pola Denver) + spanduk skip di Ringkasan
("LAGA INI DI-SKIP dari kedua tiket: ..."). Laga yang di-skip
TIDAK dihapus dari laporan. Gagal hitung dicatat sebagai celah,
tidak pernah crash. Catatan: alasan mesin memakai pemisah desimal
"." (mis. "75.9%") — konsisten dengan alasan coret komposer yang
sudah ada ("54.1%"), berbeda dengan "," di narasi laporan.

## 7. Tes

**Baru (69):** `tests/test_equilibrium.py` (32) — definisi max-ER,
seri ER → p_final → garis terkecil, tidak ada lantai ER, gate per
tiket + diagnosis, subsumsi label MAHAL oleh gate edge, geser pasar
(produksi p_market jangkar persis), tidak-dihitung, rakit kaki
(termasuk rangkai climb + tidak ada mutasi artefak), 8 tes artefak
nyata. `tests/test_skip_awal.py` (25) — konjungsi pola (tiap
syarat di-toggle mati satu per satu), ambang OT 0,028 (batas
inklusif), pemicu ganda, (a) dua arah, tidak-dievaluasi (termasuk
OT-saja), kontrol fixture sintetis DEN (tidak memicu pola —
membuktikan pola tidak memukul semua laga), 7 tes artefak nyata.
Integrasi komposer (4) — skip DEN artefak nyata, flag-mati =
perilaku lama persis, leg_id tidak berubah, skip OT sintetis.
Laporan (5) — bagian baru, spanduk Ringkasan, varian tidak-di-skip,
JSON, minimal tidak crash. Config (3) — tiga section baru + nilai.

**Diperbarui (3, alasan terdokumentasi di komentar tes):**
- `test_garis_tahan_banjir_dipakai_bila_tidak_thin`: climb reason
  `"banjir"` → `"equilibrium"`; p_final 0,927 (garis lama) →
  0,995248 (dihitung ulang di garis baru — perbaikan §5).
- `test_garis_tahan_banjir_thin_skip_meski_garis_atas_tebal` →
  diganti nama `test_equilibrium_memakai_garis_tebal_di_atas_garis_tahan_thin`:
  equilibrium kini MEMAKAI 248,5 @90,5¢ (keputusan "tidak melompat"
  digantikan — lihat §2).
- `test_racik_penuh_dengan_kaki_naik_garis`: climb reason
  `"banjir"` → `"equilibrium"`; garis + pengali 2,22 tidak berubah.
- `test_den_ditolak_gate_banjir` diperkuat (alasan menyebut
  "equilibrium"; kaki Utama kini U254,5 equilibrium) — tidak ada
  asersi lama yang diubah.

**Full suite: 1696 tes OK** (baseline 1537 di a84a249; +69 build
ini + ~90 dari worker lain yang sedang berjalan di working tree
yang sama). `ruff check .` dan `black --check .` bersih.

## 8. Parameter INITIAL + rencana kalibrasi

1. `skip_awal.pola_denver.edge_kecil_pct` = 3,5 (INITIAL, cermin
   proposal D12). Kalibrasi: kumpulkan edge di garis acuan +
   hasil laga (menang/kalah kaki, total akhir vs garis) selama
   satu musim slate; ukur daya beda ambang (berapa laga anomali
   yang tertangkap vs laga normal yang ikut ter-skip); fit ulang
   ambang ke budget skip yang dipilih user. Efektif hanya atas
   persetujuan user.
2. `ot_seleksi.skip_ot_prob` = 0,028 (INITIAL, ≈ plafon teoretis
   0,0277). Kalibrasi: kumpulkan ot_prob sim + hasil OT aktual
   selama satu musim slate; ukur kalibrasi (apakah laga dengan
   ot_prob 2,8% benar-benar OT ~2,8% dari waktu); fit ulang ambang
   ke budget skip yang dipilih user. Efektif hanya atas
   persetujuan user.

## 9. Keputusan desain yang menunggu keberatan

1. **Definisi equilibrium = max-ER** (bukan garis termurah, bukan
   p_final tertinggi). Alternatif yang dipertimbangkan: p_final
   tertinggi akan selalu memilih garis termahal (monoton) —
   ditolak karena melanggar "harga mengikuti statistik".
2. **Tidak ada lantai ER > 1** pada equilibrium (titik manis boleh
   EV negatif; viabilitas dinilai di level tiket).
3. **Skip (a) butuh tidak ada equilibrium di KEDUA tiket** — satu
   tiket punya equilibrium → tidak skip via (a).
4. **OT: SKIP, bukan bantalan lebih besar** (alasan §3).
5. **Equilibrium boleh melompati garis tahan-banjir thin** —
   menggantikan keputusan "gate tidak melompat" (§7.1
   LAPORAN-ATURAN-KERAS).
6. **Ambang OT 0,028 dalam skala sim** (bukan 5% historis).
7. **Syarat (1) pola Denver (flag setan di garis acuan) hampir
   selalu benar** pada tangga rapat — daya beda pola datang dari
   syarat (2)–(4). Bila reviewer menilai syarat (1) tidak menambah
   apa-apa, ia bisa dihapus atau dipindah ke garis lain (mis. kaki
   artefak) — tapi pemindahan ke kaki artefak akan membuat pola
   tidak bisa dinilai pada laga tanpa kaki artefak (mis. DEN
   verif HOLD).

## 10. Batasan yang diketahui

- **Recheck menilai garis LAMA.** Kaki equilibrium dibangun ulang
  SETELAH recheck (pola yang sama dengan climb lama): recheck
  menilai garis artefak, bukan garis equilibrium. Kebasahan yang
  sama seperti sebelum build ini — bukan regresi, tapi belum
  diperbaiki.
- **CDF dijepit di ujung tanpa ekstrapolasi** (seperti stress.py):
  garis di luar jangkauan CDF memakai peluang ujung.
- **Pilihan jangkar memengaruhi ranking.** Jangkar tiket-yang-sama
  diutamakan; jangkar berbeda → δ berbeda → ranking ER bisa
  berubah (contoh: ORL Utama U241,5 dengan jangkar Main vs U233,5
  dengan jangkar Asuransi). Didokumentasikan; belum ada aturan
  pemilihan jangkar yang lebih baik.
- **Asumsi geser-lokasi** (pasar vs model hanya berbeda lokasi)
  belum divalidasi di luar titik jangkar — validasi baru di titik
  jangkar (selisih 0,0). Kalibrasi w (Brier, tiap 50 kaki) tetap
  berjalan seperti sebelumnya.

## 11. File yang berubah (Worker A saja)

- Baru: `engine/equilibrium.py`, `engine/skip_awal.py`,
  `scripts/ukur_equilibrium.py`, `tests/test_equilibrium.py`,
  `tests/test_skip_awal.py`, `LAPORAN-EQUILIBRIUM-SKIP-AWAL.md`,
  `out/ukur_equilibrium.json` (gitignored).
- Diubah: `config/playstyle.yaml` (3 section baru; versi TIDAK
  diubah, tetap 15), `config.py` (3 section masuk
  REQUIRED_PLAYSTYLE_SECTIONS), `engine/ticket_composer.py`
  (integrasi equilibrium + skip + `skipped_matches`),
  `report/nba_report.py` (bagian baru + spanduk Ringkasan),
  `tests/test_ticket_composer.py` (3 tes diperbarui + 4 integrasi
  baru), `tests/test_report_nba.py` (5 tes baru),
  `tests/test_config.py` (3 tes baru).
- TIDAK disentuh: `DECISIONS.md` (koordinator), file worker lain
  (`ingest/news_nba.py`, `engine/nba_sim.py`, `ingest/nba_brain.py`,
  `report/news_section.py`).
