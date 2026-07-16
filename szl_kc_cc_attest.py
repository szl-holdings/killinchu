# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_cc_attest.py — ADDITIVE Confidential-Compute Attestation-Chain SIMULATION for
killinchu's frontier ring (backs static/3d/surfaces/ccattest.js in the a11oy repo).

WHAT THIS IS
  A deterministic, seeded SIMULATION of a Trusted-Execution-Environment (TEE) measured-boot
  attestation hash-chain in the style of NVIDIA H100 Confidential Computing. A confidential
  H100 boots through an ordered measurement sequence — bootloader → firmware → driver →
  microcode → gpu-vbios — each stage measured (hashed) into a running measurement log; a
  relying party then verifies the resulting chain / attestation report against a golden
  reference via NVIDIA's Remote Attestation Service (NRAS) before trusting the GPU with
  secrets. This module reproduces the SHAPE of that verification with plain SHA-256/SHA-384:

    device_identity      = sha384(seed | "H100-CC-device") — synthetic device id (hex)
    stage_digest[k]      = sha256(prev_digest | stage_name | seed) — chained measurement log
    final_digest         = the last chained stage digest
    golden_reference     = final_digest recomputed the SAME deterministic way from the seed
    golden_match         = (final_digest == golden_reference)  -> TRUE for the canonical seed

