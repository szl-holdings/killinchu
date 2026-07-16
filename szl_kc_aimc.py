# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_aimc.py — ADDITIVE Analog In-Memory-Compute ATTENTION simulator for killinchu's frontier
surface (backs a11oy static/3d/surfaces/aimc.js).

Analog In-Memory Computing (AIMC) attention (Leroux, Manea, Sudarshan, Finkbeiner, Siegel,
Strachan, Neftci 2024; arXiv:2409.19315, published in Nature Computational Science 2025) stores
the key/value projections directly in capacitor-based "gain cell" crossbar arrays and computes the
two attention dot-products (Q·K then softmax·V) in the ANALOG domain via Ohm's-law multiply and
Kirchhoff's-law current summation, avoiding the KV-cache data movement that dominates GPU
attention energy. The physics gives large energy/latency wins but injects analog NON-IDEALITIES:
device conductance quantization, capacitor leakage, and read noise, so a hardware-aware
initialization is needed to keep accuracy close to a digital baseline.

This module simulates one sliding-window attention head deterministically (seeded, NO trained
model, NO real circuit): it builds Q, K, V, computes an exact DIGITAL reference attention output,
then computes an ANALOG output where each MAC is perturbed by (a) conductance quantization to a
fixed number of levels and (b) additive read noise. It reports the analog-vs-digital cosine
fidelity and mean-abs error, plus a MODELED energy receipt (analog fJ/MAC vs digital pJ/MAC) that
mirrors the orders-of-magnitude energy reduction the paper reports over GPUs.

