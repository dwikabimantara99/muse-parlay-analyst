# LAPORAN PATCH TAHAP 3 LANGKAH 1B — Perbaikan Otak NBA (4 Temuan Auditor)

Tanggal: 2026-11-22. Patch ini memperbaiki keempat temuan auditor (Claude)
atas Otak NBA langkah 1, yang semuanya sudah dicek dan dikonfirmasi main
agent dari kode/data live sebelum patch dimulai (lihat DECISIONS.md bagian
"Persetujuan parameter fit NBA (D12) + temuan auditor"). User menyetujui
perbaikan dulu sebelum langkah 2 (2026-11-22 20:06 WIB), dengan titipan:
bantalan Asuransi dihitung dari target peluang 74%, bukan dikunci +12.

**Hasil akhir: 707 tes, semua lulus (dari 613; +94). Ruff + black bersih
repo-wide. 0 kredit Odds API dipakai patch ini. Config v6.**

| Temuan | Verdict | Inti perbaikan |
|---|---|---|
| 1. Validasi terlalu optimis | BENAR, diukur | Rating rolling point-in-time; Brier jujur 0,1983 (v1: 0,1859); re-fit TIDAK MATERIAL |
| 2. Hitung-ganda pemain absen | BENAR, diperbaiki | Replacement level BPM −2,0 + koreksi tumpang-tindih last10; total DET@ATL 221,95 → 218,75 |
| 3. Bantalan Under +8 hanya ~66% | BENAR, diperbaiki | Bantalan Asuransi dari target peluang 0,74 + lantai market +8; garis final 233,5 @ 66,5¢ |
| 4. Cek silang cedera 1 sumber | BENAR, diperbaiki | ESPN cedera NBA jadi sumber kedua; B2 terpenuhi; Rotowire cadangan (paywall) |

Parameter fit yang disetujui user (D12) TIDAK diubah: re-fit rolling
tidak material (lihat §1), jadi `playstyle.yaml` tetap memakai nilai
D12. Adopsi nilai rolling adalah keputusan terpisah (lihat §8).

---

## 1. Perbaikan 1 — Validasi out-of-sample (temuan 1)

