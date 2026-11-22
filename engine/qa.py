"""Tanya-jawab soal laga/analisis NBA (Tahap 3 Langkah 3).

Modul ini menjawab pertanyaan user tentang SATU artefak analisis
(`nba_analysis` format_version 1, lihat engine/nba_analysis.py) dalam
Bahasa Indonesia sehari-hari, tanpa jargon. Pengenalan maksud
pertanyaan DETERMINISTIK dari kata kunci (tanpa LLM).

Fungsi utama: `answer(analysis, question, config=None)` ->
`{"question", "intent", "answer", "numbers", "verified"}`.
`numbers` hanya berisi angka dari artefak/kode/config — tidak ada
angka karangan. `verified` False bila ada bagian jawaban yang
"tidak terverifikasi" (data tidak ada di artefak).

Intent yang didukung (lihat SUPPORTED_QUESTIONS):
  kenapa_total, bagaimana_jika_absen, garis_teraman, kabar_pemain,
  kenapa_beda_model_market, peluang_laga, unknown.

SIM ULANG (intent bagaimana_jika_absen): jawaban dihitung dengan
simulasi ulang nyata (engine/nba_sim.simulate) sebanyak
RESIM_ITERATIONS = 20.000 iterasi — lebih kecil dari 100.000 iterasi
analisis awal agar cepat, dan jumlahnya selalu disebutkan di jawaban.
Perbandingan apel-ke-apel: simulasi dasar DAN simulasi skenario
dijalankan ulang pada iterasi dan seed yang sama (seed dari artefak
bila ada, else 7). Skenario standar dilewati (scenarios=[]) karena
hanya base case yang dibandingkan; pemain hipotetis absen ditambahkan
ke daftar cedera OUT pada SALINAN inputs (artefak asli tidak diubah).

KOMPONEN PROYEKSI (intent kenapa_total): rating gabungan dihitung
ulang dari inputs dengan bobot resensi config, rata-rata poin dasar
dengan fungsi engine nba_sim.project_points, dan dampak pemain absen
dengan nba_sim._dampak_pemain (rumus yang sama dengan simulasi, jadi
angkanya identik dengan yang dipakai sim — bukan perkiraan kedua).
Bila komponen tidak bisa dihitung (inputs hilang), bagian itu dijawab
"tidak terverifikasi", bukan dikarang.

"KENAPA BEDA?" (intent kenapa_beda_model_market): mengikuti aturan
DECISIONS.md — ambang selisih peluang 8 poin
(anomaly.model_vs_market_points) dan ambang selisih median-garis
5 poin (market_line_check.total_gap_points), keduanya dari config.
Kesimpulan mekanis dari data artefak saja: (b) "Model kemungkinan
kurang data" bila ada kelemahan data yang tercatat (status HOLD /
MODEL_ONLY / cedera 1 sumber), else (c) "Tidak ditemukan alasan".
Alasan (a) "Pasar kemungkinan tahu sesuatu" TIDAK BISA ditegakkan
dari satu artefak (butuh kabar cedera segar + pergerakan harga —
itu pekerjaan recheck), jadi tidak pernah diklaim; bila user butuh
itu, jawaban mengarahkan ke recheck.

Modul ini murni baca + sim ulang offline: TIDAK memanggil Odds API
(0 kredit), TIDAK menulis ke out/ atau data/, TIDAK mengubah artefak.
"""

from __future__ import annotations

import copy
import math

import config as config_mod
from engine import nba_sim as nba_sim_mod

# Jumlah iterasi sim ulang untuk pertanyaan "bagaimana jika ... absen?"
# (lebih kecil dari 100.000 iterasi analisis awal agar cepat; jawaban
# selalu menyebutkan angka ini). Tes memakai nilai kecil lewat argumen
# iterations= pada answer().
RESIM_ITERATIONS = 20000

# Seed sim ulang bila artefak tidak membawa seed (seed artefak dipakai
# bila ada, agar sim ulang sedekat mungkin dengan sim awal).
_RESIM_SEED_DEFAULT = 7

# Intent yang dikenali + contoh pertanyaan user (dipakai jawaban unknown).
SUPPORTED_QUESTIONS = [
    {
        "intent": "kenapa_total",
        "contoh": "Kenapa totalnya 219?",
        "keterangan": "uraian komponen proyeksi total",
    },
    {
        "intent": "bagaimana_jika_absen",
        "contoh": "Apa jadinya kalau Cade Cunningham absen?",
        "keterangan": "sim ulang dengan pemain itu absen",
    },
    {
        "intent": "garis_teraman",
        "contoh": "Garis Asuransi mana yang paling aman?",
        "keterangan": "bandingkan garis Asuransi dan Utama",
    },
    {
        "intent": "kabar_pemain",
        "contoh": "Siapa yang diragukan tampil?",
        "keterangan": "kabar cedera dan ketersediaan pemain",
    },
    {
        "intent": "kenapa_beda_model_market",
        "contoh": "Kenapa model dan market beda?",
        "keterangan": "selisih model vs market dan alasannya",
    },
    {
        "intent": "peluang_laga",
        "contoh": "Berapa peluang masuk OT?",
        "keterangan": "peluang perpanjangan waktu dan peluang menang",
    },
]

# Status cedera -> kata sehari-hari.
_STATUS_KATA = {
    "OUT": "pasti absen",
    "DOUBTFUL": "diragukan — kemungkinan besar absen",
    "QUESTIONABLE": "diragukan — masih mungkin main",
    "PROBABLE": "kemungkinan besar main",
    "AVAILABLE": "tersedia",
}

# Alasan kaki tidak memenuhi (cushion/nba_analysis) -> kata sehari-hari.
_ALASAN_KAKI = {
    "tidak_ada_garis_memenuhi": (
        "tidak ada garis di bursa yang cukup jauh di atas perkiraan"
    ),
    "p_model_tidak_ada": "peluang model untuk garis itu tidak tersedia",
    "garis_market_tidak_ada": "garis market tidak tersedia",
    "median_tidak_ada": "nilai tengah model tidak tersedia",
    "tangga_kosong": "tangga garis dari bursa kosong",
    "persentil_tidak_lengkap": "sebaran simulasi tidak lengkap",
    "blend_gagal": "gabungan peluang model dan market gagal dihitung",
}

_LABEL_TIKET = {"insurance": "Asuransi", "main": "Utama"}


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


def _muat_cfg(cfg: dict | None) -> dict:
    """Config efektif: argumen bila diberikan, else playstyle.yaml.

    Gagal baca -> dict kosong (ambang lalu memakai default modul ini,
    yang dicatat di numbers sebagai ambang yang dipakai).
    """
    if cfg is not None:
        return cfg
    try:
        return config_mod.load_playstyle()
    except Exception:  # noqa: BLE001 - config gagal bukan alasan meledak
        return {}


def _ambang(cfg: dict, default: float, *kunci: str) -> float:
    """Baca satu ambang numerik dari config; default bila hilang/tidak valid."""
    try:
        nilai = config_mod.get_value(cfg, *kunci)
    except Exception:  # noqa: BLE001 - kunci hilang -> default
        return default
    angka = _angka(nilai)
    return angka if angka is not None else default


def _fmt_poin(nilai: float) -> str:
    """Format poin Indonesia: 219 -> "219", 233.5 -> "233,5"."""
    dibulatkan = round(nilai, 1)
    if dibulatkan == int(dibulatkan):
        return str(int(dibulatkan))
    return f"{dibulatkan:.1f}".replace(".", ",")


def _fmt_persen(peluang: float) -> str:
    """Format peluang 0-1 jadi persen Indonesia: 0.77 -> "77%"."""
    persen = round(peluang * 100.0, 1)
    if persen == int(persen):
        return f"{int(persen)}%"
    return f"{persen:.1f}%".replace(".", ",")


