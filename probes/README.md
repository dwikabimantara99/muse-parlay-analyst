# Probe Tahap 2a

Probe memeriksa apakah setiap sumber data bisa diakses dari VM ini, format
apa yang dikembalikan, dan batas/rate limit-nya — **tanpa membangun penarik
data lengkap** (itu Tahap 2b). Hasil probe ada di `HASIL-PROBE-2A.md` dan
`out/*.json`.

## Menjalankan

Dari root repo:

```bash
# Semua probe berurutan (jeda sopan antar probe), lalu summary.json
python3 probes/run_all.py

# Satu probe saja (menulis probes/out/<nama>.json)
python3 probes/espn.py
python3 probes/jupiter.py
```

Daftar probe: `jupiter`, `polymarket`, `kalshi`, `odds_api`, `nba_com`,
`espn`, `bbref`, `nba_injury_report`, `rotowire`, `understat`,
`official_leagues`, ditambah probe tambahan 2a: `espn_odds`,
`kalshi_sports`, `jup_markup`, `football_data`, `understat_recheck`
(hasilnya di `HASIL-PROBE-TAMBAHAN.md`).

`sofascore` dan `fotmob` TIDAK lagi dijalankan `run_all.py` (sumber DITOLAK
user 2026-11-20); modulnya tetap ada sebagai bukti probe 2a.

## Cek harian Understat (bukan probe)

`probes/check_understat.py` adalah health check non-interaktif (1 request
ringan) yang menulis status ke `probes/out/understat_status.json` dan
menambah satu baris ke `probes/out/understat_health.log`. Fetcher 2b
membaca file status ini: bila `status == "up"` dan `checked_at` masih dalam
24 jam, Understat aktif lagi di rantai xG; bila tidak, bola jalan dengan
aturan B4 (TANPA_XG). Jadwal yang disarankan: 1x sehari via cron.

```bash
python3 probes/check_understat.py
```

## Cache

Respons HTTP 200 disimpan di `probes/out/cache/` (gitignored) dengan TTL
1 jam; pengulangan dalam TTL memakai cache, bukan request baru. Cache Jupiter
dipisah per mode (`#keyed` / `#keyless`) agar mode tercatat jujur. Untuk
memaksa request segar, hapus `probes/out/cache/`.

## API key

- `JUPITER_API_KEY` dibaca dari `.env` di root repo (hanya oleh
  `probes/jupiter.py`, lewat `common.load_dotenv`). Nilai key **tidak pernah**
  di-print, di-log, atau ditulis ke file apa pun — evidence respons juga
  tidak memuat header `Authorization`/`x-api-key`.
- `ODDS_API_KEY` belum disediakan user; `probes/odds_api.py` hanya memastikan
  endpoint terjangkau (ekspektasi 401 tanpa key).

## Aturan probe

- Maks ~3 request per sumber (kecuali dinyatakan lain), jeda sopan antar
  request, selalu pakai cache bila mengulang.
- Setiap probe mencatat URL yang dicoba, status HTTP, format respons
  (contoh dipotong), header rate limit bila ada, dan error apa adanya.
- Yang tidak bisa ditentukan ditulis `UNKNOWN` — jangan menebak.
- Jupiter: HANYA endpoint baca GET (`/events`, `/events/search`,
  `/events/{id}`, `/markets/{id}`). Endpoint yang memindahkan dana
  (`/orders`, `/positions`, `/claim`) ditolak keras di `common.py`.

## Tes

Tes unit (tanpa network, tanpa API key) ada di `tests/test_probes.py`:

```bash
python3 -m unittest discover -s tests
```
