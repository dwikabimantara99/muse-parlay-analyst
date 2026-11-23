# LAPORAN ASURANSI BARU — Worker B

**Tanggal:** 23 Nov 2026 (sore WIB) · **Repo:** muse-parlay-analyst, branch main, HEAD `be7371f`
**Config:** v16 (tidak berubah) · **Suite:** 1790 tes OK (baseline 1698) · **Kredit Odds API:** 0
**Commit:** TIDAK ADA (koordinator yang commit, sesuai perintah)

Empat item: (1) tanpa kaki kembar, (2) equilibrium Asuransi safety-first,
(3) koreksi geser banjir ke data bersih, (4) transparansi volume + deviasi
vs garis bandar. Plus pengukuran ulang di slate uji (`scripts/ukur_asuransi_baru.py`).

---

## 1. Tanpa kaki kembar — `engine/ticket_composer.py`

### Yang dibangun

Satu `match_id` tidak boleh muncul di kedua tiket. Aturan lama "garis
berbeda" (laga boleh masuk kedua tiket asal garis Asuransinya lebih tinggi)
DIGANTI total oleh keputusan user 12:20 WIB (insiden DEN@CHI 23 Nov: kaki
Denver di kedua tiket, keduanya mati bersamaan).

- **Alokasi berdasarkan vonis** — helper baru `_alokasikan_laga`
  (dipanggil `compose_tickets` setelah `_kumpulkan_kandidat`, sebelum
  pemilihan subset):
  - HIJAU → Asuransi saja (kandidat Utamanya dibuang).
  - menengah-hijau → Utama saja (kandidat Asuransinya dibuang).
  - KUNING yang **dievaluasi** → skip dari kedua tiket. KUNING yang
    **tidak** dievaluasi (KUNING-karena-data, `indikator.dievaluasi`
    False) → diperlakukan seperti tanpa vonis (bukan skip — preseden
    skip_awal: tanpa data → tidak dievaluasi, BUKAN skip).
  - Tanpa vonis → **tidak ada preferensi alokasi** (lihat
    "Penyimpangan yang didokumentasikan" di §6).
  - Vonis bentrok di satu laga (tidak seharusnya terjadi) → tanpa
    preferensi + catatan di coret kedua tiket supaya terlihat.
  - Penghapusan dicatat di `coret` (alasan jujur di ringkasan).
    Mengembalikan dict kandidat baru (dict lama tidak diubah).
- **Disjoint di tingkat subset** — `compose_tickets`: Asuransi dipilih
  dulu; kandidat Utama yang `match_id`-nya sudah masuk subset Asuransi
  dibuang dengan catatan "Laga {mid} hanya masuk Asuransi (aturan tanpa
  kaki kembar — satu laga tidak boleh ada di kedua tiket)." Variabel
  `garis_ins_terpilih` (dict garis) → `laga_ins_terpilih` (set match_id).
- **Fail-closed** — bila satu tiket tidak mencapai target pengali karena
  pembagian ini → tiket tidak terbentuk (`_pilih_subset` mengembalikan
  None; tidak ada pemaksaan memakai ulang laga).
- **Pembacaan vonis** — helper `_vonis_kandidat` / `_vonis_dari_nilai` /
  `_normalisasi_vonis`: membaca field `vonis` kandidat (string worker
  sistem vonis) lalu `analysis["vonis"]` (cadangan); menerima string
  ("HIJAU" / "menengah_hijau" / "menengah-cukup-hijau" / "KUNING",
  ejaan apa pun) atau dict hasil `engine.vonis.nilai_vonis`.
- `_kumpulkan_kandidat` TIDAK disentuh (milik worker A) — kecuali
  penggabungan (merge) wiring vonis mereka, lihat §7.

### Bukti tes wajib

- **Artefak nyata** (`test_artefak_nyata_kedua_tiket_disjoint`): compose
  slate 10 baris (live + verif) — kedua tiket yang terbentuk tidak
  berbagi satu laga pun. Catatan jujur: di slate nyata saat ini KEDUA
  tiket tidak terbentuk (lihat §5), jadi cek disjoint di artefak ini
  vakum — disjoint DIBUKTIKAN di slate sintetis (di bawah).
