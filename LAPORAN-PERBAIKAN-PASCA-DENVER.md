# Laporan Perbaikan Pasca-Denver — Mesin Analis Parlay

**Tanggal:** 23 November 2026 (dibangun sore hari, untuk dipakai Selasa 24 Nov pagi — slate 10 laga, kickoff 07:00 WIB)
**Commit:** `11ed42e` (feat perbaikan pasca-Denver)
**Config:** playstyle.yaml v14
**Tes:** 1.481 lulus (dari 1.395 — tambah 86), ruff + black bersih, **0 kredit Odds API**

## 0. Insiden yang diperbaiki

Tiket nyata user 23 Nov 2026 (jup.ag, stake $15 + $15): Asuransi 4 kaki
2,17x, Utama 6 kaki 3,72x. Kaki DEN@CHI (Asuransi U252,5 @82¢, Utama
U250,5 @79¢) jebol karena banjir 3 poin: halftime total 142 (Q2 78 poin),
tripoin 21-41 (51%), proyeksi live 284. Pra-laga, mesin sudah menandai DEN
sebagai kaki terlemah Asuransi (P 84,5%, edge +2,5% terkecil; gap
model-vs-pasar −3,5 vs −7,5 s.d. −8,5 di kaki lain) — tapi kaki itu lolos
semua gate. Gemini mengakui salah memasukkan DEN (sudah dilabeli KUNING,
harusnya skip) karena tidak punya mesin rigid. Pelajaran yang
diterjemahkan ke kode ada di §6.

Koreksi aritmetika (ditemukan saat membangun item 2): proyeksi halftime
284 vs median sim 233 adalah deviasi **+51**, bukan +28. Angka +28 adalah
proyeksi 261,2 yang lebih awal.

## 1. Audit tiket sebelum pasang (BARU)

**File:** `engine/ticket_audit.py` (baru) + `tests/test_ticket_audit.py`
(30 tes) + subperintah `cli.py audit`.

```
python3 cli.py audit --ticket <file-tiket> --analysis <artefak>... [--output <file>]
```

Masukan: file tiket (format apa pun yang dipakai `pantau`) + satu atau
lebih artefak analisis. Keluaran per kaki: P_model dari sim markets,
harga, edge, volume ladder + thin?, evaluasi lean-to-market, hasil tiap
gate (min_leg_prob, lantai harga 75¢, volume), verdict LOLOS / PERHATIAN /
JANGAN_PASANG + alasan bahasa Indonesia sederhana. Per tiket: kaki
terlemah, peluang gabungan, EV dengan pengali riil, verdict GO / NO-GO.
File tiket asli tidak diubah; hasil ditulis ke `out/`. Exit code: 0 GO,
1 NO-GO, 2 tidak bisa jalan.

**Peringatan penting yang ditegakkan kode:** `p_model` di file tiket nyata
adalah angka Gemini, BUKAN angka mesin. Audit mengabaikannya untuk verdict
(hanya ditampilkan dengan label "angka Gemini, bukan mesin") dan selalu
menghitung dari sim markets artefak. Bila satu laga muncul di dua artefak,
dipakai yang terbaru (`generated_at`) — selaras dengan peracik.

**Kasus uji wajib — tiket nyata 23 Nov** (perintah di atas dengan kedua
artefak; output `out/audit_tickets_real_2026-11-23.json`):

| Tiket | Verdict | Peluang gabungan | EV |
|---|---|---|---|
| Asuransi (2,17x) | **NO-GO** | 58,0% | +25,9% |
| Utama (3,72x) | GO + 5 peringatan | 34,8% | +29,3% |

- **DEN Asuransi U252,5: JANGAN_PASANG** — P 84,5%, edge +2,5%, thin
  (vol $26,25). Alasan: volume tipis + edge tipis. ✓
