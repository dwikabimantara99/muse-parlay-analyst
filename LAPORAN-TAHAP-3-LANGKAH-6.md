# Laporan Tahap 3 Langkah 6 — Belajar Sendiri (Self-Learning)

Langkah TERAKHIR dari urutan bangun yang disetujui user (1 otak NBA,
2 cek ulang, 3 laporan+tanya-jawab, 4 pantauan live, 5 otak bola,
6 belajar sendiri). Commit: (lihat log git). Tes: 1308 lulus (dari
1207). Ruff + black bersih. 0 kredit Odds API. On-demand (tidak ada
loop terjadwal).

## 1. Ringkasan

Mesin sekarang bisa belajar dari hasilnya sendiri — dengan satu pagar
yang tidak bisa ditawar: **mesin TIDAK PERNAH mengubah parameter,
ambang, atau strategi secara diam-diam.** Ia menghitung dari data,
mengusulkan perubahan dengan bukti angka, dan perubahan hanya berlaku
setelah user menyetujui (pola D12, sama seperti persetujuan parameter
fit NBA).

Yang dibangun:

- **Pelacakan hasil** (`engine/learning.py`): membaca ledger
  (tiket + kaki yang sudah selesai), menghitung Brier per pasar
  (model vs pasar vs tebakan dasar) dan EV terealisasi vs EV
  prediksi.
- **Kalibrasi w** (`engine/calibration.py`): rekomendasi bobot blend
  w dari Brier tiap 50 kaki (keputusan user 2026-11-21) —
  rekomendasi saja, tidak pernah diterapkan otomatis.
- **Usulan belajar** (`engine/proposals.py`): usulan perubahan dari
  data (pasar yang sebaiknya tidak dimainkan, ambang EV yang terlalu
  optimis, pasar tempat model mengalahkan market) — tiap usulan
  membawa bukti angka, jumlah sampel, dan keyakinan; status selalu
  `menunggu_persetujuan`.
- **Perintah `cli.py belajar`** + laporan mudah dibaca
  (`report/learning_report.py`): ringkasan dalam Bahasa Indonesia
  sehari-hari — di mana mesin lebih jago dari market, di mana tidak,
  apa yang dipelajari, dan usulan apa yang menunggu persetujuan.

Keadaan jujur saat ini: **belum ada satu pun tiket nyata yang
selesai** (`ledger.db` belum ada), jadi laporan belajar saat ini
berbunyi "belum ada hasil tercatat" — bukan mengarang. Semua validasi
langkah ini memakai replay backtest + fixture sintetis yang dilabeli
jelas (§8).

## 2. Apa yang dibangun

| File | Isi |
|---|---|
| `engine/learning.py` (baru) | `muat_hasil_ledger`, `ringkasan_per_pasar`, `ringkasan_keseluruhan` |
| `engine/calibration.py` (baru) | `rekomendasi_w` (grid search w 0,00–1,00) |
| `engine/proposals.py` (baru) | `hasilkan_usulan` (aturan a–d, §6) |
| `report/learning_report.py` (baru) | `render_laporan_belajar` (teks Bahasa Indonesia) |
| `scripts/laporan_belajar_replay.py` (baru) | Replay dari `out/validation_nba_rolling.json` + cek silang Brier |
| `cli.py` (+198/−2) | Subcommand `belajar` (`--db`, `--keluaran`, `--contoh-sintetis`) |
| `config/playstyle.yaml` (v11→v12) | `calibration.min_legs_w: 50` + section baru `learning:` |
| `config.py` | `"learning"` masuk `REQUIRED_PLAYSTYLE_SECTIONS` |
| `tests/fixtures/sintetis_belajar_kaki.json` (baru) | 62 kaki sintetis (dilabeli) |
| `examples/laporan_belajar_contoh_sintetis.txt` (baru) | Contoh keluaran `--contoh-sintetis` (label SINTETIS 4×) |
| `tests/test_learning.py`, `test_calibration.py`, `test_proposals.py`, `test_learning_report.py`, `test_cli_belajar.py` (baru) | 101 tes baru (16+10+18+57 dari C: 57 = report+CLI) |

Brier memakai ulang `engine/validation.py` (`brier_score`,
`calibration_summary`) — tidak ditulis ulang.

## 3. Cara kerja loop belajar + pengaman persetujuan

