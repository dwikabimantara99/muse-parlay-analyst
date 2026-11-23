"""Cek ulang pra-submit tiket parlay NBA (Tahap 3 Langkah 2).

Tiket parlay yang sudah di-submit TIDAK BISA dibatalkan — karena itu
modul ini memeriksa ulang artefak analisis NBA sesaat sebelum user
submit, dan memberi putusan GO / NO_GO. Modul ini mengonsumsi artefak
``nba_analysis`` format_version 1 (kontrak bersama dengan pekerja W1,
yang membangun artefak itu) dan TIDAK mengubah artefak tersebut.

ALUR: fetch_fresh() mengambil data segar (input otak + tangga
Polymarket + moneyline jup.ag + berita NBA) -> compare_injuries() /
compare_prices() / compare_news() membandingkan dengan analisis awal
-> needs_resim() memutuskan perlu hitung ulang -> decide() memberi
putusan per kaki dan per tiket.

BERITA MENDADAK (modul news, kasus Thunder): berita yang terbit
SETELAH analisis awal DAN relevan dengan laga ini (fetcher sudah
menyaring per tim) ditandai sebagai berita baru. Definisinya
eksplisit di compare_news():
  - MENDADAK: jam terbit artikel > analysis.generated_at (artikel
    tanpa jam terbit TIDAK PERNAH dihitung mendadak — tidak bisa
    dibuktikan terbit setelah analisis).
  - RELEVAN: artikel ada di feed berita laga ini (fetcher
    news_nba sudah menyaring per tim) DAN belum ada di blok news
    analisis awal (dedup per id/url/judul).
  Berita baru TIDAK memicu hitung ulang (news adalah konteks,
  bukan angka) dan TIDAK mengubah GO menjadi NO_GO — tapi membuat
  semua kaki laga itu PERHATIAN (user wajib membaca daftar
  perhatian) + satu entri changes kind "news". Alasannya: kasus
  Thunder (harga 75¢ -> 71¢ satu jam sebelum tip-off karena news
  yang tidak diketahui user) — recheck yang menemukan berita baru
  harus menandainya sebelum user submit.

AMBANG — SEMUA dari config/playstyle.yaml, dibaca lewat
config.get_value (fail-closed: kunci hilang -> ConfigError, tidak
ada default diam-diam):
  - anomaly.sharp_move_cents (3): gerakan harga >= ambang = ANOMALI.
  - recheck.market_line_move_points (2.0): garis market bergerak >
    ambang -> hitung ulang.
  - data.stale_hours_injury_lineup (3): data cedera lebih tua dari
    ini = basi.
  - calibration.lean_to_market_gap (5.0 — v18, dipindahkan dari
    market_line_check.total_gap_points): pemicu aturan
    condong-ke-market (lihat bawah).
  - filters.nba_alt_under.insurance_target_probability (0.74):
    probabilitas minimum kaki Asuransi.
  - blend.w_model: bobot blend p_final saat hitung ulang.

ATURAN PUTUSAN (per kaki, prioritas tertinggi dulu):
  1. Analisis awal berstatus DATA_INCOMPLETE -> DATA_INCOMPLETE.
     Analisis awal berstatus HOLD -> JANGAN_PASANG (belum siap).
  2. Tangga segar gagal diambil -> DATA_INCOMPLETE (harga dipakai
     semua kaki; tanpa harga segar tidak ada yang bisa diputuskan).
  3. Data cedera analisis awal BASI (> 3 jam) dan fetch segar gagal
     -> DATA_INCOMPLETE. Bila data cedera masih segar (<= 3 jam)
     dan fetch gagal, kaki tetap bisa diputuskan dari harga (data
     lama masih dalam jendela validitasnya) + dicatat sebagai
     perubahan fetch_error. Umur yang tidak bisa dihitung (jam
     hilang/rusak) dianggap BASI (fail-closed).
  4. Kaki awal tidak memenuhi syarat (meets False) -> JANGAN_PASANG.
  5. Garis kaki hilang dari tangga segar -> JANGAN_PASANG.
  6. Gerakan harga >= 3¢ (anomali sharp move, aturan Thunder) ->
     JANGAN_PASANG (lebih keras dari PERHATIAN) + framing "sharp
     move BUKAN diskon" (keputusan user 2026-11-23 09:47 WIB):
     label harga ditekan — EV yang akan berlabel DISKON menjadi
     DISKON_DITEKAN (dicatat di entri anomali ``price_label`` dan
     di kaki resim bila ada) — dan "Kenapa beda?" wajib
     (``kenapa_beda_required: True`` pada entri anomali) sampai
     pergerakannya dijelaskan. "Kenapa beda?" sharp move ini
     sengaja TIDAK memakai dict ``kenapa_beda`` per kaki (itu
     mekanisme selisih median-vs-garis market yang menggerakkan
     aturan condong-ke-market; memakainya untuk sharp move akan
     salah mengaktifkan aturan itu) — melainkan pola yang sama
     seperti anomaly.py: flag ``kenapa_beda_required`` pada dict
     anomali.
  7. Hitung ulang dibutuhkan tapi GAGAL -> DATA_INCOMPLETE untuk
     kaki yang belum diputus keras (sesuatu yang material berubah
     tapi tidak bisa dihitung ulang). Kaki yang sudah JANGAN_PASANG
     tetap JANGAN_PASANG.
  8. Hitung ulang selesai tapi garis baru tidak meets -> JANGAN_PASANG.
  9. Hitung ulang selesai dan garis BERUBAH -> JANGAN_PASANG untuk
     garis LAMA (rencana awal sudah tidak berlaku) + action_required
     "ganti garis ke {garis baru}". Tiket NO_GO berarti "jangan
     submit SESUAI RENCANA AWAL" — user analisis ulang / pakai
     garis baru.
  10. Aturan condong-ke-market (kaki Asuransi saja, lihat bawah).
  11. PERHATIAN (tetap GO, tapi user WAJIB membaca daftar perhatian):
      harga bergerak 1-2¢; garis market bergerak > 0 s.d. 2 poin;
      hitung ulang selesai tapi garis tetap; konflik cedera baru
      yang tidak mengubah status OUT; perubahan status ringan;
      pemain kembali dari cedera; probabilitas market dipakai
      (aturan condong-ke-market, lolos ambang); berita baru yang
      mendadak + relevan dengan laga ini (modul news).
  12. Selain itu -> TETAP_OK.

PUTUSAN TIKET: NO_GO bila ada kaki JANGAN_PASANG atau
DATA_INCOMPLETE, atau bila tidak ada kaki sama sekali. GO bila
semua kaki TETAP_OK atau PERHATIAN.

HITUNG ULANG (needs_resim True) bila salah satu terjadi:
  - ada pemain baru OUT/DOUBTFUL sejak analyze (termasuk status
    yang memburuk menjadi OUT/DOUBTFUL — kondisi "status berubah
    ke OUT/DOUBTFUL" tercakup di sini);
  - |pergerakan garis market| > 2.0 poin (tepat 2.0 TIDAK memicu);
  - ada gerakan harga >= 3¢.
  Pemain yang KEMBALI dari cedera (resolved) TIDAK memicu hitung
  ulang (di luar daftar pemicu yang disepakati) — tapi dicatat di
  changes + menjadi alasan PERHATIAN. Garis yang hilang dari tangga
  juga TIDAK memicu hitung ulang — langsung JANGAN_PASANG.

ATURAN CONDONG-KE-MARKET (keputusan user 2026-11-22, addendum
Langkah 2; HANYA untuk kaki Asuransi, kaki Utama tetap memakai
probabilitas model):
  - PEMICU: |median model - garis market| > 5.0 poin. Median dari
    sim SEGAR bila resim terjadi, else sim analisis awal. Garis
    market dari garis utama tangga SEGAR. Bila salah satunya tidak
    ada, pemicu tidak aktif (tidak bisa dihitung -> tidak ada
    putusan dari aturan ini; aturan fail-closed lain tetap jalan).
  - Bila pemicu aktif, jalankan "Kenapa beda?" mekanis. Alasan
    konkret yang diakui (hanya ini yang bisa dihitung dari data
    yang ada — JANGAN mengarang alasan dari data yang tidak ada):
      (a) Cedera terkonfirmasi yang belum dihargai market: ada
          pemain baru OUT/DOUBTFUL sejak analyze, DAN garis market
          tidak bergerak searah perubahan median model (atau
          bergerak < 1 poin). Bila tidak ada sim segar (median
          tidak berubah/ tidak diketahui), klausul "< 1 poin"
          yang dipakai. Bila pergerakan garis market tidak
          diketahui, alasan (a) TIDAK bisa ditegakkan (lebih aman
          memakai probabilitas market).
    Bila tidak ada alasan konkret -> "tidak ditemukan alasan".
  - Bila pemicu aktif DAN tidak ada alasan konkret: probabilitas
    kaki untuk keputusan Asuransi memakai probabilitas tersirat
    MARKET (price_cents sisi Under garis itu dari tangga SEGAR /
    100; bila price_cents tidak ada, mid_cents; bila keduanya
    tidak ada -> kaki DATA_INCOMPLETE). Bila probabilitas market
    < 0.74 -> kaki TIDAK memenuhi syarat Asuransi -> JANGAN_PASANG.
    Bila >= 0.74 -> kaki lolos syarat peluang (tetap dinilai
    aturan lain seperti biasa) + dicatat sebagai PERHATIAN karena
    basis probabilitasnya berubah.
  - Bila alasan konkret ditemukan: probabilitas model BOLEH dipakai,
    dengan alasan tercatat di laporan (kenapa_beda.reason).
  - Setiap kaki di laporan membawa probability_used ("model" /
    "market"), probability_value, dan kenapa_beda {gap_points,
    triggered, reason_found, reason}.

BASIS HARGA (compare_prices): harga yang dibandingkan adalah harga
VENUE yang dibayar user — jup_estimated_cents bila tersedia, else
price_cents — di kedua sisi (lama dan baru). Baseline harga lama
adalah snapshot PERTAMA di analysis.price_snapshots bila ada (aturan
Thunder: gerak diukur dari pengambilan pertama), else harga kaki di
analisis. ASUMSI yang didokumentasikan: "cents" di snapshot berada
di basis yang sama dengan harga efektif kaki (estimasi jup.ag bila
tersedia). Bila W1 menyimpan snapshot di basis price_cents mentah,
gerak semu maksimal sebesar markup tipikal (0,5¢) bisa muncul —
di bawah semua ambang putusan (1¢ / 3¢), jadi tidak mengubah
putusan apa pun. PENGECUALIAN: probabilitas tersirat market untuk
aturan condong-ke-market memakai price_cents mentah (bukan estimasi
jup.ag), sesuai bunyi keputusan user.

GARIS MARKET UTAMA SEGAR: garis total dengan volume_usd terbesar
di tangga segar (garis paling likuid = garis utama); seri -> garis
terkecil. Bila tidak ada volume yang terbaca -> None.

FAIL-CLOSED LAINNYA: fetch segar yang gagal tidak melempar —
errors terisi + data None. Moneyline jup.ag TIDAK bisa diambil
dengan wajar (ingest/jupiter.py hanya punya pemindaian penuh,
tanpa fetcher per-event) -> dicatat di errors + moneyline_jup
None, dan TIDAK menggagalkan recheck (kaki Alt Under tidak
memakainya; error ini juga tidak masuk missing/changes laporan).
ConfigError (ambang hilang) DIBIARKAN naik — config rusak bukan
kegagalan data. decide() memvalidasi laporannya sendiri terhadap
schemas/recheck.schema.json dan melempar ValueError bila laporan
yang dihasilkannya tidak valid (itu bug kode, bukan data).
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from datetime import UTC, datetime

import config
from engine import cushion, nba_sim, price_labels

# Default sementara harga minimum kaki Tahap 4 (sen) sampai kunci
# analis.harga_min_utama_cents / analis.harga_min_asuransi_cents ada di
# playstyle.yaml — nilai kontrak bersama (75¢), BUKAN karangan. Pola
# yang sama dengan DEFAULT_HARGA_MIN_CENTS di engine/nba_analysis.py.
_DEFAULT_HARGA_MIN_CENTS = 75.0

# Status cedera yang dihitung dalam perbandingan (normalisasi huruf besar).
STATUS_DIHITUNG = ("OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE")
# Status yang dianggap "material": memicu hitung ulang.
STATUS_MATERIAL = ("OUT", "DOUBTFUL")

SCHEMA_PATH = config.REPO_ROOT / "schemas" / "recheck.schema.json"

# Gerakan harga di bawah ini dianggap stabil (bukan PERHATIAN).
# Gerakan 1-2¢ -> PERHATIAN; >= ambang sharp (3¢) -> anomali.
_GERAK_MIN_PERHATIAN_CENTS = 1.0
# Klausul "< 1 poin" pada alasan konkret (a) aturan condong-ke-market.
_GERAK_MARKET_MIN_DIHARGAI_POINTS = 1.0


def _sekarang_iso() -> str:
    """Jam sekarang dalam ISO 8601 UTC."""
    return datetime.now(UTC).isoformat()


def _muat_cfg(cfg: dict | None) -> dict:
    """Pakai cfg yang diberikan, else baca playstyle.yaml."""
    return cfg if cfg is not None else config.load_playstyle()


def _ambang(cfg: dict, *kunci: str) -> float:
    """Baca satu ambang dari config; ConfigError bila kunci hilang.

    Nilai harus angka hingga >= 0, else ValueError. TIDAK ada default
    diam-diam — kunci hilang berarti config rusak.
    """
    nilai = config.get_value(cfg, *kunci)
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or nilai < 0
    ):
        raise ValueError(
            f"ambang config {'.'.join(kunci)} tidak valid: {nilai!r} "
            "(harus angka hingga >= 0)"
        )
    return float(nilai)


def _parse_iso(teks) -> datetime | None:
    """Parse ISO 8601 menjadi datetime aware; None bila tidak sah.

    Akhiran "Z" diterima (= UTC). Jam tanpa zona waktu dianggap UTC
    (repo memakai UTC di mana-mana).
    """
    if not isinstance(teks, str) or not teks.strip():
        return None
    try:
        hasil = datetime.fromisoformat(teks.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if hasil.tzinfo is None:
        hasil = hasil.replace(tzinfo=UTC)
    return hasil


def _angka(nilai) -> float | None:
    """Angka hingga sebagai float, atau None bila bukan angka."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    if not math.isfinite(nilai):
        return None
    return float(nilai)


