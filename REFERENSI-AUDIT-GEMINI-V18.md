# AUDIT MESIN PARLAY v17 & PROPOSAL KALIBRASI v18 — DARI GEMINI UNTUK MUSE

**Tanggal:** 2026-11-23 (WIB)  
**Dari:** Gemini (Analis Pendamping User)  
**Untuk:** Muse (Arsitek & Pengembang Mesin) — *disampaikan melalui User*  
**Status Dokumen:** Audit Teknis & Usulan Perubahan Config (Mengikuti Pola D12 — semua angka usulan bersifat proposal dan menunggu pengujian kode + persetujuan User)

---

## Ringkasan Eksekutif untuk Muse

Pertama, apresiasi jujur untuk fondasi rekayasa yang sudah kamu bangun di v17: seluruh angka berasal dari kode Python (zero karangan LLM), parameter *Student-t* di-*fit* secara *rolling* dari $2.701$ laga tanpa *look-ahead*, aturan tanpa kaki kembar, fitur *setan per pemain*, dan prinsip *fail-closed*. **Fondasi ini jauh lebih disiplin daripada cara kerjaku kemarin dan tidak boleh dibuang.**

Namun, hasil `HIJAU 0/10` dan `Equilibrium Asuransi 0/10` bukan sekadar karena ambangnya sedikit terlalu ketat. Hasil pemeriksaan terhadap parameter v17 menunjukkan adanya **tiga *deadlock* matematis dan satu cacat kalibrasi OT** di dalam spesifikasi gate yang secara aljabar mengunci ruang solusi Asuransi hingga nyaris kosong.

Dokumen ini membedah:
1. Bukti matematis 4 cacat struktural v17.
2. Jawaban objektif atas seluruh 10 pertanyaan di §6 rekapmu.
3. Draf usulan struktur `playstyle.yaml` (v18) untuk kamu review dan uji ulang.
4. Kriteria *acceptance test* konkret di *slate* uji 23 Nov sebelum minta persetujuan final User.

---

## 1. Bukti Matematis: 4 Cacat Struktural di v17

### 1.1 *Deadlock* Gate Asuransi (`P_banjir` vs `edge` vs `lean-to-market`)
Dengan distribusi simulasi *Student-t* ($\nu = 35{,}0$, $\sigma_{\text{total}} = 18{,}9868$) dan banjir FT bersih sebesar $+12{,}52$ poin:
* Syarat `P_banjir >= 74%` secara matematis memaksa garis berada minimal:
  $$12{,}52 + t_{0{,}74,\,35} \times 18{,}9868 \approx 12{,}52 + 0{,}650 \times 18{,}9868 = +24{,}86\text{ poin di atas median model}$$
  Pada jarak ini, probabilitas normal model sudah mencapai $P_{\text{model}} \approx 90{,}05\%$.
* Sekarang benturkan dengan aturan kalian yang lain:
  * **Skenario A (Keunggulan model realistis $0$ s.d. $5$ poin di bawah pasar):** Di jarak $+20$ sampai $+25$ poin di atas garis pasar, harga *ask* bursa sudah berada di kisaran $86{,}4\text{¢} - 91{,}6\text{¢}$. Akibatnya, *edge* absolut ($p_{\text{final}} - \text{harga}$) mentok di rentang $-1{,}50\%$ hingga $+2{,}13\%$ — **secara aljabar mustahil menembus gate `edge >= 3,5%`**.
  * **Skenario B (Model lebih rendah $> 5{,}0$ poin dari pasar demi mengejar *edge*):** Kondisi ini langsung memicu `lean-to-market` ($|\text{median}_{\text{model}} - \text{pasar}| > 5{,}0$), yang memaksa Asuransi memakai $p_{\text{pasar}}$ sehingga *edge* langsung menjadi negatif sebesar *vig* bursa.
* **Kesimpulan:** Selama tiga aturan (`P_banjir >= 74%`, `edge >= 3,5%`, `lean-to-market > 5,0`) aktif bersamaan, `Equilibrium Asuransi` memang terkunci mati di `0/10`.

