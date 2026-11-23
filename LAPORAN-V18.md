# LAPORAN v18 — Mesin Parlay NBA (Gemini Audit Build)

**Tanggal:** 2026-11-23 sore WIB · **Config:** v18 · **Tes:** 2003/2003 lolos
(dari 1806 di v17) · **Kredit Odds API:** 0 · **Ruff + black:** bersih ·
**Cabang:** main (dari `ad2cfa0`)

Sumber: `REFERENSI-AUDIT-GEMINI-V18.md` (§1–§4) + keputusan user 13:57–13:59 WIB
di `DECISIONS.md` (mengikat, tidak diubah). Laporan worker:
`LAPORAN-VONIS-V18.md` (A — vonis/veto/OT/timing gate),
`LAPORAN-GATE-V18.md` (B — equilibrium/komposer/Vegas/laporan),
`LAPORAN-DEMON-V18.md` (C — demon cap/short-circuit/acceptance).
Pengukuran: `scripts/ukur_v18.py` → `out/ukur_v18.json`.

---

## 1. Ringkasan eksekutif

v18 memperbaiki 4 cacat struktural yang ditemukan audit Gemini atas v17
(deadlock Asuransi, bias edge datar di ekor, jendela gap terjepit 4,0–5,0,
pemicu OT di atas kap teoretis sim). Hasil di slate uji 10 baris:

| Ukuran | v17 | v18 |
|---|---|---|
| Vonis HIJAU / MENENGAH / KUNING / TUNGGU | 0 / 2 / 8 / — | **5 / 0 / 1 / 4** |
| Equilibrium Asuransi | 0/10 | **10/10** |
| Equilibrium Utama | 10/10 | **10/10** |
| False positive (laga pemenang divonis KUNING) | 4/5 | **0/5** |
| Laga di-skip (skip_awal) | 8/10 | **6/10** (semua pola Denver) |
| Total setan DEN@CHI | 274,14 | **253,71** |
| Tiket terbentuk (slate live 7 laga) | — | **tidak ada** (lihat T2) |

**Acceptance test Gemini §4: 2/5 LITERAL.** T3 (false positive) + T4
(IND TUNGGU_LINEUP) LOLOS. T1 + T5 lolos di bawah rumusan ulang
koordinator yang didokumentasikan (T1: DEN terblokir dari kedua tiket
di kedua baris; T5: penghematan 6,85 dtk/laga kena veto terukur).
**T2 GAGAL secara jujur:** 5 baris HIJAU+EQ ada (4 laga berbeda), tapi
hanya 3 kaki mencapai komposer Asuransi — pengali maks **x1,36** < x2.
Tidak ada ambang yang dilonggarkan untuk mengejar target.

**Temuan terpenting untuk iterasi dengan Gemini:** penghalang v18 bukan
lagi ambang peluang (equilibrium 10/10), melainkan **jumlah kaki**.
Pola Denver men-skip 4/7 laga live — 3 di antaranya (OKC, ORL, IND)
menang di garis EQ. Konservatisme mesin pindah dari lapisan vonis
(sudah diperbaiki: 0/5 KUNING) ke lapisan skip. Lihat §4 + §7.

---

## 2. Yang dibangun (10 item proposal v18)

### 1. Gate Asuransi/Utama baru — `engine/equilibrium.py`, `config/playstyle.yaml`

- **Asuransi:** p_final ≥ 0,82 + p_market ≥ 0,80 + banjir 3P ≥ 70% /
  FT ≥ 65% + **EV ≥ −1%** (mengganti edge datar 3,5%; `min_edge_pct`
  dihapus dari semua pembaca) + lantai 75¢ + gate eksekusi. Band
  80–89¢, safety-first dalam band, fallback tercatat.
- **Utama:** p_final ≥ 0,74 + EV ≥ −2% + banjir warning-only, band
  76–84¢, max-ER dengan tie-break ke garis lebih aman bila selisih
  ER < 0,015.
- Bukti: OKC verif U250,5 @89,5¢ lolos semua gate (p_final 0,908,
  EV +1,49%, banjir 0,869/0,821); equilibrium memilih U248,5 @88¢
  (dalam band). 57 tes equilibrium.

### 2. Vonis baru — `engine/vonis.py`

