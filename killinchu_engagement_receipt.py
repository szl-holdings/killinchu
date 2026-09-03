#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""killinchu_engagement_receipt.py — PCGI proof-carrying engagement receipt.

Turns ONE real killinchu counter-UAS decision output (the edge verdict computed
by ``killinchu_edge_formulas.edge_verdict`` over REAL, caller-submitted drone
telemetry) into a single signed, verifiable szl-receipt so that every
engagement decision becomes independently auditable.

The receipt binds, in one cryptographic subject:
  * input_digest        — sha256 over the canonical telemetry that was decided on
  * output_digest       — sha256 over the canonical decision output (Λ + verdict)
  * governing_policy_id — the policy id that governed the decision
  * measured energy     — honest ``UNAVAILABLE`` (edge inference is NOT
                          instrumented on this node — a joule is NEVER fabricated)
  * optional BFT witnesses — co-signers, if any were supplied

It reuses the EXISTING szl-receipt library (canonicalisation + DSSE/ECDSA-P256
signing + in-toto Statement v1) when installed:

    pip install "git+https://…/szl-receipt.git@v0.2.0"

and falls back to a BYTE-IDENTICAL vendored implementation of the exact same
shapes (``_vendor`` below) when the package install is blocked (e.g. offline
edge / air-gapped CI). Either path produces the identical envelope + statement.

HONESTY DOCTRINE (non-negotiable):
  * The receipt is an EVIDENCE TRAIL — it proves *what the decision was and that
    it has not been altered*. It is NOT a proof that the autonomy is correct.
  * Energy is ``UNAVAILABLE`` because it is unmeasured here; never a fabricated
    number.
  * Λ = Conjecture 1 (NEVER a theorem). Doctrine v11.

Signed-off-by: Forge <forge@a-11-oy.com>
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Path bootstrap so ``killinchu_edge_formulas`` resolves whether we run from the
# repo root (WORKDIR /app) or elsewhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in ("/app", _HERE):
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

import killinchu_edge_formulas as _edge

# Honest sentinel for energy that was not measured on the edge node.
UNAVAILABLE = "UNAVAILABLE"

# The predicate type for a killinchu engagement receipt. Honest: an SZL-owned
# URI (SLSA-*shaped* for recognizability), NEVER a claim of official SLSA
# provenance conformance.
PREDICATE_TYPE = "https://a-11-oy.com/attest/killinchu-engagement/v0.1"

# Identifies the decision producer (model/formula surface) that emitted the
# verdict this receipt attests to.
MODEL_ID = "killinchu-edge-formulas/real-edge-v2"

# Default governing policy id. Callers SHOULD pass their own.
DEFAULT_POLICY_ID = "killinchu-cuas-engagement-policy/v11"


# ---------------------------------------------------------------------------
# szl-receipt binding: prefer the installed library; else a byte-identical
# vendored fallback. Both paths yield identical envelopes + statements.
#
# The vendored primitives below copy szl-receipt's canonicalisation, DSSE PAE,
# receipt-envelope, and in-toto Statement shapes VERBATIM so that — when the
# package install is blocked (offline / air-gapped edge) — the receipt is
# byte-for-byte identical to one produced by the installed library.
# ---------------------------------------------------------------------------
import base64 as _base64
import dataclasses as _dc
import json as _json
# (struct import removed with the B-08 legacy PAE)

_IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
_DEFAULT_PREDICATE_TYPE = "https://a-11-oy.com/attest/szl-receipt/v0.1"
_PAYLOAD_TYPE = "application/vnd.szl.receipt+json"
_UNSIGNED_NOTE = "UNSIGNED-honest: no cosign key present"
_ALGO_SIGNED = "ECDSA-P256-SHA256"
_ALGO_UNSIGNED = "UNSIGNED"


def _v_canonical_json(obj: object) -> bytes:
    return _json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _v_pae(payload_type: str, body: bytes) -> bytes:
    # DSSE v1 spec-exact PAE (ASCII decimal lengths over the decoded bytes),
    # cosign-compatible. Replaces the pre-migration B-08 little-endian form so
    # vendored sign/verify interoperate with the installed szl_receipt package.
    pt = payload_type.encode("utf-8")
    return b" ".join(
        (b"DSSEv1", str(len(pt)).encode("ascii"), pt, str(len(body)).encode("ascii"), body)
    )


def _v_body_digest(body: object) -> str:
    return hashlib.sha256(_v_canonical_json(body)).hexdigest()


@_dc.dataclass
class _VendorReceipt:
    kind: str
    body: Dict[str, Any]

    def digest(self) -> str:
        return _v_body_digest(self.body)


def _v_generate_keypair() -> Tuple[bytes, bytes]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub


