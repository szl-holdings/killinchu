# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_kla.py — ADDITIVE Kaczmarz Linear Attention (KLA) state-update simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/kla.js).

Kaczmarz Linear Attention (Zou, Ren, Liu 2026; arXiv:2605.08587) is a one-scalar modification of
Gated DeltaNet (GDN) for linear-attention sequence models. Linear-attention models compress the
context into a fixed-size matrix state S and update it per token with a gated delta rule:
    S_t = a_t * S_t-1 + beta_t * (v_t - S_t-1 k_t) k_t^T
Standard GDN LEARNS the write coefficient beta_t empirically. KLA instead derives it from the
online-regression objective via the Kaczmarz projection method, giving a key-norm-normalized
dynamic step size:
    beta_t = eta_t / (||k_t||_2^2 + eps)
which is the exact-projection step of the Kaczmarz iterative solver. This preserves the state
shape, gates, linear recurrence and chunkwise kernel, but improves stability and the fit of each
delta write. The paper reports lower validation perplexity than GDN (8.09 vs 8.50 at 0.4B / 1B
tokens) and higher decode throughput.

This module simulates the KLA state update deterministically (seeded, NO trained model): it
streams T (key, value) pairs, maintains a fixed d x d state S under BOTH the fixed-beta GDN rule
and the Kaczmarz key-norm-normalized rule, and measures the mean reconstruction residual
||v_t - S k_t|| for each. It reports the KLA-vs-GDN residual and the residual reduction — the
mechanism-level reason KLA fits better.

