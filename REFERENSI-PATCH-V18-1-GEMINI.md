# REVIEW HASIL v18 & SPESIFIKASI PATCH v18.1 — DARI GEMINI UNTUK MUSE

**Tanggal:** 2026-11-23 (sore WIB)

**Dari:** Gemini (Analis Pendamping User)

**Untuk:** Muse (Arsitek & Pengembang Mesin) — *disampaikan melalui User*

**Target Rilis:** *Patch* v18.1 sebelum analisis *slate* Selasa, 24 Nov 2026 (`05:00 WIB`)

**Status:** Persetujuan perbaikan `skip_awal` + 4 temuan kritis tambahan (mengikuti pola D12: semua perubahan ambang menunggu uji kode dan persetujuan User)

## Ringkasan Eksekutif & Apresiasi v18

Hasil pengerjaan v18 sangat solid dan disiplin: $2.003/2.003$ tes lolos, *false positive* `KUNING` turun dari $4/5$ menjadi $0/5$, `DEN@CHI` tetap tertangkap veto `AND` (`Claxton OUT + 236,5 + pace 103,22`), `OKC@MIA` lolos, dan tidak ada ambang yang dilonggarkan diam-diam saat T2 gagal.

Dua keputusan koordinator di luar proposal awal juga sangat tepat:

1. Mengganti gate volume kumulatif menjadi **likuiditas Gamma (**$\ge \$30$**) + spread bid/ask (**$\le 5{,}0\text{¢}$**) + ask nyata** — koreksi rekayasa yang jitu dan langsung memecah *deadlock* Equilibrium Asuransi dari $0/10 \to 10/10$.

2. Mengalirkan sisa laga `HIJAU` ke Tiket Utama sambil tetap menegakkan aturan tanpa kaki kembar.

3. Koreksi atas klaim *short-circuit* ($6{,}85$ detik/laga karena pemindaian `jup.ag` bersifat *slate-level*) sepenuhnya valid dan diterima.

**Keputusan atas usulan Muse:** **SETUJU** $100\%$ untuk memperbaiki `skip_awal` (pola Denver) sekarang juga. **Namun**, ada **satu cacat struktural baru di Komposer Asuransi ("Perangkap Plafon `88,5¢`")** yang jika tidak dibereskan bersama `skip_awal`, akan membuat Tiket Asuransi tetap sangat sulit menembus target $2{,}00\times$ pada *slate* 24 Nov besok.

## 1. Spesifikasi 5 Perbaikan Patch v18.1 (Urutan Prioritas)

### Patch #1 (WAJIB — Usulan Muse): Perbaikan `skip_awal` (Pola Denver)

**Masalah di v18:** `skip_awal` men-skip $4/7$ laga *live* (`OKC`, `ORL`, `DEN`, `IND`), padahal $3$ di antaranya (`OKC`, `ORL`, `IND`) menang di garis EQ. Penyebabnya: syarat (4) masih membaca aturan usang `edge < 3,5%` dan syarat (2) masih memakai definisi `thin` lama.

**Spesifikasi perbaikan:**

* Ganti syarat `edge < 3,5%` menjadi berbasis EV: $\text{EV} < -1\%$ (atau gagal gate EV Asuransi).

* Ganti definisi "non-thin" menjadi **`equilibrium.cek_eksekusi` lolos** (likuiditas $\ge \$30$, spread $\le 5{,}0\text{¢}$, ask $< 99\text{¢}$).

* Gunakan output **`setan_pemain` v18** ($\min(50\%,\; 3P\%_{\text{musim}} + 12\%)$).

* **Pagar anti-redundansi dengan Equilibrium:** Jika sebuah laga **tidak** kena *Hard Veto* dan memiliki minimal $1$ garis yang lolos **seluruh** gate Equilibrium Asuransi (probabilitas, banjir, EV, eksekusi), `skip_awal` pola Denver **hanya** boleh menyala jika terjadi kombinasi kerapuhan struktural ekstrem:

  1. Garis Asuransi masih rapuh terhadap `setan_pemain` v18 ($P_{\text{setan}} < 0{,}55$ atau $\text{median}_{\text{setan}} > \text{garis}_{\text{asuransi}}$), **DAN**

  2. Total pasar sudah tinggi ($\text{garis\_pasar} \ge 232{,}0$), **DAN**

  3. Tidak ada garis valid (`cek_eksekusi` lolos + $\text{EV} \ge -1\%$) yang tahan terhadap deviasi banjir maupun setan.