def _fmt_sen(harga: float) -> str:
    """Format harga sen: 67.0 -> "67¢", 66.5 -> "66,5¢"."""
    return f"{_fmt_poin(harga)}¢"


def _fmt_ribu(nilai: int) -> str:
    """Format ribuan Indonesia: 20000 -> "20.000"."""
    return f"{nilai:,}".replace(",", ".")


def _nama_laga(analysis: dict) -> str:
    """Nama laga untuk jawaban, mis. "Detroit Pistons di Atlanta Hawks"."""
    inputs = analysis.get("inputs") if isinstance(analysis, dict) else None
    home = analysis.get("home_tricode") if isinstance(analysis, dict) else None
    away = analysis.get("away_tricode") if isinstance(analysis, dict) else None
    nama_home = home or "tuan rumah"
    nama_away = away or "tamu"
    if isinstance(inputs, dict):
        blok_home = inputs.get("home") or {}
        blok_away = inputs.get("away") or {}
        if isinstance(blok_home, dict) and isinstance(blok_home.get("team"), str):
            nama_home = blok_home["team"]
        if isinstance(blok_away, dict) and isinstance(blok_away.get("team"), str):
            nama_away = blok_away["team"]
    if home and away:
        return f"{nama_away} di {nama_home}"
    return "laga ini"


def _simulasi(analysis: dict) -> dict | None:
    """Dict simulation artefak, atau None bila tidak ada/bukan dict."""
    sim = analysis.get("simulation") if isinstance(analysis, dict) else None
    return sim if isinstance(sim, dict) else None


def _inputs(analysis: dict) -> dict | None:
    """Dict inputs artefak, atau None bila tidak ada/bukan dict."""
    inputs = analysis.get("inputs") if isinstance(analysis, dict) else None
    return inputs if isinstance(inputs, dict) else None


def _dist_total(analysis: dict) -> dict:
    """Distribusi total sim ({} bila tidak ada)."""
    sim = _simulasi(analysis)
    if sim is None:
        return {}
    dist = (sim.get("score_distribution") or {}).get("total") or {}
    return dist if isinstance(dist, dict) else {}


def _ringkasan_inputs(analysis: dict) -> dict:
    """inputs_summary sim ({} bila tidak ada)."""
    sim = _simulasi(analysis)
    if sim is None:
        return {}
    ringkasan = sim.get("inputs_summary") or {}
    return ringkasan if isinstance(ringkasan, dict) else {}


def _kaki(analysis: dict) -> list[dict]:
    """Daftar leg artefak (hanya dict)."""
    legs = analysis.get("legs") if isinstance(analysis, dict) else None
    if not isinstance(legs, list):
        return []
    return [leg for leg in legs if isinstance(leg, dict)]


def _kaki_tiket(analysis: dict, ticket: str) -> dict | None:
    """Leg dengan ticket tertentu, atau None."""
    for leg in _kaki(analysis):
        if leg.get("ticket") == ticket:
            return leg
    return None


def _entri_cedera(analysis: dict) -> list[dict]:
    """Entri cedera gabungan dari blok injuries artefak."""
    injuries = analysis.get("injuries") if isinstance(analysis, dict) else None
    if not isinstance(injuries, dict):
        return []
    entri = injuries.get("entries") or []
    return [e for e in entri if isinstance(e, dict)]


def _daftar_pemain(analysis: dict) -> dict[str, dict]:
    """Peta nama pemain -> {nama, tim, tricode} dari inputs kedua tim.

    Kunci peta adalah nama persis seperti di inputs (pencocokan di
    _cari_pemain tidak peka huruf besar/kecil).
    """
    pemain: dict[str, dict] = {}
    inputs = _inputs(analysis)
    if inputs is None:
        return pemain
    for tim, kunci in (("home", "home"), ("away", "away")):
        blok = inputs.get(kunci) or {}
        if not isinstance(blok, dict):
            continue
        tricode = blok.get("tricode")
        for entri in blok.get("players") or []:
            if not isinstance(entri, dict):
                continue
            nama = entri.get("player")
            if isinstance(nama, str) and nama and nama not in pemain:
                pemain[nama] = {
                    "nama": nama,
                    "tim": tim,
                    "tricode": tricode if isinstance(tricode, str) else None,
                    "data": entri,
                }
    # Pemain yang hanya muncul di daftar cedera (tanpa data BPM/menit)
    # tetap dikenal namanya — untuk pertanyaan kabar pemain.
    for entri in _entri_cedera(analysis):
        nama = entri.get("player")
        if isinstance(nama, str) and nama and nama not in pemain:
            tricode = entri.get("team_tricode")
            tim = "home" if tricode == analysis.get("home_tricode") else "away"
            pemain[nama] = {
                "nama": nama,
                "tim": tim,
                "tricode": tricode if isinstance(tricode, str) else None,
                "data": None,
            }
    return pemain


def _cari_pemain(pertanyaan: str, analysis: dict) -> dict | None:
    """Cari pemain yang disebut di pertanyaan (cocok nama lengkap dulu).

    Nama lengkap dicocokkan sebagai substring (tidak peka huruf);
    bila tidak ada, nama belakang (kata terakhir, >= 3 huruf) dicocokkan
    sebagai kata utuh bila unik di antara pemain yang dikenal. None
    bila tidak ada yang cocok / cocoknya ambigu.
    """
    teks = pertanyaan.lower()
    pemain = _daftar_pemain(analysis)
    for nama in sorted(pemain, key=len, reverse=True):
        if nama.lower() in teks:
            return pemain[nama]
    kata = set(teks.replace("?", "").replace(".", "").replace(",", "").split())
    cocok_belakang: list[dict] = []
    for nama, info in pemain.items():
        belakang = nama.strip().split()[-1].lower()
        if len(belakang) >= 3 and belakang in kata:
            cocok_belakang.append(info)
    if len(cocok_belakang) == 1:
        return cocok_belakang[0]
    return None


def _status_pemain(analysis: dict, nama: str) -> str | None:
    """Status cedera pemain (huruf besar) dari entri cedera, atau None."""
    for entri in _entri_cedera(analysis):
        if entri.get("player") == nama:
            status = entri.get("status")
            if isinstance(status, str) and status.strip():
                return status.strip().upper()
    inputs = _inputs(analysis)
    if inputs is not None:
        for kunci in ("home", "away"):
            blok = inputs.get(kunci) or {}
            if not isinstance(blok, dict):
                continue
            for entri in blok.get("injuries") or []:
                if isinstance(entri, dict) and entri.get("player") == nama:
                    status = entri.get("status")
                    if isinstance(status, str) and status.strip():
                        return status.strip().upper()
    return None


def _hasil(
    pertanyaan: str, intent: str, jawaban: str, numbers: dict, verified: bool
) -> dict:
    """Rakit dict hasil answer() (kontrak: 5 kunci)."""
    return {
        "question": pertanyaan,
        "intent": intent,
        "answer": jawaban,
        "numbers": numbers,
        "verified": verified,
    }


def _kata_utuh(teks: str, kata: str) -> bool:
    """Apakah kata muncul sebagai kata utuh di teks (bukan substring).

    "ot" sebagai substring ada di "total" — pencocokan kata utuh
    mencegah "peluang total ..." salah dikenali sebagai pertanyaan OT.
    """
    kata_bersih = teks.replace("?", " ").replace(".", " ").replace(",", " ").split()
    return kata in kata_bersih


