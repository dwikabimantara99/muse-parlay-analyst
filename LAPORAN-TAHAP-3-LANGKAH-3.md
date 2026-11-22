# LAPORAN TAHAP 3 LANGKAH 3 — Laporan Lengkap + Tanya-Jawab + Peracik Tiket

Tanggal: 2026-11-22. Repo `muse-parlay-analyst`, branch `main`.
Suite: **966 tes, semua lulus** (dari 849 di langkah 2). Config v9.
Kredit Odds API yang dipakai langkah ini: **0**.

## 1. Ringkasan

Langkah 3 membangun tiga hal yang membuat mesin bisa dipakai user
langsung: **laporan lengkap** per laga dalam Bahasa Indonesia
sehari-hari, **tanya-jawab** berbasis data (angka dari kode, bukan
karangan), dan **peracik tiket** yang meracik Tiket Asuransi + Tiket
Utama dari analisis + recheck — dengan kendala garis berbeda untuk
laga yang sama dan aturan condong-ke-market.

Hasil verifikasi live (slate 7 laga NBA 22 Nov, §8): analyze 7/7 OK,
recheck 3 GO + 4 NO-GO (semua kaki Asuransi di 4 laga itu ditolak
aturan condong-ke-market), laporan lengkap terbit, 5 jenis pertanyaan
dijawab dengan angka nyata, dan peracik meracik **Tiket Utama x3,18**
(4 kaki, EV +8,57%). **Tiket Asuransi TIDAK diracik** — hanya 2 kaki
yang lolos (pengali maks x1,65 < target x2,20) — dan mesin menolak
memaksakan tiket yang tidak memenuhi syarat. Itu perilaku yang benar,
bukan kegagalan (§8.5).

## 2. Apa yang dibangun

| Bagian | File | Isi |
|---|---|---|
| Laporan lengkap | `report/nba_report.py` (baru, 1.638 baris) + `tests/test_report_nba.py` (28 tes) | `render_nba_report(analysis, recheck=None)` → teks 17 bagian; `render_nba_report_json(...)` → bentuk JSON yang sama |
| Tanya-jawab | `engine/qa.py` (baru, 1.483 baris) + `tests/test_qa.py` (34 tes) | `answer(analysis, question, config=None, *, iterations=None)` — 6 intent deterministik + `unknown`; sim ulang "bagaimana-jika" 20.000 iterasi |
| Peracik tiket | `engine/ticket_composer.py` (baru, ~900 baris) + `tests/test_ticket_composer.py` (38 tes) | `compose_tickets(analyses, rechecks, config, stake_total=...)` — cari subset deterministik (DFS + pruning, batas 18 kaki) |
| Wiring CLI | `cli.py` (+312 baris) + `tests/test_cli_langkah3.py` (17 tes) | Subcommand baru `laporan`, `tanya`, `racik`; helper `_kumpulkan_nba_analysis`; perbaikan `--match` (§6) |
| Config | `config/playstyle.yaml` v9 | `tickets.main.multiplier_min` 3,5→3,0; `multiplier_max` 6,0→5,0; kunci baru `target_multiplier_max` 4,0 (semua dari profil user 2026-11-22) |
| Contoh | `examples/laporan_nba_ATL_DET_2026-11-22.txt` | Laporan lengkap DET@ATL dari verifikasi live (§8) |

Tes baru: 117 (28 laporan + 34 tanya-jawab + 38 peracik + 17 CLI
langkah 3). Semua offline kecuali verifikasi live §8.

## 3. Laporan lengkap

Perintah: `cli.py laporan --analysis <file> [--match <id>]
[--recheck <file>] [--out <file>] [--json]`. Exit 0 sukses,
2 bila file tidak bisa dibaca / artefak tidak valid.

