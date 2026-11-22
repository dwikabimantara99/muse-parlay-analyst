"""Simulasi sepak bola 100.000x: Dixon-Coles (Blueprint §5b).

RUMUS (Dixon & Coles 1997):
    lam_kandang = attack_kandang x defence_tandang x avg_home_goals
    lam_tandang = attack_tandang x defence_kandang x avg_away_goals
dengan attack/defence = pengali ternormalisasi (rata-rata liga 1).
Koreksi tau() standar untuk skor rendah:
    tau(0,0) = 1 - lam_kandang x lam_tandang x rho
    tau(1,0) = 1 + lam_tandang x rho
    tau(0,1) = 1 + lam_kandang x rho
    tau(1,1) = 1 - rho
    tau(x,y) = 1 untuk skor lainnya.
PMF gabungan dibangun atas gol 0..10 per tim (Poisson x tau),
dinormalisasi setelah pemotongan, lalu disampling dengan
random.Random(seed). Deterministik bila seed diberikan.

PARAMETER DILEWAT EKSPLISIT (argumen params): modul ini TIDAK membaca
rho / home-advantage dari playstyle.yaml — nilainya di sana masih
null/TBD (D12) sampai user menyetujui fit. Yang dibaca dari config
hanya simulation.iterations (default jumlah iterasi).

KETERBATASAN (jujur, jangan dikarang):
- squad_scenarios SELALU []: pemodelan absensi pemain bola (bek/kiper/
  striker) BELUM ada — absence_penalty di playstyle.yaml masih null.
- Gol dibatasi 0..10 per tim; ekor Poisson di atas 10 gol diabaikan
  (untuk lam <= ~3 peluangnya < 1e-4 per tim; PMF dinormalisasi
  setelah pemotongan sehingga peluang tetap berjumlah 1).
- rho harus membuat keempat nilai tau() positif; bila tidak, simulasi
  ditolak (ValueError) — bukan dijepit diam-diam.
"""

from __future__ import annotations

import bisect
import json
import math
import random
import statistics
import time
from collections import Counter
from datetime import UTC, datetime

import config as config_mod

ENGINE_VERSION = "1.0.0"
_SKEMA_SIMULASI = "simulation.schema.json"

# Batas atas gol per tim dalam PMF gabungan (lihat docstring modul).
MAX_GOL = 10
# Rentang rho yang dianggap wajar. Nilai fit literatur EPL ~ -0,13;
# batas ini longgar, dan validasi tau() positif adalah penjaga kedua.
RHO_MIN = -0.5
RHO_MAX = 0.5

# Pasar yang selalu dihitung (peluang 0-1, dari simulasi yang sama).
# Garis 0.5-8.5 menutup seluruh tangga total market (ditemukan di contoh
# live langkah 5: jup.ag/Polymarket menawarkan total 0.5-8.5). Perluasan
# dari (1.5, 2.5, 3.5) adalah keputusan integrasi koordinator langkah 5:
# dengan 3 garis, 12 dari 22 kaki contoh live tidak punya p_model
# (termasuk Alt Under dalam, pasar utama user); peluang tiap garis
# dihitung dari PMF yang sama, tanpa biaya tambahan berarti.
GARIS_TOTAL = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5)

# Kunci wajib simulasi (validasi minimal, selaras simulation.schema.json).
_WAJIB_SIMULASI = (
    "match_id",
    "sport",
    "iterations",
    "generated_at",
    "engine",
    "markets",
)


def _kuantil(nilai_urut: list[float], q: float) -> float:
    """Kuantil q (0-1) dari daftar yang sudah terurut (interpolasi linear)."""
    n = len(nilai_urut)
    pos = q * (n - 1)
    bawah = int(pos)
    atas = min(bawah + 1, n - 1)
    frac = pos - bawah
    return nilai_urut[bawah] * (1.0 - frac) + nilai_urut[atas] * frac


