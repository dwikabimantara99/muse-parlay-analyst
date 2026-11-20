"""Helper bersama untuk probe Tahap 2a (STDLIB SAJA).

Berisi: HttpClient (User-Agent jelas, timeout 30 dtk), RateLimiter per host,
DiskCache JSON di probes/out/, load_dotenv (HANYA untuk JUPITER_API_KEY),
dan JupiterClient (mode keyed 1 RPS dengan fallback keyless 0,5 RPS).

KEAMANAN: nilai API key TIDAK PERNAH di-print, di-log, atau disimpan ke file
apa pun. Evidence respons tidak pernah memuat header Authorization/x-api-key.
JupiterClient HANYA memanggil endpoint baca GET; endpoint yang memindahkan
dana (POST /orders, DELETE /positions, /claim) DILARANG KERAS.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

USER_AGENT = "muse-parlay-analyst probe/2a"
DEFAULT_TIMEOUT = 30

# Header respons yang tidak boleh disimpan (berpotensi memuat kredensial).
_SENSITIVE_HEADER_RE = re.compile(r"authorization|api[-_]?key|cookie", re.I)

# Endpoint baca Jupiter yang diizinkan (DECISIONS.md K3). Selain ini ditolak.
_JUPITER_BASE = "https://api.jup.ag/prediction/v1"
_JUPITER_ALLOWED_RE = re.compile(
    r"^/(events|events/search|events/[^/]+|markets/[^/]+)$"
)


def now_iso() -> str:
    """Jam sekarang dalam ISO 8601 UTC."""
    return datetime.now(UTC).isoformat()


def load_dotenv(repo_root: str | Path) -> dict[str, str]:
    """Baca file .env (format KEY=VALUE, abaikan komentar dan baris kosong).

    Dipakai HANYA untuk JUPITER_API_KEY. Nilai yang dikembalikan tidak boleh
    di-print, di-log, atau ditulis ke file.
    """
    values: dict[str, str] = {}
    env_path = Path(repo_root) / ".env"
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


class RateLimiter:
    """Jeda minimum antar request, per host."""

    def __init__(
        self,
        min_gap_seconds: float,
        time_fn: object = None,
        sleep_fn: object = None,
    ) -> None:
        """min_gap_seconds: jeda minimum antar request ke host yang sama.

        time_fn/sleep_fn bisa di-inject untuk tes (default: time.monotonic
        dan time.sleep).
        """
        self.min_gap_seconds = min_gap_seconds
        self._time = time_fn if time_fn is not None else time.monotonic
        self._sleep = sleep_fn if sleep_fn is not None else time.sleep
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> float:
        """Tidur seperlunya agar jeda sejak request terakhir ke host terpenuhi.

        Mengembalikan jumlah detik yang ditidurkan (0 bila tidak perlu).
        """
        last = self._last.get(host)
        slept = 0.0
        if last is not None:
            elapsed = self._time() - last
            remaining = self.min_gap_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                slept = remaining
        self._last[host] = self._time()
        return slept


class DiskCache:
    """Cache JSON di disk dengan TTL; kunci = hash SHA-256 dari URL."""

    def __init__(self, cache_dir: str | Path, ttl_seconds: float) -> None:
        """cache_dir: direktori penyimpanan; ttl_seconds: umur maksimum entri."""
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key_for(url: str) -> str:
        """Kunci cache untuk sebuah URL (hash, bukan URL mentah)."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, url: str) -> dict | None:
        """Ambil entri cache untuk URL, atau None bila tidak ada/kedaluwarsa."""
        path = self._path(self.key_for(url))
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        saved_at = payload.get("saved_at", 0)
        if time.time() - float(saved_at) > self.ttl_seconds:
            return None
        return payload.get("value")

    def set(self, url: str, value: dict) -> None:
        """Simpan entri cache untuk URL."""
        payload = {"saved_at": time.time(), "value": value}
        self._path(self.key_for(url)).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )


def _safe_headers(headers: object) -> dict[str, str]:
    """Salin header respons, buang header yang berpotensi sensitif."""
    safe: dict[str, str] = {}
    for key, value in dict(headers).items():
        if _SENSITIVE_HEADER_RE.search(key):
            continue
        safe[key] = value
    return safe


def rate_limit_headers(headers: dict[str, str]) -> dict[str, str]:
    """Ambil header terkait rate limit dari header respons (bila ada)."""
    wanted = (
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "retry-after",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
    )
    return {k: v for k, v in headers.items() if k.lower() in wanted}


class HttpClient:
    """Client HTTP GET dengan User-Agent jelas, timeout, dan rate limit."""

    def __init__(
        self,
        rate_limiter: RateLimiter,
        cache: DiskCache | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """rate_limiter: pembatas jeda per host. cache: opsional DiskCache.

        extra_headers: header tambahan per request (JANGAN berisi kredensial
        — kredensial hanya dipakai JupiterClient, dan tidak pernah disimpan).
        """
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    def get(self, url: str, use_cache: bool = True) -> dict[str, object]:
        """GET satu URL. Mengembalikan dict status/headers/body/error.

        Selalu mengembalikan dict (tidak melempar) agar probe mencatat error
        apa adanya. Body disimpan UTUH agar JSON besar tetap bisa di-parse;
        pemotongan hanya dilakukan di ringkasan evidence tiap probe.
        """
        if use_cache and self.cache is not None:
            cached = self.cache.get(url)
            if cached is not None:
                return {**cached, "from_cache": True}
        host = urllib.parse.urlparse(url).netloc
        self.rate_limiter.wait(host)
        headers = {"User-Agent": USER_AGENT, **self.extra_headers}
        request = urllib.request.Request(url, headers=headers, method="GET")
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read()
                status = resp.status
                resp_headers = _safe_headers(resp.headers)
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except OSError:
                raw = b""
            status = exc.code
            resp_headers = _safe_headers(exc.headers)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "url": url,
                "status": None,
                "headers": {},
                "rate_limit_headers": {},
                "body": "",
                "truncated": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "from_cache": False,
            }
        text = raw.decode("utf-8", errors="replace")
        result: dict[str, object] = {
            "url": url,
            "status": status,
            "headers": resp_headers,
            "rate_limit_headers": rate_limit_headers(resp_headers),
            "body": text,
            "truncated": False,
            "error": None,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "from_cache": False,
        }
        if use_cache and self.cache is not None and status == 200:
            self.cache.set(url, result)
        return result


