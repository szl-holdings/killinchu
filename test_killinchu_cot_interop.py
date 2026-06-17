# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
#
# Network-free stdlib self-test for killinchu_cot_interop.py.
#
# Proves the CoT interop contract WITHOUT any socket / TAK server:
#   * vessel/drone/threat -> CoT event dict has every required W3 field
#   * CoT type-atom resolution (friendly surface / friendly UAS / hostile air)
#   * event dict -> XML produces a parseable <event> with point lat/lon/hae/ce/le
#   * schema-shape validation accepts good events, rejects malformed ones
#   * round-trip: track -> CoT XML -> ingest -> track preserves W3
#   * batch <events> wrapper validates per-child
#   * status manifest is honest (live flags true, roadmap flags false)
#
# Run by file path (the module is shipped flat next to serve.py):
#   python3 test_killinchu_cot_interop.py
#
import os
import sys
import unittest
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import killinchu_cot_interop as cot  # noqa: E402


_VESSEL = {
    "id": 1, "name": "CONSTANTA SPIRIT", "imo": "9732847", "mmsi": "264700100",
    "vesselType": "bulk", "flag": "Romania", "currentLat": 43.18, "currentLon": 28.59,
    "currentSpeed": 12.4, "currentHeading": 195, "lastPort": "Constanta", "nextPort": "Istanbul",
}
_DRONE = {
    "id": "KLN-F001", "callsign": "KESTREL-1", "type": "DJI Matrice 350 RTK",
    "role": "ISR", "status": "PATROL", "lat": 37.4275, "lon": -122.1697,
    "alt_m": 150, "speed_ms": 12.5, "battery_pct": 78, "remote_id": "FA:12:34:56:78:01",
}
_THREAT = {
    "track_id": "THR-001", "type": "UNKNOWN-UAS", "lat": 37.4250, "lon": -122.1750,
    "alt_m": 85, "speed_ms": 5.2, "lambda_score": 0.41,
    "lambda_verdict": "THREAT — Λ below floor 0.87", "threat_category": "GEOFENCE_VIOLATION",
    "cuing_sensor": "RF_DETECT/Hawkeye-3",
}


class TestCoTEventBuild(unittest.TestCase):
    def _assert_w3(self, ev):
        for k in ("version", "uid", "type", "time", "start", "stale", "point", "detail"):
            self.assertIn(k, ev)
        for k in ("lat", "lon", "hae", "ce", "le"):
            self.assertIn(k, ev["point"])
        # CoT stamps must be ISO-8601 UTC with Z.
        for k in ("time", "start", "stale"):
            self.assertTrue(ev[k].endswith("Z"), f"{k} not Z-suffixed: {ev[k]}")

    def test_vessel_event(self):
        ev = cot.vessel_to_cot(_VESSEL)
        self._assert_w3(ev)
        self.assertEqual(ev["type"], "a-f-S-X-M")  # friendly surface vessel
        self.assertTrue(ev["uid"].endswith("264700100"))
        self.assertAlmostEqual(ev["point"]["lat"], 43.18, places=4)

    def test_friendly_drone_event(self):
        ev = cot.friendly_drone_to_cot(_DRONE)
        self._assert_w3(ev)
        self.assertEqual(ev["type"], "a-f-A-M-F-Q")  # friendly UAS
        self.assertEqual(ev["point"]["hae"], 150.0)

    def test_threat_event_hostile(self):
        ev = cot.threat_to_cot(_THREAT)
        self._assert_w3(ev)
        # THREAT verdict -> hostile affiliation atom (a-h-...).
        self.assertTrue(ev["type"].startswith("a-h-A"), ev["type"])

    def test_threat_event_unknown(self):
        suspect = dict(_THREAT, lambda_verdict="SUSPECT — Λ below threshold 0.87")
        ev = cot.threat_to_cot(suspect)
        self.assertTrue(ev["type"].startswith("a-u-A"), ev["type"])


class TestCoTXml(unittest.TestCase):
    def test_event_to_xml_parseable(self):
        ev = cot.vessel_to_cot(_VESSEL)
        xml = cot.event_to_xml_string(ev)
        self.assertIn("<?xml", xml)
        root = ET.fromstring(xml.split("?>", 1)[1])
        self.assertEqual(root.tag, "event")
        pt = root.find("point")
        self.assertIsNotNone(pt)
        for attr in ("lat", "lon", "hae", "ce", "le"):
            self.assertIsNotNone(pt.get(attr))

    def test_events_wrapper_counts(self):
        evs = [cot.vessel_to_cot(_VESSEL), cot.friendly_drone_to_cot(_DRONE)]
        xml = cot.events_to_xml_string(evs)
        root = ET.fromstring(xml.split("?>", 1)[1])
        self.assertEqual(root.tag, "events")
        self.assertEqual(root.get("count"), "2")
        self.assertEqual(len(root.findall("event")), 2)


