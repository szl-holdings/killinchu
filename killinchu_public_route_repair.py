"""Fail-closed public runtime routes for the Killinchu Space.

The application has a large, additive router. Eight exact public contracts must
win before its SPA catch-all:

* ``/openapi.json`` delegates to the already-hardened namespaced generator.
* ``/.well-known/szl-source.json`` serves the on-disk attestation artifact.
* ``/api/build-info`` exposes only a strictly validated deployment source SHA.
* ``/version`` exposes that same exact SHA for vertical conformance.
* ``/evidence`` exposes an honest, fail-closed conformance evidence boundary.
* ``/api/public-risk-status`` exposes the dated conditional-publication contract.
* ``/code`` and ``/chat`` redirect to the existing Edge Verdict Console.

This module does not manufacture OpenAPI or source-attestation evidence. If the
real generator or artifact is unavailable, callers receive an explicit JSON
503 instead of a misleading HTML shell or a synthetic success response. Build
identity is captured once at registration and is ``UNKNOWN`` unless
``SZL_GIT_SHA`` is an exact 40-character hexadecimal revision.
"""

from __future__ import annotations

import inspect
import json
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


_OPENAPI_ROUTE_NAME = "killinchu_p0_openapi_alias"
_SOURCE_ROUTE_NAME = "killinchu_p0_source_artifact"
_BUILD_INFO_ROUTE_NAME = "killinchu_p0_build_info"
_VERSION_ROUTE_NAME = "killinchu_vertical_conformance_version"
_EVIDENCE_ROUTE_NAME = "killinchu_vertical_conformance_evidence"
_PUBLIC_RISK_ROUTE_NAME = "killinchu_p0_public_risk_status"
_CODE_ROUTE_NAME = "killinchu_p0_code_entry"
_CHAT_ROUTE_NAME = "killinchu_p0_chat_entry"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_PUBLIC_RISK_BYTES = 128 * 1024
_MAX_RELEASE_ATTESTATION_BYTES = 4096
_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTESTATION_ID_RE = re.compile(r"^[0-9]+$")
_PINNED_OPTION_A_RECORD = (
    "https://github.com/szl-holdings/a11oy/blob/"
    "1ca37c24fd39660fcfbca009b0c7a39bfaf8e286/"
    "docs/decisions/2026-07-25-killinchu-public-space-exception.md"
)
_OPTION_A_APPROVED_AT = date(2026, 7, 25)
_OPTION_A_REVIEW_DUE = date(2026, 10, 23)
_APPROVED_OPTION_A_ROLE = (
    "active, distinct counter-UAS product and deployment staging surface"
)
_APPROVED_PUBLIC_RISK_CONTROLS = (
    (
        "github-single-editable-source",
        "UNVERIFIED",
        ".github/workflows/hf-sync.yml",
    ),
    (
        "generated-exact-hf-deployment",
        "UNVERIFIED",
        ".github/workflows/hf-sync.yml",
    ),
    (
        "ci-reconciliation-gates",
        "UNVERIFIED",
        (
            ".github/workflows/copy-completeness-guard.yml",
            ".github/workflows/dockerfile-copy-guard.yml",
            ".github/workflows/fgbrain-doctrine-verify.yml",
            "tests/test_public_route_repair.py",
        ),
    ),
    (
        "complete-post-deploy-attestation",
        "UNAVAILABLE",
        (
            ".github/workflows/hf-sync.yml",
            "/api/build-info",
            "/api/public-risk-status",
        ),
    ),
    (
        "mismatch-publication",
        "DIVERGENT_ON_ANY_MISMATCH",
        (
            "killinchu_public_route_repair.py",
            "tests/test_public_route_repair.py",
        ),
    ),
    (
        "outside-primary-navigation",
        "OUTSIDE_PRIMARY_NAVIGATION",
        _PINNED_OPTION_A_RECORD,
    ),
    (
        "mixed-source-rights-and-attribution",
        "UNVERIFIED",
        (
            "datasets/killinchu-osint-corpus/README.md",
            "datasets/killinchu-osint-corpus/LICENSE.md",
            ".github/workflows/publish-intel-archive-card.yml",
        ),
    ),
    (
        "passive-sensing-legal-boundary",
        "DECLARED_AND_RUNTIME_GATED",
        (
            "LEGAL_BOUNDARIES.md",
            "tests/test_operator_mutation_security.py",
        ),
    ),
    ("rollback-runbook", "DOCUMENTED", "DEPLOY.md"),
)
_FAIL_CLOSED_CONTROL_STATES = frozenset({"UNAVAILABLE", "UNVERIFIED"})
_APPROVED_PUBLIC_RISK_EXCEPTIONS = (
    (
        "runtime-source-receipt",
        "UNAVAILABLE",
        (
            "/api/build-info reports startup-captured source identity but "
            "does not mint a cryptographic receipt"
        ),
    ),
    (
        "historical-pre-v2-archive-shards",
        "NOT_REWRITTEN",
        (
            "the public recent API withholds legacy platform rows; the "
            "backing shards are not claimed erased or rewritten"
        ),
    ),
)
_PUBLIC_RISK_TOP_LEVEL_KEYS = {
    "schema",
    "product",
    "overall_state",
    "decision",
    "controls",
    "explicit_exceptions",
    "required_external_verification",
    "truth_boundary",
}
_PUBLIC_RISK_DECISION_KEYS = {
    "option",
    "status",
    "approved_at",
    "review_due",
    "migration_state",
    "role",
    "authoritative_record",
}
_PUBLIC_RISK_CONTROL_KEYS = {"id", "state", "evidence"}
_PUBLIC_RISK_EXCEPTION_KEYS = {"id", "state", "boundary"}
_REQUIRED_EXTERNAL_VERIFICATION = [
    "bind the deployed image digest to an immutable protected-main build output",
    "bind the deployed organ inventory to the canonical registration inventory",
    "verify actual protected-main required-check settings cover every claimed CI gate",
    "compare the runtime /api/build-info revision to the exact protected GitHub main revision",
    "verify the Hugging Face Space repository revision from the deploy receipt",
    "verify the mixed-source dataset card from its immutable publication receipt",
    "verify product-domain primary navigation excludes Killinchu until the reconciliation gate passes",
]
_TRUTH_BOUNDARY = (
    "RUNNING and HTTP 200 are transport evidence only; they do not override "
    "failed source binding, rights publication, explicit exceptions, or "
    "unproved image digest, organ inventory, and required-check settings"
)
_JSON_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}
_REDIRECT_HEADERS = {
    **_JSON_HEADERS,
    "Location": "/console",
}


