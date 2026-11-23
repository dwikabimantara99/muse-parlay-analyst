"""Penyambungan Otak NBA -> artefak analisis per laga (Tahap 3 Langkah 2 + Tahap 4).

Modul ini menyambungkan komponen Otak NBA yang sudah jadi
(ingest.nba_brain, engine.nba_sim, engine.cushion, tangga Polymarket,
Kalshi sebagai pembanding) menjadi SATU artefak JSON per laga
("nba_analysis", format_version 1) yang dipakai cli.py analyze dan
dikonsumsi engine/recheck.py (cek ulang pra-submit).

KONTRAK ARTEFAK (format_version 1 — KONTRAK BERSAMA dengan recheck,
jangan diubah sepihak; lihat schemas/nba_analysis.schema.json):
  format/format_version/match_id/home_tricode/away_tricode/game_date/
  start_time/generated_at/status/missing/sources/inputs/simulation/
  market/legs/injuries/anomalies/price_snapshots + analisis_wajar
  (Tahap 4, opsional — artefak lama tanpanya tetap valid) + news
  (modul news, opsional — artefak lama tanpanya tetap valid).
  match_id SAMA dengan simulation.match_id ("{AWAY}@{HOME}_{YYYY-MM-DD}").
  legs HANYA Asuransi + Utama (kaki moneyline di luar lingkup langkah ini).
  Tiap kaki Tahap 4 membawa cushion_points/cushion_reason (dari analis),
  volume_usd/thin/climb (dari cushion) — semuanya opsional di skema
  supaya artefak lama tetap valid.
  news adalah KONTEKS, bukan angka: status "ok" (ada berita),
  "kosong" (fetch berhasil, tidak ada berita relevan), atau "gagal"
  (fetch gagal, alasan di error). Berita gagal TIDAK mengubah status
  artefak (seperti Kalshi gagal -> MODEL_ONLY, bukan DATA_INCOMPLETE).

PIPELINE build_nba_analysis:
  1. fetch_match_inputs (input otak) — gagal -> DATA_INCOMPLETE.
  2. Tangga Polymarket (nba_slug + fetch_event_by_slug +
     parse_event_ladders) — gagal/kosong -> DATA_INCOMPLETE.
  3. Simulasi DUA PASS (seed sama): pass 1 (lines=None) untuk median,
     pass 2 dengan lines totals = semua garis Under tangga + garis
     median, agar kunci markets "total_under_{line:g}" ada untuk semua
     kaki. Dua pass memakai noise yang sama bila seed diberikan, jadi
     median pass 1 == median pass 2. Biaya: 2x waktu simulasi (~3,4
     detik untuk 100.000 iterasi default). Gagal -> DATA_INCOMPLETE.
  4. (Tahap 4) Bantalan adaptif DULU (analis.bantalan_adaptif dari
     statistik laga inputs + distribusi sim), lalu cushion.utama_line
     (signature baru: cushion_points adaptif, peluang_under dari
     markets sim, harga_min_cents dari config), lalu
     cushion.insurance_line (signature baru: garis_di_atas = garis
     Utama, peluang_under, harga_min_cents). Bila bantalan adaptif
     None (data tidak lengkap / modul analis belum tersedia) -> kedua
     kaki fail-closed dengan alasan tercatat, TANPA fallback ke +8.
     Spread TIDAK LAGI dipakai untuk bantalan (signature baru tanpa
     spread) maupun cek anomali (cek anomali memakai bantalan adaptif
     yang tercatat pada kaki); spread dari tangga tetap disimpan di
     artefak (market.spreads) untuk laporan.
     Penilaian wajar (analis.nilai_wajar, acuan = median sim) disimpan
     sebagai top-level `analisis_wajar`.
  5. Per kaki: p_model dari markets sim, p_market dari Kalshi
     (fetch_total_markets + kalshi_probability pada garis yang SAMA
     PERSIS; Under = komplemen 1 - p_over; tidak ada garis cocok ->
     None/MODEL_ONLY), blend (devig.blend), EV (D7), label
     (price_labels.label_for_ev).
  5b. Berita (ingest/news_nba.fetch_news_nba) — KONTEKS, bukan angka:
     gagal -> blok news status "gagal" + missing, artefak tetap jalan.
  6. Anomali (engine/anomaly.py): check_total_line_vs_model,
     check_cushion_vs_market, check_under_safety (yang di dalamnya
     menjalankan dua cek pertama — hasil dideduplikasi), ditambah
     check_model_vs_market + check_jup_vs_market per kaki bila
     p_market ada. price_delta_cents untuk check_under_safety adalah
     None di analisis awal (belum ada harga sebelumnya — snapshot
     pertama baru dibuat di sini).

STATUS: OK = sim + tangga + cedera 2 sumber semua ada. HOLD = B2 tidak
terpenuhi (cedera hanya 1 sumber) ATAU kaki Asuransi meets=false.
DATA_INCOMPLETE = fetch/sim gagal (input kritis hilang, tangga
kosong/gagal, sim error).

TAHAP v18 (worker C — wiring veto / timing gate / Vegas):
  1b. TUNGGU_LINEUP (engine.vonis.cek_tunggu_lineup, worker A):
      dievaluasi setelah Tahap 1 (data cedera ada). Bila tunggu=True,
      analisis DILANJUTKAN sebagai draf (sim + kaki tetap dihitung)
      tapi status akhir dipaksa HOLD + dicatat di missing, supaya
      komposer tidak memakai laga ini sampai recheck memperbarui
      statusnya. Pilihan draf-vs-henti: LANJUTKAN SEBAGAI DRAF —
      recheck butuh dasar perhitungan untuk memperbarui status
      tanpa analisis ulang penuh; keputusan ini menunggu keberatan.
      Bila fungsinya belum ada (worker A belum mendarat), dicatat di
      missing dan analisis jalan normal (tanpa gate).
  2b. VETO + SHORT-CIRCUIT (engine.vonis.evaluasi_veto): dievaluasi
      setelah Tahap 2 (garis pasar + cedera + pace sudah ada). Bila
      veto MENYALA, Tahap 3 (simulasi), 5 (Kalshi), 5b (news), dan
      5c (setan) DILEWATI — artefak tetap ditulis (status
      DATA_INCOMPLETE + blok veto + alasan jelas). Vonis KUNING
      untuk laga ini dihitung on-demand oleh engine/vonis.nilai_vonis
      (pemicu keras veto — dicatat juga di missing sebagai penanda).
      Hasil veto disimpan untuk SEMUA laga (menyala atau tidak).
      JUJUR SOAL ARSITEKTUR: pemindaian jup.ag adalah SLATE-LEVEL
      (SlateBuilder.fetch_all, sebelum analisis per laga), jadi
      short-circuit per laga TIDAK memangkas scan jup.ag — klaim
      penghematan Gemini §2 Q8 poin 3 ("pangkas 30-50% per slate")
      TIDAK berlaku untuk arsitektur ini. Yang dihemat adalah waktu
      Tahap 3+5+5b+5c per laga kena veto (diukur di
      LAPORAN-DEMON-V18.md + out/ukur_short_circuit.json).
      Pemangkasan scan jup.ag butuh restrukturisasi slate-level
      (di luar lingkup v18) — rekomendasi, bukan klaim.
  3b. VEGAS SHRINKAGE (engine.vegas.sesuaikan_median, worker B —
      signature asli dibaca dari disk: sesuaikan_median(median_model,
      garis_pasar, ada_sebab_cedera_baru, cfg=None) -> {"median_baru",
      "geser", "diterapkan", "alasan"}): dipanggil setelah Tahap 3
      (median sim + garis pasar ada). Kill-switch
      calibration.apply_shrinkage_pre_verdict False -> dilewati.
      "Sebab cedera baru" DIDEFINISIKAN wiring ini (B hanya menerima
      flag-nya): ada pemain OUT terkonfirmasi (>= 2 sumber) yang
      merupakan bintang (BPM >= vonis.tunggu_lineup.bpm_bintang —
      ambang dipakai ulang, bukan angka baru); USG tidak dipakai
      (butuh fetch); kesegaran "baru" tidak bisa dibuktikan dari
      satu snapshot (lihat _sebab_cedera_baru) — menunggu keberatan.
      Bila diterapkan, distribusi sim DIGESER KAKU sebesar geser
      (semua kuantil dist_total + P Under tiap garis = CDF mentah
      pada garis-geser) dan distribusi EFEKTIF itu menjadi distribusi
      KANONIK artefak: simulation.markets +
      simulation.score_distribution.total diganti dengan yang efektif
      (keputusan integrasi koordinator v18 — vonis/equilibrium/skip/
      komposer semuanya membaca CDF yang sudah disesuaikan, sesuai
      brief item 8 "SEBELUM vonis + equilibrium"). Distribusi mentah
      dipertahankan di simulation.markets_mentah +
      score_distribution.total_mentah + blok root "vegas"
      (median_mentah/median_baru/geser/alasan/sebab_cedera_baru);
      analisis_wajar membawa cermin field-field Vegas yang sama.
      Bila modulnya belum ada (worker B belum mendarat), median
      mentah dipakai apa adanya + dicatat di missing.
  PENEMPATAN SKEMA (v18, final — integrasi koordinator): blok veto /
  tunggu_lineup / vegas ada di ROOT artefak (properti opsional
  nba_analysis.schema.json); status "tunggu_lineup" ada di enum
  (nilai_vonis; builder tetap memakai HOLD untuk draf
  TUNGGU_LINEUP). TIDAK ADA status "VETO" — laga kena veto memakai
  DATA_INCOMPLETE + blok veto + vonis KUNING (keputusan integrasi:
  tidak ada jalur kode yang memakai status VETO).

FAIL-CLOSED: kegagalan tiap tahap -> artefak DATA_INCOMPLETE (dengan
data tahap yang berhasil tetap terlampir) + missing + error tercatat,
TIDAK PERNAH raise — kecuali argumen input tidak valid (ValueError).
Modul ini TIDAK PERNAH memanggil Odds API (pembanding hanya Kalshi);
0 kredit Odds API untuk langkah ini.

KAKI meets=false TETAP DICATAT sebagai leg (line null, leg_id memakai
"total_under_none", p_final/ev/label null, reason dari cushion) supaya
recheck dan laporan melihat kaki itu ada tapi tidak memenuhi syarat.

CATATAN HARGA: price_cents = harga Polymarket (mid book /
outcomePrices); jup_estimated_cents = estimasi harga venue jup.ag
(mid + markup tipikal). EV memakai jup_estimated_cents bila ada,
else price_cents. price_snapshots memakai harga yang sama (baseline
aturan Thunder untuk recheck).

CATATAN TAHAP 4 (integrasi paralel): engine/analis.py dan signature
baru cushion.py + kunci config analis.harga_min_*_cents dibangun
pekerja A (sudah mendarat di working tree saat wiring ini ditulis).
Bila modul analis belum ada saat builder jalan, bantalan dianggap
tidak tersedia -> kedua kaki fail-closed (alasan
"analis_belum_tersedia") dan analisis_wajar = "tidak_terverifikasi".
Bila cushion lama masih terpasang (TypeError karena kwarg baru),
builder mengembalikan DATA_INCOMPLETE dengan alasan cushion_gagal —
JANGAN fallback ke aturan lama.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from datetime import UTC, datetime

import config as config_mod
from engine import anomaly as anomaly_mod
from engine import cushion as cushion_mod
from engine import devig as devig_mod
from engine import nba_sim as nba_sim_mod
from engine import price_labels as price_labels_mod
from engine import setan_pemain as setan_pemain_mod
from engine import stress as stress_mod
from engine import vonis as vonis_mod
from ingest import kalshi as kalshi_mod
from ingest import matching as matching_mod
from ingest import nba_brain as nba_brain_mod
from ingest import news_nba as news_nba_mod
from ingest import pemain_3p as pemain_3p_mod
from ingest import polymarket as polymarket_mod
from ingest.common import now_iso

FORMAT = "nba_analysis"
FORMAT_VERSION = 1

# Default sementara harga minimum kaki Tahap 4 (sen) sampai pekerja A
# menambahkan kunci analis.harga_min_utama_cents /
# analis.harga_min_asuransi_cents ke playstyle.yaml — nilai ini adalah
# nilai kontrak bersama (75¢), BUKAN karangan. Bila kunci sudah ada di
# config, nilai config yang dipakai (dan divalidasi); bila belum ada,
# default ini yang dipakai + dicatat sumbernya ("default").
# Pola yang sama dengan DEFAULT_* di engine/cushion.py.
DEFAULT_HARGA_MIN_CENTS = 75.0

# Penilaian yang sah dari analis.nilai_wajar (kontrak bersama).
_PENILAIAN_WAJAR = ("wajar", "di_bawah_wajar", "tidak_terverifikasi")

_SKEMA_NBA_ANALYSIS = "nba_analysis.schema.json"
_SKEMA_SIMULASI = "simulation.schema.json"
_TANGGAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Kunci wajib artefak (validasi minimal bila jsonschema tidak tersedia).
_WAJIB_ARTEFAK = (
    "format",
    "format_version",
    "match_id",
    "home_tricode",
    "away_tricode",
    "game_date",
    "generated_at",
    "status",
    "legs",
)
# Kunci wajib simulasi (validasi minimal, selaras simulation.schema.json).
_WAJIB_SIMULASI = (
    "match_id",
    "sport",
    "iterations",
    "generated_at",
    "engine",
    "markets",
)


def _muat_skema(nama: str) -> dict | None:
    """Muat satu file skema dari schemas/; None bila tidak bisa dibaca."""
    try:
        teks = (config_mod.REPO_ROOT / "schemas" / nama).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(teks)
    except json.JSONDecodeError:
        return None


def _validasi_jsonschema(instansi: dict, nama_skema: str) -> str | None:
    """Validasi instansi terhadap skema; None bila valid.

    Bila jsonschema tidak tersedia, pakai validasi minimal
    (required-field) — pola yang sama dengan _validate_slate di cli.py.
    """
    try:
        import jsonschema
    except ImportError:
        wajib = _WAJIB_ARTEFAK if nama_skema == _SKEMA_NBA_ANALYSIS else _WAJIB_SIMULASI
        for kunci in wajib:
            if kunci not in instansi:
                return f"{nama_skema}: kehilangan kunci wajib: {kunci}"
        return None
    skema = _muat_skema(nama_skema)
    if skema is None:
        return f"tidak bisa membaca skema {nama_skema}"
    try:
        jsonschema.validate(instansi, skema)
    except jsonschema.ValidationError as exc:
        return f"tidak valid vs {nama_skema}: {exc.message}"
    return None


def validate_nba_analysis(artefak: dict) -> str | None:
    """Validasi artefak nba_analysis terhadap skemanya.

    Mengembalikan pesan error, atau None bila valid. Dipakai builder
    sebelum mengembalikan artefak, dan tersedia untuk konsumen
    (mis. recheck) yang ingin memvalidasi artefak yang dibacanya.
    """
    if not isinstance(artefak, dict):
        return "artefak harus dict"
    return _validasi_jsonschema(artefak, _SKEMA_NBA_ANALYSIS)


def _validasi_simulasi(sim: dict) -> str | None:
    """Validasi dict simulasi terhadap simulation.schema.json."""
    if not isinstance(sim, dict):
        return "simulasi harus dict"
    return _validasi_jsonschema(sim, _SKEMA_SIMULASI)


def minimal_nba_analysis(
    match_id: str,
    home_tricode: str,
    away_tricode: str,
    game_date: str,
    missing: list[str],
    start_time: str | None = None,
) -> dict:
    """Artefak minimal DATA_INCOMPLETE yang tetap valid vs skema.

    Dipakai builder untuk kegagalan total, dan cli.py analyze bila
    builder gagal total / tricode tidak bisa dipetakan — analyze tetap
    jalan, slate tidak gagal hanya karena satu laga NBA.
    """
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "match_id": match_id,
        "home_tricode": home_tricode,
        "away_tricode": away_tricode,
        "game_date": game_date,
        "start_time": start_time,
        "generated_at": now_iso(),
        "status": "DATA_INCOMPLETE",
        "missing": list(missing),
        "sources": [],
        "inputs": None,
        "simulation": None,
        "market": None,
        "legs": [],
        "injuries": {
            "sources": [],
            "n_sources": 0,
            "confirmed_both": [],
            "entries": [],
            "conflicts": [],
            "fetched_at": None,
        },
        "anomalies": [],
        "price_snapshots": {},
        "news": {
            "status": "gagal",
            "items": [],
            "sources": [],
            "fetched_at": None,
            "error": "tidak_diambil",
        },
    }


def _blok_news(hasil) -> dict:
    """Rakit blok news artefak dari FetchResult ingest/news_nba.

    ok + ada item -> status 'ok'; ok + kosong -> 'kosong' (fetch
    berhasil, tidak ada berita relevan — dibedakan dari gagal);
    gagal -> 'gagal' + error. Bentuk lain (bukan FetchResult) ->
    'gagal' + error 'hasil_fetch_tidak_dikenal'.
    """
    if not hasattr(hasil, "ok"):
        return {
            "status": "gagal",
            "items": [],
            "sources": [],
            "fetched_at": None,
            "error": "hasil_fetch_tidak_dikenal",
        }
    if not hasil.ok:
        return {
            "status": "gagal",
            "items": [],
            "sources": [],
            "fetched_at": getattr(hasil, "fetched_at", None),
            "error": str(getattr(hasil, "error", None) or "fetch gagal"),
        }
    items = hasil.data if isinstance(hasil.data, list) else []
    return {
        "status": "ok" if items else "kosong",
        "items": items,
        "sources": [hasil.source] if isinstance(hasil.source, str) else [],
        "fetched_at": getattr(hasil, "fetched_at", None),
        "error": None,
    }


def _musim_nba_dari_tanggal(tanggal: str) -> str:
    """Turunkan musim NBA ('2026-27') dari tanggal laga YYYY-MM-DD.

    Musim NBA mulai Oktober: tanggal Okt–Des -> musim tahun itu;
    Jan–Sep -> musim tahun sebelumnya. ValueError bila tanggal
    tidak bisa diparse (pemanggil mengubahnya jadi blok gagal).
    """
    potong = str(tanggal or "").strip().split("T", 1)[0].split(" ", 1)[0]
    tahun, bulan, _hari = (int(bagian) for bagian in potong.split("-", 2))
    if bulan >= 10:
        return f"{tahun}-{str(tahun + 1)[2:]}"
    return f"{tahun - 1}-{str(tahun)[2:]}"


def _blok_setan_pemain(
    home: str,
    away: str,
    median: float | None,
    main_line: float | None,
    artefak: dict,
    cfg: dict,
    generated_at: str,
    tanggal: str,
) -> dict:
    """Rakit blok setan_pemain artefak (Tahap 5c, setan per pemain).

    Fetch data 3P se-liga (sekali per proses via cache pemain_3p),
    hitung total setan spesifik-tim via engine/setan_pemain, lalu
    ratakan hasilnya ke blok dengan status + sumber + jam.
    TIDAK PERNAH melempar: fetch/hitung gagal -> status 'gagal' +
    error, artefak tetap jalan dan skenario_panas fallback ke
    setan umum. ``setan_pemain.enabled`` false -> 'nonaktif'
    (tanpa fetch). Kunci ``total_setan_pemain`` di level atas blok
    dibaca engine/stress.skenario_panas dari analysis.
    3PAr kedua tim dibaca dari inputs artefak (stats_season.
    tiga_pa_rate, ditambahkan worker A v18) dan diteruskan ke
    hitung_setan_pemain untuk flag 3P Volume Risk; artefak tanpa
    field itu -> flag "tidak_dievaluasi" (lihat setan_pemain).
    """
    dasar: dict = {
        "status": "gagal",
        "sources": [],
        "tier": None,
        "fetched_at": generated_at,
        "error": None,
    }
    try:
        aktif = config_mod.get_value(cfg, "setan_pemain", "enabled")
    except Exception:  # noqa: BLE001 - config lama tanpa kunci -> anggap aktif
        aktif = True
    if aktif is False:
        return {**dasar, "status": "nonaktif", "error": "setan_pemain.enabled false"}
    if median is None:
        return {**dasar, "error": "median_tidak_ada"}
    try:
        musim = _musim_nba_dari_tanggal(tanggal)
        hasil = pemain_3p_mod.fetch_pemain_3p_cached(season=musim)
    except Exception as exc:  # noqa: BLE001 - fetch tidak boleh mematikan builder
        return {**dasar, "error": f"{type(exc).__name__}: {exc}"}
    if (
        not getattr(hasil, "ok", False)
        or not isinstance(getattr(hasil, "data", None), list)
        or not hasil.data
    ):
        return {
            **dasar,
            "fetched_at": getattr(hasil, "fetched_at", generated_at),
            "error": str(getattr(hasil, "error", None) or "fetch pemain 3P gagal"),
        }
    try:
        absen = setan_pemain_mod.pemain_absen_dari_artefak(artefak)
        demon = setan_pemain_mod.hitung_setan_pemain(
            hasil.data,
            home,
            away,
            median,
            garis_bandar=main_line,
            pemain_absen=absen,
            cfg=cfg,
            tiga_pa_rate=_tiga_pa_rate_dari_artefak(artefak, home, away),
        )
    except Exception as exc:  # noqa: BLE001 - hitung gagal -> blok gagal
        return {
            **dasar,
            "fetched_at": getattr(hasil, "fetched_at", generated_at),
            "error": f"{type(exc).__name__}: {exc}",
        }
    blok: dict = {
        "status": "ok",
        "sources": [hasil.source] if isinstance(hasil.source, str) else [],
        "tier": getattr(hasil, "tier", None),
        "fetched_at": getattr(hasil, "fetched_at", generated_at),
        "error": None,
    }
    blok.update(demon)
    return blok


def _tiga_pa_rate_dari_artefak(artefak: dict, home: str, away: str) -> dict:
    """3PAr kedua tim dari inputs artefak ({tricode: nilai}).

    Dibaca dari inputs.home/away.stats_season.tiga_pa_rate (field
    v18 worker A). Nilai yang hilang / bukan angka tidak dimasukkan
    — hitung_setan_pemain lalu memberi flag "tidak_dievaluasi".
    TIDAK PERNAH melempar (inputs berbentuk aneh -> dict kosong).
    """
    hasil: dict[str, float] = {}
    try:
        inputs = artefak.get("inputs") if isinstance(artefak, dict) else None
        if not isinstance(inputs, dict):
            return hasil
        for tricode, sisi in ((home, "home"), (away, "away")):
            blok = inputs.get(sisi)
            musim = blok.get("stats_season") if isinstance(blok, dict) else None
            nilai = (
                _angka(musim.get("tiga_pa_rate")) if isinstance(musim, dict) else None
            )
            if nilai is not None:
                hasil[tricode] = nilai
    except (AttributeError, TypeError):
        return hasil
    return hasil


# ---------------------------------------------------------------------------
# Helper v18: veto (short-circuit), timing gate TUNGGU_LINEUP, Vegas.
# ---------------------------------------------------------------------------

# Kunci kuantil dist_total nba_sim yang digeser kaku oleh Vegas
# (parameter LOKASI — mean/median/kuantil; std TIDAK digeser karena
# parameter skala). Kunci di luar daftar ini diteruskan apa adanya.
_KUNCI_GESER_DIST = ("mean", "median", "p5", "p25", "p74", "p75", "p95")


def _blok_veto(artefak: dict, cfg: dict) -> tuple[dict, str | None]:
    """Evaluasi veto rim protector (Tahap 2b) — TIDAK PERNAH melempar.

    Mengembalikan (blok_veto, entri_missing_atau_None). Blok veto
    adalah hasil engine.vonis.evaluasi_veto apa adanya (dievaluasi
    untuk SEMUA laga, menyala atau tidak). Bila evaluasi gagal
    (mis. config ambang veto rusak) -> blok dievaluasi=False +
    entri missing; builder LANJUT normal (veto adalah klaim positif
    yang butuh data — kegagalan evaluasi bukan veto).
    """
    try:
        blok = vonis_mod.evaluasi_veto(artefak, cfg)
    except Exception as exc:  # noqa: BLE001 - veto gagal != analisis gagal
        return (
            {
                "dievaluasi": False,
                "menyala": False,
                "alasan": [],
                "alasan_tidak_dievaluasi": (
                    f"evaluasi_veto_gagal: {type(exc).__name__}: {exc}"
                ),
            },
            f"veto_tidak_dievaluasi: {type(exc).__name__}: {exc}",
        )
    if not isinstance(blok, dict):
        return (
            {
                "dievaluasi": False,
                "menyala": False,
                "alasan": [],
                "alasan_tidak_dievaluasi": ("evaluasi_veto mengembalikan bukan-dict"),
            },
            "veto_tidak_dievaluasi: hasil evaluasi bukan dict",
        )
    return blok, None


def _blok_tunggu_lineup(
    artefak: dict, cfg: dict
) -> tuple[dict | None, bool, str | None]:
    """Evaluasi timing gate TUNGGU_LINEUP (Tahap 1b).

    Mengembalikan (blok, tunggu, entri_missing_atau_None). Kontrak
    fungsi worker A (engine.vonis.cek_tunggu_lineup — DIBACA DARI
    DISK, bukan asumsi): cek_tunggu_lineup(analysis, cfg=None,
    usg_pemain=None) -> {"tunggu": bool, "bintang": [{"player",
    "team", "status", "usg", "bpm"}], "alasan": [str],
    "dievaluasi": bool, ...}. Bintang dinormalisasi ke daftar nama
    (detail dict dipertahankan di "bintang_detail"). Kunci "tunggu"
    juga dibaca dari fallback "hold"/"tahan"/status "tunggu_lineup"
    bila "tunggu" tidak ada — wiring defensif terhadap variasi.
    CATATAN FETCH: cek_tunggu_lineup menarik USG live
    (ingest/pemain_usg, gratis + cache satu-proses) HANYA bila ada
    pemain Questionable yang belum lolos lewat BPM — 0 kredit Odds
    API.
    Bila fungsinya belum ada -> (None, False, missing "belum
    tersedia") dan analisis jalan normal (tanpa gate).
    Bila fungsinya melempar -> fail-CLOSED: tunggu=True (status
    akhir HOLD) + blok dievaluasi=False + missing, supaya laga yang
    gate-nya tidak bisa dinilai tidak lolos diam-diam ke komposer.
    """
    fungsi = getattr(vonis_mod, "cek_tunggu_lineup", None)
    if not callable(fungsi):
        return (
            None,
            False,
            "tunggu_lineup_tidak_dievaluasi: cek_tunggu_lineup belum "
            "tersedia (worker A v18)",
        )
    try:
        hasil = fungsi(artefak, cfg)
    except Exception as exc:  # noqa: BLE001 - gate gagal = tahan laga
        return (
            {
                "dievaluasi": False,
                "tunggu": True,
                "bintang": [],
                "alasan": [f"cek_tunggu_lineup_gagal: {type(exc).__name__}: {exc}"],
                "sumber": "engine.vonis.cek_tunggu_lineup",
            },
            True,
            f"tunggu_lineup_gagal: {type(exc).__name__}: {exc}",
        )
    if not isinstance(hasil, dict):
        return (
            {
                "dievaluasi": False,
                "tunggu": True,
                "bintang": [],
                "alasan": ["cek_tunggu_lineup mengembalikan bukan-dict"],
                "sumber": "engine.vonis.cek_tunggu_lineup",
            },
            True,
            "tunggu_lineup_gagal: hasil cek bukan dict",
        )
    tunggu = hasil.get("tunggu")
    if tunggu is None:
        tunggu = hasil.get("hold", hasil.get("tahan"))
    if tunggu is None:
        tunggu = str(hasil.get("status") or "") == "tunggu_lineup"
    bintang = hasil.get("bintang", hasil.get("pemain", []))
    if not isinstance(bintang, list):
        bintang = [bintang] if bintang else []
    # Bintang v18 A adalah list dict {"player", "team", "status",
    # "usg", "bpm"} — normalisasi ke nama pemain (string); entri
    # string diteruskan apa adanya.
    nama_bintang: list[str] = []
    for entri in bintang:
        if isinstance(entri, dict):
            nama = entri.get("player")
            if isinstance(nama, str) and nama:
                nama_bintang.append(nama)
        elif isinstance(entri, str) and entri:
            nama_bintang.append(entri)
    alasan = hasil.get("alasan", [])
    if isinstance(alasan, str):
        alasan = [alasan]
    if not isinstance(alasan, list):
        alasan = []
    return (
        {
            "dievaluasi": bool(hasil.get("dievaluasi", True)),
            "tunggu": bool(tunggu),
            "bintang": nama_bintang,
            "bintang_detail": [entri for entri in bintang if isinstance(entri, dict)],
            "alasan": [str(a) for a in alasan],
            "sumber": "engine.vonis.cek_tunggu_lineup",
        },
        bool(tunggu),
        None,
    )


def _muat_vegas():
    """Muat engine.vegas (worker B); None bila modul belum tersedia.

    Pola yang sama dengan _muat_analis, dengan satu perbedaan yang
    disengaja: modul yang ADA tapi gagal diimpor JUGA mengembalikan
    None (bukan raise) — Vegas adalah penyesuaian dengan fallback
    yang aman (median mentah), bukan input kritis; kegagalan impor
    dicatat di missing oleh _terapkan_vegas, bukan mematikan
    analisis.
    """
    modul = sys.modules.get("engine.vegas")
    if modul is not None:
        return modul
    try:
        if importlib.util.find_spec("engine.vegas") is None:
            return None
    except (ImportError, ValueError):
        return None
    try:
        from engine import vegas as vegas_mod

        return vegas_mod
    except ImportError:
        return None


def _sebab_cedera_baru(
    artefak: dict, cfg: dict
) -> tuple[bool, list[str], bool, list[dict]]:
    """Apakah ada sebab cedera baru terverifikasi (untuk Vegas)?

    Definisi wiring v18 (keputusan worker C — menunggu keberatan;
    TIDAK didefinisikan worker B, modulnya hanya menerima flag ini):
    ada pemain berstatus OUT TERKONFIRMASI (>= 2 sumber, aturan yang
    sama dengan veto rim protector) yang merupakan BINTANG — BPM
    (inputs pemain, field "bpm") >= vonis.tunggu_lineup.bpm_bintang
    (2,0 — ambang "bintang" yang sama dengan timing gate, dipakai
    ulang, bukan angka baru). USG tidak dipakai di sini (butuh fetch
    ingest/pemain_usg — di luar builder; BPM saja sebagai proksi).

    v18.1 (Patch #4): filter KESEGARAN — pemain OUT hanya dihitung
    bila games_played musim berjalan (inputs pemain, field
    "games_played" dari BBRef via nba_brain) >=
    calibration.fresh_injury_min_gp_season (3). Pemain GP < 3
    (termasuk GP == 0 — absen sejak awal musim) sudah terserap
    harga pasar sehingga tidak membatalkan shrinkage. GP tidak
    tersedia / bukan angka -> TIDAK segar (fail-closed ke arah
    shrinkage berjalan) + dicatat di "dikecualikan".

    Mengembalikan (ada, [nama bintang OUT segar], dievaluasi,
    [dikecualikan]) — "dikecualikan" list {"player",
    "games_played" (None bila tidak tersedia), "alasan":
    "gp_di_bawah_minimum" / "gp_tidak_tersedia"} untuk bintang OUT
    terkonfirmasi yang gagal filter kesegaran. "Dievaluasi" False
    bila data pemain inputs tidak ada / ambang BPM atau ambang GP
    tidak bisa dibaca — pemanggil memakai ada=False (penyusutan
    berjalan sesuai default B) + mencatatnya di missing. BATAS
    JUJUR: kesegaran ("baru") TIDAK bisa dibuktikan dari satu
    snapshot — artefak tidak mencatat kapan cedera dilaporkan;
    definisi ini memakai OUT terkonfirmasi + GP sebagai proksi.
    Definisi "baru" yang tepat (membandingkan cedera lama vs baru)
    hanya ada di recheck. Tidak ada field "out for season"
    terstruktur di data cedera — GP adalah satu-satunya
    operasionalisasi kesegaran di jalur ini.
    """
    try:
        ambang_bpm = float(
            config_mod.get_value(cfg, "vonis", "tunggu_lineup", "bpm_bintang")
        )
    except (config_mod.ConfigError, TypeError, ValueError):
        return False, [], False, []
    try:
        ambang_gp = float(
            config_mod.get_value(cfg, "calibration", "fresh_injury_min_gp_season")
        )
    except (config_mod.ConfigError, TypeError, ValueError):
        return False, [], False, []
    inputs = artefak.get("inputs") if isinstance(artefak, dict) else None
    if not isinstance(inputs, dict):
        return False, [], False, []
    bpm_pemain: dict[str, float] = {}
    gp_pemain: dict[str, float | None] = {}
    ada_data_pemain = False
    for sisi in ("home", "away"):
        blok = inputs.get(sisi)
        pemain = blok.get("players") if isinstance(blok, dict) else None
        if not isinstance(pemain, list):
            continue
        ada_data_pemain = True
        for entri in pemain:
            if not isinstance(entri, dict):
                continue
            nama = entri.get("player")
            bpm = _angka(entri.get("bpm"))
            if isinstance(nama, str) and nama and bpm is not None:
                bpm_pemain[nama] = bpm
                gp_pemain[nama] = _angka(entri.get("games_played"))
    if not ada_data_pemain:
        return False, [], False, []
    cedera = artefak.get("injuries") if isinstance(artefak, dict) else None
    entri_cedera = (
        cedera.get("entries")
        if isinstance(cedera, dict) and isinstance(cedera.get("entries"), list)
        else []
    )
    bintang_out: list[str] = []
    dikecualikan: list[dict] = []
    for entri in entri_cedera:
        if not isinstance(entri, dict):
            continue
        if str(entri.get("status") or "").upper() != "OUT":
            continue
        n_sumber = _angka(entri.get("availability_n_sources"))
        if n_sumber is None:
            sumber = entri.get("sources")
            n_sumber = float(len(sumber)) if isinstance(sumber, list) else 0.0
        if n_sumber < 2:
            continue
        nama = entri.get("player")
        if (
            isinstance(nama, str)
            and nama in bpm_pemain
            and bpm_pemain[nama] >= ambang_bpm
        ):
            gp = gp_pemain.get(nama)
            if gp is None:
                dikecualikan.append(
                    {
                        "player": nama,
                        "games_played": None,
                        "alasan": "gp_tidak_tersedia",
                    }
                )
            elif gp < ambang_gp:
                dikecualikan.append(
                    {
                        "player": nama,
                        "games_played": gp,
                        "alasan": "gp_di_bawah_minimum",
                    }
                )
            else:
                bintang_out.append(nama)
    dikecualikan.sort(key=lambda d: d["player"])
    return bool(bintang_out), sorted(bintang_out), True, dikecualikan


def _panggil_sesuaikan_median(
    modul, median, garis_pasar, ada_sebab_cedera_baru, cfg, artefak
):
    """Panggil sesuaikan_median sesuai kontrak worker B.

    Signature asli (engine/vegas.py, dibaca dari disk):
    sesuaikan_median(median_model, garis_pasar,
    ada_sebab_cedera_baru, cfg=None) -> {"median_baru", "geser",
    "diterapkan", "alasan"}. Dipanggil dengan kwargs bernama persis;
    bila TypeError (signature berubah), dicoba posisional 4-arg,
    lalu varian 3-arg (median, garis_pasar, cfg) sebagai fallback
    terakhir. ValueError/ConfigError dari fungsi DIBIARKAN naik ke
    _terapkan_vegas (yang mencatatnya di missing dan memakai median
    mentah).
    """
    fungsi = getattr(modul, "sesuaikan_median", None)
    if not callable(fungsi):
        raise AttributeError("engine.vegas tanpa fungsi sesuaikan_median")
    try:
        return fungsi(
            median_model=median,
            garis_pasar=garis_pasar,
            ada_sebab_cedera_baru=ada_sebab_cedera_baru,
            cfg=cfg,
        )
    except TypeError:
        pass
    try:
        return fungsi(median, garis_pasar, ada_sebab_cedera_baru, cfg)
    except TypeError:
        return fungsi(median, garis_pasar, cfg)


def _terapkan_vegas(
    median: float, garis_pasar: float | None, cfg: dict, artefak: dict
) -> tuple[dict | None, str | None]:
    """Terapkan Vegas shrinkage (Tahap 3b) — TIDAK PERNAH melempar.

    Mengembalikan (vegas_info, entri_missing_atau_None). vegas_info:
    {"diterapkan": bool, "median_mentah": float, "median_baru":
    float | None, "geser": float | None, "alasan": str | None,
    "sebab_cedera_baru": {"ada": bool, "pemain": [...],
    "dievaluasi": bool, "dikecualikan_gp": [...]}, "sumber":
    "engine.vegas"}. None bila
    kill-switch calibration.apply_shrinkage_pre_verdict False /
    modul belum ada / garis pasar tidak ada / panggilan gagal —
    pemanggil memakai median mentah + mencatat missing.
    "Diterapkan" mengikuti flag "diterapkan" dari sesuaikan_median
    (dan median baru yang numerik); geser 0 = tidak diterapkan.
    """
    if garis_pasar is None:
        return None, "vegas_dilewati: garis_pasar_tidak_ada"
    try:
        terapkan = config_mod.get_value(
            cfg, "calibration", "apply_shrinkage_pre_verdict"
        )
    except config_mod.ConfigError:
        terapkan = True  # Kunci v18 belum ada -> terapkan (default B).
    if terapkan is False:
        return None, "vegas_dinonaktifkan: apply_shrinkage_pre_verdict false"
    modul = _muat_vegas()
    if modul is None:
        return (
            None,
            "vegas_tidak_dievaluasi: engine.vegas belum tersedia (worker B v18)",
        )
    ada_sebab, pemain_sebab, sebab_dievaluasi, dikecualikan_gp = _sebab_cedera_baru(
        artefak, cfg
    )
    catatan_sebab = None
    if not sebab_dievaluasi:
        catatan_sebab = (
            "vegas_sebab_cedera_tidak_dievaluasi: data BPM pemain / "
            "ambang bpm_bintang tidak ada — penyusutan berjalan "
            "tanpa pengecualian cedera"
        )
    try:
        hasil = _panggil_sesuaikan_median(
            modul, median, garis_pasar, ada_sebab, cfg, artefak
        )
    except Exception as exc:  # noqa: BLE001 - Vegas gagal = median mentah
        return None, f"vegas_gagal: {type(exc).__name__}: {exc}"
    info: dict = {
        "diterapkan": False,
        "median_mentah": median,
        "median_baru": None,
        "geser": None,
        "alasan": None,
        "sebab_cedera_baru": {
            "ada": ada_sebab,
            "pemain": pemain_sebab,
            "dievaluasi": sebab_dievaluasi,
            # v18.1 (Patch #4): bintang OUT terkonfirmasi yang gagal
            # filter kesegaran GP — [{player, games_played, alasan}].
            "dikecualikan_gp": dikecualikan_gp,
        },
        "sumber": "engine.vegas",
    }
    if isinstance(hasil, (bool, int, float)):
        median_baru = _angka(hasil)
        if median_baru is None:
            return None, "vegas_hasil_tidak_dikenal: median_baru bukan angka"
        info["median_baru"] = median_baru
        info["geser"] = median_baru - median
        info["diterapkan"] = median_baru != median
        return info, catatan_sebab
    if not isinstance(hasil, dict):
        return None, "vegas_hasil_tidak_dikenal: hasil bukan dict/angka"
    diterapkan = hasil.get("diterapkan", hasil.get("applied"))
    median_baru = _angka(
        hasil.get("median_baru", hasil.get("median_disesuaikan", hasil.get("median")))
    )
    geser = _angka(hasil.get("geser", hasil.get("geser_vegas", hasil.get("shift"))))
    alasan = hasil.get("alasan", hasil.get("reason"))
    info["alasan"] = alasan if isinstance(alasan, str) else None
    if diterapkan is False or median_baru is None:
        # Fungsi memutuskan tidak menyesuaikan (mis. gap <= ambang)
        # atau tidak mengembalikan median baru — bukan error.
        info["median_baru"] = median_baru
        info["geser"] = geser
        return info, catatan_sebab
    if geser is None:
        geser = median_baru - median
    info["median_baru"] = median_baru
    info["geser"] = geser
    info["diterapkan"] = bool(diterapkan) and median_baru != median
    return info, catatan_sebab


def _cdf_dari_markets(markets_sim: dict) -> list[tuple[float, float]]:
    """CDF total (garis, P Under) terurut dari markets sim."""
    hasil: list[tuple[float, float]] = []
    if not isinstance(markets_sim, dict):
        return hasil
    for kunci, nilai in markets_sim.items():
        if not isinstance(kunci, str) or not kunci.startswith("total_under_"):
            continue
        try:
            garis = float(kunci[len("total_under_") :])
        except ValueError:
            continue
        peluang = _peluang(nilai)
        if peluang is not None:
            hasil.append((garis, peluang))
    return sorted(hasil)


def _geser_distribusi(
    markets_sim: dict, dist_total: dict, geser: float
) -> tuple[dict, dict]:
    """Geser kaku distribusi sim sebesar geser (distribusi EFEKTIF v18).

    Mengembalikan (markets_efektif, dist_total_efektif) — distribusi
    kanonik artefak bila Vegas diterapkan (vonis/equilibrium/skip/
    komposer membacanya dari simulation.markets + total):
    - markets: tiap P(total_under_garis) menjadi CDF mentah pada
      (garis - geser) via engine/stress.p_under_digeser (interpolasi
      linear, dijepit di ujung — tanpa ekstrapolasi); kunci
      non-total_under diteruskan apa adanya.
    - dist_total: semua parameter lokasi (mean/median/kuantil —
      lihat _KUNCI_GESER_DIST) ditambah geser; std + kunci lain
      diteruskan apa adanya.
    Dict mentah TIDAK diubah (salinan baru). Asumsi wiring v18:
    geser kaku seluruh distribusi — worker B boleh mengganti
    dengan desain shift lain; median mentah tersimpan di blok root
    "vegas" + simulation.markets_mentah / total_mentah sebagai bukti.
    """
    cdf = _cdf_dari_markets(markets_sim)
    markets_efektif = dict(markets_sim)
    if cdf:
        for kunci in list(markets_sim):
            if not isinstance(kunci, str) or not kunci.startswith("total_under_"):
                continue
            try:
                garis = float(kunci[len("total_under_") :])
            except ValueError:
                continue
            try:
                markets_efektif[kunci] = stress_mod.p_under_digeser(cdf, garis, geser)
            except ValueError:
                continue
    dist_efektif = dict(dist_total)
    for kunci in _KUNCI_GESER_DIST:
        nilai = _angka(dist_total.get(kunci))
        if nilai is not None:
            dist_efektif[kunci] = nilai + geser
    return markets_efektif, dist_efektif


def _angka(nilai) -> float | None:
    """Ubah nilai jadi float; None bila bukan angka hingga (bool ditolak)."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    if not math.isfinite(nilai):
        return None
    return float(nilai)


def _peluang(nilai) -> float | None:
    """Ubah nilai jadi peluang 0-1; None bila bukan angka / di luar 0-1."""
    angka = _angka(nilai)
    if angka is None or not 0.0 <= angka <= 1.0:
        return None
    return angka


def _parse_waktu(nilai) -> datetime | None:
    """Parse ISO 8601 (dengan zona waktu) menjadi datetime; None bila gagal."""
    if not isinstance(nilai, str):
        return None
    try:
        parsed = datetime.fromisoformat(nilai)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _terdekat_waktu(items: list[dict], target, kunci_waktu: str) -> dict | None:
    """Pilih item yang waktunya (kunci_waktu, ISO) terdekat target.

    Sama seperti _closest_by_time di ingest/slate.py: pasangan tim yang
    sama bisa main dua kali (malam ini + rematch), jadi pasar yang
    expiration-nya terdekat dengan jam mulai laga inilah yang dipakai.
    Target tidak terbaca -> item berwaktu paling awal; tak ada item
    berwaktu -> item pertama. List kosong -> None.
    """
    if not items:
        return None
    target_dt = _parse_waktu(target)
    berwaktu = [
        (item, parsed)
        for item in items
        if (parsed := _parse_waktu(item.get(kunci_waktu))) is not None
    ]
    if target_dt is None:
        if berwaktu:
            return min(berwaktu, key=lambda pasangan: pasangan[1])[0]
        return items[0]
    if not berwaktu:
        return items[0]
    return min(berwaktu, key=lambda pasangan: abs(pasangan[1] - target_dt))[0]


def _validasi_argumen(
    home_tricode, away_tricode, game_date, seed, iterations
) -> tuple[str, str, str]:
    """Validasi + normalisasi argumen builder; ValueError bila tidak valid.

    Tricode dinormalisasi ke huruf besar (fetch_match_inputs juga
    melakukannya); tricode yang TIDAK DIKENAL bukan ValueError di sini —
    fetch yang akan gagal dan builder mengembalikan DATA_INCOMPLETE.
    """
    if not isinstance(home_tricode, str) or not home_tricode.strip():
        raise ValueError(f"home_tricode harus string tidak kosong: {home_tricode!r}")
    if not isinstance(away_tricode, str) or not away_tricode.strip():
        raise ValueError(f"away_tricode harus string tidak kosong: {away_tricode!r}")
    if not isinstance(game_date, str) or not _TANGGAL_RE.match(game_date):
        raise ValueError(f"game_date harus YYYY-MM-DD: {game_date!r}")
    try:
        datetime.strptime(game_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"game_date tidak valid: {game_date!r}") from exc
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"seed harus integer atau None: {seed!r}")
    if iterations is not None and (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < 1
    ):
        raise ValueError(f"iterations harus integer >= 1 atau None: {iterations!r}")
    return home_tricode.strip().upper(), away_tricode.strip().upper(), game_date


def _blok_cedera(inputs_data: dict) -> dict:
    """Rakit blok injuries artefak dari inputs nba_brain.

    n_sources = jumlah sumber cedera berbeda yang berhasil (entri
    sources data_kind 'nba_injuries'); confirmed_both = pemain
    OUT/DOUBTFUL yang dikonfirmasi >= 2 sumber di entri gabungnya.
    """
    entri: list[dict] = []
    for blok in (inputs_data.get("home") or {}, inputs_data.get("away") or {}):
        if isinstance(blok, dict):
            entri.extend(blok.get("injuries") or [])
    sumber: set[str] = set()
    for entri_sumber in inputs_data.get("sources") or []:
        if not isinstance(entri_sumber, dict):
            continue
        if entri_sumber.get("data_kind") == "nba_injuries":
            nama = entri_sumber.get("source")
            if isinstance(nama, str) and nama:
                sumber.add(nama)
    dikonfirmasi: list[str] = []
    konflik: list[dict] = []
    for cedera in entri:
        if not isinstance(cedera, dict):
            continue
        status = str(cedera.get("status") or "").upper()
        daftar_sumber = cedera.get("sources") or []
        if status in ("OUT", "DOUBTFUL") and len(daftar_sumber) >= 2:
            nama = cedera.get("player")
            if isinstance(nama, str) and nama:
                dikonfirmasi.append(nama)
        if isinstance(cedera.get("conflict"), dict):
            konflik.append(
                {
                    "player": cedera.get("player"),
                    "team_tricode": cedera.get("team_tricode"),
                    "statuses": cedera["conflict"],
                }
            )
    return {
        "sources": sorted(sumber),
        "n_sources": len(sumber),
        "confirmed_both": sorted(dikonfirmasi),
        "entries": entri,
        "conflicts": konflik,
        "fetched_at": inputs_data.get("fetched_at"),
    }


def _garis_volume_terbesar(entri_list: list[dict]) -> tuple[float | None, float | None]:
    """(garis, volume) entri dengan volume_usd terbesar; (None, None) bila tak ada."""
    terbaik: dict | None = None
    for entri in entri_list:
        if not isinstance(entri, dict):
            continue
        garis = _angka(entri.get("line"))
        volume = _angka(entri.get("volume_usd"))
        if garis is None or volume is None:
            continue
        if terbaik is None or volume > terbaik["volume_usd"]:
            terbaik = {"line": garis, "volume_usd": volume}
    if terbaik is None:
        return None, None
    return terbaik["line"], terbaik["volume_usd"]


def _moneyline_jup(slate_match) -> tuple[dict | None, str | None]:
    """Moneyline jup.ag dari entri MatchData 2b; (dict, None) atau (None, alasan).

    Kunci market_prices 'moneyline_home'/'moneyline_away' membawa
    jup_price_cents (lihat _market_key di ingest/slate.py). Kedua sisi
    harus ada — bila satu hilang, seluruh moneyline_jup null (kontrak
    memakai pasangan lengkap) + dicatat di missing.
    """
    if not isinstance(slate_match, dict):
        return None, "slate_match_tidak_ada"
    harga = slate_match.get("market_prices") or {}
    if not isinstance(harga, dict):
        return None, "moneyline_jup_tidak_ada"
    kandang = _angka((harga.get("moneyline_home") or {}).get("jup_price_cents"))
    tandang = _angka((harga.get("moneyline_away") or {}).get("jup_price_cents"))
    if kandang is None or tandang is None:
        return None, "moneyline_jup_tidak_ada"
    return (
        {
            "home_cents": kandang,
            "away_cents": tandang,
            "fetched_at": slate_match.get("fetched_at"),
        },
        None,
    )


def _p_market_kalshi(
    markets: list[dict] | None,
    home_tricode: str,
    away_tricode: str,
    line: float,
    start_time: str | None,
) -> float | None:
    """Peluang Under dari Kalshi pada garis yang SAMA PERSIS, atau None.

    Kalshi hanya punya pasar Over untuk total — Under adalah komplemen
    (1 - p_over) dari pasar Over yang sama (identitas pasar biner,
    sama seperti slate.py). Garis harus sama persis (aturan pembanding
    2b); garis Kalshi NBA adalah bilangan bulat (langkah 2 poin)
    sedangkan tangga Polymarket .5, jadi kecocokan eksak jarang — itu
    keadaan jujur MODEL_ONLY, bukan alasan interpolasi. Bila pasangan
    tim yang sama muncul dua kali (rematch), dipilih yang
    expiration_time-nya terdekat jam mulai laga.
    """
    if markets is None:
        return None
    cocok: list[dict] = []
    for pasar in markets:
        if not isinstance(pasar, dict):
            continue
        if str(pasar.get("side") or "").lower() != "over":
            continue
        if _angka(pasar.get("line")) != line:
            continue
        if not (
            matching_mod.teams_match(
                str(pasar.get("home_team") or ""), home_tricode, "nba"
            )
            and matching_mod.teams_match(
                str(pasar.get("away_team") or ""), away_tricode, "nba"
            )
        ):
            continue
        cocok.append(pasar)
    if not cocok:
        return None
    dipilih = _terdekat_waktu(cocok, start_time, "expiration_time")
    if dipilih is None:
        return None
    try:
        p_over = kalshi_mod.kalshi_probability(dipilih)
    except (ValueError, TypeError):
        return None
    p_under = _peluang(1.0 - p_over)
    return p_under


# ---------------------------------------------------------------------------
# Helper Tahap 4 (bantalan adaptif + penilaian wajar + harga minimum).
# ---------------------------------------------------------------------------


def _muat_analis():
    """Muat engine.analis (pekerja A); None bila modul belum tersedia.

    Modul yang belum ada (find_spec None) adalah keadaan operasional
    yang sah selama integrasi paralel — pemanggil memperlakukannya
    sebagai bantalan tidak tersedia (fail-closed), bukan error.
    Modul yang ADA tapi gagal diimpor (ImportError di dalamnya)
    DIBIARKAN raise: itu bug kode, bukan data hilang, dan jaring
    pengaman build_nba_analysis akan mengubahnya jadi artefak
    DATA_INCOMPLETE dengan kesalahan_internal tercatat.
    """
    modul = sys.modules.get("engine.analis")
    if modul is not None:
        return modul
    try:
        if importlib.util.find_spec("engine.analis") is None:
            return None
    except (ImportError, ValueError):
        return None
    from engine import analis as analis_mod

    return analis_mod


def _total_rata_tim(blok_tim: dict) -> float | None:
    """Rata-rata total poin (cetak + kebobolan) satu tim semusim.

    Dari home_record + road_record (ppg/opp_ppg, dibobot jumlah laga
    w+l tiap rekor). None bila tidak ada rekor yang bisa dipakai —
    jangan ditebak dari satu rekor saja.
    """
    total_terbobot = 0.0
    total_laga = 0
    for kunci in ("home_record", "road_record"):
        rekor = blok_tim.get(kunci)
        if not isinstance(rekor, dict):
            continue
        menang = rekor.get("w")
        kalah = rekor.get("l")
        if (
            isinstance(menang, bool)
            or isinstance(kalah, bool)
            or not isinstance(menang, int)
            or not isinstance(kalah, int)
        ):
            continue
        laga = menang + kalah
        ppg = _angka(rekor.get("ppg"))
        opp_ppg = _angka(rekor.get("opp_ppg"))
        if laga <= 0 or ppg is None or opp_ppg is None:
            continue
        total_terbobot += laga * (ppg + opp_ppg)
        total_laga += laga
    if total_laga <= 0:
        return None
    return total_terbobot / total_laga


def stats_laga_untuk_analis(inputs_data: dict) -> dict:
    """Statistik laga untuk analis.bantalan_adaptif (kontrak bersama).

    Mengembalikan {"ortg_home", "ortg_away", "ortg_liga_rata",
    "total_rata_5laga", "total_rata_musim"}; yang tidak tersedia diisi
    None, JANGAN ditebak.
      - ortg_home/ortg_away: off_rtg MUSIM (stats_season) tiap tim —
        pilihan wiring Tahap 4: angka musim penuh lebih stabil
        daripada last10; analis yang menilai (koordinator boleh
        mengubah pilihan ini bila analis meminta last10).
      - ortg_liga_rata: inputs["league"]["avg_off_rtg"] (rata-rata
        liga dari nba_brain; BUKAN dari simulasi).
      - total_rata_5laga: rata-rata (pts + opp_pts) semua laga form5
        kedua tim (maks 10 laga); None bila tidak ada laga yang bisa
        dipakai.
      - total_rata_musim: rata-rata total_rata_tim kedua tim (ppg +
        opp_ppg semusim, dibobot laga kandang+tandang); None bila
        salah satu tim tidak punya rekor yang bisa dipakai.
    """
    home = inputs_data.get("home")
    away = inputs_data.get("away")
    home = home if isinstance(home, dict) else {}
    away = away if isinstance(away, dict) else {}
    liga = inputs_data.get("league")
    liga = liga if isinstance(liga, dict) else {}

    def _off_rtg_musim(blok: dict) -> float | None:
        musim = blok.get("stats_season")
        if not isinstance(musim, dict):
            return None
        return _angka(musim.get("off_rtg"))

    total_5laga: list[float] = []
    for blok in (home, away):
        form5 = blok.get("form5")
        if not isinstance(form5, list):
            continue
        for laga in form5:
            if not isinstance(laga, dict):
                continue
            pts = _angka(laga.get("pts"))
            opp_pts = _angka(laga.get("opp_pts"))
            if pts is not None and opp_pts is not None:
                total_5laga.append(pts + opp_pts)
    total_musim_home = _total_rata_tim(home)
    total_musim_away = _total_rata_tim(away)
    return {
        "ortg_home": _off_rtg_musim(home),
        "ortg_away": _off_rtg_musim(away),
        "ortg_liga_rata": _angka(liga.get("avg_off_rtg")),
        "total_rata_5laga": (
            sum(total_5laga) / len(total_5laga) if total_5laga else None
        ),
        "total_rata_musim": (
            (total_musim_home + total_musim_away) / 2.0
            if total_musim_home is not None and total_musim_away is not None
            else None
        ),
    }


def peluang_under_dari_markets(markets_sim: dict) -> dict:
    """Konversi markets sim -> {garis: P(Under)} untuk cushion.

    cushion.utama_line/insurance_line menerima peluang_under sebagai
    dict GARIS (float) -> probabilitas 0-1, BUKAN dict markets mentah
    (kunci string "total_under_<garis>" + moneyline + total_over).
    Hanya kunci "total_under_<garis>" yang dipakai; garis diparse
    jadi float, peluang divalidasi 0-1. Kunci malformed / peluang
    tidak valid DILEWATI (bukan error) — cushion memakai interpolasi
    persentil bila garis tak ada, dan kaki gagal via p_model None di
    _rakit_kaki bila kuncinya memang hilang.
    """
    hasil: dict[float, float] = {}
    if not isinstance(markets_sim, dict):
        return hasil
    for kunci, nilai in markets_sim.items():
        if not isinstance(kunci, str) or not kunci.startswith("total_under_"):
            continue
        try:
            garis = float(kunci[len("total_under_") :])
        except ValueError:
            continue
        peluang = _peluang(nilai)
        if peluang is not None:
            hasil[garis] = peluang
    return hasil


def baca_harga_min(cfg: dict, kunci: str) -> tuple[float, str]:
    """Baca analis.<kunci> (harga minimum kaki, sen) dari config.

    Mengembalikan (nilai, sumber) dengan sumber "config" bila kunci
    ada, "default" bila belum ada (pekerja A belum menambahkan —
    dipakai DEFAULT_HARGA_MIN_CENTS = nilai kontrak 75¢). Nilai yang
    ada divalidasi (0 < v < 100); tidak valid -> ValueError.
    Pola yang sama dengan _baca_param_baru di engine/cushion.py.
    """
    section = cfg.get("analis", {})
    if not isinstance(section, dict) or kunci not in section:
        return DEFAULT_HARGA_MIN_CENTS, "default"
    nilai = section[kunci]
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or not 0.0 < nilai < 100.0
    ):
        raise ValueError(f"analis.{kunci} tidak valid: {nilai!r} (harus angka 0-100)")
    return float(nilai), "config"


