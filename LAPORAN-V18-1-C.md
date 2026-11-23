# LAPORAN WORKER C — Patch v18.1 bagian C: Peta Rim Protector 30/30 + Script Pengukuran

**Tanggal:** 2026-11-23 (sore WIB)
**Cakupan:** Patch #3 (peta rim protector 21/30 → 30/30) + script pengukuran acceptance test v18.1 (`scripts/ukur_v18_1.py`).
**Bukan cakupan worker ini:** Patch #1 (skip_awal, Worker A), Patch #2 (komposer, Worker B), Patch #4 (kesegaran cedera), Patch #5. Config hanya disentuh di section `hard_vetoes` (baru). Tidak ada operasi git (koordinator yang commit). Config version TIDAK di-bump (koordinator yang bump ke v18.1).

---

## 1. Diagnosa 9 tim yang hilang (data live 2026-11-23 ~16:00 WIB)

Diagnosa dijalankan dengan fungsi-fungsi `scripts/fetch_rim_protector.py` sendiri (`fetch_pemain_blok` + `fetch_posisi_bbref` + `gabung_posisi`), bukan asumsi. Sumber blok: stats.nba.com (474 pemain); posisi: BBRef (478 kunci).

### 1.1 Funnel per tim (aturan primer: GP ≥ 3, MP ≥ 18, BLK ≥ 1,0, pos C/PF/F-C/C-F)

| Tim | Tertarik | Posisi tergabung | Lolos GP ≥ 3 | Lolos MP ≥ 18 | Lolos BLK ≥ 1,0 | Lolos posisi |
|-----|---------:|-----------------:|-------------:|--------------:|----------------:|-------------:|
| ATL | 14 | 14 | 14 | 8 | **0** | 0 |
| DET | 17 | 16 | 16 | 8 | **0** | 0 |
| GSW | 15 | 15 | 15 | 8 | **0** | 0 |
| HOU | 15 | 15 | 15 | 8 | **0** | 0 |
| IND | 16 | 16 | 15 | 9 | **0** | 0 |
| LAC | 16 | 16 | 14 | 8 | **0** | 0 |
| NYK | 16 | 16 | 15 | 6 | **0** | 0 |
| ORL | 14 | 14 | 13 | 7 | **0** | 0 |
| PHX | 15 | 15 | 15 | 8 | **0** | 0 |

### 1.2 Kesimpulan diagnosa: BUKAN mapping, BUKAN normalisasi, BUKAN bug filter

- **Mapping tricode terbukti jalan.** PHX muncul dengan 15 pemain (BBRef `PHO` → `PHX`); BKN/CHA juga terpetakan di peta v18. Hipotesis "kode tim salah" GUGUR dari data.
- **Join posisi hampir sempurna.** 14–16 dari 14–17 pemain per tim mendapat posisi. Satu-satunya pemain tanpa posisi di 9 tim ini adalah Ronald Holland II (DET) — dan itu BUKAN cacat normalisasi: stats.nba.com menulis "Ronald Holland II", BBRef menulis "Ron Holland" (nama panggilan, bukan varian ejaan). Ia juga tidak relevan dengan peta (MP 15,4 < 18, wing).
- **Normalisasi aksen terbukti jalan.** "Yanic Konan Niederhäuser", "Nikola Vučević", "Alperen Şengün" semua cocok dengan pos BBRef.
- **Penyebab sebenarnya: ambang primer BLK ≥ 1,0 terlalu ketat untuk 9 tim ini.** Di SEMUA 9 tim, kolom "Lolos BLK ≥ 1,0" = 0 — tidak ada satu pun pemain rotasi (GP ≥ 3, MP ≥ 18) yang memblokir ≥ 1,0/laga. Big rotasi terbaik mereka hanya 0,8–0,9 blok/laga (lihat §3). Jadi tidak ada bug kode yang diperbaiki di jalur primer — perbaikannya adalah tier fallback terukur sesuai spesifikasi Patch #3 (§2).

### 1.3 Nyaris lolos di tahap lain (bukan penyebab, dicatat untuk audit)

- DET: Jalen Duren 1,0 blok/laga tapi GP = 2 < 3 (keterbatasan yang sudah didokumentasikan di docstring script — pemain 0–2 laga tidak bisa diidentifikasi dari statistik musim berjalan).
- GSW: Al Horford 1,0 blok/laga tapi MP = 17,0 < 18.
- LAC: Isaiah Jackson 1,1 blok/laga tapi MP = 17,7 < 18 (kurang 0,3 menit).
- NYK: James Wiseman 1,0 blok/laga tapi MP = 7,7.