- **DEN Utama U250,5: PERHATIAN** — P 81,8%, edge +2,8%, thin ($6,45). ✓
- **ORL Utama U235,5: PERHATIAN + OVERPAY** — P 78,3%, edge **−4,7%**,
  EV −5,6%, label MAHAL. ✓
- Satu-satunya kaki LOLOS: OKC Utama U238,5 (P 82,8%, edge +6,8%,
  tidak thin).

Angka agregat persis sama dengan audit manual pra-laga (58,0%/+25,9% dan
34,8%/+29,3%) — validasi independen aturan dedup terbaru-menang.

**Temuan di luar kasus wajib:** keempat kaki Asuransi JANGAN_PASANG
karena volume tipis (OKC $22,63; DAL tidak tercatat; BOS $9,05; DEN
$26,25). Dengan kata lain, audit mesin akan NO-GO-kan seluruh Tiket
Asuransi tadi pagi hanya karena volume — garis-garis jauh (alt) memang
tipis di Polymarket. Apakah ambang $100 terlalu ketat untuk garis alt
adalah pertanyaan terbuka untuk reviewer (§6.7).

## 2. Skenario panas (BARU)

**File:** `engine/stress.py` (baru) + `tests/test_stress.py` (29 tes) +
bagian baru "Skenario panas" di `report/nba_report.py` (2 tes laporan)
+ bagian `stress` di `config/playstyle.yaml`.

**Desain (dipilih worker, disetujui koordinator):** modul baru yang
**menggeser CDF total yang sudah tersimpan di artefak**
(P_skenario(Under L) = CDF_normal(L − geser), interpolasi linear antar
garis, dijepit di ujung tanpa ekstrapolasi) — BUKAN simulasi ulang
100.000x, BUKAN perluasan `nba_sim.py`. Alasan: definisi skenario
konservatif memang pergeseran distribusi; murah dan deterministik
(laporan bisa menghitung langsung); mudah diuji. Keterbatasan yang
didokumentasikan: banjir hanya menggeser rata-rata, varians dianggap
tetap.

**Parameter banjir — diturunkan dari data, bukan INITIAL.** Satu panggilan
keyless stats.nba.com `leaguegamefinder` musim 2026-27 (n=247 laga,
20 Okt–22 Nov 2026; skrip derivasi `/tmp/turunkan_banjir.py`):

| Parameter | Derivasi | Nilai |
|---|---|---|
| `banjir_3p_points` | (p90 − rerata 3PM gabungan/laga) × kemiringan OLS total/3PM = (33,00 − 26,62) × 2,12 | **13,54** |
| `banjir_ft_points` | (p90 − rerata FTM gabungan/laga) × kemiringan OLS total/FTM = (52,00 − 37,79) × 1,23 | **17,54** |

Kemiringan 3PM 2,12 (bukan 3,0) karena tembakan tiga tambahan sebagian
menggantikan tembakan dua angka; kemiringan bersifat asosiatif (ikut
menangkap pace/OT) — didokumentasikan sebagai caveat. Validasi silang:
game log memberi DEN 10,53 dan CHI 13,00 tripoin/laga (vs BBRef 10,6 /
12,9 ✓). Skenario konservatif: geser = garis market − median sim,
sigma sama, tanpa kunci config baru.

**Jangkar insiden:** 21 tripoin di halftime (laju 42/laga) berada DI ATAS
maks musim (40; z +2,89, di atas p99) — banjir p90 TIDAK mencakup
insiden separah DEN@CHI. Garis tahan-banjir menjawab "tahan banjir
1-dari-10", bukan "tahan banjir separah insiden". Ini ditulis eksplisit
di laporan.

**Kasus uji wajib — DEN@CHI** (output
`out/stress_den_chi_2026-11-22.json`; median 233, market 236,5):