6 demerit: (a) kerapuhan ekor gabungan (banjir 3P < 0,72 ATAU FT <
0,67); (b) total ≥ 235; (c) gap > 8,0 HANYA tanpa cedera baru
terverifikasi; (d) ekor gemuk diperketat (≥ +16 poin DAN harga ≤ 80¢);
(e) lingkungan foul (FTr gabungan ≥ p80 0,308111 — FIT dari distribusi
liga); (f) spread tipis ≤ 3,0. Dihapus: gap < 4,0, volume, demerit
edge/setan, pemicu OT sim. HIJAU = 0 veto + ≤1 demerit + ≥1 rem alami;
KUNING = ≥4 demerit ATAU veto. 5 rem alami (cutoff FIT n=30: DRtg
Top-10 ≤ 112,9; pace Bottom-12 ≤ 98,91; FTr p50 0,274398).
`stats_season` kini 6 field (tambah FTr + 3PAr dari stats.nba.com).
64 tes vonis.

### 3. Veto AND + filter posisi — `engine/vonis.py`, `config/rim_protector_2026-27.json`

Rim protector OUT terkonfirmasi (2 sumber) + garis pasar ≥ 232,0 DAN
pace proyeksi ≥ 100,5 → veto menyala, blokir kedua tiket. Definisi:
posisi C/PF/F-C/C-F, min 18 mnt/laga, BLK ≥ 1,0. **stats.nba.com TIDAK
punya kolom posisi** (terverifikasi live) — posisi dari BBRef. Peta
regenerasi live: **21/30 tim** (9 belum terpetakan: ATL, DET, GSW, HOU,
IND, LAC, NYK, ORL, PHX — veto tidak bisa mengevaluasi tim itu).
Satu kondisi menyala → warning + bantalan +3 poin (bukan blokir).
Ambang 232,0/100,5 **INITIAL** (2 titik data).

- DEN verif MENYALA: Claxton OUT + 236,5 + 103,22.
- OKC verif TIDAK: 231,5 < 232,0 (pace saja menyala, tercatat
  `peringatan_parsial`).
- DEN live TIDAK: garis+pace keduanya menyala, tapi belum ada rim
  protector OUT di snapshot pagi itu (Claxton belum OUT) — perilaku
  AND yang benar.

### 4. Volume → gate eksekusi — direvisi koordinator (lihat §5.1)

Gate eksekusi v18 = **likuiditas Gamma ≥ $30 DAN spread bid/ask ≤ 5,0¢
DAN ask nyata (< 99¢)**; data hilang = gagal. Volume kumulatif bukan
gate lagi — hanya flag thin + info L3. Implementasi tunggal
`equilibrium.cek_eksekusi`, dipakai equilibrium + komposer (kaki dulu,
fallback ke tangga). 8 tes gate baru.

### 5. Setan per pemain — `engine/setan_pemain.py`

Cap per pemain min(50%, %musim + 12pp) ganti uniform 54,1%
(`FORMAT_VERSION` 2). Flag 3P Volume Risk bila kedua tim Top-10 3PAr
(cutoff 0,457207 FIT). Tetap diagnostic, bukan gate.

- **DEN@CHI total setan baru 253,71** (v17: 274,14; geser 20,71;
  hitung tangan 233,0 − 68,09 + 88,80 = 253,71 — identik dengan kode).
- **Kedua kaki DEN nyata TETAP rapuh** (U252,5 p=0,4782; U250,5
  p=0,4366; keduanya < 0,74) tapi margin tipis (+1,21/+3,21 di atas
  garis vs +21,64/+23,64 di v17).

### 6. Timing gate TUNGGU_LINEUP — `engine/vonis.py`, `ingest/pemain_usg.py`

Bintang Questionable (USG ≥ 24% atau BPM ≥ +2,0) → status TUNGGU_LINEUP,
tidak masuk racik final, tidak divonis prematur. USG dari stats.nba.com
Usage (fallback BBRef, 474 pemain terverifikasi live). Kualifikasi D7:
jalur USG mensyaratkan mp ≥ 10,0 + BPM ≥ 0,0 (menolak pemain pinggiran).
IND@NYK ditahan (Towns BPM +5,4 + Siakam USG 27,8%). 4/10 baris
ditahan (tanpa D7: 6/10).

### 7. OT empiris — `engine/ot_empiris.py` (baru)

