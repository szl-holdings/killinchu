# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_opera.py — SZL OPERA (PERPLEXITY-REWARD REFLECTIVE ALIGNMENT) endpoint, MODELED.

Exposes a MODELED, deterministic, pure-stdlib re-implementation of the OPERA
intrinsic-reward MECHANISM (Wenxuan Jiang et al., "OPERA: Aligning Open-Ended
Reasoning via Objective Perplexity-based Reinforcement Learning",
arXiv:2606.25757, 2026-06-24) applied to small SYNTHETIC reasoning traces drawn
from the pure-stdlib LCG PRNG below — so the opera organ has a live data source
that is honest, deterministic, and citable — never a trained model, never a real
LLM forward pass, never a GPU rollout.

  GET  /api/<ns>/v1/opera/reward?seed=&traces=&steps=

WHAT IS MODELED
---------------
OPERA replaces an unreliable EXTERNAL LLM-as-a-judge reward (which the paper
notes suffers from STYLISTIC BIASES and POSITIONAL INCONSISTENCIES) with an
INTRINSIC reward derived from PERPLEXITY DYNAMICS — the uncertainty reduction
(perplexity drop) at CRITICAL REFLECTIVE STATES within a reasoning trace.

This module simulates `traces` toy reasoning traces, each a length-`steps`
sequence of per-step token LOG-PROBABILITIES. For step t, the running
perplexity proxy is

    ppl_t = exp( -mean(logprob_0 .. logprob_t) )      (lower = more certain)

Each trace carries a HIDDEN GROUND-TRUTH logical-consistency label in {0,1}.
A LOGICALLY-CONSISTENT trace genuinely resolves uncertainty: at its reflective
steps (a fixed subset of positions), the model becomes MORE confident, so
perplexity DROPS (Δppl = ppl_before − ppl_after > 0). An INCONSISTENT trace does
not resolve uncertainty at reflective steps — its perplexity drifts / rises.

Two reward signals are computed per trace and compared against that label:

  OPERA INTRINSIC REWARD (what the paper proposes):
      opera_r = sum over reflective steps of max(0, Δppl_at_step)
    i.e. total uncertainty reduction accrued at reflective states. Because the
    label is DEFINED by whether reflective steps resolve uncertainty, this
    intrinsic signal tracks the label tightly.

  SIMULATED BIASED-JUDGE REWARD (the unreliable baseline the paper replaces):
      judge_r = w_c*consistency + w_s*style_noise + w_p*position_noise
    a weak consistency term swamped by STYLISTIC noise (per-trace verbosity /
    formatting quirk) and POSITIONAL noise (an order/length artifact) — so it is
    high-variance and only loosely coupled to the true label.

The module then MEASURES, across all traces, the Pearson correlation of each
reward with the ground-truth consistency label, and the VARIANCE of the judge
reward (a stability proxy — higher = more unstable supervision). The headline
finding reproduced in miniature: OPERA's intrinsic reward CORRELATES with logical
consistency (correlation_opera high) while the noisy judge does NOT
(correlation_judge low, judge_reward_variance high).

Returned JSON fields
--------------------
  label                    : "MODELED" (always — clean-room mechanism, NOT a
                             trained model / real RL rollout)
  model                    : short description of the modeled setup
  method                   : one-line description of the two reward signals
  seed                     : RNG seed used
  traces, steps            : number of toy traces, steps per trace
  reflective_steps         : the reflective-state positions used per trace
  opera_reward             : MEASURED mean OPERA intrinsic reward across traces
  opera_reward_variance    : MEASURED variance of the OPERA reward (stability)
  judge_reward             : MEASURED mean biased-judge reward across traces
  judge_reward_variance    : MEASURED variance of the judge reward (higher=unstable)
  correlation_opera        : MEASURED Pearson corr(OPERA reward, consistency label)
  correlation_judge        : MEASURED Pearson corr(judge reward, consistency label)
  consistency_rate         : fraction of traces with ground-truth label == 1
  per_trace                : head sample of per-trace {label, ppl_first, ppl_last,
                             opera_r, judge_r}
  ppl_curves_head          : head sample of per-step perplexity curves
  honest_note              : plain-language honesty disclaimer (see below)
  citations                : dict of citable sources (verified real)
  computed_at              : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib TOY demo of the OPERA intrinsic-reward
  MECHANISM (perplexity-drop reward at reflective states vs a noisy LLM-judge
  reward). No numpy, no stdlib `random`, no trained model, no real LLM forward
  pass, no RL optimization, no GPU rollout. The perplexity curves, both reward
  signals, their variances, and the correlations with the synthetic
  consistency label are all MEASURED on the synthetic traces. It does NOT
  reproduce OPERA's Qwen3-8B SOTA results, its parity with
  Gemini2.5 / MiniMax-M2.5, or its 20,000-trajectory cold-start dataset — those
  are CLAIMS about REAL trained models and pipelines the estate does NOT
  independently verify. This organ is DISTINCT from the grpo organ: grpo models
  GROUP-RELATIVE POLICY OPTIMIZATION reward dynamics, whereas OPERA here is an
  INTRINSIC PERPLEXITY reward — not group-relative advantage estimation. The
  label "MODELED" is returned verbatim and displayed verbatim by the surface;
  never upgraded.

