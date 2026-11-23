# LAPORAN WORKER C — v18: Demon Cap per Pemain + Short-Circuit + Wiring

Repo `muse-parlay-analyst`, branch main. Dilaporkan 2026-11-23 (sore WIB).
Config v18. Tes milik worker C: **79/79 lolos**. Tidak ada commit/push/stash
oleh worker C. File milik worker C saja yang disentuh
(`engine/setan_pemain.py`, `engine/nba_analysis.py`,
`scripts/ukur_v18.py`, `tests/test_setan_pemain.py`,
`tests/test_setan_pemain_wiring.py`, `tests/test_short_circuit.py`,
laporan ini). 0 kredit Odds API dipakai.

## 1. Demon per pemain — CAP (SELESAI)

**Rumus baru** (`engine/setan_pemain.py`, `FORMAT_VERSION` 1 → 2):

    pct_setan_i = min(cap_pct, pct_musim_i + boost_pp)

dengan `boost_pp = 12.0`, `cap_pct = 0.50` — dibaca dari config
`setan_pemain.boost_pp` / `setan_pemain.cap_pct` (ditulis worker A);
bila kunci hilang, dipakai default kontrak yang sama (12.0/0.50) dan
`sumber_boost_cap` mencatat "config"/"default" (preseden sama seperti
`DEFAULT_HARGA_MIN_CENTS`). `pct_terbaik_liga` DIPERTAHANKAN sebagai
info saja (tetap dilaporkan, boleh `None`) — tidak lagi dipakai rumus
dan tidak lagi raise bila tak ada kandidat memenuhi ambang. Kontributor
kini membawa `pct_setan_3p` per pemain.

**Ukur ulang DEN@CHI** (fixture = nilai stats.nba.com 23 Nov 2026,
median 233.0, garis bandar 236.5 — dihitung tangan DAN diverifikasi
kode, hasilnya identik):

| | v17 (uniform 54,1%) | v18 (cap per pemain) |
|---|---|---|
| Total setan | 274,14 | **253,71** |
| Geser | — | 20,71 |
| Deviasi | — | +17,21 |
| Attempts | — | 67,30 |
| Poin normal / setan | — | 68,09 / 88,80 (DEN 43,61, CHI 45,19) |

**Kedua kaki nyata MASIH ter-flag rapuh**: U252,5 p_setan_pemain
0,4782; U250,5 0,4366 (keduanya < 0,74). Tapi marginnya tipis:
total setan hanya +1,21 / +3,21 di atas garis (v17: +21,64/+23,64).
Top kontributor: Cameron Johnson 1,91; Matas Buzelis 2,12.

## 2. Flag 3P Volume Risk (SELESAI)

`evaluasi_flag_3par()`: True **hanya bila KEDUA tim** 3PAr ≥
`vonis.tiga_pa_rate_top10_cutoff` (0,457207 — difit worker A, nilai
ke-10 terbesar 3PAr, n=30). Bila salah satu 3PAr/cutoff hilang →
`"tidak_dievaluasi"` (BUKAN False). Kill-switch
`setan_pemain.add_3par_volume_flag` (False → tidak dievaluasi).
3PAr masuk lewat parameter opsional `tiga_pa_rate` (dict per tricode);
wiring membaca `inputs.home/away.stats_season.tiga_pa_rate` dari
artefak (field yang ditambahkan worker A via `ingest/nba_brain.py` +
`ingest/stats_nba.py`). Artefak lama tanpa field itu → flag
"tidak_dievaluasi" — jujur, bukan diam-diam aman.

## 3. Short-circuit veto (SELESAI + DIUKUR)

Setelah Tahap 2 (garis pasar ada) + Tahap 1 (cedera + pace ada),
`engine/nba_analysis.py` memanggil `engine.vonis.evaluasi_veto`
(signature asli dibaca dari disk: `evaluasi_veto(analysis, cfg=None,
pemetaan=None)`). Bila veto menyala: Tahap 3 (sim), 5 (Kalshi), 5b
(news), 5c (setan) DILEWATI; artefak tetap ditulis
(status DATA_INCOMPLETE + blok veto + entri missing
`veto_short_circuit` / `vonis_kuning`); `nilai_vonis` atas artefak
short-circuit mengembalikan KUNING (data_tidak_cukup, alasan veto
ikut tercatat). Blok veto disimpan untuk SEMUA laga.

**Pengukuran jujur** (`out/ukur_short_circuit.json`; metode: sim 2-pass
nyata pada input DEN@CHI tersimpan, offline + satu fetch live gratis
per tahap; 0 Odds API):

