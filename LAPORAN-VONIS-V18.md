# LAPORAN WORKER A — v18: vonis baru + veto AND + OT empiris + timing gate + config v18

**Repo:** `~/workspace/projects/muse-parlay-analyst`, branch main, dari commit `ad2cfa0` (config v17, 1806 tes).
**Tanggal:** 2026-11-23. **Status:** selesai — semua item tugas dikerjakan; **tidak ada commit/push/stash** (sesuai instruksi); `DECISIONS.md` / `LAPORAN-V18.md` tidak disentuh.
**Biaya:** 0 kredit Odds API (semua tarikan live dari stats.nba.com + Basketball-Reference, gratis).

## Ringkasan hasil

| Area | Status |
|---|---|
| Config v18 (`meta.version` 18) | ✅ selesai, dimuat + dites |
| Vonis baru (`engine/vonis.py`) | ✅ ditulis ulang, signature publik tetap |
| Veto AND + filter posisi | ✅ selesai, pemetaan regenerate dari data live |
| OT empiris (`engine/ot_empiris.py` baru) | ✅ selesai, rumus + hard-skip dormant didokumentasikan |
| Timing gate TUNGGU_LINEUP | ✅ selesai, termasuk kualifikasi jalur USG (temuan baru, lihat D7) |
| FTr + 3PAr di statistik tim | ✅ selesai (Base fetch baru + merge nba_brain) |
| `ingest/pemain_usg.py` (baru) | ✅ selesai, terverifikasi live (474 pemain) |
| `engine/skip_awal.py` (pemicu OT) | ✅ selesai (OT empiris; pola Denver dipertahankan — lihat §8) |
| Schema status `tunggu_lineup` | ✅ selesai |
| Tes milik worker A | ✅ **148/148 lolos** (4 file baru/dirombak + tes OT di `test_skip_awal.py`) |
| Full suite | ⚠️ **1982 tes, 144 bermasalah (36 gagal + 108 error) — 0 di file milik worker A.** Semua 144 ada di file worker lain / file yang belum diperbarui ke v18 (rincian §10). Angka ini bergerak: worker B sedang aktif memperbaiki `test_ticket_composer.py` (28 → 21 antar run). |

**Distribusi vonis slate uji 22 Nov (10 baris, diukur dengan kode v18):**

| Vonis | v17 | v18 |
|---|---|---|
| HIJAU | 0 | **5** (DET, ORL, DAL, BOS live, BOS verif) |
| MENENGAH_HIJAU | 2 | **0** |
| KUNING | 8 | **1** (DEN verif — veto) |
| TUNGGU_LINEUP | — | **4** (OKC live, DEN live, IND, OKC verif) |

Kriteria penerimaan Gemini §4 (dari brief): DEN tetap KUNING ✅ (DEN verif; DEN live TUNGGU_LINEUP karena Powell Questionable — perilaku gate yang benar, bukan kegagalan); ≥2–3 kandidat HIJAU ✅ (5); KUNING positif-palsu 4/5 → 0–1 ✅ (1, veto asli); bintang Questionable → TUNGGU_LINEUP ✅.

---

## 1. Config v18 — `config/playstyle.yaml` (satu-satunya penulis file ini)

`meta.version` 17 → 18. Semua kunci dari proposal Gemini §3 + keputusan user 2026-11-23 13:57/13:59 WIB.

### 1.1 Tiket + eksekusi

