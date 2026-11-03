import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_public_contracts
import szl_be_hardening
import szl_metrics_prom


class PublicContractTests(unittest.TestCase):
    def build_app(self):
        app = FastAPI(title="contract-test", version="1")
        szl_metrics_prom.register(app, ns="killinchu")

        @app.get("/api/killinchu/v1/mesh/state")
        async def mesh_state():
            return {"state": "test"}

        szl_be_hardening.harden(app, organ="killinchu", khipu_path=":memory:")
        killinchu_public_contracts.register(app, ns="killinchu")
        return app

    def test_health_status_and_melt_are_typed(self):
        client = TestClient(self.build_app())
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["transport_state"], "REACHABLE")
        self.assertEqual(health.json()["authority_state"], "READ_ONLY")
        runtime = health.json()["runtime"]
        self.assertNotIn("git_sha", runtime)
        self.assertEqual(
            runtime["source_git_revision_variable"]["meaning"],
            "operator-supplied source revision build metadata",
        )
        self.assertFalse(
            runtime["source_git_revision_variable"][
                "is_huggingface_deployment_revision"
            ]
        )

        status = client.get("/api/killinchu/v1/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["schema"], "szl.killinchu.runtime-status/v1")

        melt = client.get("/api/killinchu/v1/melt/summary")
        self.assertEqual(melt.status_code, 200)
        self.assertEqual(melt.json()["evidence_state"], "LIVE")
        self.assertTrue(melt.json()["contracts"]["metrics_route_registered"])
        self.assertTrue(melt.json()["contracts"]["mesh_state_route_registered"])
        self.assertEqual(melt.json()["signals"]["traces"]["state"], "EXPORT_UNAVAILABLE")

    def test_source_attestation_keeps_source_and_deployment_distinct(self):
        client = TestClient(self.build_app())
        head = {
            "revision": "a" * 40,
            "last_modified": "2026-07-11T16:18:34.000Z",
            "observed_at": "2026-07-11T16:20:00+00:00",
        }
        with patch.dict("os.environ", {"SZL_GIT_SHA": "source-build-sha"}), patch.object(
            killinchu_public_contracts, "_hf_repository_head", return_value=head
        ):
            response = client.get("/.well-known/szl-source.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        payload = response.json()
        self.assertEqual(payload["schema"], "szl.deployment-source/v1")
        self.assertEqual(payload["alignment_state"], "PENDING_GITHUB_SYNC")
        self.assertEqual(
            payload["source"],
            {
                "repository": "szl-holdings/killinchu",
                "commit": killinchu_public_contracts.GITHUB_OBSERVED_REVISION,
                "path": "",
            },
        )
        self.assertEqual(
            payload["deployment"],
            {"hf_space": "SZLHOLDINGS/killinchu", "hf_revision": "a" * 40},
        )
        self.assertEqual(payload["built_at"], "2026-07-11T16:18:34.000Z")
        extension = payload["extensions"]
        self.assertEqual(
            extension["deployment_revision_evidence"][
                "running_process_revision_state"
            ],
            "NOT_EXPOSED_IN_PROCESS",
        )
        build_variable = extension["build_metadata"]["source_git_revision_variable"]
        self.assertEqual(build_variable["value"], "source-build-sha")
        self.assertFalse(build_variable["is_huggingface_deployment_revision"])
        overlay = extension["overlay"]
        self.assertEqual(overlay["state"], "HF_ONLY_CORRECTIVE_OVERLAY")
        self.assertEqual(overlay["base_revision"], killinchu_public_contracts.HF_OVERLAY_BASE_REVISION)
        self.assertEqual(
            [item["path"] for item in overlay["documented_paths"]],
            ["Dockerfile", "serve.py", "killinchu_public_contracts.py", "tests/test_public_contracts.py", "README.md"],
        )
        self.assertIn("not a complete", overlay["scope_limit"])

        # Mirrors the identity checks in check_ecosystem_drift.compare.
        identity_errors = []
        if payload.get("schema") != "szl.deployment-source/v1":
            identity_errors.append("schema")
        if payload.get("source", {}).get("repository") != "szl-holdings/killinchu":
            identity_errors.append("source.repository")
        if payload.get("deployment", {}).get("hf_space") != "SZLHOLDINGS/killinchu":
            identity_errors.append("deployment.hf_space")
        if payload.get("deployment", {}).get("hf_revision") != "a" * 40:
            identity_errors.append("deployment.hf_revision")
        self.assertEqual(identity_errors, [])

    def test_source_attestation_fails_unknown_instead_of_claiming_stale_head(self):
        client = TestClient(self.build_app())
        with patch.object(
            killinchu_public_contracts, "_hf_repository_head", return_value=None
        ):
            response = client.get("/.well-known/szl-source.json?refresh=1")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["state"], "UNAVAILABLE")

    def test_all_openapi_discovery_paths_avoid_legacy_500(self):
        client = TestClient(self.build_app())
        for path in (
            "/openapi.json",
            "/api/killinchu/openapi.json",
            "/api/killinchu/v1/openapi.json",
        ):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["openapi"], "3.1.0")


    def test_runtime_wires_contracts_before_entrypoint(self):
        root = Path(__file__).resolve().parents[1]
        serve = (root / "serve.py").read_text(encoding="utf-8")
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        registration = serve.index("_kc_public_contracts.register(app, ns=\"killinchu\")")
        entrypoint = serve.index('if __name__ == "__main__":')
        self.assertLess(registration, entrypoint)
        self.assertIn("COPY killinchu_public_contracts.py ./", dockerfile)


if __name__ == "__main__":
    unittest.main()