* **Target validasi:** `DEN@CHI` **wajib tetap di-skip**; `OKC@MIA`, `ORL@WAS`, dan `IND@NYK` harus bebas dari `skip_awal` pola Denver.

### Patch #2 (KRITIS — Temuan Baru): Buka "Perangkap Plafon `88,5¢`" di Komposer Asuransi

**Masalah di v18:** Di hasil T2 `LAPORAN-V18.md`, ketiga kaki Asuransi yang lolos ke komposer (`BOS 231,5`, `DAL 246,5`, `DET 245,5`) semuanya terkunci di harga **`88,5¢`**, menghasilkan pengali maks hanya $1{,}36\times$.

Ini bukan kebetulan, melainkan konsekuensi matematis dari aturan **`safety-first` (**$P_{\text{final}}$ **tertinggi)** di dalam band `80¢–89¢`: karena $P_{\text{final}}$ monoton naik terhadap harga, Equilibrium akan **selalu** memetik garis plafon atas ($\approx 88{,}5\text{¢}$) di setiap laga.

Bukti matematis jumlah kaki yang dibutuhkan untuk menembus pengali bersih $\ge 2{,}00\times$ (dengan faktor *spread* kombo $0{,}945$ milik mesin kalian):

| Harga per Kaki | $3$ Kaki | $4$ Kaki | $5$ Kaki | $6$ Kaki | Minimal Kaki untuk $\ge 2{,}00\times$ | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| **`88,5¢`** *(plafon saat ini)* | $1{,}36\times$ | $1{,}54\times$ | $1{,}74\times$ | $1{,}97\times$ | $7$ **kaki** | 
| **`86,0¢`** | $1{,}49\times$ | $1{,}73\times$ | $2{,}01\times$ | $2{,}34\times$ | $5$ **kaki** | 
| **`84,0¢`** | $1{,}59\times$ | $1{,}90\times$ | $2{,}26\times$ | $2{,}69\times$ | $5$ **kaki** | 
| **`82,0¢`** | $1{,}71\times$ | $2{,}09\times$ | $2{,}55\times$ | $3{,}11\times$ | $4$ **kaki** | 

Pada *slate* $10$ laga besok, hampir mustahil mendapatkan $7$ **laga HIJAU sekaligus** (terlebih setelah dikurangi laga `TUNGGU_LINEUP`, veto, dan kebutuhan menyisakan laga berbeda untuk Tiket Utama demi aturan tanpa kaki kembar).

**Solusi bersih (ZERO pelonggaran gate keamanan):**
Pisahkan tugas `equilibrium.py` dan komposer menjadi 2 langkah:

1. **`equilibrium.py` mengembalikan semua garis valid (`valid_lines`), bukan hanya 1 garis plafon:** Kembalikan seluruh daftar garis di dalam band `80¢–89¢` yang lolos $100\%$ **gate Asuransi** ($P_{\text{final}} \ge 0{,}82$, $P_{\text{market}} \ge 0{,}80$, banjir 3P $\ge 70\%$, banjir FT $\ge 65\%$, $\text{EV} \ge -1\%$, `cek_eksekusi` lolos). Garis plafon `safety-first` tetap disimpan sebagai `default_eq` untuk laporan individu.

2. **Komposer Asuransi memilih kombinasi optimal lintas garis valid:** Dari seluruh kombinasi ($1$ garis per laga dari himpunan `valid_lines` laga `HIJAU`), cari kombinasi yang **memaksimalkan peluang cair gabungan**:
   

   $$
   \max \prod_{i=1}^{k} P_{\text{final},\,i}
   $$

   
   dengan syarat pengali bersih berada di rentang **`[2,00x, 2,50x]`** (atau *fallback* terlaporkan **`[1,80x, 1,99x]`** jika tidak ada kombinasi yang mencapai $2{,}00\times$ tanpa melanggar gate).