def _angka(nilai: object, label: str) -> float:
    """Validasi satu nilai numerik berhingga; raise ValueError bila tidak."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        raise ValueError(f"{label} harus angka, didapat {nilai!r}")
    hasil = float(nilai)
    if not math.isfinite(hasil):
        raise ValueError(f"{label} harus berhingga, didapat {nilai!r}")
    return hasil


def _angka_positif(nilai: object, label: str) -> float:
    """Validasi satu nilai numerik > 0; raise ValueError bila tidak."""
    hasil = _angka(nilai, label)
    if hasil <= 0:
        raise ValueError(f"{label} harus > 0, didapat {nilai!r}")
    return hasil


def _teks_tak_kosong(nilai: object, label: str) -> str:
    """Validasi satu string tak kosong; raise ValueError bila tidak."""
    if not isinstance(nilai, str) or not nilai.strip():
        raise ValueError(f"{label} harus string tak kosong, didapat {nilai!r}")
    return nilai


def _blok_tim(inputs: dict, kunci: str) -> dict:
    """Ambil + validasi satu blok tim (name, attack, defence)."""
    blok = inputs.get(kunci)
    if not isinstance(blok, dict):
        raise ValueError(f"data_tidak_lengkap: blok {kunci} hilang atau bukan dict")
    return {
        "name": _teks_tak_kosong(blok.get("name"), f"{kunci}.name"),
        "attack": _angka_positif(blok.get("attack"), f"{kunci}.attack"),
        "defence": _angka_positif(blok.get("defence"), f"{kunci}.defence"),
    }


def _tau(x: int, y: int, lam_kandang: float, lam_tandang: float, rho: float) -> float:
    """Koreksi Dixon-Coles tau(x, y) untuk skor (x, y)."""
    if x == 0 and y == 0:
        return 1.0 - lam_kandang * lam_tandang * rho
    if x == 1 and y == 0:
        return 1.0 + lam_tandang * rho
    if x == 0 and y == 1:
        return 1.0 + lam_kandang * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _pmf_kumulatif(lam_kandang: float, lam_tandang: float, rho: float) -> list[float]:
    """PMF gabungan gol 0..MAX_GOL sebagai distribusi kumulatif.

    Urutan indeks: h * (MAX_GOL + 1) + a. Nilai tau() keempat skor
    rendah dicek positif dulu — PMF dengan peluang negatif ditolak,
    bukan dijepit.
    """
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
        nilai_tau = _tau(x, y, lam_kandang, lam_tandang, rho)
        if nilai_tau <= 0:
            raise ValueError(
                f"koreksi tau({x},{y}) = {nilai_tau:.4f} <= 0 untuk "
                f"lambda_kandang={lam_kandang:.4f}, "
                f"lambda_tandang={lam_tandang:.4f}, rho={rho} — "
                "kombinasi parameter tidak valid (rho terlalu besar "
                "untuk lambda sebesar ini)"
            )
    poisson_kandang = [
        math.exp(-lam_kandang) * lam_kandang**x / math.factorial(x)
        for x in range(MAX_GOL + 1)
    ]
    poisson_tandang = [
        math.exp(-lam_tandang) * lam_tandang**y / math.factorial(y)
        for y in range(MAX_GOL + 1)
    ]
    gabung = [
        poisson_kandang[h]
        * poisson_tandang[a]
        * _tau(h, a, lam_kandang, lam_tandang, rho)
        for h in range(MAX_GOL + 1)
        for a in range(MAX_GOL + 1)
    ]
    total = sum(gabung)
    if total <= 0:
        raise ValueError(f"PMF gabungan tidak valid: jumlah peluang {total}")
    kumulatif: list[float] = []
    berjalan = 0.0
    for peluang in gabung:
        berjalan += peluang / total
        kumulatif.append(berjalan)
    # Jaga dari hanyutan float: nilai terakhir harus persis 1.
    kumulatif[-1] = 1.0
    return kumulatif


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


def _validasi_simulasi(hasil: dict) -> str | None:
    """Validasi dict simulasi terhadap simulation.schema.json.

    Pola yang sama dengan engine.nba_analysis._validasi_jsonschema:
    bila jsonschema tidak tersedia, pakai validasi minimal (field
    wajib + rentang peluang). Mengembalikan pesan error, atau None
    bila valid.
    """
    try:
        import jsonschema
    except ImportError:
        for kunci in _WAJIB_SIMULASI:
            if kunci not in hasil:
                return f"{_SKEMA_SIMULASI}: kehilangan kunci wajib: {kunci}"
        if hasil.get("sport") != "football":
            return f"{_SKEMA_SIMULASI}: sport harus 'football'"
        markets = hasil.get("markets")
        if not isinstance(markets, dict):
            return f"{_SKEMA_SIMULASI}: markets harus dict"
        for kunci, nilai in markets.items():
            if (
                isinstance(nilai, bool)
                or not isinstance(nilai, (int, float))
                or not 0.0 <= nilai <= 1.0
            ):
                return f"{_SKEMA_SIMULASI}: markets.{kunci} di luar 0-1: {nilai!r}"
        return None
    skema = _muat_skema(_SKEMA_SIMULASI)
    if skema is None:
        return f"tidak bisa membaca skema {_SKEMA_SIMULASI}"
    try:
        jsonschema.validate(hasil, skema)
    except jsonschema.ValidationError as exc:
        return f"tidak valid vs {_SKEMA_SIMULASI}: {exc.message}"
    return None


def validate_football_sim(hasil: dict) -> str | None:
    """Validasi hasil simulate() terhadap simulation.schema.json.

    Mengembalikan pesan error, atau None bila valid. Dipakai simulate()
    sebelum mengembalikan hasil, dan tersedia untuk konsumen (mis.
    wiring Tahap 3) yang ingin memvalidasi hasil yang dibacanya.
    """
    if not isinstance(hasil, dict):
        return "hasil simulasi harus dict"
    return _validasi_simulasi(hasil)


def simulate(
    inputs: dict,
    params: dict,
    cfg: dict | None = None,
    seed: int | None = None,
    iterations: int | None = None,
) -> dict:
    """Simulasi satu laga sepak bola (Dixon-Coles), valid vs skema simulasi.

    inputs: {"home": {"name", "attack", "defence"}, "away": {...},
      "match": {"match_id", "home_team", "away_team", "date"}}.
      attack/defence = pengali ternormalisasi (rata-rata liga 1).
    params: {"rho", "avg_home_goals", "avg_away_goals", "league",
      "fit_version"} — dilewat eksplisit; modul TIDAK membaca rho /
      home-advantage dari playstyle.yaml (masih null/TBD, D12).
    cfg: dict playstyle (default: dibaca dari config/playstyle.yaml);
      hanya simulation.iterations yang dipakai.
    seed: bila diberikan, hasil deterministik (random.Random(seed)).
    iterations: jumlah iterasi; bila None, dari config
      simulation.iterations (100000). Tes unit memakai nilai kecil.
    """
    mulai = time.perf_counter()
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"seed harus integer atau None, didapat {seed!r}")
    if not isinstance(inputs, dict):
        raise ValueError("data_tidak_lengkap: inputs harus dict")
    if not isinstance(params, dict):
        raise ValueError("data_tidak_lengkap: params harus dict")

    kandang = _blok_tim(inputs, "home")
    tandang = _blok_tim(inputs, "away")
    pertandingan = inputs.get("match")
    if not isinstance(pertandingan, dict):
        raise ValueError("data_tidak_lengkap: blok match hilang atau bukan dict")
    match_id = _teks_tak_kosong(pertandingan.get("match_id"), "match.match_id")
    tim_kandang = _teks_tak_kosong(pertandingan.get("home_team"), "match.home_team")
    tim_tandang = _teks_tak_kosong(pertandingan.get("away_team"), "match.away_team")
    tanggal = _teks_tak_kosong(pertandingan.get("date"), "match.date")

    rho = _angka(params.get("rho"), "params.rho")
    if not RHO_MIN <= rho <= RHO_MAX:
        raise ValueError(
            f"params.rho di luar rentang wajar [{RHO_MIN}, {RHO_MAX}]: {rho}"
        )
    avg_home = _angka_positif(params.get("avg_home_goals"), "params.avg_home_goals")
    avg_away = _angka_positif(params.get("avg_away_goals"), "params.avg_away_goals")
    liga = _teks_tak_kosong(params.get("league"), "params.league")
    fit_version = _teks_tak_kosong(params.get("fit_version"), "params.fit_version")

    cfg = cfg if cfg is not None else config_mod.load_playstyle()
    if iterations is None:
        nilai_iterasi = config_mod.get_value(cfg, "simulation", "iterations")
        if nilai_iterasi is None:
            raise config_mod.ConfigError(
                "parameter_belum_difit: simulation.iterations masih null"
            )
        iterations = nilai_iterasi
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < 1
    ):
        raise ValueError(f"iterations harus integer >= 1, didapat {iterations!r}")

    lam_kandang = kandang["attack"] * tandang["defence"] * avg_home
    lam_tandang = tandang["attack"] * kandang["defence"] * avg_away
    kumulatif = _pmf_kumulatif(lam_kandang, lam_tandang, rho)

    rng = random.Random(seed)
    lebar = MAX_GOL + 1
    hitung_skor: Counter[tuple[int, int]] = Counter()
    gol_kandang: list[float] = []
    gol_tandang: list[float] = []
    gol_total: list[float] = []
    menang_kandang = 0
    seri = 0
    menang_tandang = 0
    over: dict[float, int] = dict.fromkeys(GARIS_TOTAL, 0)
    btts = 0
    for _ in range(iterations):
        idx = bisect.bisect_left(kumulatif, rng.random())
        h, a = divmod(idx, lebar)
        hitung_skor[(h, a)] += 1
        gol_kandang.append(float(h))
        gol_tandang.append(float(a))
        total = h + a
        gol_total.append(float(total))
        if h > a:
            menang_kandang += 1
        elif h == a:
            seri += 1
        else:
            menang_tandang += 1
        for garis in GARIS_TOTAL:
            if total > garis:
                over[garis] += 1
        if h > 0 and a > 0:
            btts += 1

    n = float(iterations)
    markets: dict[str, float] = {
        "home_win": round(menang_kandang / n, 6),
        "draw": round(seri / n, 6),
        "away_win": round(menang_tandang / n, 6),
        "btts_yes": round(btts / n, 6),
        "btts_no": round((iterations - btts) / n, 6),
    }
    for garis in GARIS_TOTAL:
        kunci = f"{garis:.1f}".replace(".", "_")
        markets[f"total_over_{kunci}"] = round(over[garis] / n, 6)
        markets[f"total_under_{kunci}"] = round((iterations - over[garis]) / n, 6)

    gol_kandang.sort()
    gol_tandang.sort()
    gol_total.sort()
    dist_total = {
        "mean": round(statistics.mean(gol_total), 2),
        "std": round(statistics.pstdev(gol_total), 2),
        "median": round(_kuantil(gol_total, 0.5), 2),
        "p5": round(_kuantil(gol_total, 0.05), 2),
        "p25": round(_kuantil(gol_total, 0.25), 2),
        # p74: KONTRAK modul cushion (patch 1b perbaikan 3) — garis Alt
        # Under Asuransi = garis market terkecil dengan P(Under) >= 74%.
        "p74": round(_kuantil(gol_total, 0.74), 2),
        "p75": round(_kuantil(gol_total, 0.75), 2),
        "p95": round(_kuantil(gol_total, 0.95), 2),
    }
    skor_teratas = sorted(
        hitung_skor.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
    )[:10]
    scorelines = [
        {
            "home_goals": h,
            "away_goals": a,
            "probability": round(jumlah / n, 6),
        }
        for (h, a), jumlah in skor_teratas
    ]

    selesai = time.perf_counter()
    hasil = {
        "match_id": match_id,
        "sport": "football",
        "iterations": iterations,
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": {
            "name": "football_sim",
            "version": ENGINE_VERSION,
            "seed": seed,
        },
        "markets": markets,
        "inputs_summary": {
            "home_team": tim_kandang,
            "away_team": tim_tandang,
            "match_date": tanggal,
            "league": liga,
            "fit_version": fit_version,
            "home_attack": kandang["attack"],
            "home_defence": kandang["defence"],
            "away_attack": tandang["attack"],
            "away_defence": tandang["defence"],
            "avg_home_goals": avg_home,
            "avg_away_goals": avg_away,
            "rho": rho,
            "lambda_home": round(lam_kandang, 4),
            "lambda_away": round(lam_tandang, 4),
            "max_goals_per_team": MAX_GOL,
            "elapsed_seconds": round(selesai - mulai, 3),
            "notes": [
                "parameter fit (rho, avg goals, kekuatan tim) dilewat "
                "eksplisit oleh pemanggil — berlaku setelah user "
                "menyetujui fit (D12); modul TIDAK membaca "
                "simulation.football dari playstyle.yaml",
                "gol dibatasi 0..10 per tim; PMF dinormalisasi setelah "
                "pemotongan (lihat docstring modul)",
                "squad_scenarios kosong: pemodelan absensi pemain bola "
                "belum ada (absence_penalty masih null)",
            ],
        },
        "score_distribution": {
            "home_points": {
                "mean": round(statistics.mean(gol_kandang), 2),
                "median": round(_kuantil(gol_kandang, 0.5), 2),
            },
            "away_points": {
                "mean": round(statistics.mean(gol_tandang), 2),
                "median": round(_kuantil(gol_tandang, 0.5), 2),
            },
            "total": dist_total,
            "scorelines": scorelines,
        },
        "squad_scenarios": [],
    }
    kesalahan = _validasi_simulasi(hasil)
    if kesalahan is not None:
        # Fail-closed: hasil yang tidak valid vs skema adalah bug
        # modul ini — jangan kembalikan diam-diam.
        raise ValueError(f"hasil simulasi tidak valid: {kesalahan}")
    return hasil
