#!/usr/bin/env python3
"""Satu pintu masuk muse-parlay-analyst (Blueprint §10, SOP §5).

    python cli.py analyze --input slate.json [--out out.json]
        # Tahap 2b ✓ — tarik data (SOP langkah 2-3), tulis
        # out/analysis_<slate_id>.json. Simulasi/tiket Tahap 3+.
    python cli.py recheck --analysis out/analysis_<id>.json [--match DET@ATL_2026-11-22]
        # Tahap 3 Langkah 2 ✓ — cek ulang pra-submit satu laga NBA.
        # Exit 0 = GO, 1 = NO-GO (laporan ditulis), 2 = tidak bisa jalan.
    python cli.py laporan --analysis out/analysis_<id>.json [--match ...]
        [--recheck out/recheck_<id>.json] [--out laporan.txt] [--json]
        # Tahap 3 Langkah 3 ✓ — laporan lengkap satu laga NBA.
    python cli.py tanya --analysis out/analysis_<id>.json [--match ...]
        "<pertanyaan>"
        # Tahap 3 Langkah 3 ✓ — tanya-jawab soal satu laga NBA.
    python cli.py racik --analysis <file...> [--recheck <file...>]
        --stake-total <usd> [--out out/tickets_<tanggal>.json]
        # Tahap 3 Langkah 3 ✓ — racik Tiket Asuransi + Utama.
        # Exit 0 = minimal satu tiket terracik, 1 = tidak ada tiket,
        # 2 = tidak bisa jalan.
    python cli.py log --file ticket.json       # Tahap 1  ✓
    python cli.py log --settle <id> --result WIN|LOSS|PUSH|VOID|CASHOUT
        [--cashout-amount <usd>] [--leg-result <leg_id>=<hasil> ...]
    python cli.py recap [--json]

Exit code: 0 sukses, 1 error (input tidak valid / ledger gagal) —
recheck: 0 = GO, 1 = NO-GO (laporan tetap ditulis), 2 = recheck tidak
bisa berjalan (tidak ada laporan). laporan/tanya: 0 sukses, 2 = tidak
bisa jalan. racik: 0 = minimal satu tiket terracik, 1 = tidak ada
tiket yang bisa diracik, 2 = tidak bisa jalan.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from ledger import recap as recap_mod  # noqa: E402
from ledger import store  # noqa: E402

RECHECK_ERROR = 2  # recheck tidak bisa berjalan (tidak ada laporan)


def _db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        default=str(store.DEFAULT_DB_PATH),
        help="path file SQLite ledger (default: ledger.db di root repo)",
    )


def _validate_slate(slate: dict) -> str | None:
    """Validasi slate input terhadap schemas/slate.schema.json.

    Mengembalikan pesan error, atau None bila valid. Bila ``jsonschema``
    tidak tersedia, pakai validasi minimal (required-field) + peringatan
    ke stderr.
    """
    try:
        import jsonschema
    except ImportError:
        print(
            "peringatan: jsonschema tidak tersedia — validasi minimal "
            "(required-field) saja",
            file=sys.stderr,
        )
        for key in ("slate_id", "created_at_wib", "matches"):
            if key not in slate:
                return f"slate kehilangan kunci wajib: {key}"
        if not isinstance(slate.get("matches"), list) or not slate["matches"]:
            return "slate.matches harus list tidak kosong"
        for entry in slate["matches"]:
            for key in ("match_id", "sport", "league", "home", "away", "start_time"):
                if key not in entry:
                    return f"laga kehilangan kunci wajib: {key}"
        return None
    schema_path = REPO_ROOT / "schemas" / "slate.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"tidak bisa membaca skema slate: {exc}"
    try:
        jsonschema.validate(slate, schema)
    except jsonschema.ValidationError as exc:
        return f"slate tidak valid: {exc.message}"
    return None


def _slate_date(match: dict, sport: str | None = None) -> str | None:
    """Tanggal (YYYY-MM-DD) dari start_time satu laga; None bila tidak sah.

    NBA: tanggal US Eastern — stats.nba.com memakai tanggal Eastern, jadi
    start_time WIB yang jatuh dini hari (mis. 08:00 WIB) adalah laga malam
    sebelumnya di AS. Sport lain: tanggal apa adanya dari start_time
    (pencocokan fixture bola toleran ±1 hari).
    """
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    try:
        parsed = datetime.fromisoformat(match["start_time"])
    except (KeyError, TypeError, ValueError):
        return None
    if sport == "nba":
        if parsed.tzinfo is None:
            # Skema slate mewajibkan zona waktu; bila hilang, anggap UTC.
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    return parsed.date().isoformat()


def _league_code(league: str | None) -> str:
    """Kode liga fetcher dari nama liga slate ('Premier League' -> 'EPL')."""
    mapping = {
        "Premier League": "EPL",
        "EPL": "EPL",
        "LaLiga": "LaLiga",
        "La Liga": "LaLiga",
    }
    return mapping.get(str(league or ""), str(league or "EPL"))


def _lampirkan_nba_analysis(
    matches_2b: list[dict], entries_slate: list[dict], tanggal_eastern: str
) -> None:
    """Lampirkan artefak nba_analysis ke tiap laga NBA hasil build_slate.

    Tahap 3 Langkah 2: untuk tiap laga NBA, tricode diambil dari nama tim
    entri slate asal (dicocokkan lewat match_id), lalu
    engine.nba_analysis.build_nba_analysis dipanggil dan hasilnya
    dilampirkan sebagai kunci "nba_analysis" pada entri MatchData 2b.
    Bila builder gagal total / tricode tidak bisa dipetakan, dilampirkan
    artefak minimal DATA_INCOMPLETE — analyze TIDAK gagal hanya karena
    satu laga NBA. Laga tanpa entri slate asal (mis. slate hasil mock
    di tes) dilewati: timnya tidak diketahui, tidak bisa dianalisis.
    """
    from engine import nba_analysis as nba_analysis_mod
    from ingest.nba_brain import team_tricode

    per_match_id = {
        entry.get("match_id"): entry
        for entry in entries_slate
        if isinstance(entry, dict)
    }
    for match_2b in matches_2b:
        entri = per_match_id.get(match_2b.get("match_id"))
        if entri is None:
            continue
        start_time = entri.get("start_time")
        home = team_tricode(entri.get("home") or "")
        away = team_tricode(entri.get("away") or "")
        if home is None or away is None:
            match_2b["nba_analysis"] = nba_analysis_mod.minimal_nba_analysis(
                entri.get("match_id") or match_2b.get("match_id"),
                home or "UNK",
                away or "UNK",
                tanggal_eastern,
                [
                    "tricode_tidak_dikenal: "
                    f"{entri.get('home')!r} vs {entri.get('away')!r}"
                ],
                start_time=start_time,
            )
            continue
        try:
            match_2b["nba_analysis"] = nba_analysis_mod.build_nba_analysis(
                home,
                away,
                tanggal_eastern,
                slate_match=match_2b,
                start_time=start_time,
            )
        except Exception as exc:  # noqa: BLE001 - builder gagal != analyze gagal
            match_2b["nba_analysis"] = nba_analysis_mod.minimal_nba_analysis(
                f"{away}@{home}_{tanggal_eastern}",
                home,
                away,
                tanggal_eastern,
                [f"builder_gagal: {type(exc).__name__}: {exc}"],
                start_time=start_time,
            )


def cmd_analyze(args: argparse.Namespace) -> int:
    """Jalankan analisis slate Tahap 2b+3: tarik data + validasi (SOP langkah 2-3).

    Input slate divalidasi skema, ditolak bila ``confirmed_by_user`` bukan
    true (SOP langkah 1). Laga dikelompokkan per sport; tanggal per sport
    = tanggal start_time laga pertama sport itu — NBA dikonversi ke tanggal
    US Eastern (stats.nba.com memakai tanggal Eastern). Bila laga lintas
    tanggal, laga di tanggal lain tetap diproses — pencocokan berbasis tim,
    tapi pencarian jadwal memakai tanggal sport itu. Untuk laga NBA,
    setelah build_slate, dilampirkan artefak "nba_analysis" per laga
    (Tahap 3 Langkah 2; gagal total -> artefak minimal DATA_INCOMPLETE,
    slate tetap jalan). Satu file output JSON ditulis (default
    ``out/analysis_<slate_id>.json``) + ringkasan tercetak.
    """
    try:
        slate = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.input}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(slate, dict):
        print("error: slate harus berupa objek JSON", file=sys.stderr)
        return 1
    error = _validate_slate(slate)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if slate.get("confirmed_by_user") is not True:
        print(
            "error: slate belum dikonfirmasi user (confirmed_by_user bukan "
            "true) — analisis tidak jalan (SOP langkah 1: tampilkan tabel "
            "dulu, tunggu user balas 'ok')",
            file=sys.stderr,
        )
        return 1

    from ingest.slate import build_slate

    by_sport: dict[str, list[dict]] = {}
    for entry in slate["matches"]:
        by_sport.setdefault(entry["sport"], []).append(entry)

    all_matches: list[dict] = []
    summary = {
        "matches": 0,
        "ok": 0,
        "data_incomplete": 0,
        "hold": 0,
        "model_only": 0,
        "tanpa_xg": 0,
    }
    odds_api = {"calls": 0, "credits_used": 0}
    skip_odds_api = bool(getattr(args, "tanpa_odds_api", False))
    for sport, entries in sorted(by_sport.items()):
        date = _slate_date(entries[0], sport)
        if date is None:
            print(
                f"error: start_time laga pertama {sport} tidak bisa dibaca: "
                f"{entries[0].get('start_time')!r}",
                file=sys.stderr,
            )
            return 1
        league = _league_code(entries[0].get("league"))
        try:
            if sport == "football":
                result = build_slate(
                    sport,
                    date,
                    matches=entries,
                    league=league,
                    skip_odds_api=skip_odds_api,
                )
            else:
                result = build_slate(
                    sport, date, matches=entries, skip_odds_api=skip_odds_api
                )
        except (ValueError, RuntimeError) as exc:
            print(f"error: gagal merakit slate {sport}: {exc}", file=sys.stderr)
            return 1
        if sport == "nba":
            _lampirkan_nba_analysis(result["matches"], entries, date)
        all_matches.extend(result["matches"])
        for key in summary:
            summary[key] += result["summary"][key]
        odds_api["calls"] += result["odds_api"]["calls"]
        odds_api["credits_used"] += result["odds_api"]["credits_used"]

    from datetime import UTC, datetime

    output = {
        "slate_id": slate["slate_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "matches": all_matches,
        "summary": summary,
        "odds_api": odds_api,
    }
    out_path = Path(
        args.out or (REPO_ROOT / "out" / f"analysis_{slate['slate_id']}.json")
    )
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return 1
    print(
        f"slate {slate['slate_id']}: {summary['matches']} laga "
        f"(OK {summary['ok']}, HOLD {summary['hold']}, "
        f"DATA_INCOMPLETE {summary['data_incomplete']})"
    )
    print(
        f"MODEL_ONLY: {summary['model_only']} laga | "
        f"TANPA_XG: {summary['tanpa_xg']} laga"
    )
    print(
        f"Odds API: {odds_api['calls']} panggilan, "
        f"{odds_api['credits_used']} kredit"
    )
    for entry in all_matches:
        labels = ",".join(entry.get("labels") or [])
        label_text = f" [{labels}]" if labels else ""
        nba = entry.get("nba_analysis")
        nba_text = (
            f" | nba_analysis: {nba['status']}"
            if isinstance(nba, dict) and isinstance(nba.get("status"), str)
            else ""
        )
        print(f"  {entry['match_id']}: {entry['status']}{label_text}{nba_text}")
    print(f"output: {out_path}")
    return 0


def _ambil_nba_analysis(
    data: dict, match_id: str | None
) -> tuple[dict | None, str | None]:
    """Ambil artefak nba_analysis dari file input recheck.

    Menerima (a) artefak nba_analysis langsung (format ==
    "nba_analysis") atau (b) output cli.py analyze (ada kunci
    "matches"; artefak ada di kunci "nba_analysis" tiap entri laga).
    match_id: bila diisi, laga yang dicari; bila kosong dan hanya
    satu laga punya artefak, laga itu yang dipakai. Mengembalikan
    (artefak, None) atau (None, pesan error).
    """
    if not isinstance(data, dict):
        return None, "file analisis harus berupa objek JSON"
    if data.get("format") == "nba_analysis":
        if match_id is not None and data.get("match_id") != match_id:
            return None, (
                f"file berisi artefak {data.get('match_id')}, bukan {match_id}"
            )
        return data, None
    matches = data.get("matches")
    if not isinstance(matches, list):
        return None, (
            "file bukan artefak nba_analysis maupun output analyze "
            "(tidak ada kunci 'matches')"
        )
    punya = [
        m
        for m in matches
        if isinstance(m, dict) and isinstance(m.get("nba_analysis"), dict)
    ]
    if match_id is not None:
        for m in punya:
            if m.get("match_id") == match_id:
                return m["nba_analysis"], None
            # Terima juga match_id artefak ("DET@ATL_2026-11-22"),
            # bukan hanya match_id slate ("nba-2026-11-22-det-atl").
            inner = m.get("nba_analysis") or {}
            if inner.get("match_id") == match_id:
                return m["nba_analysis"], None
        return None, f"laga {match_id} tidak punya artefak nba_analysis di file ini"
    if len(punya) == 1:
        return punya[0]["nba_analysis"], None
    if not punya:
        return None, "tidak ada laga dengan artefak nba_analysis di file ini"
    daftar = ", ".join(m.get("match_id", "?") for m in punya)
    return (
        None,
        f"ada {len(punya)} laga dengan artefak nba_analysis ({daftar}) — "
        "sebutkan --match",
    )


def _kumpulkan_nba_analysis(
    data: dict,
) -> tuple[list[dict] | None, str | None]:
    """Kumpulkan SEMUA artefak nba_analysis dari file input (untuk racik).

    Menerima (a) artefak nba_analysis langsung (format ==
    "nba_analysis") atau (b) output cli.py analyze (ada kunci
    "matches"; artefak ada di kunci "nba_analysis" tiap entri laga).
    Mengembalikan (daftar artefak, None) atau (None, pesan error).
    """
    if not isinstance(data, dict):
        return None, "file analisis harus berupa objek JSON"
    if data.get("format") == "nba_analysis":
        return [data], None
    matches = data.get("matches")
    if not isinstance(matches, list):
        return None, (
            "file bukan artefak nba_analysis maupun output analyze "
            "(tidak ada kunci 'matches')"
        )
    punya = [
        m["nba_analysis"]
        for m in matches
        if isinstance(m, dict) and isinstance(m.get("nba_analysis"), dict)
    ]
    if not punya:
        return None, "tidak ada laga dengan artefak nba_analysis di file ini"
    return punya, None


def cmd_recheck(args: argparse.Namespace) -> int:
    """Cek ulang pra-submit satu laga NBA (Tahap 3 Langkah 2).

    Input: file JSON analisis (--analysis) — artefak nba_analysis
    langsung, atau output cli.py analyze (pilih laga dengan --match).
    Ambil data segar + putuskan GO / NO-GO via engine.recheck
    (0 kredit Odds API: recheck hanya memakai cedera + tangga
    Polymarket/jup.ag). Laporan ditulis ke --out (default
    out/recheck_<match_id>.json). Exit code: 0 = GO, 1 = NO-GO
    (laporan tetap ditulis), 2 = recheck tidak bisa berjalan
    (tidak ada laporan).
    """
    try:
        data = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.analysis}: {exc}", file=sys.stderr)
        return RECHECK_ERROR
    analysis, error = _ambil_nba_analysis(data, args.match)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return RECHECK_ERROR
    from config import ConfigError
    from engine import nba_analysis as nba_analysis_mod
    from engine import recheck as recheck_mod

    error = nba_analysis_mod.validate_nba_analysis(analysis)
    if error is not None:
        print(f"error: artefak nba_analysis tidak valid: {error}", file=sys.stderr)
        return RECHECK_ERROR
    try:
        fresh = recheck_mod.fetch_fresh(analysis)
        laporan = recheck_mod.decide(analysis, fresh)
    except (ValueError, OSError, ConfigError) as exc:
        print(f"error: recheck gagal: {exc}", file=sys.stderr)
        return RECHECK_ERROR
    match_id = analysis.get("match_id", "unknown")
    out_path = Path(args.out or (REPO_ROOT / "out" / f"recheck_{match_id}.json"))
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(laporan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return RECHECK_ERROR
    verdict = laporan.get("verdict", "?")
    resim = "ya" if laporan.get("resimulated") else "tidak"
    print(f"recheck {match_id}: {verdict} (resim: {resim})")
    for kaki in laporan.get("legs", []):
        tiket = kaki.get("ticket")
        if not tiket:
            # Laporan recheck belum membawa kunci "ticket" (kontrak
            # langkah 2); tiket diambil dari akhir leg_id
            # ("...:total_under_233.5:insurance" -> "insurance").
            leg_id = kaki.get("leg_id", "?")
            tiket = leg_id.rsplit(":", 1)[-1] if ":" in leg_id else leg_id
        garis = (
            kaki.get("new_line")
            if kaki.get("new_line") is not None
            else kaki.get("old_line")
        )
        garis_txt = f" U{garis:g}" if isinstance(garis, (int, float)) else ""
        alasan = kaki.get("reasons") or []
        alasan_txt = f" — {alasan[0]}" if alasan else ""
        print(f"  {tiket}{garis_txt}: {kaki.get('verdict')}{alasan_txt}")
    if laporan.get("action_required"):
        print(f"  yang harus diubah: {laporan['action_required']}")
    print(f"output: {out_path}")
    return 0 if verdict == "GO" else 1


def cmd_laporan(args: argparse.Namespace) -> int:
    """Laporan lengkap satu laga NBA (Tahap 3 Langkah 3).

    Input: file JSON analisis (--analysis) — artefak nba_analysis
    langsung, atau output cli.py analyze (pilih laga dengan --match).
    Laporan recheck opsional (--recheck) dilampirkan bila ada.
    Teks dicetak ke stdout atau ditulis ke --out; --json mengeluarkan
    bentuk JSON laporan. Exit code: 0 sukses, 2 = tidak bisa jalan.
    """
    try:
        data = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.analysis}: {exc}", file=sys.stderr)
        return 2
    analysis, error = _ambil_nba_analysis(data, args.match)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2
    recheck = None
    if args.recheck:
        try:
            recheck = json.loads(Path(args.recheck).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: tidak bisa membaca {args.recheck}: {exc}", file=sys.stderr)
            return 2
    from report import nba_report as nba_report_mod

    try:
        if args.json:
            hasil = nba_report_mod.render_nba_report_json(analysis, recheck)
            teks = json.dumps(hasil, ensure_ascii=False, indent=2)
        else:
            teks = nba_report_mod.render_nba_report(analysis, recheck)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    match_id = analysis.get("match_id", "unknown")
    if args.out:
        try:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(teks, encoding="utf-8")
        except OSError as exc:
            print(f"error: tidak bisa menulis {args.out}: {exc}", file=sys.stderr)
            return 2
        print(f"laporan {match_id} ditulis ke {args.out}")
        return 0
    print(teks)
    return 0


def cmd_tanya(args: argparse.Namespace) -> int:
    """Tanya-jawab soal satu laga NBA (Tahap 3 Langkah 3).

    Input: file JSON analisis (--analysis) + pertanyaan
    (Bahasa Indonesia). Jawaban berasal dari artefak analisis dan
    mesin sim — angka dari kode, bukan karangan; data tidak ada
    dijawab "tidak terverifikasi". Exit code: 0 sukses,
    2 = tidak bisa jalan.
    """
    try:
        data = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.analysis}: {exc}", file=sys.stderr)
        return 2
    analysis, error = _ambil_nba_analysis(data, args.match)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2
    from engine import qa as qa_mod

    hasil = qa_mod.answer(analysis, args.pertanyaan)
    print(hasil["answer"])
    if not hasil.get("verified", True):
        print(
            "[sebagian jawaban tidak terverifikasi — datanya tidak ada "
            "di analisis ini]",
            file=sys.stderr,
        )
    return 0


def cmd_racik(args: argparse.Namespace) -> int:
    """Racik Tiket Asuransi + Utama dari satu slate NBA (Tahap 3 Langkah 3).

    Input: file-file JSON analisis (--analysis, boleh banyak) —
    artefak nba_analysis langsung, atau output cli.py analyze.
    Laporan recheck (--recheck, boleh banyak) bersifat opsional;
    tanpa recheck, tiket mendapat peringatan jendela. Modal total
    (--stake-total, USD) wajib — peracik tidak mengarang modal.
    Hasil ditulis ke --out (default out/tickets_<tanggal>.json) +
    ringkasan tercetak. Exit code: 0 = minimal satu tiket terracik,
    1 = tidak ada tiket yang bisa diracik, 2 = tidak bisa jalan.
    """
    analyses: list[dict] = []
    for path in args.analysis:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: tidak bisa membaca {path}: {exc}", file=sys.stderr)
            return 2
        got, error = _kumpulkan_nba_analysis(data)
        if error is not None:
            print(f"error: {path}: {error}", file=sys.stderr)
            return 2
        analyses.extend(got)
    # Laga yang sama dari dua file dihitung sekali (kemunculan pertama).
    dilihat: set[str] = set()
    unik: list[dict] = []
    for art in analyses:
        mid = art.get("match_id")
        if isinstance(mid, str) and mid in dilihat:
            print(
                f"catatan: laga {mid} muncul dua kali — dipakai sekali",
                file=sys.stderr,
            )
            continue
        if isinstance(mid, str):
            dilihat.add(mid)
        unik.append(art)
    analyses = unik
    if not analyses:
        print("error: tidak ada artefak nba_analysis", file=sys.stderr)
        return 2
    rechecks: list[dict] | None = None
    if args.recheck:
        rechecks = []
        for path in args.recheck:
            try:
                lap = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"error: tidak bisa membaca {path}: {exc}", file=sys.stderr)
                return 2
            if not isinstance(lap, dict) or lap.get("format") != "nba_recheck":
                print(f"error: {path} bukan laporan nba_recheck", file=sys.stderr)
                return 2
            rechecks.append(lap)
    from config import ConfigError, load_playstyle
    from engine import nba_analysis as nba_analysis_mod
    from engine import ticket_composer as composer_mod

    for art in analyses:
        error = nba_analysis_mod.validate_nba_analysis(art)
        if error is not None:
            print(
                f"error: artefak {art.get('match_id', '?')} tidak valid: {error}",
                file=sys.stderr,
            )
            return 2
    try:
        cfg = load_playstyle()
        hasil = composer_mod.compose_tickets(
            analyses, rechecks, cfg, stake_total=args.stake_total
        )
    except (ValueError, ConfigError) as exc:
        print(f"error: peracik gagal: {exc}", file=sys.stderr)
        return 2
    tanggal = analyses[0].get("game_date") or datetime.date.today().isoformat()
    out_path = Path(args.out or (REPO_ROOT / "out" / f"tickets_{tanggal}.json"))
    payload = {
        "format": "tickets",
        "game_date": tanggal,
        "insurance": hasil.get("insurance"),
        "insurance_reason": hasil.get("insurance_reason"),
        "main": hasil.get("main"),
        "main_reason": hasil.get("main_reason"),
        "warnings": hasil.get("warnings", []),
        "summary": hasil.get("summary", ""),
    }
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return 2
    print(hasil.get("summary", ""))
    for warn in hasil.get("warnings", []):
        print(f"PERINGATAN: {warn}")
    print(f"output: {out_path}")
    return 0 if (hasil.get("insurance") or hasil.get("main")) else 1


def _parse_leg_results(raw: list[str] | None) -> dict[str, str]:
    """Ubah ['leg-01=WIN', ...] menjadi {leg_id: hasil}. Format salah -> error."""
    parsed: dict[str, str] = {}
    for item in raw or []:
        if "=" not in item:
            raise ValueError(f"format --leg-result salah: {item!r} (pakai ID=HASIL)")
        leg_id, result = item.split("=", 1)
        parsed[leg_id.strip()] = result.strip().upper()
    return parsed


def cmd_log(args: argparse.Namespace) -> int:
    """Catat tiket dari file JSON, atau selesaikan tiket PENDING."""
    conn = store.connect(args.db)
    if args.settle:
        try:
            leg_results = _parse_leg_results(args.leg_result)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            profit = store.settle_ticket(
                conn,
                args.settle,
                args.result,
                leg_results=leg_results,
                cashout_amount=args.cashout_amount,
            )
        except store.LedgerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        saved = store.get_ticket(conn, args.settle)
        extra = ""
        if saved and saved.get("multiplier_original") is not None:
            extra = (
                f" (pengali dihitung ulang {saved['multiplier_original']}"
                f"x -> {saved['multiplier']:.4f}x karena kaki VOID/PUSH)"
            )
        print(
            f"tiket {args.settle} diselesaikan: {saved['result']}, "
            f"untung/rugi ${profit:+.2f}{extra}"
        )
        return 0

    if not args.file:
        print(
            "error: pakai --file ticket.json atau --settle <id> --result ...",
            file=sys.stderr,
        )
        return 1
    try:
        ticket = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.file}: {exc}", file=sys.stderr)
        return 1
    try:
        ticket_id = store.log_ticket(conn, ticket)
    except store.LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    saved = store.get_ticket(conn, ticket_id)
    profit = saved["profit_loss"] if saved else None
    profit_text = f"${profit:+.2f}" if profit is not None else "pending"
    extra = ""
    if saved and saved.get("multiplier_original") is not None:
        extra = (
            f", pengali awal {saved['multiplier_original']}x "
            f"(dihitung ulang karena kaki VOID/PUSH)"
        )
    print(
        f"tiket {ticket_id} dicatat ({saved['type']}, "
        f"modal ${saved['stake']:.2f}, pengali {saved['multiplier']}x, "
        f"hasil {saved['result']}, untung/rugi {profit_text}{extra})"
    )
    return 0


def cmd_recap(args: argparse.Namespace) -> int:
    """Tampilkan rekap untung/rugi ledger (teks atau JSON)."""
    conn = store.connect(args.db)
    data = recap_mod.compute_recap(conn)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(recap_mod.format_recap(data))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser argumen CLI (analyze / recheck / laporan / tanya / racik / log / recap)."""
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="muse-parlay-analyst — satu pintu masuk (Blueprint §10).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="analisis slate (Tahap 2b: tarik data)")
    p_analyze.add_argument("--input", required=True, help="file slate.json")
    p_analyze.add_argument(
        "--out",
        default=None,
        help="file output JSON (default: out/analysis_<slate_id>.json)",
    )
    p_analyze.add_argument(
        "--tanpa-odds-api",
        action="store_true",
        help="jangan panggil The Odds API sama sekali (0 kredit; pembanding "
        "sportsbook dilewati, Kalshi tetap dicoba)",
    )
    p_analyze.set_defaults(func=cmd_analyze)

    p_recheck = sub.add_parser(
        "recheck",
        help="cek ulang pra-submit satu laga NBA (Tahap 3 Langkah 2)",
    )
    p_recheck.add_argument(
        "--analysis",
        required=True,
        help="file JSON analisis: artefak nba_analysis langsung, atau "
        "output cli.py analyze",
    )
    p_recheck.add_argument(
        "--match",
        default=None,
        help="match_id laga yang dicek (wajib bila file berisi lebih "
        "dari satu laga dengan artefak nba_analysis)",
    )
    p_recheck.add_argument(
        "--out",
        default=None,
        help="file output JSON (default: out/recheck_<match_id>.json)",
    )
    p_recheck.set_defaults(func=cmd_recheck)

    p_laporan = sub.add_parser(
        "laporan",
        help="laporan lengkap satu laga NBA (Tahap 3 Langkah 3)",
    )
    p_laporan.add_argument(
        "--analysis",
        required=True,
        help="file JSON analisis: artefak nba_analysis langsung, atau "
        "output cli.py analyze",
    )
    p_laporan.add_argument(
        "--match",
        default=None,
        help="match_id laga yang dilaporkan (wajib bila file berisi lebih "
        "dari satu laga dengan artefak nba_analysis)",
    )
    p_laporan.add_argument(
        "--recheck",
        default=None,
        help="file laporan nba_recheck untuk dilampirkan (opsional)",
    )
    p_laporan.add_argument(
        "--out",
        default=None,
        help="file output (default: cetak ke stdout)",
    )
    p_laporan.add_argument(
        "--json", action="store_true", help="keluarkan JSON, bukan teks"
    )
    p_laporan.set_defaults(func=cmd_laporan)

    p_tanya = sub.add_parser(
        "tanya",
        help="tanya-jawab soal satu laga NBA (Tahap 3 Langkah 3)",
    )
    p_tanya.add_argument(
        "--analysis",
        required=True,
        help="file JSON analisis: artefak nba_analysis langsung, atau "
        "output cli.py analyze",
    )
    p_tanya.add_argument(
        "--match",
        default=None,
        help="match_id laga yang ditanya (wajib bila file berisi lebih "
        "dari satu laga dengan artefak nba_analysis)",
    )
    p_tanya.add_argument("pertanyaan", help="pertanyaan dalam Bahasa Indonesia")
    p_tanya.set_defaults(func=cmd_tanya)

    p_racik = sub.add_parser(
        "racik",
        help="racik Tiket Asuransi + Utama dari satu slate NBA " "(Tahap 3 Langkah 3)",
    )
    p_racik.add_argument(
        "--analysis",
        required=True,
        nargs="+",
        help="file JSON analisis (artefak nba_analysis atau output "
        "analyze), boleh banyak",
    )
    p_racik.add_argument(
        "--recheck",
        default=None,
        nargs="+",
        help="file laporan nba_recheck, boleh banyak (opsional)",
    )
    p_racik.add_argument(
        "--stake-total",
        required=True,
        type=float,
        help="total modal kedua tiket (USD) — wajib",
    )
    p_racik.add_argument(
        "--out",
        default=None,
        help="file output JSON (default: out/tickets_<tanggal>.json)",
    )
    p_racik.set_defaults(func=cmd_racik)

    p_log = sub.add_parser("log", help="catat / selesaikan tiket (Tahap 1)")
    p_log.add_argument("--file", help="file ticket.json (sesuai skema)")
    p_log.add_argument("--settle", metavar="TICKET_ID", help="selesaikan tiket PENDING")
    p_log.add_argument(
        "--result",
        choices=["WIN", "LOSS", "PUSH", "VOID", "CASHOUT"],
        help="hasil untuk --settle",
    )
    p_log.add_argument(
        "--cashout-amount",
        type=float,
        default=None,
        help="jumlah cashout USD (wajib bila --result CASHOUT)",
    )
    p_log.add_argument(
        "--leg-result",
        action="append",
        default=None,
        metavar="LEG_ID=HASIL",
        help="hasil per kaki, boleh diulang: --leg-result leg-01=WIN",
    )
    _db_arg(p_log)
    p_log.set_defaults(func=cmd_log)

    p_recap = sub.add_parser("recap", help="rekap untung/rugi (Tahap 1)")
    p_recap.add_argument(
        "--json", action="store_true", help="keluarkan JSON, bukan teks"
    )
    _db_arg(p_recap)
    p_recap.set_defaults(func=cmd_recap)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Titik masuk CLI; mengembalikan exit code (0 sukses, 1 error, 2 belum tersedia)."""
    args = build_parser().parse_args(argv)
    if args.command == "log" and args.settle and not args.result:
        print(
            "error: --settle butuh --result WIN|LOSS|PUSH|VOID|CASHOUT", file=sys.stderr
        )
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
