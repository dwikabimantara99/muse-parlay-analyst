# LAPORAN GATE v18 — Worker B

**Repo:** `muse-parlay-analyst`, branch main, mulai commit `ad2cfa0` (config v17,
1806 tes). **Selesai:** 2026-11-23 (config v18, 1990 tes).
**Ruang kerja:** `engine/equilibrium.py`, `engine/ticket_composer.py`,
`engine/vegas.py` (BARU), `report/nba_report.py` (hanya bagian vonis),
`tests/test_equilibrium.py`, `tests/test_ticket_composer.py`,
`tests/test_vegas.py` (BARU), `tests/test_report_v18.py` (BARU).
**Tidak disentuh:** `DECISIONS.md`, `LAPORAN-V18.md`, `config/playstyle.yaml`
(hanya baca), semua file worker A/C. **Tidak ada commit/push/stash.**
**0 kredit Odds API.** Semua tes offline (fixture + artefak tersimpan).

Keputusan user yang mengikat (DECISIONS.md, 2026-11-23 13:57 + veto AND
13:59 WIB): Asuransi TETAP x2 (2,0–2,5); banjir 70/65 + EV ≥ −1% DISETUJUI
(menggantikan edge datar 3,5%); Utama min p_final 0,74 DISETUJUI dengan
kendala x3–x5; veto AND + ambang 232,0/100,5 DISETUJUI. Prinsip user:
mesin mencari kaki yang MASUK AKAL, bukan yang paling ketat — KUNING =
tidak masuk akal (seperti Denver), bukan "tidak sempurna".

## Ringkasan hasil tes

| Cakupan | Hasil |
|---|---|
| Tes milikku (4 file) | **217/217 LULUS** — komposer 128, equilibrium 49, vegas 18, report_v18 22 |
| Full suite (`discover -s tests`) | 1990 tes, **23 gagal + 100 error — 0 di file milikku** |

Dari 123 kegagalan full suite, **98 punya SATU akar yang sama** — kunci
v17 yang dihapus `market_line_check.total_gap_points`: 97 error berupa
`config.ConfigError: kunci config tidak ditemukan:
market_line_check.total_gap_points` + 1 error `KeyError:
'total_gap_points'` — pembaca di kode worker lain (recheck/audit/qa)
masih membaca kunci v17 yang dihapus worker A dari config v18. Bukan
fileku — dilaporkan ke koordinator, tidak diperbaiki (§10). Sisanya:
ekspektasi v17 yang basi di `test_config` (versi 17, ambang 0,74/0,65,
kunci yang dihapus), `test_skip_awal` (DEN kini membawa dua pemicu),
`test_vonis`, `test_ingest_nba_brain`, `test_report_nba` (bagian
skip/skenario panas — BUKAN bagian vonis yang kuubah),
`test_pantau_blend`, `test_nba_analysis`, `test_stress` (masing-masing
1–9; rincian di §10).

## 1. Gate Asuransi baru (`engine/equilibrium.py` `_nilai_garis` + komposer)

Garis Under lolos Asuransi bila **SEMUA** ini terpenuhi:

| Gate | Ambang (config) | Catatan |
|---|---|---|
| Peluang | p_final ≥ 0,82 (`tickets.insurance.min_leg_prob`) | naik dari 0,74 (v17) |
| p_market | p_market ≥ 0,80 (`min_p_market`) | BARU. Bila p_market tidak ada (MODEL_ONLY) dan `equilibrium.butuh_anchor_pasar` false → gate ini TIDAK dievaluasi (dicatat `p_market_gate_dievaluasi: False`), kaki tetap boleh lolos bila p_final + banjir + EV lolos — bukan fail-closed buta. Bila butuh jangkar dan tidak ada → equilibrium tidak dihitung (perilaku lama) |
| Banjir 3P | P ≥ 0,70 (`flood_3p_min`) | dari CDF yang digeser (geser 8,50 poin) |
| Banjir FT | P ≥ 0,65 (`flood_ft_min`) | DUA ambang terpisah — menggantikan skenario tunggal `banjir_terburuk` ≥ 74% |
| EV | ev_pct ≥ −1,0% (`max_negative_ev_pct`) | ev = p_final × 100/harga − 1. **MENGGANTIKAN edge datar 3,5%** |
| Lantai harga | harga ≥ 75¢ (`analis.harga_min_asuransi_cents`) | tetap |
| Eksekusi | volume_usd ≥ $30 (lihat §3) | BARU, menggantikan thin sebagai penghalang keras |