def _head_from(response: Any, response_cls: Any) -> Any:
    """Return a bodyless response while preserving GET status and headers."""

    return response_cls(
        content=b"",
        status_code=response.status_code,
        headers=dict(response.headers),
    )


def _source_build_identity() -> dict[str, str | None]:
    """Capture only the deployer's allowlisted source revision."""

    candidate = str(os.environ.get("SZL_GIT_SHA", ""))
    if _SHA40_RE.fullmatch(candidate):
        return {
            "state": "OBSERVED",
            "revision": candidate.lower(),
            "revision_source": "env:SZL_GIT_SHA",
        }
    return {
        "state": "UNKNOWN",
        "revision": None,
        "revision_source": "UNKNOWN",
    }


def _release_receipt(source_revision: str | None) -> dict[str, str]:
    """Validate the exact non-secret GitHub OIDC attestation reference."""

    unavailable = {
        "state": "UNAVAILABLE",
        "reason": "NO_MATCHED_GITHUB_OIDC_ATTESTATION",
    }
    raw = os.environ.get("RELEASE_ATTESTATION", "")
    if (
        not raw
        or len(raw) > _MAX_RELEASE_ATTESTATION_BYTES
        or source_revision is None
    ):
        return unavailable
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return unavailable
    if not isinstance(value, dict):
        return unavailable

    revision = str(value.get("source_revision") or "")
    digest = str(value.get("manifest_sha256") or "")
    attestation_id = str(value.get("attestation_id") or "")
    url = str(value.get("attestation_url") or "")
    expected_url = (
        "https://github.com/szl-holdings/killinchu/attestations/"
        + attestation_id
    )
    if (
        value.get("schema") != "szl.github-oidc-release-attestation/v1"
        or revision != source_revision
        or not re.fullmatch(r"[0-9a-f]{40}", revision)
        or not _SHA256_RE.fullmatch(digest)
        or not _ATTESTATION_ID_RE.fullmatch(attestation_id)
        or url != expected_url
    ):
        return unavailable

    return {
        "state": "GITHUB_OIDC_ATTESTED",
        "source_revision": revision,
        "subject": "hf-deploy-manifest.json",
        "subject_sha256": digest,
        "attestation_id": attestation_id,
        "attestation_url": url,
        "verification": (
            "Download hf-deploy-manifest.json from the matching deployment run "
            "and run gh attestation verify hf-deploy-manifest.json "
            "-R szl-holdings/killinchu"
        ),
    }


