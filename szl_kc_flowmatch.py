# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_flowmatch.py — ADDITIVE Flow-Matching / Rectified-Flow straight-line ODE sampler for
killinchu's frontier surface (backs a11oy static/3d/surfaces/flowmatch.js).

Flow Matching (Lipman, Chen, Ben-Hamu, Nickel, Le 2023; arXiv:2210.02747) trains a Continuous
Normalizing Flow by regressing a velocity field v_theta(x,t) onto the velocity of a fixed
conditional probability path between noise x0 ~ N(0,I) and a data sample x1. With the
Optimal-Transport / linear interpolation path x_t = (1-t) x0 + t x1, the target velocity is the
CONSTANT straight-line displacement dx/dt = x1 - x0 (this is the "rectified flow" of Liu, Gong,
Liu 2022; arXiv:2209.03003). A straight path means an ODE solver needs very few Euler steps to
transport noise to data, so few-step sampling error is small.

This module simulates that sampler deterministically (seeded, NO trained network): for D
independent coordinates it draws x0 (noise) and x1 (target), integrates dx/dt = v = x1 - x0 with
plain forward-Euler over `steps` uniform substeps from t=0 to t=1, and measures the final
displacement error ||x_hat(1) - x1||. Because the true path is exactly linear, forward-Euler is
EXACT up to floating round-off for the straight OT path — the residual is the honest yardstick.
A straightness_score reports how close the (already straight) modeled path is to a perfect line;
steps_to_converge is the smallest step count reaching an error tolerance.

Reported (field names read verbatim by flowmatch.js):
  dims                — D, number of independent coordinates integrated
  steps_euler         — number of Euler substeps used for the headline solve
  final_error         — ||x_hat(1) - x1|| (MODELED) for steps_euler
  straightness_score  — 1 - normalized path-curvature (1.0 == perfectly straight)
  steps_to_converge   — smallest Euler step count with error <= tolerance
  few_step_error      — final_error at a small step budget (e.g. 1 step)
  many_step_error     — final_error at a large step budget (e.g. 128 steps)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic straight-line ODE integration. NOT a trained flow-matching / rectified-
    flow network; NO neural velocity field, NO GPU, NO learned weights. x0/x1 are SEEDED samples.
  * "final_error" is the numerical forward-Euler residual on the EXACT linear OT path — it is a
    property of the integrator + the modeled straight path, honestly labeled, not a sample-quality
    (FID/likelihood) claim about any real generative model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/flowmatch/sample — rectified-flow straight-line ODE sample snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from urllib.parse import urlparse as _urlparse
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "flow_matching": ("Lipman, Chen, Ben-Hamu, Nickel, Le (2023) Flow Matching for Generative "
                      "Modeling — arXiv:2210.02747 · https://arxiv.org/abs/2210.02747"),
    "rectified_flow": ("Liu, Gong, Liu (2022) Flow Straight and Fast: Learning to Generate and "
                       "Transfer Data with Rectified Flow — arXiv:2209.03003 · "
                       "https://arxiv.org/abs/2209.03003"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | RECTIFIED_FLOW_ODE_SIM | NOT_LIVE | NO_MODEL | STRAIGHT_LINE_PATH"


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
        # Box-Muller from two uniforms (deterministic, pure stdlib).
        u1 = max(1e-12, self.uniform())
        u2 = self.uniform()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _euler_solve(x0, x1, steps: int):
    """Forward-Euler integrate dx/dt = v = (x1 - x0) from t=0 (x=x0) to t=1.
    Returns x_hat(1). For the linear OT path the velocity is constant, so exact up to round-off."""
    D = len(x0)
    x = list(x0)
    dt = 1.0 / steps
    v = [x1[i] - x0[i] for i in range(D)]  # constant straight-line velocity (rectified flow)
    for _ in range(steps):
        for i in range(D):
            x[i] += dt * v[i]
    return x


def _l2(a, b) -> float:
    return _math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(len(a))))


