# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Authored for Warhacker 2026 (Cannonico problem). Co-Authored-By: Perplexity Computer Agent.
# Doctrine v11 · Λ Conjecture 1 (NEVER a theorem) · SLSA L1 (killinchu, honest)
"""
tests/test_cannonico_real.py — proves the Cannonico lost-contact autonomous-
governance loop is REAL and operational on killinchu (no mocks):

  1. The loop catches the EXACT moment a line is crossed (envelope breach +
     Λ above floor -> LINE_CROSSED) in a lost-contact decision replay.
  2. In-bounds decisions pass as IN_BOUNDS.
  3. A breach with Λ BELOW the floor escalates to REVIEW (governance is not
     confident enough to assert a crossing on its own) — never silently passes.
  4. With NO signing secret the chain is honestly UNSIGNED (all_signatures_
     verified is null, not a fabricated pass).
  5. With an ephemeral cosign P-256 key present every receipt is REAL-signed,
     verifies via szl_dsse.verify_envelope AND raw cryptography, the Merkle
     chain is contiguous, and tampering with a decision breaks verification.

HONESTY / SAFETY
  - No real org private key is required or baked in. The signed tests GENERATE
    an ephemeral P-256 key at runtime, point szl_dsse at its matching public
    half, and verify against THAT.
  - We exercise the SAME app + SAME _emit_receipt that serve.py ships, so the
    Cannonico chain is the same tamper-evident fiber as every other killinchu
    decision — not a test-only stub.
"""
from __future__ import annotations

import base64
import importlib
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

pytest.importorskip("fastapi")
cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

from fastapi.testclient import TestClient

_PRIV_ENV = "SZL_COSIGN_PRIVATE_KEY_PEM"
_LEGACY_ENV = "SZL_COSIGN_PRIVATE_PEM"

# The authorized-parameters envelope the drone carries into the mission: a 1 km
# operating box, 30 m/s + 120 m ceilings, LOITER/RTB/TRACK allowed (ENGAGE never
# authorized), and ENGAGE additionally requires a human.
_ENVELOPE = {
    "geofence": {"center_lat": 13.16, "center_lon": -72.55, "radius_m": 1000, "mode": "stay_inside"},
    "max_speed_m_s": 30,
    "max_altitude_m": 120,
    "allowed_actions": ["LOITER", "RTB", "TRACK"],
    "require_human_for": ["ENGAGE"],
}

# A lost-contact black-box: 2 in-bounds decisions, then the AI goes off script.
# seq 2 is "the moment": ENGAGE (not allowed + needs human) while outside the box
# and overspeed/over-altitude — every hard constraint breached at once.
_IN_BOUNDS_TEL = {"latitude": 13.16, "longitude": -72.55, "altitude_m": 90, "ground_speed_m_s": 18}
_OFF_SCRIPT_TEL = {"latitude": 13.20, "longitude": -72.60, "altitude_m": 200, "ground_speed_m_s": 55}

_DECISIONS = [
    {"action": "LOITER", "telemetry": _IN_BOUNDS_TEL},
    {"action": "TRACK", "telemetry": _IN_BOUNDS_TEL},
    {"action": "ENGAGE", "telemetry": _OFF_SCRIPT_TEL},  # the moment
    {"action": "RTB", "telemetry": _IN_BOUNDS_TEL},
]


def _gen_ephemeral_keypair():
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return priv_pem, pub_pem


