#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""killinchu_edge_formulas.py — REAL-EDGE formula surface (real-edge-v2 cycle).

Mounts the formulas that materially help the killinchu edge organ make and sign verdicts
over noisy, adversarial, multi-sensor drone telemetry. ADDITIVE, self-contained,
register(app, ns="killinchu")-style. NO MOCKS: every endpoint operates on whatever real
telemetry the caller submits; the DSSE receipt is a real ECDSA-P256 PAE-v1 signature.

Endpoints:
  POST /api/killinchu/v1/edge/verdict        accepts real telemetry → Λ ∈ [0,1] + DSSE receipt
  POST /api/killinchu/v1/edge/track-smooth   Kalman smoothing of a noisy trajectory
  GET  /api/killinchu/v1/edge/quorum-status  Byzantine quorum on 5-sensor fusion (f=1)
  GET  /api/killinchu/v1/formulas/index      wired formulas + thesis citation + Lean permalink

Λ definition (edge): the canonical Lutar geometric-mean aggregator over normalised trust
axes. For the edge we aggregate per-formula sub-scores in [0,1]:
  Λ = (∏ᵢ sᵢ)^(1/k),  with sᵢ ∈ {confidence (PAC-Bayes), quorum_ok, track_consistency}.
This is A5-permutation-invariant by construction (geometric mean of the axes) and is a
DECIDABLE pass/fail against a floor — consistent with Lutar/LambdaPermInvariant.lean.

Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem).
Signed-off-by: Yachay <yachay@szlholdings.ai>
Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

# Path bootstrap: vendored package sits at repo root (WORKDIR /app) next to this file.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in ("/app", _HERE):
    if os.path.isdir(os.path.join(_cand, "szl_shared_formulas")) and _cand not in sys.path:
        sys.path.insert(0, _cand)

from szl_shared_formulas import pac_bayes, kalman, byzantine_quorum, welford, bloom_filter

try:  # module-level so FastAPI's PEP-563 string-annotation resolution sees Request
    from fastapi import Request
    _FastAPIRequest = Request
except Exception:  # pragma: no cover
    Request = None
    _FastAPIRequest = None

LEAN_BASE = "https://github.com/szl-holdings/lutar-lean/blob"

_INDEX = [
    {"name": "pac_bayes", "endpoint": "/api/killinchu/v1/edge/verdict",
     "citation": pac_bayes.CITATION, "lean_theorem": pac_bayes.LEAN_THEOREM,
     "lean_permalink": pac_bayes.LEAN_PERMALINK},
    {"name": "kalman", "endpoint": "/api/killinchu/v1/edge/track-smooth",
     "citation": kalman.CITATION, "lean_theorem": kalman.LEAN_THEOREM,
     "lean_permalink": kalman.LEAN_PERMALINK},
    {"name": "byzantine_quorum", "endpoint": "/api/killinchu/v1/edge/quorum-status",
     "citation": byzantine_quorum.CITATION, "lean_theorem": byzantine_quorum.LEAN_THEOREM,
     "lean_permalink": byzantine_quorum.LEAN_PERMALINK},
    {"name": "welford", "endpoint": "/api/killinchu/v1/edge/verdict",
     "citation": welford.CITATION, "lean_theorem": welford.LEAN_THEOREM,
     "lean_permalink": (LEAN_BASE + "/f3153a684e7d9b77462d58185bd1eae0aeacd1bc/"
                        "Lutar/Innovations/round11/FrontierWelfordVariance.lean#L89")},
    {"name": "bloom_filter", "endpoint": "/api/killinchu/v1/edge/verdict",
     "citation": bloom_filter.CITATION, "lean_theorem": bloom_filter.LEAN_THEOREM,
     "lean_permalink": (LEAN_BASE + "/f3153a684e7d9b77462d58185bd1eae0aeacd1bc/"
                        "Lutar/Innovations/round11/FrontierBloomCacheBypass.lean#L77")},
]

# ---- Real DSSE-v1 ECDSA-P256 receipt (no fake signatures) -------------------------
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    _CRYPTO = True
except Exception:  # pragma: no cover
    _CRYPTO = False

_SIGNER = None
_PUBPEM = None
_KEYID = None


def _signer():
    global _SIGNER, _PUBPEM, _KEYID
    if _SIGNER is None and _CRYPTO:
        _SIGNER = ec.generate_private_key(ec.SECP256R1())
        _PUBPEM = _SIGNER.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        _KEYID = hashlib.sha256(_PUBPEM.encode()).hexdigest()[:16]
    return _SIGNER


def _pae(payload_type: str, payload: bytes) -> bytes:
    t = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


