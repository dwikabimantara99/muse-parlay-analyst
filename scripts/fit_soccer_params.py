"""Fit parameter Dixon-Coles sepak bola dari data historis (D12).

Metode (didokumentasikan di sini + LAPORAN-FIT-BOLA.md):

  (a) MODEL — SAMA PERSIS dengan engine.football_sim (pekerja B):
      lam_kandang = attack_kandang x defence_tandang x avg_home_goals
      lam_tandang = attack_tandang x defence_kandang x avg_away_goals
      dengan koreksi korelasi Dixon-Coles tau():
        tau(0,0) = 1 - lam_kandang x lam_tandang x rho
        tau(1,0) = 1 + lam_tandang x rho
        tau(0,1) = 1 + lam_kandang x rho
        tau(1,1) = 1 - rho
        tau(x,y) = 1 untuk skor lainnya.
      attack/defence dinormalisasi rata-rata (aritmetik) 1 per
      liga-musim. Home advantage DILAPORKAN sebagai rasio
      avg_home_goals / avg_away_goals (bukan parameter bebas terpisah).
  (b) ESTIMASI. Maximum likelihood atas log-likelihood Dixon-Coles:
      sum_laga [x*log(lam_h) - lam_h - log(x!)
                + y*log(lam_a) - lam_a - log(y!) + log(tau(x,y))].
      Catatan: keempat suku koreksi tau MENJUMLAH NOL atas grid skor
      penuh (suku (0,0),(1,0),(0,1),(1,1) saling meniadakan persis),
      jadi likelihood ini adalah likelihood eksak dari distribusi
      yang dipakai mesin sim — satu-satunya selisih adalah pemotongan
      mesin di 10 gol per tim (ekor < 1e-4, diabaikan).
  (c) OPTIMASI (pure Python stdlib — tanpa numpy/scipy). Coordinate
      ascent atas log-attack / log-defence tiap tim (golden-section
      per koordinat, hanya laga yang melibatkan tim itu yang dihitung
      ulang) + pencarian grid rho atas laga skor-rendah saja. Setelah
      tiap sapuan, log-attack/log-defence di-centering (rata-rata
      geometrik 1) dengan avg goals dikalikan faktor yang sama —
      lambda TIDAK berubah oleh langkah ini (identifikasi skala).
      Di akhir, attack/defence dinormalisasi ke rata-rata ARITMETIK
      1 dengan avg goals dikoreksi faktor yang sama persis, jadi
      lambda tetap sama persis. Konvergen bila perbaikan loglik satu
      sapuan penuh < 1e-7 x (1 + |loglik|).
  (d) CAKUPAN FIT. Per liga: (i) fit per musim (satu rho + kekuatan
      per musim), (ii) fit GABUNGAN atas semua musim fit (satu rho
      bersama, kekuatan tim = satu entitas lintas musim — kekuatan
      "rata-rata 3 musim"), (iii) fit parsial musim berjalan untuk
      contoh live (label jelas "parsial").
  (e) DATA. Hanya kolom HASIL (FTHG/FTAG) dari CSV football-data.co.uk
      lokal di data/ (lihat ingest/football_data.py). Kolom odds
      Pinnacle TIDAK dipakai (stale sejak 23/07/2025).

Aturan D12: nilai fit DILAPORKAN untuk persetujuan user — skrip ini
TIDAK menulis ke config/playstyle.yaml (dixon_coles_rho dan
home_advantage_by_league tetap null sampai user menyetujui).

Jalankan dari root repo:
  python3 scripts/fit_soccer_params.py [--leagues EPL LaLiga]
      [--seasons 2223 2324 2425] [--live-season 2627]
      [--data-dir data] [--out out/fit_soccer_params.json]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import football_data

# Batas atas gol per tim dalam grid peluang — SAMA dengan
# engine.football_sim.MAX_GOL (konsistensi dengan mesin sim).
MAX_GOL = 10
# Rentang pencarian rho — SAMA dengan engine (RHO_MIN/RHO_MAX).
RHO_MIN = -0.5
RHO_MAX = 0.5
# Grid kasar rho + grid halus di sekitar titik terbaik.
RHO_GRID_MIN = -0.4
RHO_GRID_MAX = 0.4
RHO_GRID_STEP = 0.01
RHO_FINE_HALF = 0.01
RHO_FINE_STEP = 0.001
# Batas log-attack/log-defence (pengali dalam [e^-2.5, e^2.5] ~ [0,08, 12]).
LOG_PARAM_MIN = -2.5
LOG_PARAM_MAX = 2.5
# Lebar braket golden-section di sekitar nilai kini (skala log).
BRAKET_LOG = 1.5
# Iterasi golden-section per koordinat.
GOLDEN_ITER = 30
# Sapuan maksimum + toleransi konvergensi loglik.
MAX_SWEEPS = 30
TOL_LIK = 1e-7
# Laga minimum agar fit dijalankan (bukan ditebak dari data tipis).
MIN_MATCHES_FIT = 100

# Skor yang kena koreksi tau Dixon-Coles.
SKOR_TAU = frozenset({(0, 0), (1, 0), (0, 1), (1, 1)})


def tau_dc(x: int, y: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Koreksi Dixon-Coles tau(x, y) — rumus SAMA dengan engine.

    tau(0,0) = 1 - lam_h*lam_a*rho; tau(1,0) = 1 + lam_a*rho;
    tau(0,1) = 1 + lam_h*rho; tau(1,1) = 1 - rho; lainnya 1.
    """
    if x == 0 and y == 0:
        return 1.0 - lam_h * lam_a * rho
    if x == 1 and y == 0:
        return 1.0 + lam_a * rho
    if x == 0 and y == 1:
        return 1.0 + lam_h * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def probabilitas_laga(
    lam_h: float, lam_a: float, rho: float, max_gol: int = MAX_GOL
) -> dict:
    """Peluang 1X2 / O-U 2.5 / BTTS dari lambda Dixon-Coles.

    Grid Poisson x tau atas gol 0..max_gol per tim, dinormalisasi
    setelah pemotongan — cara yang SAMA dengan engine.football_sim.
    Raise ValueError bila ada tau <= 0 (parameter tidak valid).
    """
    if lam_h <= 0 or lam_a <= 0:
        raise ValueError(f"lambda harus > 0: lam_h={lam_h}, lam_a={lam_a}")
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
        nilai_tau = tau_dc(x, y, lam_h, lam_a, rho)
        if nilai_tau <= 0:
            raise ValueError(
                f"koreksi tau({x},{y}) = {nilai_tau:.4f} <= 0 untuk "
                f"lambda_kandang={lam_h:.4f}, lambda_tandang={lam_a:.4f}, "
                f"rho={rho}"
            )
    poisson_h = [
        math.exp(-lam_h) * lam_h**h / math.factorial(h) for h in range(max_gol + 1)
    ]
    poisson_a = [
        math.exp(-lam_a) * lam_a**a / math.factorial(a) for a in range(max_gol + 1)
    ]
    grid = [
        [
            poisson_h[h] * poisson_a[a] * tau_dc(h, a, lam_h, lam_a, rho)
            for a in range(max_gol + 1)
        ]
        for h in range(max_gol + 1)
    ]
    total = sum(sum(baris) for baris in grid)
    if total <= 0:
        raise ValueError(f"grid peluang tidak valid: jumlah {total}")
    p_home = p_draw = p_away = p_over = p_btts = 0.0
    for h in range(max_gol + 1):
        for a in range(max_gol + 1):
            p = grid[h][a] / total
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            if h + a > 2.5:
                p_over += p
            if h > 0 and a > 0:
                p_btts += p
    return {
        "home_win": p_home,
        "draw": p_draw,
        "away_win": p_away,
        "over_2.5": p_over,
        "under_2.5": 1.0 - p_over,
        "btts_yes": p_btts,
        "btts_no": 1.0 - p_btts,
        "massa_grid": total,
    }


