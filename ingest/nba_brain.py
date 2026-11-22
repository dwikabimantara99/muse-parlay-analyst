"""Perakit input Otak NBA untuk satu laga (Tahap 3 Langkah 1).

Menggabungkan fetcher yang sudah ada menjadi satu paket input siap model
untuk SATU laga NBA: statistik tim (musim + 10 laga terakhir), 5 laga
terakhir, rekor kandang/tandang, hari istirahat/B2B, pemain inti (BPM x
menit), cedera dari 2 sumber, H2H 5 laga terakhir, dan rata-rata liga.

KONTRAK OUTPUT (modul model bergantung pada bentuk persis ini) —
data FetchResult:
  {"match": {"home_tricode", "away_tricode", "game_date", "season"},
   "home": {blok tim}, "away": {blok tim},
   "h2h_last5": [laga...], "tournament": None | "NBA Cup" | "Playoff",
   "league": {"avg_pace", "avg_off_rtg"},
   "missing": [nama field yang gagal diambil],
   "sources": [{data_kind, source, tier, fetched_at}...],
   "fetched_at": iso}
Blok tim:
  {"tricode", "team", "stats_season": {off_rtg, def_rtg, net_rtg, pace},
   "stats_last10": {kunci sama},
   "form5": [{"game_date", "opponent_tricode", "home", "wl", "pts",
              "opp_pts"}... urutan terbaru dulu],
   "home_record": {"w", "l", "ppg", "opp_ppg"},
   "road_record": {sama},
   "rest_days": int | None, "back_to_back": bool | None,
   "altitude_home": bool,
   "players": [{"player", "bpm", "mp_per_game", "team_tricode"}...],
     # 8 pemain bermenit terbanyak + semua pemain cedera yang ada di
     # daftar cedera tim ini (walau di luar 8 besar) agar model bisa
     # menghitung dampak absennya.
   "injuries": [{"player", "status", "team_tricode", "sources": [...]}...]}

ATURAN GAGAL (sesuai DECISIONS.md B):
- Setiap kegagalan fetch -> field None (atau list kosong) + nama field di
  "missing" + error di FetchResult.extra["fetch_errors"]. ok=False HANYA
  bila SEMUA sumber gagal total; bila sebagian berhasil, ok=True dengan
  "missing" terisi. Data selalu berbentuk kontrak (kecuali input tidak
  valid -> ok=False, data=None).
- Nama di "missing" memakai jalur field bertitik ("home.stats_season",
  "h2h_last5", "league.avg_pace"), kecuali yang memakai nama khusus:
  "tournament_flag_tidak_dapat_ditentukan",
  "injuries_konflik:<pemain>", "injuries_status_tidak_dikenal:<pemain>",
  "injuries_tim_tidak_dikenal", "injuries_bukan_cedera:<pemain>",
  "injuries_komentar_konflik:<pemain>".
- rest_days = jumlah hari istirahat penuh antar laga: selisih hari dari
  laga terakhir sebelum game_date dikurangi 1 (main kemarin -> 0).
  back_to_back = rest_days == 0. Tanpa laga sebelumnya -> keduanya None.
- Statistik musim: tier 1 stats.nba.com dulu; bila gagal, fallback ke
  Basketball-Reference (tier 2, hanya musim — tidak ada fallback
  10-laga-terakhir). Sumber yang dipakai dicatat di "sources".
- Cedera (B2): PDF resmi (tier 1) + ESPN (tier 2, sejak 2026-11-22;
  Rotowire dicopot — versi gratisnya hanya 5 entri + paywall).
  Status dinormalisasi ke OUT/DOUBTFUL/QUESTIONABLE/PROBABLE/AVAILABLE;
  "Day-To-Day"/"GTD" dipetakan ke QUESTIONABLE (perkiraan terdekat,
  status asli disimpan di "status_asli"); status yang tidak bisa
  dipetakan -> None + dicatat di "missing". Baris ESPN yang sudah
  membawa "status_normalized" dipakai apa adanya (pemetaan ESPN di
  ingest/espn.py, selaras dengan _normalize_status di sini); baris
  tanpa field itu (PDF) dinormalisasi dengan _normalize_status.
  Bila dua sumber berbeda status, yang dipakai adalah status tier
  tertinggi (B1) dan konfliknya dicatat di "missing" + kunci
  "conflict" di entri cedera (B2: jangan pilih diam-diam). Bila status
  tier 1 tidak terbaca tapi tier 2 terbaca, status tier 2 yang dipakai
  (status yang diketahui mengalahkan status yang tidak terbaca).
  Entri ESPN dengan is_injury False (bukan cedera: kontrak two-way,
  rest, personal, dst — lihat ingest/espn.py) TIDAK dihitung sebagai
  konfirmasi cedera: tidak masuk daftar cedera, dicatat di "missing"
  sebagai "injuries_bukan_cedera:<pemain>". Entri ESPN dengan
  status_comment_conflict True (status vs komentar bertentangan)
  diteruskan ke entri gabung sebagai kunci "status_comment_conflict"
  + dicatat di "missing" sebagai "injuries_komentar_konflik:<pemain>".
- tournament: None sampai ada sumber yang bisa menentukannya — tanggal
  NBA Cup/Playoff TIDAK ditebak.
- altitude_home: True bila tricode tim ini DEN/UTA (fakta arena).
"""