| Tahap yang dilewati | Waktu |
|---|---|
| Tahap 3 simulasi (2 pass) | 3,70 dtk (1,68 + 2,02) |
| Tahap 5 Kalshi | 3,12 dtk |
| Tahap 5b news | 0,02 dtk (5 item, ESPN) |
| Tahap 5c pemain 3P (cold) | 0,02 dtk (474 pemain) |
| **Hemat per laga kena veto** | **≈ 6,85 dtk (cache dingin) / 6,83 dtk (hangat)** |

Wall-clock build mock (stub instan, komputasi builder saja): veto
0,038 dtk vs normal 0,057 dtk.

**KEJUJURAN ARSITEKTUR (penting):** pemindaian jup.ag adalah
SLATE-LEVEL (`SlateBuilder.fetch_all`, sekali per slate sebelum
analisis per laga), jadi short-circuit per laga **TIDAK BISA**
memangkas scan jup.ag. Klaim Gemini §2 Q8 "30–50% per slate" TIDAK
berlaku di arsitektur ini. Pemangkasan scan jup.ag butuh
restrukturisasi slate-level — di luar lingkup v18, dicatat sebagai
rekomendasi, bukan klaim. Tidak ada cara sah yang ditemukan untuk
menunda scan untuk slate yang semua laganya kena veto (veto baru bisa
dievaluasi setelah Tahap 1+2 per laga, yang datang setelah scan) —
dilaporkan apa adanya.

## 4. Wiring `nba_analysis.py` (SELESAI)

### 4a. Tahap 1b — TUNGGU_LINEUP (worker A)

Memanggil `engine.vonis.cek_tunggu_lineup` setelah Tahap 1 (signature
asli dibaca dari disk: `cek_tunggu_lineup(analysis, cfg=None,
usg_pemain=None)` → `{"tunggu", "bintang": [{player, team, status,
usg, bpm}], "alasan", "dievaluasi", ...}`; `bintang` dinormalisasi ke
daftar nama, detail dict dipertahankan di `bintang_detail`).
**Keputusan: LANJUTKAN sebagai draf** — sim + kaki tetap dihitung,
status akhir dipaksa HOLD + entri missing, komposer menahan laga
sampai recheck. Alasan: recheck butuh dasar perhitungan.
Menunggu keberatan. Bila fungsi belum ada → missing "belum tersedia",
analisis jalan normal. Bila fungsi melempar → fail-CLOSED (tunggu=True,
HOLD). CATATAN: fungsi A menarik USG live (gratis + cache
satu-proses) hanya bila ada pemain Questionable yang belum lolos lewat
BPM — 0 kredit Odds API.

### 4b. Tahap 3b — Vegas shrinkage (worker B)

Signature asli dibaca dari disk:
`sesuaikan_median(median_model, garis_pasar, ada_sebab_cedera_baru,
cfg=None)` → `{"median_baru", "geser", "diterapkan", "alasan"}` —
fraksi 0,5, ambang gap 5,0, mode `setengah_jarak`. Dihormati
kill-switch `calibration.apply_shrinkage_pre_verdict`. Bila diterapkan:
**geser CDF kaku** (semua kunci lokasi `dist_total` + P(Under) per
garis = CDF mentah di garis−geser via `stress.p_under_digeser`) untuk
kaki Tahap 4 + setan + analisis_wajar + anomali; simulasi mentah
TIDAK disentuh (bukti). Field Vegas disimpan di `analisis_wajar`:
`median_disesuaikan`, `median_mentah`, `geser_vegas`,
`vegas_diterapkan`, `vegas_alasan`, `vegas_sebab_cedera_baru`.

**`ada_sebab_cedera_baru` DIDEFINISIKAN worker C** (B hanya menerima
flag): OUT terkonfirmasi (≥2 sumber) + bintang (BPM ≥
`vonis.tunggu_lineup.bpm_bintang` = 2,0 — ambang dipakai ulang; BPM
dari pemain inputs; USG tidak dipakai — butuh fetch).
**Batasan yang diketahui, menunggu keberatan:** kesegaran
(freshness) tidak bisa dibuktikan dari satu snapshot — OUT jangka
panjang ikut terhitung. Terverifikasi live: IND@NYK mengembalikan
`['T.J. McConnell', 'Tyrese Haliburton']` — Haliburton adalah OUT
sepanjang musim, jadi shrinkage diblokir di laga itu walau "sebab
baru"-nya bukan baru. Bila data/threshold BPM tidak tersedia → tidak
dievaluasi, flag False, missing tercatat.

### 4c. Temuan skema (PERMINTAAN KE KOORDINATOR)