def _hasil_cushion_gagal(alasan: str) -> dict:
    """Hasil cushion meets=False untuk kaki fail-closed (bantalan None).

    Bentuknya sama dengan hasil cushion yang tidak memenuhi (semua
    kunci yang dibaca _rakit_kaki ada, bernilai None) supaya kaki
    tetap dirakit dengan alasan tercatat.
    """
    return {
        "line": None,
        "meets": False,
        "reason": alasan,
        "price_cents": None,
        "jup_estimated_cents": None,
        "cushion_vs_market_points": None,
        "cushion_vs_median_points": None,
        "volume_usd": None,
        "thin": None,
        "liquidity": None,
        "bid_cents": None,
        "ask_cents": None,
        "climb": None,
    }


def _analisis_wajar_tidak_terverifikasi(
    acuan_sim,
    garis_market,
    garis_harga,
    harga_cents,
    bantalan_dibutuhkan_poin,
    penjelasan: str,
) -> dict:
    """Dict analisis_wajar penilaian 'tidak_terverifikasi' (kontrak).

    Dipakai bila modul analis belum tersedia atau nilai_wajar gagal /
    mengembalikan bentuk yang tidak sah — angka yang ada tetap
    dicatat apa adanya (bukan ditebak), jarak_poin dihitung bila
    acuan + garis harga tersedia, else None.
    """
    acuan = _angka(acuan_sim)
    garis = _angka(garis_harga)
    jarak = round(garis - acuan, 9) if acuan is not None and garis is not None else None
    return {
        "acuan_sim": acuan,
        "garis_market": _angka(garis_market),
        "garis_harga": garis,
        "harga_cents": _angka(harga_cents),
        "jarak_poin": jarak,
        "bantalan_dibutuhkan_poin": _angka(bantalan_dibutuhkan_poin),
        "penilaian": "tidak_terverifikasi",
        "penjelasan": penjelasan,
    }


