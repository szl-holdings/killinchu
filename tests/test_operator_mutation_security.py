# SPDX-License-Identifier: Apache-2.0
"""Fail-closed operator mutation, idempotency, receipt, and OpenAPI proof."""
from __future__ import annotations

import hashlib

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
            client.post(f"/api/{NS}/crawl/run"),
            client.post(f"/api/{NS}/watchlists", json={"name": "anonymous"}),
            client.put(f"/api/{NS}/watchlists/1", json={"enabled": False}),
            client.delete(f"/api/{NS}/watchlists/1"),
        )
        assert [response.status_code for response in attempts] == [401, 401, 401, 401]
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
    assert [response.status_code for response in attempts] == [400, 400, 400, 400]
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


def test_openapi_keeps_all_routes_and_declares_operator_security(secured_backend):
    app, _, _ = secured_backend
    schema = app.openapi()
    protected = {
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