def _v_sign_receipt(receipt, private_key_pem, organ: str = "unknown",
                    keyid: str = "") -> Dict[str, Any]:
    digest = receipt.digest()
    payload = _v_canonical_json(receipt.body)
    payload_b64 = _base64.b64encode(payload).decode("ascii")
    if not private_key_pem:
        return {
            "payloadType": _PAYLOAD_TYPE,
            "payload": payload_b64,
            "signature": "",
            "signed": False,
            "organ": organ,
            "keyid": keyid,
            "digest": digest,
            "algo": _ALGO_UNSIGNED,
            "note": _UNSIGNED_NOTE,
        }
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pem = private_key_pem
    if isinstance(pem, str):
        pem = pem.encode("utf-8")
    key = serialization.load_pem_private_key(pem, password=None)
    signing = _v_pae(_PAYLOAD_TYPE, payload)
    der_sig = key.sign(signing, ec.ECDSA(hashes.SHA256()))
    sig_b64 = _base64.b64encode(der_sig).decode("ascii")
    return {
        "payloadType": _PAYLOAD_TYPE,
        "payload": payload_b64,
        "signature": sig_b64,
        "signed": True,
        "organ": organ,
        "keyid": keyid,
        "digest": digest,
        "algo": _ALGO_SIGNED,
    }