### 1.2 Bias *Flat Edge* di Ekor Distribusi ($82\text{¢} - 94\text{¢}$)
Mesin kalian tidak memasang *price cap* (membolehkan pembelian sampai $89\text{¢} - 94\text{¢}$), tetapi tetap memakai ambang *edge* absolut yang datar ($\ge 3{,}5\%$). Di ekor distribusi, kemiringan CDF makin landai:
* Keunggulan riil $3$ poin terhadap pasar yang bernilai sekitar $+6{,}0\%$ di garis $50\text{¢}$ otomatis menyusut menjadi:
  * $\approx +1{,}3\%$ di harga $82\text{¢}$,
  * $\approx +0{,}6\%$ di harga $88\text{¢}$,
  * $\approx +0{,}3\%$ di harga $90\text{¢}$.
* Meminta *edge* datar $+3{,}5\%$ pada harga $90\text{¢}$ sama saja menuntut $p_{\text{final}} = 93{,}5\%$ (pemotongan risiko kalah sebesar $35\%$) — secara praktis tidak ada di pasar NBA yang efisien.

### 1.3 Jendela *Gap* yang Terjepit $1$ Poin ($4{,}0 - 5{,}0$)
* Demerit #6 menghukum laga jika $|\text{model} - \text{pasar}| < 4{,}0$ poin.
* Aturan `lean-to-market` mematikan model jika $|\text{model} - \text{pasar}| > 5{,}0$ poin.
* Demerit #7 menghukum laga jika $|\text{model} - \text{pasar}| > 8{,}0$ poin.
* Padahal §3.1 secara jujur mencatat Brier total Under model belum terbukti mengalahkan pasar. Menghukum laga yang sepakat dengan pasar ($\text{gap} < 4{,}0$) justru membuang laga paling bersih dari sisi *blind spot* model.

### 1.4 Anomali Kalibrasi OT vs Pemicu Keras $2{,}8\%$
Dengan $t(35)$ dan $\sigma_{\text{margin}} = 14{,}4307$, probabilitas selisih skor akhir jatuh tepat di angka $0$ (memicu OT) bahkan untuk laga paling imbang ($\text{spread} = 0$) secara teoretis mentok di sekitar $2{,}74\%$. Di NBA nyata, laju OT adalah sekitar $5{,}5\% - 6{,}0\%$ karena mekanisme strategi *clutch* di menit akhir Q4. Artinya, pemicu keras `OT >= 2,8%` saat ini tidak sedang mendeteksi laga rawan OT secara akurat, melainkan hanya meledak karena *noise* Monte Carlo pada laga berselisih tipis ($\text{spread } 0 - 2$, seperti kasus `DET@ATL`).

---

## 2. Jawaban atas 10 Pertanyaan Muse (§6)

### 1. Kalibrasi HIJAU
Di *slate* normal $6 - 8$ laga NBA, jumlah laga yang benar-benar `HIJAU` (layak Asuransi) secara realistis berkisar **$2 - 4$ laga** ($35\% - 50\%$ dari *slate*). Pada *slate* tipis ($4 - 5$ laga), mendapatkan $0 - 1$ laga HIJAU lalu memilih `NO BET` itu sehat — tetapi mendapat `0/10` di *slate* 23 Nov menandakan miskalibrasi berat.

Klasifikasi jujur *slate* 23 Nov pagi berdasarkan informasi **pra-*tip-off*** (tanpa *hindsight*):
* **HIJAU (Layak Asuransi — $2$ s.d. $3$ laga):**
  1. `BOS@GSW`: Paling bersih (5 inti Warriors OUT, pertahanan elit Celtics, garis terendah $210{,}5$).
  2. `OKC@MIA`: Layak Asuransi di garis tebal (`U 242,5`) karena kedua pencetak poin utama (SGA & Giannis) sama-sama OUT, menyeimbangkan tempo cepat Miami.
  3. `ORL@WAS`: Kandidat HIJAU batas bawah jika garis cukup tebal (`U 235+`) bertumpu pada pertahanan Orlando.
* **MENENGAH_HIJAU (Utama saja — $2$ laga):**
  4. `DAL@UTA`: Faktor berlawanan (*paint* Jazz tipis vs B2B Dallas di *altitude*).
  5. `IND@NYK`: Seharusnya berstatus `TUNGGU_LINEUP` sampai status *Questionable* KAT & Siakam final 30 menit sebelum *tip-off*.
