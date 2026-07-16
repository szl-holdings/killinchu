# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_qec.py — FRONTIER WAVE C. ADDITIVE governed TOPOLOGICAL QEC / surface-code
backend for the a11oy frontier surface (static/3d/surfaces/qec.js →
GET /api/killinchu/v1/qec/surface-code), with the SZL mapping:

  "RECEIPTS SURVIVE CORRUPTION LIKE LOGICAL QUBITS SURVIVE NOISE."

WHAT THIS IS
------------
A deterministic, seeded SIMULATION of a rotated surface code's below-threshold
scaling — data qubits on lattice sites, ancilla (syndrome/stabilizer) qubits on
plaquette centers, and the frontier result: below a critical physical error rate,
GROWING the code distance suppresses the logical error rate EXPONENTIALLY (the
"Willow" figure of merit Λ = p_L(d)/p_L(d+2)). Google Quantum AI demonstrated this
below-threshold regime on real superconducting qubits (Nature, 2024).

The SZL twist — the reason this lives on killinchu — is a DIRECT MAP from the
surface-code intuition to how SZL receipts survive storage corruption:

  * A signed receipt is erasure-coded across the Khipu-DAG with Reed-Solomon
    RS(n=10, k=6): 6 data shards + 4 parity shards. Any 6 of the 10 shards
    reconstruct the receipt exactly. This is an ERASURE code (a maximum-distance-
    separable code): it survives up to n-k = 4 erased/corrupted shards, exactly as a
    distance-d surface code survives up to (d-1)/2 physical errors.
  * receipt_survival(p) = P[at least k of n shards intact] under i.i.d. shard-loss p
    is computed EXACTLY from the binomial tail — the honest analogue of the logical
    survival p_L that the quantum lattice reports.

CLOSED-FORM QEC MODEL (shown verbatim in the surface overlay):
  num_data_qubits    = d^2
  num_ancilla        = d^2 - 1
  p_L(d, p)          = A · (p / p_th) ^ ((d+1)/2)          (below-threshold ansatz)
  suppression Λ      = p_L(d, p) / p_L(d+2, p)             (per-two-distance factor)
  below_threshold    = (p < p_th)                          (p_th ≈ 0.01, MODELED)

RS(10,6) KHIPU-DAG ERASURE SURVIVAL (the SZL receipt map):
  receipt_survival(p) = Σ_{i=k..n} C(n,i) (1-p)^i p^(n-i)   (n=10, k=6, exact binomial)
  max_erasures_tolerated = n - k = 4                        (MDS erasure code)

HONESTY SPINE (Doctrine v11):
  * MODELED. Simulation of the METHOD/scaling law — NO proprietary QPU data, NO
    measured hardware syndromes, NO real superconducting device. p_th and A are
    MODELED constants, not device-calibrated.
  * The RS(10,6) survival math is EXACT (binomial); it is an honest analogue of QEC
    survival, NOT a claim that SZL runs a quantum computer.
  * Adds NOTHING to the locked-8. Λ here is the QEC suppression factor (a physics
    figure of merit), distinct from and NOT promoted into SZL's Λ = Conjecture 1.
  * Every result is a SIGNED receipt (REAL ECDSA in-Space; honest UNSIGNED otherwise).

Route (NEW; never collides):
  GET /api/{ns}/v1/qec/surface-code  — surface-code scaling + RS(10,6) receipt survival

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.