class JupiterClient:
    """Client baca Jupiter Prediction API (mode keyed + fallback keyless).

    Mode keyed: header x-api-key, jeda minimum 1,1 dtk (aman di bawah 1 RPS).
    Bila respons 401/403, fallback SEKALI ke keyless (tanpa header, jeda
    minimum 2,2 dtk = aman di bawah 0,5 RPS) dan catat mode yang dipakai.
    HANYA endpoint GET baca; yang lain ditolak ValueError.
    """

    def __init__(
        self,
        api_key: str | None,
        cache: DiskCache | None = None,
    ) -> None:
        """api_key: nilai JUPITER_API_KEY dari .env (atau None = keyless)."""
        self.api_key = api_key
        self.cache = cache
        self._keyed_limiter = RateLimiter(1.1)
        self._keyless_limiter = RateLimiter(2.2)
        self.mode_used: str | None = None
        self.fallback_used = False

    def _request(
        self, url: str, keyed: bool, params: dict[str, str] | None
    ) -> dict[str, object]:
        limiter = self._keyed_limiter if keyed else self._keyless_limiter
        headers = {"User-Agent": USER_AGENT}
        if keyed and self.api_key:
            headers["x-api-key"] = self.api_key
        # Cache keyed dan keyless dipisah: URL keyed tidak boleh dipakai
        # ulang tanpa key (dan sebaliknya) agar mode tercatat jujur.
        cache_url = url + ("#keyed" if keyed else "#keyless")
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"
            cache_url = f"{cache_url}?{query}"
        if self.cache is not None:
            cached = self.cache.get(cache_url)
            if cached is not None:
                return {**cached, "from_cache": True}
        host = urllib.parse.urlparse(url).netloc
        limiter.wait(host)
        request = urllib.request.Request(url, headers=headers, method="GET")
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as resp:
                raw = resp.read()
                status = resp.status
                resp_headers = _safe_headers(resp.headers)
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except OSError:
                raw = b""
            status = exc.code
            resp_headers = _safe_headers(exc.headers)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "url": url,
                "status": None,
                "headers": {},
                "rate_limit_headers": {},
                "body": "",
                "truncated": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "from_cache": False,
            }
        text = raw.decode("utf-8", errors="replace")
        result: dict[str, object] = {
            "url": url,
            "status": status,
            "headers": resp_headers,
            "rate_limit_headers": rate_limit_headers(resp_headers),
            "body": text,
            "truncated": False,
            "error": None,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "from_cache": False,
        }
        if self.cache is not None and status == 200:
            self.cache.set(cache_url, result)
        return result

    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, object]:
        """GET satu path Jupiter yang diizinkan.

        Mengembalikan dict hasil HttpClient ditambah 'mode' ('keyed' /
        'keyless') dan 'fallback' (True bila key ditolak lalu keyless).
        """
        if not _JUPITER_ALLOWED_RE.match(path):
            raise ValueError(
                f"path Jupiter tidak diizinkan (hanya endpoint baca): {path}"
            )
        url = _JUPITER_BASE + path
        if self.api_key:
            result = self._request(url, keyed=True, params=params)
            if result["status"] in (401, 403):
                self.fallback_used = True
                result = self._request(url, keyed=False, params=params)
                result["mode"] = "keyless"
                self.mode_used = "keyless"
                return result
            result["mode"] = "keyed"
            self.mode_used = "keyed"
            return result
        result = self._request(url, keyed=False, params=params)
        result["mode"] = "keyless"
        self.mode_used = "keyless"
        return result


def repo_root() -> Path:
    """Root repo (induk direktori probes/)."""
    return Path(__file__).resolve().parent.parent


def out_dir() -> Path:
    """Direktori output probe (probes/out/), dibuat bila belum ada."""
    path = Path(__file__).resolve().parent / "out"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_result(source: str, tier: int) -> dict[str, object]:
    """Kerangka hasil probe standar untuk satu sumber."""
    return {
        "source": source,
        "tier": tier,
        "probed_at": now_iso(),
        "accessible_from_vm": None,
        "format": None,
        "rate_limit": None,
        "data_available": [],
        "risk_notes": [],
        "requests": [],
        "verdict": None,
        "unknown": [],
    }


def write_result(name: str, result: dict) -> Path:
    """Tulis hasil probe ke probes/out/<name>.json. Mengembalikan path-nya."""
    path = out_dir() / f"{name}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_json_body(result: dict[str, object]) -> dict | list | None:
    """Parse body JSON dari hasil request; None bila gagal/bukan JSON."""
    body = result.get("body")
    if not isinstance(body, str) or not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None