def prediksi_laga(hasil_fit: dict, tim_kandang: str, tim_tandang: str) -> dict:
    """Prediksi satu laga dari hasil fit (kekuatan + rho + avg goals).

    Tim yang TIDAK ADA di hasil fit (mis. tim promosi yang belum
    pernah main di data fit) memakai attack = defence = 1,0 (rata-rata
    liga) — dicatat di "tim_tidak_dikenal", bukan dikarang dari tim lain.
    """
    attack = hasil_fit["attack"]
    defence = hasil_fit["defence"]
    tidak_dikenal = []
    atk_h = attack.get(tim_kandang)
    if atk_h is None:
        atk_h = 1.0
        tidak_dikenal.append(tim_kandang)
    def_h = defence.get(tim_kandang)
    if def_h is None:
        def_h = 1.0
        if tim_kandang not in tidak_dikenal:
            tidak_dikenal.append(tim_kandang)
    atk_a = attack.get(tim_tandang)
    if atk_a is None:
        atk_a = 1.0
        tidak_dikenal.append(tim_tandang)
    def_a = defence.get(tim_tandang)
    if def_a is None:
        def_a = 1.0
        if tim_tandang not in tidak_dikenal:
            tidak_dikenal.append(tim_tandang)
    avg_h = hasil_fit["avg_home_goals"]
    avg_a = hasil_fit["avg_away_goals"]
    lam_h = atk_h * def_a * avg_h
    lam_a = atk_a * def_h * avg_a
    peluang = probabilitas_laga(lam_h, lam_a, hasil_fit["rho"])
    peluang.update(
        {
            "lambda_home": lam_h,
            "lambda_away": lam_a,
            "attack_home": atk_h,
            "defence_home": def_h,
            "attack_away": atk_a,
            "defence_away": def_a,
            "tim_tidak_dikenal": tidak_dikenal,
        }
    )
    return peluang


