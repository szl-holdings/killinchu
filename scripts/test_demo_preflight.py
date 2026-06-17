#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
#
# Network-free unit tests for scripts/demo_preflight.py.
#
# Covers the pure logic only (no HTTP): verdict classification (the honesty
# gate), content sanity checks, exit-code computation, and table rendering.
#
#   python3 scripts/test_demo_preflight.py
#
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo_preflight as dp  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_2xx_with_good_content_is_green(self):
        v, _ = dp.classify(200, True, "ok", None)
        self.assertEqual(v, dp.GREEN)

    def test_2xx_with_bad_content_is_red_not_green(self):
        # Doctrine v11: a 200 with the wrong shape is NEVER green.
        v, detail = dp.classify(200, False, "wrong shape", None)
        self.assertEqual(v, dp.RED)
        self.assertIn("content check failed", detail)

    def test_404_on_pending_route_is_pending(self):
        v, detail = dp.classify(404, False, "", pending_pr=133)
        self.assertEqual(v, dp.PENDING)
        self.assertIn("#133", detail)

    def test_404_without_pending_is_red(self):
        v, _ = dp.classify(404, False, "missing", None)
        self.assertEqual(v, dp.RED)

    def test_500_on_pending_route_still_red(self):
        # Only 404/405 mean "not merged yet". A 500 is a real failure.
        v, _ = dp.classify(500, False, "boom", pending_pr=133)
        self.assertEqual(v, dp.RED)

    def test_transport_error_is_red(self):
        v, detail = dp.classify(None, False, "transport error: timed out", None)
        self.assertEqual(v, dp.RED)
        self.assertIn("transport", detail)

    def test_pending_route_that_is_actually_live_is_green(self):
        # If a pending route returns 200 + valid content, it's merged → verify real.
        v, _ = dp.classify(200, True, "ok", pending_pr=132)
        self.assertEqual(v, dp.GREEN)


class TestContentChecks(unittest.TestCase):
    def test_cot_xml_valid_single_event(self):
        xml = (b'<event uid="v1" type="a-f-S-X-M">'
               b'<point lat="40.1" lon="-70.2" hae="0" ce="9" le="9"/></event>')
        ok, detail = dp.check_cot_xml(200, xml, {})
        self.assertTrue(ok)
        self.assertIn("uid=v1", detail)

    def test_cot_xml_batch_events_wrapper(self):
        xml = (b'<events count="2">'
               b'<event uid="a"><point lat="1" lon="2"/></event>'
               b'<event uid="b"><point lat="3" lon="4"/></event></events>')
        ok, _ = dp.check_cot_xml(200, xml, {})
        self.assertTrue(ok)

    def test_cot_xml_missing_point_is_rejected(self):
        ok, detail = dp.check_cot_xml(200, b'<event uid="x"></event>', {})
        self.assertFalse(ok)
        self.assertIn("no <point>", detail)

    def test_cot_xml_malformed_is_rejected_not_raised(self):
        ok, detail = dp.check_cot_xml(200, b'<event uid="x"><point ', {})
        self.assertFalse(ok)
        self.assertIn("not well-formed", detail)

    def test_has_vessels_counts_list_key(self):
        body = b'{"vessels": [{"mmsi": 1}, {"mmsi": 2}], "source": "noaa"}'
        ok, detail = dp.check_has_vessels(200, body, {})
        self.assertTrue(ok)
        self.assertIn("2 vessels", detail)

    def test_has_vessels_empty_list_is_red(self):
        ok, detail = dp.check_has_vessels(200, b'{"tracks": []}', {})
        self.assertFalse(ok)
        self.assertIn("EMPTY", detail)

    def test_has_vessels_top_level_array(self):
        ok, _ = dp.check_has_vessels(200, b'[1, 2, 3]', {})
        self.assertTrue(ok)

    def test_has_vessels_no_list_is_red(self):
        ok, _ = dp.check_has_vessels(200, b'{"status": "ok"}', {})
        self.assertFalse(ok)

    def test_has_vessels_bad_json_is_red_not_raised(self):
        ok, detail = dp.check_has_vessels(200, b'not json', {})
        self.assertFalse(ok)
        self.assertIn("not JSON", detail)

    def test_healthz_ok(self):
        ok, _ = dp.check_healthz(200, b'{"status": "ok", "service": "killinchu"}', {})
        self.assertTrue(ok)

    def test_healthz_bad_status(self):
        ok, _ = dp.check_healthz(200, b'{"status": "degraded"}', {})
        self.assertFalse(ok)

    def test_json_has_keys(self):
        chk = dp.check_json_has(("live", "roadmap"))
        ok, _ = chk(200, b'{"live": {}, "roadmap": {}}', {})
        self.assertTrue(ok)
        ok2, detail = chk(200, b'{"live": {}}', {})
        self.assertFalse(ok2)
        self.assertIn("roadmap", detail)

    def test_receipt_ledger_populated_ok(self):
        body = b'{"khipu_root": "abc123", "count": 1, "nodes": [{"index": 0}]}'
        ok, detail = dp.check_receipt_ledger(200, body, {})
        self.assertTrue(ok)
        self.assertIn("abc123", detail)

    def test_receipt_ledger_empty_is_honest_green(self):
        # In-memory DAG resets on Space restart; an empty well-formed ledger is
        # the honest state, not a failure.
        body = b'{"khipu_root": null, "count": 0, "nodes": []}'
        ok, detail = dp.check_receipt_ledger(200, body, {})
        self.assertTrue(ok)
        self.assertIn("empty", detail)

    def test_receipt_ledger_missing_envelope_is_red(self):
        ok, _ = dp.check_receipt_ledger(200, b'{"count": 0}', {})
        self.assertFalse(ok)

    def test_receipt_ledger_count_mismatch_is_red(self):
        # count says 5 but nodes is empty → fabrication tell, must be RED.
        body = b'{"khipu_root": "x", "count": 5, "nodes": []}'
        ok, detail = dp.check_receipt_ledger(200, body, {})
        self.assertFalse(ok)
        self.assertIn("fabrication tell", detail)

    def test_elite_board_html(self):
        ok, _ = dp.check_elite_board(200, b'<!DOCTYPE html><html><body>killinchu</body></html>', {})
        self.assertTrue(ok)

    def test_elite_board_non_html_rejected(self):
        ok, _ = dp.check_elite_board(200, b'{"json": true}', {})
        self.assertFalse(ok)

    def test_pem_check(self):
        ok, _ = dp.check_pem(200, b'-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----', {})
        self.assertTrue(ok)
        ok2, _ = dp.check_pem(200, b'not a key', {})
        self.assertFalse(ok2)


