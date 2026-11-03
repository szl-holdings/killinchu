# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_testtime.py — SZL test-time-compute / reasoning-scaling-laws endpoint.

Exposes a MODELED closed-form model of the THIRD scaling axis — test-time
("inference-time") compute — alongside pretrain scaling and post-train
(RLHF/RL) scaling. This is a same-origin REST endpoint so the test-time-compute
surface organ has a live data source that is honest, deterministic, and
citable — never fabricated, never random-faked, no LLM calls.

  GET  /api/<ns>/v1/testtime/scaling?seed=&p=&N=&steps=

Modeled quantities
-------------------
  pass@N (best-of-N / repeated-sampling coverage):
      pass_at_N = 1 - (1 - p)^N
    where p is a per-sample success probability and N is the number of
    independent samples drawn (parallel test-time compute). This is the
    standard "coverage" curve used to characterize repeated sampling
    (Brown et al. 2024, "Large Language Monkeys", arXiv:2407.21787).

  Sequential revision curve (accuracy vs number of reasoning/revision steps,
  diminishing returns):
      revised_accuracy(k) = 1 - (1 - p) * exp(-alpha * k)
    a saturating exponential approach from the base accuracy p (k=0) toward
    1.0 as the number of sequential revision/reasoning steps k grows, with a
    per-step diminishing-returns rate alpha. This models the qualitative
    shape of sequential test-time revision / long chain-of-thought scaling
    reported for reasoning models (DeepSeek-AI et al. 2025, DeepSeek-R1,
    arXiv:2501.12948) and the sequential-vs-parallel test-time compute
    trade-off analyzed by Snell et al. 2024 (arXiv:2408.03314).

  Effective compute multiplier (log-scaling of inference compute vs accuracy
  gain):
      effective_oom_multiplier = log10(N) / scaling_exponent  (order-of-magnitude
        extra *inference* compute a given accuracy improvement is "worth")
      scaling_exponent = -ln(1 - p) (the per-sample exponential rate implied
        by the pass@N law itself: pass_at_N = 1 - exp(-scaling_exponent * N)
        for the Bernoulli/geometric coverage model)
    This mirrors the "optimal test-time compute" framing of Snell et al. 2024,
    who show additional inference compute can, on some problems, substitute
    for additional *pretraining* compute — i.e. there is an effective
    exchange rate between test-time FLOPs and accuracy, distinct from the
    pretrain scaling-law exchange rate (params/tokens) and the post-train
    scaling exchange rate (RL steps/preference data).