LEADERS ADOPTED & CITED (clean-room; NOT claimed as SZL's own):
  Google Quantum AI (2024) "Quantum error correction below the surface code
    threshold" (Willow), Nature 638:920-926 — arXiv:2408.13687
    — https://arxiv.org/abs/2408.13687
  Fowler, Mariantoni, Martinis & Cleland (2012) "Surface codes: Towards practical
    large-scale quantum computation" — arXiv:1208.0928
  Kitaev (1997/2003) "Fault-tolerant quantum computation by anyons" (toric code)
    — arXiv:quant-ph/9707021
  Reed & Solomon (1960) "Polynomial Codes over Certain Finite Fields", J. SIAM 8(2)
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker otherwise
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.qec+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": __import__("base64").b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_QEC_PAYLOAD_TYPE = "application/vnd.szl.kc.qec+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "willow": ("Google Quantum AI (2024) Quantum error correction below the surface "
               "code threshold (Willow), Nature 638:920-926 — arXiv:2408.13687"),
    "fowler": ("Fowler, Mariantoni, Martinis & Cleland (2012) Surface codes: Towards "
               "practical large-scale quantum computation — arXiv:1208.0928"),
    "kitaev": ("Kitaev (1997/2003) Fault-tolerant quantum computation by anyons "
               "(toric code) — arXiv:quant-ph/9707021"),
    "reed_solomon": "Reed & Solomon (1960) Polynomial Codes over Certain Finite Fields, J. SIAM 8(2)",
}

# MODELED label read VERBATIM by qec.js
MODELED_LABEL = "MODELED"
MODELED_LABEL_LONG = "MODELED | SIM_SCALING_LAW | NOT_A_QPU | NO_MEASURED_SYNDROMES"

# MODELED below-threshold constants (NOT device-calibrated)
_P_THRESHOLD = 0.01     # ~1% surface-code accuracy threshold (order of magnitude)
_A_PREFACTOR = 0.03     # MODELED prefactor

# RS(n,k) Khipu-DAG receipt erasure code
_RS_N = 10
_RS_K = 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _comb(n: int, r: int) -> int:
    if r < 0 or r > n:
        return 0
    try:
        return _math.comb(n, r)  # py3.8+
    except AttributeError:  # pragma: no cover
        num = 1
        for i in range(r):
            num = num * (n - i) // (i + 1)
        return num


def _logical_error_rate(d: int, p: float) -> float:
    """Below-threshold ansatz p_L(d,p) = A (p/p_th)^((d+1)/2)."""
    d = max(3, int(d) | 1)
    ratio = max(1e-12, p / _P_THRESHOLD)
    pl = _A_PREFACTOR * (ratio ** ((d + 1) / 2.0))
    # a logical error rate is a probability — clamp to [0,1] for display integrity
    return float(min(1.0, pl))


def _rs_survival(p_loss: float, n: int = _RS_N, k: int = _RS_K) -> float:
    """EXACT P[at least k of n shards intact] under i.i.d. per-shard loss p_loss."""
    p_loss = max(0.0, min(1.0, float(p_loss)))
    q = 1.0 - p_loss
    s = 0.0
    for i in range(k, n + 1):
        s += _comb(n, i) * (q ** i) * (p_loss ** (n - i))
    return float(max(0.0, min(1.0, s)))


def _syndrome_weight(d: int, p: float, seed: int) -> float:
    """MODELED mean fired-stabilizer count this cycle: ~ (#ancilla) · p, deterministic."""
    n_anc = d * d - 1
    # expected fired stabilizers under per-qubit error p, plus a tiny seeded jitter
    jitter_seed = int(_hashlib.sha256(("qecsyn::%d::%d" % (d, seed)).encode()).hexdigest()[:8], 16)
    jitter = ((jitter_seed % 1000) / 1000.0 - 0.5) * 0.1  # ±0.05
    return float(max(0.0, min(n_anc, n_anc * p * 4.0 + jitter)))


