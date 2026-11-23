# REKAP MESIN PARLAY — UNTUK AUDIT GEMINI

**Tanggal:** 2026-11-23 (sore WIB) · **Dari:** Muse (yang membangun mesin)
**Untuk:** Gemini (analis senior user) — diminta user untuk mengaudit
mesin ini dan memberi saran perbaikan dari ingatan + pengalamanmu
meracik tiket.

**Konteks singkat.** User membangun mesin analis parlay NBA (bukan bot
otomatis — user pasang tiket sendiri di jup.ag). Mesin menganalisis
slate, meracik Tiket Asuransi (target x2+) + Tiket Utama (target x3+),
user yang memutuskan dan memasang. Kamu selama ini analisnya user
(winrate ~90% menurut user, baru kalah sekali — 23 Nov pagi, kedua
tiket mati karena satu kaki Denver yang ada di kedua tiket). Mesin ini
dibangun untuk memberi penilaianmu badan yang kaku: vonis yang
ditegakkan kode, bukan ingatan.

**Yang user minta darimu:** audit rekap ini, jawab 10 pertanyaan di §6,
dan beri saran apa yang harus diubah agar mesin ini lebih sempurna.
Fokusnya: mesin ini TERLALU KETAT — hampir semua laga ditandai KUNING
(lihat §4), sehingga user tidak bisa main dengan tenang.

---

## 1. Prinsip mesin (tidak bisa dilanggar)

1. Semua angka (probabilitas, simulasi, EV, pengali) harus dari kode
   Python — LLM tidak boleh mengarang angka.
2. Data gagal diambil → laga ditandai DATA_INCOMPLETE, tidak boleh
   masuk tiket; tidak pernah mengisi data kosong dengan tebakan.
3. Hanya sumber data gratis. API key di `.env`, tidak pernah
   ditampilkan/di-commit.
4. Semua ambang (threshold) + default strategi HANYA di
   `config/playstyle.yaml` (saat ini v17). Perubahan parameter harus
   lewat perubahan config berversi + persetujuan user (pola D12).
5. Mesin TIDAK PERNAH mengubah parameter sendiri (self-learning hanya
   mengusulkan).
6. Harga pasar = penguat + alat cek harga, BUKAN hakim. Selisih besar
   model-vs-pasar = alasan menyelidiki, bukan otomatis mengikuti pasar.
7. Satu-satunya jalan masuk: `cli.py` (analyze / recheck / racik /
   audit / pantau / laporan / tanya / log / belajar).

## 2. Alur kerja (workflow)

```
analyze (per laga) → simulasi 100.000x → vonis → equilibrium
  → racik (Asuransi + Utama) → audit SEBELUM pasang → pantau live
  → hasil masuk ledger (untuk kalibrasi)
```

- **analyze**: tarik data (statistik tim, pemain, cedera 2 sumber,
  berita, tangga harga Polymarket, pembanding Kalshi/Odds API),
  simulasikan 100.000x, hitung kaki Alt Under Asuransi + Utama.
  Lambat: ~3,5 menit/laga (sebagian besar pemindaian jup.ag).
- **recheck** (pra-submit): tarik ulang data segar, bandingkan dengan
  analisis, simulasi ulang bila ada perubahan material, beri vonis
  per kaki (TETAP_OK / PERHATIAN / JANGAN_PASANG) + GO/NO-GO tiket.
- **racik**: susun Asuransi + Utama dari kaki yang lolos gate.
- **audit**: audit tiket NYATA (dari screenshot/file tiket user)
  sebelum dipasang — per kaki + agregat tiket.
- **pantau**: lacak tiket live (proyeksi total akhir dari laju live +
  median pra-laga; status AMAN/WASPADA/TERANCAM/MENANG/KALAH; deteksi
  anomali: hujan tripoin, FT berlebihan, laju skor tinggi).
- **ledger**: semua hasil tiket dicatat (menang/kalah per kaki) untuk
  kalibrasi. Saat ini baru 10 kaki nyata (8 menang, 2 kalah — keduanya
  kaki Denver 23 Nov).

## 3. Logika per bagian (dengan ambang persisnya)

### 3.1 Simulasi (otak NBA)
- Proyeksi dari rating tim (ORtg/DRtg/Pace/NetRtg, musim + 10 laga
  terakhir, disesuaikan lawan) + dampak pemain (BPM × menit, dengan
  level pengganti −2,0 + penyusutan ke musim lalu) + form5 + kandang/
  tandang + istirahat/B2B + ketinggian (Denver/Utah, efek terukur
  hampir nol: −0,0105) + cedera dari 2 sumber.
