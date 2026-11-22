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
      Perbaikan itu SUDAH DIBUAT (patch 1b, temuan auditor 1) — lihat
      "MODE ROLLING" di bawah.
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

MODE ROLLING (--rolling; patch 1b, temuan auditor 1 — validasi
out-of-sample). Proyeksi memakai rating ROLLING POINT-IN-TIME:
untuk tiap laga, rating tiap tim dihitung HANYA dari laga sebelum
tanggal laga itu (musim-berjalan + last10-berjalan), dari box score
game log leaguegamefinder (kolom FGA/FTA/OREB/TOV/PTS/MIN dari
respons mentah endpoint yang sama dengan fetch_league_games —
parser kontrak hanya menyimpan PTS, jadi skrip ini mem-parse
respons mentahnya sendiri; lihat parse_boxscores_leaguegamefinder).
Rumus possessions Dean Oliver: POSS = FGA + 0,44*FTA - OREB + TOV.
off_rtg = 100*PTS/POSS sendiri; def_rtg = 100*PTS_lawan/POSS_lawan;
pace = 240*POSS/MIN_tim (POSS per 48 menit; MIN_tim = jumlah menit
pemain, 240 untuk laga regulasi).

Keputusan desain rolling (D-R1 s.d. D-R5; didokumentasikan juga di
LAPORAN-FIT-NBA.md §12):
  D-R1 PRIOR = rating BBRef musim SEBELUMNYA untuk tim itu (data
      masa lalu, bukan look-ahead). Untuk 2024-25, priornya rating
      BBRef 2023-24 (di-fetch sekali, di-cache).
  D-R2 SHRINKAGE awal musim: rating = (n*obs + K*prior)/(n+K),
      K = 10 laga (SHRINKAGE_K_GAMES). n=0 -> prior persis; n=10 ->
      50/50; n=82 -> ~89% observasi.
  D-R3 Last10 di-shrink ke RATING MUSIM (bukan ke prior) — hirarki
      prior -> musim -> last10, agar prior musim lalu tidak
      dihitung ganda di komponen last10.
  D-R4 Jendela reset tiap musim (musim-berjalan + last10-berjalan
      hanya dalam musim yang sama); carryover antar musim hanya
      lewat prior D-R1.
  D-R5 Rata-rata liga (lg_avg) juga point-in-time: rata-rata
      off_rtg efektif ke-30 tim pada tanggal laga itu (tim yang
      belum main menyumbang priornya). Rating efektif yang masuk
      project_points = gabungan 60% musim + 40% last10 (bobot
      recency dari config — SAMA seperti yang dipakai sim, jadi fit
      rolling mengukur persis rumus yang dipakai mesin; fit v1
      memakai 100% rating musim penuh).
  Keterbatasan yang TETAP ADA di mode rolling: last10/cedera per
  tanggal untuk laga historis tetap tidak tersedia di tingkat
  PEMAIN (tidak ada data cedera per tanggal) — backtest tetap tanpa
  penyesuaian pemain absen; last10 di sini adalah last10 STATISTIK
  TIM, bukan skuad.

Data:
  - Box score (mode rolling saja): via fetch mentah leaguegamefinder
    (3 panggilan keyless, gratis, 0 kredit Odds API), di-cache ke
    data/nba_history/boxscores_{musim}.json (+ boxscores_all.json).
    Bila file cache sudah ada, tidak ada panggilan network.
  - Prior (mode rolling saja): rating BBRef musim sebelumnya, cache
    ratings_bbref_{musim-sebelumnya}.json (lihat load_prior_ratings).
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
  Mode rolling (patch 1b):
  python3 scripts/fit_nba_params.py --rolling
      [--boxscores-file data/nba_history/boxscores_all.json]
      [--out out/fit_nba_params_rolling.json]
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

# --- Rating rolling point-in-time (patch 1b) ---
# Bobot prior shrinkage, setara K laga (keputusan desain D-R2).
SHRINKAGE_K_GAMES = 10
# Ukuran jendela last10 (sama seperti definisi last10 di sim).
LAST10_N = 10
# Koefisien possessions Dean Oliver: POSS = FGA + 0,44*FTA - OREB + TOV.
POSS_FTA_COEF = 0.44
# Menit tim satu laga regulasi (5 pemain x 48 menit) — penyebut pace.
TEAM_MINUTES_REGULATION = 240.0


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


