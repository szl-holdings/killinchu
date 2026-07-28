# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# test_elite_wiring.py — REAL, committed guard for the /elite view-wiring audit
# layer (wire-elite-views). It proves, with NO MOCKS of the logic under test:
#
#   * every /elite view in ELITE_WIRING declares at least one real data endpoint
#   * the static wiring map carries the doctrine invariants (v11, Λ=Conjecture 1,
#     locked-8) and never asserts reachability
#   * effector / weapon-target / intercept views are labelled SIMULATED (doctrine
#     v11: killinchu NEVER claims a real kinetic effect)
#   * no committed leader/source string smuggles in an API key
#   * register() is additive — it adds its audit and preview routes and touches
#     none of the pre-existing /elite data routes
#
# The module is pure stdlib; this test does not require network.
from __future__ import annotations

import re

import killinchu_elite_wiring as kew


def test_every_view_has_a_real_endpoint():
    assert len(kew.ELITE_WIRING) >= 16, "expected the full /elite view set"
    for vid, w in kew.ELITE_WIRING.items():
        assert w["endpoints"], f"{vid} has no data endpoint (would be an empty panel)"
        for ep in w["endpoints"]:
            assert ep.startswith("/api/") or ep.startswith("/metrics"), \
                f"{vid} endpoint {ep!r} is not a real API route"
        assert w["data_class"] in {
            "live-feed", "leader-cited", "real-compute", "curated",
            "signed-loop", "SIMULATED", "interop-standard",
        }, f"{vid} has an unknown data_class {w['data_class']!r}"


def test_doctrine_invariants_in_map():
    m = kew.audit_map("killinchu")
    assert m["doctrine"] == "v11"
    assert m["lambda"] == "Conjecture 1"
    assert m["locked_formulas"] == 8
    assert m["view_count"] == len(kew.ELITE_WIRING)


def test_effector_views_labelled_simulated():
    # Effector / weapon-target / intercept demos MUST be SIMULATED by doctrine.
    must_be_sim = {"operate", "cuas_intercept", "cuas_triage"}
    for vid in must_be_sim:
        assert kew.ELITE_WIRING[vid]["data_class"] == "SIMULATED", \
            f"{vid} must be SIMULATED (no real kinetic effect claim allowed)"
    assert set(must_be_sim).issubset(set(kew.SIMULATED_VIEWS))


def test_no_key_in_any_source_or_endpoint():
    blob = repr(kew.ELITE_WIRING)
    # honest doctrine: no api_key / token / bearer in any committed string
    assert not re.search(r"(?i)(api[_-]?key|access[_-]?token|bearer\s+[A-Za-z0-9])", blob)
    assert "key=" not in blob.lower()


def test_register_is_additive():
    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/api/killinchu/v1/posture/drift")
    async def _pre_existing():  # the audit must NOT clobber a real data route
        return {"ok": True, "pre_existing": True}

    before = {(r.path, frozenset(getattr(r, "methods", set()) or set()))
              for r in app.routes}
    info = kew.register(app, ns="killinchu")
    assert info["registered"] is True
    after = {(r.path, frozenset(getattr(r, "methods", set()) or set()))
             for r in app.routes}
    added = after - before
    added_paths = {p for p, _ in added}
    assert added_paths == {
        "/api/killinchu/v1/elite/wiring",
        "/api/killinchu/v1/elite/wiring/health",
        "/api/killinchu/v1/elite/incident-command",
        "/api/killinchu/v1/elite/authorization/lease/preview",
    }, f"register added unexpected routes: {added_paths}"
    # the pre-existing data route is still present, untouched
    assert ("/api/killinchu/v1/posture/drift",
            frozenset({"GET"})) in after


def test_health_reports_honestly_without_probe():
    from fastapi import FastAPI
    app = FastAPI()
    # register only two of the data routes -> the rest must be 'needs-deploy',
    # never silently 'wired'. SIMULATED stays SIMULATED.
    @app.get("/api/killinchu/v1/posture/drift")
    async def _a():
        return {"ok": True}

    @app.get("/api/killinchu/v1/topology/health")
    async def _b():
        return {"ok": True}

    h = kew.health(app, ns="killinchu", probe=False)
    by_view = {r["view"]: r for r in h["views"]}
    assert by_view["operate"]["verdict"] == "SIMULATED"
    assert by_view["cuas_intercept"]["verdict"] == "SIMULATED"
    # u_posture has multiple endpoints incl. posture/drift -> at least one route
    # registered -> 'wired'; a view with no registered route -> 'needs-deploy'
    assert by_view["u_posture"]["verdict"] == "wired"
    assert by_view["scaling"]["verdict"] == "needs-deploy"
    s = h["summary"]
    assert s["simulated"] == len(kew.SIMULATED_VIEWS)
    assert (
        s["wired"] + s["cached"] + s["degraded"]
        + s["needs_deploy"] + s["simulated"]
    ) == h["view_count"]