17 bagian, Bahasa Indonesia sehari-hari, setiap datum memuat sumber +
jenjang + jam: judul+status, Ringkasan, Data tim, Pemain kunci
(top 5 per menit, BPM + status absen, shrinkage ditandai),
Proyeksi total, Kabar pemain (OUT/DOUBTFUL/QUESTIONABLE/PROBABLE +
alasan cedera/rest/personal/two-way + konflik antar sumber ditampilkan
dua-duanya), Bursa & harga pasar (garis utama, spread paling cair,
moneyline jup.ag, tangga Under + penanda pasar tipis), Kaki Asuransi
& Utama (p_model | p_pasar + sumber | p_final, EV, label
DISKON/WAJAR/MAHAL, bantalan, PEMBANDING_KALSHI), 5 laga terakhir,
5 pertemuan terakhir, Kandang vs tandang, Simulasi 100.000x (median,
p74, p5–p95, OT, moneyline), Skenario skuad, Anomali (diterjemahkan
ke kalimat), "Kenapa beda?", Cek ulang, Sumber data, Yang belum bisa
dipastikan.

"Kenapa beda?" memakai `engine/anomaly.check_model_vs_market`
(ambang 8 poin dari config, bukan hardcode), fallback ke anomali
artefak bila config gagal; terpicu juga bila artefak menandai
`kenapa_beda_required` atau recheck `triggered`. Kesimpulan default
jujur: "tidak ditemukan alasan konkret dari data yang ada" — kecuali
recheck memberi alasan konkret (dikutip apa adanya). Data yang tidak
ada ditulis "tidak terverifikasi", tidak pernah diisi tebakan.

### 3a. Contoh laporan live: DET@ATL 2026-11-22 (ringkasan)

Teks lengkap (16.819 karakter):
`examples/laporan_nba_ATL_DET_2026-11-22.txt`.

```
# Laporan Laga NBA: Detroit Pistons vs Atlanta Hawks
Tanggal laga: 22 Nov 2026. Jam mulai: 23 Nov 2026 03:30 UTC+07:00.
Status data: Lengkap.

## Ringkasan
Model memperkirakan total tengah-tengah (median) 219 poin; pasar memasang
garis 225,5 — market mengharap total lebih tinggi dari model (selisih 6,5 poin).
Kaki Asuransi Under 233,5: model 77,0% | pasar 68,5% (kalshi) | akhir 71,1% — WAJAR.
Kaki Utama Under 237,5: model 82,7% | pasar 75,5% (kalshi) | akhir 77,7% — WAJAR.
Cek ulang sebelum pasang: JANGAN PASANG.
```

Bagian "Kenapa beda?" pada laporan ini memeriksa dari data: 10 pemain
absen sudah masuk hitungan model; ada konflik status cedera antar
sumber; median vs garis market selisih 6,5; harga bergerak +0,0¢
sejak analisis; catatan data hilang dicantumkan — kesimpulannya
"cek ulang tidak menemukan alasan konkret — aturan condong-ke-market
memakai probabilitas pasar untuk kaki Asuransi."

## 4. Tanya-jawab

Perintah: `cli.py tanya --analysis <file> [--match <id>]
"<pertanyaan>"`. Exit 0 sukses, 2 bila file tidak bisa dibaca.
Jawaban: `{"question", "intent", "answer", "numbers", "verified"}` —
`verified` False bila ada bagian "tidak terverifikasi" (CLI memberi
penanda di stderr). Intent dikenali deterministik dari kata kunci
(tanpa LLM); pertanyaan tak dikenal dijawab "tidak mengerti" +
daftar jenis yang didukung. `answer()` tidak pernah raise untuk
artefak rusak (fail-closed).

| Intent | Contoh pertanyaan | Sumber jawaban |
|---|---|---|
| `kenapa_total` | Kenapa totalnya 219? | Uraian komponen proyeksi — dihitung ulang dari inputs dengan fungsi engine yang sama (`nba_sim.project_points`, `_dampak_pemain`), bukan perkiraan kedua |
| `bagaimana_jika_absen` | Apa jadinya kalau Cade absen? | Sim ulang 20.000 iterasi (default `RESIM_ITERATIONS`) dengan pemain itu OUT; dasar dan skenario di seed + iterasi sama agar apel-ke-apel |
| `garis_teraman` | Garis Asuransi mana yang paling aman? | p_final tertinggi di antara kaki meets; kaki MAHAL / MODEL_ONLY diberi catatan |
| `kabar_pemain` | Siapa yang diragukan tampil? | Blok injuries artefak (status, alasan, jumlah sumber) |
| `kenapa_beda_model_market` | Kenapa model dan market beda? | Ambang dari config; kesimpulan mekanis dari artefak saja — alasan (a) "pasar tahu sesuatu" tidak pernah diklaim dari satu artefak (butuh data segar → diarahkan ke recheck) |
| `peluang_laga` | Berapa peluang masuk OT? | `score_distribution` sim (OT, moneyline) |

