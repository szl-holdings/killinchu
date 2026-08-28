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

    def test_verify_explains_dsse_and_is_not_404(self):
        response = self.client.get("/verify")
        head = self.client.head("/verify")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("DSSEv1", response.text)
        self.assertIn("POST /khipu/verify", response.text)
        self.assertIn("/elite#audit", response.text)
        self.assertIn("Conjecture 1", response.text)
        self.assertIn("SIMULATED", response.text)
        self.assertIn("EPHEMERAL", response.text)
        self.assertNotIn("not found", response.text.lower())
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b"")

        json_response = self.client.get(
            "/verify", headers={"Accept": "application/json"}
        )
        self.assertEqual(json_response.status_code, 200)
        self.assertIn("application/json", json_response.headers["content-type"])
        body = json_response.json()
        self.assertEqual(body["dsse"]["in_process"], "POST /khipu/verify")
        self.assertEqual(body["lambda"], "Conjecture 1 (never a theorem)")
        self.assertEqual(body["effector"], "SIMULATED")
        self.assertEqual(body["ledger"], "EPHEMERAL")

    def test_lambda_and_drones_database_return_json_not_spa_html(self):
        for path, required_keys in (
            ("/lambda", ("lambda", "uniqueness", "doctrine")),
            ("/drones/database", ("drones", "count", "total")),
        ):
            for headers in ({}, {"Accept": "application/json"}):
                with self.subTest(path=path, headers=headers):
                    response = self.client.get(path, headers=headers)
                    self.assertEqual(response.status_code, 200, path)
                    self.assertIn(
                        "application/json",
                        response.headers["content-type"],
                        path,
                    )
                    self.assertNotIn("text/html", response.headers["content-type"], path)
                    body = response.json()
                    for key in required_keys:
                        self.assertIn(key, body, path)
                    if path == "/lambda":
                        self.assertIn("Conjecture 1", body["uniqueness"])
                    canonical = self.client.get(f"/api/killinchu/v1{path}")
                    self.assertEqual(canonical.status_code, 200, path)
                    self.assertEqual(body.keys(), canonical.json().keys(), path)

            head = self.client.head(path)
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
