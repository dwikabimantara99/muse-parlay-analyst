# LAPORAN — Sistem Vonis Per Laga (engine/vonis.py)

**Tanggal:** 2026-11-23 · **Repo:** muse-parlay-analyst, branch main, HEAD be7371f ·
**Config:** v16 (tidak diubah) · **Kredit Odds API:** 0

## Ringkasan eksekutif

Mesin kini menghitung **vonis per laga NBA dari data** — HIJAU (sehat,
kandidat Asuransi), MENENGAH_HIJAU (cukup sehat untuk Utama),
KUNING (lempar koin, skip dari kedua tiket) — dari 8 indikator
pelajaran Denver + **veto rim protector** (temuan Gemini yang sudah
diverifikasi main agent dari data mesin).

**Distribusi di slate uji 22 Nov 2026 (10 baris, 0 error):
HIJAU 0 / MENENGAH_HIJAU 2 / KUNING 8.** Veto menyala di 3 baris.
DEN@CHI verif → KUNING dengan pemicu keras veto (Nic Claxton OUT)
+ ketujuh demerit. Satu-satunya laga yang tadinya HIJAU (OKC@MIA
verif, 0 demerit) berubah KUNING karena veto — Chet Holmgren
(3,0 blok/laga) OUT + MIA pace 102,19. Itu hasil yang benar, bukan
efek samping: OKC tanpa frontcourt-nya bukan kandidat Asuransi yang
sehat — dan justru inilah nilai tambah veto: ia menangkap bahaya yang
tidak terlihat dari harga/banjir/volume.

**Kejujuran di depan:** dengan gerbang saat ini, vonis TIDAK
menyelesaikan kekhawatiran "v16 TERLALU KETAT" di slate ini — 0 HIJAU
berarti Asuransi tetap tidak terbentuk dari slate ini. Vonis memberi
gradasi (MENENGAH untuk Utama) + veto, bukan kelonggaran. Apakah
gerbangnya memang terlalu ketat atau slatenya memang buruk, hanya
bisa dijawab kalibrasi atas hasil settled (rencana di §8) — bukan
oleh 10 baris ini.

## 1. Aturan vonis persis

### 1.1 Garis Asuransi (garis rujukan)

Semua indikator per garis dibaca di **garis Asuransi** — garis yang
akan dimainkan mesin untuk Asuransi — prioritas:

| Prioritas | Garis |
|---|---|
| (a) | Garis equilibrium Asuransi (bila ada) |
| (b) | Garis tahan-banjir TIDAK-TIPIS terendah (bila ada) |
| (c) | Garis kaki Asuransi artefak (bila bergaris + berharga) |
| (d) | Garis equilibrium Utama (bila ada) |
| (e) | Garis kaki Utama artefak (bila bergaris + berharga) |
| (f) | Garis acuan (garis tangga termurah dengan P normal ≥ 0,74) |

Bila tidak satu pun ada → KUNING `data_tidak_cukup`.

### 1.2 Sistem demerit + pemicu keras

Tiap indikator lemah = 1 demerit. **HIJAU = 0 demerit;
MENENGAH_HIJAU = 1 s.d. 4 demerit; KUNING = > 4 demerit atau pemicu
keras.**

| Token | Syarat (1 demerit) | Ambang | Sumber ambang |
|---|---|---|---|
| `edge_kecil` | edge kaki terbaik < ambang | 2,5% | `vonis.edge_hijau_pct` (INITIAL, FIT) |
| `banjir_lemah` | P banjir < 74% di garis Asuransi DAN tidak ada garis tidak-tipis yang tahan banjir | 74% | dipakai ulang `tickets.insurance.min_leg_prob` |
| `setan_lemah` | P setan < ambang | 65% | `vonis.p_setan_hijau` (INITIAL, FIT) |
| `volume_tipis` | garis Asuransi thin (flag ATAU volume < $100) | $100 | dipakai ulang `polymarket_ladder.min_volume_usd` — TIDAK diubah |
| `volume_tidak_diketahui` | flag thin + angka volume sama-sama hilang | — | (tanpa ambang) |
| `gap_kecil` | gap model-vs-pasar < ambang | 4,0 poin | `vonis.gap_kecil_pct` (INITIAL, FIT) |
| `gap_besar` | gap model-vs-pasar > ambang | 8,0 poin | dipakai ulang `anomaly.model_vs_market_points` |
| `ekor_gemuk` | jarak garis Asuransi ke total pasar ≥ 10 poin DAN harga venue ≤ 85¢ | 10 poin / 85¢ | `vonis.ekor_jauh_points` / `vonis.ekor_harga_rendah_cents` (INITIAL, FIT) |
| `total_tinggi` | garis bandar ≥ ambang | 235,0 | `vonis.total_tinggi_points` (INITIAL, FIT — SEKUNDER, lihat §8) |