def _analisis_wajar_sah(nilai) -> bool:
    """Hasil nilai_wajar sah vs kontrak skema? (8 kunci + jenis benar).

    Validasi ketat di sini penting: hasil tak sah yang lolos akan
    menggagalkan validasi SELURUH artefak di _finalisasi (artefak
    minimal) — lebih baik jatuh ke 'tidak_terverifikasi'.
    """
    if not isinstance(nilai, dict):
        return False
    for kunci in (
        "acuan_sim",
        "garis_market",
        "garis_harga",
        "harga_cents",
        "jarak_poin",
        "bantalan_dibutuhkan_poin",
    ):
        if kunci not in nilai:
            return False
        angka = nilai[kunci]
        if angka is not None and _angka(angka) is None:
            return False
    if nilai.get("penilaian") not in _PENILAIAN_WAJAR:
        return False
    return isinstance(nilai.get("penjelasan"), str)


def _sanitasi_climb(nilai):
    """Climb dari hasil cushion: hanya bool/angka-hingga/dict yang lolos.

    Bentuk climb adalah wewenang cushion (pekerja A); wiring hanya
    meneruskannya apa adanya bila jenisnya dikenal skema, else None
    supaya artefak tidak gagal validasi karena nilai tak terduga.
    """
    if nilai is None or isinstance(nilai, (bool, dict)):
        return nilai
    if isinstance(nilai, (int, float)) and math.isfinite(nilai):
        return nilai
    return None