**`min_edge_pct` Asuransi DIHAPUS dari semua pembaca.** Verifikasi grep:
satu-satunya pembaca di kode adalah komposer + equilibrium (keduanya
sudah diperbarui; yang tersisa hanya docstring yang menjelaskan
penghapusan). `recheck`, `audit`, `report` tidak pernah membacanya.
`audit` punya `edge_tipis_pct` sendiri (peringatan audit saja — dipertahankan,
bukan gate Asuransi). **Catatan untuk koordinator:** `scripts/ukur_equilibrium.py`
dan `scripts/ukur_asuransi_baru.py` masih membaca `min_edge_pct` dari config
(bukan fileku — belum diperbaiki).

**Band harga 80–89¢** (`preferred_price_band`): safety-first memilih
p_final TERTINGGI di antara garis lolos **DALAM band**; bila tidak ada garis
lolos dalam band, fallback ke p_final tertinggi di antara semua garis lolos
(dicatat `fallback_band: True` di hasil). Band adalah preferensi seleksi,
bukan gate.

**Kasus wajib OKC verif U250,5 @89,5¢: LOLOS semua gate v18** — p_final
0,908341, p_market 0,8950, EV +1,49%, banjir 0,86882/0,82114, volume
$226,875. Equilibrium memilih U246,5 @85,5¢ sebagai gantinya karena
89,5¢ berada di atas puncak band 80–89 (diuji di `test_equilibrium.py`).

**Target Asuransi TETAP 2,0–2,5** (`multiplier_min/max` tidak diubah);
`must_cover_total_stake` tetap berlaku.

## 2. Gate Utama baru

| Gate | Ambang (config) | Catatan |
|---|---|---|
| Peluang | p_final ≥ 0,74 (`tickets.main.min_leg_prob`) | naik dari 0,65 (v17) |
| EV | ev_pct ≥ −2,0% (`max_negative_ev_pct`) | tolak bila sangat MAHAL |
| Banjir | **warning-only** | P banjir 3P/FT dicatat di kandidat (`p_banjir_3p`, `p_banjir_ft`); bila di bawah ambang Asuransi (70/65) → `banjir_warning: True` + peringatan "rapuh bila laga banjir poin" di compose. Tidak memblokir |
| Lantai harga | harga ≥ 75¢ | tetap |
| Eksekusi | volume_usd ≥ $30 | sama dengan Asuransi |

**Band 76–84¢** (`preferred_price_band`), mode **max-ER** dengan tie-break:
bila selisih ER < 0,015 (`tiebreak_er_tolerance`), pilih garis yang LEBIH
AMAN (p_final lebih tinggi), lalu garis terkecil.

**TEMUAN — kendala x3–x5 TIDAK tercapai di slate uji (dilaporkan, ambang
TIDAK diturunkan):** dari 3 equilibrium Utama di slate 10 baris, pengali
maksimum = 1,075 × 1,325 × 1,042 × 0,945 ≈ **1,40x** — jauh di bawah x3.
Asuransi maksimum ≈ **1,35x** — di bawah x2. Penyebabnya BUKAN ambang 0,74
(diagnosis `peluang` lolos di 8–11 garis per laga) melainkan gate eksekusi/
volume (§8). Komposer nyata lebih ketat lagi: hanya 1 kaki Asuransi lolos
(DET) → pengali maks x1,07; Utama 0 kaki.

## 3. Volume → gate eksekusi

Minimum eksekusi = **max(2 × stake, $25)** dengan stake dari
`execution.stake_default_usd` (15,0) → **$30** per kaki. Helper publik
bersama `equilibrium.volume_min_eksekusi(cfg)` dipakai equilibrium +
komposer. Berlaku per KAKI di `_nilai_garis` (diagnosis `eksekusi`) dan
komposer.

- Volume tidak tercatat (None) → **tidak lolos (fail-closed)** + dicatat.
- Volume lolos gate tapi < $100 (ambang lama) → dicatat sebagai info
  (`info_volume_dibawah_100`), bukan blokir.
- `thin=True` yang lolos gate eksekusi **BOLEH masuk kedua tiket** (dulu:
  penghalang keras Asuransi) — ditandai flag `VOLUME_TIPIS` + peringatan
  di kedua tiket.
- **Hanya kaki NBA `total_under`** (keputusan menunggu keberatan — §9):
  kaki bola/moneyline tidak membawa data volume di artefak; fail-closed
  di sana akan membunuh semua kaki bola.

## 4. Komposer (`engine/ticket_composer.py`)