- Distribusi Student-t (nu 35,0); sigma_total 18,9868; sigma_margin
  14,4307; home +1,6639; B2B −1,5164 — semua FIT dari 2.701 laga
  (rolling, tanpa look-ahead). OT: 5 menit tambahan bila imbang.
- Semua pasar dinilai dari SATU simulasi yang sama (korelasi terhitung).
- Validasi: Brier home-win 0,198 (vs klimatologi 0,244) — model punya
  skill di moneyline; di total Under, model BELUM terbukti lebih baik
  dari pasar (Brier ≈ klimatologi). Ini alasan aturan lean-to-market
  di bawah.

### 3.2 Harga + blend
- p_model (sim) + p_pasar (pembanding: sportsbook devig → ESPN odds →
  Kalshi; Polymarket BUKAN pembanding untuk pasar asal Polymarket)
  diblend: p_final = 0,7 × p_model + 0,3 × p_pasar (w = 0,3, akan
  dikalibrasi dari data tiap 50 kaki).
- Label harga dari EV vs harga jup.ag: DISKON (EV ≥ +2%), WAJAR
  (−2% s.d. +2%), MAHAL (< −2%). MAHAL tidak boleh masuk Asuransi.
- **Lean-to-market:** bila |median model − garis pasar| > 5,0 poin DAN
  tidak ada alasan konkret, keputusan Asuransi memakai probabilitas
  PASAR; bila probabilitas pasar < 74%, kaki tidak lolos Asuransi.
- **Kenapa beda?:** bila |model − pasar| > 8 poin, laporan WAJIB berisi
  penjelasan (pasar tahu sesuatu / model salah / tidak ditemukan alasan).

### 3.3 Bantalan adaptif + equilibrium
- Bantalan (cushion) dihitung per laga dari data (bukan +8 kaku):
  `clamp(std_sim×0,42 + (ortg_rata−ortg_liga)×0,5 + (total_5laga−
  total_musim)×0,25, 4–20)`. Bobotnya INITIAL (belum terkalibrasi).
- **Equilibrium** = titik paling manis per kaki. Utama: max-ER
  (p_final × 100/harga). Asuransi: safety-first (p_final TERTINGGI di
  antara garis yang lolos semua gate). Garis dipilih dari volatilitas
  dulu, baru cek harga — BUKAN hitung mundur dari target pengali
  (pelajaran dari pengakuanmu soal 252,5/250,5).
- Lantai harga 75¢; TIDAK ADA price cap (harga 89¢ bahkan 94¢ boleh
  bila statistik mengizinkan — keputusan user 23 Nov 08:19 WIB).
- Target pengali: Asuransi x2–2,5; Utama x3–5 (lunak 3,5; di atas
  3,5 butuh semua kaki "yakin", p_final ≥ 0,75).

### 3.4 Gate (semua harus lolos untuk masuk tiket)
- Asuransi: p_final ≥ 0,74; edge (p_final − harga) ≥ 3,5%
  (PROPOSAL D12, belum disetujui user — titik tengah dari insiden
  Denver: edge Denver +2,5% kalah, edge OKC +4,4% menang);
  lolos skenario banjir (P ≥ 74% di bawah banjir terburuk);
  volume per garis ≥ $100 (tipis = BLOKIR untuk Asuransi).
- Utama: p_final ≥ 0,65; tanpa gate banjir/edge (banjir hanya
  peringatan); volume tipis hanya peringatan.
- **Tanpa kaki kembar:** satu laga tidak boleh ada di kedua tiket
  (keputusan user 23 Nov 12:20 — pelajaran langsung dari Denver yang
  ada di kedua tiket dan membunuh keduanya).
- **Skip dari awal:** laga yang tidak masuk akal / potensi OT tinggi
  di-skip dari kedua tiket (bukan dipaksa masuk di garis lebih tinggi).
  OT ≥ 2,8% → skip. Pola Denver (kaki lolos normal tapi jebol di
  deviasi maksimal + tidak ada garis tidak-tipis yang tahan banjir +
  edge < 3,5%) → skip.

### 3.5 Skenario panas (banjir + setan)
- **Banjir:** geser CDF total. Nilai FIT dari 247 game log, lalu
  DIBETULKAN ke data bersih (n=243, tanpa 4 laga berjalan): banjir
  3P +8,50 poin; banjir FT +12,52 poin (p90). Sebelumnya 13,54/17,54
  (tercemar).
- **Setan umum:** deviasi maksimal 3P dari data musim: +18,07 poin
  (maks 40 tripoin gabungan/laga). Hanya DETEKSI (flag), bukan gate —
  keputusan user (kalau semua dianggap anomali, tidak ada yang
  dimainkan).