def loglik_dixon_coles(
    laga: list[dict],
    attack: dict[str, float],
    defence: dict[str, float],
    avg_h: float,
    avg_a: float,
    rho: float,
) -> float:
    """Log-likelihood Dixon-Coles penuh atas daftar laga.

    Tim yang tidak ada di attack/defence memakai 1,0 (sama seperti
    prediksi_laga). Mengembalikan -inf bila ada tau <= 0.
    """
    total = 0.0
    for m in laga:
        lam_h = (
            attack.get(m["home_team"], 1.0) * defence.get(m["away_team"], 1.0) * avg_h
        )
        lam_a = (
            attack.get(m["away_team"], 1.0) * defence.get(m["home_team"], 1.0) * avg_a
        )
        x = m["home_goals"]
        y = m["away_goals"]
        if lam_h <= 0 or lam_a <= 0:
            return float("-inf")
        total += (
            x * math.log(lam_h)
            - lam_h
            - math.lgamma(x + 1)
            + y * math.log(lam_a)
            - lam_a
            - math.lgamma(y + 1)
        )
        if (x, y) in SKOR_TAU:
            nilai_tau = tau_dc(x, y, lam_h, lam_a, rho)
            if nilai_tau <= 0:
                return float("-inf")
            total += math.log(nilai_tau)
    return total


def _maksimum_golden(f, lo: float, hi: float, n_iter: int = GOLDEN_ITER) -> float:
    """Maksimalkan f (unimodal) atas [lo, hi] dengan golden-section."""
    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c = b - invphi * (b - a)
    d = a + invphi * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(n_iter):
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - invphi * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + invphi * (b - a)
            fd = f(d)
    return (a + b) / 2.0


class _DataFit:
    """Struktur bantu fit: indeks tim + array per laga + daftar per tim."""

    def __init__(self, laga: list[dict]):
        self.teams = sorted(
            {m["home_team"] for m in laga} | {m["away_team"] for m in laga}
        )
        self.idx = {tim: i for i, tim in enumerate(self.teams)}
        self.home = [self.idx[m["home_team"]] for m in laga]
        self.away = [self.idx[m["away_team"]] for m in laga]
        self.x = [m["home_goals"] for m in laga]
        self.y = [m["away_goals"] for m in laga]
        self.logfak = [
            math.lgamma(m["home_goals"] + 1) + math.lgamma(m["away_goals"] + 1)
            for m in laga
        ]
        self.is_low = [
            (xi, yi) in SKOR_TAU for xi, yi in zip(self.x, self.y, strict=True)
        ]
        self.per_tim: list[list[int]] = [[] for _ in self.teams]
        for i, (hi, ai) in enumerate(zip(self.home, self.away, strict=True)):
            self.per_tim[hi].append(i)
            self.per_tim[ai].append(i)
        self.low_idx = [i for i, rendah in enumerate(self.is_low) if rendah]
        self.n = len(laga)


