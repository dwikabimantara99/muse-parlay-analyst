# Hasil Probe Berita NBA (modul news)

Probe: 2026-11-23 ~10:50 WIB. Total 6 request. Semua sumber gratis,
tanpa kunci, tanpa signup. 0 kredit Odds API.

## Ringkasan

| Sumber | Putusan | Alasan singkat |
|---|---|---|
| ESPN JSON (`site.api.espn.com/.../nba/news`) | **PAKAI** | JSON terstruktur, kategori tim per artikel, jam terbit, 50 artikel ≈ 2 hari terakhir |
| Google News RSS | **CADANGAN** | Berfungsi (100 item/kueri, 30 penerbit), tapi agregator + 2 request per laga; tidak dipakai sekarang |
| NBA resmi (nba.com) | **JANGAN** | Tidak ada API JSON/RSS berita; hanya halaman HTML (Next.js) — mengupas HTML rapuh, di luar pola repo |

## 1. ESPN — PAKAI (sumber utama)

- Endpoint: `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=N`
- Satu panggilan mengembalikan feed liga (terbaru dulu). `limit=50`
  mengembalikan 50 artikel, terbit 21–23 Nov 2026 (± 2 hari).
- Jenis artikel (limit=50): Recap 18, Media 18, HeadlineNews 11,
  Story 3.
- Tiap artikel membawa: `headline`, `description` (ringkasan),
  `published` (ISO), `lastModified`, `links.web.href` (URL baca),
  `type`, `premium`, dan `categories` — termasuk kategori `team`
  (nama + ID tim ESPN) dan `event` ("Denver Nuggets @ Chicago
  Bulls"). Kategori tim inilah yang dipakai fetcher untuk
  mencocokkan berita ke laga.
- Endpoint per-tim yang diduga
  (`.../nba/teams/25/news`) mengembalikan status 200 dengan body
  kosong (tanpa daftar artikel) — jadi filter per-tim dilakukan di
  sisi klien dari feed liga, bukan dari endpoint per-tim.
- Batasan jujur: bahasa Inggris (laporan menampilkan judul asli,
  tidak diterjemahkan mesin); artikel `Media` adalah sorotan video
  (judulnya tetap informatif, tapi bukan teks berita); tidak ada
  header rate limit yang terlihat (fetcher memakai jeda 1 detik,
  sama seperti modul ESPN lain).
- Bukti: `probes/out/probe_news_espn.json`.

Contoh isi nyata (23 Nov 2026, dari feed):

- "Jokic's triple-double, Murray's 45 points lead Nuggets to
  151-145 overtime win over Bulls" (Recap, terbit 03:15 UTC,
  kategori tim: Chicago Bulls, Denver Nuggets)
- "Cooper Flagg saves Mavericks with late free throws to hold off
  Jazz comeback in 119-115 win" (Recap, terbit 02:57 UTC,
  kategori tim: Utah Jazz, Dallas Mavericks)
- "Wizards rout the Magic 116-96 to win their 3rd straight
  following an 8-game skid" (Recap, terbit 02:33 UTC, kategori
  tim: Washington Wizards, Orlando Magic)

## 2. Google News RSS — CADANGAN (tidak dipakai sekarang)

- Endpoint: `https://news.google.com/rss/search?q=<tim>+NBA&hl=en-US&gl=US&ceid=US:en`
- Kueri "Oklahoma City Thunder NBA": 100 item, 30 penerbit
  (ESPN, Yahoo Sports, USA Today, Bleacher Report, ...).
- Contoh nyata: "Shai-Gilgeous Alexander, Giannis Antetokounmpo sit
  out Heat's victory over Thunder" (Yahoo Sports, 23 Nov 02:06 UTC);
  "Thunder are NBA's deepest team, but not even they can weather
  all these injuries" (USA Today, 23 Nov 01:55 UTC).
- Alasan cadangan, bukan utama: agregator (bukan sumber primer);
  hanya judul + penerbit + tanggal (ringkasan berupa cuplikan HTML,
  bukan teks bersih); butuh 1 request per tim (2 per laga),
  sementara feed liga ESPN 1 request untuk semua laga.
- Bukti: `probes/out/probe_news_google.json`.

## 3. NBA resmi (nba.com) — JANGAN

- `https://www.nba.com/news`: status 200, HTML ±320 ribu karakter
  (Next.js, data tertanam di `__NEXT_DATA__`) — bukan API.
- `https://www.nba.com/rss/nba.xml`: status 404 — tidak ada feed RSS
  di alamat itu.
- Tidak ada endpoint JSON/RSS berita resmi yang ditemukan.
  Mengupas HTML Next.js rapuh (struktur berubah sewaktu-waktu) dan
  di luar pola repo (semua fetcher memakai JSON API).
- Bukti: `probes/out/probe_news_nba.json`.

## Keputusan pemakaian

- Fetcher (`ingest/news_nba.py`) memakai ESPN sebagai satu-satunya
  sumber (jenjang 2, sama seperti cedera ESPN). Satu panggilan feed
  liga per analyze/recheck, lalu filter per laga di sisi klien.
- Google News RSS dicatat sebagai cadangan bila ESPN gagal di masa
  depan — belum diimplementasikan sebagai fetcher.