def detect_intent(question: str) -> str:
    """Kenali intent pertanyaan dari kata kunci (deterministik, tanpa LLM).

    Urutan penting: pertanyaan hipotetis ("kalau ... absen?") dicek
    dulu supaya tidak tertukar dengan kabar pemain; "kenapa beda?"
    dicek sebelum "kenapa total?" karena keduanya memakai "kenapa".
    """
    if not isinstance(question, str):
        return "unknown"
    teks = question.lower()

    hipotetis = (
        "kalau",
        "kalo",
        "seandainya",
        "andai",
        "misal",
        "jika",
        "apa jadinya",
        "apa yang terjadi",
        "gimana kalau",
        "bagaimana kalau",
    )
    absen_kata = (
        "absen",
        "tidak main",
        "tidak tampil",
        "nggak main",
        "ga main",
        "tidak bermain",
        "cedera",
    )
    if any(kata in teks for kata in hipotetis) and any(
        kata in teks for kata in absen_kata
    ):
        return "bagaimana_jika_absen"

    if "kenapa beda" in teks or (
        "beda" in teks
        and any(
            kata in teks for kata in ("model", "market", "pasar", "bandar", "bursa")
        )
    ):
        return "kenapa_beda_model_market"
    if "selisih" in teks and any(
        kata in teks for kata in ("model", "market", "pasar", "bandar")
    ):
        return "kenapa_beda_model_market"

    if "garis" in teks and any(
        kata in teks
        for kata in (
            "aman",
            "pilih",
            "sebaiknya",
            "mana",
            "asuransi",
            "utama",
            "paling",
            "bagus",
            "rekomendasi",
        )
    ):
        return "garis_teraman"
    if (
        "asuransi" in teks
        and "utama" in teks
        and any(kata in teks for kata in ("pilih", "mana", "sebaiknya"))
    ):
        return "garis_teraman"

    if (
        "diragukan" in teks
        or "kabar" in teks
        or "status" in teks
        or ("siapa" in teks and "cedera" in teks)
        or ("siapa" in teks and "absen" in teks)
        or ("siapa" in teks and "tidak main" in teks)
        or ("siapa" in teks and "tidak tampil" in teks)
        or ("ada yang" in teks and "cedera" in teks)
        or ("apakah" in teks and ("main" in teks or "tampil" in teks))
    ):
        return "kabar_pemain"

    if (
        ("peluang" in teks or "kemungkinan" in teks or "probabilitas" in teks)
        and (
            _kata_utuh(teks, "ot")
            or any(
                kata in teks
                for kata in (
                    "overtime",
                    "perpanjangan",
                    "menang",
                    "kandang",
                    "tandang",
                    "seri",
                    "imbang",
                )
            )
        )
    ) or (
        "siapa" in teks
        and "menang" in teks
        or "bakal ot" in teks
        or "masuk ot" in teks
        or "akan ot" in teks
    ):
        return "peluang_laga"

    if (
        ("kenapa" in teks and "total" in teks)
        or (
            "dari mana" in teks
            and any(kata in teks for kata in ("total", "proyeksi", "angka"))
        )
        or "komponen" in teks
        or (
            "kenapa" in teks
            and any(kata in teks for kata in ("proyeksi", "median", "angkanya"))
        )
        or "rincian total" in teks
        or "penjelasan total" in teks
    ):
        return "kenapa_total"

    return "unknown"


def _jawab_unknown(pertanyaan: str) -> dict:
    """Jawaban jujur untuk pertanyaan yang tidak dikenali."""
    daftar = "\n".join(
        f"- {item['contoh']} ({item['keterangan']})" for item in SUPPORTED_QUESTIONS
    )
    jawaban = (
        "Maaf, saya tidak mengerti pertanyaan itu. Saya bisa menjawab "
        "pertanyaan seperti ini:\n"
        f"{daftar}"
    )
    return _hasil(pertanyaan, "unknown", jawaban, {}, True)


def _bobot_resensi(cfg: dict, ringkasan: dict) -> tuple[float, float] | None:
    """Bobot resensi (musim, last10) ternormalisasi, atau None bila tak ada."""
    try:
        w_musim = _angka(
            config_mod.get_value(cfg, "simulation", "nba", "recency", "season")
        )
        w_terakhir = _angka(
            config_mod.get_value(cfg, "simulation", "nba", "recency", "last10")
        )
    except Exception:  # noqa: BLE001 - kunci hilang -> coba ringkasan sim
        w_musim = w_terakhir = None
    if w_musim is None or w_terakhir is None:
        bobot = ringkasan.get("recency_weights") or {}
        if isinstance(bobot, dict):
            w_musim = _angka(bobot.get("season"))
            w_terakhir = _angka(bobot.get("last10"))
    if w_musim is None or w_terakhir is None:
        return None
    total = w_musim + w_terakhir
    if total <= 0:
        return None
    return w_musim / total, w_terakhir / total


