"""DSSE envelope inspection with fail-closed verification (propose-only).

PAE (Pre-Authentication Encoding) follows the in-toto Attestation
Framework / DSSE v1 shape: "DSSEv1" followed by length-prefixed byte
fields for payloadType, payload, and the serialized signature list.

Honest limitation, disclosed: Python's stdlib ships no Ed25519, so
signature verification is DELEGATED to an injected verifier callable.
Without a verifier the verdict is VERIFICATION_UNAVAILABLE - MEASURED is
never PASS, and every failure mode carries a receipted reason.

PROPOSAL_ONLY, unsigned; merges are owned by the estate signature wall.
No status claims are made about any other pull request.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, List, Optional

VERIFIED = "VERIFIED"
VERIFICATION_UNAVAILABLE = "VERIFICATION_UNAVAILABLE"
SIGNATURE_MISMATCH = "SIGNATURE_MISMATCH"
POLICY_REJECTED = "POLICY_REJECTED"
INVALID = "INVALID"


def pae(payload_type: str, payload: str, signatures: list) -> bytes:
    """DSSE v1 pre-authentication encoding over the envelope fields."""
    if not isinstance(payload_type, str) or not isinstance(payload, str):
        raise TypeError("payload_type and payload must be strings")
    if not isinstance(signatures, list):
        raise TypeError("signatures must be a list")
    sig_bytes = json.dumps(signatures, separators=(",", ":")).encode("utf-8")
    pt = payload_type.encode("utf-8")
    bd = payload.encode("utf-8")
    return b"".join([
        b"DSSEv1",
        b" %d " % len(pt), pt,
        b" %d " % len(bd), bd,
        b" %d " % len(sig_bytes), sig_bytes,
    ])


@dataclass
class Verdict:
    result: str
    reason: str
    payload_type: Optional[str] = None
    signature_count: int = 0

    def as_dict(self) -> dict:
        return {
            "result": self.result,
            "reason": self.reason,
            "payload_type": self.payload_type,
            "signature_count": self.signature_count,
        }


def verify_envelope(envelope_text: str,
                    verifier: Optional[Callable[[bytes, List[bytes]], bool]] = None,
                    policy: Optional[Callable[[str], bool]] = None) -> Verdict:
    """Inspect a DSSE envelope and fail closed at every step.

    - structural faults -> INVALID
    - payloadType rejected by policy -> POLICY_REJECTED
    - no verifier injected -> VERIFICATION_UNAVAILABLE (never PASS)
    - verifier misbehaves -> INVALID (a broken oracle is a fault, not a pass)
    """
    try:
        envelope = json.loads(envelope_text)
    except Exception as exc:
        return Verdict(INVALID, "envelope is not valid JSON: %s" % exc)
    if not isinstance(envelope, dict):
        return Verdict(INVALID, "envelope must be a JSON object")
    payload_type = envelope.get("payloadType")
    payload = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_type, str) or not payload_type:
        return Verdict(INVALID, "payloadType must be a non-empty string")
    if not isinstance(payload, str):
        return Verdict(INVALID, "payload must be a raw string (base64 or utf-8); never decoded here")
    if not isinstance(signatures, list) or not signatures:
        return Verdict(INVALID, "signatures must be a non-empty list")
    for sig in signatures:
        if not isinstance(sig, dict) or not isinstance(sig.get("sig"), str):
            return Verdict(INVALID, "each signature must be an object with a 'sig' string")
    if policy is not None and policy(payload_type) is not True:
        return Verdict(POLICY_REJECTED, "payloadType rejected by policy: %s" % payload_type,
                       payload_type, len(signatures))
    try:
        encoded = pae(payload_type, payload, signatures)
    except Exception as exc:
        return Verdict(INVALID, "PAE encoding failed: %s" % exc, payload_type, len(signatures))
    if verifier is None:
        return Verdict(VERIFICATION_UNAVAILABLE,
                       "no crypto verifier injected: stdlib has no Ed25519; verdict fails closed",
                       payload_type, len(signatures))
    sig_blobs = [s["sig"].encode("utf-8") for s in signatures]
    try:
        ok = verifier(encoded, sig_blobs)
    except Exception as exc:
        return Verdict(INVALID, "verifier raised: %s: %s" % (type(exc).__name__, exc),
                       payload_type, len(signatures))
    if ok is True:
        return Verdict(VERIFIED, "verifier confirmed the signatures over the PAE bytes",
                       payload_type, len(signatures))
    return Verdict(SIGNATURE_MISMATCH, "verifier rejected the PAE bytes/signatures",
                   payload_type, len(signatures))
