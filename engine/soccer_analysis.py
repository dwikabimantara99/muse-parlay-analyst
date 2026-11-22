"""Penyambungan Otak Bola -> artefak analisis per laga (Tahap 3 Langkah 5).

Modul ini menyambungkan komponen Otak Bola (ingest.soccer_brain,
engine.football_sim Dixon-Coles, harga jup.ag dari slate 2b) menjadi
SATU artefak JSON per laga ("soccer_analysis", format_version 1) yang
dipakai cli.py analyze dan dikonsumsi engine/ticket_composer.py
(penegakan TANPA_XG), engine/qa.py, dan report/nba_report.py (render
bola).

KONTRAK ARTEFAK (format_version 1 — KONTRAK BERSAMA dengan composer/
qa/report, jangan diubah sepihak; lihat
schemas/soccer_analysis.schema.json):
  format/format_version/match_id/home_team/away_team/league/match_date/
  start_time/generated_at/status/missing/sources/inputs/simulation/
  market/legs/injuries/labels/fit_status/anomalies/price_snapshots.
  match_id = "{slug-away}@{slug-home}_{YYYY-MM-DD}".
  legs = 1X2 + O/U gol + BTTS; SEMUA kaki bertiket "main" (TANPA_XG
  dilarang masuk Asuransi, B4).

PIPELINE build_soccer_analysis:
  1. fetch_match_inputs (input otak) — gagal -> DATA_INCOMPLETE.
  2. Parameter fit Dixon-Coles: argumen fit_params, atau file
     out/fit_soccer_params.json (pekerja A, format bersarang:
     leagues.<liga>.pooled — dipakai bagian POOLED 3 musim penuh;
     live_parsial TIDAK dipakai karena eksplisit noisy per laporan
     pekerja A §4.4). TIDAK ADA parameter contoh sebagai default
     berjalan: bila file belum ada dan tidak ada argumen ->
     DATA_INCOMPLETE "fit_menunggu_persetujuan". Parameter yang
     belum disetujui user (D12) -> status maksimal HOLD
     ("fit_belum_disetujui"), tidak pernah OK.
  3. Harga dari slate_match (market_prices 2b: harga jup.ag +
     p_market yang SUDAH di-resolve per P1-P4 oleh slate —
     sportsbook devig dulu, Kalshi terakhir) — tanpa slate tidak ada
     harga -> DATA_INCOMPLETE.
  4. Simulasi Dixon-Coles: football_sim.simulate(inputs, params, cfg,
     seed, iterations) dengan inputs {"home": {"name","attack",
     "defence"}, "away": {...}, "match": {"match_id","home_team",
     "away_team","date",...}} dan params {"rho",
     "avg_home_goals", "avg_away_goals", "league", "fit_version"}.
     Gagal -> DATA_INCOMPLETE. KONTRAK SIM (nyata, pekerja B —
     engine/football_sim.py GARIS_TOTAL = (0.5, 1.5, 2.5, 3.5, 4.5,
     5.5, 6.5, 7.5, 8.5); diperluas koordinator langkah 5 dari
     (1.5, 2.5, 3.5) agar menutup tangga total market): dict hasil
     membawa "markets" dengan kunci home_win/draw/away_win,
     total_over/under_0_5 s.d. _8_5, btts_yes/btts_no, dan
     score_distribution.total.median + home_points/away_points
     (mean/median). Garis total DI LUAR 0.5-8.5 TIDAK dipunyai
     sim -> kaki itu meets=false ("p_model_tidak_ada"), bukan
     ditebak.
  5. Per kaki: p_model dari markets sim, p_market dari slate
     (MODEL_ONLY bila tidak ada), blend (devig.blend, w=0,3), EV
     (D7), label (price_labels.label_for_ev). Setiap kaki membawa
     no_xg=true + banned_from_insurance=true +
     threshold_penalty_points dari config no_xg (5).
  6. Status: OK = sim + harga + cedera 2 sumber + fit disetujui
     (saat ini TIDAK TERCAPAI: cedera bola 0 sumber — tidak ada
     sumber cedera bola yang bisa dipakai, lihat soccer_brain).
     HOLD = B2 tidak terpenuhi ATAU fit belum disetujui ATAU tidak
     ada kaki yang memenuhi. DATA_INCOMPLETE = fetch/sim/harga gagal.

FAIL-CLOSED: kegagalan tiap tahap -> artefak DATA_INCOMPLETE (dengan
data tahap yang berhasil tetap terlampir) + missing + error tercatat,
TIDAK PERNAH raise — kecuali argumen input tidak valid (ValueError).
Modul ini TIDAK PERNAH memanggil Odds API (p_market dibaca dari slate
yang sudah jadi; 0 kredit untuk langkah ini).

SPREAD TIDAK DIBUAT KAKINYA di langkah 5 (di luar lingkup tugas:
kaki 1X2/O-U gol/BTTS saja) — pasar spread tetap dihitung di
market.n_markets tapi tidak menjadi leg.

RECHECK BOLA: BELUM DIDEFINISIKAN (hutang Langkah 5 — lihat laporan
pekerja C). Kontrak recheck NBA (engine/recheck.py) tidak berlaku
untuk bola: tidak ada sumber cedera segar, tidak ada tangga
Polymarket bola, dan sim ulang butuh football_sim. Jangan memakai
recheck NBA untuk artefak ini.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

import config as config_mod
from engine import devig as devig_mod
from engine import football_sim as football_sim_mod
from engine import price_labels as price_labels_mod
from ingest import soccer_brain as soccer_brain_mod
from ingest.common import now_iso

FORMAT = "soccer_analysis"
FORMAT_VERSION = 1

_SKEMA_SOCCER_ANALYSIS = "soccer_analysis.schema.json"
_SKEMA_SIMULASI = "simulation.schema.json"
_TANGGAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Kunci wajib artefak (validasi minimal bila jsonschema tidak tersedia).
_WAJIB_ARTEFAK = (
    "format",
    "format_version",
    "match_id",
    "home_team",
    "away_team",
    "league",
    "match_date",
    "generated_at",
    "status",
    "legs",
    "labels",
    "fit_status",
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

# Sumber p_market yang sah dari slate (P1-P4).
_SUMBER_PEMBANDING_SAH = frozenset({"kalshi", "odds_api_devig", "espn_odds_devig"})

# Kunci pasar slate -> (market_type, selection, kunci markets sim).
# Kunci sim mengikuti kontrak nyata football_sim (home_win/draw/
# away_win) — BUKAN moneyline_* (itu kunci slate + market_type kaki).
_KAKI_MONEYLINE = (
    ("moneyline_home", "moneyline_home", "home", "home_win"),
    ("moneyline_draw", "moneyline_draw", "draw", "draw"),
    ("moneyline_away", "moneyline_away", "away", "away_win"),
)


def _slug(nama: str) -> str:
    """Slug pendek nama tim untuk match_id ('Man City' -> 'man-city')."""
    return re.sub(r"[^a-z0-9]+", "-", str(nama or "").lower()).strip("-") or "tim"


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
    (required-field) — pola yang sama dengan engine/nba_analysis.py.
    """
    try:
        import jsonschema
    except ImportError:
        wajib = (
            _WAJIB_ARTEFAK if nama_skema == _SKEMA_SOCCER_ANALYSIS else _WAJIB_SIMULASI
        )
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