def surface_code(distance: int = 5, p: float = 0.003, seed: int = 42) -> dict:
    """Rotated surface-code below-threshold scaling + RS(10,6) receipt-survival map.

    Returns a JSON shape read VERBATIM by a11oy static/3d/surfaces/qec.js:
      { label, code_distance, physical_error_rate, num_data_qubits, num_ancilla,
        syndrome_weight, logical_error_rate, suppression_factor, below_threshold,
        threshold_note, receipt_erasure_code{...}, signed_receipt, ... }
    """
    # ---- bounds (defensive; qec.js lattice caps at 25x25) ----
    d = max(3, min(25, int(distance) | 1))  # force odd
    p = max(0.0, min(0.5, float(p)))

    n_data = d * d
    n_ancilla = d * d - 1

    p_L = _logical_error_rate(d, p)
    p_L_next = _logical_error_rate(d + 2, p)
    suppression = float(p_L / p_L_next) if p_L_next > 0 else 1.0
    syn_weight = _syndrome_weight(d, p, seed)
    below = bool(p < _P_THRESHOLD)

    if below:
        threshold_note = ("BELOW threshold (p=%.3g < p_th=%.3g): logical error suppressed "
                          "exponentially with distance — Λ=%.3f× per +2 distance" %
                          (p, _P_THRESHOLD, suppression))
    else:
        threshold_note = ("AT/ABOVE threshold (p=%.3g >= p_th=%.3g): growing d does NOT "
                          "help — logical error does not shrink" % (p, _P_THRESHOLD))

    # ---- SZL map: RS(10,6) Khipu-DAG receipt erasure survival ----
    # Use the SAME physical rate p as the per-shard loss so the two survival curves are
    # directly comparable on the same axis (the frontier storytelling).
    receipt_survival = _rs_survival(p)
    survival_curve = [{"p_loss": round(pl, 4),
                       "receipt_survival": round(_rs_survival(pl), 6)}
                      for pl in (0.0, 0.05, 0.10, 0.20, 0.30, 0.40)]

    receipt_erasure_code = {
        "scheme": "Reed-Solomon RS(n=%d, k=%d) over the Khipu-DAG" % (_RS_N, _RS_K),
        "n_shards": _RS_N,
        "k_data_shards": _RS_K,
        "parity_shards": _RS_N - _RS_K,
        "max_erasures_tolerated": _RS_N - _RS_K,
        "receipt_survival_at_p": round(float(receipt_survival), 6),
        "survival_curve": survival_curve,
        "mapping": ("receipts survive corruption like logical qubits survive noise — "
                    "RS(10,6) is an MDS erasure code: any %d of %d shards reconstruct the "
                    "receipt, tolerating up to %d erased/corrupted shards, exactly as a "
                    "distance-d surface code tolerates up to (d-1)/2 physical errors" %
                    (_RS_K, _RS_N, _RS_N - _RS_K)),
        "formula": "receipt_survival(p)=Σ_{i=k..n} C(n,i)(1-p)^i p^(n-i)",
        "label": "MODELED (analogue) · RS math EXACT (binomial)",
    }

    receipt = {
        "window_timestamp": _now_iso(),
        "organ": "topological-qec-surface-code",
        "organ_version": "szl-kc-qec-v0.1",
        "data_source": "SIM_SCALING_LAW",
        "code_distance": d,
        "physical_error_rate": p,
        "logical_error_rate": p_L,
        "suppression_factor": round(suppression, 6),
        "below_threshold": below,
        "receipt_survival_rs_10_6": round(float(receipt_survival), 6),
        "label": MODELED_LABEL_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda_szl": "Conjecture 1 (advisory, NOT a theorem) — DISTINCT from QEC suppression Λ",
        "lambda_qec_note": ("suppression_factor is the Willow QEC figure of merit "
                            "Λ_QEC = p_L(d)/p_L(d+2); it is NOT promoted into SZL's Λ = Conjecture 1"),
        "effector_posture": "N/A (physics/erasure simulation — never an engage)",
        "citations": [CITATIONS["willow"], CITATIONS["fowler"],
                      CITATIONS["kitaev"], CITATIONS["reed_solomon"]],
        "honesty": ("MODELED surface-code scaling law — NO QPU, NO measured syndromes, "
                    "p_th/A are MODELED constants. The RS(10,6) receipt-survival math is EXACT "
                    "(binomial tail); it is an honest analogue of QEC survival, not a claim that "
                    "SZL runs a quantum computer."),
    }
    dsse = _sign_payload(receipt, _QEC_PAYLOAD_TYPE)

    return {
        "service": "topological-qec",
        "label": MODELED_LABEL,              # read VERBATIM by qec.js
        "code_distance": d,
        "physical_error_rate": p,
        "num_data_qubits": n_data,
        "num_ancilla": n_ancilla,
        "syndrome_weight": round(float(syn_weight), 4),
        "logical_error_rate": p_L,
        "suppression_factor": round(float(suppression), 6),
        "below_threshold": below,
        "threshold_note": threshold_note,
        "receipt_erasure_code": receipt_erasure_code,
        "formulas": {
            "num_data_qubits": "d^2",
            "num_ancilla": "d^2 - 1",
            "logical_error_rate": "p_L(d,p) = A (p/p_th)^((d+1)/2)",
            "suppression": "Λ = p_L(d,p) / p_L(d+2,p)",
            "receipt_survival": "receipt_survival(p)=Σ_{i=k..n} C(n,i)(1-p)^i p^(n-i), RS(10,6)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python (stdlib)",
            "label": "MODELED",
            "honest_note": ("Closed-form below-threshold ansatz + EXACT binomial RS(10,6) survival. "
                            "NO QPU, NO decoder, NO measured hardware syndromes."),
        },
        "wired_into": "frontier ring · topological-QEC organ (qec.js)",
        "citations": [CITATIONS["willow"], CITATIONS["reed_solomon"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/qec" % ns

    @app.get("%s/surface-code" % base)
    async def _kc_qec(distance: int = 5, p: float = 0.003, seed: int = 42):  # noqa: ANN202
        try:
            return JSONResponse(surface_code(distance=distance, p=p, seed=seed))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "topological-qec", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "code_distance": None, "logical_error_rate": None,
                                 "suppression_factor": None, "below_threshold": None},
                                status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/surface-code" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = surface_code(distance=5, p=0.003, seed=42)
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("code_distance", "physical_error_rate", "num_data_qubits", "num_ancilla",
              "syndrome_weight", "logical_error_rate", "suppression_factor",
              "below_threshold", "threshold_note"):
        assert f in r, f
    assert r["code_distance"] == 5, r["code_distance"]
    assert r["num_data_qubits"] == 25, r["num_data_qubits"]
    assert r["num_ancilla"] == 24, r["num_ancilla"]
    assert 0.0 <= r["syndrome_weight"] <= r["num_ancilla"], r["syndrome_weight"]
    assert isinstance(r["below_threshold"], bool), r["below_threshold"]
    # p=0.003 < p_th=0.01 => below threshold, suppression > 1 (errors shrink with d)
    assert r["below_threshold"] is True, r["below_threshold"]
    assert r["suppression_factor"] > 1.0, r["suppression_factor"]
    out["below"] = {"pL": r["logical_error_rate"], "supp": r["suppression_factor"]}

    # above threshold: p large => no suppression benefit (<=1)
    hi = surface_code(distance=5, p=0.05, seed=42)
    assert hi["below_threshold"] is False, hi["below_threshold"]
    out["above"] = {"pL": hi["logical_error_rate"], "below": hi["below_threshold"]}

    # RS(10,6) erasure survival: MDS, tolerates 4 erasures; survival monotone-decreasing in p
    ec = r["receipt_erasure_code"]
    assert ec["n_shards"] == 10 and ec["k_data_shards"] == 6, ec
    assert ec["max_erasures_tolerated"] == 4, ec
    assert abs(_rs_survival(0.0) - 1.0) < 1e-9, _rs_survival(0.0)
    curve = [c["receipt_survival"] for c in ec["survival_curve"]]
    assert all(curve[i] >= curve[i + 1] - 1e-9 for i in range(len(curve) - 1)), curve
    out["rs_survival"] = ec["receipt_survival_at_p"]

    # determinism
    r2 = surface_code(distance=5, p=0.003, seed=42)
    assert r2["syndrome_weight"] == r["syndrome_weight"], "non-deterministic"

    # signed receipt present + honest label; never fabricated
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_A_QPU" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    out["signed"] = d.get("signed")
    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