**Pemicu keras** (langsung KUNING, berapa pun demeritnya):

| Token | Syarat |
|---|---|
| `data_tidak_cukup` | data WAJIB hilang (§1.4) |
| `ot_tinggi` | ot_probability ≥ 0,028 (dipakai ulang `ot_seleksi.skip_ot_prob` — selaras skip_awal) |
| `edge_tidak_positif` | edge kaki terbaik ≤ 0 (tidak ada nilai di mana pun di laga ini) |
| `veto_rim_protector` | veto menyala (§2) — tidak bisa dikalahkan skor EV simulasi |

**Definisi indikator (yang perlu rumus eksplisit):**

- **Edge kaki terbaik** = maks edge (p_final − harga venue) atas kaki
  artefak + garis equilibrium kedua tiket + garis Asuransi. Ini sifat
  LAGA ("apakah laga ini menawarkan nilai di mana pun?"), bukan sifat
  satu kaki — gate edge per kaki tetap diurus komposer.
- **Sinyal ekor gemuk** (pasar bilang ekor gemuk): `jarak = garis
  Asuransi − main_total_line` (poin); sinyal TRUE bila `jarak ≥ 10,0`
  DAN `harga venue garis Asuransi ≤ 85¢`. Contoh: DEN verif 14 poin
  @78,5¢ → YA; OKC verif 19 poin @89,5¢ → TIDAK (harganya tinggi —
  pasar percaya garis itu).
- **P banjir / P setan**: dari `hasil_stress` bila diberikan dan
  memuat garis Asuransi (dicocokkan per GARIS saja — P Under per
  skenario hanya bergantung pada garis, bukan tiket), kalau tidak
  dihitung langsung dari CDF via `stress.p_under_digeser`
  (matematikanya sama — dibuktikan tes `test_hasil_stress_konsisten`).

### 1.3 Dasar FIT ambang (slate 10 baris, 22 Nov 2026)

Semua ambang baru INITIAL dengan rencana kalibrasi di komentar
config. Dasar FIT-nya (angka mentah, bukan tebakan):

- `edge_hijau_pct 2,5`: DEN verif +1,0%, DET +1,2%, OKC live +1,4%,
  BOS verif +1,9%, DEN live +2,1%, IND +2,2% di bawah; OKC verif
  +3,4%, BOS live +4,2%, DAL +4,2% di atas — ambang di celah 2,2–3,4.
- `p_setan_hijau 0,65`: OKC verif 73,8% satu-satunya di atas 60%;
  tertinggi berikutnya BOS live 56,5% — ambang di celah 56,5–73,8.
- `gap_kecil_pct 4,0`: DEN verif +3,3, DEN live +3,4, OKC live +2,7
  di bawah; OKC verif +4,4 di atas — ambang di celah 3,4–4,4.
- `ekor 10 poin / 85¢`: DEN verif 14 @78,5¢, DEN live 11 @72¢, ORL
  12 @77,5¢, OKC live 11 @74¢, BOS verif 13 @77,5¢ kena; OKC verif
  19 @89,5¢ tidak (harga tinggi); DET 8, DAL 9, IND 8, BOS live 8
  tidak (garis dekat).
- `total_tinggi_points 235,0`: DEN live 237,5 + DEN verif 236,5 di
  atas; tertinggi berikutnya OKC 231,5 — ambang di celah 231,5–236,5.
- `max_demerit_menengah 4`: OKC verif 0, DAL + BOS live 4, IND 5,
  OKC live 6, ORL 6, BOS verif 6, DEN live 7, DEN verif 7 — ambang di
  celah 4–5. **IND adalah kasus batas** (demerit ke-5-nya gap_besar
  +8,91, tipis di atas ambang 8,0 yang dipakai ulang).

### 1.4 Data wajib vs sekunder (fail-closed)

- **WAJIB** (hilang → KUNING `data_tidak_cukup`, `dievaluasi: False`):
  CDF total, tangga Under, jangkar pasar (kaki artefak bergaris +
  p_market — sama seperti equilibrium), ot_probability, dan satu
  garis Asuransi yang bisa dipilih + harganya.
- **SEKUNDER** (hilang → tidak dinilai, dicatat di `tidak_dinilai`,
  TANPA demerit): `main_total_line` (memberi makan ekor gemuk +
  level total).
- **Volume tidak diketahui** (flag + angka sama-sama hilang) →
  demerit `volume_tidak_diketahui` (tengah-tengah: tidak diabaikan,
  tidak juga pemicu keras).
