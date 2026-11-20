# Hasil Probe Tahap 2a

Tanggal probe: **2026-11-20** (rangkaian terakhir selesai 22:34 WIB).
Semua angka di bawah berasal dari `probes/out/*.json` — bukan dari ingatan
model. Total **44 request** ke 13 sumber.

Ringkasan verdict: **PAKAI 8, CADANGAN 3, JANGAN 2.**

| Sumber | Jenjang | Bisa diakses dari VM? | Format | Batas / rate limit | Data yang tersedia | Catatan risiko |
|---|---|---|---|---|---|---|
| Jupiter Prediction API | 1 | Ya (4/4 request HTTP 200, mode keyed) | JSON REST | Keyed 1 RPS (jeda 1,1 dtk); fallback keyless 0,5 RPS (jeda 2,2 dtk) | 100 event sports, 5.720 pasar; pencarian "NBA" 10 hasil; detail event + pasar; harga Yes/No per pasar | API masih beta, bisa berubah. HANYA BACA — endpoint order/posisi/claim dilarang (K3) |
| Polymarket API | 2 | Ya (3/3 HTTP 200) | JSON REST | UNKNOWN (tidak ada header rate limit terlihat) | Gamma events + markets; CLOB markets (mengembalikan dict, bukan list) | Pembanding independen (P2): hanya dipakai bila provider asal pasar jup.ag BUKAN polymarket |
| Kalshi API | 2 | Ya (3/3 HTTP 200) | JSON REST | Header: limit 600, remaining 550, reset 0.25 | Events, markets, series (16.757 item) | Pembanding independen (P2): hanya dipakai bila provider asal pasar jup.ag BUKAN kalshi |
| The Odds API | 2 | Ya, endpoint terjangkau (2/2 HTTP 401 — tanpa key) | JSON REST (butuh key) | 450 kredit/bulan, peringatan 80% (D3) — belum bisa diverifikasi tanpa key | Belum ada (key dibutuhkan) | Butuh `ODDS_API_KEY` dari user. 1 panggilan bisa makan beberapa kredit; cache 30 menit, maks 2 panggilan per analisis |
| nba.com / stats.nba.com | 1 | Sebagian (2/3 HTTP 200) | JSON REST | UNKNOWN (tidak ada header rate limit terlihat) | stats.nba.com `leaguestandingsv3` + `scoreboardv2` (200); CDN `todaysScoreboard_00.json` 403 | stats.nba.com dikenal memblokir IP cloud — bila gagal, ESPN (jenjang 2) jadi utama untuk jadwal/statistik |
| ESPN JSON publik | 2 | Ya (3/3 HTTP 200) | JSON REST | UNKNOWN (tidak ada header rate limit terlihat) | NBA scoreboard (4 event), EPL scoreboard (7 event), NBA injuries (28 tim dengan cedera) | — |
| Basketball-Reference | 2 | Ya (2/2 HTTP 200, jeda 4 dtk) | HTML (scraping) | Tidak dipublikasikan; dikenal membatasi request agresif | Halaman advanced NBA 2026: 2.214.959 karakter, penanda BPM + MP ditemukan; standings 290.478 karakter | Scraping HTML rapuh bila format berubah; butuh tes kesehatan scraper + cache agresif |
| Official NBA Injury Report | 1 | Ya (PDF resmi terverifikasi HTTP 200) | PDF | UNKNOWN | PDF harian per 15 menit: `ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-20_12_00AM.pdf` (application/pdf); halaman resmi `official.nba.com/nba-injury-report-2026-27-season/` | PDF harus di-parse otomatis; format PDF bisa berubah. Cedera wajib dicek silang min 2 sumber (B2): ESPN + Rotowire |
| Rotowire (cedera NBA) | 2 | Ya (2/2 HTTP 200) | HTML (scraping) | UNKNOWN (tidak ada header rate limit terlihat) | injury-report.php: 346.302 karakter, penanda "Out" ditemukan; endpoint tables hanya 43 karakter | Scraping HTML rapuh bila format berubah; butuh tes kesehatan scraper |
| Understat (xG) | 2 | Tidak (situs maintenance) | — (halaman maintenance) | UNKNOWN | Tidak ada saat probe: kedua liga mengembalikan halaman "We will come back soon" (26.719 karakter, identik) | Rantai xG B4 putus sementara; perlu dicek ulang di 2b — situs bisa kembali |
| Sofascore | 2 | Tidak (3/3 HTTP 403) | — (diblokir) | Header `Retry-After: 0`; tantangan bot aktif | Tidak ada: scheduled-events, seasons, live events semua 403 | API tidak resmi + tantangan bot dari VM ini; jangan dipakai kecuali ada cara akses sah |
| FotMob | 2 | Ya (2/2 HTTP 200) | JSON REST (API tidak resmi) | UNKNOWN (tidak ada header rate limit terlihat) | `data/matches?date=20261120`: 86 liga; `data/leagues?id=47` (EPL): fixtures, overview, seasons | API tidak resmi, bisa berubah/diblokir tanpa pemberitahuan. **Ketentuan FotMob melarang pengambilan otomatis tanpa izin — pemakaian perlu diputuskan user (risiko ToS)** |
| Situs/data resmi liga (bola) | 1 | Sebagian (5/6 liga terjangkau; 1/6 JSON) | Campuran JSON + HTML | UNKNOWN | Premier League: endpoint JSON publik terverifikasi (fixtures, 7.379 karakter). UEFA, LaLiga, Bundesliga, Ligue 1: hanya halaman HTML (bukan JSON langsung). Serie A: 307 di kedua URL | Situs resmi liga umumnya tidak menyediakan API JSON publik yang stabil; halaman HTML/JS berat dan bisa berubah. xG resmi hampir tidak ada |

