"""Penarik berita NBA dari ESPN JSON publik (jenjang 2) — modul news.

News adalah KONTEKS, bukan angka (DECISIONS.md 2026-11-23 10:41 WIB):
berita tidak pernah diubah jadi angka simulasi. Fungsinya memberi
bahan bacaan + argumen saat mau pasang — berita cedera, berita tim,
apa pun yang relevan dengan laga itu. Berita jelek pun berguna
sebagai bahan bacaan.

Sumber: feed liga ESPN (site.api.espn.com, terverifikasi di probe
2026-11-23 — lihat probes/HASIL-PROBE-NEWS.md). Endpoint per-tim
yang diduga mengembalikan body kosong, jadi filter per laga
dilakukan di sisi klien: artikel relevan bila kategori tim-nya
cocok dengan salah satu tim laga, atau nama lengkap tim muncul di
judul/ringkasan. Satu panggilan feed liga per analyze/recheck
(maksimal news.max_items_fetch artikel), dipakai untuk satu laga.

KONTRAK: mengikuti pola ingest/espn.py — FetchResult dengan
source+tier+time per datum; fetch gagal -> ok=False + error (tidak
melempar); bedakan "tidak ada berita" (ok=True, data=[]) dari
"gagal ambil" (ok=False). Semua ambang dari config/playstyle.yaml
section `news:` (kunci hilang -> ok=False, tidak ada default
diam-diam). 0 kredit Odds API.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import config as config_mod
from ingest import matching as matching_mod
from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

SOURCE = "ESPN"
TIER = 2

NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"

# Kota -> julukan (balikan NBA_NICKNAME_TO_CITY) untuk nama lengkap tim
# ("oklahoma city thunder") yang dipakai di pencocokan judul.
_KOTA_KE_JULUKAN = {
    kota: julukan for julukan, kota in matching_mod.NBA_NICKNAME_TO_CITY.items()
}

# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan. Jeda dibaca dari config news.rate_gap_seconds setiap kali
# _default_client dipanggil (lihat komentar di sana).
_LIMITER = RateLimiter(1.0)


def _parse_waktu(nilai) -> datetime | None:
    """Parse ISO 8601 (dengan zona waktu) menjadi datetime; None bila gagal."""
    if not isinstance(nilai, str) or not nilai.strip():
        return None
    try:
        parsed = datetime.fromisoformat(nilai.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _baca_config(cfg: dict | None) -> dict:
    """Baca + validasi section `news:` dari config.

    cfg None -> baca playstyle.yaml. Mengembalikan dict parameter
    tervalidasi. ConfigError bila section/kunci hilang atau nilainya
    tidak valid — pemanggil mengubahnya jadi FetchResult gagal.
    """
    if cfg is None:
        cfg = config_mod.load_playstyle()
    section = cfg.get("news")
    if not isinstance(section, dict):
        raise config_mod.ConfigError("config kehilangan section: news")
    params: dict = {}
    for kunci, jenis in (
        ("max_items_fetch", "int_positif"),
        ("max_items_per_match", "int_positif"),
        ("max_age_hours", "angka_positif"),
        ("cache_ttl_seconds", "angka_non_negatif"),
        ("rate_gap_seconds", "angka_non_negatif"),
    ):
        if kunci not in section:
            raise config_mod.ConfigError(f"kunci config tidak ditemukan: news.{kunci}")
        nilai = section[kunci]
        if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
            raise config_mod.ConfigError(f"news.{kunci} tidak valid: {nilai!r}")
        if jenis == "int_positif" and (not isinstance(nilai, int) or nilai <= 0):
            raise config_mod.ConfigError(f"news.{kunci} tidak valid: {nilai!r}")
        if jenis == "angka_positif" and nilai <= 0:
            raise config_mod.ConfigError(f"news.{kunci} tidak valid: {nilai!r}")
        if jenis == "angka_non_negatif" and nilai < 0:
            raise config_mod.ConfigError(f"news.{kunci} tidak valid: {nilai!r}")
        params[kunci] = nilai
    return params


def _default_client(params: dict) -> HttpClient:
    """Buat HttpClient default (limiter bersama + cache config)."""
    # Jeda limiter bersama di-set dari config setiap panggilan: satu
    # limiter untuk semua pemanggilan (agar jeda antar panggilan tetap
    # berlaku), tapi angkanya tetap wewenang config, bukan kode.
    _LIMITER.min_gap_seconds = float(params["rate_gap_seconds"])
    return HttpClient(
        _LIMITER,
        cache=DiskCache(default_cache_dir(), float(params["cache_ttl_seconds"])),
    )


def parse_news(data: dict) -> list[dict]:
    """Ubah respons JSON news ESPN jadi list artikel.

    Setiap artikel: {id, headline, description, published,
    last_modified, url, type, premium, teams: [{id, name}],
    athletes: [nama]}. Field yang tidak ada -> None/list kosong
    (bukan ditebak). Artikel tanpa headline DILEWATI (tidak ada
    yang bisa dibaca). "time" (jam pengambilan) TIDAK diisi di sini
    — ditambahkan fetch_news_nba dari fetched_at FetchResult.
    ValueError("espn_format_changed") bila field articles tidak ada.
    """
    articles = data.get("articles")
    if not isinstance(articles, list):
        raise ValueError("espn_format_changed")
    hasil: list[dict] = []
    for artikel in articles:
        if not isinstance(artikel, dict):
            continue
        headline = artikel.get("headline")
        if not isinstance(headline, str) or not headline.strip():
            continue
        teams: list[dict] = []
        athletes: list[str] = []
        for kategori in artikel.get("categories") or []:
            if not isinstance(kategori, dict):
                continue
            jenis = kategori.get("type")
            nama = kategori.get("description")
            if jenis == "team" and isinstance(nama, str) and nama:
                tim = kategori.get("team") or {}
                teams.append(
                    {
                        "id": tim.get("id") if isinstance(tim, dict) else None,
                        "name": nama,
                    }
                )
            elif jenis == "athlete" and isinstance(nama, str) and nama:
                athletes.append(nama)
        links = artikel.get("links") or {}
        web = links.get("web") or {} if isinstance(links, dict) else {}
        url = web.get("href") if isinstance(web, dict) else None
        artikel_id = artikel.get("id")
        hasil.append(
            {
                "id": str(artikel_id) if artikel_id is not None else None,
                "headline": headline.strip(),
                "description": (
                    artikel.get("description")
                    if isinstance(artikel.get("description"), str)
                    else None
                ),
                "published": (
                    artikel.get("published")
                    if isinstance(artikel.get("published"), str)
                    else None
                ),
                "last_modified": (
                    artikel.get("lastModified")
                    if isinstance(artikel.get("lastModified"), str)
                    else None
                ),
                "url": url if isinstance(url, str) else None,
                "type": (
                    artikel.get("type")
                    if isinstance(artikel.get("type"), str)
                    else None
                ),
                "premium": bool(artikel.get("premium")),
                "teams": teams,
                "athletes": athletes,
            }
        )
    return hasil


def _kota_tricode(tricode: str) -> str | None:
    """Kota kanonik satu tricode NBA (mis. DEN -> 'denver'); None bila asing."""
    return matching_mod.NBA_TRICODE_TO_CITY.get(tricode.strip().lower())


def _nama_lengkap_tim(tricode: str) -> str | None:
    """Nama lengkap ternormalisasi satu tricode ('oklahoma city thunder').

    None bila tricode/julukan tidak dikenal.
    """
    kota = _kota_tricode(tricode)
    if kota is None:
        return None
    julukan = _KOTA_KE_JULUKAN.get(kota)
    if julukan is None:
        return None
    return f"{kota} {julukan}"


def _normalisasi_teks(teks: str) -> str:
    """Normalisasi teks untuk pencocokan substring (huruf kecil + spasi)."""
    rendah = teks.lower()
    rendah = re.sub(r"[^a-z0-9 ]+", " ", rendah)
    return re.sub(r"\s+", " ", rendah).strip()


def article_relevan(artikel: dict, home_tricode: str, away_tricode: str) -> bool:
    """Apakah artikel ini relevan dengan laga (home vs away)?

    Relevan bila SALAH SATU terjadi:
    (a) kategori tim artikel (nama lengkap ESPN, mis. 'Denver
        Nuggets') menormalisasi ke kota salah satu tim laga; atau
    (b) nama lengkap salah satu tim ('oklahoma city thunder')
        muncul di judul/ringkasan (fallback bila artikel tidak
        membawa kategori tim).
    Julukan saja ('Thunder') TIDAK dipakai di (b) — kata itu bisa
    muncul sebagai kata umum ('thunderous'), sementara nama lengkap
    hampir tidak pernah false positive.
    """
    kota_home = _kota_tricode(home_tricode)
    kota_away = _kota_tricode(away_tricode)
    kota_laga = {k for k in (kota_home, kota_away) if k}
    for tim in artikel.get("teams") or []:
        if not isinstance(tim, dict):
            continue
        nama = tim.get("name")
        if (
            isinstance(nama, str)
            and nama
            and matching_mod.normalize_team(nama, "nba") in kota_laga
        ):
            return True
    teks = _normalisasi_teks(
        f"{artikel.get('headline') or ''} {artikel.get('description') or ''}"
    )
    for tricode in (home_tricode, away_tricode):
        nama_lengkap = _nama_lengkap_tim(tricode)
        if nama_lengkap and nama_lengkap in teks:
            return True
    return False


def fetch_news_nba(
    home_tricode: str,
    away_tricode: str,
    game_date: str,
    client: HttpClient | None = None,
    cfg: dict | None = None,
) -> FetchResult:
    """Ambil berita NBA yang relevan dengan satu laga dari ESPN.

    home_tricode/away_tricode: tricode tim ('ATL'/'DET'). game_date:
    tanggal Eastern 'YYYY-MM-DD' (dicatat di extra; jendela umur
    dihitung dari jam ambil, bukan tanggal laga — analisis dibuat
    di hari laga). client: HttpClient bersama (opsional). cfg: dict
    playstyle (None = baca playstyle.yaml).

    data: list artikel relevan (lihat parse_news) + 'source'/'tier'/
    'time' per item, urut terbaru dulu, maksimal
    news.max_items_per_match. Artikel tanpa jam terbit yang bisa
    di-parse TETAP disertakan (published None) — recheck yang
    memperlakukannya sebagai bukan-berita-mendadak (tidak bisa
    dibuktikan terbit setelah analisis). data=[] + ok=True berarti
    'tidak ada berita' (bukan gagal). Fetch gagal -> ok=False
    (tidak melempar). Config hilang/rusak -> ok=False TANPA request
    HTTP (validasi config dulu).
    """
    fetched_at = now_iso()
    if (
        not isinstance(home_tricode, str)
        or not home_tricode.strip()
        or not isinstance(away_tricode, str)
        or not away_tricode.strip()
    ):
        return FetchResult(SOURCE, TIER, fetched_at, False, error="tricode_tidak_valid")
    try:
        datetime.strptime(game_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error=f"tanggal_tidak_valid: {game_date!r}"
        )
    try:
        params = _baca_config(cfg)
    except config_mod.ConfigError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))

    url = f"{NEWS_URL}?limit={params['max_items_fetch']}"
    resp = (client or _default_client(params)).get(url)
    if resp.get("status") != 200:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"http_{resp.get('status')}: {resp.get('error') or 'espn gagal'}",
        )
    data = parse_json_body(resp)
    if not isinstance(data, dict):
        return FetchResult(SOURCE, TIER, fetched_at, False, error="espn_format_changed")
    try:
        artikel = parse_news(data)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))

    jam_ambil = _parse_waktu(fetched_at) or datetime.now(UTC)
    batas_umur = jam_ambil - timedelta(hours=float(params["max_age_hours"]))
    relevan: list[dict] = []
    for item in artikel:
        if not article_relevan(item, home_tricode, away_tricode):
            continue
        terbit = _parse_waktu(item.get("published"))
        if terbit is not None and terbit < batas_umur:
            continue
        relevan.append(item)
    # Terbaru dulu; yang tanpa jam terbit di belakang (jam tidak diketahui).
    relevan.sort(
        key=lambda item: (
            _parse_waktu(item.get("published")) or datetime.min.replace(tzinfo=UTC)
        ),
        reverse=True,
    )
    dipilih = relevan[: params["max_items_per_match"]]
    for item in dipilih:
        item["source"] = SOURCE
        item["tier"] = TIER
        item["time"] = fetched_at
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=dipilih,
        extra={
            "home_tricode": home_tricode.strip().upper(),
            "away_tricode": away_tricode.strip().upper(),
            "game_date": game_date,
            "n_fetched": len(artikel),
            "n_relevant": len(relevan),
            "n_kept": len(dipilih),
        },
    )
