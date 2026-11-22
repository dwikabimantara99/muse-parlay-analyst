# LAPORAN TAHAP 3 LANGKAH 2 — Cek Ulang Pra-Submit

Tanggal: 2026-11-22. Repo `muse-parlay-analyst`, branch `main`.
Suite: **849 tes, semua lulus** (dari 707 di langkah 1b). Config v8.
Kredit Odds API yang dipakai langkah ini: **0**.

## 1. Ringkasan

Langkah 2 membangun **cek ulang pra-submit** — pemeriksaan terakhir
sebelum user memasang tiket, karena tiket parlay tidak bisa dibatalkan.
Dua hal besar dibangun:

1. **Penyambungan Otak NBA ke `cli.py analyze`** — analyze kini
   menghasilkan artefak analisis per laga (proyeksi, simulasi 100.000x,
   garis Asuransi/Utama, harga, cedera) yang bisa diverifikasi recheck.
2. **Mesin recheck (`cli.py recheck`)** — ambil data segar, bandingkan
   dengan analisis awal, hitung ulang simulasi bila ada perubahan
   material, dan putuskan GO / NO-GO per kaki dan per tiket.

Lingkup langkah 2 diperluas atas keputusan user (20:41 WIB): patch 1c
yang direncanakan **dilebur** ke langkah ini. Kelima aturan baru —
rolling, ketersediaan rest/personal, shrinkage musim lalu, spread+12,
condong-ke-market — **semuanya terpasang dan teruji** (rincian §5).

Hasil verifikasi live (DET@ATL, 22 Nov, §8): recheck memberi putusan
**NO-GO** — kaki Asuransi ditolak aturan condong-ke-market (harga market
68% < 74%), kaki Utama TETAP_OK. Recheck bekerja sebagai penjaga, bukan
stempel.

## 2. Apa yang dibangun

| Bagian | File | Isi |
|---|---|---|
| Artefak analisis | `engine/nba_analysis.py` (baru, 994 baris) + `schemas/nba_analysis.schema.json` | `build_nba_analysis()` — sim 2 tahap (tahap 1 cari median, tahap 2 sim semua garis Under tangga), garis dari `cushion.py`, harga tangga Polymarket + estimasi jup.ag, p_market Kalshi/Odds API + blend w=0,3, label harga, cedera 2 sumber, snapshot harga pertama |
| Wiring analyze | `cli.py` (+`_lampirkan_nba_analysis`), `ingest/slate.py` | Analyze melampirkan artefak `nba_analysis` per laga NBA; flag baru `--tanpa-odds-api` (0 kredit) |
| Mesin recheck | `engine/recheck.py` (baru, 1.598 baris) + `schemas/recheck.schema.json` | `fetch_fresh`, `compare_injuries`, `compare_prices`, `needs_resim`, `decide`, `_resim_default` (sim nyata satu kali dengan semua garis tangga) |
| CLI recheck | `cli.py` (`cmd_recheck`, `_ambil_nba_analysis`) | `cli.py recheck --analysis <file> [--match <id>] [--out <file>]`; exit 0 = GO, 1 = NO-GO (laporan tetap ditulis), 2 = tidak bisa jalan |
| Ketersediaan | `ingest/nba_brain.py` (`_merge_injuries`) | OUT apapun alasan → absen, alasan tercatat |
| Shrinkage | `ingest/nba_brain.py` + `ingest/bbref.py` (`games_played`) | Menit + BPM menyusut ke musim lalu; sim hanya mencatat alasan absen di notes (`engine/nba_sim.py`, rumus tidak berubah) |
| Config | `config/playstyle.yaml` v8, `config.py` | Bagian `recheck:` baru; nilai rolling (v7); `simulation.nba.shrinkage_k_games: 10` (v8) |

Tes baru: 142 (31 nba_analysis + 68 recheck + 12 CLI recheck + 26
ketersediaan/shrinkage + 2 fixture istirahat mendadak + 3 config/CLI).
Semua offline kecuali verifikasi live §8.

## 3. Format artefak

### 3a. Artefak analisis (`nba_analysis`, format_version 1)

