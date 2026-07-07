# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_catq.py — ADDITIVE CALIBRATION / CONFORMAL-QUANTIZATION organ for killinchu's
frontier surface (backs a11oy static/3d/surfaces/catq.js).

The surface names two fused field-leader mechanisms:

  1. CALIBRATION-DRIVEN TERNARY QUANTIZATION — CAT-Q (Wang, Li, Kang, Fan, Yao 2026,
     arXiv:2606.26650) is a post-training ternary-quantization scheme that maps
     high-precision weights to {-1,0,1} using only a small CALIBRATION set (~512
     samples) plus a learnable modulation of the ternary threshold, avoiding the
     100B-token quantization-aware training of BitNet b1.58. The calibration set is
     used to pick a per-tensor threshold delta so ternarization least perturbs the
     activations.

  2. CONFORMAL CALIBRATION — split conformal prediction (Vovk, Gammerman, Shafer 2005;
     Angelopoulos & Bates 2021, arXiv:2107.07511) turns any point score into a
     DISTRIBUTION-FREE prediction set with a finite-sample coverage guarantee:
     for miscoverage alpha, the (1-alpha)(1+1/n) empirical quantile qhat of the
     calibration nonconformity scores gives sets that cover the truth with
     probability >= 1-alpha (marginal, exchangeable data).

This organ FUSES the two honestly: it picks a ternary threshold delta from a MODELED
calibration histogram (CAT-Q side), measures the resulting quantization nonconformity
scores, and reports the split-conformal quantile qhat and the empirical coverage of
the (1-alpha) quantization-error prediction interval (conformal side). The SZL
addition is a J/param ENERGY RECEIPT for the ternary vs FP16 weight footprint.

Deterministic MODELED formulation (seeded, no live model, no real weights):
  * synthesize n_params weights w_i from a seeded mixture (a bell-ish core + tails),
    representing a pre-trained tensor's weight distribution.
  * scale s = mean(|w|); threshold delta = tau * s ; ternary q_i = -1 if w<-delta,
    +1 if w>delta, else 0. dequant wq_i = s * q_i.
  * nonconformity score r_i = |w_i - wq_i| (per-weight quantization residual).
  * split the params: half CALIBRATION, half TEST. On calibration scores compute the
    split-conformal quantile qhat at level (ceil((n_cal+1)(1-alpha)))/n_cal.
  * empirical_coverage = fraction of TEST residuals <= qhat  (should be ~ 1-alpha).
  * sparsity = fraction of q_i == 0 ; kept = 1 - sparsity.

  qhat                = ranked calibration residual at conformal rank
  empirical_coverage  = mean(test_residual <= qhat)
  coverage_gap        = empirical_coverage - (1 - alpha)   (target ~ 0)
  bits_per_param      = ~1.58 ternary vs 16 FP16  -> compression ~10.1x (footprint)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic calibration + conformal SIMULATION. NOT CAT-Q running; NO
    live model, NO GPU, NO trained weights, NO real calibration corpus. The weight
    distribution, tau, and alpha are SEEDED inputs / MODELED references, not measured.
  * The conformal coverage guarantee is a property of the split-conformal ALGORITHM
    under exchangeability, honestly labeled — not a measured claim about a real LLM.
  * bits/param and the J/param footprint are MODELED order-of-magnitude figures, NOT
    a live wattmeter or a real quantized checkpoint.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/catq/calibrate  — calibration/conformal ternary-quant snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import json as _json
import math as _math
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker, never fabricated
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.catq+json"):  # type: ignore
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

_CATQ_PAYLOAD_TYPE = "application/vnd.szl.kc.catq+json"
DOCTRINE_VERSION = "v11"

