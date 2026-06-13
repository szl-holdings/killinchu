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
#   * register() is additive — it adds exactly its two routes and touches none of
#     the pre-existing /elite data routes
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
            "signed-loop", "SIMULATED",
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
    assert s["wired"] + s["degraded"] + s["needs_deploy"] + s["simulated"] == h["view_count"]


if __name__ == "__main__":
    test_every_view_has_a_real_endpoint()
    test_doctrine_invariants_in_map()
    test_effector_views_labelled_simulated()
    test_no_key_in_any_source_or_endpoint()
    test_register_is_additive()
    test_health_reports_honestly_without_probe()
    print("OK — all elite-wiring self-tests passed")
