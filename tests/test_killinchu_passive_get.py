"""Served canonical GETs must not replay, mint, or acquire a writer lock."""
from contextlib import closing, contextmanager
import hashlib
import importlib
import json
import sqlite3
import threading

from fastapi.testclient import TestClient
import pytest

from killinchu_ledger import DURABLE_EXTERNAL, EPHEMERAL, LedgerRuntime, LedgerUnavailable
import killinchu_ledger_sqlite as storage


PATHS = [
    "/readyz", "/api/killinchu/v1/readyz", "/honest", "/api/killinchu/v1/honest",
    "/api/killinchu/healthz", "/api/killinchu/readyz",
    "/api/killinchu/v1/receipt/ledger?limit=0",
    "/api/killinchu/v1/receipt/export",
    "/api/killinchu/v1/receipt/ledger/readiness",
]
HEAD_PATHS = PATHS[4:]


def _digest(receipt, parents):
    digest = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode())
    for parent in parents:
        digest.update(parent.encode())
    return digest.hexdigest()


def _node(index=0, parent=None):
    receipt = {"kind": "LOCAL_TEST", "schema": "test/v1", "index": index}
    parents = [] if parent is None else [parent]
    return {"index": index, "receipt": receipt, "parents": parents,
            "digest": _digest(receipt, parents), "dsse": {"signatures": []}}


@pytest.fixture
def host(monkeypatch, request):
    # The CI environment isolates persistent paths before importing serve.
    # Loading the actual host preserves early route order and middleware.
    module = importlib.import_module("serve")
    address = "passive-" + hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16]
    client = TestClient(module.app, client=(address, 50000))
    return module, client


def _bind(host, monkeypatch, runtime):
    module, _ = host
    monkeypatch.setattr(module, "_LEDGER_RUNTIME", runtime)
    monkeypatch.setattr(module, "_KHIPU_DAG", runtime._dag)


def _runtime(tmp_path, mode, *, started=True):
    adapter = None
    path = None
    if mode == DURABLE_EXTERNAL:
        path = tmp_path / "canonical.sqlite3"
        adapter = storage.SQLiteLedgerAdapter(path, storage.provision(path), timeout_s=0.02)
    runtime = LedgerRuntime([], threading.RLock(), _digest, mode=mode, adapter=adapter,
                            recovery_interval_s=0)
    if started:
        assert runtime.startup()["ready"] is True
        runtime.append(_node())
    return runtime, adapter, path


def _observe(monkeypatch, host, runtime, adapter, path):
    observed = {"startup": 0, "replay": 0, "append": 0, "sign": 0,
                "transactions": [], "connections": [], "sql": []}
    for name in ("startup", "append"):
        original = getattr(runtime, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            observed[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(runtime, name, counted)
    module, _ = host

    def forbidden_sign(*args, **kwargs):
        observed["sign"] += 1
        raise AssertionError("a GET must not sign")

    monkeypatch.setattr(module, "_receipt_signatures", forbidden_sign)
    monkeypatch.setattr(storage, "provision", lambda *a, **k: pytest.fail("GET provisioned"))
    if adapter is not None:
        replay = adapter.replay

        def counted_replay():
            observed["replay"] += 1
            return replay()

        monkeypatch.setattr(adapter, "replay", counted_replay)
        transaction = adapter._transaction

        @contextmanager
        def traced_transaction(*, write=False, read_only=False):
            observed["transactions"].append((write, read_only))
            with transaction(write=write, read_only=read_only) as connection:
                yield connection

        monkeypatch.setattr(adapter, "_transaction", traced_transaction)
        connect = sqlite3.connect

        def traced_connect(database, *args, **kwargs):
            connection = connect(database, *args, **kwargs)
            if str(database).startswith(path.as_uri()):
                observed["connections"].append(str(database))
                connection.set_trace_callback(observed["sql"].append)
            return connection

        monkeypatch.setattr(sqlite3, "connect", traced_connect)
    return observed


def _ledger(body):
    return body if body.get("schema") == "szl.killinchu.ledger-readiness/v1" else body["ledger"]


def _assert_passive(observed):
    assert all(observed[name] == 0 for name in ("startup", "replay", "append", "sign"))
    assert all(flags == (False, True) for flags in observed["transactions"])
    assert all(uri.endswith("?mode=ro") for uri in observed["connections"])
    statements = [statement.strip().upper() for statement in observed["sql"]]
    assert "BEGIN IMMEDIATE" not in statements
    assert not any(statement.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "COMMIT"))
                   for statement in statements)