def validate_soccer_analysis(artefak: dict) -> str | None:
    """Validasi artefak soccer_analysis terhadap skemanya.

    Mengembalikan pesan error, atau None bila valid. Dipakai builder
    sebelum mengembalikan artefak, dan tersedia untuk konsumen.
    """
    if not isinstance(artefak, dict):
        return "artefak harus dict"
    return _validasi_jsonschema(artefak, _SKEMA_SOCCER_ANALYSIS)


def _validasi_simulasi(sim: dict) -> str | None:
    """Validasi dict simulasi terhadap simulation.schema.json."""
    if not isinstance(sim, dict):
        return "simulasi harus dict"
    return _validasi_jsonschema(sim, _SKEMA_SIMULASI)


def minimal_soccer_analysis(
    match_id: str,
    home_team: str,
    away_team: str,
    match_date: str,
    missing: list[str],
    league: str = "EPL",
    start_time: str | None = None,
) -> dict:
    """Artefak minimal DATA_INCOMPLETE yang tetap valid vs skema.

    Dipakai builder untuk kegagalan total, dan cli.py analyze bila
    builder gagal total — analyze tetap jalan, slate tidak gagal hanya
    karena satu laga bola.
    """
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "match_id": match_id,
        "home_team": home_team,
        "away_team": away_team,
        "league": league,
        "match_date": match_date,
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
        "labels": ["TANPA_XG"],
        "fit_status": {
            "source": "tidak_ada",
            "fit_version": None,
            "approved": False,
            "status": "tidak_ada",
        },
        "anomalies": [],
        "price_snapshots": {},
    }


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