def test_health_recognizes_late_included_router_routes():
    """FastAPI's lazy include_router mounts must count as real wiring.

    Recent FastAPI releases can expose an included router as a private wrapper
    with no literal ``path`` attribute. The ASGI router still serves its
    children. This is the exact production shape used by the AIS and CoT
    modules, and the wiring audit must ask the router rather than report a
    false NEEDS_DEPLOY.
    """
    from fastapi import APIRouter, FastAPI

    app = FastAPI()
    kew.register(app, ns="killinchu")

    late = APIRouter()

    @late.get("/api/killinchu/v1/ais/sources")
    async def _ais_sources():
        return {"sources_wired": 2}

    @late.get("/api/killinchu/v1/cot/status")
    async def _cot_status():
        return {"live": {"cot_xml_export": True}}

    app.include_router(late)

    @app.get("/{full_path:path}")
    async def _spa_catch_all(full_path: str):
        return {"page": full_path}

    h = kew.health(app, ns="killinchu", probe=False)
    by_view = {r["view"]: r for r in h["views"]}
    assert by_view["ais_aug2024"]["verdict"] == "wired"
    assert by_view["cot_interop"]["verdict"] == "wired"
    assert by_view["operate"]["verdict"] == "SIMULATED"
    assert by_view["cuas_intercept"]["verdict"] == "SIMULATED"
    assert by_view["cuas_triage"]["verdict"] == "SIMULATED"
    # The SPA catch-all must not turn an actually absent data route green.
    assert by_view["scaling"]["verdict"] == "needs-deploy"


def test_incident_command_distinguishes_verified_from_measured():
    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/api/killinchu/v1/scaling/summary")
    async def _scaling():
        return {"status": "available"}

    command = kew.incident_command(app, ns="killinchu", probe=False)
    by_view = {row["view"]: row for row in command["queue"]}

    assert command["probe_requested"] is False
    assert command["probe_performed"] is False
    assert command["evidence_label"] == "VERIFIED"
    assert command["next_allowed_action"] == "REQUEST_READ_ONLY_PROBE"
    assert command["executable"] is False
    assert by_view["scaling"]["source_state"] == "CACHED"
    assert all(row["evidence_label"] == "VERIFIED" for row in command["queue"])
    assert all(row["executable"] is False for row in command["queue"])
    assert command["queue_digest"] == kew._frontier_sha(command["queue"])


def test_health_deduplicates_and_bounds_live_probes(monkeypatch):
    from fastapi import FastAPI

    app = FastAPI()
    calls = []

    @app.get("/api/killinchu/v1/probe/a")
    async def _probe_a():
        calls.append("a")
        return {"status": "available"}

    @app.get("/api/killinchu/v1/probe/b")
    async def _probe_b():
        calls.append("b")
        return {"status": "available"}

    monkeypatch.setattr(kew, "ELITE_WIRING", {
        "first": {
            "endpoints": ["/api/killinchu/v1/probe/a"],
            "data_class": "live-feed",
            "leaders": [],
            "note": "first",
        },
        "second": {
            "endpoints": [
                "/api/killinchu/v1/probe/a",
                "/api/killinchu/v1/probe/b",
            ],
            "data_class": "live-feed",
            "leaders": [],
            "note": "second",
        },
    })

    result = kew.health(app, probe=True, probe_limit=1)
    by_view = {row["view"]: row for row in result["views"]}

    assert calls == ["a"]
    assert result["probe_performed"] is True
    assert result["unique_probes"] == 1
    assert by_view["first"]["endpoints"][0]["status"] == 200
    assert by_view["second"]["endpoints"][0]["status"] == 200
    assert by_view["second"]["endpoints"][1]["status"] == "probe-budget-exhausted"
    assert by_view["second"]["verdict"] == "cached"
    assert sum(result["summary"].values()) == result["view_count"]


def test_incident_command_keeps_unprobed_views_verified(monkeypatch):
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/api/killinchu/v1/probe/a")
    async def _probe_a():
        return {"status": "available"}

    @app.get("/api/killinchu/v1/probe/b")
    async def _probe_b():
        return {"status": "available"}

    monkeypatch.setattr(kew, "ELITE_WIRING", {
        "measured": {
            "endpoints": ["/api/killinchu/v1/probe/a"],
            "data_class": "live-feed",
            "leaders": [],
            "note": "measured",
        },
        "budget_exhausted": {
            "endpoints": ["/api/killinchu/v1/probe/b"],
            "data_class": "live-feed",
            "leaders": [],
            "note": "not probed",
        },
    })

    command = kew.incident_command(app, probe=True, probe_limit=1)
    by_view = {row["view"]: row for row in command["queue"]}

    assert command["probe_performed"] is True
    assert command["unique_probes"] == 1
    assert command["evidence_label"] == "VERIFIED"
    assert by_view["measured"]["probe_complete"] is True
    assert by_view["measured"]["evidence_label"] == "MEASURED"
    assert by_view["budget_exhausted"]["probe_performed"] is False
    assert by_view["budget_exhausted"]["probe_complete"] is False
    assert by_view["budget_exhausted"]["evidence_label"] == "VERIFIED"
    assert by_view["budget_exhausted"]["source_state"] == "CACHED"