| Kaki | Normal | Banjir 3P | Banjir FT | Konservatif | Tahan banjir? | Garis tahan-banjir |
|---|---|---|---|---|---|---|
| Asuransi U252,5 @82¢ (target 74%) | 84,5% | 62,4% | **54,3%** | 79,7% | **TIDAK** | **264,5 @94,0¢** (jup ~94,5¢), thin — 12 poin di atas 252,5 ✓ |
| Utama U250,5 @79¢ (target 65%) | 81,8% | 58,3% | **49,3%** | 76,7% | **TIDAK** | **258,5 @88,5¢** (jup ~89,0¢), thin — 8 poin di atas 250,5 |

Jawaban pertanyaan user: **di 82¢ TIDAK tembus kalau panas** (peluang
Under tinggal 54,3% di banjir terburuk); **di 94¢ TEMBUS di skenario
banjir p90** (76,6% ≥ 74% — tapi garisnya thin/volume tidak tercatat,
dan tetap di bawah laju insiden 284). Semua angka diverifikasi hitung
tangan dari CDF artefak oleh worker dan dicek ulang koordinator dari
file output.

**Integrasi laporan:** bagian "Skenario panas" membaca
`analysis["stress"]` bila ada, bila tidak menghitung otomatis lewat
`engine/stress.py` (tanpa fetch, tanpa simulasi ulang, tanpa Odds API)
— sehingga langsung hidup untuk semua artefak lama. Bila tidak bisa
dihitung, alasannya ditulis, bukan crash.

## 3. Edge jadi gate (BARU)

**File:** `engine/ticket_composer.py` + `tests/test_ticket_composer.py`
(7 tes baru, kelas `TestGateEdgeAsuransi`) + kunci config
`tickets.insurance.min_edge_pct`.

**Usulan ambang: +3,5% (PROPOSAL, pola D12 — menunggu persetujuan
user, bukan keputusan final).** Dasar data: kaki DEN yang jebol edge
+2,5%; kaki Asuransi selamat terendah OKC +4,4% (lainnya +6,2%, +9,1%).
Ambang 3,5% = pembulatan titik tengah (2,5+4,4)/2 = 3,45%. Alternatif
+4,0% ditolak dengan alasan terukur: kaki Asuransi standar yang baik
(p_final 0,786 @75¢, edge +3,6%) akan ikut ditolak.

Gate aktif sebagai hard gate Asuransi (seperti thin), di `_kumpulkan_
kandidat` setelah cek `min_leg_prob`; alasan penolakan tercatat dengan
token `edge_kecil` + nilainya dan muncul di ringkasan "KAKI YANG TIDAK
LOLOS". Utama tidak kena gate ini. Definisi edge: `p_final − harga/100`
— selaras dengan definisi yang sudah dipakai composer (bukan
probabilitas keputusan; lihat §6.2). Fallback default 3,5% bila kunci
hilang (pola lantai harga/yakin), sumber dicatat di ringkasan.

## 4. Fondasi baru (config v14)

**File:** `config/playstyle.yaml` (version 13 → 14) +
`tests/test_config.py` + `tests/test_ticket_composer.py`.

| Kunci | Lama | Baru |
|---|---|---|
| Asuransi `multiplier_min` / `multiplier_max` | 2,5 / 3,0 | **2,0 / 2,5** |
| Utama `target_multiplier_max` (lunak) | 4,0 | **3,5** |
| Utama `multiplier_max` | 5,0 | 5,0 (tetap) |
| Utama `yakin_min_leg_prob` | 0,75 | 0,75 (tetap) |
| `must_cover_total_stake` | true | true (tetap — 2,0 × $10 = $20 = total modal, pas) |
| Price floor | 75¢ | 75¢ (tetap) |
| Price cap | — (pertanyaan terbuka) | **tidak ditambahkan** (keputusan: tanpa cap) |

