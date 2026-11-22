'''Peer regression for the optional observed backend boundary; no live model claim.'''
import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

import szl_agentic_loop as loop


def stub_metadata(monkeypatch):
    rag = {"built": True, "chunks": 4, "state": "READY"}
    monkeypatch.setitem(sys.modules, "a11oy_org_rag", SimpleNamespace(status=lambda: rag))
    monkeypatch.setitem(sys.modules, "szl_formulas", SimpleNamespace(FORMULA_NAMES=[]))
    monkeypatch.setitem(sys.modules, "szl_anatomy_routes", SimpleNamespace(CHAKRAS=[]))
    return rag


def read_mesh(signer):
    app = Starlette()
    # This shared mesh is an A11oy namespace surface; the peer keeps that boundary.
    loop.register(app, "a11oy", signer)
    with TestClient(app) as client:
        response = client.get("/api/a11oy/v1/hatun/mesh")
    assert response.status_code == 200
    body = response.json()
    assert body["get_mints_receipt"] is False
    return body


def test_missing_optional_provider_cannot_make_built_index_ready(monkeypatch):
    stub_metadata(monkeypatch)
    monkeypatch.setitem(sys.modules, "ayllu", None)
    monkeypatch.setitem(sys.modules, "ayllu.backend", None)
    calls = []

    def signer(payload):
        calls.append(payload)
        raise AssertionError("mesh GET must not sign")

    brain = read_mesh(signer)["second_brain"]
    assert brain["state"] == "UNAVAILABLE"
    assert brain["ready_for_grounded_navigation"] is False
    assert brain["index_built"] is True
    assert calls == []


@pytest.mark.parametrize("available", [True, False])
def test_observation_is_forwarded_off_loop_without_asserting_a_model(monkeypatch, available):
    rag = stub_metadata(monkeypatch)
    runtime = {"fixture_inventory": {"available": available}}
    calls = {"backend": 0, "binding": 0, "signer": 0}

    def backend_status():
        calls["backend"] += 1
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        return runtime

    def binding(*, namespace, backend_status, rag_status):
        calls["binding"] += 1
        assert namespace == "a11oy"
        assert backend_status is runtime
        assert rag_status is rag
        return {"state": "OBSERVED_FIXTURE" if available else "UNAVAILABLE",
                "ready_for_grounded_navigation": available}

    def signer(payload):
        calls["signer"] += 1
        raise AssertionError("mesh GET must not sign")

    package = ModuleType("ayllu")
    package.__path__ = []
    backend = ModuleType("ayllu.backend")
    backend.backend_status = backend_status
    model_binding = ModuleType("ayllu.model_binding")
    model_binding.second_brain_binding = binding
    for name, module in (("ayllu", package), ("ayllu.backend", backend),
                         ("ayllu.model_binding", model_binding)):
        monkeypatch.setitem(sys.modules, name, module)
    brain = read_mesh(signer)["second_brain"]
    assert brain["state"] == ("OBSERVED_FIXTURE" if available else "UNAVAILABLE")
    assert brain["ready_for_grounded_navigation"] is available
    assert calls == {"backend": 1, "binding": 1, "signer": 0}


def test_killinchu_namespace_keeps_existing_route_boundary(monkeypatch):
    stub_metadata(monkeypatch)
    app = Starlette()
    loop.register(app, "killinchu", None)
    with TestClient(app) as client:
        assert client.get("/api/killinchu/v1/agent/evidence").status_code == 200
        assert client.get("/api/killinchu/v1/hatun/mesh").status_code == 404
        assert client.get("/api/hatun/mesh").status_code == 404
