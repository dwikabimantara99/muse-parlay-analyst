# Laporan Tahap 2b — Fetcher + Demo Slate

Tanggal: 20–21 Nov 2026 (selesai 21 Nov 2026 ~00:12 WIB).
Ruang lingkup: paket `ingest/` (satu fetcher per sumber), perakit slate,
`cli.py analyze` (SOP langkah 2–3), validasi, devig untuk p_market.
Simulasi model, blend, dan penyusunan tiket adalah Tahap 3+.

## Ringkasan hasil

| Item | Hasil |
| --- | --- |
| Fetcher | 13 modul di `ingest/` (lihat `ingest/README.md`) |
| `cli.py analyze` | Tersedia — tarik data + validasi, tulis `out/analysis_<slate_id>.json` |
| Devig | `american_to_decimal` + `devig` di `engine/devig.py`; `blend` tetap stub Tahap 3 |
| Demo NBA | 3 laga, 3 OK, 0 HOLD, 0 DATA_INCOMPLETE |
| Demo EPL | 3 laga, 0 OK, 3 HOLD (cedera 1 sumber; B2 butuh 2), 0 DATA_INCOMPLETE, 3 TANPA_XG |
| Spread/total NBA di jup.ag | **TIDAK ADA** (pindai penuh, bukti di bawah) |
| Kualitas | black 85 file bersih, ruff bersih, unittest 399/399 lulus |
| Kunci API | Tidak ada kebocoran (Jupiter + Odds API diperiksa) |

## Demo slate NBA — 3 OK

`examples/slate_demo_nba_2026-11-20.json` →
`examples/analysis_demo_nba_2026-11-20.json`.

Laga: Wizards–Bulls, Hornets–Hawks, Suns–Jazz. Semua 6 pasar moneyline
punya p_market dari Odds API devig (`comparison_source:
odds_api_devig`), jup_markup 0,5¢. Sumber per laga: Jupiter (1),
Odds API (2), stats.nba.com (1), BBRef (2), Official NBA Injury
Report (1), Rotowire (2), ESPN (2). Odds API: 1 panggilan, 3 kredit
(satu panggilan slate = 3 kredit, bukan 1 — koreksi terhadap asumsi
awal 2b).

## Demo slate EPL — 3 HOLD (bukan gagal fetch)

`examples/slate_demo_epl_2026-11-21.json` →
`examples/analysis_demo_epl_2026-11-21.json`.

Laga: Man City–Fulham, Chelsea–Leeds, Newcastle–Arsenal. Ketiganya
HOLD dengan alasan "cedera: hanya 1 sumber (B2 butuh 2 sumber)" —
mesin bekerja fail-closed sesuai aturan, bukan kegagalan fetch.
Ketiganya berlabel TANPA_XG (Understat maintenance).

126 pasar (spread 60, total 54, moneyline 9, BTTS 3); 69 punya
p_market: Odds API devig 9, ESPN odds devig 8, Kalshi 52 — semuanya
berlabel `PEMBANDING_KALSHI` sesuai keputusan user. Odds API: 1
panggilan, 0 kredit (cache hit 30 menit, D3).

## Spread/total NBA di jup.ag — TIDAK ADA (pindai penuh)

`examples/nba_lines_check_2026-11-20.json`
(`ingest/check_nba_lines.py`, 20 Nov 2026 16:32:46 UTC):

- 5.116 event sports dipindai (52 halaman, `scan_complete: true`,
  mode keyed, 0 retry), 153 event NBA, 99 laga NBA.
- **0 pasar spread, 0 pasar total** di semua 99 laga (tiap laga hanya
  2 pasar moneyline).
- Cek ulang terjadwal 21 Nov 2026 pukul 04:00 / 06:00 / 07:00 / 09:00
  WIB (3 jam & 1 jam sebelum tip-off 9 laga malam ini) — pasar
  mungkin baru dibuka dekat tip-off. Jadwal per laga ada di
  `recheck_schedule` pada file bukti.

## Sumber baru: Fantasy Premier League API — BUTUH RATIFIKASI USER

`ingest/premier_league.py::fetch_injuries_fpl` menarik status
ketersediaan pemain EPL (672 pemain, 20 tim, status a/u/i/d/s) dari
endpoint resmi `fantasy.premierleague.com/api/bootstrap-static/`.
Sumber ini dibangun koordinator 2b karena endpoint ESPN injuries
selalu mengembalikan list kosong dan Rotowire gratis mengabaikan
filter liga — tanpanya laga bola selalu DATA_INCOMPLETE. Dicatat
tier 1 (produk resmi Premier League yang sama), **belum ada di
`sources.yaml` v3 — menunggu ratifikasi user**.