`schemas/nba_analysis.schema.json`: root `additionalProperties: false`
+ enum status hanya OK/HOLD/DATA_INCOMPLETE. Maka blok veto/tunggu
TIDAK bisa di root dan status "tunggu_lineup"/"VETO" tidak bisa
dipakai. Penempatan sementara yang valid vs skema:
`injuries.veto`, `injuries.tunggu_lineup`, field Vegas di
`analisis_wajar` (ketiga objek itu mengizinkan properti tambahan).
**Permintaan:** koordinator menambahkan properti root opsional `veto`
+ `tunggu_lineup` dan nilai status ke skema, lalu blok dipindah ke
root. Worker C TIDAK menyentuh `schemas/`.

**Caveat terkait:** vonis/equilibrium membaca CDF mentah dari
`simulation.markets`, jadi penyesuaian Vegas belum terlihat oleh
mereka sampai worker B/koordinator memutuskan di mana CDF yang
disesuaikan tinggal (butuh perubahan skema).

## 5. Script acceptance test v18 (SELESAI + DIJALANKAN)

`scripts/ukur_v18.py` → `out/ukur_v18.json`. Cara menjalankan:

    python3 scripts/ukur_v18.py [--out out/ukur_v18.json]

Exit 0 walau target gagal (kegagalan tercatat, bukan dipalsukan);
exit 2 hanya bila file input hilang. Tanpa fetch live kecuali USG
gratis+cache di dalam `cek_tunggu_lineup`; 0 kredit Odds API.
Hasil saat dijalankan (config v18, 10 baris):

| Target | Hasil |
|---|---|
| T1 DEN@CHI kedua artefak KUNING via veto AND | **GAGAL (literal)** — verif KUNING ✓ (veto menyala, pemicu veto_rim_protector, demerit tail_fragility+total_tinggi); live `tunggu_lineup` (Powell Questionable, USG 0,26 ≥ 0,24; Claxton BELUM tercatat OUT di snapshot pagi → veto tidak menyala walau garis+pace menyala). **Fungsional AMAN**: kedua baris terblokir dari tiket. Koordinator/user perlu memutuskan apakah tunggu_lineup dihitung "terblokir" untuk target ini. |
| T2 EQ Asuransi: 2–3 kandidat HIJAU → tiket valid x2 | **GAGAL** — hanya 1 kandidat HIJAU+EQ (BOS@GSW verif, U235.5, edge −0,15%); HIJAU lain DAL@UTA tanpa EQ (gate eksekusi volume); OKC/ORL tertahan timing gate. Komposer TIDAK BISA DIJALANKAN: `NameError: _ambang_edge_asuransi` (ticket_composer.py sedang diedit worker A/B). Gate yang mengikat di mana-mana: eksekusi volume (minimum $30 = 2× stake $15). |
| T3 False positive 0–1 (dari 4/5 v17) | **LOLOS — 0/5 KUNING.** Tapi 3/5 ditahan timing gate (OKC, ORL, IND) — bukan KUNING, tapi juga tidak bisa masuk tiket. DET (konteks, bukan penyebut): tunggu_lineup. |
| T4 IND@NYK TUNGGU_LINEUP | **LOLOS** — tunggu=True, bintang Karl-Anthony Towns + Pascal Siakam. Artefak verif tidak memuat IND (hanya OKC/DEN/BOS) — dicatat apa adanya. |
| T5 Efisiensi short-circuit | **GAGAL (literal)** — target Gemini (pangkas scan jup.ag) tidak berlaku di arsitektur slate-level (lihat §3). Yang terukur: hemat ≈6,85 dtk per laga kena veto. |

**Skor: 2/5 LOLOS.** Yang gagal adalah target literal (T1, T5) yang
tidak memperhitungkan tunggu_lineup / arsitektur slate-level, dan T2
yang diblokir komposer rusak + gate volume. Semua angka tercatat di
`out/ukur_v18.json` (per-baris: vonis, veto, EQ Asuransi/Utama,
alasan + catatan metodologi).

## 6. Tes

- Milik worker C: **79/79 lolos**
  (`test_setan_pemain.py`, `test_setan_pemain_wiring.py`,
  `test_short_circuit.py` — 15 tes, termasuk veto menyala →
  Tahap 3/5/5b/5c dilewati + artefak valid + blok veto; veto tidak
  menyala → normal; TUNGGU_LINEUP draf+HOLD; fail-closed saat gate
  melempar; Vegas diterapkan (median 219 vs pasar 225,5 → 222,25,
  geser 3,25, sim mentah tetap 219,0); bintang-OUT memblokir
  shrinkage).