Fallback TIDAK melonggarkan min_games/minutes untuk kasus-kasus ini (lihat §2) — mereka tetap tidak teridentifikasi, sesuai spesifikasi.

---

## 2. Perbaikan: tier fallback terukur

### 2.1 Aturan (di `scripts/fetch_rim_protector.py::turunkan_pemetaan`)

- Bila suatu tim menghasilkan **0 pemain primer**, ambil **top-1** big tim itu dengan GP ≥ min_games (3 — SAMA dengan primer), MP ≥ `fallback_min_minutes_pg` (18,0), BLK ≥ `fallback_min_bpg` (0,7). Urutan sama dengan primer (BPG tertinggi, seri → menit lebih besar → nama abjad, deterministik).
- Fallback **tidak** melonggarkan filter posisi (guard/wing tetap dikeluarkan — cacat v17 tidak kembali), min_games, atau ambang menit.
- Label transparan di tiap entri JSON: `"tier": "primary"` atau `"tier": "fallback"` (kedua tier berlabel eksplisit — dipilih agar audit tidak bergantung pada ketiadaan field).
- Daftar `tanpa_posisi` kini mencatat tier ambang yang dilolosinya (`"tier": "primary"/"fallback"`) — pemain yang lolos ambang fallback tapi posisinya tidak diketahui tetap terlacak.
- `engine/vonis.py` TIDAK diubah: pembaca peta (`_muat_rim_protector` + `evaluasi_veto`) hanya membaca `player` + `blk_per_game`, sehingga field `tier` tambahan bersifat kompatibel-mundur.

### 2.2 Config (HANYA section baru `hard_vetoes`)

```yaml
hard_vetoes:
  rim_protector_veto:
    fallback_tier_enabled: true
    fallback_min_minutes_pg: 18.0
    fallback_min_bpg: 0.7
```

Catatan: section `hard_vetoes` BELUM ADA di playstyle.yaml v18 (definisi primer ada di `vonis.veto.rim_protector`) — section ini dibuat baru sesuai spesifikasi patch (§3 referensi Gemini). Pemisahan primer (`vonis.veto.rim_protector`) vs fallback (`hard_vetoes.rim_protector_veto`) dicatat sebagai keputusan desain yang menunggu keberatan (§6, D2).

Ambang 0,7 dari proposal Gemini §3, ditandai **INITIAL** di komentar config + rencana kalibrasi (ukur korelasi rim protector fallback OUT dengan jebolnya Under di ledger PAPER).

---

## 3. Hasil regenerasi: 30/30

Regenerasi lewat script (`python3 scripts/fetch_rim_protector.py`, live fetch; sumber stats.nba.com, posisi BBRef):

**Tim terpetakan: 30 dari 30 (9 fallback).** 21 tim primer TIDAK BERUBAH SAMA SEKALI (pemain + angka identik dengan peta v18 — diverifikasi dengan diff per entri). `tanpa_posisi`: kosong.

### 3.1 Sembilan tim fallback (semua big sungguhan — spot-check posisi + nama)

| Tim | Pemain | Pos | BLK | MP | GP | Catatan |
|-----|--------|-----|----:|---:|---:|---------|
| ATL | Onyeka Okongwu | C | 0,8 | 30,9 | 17 | Center starter ATL |
| DET | Paul Reed | C | 0,9 | 26,1 | 16 | Seri 0,9 dengan John Collins (PF); menang tie-break menit (26,1 vs 25,7). Guard Cade Cunningham (0,9) + Huerter (0,9) benar dikeluarkan filter posisi |
| GSW | Draymond Green | PF | 0,9 | 25,6 | 14 | |
| HOU | Jabari Smith Jr. | PF | 0,9 | 33,3 | 17 | Seri 0,9 tiga arah (Sengun 33,0 / Eason 24,9); menang tie-break menit |
| IND | Ivica Zubac | C | 0,8 | 24,3 | 12 | |
| LAC | Brook Lopez | C | 0,9 | 24,6 | 15 | Isaiah Jackson (1,1) tetap tidak lolos: MP 17,7 < 18 |
| NYK | OG Anunoby | PF | 0,9 | 34,0 | 15 | **Keputusan menunggu keberatan (§6, D1)** — BBRef pos PF; alternatifnya KAT (C, 0,7) |
| ORL | Wendell Carter Jr. | C | 0,9 | 32,0 | 16 | Guard Anthony Black (PG, 0,8) benar dikeluarkan |
| PHX | Khaman Maluach | C | 0,8 | 18,5 | 15 | |

