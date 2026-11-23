# LAPORAN — Aturan Keras Pasca-Denver: Gate Banjir, Skenario Setan, Sharp Move Bukan Diskon

**Status: SELESAI, terverifikasi koordinator dari disk, commit + push ke main.**
Commit: `c361a04` (feat) + `1315ad5` (docs hash). Remote HEAD terverifikasi
sama; tree bersih — config v15, **1.537 tes lulus**
(dari 1.483, +54), ruff + black bersih, **0 kredit Odds API**.

Keputusan user yang diterapkan: DECISIONS.md, "Aturan keras pasca-Denver +
kasus Thunder" (09:47 WIB) + koreksi 09:52 WIB (setan BUKAN gate keras —
gate keras Asuransi tetap banjir p90; setan adalah lapisan deteksi).
Spesifikasi user di DECISIONS.md tidak diubah; yang ditambahkan hanya
catatan implementasi.

## §1. Ringkasan — apa yang dibangun

| # | Item | Hasil |
|---|---|---|
| 1 | Gate banjir Asuransi (R1) | `ticket_composer.py`: kaki Asuransi wajib P ≥ 74% di banjir terburuk p90; gagal → naik ke garis tahan-banjir; tidak ada garis tahan (atau thin) → SKIP. Kunci config `tickets.insurance.stress_gate_scenario: banjir_terburuk` (fail-closed). |
| 2 | Skenario "setan" (deviasi maksimal) | `engine/stress.py`: skenario baru, geser **+18,07** (maksimum teramati, dari data game log). Flag deteksi `flag_setan` per kaki + garis tahan-setan. DETEKSI saja — tidak memblokir. Tampil di laporan + audit. |
| 3 | Sharp move BUKAN diskon | Label `DISKON_DITEKAN` di `price_labels.py`; diterapkan di recheck, audit, dan `anomaly.evaluate_leg`. Kasus Thunder (75¢ → 71¢) tidak lagi berlabel DISKON polos di mana pun. |

## §2. Item 1 — Gate banjir Asuransi

**Desain.** Di `_kumpulkan_kandidat`, sebelum gate harga/edge, tiap kaki
Asuransi dinilai di skenario banjir terburuk (worst of banjir_3p/banjir_ft
p90) lewat `skenario_panas` (dihitung sekali per laga, cache per
match_id — dibuktikan tes: 5 laga = 5 panggilan). Tiga putusan:
`lolos` (P ≥ 74%), `naik` (P < 74% tapi ada garis tahan-banjir →
climb tercatat alasan `banjir`), `tolak` (tidak ada garis tahan →
SKIP dengan alasan `tidak_ada_garis_tahan_banjir`). Bila stress tidak
bisa dihitung atau kaki tidak ada di hasil stress → ditolak
(fail-closed). Hanya kaki NBA total_under Asuransi; bola/total_over
tidak kena gate.

**Keputusan THIN (menunggu keberatan).** Garis tahan-banjir yang thin
TIDAK dipakai → SKIP, mengikuti aturan thin Asuransi yang sudah ada
(thin = hard gate). Gate TIDAK melompat ke garis tebal di atas garis
tahan yang thin (perilaku dipinkan di tes). Alasan tercatat eksplisit,
mis. *"garis tahan-banjir Under 264.5 volume tipis — tidak dipakai
(aturan thin Asuransi); P(Under) di skenario banjir terburuk
(banjir_ft) 54.3% < 74% di garis awal"*.

**Kaki naik garis memakai p_final/EV garis LAMA** (tidak dihitung ulang
di garis baru — didokumentasikan sebagai konservatif: peluang sebenarnya
di garis baru lebih tinggi). Konsekuensi nyata, lihat §5: kaki yang
naik garis hampir selalu gagal gate edge karena harga naik sementara
p_final tetap.

**Kasus uji wajib DEN@CHI (verifikasi koordinator dari disk, artefak
nyata `out/analysis_verif_tahap4_2026-11-22.json`):**
- `_gate_skenario` DEN U252,5 → `naik`, P banjir FT **54,28%**,
  garis tahan 264,5 @94¢ (thin).