def _reject_non_finite_json_constant(value: str) -> None:
    """Reject decoder extensions that cannot be emitted by JSONResponse."""

    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _parse_finite_json_float(value: str) -> float:
    """Parse a JSON float while rejecting exponent overflow."""

    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON float is forbidden: {value}")
    return parsed


class _PublicRiskContractError(ValueError):
    """A public-safe fail-closed classification for an invalid risk contract."""

    def __init__(self, state: str, reason_code: str) -> None:
        super().__init__(reason_code)
        self.state = state
        self.reason_code = reason_code


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _read_bounded(path: Path, max_bytes: int) -> bytes:
    """Read at most max_bytes plus one sentinel byte."""

    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if not raw or len(raw) > max_bytes:
        raise ValueError("artifact has an invalid size")
    return raw


def _exact_keys(value: object, required: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == required


def _project_public_risk_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only the reviewed public v1 fields."""

    decision = payload["decision"]
    return {
        "schema": payload["schema"],
        "product": payload["product"],
        "overall_state": payload["overall_state"],
        "decision": {
            key: decision[key]
            for key in (
                "option",
                "status",
                "approved_at",
                "review_due",
                "migration_state",
                "role",
                "authoritative_record",
            )
        },
        "controls": [
            {
                "id": control["id"],
                "state": control["state"],
                "evidence": (
                    list(control["evidence"])
                    if isinstance(control["evidence"], list)
                    else control["evidence"]
                ),
            }
            for control in payload["controls"]
        ],
        "explicit_exceptions": [
            {
                "id": exception["id"],
                "state": exception["state"],
                "boundary": exception["boundary"],
            }
            for exception in payload["explicit_exceptions"]
        ],
        "required_external_verification": list(
            payload["required_external_verification"]
        ),
        "truth_boundary": payload["truth_boundary"],
    }


def _validate_public_risk_contract(
    payload: object,
    *,
    today: date,
) -> dict[str, Any]:
    """Validate the closed public schema and current Option A authority."""

    if not _exact_keys(payload, _PUBLIC_RISK_TOP_LEVEL_KEYS):
        raise _PublicRiskContractError("UNAVAILABLE", "PUBLIC_SCHEMA_INVALID")

    decision = payload.get("decision")
    controls = payload.get("controls")
    exceptions = payload.get("explicit_exceptions")
    if (
        payload.get("schema") != "szl.killinchu-public-risk-transition/v1"
        or payload.get("product") != "killinchu"
        or payload.get("overall_state")
        != "CONDITIONAL_EXCEPTION_UNVERIFIED"
        or not _exact_keys(decision, _PUBLIC_RISK_DECISION_KEYS)
        or decision.get("option") != "A"
        or decision.get("status") != "ACCEPTED_CONDITIONAL"
        or decision.get("approved_at") != _OPTION_A_APPROVED_AT.isoformat()
        or decision.get("review_due") != _OPTION_A_REVIEW_DUE.isoformat()
        or not isinstance(decision.get("role"), str)
        or not decision["role"]
        or decision.get("authoritative_record") != _PINNED_OPTION_A_RECORD
        or not isinstance(controls, list)
        or not controls
        or not isinstance(exceptions, list)
        or not exceptions
        or payload.get("required_external_verification")
        != _REQUIRED_EXTERNAL_VERIFICATION
        or payload.get("truth_boundary") != _TRUTH_BOUNDARY
    ):
        raise _PublicRiskContractError("UNAVAILABLE", "PUBLIC_SCHEMA_INVALID")

    if decision.get("migration_state") != "NOT_MIGRATED":
        raise _PublicRiskContractError(
            "UNAVAILABLE", "OPTION_A_CAPABILITY_MIGRATED"
        )
    if today >= _OPTION_A_REVIEW_DUE:
        raise _PublicRiskContractError(
            "UNAVAILABLE", "OPTION_A_REVIEW_EXPIRED"
        )
    if decision["role"] != _APPROVED_OPTION_A_ROLE:
        raise _PublicRiskContractError(
            "DIVERGENT", "OPTION_A_ROLE_MISMATCH"
        )

    seen_control_ids: set[str] = set()
    approved_control_projection: list[tuple[object, object, object]] = []
    for control in controls:
        if not _exact_keys(control, _PUBLIC_RISK_CONTROL_KEYS):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        identifier = control.get("id")
        state = control.get("state")
        evidence = control.get("evidence")
        if (
            not isinstance(identifier, str)
            or identifier in seen_control_ids
            or not isinstance(state, str)
            or not state
        ):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        if isinstance(evidence, str):
            if not evidence:
                raise _PublicRiskContractError(
                    "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
                )
            normalized_evidence: object = evidence
        elif (
            isinstance(evidence, list)
            and evidence
            and all(isinstance(item, str) and item for item in evidence)
        ):
            normalized_evidence = tuple(evidence)
        else:
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        seen_control_ids.add(identifier)
        approved_control_projection.append(
            (identifier, state, normalized_evidence)
        )

    seen_exception_ids: set[str] = set()
    approved_exception_projection: list[tuple[object, object, object]] = []
    for exception in exceptions:
        if not _exact_keys(exception, _PUBLIC_RISK_EXCEPTION_KEYS):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        identifier = exception.get("id")
        state = exception.get("state")
        boundary = exception.get("boundary")
        if (
            not isinstance(identifier, str)
            or identifier in seen_exception_ids
            or not isinstance(state, str)
            or not state
            or not isinstance(boundary, str)
            or not boundary
        ):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        seen_exception_ids.add(identifier)
        approved_exception_projection.append((identifier, state, boundary))

    if tuple(approved_control_projection) != _APPROVED_PUBLIC_RISK_CONTROLS:
        raise _PublicRiskContractError(
            "DIVERGENT", "OPTION_A_CONTROL_MISMATCH"
        )
    if (
        tuple(approved_exception_projection)
        != _APPROVED_PUBLIC_RISK_EXCEPTIONS
    ):
        raise _PublicRiskContractError(
            "DIVERGENT", "OPTION_A_EXCEPTION_MISMATCH"
        )

    # The v1 artifact has no immutable image-digest, organ-inventory, or live
    # branch-protection proof fields. File and workflow references therefore
    # cannot substantiate CI or attestation enforcement.
    if any(
        state in _FAIL_CLOSED_CONTROL_STATES
        for _, state, _ in approved_control_projection
    ):
        raise _PublicRiskContractError(
            "UNAVAILABLE", "CI_ATTESTATION_EVIDENCE_UNPROVED"
        )
    return _project_public_risk_contract(payload)


def register(
    app: Any,
    *,
    ns: str = "killinchu",
    artifact_path: str | os.PathLike[str] | None = None,
    risk_artifact_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Register exact public routes ahead of defaults and the SPA catch-all."""

    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    organ_path = f"/api/{ns}/openapi.json"
    organ_endpoint = next(
        (
            getattr(route, "endpoint", None)
            for route in app.router.routes
            if getattr(route, "path", None) == organ_path
            and callable(getattr(route, "endpoint", None))
        ),
        None,
    )

    if artifact_path is None:
        configured_path = os.environ.get("KILLINCHU_SOURCE_ATTESTATION_PATH", "").strip()
        if configured_path:
            source_path = Path(configured_path)
        else:
            app_root = Path(os.environ.get("KILLINCHU_ROOT", "/app"))
            source_path = app_root / ".well-known" / "szl-source.json"
    else:
        source_path = Path(artifact_path)

    if risk_artifact_path is None:
        configured_risk_path = os.environ.get(
            "KILLINCHU_PUBLIC_RISK_PATH", ""
        ).strip()
        if configured_risk_path:
            public_risk_path = Path(configured_risk_path)
        else:
            app_root = Path(os.environ.get("KILLINCHU_ROOT", "/app"))
            public_risk_path = app_root / "public-risk-transition.json"
    else:
        public_risk_path = Path(risk_artifact_path)

    # The reusable deployer compares this immutable startup observation with
    # the exact checked-out GitHub SHA. Public requests never re-read process
    # environment or execute a source-control command.
    build_identity = _source_build_identity()
    release_receipt = _release_receipt(build_identity["revision"])
    receipt_minted = release_receipt["state"] == "GITHUB_OIDC_ATTESTED"

    def unavailable(schema: str, reason: str, method: str) -> Any:
        response = JSONResponse(
            {
                "schema": schema,
                "state": "UNAVAILABLE",
                "reason": reason,
            },
            status_code=503,
            headers=_JSON_HEADERS,
        )
        return _head_from(response, Response) if method == "HEAD" else response

    async def public_openapi(request: Any) -> Any:
        if organ_endpoint is None:
            return unavailable(
                "szl.openapi-unavailable/v1",
                "generated OpenAPI contract is unavailable",
                request.method,
            )

        try:
            generated = organ_endpoint()
            if inspect.isawaitable(generated):
                generated = await generated

            status_code = 200
            if isinstance(generated, Response):
                status_code = generated.status_code
                raw_body = getattr(generated, "body", None)
                if raw_body is None:
                    raise ValueError("schema response is not materialized JSON")
                payload = json.loads(bytes(raw_body).decode("utf-8"))
            else:
                payload = generated

            if status_code >= 400 or not isinstance(payload, dict) or not payload.get("openapi"):
                raise ValueError("schema response is not a valid OpenAPI document")
        except Exception:
            return unavailable(
                "szl.openapi-unavailable/v1",
                "generated OpenAPI contract is unavailable",
                request.method,
            )

        response = JSONResponse(payload, headers=_JSON_HEADERS)
        return _head_from(response, Response) if request.method == "HEAD" else response

    async def source_attestation(request: Any) -> Any:
        try:
            raw = _read_bounded(source_path, _MAX_SOURCE_BYTES)
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("source attestation must be a JSON object")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return unavailable(
                "szl.source-attestation-unavailable/v1",
                "source attestation artifact is unavailable or invalid",
                request.method,
            )

        response = Response(content=raw, media_type="application/json", headers=_JSON_HEADERS)
        return _head_from(response, Response) if request.method == "HEAD" else response

    async def build_info(request: Any) -> Any:
        response = JSONResponse(
            {
                "status": build_identity["state"],
                "service": ns,
                "build": build_identity,
                "receipt_minted": receipt_minted,
                "release_receipt": release_receipt,
            },
            headers=_JSON_HEADERS,
        )
        return _head_from(response, Response) if request.method == "HEAD" else response

    async def conformance_version(request: Any) -> Any:
        if build_identity["state"] != "OBSERVED":
            return unavailable(
                "szl.vertical-conformance.version-unavailable/v1",
                "exact deployed Git SHA is unavailable",
                request.method,
            )
        response = JSONResponse(
            {
                "schemaVersion": "szl.vertical-conformance.version.v1",
                "service": ns,
                "surface": "vessels",
                "gitSha": build_identity["revision"],
            },
            headers=_JSON_HEADERS,
        )
        return _head_from(response, Response) if request.method == "HEAD" else response

    async def conformance_evidence(request: Any) -> Any:
        if build_identity["state"] != "OBSERVED":
            return unavailable(
                "szl.vertical-conformance.evidence-unavailable/v1",
                "exact deployed Git SHA is unavailable",
                request.method,
            )
        response = JSONResponse(
            {
                "schemaVersion": "szl.vertical-conformance.evidence.v1",
                "service": ns,
                "surface": "vessels",
                "evidenceState": "PARTIAL",
                "gitSha": build_identity["revision"],
                "receipts": [],
                "releaseReceipt": release_receipt,
                "limitations": [
                    (
                        "No portable cross-repository root-to-target DSSE receipt "
                        "pair is exposed by this deployment."
                    ),
                    (
                        "No conformance denial receipt or OTel GenAI span set is "
                        "claimed by this endpoint."
                    ),
                ],
            },
            headers=_JSON_HEADERS,
        )
        return _head_from(response, Response) if request.method == "HEAD" else response

    def public_risk_failure(
        *,
        state: str,
        reason_code: str,
        method: str,
    ) -> Any:
        response = JSONResponse(
            {
                "schema": "szl.killinchu-public-risk-transition-status/v1",
                "state": state,
                "reason_code": reason_code,
                "runtime_observation": {
                    "source": build_identity,
                    "source_identity_receipt_minted": receipt_minted,
                    "release_receipt": release_receipt,
                    "observation_scope": "STARTUP_CAPTURED",
                },
            },
            status_code=503,
            headers=_JSON_HEADERS,
        )
        return _head_from(response, Response) if method == "HEAD" else response

    async def public_risk_status(request: Any) -> Any:
        try:
            raw = _read_bounded(public_risk_path, _MAX_PUBLIC_RISK_BYTES)
            payload = json.loads(
                raw.decode("utf-8"),
                parse_constant=_reject_non_finite_json_constant,
                parse_float=_parse_finite_json_float,
            )
            response_payload = _validate_public_risk_contract(
                payload,
                today=_utc_today(),
            )
        except _PublicRiskContractError as exc:
            if (
                exc.reason_code == "CI_ATTESTATION_EVIDENCE_UNPROVED"
                and build_identity["state"] != "OBSERVED"
            ):
                return public_risk_failure(
                    state="DIVERGENT",
                    reason_code="RUNTIME_SOURCE_MISMATCH",
                    method=request.method,
                )
            return public_risk_failure(
                state=exc.state,
                reason_code=exc.reason_code,
                method=request.method,
            )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return public_risk_failure(
                state="UNAVAILABLE",
                reason_code="PUBLIC_CONTRACT_UNAVAILABLE",
                method=request.method,
            )

        if build_identity["state"] != "OBSERVED":
            return public_risk_failure(
                state="DIVERGENT",
                reason_code="RUNTIME_SOURCE_MISMATCH",
                method=request.method,
            )

        response_payload["runtime_observation"] = {
            "source": build_identity,
            "source_identity_receipt_minted": receipt_minted,
            "release_receipt": release_receipt,
            "observation_scope": "STARTUP_CAPTURED",
        }
        response = JSONResponse(response_payload, headers=_JSON_HEADERS)
        return _head_from(response, Response) if request.method == "HEAD" else response

    async def console_entry(_: Any) -> Any:
        return Response(content=b"", status_code=302, headers=_REDIRECT_HEADERS)

    existing_names = {getattr(route, "name", None) for route in app.router.routes}
    routes: list[Any] = []
    registered: list[str] = []

    if _OPENAPI_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/openapi.json",
                endpoint=public_openapi,
                methods=["GET", "HEAD"],
                name=_OPENAPI_ROUTE_NAME,
            )
        )
        registered.append("/openapi.json")

    if _SOURCE_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/.well-known/szl-source.json",
                endpoint=source_attestation,
                methods=["GET", "HEAD"],
                name=_SOURCE_ROUTE_NAME,
            )
        )
        registered.append("/.well-known/szl-source.json")

    if _BUILD_INFO_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/api/build-info",
                endpoint=build_info,
                methods=["GET", "HEAD"],
                name=_BUILD_INFO_ROUTE_NAME,
            )
        )
        registered.append("/api/build-info")

    if _VERSION_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/version",
                endpoint=conformance_version,
                methods=["GET", "HEAD"],
                name=_VERSION_ROUTE_NAME,
            )
        )
        registered.append("/version")

    if _EVIDENCE_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/evidence",
                endpoint=conformance_evidence,
                methods=["GET", "HEAD"],
                name=_EVIDENCE_ROUTE_NAME,
            )
        )
        registered.append("/evidence")

    if _PUBLIC_RISK_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/api/public-risk-status",
                endpoint=public_risk_status,
                methods=["GET", "HEAD"],
                name=_PUBLIC_RISK_ROUTE_NAME,
            )
        )
        registered.append("/api/public-risk-status")

    if _CODE_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/code",
                endpoint=console_entry,
                methods=["GET", "HEAD"],
                name=_CODE_ROUTE_NAME,
            )
        )
        registered.append("/code")

    if _CHAT_ROUTE_NAME not in existing_names:
        routes.append(
            Route(
                "/chat",
                endpoint=console_entry,
                methods=["GET", "HEAD"],
                name=_CHAT_ROUTE_NAME,
            )
        )
        registered.append("/chat")

    # Starlette resolves in declaration order. Front insertion ensures these
    # exact contracts win over FastAPI's defaults and /{full_path:path}.
    if routes:
        app.router.routes[0:0] = routes

    return {
        "registered": registered,
        "openapi_source": organ_path,
        "source_artifact": str(source_path),
        "public_risk_artifact": str(public_risk_path),
    }


__all__ = ["register"]