```
ledger (tiket PAPER yang sudah settle)
  -> engine/learning.py: rekor hasil + ringkasan per pasar
  -> engine/calibration.py: rekomendasi w (hitung saja)
  -> engine/proposals.py: usulan perubahan (hitung saja)
  -> cli.py belajar: laporan mudah dibaca
  -> USER memutuskan (setuju / tolak / tunda)
  -> (bila setuju) perubahan diterapkan manual + dicatat di DECISIONS.md
```

Pengaman (ditegakkan kode + tes, bukan sekadar janji):

- `rekomendasi_w` dan `hasilkan_usulan` adalah fungsi murni tanpa
  tulis file; setiap keluaran membawa `"diterapkan": False` dan
  `"butuh_persetujuan_user": True` (kalibrasi) /
  `"status": "menunggu_persetujuan"` (usulan). Tes membuktikan
  `playstyle.yaml` tidak berubah (hash file) setelah rekomendasi
  w=1,0 dihitung — `blend.w_model` tetap 0,3.
- Sampel minimum ditegakkan: w baru hanya diusulkan bila n >= 50
  kaki settled dengan p_model DAN p_market
  (`calibration.min_legs_w`); usulan pasar butuh n >= 20
  (`learning.min_n_pasar`). Di bawah itu mesin diam dan berkata
  "sampel belum cukup".
- Kaki VOID/PUSH dikeluarkan dari statistik (dihitung di
  `n_dikeluarkan`); kaki PENDING tidak masuk Brier. Hasil di luar
  skema tidak ditebak — dihitung di `n_hasil_tidak_dikenal`.

## 4. Pelacakan hasil

`muat_hasil_ledger` membaca ledger read-only (`mode=ro` — file tidak
dibuat/diubah; dibuktikan tes byte-per-byte). Bila file tidak ada,
tabel kosong, atau tidak ada kaki settled, hasilnya `ada_data: False`
+ pesan jujur, bukan error dan bukan angka karangan.

Rekor hasil (OUTCOME RECORD, kontrak antar-modul, 14 kunci): leg_id,
ticket_id, sport, market, selection, p_model, p_market, p_final,
price_buy_cents, price_close_cents, ev_pct (fraksi), result
(True/False/None), settled, sumber.

Dua ketidaksesuaian skema yang ditemukan dan ditangani saat membaca
ledger (keduanya didokumentasikan di docstring modul):

1. **Sport**: ledger menyimpan `"nba"`/`"football"`
   (ticket.schema.json), kontrak memakai `"NBA"`/`"soccer"` →
   dinormalisasi saat baca.
2. **ev_pct**: ledger menyimpan EV dalam PERSEN (kedua modul analisis
   mengalikan 100; tiket contoh berisi 2.1/1.8) → dibagi 100 saat
   baca, sehingga EV prediksi sebanding langsung dengan EV
   terealisasi (fraksi). Bila penulis ledger suatu hari berubah ke
   fraksi, konversi ini harus dicabut.

Per pasar, ringkasan menghitung: n, win rate, Brier model/market/
final (masing-masing hanya atas kaki yang punya nilai itu; bila tidak
ada → None + alasan), Brier tebakan dasar (frekuensi aktual sebagai
prediksi konstan), EV prediksi rata-rata, dan EV terealisasi
rata-rata (per kaki: WIN → 100/harga_beli − 1, LOSS → −1 —
didokumentasikan sebagai diagnostik per kaki, BUKAN untung/rugi
tiket parlay).

## 5. Kalibrasi w

`rekomendasi_w(outcomes, cfg)`: atas kaki settled yang punya p_model
DAN p_market, grid search w = 0,00–1,00 langkah 0,05; tiap w dihitung
Brier blend-nya (dihitung ulang dari `brier_score`, bukan dari
p_final tersimpan, supaya rekomendasi tidak bergantung pada w lama);
dipilih w dengan Brier terkecil. Kaki MODEL_ONLY (tanpa p_market)
diabaikan — tanpa pembanding pasar, w tidak bisa dikalibrasi.

Keputusan desain (terdokumentasi di docstring):

- **Tie-break**: bila beberapa w berbagi Brier terkecil, dipilih w
  terkecil (pemindaian 0,00→1,00, minimum pertama menang).
- **Bila w optimal sama dengan w saat ini**: alasan berbunyi "tidak
  ada perubahan yang diusulkan".
- Bila n = 0, semua Brier None (tidak ada yang bisa dihitung).

## 6. Usulan belajar