- What-if composer (salinan DEN status OK + kaki Asuransi dipulihkan,
  dilabeli jelas sebagai salinan termodifikasi): kandidat Asuransi
  KOSONG, alasan coret persis alasan thin di atas. Kaki Utama U250,5
  tetap diterima (tidak kena gate).
- OKC@MIA nyata tanpa modifikasi (status OK): kaki Asuransi U250,5
  **LOLOS gate banjir** (P banjir FT 74,65% ≥ 74%, garis tahannya =
  garisnya sendiri, tidak thin) tapi ditolak **gate edge** (+1,3% <
  3,5%; p_final 90,8% − harga 89,5¢). Gate banjir bisa diloloskan;
  yang mengikat OKC adalah edge.

**Kaki Utama:** tidak kena gate; P banjir + P setan per kaki Utama
tampil di laporan (bagian "Skenario panas") dan audit (baris
"Kalau panas: …") — terverifikasi hidup pada DEN nyata.

## §2a. Klarifikasi harga: harga mengikuti statistik (koreksi user 10:14 WIB)

Angka 89–94¢ dari user adalah **HIPERBOLA, BUKAN target** (DECISIONS.md,
"Klarifikasi: harga mengikuti statistik", 10:14 WIB). Prinsip yang
benar: **HARGA MENGIKUTI STATISTIK, bukan sebaliknya.**

- **Garis tahan-banjir adalah garis TERMURAH yang lolos banjir**
  (bukan garis termahal). By construction: `garis_tahan_banjir`
  mengiterasi tangga dari garis terkecil ke atas dan mengambil garis
  PERTAMA yang P(Under) ≥ target di banjir. Naik garis hanya terjadi
  bila gate tidak lolos di garis bawah. Harga tinggi (89¢/94¢) hanya
  terjadi bila statistik laga itu memang menuntutnya (garis bawahnya
  gagal uji) — angka-angka 89¢/94¢ di laporan ini (mis. garis
  tahan-banjir DEN 264,5 @94¢, tabel §5) adalah HASIL pengukuran di
  slate nyata, bukan rentang target.
- **Tidak ada logika "prefer harga tinggi"** di komposer/gate banjir
  (diverifikasi koordinator atas diff build ini — tidak ada). Cara
  komposer menyeimbangkan harga vs target pengali TIDAK diubah: pilih
  subset kaki-kaki yang lolos gate hingga mencapai target (preferensi
  subset yang sudah ada memaksimalkan peluang menang lalu pengali —
  pengali lebih besar justru datang dari kaki yang lebih murah).
- **Kendala matematika** (dihitung tangan): 5 kaki @89¢ = (100/89)^5
  ≈ x1,79 mentah, **x1,69 setelah potongan kombo 5,5%** — tidak
  sampai x2. 5 kaki @85¢ ≈ x2,25 mentah, x2,13 setelah potongan.
  Dengan sedikit laga, semua kaki di harga tinggi tidak bisa mencapai
  target pengali — karena itu komposer TIDAK BOLEH mendorong semua
  kaki ke harga tinggi.
- **Interaksi dengan gate banjir (konsekuensi jujur):** gate banjir
  menaikkan garis (harga) kaki yang gagal. Bila semua kaki naik ke
  harga tinggi dan target pengali tidak tercapai dengan laga yang
  ada, Asuransi tidak terbentuk — itu perilaku fail-closed yang
  benar, bukan bug. Lihat §5 butir 2 untuk ukurannya di slate nyata.

## §3. Item 2 — Skenario "setan" (deviasi maksimal)

**Derivasi (dari data, metode sama seperti p90).**
`setan_points = 18,07 = (40,00 − 26,7901) × 1,3681`:
- Sumber: leaguegamefinder stats.nba.com, musim 2026-27, ditarik
  2026-11-23 09:52 WIB (0 kredit; mentah di `out/cache/`).