def _rakit_kaki(
    ticket: str,
    hasil_cushion: dict,
    markets_sim: dict,
    kalshi_markets: list[dict] | None,
    home_tricode: str,
    away_tricode: str,
    match_id: str,
    start_time: str | None,
    cfg: dict,
    generated_at: str,
    hasil_bantalan: dict | None = None,
) -> dict:
    """Rakit satu leg Alt Under dari hasil cushion + sim + Kalshi.

    Kaki meets=false tetap dirakit (line null, leg_id '...:total_under_
    none:<ticket>') supaya keberadaannya tercatat dengan alasan.
    Tahap 4: cushion_points/cushion_reason dari hasil_bantalan
    (analis.bantalan_adaptif; None bila bantalan tidak tersedia);
    volume_usd/thin/climb dari hasil_cushion (None bila cushion
    tidak membawanya — mis. kaki fail-closed). v18 (revisi
    koordinator): liquidity_usd/bid_cents/ask_cents juga dari
    hasil_cushion (bukti gate eksekusi — dipakai komposer).
    """
    garis = _angka(hasil_cushion.get("line"))
    leg_id = (
        f"{match_id}:total_under_{garis:g}:{ticket}"
        if garis is not None
        else f"{match_id}:total_under_none:{ticket}"
    )
    p_model = None
    if garis is not None:
        p_model = _peluang(markets_sim.get(f"total_under_{garis:g}"))
    p_market = None
    sumber_pembanding = None
    if garis is not None and kalshi_markets is not None:
        p_market = _p_market_kalshi(
            kalshi_markets, home_tricode, away_tricode, garis, start_time
        )
        if p_market is not None:
            sumber_pembanding = "kalshi"
    p_final = None
    blend_gagal = False
    if p_model is not None:
        try:
            p_final = devig_mod.blend(p_model, p_market, cfg)["p_final"]
        except (ValueError, config_mod.ConfigError):
            # p_model/p_market sudah divalidasi 0-1 di atas; kegagalan
            # di sini berarti config blend rusak — kaki tidak memenuhi.
            blend_gagal = True
    harga_poly = _angka(hasil_cushion.get("price_cents"))
    harga_jup = _angka(hasil_cushion.get("jup_estimated_cents"))
    harga = harga_jup if harga_jup is not None else harga_poly
    ev_pct = None
    label = None
    if p_final is not None and harga is not None and 0.0 < harga < 100.0:
        ev_pct = (p_final * (100.0 / harga) - 1.0) * 100.0
        if math.isfinite(ev_pct):
            try:
                label = price_labels_mod.label_for_ev(ev_pct, cfg)
            except (ValueError, config_mod.ConfigError):
                label = None
        else:
            ev_pct = None
    meets_cushion = bool(hasil_cushion.get("meets"))
    meets = meets_cushion and p_model is not None and not blend_gagal
    if not meets_cushion:
        reason = hasil_cushion.get("reason")
    elif p_model is None:
        reason = "p_model_tidak_ada"
    elif blend_gagal:
        reason = "blend_gagal"
    else:
        reason = None
    # Tahap 4: field baru. cushion_points/cushion_reason dari analis
    # (sama untuk kedua kaki — satu bantalan adaptif per laga);
    # volume_usd/thin/climb dari hasil cushion.
    bantalan_poin = None
    bantalan_alasan = None
    if isinstance(hasil_bantalan, dict):
        bantalan_poin = _angka(hasil_bantalan.get("cushion_points"))
        alasan_mentah = hasil_bantalan.get("alasan")
        bantalan_alasan = alasan_mentah if isinstance(alasan_mentah, str) else None
    thin_mentah = hasil_cushion.get("thin")
    return {
        "leg_id": leg_id,
        "market_type": "total_under",
        "line": garis,
        "ticket": ticket,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": sumber_pembanding,
        "p_final": p_final,
        "price_cents": harga_poly,
        "jup_estimated_cents": harga_jup,
        "ev_pct": ev_pct,
        "price_label": label,
        "cushion_vs_median_points": _angka(
            hasil_cushion.get("cushion_vs_median_points")
        ),
        "cushion_vs_market_points": _angka(
            hasil_cushion.get("cushion_vs_market_points")
        ),
        "cushion_points": bantalan_poin,
        "cushion_reason": bantalan_alasan,
        "volume_usd": _angka(hasil_cushion.get("volume_usd")),
        "thin": thin_mentah if isinstance(thin_mentah, bool) else None,
        "liquidity_usd": _angka(hasil_cushion.get("liquidity")),
        "bid_cents": _angka(hasil_cushion.get("bid_cents")),
        "ask_cents": _angka(hasil_cushion.get("ask_cents")),
        "climb": _sanitasi_climb(hasil_cushion.get("climb")),
        "meets": meets,
        "reason": reason if isinstance(reason, str) else None,
        "fetched_at": generated_at,
    }