Satu JSON per laga. Kunci utama: `format`, `match_id`
(`{AWAY}@{HOME}_{YYYY-MM-DD}`), tricode kandang/tandang, `game_date`
(Eastern), `start_time`, `generated_at`, `status`
(OK | HOLD | DATA_INCOMPLETE), `missing`, `sources`, `inputs` (mentah
dari `fetch_match_inputs`), `simulation` (mentah dari `nba_sim`,
100.000 iterasi: median, p74, peluang OT, semua pasar dari satu sim),
`market` (slug, garis total utama = garis bervolume terbesar, tangga
totals + spreads apa adanya, moneyline jup.ag), `legs` (Alt Under saja:
Asuransi + Utama — tiap kaki membawa `leg_id`, garis, p_model,
p_market + `comparison_source`, p_final, harga ¢, estimasi jup.ag,
EV, label DISKON/WAJAR/MAHAL, bantalan vs median/market, `meets`,
`reason`, `fetched_at`), `injuries` (sumber, jumlah sumber,
`confirmed_both`, entri, konflik), `anomalies`, `price_snapshots`
(harga pertama tiap garis, basis jup_estimated_cents — baseline
aturan Thunder).

Status: OK = sim + tangga + cedera 2 sumber lengkap; HOLD = B2 gagal
ATAU kaki Asuransi tidak meets; DATA_INCOMPLETE = fetch/sim gagal.
Kaki yang tidak meets tetap dicatat dengan `line: null`.

### 3b. Laporan recheck (`nba_recheck`, format_version 1)

`match_id`, `analysis_generated_at`, `recheck_at`, `verdict` (GO |
NO-GO), `resimulated`, `resim_reasons`, `changes` (jenis:
injury | price | market_line | stale | fetch_error + detail),
`legs` (tiap kaki: `leg_id`, `verdict` TETAP_OK | PERHATIAN |
JANGAN_PASANG | DATA_INCOMPLETE, `reasons`, garis/harga lama-baru,
`price_move_cents`, `resimulated`, `probability_used` model/market,
`probability_value`, `kenapa_beda`), `anomalies`, `missing`,
`attention`, `action_required` (mis. "ganti garis ke 235.5").

Catatan: kaki laporan recheck belum membawa kunci `ticket` (kontrak
langkah 2 tidak memintanya; `leg_id` sudah mengidentifikasinya, dan
CLI membaca tiket dari akhir `leg_id`). Pertimbangkan menambahkannya
di langkah 3 bila peracik tiket membutuhkannya.

## 4. Aturan putusan + ambang

Semua ambang di `config/playstyle.yaml` (tidak ada angka di kode).

| Pemicu | Ambang (config) | Akibat |
|---|---|---|
| Cedera inti baru OUT/DOUBTFUL, atau status berubah | — (perubahan apa pun) | Resim + hitung ulang garis |
| Garis market bergerak | `recheck.market_line_move_points` = 2,0 poin | Resim (tepat 2,0 tidak resim; 2,5 resim) |
| Harga bergerak | `anomaly.sharp_move_cents` = 3¢ (aturan Thunder) | Resim + ANOMALI; <1¢ = noise, 1–2¢ = PERHATIAN |
| Data cedera basi | `data.stale_hours_injury_lineup` = 3 jam | Ambil ulang; gagal + basi → DATA_INCOMPLETE |
| Selisih median vs garis market | `market_line_check.total_gap_points` = 5,0 | Pemicu aturan condong-ke-market (§5.5) |
| Bantalan Asuransi | target peluang 0,74 + lantai market +8 | Garis dari persentil ke-74 sim |
| Bantalan Utama | +8, atau +12 bila spread ≤ 2,5 atau tidak diketahui | `filters.nba_alt_under` |

Prioritas putusan (tertinggi dulu): analisis DATA_INCOMPLETE/HOLD →
tangga gagal → basi + fetch gagal → meets False → garis hilang →
sharp ≥3¢ → resim gagal → resim tidak meets → garis berubah →
condong-ke-market.

Keputusan desain (koordinator, menunggu objeksi reviewer):
- **HOLD → JANGAN_PASANG** — HOLD berarti belum siap masuk tiket.
- **Resim + garis berubah → JANGAN_PASANG garis lama** +
  `action_required` "ganti garis ke X" (NO-GO = jangan submit sesuai
  rencana awal). Resim + garis tetap → PERHATIAN.
