"""Penarik Official NBA Injury Report (PDF resmi, jenjang 1).

Sumber UTAMA cedera NBA (config/sources.yaml nba_injuries; D4 TERJAWAB).
Alur: ambil halaman resmi, ekstrak tautan PDF terbaru
(pola Injury-Report_YYYY-MM-DD_HH_MMAP.pdf); bila halaman gagal, coba file
12:00 AM hari yang diminta. PDF diunduh mentah (bytes) lalu diparsing
dengan STDLIB SAJA (zlib + regex) — HttpClient tidak dipakai untuk PDF
karena ia mendekode body sebagai teks UTF-8 dan akan merusak bytes PDF.

VERDIK PARSE PDF STDLIB (terverifikasi 2026-11-20 pada PDF asli
Injury-Report_2026-11-20_12_00AM.pdf, 98.980 byte, 7 halaman):
BERHASIL. PDF dibuat GemBox.Document 3.1, font TrueType dengan
WinAnsiEncoding, teks sebagai string literal di operator Tj (1.007 fragmen,
0 TJ). Tidak ada ToUnicode CMap — tidak diperlukan karena byte teks sudah
WinAnsi (cp1252). Parser tidak memakai tabel xref (memindai stream dengan
regex), jadi tetap bekerja bila xref rusak.

Keterbatasan yang diketahui (dicatat jujur, bukan ditebak):

- Teks direkonstruksi per baris dari koordinat Td; sel yang membungkus
  (alasan cedera panjang) digabung ke baris logis bila celah y antar
  fragmen <= 12 poin (pitch baris ~22 poin, celah bungkus ~7 poin).
- String literal PDF dengan tanda kurung bersarang tanpa escape tidak
  didukung (tidak muncul di PDF ini).
- URL halaman memuat musim ("2026-27") — perlu diperbarui saat musim baru.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ingest.common import (
    DEFAULT_TIMEOUT,
    USER_AGENT,
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    open_url,
)

SOURCE = "Official NBA Injury Report"
TIER = 1
CACHE_TTL_SECONDS = 900
RATE_GAP_SECONDS = 1.0

REPORT_PAGE_URL = "https://official.nba.com/nba-injury-report-2026-27-season/"
PDF_BASE_URL = "https://ak-static.cms.nba.com/referee/injury/"

EASTERN = ZoneInfo("America/New_York")

# Pola nama file PDF resmi, misal Injury-Report_2026-11-20_12_00AM.pdf
# (jam per 15 menit; file 12:00 AM selalu ada sebagai laporan awal hari).
PDF_NAME_RE = re.compile(
    r"Injury-Report_(\d{4})-(\d{2})-(\d{2})_(\d{1,2})_(\d{2})(AM|PM)\.pdf"
)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)

# --- Parser PDF (stdlib) -------------------------------------------------

# Celah y maksimum antar fragmen satu baris logis (lihat docstring modul).
_LINE_GAP_PT = 12.0

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
# Token content stream: string literal, string heksadesimal, array,
# angka, nama, dan operator teks yang dilacak.
_TOKEN_RE = re.compile(
    rb"\((?:\\.|[^\\()])*\)"  # string literal (escape ditangani)
    rb"|<[0-9A-Fa-f\s]+>"  # string heksadesimal
    rb"|\[(?:[^\[\]]|\((?:\\.|[^\\()])*\))*\]"  # array (untuk TJ)
    rb"|[+-]?[0-9]*\.?[0-9]+"
    rb"|/[A-Za-z0-9_.*+-]+"
    rb"|BT|ET|Td|TD|T\*|Tj|TJ|Tm|TL|'|\"",
    re.S,
)
_STRING_IN_ARRAY_RE = re.compile(rb"\((?:\\.|[^\\()])*\)")

_ESCAPES = {
    ord("n"): 10,
    ord("r"): 13,
    ord("t"): 9,
    ord("b"): 8,
    ord("f"): 12,
    ord("("): 40,
    ord(")"): 41,
    ord("\\"): 92,
}


def _unescape_pdf_string(raw: bytes) -> str:
    """Ubah isi string literal PDF (tanpa kurung) jadi teks.

    Menangani escape \\n \\r \\t \\b \\f \\( \\) \\\\ dan oktal \\ddd.
    Byte didekode sebagai cp1252 (WinAnsiEncoding, sesuai font PDF ini).
    """
    out = bytearray()
    i = 0
    while i < len(raw):
        byte = raw[i]
        if byte == 0x5C and i + 1 < len(raw):  # backslash
            nxt = raw[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if 48 <= nxt <= 55:  # digit oktal
                j = i + 1
                digits = bytearray()
                while j < len(raw) and len(digits) < 3 and 48 <= raw[j] <= 55:
                    digits.append(raw[j])
                    j += 1
                out.append(int(bytes(digits), 8))
                i = j
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(byte)
        i += 1
    return bytes(out).decode("cp1252", errors="replace")


def _decode_token(token: bytes) -> str:
    """Dekode satu token string (literal atau heksadesimal) jadi teks."""
    if token.startswith(b"("):
        return _unescape_pdf_string(token[1:-1])
    if token.startswith(b"<"):
        hex_text = re.sub(rb"\s+", b"", token[1:-1])
        if len(hex_text) % 2:
            hex_text += b"0"
        try:
            return bytes.fromhex(hex_text.decode("ascii")).decode(
                "cp1252", errors="replace"
            )
        except ValueError:
            return ""
    return ""


def _extract_fragments(content: bytes) -> list[tuple[float, float, str]]:
    """Ekstrak fragmen teks berposisi (y, x, teks) dari satu content stream.

    Melacak matriks teks lewat operator Td/TD/Tm/TL/T*; teks dari Tj/TJ
    serta ' dan ". Mengembalikan list kosong bila stream bukan teks.
    """
    fragments: list[tuple[float, float, str]] = []
    x = y = 0.0
    leading = 12.0
    in_text = False
    stack: list[bytes] = []

    def _numbers(count: int) -> list[float] | None:
        if len(stack) < count:
            return None
        try:
            return [float(tok) for tok in stack[-count:]]
        except ValueError:
            return None

    for match in _TOKEN_RE.finditer(content):
        tok = match.group(0)
        if tok == b"BT":
            in_text, x, y, stack = True, 0.0, 0.0, []
        elif tok == b"ET":
            in_text, stack = False, []
        elif not in_text:
            stack = []
        elif tok in (b"Td", b"TD"):
            nums = _numbers(2)
            if nums:
                x += nums[0]
                y += nums[1]
            stack = []
        elif tok == b"Tm":
            nums = _numbers(6)
            if nums:
                x, y = nums[4], nums[5]
            stack = []
        elif tok == b"TL":
            nums = _numbers(1)
            if nums:
                leading = nums[0]
            stack = []
        elif tok == b"T*":
            y += leading
            stack = []
        elif tok == b"Tj":
            if stack and stack[-1].startswith((b"(", b"<")):
                text = _decode_token(stack[-1])
                if text:
                    fragments.append((y, x, text))
            stack = []
        elif tok == b"TJ":
            if stack and stack[-1].startswith(b"["):
                parts = [
                    _decode_token(part)
                    for part in _STRING_IN_ARRAY_RE.findall(stack[-1])
                ]
                text = "".join(parts)
                if text:
                    fragments.append((y, x, text))
            stack = []
        elif tok in (b"'", b'"'):
            y += leading
            if stack and stack[-1].startswith((b"(", b"<")):
                text = _decode_token(stack[-1])
                if text:
                    fragments.append((y, x, text))
            stack = []
        elif tok.startswith(b"/"):
            stack = []
        else:
            stack.append(tok)
    return fragments


def _fragments_to_lines(fragments: list[tuple[float, float, str]]) -> list[str]:
    """Kelompokkan fragmen berposisi jadi baris-baris teks logis.

    Fragmen diurutkan per y; celah y <= 12 poin digabung ke baris yang
    sama (menangani sel yang membungkus ke 2-3 baris); dalam satu baris
    fragmen diurutkan per x lalu digabung dengan satu spasi — kecuali
    fragmen yang berakhir tanda hubung ("Two-" + "Way" -> "Two-Way").
    """
    if not fragments:
        return []
    ordered = sorted(fragments, key=lambda frag: (frag[0], frag[1]))
    lines: list[str] = []
    band: list[tuple[float, float, str]] = [ordered[0]]
    last_y = ordered[0][0]
    for frag in ordered[1:]:
        if frag[0] - last_y <= _LINE_GAP_PT:
            band.append(frag)
        else:
            lines.append(_join_band(band))
            band = [frag]
        last_y = frag[0]
    lines.append(_join_band(band))
    return [line for line in lines if line.strip()]


def _join_band(band: list[tuple[float, float, str]]) -> str:
    """Gabung fragmen satu baris (urut x); tanpa spasi setelah tanda hubung.

    Hanya bila tanda hubung menempel pada kata ("Two-" + "Way" ->
    "Two-Way"); fragmen "-" yang berdiri sendiri tetap dipisah spasi
    ("G League - Two-Way").
    """
    texts = [text for _, _, text in sorted(band, key=lambda frag: frag[1])]
    joined = texts[0]
    for prev, text in zip(texts, texts[1:], strict=False):
        joined += text if len(prev) > 1 and prev.endswith("-") else " " + text
    return joined


def parse_pdf_text(pdf_bytes: bytes) -> str:
    """Ekstrak teks dari bytes PDF dengan stdlib saja (zlib + regex).

    Mendekompresi stream FlateDecode lalu mengekstrak teks dari operator
    Tj/TJ (plus ' dan "). ValueError("pdf_parse_failed: ...") bila bukan
    PDF, tidak ada stream yang bisa didekompresi, atau tidak ada teks
    yang berhasil diekstrak.
    """
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("pdf_parse_failed: bukan file PDF (header %PDF- hilang)")
    lines: list[str] = []
    n_streams = 0
    for match in _STREAM_RE.finditer(pdf_bytes):
        try:
            content = zlib.decompress(match.group(1))
        except zlib.error:
            continue
        n_streams += 1
        if b"Tj" not in content and b"TJ" not in content:
            continue
        lines.extend(_fragments_to_lines(_extract_fragments(content)))
    if n_streams == 0:
        raise ValueError("pdf_parse_failed: tidak ada stream FlateDecode")
    if not lines:
        raise ValueError("pdf_parse_failed: tidak ada teks yang bisa diekstrak")
    return "\n".join(lines)


# --- Parser daftar cedera --------------------------------------------------

# 30 nama tim NBA (lengkap). Dipakai untuk melacak tim aktif: nama tim
# hanya tercetak di baris pertama tiap blok tim di PDF.
NBA_TEAM_NAMES = (
    "Atlanta Hawks",
    "Boston Celtics",
    "Brooklyn Nets",
    "Charlotte Hornets",
    "Chicago Bulls",
    "Cleveland Cavaliers",
    "Dallas Mavericks",
    "Denver Nuggets",
    "Detroit Pistons",
    "Golden State Warriors",
    "Houston Rockets",
    "Indiana Pacers",
    "LA Clippers",
    "Los Angeles Lakers",
    "Memphis Grizzlies",
    "Miami Heat",
    "Milwaukee Bucks",
    "Minnesota Timberwolves",
    "New Orleans Pelicans",
    "New York Knicks",
    "Oklahoma City Thunder",
    "Orlando Magic",
    "Philadelphia 76ers",
    "Phoenix Suns",
    "Portland Trail Blazers",
    "Sacramento Kings",
    "San Antonio Spurs",
    "Toronto Raptors",
    "Utah Jazz",
    "Washington Wizards",
)

# Nama pemain di PDF berbentuk "Belakang, Depan", misal "Ajayi, Michael",
# "Udeh Jr., Ernest", "McConnell, T.J.". Token nama depan kedua tidak
# boleh berupa kata status (Out/dll) — itu kolom berikutnya.
_PLAYER_RE = re.compile(
    r"([A-Z][A-Za-z'.\-]*(?:\s+(?:Jr\.|Sr\.|II|III|IV))?,\s+"
    r"[A-Z][A-Za-z'.\-]+"
    r"(?:\s+(?!Out\b|Doubtful\b|Questionable\b|Probable\b|Available\b)"
    r"[A-Z][A-Za-z'.\-]+)?)"
)
_STATUS_RE = re.compile(r"\b(Out|Doubtful|Questionable|Probable|Available)\b")
_PAGE_FOOTER_RE = re.compile(r"^Page \d+ of \d+$")


def _find_team(line: str) -> str | None:
    """Cari nama tim NBA di satu baris (cocok terpanjang menang)."""
    found = [name for name in NBA_TEAM_NAMES if name in line]
    if not found:
        return None
    return max(found, key=len)


def parse_injuries(text: str) -> list[dict]:
    """Ubah teks laporan cedera (dari parse_pdf_text) jadi list cedera.

    Setiap entri: {player, team, status, detail}. player dinormalisasi
    dari "Belakang, Depan" menjadi "Depan Belakang" (agar cocok dengan
    format ESPN/Rotowire); status memakai istilah sumber apa adanya
    (Out/Doubtful/Questionable/Probable/Available). Baris tanpa nama
    pemain (lanjutan alasan yang membungkus) ditempel ke detail entri
    sebelumnya. Baris judul/header/footer halaman dilewati. Tim dilacak
    dari baris blok tim; bila tidak ditemukan, team = "UNKNOWN".
    """
    injuries: list[dict] = []
    current_team: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Injury Report:") or _PAGE_FOOTER_RE.match(line):
            continue
        if "Current Status" in line and "Reason" in line:
            continue  # baris header kolom
        team = _find_team(line)
        if team is not None:
            current_team = team
        player_match = _PLAYER_RE.search(line)
        if player_match is None:
            # Lanjutan baris sebelumnya (alasan yang membungkus).
            if injuries and line:
                prev = injuries[-1]
                detail = (prev["detail"] or "") + " " + line
                prev["detail"] = detail.strip() or None
            continue
        last, first = [part.strip() for part in player_match.group(1).split(",", 1)]
        rest = line[player_match.end() :]
        status_match = _STATUS_RE.search(rest)
        if status_match is None:
            status, detail = "UNKNOWN", rest.strip()
        else:
            status = status_match.group(1)
            detail = rest[status_match.end() :].strip()
        injuries.append(
            {
                "player": f"{first} {last}",
                "team": current_team or "UNKNOWN",
                "status": status,
                "detail": detail or None,
            }
        )
    return injuries


# --- Pengambilan -----------------------------------------------------------


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(RATE_GAP_SECONDS)


def _default_client() -> HttpClient:
    """Buat HttpClient default untuk halaman laporan (jeda 1 dtk, cache 900 dtk)."""
    return HttpClient(
        _LIMITER,
        cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
    )


def _pdf_datetime(name: str) -> datetime | None:
    """Ubah nama file PDF jadi datetime (zona Eastern); None bila tak cocok."""
    match = PDF_NAME_RE.search(name)
    if not match:
        return None
    year, month, day, hour, minute, meridiem = match.groups()
    hour_int = int(hour) % 12 + (12 if meridiem == "PM" else 0)
    return datetime(
        int(year), int(month), int(day), hour_int, int(minute), tzinfo=EASTERN
    )


def _latest_pdf_link(html: str, date_str: str) -> str | None:
    """Pilih tautan PDF terbaru untuk tanggal yang diminta dari HTML halaman.

    Mengembalikan URL absolut atau None bila tidak ada tautan untuk
    tanggal itu.
    """
    best_url: str | None = None
    best_time: datetime | None = None
    for href in HREF_RE.findall(html):
        stamp = _pdf_datetime(href)
        if stamp is None:
            continue
        if date_str and stamp.strftime("%Y-%m-%d") != date_str:
            continue
        if best_time is None or stamp > best_time:
            best_time = stamp
            best_url = href
    if best_url is None:
        return None
    return urllib.parse.urljoin(REPORT_PAGE_URL, best_url)


def _fallback_pdf_url(date_str: str) -> str:
    """URL PDF 12:00 AM untuk tanggal yang diminta (laporan awal hari)."""
    return f"{PDF_BASE_URL}Injury-Report_{date_str}_12_00AM.pdf"


def _download_pdf_bytes(
    url: str, limiter: RateLimiter
) -> tuple[int | None, bytes | None, str | None]:
    """Unduh PDF mentah (bytes). HttpClient tidak dipakai: ia mendekode
    body sebagai teks dan akan merusak bytes PDF.

    Mengembalikan (status, bytes, error); tidak melempar.
    """
    host = urllib.parse.urlparse(url).netloc
    limiter.wait(host)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with open_url(request, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.status, resp.read(), None
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def fetch_report(
    date: str | None = None, client: HttpClient | None = None
) -> FetchResult:
    """Ambil laporan cedera resmi untuk satu tanggal.

    date: "YYYY-MM-DD" (tanggal Eastern) atau None = hari ini (Eastern).
    Alur: halaman resmi -> tautan PDF terbaru hari itu; bila halaman
    gagal/tidak ada tautan, coba file 12:00 AM. data: list cedera
    {player, team, status, detail}. Fetch/parse gagal -> ok=False
    dengan error jujur (tidak melempar).
    """
    fetched_at = now_iso()
    if date is None:
        date = datetime.now(UTC).astimezone(EASTERN).strftime("%Y-%m-%d")
    else:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except (ValueError, TypeError):
            return FetchResult(
                SOURCE, TIER, fetched_at, False, error=f"tanggal_tidak_valid: {date!r}"
            )
    http_client = client or _default_client()
    # Teks PDF hasil parse di-cache di cache yang sama dengan client
    # (kunci = URL PDF, nilai = {"text": ...}).
    cache = http_client.cache
    if cache is None:
        cache = DiskCache(default_cache_dir(), CACHE_TTL_SECONDS)
    limiter = _LIMITER

    pdf_url: str | None = None
    page_error: str | None = None
    resp = http_client.get(REPORT_PAGE_URL)
    if resp.get("status") == 200 and isinstance(resp.get("body"), str):
        pdf_url = _latest_pdf_link(resp["body"], date)
        if pdf_url is None:
            page_error = "tidak ada tautan PDF untuk tanggal itu di halaman resmi"
    else:
        page_error = f"halaman laporan http_{resp.get('status')}: {resp.get('error')}"
    if pdf_url is None:
        pdf_url = _fallback_pdf_url(date)

    cached = cache.get(pdf_url)
    text: str | None = None
    from_cache = False
    if isinstance(cached, dict) and isinstance(cached.get("text"), str):
        text = cached["text"]
        from_cache = True
    else:
        status, pdf_bytes, error = _download_pdf_bytes(pdf_url, limiter)
        if pdf_bytes is None:
            return FetchResult(
                SOURCE,
                TIER,
                fetched_at,
                False,
                error=f"pdf_http_{status}: {error}",
                extra={"pdf_url": pdf_url, "page_error": page_error},
            )
        try:
            text = parse_pdf_text(pdf_bytes)
        except ValueError as exc:
            return FetchResult(
                SOURCE,
                TIER,
                fetched_at,
                False,
                error=str(exc),
                extra={"pdf_url": pdf_url, "page_error": page_error},
            )
        cache.set(pdf_url, {"text": text})
    injuries = parse_injuries(text)
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=injuries,
        extra={
            "pdf_url": pdf_url,
            "report_date": date,
            "from_cache": from_cache,
            "n_injuries": len(injuries),
            "page_error": page_error,
        },
    )
