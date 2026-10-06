"""Actual backend GET/HEAD reads observe state; explicit writers still commit."""
from copy import deepcopy
import hashlib
import sqlite3
import sys
import threading
from types import SimpleNamespace
import urllib.request

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from starlette.routing import Match

import szl_be_hardening as backend
import szl_dsse


ORGAN = "passive"
BASE = "/api/passive/v1"


@pytest.fixture
def host(tmp_path):
    app = FastAPI()
    database = tmp_path / "backend.sqlite3"
    assert backend.harden(app, organ=ORGAN, khipu_path=str(database))["ok"]

    @app.get("/{path:path}")
    async def fallback(path: str):
        return {"fallback": path}

    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield app, client, database
    finally:
        if app.state.be_khipu._db is not None:
            app.state.be_khipu._db.close()


def _guards(monkeypatch, host, *, allow_writer=False, observe_sql=True):
    calls = {"sign": 0, "key_load": 0, "connect": 0, "emit": 0, "network": 0}

    def forbidden(name):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError("read attempted " + name)
        return fail

    monkeypatch.setattr(szl_dsse, "sign_payload", forbidden("sign"))
    monkeypatch.setattr(szl_dsse, "_load_private_key", forbidden("key_load"))
    monkeypatch.setattr(sqlite3, "connect", forbidden("connect"))
    monkeypatch.setattr(urllib.request, "urlopen", forbidden("network"))
    original = host[0].state.be_khipu.emit

    def emit(*args, **kwargs):
        calls["emit"] += 1
        if not allow_writer:
            raise AssertionError("read attempted receipt emission")
        return original(*args, **kwargs)

    monkeypatch.setattr(host[0].state.be_khipu, "emit", emit)
    sql = []
    if observe_sql:
        host[0].state.be_khipu._db.set_trace_callback(sql.append)
    return calls, sql


def _assert_route(host, path, method):
    scope = {"type": "http", "path": path, "method": method.upper(), "root_path": ""}
    first = next(route for route in host[0].router.routes if route.matches(scope)[0] is Match.FULL)
    assert first.endpoint.__module__ == "szl_be_hardening"


def _assert_unsigned(response, method):
    assert response.headers["cache-control"] == "no-store"
    if method == "head":
        assert response.content == b""
    else:
        body = response.json()
        assert body["dsse"] is None
        assert body["signed"] is False
        assert body["receipt_minted"] is False
        assert body["export_read_only"] is True
        return body


def _assert_no_sql_write(sql):
    assert all(not line.lstrip().upper().startswith(
        ("BEGIN", "INSERT", "UPDATE", "DELETE", "CREATE", "PRAGMA", "COMMIT")) for line in sql)


def _files(host):
    directory = host[2].parent
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("key_capability", [False, True])
def test_served_attestation_read_does_not_sign_or_write(monkeypatch, host, method, key_capability):
    # The capability flag must not be inspected or exercised by this read.
    monkeypatch.setattr(szl_dsse, "signing_available", lambda: key_capability)
    store = host[0].state.be_khipu
    before = store._all()
    database_bytes = _files(host)
    calls, sql = _guards(monkeypatch, host)
    path = BASE + "/assurance/attest"
    for _ in range(2):
        response = getattr(host[1], method)(path)
        assert response.status_code == 200
        body = _assert_unsigned(response, method)
        if body is not None:
            assert body["statement"]["khipu_chain"]["chain_ok"] is True
            assert "authorization" not in body and "production_ready" not in body
    _assert_route(host, path, method)
    assert store._all() == before
    assert _files(host) == database_bytes
    assert calls == {name: 0 for name in calls}
    _assert_no_sql_write(sql)


@pytest.mark.parametrize("method", ["get", "head"])
def test_broken_chain_is_observed_without_signature_or_repair(monkeypatch, host, method):
    store = host[0].state.be_khipu
    store.emit("LOCAL_TEST", {"synthetic": True})
    store._db.execute("UPDATE khipu SET digest=? WHERE seq=0", ("0" * 64,))
    store._db.commit()
    before = _files(host)
    calls, sql = _guards(monkeypatch, host)
    response = getattr(host[1], method)(BASE + "/assurance/attest")
    assert response.status_code == 200
    body = _assert_unsigned(response, method)
    if body is not None:
        assert body["statement"]["khipu_chain"]["chain_ok"] is False
        assert body["statement"]["khipu_chain"]["first_break_seq"] == 0
    assert _files(host) == before
    assert calls == {name: 0 for name in calls}
    _assert_no_sql_write(sql)