`hasilkan_usulan(ringkasan, outcomes, cfg)` — empat aturan
(ambang di config, section `learning:`):

| Aturan | Pemicu | Jenis |
|---|---|---|
| (a) | Brier model > Brier tebakan dasar DAN n >= 20 | `pasar` — pertimbangkan tidak memainkan / menaikkan ambang pasar itu |
| (b) | Brier model < Brier market DAN n >= 50 | `kalibrasi` — model mengalahkan market di pasar ini, pertimbangkan menaikkan w khusus pasar |
| (c) | EV terealisasi < EV prediksi − 0,05 DAN n >= 20 | `ambang` — EV prediksi terlalu optimis, tinjau ambang EV/label harga |
| (d) | Tidak ada kaki settled sama sekali | `data` — belum ada hasil tercatat, kumpulkan data PAPER dulu |

Tiap usulan: id berurutan (`USUL-001`, ...), judul, isi, bukti
(angka-angka), n, keyakinan dari n (<20 rendah, 20–49 sedang, >=50
tinggi; ambang di `learning.keyakinan_n`), status selalu
`menunggu_persetujuan`, dan teks aksi yang tidak dieksekusi.

Config baru (playstyle.yaml v12): `calibration.min_legs_w: 50`;
`learning.min_n_pasar: 20`; `learning.min_n_kalibrasi_pasar: 50`;
`learning.ev_gap_warn: 0.05`; `learning.keyakinan_n: {sedang_min: 20,
tinggi_min: 50}`.

## 7. Laporan belajar (`cli.py belajar`)

```
python3 cli.py belajar [--db PATH] [--keluaran PATH] [--contoh-sintetis]
```

- Tanpa DB / tanpa kaki settled: laporan singkat "Belum ada hasil
  tercatat" + langkah yang perlu terjadi dulu (catat tiket PAPER,
  selesaikan setelah laga usai, jalankan lagi) — exit 0.
