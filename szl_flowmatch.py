# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_flowmatch.py — SZL rectified-flow / flow-matching ODE-sampler endpoint.

Exposes a MODELED deterministic rectified-flow generative sampler: integrate the
probability-flow ODE dx/dt = v(x,t) from a noise sample x0 ~ N(0,I) to a target
point x1, using a straight-line ("rectified") velocity field v = x1 - x0, via
`steps` explicit Euler steps over t in [0,1]. This is the closed-form illustration
of the central rectified-flow result: because the straight-line coupling makes the
ODE trajectory itself a straight line, a SINGLE Euler step already lands exactly on
x1 (up to floating-point error) — i.e. rectified flow needs few integration steps,
unlike a curved/learned flow or a diffusion SDE which needs many. This gives the
flow-matching/rectified-flow surface organ a live data source that is honest,
deterministic, and citable — never fabricated, never a trained model.

  GET  /api/<ns>/v1/flowmatch/sample?seed=&steps=&dims=

Method (all closed-form / deterministic from seed)
----------------------------------------------------
  x0 ~ N(0,I)_dims        : noise draw, pure-stdlib Box-Muller over an LCG stream
  x1                      : target point, pure-stdlib deterministic draw (seed-derived)
  v(x,t) = x1 - x0        : constant straight-line velocity field (rectified flow;
                            Liu et al. 2022, arXiv:2209.03003). This is the exact
                            vector field of the linear interpolant x_t = (1-t)x0 + t*x1
                            used by Lipman et al.'s Conditional Flow Matching objective
                            (arXiv:2210.02747) in the special case of a single
                            (x0, x1) pair with a straight-line (OT) probability path.
  dx/dt = v(x,t)          : the flow ODE, integrated forward from t=0 to t=1 with
                            `steps` explicit-Euler steps of size dt = 1/steps.
  trajectory              : the list of intermediate points x_t at each step (small
                            dims, 3..8, kept short for the surface to render as a
                            path in 3D)
  final_error             : L2 distance from the ODE's final point to the true
                            target x1 (should be ~0 for the analytic straight-line
                            case, regardless of step count — the rectified-flow win)
  straightness_score      : 1 - (path length actually travelled) / (straight-line
                            distance |x1-x0|); 1.0 means perfectly straight (the
                            rectified-flow ideal), lower means curved/wasteful path.
                            For this analytic case the path IS the straight line, so
                            straightness_score is always ~1.0 by construction.
  steps_to_converge       : smallest step count (from a fixed probe ladder) whose
                            final_error first drops below a small convergence
                            tolerance — MODELED demonstration that rectified flow
                            converges in very few steps, unlike curved paths that
                            need many small steps to avoid discretization error.
  few_vs_many             : {few_step_error, many_step_error} — final_error at a
                            small step count vs a large one, to show BOTH already
                            converge (the rectified-flow win: no incremental benefit
                            from many steps because the field is exactly constant
                            along the path, so Euler integration is exact for any
                            steps >= 1, up to floating-point noise).