def _kumpulkan_anomali(
    legs: list[dict],
    median: float | None,
    main_line: float | None,
    cfg: dict,
) -> tuple[list[dict], list[str]]:
    """Kumpulkan anomali engine/anomaly.py (dideduplikasi) + kegagalan cek.

    Memakai check_total_line_vs_model (tingkat laga), lalu per kaki
    check_cushion_vs_market + check_under_safety (yang di dalamnya
    menjalankan dua cek pertama — duplikat dibuang berdasarkan isi)
    + check_model_vs_market dan check_jup_vs_market bila p_market ada.
    check_cushion_vs_market/check_under_safety memakai bantalan
    adaptif yang TERCATAT pada kaki (leg["cushion_points"], dari
    analis) — BUKAN lagi spread (signature baru anomaly.py Tahap 4).
    check_under_safety dipanggil dengan price_delta_cents=None: di
    analisis awal belum ada harga sebelumnya (snapshot pertama baru
    dibuat di artefak ini), jadi cek harga-melawan dilewati.
    """
    hasil: list[dict] = []
    gagal: list[str] = []

    def _tambah(anomali, leg_id: str | None) -> None:
        if anomali is None:
            return
        salinan = dict(anomali)
        salinan["leg_id"] = leg_id
        hasil.append(salinan)

    def _cek(nama: str, fungsi, *args, **kwargs):
        try:
            return fungsi(*args, **kwargs)
        except (ValueError, config_mod.ConfigError) as exc:
            gagal.append(f"anomali_{nama}_gagal: {exc}")
            return None

    _tambah(
        _cek(
            "total_line_vs_model",
            anomaly_mod.check_total_line_vs_model,
            median,
            main_line,
            cfg,
        ),
        None,
    )
    for leg in legs:
        garis = leg.get("line")
        leg_id = leg["leg_id"]
        bantalan_kaki = _angka(leg.get("cushion_points"))
        if garis is not None:
            _tambah(
                _cek(
                    "cushion_vs_market",
                    anomaly_mod.check_cushion_vs_market,
                    garis,
                    median,
                    main_line,
                    bantalan_kaki,
                ),
                leg_id,
            )
            hasil_aman = _cek(
                "under_safety",
                anomaly_mod.check_under_safety,
                leg.get("p_model"),
                median,
                main_line,
                garis,
                bantalan_kaki,
                None,
                cfg,
            )
            if isinstance(hasil_aman, dict):
                for anomali in hasil_aman.get("anomalies") or []:
                    _tambah(anomali, leg_id)
        if leg.get("p_market") is not None and leg.get("p_model") is not None:
            _tambah(
                _cek(
                    "model_vs_market",
                    anomaly_mod.check_model_vs_market,
                    leg["p_model"],
                    leg["p_market"],
                    cfg,
                ),
                leg_id,
            )
            harga = leg.get("jup_estimated_cents") or leg.get("price_cents")
            if harga is not None:
                _tambah(
                    _cek(
                        "jup_vs_market",
                        anomaly_mod.check_jup_vs_market,
                        harga,
                        leg["p_market"],
                        cfg,
                    ),
                    leg_id,
                )
    # Deduplikasi berdasarkan isi (tanpa leg_id): check_under_safety
    # mengulang cek garis/bantalan, dan dua kaki bisa memicu anomali
    # tingkat laga yang sama — kemunculan pertama yang dipertahankan.
    unik: list[dict] = []
    terlihat: set[str] = set()
    for anomali in hasil:
        isi = {kunci: nilai for kunci, nilai in anomali.items() if kunci != "leg_id"}
        kunci_dedup = json.dumps(isi, sort_keys=True, ensure_ascii=False)
        if kunci_dedup in terlihat:
            continue
        terlihat.add(kunci_dedup)
        unik.append(anomali)
    return unik, gagal


