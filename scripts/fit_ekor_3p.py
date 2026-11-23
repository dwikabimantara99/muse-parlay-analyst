"""Fit ekor 3 poin per laga: apakah residual total membesar saat laju 3PA gabungan tinggi?

PERTANYAAN (item 4 build penyempurnaan mesin, pasca-DEN@CHI 22 Nov 2026):
sim sekarang memakai satu sigma_total global (18,9868) untuk semua laga,
padahal laga dua tim penembak tripoin diduga ekornya lebih gemuk. Skrip
ini MENGUJI dugaan itu pada data, bukan mengasumsikannya.

METODE (didokumentasikan di sini + LAPORAN-EKOR-3P.md):

  (a) RESIDUAL. Seperti scripts/fit_nba_params.py mode rolling: setiap
      laga historis diproyeksikan dengan engine.nba_sim.project_points
      memakai rating ROLLING POINT-IN-TIME (hanya laga sebelum tanggal
      laga; prior = rating BBRef musim sebelumnya) — residual total
      dan margin = aktual - proyeksi. Fungsi rolling DIPAKAI ULANG
      dari fit_nba_params (tidak diduplikasi).
  (b) LAJU 3PA POINT-IN-TIME. Untuk tiap laga, laju 3PA/laga tiap tim
      dihitung HANYA dari laga SEBELUM tanggal laga itu (musim yang
      sama): 3PA gabungan = laju kandang + laju tandang. Sumber FG3A/
      FG3M/FGA per team-game: respons mentah leaguegamefinder yang
      SAMA dengan fit_nba_params (kolom FG3A/FG3M/FGA ada di respons
      itu; parser kontrak hanya membuangnya). Laga yang belum selesai
      saat snapshot (WL kosong — 4 laga 22 Nov 2026) DIKECUALIKAN:
      bukan observasi laga penuh (pelajaran kontaminasi p90 di
      engine/stress.py). Tim dengan laga sebelumnya < MIN_LAGA membuat
      laganya dilewati dari fit (laju terlalu noisy) + dicatat.
  (c) REGRESI VARIANS (model utama). OLS resid_total^2 ~ a + b x
      3PA_gabung. Bila b > 0 signifikan, sigma_total per laga =
      akar(a + b x 3PA_gabung) — model varians-linear yang dipakai
      engine/nba_sim.py (config ekor_3p). Uji yang sama diulang pada
      resid_margin^2, |resid_total|, |resid_margin|, dan prediktor
      alternatif (3P% gabungan, volatilitas 3PM per tim, share 3PA,
      varians 3P binomial tersirat, max/min laju tim) + tabel kuartil
      dan kuantil ekor atas per kuartil — agar verdict tidak
      bergantung pada satu spesifikasi.
  (d) SLOPE BINOMIAL TEORITIS (pembanding, bukan fit). Varians poin
      tripoin satu tim = n x p(1-p) x 9 (n percobaan, p = 3P%).
      Dengan p kedua tim ~ p_rata-rata liga, varians 3P gabungan ~
      9 x p(1-p) x 3PA_gabung, jadi slope teoritis = 9 x p(1-p)
      (p dari sampel fit). Bila slope fit jauh di bawah nilai ini,
      mekanisme binomial TIDAK menembus ke varians residual total
      (mis. karena komponen varians lain berkorelasi negatif dengan
      laju 3PA, atau efeknya di bawah daya deteksi).
  (e) VERDICT. Signifikan bila |t| >= 2,0 pada regresi utama
      (ambang ~p<0,05 dua sisi untuk n besar — pilihan desain yang
      didokumentasikan). Bila tidak signifikan, slope AKTIF yang
      direkomendasikan = 0,0 (mengikuti preseden altitude di
      LAPORAN-FIT-NBA.md: nilai fit dalam noise tidak diadopsi) dan
      sim tetap memakai sigma global sampai kalibrasi ulang.

Data:
  - Game log + box score + prior: SAMA dengan fit_nba_params
    --rolling (data/nba_history/games_all.json,
    boxscores_all.json, ratings_bbref_*.json; gitignored).
  - FG3A per team-game: diekstrak dari respons mentah
    leaguegamefinder — dibaca dari DiskCache out/cache/ (kunci =
    SHA-256 URL, TTL DIABAIKAN: snapshot historis; musim
    2024-25/2025-26 sudah selesai sehingga snapshotnya final,
    2026-27 tercatat tanggal snapshotnya di output) atau di-fetch
    langsung (keyless, gratis, 0 kredit Odds API) bila cache tidak
    ada. Hasil ekstraksi ditulis ke
    data/nba_history/fg3a_{musim}.json (+ fg3a_all.json) agar fit
    bisa diulang tanpa network/cache.
  - Hasil fit ke out/fit_ekor_3p.json (gitignored) + print ringkasan.

Aturan: JANGAN mengarang angka. Bila data tidak cukup (di bawah
ambang simulation.fitting di playstyle.yaml), parameter ditulis
null + alasan.

Jalankan dari root repo:
  python3 scripts/fit_ekor_3p.py [--seasons 2024-25 2025-26 2026-27]
      [--games-file data/nba_history/games_all.json]
      [--boxscores-file data/nba_history/boxscores_all.json]
      [--out out/fit_ekor_3p.json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine.nba_sim import project_points

# Muat fit_nba_params sebagai modul (scripts/ bukan package).
_SPEK_FIT = importlib.util.spec_from_file_location(
    "fit_nba_params", Path(__file__).resolve().parent / "fit_nba_params.py"
)
fit_nba_params = importlib.util.module_from_spec(_SPEK_FIT)
_SPEK_FIT.loader.exec_module(fit_nba_params)

# Jumlah minimum laga sebelumnya agar laju 3PA satu tim dipakai
# (keputusan desain, seperti SHRINKAGE_K_GAMES di fit_nba_params):
# di bawah 5 laga, laju musim berjalan terlalu noisy untuk jadi
# prediktor. Laga yang salah satu timnya di bawah ambang ini
# dilewati dari fit + dicatat (bukan ditebak).
MIN_LAGA_UNTUK_LAJU = 5

# Ambang signifikansi verdict (lihat docstring modul butir (e)).
AMBANG_T_SIGNIFIKAN = 2.0


def _kuantil(nilai_urut: list[float], q: float) -> float:
    """Kuantil q (0-1) dari daftar yang sudah terurut (interpolasi linear)."""
    n = len(nilai_urut)
    pos = q * (n - 1)
    bawah = int(pos)
    atas = min(bawah + 1, n - 1)
    frac = pos - bawah
    return nilai_urut[bawah] * (1.0 - frac) + nilai_urut[atas] * frac


def ols(xs: list[float], ys: list[float]) -> dict:
    """OLS y ~ a + b*x. Kembalikan dict (a, b, se_b, t_b, r2, n).

    se_b = standard error SLOPE (yang dipakai verdict; berbeda dari
    _regresi_linear_sederhana di fit_nba_params yang mengembalikan
    SE intersep). Raise ValueError bila n < 3 atau varians x = 0.
    """
    n = len(xs)
    if n < 3:
        raise ValueError(f"regresi butuh n >= 3, didapat {n}")
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("regresi gagal: varians x = 0")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intersep = mean_y - slope * mean_x
    sse = sum((y - (intersep + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    sst = sum((y - mean_y) ** 2 for y in ys)
    mse = sse / (n - 2)
    se_b = math.sqrt(mse / sxx)
    t_b = slope / se_b if se_b > 0 else 0.0
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    return {
        "a": intersep,
        "b": slope,
        "se_b": se_b,
        "t_b": t_b,
        "r2": r2,
        "n": n,
    }


def _hasil_ols(regresi: dict) -> dict:
    """Ringkasan regresi untuk JSON (dibulatkan, + CI 95% slope)."""
    b = regresi["b"]
    se = regresi["se_b"]
    return {
        "intersep": round(regresi["a"], 4),
        "slope": round(b, 4),
        "se_slope": round(se, 4),
        "t_slope": round(regresi["t_b"], 2),
        "r2": round(regresi["r2"], 4),
        "n": regresi["n"],
        "ci95_slope": [round(b - 1.96 * se, 4), round(b + 1.96 * se, 4)],
    }


# ---------------------------------------------------------------------------
# FG3A per team-game dari leaguegamefinder (mentah)
# ---------------------------------------------------------------------------


def baca_respons_leaguegamefinder_cache(
    season: str, cache_dir: Path
) -> tuple[dict | None, dict]:
    """Baca respons mentah leaguegamefinder satu musim dari DiskCache.

    Kunci = SHA-256 URL (ingest.common.DiskCache.key_for). TTL
    DIABAIKAN dengan sengaja: ini snapshot historis, bukan data
    live — musim yang sudah selesai snapshotnya final. Mengembalikan
    (data_respons, info): data None bila file cache tidak ada /
    tidak bisa di-parse; info membawa saved_at + tanggal snapshot.
    """
    from ingest.common import DiskCache
    from ingest.stats_nba import LEAGUE_GAMES_URL

    url = (
        f"{LEAGUE_GAMES_URL}?LeagueID=00&Season={season}"
        "&SeasonType=Regular%20Season&PlayerOrTeam=T"
    )
    path = cache_dir / f"{DiskCache.key_for(url)}.json"
    info: dict = {"season": season, "cache_path": str(path), "sumber": "cache"}
    if not path.exists():
        info["error"] = "file cache tidak ada"
        return None, info
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        info["saved_at"] = payload.get("saved_at")
        body = json.loads(payload["value"]["body"])
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        info["error"] = f"cache tidak bisa di-parse: {exc}"
        return None, info
    if not isinstance(body, dict):
        info["error"] = "body cache bukan dict"
        return None, info
    return body, info


def fetch_respons_leaguegamefinder(season: str) -> dict:
    """Fetch mentah leaguegamefinder satu musim (keyless, 0 kredit).

    Hanya dipakai bila cache tidak ada. Raise RuntimeError bila
    fetch gagal (pesan jelas).
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
    url = (
        f"{LEAGUE_GAMES_URL}?LeagueID=00&Season={season}"
        "&SeasonType=Regular%20Season&PlayerOrTeam=T"
    )
    resp = client.get(url, use_cache=False)
    if resp.get("status") != 200:
        raise RuntimeError(
            f"leaguegamefinder musim {season} gagal: http_{resp.get('status')}: "
            f"{resp.get('error') or 'leaguegamefinder gagal'}"
        )
    data = parse_json_body(resp)
    if not isinstance(data, dict):
        raise RuntimeError(
            f"leaguegamefinder musim {season} gagal: stats_nba_format_changed"
        )
    return data


