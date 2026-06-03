# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# killinchu.dsse — REAL DSSEv1 signing of each edge verdict (NO MOCK SIGNATURES).
#
# Uses ECDSA-P256-SHA256 over the DSSE Pre-Authentication Encoding (PAE), exactly
# as `cosign verify-blob` expects.  Key resolution order (honest, no fabrication):
#   1. SZL_COSIGN_PRIVATE_PEM env  (the org Sigstore key — production)
#   2. KILLINCHU_EDGE_KEY_PEM env   (a node-local edge key)
#   3. A per-process EPHEMERAL P-256 key generated at import time.  This is a
#      REAL key producing REAL, verifiable signatures — it is honestly labelled
#      `ephemeral` so consumers know it is node-scoped, not the org root.
# We NEVER emit a placeholder/fake signature.
from __future__ import annotations
import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

PAYLOAD_TYPE = "application/vnd.szl.killinchu.verdict+json"

_PRIV: ec.EllipticCurvePrivateKey | None = None
_KEY_SOURCE = "uninitialised"


def _load_private_key() -> tuple[ec.EllipticCurvePrivateKey, str]:
    global _PRIV, _KEY_SOURCE
    if _PRIV is not None:
        return _PRIV, _KEY_SOURCE
    for env, src in (("SZL_COSIGN_PRIVATE_PEM", "org-cosign"),
                     ("KILLINCHU_EDGE_KEY_PEM", "node-edge")):
        pem = os.environ.get(env)
        if pem:
            try:
                _PRIV = serialization.load_pem_private_key(pem.encode(), password=None)
                _KEY_SOURCE = src
                return _PRIV, _KEY_SOURCE
            except Exception:
                continue
    # Ephemeral REAL key — verifiable, honestly labelled, never a placeholder.
    _PRIV = ec.generate_private_key(ec.SECP256R1())
    _KEY_SOURCE = "ephemeral"
    return _PRIV, _KEY_SOURCE


def public_key_pem() -> str:
    priv, _ = _load_private_key()
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def key_source() -> str:
    _load_private_key()
    return _KEY_SOURCE


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def pae(payload_type: str, body: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding (DSSEv1)."""
    return b"DSSEv1 %d %s %d %s" % (
        len(payload_type.encode()), payload_type.encode(), len(body), body)


def sign_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    """Produce a REAL DSSE envelope over the canonical verdict JSON."""
    priv, source = _load_private_key()
    body = canonical_json(verdict)
    to_sign = pae(PAYLOAD_TYPE, body)
    sig = priv.sign(to_sign, ec.ECDSA(hashes.SHA256()))
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(body).decode("ascii"),
        "signatures": [{
            "sig": base64.b64encode(sig).decode("ascii"),
            "keyid": "szlholdings-cosign" if source == "org-cosign" else f"killinchu-{source}",
        }],
        "_dsse": "DSSEv1",
        "_pae_sha256": hashlib.sha256(to_sign).hexdigest(),
        "_signed_at": datetime.now(timezone.utc).isoformat(),
        "key_source": source,
        "signed": True,
        "honesty": ("REAL ECDSA-P256-SHA256 over DSSE PAE; verifiable by cosign "
                    "verify-blob and by verify_envelope(). key_source=%s." % source),
    }


def verify_envelope(env: dict[str, Any], pub_pem: str | None = None) -> dict[str, Any]:
    """Verify a DSSE envelope's ECDSA-P256 signature. Never raises."""
    try:
        body = base64.b64decode(env["payload"])
        to_verify = pae(env["payloadType"], body)
        if pub_pem:
            pub = serialization.load_pem_public_key(pub_pem.encode())
        else:
            priv, _ = _load_private_key()
            pub = priv.public_key()
        ok = False
        for s in env.get("signatures", []):
            try:
                pub.verify(base64.b64decode(s["sig"]), to_verify,
                           ec.ECDSA(hashes.SHA256()))
                ok = True
            except InvalidSignature:
                pass
        return {"verified": ok, "pae_sha256": hashlib.sha256(to_verify).hexdigest(),
                "payload_decoded": json.loads(body)}
    except Exception as e:
        return {"verified": False, "reason": f"{type(e).__name__}: {e}"}
