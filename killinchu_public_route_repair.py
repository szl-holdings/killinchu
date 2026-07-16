"""Fail-closed public discovery routes for the Killinchu Space.

The application has a large, additive router. Two public discovery contracts
must win before its SPA catch-all:

* ``/openapi.json`` delegates to the already-hardened namespaced generator.
* ``/.well-known/szl-source.json`` serves the on-disk attestation artifact.

This module deliberately does not manufacture either contract. If the real
generator or artifact is unavailable, callers receive an explicit JSON 503
instead of a misleading HTML shell or a synthetic success response.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any


_OPENAPI_ROUTE_NAME = "killinchu_p0_openapi_alias"
_SOURCE_ROUTE_NAME = "killinchu_p0_source_artifact"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_JSON_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def _head_from(response: Any, response_cls: Any) -> Any:
    """Return a bodyless response while preserving GET status and headers."""

    return response_cls(
        content=b"",
        status_code=response.status_code,
        headers=dict(response.headers),
    )


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

    # Starlette resolves in declaration order. Front insertion ensures these
    # exact contracts win over FastAPI's broken default and /{full_path:path}.
    if routes:
        app.router.routes[0:0] = routes

    return {
        "registered": registered,
        "openapi_source": organ_path,
        "source_artifact": str(source_path),
    }


__all__ = ["register"]