- **Fetch cedera gagal + data masih segar (≤3 jam) → tetap bisa GO**
  + `fetch_error` tercatat; basi atau umur tak diketahui →
  DATA_INCOMPLETE.
- **Pemain kembali dari cedera (resolved) TIDAK memicu resim**
  (di luar daftar pemicu yang disepakati) tapi dicatat di `changes`.
- **Garis hilang → langsung JANGAN_PASANG** tanpa resim.
- **Moneyline jup.ag tidak dicek** — repo tidak punya fetcher
  moneyline jup.ag per-event (hanya pemindaian penuh); `moneyline_jup`
  None + `errors`, TIDAK menggagalkan recheck.
- **Recheck membawa `p_market` kaki lama** — tidak ada pembanding
  baru (0 kredit Odds API); pembanding segar di luar lingkup langkah 2.

## 5. Lima aturan baru — status masing-masing (syarat laporan #1)

| # | Aturan | Status | Bukti |
|---|---|---|---|
| 1 | **Adopsi nilai rolling** | ✅ Terpasang + teruji | playstyle.yaml v7: sigma_total 18,9868; sigma_margin 14,4307; home 1,6639; B2B −1,5164; t_nu 35,0. Altitude tetap −0,0105 (rolling −0,399 = noise). Contoh diregenerasi: std 18,78→19,44; p74 231→232; ML kandang 59,2%→59,1%; OT 2,9%→2,7%; median/total tidak berubah. Garis Asuransi tetap 233,5 (lantai market mengikat). |
| 2 | **Ketersediaan rest/personal** | ✅ Terpasang + teruji | `ingest/nba_brain.py`: entri gabungan membawa `is_injury`, `reason`, `availability_n_sources`. OUT non-cedera (rest/personal/skors/two-way/G League) MASUK daftar absen; non-OUT non-cedera tetap dikecualikan. Rest 1 sumber → absen + catatan `availability_1_sumber:<pemain>`. B2 tidak berubah untuk klaim cedera. Kasus campuran PDF-cedera/ESPN-rest → `is_injury=True`, alasan detail PDF, masuk `confirmed_both` (keputusan koordinator, menunggu objeksi reviewer). 7 tes ketersediaan. |
| 3 | **Shrinkage menit+BPM ke musim lalu** | ✅ Terpasang + teruji | Rumus w = n/(n+K), K=10 (`simulation.nba.shrinkage_k_games`, config v8) — PILIHAN DESAIN mengikuti K=10 D-R2, bukan hasil fit. Berlaku untuk menit DAN BPM; rookie/tanpa musim lalu → nilai musim berjalan + catatan. Fetch musim lalu 1 request BBRef (best-effort, gagal → nilai musim berjalan). 15 tes shrinkage + 1 bbref + 3 sim. Contoh Duren (2 laga): mp 19,0→26,69; BPM 8,8→5,63 (musim lalu mp 28,23, BPM 5,0; w=1/6). |
| 4 | **Spread dari market + fallback +12** | ✅ Terpasang + teruji | Spread = \|garis spread bervolume terbesar\| dari tangga Polymarket (di `nba_analysis` dan di `_resim_default` recheck); unknown → bantalan Utama +12 (sebelumnya +8). Menggantikan keputusan desain 1b "spread=None → bantalan 8". Tes: spread 5,5 → garis +8; spread 2,0 / None → +12. Live DET@ATL: spread tidak diketahui → kaki Utama 237,5 (bukan 233,5). |
| 5 | **Condong-ke-market** | ✅ Terpasang + teruji | Di `decide()`: pemicu \|median − garis market\| > 5,0; "Kenapa beda?" mekanis hanya alasan (a) — cedera baru OUT/DOUBTFUL + market belum menghargainya (garis tidak bergerak searah median, atau < 1 poin); tanpa alasan → kaki Asuransi pakai probabilitas market (harga tangga segar `price_cents`/100, fallback `mid_cents`); < 0,74 → JANGAN_PASANG; Utama selalu probabilitas model. Fixture DET@ATL (median 219 vs 225,5, harga 66,5¢ → 0,665 < 0,74 → JANGAN_PASANG + NO-GO) + varian alasan-konkret (model dipakai + PERHATIAN + GO). |

## 6. Bukti: recheck menangkap kabar istirahat mendadak (syarat laporan #2)

