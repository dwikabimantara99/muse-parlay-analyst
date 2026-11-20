# Hasil Probe Tambahan (Tahap 2a lanjutan)

Tanggal probe: **2026-11-20** (rangkaian selesai 22:57 WIB).
Semua angka di bawah berasal dari `probes/out/*.json` — bukan dari ingatan
model. Total **40 request baru** (37 respons tersimpan di cache + 3 cek
Understat tanpa cache; file cache 33 → 70). Slate jup.ag dipakai ulang
dari cache probe 2a (0 request Jupiter baru).

Ringkasan verdict: **PAKAI 4, JANGAN 1.**

| Probe | Hasil | Verdict |
|---|---|---|
| 1. ESPN odds | Garis sportsbook ADA untuk bola (EPL 7/7, DraftKings lengkap ML+spread+total; summary tambah Bet 365 desimal ML). TIDAK ADA untuk NBA (scoreboard 0/4 + 0/6, summary odds `[]`) | **PAKAI** (bola saja) |
| 2. Kalshi sports | Moneyline tercocokkan 100% di liga yang dicakup Kalshi (NBA 20/20, EPL 15/15, LaLiga 9/9); EPL spread 40/100, total 60/90 (per garis); harga tersedia (field `*_dollars`) | **PAKAI** |
| 3. jup_markup | 11/11 pasar tercocokkan; median markup **0,5¢** (mean 0,68¢, min 0,5¢, max 1,5¢) — praktis sama dengan setengah lebar bid-ask Polymarket | **PAKAI** |
| 4. football-data.co.uk | CSV historis bisa diunduh (EPL 2526 + 2425, 380 baris, kolom Pinnacle lengkap); 27 liga terdaftar; TAPI ada peringatan Pinnacle basi + ketentuan pakai | **PAKAI** (dengan catatan) |
| 5. Understat cek ulang | Masih maintenance (EPL + LaLiga, halaman identik 26.719 karakter); cek harian otomatis sudah jalan dan mencatat status | **JANGAN** (tetap B4) |

## 1. ESPN odds — PAKAI (bola saja)

| Endpoint | Event | Punya odds | Provider | Kelengkapan |
|---|---|---|---|---|
| NBA scoreboard hari ini | 4 (semua sudah selesai) | 0/4 | — | — |
| NBA scoreboard besok | 6 (semua pre) | 0/6 | — | — |
| NBA summary (1 laga) | 1 | tidak (field `odds` = `[]`) | — | — |
| EPL scoreboard hari ini | 7 | 7/7 | DraftKings | ML 7/7, spread 7/7, total 7/7 |
| EPL summary (1 laga) | 1 | ya, 2 entri | DraftKings + Bet 365 | DraftKings lengkap; Bet 365 ML desimal saja |

- Struktur odds DraftKings: `moneyline` (home/away/draw, odds Amerika,
  `open` + `close`), `pointSpread` (home/away, line + odds),
  `total` (over/under, line + odds), `overUnder`, `details`.
  Contoh (Man City vs Fulham): ML home `-260`, away `+650`, draw `+425`;
  spread home `-1.5 @ -105`; total `o3.5 @ +120` / `u3.5 @ -145`.
- Bet 365 di summary: moneyline DESIMAL (`homeTeamOdds`/`awayTeamOdds`/
  `drawOdds`, nilai mis. 1.364 / 7.0 / 5.25) — tanpa spread/total.
- **Implikasi urutan pembanding:** ESPN odds hanya menutup BOLA. Untuk NBA,
  setelah Odds API, pembanding berikutnya adalah Kalshi (bukan ESPN odds).

## 2. Kalshi sports — PAKAI

Series yang terkonfirmasi ada (semua HTTP 200):

| Series | Event open | Pasar open | Catatan |
|---|---|---|---|
| KXNBAGAME (NBA moneyline) | 32 | 64 | 64/64 punya bid+ask |
| KXNBASPREAD (NBA spread) | 9 | — (contoh: "Utah wins by over 7.5 points") | garis 3.5/5.5/7.5 dst. |
| KXNBATOTAL (NBA total) | 9 | — | |
| KXEPLGAME (EPL moneyline) | 29 | 87 (3/event) | 87/87 punya bid+ask |
| KXEPLSPREAD (EPL spread) | 10 | 40 | garis 1.5/2.5 saja; 40/40 punya bid+ask |
| KXEPLTOTAL (EPL total) | 10 | 60 | Over 0.5–5.5 saja; 60/60 punya bid+ask |
| KXLALIGAGAME (LaLiga moneyline) | 23 | — | |