* **Dampak:** Tidak ada satu pun gate keamanan yang dilonggarkan. Jika tersedia $5-6$ laga HIJAU, komposer otomatis memilih kombinasi di `85¢–88¢`; jika hanya tersedia $4$ laga HIJAU, komposer otomatis bergeser terukur ke `81¢–83¢` **hanya jika garis tersebut memang lolos** $100\%$ **gate Asuransi**.

### Patch #3 (KRITIS UNTUK 24 NOV): Tutup Lubang Buta `rim_protector_2026-27.json` ($21/30 \to 30/30$)

**Masalah di v18:** $9$ tim belum terpetakan (`ATL, DET, GSW, HOU, IND, LAC, NYK, ORL, PHX`), sehingga $3$ **dari** $10$ **laga besok (`OKC@IND`, `PHX@NOP`, `LAC@HOU`)** langsung dalam kondisi veto-buta. Padahal tim-tim tersebut jelas memiliki *rim protector* sah (center/PF utama).

**Langkah diagnosa & perbaikan:**

1. **Periksa *mapping* kode tim & nama pemain BBRef vs `stats.nba.com`:** Cek perbedaan kode standar BBRef vs NBA (`PHO` vs `PHX`, `BRK` vs `BKN`, `CHO` vs `CHA`) serta normalisasi nama pemain (diakritik seperti *Jokić / Vučević / Sengün*, tanda titik `P.J.`, dan sufiks `Jr.` / `III`).

2. **Tambahkan *tier fallback* terukur di generator peta:** Jika suatu tim menghasilkan $0$ pemain pada filter primer (`C/PF/F-C/C-F`, `min >= 18`, `BLK >= 1,0`), jalankan *tier fallback* untuk mengambil top-$1$ `C/PF/F-C/C-F` tim tersebut dengan `min >= 18` dan `BLK >= 0,7`, lalu beri label `tier: "fallback"` di file JSON agar transparan.

3. **Target:** Peta mencapai $30/30$ **tim** (atau minimal $100\%$ tim yang bermain pada *slate* 24 Nov terpetakan lengkap) sebelum `05:00 WIB`.

### Patch #4 (PENTING — Akurasi Vegas Sanity Check): Filter Kesegaran `_sebab_cedera_baru`

**Masalah di v18:** Definisi `_sebab_cedera_baru` saat ini ($\text{OUT} + \text{BPM} \ge 2{,}0$) ikut menghitung pemain yang absen sejak awal musim (seperti Tyrese Haliburton). Padahal pemain yang absen jangka panjang sudah $100\%$ masuk ke harga pasar Vegas, sehingga pengecualian ini keliru mematikan *Vegas shrinkage*.

**Solusi:** Tambahkan syarat kesegaran sederhana di `_sebab_cedera_baru`:

* Pemain OUT hanya dihitung sebagai penyebab gap cedera baru jika **`GP >= 3` di musim berjalan** (atau tercatat bermain dalam $14$ hari terakhir).

* Pemain dengan `GP == 0` atau cedera jangka panjang (*out for season*) **tidak** boleh membatalkan *Vegas shrinkage*.

### Patch #5 (POLISH — Pemulihan Tier `MENENGAH_HIJAU` & Simetri D7)

1. **Pulihkan Tier `MENENGAH_HIJAU` (**$0/10$ **di v18):**

   * *Akar masalah:* Demerit `tail_fragility` dievaluasi pada garis EQ plafon (`88,5¢`), tempat hampir semua laga tampak tahan banjir — akibatnya batas pemisah antara `HIJAU` dan `MENENGAH_HIJAU` hilang.

   * *Solusi:* Evaluasi demerit `tail_fragility` di `vonis.py` pada **garis referensi standar** (misalnya garis terendah pada tangga harga yang memiliki harga $\ge 82\text{¢}$, atau garis terdekat dengan $\text{garis\_pasar} + 15{,}5$), bukan di plafon `88,5¢`. Dengan begitu, laga yang memang kokoh tetap `HIJAU` dan laga tanggung kembali masuk `MENENGAH_HIJAU` sebagai kandidat Tiket Utama.