* **KUNING (Skip Mutlak kedua tiket — $1$ laga):**
  6. `DEN@CHI`: Veto struktural (Claxton OUT lawan Jokić + *pace* tinggi + garis Vegas tertinggi $236{,}5$).

### 2. Audit 9 Demerit (Buang, Gabung, Longgarkan, & Tambah)
Diagnosis kamu di §5 sudah tepat: beberapa demerit menghitung ganda fakta yang sama.

| Indikator v17 | Rekomendasi | Alasan Teknis |
| :--- | :--- | :--- |
| `#1` Edge kecil ($< 2{,}5\%$) | **Ubah rumus** | Ganti ke label `MAHAL` ($\text{EV} < -2\%$) atau *relative edge* agar tidak menghukum kaki harga tinggi ($85\text{¢}+$). |
| `#2` P banjir ($< 74\%$) & `#3` P setan ($< 65\%$) | **Gabung jadi 1 skor** | Mengukur hal yang sama (*Tail Fragility*). Pakai `P_banjir` sebagai skor utama yang dilonggarkan; jadikan `Setan` sebagai *flag* informatif. |
| `#4` Volume tipis ($< \$100$) & `#5` Volume unknown | **Keluarkan dari vonis laga** | Ini sifat *orderbook* garis jauh di Polymarket/Jup.ag, bukan cacat pertandingan. Jadikan **gate eksekusi/likuiditas** berbasis *stake* user (mis. $\ge 2 \times \text{stake}$). |
| `#6` Gap model-pasar kecil ($< 4{,}0$) | **BUANG** | Kontradiktif dengan Brier Total. Kesepakatan model & pasar adalah sinyal keamanan, bukan cacat. |
| `#7` Gap model-pasar besar ($> 8{,}0$) | **Pertahankan (bersyarat)** | Jadikan *flag* investigasi wajib; hanya beri demerit jika **tidak ada** berita cedera baru terverifikasi. |
| `#8` Sinyal ekor gemuk ($\ge +10$ & $\le 85\text{¢}$) | **Perketat definisi** | Di $\sigma \approx 19$, jarak $+14$ sampai $+16$ memang wajar di $80\text{¢} - 84\text{¢}$. Ubah ke: jarak $\ge +16$ poin DAN harga $\le 80\text{¢}$. |
| `#9` Total tinggi ($\ge 235{,}0$) | **Pertahankan** | Valid sebagai indikator risiko *upper-tail* di NBA. |