def _format_garis(garis) -> str:
    """Garis total untuk pesan (format :g, titik desimal)."""
    angka = _angka(garis)
    return f"{angka:g}" if angka is not None else "tidak_diketahui"


def _normalisasi_nama(nama) -> str:
    """Normalisasi nama pemain: lowercase + rapikan spasi."""
    if not isinstance(nama, str):
        return ""
    return re.sub(r"\s+", " ", nama.lower()).strip()


def _normalisasi_status(status) -> str | None:
    """Normalisasi status cedera: huruf besar + rapikan spasi."""
    if not isinstance(status, str) or not status.strip():
        return None
    return re.sub(r"\s+", " ", status.strip().upper())


def _peta_cedera(entri) -> dict[str, dict]:
    """Peta nama ternormalisasi -> {"player", "status"}.

    Entri tanpa nama pemain yang bisa dipakai dilewati. Bila satu
    nama muncul dua kali, kemunculan pertama yang dipakai.
    """
    peta: dict[str, dict] = {}
    if not isinstance(entri, (list, tuple)):
        return peta
    for item in entri:
        if not isinstance(item, dict):
            continue
        nama_norm = _normalisasi_nama(item.get("player"))
        if not nama_norm or nama_norm in peta:
            continue
        peta[nama_norm] = {
            "player": item.get("player"),
            "status": _normalisasi_status(item.get("status")),
        }
    return peta


def _harga_efektif(entri: dict) -> float | None:
    """Harga venue efektif (¢): jup_estimated_cents bila ada, else price_cents."""
    if not isinstance(entri, dict):
        return None
    harga = _angka(entri.get("jup_estimated_cents"))
    if harga is None:
        harga = _angka(entri.get("price_cents"))
    return harga


def entri_cedera_dari_inputs(inputs: dict | None) -> list[dict]:
    """Daftar cedera gabungan dari blok home/away hasil fetch_match_inputs.

    Mengembalikan list entri {"player", "status", ...} apa adanya
    (urut home lalu away). inputs None/bukan dict -> list kosong.
    """
    if not isinstance(inputs, dict):
        return []
    hasil: list[dict] = []
    for blok in (inputs.get("home"), inputs.get("away")):
        if not isinstance(blok, dict):
            continue
        for item in blok.get("injuries") or []:
            if isinstance(item, dict):
                hasil.append(item)
    return hasil


def _entri_cedera_analisis(analysis: dict) -> list[dict]:
    """Daftar cedera analisis awal: injuries.entries, fallback ke inputs."""
    cedera = analysis.get("injuries")
    if isinstance(cedera, dict) and isinstance(cedera.get("entries"), list):
        return [e for e in cedera["entries"] if isinstance(e, dict)]
    return entri_cedera_dari_inputs(analysis.get("inputs"))


def garis_utama_dari_tangga(totals) -> float | None:
    """Garis total utama dari tangga: garis bervolume_usd terbesar.

    Seri -> garis terkecil. Entri tanpa garis dilewati; entri tanpa
    volume tidak bisa menjadi garis utama. Bila tidak ada volume
    yang terbaca -> None (garis utama tidak diketahui).
    """
    if not isinstance(totals, (list, tuple)):
        return None
    terbaik: tuple[float, float] | None = None  # (volume, garis)
    for entri in totals:
        if not isinstance(entri, dict):
            continue
        garis = _angka(entri.get("line"))
        volume = _angka(entri.get("volume_usd"))
        if garis is None or volume is None:
            continue
        if (
            terbaik is None
            or volume > terbaik[0]
            or (volume == terbaik[0] and garis < terbaik[1])
        ):
            terbaik = (volume, garis)
    return terbaik[1] if terbaik is not None else None


def spread_abs_dari_tangga(spreads) -> float | None:
    """Spread absolut laga dari tangga spread segar.

    Aturan yang sama seperti W1 di engine/nba_analysis.py: nilai
    absolut garis spread bervolume_usd terbesar; seri -> entri
    pertama. None bila tidak ada entri spread yang membawa garis +
    volume. (Tidak lagi dipakai hitung ulang sejak bantalan adaptif
    menggantikan aturan spread — dipertahankan sebagai helper +
    untuk tes.)
    """
    if not isinstance(spreads, (list, tuple)):
        return None
    terbaik: tuple[float, float] | None = None  # (volume, garis)
    for entri in spreads:
        if not isinstance(entri, dict):
            continue
        garis = _angka(entri.get("line"))
        volume = _angka(entri.get("volume_usd"))
        if garis is None or volume is None:
            continue
        if terbaik is None or volume > terbaik[0]:
            terbaik = (volume, garis)
    return abs(terbaik[1]) if terbaik is not None else None


def _tangga_under(totals) -> list[dict]:
    """Entri sisi Under dari tangga totals (list dict)."""
    if not isinstance(totals, (list, tuple)):
        return []
    return [
        entri
        for entri in totals
        if isinstance(entri, dict) and entri.get("side") == "under"
    ]


def _peta_harga_under(totals) -> dict[float, dict]:
    """Peta garis -> entri Under (kemunculan pertama per garis)."""
    peta: dict[float, dict] = {}
    for entri in _tangga_under(totals):
        garis = _angka(entri.get("line"))
        if garis is not None and garis not in peta:
            peta[garis] = entri
    return peta


def _unpack_fetch(hasil):
    """Urai hasil fetcher menjadi (data, pesan_error).

    Menerima FetchResult (duck-typing: atribut ok/data/error), dict
    mentah (dianggap sukses), atau None. Tipe lain -> error.
    """
    if hasil is None:
        return None, "fetcher mengembalikan None"
    if hasattr(hasil, "ok") and hasattr(hasil, "data"):
        if hasil.ok:
            return hasil.data, None
        return None, str(getattr(hasil, "error", None) or "fetch gagal")
    if isinstance(hasil, dict):
        return hasil, None
    return None, f"tipe hasil fetch tidak dikenal: {type(hasil).__name__}"


def _fetch_inputs_default(analysis: dict, client=None):
    """Fetcher inputs default: ingest.nba_brain.fetch_match_inputs."""
    from ingest import nba_brain

    return nba_brain.fetch_match_inputs(
        (analysis.get("home_tricode") or ""),
        (analysis.get("away_tricode") or ""),
        (analysis.get("game_date") or ""),
        client=client,
    )


def _fetch_ladder_default(analysis: dict, client=None):
    """Fetcher tangga default: event Gamma via slug di market.slug."""
    from ingest import polymarket

    market = analysis.get("market") or {}
    slug = market.get("slug") if isinstance(market, dict) else None
    return polymarket.fetch_event_by_slug(slug or "", client=client)