Returned JSON fields
---------------------
  label                : "MODELED" (always — a toy analytic ODE, not a trained model)
  model                 : short description
  dims                  : dimensionality of the toy noise/target vectors
  steps                 : number of Euler steps requested
  x0, x1                : the noise draw and target point (dims-length lists)
  trajectory            : [{t, x}, ...] intermediate points (t in [0,1])
  final_error           : L2(x_T, x1) at the requested step count
  straightness_score    : 1 - path_length/straight_line_length (rectified-flow win)
  steps_to_converge     : smallest probed step count with final_error < tol
  few_vs_many           : {few_step_error, many_step_error, few_steps, many_steps}
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form, pure-stdlib simulation of the rectified-flow
  ODE-sampling METHOD on a toy noise -> single-target-point case with an EXACTLY
  straight-line (analytic) velocity field. It is NOT a trained flow-matching or
  diffusion model, uses NO learned weights, and generates NO images/audio/video.
  NEVER claimed as FLUX, Stable Diffusion 3, or any other production flow-matching
  model — those are cited below purely as the real systems that popularized this
  METHOD family; SZL claims none of their weights or results as its own. The label
  "MODELED" is returned verbatim and displayed verbatim by the surface; it is never
  upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Flow Matching for Generative Modeling:
    Lipman, Chen, Ben-Hamu, Nickel & Le (2022) "Flow Matching for Generative
    Modeling". arXiv:2210.02747. https://arxiv.org/abs/2210.02747
  Rectified Flow (straight-line couplings, "Flow Straight and Fast"):
    Liu, Gong & Liu (2022) "Flow Straight and Fast: Learning to Generate and
    Transfer Data with Rectified Flow". arXiv:2209.03003.
    https://arxiv.org/abs/2209.03003
  FLUX (production rectified-flow / flow-matching text-to-image transformer,
  NEVER claimed as SZL's own; cited only as the real system that demonstrates this
  METHOD family at scale):
    Black Forest Labs, FLUX. https://github.com/black-forest-labs/flux

DOCTRINE v11: NOTHING here is in the locked-8. Λ stays Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (no numpy). Deterministic with seed. 0 runtime CDN.
  NEVER-CLAIMED-AS FLUX / Stable Diffusion 3 / any trained flow-matching model.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "Flow Matching for Generative Modeling — Lipman et al. arXiv:2210.02747": "https://arxiv.org/abs/2210.02747",
    "Rectified Flow — Liu et al. arXiv:2209.03003": "https://arxiv.org/abs/2209.03003",
    "FLUX (Black Forest Labs, production rectified-flow model — NOT claimed as SZL's own)": "https://github.com/black-forest-labs/flux",
}

# Convergence tolerance for steps_to_converge probing, and the probe ladder itself.
_CONVERGE_TOL = 1e-9
_PROBE_STEPS = [1, 2, 4, 8, 16, 32, 64, 128]


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy/random) — reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _gauss_stream(seed: int):
    """Deterministic standard-normal stream via Box-Muller over the LCG uniform
    stream. Pure stdlib (math.log/cos/sqrt only) — no numpy, no random module."""
    rng = _lcg(seed)
    while True:
        u1 = max(next(rng), 1e-12)   # avoid log(0)
        u2 = next(rng)
        r = math.sqrt(-2.0 * math.log(u1))
        theta = 2.0 * math.pi * u2
        yield r * math.cos(theta)
        yield r * math.sin(theta)


# ---------------------------------------------------------------------------
# Small pure-stdlib vector ops (no numpy)
# ---------------------------------------------------------------------------
def _vsub(a, b):
    return [ai - bi for ai, bi in zip(a, b)]


def _vadd(a, b):
    return [ai + bi for ai, bi in zip(a, b)]


def _vscale(a, s):
    return [ai * s for ai in a]


def _vnorm(a):
    return math.sqrt(sum(ai * ai for ai in a))


def _vdist(a, b):
    return _vnorm(_vsub(a, b))


# ---------------------------------------------------------------------------
# MODELED rectified-flow ODE sampler (deterministic)
# ---------------------------------------------------------------------------
def _draw_noise_and_target(seed: int, dims: int):
    """Deterministically draw x0 ~ N(0,I)_dims and a target point x1 from two
    independent derived seeds (so x0 and x1 are not trivially correlated)."""
    g0 = _gauss_stream(seed)
    x0 = [next(g0) for _ in range(dims)]
    g1 = _gauss_stream((int(seed) ^ 0xA5A5A5A5) & 0xFFFFFFFF)
    # Target drawn with a small deterministic offset+scale so it is a distinct
    # point in space, not degenerate with the noise sample.
    x1 = [2.5 + next(g1) for _ in range(dims)]
    return x0, x1


