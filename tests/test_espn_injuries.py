"""Tes cedera NBA ESPN (ingest/espn.py) — TANPA network.

Semua tes memakai fixture tests/fixtures/espn_injuries_nba_2026-11-22.json
— tangkapan respons live ESPN SEKALI (22 Nov 2026, dipangkas ke 7 tim,
31 entri; lihat _meta di file fixture). Tidak ada panggilan live di
tes ini. Kasus uji nyata dari fixture: konflik status-vs-komentar
(Holland, Flemings, Nelson, ...), entri non-cedera (Onyenso two-way,
Saunders two-way, Tatum rest, Small personal), illness (Robinson,
Towns).
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import espn

FIXTURE_PATH = Path(__file__).resolve().parent / (
    "fixtures/espn_injuries_nba_2026-11-22.json"
)


class FakeClient:
    """Client palsu: get() mengembalikan respons yang sudah disiapkan."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.urls_requested: list[str] = []

    def get(self, url: str, use_cache: bool = True) -> dict:
        """Kembalikan respons untuk URL (default: 404)."""
        self.urls_requested.append(url)
        return self.responses.get(url, {"status": 404, "body": "", "error": None})


def _resp(status: int, body: object) -> dict:
    return {
        "status": status,
        "body": body if isinstance(body, str) else json.dumps(body),
        "error": None,
    }


def _muat_fixture() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _berdasarkan_nama(injuries: list[dict]) -> dict[str, dict]:
    return {injury["player"]: injury for injury in injuries}


class TestParseFixture(unittest.TestCase):
    def test_jumlah_entri(self):
        injuries = espn.parse_injuries_nba(_muat_fixture())
        # 7 tim: ATL 6, BOS 3, BKN 2, CHA 4, DET 7, MEM 6, NYK 3.
        self.assertEqual(len(injuries), 31)

    def test_bentuk_entri(self):
        injuries = espn.parse_injuries_nba(_muat_fixture())
        for injury in injuries:
            for kunci in (
                "player",
                "team",
                "status",
                "detail",
                "status_normalized",
                "status_comment_conflict",
                "is_injury",
                "long_comment",
                "date",
                "source",
                "tier",
            ):
                self.assertIn(kunci, injury, injury.get("player"))
            self.assertEqual(injury["source"], "ESPN")
            self.assertEqual(injury["tier"], 2)
            self.assertIsInstance(injury["status_comment_conflict"], bool)
            self.assertIsInstance(injury["is_injury"], bool)

    def test_det_atl_lengkap(self):
        injuries = espn.parse_injuries_nba(_muat_fixture())
        det = [i for i in injuries if i["team"] == "Detroit Pistons"]
        atl = [i for i in injuries if i["team"] == "Atlanta Hawks"]
        self.assertEqual(len(det), 7)
        self.assertEqual(len(atl), 6)
        self.assertIn("Jalen Duren", [i["player"] for i in det])
        self.assertIn("CJ McCollum", [i["player"] for i in atl])

    def test_duren(self):
        injuries = _berdasarkan_nama(espn.parse_injuries_nba(_muat_fixture()))
        duren = injuries["Jalen Duren"]
        self.assertEqual(duren["team"], "Detroit Pistons")
        self.assertEqual(duren["status"], "Out")
        self.assertEqual(duren["status_normalized"], "OUT")
        self.assertNotIn("status_asli", duren)  # pemetaan eksak
        self.assertTrue(duren["is_injury"])
        self.assertFalse(duren["status_comment_conflict"])
        self.assertEqual(duren["date"], "2026-11-08T16:05Z")
        self.assertIn("hamstring", duren["detail"])

    def test_day_to_day_menyimpan_status_asli(self):
        injuries = _berdasarkan_nama(espn.parse_injuries_nba(_muat_fixture()))
        cunningham = injuries["Cade Cunningham"]
        self.assertEqual(cunningham["status"], "Day-To-Day")
        self.assertEqual(cunningham["status_normalized"], "QUESTIONABLE")
        self.assertEqual(cunningham["status_asli"], "Day-To-Day")