- **Sintetik** (`test_satu_laga_bagus_kedua_tiket_hanya_masuk_satu`):
  satu laga bagus untuk kedua tiket (kedua kaki DISKON, p_final tinggi)
  hanya masuk Asuransi; `laga_ins & laga_main == ∅`.
- **Fail-closed** (`test_fail_closed_pembagian_bikin_tiket_tidak_terbentuk`):
  4 laga → Asuransi terbentuk (3 kaki), Utama None (sisa 1 laga,
  pengali maks 1,33 < 3,0) — mesin tidak memaksa memakai ulang laga.
- **Alokasi vonis end-to-end** (`test_alokasi_vonis_integrasi`, flag
  vonis dimatikan + vonis ditempel di artefak): 9 laga — HIJAU
  (BOS/DET/LAL) → Asuransi saja; menengah-hijau (AAA/MIA/PHX/SAC) →
  Utama saja; KUNING dievaluasi (TOR) → tidak masuk mana pun; tanpa
  vonis (WAS) → masuk Utama lewat subset. Kedua tiket disjoint.
- **Unit alokasi** (`test_alokasi_vonis_unit`): tiap cabang + bentuk
  vonis string/dict + KUNING-tidak-dievaluasi + vonis bentrok + dict
  lama tidak diubah.
- Kelas lama `TestGarisBerbeda` ditulis ulang menjadi
  `TestTanpaKakiKembar` (5 tes perilaku lama diperbarui ke aturan baru;
  `test_garis_berbeda_boleh_dua_tiket` → `test_garis_berbeda_tetap_tidak_benar_dua_tiket`).
- Slate standar diperluas 5 → 8 laga (3 Asuransi + 5 Utama) — dengan
  aturan tanpa-kembar, 5 laga tidak bisa mengisi kedua tiket.

---

## 2. Equilibrium Asuransi safety-first — `engine/equilibrium.py`

### Yang dibangun

Mode pemilihan equilibrium per tiket, dikendalikan config
(`equilibrium.mode_insurance: safety_first`,
`equilibrium.mode_main: max_er`; versi config TIDAK berubah):

- **Asuransi safety-first**: di antara garis yang lolos SEMUA gate,
  pilih p_final TERTINGGI (paling aman). Seri p_final (< 1e-9) → ER
  lebih besar → garis lebih kecil.
- **Utama tetap max-ER**: p_final × 100/harga (tidak berubah).
- Mode hilang / bukan string / tidak dikenal → `ConfigError`
  (fail-closed: mode yang salah diam-diam lebih buruk daripada error
  keras). Hasil `cari_equilibrium` membawa field `"mode"`.
- Kendala pengali Asuransi (x2) TIDAK ditegakkan di equilibrium —
  tetap di komposer (`_pilih_subset`, fail-closed). Konsekuensinya
  jujur: garis paling aman adalah yang paling mahal, jadi Asuransi
  butuh LEBIH BANYAK kaki untuk mencapai x2 (lihat §5).
- Fungsi publik baru `nilai_semua_garis(analysis, tiket, cfg, ktx)` →
  daftar penilaian per garis (tanpa kunci "entri") — untuk pengukuran
  (hitung thin-only) tanpa menduplikasi logika gate.
- `cari_equilibrium` direfaktor memakai `nilai_semua_garis`; seleksi
  berdasarkan mode.

### Bukti tes wajib (OKC verif)

`test_okc_verif_asuransi_vs_utama_berbeda_tujuan` (artefak verif):

| Tiket | Mode | Hasil |
|---|---|---|
| Asuransi | safety_first | TIDAK ADA — garis terbaik yang lolos banjir + volume (U250,5 @89,5¢, p_final 0,908) gagal edge (+1,3% < 3,5%) |
| Utama | max_er | ADA — U240,5 @75,5¢, p_final 0,788828, ER 1,044805 |

Catatan jujur: perbedaan MODE (safety-first vs max-er) dibuktikan di
fixture sintetis (di bawah) — di OKC verif, Asuransi tidak punya garis
yang lolos di mode mana pun, jadi tes ini membuktikan perbedaan HASIL
(Utama ada, Asuransi tidak ada) + alasan gate-nya. Safety-first TIDAK
melonggarkan gate: garis paling aman pun harus lolos semua gate.