- **Setan per pemain (BARU, v17):** tiap pemain (semua terdaftar +
  rotasi, bukan cuma starter) dihitung: percobaan 3P yang diharapkan
  (memperhitungkan siapa yang benar-benar main; pemain OUT → 0;
  < 10 menit/laga → tidak dihitung) × % 3P TERBAIK liga musim ini
  (54,1%, Cam Spencer, MEM — syarat ≥ 50 total percobaan 3P).
  Total setan tim = (total normal − poin 3P normal) + poin 3P setan.
  Denver: 274,14 (median 233; garis bandar 236,5; jadi +37,64 dari
  garis bandar). Aktual 296 — demon TIDAK memodelkan lonjakan JUMLAH
  percobaan (aktual 90 vs 67,3 yang diharapkan). Kedua kaki Denver
  ter-flag rapuh (P setan 13,0% / 11,8%).

### 3.6 Sistem vonis (BARU, v17) — INI YANG BERMASALAH
Vonis per laga dari DATA: **HIJAU** (sehat → kandidat Asuransi),
**MENENGAH_HIJAU** (cukup sehat → kandidat Utama), **KUNING**
(lempar koin → skip dari kedua tiket). Sistem demerit atas 9 indikator
pelajaran Denver + 4 pemicu keras:

**9 demerit** (masing-masing 1 poin; ambang di config, semua INITIAL):
1. edge kecil (< 2,5%)
2. P banjir lemah (< 74%)
3. P setan lemah (< 65%)
4. volume tipis (< $100)
5. volume tidak diketahui
6. gap model-vs-pasar kecil (< 4,0 poin) — tidak ada edge
7. gap model-vs-pasar besar (> 8,0 poin) — model dicurigai salah
8. sinyal ekor gemuk (garis Asuransi ≥ 10 poin dari total pasar DAN
   harga ≤ 85¢ — pasar bilang ekornya gemuk)
9. total tinggi (garis bandar ≥ 235,0)

**4 pemicu keras** (langsung KUNING): data tidak cukup; OT tinggi
(≥ 2,8%); edge tidak positif; **veto rim protector**.

**Aturan vonis:** HIJAU = 0 demerit; MENENGAH_HIJAU = 1–4 demerit;
KUNING = > 4 demerit ATAU pemicu keras.

**Veto rim protector** (dari bedah jujurmu — TERVERIFIKASI dari data
mesin: Claxton OUT vs Jokic, 2 sumber): rim protector utama OUT
terkonfirmasi (2 sumber) + garis pasar ≥ 235,0 ATAU pace ≥ 102,0 →
veto menyala → KUNING, tidak bisa dikalahkan skor EV. Rim protector
= top-2 blok per laga per tim (GP ≥ 3, menit ≥ 15, blok ≥ 0,8) dari
stats.nba.com, disimpan di `config/rim_protector_2026-27.json`
(30/30 tim). Veto memblokir KEDUA tiket (lebih ketat dari
usulanmu yang hanya Asuransi — keputusan desain yang menunggu
keberatan). Catatan: definisi top-2 BPG menamai guard di tim yang
bloknya lemah (mis. Jamal Murray di DEN, Haliburton di IND) — proksi
kasar, bukan penilaian bola basket.

## 4. Hasil pengukuran (skor jujur mesin ini)

### 4.1 Vonis vs hasil nyata — slate 23 Nov pagi (6 laga)
Data dari artefak tersimpan (7 laga live 22 Nov + 3 verif; 10 baris):

| Laga | Vonis mesin | Alasan utama | Hasil nyata |
|---|---|---|---|
| OKC@MIA | KUNING | Veto (Holmgren OUT + pace 102,19) | MENANG (total 236) |
| DEN@CHI | KUNING | Veto (Claxton OUT + garis 236,5 + pace 103,22) + 7 demerit | KALAH (total 296, OT) |
| DAL@UTA | MENENGAH_HIJAU | 4 demerit (banjir/setan lemah, volume tipis, gap besar) | MENANG (230) |
| ORL@WAS | KUNING | 6 demerit | MENANG (212) |
| IND@NYK | KUNING | 5 demerit | MENANG (219) |
| BOS@GSW | KUNING (verif) / MENENGAH (live) | 6 demerit di verif | MENANG (175) |

**Distribusi vonis: HIJAU 0 / MENENGAH 2 / KUNING 8 (dari 10 baris).**
**Skor vonis: 1 true positive (Denver) vs 4 false positive** (OKC, ORL,
IND, BOS-verif — semuanya ditandai KUNING padahal kaki Under-nya
menang). DET@ATL juga KUNING (OT tinggi) — final 204, kakinya akan
menang juga.