def _jawab_kenapa_total(pertanyaan: str, analysis: dict, cfg: dict) -> dict:
    """Uraikan komponen proyeksi total dari sim + inputs artefak."""
    sim = _simulasi(analysis)
    inputs = _inputs(analysis)
    dist = _dist_total(analysis)
    ringkasan = _ringkasan_inputs(analysis)
    median = _angka(dist.get("median"))
    mean = _angka(dist.get("mean"))
    std = _angka(dist.get("std"))
    p74 = _angka(dist.get("p74"))
    proj_total = _angka(ringkasan.get("projected_total"))
    proj_home = _angka(ringkasan.get("projected_home_points"))
    proj_away = _angka(ringkasan.get("projected_away_points"))
    pace = _angka(ringkasan.get("pace_game"))
    lg_avg = _angka(ringkasan.get("league_avg_off_rtg"))
    iterasi = _angka(sim.get("iterations")) if sim is not None else None
    numbers: dict = {}
    if median is not None:
        numbers["median_total"] = median
    if mean is not None:
        numbers["mean_total"] = mean
    if std is not None:
        numbers["std_total"] = std
    if p74 is not None:
        numbers["p74_total"] = p74
    if proj_total is not None:
        numbers["projected_total"] = proj_total
    if proj_home is not None:
        numbers["projected_home_points"] = proj_home
    if proj_away is not None:
        numbers["projected_away_points"] = proj_away
    if pace is not None:
        numbers["pace_game"] = pace
    if lg_avg is not None:
        numbers["league_avg_off_rtg"] = lg_avg
    if iterasi is not None:
        numbers["iterations"] = iterasi

    if sim is None or (median is None and proj_total is None):
        jawaban = (
            "Saya tidak bisa menguraikan total untuk laga ini — hasil "
            "simulasinya tidak ada di analisis ini, jadi bagian itu "
            "tidak terverifikasi."
        )
        return _hasil(pertanyaan, "kenapa_total", jawaban, numbers, False)

    nama_laga = _nama_laga(analysis)
    home_tri = analysis.get("home_tricode") or "tuan rumah"
    away_tri = analysis.get("away_tricode") or "tamu"
    total_acuan = median if median is not None else proj_total
    assert total_acuan is not None
    iterasi_teks = _fmt_ribu(int(iterasi)) if iterasi is not None else "100.000"
    baris = [
        f"Model memperkirakan total sekitar {_fmt_poin(total_acuan)} poin "
        f"untuk {nama_laga}. Angka itu nilai tengah dari {iterasi_teks} "
        "simulasi — separuh simulasi menghasilkan total di bawah angka "
        "itu, separuhnya di atas."
    ]
    verified = True

    if proj_home is not None and proj_away is not None:
        baris.append(
            f"- {home_tri} diperkirakan mencetak {_fmt_poin(proj_home)} poin, "
            f"{away_tri} {_fmt_poin(proj_away)} poin."
        )
    if pace is not None:
        baris.append(
            f"- Kecepatan main gabungan kedua tim (pace) sekitar " f"{_fmt_poin(pace)}."
        )

    # Rating gabungan + rata-rata dasar: hitung ulang dari inputs
    # dengan fungsi engine (nba_sim._combined_stats + project_points).
    bobot = _bobot_resensi(cfg, ringkasan)
    if inputs is not None and bobot is not None:
        w_musim, w_terakhir = bobot
        try:
            catatan: list[str] = []
            stat_home = nba_sim_mod._combined_stats(
                inputs.get("home") or {}, w_musim, w_terakhir, str(home_tri), catatan
            )
            stat_away = nba_sim_mod._combined_stats(
                inputs.get("away") or {}, w_musim, w_terakhir, str(away_tri), catatan
            )
            lg = lg_avg
            if lg is None:
                lg = (
                    stat_home["off_rtg"]
                    + stat_home["def_rtg"]
                    + stat_away["off_rtg"]
                    + stat_away["def_rtg"]
                ) / 4.0
            mu_home, mu_away, _pace = nba_sim_mod.project_points(
                stat_home, stat_away, lg
            )
            numbers["home_off_rtg"] = round(stat_home["off_rtg"], 2)
            numbers["home_def_rtg"] = round(stat_home["def_rtg"], 2)
            numbers["away_off_rtg"] = round(stat_away["off_rtg"], 2)
            numbers["away_def_rtg"] = round(stat_away["def_rtg"], 2)
            numbers["base_home_points"] = round(mu_home, 2)
            numbers["base_away_points"] = round(mu_away, 2)
            baris.append(
                f"- Rating serangan gabungan: {home_tri} "
                f"{_fmt_poin(stat_home['off_rtg'])}, {away_tri} "
                f"{_fmt_poin(stat_away['off_rtg'])}; rating pertahanan "
                f"gabungan: {home_tri} {_fmt_poin(stat_home['def_rtg'])}, "
                f"{away_tri} {_fmt_poin(stat_away['def_rtg'])}. "
                f"Rata-rata liga {_fmt_poin(lg)}. Dari rating itu saja, "
                f"rata-rata dasarnya {home_tri} {_fmt_poin(mu_home)} poin "
                f"dan {away_tri} {_fmt_poin(mu_away)} poin."
            )
        except (ValueError, KeyError, TypeError):
            verified = False
            baris.append(
                "- Rating tim tidak bisa dihitung ulang dari data ini — "
                "bagian itu tidak terverifikasi."
            )
    else:
        verified = False
        baris.append(
            "- Rincian rating tim tidak terverifikasi karena data input "
            "tidak ada di analisis ini."
        )

    # Keuntungan kandang (hanya menggeser selisih, total tidak berubah).
    home_adv = _angka(ringkasan.get("home_advantage_points"))
    if home_adv is None:
        home_adv = _ambang(cfg, 0.0, "simulation", "nba", "home_advantage_points")
        if home_adv == 0.0:
            home_adv = None
    if home_adv is not None:
        numbers["home_advantage_points"] = home_adv
        baris.append(
            f"- Keuntungan kandang {_fmt_poin(home_adv)} poin hanya "
            "menggeser selisih skor, tidak mengubah total."
        )

    # Back-to-back.
    b2b = ringkasan.get("back_to_back") or {}
    b2b_home = bool(b2b.get("home")) if isinstance(b2b, dict) else False
    b2b_away = bool(b2b.get("away")) if isinstance(b2b, dict) else False
    penalti_b2b = _angka(b2b.get("penalty_points")) if isinstance(b2b, dict) else None
    if penalti_b2b is None:
        penalti_b2b = _ambang(
            cfg, 0.0, "simulation", "nba", "back_to_back_penalty_points"
        )
        if penalti_b2b == 0.0:
            penalti_b2b = None
    if b2b_home or b2b_away:
        numbers["b2b_home"] = 1.0 if b2b_home else 0.0
        numbers["b2b_away"] = 1.0 if b2b_away else 0.0
        if penalti_b2b is not None:
            numbers["b2b_penalty_points"] = penalti_b2b
        tim_b2b = []
        if b2b_home:
            tim_b2b.append(str(home_tri))
        if b2b_away:
            tim_b2b.append(str(away_tri))
        potongan = (
            f"sebesar {_fmt_poin(abs(penalti_b2b))} poin per tim"
            if penalti_b2b is not None
            else "dengan besar potongan tidak terverifikasi"
        )
        if penalti_b2b is None:
            verified = False
        baris.append(
            f"- {' dan '.join(tim_b2b)} main dua malam berturut-turut, "
            f"jadi perkiraannya dipotong {potongan}."
        )
    else:
        baris.append(
            "- Tidak ada tim yang main dua malam berturut-turut, jadi "
            "tidak ada potongan back-to-back."
        )

    # Dampak pemain absen (dihitung ulang dengan rumus sim).
    absen = ringkasan.get("base_absent_players") or []
    dampak_total = 0.0
    dampak_per_pemain: dict[str, float] = {}
    if inputs is not None and bobot is not None and absen:
        bpm_scale = _angka(ringkasan.get("bpm_scale"))
        if bpm_scale is None:
            bpm_scale = _ambang(cfg, 1.0, "simulation", "nba", "bpm_scale")
        bpm_rep = _angka(ringkasan.get("bpm_replacement"))
        if bpm_rep is None:
            bpm_rep = _ambang(cfg, -2.0, "simulation", "nba", "bpm_replacement")
        peta_pemain: dict[str, dict] = {}
        for kunci in ("home", "away"):
            blok = inputs.get(kunci) or {}
            if not isinstance(blok, dict):
                continue
            for entri in blok.get("players") or []:
                if isinstance(entri, dict) and isinstance(entri.get("player"), str):
                    peta_pemain[entri["player"]] = entri
        for nama in absen:
            data_pemain = peta_pemain.get(nama)
            if data_pemain is None:
                continue
            dampak, _catatan = nba_sim_mod._dampak_pemain(
                data_pemain, bpm_scale, bpm_rep, bobot[1]
            )
            dampak_per_pemain[nama] = round(dampak, 2)
            dampak_total += dampak
        numbers["absent_impacts"] = dampak_per_pemain
        numbers["absent_total_points"] = round(dampak_total, 2)
        if dampak_per_pemain:
            rincian = ", ".join(
                f"{nama} {_fmt_poin(nilai)} poin"
                for nama, nilai in sorted(
                    dampak_per_pemain.items(), key=lambda item: -item[1]
                )
            )
            baris.append(
                f"- Pemain absen mengurangi total {_fmt_poin(dampak_total)} "
                f"poin: {rincian}."
            )
        else:
            baris.append(
                "- Ada pemain absen, tapi dampaknya tidak bisa dihitung "
                "karena data pemainnya tidak ada — bagian itu tidak "
                "terverifikasi."
            )
            verified = False
    elif absen:
        verified = False
        baris.append(
            "- Dampak pemain absen tidak terverifikasi karena data input "
            "tidak ada di analisis ini."
        )
    else:
        baris.append("- Tidak ada pemain inti yang absen.")

    if std is not None:
        baris.append(
            f"Sebaran simulasi: total biasanya bergerak sekitar "
            f"{_fmt_poin(std)} poin di atas atau di bawah rata-rata."
        )
    if p74 is not None:
        baris.append(
            f"Dalam 74 dari 100 simulasi, totalnya di bawah " f"{_fmt_poin(p74)} poin."
        )
    return _hasil(pertanyaan, "kenapa_total", "\n".join(baris), numbers, verified)