def _validasi_argumen(
    home_team, away_team, match_date, league, seed, iterations
) -> tuple[str, str, str, str]:
    """Validasi + normalisasi argumen builder; ValueError bila tidak valid."""
    if not isinstance(home_team, str) or not home_team.strip():
        raise ValueError(f"home_team harus string tidak kosong: {home_team!r}")
    if not isinstance(away_team, str) or not away_team.strip():
        raise ValueError(f"away_team harus string tidak kosong: {away_team!r}")
    if not isinstance(match_date, str) or not _TANGGAL_RE.match(match_date):
        raise ValueError(f"match_date harus YYYY-MM-DD: {match_date!r}")
    try:
        datetime.strptime(match_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"match_date tidak valid: {match_date!r}") from exc
    if not isinstance(league, str) or not league.strip():
        raise ValueError(f"league harus string tidak kosong: {league!r}")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"seed harus integer atau None: {seed!r}")
    if iterations is not None and (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < 1
    ):
        raise ValueError(f"iterations harus integer >= 1 atau None: {iterations!r}")
    return home_team.strip(), away_team.strip(), match_date, league.strip()


def _validasi_param_fit(params: dict) -> tuple[dict | None, str | None]:
    """Validasi dict parameter fit Dixon-Coles.

    Mengembalikan (params_ternormalisasi, None) atau (None, alasan).
    Kunci wajib: rho (angka), avg_home_goals + avg_away_goals (angka
    > 0), league (string), fit_version (string). "approved" harus
    True eksplisit agar dianggap disetujui — nilai lain (termasuk
    hilang) berarti belum disetujui.
    """
    if not isinstance(params, dict):
        return None, "params_bukan_dict"
    rho = _angka(params.get("rho"))
    avg_home = _angka(params.get("avg_home_goals"))
    avg_away = _angka(params.get("avg_away_goals"))
    if rho is None:
        return None, "rho_tidak_valid"
    if avg_home is None or avg_home <= 0:
        return None, "avg_home_goals_tidak_valid"
    if avg_away is None or avg_away <= 0:
        return None, "avg_away_goals_tidak_valid"
    liga = params.get("league")
    versi = params.get("fit_version")
    if not isinstance(liga, str) or not liga.strip():
        return None, "league_tidak_valid"
    if not isinstance(versi, str) or not versi.strip():
        return None, "fit_version_tidak_valid"
    return (
        {
            "rho": rho,
            "avg_home_goals": avg_home,
            "avg_away_goals": avg_away,
            "league": liga.strip(),
            "fit_version": versi.strip(),
            "approved": params.get("approved") is True,
        },
        None,
    )


def _params_dari_file_fit(mentah: dict, liga: str) -> tuple[dict | None, str | None]:
    """Ekstrak parameter flat dari format file fit pekerja A.

    Format nyata out/fit_soccer_params.json (pekerja A):
    {"generated_at", "status_persetujuan", "leagues": {liga:
    {"musim_fit": [...], "pooled": {rho, avg_home_goals,
    avg_away_goals, ...}, "live_parsial": {...}, "per_musim":
    {...}}}}. Dipakai bagian POOLED (3 musim penuh, n=1140 untuk
    EPL) — live_parsial TIDAK dipakai karena eksplisit noisy
    ("hanya contoh live, bukan estimasi stabil", laporan pekerja A
    §4.4 + keterbatasan file). Persetujuan dibaca dari
    status_persetujuan: disetujui HANYA bila stringnya diawali
    "DISETUJUI" (huruf besar diabaikan) — "MENUNGGU persetujuan
    user" dan "BELUM DISETUJUI" sama-sama belum disetujui.

    Mengembalikan (params_flat, None) atau (None, alasan). Format
    datar lama (rho di top-level) tetap diterima sebagai fallback.
    """
    if not isinstance(mentah, dict):
        return None, "file_bukan_dict"
    if "leagues" not in mentah:
        # Format datar lama (rho/avg di top-level) — fallback.
        params, alasan = _validasi_param_fit(mentah)
        if alasan is not None:
            return None, alasan
        return params, None
    leagues = mentah.get("leagues")
    if not isinstance(leagues, dict):
        return None, "leagues_tidak_valid"
    blok_liga = leagues.get(liga)
    if not isinstance(blok_liga, dict):
        return None, f"liga_{liga}_tidak_ada"
    pooled = blok_liga.get("pooled")
    if not isinstance(pooled, dict):
        return None, f"pooled_{liga}_tidak_ada"
    rho = _angka(pooled.get("rho"))
    avg_home = _angka(pooled.get("avg_home_goals"))
    avg_away = _angka(pooled.get("avg_away_goals"))
    if rho is None:
        return None, "rho_tidak_valid"
    if avg_home is None or avg_home <= 0:
        return None, "avg_home_goals_tidak_valid"
    if avg_away is None or avg_away <= 0:
        return None, "avg_away_goals_tidak_valid"
    musim = blok_liga.get("musim_fit") or []
    if isinstance(musim, list) and len(musim) >= 2:
        rentang = f"{musim[0]}–{musim[-1]}"
    elif isinstance(musim, list) and musim:
        rentang = str(musim[0])
    else:
        rentang = "?"
    dibuat = mentah.get("generated_at")
    versi = f"pooled {liga} {rentang}"
    if isinstance(dibuat, str) and dibuat:
        versi += f" (fit {dibuat[:10]})"
    status = mentah.get("status_persetujuan")
    disetujui = isinstance(status, str) and status.strip().upper().startswith(
        "DISETUJUI"
    )
    return (
        {
            "rho": rho,
            "avg_home_goals": avg_home,
            "avg_away_goals": avg_away,
            "league": liga,
            "fit_version": versi,
            "approved": disetujui,
        },
        None,
    )


