# LAPORAN v18.1 — Patch Pra-Slate 24 Nov (Review Gemini atas v18)

**Tanggal:** 2026-11-23 sore WIB · **Config:** v18.1 · **Tes:** 2111/2111 lolos
(dari 2003 di v18) · **Kredit Odds API:** 0 · **Ruff + black:** bersih ·
**Cabang:** main (dari `a6a0d93`)

Sumber: `REFERENSI-PATCH-V18-1-GEMINI.md` (§1–§4) + keputusan user 15:52 WIB
di `DECISIONS.md` (fallback (b) + filosofi "pasti menang" — mengikat).
Laporan worker: `LAPORAN-V18-1-A.md` (Patch #1/#4/#5),
`LAPORAN-V18-1-B.md` (Patch #2), `LAPORAN-V18-1-C.md` (Patch #3 +
pengukuran). Pengukuran: `scripts/ukur_v18_1.py` → `out/ukur_v18_1.json`.

---

## 1. Ringkasan eksekutif

v18.1 membangun 5 patch dari review Gemini atas hasil v18 + fallback
Asuransi (b) sesuai pilihan user. Hasil di slate uji 10 baris:

| Ukuran | v18 | v18.1 |
|---|---|---|
| Vonis HIJAU / MENENGAH / KUNING / TUNGGU | 5 / 0 / 1 / 4 | **5 / 0 / 1 / 4** |
| Equilibrium Asuransi | 10/10 | **10/10** |
| Laga di-skip (skip_awal) | 6/10 | **0/10** |
| Peta rim protector | 21/30 | **30/30** |
| Tiket Asuransi terbentuk (slate live 7 laga) | tidak (maks x1,36) | **tidak (maks x1,86)** |
| Opsi fallback Asuransi terlaporkan | — | **x1,80, joint P 51%** |
| Tiket Utama terbentuk | tidak (maks x1,85) | **tidak (maks x2,30)** |
| False positive (laga pemenang divonis KUNING) | 0/5 | **0/5** |

**Acceptance test Gemini §4 (disesuaikan keputusan user): 4/5.**
K1 LOLOS (fungsional — DEN terblokir kedua baris; pola itu sendiri 0/10,
lihat §4). K2 GAGAL literal (tiket x2 tidak terbentuk) TAPI opsi fallback
[1,80x, 1,99x] TERLAPORKAN sesuai desain (b). K3 LOLOS (30/30). K4 LOLOS.
K5 LOLOS (2111 tes, regresi nol). Tidak ada ambang keamanan inti yang
disentuh (p_final, p_market, banjir, EV, cek_eksekusi).

**Temuan terpenting:** penghalang kini BUKAN skip lagi (0/10) dan BUKAN
ambang (equilibrium 10/10) — melainkan **jumlah kaki + harga di slate
uji 7 laga**: hanya 4 laga HIJAU yang mencapai komposer (3 lainnya
TUNGGU_LINEUP menunggu injury report final), dan 4 kaki termurah yang
lolos gate hanya mencapai x1,86. Di slate 10 laga besok, kandidatnya
lebih banyak — peluang tiket terbentuk lebih besar. Bila tetap tidak
terbentuk, mesin melaporkan opsi fallback + alasan, sesuai keputusan user.

---

## 2. Yang dibangun (5 patch + fallback (b))

### Patch #1 — Perbaiki skip_awal (pola Denver) — `engine/skip_awal.py`

- Syarat (4) edge < 3,5% → **EV < −1%** (`max_ev_for_weak_flag: -0.01`).
- "Non-thin" → **lolos `cek_eksekusi`** (likuiditas ≥ $30, spread ≤ 5,0¢,
  ask < 99¢) di syarat (2) dan (3).
- Flag setan memakai **setan per pemain v18** (cap min(50%, %+12pp));
  fallback setan generik + catatan bila blok tidak ada.
- **Pagar anti-redundansi** (`_evaluasi_pagar`): bila laga tidak kena veto
  DAN punya ≥1 garis lolos 6 gate Equilibrium Asuransi, pola hanya berdiri
  bila (1) garis Asuransi rapuh vs setan (`P_setan < 0,55` ATAU
  `median_setan > garis_asuransi`) DAN (2) total pasar ≥ 232,0 DAN (3)
  tidak ada garis valid yang tahan banjir maupun setan. Pagar hanya bisa
  MEMBLOKIR pola — tidak pernah membuatnya menyala.
- Mode legacy satu-baris-config untuk ketiganya (reversibilitas).
- 30 tes baru, fail-first 29/30.

### Patch #2 — Buka "Perangkap Plafon 88,5¢" — `engine/equilibrium.py`, `engine/ticket_composer.py`, `cli.py`

- `equilibrium.garis_valid_asuransi()`: kembalikan **SEMUA garis valid**
  Asuransi (band 80–89¢, lolos 100% gate) — dibangun di atas
  `nilai_semua_garis`, tanpa duplikasi logika. `cari_equilibrium` tidak
  berubah (plafon safety-first tetap `default_eq`).
- Komposer Asuransi: **DP atas bucket log-pengali** (langkah 0,001) memilih
  kombinasi 2–6 kaki yang memaksimalkan peluang cair gabungan
  (max Σ log decision_prob) dengan pengali bersih di [2,00x, 2,50x].
  Setiap garis kombinasi divalidasi keanggotaannya di valid_lines
  (fail-closed). **Runtime: 0,07 dtk** untuk 10 laga × 9 garis valid
  (target < 5 dtk).
- **Fallback (b)** — keputusan user 15:52 WIB: bila tidak ada kombinasi
  ≥ 2,00x, komposer melaporkan opsi terbaik di [1,80x, 1,99x] sebagai
  `insurance_fallback_option` (label `OPSI_DI_BAWAH_TARGET`, pengali,
  joint P_final, detail per kaki, alasan konkret) — **BUKAN tiket**
  (tanpa ticket_id/type/stake; ledger menolak dengan LedgerError;
  `cli.py` meneruskannya ke `out/tickets_*.json`).
- Bukti fixture: perangkap 4 laga — v18 terkunci x1,54 tanpa tiket →
  v18.1 tiket **x2,04 (4 kaki @82,5¢), joint P 0,7476**. Fixture fallback:
  opsi **x1,81, joint P 0,7831**.
- 25 tes baru (11 equilibrium + 14 komposer), fail-first 20/25.
- 1 tes lama diperbarui (7 kaki @88,5¢ = x2,22 → 6 kaki = x2,01, sesuai
  spek "2–6 kaki"; asersi diperkuat).

### Patch #3 — Peta rim protector 30/30 — `scripts/fetch_rim_protector.py`, `config/rim_protector_2026-27.json`

- **Diagnosa dari data live** (bukan asumsi): 9 tim hilang BUKAN karena
  mapping tricode/nama (join posisi 14–16/14–17 per tim; PHO→PHX jalan;
  aksen cocok) — melainkan karena di semua 9 tim, **0 pemain rotasi
  mencapai BLK ≥ 1,0** (big terbaik hanya 0,8–0,9 blok/laga). Satu-satunya
  join gagal se-liga: Ronald Holland II vs "Ron Holland" (nama panggilan,
  tidak berdampak).
- **Tier fallback terukur**: tim 0 primer → top-1 big (GP ≥ 3, MP ≥ 18,
  BLK ≥ 0,7), label `tier: "fallback"`; filter posisi/min_games/menit
  TIDAK dilonggarkan. Config: `hard_vetoes.rim_protector_veto`
  (fallback_tier_enabled, fallback_min_minutes_pg 18,0, fallback_min_bpg
  0,7).
- Regenerasi live: **30/30 tim (9 fallback)**; 21 tim primer tidak berubah
  sama sekali (diff per entri); 0 tim buta di slate 24 Nov (OKC@IND,
  PHX@NOP, LAC@HOU tertutup). Fallback: Okongwu ATL, Paul Reed DET,
  Draymond GSW, Jabari HOU, Zubac IND, Brook Lopez LAC, OG Anunoby NYK,
  Carter Jr. ORL, Maluach PHX — semua big sungguhan; guard (Cade,
  Huerter, Black) benar dikeluarkan.
- 18 tes baru, fail-first (5 failures + 9 errors sebelum implementasi).

### Patch #4 — Filter kesegaran `_sebab_cedera_baru` — `engine/nba_analysis.py`

- OUT hanya dihitung penyebab gap cedera baru bila **GP ≥ 3** di musim
  berjalan (`calibration.fresh_injury_min_gp_season: 3`; GP dari
  `games_played` BBRef via nba_brain). GP < 3 / tidak tersedia → TIDAK
  segar (fail-closed ke arah shrinkage berjalan) + dicatat. Fungsi kini
  4-tuple `(ada, [nama], dievaluasi, [dikecualikan])`.
- 12 tes baru, fail-first 11/12.
- **Temuan data:** Haliburton di artefak live punya `games_played: 4`
  (bukan 0) + `missed_last10: 10` — filter GP≥3 TIDAK mengecualikannya
  di artefak nyata (K4 lolos pada kasus sintetis GP==0). Lihat §5.

### Patch #5 — Pulihkan MENENGAH_HIJAU + simetri D7 — `engine/vonis.py`

- (a) Demerit tail_fragility dinilai di **garis referensi standar** (garis
  tangga terendah dengan harga ≥ 82¢ yang LOLOS `cek_eksekusi`;
  `vonis.tail_fragility_reference_price_min: 0.82`; fallback ke garis EQ
  + dicatat). **Jebakan garis sampah:** definisi harfiah jatuh ke U117,5
  @82,5¢ (ask 99¢, likuiditas $3,80) — filter eksekusi mencegah demerit
  dinilai di garis khayalan. MENENGAH terbukti via fixture sintetis
  (margin 2,0 → 2 demerit → MENENGAH_HIJAU); 0/10 di slate ini (ORL kini
  1 demerit, tetap HIJAU).
- (b) Simetri D7: filter menit **mp ≥ 15,0** di KEDUA jalur bintang
  TUNGGU_LINEUP (`vonis.tunggu_lineup.min_minutes_pg_all_paths: 15.0`).
  `mp_min_rotasi` 10,0 tetap untuk rem alami + gap besar.
- 22 tes baru, fail-first 14/22.

---

## 3. Acceptance test (§4, disesuaikan keputusan user)

| Kriteria | Hasil |
|---|---|
| **K1** skip_awal baru | **LOLOS (fungsional)** — DEN terblokir kedua baris (live TUNGGU_LINEUP, verif KUNING + veto); OKC/ORL/IND bebas pola. Pola itu sendiri 0/10 (lihat §4). |
| **K2** Pemulihan T2 (tiket x2) | **GAGAL literal** — maks x1,86 (4 kaki). **Fallback TERLAPORKAN**: opsi x1,8015, joint P 0,5107, 4 kaki (BOS 227,5 @83¢, DAL 242,5 @84¢, DET 243,5 @85,5¢, ORL 241,5 @88¢) — semua lolos 100% gate. |
| **K3** Peta 30/30 | **LOLOS** — 30/30 tim, 0 buta di slate 24 Nov. |
| **K4** Kesegaran cedera | **LOLOS** — GP==0 tidak memicu (dikecualikan `gp_di_bawah_minimum`); kontrol GP=10 memicu. |
| **K5** Regresi nol | **LOLOS** — 2111/2111 tes, ruff + black bersih. |

**Verifikasi tangan koordinator (dari `out/ukur_v18_1.json`):**
- Pengali fallback: (100/83)×(100/84)×(100/85,5)×(100/88)×0,945 = **1,8016** ✓
  (terlaporkan 1,8015 — selisih pembulatan).
- Joint P fallback: **0,5107 = Π decision_prob** — BUKAN Π p_final (0,5402).
  Untuk 3 kaki condong-ke-market (BOS/DAL/DET, gap model-pasar > 5,0),
  decision_prob = harga market mentah di garis varian (≈0,825 × 0,835 ×
  0,85); ORL memakai p_final 0,8721. 0,825 × 0,835 × 0,85 × 0,8721 ≈
  **0,5107** ✓. Nilai BENAR sesuai aturan (konservatif, searah
  lean-to-market) — tapi nama kunci `joint_p_final` menyesatkan
  (lihat §5 butir 2).
- Peta: 9 baris `player` ditambahkan (9 tim fallback, 1 pemain tiap tim);
  0 perubahan pada 21 tim primer ✓.
- Vonis: HIJAU 5 / TUNGGU 4 / KUNING 1; skip 0/10; pola cocok 0/10;
  `skipped_matches` komposer [] ✓.

---

## 4. Temuan utama — pola Denver menyala 0/10

Dengan substitusi harfiah spek, pola Denver TIDAK menyala di satu pun
baris — termasuk DEN@CHI live, padahal target mewajibkan DEN tetap
di-skip. Per-syarat DEN live (dari `LAPORAN-V18-1-A.md` §1.4):

| Syarat | DEN live | Keterangan |
|---|---|---|
| S1 flag setan | ✅ | P normal 84,3% vs P setan 52,9% |
| S2 tidak ada tahan-banjir bisa-dibeli | ❌ | garis 266,5 lolos cek_eksekusi (1 garis) |
| S3 garis acuan gagal eksekusi | ❌ | acuan U254,5 lolos (likuiditas $23–32 ribu, spread 3–5¢) |
| S4 EV kecil | ❌ | EV acuan −0,04% > −1% (hampir impas) |

**Akar penyebab:** syarat (2)/(3)/(4) dibangun di atas premis era v16
(garis jauh thin + edge datar) yang SUDAH dibatalkan pengukuran v18
sendiri: orderbook market-maker ternyata dalam ($23–32 ribu + spread
3–5¢ di semua garis tangga — S3 mati struktural di artefak ini), dan
EV garis acuan ≈ impas (S4 mati di DEN). S1 menyala di 10/10 baris —
tidak membedakan DEN dari laga biasa. Bahkan ORL memenuhi LEBIH BANYAK
syarat pola daripada DEN (S1+S2+S4 vs S1 saja). Pagar anti-redundansi
tidak pernah dievaluasi (pola tidak cocok sejak awal; pagar hanya bisa
memblokir).

**Yang tetap melindungi dari DEN:** DEN live TUNGGU_LINEUP (Norman Powell
Questionable, USG 26%, mp 29,5) — tidak masuk kandidat komposer; DEN
verif KUNING via veto AND (Nic Claxton OUT). 0 kaki DEN mencapai komposer
di kedua baris. Mesin AMAN — hanya saja bukan via pola skip.

**Keputusan koordinator (menunggu keberatan + iterasi Gemini):** TIDAK
ADA ambang yang di-retune untuk memaksakan pola menyala (itu overfitting
pada satu titik data). Fungsi skip pola Denver kini ditanggung lapisan
veto + vonis + timing gate + gate equilibrium. Pola butuh REDESAIN
berprinsip — apa yang membedakan DEN sekarang, setelah eksekusi dan EV
tidak lagi membedakan? Kirim pengukuran v18.1 ke Gemini untuk iterasi
(Gemini mengundang ini di penutup §4 spek v18).

---

## 5. Keputusan koordinator (menunggu keberatan)

1. **Batas 6 kaki DIPERTAHANKAN sesuai spek** (Gemini §3
   `max_legs_insurance: 6`; `_DP_MAKS_KAKI = 6` di kode — BUKAN nilai
   config). Trade-off nyata: slate dengan ≥ 7 laga HIJAU yang garis
   validnya semua ≥ 88,5¢ tidak bisa membentuk x2 (maks 6×88,5¢ = x1,97),
   padahal 7 kaki @88,5¢ = x2,22 dan joint P-nya bisa LEBIH TINGGI dari
   4 kaki murah (0,93^7 > 0,85^4); band [2,00x, 2,50x] sendiri membatasi
   kaki maks 8 (di 89¢). **Rekomendasi: naikkan ke 8** (selaras filosofi
   user menumpuk banyak kaki + perilaku komposer v18 yang mengizinkan 7+
   kaki). Satu nilai bila disetujui — tapi `_DP_MAKS_KAKI` perlu dipindah
   ke config dulu (saat ini konstanta kode).
2. **`joint_p_final` = Π decision_prob, bukan Π p_final** (terverifikasi
   §3). Nilai benar + konservatif; nama kunci menyesatkan. Tindak lanjut
   minor: ganti nama jadi `joint_p_keputusan` atau dokumentasikan
   definisinya di docstring komposer + laporan.
3. **Haliburton GP=4 di artefak nyata** — filter GP≥3 tidak
   mengecualikannya (ia main 4 laga lalu absen 10 terakhir). GP≥3 adalah
   proksi kesegaran yang lemah. Rekomendasi: aturan 14-hari /
   `missed_last10` sebagai tindak lanjut (opsi kedua spek Patch #4).
4. **Perbaikan integrasi:** script ukur K4 unpack 3-nilai (kode v18) vs
   4-tuple v18.1 (`_sebab_cedera_baru`) — diperbaiki di
   `scripts/ukur_v18_1.py` (2 tempat); K4 lolos setelahnya. Tidak ada
   perubahan kode produksi untuk ini.
5. **Garis referensi tail_fragility difilter `cek_eksekusi`** (Worker A):
   definisi harfiah jatuh ke garis sampah U117,5 @82,5¢ (ask 99¢,
   likuiditas $3,80).
6. **Pagar syarat (3) "tahan setan" = P_setan ≥ 0,55** (cermin ambang
   rapuh 0,55, INITIAL) — bukan 0,82.
7. **D1 (Worker C):** OG Anunoby (PF BBRef) sebagai fallback NYK —
   alternatifnya KAT (C, 0,7) bila fallback dibatasi C saja.
8. **D2 (Worker C):** pemisahan section config (primer
   `vonis.veto.rim_protector` vs fallback
   `hard_vetoes.rim_protector_veto`) — sesuai spek Gemini §3.

---

## 6. Batasan jujur

- Artefak uji **tanpa blok `setan_pemain` maupun `veto`** (dibangun
  sebelum wiring v18) → S1 terukur via fallback setan generik; jalur
  setan pemain + veto-blok hanya teruji di fixture sintetis. Artefak
  SEGAR besok pagi (dengan kedua blok) bisa memberi angka S1/pagar yang
  berbeda.
- Pagar anti-redundansi **tidak pernah berlaku di slate uji** (pola 0/10)
  — semua bukti pagar dari fixture sintetis.
- MENENGAH terbukti via fixture sintetis, 0/10 di slate ini.
- Demerit foul belum teruji di data nyata (FTr None di artefak 22 Nov).
- OT hard-skip tetap DORMAN (prior 0,0575 tidak diubah — §5.10 spek).
- Ambang pagar 0,55 INITIAL + rencana kalibrasi (ledger).
- Veto bergantung data cedera SEGAR (snapshot sore menangkap Claxton OUT;
  snapshot pagi tidak) — analisis besok pagi WAJIB data segar.

---

## 7. Catatan operasional — slate Selasa 24 Nov (10 laga, tip-off 07:00 WIB)

- Analisis awal ~05:00–05:30 WIB (data cedera segar + injury report final).
- Recheck terarah 30–40 menit sebelum tiap kloter tip-off untuk laga
  TUNGGU_LINEUP (vonis final dari injury report resmi).
- Laporkan SEMUA laga termasuk yang di-skip/ditahan + alasannya.
- Veto kini menutup 30/30 tim (0 buta) — termasuk OKC@IND, PHX@NOP,
  LAC@HOU.
- Bila tiket x2 tidak terbentuk, mesin melaporkan opsi fallback [1,80x,
  1,99x] + joint P + alasan — **itu BUKAN tiket**; keputusan pasang di
  tangan user. Jangan longgarkan ambang untuk memaksakan tiket.
- Catat fill nyata di jup.ag (harga eksekusi vs spread 5¢) untuk
  kalibrasi ledger berikutnya.
