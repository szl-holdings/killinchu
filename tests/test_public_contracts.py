import sys
import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_public_contracts


class PublicContractTests(unittest.TestCase):
    def setUp(self):
        self.original_metrics = sys.modules.get("szl_metrics_prom")
        metrics = types.ModuleType("szl_metrics_prom")
        metrics.render = lambda _app: (
            "# HELP szl_requests_total Requests observed\n"
            "# TYPE szl_requests_total counter\n"
            "szl_requests_total 3\n"
        )
        sys.modules["szl_metrics_prom"] = metrics

    def tearDown(self):
        if self.original_metrics is None:
            sys.modules.pop("szl_metrics_prom", None)
        else:
            sys.modules["szl_metrics_prom"] = self.original_metrics

    @staticmethod
    def build_app():
        app = FastAPI(title="contract-test", version="1")

        @app.get("/metrics")
        async def metrics():
            return "szl_requests_total 3\n"

        @app.get("/api/killinchu/v1/mesh/state")
        async def mesh_state():
            return {"state": "test"}

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            return {"spa": full_path}

        killinchu_public_contracts.register(app, ns="killinchu")
        return app

    def test_health_status_and_melt_are_typed_ahead_of_spa(self):
        client = TestClient(self.build_app())
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.headers["content-type"], "application/json")
        self.assertEqual(health.json()["schema"], "szl.killinchu.health/v1")
        self.assertEqual(health.json()["authority_state"], "READ_ONLY")

        status = client.get("/api/killinchu/v1/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["schema"], "szl.killinchu.runtime-status/v1")
        self.assertEqual(status.json()["doctrine"]["locked_proven_count"], 8)
        self.assertNotIn("locked_core", status.json()["doctrine"])
        self.assertIn("OPEN", status.json()["doctrine"]["lambda"])

        melt = client.get("/api/killinchu/v1/melt/summary")
        self.assertEqual(melt.status_code, 200)
        self.assertEqual(melt.json()["schema"], "szl.killinchu.melt-summary/v1")
        self.assertEqual(melt.json()["evidence_state"], "LIVE")
        self.assertEqual(melt.json()["signals"]["traces"]["state"], "EXPORT_UNAVAILABLE")

    def test_source_attestation_is_typed_and_candid(self):
        measured = {
            "revision": "a77c8c5257e49953e042202301a3065a54908c5a",
            "last_modified": "2026-07-12T00:00:00Z",
            "observed_at": "2026-07-12T00:00:01Z",
        }
        with mock.patch.object(killinchu_public_contracts, "_hf_repository_head", return_value=measured):
            response = TestClient(self.build_app()).get("/.well-known/szl-source.json")
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "szl.deployment-source/v1")
        self.assertEqual(payload["alignment_state"], "PENDING_GITHUB_SYNC")
        self.assertEqual(payload["source"]["commit"], "b2a0403fd790d4ae4b243adaa1ea764df3d091f5")
        self.assertIn("not proof", " ".join(payload["limits"]).lower())

    def test_source_attestation_fails_honestly_when_unmeasured(self):
        with mock.patch.object(killinchu_public_contracts, "_hf_repository_head", return_value=None):
            response = TestClient(self.build_app()).get("/.well-known/szl-source.json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["state"], "UNAVAILABLE")

    def test_openapi_remains_typed(self):
        response = TestClient(self.build_app()).get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["openapi"], "3.1.0")

    def test_registration_is_idempotent(self):
        app = self.build_app()
        before = len(app.router.routes)
        result = killinchu_public_contracts.register(app, ns="killinchu")
        self.assertEqual(result["routes"], [])
        self.assertEqual(len(app.router.routes), before)


if __name__ == "__main__":
    unittest.main()