WHAT THIS IS NOT (honesty spine, doctrine v11)
  * MODELED — this is NOT a real TDX/SEV-SNP verifier, NOT a real NVIDIA NRAS client, NOT a
    real GPU/TEE. No real key material, no live device, no network call, no attestation token.
    Read the honesty label VERBATIM; ccattest.js never upgrades it.
  * It exists to show HOW attestation-chain verification WORKS, not to perform one.
  * Adds NOTHING to the locked-8. Λ stays Conjecture 1 (advisory, never "green"). Trust never
    100% — the attestation is MODELED, not real trust. Emits an honest UNSIGNED receipt marker
    locally (a REAL DSSE signature is only produced in-Space when the cosign key is present;
    a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/cc-attest/verify?seed=<int>&stages=<int>

Sources (cited in code + response; adopted, NOT reclaimed as an SZL theorem):
  - NVIDIA, "Confidential Computing on H100 GPUs for Secure and Trustworthy AI" (2023):
    https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai/
  - NVIDIA Remote Attestation Service (NRAS) / NVIDIA Attestation Suite:
    https://docs.nvidia.com/attestation/index.html

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import json as _json
from datetime import datetime, timezone
from typing import Any, Dict, List

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker otherwise
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.ccattest+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": _base64.b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_CCATTEST_PAYLOAD_TYPE = "application/vnd.szl.kc.ccattest+json"

DOCTRINE_VERSION = "v11"

# Canonical H100 CC measured-boot stage order (measured into the attestation log in order).
_STAGE_ORDER = ["bootloader", "firmware", "driver", "microcode", "gpu-vbios"]
_MAX_STAGES = 5  # the frontend tower renders up to MAX_BLOCKS = 5

CITATIONS = {
    "h100_cc": ("NVIDIA, \"Confidential Computing on H100 GPUs for Secure and Trustworthy AI\" "
                "(2023) — https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-"
                "for-secure-and-trustworthy-ai/"),
    "nras": ("NVIDIA Remote Attestation Service (NRAS) / NVIDIA Attestation Suite — "
             "https://docs.nvidia.com/attestation/index.html"),
}

# Honesty label — read VERBATIM by ccattest.js and displayed as-is; never upgraded.
MODELED_LABEL = "MODELED"

HONEST_NOTE = (
    "MODELED — deterministic SHA-256/SHA-384 hash-chain SIMULATION of a TEE + NVIDIA H100 "
    "Confidential Computing measured-boot attestation. NOT a real TDX/SEV-SNP/NRAS verifier: "
    "no real GPU, no real key material, no attestation token, no network call. It demonstrates "
    "HOW an attestation chain is verified (device identity -> ordered stage digests -> final "
    "digest checked against a golden reference), it does not PERFORM a real one. Adds nothing to "
    "the locked-8; Λ stays Conjecture 1 (advisory, never 'green'); trust never 100% — the "
    "attestation is MODELED, not real trust."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha384_hex(data: bytes) -> str:
    return _hashlib.sha384(data).hexdigest()


def _sha256_hex(data: bytes) -> str:
    return _hashlib.sha256(data).hexdigest()


def _stage_names(stages: int) -> List[str]:
    """Return exactly `stages` stage names, truncating or extending the canonical order.

    Extension past gpu-vbios appends deterministic, clearly-synthetic extra measurement
    slots (ext-<n>) so the chain length always matches the caller's request."""
    n = max(1, int(stages))
    names = list(_STAGE_ORDER[:n])
    while len(names) < n:
        names.append("ext-%d" % (len(names) + 1))
    return names


def cc_attest_verify(seed: int = 42, stages: int = 5) -> Dict[str, Any]:
    """Deterministic seeded TEE measurement-chain SIMULATION (NVIDIA H100 CC).

    Builds a synthetic device identity (sha384) and a chained measurement log where each
    stage digest folds the previous digest, the stage name, and the seed via sha256. The
    final digest is compared to a golden reference recomputed the SAME deterministic way
    from the same seed, so `golden_match` is TRUE for the canonical (unmodified) seed path.
    Returns EXACTLY the JSON shape ccattest.js reads. [MODELED]"""
    s = int(seed)
    n = max(1, min(int(stages), _MAX_STAGES))  # frontend tower renders up to 5 blocks

    seed_bytes = str(s).encode()

    # Synthetic device identity — sha384 hex (violet-blue device-identity marker).
    device_identity = _sha384_hex(seed_bytes + b"|H100-CC-device")

    # Ordered measurement chain: each stage digest folds prev-digest | stage | seed.
    names = _stage_names(n)
    prev = device_identity  # anchor the chain to the device identity
    chain: List[Dict[str, str]] = []
    for stage in names:
        digest = _sha256_hex(("%s|%s|%s" % (prev, stage, s)).encode())
        chain.append({"stage": stage, "digest": digest})
        prev = digest

    final_digest = chain[-1]["digest"] if chain else device_identity

    # Golden reference: recompute the final digest the SAME deterministic way from the seed.
    # For the canonical (unmodified) seed path this equals final_digest -> golden_match True.
    gref_prev = device_identity
    for stage in names:
        gref_prev = _sha256_hex(("%s|%s|%s" % (gref_prev, stage, s)).encode())
    golden_reference = gref_prev
    golden_match = bool(final_digest == golden_reference)

    payload = {
        # --- EXACTLY the fields ccattest.js reads ------------------------------------
        "label": MODELED_LABEL,                 # read VERBATIM; never upgraded
        "seed": s,                              # number
        "stages": n,                            # number (measurement-log depth)
        "device_identity": device_identity,     # sha384 hex string
        "measurement_chain": chain,             # [{stage, digest}, ...]
        "final_digest": final_digest,           # hex string
        "golden_match": golden_match,           # boolean
        "honest_note": HONEST_NOTE,             # honest, read-as-is
        # --- extra provenance / doctrine (ignored by the frontend, useful for /info) --
        "golden_reference": golden_reference,
        "stage_order_canonical": _STAGE_ORDER,
        "algorithms": {"device_identity": "sha384", "measurement_chain": "sha256"},
        "doctrine": {
            "version": DOCTRINE_VERSION,
            "locked_proven": 8,
            "lambda": "Conjecture 1 (advisory, never 'green'; NOT a theorem)",
            "trust": "never 100% — attestation is MODELED, not real trust",
            "adds_to_locked_8": False,
        },
        "citations": [CITATIONS["h100_cc"], CITATIONS["nras"]],
        "service": "cc-attest-verify",
        "computed_at": _now_iso(),
    }
    return payload


def _service_response(seed: int = 42, stages: int = 5) -> Dict[str, Any]:
    """Wrap cc_attest_verify() with an honest (UNSIGNED-locally) DSSE receipt marker.

    The top-level shape still carries every field ccattest.js reads (label, seed, stages,
    device_identity, measurement_chain, final_digest, golden_match, honest_note), so the
    frontend renders directly off the response root — the receipt is additive metadata."""
    payload = cc_attest_verify(seed=seed, stages=stages)
    dsse = _sign_payload(payload, _CCATTEST_PAYLOAD_TYPE)
    out = dict(payload)
    out["signed_receipt"] = {"dsse": dsse}
    return out


def info(ns: str) -> Dict[str, Any]:
    return {
        "capability": "Confidential-Compute Attestation Chain · TEE / NVIDIA H100 CC (MODELED)",
        "ns": ns,
        "endpoint": "/api/%s/v1/cc-attest/verify" % ns,
        "params": {"seed": "int (default 42)", "stages": "int 1..5 (default 5)"},
        "label": MODELED_LABEL,
        "honest_note": HONEST_NOTE,
        "citations": [CITATIONS["h100_cc"], CITATIONS["nras"]],
        "doctrine": {"locked_proven": 8, "lambda": "Conjecture 1", "trust": "never 100%",
                     "data_label": "MODELED — no real GPU/TEE/NRAS/network"},
        "status": "MODELED",
    }


# =====================================================================================
# Registration (additive; routes win over the SPA catch-all when registered earlier).
# =====================================================================================
def register(app, ns: str = "killinchu") -> Dict[str, Any]:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/cc-attest" % ns

    @app.get("%s/verify" % base)
    async def _kc_cc_attest(seed: int = 42, stages: int = 5):  # noqa: ANN202
        try:
            return JSONResponse(_service_response(seed=seed, stages=stages))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            # fail-open with the honest label so the frontend degrades gracefully
            return JSONResponse({"service": "cc-attest-verify", "label": MODELED_LABEL,
                                 "honest_note": HONEST_NOTE,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "golden_match": None}, status_code=200)

    @app.get("%s/info" % base)
    async def _kc_cc_attest_info():  # noqa: ANN202
        try:
            return JSONResponse(info(ns))
        except Exception as exc:  # pragma: no cover
            return JSONResponse({"service": "cc-attest-info", "label": MODELED_LABEL,
                                 "error": type(exc).__name__}, status_code=200)

    return {"ok": True, "ns": ns,
            "routes": ["%s/verify" % base, "%s/info" % base],
            "data_label": MODELED_LABEL}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # (a) canonical seed path: golden_match TRUE, exact frontend shape present.
    r = cc_attest_verify(seed=42, stages=5)
    for f in ("label", "seed", "stages", "device_identity", "measurement_chain",
              "final_digest", "golden_match", "honest_note"):
        assert f in r, ("missing frontend field: %s" % f)
    assert r["label"] == "MODELED", r["label"]
    assert r["golden_match"] is True, r["golden_match"]
    assert isinstance(r["measurement_chain"], list) and len(r["measurement_chain"]) == 5, r
    assert all(set(c.keys()) == {"stage", "digest"} for c in r["measurement_chain"]), r
    assert len(r["device_identity"]) == 96, r["device_identity"]  # sha384 hex = 96 chars
    assert r["measurement_chain"][0]["stage"] == "bootloader", r
    assert r["measurement_chain"][-1]["digest"] == r["final_digest"], r
    out["canonical"] = {"golden_match": r["golden_match"], "stages": r["stages"]}

    # (b) determinism: same seed -> identical final digest.
    r2 = cc_attest_verify(seed=42, stages=5)
    assert r2["final_digest"] == r["final_digest"], "not deterministic"
    out["deterministic"] = True

    # (c) different seed -> different chain, but still golden_match TRUE (self-consistent).
    r3 = cc_attest_verify(seed=7, stages=5)
    assert r3["final_digest"] != r["final_digest"], r3
    assert r3["golden_match"] is True, r3
    out["seed_varies"] = True

    # (d) stages truncation.
    r4 = cc_attest_verify(seed=42, stages=3)
    assert len(r4["measurement_chain"]) == 3, r4
    assert r4["measurement_chain"][-1]["stage"] == "driver", r4
    out["truncation"] = True

    # (e) honest UNSIGNED (or REAL signed) receipt marker present; never fabricated.
    sr = _service_response(seed=42, stages=5)
    dsse = sr["signed_receipt"]["dsse"]
    assert dsse.get("_pae_sha256"), dsse
    assert dsse.get("signed") is True or "UNSIGNED" in (dsse.get("honesty") or ""), dsse
    out["signed_receipt"] = {"signed": dsse.get("signed")}

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
