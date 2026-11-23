# Laporan Penyempurnaan Mesin — Tambal Semua Kebulungan Sekaligus

Commit: `<diisi setelah commit feat>` (config v16, 0 kredit Odds API).
Laporan per item: LAPORAN-EQUILIBRIUM-SKIP-AWAL.md (items 1, 2, 5),
LAPORAN-EKOR-3P.md (item 4), probes/HASIL-PROBE-NEWS.md (item 3).
Keputusan user yang diimplementasikan: DECISIONS.md ("Titik
equilibrium" 10:31 WIB, "Prinsip skip dari awal" 10:22 WIB,
"Penyempurnaan mesin" 10:41 WIB).

## §1. Ringkasan — apa yang dibangun

Perintah user 10:41 WIB: tambal SEMUA kebolongan sekaligus (gate
tetap ketat; bukan saringan ketat vs bolong, tapi titik equilibrium;
laga tanpa equilibrium di-skip dari awal; semua laga dilaporkan
termasuk yang di-skip beserta alasannya).

| Item | Status | Bukti singkat |
|---|---|---|
| 1. Titik equilibrium per kaki | ✅ SELESAI | `engine/equilibrium.py`; definisi max-ER; DEN tidak ada equilibrium; OKC verif EQ Utama U240,5 @75,5¢ ER 1,0448 |
| 2. Aturan skip dari awal | ✅ SELESAI | `engine/skip_awal.py`; 3 pemicu eksplisit; 6/10 baris slate di-skip (5 pola Denver + 1 OT); semua laga dilaporkan |
| 3. Modul news | ✅ SELESAI | ESPN JSON PAKAI (live: 5 berita DEN@CHI incl. cedera Powell); laporan + recheck terintegrasi |
| 4. Ekor 3P per laga di sim | ✅ SELESAI, HASIL NOL | Regresi n=2.466: slope −0,34, t=−0,17, R²=0 — laju 3PA tidak memengaruhi ekor; slope_aktif 0,0; DEN lama==baru |
| 5. Peluang OT di seleksi | ✅ SELESAI | Ambang 0,028 INITIAL; skip (bukan bantalan); DET di-skip OT (2,89% vs 2,8%) |

**Verifikasi koordinator (dari disk, bukan narasi worker):** full
suite **1.698 tes lulus** (1.537 baseline + 161 baru: 69 equilibrium/
skip/OT + 51 news + 39 ekor 3P incl. 4 tes brain + 2 integrasi
koordinator), ruff + black bersih, config v16, remote HEAD cocok,
tree bersih setelah commit. Koordinator memverifikasi sendiri: JSON ukur equilibrium
(ringkasan 0/10 Asuransi EQ, 10/10 Utama EQ, 6/10 skip), JSON fit
ekor (slope −0,3364, t=−0,17), JSON verifikasi DEN lama-vs-baru
(identik persis), fetcher news live (5 berita nyata DEN@CHI),
dan render bagian Berita di laporan (2 tes integrasi baru).

**Temuan yang harus dilihat user (tidak dilunakkan):** dengan gate
tetap ketat + equilibrium, **Asuransi tetap tidak terbentuk** di slate
uji (0/10 kaki equilibrium Asuransi — sama seperti aturan lama).
Ketegangan banjir+edge dari LAPORAN-ATURAN-KERAS §5 BERTAHAN di
bawah equilibrium. Ini temuan, bukan bug — lihat §7 untuk pilihan
keputusannya. Tidak ada yang dilonggarkan diam-diam.

## §2. Item 1 — Titik equilibrium per kaki

**Definisi yang dipilih: equilibrium = garis tangga dengan expected
return tertinggi** (ER = p_final × (100 / harga venue)) di antara
garis yang lolos SEMUA gate tiket itu (min_leg_prob, banjir, edge,
volume, floor 75¢). Seri ER (<1e-9) → p_final lebih besar → garis
lebih kecil. Alasan: aturan lama (garis termurah yang lolos) lolos
filter tapi belum tentu titik paling manis — garis sedikit lebih
mahal bisa jauh lebih mungkin menang, atau sebaliknya. Target
pengali tiket (x2/x3+) BUKAN kendala per kaki; komposer menumpuk
kaki equilibrium sampai target tercapai. **Tidak ada lantai ER > 1**
(titik manis boleh EV negatif, dilaporkan transparan; viabilitas
dinilai di level tiket). **Tidak ada logika prefer-harga-tinggi** —
harga mengikuti statistik. Alternatif p_final tertinggi ditolak
karena selalu memilih garis termahal.