## Tabel Jupiter: provider asal per jenis pasar

Sampel: `/events?category=sports&limit=100` → 100 event, **5.720 pasar**,
31 jenis pasar. **Semua pasar dalam sampel berasal dari Polymarket — 0 pasar
Kalshi.** (Apakah Kalshi muncul di luar sampel 100 event ini: UNKNOWN.)

| Jenis pasar (`sportsMarketType`) | Provider | Jumlah pasar |
|---|---|---|
| soccer_exact_score | polymarket | 1.147 |
| soccer_team_totals | polymarket | 744 |
| spreads | polymarket | 640 |
| totals | polymarket | 576 |
| (null / tanpa tipe) | polymarket | 409 |
| soccer_first_half_team_totals | polymarket | 320 |
| first_half_totals | polymarket | 310 |
| soccer_team_total_corners | polymarket | 208 |
| moneyline | polymarket | 195 |
| total_corners | polymarket | 182 |
| soccer_player_goals_plus_assists | polymarket | 177 |
| soccer_player_goals | polymarket | 158 |
| second_half_totals | polymarket | 130 |
| soccer_halftime_result | polymarket | 93 |
| soccer_anytime_goalscorer | polymarket | 79 |
| soccer_first_half_total_corners | polymarket | 78 |
| first_half_spreads | polymarket | 72 |
| soccer_first_to_score | polymarket | 60 |
| both_teams_to_score | polymarket | 31 |
| f1_race_winner | polymarket | 23 |
| both_teams_to_score_first_half | polymarket | 20 |
| tennis_match_totals | polymarket | 18 |
| soccer_second_half_team_totals | polymarket | 16 |
| handicap | polymarket | 12 |
| soccer_second_half_total_corners | polymarket | 6 |
| tennis_set_totals | polymarket | 6 |
| soccer_second_half_result | polymarket | 3 |
| soccer_first_corner | polymarket | 2 |
| soccer_game_corners_odd_even | polymarket | 2 |
| tennis_game_handicap | polymarket | 2 |
| both_teams_to_score_second_half | polymarket | 1 |
| **Total** | | **5.720** |

`sportsLine` tercatat per jenis pasar, contoh: spreads −1.5/−2.5/−3.5/−4.5/−5.5;
totals 0.5–4.5; total_corners 7.5–13.5; tennis_match_totals 21.5/22.5/23.5
(selengkapnya di `out/jupiter.json`, kunci `sports_line_samples`).