class TestNormalizeStatus(unittest.TestCase):
    def test_status_eksak(self):
        for raw, expected in (
            ("Out", "OUT"),
            ("DOUBTFUL", "DOUBTFUL"),
            ("Questionable", "QUESTIONABLE"),
            ("probable", "PROBABLE"),
            ("Available", "AVAILABLE"),
        ):
            status, asli = espn.normalize_injury_status(raw)
            self.assertEqual(status, expected, raw)
            self.assertIsNone(asli, raw)

    def test_status_perkiraan(self):
        for raw in ("Day-To-Day", "day to day", "GTD", "Game-Time Decision"):
            status, asli = espn.normalize_injury_status(raw)
            self.assertEqual(status, "QUESTIONABLE", raw)
            self.assertEqual(asli, raw)

    def test_status_tidak_dikenal(self):
        status, asli = espn.normalize_injury_status("UNKNOWN")
        self.assertIsNone(status)
        self.assertEqual(asli, "UNKNOWN")
        status, asli = espn.normalize_injury_status(None)
        self.assertIsNone(status)
        self.assertIsNone(asli)
        status, asli = espn.normalize_injury_status("  ")
        self.assertIsNone(status)
        self.assertIsNone(asli)


class TestKonflikStatusKomentar(unittest.TestCase):
    def test_konflik_dari_fixture(self):
        injuries = _berdasarkan_nama(espn.parse_injuries_nba(_muat_fixture()))
        # Out tapi komentar "questionable" (kasus Holland + Flemings).
        self.assertTrue(injuries["Ronald Holland II"]["status_comment_conflict"])
        self.assertTrue(injuries["Kingston Flemings"]["status_comment_conflict"])
        # Day-To-Day tapi komentar "ruled out"/"won't play"/"listed as out".
        for nama in (
            "Grant Nelson",
            "Grant Williams",
            "Grayson Allen",
            "Karl-Anthony Towns",
            "Jordan Clarkson",
            "OG Anunoby",
        ):
            self.assertTrue(injuries[nama]["status_comment_conflict"], nama)
        # Total 8 konflik dari 31 entri fixture.
        konflik = [i for i in injuries.values() if i["status_comment_conflict"]]
        self.assertEqual(len(konflik), 8)

    def test_bukan_konflik_dari_fixture(self):
        injuries = _berdasarkan_nama(espn.parse_injuries_nba(_muat_fixture()))
        # Out + "won't play" = konsisten.
        self.assertFalse(injuries["Jock Landale"]["status_comment_conflict"])
        # Day-To-Day + "probable" = masih dalam keluarga game-time decision.
        self.assertFalse(injuries["Cade Cunningham"]["status_comment_conflict"])
        # Day-To-Day + "won't return" (laga berjalan) bukan sinyal konflik.
        self.assertFalse(injuries["Nolan Traore"]["status_comment_conflict"])
        # Out + komentar cedera biasa.
        self.assertFalse(injuries["Jalen Duren"]["status_comment_conflict"])

    def test_pasangan_sintetis(self):
        konflik = espn._status_comment_conflict
        # PROBABLE/AVAILABLE + sinyal definitif tidak main -> konflik.
        self.assertTrue(konflik("PROBABLE", "Smith (ankle) has been ruled out."))
        self.assertTrue(konflik("AVAILABLE", "Jones will not play tonight."))
        # OUT + sinyal bisa-main -> konflik.
        self.assertTrue(konflik("OUT", "Doe is expected to play Sunday."))
        self.assertTrue(konflik("OUT", "Doe is likely to play Sunday."))
        # QUESTIONABLE + sinyal bisa-main BUKAN konflik.
        self.assertFalse(konflik("QUESTIONABLE", "Doe is probable to play."))
        # Status tidak dikenal -> tidak bisa dinilai, bukan konflik.
        self.assertFalse(konflik(None, "Doe has been ruled out."))
        # Komentar kosong -> bukan konflik.
        self.assertFalse(konflik("OUT", ""))