def _fetch_news_default(analysis: dict, client=None):
    """Fetcher berita default: ingest.news_nba.fetch_news_nba."""
    from ingest import news_nba

    return news_nba.fetch_news_nba(
        (analysis.get("home_tricode") or ""),
        (analysis.get("away_tricode") or ""),
        (analysis.get("game_date") or ""),
        client=client,
    )


def fetch_fresh(
    analysis: dict,
    cfg: dict | None = None,
    client=None,
    fetch_inputs=None,
    fetch_ladder=None,
    fetch_jup_ml=None,
    fetch_news=None,
) -> dict:
    """Ambil data segar untuk cek ulang.

    analysis: artefak nba_analysis. cfg: dict playstyle (None = baca
    playstyle.yaml). client: HttpClient bersama (diteruskan ke
    fetcher default). fetch_inputs / fetch_ladder / fetch_jup_ml /
    fetch_news: fetcher injeksi untuk tes, masing-masing
    callable(analysis, client) yang mengembalikan FetchResult atau
    dict mentah:
      - fetch_inputs -> FetchResult berisi dict fetch_match_inputs.
      - fetch_ladder -> FetchResult berisi dict event Gamma (lalu
        di-parse dengan parse_event_ladders) ATAU dict tangga yang
        sudah ter-parse (mengandung kunci "totals").
      - fetch_jup_ml -> dict {"home_cents", "away_cents",
        "fetched_at"} atau FetchResult berisi dict itu.
      - fetch_news -> FetchResult berisi list artikel news_nba
        ATAU list artikel mentah.
    Default fetch_inputs = ingest.nba_brain.fetch_match_inputs;
    default fetch_ladder = ingest.polymarket.fetch_event_by_slug +
    parse_event_ladders; default fetch_news =
    ingest.news_nba.fetch_news_nba. Default fetch_jup_ml = TIDAK ADA
    fetcher (repo tidak punya fetcher moneyline jup.ag per-event;
    hanya pemindaian penuh di ingest/jupiter.py) -> moneyline_jup
    None + errors terisi, dan itu TIDAK menggagalkan recheck.

    Mengembalikan {"inputs", "ladders", "moneyline_jup", "news",
    "fetched_at", "errors": {kunci: pesan}}. Fetch yang gagal
    mengisi errors + data None — TIDAK melempar — kecuali
    ConfigError (ambang config hilang) yang dibiarkan naik.
    Melempar ValueError bila analysis bukan dict.
    """
    if not isinstance(analysis, dict):
        raise ValueError(f"analysis harus dict, didapat {type(analysis).__name__}")
    cfg = _muat_cfg(cfg)
    errors: dict[str, str] = {}
    inputs = None
    ladders = None
    moneyline_jup = None
    news = None

    try:
        fetcher = fetch_inputs or _fetch_inputs_default
        inputs, err = _unpack_fetch(fetcher(analysis, client))
        if err is not None:
            errors["inputs"] = err
    except config.ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — fetch gagal = errors, bukan exception
        errors["inputs"] = f"{type(exc).__name__}: {exc}"
        inputs = None

    try:
        fetcher = fetch_ladder or _fetch_ladder_default
        hasil = fetcher(analysis, client)
        if isinstance(hasil, dict) and "totals" in hasil:
            ladders = hasil
        else:
            event, err = _unpack_fetch(hasil)
            if err is not None:
                errors["ladders"] = err
            elif not isinstance(event, dict):
                errors["ladders"] = "event Gamma kosong/bukan dict"
            else:
                from ingest import polymarket

                ladders = polymarket.parse_event_ladders(event, cfg=cfg)
    except config.ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — fetch gagal = errors, bukan exception
        errors["ladders"] = f"{type(exc).__name__}: {exc}"
        ladders = None

    if fetch_jup_ml is None:
        errors["moneyline_jup"] = (
            "tidak ada fetcher moneyline jup.ag per-event di repo "
            "(ingest/jupiter.py hanya pemindaian penuh); moneyline "
            "tidak dipakai kaki Alt Under"
        )
    else:
        try:
            moneyline_jup, err = _unpack_fetch(fetch_jup_ml(analysis, client))
            if err is not None:
                errors["moneyline_jup"] = err
        except config.ConfigError:
            raise
        except Exception as exc:  # noqa: BLE001 — fetch gagal = errors
            errors["moneyline_jup"] = f"{type(exc).__name__}: {exc}"
            moneyline_jup = None

    # Berita segar (modul news): gagal -> errors["news"] saja, tidak
    # menggagalkan recheck (berita adalah konteks, bukan angka).
    try:
        fetcher_news = fetch_news or _fetch_news_default
        hasil_news = fetcher_news(analysis, client)
        if isinstance(hasil_news, list):
            news = hasil_news
        else:
            news, err = _unpack_fetch(hasil_news)
            if err is not None:
                errors["news"] = err
            elif news is not None and not isinstance(news, list):
                errors["news"] = f"hasil fetch berita bukan list: {type(news).__name__}"
                news = None
    except config.ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — fetch gagal = errors, bukan exception
        errors["news"] = f"{type(exc).__name__}: {exc}"
        news = None

    return {
        "inputs": inputs,
        "ladders": ladders,
        "moneyline_jup": moneyline_jup,
        "news": news,
        "fetched_at": _sekarang_iso(),
        "errors": errors,
    }


def compare_injuries(old_entries, new_entries) -> dict:
    """Bandingkan daftar cedera lama vs baru, per pemain.

    Nama dinormalisasi (lowercase + rapikan spasi); status
    dinormalisasi (huruf besar). Mengembalikan:
      {"new_out": [nama pemain],           # baru OUT/DOUBTFUL
       "status_changed": [{"player", "old", "new"}],
       "resolved": [nama pemain]}          # hilang dari daftar baru
    new_out = pemain yang di daftar baru berstatus OUT/DOUBTFUL
    padahal di daftar lama tidak (belum ada, atau statusnya lebih
    ringan). Status OUT -> DOUBTFUL (membaik) TIDAK masuk new_out.
    resolved = pemain yang di daftar lama punya status yang
    dihitung (OUT/DOUBTFUL/QUESTIONABLE/PROBABLE) tapi tidak ada
    lagi di daftar baru. Perubahan status apa pun (termasuk ke/dari
    status yang tidak dikenal) tercatat di status_changed. Urutan
    keluaran deterministik (urut nama ternormalisasi).
    """
    lama = _peta_cedera(old_entries)
    baru = _peta_cedera(new_entries)
    new_out: list[str] = []
    status_changed: list[dict] = []
    resolved: list[str] = []
    for nama_norm in sorted(baru):
        entri_baru = baru[nama_norm]
        status_baru = entri_baru["status"]
        status_lama = lama[nama_norm]["status"] if nama_norm in lama else None
        if status_baru in STATUS_MATERIAL and status_lama not in STATUS_MATERIAL:
            new_out.append(entri_baru["player"])
        if status_lama != status_baru:
            status_changed.append(
                {
                    "player": entri_baru["player"],
                    "old": status_lama,
                    "new": status_baru,
                }
            )
    for nama_norm in sorted(lama):
        if nama_norm not in baru and lama[nama_norm]["status"] in STATUS_DIHITUNG:
            resolved.append(lama[nama_norm]["player"])
    return {
        "new_out": new_out,
        "status_changed": status_changed,
        "resolved": resolved,
    }


def _kunci_berita(item: dict) -> str | None:
    """Identitas satu artikel berita untuk dedup (id, lalu url, lalu judul)."""
    for kunci in ("id", "url", "headline"):
        nilai = item.get(kunci)
        if isinstance(nilai, str) and nilai:
            return f"{kunci}:{nilai}"
    return None


def compare_news(old_news, new_items, analysis_generated_at) -> dict:
    """Bandingkan berita analisis awal vs berita segar.

    old_news: blok `news` artefak analisis awal (atau None bila
    artefak lama tanpa blok itu). new_items: list artikel segar
    dari fetch_fresh (atau None bila fetch berita gagal).
    analysis_generated_at: jam artefak analisis dibuat (ISO).

    Mengembalikan {"baru": [...], "n_baru": int, "n_dibandingkan":
    int}. "baru" = artikel MENDADAK + RELEVAN:
      - MENDADAK: jam terbit (published) LEBIH BARU dari
        analysis_generated_at. Artikel tanpa jam terbit yang bisa
        di-parse TIDAK PERNAH dihitung mendadak (tidak bisa
        dibuktikan terbit setelah analisis). Jam analisis awal
        yang tidak bisa di-parse -> tidak ada yang dihitung
        mendadak (baseline tidak diketahui).
      - RELEVAN: artikel ada di feed berita laga ini (fetcher
        sudah menyaring per tim) DAN identitasnya (id/url/judul)
        belum ada di blok news analisis awal.
    Urutan keluaran: terbaru dulu (sesuai urutan fetcher).
    """
    segar = [item for item in (new_items or []) if isinstance(item, dict)]
    baseline = _parse_iso(analysis_generated_at)
    if baseline is None:
        return {"baru": [], "n_baru": 0, "n_dibandingkan": len(segar)}
    lama: set[str] = set()
    if isinstance(old_news, dict):
        for item in old_news.get("items") or []:
            if isinstance(item, dict):
                kunci = _kunci_berita(item)
                if kunci is not None:
                    lama.add(kunci)
    baru: list[dict] = []
    for item in segar:
        terbit = _parse_iso(item.get("published"))
        if terbit is None or terbit <= baseline:
            continue
        kunci = _kunci_berita(item)
        if kunci is not None and kunci in lama:
            continue
        baru.append(item)
    return {"baru": baru, "n_baru": len(baru), "n_dibandingkan": len(segar)}