Komentar filosofi lama (x2,5 sebagai keharusan) diganti fondasi baru
+ tanggal keputusan (2026-11-23). 16 perubahan tes yang mengunci
target lama, semua didokumentasi di komentar tes dengan tanggal
keputusan (bukan dilonggarkan diam-diam) — termasuk: Asuransi standar
kini 3 kaki @75¢ = 2,24 (4 kaki = 2,99 di atas maks baru); tes EV
negatif pindah ke Utama karena Asuransi ber-EV negatif kini tidak
mungkin (tiap kaki lolos gate edge punya faktor EV ≥ 1,035);
`test_tanpa_recheck_*` memakai kaki Utama @78¢ karena 5 kaki @75¢ =
3,98 kini di atas lunak 3,5 dan butuh "yakin" yang mustahil tanpa
recheck. `report/nba_report.py` ternyata tidak mengandung teks target
pengali apa pun (dicek dengan grep menyeluruh) — tidak ada yang perlu
diselaraskan di sana.

## 5. Proyeksi live pakai median pra-laga

**File:** `cli.py` (pantau `--analysis` jadi `nargs="+"`) +
`tests/test_pantau_blend.py` (18 tes) + pembantu bersama di
`engine/ticket_audit.py` (`kumpulkan_analisis`, `median_pra_laga`,
`terbaru_per_laga`).

**Desain (dipilih worker, disetujui koordinator):** `--analysis` pantau
diperluas ke banyak file (pola sama seperti `racik`), bukan mekanisme
tautan baru. Median diambil per laga dari artefak (terbaru menang bila
satu laga muncul di dua artefak); laga tanpa median tetap
live-rate-only + dicatat. `cmd_pantau` tetap menerima string tunggal
(kompatibel pemanggil lama). JSON pantau kini mencatat
`projection_method` + `pregame_median_total` per laga di bagian
`matches`.

**Bukti replay (dua jalur):**
- (a) Pantau live tiket nyata 23 Nov dengan kedua artefak terlampir
  (`out/pantau_blend_2026-11-23.json`): 4 laga tengah-laga memakai
  method **blend** — DEN 266,74 (median 233), DAL 215,31 (median 217),
  ORL 235,51 (median 220), IND 208,0 (median 208); OKC `final` (236);
  BOS belum mulai (median 203 tercatat). Semua 6 laga punya median,
  `missing_matches` kosong.
- (b) Replay fixture (keadaan live tengah-laga sintetis + median asli
  artefak, `out/pantau_blend_fixture_2026-11-23.json`): ke-6 laga
  method `blend`, proyeksi berbeda dari `live_rate_only` — DEN
  halftime 142: blend **271,25 vs 284,00** (−12,75); OKC 271,35 vs
  278,71; DAL 243,89 vs 247,74; ORL 249,68 vs 253,94; IND 229,22 vs
  232,26; BOS 239,42 vs 244,65.

## 6. Keputusan desain & pertanyaan yang menunggu keberatan / keputusan

1. **Ambang edge 3,5%** — proposal D12, menunggu persetujuan user (§3).
2. **Edge gate memakai p_final, bukan probabilitas keputusan** — di
   bawah condong-ke-market, kaki dinilai peluangnya dari harga market
   tapi edge-nya tetap dari p_final. Konsisten dengan `_rakit_tiket`,
   tapi perlu keberatan bila reviewer ingin edge dari probabilitas
   keputusan. Terkait: angka insiden memakai edge P_model, gate memakai
   edge p_final — pemindahan ambang antar-definisi ini menunggu
   validasi atas data PAPER.
3. **Gate edge tidak dikaitkan ke audit** (keputusan koordinator):
   audit memakai edge P_model (tidak punya blend p_market), gate
   memakai edge p_final — keduanya sengaja tidak disamakan. Audit
   tetap menandai edge tipis (< 5 poin, `audit.edge_tipis_pct`,
   NILAI AWAL menunggu kalibrasi + persetujuan user) sebagai
   PERHATIAN, sehingga kaki kelas DEN tetap ketangkep di audit.