### 4a. TUNGGU_LINEUP
Laga berstatus `"tunggu_lineup"` ATAU bervonis `"tunggu_lineup"` (dari
artefak atau dari `nilai_vonis` worker A) **DIKELUARKAN dari kandidat final**
+ dicatat terpisah di hasil compose kunci **`"menunggu_lineup"`**:
`[{"match_id", "bintang", "alasan"}]` — bukan KUNING, bukan kandidat,
bukan skip. Bintang dibaca dari `indikator["timing_gate"]["bintang"]`
(bentuk nyata worker A) dengan fallback defensif ke kunci lain dan ke
`injuries.entries` berstatus QUESTIONABLE/DOUBTFUL; bila tidak ada nama
yang bisa disebut, bintang `[]` (nama tidak dikarang). Ringkasan mendapat
bagian "LAGA YANG MENUNGGU LINEUP". `_alokasikan_laga` juga melewatinya
(pertahanan berlapis). Terverifikasi end-to-end di artefak nyata:
OKC@MIA (verif) tercatat menunggu lineup — Giannis Antetokounmpo.

### 4b. Veto parsial +3
Bila `nilai_vonis.indikator["veto"]["peringatan_parsial"]` menyala, kaki
laga itu wajib **+3,0 poin bantalan**: garis yang dipilih (equilibrium
atau kaki artefak) harus ≥ **garis_acuan_normal + 3,0** (garis kaki artefak
SEBELUM equilibrium). Bila garis equilibrium kurang, komposer mencari
garis lolos semua gate di atas batas itu lewat `_pilih_garis_veto_parsial`
(mode tiket dipakai, **band harga diabaikan** — keselamatan veto di atas
preferensi harga); kaki dibangun ulang dari kaki artefak ASLI dengan
climb reason `equilibrium+veto_parsial`. Bila tidak ada garis yang
memenuhi → kaki dicoret dengan alasan tercatat (garis minimum + garis
acuan + alasan veto). Bantalan dibaca dari
`vonis.veto_parsial_bantalan_points` — **kunci ini BELUM ADA di config
saat build ini (default 3,0 dipakai)** — flag ke worker A untuk
menambahkannya (§10).

### 4c. Tanpa-kembar + alokasi vonis TETAP
HIJAU → Asuransi saja, menengah-hijau → Utama saja, KUNING dievaluasi →
tidak masuk mana pun, KUNING-karena-data (tidak dievaluasi) → tanpa
preferensi. Satu laga tidak pernah masuk kedua tiket.

### 4d. Equilibrium v18 dipakai peracik; gate v18 diterapkan ulang pada kaki artefak
Bila equilibrium terhitung, kaki dibangun ulang dari tangga (p_final dll.
dihitung ulang di garis baru). Bila equilibrium terhitung tapi TIDAK ADA →
kaki ditolak dengan alasan diagnostiknya (tanpa fallback ke kaki artefak).
Bila equilibrium TIDAK DIHITUNG (tanpa CDF/tangga/jangkar) → kaki artefak
dipakai apa adanya, tetapi **semua gate v18 tetap diterapkan ulang**
(peluang, p_market, banjir, EV, lantai, eksekusi) — bukan dipakai
mentah-mentah.

**Gate banjir komposer kini CDF-langsung (bukan `skenario_panas`):**
P banjir dihitung dari CDF equilibrium yang sama dengan
`stress.p_under_digeser` — sehingga gate menilai garis APAPUN yang dipilih
(equilibrium/veto/climb), bukan hanya garis artefak. `skenario_panas`
tidak lagi dipanggil komposer (0 panggilan saat compose — diuji);
cache `stress_per_laga` dihapus. Bila konteks equilibrium tanpa CDF
(artefak tanpa tangga), CDF dibangun langsung dari `simulation.markets`
(perilaku yang sama dengan gate stress v17; tanpa fallback ini kaki
artefak tanpa tangga selalu ditolak fail-closed — bug yang kutemukan
dan kuperbaiki saat smoke test). Climb banjir memakai
`_garis_tahan_banjir_ganda` (garis terendah yang lolos KEDUA ambang +
gate eksekusi).

**Urutan cek per kaki** (setelah rebuild equilibrium + penyesuaian veto):
meets → garis ada → gate banjir (Asuransi NBA) → kelengkapan
p_final/p_model/EV → penolakan MODEL_ONLY (skema mewajibkan p_market;
dipertahankan) → harga venue → lantai harga → gate eksekusi volume
(NBA total_under saja) → cek MAHAL Asuransi (pertahanan berlapis;
disubsumsi EV ≥ −1%) → TANPA_XG → putusan recheck → condong-ke-market →
ambang peluang → gate p_market (Asuransi) → gate EV (kedua tiket).