def _v_verify_receipt(envelope, public_key_pem=None) -> Tuple[bool, str]:
    if not envelope.get("signed", False):
        return False, "unsigned-honest"
    if not public_key_pem:
        return False, "no public key provided"
    try:
        payload = _base64.b64decode(envelope["payload"])
    except Exception as exc:  # noqa: BLE001
        return False, f"envelope decode error: {exc}"
    try:
        body = _json.loads(payload.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False, "signature mismatch"
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pem = public_key_pem
    if isinstance(pem, str):
        pem = pem.encode("utf-8")
    try:
        pub = serialization.load_pem_public_key(pem)
        signing = _v_pae(_PAYLOAD_TYPE, _v_canonical_json(body))
        der_sig = _base64.b64decode(envelope["signature"])
        pub.verify(der_sig, signing, ec.ECDSA(hashes.SHA256()))
        return True, "ok"
    except InvalidSignature:
        return False, "signature mismatch"
    except Exception as exc:  # noqa: BLE001
        return False, f"invalid key or encoding: {exc}"


def _v_build_statement(*, subject_name: str, subject_digest: str,
                       predicate: Dict[str, Any],
                       predicate_type: str = _DEFAULT_PREDICATE_TYPE,
                       digest_alg: str = "sha256") -> Dict[str, Any]:
    return {
        "_type": _IN_TOTO_STATEMENT_TYPE,
        "subject": [
            {"name": subject_name, "digest": {digest_alg: subject_digest}}
        ],
        "predicateType": predicate_type,
        "predicate": predicate,
    }


def _v_verify_statement(statement, *, expected_digest: str,
                        predicate_type: Optional[str] = None,
                        digest_alg: str = "sha256") -> Tuple[bool, str]:
    if not isinstance(statement, dict):
        return (False, "not-a-statement")
    if statement.get("_type") != _IN_TOTO_STATEMENT_TYPE:
        return (False, "not-an-intoto-statement")
    if (predicate_type is not None
            and statement.get("predicateType") != predicate_type):
        return (False, "unexpected-predicate-type")
    subjects = statement.get("subject") or []
    subj_digests = [
        s.get("digest", {}).get(digest_alg)
        for s in subjects if isinstance(s, dict)
    ]
    if expected_digest not in subj_digests:
        return (False, "subject-digest-not-bound")
    return (True, "ok")


class _VendorImpl:
    """Byte-identical vendored fallback for the szl-receipt primitives."""

    Receipt = _VendorReceipt
    sign_receipt = staticmethod(_v_sign_receipt)
    verify_receipt = staticmethod(_v_verify_receipt)
    build_statement = staticmethod(_v_build_statement)
    verify_statement = staticmethod(_v_verify_statement)
    generate_keypair = staticmethod(_v_generate_keypair)
    IN_TOTO_STATEMENT_TYPE = _IN_TOTO_STATEMENT_TYPE
    PAYLOAD_TYPE = _PAYLOAD_TYPE


def _load_szl_receipt():
    """Return (impl, source) where impl exposes the szl-receipt primitives.

    Primary: the installed ``szl_receipt`` package. Fallback: ``_VendorImpl`` —
    a byte-identical reimplementation of the exact same shapes (canonical_json,
    DSSE/ECDSA-P256 signing, in-toto Statement v1)."""
    try:
        import szl_receipt as _sr  # type: ignore

        class _Impl:
            Receipt = _sr.Receipt
            sign_receipt = staticmethod(_sr.sign_receipt)
            verify_receipt = staticmethod(_sr.verify_receipt)
            build_statement = staticmethod(_sr.build_statement)
            verify_statement = staticmethod(_sr.verify_statement)
            generate_keypair = staticmethod(_sr.generate_keypair)
            IN_TOTO_STATEMENT_TYPE = _sr.IN_TOTO_STATEMENT_TYPE
            PAYLOAD_TYPE = _sr.PAYLOAD_TYPE

        return _Impl, "szl-receipt (installed)"
    except Exception:
        return _VendorImpl, "szl-receipt (vendored byte-identical fallback)"


_SR, _SR_SOURCE = _load_szl_receipt()


def _digest(obj: Any) -> str:
    """sha256 hex over canonical JSON — the single hashing convention."""
    return hashlib.sha256(
        __import__("json").dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def decision_output(verdict: Dict[str, Any]) -> Dict[str, Any]:
    """Project the edge verdict onto its STABLE, decision-relevant fields.

    We hash exactly what makes the engagement decision — the verdict, Λ, the
    decision floor, and the trust axes — NOT the per-process signature or the
    wall-clock timestamp (which would be non-deterministic). This is the honest
    'output' the receipt binds."""
    return {
        "decision": verdict["decision"],
        "lambda": verdict["lambda"],
        "lambda_floor": verdict["lambda_floor"],
        "axes": verdict["axes"],
    }


def emit_engagement_receipt(
    telemetry: Dict[str, Any],
    *,
    policy_id: str = DEFAULT_POLICY_ID,
    private_key_pem: Optional[bytes | str] = None,
    bft_witnesses: Optional[List[str]] = None,
    organ: str = "killinchu",
    ts: Optional[str] = None,
    verdict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute a killinchu edge verdict and emit ONE signed szl-receipt for it.

    Args:
        telemetry: REAL caller-submitted drone telemetry (see
            ``killinchu_edge_formulas.edge_verdict`` for the schema).
        policy_id: The governing engagement policy id bound into the receipt.
        private_key_pem: ECDSA-P256 PEM private key. When ``None``/empty the
            receipt is UNSIGNED-honest (signed=False) — never a fake signature.
        bft_witnesses: Optional list of BFT co-signer ids to record.
        organ: Signing authority label.
        ts: Optional ISO-8601 timestamp override (for deterministic tests);
            defaults to now(UTC).
        verdict: Optional precomputed verdict (else computed from telemetry).

    Returns:
        A bundle dict:
            {
              "receipt": <DSSE envelope>,       # signed or UNSIGNED-honest
              "statement": <in-toto Statement v1>,  # binds subject digest
              "input_digest", "output_digest", "subject_digest",
              "policy_id", "energy_joules" (UNAVAILABLE), "decision",
              "lambda", "verdict", "receipt_source"
            }
    """
    if verdict is None:
        verdict = _edge.edge_verdict(telemetry)

    out = decision_output(verdict)
    input_digest = _digest(telemetry)
    output_digest = _digest(out)

    body: Dict[str, Any] = {
        "organ": organ,
        "decision_type": "counter-uas-engagement",
        "model_id": MODEL_ID,
        "input_digest": input_digest,
        "output_digest": output_digest,
        "decision": out["decision"],
        "lambda": out["lambda"],
        "lambda_floor": out["lambda_floor"],
        "governing_policy_id": policy_id,
        "energy_joules": UNAVAILABLE,
        "energy_note": (
            "edge inference energy is not instrumented on this node "
            "(honest UNAVAILABLE — never fabricated)"
        ),
        "bft_witnesses": list(bft_witnesses or []),
        "digest_alg": "sha256",
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "doctrine": (
            "v11 · Λ = Conjecture 1 (NEVER a theorem); this receipt is an "
            "evidence trail, NOT a proof the autonomy is correct"
        ),
    }

    receipt = _SR.Receipt(kind="counter-uas-engagement", body=body)
    subject_digest = receipt.digest()
    envelope = _SR.sign_receipt(receipt, private_key_pem, organ=organ)

    predicate = {
        "buildType": "https://a-11-oy.com/attest/killinchu-engagement/v0.1",
        "input": {"digest": {"sha256": input_digest}},
        "output": {"digest": {"sha256": output_digest},
                   "decision": out["decision"], "lambda": out["lambda"]},
        "governingPolicy": {"id": policy_id},
        "energy": {"joules": UNAVAILABLE,
                   "note": "unmeasured on edge (honest UNAVAILABLE)"},
        "bftWitnesses": list(bft_witnesses or []),
        "doctrine": "Λ = Conjecture 1 (NEVER a theorem); evidence trail only",
    }
    statement = _SR.build_statement(
        subject_name="killinchu-engagement-receipt",
        subject_digest=subject_digest,
        predicate=predicate,
        predicate_type=PREDICATE_TYPE,
    )

    return {
        "receipt": envelope,
        "statement": statement,
        "input_digest": input_digest,
        "output_digest": output_digest,
        "subject_digest": subject_digest,
        "policy_id": policy_id,
        "energy_joules": UNAVAILABLE,
        "decision": out["decision"],
        "lambda": out["lambda"],
        "verdict": verdict,
        "receipt_source": _SR_SOURCE,
    }


def verify_engagement_receipt(
    bundle: Dict[str, Any],
    *,
    public_key_pem: Optional[bytes | str] = None,
    telemetry: Optional[Dict[str, Any]] = None,
    verdict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Verify a receipt bundle end-to-end.

    Checks, in order:
      1. the in-toto Statement is a valid Statement bound to the receipt digest;
      2. the DSSE envelope signature verifies (or is honestly UNSIGNED);
      3. (optional) the bound input/output digests re-derive from the supplied
         telemetry / verdict — proving the receipt binds the RIGHT decision;
      4. energy is the honest ``UNAVAILABLE`` sentinel (never a number).

    Returns a dict of booleans + detail so callers get an honest, granular
    verdict rather than a single opaque pass/fail."""
    envelope = bundle["receipt"]
    statement = bundle["statement"]
    subject_digest = bundle["subject_digest"]

    stmt_ok, stmt_detail = _SR.verify_statement(
        statement, expected_digest=subject_digest, predicate_type=PREDICATE_TYPE
    )

    sig_ok, sig_detail = _SR.verify_receipt(envelope, public_key_pem)

    digests_match: Optional[bool] = None
    if telemetry is not None or verdict is not None:
        v = verdict if verdict is not None else _edge.edge_verdict(telemetry)
        recomputed_out = _digest(decision_output(v))
        recomputed_in = _digest(telemetry) if telemetry is not None else \
            bundle["input_digest"]
        digests_match = (
            recomputed_out == bundle["output_digest"]
            and recomputed_in == bundle["input_digest"]
        )

    energy_honest = bundle.get("energy_joules") == UNAVAILABLE
    signed = bool(envelope.get("signed", False))

    # A SIGNED envelope must cryptographically verify. An UNSIGNED-honest
    # envelope cannot be "verified" as authentic (no fake pass) — it is only
    # ever an integrity-of-binding claim, so signature_verified stays False.
    verified = bool(
        stmt_ok
        and energy_honest
        and (digests_match is not False)
        and (sig_ok if signed else False)
    )

    return {
        "verified": verified,
        "statement_binds_receipt": stmt_ok,
        "statement_detail": stmt_detail,
        "signature_verified": sig_ok,
        "signature_detail": sig_detail,
        "digests_match": digests_match,
        "energy_honest_unavailable": energy_honest,
        "signed": bool(envelope.get("signed", False)),
    }


def register(app, ns: str = "killinchu") -> str:
    """Mount the engagement-receipt endpoint (additive).

    POST /api/{ns}/v1/edge/engagement-receipt
        body: telemetry (+ optional policy_id, bft_witnesses)
        → { bundle with signed szl-receipt over the edge verdict }

    A fresh per-process ECDSA-P256 key signs the receipt (honest: resets on
    restart; verifies in-process). The public key is returned so a caller can
    verify the signature independently."""
    from starlette.requests import Request as _Request
    from starlette.routing import Route as _Route
    from fastapi.responses import JSONResponse

    priv, pub = _SR.generate_keypair()
    keyid = hashlib.sha256(pub).hexdigest()[:16]

    async def _engagement_receipt(request: _Request):
        body = await request.json()
        telemetry = body.get("telemetry", body)
        policy_id = body.get("policy_id", DEFAULT_POLICY_ID)
        witnesses = body.get("bft_witnesses", [])
        bundle = emit_engagement_receipt(
            telemetry, policy_id=policy_id, private_key_pem=priv,
            bft_witnesses=witnesses,
        )
        bundle["public_key_pem"] = pub.decode("utf-8")
        bundle["keyid"] = keyid
        return JSONResponse(bundle)

    app.router.routes.insert(
        0,
        _Route(f"/api/{ns}/v1/edge/engagement-receipt", _engagement_receipt,
               methods=["POST"], name="kc_edge_engagement_receipt"),
    )
    return f"engagement-receipt-wired:{_SR_SOURCE}"


__all__ = [
    "emit_engagement_receipt",
    "verify_engagement_receipt",
    "decision_output",
    "register",
    "UNAVAILABLE",
    "PREDICATE_TYPE",
    "MODEL_ID",
    "DEFAULT_POLICY_ID",
]

# Doctrine v11 LOCKED · Λ = Conjecture 1 (NEVER a theorem).
# Receipt = evidence trail, not a proof the autonomy is correct.
