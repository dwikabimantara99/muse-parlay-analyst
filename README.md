# muse-parlay-analyst

Mesin analis parlay (NBA + sepak bola) yang workflow-nya terkunci.
Bukan bot otomatis: user kirim screenshot/daftar laga lewat Telegram, mesin
menganalisis secara mendalam, meracik Tiket Asuransi + Tiket Utama, dan bisa
diajak diskusi. User memasang tiket sendiri secara manual di jup.ag.

Spesifikasi resmi: **Blueprint Mesin Analis Parlay (Muse)** (Nov 20, 2026).
Aturan kerja yang tidak boleh dilanggar:

1. Semua angka (peluang, simulasi, EV, pengali) wajib keluar dari kode Python.
   LLM tidak boleh mengarang atau memperkirakan angka.
2. Data gagal diambil = laga ditandai `DATA_INCOMPLETE` dan tidak boleh masuk
   tiket. Jangan pernah mengisi data kosong dengan tebakan.
3. Hanya pakai sumber data gratis (lihat `config/sources.yaml`). Simpan API key
   di `.env`, jangan pernah di-commit.
4. Semua ambang & default strategi hanya ada di `config/playstyle.yaml`.
5. Satu pintu masuk: `cli.py` (analyze / recheck / log / recap).
6. Setiap modul wajib punya tes.

Workflow terkunci ada di **`SOP.md`** — wajib dibaca Muse setiap Mode Analisis.

## Status tahapan (Blueprint §10)

| Tahap | Isi | Status |
| --- | --- | --- |
| 1 — Pondasi | Struktur repo, `playstyle.yaml`, `SOP.md`, skema JSON, ledger SQLite | ✅ Selesai (2026-11-20), 55 tes lulus |
| 2 — Data | Semua penarik data + validasi + tes scraper | ⏳ Menunggu persetujuan user |
| 3 — Mesin hitung | Simulasi NBA & bola, devig, edge, anomali | ⏳ |
| 4 — Peracik & kritikus | Optimizer, kritikus, validator angka, format laporan | ⏳ |
| 5 — Telegram | Mode Analisis, Mode Diskusi, `cek ulang`, pencatatan via chat | ⏳ |
| 6 — Kalibrasi | Laporan otomatis setiap 50 kaki | ⏳ |

## Struktur

```text
muse-parlay-analyst/
├── config/
│   ├── playstyle.yaml        # semua ambang & default strategi (satu sumber)
│   └── sources.yaml          # daftar sumber data + cadangan
├── SOP.md                    # workflow terkunci yang wajib dibaca Muse
├── schemas/                  # skema JSON: slate, match_data, simulation, leg, ticket
├── examples/                 # contoh slate + 2 tiket (fixture tes)
├── ingest/                   # penarik data per sumber (Tahap 2, saat ini stub)
├── validate/                 # cek kelengkapan & umur data (Tahap 2, stub)
├── engine/                   # simulasi NBA/bola, pasar, devig (Tahap 3, stub)
├── optimizer/                # peracik Asuransi + Utama (Tahap 4, stub)
├── critic/                   # kritikus + validator angka (Tahap 4, stub)
├── report/                   # format laporan Telegram (Tahap 4, stub)
├── ledger/                   # SQLite, rekap (Tahap 1 ✓)
├── config.py                 # loader playstyle.yaml & sources.yaml
├── cli.py                    # satu pintu: analyze / recheck / log / recap
└── tests/                    # tes unittest (stdlib)
```

Modul Tahap 2+ saat ini berupa stub yang sengaja melempar
`NotImplementedError` — tidak ada data palsu, tidak ada angka karangan.
`tests/test_stubs.py` membuktikan itu.

## Cara pakai

```bash
# Instal dependensi (Python 3.11+)
pip install -r requirements.txt

# API key (opsional di Tahap 1, wajib mulai Tahap 2)
cp .env.example .env   # lalu isi key gratis kamu; JANGAN commit .env

# Catat tiket yang sudah dipasang
python cli.py log --file examples/ticket_asuransi.json
python cli.py log --file examples/ticket_utama.json

# Selesaikan tiket yang masih pending
python cli.py log --settle <ticket_id> --result WIN

# Rekap untung/rugi
python cli.py recap            # teks
python cli.py recap --json     # JSON

# Jalankan semua tes
python -m unittest discover -s tests -v
```

Database default: `ledger.db` di root repo (masuk `.gitignore`).
Pakai `--db <path>` untuk memakai file lain.

## Catatan Tahap 1

- Untung/rugi selalu dihitung kode dari modal × pengali × hasil. Skema tiket
  menolak field `profit_loss` dari input — tidak ada jalan memasukkan angka
  dari luar.
- Beberapa angka blueprint belum ditentukan dan ditulis `null` + `TBD` di
  `playstyle.yaml` (bukan ditebak): ambang "harga bergerak tajam", definisi
  "bantalan ekstra" Alt Under, definisi "pemain kunci" bola, parameter
  kalibrasi simulasi (σ NBA, home advantage, penalti B2B/ketinggian/absensi,
  rho Dixon-Coles), dan pembagian modal default. Daftar lengkap + pertanyaan
  soal sumber data ada di laporan Tahap 1.
