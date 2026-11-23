# LAPORAN WORKER A — Patch v18.1 Bagian A

**Patch #1 (skip_awal) + Patch #4 (kesegaran cedera) + Patch #5 (MENENGAH + simetri D7)**
Tanggal: 2026-11-23. Repo: `muse-parlay-analyst`, branch main, HEAD `a6a0d93`, config **v18 (tidak di-bump — koordinator yang bump ke v18.1)**. Tidak ada operasi git. Tidak ada kredit Odds API dipakai (0).

## Ringkasan

Ketiga patch selesai + hijau. Suite penuh: **2111 tes OK** (termasuk tes worker lain yang sedang berjalan di working tree yang sama), `ruff check` + `black --check` bersih pada semua file yang saya ubah.

| Patch | Tes baru | Fail-first (gagal di kode lama) | Status |
|---|---|---|---|
| #1 skip_awal | 30 (`test_skip_awal_v18_1.py`) | 29/30 (1 lolos = tes reversibilitas mode legacy, sesuai desain) | ✅ selesai |
| #4 kesegaran cedera | 12 (`test_vegas_freshness_v18_1.py`) | 11/12 | ✅ selesai |
| #5 MENENGAH + D7 | 22 (`test_vonis_v18_1.py`) | 14/22 | ✅ selesai |