def _dsse_receipt(claim: dict) -> dict:
    """Mint a real DSSE-v1 ECDSA receipt over the claim. Honest: per-process key."""
    payload = json.dumps(claim, sort_keys=True, separators=(",", ":")).encode()
    ptype = "application/vnd.szl.killinchu.edge-verdict+json"
    if not _CRYPTO:
        return {"signed": False, "reason": "cryptography backend unavailable (honest)",
                "payload_sha256": hashlib.sha256(payload).hexdigest()}
    s = _signer()
    sig = s.sign(_pae(ptype, payload), ec.ECDSA(hashes.SHA256()))
    return {
        "signed": True,
        "payloadType": ptype,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "signatures": [{"keyid": _KEYID, "sig": sig.hex()}],
        "publicKeyPem": _PUBPEM,
        "scheme": "ecdsa-p256-sha256-dsse-v1",
        "note": "per-process key, resets on restart (honest); verifies in-process",
    }


# ---- Λ aggregator (geometric mean of normalised axes; A5-invariant) ---------------
def compute_lambda(axes: dict) -> float:
    """Λ = (∏ sᵢ)^(1/k) over axis scores in [0,1]. Clamped, A5-invariant."""
    vals = [min(max(float(v), 0.0), 1.0) for v in axes.values() if v is not None]
    if not vals:
        return 0.0
    log_sum = sum(math.log(v) if v > 0 else -math.inf for v in vals)
    if log_sum == -math.inf:
        return 0.0
    return math.exp(log_sum / len(vals))


def edge_verdict(telemetry: dict) -> dict:
    """Compute an edge verdict Λ over REAL telemetry and sign a DSSE receipt.

    telemetry schema (all real, caller-provided):
      sensors        : {sensor_id: position_value}  (≥1; quorum needs n≥4 for f=1)
      track          : [float, ...] noisy position series (optional, for consistency axis)
      fusion_window  : int   (samples used; default len of track or 32)
      empirical_risk : float observed disagreement rate in [0,1] (default from quorum)
      threat_keys    : [str] signatures to membership-check against the threat bloom
      lambda_floor   : float decision floor (default 0.5)
    """
    sensors = telemetry.get("sensors", {})
    track = telemetry.get("track", [])
    floor = float(telemetry.get("lambda_floor", 0.5))

    # --- Byzantine quorum over the sensors (f=1) ---
    f = int(telemetry.get("f", 1))
    sensor_tol = float(telemetry.get("sensor_tol", 1.0))
    quorum = byzantine_quorum.fuse_sensors(sensors, f=f, tol=sensor_tol) if sensors else \
        {"quorum_met": False, "agreement_count": 0, "required_quorum": 2 * f + 1,
         "bft_feasible": False, "n": 0, "verdict": "REFUSE",
         "citation": byzantine_quorum.CITATION, "lean_theorem": byzantine_quorum.LEAN_THEOREM}
    quorum_ok = 1.0 if quorum.get("quorum_met") else 0.0

    # --- PAC-Bayes confidence on the fusion window ---
    n = int(telemetry.get("fusion_window", len(track) or 32))
    n = max(n, 1)
    if "empirical_risk" in telemetry:
        emp_risk = float(telemetry["empirical_risk"])
    else:
        # honest: disagreement fraction among sensors = outliers / n_sensors
        ns = max(quorum.get("n", 1), 1)
        emp_risk = len(quorum.get("suspected_byzantine", [])) / ns
    pb = pac_bayes.bound(emp_risk=emp_risk, n=n, kl=float(telemetry.get("kl", 0.0)),
                         delta=float(telemetry.get("delta", 0.05)), method="catoni")
    confidence = pb["confidence_lower_bound"]

    # --- Track consistency via Kalman jitter reduction (real numpy) ---
    track_consistency = 1.0
    track_stats = None
    if track and len(track) >= 2:
        track_stats = kalman.smooth_track(track,
                                          meas_var=float(telemetry.get("meas_var", 1.0)))
        rj = track_stats["raw_jitter_std"] or 1e-9
        # consistency = how much of the jitter the filter explained as noise, in [0,1]
        track_consistency = min(max(track_stats["smoothed_jitter_std"] / rj, 0.0), 1.0)
        track_consistency = 1.0 - track_consistency  # less residual jitter ⇒ more consistent
        track_consistency = min(max(track_consistency, 0.0), 1.0)

    # --- Welford running stats on the track (streaming Λ proxy) ---
    wf = welford.Welford()
    welford_snap = None
    if track:
        for x in track:
            wf.update(float(x))
        welford_snap = wf.snapshot()

    # --- Threat bloom membership (fast definitely-absent check) ---
    threat_hits = []
    bloom_meta = None
    threat_keys = telemetry.get("threat_keys", [])
    if threat_keys:
        bf = bloom_filter.BloomFilter()
        for k in telemetry.get("known_threats", []):
            bf.add(str(k))
        for k in threat_keys:
            if bf.probably_present(str(k)):
                threat_hits.append(k)
        bloom_meta = {"checked": len(threat_keys), "possible_hits": threat_hits,
                      "citation": bloom_filter.CITATION,
                      "lean_theorem": bloom_filter.LEAN_THEOREM}

    axes = {"confidence": confidence, "quorum_ok": quorum_ok,
            "track_consistency": track_consistency}
    lam = compute_lambda(axes)
    decision = "ALLOW" if (lam >= floor and not threat_hits) else "HALT"

    claim = {
        "organ": "killinchu",
        "lambda": round(lam, 6),
        "lambda_floor": floor,
        "decision": decision,
        "axes": {k: round(v, 6) for k, v in axes.items()},
        "ts": datetime.now(timezone.utc).isoformat(),
        "formulas": ["pac_bayes", "kalman", "byzantine_quorum", "welford", "bloom_filter"],
    }
    receipt = _dsse_receipt(claim)

    return {
        "value": round(lam, 6),
        "lambda": round(lam, 6),
        "lambda_in_unit_interval": bool(0.0 <= lam <= 1.0),
        "lambda_floor": floor,
        "decision": decision,
        "axes": {k: round(v, 6) for k, v in axes.items()},
        "pac_bayes": pb,
        "quorum": quorum,
        "track": track_stats,
        "welford": welford_snap,
        "bloom": bloom_meta,
        "dsse_receipt": receipt,
        "doctrine": "v11 · Λ = Conjecture 1 (NEVER a theorem)",
        "citations": {
            "pac_bayes": pac_bayes.CITATION, "kalman": kalman.CITATION,
            "byzantine_quorum": byzantine_quorum.CITATION, "welford": welford.CITATION,
        },
    }