### Masalah
Skrip fit + validasi memakai rating musim penuh BBRef ("melihat masa
depan"). Backtest v1 (150 laga, 50 terbaru/musim) Brier kandang-menang
0,1859 vs klimatologi 0,2436 — kemungkinan agak optimis. Kelemahan ini
sudah dicatat jujur di docstring fit ("Perbaikan ke depan: rating
rolling sampai sebelum tanggal laga").

### Yang diubah
- `scripts/fit_nba_params.py` + `scripts/validate_nba_model.py`: mode
  `--rolling`. Untuk tiap laga uji, rating tim dihitung HANYA dari laga
  sebelum tanggal laga itu (musim-berjalan + last10-berjalan).
- **Temuan soal data:** `data/nba_history/games_all.json` ternyata hanya
  menyimpan poin (tanpa FGA/FTA/OREB/TOV) — tidak cukup untuk
  possessions. Jalan keluar: respons mentah endpoint leaguegamefinder
  yang sama memuat kolom box score lengkap; skrip fit kini mem-parse
  respons mentah itu sendiri. Hasil: 5.402 record (2.701 laga × 2 tim),
  0 laga hilang. Total network: 4 panggilan keyless gratis (3 box score
  + 1 BBRef 2023-24). Cache: `data/nba_history/boxscores_all.json`
  (gitignored).
- Keputusan desain rolling (D-R1–D-R5, didokumentasikan di docstring +
  LAPORAN-FIT-NBA.md §12):
  - **D-R1** Prior = rating BBRef musim sebelumnya per tim (untuk
    2024-25: BBRef 2023-24).
  - **D-R2** Shrinkage (n×obs + K×prior)/(n+K), K = 10 laga (pilihan
    desain, bukan fit).
  - **D-R3** Last10 di-shrink ke rating musim (hirarki prior → musim →
    last10, anti hitung-ganda).
  - **D-R4** Jendela reset tiap musim; carryover hanya lewat prior.
  - **D-R5** lg_avg juga point-in-time; rating efektif = 60% musim +
    40% last10 seperti sim.
- **Catatan jujur (D-R5):** selisih v1 vs rolling adalah efek gabungan
  point-in-time + resensi 60/40 yang kini beroperasi (v1 tidak memakai
  last10 sama sekali di backtest) — bukan efek point-in-time saja.
  Efek murni look-ahead tidak diisolasi.
- Sinkronisasi `_dampak_pemain`: salinan rumus lama di
  `scripts/validate_nba_model.py` kini delegasi ke
  `engine.nba_sim._dampak_pemain` (rumus tunggal di engine; bila engine
  berubah signature, skrip gagal loud). Kepekaan membaca
  `bpm_replacement` + bobot recency dari config.

### Hasil backtest (subset 150 laga IDENTIK — satu fungsi pilih_subset
### untuk kedua mode, dari games_all.json yang sama)

| Event | v1 | Rolling | Selisih |
|---|---|---|---|
| Kandang menang (Brier) | 0,185911 | **0,198308** | +0,012397 (+6,67%) |
| Under median+8 (Brier) | 0,230642 | 0,219926 | −0,010716 |

- **Kandang:** perbandingan bersih (event tidak bergantung model).
  Brier jujur = 0,1983, masih jauh di bawah klimatologi 0,2436 —
  skill nyata tetap ada, v1 memang agak optimis.
- **Under:** baca dengan hati-hati — frekuensi aktual ikut berubah
  (0,64 → 0,6733) karena garis (median+8) bergeser mengikuti median
  baru. Brier model praktis sama dengan klimatologi di kedua run
  (rolling 0,2199 vs klim 0,2200; v1 0,2306 vs klim 0,2304), dan
  semua 150 prediksi tetap dalam satu bucket. "Perbaikan" Under
  terutama mencerminkan garis bergeser, bukan skill baru.
- Backtest rolling: 284 detik. Brier pasar tetap DATA_INCOMPLETE
  (tidak ada harga pasar historis).

### Re-fit (2.701/2.701 laga) — TIDAK MATERIAL

| Parameter | D12 (disetujui) | Rolling | Selisih |
|---|---|---|---|
| sigma_margin | 13,8168 | 14,4307 | +0,6139 (+4,44%) |
| sigma_total | 18,2198 | 18,9868 | +0,7670 (+4,21%) |
| home | 1,6552 | 1,6639 | +0,0087 |
| B2B | −1,596 | −1,5164 | +0,0796 |
| altitude | −0,0105 | −0,4094 | −0,3989 (SE 1,14 — dalam noise) |
| t_nu | 34,5 | 35,0 | +0,5 |

Ambang pelaporan (bukan keputusan): material bila sigma berubah >10%
atau home/B2B berubah >0,5 poin — tidak ada yang terlampaui. **Tidak
ada penanda "menunggu persetujuan ulang".** Arah sesuai dugaan: sigma
rolling lebih besar (v1 underestimate ~4–4,5%). Nilai rolling
TIDAK dimasukkan ke playstyle.yaml; adopsi adalah keputusan
user/reviewer terpisah (lihat §8).

Detail lengkap + metode: LAPORAN-FIT-NBA.md §12. Bukti (gitignored):
`out/fit_nba_params_rolling.json`, `out/validation_nba_rolling.json`,
`out/fit_nba_params_v1.json`, `out/validation_nba_v1.json` (backup v1).

### Keterbatasan yang tersisa
Cedera per tanggal untuk laga historis tetap tidak tersedia (backtest
tanpa penyesuaian pemain absen); B2B tetap dari tanggal kalender;
sigma_total tetap mencakup varians OT; K=10 adalah pilihan desain
yang belum difit.

---

## 2. Perbaikan 2 — Replacement level + koreksi tumpang-tindih (temuan 2)

### Masalah (terverifikasi di kode)
`engine/nba_sim.py` `_dampak_pemain`: dampak absen = BPM × (mp/48) ×
bpm_scale, dikurangi penuh, TANPA replacement level. Rating tim 60%
musim + 40% last10 — pemain yang sudah absen di last10 terhitung
ganda. Bukti: 4 pemain cadangan BPM negatif menaikkan total contoh
DET@ATL 218,28 → 221,95; Duren (BPM 8,8) dihitung ganda ~1,4 poin.

### Yang diubah
- **Replacement level:** dampak absen = (BPM − BPM_replacement) ×
  (mp/48) × bpm_scale × faktor_overlap. `bpm_replacement = −2,0`
  (parameter baru `simulation.nba` di playstyle.yaml).
  Nilai −2,0 dari literatur Basketball-Reference — diverifikasi
  koordinator langsung dari sumbernya: Sports-Reference Blog,
  "Introducing Box Plus/Minus (BPM)" (2014):
  *"BPM is scaled so that -2.0 represents a theoretical 'replacement
  level'"*, rumus VORP = [BPM − (−2,0)] × %menit
  (https://www.sports-reference.com/blog/2014/10/introducing-box-plusminus-bpm-2/;
  juga http://basketball-reference.com/about/bpm.html).
  Dicatat sebagai **asumsi yang didokumentasikan, bukan hasil fit**
  (seperti bpm_scale).
- **Koreksi tumpang-tindih:** faktor = (1 − 0,4 × missed_last10/10),
  di mana missed_last10 = jumlah dari 10 laga terakhir tim yang tidak
  dimainkan pemain itu. `nba_sim` membaca field opsional
  `missed_last10` per dict pemain; hilang/tidak valid → faktor 1,0
  (perilaku lama) + catatan di `inputs_summary.notes` (hanya untuk
  pemain yang memang absen di base case). Pemain skenario hipotetis
  yang sehat: faktor 1,0 (asumsi yang didokumentasikan).
- **Modul baru `ingest/player_gamelog.py`:** parse game log BBRef +
  hitung missed_last10. Penyebab kegagalan parse main agent ditemukan:
  id tabelnya `player_game_log_reg`, bukan `pgl_basic`. Baris tidak
  bermain dikenali lewat sel `is_starter` ("Inactive"/"Did Not Play")
  + tidak ada sel `mp`; baris header di tengah `<tbody>` dilewati.
  `ingest/bbref.py` kini menangkap `bbref_slug` pemain + menyediakan
  `shared_client()` (satu limiter 4 dtk untuk semua modul BBRef).
  stats.nba.com tidak dicoba (tidak diperlukan; endpoint-nya butuh
  PlayerID NBA yang tidak tersedia dari BBRef).
- **Output sim:** persentil `p74` ditambahkan ke
  `score_distribution.total` (+ skema). `ENGINE_VERSION` 1.0.0 → 1.1.0.
- **Wiring koordinator:** `ingest/nba_brain.py` kini memanggil
  `fetch_missed_last10_many` untuk pemain OUT (best-effort; gagal →
  field tidak ada, sim memakai faktor 1,0 + notes). Hanya pemain OUT
  yang diambil game log-nya (hemat request).

### Contoh DET@ATL 2026-11-22 — sebelum vs sesudah
### (input SAMA; varian A mereproduksi contoh lama persis — dekomposisi
### murni efek rumus)

| Varian | Total | Margin | Median | p74 | ML kandang |
|---|---|---|---|---|---|
| A — rumus lama | 221,95 | 4,87 | 223 | 234 | 63,9% |
| B — replacement saja | 217,22 (−4,73) | 5,21 (+0,34) | 218 | 230 | 64,8% |
| **C — replacement + overlap (final)** | **218,75** | **3,18** | **219** | **231** | **59,2%** |

Contoh final di `examples/` adalah varian C (diregenerasi koordinator
setelah wiring partisipasi; total/margin/median/p74/ML cocok persis
dengan probe pekerja). OT final 2,9% (v1: 2,6%).

Dekomposisi per pemain (dampak = poin yang dikurangi dari proyeksi
tim bila pemain absen):

| Pemain | Tim | BPM | mp | Lama | Replacement | missed | Faktor | Repl+overlap |
|---|---|---|---|---|---|---|---|---|
| CJ McCollum | ATL | −0,6 | 26,36 | −0,329 | 0,769 | 2 | 0,92 | 0,707 |
| Asa Newell | ATL | −3,9 | 11,00 | −0,894 | −0,435 | 7 | 0,72 | −0,313 |
| Jock Landale | ATL | −4,1 | 15,44 | −1,319 | −0,676 | 7 | 0,72 | −0,486 |
| Duncan Robinson | DET | 2,6 | 30,50 | 1,652 | 2,923 | 3 | 0,88 | 2,572 |
| Jalen Duren | DET | 8,8 | 19,00 | 3,483 | 4,275 | 10 | 0,60 | 2,565 |
| Ebuka Okorie | DET | −13,3 | 4,00 | −1,108 | −0,942 | 7 | 0,72 | −0,678 |
| Taurean Prince | DET | −2,3 | 7,33 | −0,351 | −0,046 | 9 | 0,64 | −0,029 |
| **TOTAL** | | | | **1,133** | **5,868** | | | **4,337** |

- **Replacement (A→B, −4,73 total):** 4 pemain cadangan BPM negatif
  (McCollum, Newell, Landale, Okorie) total dampak lama −3,65 —
  merekalah yang menaikkan total lama (temuan auditor "+3,67"
  terkonfirmasi; selisih 0,02 dari pembulatan menit). Dengan
  replacement, McCollum berbalik menekan proyeksi (+0,77);
  Newell/Landale/Okorie tetap berdampak negatif karena BPM mereka di
  bawah −2,0 — jawaban jujur model: pengganti level −2,0 memang lebih
  baik dari mereka. Duren naik 3,48 → 4,28.
- **Overlap (B→C, +1,53 total):** Duren (missed 10/10 → faktor 0,60)
  turun 4,28 → 2,57 — koreksi 1,71 poin; pada basis rumus lama,
  hitung-gandanya 3,483 × 0,4 = **1,39 ≈ 1,4**, persis angka auditor
  (tapi lewat data nyata missed 10/10, bukan perkiraan 6–7/10).
  Margin jatuh 2,03 karena DET jauh lebih banyak dikoreksi.
- 3 pemain OUT tanpa BPM (Veesaar, Gueye, Onyenso) tetap berdampak 0 +
  catatan, seperti sebelumnya.

### Uji kepekaan bpm_replacement ±1

| bpm_replacement | Total (B) | Median (B) | p74 (B) | Total (C) | Median (C) | p74 (C) |
|---|---|---|---|---|---|---|
| −3,0 | 214,85 | 215 | 227 | 216,89 | 218 | 229 |
| **−2,0** | **217,22** | **218** | **230** | **218,75** | **219** | **231** |
| −1,0 | 219,58 | 220 | 232 | 220,60 | 221 | 233 |

Perubahan total linear: ±1 menggeser total ∓2,37/+2,36 (B) dan
∓1,86/+1,85 (C) — persis total menit OUT berbobot (113,63/48 =
2,367; berbobot overlap 89,10/48 = 1,856). Margin hanya bergerak
±0,17. Pilihan −2,0 vs −1,0/−3,0 mengubah total ~2 poin — material
untuk garis Alt Under, tapi tidak mengubah arah cerita.

### Status data partisipasi
BBRef BERHASIL, 7/7 pemain OUT ber-BPM (McCollum 2, Newell 7,
Landale 7, Robinson 3, **Duren 10**, Okorie 7, Prince 9 — semua
games_considered 10/10, 0 gagal). Fallback teruji: tanpa
`missed_last10` → faktor 1,0 + catatan per pemain OUT. Contoh final
hanya memuat 3 catatan tanpa-BPM (0 catatan fallback partisipasi).

### Keterbatasan / UNKNOWN
- **Duren: BBRef vs ESPN berbeda.** BBRef menunjukkan Duren Inactive
  sejak laga tim ke-3 (25 Okt) → missed 10/10; ESPN menyebut OUT
  sejak ~8 Nov → perkiraan 6–7/10. BBRef adalah sumber partisipasi
  modul ini, jadi 10/10 yang dipakai — selisih sumber ini UNKNOWN
  penyebabnya (mungkin tanggal status ESPN ≠ tanggal tidak bermain).
- **`mp_per_game` Duren = 19,0 dari hanya 2 laga yang dimainkan.**
  Definisi BBRef: menit per laga *yang dimainkan*, bukan per laga tim.
  Bila menit normalnya ~30, dampak absennya diremehkan. Keterbatasan
  data yang sudah ada sebelumnya, bukan dari patch ini.
- **Awal musim (<10 laga tim):** missed dihitung dari laga yang ada,
  tapi penyebut rumus overlap tetap 10 — sedikit kurang mengoreksi.
- **Pemain di bawah replacement (BPM < −2,0)** tetap menaikkan
  proyeksi bila absen — disengaja dan didokumentasikan, bukan bug.
- **Biaya waktu:** game log BBRef memakai limiter bersama 4 dtk —
  panggilan dingin pertama menambah ~28 dtk untuk 7 pemain OUT
  (panggilan ulang memakai cache; regenerasi contoh final berjalan
  9,6 dtk total karena cache).

---

## 3. Perbaikan 3 — Bantalan Asuransi dari target peluang 74% (temuan 3 + titipan user)

### Keputusan user (mengikat, 2026-11-22 20:06 WIB)
Bantalan Asuransi TIDAK dikunci +12. Aturan: garis Alt Under Asuransi
= garis terkecil dari tangga market yang memenuhi (a) P_model(Under
pada garis itu) ≥ 0,74 — dihitung dari distribusi empiris simulasi
100.000x (persentil ke-74 total sim), BUKAN rumus analitik terpisah;
DAN (b) garis ≥ garis market + 8 (lantai "batas bawah bandar").
Bila re-fit mengubah sigma, bantalan ikut menyesuaikan otomatis.
Utama: tetap +8 (atau +12 bila spread ≤ 2,5), diukur dari max(median
model, garis market).

### Yang diubah
- **Modul baru `engine/cushion.py`** (self-contained): `insurance_line`
  + `utama_line`. `insurance_line` memakai `p74` dari distribusi sim
  bila ada (garis pada persentil ke-74 berarti P(Under) ≈ 0,74
  menurut distribusi empiris); bila p74 tidak ada, fallback
  interpolasi linear antara median (p50) dan p75 (didokumentasikan).
  Bila tidak ada garis tangga yang memenuhi kedua syarat → `meets =
  False` + alasan (kaki TIDAK memenuhi syarat Asuransi — tidak
  dipaksakan). Data hilang → `meets=False` + alasan (bukan exception);
  input bertipe salah → `ValueError`. `markets.py` hanya dibaca
  (tidak ada helper bantalan yang bisa dipakai ulang).
- **Parameter baru di `filters.nba_alt_under`** (playstyle.yaml v6):
  `insurance_target_probability: 0,74`,
  `market_cushion_floor_points: 8`. Modul membaca dari config bila ada
  (divalidasi); sebelum ditambahkan koordinator, modul memakai default
  0,74/8 dengan penanda `"*_source": "default"` — default itu nilai
  keputusan user, bukan karangan.
- **Keputusan desain:** `utama_line` dengan `spread=None` memakai
  bantalan 8 (aturan +12 hanya bila terbukti spread ≤ 2,5) —
  didokumentasikan sebagai pilihan yang disadari, bukan fail-closed
  sempurna; pemanggil yang tidak tahu spread harus sadar akan hal ini.

### Garis final DET@ATL (contoh final + tangga segar 22 Nov 13:28Z)
- Persentil final: median 219, p74 231, p75 232. Garis market 225,5
  (volume terbesar $44.049).
- **Asuransi: garis 233,5 @ 66,5¢ (estimasi jup.ag 67,0¢).**
  p_target 231,0 (sumber p74); lantai market 233,5 yang mengikat.
  Bantalan vs market 8,0 poin; vs median 14,5 poin. P_model(Under
  233,5) ≈ 77% (di atas target 74% karena lantai yang mengikat).
- **Utama (spread 5,0): garis 233,5 @ 66,5¢**
  (max(219, 225,5) + 8 = 233,5). Spread 2,0 → 237,5 @ 75,5¢.
- Perbandingan dengan spesifikasi lama (median 223, p75 235): garis
  Asuransi 235,5 @ 71,0¢ (p74 interpolasi 234,52 mengikat). Tes
  cushion sengaja tetap memakai angka spesifikasi lama (inline) karena
  menguji logika + jalur interpolasi; angka final di atas dihitung
  koordinator dari contoh + tangga final.

---

## 4. Perbaikan 4 — ESPN cedera NBA sebagai sumber kedua (temuan 4)

### Yang diubah
- **Perluas `ingest/espn.py`** (bukan modul baru — fetcher + parser
  ESPN injuries sudah ada di sana: `parse_injuries_nba`,
  `fetch_injuries_nba`; modul baru akan menduplikasi endpoint/limiter/
  cache): `normalize_injury_status`, deteksi konflik status-vs-komentar,
  deteksi entri non-cedera, entri diperkaya (`status_normalized`,
  `status_comment_conflict`, `is_injury`, `long_comment`, `date`,
  `source`, `tier`, `time`).
- **`ingest/nba_brain.py`:** merge cedera kini PDF resmi (tier 1) +
  ESPN (tier 2); Rotowire dicopot. Merge memakai `status_normalized`,
  mengecualikan `is_injury=False` (missing
  `injuries_bukan_cedera:<pemain>`), meneruskan
  `status_comment_conflict` (missing
  `injuries_komentar_konflik:<pemain>`); kunci error
  `injuries_rotowire` → `injuries_espn`.
- **`config/sources.yaml`:** ESPN jadi kandidat cek silang utama (tier
  2) dengan catatan verifikasi live; Rotowire pindah ke posisi terakhir
  (cadangan) dengan catatan paywall "5 entri + Subscribers Only,
  22 Nov 2026".
- **Aturan konflik (didokumentasikan):** field status adalah datum
  terstruktur, komentar disimpan sebagai konteks; konflik ditandai
  bila jelas bertentangan (OUT + sinyal bisa-main; PROBABLE/AVAILABLE
  + sinyal definitif-tidak-main; QUESTIONABLE/DOUBTFUL + sinyal
  definitif-tidak-main). Day-To-Day + "probable" BUKAN konflik;
  "won't return" (laga berjalan) BUKAN sinyal. Deteksi HANYA dari
  `shortComment`, bukan `longComment` (verifikasi pada 110 entri live:
  substring di longComment memberi banyak false positive).
- **Aturan non-cedera:** `is_injury` = status OUT/DOUBTFUL/QUESTIONABLE
  + ada detail cedera + tanpa alasan administratif (pola shortComment:
  two-way contract/deal, personal reasons, G League assignment,
  suspensi; atau `details.type` Rest/Personal). Catatan: Onyenso punya
  `details.type` "Foot" — detail saja tidak cukup; komentarlah
  penentunya. Illness DIHITUNG sebagai detail kesehatan.
- **Keputusan desain:** Rest/Personal yang dikecualikan (mis. Tatum)
  hanya tercatat di `missing`, tidak dimodelkan sebagai absen —
  konsekuensi harfiah dari aturan tugas; konsep "ketersediaan" di luar
  cedera adalah pekerjaan lanjutan bila diinginkan.

### Verifikasi live (dijalankan ulang koordinator, DET@ATL 2026-11-22 pra-laga)
`fetch_match_inputs("ATL", "DET", "2026-11-22")` → ok=True, 0 fetch
error, **B2 TERPENUHI**: kedua sumber cedera tercatat (PDF resmi tier
1 + ESPN tier 2). 17 cedera tergabung (ATL 9, DET 8); 12 dikonfirmasi
kedua sumber, 5 hanya PDF.
- **Pengecualian non-cedera:** entri ESPN Onyenso (two-way)
  dikecualikan — namun Onyenso TETAP ada di daftar cedera karena PDF
  resmi secara independen menyatakan OUT. Perilaku yang benar:
  pengecualian ESPN hanya mencabut konfirmasi ESPN, bukan membatalkan
  tier 1.
- **Konflik antar-sumber (3):** Flemings (PDF QUESTIONABLE vs ESPN
  OUT), Holland (PDF QUESTIONABLE vs ESPN OUT), Cunningham (PDF
  PROBABLE vs ESPN QUESTIONABLE dari pemetaan Day-To-Day) — pemenang
  tier 1 sesuai B1, konflik dicatat.
- **Konflik status-vs-komentar (2):** Flemings + Holland keduanya
  `status_comment_conflict=True` — dan dalam kedua kasus, komentar
  ESPN ("questionable") justru sejalan dengan PDF melawan field status
  ESPN sendiri. Flag ini menangkap inkonsistensi nyata, bukan noise.
- Fixture: `tests/fixtures/espn_injuries_nba_2026-11-22.json`
  (tangkapan live sekali, 22 Nov 13:12Z, 30 tim, 110 cedera; dipangkas
  ke 7 tim / 31 entri — DET + ATL lengkap + 5 tim kasus uji;
  pemangkasan didokumentasikan di `_meta`).

### Keterbatasan / UNKNOWN
- Status ESPN di luar Out/Day-To-Day (Doubtful/Questionable/Probable)
  tidak muncul di data live hari ini (92 Out + 18 Day-To-Day) —
  pemetaannya dites sintetis, belum tervalidasi terhadap respons live.
- Pola administratif non-cedera didasarkan pada 110 entri hari ini;
  pola baru di masa depan akan lolos sebagai cedera sampai aturannya
  diperbarui.

---

## 5. Integrasi koordinator

Pekerjaan dibagi ke 3 pekerja paralel (kepemilikan file tidak
bertabrakan); koordinator memverifikasi tiap hasil dari disk sebelum
integrasi:
- **Perbaikan 2:** 75/75 tes target lulus; rumus dicek dari diff;
  aritmetika dekomposisi dihitung ulang (cocok); kutipan −2,0
  diverifikasi langsung dari blog Sports-Reference; contoh B cocok
  persis (217,22).
- **Perbaikan 4+3:** 78/78 tes target lulus; verifikasi live
  dijalankan ulang independen (17 cedera, 12 dua sumber, Onyenso,
  3 konflik, 2 konflik komentar — semua cocok); garis Asuransi/Utama
  dihitung ulang dari tangga asli (cocok).
- **Perbaikan 1:** 49/49 tes target lulus; parameter + Brier dicek
  dari JSON (cocok); subset identik lewat satu fungsi pilih_subset;
  delegasi `_dampak_pemain` dicek dari kode; games_all.json
  dikonfirmasi hanya-poin.

Pekerjaan integrasi oleh koordinator:
- Parameter bantalan di `filters.nba_alt_under` (playstyle.yaml v6)
  + meta.source diperbarui. `test_config.py`: `test_meta_versi_5` →
  `test_meta_versi_6`.
- Wiring partisipasi ke `nba_brain.py` (`_tambah_partisipasi`,
  best-effort) + 3 tes wiring + patch `fetch_missed_last10_many` di
  `_PatchSemua` (side effect: Kessler 7/10) + asersi end-to-end di
  `test_blok_tim_kandang_uta`.
- Regenerasi contoh final DET@ATL (varian C) + tangga segar +
  hitung garis Asuransi/Utama final.
- Laporan ini + DECISIONS.md.

Satu kegagalan tes saat integrasi (diperbaiki koordinator):
`test_kontrak_lengkap` gagal karena wiring partisipasi menambah
`UTA.participation:Walker Kessler` ke missing (fixture tanpa slug) —
diselesaikan dengan mem-patch fetcher partisipasi di `_PatchSemua`
+ slug di fixture, bukan dengan melonggarkan tes.

---

## 6. Angka kunci sebelum vs sesudah (contoh DET@ATL + validasi)

| Ukuran | Langkah 1 (v1) | Patch 1b (final) |
|---|---|---|
| Total proyeksi DET@ATL | 221,95 | 218,75 |
| Margin | +4,87 | +3,18 |
| Median total | 223 | 219 |
| p74 total | — (baru) | 231 |
| ML kandang | 64,1% | 59,2% |
| Peluang OT | 2,6% | 2,9% |
| Garis Asuransi | — (aturan baru) | 233,5 @ 66,5¢ |
| Brier kandang-menang (backtest) | 0,1859 (optimis) | 0,1983 (jujur) |
| Sumber cek silang cedera | PDF + Rotowire (rusak) | PDF + ESPN (B2 ✓) |
| Tes | 613 | 707 (+94) |

---

## 7. File yang berubah

Baru: `engine/cushion.py`, `ingest/player_gamelog.py`,
`tests/test_cushion.py`, `tests/test_espn_injuries.py`,
`tests/test_player_gamelog.py`,
`tests/fixtures/espn_injuries_nba_2026-11-22.json`,
`tests/fixtures/nba_brain/player_gamelog_duren_2027.html`,
`LAPORAN-TAHAP-3-LANGKAH-1B.md` (laporan ini).
Diubah: `engine/nba_sim.py`, `ingest/nba_brain.py`,
`ingest/bbref.py`, `ingest/espn.py`, `config/playstyle.yaml` (v6),
`config/sources.yaml`, `schemas/simulation.schema.json`,
`scripts/fit_nba_params.py`, `scripts/validate_nba_model.py`,
`tests/test_fit_nba.py`, `tests/test_validation.py`,
`tests/test_nba_sim.py`, `tests/test_ingest_nba_brain.py`,
`tests/test_config.py`, `examples/simulation_nba_ATL_DET_2026-11-22.json`,
`LAPORAN-FIT-NBA.md` (§12), `DECISIONS.md`.
Bukti gitignored: `out/fit_nba_params_rolling.json`,
`out/validation_nba_rolling.json`, `out/fit_nba_params_v1.json`,
`out/validation_nba_v1.json`, `data/nba_history/boxscores_all.json`.

---

## 8. Keputusan yang masih menunggu user / reviewer

1. **Adopsi nilai re-fit rolling?** Pergeseran tidak material, jadi
   nilai D12 tetap berlaku tanpa persetujuan ulang. Tapi apakah nilai
   rolling (sigma_total 18,99 vs 18,22; sigma_margin 14,43 vs 13,82)
   sebaiknya DIADOPSI sebagai parameter berjalan adalah keputusan
   terpisah — angka rolling diukur lebih jujur (tanpa look-ahead),
   tapi mengadopsinya mengubah proyeksi + garis Asuransi (bantalan
   ikut menyesuaikan otomatis lewat p74).
2. **BPM_replacement −2,0** adalah asumsi yang didokumentasikan dari
   literatur, bukan hasil fit — menunggu objeksi reviewer (uji
   kepekaan ±1: total bergeser ~±2 poin).
3. **K=10 shrinkage** (D-R2) adalah pilihan desain, belum difit —
   menunggu objeksi reviewer.
4. **`utama_line` spread=None → bantalan 8** (pilihan yang
   didokumentasikan, bukan fail-closed sempurna) — menunggu objeksi
   reviewer.
5. **Rest/Personal tidak dimodelkan sebagai absen** — konsep
   "ketersediaan" di luar cedera adalah pekerjaan lanjutan bila
   diinginkan.
6. **Selisih BBRef vs ESPN soal Duren** (inactive sejak 25 Okt vs OUT
   sejak ~8 Nov) — UNKNOWN penyebabnya; partisipasi memakai BBRef.