def _muat_fit(
    fit_params: dict | None, fit_path=None, liga: str = "EPL"
) -> tuple[dict | None, dict, str | None]:
    """Resolusi parameter fit: argumen dulu, lalu file pekerja A.

    Mengembalikan (params, fit_status, alasan_gagal). params None +
    alasan None berarti fit TIDAK ADA (file belum ada — bukan error
    baca, melainkan "fit menunggu persetujuan"). Alasan terisi berarti
    parameter ada tapi TIDAK VALID (file/argumen rusak).
    """
    status_kosong = {
        "source": "tidak_ada",
        "fit_version": None,
        "approved": False,
        "status": "tidak_ada",
    }
    if fit_params is not None:
        params, alasan = _validasi_param_fit(fit_params)
        if alasan is not None:
            return None, status_kosong, f"fit_argumen_tidak_valid: {alasan}"
        assert params is not None
        return (
            params,
            {
                "source": "argumen",
                "fit_version": params["fit_version"],
                "approved": params["approved"],
                "status": (
                    "disetujui" if params["approved"] else "menunggu_persetujuan"
                ),
            },
            None,
        )
    jalur = fit_path or (config_mod.REPO_ROOT / "out" / "fit_soccer_params.json")
    try:
        teks = Path(jalur).read_text(encoding="utf-8")
    except OSError:
        return None, status_kosong, None
    try:
        mentah = json.loads(teks)
    except json.JSONDecodeError as exc:
        return None, status_kosong, f"fit_file_json_rusak: {exc}"
    params, alasan = _params_dari_file_fit(mentah, liga)
    if alasan is not None:
        return None, status_kosong, f"fit_file_tidak_valid: {alasan}"
    assert params is not None
    return (
        params,
        {
            "source": "out/fit_soccer_params.json",
            "fit_version": params["fit_version"],
            "approved": params["approved"],
            "status": "disetujui" if params["approved"] else "menunggu_persetujuan",
        },
        None,
    )


def _blok_cedera(inputs_data: dict) -> dict:
    """Rakit blok injuries artefak dari inputs soccer_brain.

    n_sources = injuries_status.n_sources (0 saat ini — tidak ada
    sumber cedera bola yang bisa dipakai); confirmed_both = pemain
    OUT/DOUBTFUL yang dikonfirmasi >= 2 sumber di entri gabungnya.
    """
    entri: list[dict] = []
    for blok in (inputs_data.get("home") or {}, inputs_data.get("away") or {}):
        if isinstance(blok, dict):
            entri.extend(blok.get("injuries") or [])
    status_cedera = inputs_data.get("injuries_status") or {}
    n_sumber = status_cedera.get("n_sources")
    if not isinstance(n_sumber, int) or isinstance(n_sumber, bool):
        n_sumber = 0
    sumber: set[str] = set()
    for cedera in entri:
        if not isinstance(cedera, dict):
            continue
        for nama in cedera.get("sources") or []:
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
                    "team": cedera.get("team"),
                    "statuses": cedera["conflict"],
                }
            )
    return {
        "sources": sorted(sumber),
        "n_sources": n_sumber,
        "confirmed_both": sorted(dikonfirmasi),
        "entries": entri,
        "conflicts": konflik,
        "fetched_at": inputs_data.get("fetched_at"),
    }


