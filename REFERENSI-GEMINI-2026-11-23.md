# Referensi: Cara Gemini Menganalisis & Meracik (23 Nov 2026)

Sumber: percakapan user–Gemini 23 Nov 2026 05:22–~06:00 WIB, disalin user ke chat Muse
06:12 WIB, + 2 screenshot tiket jup.ag (05:51 & 05:57 WIB).
Dokumen ini ringkasan terstruktur + angka kunci. Transkrip lengkap ada di chat Muse
(side chat "Mesin Agent Baru", 2026-11-23 06:12 WIB).

## Jadwal: 6 laga NBA pagi ini (Senin, 23 Nov 2026)

| Jam WIB | Laga | Garis pasar | Proyeksi normal Gemini |
|---|---|---|---|
| 06:00 | Thunder @ Heat | 228,5 (turun dari 231,5) | 212,3 |
| 07:00 | Nuggets @ Bulls | 236,5–237,5 | 227,1 |
| 07:00 | Mavericks @ Jazz | 225,5 | 215,5 |
| 07:00 | Magic @ Wizards | 219,5 (turun dari 222,5) | 217,7 |
| 08:00 | Pacers @ Knicks | 213,5 (turun dari 216,5) | 214,3 |
| 08:30 | Celtics @ Warriors | 210,5–211,5 | 202,0 |

## Struktur bedah per laga (sama untuk 6 laga)

1. Update cedera & news real-time (laporan cedera final, siapa OUT/Questionable,
   dampak PPG pemain yang absen; berita breaking: SGA OUT pertama musim ini,
   Giannis OUT groin 19 menit sebelum analisis).
2. Statistik musim 2026–27 per tim (PPG, pace, ORtg/DRtg, 3P, TOV, FT rate,
   rekor Over/Under) + 5 laga terakhir + H2H musim ini.
3. Simulasi 100.000x MULTI-SKENARIO (bukan satu distribusi): normal,
   konservatif/sejajar pasar, banjir free throw (~57–66 FTA), banjir 3 poin
   (+6% akurasi 3P, ~26–30 3PM); kadang skenario cabang cedera
   (KAT & Siakam main / absen) dan efek kandang.
4. Tabel peluang P(Under) per garis per skenario.
5. Vonis: HIJAU / KUNING / KUNING–HIJAU / HIJAU BERSYARAT + target garis
   Tiket Utama & Tiket Asuransi + "racun" (cara spesifik Under bisa jebol).

## Vonis & target garis per laga

| Laga | Vonis | Target Utama | Target Asuransi |
|---|---|---|---|
| OKC @ MIA | HIJAU | U 234,5–236,5 | U 239,5–242,5 |
| BOS @ GSW | HIJAU | U 223,5–225,5 | U 228,5–231,5 |
| DAL @ UTA | HIJAU | U 237,5–239,5 | U 242,5–245,5 |
| IND @ NYK | HIJAU BERSYARAT | U 229,5–231,5 | U 234,5–236,5 |
| ORL @ WAS | KUNING–HIJAU | U 235,5–237,5 | U 239,5–241,5 |
| DEN @ CHI | KUNING | U 249,5–252,5 | U 254,5–256,5 |

## Racikan: pilih 4 kaki edge terbesar, buang 2 laga

- Dipakai: OKC, DAL, DEN, BOS — proyeksi model 8,5–13,2 poin di bawah garis pasar.
- Dibuang: ORL & IND — selisih edge < 2 poin (garis pasar sudah diperas:
  219,5 & 213,5) + status KAT/Siakam masih Questionable.
- Asuransi: 4 kaki ~82¢, ~2,24x, peluang tembus 71,6% (normal).
- Utama: awalnya 4 kaki ~3,5x (rekomendasi) / ~4,5x (agresif); setelah debat
  jadi 5 kaki 78–82¢ (tambah ORL U 233,5), 3,05–3,32x.