### 4a. Contoh jawaban live (DET@ATL, disingkat)

**"Kenapa totalnya 219?"** — "ATL diperkirakan mencetak 110,1 poin,
DET 108,6 poin. Kecepatan main gabungan sekitar 100,6. … Pemain absen
mengurangi total 4,4 poin: Jalen Duren 2,5 poin, Duncan Robinson
2 poin, CJ McCollum 0,8 poin … Dalam 74 dari 100 simulasi, totalnya
di bawah 232 poin."

**"Apa jadinya kalau Cade Cunningham absen?"** (sim ulang 20.000x,
0,6 detik) — "nilai tengah total turun dari 219 menjadi 213 poin
(turun 6 poin). Peluang ATL menang berubah dari 54,1% menjadi 69,3%.
Peluang total di bawah 233,5 berubah dari 76,2% menjadi 84,8%."

**"Garis Asuransi mana yang paling aman?"** — "yang paling aman adalah
Under 237,5 (Tiket Utama). … peluang menurut model 82,7%, menurut
kalshi 75,5%, gabungannya 77,7% … harganya 76,5¢, labelnya WAJAR."
(Jawaban memilih garis teraman dari semua kaki yang memenuhi syarat —
garis Utama boleh jadi lebih aman dari garis Asuransi bila bantalannya
lebih besar; kedua kaki dicantumkan.)

**"Kenapa model dan market beda?"** — "Nilai tengah model 219 poin,
garis market 225,5 poin — selisih 6,5 poin … Untuk garis Under 233,5
(Asuransi): peluang model 77%, peluang pembanding 68,5% — selisih
8,5 poin. … Saya memeriksa data di analisis ini dan tidak menemukan
alasan konkret … Catatan aturan condong-ke-market: selama selisihnya
di atas 5 poin tanpa alasan konkret, kaki Asuransi memakai peluang
market, bukan model."

## 5. Peracik tiket

Perintah: `cli.py racik --analysis <file...> [--recheck <file...>]
--stake-total <usd> [--out <file>]`. Exit 0 = minimal satu tiket
terracik, 1 = tidak ada tiket yang bisa diracik, 2 = tidak bisa
jalan. Hasil JSON (`format: "tickets"`) berisi kedua tiket (valid vs
`ticket.schema.json`, siap dicatat via `cli.py log --file`),
alasan bila tidak terracik, warnings, dan ringkasan mudah dibaca.
Modal total wajib diisi — peracik tidak mengarang modal; pembagian
50/50 dari config.

Aturan peracik (semua ambang dari config):

- **Garis berbeda untuk laga sama** (kendala wajib temuan auditor
  babak 2, temuan 3): untuk laga yang sama, garis Asuransi dan Utama
  HARUS berbeda (Asuransi lebih tinggi/lebih aman). Bila hanya satu
  garis lolos, laga itu hanya masuk SATU tiket (prioritas Asuransi).
  Diperluas: bila garis Asuransi < garis Utama (bisa terjadi karena
  garis Utama dari median), laga hanya masuk Asuransi. Tiap laga
  ≤1 kaki per tiket (by construction + penjaga dedup).
- **Condong-ke-market berlaku di peracik**: selisih >5 tanpa alasan
  konkret → probabilitas kaki pakai harga market; harga market <74%
  → kaki tidak lolos Asuransi. Peracik TIDAK PERNAH melonggarkan
  putusan recheck (JANGAN_PASANG = tidak masuk tiket). Tanpa recheck,
  peracik menerapkan condong-ke-market sendiri dari artefak.
- **Filter recheck**: hanya TETAP_OK (PERHATIAN hanya dengan alasan
  tercatat + ditandai); JANGAN_PASANG / DATA_INCOMPLETE tidak masuk;
  kaki hilang dari laporan recheck → fail-closed; HOLD → semua kaki
  dicoret.
