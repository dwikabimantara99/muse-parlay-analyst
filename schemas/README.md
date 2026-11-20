# Skema JSON

Lima skema (JSON Schema draft 2020-12) yang mengunci bentuk data antar langkah
SOP. Validasi memakai `jsonschema` (lihat `tests/test_schemas.py`).

| Skema | Dipakai di | Isi |
| --- | --- | --- |
| `slate.schema.json` | SOP langkah 1 → input `analyze` | Daftar laga + harga ¢ screenshot |
| `match_data.schema.json` | SOP langkah 2–3 | Data per laga + sumber/jam + status OK/HOLD/DATA_INCOMPLETE |
| `simulation.schema.json` | SOP langkah 4 | Hasil simulasi 100.000x + skenario skuad |
| `leg.schema.json` | SOP langkah 5–7, 9 | Kaki kandidat: peluang, edge, EV, status, lampu kritikus |
| `ticket.schema.json` | SOP langkah 8, 10 + `cli.py log` | Tiket Asuransi/Utama + kaki + hasil |

Aturan umum:
- Peluang selalu desimal 0–1. Harga jup.ag selalu ¢ 0–100. Uang selalu USD.
- Waktu selalu ISO 8601 dengan zona waktu.
- Field yang belum punya nilai diisi `null` atau dicatat di `missing[]` —
  jangan pernah diisi tebakan.
- `ticket.schema.json` dipakai juga oleh `cli.py log`: file tiket yang tidak
  lolos skema ditolak, tidak masuk ledger.