@pytest.mark.parametrize("mode", [EPHEMERAL, DURABLE_EXTERNAL])
@pytest.mark.parametrize("path", PATHS)
def test_actual_served_get_is_passive(tmp_path, monkeypatch, host, mode, path):
    runtime, adapter, database = _runtime(tmp_path, mode)
    _bind(host, monkeypatch, runtime)
    before_nodes = runtime.snapshot()
    before_attempts = runtime.readiness(recover=False)["recovery"]["attempts"]
    before_bytes = database.read_bytes() if database else None
    backend = host[0].app.state.be_khipu
    backend_depth = backend.verify()[1]
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].get(path)
    assert response.status_code == 200, response.text
    ledger = _ledger(response.json())
    assert ledger["ready"] is True
    assert ledger["production_ready"] is False
    assert ledger["readiness_probe"] == "READ_ONLY"
    assert ledger["durability_state"] == mode
    assert ledger["integrity"]["nodes"] == 1
    assert ledger["recovery"]["attempts"] == before_attempts
    assert runtime.snapshot() == before_nodes
    assert backend.verify()[1] == backend_depth
    if database:
        assert database.read_bytes() == before_bytes
        assert observed["transactions"] == [(False, True)]
        assert "BEGIN" in observed["sql"]
    _assert_passive(observed)
    if path in PATHS[:4]:
        assert response.json()["ledger_role"] == "CANONICAL_RECEIPT_LEDGER"
        assert response.json()["receipt_minted"] is False
    if "receipt/ledger?" in path:
        assert response.json()["count"] == len(response.json()["nodes"]) == 1


@pytest.mark.parametrize("mode", [EPHEMERAL, DURABLE_EXTERNAL])
@pytest.mark.parametrize("path", HEAD_PATHS)
def test_actual_served_head_is_passive(tmp_path, monkeypatch, host, mode, path):
    runtime, adapter, database = _runtime(tmp_path, mode)
    _bind(host, monkeypatch, runtime)
    before = database.read_bytes() if database else None
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].head(path)
    assert response.status_code == 200
    assert response.content == b""
    if database:
        assert database.read_bytes() == before
    _assert_passive(observed)


@pytest.mark.parametrize("mode", [EPHEMERAL, DURABLE_EXTERNAL])
@pytest.mark.parametrize("path", PATHS)
def test_get_never_starts_unstarted_runtime(tmp_path, monkeypatch, host, mode, path):
    runtime, adapter, database = _runtime(tmp_path, mode, started=False)
    _bind(host, monkeypatch, runtime)
    before = database.read_bytes() if database else None
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].get(path)
    assert response.status_code == (200 if path.endswith("healthz") else 503)
    ledger = _ledger(response.json())
    assert ledger["ready"] is ledger["production_ready"] is False
    assert ledger["startup_state"] == "NOT_STARTED"
    assert ledger["recovery"]["attempts"] == 0
    assert runtime.snapshot() == []
    if database:
        assert database.read_bytes() == before
    _assert_passive(observed)


def test_read_only_flag_suppresses_default_recovery(tmp_path):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL, started=False)
    assert runtime.readiness(read_only=True)["ready"] is False
    assert runtime.readiness(read_only=True)["recovery"]["attempts"] == 0
    assert runtime.snapshot() == []
    # Explicit startup still replays and tests writer capability.
    assert runtime.startup()["ready"] is True
    assert runtime.readiness(recover=False)["recovery"]["attempts"] == 1