- **Target pengali (profil user)**: Asuransi 2,2–2,5; Utama 3,0–4,0
  (target lunak ≤4,0), maks 5,0. Bila target tidak tercapai dengan
  kaki yang lolos → tiket None + alasan jujur (tidak memaksa kaki
  yang tidak lolos). Minimal 2 kaki per tiket bila memungkinkan;
  1 kaki hanya bila tidak ada pilihan lain + ditandai.
- **Probabilitas minimum kaki** ditegakkan atas probabilitas
  keputusan: Asuransi 0,74 / Utama 0,65 (config `min_leg_prob`) —
  lihat §9 soal dampaknya di verifikasi live.
- **EV tiket dari simulasi gabungan**: kaki dari laga BERBEDA =
  independen (P menang = Π p_final); kaki dari laga SAMA =
  `simulation.markets["total_under_<garis terendah>"]` (tersedia di
  artefak — sim tahap 2 mengevaluasi semua garis tangga), fallback
  Π p_final + catatan bila tidak tersedia. Pengali kombo dengan
  potongan 5,5% (`combo.spread_cut_pct`). Label DISKON/WAJAR/MAHAL
  per kaki dari artefak. MAHAL tidak masuk Asuransi; boleh masuk
  Utama dengan label.
- **MODEL_ONLY dicoret**: skema tiket mewajibkan `p_market` angka
  (bukan null), jadi kaki tanpa pembanding tidak bisa masuk tiket
  valid — dicoret dengan alasan, skema tidak diubah.
- **Peringatan jendela recheck** (hutang §10 langkah 2): peracik
  memberi peringatan bila recheck terakhir lebih tua dari batas atas
  jendela (60 menit) atau bila belum ada recheck — tidak melarang,
  tapi memperingatkan dengan jelas. Bila satu tiket None, stake
  tidak dialihkan diam-diam.
- **Hanya Alt Under yang diracik**; moneyline tidak dipakai
  (sesuai profil user — hanya bila fakta sangat membuktikan pemenang;
  peracik belum menilai moneyline).

### 5a. Contoh pasangan tiket dari fixture (BUKAN laga nyata)

Slate fixture 4 laga, semua recheck TETAP_OK 30 menit lalu,
`stake_total=20` (dites di `tests/test_ticket_composer.py`):

- **Asuransi** `tkt-2026-11-22-ins`: $10, pengali **x2,24**, 3 kaki
  Under 235.5 @75¢ (BOS@NYK, DET@ATL, LAL@GSW), p_final 0,786/kaki,
  P menang 48,56%, EV +8,77%, DISKON semua.
- **Utama** `tkt-2026-11-22-utm`: $10, pengali **x3,52**, 4 kaki
  Under 231.5 @72¢, p_final 0,746/kaki, P menang 30,97%, EV +8,91%.

Kedua tiket valid terhadap `ticket.schema.json`.

## 6. Wiring CLI + perbaikan `--match`

Tiga subcommand baru mengikuti pola `cmd_recheck` (baca file →
`_ambil_nba_analysis` → modul → tulis output → exit code). `racik`
memakai helper baru `_kumpulkan_nba_analysis` (semua artefak dari
satu file, bukan satu laga) dan mendedup laga yang muncul di dua
file (kemunculan pertama dipakai, dicatat di stderr).

**Perbaikan `--match` (ditemukan saat verifikasi live):**
`_ambil_nba_analysis` hanya mencocokkan `match_id` slate
("nba-2026-11-22-det-atl"), sehingga `--match DET@ATL_2026-11-22`
— ID yang terlihat di laporan dan artefak — ditolak dengan "tidak
punya artefak". Diperbaiki: `--match` kini menerima kedua bentuk
ID. 2 tes regresi di `tests/test_cli_langkah3.py`.

## 7. Perubahan config (v9)

Profil user 2026-11-22 (Utama x3–x4, maks x5; x3,5 saja sudah
berkah; x9–x10 hanya hiburan) kini menjadi nilai config, menggantikan
default blueprint:

| Kunci | Lama | Baru |
|---|---|---|
| `tickets.main.multiplier_min` | 3,5 | **3,0** |
| `tickets.main.multiplier_max` | 6,0 | **5,0** |
| `tickets.main.target_multiplier_max` | — (baru) | **4,0** (target lunak) |

`tests/test_config.py` diperbarui (versi 9 + nilai baru). Mode
agresif tetap membebaskan maks Utama (sesuai komentar config) —
hanya atas perintah user per malam.

## 8. Verifikasi live: slate 7 laga NBA 2026-11-22

Slate dirakit dari scoreboard ESPN (7 laga, semua terjadwal):
DET@ATL, OKC@MIA, ORL@WAS, DEN@CHI, DAL@UTA, IND@NYK, BOS@GSW.
Seluruh rangkaian `--tanpa-odds-api` (**0 kredit**).

### 8.1 Analyze — 6m20d, 7/7 OK

`cli.py analyze` (205 dtk di langkah 2 untuk 1 laga — didominasi
pemindaian penuh jup.ag): 7 laga OK, semua `nba_analysis: OK`,
HOLD 0, DATA_INCOMPLETE 0. Nilai rolling terkonfirmasi di
`inputs_summary` (sigma_total 18,9868; sigma_margin 14,4307;
home 1,6639; B2B −1,5164; t_nu 35,0).

Garis kaki yang dianalisis (semua `meets=True`):

| Laga | Median | Garis market | Selisih | Asuransi | Utama |
|---|---|---|---|---|---|
| DET@ATL | 219 | 225,5 | 6,5 | U233,5 @69,5¢ | U237,5 @76¢ |
| OKC@MIA | 229 | 231,5 | 2,5 | U242,5 @73,5¢ | U240,5 @68,5¢ |
| ORL@WAS | 220 | 221,5 | 1,5 | U233,5 @77¢ | U229,5 @70¢ |
| DEN@CHI | 235 | 237,5 | 2,5 | U248,5 @71,5¢ | U246,5 @67,5¢ |
| DAL@UTA | 217 | 225,5 | 8,5 | U234,5 @69¢ | U238,5 @77¢ |
| IND@NYK | 208 | 216,5 | 8,5 | U224,5 @71¢ | U224,5 @71¢ |
| BOS@GSW | 198 | 211,5 | 13,5 | U219,5 @69,5¢ | U219,5 @69,5¢ |

Slate ini menguji kendala garis berbeda dengan nyata: 2 laga
garisnya IDENTIK (IND@NYK, BOS@GSW) dan 1 laga garisnya TERBALIK
(DAL@UTA: Utama 238,5 > Asuransi 234,5). Selisih median–market
di 4 laga (DET, DAL, IND, BOS) melewati ambang 5,0 — keempatnya
menjadi NO-GO di recheck (§8.2); selisih terbesar BOS@GSW
13,5 poin.

### 8.2 Recheck — 3 GO, 4 NO-GO

7 recheck, total ~11 detik, tanpa resim (tidak ada perubahan
material sejak analyze):

- GO: OKC@MIA, ORL@WAS, DEN@CHI (kedua kaki TETAP_OK).
- NO-GO: DET@ATL, DAL@UTA, IND@NYK, BOS@GSW — kaki Asuransi
  JANGAN_PASANG (aturan condong-ke-market: harga market
  69–71% < 74%, tanpa alasan konkret); kaki Utama TETAP_OK.

### 8.3 Laporan — DET@ATL

`cli.py laporan --match DET@ATL_2026-11-22 --recheck ...` →
16.819 karakter, 17 bagian (§3a). Harga Asuransi bergerak
68,0¢ (langkah 2) → 69,5¢; label berubah DISKON → WAJAR
(EV +1,50%).

### 8.4 Tanya-jawab — 5 intent live

"Kenapa totalnya 219?", "Garis Asuransi mana yang paling aman?",
"Kenapa model dan market beda?", "Siapa yang diragukan tampil?",
dan "Apa jadinya kalau Cade Cunningham absen?" (sim ulang
20.000x, 0,6 detik: median 219→213, ML ATL 54,1%→69,3%).
Jawaban lengkap di §4a.

