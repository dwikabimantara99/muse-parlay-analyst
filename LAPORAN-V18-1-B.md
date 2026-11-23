# LAPORAN PATCH v18.1 — Bagian B (Worker B): Patch #2 "Perangkap Plafon 88,5¢"

Tanggal: 2026-11-23 · Repo: `muse-parlay-analyst`, branch main, HEAD a6a0d93
(config v18 — version TIDAK di-bump; koordinator yang bump ke v18.1)
Spesifikasi: `REFERENSI-PATCH-V18-1-GEMINI.md` §1 Patch #2 + §3 delta,
keputusan user fallback (b) 2026-11-23 15:52 WIB (DECISIONS.md).

## 1. Ringkasan

Masalah (T2 v18): equilibrium safety-first dalam band 80–89¢ selalu memetik
garis plafon (P_final monoton naik terhadap harga) — ketiga kaki Asuransi
terkunci di 88,5¢, pengali maks x1,36, tidak ada tiket Asuransi. Perbaikannya
TANPA melonggarkan satu gate pun:

- **#2a** — `engine/equilibrium.py` kini mengembalikan SEMUA garis valid
  Asuransi (`garis_valid_asuransi`), bukan hanya garis plafon.
- **#2b** — `engine/ticket_composer.py` memilih kombinasi garis valid yang
  memaksimalkan peluang cair gabungan (max Π P_final) dalam jendela
  [2,00x, 2,50x] lewat DP atas bucket log-pengali.
- **Fallback (b)** — bila tidak ada kombinasi ≥ 2,00x, komposer MELAPORKAN
  opsi terbaik di [1,80x, 1,99x] sebagai opsi berlabel, BUKAN tiket.

Hasil pada fixture perangkap (4 laga HIJAU, valid_lines 80,5–88,5¢): v18
terkunci x1,54 tanpa tiket → **v18.1 membentuk tiket x2,04 (4 kaki @82,5¢),
peluang cair gabungan 0,7476**. Runtime compose 10 laga × 9 garis valid:
**0,072 detik** (target < 5 detik). Seluruh suite: **2080 tes, OK** (1 tes
lama diperbarui karena perubahan perilaku yang diinginkan — §6).

## 2. Apa yang dibangun

### 2a. `engine/equilibrium.py` — `garis_valid_asuransi(analysis, cfg=None, ktx=None)`

- Dibangun di atas `nilai_semua_garis` yang sudah ada (TIDAK menduplikasi
  logika gate): memfilter entri `lolos_semua` + dalam band harga Asuransi
  dari `_cfg_band(cfg, "insurance")`.
- Mengembalikan `list[dict] | None` (None = tidak ada tangga / tidak ada
  garis yang dinilai; [] = ada tangga tapi tidak ada garis yang lolos).
  Setiap entri memuat minimal: `garis` (alias `line`), `harga_venue_cents`,
  `p_final`, `p_market`, `ev_pct`, `p_banjir_3p`, `p_banjir_ft` (+ seluruh
  kolom `nilai_semua_garis` lainnya, disalin — pemanggil tidak bisa merusak
  hasil ktx).
- `cari_equilibrium` TIDAK berubah perilakunya (garis plafon safety-first
  tetap default untuk laporan individu; vonis/skip/analysis tidak rusak —
  dibuktikan 2 tes backward-compat + seluruh tes lama equilibrium lolos).
- Tidak ada perubahan skema artefak: `valid_lines` tidak ditulis ke artefak
  (komposer menghitungnya on-demand dari tangga di analysis); format_version
  skema tetap.

### 2b. `engine/ticket_composer.py` — optimasi gabungan + fallback (b)

**Kandidat** (`_kumpulkan_kandidat`): per laga, `valid_lines_ins` dihitung
sekali dari `ktx_ins` yang sama dengan equilibrium (tanpa biaya API — semua
dari tangga artefak); setiap kandidat Asuransi membawa `valid_lines`
(difilter veto parsial: hanya garis ≥ garis_acuan + 3,0), `decision_prob`
+ `decision_prob_sumber` ("p_final" / "market_recheck" /
"market_condong"), dan `leg_awal` (kaki artefak sebelum equilibrium — §8).

**Varian** (`_varian_kandidat_asuransi` → `_varian_dari_garis_valid`): satu
varian per garis valid; kaki dibangun ulang di garis entri via
`rakit_kaki_equilibrium` dengan hasil-equilibrium sintetis (pola yang sama
dengan `_pilih_garis_veto_parsial`), dengan bukti eksekusi SEGAR dari entri
tangga (likuiditas/bid/ask) dan decision_prob dihitung ulang per sumber
(varian condong-ke-market di bawah min_leg_prob dibuang). Laga tanpa
valid_lines menyumbang kandidat v18-nya sebagai varian tunggal (pengecualian
terdokumentasi dari invarian "semua garis dari valid_lines" — garis dasar
itu sudah lolos semua gate komposer).