CITATIONS (clean-room; none claimed as SZL's own; VERIFIED real):
  OPERA: Aligning Open-Ended Reasoning via Objective Perplexity-based
    Reinforcement Learning — Wenxuan Jiang, Zining Fan, Zijian Zhang,
    Xuecheng Wu, Hongming Tan, Haoyang Dai, Xiaoyu Li, Xuezhi Cao, Ninghao Liu.
    arXiv:2606.25757
    https://arxiv.org/abs/2606.25757
  NEVER-CLAIMED-AS: this module is not the paper's released code, does not
  reproduce its SOTA / dataset numbers, trains no model, and runs no real RL.
  It is a clean-room MODELED reproduction of the perplexity-reward MECHANISM.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
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
    "OPERA: Aligning Open-Ended Reasoning via Objective Perplexity-based Reinforcement Learning — Wenxuan Jiang et al. arXiv:2606.25757": "https://arxiv.org/abs/2606.25757",
}


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _gauss(rng) -> float:
    """Box-Muller Gaussian-ish draw from two uniform LCG samples (pure stdlib)."""
    u1 = next(rng)
    u2 = next(rng)
    if u1 < 1e-12:
        u1 = 1e-12
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


# ---------------------------------------------------------------------------
# Tiny pure-stdlib statistics (NO numpy)
# ---------------------------------------------------------------------------
def _mean(xs) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _variance(xs) -> float:
    """Population variance (pure stdlib)."""
    if not xs:
        return 0.0
    mu = _mean(xs)
    return sum((x - mu) * (x - mu) for x in xs) / len(xs)


def _pearson(xs, ys) -> float:
    """Pearson correlation coefficient, guarded against zero variance."""
    n = len(xs)
    if n == 0 or n != len(ys):
        return 0.0
    mx = _mean(xs)
    my = _mean(ys)
    sxy = 0.0
    sxx = 0.0
    syy = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        sxy += dx * dy
        sxx += dx * dx
        syy += dy * dy
    if sxx <= 0.0 or syy <= 0.0:
        return 0.0
    return sxy / (math.sqrt(sxx) * math.sqrt(syy))