4. **Persentil p90** ("1 dari 10 laga") sebagai definisi banjir —
   pilihan desain. p95 akan memberi geser 3P 17,79 / FT 21,25 dan
   membuat DEN tidak punya garis tahan-banjir sama sekali (garis yang
   dibutuhkan 266,7 > ujung tangga 266,5).
5. **Garis thin TIDAK dikeluarkan** dari pencarian garis tahan-banjir
   (pertanyaannya soal garis, bukan eksekusi) — tapi thin + volume
   selalu dilaporkan; kedua garis tahan-banjir DEN thin.
6. **Geser banjir adalah angka liga**, bukan per-matchup (simpangan
   baku 3PM per tim nyaris sama di semua tim — alasan kuantitatif di
   docstring modul). Per-matchup butuh rerata 3PM/FTM per tim di
   artefak inputs (belum ada).
7. **Ambang volume $100 untuk garis alt** — keempat kaki Asuransi
   nyata 23 Nov thin (§1). Apakah ambang ini terlalu ketat untuk
   garis jauh adalah pertanyaan terbuka.
8. **Verdict audit:** NO-GO hanya bila ada kaki JANGAN_PASANG /
   DATA_INCOMPLETE; kaki PERHATIAN → GO + peringatan eksplisit
   (selaras composer). MAHAL (EV < −2%) → JANGAN_PASANG di Asuransi,
   PERHATIAN di Utama. Tangga tidak ditemukan → Asuransi
   JANGAN_PASANG (fail-closed), Utama PERHATIAN. Lean-to-market di
   Utama hanya dicatat; PERHATIAN bila probabilitas pasar < ambang
   Utama.
9. **Mode gagal berbeda sengaja:** audit batal (exit 2) bila satu file
   analisis rusak; pantau melewati file rusak dan lanjut.
10. **Gate edge ditempatkan setelah cek min_leg_prob** — kaki yang
    gagal di kedua gate tercatat dengan alasan peluang minimum, bukan
    edge (alasan paling dasar didahulukan).

## 7. Keputusan koordinator saat integrasi

- **`"stress"` ditambahkan ke `REQUIRED_PLAYSTYLE_SECTIONS`** di
  `config.py` (fail-closed saat load; rekomendasi worker B). Tanpa
  ini, config tanpa `stress` baru gagal saat `skenario_panas`
  dipanggil.
- **Ambang edge tipis audit dipindah ke config** (`audit.edge_tipis_pct:
  5.0`, NILAI AWAL + dokumentasi kalibrasi) — nilai awalnya sempat
  hardcoded di modul, melanggar aturan "semua threshold hanya di
  config". Fallback default 5% bila kunci hilang, sumber dicatat di
  output audit. 2 tes baru mengunci perilaku ini. Bagian `audit`
  sengaja TIDAK masuk required sections (ada fallback default —
  berbeda dengan `stress` yang tidak punya fallback).
- **Wiring `nba_analysis.py` (artefak membawa kunci `stress`)
  DITUNDA** — laporan sudah menghitung otomatis bila kunci tidak ada,
  sehingga nilai tambah wiring hanya provenans + menghindari hitung
  ulang. Dicatat sebagai utang (§8).
- **Tes bagian laporan ditambahkan koordinator** (2 tes,
  `TestSkenarioPanas`): worker B hanya melakukan uji asap manual.
  Angka ekspektasi dihitung tangan dari CDF fixture dan cocok persis
  (mis. Under 233,5 banjir 3P 51,8%, konservatif 65,0%).

## 8. Utang & batasan jujur

- Wiring `nba_analysis.py` agar artefak mendatang membawa kunci
  `"stress"` (laporan menghitung otomatis sampai itu ada; kaki nyata
  di luar kaki artefak hanya tercakup bila dilewatkan eksplisit).
- Banjir hanya menggeser rata-rata; varians dianggap tetap (banjir
  nyata mungkin juga melebarkan sebaran — tidak dimodelkan).