def build_nba_analysis(
    home_tricode: str,
    away_tricode: str,
    game_date: str,
    slate_match: dict | None = None,
    start_time: str | None = None,
    cfg: dict | None = None,
    client=None,
    seed: int | None = None,
    iterations: int | None = None,
) -> dict:
    """Bangun artefak analisis NBA satu laga (format 'nba_analysis' v1).

    home_tricode/away_tricode: tricode tim ("ATL"/"DET"). game_date:
    tanggal Eastern "YYYY-MM-DD". slate_match: entri MatchData 2b laga
    ini (untuk moneyline jup.ag; None = moneyline_jup null + dicatat).
    start_time: jam mulai laga (ISO, dari slate); bila None, dipakai
    slate_match["start_time"] bila ada. cfg: dict playstyle (None =
    baca playstyle.yaml). client: HttpClient bersama (opsional).
    seed/iterations: diteruskan ke nba_sim.simulate (None = default
    config; tes memakai iterations kecil).

    Fail-closed: kegagalan tiap tahap -> artefak DATA_INCOMPLETE
    (data tahap yang berhasil tetap terlampir) + missing + error
    tercatat. TIDAK PERNAH raise, kecuali argumen input tidak valid
    (ValueError). TIDAK PERNAH memanggil Odds API.
    """
    home, away, tanggal = _validasi_argumen(
        home_tricode, away_tricode, game_date, seed, iterations
    )
    match_id = f"{away}@{home}_{tanggal}"
    start_efektif = start_time
    if start_efektif is None and isinstance(slate_match, dict):
        start_efektif = slate_match.get("start_time")
    if not isinstance(start_efektif, str):
        start_efektif = None
    try:
        return _build_nba_analysis(
            home,
            away,
            tanggal,
            match_id,
            slate_match,
            start_efektif,
            cfg,
            client,
            seed,
            iterations,
        )
    except Exception as exc:  # noqa: BLE001 - jaring pengaman terakhir
        return minimal_nba_analysis(
            match_id,
            home,
            away,
            tanggal,
            [f"kesalahan_internal:{type(exc).__name__}: {exc}"],
            start_time=start_efektif,
        )