Pemicu keras 2,8% DIHAPUS (di atas kap teoretis sim 2,74% — noise
Monte Carlo). Model baru: p = 0,0575 × exp(−spread²/(2×14,4307²)).
Base rate 0,0575 adalah **PRIOR yang didokumentasikan, bukan fit**
(tidak ada flag OT di 2.701 laga data fit). Hard-skip 0,085 **DORMAN**
(p_ot maks 0,0575 < 0,085 — tidak pernah menyala di v18; dikunci tes).
DET@ATL p=0,05695, tidak di-skip. 0/10 baris kena skip OT (lama: 0 juga
di slate ini — pemicu lama tidak pernah menyala di sini, tapi cacatnya
terbukti di teori).

### 8. Vegas sanity check awal — `engine/vegas.py` (baru), `engine/nba_analysis.py`

Bila |median model − garis pasar| > 5,0 tanpa sebab cedera baru
terverifikasi, median digeser **setengah jarak** ke pasar SEBELUM vonis
+ equilibrium. Penyusutan 0,5 (keputusan desain, menunggu keberatan).
Penempatan: CDF efektif kanonis di artefak (`simulation.markets` +
`score_distribution.total` = nilai efektif; mentah di `*_mentah`; blok
root `vegas` mencatat keputusan) — vonis/equilibrium/skip/komposer
membaca nilai efektif tanpa perubahan hilir.
Kontrafaktual slate uji: 6/10 median bergeser, semua NAIK, total +28,0
poin; p_final −1,31 s.d. −2,73 pp; tidak mengubah gate mana pun di slate
ini (OKC verif tetap di atas ambang: 0,8953).

### 9. Short-circuit — `engine/nba_analysis.py`

Laga kena Hard Veto melompati Tahap 3 (sim), 5 (Kalshi), 5b (news),
5c (demon); artefak tetap valid (DATA_INCOMPLETE + blok veto + KUNING).
**Hemat terukur ≈ 6,85 dtk/laga kena veto** (sim 3,70 + Kalshi 3,12 +
news 0,02 + pemain 0,02) — `out/ukur_short_circuit.json`. Klaim Gemini
"30–50% per slate" TIDAK BERLAKU: scan jup.ag slate-level
(~3,5 mnt/slate), bukan per laga — restrukturisasi adalah rekomendasi,
bukan klaim.

### 10. Tampilan 3 lapis + "Skenario Mati" — `report/nba_report.py`