def verify_receipt(receipt: dict, claim: dict) -> bool:
    """In-process verification of a DSSE-v1 ECDSA receipt against a claim."""
    if not receipt.get("signed") or not _CRYPTO:
        return False
    payload = json.dumps(claim, sort_keys=True, separators=(",", ":")).encode()
    pub = serialization.load_pem_public_key(receipt["publicKeyPem"].encode())
    sig = bytes.fromhex(receipt["signatures"][0]["sig"])
    try:
        pub.verify(sig, _pae(receipt["payloadType"], payload), ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False


def quorum_status(n: int = 5, f: int = 1, sample: dict | None = None) -> dict:
    """Byzantine quorum on multi-sensor fusion. Default: 5 sensors, tolerate 1 fault.

    If `sample` reports are given, fuse them; otherwise return the sizing + a real
    worked example (5 sensors, 1 disagreeing) computed live (NOT a stored mock).
    """
    sizing = byzantine_quorum.required_quorum(n, f)
    if sample:
        fusion = byzantine_quorum.fuse_sensors(sample, f=f)
    else:
        # Real, deterministically-computed worked example: 4 agree on 100.0, 1 spoofed.
        reports = {f"sensor_{i}": 100.0 for i in range(n - 1)}
        reports[f"sensor_{n - 1}"] = 100.0 + 50.0  # byzantine / spoofed fix
        fusion = byzantine_quorum.fuse_sensors(reports, f=f)
        fusion["example"] = "computed live: n-1 sensors agree @100.0, 1 spoofed @150.0"
    return {"sizing": sizing, "fusion": fusion,
            "lean_permalink": byzantine_quorum.LEAN_PERMALINK}


def register(app, ns: str = "killinchu") -> str:
    """Mount the real-edge formula endpoints (additive)."""
    from fastapi.responses import JSONResponse

    @app.get(f"/api/{ns}/v1/formulas/index")
    async def _formulas_index():
        return JSONResponse({"wired": _INDEX, "count": len(_INDEX), "doctrine": "v11",
                            "lambda": "Conjecture 1 (NEVER a theorem)",
                            "source": "killinchu real-edge-v2"})

    @app.post(f"/api/{ns}/v1/edge/verdict")
    async def _edge_verdict(req: Request):
        body = await req.json()
        return JSONResponse(edge_verdict(body))

    @app.post(f"/api/{ns}/v1/edge/track-smooth")
    async def _edge_track(req: Request):
        body = await req.json()
        track = body.get("track")
        if isinstance(track, list) and track and isinstance(track[0], (list, tuple)):
            return JSONResponse(kalman.smooth_track_3d(track,
                               meas_var=float(body.get("meas_var", 1.0))))
        return JSONResponse(kalman.smooth_track(track or [],
                           meas_var=float(body.get("meas_var", 1.0))))

    @app.get(f"/api/{ns}/v1/edge/quorum-status")
    async def _quorum_status(n: int = 5, f: int = 1):
        return JSONResponse(quorum_status(n=n, f=f))

    return f"edge-formulas-wired:{len(_INDEX)}"


__all__ = ["register", "edge_verdict", "verify_receipt", "quorum_status",
           "compute_lambda", "_INDEX"]

# Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem)
# SLSA L1 honest + L2 attested (public Sigstore+Rekor) where slsa-verifier confirms.
