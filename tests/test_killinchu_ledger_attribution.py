"""Real HTTP routing regression for attribution across the two receipt stores."""
import ast
import hashlib
import json
from pathlib import Path
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from killinchu_ledger import DURABLE_EXTERNAL, LedgerRuntime
from killinchu_ledger_attribution import harden_with_canonical_ledger
import szl_be_hardening as hardening


PATHS = ["/readyz", "/api/killinchu/v1/readyz", "/honest", "/api/killinchu/v1/honest"]


def _digest(receipt, parents):
    return hashlib.sha256(json.dumps([receipt, parents], sort_keys=True).encode()).hexdigest()


def _runtime():
    runtime = LedgerRuntime([], threading.RLock(), _digest)
    runtime.startup()
    receipt = {"kind": "LOCAL_TEST", "schema": "test/v1"}
    runtime.append({"index": 0, "receipt": receipt, "parents": [],
                    "digest": _digest(receipt, []), "dsse": {"signatures": []}})
    return runtime


def _app(tmp_path, provider):
    app = FastAPI()
    original_class = app.router.route_class
    database = tmp_path / "backend.sqlite3"

    def bind(host, *, organ):
        return hardening.harden(host, organ=organ, khipu_path=str(database))

    harden_with_canonical_ledger(app, bind, ledger_readiness=provider)
    assert app.router.route_class is original_class
    return app, database


@pytest.mark.parametrize("path", PATHS)
def test_active_early_routes_report_canonical_ephemeral_ledger(tmp_path, path):
    runtime = _runtime()
    calls = []

    def provider():
        calls.append(True)
        return runtime.readiness(recover=False)

    app, database = _app(tmp_path, provider)
    before = database.read_bytes()
    before_nodes = runtime.snapshot()
    before_routes = list(app.router.routes)
    response = TestClient(app).get(path)
    assert response.status_code == 200
    body = response.json()
    assert body["ledger_role"] == "CANONICAL_RECEIPT_LEDGER"
    assert body["ledger"]["durability_state"] == "EPHEMERAL"
    assert body["ledger"]["persistence_scope"] == "PROCESS_MEMORY"
    assert body["ledger"]["production_ready"] is False
    assert body["ledger"]["integrity"]["nodes"] == 1
    assert body["receipt_minted"] is False
    assert response.headers["cache-control"] == "no-store"
    assert calls == [True]
    assert runtime.snapshot() == before_nodes
    assert runtime.readiness(recover=False)["recovery"]["attempts"] == 0
    assert database.read_bytes() == before
    assert app.router.routes == before_routes
    if path.endswith("readyz"):
        diagnostic = body["backend_store_diagnostics"]
        assert diagnostic["depth"] == 0
        assert diagnostic["ledger_role"] == "BACKEND_HARDENING_DIAGNOSTIC_STORE"
        assert diagnostic["provider_persistence"] == "UNKNOWN"
        assert diagnostic["production_ready"] is False
        assert "khipu_durable" not in body
    else:
        assert "EPHEMERAL" in body["honest_labels"]["persistence"]
        assert "durable=True" not in body["honest_labels"]["persistence"]
        assert "Conjecture 1" in body["honest_labels"]["lambda"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("failure", ["missing", "raises", "malformed"])
def test_missing_or_invalid_canonical_provider_fails_closed(tmp_path, path, failure):
    if failure == "missing":
        provider = None
    elif failure == "raises":
        def provider():
            raise RuntimeError("SECRET_SENTINEL_DO_NOT_EXPORT")
    else:
        provider = lambda: {"ready": True, "production_ready": True}
    app, _ = _app(tmp_path, provider)
    response = TestClient(app).get(path)
    assert response.status_code == 503
    assert response.json()["ledger"]["production_ready"] is False
    assert response.json()["ledger"]["ready"] is False
    assert "SECRET_SENTINEL" not in response.text


@pytest.mark.parametrize("changes", [
    {"ready": 1}, {"production_ready": 1}, {"production_ready": True},
    {"production_ready": True, "durability_state": "DURABLE_EXTERNAL",
     "production_readiness_basis": "LEGACY_ADAPTER_CONTRACT"},
    {"integrity": {"verified": False}},
])
def test_malformed_readiness_cannot_be_promoted(tmp_path, changes):
    state = _runtime().readiness(recover=False)
    state.update(changes)
    app, _ = _app(tmp_path, lambda: state)
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    assert response.json()["ledger"]["production_ready"] is False


@pytest.mark.parametrize("scope", ["LOCAL_FILESYSTEM", "EXTERNAL_SERVICE"])
@pytest.mark.parametrize("path", PATHS)
def test_explicit_external_adapter_contract_is_reported_without_get_replay(tmp_path, scope, path):
    # This controlled adapter proves contract handling only, not provider
    # persistence, independent authorization, or a production deployment.
    class ExplicitAdapter:
        startup_calls = 0
        replay_calls = 0

        def startup(self):
            self.startup_calls += 1

        def replay(self):
            self.replay_calls += 1
            return []

        def append(self, node):
            raise AssertionError("GET cannot append")

        def verify_integrity(self, nodes):
            return {"verified": list(nodes) == []}

        def readiness(self):
            return {"ready": True, "production_ready": True, "persistence_scope": scope}

    adapter = ExplicitAdapter()
    runtime = LedgerRuntime([], threading.RLock(), _digest,
                            mode=DURABLE_EXTERNAL, adapter=adapter)
    runtime.startup()
    before_attempts = runtime.readiness(recover=False)["recovery"]["attempts"]
    app, database = _app(tmp_path, lambda: runtime.readiness(recover=False))
    before = database.read_bytes()
    response = TestClient(app).get(path)
    assert response.status_code == 200
    ledger = response.json()["ledger"]
    assert ledger["durability_state"] == "DURABLE_EXTERNAL"
    assert ledger["ready"] is True
    assert ledger["production_ready"] is True
    assert ledger["production_readiness_basis"] == "EXPLICIT_ADAPTER_CONTRACT"
    assert ledger["persistence_scope"] == scope
    assert adapter.startup_calls == adapter.replay_calls == 1
    assert ledger["recovery"]["attempts"] == before_attempts
    assert database.read_bytes() == before
    assert response.json()["receipt_minted"] is False
    if path.endswith("readyz"):
        assert response.json()["backend_store_diagnostics"]["production_ready"] is False


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), object()])
@pytest.mark.parametrize("path", PATHS)
def test_non_json_or_nonfinite_canonical_state_fails_closed(tmp_path, invalid, path):
    state = _runtime().readiness(recover=False)
    state["invalid"] = invalid
    app, _ = _app(tmp_path, lambda: state)
    response = TestClient(app).get(path)
    assert response.status_code == 503
    assert response.json()["ledger"]["ready"] is False
    assert response.json()["ledger"]["production_ready"] is False