2. **Simetri Kualifikasi D7 pada `TUNGGU_LINEUP`:**

   * Pastikan filter menit minimal (`mp >= 10,0`, lebih ideal `mp >= 15,0`) diterapkan pada **kedua** jalur bintang (`USG >= 24%` **DAN** `BPM >= +2,0`) agar pemain cadangan dengan sampel menit sangat kecil tidak memicu *hold* palsu.

## 2. Tanggapan atas Keputusan Terbuka di `DECISIONS.md` (§5 & §6 `LAPORAN-V18.md`)

Agar Muse bisa langsung menutup *open items* tanpa bolak-balik:

| Poin Laporan v18 | Status Review Gemini | Catatan Objektif | 
| ----- | ----- | ----- | 
| **§5.1** Gate eksekusi = likuiditas $\ge \$30$ + spread $\le 5\text{¢}$ | **SETUJU PENUH** | Solusi paling tepat; teruskan rencana kalibrasi dari *fill* nyata User di `jup.ag`. | 
| **§5.2 & §5.3** T1 fungsional + T5 reformulasi | **SETUJU PENUH** | Transparansi mencatat `lolos` literal sekaligus `lolos_fungsional` sangat baik. | 
| **§5.4** Sisa `HIJAU` mengalir ke Utama | **SETUJU PENUH** | Tetap patuh pada aturan tanpa kaki kembar di tingkat subset. | 
| **§5.5** Vegas CDF efektif kanonis + `shrinkage = 0,5` | **SETUJU** | Shrinkage $0{,}5$ adalah titik awal yang sehat; pantau Brier setelah $50$ kaki di *ledger*. | 
| **§5.6** Veto = `DATA_INCOMPLETE` + blok root + `KUNING` | **SETUJU** | Bersih secara skema. | 
| **§5.7** D7 kualifikasi USG | **SETUJU + REVISI KECIL** | Terapkan `mp >= 15,0` (atau `>= 10,0`) secara simetris pada jalur BPM juga (lihat Patch #5). | 
| **§5.8** `_sebab_cedera_baru` | **REVISI** | Wajib tambahkan filter `GP >= 3` / aktif $14$ hari terakhir (Patch #4). | 
| **§5.9** Peta rim protector $21/30$ | **REVISI SEGERA** | Tutup lubang $9$ tim menjadi $30/30$ sebelum *slate* 24 Nov (Patch #3). | 
| **§5.10** Hard-skip OT `0,085` dorman | **SETUJU SEMENTARA** | Jangan ubah *prior* $0{,}0575$ tanpa data *fit* OT; biarkan *hard-skip* dorman di v18.1, andalkan demerit `spread <= 3,0` + info `p_ot` di L3. | 
| **§6 (B)** Gate eksekusi khusus `total_under` NBA + `+3` veto parsial | **SETUJU** | Sesuai kebutuhan operasional saat ini. | 

## 3. Usulan Delta Konfigurasi `config/playstyle.yaml` (v18 $\to$ v18.1)

> **Catatan D12:** Hanya mencantumkan delta perubahan dari v18 agar mudah di-*diff*, diuji, dan disetujui User.

```
# ==============================================================================
# DELTA PROPOSAL CONFIG v18.1 — PATCH PRA-SLATE 24 NOV 2026
# ==============================================================================
version: "v18.1-proposal"

insurance:
  # Komposer memilih kombinasi optimal dari semua garis yang lolos 100% gate:
  expose_all_valid_lines_to_composer: true
  composer_objective: "max_joint_p_final_within_target_multiplier"
  target_multiplier_min: 2.00
  target_multiplier_fallback_min: 1.80   # Hanya jika kombinasi >= 2.00x tidak ada di garis valid
  target_multiplier_max: 2.50

skip_awal:
  # Mengganti aturan edge lama < 3.5% & volume thin lama:
  denver_pattern:
    use_ev_instead_of_flat_edge: true
    max_ev_for_weak_flag: -0.01          # Gagal jika EV < -1% (selaras gate Asuransi)
    use_cek_eksekusi_for_thin: true      # Likuiditas >= $30 & spread <= 5c
    use_demon_per_player_v18: true
    min_market_total_for_pattern: 232.0  # Hanya aktif di lingkungan skor tinggi
    demon_p_fragile_threshold: 0.55      # Atau median_setan > garis_asuransi

hard_vetoes:
  rim_protector_veto:
    fallback_tier_enabled: true          # Menutup 9 tim yang kosong di peta 21/30
    fallback_min_minutes_pg: 18.0
    fallback_min_bpg: 0.7

  lineup_timing_gate:
    min_minutes_pg_all_paths: 15.0       # Berlaku simetris untuk jalur USG maupun BPM

verdict:
  tail_fragility_reference_price_min: 0.82   # Evaluasi demerit pada garis referensi ~82c, bukan plafon 88.5c

calibration:
  fresh_injury_min_gp_season: 3          # Kecualikan pemain cedera panjang (GP < 3) dari _sebab_cedera_baru

```

## 4. Kriteria Uji Penerimaan (*Acceptance Test* v18.1 — Sebelum `05:00 WIB`)

Jalankan ulang pengujian pada artefak *slate* uji 23 Nov dan verifikasi $5$ kriteria berikut sebelum meminta persetujuan final User untuk *deploy* v18.1:

1. **Presisi `skip_awal` Baru:** `DEN@CHI` **wajib tetap di-skip** (dan/atau diblokir veto), sedangkan `OKC@MIA`, `ORL@WAS`, dan `IND@NYK` **tidak lagi terkena `skip_awal` pola Denver**.

2. **Pemulihan T2 (Tiket Asuransi Terbentuk Tanpa Pelonggaran Gate):** Pada *slate* uji 23 Nov (saat kandidat `HIJAU` tersedia $\ge 4$ laga setelah perbaikan `skip_awal`), Komposer Asuransi berhasil memilih kombinasi dari `valid_lines` (`80¢–89¢`) yang mencapai pengali bersih $\ge 1{,}80\times$ (target ideal $\ge 2{,}00\times$) **tanpa melanggar satu pun gate Asuransi maupun aturan tanpa kaki kembar**.

3. **Cakupan Peta *Rim Protector*** $30/30$**:** `config/rim_protector_2026-27.json` memuat data valid untuk $30/30$ **tim NBA** (0 tim buta pada $10$ laga *slate* 24 Nov, khususnya `OKC@IND`, `PHX@NOP`, dan `LAC@HOU`).

4. **Validasi Kesegaran Cedera:** Pemain absen jangka panjang (`GP == 0`, contoh Haliburton) **tidak lagi** memicu `_sebab_cedera_baru` sehingga *Vegas sanity check* berjalan bersih.

5. **Kepatuhan Mutlak & Regresi Nol:** Seluruh unit test lama + tes fail-first baru untuk Patch #1 s.d. #5 lulus $100\%$ (`ruff` & `black` bersih), tanpa menyentuh ambang keamanan inti (`p_final`, `p_market`, `banjir`, `EV`, `cek_eksekusi`).

## Catatan Operasional untuk Pagi 24 Nov 2026 (`10` Laga, *Tip-off* `07:00 WIB`)

* Jalankan analisis awal pukul `05:00–05:30 WIB` untuk menyaring laga bersih dan mengidentifikasi laga berstatus `TUNGGU_LINEUP`.

* Lakukan `recheck` terarah $30-40$ menit sebelum kloter *tip-off* masing-masing agar laga `TUNGGU_LINEUP` mendapat vonis final dari *injury report* resmi sebelum User memasang tiket.

* Tetap catat *fill* nyata di `jup.ag` (terutama harga eksekusi vs *spread* `5¢`) untuk bahan kalibrasi *ledger* berikutnya.