- **Veto tidak dievaluasi** (pemetaan hilang, data ketersediaan tidak
  ada, tidak ada tim terpetakan, atau garis+pace sama-sama hilang) →
  dicatat di `tidak_dinilai`; permainan tetap dinilai sistem demerit
  (§2.4).
- Laga bola (`soccer_analysis`) → KUNING `bukan_nba`
  (`dievaluasi: False`) — vonis hanya untuk total Under NBA.

## 2. Veto rim protector (BARU — temuan Gemini terverifikasi)

### 2.1 Aturan

**Rim protector OUT terkonfirmasi + (garis pasar tinggi ATAU pace
tinggi) → veto menyala → vonis KUNING.** Veto memblokir kedua tiket
(karena vonisnya KUNING) dan tidak bisa dikalahkan skor EV simulasi:
sim menyesuaikan BPM pemain absen, tapi tidak memodelkan hilangnya
perlindungan ring secara eksplisit.

- **OUT terkonfirmasi**: status OUT di `injuries.entries` artefak
  dengan ≥ 2 sumber (`availability_n_sources`, fallback jumlah
  `sources`). OUT 1 sumber TIDAK memveto (selaras aturan cedera B2
  mesin: cedera perlu 2 sumber).
- **Garis pasar tinggi**: `main_total_line ≥ 235,0`
  (`vonis.veto_total_tinggi_points`, INITIAL — potongan yang sama
  dengan `total_tinggi_points`; kunci terpisah supaya veto bisa
  dikalibrasi sendiri).
- **Pace tinggi**: pace musim tertinggi kedua tim ≥ 102,0
  (`vonis.veto_pace_tinggi`, INITIAL — rata-rata liga 99,46;
  kelompok cepat {102,19 (MIA), 103,11 (ATL), 103,22 (CHI)} vs
  sisanya ≤ 101,22; ambang di celah 101,22–102,19). Pace tim
  tercepat dipakai, bukan pace laga rata-rata sim, karena tim
  tercepat yang menentukan tempo menyerang melawan pertahanan tanpa
  pelindung ring. Pace musim dipakai (bukan last10 — lebih stabil;
  CHI last10 101,15 tidak menangkap identitas cepat CHI yang
  sudah mapan semusim).