Catatan: FPL adalah status ketersediaan dari game fantasy resmi,
bukan laporan medis cedera. Dan ratifikasi pun tidak membuat EPL
OK — B2 tetap butuh sumber cedera kedua, yang belum ada.

## Temuan integrasi (koordinator 2b)

1. **Transport keep-alive.** urllib memaksa header `Connection:
   close`; kombinasi itu dengan egress proxy VM memotong respons
   api.jup.ag ~50–70% (diukur: tanpa header 6/6 berhasil, dengan
   header 1/6). Semua fetch kini memakai opener keep-alive bersama
   (`ingest/common.py::open_url`). Pindai penuh: 52 halaman, 52
   percobaan, 0 retry.
2. **Rate limiter dibagi.** Sebelumnya tiap pemanggilan membuat
   limiter baru sehingga tidak ada jeda antar pemanggilan — Kalshi
   membalas 429 saat demo. Kini satu limiter per modul.
3. **Disambiguasi laga ganda.** Pasangan tim yang sama bisa main dua
   kali (rematch); pencocokan hanya by tim mengambil harga rematch
   (Suns–Jazz memakai harga 29 Nov). Kini dipakai yang waktunya
   terdekat (`_closest_by_time`).
4. **Garis spread dibalik tanda.** `sportsLine` adalah garis untuk
   tim pertama di `outcomes`; pasar tim kedua dibalik tandanya saat
   normalisasi.
5. **jup_markup dari fallback midpoint menyesatkan** di pasar
   ilikuid (teramati 41,5–44¢ palsu). Entri slate mencatat
   `jup_markup_source` ("book" vs "midpoint") — Tahap 3 wajib
   mengabaikan/menandai markup bersumber "midpoint" pada pasar
   ilikuid.
6. **Parser Understat belum terverifikasi live** (situs maintenance
   sejak probe 2a; hanya dites dengan fixture sintetis). Begitu
   Understat kembali, jalankan tes kesehatan scraper sebelum memakai
   xG untuk keputusan.

## Kesenjangan yang diketahui

- Cedera bola hanya 1 sumber (FPL) → EPL HOLD; sumber kedua belum
  ada. LaLiga tanpa sumber cedera sama sekali.
- `lineup` selalu `null` (tidak ada fetcher lineup di kontrak 2b).
- `nba_player_impact` belum punya fetcher (dibutuhkan Tahap 3).
- LaLiga: tanpa fixtures PL & odds ESPN (EPL saja); Kalshi LaLiga
  hanya moneyline; discovery hanya EPL.

## Odds API — pemakaian kredit

Total terpakai 13 kredit (sisa 487/500 menurut laporan koordinator).
Yang tercatat di bukti: verifikasi awal 1 kredit, demo NBA 3 kredit,
demo EPL 0 kredit (cache). 9 kredit sisanya dipakai panggilan
pengembangan worker tanpa catatan per-panggilan — angka 487 belum
terverifikasi dari header tersimpan (cache hanya menyimpan body,
bukan header). Panggilan Odds API berikutnya akan mengonfirmasi sisa
kuota dari header `x-requests-remaining`.

## Keputusan yang masih terbuka untuk user

1. Ratifikasi FPL sebagai sumber cedera bola tier 1 + penambahan ke
   `sources.yaml` v3.
2. Sumber cedera bola kedua (agar EPL bisa OK, bukan HOLD).
3. Hasil cek ulang spread/total NBA (21 Nov pagi) — menentukan
   apakah Alt Under NBA bisa dianalisis dari jup.ag.

## Perubahan lain dalam commit ini

- `DECISIONS.md`: keputusan user 20 Nov 23:08 WIB (football-data
  BOLEH dengan syarat; bobot pembanding + label PEMBANDING_KALSHI;
  verifikasi spread/total NBA).
- Stub fetcher FotMob/Sofascore dihapus (sumber ditolak user).
- `schemas/match_data.schema.json`: kunci opsional `labels`
  (aditif, backward-compatible).
- `probes/out/understat_status.json` menjadi state runtime
  (untracked) — ditulis cek harian, bukan bukti yang di-commit.