class TestCoTValidation(unittest.TestCase):
    def test_valid_event_passes(self):
        for builder, src in [
            (cot.vessel_to_cot, _VESSEL),
            (cot.friendly_drone_to_cot, _DRONE),
            (cot.threat_to_cot, _THREAT),
        ]:
            ok, errs = cot.validate_event(builder(src))
            self.assertTrue(ok, f"{builder.__name__} errors: {errs}")

    def test_missing_uid_rejected(self):
        ev = cot.vessel_to_cot(_VESSEL)
        del ev["uid"]
        # build XML manually missing uid
        el = ET.Element("event")
        for a in ("version", "type", "time", "start", "stale"):
            el.set(a, str(ev[a]))
        p = ET.SubElement(el, "point")
        for a in ("lat", "lon", "hae", "ce", "le"):
            p.set(a, str(ev["point"][a]))
        errs = cot.validate_event_element(el)
        self.assertTrue(any("uid" in e for e in errs), errs)

    def test_bad_lat_rejected(self):
        ev = cot.vessel_to_cot(_VESSEL)
        ev["point"]["lat"] = 999.0
        ok, errs = cot.validate_event(ev)
        self.assertFalse(ok)
        self.assertTrue(any("lat" in e for e in errs), errs)

    def test_bad_type_atom_rejected(self):
        xml = '<event version="2.0" uid="x" type="NOTATOM" time="2026-01-01T00:00:00Z" ' \
              'start="2026-01-01T00:00:00Z" stale="2026-01-01T00:02:00Z">' \
              '<point lat="1" lon="2" hae="0" ce="9" le="9"/></event>'
        ok, errs = cot.validate_xml_string(xml)
        self.assertFalse(ok)
        self.assertTrue(any("atom" in e for e in errs), errs)

    def test_parse_error_rejected(self):
        ok, errs = cot.validate_xml_string("<event><point></event>")
        self.assertFalse(ok)
        self.assertTrue(any("parse" in e.lower() for e in errs), errs)


class TestCoTIngestRoundTrip(unittest.TestCase):
    def test_round_trip_vessel(self):
        ev = cot.vessel_to_cot(_VESSEL)
        xml = cot.event_to_xml_string(ev)
        track = cot.cot_xml_to_track(xml)
        self.assertEqual(track["track_id"], ev["uid"])
        self.assertEqual(track["cot_type"], "a-f-S-X-M")
        self.assertEqual(track["affiliation"], "friendly")
        self.assertAlmostEqual(track["lat"], 43.18, places=4)
        self.assertAlmostEqual(track["lon"], 28.59, places=4)
        self.assertEqual(track["callsign"], "CONSTANTA SPIRIT")
        self.assertEqual(track["source"], "cot_ingest")

    def test_round_trip_threat_hostile(self):
        ev = cot.threat_to_cot(_THREAT)
        track = cot.cot_xml_to_track(cot.event_to_xml_string(ev))
        self.assertEqual(track["affiliation"], "hostile")
        self.assertAlmostEqual(track["alt_m"], 85.0, places=3)

    def test_ingest_rejects_non_event(self):
        with self.assertRaises(ValueError):
            cot.cot_xml_to_track("<notevent/>")

    def test_ingest_rejects_invalid_event(self):
        with self.assertRaises(ValueError):
            cot.cot_xml_to_track('<event uid="x"><point lat="1" lon="2"/></event>')


class TestCoTStatusHonesty(unittest.TestCase):
    def test_status_live_and_roadmap(self):
        st = cot.cot_status()
        # LIVE capabilities are true.
        self.assertTrue(st["live"]["cot_xml_export"])
        self.assertTrue(st["live"]["schema_shape_validation"])
        self.assertTrue(st["live"]["cot_xml_ingest"])
        # ROADMAP transports are explicitly NOT wired (honest).
        self.assertFalse(st["roadmap"]["udp_multicast_emit"]["wired"])
        self.assertFalse(st["roadmap"]["live_tak_server_stream"]["wired"])
        self.assertIn("roadmap", st["roadmap"]["udp_multicast_emit"]["note"].lower())

    def test_collect_events_all_valid(self):
        evs = cot.collect_cot_events()
        # collect must yield at least the embedded vessels.
        self.assertGreater(len(evs), 0)
        for ev in evs:
            ok, errs = cot.validate_event(ev)
            self.assertTrue(ok, f"{ev['uid']} invalid: {errs}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
