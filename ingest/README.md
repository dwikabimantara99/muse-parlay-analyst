# ingest — Penarik data (Tahap 2b)

Satu fetcher per sumber. Semua fetcher mengembalikan `FetchResult` dan
tidak pernah melempar untuk kegagalan data (gagal → `ok=False` + `error`
apa adanya; pemanggil yang memutuskan status `DATA_INCOMPLETE`/`HOLD`).

## Kontrak FetchResult (`ingest/common.py` — JANGAN DIUBAH)

```python
FetchResult(
    source: str,        # nama sumber aktual, mis. "ESPN"
    tier: int,          # jenjang 1/2/3 (DECISIONS.md B)
    fetched_at: str,    # ISO 8601 UTC saat fetch
    ok: bool,           # True bila data berhasil diambil
    data: Any = None,   # payload ternormalisasi (bentuk per fetcher)
    error: str | None = None,   # alasan gagal (ok=False)
    credits_used: int = 0,      # hanya The Odds API
    extra: dict = {},           # info tambahan (mode, cache, dll.)
)
```

Helper bersama di `common.py`: `HttpClient` (User-Agent `muse-parlay-analyst
ingest/2b`, timeout 30 dtk), `RateLimiter` per host, `DiskCache` JSON di
`out/cache/` (kunci = hash SHA-256 URL), `load_dotenv` (key dari `.env`,
tidak pernah di-print), `JupiterClient` (keyed 1 RPS + fallback keyless
0,5 RPS; HANYA endpoint baca GET).

TRANSPORT: semua fetch memakai opener keep-alive bersama (`open_url` di
`common.py`), BUKAN `urllib.request.urlopen` langsung. urllib memaksa
header `Connection: close`; kombinasi header itu dengan egress proxy VM
memotong respons api.jup.ag ~50–70% dari waktu
(IncompleteRead/RemoteDisconnected — diukur worker pasar 2b, 2026-11-20:
tanpa header itu 6/6 berhasil, dengan header 1/6). Opener ini mengirim
`Connection: keep-alive` (perilaku default HTTP/1.1, sama seperti
curl/requests). `jupiter.py` tetap me-retry tiap halaman sampai 8x
sebagai mitigasi kedua; `extra` pemindaian mencatat `total_attempts` +
`retried_pages` (pindai penuh 2026-11-20: 52 halaman, 52 percobaan,
0 retry — perbaikan terbukti live).

JEDA: tiap modul memakai SATU `RateLimiter` tingkat modul (`_LIMITER`)
yang dibagi semua pemanggilannya. Sebelumnya tiap pemanggilan membuat
limiter baru sehingga tidak ada jeda ANTAR pemanggilan — slate memanggil
fetcher berkali-kali (Kalshi: 3 series; Polymarket: 1x per pasar) dan
Kalshi membalas 429 (teramati saat demo 2b). `RateLimiter.wait()` melacak
per host, jadi satu limiter aman untuk beberapa host modul itu.

## Daftar fetcher

