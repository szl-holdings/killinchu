"""Focused contract tests for Killinchu's P0 public runtime routes."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from html import escape as html_escape
from io import BytesIO
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from killinchu_public_route_repair import (
    _MAX_PUBLIC_RISK_BYTES,
    _read_bounded,
    register,
)


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
            self.assertEqual(
                response.json()["release_receipt"]["state"],
                "UNAVAILABLE",
            )
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

    def test_build_info_accepts_only_exact_revision_github_oidc_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            revision = "a" * 40
            attestation_id = "123456"
            receipt = {
                "schema": "szl.github-oidc-release-attestation/v1",
                "source_revision": revision,
                "manifest_sha256": "b" * 64,
                "attestation_id": attestation_id,
                "attestation_url": (
                    "https://github.com/szl-holdings/killinchu/attestations/"
                    + attestation_id
                ),
            }
            with patch.dict(
                os.environ,
                {
                    "SZL_GIT_SHA": revision,
                    "RELEASE_ATTESTATION": json.dumps(receipt),
                },
            ):
                response = TestClient(self._app(Path(tmp) / "source.json")).get(
                    "/api/build-info"
                )

            payload = response.json()
            self.assertIs(payload["receipt_minted"], True)
            self.assertEqual(
                payload["release_receipt"]["state"],
                "GITHUB_OIDC_ATTESTED",
            )
            self.assertEqual(payload["release_receipt"]["source_revision"], revision)
            self.assertEqual(payload["release_receipt"]["subject_sha256"], "b" * 64)
            self.assertEqual(
                payload["release_receipt"]["attestation_url"],
                receipt["attestation_url"],
            )

            invalid_receipts = (
                {**receipt, "source_revision": "c" * 40},
                {**receipt, "manifest_sha256": "B" * 64},
                {**receipt, "attestation_id": "../123"},
                {
                    **receipt,
                    "attestation_url": (
                        "https://github.com/szl-holdings/david-leads/"
                        "attestations/123456"
                    ),
                },
                {**receipt, "schema": "szl.github-oidc-release-attestation/v2"},
            )
            for invalid in invalid_receipts:
                with self.subTest(invalid=invalid), patch.dict(
                    os.environ,
                    {
                        "SZL_GIT_SHA": revision,
                        "RELEASE_ATTESTATION": json.dumps(invalid),
                    },
                ):
                    rejected = TestClient(self._app(Path(tmp) / "source.json")).get(
                        "/api/build-info"
                    )
                self.assertIs(rejected.json()["receipt_minted"], False)
                self.assertEqual(
                    rejected.json()["release_receipt"]["state"],
                    "UNAVAILABLE",
                )

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

    def test_vertical_conformance_routes_expose_exact_sha_and_honest_partial_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sha = "d" * 40
            with patch.dict(os.environ, {"SZL_GIT_SHA": sha}):
                app = self._app(Path(tmp) / "source.json")
                client = TestClient(app)
                version = client.get("/version")
                evidence = client.get("/evidence")
                version_head = client.head("/version")
                evidence_head = client.head("/evidence")

            self.assertEqual(version.status_code, 200)
            self.assertEqual(
                version.json(),
                {
                    "schemaVersion": "szl.vertical-conformance.version.v1",
                    "service": "killinchu",
                    "surface": "vessels",
                    "gitSha": sha,
                },
            )
            self.assertEqual(evidence.status_code, 200)
            self.assertEqual(
                evidence.json()["schemaVersion"],
                "szl.vertical-conformance.evidence.v1",
            )
            self.assertEqual(evidence.json()["surface"], "vessels")
            self.assertEqual(evidence.json()["evidenceState"], "PARTIAL")
            self.assertEqual(evidence.json()["gitSha"], sha)
            self.assertEqual(evidence.json()["receipts"], [])
            self.assertEqual(
                evidence.json()["releaseReceipt"]["state"],
                "UNAVAILABLE",
            )
            self.assertIn(
                "No portable cross-repository root-to-target DSSE receipt pair",
                evidence.json()["limitations"][0],
            )
            self.assertEqual(version.headers["cache-control"], "no-store")
            self.assertEqual(evidence.headers["cache-control"], "no-store")
            self.assertEqual(version_head.status_code, 200)
            self.assertEqual(version_head.content, b"")
            self.assertEqual(evidence_head.status_code, 200)
            self.assertEqual(evidence_head.content, b"")

            route_names = {
                getattr(route, "name", None): app.router.routes.index(route)
                for route in app.router.routes
            }
            catchall = next(
                route
                for route in app.router.routes
                if getattr(route, "path", None) == "/{full_path:path}"
            )
            self.assertLess(
                route_names["killinchu_vertical_conformance_version"],
                app.router.routes.index(catchall),
            )
            self.assertLess(
                route_names["killinchu_vertical_conformance_evidence"],
                app.router.routes.index(catchall),
            )

    def test_vertical_conformance_routes_fail_closed_without_exact_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for invalid in ("", "not-a-sha", "a" * 39):
                with self.subTest(invalid=invalid), patch.dict(
                    os.environ,
                    {"SZL_GIT_SHA": invalid},
                ):
                    client = TestClient(self._app(Path(tmp) / "source.json"))
                    version = client.get("/version")
                    evidence = client.get("/evidence")

                self.assertEqual(version.status_code, 503)
                self.assertEqual(version.json()["state"], "UNAVAILABLE")
                self.assertEqual(evidence.status_code, 503)
                self.assertEqual(evidence.json()["state"], "UNAVAILABLE")
                if invalid:
                    self.assertNotIn(invalid, version.text)
                    self.assertNotIn(invalid, evidence.text)

    def test_public_risk_status_fails_closed_for_unproved_controls_with_head_parity(
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
            with (
                patch.dict(os.environ, {"SZL_GIT_SHA": sha}),
                patch(
                    "killinchu_public_route_repair._utc_today",
                    return_value=date(2026, 7, 28),
                ),
            ):
                app = self._app(
                    Path(tmp) / "source.json",
                    risk_artifact_path=risk_path,
                )
                client = TestClient(app)
                response = client.get("/api/public-risk-status")
                head = client.head("/api/public-risk-status")

            self.assertEqual(response.status_code, 503)
            payload = response.json()
            self.assertEqual(payload["state"], "UNAVAILABLE")
            self.assertEqual(
                payload["reason_code"],
                "CI_ATTESTATION_EVIDENCE_UNPROVED",
            )
            self.assertEqual(
                payload["runtime_observation"]["source"]["revision"],
                sha,
            )
            self.assertIs(
                payload["runtime_observation"]["source_identity_receipt_minted"],
                False,
            )
            self.assertEqual(
                payload["runtime_observation"]["release_receipt"]["state"],
                "UNAVAILABLE",
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
                "szl.killinchu-public-risk-transition-status/v1",
            )
            self.assertEqual(
                response.json()["reason_code"],
                "PUBLIC_SCHEMA_INVALID",
            )

    def test_public_risk_status_fails_closed_for_non_finite_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository_root = Path(__file__).resolve().parents[1]
            payload = json.loads(
                (repository_root / "public-risk-transition.json").read_text(
                    encoding="utf-8"
                )
            )
            risk_path = Path(tmp) / "public-risk-transition.json"
            client = TestClient(
                self._app(
                    Path(tmp) / "source.json",
                    risk_artifact_path=risk_path,
                )
            )

            for label, token in (
                ("decoder extension", "NaN"),
                ("exponent overflow", "1e999"),
            ):
                with self.subTest(label=label):
                    payload["truth_boundary"] = "NON_FINITE_PLACEHOLDER"
                    serialized = json.dumps(payload).replace(
                        '"NON_FINITE_PLACEHOLDER"',
                        token,
                    )
                    risk_path.write_text(serialized, encoding="utf-8")
                    response = client.get("/api/public-risk-status")

                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["state"], "UNAVAILABLE")
                    self.assertEqual(
                        response.json()["schema"],
                        "szl.killinchu-public-risk-transition-status/v1",
                    )
                    self.assertEqual(
                        response.json()["reason_code"],
                        "PUBLIC_CONTRACT_UNAVAILABLE",
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
                            "state": (
                                "ENFORCED_BY_CI"
                                if control["state"] == "UNVERIFIED"
                                else "UNVERIFIED"
                            ),
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
                    with patch(
                        "killinchu_public_route_repair._utc_today",
                        return_value=date(2026, 7, 28),
                    ):
                        response = TestClient(
                            self._app(
                                Path(tmp) / "source.json",
                                risk_artifact_path=risk_path,
                            )
                        ).get("/api/public-risk-status")
                    self.assertEqual(response.status_code, 503)
                    expected_state = (
                        "UNAVAILABLE"
                        if name == "decision-type"
                        else "DIVERGENT"
                    )
                    self.assertEqual(
                        response.json()["state"],
                        expected_state,
                    )

    def test_public_risk_status_rejects_unknown_fields_without_reflection(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        canonical = json.loads(
            (repository_root / "public-risk-transition.json").read_text(
                encoding="utf-8"
            )
        )
        mutations = (
            {**canonical, "internal_notes": "TOP_SECRET_VALUE"},
            {
                **canonical,
                "decision": {
                    **canonical["decision"],
                    "private_owner": "TOP_SECRET_VALUE",
                },
            },
            {
                **canonical,
                "controls": [
                    {
                        **canonical["controls"][0],
                        "internal_ticket": "TOP_SECRET_VALUE",
                    },
                    *canonical["controls"][1:],
                ],
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            for index, mutated in enumerate(mutations):
                with self.subTest(index=index):
                    risk_path = Path(tmp) / f"unknown-{index}.json"
                    risk_path.write_text(json.dumps(mutated), encoding="utf-8")
                    with (
                        patch.dict(os.environ, {"SZL_GIT_SHA": "c" * 40}),
                        patch(
                            "killinchu_public_route_repair._utc_today",
                            return_value=date(2026, 7, 28),
                        ),
                    ):
                        response = TestClient(
                            self._app(
                                Path(tmp) / "source.json",
                                risk_artifact_path=risk_path,
                            )
                        ).get("/api/public-risk-status")

                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["state"], "UNAVAILABLE")
                    self.assertEqual(
                        response.json()["reason_code"],
                        "PUBLIC_SCHEMA_INVALID",
                    )
                    self.assertNotIn("TOP_SECRET_VALUE", response.text)

    def test_public_risk_status_fails_closed_at_review_due_or_migration(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        canonical = json.loads(
            (repository_root / "public-risk-transition.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            risk_path = Path(tmp) / "public-risk-transition.json"
            risk_path.write_text(json.dumps(canonical), encoding="utf-8")
            with (
                patch.dict(os.environ, {"SZL_GIT_SHA": "c" * 40}),
                patch(
                    "killinchu_public_route_repair._utc_today",
                    return_value=date(2026, 10, 23),
                ),
            ):
                expired = TestClient(
                    self._app(
                        Path(tmp) / "source.json",
                        risk_artifact_path=risk_path,
                    )
                ).get("/api/public-risk-status")

            migrated_payload = {
                **canonical,
                "decision": {
                    **canonical["decision"],
                    "migration_state": "MIGRATED_TO_APPROVED_FIVE",
                },
            }
            risk_path.write_text(
                json.dumps(migrated_payload),
                encoding="utf-8",
            )
            with (
                patch.dict(os.environ, {"SZL_GIT_SHA": "c" * 40}),
                patch(
                    "killinchu_public_route_repair._utc_today",
                    return_value=date(2026, 7, 28),
                ),
            ):
                migrated = TestClient(
                    self._app(
                        Path(tmp) / "source.json",
                        risk_artifact_path=risk_path,
                    )
                ).get("/api/public-risk-status")

        self.assertEqual(expired.status_code, 503)
        self.assertEqual(
            expired.json()["reason_code"],
            "OPTION_A_REVIEW_EXPIRED",
        )
        self.assertEqual(migrated.status_code, 503)
        self.assertEqual(
            migrated.json()["reason_code"],
            "OPTION_A_CAPABILITY_MIGRATED",
        )

    def test_public_risk_status_rejects_mutated_authority_or_deadline(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        canonical = json.loads(
            (repository_root / "public-risk-transition.json").read_text(
                encoding="utf-8"
            )
        )
        mutations = {
            "authority": {
                **canonical,
                "decision": {
                    **canonical["decision"],
                    "authoritative_record": canonical["decision"][
                        "authoritative_record"
                    ].replace(
                        "1ca37c24fd39660fcfbca009b0c7a39bfaf8e286",
                        "f" * 40,
                    ),
                },
            },
            "deadline": {
                **canonical,
                "decision": {
                    **canonical["decision"],
                    "review_due": "2027-10-23",
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            for label, mutated in mutations.items():
                with self.subTest(label=label):
                    risk_path = Path(tmp) / f"{label}.json"
                    risk_path.write_text(json.dumps(mutated), encoding="utf-8")
                    with (
                        patch.dict(os.environ, {"SZL_GIT_SHA": "c" * 40}),
                        patch(
                            "killinchu_public_route_repair._utc_today",
                            return_value=date(2026, 7, 28),
                        ),
                    ):
                        response = TestClient(
                            self._app(
                                Path(tmp) / "source.json",
                                risk_artifact_path=risk_path,
                            )
                        ).get("/api/public-risk-status")

                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["state"], "UNAVAILABLE")
                    self.assertEqual(
                        response.json()["reason_code"],
                        "PUBLIC_SCHEMA_INVALID",
                    )

    def test_public_risk_status_rejects_unapproved_published_content(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        canonical = json.loads(
            (repository_root / "public-risk-transition.json").read_text(
                encoding="utf-8"
            )
        )
        mutations = [
            (
                "decision-role",
                {
                    **canonical,
                    "decision": {
                        **canonical["decision"],
                        "role": "unreviewed role",
                    },
                },
                "OPTION_A_ROLE_MISMATCH",
                "unreviewed role",
            ),
        ]
        mutations.extend(
            (
                f"control-evidence-{entry['id']}",
                {
                    **canonical,
                    "controls": [
                        {
                            **control,
                            "evidence": (
                                ["unreviewed-control-evidence"]
                                if isinstance(control["evidence"], list)
                                else "unreviewed-control-evidence"
                            ),
                        }
                        if control["id"] == entry["id"]
                        else control
                        for control in canonical["controls"]
                    ],
                },
                "OPTION_A_CONTROL_MISMATCH",
                "unreviewed-control-evidence",
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
                            "state": "ENFORCED_BY_CI",
                        }
                        if control["id"] == entry["id"]
                        else control
                        for control in canonical["controls"]
                    ],
                },
                "OPTION_A_CONTROL_MISMATCH",
                "ENFORCED_BY_CI",
            )
            for entry in canonical["controls"]
            if entry["state"] in {"UNAVAILABLE", "UNVERIFIED"}
        )
        mutations.extend(
            (
                f"exception-boundary-{entry['id']}",
                {
                    **canonical,
                    "explicit_exceptions": [
                        {
                            **exception,
                            "boundary": "unreviewed exception boundary",
                        }
                        if exception["id"] == entry["id"]
                        else exception
                        for exception in canonical["explicit_exceptions"]
                    ],
                },
                "OPTION_A_EXCEPTION_MISMATCH",
                "unreviewed exception boundary",
            )
            for entry in canonical["explicit_exceptions"]
        )

        with tempfile.TemporaryDirectory() as tmp:
            for index, (
                label,
                mutated,
                reason_code,
                injected_text,
            ) in enumerate(mutations):
                with self.subTest(label=label):
                    risk_path = Path(tmp) / f"unapproved-{index}.json"
                    risk_path.write_text(json.dumps(mutated), encoding="utf-8")
                    with (
                        patch.dict(os.environ, {"SZL_GIT_SHA": "c" * 40}),
                        patch(
                            "killinchu_public_route_repair._utc_today",
                            return_value=date(2026, 7, 28),
                        ),
                    ):
                        response = TestClient(
                            self._app(
                                Path(tmp) / "source.json",
                                risk_artifact_path=risk_path,
                            )
                        ).get("/api/public-risk-status")

                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["state"], "DIVERGENT")
                    self.assertEqual(
                        response.json()["reason_code"],
                        reason_code,
                    )
                    self.assertNotIn(injected_text, response.text)

    def test_public_risk_status_publishes_runtime_mismatch_as_divergent(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        with (
            patch.dict(os.environ, {"SZL_GIT_SHA": ""}),
            patch(
                "killinchu_public_route_repair._utc_today",
                return_value=date(2026, 7, 28),
            ),
        ):
            response = TestClient(
                self._app(
                    repository_root / ".well-known" / "szl-source.json",
                    risk_artifact_path=(
                        repository_root / "public-risk-transition.json"
                    ),
                )
            ).get("/api/public-risk-status")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["state"], "DIVERGENT")
        self.assertEqual(
            response.json()["reason_code"],
            "RUNTIME_SOURCE_MISMATCH",
        )

    def test_public_risk_reader_never_reads_past_bound_plus_sentinel(
        self,
    ) -> None:
        class TrackingReader(BytesIO):
            def __init__(self, payload: bytes) -> None:
                super().__init__(payload)
                self.read_sizes: list[int] = []

            def read(self, size: int = -1) -> bytes:
                self.read_sizes.append(size)
                return super().read(size)

        reader = TrackingReader(b"x" * (_MAX_PUBLIC_RISK_BYTES + 16))
        with (
            patch.object(Path, "open", return_value=reader),
            self.assertRaises(ValueError),
        ):
            _read_bounded(Path("ignored"), _MAX_PUBLIC_RISK_BYTES)

        self.assertEqual(
            reader.read_sizes,
            [_MAX_PUBLIC_RISK_BYTES + 1],
        )

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
            "CONDITIONAL_EXCEPTION_UNVERIFIED",
        )
        self.assertEqual(payload["decision"]["status"], "ACCEPTED_CONDITIONAL")
        self.assertEqual(payload["decision"]["option"], "A")
        self.assertEqual(payload["decision"]["review_due"], "2026-10-23")
        self.assertEqual(payload["decision"]["migration_state"], "NOT_MIGRATED")
        self.assertEqual(
            payload["decision"]["role"],
            "active, distinct counter-UAS product and deployment staging surface",
        )
        self.assertIn(
            "/blob/1ca37c24fd39660fcfbca009b0c7a39bfaf8e286/",
            payload["decision"]["authoritative_record"],
        )
        self.assertGreaterEqual(len(payload["explicit_exceptions"]), 2)
        control_states = {
            control["id"]: control["state"]
            for control in payload["controls"]
        }
        self.assertEqual(
            control_states["mismatch-publication"],
            "DIVERGENT_ON_ANY_MISMATCH",
        )
        self.assertEqual(
            control_states["outside-primary-navigation"],
            "OUTSIDE_PRIMARY_NAVIGATION",
        )
        for control_id in (
            "github-single-editable-source",
            "generated-exact-hf-deployment",
            "ci-reconciliation-gates",
            "mixed-source-rights-and-attribution",
        ):
            self.assertEqual(control_states[control_id], "UNVERIFIED")
        self.assertEqual(
            control_states["complete-post-deploy-attestation"],
            "UNAVAILABLE",
        )
        self.assertNotIn("ENFORCED_BY_CI", control_states.values())
        self.assertIn(
            "bind the deployed image digest to an immutable protected-main build output",
            payload["required_external_verification"],
        )
        self.assertIn(
            "bind the deployed organ inventory to the canonical registration inventory",
            payload["required_external_verification"],
        )
        self.assertIn(
            "verify actual protected-main required-check settings cover every claimed CI gate",
            payload["required_external_verification"],
        )

        for control in payload["controls"]:
            evidence = control["evidence"]
            for reference in evidence if isinstance(evidence, list) else [evidence]:
                if reference.startswith(("/", "https://")):
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
            "reusable-hf-deploy.yml@391f67e28dd966d9e42f88c6e3f852f3c63add84",
            "hf-repo: SZLHOLDINGS/killinchu",
            "ref: ${{ github.sha }}",
            "require-default-branch-tip: true",
            "dockerfile-path: Dockerfile",
            "include-readme: true",
            "prune: true",
            "source-revision-variable: SZL_GIT_SHA",
            "source-revision-probe-path: /api/build-info",
            '"/api/killinchu/healthz"',
            '"/api/build-info"',
            "https://szlholdings-killinchu.hf.space/api/public-risk-status",
            '"/console"',
            '"/api/killinchu/v1/code/capabilities"',
            "HF_TOKEN: ${{ secrets.HF_ORG_TOKEN || secrets.HF_TOKEN }}",
            "verify-risk-status-fails-closed:",
            'test "$code" = "503"',
            'payload["state"] == "UNAVAILABLE"',
            'payload["reason_code"] == "CI_ATTESTATION_EVIDENCE_UNPROVED"',
            "id-token: write",
            "attestations: write",
            "release-receipt:",
            "actions/attest@36051bcae73b7c2a8a6945a48cbf80953c6baa35",
            'key="RELEASE_ATTESTATION"',
            'body.get("receipt_minted") is True',
            "killinchu-release-receipt",
        ):
            self.assertIn(contract, workflow)
        self.assertNotIn("secrets: inherit", workflow)
        smoke_paths = next(
            line for line in workflow.splitlines() if "smoke-paths:" in line
        )
        self.assertNotIn("/api/public-risk-status", smoke_paths)

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
            self.assertEqual(names.count("killinchu_vertical_conformance_version"), 1)
            self.assertEqual(names.count("killinchu_vertical_conformance_evidence"), 1)
            self.assertEqual(names.count("killinchu_p0_public_risk_status"), 1)
            self.assertEqual(names.count("killinchu_p0_code_entry"), 1)
            self.assertEqual(names.count("killinchu_p0_chat_entry"), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