**Tiket yang dibentuk mesin di slate ini: TIDAK ADA.** Asuransi 0
kandidat; Utama hanya DAL (maks x1,22, di bawah target x3) → mesin
menolak membentuk tiket (NO BET). Hasil mesin: $0. Hasil tiketmu
(Gemini): −$30 (kedua tiket kalah karena Denver). Hasil "pasang semua
pemenang": akan menang besar. **Mesin menyelamatkan $30 tapi melewatkan
semua pemenang.**

### 4.2 Asuransi tidak pernah terbentuk (temuan struktural)
Di SEMUA pengukuran (v13–v17, slate uji 10 baris): **Equilibrium
Asuransi 0/10.** Mekanismenya struktural: gate banjir mendorong harga
naik (garis tahan banjir lebih mahal) → edge mengecil secara mekanis →
garis yang lolos banjir gagal edge (satu-satunya baris yang lolos
banjir, OKC verif 82,1%, gagal edge +1,3% < 3,5%) → garis yang tersisa
tipis volumenya. Koreksi banjir ke data bersih (8,50/12,52) TIDAK
mengubah hasil. Volume SATU-SATUNYA penghalang hanya di 1/10 baris —
melonggarkan ambang $100 saja TIDAK akan membentuk Asuransi.
**Tidak ada yang dilonggarkan diam-diam** — semua ambang di atas tetap
seperti yang diputuskan user.

### 4.3 Yang mesin lakukan dengan benar
- Menangkap Denver sebagai laga paling berbahaya SEBELUM laga (audit
  mesin menandai Denver kaki terlemah: P 84,5%, edge +2,5% terkecil).
- Audit tiket nyata 23 Nov memberi Asuransi NO-GO (Denver
  JANGAN_PASANG) — benar, tiket itu kalah.
- Setan per pemain (274,14) jauh lebih dekat ke aktual (296) daripada
  setan umum (251,07), dan menandai kedua kaki Denver sebagai rapuh.
- Tidak pernah memaksa tiket demi pengali (fail-closed).
- Semua angka bisa dilacak ke perhitungan (tidak ada angka karangan).

## 5. Kritik jujurku terhadap mesinku sendiri (Muse)

User memintaku jujur dulu sebelum bertanya padamu. Ini diagnosis
biasnya, sejujur yang aku bisa:

**1. Mesin ini dibangun dari SATU kekalahan.** Hampir semua gate,
demerit, dan veto lahir dari insiden Denver 23 Nov. Setiap pelajaran
dari kekalahan itu menjadi aturan keras. Akibatnya mesin melihat Denver
di mana-mana — ia disetel untuk menghindari bencana terakhir, bukan
untuk menemukan pemenang. Itu biasnya.

**2. HIJAU = 0 demerit adalah standar kesempurnaan, bukan standar
bertaruh.** Hampir tidak ada laga yang sempurna: volume garis jauh
SELALU tipis (itu sifat bursa, bukan cacat laga), P banjir di bawah
74% adalah hal biasa untuk garis yang wajar, dan seterusnya. Jadi
0 HIJAU adalah sistem yang bekerja sesuai desain — tapi desainnya
salah untuk tujuannya. User butuh "cukup bagus untuk main dengan
tenang", bukan "sempurna".

**3. Demerit menghitung ganda fakta yang sama.** Banjir-lemah +
setan-lemah + volume-tipis + edge-kecil sering menyala BERSAMAAN di
laga yang sama untuk alasan mendasar yang sama (garisnya rendah /
laganya biasa saja). Satu fakta menjadi 3–4 demerit, dan 5 demerit
sudah cukup untuk KUNING. Indikator-indikator ini berkorelasi, tapi
sistem memperlakukannya sebagai independen.

**4. Ambangnya tebakan, bukan kalibrasi.** Semua ambang vonis berstatus
INITIAL — ditetapkan dari satu insiden + intuisi, tidak pernah diuji
terhadap hasil nyata. Sampel 10 baris membuktikan miskalibrasi (5 dari
6 laga KUNING menang), tapi 10 baris juga terlalu kecil untuk
kalibrasi yang benar. Ledger baru punya 10 kaki nyata.

**5. Logika veto OR terlalu lebar.** Veto menyala bila garis ≥235 ATAU
pace ≥102 (salah satu cukup). OKC kena veto dari pace saja (garis
231,5 < 235) padahal kakinya menang. Dengan logika AND (kedua kondisi),
Denver tetap ketangkap dan OKC lolos. Aku tidak tahu mana yang benar —
itu yang perlu diuji.

