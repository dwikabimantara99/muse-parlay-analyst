# SOP — Workflow Terkunci Mesin Analis Parlay (Muse)

**Dokumen ini WAJIB dibaca Muse setiap Mode Analisis.**
Sumber resmi: Blueprint Mesin Analis Parlay (Muse) §3 + §8 + §7c.
Keputusan yang mengubah/menambah blueprint dicatat di `DECISIONS.md` — baca
bersama dokumen ini. Kalau keduanya berbeda, `DECISIONS.md` yang berlaku.
Perubahan SOP hanya lewat revisi dokumen ini, bukan lewat ingatan chat.

---

## 0. Prinsip yang tidak boleh dilanggar

1. **Angka hanya dari script.** Peluang, simulasi, EV, dan pengali tiket wajib
   keluar dari kode Python (`cli.py` / modul di repo ini). LLM dilarang menulis
   angka yang tidak berasal dari output script.
2. **Nol data = berhenti.** Data penting (cedera, lineup, statistik, harga)
   gagal diambil → laga ditandai `DATA_INCOMPLETE` dan tidak boleh masuk tiket.
   Jangan pernah mengisi data kosong dengan tebakan.
3. **Setiap angka ada sumbernya.** Laporan menyebut dari mana data diambil
   dan kapan.
4. **Pasar adalah patokan.** Harga pasar lain (Polymarket, Kalshi, sportsbook)
   dipakai sebagai pembanding wajib. Model sendiri tidak boleh dipercaya
   sendirian.
5. **Fleksibel di strategi, kaku di proses.** Jumlah kaki, pengali, dan
   pembagian modal boleh berubah sesuai situasi. Langkah analisisnya tidak
   boleh dilewati.
6. **Semua tercatat.** Setiap tiket yang dipasang masuk ke ledger (SQLite)
   supaya kualitas mesin bisa diukur jujur.
7. **Semua ambang & default strategi hanya ada di `config/playstyle.yaml`.**
   Jangan menulis angka ambang di kode, di SOP ini, atau di laporan — baca
   dari file itu.

---

## 1. Dua mode

| Mode | Pemicu | Perilaku |
| --- | --- | --- |
| **Mode Analisis** | User kirim screenshot bursa atau daftar laga + kata kunci "analisis" / "racik" | Jalankan workflow 10 langkah (§2) sampai selesai, tanpa dilewati |
| **Mode Diskusi** | Pertanyaan lanjutan ("kenapa kaki ini?", "kalau Brunson absen gimana?", "ganti kaki 3 dengan yang lebih aman") | Jawab dari file JSON analisis yang tersimpan. Kalau butuh angka baru, jalankan ulang script — jangan mengira-ngira |

Analisis lengkap per laga disimpan sebagai file JSON. Saat diskusi, Muse membaca
angka dari file itu, bukan dari ingatan chat.

---

## 2. Workflow terkunci — 10 langkah (wajib berurutan)

**Kalau ada langkah yang dilewati, laporan dianggap TIDAK SAH.**

### Langkah 1 — Baca & konfirmasi
- Muse membaca screenshot, lalu menampilkan tabel: laga, liga, jam, pasar,
  dan harga ¢.
- User cukup balas "ok" atau koreksi. Tujuannya mencegah salah baca gambar.
- Jangan lanjut ke Langkah 2 sebelum user konfirmasi (atau user sudah kirim
  daftar laga tertulis yang tidak ambigu).

### Langkah 2 — Tarik data
- Script mengambil semua data per laga (aturan jenjang di `DECISIONS.md` B,
  daftar di `config/sources.yaml`): statistik musim, 5–10 laga terakhir,
  kandang/tandang, jadwal istirahat, cedera, lineup, dan harga pasar lain.
- Selalu pakai jenjang tertinggi yang tersedia. Setiap data disimpan dengan
  **jenjang + sumber + jam pengambilan**.

### Langkah 3 — Validasi
- Script mengecek kelengkapan dan umur data.
- Data bolong atau basi → status `DATA_INCOMPLETE` atau `HOLD`.
- Cedera/lineup lebih tua dari 3 jam = "basi", wajib diambil ulang sebelum
  dipakai di tiket final (ambang di `config/playstyle.yaml` → `data`).
- Cedera & lineup dicek silang minimal 2 sumber (`DECISIONS.md` B2); kalau
  beda, laporan menampilkan keduanya.

### Langkah 4 — Simulasi 100.000x
- Setiap laga disimulasikan 100.000 kali (NBA: Student-t + OT; bola:
  Dixon-Coles), termasuk skenario skuad (lengkap, absen 1, absen 2, absen 4
  pemain inti).
- Semua hasil simulasi disimpan; moneyline, spread, Under/Over, BTTS semuanya
  dinilai dari hasil simulasi yang sama.

### Langkah 5 — Bandingkan dengan pasar
- Peluang model dibandingkan dengan peluang no-vig dari pasar lain dan harga ¢
  di jup.ag. Hasilnya: edge, EV, dan selisih yang aneh.
- Rumus devig & blend ada di Blueprint §5c; bobot `w` dibaca dari
  `config/playstyle.yaml` → `blend`.

### Langkah 6 — Deteksi anomali
- Tandai kaki **ANOMALI** bila memenuhi ambang di `config/playstyle.yaml` →
  `anomaly` (selisih jup.ag vs pasar lain, selisih model vs pasar, pergerakan
  harga tajam).
- Anomali bukan otomatis peluang bagus. Muse wajib mencari penjelasannya dulu
  sebelum kaki itu boleh dipakai.

