"""Fail-closed public runtime routes for the Killinchu Space.

The application has a large, additive router. Six exact public contracts must
win before its SPA catch-all:

* ``/openapi.json`` delegates to the already-hardened namespaced generator.
* ``/.well-known/szl-source.json`` serves the on-disk attestation artifact.
* ``/api/build-info`` exposes only a strictly validated deployment source SHA.
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
_PUBLIC_RISK_ROUTE_NAME = "killinchu_p0_public_risk_status"
_CODE_ROUTE_NAME = "killinchu_p0_code_entry"
_CHAT_ROUTE_NAME = "killinchu_p0_chat_entry"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_PUBLIC_RISK_BYTES = 128 * 1024
_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_PINNED_OPTION_A_RECORD = (
    "https://github.com/szl-holdings/a11oy/blob/"
    "1ca37c24fd39660fcfbca009b0c7a39bfaf8e286/"
    "docs/decisions/2026-07-25-killinchu-public-space-exception.md"
)
_OPTION_A_APPROVED_AT = date(2026, 7, 25)
_OPTION_A_REVIEW_DUE = date(2026, 10, 23)
_REQUIRED_OPTION_A_CONTROLS = {
    "github-single-editable-source": "ENFORCED_BY_CODE",
    "generated-exact-hf-deployment": "ENFORCED_BY_CODE",
    "ci-reconciliation-gates": "ENFORCED_BY_CI",
    "complete-post-deploy-attestation": "ENFORCED_BY_CI",
    "mismatch-publication": "DIVERGENT_ON_ANY_MISMATCH",
    "outside-primary-navigation": "OUTSIDE_PRIMARY_NAVIGATION",
}
_REQUIRED_ADDITIONAL_CONTROLS = {
    "mixed-source-rights-and-attribution": "ENFORCED_BY_CI",
    "passive-sensing-legal-boundary": "DECLARED_AND_RUNTIME_GATED",
    "rollback-runbook": "DOCUMENTED",
}
_REQUIRED_PUBLIC_RISK_CONTROLS = {
    **_REQUIRED_OPTION_A_CONTROLS,
    **_REQUIRED_ADDITIONAL_CONTROLS,
}
_REQUIRED_PUBLIC_RISK_EXCEPTIONS = {
    "runtime-source-receipt": "UNAVAILABLE",
    "historical-pre-v2-archive-shards": "NOT_REWRITTEN",
}
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
    "compare the runtime /api/build-info revision to the exact protected GitHub main revision",
    "verify the Hugging Face Space repository revision from the deploy receipt",
    "verify the mixed-source dataset card from its immutable publication receipt",
    "verify product-domain primary navigation excludes Killinchu until the reconciliation gate passes",
]
_TRUTH_BOUNDARY = (
    "RUNNING and HTTP 200 are transport evidence only; they do not override "
    "failed source binding, rights publication, or explicit exceptions"
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


def _valid_evidence(value: object) -> bool:
    if isinstance(value, str):
        return bool(value)
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item) for item in value)
    )


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
        or payload.get("overall_state") != "CONDITIONAL_EXCEPTION_ACTIVE"
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

    control_states: dict[str, object] = {}
    for control in controls:
        if not _exact_keys(control, _PUBLIC_RISK_CONTROL_KEYS):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        identifier = control.get("id")
        if (
            not isinstance(identifier, str)
            or identifier in control_states
            or not _valid_evidence(control.get("evidence"))
        ):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        control_states[identifier] = control.get("state")

    exception_states: dict[str, object] = {}
    for exception in exceptions:
        if not _exact_keys(exception, _PUBLIC_RISK_EXCEPTION_KEYS):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        identifier = exception.get("id")
        if (
            not isinstance(identifier, str)
            or identifier in exception_states
            or not isinstance(exception.get("boundary"), str)
            or not exception["boundary"]
        ):
            raise _PublicRiskContractError(
                "UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"
            )
        exception_states[identifier] = exception.get("state")

    if control_states != _REQUIRED_PUBLIC_RISK_CONTROLS:
        raise _PublicRiskContractError(
            "DIVERGENT", "OPTION_A_CONTROL_MISMATCH"
        )
    if exception_states != _REQUIRED_PUBLIC_RISK_EXCEPTIONS:
        raise _PublicRiskContractError(
            "DIVERGENT", "OPTION_A_EXCEPTION_MISMATCH"
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
                "receipt_minted": False,
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
                    "source_identity_receipt_minted": False,
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
            "source_identity_receipt_minted": False,
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