def _blok_market(slate_match: dict) -> dict:
    """Rakit blok market artefak dari market_prices slate 2b."""
    harga = slate_match.get("market_prices") or {}
    if not isinstance(harga, dict):
        harga = {}

    def _sen(kunci: str) -> float | None:
        entri = harga.get(kunci)
        if not isinstance(entri, dict):
            return None
        return _angka(entri.get("jup_price_cents"))

    garis_total: dict[float, dict] = {}
    for _kunci, entri in harga.items():
        if not isinstance(entri, dict):
            continue
        if entri.get("market_type") != "totals":
            continue
        garis = _angka(entri.get("line"))
        if garis is None:
            continue
        sisi = str(entri.get("side") or "").lower()
        if sisi not in ("over", "under"):
            continue
        baris = garis_total.setdefault(
            garis, {"line": garis, "over_cents": None, "under_cents": None}
        )
        baris[f"{sisi}_cents"] = _angka(entri.get("jup_price_cents"))
    totals = [garis_total[garis] for garis in sorted(garis_total)]
    return {
        "source": "jup_ag_via_slate",
        "fetched_at": (
            slate_match.get("fetched_at")
            if isinstance(slate_match.get("fetched_at"), str)
            else None
        ),
        "n_markets": len(harga),
        "moneyline": {
            "home_cents": _sen("moneyline_home"),
            "draw_cents": _sen("moneyline_draw"),
            "away_cents": _sen("moneyline_away"),
        },
        "totals": totals,
        "btts_cents": _sen("both_teams_to_score_yes"),
    }


def _rakit_kaki(
    market_type: str,
    selection: str,
    line: float | None,
    entri_slate: dict,
    kunci_sim: str,
    markets_sim: dict,
    match_id: str,
    penalti_poin: float,
    cfg: dict,
    generated_at: str,
) -> dict:
    """Rakit satu kaki bola dari entri slate + markets sim.

    p_market dibaca dari entri slate (sudah di-resolve per P1-P4 oleh
    slate 2b); comparison_source yang tidak dikenal -> diperlakukan
    sebagai tidak ada (MODEL_ONLY). Harga venue = jup_price_cents
    slate (harga jup.ag ASLI — price_cents dan jup_estimated_cents
    diisi nilai yang sama).
    """
    if line is not None:
        leg_id = f"{match_id}:{market_type}_{line:g}:main"
    else:
        leg_id = f"{match_id}:{market_type}_{selection}:main"
    p_model = _peluang(markets_sim.get(kunci_sim))
    p_market = _peluang(entri_slate.get("p_market"))
    sumber_pembanding = entri_slate.get("comparison_source")
    if p_market is None or sumber_pembanding not in _SUMBER_PEMBANDING_SAH:
        p_market = None
        sumber_pembanding = None
    p_final = None
    blend_gagal = False
    if p_model is not None:
        try:
            p_final = devig_mod.blend(p_model, p_market, cfg)["p_final"]
        except (ValueError, config_mod.ConfigError):
            blend_gagal = True
    harga = _angka(entri_slate.get("jup_price_cents"))
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
    meets = p_model is not None and harga is not None and not blend_gagal
    if p_model is None:
        reason = "p_model_tidak_ada"
    elif harga is None:
        reason = "harga_tidak_ada"
    elif blend_gagal:
        reason = "blend_gagal"
    else:
        reason = None
    return {
        "leg_id": leg_id,
        "market_type": market_type,
        "selection": selection,
        "line": line,
        "ticket": "main",
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": sumber_pembanding,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
        "ev_pct": ev_pct,
        "price_label": label,
        "meets": meets,
        "reason": reason,
        "fetched_at": generated_at,
        "no_xg": True,
        "banned_from_insurance": True,
        "threshold_penalty_points": penalti_poin,
        "model_only": p_market is None,
    }