def _fresh_client(monkeypatch, priv_pem: str | None, pub_pem: str | None = None):
    """Build a TestClient on a freshly-imported serve app.

    If priv_pem is given, the env secret is set and szl_dsse is reloaded so its
    signer picks the ephemeral key up; pub_pem (if given) is patched onto
    szl_dsse.COSIGN_PUBLIC_PEM so verify_envelope checks against the matching
    public half. serve + cannonico are reimported fresh each call so the in-
    memory Khipu DAG / mission registry start clean.
    """
    if priv_pem:
        monkeypatch.setenv(_PRIV_ENV, priv_pem)
    else:
        monkeypatch.delenv(_PRIV_ENV, raising=False)
    monkeypatch.delenv(_LEGACY_ENV, raising=False)

    import szl_dsse
    importlib.reload(szl_dsse)
    if pub_pem is not None:
        monkeypatch.setattr(szl_dsse, "COSIGN_PUBLIC_PEM", pub_pem, raising=True)

    import killinchu_cannonico
    importlib.reload(killinchu_cannonico)
    # Make the reloaded cannonico use the reloaded (key-patched) szl_dsse.
    monkeypatch.setattr(killinchu_cannonico, "_dsse", szl_dsse, raising=True)

    import serve
    importlib.reload(serve)
    # serve imported its own szl_dsse at module load; align it to the patched one
    # so the signer + the verify path share the same (ephemeral) keypair.
    if hasattr(serve, "_szl_dsse") and serve._szl_dsse is not None:
        monkeypatch.setattr(serve, "_szl_dsse", szl_dsse, raising=False)
    # serve registered cannonico at import using the module object it imported;
    # re-register on the same app against the reloaded cannonico so the routes
    # use the patched _dsse for their embedded _full_envelope reconstruction.
    serve._cannonico = killinchu_cannonico
    killinchu_cannonico.register(serve.app, emit_receipt=serve._emit_receipt, ns="killinchu")
    return TestClient(serve.app), szl_dsse


def _replay(client, decisions=_DECISIONS, envelope=_ENVELOPE):
    r = client.post("/api/killinchu/v1/cannonico/mission/replay",
                    json={"envelope": envelope, "decisions": decisions})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# 1. The loop catches the exact moment a line is crossed.
# ---------------------------------------------------------------------------

def test_loop_catches_the_moment_a_line_is_crossed(monkeypatch):
    client, _ = _fresh_client(monkeypatch, priv_pem=None)
    out = _replay(client)

    assert out["ok"] is True
    assert out["decision_count"] == 4
    # seq 0 + 1 in bounds; seq 2 is the first breach ("the moment").
    assert out["first_line_crossed_at_seq"] == 2
    moment = out["the_moment"]
    assert moment is not None
    assert moment["seq"] == 2
    assert moment["action"] == "ENGAGE"
    # Every hard constraint is breached at the moment: left box, overspeed,
    # over-altitude, off-script action, and requires-human.
    blob = " | ".join(moment["breaches"]).lower()
    assert "left authorized operating box" in blob
    assert "exceeds authorized ceiling" in blob   # speed and/or altitude
    assert "off script" in blob
    assert "requires human" in blob
    # With default (high) axis scores this is a confident catch: LINE_CROSSED.
    assert out["line_crossings"] >= 1
    seq2 = next(d for d in out["decision_log"] if d["seq"] == 2)
    assert seq2["verdict"] == "LINE_CROSSED"
    assert moment["receipt_digest"] == seq2["receipt"]["digest"]


# ---------------------------------------------------------------------------
# 2. In-bounds decisions pass.
# ---------------------------------------------------------------------------

def test_in_bounds_decisions_pass(monkeypatch):
    client, _ = _fresh_client(monkeypatch, priv_pem=None)
    out = _replay(client, decisions=_DECISIONS[:2])
    assert out["decision_count"] == 2
    assert out["in_bounds"] == 2
    assert out["line_crossings"] == 0
    assert out["first_line_crossed_at_seq"] is None
    for d in out["decision_log"]:
        assert d["verdict"] == "IN_BOUNDS"
        assert d["breaches"] == []


# ---------------------------------------------------------------------------
# 3. Breach + Λ below floor -> REVIEW (never a silent pass).
# ---------------------------------------------------------------------------