def _jawab_bagaimana_jika_absen(
    pertanyaan: str, analysis: dict, cfg: dict, iterations: int | None
) -> dict:
    """Sim ulang dengan satu pemain tambahan absen; bandingkan hasilnya."""
    info = _cari_pemain(pertanyaan, analysis)
    if info is None:
        jawaban = (
            "Saya tidak menemukan pemain yang dimaksud di data laga ini — "
            "mungkin namanya salah ketik. Coba sebut nama lengkap pemainnya, "
            "misalnya seperti yang tertulis di daftar cedera. Bagian ini "
            "tidak terverifikasi."
        )
        return _hasil(pertanyaan, "bagaimana_jika_absen", jawaban, {}, False)
    nama = info["nama"]
    inputs = _inputs(analysis)
    sim = _simulasi(analysis)
    if inputs is None or sim is None:
        jawaban = (
            f"Saya tidak bisa menghitung apa jadinya kalau {nama} absen — "
            "data input dan simulasinya tidak ada di analisis ini, jadi "
            "bagian itu tidak terverifikasi."
        )
        return _hasil(pertanyaan, "bagaimana_jika_absen", jawaban, {}, False)

    status = _status_pemain(analysis, nama)
    dist = _dist_total(analysis)
    median_asli = _angka(dist.get("median"))
    numbers: dict = {}
    if median_asli is not None:
        numbers["median_total_asli"] = median_asli

    if status == "OUT":
        # Pemain sudah dihitung absen di analisis awal — tidak ada
        # yang berubah; tidak perlu sim ulang.
        numbers["sudah_absen"] = 1.0
        jawaban = (
            f"{nama} sudah dihitung absen di analisis ini, jadi tidak ada "
            "yang berubah — perkiraannya sudah memperhitungkan "
            "ketidakhadirannya."
        )
        if median_asli is not None:
            jawaban += f" Nilai tengah total tetap {_fmt_poin(median_asli)} poin."
        return _hasil(pertanyaan, "bagaimana_jika_absen", jawaban, numbers, True)

    n_iter = iterations if iterations is not None else RESIM_ITERATIONS
    seed = None
    engine = sim.get("engine") or {}
    if isinstance(engine, dict) and isinstance(engine.get("seed"), int):
        seed = engine["seed"]
    if seed is None:
        seed = _RESIM_SEED_DEFAULT
    garis_sim = sorted(
        {
            leg["line"]
            for leg in _kaki(analysis)
            if leg.get("meets") and _angka(leg.get("line")) is not None
        }
        | ({median_asli} if median_asli is not None else set())
    )
    lines = {"totals": garis_sim} if garis_sim else None

    inputs_skenario = copy.deepcopy(inputs)
    kunci_tim = info["tim"]
    blok = inputs_skenario.get(kunci_tim) or {}
    cedera = list(blok.get("injuries") or [])
    diganti = False
    for entri in cedera:
        if isinstance(entri, dict) and entri.get("player") == nama:
            entri["status"] = "OUT"
            diganti = True
    if not diganti:
        cedera.append(
            {
                "player": nama,
                "status": "OUT",
                "team_tricode": info["tricode"],
                "sources": [],
            }
        )
    blok["injuries"] = cedera
    inputs_skenario[kunci_tim] = blok

    try:
        sim_dasar = nba_sim_mod.simulate(
            inputs, cfg=cfg, lines=lines, scenarios=[], seed=seed, iterations=n_iter
        )
        sim_baru = nba_sim_mod.simulate(
            inputs_skenario,
            cfg=cfg,
            lines=lines,
            scenarios=[],
            seed=seed,
            iterations=n_iter,
        )
    except Exception:  # noqa: BLE001 - sim gagal -> jawaban fail-closed
        jawaban = (
            f"Saya tidak bisa menghitung apa jadinya kalau {nama} absen — "
            "sim ulangnya gagal, jadi bagian itu tidak terverifikasi."
        )
        return _hasil(pertanyaan, "bagaimana_jika_absen", jawaban, numbers, False)

    def _median(sim_hasil: dict) -> float | None:
        total = (sim_hasil.get("score_distribution") or {}).get("total") or {}
        return _angka(total.get("median"))

    def _mean(sim_hasil: dict) -> float | None:
        total = (sim_hasil.get("score_distribution") or {}).get("total") or {}
        return _angka(total.get("mean"))

    median_dasar = _median(sim_dasar)
    median_baru = _median(sim_baru)
    mean_dasar = _mean(sim_dasar)
    mean_baru = _mean(sim_baru)
    ml_dasar = _peluang((sim_dasar.get("markets") or {}).get("moneyline_home"))
    ml_baru = _peluang((sim_baru.get("markets") or {}).get("moneyline_home"))
    if median_dasar is None or median_baru is None:
        jawaban = (
            f"Saya tidak bisa menghitung apa jadinya kalau {nama} absen — "
            "sim ulangnya tidak menghasilkan nilai tengah, jadi bagian "
            "itu tidak terverifikasi."
        )
        return _hasil(pertanyaan, "bagaimana_jika_absen", jawaban, numbers, False)

    numbers["resim_iterations"] = float(n_iter)
    numbers["resim_seed"] = float(seed)
    numbers["median_dasar"] = median_dasar
    numbers["median_baru"] = median_baru
    numbers["delta_median_points"] = round(median_baru - median_dasar, 2)
    if mean_dasar is not None and mean_baru is not None:
        numbers["mean_dasar"] = mean_dasar
        numbers["mean_baru"] = mean_baru
        numbers["delta_mean_points"] = round(mean_baru - mean_dasar, 2)
    if ml_dasar is not None and ml_baru is not None:
        numbers["moneyline_home_dasar"] = ml_dasar
        numbers["moneyline_home_baru"] = ml_baru
        numbers["delta_moneyline_home_points"] = round((ml_baru - ml_dasar) * 100.0, 2)

    delta = median_baru - median_dasar
    arah = "turun" if delta < 0 else ("naik" if delta > 0 else "tetap")
    kalimat = [
        f"Kalau {nama} absen, saya sim ulang laganya {_fmt_ribu(n_iter)} "
        f"kali dengan {nama} tidak main. Hasil sim ulangnya: nilai tengah "
        f"total {arah} dari {_fmt_poin(median_dasar)} menjadi "
        f"{_fmt_poin(median_baru)} poin"
    ]
    if delta != 0:
        kalimat[0] += f" ({arah} {_fmt_poin(abs(delta))} poin)"
    kalimat[0] += "."
    if ml_dasar is not None and ml_baru is not None:
        home_tri = analysis.get("home_tricode") or "tuan rumah"
        kalimat.append(
            f"Peluang {home_tri} menang berubah dari {_fmt_persen(ml_dasar)} "
            f"menjadi {_fmt_persen(ml_baru)}."
        )
    for garis in garis_sim:
        if median_asli is not None and garis == median_asli:
            continue
        kunci = f"total_under_{garis:g}"
        p_dasar = _peluang((sim_dasar.get("markets") or {}).get(kunci))
        p_baru = _peluang((sim_baru.get("markets") or {}).get(kunci))
        if p_dasar is not None and p_baru is not None:
            numbers[f"p_under_{garis:g}_dasar"] = p_dasar
            numbers[f"p_under_{garis:g}_baru"] = p_baru
            numbers[f"delta_p_under_{garis:g}_points"] = round(
                (p_baru - p_dasar) * 100.0, 2
            )
            kalimat.append(
                f"Peluang total di bawah {_fmt_poin(garis)} berubah dari "
                f"{_fmt_persen(p_dasar)} menjadi {_fmt_persen(p_baru)}."
            )
    if median_asli is not None:
        iterasi_asli = _angka(sim.get("iterations"))
        iterasi_teks = (
            _fmt_ribu(int(iterasi_asli)) if iterasi_asli is not None else "100.000"
        )
        kalimat.append(
            "Sebagai perbandingan, nilai tengah total di analisis awal "
            f"({iterasi_teks} simulasi) adalah {_fmt_poin(median_asli)} poin."
        )
    return _hasil(pertanyaan, "bagaimana_jika_absen", " ".join(kalimat), numbers, True)