- Garis tahan-banjir p90 tidak menjamin tahan banjir separah DEN@CHI
  (di atas p99). Tidak ada garis di tangga DEN yang tahan banjir
  separah itu.
- Audit memakai peluang gabungan produk P_model (asumsi independen,
  sama seperti peracik) — korelasi antar laga tidak dimodelkan.
- `p_total_loss` masih null; audit tidak menghitungnya.
- Data DAL/ORL/IND di kasus uji berasal dari artefak 22 Nov (basi
  dibanding sim 04:58 untuk OKC/DEN/BOS) — audit memakai apa adanya
  dan mencatat stempel waktunya; kesegaran data tetap tanggung jawab
  alur analisis, bukan audit.
- Analisis masih lambat (~3,5 menit/laga, didominasi pemindaian
  jup.ag) — tidak disentuh perbaikan ini.

## 9. Cara pakai besok pagi (slate Selasa 24 Nov, 10 laga)

```bash
export PATH="$HOME/.venvs/parlay-tools/bin:$PATH"
# 1. Analisis slate seperti biasa (cli.py analyze)
# 2. Racik seperti biasa (cli.py racik) — target baru x2,0–2,5 / x3,0–3,5
#    lunak, gate edge Asuransi +3,5% (proposal) aktif
# 3. Audit tiket apa pun SEBELUM pasang (tiket mesin, tiket Gemini,
#    tiket rakitan tangan):
python3 cli.py audit --ticket <tiket.json> --analysis <artefak>... --output out/audit_<tanggal>.json
# 4. Laporan per laga kini memuat bagian "Skenario panas" (garis
#    tahan-banjir + cek harga 82¢/94¢)
# 5. Pantau tiket nyata dengan median pra-laga (blend):
python3 cli.py pantau --ticket <tiket.json> --analysis <artefak>... --output out/pantau_<tanggal>.json
```

## 10. File yang berubah

Baru: `engine/ticket_audit.py`, `engine/stress.py`,
`tests/test_ticket_audit.py`, `tests/test_stress.py`,
`tests/test_pantau_blend.py`.
Diubah: `cli.py` (subperintah audit + pantau multi `--analysis`),
`config.py` (`"stress"` di required sections),
`config/playstyle.yaml` (v14: target baru + `min_edge_pct` 3,5 +
bagian `stress` + bagian `audit`),
`engine/ticket_composer.py` (gate edge + teks target lunak),
`report/nba_report.py` (bagian "Skenario panas"),
`tests/test_ticket_composer.py`, `tests/test_config.py`,
`tests/test_report_nba.py`, `DECISIONS.md` (fondasi harga & pengali
2026-11-23, ditulis sebelum build ini).
Bukti di `out/` (gitignored): `audit_tickets_real_2026-11-23.json`,
`stress_den_chi_2026-11-22.json`, `pantau_blend_2026-11-23.json`,
`pantau_blend_fixture_2026-11-23.json`.

## 11. Verifikasi koordinator (dari disk, bukan dari laporan worker)

- Full suite 1.479 lulus sebelum 2 tes laporan koordinator; total
  1.481 (hook pre-commit menjalankan ulang full suite saat commit).
- Ruff + black bersih (153 file).
- Audit CLI dijalankan ulang koordinator: verdict sama (Asuransi
  NO-GO, Utama GO), exit 1, ambang edge tipis terbaca dari config
  (5,0, sumber "config audit.edge_tipis_pct").
- Angka stress DEN dicek dari file output (bukan dari narasi worker);
  angka laporan fixture dihitung tangan dan cocok persis.
- Angka audit agregat (58,0% / 34,8%) cocok dengan audit manual
  pra-laga di memori.
- Config v14 + bagian `stress` + bagian `audit` hidup berdampingan;
  tidak ada edit worker yang saling menimpa (dicek lewat diff).