Tidak ada tim yang tetap 0 pemain setelah fallback — tidak ada pemain yang dikarang, dan tidak ada tim yang dibiarkan tanpa entri.

### 3.2 Slate 24 Nov: 0 tim buta

Semua 20 tim slate 24 Nov terpetakan, termasuk ketiga laga sorotan: OKC@IND, PHX@NOP, LAC@HOU (kedua sisi terpetakan di ketiganya).

### 3.3 Efek samping yang BENAR (bukan regresi)

Fixture sehat sintetis `test_vonis` (IND@NYK) kini mendapat rem alami ketiga `paint_utuh_blowout_atau_ftr_rendah`: di v18 veto tidak dievaluasi (IND+NYK buta), kini veto dievaluasi dan tidak menyala (tidak ada rim protector OUT) sehingga rem paint-utuh menyala. Vonis tetap HIJAU, demerit tetap `["gap_besar"]`. Ini adalah konsekuensi yang dimaksud dari menutup lubang buta, bukan cacat — tes diperbarui dengan penjelasan (§5).

---

## 4. Script pengukuran: `scripts/ukur_v18_1.py`

Tiruan `scripts/ukur_v18.py` (struktur sama: baca 2 artefak → per-baris vonis/skip/equilibrium → 5 kriteria → JSON + tabel). Output: `out/ukur_v18_1.json`. Exit 0 selalu (termasuk kriteria gagal); exit 2 hanya bila file input hilang. 0 kredit Odds API.

### 4.1 Kriteria

1. **skip_awal baru** — via `engine.skip_awal.evaluasi_skip_awal` (defensif `getattr`). DEN@CHI wajib "terblokir" di kedua baris (skip menyala ATAU vonis kuning/tunggu_lineup ATAU veto menyala); OKC@MIA, ORL@WAS, IND@NYK wajib `pola_denver.cocok == False` (dinilai dari pola, bukan skip keseluruhan — laga boleh di-skip pemicu lain seperti OT).
2. **Pemulihan T2** — `compose_tickets` atas 7 laga live (stake $30). Lolos bila Asuransi terbentuk, pengali ≥ 2,00x, tanpa kembar, semua kaki dalam band 80–89¢ (band valid_lines). Joint P_final dihitung dari kaki (perkalian `p_final`). Bila < 2,00x: opsi `insurance_fallback_option` dibaca defensif — bila ada dan pengalinya dalam [1,80x, 1,99x], dicatat `lolos_fallback_terlaporkan` (bukan tiket, bukan lolos literal); bila kunci absen, dicatat `tidak_dievaluasi` (bukan crash).
3. **Peta rim protector 30/30** — baca `config/rim_protector_2026-27.json`: jumlah tim, tim buta di 20 tim slate 24 Nov, 3 laga sorotan (kedua sisi), jumlah tim/entri fallback.
4. **Kesegaran cedera** — artefak SINTETIS via `engine.nba_analysis._sebab_cedera_baru`: Haliburton OUT (2 sumber), BPM 2,5, GP = 0 → wajib TIDAK memicu; kontrol GP = 10 → wajib tetap memicu. Konteks artefak nyata IND@NYK live dicatat terpisah (Haliburton di sana GP = 4, jadi di bawah aturan GP ≥ 3 ia tetap terhitung — konteks, bukan penentu kriteria).
5. **Regresi nol** — koordinator menjalankan full suite dan menulis `out/full_suite_v18_1.json` berformat `{"total": N, "gagal": n, "error": n, "perintah": "..."}`; script membaca file itu bila ada. Bila tidak ada: status `menunggu_koordinator` (bukan gagal, bukan lolos).

### 4.2 Baseline pra-integrasi (dijalankan 2026-11-23 sore, Worker A/B/D belum mendarat)