**Validasi fail-closed** (`_varian_dalam_valid_lines`): setiap garis
kombinasi dicocokkan ke valid_lines (garis sama + harga venue sama dalam
1e-9); varian yang tidak cocok DIBUANG, bukan dipakai. Tes
`test_semua_garis_kombinasi_dari_valid_lines` membuktikan varian palsu
(250,5 @92,5¢) ditolak validator.

**DP** (`_optimasi_asuransi`): bucket DP atas log-pengali kotor (langkah
0,001), satu varian per laga, 2–6 kaki (1 kaki hanya sebagai jalan terakhir,
meniru `_pilih_subset` v18 — menjaga `test_satu_kaki_bila_terpaksa`).
Status: (bucket, jumlah_kaki) → (Σ log decision_prob, Σ log pengali kotor,
pilihan). Satu run DP melayani dua jendela: tiket [mult_min, mult_max] =
[2,00, 2,50] dan fallback [fallback_min, mult_min − 0,01] = [1,80, 1,99].
Seleksi akhir dicek ulang dengan pengali EKSIS dari `combo_multiplier`
(bukan dari bucket). Tie-break tiket: peluang gabungan tertinggi → terdekat
ke tengah jendela (2,25) → kaki lebih banyak → sidik deterministik; tie-break
fallback: peluang gabungan tertinggi → pengali LEBIH TINGGI (paling dekat
menutup stake).

**Fallback (b)** (`_rakit_opsi_fallback`): kunci output baru
`insurance_fallback_option` = `{"label": "OPSI_DI_BAWAH_TARGET",
"multiplier", "joint_p_final", "legs": [...], "alasan", "pengali_min_target",
"pengali_maks_tercapai"}`. Opsi ini TIDAK punya ticket_id/type/stake,
TIDAK masuk ke `insurance_reason` sebagai tiket (insurance_reason hanya
menunjuk ke opsi dengan satu kalimat), dan TIDAK bisa masuk ledger sebagai
tiket (dibuktikan tes: `log_ticket` menolak dengan LedgerError karena
validasi skema tiket duluan). Bila tidak ada kombinasi di [1,80x, 1,99x]:
opsi None + alasan menyebut pengali maks yang tercapai. Kunci ini selalu ada
di hasil compose (None bila tidak ada opsi).

**Wiring `compose_tickets`**: jalur DP aktif bila flag config on (default
True); flag off → jalur `_pilih_subset` v18 persis (rollback eksak, tanpa
opsi fallback). `pengali_maks_asuransi` kini eksak atas ≤ 6 kaki (varian
termurah per laga) — lebih jujur dari v18 yang mengalikan SEMUA kandidat
(sampai 18). Peringatan tumpang-tindih (`_peringatan_tumpang_tindih_opsi`):
bila opsi fallback berbagi laga dengan tiket Utama, peringatan ditambahkan
— tambahan saya sendiri, dari pelajaran DEN (laga yang sama di kedua tiket
membunuh keduanya 2026-11-23). Ringkasan opsi masuk blok ringkasan racik
setelah blok Asuransi.

**`cli.py`**: payload racik kini menyertakan `insurance_fallback_option`
sehingga opsi sampai ke `out/tickets_*.json` (tidak ada skema yang
memvalidasi payload itu; jalur audit/log mengabaikan kunci tambahan).

### Kunci config baru (`config/playstyle.yaml`, section `tickets.insurance` saja)

| Kunci | Nilai | Keterangan |
|---|---|---|
| `expose_all_valid_lines_to_composer` | `true` | Flag DP; false = perilaku v18 persis |
| `composer_objective` | `"max_joint_p_final_within_target_multiplier"` | Nilai lain → ConfigError (fail-closed) |
| `target_multiplier_fallback_min` | `1.80` | Batas bawah opsi fallback; harus 1,0 < x < mult_min, kalau tidak ConfigError |

Target Asuransi [2,00x, 2,50x] TIDAK diubah. `meta.version` tetap 18.
Catatan: diff `playstyle.yaml` juga memuat perubahan section `skip_awal`
milik worker Patch #1 (pekerjaan paralel) — edit saya hanya di section
insurance (24 baris).

## 3. Tes baru (fail-first)

