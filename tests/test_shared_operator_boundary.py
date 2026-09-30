# SPDX-License-Identifier: Apache-2.0
"""Offline handler contracts for the shared code, receipt, and KEN boundaries.

These exercise real Killinchu-namespaced handlers without installing A11oy's
route-table middleware. They do not assert coverage of all Killinchu routes,
live inference, a production signer, or independent custody of test keys.
"""

from pathlib import Path
import runpy
import socket

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import a11oy_code_engine as code
import szl_agentic_loop as loop
import szl_ken as ken
import szl_operator_auth as auth


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = "test-only-operator"
SECOND = "test-only-second-approver"
HEADERS = {"Authorization": f"Bearer {OPERATOR}"}
TWO_HEADERS = {**HEADERS, "X-A11oy-Second-Approver": SECOND}


@pytest.fixture(autouse=True)
def isolated_authority(monkeypatch):
    monkeypatch.setenv(auth.OPERATOR_KEY_ENV, OPERATOR)
    monkeypatch.setenv(auth.SECOND_APPROVER_KEY_ENV, SECOND)

    def no_network(*_args, **_kwargs):
        raise AssertionError("offline boundary tests must not open a network connection")

    monkeypatch.setattr(socket, "create_connection", no_network)


def _forbidden(calls, category):
    def invoke(*_args, **_kwargs):
        calls.append(category)
        raise AssertionError(f"unauthorized side effect: {category}")
    return invoke


def test_both_runtime_copy_sets_include_the_auth_dependency():
    parser = runpy.run_path(str(ROOT / ".github/shared-file-drift-check.py"))
    for relative in ("Dockerfile", "deploy/space/Dockerfile"):
        instructions = parser["logical_lines"](
            (ROOT / relative).read_text(encoding="utf-8"))
        sources = {
            source for instruction in instructions
            for source in parser["parse_copy_sources"](instruction)
        }
        assert "szl_operator_auth.py" in sources


@pytest.mark.parametrize("endpoint", ["turn", "run", "consensus"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer incorrect"}])
def test_unauthorized_code_handlers_have_no_side_effects(monkeypatch, endpoint, headers):
    calls = []
    monkeypatch.setattr(code, "_hf_chat", _forbidden(calls, "model"))
    monkeypatch.setattr(code, "_sandbox_exec", _forbidden(calls, "sandbox"))
    monkeypatch.setattr(code, "governed_turn", _forbidden(calls, "governed-turn"))
    app = FastAPI()
    code.register(app, "killinchu", sign_fn=_forbidden(calls, "sign"))
    assert app.user_middleware == []
    with TestClient(app) as client:
        response = client.post(
            f"/api/killinchu/v1/code/{endpoint}",
            headers=headers,
            json={"prompt": "print(1)", "mode": "code", "sandbox": True,
                  "two_person_attested": True, "attestation": {"operator": True},
                  "allow_exec": True},
        )
    assert response.status_code == 401
    assert response.json()["status"] == "BLOCKED"
    assert response.headers["www-authenticate"] == "Bearer"
    assert calls == []


@pytest.mark.parametrize("headers,expected", [
    (HEADERS, False),
    ({**HEADERS, "X-A11oy-Second-Approver": OPERATOR}, False),
    (TWO_HEADERS, True),
])
def test_execution_authority_is_derived_from_headers_not_body(monkeypatch, headers, expected):
    observed = []

    def capture_turn(*_args, **kwargs):
        observed.append(kwargs["allow_exec"])
        return {"test_handler_reached": True, "executed": False}

    monkeypatch.setattr(code, "governed_turn", capture_turn)
    app = FastAPI()
    code.register(app, "killinchu", sign_fn=lambda _payload: {})
    with TestClient(app) as client:
        response = client.post(
            "/api/killinchu/v1/code/run", headers=headers,
            json={"prompt": "print(1)", "two_person_attested": True, "allow_exec": True},
        )
    assert response.status_code == 200
    assert observed == [expected]


def test_distinct_credentials_do_not_override_the_real_code_policy_gate(monkeypatch):
    calls = []
    monkeypatch.setattr(code, "_model_configured", lambda: False)
    monkeypatch.setattr(code, "_roster", lambda: ([], "offline test"))
    monkeypatch.setattr(code, "_retrieve", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(code, "_sandbox_exec", _forbidden(calls, "sandbox"))
    monkeypatch.setattr(code, "_local_code", lambda _prompt: {
        "code": "open('/tmp/forbidden', 'w').write('no')",
        "language": "python", "source": "offline-test",
    })
    app = FastAPI()
    code.register(app, "killinchu", sign_fn=lambda _payload: {
        "signed": False, "signatures": [], "honesty": "offline unsigned test",
    })
    with TestClient(app) as client:
        response = client.post(
            "/api/killinchu/v1/code/run", headers=TWO_HEADERS,
            json={"prompt": "write a file", "sandbox": True},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "DENY"
    assert body["sandbox"]["executed"] is False
    assert calls == []


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer incorrect"}])
def test_mcp_cannot_sign_caller_payload_without_operator(headers):
    calls = []
    app = FastAPI()
    loop.register(app, "killinchu", sign_fn=_forbidden(calls, "sign"))
    with TestClient(app) as client:
        response = client.post("/mcp/", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "sign_receipt", "arguments": {
                "payload": {"forged": True}, "two_person_attested": True}},
        })
    assert response.status_code == 401
    assert response.json()["error"]["code"] == -32001
    assert calls == []


def test_mcp_operator_reaches_only_the_supplied_test_signer():
    signed_payloads = []

    def unsigned_test_signer(payload):
        signed_payloads.append(payload)
        return {"signed": False, "signatures": [], "honesty": "offline test"}

    app = FastAPI()
    loop.register(app, "killinchu", sign_fn=unsigned_test_signer)
    with TestClient(app) as client:
        response = client.post("/mcp/", headers=HEADERS, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "sign_receipt", "arguments": {
                "payload": {"message": "test payload"}}},
        })
    assert response.status_code == 200
    assert signed_payloads == [{"message": "test payload"}]
    assert response.json()["result"]["structuredContent"]["envelope"]["signed"] is False