# ---------------------------------------------------------------------------
# Trace synthesis + reward computation (the EXACT mechanism, on toy traces)
# ---------------------------------------------------------------------------
def _reflective_positions(steps: int):
    """Fixed reflective-state positions within a length-`steps` trace: the
    interior thirds where a reasoner is most likely to reconsider (never step 0,
    since Δppl needs a predecessor)."""
    if steps < 3:
        return [max(1, steps - 1)]
    a = max(1, steps // 3)
    b = max(a + 1, (2 * steps) // 3)
    c = max(b + 1, steps - 2)
    return sorted(set(p for p in (a, b, c) if 1 <= p < steps))


def _build_trace(rng, steps: int, consistent: bool, reflective):
    """
    Build one toy reasoning trace as a sequence of per-step token log-probs, and
    the running perplexity proxy ppl_t = exp(-mean(logprob_0..t)).

    A CONSISTENT trace resolves uncertainty AT reflective steps: the step's
    log-prob jumps UP (more confident) so the running perplexity DROPS. An
    INCONSISTENT trace does not — reflective steps drift toward LOWER confidence,
    so perplexity does not drop (or rises).

    Returns (logprobs, ppl_curve).
    """
    reflect = set(reflective)
    # baseline per-step log-prob: mildly negative with small Gaussian jitter
    logprobs = []
    for t in range(steps):
        base = -1.4 + 0.10 * _gauss(rng)     # typical token log-prob ~ -1.4 nats
        if t in reflect:
            if consistent:
                # genuine uncertainty reduction: confidence rises at reflection
                base += 0.85 + 0.15 * abs(_gauss(rng))
            else:
                # failed reflection: confidence falls (perplexity drifts up)
                base -= 0.55 + 0.15 * abs(_gauss(rng))
        logprobs.append(base)

    # running perplexity proxy per step
    ppl_curve = []
    run = 0.0
    for t, lp in enumerate(logprobs):
        run += lp
        mean_lp = run / (t + 1)
        ppl_curve.append(math.exp(-mean_lp))
    return logprobs, ppl_curve


def _opera_reward(ppl_curve, reflective) -> float:
    """OPERA intrinsic reward: total POSITIVE perplexity drop accrued at the
    reflective steps. Δppl_t = ppl_{t-1} − ppl_t ; reward sums max(0, Δppl)."""
    r = 0.0
    for t in reflective:
        if 1 <= t < len(ppl_curve):
            dppl = ppl_curve[t - 1] - ppl_curve[t]
            if dppl > 0.0:
                r += dppl
    return r


def _judge_reward(rng, consistent: bool, trace_index: int, steps: int) -> float:
    """Simulated BIASED LLM-as-a-judge reward: a WEAK consistency term corrupted
    by STYLISTIC noise (per-trace verbosity/formatting quirk) and POSITIONAL
    noise (an order/length artifact) — the unreliable supervision OPERA replaces.
    High variance, low coupling to the true label."""
    w_c = 0.30                                   # weak true-signal weight
    w_style = 1.45                               # dominant stylistic bias
    w_pos = 0.95                                 # positional inconsistency
    consistency_term = 1.0 if consistent else 0.0
    style_noise = _gauss(rng)                    # verbosity / formatting quirk
    # positional artifact: judge favours certain positions/lengths spuriously
    pos_artifact = math.sin(0.9 * trace_index + 0.05 * steps) + 0.4 * _gauss(rng)
    return w_c * consistency_term + w_style * style_noise + w_pos * pos_artifact


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _opera_snapshot(seed: int = 42, traces: int = 8, steps: int = 12) -> dict:
    """
    Deterministically synthesize `traces` toy reasoning traces (each length
    `steps`), assign each a hidden ground-truth logical-consistency label,
    compute the OPERA intrinsic reward (Δperplexity at reflective steps) and the
    simulated biased-judge reward, and MEASURE: mean/variance of each reward, and
    the Pearson correlation of each reward with the consistency label.

    Pure stdlib; deterministic — same (seed, traces, steps) -> identical snapshot.
    """
    rng = _lcg(seed)
    reflective = _reflective_positions(steps)

    labels = []
    opera_rs = []
    judge_rs = []
    per_trace = []
    ppl_curves = []

    for i in range(traces):
        # ground-truth consistency label: deterministic ~50/50 from the PRNG
        consistent = next(rng) < 0.5
        lab = 1 if consistent else 0

        logprobs, ppl_curve = _build_trace(rng, steps, consistent, reflective)
        opera_r = _opera_reward(ppl_curve, reflective)
        judge_r = _judge_reward(rng, consistent, i, steps)

        labels.append(lab)
        opera_rs.append(opera_r)
        judge_rs.append(judge_r)
        ppl_curves.append(ppl_curve)
        per_trace.append({
            "trace": i,
            "label": lab,
            "ppl_first": round(ppl_curve[0], 6),
            "ppl_last": round(ppl_curve[-1], 6),
            "opera_r": round(opera_r, 6),
            "judge_r": round(judge_r, 6),
        })

    opera_reward = _mean(opera_rs)
    opera_reward_variance = _variance(opera_rs)
    judge_reward = _mean(judge_rs)
    judge_reward_variance = _variance(judge_rs)
    correlation_opera = _pearson(opera_rs, [float(x) for x in labels])
    correlation_judge = _pearson(judge_rs, [float(x) for x in labels])
    consistency_rate = _mean([float(x) for x in labels])

    cap = 6
    ppl_curves_head = [[round(v, 6) for v in c] for c in ppl_curves[:cap]]

    return {
        "traces": traces,
        "steps": steps,
        "reflective_steps": reflective,
        "opera_reward": round(opera_reward, 6),
        "opera_reward_variance": round(opera_reward_variance, 6),
        "judge_reward": round(judge_reward, 6),
        "judge_reward_variance": round(judge_reward_variance, 6),
        "correlation_opera": round(correlation_opera, 6),
        "correlation_judge": round(correlation_judge, 6),
        "consistency_rate": round(consistency_rate, 6),
        "per_trace": per_trace[:cap],
        "ppl_curves_head": ppl_curves_head,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


_HONEST_NOTE = (
    "MODELED: this is a clean-room, pure-stdlib TOY demo of the OPERA "
    "intrinsic-reward MECHANISM (Wenxuan Jiang et al., 'OPERA: Aligning "
    "Open-Ended Reasoning via Objective Perplexity-based Reinforcement "
    "Learning', arXiv:2606.25757), NOT a trained model or real RL rollout. "
    "Toy reasoning traces are synthesized as per-step token log-prob sequences; "
    "the running perplexity proxy is ppl_t = exp(-mean(logprob_0..t)). Each "
    "trace has a hidden ground-truth logical-consistency label; consistent "
    "traces resolve uncertainty at reflective steps (perplexity DROPS) and "
    "inconsistent ones do not. The OPERA intrinsic reward = total positive "
    "Δperplexity at the reflective steps; the simulated biased-judge reward = a "
    "weak consistency term corrupted by STYLISTIC and POSITIONAL noise (the "
    "unreliable supervision OPERA replaces). The reward means, variances, and "
    "the Pearson correlations with the consistency label are all MEASURED on "
    "the synthetic traces — reproducing in miniature the paper's finding that "
    "the intrinsic perplexity reward correlates with logical consistency while "
    "the noisy judge does not (higher judge_reward_variance = more unstable). "
    "This is a MECHANISM DEMO — it trains NOTHING and does NOT reproduce OPERA's "
    "Qwen3-8B SOTA, its parity with Gemini2.5 / MiniMax-M2.5, or its "
    "20,000-trajectory cold-start dataset (those are CLAIMS about REAL trained "
    "models the estate does not verify). DISTINCT from the grpo organ: grpo "
    "models GROUP-RELATIVE POLICY OPTIMIZATION reward dynamics, while OPERA here "
    "is an INTRINSIC PERPLEXITY reward, not group-relative advantage estimation. "
    "Pure stdlib, no numpy, no stdlib random, no GPU. Deterministic: same "
    "seed/traces/steps -> identical snapshot. NEVER-CLAIMED-AS a production "
    "reward model. SZL claims NONE of these methods as its own."
)


def _h_reward(req: Request):
    seed   = _ii(req, "seed", 42)
    traces = max(2, min(_ii(req, "traces", 8), 64))
    steps  = max(3, min(_ii(req, "steps", 12), 64))

    snap = _opera_snapshot(seed=seed, traces=traces, steps=steps)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "OPERA (Perplexity-Reward Reflective Alignment) — intrinsic perplexity-drop reward at reflective states vs a simulated biased LLM-judge reward, over synthetic reasoning traces with hidden logical-consistency labels",
        "method": "Per trace: token log-prob sequence -> running perplexity ppl_t=exp(-mean logprob). OPERA reward = sum of positive Δppl at reflective steps (uncertainty reduction). Judge reward = weak consistency term + stylistic noise + positional noise. Measure mean/variance of each reward and Pearson correlation with the ground-truth consistency label; OPERA correlates, noisy judge does not (higher judge_reward_variance = unstable)",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_keyless.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/opera/reward onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/opera"
    handlers = [
        (f"{base}/reward", _h_reward),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _opera_snapshot(seed=42, traces=8, steps=12)
    print("label: MODELED")
    print("traces:", snap["traces"], "steps:", snap["steps"])
    print("reflective_steps:", snap["reflective_steps"])
    print("--- METRIC: OPERA INTRINSIC REWARD (Δperplexity at reflective steps) ---")
    print("opera_reward:          ", snap["opera_reward"])
    print("opera_reward_variance: ", snap["opera_reward_variance"])
    print("--- METRIC: SIMULATED BIASED-JUDGE REWARD (stylistic+positional noise) ---")
    print("judge_reward:          ", snap["judge_reward"])
    print("judge_reward_variance: ", snap["judge_reward_variance"], "(higher = unstable)")
    print("--- METRIC: CORRELATION WITH GROUND-TRUTH CONSISTENCY LABEL ---")
    print("correlation_opera:     ", snap["correlation_opera"])
    print("correlation_judge:     ", snap["correlation_judge"])
    print("consistency_rate:      ", snap["consistency_rate"])

    # sanity: reflective steps valid
    assert all(1 <= p < snap["steps"] for p in snap["reflective_steps"]), "reflective steps out of range"

    # sanity: OPERA reward is a non-negative accumulation of perplexity drops
    assert snap["opera_reward"] >= 0.0, "opera_reward must be non-negative"
    assert snap["opera_reward_variance"] >= 0.0, "variance must be non-negative"
    assert snap["judge_reward_variance"] >= 0.0, "variance must be non-negative"

    # sanity: correlations in [-1, 1]
    assert -1.0 <= snap["correlation_opera"] <= 1.0, "corr out of range"
    assert -1.0 <= snap["correlation_judge"] <= 1.0, "corr out of range"

    # headline: OPERA reward correlates with consistency MORE than the noisy judge,
    # and the judge reward is the more unstable (higher-variance) signal.
    assert snap["correlation_opera"] > snap["correlation_judge"], "OPERA must correlate more than the noisy judge"
    assert snap["judge_reward_variance"] > snap["opera_reward_variance"], "judge reward must be the more unstable signal"

    # sanity: perplexity curves are positive (exp of a real number)
    for curve in snap["ppl_curves_head"]:
        assert all(v > 0.0 for v in curve), "perplexity must be positive"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _opera_snapshot(seed=42, traces=8, steps=12)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_opera: ALL OK — intrinsic perplexity reward correlates with consistency, noisy judge does not, deterministic.")