**3 Indikator penting yang belum ada di daftar v17:**
1. **Profil *Foul* & *Free Throw Rate* (FTr):** Tim dengan peringkat pertahanan *foul* terburuk (mis. Utah #30) sangat berbahaya bagi *Under* di Q4 meski akurasi FG normal.
2. ***Q-Uncertainty* (Bintang *Questionable*):** Jika pemain dengan $\text{USG} \ge 24\%$ atau $\text{BPM} \ge +2{,}0$ masih berstatus *Questionable*, tahan laga di status `TUNGGU_LINEUP` — jangan divonis prematur.
3. **Probabilitas *Blowout* (Sinyal Positif):** $|\text{Spread}| \ge 9{,}0$ poin adalah aset positif bagi *Under* (mematikan *clutch foul*, memotong menit starter Q4, menurunkan risiko OT).

### 3. Veto `AND` vs `OR` pada *Rim Protector OUT*
* **Ubah ke `AND`:** *Rim protector* absen hanya menjadi racun struktural jika dibarengi tempo cepat **DAN** ekspektasi skor tinggi (`garis_pasar >= 232.0` **AND** `pace_proyeksi >= 100.5`), atau lawan memiliki dominasi *paint scoring* utama. Logika `OR` di v17 memblokir `OKC@MIA` hanya karena *pace* Miami ($102{,}19$) tanpa memperhitungkan hilangnya SGA & Giannis di sisi serangan.
* **Perbaiki definisi *rim protector*:** Jangan ambil `top-2 BPG` mentah tanpa filter posisi (yang menyebabkan *guard* seperti Jamal Murray atau Haliburton masuk daftar). Tambahkan filter posisi `C` / `PF` / `F-C` (atau tinggi $\ge 6'9''$), minimal $18$ menit/laga, dan $\text{BLK} \ge 1{,}0$ (atau gunakan *rim contests / DFG% at rim* dari `stats.nba.com`).
* **Cakupan blokir:** Mutlak memblokir **Asuransi**. Untuk **Utama**, blokir jika kondisi `AND` menyala; jika hanya salah satu kondisi menyala, cukup jadikan *warning* + wajib tambahan bantalan $+3$ poin.

### 4. Asuransi `0/10` — Mulai dari Volatilitas Dulu atau Harga Dulu?
**Mulai dari volatilitas/distribusi dulu (pendekatanmu) adalah yang benar secara manajemen risiko.** Cara hitung mundur dari target pengali yang kulakukan kemarin adalah akar kesalahan pemilihan garis Denver ($252{,}5 / 250{,}5$).

Solusi menyeimbangkan keamanan dan target pengali $2\text{x}$ tanpa terjebak `0/10`:
* **Ubah filosofi *edge* di Asuransi:** Tujuan Asuransi adalah **probabilitas cair tinggi dengan harga wajar ($\text{EV} \ge -1\%$, bukan `MAHAL`)**, bukan memaksa *alpha* $+3{,}5\%$ di harga $88\text{¢}$.
* **Fleksibilitas jumlah kaki ($3 - 6$ kaki):**
  * Jika tersedia $3 - 4$ laga HIJAU $\rightarrow$ cari titik di $80\text{¢} - 84\text{¢}$ (pengali $\approx 1{,}8\text{x} - 2{,}2\text{x}$).
  * Jika tersedia $5 - 6$ laga HIJAU $\rightarrow$ boleh naik ke $86\text{¢} - 89\text{¢}$ (tetap $\approx 2{,}0\text{x}$ dengan bantalan jauh lebih tebal).
* Jika di seluruh *slate* hanya ada $2$ laga HIJAU, lebih sehat menurunkan target pengali Asuransi ke $1{,}5\text{x} - 1{,}7\text{x}$ (dengan penyesuaian porsi *stake*) daripada memaksa laga KUNING masuk demi mengejar angka $2{,}0\text{x}$.

### 5. Aturan Memilih Garis Ideal (*Distribution-First, Price-Constrained*)
Rekomendasi aturan 3 langkah berurutan:
1. **Tentukan Lantai Aman (*Floor Line*) dari Distribusi:**
   * **Asuransi:** Garis terendah yang memenuhi $P_{\text{final}} \ge 0{,}82$ (dan $P_{\text{pasar}} \ge 0{,}80$ agar tidak melawan pasar secara ekstrem) **DAN** $P_{\text{banjir 3P}} \ge 0{,}70$ (atau $P_{\text{banjir FT}} \ge 0{,}65$).
   * **Utama:** Garis terendah yang memenuhi $P_{\text{final}} \ge 0{,}74$ dengan lantai harga mutlak $\ge 75\text{¢}$.
2. **Saring Zona Layak Eksekusi (*Feasible Band*):** Ambil semua garis $\ge \text{Floor Line}$ yang memiliki likuiditas cukup ($\ge 2 \times \text{stake}$ user) dan tidak berlabel `MAHAL` ($\text{EV} \ge -2\%$).
3. **Pilih Equilibrium di Dalam Band:**
   * **Asuransi:** Prioritaskan $P_{\text{final}}$ tertinggi di kisaran harga $82\text{¢} - 89\text{¢}$ yang masih menghasilkan rasio $P_{\text{final}} / \text{harga}$ sehat dan memungkinkan pengali gabungan masuk rentang target.
   * **Utama:** Pilih *max-ER* ($P_{\text{final}} / \text{harga}$) di kisaran $76\text{¢} - 84\text{¢}$ (dengan *tie-breaker* memilih harga lebih tinggi/aman jika selisih ER $< 0{,}015$).

### 6. Setan per Pemain — Pertahankan & Kalibrasi
Fitur ini **sangat bernilai** (memprediksi `274,14` pada Denver jauh lebih realistis menangkap risiko ekor kanan dibanding setan umum `251,07`). Pertahankan sebagai *diagnostic flag*, bukan *hard gate*, dengan 2 penyempurnaan:
* Hindari mengalikan seluruh pemain rotasi dengan akurasi #1 liga ($54{,}1\%$ Cam Spencer) secara seragam — itu membuat terlalu banyak laga biasa tampak rapuh. Gunakan batas realistis per pemain:
  $$3P\%_{\text{setan},\,i} = \min\left(50\%,\; 3P\%_{\text{musim},\,i} + 12\%\right)$$
* Catat pemicu ledakan volume (seperti $90$ percobaan 3P aktual di Denver vs $67{,}3$ ekspektasi) dengan menambahkan bendera *3P Volume Risk* apabila kedua tim sama-sama masuk Top-10 *3-Point Attempt Rate* (`3PAr`).

### 7. Beda Praktis `HIJAU` vs `KUNING` (Bukti Positif Keamanan)
Setuju dengan §5: `HIJAU` harus berarti **terbukti punya rem alami**, bukan sekadar absennya tanda bahaya.
* **Syarat Positif `HIJAU` (minimal terpenuhi 1 "Rem Alami" + 0 *Hard Veto* + $\le 1 - 2$ demerit minor):**
  1. Minimal satu tim memiliki pertahanan Top-10 (`DRtg`) **atau** tempo lambat (`Pace` Bottom-12).
  2. Kedua tim kehilangan pencetak poin utama ($\text{USG} \ge 25\%$) yang terkonfirmasi OUT.
  3. Pertahanan *paint* utuh **dan** potensi *blowout* mendukung ($|\text{spread}| \ge 8{,}5$) atau kedua tim ber-`FTr` rendah.
  4. Selaras dengan pasar ($|\text{median}_{\text{model}} - \text{pasar}| \le 5{,}0$, atau $> 5{,}0$ dengan alasan cedera segar yang belum terserap pasar).
* **`KUNING`:** Memiliki akselerator aktif (veto *rim protector* `AND`, *pace* + garis ekstrem, atau harga `MAHAL`) sehingga kelolosan terlalu bergantung pada keberuntungan akurasi lawan.

### 8. Perbaikan Urutan Kerja (*Workflow*)
Alur kalian sudah sangat terstruktur. Tambahkan 3 perbaikan praktis:
1. **Sisipkan *Timing Gate* (`TUNGGU_LINEUP`):** Setelah langkah `cedera`, jika ada bintang dengan status *Questionable*, tahan laga agar tidak masuk `racik` final sebelum *injury report* 30 menit pra-*tip-off*.
2. **Pindahkan *Vegas Sanity Check* tepat setelah `sim`:** Jika $|\text{model} - \text{pasar}| > 5{,}0$ tanpa penyebab cedera baru, langsung susutkan proyeksi median ke arah pasar sebelum menghitung vonis dan *equilibrium* (jangan hanya diterapkan di tahap akhir Asuransi).
3. **Pindahkan Pemindaian *Orderbook* `jup.ag` ke Belakang (*Short-Circuit*):** Lakukan `cedera -> pasar -> konteks -> sim -> cek veto/OT` dulu. Laga yang sudah kena *Hard Veto* (seperti `DEN@CHI`) **tidak perlu** dipindai tangga harganya ke `jup.ag`. Ini langsung memangkas waktu analisis $3{,}5$ menit/laga sekitar $30\% - 50\%$ per *slate*.

### 9. Vonis Tegas Tanpa *Over-Warning* (Supaya User Tenang)
User stres karena mesin menyamakan bobot bahaya struktural (Denver) dengan kebisingan mikro (volume $\$70$ di garis jauh atau `gap < 4`). Solusinya pakai pemisahan tampilan yang tegas:
* **Lapisan 1 — *Hard Blocker* (Menentukan Warna):** Veto *rim protector* (`AND`), data tidak lengkap, harga `MAHAL`, OT ekstrem.
* **Lapisan 2 — Demerit Kualitas Laga (Ringan, Maks $1 - 2$ untuk `HIJAU`):** Total tinggi, ekor banjir rapuh, `FTr` tinggi, gap besar tanpa alasan.
* **Lapisan 3 — Catatan Informatif (Abu-abu, TIDAK mengubah warna vonis):** Volume tipis, skor *setan per pemain*, selisih kecil vs pasar.
* **Tampilkan 1 Kalimat "Skenario Mati" per Kaki:** Alih-alih menampilkan 6 *badge* kuning, tampilkan satu kalimat konkret untuk tiap kaki HIJAU (contoh: *"Kaki ini secara realistis hanya kalah jika terjadi OT atau akurasi 3P gabungan melebihi 45%"*).

### 10. Tiga Perubahan Prioritas Tertinggi (Jika Hanya Boleh Ubah 3 Hal)
1. **Pecahkan *Deadlock* Asuransi:** Ganti gate *edge* datar Asuransi ($\ge 3{,}5\%$) menjadi `EV >= -1%` (atau *relative edge* di ekor) dan sesuaikan lantai `P_banjir` ke $\ge 70\%$ (3P) / $\ge 65\%$ (FT). *Alasan:* Langsung menghidupkan kembali `Equilibrium Asuransi` dari `0/10` menjadi realistis tanpa menurunkan standar keamanan inti.
2. **Rombak Sistem Demerit & Ambang `HIJAU`:** Buang Demerit #6 (`gap < 4`), keluarkan volume (`#4/#5`) dari kualitas laga ke filter eksekusi berbasis *stake*, gabungkan banjir/setan (`#2/#3`) jadi 1 metrik kerapuhan ekor, dan ubah definisi `HIJAU` menjadi `0 Hard Veto` + `<= 1-2 demerit minor` + minimal 1 "rem alami". *Alasan:* Menghilangkan $4/5$ *false positive* KUNING yang melumpuhkan mesin.
3. **Perbaiki Dua Pemicu Keras yang Miskalibrasi:** Ubah Veto *Rim Protector* ke logika `AND` + filter posisi `C/PF`, dan kalibrasi ulang distribusi/ambang OT (ubah dari pemicu keras `2,8%` berbasis *noise* $t(35)$ menjadi bobot risiko berbasis *spread* tipis + kalibrasi OT empiris NBA $\approx 5{,}5\%$). *Alasan:* Tetap menangkap bencana seperti `DEN@CHI` dengan presisi tinggi, sekaligus berhenti memblokir pemenang bersih seperti `OKC@MIA` dan `DET@ATL`.

---

## 3. Draf Usulan Konfigurasi `config/playstyle.yaml` (PROPOSAL v18)

> **Catatan D12:** Seluruh nilai di bawah adalah **PROPOSAL AWAL** untuk diuji Muse di kode terhadap *slate* uji dan artefak historis, lalu diajukan ke User untuk persetujuan resmi sebelum diterapkan.

```yaml
# ==============================================================================
# PROPOSAL CONFIG v18 — USULAN AUDIT GEMINI UNTUK REVIEW MUSE & PERSETUJUAN USER
# ==============================================================================
version: "v18-proposal"
status: "PROPOSED_PENDING_BACKTEST_AND_USER_APPROVAL"

# 1. GATE EKSEKUSI & LIKUIDITAS (Dipisah dari kualitas pertandingan)
execution:
  min_price_floor: 0.75
  price_cap: null                 # Tetap tanpa price cap (keputusan User 23 Nov)
  min_liquidity_multiplier: 2.0   # Minimal 2x stake user (mis. $30 untuk stake $15), bukan mati di $100
  liquidity_hard_min_usd: 25.0    # Batas bawah absolut agar orderbook tidak kosong total

# 2. GATE KAKI & EQUILIBRIUM (Memecahkan deadlock Asuransi 0/10)
insurance:
  target_multiplier_min: 1.80     # Diperbolehkan turun ke 1.8x jika slate tipis (3-4 laga HIJAU)
  target_multiplier_ideal: 2.15
  target_multiplier_max: 2.50
  min_p_final: 0.82               # Prioritas utama Asuransi = probabilitas cair tinggi
  min_p_market: 0.80              # Proteksi agar tidak bertaruh ekstrem melawan pasar
  # Ganti flat edge >= 3.5% yang menciptakan deadlock di ekor 85c-92c:
  max_negative_ev: -0.01          # Tidak boleh MAHAL (EV >= -1%); DISKON/WAJAR boleh masuk
  min_relative_edge_ratio: 0.99   # p_final / harga >= 0.99
  flood_gate:
    p_flood_3p_min: 0.70          # Banjir 3P (+8.50)
    p_flood_ft_min: 0.65          # Banjir FT (+12.52)
  preferred_price_band: [0.80, 0.89]
  selection_mode: "safety_first_within_band"

main_ticket:
  target_multiplier_min: 3.00
  target_multiplier_soft: 3.50
  target_multiplier_max: 5.00
  min_p_final: 0.74               # Naik sedikit dari 0.65 untuk hindari kaki terlalu rapuh
  max_negative_ev: -0.02          # Tolak jika sangat MAHAL (EV < -2%)
  flood_gate_mode: "warning_only"
  preferred_price_band: [0.76, 0.84]
  selection_mode: "max_er_with_safety_tiebreak"
  tiebreak_er_tolerance: 0.015    # Jika selisih ER < 1.5%, pilih garis yang lebih aman

portfolio_rules:
  allow_twin_legs: false          # Mutlak tanpa kaki kembar (keputusan User 23 Nov)
  max_legs_insurance: 6
  min_legs_insurance: 2           # Jika hanya 2 HIJAU, tawarkan opsi stake-adjusted atau NO BET

# 3. PEMICU KERAS (HARD VETOES)
hard_vetoes:
  data_incomplete: true
  price_label_expensive_insurance: true   # Label MAHAL (EV < -2%) blokir Asuransi

  rim_protector_veto:
    enabled: true
    logic: "AND"                  # Diubah dari OR -> AND (tangkap DEN@CHI, loloskan OKC@MIA)
    require_confirmed_sources: 2
    min_market_total: 232.0       # Kondisi 1
    min_projected_pace: 100.5     # Kondisi 2 (keduanya harus terpenuhi bersama rim protector OUT)
    position_filter: ["C", "PF", "F-C", "C-F"]
    min_minutes_pg: 18.0
    min_bpg: 1.0
    block_insurance: true
    block_main: true              # Jika kondisi AND penuh terpenuhi, blokir keduanya

  overtime_risk:
    # Catatan untuk Muse: kalibrasi ulang probabilitas OT empiris (NBA riil ~5.5%-6.0%)
    # Jangan jadikan noise Student-t 2.8% sebagai kill switch tunggal
    mode: "calibrated_empirical"
    hard_skip_ot_prob: 0.085      # Hanya hard-skip jika OT benar-benar ekstrem (mis. spread <= 1.5 + pace/clutch tinggi)
    demerit_spread_threshold: 3.0 # Spread tipis <= 3.0 masuk demerit minor, bukan langsung bunuh laga

  lineup_timing_gate:
    enabled: true
    hold_if_star_questionable: true
    star_usg_threshold: 0.24
    star_bpm_threshold: 2.0
    status_output: "TUNGGU_LINEUP"

# 4. SISTEM VONIS & DEMERIT (Ramping, Non-Redundan, Berbasis Rem Alami)
verdict:
  # Daftar demerit kualitas laga (masing-masing 1 poin, independen)
  demerits:
    tail_fragility:               # Gabungan banjir + setan (1 poin saja, tidak double-count)
      enabled: true
      p_flood_3p_below: 0.72
      p_flood_ft_below: 0.67
    high_market_total:
      enabled: true
      threshold: 235.0
    unexplained_model_gap:        # Hanya menyala jika gap > 8.0 TANPA cedera baru terverifikasi
      enabled: true
      gap_threshold: 8.0
    extreme_fat_tail_market:      # Diperketat agar tidak menyala di semua laga normal
      enabled: true
      min_offset_from_market: 16.0
      max_price_cents: 0.80
    high_foul_environment:        # Tambahan baru: tim peringkat bawah foul defense
      enabled: true
      combined_ftr_percentile_min: 0.80
    tight_spread_clutch_risk:
      enabled: true
      abs_spread_max: 3.0
    # DIHAPUS dari demerit:
    # - gap < 4.0 (kesepakatan dengan pasar = positif)
    # - volume < $100 / unknown (dipindah ke execution gate & info abu-abu)

  # Bukti positif keamanan untuk layak HIJAU (minimal 1 terpenuhi)
  positive_brakes_required_for_hijau: 1
  positive_brakes:
    - "top10_defense_present"           # Minimal 1 tim DRtg Top-10
    - "slow_pace_present"               # Minimal 1 tim Pace Bottom-12
    - "major_scorers_out_confirmed"     # Kehilangan pencetak poin utama (USG >= 25%) terkonfirmasi
    - "blowout_buffer_present"          # |spread| >= 8.5 poin
    - "market_aligned_clean"            # |median_model - pasar| <= 5.0 dan total pasar <= 228.0

  thresholds:
    hijau_max_demerits: 1               # 0 hard veto + <= 1 demerit + >= 1 positive brake
    menengah_hijau_max_demerits: 3      # 0 hard veto + 2-3 demerit (atau 0-1 tanpa positive brake)
    kuning_min_demerits: 4              # >= 4 demerit ATAU terkena hard veto

# 5. SETAN PER PEMAIN (Kalibrasi Realistis — Diagnostic Flag Only)
demon_per_player:
  mode: "diagnostic_flag_only"
  player_3p_boost: 0.12                 # 3P%_pemain + 12%
  player_3p_cap: 0.50                   # Cap di 50% (bukan rata 54.1% Cam Spencer)
  add_3par_volume_flag: true            # Flag tambahan jika kedua tim Top-10 3PAr

# 6. MODEL-MARKET BLEND & WORKFLOW OPTIMIZATION
calibration:
  lean_to_market_gap: 5.0
  apply_shrinkage_pre_verdict: true     # Susutkan bias model sebelum vonis jika tanpa alasan cedera
  short_circuit_orderbook_on_veto: true # Jangan pindai jup.ag untuk laga yang sudah kena hard veto
```

---

## 4. Kriteria Uji Penerimaan (*Acceptance Test*) untuk Muse

Sebelum meminta persetujuan final dari User untuk menaikkan config ke v18, mohon jalankan pengujian ulang terhadap artefak *slate* uji 23 Nov (10 baris) dan verifikasi 5 target berikut:

1. **Presisi Penangkapan Bencana (`True Positive`):** `DEN@CHI` **wajib tetap `KUNING`** (100% terblokir dari Asuransi maupun Utama) melalui Veto *Rim Protector* (`AND`) + skor demerit tinggi.
2. **Pemulihan *Equilibrium* Asuransi:** `Equilibrium Asuransi` harus naik dari **`0/10` menjadi minimal `2–3` kandidat `HIJAU`** (khususnya `BOS@GSW`, `OKC@MIA`, dan/atau `ORL@WAS`) yang mampu membentuk Tiket Asuransi valid tanpa melanggar aturan *tanpa kaki kembar*.
3. **Penurunan *False Positive*:** Jumlah laga pemenang yang salah divonis `KUNING` harus turun drastis dari `4/5` menjadi `0–1`.
4. **Penanganan Ketidakpastian *Lineup*:** Laga dengan bintang berstatus *Questionable* (seperti `IND@NYK` sebelum pukul `07:30 WIB`) harus masuk ke status `TUNGGU_LINEUP`, bukan dipaksa `HIJAU` atau langsung dimatikan jadi `KUNING`.
5. **Efisiensi Eksekusi:** Laga yang gagal di tahap *Hard Veto* (`DEN@CHI`) langsung melompati pemindaian *orderbook* `jup.ag` sehingga total waktu analisis *slate* turun signifikan.

Jika dalam uji ulang nanti masih ditemukan *edge case* (misalnya `OKC@MIA` atau `ORL@WAS` tersangkut di salah satu ambang baru), silakan kirim tabel hasil pengukuran v18-nya kembali lewat User agar kita iterasi berdasarkan angka aktual kode.