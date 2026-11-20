# Laporan Tahap 1 — Pondasi muse-parlay-analyst

Tanggal: 20 November 2026
Commit: `24d6fa1` (repo git lokal, belum ada remote GitHub)
Lokasi: `~/workspace/projects/muse-parlay-analyst/`
Python: 3.12.3 (blueprint minta 3.11+, terpenuhi)

## 1. Struktur repo yang dibuat

51 file, sesuai Blueprint §10, ditambah 3 hal yang diminta tugas Tahap 1
(di luar daftar §10): `config.py` (loader config), `schemas/` (5 skema JSON),
`examples/` (slate + 2 tiket contoh).

```text
muse-parlay-analyst/
├── README.md, SOP.md, LAPORAN-TAHAP-1.md
├── requirements.txt              # pyyaml, jsonschema (tes: unittest stdlib)
├── .env.example, .gitignore     # .env, *.db, data/, out/ tidak di-commit
├── config/
│   ├── playstyle.yaml            # SEMUA ambang & default (§6, §7, + §3/4/5/9)
│   └── sources.yaml              # sumber data + cadangan (§4)
├── schemas/                      # slate, match_data, simulation, leg, ticket
│   └── README.md
├── examples/                     # slate_contoh.json + 2 tiket + README
├── config.py                     # load_playstyle(), load_sources(), get_value()
├── cli.py                        # analyze / recheck / log / recap
├── ledger/                       # store.py (SQLite) + recap.py + __init__.py
├── ingest/                       # 10 penarik per sumber (§4) — STUB Tahap 2
├── validate/                     # checks.py — STUB Tahap 2
├── engine/                       # nba_sim, football_sim, markets, devig — STUB Tahap 3
├── optimizer/                    # tickets.py — STUB Tahap 4
├── critic/                       # critic.py, validate_numbers.py — STUB Tahap 4
├── report/                       # telegram.py — STUB Tahap 4
└── tests/                        # 6 file tes unittest
```

Keputusan desain Tahap 1:

- **Stub melempar `NotImplementedError`.** Semua modul Tahap 2+ ada sebagai
  kerangka, tapi fungsinya sengaja gagal dengan pesan "Tahap N belum
  tersedia". Tidak ada data palsu, tidak ada angka karangan.
  `tests/test_stubs.py` membuktikan ke-19 stub berperilaku begitu.
- **Tes memakai `unittest` (stdlib).** `pytest` tidak terinstal di VM ini;
  daripada menambah dependensi, tes ditulis dengan `unittest` yang sudah ada.
  Jalankan: `python -m unittest discover -s tests -v`.
- **Untung/rugi tidak bisa diinput.** Skema tiket menolak field `profit_loss`
  (`additionalProperties: false`). `ledger/store.py` selalu menghitung dari
  modal × pengali × hasil. Tiket duplikat dan tiket tidak valid ditolak.
- **`analyze` / `recheck` keluar dengan kode 2** dan pesan jelas bahwa
  tahapnya belum dibangun — bukan diam-diam gagal atau pura-pura jalan.
- **Repo git lokal saja.** Belum ada remote GitHub; itu keputusan user
  (lihat pertanyaan 10). Identitas commit lokal: `Muse <muse@localhost>`
  (placeholder, bisa diganti).

## 2. Isi playstyle.yaml

Semua default §6 dan §7, ditambah angka terkait §3, §4, §5, §9 — satu sumber,
dengan komentar yang mengutip nomor bagiannya. Ringkasan:

| Bagian | Isi |
| --- | --- |
| `tickets.insurance` | pengali 2,20–2,50x; min peluang/kaki 74%; wajib menutup total modal |
| `tickets.main` | pengali 3,5–6x (Agresif: bebas); min peluang/kaki 65% |
| `tickets.mode` | `standard` (default); `aggressive` hanya atas perintah user |
| `optimizer` | urut P(rugi total) terkecil → EV gabungan terbesar; 3 opsi teratas |
| `combo` | potongan spread kombo 5,5% |
| `blend` | w_model 0,3 (pasar patokan utama) |
| `anomaly` | jup vs pasar > 4 poin; model vs pasar > 8 poin |
| `filters.all_markets` | coret DATA_INCOMPLETE; coret EV < −2% setelah spread |
| `filters.moneyline` | coret p_akhir < 65% (Agresif boleh, wajib label) |
| `filters.nba_alt_under` | coret DRtg #23–30; coret kedua tim top-10 Pace; coret spread ≤ 2,5 tanpa bantalan |
| `filters.football_btts_yes` | coret total xG gabungan < 2,45 |
| `filters.football_lineup` | coret lineup belum keluar + < 60 menit + pemain kunci diragukan |
| `simulation` | 100.000 iterasi; NBA Student-t + OT 5 menit + skenario absen 1/2/4; bola Dixon-Coles, xG 60% musim + 40% 5–6 laga terakhir |
| `data` | cedera/lineup basi > 3 jam; cek ulang 30–60 menit sebelum laga |
| `calibration` | laporan kalibrasi setiap 50 kaki |