def compare_prices(analysis: dict, fresh: dict, cfg: dict | None = None) -> dict:
    """Bandingkan harga kaki (analisis awal) vs tangga segar.

    Mengembalikan {"moves": [...], "market_line_move": {...}}.
    Satu entri moves per kaki di analysis (invarian: jumlah moves
    == jumlah kaki):
      {"leg_key", "leg_id", "old_cents", "new_cents", "move_cents",
       "anomaly", "missing_line", "reason"}
    Harga lama = snapshot pertama (price_snapshots) bila ada, else
    harga efektif kaki. Harga baru = harga efektif entri Under
    tangga segar pada garis yang sama (jup_estimated_cents bila
    ada, else price_cents). anomaly = |gerak| >=
    anomaly.sharp_move_cents. Garis yang hilang dari tangga (atau
    harganya tidak terbaca) -> new_cents/move_cents None +
    missing_line True. Kaki yang bukan total_under atau garisnya
    tidak valid juga missing_line (recheck v1 hanya total_under).
    market_line_move = {"old", "new", "move_points"}: garis utama
    lama (market.main_total_line) vs garis utama segar (garis
    bervolume terbesar di tangga); move_points None bila salah
    satu tidak diketahui. Ambang sharp dibaca dari config
    (ConfigError bila kunci hilang).
    """
    if not isinstance(analysis, dict):
        raise ValueError(f"analysis harus dict, didapat {type(analysis).__name__}")
    if not isinstance(fresh, dict):
        raise ValueError(f"fresh harus dict, didapat {type(fresh).__name__}")
    cfg = _muat_cfg(cfg)
    ambang_sharp = _ambang(cfg, "anomaly", "sharp_move_cents")
    snapshots = analysis.get("price_snapshots")
    if not isinstance(snapshots, dict):
        snapshots = {}
    ladders = fresh.get("ladders")
    totals = ladders.get("totals") if isinstance(ladders, dict) else None
    peta_under = _peta_harga_under(totals)

    moves: list[dict] = []
    for leg in analysis.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        leg_id = leg.get("leg_id")
        garis = _angka(leg.get("line"))
        leg_key = f"total_under_{garis:g}" if garis is not None else None
        dasar = {
            "leg_key": leg_key,
            "leg_id": leg_id,
            "old_cents": None,
            "new_cents": None,
            "move_cents": None,
            "anomaly": False,
            "missing_line": False,
            "reason": None,
        }
        if leg.get("market_type") not in (None, "total_under"):
            dasar["missing_line"] = True
            dasar["reason"] = "pasar_bukan_total_under_tidak_didukung_recheck"
            moves.append(dasar)
            continue
        if garis is None:
            dasar["missing_line"] = True
            dasar["reason"] = "garis_kaki_tidak_valid"
            moves.append(dasar)
            continue
        snapshot = snapshots.get(leg_key) if leg_key is not None else None
        harga_lama = None
        if isinstance(snapshot, dict):
            harga_lama = _angka(snapshot.get("cents"))
        if harga_lama is None:
            harga_lama = _harga_efektif(leg)
        dasar["old_cents"] = harga_lama
        entri_baru = peta_under.get(garis)
        if entri_baru is None:
            dasar["missing_line"] = True
            dasar["reason"] = "garis_hilang_dari_tangga"
            moves.append(dasar)
            continue
        harga_baru = _harga_efektif(entri_baru)
        dasar["new_cents"] = harga_baru
        if harga_lama is None or harga_baru is None:
            dasar["missing_line"] = True
            dasar["reason"] = "harga_tidak_tersedia"
            moves.append(dasar)
            continue
        gerak = round(harga_baru - harga_lama, 9)
        dasar["move_cents"] = gerak
        dasar["anomaly"] = abs(gerak) >= ambang_sharp
        moves.append(dasar)

    market_lama = analysis.get("market")
    garis_lama = None
    if isinstance(market_lama, dict):
        garis_lama = _angka(market_lama.get("main_total_line"))
    garis_baru = garis_utama_dari_tangga(totals)
    gerak_garis = None
    if garis_lama is not None and garis_baru is not None:
        gerak_garis = round(garis_baru - garis_lama, 9)
    return {
        "moves": moves,
        "market_line_move": {
            "old": garis_lama,
            "new": garis_baru,
            "move_points": gerak_garis,
        },
    }


def needs_resim(
    injury_diff: dict | None, price_diff: dict, cfg: dict | None = None
) -> tuple[bool, list[str]]:
    """Putuskan perlu hitung ulang + alasan (list string).

    True bila: ada pemain baru OUT/DOUBTFUL (injury_diff.new_out
    tidak kosong — ini sudah mencakup "status berubah ke
    OUT/DOUBTFUL"), ATAU |pergerakan garis market| >
    recheck.market_line_move_points (tepat di ambang TIDAK memicu),
    ATAU ada gerakan harga anomali (>= ambang sharp). injury_diff
    None (cedera segar tidak diketahui karena fetch gagal) bukan
    pemicu — kasus itu ditangani aturan basi di decide().
    """
    if not isinstance(price_diff, dict):
        raise ValueError(f"price_diff harus dict, didapat {type(price_diff).__name__}")
    cfg = _muat_cfg(cfg)
    ambang_garis = _ambang(cfg, "recheck", "market_line_move_points")
    alasan: list[str] = []
    if isinstance(injury_diff, dict) and injury_diff.get("new_out"):
        alasan.append(
            "cedera_baru_out: " + ", ".join(str(n) for n in injury_diff["new_out"])
        )
    gerak = (price_diff.get("market_line_move") or {}).get("move_points")
    gerak = _angka(gerak)
    if gerak is not None and abs(gerak) > ambang_garis:
        alasan.append(f"garis_market_bergerak_{gerak:+g}_poin")
    for gerak_harga in price_diff.get("moves") or []:
        if isinstance(gerak_harga, dict) and gerak_harga.get("anomaly"):
            nilai = _angka(gerak_harga.get("move_cents"))
            kunci = gerak_harga.get("leg_key")
            if nilai is not None:
                alasan.append(f"harga_bergerak_{nilai:+g}c_{kunci}")
            else:
                alasan.append(f"harga_bergerak_anomali_{kunci}")
    return (len(alasan) > 0, alasan)


def _muat_modul(nama: str):
    """Muat satu modul engine; None bila modul belum tersedia.

    Cermin ``_muat_analis`` di engine/nba_analysis.py: modul yang
    belum ada (find_spec None) adalah keadaan operasional yang sah
    selama integrasi paralel — pemanggil memperlakukannya sebagai
    data tidak tersedia (fail-closed), bukan error. Modul yang ADA
    tapi gagal diimpor DIBIARKAN raise (bug kode, bukan data hilang).
    """
    modul = sys.modules.get(nama)
    if modul is not None:
        return modul
    try:
        if importlib.util.find_spec(nama) is None:
            return None
    except (ImportError, ValueError):
        return None
    return importlib.import_module(nama)


def _harga_min_cents(cfg: dict, tiket: str) -> float:
    """Harga minimum kaki (sen) dari analis.harga_min_*_cents.

    Kunci hilang -> default kontrak 75¢ (cermin
    ``baca_harga_min`` di engine/nba_analysis.py). Nilai yang ada
    tapi tidak valid (bukan angka 0–100) -> ValueError.
    """
    kunci = "harga_min_utama_cents" if tiket == "main" else "harga_min_asuransi_cents"
    section = cfg.get("analis", {})
    if not isinstance(section, dict) or kunci not in section:
        return _DEFAULT_HARGA_MIN_CENTS
    nilai = section[kunci]
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or not 0.0 < nilai < 100.0
    ):
        raise ValueError(f"analis.{kunci} tidak valid: {nilai!r} (harus angka 0-100)")
    return float(nilai)


def _hitung_bantalan(
    simulation: dict, inputs: dict | None, cfg: dict
) -> tuple[float | None, str | None]:
    """Bantalan adaptif Utama via engine.analis (cermin nba_analysis).

    Input SAMA seperti nba_analysis Tahap 4: stats laga dari
    ``nba_analysis.stats_laga_untuk_analis(inputs)`` + distribusi sim
    (``simulation["score_distribution"]["total"]``, butuh median +
    std). Mengembalikan (cushion_points, alasan) — alasan None bila
    berhasil, else kode alasan gaya nba_analysis
    ("analis_belum_tersedia", "bantalan_adaptif_tidak_tersedia",
    "bantalan_adaptif_gagal: <Tipe>",
    "bantalan_adaptif_hasil_tidak_valid") atau
    "inputs_tidak_tersedia" / "nba_analysis_belum_tersedia".
    TIDAK ada tebakan: None berarti kedua kaki resim fail-closed
    (cermin nba_analysis — Asuransi butuh garis Utama sebagai acuan).
    """
    if not isinstance(inputs, dict):
        return None, "inputs_tidak_tersedia"
    nba_mod = _muat_modul("engine.nba_analysis")
    if nba_mod is None:
        return None, "nba_analysis_belum_tersedia"
    analis_mod = _muat_modul("engine.analis")
    if analis_mod is None:
        return None, "analis_belum_tersedia"
    persen = (simulation.get("score_distribution") or {}).get("total")
    if not isinstance(persen, dict):
        return None, "bantalan_adaptif_tidak_tersedia"
    try:
        stats_laga = nba_mod.stats_laga_untuk_analis(inputs)
    except Exception as exc:  # noqa: BLE001 - statistik gagal = bantalan gagal
        return None, f"bantalan_adaptif_gagal: {type(exc).__name__}"
    try:
        hasil = analis_mod.bantalan_adaptif(stats_laga, persen, cfg)
    except Exception as exc:  # noqa: BLE001 - analis gagal = bantalan gagal
        return None, f"bantalan_adaptif_gagal: {type(exc).__name__}"
    if hasil is None:
        return None, "bantalan_adaptif_tidak_tersedia"
    poin = _angka(hasil.get("cushion_points")) if isinstance(hasil, dict) else None
    if poin is None:
        return None, "bantalan_adaptif_hasil_tidak_valid"
    alasan = hasil.get("alasan")
    return poin, (alasan if isinstance(alasan, str) else None)