**p_final per garis** via geser pasar tersirat: δ = garis jangkar −
CDF⁻¹(p_market jangkar Kalshi), p_market(garis) = CDF(garis − δ),
blend w=0,3. Asumsi (terdokumentasi): pasar vs model hanya berbeda
geser lokasi — sama seperti `stress.py`. Validasi: di garis jangkar
OKC verif, p_final hasil geser mereproduksi p_final kaki artefak
**persis (0,908341, selisih 0,0)**. P2 dihormati: Polymarket hanya
sebagai harga, tidak pernah sebagai p_market.

**Equilibrium MENGGANTIKAN mekanisme climb banjir.** Kaki dibangun
ulang dengan p_final/EV/label dihitung ulang DI GARIS BARU — ini
memperbaiki interaksi banjir × edge (aturan keras §5) di mana kaki
naik garis memakai p_final basi. Equilibrium **boleh melompati garis
tahan-banjir yang thin** ke garis tebal di atasnya — keputusan lama
"gate tidak melompat" (aturan keras §7.1) DIGANTIKAN, karena hanya
masuk akal di dalam mekanisme climb. `leg_id` tidak berubah.

**Hasil ukur slate nyata** (`scripts/ukur_equilibrium.py` →
`out/ukur_equilibrium.json`, 10 baris yang sama seperti
`ukur_gate_banjir`):

| Laga | Artefak | EQ Asuransi | EQ Utama | Skip |
|---|---|---|---|---|
| DET@ATL | live | — | U237,5 @76,5¢ ER 1,0152 | OT (2,89% ≥ 2,8%) |
| OKC@MIA | live | — | U244,5 @77¢ ER 1,0004 | pola Denver |
| ORL@WAS | live | — | U241,5 @88¢ ER 0,9889 | pola Denver |
| DEN@CHI | live | — | U250,5 @76,5¢ ER 1,0033 | pola Denver |
| DAL@UTA | live | — | U238,5 @77,5¢ ER 1,0367 | tidak |
| IND@NYK | live | — | U226,5 @75¢ ER 1,0258 | pola Denver |
| BOS@GSW | live | — | U223,5 @76,5¢ ER 1,0468 | tidak |
| OKC@MIA | verif | — | U240,5 @75,5¢ ER 1,0448 | tidak |
| DEN@CHI | verif | — | U250,5 @78,5¢ ER 1,0127 | pola Denver |
| BOS@GSW | verif | — | U223,5 @77,5¢ ER 1,0242 | tidak |

EQ Asuransi **0/10** (gate mengikat: volume 7, edge 2, banjir 1);
EQ Utama **10/10**. Catatan: 9 dari 10 EQ Utama thin (peringatan
untuk Utama, bukan gate — hanya OKC verif yang tidak thin).

**Kasus uji wajib:**
- **DEN@CHI — tidak ada equilibrium Asuransi** (volume; satu-satunya
  garis tahan-banjir U266,5 @94¢ thin di artefak live, U264,5 @94¢
  thin di verif). Presisi penting: equilibrium Utama ADA (U250,5
  @76,5¢, ER 1,0033) — jadi skip Denver datang dari pola_denver
  (§3), BUKAN dari tidak-adanya-equilibrium.
- **OKC@MIA verif — equilibrium ada, tidak di-skip.** EQ Utama
  **U240,5 @75,5¢, p_final 0,789, ER 1,0448**, tidak thin — dipilih
  karena ER tertinggi di antara 10 garis yang lolos (vs kaki artefak
  U244,5 @82,5¢, ER 1,0207): lebih murah DAN bernilai lebih baik.
  EQ Asuransi tidak ada karena edge (+1,3% < 3,5%).

Komposisi tiket berubah dan lebih jujur dibanding aturan lama: slate
live menukar DET (skip OT) dengan BOS (equilibrium menyelamatkan
kaki artefak U219,5 di bawah lantai ke U223,5 @76,5¢); slate verif
memakai garis equilibrium OKC yang lebih bernilai (pengali maks
x1,15 → x1,25). **Tidak ada tiket terbentuk** — sama seperti aturan
lama (lihat §7).

## §3. Item 2 — Aturan skip dari awal

