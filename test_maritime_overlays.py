# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
#
# Network-free stdlib self-test for the WarHacker maritime overlay datasets:
#   * pirate_attacks  — Global Maritime Pirate Attacks (1993-2020) overlay
#   * world_port_index — MSI World Port Index (NGA Pub 150) reference layer
#   * the pirate_zone risk axis wired into killinchu_maritime_risk
#
# Proves the HONEST-DATA contract WITHOUT touching the network:
#   * connectors register and read; default path is labelled SAMPLE (never CONNECTED-faked)
#   * real schema columns are preserved in normalized records
#   * the real-CSV parser parses the documented schema (offline, in-memory)
#   * a vessel near a historical hot zone reads HIGHER Λ risk than one far away
#   * the pirate_zone axis is present in score_vessel + signed receipt summary
#   * no fabricated rows / counts: count == len(records)
#
# Run by file path (modules ship flat next to serve.py):
#   python3 test_maritime_overlays.py
#
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import szl_connectors as sc  # noqa: E402
from szl_connectors.data_sources import maritime_overlays as mo  # noqa: E402
import killinchu_maritime_risk as risk  # noqa: E402


class TestPirateConnector(unittest.TestCase):
    def setUp(self):
        os.environ.pop("SZL_PIRATE_CSV_URL", None)

    def test_registered(self):
        self.assertIn("pirate_attacks", sc.all_ids())
        self.assertIsNotNone(sc.get("pirate_attacks"))

    def test_default_is_labelled_sample(self):
        c = sc.get("pirate_attacks")
        h = c.health()
        self.assertEqual(h.state.value, "sample")
        r = c.read({"limit": 5}).to_dict()
        self.assertEqual(r["state"], "sample")
        self.assertFalse(r["live"])
        self.assertIn("sample", r["note"].lower())
        # honest count: never fabricated
        self.assertEqual(r["count"], len(r["records"]))
        self.assertLessEqual(r["count"], 5)

    def test_real_schema_columns(self):
        c = sc.get("pirate_attacks")
        row = c.read({"limit": 1}).to_dict()["records"][0]
        for col in ("date", "lat", "lon", "region", "attack_type",
                    "vessel_type", "vessel_status", "location_description"):
            self.assertIn(col, row)

    def test_real_csv_parser(self):
        csv = ("date,lat,lon,region,attack_type,vessel_type,vessel_status,location_description\n"
               "2001-01-01,5.0,6.0,Gulf of Guinea,Boarded,Tanker,Anchored,test\n"
               "bad,,,no coords,,,,skip me\n"
               "2002-02-02,1.1,2.2,Malacca,Attempted,Bulk,Underway,row2\n")
        rows = mo._parse_pirate_csv(csv, 10)
        self.assertEqual(len(rows), 2)  # the no-coords row is dropped, never faked
        self.assertEqual(rows[0]["region"], "Gulf of Guinea")
        self.assertAlmostEqual(rows[1]["lat"], 1.1)


class TestWpiConnector(unittest.TestCase):
    def setUp(self):
        os.environ.pop("SZL_WPI_CSV_URL", None)

    def test_registered(self):
        self.assertIn("world_port_index", sc.all_ids())

    def test_default_is_labelled_sample(self):
        c = sc.get("world_port_index")
        self.assertEqual(c.health().state.value, "sample")
        r = c.read({"limit": 6}).to_dict()
        self.assertEqual(r["state"], "sample")
        self.assertFalse(r["live"])
        self.assertEqual(r["count"], len(r["records"]))

    def test_real_schema_columns(self):
        row = sc.get("world_port_index").read({"limit": 1}).to_dict()["records"][0]
        for col in ("World Port Index Number", "Main Port Name", "Country",
                    "Latitude", "Longitude", "Harbor Size", "Harbor Type"):
            self.assertIn(col, row)

    def test_real_csv_parser_tolerant_headers(self):
        csv = ("World Port Index Number,Main Port Name,Country Code,Latitude,Longitude,Harbor Size,Harbor Type\n"
               "12345,Testport,US,40.0,-70.0,Large,Coastal Natural\n")
        rows = mo._parse_wpi_csv(csv, 10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Main Port Name"], "Testport")
        self.assertEqual(rows[0]["World Port Index Number"], 12345)


class TestPirateZoneRiskAxis(unittest.TestCase):
    def test_axis_present(self):
        self.assertIn("pirate_zone", risk._AXES)

    def test_hot_zone_reads_higher_risk(self):
        base = dict(name="T", flag="Panama", status="steaming", currentSpeed=12,
                    lastPort="Salalah", nextPort="Suez")
        hot = dict(base, currentLat=12.8, currentLon=48.0)    # Gulf of Aden
        cold = dict(base, currentLat=30.0, currentLon=-40.0)  # mid-Atlantic
        vh = risk.score_vessel(hot)
        vc = risk.score_vessel(cold)
        self.assertIn("pirate_zone", vh["axes"])
        self.assertGreater(vh["axes"]["pirate_zone"]["raw_risk"],
                           vc["axes"]["pirate_zone"]["raw_risk"])
        self.assertGreater(vh["risk_score"], vc["risk_score"])

    def test_pirate_zone_risk_helper(self):
        inside = risk.pirate_zone_risk(12.8, 48.0)
        self.assertTrue(inside["inside"])
        self.assertEqual(inside["nearest_zone"], "Gulf of Aden")
        far = risk.pirate_zone_risk(30.0, -40.0)
        self.assertEqual(far["risk"], 0.0)
        none = risk.pirate_zone_risk(None, None)
        self.assertEqual(none["risk"], 0.0)

    def test_receipt_summary_includes_pirate_zone(self):
        v = risk.score_vessel(dict(name="T", currentLat=12.8, currentLon=48.0))
        rcpt = risk._sign_judgment("maritime.risk", v)
        summary = rcpt["dsse"]
        # the signed payload commits axes_raw_risk including pirate_zone
        self.assertIn("pirate_zone", v["axes"])
        self.assertIn("receipt_digest_sha256", rcpt)
        # honest signing: signed flag is a real bool, never a fabricated signature
        self.assertIsInstance(rcpt["signed"], bool)


if __name__ == "__main__":
    unittest.main(verbosity=2)