def _harga_kaki(leg: dict) -> float | None:
    """Harga kaki yang dipakai jawaban: estimasi jup.ag bila ada, else Polymarket."""
    harga = _angka(leg.get("jup_estimated_cents"))
    if harga is None:
        harga = _angka(leg.get("price_cents"))
    return harga


def _jawab_garis_teraman(pertanyaan: str, analysis: dict) -> dict:
    """Bandingkan garis Asuransi/Utama; rekomendasikan peluang tertinggi."""
    legs = _kaki(analysis)
    if not legs:
        jawaban = (
            "Saya tidak bisa merekomendasikan garis — daftar garis tidak "
            "ada di analisis ini, jadi bagian itu tidak terverifikasi."
        )
        return _hasil(pertanyaan, "garis_teraman", jawaban, {}, False)
    numbers: dict = {}
    for leg in legs:
        ticket = leg.get("ticket")
        if ticket not in ("insurance", "main"):
            continue
        for kunci, nilai in (
            ("line", _angka(leg.get("line"))),
            ("p_model", _peluang(leg.get("p_model"))),
            ("p_market", _peluang(leg.get("p_market"))),
            ("p_final", _peluang(leg.get("p_final"))),
            ("price_cents", _harga_kaki(leg)),
            ("ev_pct", _angka(leg.get("ev_pct"))),
            (
                "cushion_vs_median_points",
                _angka(leg.get("cushion_vs_median_points")),
            ),
            (
                "cushion_vs_market_points",
                _angka(leg.get("cushion_vs_market_points")),
            ),
        ):
            if nilai is not None:
                numbers[f"{kunci}_{ticket}"] = nilai
    memenuhi = [
        leg for leg in legs if leg.get("meets") and _angka(leg.get("line")) is not None
    ]
    if not memenuhi:
        rincian = []
        for leg in legs:
            label = _LABEL_TIKET.get(leg.get("ticket"), str(leg.get("ticket")))
            alasan = leg.get("reason")
            kata = _ALASAN_KAKI.get(alasan, alasan) if isinstance(alasan, str) else None
            rincian.append(
                f"{label}: {kata}"
                if kata
                else f"{label}: tidak memenuhi syarat (alasan tidak tercatat)"
            )
        jawaban = (
            "Tidak ada garis yang memenuhi syarat di analisis ini, jadi "
            "saya tidak bisa merekomendasikan garis. Rinciannya: "
            + "; ".join(rincian)
            + "."
        )
        return _hasil(pertanyaan, "garis_teraman", jawaban, numbers, True)

    def _skor(leg: dict) -> float:
        p_final = _peluang(leg.get("p_final"))
        if p_final is not None:
            return p_final
        p_model = _peluang(leg.get("p_model"))
        return p_model if p_model is not None else -1.0

    memenuhi_urut = sorted(memenuhi, key=_skor, reverse=True)
    pilihan = memenuhi_urut[0]
    garis_pilihan = _angka(pilihan.get("line"))
    assert garis_pilihan is not None
    label_pilihan = _LABEL_TIKET.get(pilihan.get("ticket"), str(pilihan.get("ticket")))
    numbers["recommended_line"] = garis_pilihan
    if _skor(pilihan) >= 0:
        numbers["recommended_p_final"] = _skor(pilihan)
    verified = _peluang(pilihan.get("p_model")) is not None
    kalimat = [
        f"Dari garis yang memenuhi syarat, yang paling aman adalah Under "
        f"{_fmt_poin(garis_pilihan)} (Tiket {label_pilihan})."
    ]
    for leg in memenuhi_urut:
        garis = _angka(leg.get("line"))
        label = _LABEL_TIKET.get(leg.get("ticket"), str(leg.get("ticket")))
        p_model = _peluang(leg.get("p_model"))
        p_market = _peluang(leg.get("p_market"))
        p_final = _peluang(leg.get("p_final"))
        harga = _harga_kaki(leg)
        label_harga = leg.get("price_label")
        bantalan_median = _angka(leg.get("cushion_vs_median_points"))
        bantalan_market = _angka(leg.get("cushion_vs_market_points"))
        bagian = [f"Under {_fmt_poin(garis)} ({label})"]
        if p_model is not None:
            bagian.append(f"peluang menurut model {_fmt_persen(p_model)}")
        if p_market is not None:
            sumber = leg.get("comparison_source") or "pembanding"
            bagian.append(f"menurut {sumber} {_fmt_persen(p_market)}")
        if p_final is not None:
            bagian.append(f"gabungannya {_fmt_persen(p_final)}")
        if bantalan_median is not None:
            bagian.append(
                f"{_fmt_poin(bantalan_median)} poin di atas perkiraan tengah model"
            )
        if bantalan_market is not None:
            bagian.append(f"{_fmt_poin(bantalan_market)} poin di atas garis market")
        if harga is not None:
            bagian.append(f"harganya {_fmt_sen(harga)}")
        if isinstance(label_harga, str) and label_harga:
            bagian.append(f"labelnya {label_harga}")
        kalimat.append("- " + ", ".join(bagian) + ".")
    if pilihan.get("p_market") is None:
        kalimat.append(
            "Catatan: garis yang saya rekomendasikan tidak punya harga "
            "pembanding (MODEL_ONLY), jadi peluangnya hanya dari model."
        )
    if pilihan.get("price_label") == "MAHAL":
        kalimat.append(
            "Catatan: garis ini berlabel MAHAL — harganya mahal dibanding "
            "peluangnya."
        )
    if not verified:
        kalimat.append(
            "Peluang model garis yang direkomendasikan tidak tersedia — "
            "bagian itu tidak terverifikasi."
        )
    return _hasil(pertanyaan, "garis_teraman", "\n".join(kalimat), numbers, verified)


def _kalimat_pemain_cedera(entri: dict, dikonfirmasi: set[str]) -> str:
    """Satu kalimat kabar pemain dari entri cedera gabungan."""
    nama = entri.get("player") or "pemain tidak dikenal"
    status = str(entri.get("status") or "").upper()
    kata_status = _STATUS_KATA.get(
        status, status.lower() if status else "tidak diketahui"
    )
    tricode = entri.get("team_tricode")
    alasan = entri.get("reason")
    sumber = entri.get("sources") or []
    n_sumber = len(sumber) if isinstance(sumber, list) else 0
    bagian = [str(nama)]
    if isinstance(tricode, str) and tricode:
        bagian[0] += f" ({tricode})"
    bagian.append(f"statusnya {kata_status}")
    if isinstance(alasan, str) and alasan.strip():
        bagian.append(f"alasan: {alasan.strip()}")
    else:
        bagian.append("alasan tidak tercatat di data ini")
    if n_sumber:
        nama_sumber = ", ".join(s for s in sumber if isinstance(s, str))
        bagian.append(
            f"dari {n_sumber} sumber" + (f" ({nama_sumber})" if nama_sumber else "")
        )
    else:
        bagian.append("jumlah sumber tidak tercatat")
    if nama in dikonfirmasi:
        bagian.append("dikonsfirmasi kedua sumber")
    return ", ".join(bagian)