Reported (field names read verbatim by aimc.js):
  seq_len, d_head        — sliding-window length and head dimension
  levels                 — analog conductance quantization levels (bits ~ log2(levels))
  attn_cosine_fidelity   — cos(analog_out, digital_out) in [0,1] (MODELED)
  attn_abs_error         — mean |analog_out - digital_out| (MODELED)
  energy_receipt         — analog vs digital MAC energy + reduction factor (MODELED)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic analog-attention SIMULATION. NOT a gain-cell chip running; NO real
    crossbar, NO GPU, NO trained weights, NO wattmeter. Quantization levels, read-noise sigma, and
    per-MAC joules are SEEDED inputs / order-of-magnitude MODELED references, NOT measured.
  * The energy reduction factor is a MODELED order-of-magnitude estimate, not a certified number.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/aimc/attend — analog in-memory attention fidelity + energy snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "aimc_attention": ("Leroux, Manea, Sudarshan, Finkbeiner, Siegel, Strachan, Neftci (2024) "
                       "Analog In-Memory Computing Attention Mechanism for Fast and Energy-"
                       "Efficient Large Language Models — arXiv:2409.19315 · "
                       "https://arxiv.org/abs/2409.19315"),
    "aimc_nature": ("Leroux et al. (2025) Analog in-memory computing attention mechanism for fast "
                    "and energy-efficient large language models — Nature Computational Science · "
                    "https://doi.org/10.1038/s43588-025-00854-1"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | ANALOG_ATTENTION_SIM | NOT_LIVE | NO_CHIP | ENERGY_IS_MODELED"

# MODELED per-MAC energy references (order-of-magnitude only; NOT a live wattmeter).
_E_DIGITAL_PJ = 1.0    # MODELED pJ per digital MAC (GPU-style unit)
_E_ANALOG_FJ = 6.0     # MODELED fJ per analog gain-cell MAC (charge-based)


# ---------------------------------------------------------------------------
# Deterministic LCG PRNG (no numpy, no stdlib random). Numerical Recipes params.
# ---------------------------------------------------------------------------
class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (seed ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def normal(self) -> float:
        u1 = max(1e-12, self.uniform())
        u2 = self.uniform()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _softmax(v):
    m = max(v)
    e = [_math.exp(x - m) for x in v]
    s = sum(e)
    return [x / s for x in e]


def _quantize(x: float, levels: int, lo: float = -3.0, hi: float = 3.0) -> float:
    """Model gain-cell conductance quantization: clip to [lo,hi], snap to `levels` steps."""
    x = max(lo, min(hi, x))
    step = (hi - lo) / (levels - 1)
    q = round((x - lo) / step)
    return lo + q * step


def aimc_attend(seed: int = 42, seq_len: int = 16, d_head: int = 8,
                levels: int = 16, noise_sigma: float = 0.02) -> dict:
    """Analog in-memory attention fidelity + energy snapshot (MODELED).

    seq_len     — sliding-window length (keys/values stored in gain cells).
    d_head      — attention head dimension.
    levels      — analog conductance quantization levels (bits ~ log2(levels)).
    noise_sigma — analog read-noise standard deviation (MODELED).
    seed        — RNG seed; identical inputs give identical output (deterministic).
    """
    T = max(2, min(256, int(seq_len)))
    D = max(1, min(128, int(d_head)))
    L = max(2, min(256, int(levels)))
    sigma = max(0.0, min(1.0, float(noise_sigma)))
    rng = _LCG(int(seed) * 1_000_003 + T * 131 + D * 17 + L * 7)

    scale = 1.0 / _math.sqrt(D)
    q = [rng.normal() for _ in range(D)]              # single query
    K = [[rng.normal() for _ in range(D)] for _ in range(T)]
    V = [[rng.normal() for _ in range(D)] for _ in range(T)]

    # --- Digital reference attention (exact) -----------------------------------------
    logits_d = [sum(q[j] * K[t][j] for j in range(D)) * scale for t in range(T)]
    w_d = _softmax(logits_d)
    out_d = [sum(w_d[t] * V[t][j] for t in range(T)) for j in range(D)]

    # --- Analog in-memory attention (quantized conductances + read noise) -------------
    # K and V are the stored gain-cell states -> quantized; each analog MAC adds read noise.
    Kq = [[_quantize(K[t][j], L) for j in range(D)] for t in range(T)]
    Vq = [[_quantize(V[t][j], L) for j in range(D)] for t in range(T)]
    logits_a = []
    for t in range(T):
        acc = 0.0
        for j in range(D):
            acc += q[j] * Kq[t][j] + sigma * rng.normal()  # per-MAC analog read noise
        logits_a.append(acc * scale)
    w_a = _softmax(logits_a)
    out_a = []
    for j in range(D):
        acc = 0.0
        for t in range(T):
            acc += w_a[t] * Vq[t][j] + sigma * rng.normal()
        out_a.append(acc)

    # --- Fidelity metrics -------------------------------------------------------------
    dot = sum(out_a[j] * out_d[j] for j in range(D))
    na = _math.sqrt(sum(x * x for x in out_a))
    nd = _math.sqrt(sum(x * x for x in out_d))
    cosine = dot / (na * nd) if na > 0 and nd > 0 else 0.0
    abs_error = sum(abs(out_a[j] - out_d[j]) for j in range(D)) / D

    # --- MODELED energy receipt -------------------------------------------------------
    # Attention MAC count ~ 2 * T * D (Q·K then weights·V).
    macs = 2 * T * D
    e_digital_j = macs * _E_DIGITAL_PJ * 1e-12
    e_analog_j = macs * _E_ANALOG_FJ * 1e-15
    reduction_factor = e_digital_j / e_analog_j if e_analog_j > 0 else 0.0
    energy_receipt = {
        "macs": int(macs),
        "joules_digital_modeled": e_digital_j,
        "joules_analog_modeled": e_analog_j,
        "energy_reduction_factor": round(float(reduction_factor), 3),
        "e_digital_per_mac_pj": _E_DIGITAL_PJ,
        "e_analog_per_mac_fj": _E_ANALOG_FJ,
        "energy_note": ("MODELED per-MAC energy — analog gain-cell fJ/MAC vs digital pJ/MAC, "
                        "order-of-magnitude only, NOT a live wattmeter. Storing K/V in-memory "
                        "removes KV-cache data movement, the dominant GPU attention energy cost."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    return {
        "service": "analog-in-memory-attention",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/aimc.js ---
        "seq_len": int(T),
        "d_head": int(D),
        "levels": int(L),
        "bits": round(_math.log2(L), 3),
        "noise_sigma": float(sigma),
        "attn_cosine_fidelity": round(float(cosine), 6),
        "attn_abs_error": round(float(abs_error), 6),
        "energy_receipt": energy_receipt,
        "formulas": {
            "attention": "softmax(qK^T / sqrt(d)) V",
            "analog_mac": "Ohm's law multiply + Kirchhoff current sum, with quantized K/V + read noise",
            "cosine_fidelity": "cos(analog_out, digital_out)",
            "energy_reduction_factor": "E_digital / E_analog (MODELED per-MAC)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python analog-attention non-ideality simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic analog-attention sim; NO gain-cell chip, NO crossbar, "
                            "NO GPU, NO trained weights. A measured-on-silicon path is ROADMAP."),
        },
        "honest_note": ("MODELED analog in-memory attention. Fidelity is analog-vs-digital cosine "
                        "under modeled conductance quantization + read noise; energy is a MODELED "
                        "order-of-magnitude per-MAC estimate, not a wattmeter reading."),
        "wired_into": "frontier ring — Analog-In-Memory-Compute attention surface",
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (advisory fidelity/energy — never autonomous)",
        "citations": {
            "aimc_attention": CITATIONS["aimc_attention"],
            "aimc_nature": CITATIONS["aimc_nature"],
        },
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/aimc" % ns
    path = "%s/attend" % base

    @app.get(path)
    async def _kc_aimc(seed: int = 42, seq_len: int = 16, d_head: int = 8, levels: int = 16):  # noqa: ANN202
        try:
            return JSONResponse(aimc_attend(seed=seed, seq_len=seq_len, d_head=d_head, levels=levels))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "analog-in-memory-attention",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "attn_cosine_fidelity": None, "attn_abs_error": None},
                                status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401 — Route fallback parity with template
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = aimc_attend(seed=42, seq_len=16, d_head=8, levels=16)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "d_head", "levels"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("attn_cosine_fidelity", "attn_abs_error"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))

    # bounds: analog output should track digital (cosine high, error small but non-zero).
    assert 0.5 < r["attn_cosine_fidelity"] <= 1.0, r["attn_cosine_fidelity"]
    assert r["attn_abs_error"] >= 0.0, r["attn_abs_error"]
    er = r["energy_receipt"]
    assert er["energy_reduction_factor"] > 1.0, er
    assert "Conjecture 1" in er["gate"], er
    out["metrics"] = {"attn_cosine_fidelity": r["attn_cosine_fidelity"],
                      "attn_abs_error": r["attn_abs_error"],
                      "energy_reduction_factor": er["energy_reduction_factor"]}

    assert "2409.19315" in r["citations"]["aimc_attention"], r["citations"]

    # determinism
    r2 = aimc_attend(seed=42, seq_len=16, d_head=8, levels=16)
    assert r2["attn_cosine_fidelity"] == r["attn_cosine_fidelity"], "non-deterministic"
    assert r2["attn_abs_error"] == r["attn_abs_error"], "non-deterministic"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2))
    assert res["ok"] is True
    print("ALL OK", file=sys.stderr)
    print("ALL OK")