class TestBukanCedera(unittest.TestCase):
    def test_non_cedera_dari_fixture(self):
        injuries = _berdasarkan_nama(espn.parse_injuries_nba(_muat_fixture()))
        # Onyenso: Day-To-Day karena kontrak two-way (kasus di DECISIONS.md).
        self.assertFalse(injuries["Ugonna Onyenso"]["is_injury"])
        # Saunders: Out karena "signed a two-way contract".
        self.assertFalse(injuries["Richie Saunders"]["is_injury"])
        # Tatum: details.type "Rest" (load management, bukan cedera).
        self.assertFalse(injuries["Jayson Tatum"]["is_injury"])
        # Small: "personal reasons".
        self.assertFalse(injuries["Javon Small"]["is_injury"])
        # Total 4 entri non-cedera dari 31 entri fixture.
        non_cedera = [i for i in injuries.values() if not i["is_injury"]]
        self.assertEqual(len(non_cedera), 4)

    def test_cedera_dari_fixture(self):
        injuries = _berdasarkan_nama(espn.parse_injuries_nba(_muat_fixture()))
        # Illness DIHITUNG sebagai detail kesehatan.
        self.assertTrue(injuries["Mitchell Robinson"]["is_injury"])
        self.assertTrue(injuries["Karl-Anthony Towns"]["is_injury"])
        # Veesaar: "G League" hanya muncul di longComment (narasi) —
        # tidak boleh mengecualikan cedera ACL sungguhan.
        self.assertTrue(injuries["Henri Veesaar"]["is_injury"])
        # Cedera biasa.
        self.assertTrue(injuries["Jalen Duren"]["is_injury"])
        self.assertTrue(injuries["Cade Cunningham"]["is_injury"])

    def test_aturan_sintetis(self):
        is_injury = espn._is_injury_entry
        detail_kaki = {"type": "Knee", "detail": "Strain", "side": "Left"}
        # Probable dengan detail cedera TIDAK dihitung (hanya
        # Out/Doubtful/Questionable yang dihitung).
        self.assertFalse(is_injury("PROBABLE", "Doe (knee) is probable.", detail_kaki))
        # Out tanpa detail apa pun TIDAK dihitung.
        self.assertFalse(is_injury("OUT", "", {}))
        # Out + skorsing bukan cedera.
        self.assertFalse(
            is_injury("OUT", "Doe is suspended for one game.", detail_kaki)
        )
        # Out + penugasan G League bukan cedera.
        self.assertFalse(
            is_injury(
                "OUT",
                "Doe was assigned to the G League on Friday.",
                detail_kaki,
            )
        )
        # Doubtful + detail cedera DIHITUNG.
        self.assertTrue(is_injury("DOUBTFUL", "Doe (ankle) is doubtful.", detail_kaki))
        # Status tidak dikenal TIDAK dihitung.
        self.assertFalse(is_injury(None, "Doe (knee) is out.", detail_kaki))


class TestFetchInjuriesNba(unittest.TestCase):
    def test_fetch_memakai_fixture(self):
        fixture = _muat_fixture()
        client = FakeClient({espn.NBA_INJURIES_URL: _resp(200, fixture)})
        result = espn.fetch_injuries_nba(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "ESPN")
        self.assertEqual(result.tier, 2)
        self.assertEqual(len(result.data), 31)
        # Tiap entri membawa jam pengambilan.
        for injury in result.data:
            self.assertEqual(injury["time"], result.fetched_at)
        self.assertEqual(result.extra["n_injuries"], 31)
        self.assertEqual(result.extra["n_injury"], 27)
        self.assertEqual(result.extra["n_non_injury"], 4)
        self.assertEqual(client.urls_requested, [espn.NBA_INJURIES_URL])

    def test_fetch_http_gagal(self):
        result = espn.fetch_injuries_nba(client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")

    def test_parse_tanpa_injuries(self):
        with self.assertRaises(ValueError) as ctx:
            espn.parse_injuries_nba({})
        self.assertEqual(str(ctx.exception), "espn_format_changed")


if __name__ == "__main__":
    unittest.main()