Fixture end-to-end `TestIstirahatMendadak` di `tests/test_recheck.py`
(offline, sim NYATA 20.000 iterasi — bukan stub resim):

- **Skenario**: analisis awal 21:30 UTC — Cade Cunningham tersedia,
  median 224, garis market 225,5, kedua kaki di 233,5. Recheck
  23:45 UTC — **45 menit sebelum tip-off** (00:30 UTC) — menemukan
  Cade OUT karena Rest (entri persis bentuk hasil lapisan
  ketersediaan dari ESPN "(rest)"). Harga + garis market DIAM — kabar
  istirahat adalah satu-satunya perubahan.
- **Hasil**: resim dipicu (`resimulated: true`, alasan `cedera_baru`);
  `changes` mencatat cedera "Cade Cunningham"; median sim turun
  ~5,67 poin (dampak absen Cade: (6,0−(−2,0)) × 34/48) melewati ambang
  selisih 5,0 — TAPI kabar Rest itu sendiri adalah alasan konkret
  aturan condong-ke-market (market diam), jadi probabilitas model
  tetap dipakai (`probability_used: model`,
  `kenapa_beda.reason_found: true`).
- **Putusan**: kedua kaki berubah TETAP_OK → **PERHATIAN** (garis
  tidak berubah — lantai market 233,5 mengikat), tiket GO dengan
  `attention` terisi. Alasan tercatat di sim:
  `pemain OUT: Cade Cunningham (alasan: rest)`.
- Tes diulang 3× — stabil.

Ini membuktikan rantai lengkap: kabar Rest → lapisan ketersediaan →
deteksi recheck → resim → putusan berubah + alasan tercatat.

## 7. Hasil probe DunkAPI (syarat laporan #3)

Probe TANPA signup (docs publik + katalog tools
`mcp.dunkapi.com/v1/tools` yang bisa dibaca tanpa key, diverifikasi
2026-11-22 13:43 UTC):

- **(a) Musim tercakup**: odds NBA 2013-14 s.d. sekarang.
- **(b) Closing atau opening? KEDUANYA** — `total_close` per
  sportsbook tersedia sejak Juli 2020 (2020-21 ke atas); contoh:
  BetMGM total_open 235,5 / total_close 233,5. Musim 2013-14–2019-20
  hanya garis final pra-laga (disimpan sebagai close).
- **Kesimpulan**: syarat "jangan dipakai bila hanya opening" TIDAK
  terpicu — **DunkAPI BISA dipakai untuk uji model-vs-market dengan
  garis penutupan**.
- **Biaya**: 500 kredit gratis/bulan, tanpa kartu. `get_odds`
  5 kredit/laga atau 10 kredit/hari. Uji historis 150 laga ≈ 15
  hari-laga × 10 = **~150 kredit** (rute per-hari; rute per-laga
  750 kredit, lewat batas gratis).
- **Catatan**: garis pra-Juli-2020 adalah tangkapan tunggal (proksi
  closing); feed harian sejak 2024-25 hanya 1–2 sportsbook/laga
  (sisanya dari arsip); beberapa field bisa null.
- **Signup (API key) butuh persetujuan user** — belum dilakukan.
  Menjalankan uji historis nyata menunggu persetujuan itu.

## 8. Verifikasi live: DET@ATL 2026-11-22

Dua putaran analyze + recheck pada laga nyata (tip-off 03:30 WIB
23 Nov), keduanya `--tanpa-odds-api` (0 kredit). Putaran pertama
13:53 UTC (kode W5 sudah di tree, kunci config masih default);
putaran kedua ~14:20 UTC (config v8 final). Hasil putaran kedua:

**Analyze** (205 dtk — pemindaian penuh jup.ag yang lambat):
1 laga OK, `nba_analysis: OK`. Median 219, p74 232, rata-rata 218,68,
peluang OT 2,74%, ML kandang 54,0%. Garis market 225,5 (vol $44.048).
Cedera 2 sumber (ESPN + PDF resmi), 9 terkonfirmasi dua sumber —
B2 terpenuhi live. Kaki Asuransi U233,5: p_model 0,772, p_market
0,68 (Kalshi), p_final 0,708, harga 68,0¢, EV +3,30% DISKON.
Kaki Utama U237,5: p_model 0,830, p_market 0,755, EV +2,29% DISKON.
3 anomali tercatat (selisih median-garis 6,5; model-vs-market 8,97).