def _rakit_semua_kaki(
    slate_match: dict,
    markets_sim: dict,
    match_id: str,
    penalti_poin: float,
    cfg: dict,
    generated_at: str,
) -> list[dict]:
    """Rakit semua kaki (1X2 + O/U + BTTS) dari market_prices slate.

    Urutan: 1X2 (home, draw, away), total per garis menaik (over lalu
    under), BTTS terakhir. Spread TIDAK dibuat kakinya (di luar
    lingkup langkah 5).
    """
    harga = slate_match.get("market_prices") or {}
    if not isinstance(harga, dict):
        return []
    legs: list[dict] = []
    for kunci_slate, market_type, selection, kunci_sim in _KAKI_MONEYLINE:
        entri = harga.get(kunci_slate)
        if not isinstance(entri, dict):
            continue
        legs.append(
            _rakit_kaki(
                market_type,
                selection,
                None,
                entri,
                kunci_sim,
                markets_sim,
                match_id,
                penalti_poin,
                cfg,
                generated_at,
            )
        )
    entri_total: list[tuple[float, str, dict]] = []
    for _kunci_slate, entri in harga.items():
        if not isinstance(entri, dict):
            continue
        if entri.get("market_type") != "totals":
            continue
        garis = _angka(entri.get("line"))
        sisi = str(entri.get("side") or "").lower()
        if garis is None or sisi not in ("over", "under"):
            continue
        entri_total.append((garis, sisi, entri))
    entri_total.sort(key=lambda item: (item[0], item[1]))
    for garis, sisi, entri in entri_total:
        # Kunci sim memakai garis 1 desimal dengan titik diganti
        # garis bawah ("2.5" -> "total_over_2_5"); garis di luar
        # GARIS_TOTAL sim (0.5-8.5) tidak ada kuncinya ->
        # p_model None -> meets=false ("p_model_tidak_ada").
        kunci_sim = f"total_{sisi}_{garis:.1f}".replace(".", "_")
        legs.append(
            _rakit_kaki(
                f"total_{sisi}",
                sisi,
                garis,
                entri,
                kunci_sim,
                markets_sim,
                match_id,
                penalti_poin,
                cfg,
                generated_at,
            )
        )
    entri_btts = harga.get("both_teams_to_score_yes")
    if isinstance(entri_btts, dict):
        legs.append(
            _rakit_kaki(
                "btts_yes",
                "yes",
                None,
                entri_btts,
                "btts_yes",
                markets_sim,
                match_id,
                penalti_poin,
                cfg,
                generated_at,
            )
        )
    return legs


def build_soccer_analysis(
    home_team: str,
    away_team: str,
    match_date: str,
    league: str = "EPL",
    slate_match: dict | None = None,
    start_time: str | None = None,
    cfg: dict | None = None,
    client=None,
    seed: int | None = None,
    iterations: int | None = None,
    fit_params: dict | None = None,
    fit_path=None,
) -> dict:
    """Bangun artefak analisis bola satu laga (format 'soccer_analysis' v1).

    home_team/away_team: nama tim ("Liverpool"/"Manchester United").
    match_date: tanggal kickoff "YYYY-MM-DD". league: "EPL" saja.
    slate_match: entri MatchData 2b laga ini (HARGA jup.ag + p_market;
    None = tidak ada harga -> DATA_INCOMPLETE). start_time: jam
    kickoff (ISO, dari slate); bila None, dipakai
    slate_match["start_time"] bila ada, lalu inputs.match.kickoff
    (MatchData 2b TIDAK punya field start_time — fallback ke
    kickoff fixture PL adalah jalur yang benar-benar terpakai saat
    builder dipanggil langsung). cfg: dict playstyle (None =
    baca playstyle.yaml). client: HttpClient bersama (opsional).
    seed/iterations: diteruskan ke football_sim.simulate (None =
    default config; tes memakai iterations kecil). fit_params: dict
    parameter fit Dixon-Coles eksplisit (untuk tes/fixture — DILARANG
    dipakai sebagai default berjalan; lihat _muat_fit). fit_path:
    path file fit (default out/fit_soccer_params.json; untuk tes).

    Fail-closed: kegagalan tiap tahap -> artefak DATA_INCOMPLETE
    (data tahap yang berhasil tetap terlampir) + missing + error
    tercatat. TIDAK PERNAH raise, kecuali argumen input tidak valid
    (ValueError). TIDAK PERNAH memanggil Odds API.
    """
    home, away, tanggal, liga = _validasi_argumen(
        home_team, away_team, match_date, league, seed, iterations
    )
    match_id = f"{_slug(away)}@{_slug(home)}_{tanggal}"
    start_efektif = start_time
    if start_efektif is None and isinstance(slate_match, dict):
        start_efektif = slate_match.get("start_time")
    if not isinstance(start_efektif, str):
        start_efektif = None
    try:
        return _build_soccer_analysis(
            home,
            away,
            tanggal,
            liga,
            match_id,
            slate_match,
            start_efektif,
            cfg,
            client,
            seed,
            iterations,
            fit_params,
            fit_path,
        )
    except Exception as exc:  # noqa: BLE001 - jaring pengaman terakhir
        return minimal_soccer_analysis(
            match_id,
            home,
            away,
            tanggal,
            [f"kesalahan_internal:{type(exc).__name__}: {exc}"],
            league=liga,
            start_time=start_efektif,
        )


