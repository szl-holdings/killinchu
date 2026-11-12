# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Shared provenance remains usable without a11oy's managed storage engine."""
import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

import szl_dsse
import szl_operator_auth as auth
import szl_provenance as provenance


OPERATOR = "synthetic-standalone-provenance-operator"


@pytest.fixture
def standalone(monkeypatch):
    monkeypatch.delenv("A11OY_STATE_STORE", raising=False)
    monkeypatch.delenv("A11OY_WIRE_D_TARGETS", raising=False)
    monkeypatch.setattr(provenance, "_state_store", None)
    monkeypatch.setenv(auth.OPERATOR_KEY_ENV, OPERATOR)
    for name in szl_dsse.PRIVATE_KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("SZL_COSIGN_PRIVATE_PEM", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode("ascii"))
    monkeypatch.setattr(szl_dsse, "_RUNTIME_PUBLIC_KEYS", {})
    monkeypatch.setattr(szl_dsse, "_ACTIVE_RUNTIME_KEYID", None)
    return key


def client_for(namespace):
    app = FastAPI()
    auth.install_gate(app)
    provenance.register_provenance(app, namespace)
    return TestClient(app)


def sign(client, namespace):
    return client.post(f"/api/{namespace}/khipu/sign",
                       headers={"Authorization": "Bearer " + OPERATOR},
                       json={"receipt": {"schema": "test/standalone", "nonce": "synthetic"}})


@pytest.mark.parametrize("namespace", ["killinchu", "a11oy"])
def test_standalone_signing_retains_memory_contract(standalone, namespace):
    with client_for(namespace) as client:
        result = sign(client, namespace)
        assert result.status_code == 200 and result.json()["signed"] is True
        assert result.json()["retention"] == {"state": "PROCESS_MEMORY", "confirmed": False}
        envelope = result.json()["dsse"]
        kind = envelope["payloadType"].encode()
        payload = base64.b64decode(envelope["payload"])
        pae = b"DSSEv1 " + str(len(kind)).encode() + b" " + kind + b" " + str(len(payload)).encode() + b" " + payload
        standalone.public_key().verify(base64.b64decode(envelope["signatures"][0]["sig"]),
                                       pae, ec.ECDSA(hashes.SHA256()))
        ledger = client.get(f"/api/{namespace}/khipu/ledger").json()
        assert ledger["count"] == 1 and ledger["nodes"][0]["digest"] == result.json()["digest"]
        assert ledger["signing_available"] is False
        assert ledger["signing_state"]["signing_ready"] is False


@pytest.mark.parametrize("recorded", [False, True])
def test_ledger_never_loads_or_generates_keys(standalone, monkeypatch, recorded):
    with client_for("killinchu") as client:
        if recorded:
            assert sign(client, "killinchu").status_code == 200
        before = list(client.app.state.szl_khipu_dag.nodes)

        def forbidden(*_args, **_kwargs):
            pytest.fail("passive ledger read reached key loading or signing")

        monkeypatch.setattr(szl_dsse, "sign_payload", forbidden)
        monkeypatch.setattr(szl_dsse, "_load_private_key", forbidden)
        monkeypatch.setattr(szl_dsse, "public_key_fingerprint", forbidden)
        monkeypatch.setattr(ec, "generate_private_key", forbidden)
        response = client.get("/api/killinchu/khipu/ledger")
        assert response.status_code == 200
        assert response.json()["count"] == int(recorded)
        assert response.json()["signing_state"]["execution_authorized"] is False
        assert client.app.state.szl_khipu_dag.nodes == before


def test_managed_intent_without_owner_refuses_memory_fallback(standalone, monkeypatch):
    monkeypatch.setenv("A11OY_STATE_STORE", "v2")
    with client_for("killinchu") as client:
        def forbidden(*_args, **_kwargs):
            pytest.fail("unavailable managed owner signed a receipt")
        monkeypatch.setattr(szl_dsse, "sign_payload", forbidden)
        assert sign(client, "killinchu").status_code == 503
        assert client.get("/api/killinchu/khipu/ledger").status_code == 503


def test_mirrored_a11oy_verification_gate_refuses_anonymous_signing(standalone, monkeypatch):
    with client_for("a11oy") as client:
        def forbidden(*_args, **_kwargs):
            pytest.fail("anonymous verification reached signer")
        monkeypatch.setattr(szl_dsse, "sign_payload", forbidden)
        monkeypatch.setattr(szl_dsse, "verify_envelope", forbidden)
        result = client.post("/api/a11oy/khipu/verify", json={})
        assert result.status_code == 401
        assert client.app.state.szl_khipu_dag.nodes == []


@pytest.mark.parametrize("dockerfile", ["Dockerfile", "deploy/space/Dockerfile"])
def test_passive_projection_module_is_copied_into_image(dockerfile):
    root = Path(__file__).resolve().parents[1]
    assert "COPY szl_signing_state.py ./" in (root / dockerfile).read_text()