**`stress_gate_scenario` TIDAK LAGI dibaca gate** (kunci dipertahankan di
config v18 tapi tidak dipakai; menghapus/mengubah nilainya tidak memecahkan
compose — diuji). Penghapusannya menunggu keputusan koordinator/worker A.

**`engine/stress.py` TIDAK diubah:** output `skenario_panas` sudah membawa
`p_under["banjir_3p"]`/`["banjir_ft"]` per kaki, dan tidak ada pembacaan
flood gate yang perlu berubah.

## 5. Vegas sanity check (`engine/vegas.py` BARU)

Signature persis (dipakai worker C di `nba_analysis.py` — JAGA):

```python
sesuaikan_median(median_model, garis_pasar, ada_sebab_cedera_baru, cfg=None)
    -> {"median_baru": float, "geser": float, "diterapkan": bool, "alasan": str}
```

Aturan: bila `|median − pasar| > 5,0` (`calibration.lean_to_market_gap`)
DAN tanpa sebab cedera baru terverifikasi → susutkan median ke arah pasar
sebesar **setengah jarak** (`calibration.shrinkage`: mode `"setengah_jarak"`,
fraction `0.5`). Alasan: pasar NBA efisien tapi model punya informasi
independen; susut penuh ke pasar membuang model sepenuhnya. Nilai dibaca
dari config dengan default yang sama dengan nilai v18 yang sudah mendarat.
Kunci config yang dibaca: `calibration.lean_to_market_gap`,
`calibration.shrinkage.mode`, `calibration.shrinkage.fraction`
(mode selain `"setengah_jarak"` → `ConfigError`; fraction di luar [0,1]
→ `ConfigError`). **Rencana kalibrasi:** ukur Brier/MAE per fraction
(0,25/0,50/0,75/1,0) di slate PAPER; perubahan hanya atas persetujuan user.

### Konterfaktual Vegas di slate uji tersimpan

10 baris (`out/analysis_live_2026-11-22.json` + `out/analysis_verif_tahap4_2026-11-22.json`).
P(Under) dihitung ulang di garis kaki Asuransi artefak dengan CDF yang
digeser sebesar `median_baru − median_lama`; p_final = 0,3×p_model +
0,7×p_market (p_market tidak bergerak — jangkar pasar). Basis CDF
tervalidasi: p_final "sebelum" cocok dengan p_final artefak sampai 4
desimal di semua baris yang terhitung.

| Laga | Median | Pasar | Gap | Geser | Median baru | Garis | p_model sblm→ssdh | p_final sblm→ssdh |
|---|---|---|---|---|---|---|---|---|
| DET@ATL (live) | 219,0 | 225,5 | 6,5 | +3,25 | 222,25 | U233,5 | 0,7701→0,7160 | 0,7105→0,6943 (−1,62 pp) |
| OKC@MIA (live) | 229,0 | 231,5 | 2,5 | 0 | 229,00 | U242,5 | 0,7673 | 0,7482 (tetap) |
| ORL@WAS (live) | 220,0 | 221,5 | 1,5 | 0 | 220,00 | U233,5 | 0,7535 | 0,7686 (tetap) |
| DEN@CHI (live) | 235,0 | 237,5 | 2,5 | 0 | 235,00 | U248,5 | 0,7589 | 0,7352 (tetap) |
| DAL@UTA (live) | 217,0 | 225,5 | 8,5 | +4,25 | 221,25 | U234,5 | 0,8227→0,7610 | 0,7368→0,7183 (−1,85 pp) |
| IND@NYK (live) | 208,0 | 216,5 | 8,5 | +4,25 | 212,25 | U224,5 | 0,7991→0,7307 | 0,7367→0,7162 (−2,05 pp) |
| BOS@GSW (live) | 198,0 | 211,5 | 13,5 | +6,75 | 204,75 | U219,5 | 0,8620→0,7709 | 0,7416→0,7143 (−2,73 pp) |
| OKC@MIA (verif) | 220,0 | 231,5 | 11,5 | +5,75 | 225,75 | U250,5 | 0,9395→0,8959 | 0,9083→0,8953 (−1,31 pp) |
| DEN@CHI (verif) | 233,0 | 236,5 | 3,5 | 0 | 233,00 | — | tidak bisa dihitung (kaki Asuransi artefak tanpa garis) | — |
| BOS@GSW (verif) | 203,0 | 210,5 | 7,5 | +3,75 | 206,75 | — | tidak bisa dihitung (kaki Asuransi artefak tanpa garis) | — |