Perbedaan mode di fixture-224 (`TestSafetyFirst`, 7 tes baru):
safety-first memilih U250,5 @92,5¢ (p_final 0,999612, ER 1,0807, 6 garis
lolos); max-er (override config) memilih U242,5 @84,5¢ (p_final 0,967212,
ER 1,1446). Termasuk tes tie-break (seri p_final → ER lebih besar; seri
penuh → garis terkecil), mode tidak dikenal → ConfigError, mode hilang →
ConfigError, dan mode Utama safety-first (membuktikan mode murni fungsi
config per tiket).

---

## 3. Koreksi geser banjir ke data bersih — `config/playstyle.yaml`

### Yang dibangun

KOREKSI kontaminasi yang disetujui user 12:38 WIB (bukan pelonggaran):

- `stress.banjir_3p_points`: 13,54 → **8,50**
- `stress.banjir_ft_points`: 17,54 → **12,52**
- `setan_points`: 18,07 **TIDAK berubah**.
- Komentar config diperbarui (penjelasan singkat + rujukan
  LAPORAN-ATURAN-KERAS.md §6 + `out/derivasi_setan_2026-11-23.json`).
- Section `vonis:` / `setan_pemain:` (worker A) tidak disentuh.

### Dampak terukur (probe sebelum menulis kode, lalu dikonfirmasi tes)

- EQ Asuransi tetap **0/10**; gate pengikat berubah: volume 7 → 8,
  edge 2 (tetap), banjir 1 → 0 (satu baris pindah dari banjir ke volume).
- Garis tahan banjir turun ~5–6 poin: DEN live 266,5 → 260,5; DEN verif
  264,5 → 258,5.
- **Hasil skip TIDAK BERUBAH di semua 10 baris** (pola Denver tetap cocok
  di DEN/OKC-live/ORL/IND; DET tetap ot_tinggi).
- OKC verif EQ Asuransi tetap tidak ada (edge-bound, garis terbaik
  U250,5 @89,5¢ edge +1,3% — identik dengan sebelumnya).
- Fixture DEN sintetis di `test_equilibrium.py` kini PUNYA equilibrium
  Asuransi (U258,5 @85,5¢, p_final 0,900437, ER 1,053143, satu-satunya
  garis lolos) — tes ditulis ulang ke realita baru dengan alasan
  terdokumentasi. (Di `test_ticket_composer.py`, `_tangga_den` justru
  dikalibrasi ulang — ambang thin 264,5 → 258,5 — supaya kasus wajib
  "DEN ditolak gate banjir" tetap teruji. Dua file, dua keputusan
  independen, masing-masing didokumentasikan.)

### Tes yang diperbarui (dengan alasan terdokumentasi di tiap tes)

Nilai geser lama dipin di banyak tempat; semua diperbarui ke nilai
bersih + alasannya ditulis di komentar/docstring tes:

- `tests/test_equilibrium.py`: ekspektasi safety-first + geser bersih
  (fixture edge dikalibrasi ulang; tangga banjir dipendekkan 244,5 →
  238,5; DEN live/verif 266,5→260,5 / 264,5→258,5; p_banjir Utama 238,5
  kini 0,654 — ambang asersi 0,65 → 0,74 dengan alasan).
- `tests/test_skip_awal.py`: fixture pola Denver — garis 258,5–262,5
  ikut thin; `n_tahan_banjir` 4 → 7; komentar DEN live diperbaiki.
- `tests/test_report_nba.py`: "banjir tripoin +8,50 poin", "banjir
  lemparan bebas +12,52 poin"; Under 233,5: banjir 3P 61,3%, banjir FT
  53,7% (dihitung tangan dari CDF fixture, terverifikasi render).
- `tests/test_ticket_audit.py`: P banjir DEN U252,5 0,541 → 0,642
  (teks "banjir terburuk 64,2%"); kaki Utama U250,5 0,499 → 0,602.
- `tests/test_ticket_composer.py`: `_tangga_den` + tes gate banjir
  (P banjir DEN 54,1% → 64,2%; garis tahan pertama 258,5).
- `tests/test_config.py`: tes baru `test_stress_section_geser_bersih`
  (8,50 / 12,52 / setan 18,07) + asersi mode di `test_equilibrium_section`.

---

## 4. Transparansi volume + deviasi vs garis bandar — `report/nba_report.py`

Hanya dua method yang disentuh (`_bagian_skenario_panas`,
`_bagian_kaki`); tidak ada method bagian baru; method lain tidak
disentuh. Ambang $100 TETAP.