def fit_dixon_coles(
    laga: list[dict],
    warm_start: dict | None = None,
    min_matches: int = MIN_MATCHES_FIT,
    max_sweeps: int = MAX_SWEEPS,
) -> dict:
    """MLE Dixon-Coles atas daftar laga (coordinate ascent, pure Python).

    laga: list dict dari ingest.football_data (home_team, away_team,
    home_goals, away_goals). warm_start: hasil fit sebelumnya (attack/
    defence/rho) untuk start hangat — dipakai validasi rolling agar
    tiap refit cepat; tim baru mulai dari 1,0. min_matches: laga
    minimum, di bawah itu ValueError (fail-closed, bukan ditebak).
    Mengembalikan dict hasil fit (presisi penuh; pembulatan hanya
    saat ditulis ke JSON oleh main).
    """
    if len(laga) < min_matches:
        raise ValueError(
            f"data tidak cukup untuk fit: {len(laga)} laga < minimum {min_matches}"
        )
    data = _DataFit(laga)
    if len(data.teams) < 2:
        raise ValueError(f"data tidak cukup untuk fit: hanya {len(data.teams)} tim")
    n_tim = len(data.teams)

    # Rata-rata sampel gol kandang/tandang — titik awal avg goals.
    sampel_h = statistics.fmean(data.x)
    sampel_a = statistics.fmean(data.y)
    if sampel_h <= 0 or sampel_a <= 0:
        raise ValueError("rata-rata gol sampel harus > 0")
    log_gh = math.log(sampel_h)
    log_ga = math.log(sampel_a)

    # State: log-attack, log-defence, rho (start hangat atau 1,0/0).
    la = [0.0] * n_tim
    ld = [0.0] * n_tim
    rho = 0.0
    if warm_start is not None:
        atk0 = warm_start.get("attack") or {}
        def0 = warm_start.get("defence") or {}
        for tim, i in data.idx.items():
            a0 = atk0.get(tim)
            d0 = def0.get(tim)
            if isinstance(a0, (int, float)) and a0 > 0:
                la[i] = math.log(a0)
            if isinstance(d0, (int, float)) and d0 > 0:
                ld[i] = math.log(d0)
        r0 = warm_start.get("rho")
        if isinstance(r0, (int, float)) and RHO_MIN <= r0 <= RHO_MAX:
            rho = float(r0)

    def _ll_laga(i: int, la_h: float, ld_a: float, la_a: float, ld_h: float) -> float:
        """Kontribusi loglik satu laga dari log-parameter komponennya."""
        log_lh = la_h + ld_a + log_gh
        log_la = la_a + ld_h + log_ga
        lh = math.exp(log_lh)
        lwt = math.exp(log_la)
        nilai = data.x[i] * log_lh - lh + data.y[i] * log_la - lwt - data.logfak[i]
        if data.is_low[i]:
            nilai_tau = tau_dc(data.x[i], data.y[i], lh, lwt, rho)
            if nilai_tau <= 0:
                return float("-inf")
            nilai += math.log(nilai_tau)
        return nilai

    def _ll_penuh() -> float:
        """Log-likelihood penuh atas semua laga (cek konvergensi)."""
        total = 0.0
        for i in range(data.n):
            nilai = _ll_laga(
                i,
                la[data.home[i]],
                ld[data.away[i]],
                la[data.away[i]],
                ld[data.home[i]],
            )
            if nilai == float("-inf"):
                return float("-inf")
            total += nilai
        return total

    def _objek_serang(tim: int, nilai_calon: float) -> float:
        """Loglik parsial (laga tim itu saja) untuk attack tim = exp(nilai)."""
        total = 0.0
        for i in data.per_tim[tim]:
            hi, ai = data.home[i], data.away[i]
            la_h = nilai_calon if hi == tim else la[hi]
            la_a = nilai_calon if ai == tim else la[ai]
            nilai = _ll_laga(i, la_h, ld[ai], la_a, ld[hi])
            if nilai == float("-inf"):
                return float("-inf")
            total += nilai
        return total

    def _objek_bertahan(tim: int, nilai_calon: float) -> float:
        """Loglik parsial (laga tim itu saja) untuk defence tim = exp(nilai)."""
        total = 0.0
        for i in data.per_tim[tim]:
            hi, ai = data.home[i], data.away[i]
            ld_a = nilai_calon if ai == tim else ld[ai]
            ld_h = nilai_calon if hi == tim else ld[hi]
            nilai = _ll_laga(i, la[hi], ld_a, la[ai], ld_h)
            if nilai == float("-inf"):
                return float("-inf")
            total += nilai
        return total

    def _cari_rho() -> float:
        """Grid rho atas laga skor-rendah (lambda kini sudah tetap)."""
        rendah = []
        for i in data.low_idx:
            lh = math.exp(la[data.home[i]] + ld[data.away[i]] + log_gh)
            lwt = math.exp(la[data.away[i]] + ld[data.home[i]] + log_ga)
            rendah.append((data.x[i], data.y[i], lh, lwt))

        def _objek(r: float) -> float:
            total = 0.0
            for x, y, lh, lwt in rendah:
                nilai_tau = tau_dc(x, y, lh, lwt, r)
                if nilai_tau <= 0:
                    return float("-inf")
                total += math.log(nilai_tau)
            return total

        terbaik = 0.0
        ll_terbaik = _objek(0.0)
        r = RHO_GRID_MIN
        while r <= RHO_GRID_MAX + 1e-9:
            nilai = _objek(r)
            if nilai > ll_terbaik:
                ll_terbaik = nilai
                terbaik = r
            r += RHO_GRID_STEP
        # Grid halus di sekitar titik terbaik.
        r = max(RHO_MIN, terbaik - RHO_FINE_HALF)
        akhir = min(RHO_MAX, terbaik + RHO_FINE_HALF)
        while r <= akhir + 1e-9:
            nilai = _objek(r)
            if nilai > ll_terbaik:
                ll_terbaik = nilai
                terbaik = r
            r += RHO_FINE_STEP
        return round(terbaik, 3)

    ll_awal = _ll_penuh()
    konvergen = False
    n_sweeps = 0
    ll_akhir = ll_awal
    for sapuan in range(max_sweeps):
        ll_sebelum = _ll_penuh()
        for tim in range(n_tim):
            lo = max(LOG_PARAM_MIN, la[tim] - BRAKET_LOG)
            hi = min(LOG_PARAM_MAX, la[tim] + BRAKET_LOG)
            la[tim] = _maksimum_golden(lambda v, t=tim: _objek_serang(t, v), lo, hi)
            lo = max(LOG_PARAM_MIN, ld[tim] - BRAKET_LOG)
            hi = min(LOG_PARAM_MAX, ld[tim] + BRAKET_LOG)
            ld[tim] = _maksimum_golden(lambda v, t=tim: _objek_bertahan(t, v), lo, hi)
        rho = _cari_rho()
        # Renormalisasi geometrik (lambda TIDAK berubah):
        # log-attack/log-defence di-centering, avg goals menyerap
        # faktor skala yang sama.
        mean_la = statistics.fmean(la)
        mean_ld = statistics.fmean(ld)
        la = [v - mean_la for v in la]
        ld = [v - mean_ld for v in ld]
        log_gh += mean_la + mean_ld
        log_ga += mean_la + mean_ld
        ll_akhir = _ll_penuh()
        n_sweeps = sapuan + 1
        if ll_akhir - ll_sebelum < TOL_LIK * (1.0 + abs(ll_akhir)):
            konvergen = True
            break

    # Normalisasi akhir ke rata-rata ARITMETIK 1 (lambda tetap sama
    # persis karena avg goals dikalikan faktor yang sama).
    attack_mentah = [math.exp(v) for v in la]
    defence_mentah = [math.exp(v) for v in ld]
    mean_atk = statistics.fmean(attack_mentah)
    mean_def = statistics.fmean(defence_mentah)
    avg_h = math.exp(log_gh) * mean_atk * mean_def
    avg_a = math.exp(log_ga) * mean_atk * mean_def
    attack = {tim: attack_mentah[i] / mean_atk for tim, i in data.idx.items()}
    defence = {tim: defence_mentah[i] / mean_def for tim, i in data.idx.items()}
    return {
        "rho": rho,
        "avg_home_goals": avg_h,
        "avg_away_goals": avg_a,
        "home_advantage_ratio": avg_h / avg_a,
        "rata-rata_sampel_home_goals": sampel_h,
        "rata-rata_sampel_away_goals": sampel_a,
        "attack": attack,
        "defence": defence,
        "teams": data.teams,
        "n_laga": data.n,
        "n_tim": n_tim,
        "loglik": ll_akhir,
        "loglik_awal": ll_awal,
        "n_sweeps": n_sweeps,
        "converged": konvergen,
    }