def test_health_marks_failed_probe_degraded(monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.get("/api/killinchu/v1/probe/failure")
    async def _probe_failure():
        return JSONResponse({"status": "unavailable"}, status_code=503)

    monkeypatch.setattr(kew, "ELITE_WIRING", {
        "failure": {
            "endpoints": ["/api/killinchu/v1/probe/failure"],
            "data_class": "live-feed",
            "leaders": [],
            "note": "failure",
        },
    })

    result = kew.health(app, probe=True, probe_limit=1)

    assert result["views"][0]["endpoints"][0]["status"] == 503
    assert result["views"][0]["verdict"] == "degraded"
    assert result["summary"]["degraded"] == 1
    assert sum(result["summary"].values()) == result["view_count"]


def test_incident_command_marks_non_200_probe_degraded(monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import Response

    app = FastAPI()

    @app.get("/api/killinchu/v1/probe/non-200")
    async def _probe_non_200():
        return Response(status_code=204)

    monkeypatch.setattr(kew, "ELITE_WIRING", {
        "non_200": {
            "endpoints": ["/api/killinchu/v1/probe/non-200"],
            "data_class": "live-feed",
            "leaders": [],
            "note": "non-200",
        },
    })

    command = kew.incident_command(app, probe=True, probe_limit=1)
    item = command["queue"][0]

    assert item["affected_endpoints"][0]["status"] == 204
    assert item["wiring_verdict"] == "degraded"
    assert item["source_state"] == "DEGRADED"
    assert item["priority"] == 75
    assert item["recommended_action"] == "INVESTIGATE_SOURCE_FRESHNESS"
    assert command["summary"]["degraded"] == 1


def test_lease_preview_withholds_without_crypto_and_never_forwards(monkeypatch):
    from datetime import datetime, timedelta, timezone

    captured = {}

    def _intercept(action, sign_fn=None, ns="killinchu", forward=True):
        captured.update({
            "action": action,
            "sign_fn": sign_fn,
            "forward": forward,
        })
        return {"verdict": "REQUIRE-HUMAN-CONFIRM", "allowed": False}

    marker_signer = object()
    monkeypatch.setattr(kew, "intercept_action", _intercept)
    now = datetime.now(timezone.utc)
    decision_digest = "a" * 64
    preview = kew.authorization_lease_preview({
        "action": "OBSERVE",
        "decision_digest": decision_digest,
        "uncertainty": 0.1,
        "lease": {
            "lease_id": "lease-1",
            "issuer": "operator",
            "subject": "killinchu",
            "mission_id": "mission-1",
            "not_before": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
            "max_uncertainty": 0.2,
            "decision_digest": decision_digest,
            "allowed_actions": ["OBSERVE"],
        },
    }, sign_fn=marker_signer)

    assert preview["verdict"] == "WITHHOLD"
    assert preview["blockers"] == ["CRYPTOGRAPHIC_LEASE_VERIFIER_UNAVAILABLE"]
    assert preview["signature_verification"] == "UNAVAILABLE"
    assert preview["evidence_label"] == "VERIFIED"
    assert preview["executable"] is False
    assert captured["sign_fn"] is marker_signer
    assert captured["forward"] is False
    assert captured["action"]["executable"] is False


def test_lease_preview_rejects_nonfinite_uncertainty(monkeypatch):
    monkeypatch.setattr(
        kew,
        "intercept_action",
        lambda action, sign_fn=None, ns="killinchu", forward=True: {
            "verdict": "REQUIRE-HUMAN-CONFIRM",
            "allowed": False,
        },
    )
    preview = kew.authorization_lease_preview({
        "action": "OBSERVE",
        "uncertainty": "nan",
        "lease": {"allowed_actions": ["OBSERVE"], "max_uncertainty": 1.0},
    })
    assert "INVALID_UNCERTAINTY" in preview["blockers"]
    assert preview["verdict"] == "WITHHOLD"


if __name__ == "__main__":
    test_every_view_has_a_real_endpoint()
    test_doctrine_invariants_in_map()
    test_effector_views_labelled_simulated()
    test_no_key_in_any_source_or_endpoint()
    test_register_is_additive()
    test_health_reports_honestly_without_probe()
    print("OK — all elite-wiring self-tests passed")