Tiga pemicu, definisi eksplisit di config (`skip_awal:`) + kode
(`engine/skip_awal.py`):

- **(a) `tidak_ada_equilibrium`** — tidak ada equilibrium di KEDUA
  tiket (satu tiket punya → tidak skip via (a)).
- **(b) `pola_denver`** — konjungsi 4 syarat: flag setan di garis
  acuan + tidak ada garis tidak-tipis yang tahan banjir + garis
  acuan thin + edge kecil (< `skip_awal.pola_denver.edge_kecil_pct`
  = **3,5 INITIAL**, cermin D12). Catatan: syarat (1) hampir selalu
  benar pada tangga rapat — daya beda datang dari syarat (2)–(4);
  bisa dihapus/dipindah bila reviewer menilai tidak menambah apa-apa.
- **(c) `ot_tinggi`** — ot_prob ≥ ambang (lihat §6).

Tanpa data → "tidak dievaluasi", bukan skip. Skip + alasan tampil di
komposer (`skipped_matches` + ringkasan) dan laporan (spanduk
Ringkasan + bagian baru "Titik equilibrium dan skip dari awal");
**semua laga tetap dilaporkan**, termasuk yang di-skip — sesuai
perintah user 10:41 WIB. Flag `equilibrium.enabled` /
`skip_awal.enabled` untuk A/B + rollback; dimatikan = perilaku lama
persis (dibuktikan tes).

**Kasus uji wajib:** DEN@CHI di-skip dengan alasan pola Denver di
kedua artefak (keempat syarat benar); DAL@UTA, BOS@GSW, dan OKC@MIA
verif TIDAK di-skip. Margin tipis yang perlu dicatat: DAL selamat
dari pola hanya karena edge acuan +4,66% vs 3,5%.

## §4. Item 3 — Modul news

**Probe sumber gratis** (6 request, 0 kredit; ringkasan lengkap di
`probes/HASIL-PROBE-NEWS.md`):

| Sumber | Putusan | Alasan |
|---|---|---|
| ESPN JSON (`site.api.espn.com/.../nba/news`) | **PAKAI** | JSON terstruktur, kategori tim per artikel, jam terbit, 50 artikel ≈ 2 hari terakhir |
| Google News RSS | **CADANGAN** | Berfungsi (100 item/kueri, 30 penerbit), tapi agregator + 2 request per laga; tidak dipakai sekarang |
| NBA resmi (nba.com) | **JANGAN** | Tidak ada API JSON/RSS berita; hanya HTML Next.js — mengupas HTML rapuh, di luar pola repo |

**Fetcher** `ingest/news_nba.py`: pola ESPN (`FetchResult`, tier 2,
gagal → `ok=False`); bedakan "tidak ada berita" (`data=[]`) dari
"gagal ambil"; relevansi via kategori tim + fallback nama lengkap
tim di judul; umur maks + cap dari config. Endpoint per-tim yang
diduga mengembalikan body kosong → filter per laga di sisi klien
dari feed liga.

**Bukti live (verifikasi koordinator, bukan hanya stub):**
`fetch_news_nba('CHI', 'DEN', '2026-11-22')` → ok, 5 item, termasuk
*"Jokic's triple-double, Murray's 45 points lead Nuggets to 151-145
overtime win over Bulls"* (03:15 UTC) dan *"Bulls G Norman Powell
sidelined by mild hamstring injury"* (23:43 UTC) — persis jenis
berita yang relevan untuk pasang.

**Integrasi:** analyze melampirkan blok `news` per laga (status
`ok`/`kosong`/`gagal`; gagal tidak mengubah status artefak seperti
Kalshi); laporan memuat bagian "Berita" (sesudah Cedera, sebelum
Market — disisipkan koordinator saat integrasi, 2 tes integrasi
baru); recheck menandai berita mendadak (terbit setelah analisis
awal + relevan + belum ada di blok awal) → **PERHATIAN** di semua
kaki laga itu (tetap GO), tidak memicu resim, tidak mengubah
GO→NO-GO. **News konteks, bukan angka** — tidak pernah masuk sim.

**Batasan jujur:** judul bahasa Inggris (tidak diterjemahkan);
artikel Media hanya sorotan video (dilabeli); relevansi via kategori
tim bisa menarik berita liga yang menyebut tim; feed hanya ~2 hari
ke belakang pada limit 50; berita lebih tua dari 72 jam dibuang
(NILAI AWAL di config); recheck hanya menandai berita terbit
setelah analisis.

