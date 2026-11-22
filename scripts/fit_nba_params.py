"""Fit parameter simulasi NBA dari data historis 2-3 musim (D12).

Metode (didokumentasikan di sini + LAPORAN-FIT-NBA.md):

  (a) PROYEKSI. Setiap laga historis diproyeksikan dengan rumus yang
      SAMA PERSIS dengan engine.nba_sim.project_points (ORtg vs DRtg
      lawan, pace rata-rata kedua tim), memakai rating MUSIM PENUH
      Basketball-Reference. KETERBATASAN (dicatat jujur): rating musim
      penuh "melihat masa depan" — rating itu dihitung dari semua laga
      musim itu, termasuk laga yang sedang diproyeksikan. Akibatnya
      residual sedikit TERLALU KECIL dan sigma sedikit underestimate.
      Perbaikan ke depan: rating rolling sampai sebelum tanggal laga.
  (b) SIGMA. sigma_margin & sigma_total = simpangan baku residual
      (aktual - proyeksi) margin dan total.
  (c) HOME ADVANTAGE. Regresi OLS sederhana: margin_aktual ~ a +
      b * selisih_net_rating. Intersep a = home advantage (poin).
      Cek silang: rata-rata residual margin (proyeksi tanpa penyesuaian).
  (d) BACK-TO-BACK. Residual poin tim (aktual - proyeksi, tanpa
      penyesuaian): penalti = rata-rata residual tim B2B - rata-rata
      residual tim tidak B2B. B2B = tim main sehari sebelumnya
      (dari tanggal game log). Nilai BERTANDA (negatif = tim B2B
      mencetak lebih sedikit) — sim MENAMBAHKAN nilai ini.
  (e) ALTITUDE. Rata-rata residual margin laga kandang DEN/UTA dikurangi
      rata-rata residual margin laga kandang lainnya.
  (f) DERAJAT BEBAS t (nu). Grid MLE atas residual terstandarisasi
      gabungan (margin + total, masing-masing dibagi sigmanya):
      nu yang memaksimalkan log-likelihood Student-t, grid 3.0-30.0
      langkah 0.5. Kurtosis lebih sampel dilaporkan sebagai cek silang.

Data:
  - Game log via ingest.stats_nba.fetch_league_games (kontrak worker
    data Tahap 3): FetchResult dengan data = list dict per laga:
    {"game_date" (YYYY-MM-DD), "game_id", "home_tricode",
     "away_tricode", "home_pts", "away_pts", ...}. Record TIDAK
    membawa "season" — loader script ini mencapnya dari argumen musim
    saat fetch (dipakai untuk lookup rating per musim).
    Bila fungsi itu belum tersedia, script berhenti dengan pesan jelas
    (exit 2) — atau pakai --games-file untuk memuat game log dari JSON
    dengan bentuk yang sama (file HARUS memuat "season" per laga).
  - Rating tim musim penuh via ingest.bbref.fetch_team_advanced
    (sudah ada): off_rtg/def_rtg/net_rtg/pace per tim per musim.
  - Data mentah disimpan ke data/nba_history/ (gitignored).
  - Hasil fit ke out/fit_nba_params.json (gitignored) + print ringkasan.

Aturan: JANGAN mengarang angka. Parameter yang datanya tidak cukup
(dibawah ambang minimum di playstyle.yaml simulation.fitting)
ditulis null + alasan.

Jalankan dari root repo:
  python3 scripts/fit_nba_params.py [--seasons 2024-25 2025-26 2026-27]
      [--games-file data/nba_history/games_all.json]
      [--out out/fit_nba_params.json]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine.nba_sim import project_points

# Nama tim Basketball-Reference -> tricode (30 tim; nama sudah tanpa "*").
BBREF_TEAM_TRICODES = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "LA Clippers": "LAC",
    "Los Angeles Clippers": "LAC",  # nama di tabel BBRef (bukan "LA")
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

# Tim kandang di ketinggian (sama seperti engine.nba_sim).
ALTITUDE_TRICODES = frozenset({"DEN", "UTA"})

# Grid MLE derajat bebas Student-t. Batas atas 50: pada data nyata
# profil log-likelihood datar di 20-100 (puncak ~30), jadi grid harus
# cukup lebar agar MLE tidak mentok di batas.
NU_GRID_MIN = 3.0
NU_GRID_MAX = 50.0
NU_GRID_STEP = 0.5


def _parse_tanggal(teks: str) -> date | None:
    """Parse tanggal YYYY-MM-DD; None bila tidak valid."""
    try:
        return date.fromisoformat(teks[:10])
    except (ValueError, TypeError, AttributeError):
        return None


def detect_back_to_back(games: list[dict]) -> dict[str, bool]:
    """Tandai team-game yang back-to-back dari tanggal game log.

    Mengembalikan peta "game_id:tricode" -> True bila tim itu main
    sehari sebelumnya (kalender). Game tanpa tanggal valid dianggap
    bukan B2B.
    """
    tanggal_main: dict[str, set[date]] = {}
    for game in games:
        tanggal = _parse_tanggal(str(game.get("game_date") or ""))
        if tanggal is None:
            continue
        for kunci in ("home_tricode", "away_tricode"):
            tricode = game.get(kunci)
            if isinstance(tricode, str):
                tanggal_main.setdefault(tricode, set()).add(tanggal)
    hasil: dict[str, bool] = {}
    for game in games:
        tanggal = _parse_tanggal(str(game.get("game_date") or ""))
        game_id = str(game.get("game_id"))
        for kunci in ("home_tricode", "away_tricode"):
            tricode = game.get(kunci)
            if not isinstance(tricode, str):
                continue
            b2b = False
            if tanggal is not None:
                sehari_sebelum = date.fromordinal(tanggal.toordinal() - 1)
                b2b = sehari_sebelum in tanggal_main.get(tricode, set())
            hasil[f"{game_id}:{tricode}"] = b2b
    return hasil


def _regresi_linear_sederhana(
    xs: list[float], ys: list[float]
) -> tuple[float, float, float, float]:
    """OLS y ~ a + b*x. Kembalikan (intersep, slope, R^2, SE intersep)."""
    n = len(xs)
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("regresi gagal: varians x = 0")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intersep = mean_y - slope * mean_x
    sst = sum((y - mean_y) ** 2 for y in ys)
    sse = sum((y - (intersep + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    mse = sse / (n - 2) if n > 2 else 0.0
    se_intersep = math.sqrt(mse * (1.0 / n + mean_x * mean_x / sxx)) if n > 2 else 0.0
    return intersep, slope, r2, se_intersep


def _loglik_student_t(z: list[float], nu: float) -> float:
    """Log-likelihood Student-t(nu) untuk residual terstandarisasi z.

    z ber-varians 1, jadi yang dipakai adalah t yang DISKALAKAN ke
    varians 1: Z = T / c dengan c = akar(nu/(nu-2)), T ~ t standar.
    f_Z(z) = c * f_T(c*z) — suku log(c) (Jacobian) wajib ada; tanpa
    itu MLE bias ke nu besar.
    """
    n = len(z)
    c = math.sqrt(nu / (nu - 2.0))
    konstanta = (
        math.lgamma((nu + 1.0) / 2.0)
        - math.lgamma(nu / 2.0)
        - 0.5 * math.log(nu * math.pi)
        + math.log(c)
    )
    jumlah = sum(math.log1p(((c * nilai) ** 2) / nu) for nilai in z)
    return n * konstanta - ((nu + 1.0) / 2.0) * jumlah


def _fit_nu(residual_terstandar: list[float]) -> tuple[float, float, float]:
    """Grid MLE derajat bebas t + kurtosis lebih sampel (cek silang).

    Mengembalikan (nu_mle, loglik_maks, kurtosis_lebih).
    """
    nu_terbaik = NU_GRID_MIN
    ll_terbaik = _loglik_student_t(residual_terstandar, NU_GRID_MIN)
    nu = NU_GRID_MIN + NU_GRID_STEP
    while nu <= NU_GRID_MAX + 1e-9:
        ll = _loglik_student_t(residual_terstandar, nu)
        if ll > ll_terbaik:
            ll_terbaik = ll
            nu_terbaik = nu
        nu += NU_GRID_STEP
    mean_z = statistics.fmean(residual_terstandar)
    m2 = statistics.fmean([(nilai - mean_z) ** 2 for nilai in residual_terstandar])
    m4 = statistics.fmean([(nilai - mean_z) ** 4 for nilai in residual_terstandar])
    kurtosis_lebih = m4 / (m2 * m2) - 3.0 if m2 > 0 else 0.0
    return nu_terbaik, ll_terbaik, kurtosis_lebih


def fit_parameters(
    games: list[dict],
    ratings: dict[str, dict[str, dict[str, float]]],
    min_games_total: int = 100,
    min_group_n: int = 30,
) -> dict:
    """Fit semua parameter NBA dari game log + rating musim penuh.

    games: list dict per laga (lihat docstring modul). ratings:
    {musim: {tricode: {off_rtg, def_rtg, net_rtg, pace}}}.
    min_games_total/min_group_n: ambang minimum data (dari config
    simulation.fitting bila dipanggil lewat main; default di sini
    hanya untuk pemakaian langsung/fixture).
    Mengembalikan dict hasil fit; tiap parameter berisi value (atau
    null + reason), n, dan bukti statistiknya.
    """
    hasil: dict = {
        "method": "lihat docstring scripts/fit_nba_params.py + LAPORAN-FIT-NBA.md",
        "look_ahead_bias": (
            "rating musim penuh melihat masa depan (termasuk laga yang "
            "diproyeksikan) — residual sedikit terlalu kecil, sigma "
            "sedikit underestimate"
        ),
        "n_games_input": len(games),
        "n_games_used": 0,
        "n_games_skipped_no_rating": 0,
        "games_per_season": {},
        "parameters": {},
    }
    params: dict = hasil["parameters"]

    def _null(nama: str, alasan: str) -> None:
        params[nama] = {"value": None, "reason": alasan}

    # Proyeksi + residual per laga.
    b2b = detect_back_to_back(games)
    resid_margin: list[float] = []
    resid_total: list[float] = []
    margin_aktual: list[float] = []
    selisih_net: list[float] = []
    resid_tim_b2b: list[float] = []
    resid_tim_non_b2b: list[float] = []
    resid_margin_alt: list[float] = []
    resid_margin_non_alt: list[float] = []
    dipakai_per_musim: dict[str, int] = {}
    for game in games:
        musim = str(game.get("season"))
        rating_musim = ratings.get(musim)
        home = game.get("home_tricode")
        away = game.get("away_tricode")
        home_pts = game.get("home_pts")
        away_pts = game.get("away_pts")
        if (
            rating_musim is None
            or home not in rating_musim
            or away not in rating_musim
            or home_pts is None
            or away_pts is None
        ):
            hasil["n_games_skipped_no_rating"] += 1
            continue
        rating_home = rating_musim[home]
        rating_away = rating_musim[away]
        if any(
            rating_home.get(k) is None or rating_away.get(k) is None
            for k in ("off_rtg", "def_rtg", "pace")
        ):
            hasil["n_games_skipped_no_rating"] += 1
            continue
        lg_avg = statistics.fmean(
            r["off_rtg"] for r in rating_musim.values() if r.get("off_rtg") is not None
        )
        mu_home, mu_away, _pace = project_points(rating_home, rating_away, lg_avg)
        margin = float(home_pts) - float(away_pts)
        total = float(home_pts) + float(away_pts)
        resid_margin.append(margin - (mu_home - mu_away))
        resid_total.append(total - (mu_home + mu_away))
        margin_aktual.append(margin)
        net_home = rating_home.get("net_rtg")
        net_away = rating_away.get("net_rtg")
        if net_home is None:
            net_home = rating_home["off_rtg"] - rating_home["def_rtg"]
        if net_away is None:
            net_away = rating_away["off_rtg"] - rating_away["def_rtg"]
        selisih_net.append(float(net_home) - float(net_away))
        game_id = str(game.get("game_id"))
        for tricode, resid in (
            (home, float(home_pts) - mu_home),
            (away, float(away_pts) - mu_away),
        ):
            if b2b.get(f"{game_id}:{tricode}", False):
                resid_tim_b2b.append(resid)
            else:
                resid_tim_non_b2b.append(resid)
        if home in ALTITUDE_TRICODES:
            resid_margin_alt.append(margin - (mu_home - mu_away))
        else:
            resid_margin_non_alt.append(margin - (mu_home - mu_away))
        dipakai_per_musim[musim] = dipakai_per_musim.get(musim, 0) + 1

    n = len(resid_margin)
    hasil["n_games_used"] = n
    hasil["games_per_season"] = dipakai_per_musim
    if n < min_games_total:
        for nama in (
            "sigma_margin_points",
            "sigma_total_points",
            "home_advantage_points",
            "back_to_back_penalty_points",
            "altitude_adjustment_points",
            "t_nu",
        ):
            _null(nama, f"data tidak cukup: {n} laga < minimum {min_games_total}")
        return hasil

    # (b) Sigma margin & total.
    sigma_margin = statistics.stdev(resid_margin)
    sigma_total = statistics.stdev(resid_total)
    params["sigma_margin_points"] = {
        "value": round(sigma_margin, 4),
        "n": n,
        "mean_residual": round(statistics.fmean(resid_margin), 4),
        "method": "simpangan baku residual margin (aktual - proyeksi)",
    }
    params["sigma_total_points"] = {
        "value": round(sigma_total, 4),
        "n": n,
        "mean_residual": round(statistics.fmean(resid_total), 4),
        "method": "simpangan baku residual total (aktual - proyeksi)",
    }

    # (c) Home advantage via regresi margin ~ selisih net rating.
    intersep, slope, r2, se_intersep = _regresi_linear_sederhana(
        selisih_net, margin_aktual
    )
    params["home_advantage_points"] = {
        "value": round(intersep, 4),
        "n": n,
        "slope_net_rating": round(slope, 4),
        "r_squared": round(r2, 4),
        "se_intercept": round(se_intersep, 4),
        "cross_check_mean_residual_margin": round(statistics.fmean(resid_margin), 4),
        "method": "intersep regresi OLS margin ~ selisih net rating",
    }

    # (d) Penalti back-to-back (bertanda).
    n_b2b = len(resid_tim_b2b)
    n_non = len(resid_tim_non_b2b)
    if n_b2b < min_group_n or n_non < min_group_n:
        _null(
            "back_to_back_penalty_points",
            f"data tidak cukup: n_b2b={n_b2b}, n_non_b2b={n_non} "
            f"(minimum grup {min_group_n})",
        )
    else:
        mean_b2b = statistics.fmean(resid_tim_b2b)
        mean_non = statistics.fmean(resid_tim_non_b2b)
        se = math.sqrt(
            statistics.variance(resid_tim_b2b) / n_b2b
            + statistics.variance(resid_tim_non_b2b) / n_non
        )
        params["back_to_back_penalty_points"] = {
            "value": round(mean_b2b - mean_non, 4),
            "n_b2b": n_b2b,
            "n_non_b2b": n_non,
            "mean_residual_b2b": round(mean_b2b, 4),
            "mean_residual_non_b2b": round(mean_non, 4),
            "se_difference": round(se, 4),
            "method": (
                "rata-rata residual poin tim B2B dikurangi rata-rata "
                "residual tim tidak B2B (bertanda; negatif = tim B2B "
                "mencetak lebih sedikit)"
            ),
        }

    # (e) Altitude (DEN/UTA kandang).
    n_alt = len(resid_margin_alt)
    n_non_alt = len(resid_margin_non_alt)
    if n_alt < min_group_n or n_non_alt < min_group_n:
        _null(
            "altitude_adjustment_points",
            f"data tidak cukup: n_alt={n_alt}, n_non_alt={n_non_alt} "
            f"(minimum grup {min_group_n})",
        )
    else:
        mean_alt = statistics.fmean(resid_margin_alt)
        mean_non_alt = statistics.fmean(resid_margin_non_alt)
        se = math.sqrt(
            statistics.variance(resid_margin_alt) / n_alt
            + statistics.variance(resid_margin_non_alt) / n_non_alt
        )
        params["altitude_adjustment_points"] = {
            "value": round(mean_alt - mean_non_alt, 4),
            "n_alt_home": n_alt,
            "n_non_alt_home": n_non_alt,
            "mean_residual_alt": round(mean_alt, 4),
            "mean_residual_non_alt": round(mean_non_alt, 4),
            "se_difference": round(se, 4),
            "method": (
                "rata-rata residual margin laga kandang DEN/UTA "
                "dikurangi rata-rata residual margin kandang lainnya"
            ),
        }

    # (f) Derajat bebas t via grid MLE atas residual terstandar gabungan.
    z = [r / sigma_margin for r in resid_margin] + [
        r / sigma_total for r in resid_total
    ]
    nu, ll, kurt = _fit_nu(z)
    params["t_nu"] = {
        "value": nu,
        "n": len(z),
        "loglik_max": round(ll, 2),
        "excess_kurtosis_pooled": round(kurt, 4),
        "kurtosis_implied_nu": (round(4.0 + 6.0 / kurt, 2) if kurt > 0 else None),
        "method": (
            "grid MLE nu 3.0-50.0 langkah 0.5 atas residual "
            "terstandarisasi gabungan (margin + total)"
        ),
    }
    return hasil


def _musim_ke_tahun_bbref(musim: str) -> int:
    """Ubah "2025-26" -> 2026 (tahun musim berakhir, konvensi BBRef)."""
    try:
        return int(musim.split("-")[0]) + 1
    except (ValueError, IndexError, AttributeError) as exc:
        raise ValueError(f"format musim tidak valid: {musim!r}") from exc


def load_ratings(seasons: list[str], data_dir: Path) -> dict:
    """Ambil rating tim musim penuh BBRef per musim; simpan mentahnya.

    Mengembalikan {musim: {tricode: {off_rtg, def_rtg, net_rtg, pace}}}.
    Raise RuntimeError bila fetch gagal (pesan jelas, tanpa traceback
    misterius di main).
    """
    from ingest.bbref import fetch_team_advanced

    ratings: dict[str, dict[str, dict[str, float]]] = {}
    data_dir.mkdir(parents=True, exist_ok=True)
    for musim in seasons:
        tahun = _musim_ke_tahun_bbref(musim)
        result = fetch_team_advanced(season=tahun)
        if not result.ok:
            raise RuntimeError(f"rating BBRef musim {musim} gagal: {result.error}")
        mentah_path = data_dir / f"ratings_bbref_{musim}.json"
        mentah_path.write_text(
            json.dumps(result.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        per_tim: dict[str, dict[str, float]] = {}
        for tim in result.data or []:
            tricode = BBREF_TEAM_TRICODES.get(tim.get("team"))
            if tricode is None:
                continue
            per_tim[tricode] = {
                "off_rtg": tim.get("off_rtg"),
                "def_rtg": tim.get("def_rtg"),
                "net_rtg": tim.get("net_rtg"),
                "pace": tim.get("pace"),
            }
        ratings[musim] = per_tim
    return ratings


def load_games(
    seasons: list[str], games_file: str | None, data_dir: Path
) -> list[dict]:
    """Muat game log: dari --games-file, atau fetch_league_games.

    Raise RuntimeError bila sumber tidak tersedia (pesan jelas).
    """
    if games_file:
        path = Path(games_file)
        if not path.exists():
            raise RuntimeError(f"file game log tidak ditemukan: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise RuntimeError(f"file game log harus berisi list: {path}")
        return data
    try:
        from ingest.stats_nba import fetch_league_games
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "ingest.stats_nba.fetch_league_games belum tersedia "
            "(kontrak worker data Tahap 3) — jalankan lagi setelah "
            "worker data selesai, atau pakai --games-file dengan JSON "
            "game log (lihat docstring modul). "
            f"Detail teknis: {exc}"
        ) from exc
    games: list[dict] = []
    data_dir.mkdir(parents=True, exist_ok=True)
    for musim in seasons:
        result = fetch_league_games(season=musim)
        if not result.ok:
            raise RuntimeError(f"game log musim {musim} gagal: {result.error}")
        records = result.data or []
        # Record kontrak tidak membawa "season" — cap dari argumen
        # musim (dipakai fit_parameters untuk lookup rating per musim).
        for game in records:
            game.setdefault("season", musim)
        mentah_path = data_dir / f"games_{musim}.json"
        mentah_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        games.extend(records)
    return games


def main(argv: list[str] | None = None) -> int:
    """Jalankan fit dari CLI. 0 sukses, 2 data/sumber tidak tersedia."""
    parser = argparse.ArgumentParser(
        description="Fit parameter simulasi NBA dari data historis."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=["2024-25", "2025-26", "2026-27"],
        help="musim yang dipakai (default: 2024-25 2025-26 2026-27)",
    )
    parser.add_argument(
        "--games-file",
        default=None,
        help="JSON game log (bila fetch_league_games belum tersedia)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/nba_history",
        help="direktori simpan data mentah (default: data/nba_history)",
    )
    parser.add_argument(
        "--out",
        default="out/fit_nba_params.json",
        help="file JSON hasil fit (default: out/fit_nba_params.json)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / args.data_dir
    out_path = repo_root / args.out

    try:
        cfg = config_mod.load_playstyle()
        min_games = int(
            config_mod.get_value(cfg, "simulation", "fitting", "min_games_total")
        )
        min_group = int(
            config_mod.get_value(cfg, "simulation", "fitting", "min_group_n")
        )
    except config_mod.ConfigError as exc:
        print(f"config tidak lengkap: {exc}", file=sys.stderr)
        return 2
    try:
        games = load_games(args.seasons, args.games_file, data_dir)
        ratings = load_ratings(args.seasons, data_dir)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"fit dibatalkan: {exc}", file=sys.stderr)
        return 2

    hasil = fit_parameters(games, ratings, min_games, min_group)
    hasil["seasons"] = args.seasons
    hasil["games_source"] = args.games_file or "ingest.stats_nba.fetch_league_games"
    hasil["ratings_source"] = "ingest.bbref.fetch_team_advanced (BBRef)"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"laga dipakai: {hasil['n_games_used']} "
        f"(dilewati tanpa rating: {hasil['n_games_skipped_no_rating']})"
    )
    for nama, param in hasil["parameters"].items():
        nilai = param.get("value")
        if nilai is None:
            print(f"  {nama}: null ({param.get('reason')})")
        else:
            n_tampil = param.get("n", param.get("n_b2b", param.get("n_alt_home", "?")))
            print(f"  {nama}: {nilai} (n={n_tampil})")
    print(f"hasil fit ditulis ke {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