Returned JSON fields
---------------------
  label                     : "MODELED" (always — closed-form simulation, not a live model eval)
  model                     : short model-family name
  seed                      : RNG seed used (deterministic derivation of alpha jitter)
  base_accuracy             : p, the per-sample success probability (0..1)
  N_samples                 : N, number of independent samples (parallel test-time compute)
  pass_at_N                 : 1-(1-p)^N, the pass@N / best-of-N coverage curve value
  pass_at_N_curve           : [{n, pass_at_n}, ...] for a standard sweep of N (1,2,4,...,N)
  sequential_steps          : k, number of sequential reasoning/revision steps
  revision_alpha            : per-step diminishing-returns rate (deterministic from seed)
  revised_accuracy          : saturating-exponential accuracy at k steps
  revised_accuracy_curve    : [{k, revised_accuracy}, ...] for a sweep of steps 0..sequential_steps
  scaling_exponent          : -ln(1-p), implied per-sample exponential coverage rate
  effective_oom_multiplier  : log10(N) / scaling_exponent — orders-of-magnitude of test-time
                              compute "spent" to reach the current pass@N, holding p fixed
  third_axis_note           : plain-language framing of test-time compute as the third
                              scaling axis (alongside pretrain and post-train)
  honest_note               : plain-language honesty disclaimer
  citations                 : dict of citable sources
  computed_at               : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic closed-form model, NOT a live evaluation of any
  language model. pass@N follows the standard repeated-independent-Bernoulli-
  trials coverage identity; the sequential-revision curve and the effective
  compute multiplier are MODELED closed forms chosen to match the *qualitative
  shape* reported in the cited papers (diminishing returns; log-scaling of
  effective compute vs accuracy). No proprietary model logits, no benchmark
  re-runs, no LLM calls of any kind. The label "MODELED" is returned verbatim
  and displayed verbatim by the surface; it is never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  DeepSeek-R1 (reasoning via RL, long CoT / sequential test-time reasoning):
    DeepSeek-AI et al. (2025) "DeepSeek-R1: Incentivizing Reasoning Capability
    in LLMs via Reinforcement Learning". arXiv:2501.12948.
    https://arxiv.org/abs/2501.12948
  Optimal test-time compute allocation (parallel vs sequential):
    Snell, Lee, Xu & Kumar (2024) "Scaling LLM Test-Time Compute Optimally
    can be More Effective than Scaling Model Parameters". arXiv:2408.03314.
    https://arxiv.org/abs/2408.03314
  Repeated sampling / pass@N coverage law ("Large Language Monkeys"):
    Brown, Juravsky, Ehrlich, Clark, Le, Ré & Mirhoseini (2024) "Large
    Language Monkeys: Scaling Inference Compute with Repeated Sampling".
    arXiv:2407.21787. https://arxiv.org/abs/2407.21787
  HONEST-STUB note: the sequential-revision saturating-exponential form and
  the effective-compute-multiplier definition are SZL's own closed-form
  MODELED choices, selected to reproduce the qualitative diminishing-returns
  and log-scaling shapes reported in the cited literature. They are not a
  re-implementation of any paper's exact fitted curve or reported numbers.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  No LLM calls of any kind — pure closed-form arithmetic.
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
    "DeepSeek-R1 — DeepSeek-AI et al. 2025, arXiv:2501.12948": "https://arxiv.org/abs/2501.12948",
    "Scaling LLM Test-Time Compute Optimally — Snell et al. 2024, arXiv:2408.03314": "https://arxiv.org/abs/2408.03314",
    "Large Language Monkeys (repeated sampling) — Brown et al. 2024, arXiv:2407.21787": "https://arxiv.org/abs/2407.21787",
}

# Standard N sweep for the pass@N curve (coverage across orders of magnitude
# of parallel test-time compute), capped by the requested N.
_N_SWEEP = [1, 2, 4, 8, 16, 32, 64, 128, 256]


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy/random) — used only to derive
# a small, reproducible per-seed jitter on the diminishing-returns rate alpha,
# so different seeds produce slightly different (but deterministic) revision
# curves. The pass@N law itself is exact closed-form and seed-independent.
# ---------------------------------------------------------------------------
_LCG_A = 1103515245
_LCG_C = 12345
_LCG_M = 2 ** 31


def _lcg_stream(seed: int, n: int):
    """Deterministic LCG stream of n floats in [0,1). Pure stdlib, no random module."""
    x = seed % _LCG_M
    out = []
    for _ in range(n):
        x = (_LCG_A * x + _LCG_C) % _LCG_M
        out.append(x / _LCG_M)
    return out


# ---------------------------------------------------------------------------
# Closed-form models
# ---------------------------------------------------------------------------
def _pass_at_n(p: float, n: int) -> float:
    """pass@N coverage: 1-(1-p)^N. Brown et al. 2024 (arXiv:2407.21787)."""
    p = min(max(p, 0.0), 1.0)
    return 1.0 - (1.0 - p) ** n


def _scaling_exponent(p: float) -> float:
    """Implied per-sample exponential coverage rate: -ln(1-p).

    Rewriting pass@N = 1-(1-p)^N = 1-exp(N*ln(1-p)) = 1-exp(-scaling_exponent*N)
    with scaling_exponent = -ln(1-p) >= 0. Larger p => larger exponent => faster
    coverage growth per additional sample.
    """
    p = min(max(p, 0.0), 1.0 - 1e-12)
    return -math.log(1.0 - p)