@pytest.mark.parametrize("method", ["get", "head"])
def test_missing_closed_store_is_not_recreated_on_read(monkeypatch, host, method):
    store = host[0].state.be_khipu
    store._db.close()
    preserved = host[2].with_name("preserved.sqlite3")
    host[2].rename(preserved)
    before = _files(host)
    calls, _ = _guards(monkeypatch, host, observe_sql=False)
    response = getattr(host[1], method)(BASE + "/assurance/attest")
    assert response.status_code == 500
    assert not host[2].exists()
    assert _files(host) == before
    assert calls == {name: 0 for name in calls}


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("state", ["absent", "uninitialized", "empty", "existing", "historical", "malformed", "missing-field", "empty-object", "nonfinite", "raises"])
def test_energy_reads_only_existing_snapshot(monkeypatch, host, method, state):
    counter = {"status": 0, "get_ledger": 0, "record": 0, "operator": 0}
    snapshot = {"decisions_total": 1, "recent_decisions": [{"chosen_node": "LOCAL_TEST", "kind": "SAMPLE"}],
                "chain": {"ok": True, "head": "local", "length": 1}}
    if state == "empty":
        snapshot.update(decisions_total=0, recent_decisions=[], chain={"ok": True, "head": "genesis", "length": 0})
    elif state == "historical":
        snapshot["recent_decisions"][0].update(signed=True, dsse={"declaration": "LOCAL_TEST_UNVERIFIED"})
    elif state == "malformed":
        snapshot["recent_decisions"] = [None]
    elif state == "missing-field":
        snapshot.pop("recent_decisions")
    elif state == "empty-object":
        snapshot = {}
    elif state == "nonfinite":
        snapshot["decisions_total"] = float("nan")
    original_snapshot = deepcopy(snapshot)

    def status():
        counter["status"] += 1
        if state == "raises":
            raise RuntimeError("private failure detail must not be reflected")
        return deepcopy(snapshot)

    def forbidden(name):
        def fail(*args, **kwargs):
            counter[name] += 1
            raise AssertionError("read attempted " + name)
        return fail

    module = SimpleNamespace(_LEDGER=SimpleNamespace(status=status, record=forbidden("record")),
                             get_ledger=forbidden("get_ledger"))
    if state == "absent":
        monkeypatch.delitem(sys.modules, "szl_cheapest_watt", raising=False)
    else:
        if state == "uninitialized":
            module._LEDGER = None
        monkeypatch.setitem(sys.modules, "szl_cheapest_watt", module)
    monkeypatch.setitem(sys.modules, "szl_energy_operator", SimpleNamespace(
        _OPERATOR=SimpleNamespace(status=forbidden("operator"))))
    before = _files(host)
    calls, sql = _guards(monkeypatch, host)
    path = BASE + "/energy/cheapest-watt"
    for _ in range(2):
        response = getattr(host[1], method)(path)
        assert response.status_code == (503 if state in {"malformed", "missing-field", "empty-object", "nonfinite", "raises"} else 200)
        body = _assert_unsigned(response, method)
        if body is not None:
            expected = "EMPTY" if state == "empty" else "AVAILABLE" if state in {"existing", "historical"} else "UNAVAILABLE"
            assert body["ledger_state"] == expected
            if state in {"existing", "historical"}:
                assert body["latest_decision"]["chosen_node"] == "LOCAL_TEST"
                assert body["latest_decision"] == original_snapshot["recent_decisions"][-1]
                assert "digest" not in body["latest_decision"]
            else:
                assert body["latest_decision"] is None
            assert "private failure detail" not in response.text
            assert body["retained_signature_verified"] is False
            assert body["retained_attestation_state"] == "UNKNOWN"
    _assert_route(host, path, method)
    assert snapshot == original_snapshot
    assert counter == {"status": 0 if state in {"absent", "uninitialized"} else 2,
                       "get_ledger": 0, "record": 0, "operator": 0}
    assert _files(host) == before
    assert calls == {name: 0 for name in calls}
    _assert_no_sql_write(sql)


@pytest.mark.parametrize("method", ["get", "head"])
def test_existing_wal_connection_reads_preserve_sidecars(monkeypatch, host, method):
    store = host[0].state.be_khipu
    assert store._db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    store.emit("LOCAL_TEST", {"synthetic": True})
    assert store.verify() == (True, 1, -1)
    before = _files(host)
    assert any(name.endswith("-wal") for name in before)
    calls, sql = _guards(monkeypatch, host)
    response = getattr(host[1], method)(BASE + "/assurance/attest")
    assert response.status_code == 200
    _assert_unsigned(response, method)
    assert _files(host) == before
    assert calls == {name: 0 for name in calls}
    _assert_no_sql_write(sql)


def test_explicit_backend_post_preserves_positive_write_control(monkeypatch, host):
    store = host[0].state.be_khipu
    before = hashlib.sha256(host[2].read_bytes()).hexdigest()
    calls, sql = _guards(monkeypatch, host, allow_writer=True)
    response = host[1].post(BASE + "/be/khipu/append", json={"action": "LOCAL_TEST", "payload": {"synthetic": True}})
    assert response.status_code == 200
    assert store.count() == 1
    assert store.verify() == (True, 1, -1)
    assert hashlib.sha256(host[2].read_bytes()).hexdigest() != before
    assert calls == {**{name: 0 for name in calls}, "emit": 1}
    assert any(line.upper().startswith("INSERT") for line in sql)
    assert any(line.upper().startswith("COMMIT") for line in sql)


def test_attestation_chain_diagnostics_remain_coherent_during_explicit_writer(monkeypatch, host):
    store = host[0].state.be_khipu
    first = store.emit("LOCAL_TEST", {"synthetic": True})
    attempted = threading.Event()
    completed = threading.Event()
    original_verify = store.verify
    original_head = store.head

    def writer():
        attempted.set()
        store.emit("LOCAL_TEST_SECOND", {"synthetic": True})
        completed.set()

    thread = threading.Thread(target=writer)

    def verify():
        result = original_verify()
        thread.start()
        assert attempted.wait(1)
        return result

    def head():
        # The writer tried to enter between verify and head. It must remain
        # blocked until this coherent diagnostic observation is captured.
        assert not completed.is_set()
        return original_head()

    monkeypatch.setattr(store, "verify", verify)
    monkeypatch.setattr(store, "head", head)
    response = host[1].get(BASE + "/assurance/attest")
    thread.join(2)
    assert not thread.is_alive()
    assert completed.is_set()
    assert response.status_code == 200
    chain = response.json()["statement"]["khipu_chain"]
    assert chain["depth"] == 1
    assert chain["head"] == first["digest"]
    assert store.count() == 2