# ---------------------------------------------------------------------------
# Rating rolling point-in-time (patch 1b, temuan auditor 1)
# ---------------------------------------------------------------------------


def hitung_possessions(fga, fta, oreb, tov) -> float | None:
    """Possessions Dean Oliver: FGA + 0,44*FTA - OREB + TOV.

    Mengembalikan None bila ada input bukan angka (bool bukan angka).
    """
    nilai = (fga, fta, oreb, tov)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in nilai):
        return None
    return float(fga) + POSS_FTA_COEF * float(fta) - float(oreb) + float(tov)


def _pecah_matchup(matchup: str) -> tuple[str, str] | None:
    """Pecah MATCHUP leaguegamefinder jadi (tricode_kandang, tricode_tandang).

    Disalin dari logika ingest.stats_nba._split_matchup agar skrip ini
    mandiri: "SAS vs. NOP" -> ("SAS", "NOP"); "BOS @ DET" -> ("DET", "BOS").
    """
    if " vs. " in matchup:
        home, away = matchup.split(" vs. ", 1)
        return home.strip(), away.strip()
    if " @ " in matchup:
        away, home = matchup.split(" @ ", 1)
        return home.strip(), away.strip()
    return None


def _pasangkan_baris_boxscore(rows: list[dict]) -> tuple[dict, dict] | None:
    """Pasangkan 2 baris satu laga -> (baris_kandang, baris_tandang).

    Logika yang sama dengan ingest.stats_nba._pair_game_rows (tahan
    terhadap anomali data stats.nba.com: laga 0022600189 menulis
    "DEN @ IND" di kedua baris — string "@ IND" tetap menunjuk IND
    sebagai kandang). None bila tidak bisa dipasangkan.
    """
    if len(rows) != 2:
        return None
    by_tricode = {row.get("TEAM_ABBREVIATION"): row for row in rows}
    if len(by_tricode) != 2 or None in by_tricode:
        return None
    for row in rows:
        split = _pecah_matchup(str(row.get("MATCHUP") or ""))
        if split is None:
            continue
        home_tri, away_tri = split
        if {home_tri, away_tri} != set(by_tricode):
            continue
        return by_tricode[home_tri], by_tricode[away_tri]
    return None