**Nilai TBD (ditulis `null`, bukan ditebak):** ambang "harga bergerak tajam"
(anomali), definisi "bantalan ekstra" Alt Under, definisi "pemain kunci" bola,
parameter kalibrasi simulasi (σ NBA, home advantage, penalti back-to-back /
ketinggian / absensi, rho Dixon-Coles, home advantage per liga), dan pembagian
modal default. Lihat pertanyaan di bawah.

## 3. Skema JSON

Lima skema (JSON Schema draft 2020-12) di `schemas/`, aturan umum: peluang
desimal 0–1, harga jup.ag ¢ 0–100, uang USD, waktu ISO 8601 berzona waktu,
nilai yang belum ada diisi `null` / dicatat di `missing[]` — tidak ditebak.

- `slate.schema.json` — daftar laga + harga ¢ screenshot (input `analyze`).
- `match_data.schema.json` — data per laga + sumber/jam + status
  OK / HOLD / DATA_INCOMPLETE + konflik antar sumber.
- `simulation.schema.json` — hasil simulasi 100.000x + skenario skuad.
- `leg.schema.json` — kaki kandidat: peluang, edge, EV, status, lampu kritikus.
- `ticket.schema.json` — tiket Asuransi/Utama + kaki + hasil (juga input
  `cli.py log`; tiket yang tidak lolos skema ditolak masuk ledger).

## 4. Ledger SQLite + CLI

Tabel `tickets` (id, placed_at, type, stake, multiplier, result, profit_loss,
settled_at, slate_id, option_label, combo_spread_pct, notes) dan `legs`
(ticket_id, leg_id, match_id, sport, market, selection, p_model, p_market,
p_final, price_buy_cents, price_close_cents, edge, ev_pct, status,
filter_reason, anomaly_reason, critic_light, result).

```bash
python cli.py log --file ticket.json        # catat tiket (validasi skema dulu)
python cli.py log --settle <id> --result WIN|LOSS|PUSH|VOID
python cli.py recap [--json]                # untung/rugi, ROI, per jenis tiket
```

## 5. Hasil tes

**55 tes, semuanya lulus** (`python -m unittest discover -s tests`, 2,5 detik):

| File tes | Tes | Yang dibuktikan |
| --- | --- | --- |
| `test_config.py` | 21 | semua angka playstyle.yaml cocok dengan blueprint; TBD berupa null; sources lengkap; tidak ada API key di repo |
| `test_schemas.py` | 9 | contoh valid lolos; tiket tanpa modal / berpengali 1,0 / berisi profit_loss ditolak |
| `test_ledger.py` | 12 | rumus untung/rugi 5 hasil; 2 tiket tercatat; duplikat & invalid ditolak; settle PENDING |
| `test_recap.py` | 6 | angka gabungan tepat; pending tidak masuk untung/rugi; rekap kosong tidak error |
| `test_cli.py` | 7 | ujung-ke-ujung lewat subprocess; analyze/recheck kode 2 |
| `test_stubs.py` | 1 (19 subtes) | semua stub Tahap 2+ melempar NotImplementedError |

**Tes 2 tiket contoh (dijalankan manual via CLI, diverifikasi hitung tangan):**

- Asuransi: modal $60, 2,35x, WIN → 60 × 2,35 − 60 = **+$81,00**
- Utama: modal $40, 4,50x, LOSS → **−$40,00**
- Rekap: 2 tiket selesai, modal $100, kembali $141, untung **+$41,00**,
  ROI **+41,00%**. Asuransi +$81,00 (ROI +135,00%); Utama −$40,00
  (ROI −100,00%). Kaki 5 total, 5 selesai, 4 menang (80,0%).
- Syarat §6a terpenuhi di contoh: 2,35 × $60 = $141 ≥ total modal $100.

## 6. Pertanyaan & bagian blueprint yang kurang jelas

### A. Sumber data (risiko terbesar Tahap 2)