### 8.5 Peracik — Utama x3,18; Asuransi TIDAK diracik

`cli.py racik --stake-total 20` (7 recheck segar, tanpa
peringatan jendela), exit 0:

**Tiket Utama** `tkt-2026-11-22-utm`: $10, pengali **x3,1847**,
4 kaki — Under 219.5 BOS@GSW @70¢ (p_final 0,742),
Under 224.5 IND@NYK @71,5¢ (0,737), Under 237.5 DET@ATL
@76,5¢ (0,777), Under 238.5 DAL@UTA @77,5¢ (0,803).
P menang 34,09%, EV **+8,57%** (+$0,86), kembali $31,85 bila
menang. Valid vs `ticket.schema.json`. Perhitungan diverifikasi
tangan oleh koordinator: pengali Π(100/harga)×0,945 = 3,1847 ✓;
P menang Π p_final = 0,3409 ✓; EV = 0,3409×3,1847−1 = +8,57% ✓.

**Tiket Asuransi: TIDAK diracik.** Alasan: "Kaki Asuransi yang
lolos hanya mencapai pengali x1,65 — target x2,20–x2,50 tidak
tercapai." Hanya 2 kaki Asuransi yang lolos (OKC@MIA U242,5 dan
ORL@WAS U233,5): 4 kaki ditolak recheck (condong-ke-market),
dan 1 kaki — DEN@CHI U248,5 (p_final 0,7352) — gugur oleh
`min_leg_prob` 0,74 (§9). Dengan 2 kaki, pengali maks
(100/74)×(100/77,5)×0,945 ≈ x1,65. Mesin menolak memaksakan
tiket — perilaku fail-closed yang benar. Konsekuensinya,
stake Asuransi ($10) TIDAK dialihkan ke Utama (tidak ada
pengalihan diam-diam).

## 9. Keterbatasan (jujur) + pertanyaan terbuka

- **`min_leg_prob` sebagai gate keras — pertanyaan untuk
  reviewer/user.** Peracik menegakkan `min_leg_prob` 0,74 atas
  p_final sebagai syarat keras. Di slate live, ini menggugurkan
  kaki DEN@CHI (p_final 0,7352 — hanya 0,5 poin di bawah ambang),
  yang membuat Asuransi tidak terracik. Padahal §6a menulis
  "idealnya ≥74% per kaki" — kata "idealnya" bisa dibaca sebagai
  preferensi lunak, bukan gate keras. Bila lunak, Asuransi live
  akan terracik 3 kaki (~x2,34). Koordinator TIDAK mengubahnya
  sepihak (melonggarkan gate agar tiket muncul adalah memanipulasi
  hasil) — keputusan menunggu user/reviewer. Perubahan ini satu
  tempat di `_kumpulkan_kandidat` bila diputuskan.
- **Kaki recheck belum membawa kunci `ticket`** (§3b langkah 2) —
  laporan + peracik mengambil nama tiket dari akhir `leg_id`;
  berfungsi tapi rapuh.
- **H2H kosong di data live** (`inputs.h2h_last5` = `[]` bila
  kedua tim belum bertemu musim ini) — laporan menulis "tidak
  terverifikasi". Pertanyaan desain: apakah H2H musim lalu boleh
  dipakai bila musim ini kosong?
- **Tangga total mencampur garis full-game + babak** (53,5–62,5;
  99,5–125,5) tanpa penanda babak di entri hasil parse. Laporan
  hanya menampilkan garis Under ≥ garis utama + catatan. Usul:
  tambah penanda periode di `parse_event_ladders` atau filter ke
  full-game.
- **Skenario skuad hanya membawa peluang** (`markets`), tanpa
  proyeksi total/median per skenario — laporan tidak bisa
  menampilkan "total proyeksi bila bintang absen".
- **Pemain hanya membawa BPM + menit** — tanpa poin/rebound/assist
  atau form per pemain; "rating pemain kunci" terbatas pada itu.
- **Tidak ada data pergerakan harga di artefak analisis** (hanya
  `price_snapshots` harga pertama) — pemeriksaan harga di "Kenapa
  beda?" hanya bisa dari recheck.