@pytest.mark.parametrize("path", PATHS)
def test_adapter_without_passive_capability_never_falls_back(tmp_path, monkeypatch, host, path):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL)
    writer_calls = []

    def legacy_readiness():
        writer_calls.append(True)
        return {"ready": True, "production_ready": False, "persistence_scope": "LOCAL_FILESYSTEM"}

    monkeypatch.setattr(adapter, "readiness", legacy_readiness)
    _bind(host, monkeypatch, runtime)
    before = database.read_bytes()
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].get(path)
    assert response.status_code == (200 if path.endswith("healthz") else 503)
    assert _ledger(response.json())["ready"] is False
    assert writer_calls == []
    assert database.read_bytes() == before
    _assert_passive(observed)
    # Compatibility remains explicit: startup/writer readiness can still use
    # the legacy adapter. GETs never silently invoke that writer path.
    assert runtime.startup()["ready"] is True
    assert writer_calls


@pytest.mark.parametrize("failure", ["missing", "identity", "schema", "node"])
def test_passive_sqlite_failure_does_not_repair_or_replay(tmp_path, monkeypatch, host, failure):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL)
    _bind(host, monkeypatch, runtime)
    if failure == "missing":
        database.rename(tmp_path / "preserved.sqlite3")
    elif failure == "identity":
        adapter._store_id = "00000000-0000-0000-0000-000000000000"
    else:
        with closing(sqlite3.connect(database)) as connection:
            with connection:
                connection.execute("CREATE TABLE unexpected (value TEXT)" if failure == "schema"
                                   else "UPDATE ledger_nodes SET digest = 'tampered'")
    before = database.read_bytes() if database.exists() else None
    nodes = runtime.snapshot()
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].get("/api/killinchu/v1/receipt/ledger?limit=0")
    assert response.status_code == 503
    assert response.json()["nodes"] == []
    assert response.json()["ledger"]["production_ready"] is False
    assert runtime.snapshot() == nodes
    assert (database.read_bytes() if database.exists() else None) == before
    _assert_passive(observed)


def test_read_probe_does_not_claim_writer_lock_and_write_still_fails_closed(
        tmp_path, monkeypatch, host):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL)
    _bind(host, monkeypatch, runtime)
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    lock = sqlite3.connect(database)
    try:
        lock.execute("BEGIN IMMEDIATE")
        observed["sql"].clear()
        response = host[1].get("/readyz")
        assert response.status_code == 200
        assert response.json()["ledger"]["readiness_probe"] == "READ_ONLY"
        _assert_passive(observed)
        before = runtime.snapshot()
        with pytest.raises(LedgerUnavailable):
            runtime.append(_node(1, before[0]["digest"]))
        assert runtime.snapshot() == before
        assert (True, False) in observed["transactions"]
        assert "BEGIN IMMEDIATE" in observed["sql"]
    finally:
        lock.rollback()
        lock.close()
    assert runtime.startup()["ready"] is True
    assert observed["startup"] == 1
    assert observed["replay"] == 3  # adapter startup, runtime replay, integrity hook


def test_explicit_writer_still_commits_and_recovers_lost_acknowledgment(
        tmp_path, monkeypatch, host):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL)
    _bind(host, monkeypatch, runtime)
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    committed_append = adapter.append

    def lost_ack(node):
        committed_append(node)
        raise RuntimeError("local synthetic lost acknowledgment")

    monkeypatch.setattr(adapter, "append", lost_ack)
    first = runtime.snapshot()[0]
    second = _node(1, first["digest"])
    with pytest.raises(LedgerUnavailable):
        runtime.append(second)
    assert runtime.snapshot() == [first]
    attempts = runtime.readiness(recover=False, read_only=True)["recovery"]["attempts"]
    response = host[1].get("/readyz")
    assert response.status_code == 503
    assert response.json()["ledger"]["recovery"]["attempts"] == attempts
    assert observed["startup"] == observed["replay"] == 0
    assert runtime.snapshot() == [first]
    # The original explicit recovery path sees the genuine committed node.
    assert runtime.readiness()["ready"] is True
    assert runtime.snapshot() == [first, second]
    assert observed["startup"] == 1
    assert observed["replay"] == 3  # adapter startup, runtime replay, integrity hook
    assert "BEGIN IMMEDIATE" in observed["sql"]
    assert any(sql.startswith("INSERT INTO ledger_nodes") for sql in observed["sql"])