**⚠️ KONFLIK TARGET — BACA DULU (Patch #1):** dengan substitusi harfiah spek, pola Denver menyala **0/10** baris artefak — termasuk **DEN@CHI live yang TIDAK lagi di-skip via pola**, padahal target tugas mewajibkan DEN tetap di-skip. Ini dilaporkan apa adanya di §1.4; saya TIDAK menutupinya dengan retune ambang. DEN live tetap terblokir fungsional via TUNGGU_LINEUP; DEN verif terblokir veto.

---

## 1. Patch #1 — Perbaiki skip_awal (pola Denver)

### 1.1 Yang dibangun — `engine/skip_awal.py`

**`_evaluasi_pola_denver(analysis, cfg, ktx=None, eq_ins=None)`** — ditulis ulang (v18.1):

- **(a) Syarat (4) EV.** `EV = p_final × (100/harga) − 1 < max_ev_for_weak_flag (−0,01)`. Kunci syarat menjadi `ev_kecil`. Mode legacy (flag `use_ev_instead_of_flat_edge: false`) kembali ke `edge_kecil` + `edge_kecil_pct` (reversibilitas satu baris config; kunci lama dipertahankan di config dengan komentar "DEPRECATED v18.1" — masih dibaca `scripts/ukur_equilibrium.py` + `test_config.py:316`, jadi tidak dihapus).
- **(b) "Non-thin" = lolos `equilibrium.cek_eksekusi`** (likuiditas ≥ $30, spread ≤ 5,0¢, ask < 99¢) di syarat (2) dan (3), menggantikan flag thin volume kumulatif. Mode legacy (flag `use_cek_eksekusi_for_thin: false`) kembali ke flag thin. Bila entri acuan tidak ditemukan di tangga (tidak seharusnya terjadi), fallback ke flag thin + dicatat, bukan crash.
- **(c) Flag setan memakai setan per pemain v18**: geser = `total_setan_pemain − median` dari blok `analysis["setan_pemain"]` (cermin `stress.skenario_panas`, termasuk kill-switch `setan_pemain.enabled`). Bila blok tidak ada / rusak / median hilang → fallback setan generik + alasan tercatat di `detail.setan_fallback` (artefak lama tanpa blok tidak crash). Mode legacy (flag `use_demon_per_player_v18: false`) memakai setan generik.
- **(d) Pagar anti-redundansi** — `_evaluasi_pagar(...)`, dievaluasi HANYA bila keempat syarat cocok. Pagar BERLAKU bila (i) veto dipastikan TIDAK menyala — dibaca dari blok `analysis["veto"]` bila dievaluasi, else dievaluasi langsung via `vonis.evaluasi_veto` (import vonis di skip_awal aman: tidak ada siklus) — DAN (ii) ≥ 1 garis lolos 6 gate Equilibrium Asuransi (`nilai_semua_garis`, gate peluang + p_market + banjir_3p + banjir_ft + ev + eksekusi — TANPA lantai_harga, sesuai daftar spek). Bila berlaku, pola hanya berdiri bila ketiganya benar: (1) garis Asuransi rapuh vs setan (`P_setan_efektif < demon_p_fragile_threshold` ATAU `median_setan > garis_asuransi`; garis Asuransi = garis EQ bila ada, else garis lolos p_final tertinggi), (2) `garis_market ≥ min_market_total_for_pattern (232,0)`, (3) tidak ada garis valid (gate eksekusi + EV lolos) yang tahan banjir (gate banjir 3P + FT lolos) maupun setan (`P_setan_efektif ≥ 0,55`). Kondisi pagar tak bisa dievaluasi karena data hilang → pagar tidak dievaluasi, pola berdiri apa adanya. Pagar tidak pernah MEMBUAT pola menyala — hanya bisa memblokirnya.
- Hasil diperkaya untuk audit: `cocok_tanpa_pagar` (konjungsi mentah), `detail` (geser/sumber setan, EV acuan, jumlah garis tahan banjir yang bisa dibeli), `pagar` (berlaku/memblokir/syarat/alasan), dan `garis_acuan` ditambah kunci v18.1 (`p_setan_efektif`, `setan_sumber`, `ev`, `eksekusi_lolos`, `eksekusi_alasan`, `n_tahan_banjir_bisa_dibeli`) — kunci lama dipertahankan (kompatibilitas).
- `evaluasi_skip_awal` meneruskan `eq_ins` ke pola (untuk pagar). Docstring modul ditulis ulang untuk v18.1.

**`report/nba_report.py`** (bagian pola, ~baris 2214): tampilkan `p_setan_efektif` (fallback `p_setan`); teks "tidak-tipis" → "bisa dibeli (lolos gate eksekusi)"; syarat (4) dibaca dari `ev_kecil` (fallback `edge_kecil`) dengan nilai EV; kasus baru: pola cocok tapi dipagar → baris "keempat syarat cocok tapi DIPAGAR anti-redundansi (alasan…)".

### 1.2 Tes baru — `tests/test_skip_awal_v18_1.py` (30 tes)

- **TestSyarat4EV (5):** keempat syarat benar via EV (acuan 252,5 EV ≈ −4,5%); EV besar mematikan; PEMBEDA EV vs edge (acuan @80,5¢: edge +0,2% < 3,5% tapi EV +0,2% > −1% → tidak memicu); mode legacy edge; kunci EV hilang → ConfigError.
- **TestCekEksekusi (5):** garis tahan banjir bisa dibeli mematikan (2); PEMBEDA flag thin saja tidak cukup (thin=False + likuiditas $5 → syarat (2) tetap benar); acuan bisa dibeli mematikan (3); acuan ask 99¢ gagal eksekusi; mode legacy thin.
- **TestSetanPemain (6):** setan pemain memadamkan flag (total 234,0 → P setan 83,2% ≥ 82%); flag hidup (total 260,0); tanpa blok → fallback generik + catatan; blok rusak → fallback; flag v18.1 nonaktif → generik; kill-switch `setan_pemain.enabled=false` → generik.
- **TestPagarAntiRedundansi (9):** berlaku + ketiga syarat benar → pola berdiri (fixture pagar: EQ 260,5, P setan 51,0% < 55%, pasar 241,5, tidak ada garis valid tahan); memblokir karena garis Asuransi tidak rapuh; tidak berlaku karena veto menyala / veto tidak diketahui / tanpa garis lolos gate; syarat (2) sendiri salah (cfg ambang pasar 250,0) → memblokir; syarat (1) salah (cfg ambang setan 0,10) → memblokir; syarat (3) sendiri salah (garis valid tahan @78,5¢ di bawah lantai) → memblokir; veto live tanpa blok (IND@NYK terpetakan).
- **TestArtefakNyataV18_1 (5):** DEN live tidak di-skip (per-syarat); DEN verif tidak di-skip pola tapi veto menyala (Claxton OUT); OKC/ORL/IND live tidak di-skip (per-syarat); BOS verif lolos; rekap 0/10.

### 1.3 Tes lama yang diperbarui — `tests/test_skip_awal.py`

- Fixture `_analisis_pola_denver` direkayasa ulang: acuan 252,5 @84,5¢ jup (EV ≈ −4,5%); acuan + garis tahan banjir 264,5–270,5 gagal eksekusi (likuiditas $5); flag thin dipertahankan (asersi `n_tahan_banjir_nonthin == 0` tetap berlaku). Helper `_tangga` diperluas: elemen ke-5 = dict override per baris (likuiditas/bid/ask).
- `test_syarat2/3_mati_*`: manipulasi kini memulihkan likuiditas (bukan hanya flag thin). `test_syarat4_mati_edge_besar` → `test_syarat4_mati_ev_besar`. Kedua tes tangga jarang: 250,5 @99,5¢ jup (ask 99,5¢ → gagal eksekusi; EV −1,9%/−17,2%); tes flag-mati kini di-skip via (a) (bukan tanpa pemicu) — poin tes dipertahankan (syarat (1) sendirian memblokir pola). `test_pemicu_ganda_pola_dan_ot` disederhanakan (manipulasi harga dihapus — fixture sudah memenuhi syarat). `test_fixture_den_sintetis_tidak_di_skip`: EV +1,8% → syarat (4) kini SALAH (perbaikan kelemahan edge datar v18).
- Tes artefak: `test_den_live_di_skip_pola_denver` → `test_den_live_tidak_di_skip_pola_v18_1` (per-syarat + catatan konflik); `test_den_verif_di_skip_pola_denver` → `test_den_verif_tidak_di_skip_pola_tapi_veto_menyala`; `test_okc_verif_tidak_di_skip` + `test_dal_dan_bos_live_tidak_di_skip`: kunci `edge_kecil` → `ev_kecil` (nilai: OKC verif EV +6,6%, DAL +6,0%, BOS +8,2%); `test_enam_dari_sepuluh_baris_di_skip` → `test_nol_dari_sepuluh_baris_di_skip_v18_1`.
- `tests/test_ticket_composer.py` (TestEquilibriumSkipIntegrasi): `test_skip_den_artefak_nyata_di_komposer` → `test_den_artefak_nyata_tidak_skip_awal_tapi_tunggu_lineup_v18_1` (`skipped_matches == []`, DEN tidak masuk kandidat via TUNGGU_LINEUP, ORL kini kandidat kedua tiket); `test_flag_dimatikan_perilaku_lama_persis`: skipped 4 → 0, + kandidat ORL (Asuransi 241,5 / Utama 235,5) + DEN/IND/OKC absen via TUNGGU_LINEUP.
- `tests/test_report_nba.py` (TestEquilibriumSkip): fixture `_artefak()` pola tidak lagi cocok (EV acuan +2,3%) → `test_bagian_hadir_dan_skip_pola_denver` → `test_bagian_hadir_dan_skip_tanpa_equilibrium_v18_1`; tes baru `test_varian_pola_cocok_ev_kecil` (acuan @79,5¢ → EV −2,2% → COCOK, cabang laporan tetap teruji); `test_spanduk_skip_di_ringkasan` + `test_json_memuat_bagian_equilibrium_skip` disesuaikan.

### 1.4 Hasil ukur — implementasi nyata atas 10 baris artefak 22 Nov

Script sementara `/tmp/ukur_v18_1_final.py` (JANGAN commit; `/tmp/ukur_v18_1.py` lama adalah pra-implementasi). S1=flag_setan, S2=tidak ada tahan-banjir bisa-dibeli, S3=acuan gagal eksekusi, S4=EV kecil.

| Baris | Skip | S1 | S2 | S3 | S4 | Acuan | EV acuan | Garis tahan bisa-dibeli |
|---|---|---|---|---|---|---|---|---|
| BOS live | ❌ | ✅ | ❌ | ❌ | ❌ | U217,5 | +8,2% | 6 |
| DAL live | ❌ | ✅ | ❌ | ❌ | ❌ | U234,5 | +6,0% | 4 |
| **DEN live** | ❌ | ✅ | ❌ | ❌ | ❌ | U254,5 | **−0,04%** | 1 |
| DET live | ❌ | ✅ | ❌ | ❌ | ❌ | U237,5 | +1,5% | 4 |
| IND live | ❌ | ✅ | ❌ | ❌ | ❌ | U226,5 | +2,6% | 4 |
| OKC live | ❌ | ✅ | ✅ | ❌ | ❌ | U246,5 | +0,6% | 0 |
| ORL live | ❌ | ✅ | ✅ | ❌ | ✅ | U239,5 | −2,4% | 0 |
| BOS verif | ❌ | ✅ | ❌ | ❌ | ❌ | U221,5 | +3,2% | 4 |
| DEN verif | ❌ | ✅ | ❌ | ❌ | ❌ | U252,5 | +1,0% | 2 |
| OKC verif | ❌ | ✅ | ❌ | ❌ | ❌ | U238,5 | +6,6% | 5 |

**Total di-skip via pola: 0/10 (v18: 6/10).** Target OKC/ORL/IND lolos ✅. Target DEN tetap di-skip ❌ — KONFLIK, analisis penyebab:

1. **S3 mati di semua baris:** semua garis tangga artefak live punya `volume_usd=None` sehingga flag thin lama True di mana-mana (vacuous), tapi likuiditas $23–32 ribu + spread 3–5¢ → `cek_eksekusi` lolos di mana-mana. Definisi "bisa dibeli" yang baru secara struktural mematikan S3 di artefak ini.
2. **S4 mematikan DEN sendirian:** EV acuan DEN live −0,04% > −1% (hampir impas, bukan "kecil"). Syarat (4) berbasis EV saja sudah cukup menggugurkan DEN.
3. **S2 mati di DEN:** garis tahan banjir 266,5 lolos cek_eksekusi (1 garis).
4. **Pagar tidak menyelamatkan DEN:** pagar hanya bisa MEMBLOKIR pola yang cocok — DEN tidak cocok sejak awal, jadi pagar tidak dievaluasi (pagar berlaku False di 10/10 baris karena pola tidak cocok).

**Yang tetap melindungi dari DEN:** DEN live TUNGGU_LINEUP (Norman Powell Questionable, USG 26%, mp 29,5) — tidak masuk kandidat komposer; DEN verif KUNING via veto AND (Nic Claxton OUT). Di komposer live: `skipped_matches == []`, kandidat Asuransi/Utama = BOS/DAL/DET/ORL (ORL baru masuk berkat patch ini); DEN/IND/OKC tercoret via TUNGGU_LINEUP. Tiket tetap tidak terbentuk (Asuransi maks x1,86 < x2,00; Utama x2,30 < x3,00) — penghalang kini jumlah kaki + harga, bukan skip.

**Keputusan yang dibutuhkan koordinator/user (bukan saya):** apakah target "DEN wajib di-skip via pola" dipertahankan dengan mengubah spek (mis. ambang EV, definisi eksekusi, atau syarat tambahan), atau diterima bahwa DEN ditangkap veto + TUNGGU_LINEUP. Saya tidak mengubah satu pun ambang untuk memaksakan hasil.

### 1.5 Batasan Patch #1

- Artefak uji **tidak punya blok `setan_pemain` maupun `veto`** (dibangun sebelum wiring v18) → semua pengukuran S1 memakai fallback setan generik; jalur setan pemain + veto blok hanya teruji di fixture sintetis. Bila pipeline menulis kedua blok itu, angka S1/pagar bisa berubah.
- Veto live tidak bisa dievaluasi di DET + IND live (tim belum di peta rim protector — ranah Patch #3 worker lain); pagar di baris itu mengandalkan blok veto / evaluasi live yang gagal → pagar tidak berlaku.
- Pagar hanya dievaluasi bila pola cocok — tidak ada baris artefak nyata yang menguji pagar berlaku (0/10 pola cocok). Semua bukti pagar dari fixture sintetis.

---

## 2. Patch #4 — Filter kesegaran `_sebab_cedera_baru`

### 2.1 Yang dibangun — `engine/nba_analysis.py`

`_sebab_cedera_baru(artefak, cfg)` kini mengembalikan 4-tuple `(ada, [nama], dievaluasi, [dikecualikan])`. Pemain OUT hanya dihitung penyebab gap cedera baru bila **GP ≥ 3** di musim berjalan (`calibration.fresh_injury_min_gp_season: 3`). GP dibaca dari field `games_played` pemain di `inputs` (BBRef via nba_brain — sumber yang sudah ada di jalur ini). GP < 3 atau tidak tersedia → TIDAK segar (fail-closed ke arah shrinkage berjalan) + dicatat (`gp_di_bawah_minimum` / `gp_tidak_tersedia`). Bila kunci GP hilang sama sekali → `dievaluasi=False` (konsisten dengan ambang BPM). `_terapkan_vegas` meneruskan `dikecualikan_gp` ke `vegas_info["sebab_cedera_baru"]`.

### 2.2 Tes — `tests/test_vegas_freshness_v18_1.py` (12 tes, fail-first 11/12)

Haliburton (GP 0) tidak lagi memicu; pemain GP ≥ 3 yang baru OUT tetap memicu; GP tidak tersedia → fail-closed + dicatat; GP 2 → dikecualikan; campuran segar + tidak segar; kunci GP hilang → tidak dievaluasi. Tes lama diperbarui: `tests/test_short_circuit.py` (TestSebabCederaBaru: CFG + unpack 4 nilai + fixture `games_played`), `tests/test_nba_analysis.py` (`_blok_tim` tambah `"games_played": 12`).

### 2.3 Batasan Patch #4

- **Haliburton di artefak live punya `games_played: 4` (bukan 0!) + `missed_last10: 10`** — filter GP≥3 TIDAK mengecualikannya di artefak live. Tes memakai fixture GP 0 sesuai spek tugas. Bila GP artefak memang 4 untuk pemain yang belum main musim ini, ada masalah data hulu (bukan di filter ini) — perlu dicek sumber BBRef.
- Tidak ada field "out for season" terstruktur; GP satu-satunya operasionalisasi. Alternatif "main dalam 14 hari" tidak diimplementasi.

---

## 3. Patch #5 — Pulihkan MENENGAH_HIJAU + simetri D7

### 3.1 Yang dibangun — `engine/vonis.py`

**(a) Garis referensi tail_fragility** — helper baru `_garis_referensi_tail_fragility(ktx, garis_asuransi, harga_min_ref, geser_3p, geser_ft, cfg)`: garis tangga TERENDAH dengan harga ≥ `vonis.tail_fragility_reference_price_min (0,82)` yang LOLOS `cek_eksekusi`; bila tidak ada → fallback ke garis EQ + dicatat. Demerit (a) tail_fragility kini dinilai di garis referensi (bukan di plafon EQ 88,5¢); P banjir di garis Asuransi tetap dipakai untuk alasan HIJAU + indikator. Indikator baru `garis_referensi_tail_fragility` (line, harga, sumber, fallback, p_banjir_3p/ft).

**Jebakan garis sampah (keputusan desain):** definisi harfiah "garis terendah harga ≥ 82¢" jatuh ke U117,5 @82,5¢ (ask 99¢, likuiditas $3,80, DET live) — garis yang tidak bisa dibeli. Karena itu referensi difilter `cek_eksekusi` lolos. Tanpa filter ini, demerit akan dinilai di garis khayalan.

**(b) Simetri D7** — helper baru `_lolos_jalur_bpm` (cermin `_lolos_jalur_usg`); `cek_tunggu_lineup`: KEDUA jalur bintang (USG ≥ 24% DAN BPM ≥ +2,0) memakai `min_minutes_pg_all_paths: 15,0`. Item `diperiksa` tambah `bpm_ditolak`. `mp_min_rotasi` 10,0 TETAP untuk rem alami + gap besar (di luar timing gate). Docstring modul diperbarui.

**Bug yang saya buat + perbaiki (jujur):** edit helper baru sempat menelan baris `def _peta_bpm` sehingga body-nya yatim (dead code setelah `return`) → `NameError` di 13 tes. Diperbaiki dengan mengembalikan baris def; suite hijau setelahnya. Juga: tes baru saya sempat memanggil `nilai_vonis(fixture, CFG)` dengan CFG di posisi `hasil_stress` (signature `nilai_vonis(analysis, hasil_stress, cfg)`) — dua tes override-config menangkapnya; diperbaiki ke `nilai_vonis(fixture, None, CFG)`.

### 3.2 Tes baru — `tests/test_vonis_v18_1.py` (22 tes, fail-first 14/22)

- **TestGarisReferensiTailFragility (9):** fixture pemisah terverifikasi numerik (median 233, sigma 19,2, kemiringan harga 2,17¢/2pt): REF U250,5 @82,0¢ (p3 0,680/pf 0,602, rapuh) vs EQ U256,5 @88,5¢ (p3 0,782/pf 0,716, tahan) → 1 demerit, HIJAU; margin 2,0 → 2 demerit → MENENGAH_HIJAU; harga datar (tanpa garis ≥ 82¢) → fallback EQ + dicatat; garis sampah U117,5 dilewati; ambang dari config (0,90 → ref naik); kunci hilang → ConfigError; ORL live demerit 0→1 tetap HIJAU; DET live tanpa demerit.
- **TestSimetriD7 (13):** BPM mp 14,9 ditolak / mp 15,0 lolos; USG mp 14,9 ditolak / mp 15,0 lolos; BPM mp 29,5 Questionable → TUNGGU; ambang dari config; kunci hilang → ConfigError; artefak nyata DEN/IND/OKC TUNGGU tidak berubah (bintang nyata semua mp ≥ 29).

### 3.3 Tes lama yang diperbarui

- `tests/test_vonis.py`: `test_orl_live_hijau_nol_demerit` → `test_orl_live_hijau_satu_demerit_referensi` (ORL kini demerit `["tail_fragility"]`, tetap HIJAU); fixture `_analisis_sehat` kini baseline MENENGAH_HIJAU 2 demerit (gap_besar + tail di referensi U232,5 @82,5¢, banjir FT 50,0% < 67% karena CDF sempit sigma 5) → `test_laga_sehat_hijau_satu_demerit_gap` → `test_laga_sehat_menengah_dua_demerit_v18_1` (nilai beku p_banjir/gap/EQ TIDAK berubah), `test_volume_bukan_demerit_v18`, `test_gap_besar_dengan_cedera_jadi_investigasi` (demerit kini `["tail_fragility"]`, tetap HIJAU), `test_tanpa_garis_bandar_*`, `test_tanpa_ot_sim_tetap_hijau` → `test_tanpa_ot_sim_tidak_mengubah_vonis` (banding baseline), `test_hasil_stress_rusak_tidak_crash` (banding baseline), `test_veto_tidak_dievaluasi_tanpa_data_cedera`; komentar `test_hasil_stress_dipakai_bila_garis_cocok` dikoreksi (demerit kini dari garis referensi, bukan P suntik).
- `tests/test_tunggu_lineup.py`: RayJ Dennis (mp 11,5) kini ditolak sebagai `bukan_rotasi` (bukan `bpm_negatif`) di 2 tes — hasil sama (bukan bintang), alasan penolakan berubah karena ambang 15,0.

### 3.4 Hasil ukur — vonis v18.1 atas 10 baris

Distribusi **tetap 5/0/1/4** (HIJAU 5 / MENENGAH 0 / KUNING 1 / TUNGGU 4). Perubahan satu-satunya: ORL live 0→1 demerit (tail_fragility di ref U237,5 @84,0¢, p3 0,675/pf 0,596), tetap HIJAU. BOS/DAL/DET/BOS-verif tanpa demerit di garis referensi; DEN verif KUNING (total_tinggi; ref U254,5 tahan banjir). **MENENGAH_HIJAU tetap 0/10 di slate ini** — mekanismenya bekerja (dibuktikan fixture sintetis margin 2,0 → MENENGAH_HIJAU), tapi tidak ada laga nyata slate ini yang mencapai 2 demerit. Garis referensi selalu ditemukan tanpa fallback di 6 baris yang dinilai (4 TUNGGU tidak sampai ke demerit).

### 3.5 Batasan Patch #5

- Ambang referensi 0,82¢ berasal dari spek (bukan fit data) — nilainya selaras lantai harga Asuransi 80¢ + 2¢, tapi bukan hasil kalibrasi.
- Fixture `_analisis_sehat` (sigma 5, tidak realistis untuk total NBA) kini MENENGAH — ini konsekuensi jujur aturan baru pada CDF sempit, bukan bug.

---

## 4. Kunci config baru — `config/playstyle.yaml` (version tetap 18)

Hanya section `skip_awal` + `calibration` + `vonis` yang saya sentuh (insurance/hard_vetoes tidak disentuh).

| Kunci | Nilai | Status |
|---|---|---|
| `skip_awal.pola_denver.use_ev_instead_of_flat_edge` | `true` | baru |
| `skip_awal.pola_denver.max_ev_for_weak_flag` | `−0.01` | baru (selaras gate EV Asuransi) |
| `skip_awal.pola_denver.use_cek_eksekusi_for_thin` | `true` | baru |
| `skip_awal.pola_denver.use_demon_per_player_v18` | `true` | baru |
| `skip_awal.pola_denver.demon_p_fragile_threshold` | `0.55` | baru, **INITIAL** + rencana kalibrasi di komentar |
| `skip_awal.pola_denver.min_market_total_for_pattern` | `232.0` | baru (selaras veto) |
| `skip_awal.pola_denver.edge_kecil_pct` | `3.5` | DIPERTAHANKAN, komentar "DEPRECATED v18.1" (mode legacy + `ukur_equilibrium.py` + `test_config.py:316`) |
| `calibration.fresh_injury_min_gp_season` | `3` | baru |
| `vonis.tail_fragility_reference_price_min` | `0.82` | baru |
| `vonis.tunggu_lineup.min_minutes_pg_all_paths` | `15.0` | baru |

**Catatan penempatan:** tugas menulis `verdict.tail_fragility_reference_price_min`, tapi tidak ada section `verdict:` di config — kunci ditaruh di `vonis:` (tempat semua ambang vonis tinggal). Bila koordinator menghendaki section `verdict:` terpisah, itu pemindahan satu kunci + satu baris kode.

---

## 5. Keputusan desain yang menunggu keberatan

1. **Pagar syarat (3) — ambang "tahan setan" 0,55 (cermin), bukan 0,82.** Spek tidak memberi angka; 0,55 dipilih sebagai cermin `demon_p_fragile_threshold` (konsisten: rapuh < 0,55 ⟺ tahan ≥ 0,55). Alternatif 0,82 (target Asuransi) akan membuat syarat (3) hampir selalu benar (tidak ada garis yang tahan setan di 0,82) sehingga pagar praktis tidak pernah memblokir via (3). Bila reviewer menghendaki 0,82, satu baris berubah + fixture pagar syarat (3) perlu direkayasa ulang.
2. **Garis referensi tail_fragility difilter `cek_eksekusi`** (bukan definisi harfiah "garis terendah harga ≥ 82¢") — karena definisi harfiah jatuh ke garis sampah U117,5 yang tidak bisa dibeli (lihat §3.1).
3. **Kunci syarat dipertahankan** (`garis_acuan_thin`, `tidak_ada_tahan_banjir_nonthin`) dengan semantik baru (gagal/lolos gate eksekusi), hanya kunci syarat (4) yang berubah (`edge_kecil` → `ev_kecil`). Alasan: meminimalkan ripple ke laporan + tes; semantik baru didokumentasikan di docstring + komentar config. Alternatif: ganti nama kunci (breaking change untuk konsumen JSON ukur).
4. **Pagar hanya dievaluasi bila pola cocok** (bukan selalu) — menghemat evaluasi veto + `nilai_semua_garis` di laga yang polanya tidak cocok; alasan "pagar tidak dievaluasi" tercatat.
5. **Garis Asuransi pagar = garis EQ bila ada, else garis lolos p_final tertinggi** (bila EQ tidak ada tapi ada garis lolos 6 gate — kasus tepi: EQ gagal karena lantai harga sementara garis lolos 6 gate ada di bawah lantai).
6. **`mp_min_rotasi` 10,0 dipertahankan** untuk rem alami + gap besar (bukan dinaikkan ke 15,0) — spek simetri hanya menyasar timing gate; menaikkan 10,0 akan mengubah definisi pemain berdampak di luar gate.

---

## 6. Verifikasi

- Suite penuh: **2111 tes OK** (`python3 -m unittest discover -s tests`, ~60 dtk). Tes yang saya sentuh langsung: 295 tes OK (skip_awal ×2, vonis ×2, tunggu_lineup, vegas_freshness, short_circuit, nba_analysis, config) + report_nba 48 + ticket_composer (TestEquilibriumSkipIntegrasi 4).
- `ruff check` bersih + `black --check` bersih pada 14 file yang saya ubah (9 file diformat ulang black — semua hunk adalah baris saya sendiri; file bersama worker lain dicek per-hunk sebelum diformat).
- Fail-first: Patch #1 29/30 gagal di kode lama; Patch #4 11/12; Patch #5 14/22. Satu-satunya tes baru yang lolos di kode lama adalah tes reversibilitas mode legacy (Patch #1) — sesuai desain.

---

## 7. Daftar file yang diubah (Worker A)

**Kode:**
- `engine/skip_awal.py` — Patch #1 (tulis ulang `_evaluasi_pola_denver`, baru `_evaluasi_pagar`, `_geser_setan_efektif`, `_setan_pemain_diaktifkan`, `_cfg_bool`, `_cfg_angka`; +501/−61 baris)
- `engine/nba_analysis.py` — Patch #4 (`_sebab_cedera_baru` 4-tuple + filter GP; `_terapkan_vegas`)
- `engine/vonis.py` — Patch #5 (`_lolos_jalur_bpm`, `_garis_referensi_tail_fragility`, `cek_tunggu_lineup` simetri 15,0, `nilai_vonis` demerit di referensi)
- `report/nba_report.py` — Patch #1 (bagian pola: EV + eksekusi + pagar)
- `config/playstyle.yaml` — 10 kunci baru (lihat §4); version tetap 18

**Tes baru:**
- `tests/test_skip_awal_v18_1.py` (30 tes, 781 baris)
- `tests/test_vonis_v18_1.py` (22 tes, 409 baris)
- `tests/test_vegas_freshness_v18_1.py` (12 tes, 227 baris)

**Tes lama diperbarui:**
- `tests/test_skip_awal.py`, `tests/test_vonis.py`, `tests/test_tunggu_lineup.py`, `tests/test_short_circuit.py`, `tests/test_nba_analysis.py`, `tests/test_report_nba.py`, `tests/test_ticket_composer.py`

**Tidak disentuh:** `DECISIONS.md` (sudah Modified oleh worker lain sejak awal), `insurance`/`hard_vetoes` di config, operasi git apa pun.

**Catatan untuk koordinator:** file bersama worker lain (`engine/vonis.py`, `engine/nba_analysis.py`, `report/nba_report.py`, `tests/test_vonis.py`, `tests/test_ticket_composer.py`, `tests/test_report_nba.py`, `config/playstyle.yaml`) mengandung perubahan paralel — harap merge per-hunk. Script ukur sementara ada di `/tmp/ukur_v18_1.py` (pra-implementasi) + `/tmp/ukur_v18_1_final.py` (pasca-implementasi) — keduanya JANGAN di-commit.