**6/10 median bergeser, semuanya ke ATAS, total +28,0 poin** (model
sistematis lebih rendah dari pasar di slate ini). Dampak ke p_final kaki:
−1,31 s.d. −2,73 poin persentase pada kaki yang bergeser. **Di slate ini
Vegas tidak mengubah satu pun vonis gate di garis kaki artefak:**
satu-satunya kaki di atas ambang Asuransi 0,82 (OKC verif) tetap di atas
(0,8953); empat kaki yang bergeser sudah berada di bawah ambang sebelum
penyesuaian. Batasan jujur: tabel ini mengukur efek pada garis TETAP
(kaki artefak); efek penuh (pemilihan ulang equilibrium di bawah CDF
yang bergeser) baru bisa diukur setelah wiring worker C + analisis ulang
— bukan bagian build ini.

## 6. Laporan 3 lapis (`report/nba_report.py` — hanya bagian vonis)

`_bagian_vonis` direstrukturasi menjadi 3 lapisan (headline vonis tetap
paling atas; teks header VETO dan headline dipertahankan persis):

- **Lapisan 1 "Yang menentukan vonis:"** pemblokir keras — veto AND,
  data tidak lengkap, MAHAL (kaki Asuransi di garis vonis berlabel MAHAL),
  OT ekstrem (p_ot ≥ 0,085). Header VETO menonjol di awal lapisan ini.
- **Lapisan 2 "Catatan kualitas:"** demerit (rapuh banjir, total tinggi,
  gap besar, ekor gemuk, foul tinggi, spread tipis, dll.). Kalimat yang
  tidak dikenali masuk sini (default aman — terlihat, tidak diklaim
  sebagai pemblokir keras).
- **Lapisan 3 "Info tambahan (tidak mengubah vonis):"** volume tipis,
  skor setan per pemain, selisih kecil vs pasar, garis yang dinilai,
  edge terbaik, kalimat banjir (v18: 3P/FT terpisah; bentuk lama sebagai
  fallback), OT empiris. Volume SELALU Lapisan 3 di v18 (bukan lagi
  demerit vonis).

Klasifikasi memakai heuristik awalan kalimat atas alasan vonis v18
(dengan bentuk v17 untuk kompatibilitas artefak lama). Headline
TUNGGU_LINEUP ditambahkan. Bahasa sederhana, tanpa jargon.

**Kalimat "Skenario Mati"** (satu per kaki HIJAU): ambang akurasi 3P
gabungan yang akan membunuh kaki =
`(garis − poin_non_3P_normal) / (3 × percobaan_3P_diharapkan)`, dari blok
`setan_pemain` artefak bila ada (status "ok"); contoh hitung tangan:
median 220, poin 3P normal 80, percobaan 70, garis 240,5 → ambang 47,9%
(normal 38,1%). Bila blok tidak ada → kalimat fallback dari P banjir/
setan; bila tidak bisa dihitung → kalimat tidak ditampilkan (bukan
dikarang). Ditampilkan hanya untuk kaki HIJAU. Catatan: artefak tersimpan
saat ini tidak membawa blok `setan_pemain` (None) — jalur fallback yang
umum untuk artefak nyata.

Smoke test render: DAL live → HIJAU (v18 vonis; dulu MENENGAH HIJAU di
v17) + 3 lapis + Skenario Mati fallback; DEN verif → KUNING + VETO
menonjol + Nic Claxton; OKC verif → TUNGGU LINEUP (Giannis
Antetokounmpo). Selama smoke test diperbaiki bug koma kalimat OT
(`.replace(".", ",")` ikut mengganti titik akhir → "5,42%,").

## 7. Tes

Tes milikku **217/217 lulus** (dijalankan 2026-11-23):

- `tests/test_equilibrium.py` — 49 tes. Tes pengunci v17 ditulis ulang
  dengan alasan tercatat di komentar (edge 3,5%, banjir 74%, p_final
  0,74/0,65, volume $100). Kelas baru `TestGateV18` (7 tes): band +
  fallback, tie-break ER, gate eksekusi ($30/batas), gate p_market,
  MODEL_ONLY, dua ambang banjir, warning banjir Utama.