def _integrate_rectified_flow(x0, x1, steps: int):
    """Integrate dx/dt = v(x,t) = x1 - x0 (constant straight-line velocity field;
    Liu et al. 2022, arXiv:2209.03003) from t=0 to t=1 with `steps` explicit-Euler
    steps. Because v is CONSTANT along the true path (independent of x and t for
    the rectified/straight-line coupling), Euler integration is exact for any
    steps >= 1 up to floating-point rounding — this is the rectified-flow win:
    few steps already converge, unlike a curved/learned vector field where Euler
    error accumulates and shrinks only as steps grows (O(1/steps) global error).

    Returns (trajectory, x_final, path_length) where trajectory is a list of
    {"t": t, "x": point} dicts including both endpoints.
    """
    steps = max(1, int(steps))
    dt = 1.0 / steps
    v = _vsub(x1, x0)  # constant straight-line velocity field

    x = list(x0)
    trajectory = [{"t": 0.0, "x": [round(c, 8) for c in x]}]
    path_length = 0.0
    for i in range(1, steps + 1):
        x_next = _vadd(x, _vscale(v, dt))
        path_length += _vdist(x_next, x)
        x = x_next
        t = i * dt
        trajectory.append({"t": round(t, 8), "x": [round(c, 8) for c in x]})

    return trajectory, x, path_length


def _straightness_score(x0, x1, path_length: float) -> float:
    """1 - (travelled path length) / (straight-line distance). 1.0 = perfectly
    straight (the rectified-flow ideal: MSE-optimal transport paths do not cross
    and approach straight lines after 'reflow', Liu et al. 2022). Clamped to
    [0,1] to stay a well-behaved score even under floating-point noise."""
    straight = _vdist(x0, x1)
    if straight < 1e-12:
        return 1.0
    score = 1.0 - (path_length / straight - 1.0)
    return max(0.0, min(1.0, score))


def _steps_to_converge(x0, x1) -> int:
    """Smallest step count in the probe ladder whose final_error first drops
    below _CONVERGE_TOL. For the exact straight-line rectified-flow field this
    is expected to be the smallest probed value (1 step) — the headline
    rectified-flow result: convergence does not require many steps."""
    for s in _PROBE_STEPS:
        _, x_final, _ = _integrate_rectified_flow(x0, x1, s)
        if _vdist(x_final, x1) < _CONVERGE_TOL:
            return s
    return _PROBE_STEPS[-1]