| File | Tes | Bukti fail-first |
|---|---|---|
| `tests/test_equilibrium_v18_1.py` | 11 | Kontrak `garis_valid_asuransi` (semua garis valid dalam band, kunci wajib, band dari config, [] vs None, ktx dipakai ulang) + backward-compat `cari_equilibrium` |
| `tests/test_composer_v18_1.py` | 14 | Regresi perangkap plafon, flag-off perilaku lama, fallback (b) + bukan-tiket + ledger menolak, batas 1,9916 (bukan opsi), tidak-ada-opsi (x1,46), tanpa-kembar (14 laga), semua garis dari valid_lines + validator fail-closed, runtime, kunci config, peringatan tumpang-tindih (2 tes unit) |

**Bukti fail-first** (dijalankan SEBELUM implementasi): 25 tes → 20 gagal
(12 error + 8 failure) karena alasan yang benar (fungsi `garis_valid_asuransi`
belum ada, kunci config/helper belum ada, insurance None di fixture
perangkap); 5 lolos sebagai penjaga perilaku lama. **Sesudah implementasi:
25/25 lolos.** Seluruh suite: **2080 tes OK** (±57 dtk).

## 4. Hasil ukur runtime

| Skenario | Waktu | Target |
|---|---|---|
| compose end-to-end, 10 laga × 9 garis valid | **0,072 dtk** (median 3x) | < 5 dtk |
| compose end-to-end, 15 laga × 9 garis valid (stres) | 0,123 dtk | — |
| DP saja, 10 laga × 9 varian | 25,4 ms (median 5x) | — |

Tes runtime di `test_composer_v18_1.py` menegaskan batas longgar < 30 dtk
dan mencetak waktu aktual (`[ritme] compose 10 laga × 9 garis valid: ...`).

## 5. Verifikasi end-to-end (artefak live + fixture)

- **Fixture perangkap 4 laga** (sigma 5, median 224): v18 → 4 kandidat
  @88,5¢, maks x1,54, insurance None. v18.1 → tiket **x2,04, 4 kaki
  @82,5¢, joint P 0,7476** (optimum unik: 3×82,5+1×84,5 = x1,9916 < 2,00).
- **Fixture fallback** (sigma 11, valid 84,5–88,5¢): tiket tidak terbentuk;
  opsi **x1,81 (3×84,5¢ + 1×86,5¢), joint P 0,7831** — mengalahkan
  4×84,5¢ (x1,85, joint 0,7670) karena tujuan adalah peluang gabungan,
  bukan pengali.
- **Slate 12 laga identik**: optimum DP **6 kaki (5×88,5¢ + 1×86,5¢) =
  x2,01, joint 0,9631** — dengan banyak laga tersedia, DP memilih kaki
  mahal karena memaksimalkan peluang gabungan.
- **Artefak live 22 Nov** (`out/analysis_live_2026-11-22.json`, 7 laga):
  masih 4 laga di-skip pola Denver (skip_awal Patch #1 BELUM mendarat —
  pekerjaan worker lain), tersisa 3 laga dengan pengali maks x1,63 →
  insurance None, opsi fallback None (1,63 < 1,80). **Kesimpulan jujur:
  Patch #2 terbukti di slate sintetis; pemulihan T2 penuh pada slate nyata
  menunggu Patch #1.** Acceptance #2 REFERENSI §3 ("kandidat HIJAU ≥ 4 laga
  setelah perbaikan skip_awal") belum bisa dijalankan sampai Patch #1
  mendarat.

## 6. Tes lama yang diperbarui (1 tes)

`test_ticket_composer.py::TestGateBanjirAsuransi.test_racik_penuh_dengan_kaki_naik_garis`
— ekspektasi v18 (7 kaki @88,5¢ = x2,22) bertentangan langsung dengan
spesifikasi Patch #2 (kombinasi 2–6 kaki). Diperbarui ke optimum baru
(6 kaki: 5×88,5¢ + 1×86,5¢ = x2,01, joint P 0,9634) TANPA melemahkan:
tetap menegaskan format seleksi, climb equilibrium per kaki (86,5¢: 2 rungs
ke 244,5; 88,5¢: 3 rungs ke 246,5), harga per kaki, DAN ditambah asersi
p_win 0,9634 (optimum peluang gabungan). Alasan perubahan didokumentasikan
di komentar tes.

## 7. Keputusan desain yang menunggu keberatan

1. **Batas 6 kaki** (sesuai spesifikasi tugas). Konsekuensi: slate yang
   hanya punya garis valid ≥ 88,5¢ dan ≥ 7 laga tidak lagi bisa membentuk
   tiket x2 (maks 6×88,5¢ = x1,97 → opsi fallback), padahal v18 membentuk
   tiket 7 kaki x2,22 (joint 0,9669 vs 0,9634 — sedikit lebih tinggi).
   Praktiknya tidak mungkin terjadi di slate nyata (tangga punya garis
   valid 80–89¢), tapi ini perubahan perilaku nyata.
