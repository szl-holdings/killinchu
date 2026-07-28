"""Focused contract tests for Killinchu's P0 public runtime routes."""

from __future__ import annotations

import json
import os
import tempfile
from html import escape as html_escape
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from killinchu_public_route_repair import register


class PublicRouteRepairTests(unittest.TestCase):
    @staticmethod
    def _app(
        artifact_path: Path | None,
        *,
        openapi_fails: bool = False,
        risk_artifact_path: Path | None = None,
    ) -> FastAPI:
        app = FastAPI()

        if openapi_fails:

            @app.get("/api/killinchu/openapi.json", include_in_schema=False)
            async def safe_openapi_failure():
                raise RuntimeError("internal generator detail must not leak")

        else:

            @app.get("/api/killinchu/openapi.json", include_in_schema=False)
            async def safe_openapi():
                return {
                    "openapi": "3.1.0",
                    "info": {"title": "Killinchu", "version": "test"},
                    "paths": {"/api/killinchu/healthz": {"get": {}}},
                }

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            return HTMLResponse(f"<html>SPA:{html_escape(full_path)}</html>")

        if artifact_path is None:
            register(
                app,
                ns="killinchu",
                risk_artifact_path=risk_artifact_path,
            )
        else:
            register(
                app,
                ns="killinchu",
                artifact_path=artifact_path,
                risk_artifact_path=risk_artifact_path,
            )
        return app

    def test_openapi_alias_precedes_default_and_has_head_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = Path(tmp) / "szl-source.json"
            app = self._app(artifact_path)
            client = TestClient(app)

            response = client.get("/openapi.json")
            head = client.head("/openapi.json")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["openapi"], "3.1.0")
            self.assertEqual(response.headers["content-type"], "application/json")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(head.status_code, response.status_code)
            self.assertEqual(head.content, b"")
            self.assertEqual(head.headers["content-type"], response.headers["content-type"])
            self.assertEqual(head.headers["content-length"], response.headers["content-length"])

            openapi_routes = [
                route for route in app.router.routes if getattr(route, "path", None) == "/openapi.json"
            ]
            self.assertGreaterEqual(len(openapi_routes), 2)
            self.assertEqual(openapi_routes[0].name, "killinchu_p0_openapi_alias")

    def test_source_artifact_is_exact_json_before_spa_with_head_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = Path(tmp) / "szl-source.json"
            payload = {
                "schema": "szl.source-attestation/v1",
                "repository": "SZLHOLDINGS/killinchu",
                "commit": "abc123",
            }
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            artifact_path.write_bytes(raw)
            app = self._app(artifact_path)
            client = TestClient(app)

            response = client.get("/.well-known/szl-source.json")
            head = client.head("/.well-known/szl-source.json")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, raw)
            self.assertEqual(response.json(), payload)
            self.assertEqual(response.headers["content-type"], "application/json")
            self.assertNotIn("text/html", response.headers["content-type"])
            self.assertEqual(head.status_code, response.status_code)
            self.assertEqual(head.content, b"")
            self.assertEqual(head.headers["content-length"], response.headers["content-length"])

            source_route = next(
                route
                for route in app.router.routes
                if getattr(route, "name", None) == "killinchu_p0_source_artifact"
            )
            catchall_route = next(
                route
                for route in app.router.routes
                if getattr(route, "path", None) == "/{full_path:path}"
            )
            self.assertLess(app.router.routes.index(source_route), app.router.routes.index(catchall_route))

    def test_build_info_uses_strict_captured_source_sha_without_environment_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sha = "A" * 40
            with patch.dict(
                os.environ,
                {
                    "SZL_GIT_SHA": sha,
                    "SECRET_TOKEN": "must-not-appear",
                },
            ):
                app = self._app(Path(tmp) / "source.json")
                os.environ["SZL_GIT_SHA"] = "b" * 40
                client = TestClient(app)

                response = client.get("/api/build-info")
                head = client.head("/api/build-info")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "OBSERVED")
            self.assertEqual(response.json()["service"], "killinchu")
            self.assertEqual(response.json()["build"]["state"], "OBSERVED")
            self.assertEqual(response.json()["build"]["revision"], sha.lower())
            self.assertEqual(
                response.json()["build"]["revision_source"],
                "env:SZL_GIT_SHA",
            )
            self.assertIs(response.json()["receipt_minted"], False)
            self.assertNotIn("must-not-appear", response.text)
            self.assertNotIn("SECRET_TOKEN", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(head.status_code, response.status_code)
            self.assertEqual(head.content, b"")
            self.assertEqual(head.headers["content-length"], response.headers["content-length"])

            build_route = next(
                route
                for route in app.router.routes
                if getattr(route, "name", None) == "killinchu_p0_build_info"
            )
            catchall_route = next(
                route
                for route in app.router.routes
                if getattr(route, "path", None) == "/{full_path:path}"
            )
            self.assertLess(app.router.routes.index(build_route), app.router.routes.index(catchall_route))

    def test_build_info_rejects_non_sha_values_without_reflection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for invalid in (
                "a" * 39,
                "a" * 41,
                "a" * 64,
                "g" * 40,
                "not-a-sha SECRET_VALUE",
                " " + ("a" * 40),
                ("a" * 40) + "\t",
            ):
                with self.subTest(invalid=invalid), patch.dict(
                    os.environ, {"SZL_GIT_SHA": invalid}
                ):
                    response = TestClient(self._app(Path(tmp) / "source.json")).get(
                        "/api/build-info"
                    )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "UNKNOWN")
                self.assertEqual(response.json()["build"]["state"], "UNKNOWN")
                self.assertIsNone(response.json()["build"]["revision"])
                self.assertEqual(response.json()["build"]["revision_source"], "UNKNOWN")
                self.assertNotIn(invalid, response.text)
                self.assertNotIn("SECRET_VALUE", response.text)

    def test_public_risk_status_preserves_explicit_exceptions_and_head_parity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            risk_path = Path(tmp) / "public-risk-transition.json"
            risk_path.write_bytes(
                (
                    Path(__file__).resolve().parents[1]
                    / "public-risk-transition.json"
                ).read_bytes()
            )
            sha = "c" * 40
            with patch.dict(os.environ, {"SZL_GIT_SHA": sha}):
                app = self._app(
                    Path(tmp) / "source.json",
                    risk_artifact_path=risk_path,
                )
                client = TestClient(app)
                response = client.get("/api/public-risk-status")
                head = client.head("/api/public-risk-status")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["overall_state"], "CONDITIONAL_EXCEPTION_ACTIVE")
            self.assertEqual(payload["decision"]["option"], "A")
            self.assertEqual(
                payload["explicit_exceptions"][0]["state"],
                "UNAVAILABLE",
            )
            self.assertEqual(
                payload["runtime_observation"]["source"]["revision"],
                sha,
            )
            self.assertIs(
                payload["runtime_observation"]["source_identity_receipt_minted"],
                False,
            )
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(head.status_code, response.status_code)
            self.assertEqual(head.content, b"")
            self.assertEqual(
                head.headers["content-length"],
                response.headers["content-length"],
            )

            route = next(
                route
                for route in app.router.routes
                if getattr(route, "name", None)
                == "killinchu_p0_public_risk_status"
            )
            catchall_route = next(
                route
                for route in app.router.routes
                if getattr(route, "path", None) == "/{full_path:path}"
            )
            self.assertLess(
                app.router.routes.index(route),
                app.router.routes.index(catchall_route),
            )

    def test_public_risk_status_fails_closed_for_invalid_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            risk_path = Path(tmp) / "public-risk-transition.json"
            risk_path.write_text('{"schema":"wrong"}', encoding="utf-8")
            response = TestClient(
                self._app(
                    Path(tmp) / "source.json",
                    risk_artifact_path=risk_path,
                )
            ).get("/api/public-risk-status")

            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["state"], "UNAVAILABLE")
            self.assertEqual(
                response.json()["schema"],
                "szl.killinchu-public-risk-transition-unavailable/v1",
            )

    def test_public_risk_status_fails_closed_if_any_boundary_is_dropped(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        canonical = json.loads(
            (repository_root / "public-risk-transition.json").read_text(
                encoding="utf-8"
            )
        )
        mutations = [("decision-type", {**canonical, "decision": "Option A"})]
        mutations.extend(
            (
                f"control-{entry['id']}",
                {
                    **canonical,
                    "controls": [
                        control
                        for control in canonical["controls"]
                        if control["id"] != entry["id"]
                    ],
                },
            )
            for entry in canonical["controls"]
        )
        mutations.extend(
            (
                f"control-state-{entry['id']}",
                {
                    **canonical,
                    "controls": [
                        {
                            **control,
                            "state": "UNVERIFIED",
                        }
                        if control["id"] == entry["id"]
                        else control
                        for control in canonical["controls"]
                    ],
                },
            )
            for entry in canonical["controls"]
        )
        mutations.extend(
            (
                f"exception-{entry['id']}",
                {
                    **canonical,
                    "explicit_exceptions": [
                        exception
                        for exception in canonical["explicit_exceptions"]
                        if exception["id"] != entry["id"]
                    ],
                },
            )
            for entry in canonical["explicit_exceptions"]
        )
        mutations.extend(
            (
                f"exception-state-{entry['id']}",
                {
                    **canonical,
                    "explicit_exceptions": [
                        {
                            **exception,
                            "state": "AVAILABLE",
                        }
                        if exception["id"] == entry["id"]
                        else exception
                        for exception in canonical["explicit_exceptions"]
                    ],
                },
            )
            for entry in canonical["explicit_exceptions"]
        )

        with tempfile.TemporaryDirectory() as tmp:
            for name, mutated in mutations:
                with self.subTest(name=name):
                    risk_path = Path(tmp) / f"{name}.json"
                    risk_path.write_text(json.dumps(mutated), encoding="utf-8")
                    response = TestClient(
                        self._app(
                            Path(tmp) / "source.json",
                            risk_artifact_path=risk_path,
                        )
                    ).get("/api/public-risk-status")
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["state"], "UNAVAILABLE")

    def test_committed_public_risk_contract_keeps_evidence_and_exceptions(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (repository_root / "public-risk-transition.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            payload["overall_state"],
            "CONDITIONAL_EXCEPTION_ACTIVE",
        )
        self.assertEqual(payload["decision"]["status"], "ACCEPTED_CONDITIONAL")
        self.assertEqual(payload["decision"]["option"], "A")
        self.assertEqual(payload["decision"]["review_due"], "2026-10-23")
        self.assertGreaterEqual(len(payload["explicit_exceptions"]), 2)

        for control in payload["controls"]:
            evidence = control["evidence"]
            for reference in evidence if isinstance(evidence, list) else [evidence]:
                if reference.startswith("/"):
                    continue
                self.assertTrue(
                    (repository_root / reference).is_file(),
                    f"missing public-risk evidence: {reference}",
                )

    def test_code_and_chat_explicitly_redirect_before_spa_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp) / "source.json")
            client = TestClient(app)
            catchall_route = next(
                route
                for route in app.router.routes
                if getattr(route, "path", None) == "/{full_path:path}"
            )

            for path, route_name in (
                ("/code", "killinchu_p0_code_entry"),
                ("/chat", "killinchu_p0_chat_entry"),
            ):
                response = client.get(path, follow_redirects=False)
                head = client.head(path, follow_redirects=False)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["location"], "/console")
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertEqual(response.content, b"")
                self.assertEqual(head.status_code, response.status_code)
                self.assertEqual(head.headers["location"], response.headers["location"])
                self.assertEqual(head.content, b"")

                route = next(
                    route
                    for route in app.router.routes
                    if getattr(route, "name", None) == route_name
                )
                self.assertLess(app.router.routes.index(route), app.router.routes.index(catchall_route))

    def test_hf_sync_binds_exact_revision_and_probes_runtime_identity(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github" / "workflows" / "hf-sync.yml").read_text(
            encoding="utf-8"
        )

        for contract in (
            "reusable-hf-deploy.yml@9aa36ed914e88bdef2873b26c022e0cecb1e6ec8",
            "hf-repo: SZLHOLDINGS/killinchu",
            "ref: ${{ github.sha }}",
            "dockerfile-path: Dockerfile",
            "include-readme: true",
            "prune: true",
            "source-revision-variable: SZL_GIT_SHA",
            "source-revision-probe-path: /api/build-info",
            '"/api/killinchu/healthz"',
            '"/api/build-info"',
            '"/api/public-risk-status"',
            '"/console"',
            '"/api/killinchu/v1/code/capabilities"',
            "HF_TOKEN: ${{ secrets.HF_ORG_TOKEN || secrets.HF_TOKEN }}",
        ):
            self.assertIn(contract, workflow)
        self.assertNotIn("secrets: inherit", workflow)

    def test_production_default_artifact_is_truthful_and_served_byte_exact(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        artifact_path = repository_root / ".well-known" / "szl-source.json"
        dockerfile = (repository_root / "Dockerfile").read_text(encoding="utf-8")
        raw = artifact_path.read_bytes()
        artifact = json.loads(raw.decode("utf-8"))

        self.assertIn(
            "COPY .well-known/szl-source.json ./.well-known/szl-source.json",
            dockerfile,
        )
        self.assertEqual(artifact["source"]["commit"], "9958c34a2066ba05e9679ce96ae4841fd67b1db6")
        self.assertEqual(artifact["source"]["sync_state"], "PENDING_GITHUB_SYNC")
        self.assertEqual(artifact["alignment_state"], "PENDING_GITHUB_SYNC")
        self.assertEqual(artifact["attestation_state"], "UNSIGNED_STRUCTURAL")
        self.assertEqual(artifact["observed_at"], "2026-07-16T18:09:53.000Z")
        self.assertEqual(
            artifact["deployment"]["audited_live_hf_revision"],
            "bba71e38fc3955fb1809a76965911675a94041b2",
        )
        self.assertEqual(artifact["deployment"]["audited_live_stage"], "RUNNING")
        self.assertEqual(artifact["deployment"]["audited_live_hardware"], "cpu-basic")
        self.assertEqual(
            artifact["deployment"]["audited_live_last_modified"],
            "2026-07-16T18:09:53.000Z",
        )
        self.assertEqual(artifact["deployment"]["current_hf_revision_state"], "NOT_CLAIMED")
        self.assertEqual(artifact["extensions"]["overlay"]["worktree_scope_state"], "NOT_ATTESTED")
        for claim in (
            "github_parity",
            "hugging_face_parity",
            "deployed_equivalence",
            "reproducible_build",
            "build_provenance",
            "current_hf_head",
        ):
            self.assertEqual(artifact["claims"][claim], "NOT_CLAIMED")

        with patch.dict(os.environ, {"KILLINCHU_ROOT": str(repository_root)}):
            client = TestClient(self._app(None))
            response = client.get("/.well-known/szl-source.json")
            head = client.head("/.well-known/szl-source.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, raw)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b"")
        self.assertEqual(head.headers["content-length"], response.headers["content-length"])

    def test_missing_or_invalid_artifact_fails_closed_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "missing.json"
            missing_client = TestClient(self._app(missing_path))

            missing = missing_client.get("/.well-known/szl-source.json")
            missing_head = missing_client.head("/.well-known/szl-source.json")
            self.assertEqual(missing.status_code, 503)
            self.assertEqual(missing.json()["state"], "UNAVAILABLE")
            self.assertEqual(missing.headers["content-type"], "application/json")
            self.assertNotIn("<html", missing.text.lower())
            self.assertEqual(missing_head.status_code, 503)
            self.assertEqual(missing_head.content, b"")

            invalid_path = Path(tmp) / "invalid.json"
            invalid_path.write_text("not-json", encoding="utf-8")
            invalid = TestClient(self._app(invalid_path)).get("/.well-known/szl-source.json")
            self.assertEqual(invalid.status_code, 503)
            self.assertEqual(invalid.json()["state"], "UNAVAILABLE")
            self.assertNotIn("JSONDecodeError", invalid.text)

    def test_openapi_generator_failure_is_honest_json_503(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp) / "source.json", openapi_fails=True)
            client = TestClient(app)

            response = client.get("/openapi.json")
            head = client.head("/openapi.json")

            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["state"], "UNAVAILABLE")
            self.assertEqual(response.headers["content-type"], "application/json")
            self.assertNotIn("internal generator detail", response.text)
            self.assertEqual(head.status_code, 503)
            self.assertEqual(head.content, b"")

    def test_registration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = Path(tmp) / "source.json"
            app = self._app(artifact_path)
            second = register(app, ns="killinchu", artifact_path=artifact_path)

            self.assertEqual(second["registered"], [])
            names = [getattr(route, "name", None) for route in app.router.routes]
            self.assertEqual(names.count("killinchu_p0_openapi_alias"), 1)
            self.assertEqual(names.count("killinchu_p0_source_artifact"), 1)
            self.assertEqual(names.count("killinchu_p0_build_info"), 1)
            self.assertEqual(names.count("killinchu_p0_public_risk_status"), 1)
            self.assertEqual(names.count("killinchu_p0_code_entry"), 1)
            self.assertEqual(names.count("killinchu_p0_chat_entry"), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
