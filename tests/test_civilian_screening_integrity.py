"""Hermetic civilian compliance regressions; no operational action authority."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import killinchu_vessels_screening as vs
import killinchu_public_source_fabric as psf


class ScreeningIntegrity(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(vs._LISTS)
        vs._LISTS.clear()
        self.clock = mock.patch("time.time", return_value=100000)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        vs._LISTS.clear()
        vs._LISTS.update(self.saved)

    def source(self, source_id):
        return dict(source_id=source_id, mode="CACHED", fetched_epoch=100000,
                    content_sha256="a" * 64, items=[dict(names=["Example Entity"])])

    def screen(self, sources, query="Unlisted Example"):
        with mock.patch.object(psf, "fetch_source", side_effect=sources):
            return psf.screen_sanctions(query)

    def test_empty_loaded_list_does_not_clear(self):
        vs.load_screening_list("empty", [])
        self.assertEqual(vs.screen_entity("Example")["result"], "BLOCKED_PENDING")

    def test_loaded_clock_is_fail_closed(self):
        for timestamp in (None, True, float("nan"), float("inf"), 100001, 78399):
            with self.subTest(timestamp=timestamp):
                vs.load_screening_list("list", ["Other Entity"])
                vs._LISTS["list"]["loaded_ts"] = timestamp
                self.assertEqual(vs.screen_entity("Example")["result"], "BLOCKED_PENDING")

    def test_fresh_miss_is_only_loaded_list_comparison(self):
        vs.load_screening_list("list", ["Other Entity"])
        result = vs.screen_entity("Example")
        self.assertEqual(result["result"], "NO_EXACT_MATCH")
        self.assertEqual(result["coverage_scope"], "LOADED_LISTS_ONLY")
        self.assertTrue(result["manual_review_required"])
        self.assertEqual(result["action_authority"], "NONE")

    def test_malformed_entries_are_rejected_before_replacing_valid_list(self):
        vs.load_screening_list("list", ["Example Entity"])
        for entries in ("Example", [None], [2]):
            with self.assertRaises(ValueError):
                vs.load_screening_list("list", entries)
        self.assertEqual(vs.screen_entity("Example Entity")["result"], "HIT")
        self.assertEqual(vs.screen_entity(2)["result"], "BLOCKED_PENDING")

    def test_incomplete_official_source_blocks_negative_claim(self):
        for field, value in (("items", []), ("items", [None]), ("items", [dict(names=[2])]),
                             ("fetched_epoch", None), ("fetched_epoch", True),
                             ("fetched_epoch", float("nan")), ("fetched_epoch", 78399),
                             ("fetched_epoch", 100001), ("content_sha256", None),
                             ("mode", "UNAVAILABLE")):
            with self.subTest(field=field, value=value):
                sources = [self.source("ofac-sdn"), self.source("un-dprk-1718")]
                sources[1][field] = value
                result = self.screen(sources)
                self.assertEqual(result["verdict"], "BLOCKED_PENDING")
                self.assertEqual(result["coverage"], "PARTIAL")

    def test_duplicate_source_cannot_satisfy_full_coverage(self):
        result = self.screen([self.source("ofac-sdn"), self.source("ofac-sdn")])
        self.assertEqual(result["coverage"], "PARTIAL")
        self.assertEqual(result["verdict"], "BLOCKED_PENDING")

    def test_fresh_full_coverage_retains_manual_review(self):
        result = self.screen([self.source("ofac-sdn"), self.source("un-dprk-1718")])
        self.assertEqual(result["verdict"], "NO_EXACT_MATCH")
        self.assertEqual(result["coverage"], "FULL")
        self.assertTrue(result["manual_review_required"])
        self.assertEqual(result["action_authority"], "NONE")

    def test_stale_positive_candidate_is_preserved_for_review(self):
        sources = [self.source("ofac-sdn"), self.source("un-dprk-1718")]
        sources[0]["fetched_epoch"] = 0
        sources[1]["items"] = []
        result = self.screen(sources, "Example Entity")
        self.assertEqual(result["coverage"], "NONE")
        self.assertEqual(result["verdict"], "POSSIBLE_MATCH")
        self.assertTrue(result["matches"])
        self.assertTrue(result["manual_review_required"])


if __name__ == "__main__":
    unittest.main()
