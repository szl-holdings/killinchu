# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings
# ORCID: 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms
"""
Killinchu — additive post-quantum / hybrid DSSE signing endpoints.

Registers, ADDITIVELY (a11oy-style `register(app, ns)`):
  POST /khipu/sign?mode={ecdsa,pqc,hybrid}
  POST /api/killinchu/v1/khipu/sign?mode={ecdsa,pqc,hybrid}

Honest framing
--------------
* ECDSA P-256 + SHA-256 is the DEFAULT (`mode=ecdsa`). PQC is ADDITIVE.
* `mode=pqc`    → ML-DSA-65 (NIST FIPS 204) only.
* `mode=hybrid` → BOTH ECDSA P-256 and ML-DSA-65; verify requires both.
  Defense procurement (killinchu vertical) asks about PQC; hybrid mode live =
  real competitive advantage.

ML-DSA backend resolution (graceful): liboqs via `oqs-python` (prod) →
pure-Python `dilithium-py` → if neither present, `mode=ecdsa` still works and
pqc/hybrid return HTTP 503 with an honest message (never a fake signature).

Sign: Yachay <yachay@szlholdings.dev>. Perplexity Computer Agent.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

ECDSA_TYPE = "ECDSA-P256-SHA256"
MLDSA_TYPE = "ML-DSA-65"

_MLDSA_BACKEND: Optional[str] = None
_PROC_SIGNERS: dict = {}


def _detect_mldsa() -> Optional[str]:
    global _MLDSA_BACKEND
    if _MLDSA_BACKEND is not None:
        return _MLDSA_BACKEND if _MLDSA_BACKEND != "none" else None
    try:
        import oqs  # type: ignore
        if hasattr(oqs, "Signature") and hasattr(oqs, "get_enabled_sig_mechanisms"):
            _MLDSA_BACKEND = "oqs"
            return "oqs"
    except Exception:
        pass
    try:
        from dilithium_py.ml_dsa import ML_DSA_65  # noqa: F401
        _MLDSA_BACKEND = "dilithium_py"
        return "dilithium_py"
    except Exception:
        pass
    _MLDSA_BACKEND = "none"
    return None


def _mldsa_keypair():
    b = _detect_mldsa()
    if b == "oqs":
        import oqs  # type: ignore
        s = oqs.Signature(MLDSA_TYPE)
        pk = s.generate_keypair()
        return pk, s.export_secret_key()
    if b == "dilithium_py":
        from dilithium_py.ml_dsa import ML_DSA_65
        return ML_DSA_65.keygen()
    raise RuntimeError("no ML-DSA backend")


def _mldsa_sign(sk, msg):
    b = _detect_mldsa()
    if b == "oqs":
        import oqs  # type: ignore
        with oqs.Signature(MLDSA_TYPE, sk) as s:
            return s.sign(msg)
    if b == "dilithium_py":
        from dilithium_py.ml_dsa import ML_DSA_65
        return ML_DSA_65.sign(sk, msg)
    raise RuntimeError("no ML-DSA backend")


def _mldsa_verify(pk, msg, sig):
    b = _detect_mldsa()
    if b == "oqs":
        import oqs  # type: ignore
        with oqs.Signature(MLDSA_TYPE) as s:
            return bool(s.verify(msg, sig, pk))
    if b == "dilithium_py":
        from dilithium_py.ml_dsa import ML_DSA_65
        return bool(ML_DSA_65.verify(pk, msg, sig))
    raise RuntimeError("no ML-DSA backend")


def _pae(payload_type: str, payload: bytes) -> bytes:
    t = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


def _b64(d: bytes) -> str:
    return base64.standard_b64encode(d).decode()


def _keyid(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def _proc_signer(mode: str):
    """Process-local signer per mode (demo/runtime; resets on restart — honest)."""
    if mode in _PROC_SIGNERS:
        return _PROC_SIGNERS[mode]
    bundle = {"ecdsa": None, "mldsa_pk": None, "mldsa_sk": None}
    if mode in ("ecdsa", "hybrid"):
        bundle["ecdsa"] = ec.generate_private_key(ec.SECP256R1())
    if mode in ("pqc", "hybrid"):
        bundle["mldsa_pk"], bundle["mldsa_sk"] = _mldsa_keypair()
    _PROC_SIGNERS[mode] = bundle
    return bundle


PAYLOAD_TYPE = "application/vnd.szl.khipu+json"


def _sign(payload: bytes, mode: str) -> dict:
    data = _pae(PAYLOAD_TYPE, payload)
    s = _proc_signer(mode)
    sigs = []
    ecdsa_ok = mldsa_ok = None
    if mode in ("ecdsa", "hybrid"):
        sig = s["ecdsa"].sign(data, ec.ECDSA(hashes.SHA256()))
        raw = s["ecdsa"].public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        sigs.append({"keyid": _keyid(raw), "sig": _b64(sig), "sig_type": ECDSA_TYPE})
        try:
            s["ecdsa"].public_key().verify(sig, data, ec.ECDSA(hashes.SHA256()))
            ecdsa_ok = True
        except InvalidSignature:
            ecdsa_ok = False
    if mode in ("pqc", "hybrid"):
        sig = _mldsa_sign(s["mldsa_sk"], data)
        sigs.append({"keyid": _keyid(s["mldsa_pk"]), "sig": _b64(sig), "sig_type": MLDSA_TYPE})
        mldsa_ok = _mldsa_verify(s["mldsa_pk"], data, sig)
    if mode == "ecdsa":
        verified = bool(ecdsa_ok)
    elif mode == "pqc":
        verified = bool(mldsa_ok)
    else:
        verified = bool(ecdsa_ok) and bool(mldsa_ok)
    return {
        "mode": mode,
        "sig_types": [x["sig_type"] for x in sigs],
        "verified": verified,
        "doctrine": "v11",
        "envelope": {
            "payload": _b64(payload),
            "payloadType": PAYLOAD_TYPE,
            "signatures": sigs,
        },
        "disclosure": (
            "ECDSA P-256 is the default; PQC (ML-DSA-65 / NIST FIPS 204) is "
            "additive. Hybrid signs with both. Per-process keys reset on restart "
            "(honest). No fake signatures: pqc/hybrid require a real ML-DSA backend."
        ),
    }


def register(app, ns: str = "killinchu") -> None:
    from fastapi import Request
    from fastapi.responses import JSONResponse

    async def _handler(request: Request) -> JSONResponse:
        mode = (request.query_params.get("mode") or "ecdsa").lower()
        if mode not in ("ecdsa", "pqc", "hybrid"):
            return JSONResponse({"error": f"unknown mode '{mode}'"}, status_code=400)
        body = await request.body()
        payload = body if body else b"{}"
        if mode in ("pqc", "hybrid") and _detect_mldsa() is None:
            return JSONResponse(
                {"error": "ML-DSA backend unavailable; install 'oqs' or 'dilithium-py'. "
                          "ECDSA mode still available.", "mode": mode},
                status_code=503,
            )
        try:
            return JSONResponse(_sign(payload, mode))
        except Exception as e:  # never fake a signature
            return JSONResponse({"error": str(e), "mode": mode}, status_code=503)

    app.add_api_route("/khipu/sign", _handler, methods=["POST"])
    app.add_api_route(f"/api/{ns}/v1/khipu/sign", _handler, methods=["POST"])