### (a) Deviasi vs garis bandar — `_bagian_skenario_panas`

- Kalimat pembuka kini menyebut garis bandar: "Kalau laga memanas,
  total poin naik dari garis bandar 225,5: banjir tripoin +8,50 poin;
  banjir lemparan bebas +12,52 poin; …" (bila garis bandar tidak ada,
  frasa lama dipakai).
- Setelah baris "Garis tahan banjir: …", baris baru: "Garis tahan
  banjir itu 16 poin di atas garis bandar 225,5." (garis tahan − garis
  bandar). Sama untuk garis tahan setan. Ditambahkan sebagai baris
  BARU (bukan satu baris) supaya asersi substring tes lama tetap lolos.
- **Setan per pemain**: dibaca dari entri kaki hasil stress
  (`total_setan_pemain`, `deviasi_setan_pemain_dari_garis_bandar` —
  field hidup PER KAKI di output worker A; top-level dicek sebagai
  cadangan): "Setan per pemain (kalau semua pemain panas bareng):
  total bisa sampai 261,5 poin, 36 poin di atas garis bandar 225,5."
  Bila tidak ada di mana pun, baris dilewati (tidak error, tidak
  mengarang) — dibuktikan tes `test_setan_per_pemain_dilewati_bila_tidak_ada`.

### (b) Volume per garis — `_bagian_kaki`

Volume USD per garis sudah tampil per kaki ("Volume garis ini: $X").
Ditambah satu kalimat penjelasan di akhir bagian: "Catatan volume:
volume satu laga tersebar di ratusan garis, sehingga garis yang jauh
dari garis bandar hanya ditawar segelintir orang dan harganya kurang
bisa dipercaya — garis seperti itu disebut volume tipis."

### Bukti tes