- Hitung tangan di tes: pemain 36,2% + 12pp = 48,2% (< cap 50%);
  pemain 45% + 12pp = 57% → cap 50%; fixture rumus total setan
  236,12; DEN 253,71 + p 0,4782/0,4366.
- Perbaikan fixture selama integrasi: `test_veto_tidak_menyala`
  dipindah dari DET@ATL ke DEN@CHI bergaris rendah — pemetaan rim
  protector v18 yang diregenerasi worker A (position filter +
  MP ≥ 18 + BLK ≥ 1,0; 21 tim) tidak memetakan DET/ATL, sehingga
  `evaluasi_veto` v18 mengembalikan dievaluasi=False di sana
  (perilaku vonis A, bukan wiring). Tes kini juga menegaskan
  `peringatan_parsial` + `kondisi_menyala == ["pace"]` (bukti logika
  AND).
- `test_nba_analysis.py`: 45/46 — satu-satunya gagal adalah
  `test_anomali_total_line_vs_model_median_219_vs_market_225_5`,
  kegagalan LAMA milik worker A (config memindah
  `market_line_check.total_gap_points` → `calibration.lean_to_market_gap`
  tapi `engine/anomaly.py` belum diarahkan ulang; terverifikasi lolos
  di HEAD lewat worktree terpisah).
- **Full suite (snapshot saat tree masih bergerak): 1835 tes,
  141 failures + 134 errors.** Atribusi (bukan milik worker C,
  TIDAK diperbaiki — file worker lain): `test_ticket_composer` 90
  (didominasi `NameError: _ambang_edge_asuransi`), `test_recheck` 37,
  `test_ticket_audit` 36, `test_equilibrium` 31, `test_vonis` 28,
  `test_qa` 24 (didominasi `ConfigError:
  market_line_check.total_gap_points`), `test_skip_awal` 17,
  sisanya kecil. **Nol traceback menyebut file worker C**
  (`engine/setan_pemain.py`, `engine/nba_analysis.py`,
  `scripts/ukur_v18.py`). Angka full suite adalah snapshot — worker
  A/B masih mendaratkan perubahan saat laporan ini ditulis, jadi
  jumlahnya bergeser antar-jalankan (jalankan sebelumnya: 106F+178E).

## 7. Keputusan desain yang menunggu keberatan

1. **TUNGGU_LINEUP = lanjut sebagai draf** (bukan henti setelah
   Tahap 1) — status HOLD + komposer menahan; recheck punya dasar
   perhitungan.
2. **`_sebab_cedera_baru`** = OUT terkonfirmasi ≥2 sumber + BPM ≥ 2,0;
   OUT jangka panjang ikut terhitung (keterbatasan freshness —
   Haliburton). Bila definisi ini salah, shrinkage bisa salah blokir/
   salah terapkan.
3. **Geser CDF kaku** untuk Vegas (bukan simulasi ulang): asumsi
   lokasi distribusi bergeser utuh sebesar `geser`, bentuk tetap.
4. **`pct_terbaik_liga` dipertahankan sebagai info** (bukan dihapus).
5. **Penempatan blok veto/tunggu di `injuries.*`** (sementara,
   menunggu perubahan skema — lihat §4c).
6. **Target 1/5 dinilai literal** di `ukur_v18.py` (tunggu_lineup
   tidak dihitung KUNING; klaim scan jup.ag dicatat tidak berlaku)
   — bila koordinator/user memutuskan sebaliknya, kriteria script
   perlu diubah eksplisit.

## 8. Batasan jujur

- Vonis/equilibrium masih membaca CDF mentah — penyesuaian Vegas
  belum terlihat downstream (§4c).
- Flag 3PAr "tidak_dievaluasi" pada artefak lama tanpa
  `tiga_pa_rate` di `stats_season` (semua artefak 22 Nov).
- Pemetaan rim protector v18 memetakan 21 tim — 9 tim tidak
  terpetakan → veto tidak dievaluasi di laga mereka (perilaku vonis
  A; dicatat, bukan disembunyikan).
- `ukur_v18.py` menilai vonis/equilibrium dari config + kode SAAT
  script dijalankan — hasilnya berubah bila A/B masih mendaratkan
  perubahan (komposer saat ini rusak: NameError).
- Short-circuit menghemat ~6,85 dtk/laga veto — BUKAN 30–50% waktu
  slate; scan jup.ag tidak terpangkas.
- DEN live vs verif menunjukkan sensitivitas snapshot: kabar cedera
  yang masuk belakangan mengubah veto (Claxton) — timing gate
  adalah pertahanan pagi hari, veto pertahanan sore hari.