def _bangun_kaki_resim(
    simulation: dict,
    entri_under: list[dict],
    garis_market: float,
    legs_lama: list[dict],
    match_id: str,
    fetched_at: str,
    cfg: dict,
    inputs: dict | None = None,
    sharp_move_per_tiket: dict | None = None,
) -> list[dict]:
    """Bangun kaki baru dari sim segar + tangga segar (murni).

    Urutan cermin nba_analysis Tahap 4: bantalan adaptif DULU
    (``_hitung_bantalan`` — input yang sama seperti nba_analysis:
    stats laga dari inputs + distribusi sim segar), lalu garis Utama
    via ``cushion.utama_line`` (signature baru: cushion_points
    adaptif, peluang_under = markets sim, harga_min_cents dari
    config), lalu garis Asuransi via ``cushion.insurance_line``
    dengan garis_di_atas = garis Utama. Bila bantalan tidak tersedia
    (inputs tidak ada / analis belum ada / data sim tidak lengkap),
    KEDUA kaki fail-closed dengan alasan tercatat — TANPA fallback ke
    aturan lama (cermin nba_analysis). p_model dari
    simulation["markets"]["total_under_{garis:g}"]. p_market DIBAWA
    dari kaki lama (recheck tidak mengambil pembanding baru — 0 kredit
    Odds API; pembanding segar di luar lingkup langkah 2) dan p_final
    di-blend ulang dengan bobot config (bila p_market None -> p_final
    = p_model). EV% + label harga dihitung ulang dari harga venue
    garis baru. Bila garis baru tidak meets: garis lama dipertahankan
    + meets False + reason dari cushion. Kaki bukan total_under /
    tiket tidak dikenal dibawa apa adanya (resim hanya menangani
    total_under). Kaki hasil membawa cushion_points/cushion_reason
    (bantalan adaptif per laga; None + kode alasan bila tidak
    tersedia) seperti kaki analisis.
    sharp_move_per_tiket: {tiket: True} untuk kaki yang harganya baru
    bergerak tajam (anomali sharp move) — label DISKON kaki itu
    ditekan jadi DISKON_DITEKAN (sharp move BUKAN diskon, kasus
    Thunder). None = tidak ada kaki yang ditekan.
    """
    persen = (simulation.get("score_distribution") or {}).get("total")
    if not isinstance(persen, dict):
        raise ValueError("resim: simulation tanpa score_distribution.total")
    markets = simulation.get("markets")
    if not isinstance(markets, dict):
        raise ValueError("resim: simulation tanpa markets")
    w_model = config.get_value(cfg, "blend", "w_model")
    if (
        isinstance(w_model, bool)
        or not isinstance(w_model, (int, float))
        or not math.isfinite(w_model)
        or not 0.0 <= w_model <= 1.0
    ):
        raise ValueError(f"blend.w_model tidak valid: {w_model!r} (harus 0–1)")
    peta_under = _peta_harga_under(entri_under)
    # Bantalan adaptif sekali per laga (sama untuk kedua kaki).
    bantalan, alasan_bantalan = _hitung_bantalan(simulation, inputs, cfg)
    ada_ins = any(
        isinstance(leg, dict)
        and leg.get("market_type") in (None, "total_under")
        and leg.get("ticket") == "insurance"
        for leg in legs_lama
    )
    ada_main = any(
        isinstance(leg, dict)
        and leg.get("market_type") in (None, "total_under")
        and leg.get("ticket") == "main"
        for leg in legs_lama
    )
    if bantalan is None:
        # Fail-closed cermin nba_analysis: tanpa bantalan, garis Utama
        # tidak bisa dipilih dan Asuransi kehilangan acuannya.
        gagal = {"meets": False, "reason": alasan_bantalan}
        pilihan_ins = gagal if ada_ins else None
        pilihan_main = gagal if ada_main else None
    else:
        pilihan_main = None
        garis_utama = None
        if ada_main:
            pilihan_main = cushion.utama_line(
                persen,
                garis_market,
                entri_under,
                cfg=cfg,
                cushion_points=bantalan,
                peluang_under=markets,
                harga_min_cents=_harga_min_cents(cfg, "main"),
            )
            if pilihan_main.get("meets"):
                garis_utama = _angka(pilihan_main.get("line"))
        pilihan_ins = None
        if ada_ins:
            pilihan_ins = cushion.insurance_line(
                persen,
                garis_market,
                entri_under,
                cfg=cfg,
                garis_di_atas=garis_utama,
                peluang_under=markets,
                harga_min_cents=_harga_min_cents(cfg, "insurance"),
            )
    hasil: list[dict] = []
    for leg_lama in legs_lama:
        if not isinstance(leg_lama, dict):
            continue
        tiket = leg_lama.get("ticket")
        if leg_lama.get("market_type") not in (None, "total_under") or tiket not in (
            "insurance",
            "main",
        ):
            hasil.append(dict(leg_lama))
            continue
        pilihan = pilihan_ins if tiket == "insurance" else pilihan_main
        garis_lama = _angka(leg_lama.get("line"))
        if pilihan.get("meets"):
            garis_baru = _angka(pilihan.get("line"))
            harga = _angka(pilihan.get("price_cents"))
            harga_jup = _angka(pilihan.get("jup_estimated_cents"))
            meets = True
            alasan = None
            bantalan_median = pilihan.get("cushion_vs_median_points")
            bantalan_market = pilihan.get("cushion_vs_market_points")
        else:
            garis_baru = garis_lama
            entri_lama = peta_under.get(garis_lama) if garis_lama is not None else None
            harga = _angka(entri_lama.get("price_cents")) if entri_lama else None
            harga_jup = (
                _angka(entri_lama.get("jup_estimated_cents")) if entri_lama else None
            )
            meets = False
            alasan = pilihan.get("reason")
            median = _angka(persen.get("median"))
            bantalan_median = (
                round(garis_baru - median, 9)
                if garis_baru is not None and median is not None
                else None
            )
            bantalan_market = (
                round(garis_baru - garis_market, 9) if garis_baru is not None else None
            )
        p_model = None
        if garis_baru is not None:
            p_model = _angka(markets.get(f"total_under_{garis_baru:g}"))
        p_market = _angka(leg_lama.get("p_market"))
        if p_model is not None and p_market is not None:
            p_final = round(w_model * p_model + (1.0 - w_model) * p_market, 9)
        elif p_model is not None:
            p_final = p_model
        else:
            p_final = None
        harga_venue = harga_jup if harga_jup is not None else harga
        ev_pct = None
        label = None
        if p_final is not None and harga_venue:
            ev_pct = round((p_final * (100.0 / harga_venue) - 1.0) * 100.0, 4)
            ditekan = (
                isinstance(sharp_move_per_tiket, dict)
                and sharp_move_per_tiket.get(tiket) is True
            )
            label = price_labels.label_for_ev(ev_pct, cfg, sharp_move=ditekan)
        if garis_baru is not None:
            leg_id = f"{match_id}:total_under_{garis_baru:g}:{tiket}"
        else:
            leg_id = f"{match_id}:total_under_na:{tiket}"
        hasil.append(
            {
                "leg_id": leg_id,
                "market_type": "total_under",
                "line": garis_baru,
                "ticket": tiket,
                "p_model": p_model,
                "p_market": p_market,
                "comparison_source": leg_lama.get("comparison_source"),
                "p_final": p_final,
                "price_cents": harga,
                "jup_estimated_cents": harga_jup,
                "ev_pct": ev_pct,
                "price_label": label,
                "cushion_vs_median_points": bantalan_median,
                "cushion_vs_market_points": bantalan_market,
                "cushion_points": bantalan,
                "cushion_reason": alasan_bantalan,
                "meets": meets,
                "reason": alasan,
                "fetched_at": fetched_at,
            }
        )
    return hasil


def _resim_default(
    fresh: dict, cfg: dict | None = None, analysis: dict | None = None
) -> dict:
    """Hitung ulang default: sim segar + garis Asuransi/Utama baru.

    fresh: dict hasil fetch_fresh (inputs segar + ladders segar).
    analysis (opsional): artefak awal — dipakai untuk (a) inputs
    lama sebagai fallback bila inputs segar tidak ada (resim karena
    gerakan harga/garis tidak butuh inputs baru), dan (b) kaki lama
    (tiket + p_market yang dibawa). Tanpa analysis, kaki dibangun
    untuk kedua tiket (insurance + main) dari match_id simulasi.
    Inputs (segar atau lama) diteruskan ke _bangun_kaki_resim untuk
    bantalan adaptif — input yang sama seperti nba_analysis.
    Mengembalikan {"simulation": dict, "legs": [leg baru]}.
    Melempar ValueError bila inputs (segar maupun lama) tidak ada,
    tangga total segar kosong, atau garis market tidak diketahui.
    Satu kali simulasi dengan SEMUA garis tangga sebagai lines,
    sehingga p_model tiap garis tersedia tanpa sim kedua.
    Sharp move per tiket dihitung di sini (via compare_prices) dan
    diteruskan ke _bangun_kaki_resim: kaki yang harganya baru
    bergerak tajam tidak boleh berlabel DISKON polos di kaki resim
    (sharp move BUKAN diskon — labelnya DISKON_DITEKAN).
    """
    if not isinstance(fresh, dict):
        raise ValueError(f"fresh harus dict, didapat {type(fresh).__name__}")
    cfg = _muat_cfg(cfg)
    inputs = fresh.get("inputs")
    if not isinstance(inputs, dict) and isinstance(analysis, dict):
        inputs = analysis.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError(
            "resim butuh inputs segar atau inputs lama; keduanya tidak ada"
        )
    ladders = fresh.get("ladders")
    totals = ladders.get("totals") if isinstance(ladders, dict) else None
    entri_under = _tangga_under(totals)
    if not entri_under:
        raise ValueError("resim butuh tangga total segar; tangga kosong")
    garis_market = garis_utama_dari_tangga(totals)
    if garis_market is None:
        raise ValueError("resim butuh garis market utama segar; tidak diketahui")
    garis_sim = sorted(
        {garis for garis in (_angka(e.get("line")) for e in entri_under) if garis}
    )
    simulation = nba_sim.simulate(
        inputs, cfg=cfg, lines={"spreads": [], "totals": garis_sim}
    )
    match_id = simulation.get("match_id") or "tidak_diketahui"
    if isinstance(analysis, dict) and isinstance(analysis.get("legs"), list):
        legs_lama = analysis["legs"]
        match_id = analysis.get("match_id") or match_id
    else:
        legs_lama = [
            {"ticket": "insurance", "market_type": "total_under"},
            {"ticket": "main", "market_type": "total_under"},
        ]
    # Sharp move per tiket (aturan Thunder): kaki yang harganya baru
    # bergerak tajam tidak boleh berlabel DISKON polos di kaki resim.
    # Tanpa analysis, tidak ada baseline harga lama -> tidak ada yang
    # ditekan (label dihitung seperti biasa).
    sharp_move_per_tiket: dict[str, bool] = {}
    if isinstance(analysis, dict):
        tiket_per_leg = {
            leg.get("leg_id"): leg.get("ticket")
            for leg in (analysis.get("legs") or [])
            if isinstance(leg, dict)
        }
        for gerak_harga in compare_prices(analysis, fresh, cfg=cfg)["moves"]:
            if isinstance(gerak_harga, dict) and gerak_harga.get("anomaly"):
                tiket = tiket_per_leg.get(gerak_harga.get("leg_id"))
                if tiket is not None:
                    sharp_move_per_tiket[tiket] = True
    legs_baru = _bangun_kaki_resim(
        simulation,
        entri_under,
        garis_market,
        legs_lama,
        match_id,
        fresh.get("fetched_at") or _sekarang_iso(),
        cfg,
        inputs=inputs,
        sharp_move_per_tiket=sharp_move_per_tiket,
    )
    return {"simulation": simulation, "legs": legs_baru}