def _jawab_kabar_pemain(pertanyaan: str, analysis: dict) -> dict:
    """Kabar cedera: daftar diragukan/absen, atau satu pemain spesifik."""
    injuries = analysis.get("injuries") if isinstance(analysis, dict) else None
    if not isinstance(injuries, dict):
        jawaban = (
            "Saya tidak bisa menjawab kabar pemain — data cedera tidak "
            "ada di analisis ini, jadi bagian itu tidak terverifikasi."
        )
        return _hasil(pertanyaan, "kabar_pemain", jawaban, {}, False)
    entri = _entri_cedera(analysis)
    dikonfirmasi = set(injuries.get("confirmed_both") or [])
    n_sumber = injuries.get("n_sources")
    numbers: dict = {}
    if isinstance(n_sumber, int) and not isinstance(n_sumber, bool):
        numbers["n_sumber_cedera"] = float(n_sumber)
    out = [e for e in entri if str(e.get("status") or "").upper() == "OUT"]
    ragu = [
        e
        for e in entri
        if str(e.get("status") or "").upper() in ("QUESTIONABLE", "DOUBTFUL")
    ]
    numbers["n_pasti_absen"] = float(len(out))
    numbers["n_diragukan"] = float(len(ragu))

    info = _cari_pemain(pertanyaan, analysis)
    if info is not None:
        nama = info["nama"]
        entri_pemain = next((e for e in entri if e.get("player") == nama), None)
        if entri_pemain is None:
            jawaban = (
                f"Tidak ada kabar cedera untuk {nama} — menurut data di "
                "analisis ini, pemain itu tersedia."
            )
            return _hasil(pertanyaan, "kabar_pemain", jawaban, numbers, True)
        sumber = entri_pemain.get("sources") or []
        if isinstance(sumber, list):
            numbers["player_n_sources"] = float(len(sumber))
        jawaban = "Kabar " + _kalimat_pemain_cedera(entri_pemain, dikonfirmasi) + "."
        return _hasil(pertanyaan, "kabar_pemain", jawaban, numbers, True)

    # Pertanyaan menyebut nama tapi tidak ditemukan di data.
    teks = pertanyaan.lower()
    if "kabar" in teks or "status" in teks or "apakah" in teks:
        jawaban = (
            "Saya tidak menemukan pemain yang dimaksud di data laga ini — "
            "mungkin namanya salah ketik. Bagian ini tidak terverifikasi."
        )
        return _hasil(pertanyaan, "kabar_pemain", jawaban, numbers, False)

    if not entri:
        jawaban = (
            "Tidak ada kabar cedera yang tercatat di analisis ini — "
            "menurut data ini, tidak ada pemain yang absen atau diragukan."
        )
        if isinstance(n_sumber, int):
            jawaban += f" Data cedera ini dari {n_sumber} sumber."
        return _hasil(pertanyaan, "kabar_pemain", jawaban, numbers, True)
    kalimat = []
    if ragu:
        kalimat.append("Yang diragukan tampil:")
        kalimat.extend(
            "- " + _kalimat_pemain_cedera(e, dikonfirmasi) + "." for e in ragu
        )
    else:
        kalimat.append("Tidak ada pemain yang diragukan tampil.")
    if out:
        kalimat.append("Yang sudah pasti absen:")
        kalimat.extend(
            "- " + _kalimat_pemain_cedera(e, dikonfirmasi) + "." for e in out
        )
    else:
        kalimat.append("Tidak ada pemain yang sudah pasti absen.")
    return _hasil(pertanyaan, "kabar_pemain", "\n".join(kalimat), numbers, True)


def _jawab_kenapa_beda(pertanyaan: str, analysis: dict, cfg: dict) -> dict:
    """Selisih model vs market + kesimpulan "Kenapa beda?" dari data artefak."""
    dist = _dist_total(analysis)
    median = _angka(dist.get("median"))
    market = analysis.get("market") if isinstance(analysis, dict) else None
    garis_market = None
    if isinstance(market, dict):
        garis_market = _angka(market.get("main_total_line"))
    ambang_gap = _ambang(cfg, 5.0, "market_line_check", "total_gap_points")
    ambang_diff = _ambang(cfg, 8.0, "anomaly", "model_vs_market_points")
    numbers: dict = {
        "ambang_gap_points": ambang_gap,
        "ambang_model_vs_market_points": ambang_diff,
    }
    if median is not None:
        numbers["median_total"] = median
    if garis_market is not None:
        numbers["market_total_line"] = garis_market
    if median is None or garis_market is None:
        jawaban = (
            "Saya tidak bisa menjawab kenapa model dan market beda — "
            "nilai tengah model atau garis market tidak ada di analisis "
            "ini, jadi selisihnya tidak terverifikasi."
        )
        return _hasil(pertanyaan, "kenapa_beda_model_market", jawaban, numbers, False)

    gap = round(garis_market - median, 2)
    numbers["gap_points"] = gap
    anomalies = analysis.get("anomalies") if isinstance(analysis, dict) else None
    daftar_anomali = (
        [a for a in anomalies if isinstance(a, dict)]
        if isinstance(anomalies, list)
        else []
    )
    tipe_anomali = [a.get("type") for a in daftar_anomali]
    arah = (
        "market mengharapkan total lebih tinggi dari model"
        if gap > 0
        else (
            "model mengharapkan total lebih tinggi dari market"
            if gap < 0
            else "model dan market memasang angka yang sama"
        )
    )
    kalimat = [
        f"Nilai tengah model {_fmt_poin(median)} poin, garis market "
        f"{_fmt_poin(garis_market)} poin — selisih {_fmt_poin(abs(gap))} "
        f"poin, {arah}."
    ]
    # Selisih peluang per kaki.
    diff_terbesar = 0.0
    for leg in _kaki(analysis):
        p_model = _peluang(leg.get("p_model"))
        p_market = _peluang(leg.get("p_market"))
        if p_model is None or p_market is None:
            continue
        diff = round(abs(p_model - p_market) * 100.0, 2)
        diff_terbesar = max(diff_terbesar, diff)
        label = _LABEL_TIKET.get(leg.get("ticket"), str(leg.get("ticket")))
        garis = _angka(leg.get("line"))
        ticket = leg.get("ticket")
        if ticket in ("insurance", "main"):
            numbers[f"diff_points_{ticket}"] = diff
            numbers[f"p_model_{ticket}"] = p_model
            numbers[f"p_market_{ticket}"] = p_market
        kalimat.append(
            f"Untuk garis Under {_fmt_poin(garis) if garis is not None else '?'} "
            f"({label}): peluang model {_fmt_persen(p_model)}, peluang "
            f"pembanding {_fmt_persen(p_market)} — selisih "
            f"{_fmt_poin(diff)} poin."
        )
    numbers["diff_terbesar_points"] = diff_terbesar

    gap_besar = abs(gap) > ambang_gap
    diff_besar = diff_terbesar > ambang_diff
    if not gap_besar and not diff_besar:
        kalimat.append(
            f"Selisih ini masih di bawah ambang ({_fmt_poin(ambang_gap)} poin "
            f"untuk total, {_fmt_poin(ambang_diff)} poin untuk peluang per "
            "kaki), jadi model dan market tidak jauh berbeda — tidak ada "
            '"Kenapa beda?" yang perlu dijawab.'
        )
        return _hasil(
            pertanyaan, "kenapa_beda_model_market", " ".join(kalimat), numbers, True
        )

    kalimat.append(
        f"Selisih ini melewati ambang ({_fmt_poin(ambang_gap)} poin untuk "
        f"total, {_fmt_poin(ambang_diff)} poin untuk peluang per kaki), "
        'jadi aturan "Kenapa beda?" berlaku.'
    )
    if "total_line_vs_model" in tipe_anomali:
        kalimat.append(
            "Analisis ini mencatat anomali selisih garis total model vs market."
        )
    if "model_vs_market" in tipe_anomali:
        kalimat.append(
            "Analisis ini mencatat anomali selisih peluang model vs pembanding."
        )
    if "cushion_tidak_dikonfirmasi_market" in tipe_anomali:
        kalimat.append(
            "Analisis ini mencatat anomali bantalan tidak dikonfirmasi market: "
            "bantalan cukup menurut model tapi tidak menurut garis market."
        )

    # Kelemahan data yang tercatat (kesimpulan (b) bila ada).
    kelemahan: list[str] = []
    status = analysis.get("status")
    if status in ("HOLD", "DATA_INCOMPLETE"):
        kelemahan.append(f"status analisis {status}")
    injuries = analysis.get("injuries") if isinstance(analysis, dict) else None
    if (
        isinstance(injuries, dict)
        and isinstance(injuries.get("n_sources"), int)
        and injuries["n_sources"] < 2
    ):
        kelemahan.append("data cedera hanya dari 1 sumber")
    model_only = [
        _LABEL_TIKET.get(leg.get("ticket"), str(leg.get("ticket")))
        for leg in _kaki(analysis)
        if leg.get("meets") and leg.get("p_market") is None
    ]
    if model_only:
        kelemahan.append("kaki " + " dan ".join(model_only) + " tanpa harga pembanding")
    if kelemahan:
        kalimat.append(
            "Kesimpulan dari data di analisis ini: model kemungkinan "
            "kurang data — " + "; ".join(kelemahan) + "."
        )
    else:
        kalimat.append(
            "Saya memeriksa data di analisis ini dan tidak menemukan "
            "alasan konkret untuk selisih ini — kesimpulannya: tidak "
            "ditemukan alasan. Kemungkinan market tahu sesuatu yang "
            "belum masuk model tidak bisa dipastikan dari analisis ini "
            "saja; untuk memeriksa kabar cedera terbaru dan pergerakan "
            "harga, jalankan recheck sebelum memasang."
        )
    if gap_besar:
        kalimat.append(
            "Catatan aturan condong-ke-market: selama selisihnya di atas "
            f"{_fmt_poin(ambang_gap)} poin tanpa alasan konkret, kaki "
            "Asuransi memakai peluang market, bukan model."
        )
    return _hasil(
        pertanyaan, "kenapa_beda_model_market", " ".join(kalimat), numbers, True
    )