def parse_fg3a_team_game(data: dict, season: str) -> tuple[list[dict], dict]:
    """Ubah respons mentah leaguegamefinder jadi record 3P per team-game.

    Tiap record: season, game_id, game_date, tricode, fg3a, fg3m, fga
    (angka per laga itu). HANYA laga SELESAI (kolom WL terisi) yang
    dipakai — laga berjalan di snapshot (WL kosong) bukan observasi
    laga penuh dan dilewati + dicatat di info. Tidak perlu pairing
    home/away (laju 3PA adalah sifat tim, bukan sifat laga).
    Raise ValueError("stats_nba_format_changed") bila resultSet
    LeagueGameFinderResults tidak ada.
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
    records: list[dict] = []
    n_berjalan = 0
    n_tanpa_angka = 0
    for row in rs.get("rowSet") or []:
        rec = dict(zip(headers, row, strict=False))
        if not rec.get("WL"):
            n_berjalan += 1
            continue
        tricode = rec.get("TEAM_ABBREVIATION")
        fg3a = rec.get("FG3A")
        fg3m = rec.get("FG3M")
        fga = rec.get("FGA")
        if (
            not isinstance(tricode, str)
            or isinstance(fg3a, bool)
            or not isinstance(fg3a, (int, float))
            or isinstance(fg3m, bool)
            or not isinstance(fg3m, (int, float))
            or isinstance(fga, bool)
            or not isinstance(fga, (int, float))
        ):
            n_tanpa_angka += 1
            continue
        records.append(
            {
                "season": season,
                "game_id": str(rec.get("GAME_ID")),
                "game_date": str(rec.get("GAME_DATE") or "")[:10],
                "tricode": tricode,
                "fg3a": float(fg3a),
                "fg3m": float(fg3m),
                "fga": float(fga),
            }
        )
    tanggal = sorted({rec["game_date"] for rec in records})
    info = {
        "season": season,
        "n_record": len(records),
        "n_laga_berjalan_dilewati": n_berjalan,
        "n_baris_tanpa_angka_dilewati": n_tanpa_angka,
        "tanggal_awal": tanggal[0] if tanggal else None,
        "tanggal_akhir": tanggal[-1] if tanggal else None,
    }
    return records, info


def muat_fg3a(
    seasons: list[str], data_dir: Path, cache_dir: Path
) -> tuple[list[dict], dict]:
    """Muat FG3A per team-game: dari file ekstrak, atau cache/fetch.

    Bila data_dir/fg3a_{musim}.json ada, musim itu tidak diekstrak
    lagi. Bila belum ada: baca respons mentah dari DiskCache
    (TTL diabaikan — lihat baca_respons_leaguegamefinder_cache) atau
    fetch langsung bila cache tidak ada, parse, lalu tulis file
    ekstraknya. File gabungan fg3a_all.json juga ditulis (cermin
    boxscores_all.json). Raise RuntimeError bila sumber tidak
    tersedia.
    """
    records_semua: list[dict] = []
    info_per_musim: dict[str, dict] = {}
    data_dir.mkdir(parents=True, exist_ok=True)
    for musim in seasons:
        cache_path = data_dir / f"fg3a_{musim}.json"
        if cache_path.exists():
            data_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(data_cache, list):
                raise RuntimeError(f"cache FG3A bukan list: {cache_path}")
            records_semua.extend(data_cache)
            tanggal = sorted(
                {str(rec.get("game_date") or "")[:10] for rec in data_cache}
            )
            info_per_musim[musim] = {
                "sumber": f"file ekstrak {cache_path.name}",
                "n_record": len(data_cache),
                "tanggal_awal": tanggal[0] if tanggal else None,
                "tanggal_akhir": tanggal[-1] if tanggal else None,
                "catatan": (
                    "metadata snapshot cache (saved_at, jumlah laga "
                    "berjalan yang dilewati) tidak tersimpan di file "
                    "ekstrak — hapus file ini untuk mengekstrak ulang "
                    "dari cache bila metadata itu dibutuhkan"
                ),
            }
            continue
        data, info_cache = baca_respons_leaguegamefinder_cache(musim, cache_dir)
        if data is None:
            data = fetch_respons_leaguegamefinder(musim)
            info_cache = {"season": musim, "sumber": "fetch langsung"}
        try:
            records, info_parse = parse_fg3a_team_game(data, musim)
        except ValueError as exc:
            raise RuntimeError(f"FG3A musim {musim} gagal: {exc}") from exc
        cache_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        records_semua.extend(records)
        info_per_musim[musim] = {**info_cache, **info_parse}
    gabung = data_dir / "fg3a_all.json"
    gabung.write_text(
        json.dumps(records_semua, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records_semua, info_per_musim


# ---------------------------------------------------------------------------
# Laju 3PA point-in-time
# ---------------------------------------------------------------------------


def laju_3pa_sebelum(
    riwayat: list[dict], tanggal: str, min_laga: int = MIN_LAGA_UNTUK_LAJU
) -> dict | None:
    """Laju 3PA satu tim dari laga SEBELUM tanggal (musim yang sama).

    riwayat: record team-game tim itu (sudah satu musim), sembarang
    urutan. Mengembalikan dict (fg3a_per_game, fg3_pct, sd_3pm,
    share_3pa, var3p_binom, n_laga) atau None bila laga sebelumnya
    < min_laga. sd_3pm = simpangan baku 3PM/laga (volatilitas
    tembakan tim); share_3pa = total 3PA / total FGA; var3p_binom =
    varians poin tripoin tersirat binomial = n x p(1-p) x 9 per laga
    (n = 3PA/laga, p = 3P%). sd_3pm None bila n < 2 (std tak
    terdefinisi); fg3_pct None bila total 3PA 0.
    """
    sebelum = [rec for rec in riwayat if str(rec.get("game_date") or "")[:10] < tanggal]
    n = len(sebelum)
    if n < min_laga:
        return None
    total_3pa = sum(float(rec["fg3a"]) for rec in sebelum)
    total_3pm = sum(float(rec["fg3m"]) for rec in sebelum)
    total_fga = sum(float(rec["fga"]) for rec in sebelum)
    fg3a_per_game = total_3pa / n
    fg3_pct = total_3pm / total_3pa if total_3pa > 0 else None
    sd_3pm = (
        statistics.stdev([float(rec["fg3m"]) for rec in sebelum]) if n > 1 else None
    )
    share_3pa = total_3pa / total_fga if total_fga > 0 else None
    var3p_binom = (
        fg3a_per_game * fg3_pct * (1.0 - fg3_pct) * 9.0 if fg3_pct is not None else None
    )
    return {
        "fg3a_per_game": fg3a_per_game,
        "fg3_pct": fg3_pct,
        "sd_3pm": sd_3pm,
        "share_3pa": share_3pa,
        "var3p_binom": var3p_binom,
        "n_laga": n,
    }


# ---------------------------------------------------------------------------
# Fit utama
# ---------------------------------------------------------------------------


def fit_ekor_3p(
    games: list[dict],
    rolling: dict,
    fg3a_records: list[dict],
    min_laga: int = MIN_LAGA_UNTUK_LAJU,
    min_games_total: int = 100,
) -> dict:
    """Fit ekor 3P dari game log + rating rolling + record FG3A.

    games: game log (lihat fit_nba_params.load_games). rolling: dict
    game_id -> data bangun_rating_rolling. fg3a_records: record
    parse_fg3a_team_game. min_laga: ambang laga sebelumnya untuk
    laju 3PA (lihat laju_3pa_sebelum). min_games_total: ambang
    minimum data (dari config simulation.fitting bila dipanggil
    lewat main) — di bawah ini semua parameter null + alasan.
    Mengembalikan dict hasil fit (siap JSON).
    """
    hasil: dict = {
        "method": "lihat docstring scripts/fit_ekor_3p.py + LAPORAN-EKOR-3P.md",
        "ratings_mode": "rolling",
        "look_ahead_bias": (
            "tidak ada — rating rolling point-in-time DAN laju 3PA "
            "point-in-time (hanya laga sebelum tanggal laga)"
        ),
        "n_games_input": len(games),
        "n_games_used": 0,
        "n_games_skipped_no_rolling": 0,
        "n_games_skipped_no_points": 0,
        "n_games_skipped_no_laju_3pa": 0,
        "min_laga_untuk_laju": min_laga,
        "games_per_season": {},
        "regresi": {},
        "kuartil_3pa": [],
        "per_musim": {},
    }
    riwayat_per_tim: dict[tuple[str, str], list[dict]] = {}
    for rec in fg3a_records:
        riwayat_per_tim.setdefault(
            (str(rec.get("season")), str(rec.get("tricode"))), []
        ).append(rec)

    baris: list[dict] = []
    dipakai_per_musim: dict[str, int] = {}
    for game in games:
        musim = str(game.get("season"))
        game_id = str(game.get("game_id"))
        data_rolling = rolling.get(game_id)
        if data_rolling is None:
            hasil["n_games_skipped_no_rolling"] += 1
            continue
        home = game.get("home_tricode")
        away = game.get("away_tricode")
        home_pts = game.get("home_pts")
        away_pts = game.get("away_pts")
        if home_pts is None or away_pts is None:
            hasil["n_games_skipped_no_points"] += 1
            continue
        tanggal = str(game.get("game_date") or "")[:10]
        laju_home = laju_3pa_sebelum(
            riwayat_per_tim.get((musim, home), []), tanggal, min_laga
        )
        laju_away = laju_3pa_sebelum(
            riwayat_per_tim.get((musim, away), []), tanggal, min_laga
        )
        if laju_home is None or laju_away is None:
            hasil["n_games_skipped_no_laju_3pa"] += 1
            continue
        mu_home, mu_away, _pace = project_points(
            data_rolling["home_efektif"],
            data_rolling["away_efektif"],
            data_rolling["lg_avg_off_rtg"],
        )
        resid_total = (float(home_pts) + float(away_pts)) - (mu_home + mu_away)
        resid_margin = (float(home_pts) - float(away_pts)) - (mu_home - mu_away)
        pct_home = laju_home["fg3_pct"]
        pct_away = laju_away["fg3_pct"]
        sd_home = laju_home["sd_3pm"]
        sd_away = laju_away["sd_3pm"]
        var_home = laju_home["var3p_binom"]
        var_away = laju_away["var3p_binom"]
        share_home = laju_home["share_3pa"]
        share_away = laju_away["share_3pa"]
        baris.append(
            {
                "game_id": game_id,
                "musim": musim,
                "resid_total": resid_total,
                "resid_margin": resid_margin,
                "pa3_gabung": laju_home["fg3a_per_game"] + laju_away["fg3a_per_game"],
                "pa3_max": max(laju_home["fg3a_per_game"], laju_away["fg3a_per_game"]),
                "pa3_min": min(laju_home["fg3a_per_game"], laju_away["fg3a_per_game"]),
                "pct3_gabung": (
                    (pct_home + pct_away) / 2.0
                    if pct_home is not None and pct_away is not None
                    else None
                ),
                "sd3pm_gabung": (
                    sd_home + sd_away
                    if sd_home is not None and sd_away is not None
                    else None
                ),
                "share3pa_gabung": (
                    (share_home + share_away) / 2.0
                    if share_home is not None and share_away is not None
                    else None
                ),
                "var3p_binom": (
                    var_home + var_away
                    if var_home is not None and var_away is not None
                    else None
                ),
            }
        )
        dipakai_per_musim[musim] = dipakai_per_musim.get(musim, 0) + 1

    n = len(baris)
    hasil["n_games_used"] = n
    hasil["games_per_season"] = dipakai_per_musim
    if n < min_games_total:
        alasan = f"data tidak cukup: {n} laga < minimum {min_games_total}"
        hasil["verdict"] = "DATA_TIDAK_CUKUP"
        hasil["alasan"] = alasan
        for nama in (
            "varians_total_vs_3pa",
            "varians_margin_vs_3pa",
            "abs_resid_total_vs_3pa",
            "abs_resid_margin_vs_3pa",
            "mean_resid_total_vs_3pa",
        ):
            hasil["regresi"][nama] = {"value": None, "reason": alasan}
        hasil["slope_aktif_direkomendasikan"] = None
        return hasil

    pa3 = [b["pa3_gabung"] for b in baris]
    hasil["tiga_pa_gabungan"] = {
        "mean": round(statistics.fmean(pa3), 4),
        "sd": round(statistics.stdev(pa3), 4),
        "min": round(min(pa3), 2),
        "p25": round(_kuantil(sorted(pa3), 0.25), 2),
        "median": round(_kuantil(sorted(pa3), 0.5), 2),
        "p75": round(_kuantil(sorted(pa3), 0.75), 2),
        "max": round(max(pa3), 2),
        "n": n,
    }
    rt2 = [b["resid_total"] ** 2 for b in baris]
    rm2 = [b["resid_margin"] ** 2 for b in baris]
    art = [abs(b["resid_total"]) for b in baris]
    arm = [abs(b["resid_margin"]) for b in baris]
    rt = [b["resid_total"] for b in baris]
    regresi = hasil["regresi"]
    regresi["varians_total_vs_3pa"] = _hasil_ols(ols(pa3, rt2))
    regresi["varians_total_vs_3pa"][
        "method"
    ] = "OLS resid_total^2 ~ a + b x 3PA_gabung (REGRESI UTAMA)"
    regresi["varians_margin_vs_3pa"] = _hasil_ols(ols(pa3, rm2))
    regresi["varians_margin_vs_3pa"][
        "method"
    ] = "OLS resid_margin^2 ~ a + b x 3PA_gabung"
    regresi["abs_resid_total_vs_3pa"] = _hasil_ols(ols(pa3, art))
    regresi["abs_resid_total_vs_3pa"][
        "method"
    ] = "OLS |resid_total| ~ a + b x 3PA_gabung"
    regresi["abs_resid_margin_vs_3pa"] = _hasil_ols(ols(pa3, arm))
    regresi["abs_resid_margin_vs_3pa"][
        "method"
    ] = "OLS |resid_margin| ~ a + b x 3PA_gabung"
    regresi["mean_resid_total_vs_3pa"] = _hasil_ols(ols(pa3, rt))
    regresi["mean_resid_total_vs_3pa"]["method"] = (
        "OLS resid_total ~ a + b x 3PA_gabung (EFEK MEAN — temuan samping; "
        "bukan bagian model ekor)"
    )

    # Prediktor alternatif (masing-masing pada subset yang datanya ada).
    # Regresi diagnostik ini TIDAK BOLEH menggagalkan fit bila
    # prediktornya tak bervariasi (mis. 3P% sama di semua laga pada
    # data sintetis) — dicatat null + alasan, bukan crash.
    for kunci_prediktor, kunci_hasil, keterangan in (
        (
            "pct3_gabung",
            "varians_total_vs_3pct",
            "OLS resid_total^2 ~ a + b x 3P%_gabungan",
        ),
        (
            "sd3pm_gabung",
            "varians_total_vs_sd3pm",
            "OLS resid_total^2 ~ a + b x sd_3PM_gabung",
        ),
        (
            "share3pa_gabung",
            "varians_total_vs_share3pa",
            "OLS resid_total^2 ~ a + b x share_3PA",
        ),
        (
            "var3p_binom",
            "varians_total_vs_var3p_binom",
            "OLS resid_total^2 ~ a + b x var_3P_binomial",
        ),
        (
            "pa3_max",
            "varians_total_vs_3pa_max",
            "OLS resid_total^2 ~ a + b x max(3PA_tim)",
        ),
        (
            "pa3_min",
            "varians_total_vs_3pa_min",
            "OLS resid_total^2 ~ a + b x min(3PA_tim)",
        ),
    ):
        sub = [b for b in baris if b[kunci_prediktor] is not None]
        if len(sub) < 3:
            regresi[kunci_hasil] = {"value": None, "reason": "data tidak cukup"}
            continue
        try:
            ringkas = _hasil_ols(
                ols(
                    [b[kunci_prediktor] for b in sub],
                    [b["resid_total"] ** 2 for b in sub],
                )
            )
        except ValueError as exc:
            regresi[kunci_hasil] = {"value": None, "reason": str(exc)}
            continue
        ringkas["method"] = keterangan
        regresi[kunci_hasil] = ringkas

    # Slope binomial teoritis dari 3P% rata-rata sampel fit.
    pct_semua = [b["pct3_gabung"] for b in baris if b["pct3_gabung"] is not None]
    p_rata = statistics.fmean(pct_semua) if pct_semua else None
    hasil["slope_binomial_teoritis"] = {
        "value": (
            round(9.0 * p_rata * (1.0 - p_rata), 4) if p_rata is not None else None
        ),
        "p_rata_liga": round(p_rata, 4) if p_rata is not None else None,
        "method": (
            "9 x p(1-p) dengan p = 3P% rata-rata sampel fit — varians poin "
            "tripoin per 1 percobaan tambahan bila mekanisme binomial "
            "menembus penuh ke varians residual total (pembanding, bukan fit)"
        ),
    }

    # Tabel kuartil 3PA gabungan + kuantil ekor atas residual total.
    pa3_urut = sorted(pa3)
    q25 = _kuantil(pa3_urut, 0.25)
    q50 = _kuantil(pa3_urut, 0.5)
    q75 = _kuantil(pa3_urut, 0.75)
    hasil["batas_kuartil_3pa"] = {
        "q25": round(q25, 2),
        "q50": round(q50, 2),
        "q75": round(q75, 2),
    }
    for nama, lo, hi in (
        ("Q1_rendah", float("-inf"), q25),
        ("Q2", q25, q50),
        ("Q3", q50, q75),
        ("Q4_tinggi", q75, float("inf")),
    ):
        grup = [b for b in baris if lo < b["pa3_gabung"] <= hi]
        if not grup:
            continue
        resid_t = sorted(b["resid_total"] for b in grup)
        resid_m = [b["resid_margin"] for b in grup]
        hasil["kuartil_3pa"].append(
            {
                "kelompok": nama,
                "n": len(grup),
                "pa3_gabung_mean": round(
                    statistics.fmean([b["pa3_gabung"] for b in grup]), 2
                ),
                "sd_resid_total": round(statistics.stdev(resid_t), 4),
                "sd_resid_margin": round(statistics.stdev(resid_m), 4),
                "mean_abs_resid_total": round(
                    statistics.fmean([abs(v) for v in resid_t]), 4
                ),
                "mean_resid_total": round(statistics.fmean(resid_t), 4),
                "p_abs_resid_total_lebih_30": round(
                    sum(1 for v in resid_t if abs(v) > 30) / len(resid_t), 4
                ),
                "p_resid_total_lebih_25": round(
                    sum(1 for v in resid_t if v > 25) / len(resid_t), 4
                ),
                "p90_resid_total": round(_kuantil(resid_t, 0.90), 2),
                "p95_resid_total": round(_kuantil(resid_t, 0.95), 2),
                "p99_resid_total": round(_kuantil(resid_t, 0.99), 2),
                "max_resid_total": round(max(resid_t), 2),
            }
        )

    # Slope varians per musim (cek stabilitas). Seperti prediktor
    # alternatif: musim dengan prediktor tak bervariasi dicatat null,
    # bukan crash.
    for musim in sorted(dipakai_per_musim):
        sub = [b for b in baris if b["musim"] == musim]
        if len(sub) < 3:
            continue
        try:
            ringkas = _hasil_ols(
                ols(
                    [b["pa3_gabung"] for b in sub],
                    [b["resid_total"] ** 2 for b in sub],
                )
            )
        except ValueError as exc:
            hasil["per_musim"][musim] = {"value": None, "reason": str(exc)}
            continue
        ringkas["method"] = "OLS resid_total^2 ~ a + b x 3PA_gabung (satu musim)"
        ringkas["sd_resid_total"] = round(
            statistics.stdev([b["resid_total"] for b in sub]), 4
        )
        hasil["per_musim"][musim] = ringkas

    # Verdict + slope aktif yang direkomendasikan.
    utama = regresi["varians_total_vs_3pa"]
    t_utama = utama["t_slope"]
    if abs(t_utama) >= AMBANG_T_SIGNIFIKAN:
        hasil["verdict"] = "SIGNIFIKAN"
        hasil["slope_aktif_direkomendasikan"] = utama["slope"]
        hasil["alasan_verdict"] = (
            f"|t| = {abs(t_utama):.2f} >= {AMBANG_T_SIGNIFIKAN} pada regresi utama "
            "(resid_total^2 ~ 3PA_gabung) — efek terukur, slope fit diajukan "
            "sebagai slope aktif (butuh persetujuan user seperti D12)"
        )
    else:
        hasil["verdict"] = "TIDAK_SIGNIFIKAN"
        hasil["slope_aktif_direkomendasikan"] = 0.0
        hasil["alasan_verdict"] = (
            f"|t| = {abs(t_utama):.2f} < {AMBANG_T_SIGNIFIKAN} pada regresi utama "
            "(resid_total^2 ~ 3PA_gabung) — efek tidak terukur pada "
            f"{n} laga; mengikuti preseden altitude (nilai fit dalam noise "
            "tidak diadopsi), slope aktif yang direkomendasikan = 0,0 "
            "(sim memakai sigma global) sampai kalibrasi ulang"
        )
    hasil["sigma_total_tersirat"] = {
        "method": (
            "akar(a + b x 3PA_gabung) dari regresi utama (a, b = nilai FIT, "
            "bukan yang aktif di sim)"
        ),
        "pada_3pa_60": round(
            math.sqrt(max(utama["intersep"] + utama["slope"] * 60.0, 0.0)), 2
        ),
        "pada_3pa_70": round(
            math.sqrt(max(utama["intersep"] + utama["slope"] * 70.0, 0.0)), 2
        ),
        "pada_3pa_80": round(
            math.sqrt(max(utama["intersep"] + utama["slope"] * 80.0, 0.0)), 2
        ),
        "pada_3pa_90": round(
            math.sqrt(max(utama["intersep"] + utama["slope"] * 90.0, 0.0)), 2
        ),
    }
    hasil["rencana_kalibrasi"] = (
        "Jalankan ulang skrip ini tiap akhir musim (n bertambah ~1.230 "
        "laga/musim) dan saat ada cukup laga musim berjalan; bila |t| "
        "regresi utama >= 2,0, ajukan slope fit sebagai slope_aktif ke "
        "user (seperti D12). Bila efek tetap tidak terukur setelah "
        "n >= 5.000, pertimbangkan menutup hipotesis laju-3PA dan "
        "mengalihkan perhatian ke prediktor ekor lain (mis. volatilitas "
        "pace per laga atau 3P% lawan)."
    )
    return hasil


def main(argv: list[str] | None = None) -> int:
    """Jalankan fit dari CLI. 0 sukses, 2 data/sumber tidak tersedia."""
    parser = argparse.ArgumentParser(
        description="Fit ekor 3 poin per laga (varians residual vs laju 3PA)."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=["2024-25", "2025-26", "2026-27"],
        help="musim yang dipakai (default: 2024-25 2025-26 2026-27)",
    )
    parser.add_argument(
        "--games-file",
        default="data/nba_history/games_all.json",
        help="JSON game log (default: data/nba_history/games_all.json)",
    )
    parser.add_argument(
        "--boxscores-file",
        default="data/nba_history/boxscores_all.json",
        help="JSON box score gabungan (default: data/nba_history/boxscores_all.json)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/nba_history",
        help="direktori data mentah (default: data/nba_history)",
    )
    parser.add_argument(
        "--out",
        default="out/fit_ekor_3p.json",
        help="file JSON hasil fit (default: out/fit_ekor_3p.json)",
    )
    parser.add_argument(
        "--min-laga",
        type=int,
        default=MIN_LAGA_UNTUK_LAJU,
        help=f"minimum laga sebelumnya untuk laju 3PA (default: {MIN_LAGA_UNTUK_LAJU})",
    )
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / args.data_dir
    out_path = repo_root / args.out
    cache_dir = repo_root / "out" / "cache"

    try:
        cfg = config_mod.load_playstyle()
        min_games = int(
            config_mod.get_value(cfg, "simulation", "fitting", "min_games_total")
        )
        w_musim = float(
            config_mod.get_value(cfg, "simulation", "nba", "recency", "season")
        )
        w_last10 = float(
            config_mod.get_value(cfg, "simulation", "nba", "recency", "last10")
        )
    except config_mod.ConfigError as exc:
        print(f"config tidak lengkap: {exc}", file=sys.stderr)
        return 2
    try:
        games = fit_nba_params.load_games(args.seasons, args.games_file, data_dir)
        boxscores = fit_nba_params.load_boxscores(
            args.seasons, args.boxscores_file, data_dir
        )
        priors = fit_nba_params.load_prior_ratings(args.seasons, data_dir)
        rolling_data, info_rolling = fit_nba_params.bangun_rating_rolling(
            games, boxscores, priors, w_musim, w_last10
        )
        fg3a_records, info_fg3a = muat_fg3a(args.seasons, data_dir, cache_dir)
        hasil = fit_ekor_3p(games, rolling_data, fg3a_records, args.min_laga, min_games)
        hasil["rolling_info"] = info_rolling
        hasil["fg3a_info"] = info_fg3a
        hasil["fg3a_source"] = (
            "leaguegamefinder mentah (DiskCache out/cache, TTL diabaikan — "
            "snapshot historis; atau fetch langsung bila cache tidak ada)"
        )
        hasil["boxscores_source"] = args.boxscores_file
        hasil["priors_source"] = "rating BBRef musim sebelumnya (cache/fetch)"
        hasil["ratings_source"] = (
            "rating rolling point-in-time dari box score leaguegamefinder "
            "+ prior BBRef musim sebelumnya"
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"fit dibatalkan: {exc}", file=sys.stderr)
        return 2

    hasil["seasons"] = args.seasons
    hasil["games_source"] = args.games_file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"laga dipakai: {hasil['n_games_used']} "
        f"(dilewati tanpa rolling: {hasil['n_games_skipped_no_rolling']}"
        f", tanpa laju 3PA: {hasil['n_games_skipped_no_laju_3pa']})"
    )
    utama = hasil["regresi"].get("varians_total_vs_3pa") or {}
    if utama.get("slope") is not None:
        print(
            f"regresi utama resid_total^2 ~ 3PA: slope {utama['slope']} "
            f"(SE {utama['se_slope']}, t={utama['t_slope']}, "
            f"CI95 {utama['ci95_slope']}, R2={utama['r2']})"
        )
        print(
            f"slope binomial teoritis: " f"{hasil['slope_binomial_teoritis']['value']}"
        )
    print(f"verdict: {hasil['verdict']} — {hasil.get('alasan_verdict', '')}")
    print(
        "slope_aktif yang direkomendasikan: "
        f"{hasil.get('slope_aktif_direkomendasikan')}"
    )
    print(f"hasil fit ditulis ke {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
