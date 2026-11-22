"""Deteksi anomali dalam laga NBA yang sedang berjalan (Tahap 3 Langkah 4).

Dipakai CLI ``pantau`` untuk memberi peringatan dini pada kaki Under:
tiga pola yang membuat total akhir cenderung LEBIH TINGGI dari
perkiraan pra-laga — hujan lemparan 3 angka, lemparan bebas
berlebihan, dan laju skor yang terlalu cepat.

KONTRAK MASUK:
- ``live_game``: dict LiveGame dari pekerja A (ingest/live_nba.py):
  match_id ("AWAY@HOME_YYYY-MM-DD"), espn_game_id, home_abbr,
  away_abbr, home_team, away_team, status ("belum_mulai" |
  "berjalan" | "selesai"), period, clock_display, seconds_remaining,
  home_score, away_score, line_scores, stats ({abbr: {fg3_made,
  fg3_attempted, ft_made, ft_attempted}} | None), fetched_at, source.
- ``baselines``: dict {tricode: {fg3a_per_game, fta_per_game}} dari
  ingest.bbref.fetch_team_shooting_baselines (atau list mentah dari
  fetcher itu — diindeks otomatis lewat index_baselines).
- ``projection``: dict dari engine/live_status.project_final_total:
  {projected_total, method, live_rate_ppm, pregame_rate_ppm,
  minutes_elapsed, minutes_remaining, ot_risk, notes}.

KELUARAN: detect_anomalies mengembalikan (anomalies, skipped).
- anomalies: list dict {type, description, numbers, implication}.
  type salah satu dari "hujan_3pt" | "ft_berlebihan" |
  "laju_skor_tinggi". description + implication Bahasa Indonesia;
  numbers berisi angka-angka yang dipakai (dari data, tidak ditebak).
- skipped: list dict {type, reason} — jenis pemeriksaan yang TIDAK
  bisa dievaluasi (data tidak ada) + alasannya. Data gagal TIDAK
  pernah ditebak: jenis itu dilewati dan dicatat.

AMBANG — SEMUA dari config/playstyle.yaml section ``live:`` (dibaca
pekerja B; modul ini hanya MEMBACA, tidak mengubah config):
  - anomaly_min_minutes_elapsed (12): di bawah ini sampel terlalu
    kecil — semua jenis dilewati.
  - anomaly_fg3_rate_multiplier (1.5): laju 3PA gabungan >= baseline
    gabungan x pengali -> "hujan_3pt".
  - anomaly_ft_rate_multiplier (1.5): laju FTA gabungan >= baseline
    gabungan x pengali -> "ft_berlebihan".
  - anomaly_scoring_rate_multiplier (1.15): live_rate_ppm >=
    pregame_rate_ppm x pengali -> "laju_skor_tinggi" (hanya bila
    pregame_rate_ppm ada).
Kunci hilang -> ValueError (fail-closed, tanpa default diam-diam).
"""

from __future__ import annotations

# Jenis anomali yang diperiksa, sesuai urutan evaluasi.
ANOMALY_TYPES = ("hujan_3pt", "ft_berlebihan", "laju_skor_tinggi")

# Kunci wajib section live: di playstyle.yaml (pekerja B yang menulis).
_LIVE_KEYS = (
    "anomaly_min_minutes_elapsed",
    "anomaly_fg3_rate_multiplier",
    "anomaly_ft_rate_multiplier",
    "anomaly_scoring_rate_multiplier",
)

_MENIT_REGULASI = 48.0
_DETIK_REGULASI = 48 * 60


def _bagian_live(cfg: dict | None) -> dict:
    """Ambil section ``live:`` dari config (atau cfg itu sendiri).

    cfg boleh berupa config playstyle lengkap (ada kunci "live") atau
    section live itu sendiri (dipakai tes). cfg None -> baca
    playstyle.yaml lewat config.load_playstyle. Kunci wajib hilang
    -> ValueError (fail-closed).
    """
    if cfg is None:
        from config import load_playstyle

        cfg = load_playstyle()
    live = cfg.get("live") if isinstance(cfg, dict) else None
    if live is None:
        live = cfg
    if not isinstance(live, dict):
        raise ValueError("config live: bukan dict")
    hilang = [k for k in _LIVE_KEYS if live.get(k) is None]
    if hilang:
        raise ValueError("config live: kehilangan kunci: " + ", ".join(hilang))
    return live


def index_baselines(baselines: dict | list | None) -> dict:
    """Indeks baseline jadi {tricode: {fg3a_per_game, fta_per_game}}.

    Menerima dict yang sudah terindeks (dikembalikan apa adanya) atau
    list mentah dari fetch_team_shooting_baselines (diindeks lewat
    kunci "tricode"). None -> {}.
    """
    if baselines is None:
        return {}
    if isinstance(baselines, dict):
        return baselines
    hasil = {}
    for tim in baselines:
        if isinstance(tim, dict) and isinstance(tim.get("tricode"), str):
            hasil[tim["tricode"]] = tim
    return hasil