def test_backend_chain_failure_remains_independent(tmp_path, monkeypatch, host):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL)
    _bind(host, monkeypatch, runtime)
    monkeypatch.setattr(host[0].app.state.be_khipu, "verify", lambda: (False, 2, 1))
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].get("/readyz")
    assert response.status_code == 503
    assert response.json()["ledger"]["ready"] is True
    assert response.json()["backend_store_diagnostics"]["chain_ok"] is False
    _assert_passive(observed)


def test_first_honest_route_remains_canonical_and_shadow_route_cannot_win(host):
    routes = [route for route in host[0].app.router.routes
              if getattr(route, "path", None) == "/api/killinchu/v1/honest"]
    assert len(routes) >= 2
    assert type(routes[0]).__name__ == "CanonicalLedgerRoute"
    assert routes[1].endpoint is host[0].honest


def test_get_unavailable_exception_handler_cannot_recover(tmp_path, monkeypatch, host):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL, started=False)
    _bind(host, monkeypatch, runtime)
    original = runtime.readiness
    calls = []

    def interrupted_readiness(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise LedgerUnavailable("local test unavailable")
        return original(**kwargs)

    monkeypatch.setattr(runtime, "readiness", interrupted_readiness)
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].get("/api/killinchu/v1/receipt/ledger?limit=0")
    assert response.status_code == 503
    assert calls == [{"recover": False, "read_only": True}] * 2
    assert response.json()["ledger"]["recovery"]["attempts"] == 0
    _assert_passive(observed)


def _after_action_record(monkeypatch, digest):
    import killinchu_parity as parity
    record = {"record_id": "LOCAL-RECORD", "track_id": "LOCAL-TRACK", "verdict": "HOLD",
              "receipt": {"index": 0, "digest": digest, "signed": False},
              "witness_quorum": {"state": "UNAVAILABLE", "quorum_mode": "SIMULATED_IN_PROCESS"}}
    monkeypatch.setattr(parity, "audit_log_snapshot", lambda: [record])
    monkeypatch.setattr(parity, "roe_decisions_snapshot", lambda: [])
    monkeypatch.setattr(parity, "_TRACK_HISTORY", {})


AFTER_ACTION_PATHS = [
    "/api/killinchu/v1/engagements/after-action?track_id=LOCAL-TRACK",
    "/api/killinchu/v1/engagements/LOCAL-RECORD/after-action",
]


@pytest.mark.parametrize("mode", [EPHEMERAL, DURABLE_EXTERNAL])
@pytest.mark.parametrize("path", AFTER_ACTION_PATHS)
@pytest.mark.parametrize("method", ["get", "head"])
def test_actual_after_action_exports_existing_evidence_without_mint(
        tmp_path, monkeypatch, host, mode, path, method):
    runtime, adapter, database = _runtime(tmp_path, mode)
    _bind(host, monkeypatch, runtime)
    nodes = runtime.snapshot()
    _after_action_record(monkeypatch, nodes[0]["digest"])
    before = database.read_bytes() if database else None
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = getattr(host[1], method)(path)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    if method == "head":
        assert response.content == b""
    else:
        body = response.json()
        assert body["schema"] == "szl.killinchu.after-action/v1"
        assert body["export_receipt"] == {
            "index": None, "digest": None, "signed": False, "state": "UNSIGNED_READ_ONLY"}
        assert body["receipt_minted"] is False
        assert body["export_read_only"] is True
        assert body["truth_states"]["effectors"] == "SIMULATED"
        assert body["sections"]["ledger_chain"]["nodes"] == nodes
        assert body["sections"]["closure"]["records"][0]["receipt"]["digest"] == nodes[0]["digest"]
        assert body["receipt_resolution"]["resolved_in_chain"] == 1
        assert body["ledger"]["readiness_probe"] == "READ_ONLY"
        assert body["ledger"]["production_ready"] is False
    assert runtime.snapshot() == nodes
    if database:
        assert database.read_bytes() == before
        assert observed["transactions"] == [(False, True)]
    _assert_passive(observed)
    # The export must be the first matching route ahead of the SPA catch-all.
    request_scope = {"type": "http", "path": path.split("?")[0],
                     "method": method.upper(), "root_path": ""}
    from starlette.routing import Match
    matched = next(route for route in host[0].app.router.routes
                   if route.matches(request_scope)[0] is Match.FULL)
    assert matched.endpoint.__module__ == "killinchu_after_action"


