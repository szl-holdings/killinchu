import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_killinchu_public_contracts as probe


class ContractProbeTests(unittest.TestCase):
    def test_accepts_exact_typed_json(self):
        payload = {
            "schema": "szl.killinchu.health/v1",
            "authority_state": "READ_ONLY",
        }
        ok, reason = probe.evaluate(
            200,
            "application/json; charset=utf-8",
            json.dumps(payload).encode(),
            payload,
        )
        self.assertTrue(ok, reason)

    def test_rejects_spa_html_even_when_http_200(self):
        ok, reason = probe.evaluate(
            200,
            "text/html; charset=utf-8",
            b"<html>SPA</html>",
            {"schema": "szl.killinchu.health/v1"},
        )
        self.assertFalse(ok)
        self.assertIn("SPA", reason)

    def test_rejects_wrong_schema(self):
        ok, reason = probe.evaluate(
            200,
            "application/json",
            b'{"schema":"wrong"}',
            {"schema": "szl.killinchu.runtime-status/v1"},
        )
        self.assertFalse(ok)
        self.assertIn("expected", reason)


if __name__ == "__main__":
    unittest.main()