def _angka_atau_none(nilai) -> float | None:
    """Ubah nilai jadi float; None bila bukan angka (bool bukan angka)."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    return float(nilai)


def parse_boxscores_leaguegamefinder(
    data: dict, season: str
) -> tuple[list[dict], dict]:
    """Ubah respons mentah leaguegamefinder jadi record box score per tim-laga.

    Tiap record: season, game_id, game_date, tricode, opp_tricode,
    is_home, pts, poss (Dean Oliver), pts_lawan, poss_lawan, minutes
    (menit tim; None bila tidak ada — laga itu tetap dipakai untuk
    off/def, tapi tidak untuk pace). Laga yang tidak bisa dipasangkan
    atau possessions-nya tidak bisa dihitung dilewati + dicatat di
    info (bukan dikarang). Raise ValueError("stats_nba_format_changed")
    bila resultSet LeagueGameFinderResults tidak ada.
    """
    sets = {
        rs.get("name"): rs
        for rs in data.get("resultSets") or []
        if isinstance(rs, dict)
    }
    if "LeagueGameFinderResults" not in sets:
        raise ValueError("stats_nba_format_changed")
    rs = sets["LeagueGameFinderResults"]
    headers = rs.get("headers") or []
    by_game: dict[str, list[dict]] = {}
    for row in rs.get("rowSet") or []:
        record = dict(zip(headers, row, strict=False))
        game_id = record.get("GAME_ID")
        if game_id is None:
            continue
        by_game.setdefault(str(game_id), []).append(record)
    records: list[dict] = []
    n_tidak_berpasangan = 0
    n_tanpa_possessions = 0
    for game_rows in by_game.values():
        pasangan = _pasangkan_baris_boxscore(game_rows)
        if pasangan is None:
            n_tidak_berpasangan += 1
            continue
        home_row, away_row = pasangan
        poss_home = hitung_possessions(
            home_row.get("FGA"),
            home_row.get("FTA"),
            home_row.get("OREB"),
            home_row.get("TOV"),
        )
        poss_away = hitung_possessions(
            away_row.get("FGA"),
            away_row.get("FTA"),
            away_row.get("OREB"),
            away_row.get("TOV"),
        )
        pts_home = _angka_atau_none(home_row.get("PTS"))
        pts_away = _angka_atau_none(away_row.get("PTS"))
        if (
            poss_home is None
            or poss_away is None
            or pts_home is None
            or pts_away is None
        ):
            n_tanpa_possessions += 1
            continue
        game_date = str(home_row.get("GAME_DATE") or "")[:10]
        game_id = str(home_row.get("GAME_ID"))
        for row, tri, opp, is_home, pts, poss, pts_lawan, poss_lawan in (
            (
                home_row,
                home_row.get("TEAM_ABBREVIATION"),
                away_row.get("TEAM_ABBREVIATION"),
                True,
                pts_home,
                poss_home,
                pts_away,
                poss_away,
            ),
            (
                away_row,
                away_row.get("TEAM_ABBREVIATION"),
                home_row.get("TEAM_ABBREVIATION"),
                False,
                pts_away,
                poss_away,
                pts_home,
                poss_home,
            ),
        ):
            records.append(
                {
                    "season": season,
                    "game_id": game_id,
                    "game_date": game_date,
                    "tricode": tri,
                    "opp_tricode": opp,
                    "is_home": is_home,
                    "pts": pts,
                    "poss": poss,
                    "pts_lawan": pts_lawan,
                    "poss_lawan": poss_lawan,
                    "minutes": _angka_atau_none(row.get("MIN")),
                }
            )
    info = {
        "season": season,
        "n_laga_mentah": len(by_game),
        "n_record": len(records),
        "n_laga_tidak_berpasangan": n_tidak_berpasangan,
        "n_laga_tanpa_possessions": n_tanpa_possessions,
    }
    return records, info


def fetch_boxscores(seasons: list[str], data_dir: Path) -> list[dict]:
    """Ambil box score leaguegamefinder per musim (cache per musim).

    Satu panggilan keyless gratis per musim (0 kredit Odds API);
    hasilnya di-cache ke data_dir/boxscores_{musim}.json — bila file
    cache sudah ada, musim itu tidak di-fetch lagi. Raise RuntimeError
    bila fetch gagal (pesan jelas).
    """
    from ingest.common import (
        DiskCache,
        HttpClient,
        RateLimiter,
        default_cache_dir,
        parse_json_body,
    )
    from ingest.stats_nba import LEAGUE_GAMES_URL, STATS_HEADERS

    client = HttpClient(
        RateLimiter(1.0),
        cache=DiskCache(default_cache_dir(), 600),
        extra_headers=STATS_HEADERS,
    )
    records_semua: list[dict] = []
    data_dir.mkdir(parents=True, exist_ok=True)
    for musim in seasons:
        cache_path = data_dir / f"boxscores_{musim}.json"
        if cache_path.exists():
            data_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(data_cache, list):
                raise RuntimeError(f"cache box score bukan list: {cache_path}")
            records_semua.extend(data_cache)
            continue
        url = (
            f"{LEAGUE_GAMES_URL}?LeagueID=00&Season={musim}"
            "&SeasonType=Regular%20Season&PlayerOrTeam=T"
        )
        resp = client.get(url, use_cache=False)
        if resp.get("status") != 200:
            raise RuntimeError(
                f"box score musim {musim} gagal: http_{resp.get('status')}: "
                f"{resp.get('error') or 'leaguegamefinder gagal'}"
            )
        data = parse_json_body(resp)
        if not isinstance(data, dict):
            raise RuntimeError(
                f"box score musim {musim} gagal: stats_nba_format_changed"
            )
        try:
            records, _info = parse_boxscores_leaguegamefinder(data, musim)
        except ValueError as exc:
            raise RuntimeError(f"box score musim {musim} gagal: {exc}") from exc
        cache_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        records_semua.extend(records)
    return records_semua


def load_boxscores(
    seasons: list[str], boxscores_file: str | None, data_dir: Path
) -> list[dict]:
    """Muat box score: dari --boxscores-file, atau cache/fetch per musim.

    Bila lewat cache/fetch, file gabungan boxscores_all.json juga
    ditulis ke data_dir (cermin games_all.json). Raise RuntimeError
    bila sumber tidak tersedia.
    """
    if boxscores_file:
        path = Path(boxscores_file)
        if not path.exists():
            raise RuntimeError(f"file box score tidak ditemukan: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise RuntimeError(f"file box score harus berisi list: {path}")
        return data
    records = fetch_boxscores(seasons, data_dir)
    gabung = data_dir / "boxscores_all.json"
    gabung.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records


def _musim_sebelumnya(musim: str) -> str:
    """Ubah "2024-25" -> "2023-24" (musim sebelumnya)."""
    try:
        awal, akhir = musim.split("-")
        return f"{int(awal) - 1}-{int(akhir) - 1:02d}"
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"format musim tidak valid: {musim!r}") from exc


def load_prior_ratings(seasons: list[str], data_dir: Path) -> dict:
    """Rating prior per musim = rating BBRef musim SEBELUMNYA (D-R1).

    Data masa lalu, bukan look-ahead. Cache: ratings_bbref_{musim
    sebelumnya}.json; bila belum ada, di-fetch via load_ratings
    (satu panggilan BBRef per musim yang belum ter-cache).
    Mengembalikan {musim: {tricode: {off_rtg, def_rtg, net_rtg, pace}}}.
    """
    priors: dict[str, dict[str, dict[str, float]]] = {}
    for musim in seasons:
        musim_lalu = _musim_sebelumnya(musim)
        path = data_dir / f"ratings_bbref_{musim_lalu}.json"
        if path.exists():
            mentah = json.loads(path.read_text(encoding="utf-8"))
            per_tim: dict[str, dict[str, float]] = {}
            for tim in mentah:
                tricode = BBREF_TEAM_TRICODES.get(tim.get("team"))
                if tricode is None:
                    continue
                per_tim[tricode] = {
                    "off_rtg": tim.get("off_rtg"),
                    "def_rtg": tim.get("def_rtg"),
                    "net_rtg": tim.get("net_rtg"),
                    "pace": tim.get("pace"),
                }
            priors[musim] = per_tim
        else:
            priors[musim] = load_ratings([musim_lalu], data_dir)[musim_lalu]
    return priors


def _agregat_jendela(
    jendela: list[dict],
) -> tuple[float | None, float | None, float | None, int, int]:
    """Agregat satu jendela team-game -> (off, def, pace, n, n_pace).

    off = 100*PTS/POSS sendiri; def = 100*PTS_lawan/POSS_lawan;
    pace = 240*POSS/MIN (hanya laga dengan menit valid). Nilai None
    bila jendela kosong / tidak ada possessions / tidak ada menit
    valid. n = jumlah laga jendela; n_pace = jumlah laga bermenit valid.
    """
    n = len(jendela)
    if n == 0:
        return None, None, None, 0, 0
    pts = poss = pts_lawan = poss_lawan = 0.0
    poss_menit = menit = 0.0
    n_pace = 0
    for rec in jendela:
        pts += rec["pts"]
        poss += rec["poss"]
        pts_lawan += rec["pts_lawan"]
        poss_lawan += rec["poss_lawan"]
        menit_rec = rec.get("minutes")
        if isinstance(menit_rec, (int, float)) and menit_rec > 0:
            poss_menit += rec["poss"]
            menit += menit_rec
            n_pace += 1
    off = 100.0 * pts / poss if poss > 0 else None
    deff = 100.0 * pts_lawan / poss_lawan if poss_lawan > 0 else None
    pace = TEAM_MINUTES_REGULATION * poss_menit / menit if menit > 0 else None
    return off, deff, pace, n, n_pace


def _shrink(nilai_obs: float | None, n: int, nilai_prior: float, k: int) -> float:
    """Shrinkage: (n*obs + k*prior)/(n+k) (D-R2).

    n=0 atau observasi None -> prior persis.
    """
    if nilai_obs is None or n <= 0:
        return float(nilai_prior)
    return (n * nilai_obs + k * nilai_prior) / (n + k)


def bangun_rating_rolling(
    games: list[dict],
    boxscores: list[dict],
    priors: dict[str, dict[str, dict[str, float]]],
    w_musim: float = 0.6,
    w_last10: float = 0.4,
    k_prior: int = SHRINKAGE_K_GAMES,
) -> tuple[dict, dict]:
    """Bangun rating rolling point-in-time untuk tiap laga di `games`.

    Untuk tiap laga, rating tiap tim dihitung HANYA dari laga sebelum
    tanggal laga itu (musim-berjalan + last10-berjalan, D-R4). Proses
    berjalan tanggal demi tanggal (gabungan tanggal laga + tanggal
    box score, menaik): snapshot rating semua laga tanggal itu DULU,
    baru update state dengan box score tanggal itu — jadi box score
    satu tanggal tidak pernah memengaruhi laga tanggal yang sama.

    Mengembalikan (per_laga, info). per_laga: {game_id: {
      "home"/"away": {"stats_season": {off_rtg, def_rtg, pace},
                      "stats_last10": {off_rtg, def_rtg, pace},
                      "n_musim": int, "n_last10": int},
      "home_efektif"/"away_efektif": {off_rtg, def_rtg, pace, net_rtg}
        (gabungan w_musim/w_last10 — yang masuk project_points),
      "lg_avg_off_rtg": float (rata-rata off_rtg efektif ke-30 tim
        pada tanggal itu, D-R5),
    }}. Laga yang salah satu timnya tanpa prior lengkap dilewati +
    dicatat di info["n_laga_tanpa_prior"] (bukan dikarang).
    """
    w_total = w_musim + w_last10
    if w_total <= 0:
        raise ValueError("bobot recency harus berjumlah > 0")
    box_per_tanggal: dict[tuple[str, str], list[dict]] = {}
    for rec in boxscores:
        kunci = (str(rec.get("season")), str(rec.get("game_date") or "")[:10])
        box_per_tanggal.setdefault(kunci, []).append(rec)
    laga_per_tanggal: dict[tuple[str, str], list[dict]] = {}
    for game in games:
        kunci = (str(game.get("season")), str(game.get("game_date") or "")[:10])
        laga_per_tanggal.setdefault(kunci, []).append(game)
    # State per (musim, tricode): team-game SEBELUM tanggal berjalan.
    state: dict[tuple[str, str], list[dict]] = {}
    # Rating efektif saat ini per (musim, tricode); awal = prior (n=0).
    efektif: dict[tuple[str, str], dict[str, float]] = {}
    for musim, per_tim in priors.items():
        for tricode, rating in per_tim.items():
            if any(rating.get(k) is None for k in ("off_rtg", "def_rtg", "pace")):
                continue
            efektif[(musim, tricode)] = {
                "off_rtg": float(rating["off_rtg"]),
                "def_rtg": float(rating["def_rtg"]),
                "pace": float(rating["pace"]),
            }

    def _rating_tim(musim: str, tricode: str):
        """Rating tim saat ini dari state.

        Mengembalikan (stats_musim, stats_last10, efektif, n_musim,
        n_last10), atau None bila prior tim tidak lengkap.
        """
        prior = (priors.get(musim) or {}).get(tricode)
        if prior is None or any(
            prior.get(k) is None for k in ("off_rtg", "def_rtg", "pace")
        ):
            return None
        jendela = state.get((musim, tricode), [])
        off, deff, pace, n, n_pace = _agregat_jendela(jendela)
        stats_musim = {
            "off_rtg": _shrink(off, n, prior["off_rtg"], k_prior),
            "def_rtg": _shrink(deff, n, prior["def_rtg"], k_prior),
            "pace": _shrink(pace, n_pace, prior["pace"], k_prior),
        }
        j10 = jendela[-LAST10_N:]
        off10, def10, pace10, n10, n10_pace = _agregat_jendela(j10)
        stats_last10 = {
            "off_rtg": _shrink(off10, n10, stats_musim["off_rtg"], k_prior),
            "def_rtg": _shrink(def10, n10, stats_musim["def_rtg"], k_prior),
            "pace": _shrink(pace10, n10_pace, stats_musim["pace"], k_prior),
        }
        rating_efektif = {
            field: (w_musim * stats_musim[field] + w_last10 * stats_last10[field])
            / w_total
            for field in ("off_rtg", "def_rtg", "pace")
        }
        rating_efektif["net_rtg"] = (
            rating_efektif["off_rtg"] - rating_efektif["def_rtg"]
        )
        return stats_musim, stats_last10, rating_efektif, n, n10

    per_laga: dict[str, dict] = {}
    info = {
        "n_laga": len(games),
        "n_laga_tanpa_prior": 0,
        "n_laga_tanpa_lg_avg": 0,
        "n_boxscore": len(boxscores),
        "k_prior": k_prior,
        "w_musim": w_musim,
        "w_last10": w_last10,
    }
    semua_tanggal = sorted(set(laga_per_tanggal) | set(box_per_tanggal))
    for musim, tanggal in semua_tanggal:
        for game in laga_per_tanggal.get((musim, tanggal), []):
            home = game.get("home_tricode")
            away = game.get("away_tricode")
            r_home = _rating_tim(musim, home)
            r_away = _rating_tim(musim, away)
            if r_home is None or r_away is None:
                info["n_laga_tanpa_prior"] += 1
                continue
            off_liga = [
                efektif[(musim, tri)]["off_rtg"]
                for tri in (priors.get(musim) or {})
                if (musim, tri) in efektif
            ]
            if not off_liga:
                info["n_laga_tanpa_lg_avg"] += 1
                continue
            lg_avg = statistics.fmean(off_liga)
            per_laga[str(game.get("game_id"))] = {
                "home": {
                    "stats_season": r_home[0],
                    "stats_last10": r_home[1],
                    "n_musim": r_home[3],
                    "n_last10": r_home[4],
                },
                "away": {
                    "stats_season": r_away[0],
                    "stats_last10": r_away[1],
                    "n_musim": r_away[3],
                    "n_last10": r_away[4],
                },
                "home_efektif": r_home[2],
                "away_efektif": r_away[2],
                "lg_avg_off_rtg": lg_avg,
            }
        for rec in box_per_tanggal.get((musim, tanggal), []):
            kunci_state = (musim, rec["tricode"])
            state.setdefault(kunci_state, []).append(rec)
            rating_baru = _rating_tim(musim, rec["tricode"])
            if rating_baru is not None:
                efektif[kunci_state] = rating_baru[2]
    info["n_laga_dengan_rating"] = len(per_laga)
    return per_laga, info


def fit_parameters(
    games: list[dict],
    ratings: dict[str, dict[str, dict[str, float]]],
    min_games_total: int = 100,
    min_group_n: int = 30,
    rolling: dict | None = None,
) -> dict:
    """Fit semua parameter NBA dari game log + rating musim penuh.

    games: list dict per laga (lihat docstring modul). ratings:
    {musim: {tricode: {off_rtg, def_rtg, net_rtg, pace}}}.
    min_games_total/min_group_n: ambang minimum data (dari config
    simulation.fitting bila dipanggil lewat main; default di sini
    hanya untuk pemakaian langsung/fixture).
    rolling: bila diberikan (dict game_id -> data dari
    bangun_rating_rolling), proyeksi memakai rating rolling
    point-in-time + lg_avg per laga, dan `ratings` diabaikan.
    Mengembalikan dict hasil fit; tiap parameter berisi value (atau
    null + reason), n, dan bukti statistiknya.
    """
    mode_rolling = rolling is not None
    hasil: dict = {
        "method": "lihat docstring scripts/fit_nba_params.py + LAPORAN-FIT-NBA.md",
        "ratings_mode": "rolling" if mode_rolling else "musim_penuh",
        "look_ahead_bias": (
            "tidak ada — rating rolling point-in-time (hanya laga "
            "sebelum tanggal laga; prior = rating BBRef musim "
            "sebelumnya)"
            if mode_rolling
            else (
                "rating musim penuh melihat masa depan (termasuk laga yang "
                "diproyeksikan) — residual sedikit terlalu kecil, sigma "
                "sedikit underestimate"
            )
        ),
        "n_games_input": len(games),
        "n_games_used": 0,
        "n_games_skipped_no_rating": 0,
        "n_games_skipped_no_rolling": 0,
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
        home = game.get("home_tricode")
        away = game.get("away_tricode")
        home_pts = game.get("home_pts")
        away_pts = game.get("away_pts")
        if home_pts is None or away_pts is None:
            hasil["n_games_skipped_no_rating"] += 1
            continue
        if mode_rolling:
            data_rolling = rolling.get(str(game.get("game_id")))
            if data_rolling is None:
                hasil["n_games_skipped_no_rolling"] += 1
                continue
            rating_home = data_rolling["home_efektif"]
            rating_away = data_rolling["away_efektif"]
            lg_avg = data_rolling["lg_avg_off_rtg"]
        else:
            rating_musim = ratings.get(musim)
            if (
                rating_musim is None
                or home not in rating_musim
                or away not in rating_musim
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
                r["off_rtg"]
                for r in rating_musim.values()
                if r.get("off_rtg") is not None
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
    parser.add_argument(
        "--rolling",
        action="store_true",
        help="mode rolling point-in-time (patch 1b): proyeksi memakai "
        "rating rolling dari box score, bukan rating musim penuh",
    )
    parser.add_argument(
        "--boxscores-file",
        default=None,
        help="JSON box score gabungan (mode rolling; bila tidak ada, "
        "cache/fetch per musim dari data dir)",
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
        if args.rolling:
            w_musim = float(
                config_mod.get_value(cfg, "simulation", "nba", "recency", "season")
            )
            w_last10 = float(
                config_mod.get_value(cfg, "simulation", "nba", "recency", "last10")
            )
            boxscores = load_boxscores(args.seasons, args.boxscores_file, data_dir)
            priors = load_prior_ratings(args.seasons, data_dir)
            rolling_data, info_rolling = bangun_rating_rolling(
                games, boxscores, priors, w_musim, w_last10
            )
            hasil = fit_parameters(
                games, {}, min_games, min_group, rolling=rolling_data
            )
            hasil["rolling_info"] = info_rolling
            hasil["boxscores_source"] = (
                args.boxscores_file or "leaguegamefinder mentah (cache/fetch)"
            )
            hasil["priors_source"] = "rating BBRef musim sebelumnya (cache/fetch)"
            hasil["ratings_source"] = (
                "rating rolling point-in-time dari box score "
                "leaguegamefinder + prior BBRef musim sebelumnya"
            )
        else:
            ratings = load_ratings(args.seasons, data_dir)
            hasil = fit_parameters(games, ratings, min_games, min_group)
            hasil["ratings_source"] = "ingest.bbref.fetch_team_advanced (BBRef)"
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"fit dibatalkan: {exc}", file=sys.stderr)
        return 2

    hasil["seasons"] = args.seasons
    hasil["games_source"] = args.games_file or "ingest.stats_nba.fetch_league_games"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"laga dipakai: {hasil['n_games_used']} "
        f"(dilewati tanpa rating: {hasil['n_games_skipped_no_rating']}"
        f", tanpa rolling: {hasil['n_games_skipped_no_rolling']})"
    )
    if args.rolling:
        info_r = hasil["rolling_info"]
        print(
            f"rolling: {info_r['n_laga_dengan_rating']} laga dengan rating, "
            f"{info_r['n_boxscore']} record box score, "
            f"k_prior={info_r['k_prior']}, "
            f"bobot {info_r['w_musim']}/{info_r['w_last10']}"
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