**Recheck** (8,4 dtk): **NO-GO, tanpa resim** (tidak ada perubahan
material sejak analyze). Asuransi U233,5: **JANGAN_PASANG** — aturan
condong-ke-market: selisih 6,5 > 5,0, tanpa alasan konkret →
probabilitas market 68% < 74%. Utama U237,5: **TETAP_OK** (probabilitas
model 0,830). `action_required`: "cari garis Asuransi lain — harga
market garis 233.5 di bawah ambang Asuransi". Exit code 1.
Putusan NO-GO konsisten di kedua putaran (putaran pertama: harga
market 68,5%).

**Dampak shrinkage, diukur dari data live** (contoh diregenerasi
dengan kode final, seed 7 — proyeksinya identik dengan analyze live):
- Duren: mp 19,0→26,69; BPM 8,8→5,63. Dampak absen Duren 4,28→4,24
  poin — **efek neto −0,04 poin, bisa diabaikan**: dua kesalahan
  (menit understated, BPM inflated) hampir persis saling
  meniadakan, seperti dugaan auditor.
- Tapi shrinkage **TIDAK netral secara keseluruhan**: margin
  proyeksi 3,19→1,55 (bergeser 1,64 poin ke arah DET) dan ML kandang
  59,1%→54,0% — karena BANYAK pemain menyusut (cth. Jalen Johnson
  BPM 1,3→2,56; Dyson Daniels 2,9→2,28; RayJ Dennis 3,8→−3,20;
  Paul Reed 1,0→2,72). Total hampir tidak berubah (218,75→218,68;
  median tetap 219). Apakah pergeseran margin ini perbaikan atau
  bukan masih **UNKNOWN** — hanya uji historis (DunkAPI, §7) yang
  bisa menjawab. Laporan ini tidak mengklaim shrinkage lebih akurat.