def test_original_handler_exception_retains_framework_failure(tmp_path):
    runtime = _runtime()
    app, _ = _app(tmp_path, lambda: runtime.readiness(recover=False))

    def fail():
        raise RuntimeError("original handler failure")

    app.state.be_khipu.verify = fail
    original_app = FastAPI()
    hardening.harden(original_app, organ="killinchu",
                     khipu_path=str(tmp_path / "original-backend.sqlite3"))
    original_app.state.be_khipu.verify = fail
    original = TestClient(original_app).get("/readyz")
    response = TestClient(app).get("/readyz")
    assert original.status_code == response.status_code == 500
    assert original.json()["error"]["code"] == response.json()["error"]["code"]
    assert "ledger" not in response.json()


def test_backend_chain_failure_is_still_an_independent_gate(tmp_path):
    runtime = _runtime()
    app, _ = _app(tmp_path, lambda: runtime.readiness(recover=False))
    app.state.be_khipu.verify = lambda: (False, 2, 1)
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    assert response.json()["ledger"]["ready"] is True
    assert response.json()["backend_store_diagnostics"]["chain_ok"] is False


def test_canonical_unready_ledger_cannot_use_green_backend_store(tmp_path):
    runtime = LedgerRuntime([], threading.RLock(), _digest)
    app, _ = _app(tmp_path, lambda: runtime.readiness(recover=False))
    response = TestClient(app).get("/api/killinchu/v1/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["ledger"]["ready"] is False
    assert body["backend_store_diagnostics"]["chain_ok"] is True
    assert runtime.readiness(recover=False)["startup_state"] == "NOT_STARTED"


def test_late_shadow_route_cannot_override_early_canonical_attribution(tmp_path):
    runtime = _runtime()
    app, _ = _app(tmp_path, lambda: runtime.readiness(recover=False))
    first = next(route for route in app.routes if getattr(route, "path", None) == PATHS[-1])

    @app.get(PATHS[-1])
    async def later_shadow():
        return {"production_ready": True, "marker": "must not win"}

    response = TestClient(app).get(PATHS[-1])
    assert response.status_code == 200
    assert response.json()["ledger"]["production_ready"] is False
    assert "marker" not in response.json()
    assert next(route for route in app.routes if getattr(route, "path", None) == PATHS[-1]) is first


def test_provider_is_resolved_at_request_without_startup_or_replay_on_get(tmp_path):
    holder = {}
    app, _ = _app(tmp_path, lambda: holder["runtime"].readiness(recover=False))
    client = TestClient(app)
    assert client.get("/honest").status_code == 503
    holder["runtime"] = _runtime()
    assert client.get("/honest").status_code == 200
    assert holder["runtime"].readiness(recover=False)["recovery"]["attempts"] == 0


def test_route_class_restores_when_hardening_registration_fails():
    app = FastAPI()
    original_class = app.router.route_class

    def fail(host, *, organ):
        raise RuntimeError("registration failure")

    with pytest.raises(RuntimeError, match="registration failure"):
        harden_with_canonical_ledger(app, fail, ledger_readiness=None)
    assert app.router.route_class is original_class


def test_host_wiring_uses_read_only_provider_and_both_dockerfiles_ship_it():
    root = Path(__file__).resolve().parents[1]
    source = ast.parse((root / "serve.py").read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(source) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "harden_with_canonical_ledger"]
    assert len(calls) == 1
    provider = next(kw.value for kw in calls[0].keywords if kw.arg == "ledger_readiness")
    assert isinstance(provider, ast.Lambda)
    assert ast.unparse(provider.body) == "_LEDGER_RUNTIME.readiness(recover=False)"
    for dockerfile in [root / "Dockerfile", root / "deploy/space/Dockerfile"]:
        assert "COPY killinchu_ledger_attribution.py ./killinchu_ledger_attribution.py" in dockerfile.read_text(encoding="utf-8")
