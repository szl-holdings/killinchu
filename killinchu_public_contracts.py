"""Read-only public contracts for Killinchu runtime and MELT observability.

These endpoints expose measured in-process telemetry and route presence. They
do not imply model quality, external collector export, operational readiness,
or authority to actuate a defense system.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any


GITHUB_REPOSITORY = "https://github.com/szl-holdings/killinchu"
GITHUB_REPOSITORY_ID = "szl-holdings/killinchu"
GITHUB_OBSERVED_REVISION = "b2a0403fd790d4ae4b243adaa1ea764df3d091f5"
HF_SPACE_REPOSITORY = "https://huggingface.co/spaces/SZLHOLDINGS/killinchu"
HF_SPACE_ID = "SZLHOLDINGS/killinchu"
HF_OVERLAY_BASE_REVISION = "a77c8c5257e49953e042202301a3065a54908c5a"
REVISION_OBSERVED_AT = "2026-07-12T23:57:20.5396012+00:00"
_HF_HEAD_CACHE: dict[str, Any] = {"at": 0.0, "value": None}
_HF_HEAD_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_route(app: Any, path: str, method: str = "GET") -> bool:
    for route in getattr(getattr(app, "router", None), "routes", []):
        methods = getattr(route, "methods", set()) or set()
        if getattr(route, "path", None) == path and method in methods:
            return True
    return False


def _source_git_build_variable() -> dict[str, Any]:
    value = os.getenv("SZL_GIT_SHA", "unknown")
    return {
        "name": "SZL_GIT_SHA",
        "value": value,
        "state": "PRESENT_UNVERIFIED" if value != "unknown" else "UNAVAILABLE",
        "meaning": "operator-supplied source revision build metadata",
        "verification_state": "UNVERIFIED",
        "is_huggingface_deployment_revision": False,
    }


def _hf_repository_head(force: bool = False) -> dict[str, str] | None:
    """Resolve the Hub repository head; never label it as the serving process SHA."""
    now = time.monotonic()
    with _HF_HEAD_LOCK:
        cached = _HF_HEAD_CACHE.get("value")
        if not force and now - float(_HF_HEAD_CACHE["at"]) < 60:
            return dict(cached) if cached else None

    request = urllib.request.Request(
        "https://huggingface.co/api/spaces/SZLHOLDINGS/killinchu"
        "?expand[]=sha&expand[]=lastModified",
        headers={
            "User-Agent": "szl-killinchu-source-attestation/2.0",
            "Accept": "application/json",
        },
    )
    value: dict[str, str] | None = None
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.load(response)
        revision = payload.get("sha")
        last_modified = payload.get("lastModified")
        if (
            isinstance(revision, str)
            and len(revision) == 40
            and all(char in "0123456789abcdef" for char in revision)
            and isinstance(last_modified, str)
            and "T" in last_modified
        ):
            value = {
                "revision": revision,
                "last_modified": last_modified,
                "observed_at": _now(),
            }
    except Exception:
        value = None

    with _HF_HEAD_LOCK:
        _HF_HEAD_CACHE.update({"at": time.monotonic(), "value": value})
    return dict(value) if value else None


def source_attestation(force: bool = False) -> dict[str, Any]:
    """Emit the estate deployment-source shape without claiming process parity."""
    head = _hf_repository_head(force=force)
    if head is None:
        raise RuntimeError("Hugging Face repository-head evidence is unavailable")
    return {
        "schema": "szl.deployment-source/v1",
        "source": {
            "repository": GITHUB_REPOSITORY_ID,
            "commit": GITHUB_OBSERVED_REVISION,
            "path": "",
        },
        "deployment": {
            "hf_space": HF_SPACE_ID,
            "hf_revision": head["revision"],
        },
        "built_at": head["last_modified"],
        "alignment_state": "PENDING_GITHUB_SYNC",
        "extensions": {
            "schema": "szl.killinchu.deployment-source-extension/v1",
            "deployment_revision_evidence": {
                "state": "MEASURED",
                "semantics": (
                    "Hugging Face repository head measured through the Hub API; it is not "
                    "proof of the exact revision serving this response during a rolling deploy."
                ),
                "resolver": (
                    "https://huggingface.co/api/spaces/SZLHOLDINGS/killinchu"
                    "?expand[]=sha&expand[]=lastModified"
                ),
                "observed_at": head["observed_at"],
                "running_process_revision_state": "NOT_EXPOSED_IN_PROCESS",
            },
            "source_observation": {
                "repository_url": GITHUB_REPOSITORY,
                "branch": "main",
                "observed_at": REVISION_OBSERVED_AT,
                "immutable_evidence": (
                    "https://api.github.com/repos/szl-holdings/killinchu/commits/"
                    + GITHUB_OBSERVED_REVISION
                ),
                "live_branch_head_resolver": (
                    "https://api.github.com/repos/szl-holdings/killinchu/commits/main"
                ),
            },
            "overlay": {
                "repository": HF_SPACE_REPOSITORY,
                "base_revision": HF_OVERLAY_BASE_REVISION,
                "base_revision_semantics": (
                    "Hugging Face revision on which this corrective overlay was based"
                ),
            },
            "build_metadata": {
                "source_git_revision_variable": _source_git_build_variable(),
                "built_at_semantics": (
                    "Provider-reported lastModified for deployment.hf_revision; not a "
                    "verified process start time or reproducible-build attestation."
                ),
            },
        },
        "limits": [
            "PENDING_GITHUB_SYNC means GitHub/Hugging Face content parity is not claimed.",
            "deployment.hf_revision is repository-head evidence, not proof of the exact serving process revision.",
            "source.commit is a point-in-time GitHub source observation, not a live branch-head claim.",
            "SZL_GIT_SHA remains unverified source build metadata, not the Hugging Face revision.",
            "This unsigned document does not establish SLSA provenance or binary reproducibility.",
        ],
    }


def _metrics_snapshot(app: Any) -> dict[str, Any]:
    try:
        import szl_metrics_prom

        text = szl_metrics_prom.render(app)
        families = sorted(
            {
                line.split()[2]
                for line in text.splitlines()
                if line.startswith("# HELP ") and len(line.split()) >= 3
            }
        )
        samples = [
            line
            for line in text.splitlines()
            if line and not line.startswith("#")
        ]
        return {
            "state": "LIVE_IN_PROCESS",
            "metric_family_count": len(families),
            "sample_count": len(samples),
            "metric_families": families,
            "source": "/metrics",
        }
    except Exception as exc:
        return {
            "state": "UNAVAILABLE",
            "metric_family_count": 0,
            "sample_count": 0,
            "metric_families": [],
            "source": "/metrics",
            "error_type": type(exc).__name__,
        }


def melt_summary(app: Any, ns: str = "killinchu") -> dict[str, Any]:
    metrics = _metrics_snapshot(app)
    metrics_route = _has_route(app, "/metrics")
    mesh_route = _has_route(app, f"/api/{ns}/v1/mesh/state")
    live = metrics_route and metrics["state"] == "LIVE_IN_PROCESS"
    return {
        "schema": "szl.killinchu.melt-summary/v1",
        "observed_at": _now(),
        "transport_state": "REACHABLE",
        "evidence_state": "LIVE" if live else "UNAVAILABLE",
        "authority_state": "READ_ONLY",
        "scope": "MELT runtime observability",
        "signals": {
            "metrics": metrics,
            "events": {
                "state": "IN_PROCESS",
                "basis": "request and receipt events remain within the running process unless a durable subsystem records them",
            },
            "logs": {
                "state": "IN_PROCESS",
                "basis": "structured application logs are emitted by the runtime; no public log corpus is exposed here",
            },
            "traces": {
                "state": "EXPORT_UNAVAILABLE",
                "basis": "OTLP export is not enabled in this public Space build",
            },
        },
        "contracts": {
            "metrics_route_registered": metrics_route,
            "mesh_state_route_registered": mesh_route,
            "metrics_endpoint": "/metrics",
            "mesh_endpoint": f"/api/{ns}/v1/mesh/state",
        },
        "limits": [
            "LIVE means measured in this process, not an uptime SLA.",
            "No external collector, distributed trace completeness, model quality, or business outcome is claimed.",
            "This endpoint is read-only and performs no effector action.",
        ],
    }


def runtime_status(app: Any, ns: str = "killinchu") -> dict[str, Any]:
    route_count = len(getattr(getattr(app, "router", None), "routes", []))
    return {
        "schema": "szl.killinchu.runtime-status/v1",
        "observed_at": _now(),
        "service": ns,
        "transport_state": "REACHABLE",
        "evidence_state": "COMPUTED",
        "verification_state": "STRUCTURAL_ONLY",
        "authority_state": "READ_ONLY",
        "doctrine": {
            "version": "v11",
            "locked_proven_count": 8,
            "locked_proven_state": "REPOSITORY_DECLARED",
            "lambda": "Conjecture 1 (OPEN)",
        },
        "runtime": {
            "route_count": route_count,
            "source_git_revision_variable": _source_git_build_variable(),
            "huggingface_revision_evidence": {
                "running_process_revision_state": "NOT_EXPOSED_IN_PROCESS",
                "repository_head_state": "RESOLVE_EXTERNALLY",
                "repository_head_resolver": "https://huggingface.co/api/spaces/SZLHOLDINGS/killinchu",
                "repository_head_json_field": "sha",
            },
            "build_time": os.getenv("SZL_BUILD_TIME", "unknown"),
        },
        "contracts": {
            "experience_manifest": f"/api/{ns}/v1/experience/manifest",
            "openapi": f"/api/{ns}/v1/openapi.json",
            "melt": f"/api/{ns}/v1/melt/summary",
            "metrics": "/metrics",
            "readiness": f"/api/{ns}/readyz",
            "source_attestation": "/.well-known/szl-source.json",
        },
        "limits": [
            "Reachability and registered routes do not establish data freshness, model quality, or mission readiness.",
            "Defense effectors remain simulated and human-controlled.",
            "REPOSITORY_DECLARED is not a substitute for an immutable Lean kernel receipt at the deployed source revision.",
        ],
    }


def register(app: Any, ns: str = "killinchu") -> dict[str, Any]:
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _health(_request):
        payload = runtime_status(app, ns)
        payload["schema"] = "szl.killinchu.health/v1"
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    async def _status(_request):
        return JSONResponse(runtime_status(app, ns), headers={"Cache-Control": "no-store"})

    async def _melt(_request):
        return JSONResponse(melt_summary(app, ns), headers={"Cache-Control": "no-store"})

    async def _source_attestation(_request):
        try:
            payload = source_attestation(
                force=_request.query_params.get("refresh") == "1"
            )
            status_code = 200
        except RuntimeError:
            payload = {
                "schema": "szl.source-attestation-unavailable/v1",
                "state": "UNAVAILABLE",
                "observed_at": _now(),
                "detail": "Hugging Face repository-head evidence could not be measured.",
            }
            status_code = 503
        return JSONResponse(
            payload,
            status_code=status_code,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    routes = [
        Route("/health", _health, methods=["GET"], name="killinchu_public_health"),
        Route(
            f"/api/{ns}/v1/status",
            _status,
            methods=["GET"],
            name="killinchu_public_status",
        ),
        Route(
            f"/api/{ns}/v1/melt/summary",
            _melt,
            methods=["GET"],
            name="killinchu_melt_summary",
        ),
        Route(
            "/.well-known/szl-source.json",
            _source_attestation,
            methods=["GET"],
            name="killinchu_source_attestation",
        ),
    ]
    existing = {getattr(route, "name", None) for route in app.router.routes}
    new = [route for route in routes if route.name not in existing]
    app.router.routes[0:0] = new
    return {
        "schema": "szl.killinchu.public-contract-registration/v1",
        "routes": [route.path for route in new],
    }


if __name__ == "__main__":
    from fastapi import FastAPI

    candidate = FastAPI()
    candidate.add_api_route("/metrics", lambda: "", methods=["GET"])
    candidate.add_api_route(
        "/api/killinchu/v1/mesh/state", lambda: {}, methods=["GET"]
    )
    result = register(candidate)
    assert len(result["routes"]) == 4
    assert runtime_status(candidate)["transport_state"] == "REACHABLE"
    print("SELFTEST OK")