- Pembagian modal simulasi: $27 → $15 Utama + $12 Asuransi, dengan tabel
  skenario hasil (keduanya tembus / hanya Asuransi / keduanya gugur).

## Debat & audit (interaktif, ini inti cara kerjanya)

1. **Tumpuk 6 laga untuk Asuransi? → TIDAK.** 6 kaki @87,5¢ = 2,21x tapi
   peluang 60,5% vs 71,7% (4 kaki); peluang OT 14,4% → 20,7%; 2 kaki tanpa
   edge = "beban mati". 6 kaki @82¢ = 3,29x (bukan 2,2x).
2. **Utama 75¢ terlalu agresif (trauma Thunder 71¢).** User minta tidak ada
   kaki di bawah 78¢ → Utama digeser ke 5 kaki 78–82¢ (tambah ORL sebagai
   tuas pengali), IND tetap dibuang. "Hedge gratis": ORL hanya ada di Utama,
   tidak di Asuransi.
3. **Audit tiket Asuransi riil** (garis + harga dari layar user): 75,8%
   normal, EV +69,7%; per kaki: OKC U 242,5 @83¢ (95,7%), DAL U 240,5 @80¢
   (93,1%), DEN U 252,5 @82¢ (92,3%), BOS U 225,5 @82¢ (92,1%).
4. **Audit tiket Utama riil** (user menambah IND@NYK U 230,5 @85¢ sendiri,
   buru-buru 3 menit sebelum tip-off): 49,5% normal, EV +84,2%; kaki paling
   rapuh IND@NYK (21,1% skenario kalah disebabkan kaki ini sendiri) lalu ORL
   (16,5%). 85¢ = ilusi aman: garis pasar 213,5 diperas, bantalan riil hanya
   +16,2 poin; KAT & Siakam main → peluang 70,7%. Tanpa IND: 3,16x tapi
   peluang 60,2%, EV +90,3% (lebih tinggi).
5. **User panik "Asuransi tipis"** → koreksi hitungan: 6 kaki @84¢ = 2,85x
   (bukan 2x); 4 kaki 80–83¢ punya bantalan +23,5–+30,2 poin vs model,
   peluang per kaki 92,4–95,8%. Fungsi hedge: Asuransi tidak memuat kaki
   berisiko (ORL/IND) yang ada di Utama — kalau Utama patah di situ,
   Asuransi tetap selamat.

## Tiket yang benar-benar dipasang user (screenshot jup.ag)

- **Asuransi** (05:51 WIB, kode 1g1URyNC1l): 4 kaki, **2,17x**, stake $15,
  menang $32,51, chance 46%. Kaki: OKC U 242,5 · DEN U 252,5 · DAL U 240,5 ·
  BOS U 225,5.
- **Utama** (05:57 WIB, kode D3pDLoyL4V): 6 kaki, **3,72x**, stake $15,
  menang $55,79, chance 27%. Kaki: OKC U 238,5 · DEN U 250,5 · DAL U 238,5 ·
  ORL U 235,5 · IND U 230,5 · BOS U 223,5.
- Total modal $30 ($15 + $15). Status saat screenshot: 0/4 hit, 0/6 hit, LIVE.

## Yang belum dikerjakan mesin kita (catatan awal, untuk analisis mendalam)

- Simulasi multi-skenario (banjir FT, banjir 3P, cabang cedera, efek kandang).
- Pemilihan kaki dari EDGE (selisih proyeksi model vs garis pasar), bukan
  hanya harga + peluang.
- Audit tiket riil (user tempel garis + harga → audit per kaki + kaki
  paling rapuh + pangsa skenario kalah per kaki).
- Struktur hedge: kaki berisiko sengaja TIDAK masuk Asuransi.
- Kesadaran waktu (sisa waktu per laga, skip laga yang mepet, rekomendasi
  berubah bila tip-off lewat).
- Harga ≠ peluang: flag overpay per kaki (harga di atas peluang model).
