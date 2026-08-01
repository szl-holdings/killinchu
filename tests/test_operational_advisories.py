# SPDX-License-Identifier: Apache-2.0
"""Authenticated, durable, advisory-only operator control contract."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_backend as kb


NS = "killinchu"
TOKEN = "operational-advisory-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TARGET = {
    "track_id": "ADSB-A1B2C3",
    "mode": "LIVE",
    "payload_sha256": "a" * 64,
    "observed_at": "2026-08-01T16:00:00Z",
    "source": "adsb.lol community ADS-B",
    "sensor_id": "adsb.lol",
    "authentication": "UNAUTHENTICATED_BROADCAST",
    "trust": "CLAIM",
}


def _headers(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


def _body(action: str = "HALT", reason: str = "Hold for human review.") -> dict:
    return {"action": action, "target": dict(TARGET), "reason": reason}


@pytest.fixture()
def advisory_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    token_digest = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()
    monkeypatch.setenv("A11OY_COMPUTE_TOKEN_SHA256", token_digest)
    monkeypatch.setenv("KILLINCHU_AUTO_CRAWL", "0")
    kb._STORE = None
    kb._SCHED_STARTED = False
    receipts: list[tuple[str, dict]] = []

    def emit_receipt(kind: str, material: dict) -> dict:
        receipts.append((kind, material))
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "kind": kind,
            "digest": f"sha256:{digest}",
            "signed": True,
            "material": material,
        }

    app = FastAPI(title="killinchu-operational-advisory-test")
    store = kb._store()

    def resolve_track(target: dict) -> dict:
        assert target["track_id"] == TARGET["track_id"]
        return dict(TARGET)

    kb.register(
        app,
        ns=NS,
        emit_receipt=emit_receipt,
        resolve_advisory_track=resolve_track,
    )
    yield app, store, receipts, tmp_path, token_digest
    kb._STORE = None
    kb._SCHED_STARTED = False


def test_advisory_route_fails_closed_before_any_durable_claim(
    advisory_backend, monkeypatch
):
    app, store, receipts, _, _ = advisory_backend
    with TestClient(app) as client:
        anonymous = client.post(f"/api/{NS}/operator-advisories", json=_body())
        assert anonymous.status_code == 401

        missing_key = client.post(
            f"/api/{NS}/operator-advisories", json=_body(), headers=AUTH
        )
        assert missing_key.status_code == 400

        monkeypatch.delenv("A11OY_COMPUTE_TOKEN_SHA256")
        unconfigured = client.post(
            f"/api/{NS}/operator-advisories",
            json=_body(),
            headers=_headers("advisory-unconfigured-0001"),
        )
        assert unconfigured.status_code == 503

    assert store.query("SELECT COUNT(*) AS c FROM advisory_actions")[0]["c"] == 0
    assert store.query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 0
    assert receipts == []


@pytest.mark.parametrize("action", ["HALT", "OVERRIDE", "ESCALATE"])
def test_advisory_is_authenticated_durable_receipted_and_never_actuates(
    advisory_backend, action
):
    app, store, receipts, _, token_digest = advisory_backend
    key = f"advisory-{action.lower()}-0001"
    body = _body(action, f"{action.title()} pending an independent human decision.")
    with TestClient(app) as client:
        created = client.post(
            f"/api/{NS}/operator-advisories", json=body, headers=_headers(key)
        )
        replayed = client.post(
            f"/api/{NS}/operator-advisories", json=body, headers=_headers(key)
        )

    assert created.status_code == replayed.status_code == 201
    first = created.json()
    second = replayed.json()
    advisory = first["advisory"]
    assert advisory["schema"] == "szl.killinchu.operational-advisory/v1"
    assert advisory["action"] == action
    assert advisory["target"] == TARGET
    assert advisory["actor_id"] == f"sha256:{token_digest[:16]}"
    assert advisory["effect"] == "ADVISORY_ONLY"
    assert advisory["advisory_only"] is True
    assert advisory["execution"] == "NOT_ATTEMPTED"
    assert advisory["dispatch"] == "NOT_ATTEMPTED"
    assert advisory["ota"] == "NOT_ATTEMPTED"
    assert advisory["destructive_action"] == "NOT_ATTEMPTED"
    assert advisory["requires_separate_authorized_procedure"] is True
    assert advisory["actuation_dispatched"] is False
    assert advisory["ota_dispatched"] is False
    assert advisory["external_command_sent"] is False
    assert first["mutation_receipt"]["signed"] is True
    assert second["advisory"] == advisory
    assert second["mutation_receipt"] == first["mutation_receipt"]
    assert second["idempotency_replayed"] is True
    assert store.query("SELECT COUNT(*) AS c FROM advisory_actions")[0]["c"] == 1
    assert store.query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 1
    assert len(receipts) == 1
    assert receipts[0][0] == "operator_mutation"
    assert receipts[0][1]["operation"] == "advisory.create"


def test_advisory_schema_is_strict_and_key_conflicts_fail_closed(advisory_backend):
    app, store, receipts, _, _ = advisory_backend
    with TestClient(app) as client:
        extra = _body()
        extra["dispatch"] = True
        rejected_extra = client.post(
            f"/api/{NS}/operator-advisories",
            json=extra,
            headers=_headers("advisory-extra-0001"),
        )
        bad_target = _body()
        bad_target["target"]["ota"] = "AUTHORIZED"
        rejected_target = client.post(
            f"/api/{NS}/operator-advisories",
            json=bad_target,
            headers=_headers("advisory-target-extra-0001"),
        )
        rejected_action = client.post(
            f"/api/{NS}/operator-advisories",
            json=_body("DEFEAT"),
            headers=_headers("advisory-defeat-0001"),
        )
        accepted = client.post(
            f"/api/{NS}/operator-advisories",
            json=_body(),
            headers=_headers("advisory-conflict-0001"),
        )
        conflict = client.post(
            f"/api/{NS}/operator-advisories",
            json=_body(reason="A materially different human rationale."),
            headers=_headers("advisory-conflict-0001"),
        )

    assert [
        rejected_extra.status_code,
        rejected_target.status_code,
        rejected_action.status_code,
    ] == [400, 400, 400]
    assert accepted.status_code == 201
    assert conflict.status_code == 409
    assert store.query("SELECT COUNT(*) AS c FROM advisory_actions")[0]["c"] == 1
    assert store.query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 1
    assert len(receipts) == 1


def test_advisory_survives_store_restart_and_public_index_redacts_actor(
    advisory_backend, monkeypatch
):
    app, _, receipts, tmp_path, token_digest = advisory_backend
    body = _body("ESCALATE", "Escalate this observation for independent review.")
    headers = _headers("advisory-restart-0001")
    with TestClient(app) as client:
        created = client.post(
            f"/api/{NS}/operator-advisories", json=body, headers=headers
        )
    assert created.status_code == 201

    kb._STORE = None
    kb._SCHED_STARTED = False
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    restarted = FastAPI(title="killinchu-operational-advisory-restart")
    kb.register(
        restarted,
        ns=NS,
        emit_receipt=lambda kind, material: receipts[0][1],
        resolve_advisory_track=lambda target: dict(TARGET),
    )
    with TestClient(restarted) as client:
        public = client.get(f"/api/{NS}/operator-advisories")
        replayed = client.post(
            f"/api/{NS}/operator-advisories", json=body, headers=headers
        )

    assert public.status_code == 200
    assert public.json()["count"] == 1
    indexed = public.json()["advisories"][0]
    assert "actor_id" not in indexed
    assert indexed["actor_id_hash"].startswith("sha256:")
    assert token_digest not in public.text
    assert TOKEN not in public.text
    assert replayed.status_code == 201
    assert replayed.json()["idempotency_replayed"] is True
    assert replayed.json()["advisory"] == created.json()["advisory"]
    assert replayed.json()["mutation_receipt"] == created.json()["mutation_receipt"]


def test_openapi_and_static_surface_bind_only_the_advisory_route(advisory_backend):
    app, _, _, _, _ = advisory_backend
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            f"/api/{NS}/operator-advisories"
        ]["post"]
    assert operation["security"] == [{"OperatorBearer": []}]

    html = open("static/index.html", encoding="utf-8").read()
    assert "/api/killinchu/operator-advisories" in html
    assert "Authorization" in html
    assert "Idempotency-Key" in html
    for forbidden in (
        "/v1/ops/command",
        "/hotl/override",
        "/ota",
        "/control",
        "/rollback",
    ):
        assert forbidden not in html


def test_advisory_requires_current_canonical_track_binding(advisory_backend):
    app, store, receipts, _, _ = advisory_backend
    stale = _body()
    stale["target"]["payload_sha256"] = "b" * 64
    mismatched_mode = _body()
    mismatched_mode["target"]["mode"] = "TRAINING"

    with TestClient(app) as client:
        stale_response = client.post(
            f"/api/{NS}/operator-advisories",
            json=stale,
            headers=_headers("advisory-stale-track-0001"),
        )
        mode_response = client.post(
            f"/api/{NS}/operator-advisories",
            json=mismatched_mode,
            headers=_headers("advisory-mode-mismatch-0001"),
        )

    assert stale_response.status_code == 409
    assert mode_response.status_code == 400
    assert store.query("SELECT COUNT(*) AS c FROM advisory_actions")[0]["c"] == 0
    assert store.query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 0
    assert receipts == []


def test_advisory_fails_closed_without_canonical_track_resolver(
    advisory_backend, monkeypatch, tmp_path
):
    _, _, _, _, _ = advisory_backend
    kb._STORE = None
    kb._SCHED_STARTED = False
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path / "no-resolver"))
    app = FastAPI(title="killinchu-advisory-no-resolver")
    kb.register(app, ns=NS, emit_receipt=lambda kind, material: material)

    with TestClient(app) as client:
        response = client.post(
            f"/api/{NS}/operator-advisories",
            json=_body(),
            headers=_headers("advisory-no-resolver-0001"),
        )

    assert response.status_code == 503
    assert "track resolver" in response.json()["error"]
    assert kb._store().query("SELECT COUNT(*) AS c FROM advisory_actions")[0]["c"] == 0
    assert (
        kb._store().query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 0
    )


def test_advisory_distinguishes_unavailable_feed_from_stale_target(
    advisory_backend, monkeypatch, tmp_path
):
    _, _, _, _, _ = advisory_backend
    kb._STORE = None
    kb._SCHED_STARTED = False
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path / "unavailable-resolver"))
    app = FastAPI(title="killinchu-advisory-unavailable-resolver")
    kb.register(
        app,
        ns=NS,
        emit_receipt=lambda kind, material: material,
        resolve_advisory_track=lambda target: {"resolver_status": "UNAVAILABLE"},
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/{NS}/operator-advisories",
            json=_body(),
            headers=_headers("advisory-feed-unavailable-0001"),
        )

    assert response.status_code == 503
    assert "feed is unavailable" in response.json()["error"]
    assert kb._store().query("SELECT COUNT(*) AS c FROM advisory_actions")[0]["c"] == 0
    assert (
        kb._store().query("SELECT COUNT(*) AS c FROM operator_mutations")[0]["c"] == 0
    )
