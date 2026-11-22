# Laporan Analisis Mendalam — Cara Gemini Meracik vs Mesin Kita

**Tanggal:** 23 November 2026 · **Sifat:** studi desain SAJA — bukan implementasi.
**Tidak ada kode/config yang diubah dalam pekerjaan ini.** 0 kredit Odds API.

## Pendahuluan

User selama ini dianalisis oleh Gemini (langganan berbayar). Analisisnya bagus,
tapi tidak efisien: user harus menyuruh satu per satu, langganan bisa habis,
dan bila sesi chat hilang, user harus melatih ulang. Mesin parlay ini dibangun
untuk **menggantikan peran Gemini**: sekali minta langsung analisis semua, kapan
saja, tanpa langganan, tanpa latih ulang.

Pada 23 Nov 2026 06:12 WIB, user mengirim transkrip lengkap percakapannya
dengan Gemini pagi itu (05:22–~06:00 WIB): 6 laga NBA + racikan 2 tiket +
debat + audit tiket riil, plus 2 screenshot tiket jup.ag. Laporan ini
menganalisis **cara kerja** Gemini dari transkrip itu dan membandingkannya
dengan mesin kita.

**Sumber:** transkrip lengkap di chat Muse (side chat "Mesin Agent Baru",
2026-11-23 06:12 WIB) + `REFERENSI-GEMINI-2026-11-23.md` (ringkasan
terstruktur + angka kunci) + kode mesin kita (branch main, commit `32cfd41`,
config v13, 1.395 tes).

**Metode:** tiga pekerja paralel (inventaris mesin, kesenjangan + usulan,
pemeriksa silang) + analisis transkrip langsung oleh koordinator. Semua angka
Gemini yang dikutip dihitung ulang dengan tangan dari transkrip (§4).
**Klaim Gemini TIDAK diverifikasi ke sumber luar** — yang dinilai adalah cara
kerjanya dan konsistensi internal angkanya, bukan kebenaran angkanya terhadap
data nyata.

**Kesimpulan satu kalimat:** Gemini adalah **spesifikasi UX yang bagus dan
mesin hitung yang tidak boleh dipercaya** — salin struktur kerjanya (bedah,
edge, audit, hedge, kesadaran waktu), bukan mesin hitungnya (angka LLM tanpa
asal-usul, basis berubah, tanpa fail-closed).

---

## 1. Alur kerja Gemini langkah demi langkah

Dari transkrip lengkap, Gemini bekerja dalam 10 langkah berurutan. Perhatikan:
alur ini digerakkan percakapan — user yang menentukan kecepatan, satu laga
demi satu laga — sementara mesin kita harus melakukan semuanya sekaligus,
otomatis, sebelum uang keluar.

### Langkah 1 — Peta slate (05:22, 38 menit sebelum tip-off pertama)