def _bulatkan_hasil_fit(hasil: dict) -> dict:
    """Salinan hasil fit dengan angka dibulatkan untuk JSON."""
    salinan = dict(hasil)
    for kunci in (
        "rho",
        "avg_home_goals",
        "avg_away_goals",
        "home_advantage_ratio",
        "rata-rata_sampel_home_goals",
        "rata-rata_sampel_away_goals",
    ):
        salinan[kunci] = round(hasil[kunci], 4)
    salinan["loglik"] = round(hasil["loglik"], 2)
    salinan["loglik_awal"] = round(hasil["loglik_awal"], 2)
    salinan["attack"] = {tim: round(v, 4) for tim, v in hasil["attack"].items()}
    salinan["defence"] = {tim: round(v, 4) for tim, v in hasil["defence"].items()}
    return salinan


def _info_file(path: Path) -> dict:
    """Info satu file CSV: ukuran + tanggal modifikasi (= tanggal unduh)."""
    stat = path.stat()
    tanggal = datetime.fromtimestamp(stat.st_mtime, tz=UTC).date().isoformat()
    return {"file": str(path), "ukuran_byte": stat.st_size, "tanggal_file": tanggal}


def fit_liga(
    data_dir: Path,
    liga: str,
    musim_fit: list[str],
    musim_live: str | None,
) -> tuple[dict, list[dict]]:
    """Fit satu liga: per musim + gabungan + parsial musim berjalan.

    Mengembalikan (hasil_liga, info_unduhan). Raise FileNotFoundError
    bila file musim fit tidak ada (fail-closed).
    """
    hasil: dict = {
        "kode_file": football_data.KODE_LIGA[liga],
        "musim_fit": [football_data.label_musim(m) for m in musim_fit],
        "per_musim": {},
        "pooled": None,
        "live_parsial": None,
    }
    info_unduhan: list[dict] = []
    semua_laga: list[dict] = []
    for musim in musim_fit:
        path = data_dir / f"{football_data.KODE_LIGA[liga]}_{musim}.csv"
        laga, info = football_data.muat_csv_hasil(path, liga, musim)
        info_unduhan.append({**_info_file(path), **info})
        hasil["per_musim"][football_data.label_musim(musim)] = _bulatkan_hasil_fit(
            fit_dixon_coles(laga)
        )
        semua_laga.extend(laga)
    hasil["pooled"] = _bulatkan_hasil_fit(fit_dixon_coles(semua_laga))
    hasil["pooled"]["musim_digabung"] = hasil["musim_fit"]
    if musim_live:
        path = data_dir / f"{football_data.KODE_LIGA[liga]}_{musim_live}.csv"
        if path.exists():
            laga, info = football_data.muat_csv_hasil(path, liga, musim_live)
            info_unduhan.append({**_info_file(path), **info})
            parsial = _bulatkan_hasil_fit(fit_dixon_coles(laga))
            parsial["label"] = "parsial — musim berjalan, BUKAN musim penuh"
            parsial["musim"] = football_data.label_musim(musim_live)
            hasil["live_parsial"] = parsial
        else:
            hasil["live_parsial"] = {
                "status": "DATA_INCOMPLETE",
                "alasan": f"file musim berjalan tidak ada: {path}",
            }
    return hasil, info_unduhan


