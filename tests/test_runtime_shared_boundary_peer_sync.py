# SPDX-License-Identifier: Apache-2.0
"""Content-bound peer proof for the a11oy runtime mutation-boundary repair."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tomllib

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
RUNLOOP_EXPECTED_SHA256 = {
    **RAG_EXPECTED_SHA256,
    "a11oy_code_engine.py": "ac7393a9394ed4a8a1acdc801260c0e505c9940868668c1c7c43a2aad8c1129d",
    "szl_agentic_loop.py": "20543887d96d594c3a71289744d6e82a0ba339f78ed16924dcd75fa015d1e6d5",
}
# Evaluation now requires the existing operator before parsing or publication.
# Retain earlier evidence; this pins reviewed source bytes, not a deployment.
EVALUATION_A11OY_COMMIT = "7d67e807dd4189576b3d48a6b92700bff99fa443"
CURRENT_A11OY_COMMIT = EVALUATION_A11OY_COMMIT
CURRENT_EXPECTED_SHA256 = {
    **RUNLOOP_EXPECTED_SHA256,
    "szl_operator_auth.py": "38880e4b02658718dd8d69070a4edd2d4abca7793c535ecc95978e5a35a3a8d7",
}
TOKEN = "test-killinchu-runtime-operator"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# The mandatory-rlimit successor (predecessor engine digest ac7393a9...) refuses
# to run code when any sandbox child rlimit cannot be applied and drops the
# unenforced seccomp/container label. It is layered on the current generation
# above. Byte identity only; this pins reviewed source, not a deployment.
RLIMITS_A11OY_COMMIT = "3595c3f0eb8b7c59efe38522a12341e553ea1c0f"
CURRENT_A11OY_COMMIT = RLIMITS_A11OY_COMMIT
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "a11oy_code_engine.py": "e515e66d812ed8f9be4cbd2cb042c9a99919d29f7e746df37b1532912a868493",
}

# The attested-sandbox successor (predecessor engine digest e515e66d...) runs the
# sandbox child as the server's own non-root uid in a fresh user + network
# namespace, refuses a root server, requires the child's attestation before any
# user code runs, and reports a run as executed only on execution_attempted=True.
# Byte identity only; this pins reviewed source, not a deployment.
ATTESTED_A11OY_COMMIT = "603b410c6c1309ba0050af32ddc74fd84ca1b99c"
CURRENT_A11OY_COMMIT = ATTESTED_A11OY_COMMIT
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "a11oy_code_engine.py": "2670d8e3acaadb7f2e4fe8cf87c8c12ae111b4e1b38aba802864a3dbdbe5c574",
}

# This successor binds the reviewed shared payload bytes before a publication
# commit exists. The prior commit observations above remain immutable; the
# payload digest does not claim a signature, deployment, or model execution.
BOUNDED_MODEL_MANIFEST_SHA256 = (
    "d8e50108743e7f02ac7b3c2af17e70c47e38922be3f4e214c5d98d1561c54ea6"
)
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "a11oy_code_engine.py": "a03aa1c294b69c8dfe3ce20d85aaf2347fac93ad7cba3544c1697d381639ac6f",
}

# This paired successor adds operator admission for observation/native writes
# and fail-closed outbound delivery accounting. It is source identity only.
OPERATOR_ADMISSION_MANIFEST_SHA256 = (
    "7dbf4ab396a4add29d22e7870951198accb3833f7feb32e8eebf6b7906ce8f1c"
)
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "szl_operator_auth.py": "5b511c270ebb0268974f144e2dc4d3754ad48803a9434f6976eb8c1681265c0d",
}

# Credential origin admission changes the shared engine only. Prior source
# digests above remain historical evidence; this is not deployment evidence.
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "a11oy_code_engine.py": "60b196bc7118ffb08a9ddf3ca1a006026aec969d3a1a8f10a5b8a0e454acc8b7",
}

# The external Bonsai successor adds exact artifact declarations and bounded
# custom-HTTPS default selection. Source identity does not establish model
# quality, endpoint availability, deployment, or production acceptance.
BONSAI_A11OY_COMMIT = "aef361bc3c831f3f1648ffcb5e5ac4576e785668"
CURRENT_A11OY_COMMIT = BONSAI_A11OY_COMMIT
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "a11oy_code_engine.py": "5994454fb6b699f94aec417ea637dec4459a6d2abcc1654df4a7f4bfba0ee67c",
}


# Replication dispatch adds an outer operator gate; original digest remains above.
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "szl_operator_auth.py": "c06458a8c846cdd2ff75efaf2dba06e3a9b9b996465e1035531c2715c73d13c6",
}

# Receipt binding advances only the engine in this runtime proof. Keep every
# prior source observation above; this exact peer commit is source evidence only.
RECEIPT_BINDING_A11OY_COMMIT = "86592c225f997a43aa8ef2ec5ee78ead3943560d"
CURRENT_A11OY_COMMIT = RECEIPT_BINDING_A11OY_COMMIT
CURRENT_EXPECTED_SHA256 = {
    **CURRENT_EXPECTED_SHA256,
    "a11oy_code_engine.py": "6968839865154818babe7e85c2bf37c944b9d0e90eb6fc600bf0e6c2d25bf73e",
}


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
    bounded = ROOT / ".github/shared-source-payloads/code-engine-bounded-model-20261015-v1.json"
    assert _digest(bounded) == BOUNDED_MODEL_MANIFEST_SHA256
    payload = json.loads(bounded.read_text(encoding="utf-8"))
    assert payload["payload_id"] == "code-engine-bounded-model-20261015-v1"
    assert payload["files"]["a11oy_code_engine.py"] == "a03aa1c294b69c8dfe3ce20d85aaf2347fac93ad7cba3544c1697d381639ac6f"
    archived_admission = ROOT / ".github/shared-source-payloads/execution-observer-operator-auth-20261016-v1.json"
    assert _digest(archived_admission) == OPERATOR_ADMISSION_MANIFEST_SHA256
    admission = json.loads(archived_admission.read_text(encoding="utf-8"))
    assert admission["payload_id"] == "execution-observer-operator-auth-20261016-v1"
    assert set(admission["files"]) == {
        ".github/shared-source-payloads/code-engine-bounded-model-20261015-v1.json",
        "szl_khipu_replicate.py", "szl_operator_auth.py", "szl_unay_routes.py",
    }
    assert admission["files"]["szl_khipu_replicate.py"] == (
        "c3f1a5e76e7c6df0c19b932afca30d99fbdd12e508e95ed9f7dfa9fd798dbbf1"
    )
    for relative, digest in admission["files"].items():
        if relative in ("szl_khipu_replicate.py", "szl_unay_routes.py", "szl_operator_auth.py"):
            continue  # The successor changes this source, never the archived hash.
        assert _digest(ROOT / relative) == digest

    integrity_path = ROOT / ".github/shared-source-payloads/replication-payload-integrity-20261017-v1.json"
    assert _digest(integrity_path) == "1b8a4693d35e342ef47088d9fbebad580d05b8425cf9f3f90d32f0c00466c1cc"
    integrity = json.loads(integrity_path.read_bytes())
    assert integrity["schema"] == "szl-shared-source-payload/v1"
    assert integrity["payload_id"] == "replication-payload-integrity-20261017-v1"
    assert set(integrity["files"]) == {
        ".github/shared-source-payloads/execution-observer-operator-auth-20261016-v1.json",
        "szl_khipu_replicate.py",
    }
    for relative, digest in integrity["files"].items():
        assert _digest(ROOT / relative) == digest

    credential_path = ROOT / ".github/shared-source-payloads/model-credential-origin-20261017-v1.json"
    assert _digest(credential_path) == "e0aefafd777d957b4bebee9a438dfea023f00fb6be5cb2863c255c4540c7b71c"
    credential = json.loads(credential_path.read_bytes())
    assert credential["schema"] == "szl-shared-source-payload/v1"
    assert credential["payload_id"] == "model-credential-origin-20261017-v1"
    assert set(credential["files"]) == {
        ".github/shared-source-payloads/execution-observer-operator-auth-20261016-v1.json",
        "a11oy_code_engine.py", "szl_khipu_replicate.py",
    }
    assert credential["files"]["a11oy_code_engine.py"] == (
        "60b196bc7118ffb08a9ddf3ca1a006026aec969d3a1a8f10a5b8a0e454acc8b7"
    )
    for relative, digest in credential["files"].items():
        if relative == "a11oy_code_engine.py":
            continue  # The immutable prior engine digest is asserted above.
        assert _digest(ROOT / relative) == digest
    prior = {**credential, "files": {key: value for key, value in credential["files"].items()
                                    if key != "a11oy_code_engine.py"},
             "payload_id": "replication-payload-integrity-20261017-v1"}
    assert hashlib.sha256((json.dumps(prior, indent=2) + "\n").encode()).hexdigest() == (
        "1b8a4693d35e342ef47088d9fbebad580d05b8425cf9f3f90d32f0c00466c1cc"
    )

    origin_path = ROOT / ".github/shared-source-payloads/replication-origin-index-20261017-v1.json"
    assert _digest(origin_path) == "3df663c60fc5f332174c83e4cec5e28831ec9b1c670e86bf13058f0fdebc3cce"
    origin = json.loads(origin_path.read_bytes())
    assert origin["schema"] == "szl-shared-source-payload/v1"
    assert origin["payload_id"] == "replication-origin-index-20261017-v1"
    assert set(origin["files"]) == {
        ".github/shared-source-payloads/model-credential-origin-20261017-v1.json",
        ".github/shared-source-payloads/replication-payload-integrity-20261017-v1.json",
        "scripts/sync_from_monorepo.sh", "szl_khipu_lmdb.py", "szl_unay_routes.py",
        "tests/test_unay_write_authorization.py", "tests/test_vendor_sync_contract.py",
    }
    for relative, digest in origin["files"].items():
        if relative == "szl_unay_routes.py":
            continue  # Historical route remains bound to its archived digest.
        assert _digest(ROOT / relative) == digest

    active_path = ROOT / ".github/shared-source-payloads/bonsai-model-catalog-20261017-v1.json"
    assert _digest(active_path) == "6cee005bcd706c7c74cf8439ed87769ad020ae2e44aa1d61beb915eeccc19ccc"
    active = json.loads(active_path.read_bytes())
    assert active["schema"] == "szl-shared-source-payload/v1"
    assert active["payload_id"] == "bonsai-model-catalog-20261017-v1"
    assert set(active["files"]) == set(origin["files"]) | {
        ".github/shared-source-payloads/execution-observer-operator-auth-20261016-v1.json",
        ".github/shared-source-payloads/replication-origin-index-20261017-v1.json",
        "a11oy_code_engine.py", "docs/bonsai-model-binding.md", "szl_khipu_replicate.py",
    }
    assert active["files"]["a11oy_code_engine.py"] == (
        "5994454fb6b699f94aec417ea637dec4459a6d2abcc1654df4a7f4bfba0ee67c"
    )
    for relative, digest in active["files"].items():
        if relative in ("a11oy_code_engine.py", "szl_unay_routes.py"):
            continue  # The successor changes source, never the old archive.
        assert _digest(ROOT / relative) == digest


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
    # A later paired contribution adds one exact-row, exact-path meter digest
    # exception. This prior boundary prohibits a broad GLOBAL path exclusion;
    # the actual-scanner regression tests enforce the narrower rule exception.
    global_paths = tomllib.loads(config)["allowlist"]["paths"]
    assert all("shared-source-payload-manifest" not in path for path in global_paths)


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