def flowmatch_sample(seed: int = 42, dims: int = 8, steps: int = 16,
                     tol: float = 1e-6) -> dict:
    """Rectified-flow straight-line ODE sample snapshot (MODELED).

    dims  — D independent coordinates transported from noise x0 to target x1.
    steps — Euler substeps for the headline solve (steps_euler).
    tol   — convergence tolerance for steps_to_converge.
    seed  — RNG seed; identical inputs give identical output (deterministic).
    """
    D = max(1, min(256, int(dims)))
    steps_euler = max(1, min(4096, int(steps)))
    tol = max(1e-12, min(1.0, float(tol)))
    rng = _LCG(int(seed) * 1_000_003 + D * 131 + steps_euler * 17)

    x0 = [rng.normal() for _ in range(D)]          # noise sample x0 ~ N(0,I)
    x1 = [rng.normal() for _ in range(D)]          # target data sample x1

    # Headline solve.
    x_hat = _euler_solve(x0, x1, steps_euler)
    final_error = _l2(x_hat, x1)

    # Few-step (1 step) and many-step (128) error for the tab's convergence panel.
    few_steps = 1
    many_steps = 128
    few_step_error = _l2(_euler_solve(x0, x1, few_steps), x1)
    many_step_error = _l2(_euler_solve(x0, x1, many_steps), x1)

    # Straightness: on the linear OT path the sample path is exactly straight. We measure the
    # normalized deviation of the traversed polyline from the chord (x0 -> x1). For the modeled
    # straight path this deviation is ~round-off, so straightness_score ~ 1.0.
    chord = _l2(x0, x1)
    # traversed polyline length under Euler == sum of |v|*dt == |v| == chord for constant v.
    v = [x1[i] - x0[i] for i in range(D)]
    path_len = _math.sqrt(sum(vi * vi for vi in v))  # = chord for the straight path
    curvature = abs(path_len - chord) / chord if chord > 0 else 0.0
    straightness_score = max(0.0, 1.0 - curvature)

    # steps_to_converge: smallest step count with final error <= tol. On the exact straight path
    # even 1 Euler step lands (up to round-off), so scan from 1 upward.
    steps_to_converge = None
    for s in (1, 2, 4, 8, 16, 32, 64, 128):
        if _l2(_euler_solve(x0, x1, s), x1) <= tol:
            steps_to_converge = s
            break
    if steps_to_converge is None:
        steps_to_converge = many_steps

    # An error-vs-steps curve for the surface plot.
    error_curve = []
    for s in (1, 2, 4, 8, 16, 32, 64, 128):
        error_curve.append({"steps": s, "error": round(_l2(_euler_solve(x0, x1, s), x1), 12)})

    return {
        "service": "rectified-flow-ode-sampler",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/flowmatch.js ---
        "dims": int(D),
        "steps_euler": int(steps_euler),
        "final_error": round(float(final_error), 12),
        "straightness_score": round(float(straightness_score), 9),
        "steps_to_converge": int(steps_to_converge),
        "few_step_error": round(float(few_step_error), 12),
        "many_step_error": round(float(many_step_error), 12),
        "error_curve": error_curve,
        "chord_length": round(float(chord), 9),
        "path_length": round(float(path_len), 9),
        "formulas": {
            "velocity": "v = x1 - x0  (constant straight-line / rectified-flow velocity)",
            "path": "x_t = (1-t) x0 + t x1  (Optimal-Transport linear interpolation)",
            "euler_step": "x <- x + dt * v,  dt = 1/steps",
            "final_error": "||x_hat(1) - x1||_2",
            "straightness_score": "1 - |path_len - chord| / chord",
        },
        "compute_backend": {
            "backend": "CPU pure-Python forward-Euler ODE integration",
            "label": "MODELED",
            "honest_note": ("Deterministic straight-line ODE sim; NO trained velocity field, NO "
                            "GPU, NO learned weights. A trained flow-matching network is ROADMAP."),
        },
        "honest_note": ("MODELED rectified-flow straight-line ODE sampler. final_error is the "
                        "forward-Euler numerical residual on the exact linear OT path — not a "
                        "sample-quality (FID/likelihood) claim about any real generative model."),
        "wired_into": "frontier ring — Flow-Matching / Rectified-Flow surface",
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (advisory sampler — never an autonomous action)",
        "citations": {
            "flow_matching": CITATIONS["flow_matching"],
            "rectified_flow": CITATIONS["rectified_flow"],
        },
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/flowmatch" % ns
    path = "%s/sample" % base

    @app.get(path)
    async def _kc_flowmatch(seed: int = 42, dims: int = 8, steps: int = 16):  # noqa: ANN202
        try:
            return JSONResponse(flowmatch_sample(seed=seed, dims=dims, steps=steps))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "rectified-flow-ode-sampler",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "final_error": None, "straightness_score": None},
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
    r = flowmatch_sample(seed=42, dims=8, steps=16)

    # (a) honest label verbatim + every field the frontend reads is present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("dims", "steps_euler", "steps_to_converge"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("final_error", "straightness_score", "few_step_error", "many_step_error"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["error_curve"], list) and r["error_curve"], r

    # (b) sane bounds: straight OT path -> final error tiny, straightness ~ 1, few>=many-ish.
    assert 0.0 <= r["final_error"] < 1e-6, r["final_error"]
    assert 0.999 <= r["straightness_score"] <= 1.0, r["straightness_score"]
    assert r["few_step_error"] < 1e-6, r["few_step_error"]
    assert r["many_step_error"] < 1e-6, r["many_step_error"]
    assert 1 <= r["steps_to_converge"] <= 128, r["steps_to_converge"]
    out["metrics"] = {"dims": r["dims"], "steps_euler": r["steps_euler"],
                      "final_error": r["final_error"],
                      "straightness_score": r["straightness_score"],
                      "steps_to_converge": r["steps_to_converge"],
                      "few_step_error": r["few_step_error"],
                      "many_step_error": r["many_step_error"]}

    # (c) citations resolve to real arxiv ids, and the cited link's host is
    # exactly arxiv.org (parse-anchored; a bare substring test would also
    # accept attacker-shaped hosts such as arxiv.org.evil.example).
    cite = r["citations"]["flow_matching"]
    assert "2210.02747" in cite, r["citations"]
    cite_url = next((tok for tok in cite.split() if tok.startswith("https://")), "")
    assert _urlparse(cite_url).hostname == "arxiv.org", r["citations"]

    # (d) determinism: same inputs -> identical output.
    r2 = flowmatch_sample(seed=42, dims=8, steps=16)
    assert r2["final_error"] == r["final_error"], "non-deterministic"
    assert r2["error_curve"] == r["error_curve"], "non-deterministic curve"
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