| Kriteria | Hasil | Penjelasan |
|----------|-------|------------|
| K1 skip_awal baru | GAGAL | DEN terblokir di kedua baris (lolos); OKC/ORL/IND masih kena pola Denver v18 (Worker A belum mendarat) |
| K2 Pemulihan T2 | GAGAL | Asuransi x1,36 (sama dengan v18); kunci `insurance_fallback_option` absen → `tidak_dievaluasi` (Worker B belum mendarat) |
| K3 Peta 30/30 | **LOLOS** | 30 tim, 0 buta, 3/3 laga sorotan tertutup |
| K4 Kesegaran cedera | GAGAL | Kasus GP = 0 masih memicu di kode v18 (Patch #4 belum mendarat); kontrol GP = 10 sudah benar |
| K5 Regresi nol | MENUNGGU | `out/full_suite_v18_1.json` belum ada — koordinator menjalankan full suite di akhir integrasi |
| **Total** | **1/5 (1 menunggu)** | Baseline jujur pra-integrasi; koordinator menjalankan ulang setelah integrasi |

---

## 5. Tes

### 5.1 Tes baru (fail-first): `tests/test_rim_protector_v18_1.py` — 18 tes

Sebelum implementasi: 5 failures + 9 errors (kwarg fallback belum ada, section config belum ada, peta 21 tim tanpa label tier). Setelah implementasi: **18/18 lolos**.

- Tier fallback (8 tes): mengisi tim tanpa primer; top-1 saja (tie-break menit, kasus HOU); tidak menyentuh tim berprimer; label `primary`; menghormati filter posisi (kasus DET: Cade/Huerter dikeluarkan, Paul Reed dipilih); menghormati min_games + menit (Duren GP=2 + Jackson MP=17,7 tetap tidak teridentifikasi); `fallback_enabled=False` = perilaku v18; tim tanpa big fallback tetap tanpa entri (tidak mengarang pemain).
- Normalisasi + tricode (3 tes): aksen dilucuti (Jokić/Şengün/Niederhäuser); join posisi lintas aksen; parse BBRef memetakan PHO→PHX, BRK→BKN, CHO→CHA.
- Config (1 tes): tiga kunci fallback di `hard_vetoes.rim_protector_veto` sesuai spesifikasi.
- Cakupan peta regenerasi (6 tes, membaca JSON yang di-commit): 30/30 tim; 9 tim hilang v18 kini ada; 20 tim slate 24 Nov ada; tiap entri bertier + posisi big + lantai BLK/MP/GP; fallback maksimal 1 per tim (dan tim fallback murni hanya punya 1 entri); `rule.fallback` tercatat di JSON.

### 5.2 Tes lama yang diperbarui (asumsi peta v18 — BUKAN pelemahan)

4 tes gagal setelah regenerasi karena mengunci asumsi v18 (21 tim / BLK ≥ 1,0 untuk semua entri / OG Anunoby tidak ada / veto tidak dievaluasi di IND@NYK). Semuanya diperbarui ke semantik v18.1 dengan komentar alasan di tiap perubahan:

- `tests/test_vonis.py::test_file_pemetaan_valid`: 21 → 30 tim; lantai BLK mengikuti tier (primer ≥ 1,0, fallback ≥ 0,7); tier wajib ada.
- `tests/test_vonis.py::test_laga_sehat_hijau_satu_demerit_gap` + docstring `_analisis_sehat` + docstring modul: rem ketiga `paint_utuh_blowout_atau_ftr_rendah` kini menyala (efek samping yang benar, §3.3).
- `tests/test_veto_and.py::test_guard_tidak_ada`: OG Anunoby keluar dari daftar pengecualian guard (ia PF menurut BBRef, bukan guard) — menunggu keberatan (§6, D1).
- `tests/test_veto_and.py::test_semua_entri_posisi_big`: lantai BLK mengikuti tier; tier wajib ada.

### 5.3 Hasil

- Modul yang disentuh: `test_config`, `test_vonis`, `test_veto_and`, `test_tunggu_lineup`, `test_rim_protector_v18_1` — **180/180 lolos**.
- Full suite: **2021/2021 lolos** (`python3 -m unittest discover -s tests`, 167,8 detik, dijalankan worker C 2026-11-23 sore sebagai pemeriksaan regresi). Catatan: angka ini adalah snapshot saat worker lain masih mendarat paralel (file mereka sudah ada di tree saat suite dijalankan); koordinator tetap menjalankan ulang di akhir integrasi untuk K5.
- `ruff check` + `black --check` bersih pada semua file yang diubah/dibuat (`scripts/fetch_rim_protector.py`, `scripts/ukur_v18_1.py`, `tests/test_rim_protector_v18_1.py`, `tests/test_vonis.py`, `tests/test_veto_and.py`).

---

## 6. Keputusan desain yang menunggu keberatan

- **D1 — OG Anunoby (PF) sebagai entri fallback NYK.** Menurut aturan (posisi BBRef PF + BLK tertinggi tim), OG (0,9) adalah pilihan yang benar; alternatifnya Karl-Anthony Towns (C, 0,7). OG lebih dikenal sebagai wing defender daripada rim protector murni. Bila reviewer menghendaki fallback dibatasi posisi C saja, NYK memakai KAT — perubahan satu baris (filter posisi khusus fallback). Draymond Green (PF, GSW) dan Jabari Smith Jr. (PF, HOU) adalah PF fallback lain yang tidak kontroversial.
- **D2 — Pemisahan section config.** Primer di `vonis.veto.rim_protector`, fallback di `hard_vetoes.rim_protector_veto` (sesuai spesifikasi referensi Gemini §3). Konsolidasi ke satu section dimungkinkan bila koordinator/reviewer menghendaki — script membaca kedua section.
- **D3 — Label tier eksplisit di kedua tier.** Entri primer berlabel `"primary"` (bukan tanpa label) agar audit tidak bergantung pada ketiadaan field. `engine/vonis.py` mengabaikan field ini.
- **D4 — Fallback memakai min_games primer (3).** Spesifikasi Patch #3 tidak menyebut GP untuk fallback; memakai 3 menjaga konsistensi ("peran belum terbentuk" di bawah 3 laga). Konsekuensi: Jalen Duren (DET, 1,0 blok, GP=2) tetap tidak teridentifikasi.
- **D5 — Kriteria 1 mengizinkan DEN "terblokir" lewat veto/vonis, bukan hanya skip.** Sesuai rumusan tugas ("wajib tetap di-skip (dan/atau diblokir veto)").
- **D6 — Kriteria 5 memakai file `out/full_suite_v18_1.json` yang ditulis koordinator.** Bila koordinator memakai mekanisme lain untuk mencatat hasil suite, script cukup diabaikan pada K5 (status menunggu) dan hasil dicatat manual di laporan integrasi.

---

## 7. Batasan jujur

- **Peta adalah snapshot.** Data diambil 2026-11-23 sore; rotasi/cedera berubah — peta perlu di-regenerasi berkala (script sudah mendukung; seminggu sekali atau setelah trade besar, sesuai docstring).
- **Ambang fallback 0,7 INITIAL.** Belum dikalibrasi terhadap hasil nyata; rencana kalibrasi tertulis di komentar config.
- **Pemain 0–2 laga tetap tidak teridentifikasi** (Duren DET; juga Yanic Konan Niederhäuser LAC, 1,0 blok, GP=2). Keterbatasan v18 yang tidak diubah patch ini; perbaikan ke depan (statistik musim lalu) sudah dicatat di docstring script.
- **Satu join nama gagal di seluruh liga yang diperiksa:** Ronald Holland II (DET) — "Ronald Holland II" (stats.nba.com) vs "Ron Holland" (BBRef). Tidak berdampak ke peta (wing, MP 15,4). Perbaikan butuh pencocokan nama panggilan — di luar lingkup patch ini.
- **Script pengukuran K2 tidak memverifikasi ulang setiap gate secara independen** — ia memverifikasi keluaran komposer (band harga, tanpa kembar, pengali) dan mengandalkan komposer sendiri untuk penegakan gate. Verifikasi gate independen adalah pekerjaan audit terpisah.
- **K4 menguji `_sebab_cedera_baru` lewat artefak sintetis** dengan field `games_played` pada entri pemain (field yang sudah ada di artefak nyata). Bila Patch #4 membaca kesegaran dari sumber lain (mis. `missed_last10`), koordinator menyesuaikan kasus sintetis.
- **DECISIONS.md sudah termodifikasi sebelum worker C mulai** (oleh worker lain) — tidak disentuh worker ini.

---

## 8. File yang diubah / dibuat

| File | Perubahan |
|------|-----------|
| `scripts/fetch_rim_protector.py` | Tier fallback di `turunkan_pemetaan` (kwargs baru + label tier + `tanpa_posisi` bertier); `main()` membaca `hard_vetoes.rim_protector_veto`, mencatat `rule.fallback`, mencetak tier |
| `config/playstyle.yaml` | Section BARU `hard_vetoes.rim_protector_veto` (3 kunci). TIDAK ada section lain yang disentuh; version TIDAK di-bump |
| `config/rim_protector_2026-27.json` | Regenerasi: 21 → 30 tim (9 fallback), entri bertier, `rule.fallback` |
| `tests/test_rim_protector_v18_1.py` | BARU — 18 tes fail-first |
| `tests/test_vonis.py` | 2 tes + 2 docstring diperbarui ke semantik v18.1 (§5.2) |
| `tests/test_veto_and.py` | 2 tes + 1 docstring diperbarui ke semantik v18.1 (§5.2) |
| `scripts/ukur_v18_1.py` | BARU — script pengukuran 5 kriteria acceptance v18.1 |
| `out/ukur_v18_1.json` | Output baseline pra-integrasi (runtime, gitignored) |
| `LAPORAN-V18-1-C.md` | Laporan ini |