- `tests/test_ticket_composer.py` — 128 tes (dari 117; +11 baru, beberapa
  digabung). Fixture standar diperbarui: volume kaki default $500
  (lolos gate eksekusi), kaki Asuransi standar p_final 0,846
  (0,86/0,84 — fixture v17 0,786 kini gagal gate peluang 0,82 +
  p_market 0,80). Kelas baru: `TestGateEvAsuransi` (menggantikan
  `TestGateEdgeAsuransi`), `TestGateEksekusiVolume` (menggantikan
  `TestThin`), `TestGateBanjirUnit` (menggantikan `TestGateSkenarioUnit`),
  `TestTungguLineupKomposer`, `TestVetoParsial`, `TestBanjirUtamaWarning`.
  Tes banjir ditulis ulang atas perilaku v18 yang terukur (bukan
  diasumsikan) — termasuk DEN yang kini naik ke 260,5 (§8).
- `tests/test_vegas.py` (BARU) — 18 tes: hitung tangan shrinkage
  (220→224,25, geser +4,25), batas (gap tepat 5,0 → tidak bergeser),
  pengecualian cedera, override/default config, kasus ConfigError,
  input tidak valid, konterfaktual artefak tersimpan.
- `tests/test_report_v18.py` (BARU) — 22 tes: klasifikasi 3 lapis,
  Skenario Mati hitung tangan + fallback + omit, render dengan vonis
  mock (urutan lapis, VETO sebelum "edge kecil", headline TUNGGU_LINEUP,
  MAHAL di Lapisan 1, Skenario Mati hanya HIJAU), artefak nyata
  (DEN verif veto di Lapisan 1, OKC verif TUNGGU LINEUP, DAL live HIJAU
  + Skenario Mati fallback).

Tes perilaku vonis/skip (tunggu_lineup, veto parsial, alokasi) memakai
mock `nilai_vonis`/`skip_awal` atau fixture sintetis dengan flag
dimatikan — bukan bergantung pada pekerjaan worker A yang belum selesai.
Tes artefak nyata memakai flag nyata dan dapat gagal sampai A/C mendarat
— saat ini semuanya lulus.

## 8. Dampak gate baru di slate uji (10 baris tersimpan)

Equilibrium v18 (config v18, geser banjir bersih 8,50/12,52):

| Laga | Asuransi | Utama |
|---|---|---|
| DET@ATL (live) | U245,5 @88,5¢, p 0,8776, EV −0,84%, banjir 0,820/0,762, vol $93, thin, dalam band | U249,5 @93¢, p 0,9136, EV −1,76%, vol $141, fallback band |
| OKC@MIA (verif) | U246,5 @85,5¢, p 0,8714, EV +1,92%, banjir 0,821/0,763, vol $31,50, thin, dalam band | U240,5 @75,5¢, p 0,7888, EV +4,48%, vol $587,03, fallback band |
| BOS@GSW (verif) | U235,5 @92,5¢, p 0,9235, EV −0,17%, banjir 0,897/0,855, vol $50,50, thin, fallback band | U239,5 @96¢, p 0,9483, EV −1,22%, vol $59,68, thin, fallback band |
| 7 baris lain | TIDAK ADA | TIDAK ADA |

**Asuransi 3/10 (v17: 0/10), Utama 3/10 (v17: 10/10)** — cocok dengan
target penerimaan Gemini 2–3 kandidat HIJAU. **Gate pengikatnya adalah
eksekusi/volume, BUKAN ambang peluang:** di SEMUA 14 kombinasi
(baris, tiket) yang gagal, alasan diagnostiknya `eksekusi —
volume_tidak_cukup` — ada 1–11 garis per kombinasi yang lolos SEMUA gate
lain tetapi gagal gate eksekusi (volume tidak tercatat, atau $1,27–$26,25
< $30). Contoh: OKC live Asuransi — 5 garis lolos gate lain, semuanya
gagal eksekusi (terbaik U248,5 volume tidak tercatat); DEN verif Utama —
9 garis lolos gate lain, terbaik U252,5 volume $26,25.

**Tidak ada tiket terbentuk** di komposer penuh (dedup 7 laga unik):
Asuransi hanya mencapai x1,07 (satu kaki DET); Utama 0 kaki (DET
dialokasikan ke Asuransi karena vonis HIJAU; BOS/DEN HOLD; OKC
TUNGGU_LINEUP; DAL/IND/ORL di-skip). Ini temuan, bukan kegagalan build —
ambang tidak diturunkan diam-diam.

### Perubahan perilaku penting vs v17 (dicatat jujur)