**Implikasi untuk aturan P1–P4:** karena (dalam sampel ini) semua pasar sports
jup.ag berasal dari Polymarket, pembanding "provider prediksi lain" (Kalshi)
hampir tidak pernah berlaku untuk sports — pembanding independen utama adalah
sportsbook lewat The Odds API (devig). Bila pasar Kalshi muncul di sampel yang
lebih besar, pembanding Polymarket berlaku untuk pasar itu.

## Verdict per sumber

| Verdict | Sumber |
|---|---|
| **PAKAI** | Jupiter, Polymarket, Kalshi, ESPN, Basketball-Reference, Official NBA Injury Report, Rotowire, FotMob (dengan catatan ToS) |
| **CADANGAN** | The Odds API (butuh key dari user), nba.com/stats.nba.com (CDN 403, stats bekerja), situs resmi liga (hanya Premier League JSON) |
| **JANGAN** | Understat (maintenance — cek ulang di 2b), Sofascore (403 tantangan bot) |

## Temuan kunci

1. **D4 TERJAWAB — Official NBA Injury Report ditemukan dan terverifikasi.**
   URL resmi: halaman `https://official.nba.com/nba-injury-report-2026-27-season/`
   (HTTP 200) dengan tautan PDF per 15 menit di
   `https://ak-static.cms.nba.com/referee/injury/Injury-Report_YYYY-MM-DD_HH_MMAP.pdf`
   (PDF 2026-11-20 12:00 AM terverifikasi HTTP 200, `application/pdf`).
   Jadwal update dari halaman resmi: *"Reports are updated on a continual
   basis throughout the day"*; tim wajib menyerahkan laporan hari pertandingan
   antara 11 am–1 pm waktu lokal (8–10 am untuk tip-off jam 5 pm atau lebih
   awal). Catatan: `nba.com/injuries` 404 dan widget
   `stats.nba.com/js/data/widgets/injuries.json` 404 — sumber resminya ada
   di `official.nba.com`, bukan `nba.com`.
2. **Jupiter bekerja dalam mode keyed** (4/4 HTTP 200, tanpa fallback).
   Semua pasar sports dalam sampel berasal dari Polymarket (lihat tabel di atas).
3. **stats.nba.com bekerja dari VM ini** (2/2 endpoint 200) — bertentangan
   dengan ekspektasi blueprint bahwa IP cloud diblokir; hanya CDN scoreboard
   yang 403.
4. **FotMob bekerja lewat `/api/data/`** (bukan path `/api/` lama yang 404) —
   tapi ketentuan layanannya melarang pengambilan otomatis tanpa izin;
   pemakaian perlu diputuskan user.
5. **Rantai xG B4 sedang putus di ujung pertama:** Understat maintenance,
   Sofascore diblokir 403 — FotMob menjadi satu-satunya kandidat xG yang
   bekerja saat ini (dengan catatan ToS di atas). Tanpa xG, aturan B4
   berlaku: model berbasis gol (Dixon-Coles), label TANPA_XG, ambang +5 poin
   lebih ketat, dilarang masuk tiket Insurance.

## Daftar UNKNOWN

- Apakah pasar Kalshi muncul di jup.ag di luar sampel 100 event (0 dalam sampel).
- Rate limit dan pemakaian kredit The Odds API yang sebenarnya (belum bisa
  diverifikasi tanpa key).
- Apakah Understat maintenance sementara atau permanen — cek ulang di 2b.
- Apakah Sofascore bisa diakses dengan header lebih lengkap / dari IP lain
  (dari VM ini: tantangan bot, 403 di semua endpoint).
- Endpoint JSON resmi untuk UEFA, LaLiga, Serie A, Bundesliga, Ligue 1
  (tidak ditemukan); penyebab 307 Serie A (loop redirect) tidak diketahui.
- Rate limit ESPN, Polymarket, Basketball-Reference, Rotowire, FotMob
  (tidak dipublikasikan / tidak ada header terlihat saat probe).
- Isi endpoint tables Rotowire (hanya 43 karakter — dicatat apa adanya).
- Penyebab 403 CDN scoreboard nba.com (blokir cloud vs path usang).