1. **Jupiter Prediction API.** Blueprint bilang API masih beta dan bisa
   dibatasi di beberapa region. Belum jelas: (a) apakah user sudah punya API
   key dari Portal; (b) apakah API memberi harga per pasar parlay (spread,
   total, BTTS) atau hanya pasar Yes/No per event — prediction market umumnya
   Yes/No, dan pemetaan ke pasar parlay belum dijelaskan; (c) apakah VM ini
   kena batas region. Ini baru bisa dijawab dengan mencoba langsung di Tahap 2.
2. **Polymarket / Kalshi sebagai pembanding.** Masalah pemetaan yang sama:
   pasar spread/total NBA dan BTTS bola belum tentu tersedia di sana. Kalau
   pasar pembanding tidak ada, `p_market` kosong — lalu bagaimana blend §5c?
   Blueprint tidak mengatur fallback (pakai model saja? tandai
   DATA_INCOMPLETE?). Perlu keputusan sebelum Tahap 3.
3. **The Odds API (500 kredit/bulan).** "Pakai hemat" belum berupa aturan
   konkret: berapa slate per minggu yang direncanakan, dan apakah odds boleh
   di-cache antar analisis? Perlu batas pemakaian yang disepakati.
4. **NBA Injury Report (PDF).** Blueprint tidak memberi URL dan jadwal
   update-nya. Perlu dikonfirmasi sumber resminya di Tahap 2.
5. **Understat / Sofascore / FotMob / Basketball-Reference.** Understat tidak
   punya API publik resmi; Sofascore/FotMob/BBref diakses lewat scraping atau
   endpoint tidak resmi, dan BBref dikenal membatasi scraping agresif.
   Blueprint sudah mengakui risiko scraper (§4), tapi perlu konfirmasi user
   bahwa pendekatan scraping tidak resmi ini dapat diterima, dan apa yang
   terjadi kalau satu sumber mati permanen (apakah cadangan ESPN saja cukup
   untuk xG? ESPN tidak menyediakan xG setara Understat).
6. **Liga sepak bola.** Understat hanya 5 liga top Eropa. Apakah slate bola
   dibatasi ke 5 liga itu? Bagaimana dengan Liga Champions / Europa League /
   liga lain — sumber xG-nya apa?

### B. Angka & definisi yang belum ada di blueprint (ditulis TBD, tidak ditebak)

7. **Rumus EV per kaki.** §7a memakai ambang EV < −2%, tapi rumus EV tidak
   ditulis eksplisit. Apakah EV = p_akhir × (100 / harga_¢) − 1? Perlu
   konfirmasi sebelum Tahap 3.
8. **Rumus pengali kombo.** §6d: pengali dari harga ¢ tiap kaki dikurangi
   spread 5,5% — rumus pastinya (perkalian 100/¢ lalu × 0,945?) tidak
   ditulis. Perlu dirumuskan sebelum Tahap 4.
9. **"Harga bergerak tajam"** (anomali §5d) — tidak ada ambang angkanya.
10. **"Bantalan ekstra"** Alt Under (§7a) — tidak didefinisikan (berapa poin?
    dari apa?).
11. **"Pemain kunci"** bola (§7a) — tidak didefinisikan (starter? kontribusi
    xG?).
12. **Parameter kalibrasi simulasi** (§5a/§5b): σ NBA, home advantage (NBA
    dan per liga bola), penalti back-to-back, penyesuaian ketinggian,
    penalti absensi (bek/kiper/striker), rho Dixon-Coles. Blueprint bilang
    dikalibrasi dari data historis — artinya nilainya baru ada saat Tahap 3
    berjalan. Perlu disepakati: kalibrasi dari data historis mana, dan siapa
    yang menyetujui angka awalnya.
13. **Pembagian modal default.** Blueprint tidak memberi default (hanya contoh
    "modal 60/40"). Apakah user mau menetapkan satu default (misal 60/40),
    atau wajib menyebut tiap malam?

### C. Lain-lain

14. **Mata uang.** Laporan memakai USD sesuai blueprint ($). jup.ag memakai
    USDC/SOL — apakah pencatatan tetap USD, atau perlu konversi kurs?
15. **Repo GitHub.** Repo saat ini hanya git lokal. Apakah perlu dibuatkan
    repo GitHub private (seperti proyek Meteora), atau tetap lokal dulu?

## 7. Yang TIDAK dikerjakan (sesuai perintah)

Tahap 2 belum dimulai. Tidak ada penarik data, simulasi, optimizer, kritikus,
laporan Telegram, atau integrasi Telegram yang dibangun — semua masih stub.