def minutes_elapsed_dari_live(live_game: dict) -> float | None:
    """Menit berjalan dari LiveGame (fallback bila projection tak ada).

    Dihitung dari seconds_remaining pada kuarter reguler
    (period <= 4): (2880 - seconds_remaining) / 60. Periode
    perpanjangan (OT) tidak bisa dihitung dari field ini saja
    (makna seconds_remaining di OT tidak didefinisikan kontrak) ->
    None (pemeriksaan dilewati, bukan ditebak). None juga bila
    seconds_remaining/period hilang atau bukan angka.
    """
    period = live_game.get("period")
    sisa = live_game.get("seconds_remaining")
    if not isinstance(period, (int, float)) or not isinstance(sisa, (int, float)):
        return None
    if period > 4:
        return None
    menit = (_DETIK_REGULASI - sisa) / 60.0
    if menit < 0:
        return 0.0
    if menit > _MENIT_REGULASI:
        return _MENIT_REGULASI
    return menit


def _angka(nilai) -> float | None:
    """Nilai jadi float, atau None bila bukan angka (bool ditolak)."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    return float(nilai)


def _laju_per_48(jumlah: float, menit: float) -> float:
    """Laju per 48 menit dari jumlah yang terjadi dalam `menit`."""
    return jumlah / menit * _MENIT_REGULASI


def detect_anomalies(
    live_game: dict,
    baselines: dict | list | None,
    projection: dict | None,
    cfg: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Deteksi anomali dalam laga. Kembalikan (anomalies, skipped).

    live_game: dict LiveGame (kontrak pekerja A). baselines: dict
    {tricode: {...}} atau list mentah fetcher BBRef. projection:
    dict project_final_total (boleh None — jenis laju skor lalu
    dilewati). cfg: config playstyle lengkap / section live / None
    (baca playstyle.yaml). Lihat docstring modul untuk arti
    anomalies + skipped.
    """
    live = _bagian_live(cfg)
    min_menit = float(live["anomaly_min_minutes_elapsed"])
    mult_3pt = float(live["anomaly_fg3_rate_multiplier"])
    mult_ft = float(live["anomaly_ft_rate_multiplier"])
    mult_skor = float(live["anomaly_scoring_rate_multiplier"])

    projection = projection or {}
    menit = _angka(projection.get("minutes_elapsed"))
    if menit is None:
        menit = minutes_elapsed_dari_live(live_game)

    def lewati(jenis: str, alasan: str) -> dict:
        return {"type": jenis, "reason": alasan}

    if menit is None:
        return [], [lewati(j, "menit_berjalan_tidak_diketahui") for j in ANOMALY_TYPES]
    if menit < min_menit:
        alasan = (
            f"sampel_terlalu_kecil: baru {menit:.1f} menit " f"(minimum {min_menit:g})"
        )
        return [], [lewati(j, alasan) for j in ANOMALY_TYPES]

    anomalies: list[dict] = []
    skipped: list[dict] = []
    dasar = index_baselines(baselines)
    home = live_game.get("home_abbr")
    away = live_game.get("away_abbr")
    stats = live_game.get("stats")

    # -- (a) hujan 3PT + (b) FT berlebihan: butuh stats + baseline. --
    for jenis, kunci_stat, kunci_dasar, mult, label in (
        ("hujan_3pt", "fg3_attempted", "fg3a_per_game", mult_3pt, "3PA"),
        ("ft_berlebihan", "ft_attempted", "fta_per_game", mult_ft, "FTA"),
    ):
        if not isinstance(stats, dict):
            skipped.append(lewati(jenis, "stats_tidak_ada (box score belum diambil)"))
            continue
        jumlah: float | None = None
        hilang_stat = []
        for abbr in (home, away):
            tim_stat = stats.get(abbr) if isinstance(abbr, str) else None
            nilai = (
                _angka(tim_stat.get(kunci_stat)) if isinstance(tim_stat, dict) else None
            )
            if nilai is None:
                hilang_stat.append(abbr)
            else:
                jumlah = nilai if jumlah is None else jumlah + nilai
        if hilang_stat:
            skipped.append(
                lewati(
                    jenis,
                    "stats_tidak_lengkap: " + ", ".join(str(a) for a in hilang_stat),
                )
            )
            continue
        dasar_gabung: float | None = None
        hilang_dasar = []
        for abbr in (home, away):
            nilai = (
                _angka(dasar.get(abbr, {}).get(kunci_dasar))
                if isinstance(abbr, str)
                else None
            )
            if nilai is None:
                hilang_dasar.append(abbr)
            else:
                dasar_gabung = nilai if dasar_gabung is None else dasar_gabung + nilai
        if hilang_dasar or dasar_gabung is None:
            skipped.append(
                lewati(
                    jenis,
                    "baseline_tidak_ada: " + ", ".join(str(a) for a in hilang_dasar),
                )
            )
            continue
        assert jumlah is not None  # dijaga cabang di atas
        laju = _laju_per_48(jumlah, menit)
        ambang = dasar_gabung * mult
        numbers = {
            "minutes_elapsed": menit,
            f"{label.lower()}_gabungan": jumlah,
            "laju_per_48": laju,
            "baseline_gabungan_per_laga": dasar_gabung,
            "multiplier": mult,
            "ambang_per_48": ambang,
        }
        if laju < ambang:
            continue
        if jenis == "hujan_3pt":
            anomalies.append(
                {
                    "type": jenis,
                    "description": (
                        f"Hujan 3 angka: kedua tim sudah mencoba "
                        f"{jumlah:g} tembakan 3 angka dalam {menit:.1f} "
                        f"menit (laju {laju:.1f} per 48 menit, "
                        f"rata-rata musim gabungan "
                        f"{dasar_gabung:.1f} — {laju / dasar_gabung:.2f}x)"
                        if dasar_gabung
                        else f"Hujan 3 angka: laju {laju:.1f} per 48 menit"
                    ),
                    "numbers": numbers,
                    "implication": (
                        "Tembakan 3 angka yang jauh di atas rata-rata "
                        "biasanya menambah total skor — kaki Under "
                        "makin berisiko."
                    ),
                }
            )
        else:
            anomalies.append(
                {
                    "type": jenis,
                    "description": (
                        f"Lemparan bebas berlebihan: kedua tim sudah "
                        f"mencoba {jumlah:g} free throw dalam "
                        f"{menit:.1f} menit (laju {laju:.1f} per 48 "
                        f"menit, rata-rata musim gabungan "
                        f"{dasar_gabung:.1f} — {laju / dasar_gabung:.2f}x)"
                        if dasar_gabung
                        else (
                            "Lemparan bebas berlebihan: laju "
                            f"{laju:.1f} per 48 menit"
                        )
                    ),
                    "numbers": numbers,
                    "implication": (
                        "Banyak pelanggaran = banyak free throw gratis "
                        "dan jam berhenti — total skor cenderung naik, "
                        "kaki Under makin berisiko."
                    ),
                }
            )

    # -- (c) laju skor tinggi: butuh live_rate + pregame_rate. --
    laju_live = _angka(projection.get("live_rate_ppm"))
    laju_pra = _angka(projection.get("pregame_rate_ppm"))
    if laju_live is None:
        skipped.append(lewati("laju_skor_tinggi", "laju_live_tidak_ada"))
    elif laju_pra is None:
        skipped.append(
            lewati(
                "laju_skor_tinggi",
                "laju_pra_laga_tidak_ada (median pra-laga tidak ada)",
            )
        )
    else:
        ambang_skor = laju_pra * mult_skor
        if laju_live >= ambang_skor:
            anomalies.append(
                {
                    "type": "laju_skor_tinggi",
                    "description": (
                        f"Laju skor tinggi: {laju_live:.2f} poin/menit "
                        f"sejauh ini, di atas laju pra-laga "
                        f"{laju_pra:.2f} poin/menit x {mult_skor:g} "
                        f"(ambang {ambang_skor:.2f})"
                    ),
                    "numbers": {
                        "minutes_elapsed": menit,
                        "live_rate_ppm": laju_live,
                        "pregame_rate_ppm": laju_pra,
                        "multiplier": mult_skor,
                        "ambang_ppm": ambang_skor,
                    },
                    "implication": (
                        "Skor berjalan lebih cepat dari perkiraan "
                        "pra-laga — proyeksi total akhir naik, kaki "
                        "Under makin berisiko."
                    ),
                }
            )

    return anomalies, skipped


def format_anomalies(
    anomalies: list[dict],
    skipped: list[dict] | None = None,
    match_id: str | None = None,
) -> str:
    """Render daftar anomali + yang dilewati jadi teks Indonesia.

    Dipakai CLI pantau. Baris pertama judul per laga bila match_id
    diberi; tanpa anomali dan tanpa yang dilewati, satu baris
    "tidak ada anomali".
    """
    baris: list[str] = []
    if match_id:
        # Tanpa anomali nyata, judulnya "Pemeriksaan" (bukan "Anomali")
        # agar yang dilewati tidak terbaca sebagai peringatan.
        judul = "Anomali" if anomalies else "Pemeriksaan"
        baris.append(f"{judul} {match_id}:")
    if not anomalies and not skipped:
        baris.append("  tidak ada anomali")
        return "\n".join(baris)
    for anom in anomalies:
        baris.append(f"  ! {anom.get('description', anom.get('type'))}")
        if anom.get("implication"):
            baris.append(f"    -> {anom['implication']}")
    for item in skipped or []:
        baris.append(
            f"  - {item.get('type')}: dilewati "
            f"({item.get('reason', 'tanpa alasan')})"
        )
    return "\n".join(baris)