1. **DEN tidak lagi ditolak komposer** pada fixture sintetis: kaki
   artefak U252,5 tetap ditolak (banjir FT 64,2% < 65%), tetapi
   equilibrium menemukan 260,5 @88,5¢ (p_final 0,917, banjir 83,8%/78,2%,
   EV +3,7%, thin tapi volume $500) sehingga DEN lolos gate komposer
   v18. Di v17 semua garis tahan-banjir thin sehingga DEN ditolak.
   **Pertahanan terhadap laga seperti DEN kini ada di skip_awal/vonis
   (worker A), bukan di gate komposer** — dan di artefak nyata DEN live
   memang di-skip (pola_denver + tidak_ada_equilibrium). Bila user
   menganggap ini tidak dapat diterima, gate yang harus diubah adalah
   ambang banjir/skip — bukan komposer yang melonggarkan sendiri.
2. **Hard-skip OT v18 DORMAN** (temuan dari `engine/ot_empiris.py`
   worker A, bukan kodenya): p_ot empiris maksimum (spread 0) =
   base_rate 0,0575 < ambang hard-skip 0,085 — `ot_tinggi` tidak pernah
   menyala dengan config live. Tesku membuktikan mekanisme dengan
   override ambang 5,0% + mendokumentasikan dormansi di config live.
3. **Thin bukan lagi penghalang**; garis thin bervolume cukup boleh
   dipilih (DEN 260,5 adalah contohnya).
4. **Gate EV tidak menjamin EV tiket positif** (berbeda dengan gate edge
   v17): EV kaki ≥ −1% hanya menjamin faktor per kaki ≥ 0,99 sehingga EV
   tiket 3 kaki bisa serendah 0,99³ × 0,945 − 1 ≈ −8,3%. Peringatan EV
   tiket negatif kini bisa menyala untuk Asuransi juga.

## 9. Keputusan desain yang menunggu keberatan

1. **Shrinkage Vegas 0,5 (setengah jarak)** — pasar efisien tapi model
   punya informasi independen; susut penuh membuang model. Rencana
   kalibrasi di §5.
2. **Fallback band** — band harga adalah preferensi seleksi, bukan gate;
   bila tidak ada garis lolos dalam band, pilih p_final tertinggi di luar
   band (dicatat). Alternatif: tidak ada equilibrium bila band kosong
   (lebih ketat, lebih sering tidak terbentuk).
3. **Aturan MODEL_ONLY untuk p_market** — tanpa p_market, gate p_market
   tidak dievaluasi (dicatat) dan kaki boleh lolos bila gate lain lolos.
   Alternatif: fail-closed (kaki tanpa pembanding pasar selalu ditolak).
   Catatan: komposer TETAP menolak MODEL_ONLY karena skema tiket
   mewajibkan p_market — jadi aturan ini hanya berpengaruh di equilibrium
   murni.
4. **Implementasi veto parsial +3** — garis acuan = garis kaki artefak
   sebelum equilibrium; pencarian mengabaikan band; climb dibangun dari
   kaki artefak asli. Bantalan default 3,0 karena kunci config belum ada.
5. **Gate eksekusi hanya NBA total_under** — kaki bola/moneyline tidak
   membawa data volume; fail-closed di sana membunuh semua kaki bola.
6. **`liquidity` vs `volume_usd` (pertanyaan terbuka untuk koordinator):**
   tangga membawa field `liquidity` ($24k–$32k bahkan di garis dengan
   `volume_usd` None). Config sendiri mencatat volume Gamma adalah
   kumulatif ("ukuran kasar, bukan likuiditas saat ini"). Bila gate
   eksekusi seharusnya memakai kedalaman orderbook (`liquidity`), 7
   baris yang kini gagal volume bisa lolos — tetapi itu keputusan
   koordinator/user, bukan pergantian sepihak olehku.
7. **Thin sebagai info, bukan gate** — konsekuensi dari keputusan user
   (volume → gate eksekusi); garis thin bervolume cukup masuk tiket
   dengan flag + peringatan.
8. **Ambang warning banjir Utama = ambang Asuransi (70/65)** — definisi
   "rapuh banjir" memakai standar Asuransi; tidak ada ambang warning
   terpisah di config.

## 10. Temuan untuk koordinator / worker lain (bukan fileku — tidak diperbaiki)

1. **98 kegagalan full suite — satu akar:** pembaca `market_line_check.total_gap_points`
   (kunci v17 yang dihapus) di kode recheck/audit/qa — 97 ConfigError + 1 KeyError.
   Perlu diperbarui ke `calibration.lean_to_market_gap` (seperti yang kulakukan di
   komposer) atau dihapus.
2. **Kunci config belum ada:** `vonis.veto_parsial_bantalan_points`
   (komposer memakai default 3,0) — mohon worker A menambahkannya.
3. **`stress_gate_scenario` tidak lagi dibaca gate** (dipertahankan di
   config, tidak dipakai) — putuskan: hapus atau biarkan.
