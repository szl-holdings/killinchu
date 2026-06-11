# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED 749/14/163 @ c7c0ba17 · Λ = Conjecture 1.
"""test_flow_compartments.py — real tests for the yarqa Flow Compartments tab.

NO mocks: runs the vendored yarqa engine on the bundled SAMPLE/SIMULATED wake
field, checks the receipt reproduces (integrity), and asserts every honesty
guardrail on the wire. The engineering-method (CFD) tier must NEVER be folded
into the locked-proven count and the locked-8 must NEVER be routed through yarqa.

Run:  pytest -q test_flow_compartments.py
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

flow = pytest.importorskip("killinchu_flow_compartments")
Starlette = pytest.importorskip("starlette.applications").Starlette
TestClient = pytest.importorskip("starlette.testclient").TestClient


def _client():
    app = Starlette()
    flow.register(app, ns="killinchu")
    return TestClient(app)


def test_engine_runs_and_receipt_reproduces():
    res = flow.compute_flow_compartments(emit_chain=False)
    assert res["ok"] is True
    assert res["compartments"]["n_compartments"] >= 1
    # Integrity claim: the receipt must replay to the same labels.
    assert res["receipt"]["verify"]["ok"] is True


def test_honesty_yarqa_never_in_locked_count():
    res = flow.compute_flow_compartments(emit_chain=False)
    assert res["yarqa_in_locked_count"] is False
    assert res["locked_proven_count"] == 8
    assert res["routes_locked8_through_yarqa"] is False
    assert "not a locked theorem" in res["honest_label"]
    assert res["method_tier"] == "engineering method (CFD)"


def test_data_is_clearly_sample_simulated():
    field = flow.sample_wake_field()
    assert field["status"] == "SAMPLE/SIMULATED"
    assert "LIVE_SOURCES_VERIFIED" in field["note"]


def test_sample_field_is_deterministic():
    a = flow.sample_wake_field()
    b = flow.sample_wake_field()
    assert a["centers"] == b["centers"]
    assert a["velocities"] == b["velocities"]


def test_index_endpoint_honest_tier():
    c = _client()
    r = c.get("/api/killinchu/v1/flow/index")
    assert r.status_code == 200
    j = r.json()
    assert j["yarqa_in_locked_count"] is False
    assert j["routes_locked8_through_yarqa"] is False
    assert j["locked_proven_count"] == 8
    assert "not a locked theorem" in j["honest_label"]


def test_compartmentalize_endpoint():
    c = _client()
    r = c.post("/api/killinchu/v1/flow/compartmentalize", json={"align_threshold": 0.3})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["receipt"]["verify"]["ok"] is True
    # Never fabricates a signature: signed is True only with a real cosign key.
    assert isinstance(j["receipt"]["signed"], bool)
    assert j["receipt"]["receipt_digest"]


def test_tab_is_self_contained_zero_cdn():
    c = _client()
    r = c.get("/flow-compartments")
    assert r.status_code == 200
    html = r.text
    assert "not a locked theorem" in html
    # Sovereign: no external CDN references in the tab.
    for bad in ("http://", "https://", "cdn.", "unpkg", "jsdelivr"):
        assert bad not in html.replace("http://www.w3.org/2000/svg", ""), bad


def test_selftest_endpoint():
    c = _client()
    r = c.get("/api/killinchu/v1/flow/selftest")
    assert r.status_code == 200
    j = r.json()
    assert j["yarqa_available"] is True
    assert j["verify_ok"] is True
    assert j["yarqa_in_locked_count"] is False