## §5. Item 4 — Ekor 3 poin per laga: HASIL NOL

**Metode:** regresi varians — `sigma_total_laga² = sigma_global² +
slope × (3PA_gabung − pusat)`, dijepit [0,5×, 2,0×] sigma global.
Fit dari **n=2.466 laga** (2024-25 s.d. 2026-27, residual rolling
point-in-time + laju 3PA point-in-time, tanpa look-ahead; 235 laga
awal musim dilewati karena belum 5 laga sebelumnya). Script:
`scripts/fit_ekor_3p.py` → `out/fit_ekor_3p.json`.

**Hasil: slope −0,3364, SE 1,9697, t=−0,17, CI95 [−4,20, +3,53],
R²=0,0000.** Semua uji ketahanan juga nol: varians margin (t=−0,07),
|resid| (t=0,16), 3P% (t=−0,24), sd 3PM per tim (t=0,76), share 3PA
(t=−0,64), varians binomial tersirat (t=−0,22). Kuartil: sd
resid_total Q1 19,12 / Q2 18,69 / Q3 18,73 / Q4 19,01 — datar; ekor
atas Q4 justru lebih tipis (p95 31,2 vs 36,4 di Q1). Slope binomial
teoritis +2,0689 berada DALAM CI fit — data tidak bisa membedakan
"tidak ada efek" dari "efek sebesar teori", tapi estimasi titik ≈ 0.
Slope per musim tidak stabil tandanya. **Kesimpulan: laju 3PA tidak
memengaruhi ekor total pada n=2.466** — ini "efek tidak terukur",
bukan "efek tidak ada".

**Parameter baru** (`ekor_3p:`): `slope_aktif` **0,0** (FIT → tidak
signifikan → 0,0, preseden altitude); `tiga_pa_gabungan_rata_liga`
**74,54** (FIT); jepit sigma 0,5×/2,0× (PILIHAN DESAIN, menunggu
keberatan). Rencana kalibrasi: ulang tiap akhir musim; bila |t| ≥ 2,0
ajukan slope fit ke user (D12); bila tetap nol pada n ≥ 5.000, tutup
hipotesis ini.

**Verifikasi wajib DEN@CHI** (100.000 iterasi, seed 20261122, inputs
pra-laga asli): **lama == baru_produksi persis** — sigma 18,99,
median 233,0, std 19,40, p95 265,0, P(U252,5) 0,8472, P(≥296) 0,0013.
**Model baru TIDAK melihat DEN lebih berisiko.** Penyebabnya jelas
dari data: DEN@CHI pra-laga 3PA gabungan **71,59 (persentil ke-29)**
— DEN tim 3PA rendah. Banjirnya adalah lonjakan percobaan DALAM
laga (90 vs ~72) + akurasi (46,7% vs ~33%), bukan sesuatu yang bisa
diprediksi laju musim berjalan. Kontrafaktual binomial (+2,07)
malah membuat DEN sedikit LEBIH AMAN (sigma 18,83). OKC@MIA juga
lama==baru persis — laga normal tidak terganggu. Baris sintetis 3PA
gabungan 90 membuktikan mesin penskalaan bekerja ke arah yang
dimaksud (sigma 19,81, P 0,8371).

**Artinya:** hipotesis "laju 3PA memprediksi ekor" DITUTUP dengan
bukti. Pertahanan terhadap banjir tetap gate banjir/edge/volume +
seleksi (skip dari awal) — bukan model 3PA. Mesin penskalaan sigma
tetap dibangun (dan `sumber_sigma` tercatat per sim:
`per_laga`/`global_slope_nol`/`global_tanpa_data_3pa`/
`global_tanpa_config`) sehingga bila fit masa depan menemukan slope
signifikan, yang berubah hanya angka config.

Temuan samping (TIDAK diimplementasikan, di luar lingkup): efek MEAN
signifikan `resid_total ~ 3PA` b=−0,2087, t=−2,91 — soal kalibrasi
mean, bukan ekor; dicatat untuk pekerjaan lanjutan.

## §6. Item 5 — Peluang OT dipakai di seleksi