- Dengan data: ringkasan (kaki settled, menang/kalah, Brier model vs
  pasar vs tebakan dasar, EV prediksi vs terealisasi), per pasar
  (di mana model lebih jago, di mana tidak, dengan n tiap pasar),
  kalibrasi w (w saat ini, rekomendasi bila ada, kalimat "belum
  diterapkan — menunggu persetujuanmu"), usulan yang menunggu
  persetujuan, dan keterbatasan.
- `--contoh-sintetis`: demo atas fixture sintetis (62 kaki),
  laporan berlabel `DATA SINTETIS — BUKAN HASIL NYATA` di judul,
  ringkasan, dan keterbatasan.
- `--keluaran PATH`: menulis laporan ke file.
- Import modul belajar defensif via `find_spec`: modul yang belum
  ada → bagiannya ditandai "belum tersedia" di laporan;
  `learning` hilang → exit 2; error DI DALAM modul yang ada tetap
  raise (tidak ditutup fallback diam-diam).
- Ambang "hampir sama" untuk verdict Brier di laporan: 0,005
  (tampilan saja, bukan ambang strategi) — selisih di bawah itu
  tidak diklaim "lebih jago".

## 8. Validasi: replay + sintetis

### 8a. Replay backtest NBA (bukan tiket nyata)

`scripts/laporan_belajar_replay.py` membaca
`out/validation_nba_rolling.json` (150 laga backtest rolling) dan
membangun 2 kaki per laga (moneyline + total Under) — 300 kaki.
`p_final = p_model` (aturan MODEL_ONLY yang sudah ada).

**Cek silang Brier COCOK persis dengan file validasi** (selisih 0
s.d. 6 desimal): moneyline 0,198308, total Under 0,219926.
Kalibrasi w replay: n=0, `cukup_data=False` — sesuai harapan, karena
backtest tidak punya harga pasar historis (perbandingan
model-vs-pasar DATA_INCOMPLETE di replay). Usulan replay: 0 (tidak
ada aturan terpicu). Laporan tersimpan di
`out/laporan_belajar_replay.txt` (gitignored, tidak di-commit).

Yang dibuktikan replay: pipa pelacakan hasil menghitung Brier
dengan benar atas data nyata model. Yang TIDAK dibuktikan replay:
apa pun soal pasar (tanpa garis penutupan historis) dan apa pun
soal tiket (backtest bukan tiket).

### 8b. Fixture sintetis (62 kaki, dilabeli)

`tests/fixtures/sintetis_belajar_kaki.json`: NBA total_under 24,
moneyline 20, bola 1X2 8, O/U 6, BTTS 4. Sifatnya diverifikasi dari
angka (dihitung ulang koordinator secara independen, bukan dari
klaim pekerja):

- Total Under: Brier model 0,1581 < pasar 0,3331 (model menang).
- Moneyline: Brier model 0,40 > tebakan dasar 0,24 (model kalah
  dari tebakan dasar) → memicu USUL-001 (pasar) + USUL-002
  (ambang), keduanya keyakinan "sedang" (n=20), status
  `menunggu_persetujuan`.
- Kalibrasi w: **w_rekomendasi 0,75** (Brier blend 0,2783 pada w=0,3
  → 0,2710 pada w=0,75) — diverifikasi dua cara (hitung tangan
  Brier blend per w + optimum kontinu w* ≈ 0,7376).
- Keseluruhan sintetis: 35 menang dari 62 (56,5%); Brier model
  0,2736 vs pasar 0,2917 vs tebakan dasar 0,2458 — model mengalahkan
  pasar tapi kalah dari tebakan dasar (fixture dirancang begitu
  untuk menguji kedua verdict).

Contoh keluaran: `examples/laporan_belajar_contoh_sintetis.txt`.

## 9. Apa yang bisa dipelajari sekarang vs butuh data nyata

**Bisa sekarang (tanpa tiket nyata):**

- Pipa belajar bekerja ujung-ke-ujung (ledger → ringkasan →
  kalibrasi → usulan → laporan) — dibuktikan replay + sintetis.
- Dari replay: model NBA lebih baik dari tebakan dasar di moneyline
  (Brier 0,1983 vs 0,2436) dan total Under (0,2199 vs 0,2200 —
  praktis sama, konsisten dengan temuan langkah 1/1b bahwa Under
  belum terbukti punya skill).
- Pola usulan + pengaman persetujuan teruji.

**Butuh data nyata (tiket PAPER dicatat + diselesaikan):**

- Kalibrasi w yang sesungguhnya (butuh >= 50 kaki settled dengan
  p_model DAN p_market).
- Usulan pasar/ambang yang sesungguhnya (butuh n >= 20 per pasar).
- Perbandingan model vs pasar yang sesungguhnya — dan, bila signup
  DunkAPI disetujui, uji historis dengan garis penutupan (§11).
- Sampai data itu ada, aturan condong-ke-market (keputusan
  2026-11-22) tetap berlaku: model belum terbukti lebih akurat
  dari market soal total.

## 10. Keterbatasan (jujur)

- **Belum ada satu pun hasil nyata.** Semua angka belajar hari ini
  berasal dari replay/sintetis. Laporan belajar nyata pertama baru
  ada setelah tiket PAPER dicatat dan diselesaikan di ledger.
- **Tidak ada harga pasar historis** di backtest — replay tidak bisa
  menguji kalibrasi w maupun aturan (b). Uji itu menunggu data
  DunkAPI (signup belum disetujui) atau kaki ledger nyata.
- **EV terealisasi per kaki bukan P/L tiket.** Kaki hidup di dalam
  parlay; diagnostik per kaki tidak sama dengan untung/rugi tiket
  (yang dihitung ledger dari pengali + hasil tiket).
- **Grid w kasar** (langkah 0,05) — cukup untuk rekomendasi, bukan
  untuk presisi. Optimum kontinu bisa berbeda beberapa poin (contoh
  sintetis: grid 0,75 vs kontinu 0,7376).
- **Keyakinan dari n saja** — belum memakai uji signifikansi
  (mis. selang kepercayaan Brier). Usulan "tinggi" pada n=50 masih
  bisa salah bila pasarnya berubah (regime shift, seperti pelajaran
  BTTS LaLiga di langkah 5).
- **Tidak ada bobot resensi** — kaki lama dan kaki baru berbobot
  sama. Jendela geser / bobot resensi adalah lanjutan (sejalan
  dengan hutang langkah 5).
- **Recheck bola belum didefinisikan** (hutang langkah 5) — kaki
  bola yang masuk belajar belum melewati cek ulang pra-submit
  seperti kaki NBA.

## 11. Keputusan yang masih menunggu user di seluruh Tahap 3

Tahap 3 selesai dibangun (langkah 1–6). Yang masih menunggu:

**Menunggu user:**

1. **Persetujuan fit bola (D12)** — adopsi rho + rata-rata gol ke
   `playstyle.yaml` atau tidak; pilihan rho gabungan vs rho = 0
   (langkah 5 §3). Sampai disetujui, parameter fit bola tetap null.
2. **Ratifikasi FPL** sebagai sumber cedera bola tier-1 (sejak 2b)
   + sumber cedera bola KEDUA (belum ada kandidat) — tanpa ini
   semua laga bola HOLD (aturan B2).
3. **Signup DunkAPI** (probe langkah 2 §7: garis penutupan tersedia
   sejak Juli 2020; uji 150 laga ≈ 150 kredit via rute per-hari
   dari 500 kredit gratis/bulan) — membuka uji historis
   model-vs-market dan Brier pasar untuk bola.
4. **`min_leg_prob` keras vs lunak** (langkah 3 §9): peracik
   menegakkan 0,74 sebagai gate keras; kaki DEN@CHI (p_final
   0,7352) gugur karenanya.
5. **Kenaikan w** — kapan pun modul belajar mengusulkan w baru,
   penerapannya butuh persetujuan user (keputusan 2026-11-21).
   Saat ini belum ada usulan (belum ada data).

**Menunggu keberatan reviewer:** koreksi rumus defence (langkah 5
§8.1), perluasan GARIS_TOTAL (langkah 5 §8.2), BPM_replacement
−2,0, shrinkage K=10 (langkah 2).

**Hutang lanjutan (bukan keputusan, tapi pekerjaan):** recheck bola
belum didefinisikan; CLI laporan/tanya/racik untuk artefak bola;
narasi bola + ambang "Kenapa beda?" bola; ingest LaLiga; bobot
resensi / jendela geser untuk fit; pemodelan absensi pemain bola;
pengecekan ulang `pantau` saat laga NBA benar-benar berjalan
(termasuk OT); kalibrasi ambang status/anomali live atas data PAPER;
berita non-cedera belum terdeteksi; recheck tidak mengambil
pembanding baru; moneyline jup.ag tidak dicek.

## 12. Keputusan koordinator (integrasi)

- **Pin versi config 11→12** diperbarui di dua tes
  (`test_config.py::test_meta_versi_12`,
  `test_ticket_composer.py::test_config_main_maks_5_target_4`) —
  satu-satunya kegagalan suite setelah bump versi pekerja B.
- **`"learning"` ditambahkan ke `REQUIRED_PLAYSTYLE_SECTIONS`**
  (`config.py`) — saran pekerja B, diterima: modul proposals
  membaca kunci `learning.*` langsung, jadi config yang kehilangan
  section itu harus gagal cepat dengan ConfigError yang jelas.
  (Section `soccer` langkah 5 tidak ada di daftar wajib — itu
  urusan langkah 5, tidak diubah di sini.)
- **Verifikasi independen koordinator**: tes tiap pekerja
  dijalankan ulang (A 16/16, B 28/28, C 57/57); `cli.py belajar`
  dijalankan langsung (tanpa DB → "belum ada data", exit 0;
  `--contoh-sintetis` → laporan berlabel); replay dijalankan
  langsung (cek silang Brier cocok persis); angka fixture
  sintetis dihitung ulang (w 0,75, Brier per pasar, 2 usulan);
  konversi ev_pct persen→fraksi dicek ke sumbernya
  (`nba_analysis.py`, `soccer_analysis.py`, tiket contoh).
- **Tidak ada `learning_fallback.py`** (keputusan pekerja C,
  disetujui): ketiga modul A/B mendarat sebelum CLI selesai, jadi
  CLI memakai modul asli dengan import defensif via `find_spec`.

## 13. File yang berubah

Baru: `engine/learning.py`, `engine/calibration.py`,
`engine/proposals.py`, `report/learning_report.py`,
`scripts/laporan_belajar_replay.py`,
`tests/fixtures/sintetis_belajar_kaki.json`,
`examples/laporan_belajar_contoh_sintetis.txt`,
`tests/test_learning.py`, `tests/test_calibration.py`,
`tests/test_proposals.py`, `tests/test_learning_report.py`,
`tests/test_cli_belajar.py`, `LAPORAN-TAHAP-3-LANGKAH-6.md` (ini).

Diubah: `cli.py`, `config.py`, `config/playstyle.yaml` (v12),
`examples/README.md`, `tests/test_config.py`,
`tests/test_ticket_composer.py`, `DECISIONS.md`.