L1 hard blocker (veto, data tidak lengkap, MAHAL, OT ekstrem) / L2
demerit kualitas / L3 info abu-abu (volume tipis TIDAK mengubah warna).
Satu kalimat "Skenario Mati" per kaki HIJAU (contoh DAL live: "Skenario
mati kaki Under 246,5: kalau laga banjir poin, peluang kaki ini lolos
turun ke 81,6%; kalau deviasi maksimal datang, turun ke 73,1%.").
Garis yang dinilai kini equilibrium Asuransi, bukan kaki artefak.

**Perubahan koordinator tambahan (di luar 10 item, dari pengukuran):**
sisa HIJAU mengalir ke Utama (§5.4); `stress_gate_scenario` mati dihapus
dari config; `lean_to_market_gap` dipindah ke `calibration.*` (4 pembaca
diarahkan ulang); kunci `vonis.veto_parsial_bantalan_points: 3,0`
ditambahkan; skema diperluas (blok root `veto`/`tunggu_lineup`/`vegas`,
`markets_mentah`/`total_mentah`, field kaki `liquidity_usd`/`bid_cents`/
`ask_cents`); 26 file diformat black + 6 error ruff diperbaiki.

---

## 3. Acceptance test — hasil akhir

`scripts/ukur_v18.py` → `out/ukur_v18.json` (dijalankan setelah semua
revisi, config v18). Tabel per baris:

| Laga | Vonis | Veto | EQ Ins | EQ Utama | Final |
|---|---|---|---|---|---|
| DET@ATL live | hijau | – | 245,5 | 241,5 | 204 ✓ |
| OKC@MIA live | tunggu_lineup | – | 252,5 | 248,5 | 236 ✓ |
| ORL@WAS live | hijau | – | 241,5 | 235,5 | 212 ✓ |
| DEN@CHI live | tunggu_lineup | – | 258,5 | 254,5 | 296 ✗ |
| DAL@UTA live | hijau | – | 246,5 | 240,5 | 230 ✓ |
| IND@NYK live | tunggu_lineup | – | 234,5 | 232,5 | 219 ✓ |
| BOS@GSW live | hijau | – | 231,5 | 223,5 | 175 ✓ |
| OKC@MIA verif | tunggu_lineup | – | 248,5 | 244,5 | 236 ✓ |
| DEN@CHI verif | **kuning** | **YA** | 258,5 | 254,5 | 296 ✗ |
| BOS@GSW verif | hijau | – | 229,5 | 223,5 | 175 ✓ |

### T1 — DEN@CHI WAJIB KUNING: GAGAL literal, LOLOS fungsional

Baris verif KUNING via veto (pemicu `veto_rim_protector`, demerit
[total_tinggi]). Baris live TUNGGU_LINEUP (bintang Questionable di
snapshot pagi, sebelum kabar Claxton OUT). **Kedua baris terblokir
dari kedua tiket** — maksud target tercapai. Keputusan koordinator:
tunggu_lineup dihitung "terblokir"; kriteria literal tetap dicatat
di JSON (`lolos: false`, `lolos_fungsional: true`).

### T2 — EQ Asuransi 2–3 kandidat HIJAU → tiket x2 valid: GAGAL

- Kandidat HIJAU+EQ: **5 baris** (DET, ORL, DAL, BOS live + BOS verif)
  = **4 laga berbeda** — bagian jumlah kandidat target ini LOLOS.
- Komposer (7 laga live, stake $30): ORL di-skip pola Denver →
  3 kaki Asuransi (BOS 231,5 @88,5¢; DAL 246,5 @88,5¢; DET 245,5
  @88,5¢) → pengali maks **x1,36** (hitung tangan:
  (100/88,5)³ × 0,945 = 1,3633) < x2,00 → **tiket tidak terbentuk**.
- Utama: 3 sisa HIJAU (DET 241,5 @83¢; DAL 240,5 @80,5¢; BOS 223,5
  @76,5¢) → pengali maks **x1,85** < x3,00 → **tidak terbentuk**.
- Rantai sebab: pola skip 4/7 laga → 3 kaki tersisa → pengali tidak
  mencapai target. Ini masalah JUMLAH KAKI, bukan ambang peluang
  (equilibrium 10/10). Tidak ada ambang dilonggarkan.

### T3 — False positive 4/5 → 0–1: LOLOS (0/5)

0 dari 5 laga pemenang tiket divonis KUNING (v17: 4/5). 2/5 ditahan
timing gate (OKC, IND — bukan KUNING, tapi juga memblokir tiket).
DET@ATL (final 204, menang) HIJAU — di luar penyebut 5 per definisi v17.

### T4 — IND@NYK TUNGGU_LINEUP: LOLOS

Baris live ditahan (Towns BPM +5,4, Siakam USG 27,8%). Artefak verif
tidak memuat IND@NYK.

### T5 — Efisiensi short-circuit: GAGAL literal, LOLOS reformulasi

Target literal Gemini (laga kena veto melompati scan jup.ag) tidak
berlaku di arsitektur ini (scan slate-level). Yang terukur:
**6,85 dtk/laga kena veto** (cache dingin) / 6,83 dtk (hangat) —
sim 3,697 + Kalshi 3,118 + news 0,018 + pemain 0,017 dtk.
Keputusan koordinator: target dirumuskan ulang ke penghematan
terukur; kriteria literal tetap dicatat (`lolos: false`,
`lolos_reformulasi: true`).

---

## 4. Temuan yang tidak diperbaiki diam-diam

1. **Pola Denver over-firing (calon iterasi utama dengan Gemini).**
   4/7 laga live di-skip pola-only (OKC, ORL, DEN, IND); 3 di
   antaranya (OKC final 236, ORL 212, IND 219) MENANG di garis EQ.
   Syarat (2) "tidak ada garis tahan-banjir non-thin" + syarat (4)
   "edge < 3,5%" hampir selalu benar di garis mahal — pola efektif
   menyala pada flag setan + acuan thin saja. Syarat (4) masih
   berbasis edge (kelemahan yang didokumentasikan worker A);
   konversi ke EV adalah tindak lanjut.
2. **MENENGAH 0/10.** Dengan garis EQ yang lebih tinggi, demerit
   kerapuhan ekor hilang — laga yang mungkin MENENGAH menjadi HIJAU.
   Alokasi lama (HIJAU→Asuransi saja, MENENGAH→Utama saja) membuat
   Utama 0 kandidat; diperbaiki dengan aliran sisa HIJAU (§5.4).
3. **Veto buta di 9 tim.** Peta rim protector 21/30; 3 dari 10 laga
   slate 24 Nov melibatkan tim belum terpetakan (OKC@IND, PHX@NOP,
   LAC@HOU) — veto tidak bisa mengevaluasi laga-laga itu.
4. **OT hard-skip dorman.** Ambang 0,085 di atas p_ot maksimum
   0,0575 — gate keras OT tidak pernah menyala di v18.
5. **DEN punya equilibrium di kedua tiket** (Ins 258,5 / Utama 254,5
   di kedua baris). Equilibrium adalah hitungan per garis, BUKAN
   vonis — Denver tetap diblokir vonis (veto/timing gate) + skip_awal
   (pola) + alokasi komposer. Ini perilaku yang benar, dikunci tes.

---

## 5. Keputusan koordinator (menunggu keberatan — detail di DECISIONS.md)

### 5.1 Gate eksekusi = likuiditas + spread (mengganti gate volume worker B)

Bukti: garis DET U239,5 (bid 79/ask 82, likuiditas $36.580) gagal gate
volume $30 karena volume kumulatifnya $5 — padahal order $15 di ask
terisi melawan kuotasi market-maker. Volume kumulatif adalah riwayat,
bukan keterbelian saat ini; config sendiri sudah menulis *likuiditas*
(`execution.min_liquidity_multiplier`). Gate volume memblokir 14/14
kombinasi (row, tiket) di pengukuran B dan membuat Asuransi tidak
terbentuk. Bid/ask adalah kuotasi CLOB asli dari gamma
(`ingest/polymarket.py`); distribusi spread artefak 22 Nov: garis
kandidat 1–3¢, kuotasi mati ≥ 7¢ — **5¢ duduk di celah bersih**.
`max_spread_cents: 5,0` INITIAL + rencana kalibrasi (laporan fill nyata
user di jup.ag). Dampak: equilibrium Asuransi 3/10 → 10/10.

### 5.2 T1 fungsional + 5.3 T5 reformulasi

Lihat §3 (T1, T5). Kriteria literal tetap dicatat di JSON; tidak ada
angka yang disembunyikan.

### 5.4 Sisa HIJAU mengalir ke Utama

Alokasi lama membuang kandidat Utama laga HIJAU → Utama 0 kandidat di
slate uji (MENENGAH 0). "DULU" dalam keputusan user 12:20 WIB dibaca
sebagai prioritas pilih, bukan kepemilikan eksklusif: Asuransi memilih
dulu di tingkat subset, laga HIJAU yang tidak terpakai mengalir ke
Utama; tanpa-kaki-kembar tetap ditegakkan di tingkat subset (sudah ada,
teruji). Dampak di slate uji: Utama 0 → 3 kaki (x1,85, tetap < x3 —
temuan T2 tidak berubah). Tes fail-first baru
(`test_sisa_hijau_mengalir_ke_utama`).

### 5.5–5.10 (ringkas)

Vegas CDF efektif kanonis (§2.8); tidak ada status VETO (veto =
DATA_INCOMPLETE + blok root + KUNING); D7 kualifikasi USG (worker A);
definisi `_sebab_cedera_baru` = OUT + BPM ≥ 2,0 (kelemahan: pemain out
sepanjang musim ikut terhitung); peta rim protector 21/30; hard-skip OT
dorman. Detail + alasan di `DECISIONS.md` § "Implementasi v18".

---

## 6. Keputusan desain worker yang menunggu keberatan

- **A (vonis):** D1–D9 di `LAPORAN-VONIS-V18.md` §9 — termasuk D7 di
  atas, prior OT 0,0575, dan pola Denver tetap berbasis edge.
- **B (gate):** shrinkage Vegas 0,5; fallback band; aturan MODEL_ONLY
  p_market; +3 parsial; gate eksekusi hanya kaki NBA total_under
  (kaki bola/moneyline tidak membawa data volume) — lihat
  `LAPORAN-GATE-V18.md` §9–§10. Pertanyaan `liquidity` vs
  `volume_usd` (§9.6) DIJAWAB koordinator di §5.1.
- **C (demon):** TUNGGU_LINEUP lanjut sebagai draf (status HOLD,
  komposer menahan); definisi `_sebab_cedera_baru`; geser CDF rigid;
  `pct_terbaik_liga` sebagai info — `LAPORAN-DEMON-V18.md` §7.

---

## 7. Batasan jujur

- **Artefak 22 Nov mendahului Vegas/FTr.** Acceptance mengukur gate
  v18 di atas artefak era v17: demerit foul (FTr) belum teruji di
  data nyata; penyesuaian Vegas belum ada di artefak tersimpan
  (kontrafaktual §2.8 dihitung dari median tersimpan).
- **Veto buta di 9 tim** (§4.3). Slate 24 Nov: 3/10 laga terdampak.
- **OT hard-skip dorman** (§4.4); base rate adalah prior, bukan fit.
- **Ambang veto INITIAL** (2 titik data) — butuh validasi ledger.
- **Pola Denver masih berbasis edge** untuk syarat (4) — konversi EV
  adalah tindak lanjut yang didokumentasikan.
- **Tidak ada tiket terbentuk di slate uji** — T2 gagal karena jumlah
  kaki. Slate 24 Nov (10 laga) memberi lebih banyak kandidat, tapi
  bila pola skip ~57% bertahan, Asuransi x2 tetap sulit (butuh 5–6
  kaki @~88¢). Mesin akan melaporkan dengan jujur bila tiket tidak
  terbentuk — jangan paksa.
- **5¢ spread INITIAL** — kalibrasi butuh laporan fill nyata.
- **`_sebab_cedera_baru` tidak membuktikan kesegaran** dari satu
  snapshot (Haliburton out sepanjang musim ikut terhitung).

---

## 8. Siap untuk slate Selasa 24 Nov 2026 (10 laga, tip-off pertama 07:00 WIB)

Mesin v18 siap dipakai di analisis pagi (rencana mulai ~05:00–05:30 WIB).
Yang perlu diperhatikan operator:

1. **Laporkan SEMUA laga termasuk yang di-skip + alasannya**
   (keputusan user 2026-11-23 10:41) — laporan sudah mendukung ini.
2. **3 laga veto-buta:** OKC@IND, PHX@NOP, LAC@HOU (tim belum
   terpetakan di peta rim protector) — veto tidak mengevaluasi;
   andalkan vonis + pola + timing gate.
3. **TUNGGU_LINEUP bukan vonis final** — laga yang ditahan menunggu
   injury report 30 menit pra-tip-off; jangan paksa masuk racik.
4. **Bila tiket tidak terbentuk, itu jawaban yang sah** — laporkan
   pengali maksimum + berapa kaki yang kurang, jangan longgarkan ambang.
5. **Catat fill nyata di jup.ag** (terutama garis spread ~5¢) untuk
   kalibrasi gate eksekusi + ambang veto INITIAL.

---

## 9. Bukti + file

- Acceptance: `scripts/ukur_v18.py` → `out/ukur_v18.json`
  (2/5 literal; T1 fungsional + T5 reformulasi lolos).
- Short-circuit: `out/ukur_short_circuit.json` (6,85 dtk/laga).
- Cutoff FIT liga: `out/fit_cutoff_liga_v18.json` (n=30, 2026-11-23).
- Equilibrium/Asuransi: `out/ukur_equilibrium.json`,
  `out/ukur_asuransi_baru.json` (dijalankan ulang pasca-revisi).
- Tes: 2003/2003 (`python3 -m unittest discover -s tests`, venv
  `~/.venvs/parlay-tools/bin`).
- Lint: `ruff check .` bersih; `black --check .` bersih.
- Config: `config/playstyle.yaml` (v18) — semua ambang baru di sini,
  fail-closed; `config/rim_protector_2026-27.json` (21/30 tim).
- Skema: `schemas/nba_analysis.schema.json` (blok root
  veto/tunggu_lineup/vegas; field kaki liquidity/bid/ask),
  `schemas/simulation.schema.json` (markets_mentah/total_mentah).
- Keputusan user (mengikat, tidak diubah) + catatan implementasi:
  `DECISIONS.md`.
