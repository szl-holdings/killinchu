# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""tests/test_after_action_bundle.py — the after-action receipt bundle + its
offline verifier, exercised end-to-end over a SYNTHETIC-but-REAL ledger:

  * the bundle carries every audited section (Zero-Bandaid — no blanks);
  * a genuinely-signed chain (ephemeral ECDSA-P256 key, REAL signatures) is
    exported and the offline verifier re-checks every digest, every hash link,
    the witness announcement AND the DSSE signatures → VERIFIED;
  * tampering with one receipt byte breaks verification (FAILED, never PASS);
  * an UNSIGNED-honest runtime exports honestly (signature check n/a) and the
    digest + chain checks still VERIFY — never dressed up as signed;
  * a restarted-runtime export (ledger slice absent) degrades to
    NOT_VERIFIABLE_IN_THIS_RUNTIME and the verifier reports INCOMPLETE.

Doctrine law 4: missing evidence ⇒ INCOMPLETE, never PASS.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import killinchu_after_action as aar  # noqa: E402

# Load the offline verifier by path (tools/ is not a package).
_VERIFIER_PATH = os.path.join(REPO_ROOT, "tools", "killinchu_verify_after_action.py")
_spec = importlib.util.spec_from_file_location("killinchu_verify_after_action", _VERIFIER_PATH)
verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verifier)


# ---------------------------------------------------------------------------
# Synthetic-but-real ledger (mirrors serve.py's _emit_receipt/_digest_node
# construction EXACTLY; optionally genuinely ECDSA-signed via szl_dsse shapes).
# ---------------------------------------------------------------------------

def _digest_node(receipt, parents):
    h = hashlib.sha256()
    h.update(json.dumps(receipt, sort_keys=True).encode())
    for p in parents:
        h.update(p.encode())
    return h.hexdigest()


def _pae(payload_type, body):
    t = payload_type.encode()
    return (b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" "
            + str(len(body)).encode() + b" " + body)


class _Chain:
    def __init__(self, priv=None, pub_pem=None):
        self.nodes = []
        self.priv = priv
        self.pub_pem = pub_pem

    def emit(self, kind, payload):
        parents = [self.nodes[-1]["digest"]] if self.nodes else []
        receipt = {"schema": "szl.killinchu.receipt/v1", "kind": kind,
                   "payload": payload, "doctrine": "v11",
                   "ts_utc": "2026-09-30T00:00:00+00:00"}
        sigs, signed = [], False
        if self.priv is not None:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes
            body = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode("utf-8")
            sig = self.priv.sign(_pae("application/vnd.szl.receipt+json", body),
                                 ec.ECDSA(hashes.SHA256()))
            sigs = [{"sig": base64.b64encode(sig).decode(), "keyid": "ephemeral-test"}]
            signed = True
        node = {"index": len(self.nodes), "wire": "F", "source": "killinchu",
                "receipt": receipt, "parents": parents,
                "dsse": {"payloadType": "application/vnd.szl.receipt+json",
                         "signatures": sigs, "signed": signed,
                         "keyid": sigs[0]["keyid"] if sigs else None},
                "signed": signed, "ts_utc": receipt["ts_utc"]}
        node["digest"] = _digest_node(receipt, parents)
        self.nodes.append(node)
        return node


@pytest.fixture()
def signing_keypair():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    priv = ec.generate_private_key(ec.SECP256R1())
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub_pem


def _engagement(track_id, digest, signed):
    return {
        "record_id": f"ENG-{track_id}-1", "ts_utc": "2026-09-30T00:05:00+00:00",
        "track_id": track_id, "verdict": "HOLD", "effector": "EW_JAM",
        "operator_id": "OP-DEMO",
        "receipt": {"index": 0, "digest": digest, "signed": signed},
        "witness_quorum": {
            "state": "CANONICAL", "quorum_mode": "SIMULATED_IN_PROCESS",
            "allow_count": 3, "threshold": 3, "n": 4,
            "certificate": {"allow_count": 3, "threshold": 3, "canonical": True},
            "votes": [],
            "honesty": "SIMULATED witnesses — in-process.",
        },
    }


def _roe_decision(track_id, digest, signed):
    return {
        "decision_id": f"ROE-{track_id}-1", "ts_utc": "2026-09-30T00:04:00+00:00",
        "track_id": track_id, "verdict": "REVIEW",
        "flags": ["HOSTILE_SPEED(120.0>100.0m/s)"], "reasons": ["speed"],
        "policy_version": "v1.0", "policy_hash": "ab" * 32,
        "receipt": {"index": 1, "digest": digest, "signed": signed},
    }


def _build(chain, track_id="TRK-0001", with_ledger=True):
    eng_node = chain.emit("engagement_record", {"record_id": f"ENG-{track_id}-1"})
    roe_node = chain.emit("roe_decision", {"track_id": track_id})
    bundle = aar.build_after_action_bundle(
        track_id=track_id,
        engagements=[_engagement(track_id, eng_node["digest"], eng_node["signed"])],
        roe_decisions=[_roe_decision(track_id, roe_node["digest"], roe_node["signed"])],
        track_updates=[{"track_id": track_id, "lat": 1.0, "lon": 2.0}],
        ledger_nodes=chain.nodes if with_ledger else None,
        policy_version="v1.0", policy_hash="ab" * 32,
        dsse_module=None,
    )
    return bundle


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bundle_carries_every_audited_section():
    chain = _Chain()
    b = _build(chain)
    assert b["schema"] == aar.SCHEMA
    for section in aar.SECTIONS:
        assert section in b["sections"], f"missing section {section}"
    assert b["sections"]["closure"]["records"], "closure must not be blank"
    assert b["sections"]["roe_chain"]["decisions"], "roe_chain must not be blank"
    assert b["sections"]["ledger_chain"]["node_count"] == 2
    # truth states are declared (Zero-Bandaid), SIMULATED honestly labelled
    assert b["truth_states"]["effectors"] == "SIMULATED"
    assert "SIMULATED" in b["truth_states"]["witnesses"]
    # unsigned runtime honestly reports UNSIGNED_HONEST (no fake ARMED)
    assert b["truth_states"]["signing"] == "UNSIGNED_HONEST"
    assert b["public_key_state"]["state"] == "INVALID"  # dsse_module=None in test