### Langkah 7 — Filter keras
- Kaki yang kena aturan coret (Blueprint §7a, ambang di
  `config/playstyle.yaml` → `filters`) dibuang dan alasannya dicatat.
- Yang dicoret tidak boleh muncul di tiket mana pun.

### Langkah 8 — Racik tiket
- Optimizer mencari kombinasi Tiket Asuransi + Tiket Utama terbaik, plus
  alternatif (Blueprint §6, default di `config/playstyle.yaml` → `tickets`,
  `optimizer`, `combo`).
- Tampilkan 3 racikan teratas: paling aman, paling seimbang, paling agresif.

### Langkah 9 — Kritikus
- Prompt terpisah (tidak diberi tahu tiket itu dianggap bagus) mencari 3 titik
  gagal terburuk per kaki dan menyebut pemain sakelar yang harus dicek ulang
  sebelum mulai.
- Kritikus hanya boleh mengutip angka dari file JSON analisis. Dia tidak boleh
  membuat angka baru.

### Langkah 10 — Laporan & catat
- Laporan dikirim dengan format tetap (§3 di bawah).
- Setelah user konfirmasi tiket yang dipasang, tiket masuk ledger
  (`python cli.py log ...`).

### Cek ulang sebelum mulai (opsional)
- User bisa kirim "cek ulang" sekitar 30–60 menit sebelum laga
  (`python cli.py recheck ...`).
- Muse menarik ulang cedera dan lineup, lalu bilang apakah tiket tetap aman
  atau kaki mana yang perlu diganti.

---

## 3. Format laporan Telegram (tetap, urut)

Selalu memakai urutan yang sama supaya mudah dibaca dari HP. Kalau terlalu
panjang untuk satu pesan, bagi menjadi beberapa pesan berurutan.

```markdown
📋 ANALISIS PARLAY — {tanggal} {jam WIB}
Data diambil: {jam} | Simulasi: 100.000x per laga

1) STATUS LAGA
✅ {Tim A vs Tim B} — data lengkap
⚠️ {Tim C vs Tim D} — HOLD: lineup belum keluar
❌ {Tim E vs Tim F} — DATA_INCOMPLETE: cedera gagal diambil

2) KANDIDAT KAKI (urut dari peluang tertinggi)
{Kaki} | Model {x}% | Pasar {y}% | jup.ag {z}¢ | Edge {+/-}% | 🟢/🟡/🔴

3) SKENARIO SKUAD (NBA)
{Tim}: lengkap {x}% → tanpa {pemain} {y}% → tanpa 2 inti {z}%

4) ANOMALI PASAR
{Kaki}: jup.ag {z}¢ vs Polymarket {y}¢ → {penjelasan}

5) RACIKAN TERBAIK (3 opsi)
Opsi A — Paling aman
  🛡️ Asuransi: {kaki 1} + {kaki 2} → {x}x | P menang {p}%
  🚀 Utama: {kaki ...} → {x}x | P menang {p}%
  P(rugi total) {p}% | P(min. balik modal) {p}% | EV {+/-}${n}
  Skenario: dua-duanya menang +${a} | hanya Asuransi +${b} | hanya Utama +${c} | dua-duanya kalah −${d}
Opsi B — Seimbang ...
Opsi C — Agresif ...

6) LAMPU MERAH (kritikus)
{Kaki}: 1) ... 2) ... 3) ...

7) PEMAIN SAKELAR — cek ulang sebelum mulai
{Pemain} ({status}) → kalau OUT: ganti {kaki X} dengan {kaki Y}

🧾 Log: {script} jalan {jam}, {iterasi} iterasi, sumber: {daftar}
```

Aturan pengisian:
- Semua bagian dalam kurung kurawal diisi dari output script.
- Bagian yang datanya tidak ada ditulis "tidak tersedia", tidak dihapus
  diam-diam.
- Kalau dua sumber berbeda (misal status cedera), tampilkan keduanya.

---

## 4. Aturan anti-halusinasi (Blueprint §7c)

- Setiap angka di laporan wajib berasal dari file output script. Script
  menyertakan ID untuk setiap angka; sebelum laporan dikirim, validator
  mengecek bahwa semua angka di teks memang ada di output.
- Muse dilarang menulis "sudah disimulasikan" kalau script simulasi tidak
  benar-benar berjalan. Log eksekusi (waktu, jumlah iterasi) ditampilkan di
  akhir laporan.
- Kalau ditanya sesuatu yang tidak ada datanya, jawabannya "data tidak
  tersedia", bukan perkiraan.
- Opini taktis (misalnya gaya main pelatih) boleh, tapi wajib diberi label
  **[opini]** dan tidak boleh mengubah angka peluang.

---

## 5. Pintu masuk (Blueprint §10)

Satu pintu: `cli.py` — `analyze` / `recheck` / `log` / `recap`.

```bash
python cli.py analyze --input slate.json [--out out.json]
    # Tahap 2b ✓ — menarik data + validasi (langkah 2-3), tulis
    # out/analysis_<slate_id>.json. Simulasi/tiket Tahap 3+.
python cli.py recheck --ticket <id>        # Tahap 5  (belum tersedia di Tahap 1)
python cli.py log --file ticket.json       # Tahap 1  ✓
python cli.py recap                        # Tahap 1  ✓
```

Semua langkah SOP dijalankan berurutan di dalam pintu itu, jadi tidak ada
langkah yang bisa terlewat. Jangan menjalankan modul di bawah `cli.py` secara
langsung untuk analisis produksi.