**Koreksi Kalshi** (terverifikasi live): garis total NBA Kalshi
BUKAN bilangan bulat — tangga 199,5–255,5 langkah 2 poin, SAMA
PERSIS dengan Polymarket (29 garis; judul literal "Over 233.5
points scored"). Cocok-eksak bekerja: p_market Kalshi tersedia
untuk kedua kaki (0,68 dari mid bid/ask Over 233,5 31/33¢; 0,755
dari Over 237,5 24/25¢). Catatan 2a soal "garis bulat" + klaim
"Kalshi hampir tidak pernah memberi p_market" DICABUT — cakupan
p_market Kalshi untuk Alt Under BAIK.

## 9. Fixture wajib

- **Pelajaran Thunder** (`tests/fixtures/recheck/thunder_*`): analisis
  Under 227,5 @ 75¢, recheck menemukan 71¢ (bid 70/ask 72) → gerak
  4¢ > 3¢ → ANOMALI + JANGAN_PASANG + NO-GO.
- **Cedera bintang baru OUT** (`TestCederaBintangBaruOut`): Cade
  Cunningham OUT → resim → garis berubah 233,5→235,5 → JANGAN_PASANG
  garis lama + `action_required` "ganti garis ke 235.5"; varian garis
  tetap → PERHATIAN + GO; varian garis baru tidak meets →
  JANGAN_PASANG.
- **Fail-closed** (`test_resim_gagal_data_incomplete`,
  `test_fetch_*`): data cedera gagal saat recheck + data basi →
  kaki DATA_INCOMPLETE + tiket NO-GO; fetch gagal + data masih segar
  (≤3 jam) → tetap bisa GO + `fetch_error` tercatat.
- **Ambang batas**: gerak harga <1¢ stabil; 1–2¢ PERHATIAN; tepat 3¢
  anomali; garis tepat 2,0 tidak resim; 2,5 resim. Semua diuji.

## 10. Keterbatasan (jujur)

- **Berita non-cedera belum terdeteksi.** Recheck hanya membaca
  cedera + harga + garis. Berita seperti pergantian pelatih,
  masalah tim, atau rumor rotation tidak masuk — tidak ada modul
  berita (pekerjaan lanjutan; user sudah tahu ini dari awal).
- **Jendela recheck belum ditegakkan.** `data.recheck_window_minutes`
  [30, 60] ada di config tapi belum dibaca kode — recheck berjalan
  on-demand kapan pun user memintanya, tanpa peringatan bila di luar
  jendela. Usulan penyelarasan (tidak diubah diam-diam): keputusan
  2b soal verifikasi pasar 3 jam & 1 jam sebelum tip-off bisa
  DIPENUHI dengan menjalankan recheck pada jam-jam itu (recheck
  ADALAH verifikasi pasar); peracik tiket langkah 3 bisa memberi
  peringatan bila recheck terakhir lebih tua dari jendela. Sesuai
  jawaban user #2, tidak ada pemeriksaan terjadwal — tetap on-demand.
- **Recheck tidak mengambil pembanding baru** — `p_market` dibawa
  dari analisis awal. Bila harga pembanding (Kalshi/sportsbook)
  bergerak setelah analyze, recheck tidak tahu.
- **Moneyline jup.ag tidak dicek** (§4).
- **Analyze lambat** (~3,5 menit/laga, didominasi pemindaian penuh
  jup.ag 52 halaman). Untuk slate 10 laga, waktu analyze belum
  diukur live (estimasi sim saja ~35 dtk + pemindaian).
- **Shrinkage K=10 belum terbukti** — pilihan desain, bukan fit;
  efeknya pada margin material (§8) dan akurasinya belum diuji.
- **Contoh DET@ATL diregenerasi** dengan kode final (margin 1,55;
  ML kandang 54,2% seed 7) — angka di laporan 1b (margin 3,19;
  ML 59,1%) adalah keadaan pra-shrinkage. Laporan 1b adalah dokumen
  historis; file contoh mengikuti kode terbaru.

## 11. Hutang ke langkah 3 (peracik tiket + laporan)

- **Asuransi & Utama garisnya HARUS berbeda** untuk laga yang sama
  (kendala dari temuan auditor babak 2, temuan 3) — langkah 2 tidak
  memperbaikinya; contoh DET@ATL kini kebetulan berbeda (233,5 vs
  237,5 berkat fallback +12), tapi tidak ada jaminan umum.
- Aturan condong-ke-market juga berlaku di peracik tiket (keputusan
  user 20:36 WIB) — baru diterapkan di recheck.
- Kaki laporan recheck belum membawa kunci `ticket` (§3b).
- Peringatan jendela recheck (§10).
- Uji historis model-vs-market dengan garis penutupan DunkAPI
  (menunggu persetujuan signup, §7) — menentukan kapan kepercayaan
  ke model dipulihkan dari aturan condong-ke-market.

## 12. File yang berubah

Baru: `engine/nba_analysis.py`, `engine/recheck.py`,
`schemas/nba_analysis.schema.json`, `schemas/recheck.schema.json`,
`tests/test_nba_analysis.py`, `tests/test_recheck.py`,
`tests/test_cli_recheck.py`, `tests/fixtures/recheck/` (4 JSON).
Diubah: `cli.py`, `config.py`, `config/playstyle.yaml` (v8),
`engine/cushion.py`, `engine/nba_sim.py` (hanya notes alasan absen),
`ingest/nba_brain.py`, `ingest/bbref.py`, `ingest/slate.py`,
`tests/test_config.py`, `tests/test_cushion.py`,
`tests/test_ingest_nba_brain.py`, `tests/test_ingest_bbref.py`,
`tests/test_nba_sim.py`, `tests/test_cli.py`,
`examples/simulation_nba_ATL_DET_2026-11-22.json`, `DECISIONS.md`,
laporan ini. Tidak ada `.env`, `data/`, `out/`, atau cache yang
di-commit.

## 13. Keputusan menunggu objeksi reviewer

- K=10 shrinkage menit+BPM (pilihan desain, bukan fit).
- Kasus campuran PDF-cedera/ESPN-rest masuk `confirmed_both` (§5.2).
- Keputusan desain recheck §4 (HOLD → JANGAN_PASANG; fetch gagal +
  data segar → GO; resolved tidak memicu resim).
- Exit code recheck 0/1/2 (§2).
- (Ditutup langkah ini: utama_line spread=None → +12 menggantikan
  "bantalan 8"; Rest/Personal kini dimodelkan sebagai absen.)