Pencocokan dengan slate jup.ag hari ini (100 event: 10 laga NBA, 5 EPL,
3 LaLiga, 24 laga bola lain):

| Kategori | Pasar jup.ag | Tercocokkan | % |
|---|---|---|---|
| NBA moneyline | 20 | 20 | 100% |
| EPL moneyline | 15 | 15 | 100% |
| LaLiga moneyline | 9 | 9 | 100% |
| EPL spreads (per garis) | 100 | 40 | 40% |
| EPL totals (per garis) | 90 | 60 | 66,7% |
| Bola lain moneyline | 72 | 0 | 0% (tidak ada series Kalshi) |
| NBA spreads/totals | 0 | — | N/A (jup.ag tanpa pasar itu) |

- Kalshi memakai nama KOTA untuk NBA ("Charlotte") dan nama SINGKAT untuk
  bola ("Newcastle"), sementara jup.ag memakai julukan ("Hornets") dan nama
  resmi ("Newcastle United FC") — pencocokan memakai normalisasi +
  pemetaan julukan→kota (30 tim NBA) + alias bola yang teramati
  (`athletic`→`bilbao`, `espanyol barcelona`→`espanyol`), semuanya diuji.
- **Field harga Kalshi bernama `*_dollars`** (string dolar, mis. `"0.1200"`)
  — nama lama `yes_bid`/`yes_ask` TIDAK ADA di API ini. Awalnya probe
  salah baca (0/64 "punya harga") karena memakai nama lama; sudah
  diperbaiki dan diverifikasi lewat 1 pasar tunggal + orderbook
  (HTTP 200, bid 0.12 / ask 0.13, 5+5 level).
- `last_price_dollars` bisa `"0.0000"` (belum ada transaksi) walau bid/ask
  ada — fetcher 2b harus memakai bid/ask, bukan last_price.
- EPL spread Kalshi hanya garis 1.5/2.5; total hanya Over 0.5–5.5 (Under =
  sisi No). Pasar jup.ag di luar garis itu tetap butuh pembanding
  sportsbook.

## 3. jup_markup — PAKAI

Sampel 11 pasar (4 NBA moneyline, 3 EPL moneyline, 2 EPL totals 2.5,
2 EPL spreads ±1.5), dicocokkan lewat `clobTokenIds` ke orderbook
Polymarket. **11/11 tercocokkan, 0 tak tercocokkan.**

| Statistik | Nilai (¢) |
|---|---|
| Median `jup_markup` | 0,5 |
| Mean | 0,68 |
| Min | 0,5 |
| Max | 1,5 (Chelsea −1.5 spread) |

- 10 dari 11 pasar: markup PERSIS setengah lebar bid-ask CLOB
  (spread 1,0¢ → markup 0,5¢; spread 2,0¢ → markup 1,0¢). Artinya harga
  beli jup.ag ≈ ask Polymarket — **jup.ag praktis tidak menambah biaya di
  atas spread Polymarket** (di luar selisih waktu pengambilan).
- 1 outlier: Chelsea −1.5 spread, markup 1,5¢ padahal spread CLOB 1,0¢
  (harga jup.ag 1¢ di atas ask CLOB) — bisa biaya nyata atau artefak
  selisih waktu; dicatat apa adanya.
- **Perangkap yang ditemukan dan diperbaiki:** pasar 2-outcome (moneyline
  NBA) MEMBAGI satu pasangan token — pasar tim kedua harus memakai token
  [1], bukan [0]. Run pertama yang memakai [0] untuk keduanya menghasilkan
  markup palsu +15,5¢ dan +37,5¢. Pemilihan token sekarang berdasarkan
  indeks judul di `outcomes` (diuji).
- Catatan: harga jup.ag dari cache 2a (±1 jam lebih tua dari midpoint
  CLOB) — markup mengandung selisih waktu; fetcher 2b/3 harus mengambil
  keduanya sedekat mungkin.

## 4. football-data.co.uk — PAKAI (dengan catatan)

| File | Status | Ukuran | Baris | Baris dgn Pinnacle 1X2 |
|---|---|---|---|---|
| `mmz4281/2526/E0.csv` (EPL 2025/26) | 200 | 203.438 byte | 380 | 210/380 |
| `mmz4281/2425/E0.csv` (EPL 2024/25) | 200 | 197.110 byte | 380 | 380/380 |

- Kolom Pinnacle lengkap: `PSH/PSD/PSA` (open), `PSCH/PSCD/PSCA`
  (close), `P>2.5`/`P<2.5` (over/under). Contoh baris: Liverpool 4–2
  Bournemouth, PSH 1.28 / PSD 6.56 / PSA 9.07.