def _jawab_peluang_laga(pertanyaan: str, analysis: dict) -> dict:
    """Peluang OT dan peluang menang kandang/tandang dari simulasi."""
    sim = _simulasi(analysis)
    if sim is None:
        jawaban = (
            "Saya tidak bisa menjawab peluang laga ini — hasil simulasinya "
            "tidak ada di analisis ini, jadi bagian itu tidak terverifikasi."
        )
        return _hasil(pertanyaan, "peluang_laga", jawaban, {}, False)
    dist = (sim.get("score_distribution") or {}).get("ot_probability")
    ot = _peluang(dist)
    markets = sim.get("markets") or {}
    ml_home = (
        _peluang(markets.get("moneyline_home")) if isinstance(markets, dict) else None
    )
    ml_away = (
        _peluang(markets.get("moneyline_away")) if isinstance(markets, dict) else None
    )
    ringkasan = _ringkasan_inputs(analysis)
    margin = _angka(ringkasan.get("projected_margin"))
    numbers: dict = {}
    if ot is not None:
        numbers["ot_probability"] = ot
    if ml_home is not None:
        numbers["moneyline_home"] = ml_home
    if ml_away is not None:
        numbers["moneyline_away"] = ml_away
    if margin is not None:
        numbers["projected_margin"] = margin
    teks = pertanyaan.lower()
    mau_ot = _kata_utuh(teks, "ot") or any(
        kata in teks for kata in ("overtime", "perpanjangan")
    )
    mau_menang = any(kata in teks for kata in ("menang", "kandang", "tandang"))
    if not mau_ot and not mau_menang:
        mau_ot = mau_menang = True
    home_tri = analysis.get("home_tricode") or "tuan rumah"
    away_tri = analysis.get("away_tricode") or "tamu"
    kalimat: list[str] = []
    verified = True
    if mau_ot:
        if ot is None:
            verified = False
            kalimat.append(
                "Peluang perpanjangan waktu tidak terverifikasi — angkanya "
                "tidak ada di analisis ini."
            )
        else:
            per_seratus = round(ot * 100.0, 1)
            kalimat.append(
                f"Peluang laga ini masuk perpanjangan waktu sekitar "
                f"{_fmt_persen(ot)} — kira-kira {_fmt_poin(per_seratus)} "
                "dari 100 simulasi berakhir seri setelah 48 menit."
            )
    if mau_menang:
        if ml_home is None or ml_away is None:
            verified = False
            kalimat.append(
                "Peluang menang tidak terverifikasi — angkanya tidak ada "
                "di analisis ini."
            )
        else:
            unggul = home_tri if ml_home >= ml_away else away_tri
            kalimat.append(
                f"{unggul} lebih dijagokan menang: {home_tri} "
                f"{_fmt_persen(ml_home)}, {away_tri} {_fmt_persen(ml_away)}."
            )
            if margin is not None:
                if margin > 0:
                    kalimat.append(
                        f"Selisih skor yang diperkirakan {_fmt_poin(margin)} "
                        f"poin untuk {home_tri}."
                    )
                elif margin < 0:
                    kalimat.append(
                        f"Selisih skor yang diperkirakan "
                        f"{_fmt_poin(abs(margin))} poin untuk {away_tri}."
                    )
                else:
                    kalimat.append("Selisih skor yang diperkirakan 0 poin.")
    return _hasil(pertanyaan, "peluang_laga", " ".join(kalimat), numbers, verified)


def answer(
    analysis: dict,
    question: str,
    config: dict | None = None,
    *,
    iterations: int | None = None,
) -> dict:
    """Jawab satu pertanyaan tentang artefak analisis NBA.

    analysis: artefak nba_analysis (format_version 1). question:
    pertanyaan user (Bahasa Indonesia). config: dict playstyle
    (None = baca playstyle.yaml; dipakai untuk ambang + sim ulang).
    iterations: jumlah iterasi sim ulang untuk intent
    bagaimana_jika_absen (None = RESIM_ITERATIONS = 20.000; tes
    memakai nilai kecil lewat argumen ini).

    Mengembalikan {"question", "intent", "answer", "numbers",
    "verified"}. "answer" teks Bahasa Indonesia sehari-hari tanpa
    jargon; "numbers" hanya angka dari artefak/kode/config;
    "verified" False bila ada bagian jawaban yang "tidak
    terverifikasi". Pertanyaan tak dikenal -> intent "unknown" +
    daftar pertanyaan yang didukung. Fungsi ini tidak pernah raise
    untuk artefak yang rusak — data hilang dijawab "tidak
    terverifikasi", bukan exception.
    """
    pertanyaan = question if isinstance(question, str) else ""
    artefak = analysis if isinstance(analysis, dict) else {}
    if not pertanyaan.strip():
        return _jawab_unknown(pertanyaan)
    intent = detect_intent(pertanyaan)
    if intent == "unknown":
        return _jawab_unknown(pertanyaan)
    cfg = _muat_cfg(config)
    if intent == "kenapa_total":
        return _jawab_kenapa_total(pertanyaan, artefak, cfg)
    if intent == "bagaimana_jika_absen":
        return _jawab_bagaimana_jika_absen(pertanyaan, artefak, cfg, iterations)
    if intent == "garis_teraman":
        return _jawab_garis_teraman(pertanyaan, artefak)
    if intent == "kabar_pemain":
        return _jawab_kabar_pemain(pertanyaan, artefak)
    if intent == "kenapa_beda_model_market":
        return _jawab_kenapa_beda(pertanyaan, artefak, cfg)
    if intent == "peluang_laga":
        return _jawab_peluang_laga(pertanyaan, artefak)
    return _jawab_unknown(pertanyaan)