from __future__ import annotations

import re
from datetime import date

from ingest import matching
from ingest.bbref import fetch_player_advanced, fetch_team_advanced
from ingest.common import FetchResult, HttpClient, now_iso
from ingest.espn import fetch_injuries_nba
from ingest.nba_injury_pdf import fetch_report
from ingest.player_gamelog import fetch_missed_last10_many
from ingest.stats_nba import (
    TEAM_TRICODES,
    fetch_league_games,
    fetch_team_advanced_stats,
)

SOURCE = "nba_brain"
TIER = 1  # Sumber utama perakit ini tier 1; tiap datum membawa
# sumber + tier aslinya sendiri di data["sources"].

# Tim yang bermain di ketinggian (fakta arena): Denver ~1.600 m,
# Salt Lake City ~1.300 m.
ALTITUDE_TRICODES = frozenset({"DEN", "UTA"})

_SEASON_RE = re.compile(r"^\d{4}-\d{2}$")

# Pemetaan status cedera eksak (huruf kecil, tanda hubung -> spasi).
_STATUS_EXACT = {
    "out": "OUT",
    "doubtful": "DOUBTFUL",
    "questionable": "QUESTIONABLE",
    "probable": "PROBABLE",
    "available": "AVAILABLE",
}
# Pemetaan perkiraan terdekat: status harian = game-time decision.
_STATUS_APPROX = {
    "day to day": "QUESTIONABLE",
    "gtd": "QUESTIONABLE",
    "game time decision": "QUESTIONABLE",
}

_KNOWN_TRICODES = frozenset(TEAM_TRICODES.values())


def _empty_stats() -> dict:
    """Blok statistik kosong (semua nilai None)."""
    return {"off_rtg": None, "def_rtg": None, "net_rtg": None, "pace": None}


def _bbref_season(season: str) -> int:
    """Konversi musim "2026-27" -> tahun berakhir BBRef (2027)."""
    return int(season[:4]) + 1


def _source_entry(data_kind: str, result: FetchResult) -> dict:
    """Satu entri sources[] dari FetchResult yang berhasil."""
    return {
        "data_kind": data_kind,
        "source": result.source,
        "tier": result.tier,
        "fetched_at": result.fetched_at,
    }