class TestExitAndTable(unittest.TestCase):
    def _result(self, name, verdict, status=200):
        return dp.ProbeResult(name=name, method="GET", path="/" + name,
                              status=status, verdict=verdict, detail="d")

    def test_required_red_blocks_demo(self):
        probes = [dp.Probe("a", "/a", lambda *x: (True, ""), required=True)]
        results = [self._result("a", dp.RED, status=500)]
        ready, n = dp.compute_exit(results, probes)
        self.assertFalse(ready)
        self.assertEqual(n, 1)

    def test_optional_red_does_not_block(self):
        probes = [dp.Probe("a", "/a", lambda *x: (True, ""), required=False)]
        results = [self._result("a", dp.RED, status=500)]
        ready, n = dp.compute_exit(results, probes)
        self.assertTrue(ready)
        self.assertEqual(n, 0)

    def test_pending_never_blocks(self):
        probes = [dp.Probe("a", "/a", lambda *x: (True, ""), pending_pr=133, required=False)]
        results = [self._result("a", dp.PENDING, status=404)]
        ready, n = dp.compute_exit(results, probes)
        self.assertTrue(ready)
        self.assertEqual(n, 0)

    def test_render_table_contains_states_and_paths(self):
        results = [
            self._result("elite", dp.GREEN),
            self._result("cot", dp.PENDING, status=404),
            self._result("bad", dp.RED, status=500),
        ]
        table = dp.render_table(results, use_color=False)
        self.assertIn("SURFACE", table)
        self.assertIn("/elite", table)
        self.assertIn("GREEN", table)
        self.assertIn("PEND", table)
        self.assertIn("RED", table)

    def test_render_table_err_for_no_status(self):
        results = [dp.ProbeResult("x", "GET", "/x", None, dp.RED, "transport error")]
        table = dp.render_table(results, use_color=False)
        self.assertIn("ERR", table)

    def test_summarize_counts(self):
        results = [
            self._result("a", dp.GREEN),
            self._result("b", dp.GREEN),
            self._result("c", dp.RED, status=500),
            self._result("d", dp.PENDING, status=404),
        ]
        s = dp.summarize(results)
        self.assertEqual(s["counts"][dp.GREEN], 2)
        self.assertEqual(s["counts"][dp.RED], 1)
        self.assertEqual(s["counts"][dp.PENDING], 1)
        self.assertEqual(s["total"], 4)


class TestCatalogue(unittest.TestCase):
    def test_probes_build_and_have_unique_names(self):
        probes = dp.build_probes()
        self.assertGreater(len(probes), 10)
        names = [p.name for p in probes]
        self.assertEqual(len(names), len(set(names)), "probe names must be unique")

    def test_new_endpoints_are_marked_pending(self):
        probes = {p.name: p for p in dp.build_probes()}
        self.assertEqual(probes["CoT export (all tracks)"].pending_pr, 132)
        self.assertEqual(probes["AIS Aug-2024 tracks"].pending_pr, 133)
        self.assertEqual(probes["pirate-attacks overlay"].pending_pr, 134)

    def test_core_surfaces_are_required(self):
        probes = {p.name: p for p in dp.build_probes()}
        self.assertTrue(probes["elite track board"].required)
        self.assertTrue(probes["health"].required)


if __name__ == "__main__":
    unittest.main(verbosity=2)