class _LegacyLedger:
    """Minimal managed owner: validate the stored chain, then append."""

    def __init__(self):
        self.rows = []

    def provenance_nodes(self, space, validate):
        assert space == "killinchu"
        validate(self.rows)
        return list(self.rows)

    def append_provenance_node(self, space, build, validate, *, confirm=False):
        assert space == "killinchu" and confirm is False
        validate(self.rows)
        parents = [self.rows[-1]["digest"]] if self.rows else []
        node = build(len(self.rows), parents)
        validate([*self.rows, node])
        self.rows.append(node)
        return node, None


class _LegacyStore:
    def __init__(self, ledger):
        self._ledger = ledger

    def active(self):
        return self._ledger

    def enabled(self):
        return True


@pytest.mark.parametrize(("number", "token"), [
    (float("nan"), b"NaN"),
    (float("inf"), b"Infinity"),
    (-float("inf"), b"-Infinity"),
], ids=["nan", "infinity", "negative-infinity"])
def test_legacy_nonfinite_chain_reloads_and_accepts_finite_append(monkeypatch, number, token):
    """A chain signed before non-finite rejection must load, then accept a finite append."""
    private = ec.generate_private_key(ec.SECP256R1())
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode("ascii")
    for name in szl_dsse.PRIVATE_KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SZL_COSIGN_PRIVATE_PEM", private_pem)
    monkeypatch.setenv("A11OY_STATE_STORE", "v2")
    monkeypatch.setattr(szl_dsse, "_RUNTIME_PUBLIC_KEYS", {})
    monkeypatch.setattr(szl_dsse, "_ACTIVE_RUNTIME_KEYID", None)

    receipt = {"schema": "legacy/nonfinite", "evidence": [{"score": number}]}
    raw = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    assert b'"score":' + token in raw
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    keyid = szl_dsse.keyid_for_public_pem(public_pem)
    signature = private.sign(
        szl_dsse.pae(szl_dsse.KHIPU_PAYLOAD_TYPE, raw), ec.ECDSA(hashes.SHA256()),
    )
    envelope = {
        "payloadType": szl_dsse.KHIPU_PAYLOAD_TYPE,
        "payload": base64.b64encode(raw).decode("ascii"),
        "signatures": [{"keyid": keyid, "sig": base64.b64encode(signature).decode("ascii")}],
        "signed": True,
    }
    ledger = _LegacyLedger()
    monkeypatch.setattr(provenance, "_state_store", _LegacyStore(ledger))
    dag = provenance._KhipuDAG("killinchu")
    assert dag.managed is True
    legacy = {
        "index": 0,
        "space": "killinchu",
        "receipt": json.loads(raw),
        "dsse": envelope,
        "parents": [],
        "signed": True,
        "keyid": keyid,
        "digest": dag._digest(raw, []),
    }
    with pytest.raises(ValueError):
        szl_dsse.canonical_json(legacy["receipt"])
    tampered = dict(legacy, receipt={
        "schema": "legacy/nonfinite", "evidence": [{"score": 0.0}],
    })
    with pytest.raises(ValueError, match="invalid retained provenance chain"):
        dag._validate([tampered])
    spaced_payload = base64.b64encode(raw + b" ").decode("ascii")
    spaced = dict(legacy, dsse=dict(envelope, payload=spaced_payload))
    with pytest.raises(ValueError, match="invalid retained provenance chain"):
        dag._validate([spaced])

    ledger.rows.append(legacy)
    loaded = dag.nodes
    assert len(loaded) == 1
    assert base64.b64decode(loaded[0]["dsse"]["payload"]) == raw
    score = loaded[0]["receipt"]["evidence"][0]["score"]
    if token == b"NaN":
        assert score != score
    else:
        assert score == number
    assert szl_dsse.verify_envelope(loaded[0]["dsse"])["verified"] is True

    with pytest.raises(ValueError):
        dag.append_signed({"schema": "legacy/nonfinite", "evidence": [{"score": number}]})
    assert len(dag.nodes) == 1

    appended = dag.append_signed({"schema": "successor/finite", "score": 1})
    assert appended["index"] == 1
    assert appended["parents"] == [loaded[0]["digest"]]
    assert appended["signed"] is True
    reloaded = dag.nodes
    assert [node["digest"] for node in reloaded] == [loaded[0]["digest"], appended["digest"]]
    assert base64.b64decode(reloaded[0]["dsse"]["payload"]) == raw
    assert reloaded[1]["receipt"] == {"schema": "successor/finite", "score": 1}
    assert szl_dsse.verify_envelope(reloaded[0]["dsse"])["verified"] is True
    assert szl_dsse.verify_envelope(reloaded[1]["dsse"])["verified"] is True