- `tickets.insurance`: multiplier 2.0/2.5 (**TETAP x2 — usulan Gemini 1,80x ditolak user**, keputusan #1), `min_leg_prob` 0.82, `min_p_market` 0.80, `max_negative_ev_pct` **−1.0 (BARU, menggantikan `min_edge_pct` — kunci itu DIHAPUS)**, `flood_3p_min` 0.70, `flood_ft_min` 0.65 (keputusan #2), `preferred_price_band` [80, 89], `must_cover_total_stake` true (tetap).
- `tickets.main`: multiplier 3.0/5.0, `target_multiplier_max` 3.5 (tetap), `min_leg_prob` **0.74** (keputusan #3), `max_negative_ev_pct` **−2.0 (BARU)**, `preferred_price_band` [76, 84], `tiebreak_er_tolerance` **0.015 (BARU)**.
- `execution` (section BARU): `min_liquidity_multiplier` 2.0, `liquidity_hard_min_usd` 25.0, `stake_default_usd` 15.0.
- `stress_gate_scenario` SENGAJA DIPERTAHANKAN (dengan komentar): worker B yang memutuskan nasibnya; kode v17 masih membacanya saat config ditulis. (Worker B sudah mendaratkan equilibrium v18 setelahnya — koordinator yang memutuskan apakah kunci ini akhirnya dihapus.)

### 1.2 Vonis (rombak penuh)

Dihapus: `edge_hijau_pct`, `p_setan_hijau`, `gap_kecil_pct`, `max_demerit_menengah`, `veto_total_tinggi_points`, `veto_pace_tinggi`, `ekor_jauh_points`, `ekor_harga_rendah_cents`, `rim_protector` tingkat-atas (pindah ke bawah `veto`).

Baru/diubah:

| Kunci | Nilai | Asal |
|---|---|---|
| `tail_fragility.p_flood_3p_below` | 0.72 | Proposal Gemini §3 |
| `tail_fragility.p_flood_ft_below` | 0.67 | Proposal Gemini §3 |
| `total_tinggi_points` | 235.0 | Tetap (v17) |
| `ekor_gemuk.min_offset_points` / `max_price_cents` | 16.0 / 80 | Diperketat dari 10/85 (proposal §3) |
| `foul.ftr_p80` / `foul.ftr_p50` | 0.308111 / 0.274398 | **FIT** (lihat §6) |
| `spread_tipis_max` | 3.0 | Proposal §3 |
| `hijau_max_demerits` / `menengah_max_demerits` | 1 / 3 | Proposal §3 |
| `rem_alami.drtg_top10_cutoff` | 112.9 | **FIT** (§6) |
| `rem_alami.pace_bottom12_cutoff` | 98.91 | **FIT** (§6) |
| `rem_alami.usg_scorer_out` | 0.25 | Proposal §3 |
| `rem_alami.blowout_spread` | 8.5 | Proposal §3 |
| `rem_alami.market_align_max_gap` / `market_align_max_total` | 5.0 / 228.0 | Proposal §3 |
| `veto.logic` | `"AND"` | Keputusan user #4 (13:59 WIB) |
| `veto.total_tinggi_points` | 232.0 | **INITIAL** (proposal Gemini) |
| `veto.pace_tinggi` | 100.5 | **INITIAL** (proposal Gemini) |
| `veto.rim_protector.position_filter` | `["C","PF","F-C","C-F"]` | Proposal §3 |
| `veto.rim_protector.min_mp_per_game` / `min_blk_per_game` / `min_games` / `max_per_team` | 18.0 / 1.0 / 3 / 2 | Proposal §3 (diperketat dari 15.0/0.8 v17) |
| `tiga_pa_rate_top10_cutoff` | 0.457207 | **FIT** (§6) — ⚠️ **nama kunci MENYIMPANG dari brief** (lihat §9.1) |
| `tunggu_lineup.usg_bintang` / `bpm_bintang` | 0.24 / 2.0 | Proposal §3 |
| `tunggu_lineup.mp_min_rotasi` / `bpm_min_jalur_usg` | 10.0 / 0.0 | **BARU (keputusan D7)** — kualifikasi jalur USG |

### 1.3 OT, setan pemain, kalibrasi

- `ot_seleksi` (rombak): `skip_ot_prob` 0.028 **DIHAPUS** (cacat — di atas kap teoretis sim 2,74%). Baru: `mode: "empiris"`, `base_rate_ot: 0.0575` (PRIOR terdokumentasi, bukan fit — lihat §4), `hard_skip_ot_prob: 0.085` **INITIAL**.
- `setan_pemain`: `boost_pp` 12.0, `cap_pct` 0.50, `add_3par_volume_flag` true (BARU); `ambang_menit_rotasi` 10.0 (tetap); `pct_terbaik_min_total_3pa` **DIHAPUS**.
- `calibration`: `lean_to_market_gap` 5.0 **DIPINDAHKAN** dari `market_line_check.total_gap_points` (kunci lama dihapus — satu sumber kebenaran, sesuai brief). ⚠️ Pemindahan ini menyebabkan 5 modul yang masih membaca kunci lama ConfigError — **bukan file worker A** (daftar lengkap §10.2). `apply_shrinkage_pre_verdict: true` (BARU); `shrinkage: {mode: "setengah_jarak", fraction: 0.5}` — **cocok dengan pilihan worker B yang sudah mendarat di `engine/vegas.py`** (bukan tebakan; komentar config sudah diperbarui).
- `equilibrium`: `mode_insurance: safety_first`, `mode_main: max_er` (tetap).

---

## 2. Vonis baru — `engine/vonis.py` (ditulis ulang)

**Signature publik TIDAK berubah:** `nilai_vonis(analysis, hasil_stress=None, cfg=None)`, `evaluasi_veto(analysis, cfg=None, pemetaan=None)`. Fungsi baru: `cek_tunggu_lineup(analysis, cfg=None, usg_pemain=None)` (lihat §5 + daftar signature §11).

### 2.1 Enam demerit (urutan tetap a–f)

| Token | Aturan v18 |
|---|---|
| `tail_fragility` | **1 poin gabungan**: P banjir 3P < 0,72 **ATAU** P banjir FT < 0,67 di garis Asuransi (dihitung terpisah dari CDF/stress; bukan lagi "terburuk" tunggal) |
| `total_tinggi` | Garis bandar ≥ 235,0 |
| `gap_besar` | gap model-vs-pasar (p_model − p_market) > 0,08 **HANYA bila tanpa cedera berdampak terverifikasi** (lihat D4); bila ada → flag investigasi, bukan demerit |
| `ekor_gemuk` | Jarak garis Asuransi ke total pasar ≥ 16,0 poin **DAN** harga venue ≤ 80¢ (diperketat dari 10/85) |
| `foul_tinggi` | FTr **gabungan** ≥ p80 (0,308111). **Definisi "gabungan" (D1): rata-rata aritmetik FTr musim kedua tim** |
| `spread_tipis` | \|spread\| ≤ 3,0 poin |

**Dihapus:** demerit `gap_kecil`, `volume_tipis` (volume kini hanya info + gate komposer, bukan vonis), semua demerit edge/setan; pemicu keras `edge_tidak_positif` (edge terbaik tetap dicatat sebagai info); pemicu OT sim 2,8% (diganti OT empiris, §4).

### 2.2 Aturan vonis

- **HIJAU** = 0 veto + ≤1 demerit + ≥1 rem alami. **MENENGAH_HIJAU** = ≤3 demerit (termasuk 0–1 demerit tanpa rem). **KUNING** = ≥4 demerit ATAU pemicu keras (veto / OT empiris / data_tidak_cukup). **TUNGGU_LINEUP** = timing gate (precedence: veto > tunggu_lineup > demerit).
- Nilai vonis `menengah_hijau` DIPERTAHANKAN dari v17 (bukan `menengah`) — token stabil untuk komposer/laporan.
- **Spread (|median margin sim|) kini data WAJIB** — tanpanya vonis KUNING `data_tidak_cukup`. OT sim (`ot_probability`) BUKAN lagi data wajib (hanya info).

### 2.3 Lima rem alami (dicatat mana yang terpenuhi + rinciannya)

1. `pertahanan_top10` — salah satu tim DRtg musim ≤ 112,9 (FIT).
2. `pace_lambat` — salah satu tim pace ≤ 98,91 (FIT). **Arah didefinisikan benar + didokumentasikan: pace lambat = angka KECIL; Bottom-12 = 12 tim paling lambat, jadi `pace ≤ cutoff`.**
3. `pencetak_utama_out` — KEDUA tim kehilangan ≥1 pencetak utama OUT terkonfirmasi (USG ≥ 25%). USG dari `ingest/pemain_usg.py`; bila USG tidak tersedia → `tidak_dievaluasi` (BPM TIDAK dipakai sebagai pengganti). Jalur USG dikualifikasi (D7).
4. `paint_utuh_blowout_atau_ftr_rendah` — (tidak ada rim protector OUT di kedua tim DAN |spread| ≥ 8,5) ATAU (kedua tim FTr < p50 0,274398). "OUT" di sini = status OUT apa pun (terkonfirmasi maupun belum — pilihan D6).
5. `selaras_pasar` — |median − pasar| ≤ 5,0 DAN total pasar ≤ 228,0.
- Data rem tidak tersedia → `tidak_dievaluasi` (bukan gagal), tercatat di `indikator.tidak_dinilai` sebagai `rem_<token>`.
- **Pemisahan (bukan penggabungan):** brief menulis rem (1) sebagai "pertahanan Top-10 ATAU pace Bottom-12" dalam satu item; implementasi memisahnya menjadi dua rem (pertahanan_top10, pace_lambat) supaya tiap rem bisa diaudit sendiri + `tidak_dievaluasi` per rem. Total tetap 5 rem (brief menghitung 4 item bernomor — (1) gabungan, (2), (3), (4); implementasi: (1a), (1b), (2), (3), (4)). Menunggu keberatan (D8).

### 2.4 Garis Asuransi + volume

- Prioritas garis Asuransi (a–f, dipertahankan dari v17): equilibrium Asuransi → garis tahan-banjir tidak-tipis → kaki Asuransi artefak → equilibrium Utama → kaki Utama artefak → garis acuan. **Garis tahan-banjir kini memakai gate v18: P banjir 3P ≥ 0,70 DAN P banjir FT ≥ 0,65.**
- Vonis tidak lagi membaca `polymarket_ladder.min_volume_usd`; flag `thin` dipakai apa adanya dari tangga hanya untuk pemilihan garis acuan.

---

## 3. Veto AND + filter posisi

### 3.1 Logika AND — `evaluasi_veto`

Veto menyala HANYA bila: rim protector **OUT terkonfirmasi (≥2 sumber)** + garis pasar ≥ 232,0 **DAN** pace tercepat ≥ 100,5. Ambang **INITIAL** (keputusan user #4, 13:59 WIB: "pake AND yang diusulkan gemini, aku setuju"). Kembali ke OR = **satu baris config** (`vonis.veto.logic: "OR"`) — diuji (D3).

Bila **hanya satu** kondisi lingkungan menyala: veto TIDAK menyala, tapi hasil mencatat `peringatan_parsial: true` + `kondisi_menyala` (worker B memakai ini untuk +3 bantalan).

**Kasus wajib (artefak verif 22 Nov, terverifikasi):**

| Laga | Hasil |
|---|---|
| DEN@CHI verif | **MENYALA** — Claxton OUT (2 sumber) + garis 236,5 + pace 103,22 |
| OKC@MIA verif | **TIDAK menyala** — garis 231,5 < 232,0; pace 102,19 menyala sendiri → `peringatan_parsial: true`, `kondisi_menyala: ["pace"]`; Holmgren OUT tercatat |

### 3.2 Regenerasi pemetaan — `scripts/fetch_rim_protector.py` + `config/rim_protector_2026-27.json`

Perubahan script:

- Ambang dibaca dari lokasi baru `vonis.veto.rim_protector` (pindah dari `vonis.rim_protector`).
- **Filter posisi (BARU):** pos BBRef harus ada di `[C, PF, F-C, C-F]`. **stats.nba.com TIDAK menyediakan kolom POSITION** (diverifikasi live 2026-11-23) — posisi SELALU dari kolom `pos` tabel per-game Basketball-Reference (tarikan tambahan gratis; bila sumber blok sudah BBRef, posisi dari parse yang sama). Pencocokan nama antar-sumber: normalisasi (aksen dilucuti, huruf kecil) + tim.
- Bila tarikan posisi BBRef gagal → script **GAGAL (exit 2)** dan JSON lama dipertahankan: pemetaan tanpa filter posisi adalah cacat v17 — lebih baik tidak regenerate daripada regenerate cacat.
- Pemain yang lolos ambang blok/menit tapi posisinya tidak diketahui → dikeluarkan + dicatat di daftar `tanpa_posisi` pada JSON (jejak audit). Entri kini membawa field `pos`; JSON membawa `position_source`.

**Hasil regenerate (live 2026-11-23T07:15:31Z, stats.nba.com 474 pemain + posisi BBRef):**

- **21 dari 30 tim** terpetakan (v17: 30/30 — penurunan adalah konsekuensi ambang BLK ≥ 1,0 + filter posisi). 9 tim tak terpetakan: ATL, DET, GSW, HOU, IND, LAC, NYK, ORL, PHX — veto tidak bisa menilai tim-tim itu (dicatat `tidak_dinilai`, bukan veto).
- **Verifikasi wajib:** Nic Claxton TETAP di CHI (C, 1,0 blok/laga) ✅; Chet Holmgren di OKC (PF menurut BBRef, 3,0 blok/laga) ✅.
- **Guard HILANG:** Cade Cunningham, Tyrese Haliburton, Jamal Murray, Kevin Huerter, OG Anunoby tidak ada lagi ✅. Semua 30 entri berposisi C/PF. `tanpa_posisi`: kosong (semua pemain yang lolos ambang cocok dengan posisi BBRef).

---

## 4. OT empiris — `engine/ot_empiris.py` (BARU)

### 4.1 Rumus

```
p_ot(spread) = base_rate_ot × exp(−spread² / (2 × σ_margin²))
```

- `spread` = |median margin sim| (fallback: |mean margin|).
- `base_rate_ot` = **0,0575** (PRIOR terdokumentasi — titik tengah laju OT NBA umum ~5,5–6,0%; BUKAN fit: `leaguegamefinder` (2.701 laga fit) tidak membawa flag OT — hanya PTS/WL/MATCHUP — diverifikasi dari `parse_league_games`. Rencana fit: kumpulkan flag OT dari boxscore BBRef/ESPN).
- `σ_margin` = 14,4307 — **dipakai ulang** dari `simulation.nba.sigma_margin_points` (HASIL FIT, n=2.701), bukan parameter baru.
- `pace_tercepat` diterima tapi **TIDAK dipakai** di v18 (tidak ada hubungan pace→OT yang terukur; parameter dipertahankan untuk kalibrasi mendatang).
- `mode` config harus `"empiris"` (nilai lain → ConfigError, fail-closed — divalidasi di muka bahkan bila spread tidak ada; perbaikan dari temuan tes).

### 4.2 Hard-skip + KEJUJURAN (dormant)

Hard-skip bila p_ot ≥ **0,085 INITIAL** (config). **Temuan jujur: ambang ini TIDAK TERCAPAI di bawah rumus v18** — p_ot maksimum (spread 0) = laju dasar 0,0575 < 0,085. Gerbang dormant sampai kalibrasi ledger memberi laju OT per kelompok spread atau ambang diturunkan atas persetujuan user. Asumsi Gemini (laga pick'em mencapai 8,5%+) tidak didukung analisis densitas: laju pick'em ≈ laju liga (~5,75%), rasio hanya ~1,07×. Fakta ini dikunci oleh tes (`TestHardSkipDormant`) supaya tidak ada yang mengira gerbang ini aktif; jalur hard-skip tetap teruji lewat cfg ambang-diturunkan (0,05).

### 4.3 Kasus wajib

**DET@ATL (spread 2,0) TIDAK hard-skip** ✅ — p_ot empiris(2,0) = 0,056950409501032494 (cocok hitung tangan). Di v17, ot sim DET 2,89% ≥ 2,8% memicu hard-skip (dan KUNING). Nilai beku lain: p(0)=0,0575; p(2,5)=0,05664357653841656; p(15)=0,033500359045927054.

---

## 5. Timing gate — `cek_tunggu_lineup` + `ingest/pemain_usg.py`

### 5.1 Aturan gate

Bintang = pemain **QUESTIONABLE** dengan USG ≥ 0,24 **ATAU** BPM ≥ +2,0 (ambang dari `vonis.tunggu_lineup`). Bila ada bintang → `nilai_vonis` mengembalikan `{"vonis": "tunggu_lineup", ...}` (nilai vonis BARU). Precedence: veto > tunggu_lineup > demerit.

- **BPM dulu (tanpa fetch):** pemain yang lolos lewat BPM tidak butuh USG. USG ditarik malas (lazy) hanya untuk pemain Questionable yang belum lolos.
- **Fetch gagal → fallback BPM saja + dicatat** di `usg_catatan` + alasan (bukan disembunyikan).
- **Schema:** `"tunggu_lineup"` ditambahkan ke enum `status` di `schemas/nba_analysis.schema.json` (sekarang `["OK","HOLD","DATA_INCOMPLETE","tunggu_lineup"]`).

**Kasus wajib (artefak live 22 Nov):** IND@NYK → tunggu=True (Karl-Anthony Towns BPM +5,4 + Pascal Siakam USG 27,8%) ✅. Slate: 4/10 baris tunggu (OKC live: Giannis + SGA; DEN live: Powell; IND: KAT + Siakam; OKC verif: Giannis).

### 5.2 `ingest/pemain_usg.py` (BARU)

Cermin `ingest/pemain_3p.py`: stats.nba.com `leaguedashplayerstats` MeasureType=Usage (`USG_PCT` pecahan) jenjang 1; BBRef tabel advanced (`usg_pct` persen → dibagi 100) jenjang 2 (parser sendiri — `bbref.py` bukan file milik worker A dan `parse_player_advanced`-nya tidak mengembalikan usg_pct). Cache satu-proses per musim (`fetch_pemain_usg_cached`); `peta_usg`, `bersihkan_cache_pemain_usg`.

**Verifikasi live 2026-11-23:** 474 pemain, stats.nba.com. Sampel USG: Towns 0,252; Siakam 0,278; OG Anunoby 0,203; SGA 0,357; Giannis 0,304; Cade Cunningham 0,293.

### 5.3 Kualifikasi jalur USG (D7 — temuan baru saat pengukuran)

Pengukuran slate awal menunjukkan gate memicu pada **pemain pinggiran**: RayJ Dennis (ATL, USG 26,7%, BPM −3,2, 11,5 mnt) dan Felix Okpara (WAS, USG 25,0%, BPM −6,7, 1,7 mnt) — USG tanpa konteks menit + kualitas menangkap pemain garbage-time. Tanpa kualifikasi: 6/10 baris tunggu_lineup; dengan kualifikasi: 4/10.

**Keputusan (menunggu keberatan):** jalur USG dikualifikasi — USG ≥ ambang **DAN** mp_per_game ≥ 10,0 (`mp_min_rotasi` — nilai = definisi rotasi mesin `setan_pemain.ambang_menit_rotasi`) **DAN** BPM ≥ 0,0 (`bpm_min_jalur_usg` — BPM 0 = rata-rata liga menurut konstruksi BPM) bila BPM diketahui. mp hilang → jalur USG tidak aktif (USG tanpa menit tidak bisa ditafsirkan); BPM hilang → lantai dilewati (tidak ada bukti negatif). Definisi ini **dibagi** timing gate + rem alami (3) + aturan gap besar ("satu definisi pemain berdampak" — helper `_lolos_jalur_usg`). Alasan penolakan dicatat per pemain (`usg_ditolak`: `bukan_rotasi` / `bpm_negatif` / `mp_tidak_ada`).

Bukti di data nyata: BOS verif rem-3 menolak Brandon Williams (USG 25,9%, BPM negatif) tapi tetap terpenuhi lewat Curry; DET + ORL tidak lagi tunggu karena pemain pinggiran.

---

## 6. FIT league cutoffs + FTr/3PAr

**Satu tarikan** stats.nba.com `leaguedashteamstats` (Advanced + Base), musim 2026-27, **n=30 tim, tanpa nilai hilang**. Snapshot: `out/fit_cutoff_liga_v18.json` (`fetched_at` 2026-11-23T07:03:56Z). Persentil: interpolasi linear (default numpy: pos = q×(n−1)).

| Cutoff | Nilai | Definisi |
|---|---|---|
| DRtg Top-10 | **112,9** | Nilai ke-10 terkecil |
| Pace Bottom-12 | **98,91** | Nilai ke-12 terkecil (pace lambat = kecil) |
| FTr p80 | **0,308111** (penuh 0,3081111037454425) | Persentil 80 |
| FTr p50 | **0,274398** (penuh 0,27439760624275017) | Persentil 50 (untuk rem-4 cabang FTr rendah) |
| 3PAr Top-10 | **0,457207** (penuh 0,45720720720720726) | Nilai ke-10 terbesar |

Config menyimpan 6 desimal; tes menghitung ulang dari snapshot dan membandingkan dalam toleransi 1e-6 (plus uji nilai snapshot penuh vs hitung ulang, places=12).

**Implementasi:**

- `ingest/stats_nba.py`: `parse_team_base` + `fetch_team_base_stats` (BARU). MeasureType=Advanced **tidak** mengembalikan FGA/FTA/FG3A — karena itu butuh tarikan Base terpisah. `ftr = FTA/FGA`, `tiga_pa_rate = FG3A/FGA`; FGA 0/hilang → rasio `None` (bukan 0).
- `ingest/nba_brain.py` (HANYA ekstensi statistik tim): `stats_season` kini membawa `ftr` + `tiga_pa_rate` (6 field, dari 4). Jalur tier-1: fetch Base setelah Advanced berhasil (gagal → field `None` + `fetch_errors["team_base_season"]`). Jalur fallback BBRef: dari field `fta_per_fga_pct` / `fg3a_per_fga_pct` yang sudah ada. `stats_last10` SENGAJA tidak diperluas (profil musim saja).
- ⚠️ **Dampak yang sudah diperkirakan:** `tests/test_ingest_nba_brain.py` (bukan file worker A) gagal di 5 tes karena assert kesetaraan dict eksak 4 kunci + `_PatchSemua` tidak mem-patch `fetch_team_base_stats` (tanpa patch → panggilan jaringan live di tes). Koordinator harus merutekan pembaruan tes itu (tambah patch + kunci yang diharapkan). Lihat §10.2.

**Catatan:** artefak 22 Nov yang tersimpan dibuat SEBELUM FTr ada — `ftr_gabungan` = `None` (tidak dinilai) di semua 10 baris artefak. Demerit `foul_tinggi` diuji sintetis; data FTr nyata baru mengalir dari analisis yang dibuat setelah perubahan nba_brain ini.

---

## 7. Skip dari awal — `engine/skip_awal.py` (HANYA pemicu OT + pola Denver)

- **Pemicu OT → empiris:** `potensi_ot_tinggi` kini memakai `ot_empiris.evaluasi_ot` (spread → p_ot; ambang `hard_skip_ot_prob` 0,085). Nilai kembalian kedua kini p_ot EMPIRIS (bukan sim). `hasil["ot"]` membawa `ot_probability` (sim, info — makna tidak berubah), `p_ot_empiris`, `spread_points`, `ambang`, `tinggi`. `baca_ot_probability` dipertahankan (pembaca sim).
- **Pola Denver DIPERTAHANKAN berbasis edge (< 3,5%), BUKAN diubah ke EV** — alasan didokumentasikan di docstring modul: (i) mengubahnya butuh ubah tes pola Denver + `test_config.py` (di luar ruang lingkup worker A v18); (ii) di dalam konjungsi 4-syarat, edge adalah sinyal lemah, bukan gerbang — cacat edge-datar paling menggigit di gerbang, dan gerbang Asuransi SUDAH diganti ke EV. Konversi ke EV dicatat sebagai tindak lanjut (EV = p_final × (100/harga) − 1 vs ambang DISKON +2%). **Kelemahan jujur:** pada harga tinggi edge menyusut mekanis, jadi syarat (4) hampir selalu benar untuk garis acuan mahal — konjungsi efektif jadi 3 syarat di sana.
- Distribusi skip v18 (10 baris, diukur): **8 di-skip** (DET live + OKC verif tidak); **tidak ada yang via `ot_tinggi`**; `tidak_ada_equilibrium` kini memicu di 6 baris (equilibrium v18 lebih ketat — perilaku worker B, bukan worker A).

---

## 8. Tes — 148/148 lolos (file milik worker A)

| File | Tes | Status |
|---|---|---|
| `tests/test_vonis.py` (ditulis ulang) | 64 | ✅ OK |
| `tests/test_veto_and.py` (BARU) | 19 | ✅ OK |
| `tests/test_ot_empiris.py` (BARU) | 20 | ✅ OK |
| `tests/test_tunggu_lineup.py` (BARU) | 31 | ✅ OK |
| `tests/test_skip_awal.py` (tes OT saja) | 14 | ✅ OK |
| **Total** | **148** | ✅ |

### Kasus uji wajib + hasil

| Kasus wajib | Hasil |
|---|---|
| DEN verif veto menyala (Claxton + 236,5 + 103,22) | ✅ menyala; vonis KUNING |
| OKC verif veto TIDAK menyala (231,5 < 232,0) | ✅ tidak menyala + `peringatan_parsial` (pace) |
| Reversibilitas OR (satu baris config) | ✅ OKC menyala dengan `logic: "OR"` |
| DET@ATL TIDAK hard-skip OT | ✅ p_ot 0,0570 < 0,085; vonis HIJAU; tidak di-skip |
| Rumus OT vs hitung tangan | ✅ 4 nilai beku cocok persis |
| Hard-skip dormant (0,085 tidak tercapai) | ✅ dikunci tes + jalur teruji via ambang-diturunkan |
| IND@NYK TUNGGU_LINEUP (KAT + Siakam) | ✅ tunggu=True, kedua bintang terdeteksi |
| Kualifikasi USG: Dennis/Okpara bukan bintang | ✅ ditolak (`bpm_negatif` / `bukan_rotasi`) |
| Cutoff FIT vs hitung tangan dari snapshot | ✅ 5 cutoff cocok (toleransi 1e-6) |
| Parser USG (stats.nba.com + BBRef persen→pecahan) | ✅ |
| Parser `parse_team_base` (FTr/3PAr, FGA 0 → None) | ✅ |
| Pemetaan regenerate (Claxton/Holmgren ada, guard hilang) | ✅ |
| Distribusi slate v18 (5/0/1/4) | ✅ dibekukan |
| DEN verif tetap KUNING; 5 HIJAU | ✅ |

### Tes v17 yang diperbarui (dengan alasan)

- **Vonis artefak (8 tes):** semua ekspektasi v17 diperbarui ke nilai v18 yang diukur (OKC verif kuning-veto → tunggu_lineup; DEN live kuning-7-demerit → tunggu_lineup; DET kuning-ot → hijau; ORL kuning-edge → hijau; DAL/BOS menengah → hijau; distribusi 0/2/8 → 5/0/1/4).
- **Dihapus:** `test_volume_tipis_demerit` → diganti `test_volume_bukan_demerit_v18` (volume bukan demerit); `test_gap_kecil_demerit` → diganti tes `gap_besar` + investigasi; `test_tanpa_ot_kuning` → diganti `test_tanpa_spread_kuning` + `test_tanpa_ot_sim_tetap_hijau` (OT sim bukan lagi data wajib).
- **Diperbarui:** `test_laga_sehat_hijau` (HIJAU dengan 1 demerit gap_besar — v18 mengizinkan ≤1); `test_total_tinggi_demerit` (2 demerit → menengah); `test_ekor_gemuk` (varian all-thin; fixture normal tidak memicu karena harga 82,5¢ > 80); `test_hasil_stress_konsisten` (`hasil_stress_dipakai` False — stress result mencakup kaki artefak, bukan garis equilibrium 238,5; ditambah tes `dipakai` dengan hasil stress rakitan); `test_veto_tidak_menyala_bila_pelindung_main` (MENENGAH, bukan KUNING); `test_mara_bukan_pemicu_okc` (veto tidak menyala + parsial); tes komposer (DET hijau jadi kandidat; OKC verif tunggu; BOS verif tidak lagi dikeluarkan vonis — dikeluarkan skip pola); tes laporan (DEN veto vs "rapuh banjir", bukan "edge kecil"; DAL HIJAU; ditambah OKC TUNGGU LINEUP); tes config/pemetaan (kunci v18, 21 tim, ambang 18,0/1,0, filter posisi).
- **Tidak diubah (masih berlaku):** `test_baca_ot_fallback_dan_kanonik_menang`, tes veto dasar (1-sumber, garis/pace rendah, tanpa pemetaan, nama aksen, tanpa data cedera), tes fail-closed CDF/tangga/jangkar/soccer/tanpa-garis-bandar, `test_entri_match_dibuka`, `test_bukan_dict_value_error`.

---

## 9. Keputusan desain yang menunggu keberatan

- **D1 — FTr "gabungan" = rata-rata aritmetik kedua tim.** Alternatif yang ditolak: maks (satu tim foul-heavy saja sudah cukup — terlalu sensitif; satu tim tidak menentukan lingkungan Q4 sendirian) dan jumlah (skala salah — jumlah dua rasio bukan rasio). Diuji: 0,40 + 0,20 → 0,30 < p80, tidak demerit.
- **D2 — Rumus OT empiris + prior 0,0575 + hard-skip dormant 0,085.** Prior dari literatur/angka umum NBA (bukan fit — tidak ada flag OT di data fit). Dormant-nya hard-skip adalah temuan, bukan bug yang disembunyikan. Rencana kalibrasi: kumpulkan flag OT dari boxscore BBRef/ESPN, fit laju per kelompok spread.
- **D3 — Ambang veto INITIAL (232,0 / 100,5) + logika AND.** Revert ke OR = satu baris config (diuji). Kalibrasi: ledger (laga veto vs hasil nyata).
- **D4 — "Cedera baru terverifikasi" (aturan gap besar) disederhanakan:** ada entri OUT terkonfirmasi yang melibatkan pemain berdampak (BPM ≥ +2,0 atau USG ≥ 24% terkualifikasi) → flag investigasi, bukan demerit. Artefak tidak mencatat apakah pasar sudah menyerap kabar itu ("baru" vs "lama") — penyederhanaan jujur yang didokumentasikan.
- **D5 — "Selaras pasar" TIDAK mengadopsi klausa Gemini "> 5,0 dengan alasan cedera baru".** Alasan: shrinkage pra-vonis worker B menangani gap besar yang beralasan; menduplikasi logika itu di vonis akan menggandakan sumber kebenaran.
- **D6 — Rem-4 "paint utuh":** OUT apa pun (terkonfirmasi maupun belum) mematahkan paint utuh. Alasan: rem adalah bukti positif keamanan — keraguan soal status pelindung sudah cukup untuk tidak mengklaim paint utuh. (Veto sendiri tetap mensyaratkan OUT terkonfirmasi.)
- **D7 — Kualifikasi jalur USG (mp ≥ 10,0 + BPM ≥ 0,0)** — lihat §5.3. Menyimpang dari definisi literal brief ("USG ≥ 24% atau BPM ≥ +2,0") berdasarkan bukti slate (2/6 pemicu adalah pemain pinggiran). Bila ditolak, hapus `_lolos_jalur_usg` + kembalikan definisi literal (tes Dennis/Okpara + BOS rem-3 harus diperbarui).
- **D8 — Rem (1) brief dipecah menjadi dua rem** (pertahanan_top10 + pace_lambat) — lihat §2.3.
- **D9 — Pemetaan rim protector: tim tanpa big yang lolos = tidak terpetakan** (veto `tidak_dinilai` untuk tim itu). Alternatif (turunkan ambang sampai semua tim terpetakan) ditolak — ambang adalah aturan, bukan target cakupan.

---

## 10. Full suite — laporan jujur + flag koordinasi

Run terakhir: **1982 tes, 144 bermasalah (36 gagal + 108 error), 0 di file milik worker A.** Rincian per modul (run yang sama):

| Modul tes | Bermasalah | Akar penyebab (didagnosis, BUKAN diperbaiki — bukan file worker A) |
|---|---|---|
| `test_recheck` | 37 | `ConfigError: market_line_check.total_gap_points` tidak ditemukan (kunci dipindah ke `calibration.lean_to_market_gap` sesuai brief) |
| `test_ticket_audit` | 36 | Sama (total_gap_points) |
| `test_qa` | 24 | Sama (total_gap_points; `qa.py` diam-diam default 5,0 di satu tempat) |
| `test_ticket_composer` | 21 | Tes v17 vs komposer v18 worker B (gate edge dihapus, gate banjir/EV baru, OT empiris); **angka turun antar run (28 → 21) — B sedang memperbaiki** |
| `test_skip_awal` | 9 | Tes pola Denver / equilibrium / rekap 6-dari-10 (BUKAN OT — tes OT lolos semua). Penyebab: target Asuransi 0,74 → 0,82 menggeser garis acuan (246,5 → 252,5) + equilibrium v18 lebih ketat (tidak_ada_equilibrium kini memicu di 6/10 baris). **Butuh re-freeze oleh pemilik tes skip_awal** (di luar lingkup worker A: "HANYA update pemicu OT"). Rekap baru yang terukur: 8/10 di-skip, 0 via OT |
| `test_ingest_nba_brain` | 5 | Perubahan worker A (§6): `stats_season` 6 kunci + `fetch_team_base_stats` belum di-patch di `_PatchSemua`. **Rutekan pembaruan tes ke pemiliknya** |
| `test_config` | 5 | Asertasi nilai v17 (versi 17, `min_edge_pct`, `skip_ot_prob`, `total_gap_points`). **Rutekan pembaruan ke pemiliknya** |
| `test_report_nba` | 3 | Perilaku v18 (skip dua pemicu, skenario panas, equilibrium) |
| `test_pantau_blend` | 2 | Audit GO/NO-GO (knock-on v18) |
| `test_stress` | 1 | Garis tahan-banjir DEN None di bawah gate v18 |
| `test_nba_analysis` | 1 | Anomali `total_line_vs_model` hilang (knock-on total_gap_points) |

### 10.1 Daftar re-pointing `total_gap_points` (untuk koordinator)

Modul yang masih membaca `market_line_check.total_gap_points` (dihapus) dan harus dipindah ke `calibration.lean_to_market_gap`: `engine/anomaly.py` (~402, get_value → ConfigError), `engine/recheck.py` (~1458), `engine/ticket_audit.py` (~1037), `engine/ticket_composer.py` (~920), `engine/qa.py` (~1300, diam-diam default 5,0 — paling berbahaya karena tidak error). Sejauh yang diketahui, tidak ada worker v18 yang memiliki anomaly/qa/recheck/ticket_audit.

### 10.2 Flag koordinasi lain

- **§9.1 — Key rename (PENTING):** brief menulis kunci `vonis.3par_top10_cutoff`, tapi kode worker C yang sudah mendarat (`engine/setan_pemain.py` + tesnya) membaca **`vonis.tiga_pa_rate_top10_cutoff`** (defensif — kunci hilang → flag "tidak_dievaluasi", mati diam-diam). Worker A memakai nama C (nilai 0,457207) supaya flag worker C hidup. Bila koordinator menghendaki nama brief, C harus mengubah kodenya.
- **Shrinkage:** `setengah_jarak` + 0,5 cocok dengan pilihan worker B yang sudah mendarat di `engine/vegas.py` (bukan tebakan worker A).
- **Shim min_edge_pct TIDAK jadi diperlukan:** worker B sudah mendaratkan equilibrium + komposer v18 di tree bersama sebelum tes worker A ditulis — semua tes worker A memakai CFG v18 murni (tidak ada nilai yang tergantung shim).
- **Laporan TUNGGU_LINEUP sudah ada:** worker B sudah menambahkan cabang `Vonis: TUNGGU LINEUP` di `report/nba_report.py` (kekhawatiran awal worker A bahwa nilai baru akan dirender sebagai KUNING sudah tidak berlaku).
- **Kontrak timing gate worker B:** `_blok_tunggu_lineup` di `engine/nba_analysis.py` membaca `{"tunggu", "bintang", "alasan"}` dan me-stringify entri bintang (`[str(b) for b in bintang]`) — tapi brief menetapkan bintang sebagai list dict. Implementasi worker A mengikuti brief (dict); blok B akan berisi str(dict) sampai B memperbarui stringifikasi. B memetakan gate aktif ke status artefak HOLD (bukan "tunggu_lineup") — konsisten dengan enum schema yang juga punya HOLD.
- **Duplikasi `_tiga_pa_rate_dari_artefak`** di `engine/nba_analysis.py` (~458 dan ~482, badan identik — tidak berbahaya, definisi kedua menang). Bukan file worker A; dicatat saja.
- **Worker B/C sudah mendarat saat worker A bekerja:** `engine/equilibrium.py`, `engine/ticket_composer.py`, `engine/vegas.py`, `report/nba_report.py`, `tests/test_ticket_composer.py`, `tests/test_equilibrium.py`, `tests/test_vegas.py`, `tests/test_report_v18.py`, `tests/test_short_circuit.py`, `scripts/ukur_v18.py`, `LAPORAN-DEMON-V18.md` berubah/muncul di tree bersama. Worker A tidak menyentuh file-file itu.

---

## 11. Daftar lengkap signature fungsi baru (untuk wiring worker C)

### `engine/ot_empiris.py` (BARU)

```python
probabilitas_ot_empiris(spread_points, cfg=None, pace_tercepat=None) -> float
# p_ot empiris 0–1. spread None/tidak-hingga -> ValueError. mode != "empiris"
# / base_rate / sigma tidak valid -> ConfigError. pace_tercepat diterima
# tapi tidak dipakai di v18.

baca_spread(analysis) -> float | None
# |median margin sim| (fallback |mean margin|); None bila tidak ada.

baca_ambang_hard_skip(cfg=None) -> float
# ot_seleksi.hard_skip_ot_prob (0,085); hilang/tidak-valid -> ConfigError.

evaluasi_ot(analysis, cfg=None, pace_tercepat=None) -> dict
# {"dievaluasi": bool, "spread_points": float|None,
#  "p_ot_empiris": float|None, "p_ot_sim": float|None (info),
#  "ambang_hard_skip": float, "hard_skip": bool,
#  "pace_tercepat": float|None, "alasan_tidak_dievaluasi": str|None}
# Config rusak -> ConfigError (divalidasi di muka).
```

### `engine/vonis.py` (fungsi publik baru + helper yang relevan)

```python
cek_tunggu_lineup(analysis, cfg=None, usg_pemain=None) -> dict
# {"tunggu": bool,
#  "bintang": [{"player", "team", "status", "usg", "bpm"}],
#  "alasan": [str], "dievaluasi": bool,
#  "diperiksa": [{"player", "team", "status", "usg", "bpm",
#                 "mp_per_game", "bintang", "lewat",
#                 "usg_ditolak": None|"bukan_rotasi"|"bpm_negatif"|"mp_tidak_ada"}],
#  "usg_sumber": str|None, "usg_catatan": str|None,
#  "ambang": {"usg_bintang": 0.24, "bpm_bintang": 2.0}}
# usg_pemain (opsional): dict {nama: usg} ATAU list {"player","usg_pct"}
# (suntikan tes/wiring — sumber "suntik"). Bila None: fetch malas
# sekali-per-proses; gagal -> fallback BPM saja.
```

Nilai `nilai_vonis` yang baru: `"vonis": "tunggu_lineup"` + `indikator.timing_gate` (dict di atas) + `indikator.rem_alami` (`{"terpenuhi", "tidak_dievaluasi", "gagal", "rincian"}`) + `indikator.investigasi` + `indikator.p_ot_empiris` + `indikator.ot` (dict `evaluasi_ot`) + `indikator.ftr_per_tim` / `indikator.ftr_gabungan` + `indikator.spread_points` + `indikator.p_banjir_3p` / `p_banjir_ft` (terpisah). `evaluasi_veto` kini mengembalikan juga `peringatan_parsial` + `kondisi_menyala` + `logic`.

### `ingest/pemain_usg.py` (BARU)

```python
parse_stats_nba_usg(data: dict) -> list[dict]
# [{"player", "team", "games_played", "usg_pct" (pecahan 0-1),
#   "source": "stats.nba.com"}]. ValueError bila format berubah.

parse_bbref_usg(html: str) -> list[dict]
# Skema sama (usg_pct BBRef persen -> pecahan), source
# "Basketball-Reference". ValueError bila format berubah.

fetch_pemain_usg(season: str = "2026-27") -> FetchResult
# stats.nba.com, fallback BBRef. data = list pemain (skema di atas).

fetch_pemain_usg_cached(season: str = "2026-27") -> FetchResult
# Seperti di atas + cache satu-proses (hanya hasil OK yang di-cache).

peta_usg(pemain: list[dict]) -> dict[str, float]
# {nama_pemain: usg_pct} (tanpa None; nama terakhir menang bila ganda).

bersihkan_cache_pemain_usg() -> None
```

### `ingest/stats_nba.py` (BARU)

```python
parse_team_base(data: dict) -> list[dict]
# [{"team", "tricode", "fga_per_game", "fta_per_game", "fg3a_per_game",
#   "ftr", "tiga_pa_rate"}] (rasio None bila FGA 0/hilang).
# ValueError("stats_nba_format_changed") bila resultSet hilang.

fetch_team_base_stats(season, client=None) -> FetchResult
# Tarikan leaguedashteamstats MeasureType=Base; data = parse_team_base.
```

### `scripts/fetch_rim_protector.py` (diubah)

```python
turunkan_pemetaan(pemain, min_games, min_mp, min_blk, max_per_team,
                  position_filter=None) -> (pemetaan, tanpa_posisi)
# pemetaan: {tricode: [{"player", "pos", "blk_per_game", "mp_per_game",
#   "games_played"}]} (maks max_per_team, urut BPG).
# tanpa_posisi: pemain lolos ambang tapi pos tidak diketahui.
# position_filter None/[] = tanpa filter (hanya tes — JANGAN di produksi).

normalisasi_nama(nama: str) -> str
fetch_posisi_bbref(season: str) -> dict[(nama_ternormalisasi, tim), pos]
gabung_posisi(pemain, posisi) -> list[dict]  # isi field "pos"
```

### `ingest/nba_brain.py` (kontrak data berubah)

`inputs.{away,home}.stats_season` kini membawa 6 field: `off_rtg`, `def_rtg`, `pace`, `net_rtg`, **`ftr`**, **`tiga_pa_rate`** (dua terakhir `None` bila fetch Base gagal / data tidak ada). Worker C: `tiga_pa_rate` + `vonis.tiga_pa_rate_top10_cutoff` (0,457207) sudah tersedia untuk flag 3PAr.

---

## 12. Batasan jujur

1. **Hard-skip OT dormant** (0,085 tidak tercapai) — gerbang OT praktis tidak aktif sampai kalibrasi ledger atau penurunan ambang atas persetujuan user (§4.2).
2. **Base rate OT adalah prior, bukan fit** — tidak ada flag OT di data fit yang tersedia (§4.1).
3. **9 tim tak terpetakan** di pemetaan rim protector — veto tidak bisa menilai tim-tim itu; veto bergantung pada ketepatan waktu kabar cedera (DEN live: Claxton belum tercatat OUT).
4. **FTr artefak lama kosong** — 10 baris artefak 22 Nov tidak membawa FTr (dibuat sebelum perubahan nba_brain); demerit foul + rem-4 cabang FTr belum teruji di data nyata.
5. **Timing gate bergantung pada data cedera + USG yang segar** — USG dari stats.nba.com (cache satu-proses); bila fetch gagal, gate hanya mengandalkan BPM (pemain USG-only seperti Siakam terlewat — dicatat, bukan disembunyikan).
6. **Kualifikasi jalur USG (D7) adalah keputusan worker A** — menyimpang dari definisi literal brief; menunggu keberatan user/reviewer.
7. **Pola Denver syarat (4) masih berbasis edge** (§7) — konversi ke EV adalah tindak lanjut yang dirutekan.
8. **Full suite belum hijau** (144 bermasalah di file lain — §10). Worker A tidak memperbaiki file worker lain sesuai instruksi.
9. **Vonis tidak menilai berita** (news) — di luar lingkup worker A v18 (modul news milik worker lain); timing gate hanya memakai status cedera + BPM/USG.

---

## 13. File yang disentuh worker A

**Diubah:** `config/playstyle.yaml`, `engine/vonis.py`, `engine/skip_awal.py`, `ingest/nba_brain.py`, `ingest/stats_nba.py`, `config/rim_protector_2026-27.json`, `scripts/fetch_rim_protector.py`, `schemas/nba_analysis.schema.json`, `tests/test_vonis.py`, `tests/test_skip_awal.py` (hanya pemicu OT + helper pendukungnya).

**Baru:** `engine/ot_empiris.py`, `ingest/pemain_usg.py`, `tests/test_veto_and.py`, `tests/test_ot_empiris.py`, `tests/test_tunggu_lineup.py`, `LAPORAN-VONIS-V18.md` (laporan ini).

**Data (runtime, gitignored):** `out/fit_cutoff_liga_v18.json` (snapshot FIT cutoff liga).

**Tidak disentuh (sesuai instruksi):** `DECISIONS.md`, `LAPORAN-V18.md`, semua file worker lain, tidak ada commit/push/stash.