def _safe_fetch(func, *args, **kwargs) -> FetchResult:
    """Panggil fetcher; exception diubah jadi FetchResult gagal.

    Fetcher yang benar tidak melempar untuk kegagalan data, tapi
    perakit ini tidak boleh mati karena satu fetcher bermasalah.
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - semua exception fetch dicatat
        return FetchResult(
            SOURCE,
            TIER,
            now_iso(),
            False,
            error=f"exception_{type(exc).__name__}: {exc}",
        )


def _team_tricode(team_raw: str) -> str | None:
    """Petakan nama/singkatan tim apa pun ke tricode (atau None).

    Memakai ingest.matching (nama lengkap, julukan, dan tricode
    diterima — misal "LA Clippers", "Clippers", "LAC" -> "LAC").
    """
    if not isinstance(team_raw, str) or not team_raw.strip():
        return None
    for tricode in sorted(_KNOWN_TRICODES):
        if matching.teams_match(team_raw, tricode, "nba"):
            return tricode
    return None


def _to_float(value: object) -> float | None:
    """Ubah nilai jadi float; None bila bukan angka."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _mean(values: list) -> float | None:
    """Rata-rata nilai angka; None bila tidak ada satu pun."""
    numbers = [
        value for value in (_to_float(item) for item in values) if value is not None
    ]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _games_before(games: list, target: date) -> list[dict]:
    """Laga dengan game_date sebelum tanggal target (sudah dimainkan)."""
    before = []
    for game in games or []:
        try:
            game_date = date.fromisoformat(str(game.get("game_date") or "")[:10])
        except ValueError:
            continue
        if game_date < target:
            before.append(game)
    return before


def _team_games(games: list, tricode: str) -> list[dict]:
    """Laga-laga satu tim dari daftar laga."""
    return [
        game
        for game in games
        if game.get("home_tricode") == tricode or game.get("away_tricode") == tricode
    ]


def _points_of(game: dict, tricode: str) -> tuple[int | None, int | None]:
    """(poin tim, poin lawan) untuk satu tim di satu laga."""
    if game.get("home_tricode") == tricode:
        return game.get("home_pts"), game.get("away_pts")
    return game.get("away_pts"), game.get("home_pts")


def _form5(team_games: list, tricode: str) -> list[dict]:
    """5 laga terakhir tim (terbaru dulu)."""
    recent = sorted(
        team_games,
        key=lambda game: (
            str(game.get("game_date") or ""),
            str(game.get("game_id") or ""),
        ),
        reverse=True,
    )[:5]
    form = []
    for game in recent:
        pts, opp_pts = _points_of(game, tricode)
        if (
            isinstance(pts, (int, float))
            and isinstance(opp_pts, (int, float))
            and pts != opp_pts
        ):
            wl = "W" if pts > opp_pts else "L"
        else:
            wl = None  # Poin hilang/seri (seri mustahil di NBA) — jangan tebak.
        form.append(
            {
                "game_date": game.get("game_date"),
                "opponent_tricode": (
                    game.get("away_tricode")
                    if game.get("home_tricode") == tricode
                    else game.get("home_tricode")
                ),
                "home": game.get("home_tricode") == tricode,
                "wl": wl,
                "pts": pts,
                "opp_pts": opp_pts,
            }
        )
    return form


def _record(team_games: list, tricode: str, home: bool) -> dict:
    """Rekor kandang/tandang: {w, l, ppg, opp_ppg}."""
    subset = [
        game for game in team_games if (game.get("home_tricode") == tricode) == home
    ]
    wins = losses = 0
    points: list[float] = []
    opp_points: list[float] = []
    for game in subset:
        pts, opp_pts = _points_of(game, tricode)
        if not isinstance(pts, (int, float)) or not isinstance(opp_pts, (int, float)):
            continue  # Laga tanpa poin tidak bisa dinilai — dilewati.
        if pts > opp_pts:
            wins += 1
        elif pts < opp_pts:
            losses += 1
        points.append(float(pts))
        opp_points.append(float(opp_pts))
    return {
        "w": wins,
        "l": losses,
        "ppg": _mean(points),
        "opp_ppg": _mean(opp_points),
    }


def _rest(team_games: list, target: date) -> tuple[int | None, bool | None]:
    """(rest_days, back_to_back) dari laga terakhir sebelum target."""
    dates = []
    for game in team_games:
        try:
            dates.append(date.fromisoformat(str(game.get("game_date") or "")[:10]))
        except ValueError:
            continue
    if not dates:
        return None, None
    rest_days = (target - max(dates)).days - 1
    return rest_days, rest_days == 0