@pytest.mark.parametrize("mode", [EPHEMERAL, DURABLE_EXTERNAL])
@pytest.mark.parametrize("path", AFTER_ACTION_PATHS)
@pytest.mark.parametrize("method", ["get", "head"])
def test_after_action_unready_is_fail_closed_without_recovery(
        tmp_path, monkeypatch, host, mode, path, method):
    runtime, adapter, database = _runtime(tmp_path, mode, started=False)
    _bind(host, monkeypatch, runtime)
    _after_action_record(monkeypatch, "0" * 64)
    before = database.read_bytes() if database else None
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = getattr(host[1], method)(path)
    assert response.status_code == 503
    if method == "get":
        body = response.json()
        assert body["ok"] is False
        assert body["receipt_minted"] is False
        assert body["sections"]["ledger_chain"]["state"] == "NOT_VERIFIABLE_IN_THIS_RUNTIME"
        assert body["sections"]["closure"]["state"] == "NOT_VERIFIABLE_IN_THIS_RUNTIME"
        assert body["ledger"]["recovery"]["attempts"] == 0
    assert runtime.snapshot() == []
    if database:
        assert database.read_bytes() == before
    _assert_passive(observed)


@pytest.mark.parametrize("path", [
    "/api/killinchu/v1/engagements/after-action?track_id=ABSENT",
    "/api/killinchu/v1/engagements/ABSENT/after-action",
])
def test_empty_after_action_does_not_mint(tmp_path, monkeypatch, host, path):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL)
    _bind(host, monkeypatch, runtime)
    _after_action_record(monkeypatch, runtime.snapshot()[0]["digest"])
    before = database.read_bytes()
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    response = host[1].get(path)
    assert response.status_code == 404
    assert database.read_bytes() == before
    _assert_passive(observed)


def test_explicit_receipt_post_still_recovers_appends_and_probes_writer(
        tmp_path, monkeypatch, host):
    runtime, adapter, database = _runtime(tmp_path, DURABLE_EXTERNAL, started=False)
    _bind(host, monkeypatch, runtime)
    observed = _observe(monkeypatch, host, runtime, adapter, database)
    # Synthetic local write: no provider call or signing credential is used.
    monkeypatch.setattr(host[0], "_receipt_signatures", lambda receipt: ([], False))
    response = host[1].post("/api/killinchu/v1/receipt/emit",
                           json={"kind": "LOCAL_TEST", "payload": {"synthetic": True}})
    assert response.status_code == 200, response.text
    assert response.json()["node_index"] == 0
    assert response.json()["ledger"]["readiness_probe"] == "WRITE_CAPABILITY"
    assert response.json()["ledger"]["production_ready"] is False
    assert len(runtime.snapshot()) == 1
    assert observed["startup"] == observed["append"] == 1
    assert "BEGIN IMMEDIATE" in observed["sql"]
    assert any(sql.startswith("INSERT INTO ledger_nodes") for sql in observed["sql"])
