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
SOURCE_A11OY_COMMIT = "3831b4475ed16d78efc337496a87847a6320b06c"
EXPECTED_MANIFEST_SHA256 = (
    "d459bbb271014a22e855ddd3053a4537a5a7f9f1cd23eaf9873cfd4a158c7637"
)
EXPECTED_SHA256 = {
    "a11oy_code_engine.py": "73f79731902dedca156ad31e551cb3b852d528e6668fa820a36a0f3a4540dbbc",
    "gdw_auth.py": "c692593e02873f7b71b9a108fa42a9c2ae7f29d455596d9dd0a4236145297e89",
    "szl_agentic_loop.py": "4cfd1b8703ac3f1a9b0fe6a31a99e8d1f5caec608f947fe9a4a3d6107eaee596",
    "szl_immune.py": "6047e4c3ac016650789a07405464a0c3bfedd14dac0cac3cc8e7327857b8893d",
    "szl_ken.py": "6c0f1da763fa94a75f4e5cefb01461d9f7e62be92f6681b0bacf671d75a39f26",
    "szl_operator_auth.py": "7a356e6423ae65d1e399e36bfeb3f941c93dcd8c980b1d11afabc8dc12dba8dc",
    "vsp_otel/__init__.py": "c474f6461efede971bdc7e00684b246eee036e7293c5e9ba37e85fd173dadd58",
    "vsp_otel/middleware.py": "93f1d16fa2d4ec0e9e29417ea7b1f5b33534520d99f2c8c41a27d951f1ac8f63",
}
# The signed successor adds the restraint operator route to the shared gate.
# Keep the earlier source/digests immutable; only this explicit successor changes.
RESTRAINT_A11OY_COMMIT = "530b0960bc8b24645cb65a132ae04254c9ae5be8"
RESTRAINT_EXPECTED_SHA256 = {
    **EXPECTED_SHA256,
    "szl_operator_auth.py": "1ee6a88e37d522c5404ac04ac90eadcbfc6f7e59140a778d03275832e217e2cf",
}
# The RAG successor adds the separate estate receipt route. Its source commit
# is unsigned; byte identity is verified here without claiming a signature.
RAG_A11OY_COMMIT = "74dbd5ce75bdb704168a05abceeb186fcf7f49ca"
RAG_EXPECTED_SHA256 = {
    **RESTRAINT_EXPECTED_SHA256,
    "szl_operator_auth.py": "86ed8b445c05f26c66c8d41dba09fe889970aad0e091090efe795299b9336539",
}
# The run-loop successor records which backend produced a retrieve hop.
# Byte identity only. This does not claim a new retrieval qualification.
RUNLOOP_A11OY_COMMIT = "4e1463cac8df3d4c685f2eafa07a08880d7fad4c"
CURRENT_A11OY_COMMIT = RUNLOOP_A11OY_COMMIT
CURRENT_EXPECTED_SHA256 = {
    **RAG_EXPECTED_SHA256,
    "a11oy_code_engine.py": "ac7393a9394ed4a8a1acdc801260c0e505c9940868668c1c7c43a2aad8c1129d",
    "szl_agentic_loop.py": "20543887d96d594c3a71289744d6e82a0ba339f78ed16924dcd75fa015d1e6d5",
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
    assert len(CURRENT_A11OY_COMMIT) == 40
    # Each new paired contribution replaces the active admission manifest.
    # Keep this earlier runtime proof immutable instead of pinning that slot.
    historical_manifest = ROOT / ".github/shared-source-payloads/runtime-boundary-1994-v2.json"
    assert _digest(historical_manifest) == (
        EXPECTED_MANIFEST_SHA256
    )
    # The historical admission manifest contains these two files; the original
    # independent eight-file runtime proof above retains its wider scope.
    assert json.loads(historical_manifest.read_text(encoding="utf-8")) == {
        "files": {relative: EXPECTED_SHA256[relative]
                  for relative in ("szl_agentic_loop.py", "szl_immune.py")},
        "payload_id": "runtime-boundary-1994-v2",
        "schema": "szl-shared-source-payload/v1",
    }
    assert {
        relative: _digest(ROOT / relative)
        for relative in CURRENT_EXPECTED_SHA256
    } == CURRENT_EXPECTED_SHA256


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
        assert "szl_operator_auth.py" in copied_sources

    image_contract = json.loads(
        (ROOT / "deploy/image-contract.json").read_text(encoding="utf-8")
    )
    assert "gdw_auth.py" in image_contract["local_copy_sources"]
    assert "szl_operator_auth.py" in image_contract["local_copy_sources"]


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