def _normalize_player_name(name: object) -> str:
    """Normalisasi nama pemain untuk pencocokan antar sumber."""
    if not isinstance(name, str):
        return ""
    cleaned = re.sub(r"[^a-z0-9 ]", "", name.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_status(raw: object) -> tuple[str | None, str | None]:
    """Normalisasi status cedera.

    Mengembalikan (status_ternormalisasi, status_asli). status_asli
    diisi hanya bila pemetaannya tidak eksak (perkiraan atau tidak
    dikenal) agar jejaknya tidak hilang.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    key = re.sub(r"\s+", " ", raw.strip().lower().replace("-", " ").replace("_", " "))
    if key in _STATUS_EXACT:
        return _STATUS_EXACT[key], None
    if key in _STATUS_APPROX:
        return _STATUS_APPROX[key], raw.strip()
    return None, raw.strip()


def _merge_injuries(
    pdf_result: FetchResult,
    espn_result: FetchResult,
    tricodes: tuple[str, str],
    missing: list,
) -> dict[str, list[dict]]:
    """Gabung daftar cedera 2 sumber untuk kedua tim laga ini.

    Hanya pemain dari kedua tim yang dikembalikan. Konflik status antar
    sumber dan status yang tidak bisa dipetakan dicatat ke `missing`
    (daftar diubah di tempat). Sumber diproses berurutan tier 1 dulu
    (PDF resmi), lalu tier 2 (ESPN). Baris dengan is_injury False
    (entri ESPN non-cedera) dilewati dan dicatat di `missing` sebagai
    "injuries_bukan_cedera:<pemain>"; baris tanpa field is_injury (PDF)
    dianggap cedera. Baris ESPN yang membawa "status_normalized"
    dipakai apa adanya; baris tanpa field itu dinormalisasi dengan
    _normalize_status. Flag "status_comment_conflict" dari ESPN
    diteruskan ke entri gabung + dicatat di `missing`.
    """
    work: dict[str, dict[str, dict]] = {tri: {} for tri in tricodes}
    unknown_team_seen = False
    bukan_cedera: set[str] = set()
    for result in (pdf_result, espn_result):
        if result is None or not result.ok:
            continue
        for row in result.data or []:
            if not isinstance(row, dict):
                continue
            team_tri = _team_tricode(row.get("team") or "")
            if team_tri is None:
                # Tim tidak dikenali sama sekali (misal "UNKNOWN" dari
                # parser PDF) — cedera tidak bisa diatribusikan.
                unknown_team_seen = True
                continue
            if team_tri not in work:
                continue  # Tim lain (daftar bersifat liga-wide) — bukan tim laga ini.
            norm_name = _normalize_player_name(row.get("player"))
            if not norm_name:
                continue
            if row.get("is_injury") is False:
                # Entri non-cedera (two-way, rest, personal, dst) —
                # bukan konfirmasi cedera, jangan masuk daftar.
                bukan_cedera.add(str(row.get("player")))
                continue
            entry = work[team_tri].setdefault(
                norm_name,
                {
                    "player": row.get("player"),
                    "statuses": {},
                    "raw": {},
                    "sources": [],
                    "comment_conflict": False,
                },
            )
            if entry["player"] is None:
                entry["player"] = row.get("player")
            if result.source not in entry["sources"]:
                entry["sources"].append(result.source)
            if "status_normalized" in row:
                # Baris ESPN: pemetaan sudah dilakukan fetcher.
                status = row.get("status_normalized")
                raw = row.get("status_asli")
            else:
                status, raw = _normalize_status(row.get("status"))
            entry["statuses"][result.source] = status
            if raw is not None:
                entry["raw"][result.source] = raw
            if row.get("status_comment_conflict") is True:
                entry["comment_conflict"] = True
    if unknown_team_seen:
        missing.append("injuries_tim_tidak_dikenal")
    for player in sorted(bukan_cedera):
        missing.append(f"injuries_bukan_cedera:{player}")
    merged: dict[str, list[dict]] = {}
    for tri in tricodes:
        entries = []
        for item in work[tri].values():
            # Status pemenang: status pertama yang terbaca dalam urutan
            # tier (PDF dulu). Status tier 2 yang terbaca mengalahkan
            # status tier 1 yang tidak terbaca.
            status = None
            winner = None
            for source in item["sources"]:
                if item["statuses"].get(source) is not None:
                    status = item["statuses"][source]
                    winner = source
                    break
            injury: dict = {
                "player": item["player"],
                "status": status,
                "team_tricode": tri,
                "sources": item["sources"],
            }
            if winner is not None and winner in item["raw"]:
                injury["status_asli"] = item["raw"][winner]
            elif status is None and item["raw"]:
                injury["status_asli"] = next(iter(item["raw"].values()))
            known = {
                source: value
                for source, value in item["statuses"].items()
                if value is not None
            }
            if len(set(known.values())) > 1:
                injury["conflict"] = dict(known)
                missing.append(f"injuries_konflik:{item['player']}")
            if any(value is None for value in item["statuses"].values()):
                missing.append(f"injuries_status_tidak_dikenal:{item['player']}")
            if item["comment_conflict"]:
                injury["status_comment_conflict"] = True
                missing.append(f"injuries_komentar_konflik:{item['player']}")
            entries.append(injury)
        entries.sort(key=lambda entry: str(entry["player"] or ""))
        merged[tri] = entries
    return merged


def _build_team_block(
    tricode: str,
    prefix: str,
    target: date,
    games_before: list | None,
    stats_season: dict | None,
    stats_last10: dict | None,
    team_name: str | None,
    players: list | None,
    injuries: list | None,
    missing: list,
) -> dict:
    """Rakit satu blok tim (lihat docstring modul untuk kontraknya).

    prefix: "home"/"away" (untuk penamaan entri missing).
    games_before/stats/players/injuries = None berarti fetch sumbernya
    gagal -> field diisi None/kosong + dicatat di `missing`.
    """
    block: dict = {
        "tricode": tricode,
        "team": team_name,
        "stats_season": stats_season if stats_season is not None else _empty_stats(),
        "stats_last10": stats_last10 if stats_last10 is not None else _empty_stats(),
        "form5": [],
        "home_record": {"w": 0, "l": 0, "ppg": None, "opp_ppg": None},
        "road_record": {"w": 0, "l": 0, "ppg": None, "opp_ppg": None},
        "rest_days": None,
        "back_to_back": None,
        "altitude_home": tricode in ALTITUDE_TRICODES,
        "players": [],
        "injuries": [],
    }
    if team_name is None:
        missing.append(f"{prefix}.team")
    if stats_season is None:
        missing.append(f"{prefix}.stats_season")
    if stats_last10 is None:
        missing.append(f"{prefix}.stats_last10")
    if games_before is None:
        missing.append(f"{prefix}.form5")
        missing.append(f"{prefix}.home_record")
        missing.append(f"{prefix}.road_record")
        missing.append(f"{prefix}.rest_days")
        missing.append(f"{prefix}.back_to_back")
    else:
        team_games = _team_games(games_before, tricode)
        block["form5"] = _form5(team_games, tricode)
        block["home_record"] = _record(team_games, tricode, home=True)
        block["road_record"] = _record(team_games, tricode, home=False)
        rest_days, back_to_back = _rest(team_games, target)
        block["rest_days"] = rest_days
        block["back_to_back"] = back_to_back
    if players is None:
        missing.append(f"{prefix}.players")
    else:
        top = sorted(
            players,
            key=lambda p: (
                p.get("mp_per_game") is None,
                -(p.get("mp_per_game") or 0),
            ),
        )[:8]
        chosen = list(top)
        # Pemain cedera di luar 8 besar tetap dimasukkan: model menghitung
        # dampak absen dari daftar pemain ini, jadi pemain OUT yang tidak
        # masuk daftar akan dihitung 0 (perbaikan koordinator Tahap 3 L1:
        # pada contoh DET@ATL 2026-11-22, 7 dari 10 pemain OUT semula
        # dihitung 0 karena di luar 8 besar).
        if injuries:
            punya = {_normalize_player_name(p.get("player")) for p in chosen}
            per_nama = {_normalize_player_name(p.get("player")): p for p in players}
            for cedera in injuries:
                kunci = _normalize_player_name(cedera.get("player"))
                if kunci and kunci not in punya and kunci in per_nama:
                    chosen.append(per_nama[kunci])
                    punya.add(kunci)
        block["players"] = [
            {
                "player": player.get("player"),
                "bpm": player.get("bpm"),
                "mp_per_game": player.get("mp_per_game"),
                "team_tricode": tricode,
            }
            for player in chosen
        ]
    if injuries is None:
        missing.append(f"{prefix}.injuries")
    else:
        block["injuries"] = injuries
    return block


def _tambah_partisipasi(
    block: dict,
    players_rows: list | None,
    bbref_season: int,
    client: HttpClient | None,
    missing: list,
    fetch_errors: dict,
) -> None:
    """Tambahkan missed_last10 ke pemain OUT di blok tim (patch 1b).

    Koreksi tumpang-tindih (temuan auditor 2): sim membutuhkan jumlah
    dari 10 laga terakhir tim yang tidak dimainkan tiap pemain OUT,
    diambil dari game log BBRef (ingest.player_gamelog). Hanya pemain
    OUT di blok ini yang diambil game log-nya (hemat request).

    players_rows: baris mentah fetch_player_advanced tim ini (membawa
    bbref_slug). Best-effort: gagal total -> dicatat di fetch_errors +
    missing, field tidak ditambahkan (sim memakai faktor 1,0 + notes —
    perilaku lama, bukan karangan). Gagal per pemain (tanpa slug /
    fetch gagal) -> dicatat di missing per pemain, field tidak
    ditambahkan.
    """
    injuries = block.get("injuries") or []
    out_names = {
        _normalize_player_name(i.get("player"))
        for i in injuries
        if str(i.get("status") or "").upper() == "OUT"
    }
    players = block.get("players") or []
    slug_by_name = {
        _normalize_player_name(row.get("player")): row.get("bbref_slug")
        for row in players_rows or []
    }
    targets = [
        {
            "player": p.get("player"),
            "bbref_slug": slug_by_name.get(_normalize_player_name(p.get("player"))),
            "team_tricode": block.get("tricode"),
        }
        for p in players
        if _normalize_player_name(p.get("player")) in out_names
    ]
    if not targets:
        return
    tricode = block.get("tricode") or "?"
    try:
        hasil = fetch_missed_last10_many(targets, season=bbref_season, client=client)
    except Exception as exc:  # noqa: BLE001 — best-effort enrichment
        fetch_errors[f"participation_{tricode}"] = f"{type(exc).__name__}: {exc}"
        missing.append(f"{tricode}.participation")
        return
    by_name = {
        _normalize_player_name(nama): entri for nama, entri in (hasil or {}).items()
    }
    for p in players:
        entri = by_name.get(_normalize_player_name(p.get("player")))
        if not isinstance(entri, dict):
            continue
        missed = entri.get("missed_last10")
        if (
            isinstance(missed, int)
            and not isinstance(missed, bool)
            and 0 <= missed <= 10
        ):
            p["missed_last10"] = missed
        else:
            missing.append(f"{tricode}.participation:{p.get('player')}")


def fetch_match_inputs(
    home_tricode: str,
    away_tricode: str,
    game_date: str,
    season: str = "2026-27",
    client: HttpClient | None = None,
) -> FetchResult:
    """Rakit input Otak NBA untuk satu laga.

    home_tricode/away_tricode: tricode stats.nba.com ("LAL", "BOS",
    ...). game_date: "YYYY-MM-DD" (tanggal Eastern, sesuai scoreboard).
    season: "YYYY-YY" (musim berjalan 2026-27). client: HttpClient
    bersama (opsional; None = tiap fetcher memakai client defaultnya
    sendiri dengan limiter + cache + header masing-masing).

    data: paket kontrak (lihat docstring modul). ok=False hanya bila
    SEMUA sumber gagal total atau input tidak valid. Kegagalan
    sebagian -> ok=True dengan field None/kosong + "missing" terisi +
    error tiap fetch di extra["fetch_errors"].
    """
    fetched_at = now_iso()
    home = (home_tricode or "").strip().upper()
    away = (away_tricode or "").strip().upper()
    if home not in _KNOWN_TRICODES or away not in _KNOWN_TRICODES:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"tricode_tidak_dikenal: {home_tricode!r} vs {away_tricode!r}",
        )
    if home == away:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"tim_kandang_sama_dengan_tandang: {home}",
        )
    try:
        target = date.fromisoformat(game_date)
    except (ValueError, TypeError):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error=f"tanggal_tidak_valid: {game_date!r}"
        )
    if not isinstance(season, str) or not _SEASON_RE.match(season):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error=f"musim_tidak_valid: {season!r}"
        )
    bbref_season = _bbref_season(season)

    missing: list[str] = []
    sources: list[dict] = []
    fetch_errors: dict[str, str] = {}
    n_ok = 0

    # 1. Laga musim (tier 1) — bahan form5/rekor/rest/H2H.
    games_result = _safe_fetch(fetch_league_games, season, client=client)
    games_before: list | None = None
    if games_result.ok:
        sources.append(_source_entry("nba_games_season", games_result))
        n_ok += 1
        games_before = _games_before(games_result.data, target)
    else:
        fetch_errors["league_games"] = games_result.error or "gagal"
        missing.append("games_season")
        missing.append("h2h_last5")

    # 2. Statistik musim (tier 1) + fallback BBRef (tier 2, musim saja).
    stats_season_map: dict[str, dict] = {}
    team_names: dict[str, str] = {}
    adv_result = _safe_fetch(fetch_team_advanced_stats, season, client=client)
    if adv_result.ok:
        sources.append(_source_entry("nba_team_advanced_season", adv_result))
        n_ok += 1
        for row in adv_result.data or []:
            tri = row.get("tricode")
            if tri is None:
                continue
            stats_season_map[tri] = {
                "off_rtg": row.get("off_rtg"),
                "def_rtg": row.get("def_rtg"),
                "net_rtg": row.get("net_rtg"),
                "pace": row.get("pace"),
            }
            if row.get("team"):
                team_names[tri] = row["team"]
    else:
        fetch_errors["team_advanced_season"] = adv_result.error or "gagal"
        bbref_result = _safe_fetch(
            fetch_team_advanced, season=bbref_season, client=client
        )
        if bbref_result.ok:
            sources.append(_source_entry("nba_team_advanced_season", bbref_result))
            n_ok += 1
            for row in bbref_result.data or []:
                tri = _team_tricode(row.get("team") or "")
                if tri is None:
                    continue
                stats_season_map[tri] = {
                    "off_rtg": _to_float(row.get("off_rtg")),
                    "def_rtg": _to_float(row.get("def_rtg")),
                    "net_rtg": _to_float(row.get("net_rtg")),
                    "pace": _to_float(row.get("pace")),
                }
                team_names[tri] = row["team"]
        else:
            fetch_errors["team_advanced_bbref"] = bbref_result.error or "gagal"

    # Nama tim cadangan dari daftar laga (bila kedua sumber statistik gagal).
    if games_before is not None:
        for game in games_before:
            for tri_key, name_key in (
                ("home_tricode", "home_team"),
                ("away_tricode", "away_team"),
            ):
                tri = game.get(tri_key)
                if tri in (home, away) and tri not in team_names and game.get(name_key):
                    team_names[tri] = game[name_key]

    # 3. Statistik 10 laga terakhir (tier 1; tanpa fallback).
    stats_last10_map: dict[str, dict] = {}
    adv10_result = _safe_fetch(
        fetch_team_advanced_stats, season, last_n_games=10, client=client
    )
    if adv10_result.ok:
        sources.append(_source_entry("nba_team_advanced_last10", adv10_result))
        n_ok += 1
        for row in adv10_result.data or []:
            tri = row.get("tricode")
            if tri is None:
                continue
            stats_last10_map[tri] = {
                "off_rtg": row.get("off_rtg"),
                "def_rtg": row.get("def_rtg"),
                "net_rtg": row.get("net_rtg"),
                "pace": row.get("pace"),
            }
    else:
        fetch_errors["team_advanced_last10"] = adv10_result.error or "gagal"

    # 4. Pemain inti (BBRef, tier 2).
    players_by_team: dict[str, list] | None = None
    players_result = _safe_fetch(
        fetch_player_advanced, season=bbref_season, client=client
    )
    if players_result.ok:
        sources.append(_source_entry("nba_player_impact", players_result))
        n_ok += 1
        players_by_team = {home: [], away: []}
        for row in players_result.data or []:
            tri = row.get("team")
            if tri in players_by_team:
                players_by_team[tri].append(row)
    else:
        fetch_errors["player_advanced"] = players_result.error or "gagal"

    # 5+6. Cedera: PDF resmi (tier 1) + ESPN (tier 2).
    pdf_result = _safe_fetch(fetch_report, date=game_date, client=client)
    if pdf_result.ok:
        sources.append(_source_entry("nba_injuries", pdf_result))
        n_ok += 1
    else:
        fetch_errors["injuries_official_pdf"] = pdf_result.error or "gagal"
        missing.append("injuries_official_pdf")
    espn_result = _safe_fetch(fetch_injuries_nba, client=client)
    if espn_result.ok:
        sources.append(_source_entry("nba_injuries", espn_result))
        n_ok += 1
    else:
        fetch_errors["injuries_espn"] = espn_result.error or "gagal"
        missing.append("injuries_espn")
    injuries_by_team: dict[str, list] | None = None
    if pdf_result.ok or espn_result.ok:
        injuries_by_team = _merge_injuries(
            pdf_result, espn_result, (home, away), missing
        )

    # Rakit blok tim.
    home_block = _build_team_block(
        home,
        "home",
        target,
        games_before,
        stats_season_map.get(home),
        stats_last10_map.get(home),
        team_names.get(home),
        players_by_team.get(home) if players_by_team is not None else None,
        injuries_by_team.get(home) if injuries_by_team is not None else None,
        missing,
    )
    away_block = _build_team_block(
        away,
        "away",
        target,
        games_before,
        stats_season_map.get(away),
        stats_last10_map.get(away),
        team_names.get(away),
        players_by_team.get(away) if players_by_team is not None else None,
        injuries_by_team.get(away) if injuries_by_team is not None else None,
        missing,
    )

    # 7. Partisipasi 10 laga terakhir untuk pemain OUT (patch 1b,
    #    koreksi tumpang-tindih): game log BBRef per pemain OUT.
    #    Best-effort: gagal -> missed_last10 tidak ada, sim memakai
    #    faktor 1,0 + notes (lihat _tambah_partisipasi).
    _tambah_partisipasi(
        home_block,
        players_by_team.get(home) if players_by_team is not None else None,
        bbref_season,
        client,
        missing,
        fetch_errors,
    )
    _tambah_partisipasi(
        away_block,
        players_by_team.get(away) if players_by_team is not None else None,
        bbref_season,
        client,
        missing,
        fetch_errors,
    )

    # H2H 5 pertemuan terakhir musim ini (terbaru dulu).
    h2h: list[dict] = []
    if games_before is not None:
        meetings = [
            game
            for game in games_before
            if {game.get("home_tricode"), game.get("away_tricode")} == {home, away}
        ]
        meetings.sort(
            key=lambda game: (
                str(game.get("game_date") or ""),
                str(game.get("game_id") or ""),
            ),
            reverse=True,
        )
        h2h = meetings[:5]

    # Rata-rata liga dari statistik musim (sumber mana pun yang berhasil).
    league = {
        "avg_pace": _mean([row.get("pace") for row in stats_season_map.values()]),
        "avg_off_rtg": _mean([row.get("off_rtg") for row in stats_season_map.values()]),
    }
    if league["avg_pace"] is None:
        missing.append("league.avg_pace")
    if league["avg_off_rtg"] is None:
        missing.append("league.avg_off_rtg")

    # Bendera turnamen: belum bisa ditentukan dari data mana pun —
    # jangan tebak tanggal NBA Cup/Playoff.
    missing.append("tournament_flag_tidak_dapat_ditentukan")

    data = {
        "match": {
            "home_tricode": home,
            "away_tricode": away,
            "game_date": game_date,
            "season": season,
        },
        "home": home_block,
        "away": away_block,
        "h2h_last5": h2h,
        "tournament": None,
        "league": league,
        "missing": missing,
        "sources": sources,
        "fetched_at": fetched_at,
    }
    ok = n_ok > 0
    error = None
    if not ok:
        error = "semua_sumber_gagal: " + "; ".join(
            f"{kind}={msg}" for kind, msg in fetch_errors.items()
        )
    extra: dict = {}
    if fetch_errors:
        extra["fetch_errors"] = fetch_errors
    return FetchResult(
        SOURCE, TIER, fetched_at, ok, data=data, error=error, extra=extra
    )