- Halaman `data.php` mendaftar **27 liga** (11 utama Eropa + 16 extra,
  termasuk USA, Jepang, Brasil) dan mengklaim: 32 musim hasil, 27 musim
  odds, 22 divisi Eropa sejak 1993/94, odds sejak 2000/01, 16 divisi
  non-Eropa sejak 2012/13. Tautan CSV ada di halaman per negara, bukan di
  `data.php` — pola URL `mmz4281/<musim>/<kode>.csv` baru terverifikasi
  untuk E0.
- **PERINGATAN PINNACLE (dari halaman situs):** sejak 23/07/2025 API publik
  Pinnacle tidak andal sehingga odds Pinnacle di situs ini "systematically
  out of date" dan "should be used with caution" — kalibrasi Tahap 3
  sebaiknya memakai odds Pinnacle dari musim selesai SEBELUM 23/07/2025
  (mis. 2024/25) atau memvalidasi dulu.
- **KETENTUAN PAKAI:** data "intended for private individuals only, NOT
  commercial or data training products using automated bots/scrapers/AI"
  — pemakaian untuk proyek pribadi ini perlu diputuskan user (klausanya
  tentang produk komersial/AI, bukan larangan mutlak pengambilan otomatis
  seperti FotMob).
- Hanya untuk KALIBRASI Tahap 3, bukan data live.

## 5. Understat cek ulang + cek harian — JANGAN (tetap B4)

- Cek ulang (request FRESH, tanpa cache): EPL + LaLiga masih maintenance
  — halaman identik 26.719 karakter, "We will come back soon", tanpa
  penanda JSON. Rantai xG tetap putus; aturan B4 (TANPA_XG) tetap berlaku.
- Mekanisme cek harian sudah dibangun dan diuji jalan 1x:
  `probes/check_understat.py` (1 request ringan, non-interaktif) menulis
  `probes/out/understat_status.json` (`checked_at`, `status`,
  `evidence`) + menambah 1 baris ke `probes/out/understat_health.log`.
  Status saat ini: `maintenance` (checked 2026-11-20 22:49 WIB).
- **Re-aktivasi otomatis (mekanisme):** fetcher 2b membaca
  `understat_status.json` sebelum memakai Understat di rantai xG — bila
  `status == "up"` DAN `checked_at` masih dalam 24 jam, Understat aktif
  lagi; bila tidak, bola jalan TANPA_XG. Script ini tidak mengubah config
  apa pun. Jadwal yang disarankan: 1x sehari via cron (lihat docstring
  `check_understat.py` dan `probes/README.md`).

## Daftar UNKNOWN

- Apakah odds NBA ESPN pernah muncul (mis. mendekati tip-off atau lewat
  endpoint lain) — teramati tidak ada di scoreboard (pre) maupun summary.
- Apakah entri Bet 365 di summary ESPN punya spread/total di kunci lain
  (yang teramati hanya moneyline desimal).
- Series Kalshi untuk Bundesliga, Serie A, Ligue 1, UCL (tidak diuji).
- Series spread/total Kalshi untuk LaLiga (tidak diuji).
- Apakah markup 1,5¢ di Chelsea −1.5 spread adalah biaya nyata atau
  artefak selisih waktu.
- Pola URL football-data.co.uk untuk liga selain E0 (tidak diunduh —
  tugas membatasi 1–2 file CSV contoh).
- Apakah ketentuan football-data.co.uk mengizinkan unduhan scripted
  untuk proyek pribadi (keputusan user).
- Kapan Understat kembali (cek harian akan mendeteksinya).
- Rate limit ESPN, Polymarket CLOB, Kalshi, football-data.co.uk
  (tidak ada header terlihat saat probe; Kalshi 2a: limit 600).

## File bukti

- `probes/out/espn_odds.json`, `kalshi_sports.json`, `jup_markup.json`,
  `football_data.json`, `understat_recheck.json`
- `probes/out/understat_status.json` + `understat_health.log` (cek harian)
- Script: `probes/espn_odds.py`, `kalshi_sports.py`, `jup_markup.py`,
  `football_data.py`, `understat_recheck.py`, `check_understat.py`
- `probes/run_all.py` kini menjalankan 5 probe tambahan; `sofascore` +
  `fotmob` dikeluarkan dari runner (sumber ditolak user — modul tetap ada
  sebagai bukti 2a).
- Tes: 140 unittest lolos (112 lama + 28 baru), black + ruff bersih.
