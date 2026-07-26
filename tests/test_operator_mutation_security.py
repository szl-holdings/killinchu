# SPDX-License-Identifier: Apache-2.0
"""Fail-closed operator mutation, idempotency, receipt, and OpenAPI proof."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_backend as kb


NS = "killinchu"
TOKEN = "focused-operator-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _headers(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


@pytest.fixture()
def secured_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    monkeypatch.setenv(
        "A11OY_COMPUTE_TOKEN_SHA256",
        hashlib.sha256(TOKEN.encode("utf-8")).hexdigest(),
    )
    monkeypatch.setenv("KILLINCHU_AUTO_CRAWL", "0")
    kb._STORE = None
    kb._SCHED_STARTED = False
    kb._sched_state["circuit_open"] = False
    kb._sched_state["failure_class"] = None
    kb._sched_state["last_error"] = None
    kb._sched_state["operator_action"] = None
    store = kb._store()
    assert store.backend == "sqlite"
    app = FastAPI(title="killinchu-operator-security-test")
    kb.register(app, ns=NS)
    yield app, store, monkeypatch
    kb._STORE = None
    kb._SCHED_STARTED = False


def test_anonymous_mutations_fail_closed_and_reads_remain_public(secured_backend):
    app, store, _ = secured_backend
    with TestClient(app) as client:
        attempts = (
            client.post(f"/api/{NS}/live"),
            client.post(f"/api/{NS}/crawl/run"),
            client.post(f"/api/{NS}/watchlists", json={"name": "anonymous"}),
            client.put(f"/api/{NS}/watchlists/1", json={"enabled": False}),
            client.delete(f"/api/{NS}/watchlists/1"),
        )
        assert [response.status_code for response in attempts] == [401, 401, 401, 401, 401]
        assert all(response.headers["www-authenticate"] == "Bearer" for response in attempts)
        public = client.get(f"/api/{NS}/watchlists")
        assert public.status_code == 200
        assert public.json()["watchlists"] == []

    assert store.query("SELECT COUNT(*) AS c FROM watchlists")[0]["c"] == 0
    assert store.query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 0


def test_authorized_mutations_require_idempotency_key(secured_backend):
    app, _, _ = secured_backend
    with TestClient(app) as client:
        attempts = (
            client.post(f"/api/{NS}/live", headers=AUTH),
            client.post(f"/api/{NS}/crawl/run", headers=AUTH),
            client.post(
                f"/api/{NS}/watchlists",
                json={"name": "missing-key"},
                headers=AUTH,
            ),
            client.put(
                f"/api/{NS}/watchlists/1",
                json={"enabled": False},
                headers=AUTH,
            ),
            client.delete(f"/api/{NS}/watchlists/1", headers=AUTH),
        )
    assert [response.status_code for response in attempts] == [400, 400, 400, 400, 400]
    assert all("Idempotency-Key" in response.json()["error"] for response in attempts)


def test_watchlist_create_update_delete_replays_are_safe(secured_backend):
    app, store, _ = secured_backend
    create_body = {
        "name": "authorized-watch",
        "triggers": [{"field": "type", "op": "eq", "threshold": "F-16"}],
    }
    with TestClient(app) as client:
        created = client.post(
            f"/api/{NS}/watchlists",
            json=create_body,
            headers=_headers("watch-create-0001"),
        )
        replayed_create = client.post(
            f"/api/{NS}/watchlists",
            json=create_body,
            headers=_headers("watch-create-0001"),
        )
        assert created.status_code == replayed_create.status_code == 201
        watchlist_id = created.json()["watchlist"]["id"]
        assert replayed_create.json()["watchlist"]["id"] == watchlist_id
        assert created.json()["mutation_receipt"] == replayed_create.json()["mutation_receipt"]
        assert created.json()["idempotency_replayed"] is False
        assert replayed_create.json()["idempotency_replayed"] is True

        conflict = client.post(
            f"/api/{NS}/watchlists",
            json={"name": "different"},
            headers=_headers("watch-create-0001"),
        )
        assert conflict.status_code == 409

        update_body = {"description": "bounded", "enabled": False}
        updated = client.put(
            f"/api/{NS}/watchlists/{watchlist_id}",
            json=update_body,
            headers=_headers("watch-update-0001"),
        )
        replayed_update = client.put(
            f"/api/{NS}/watchlists/{watchlist_id}",
            json=update_body,
            headers=_headers("watch-update-0001"),
        )
        assert updated.status_code == replayed_update.status_code == 200
        assert updated.json()["mutation_receipt"] == replayed_update.json()["mutation_receipt"]
        assert replayed_update.json()["idempotency_replayed"] is True

        deleted = client.delete(
            f"/api/{NS}/watchlists/{watchlist_id}",
            headers=_headers("watch-delete-0001"),
        )
        replayed_delete = client.delete(
            f"/api/{NS}/watchlists/{watchlist_id}",
            headers=_headers("watch-delete-0001"),
        )
        assert deleted.status_code == replayed_delete.status_code == 200
        assert deleted.json()["mutation_receipt"] == replayed_delete.json()["mutation_receipt"]
        assert replayed_delete.json()["idempotency_replayed"] is True

    assert store.query("SELECT COUNT(*) AS c FROM watchlists")[0]["c"] == 0
    assert store.query("SELECT COUNT(*) AS c FROM triggers")[0]["c"] == 0
    assert store.query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 3
    serialized = created.text
    assert TOKEN not in serialized
    assert "watch-create-0001" not in serialized
    assert created.json()["mutation_receipt"]["signed"] is False


def test_definitive_watchlist_not_found_does_not_consume_key(secured_backend):
    app, store, _ = secured_backend
    now = "2026-07-26T00:00:00Z"

    with TestClient(app) as client:
        update_headers = _headers("missing-watch-update-0001")
        missing_update = client.put(
            f"/api/{NS}/watchlists/700",
            json={"name": "now-present"},
            headers=update_headers,
        )
        assert missing_update.status_code == 404
        assert store.query(
            "SELECT COUNT(*) AS c FROM operator_mutations"
        )[0]["c"] == 0

        store.execute(
            "INSERT INTO watchlists("
            "id, name, description, enabled, created_at, updated_at"
            ") VALUES(?,?,?,?,?,?)",
            (700, "seed", "", 1, now, now),
        )
        updated = client.put(
            f"/api/{NS}/watchlists/700",
            json={"name": "now-present"},
            headers=update_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["watchlist"]["name"] == "now-present"

        delete_headers = _headers("missing-watch-delete-0001")
        missing_delete = client.delete(
            f"/api/{NS}/watchlists/701",
            headers=delete_headers,
        )
        assert missing_delete.status_code == 404
        store.execute(
            "INSERT INTO watchlists("
            "id, name, description, enabled, created_at, updated_at"
            ") VALUES(?,?,?,?,?,?)",
            (701, "delete-me", "", 1, now, now),
        )
        deleted = client.delete(
            f"/api/{NS}/watchlists/701",
            headers=delete_headers,
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == 701


def test_manual_crawl_replay_does_not_repeat_side_effects(secured_backend):
    app, store, monkeypatch = secured_backend
    payload = {"ac": [{"t": "F16", "flag": "US"}]}
    monkeypatch.setattr(
        kb,
        "_fetch_mil_adsb",
        lambda timeout=12.0: (payload, 200, None),
    )

    with TestClient(app) as client:
        first = client.post(
            f"/api/{NS}/crawl/run",
            headers=_headers("crawl-run-0001"),
        )
        replay = client.post(
            f"/api/{NS}/crawl/run",
            headers=_headers("crawl-run-0001"),
        )

    assert first.status_code == replay.status_code == 200
    assert first.json()["snapshot_id"] == replay.json()["snapshot_id"]
    assert first.json()["mutation_receipt"] == replay.json()["mutation_receipt"]
    assert replay.json()["idempotency_replayed"] is True
    assert store.query("SELECT COUNT(*) AS c FROM snapshots")[0]["c"] == 1


def test_live_refresh_requires_authority_and_replays_without_rescrape(
    secured_backend,
):
    app, store, monkeypatch = secured_backend
    calls = []
    payload = {"ac": [{"t": "F16", "flag": "US"}]}

    def fetch(timeout=12.0):
        calls.append(timeout)
        return payload, 200, None

    monkeypatch.setattr(kb, "_fetch_mil_adsb", fetch)
    with TestClient(app) as client:
        first = client.post(
            f"/api/{NS}/live",
            headers=_headers("live-refresh-0001"),
        )
        replay = client.post(
            f"/api/{NS}/live",
            headers=_headers("live-refresh-0001"),
        )
    assert first.status_code == replay.status_code == 200
    assert first.json()["snapshot_id"] == replay.json()["snapshot_id"]
    assert first.json()["mutation_receipt"] == replay.json()["mutation_receipt"]
    assert replay.json()["idempotency_replayed"] is True
    assert len(calls) == 1
    assert store.query("SELECT COUNT(*) AS c FROM snapshots")[0]["c"] == 1


def test_openapi_keeps_all_routes_and_declares_operator_security(secured_backend):
    app, _, _ = secured_backend
    schema = app.openapi()
    protected = {
        (f"/api/{NS}/live", "post"),
        (f"/api/{NS}/crawl/run", "post"),
        (f"/api/{NS}/watchlists", "post"),
        (f"/api/{NS}/watchlists/{{wid}}", "put"),
        (f"/api/{NS}/watchlists/{{wid}}", "delete"),
    }
    assert schema["components"]["securitySchemes"]["OperatorBearer"]["type"] == "http"
    for path, method in protected:
        assert schema["paths"][path][method]["security"] == [{"OperatorBearer": []}]

    assert "get" in schema["paths"][f"/api/{NS}/watchlists"]
    assert "security" not in schema["paths"][f"/api/{NS}/watchlists"]["get"]
    assert "get" in schema["paths"][f"/api/{NS}/crawl/status"]
    assert schema["paths"][
        f"/api/{NS}/operator-mutations/{{key_digest}}"
    ]["get"]["security"] == [{"OperatorBearer": []}]
    assert schema["paths"][
        f"/api/{NS}/operator-mutations/{{key_digest}}/reconcile"
    ]["post"]["security"] == [{"OperatorBearer": []}]


def _canonical_test_emitter(emissions):
    def emit(kind, payload):
        node = {
            "digest": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "receipt": {"kind": kind, "payload": payload},
            "dsse": {"signed": True, "signatures": [{"keyid": "test-key"}]},
            "signed": True,
        }
        emissions.append(node)
        return node

    return emit


def _configure_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    monkeypatch.setenv(
        "A11OY_COMPUTE_TOKEN_SHA256",
        hashlib.sha256(TOKEN.encode("utf-8")).hexdigest(),
    )
    monkeypatch.setenv("KILLINCHU_AUTO_CRAWL", "0")
    kb._STORE = None
    kb._SCHED_STARTED = False


def test_registration_injects_canonical_khipu_receipt_emitter(tmp_path, monkeypatch):
    _configure_backend(tmp_path, monkeypatch)
    emissions = []
    app = FastAPI(title="killinchu-canonical-emitter-test")
    kb.register(
        app,
        ns=NS,
        emit_receipt=_canonical_test_emitter(emissions),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/{NS}/watchlists",
            json={"name": "canonical-receipt"},
            headers=_headers("canonical-receipt-0001"),
        )
    assert response.status_code == 201
    receipt = response.json()["mutation_receipt"]
    assert receipt["signed"] is True
    assert receipt["dsse"]["signatures"][0]["keyid"] == "test-key"
    assert emissions == [receipt]
    row = kb._store().query(
        "SELECT state, receipt_json FROM operator_mutations"
    )[0]
    assert row["state"] == "completed"
    assert json.loads(row["receipt_json"]) == receipt
    kb._STORE = None


def test_sqlite_same_key_concurrency_is_at_most_once_then_replays(
    secured_backend,
):
    app, store, _ = secured_backend
    barrier = threading.Barrier(2)

    def create():
        with TestClient(app) as client:
            barrier.wait(timeout=5)
            return client.post(
                f"/api/{NS}/watchlists",
                json={"name": "concurrent-watch"},
                headers=_headers("concurrent-watch-0001"),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(), range(2)))

    assert any(response.status_code == 201 for response in responses)
    assert all(response.status_code in {201, 409} for response in responses)
    with TestClient(app) as client:
        replay = client.post(
            f"/api/{NS}/watchlists",
            json={"name": "concurrent-watch"},
            headers=_headers("concurrent-watch-0001"),
        )
    assert replay.status_code == 201
    assert replay.json()["idempotency_replayed"] is True
    assert store.query("SELECT COUNT(*) AS c FROM watchlists")[0]["c"] == 1
    assert store.query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 1


def test_sqlite_crash_after_commit_reconciles_receipt_without_remutation(
    tmp_path,
    monkeypatch,
):
    _configure_backend(tmp_path, monkeypatch)
    store = kb._store()
    body = {"name": "crash-reconcile"}
    operation = "watchlist.create"
    key = "crash-reconcile-0001"
    key_hash = "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()
    actor_id = "sha256:" + hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()[:16]
    request_digest = kb._sha256_json(
        {"operation": operation, "payload": body}
    )
    assert store.claim_operator_mutation(
        key_hash=key_hash,
        operation=operation,
        actor_id=actor_id,
        request_digest=request_digest,
    )[0] == "claimed"
    with store.transaction():
        wid = store.insert_returning_id(
            "INSERT INTO watchlists("
            "name, description, enabled, created_at, updated_at"
            ") VALUES(?,?,?,?,?)",
            ("crash-reconcile", "", 1, kb._now_iso(), kb._now_iso()),
        )
        result = kb._envelope(
            "ok",
            {"watchlist": {"id": wid, "name": "crash-reconcile"}},
            [],
        )
        store.stage_operator_mutation(
            key_hash=key_hash,
            status_code=201,
            response={**result, "idempotency_replayed": False},
            receipt_request=kb._mutation_receipt_request(
                operation=operation,
                actor_id=actor_id,
                key_hash=key_hash,
                request_digest=request_digest,
                result=result,
            ),
        )
    assert store.get_operator_mutation(key_hash=key_hash)["state"] == "receipt_pending"

    emissions = []
    app = FastAPI(title="killinchu-crash-reconcile-test")
    kb.register(
        app,
        ns=NS,
        emit_receipt=_canonical_test_emitter(emissions),
    )
    with TestClient(app) as client:
        recovered = client.post(
            f"/api/{NS}/watchlists",
            json=body,
            headers=_headers(key),
        )
    assert recovered.status_code == 201
    assert recovered.json()["idempotency_replayed"] is True
    assert len(emissions) == 1
    assert store.query("SELECT COUNT(*) AS c FROM watchlists")[0]["c"] == 1
    assert store.get_operator_mutation(key_hash=key_hash)["state"] == "completed"
    kb._STORE = None


def test_sqlite_transaction_rolls_back_mutation_before_review_state(
    secured_backend,
    monkeypatch,
):
    app, store, _ = secured_backend

    def crash_before_stage(**kwargs):
        raise RuntimeError("simulated process loss before receipt staging")

    monkeypatch.setattr(store, "stage_operator_mutation", crash_before_stage)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/api/{NS}/watchlists",
            json={"name": "must-roll-back"},
            headers=_headers("rollback-watch-0001"),
        )
    assert response.status_code == 500
    assert store.query("SELECT COUNT(*) AS c FROM watchlists")[0]["c"] == 0
    row = store.query(
        "SELECT state FROM operator_mutations"
    )[0]
    assert row["state"] == "needs_operator_review"


def test_ambiguous_receipt_requires_inspection_before_explicit_retry(
    tmp_path,
    monkeypatch,
):
    _configure_backend(tmp_path, monkeypatch)
    emissions = []
    attempts = 0
    canonical = _canonical_test_emitter(emissions)

    def fail_once(kind, payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated loss while emitter outcome is unknown")
        return canonical(kind, payload)

    app = FastAPI(title="killinchu-explicit-reconciliation-test")
    kb.register(app, ns=NS, emit_receipt=fail_once)
    key = "ambiguous-receipt-0001"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    with TestClient(app) as client:
        first = client.post(
            f"/api/{NS}/watchlists",
            json={"name": "ambiguous-receipt"},
            headers=_headers(key),
        )
        inspected = client.get(
            f"/api/{NS}/operator-mutations/{digest}",
            headers=AUTH,
        )
        refused = client.post(
            f"/api/{NS}/operator-mutations/{digest}/reconcile",
            json={"resolution": "retry_receipt_emission"},
            headers=AUTH,
        )
        resolved = client.post(
            f"/api/{NS}/operator-mutations/{digest}/reconcile",
            json={
                "resolution": "retry_receipt_emission",
                "receipt_absence_confirmed": True,
            },
            headers=AUTH,
        )

    assert first.status_code == 503
    assert first.json()["mutation_state"] == "receipt_emitting"
    assert inspected.status_code == 200
    assert inspected.json()["mutation"]["state"] == "receipt_emitting"
    assert inspected.json()["mutation"][
        "requires_receipt_absence_confirmation"
    ] is True
    assert refused.status_code == 409
    assert resolved.status_code == 201
    assert resolved.json()["idempotency_replayed"] is True
    assert len(emissions) == 1
    store = kb._store()
    assert store.query("SELECT COUNT(*) AS c FROM watchlists")[0]["c"] == 1
    assert store.query(
        "SELECT state FROM operator_mutations"
    )[0]["state"] == "completed"
    kb._STORE = None


def _exercise_store_same_key_concurrency(stores):
    key_hash = "sha256:" + uuid.uuid4().hex + uuid.uuid4().hex
    operation = "watchlist.create"
    actor_id = "sha256:test-actor"
    request_digest = kb._sha256_json(
        {"operation": operation, "payload": {"name": "db-concurrent"}}
    )
    barrier = threading.Barrier(len(stores))

    def claim(store):
        barrier.wait(timeout=10)
        return store.claim_operator_mutation(
            key_hash=key_hash,
            operation=operation,
            actor_id=actor_id,
            request_digest=request_digest,
        )[0]

    with ThreadPoolExecutor(max_workers=len(stores)) as pool:
        states = list(pool.map(claim, stores))
    assert states.count("claimed") == 1
    assert states.count("in_progress") == len(stores) - 1

    winner = stores[states.index("claimed")]
    now = kb._now_iso()
    with winner.transaction():
        wid = winner.insert_returning_id(
            "INSERT INTO watchlists("
            "name, description, enabled, created_at, updated_at"
            ") VALUES(?,?,?,?,?)",
            ("db-concurrent", "", 1, now, now),
        )
        result = {"watchlist": {"id": wid, "name": "db-concurrent"}}
        request = kb._mutation_receipt_request(
            operation=operation,
            actor_id=actor_id,
            key_hash=key_hash,
            request_digest=request_digest,
            result=result,
        )
        winner.stage_operator_mutation(
            key_hash=key_hash,
            status_code=201,
            response={**result, "idempotency_replayed": False},
            receipt_request=request,
        )
    assert winner.begin_receipt_emission(key_hash=key_hash) is True
    receipt = kb._unsigned_mutation_receipt(request)
    response = {
        **result,
        "mutation_receipt": receipt,
        "idempotency_replayed": False,
    }
    with winner.transaction():
        winner.complete_operator_mutation(
            key_hash=key_hash,
            status_code=201,
            response=response,
            receipt=receipt,
        )

    for store in stores:
        state, row = store.claim_operator_mutation(
            key_hash=key_hash,
            operation=operation,
            actor_id=actor_id,
            request_digest=request_digest,
        )
        assert state == "replay"
        assert json.loads(row["response_json"]) == response
    assert winner.query(
        "SELECT COUNT(*) AS c FROM operator_mutations "
        "WHERE idempotency_key_hash=?",
        (key_hash,),
    )[0]["c"] == 1
    assert winner.query(
        "SELECT COUNT(*) AS c FROM watchlists WHERE id=?",
        (wid,),
    )[0]["c"] == 1
    return key_hash, wid


def _exercise_store_transaction_rollback(store):
    key_hash = "sha256:" + uuid.uuid4().hex + uuid.uuid4().hex
    name = "rollback-" + uuid.uuid4().hex
    assert store.claim_operator_mutation(
        key_hash=key_hash,
        operation="watchlist.create",
        actor_id="sha256:test-actor",
        request_digest=kb._sha256_json({"name": name}),
    )[0] == "claimed"
    with pytest.raises(RuntimeError, match="simulated transaction crash"):
        with store.transaction():
            now = kb._now_iso()
            store.insert_returning_id(
                "INSERT INTO watchlists("
                "name, description, enabled, created_at, updated_at"
                ") VALUES(?,?,?,?,?)",
                (name, "", 1, now, now),
            )
            raise RuntimeError("simulated transaction crash")
    assert store.query(
        "SELECT COUNT(*) AS c FROM watchlists WHERE name=?",
        (name,),
    )[0]["c"] == 0
    assert store.get_operator_mutation(key_hash=key_hash)["state"] == "in_progress"
    store.execute(
        "DELETE FROM operator_mutations WHERE idempotency_key_hash=?",
        (key_hash,),
    )


def test_sqlite_multi_connection_same_key_concurrency_and_replay(
    tmp_path,
    monkeypatch,
):
    _configure_backend(tmp_path, monkeypatch)
    first = kb._Store()
    second = kb._Store()
    assert first.backend == second.backend == "sqlite"
    key_hash, wid = _exercise_store_same_key_concurrency([first, second])
    _exercise_store_transaction_rollback(first)
    first.execute("DELETE FROM watchlists WHERE id=?", (wid,))
    first.execute(
        "DELETE FROM operator_mutations WHERE idempotency_key_hash=?",
        (key_hash,),
    )
    kb._STORE = None


def test_postgres_same_key_concurrency_and_replay(monkeypatch):
    dsn = os.environ.get("KILLINCHU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("set KILLINCHU_TEST_POSTGRES_DSN for real Postgres evidence")
    monkeypatch.setenv("KILLINCHU_DATABASE_URL", dsn)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    first = kb._Store()
    second = kb._Store()
    assert first.backend == second.backend == "postgres"
    key_hash, wid = _exercise_store_same_key_concurrency([first, second])
    _exercise_store_transaction_rollback(first)
    first.execute("DELETE FROM watchlists WHERE id=?", (wid,))
    first.execute(
        "DELETE FROM operator_mutations WHERE idempotency_key_hash=?",
        (key_hash,),
    )