- **Pencocokan nama**: normalisasi (aksen dilipat — "Jokić" →
  "jokic", tanda baca .' - dibuang, huruf kecil) karena stats.nba.com
  dan laporan cedera tidak selalu menulis nama sama persis.
  Dibuktikan tes aksen (`test_veto_pemetaan_suntik_dan_nama_aksen`).

### 2.2 Definisi rim protector — dari data, dengan kejujuran penuh

**Definisi: per tim maksimal 2 pemain rotasi (GP ≥ 3, MP ≥ 15)
dengan blok bermakna (BLK ≥ 0,8), urut BPG tertinggi** (seri →
menit lebih besar → nama abjad, deterministik). Ambang derivasi di
`vonis.rim_protector` config. Diturunkan dari stats.nba.com
`leaguedashplayerstats` Base PerGame (fallback BBRef per-game) oleh
`scripts/fetch_rim_protector.py` → `config/rim_protector_2026-27.json`
(CHECK-IN, 30/30 tim terpetakan, musim 2026-27, sumber stats.nba.com,
474 pemain, diambil 2026-11-23).

**Kenapa bukan top-1 BPG (definisi yang pertama terpikir): data
membantahnya.** Pemimpin blok CHI adalah Jalen Smith (1,1 BPG),
BUKAN Nic Claxton (1,0) — selisih satu blok per 10 laga, di dalam
noise statistik. Aturan top-1 akan menyatakan CHI "aman" padahal
Claxton OUT dan cadangan ketiganya (Caleb Wilson 0,9) juga OUT.
Perlindungan ring adalah pekerjaan rotasi (center starter + big
cadangan) — karena itu top-2.

**Kenapa min_games = 3 (bukan 5):** pemain bintang yang cedera
(Chet Holmgren 3 laga @3,0 BPG, Jaren Jackson Jr. 4 laga @1,3 BPG)
tidak bisa diidentifikasi bila ambangnya 5 — dan merekalah yang
justru perlu ditangkap veto. 2 laga (Jalen Duren DET, 2 blok total)
terlalu sedikit — noise. Duren tidak tertangkap veto: keterbatasan
yang didokumentasikan, bukan disembunyikan (§8).

**Keterbatasan jujur definisi BPG murni:**

1. Bisa menamai **guard** di tim yang bloknya lemah (DET: Cade
   Cunningham 0,9 + Kevin Huerter 0,9; DEN: Jamal Murray 1,0).
   Veto hanya menyala bila pemain itu OUT + garis/pace tinggi, dan
   alasan veto selalu menyebut nama + angka bloknya supaya bisa
   diaudit. Di slate ini, Haliburton (IND, 0,8) tercatat OUT tapi
   garis/pace rendah → tidak memveto.
2. **Pemain 0–2 laga tidak bisa diidentifikasi** (Duren; juga
   Porzingis GSW yang tidak muncul di data musim berjalan).
   Perbaikan ke depan: identifikasi peran dari statistik musim lalu.
3. **Posisi tidak dipakai**: stats.nba.com tidak punya field posisi;
   label posisi BBRef (PF/C) tidak memisahkan big dengan bersih.
   Aturan BPG konsisten di kedua sumber.

**Kenapa file di `config/`, bukan `data/`:** `/data/` di-`.gitignore`
(isinya output lokal — `git ls-files data/` kosong). File pemetaan
adalah input statis versi mesin, seperti playstyle.yaml — karena itu
di `config/rim_protector_2026-27.json`. **Segarkan mingguan** (atau
setelah trade besar / perubahan rotasi) dengan menjalankan ulang
`scripts/fetch_rim_protector.py`.

### 2.3 Bukti veto menyala (dan tidak menyala)

| Laga | Pelindung OUT (terkonfirmasi) | Garis | Pace maks | Veto | Vonis |
|---|---|---|---|---|---|
| DEN@CHI verif | Nic Claxton CHI 1,0 | 236,5 ✓ | 103,22 ✓ | **YA** | KUNING (pemicu veto + 7 demerit) |
| OKC@MIA verif | Chet Holmgren OKC 3,0 | 231,5 ✗ | 102,19 ✓ | **YA** | KUNING (pemicu veto, **0 demerit**) |
| OKC@MIA live | Chet Holmgren OKC 3,0 | 231,5 ✗ | 102,19 ✓ | **YA** | KUNING (pemicu veto + 6 demerit) |
| DAL@UTA live | Jaren Jackson Jr. UTA 1,3 | 225,5 ✗ | 99,89 ✗ | tidak | MENENGAH_HIJAU (4 demerit) |
| BOS@GSW verif | Mitchell Robinson BOS 0,8 | 210,5 ✗ | 99,2 ✗ | tidak | KUNING (6 demerit) |
| IND@NYK live | Tyrese Haliburton IND 0,8 | 216,5 ✗ | 101,22 ✗ | tidak | KUNING (5 demerit) |
| DEN@CHI live | — (Claxton main di snapshot ini) | 237,5 ✓ | 103,22 ✓ | tidak | KUNING (7 demerit) |

**Catatan snapshot (penting):** veto TIDAK menyala di DEN@CHI live
karena snapshot analisis itu dibuat SEBELUM penyakit Claxton
diumumkan (Claxton tidak tercatat OUT di artefak live). Veto
bergantung pada ketepatan waktu kabar cedera — recheck sebelum
pasang adalah mitigasinya, bukan alasan untuk melonggarkan veto.

**Aday Mara — klaim yang TIDAK dipakai:** Mara ADALAH pemimpin blok
OKC (1,7 BPG, 16 laga) dan dia MAIN (tidak ada di data cedera
mesin). Veto OKC menyala karena Chet Holmgren, bukan Mara. Tes
`test_mara_bukan_pemicu_okc` mengunci ini sebagai regresi.

### 2.4 Veto tidak dievaluasi ≠ fail-closed (keputusan desain)

Bila veto tidak bisa dievaluasi (pemetaan hilang/rusak, data
ketersediaan tidak ada, tidak ada tim terpetakan, garis+pace
sama-sama hilang), veto TIDAK menyala dan alasannya dicatat di
`indikator.veto.alasan_tidak_dievaluasi` + `tidak_dinilai`. Veto
adalah klaim positif yang butuh data ("pelindung X OUT"), bukan
default — meng-KUNING-kan seluruh slate karena satu file pemetaan
hilang akan mematikan mesin karena kesalahan operasional, bukan
karena data laga. Permainan tetap dinilai sistem demerit. Ini
keputusan desain yang menunggu keberatan (§7).

## 3. Distribusi vonis di slate uji

**Sumber:** `scripts/ukur_vonis.py` → `out/ukur_vonis.json`
(10 baris, 0 error; tidak ada artefak analisis 23 Nov di
`out/analysis*.json` — yang diukur 7 live + 3 verif 22 Nov).

**HIJAU 0 / MENENGAH_HIJAU 2 / KUNING 8. Veto menyala di 3 baris.**

| Laga | Artefak | Vonis | Dem | Pemicu keras | Edge | P banjir | P setan | Gap | Ekor | OT | Garis Asuransi | Skip_awal* |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DET@ATL | live | KUNING | 2 | ot_tinggi | +1,2% | 82,0% | 73,7% | +3,6 | tidak | 2,89% | U249,5 @93¢ $141 | SKIP (OT) |
| OKC@MIA | live | KUNING | 6 | veto | +1,4% | 53,1% | 41,7% | +2,7 | YA | 2,64% | U242,5 @74¢ $7,63 | SKIP (pola) |
| ORL@WAS | live | KUNING | 6 | edge_tidak_positif | −0,6% | 51,3% | 39,7% | −2,1 | YA | 2,60% | U233,5 thin | SKIP (pola) |
| DEN@CHI | live | KUNING | 7 | — | +2,1% | 51,7% | 40,5% | +3,4 | YA | 2,36% | U248,5 thin | SKIP (pola) |
| DAL@UTA | live | MENENGAH | 4 | — | +4,2% | 61,1% | 49,7% | +12,3 | tidak | 2,70% | U234,5 thin | — |
| IND@NYK | live | KUNING | 5 | — | +2,2% | 57,3% | 45,8% | +8,9 | tidak | 1,70% | U224,5 $5 | SKIP (pola) |
| BOS@GSW | live | MENENGAH | 4 | — | +4,2% | 67,3% | 56,5% | +17,2 | tidak | 2,49% | U219,5 thin | — |
| OKC@MIA | verif | KUNING | 0 | veto | +3,4% | 82,1% | 73,8% | +4,4 | tidak | 1,90% | U250,5 @89,5¢ $226,88 | — |
| DEN@CHI | verif | KUNING | 7 | veto | +1,0% | 60,4% | 49,1% | +3,3 | YA | 2,13% | U250,5 @78,5¢ $6,45 | SKIP (pola) |
| BOS@GSW | verif | KUNING | 6 | — | +1,9% | 67,1% | 56,1% | +9,6 | YA | 2,21% | U223,5 thin | — |

\* `skip_awal` hanya KONTEKS (bukan bagian vonis). Vonis menambah
nilai di luar skip_awal pada BOS verif + OKC verif — keduanya TIDAK
kena skip_awal, tapi KUNING menurut vonis (dan keduanya memang
dikeluarkan komposer karena vonis — dibuktikan tes komposer §5).

**Catatan hasil settled (sumber: MEMORY.md, BUKAN pengukuran
saya — 10 baris bukan bukti):** DEN kalah (final 296); OKC MENANG
(final 236), ORL MENANG (final 212), DAL/BOS/IND aman. Artinya di
slate ini veto melewatkan 1 pemenang (OKC) sambil menangkap 1
pecundang (DEN), dan vonis melewatkan pemenang ORL/IND (KUNING).
Pola ini konsisten dengan kekhawatiran "v16 TERLALU KETAT" — tapi
10 baris tidak membuktikan apa-apa tentang kalibrasi gerbang; yang
membuktikan adalah ledger hasil settled (§8).

## 4. Bukti kasus uji wajib

| Kasus wajib | Bukti |
|---|---|
| DEN@CHI (artefak verif) → KUNING, alasan menyebut pemicu | `test_den_verif_kuning_veto_menyala`: vonis kuning, pemicu `veto_rim_protector`, ketujuh demerit (edge_kecil, banjir_lemah, setan_lemah, volume_tipis, gap_kecil, ekor_gemuk, total_tinggi); alasan[0] = "VETO rim protector: Nic Claxton (CHI, 1.0 blok/laga) OUT terkonfirmasi (Official NBA Injury Report, ESPN) + garis pasar 236.5 >= 235 dan pace tercepat 103.22 >= 102 …" |
| Satu laga sehat → HIJAU | **SINTETIS** (`test_laga_sehat_hijau`) — tidak ada laga slate yang HIJAU setelah veto (OKC verif, satu-satunya kandidat 0-demerit, kena veto). Fixture `_analisis_sehat` (median 220, sigma 5, garis 221,5, pace < 102, tanpa cedera): 0 demerit; edge +8,2%, P banjir 94,5%, P setan 68,4%, gap +7,0, volume $500 tidak-tipis, OT 1,90%, veto dievaluasi + tidak menyala. Nilai-nilai ini DIUKUR lalu dibekukan sebagai fixture, bukan ditebak. |
| Data hilang → KUNING fail-closed | `TestFailClosed` (7 tes): tanpa CDF, tanpa tangga, tanpa jangkar pasar, tanpa OT → KUNING `data_tidak_cukup` (`dievaluasi: False`); soccer → KUNING `bukan_nba`; config rusak → ConfigError. |

Tes veto (8 tes di `TestVeto`): menyala di DEN verif; TIDAK menyala
bila pelindung main (Claxton dihapus dari cedera), bila garis/pace
rendah (Claxton tetap OUT), bila OUT 1 sumber; tidak dievaluasi bila
pemetaan kosong / tanpa data cedera (dan `nilai_vonis` tetap jalan);
logika veto via pemetaan suntik + nama aksen (Jokić/Jokic cocok);
Mara bukan pemicu OKC.

## 5. Wiring

### 5.1 Komposer — `engine/ticket_composer.py::_kumpulkan_kandidat` SAJA

- `nilai_vonis` dipanggil per laga (NBA saja; dihormati flag
  `vonis.enabled` via `_flag_enabled` — `false` = perilaku lama
  persis).
- Laga KUNING yang **DIEVALUASI** dikeluarkan dari kandidat kedua
  tiket; alasannya tercatat di `coret` ("`{match_id}: vonis KUNING —
  {alasan}`").
- Tiap kandidat membawa `"vonis"` (`"hijau"` / `"menengah_hijau"` /
  `None` bila tidak dievaluasi) + `"vonis_alasan"` (daftar) — dibaca
  alokasi tiket untuk aturan tanpa kaki kembar.
- **Laga KUNING-karena-data (tidak dievaluasi) TIDAK dikeluarkan di
  sini** — gate per kaki tetap fail-closed sendiri — supaya satu
  ladder fetch yang gagal tidak mematikan seluruh slate termasuk
  Utama. Preseden yang sama dengan skip_awal ("tanpa data → tidak
  dievaluasi, BUKAN skip"). Keputusan ini menunggu keberatan (§7).
- Fungsi lain di komposer TIDAK disentuh.

Dibuktikan 5 tes `TestKomposerVonis`: BOS verif dikeluarkan kedua
tiket; OKC verif dikeluarkan karena veto (coret menyebut Chet
Holmgren); DEN verif dikeluarkan veto bila skip_awal dimatikan
(biasanya DEN sudah kena skip_awal duluan); kandidat DAL/BOS-live
membawa vonis `menengah_hijau`; vonis dimatikan → tidak ada coret
vonis + kandidat membawa `None`.

### 5.2 Laporan — `report/nba_report.py::_bagian_vonis` (BARU)

- Didaftarkan di `bangun()` sesudah `_bagian_berita`, sebelum
  `_bagian_market`. Method lain TIDAK diubah.
- Menampilkan vonis + alasan per laga dalam kata-kata sederhana +
  angka kunci (garis yang dinilai + harga + sumber, edge terbaik,
  P banjir/setan, volume, OT).
- **Veto ditampilkan MENONJOL**: baris "VETO — LAGA INI DIBLOKIR
  DARI TIKET (pelindung ring utama absen di laga skor-tinggi):"
  tepat setelah baris vonis, sebelum bullet demerit (alasan veto
  tidak diduplikasi di bullet). Dibuktikan
  `test_den_verif_veto_menonjol`.
- Laporan tidak pernah crash karena vonis gagal (try/except, pola
  yang sama dengan skenario panas); `data_tidak_cukup` juga dicatat
  via `_celah`. Laga bola → tidak ada bagian ini.
- **Cek urutan section (tugas follow-up #5):** `bangun()` = Judul,
  Ringkasan, Garis bandar, Data tim, Pemain kunci, Proyeksi,
  **Cedera (ke-7)**, Berita, **Vonis (ke-9)**, Market, **Kaki
  (ke-11)**, … — Cedera SUDAH sebelum bagian kaki/tiket. Urutan
  sudah benar; tidak ada perubahan urutan yang dilakukan.

## 6. Tiga prinsip (didokumentasikan — diverifikasi dari kode)

Ketiganya sudah cara kerja mesin; diverifikasi langsung dari kode
sebelum ditulis di sini (bukan klaim tanpa bukti):

1. **Pilih garis dari volatilitas laga dulu, baru cek harga**
   (bukan hitung mundur dari target pengali).
   `engine/analis.py::bantalan_adaptif`: "Dasar dari sebaran sim:
   varians besar → bantalan tebal" — `dasar = std × std_factor`
   (+ penyesuaian kekuatan serang + form skor). Garis lahir dari
   sebaran sim; harga dicek setelahnya (equilibrium menilai edge di
   garis tangga riil). Pengali adalah kendala level TIKET di
   `_pilih_subset`, bukan hitung-mundur per kaki.
2. **NO BET / turunkan target bila filter keras cuma menyisakan
   2–3 laga bersih (fail-closed).** `_pilih_subset` mengembalikan
   `None` bila tidak ada subset yang masuk target; `compose_tickets`
   menetapkan `hasil["insurance"] = None` + alasan jujur
   ("Kaki Asuransi yang lolos hanya mencapai pengali x… — target …
   tidak tercapai"). **KEJUJURAN: "turunkan target" TIDAK otomatis
   di kode** — tidak ada logika yang menurunkan `mult_min`; target
   turun hanya bila user mengubah config / memutuskan sendiri.
   Yang otomatis adalah NO BET-nya, bukan penurunan targetnya.
3. **Exchange-first (harga riil dulu, baru simulasi).** Harga adalah
   harga tangga Polymarket + markup jup (`jup_estimated_cents`,
   fallback `price_cents` — `engine/equilibrium.py`); sim memberi
   probabilitas (p_model/p_final) yang DIEVALUASI di garis tangga
   riil itu (`peluang_pada_garis`). Pengali tiket dihitung dari
   `100 / harga_jup` — harga bursa, bukan harga model.

## 7. Keputusan desain yang menunggu keberatan

1. **Komposer hanya mengeluarkan KUNING yang dievaluasi**
   (KUNING-karena-data tetap lewat ke gate per kaki). Alternatif:
   keluarkan semua KUNING (lebih ketat, tapi satu fetch gagal bisa
   mematikan slate).
2. **Edge terbaik sebagai indikator level-laga** (maks atas semua
   kaki + equilibrium). Alternatif: edge hanya di garis Asuransi
   (lebih ketat per kaki, tapi menghukum laga yang nilainya ada di
   garis lain).
3. **`total_tinggi` sebagai indikator sekunder yang belum terbukti**
   (hanya 1 demerit; sim memakai satu sigma_total global, jadi
   mesin belum mengukur apakah laga total-tinggi benar-benar lebih
   bervariasi). Bila kalibrasi menunjukkan tidak ada hubungan,
   indikator ini harus dihapus.
4. **Batas demerit 4|5** dengan IND sebagai kasus batas (demerit
   ke-5: gap_besar +8,91 vs ambang 8,0 yang dipakai ulang).
5. **Veto top-2 + GP ≥ 3 + BLK ≥ 0,8** (§2.2) — termasuk
   konsekuensi yang didokumentasikan: menamai guard di tim lemah,
   melewatkan pemain 0–2 laga (Duren), dan veto OKC (skipped
   winner di slate ini).
6. **Pace veto = pace musim tim tercepat** (bukan pace laga sim,
   bukan last10). Alternatif yang dipertimbangkan: `pace_game`
   (DEN 100,26 — nyaris rata-rata liga, ambangnya jadi arbitrer).
   Hasil veto OKC kokoh terhadap pilihan definisi ini (pace_game
   OKC 100,74 juga di atas ambang wajar mana pun di kisaran 100,5).
7. **Veto tidak dievaluasi → tidak menyala** (§2.4), bukan
   fail-closed-KUNING. Alternatif: KUNING-kan semua laga bila
   pemetaan hilang (lebih aman dari sisi veto, lebih rapuh dari
   sisi operasional).
8. **Pemetaan di `config/`** (§2.2) — karena `/data/` di-`.gitignore`.
9. **Veto memblokir KEDUA tiket** (vonis KUNING), bukan hanya
   Asuransi. Brief meminta "minimal tidak masuk Asuransi"; KUNING
   adalah pembacaan yang lebih ketat — bila reviewer mau veto hanya
   memblokir Asuransi (laga tetap boleh ke Utama sebagai
   MENENGAH_HIJAU), itu perubahan satu baris di `nilai_vonis` +
   komposer, tapi perlu keputusan eksplisit.

## 8. Batasan jujur + utang

- **Sampel FIT kecil (10 baris, 1 slate).** Semua ambang INITIAL;
  rencana kalibrasi ada di komentar config (ukur win rate kaki per
  pita edge / P setan / gap / jumlah demerit dari hasil settled;
  geser hanya atas persetujuan user). 10 baris tidak membuktikan
  apa-apa — distribusi 0/2/8 adalah gambaran, bukan bukti.
- **Banjir dan setan berkorelasi** (keduanya menggeser CDF yang
  sama) tapi geser + ambangnya berbeda (banjir p90 bersih 12,52;
  setan 18,07) sehingga bisa berbeda putusan (BOS live: P banjir
  67,3% tapi P setan 56,5%). Keduanya tetap dihitung terpisah karena
  user menamai keduanya sebagai indikator Denver yang berbeda.
- **Ketergantungan garis rujukan:** laga yang sama dinilai berbeda
  di dua analisis (DEN live vs verif: garis Asuransi U248,5 vs
  U250,5, veto mati vs menyala) karena sim/tangga/snapshot
  cederanya memang berbeda. Vonis menilai ANALISIS, bukan laga
  abstrak — dan vonis yang benar kemarin bisa salah hari ini bila
  datanya berubah.
- **HIJAU ≠ kaki Asuransi yang dijamin.** Vonis adalah seleksi
  level-laga; gate per kaki (banjir, edge, volume, min_leg_prob)
  tetap berlaku di komposer. Laga HIJAU bisa tetap tidak punya kaki
  Asuransi yang lolos.
- **Veto bergantung pada ketepatan waktu kabar cedera** (§2.3) dan
  pada **kesegaran pemetaan** (trade/rotasi mengubah pelindung;
  segarkan mingguan — tidak ada peringatan otomatis bila pemetaan
  basi; `pemetaan_diambil` tercatat di indikator untuk audit).
- **UTANG — fetch H2H:** vonis TIDAK bergantung pada H2H sama sekali
  (data H2H mesin KOSONG untuk DEN@CHI: `h2h_last5 []`). Keterbatasan
  fetch H2H (hanya dari gamelog musim berjalan) adalah utang mesin
  yang sudah dicatat sebelumnya — bukan bagian build ini, tapi
  dicatat di sini sesuai brief: klaim H2H DEN-CHI 248–257 (Gemini)
  TIDAK dipakai dan TIDAK bisa diverifikasi dari data mesin.
- **Klaim yang TIDAK dipakai sebagai fakta:** (a) Aday Mara OUT di
  OKC — tidak ada di data cedera mesin (2 sumber, 2 snapshot) dan
  tidak ada di boxscore; (b) H2H DEN-CHI 248–257 (di atas);
  (c) pace Bulls ~103,9 versi Gemini — dipakai data pace mesin
  sendiri (103,22 musim / 101,15 last10). Substansi "tim sangat
  cepat" benar; angka persis beda sumber.
- **Tidak diubah (sesuai brief):** ambang gate mesin 5,0 +
  lean-to-market (butuh uji historis DunkAPI); ambang volume $100;
  version config (tetap 16); section config lain; fungsi komposer
  selain `_kumpulkan_kandidat`; method laporan selain
  `_bagian_vonis` (baru).

## 9. Ringkasan hasil

- **Sistem vonis selesai + teruji:** `engine/vonis.py` (demerit +
  4 pemicu keras termasuk veto), section `vonis:` di config
  (7 ambang + 2 ambang veto + 4 ambang derivasi rim protector),
  wiring komposer + laporan, script ukur + script fetch pemetaan.
- **Distribusi slate uji (10 baris, 0 error):** HIJAU 0 /
  MENENGAH_HIJAU 2 (DAL, BOS live) / KUNING 8; veto menyala 3 baris
  (DEN verif via Claxton; OKC live + verif via Chet Holmgren).
- **Tes baru: 41** (`tests/test_vonis.py`) — 8 artefak nyata,
  9 sintetis, 7 fail-closed, 8 veto, 5 komposer, 2 laporan,
  2 config/pemetaan. Semua lolos.
- **Ruff + black:** bersih di semua file yang dibuat/diubah
  (vonis.py, fetch_rim_protector.py, ukur_vonis.py, test_vonis.py,
  ticket_composer.py, nba_report.py).
- **Kredit Odds API:** 0. Fetch blok: stats.nba.com (gratis, 1
  tarikan seluruh liga) + fallback BBRef (tidak terpakai).

### File yang dibuat / diubah

| File | Perubahan |
|---|---|
| `engine/vonis.py` | BARU — `nilai_vonis` + `evaluasi_veto` + loader pemetaan |
| `config/playstyle.yaml` | Section `vonis:` BARU (setelah `skip_awal:`); version tetap 16 |
| `config/rim_protector_2026-27.json` | BARU (CHECK-IN) — pemetaan 30 tim, stats.nba.com 2026-11-23 |
| `scripts/fetch_rim_protector.py` | BARU — tarik blok + turunkan pemetaan (stats.nba.com → BBRef) |
| `scripts/ukur_vonis.py` | BARU — ukur distribusi vonis slate uji (+ kolom veto) |
| `out/ukur_vonis.json` | BARU (dihasilkan) — 10 baris, distribusi 0/2/8, veto 3 |
| `engine/ticket_composer.py` | `_kumpulkan_kandidat` SAJA: panggil vonis, keluarkan KUNING dievaluasi, kandidat bawa vonis+alasan (+ import + docstring) |
| `report/nba_report.py` | `_bagian_vonis` BARU + registrasi (sesudah Berita, sebelum Market) + veto menonjol |
| `tests/test_vonis.py` | BARU — 41 tes |
| `LAPORAN-VONIS.md` | BARU — laporan ini |
