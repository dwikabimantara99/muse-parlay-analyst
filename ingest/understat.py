"""Penarik Understat (xG sepak bola) + gate status — Tahap 2b.

Jenjang 2 (DECISIONS.md B4): rantai xG bola adalah resmi → Understat.
Understat TIDAK punya API publik resmi; data tertanam sebagai JSON di
dalam halaman HTML (``teamsData``). Situs sedang maintenance sejak probe
2a (2026-11-20); cek harian otomatis (``probes/check_understat.py``)
menulis status ke ``probes/out/understat_status.json``.

GATE: ``fetch_xg`` HANYA mengambil data bila ``is_available()`` True,
yaitu status == "up" DAN ``checked_at`` dalam 24 jam terakhir. Bila tidak,
fetch mengembalikan ``ok=False`` dengan error ``understat_not_available:
<alasan>`` dan pemanggil (slate builder) menerapkan aturan B4 (TANPA_XG).

PERINGATAN: parser ``parse_teams_data`` BELUM terverifikasi terhadap
halaman live — halaman live tidak bisa diambil karena maintenance. Parser
ini ditulis dari penanda yang dicari probe 2a (``teamsData``/``datesData``)
dan dites hanya dengan fixture HTML sintetis. Begitu Understat kembali,
jalankan tes kesehatan scraper terhadap halaman live sebelum memakai xG
untuk keputusan.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    repo_root,
)

SOURCE = "Understat"
TIER = 2
BASE_URL = "https://understat.com/league"

# Umur maksimum status "up" agar Understat dianggap tersedia (aturan dari
# probes/check_understat.py: re-aktivasi otomatis bila status "up" dan
# checked_at < 24 jam).
STATUS_MAX_AGE_HOURS = 24

MAINTENANCE_TEXT = "We will come back soon"

# Slug liga di URL Understat (terverifikasi probe 2a: EPL + La_liga).
LEAGUE_SLUGS = {
    "EPL": "EPL",
    "LaLiga": "La_liga",
    "La_liga": "La_liga",
}

# teamsData tertanam sebagai: var teamsData = JSON.parse('...').
_TEAMS_DATA_RE = re.compile(
    r"teamsData\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)*)'\)", re.DOTALL
)

# Escape JS di dalam string JSON.parse('...').
_JS_ESCAPE_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|.)", re.DOTALL)
_JS_SIMPLE_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "0": "\0",
}


def default_status_path() -> Path:
    """Path default file status (ditulis probes/check_understat.py)."""
    return repo_root() / "probes" / "out" / "understat_status.json"


def read_status(status_path: str | Path | None = None) -> dict:
    """Baca file status Understat.

    Bila file hilang atau rusak, kembalikan ``{"status": "unknown", ...}``
    (bukan melempar) — pemanggil memperlakukannya sebagai "tidak tersedia".
    """
    path = Path(status_path) if status_path is not None else default_status_path()
    if not path.exists():
        return {
            "status": "unknown",
            "checked_at": None,
            "error": f"file status tidak ditemukan: {path}",
        }
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "status": "unknown",
            "checked_at": None,
            "error": f"file status rusak: {exc}",
        }
    if not isinstance(record, dict) or "status" not in record:
        return {
            "status": "unknown",
            "checked_at": None,
            "error": "file status bukan dict / tanpa kunci 'status'",
        }
    return record


def is_available(now: datetime | None = None) -> tuple[bool, str]:
    """Apakah Understat boleh dipakai? (status "up" + checked_at < 24 jam).

    Mengembalikan ``(tersedia, alasan)``. ``now`` bisa di-inject (untuk
    tes); default jam sekarang (UTC).
    """
    record = read_status()
    status = record.get("status")
    if status != "up":
        return False, f"status {status!r} (bukan 'up')"
    checked_at = record.get("checked_at")
    if not isinstance(checked_at, str):
        return False, "checked_at tidak ada / bukan string"
    try:
        checked = datetime.fromisoformat(checked_at)
    except ValueError:
        return False, f"checked_at tidak bisa dibaca: {checked_at!r}"
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    moment = now or datetime.now(UTC)
    age = moment - checked
    if age < timedelta(0):
        return False, "checked_at di masa depan"
    if age > timedelta(hours=STATUS_MAX_AGE_HOURS):
        return (
            False,
            f"checked_at basi: {age.total_seconds() / 3600:.1f} jam lalu "
            f"(> {STATUS_MAX_AGE_HOURS} jam)",
        )
    return True, f"up, checked_at {checked_at}"


def _js_unescape(text: str) -> str:
    """Buka escape string JS (\\', \\\\, \\uXXXX, \\n, ...)."""

    def _replace(match: re.Match) -> str:
        token = match.group(1)
        if token.startswith("u") and len(token) == 5:
            return chr(int(token[1:], 16))
        if token in _JS_SIMPLE_ESCAPES:
            return _JS_SIMPLE_ESCAPES[token]
        return token

    return _JS_ESCAPE_RE.sub(_replace, text)


def parse_teams_data(html: str) -> dict:
    """Parse ``teamsData`` dari HTML halaman liga Understat (fungsi murni).

    Mengembalikan dict data tim (kunci = id tim). Raise ``ValueError``
    bila penanda ``teamsData`` tidak ditemukan atau JSON-nya tidak bisa
    di-parse. BELUM terverifikasi terhadap halaman live (lihat docstring
    modul) — hanya dites dengan fixture sintetis.
    """
    match = _TEAMS_DATA_RE.search(html)
    if match is None:
        raise ValueError("penanda teamsData tidak ditemukan di HTML")
    raw = match.group(1)
    try:
        text = _js_unescape(raw)
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"JSON teamsData tidak bisa di-parse: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("teamsData bukan dict")
    return data


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(3.0)


def fetch_xg(
    league: str = "EPL",
    season: int = 2025,
    client: HttpClient | None = None,
) -> FetchResult:
    """Ambil data tim + xG Understat untuk satu liga/musim.

    GATE dulu lewat ``is_available()``: bila Understat tidak tersedia,
    kembalikan ``ok=False`` dengan error ``understat_not_available:
    <alasan>`` tanpa menyentuh network — pemanggil menerapkan TANPA_XG.
    Bila tersedia, ambil halaman liga dan parse ``teamsData``. Halaman
    maintenance (HTTP 200 + teks maintenance) juga ditolak sebagai
    ``understat_not_available`` (pertahanan berlapis bila file status
    sudah kedaluwarsa).
    """
    fetched_at = now_iso()
    available, reason = is_available()
    if not available:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=f"understat_not_available: {reason}",
        )
    slug = LEAGUE_SLUGS.get(league, league)
    url = f"{BASE_URL}/{slug}/{season}"
    http = client
    if http is None:
        cache = DiskCache(default_cache_dir(), ttl_seconds=3600)
        http = HttpClient(_LIMITER, cache=cache)
    result = http.get(url)
    if result.get("status") != 200:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=(
                f"http_{result.get('status')}: "
                f"{result.get('error') or 'tanpa body'}"
            ),
        )
    body = str(result.get("body") or "")
    if MAINTENANCE_TEXT in body:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error="understat_not_available: halaman maintenance",
        )
    try:
        data = parse_teams_data(body)
    except ValueError as exc:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=f"parse_gagal: {exc}",
        )
    return FetchResult(
        source=SOURCE,
        tier=TIER,
        fetched_at=fetched_at,
        ok=True,
        data=data,
    )
