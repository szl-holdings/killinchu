#!/usr/bin/env python3
"""Self-test for evaluate() in check_killinchu_api_health.py.

Proves the checker actually catches the regressions it claims to catch:
SPA-HTML-instead-of-JSON (200 but text/html), non-200, unparseable body, a
non-object payload, and a missing Doctrine v11 envelope field — and that it
accepts a valid envelope. Stdlib unittest, no network. Guards the validator so
a future edit can't silently neuter the health check.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_killinchu_api_health import evaluate  # noqa: E402

ENVELOPE = ["status", "citations", "fetchedAt"]
GOOD = json.dumps(
    {
        "status": "ok",
        "doctrine": "v11",
        "service": "killinchu",
        "citations": [],
        "fetchedAt": "2026-06-09T00:00:00+00:00",
        "watchlists": [],
        "count": 0,
    }
).encode("utf-8")
SPA_HTML = b"<!doctype html><html><head><title>killinchu</title></head><body></body></html>"


class EvaluateTests(unittest.TestCase):
    def test_valid_envelope_passes(self):
        ok, reason = evaluate(200, "application/json", GOOD, ENVELOPE)
        self.assertTrue(ok, reason)

    def test_valid_with_charset_suffix_passes(self):
        ok, reason = evaluate(200, "application/json; charset=utf-8", GOOD, ENVELOPE)
        self.assertTrue(ok, reason)

    def test_spa_html_200_fails(self):
        ok, reason = evaluate(200, "text/html; charset=utf-8", SPA_HTML, ENVELOPE)
        self.assertFalse(ok)
        self.assertIn("not application/json", reason)

    def test_non_200_fails(self):
        ok, reason = evaluate(503, "application/json", GOOD, ENVELOPE)
        self.assertFalse(ok)
        self.assertIn("503", reason)

    def test_unparseable_json_fails(self):
        ok, reason = evaluate(200, "application/json", b"{not json", ENVELOPE)
        self.assertFalse(ok)
        self.assertIn("not valid JSON", reason)

    def test_non_object_json_fails(self):
        ok, reason = evaluate(200, "application/json", b"[1,2,3]", ENVELOPE)
        self.assertFalse(ok)
        self.assertIn("not an object", reason)

    def test_missing_envelope_field_fails(self):
        body = json.dumps({"status": "ok", "citations": []}).encode("utf-8")  # no fetchedAt
        ok, reason = evaluate(200, "application/json", body, ENVELOPE)
        self.assertFalse(ok)
        self.assertIn("fetchedAt", reason)

    def test_healthz_minimal_status_passes(self):
        body = json.dumps({"status": "ok", "organ": "killinchu"}).encode("utf-8")
        ok, reason = evaluate(200, "application/json", body, ["status"])
        self.assertTrue(ok, reason)

    def test_healthz_missing_status_fails(self):
        body = json.dumps({"organ": "killinchu"}).encode("utf-8")
        ok, reason = evaluate(200, "application/json", body, ["status"])
        self.assertFalse(ok)
        self.assertIn("status", reason)

    # --- /elite Research & Sources tab contracts (own shape, no v11 envelope) --
    def test_research_contract_passes(self):
        body = json.dumps(
            {"honest": True, "source_pool": [], "tabs_with_overrides": [], "layer": "x"}
        ).encode("utf-8")
        ok, reason = evaluate(
            200, "application/json", body, ["honest", "source_pool", "tabs_with_overrides"]
        )
        self.assertTrue(ok, reason)

    def test_research_missing_honest_flag_fails(self):
        body = json.dumps({"source_pool": [], "tabs_with_overrides": []}).encode("utf-8")
        ok, reason = evaluate(
            200, "application/json", body, ["honest", "source_pool", "tabs_with_overrides"]
        )
        self.assertFalse(ok)
        self.assertIn("honest", reason)

    def test_research_live_contract_passes(self):
        body = json.dumps(
            {"honest": True, "tab": "default", "sources": [], "summary": "x"}
        ).encode("utf-8")
        ok, reason = evaluate(200, "application/json", body, ["honest", "tab", "sources"])
        self.assertTrue(ok, reason)

    def test_research_live_missing_sources_fails(self):
        body = json.dumps({"honest": True, "tab": "default"}).encode("utf-8")
        ok, reason = evaluate(200, "application/json", body, ["honest", "tab", "sources"])
        self.assertFalse(ok)
        self.assertIn("sources", reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