**6. Yang mesin lakukan dengan benar (jangan dibuang):** menangkap
Denver; setan per pemain; tanpa-kembar; audit yang jujur; simulasi yang
solid; fail-closed. Masalahnya bukan mesinnya tidak bisa menghitung —
masalahnya ambang vonisnya tidak dikalibrasi untuk membedakan "bahaya"
dari "biasa".

**Arah perbaikan versiku (untuk kamu nilai, bukan keputusan):**
(a) kalibrasi vonis terhadap hasil nyata di ledger (bukan dari
intuisi); (b) gabungkan demerit yang berkorelasi menjadi SATU skor
kerapuhan, bukan 3–4 demerit terpisah; (c) HIJAU = "cukup bagus"
(mis. ≤1–2 demerit, dengan pemicu keras — veto, OT, edge negatif —
tetap absolut); (d) uji veto AND vs OR terhadap data; (e) bedakan
"tidak ada tanda bahaya" dari "terbukti aman" — HIJAU harus berarti
yang kedua.

## 6. Pertanyaan untuk Gemini (10)

1. **Kalibrasi HIJAU.** Dari pengalamanmu meracik tiket yang menang,
   berapa laga per slate yang benar-benar HIJAU (layak Asuransi)? Di
   slate 6 laga kemarin, berapa yang menurutmu HIJAU? (Mesin kami:
   0 dari 10 baris.)
2. **Demerit mana yang terlalu ketat?** Dari 9 indikator demerit kami
   (§3.6), mana yang menurutmu harus dilonggarkan, digabung, atau
   dibuang? Dan indikator apa yang KAMU pakai tapi TIDAK ada di daftar
   kami?
3. **Veto AND vs OR.** Veto kami menyala bila rim protector OUT +
   (garis ≥235 ATAU pace ≥102). Ini menangkap Denver tapi juga
   memblokir OKC (yang menang). Menurutmu harus AND (kedua kondisi)
   atau tetap OR? Bagaimana kamu menimbang rim protector OUT vs
   faktor lain di laga itu?
4. **Asuransi yang tidak terbentuk.** Asuransi kami 0/10 — gate banjir
   menaikkan harga, edge mengecil, volume memblokir. Kamu membangun
   Asuransi dari target pengali (~82¢/kaki). Menurutmu pendekatan mana
   yang benar — dari volatilitas dulu (kami) atau dari harga dulu
   (kamu)? Bagaimana menyeimbangkan keamanan vs target x2?
5. **Memilih garis.** Kamu mengakui 252,5/250,5 adalah hitung mundur
   dari target pengali. Kalau membangun dari nol, bagaimana SEHARUSNYA
   aturan memilih garis? Dari distribusi? Dari harga? Kombinasi?
6. **Setan per pemain.** Kami menghitung total setan dari data pemain
   (Denver 274,14 vs aktual 296). Apakah kamu memakai perhitungan
   semacam ini? Bagaimana kamu menilai apakah sebuah laga bisa meledak?
7. **KUNING vs HIJAU dalam praktik.** Apa beda praktis antara laga yang
   kamu labeli KUNING vs HIJAU? Sinyal apa yang membuatmu YAKIN sebuah
   laga AMAN untuk Asuransi (bukan sekadar "tidak ada tanda bahaya")?
8. **Urutan kerja.** Urutan kami: cedera → pasar → konteks → sim →
   vonis → equilibrium → racik → audit. Urutanmu: injury scan → garis
   pasar → konteks → sim → tiering. Apa yang salah atau hilang dari
   urutan kami?
9. **Bermain dengan tenang.** User bilang kalau semua KUNING, dia
   tidak bisa main dengan tenang. Bagaimana kamu memberi vonis yang
   tegas tanpa over-warning? Kapan kamu berani bilang "laga ini aman,
   pasang"?
10. **Yang paling penting.** Jika kamu hanya boleh mengubah TIGA hal
    dari mesin ini, apa saja — dan kenapa?

## 7. Yang terjadi dengan jawabanmu

Jawabanmu akan dibawa user kembali ke Muse. Yang bisa diubah menjadi
data + aturan akan dilipat ke mesin (config berversi, tes, pengukuran
ulang di slate uji) — dengan persetujuan user untuk setiap perubahan
ambang. Yang tidak bisa diverifikasi dari data tidak akan dipakai
sebagai fakta. Angka-angka mesin tetap dari kode, bukan dari LLM
(mana pun LLM-nya).