def validate_recheck(laporan: dict) -> str | None:
    """Validasi laporan recheck terhadap schemas/recheck.schema.json.

    Mengembalikan pesan error, atau None bila valid. Bila
    ``jsonschema`` tidak tersedia, pakai validasi minimal
    (required-field) + peringatan ke stderr — pola yang sama
    seperti _validate_slate di cli.py.
    """
    if not isinstance(laporan, dict):
        return "laporan recheck harus dict"
    try:
        import jsonschema
    except ImportError:
        print(
            "peringatan: jsonschema tidak tersedia — validasi minimal "
            "(required-field) saja",
            file=sys.stderr,
        )
        for key in (
            "format",
            "format_version",
            "match_id",
            "recheck_at",
            "verdict",
            "resimulated",
            "resim_reasons",
            "changes",
            "legs",
            "anomalies",
            "missing",
            "attention",
            "action_required",
        ):
            if key not in laporan:
                return f"laporan recheck kehilangan kunci wajib: {key}"
        if not isinstance(laporan.get("legs"), list):
            return "laporan recheck.legs harus list"
        for leg in laporan["legs"]:
            for key in (
                "leg_id",
                "verdict",
                "reasons",
                "old_line",
                "new_line",
                "old_price_cents",
                "new_price_cents",
                "price_move_cents",
                "resimulated",
                "probability_used",
                "probability_value",
                "kenapa_beda",
            ):
                if key not in leg:
                    return f"kaki recheck kehilangan kunci wajib: {key}"
        return None
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"tidak bisa membaca skema recheck: {exc}"
    try:
        jsonschema.validate(laporan, schema)
    except jsonschema.ValidationError as exc:
        return f"laporan recheck tidak valid: {exc.message}"
    return None


def _data_cedera_basi(analysis: dict, recheck_at: str, stale_hours: float) -> bool:
    """Apakah data cedera analisis awal sudah basi (> stale_hours)?

    Umur diukur dari injuries.fetched_at, fallback ke generated_at.
    Jam yang hilang/tidak bisa di-parse -> dianggap BASI (fail-closed).
    """
    cedera = analysis.get("injuries")
    stamp = None
    if isinstance(cedera, dict):
        stamp = cedera.get("fetched_at")
    if stamp is None:
        stamp = analysis.get("generated_at")
    jam_data = _parse_iso(stamp)
    jam_recheck = _parse_iso(recheck_at)
    if jam_data is None or jam_recheck is None:
        return True
    return (jam_recheck - jam_data).total_seconds() > stale_hours * 3600.0


def _konflik_baru(entri_lama: list[dict], entri_baru: list[dict]) -> list[str]:
    """Pemain yang BARU punya konflik antar sumber di daftar segar.

    Entri gabungan membawa kunci "conflict" bila sumber-sumbernya
    tidak sepakat soal status. Konflik yang sudah ada di analisis
    awal bukan "baru" dan tidak dilaporkan lagi.
    """
    baru = _peta_cedera(entri_baru)
    hasil: list[str] = []
    for nama_norm in sorted(baru):
        if _konflik_entri(entri_baru, nama_norm) and not _konflik_entri(
            entri_lama, nama_norm
        ):
            hasil.append(baru[nama_norm]["player"])
    return hasil


def _konflik_entri(entri: list[dict], nama_norm: str) -> bool:
    """Apakah entri pemain ini membawa konflik antar sumber?"""
    for item in entri:
        if not isinstance(item, dict):
            continue
        if _normalisasi_nama(item.get("player")) != nama_norm:
            continue
        if item.get("conflict"):
            return True
        if item.get("status_comment_conflict") is True:
            return True
    return False


def _median_total(simulation) -> float | None:
    """Median total dari dict simulasi (score_distribution.total.median)."""
    if not isinstance(simulation, dict):
        return None
    total = (simulation.get("score_distribution") or {}).get("total")
    if not isinstance(total, dict):
        return None
    return _angka(total.get("median"))


def _kenapa_beda(
    median_lama: float | None,
    median_baru: float | None,
    garis_market_baru: float | None,
    gerak_garis_poin: float | None,
    cedera_baru: list[tuple[str, str | None]],
    ambang_gap: float,
) -> dict:
    """Hitung pemicu condong-ke-market + alasan konkret (a).

    median_lama: median sim analisis awal. median_baru: median sim
    segar bila resim (None bila tidak resim). garis_market_baru:
    garis utama tangga segar. gerak_garis_poin: pergerakan garis
    market (baru - lama), None bila tidak diketahui. cedera_baru:
    [(nama, status)] pemain baru OUT/DOUBTFUL. ambang_gap: ambang
    pemicu dari config.
    Mengembalikan {"gap_points", "triggered", "reason_found",
    "reason"}. Pemicu aktif bila |median - garis market| > ambang
    (median segar bila ada, else median lama). Alasan konkret (a)
    hanya bila ada cedera baru DAN market belum menghargainya:
    garis market tidak bergerak searah perubahan median (atau
    bergerak < 1 poin); tanpa sim segar, klausul "< 1 poin" yang
    dipakai; bila gerak garis tidak diketahui, alasan TIDAK
    ditegakkan.
    """
    median = median_baru if median_baru is not None else median_lama
    gap = None
    triggered = False
    if median is not None and garis_market_baru is not None:
        gap = round(abs(median - garis_market_baru), 9)
        triggered = gap > ambang_gap
    reason_found = False
    reason = None
    if triggered and cedera_baru and gerak_garis_poin is not None:
        if median_baru is not None and median_lama is not None:
            delta_median = round(median_baru - median_lama, 9)
        else:
            delta_median = None
        if delta_median is None or delta_median == 0:
            belum_dihargai = abs(gerak_garis_poin) < _GERAK_MARKET_MIN_DIHARGAI_POINTS
        else:
            searah = (gerak_garis_poin > 0) == (delta_median > 0) and (
                gerak_garis_poin != 0
            )
            belum_dihargai = not (
                searah and abs(gerak_garis_poin) >= _GERAK_MARKET_MIN_DIHARGAI_POINTS
            )
        if belum_dihargai:
            daftar = ", ".join(
                f"{nama} ({status})" if status else str(nama)
                for nama, status in cedera_baru
            )
            if delta_median is not None:
                reason = (
                    f"cedera baru {daftar}; garis market bergerak "
                    f"{gerak_garis_poin:+g} poin, median model bergerak "
                    f"{delta_median:+g} poin — market belum menghargai cedera"
                )
            else:
                reason = (
                    f"cedera baru {daftar}; garis market bergerak "
                    f"{gerak_garis_poin:+g} poin (< 1 poin) — market "
                    "belum menghargai cedera"
                )
            reason_found = True
    return {
        "gap_points": gap,
        "triggered": triggered,
        "reason_found": reason_found,
        "reason": reason,
    }


def _probabilitas_market(entri_under: dict | None) -> float | None:
    """Probabilitas tersirat market dari entri Under tangga segar.

    price_cents / 100; bila price_cents tidak ada, mid_cents / 100;
    bila keduanya tidak ada (atau tidak valid) -> None. Sengaja
    TIDAK memakai jup_estimated_cents — keputusan user memakai
    harga market mentah.
    """
    if not isinstance(entri_under, dict):
        return None
    harga = _angka(entri_under.get("price_cents"))
    if harga is None:
        harga = _angka(entri_under.get("mid_cents"))
    if harga is None or not 0.0 < harga < 100.0:
        return None
    return round(harga / 100.0, 9)


def _label_setelah_sharp_move(p_final, harga_baru_cents, cfg) -> str | None:
    """Label harga kaki setelah sharp move (DISKON ditekan).

    EV dihitung dari p_final pada harga BARU (harga segar), lalu label
    via price_labels.label_for_ev dengan sharp_move=True — EV yang
    akan berlabel DISKON menjadi DISKON_DITEKAN (sharp move BUKAN
    diskon, kasus Thunder). None bila p_final atau harga tidak bisa
    dipakai (label tidak bisa dihitung — tidak ditebak).
    """
    p = _angka(p_final)
    harga = _angka(harga_baru_cents)
    if p is None or harga is None:
        return None
    if not 0.0 <= p <= 1.0 or not 0.0 < harga < 100.0:
        return None
    ev_pct = round((p * (100.0 / harga) - 1.0) * 100.0, 4)
    return price_labels.label_for_ev(ev_pct, cfg, sharp_move=True)