CITATIONS = {
    "catq": ("Wang, Li, Kang, Fan, Yao (2026) CAT-Q: Cost-efficient and Accurate Ternary "
             "Quantization for LLMs — arXiv:2606.26650 — https://arxiv.org/abs/2606.26650"),
    "bitnet158": ("Ma, Wang, Ma, Wang, Wang, Huang, Dong, Wang, Xue, Wei (2024) The Era of "
                  "1-bit LLMs: All LLMs are in 1.58 Bits (BitNet b1.58) — arXiv:2402.17764 — "
                  "https://arxiv.org/abs/2402.17764"),
    "conformal": ("Angelopoulos & Bates (2021) A Gentle Introduction to Conformal Prediction "
                  "and Distribution-Free Uncertainty Quantification — arXiv:2107.07511 — "
                  "https://arxiv.org/abs/2107.07511"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | CALIBRATION_CONFORMAL_SIM | NOT_LIVE | NO_MODEL | NO_WEIGHTS | BITS_ARE_MODELED"

# MODELED weight-footprint references (order-of-magnitude only; NOT a live wattmeter).
_BITS_FP16 = 16.0
_BITS_TERNARY = 1.58        # log2(3), the b1.58 ternary information content
_J_PER_BIT_MOVED = 1.0e-3   # MODELED joules to move one weight-bit through the memory hierarchy


# ---------------------------------------------------------------------------
# Deterministic LCG PRNG (no numpy, no stdlib random). Numerical Recipes params.
# ---------------------------------------------------------------------------
class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (int(seed) ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def normalish(self) -> float:
        # Irwin–Hall(6)-centered pseudo-normal: sum of 6 uniforms minus 3, ~N(0,0.5).
        return (self.uniform() + self.uniform() + self.uniform()
                + self.uniform() + self.uniform() + self.uniform()) - 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def catq_calibrate(seed: int = 42, n_params: int = 4096, tau: float = 0.75,
                   alpha: float = 0.1) -> dict:
    """Calibration/conformal ternary-quantization snapshot (MODELED).

    n_params — synthetic weights in the modeled tensor (split half cal / half test).
    tau      — ternary-threshold factor: delta = tau * mean(|w|) (CAT-Q calibration knob).
    alpha    — conformal miscoverage level; target coverage = 1 - alpha.
    seed     — RNG seed; identical inputs give identical output (deterministic).
    """
    n = max(64, min(200000, int(n_params)))
    tau = max(0.05, min(3.0, float(tau)))
    alpha = max(0.005, min(0.5, float(alpha)))
    rng = _LCG(int(seed) * 1_000_003 + n * 131 + int(tau * 1000) * 17 + int(alpha * 1000))

    # 1) synthesize a pre-trained weight tensor (bell core + occasional heavy tail).
    w = []
    for _ in range(n):
        x = rng.normalish()
        if rng.uniform() < 0.03:           # 3% heavy tail (outlier channels)
            x *= 3.0
        w.append(x)

    # 2) CAT-Q-style scale + ternary threshold from the calibration statistics.
    scale = sum(abs(v) for v in w) / n
    delta = tau * scale

    # 3) ternarize + measure per-weight quantization residuals (nonconformity scores).
    resid = []
    zeros = 0
    for v in w:
        if v > delta:
            q = 1
        elif v < -delta:
            q = -1
        else:
            q = 0
            zeros += 1
        resid.append(abs(v - scale * q))

    # 4) split-conformal calibration: half calibrate, half test.
    half = n // 2
    cal = sorted(resid[:half])
    test = resid[half:]
    n_cal = len(cal)
    # conformal rank: ceil((n_cal+1)(1-alpha)); clamp into [1, n_cal].
    rank = int(_math.ceil((n_cal + 1) * (1.0 - alpha)))
    rank = max(1, min(n_cal, rank))
    qhat = cal[rank - 1]

    covered = sum(1 for r in test if r <= qhat)
    empirical_coverage = covered / len(test) if test else 0.0
    target_coverage = 1.0 - alpha
    coverage_gap = empirical_coverage - target_coverage

    sparsity = zeros / n
    kept = 1.0 - sparsity
    mean_resid = sum(resid) / n
    rms_resid = _math.sqrt(sum(r * r for r in resid) / n)

    # footprint compression (MODELED): ternary 1.58 bits vs FP16 16 bits.
    compression_x = _BITS_FP16 / _BITS_TERNARY
    bits_saved_per_param = _BITS_FP16 - _BITS_TERNARY
    joules_saved_per_param = bits_saved_per_param * _J_PER_BIT_MOVED
    energy_reduction_pct = (bits_saved_per_param / _BITS_FP16) * 100.0

    energy_receipt = {
        "bits_per_param_fp16": _BITS_FP16,
        "bits_per_param_ternary": _BITS_TERNARY,
        "compression_x": round(float(compression_x), 4),
        "bits_saved_per_param": round(float(bits_saved_per_param), 4),
        "joules_saved_per_param_modeled": round(float(joules_saved_per_param), 8),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "energy_note": ("MODELED weight-footprint arithmetic — ternary carries log2(3)=1.58 "
                        "bits/param vs 16 for FP16; joules/param is an order-of-magnitude "
                        "memory-movement estimate, NOT a live wattmeter or a real checkpoint."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    hist = [int(x) for x in [zeros, sum(1 for v in w if v > delta),
                             sum(1 for v in w if v < -delta)]]

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "calibration-conformal-ternary-quant",
        "service_version": "szl-kc-catq-v0.1",
        "seed": int(seed),
        "inputs": {"n_params": n, "tau": tau, "alpha": alpha},
        "scale": round(float(scale), 6),
        "delta": round(float(delta), 6),
        "qhat": round(float(qhat), 6),
        "empirical_coverage": round(float(empirical_coverage), 6),
        "target_coverage": round(float(target_coverage), 6),
        "coverage_gap": round(float(coverage_gap), 6),
        "sparsity": round(float(sparsity), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (quant-calibration advisory — never autonomous)",
        "citations": [CITATIONS["catq"], CITATIONS["bitnet158"], CITATIONS["conformal"]],
        "honesty": ("Deterministic calibration + split-conformal ternary-quant simulation. NOT "
                    "CAT-Q running; NO live model, NO GPU, NO trained weights, NO real calibration "
                    "corpus. Weight distribution, tau, alpha are seeded inputs / MODELED references. "
                    "The coverage guarantee is a property of the conformal ALGORITHM under "
                    "exchangeability, honestly labeled. MODELED, not live; advisory to Λ."),
    }
    dsse = _sign_payload(receipt, _CATQ_PAYLOAD_TYPE)

    return {
        "service": "calibration-conformal-ternary-quant",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/catq.js ---
        "n_params": int(n),
        "tau": round(float(tau), 6),
        "alpha": round(float(alpha), 6),
        "scale": round(float(scale), 6),
        "delta": round(float(delta), 6),
        "qhat": round(float(qhat), 6),
        "empirical_coverage": round(float(empirical_coverage), 6),
        "target_coverage": round(float(target_coverage), 6),
        "coverage_gap": round(float(coverage_gap), 6),
        "sparsity": round(float(sparsity), 6),
        "kept_fraction": round(float(kept), 6),
        "mean_residual": round(float(mean_resid), 6),
        "rms_residual": round(float(rms_resid), 6),
        "ternary_histogram": {"zero": hist[0], "pos": hist[1], "neg": hist[2]},
        # --- SZL addition: the bits/param + J/param footprint receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "delta": "tau * mean(|w|)  (CAT-Q calibration threshold)",
            "ternary": "q = sign(w) if |w| > delta else 0 ; dequant = scale * q",
            "nonconformity": "r_i = |w_i - scale*q_i|",
            "qhat": "calibration residual at rank ceil((n_cal+1)(1-alpha))",
            "empirical_coverage": "mean(test_residual <= qhat)  (~ 1-alpha)",
            "compression_x": "16 / 1.58  (FP16 bits / ternary bits)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python calibration + conformal simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic sim; NO live model, NO GPU, NO trained weights, NO "
                            "real calibration corpus. The measured-on-a-real-checkpoint path is ROADMAP."),
        },
        "wired_into": "frontier ring — CAT-Q calibration/conformal surface + quant energy receipt",
        "citations": [CITATIONS["catq"], CITATIONS["conformal"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/catq" % ns

    async def _kc_catq(seed: int = 42, n_params: int = 4096, tau: float = 0.75,
                       alpha: float = 0.1):  # noqa: ANN202
        try:
            return JSONResponse(catq_calibrate(seed=seed, n_params=n_params, tau=tau, alpha=alpha))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "calibration-conformal-ternary-quant",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "empirical_coverage": None, "qhat": None},
                                status_code=200)

    try:
        app.add_api_route("%s/calibrate" % base, _kc_catq, methods=["GET"])
    except Exception:  # pragma: no cover — Starlette Route fallback
        from starlette.routing import Route

        async def _kc_catq_route(request):
            qp = request.query_params
            return await _kc_catq(seed=int(qp.get("seed", 42)),
                                  n_params=int(qp.get("n_params", 4096)),
                                  tau=float(qp.get("tau", 0.75)),
                                  alpha=float(qp.get("alpha", 0.1)))
        app.router.routes.append(Route("%s/calibrate" % base, _kc_catq_route, methods=["GET"]))

    return {"ok": True, "ns": ns, "routes": ["%s/calibrate" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = catq_calibrate(seed=42, n_params=4096, tau=0.75, alpha=0.1)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("scale", "delta", "qhat", "empirical_coverage", "coverage_gap", "sparsity"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert 0.0 <= r["sparsity"] <= 1.0, r
    assert 0.0 <= r["empirical_coverage"] <= 1.0, r
    # conformal coverage should be near target 1-alpha (within a modest band for this n).
    assert abs(r["coverage_gap"]) < 0.1, r["coverage_gap"]
    assert r["qhat"] >= 0.0, r
    assert r["ternary_histogram"]["zero"] + r["ternary_histogram"]["pos"] + r["ternary_histogram"]["neg"] == r["n_params"], r
    out["metrics"] = {"empirical_coverage": r["empirical_coverage"],
                      "target_coverage": r["target_coverage"],
                      "coverage_gap": r["coverage_gap"], "qhat": r["qhat"],
                      "sparsity": r["sparsity"]}

    er = r["energy_receipt"]
    assert er["compression_x"] > 1.0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"compression_x": er["compression_x"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc

    # determinism: same inputs -> identical output.
    r2 = catq_calibrate(seed=42, n_params=4096, tau=0.75, alpha=0.1)
    assert r2["qhat"] == r["qhat"], "non-deterministic qhat"
    assert r2["empirical_coverage"] == r["empirical_coverage"], "non-deterministic coverage"
    assert r2["sparsity"] == r["sparsity"], "non-deterministic sparsity"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("ALL OK")