Sim sudah menghitung `ot_probability` (sekarang dipakai seleksi,
bukan hanya Q&A). **Keputusan: SKIP, bukan bantalan lebih besar**
(OT sudah dimodelkan sim; risiko sisa adalah model meremehkan OT).
Ambang `ot_seleksi.skip_ot_prob` = **0,028 INITIAL** (≈ plafon
teoretis peluang seri laga imbang 0,0277, dalam SKALA SIM — bukan
laju OT historis 5–6%, karena peluang OT sim adalah peluang seri
tepat di akhir 48 menit). Rencana kalibrasi ada di komentar config.

**Hasil:** DET@ATL di-skip OT (ot_prob 2,89% vs ambang 2,8% — margin
hanya 0,09 poin, perlu dicatat). **Batasan jujur: aturan OT tidak
menangkap Denver** (ot_prob DEN 2,36%/2,13%, di bawah ambang) —
Denver ditangkap pola Denver (§3), bukan OT. Laga yang sebenarnya
masuk OT tidak selalu punya ot_prob sim tinggi; ini keterbatasan
model, bukan alasan melonggarkan ambang tanpa data.

## §7. Ketegangan: gate ketat + equilibrium — Asuransi tetap tidak terbentuk

Dengan parameter saat ini (banjir p90 + edge 3,5% + thin + floor
75¢), **equilibrium Asuransi 0/10** dan **tidak ada tiket Asuransi
terbentuk** di slate uji — sama seperti aturan lama. Equilibrium
memperbaiki komposisi (p_final dihitung ulang di garis baru; garis
lebih bernilai dipilih; BOS diselamatkan dari bawah lantai) tapi
TIDAK mengubah hasil akhir Asuransi: gate mengikatnya adalah volume
(7), edge (2), banjir (1). Mekanisme struktural §5 aturan keras
bertahan: kaki yang tahan banjir harganya tinggi, dan di harga
tinggi edge mengecil secara mekanis.

Ini untuk keputusan user — koordinator TIDAK melonggarkan apa pun
diam-diam. Pilihan yang tersedia (sama seperti §5 aturan keras,
masih berlaku): terima bahwa Asuransi jarang terbentuk; turunkan
ambang edge; longgarkan aturan thin untuk garis tahan; atau
kalibrasi ulang banjir ke data bersih (§6 aturan keras — nilai
config 13,54/17,54 tercemar; data bersih 8,50/12,52; konterfaktual
block rate tetap 1/10, jadi bukan obatnya). Opsi "hitung ulang
p_final di garis baru" SUDAH diterapkan lewat equilibrium (§2) —
dan terbukti tidak cukup sendirian.

**Untuk besok pagi (slate 10 laga):** dengan 10 laga, peluang ada
kaki Asuransi yang lolos lebih besar daripada slate uji 7 laga —
tapi bila tetap tidak terbentuk, itu mesin yang bekerja sesuai
perintah (tetap ketat + jangan isi tiket demi pengali), bukan mesin
yang rusak.

## §8. Keputusan desain yang menunggu keberatan

1. Max-ER sebagai definisi equilibrium (alternatif p_final tertinggi
   ditolak: selalu memilih garis termahal).
2. Tidak ada lantai ER > 1.
3. Skip (a) butuh tidak ada equilibrium di kedua tiket.
4. OT: skip, bukan bantalan; ambang 0,028 dalam skala sim (INITIAL).
5. Equilibrium boleh melompati garis tahan-banjir yang thin
   (menggantikan "gate tidak melompat").
6. Ambang edge pola Denver 3,5% INITIAL (cermin D12).
7. Syarat (1) pola Denver (flag setan di acuan) hampir selalu benar
   — daya beda dari syarat (2)–(4).
8. Slope ekor 3P aktif 0,0 (bukan slope fit −0,34) — preseden
   altitude; jepit sigma 0,5×/2,0×; ambang signifikansi |t| ≥ 2,0;
   `MIN_LAGA_UNTUK_LAJU = 5`; data `tembakan_3p` mentah tanpa
   shrinkage; section `ekor_3p` opsional di kode.
9. Efek mean 3PA (t=−2,91) tidak diimplementasikan.
10. News: feed 72 jam + limit 50 (NILAI AWAL); recheck news hanya
    PERHATIAN, tidak mengubah putusan.
11. Integrasi koordinator: section `news:` dan `ekor_3p:` TIDAK
    masuk REQUIRED_PLAYSTYLE_SECTIONS (fail-closed per pemakaian);
    equilibrium/skip_awal/ot_seleksi wajib ada.