def _flowmatch_sample(seed: int = 42, steps: int = 8, dims: int = 3) -> dict:
    dims = max(2, min(int(dims), 8))
    steps = max(1, min(int(steps), 512))

    x0, x1 = _draw_noise_and_target(seed, dims)
    trajectory, x_final, path_length = _integrate_rectified_flow(x0, x1, steps)
    final_error = _vdist(x_final, x1)
    straightness = _straightness_score(x0, x1, path_length)
    conv_steps = _steps_to_converge(x0, x1)

    few_steps = min(_PROBE_STEPS)          # 1 step — deliberately "few"
    many_steps = max(_PROBE_STEPS)         # 128 steps — deliberately "many"
    _, x_few, _ = _integrate_rectified_flow(x0, x1, few_steps)
    _, x_many, _ = _integrate_rectified_flow(x0, x1, many_steps)
    few_step_error = _vdist(x_few, x1)
    many_step_error = _vdist(x_many, x1)

    return {
        "dims": dims,
        "steps": steps,
        "x0": [round(c, 8) for c in x0],
        "x1": [round(c, 8) for c in x1],
        "trajectory": trajectory,
        "final_error": round(final_error, 12),
        "straightness_score": round(straightness, 8),
        "steps_to_converge": conv_steps,
        "few_vs_many": {
            "few_steps": few_steps,
            "few_step_error": round(few_step_error, 12),
            "many_steps": many_steps,
            "many_step_error": round(many_step_error, 12),
        },
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_sample(req: Request):
    seed  = _ii(req, "seed",  42)
    steps = max(1, min(_ii(req, "steps", 8), 512))
    dims  = max(2, min(_ii(req, "dims", 3), 8))

    m = _flowmatch_sample(seed=seed, steps=steps, dims=dims)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Rectified-flow ODE sampler: analytic straight-line velocity field, explicit-Euler integration",
        "method": "dx/dt = v(x,t) = x1 - x0 (constant straight-line field); Euler integration, t in [0,1]",
        "seed":   seed,
        **m,
        "honest_note": (
            "MODELED: this is a deterministic, closed-form, pure-stdlib simulation of the "
            "rectified-flow ODE-SAMPLING METHOD on a toy noise -> single-target-point case "
            "with an EXACTLY straight-line (analytic) velocity field v = x1 - x0. It is NOT "
            "a trained flow-matching or diffusion model, uses NO learned weights, and "
            "generates NO images, audio, or video. Because the field is exactly constant "
            "along the true path, explicit-Euler integration is exact for ANY step count "
            ">= 1 (up to floating-point rounding) -- this reproduces the headline "
            "rectified-flow result that few integration steps already converge, unlike a "
            "curved/learned vector field or a diffusion SDE which needs many small steps. "
            "Deterministic: same seed/steps/dims -> identical output. Cite: Lipman et al. "
            "arXiv:2210.02747 (Flow Matching); Liu et al. arXiv:2209.03003 (Rectified Flow); "
            "Black Forest Labs FLUX github.com/black-forest-labs/flux (real production "
            "rectified-flow system, cited only -- NEVER claimed as SZL's own; this endpoint "
            "is NOT FLUX and NOT Stable Diffusion 3). SZL claims NONE of these methods as "
            "its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_testtime.register() / szl_interpretability.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/flowmatch/sample onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/flowmatch"
    handlers = [
        (f"{base}/sample", _h_sample),
    ]
    add_api_route = getattr(app, "add_api_route", None)
    for path, fn in handlers:
        if callable(add_api_route):
            app.add_api_route(path, fn, methods=["GET"])
        else:
            app.router.routes.append(Route(path, fn))
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    print("label: MODELED")
    print("method: dx/dt = v(x,t) = x1 - x0 (rectified/straight-line field); Euler integration")
    print()

    m = _flowmatch_sample(seed=42, steps=8, dims=3)
    print(f"dims={m['dims']}  steps={m['steps']}")
    print("x0:", m["x0"])
    print("x1:", m["x1"])
    print("final_error:", m["final_error"])
    print("straightness_score:", m["straightness_score"])
    print("steps_to_converge:", m["steps_to_converge"])
    print()

    fvm = m["few_vs_many"]
    print(f"few-step  (steps={fvm['few_steps']:>3}) final_error = {fvm['few_step_error']:.12f}")
    print(f"many-step (steps={fvm['many_steps']:>3}) final_error = {fvm['many_step_error']:.12f}")
    print()

    # sanity: rectified flow win — both few-step and many-step should already
    # be converged (near-zero error), since the field is exactly constant.
    assert fvm["few_step_error"] < 1e-6, f"few-step error too large: {fvm['few_step_error']}"
    assert fvm["many_step_error"] < 1e-6, f"many-step error too large: {fvm['many_step_error']}"
    # sanity: straightness_score should be ~1.0 (perfectly straight path)
    assert m["straightness_score"] > 0.999, f"straightness_score too low: {m['straightness_score']}"
    # sanity: steps_to_converge should be the smallest probed value (1)
    assert m["steps_to_converge"] == 1, f"steps_to_converge unexpectedly high: {m['steps_to_converge']}"
    # sanity: trajectory must start at x0 and end at x1 (within final_error)
    assert m["trajectory"][0]["x"] == m["x0"], "trajectory does not start at x0"
    assert _vdist(m["trajectory"][-1]["x"], m["x1"]) < 1e-6, "trajectory does not end at x1"

    print("szl_flowmatch: ALL OK — few-step and many-step both converge (rectified-flow win);")
    print("               straightness_score ~1.0; steps_to_converge == 1.")