def _effective_oom_multiplier(n: int, exponent: float) -> float:
    """Orders-of-magnitude of test-time (inference) compute 'spent' to reach
    the current N, normalized by the per-sample scaling exponent. This is a
    MODELED analogue of an "effective compute multiplier": how many decades
    of extra sampling compute are being traded for the coverage gain, given
    how quickly (exponent) each additional sample closes the coverage gap.
    """
    if exponent <= 0:
        return 0.0
    return round(math.log10(max(n, 1)) / exponent, 6) if n > 1 else 0.0


def _revision_alpha(seed: int, base_alpha: float = 0.35) -> float:
    """Deterministic per-step diminishing-returns rate, seed-jittered by a
    small +/-15% band via the LCG stream so the curve is reproducible but
    not identical across seeds."""
    jitter = _lcg_stream(seed, 1)[0]  # in [0,1)
    factor = 0.85 + 0.30 * jitter     # in [0.85, 1.15)
    return round(base_alpha * factor, 6)


def _revised_accuracy(p: float, k: int, alpha: float) -> float:
    """Saturating-exponential sequential-revision curve:
        revised_accuracy(k) = 1 - (1-p) * exp(-alpha*k)
    k=0 recovers the base accuracy p; as k -> infinity, accuracy -> 1.0 with
    diminishing per-step returns (rate alpha). MODELED shape chosen to match
    the qualitative diminishing-returns behaviour reported for sequential
    test-time revision (Snell et al. 2024, arXiv:2408.03314; DeepSeek-R1
    long-CoT reasoning, arXiv:2501.12948).
    """
    p = min(max(p, 0.0), 1.0)
    return 1.0 - (1.0 - p) * math.exp(-alpha * k)