## §9. Batasan jujur

- Equilibrium: recheck menilai garis LAMA (pola yang sama dengan
  climb lama — bukan regresi); CDF dijepit di ujung tanpa
  ekstrapolasi; pilihan jangkar memengaruhi ranking ER (contoh ORL);
  asumsi geser-lokasi baru divalidasi di titik jangkar.
- Skip: ambang OT dan edge pola Denver INITIAL (belum terkalibrasi);
  margin tipis DET (0,09 poin) dan DAL (edge +4,66% vs 3,5%)
  menunjukkan ambang-ambang ini sensitif — kalibrasi PAPER akan
  mengujinya.
- Ekor 3P: CI95 masih mencakup slope teoritis; laju 3PA tidak bisa
  memprediksi banjir dalam laga; laju awal musim berisik tanpa
  shrinkage; residual fit tidak mengandung cedera; hanya sigma total
  yang diskala, bukan bentuk ekor (t_nu).
- News: lihat §4. OT: lihat §6.
- 9 dari 10 kaki equilibrium Utama thin — peringatan, bukan gate;
  bila user ingin Utama juga ketat soal volume, itu keputusan baru.

## §10. Siap besok pagi (slate Selasa 24 Nov, 10 laga)

Alur: analyze (dengan news + tembakan_3p + ot_probability) → racik
(equilibrium + skip dari awal + gate banjir/edge/volume) → `cli.py
audit` SEBELUM pasang → laporan (bagian Berita + "Titik equilibrium
dan skip dari awal" + "Skenario panas") → `pantau --analysis …`
(blend). Semua laga dilaporkan, termasuk yang di-skip beserta
alasannya. Bila Asuransi tidak terbentuk, laporan menunjukkan
alasannya per laga (gate mana yang mengikat) — bukan diam.

## §11. File yang berubah

Baru: `engine/equilibrium.py`, `engine/skip_awal.py`,
`ingest/news_nba.py`, `report/news_section.py`,
`scripts/ukur_equilibrium.py`, `scripts/fit_ekor_3p.py`,
`scripts/verifikasi_ekor_3p.py`, `probes/probe_news_{espn,nba,
google}.py`, `probes/HASIL-PROBE-NEWS.md`,
`probes/out/probe_news_{espn,nba,google}.json`,
`tests/test_equilibrium.py`, `tests/test_skip_awal.py`,
`tests/test_news_nba.py`, `tests/test_news_section.py`,
`tests/test_ekor_3p.py`, `tests/fixtures/espn_news_nba_2026-11-23.json`,
`LAPORAN-EQUILIBRIUM-SKIP-AWAL.md`, `LAPORAN-EKOR-3P.md`,
`LAPORAN-PENYEMPURNAAN-MESIN.md` (file ini).
Diubah: `config/playstyle.yaml` (v16; sections `equilibrium:`,
`skip_awal:`, `ot_seleksi:`, `news:`, `ekor_3p:`), `config.py`
(REQUIRED + equilibrium/skip_awal/ot_seleksi),
`engine/ticket_composer.py` (equilibrium menggantikan climb banjir),
`engine/nba_analysis.py` (blok news), `engine/nba_sim.py`
(ENGINE_VERSION 1.2.0; sigma per laga), `engine/recheck.py`
(peringatan berita mendadak), `ingest/nba_brain.py` (blok
`tembakan_3p`), `ingest/bbref.py` (kolom `fg3`),
`report/nba_report.py` (bagian Berita + equilibrium/skip),
`schemas/nba_analysis.schema.json` + `schemas/recheck.schema.json`
(aditif: properti `news` opsional + kind `news`),
`tests/test_ticket_composer.py` (3 tes diperbarui dengan alasan
terdokumentasi), `tests/test_report_nba.py` (+ tes Berita),
`tests/test_nba_analysis.py`, `tests/test_recheck.py`,
`tests/test_config.py`, `tests/test_ingest_nba_brain.py`,
`DECISIONS.md` (catatan implementasi + keputusan user 10:22/10:31/
10:41 WIB yang belum ter-commit).
Gitignored (runtime state): `out/ukur_equilibrium.json`,
`out/fit_ekor_3p.json`, `out/verifikasi_ekor_3p.json`,
`data/nba_history/fg3a_*.json`.