def decide(
    analysis: dict,
    fresh: dict,
    cfg: dict | None = None,
    resim_fn=None,
    sekarang: str | None = None,
) -> dict:
    """Putuskan GO / NO_GO dari artefak analisis + data segar.

    analysis: artefak nba_analysis. fresh: dict hasil fetch_fresh
    (atau stub setara di tes). cfg: dict playstyle (None = baca
    playstyle.yaml). resim_fn: callable(fresh) -> {"simulation",
    "legs"} untuk hitung ulang; None = pakai _resim_default.
    sekarang: jam recheck ISO (untuk tes; None = jam sekarang).

    Mengembalikan laporan recheck format_version 1 (lihat
    schemas/recheck.schema.json), tervalidasi terhadap skema
    sebelum dikembalikan. Aturan putusan lengkap ada di docstring
    modul. ConfigError (ambang hilang) dibiarkan naik. ValueError
    bila analysis/fresh bukan dict, atau bila laporan yang
    dihasilkan tidak lolos skema.
    """
    if not isinstance(analysis, dict):
        raise ValueError(f"analysis harus dict, didapat {type(analysis).__name__}")
    if not isinstance(fresh, dict):
        raise ValueError(f"fresh harus dict, didapat {type(fresh).__name__}")
    cfg = _muat_cfg(cfg)
    ambang_sharp = _ambang(cfg, "anomaly", "sharp_move_cents")
    ambang_gerak_garis = _ambang(cfg, "recheck", "market_line_move_points")
    stale_hours = _ambang(cfg, "data", "stale_hours_injury_lineup")
    ambang_gap = _ambang(cfg, "calibration", "lean_to_market_gap")
    target_asuransi = _ambang(
        cfg, "filters", "nba_alt_under", "insurance_target_probability"
    )
    if not 0.0 < target_asuransi < 1.0:
        raise ValueError(
            "filters.nba_alt_under.insurance_target_probability tidak valid: "
            f"{target_asuransi!r} (harus di antara 0 dan 1)"
        )
    recheck_at = sekarang or _sekarang_iso()
    match_id = analysis.get("match_id") or "tidak_diketahui"
    errors = fresh.get("errors")
    if not isinstance(errors, dict):
        errors = {}
    inputs_gagal = fresh.get("inputs") is None or "inputs" in errors
    tangga_gagal = fresh.get("ladders") is None or "ladders" in errors

    # --- Perbandingan cedera + harga -------------------------------------
    entri_lama = _entri_cedera_analisis(analysis)
    entri_baru = None if inputs_gagal else entri_cedera_dari_inputs(fresh.get("inputs"))
    injury_diff = (
        compare_injuries(entri_lama, entri_baru) if entri_baru is not None else None
    )
    konflik_baru = (
        _konflik_baru(entri_lama, entri_baru) if entri_baru is not None else []
    )
    price_diff = compare_prices(analysis, fresh, cfg=cfg)
    perlu_resim, alasan_resim = needs_resim(injury_diff, price_diff, cfg=cfg)
    umur_basi = _data_cedera_basi(analysis, recheck_at, stale_hours)
    gerak_garis = price_diff["market_line_move"]["move_points"]
    garis_market_baru = price_diff["market_line_move"]["new"]

    # --- Perbandingan berita (modul news) -------------------------------
    # Berita baru TIDAK memicu hitung ulang (konteks, bukan angka) —
    # hanya PERHATIAN + changes (lihat compare_news untuk definisi
    # "mendadak" + "relevan"). fresh tanpa kunci "news" (stub lama)
    # berarti tidak ada data berita segar: tidak ada yang ditandai.
    news_baru: list[dict] = []
    if isinstance(fresh.get("news"), list):
        news_diff = compare_news(
            analysis.get("news"), fresh["news"], analysis.get("generated_at")
        )
        news_baru = news_diff["baru"]
    teks_news_baru = None
    if news_baru:
        judul_pertama = news_baru[0].get("headline") or "(judul tidak tercatat)"
        teks_news_baru = f"berita baru sejak analisis awal: {judul_pertama}"
        if len(news_baru) > 1:
            teks_news_baru += f" (+{len(news_baru) - 1} berita lain)"

    # --- Hitung ulang bila perlu -----------------------------------------
    resim = None
    resim_gagal = None
    if perlu_resim:
        try:
            if resim_fn is not None:
                resim = resim_fn(fresh)
            else:
                resim = _resim_default(fresh, cfg=cfg, analysis=analysis)
            if not isinstance(resim, dict) or not isinstance(resim.get("legs"), list):
                raise ValueError("resim mengembalikan bentuk tidak valid (tanpa legs)")
        except Exception as exc:  # noqa: BLE001 — resim gagal = DATA_INCOMPLETE
            resim = None
            resim_gagal = f"{type(exc).__name__}: {exc}"
    resimulated = resim is not None
    kaki_resim: dict[str, dict] = {}
    if resim is not None:
        for leg_baru in resim["legs"]:
            if isinstance(leg_baru, dict) and leg_baru.get("ticket") not in kaki_resim:
                kaki_resim[leg_baru.get("ticket")] = leg_baru

    # --- Aturan condong-ke-market (match-level) ---------------------------
    peta_baru = _peta_cedera(entri_baru) if entri_baru is not None else {}
    cedera_baru: list[tuple[str, str | None]] = []
    if injury_diff is not None:
        for nama in injury_diff["new_out"]:
            info = peta_baru.get(_normalisasi_nama(nama)) or {}
            cedera_baru.append((nama, info.get("status")))
    median_baru = _median_total(resim.get("simulation")) if resim is not None else None
    median_lama = _median_total(analysis.get("simulation"))
    kenapa_beda = _kenapa_beda(
        median_lama,
        median_baru,
        garis_market_baru,
        gerak_garis,
        cedera_baru,
        ambang_gap,
    )
    ladders = fresh.get("ladders")
    totals_segar = ladders.get("totals") if isinstance(ladders, dict) else None
    peta_under = _peta_harga_under(totals_segar)

    # --- Perubahan (changes) ----------------------------------------------
    changes: list[dict] = []
    if injury_diff is not None:
        if injury_diff["new_out"]:
            changes.append(
                {
                    "kind": "injury",
                    "detail": "pemain baru OUT/DOUBTFUL: "
                    + ", ".join(str(n) for n in injury_diff["new_out"]),
                }
            )
        for perubahan in injury_diff["status_changed"]:
            if perubahan["new"] in STATUS_MATERIAL:
                continue  # sudah tercatat sebagai new_out
            changes.append(
                {
                    "kind": "injury",
                    "detail": f"status {perubahan['player']}: "
                    f"{perubahan['old']} -> {perubahan['new']}",
                }
            )
        if injury_diff["resolved"]:
            changes.append(
                {
                    "kind": "injury",
                    "detail": "pemain kembali dari cedera: "
                    + ", ".join(str(n) for n in injury_diff["resolved"]),
                }
            )
    if konflik_baru:
        changes.append(
            {
                "kind": "injury",
                "detail": "konflik cedera baru antar sumber: "
                + ", ".join(konflik_baru),
            }
        )
    if teks_news_baru is not None:
        changes.append({"kind": "news", "detail": teks_news_baru})
    for gerak_harga in price_diff["moves"]:
        if gerak_harga.get("missing_line"):
            changes.append(
                {
                    "kind": "price",
                    "detail": f"garis {gerak_harga.get('leg_key')} hilang dari "
                    "tangga segar (atau harganya tidak terbaca)",
                }
            )
        elif (
            gerak_harga.get("move_cents") is not None
            and abs(gerak_harga["move_cents"]) >= _GERAK_MIN_PERHATIAN_CENTS
        ):
            changes.append(
                {
                    "kind": "price",
                    "detail": f"harga {gerak_harga.get('leg_key')} bergerak "
                    f"{gerak_harga['move_cents']:+g}¢ "
                    f"({gerak_harga.get('old_cents')} -> "
                    f"{gerak_harga.get('new_cents')})",
                }
            )
    garis_lama = price_diff["market_line_move"]["old"]
    if gerak_garis is not None and gerak_garis != 0:
        changes.append(
            {
                "kind": "market_line",
                "detail": f"garis market {_format_garis(garis_lama)} -> "
                f"{_format_garis(garis_market_baru)} ({gerak_garis:+g} poin)",
            }
        )
    if kenapa_beda["triggered"]:
        if kenapa_beda["reason_found"]:
            detail_gap = (
                f"selisih median model vs garis market "
                f"{kenapa_beda['gap_points']:g} poin (> ambang {ambang_gap:g}); "
                f"alasan konkret: {kenapa_beda['reason']}"
            )
        else:
            detail_gap = (
                f"selisih median model vs garis market "
                f"{kenapa_beda['gap_points']:g} poin (> ambang {ambang_gap:g}); "
                "tidak ditemukan alasan konkret — probabilitas Asuransi "
                "memakai harga market"
            )
        changes.append({"kind": "market_line", "detail": detail_gap})
    if inputs_gagal and umur_basi:
        changes.append(
            {
                "kind": "stale",
                "detail": f"data cedera analisis awal basi (> {stale_hours:g} jam) "
                "dan fetch segar gagal",
            }
        )
    for kunci in ("inputs", "ladders"):
        if kunci in errors:
            changes.append(
                {"kind": "fetch_error", "detail": f"{kunci}: {errors[kunci]}"}
            )
    if resim_gagal is not None:
        changes.append(
            {"kind": "fetch_error", "detail": f"hitung ulang gagal: {resim_gagal}"}
        )

    # --- Anomali segar (bentuk dict sharp_move anomaly.py) ----------------
    snapshots = analysis.get("price_snapshots")
    if not isinstance(snapshots, dict):
        snapshots = {}
    anomalies: list[dict] = []
    label_sharp_per_leg: dict[str, str | None] = {}
    kaki_analisis_per_id = {
        leg.get("leg_id"): leg
        for leg in (analysis.get("legs") or [])
        if isinstance(leg, dict)
    }
    for gerak_harga in price_diff["moves"]:
        if not gerak_harga.get("anomaly"):
            continue
        snapshot = snapshots.get(gerak_harga.get("leg_key") or "")
        first_at = None
        if isinstance(snapshot, dict):
            first_at = snapshot.get("at")
        # Label harga setelah sharp move: p_final kaki resim bila ada,
        # else p_final analisis awal; EV pada harga BARU. DISKON polos
        # dilarang di sini (sharp move BUKAN diskon).
        leg_lama = kaki_analisis_per_id.get(gerak_harga.get("leg_id")) or {}
        kaki_baru = kaki_resim.get(leg_lama.get("ticket")) or {}
        p_final_anomali = _angka(kaki_baru.get("p_final"))
        if p_final_anomali is None:
            p_final_anomali = _angka(leg_lama.get("p_final"))
        label_anomali = _label_setelah_sharp_move(
            p_final_anomali, gerak_harga.get("new_cents"), cfg
        )
        if gerak_harga.get("leg_id") is not None:
            label_sharp_per_leg[gerak_harga["leg_id"]] = label_anomali
        anomalies.append(
            {
                "type": "sharp_move",
                "key": gerak_harga.get("leg_key"),
                "leg_id": gerak_harga.get("leg_id"),
                "first_cents": gerak_harga.get("old_cents"),
                "now_cents": gerak_harga.get("new_cents"),
                "delta_cents": gerak_harga.get("move_cents"),
                "first_at": first_at,
                # Framing sharp move BUKAN diskon (kasus Thunder):
                # label ditekan + "Kenapa beda?" wajib sampai
                # pergerakannya dijelaskan. price_label None bila EV
                # tidak bisa dihitung (p_final/harga tidak tersedia).
                "price_label": label_anomali,
                "kenapa_beda_required": True,
                "catatan": (
                    "harga baru bergerak tajam, selidiki dulu — pasar "
                    "kemungkinan tahu sesuatu (bukan diskon)"
                ),
            }
        )

    # --- Putusan per kaki --------------------------------------------------
    status_analisis = analysis.get("status")
    gerak_per_leg = {
        gerak.get("leg_id"): gerak
        for gerak in price_diff["moves"]
        if isinstance(gerak, dict)
    }
    legs_lama = analysis.get("legs")
    if not isinstance(legs_lama, list):
        legs_lama = []
    legs_laporan: list[dict] = []
    attention: list[str] = []
    action_required: str | None = None
    for leg in legs_lama:
        if not isinstance(leg, dict):
            continue
        leg_id = leg.get("leg_id") or "leg_tanpa_id"
        tiket = leg.get("ticket")
        garis_lama_kaki = _angka(leg.get("line"))
        gerak = gerak_per_leg.get(leg_id) or {}
        kaki_baru = kaki_resim.get(tiket)
        kaki_diresim = kaki_baru is not None
        garis_baru_kaki = garis_lama_kaki
        if kaki_baru is not None:
            garis_baru_kaki = _angka(kaki_baru.get("line"))
            if garis_baru_kaki is None:
                garis_baru_kaki = garis_lama_kaki

        # Probabilitas yang dipakai (pencatatan; aturan condong-ke-market
        # hanya mengubah keputusan Asuransi).
        p_model_kaki = None
        if kaki_baru is not None:
            p_model_kaki = _angka(kaki_baru.get("p_model"))
        if p_model_kaki is None:
            p_model_kaki = _angka(leg.get("p_model"))
        probability_used = "model"
        probability_value = p_model_kaki
        prob_market = None
        aturan_market_aktif = (
            tiket == "insurance"
            and kenapa_beda["triggered"]
            and not kenapa_beda["reason_found"]
        )
        if aturan_market_aktif:
            entri_under = (
                peta_under.get(garis_lama_kaki) if garis_lama_kaki is not None else None
            )
            prob_market = _probabilitas_market(entri_under)
            probability_used = "market"
            probability_value = prob_market

        # Putusan keras (prioritas berurutan) vs alasan lunak.
        verdict = None
        alasan: list[str] = []
        lunak: list[str] = []
        if status_analisis == "DATA_INCOMPLETE":
            verdict = "DATA_INCOMPLETE"
            alasan.append("analisis awal DATA_INCOMPLETE")
        elif status_analisis == "HOLD":
            verdict = "JANGAN_PASANG"
            alasan.append("analisis awal berstatus HOLD — belum siap dipasang")
        elif tangga_gagal:
            verdict = "DATA_INCOMPLETE"
            alasan.append(f"harga segar gagal diambil: {errors.get('ladders')}")
        elif inputs_gagal and umur_basi:
            verdict = "DATA_INCOMPLETE"
            alasan.append(
                f"data cedera basi (> {stale_hours:g} jam) dan fetch segar gagal"
            )
        elif leg.get("meets") is False:
            verdict = "JANGAN_PASANG"
            alasan.append("kaki awal tidak memenuhi syarat")
        elif gerak.get("missing_line"):
            verdict = "JANGAN_PASANG"
            alasan.append(
                f"garis {_format_garis(garis_lama_kaki)} hilang dari tangga segar"
            )
        elif gerak.get("anomaly"):
            verdict = "JANGAN_PASANG"
            alasan.append(
                f"harga bergerak {gerak.get('move_cents'):+g}¢ "
                f"(>= ambang sharp {ambang_sharp:g}¢)"
            )
            # Framing sharp move BUKAN diskon (kasus Thunder):
            # JANGAN_PASANG sudah lebih keras dari PERHATIAN; alasan
            # ini menjelaskan kenapa label DISKON ditekan sampai
            # "Kenapa beda?" terjawab.
            if label_sharp_per_leg.get(leg_id) == price_labels.DISKON_DITEKAN:
                alasan.append(
                    "label DISKON ditekan jadi DISKON_DITEKAN — harga "
                    "baru bergerak tajam, selidiki dulu"
                )
            else:
                alasan.append(
                    "harga baru bergerak tajam, selidiki dulu — pasar "
                    "kemungkinan tahu sesuatu (bukan diskon)"
                )
        elif perlu_resim and resim_gagal is not None:
            verdict = "DATA_INCOMPLETE"
            alasan.append(f"hitung ulang gagal: {resim_gagal}")
        elif perlu_resim and resimulated and kaki_baru is None:
            verdict = "DATA_INCOMPLETE"
            alasan.append(f"kaki resim untuk tiket {tiket} tidak ada")
        elif kaki_baru is not None and not kaki_baru.get("meets", False):
            verdict = "JANGAN_PASANG"
            alasan.append(
                "garis baru tidak memenuhi syarat: "
                f"{kaki_baru.get('reason') or 'tanpa alasan'}"
            )
        elif (
            kaki_baru is not None
            and garis_baru_kaki is not None
            and garis_lama_kaki is not None
            and garis_baru_kaki != garis_lama_kaki
        ):
            verdict = "JANGAN_PASANG"
            alasan.append(
                f"garis berubah {_format_garis(garis_lama_kaki)} -> "
                f"{_format_garis(garis_baru_kaki)} setelah hitung ulang"
            )
            if action_required is None:
                action_required = f"ganti garis ke {_format_garis(garis_baru_kaki)}"
        elif aturan_market_aktif and prob_market is None:
            verdict = "DATA_INCOMPLETE"
            alasan.append(
                "condong_ke_market: harga market garis "
                f"{_format_garis(garis_lama_kaki)} tidak tersedia di tangga segar"
            )
        elif (
            aturan_market_aktif
            and prob_market is not None
            and prob_market < target_asuransi
        ):
            verdict = "JANGAN_PASANG"
            alasan.append(
                "condong_ke_market: harga market "
                f"{prob_market * 100:g}% < {target_asuransi * 100:g}% "
                "dan tidak ada alasan konkret"
            )
        if verdict is None:
            # Alasan lunak -> PERHATIAN (tetap GO).
            if kaki_baru is not None:
                lunak.append(
                    "hitung ulang ("
                    + "; ".join(alasan_resim)
                    + f"); garis tetap {_format_garis(garis_lama_kaki)}"
                )
            gerak_cents = _angka(gerak.get("move_cents"))
            if gerak_cents is not None and (
                _GERAK_MIN_PERHATIAN_CENTS <= abs(gerak_cents) < ambang_sharp
            ):
                lunak.append(f"harga bergerak {gerak_cents:+g}¢")
            if gerak_garis is not None and 0 < abs(gerak_garis) <= ambang_gerak_garis:
                lunak.append(f"garis market bergerak {gerak_garis:+g} poin")
            if konflik_baru:
                lunak.append(
                    "konflik cedera baru antar sumber: " + ", ".join(konflik_baru)
                )
            if injury_diff is not None:
                ringan = [
                    f"{p['player']}: {p['old']} -> {p['new']}"
                    for p in injury_diff["status_changed"]
                    if p["new"] not in STATUS_MATERIAL
                ]
                if ringan:
                    lunak.append("status cedera berubah: " + "; ".join(ringan))
                if injury_diff["resolved"]:
                    lunak.append(
                        "pemain kembali dari cedera: "
                        + ", ".join(str(n) for n in injury_diff["resolved"])
                    )
            if teks_news_baru is not None:
                lunak.append(teks_news_baru)
            if aturan_market_aktif and prob_market is not None:
                lunak.append(
                    "condong_ke_market: memakai probabilitas market "
                    f"{prob_market * 100:g}% (>= {target_asuransi * 100:g}%) "
                    "karena tidak ada alasan konkret"
                )
            if lunak:
                verdict = "PERHATIAN"
                alasan.extend(lunak)
            else:
                verdict = "TETAP_OK"
        if verdict == "PERHATIAN":
            for item in alasan:
                if item not in attention:
                    attention.append(item)
        if verdict == "JANGAN_PASANG" and action_required is None:
            if gerak.get("anomaly"):
                action_required = (
                    "jangan pasang — harga bergerak "
                    f"{gerak.get('move_cents'):+g}¢ sejak analisis awal"
                )
            elif gerak.get("missing_line"):
                action_required = (
                    "analisis ulang — garis "
                    f"{_format_garis(garis_lama_kaki)} hilang dari tangga"
                )
            elif status_analisis == "HOLD":
                action_required = "tunggu analisis berstatus OK sebelum submit"
            elif aturan_market_aktif and prob_market is not None:
                action_required = (
                    "jangan pasang kaki Asuransi garis "
                    f"{_format_garis(garis_lama_kaki)} — mesin sudah "
                    "menaikkan garis ke anak tangga yang lebih aman, tapi "
                    "harga marketnya tetap di bawah ambang Asuransi "
                    f"({target_asuransi * 100:g}%)"
                )
        legs_laporan.append(
            {
                "leg_id": leg_id,
                "verdict": verdict,
                "reasons": alasan,
                "old_line": garis_lama_kaki,
                "new_line": garis_baru_kaki,
                "old_price_cents": _angka(gerak.get("old_cents")),
                "new_price_cents": _angka(gerak.get("new_cents")),
                "price_move_cents": _angka(gerak.get("move_cents")),
                "resimulated": kaki_diresim,
                "probability_used": probability_used,
                "probability_value": probability_value,
                "kenapa_beda": dict(kenapa_beda),
            }
        )

    # --- Putusan tiket ------------------------------------------------------
    ada_tolak = any(
        leg["verdict"] in ("JANGAN_PASANG", "DATA_INCOMPLETE") for leg in legs_laporan
    )
    verdict_tiket = "NO_GO" if (ada_tolak or not legs_laporan) else "GO"
    if verdict_tiket == "GO" and attention and action_required is None:
        action_required = "baca daftar perhatian di laporan sebelum submit"
    if verdict_tiket == "NO_GO" and action_required is None:
        if not legs_laporan:
            action_required = "analisis tidak punya kaki — tidak ada yang bisa dipasang"
        elif any(leg["verdict"] == "DATA_INCOMPLETE" for leg in legs_laporan):
            action_required = "coba cek ulang lagi nanti — data segar tidak lengkap"
        else:
            action_required = "jangan submit tiket ini sesuai rencana awal"

    missing: list[str] = []
    if inputs_gagal:
        missing.append("inputs")
    if tangga_gagal:
        missing.append("ladders")
    if not legs_laporan:
        missing.append("legs")
    if resim_gagal is not None:
        missing.append("resim")
    if "news" in errors:
        missing.append("news")

    laporan = {
        "format": "nba_recheck",
        "format_version": 1,
        "match_id": match_id,
        "analysis_generated_at": analysis.get("generated_at"),
        "recheck_at": recheck_at,
        "verdict": verdict_tiket,
        "resimulated": resimulated,
        "resim_reasons": alasan_resim,
        "changes": changes,
        "legs": legs_laporan,
        "anomalies": anomalies,
        "missing": missing,
        "attention": attention,
        "action_required": action_required,
    }
    error_validasi = validate_recheck(laporan)
    if error_validasi is not None:
        raise ValueError(error_validasi)
    return laporan
