import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient


os.environ.setdefault("KILLINCHU_ROOT", str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("KILLINCHU_LEDGER_MODE", "EPHEMERAL")

from serve import app  # noqa: E402


class KillinchuHttpHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_robots_is_text_and_supports_head(self):
        response = self.client.get("/robots.txt")
        head = self.client.head("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "User-agent: *\nAllow: /\n")
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b"")

    def test_unknown_get_and_head_return_real_404(self):
        path = "/definitely-not-a-killinchu-route-9f9c"
        response = self.client.get(path)
        head = self.client.head(path)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "not found")
        self.assertEqual(head.status_code, 404)
        self.assertEqual(head.content, b"")

    def test_known_spa_history_routes_support_direct_get_and_head(self):
        for path in (
            "/receipts",
            "/research",
            "/remote-id",
            "/swarm",
            "/threats/active",
            "/threats/live",
            "/drones/database",
            "/drones/track-42",
        ):
            response = self.client.get(path)
            head = self.client.head(path)

            self.assertEqual(response.status_code, 200, path)
            self.assertIn("text/html", response.headers["content-type"], path)
            self.assertIn('<div id="root"></div>', response.text, path)
            self.assertEqual(response.headers["cache-control"], "no-store", path)
            self.assertEqual(head.status_code, 200, path)
            self.assertEqual(head.content, b"", path)

    def test_root_key_and_export_support_head(self):
        root = self.client.head("/", follow_redirects=False)
        key = self.client.head("/cosign.pub")
        export = self.client.head("/api/killinchu/v1/receipt/export")

        self.assertIn(root.status_code, {200, 307})
        self.assertIn(key.status_code, {200, 503})
        self.assertEqual(export.status_code, 200)
        self.assertEqual(root.content, b"")
        self.assertEqual(key.content, b"")
        self.assertEqual(export.content, b"")

    def test_readiness_exposes_ephemeral_truth_without_production_claim(self):
        response = self.client.get("/api/killinchu/readyz")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["ledger"]["durability_state"], "EPHEMERAL")
        self.assertTrue(body["ledger"]["ready"])
        self.assertFalse(body["ledger"]["production_ready"])


if __name__ == "__main__":
    unittest.main()