def _testtime_model(seed: int = 42, p: float = 0.2, N: int = 16, steps: int = 8) -> dict:
    p = min(max(p, 1e-6), 1.0 - 1e-9)
    N = max(1, min(int(N), 100000))
    steps = max(0, min(int(steps), 1000))

    exponent = _scaling_exponent(p)
    alpha = _revision_alpha(seed)

    pass_at_N = round(_pass_at_n(p, N), 8)
    n_sweep = sorted(set(_N_SWEEP + [N]))
    n_sweep = [n for n in n_sweep if n <= max(N, _N_SWEEP[-1])]
    pass_at_N_curve = [
        {"n": n, "pass_at_n": round(_pass_at_n(p, n), 8)} for n in n_sweep
    ]

    revised_accuracy = round(_revised_accuracy(p, steps, alpha), 8)
    step_sweep = sorted(set(list(range(0, steps + 1, max(1, steps // 8 or 1))) + [steps]))
    revised_accuracy_curve = [
        {"k": k, "revised_accuracy": round(_revised_accuracy(p, k, alpha), 8)}
        for k in step_sweep
    ]

    effective_oom_multiplier = _effective_oom_multiplier(N, exponent)

    return {
        "base_accuracy": round(p, 6),
        "N_samples": N,
        "pass_at_N": pass_at_N,
        "pass_at_N_curve": pass_at_N_curve,
        "sequential_steps": steps,
        "revision_alpha": alpha,
        "revised_accuracy": revised_accuracy,
        "revised_accuracy_curve": revised_accuracy_curve,
        "scaling_exponent": round(exponent, 8),
        "effective_oom_multiplier": effective_oom_multiplier,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _fi(req: Request, key: str, default) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return float(default)


def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_scaling(req: Request):
    seed  = _ii(req, "seed", 42)
    p     = max(1e-6, min(_fi(req, "p", 0.2), 1.0 - 1e-9))
    N     = max(1, min(_ii(req, "N", 16), 100000))
    steps = max(0, min(_ii(req, "steps", 8), 1000))

    m = _testtime_model(seed=seed, p=p, N=N, steps=steps)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Closed-form test-time-compute scaling: pass@N coverage + sequential revision + effective compute multiplier",
        "equation_pass_at_N": "pass@N = 1 - (1-p)^N  (Brown et al. 2024, arXiv:2407.21787)",
        "equation_revision":  "revised_accuracy(k) = 1 - (1-p)*exp(-alpha*k)  (MODELED saturating exponential; qualitative shape per Snell et al. 2024 arXiv:2408.03314 / DeepSeek-R1 arXiv:2501.12948)",
        "equation_scaling_exponent": "scaling_exponent = -ln(1-p)  (implied per-sample exponential coverage rate)",
        "equation_effective_oom": "effective_oom_multiplier = log10(N) / scaling_exponent  (MODELED; orders-of-magnitude of test-time compute vs accuracy)",
        "seed": seed,
        **m,
        "third_axis_note": (
            "Test-time (inference-time) compute is modeled here as the THIRD scaling axis "
            "for LLM capability, alongside (1) pretrain scaling (params x tokens) and "
            "(2) post-train scaling (RL/preference-optimization steps and data). Spending "
            "more compute at inference time -- via parallel repeated sampling (pass@N / "
            "best-of-N) or sequential reasoning/revision (more chain-of-thought steps) -- "
            "can trade off against pretrain/post-train compute on some tasks (Snell et al. "
            "2024, arXiv:2408.03314)."
        ),
        "honest_note": (
            "MODELED: this is a closed-form scaling-law simulation, not a live model "
            "evaluation. pass@N follows the exact repeated-independent-trials coverage "
            "identity (Brown et al. 2024, 'Large Language Monkeys', arXiv:2407.21787). "
            "The sequential-revision curve and effective-compute-multiplier are SZL's own "
            "MODELED closed forms chosen to reproduce the qualitative diminishing-returns "
            "and log-scaling shapes discussed by Snell et al. 2024 (arXiv:2408.03314) and "
            "DeepSeek-R1 (DeepSeek-AI et al. 2025, arXiv:2501.12948). No LLM calls, no "
            "benchmark re-runs, no proprietary model data. Deterministic: same "
            "seed/p/N/steps -> identical output. SZL claims NONE of these methods as its "
            "own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_neuromorphic.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/testtime/scaling onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/testtime"
    handlers = [
        (f"{base}/scaling", _h_scaling),
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
    print("equation_pass_at_N: pass@N = 1 - (1-p)^N  (Brown et al. 2024, arXiv:2407.21787)")
    print()
    p_demo = 0.2
    print(f"pass@N rising for p={p_demo}, N=1,4,16,64:")
    for n in (1, 4, 16, 64):
        m = _testtime_model(seed=42, p=p_demo, N=n, steps=8)
        print(f"  N={n:>3}  pass_at_N={m['pass_at_N']:.8f}")

    print()
    m8 = _testtime_model(seed=42, p=p_demo, N=64, steps=8)
    print("scaling_exponent:", m8["scaling_exponent"])
    print("effective_oom_multiplier (N=64):", m8["effective_oom_multiplier"])
    print("revision_alpha (seed=42):", m8["revision_alpha"])
    print("revised_accuracy_curve:")
    for row in m8["revised_accuracy_curve"]:
        print(f"  k={row['k']:>2}  revised_accuracy={row['revised_accuracy']:.8f}")

    # sanity: pass@N must be monotonically non-decreasing in N
    vals = [_testtime_model(seed=42, p=p_demo, N=n, steps=8)["pass_at_N"] for n in (1, 4, 16, 64)]
    assert vals == sorted(vals), f"pass@N not monotonically rising: {vals}"
    # sanity: revised_accuracy must be monotonically non-decreasing in k
    racc = [row["revised_accuracy"] for row in m8["revised_accuracy_curve"]]
    assert racc == sorted(racc), f"revised_accuracy not monotonically rising: {racc}"

    print()
    print("szl_testtime: ALL OK — pass@N and revised_accuracy both rise monotonically.")