def _ken_app(dispatch):
    app = FastAPI()
    app.include_router(ken.make_ken_router(
        "killinchu", [{"name": "test_mutation", "requires_two_person": True}],
        dispatch_fn=dispatch,
    ))
    assert app.user_middleware == []
    return app


@pytest.mark.parametrize("headers", [
    {}, HEADERS, {**HEADERS, "X-A11oy-Second-Approver": OPERATOR},
])
def test_ken_rejects_body_forged_attestation_before_gate_or_dispatch(monkeypatch, headers):
    calls = []
    monkeypatch.setattr(ken, "a11oy_gate", _forbidden(calls, "governance"))
    app = _ken_app(_forbidden(calls, "dispatch"))
    with TestClient(app) as client:
        response = client.post("/api/killinchu/v1/mcp/call", headers=headers, json={
            "name": "test_mutation", "two_person_attested": True,
            "attestation": {"operator": True, "second_approver": True},
        })
    assert response.status_code == 403
    assert response.json()["error"] == "two_person_required"
    assert calls == []


@pytest.mark.parametrize("decision,expected_status", [("decline", 403), ("allow", 200)])
def test_ken_distinct_headers_still_reach_the_governance_gate(
    monkeypatch, decision, expected_status,
):
    calls = []

    async def gate(plan, _state):
        calls.append(("gate", plan["tool"]))
        return {"decision": decision, "source": "offline-test"}

    async def dispatch(plan, _state):
        calls.append(("dispatch", plan["tool"]))
        return {"success": True, "source": "offline-test", "executed": False}

    monkeypatch.setattr(ken, "a11oy_gate", gate)
    with TestClient(_ken_app(dispatch)) as client:
        response = client.post("/api/killinchu/v1/mcp/call", headers=TWO_HEADERS,
                               json={"name": "test_mutation"})
    assert response.status_code == expected_status
    expected = [("gate", "test_mutation")]
    if decision == "allow":
        expected.append(("dispatch", "test_mutation"))
    assert calls == expected


def test_missing_server_secret_or_resolver_error_never_grants_execution(monkeypatch):
    monkeypatch.delenv(auth.SECOND_APPROVER_KEY_ENV)
    assert auth.principal_from_headers(TWO_HEADERS)["two_person_attested"] is False
    monkeypatch.setenv(auth.SECOND_APPROVER_KEY_ENV, OPERATOR)
    same_headers = {**HEADERS, "X-A11oy-Second-Approver": OPERATOR}
    assert auth.principal_from_headers(same_headers)["two_person_attested"] is False
    calls = []
    monkeypatch.setattr(auth, "principal", _forbidden(calls, "resolver"))
    request = type("TestRequest", (), {"headers": TWO_HEADERS})()
    assert code._exec_permitted(request) is False
    assert ken._two_person_attested(request) is False