def _build_soccer_analysis(
    home: str,
    away: str,
    tanggal: str,
    liga: str,
    match_id: str,
    slate_match: dict | None,
    start_time: str | None,
    cfg: dict | None,
    client,
    seed: int | None,
    iterations: int | None,
    fit_params: dict | None,
    fit_path,
) -> dict:
    """Pipeline builder (dipanggil build_soccer_analysis; lihat docstringnya)."""
    generated_at = now_iso()
    missing: list[str] = []
    artefak: dict = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "match_id": match_id,
        "home_team": home,
        "away_team": away,
        "league": liga,
        "match_date": tanggal,
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
        "labels": ["TANPA_XG"],
        "fit_status": {
            "source": "tidak_ada",
            "fit_version": None,
            "approved": False,
            "status": "tidak_ada",
        },
        "anomalies": [],
        "price_snapshots": {},
    }

    def _gagal() -> dict:
        """Finalisasi artefak DATA_INCOMPLETE (validasi skema dulu)."""
        artefak["status"] = "DATA_INCOMPLETE"
        return _finalisasi(artefak)

    # Config (None = baca playstyle.yaml) + penalti ambang TANPA_XG.
    try:
        cfg_efektif = cfg if cfg is not None else config_mod.load_playstyle()
    except Exception as exc:  # noqa: BLE001 - config gagal = tahap gagal
        missing.append(f"config_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    try:
        penalti = config_mod.get_value(cfg_efektif, "no_xg", "threshold_penalty_points")
    except config_mod.ConfigError as exc:
        missing.append(f"config_no_xg_hilang: {exc}")
        return _gagal()
    penalti_poin = _angka(penalti)
    if penalti_poin is None or penalti_poin < 0:
        missing.append(f"config_no_xg_tidak_valid: {penalti!r}")
        return _gagal()

    # Tahap 1: input Otak Bola.
    try:
        hasil_inputs = soccer_brain_mod.fetch_match_inputs(
            home_team=home,
            away_team=away,
            match_date=tanggal,
            league=liga,
            client=client,
            cfg=cfg_efektif,
        )
    except Exception as exc:  # noqa: BLE001 - fetch tidak boleh mematikan builder
        missing.append(f"inputs_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    if not hasil_inputs.ok or not isinstance(hasil_inputs.data, dict):
        missing.append(f"inputs_gagal: {hasil_inputs.error or 'tidak diketahui'}")
        return _gagal()
    inputs_data = hasil_inputs.data
    artefak["inputs"] = inputs_data
    # Fallback kickoff: MatchData 2b tidak punya start_time, jadi
    # bila pemanggil tidak memberi start_time, pakai kickoff fixture
    # PL dari inputs (selalu ada bila inputs berhasil).
    if start_time is None:
        blok_match_inputs = inputs_data.get("match") or {}
        kickoff = (
            blok_match_inputs.get("kickoff")
            if isinstance(blok_match_inputs, dict)
            else None
        )
        if isinstance(kickoff, str) and kickoff:
            start_time = kickoff
            artefak["start_time"] = kickoff
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

    # Tahap 2: parameter fit (TIDAK ADA default contoh yang berjalan).
    params, fit_status, alasan_fit = _muat_fit(fit_params, fit_path, liga)
    artefak["fit_status"] = fit_status
    if alasan_fit is not None:
        missing.append(alasan_fit)
        return _gagal()
    if params is None:
        missing.append("fit_menunggu_persetujuan")
        return _gagal()

    # Tahap 3: harga dari slate 2b.
    if not isinstance(slate_match, dict):
        missing.append("slate_match_tidak_ada")
        return _gagal()
    harga_slate = slate_match.get("market_prices")
    if not isinstance(harga_slate, dict) or not harga_slate:
        missing.append("pasar_jup_tidak_ada")
        return _gagal()
    artefak["market"] = _blok_market(slate_match)
    waktu_slate = slate_match.get("fetched_at")
    if isinstance(waktu_slate, str):
        artefak["sources"].append(
            {
                "kind": "jup_prices",
                "source": "Jupiter Prediction API",
                "tier": 1,
                "time": waktu_slate,
            }
        )

    # Tahap 4: simulasi Dixon-Coles.
    blok_home = inputs_data.get("home") or {}
    blok_away = inputs_data.get("away") or {}
    attack_home = _angka(blok_home.get("attack"))
    defence_home = _angka(blok_home.get("defence"))
    attack_away = _angka(blok_away.get("attack"))
    defence_away = _angka(blok_away.get("defence"))
    if (
        attack_home is None
        or defence_home is None
        or attack_away is None
        or defence_away is None
    ):
        missing.append("attack_defence_tidak_lengkap")
        return _gagal()
    blok_match = inputs_data.get("match") or {}
    sim_inputs = {
        "home": {
            "name": home,
            "attack": attack_home,
            "defence": defence_home,
        },
        "away": {
            "name": away,
            "attack": attack_away,
            "defence": defence_away,
        },
        "match": {
            # simulate WAJIB punya match_id + date (ValueError bila
            # hilang); match_date/matchweek/kickoff info tambahan.
            "match_id": match_id,
            "date": tanggal,
            "home_team": home,
            "away_team": away,
            "match_date": tanggal,
            "league": liga,
            "matchweek": blok_match.get("matchweek"),
            "kickoff": blok_match.get("kickoff"),
        },
    }
    sim_params = {
        "rho": params["rho"],
        "avg_home_goals": params["avg_home_goals"],
        "avg_away_goals": params["avg_away_goals"],
        "league": params["league"],
        "fit_version": params["fit_version"],
    }
    try:
        sim = football_sim_mod.simulate(
            sim_inputs, sim_params, cfg_efektif, seed, iterations
        )
    except NotImplementedError:
        missing.append("simulasi_belum_tersedia")
        return _gagal()
    except Exception as exc:  # noqa: BLE001 - sim gagal = DATA_INCOMPLETE
        missing.append(f"simulasi_gagal: {type(exc).__name__}: {exc}")
        return _gagal()
    galat_sim = _validasi_simulasi(sim)
    if galat_sim is not None:
        missing.append(f"simulasi_tidak_valid: {galat_sim}")
        return _gagal()
    artefak["simulation"] = sim
    markets_sim = sim.get("markets") or {}

    # Tahap 5: kaki 1X2 + O/U + BTTS.
    legs = _rakit_semua_kaki(
        slate_match, markets_sim, match_id, penalti_poin, cfg_efektif, generated_at
    )
    artefak["legs"] = legs
    if not legs:
        missing.append("tidak_ada_pasar_1x2_total_btts")
        return _gagal()
    for leg in legs:
        harga = leg.get("jup_estimated_cents")
        if harga is None:
            continue
        garis = leg.get("line")
        if garis is not None:
            kunci = f"{leg['market_type']}_{garis:g}"
        else:
            kunci = f"{leg['market_type']}_{leg['selection']}"
        artefak["price_snapshots"][kunci] = {"cents": harga, "at": generated_at}
    if all(leg.get("p_market") is None for leg in legs):
        artefak["labels"].append("MODEL_ONLY")

    # Status akhir.
    b2_gagal = artefak["injuries"]["n_sources"] < 2
    if b2_gagal:
        missing.append("cedera_kurang_dari_2_sumber")
    fit_belum_setuju = not fit_status["approved"]
    if fit_belum_setuju:
        missing.append("fit_belum_disetujui")
    ada_memenuhi = any(leg.get("meets") for leg in legs)
    if not ada_memenuhi:
        missing.append("tidak_ada_kaki_memenuhi")
    artefak["status"] = (
        "HOLD" if (b2_gagal or fit_belum_setuju or not ada_memenuhi) else "OK"
    )
    return _finalisasi(artefak)


def _finalisasi(artefak: dict) -> dict:
    """Validasi artefak terhadap skema; bila tidak valid, artefak minimal.

    Artefak minimal mempertahankan match_id + missing (ditambah pesan
    validasi) supaya kegagalan validasi tidak menghilangkan jejak.
    """
    galat = validate_soccer_analysis(artefak)
    if galat is None:
        return artefak
    return minimal_soccer_analysis(
        artefak["match_id"],
        artefak["home_team"],
        artefak["away_team"],
        artefak["match_date"],
        [*artefak.get("missing", []), f"artefak_tidak_valid: {galat}"],
        league=artefak.get("league") or "EPL",
        start_time=artefak.get("start_time"),
    )
