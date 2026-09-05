# SPDX-License-Identifier: Apache-2.0
"""Content-bound peer proof for the a11oy runtime mutation-boundary repair."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import szl_agentic_loop as runtime_loop
import szl_immune as immune


ROOT = Path(__file__).resolve().parents[1]
SOURCE_A11OY_COMMIT = "5c554a243364b6629a4c41a5d07d355241ac16d6"
EXPECTED_MANIFEST_SHA256 = (
    "3197110a3061ee92e5cf051a632a63aaf12255a03c751360488a4c084950ad28"
)
EXPECTED_SHA256 = {
    "gdw_auth.py": "c692593e02873f7b71b9a108fa42a9c2ae7f29d455596d9dd0a4236145297e89",
    "szl_agentic_loop.py": "84b29cbe7db8b8931afcf79c58d8b14f7457dee48c66cb906726dbeb65b74849",
    "szl_immune.py": "acd3cb1d72cd87e812c80ff25349268b9e46256a1ce4ddd017c28cf9c3805378",
}
TOKEN = "test-killinchu-runtime-operator"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _app() -> FastAPI:
    app = FastAPI()
    runtime_loop.register(
        app,
        ns="killinchu",
        sign_fn=lambda payload: {
            "payloadType": "application/json",
            "payload": payload,
            "signatures": [],
            "signed": False,
            "honesty": "test structural envelope",
        },
    )
    return app


@pytest.fixture(autouse=True)
def _operator_registry(monkeypatch):
    monkeypatch.setenv("KILLINCHU_OPERATOR_CREDENTIALS_JSON", json.dumps({
        "version": 1,
        "credentials": [{
            "owner_id": "operator:test",
            "namespace": "killinchu",
            "key_id": "runtime-peer-test-key",
            "token": TOKEN,
            "scopes": ["agent:cycle", "immune:lorenz"],
            "revoked": False,
        }],
    }))
    monkeypatch.setenv("KILLINCHU_OPERATOR_NAMESPACE", "killinchu")
    monkeypatch.setenv("KILLINCHU_OPERATOR_MIN_INTERVAL_SEC", "0")
    monkeypatch.delenv("KILLINCHU_OPERATOR_PRINCIPALS_JSON", raising=False)
    with runtime_loop._OPERATOR_ACTION_LOCK:
        runtime_loop._OPERATOR_ACTION_PENDING.clear()
        runtime_loop._OPERATOR_ACTION_LAST.clear()
    yield
    with runtime_loop._OPERATOR_ACTION_LOCK:
        runtime_loop._OPERATOR_ACTION_PENDING.clear()
        runtime_loop._OPERATOR_ACTION_LAST.clear()


def test_shared_runtime_files_match_the_a11oy_content_address() -> None:
    assert len(SOURCE_A11OY_COMMIT) == 40
    assert _digest(ROOT / ".github/shared-source-payload-manifest.json") == (
        EXPECTED_MANIFEST_SHA256
    )
    assert {
        relative: _digest(ROOT / relative)
        for relative in EXPECTED_SHA256
    } == EXPECTED_SHA256


def test_operator_auth_dependency_is_in_the_runtime_image() -> None:
    for relative in ("Dockerfile", "deploy/space/Dockerfile"):
        dockerfile = (ROOT / relative).read_text(encoding="utf-8")
        copy_lines = [
            line for line in dockerfile.splitlines() if line.startswith("COPY ")
        ]
        copied_sources = {
            token
            for line in copy_lines
            for token in line.split()[1:-1]
        }
        assert "szl_agentic_loop.py" in copied_sources
        assert "gdw_auth.py" in copied_sources

    image_contract = json.loads(
        (ROOT / "deploy/image-contract.json").read_text(encoding="utf-8")
    )
    assert "gdw_auth.py" in image_contract["local_copy_sources"]


def test_gitleaks_exception_is_bound_to_the_public_auth_digest_row() -> None:
    config = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    assert (
        r'''^\s*"gdw_auth\.py"\s*:\s*"[0-9a-f]{64}",?\s*$'''
        in config
    )
    paths_block = config.split("paths = [", 1)[1]
    assert "shared-source-payload-manifest" not in paths_block


def test_killinchu_mcp_notification_has_empty_202_response() -> None:
    with TestClient(_app()) as client:
        notification = client.post("/mcp/", json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        request = client.post("/mcp/", json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "ping",
        })
    assert notification.status_code == 202
    assert notification.content == b""
    assert request.json() == {"jsonrpc": "2.0", "id": 3, "result": {}}


def test_killinchu_cycle_requires_strict_opt_in_and_scoped_operator(monkeypatch) -> None:
    monkeypatch.setenv("A11OY_OUROBOROS", "1")
    with TestClient(_app()) as client:
        string_false = client.post(
            "/api/killinchu/v1/agent/cycle", json={"loop": "false"}
        )
        unauthenticated = client.post(
            "/api/killinchu/v1/agent/cycle", json={"loop": True}
        )
        authorized = client.post(
            "/api/killinchu/v1/agent/cycle",
            json={"loop": True, "budget": 1},
            headers=AUTH,
        )
    assert string_false.status_code == 200
    assert string_false.json()["cycle"] is False
    assert unauthenticated.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["cycle"] is True
    assert authorized.json()["operator"]["namespace"] == "killinchu"


def test_lorenz_receipt_substitution_and_action_cache_fail_closed() -> None:
    requests: list[str] = []

    def post(_url: str, body: dict):
        requests.append(body["requestId"])
        return 201, {
            "requestId": body["requestId"],
            "governed": {
                "pass": True,
                "receipt": {"payloadType": "application/vnd.in-toto+json"},
            },
        }, None

    def substituted(_receipt: dict):
        return {
            "verified": True,
            "keyid_expected": "test-key",
            "payload_decoded": {
                "requestId": "lorenz-op-substituted",
                "program": "lorenz",
                "mode": "OP",
                "steps": 320,
                "agent": {"nexus": {
                    "requestId": "lorenz-op-substituted",
                    "program": "lorenz",
                    "mode": "OP",
                    "steps": 320,
                    "inputHash": "a" * 64,
                    "outputHash": "b" * 64,
                    "invariantsHold": True,
                }},
            },
        }

    first = immune._nexus_lorenz(now=10.0, post=post, verify=substituted)
    second = immune._nexus_lorenz(now=11.0, post=post, verify=substituted)
    assert len(requests) == 2
    assert requests[0] != requests[1]
    assert first["sealed"] is second["sealed"] is False
    assert first["inputHash"] is second["outputHash"] is None
    assert first["receipt_verification"]["request_binding"] is False
    assert first["cached"] is second["cached"] is False


def test_lorenz_safe_methods_never_invoke_the_action(monkeypatch) -> None:
    calls = {"n": 0}

    def forbidden_action() -> dict:
        calls["n"] += 1
        raise AssertionError("GET or HEAD executed Lorenz")

    monkeypatch.setattr(immune, "_nexus_lorenz", forbidden_action)
    app = FastAPI()
    immune.register(app, ns="killinchu")
    with TestClient(app) as client:
        get_response = client.get("/api/killinchu/v1/immune/nexus/lorenz")
        head_response = client.head("/api/killinchu/v1/immune/nexus/lorenz")
    assert get_response.status_code == 200
    assert get_response.json()["state"] == "POST_ONLY"
    assert head_response.status_code == 200
    assert calls["n"] == 0