User: belum meracik, minta update + racik sekarang, waktu sudah mepet.
Gemini menjawab dengan **peta 6 laga**: jam, sisa waktu, konteks jadwal
(back-to-back, pertahanan #1), dan prioritas Under per laga. Ditambah strategi
cepat: jangan paksa laga 06:00 bila dalam 15 menit belum terverifikasi (skip
saja); kunci poros di laga B2B & defensif; pola 2 lapis (Utama +12 s/d +15,
Asuransi +18 s/d +22 di atas main line). Ia **belum mengunci angka** sebelum
melihat data resmi — dan meminta user mengirim screenshot garis + harga.

### Langkah 2 — Bedah laga #1 dengan berita breaking (Thunder @ Heat)

User: verifikasi realtime, pasang Under saja, mulai dari Thunder.
Gemini membuka dengan **breaking news**: SGA dan Giannis DUA-DUANYA resmi OUT
(Giannis 19 menit sebelum analisis). Lalu bedah terstruktur: laporan cedera
final per tim (8 pemain OKC OUT, dampak PPG), pergerakan bursa (total 231,5 →
228,5; spread −2,5 → −7,5), statistik resmi + 5 laga terakhir + sisi bahaya
(Heat masih cepat, penembak 3P tajam), lalu **simulasi 100.000x 4 skenario**
(normal, konservatif 5-out, banjir FT, banjir 3P) dengan tabel P(Under) per
garis, vonis **HIJAU** + target garis Utama (U 234,5–236,5) dan Asuransi
(U 239,5–242,5). Ditutup radar singkat 5 laga berikutnya.

### Langkah 3 — Bedah laga #2–#6, satu per satu atas permintaan user

User meminta tiap laga berikutnya dengan satu pesan singkat ("lanjut bedah ke
pertandingan selanjutnya …"). Setiap bedah memakai **struktur yang sama**:
(1) cedera & news real-time, (2) statistik musim + 5 laga terakhir + H2H,
(3) simulasi 100.000x multi-skenario (4–6 skenario; IND@NYK memakai cabang
cedera KAT & Siakam main/absen), (4) tabel P(Under) per garis per skenario,
(5) vonis + target garis + "racun" (cara spesifik Under bisa jebol).
Setelah laga #6, Gemini memberi **tabel ringkasan peringkat 6 laga** (vonis,
garis pasar, proyeksi, target Utama/Asuransi).

### Langkah 4 — Racikan 2 tiket

User meminta racikan (Asuransi x2–2,5; Utama x4–x5 bila memungkinkan, x3
sudah bagus). Gemini **memilih 4 kaki edge terbesar** (OKC, DAL, DEN, BOS —
proyeksi 8,5–13,2 poin di bawah garis pasar) dan **membuang 2 laga** (ORL &
IND — edge < 2 poin + KAT/Siakam Questionable). Asuransi: 4 kaki ~82¢, ~2,24x.
Utama: opsi A ~3,5x (rekomendasi) / opsi B ~4,5x (agresif). Plus 2 opsi
alternatif (buang DEN; ganti OKC dengan IND bila lewat 06:00) dan **tabel
skenario hasil modal** ($27 → $15 Utama + $12 Asuransi: keduanya tembus /
hanya Asuransi / keduanya gugur, dengan dolar + peluang tiap skenario).

### Langkah 5 — Debat 1: kenapa tidak tumpuk 6 laga untuk Asuransi?

User mengusulkan menumpuk semua 6 laga di ~82¢. Gemini menjawab dengan
**angka, bukan pendapat**: tabel adu 4 kaki vs 6 kaki (peluang 71,7% vs
60,5% di pengali sama; peluang OT 14,4% → 20,7%; "2 kaki tanpa edge = beban
mati"), lalu solusi jalan tengah (tetap 4 kaki; Utama naik ke ~75¢ agar tidak
agresif). User menerima arahnya.

### Langkah 6 — Debat 2: Utama 75¢ terlalu agresif (trauma Thunder 71¢)

User menolak kaki 75¢ — ia trauma kasus Thunder (beli 71¢ lalu kalah) — dan
meminta tidak ada kaki di bawah 78¢, dengan analisis ulang. Gemini
**menggeser racikan, bukan membantah user**: Utama jadi 5 kaki 78–82¢
(menambah ORL U 233,5 sebagai "tuas pengali"), IND tetap dibuang, Asuransi
tetap 4 kaki ~82¢. Alasan yang dicatat: "hedge gratis" (ORL hanya di Utama,
tidak di Asuransi) + efek tiap kaki terhadap peluang & EV.

### Langkah 7 — Audit tiket Asuransi riil (garis + harga dari layar user)

User menempel 4 garis + harga Asuransi dari bursanya. Gemini mengaudit:
75,8% normal (EV +69,7%), per kaki 92,1–95,7%, bantalan +23,5–+30,2 poin vs
model, titik impas 44,6% vs peluang riil 75,8% — vonis "HIJAU SOLID", "kunci
sekarang". Ini audit **setelah** user memilih garis, sebelum ia menekan beli.

### Langkah 8 — Racikan Utama final + opsi

User meminta Utama disusun. Gemini: 5 kaki ~3,28x (semua 77–82¢, tanpa kaki
di bawah 77¢), plus opsi B (~3,85x) dan opsi C (~4,30x, 6 kaki termasuk IND —
dengan catatan jujur "skenario konservatif jadi minus −11,5%"). Aturan klik
cepat: pastikan 77–80¢, jangan di bawah 75¢.

### Langkah 9 — Audit tiket Utama riil (user menambah IND sendiri)

User memasang Utama 6 kaki — ia **menambah IND@NYK U 230,5 @85¢ sendiri,
buru-buru 3 menit sebelum tip-off**, melawan rekomendasi. Gemini mengaudit:
49,5% normal (EV +84,2%), peringkat kekuatan 6 kaki, titik paling rapuh
IND (21,1% skenario kalah disebabkan kaki ini sendiri) lalu ORL (16,5%),
penjelasan kenapa IND tidak direkomendasikan ("85¢ = ilusi aman": garis pasar
213,5 diperas, bantalan riil hanya +16,2 poin; KAT & Siakam main → peluang
70,7%), dan temuan kunci: **tanpa IND, pengali turun ke 3,16x tapi peluang
naik ke 60,2% dan EV naik ke +90,3%**. Posisi portofolio: peluang minimal
satu tiket hijau 76,6%.

### Langkah 10 — Menenangkan user yang panik

User panik: Asuransi 80–83¢ "kelihatan tipis", kenapa tidak tumpuk 6 laga di
84¢ saja. Gemini menenangkan dengan **mengoreksi hitungan user**: 6 kaki @84¢
= 2,85x (bukan 2x); tabel adu 4 kaki vs 6 kaki di berbagai harga (4 kaki
76,6% vs 6 kaki @87,5¢ 66,4% vs 6 kaki @89¢ 70,5%); bantalan riil +23,5–+30,2
poin; fungsi hedge (Asuransi tidak memuat kaki berisiko ORL/IND). Ditutup
tawaran pantau pace halftime.

**Pola yang muncul:** Gemini adalah analis percakapan yang (a) selalu mulai
dari peta + prioritas, (b) membedah dengan struktur tetap per laga, (c) menilai
risiko lewat skenario stres, (d) meracik dari edge, (e) menjawab keberatan
dengan angka yang dihitung ulang, (f) mengaudit tiket riil, (g) menenangkan
dengan aritmetika. Mesin kita harus melakukan (a)–(g) dalam satu perintah,
tanpa percakapan — dan auditnya harus datang **sebelum** user memasang, bukan
sesudah.

---

## 2. Prinsip pengambilan keputusan Gemini

Masing-masing dengan bukti dari transkrip.

### P1. Pilih kaki dari EDGE, bukan dari harga atau peluang saja

Edge = selisih proyeksi model vs garis pasar. Empat kaki yang dipakai punya
edge 8,5–13,2 poin; ORL (edge 1,8) & IND (edge −0,8 — proyeksi DI ATAS garis
pasar) dibuang. Bukti: "Seluruh 6 laga dihitung ulang terhadap garis pasar,
racikan paling kuat pagi ini adalah 4 Kaki Edge Terbesar… sengaja membuang
Magic @ Wizards serta Pacers @ Knicks. Garis pasar mereka sudah terlalu
diperas (219,5 dan 213,5) sehingga selisih keunggulan model kita tipis
(< 2 poin)."

### P2. Vonis lahir dari skenario stres, bukan dari satu angka peluang

Setiap laga diuji 4–6 skenario: normal, konservatif/sejajar pasar, banjir FT
(~57–66 FTA), banjir 3P (+6% akurasi, ~26–30 3PM), cabang cedera, efek
kandang. Vonis HIJAU/KUNING ditentukan seberapa tahan Under di skenario
buruk. Bukti: DEN@CHI "KUNING — Pakai Hanya di Garis Super Tinggi" karena
skenario banjir 3P menjatuhkan P(U 250,5) ke 72,3%; BOS@GSW "HIJAU" karena
skenario normal 92,2% dan banjir 3P masih 74,0%.

### P3. Harga ≠ peluang — waspadai "ilusi aman"

Harga tinggi (85¢) tidak berarti aman bila garis pasar sudah diperas.
Bukti: "Harga 85¢ di bursa sering memberi ilusi aman… 85¢ cuma cerminan jarak
+17 poin dari garis utama pasar (213,5) — bukan jaminan peluang aslinya 85%…
kamu bayar 85¢ untuk peluang 82,1% (overpay −2,9%)." Yang menentukan adalah
bantalan vs PROYEKSI MODEL (+16,2 poin untuk IND — paling sempit), bukan
jarak vs garis pasar.

### P4. Sedikit kaki yang bagus mengalahkan banyak kaki yang biasa-biasa saja

Menambah kaki membuka pintu kegagalan baru. Bukti: 4 kaki @82¢ = 2,24x,
peluang 71,7%; 6 kaki @87,5¢ = 2,21x, peluang 60,5% (−11,2 poin); peluang
minimal satu laga OT naik 14,4% → 20,7%. "2 kaki tanpa edge (Magic & Knicks)
jadi beban mati."

### P5. Hedge lewat struktur: kaki berisiko hanya di Utama, tidak di Asuransi

ORL sengaja hanya masuk Utama ("hedge gratis: kalau laga kandang Wizards
mendadak meledak, Tiket Asuransi 4 kakimu tetap selamat"). Bukti dari jawaban
panik: "Tiket Utama 6 kakimu sudah membawa risiko Magic @ Wizards dan Pacers
@ Knicks. Kalau Asuransimu ikut menumpuk 6 laga yang sama, satu saja dari
Magic atau Knicks meledak, kedua tiketmu hangus bersamaan."

### P6. Hormati batasan user (termasuk trauma) — geser racikan, jangan berdebat

User menolak kaki di bawah 78¢ karena trauma Thunder 71¢. Gemini tidak
membantah ("trauma bantalan tipis 71¢–75¢ itu valid banget, bro") — ia
menghitung ulang dan menggeser racikan ke 5 kaki 78–82¢. Prinsipnya:
batasan user adalah input, bukan keberatan yang harus dipatahkan.

### P7. Setiap klaim membawa angka; setiap vonis membawa "racun"

Tidak ada rekomendasi tanpa angka pendukung. Dan setiap laga mendapat
"racun" — cara spesifik Under bisa jebol: OKC ("Heat 5-out tanpa Caruso"),
DEN ("Claxton absen → Jokić membantai paint + tempo Bulls #2 + H2H liar
248–257"), ORL ("3 laga kandang Wizards meledak 256–284 + Bane/Wagner 19
tripoin"), IND ("KAT & Siakam main + Pacers tandang liar 237,1"), BOS
("rebound tembakan 3P Boston volume #1").

### P8. Sadar waktu — rekomendasi kedaluwarsa di tip-off

Dari pesan pertama: "laga Thunder @ Heat tinggal 38 menit… jangan paksa
kalau dalam 15 menit belum sempat verifikasi." Urgensi naik seiring waktu
("tinggal 23 menit", "tinggal 19 menit", "tinggal 15 menit", "8 menit lagi").
Laga yang sudah lewat diganti (opsi ganti OKC dengan IND bila lewat 06:00).
Keputusan terburuk pagi itu (menambah IND 3 menit sebelum tip-off) terjadi
justru karena tidak ada yang berkata "sudah mepet, lewatkan".

### P9. Koreksi hitungan user dengan lembut, lalu tenangkan dengan aritmetika

Saat user panik ("Asuransi tipis"), Gemini tidak berkata "tenang saja" —
ia menghitung: 6 kaki @84¢ = 2,85x bukan 2x; bantalan +23,5–+30,2 poin;
peluang per kaki 92,4–95,8%; lalu menyimpulkan "kepalamu nggak salah
langkah tadi."

### P10. Vonis percaya diri dengan bahasa yang membujuk

HIJAU / KUNING / "beban mati" / "ilusi aman" / "hedge gratis" / "benteng
super aman" — bahasa yang menutup ruang keraguan. Ini efektif untuk
mengambil keputusan cepat di bawah tekanan waktu, tapi menyembunyikan
ketidakpastian (§4 menunjukkan inputnya sendiri goyah: garis OKC yang
berubah, pemain Questionable, angka yang bergeser antar jawaban).

---
## 3. Perbandingan dengan mesin kita (analisis kesenjangan)

Legenda: ✅ SUDAH PUNYA · ◐ SEBAGIAN · ❌ TIDAK ADA · 🔀 PUNYA TAPI BERBEDA CARA

| # | Kemampuan Gemini | Status | Penilaian (dengan rujukan kode) |
|---|---|---|---|
| (a) | Peta slate 6 laga + prioritas + kesadaran waktu/sisa waktu | ◐ SEBAGIAN | Slate dibangun (`ingest/slate.py`), jam tip-off disimpan di artefak (`engine/nba_analysis.py`), jendela recheck 30–60 menit + peringatan usia recheck (`engine/ticket_composer.py::_peringatan_jendela`). Yang TIDAK ADA: peta slate berprioritas, skip laga mepet tip-off, rekomendasi yang kedaluwarsa bila tip-off lewat. `compose_tickets()` sama sekali tidak membaca jam tip-off (terverifikasi: grep `start_time\|tip_off` di `ticket_composer.py` kosong). |
| (b) | Bedah per laga terstruktur (cedera/news, statistik, 5 laga terakhir, H2H) | ◐ SEBAGIAN | Hampir lengkap: cedera 2 sumber (`ingest/nba_brain.py::_merge_injuries`), statistik musim+last10, form5, H2H musim ini, dampak absen BPM×menit + shrinkage, laporan per laga (`report/nba_report.py`). Yang HILANG: **berita breaking non-cedera** — Gemini memakai "SGA OUT pertama musim ini" dan "Giannis OUT groin 19 menit sebelum analisis" sebagai bahan vonis. Hutang lama yang diakui (`LAPORAN-PERBAIKAN-RACIK.md` §6.9). |
| (c) | Simulasi 100.000x MULTI-SKENARIO + tabel P(Under) per garis per skenario | ◐ SEBAGIAN | Sim 100.000x ada (`engine/nba_sim.py::simulate`), skenario skuad `full / missing_1 / missing_2 / missing_4 / doubtful_out` (cabang cedera ✅), peluang OT per laga. Yang TIDAK ADA: skenario **banjir FT**, **banjir 3P**, dan skenario **konservatif/sejajar pasar**. Efek kandang hanya penyesuaian tetap (+1,6639), bukan cabang skenario. Skenario skuad hanya membawa peluang, tanpa proyeksi total per skenario. |
| (d) | Vonis HIJAU/KUNING + target garis per laga + "racun" | ◐ SEBAGIAN | Target garis per laga ✅ (`engine/cushion.py::utama_line` + `insurance_line`, bantalan adaptif). Vonis warna ❌: mesin hanya punya status artefak OK / HOLD / DATA_INCOMPLETE (soal kelengkapan data, bukan kualitas laga) — terverifikasi: grep `hijau\|kuning\|vonis` di `engine/` + `report/` tidak menemukan sistem vonis. "Racun" ❌: tidak ada penjelasan mode-kegagalan per laga. Yang terdekat: anomali (`engine/anomaly.py`) dan "Kenapa beda?" — soal angka, bukan soal "apa yang bisa menjebol Under laga ini". |
| (e) | Pemilihan kaki dari EDGE + membuang laga tanpa edge | 🔀 BERBEDA CARA | **Kesenjangan konseptual terbesar.** Gemini memilih 4 kaki edge 8,5–13,2 poin dan membuang ORL & IND (edge < 2 poin). Mesin kita: (1) `edge` (p_final − harga) hanya **dicatat** di kaki tiket (`engine/ticket_composer.py:1046`) tapi **tidak pernah dipakai** untuk seleksi (terverifikasi: hanya 2 kemunculan `edge` di file itu); (2) seleksi subset mengoptimasi peluang menang + pengali, bukan edge; (3) selisih median vs garis market justru dipakai ke arah BERLAWANAN — `market_line_check.total_gap_points: 5,0` + aturan **condong-ke-market** menganggap gap besar sebagai alasan untuk TIDAK percaya model dan memakai probabilitas market untuk Asuransi. **Gemini melihat gap besar = peluang; mesin melihat gap besar = kecurigaan.** Keduanya tidak bisa benar bersamaan tanpa aturan yang memutuskan kapan gap adalah edge dan kapan gap adalah kesalahan model. |
| (f) | Racikan 2 tiket + pembagian modal + tabel skenario hasil | ◐ SEBAGIAN | Dua tiket ✅ (`compose_tickets`), pembagian modal ✅ (50/50 default; user pagi ini $15+$15 dari $30), peluang + EV + "bila menang, kembali $X" per tiket ✅. Yang TIDAK ADA: **tabel skenario hasil gabungan** (keduanya tembus / hanya Asuransi / keduanya gugur + dolar tiap skenario). `p_total_loss` masih `None` (terverifikasi: `ticket_composer.py:96` — butuh sebaran gabungan antar-tiket yang berkorelasi). Optimizer §6c (3 opsi racikan) ada di config tapi peracik hanya menghasilkan satu pasangan tiket (`optimizer/tickets.py` ada, tidak dipanggil `compose_tickets`). |
| (g) | Debat interaktif: menjawab keberatan dengan angka | ◐ SEBAGIAN | QA deterministik ✅ (`engine/qa.py::answer`, 6 intent termasuk sim ulang "bagaimana jika absen" 20.000x). Tapi QA bersifat **per-laga dan per-artefak**, bukan per-tiket/per-slate. Yang TIDAK ADA: debat tingkat tiket — "tumpuk 6 vs 4 kaki?", "lantai harga 78¢?", "buang kaki X?" — dengan racik ulang + perbandingan antar-varian. Tidak ada jalur meracik ulang dengan parameter berbeda. |
| (h) | Audit tiket riil (garis+harga user → peluang per kaki, kaki paling rapuh, pangsa skenario kalah) | ❌ TIDAK ADA | Tidak ada modul apa pun yang menerima tiket riil dari user lalu mengauditnya (terverifikasi: grep `audit\|tempel` di `cli.py` + `engine/` + `report/` kosong). Yang terdekat bukan audit: `live_status.evaluate_ticket()` memantau tiket SETELAH dipasang; `recheck.decide()` memvalidasi kaki **buatan mesin sendiri**. Yang hilang persis seperti yang Gemini lakukan: peluang per kaki, kaki paling rapuh, pangsa skenario kalah per kaki (IND 21,1%, ORL 16,5%), dan perbandingan "tanpa kaki X" (3,16x, peluang 60,2%, EV +90,3%). |
| (i) | Struktur hedge (kaki berisiko sengaja tidak masuk Asuransi) | ❌ TIDAK ADA | Mesin melakukan kebalikannya secara struktural: satu laga BOLEH masuk kedua tiket, hanya dengan syarat garis Asuransi > garis Utama. Tidak ada konsep "kaki berisiko sengaja dikecualikan dari Asuransi". Yang ada hanya filter kelayakan per kaki (MAHAL, TANPA_XG, volume tipis) — itu filter, bukan desain hedge. Gemini: ORL hanya di Utama ("hedge gratis"). |
| (j) | Flag overpay (harga di atas peluang model) | ✅ SUDAH PUNYA | Label DISKON/WAJAR/MAHAL dari EV (`engine/price_labels.py`), MAHAL dilarang masuk Asuransi, plus penilaian "wajar" dari jarak garis vs bantalan (`engine/analis.py::nilai_wajar`). Setara dengan fungsi flag overpay Gemini ("85¢ = ilusi aman"). Nuansa yang belum ada: flag gabungan "harga tinggi TAPI bantalan riil tipis karena garis pasar sudah diperas" (kasus IND) — mesin punya kedua angka di tempat berbeda tapi tidak menggabungkannya menjadi satu peringatan. |
| (k) | Penjelasan bahasa percakapan + menenangkan user yang panik | ◐ SEBAGIAN | Bahasa percakapan ✅ (laporan Indonesia sehari-hari, alasan bantalan kata-kata biasa, jawaban QA tanpa jargon). Menenangkan user yang panik ❌: tidak ada fungsi yang mengoreksi hitungan user yang salah dengan angka lalu menenangkan ("6 kaki @84¢ = 2,85x, bukan 2x"). QA hanya menjawab pertanyaan yang dikenali; tidak mendeteksi kesalahpahaman dan tidak proaktif mengoreksi. |

### Ringkasan hitungan

| Status | Jumlah |
|---|---|
| ✅ SUDAH PUNYA | 1 (j) |
| ◐ SEBAGIAN | 7 (a, b, c, d, f, g, k) |
| 🔀 PUNYA TAPI BERBEDA CARA | 1 (e) |
| ❌ TIDAK ADA | 2 (h, i) |

**Pola yang muncul:** mesin kita kuat di fondasi (data, simulasi 100.000x,
pemilihan garis, label harga, laporan) dan lemah di **lapisan analis tingkat
slate/tiket**: edge sebagai logika seleksi, skenario stres, vonis + racun,
audit tiket riil, struktur hedge, tabel skenario hasil, dan debat what-if.
Semua yang hilang itu adalah hal-hal yang Gemini lakukan DI ATAS angka dasar
— bukan angka dasarnya sendiri.

---

## 4. Cek konsistensi angka Gemini (dihitung ulang dari transkrip)

Semua hitungan di bawah dikerjakan ulang oleh koordinator + pekerja C dari
angka yang tertulis di transkrip. **Tidak ada verifikasi ke sumber luar.**

### 4.1 Yang konsisten — aritmetika turunannya koheren

| Cek | Hitungan ulang | Klaim Gemini | Selisih |
|---|---|---|---|
| Peluang Asuransi riil (4 kaki) | 0,957 × 0,931 × 0,923 × 0,921 = 75,74% | 75,8% | −0,06 |
| Peluang Utama riil (6 kaki) | 0,933 × 0,913 × 0,911 × 0,906 × 0,854 × 0,821 = 49,29% | 49,5% | −0,21 |
| Utama tanpa IND | 0,4929 / 0,821 = 60,04% | 60,2% | −0,16 |
| Pangsa kalah IND saja | (1−0,821) × 0,6004 / (1−0,4929) = 21,19% | 21,1% | +0,1 |
| Pangsa kalah ORL saja | (1−0,854) × (0,4929/0,854) / (1−0,4929) = 16,62% | 16,5% | +0,1 |
| 6 kaki @84¢ (mentah) | (100/84)⁶ = 2,8466 | 2,85x | +0,1% |
| 6 kaki @82¢ (mentah) | (100/82)⁶ = 3,2894 | 3,29x | −0,0% |
| EV Utama riil | 0,495 × 3,72 − 1 = +84,14% | +84,2% | +0,1 |
| EV Utama tanpa IND | 0,602 × 3,16 − 1 = +90,2% | +90,3% | +0,1 |
| OT 4 laga → per laga | 1 − (1−0,144)^(1/4) = 3,81% | ~3,8%/laga | ✓ |
| OT 6 laga → per laga | 1 − (1−0,207)^(1/6) = 3,79% | ~3,8%/laga | ✓ |
| Bantalan IND vs model | 230,5 − 214,3 = 16,2 | +16,2 poin | ✓ |
| Edge ORL / IND | 219,5−217,7 = 1,8 / 213,5−214,3 = −0,8 | "< 2 poin" | ✓ (IND negatif) |
| Bantalan Asuransi vs model | OKC 30,2; DAL 25,0; DEN 25,4; BOS 23,5 | "23,5–30,2" | ✓ |

Kesimpulan: **Gemini pandai berhitung dari angka-angka yang ia sendiri pakai
sebagai input.** Produk peluang, pangsa kalah, bantalan, dan OT semuanya bisa
direkonsiliasi. Masalahnya bukan hitung-hitungan — melainkan §4.2 dan §4.3.

### 4.2 Temuan material — dua kesalahan basis + angka yang bergeser

**Temuan 1 — EV Asuransi salah basis (+5,2 poin).** EV Asuransi +69,7%
dihitung dengan pengali MENTAH (0,758 × 2,2398 − 1 = +69,78%), sementara EV
Utama +84,2% dihitung dengan pengali ASLI jup.ag (0,495 × 3,72 − 1 =
+84,14%). **Satu audit, dua basis.** Pada pengali riil 2,17x, EV Asuransi
yang benar adalah +64,5% (0,758 × 2,17 − 1). Selisih 5,2 poin — lebih besar
dari ambang label DISKON/MAHAL kita (±2%). Alternatifnya: bila EV +69,7% dan
pengali 2,17 keduanya benar, peluangnya harus 78,2%, bukan 75,8% —
kontradiksi dengan klaim peluangnya sendiri. Satu dari tiga angka Asuransi
(P / pengali / EV) salah; yang paling mungkin salah adalah basis pengali EV.

**Temuan 2 — Garis OKC dipakai dua nilai berbeda (selisih 3 poin).**
Tabel jadwal memakai garis pasar OKC 228,5 (edge 228,5 − 212,3 = 16,2 poin),
tapi ringkasan edge "8,5–13,2 poin" hanya koheren bila garis OKC = 225,5
(225,5 − 212,3 = 13,2 persis; tiga laga lain: DEN 9,4, DAL 10,0, BOS 8,5 —
semuanya di dalam rentang). Tabel racikan Asuransi sendiri menulis garis OKC
"~225,5". Nuansa jujur: selisih ini **mungkin** mencerminkan pergerakan pasar
selama ~30 menit (231,5 buka → 228,5 setelah SGA OUT → ~225,5 setelah
Giannis OUT — Gemini sendiri berkata pasar "masih berpotensi turun lebih
dalam"). Tapi Gemini tidak pernah menyatakan garis mana yang dipakai tiap
perhitungan, sehingga rentang edge mencampur dua basis. Tiga poin itu
material: lebih besar dari ambang gerak garis 2,0 poin yang memicu hitung
ulang di recheck mesin kita.

**Temuan 3 — Peluang Asuransi bergeser antar jawaban (75,8% → 76,6%).**
Audit Asuransi: 75,8% normal / 52,6% konservatif. Jawaban penenang (beberapa
pesan kemudian): 76,6% normal / 53,4% konservatif — dan angka 76,6% itu
adalah angka yang sama dengan "peluang minimal satu tiket hijau" dari audit
Utama (49,5% + 27,1% = 76,6%). Artinya angka yang sama dipakai untuk dua hal
berbeda, dan peluang Asuransi naik 0,8 poin tanpa perhitungan baru. Pergeseran
ini merambat: "hanya Asuransi tembus" 27,1% cocok dengan 76,6% (0,766 −
0,495 = 0,271), bukan dengan 75,8% (0,263). EV konservatif di kedua jawaban
masing-masing konsisten dengan peluangnya sendiri (+19,6% dari 53,4%;
+17,9% dari 52,6%) — jadi aritmetikanya benar, inputnya yang bergeser.

**Temuan 4 — 2,79x vs 2,85x dalam satu jawaban.** Di jawaban penenang yang
sama, teks berkata "6 kaki @84¢ = 2,85x (1/0,84⁶ = 2,85)" (mentah, benar:
2,8466), tapi tabel di jawaban itu menulis "6 kaki @ ~84¢ → 2,79x" (= mentah
× 0,98 — potongan ~2% yang tidak dinyatakan). Dua basis pengali dalam satu
jawaban.

**Temuan 5 — Angka kecil yang melenceng karena diketik ulang.** Peluang
Asuransi 71,6% (racikan awal) vs 71,7% (tabel debat); rentang peluang per
kaki Asuransi 92,1–95,7% (audit) vs 92,4–95,8% (jawaban penenang). Nilainya
sepele, tapi buktinya penting: **angka dihitung ulang/diketik ulang tiap
jawaban, bukan dirujuk dari satu sumber.** Mesin kita menghitung sekali,
menyimpan di artefak, dan recheck membandingkan terhadap snapshot tersimpan.

### 4.3 Keberatan metodologis (bukan soal aritmetika)

**Hitung ganda risiko OT.** Bila simulasi 100.000x Gemini sudah memasukkan OT
(seperti sim kita), maka P(Under) 71,6% / 60,5% SUDAH mengandung risiko OT.
Mengutip "peluang OT 14,4% → 20,7%" sebagai alasan TAMBAHAN menolak 6 kaki
berarti menghitung risiko yang sama dua kali. Yang relevan bukan P(ada OT),
melainkan P(total melewati garis) — dan itu sudah menjadi keluaran simulasi.

**Perbandingan 6 kaki yang tidak adil.** Klaim "6 kaki @87,5¢ peluang 60,5%"
menyiratkan tiap kaki ~92% (0,92⁶ = 60,6%) — SAMA dengan kaki 82¢. Padahal
kaki 87,5¢ adalah garis yang LEBIH AMAN, jadi peluang per kakinya seharusnya
LEBIH TINGGI. Asumsi tersirat ini tidak dinyatakan dan merugikan opsi 6 kaki.

**"Chance" jup.ag bukan probabilitas.** 1/2,17 = 46,1% ≈ 46% di layar;
1/3,72 = 26,9% ≈ 27%. "Chance" itu hanya titik impas (1/pengali).
Kesenjangan Gemini-vs-market sangat besar: Asuransi 75,8% vs 46,1% tersirat
(~30 poin); Utama 49,5% vs 26,9% (~23 poin). Di bawah aturan mesin kita,
selisih > 8 poin WAJIB memicu bagian "Kenapa beda?" — Gemini tidak punya
mekanisme seperti itu.

**Yang paling mendasar: input tanpa asal-usul.** Semua cek di §4.1 membuktikan
aritmetika turunannya koheren — tapi itu hanya membuktikan Gemini pandai
berhitung dari angka-angka yang IA SENDIRI karang sebagai input. Peluang per
kaki 95,7%, proyeksi 212,3, "21,1% skenario kalah" — tidak ada satu pun yang
bisa dilacak ke perhitungan yang dapat diulang. Presisi tanpa provenance lebih
berbahaya daripada perkiraan kasar yang jujur.

### 4.4 Catatan sampingan — potongan kombo jup.ag tidak tetap (data kalibrasi)

Dari dua tiket riil: potongan tersirat jup.ag 3,12% (Asuransi) dan 4,13%
(Utama) — bukan angka tetap. Potongan 5,5% mesin kita (D8) konservatif di
kedua tiket (meremehkan pengali riil 1,4–2,5%) — arah yang aman. D8 sudah
memerintahkan menyimpan selisih vs pengali asli jup.ag untuk kalibrasi; dua
tiket ini adalah data kalibrasi pertama (n=2, belum cukup untuk mengubah
5,5%).

---
## 5. Apa yang mesin kita lakukan lebih baik / lebih ketat dari Gemini

Jujur soal keduanya: mesin kita bukan hanya tertinggal — di tujuh hal ini ia
lebih ketat, dan ketujuh-tujuhnya harus dipertahankan saat meniru Gemini.

### 5.1 Angka dari kode deterministik yang bisa diulang

`engine/nba_sim.py::simulate()` — simulasi 100.000x Student-t + OT + skenario
skuad, dengan seed (hasil deterministik), rumus proyeksi tertulis di docstring,
parameter HASIL FIT dari data (sigma_total 18,9868, home 1,6639, dst. — D12,
disetujui user). Input yang sama → angka yang sama, kapan pun dijalankan.
Gemini: "simulasi 100.000x MULTI-SKENARIO" tanpa kode, tanpa seed, tanpa
parameter yang bisa dibaca. Angka 95,7% tidak bisa dihitung ulang oleh siapa
pun — termasuk oleh Gemini sendiri di jawaban berikutnya (buktinya §4.2:
71,6% vs 71,7%, rentang kaki yang melenceng, 75,8% → 76,6%).

### 5.2 Fail-closed: data hilang = BERHENTI, bukan mengarang angka

Sim menolak jalan bila data hilang (`ValueError("data_tidak_lengkap")`);
parameter null → `ConfigError` (D12: "JANGAN ditebak"); cushion →
`meets=False` + alasan; recheck → DATA_INCOMPLETE bila tangga segar gagal;
peracik mencoret kaki JANGAN_PASANG/DATA_INCOMPLETE dan kaki yang hilang dari
laporan recheck; `bantalan_adaptif` → `None` bila input hilang ("jangan
tebak"); `nilai_wajar` → "tidak_terverifikasi". Gemini TIDAK PERNAH mengatakan
"data tidak lengkap" di seluruh transkrip — selalu ada vonis dan angka 1
desimal, bahkan untuk laga dengan pemain Questionable (IND) dan garis pasar
yang ia sendiri sebut "diperas".

### 5.3 Cek keterbelian: volume & bid/ask, bukan sekadar harga

`_parse_tangga` mempertahankan `volume_usd` + `thin` tiap baris; volume None
→ thin (likuiditas tak diketahui = tipis = fail-closed). Garis tipis adalah
PENGHALANG KERAS untuk Asuransi; lantai volume $100. Bukti live: verifikasi
Tahap 4 — Asuransi gagal di 2/3 laga karena volume tipis, dan mesin
MELAPORKAN kegagalan itu dengan jujur, bukan memaksakan tiket. Gemini
merekomendasikan garis sampai U 256,5 (DEN Asuransi) TANPA SATU PUN penyebutan
volume/likuiditas. Data live kita: garis jauh bervolume $5–11 — garis yang
"aman" di atas kertas bisa tidak terbeli $15 tanpa menggerakkan harga.

### 5.4 Condong-ke-market + "Kenapa beda?" — mesin tidak percaya diri sendiri begitu saja

`|median model − garis market| > 5,0` tanpa alasan konkret → kaki Asuransi
memakai probabilitas MARKET; < 74% → JANGAN_PASANG (`engine/recheck.py::
_kenapa_beda`). Blend w_model 0,3 (pasar patokan utama; w baru naik bila
ledger membuktikan model lebih akurat, atas persetujuan user). Gemini: selisih
model-vs-market OKC 16,2 poin (tiga kali ambang pemicu kita) diterima begitu
saja sebagai "edge" — tanpa mekanisme apa pun untuk bertanya apakah MARKET
yang tahu sesuatu. Kesenjangan peluangnya vs tersirat market ~30 poin tidak
pernah dipertanyakan.

### 5.5 Recheck pra-submit — cek ulang sebelum uang keluar

`engine/recheck.py::decide`: ambil ulang cedera (PDF + ESPN) dan tangga;
gerak harga ≥ 3¢ = anomali (aturan Thunder); gerak garis > 2 poin → resim;
garis berubah → JANGAN_PASANG garis lama + `action_required`. Exit code 0 =
GO, 1 = NO-GO, 2 = tidak bisa berjalan. Gemini adalah analisis SATU JEPRETAN
(one-shot chat). Buktinya di transkrip sendiri: user menambah kaki IND 3
menit sebelum tip-off MELAWAN rekomendasi — tidak ada recheck apa pun sebelum
submit; audit baru datang sesudah tiket terpasang.

### 5.6 Pengali & EV dengan basis yang dinyatakan dan konservatif

`combo_multiplier` = Π(100/harga) × (1 − 5,5%), potongan TERTULIS di config
(`combo.spread_cut_pct`), bukan tersembunyi. §4.4 membuktikan 5,5%
konservatif vs potongan riil jup.ag (3,1–4,1%). Kaki dari laga yang SAMA tidak
dikali mentah-mentah (`ticket_win_probability`: P = P(total ≤ garis terendah)
dari distribusi sim). Laporan menampilkan p_model | p_pasar (+ sumber) |
p_akhir TERPISAH, dan setiap datum membawa sumber + jenjang + jam (aturan
B1). Gemini: pengali mentah tanpa potongan (EV Asuransi +5,2 poin terlalu
tinggi), basis EV berubah antar tiket tanpa dinyatakan, tanpa jejak
sumber/jam untuk angka mana pun.

### 5.7 Mesin belajar hanya lewat persetujuan — tidak ada parameter yang berubah diam-diam

Prinsip keamanan belajar (Langkah 6): mesin MENGHITUNG rekomendasi, perubahan
HANYA berlaku setelah persetujuan user (pola D12). Ditegakkan kode: fungsi
rekomendasi murni tanpa tulis file, keluaran membawa `"diterapkan": False`.
Kalibrasi w tiap 50 kaki via Brier. Gemini tidak punya loop kalibrasi: klaim
75,8% tidak pernah di-skor terhadap hasil nyata, dan tidak ada mekanisme
baginya untuk menjadi kurang percaya diri setelah salah.

---

## 6. Usulan perubahan desain (bukan kode)

Diurutkan dari yang paling berdampak. Setiap usulan: APA, KENAPA (bukti dari
transkrip), RISIKO. Prinsip payung dari §5: **salin struktur kerja Gemini,
bukan mesin hitungnya** — kode menghitung, penjelasan hanya menjelaskan
artefak yang sudah dihitung.

### Usulan 1 — Jadikan EDGE sebagai logika seleksi kaki, dan selesaikan pertentangannya dengan condong-ke-market

- **APA:** Tambah `edge_points = garis_market − median_model` sebagai field
  per laga/per kaki. Peracik menyeleksi dan mengurutkan kandidat berdasarkan
  edge (dengan ambang minimum), dan membuang laga tanpa edge — bukan hanya
  berdasarkan peluang + pengali. Bersamaan dengan itu, putuskan aturan yang
  membedakan "gap besar = edge yang bisa dipakai" vs "gap besar = model
  dicurigai" (aturan condong-ke-market saat ini).
- **KENAPA:** Seluruh racikan Gemini dibangun dari edge: 4 kaki yang dipakai
  punya proyeksi 8,5–13,2 poin di bawah garis pasar; ORL & IND dibuang karena
  edge < 2 poin. Tanpa logika ini, mesin bisa meracik kaki dari laga yang
  garisnya sudah diperas — persis kesalahan yang membuat user menambah
  IND@NYK U 230,5 @85¢ sendiri ("85¢ = ilusi aman", bantalan riil hanya
  +16,2 poin; kaki itu menyebabkan 21,1% skenario kalah Utama). Mesin saat
  ini bahkan tidak memakai `edge` yang sudah dicatatnya untuk seleksi.
- **RISIKO:** Edge besar bisa berarti model salah, bukan pasar salah —
  itulah alasan aturan condong-ke-market dibuat. Bila edge dijadikan raja
  tanpa penyeimbang, mesin bisa agresif di laga yang modelnya meleset. Perlu
  kalibrasi/backtest (apakah edge historis memprediksi kemenangan Under?)
  dan ambang minimum yang diputuskan user, bukan ditebak. Perubahan ini juga
  menyentuh keputusan user 2026-11-21 (peran harga pasar) sehingga tidak
  boleh diputuskan sepihak oleh agen.

### Usulan 2 — Tambah skenario stres ke simulasi: banjir FT, banjir 3P, konservatif/sejajar pasar

- **APA:** Perluas `nba_sim.simulate()` dengan cabang skenario baru di
  samping skenario skuad yang sudah ada: banjir free throw (~57–66 FTA),
  banjir 3 poin (+6% akurasi 3P, ~26–30 3PM), dan skenario konservatif
  (proyeksi digeser ke garis pasar). Keluarkan tabel P(Under) per garis per
  skenario untuk garis-garis tangga, bukan hanya garis yang dilewatkan ke
  sim.
- **KENAPA:** Ini inti cara Gemini menilai risiko: setiap laga diuji di 4–6
  skenario, dan vonis HIJAU/KUNING lahir dari seberapa tahan Under di
  skenario buruk — bukan dari satu angka peluang. Tanpa skenario stres,
  mesin hanya tahu "peluang Under di dunia normal" dan tidak tahu apa yang
  menjebolnya. Skenario ini juga bahan baku Usulan 4 (racun) dan Usulan 3
  (audit per skenario).
- **RISIKO:** Parameter stres (berapa FTA = "banjir"? +6% akurasi 3P dari
  basis apa?) harus difit dari data historis, bukan ditebak — D12 melarang
  parameter tebakan. Data laju FT/3P per laga mungkin belum tersedia di
  ingest saat ini. Waktu hitung naik (lebih banyak skenario × 100.000
  iterasi); perlu diukur apakah satu slate 6 laga tetap selesai dalam waktu
  yang wajar.

### Usulan 3 — Modul baru: Audit Tiket Riil (user tempel garis + harga → audit per kaki)

- **APA:** Modul/CLI baru yang menerima tiket riil dari user (daftar garis +
  harga per kaki, seperti yang tampil di layar jup.ag) dan mengembalikan:
  peluang per kaki dari model, peluang + EV tiket, kaki paling rapuh, pangsa
  skenario kalah per kaki (dekomposisi peluang kalah tiket), flag overpay per
  kaki, dan perbandingan "tanpa kaki X" (pengali, peluang, EV bila kaki
  terburuk dibuang).
- **KENAPA:** Ini fitur Gemini yang paling langsung menyelamatkan uang user
  pagi ini. Audit Asuransi riil: 75,8% normal, EV +69,7%, per kaki 92,1–
  95,7%. Audit Utama riil: 49,5% normal, EV +84,2%, kaki paling rapuh IND
  (21,1% skenario kalah) lalu ORL (16,5%) — dan temuan kuncinya: "Tanpa IND:
  3,16x tapi peluang 60,2%, EV +90,3% (lebih tinggi)". User memasang tiket 3
  menit sebelum tip-off dalam keadaan buru-buru; audit otomatis adalah jaring
  pengaman terakhir sebelum uang keluar. Semua bahan sudah ada di mesin
  (distribusi sim per laga, label harga, rumus EV) — yang belum ada hanya
  modulnya dan jalur inputnya.
- **RISIKO:** Input dari user bisa salah ketik/salah baca (garis atau harga
  keliru) — perlu validasi silang ke tangga (garis harus ada di tangga; harga
  dalam rentang wajar) dan fail-closed bila tidak cocok. Pangsa skenario
  kalah mengasumsikan kaki independen; korelasi antar-kaki harus dinyatakan
  jujur sebagai batasan. Format input (teks tempel? foto screenshot?) perlu
  diputuskan — screenshot butuh OCR, di luar cakupan modul ini.

### Usulan 4 — Vonis per laga (HIJAU/KUNING/…) + "racun" (cara spesifik Under bisa jebol)

- **APA:** Setiap artefak analisis mendapat vonis per laga yang diturunkan
  dari aturan yang tercatat (mis. peluang Under di skenario normal DAN
  skenario stres, edge, status Questionable, volume tangga), plus satu field
  "racun": cara spesifik yang paling mungkin menjebol Under laga itu (mis.
  "banjir FT: di skenario 60+ FTA, P(Under 242,5) turun ke X%"; "KAT/Siakam
  main → peluang turun ke 70,7%"; "peluang OT 14,4%").
- **KENAPA:** Vonis adalah bahasa yang dipakai user untuk mengambil keputusan
  cepat: OKC/BOS/DAL HIJAU, IND HIJAU BERSYARAT, ORL KUNING–HIJAU, DEN
  KUNING — lengkap dengan target garis per tiket per laga. "Racun" adalah
  yang membuat vonis itu bisa dipercaya: Gemini tidak hanya bilang "KUNING",
  tapi bilang KENAPA dan lewat jalur apa Under bisa jebol. Mesin saat ini
  memberi angka tanpa vonis, sehingga user harus menafsirkan sendiri
  angka-angka itu di bawah tekanan waktu (dan terbukti salah tafsir: menambah
  IND 3 menit sebelum tip-off).
- **RISIKO:** Ambang vonis (berapa % = HIJAU?) adalah angka baru yang belum
  dikalibrasi — bila salah, vonis memberi rasa aman palsu, lebih berbahaya
  daripada tidak ada vonis. "Racun" harus diturunkan dari skenario yang
  benar-benar dihitung (Usulan 2), bukan dari template kalimat generik. Perlu
  diputuskan apakah vonis memengaruhi seleksi tiket (KUNING tidak masuk
  Asuransi?) atau hanya informatif — itu bersinggungan dengan Usulan 6.

### Usulan 5 — Kesadaran waktu slate: peta slate berprioritas + skip laga mepet tip-off

- **APA:** (1) Laporan slate satu halaman: semua laga malam ini dengan jam
  tip-off, edge, vonis, dan urutan prioritas analisis. (2) Peracik dan
  recheck membaca jam tip-off: laga yang tip-off-nya kurang dari X menit
  lagi dikeluarkan dari racikan baru (atau ditandai "mepet — pasang sekarang
  atau lewatkan"), dan rekomendasi kedaluwarsa bila tip-off lewat. (3) Urutan
  kerja otomatis: analisis laga paling awal dulu.
- **KENAPA:** Slate pagi ini tersebar 06:00–08:30 WIB, dan tekanan waktu
  nyata: user menambah kaki IND "buru-buru, 3 menit sebelum tip-off" —
  keputusan terburuk pagi itu, yang dibuat justru karena tidak ada mesin yang
  berkata "laga ini sudah mepet, lewatkan". Gemini sadar waktu karena ia
  bekerja dalam percakapan; mesin yang otomatis harus sadar waktu lewat jam.
- **RISIKO:** Ambang "mepet" (30? 60 menit?) perlu diputuskan user; terlalu
  longgar membuat mesin membuang laga yang masih bisa dipasang, terlalu ketat
  membuat mesin meracik tiket yang tidak sempat dipasang. Penanganan zona
  waktu (ET vs WIB vs UTC) harus benar — salah satu jam saja bisa membuat
  mesin melewatkan seluruh slate. Laga yang sudah mulai harus dikeluarkan
  secara fail-closed, bukan diam-diam tetap diracik.

### Usulan 6 — Struktur hedge eksplisit: kaki berisiko sengaja TIDAK masuk Asuransi

- **APA:** Definisikan "kaki berisiko" dari aturan tercatat (mis. vonis
  KUNING, edge di bawah ambang, pemain kunci Questionable, atau garis dari
  tangga tipis) dan tegakkan di peracik: kaki berisiko boleh masuk Utama tapi
  dilarang masuk Asuransi — bahkan bila peluang dan harganya lolos. Catat
  alasan pengecualian di ringkasan ("ORL hanya di Utama sebagai hedge").
- **KENAPA:** Ini desain yang membuat dua tiket Gemini benar-benar berbeda
  peran, bukan sekadar dua versi garis yang sama: "Hedge gratis: ORL hanya
  ada di Utama, tidak di Asuransi" — dan saat user panik, Gemini menjelaskan
  fungsi hedge itu: "Asuransi tidak memuat kaki berisiko (ORL/IND) yang ada
  di Utama — kalau Utama patah di situ, Asuransi tetap selamat." Mesin saat
  ini menaruh laga yang sama di kedua tiket (dengan garis berbeda), sehingga
  satu laga yang jebol bisa membunuh kedua tiket sekaligus — persis kegagalan
  yang diperbaiki Tahap 4 di level garis, tapi belum di level struktur.
- **RISIKO:** Mempersempit kandidat Asuransi — di slate kecil (3 laga),
  Asuransi bisa gagal terbentuk lebih sering (sudah terjadi di verifikasi
  Tahap 4: 2/3 laga gagal Asuransi karena volume). Definisi "berisiko" yang
  terlalu luas membuat Asuransi hampir tidak pernah terisi; yang terlalu
  sempit membuat hedge tidak bermakna. Perlu diputuskan apakah hedge berlaku
  per laga atau per kaki, dan apakah user boleh menonaktifkannya per malam.

### Usulan 7 — Tabel skenario hasil gabungan dua tiket di ringkasan racikan

- **APA:** Tambahkan ke `compose_tickets()` summary sebuah tabel 3–4 skenario
  dengan hasil dolar: keduanya tembus, hanya Asuransi tembus, hanya Utama
  tembus, keduanya gugur — memakai stake dan pengali masing-masing tiket,
  plus probabilitas tiap skenario.
- **KENAPA:** Gemini memberi tabel ini untuk simulasi modal $27 ($15 Utama +
  $12 Asuransi) — inilah yang membuat user mengerti APA YANG TERJADI pada
  uangnya, bukan hanya "EV +X%". Mesin saat ini hanya memberi per tiket
  ("bila menang, kembali $X") dan `p_total_loss` masih `None`. Ini usulan
  termurah di daftar ini (hanya aritmetika dari angka yang sudah ada) dengan
  kejelasan tertinggi bagi user.
- **RISIKO:** Probabilitas skenario gabungan butuh asumsi independensi antar
  tiket — padahal bila satu laga ada di kedua tiket, kedua tiket berkorelasi
  (laga jebol → keduanya bisa kalah bersamaan). Tabel harus menghitung
  probabilitas gabungan dengan benar dari kaki-kaki yang tumpang tindih, atau
  menyatakan asumsi independensi secara eksplisit bila tidak bisa. Angka yang
  salah di sini lebih menyesatkan daripada tidak ada tabel.

### Usulan 8 — Debat what-if tingkat tiket di QA: bandingkan racikan alternatif dengan angka

- **APA:** Perluas `engine/qa.py` (atau modul debat baru) dengan intent
  tingkat tiket/slate: "tumpuk 6 kaki vs 4 kaki?", "lantai harga 78¢?",
  "buang kaki X?" — setiap pertanyaan dijawab dengan meracik ulang varian
  yang diminta (memakai `compose_tickets()` dengan parameter berbeda) lalu
  membandingkan pengali, peluang menang, EV, dan peluang OT antar-varian
  dalam satu tabel.
- **KENAPA:** Debat adalah "inti cara kerja" Gemini menurut REFERENSI file:
  user mengusulkan 6 kaki untuk Asuransi, Gemini menjawab dengan angka (6
  kaki @87,5¢ = 2,21x tapi peluang 60,5% vs 71,7%; peluang OT 14,4% →
  20,7%; "2 kaki tanpa edge = beban mati") dan user menerima. User juga
  meminta lantai 78¢ karena trauma kaki 71¢ (Thunder) — Gemini menggeser
  racikan, bukan sekadar menjawab. Mesin saat ini tidak bisa diajak berdebat
  seperti ini: QA hanya menjawab soal satu laga, dan tidak ada jalur meracik
  ulang dengan parameter berbeda.
- **RISIKO:** Cakupan bisa melebar tanpa batas (setiap "bagaimana kalau…"
  adalah fitur baru) — perlu dibatasi pada 2–3 varian yang paling sering:
  jumlah kaki, lantai harga, dan buang/tambah satu kaki. Setiap varian harus
  memakai artefak + recheck yang sama agar perbandingan apel-ke-apel; bila
  data berubah di tengah debat, hasil bisa tidak konsisten. Perlu diputuskan
  apakah debat berjalan di CLI/chat dan siapa yang memegang status ("racikan
  aktif saat ini").

### Usulan 9 — Flag gabungan "ilusi aman": harga tinggi + bantalan riil tipis

- **APA:** Peringatan per kaki yang menggabungkan dua sinyal yang saat ini
  terpisah: label harga (MAHAL/overpay, dari EV) dan penilaian wajar (jarak
  garis vs bantalan adaptif) — dengan perhatian khusus pada kasus garis pasar
  sudah diperas (edge kecil) sehingga harga tinggi tidak berarti aman.
- **KENAPA:** Kasus IND@NYK adalah pelajaran termahal pagi ini: U 230,5 @85¢
  TERLIHAT aman (harga tinggi), tapi garis pasar 213,5 sudah diperas sehingga
  bantalan riil hanya +16,2 poin; KAT & Siakam main → peluang 70,7%. Gemini
  menyebutnya "ilusi aman". Mesin punya kedua angka (label MAHAL +
  `nilai_wajar`) tapi tidak pernah menggabungkannya menjadi satu peringatan
  yang akan menghentikan user sebelum memasang.
- **RISIKO:** Kecil — ini lapisan presentasi di atas angka yang sudah ada.
  Risiko utamanya adalah ambang: kapan kombinasi itu cukup serius untuk
  menjadi peringatan keras vs catatan biasa. Sebaiknya peringatan ini juga
  dipakai di audit tiket riil (Usulan 3), bukan hanya di laporan analisis.

### Usulan 10 — Modul berita breaking (pelengkap cedera, bukan pengganti)

- **APA:** Ingest berita NBA real-time dari sumber gratis (feed resmi
  tim/liga atau agregator bebas) yang hanya mengekstrak fakta berdampak-laga:
  pemain OUT/cedera mendadak, perubahan starter, dan konteks (mis. "pertama
  kali absen musim ini"). Hasilnya masuk artefak sebagai field `news` dengan
  sumber + jam, dan memicu recheck bila muncul setelah analisis.
- **KENAPA:** Dua fakta berita mengubah analisis Gemini pagi ini: SGA OUT
  (pertama musim ini) dan Giannis OUT groin 19 menit sebelum analisis. Feed
  cedera 2 sumber yang dimiliki mesin mungkin menangkap status OUT-nya, tapi
  tidak menangkap konteks ("pertama kali", "19 menit lalu") dan tidak
  menangkap berita non-cedera (motivasi, pelatih, rotasi). Ini hutang lama
  yang sudah diakui (`LAPORAN-PERBAIKAN-RACIK.md` §6.9).
- **RISIKO:** Sumber berita gratis sering tidak stabil, berubah format, atau
  punya batasan ToS (FotMob/Sofascore sudah ditolak karena alasan ini).
  Berita juga paling rawan "kabar burung" — perlu aturan: hanya fakta dari
  sumber resmi yang dipakai untuk keputusan, sisanya hanya catatan. Prioritas
  paling rendah di daftar ini karena feed cedera sudah menutup sebagian besar
  nilai berita cedera; usulan ini hanya menutup sisanya.

### Yang TIDAK boleh disalin dari Gemini (peringatan penantang)

1. **Angka "presisi palsu" tanpa asal-usul.** 95,7%, EV +69,7%, "21,1%
   skenario kalah" — presisi 1 desimal seolah-olah hasil komputasi, padahal
   tidak ada komputasi yang bisa diulang. Setiap angka mesin harus membawa
   sumber + cara hitung + jejak — atau berlabel `tidak_terverifikasi`.
2. **Klaim EV yang basisnya berubah tanpa dinyatakan.** Satu audit, dua basis
   (§4.2 Temuan 1). EV selalu dengan pengali yang dinyatakan (D7/D8).
3. **Vonis yang terlalu percaya diri + angka yang berubah tiap jawaban.**
   Menyalin gaya vonis Gemini berarti menukar artefak yang stabil dengan
   narasi yang bergeser tiap dibaca — dan menghancurkan kalibrasi (Brier atas
   p_final menjadi tak bermakna bila p_final bukan fungsi yang stabil dari
   data).
4. **Hitung ganda risiko dan frasa persuasif sebagai pengganti kuantifikasi.**
   "Peluang OT 14,4% → 20,7%" di atas peluang sim yang sudah memasukkan OT;
   "hedge gratis" menyembunyikan bahwa Utama TETAP menanggung risiko ORL.
   Gantikan dengan angka: P(rugi total), EV gabungan.
5. **Rekomendasi garis tanpa cek keterbelian dan tanpa cek ulang pra-submit.**
   Dua pertahanan yang mesin kita bangun dengan susah payah (penghalang
   volume keras; recheck pra-submit) — jangan dibuang demi meniru alur
   "analisis → rekomendasi → selesai" Gemini.

---
## 7. Pertanyaan yang masih butuh jawaban user

1. **Edge vs condong-ke-market — mana yang menang?** Saat proyeksi model jauh
   di bawah garis pasar (gap besar), Gemini menganggap itu edge (peluang),
   tapi mesin saat ini menganggap itu alasan untuk tidak percaya model (gap >
   5 poin tanpa alasan konkret → pakai probabilitas market untuk Asuransi).
   Mana yang berlaku? Dan berapa ambang edge minimum (dalam poin) agar sebuah
   laga layak masuk racikan — Gemini membuang laga dengan edge < 2 poin dan
   memakai yang 8,5–13,2 poin; apakah ambang itu juga berlaku untuk mesin,
   dan apakah ambangnya sama untuk Utama dan Asuransi?
2. **Apa definisi "kaki berisiko" untuk struktur hedge?** Kaki mana yang boleh
   masuk Utama tapi sengaja tidak masuk Asuransi — yang vonisnya KUNING, yang
   edge-nya kecil, yang pemain kuncinya masih Questionable, atau yang user
   pilih sendiri per malam? Dan bila aturan hedge membuat Asuransi gagal
   terbentuk di slate kecil, apakah user lebih rela Asuransi tidak terbentuk,
   atau hedge dilonggarkan?
3. **Berapa menit sebelum tip-off sebuah laga harus dikeluarkan dari racikan
   baru?** (Mis. 30 menit? 60 menit?) Dan bila tip-off sudah lewat saat mesin
   bekerja, apakah rekomendasi untuk laga itu langsung kedaluwarsa, atau
   tetap ditampilkan dengan label "sudah mulai"?
4. **Bagaimana user akan memberikan tiket riil untuk diaudit?** Apakah dengan
   menempel daftar garis + harga sebagai teks (mis. "OKC U 242,5 @83¢"), atau
   ada cara lain? Dan untuk audit, peluang per kaki sebaiknya memakai
   probabilitas model, probabilitas market, atau campuran keduanya (p_final)?
5. **Apa ambang vonis HIJAU vs KUNING?** Apakah vonis ditentukan dari peluang
   Under di skenario normal saja, atau harus tahan juga di skenario stres
   (banjir FT/3P)? Dan apakah vonis KUNING hanya informatif, atau ikut
   melarang kaki masuk Asuransi (berkaitan dengan pertanyaan 2)?
6. **Apakah skenario stres (banjir FT, banjir 3P) boleh memengaruhi seleksi
   kaki, atau hanya untuk laporan?** Mis. bila sebuah kaki lolos di skenario
   normal tapi jebol di skenario banjir FT — apakah kaki itu tetap boleh masuk
   tiket (dengan peringatan), atau langsung dicoret?
7. **Apakah user mau modul berita breaking dibangun dari sumber gratis?**
   Bila ya, apakah ada sumber berita NBA tertentu yang user percayai? Bila
   tidak, apakah feed cedera 2 sumber yang ada sudah cukup, dan berita
   non-cedera tetap di luar cakupan mesin?

---

## 8. Verifikasi koordinator (dari disk, bukan dari laporan pekerja)

Koordinator memverifikasi klaim-klaim kunci pekerja sebelum menulis laporan
ini:

- **Hitung ulang §4 dengan tangan (Python):** semua angka di tabel §4.1 dan
  temuan §4.2 dihitung ulang dari angka transkrip dan cocok dengan hitungan
  pekerja C (produk peluang, pengali mentah, EV dua basis, inversi OT, edge
  per laga, bantalan IND). Temuan 3 (76,6%) dan Temuan 4 (2,79x vs 2,85x)
  adalah temuan koordinator sendiri dari transkrip lengkap — tidak ada di
  REFERENSI file.
- **Angka yang tidak terlacak di REFERENSI, dikonfirmasi dari transkrip
  lengkap:** peluang per kaki Utama riil (93,3 / 91,3 / 91,1 / 90,6 / 85,4 /
  82,1), peluang 76,6%, risiko OT 3,8%/laga (audit Asuransi) dan 3,9%
  (DAL@UTA) — ketiganya ADA di transkrip lengkap di chat Muse.
- **Rujukan kode (grep):** semua fungsi kunci ada di lokasi yang diklaim
  pekerja A (`simulate` nba_sim.py:436, `insurance_line` cushion.py:377,
  `utama_line` cushion.py:525, `compose_tickets` ticket_composer.py:1190,
  `combo_multiplier` :386, `ticket_win_probability` :403, `decide`
  recheck.py:1256, `answer` qa.py:1702, `evaluate_leg`/`evaluate_ticket`
  live_status.py:329/:471, `detect_anomalies` live_anomaly.py:139,
  `nilai_wajar` analis.py:298, `bantalan_adaptif` analis.py:114,
  `rekomendasi_w` calibration.py:70, `hasilkan_usulan` proposals.py:102).
- **Klaim ketiadaan (grep kosong):** tidak ada sistem vonis HIJAU/KUNING di
  `engine/` + `report/`; tidak ada fungsi audit tiket riil di `cli.py` +
  `engine/` + `report/`; `compose_tickets` tidak membaca jam tip-off.
- **`edge` dicatat tapi tidak dipakai seleksi:** hanya 2 kemunculan `edge`
  di `ticket_composer.py` (field di daftar + pencatatan di baris 1046),
  tidak ada di `_pilih_subset` — klaim pekerja B terkonfirmasi.
- **`p_total_loss` tidak dihitung:** docstring `ticket_composer.py:96`
  menyatakan eksplisit. Config optimizer (`sort_by:
  ["p_total_loss_asc", "combined_ev_desc"]`, `top_options: 3`) ada di
  playstyle.yaml, tapi `optimizer/tickets.py` tidak dipanggil
  `compose_tickets` — klaim pekerja A terkonfirmasi.
- **Config:** `w_model: 0.3`, `total_gap_points: 5.0`, `min_leg_prob`
  0,74/0,65, `yakin_min_leg_prob: 0,75` — semua sesuai klaim pekerja.
- **Nuansa yang koordinator perbaiki dari draf pekerja:** (a) inkonsistensi
  garis OKC 3 poin mungkin mencerminkan pergerakan pasar selama ~30 menit,
  bukan semata kesalahan — yang tetap berdiri adalah "basis tidak
  dinyatakan / mencampur basis" (§4.2 Temuan 2); (b) klaim pekerja C bahwa
  angka 76,6% / OT 3,8% / kaki Utama "tidak terlacak" hanya berlaku untuk
  REFERENSI file — ketiganya ada di transkrip lengkap dan sudah
  dikonfirmasi di atas.

## 9. Catatan metode & batasan

- **Studi desain saja.** Tidak ada kode/config yang diubah. Semua usulan di
  §6 menunggu keputusan user (§7) sebelum implementasi apa pun.
- **Transkrip satu pagi.** Analisis ini memakai satu percakapan (23 Nov
  2026, 6 laga). Cara kerja Gemini di malam lain bisa berbeda; pola yang
  diekstrak (§2) adalah pola dari satu contoh yang kaya, bukan dari
  pengamatan berulang.
- **Tidak ada verifikasi ke sumber luar.** Kebenaran angka Gemini terhadap
  data nyata (apakah SGA benar-benar OUT, apakah proyeksi 212,3 akurat)
  TIDAK diuji — yang diuji hanya konsistensi internal dan cara kerjanya.
  Bila angka Gemini ternyata salah secara faktual, temuan di §4 tidak
  berubah (aritmetika turunannya tetap koheren), tapi nilai "edge" yang ia
  klaim bisa runtuh — alasan tambahan untuk tidak menyalin mesin hitungnya.
- **Hasil laga pagi ini belum diketahui** saat laporan ini ditulis (tiket
  masih LIVE saat screenshot 05:51/05:57 WIB). Apakah racikan Gemini menang
  atau kalah adalah data kalibrasi masa depan, bukan bagian dari analisis
  ini.
- **Hutang lama yang tetap terbuka** (dari langkah sebelumnya): persetujuan
  fit bola, ratifikasi FPL + sumber cedera bola kedua, signup DunkAPI,
  min_leg_prob 0,74 (gate keras vs lunak), kenaikan w, batas harga
  pendakian (pertanyaan terbuka dari LAPORAN-PERBAIKAN-RACIK), batas atas
  Asuransi 3,0 + kriteria "yakin" x5 (menunggu keberatan).
- **File kerja pekerja** (bukan bagian repo, tersimpan di `/tmp`):
  `analisis_gemini_A_inventaris.md` (inventaris kemampuan mesin, 882 baris),
  `analisis_gemini_B_kesenjangan.md` (tabel kesenjangan + usulan + pertanyaan),
  `analisis_gemini_C_konfirmasi.md` (cek konsistensi + penantang). Bila
  dibutuhkan kembali, minta koordinator menyalinnya ke repo.