- Dataset: **243 laga SELESAI saja** (WL terisi), 20 Okt–22 Nov 2026.
- 3PM gabungan/laga: rerata 26,7901; p90 33,00; p99 37,00; **maks 40**
  (CHI@NYK 2026-10-28, total 260). Kemiringan OLS total/3PM 1,3681
  (diverifikasi dua cara independen, identik s.d. 6 desimal).
- Dipilih MAKSIMUM, bukan p99 (13,97), mengikuti kata user "MAKSIMAL".
  Detail + dataset: `out/derivasi_setan_2026-11-23.json` (git-ignored,
  runtime state seperti JSON fit/validasi lainnya).

**Peran: DETEKSI, bukan gate** (koreksi user 09:52 WIB). Per kaki:
`p_under["setan"]`, `tahan_setan`, `garis_tahan_setan`,
`alasan_tidak_tahan_setan`, dan **`flag_setan`** — True bila P(normal)
≥ target TAPI P(setan) < target ("kaki ini lolos normal tapi jebol
bila deviasi maksimal datang"). Tidak ada kode yang memblokir
berdasarkan setan. Tampil di laporan (baris FLAG SETAN + garis
tahan-setan) dan audit ("Kalau panas: … skenario setan …").

**Kasus uji wajib DEN@CHI (verifikasi koordinator dari disk):**
- Asuransi U252,5: normal **84,47%** ≥ 74%, setan **53,15%** < 74% →
  **flag_setan True**. Garis tahan-setan ada: 264,5 @94¢ (thin).
- Utama U250,5: normal 81,83% ≥ 65%, setan **49,15%** < 65% →
  **flag_setan True**. Garis tahan-setan 258,5 @88,5¢.
- Penolakan DEN dari Asuransi tetap lewat GATE BANJIR (§2), bukan setan.

**Batasan jujur.** Laju halftime DEN (42 tripoin/laga) masih di atas
maks musim (40) — setan mencakup banjir terburuk yang pernah
SELESAI, bukan banjir yang lebih parah dari semua yang pernah terjadi.

## §4. Item 3 — Sharp move BUKAN diskon

**Label.** `price_labels.label_for_ev(ev_pct, cfg, sharp_move=False)`:
bila `sharp_move=True` dan EV memenuhi ambang DISKON → kembalikan
`DISKON_DITEKAN`. Definisi EV dan ambang label TIDAK berubah; WAJAR/MAHAL
tidak berubah; pemanggil lama tanpa parameter tidak berubah perilaku.

**Diterapkan di 4 tempat:**
1. `engine/recheck.py` — anomali sharp_move kini membawa `price_label`
   + `kenapa_beda_required: True`; verdict tetap **JANGAN_PASANG**
   (aturan 6 yang sudah ada — lebih keras dari PERHATIAN, memenuhi
   "PERHATIAN (minimal)"); teks alasan: "harga baru bergerak tajam,
   selidiki dulu".
2. `engine/ticket_audit.py` — membandingkan harga tiket vs harga saat
   analisis untuk garis yang sama; selisih ≥ 3¢ → PERHATIAN (gate
   lunak) + `DISKON_DITEKAN` + flag `SHARP_MOVE` +
   `kenapa_beda_required`. Bila harga analisis tidak tersedia: dicatat
   "tidak bisa dinilai (bukan bukti tidak ada gerak)", label TIDAK
   ditekan (tidak ditebak).
3. `engine/anomaly.py::evaluate_leg` — temuan Worker C, diperbaiki
   koordinator dengan tes fail-first: sebelumnya mengembalikan label
   DISKON polos bersamaan dengan anomali sharp_move dalam satu hasil
   (kesalahan framing yang sama persis seperti Gemini). Kini label
   dihitung SETELAH cek sharp move.
4. `engine/price_labels.py` — definisi label (di atas).

**Kasus uji wajib Thunder (75¢ → 71¢, 1 jam sebelum tip-off):**
- price_labels: EV +5,63% → DISKON tanpa flag (jebakan Gemini),
  DISKON_DITEKAN dengan flag. Gerak 2¢ bukan sharp → DISKON tetap
  boleh; tepat 3¢ → sharp → ditekan.
- recheck: kaki JANGAN_PASANG, `price_move_cents` −4,0,
  `anomalies[0].price_label = DISKON_DITEKAN`,
  `kenapa_beda_required = True`.
- audit (literal 75→71): `price_label = DISKON_DITEKAN`,
  `sharp_move = True`, verdict JANGAN_PASANG — dari gate lantai harga
  yang sudah ada (71¢ < lantai 75¢), bukan dari sharp move; tes
  isolasi 80¢→76¢ membuktikan kontribusi sharp move sendiri lunak
  (PERHATIAN).
- anomaly.evaluate_leg: DISKON_DITEKAN + anomali sharp_move; kontrol
  tanpa snapshot tetap DISKON.
- Fail-first terverifikasi: 18 dari 20 tes baru Worker C GAGAL di
  kode lama; 2 tes baru koordinator untuk `evaluate_leg` juga gagal
  di kode lama (DISKON) sebelum perbaikan.

## §5. Pengukuran — seberapa ketat gate ini (slate nyata)

Script `scripts/ukur_gate_banjir.py` → `out/ukur_gate_banjir.json`
(10 baris: 7 laga live 22 Nov + 3 verif tahap 4; DEN muncul 2× karena
dua analisis berbeda). Target 74%.

**Gate banjir p90: 1 LOLOS / 9 TERBLOKIR.** Garis tahan-banjir ada di
9/10 baris. Flag setan (deteksi, BUKAN gate): **10/10**.

| Laga | Artefak | Kaki Asuransi | Normal | Banjir terburuk | Setan | Gate | Garis tahan-banjir |
|---|---|---|---|---|---|---|---|
| DET@ATL | live | U233,5 @69,5¢ | 77,0% | 43,2% | 42,1% | BLOKIR | U249,5 @92,5¢ |
| OKC@MIA | live | U242,5 @73,5¢ | 76,7% | 42,8% | 41,7% | BLOKIR | U258,5 @93¢ thin |
| ORL@WAS | live | U233,5 @77¢ | 75,4% | 40,8% | 39,7% | BLOKIR | tidak ada |
| DEN@CHI | live | U248,5 @71,5¢ | 75,9% | 41,6% | 40,5% | BLOKIR | U266,5 @93,5¢ thin |
| DAL@UTA | live | U234,5 @69¢ | 82,3% | 49,8% | 49,7% | BLOKIR | U248,5 @91¢ thin |
| IND@NYK | live | U224,5 @71¢ | 79,9% | 46,6% | 45,8% | BLOKIR | U238,5 @91,5¢ thin |
| BOS@GSW | live | U219,5 @69,5¢ | 86,2% | 57,6% | 56,5% | BLOKIR | U229,5 @85¢ thin |
| OKC@MIA | verif | U250,5 @89¢ | 93,9% | **74,6%** | 73,8% | **LOLOS** | U250,5 @89¢ (kaki sendiri) |
| DEN@CHI | verif | U252,5 @82¢ | 84,5% | 54,3% | 53,2% | BLOKIR | U264,5 @94¢ thin |
| BOS@GSW | verif | U225,5 @82¢ | 88,2% | 61,2% | 60,2% | BLOKIR | U233,5 @90,5¢ thin |

**Dua temuan yang harus dilihat user (tidak dilunakkan):**
1. **Satu-satunya yang lolos hanya menang tipis** (+0,65 poin di atas
   74%) DAN tetap kena flag setan (73,8%) — contoh tepat peran
   deteksi: lolos gate keras, tapi rapuh.
2. **Gabungan gate banjir + gate edge: 0/10 kaki Asuransi lolos.**
   OKC U250,5 @89¢ lolos banjir tapi gagal edge (+1,3% < 3,5%).
   Mekanismenya struktural: gate banjir mendorong kaki ke harga
   tinggi (89–94¢), dan di harga setinggi itu edge (p_final − harga)
   mengecil secara mekanis — p_final 90,8% di harga 89,5¢ hanya
   memberi edge +1,3%. Ditambah kaki yang naik garis memakai p_final
   garis LAMA (§2), climb hampir selalu gagal gate edge juga.
   Dengan parameter saat ini (banjir p90 + edge 3,5% + thin),
   Asuransi praktis tidak terbentuk dari slate-slat ini. Angka ini
   untuk keputusan user — koordinator TIDAK melonggarkan apa pun
   diam-diam. Pilihan yang tersedia (keputusan user): terima bahwa
   Asuransi jarang terbentuk; turunkan ambang edge; hitung ulang
   p_final di garis baru; longgarkan aturan thin untuk garis tahan;
   atau kalibrasi ulang banjir ke data bersih (§6).

## §6. Temuan kontaminasi derivasi p90 (dilaporkan, tidak diperbaiki diam-diam)

Nilai banjir p90 di config (13,54/17,54) diturunkan dari snapshot
n=247 yang **tercemar 4 laga yang sedang berjalan** (WL kosong):
IND@NYK baru 31 poin, DEN@CHI 171, ORL@WAS 124, DAL@UTA 134. Laga
berjalan bukan observasi laga penuh — ia menarik rerata ke bawah dan
kemiringan ke atas (2,12 vs bersih 1,37). Data bersih (n=243) memberi
p90 3P **8,50** / FT **12,52**. Bukti: tarikan yang sama mereproduksi
derivasi p90 persis (n=247: rerata 26,6194, kemiringan 2,1227, geser
13,54) — dataset dan metode cocok dengan build sebelumnya; dataset
bersih vs tercemar berdampingan di
`out/derivasi_setan_2026-11-23.json`.

**Nilai config TIDAK diubah** — kalibrasi ulang banjir menunggu
keputusan user. Konterfaktual (analisis saja, bukan config): dengan
geser p90 data bersih (8,50/12,52), block rate gate banjir **tetap
1/10 lolos** (BOS verif naik ke 70,67%, masih blokir). Jadi block rate
9/10 didorong garis kaki yang terlalu rendah, bukan semata-mata geser
yang tercemar — temuan ini kokoh.

## §7. Keputusan desain yang menunggu keberatan

1. **Garis tahan-banjir yang thin TIDAK dipakai** (§2) — mengikuti
   aturan thin Asuransi. Alternatif: boleh dipakai dengan peringatan,
   atau lompat ke garis tebal di atasnya.
2. **Setan = MAKS (18,07), bukan p99 (13,97)** — mengikuti kata user
   "MAKSIMAL".
3. **Dataset setan = laga selesai saja (n=243)**, sementara banjir p90
   di config memakai snapshot tercemar n=247 — inkonsistensi disengaja
   + didokumentasikan; kalibrasi ulang banjir menunggu keputusan user.
4. **`flag_setan` hanya untuk kaki yang lolos normal** — kaki yang
   sudah gagal di normal tidak di-flag (bukan kerapuhan tersembunyi).
5. **Kaki naik garis memakai p_final/EV garis lama** (§2) — interaksi
   gate banjir × gate edge (§5) perlu dilihat user/reviewer.
6. **Recheck tetap JANGAN_PASANG untuk sharp move** (aturan 6 yang
   sudah ada) — lebih keras dari PERHATIAN; tidak diturunkan karena
   itu akan melemahkan gate pengaman yang sudah ada.
7. **Tanpa jendela waktu tip-off** untuk penekanan DISKON — berlaku
   untuk sharp move apa pun yang terdeteksi aturan D9; "1 jam sebelum
   tip-off" adalah konteks kasus, bukan kondisi kode.
8. **`stress_gate_scenario` mendukung nilai `setan`** di kode (gate
   berparameter skenario) tapi BUKAN kriteria produksi — jangan diubah
   tanpa persetujuan user.
9. **Tanpa perubahan skema recheck**: `price_label` +
   `kenapa_beda_required` sharp move diletakkan di entri anomali
   (skema membolehkan field tambahan di sana), bukan di dict
   `kenapa_beda` per kaki (itu mekanisme condong-ke-market; memakainya
   akan salah mengaktifkan aturan itu).
10. **Fixture slate standar lolos gate banjir hanya via artefak clamp
    CDF 2 titik** — perilaku gate diuji dengan CDF realistis di
    `TestGateBanjirAsuransi`; tes lain tidak menguji gate banjir.

## §8. Batasan jujur

- Banjir/setan hanya menggeser rata-rata distribusi (varians tetap);
  banjir nyata mungkin juga melebarkan sebaran — tidak dimodelkan.
- Setan mencakup banjir terburuk yang pernah SELESAI (maks 40
  tripoin/laga); laju halftime DEN (42/laga) masih di atas itu.
- Gate banjir memakai nilai config p90 yang tercemar (§6) apa adanya
  sampai user memutuskan kalibrasi ulang.
- Audit mengasumsikan kaki independen (sudah didokumentasikan
  sebelumnya).
- Audit sharp move butuh harga saat analisis; bila tidak tersedia,
  gerak dicatat "tidak bisa dinilai" (bukan bukti tidak ada gerak).
- Pengukuran §5 memakai kaki Asuransi dari artefak analisis (fallback
  ke tiket nyata hanya untuk DEN/BOS verif yang kakinya tidak
  bergaris); DEN dihitung 2× (dua analisis).

## §9. Siap besok pagi (slate Selasa 24 Nov, 10 laga)

Alur: analyze → racik (gate banjir + edge + volume aktif) →
**`cli.py audit` sebelum pasang** (kini menampilkan "Kalau panas:
banjir terburuk …%; skenario setan …%" per kaki + framing sharp
move) → laporan memuat "Skenario panas" + FLAG SETAN →
`pantau --analysis …` (blend).

**Keputusan yang menunggu user sebelum/saat pemakaian besok:**
(a) kalibrasi ulang banjir p90 ke data bersih (8,50/12,52) atau tetap
(13,54/17,54); (b) ambang edge 3,5% (PROPOSAL D12 — gabungannya
dengan gate banjir membuat Asuransi praktis tidak terbentuk, §5);
(c) aturan thin untuk garis tahan-banjir; (d) hitung ulang p_final
di garis baru untuk kaki yang naik garis, atau tetap konservatif.
Tidak satu pun dari keempatnya diubah koordinator tanpa persetujuan.

## §10. File yang berubah

- `config/playstyle.yaml` — version 15; `stress.setan_points: 18.07`;
  `tickets.insurance.stress_gate_scenario: banjir_terburuk`.
- `engine/stress.py` — skenario setan + `flag_setan` + garis
  tahan-setan.
- `engine/ticket_composer.py` — gate banjir Asuransi + climb.
- `engine/ticket_audit.py` — tampilkan P banjir/setan per kaki +
  framing sharp move.
- `engine/price_labels.py` — label `DISKON_DITEKAN`.
- `engine/recheck.py` — framing sharp move + `kenapa_beda_required`.
- `engine/anomaly.py` — `evaluate_leg` menekan DISKON bila sharp
  move terdeteksi (perbaikan koordinator, tes fail-first).
- `report/nba_report.py` — bagian "Skenario panas" + setan.
- `scripts/ukur_gate_banjir.py` (baru) + `out/ukur_gate_banjir.json`
  + `out/derivasi_setan_2026-11-23.json` (git-ignored, runtime state).
- `DECISIONS.md` — bagian keputusan user 09:47 WIB (ditulis main
  agent) + catatan implementasi koordinator.
- Tes: `tests/test_stress.py`, `tests/test_ticket_composer.py`,
  `tests/test_ticket_audit.py`, `tests/test_recheck.py`,
  `tests/test_price_labels.py`, `tests/test_anomaly.py`,
  `tests/test_config.py`, `tests/test_report_nba.py`.

**Insiden saat build (dipulihkan, terverifikasi):** `git stash`
Worker C sempat menampung perubahan worker lain dan `stash pop`
gagal; C memulihkan semuanya via merge 3-arah. Koordinator
memverifikasi dari disk: `ticket_composer.py` (gate + import
`stress_mod`) dan `stress.py` utuh, tidak ada stash tersisa,
full suite 1.537 tes lulus.