- **Status turnamen selalu tidak terverifikasi**
  (`tournament_flag_tidak_dapat_ditentukan` selalu ada di
  `missing`) — sudah diketahui sejak langkah 1.
- **Berita non-cedera belum terdeteksi** (hutang langkah 2, masih
  berlaku) — tidak ada modul berita.
- **Recheck tidak mengambil pembanding baru** (hutang langkah 2) —
  `p_market` dibawa dari analisis awal.
- **Moneyline jup.ag tidak dicek** (hutang langkah 2) — repo tidak
  punya fetcher moneyline jup.ag per-event.
- **Analyze lambat**: 6m20d untuk 7 laga (didominasi pemindaian
  penuh jup.ag 52 halaman). Untuk slate lebih besar, waktu belum
  diukur.
- **`p_total_loss` dibiarkan null** (butuh sebaran gabungan
  antar-tiket yang berkorelasi); EV negatif hanya peringatan,
  bukan gate; syarat cover §6a dicek, peringatan saja.
- **MODEL_ONLY dicoret dari tiket** (skema mewajibkan `p_market`
  angka) — kaki tanpa pembanding tidak bisa masuk tiket valid.
- **Shrinkage K=10 belum terbukti** (hutang langkah 2) — pilihan
  desain, bukan fit; hanya uji historis (DunkAPI) yang menjawab.

## 10. Hutang ke langkah 4 (pantauan live) + lanjutan

- Pantauan live dalam laga + status tiket real-time
  ("tiketmu masih hijau") + deteksi anomali (FT berlebihan,
  hujan tripoin) — langkah 4.
- Uji historis model-vs-market dengan garis penutupan DunkAPI
  (menunggu persetujuan signup user, §7 langkah 2) — menentukan
  kapan kepercayaan ke model dipulihkan dari aturan
  condong-ke-market.
- Pertanyaan H2H musim lalu, penanda periode tangga, ringkasan
  distribusi per skenario (§9).
- Pertanyaan `min_leg_prob` keras vs lunak (§9).
- Otak bola (langkah 5), belajar sendiri (langkah 6).

## 11. File yang berubah

Baru: `report/nba_report.py`, `engine/qa.py`,
`engine/ticket_composer.py`, `tests/test_report_nba.py`,
`tests/test_qa.py`, `tests/test_ticket_composer.py`,
`tests/test_cli_langkah3.py`,
`examples/laporan_nba_ATL_DET_2026-11-22.txt`, laporan ini.
Diubah: `cli.py`, `config/playstyle.yaml` (v9),
`tests/test_config.py`, `DECISIONS.md`. Tidak ada `.env`, `data/`,
`out/`, atau cache yang di-commit.

## 12. Keputusan menunggu objeksi reviewer

- `tickets.main`: min 3,0 / maks 5,0 / target lunak 4,0 (profil
  user 2026-11-22, §7).
- `min_leg_prob` sebagai gate keras di peracik (§9).
- Peracik: prioritas Asuransi bila satu garis; garis terbalik →
  laga hanya masuk Asuransi; PERHATIAN wajib alasan tercatat;
  tanpa recheck kaki tetap boleh dipakai + peringatan jendela;
  stake tidak dialihkan bila satu tiket None; mode agresif
  membebaskan maks Utama.
- Laporan: bagian "Kenapa beda?" tetap tampil bila ada anomali
  `kenapa_beda_required` walau tidak ada kaki yang selisihnya
  > 8 poin.
- Tanya-jawab: pencocokan pemain (nama lengkap substring, lalu
  nama belakang unik ≥3 huruf); kata "ot" dicocokkan sebagai kata
  utuh; sim ulang default 20.000 iterasi; QA memakai fungsi privat
  `nba_sim` (`_dampak_pemain`, `_combined_stats`) agar aritmetika
  komponen identik dengan sim.
- `--match` menerima match_id artefak maupun slate (§6).
- (Ditutup langkah ini: hutang peringatan jendela recheck §10
  langkah 2; kendala garis berbeda Asuransi/Utama §11 langkah 2;
  condong-ke-market di peracik §11 langkah 2.)