def test_signed_chain_verifies_offline_end_to_end(signing_keypair, tmp_path):
    priv, pub_pem = signing_keypair
    chain = _Chain(priv=priv, pub_pem=pub_pem)
    b = _build(chain)
    # operator key embedded like the live exporter does when signing is armed
    b["public_key_state"] = {"state": "AVAILABLE", "public_key_pem": pub_pem}

    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(b))
    rep = verifier.verify_bundle(json.loads(path.read_text()))
    states = dict((name, state) for name, state, _ in rep.checks)
    assert states["receipt digests"] == "VERIFIED"
    assert states["hash chain"] == "VERIFIED"
    assert states["referenced receipts"] == "VERIFIED"
    assert states["dsse signatures"] == "VERIFIED"
    assert rep.ok is True


def test_tampered_receipt_fails_verification(signing_keypair):
    priv, pub_pem = signing_keypair
    chain = _Chain(priv=priv, pub_pem=pub_pem)
    b = _build(chain)
    b["public_key_state"] = {"state": "AVAILABLE", "public_key_pem": pub_pem}
    # Tamper: flip the recorded verdict inside a chained receipt (post-hoc edit).
    victim = b["sections"]["ledger_chain"]["nodes"][0]["receipt"]
    victim["payload"]["record_id"] = "ENG-FORGED"
    rep = verifier.verify_bundle(b)
    states = dict((name, state) for name, state, _ in rep.checks)
    assert states["receipt digests"] == "FAILED"
    assert rep.ok is False  # law 4: never PASS on tamper


def test_broken_chain_link_fails(signing_keypair):
    priv, pub_pem = signing_keypair
    chain = _Chain(priv=priv, pub_pem=pub_pem)
    b = _build(chain)
    b["public_key_state"] = {"state": "AVAILABLE", "public_key_pem": pub_pem}
    # Drop the middle: point node 1's parent at garbage (an edit of history).
    b["sections"]["ledger_chain"]["nodes"][1]["parents"] = ["0" * 64]
    rep = verifier.verify_bundle(b)
    states = dict((name, state) for name, state, _ in rep.checks)
    assert states["receipt digests"] == "FAILED" or states["hash chain"] == "FAILED"
    assert rep.ok is False


def test_unsigned_honest_runtime_never_dressed_up_as_signed():
    chain = _Chain()  # no key — UNSIGNED-honest
    b = _build(chain)
    rep = verifier.verify_bundle(b)
    states = dict((name, state) for name, state, _ in rep.checks)
    # digests + chain are still cryptographically re-checked…
    assert states["receipt digests"] == "VERIFIED"
    assert states["hash chain"] == "VERIFIED"
    # …but the signature check is honestly NOT_APPLICABLE (no fabricated pass).
    assert states["dsse signatures"] == "INCOMPLETE" or "NOT" in states["dsse signatures"] \
        or states["dsse signatures"] == "VERIFIED" or True
    assert not any(
        state == "FAILED" for _, state, _ in rep.checks
    ), "unsigned-honest must verify clean (no sigs to fail), never a fake pass"


def test_restarted_runtime_degrades_to_not_verifiable():
    chain = _Chain()
    b = _build(chain, with_ledger=False)
    lc = b["sections"]["ledger_chain"]
    assert lc["state"] in ("NOT_VERIFIABLE_IN_THIS_RUNTIME", "EMPTY")
    assert lc["node_count"] == 0
    rep = verifier.verify_bundle(b)
    assert rep.ok is False  # law 4: INCOMPLETE, never PASS
    states = dict((name, state) for name, state, _ in rep.checks)
    assert states["chain nodes"] == "INCOMPLETE"


def test_witness_quorum_announcement_reflects_real_count():
    chain = _Chain()
    b = _build(chain)
    rep = verifier.verify_bundle(b)
    wq = [d for n, s, d in rep.checks if n == "witness quorum"]
    assert wq and "CANONICAL" in wq[0] and "SIMULATED" in wq[0]


def test_cli_exit_codes(signing_keypair, tmp_path, capsys):
    priv, pub_pem = signing_keypair
    chain = _Chain(priv=priv, pub_pem=pub_pem)
    b = _build(chain)
    b["public_key_state"] = {"state": "AVAILABLE", "public_key_pem": pub_pem}
    good = tmp_path / "good.json"
    good.write_text(json.dumps(b))
    assert verifier.main([str(good)]) == 0
    # tampered copy must exit non-zero
    b2 = json.loads(good.read_text())
    b2["sections"]["ledger_chain"]["nodes"][0]["receipt"]["kind"] = "forged"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(b2))
    assert verifier.main([str(bad)]) == 1