2. **Tujuan DP memakai decision_prob, bukan p_final mentah.** Identik
   kecuali di bawah condong-ke-market / recheck-market — di sana
   decision_prob adalah probabilitas yang dipercaya komposer (dan yang
   dipakai `ticket_win_probability`/`_rakit_tiket` untuk p_win).
3. **Batas atas fallback = mult_min − 0,01 (1,99 live)** — diturunkan,
   bukan kunci config tersendiri.
4. **Tie-break fallback memilih pengali LEBIH TINGGI** (paling dekat
   menutup stake); tie-break tiket mempertahankan v18 (terdekat ke tengah
   jendela 2,25).
5. **`pengali_maks` kini eksak atas ≤ 6 kaki** (varian termurah) — teks
   alasan berbeda dari v18 bila kandidat > 6 dan tidak ada tiket; angka
   baru jujur di bawah aturan 6 kaki.
6. **Peringatan tumpang-tindih opsi↔Utama** — tambahan saya (bukan di
   spesifikasi tugas), dari pelajaran DEN.
7. **Laga tanpa valid_lines menyumbang kandidat v18 sebagai varian
   tunggal** — pengecualian terdokumentasi dari invarian valid_lines
   (garis dasar sudah lolos semua gate komposer).

## 8. Batasan jujur

- **Bug climb yang ditemukan saat verifikasi (SUDAH DIPERBAIKI):** varian
  awalnya dibangun dari kaki equilibrium (bukan kaki artefak), sehingga
  climb dirangkai salah (mis. rungs 4, reason "equilibrium+equilibrium").
  Perbaikan: kandidat kini membawa `leg_awal`; varian dibangun ulang dari
  kaki artefak (climb BOS U244,5 kini benar: 2 rungs, "equilibrium").
- **Bucket-straddle teoritis:** dua kombinasi dalam satu bucket 0,001-log
  yang mengangkangi tepi jendela — satu bisa terbuang. Konsekuensi hanya
  jatuh ke opsi fallback, tidak pernah tiket yang salah.
- **Bukti eksekusi usang pada kandidat dasar:** `rakit_kaki_equilibrium`
  mempertahankan likuiditas/bid/ask lama dari garis artefak (quirk v18 di
  luar scope). Varian saya menimpa dengan bukti segar dari entri tangga;
  kandidat dasar masih membawa bukti usang.
- **Interaksi condong/recheck-market:** varian di bawah condong memakai
  decision_prob = p_market (bukan p_final) — tujuan DP mengikuti itu
  (lihat keputusan #2).
- **Tanpa-kembar** dipertahankan (Insurance dulu, Utama dari sisa laga);
  opsi fallback tidak mengambil laga (bukan tiket) sehingga tidak
  memengaruhi alokasi Utama.

## 9. File yang diubah

| File | Perubahan |
|---|---|
| `config/playstyle.yaml` | 3 kunci baru di `tickets.insurance` (+ komentar) |
| `engine/equilibrium.py` | `garis_valid_asuransi` + docstring (+57 baris) |
| `engine/ticket_composer.py` | DP + varian + fallback + wiring (+795/−65 baris) |
| `cli.py` | Payload racik menyertakan `insurance_fallback_option` (+4) |
| `tests/test_equilibrium_v18_1.py` | BARU, 11 tes (306 baris) |
| `tests/test_composer_v18_1.py` | BARU, 14 tes (593 baris) |
| `tests/test_ticket_composer.py` | 1 tes diperbarui (§6) |

Lint: `ruff check` + `black --check` bersih pada semua file yang diubah.
**Tidak ada operasi git** (sesuai instruksi). Config version tetap 18.

## 10. Catatan untuk koordinator

- Selama sesi ini, suite penuh sempat menunjukkan 8 kegagalan
  vonis/tunggu_lineup dari edit `engine/vonis.py` (221 baris) worker Patch
  #5 yang masih berjalan — BUKAN dari Patch #2 (terbukti berdiri sendiri,
  file tidak bersentuhan). Worker tersebut memperbaikinya; run penuh
  terakhir: **2080 tes OK**.
- File saya tidak bertabrakan dengan worker lain (Patch #1 skip_awal,
  Patch #3 rim protector, Patch #5 vonis) kecuali `config/playstyle.yaml`
  (section berbeda) dan `DECISIONS.md` (tidak saya sentuh).
- Acceptance REFERENSI §3 #2 (T2 pulih di slate nyata) menunggu Patch #1
  mendarat, lalu jalankan compose pada artefak live 22 Nov.