| Modul | Fungsi utama | Sumber | Jenjang | Jeda | Cache |
| --- | --- | --- | --- | --- | --- |
| `jupiter.py` | `fetch_sports_markets()` / `fetch_sports_events()` (SEMUA event, paginasi; safety cap 10000) | Jupiter Prediction API | 1 | 1,1 dtk keyed / 2,2 dtk keyless | 300 dtk |
| `odds_api.py` | `fetch_odds(sport_key, markets, regions)` | The Odds API | 2 | 2,0 dtk | 1800 dtk (D3: 30 mnt) |
| `kalshi.py` | `fetch_moneyline_markets / fetch_spread_markets / fetch_total_markets(league)` + `kalshi_probability(market)` | Kalshi API | 2 | 1,0 dtk | 300 dtk |
| `polymarket.py` | `find_token_for_jup_market(jup_market)`, `fetch_orderbook(token_id)`, `compute_jup_markup(jup, mid)` | Polymarket CLOB | 2 | 0,5 dtk | 300 dtk |
| `espn.py` | `fetch_scoreboard(sport, date)`, `fetch_injuries_nba()`, `fetch_odds_football(league)` | ESPN | 2 | 1,0 dtk | 600 dtk |
| `stats_nba.py` | `fetch_scoreboard(date)`, `fetch_standings()` | stats.nba.com | 1 | 1,0 dtk | 600 dtk |
| `nba_injury_pdf.py` | `fetch_report(date=None)` | Official NBA Injury Report | 1 | 1,0 dtk | 900 dtk |
| `rotowire.py` | `fetch_injuries()` | Rotowire | 2 | 2,0 dtk | 900 dtk |
| `bbref.py` | `fetch_team_advanced(season=2026)` | Basketball-Reference | 2 | 4,0 dtk | 21600 dtk (6 jam) |
| `premier_league.py` | `fetch_fixtures()`, `fetch_injuries_fpl()` | Premier League (JSON resmi) + Fantasy Premier League API | 1 | 1,0 dtk | 1800 dtk |
| `understat.py` | `fetch_xg(league, season)` + `read_status()` / `is_available()` | Understat | 2 | 3,0 dtk | 3600 dtk |
| `matching.py` | `teams_match(a, b, sport)`, `normalize_team(name, sport)` | — (murni, tanpa network) | — | — | — |
| `check_nba_lines.py` | `python -m ingest.check_nba_lines [--date YYYY-MM-DD] [--out PATH]` | Jupiter (pindai spread/total NBA) | 1 | seperti jupiter | 300 dtk |

Catatan per fetcher:

- **Jupiter**: harga BELI (ask) dipakai sebagai `yes_price_cents` /
  `no_price_cents` (harga yang dibayar user). `outcome` = JUDUL pasar
  (nama tim untuk moneyline/spread, "Over"/"Under" untuk total, "Both
  Teams to Score" untuk BTTS) — bukan kata sisi; slate memecahkan sisi
  dari judul + tim laga. `sport` = "nba"/"football"/"other". Harga
  dibaca dari `pricing.buyYesPriceUsd` / `buyNoPriceUsd` (micro-USD,
  1¢ = 10.000; nilai 0 = tidak ada kuotasi → None) — nama field
  DIVERIFIKASI dari payload asli probe. Paginasi: window
  `start`/`end` + `limit` maks 100 per halaman, `pagination.hasNext`;
  parameter `offset` DIABAIKAN server. `fetch_sports_markets()`
  memindai SEMUA halaman (default cap 10000 event; pindai 2026-11-20
  menemukan API punya >2000 event, jadi cap lama 2000 memotong data)
  — JANGAN dibatasi 100 (keputusan user 2b). Pasar ternormalisasi meneruskan
  `clobTokenIds`/`outcomes` mentah agar `jup_markup` tidak perlu
  pencarian Gamma per pasar. **Garis spread**: `sportsLine` adalah garis
  PASAR (untuk tim pertama di `outcomes`) — pasar tim kedua adalah sisi
  cover dan garisnya DIBALIK tandanya saat normalisasi (mis. "Arsenal
  +2.5" 99¢ tercatat sebagai +2.5, bukan -2.5). Tanpa pembalikan, dua
  pasar berbeda jatuh ke satu kunci slate dan harga cover dibandingkan
  dengan pembanding -2.5 (bug demo 2b).
- **Odds API**: `sport_key` "basketball_nba"/"soccer_epl"; region `eu`;
  1 panggilan per sport per analisis (maks 2/analisis, D3); kredit dari
  header `x-requests-last` (0 bila dari cache). Bookmaker Pinnacle
  diutamakan, bila tidak ada dipakai bookmaker eu pertama.
- **Kalshi**: harga dari `*_dollars` bid/ask (bukan `last_price`);
  `kalshi_probability` = midpoint bid/ask. Garis spread adalah MAGNITUDO
  ("X wins by more than 1.5" → line 1.5); hanya ada pasar Over untuk
  total. LaLiga hanya moneyline (spread/total → `ok=False`).
- **Polymarket**: HANYA untuk `jup_markup` (midpoint CLOB vs harga
  jup.ag) — bukan pembanding `p_market` (P2). `find_token` memakai
  passthrough `clobTokenIds` pasar ternormalisasi (tanpa network);
  Gamma public-search hanya bila token tidak dibawa pasar. Token Yes
  dipilih dari INDEKS judul di `outcomes`, bukan selalu [0] (pasar
  2-outcome membagi satu pasangan token — memakai [0] untuk kedua tim
  menghasilkan markup palsu ~15–37¢). **Batas fallback midpoint**:
  bila orderbook KOSONG, `fetch_orderbook` memakai endpoint `/midpoint`
  — tetapi untuk pasar yang praktis tidak diperdagangkan (mis. spread
  bola -4.5/-5.5), nilai `/midpoint` tidak mencerminkan peluang
  sebenarnya (teramati: mid 42,5¢ untuk pasar ~0,5%), sehingga
  `jup_markup` dari fallback itu menyesatkan (41,5–44¢). Entri slate
  mencatat `jup_markup_source` ("book" vs "midpoint") — Tahap 3 wajib
  mengabaikan/menandai markup bersumber "midpoint" pada pasar ilikuid.
  Kuotasi jup.ag satu sisi (ask tanpa bid, `sellYesPriceUsd` 0) juga
  menandai harga basi — Tahap 3 sebaiknya membawa `sellYesPriceUsd`
  sebagai `yes_bid_cents` untuk mendeteksinya.
- **ESPN odds**: HANYA BOLA (scoreboard EPL; NBA tidak punya odds di
  ESPN). Odds Amerika disimpan sebagai STRING ("-150") — slate
  mengonversi ke angka sebelum devig. DraftKings diutamakan.
- **BBRef**: `season` = tahun musim berakhir (2027 = musim berjalan
  2026-27; default 2026 = musim 2025-26). Slate memanggil dengan 2027.
- **Premier League**: endpoint persis dari probe
  (`footballapi.pulselive.com/football/fixtures?comps=1&...`). Arsip
  dimulai dari 1992 (13.546 entri, terurut menaik), jadi
  `fetch_fixtures()` mencari halaman masa kini dengan pencarian biner
  berdasarkan kickoff (hanya memakai parameter halaman dari URL probe —
  tidak ada parameter baru yang ditebak) dan mengembalikan fixtures dalam
  jendela ±7 hari dari sekarang. Tidak ada `fetch_teams()` (tidak ada
  endpoint tim yang terverifikasi probe).
- **Fantasy Premier League API** (`fetch_injuries_fpl`): cedera/
  ketersediaan pemain EPL dari endpoint resmi
  `fantasy.premierleague.com/api/bootstrap-static/` (672 pemain, 20
  tim, status a/u/i/d/s). Sumber BARU dari integrasi 2b (koordinator):
  endpoint ESPN injuries selalu mengembalikan list kosong dan Rotowire
  gratis mengabaikan filter liga, sehingga tanpa sumber ini laga bola
  selalu DATA_INCOMPLETE. Dicatat tier 1 (produk resmi Premier League
  yang sama) — BELUM ADA di `sources.yaml` v3, BUTUH RATIFIKASI USER.
  Dengan 1 sumber ini, laga bola menjadi HOLD (B2 butuh 2 sumber),
  bukan DATA_INCOMPLETE.
- **matching**: NBA menerima tiga bentuk nama tim ke satu kanonik
  kota: julukan ("Lakers"), tricode ("LAL", dari Rotowire), dan nama
  lengkap ("Los Angeles Lakers", dari stats.nba.com/ESPN/PDF/BBRef).
- **check_nba_lines**: pindai pasar spread/total NBA di SELURUH event
  sports jup.ag (bukan sampel 100). Laporan JSON berisi per laga
  (garis, jumlah pasar, tip-off) + `recheck_schedule` (cek ulang 3 jam
  & 1 jam sebelum tip-off — pasar mungkin baru dibuka dekat tip-off).
  Jalankan ulang terjadwal bila hasil pertama 0 pasar.
- **Understat**: lihat "Gate Understat" di bawah.
- **FotMob / Sofascore**: DITOLAK user — tidak ada fetchernya di paket
  ini (file stub dihapus di 2b; daftar `rejected` di `sources.yaml`).

## Perakit slate (`slate.py`)

`build_slate(sport, date, matches=None, ...)` /
`build_nba_slate(date, ...)` / `build_football_slate(date, league="EPL", ...)`.

- `matches`: list `{home, away}` (+ opsional `match_id`, `start_time`,
  `league`) untuk memfilter; `None` = semua laga hari itu dari sumber
  jadwal (NBA: scoreboard stats.nba.com; bola EPL: fixtures PL).
- Semua fetch dilakukan SEKALI per slate lalu dipakai ulang per laga.
- Fetcher modul lain di-import MALAS: bila modul/fungsi belum ada, fetch
  itu dicatat gagal (`modul_belum_tersedia` /
  `fungsi_belum_tersedia`) dan slate tetap dirakit (fail-closed per fetch).
- Output: `{slate_id, sport, slate_date, generated_at, matches: [...],
  summary: {matches, ok, data_incomplete, hold, model_only, tanpa_xg},
  odds_api: {calls, credits_used}}`.

### sources[] / missing[]

- `sources[]` mencatat setiap `data_kind` (kunci `sources.yaml`) dengan
  `source` + `tier` + `fetched_at` ASLI dari `FetchResult` — hanya bila
  fetch itu benar-benar menyumbang data untuk laga tersebut. Pengecualian:
  sumber cedera NBA dicatat bila fetch-nya berhasil (daftar cedera
  bersifat liga-wide; "tidak ada cedera untuk tim ini" adalah temuan,
  bukan kegagalan).
- Fixtures PL dicatat di bawah `football_stats_xg` (JSON resmi PL adalah
  kandidat jenjang 1 untuk kind itu; fixtures direkam di
  `stats.fixture`). Kind `football_lineup_injuries` hanya dipakai untuk
  data cedera/lineup aktual.
- `missing[]` memuat `data_kind` yang SEMUA fetch-nya gagal.
  `nba_player_impact` tidak punya fetcher di kontrak 2b (tidak dicoba,
  tidak masuk `missing[]` — lihat "Kesenjangan yang diketahui").
- `lineup` selalu `null` di 2b (tidak ada fetcher lineup di kontrak).

### Disambiguasi laga ganda (pasangan tim yang sama main dua kali)

Pasangan tim yang sama bisa main dua kali dalam jendela data (NBA:
malam ini + rematch minggu depan; bola: liga + piala). Pencocokan
HANYA berdasarkan tim akan mengambil laga yang salah — bug ini
tertangkap di demo 2b (Suns-Jazz memakai harga rematch 29 Nov, bukan
malam ini: jup 76/55, markup 15,5¢ — harga malam ini 63/38). Aturannya
(`_closest_by_time` di `slate.py`): per kunci pasar / per event
pembanding, dipakai yang waktunya TERDEKAT dengan laga ini
(laga pasangan sama berjarak hari, jadi yang terdekat menang tanpa
ambang):

- Pasar jup.ag: `start_time` pasar (dari `beginAt` event) terdekat
  dengan `start_time` laga di slate.
- Odds API / ESPN odds: event yang `commence_time`-nya terdekat dengan
  `start_time` pasar jup.ag.
- Kalshi: pasar yang `expiration_time`-nya terdekat dengan `start_time`
  pasar jup.ag (expiration ≈ mulai + durasi laga).

Bila waktu target tidak diketahui: dipakai yang paling awal (jup.ag)
atau yang pertama di list (pembanding). Data jadwal satu tanggal
(scoreboard stats.nba.com/ESPN, fixtures PL) tidak butuh aturan ini —
satu tanggal tidak punya duplikat.

### Urutan pembanding p_market (P1–P4 + keputusan user 2b)

Per pasar, sportsbook dulu — Odds API devig → ESPN odds devig (BOLA
SAJA) — dan Kalshi HANYA bila tidak ada pembanding sportsbook untuk
pasar itu. Urutan relatif langkah sportsbook dibaca dari
`playstyle.yaml` → `comparison.order`; Kalshi selalu terakhir apa pun
urutannya di config. Bila `jup_provider == "kalshi"`, Kalshi dilewati
(P2: itu harga yang sama, bukan pembanding). Polymarket tidak pernah
dipakai sebagai pembanding (P2) — hanya untuk `jup_markup`.

Entri `market_prices` per pasar:

```json
{
  "market_type": "spreads", "line": -1.5, "outcome": "Chelsea",
  "side": "home",
  "jup_price_cents": 32, "jup_provider": "polymarket",
  "jup_markup_cents": 0.5, "jup_markup_reason": null,
  "jup_markup_source": "book",
  "p_market": 0.32, "comparison_source": "kalshi",
  "p_market_missing_reason": null, "p_market_complement": false,
  "labels": ["PEMBANDING_KALSHI"],
  "comparison_line": 1.5, "line_matched": true
}
```

- `comparison_source`: "odds_api_devig" / "espn_odds_devig" / "kalshi" /
  `null` (nama eksplisit dari user; sebelumnya `p_market_source`).
- `labels` (per pasar): `["PEMBANDING_KALSHI"]` bila `p_market` dari
  Kalshi (harga Kalshi kurang tajam dibanding sportsbook; Tahap 3
  meneruskan label ini ke kaki), `[]` bila dari sportsbook.
- `comparison_line` / `line_matched` (hanya pasar spread/total):
  pembanding hanya sah bila garisnya SAMA PERSIS dengan garis jup.ag
  (spread Kalshi dicocokkan dengan magnitudo |garis|). Bila tidak ada
  pembanding bergaris sama: `comparison_line: null`, `line_matched:
  false`, tidak ada `p_market` dari sumber itu.
- `p_market_complement`: `true` bila `p_market` dihitung sebagai `1 - p`
  dari pasar Kalshi sisi lawan (lihat bawah). Sportsbook tidak pernah
  memakai komplemen.

### Komplemen Kalshi (identitas pasar biner, bukan tebakan)

Kalshi hanya punya pasar Over untuk total dan pasar "menang dengan
selisih > X" untuk spread. Maka:

- Total Under = sisi No pasar Over yang sama → `p = 1 - p_over`.
- Spread underdog (garis jup +) = 1 − p pasar lawan
  ("lawan menang > |garis|").
- Spread favorit (garis jup −) cocok langsung ke pasar tim yang sama.

Pasar spread underdog TIDAK PERNAH dicocokkan ke pasar Kalshi tim yang
sama — itu peluang kejadian lain (mis. "Everton menang > 1.5" ≠
"Everton menahan +1.5"). Semua komplemen dicatat
(`p_market_complement: true`).

### Label laga (ekstensi 2b — kunci `labels` pada MatchData)

`TANPA_XG`: bola tanpa xG (Understat tidak tersedia → B4).
`MODEL_ONLY`: TIDAK SATU PUN pasar di laga itu punya `p_market` (D2;
bila sebagian pasar punya pembanding, laga bukan MODEL_ONLY).

KEPUTUSAN SKEMA (koordinator 2b): kunci opsional `labels` (array string)
DITAMBAHKAN ke `schemas/match_data.schema.json` — perubahan aditif,
backward-compatible (dokumen lama tanpa `labels` tetap valid), dipaksa
oleh persyaratan eksplisit user (label `PEMBANDING_KALSHI` di output).
Label per pasar di entri `market_prices` tidak pernah melanggar skema
(`market_prices` memakai `additionalProperties: true`). `cli.py analyze`
tidak memvalidasi output terhadap skema match_data (validasi output
adalah pekerjaan Tahap 3).

## Gate Understat (`understat.py`)

`fetch_xg` HANYA mengambil data bila `is_available()` True: file
`probes/out/understat_status.json` (ditulis cek harian
`probes/check_understat.py`) berisi status `"up"` DAN `checked_at`
dalam 24 jam terakhir. Bila tidak: `ok=False`, error
`understat_not_available: <alasan>`, tanpa network — slate menerapkan
TANPA_XG. File hilang/rusak → status `"unknown"` (tidak tersedia).
Halaman maintenance (HTTP 200 + "We will come back soon") juga ditolak
sebagai tidak tersedia (pertahanan berlapis).

PERINGATAN: parser `parse_teams_data` BELUM terverifikasi terhadap
halaman live (situs maintenance sejak probe 2a) — hanya dites dengan
fixture HTML sintetis. Begitu Understat kembali, jalankan tes kesehatan
scraper terhadap halaman live sebelum memakai xG untuk keputusan.

## Validasi (`validate/checks.py`)

`validate_match_data(match, stale_hours_injury_lineup)` → `{"status",
"reasons"}`. Aturan (SOP langkah 3): cedera 0 sumber →
DATA_INCOMPLETE; cedera 1 sumber → HOLD ("B2 butuh 2 sumber"); stats
kosong → DATA_INCOMPLETE; `market_prices` kosong → DATA_INCOMPLETE;
cedera/lineup lebih tua dari `stale_hours` → HOLD ("basi", dinilai dari
`fetched_at` TERBARU antar sumber cedera); `p_market` kosong di semua
pasar BUKAN incompleteness (ditangani label MODEL_ONLY).
`stale_hours` dibaca dari `playstyle.yaml` → `data` (3 jam).

## Kesenjangan yang diketahui (2b)

1. **Cedera bola hanya 1 sumber**: FPL API memberi 1 sumber cedera bola
   (lihat atas) → laga bola menjadi HOLD ("B2 butuh 2 sumber"), bukan
   OK. Sumber kedua yang sah belum ada (endpoint ESPN injuries selalu
   kosong — TIDAK dihitung sebagai sumber kedua, itu akan mempermainkan
   validasi). LaLiga tanpa sumber cedera sama sekali (FPL hanya EPL).
2. **Lineup**: selalu `null` (tidak ada fetcher lineup di kontrak).
3. **`nba_player_impact`**: tidak ada fetcher pemain di kontrak 2b
   (dibutuhkan Tahap 3 untuk skenario skuad).
4. **LaLiga**: tanpa fixtures PL & odds ESPN (EPL saja); Kalshi LaLiga
   hanya moneyline; discovery (`matches=None`) hanya EPL.

Kesenjangan yang SUDAH DITUTUP saat integrasi 2b (koordinator):

- **Zona waktu tanggal NBA**: `cli.py` mengonversi `start_time` laga
  NBA ke tanggal US Eastern sebelum memanggil slate builder
  (stats.nba.com memakai tanggal Eastern).
- **Rotowire memakai singkatan tim** ("LAL"): `ingest/matching.py` kini
  memetakan tricode + nama lengkap NBA ke kanonik kota yang sama
  (30 tim × 3 bentuk, dites).
- **Kunci `labels` di luar skema**: ditambahkan ke
  `schemas/match_data.schema.json` (lihat "Keputusan skema" di atas).