Reported (field names read verbatim by kla.js):
  seq_len              — T, tokens streamed
  d_state              — d, key/value dimension (state is d x d)
  kla_residual         — mean ||v - S k|| under the Kaczmarz step (MODELED)
  gdn_residual         — mean ||v - S k|| under fixed-beta GDN (MODELED)
  residual_reduction   — (gdn - kla) / gdn, fraction KLA improves the fit
  mean_beta            — mean Kaczmarz step size eta / (||k||^2 + eps)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic delta-rule state-update SIMULATION. NOT trained KLA/GDN running; NO
    learned projections, NO GPU, NO chunkwise CUDA kernel. eta, the gate a_t and the key/value
    streams are SEEDED inputs / MODELED references, NOT measured on any real model.
  * "residual_reduction" is a property of the modeled update rules on modeled data, honestly
    labeled, not the paper's perplexity number and not a benchmark claim about any real model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/kla/update — Kaczmarz linear-attention state-update snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "kla": ("Zou, Ren, Liu (2026) Kaczmarz Linear Attention — arXiv:2605.08587 · "
            "https://arxiv.org/abs/2605.08587"),
    "deltanet": ("Yang, Wang, Zhang, Shen, Kim, Zettlemoyer (2024) Parallelizing Linear "
                 "Transformers with the Delta Rule over Sequence Length — arXiv:2406.06484 · "
                 "https://arxiv.org/abs/2406.06484"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | KACZMARZ_DELTA_RULE_SIM | NOT_LIVE | NO_MODEL | RESIDUAL_IS_MODELED"


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


def _matvec(S, k):
    """S (d x d) times k (d)."""
    d = len(k)
    return [sum(S[i][j] * k[j] for j in range(d)) for i in range(d)]


def _residual(v, Sk):
    return _math.sqrt(sum((v[i] - Sk[i]) ** 2 for i in range(len(v))))


def kla_update(seed: int = 42, seq_len: int = 64, d_state: int = 8,
               eta: float = 0.9, gate: float = 0.95, gdn_beta: float = 0.08) -> dict:
    """Kaczmarz linear-attention state-update snapshot (MODELED).

    seq_len  — T, (key,value) tokens streamed.
    d_state  — d, key/value dimension; the recurrent state S is d x d.
    eta      — Kaczmarz learning rate (numerator of the dynamic step size).
    gate     — decay gate a_t applied to the previous state each step.
    gdn_beta — the FIXED write coefficient of the GDN baseline (learned-but-static).
    seed     — RNG seed; identical inputs give identical output (deterministic).
    """
    T = max(2, min(2048, int(seq_len)))
    d = max(1, min(64, int(d_state)))
    eta = max(1e-3, min(10.0, float(eta)))
    a = max(0.5, min(0.999, float(gate)))
    gdn_beta = max(1e-3, min(1.0, float(gdn_beta)))
    eps = 1e-8
    rng = _LCG(int(seed) * 1_000_003 + T * 131 + d * 17)

    # Two independent states with identical init and identical (k,v) stream.
    S_kla = [[0.0] * d for _ in range(d)]
    S_gdn = [[0.0] * d for _ in range(d)]

    kla_res_sum = 0.0
    gdn_res_sum = 0.0
    beta_sum = 0.0

    for t in range(T):
        # keys have a spread of magnitudes -> ||k||^2 varies a lot, which is exactly where the
        # key-norm-normalized Kaczmarz step helps and a single fixed beta cannot fit all scales.
        scale = 0.4 + 1.6 * rng.uniform()
        k = [scale * rng.normal() for _ in range(d)]
        # value is a fixed linear map of k plus noise -> there IS a target to fit.
        v = [1.3 * k[i] + 0.1 * rng.normal() for i in range(d)]
        knorm2 = sum(x * x for x in k)

        # --- residual BEFORE this write (how well each state predicts v from k) ---
        kla_res_sum += _residual(v, _matvec(S_kla, k))
        gdn_res_sum += _residual(v, _matvec(S_gdn, k))

        # --- Kaczmarz step: beta = eta / (||k||^2 + eps) (key-norm-normalized) ---
        beta_kla = eta / (knorm2 + eps)
        beta_sum += beta_kla
        # delta = v - S_prev k  ; S <- a S + beta (v - S k) k^T
        Sk_kla = _matvec(S_kla, k)
        for i in range(d):
            delta_i = v[i] - Sk_kla[i]
            for j in range(d):
                S_kla[i][j] = a * S_kla[i][j] + beta_kla * delta_i * k[j]

        # --- GDN baseline: fixed beta ---
        Sk_gdn = _matvec(S_gdn, k)
        for i in range(d):
            delta_i = v[i] - Sk_gdn[i]
            for j in range(d):
                S_gdn[i][j] = a * S_gdn[i][j] + gdn_beta * delta_i * k[j]

    kla_residual = kla_res_sum / T
    gdn_residual = gdn_res_sum / T
    residual_reduction = (gdn_residual - kla_residual) / gdn_residual if gdn_residual > 0 else 0.0
    mean_beta = beta_sum / T

    return {
        "service": "kaczmarz-linear-attention-update",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/kla.js ---
        "seq_len": int(T),
        "d_state": int(d),
        "kla_residual": round(float(kla_residual), 6),
        "gdn_residual": round(float(gdn_residual), 6),
        "residual_reduction": round(float(residual_reduction), 6),
        "mean_beta": round(float(mean_beta), 6),
        "gate": float(a),
        "eta": float(eta),
        "formulas": {
            "state_update": "S_t = a S_{t-1} + beta_t (v_t - S_{t-1} k_t) k_t^T  (gated delta rule)",
            "kaczmarz_beta": "beta_t = eta / (||k_t||_2^2 + eps)  (key-norm-normalized step)",
            "gdn_beta": "beta_t = const  (fixed, learned-but-static baseline)",
            "residual_reduction": "(gdn_residual - kla_residual) / gdn_residual",
        },
        "compute_backend": {
            "backend": "CPU pure-Python gated delta-rule state-update simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic delta-rule sim; NO trained KLA/GDN, NO learned "
                            "projections, NO GPU, NO chunkwise kernel. A trained model is ROADMAP."),
        },
        "honest_note": ("MODELED Kaczmarz linear-attention update. residual_reduction is a "
                        "property of the modeled update rules on modeled data, not the paper's "
                        "perplexity number and not a benchmark claim about any real model."),
        "wired_into": "frontier ring — Kaczmarz / linear-attention (Kimi-style) update surface",
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (advisory residual metrics — never autonomous)",
        "citations": {"kla": CITATIONS["kla"], "deltanet": CITATIONS["deltanet"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/kla" % ns
    path = "%s/update" % base

    @app.get(path)
    async def _kc_kla(seed: int = 42, seq_len: int = 64, d_state: int = 8):  # noqa: ANN202
        try:
            return JSONResponse(kla_update(seed=seed, seq_len=seq_len, d_state=d_state))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "kaczmarz-linear-attention-update",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "kla_residual": None, "residual_reduction": None},
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
    r = kla_update(seed=42, seq_len=64, d_state=8)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "d_state"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("kla_residual", "gdn_residual", "residual_reduction", "mean_beta"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))

    # bounds: residuals positive; Kaczmarz key-norm-normalized step should fit at least as well
    # as the fixed-beta GDN baseline on this modeled stream (reduction >= 0).
    assert r["kla_residual"] > 0.0, r["kla_residual"]
    assert r["gdn_residual"] > 0.0, r["gdn_residual"]
    assert r["residual_reduction"] >= 0.0, r["residual_reduction"]
    assert r["mean_beta"] > 0.0, r["mean_beta"]
    out["metrics"] = {"kla_residual": r["kla_residual"], "gdn_residual": r["gdn_residual"],
                      "residual_reduction": r["residual_reduction"], "mean_beta": r["mean_beta"]}

    assert "2605.08587" in r["citations"]["kla"], r["citations"]

    # determinism
    r2 = kla_update(seed=42, seq_len=64, d_state=8)
    assert r2["kla_residual"] == r["kla_residual"], "non-deterministic"
    assert r2["residual_reduction"] == r["residual_reduction"], "non-deterministic"
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