KETERBATASAN = [
    "Kekuatan tim fit GABUNGAN adalah rata-rata 3 musim — skuad berubah "
    "antar musim, jadi kekuatan gabungan sudah agak basi untuk tim yang "
    "banyak berubah (lihat per-musim untuk pergeserannya).",
    "Tim promosi yang belum pernah main di data fit diprediksi dengan "
    "attack = defence = 1,0 (rata-rata liga) — bukan estimasi dari data.",
    "Fit memakai likelihood Dixon-Coles standar (Poisson x tau); mesin "
    "sim memotong grid di 10 gol per tim lalu menormalisasi — selisih "
    "massa peluang < 1e-4, tidak memengaruhi parameter secara material.",
    "Tidak ada penyesuaian cedera/absensi pemain, jadwal padat, atau "
    "motivasi (laga akhir musim) — model hanya membaca skor historis.",
    "Rho adalah satu nilai per liga (per musim / gabungan) — korelasi "
    "skor rendah diasumsikan sama untuk semua pasangan tim.",
    "Fit parsial musim berjalan memakai sedikit laga per tim (~5 kandang "
    "+ ~5 tandang) — kekuatannya NOISY, hanya contoh live, bukan "
    "estimasi stabil.",
]


def main(argv: list[str] | None = None) -> int:
    """Jalankan fit dari CLI. 0 sukses, 2 data tidak tersedia."""
    parser = argparse.ArgumentParser(
        description="Fit parameter Dixon-Coles sepak bola dari CSV hasil."
    )
    parser.add_argument(
        "--leagues",
        nargs="+",
        default=["EPL", "LaLiga"],
        help="liga yang di-fit (default: EPL LaLiga)",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=["2223", "2324", "2425"],
        help="musim fit (default: 2223 2324 2425)",
    )
    parser.add_argument(
        "--live-season",
        default="2627",
        help="musim berjalan untuk fit parsial contoh live "
        "(default: 2627; kosongkan dengan --live-season '')",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="direktori CSV hasil (default: data)",
    )
    parser.add_argument(
        "--out",
        default="out/fit_soccer_params.json",
        help="file JSON hasil fit (default: out/fit_soccer_params.json)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / args.data_dir
    out_path = repo_root / args.out
    musim_live = args.live_season or None

    hasil = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": (
            "MLE Dixon-Coles (coordinate ascent, pure Python) — "
            "lihat docstring scripts/fit_soccer_params.py + "
            "LAPORAN-FIT-BOLA.md"
        ),
        "sumber_data": (
            "football-data.co.uk (CSV lokal di data/; hanya kolom hasil "
            "FTHG/FTAG — kolom odds Pinnacle TIDAK dipakai, stale sejak "
            "23/07/2025)"
        ),
        "status_persetujuan": (
            "MENUNGGU persetujuan user — nilai ini BELUM ditulis ke "
            "config/playstyle.yaml (dixon_coles_rho dan "
            "home_advantage_by_league tetap null)"
        ),
        "leagues": {},
        "downloads": [],
        "keterbatasan": KETERBATASAN,
    }
    for liga in args.leagues:
        try:
            hasil_liga, info_unduhan = fit_liga(
                data_dir, liga, args.seasons, musim_live
            )
        except (FileNotFoundError, ValueError) as exc:
            if liga == "EPL":
                print(f"fit dibatalkan: {exc}", file=sys.stderr)
                return 2
            print(f"peringatan: liga {liga} dilewati ({exc})", file=sys.stderr)
            hasil["leagues"][liga] = {"status": "DILEWATI", "alasan": str(exc)}
            continue
        hasil["leagues"][liga] = hasil_liga
        hasil["downloads"].extend(info_unduhan)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for liga, hasil_liga in hasil["leagues"].items():
        if hasil_liga.get("status") == "DILEWATI":
            print(f"{liga}: DILEWATI ({hasil_liga['alasan']})")
            continue
        pooled = hasil_liga["pooled"]
        print(
            f"{liga} gabungan ({', '.join(hasil_liga['musim_fit'])}): "
            f"n={pooled['n_laga']} rho={pooled['rho']} "
            f"avg_home={pooled['avg_home_goals']} "
            f"avg_away={pooled['avg_away_goals']} "
            f"rasio_kandang={pooled['home_advantage_ratio']} "
            f"loglik={pooled['loglik']} sapuan={pooled['n_sweeps']} "
            f"konvergen={pooled['converged']}"
        )
        for musim, fit_musim in hasil_liga["per_musim"].items():
            print(
                f"  {musim}: n={fit_musim['n_laga']} rho={fit_musim['rho']} "
                f"avg_home={fit_musim['avg_home_goals']} "
                f"avg_away={fit_musim['avg_away_goals']} "
                f"rasio={fit_musim['home_advantage_ratio']}"
            )
        parsial = hasil_liga.get("live_parsial")
        if parsial and parsial.get("status") != "DATA_INCOMPLETE":
            print(
                f"  parsial {parsial['musim']}: n={parsial['n_laga']} "
                f"rho={parsial['rho']} "
                f"avg_home={parsial['avg_home_goals']} "
                f"avg_away={parsial['avg_away_goals']}"
            )
    print(f"hasil fit ditulis ke {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