- `test_hitung_otomatis_dari_artefak` diperbarui (nilai bersih +
  asersi "dari garis bandar 225,5" + "Garis tahan banjir itu 16 poin
  di atas garis bandar 225,5.").
- `test_membaca_stress_tersimpan_bila_ada` + asersi deviasi jalur
  stress-tersimpan ("15 poin di atas garis bandar").
- Baru: `test_setan_per_pemain_dirender_bila_ada`,
  `test_setan_per_pemain_dilewati_bila_tidak_ada`,
  `test_penjelasan_volume_per_garis`.

---

## 5. Pengukuran — `scripts/ukur_asuransi_baru.py` → `out/ukur_asuransi_baru.json`

Slate uji yang sama: 10 baris (7 live + 3 verif 22 Nov). **Tidak ada
artefak analysis 23 Nov** (hanya `tickets_real_2026-11-23.json` + file
audit) — pengukuran hanya di 10 baris 22 Nov. 0 kredit Odds API.

### Hasil per baris

| Ukuran | Hasil |
|---|---|
| Gate banjir kaki artefak Asuransi (geser bersih) | **1 lolos / 7 gagal** (dari 8 dihitung). Yang lolos: OKC verif (82,1%). 2 baris tidak dihitung: DEN verif + BOS verif — analisis HOLD, kaki Asuransinya tidak ada (line None, meets False), jadi tidak ada yang diuji. |
| Equilibrium Asuransi (safety-first) | **0 ada / 10 tidak ada** |
| Equilibrium Utama (max-er) | **10 ada / 0 tidak ada** |
| Garis thin-only (gagal HANYA karena volume) | **1 garis di 1 baris**: BOS live U223,5 @76,5¢, p_final 0,8008, edge +3,58% — volume TIDAK TERCATAT (None), bukan $0. Edge-nya hanya 0,08 poin di atas ambang 3,5%. |
| Baris dengan volume sebagai penghalang | **1/10** (BOS live) |
| Vonis per baris | 8 KUNING (dievaluasi), 2 menengah-hijau (DAL live, BOS live), **0 HIJAU** |

### Hasil racik (slate gabungan, 7 laga unik setelah dedupe)

| Varian | Asuransi | Utama | Disjoint |
|---|---|---|---|
| Default (vonis aktif) | tidak terbentuk (0 kandidat) | tidak terbentuk (maks x1,22 — hanya DAL) | YA (vakum) |
| Tanpa vonis (flag mati) | tidak terbentuk (0 kandidat) | tidak terbentuk (maks x1,62 — DAL + OKC verif) | YA (vakum) |
| Vonis-alokasi-saja (flag mati + dict vonis ditempel) | tidak terbentuk | tidak terbentuk (maks x1,22 — sama dengan default) | YA (vakum) |

**Temuan, dilaporkan apa adanya (tidak ada yang dilonggarkan):**

1. **Asuransi tetap tidak terbentuk.** Koreksi banjir + safety-first
   TIDAK membuka Asuransi di slate ini. Penghalang kini: volume (garis
   tahan banjir thin) di 8 baris + edge di 2 baris. Temuan struktural
   LAPORAN-ATURAN-KERAS §5 bertahan: satu-satunya baris yang lolos
   banjir (OKC verif) gagal edge (+1,3% < 3,5%).
2. **Volume jarang menjadi SATU-SATUNYA penghalang: 1 dari 10 baris.**
   Di 7 baris lain yang gagal, volume gagal BERSAMA gate lain
   (banjir/edge) — jadi melonggarkan ambang $100 saja tidak akan
   membentuk Asuransi di slate ini. Satu-satunya garis thin-only
   (BOS U223,5) volumenya tidak tercatat dan edge-nya nyaris di ambang.
3. **Vonis mengubah Utama, bukan Asuransi.** Default vs tanpa-vonis:
   Utama maks x1,22 vs x1,62 — selisihnya satu kaki OKC live yang
   di-VETO vonis (HARD VETO rim protector worker A: Chet Holmgren OUT
   + pace tinggi). Asuransi 0 kandidat di semua varian — vonis bukan
   penghalang Asuransi di sini; gate-lah penghalangnya.
4. **Varian vonis-alokasi-saja == default** (x1,22) — jalur cadangan
   `analysis["vonis"]` konsisten dengan jalur live (KUNING dievaluasi
   di-skip oleh `_alokasikan_laga`, bukan `_kumpulkan_kandidat`).
5. **Disjoint di slate nyata bersifat vakum** (tidak ada tiket yang
   terbentuk) — disjoint DIBUKTIKAN di slate sintetis (§1), bukan di
   slate ini. Laporan ini tidak mengklaim lebih dari itu.
6. **0 HIJAU di slate uji** — alokasi HIJAU → Asuransi belum pernah
   teruji di data nyata, hanya di fixture sintetis.

---

## 6. Keputusan desain yang menunggu keberatan

1. **Tanpa vonis = tanpa preferensi (BUKAN menengah-hijau).**
   PENYIMPANGAN YANG DIDOKUMENTASIKAN dari perintah kerja ("bila belum
   ada [vonis], perlakukan semua kandidat sebagai menengah_hijau"):
   menandai semua laga tanpa vonis sebagai menengah-hijau akan membuang
   SEMUA kandidat Asuransi dan membuat Asuransi tidak pernah terbentuk
   — termasuk di slate uji yang belum punya vonis — dan merusak suite
   yang ada. Implementasi: tanpa vonis → kedua kandidat dipertahankan,
   disjoint ditegakkan di tingkat subset. Bila koordinator memutuskan
   lain, yang berubah hanya cabang ini (satu tempat di
   `_alokasikan_laga`, didokumentasikan di docstring-nya).
2. **Safety-first adalah max p_final per kaki; kendala x2 tetap di
   komposer.** Tidak ada optimasi gabungan keamanan-vs-pengali: garis
   paling aman bisa begitu mahal sehingga tiket tidak mencapai x2
   (fail-closed). Contoh fixture: kaki Asuransi @92,5¢ butuh 10 kaki
   untuk x2 (pengali 2,06). Optimasi gabungan adalah pekerjaan desain
   lanjutan, di luar lingkup.
3. **Fixture DEN diperlakukan berbeda di dua file tes** (keputusan
   independen, masing-masing didokumentasikan): di
   `test_equilibrium.py`, fixture DEN ditulis ulang ke realita baru
   (kini PUNYA equilibrium Asuransi — koreksi banjir membukanya);
   cakupan "volume mengikat" sintetis pindah ke artefak nyata DEN
   live/verif. Di `test_ticket_composer.py`, `_tangga_den` dikalibrasi
   ulang (ambang thin 264,5 → 258,5) supaya kasus wajib "DEN ditolak
   gate banjir" tetap teruji.
4. **`test_flag_dimatikan_perilaku_lama_persis`** kini juga mematikan
   flag vonis — vonis adalah gate baru (worker A); "perilaku lama"
   berarti SEMUA gate baru mati. Tanpa ini DET@ATL (KUNING dievaluasi)
   dikeluarkan dari kandidat dan tes gagal. Ini perbaikan tes atas
   perubahan perilaku worker A, bukan perubahan perilaku saya.
5. **Mode tidak dikenal / hilang → ConfigError** (fail-closed), bukan
   default diam-diam ke max-er. Alasan: mode yang salah diam-diam
   (Asuransi tiba-tiba max-er) lebih buruk daripada error keras.

---

## 7. Insiden stash + jawaban 3 pertanyaan koordinator

Di tengah sesi, `git stash` dijalankan (bukan oleh saya) dan
mengembalikan `engine/equilibrium.py` + `engine/ticket_composer.py`
ke HEAD — pekerjaan saya saat itu hanya tersisa di `stash@{0}` +
backup `/tmp/worker-b-backup/`. Saya memulihkan dengan 3-way merge
(`git merge-file`, di /tmp) antara versi tree saat itu (HEAD + wiring
vonis worker A), versi backup saya, dan HEAD — 0 konflik — lalu
menyalin hasil merge ke tree. Stash TIDAK di-pop / di-drop oleh saya
(masih ada, untuk direkonsiliasi koordinator).

Jawaban 3 pertanyaan koordinator (diverifikasi dari disk 23 Nov sore):

1. **Apakah perubahan ticket_composer.py di disk sudah lengkap dan
   final? YA.** Diff vs HEAD saat ini: **254 insertions, 37 deletions**
   (bukan 33 baris — angka 33 itu snapshot sebelum merge saya
   dipasang). Keempat helper ada di disk (`_alokasikan_laga`,
   `_vonis_kandidat`, `_vonis_dari_nilai`, `_normalisasi_vonis`),
   docstring + catatan "tanpa kaki kembar" ada, wiring vonis worker A
   juga ada di file yang sama, suite hijau. Lengkap dan final.
2. **Apakah saya pernah menulis ulang ticket_composer.py dari nol /
   mengembalikannya ke HEAD? TIDAK.** Saya tidak pernah menjalankan
   `git stash`, `git stash pop`, `git stash drop`, atau
   `git checkout --` apa pun. Diff kecil di disk yang dilihat Worker C
   disebabkan operasi stash oleh pihak lain, bukan oleh saya.
   Pemulihan saya hanya memakai `git merge-file` (di /tmp, tidak
   menyentuh index/working tree git) + `cp` file hasil merge ke tree.
3. **Apakah `_alokasikan_laga` tulisan saya? YA.** Saya yang menulis
   fungsi itu (desain alokasi vonis, "Design X") sebagai bagian dari
   item tanpa-kaki-kembar. Fungsi itu ada di versi stash (versi saya)
   dan di versi tree hasil merge.

---

## 8. Batasan jujur

- Asuransi **tetap 0/10** equilibrium di slate uji — keempat item ini
  tidak membuka Asuransi; yang berubah adalah kebenaran mekanismenya
  (geser bersih, safety-first, disjoint), bukan hasilnya di slate ini.
- Safety-first membuat kaki Asuransi mahal (92,5¢ di fixture) — di
  slate 10 laga, Asuransi x2 butuh ~10 kaki; kelayakan praktisnya
  belum terbukti di data nyata.
- Disjoint di slate nyata vakum (tidak ada tiket terbentuk); vonis
  HIJAU 0 di slate uji — dua perilaku kunci baru hanya terbukti di
  fixture sintetis.
- Pengukuran hanya 22 Nov (tidak ada artefak analysis 23 Nov); gate
  banjir hanya terukur di 8/10 baris (2 baris HOLD tanpa kaki Asuransi).
- `nilai_semua_garis` mengembalikan penilaian semua garis — dipakai
  pengukuran; komposer tetap memakai `cari_equilibrium` (tidak ada
  perubahan jalur panas).
- Deviasi garis tahan-setan vs garis bandar diimplementasikan tapi
  belum punya asersi tes artefak (fixture tidak punya garis tahan
  setan) — hanya jalur garis tahan banjir yang diasersi.

## 9. Item koordinasi (bukan milik saya — jangan saya perbaiki sendiri)

1. `stash@{0}` kini redundan (isinya = keadaan tree setelah merge) —
   dibiarkan untuk koordinator.
2. `engine/stress.py` (milik worker A): teks runtime `_DASAR_BANJIR_3P` /
   `_DASAR_BANJIR_FT` masih mengutip nilai tercemar lama (13,54/17,54,
   n=247) — tidak konsisten dengan config yang sudah dikoreksi.
   Perlu diperbarui worker A/koordinator.
3. `engine/vonis.py` (worker A): docstring mengutip "geser 17,54"
   (basi — kini 12,52); ambang INITIAL vonis mereka di-fit dari slate
   dengan geser lama — kalibrasi ulang adalah urusan mereka.
4. HARD VETO rim protector (worker A) mendarat di tengah pengukuran
   saya — OKC live kini di-VETO; memengaruhi angka racik default
   (Utama x1,22 vs x1,62 tanpa vonis). Dicatat, bukan dipersoalkan.
5. `ruff format --check` gagal di file repo — BUKAN standar repo:
   `pyproject.toml` hanya punya `[tool.black]` + `[tool.ruff.lint]`
   (tanpa `[tool.ruff.format]`), dan `ruff format` juga gagal di versi
   HEAD (gaya gabung string yang diterima black). Black + ruff lint
   bersih; saya tidak memformat ulang file ke gaya ruff-format
   (akan menciptakan diff besar yang tidak terkait).

---

## Ringkasan hasil

| Item | Status |
|---|---|
| 1. Tanpa kaki kembar + alokasi vonis | SELESAI — disjoint di subset + alokasi; 5 tes baru |
| 2. Equilibrium Asuransi safety-first | SELESAI — mode per tiket di config; 8 tes baru |
| 3. Koreksi geser banjir (8,50 / 12,52) | SELESAI — config + komentar; setan 18,07 tetap |
| 4. Transparansi volume + deviasi | SELESAI — 2 method report; 3 tes baru |
| Pengukuran | SELESAI — `scripts/ukur_asuransi_baru.py` → `out/ukur_asuransi_baru.json` |
| Suite | **1790 tes OK** (baseline 1698; +17 saya, +75 worker A) |
| Ruff (lint) + black | BERSIH pada semua file yang saya ubah |
| Odds API | 0 kredit |
| Commit | TIDAK ADA (koordinator) |

**Tes baru (17):** `tests/test_equilibrium.py` +8 (TestSafetyFirst 7 +
OKC verif 1), `tests/test_ticket_composer.py` +5 (TestTanpaKakiKembar:
sintetik 1, fail-closed 1, alokasi vonis 2, artefak 1),
`tests/test_report_nba.py` +3 (setan per pemain 2, volume 1),
`tests/test_config.py` +1 (geser bersih).

**File yang diubah/dibuat (saya):**

- `config/playstyle.yaml` — geser banjir bersih + kunci
  `equilibrium.mode_insurance` / `mode_main` (file ini juga memuat
  section worker A; diff gabungan 234 baris)
- `engine/equilibrium.py` — mode safety-first + `nilai_semua_garis`
  (+103/−29)
- `engine/ticket_composer.py` — alokasi vonis + disjoint subset
  (+254/−37 termasuk wiring vonis worker A hasil merge)
- `report/nba_report.py` — deviasi vs garis bandar + setan per pemain
  + catatan volume (file ini juga memuat `_bagian_vonis` worker A)
- `scripts/ukur_asuransi_baru.py` — BARU (pengukuran)
- `out/ukur_asuransi_baru.json` — BARU (hasil pengukuran)
- `tests/test_equilibrium.py`, `tests/test_ticket_composer.py`,
  `tests/test_report_nba.py`, `tests/test_config.py`,
  `tests/test_skip_awal.py`, `tests/test_ticket_audit.py` — tes
  diperbarui + 17 tes baru
- `LAPORAN-ASURANSI-BARU.md` — laporan ini (BARU)

**Tidak disentuh (milik worker lain):** `engine/stress.py`,
`engine/vonis.py`, `engine/setan_pemain.py`, `ingest/pemain_3p.py`,
section `vonis:`/`setan_pemain:` di config, `_kumpulkan_kandidat`
(kecuali merge wiring vonis), `DECISIONS.md`.