def _build_nba_analysis(
    home: str,
    away: str,
    tanggal: str,
    match_id: str,
    slate_match: dict | None,
    start_time: str | None,
    cfg: dict | None,
    client,
    seed: int | None,
    iterations: int | None,
) -> dict:
    """Pipeline builder (dipanggil build_nba_analysis; lihat docstringnya)."""
    generated_at = now_iso()
    missing: list[str] = []
    artefak: dict = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "match_id": match_id,
        "home_tricode": home,
        "away_tricode": away,
        "game_date": tanggal,
        "start_time": start_time,
        "generated_at": generated_at,
        "status": "DATA_INCOMPLETE",
        "missing": missing,
        "sources": [],
        "inputs": None,
        "simulation": None,
        "market": None,
        "legs": [],
        "injuries": {
            "sources": [],
            "n_sources": 0,
            "confirmed_both": [],
            "entries": [],
            "conflicts": [],
            "fetched_at": None,
        },
        "anomalies": [],
        "price_snapshots": {},
        "news": {
            "status": "gagal",
            "items": [],
            "sources": [],
            "fetched_at": None,
            "error": "tidak_diambil",
        },
    }

    def _gagal() -> dict:
        """Finalisasi artefak DATA_INCOMPLETE (validasi skema dulu)."""
        artefak["status"] = "DATA_INCOMPLETE"
        return _finalisasi(artefak)

    # Config (None = baca playstyle.yaml).
    try:
        cfg_efektif = cfg if cfg is not None else config_mod.load_playstyle()
    except Exception as exc:  # noqa: BLE001 - config gagal = tahap gagal
        missing.append(f"config_gagal: {type(exc).__name__}: {exc}")
        return _gagal()

    # Tahap 1: input Otak NBA.
    try:
        hasil_inputs = nba_brain_mod.fetch_match_inputs(
            home_tricode=home, away_tricode=away, game_date=tanggal, client=client
        )
    except Exception as exc:  # noqa: BLE001 - fetch tidak boleh mematikan builder
        missing.append(f"inputs_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    if not hasil_inputs.ok or not isinstance(hasil_inputs.data, dict):
        missing.append(f"inputs_gagal: {hasil_inputs.error or 'tidak diketahui'}")
        return _gagal()
    inputs_data = hasil_inputs.data
    artefak["inputs"] = inputs_data
    missing.extend(str(item) for item in inputs_data.get("missing") or [])
    for entri_sumber in inputs_data.get("sources") or []:
        if not isinstance(entri_sumber, dict):
            continue
        kind = entri_sumber.get("data_kind")
        sumber = entri_sumber.get("source")
        tier = entri_sumber.get("tier")
        waktu = entri_sumber.get("fetched_at")
        if (
            isinstance(kind, str)
            and isinstance(sumber, str)
            and isinstance(tier, int)
            and not isinstance(tier, bool)
            and isinstance(waktu, str)
        ):
            artefak["sources"].append(
                {"kind": kind, "source": sumber, "tier": tier, "time": waktu}
            )
    artefak["injuries"] = _blok_cedera(inputs_data)

    # Tahap 1b (v18): timing gate TUNGGU_LINEUP — dievaluasi setelah
    # data cedera ada. Bila tunggu=True, analisis DILANJUTKAN sebagai
    # draf (sim + kaki tetap dihitung) tapi status akhir dipaksa HOLD
    # (lihat akhir builder) supaya komposer tidak memakai laga ini
    # sampai recheck memperbarui statusnya. Blok disimpan di root
    # artefak["tunggu_lineup"] (properti opsional skema v18).
    tunggu_lineup_aktif = False
    blok_tunggu, tunggu_lineup_aktif, catatan_tunggu = _blok_tunggu_lineup(
        artefak, cfg_efektif
    )
    if blok_tunggu is not None:
        artefak["tunggu_lineup"] = blok_tunggu
    if catatan_tunggu is not None:
        missing.append(catatan_tunggu)
    if tunggu_lineup_aktif:
        bintang_tunggu = ", ".join(blok_tunggu.get("bintang") or [])
        missing.append(
            "tunggu_lineup: "
            + (f"bintang Questionable ({bintang_tunggu}) — " if bintang_tunggu else "")
            + "analisis ini draf; komposer tidak memakai laga ini "
            "sampai status diperbarui recheck"
        )

    # Tahap 2: tangga Polymarket (harga venue).
    try:
        slug = polymarket_mod.nba_slug(away, home, tanggal)
    except ValueError as exc:
        missing.append(f"slug_gagal: {exc}")
        return _gagal()
    try:
        hasil_tangga = polymarket_mod.fetch_event_by_slug(slug, client=client)
    except Exception as exc:  # noqa: BLE001 - fetch tidak boleh mematikan builder
        missing.append(f"tangga_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    if not hasil_tangga.ok or not isinstance(hasil_tangga.data, dict):
        missing.append(f"tangga_gagal: {hasil_tangga.error or 'tidak diketahui'}")
        return _gagal()
    try:
        tangga = polymarket_mod.parse_event_ladders(hasil_tangga.data, cfg_efektif)
    except Exception as exc:  # noqa: BLE001 - parse gagal = tahap gagal
        missing.append(f"parse_tangga_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    totals = tangga.get("totals") or []
    spreads = tangga.get("spreads") or []
    entri_under = [
        entri
        for entri in totals
        if isinstance(entri, dict)
        and str(entri.get("side") or "").lower() == "under"
        and _angka(entri.get("line")) is not None
    ]
    if not entri_under:
        missing.append("tangga_under_kosong")
        return _gagal()
    main_line, main_volume = _garis_volume_terbesar(totals)
    spread_line, _spread_volume = _garis_volume_terbesar(spreads)
    spread_abs = abs(spread_line) if spread_line is not None else None
    if spread_abs is None:
        missing.append("spread_tidak_diketahui")
    moneyline, alasan_ml = _moneyline_jup(slate_match)
    if alasan_ml is not None:
        missing.append(alasan_ml)
    artefak["market"] = {
        "slug": slug,
        "main_total_line": main_line,
        "main_total_volume_usd": main_volume,
        "ladder_fetched_at": hasil_tangga.fetched_at,
        "ladder_warnings": list(tangga.get("warnings") or []),
        "moneyline_jup": moneyline,
        "totals": totals,
        "spreads": spreads,
    }
    artefak["sources"].append(
        {
            "kind": "polymarket_ladder",
            "source": polymarket_mod.SOURCE,
            "tier": polymarket_mod.TIER,
            "time": hasil_tangga.fetched_at,
        }
    )

    # Tahap 2b (v18): veto rim protector + SHORT-CIRCUIT. Dievaluasi
    # setelah Tahap 2 karena butuh garis pasar (Tahap 2) + cedera +
    # pace (Tahap 1). Hasil veto disimpan di root artefak["veto"]
    # untuk SEMUA laga (menyala atau tidak — properti opsional skema
    # v18). Bila veto MENYALA: lewati Tahap 3 (simulasi), 5 (Kalshi),
    # 5b (news), 5c (setan) — artefak tetap ditulis dengan status
    # DATA_INCOMPLETE + blok veto + alasan jelas (laga kena veto,
    # tidak dianalisis lebih lanjut). Vonis KUNING-nya dihitung
    # on-demand oleh nilai_vonis (pemicu keras veto); missing mencatat
    # penandanya. Scan jup.ag TIDAK terpangkas (slate-level — lihat
    # docstring modul).
    blok_veto, catatan_veto = _blok_veto(artefak, cfg_efektif)
    artefak["veto"] = blok_veto
    if catatan_veto is not None:
        missing.append(catatan_veto)
    if blok_veto.get("menyala"):
        alasan_veto = "; ".join(blok_veto.get("alasan") or []) or (
            "veto rim protector menyala"
        )
        missing.append(f"veto_short_circuit: {alasan_veto}")
        missing.append(
            "vonis_kuning: veto_rim_protector — laga kena veto, "
            "tidak dianalisis lebih lanjut (simulasi/Kalshi/news/"
            "setan dilewati)"
        )
        return _gagal()

    # Tahap 3: simulasi dua pass (median dari pass 1, garis dari tangga).
    garis_under = sorted({_angka(e["line"]) for e in entri_under})
    try:
        sim1 = nba_sim_mod.simulate(
            inputs_data, cfg=cfg_efektif, seed=seed, iterations=iterations
        )
    except Exception as exc:  # noqa: BLE001 - sim gagal = DATA_INCOMPLETE
        missing.append(f"simulasi_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    dist_total_1 = (sim1.get("score_distribution") or {}).get("total") or {}
    median = _angka(dist_total_1.get("median"))
    if median is None:
        missing.append("simulasi_tanpa_median_total")
        return _gagal()
    garis_sim = sorted(set(garis_under) | {median})
    try:
        sim2 = nba_sim_mod.simulate(
            inputs_data,
            cfg=cfg_efektif,
            lines={"totals": garis_sim},
            seed=seed,
            iterations=iterations,
        )
    except Exception as exc:  # noqa: BLE001 - sim gagal = DATA_INCOMPLETE
        missing.append(f"simulasi_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    galat_sim = _validasi_simulasi(sim2)
    if galat_sim is not None:
        missing.append(f"simulasi_tidak_valid: {galat_sim}")
        return _gagal()
    artefak["simulation"] = sim2
    markets_sim = sim2.get("markets") or {}
    dist_total = (sim2.get("score_distribution") or {}).get("total") or {}

    # Tahap 3b (v18): Vegas shrinkage — sesuaikan median ke arah
    # pasar SETELAH sim. Bila diterapkan, distribusi EFEKTIF (geser
    # kaku: kuantil + P Under digeser sebesar geser) menjadi distribusi
    # KANONIK artefak: simulation.markets +
    # simulation.score_distribution.total DIGANTI dengan yang efektif,
    # sehingga vonis/equilibrium/skip/komposer (yang membaca artefak)
    # semuanya melihat CDF yang sudah disesuaikan — sesuai brief v18
    # item 8 ("SEBELUM vonis + equilibrium"). Distribusi mentah TIDAK
    # hilang: tersimpan di simulation.markets_mentah +
    # score_distribution.total_mentah (bukti/audit) + blok root
    # "vegas" (median_mentah/median_baru/geser/alasan). Bila tidak
    # diterapkan / modul belum ada, efektif == mentah (tidak ada
    # kunci _mentah; blok vegas tetap ditulis bila infonya ada).
    vegas_info, catatan_vegas = _terapkan_vegas(median, main_line, cfg_efektif, artefak)
    if catatan_vegas is not None:
        missing.append(catatan_vegas)
    if vegas_info is not None:
        artefak["vegas"] = vegas_info
    median_efektif = median
    markets_efektif = markets_sim
    dist_total_efektif = dist_total
    if (
        vegas_info is not None
        and vegas_info.get("diterapkan")
        and vegas_info.get("median_baru") is not None
        and vegas_info.get("geser") is not None
    ):
        median_efektif = float(vegas_info["median_baru"])
        markets_efektif, dist_total_efektif = _geser_distribusi(
            markets_sim, dist_total, float(vegas_info["geser"])
        )
        # Tukarkan distribusi kanonik artefak ke yang efektif;
        # mentah dipertahankan sebagai bukti (salinan _geser_distribusi
        # tidak mengubah dict mentah — markets_sim/dist_total masih asli).
        sim2["markets_mentah"] = markets_sim
        sim2["markets"] = markets_efektif
        dist_sim = sim2.get("score_distribution")
        if isinstance(dist_sim, dict):
            dist_sim["total_mentah"] = dist_total
            dist_sim["total"] = dist_total_efektif

    # Tahap 4: bantalan adaptif DULU, lalu Utama, lalu
    # Asuransi di atas Utama. Bila bantalan adaptif None (data tidak
    # lengkap / modul analis belum tersedia) -> kedua kaki fail-closed
    # dengan alasan tercatat, TANPA fallback ke +8.
    stats_laga = stats_laga_untuk_analis(inputs_data)
    analis_mod = _muat_analis()
    hasil_bantalan = None
    alasan_bantalan = None
    if analis_mod is None:
        alasan_bantalan = "analis_belum_tersedia"
    else:
        try:
            hasil_bantalan = analis_mod.bantalan_adaptif(
                stats_laga, dist_total_efektif, cfg_efektif
            )
        except Exception as exc:  # noqa: BLE001 - analis gagal = kaki gagal
            alasan_bantalan = f"bantalan_adaptif_gagal: {type(exc).__name__}"
            hasil_bantalan = None
        if hasil_bantalan is not None:
            if (
                not isinstance(hasil_bantalan, dict)
                or _angka(hasil_bantalan.get("cushion_points")) is None
            ):
                alasan_bantalan = "bantalan_adaptif_hasil_tidak_valid"
                hasil_bantalan = None
        elif alasan_bantalan is None:
            alasan_bantalan = "bantalan_adaptif_tidak_tersedia"
    if hasil_bantalan is None:
        missing.append(f"bantalan_adaptif: {alasan_bantalan}")
        hasil_utama = _hasil_cushion_gagal(alasan_bantalan)
        hasil_asuransi = _hasil_cushion_gagal(alasan_bantalan)
    else:
        try:
            harga_min_utama, _sumber_min_utama = baca_harga_min(
                cfg_efektif, "harga_min_utama_cents"
            )
            harga_min_asuransi, _sumber_min_asuransi = baca_harga_min(
                cfg_efektif, "harga_min_asuransi_cents"
            )
            # Utama DULU (signature baru, tanpa spread), lalu Asuransi
            # di atas garis Utama. peluang_under dikonversi dari
            # markets EFEKTIF (pasca-Vegas, Tahap 3b) ke
            # {garis: P(Under)} (kontrak cushion); dist_total yang
            # dipakai juga EFEKTIF.
            peluang_under = peluang_under_dari_markets(markets_efektif)
            hasil_utama = cushion_mod.utama_line(
                dist_total_efektif,
                main_line,
                entri_under,
                cfg=cfg_efektif,
                cushion_points=_angka(hasil_bantalan["cushion_points"]),
                peluang_under=peluang_under,
                harga_min_cents=harga_min_utama,
            )
            garis_utama = _angka(hasil_utama.get("line"))
            hasil_asuransi = cushion_mod.insurance_line(
                dist_total_efektif,
                main_line,
                entri_under,
                cfg=cfg_efektif,
                garis_di_atas=garis_utama,
                peluang_under=peluang_under,
                harga_min_cents=harga_min_asuransi,
            )
        except (ValueError, config_mod.ConfigError, TypeError) as exc:
            # TypeError di sini berarti signature baru cushion belum
            # terpasang (cushion lama menolak kwarg baru) — JANGAN
            # fallback ke aturan lama; DATA_INCOMPLETE + alasan.
            missing.append(f"cushion_gagal: {exc}")
            return _gagal()

    # Tahap 5: pembanding Kalshi (gagal -> MODEL_ONLY, bukan DATA_INCOMPLETE).
    kalshi_markets: list[dict] | None = None
    try:
        hasil_kalshi = kalshi_mod.fetch_total_markets("nba", client=client)
    except Exception as exc:  # noqa: BLE001 - pembanding gagal != analisis gagal
        missing.append(f"kalshi_total_markets_gagal: {type(exc).__name__}: {exc}")
    else:
        if hasil_kalshi.ok and isinstance(hasil_kalshi.data, list):
            kalshi_markets = hasil_kalshi.data
            artefak["sources"].append(
                {
                    "kind": "kalshi_total_markets",
                    "source": kalshi_mod.SOURCE,
                    "tier": kalshi_mod.TIER,
                    "time": hasil_kalshi.fetched_at,
                }
            )
        else:
            missing.append(
                f"kalshi_total_markets_gagal: {hasil_kalshi.error or 'tidak diketahui'}"
            )

    # Tahap 5b: berita (KONTEKS, bukan angka — gagal -> blok news
    # status "gagal" + missing, artefak tetap jalan seperti Kalshi).
    try:
        hasil_news = news_nba_mod.fetch_news_nba(
            home_tricode=home,
            away_tricode=away,
            game_date=tanggal,
            client=client,
            cfg=cfg_efektif,
        )
    except Exception as exc:  # noqa: BLE001 - berita gagal != analisis gagal
        artefak["news"] = {
            "status": "gagal",
            "items": [],
            "sources": [],
            "fetched_at": generated_at,
            "error": f"{type(exc).__name__}: {exc}",
        }
        missing.append(f"news_gagal: {type(exc).__name__}: {exc}")
    else:
        artefak["news"] = _blok_news(hasil_news)
        if artefak["news"]["status"] == "gagal":
            missing.append(f"news_gagal: {artefak['news']['error']}")
        elif hasil_news.ok:
            artefak["sources"].append(
                {
                    "kind": "nba_news",
                    "source": news_nba_mod.SOURCE,
                    "tier": news_nba_mod.TIER,
                    "time": hasil_news.fetched_at,
                }
            )

    # Tahap 5c: setan per pemain (KONTEKS stress — gagal -> blok
    # setan_pemain status "gagal" + missing, artefak tetap jalan;
    # skenario_panas fallback ke setan umum bila blok tidak ada/ok).
    # Median yang dipakai adalah EFEKTIF (pasca-Vegas, Tahap 3b).
    artefak["setan_pemain"] = _blok_setan_pemain(
        home,
        away,
        median_efektif,
        main_line,
        artefak,
        cfg_efektif,
        generated_at,
        tanggal,
    )
    if artefak["setan_pemain"]["status"] == "gagal":
        missing.append(f"setan_pemain_gagal: {artefak['setan_pemain']['error']}")
    elif artefak["setan_pemain"]["status"] == "ok":
        artefak["sources"].append(
            {
                "kind": "nba_pemain_3p",
                "source": (
                    artefak["setan_pemain"]["sources"][0]
                    if artefak["setan_pemain"]["sources"]
                    else "stats.nba.com"
                ),
                "tier": artefak["setan_pemain"].get("tier") or 2,
                "time": artefak["setan_pemain"]["fetched_at"],
            }
        )

    legs = [
        _rakit_kaki(
            "insurance",
            hasil_asuransi,
            markets_efektif,
            kalshi_markets,
            home,
            away,
            match_id,
            start_time,
            cfg_efektif,
            generated_at,
            hasil_bantalan,
        ),
        _rakit_kaki(
            "main",
            hasil_utama,
            markets_efektif,
            kalshi_markets,
            home,
            away,
            match_id,
            start_time,
            cfg_efektif,
            generated_at,
            hasil_bantalan,
        ),
    ]
    artefak["legs"] = legs
    for leg in legs:
        garis = leg.get("line")
        harga = leg.get("jup_estimated_cents")
        if harga is None:
            harga = leg.get("price_cents")
        if garis is not None and harga is not None:
            artefak["price_snapshots"][f"total_under_{garis:g}"] = {
                "cents": harga,
                "at": generated_at,
            }

    # Penilaian wajar (Tahap 4): acuan = median EFEKTIF (pasca-Vegas),
    # garis + harga jup kaki Utama, bantalan yang dibutuhkan =
    # bantalan adaptif. Bila analis belum tersedia / nilai_wajar
    # gagal / hasilnya tidak sah -> "tidak_terverifikasi" dengan
    # angka yang ada tetap dicatat.
    kaki_utama = legs[1]
    harga_utama = _angka(kaki_utama.get("jup_estimated_cents"))
    if harga_utama is None:
        harga_utama = _angka(kaki_utama.get("price_cents"))
    bantalan_dibutuhkan = (
        _angka(hasil_bantalan.get("cushion_points"))
        if isinstance(hasil_bantalan, dict)
        else None
    )
    analisis_wajar = None
    if analis_mod is not None:
        try:
            analisis_wajar = analis_mod.nilai_wajar(
                acuan_sim=median_efektif,
                garis_market=main_line,
                garis_harga=_angka(kaki_utama.get("line")),
                harga_cents=harga_utama,
                bantalan_dibutuhkan_poin=bantalan_dibutuhkan,
                cfg=cfg_efektif,
            )
        except Exception:  # noqa: BLE001 - nilai_wajar gagal = tidak terverifikasi
            analisis_wajar = None
    if not _analisis_wajar_sah(analisis_wajar):
        if analis_mod is None:
            penjelasan = (
                "Modul analis belum tersedia, jadi kewajaran harga belum bisa dinilai."
            )
        elif bantalan_dibutuhkan is None:
            penjelasan = (
                "Bantalan adaptif tidak tersedia, jadi kewajaran harga "
                "belum bisa dinilai."
            )
        else:
            penjelasan = (
                "Penilaian wajar gagal dihitung, jadi kewajaran harga "
                "belum bisa dinilai."
            )
        analisis_wajar = _analisis_wajar_tidak_terverifikasi(
            median_efektif,
            main_line,
            kaki_utama.get("line"),
            harga_utama,
            bantalan_dibutuhkan,
            penjelasan,
        )
    # Vegas (Tahap 3b): median yang disesuaikan + geser + alasan
    # disimpan di analisis_wajar (kunci opsional — cermin dari blok
    # root "vegas" untuk bagian penilaian wajar; median mentah ada di
    # blok root "vegas" + simulation.markets_mentah /
    # score_distribution.total_mentah sebagai bukti).
    if vegas_info is not None:
        analisis_wajar["median_disesuaikan"] = vegas_info.get("median_baru")
        analisis_wajar["median_mentah"] = vegas_info.get("median_mentah")
        analisis_wajar["geser_vegas"] = vegas_info.get("geser")
        analisis_wajar["vegas_diterapkan"] = bool(vegas_info.get("diterapkan"))
        analisis_wajar["vegas_alasan"] = vegas_info.get("alasan")
        analisis_wajar["vegas_sebab_cedera_baru"] = vegas_info.get("sebab_cedera_baru")
    artefak["analisis_wajar"] = analisis_wajar

    # Tahap 6: anomali (median EFEKTIF pasca-Vegas).
    anomalies, gagal_anomali = _kumpulkan_anomali(
        legs, median_efektif, main_line, cfg_efektif
    )
    artefak["anomalies"] = anomalies
    missing.extend(gagal_anomali)

    # Status akhir. TUNGGU_LINEUP (Tahap 1b) memaksa HOLD: draf
    # tetap dihitung, tapi komposer tidak memakai laga ini sampai
    # recheck memperbarui statusnya.
    asuransi = legs[0]
    b2_gagal = artefak["injuries"]["n_sources"] < 2
    if b2_gagal:
        missing.append("cedera_kurang_dari_2_sumber")
    if not asuransi["meets"]:
        alasan = asuransi.get("reason") or "tidak_memenuhi"
        missing.append(f"asuransi_tidak_memenuhi: {alasan}")
    artefak["status"] = (
        "HOLD" if (b2_gagal or not asuransi["meets"] or tunggu_lineup_aktif) else "OK"
    )
    return _finalisasi(artefak)


def _finalisasi(artefak: dict) -> dict:
    """Validasi artefak terhadap skema; bila tidak valid, artefak minimal.

    Artefak minimal mempertahankan match_id + missing (ditambah pesan
    validasi) supaya kegagalan validasi tidak menghilangkan jejak.
    """
    galat = validate_nba_analysis(artefak)
    if galat is None:
        return artefak
    return minimal_nba_analysis(
        artefak["match_id"],
        artefak["home_tricode"],
        artefak["away_tricode"],
        artefak["game_date"],
        [*artefak.get("missing", []), f"artefak_tidak_valid: {galat}"],
        start_time=artefak.get("start_time"),
    )
