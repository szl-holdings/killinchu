"""Fail-closed public runtime routes for the Killinchu Space.

The application has a large, additive router. Five exact public contracts must
win before its SPA catch-all:

* ``/openapi.json`` delegates to the already-hardened namespaced generator.
* ``/.well-known/szl-source.json`` serves the on-disk attestation artifact.
* ``/api/build-info`` exposes only a strictly validated deployment source SHA.
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
import os
import re
from pathlib import Path
from typing import Any


_OPENAPI_ROUTE_NAME = "killinchu_p0_openapi_alias"
_SOURCE_ROUTE_NAME = "killinchu_p0_source_artifact"
_BUILD_INFO_ROUTE_NAME = "killinchu_p0_build_info"
_CODE_ROUTE_NAME = "killinchu_p0_code_entry"
_CHAT_ROUTE_NAME = "killinchu_p0_chat_entry"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
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


def register(
    app: Any,
    *,
    ns: str = "killinchu",
    artifact_path: str | os.PathLike[str] | None = None,
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
            raw = source_path.read_bytes()
            if not raw or len(raw) > _MAX_SOURCE_BYTES:
                raise ValueError("source attestation has an invalid size")
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
    }


__all__ = ["register"]