4. **`skip_awal` masih menyebut edge 3,5%** di teks pola-Denver
   ("edge kecil (+1,9% < 3,5%)") — teks basi pasca-penghapusan edge.
5. **`scripts/ukur_equilibrium.py` + `scripts/ukur_asuransi_baru.py`**
   masih membaca `min_edge_pct` dari config.
6. **Tes basi v17 di file lain:** `test_config` (versi/ambang/kunci),
   `test_skip_awal` (DEN kini dua pemicu; 6/10 baris di-skip),
   `test_vonis` (kunci v17 yang dihapus; DAL live kini HIJAU di v18).
   Struktur kontrak laporanku dipertahankan (teks header VETO + headline
   persis) sehingga tes struktural vonis tetap berlaku.
7. **Perubahan config selama sesi ini (oleh worker A):**
   `stress.banjir_3p_points`/`banjir_ft_points` 13,54/17,54 (p90 tercemar,
   dulu sengaja dipertahankan) → **8,50/12,52** (p90 bersih). Semua angka
   di laporan ini diukur dengan 8,50/12,52; angka lama dengan 13,54/17,54
   sudah basi.
8. **Perilaku equilibrium yang perlu diketahui worker C:** bila garis
   equilibrium SAMA dengan garis artefak, kaki artefak dipakai apa adanya
   (tanpa rebuild — harga venue tetap harga artefak, bukan jup tangga).
   Terlihat di tes warning banjir Utama (kaki @78,0¢ bukan 78,5¢).

## 11. Kunci config yang dibaca (worker B)

```
tickets.insurance.{multiplier_min, multiplier_max, min_leg_prob,
  min_p_market, max_negative_ev_pct, flood_3p_min, flood_ft_min,
  preferred_price_band, must_cover_total_stake}
tickets.main.{multiplier_min, multiplier_max, target_multiplier_max,
  min_leg_prob, max_negative_ev_pct, preferred_price_band,
  tiebreak_er_tolerance}
tickets.mode, tickets.{insurance,main} (via _ambang umum)
execution.{min_liquidity_multiplier, liquidity_hard_min_usd, stake_default_usd}
calibration.{lean_to_market_gap, apply_shrinkage_pre_verdict,
  shrinkage.mode, shrinkage.fraction}
equilibrium.{mode_insurance, mode_main, butuh_anchor_pasar, enabled}
stress.{banjir_3p_points, banjir_ft_points}
stress_gate_scenario (DIBACA: tidak lagi — lihat §4)
vonis.veto_parsial_bantalan_points (BELUM ADA — default 3,0)
vonis.enabled, skip_awal.enabled, analis.{harga_min_utama_cents,
  harga_min_asuransi_cents}, optimizer.exclude_mahal_from_insurance
```

Nilai default bila kunci hilang (pola yang sama dengan lantai harga /
ambang yakin): EV Asuransi −1,0 / Utama −2,0; banjir 0,70/0,65;
p_market 0,80; bantalan veto 3,0; shrinkage 0,5/setengah_jarak;
gap 5,0. Semua default diuji (tes "default bila kunci hilang").

## 12. Batasan jujur

- Gate diukur di slate 10 baris tersimpan (22 Nov) — gambaran, bukan
  bukti. Slate 24 Nov (10 laga) adalah ujian nyata pertama.
- Konterfaktual Vegas hanya mengukur efek garis-tetap; efek penuh butuh
  wiring worker C + analisis ulang.
- Volume Gamma kumulatif adalah proksi kasar likuiditas (lihat §9.6) —
  gate eksekusi bisa menolak garis yang sebenarnya bisa dibeli, atau
  sebaliknya. 52/67 garis Under tangga OKC live tidak membawa
  `volume_usd` sama sekali.
- Klasifikasi 3 lapis memakai heuristik awalan kalimat atas bentuk
  kalimat vonis v18 — bila worker A mengubah redaksi alasan vonis,
  klasifikasi bisa salah lapis (default aman: Lapisan 2).
- Skenario Mati butuh blok `setan_pemain` (belum ada di artefak
  tersimpan) — untuk artefak nyata saat ini hanya jalur fallback yang
  berjalan.
- Hard-skip OT dorman dengan config live (§8.2) — bukan kewenanganku
  mengubah ambang atau laju dasar.
- Full suite belum hijau (123 kegagalan, 0 milikku) — menunggu worker
  lain menyelesaikan pembaruan mereka; rilis v18 tidak bisa dinyatakan
  hijau sampai 98 kegagalan `total_gap_points` + tes basi dibereskan pemiliknya.
