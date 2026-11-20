# Contoh (fixture tes Tahap 1)

File-file ini **CONTOH** untuk menguji ledger & skema — bukan hasil analisis.
Angka peluang di dalamnya ilustratif, bukan dari simulasi.

- `slate_contoh.json` — slate 3 laga (2 NBA + 1 bola), pembagian modal 60/40.
- `ticket_asuransi.json` — Asuransi: modal $60, pengali 2,35x, hasil WIN.
  Untung yang benar: 60 × 2,35 − 60 = **+$81,00**.
  Cek syarat §6a: 2,35 × 60 = $141 ≥ total modal $100 ✓.
- `ticket_utama.json` — Utama: modal $40, pengali 4,50x, hasil LOSS.
  Untung yang benar: **−$40,00**.

Rekap gabungan yang benar (dipakai `tests/test_recap.py`):
- Tiket selesai: 2, total modal $100, total kembali $141, untung **+$41,00**,
  ROI **+41,00%**.
- Asuransi: +$81,00 (ROI +135,00%). Utama: −$40,00 (ROI −100,00%).
- Kaki: 5 total, 5 selesai, 4 menang (80,0%).

Cara mencoba manual:

```bash
python cli.py log --file examples/ticket_asuransi.json --db /tmp/contoh.db
python cli.py log --file examples/ticket_utama.json --db /tmp/contoh.db
python cli.py recap --db /tmp/contoh.db
```
