# LAPORAN TAHAP 3 LANGKAH 4 — Pantauan Live Dalam Laga

## 1. Ringkasan

Langkah 4 selesai: mesin kini bisa memantau tiket yang sedang
berjalan — memeriksa skor live, memproyeksikan total akhir tiap
kaki Under, memberi status AMAN / WASPADA / TERANCAM dengan bahasa
sehari-hari ("Tiket Utamamu masih hijau"), dan mendeteksi anomali
dalam laga (hujan 3 angka, lemparan bebas berlebihan, laju skor
terlalu cepat). Perintah baru: `cli.py pantau --ticket <file>`.

- **Tes: 1088 (dari 966)** — semua lulus; ruff + black bersih.
- **Config v10** — section `live:` baru (ambang status + anomali,
  semua nilai awal belum dikalibrasi).
- **0 kredit Odds API** — skor live dari ESPN, baseline dari BBRef.
- **On-demand** (sesuai jawaban user #2): tidak ada loop terjadwal;
  pantauan berjalan saat user memintanya.

Verifikasi dilakukan dengan replay laga selesai lewat data ESPN
asli + tiket asli 22 Nov (laga belum mulai) + fixture laga
berjalan. **Tidak ada laga live sungguhan saat verifikasi**
(21:30 WIB = pagi di AS; laga tip-off ~07:00 WIB 23 Nov) — perilaku
di tengah laga yang benar-benar berjalan, termasuk jam OT, masih
perlu satu pengecekan ulang saat ada laga berjalan (§7, §9).

## 2. Apa yang dibangun

| Bagian | File | Isi |
|---|---|---|
| Umpan skor live | `ingest/live_nba.py` (baru) | Scoreboard ESPN (skor, kuarter, jam, status) + summary boxscore (3PT, FT per tim) |
| Status tiket + proyeksi | `engine/live_status.py` (baru) | Proyeksi total akhir pace-based (blend), status kaki/tiket, teks Indonesia |
| Deteksi anomali | `engine/live_anomaly.py` (baru) | 3 jenis anomali + baseline tembakan BBRef |
| Baseline tembakan | `ingest/bbref.py` (tambah) | `fetch_team_shooting_baselines` (3PA/laga, FTA/laga per tim) |
| CLI | `cli.py` (tambah) | `cmd_pantau` + subparser `pantau` |
| Config | `config/playstyle.yaml` (v10) | Section `live:` (8 kunci) |

Tes baru: `tests/test_live_nba.py` (39),
`tests/test_live_status.py` (42), `tests/test_live_anomaly.py`
(27), `tests/test_cli_pantau.py` (13). Fixture: respons ESPN asli
(scoreboard 21 Nov 6 laga + summary MIL@PHI) + fixture simulasi
laga berjalan + HTML totals BBRef.

## 3. Umpan skor live

Sumber utama scoreboard ESPN
(`site.api.espn.com/.../basketball/nba/scoreboard`, terverifikasi
di probe 2a); statistik berjalan dari summary ESPN per laga
(`.../nba/summary?event={id}`, boxscore). Bila feed gagal → kaki
yang bersangkutan DATA_INCOMPLETE, bukan tebakan. Tanpa cache
disk (skor berubah tiap detik); rate limit 1 detik per modul.

Temuan format ESPN (terverifikasi dari respons asli, bukan
dugaan):

- Skor kompetitor adalah **string** (`"132"`), diubah ke int.
- Skor per kuarter ada di kunci **`linescores`** (huruf kecil
  semua), entri `{"displayValue": "29"}` — bukan
  `lineScores`/`value` seperti dugaan awal. Parser membaca format
  asli + fallback camelCase.
- Tanggal parameter `dates` ESPN adalah **tanggal Amerika Timur**;
  laga malam AS punya field `date` UTC keesokan hari. Tanggal
  `match_id` diambil dari tanggal yang diminta, atau dari field
  date yang dikonversi ke `America/New_York`.
- **Singkatan ESPN berbeda dari tricode repo untuk 6 tim:**
  GS→GSW, NY→NYK, NO→NOP, SA→SAS, UTAH→UTA, WSH→WAS.
  Ditemukan pekerja A (4 tim) + koordinator saat verifikasi live
  (UTAH — kaki DAL@UTA tidak join sampai pemetaan ditambahkan;
  WSH mentah dikonfirmasi dari JSON asli). Ke-30 singkatan ESPN
  sudah dicocokkan dengan tricode repo (scoreboard 21–23 Nov).
  Tanpa pemetaan ini, laga 6 tim itu tidak pernah tersambung ke
  kaki tiket maupun baseline BBRef.

`stats.nba.com` sebagai cadangan **tidak dibangun** (dinilai di
luar tugas; ESPN saja yang jadi sumber).

## 4. Status tiket + proyeksi total akhir

Metode proyeksi (pace-based, didokumentasikan di docstring
`engine/live_status.py`):

- `menit_lalu = 48 − menit_sisa` (dari `seconds_remaining`; OT:
  `48 + 5×(period−4) − sisa OT berjalan`).
- `live_rate = total_berjalan / menit_lalu` (butuh ≥ 1 menit).
- `pregame_rate = median_total_pra_laga / 48` (bila ada artefak
  analisis; tanpa median → metode `live_rate_only` + catatan).
- Bobot `w_live = menit_lalu / 48` dijepit [0,1] — makin lama laga
  berjalan, makin besar porsi laju live.
- `projected = total_berjalan + (w_live×live_rate +
  (1−w_live)×pregame_rate) × menit_sisa`.
- Laga selesai → proyeksi = total akhir (metode `final`).
- **Risiko OT:** flag True bila `|selisih skor| ≤ 3` DAN sisa
  `≤ 2,0 menit` — laga bisa OT dan total bertambah (penting untuk
  kaki Under). Proyeksi sendiri tidak menambah menit OT.

Status kaki Under (margin = garis − proyeksi): margin ≥ 6,0 →
**AMAN**; ≥ 2,0 → **WASPADA**; sisanya **TERANCAM**. Laga selesai:
total < garis → **MENANG**; > garis → **KALAH**; == garis →
**PUSH** (keputusan modul: seri, modal kaki biasanya kembali;
garis .5 praktis tidak pernah push). Laga belum mulai →
**BELUM_MULAI**. Pasar bukan `total_under`, garis tak terurai
dari `selection`, laga tak ditemukan, atau proyeksi tak bisa
dihitung → **DATA_INCOMPLETE** + alasan.

Status tiket = kaki terburuk, urutan: KALAH > TERANCAM > WASPADA
> DATA_INCOMPLETE > AMAN > BELUM_MULAI. Kaki selesai tidak
menarik status ke bawah (campuran mengikuti kaki terburuk yang
belum selesai + catatan). Semua MENANG → MENANG; semua PUSH →
PUSH; campuran MENANG+PUSH → MENANG + catatan.

Teks contoh (dari verifikasi live): "Tiket Utamamu kalah — ada
kaki yang kalah." / "Kaki MIL@PHI kalah — total akhir 261 di
atas garis 237,5." / "Tiket Utamamu belum mulai — semua laga
belum berjalan."

## 5. Deteksi anomali dalam laga

Tiga jenis (ambang di config, nilai awal belum dikalibrasi):

- **Hujan 3 angka** (`hujan_3pt`): laju 3PA gabungan kedua tim
  ≥ baseline gabungan × 1,5.
- **FT berlebihan** (`ft_berlebihan`): laju FTA gabungan ≥
  baseline gabungan × 1,5.
- **Laju skor tinggi** (`laju_skor_tinggi`): laju poin/menit live
  ≥ laju pra-laga × 1,15 (hanya bila median pra-laga ada).

Hanya dievaluasi bila laga sudah berjalan ≥ 12 menit (di bawah
itu sampel terlalu kecil → dilewati + alasan). Bila stats atau
baseline hilang → jenis itu dilewati + dicatat di `skipped`,
tidak pernah ditebak. Tiap anomali membawa `description` +
`implication` Bahasa Indonesia (artinya untuk kaki Under).

Baseline: rata-rata musim berjalan per tim (3PA/laga, FTA/laga)
dari tabel totals tim BBRef. **Koreksi sumber:** tugas mengira
tabel tim ada di `leagues/NBA_YYYY_totals.html` — salah,
terverifikasi dari HTML asli: halaman itu hanya memuat tabel
pemain; tabel totals tim (`id="totals-team"`, dibungkus komentar
HTML) ada di halaman **utama** liga `leagues/NBA_YYYY.html`.
Fetcher memakai halaman utama. Bukti live musim 2026-27 (30
tim): DET 35,47 3PA/laga / 24,60 FTA/laga; ATL 42,88 / 20,38;
BOS 44,81 3PA/laga.

## 6. Wiring CLI

```
python cli.py pantau --ticket out/tickets_<tanggal>.json
    [--analysis out/analysis_<id>.json] [--match DET@ATL_2026-11-22]
    [--date YYYY-MM-DD] [--output out/pantau_<tanggal>.json]
```

- `--ticket` menerima: objek tiket tunggal, pasangan racik
  (`{"insurance", "main"}`), atau `{"tickets": [...]}`.
- Tanggal diambil dari `match_id` kaki (atau `--date`).
  Scoreboard per tanggal → stats per laga berjalan/selesai →
  baseline BBRef → evaluasi + anomali → teks ke stdout, JSON
  lengkap bila `--output` diberi (`format: "live_monitor"`).
- `--analysis` opsional: median pra-laga untuk proyeksi blend +
  anomali laju skor. Tanpa file itu, proyeksi memakai laju live
  saja + anomali laju skor dilewati (dicatat).
- `--match` menerima format artefak maupun slate (seperti
  perbaikan langkah 3).
- **Exit code (keputusan koordinator, §8):** 0 = tidak ada kaki
  TERANCAM/KALAH/DATA_INCOMPLETE dan tidak ada anomali; 1 = ada
  kaki TERANCAM/KALAH/DATA_INCOMPLETE atau anomali (laporan tetap
  tampil); 2 = pantauan tidak bisa berjalan. WASPADA/PUSH tidak
  menaikkan exit code (terlihat jelas di teks; WASPADA masih
  diproyeksikan menang).

## 7. Verifikasi live

Tidak ada laga live saat verifikasi (21:30 WIB = 09:30 EST;
laga 22 Nov tip-off ~07:00 WIB 23 Nov). Yang terverifikasi:

**Replay 1 — laga selesai 21 Nov (data ESPN asli, tiket replay
5 kaki di /tmp):** MIL@PHI KALAH total 261 vs garis 237,5;
LAC@DAL MENANG 210 vs 245,5; POR@NYK MENANG 193 vs 227,5;
NOP@SAS MENANG 205 vs 241,5; BOS@SAC MENANG 193 vs 227,5.
Tiket KALAH, exit 1. Tiga kaki membuktikan pemetaan singkatan
hidup (NYK, NOP, SAS join dengan benar). Anomali 3PT/FT
dievaluasi dan tidak terpicu; `laju_skor_tinggi` dilewati
dengan jujur (tanpa median pra-laga untuk tanggal replay).
`has_data_incomplete: false`, `missing_matches: []`.

**Replay 2 — tiket asli 22 Nov (`out/tickets_2026-11-22.json`,
Utama 4 kaki):** keempat kaki BELUM_MULAI (BOS@GSW, IND@NYK,
DET@ATL, DAL@UTA), exit 0, teks bersih. Putaran pertama
menemukan DAL@UTA DATA_INCOMPLETE karena ESPN memakai `UTAH`
— pemetaan diperbaiki, putaran kedua semua join.

**Cek tangan proyeksi (koordinator, independen):** Q3 tersisa
5:32 (1052 detik), total berjalan 159, median pra-laga 225 →
modul 247,1004; hitungan tangan koordinator 247,1004 — **cocok
persis**.

**Smoke test pekerja C (end-to-end, modul asli):**
`laju_skor_tinggi` terpicu dengan benar pada MIL@PHI (5,44
poin/menit vs ambang 5,25; 3PA 72 < ambang 116,6 dan FTA 55 <
ambang 74,3 sehingga dua jenis lain benar tidak terpicu).

**Yang belum terverifikasi live:** laga yang benar-benar
berjalan (status AMAN/WASPADA/TERANCAM di tengah laga hanya
teruji lewat fixture + tes CLI stub); jam `displayClock` /
`period` saat OT dan jeda antar-kuarter (fixture mensimulasikan
Q3 + OT dari format yang didokumentasikan, belum dari respons
live asli). Satu pengecekan ulang saat ada laga berjalan
dijadwalkan sebagai hutang (§10).

## 8. Keputusan koordinator (integrasi)

- **Pemetaan singkatan ESPN → tricode (6 tim)** di
  `ingest/live_nba.py` (`_ESPN_KE_TRICODE`), diterapkan di
  scoreboard dan summary agar kunci stats ikut tersambung.
  Diverifikasi terhadap ke-30 tim (scoreboard 21–23 Nov).
- **DATA_INCOMPLETE menaikkan exit code ke 1** (fail-closed):
  kaki yang tidak bisa dinilai bukan berarti aman — exit 0
  akan berbohong ("semua aman") padahal satu kaki buta.
  Menggantikan spesifikasi awal tugas (hanya TERANCAM/KALAH/
  anomali). WASPADA/PUSH tetap exit 0.
- **Judul "Pemeriksaan" untuk yang dilewati** (bukan "Anomali")
  + blok yang dilewati tidak dicetak untuk laga belum mulai
  (trivially dilewati — 0 menit; render sudah menulis "belum
  mulai"). Alasannya: teks "Anomali ... dilewati" membingungkan
  user.
- **Koreksi sumber BBRef** (tabel totals tim di halaman utama
  liga, bukan `*_totals.html`) — temuan pekerja C, diterima.
- **Docstring `live_status.py`** diperbaiki: subcommand
  `pantau` (bukan `status`) + exit code diselaraskan dengan
  keputusan di atas.

## 9. Keterbatasan (jujur)

- **Proyeksi pace-based itu kasar:** mengasumsikan laju skor
  berjalan berlanjut; mengabaikan perubahan tempo kuarter
  akhir, foul di akhir laga (yang menaikkan total), cedera /
  pergantian pemain tengah laga, dan menit OT itu sendiri
  (hanya flag risiko). Bukan pengganti simulasi pra-laga —
  jangan dipakai menilai ulang peluang menang tiket.
- **Semua ambang belum dikalibrasi** (status 6,0 / 2,0; anomali
  1,5× / 1,15× / 12 menit; OT 3 poin / 2 menit) — nilai awal
  menunggu validasi atas data PAPER + persetujuan user.
- **Belum ada verifikasi laga live sungguhan** (§7) — perilaku
  tengah laga + OT perlu satu pengecekan ulang.
- **Fallback menit OT di deteksi anomali** mengembalikan None
  untuk period > 4 (kontrak `seconds_remaining` di OT = 0);
  jalur normal memakai `minutes_elapsed` dari proyeksi B,
  jadi ini hanya berpengaruh bila proyeksi tak menyediakannya.
- **Hanya kaki `total_under` yang dipantau** — kaki moneyline
  atau pasar lain dinilai DATA_INCOMPLETE (peracik hanya
  meracik Alt Under, jadi ini konsisten untuk sekarang).
- **Berita non-cedera belum terdeteksi** (hutang lama, masih
  berlaku) — pantauan tidak tahu kabar di luar skor + stats.
- **stats.nba.com cadangan tidak dibangun** (§3); bila ESPN
  gagal, pantauan DATA_INCOMPLETE.
- **Baseline BBRef = rata-rata musim berjalan** — belum
  menyesuaikan lawan, tempo laga ini, atau pemain yang absen.

## 10. Hutang ke langkah 5 (otak bola) + lanjutan

- Pengecekan ulang pantauan saat ada laga NBA yang benar-benar
  berjalan (termasuk OT) — satu putaran `pantau` live.
- Kalibrasi ambang status/anomali atas data PAPER.
- Uji historis model-vs-market dengan garis penutupan DunkAPI
  (menunggu persetujuan signup user, §7 langkah 2) — menentukan
  kapan kepercayaan ke model dipulihkan dari aturan
  condong-ke-market.
- Pertanyaan `min_leg_prob` keras vs lunak (§9 langkah 3);
  pertanyaan H2H musim lalu, penanda periode tangga, ringkasan
  distribusi per skenario (§9 langkah 3).
- Otak bola (langkah 5), belajar sendiri (langkah 6).

## 11. File yang berubah

Baru: `ingest/live_nba.py`, `engine/live_status.py`,
`engine/live_anomaly.py`, `tests/test_live_nba.py`,
`tests/test_live_status.py`, `tests/test_live_anomaly.py`,
`tests/test_cli_pantau.py`,
`tests/fixtures/live_nba_scoreboard_2026-11-21.json`,
`tests/fixtures/live_nba_summary_401910023.json`,
`tests/fixtures/live_nba_scoreboard_live_sim.json`,
`tests/fixtures/live_anomaly_totals.html`, laporan ini.
Diubah: `cli.py`, `ingest/bbref.py`, `config.py`,
`config/playstyle.yaml` (v10), `tests/test_config.py`,
`tests/test_ticket_composer.py`, `DECISIONS.md`. Tidak ada
`.env`, `data/`, `out/`, atau cache yang di-commit.

## 12. Keputusan menunggu objeksi reviewer

- Ambang status kaki (AMAN ≥ 6,0; WASPADA ≥ 2,0) + ambang
  anomali (1,5× / 1,15× / 12 menit) + ambang OT (3 poin /
  2 menit) — nilai awal belum dikalibrasi (§9).
- Exit code: DATA_INCOMPLETE → 1; WASPADA/PUSH → 0 (§8).
- Urutan status tiket (KALAH > TERANCAM > WASPADA >
  DATA_INCOMPLETE > AMAN > BELUM_MULAI); PUSH = seri.
- Proyeksi blend pace-based + bobot `w_live = menit_lalu/48`
  sebagai metode pantauan (bukan simulasi ulang).
- Baseline anomali = rata-rata musim berjalan BBRef (tanpa
  penyesuaian lawan/tempo).
- Pemetaan singkatan ESPN 6 tim (§3).