def test_low_lambda_breach_escalates_to_review(monkeypatch):
    client, _ = _fresh_client(monkeypatch, priv_pem=None)
    # A breach (off-script ENGAGE outside the box) but with a near-zero axis,
    # which collapses the geometric-mean Λ below the 0.90 floor: governance is
    # not confident enough to assert a crossing -> REVIEW, not LINE_CROSSED.
    low_axes = [0.01] + [0.9] * 12
    out = _replay(client, decisions=[
        {"action": "ENGAGE", "telemetry": _OFF_SCRIPT_TEL, "axis_scores": low_axes},
    ])
    d = out["decision_log"][0]
    assert d["lambda"] < 0.90
    assert d["lambda_pass"] is False
    assert d["breaches"]  # there IS a breach
    assert d["verdict"] == "REVIEW"
    assert out["line_crossings"] == 0
    assert out["reviews"] == 1
    # REVIEW still counts as a flagged breach moment (not in-bounds).
    assert out["first_line_crossed_at_seq"] == 0


# ---------------------------------------------------------------------------
# 4. No secret -> honestly UNSIGNED (null, not a fabricated pass).
# ---------------------------------------------------------------------------

def test_unsigned_when_no_key_is_honest(monkeypatch):
    client, _ = _fresh_client(monkeypatch, priv_pem=None)
    out = _replay(client)
    mission_id = out["mission_id"]
    v = client.get(f"/api/killinchu/v1/cannonico/mission/{mission_id}/verify")
    assert v.status_code == 200, v.text
    vj = v.json()
    assert vj["any_signed"] is False
    # null is the honest verdict for placeholder receipts — NOT True.
    assert vj["all_signatures_verified"] is None
    # The Merkle chain is still contiguous even when unsigned.
    assert vj["merkle_chain_contiguous"] is True


# ---------------------------------------------------------------------------
# 5. Ephemeral key -> REAL signatures that verify; tamper is detected.
# ---------------------------------------------------------------------------

def test_real_signatures_verify_and_tamper_is_detected(monkeypatch):
    priv_pem, pub_pem = _gen_ephemeral_keypair()
    client, szl_dsse = _fresh_client(monkeypatch, priv_pem=priv_pem, pub_pem=pub_pem)
    assert szl_dsse.signing_available() is True

    out = _replay(client)
    mission_id = out["mission_id"]

    # The module's own independent verify path: every signature verifies and the
    # Merkle chain is contiguous.
    v = client.get(f"/api/killinchu/v1/cannonico/mission/{mission_id}/verify").json()
    assert v["any_signed"] is True
    assert v["all_signatures_verified"] is True, v
    assert v["merkle_chain_contiguous"] is True
    assert len(v["checks"]) == 4
    for c in v["checks"]:
        assert c["signature_verified"] is True
        assert c["merkle_link_ok"] is True

    # Independent raw-cryptography verification of one decision receipt: rebuild
    # the exact DSSE PAE bytes and check the ECDSA-P256-SHA256 signature against
    # the ephemeral public key.
    audit = client.get(f"/api/killinchu/v1/cannonico/mission/{mission_id}/audit").json()
    dsse_env = audit["decision_chain"][2]["receipt"]["dsse"]
    assert dsse_env["signed"] is True
    body = base64.b64decode(dsse_env["payload"])
    msg = szl_dsse.pae(dsse_env["payloadType"], body)
    pub = serialization.load_pem_public_key(pub_pem.encode("utf-8"))
    sig = base64.b64decode(dsse_env["signatures"][0]["sig"])
    pub.verify(sig, msg, ec.ECDSA(hashes.SHA256()))  # raises on failure

    # Tamper: flip the recorded action ENGAGE -> LOITER and re-verify. The
    # signature binds the canonical payload, so the tampered envelope must fail.
    tampered = dict(dsse_env)
    decoded = szl_dsse.verify_envelope(dsse_env)
    assert decoded["verified"] is True
    payload_obj = decoded["payload_decoded"]
    assert payload_obj["payload"]["action"] == "ENGAGE"
    payload_obj["payload"]["action"] = "LOITER"
    tampered["payload"] = base64.b64encode(
        szl_dsse.canonical_json(payload_obj)
    ).decode("ascii")
    assert szl_dsse.verify_envelope(tampered)["verified"] is False


@pytest.fixture(autouse=True)
def _restore_module():
    yield
    for _n in (_PRIV_ENV, _LEGACY_ENV):
        os.environ.pop(_n, None)
    import szl_dsse
    importlib.reload(szl_dsse)
