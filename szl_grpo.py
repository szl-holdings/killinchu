# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_grpo.py — SZL GRPO REWARD DYNAMICS endpoint (Group Relative Policy
Optimization, critic-free RL post-training), MODELED.

Exposes a MODELED closed-form/deterministic simulation of the GRPO training
loop's group-advantage + PPO-clip surrogate + KL-penalty arithmetic
(Shao et al. 2024, DeepSeekMath, arXiv:2402.03300; as also used to train
DeepSeek-R1, arXiv:2501.12948) as a same-origin REST endpoint, so the GRPO
reward-dynamics surface organ has a live data source that is honest,
deterministic, and citable — never fabricated, never random-faked, never a
run of an actual policy-gradient training job against a real reward model.

  GET  /api/<ns>/v1/grpo/reward-dynamics?seed=&group_size=&steps=&kl_beta=

WHAT IS SIMULATED
------------------
GRPO removes the separate value/critic network that vanilla PPO requires.
For each training step, the policy samples a GROUP of `group_size`
completions for the same prompt/question and receives a scalar reward for
each. The advantage of each sample is computed by normalizing against the
GROUP's own mean and standard deviation — no learned critic is needed:

    A_i = (r_i - mean(r_1..r_G)) / (std(r_1..r_G) + eps)

The policy is then updated via a PPO-style clipped surrogate objective using
that group-relative advantage, plus a KL-divergence penalty against a fixed
reference policy (the pre-RL checkpoint) to keep the policy from drifting
too far, using the low-variance "k3" KL estimator from Schulman's unbiased
KL-estimation note (k3 = exp(log_ratio) - log_ratio - 1, an always-nonnegative
estimator of KL(pi || pi_ref)):

    J_GRPO(theta) = E[ min( ratio_i * A_i, clip(ratio_i, 1-eps, 1+eps) * A_i )
                        - kl_beta * D_KL_k3(pi_theta || pi_ref) ]

This module draws entirely SYNTHETIC per-sample rewards and importance
ratios from the pure-stdlib LCG PRNG below (no numpy, no stdlib `random`),
then applies the exact group-normalization, PPO-clip, and k3-KL arithmetic
above, deterministically, so that a given (seed, group_size, steps, kl_beta)
tuple always reproduces byte-identical output. It does NOT run any real
policy network, reward model, or gradient step, and is NEVER-CLAIMED-AS a
DeepSeek-R1 or DeepSeekMath training run.

Returned JSON fields
---------------------
  label                 : "MODELED" (always — deterministic re-implementation
                           of the GRPO group-advantage/PPO-clip/KL arithmetic,
                           NOT a trained policy)
  model                 : short description of the simulated setup
  seed                  : RNG seed used
  group_size            : G — number of sampled completions per group/step
  steps                 : number of simulated training steps
  kl_beta               : KL-penalty coefficient (beta) vs the reference policy
  clip_eps              : PPO-clip epsilon (fixed at 0.2, per the GRPO/PPO papers)
  mean_reward           : mean group reward at the FINAL step
  mean_advantage        : mean |group-normalized advantage| at the final step
  kl_divergence         : k3 KL-penalty estimate at the final step (>= 0)
  clip_fraction         : fraction of samples whose probability ratio was
                           clipped at the final step
  final_policy_score    : converging scalar proxy for policy quality (0..1),
                           MODELED as saturating toward 1 as reward rises and
                           KL/clip pressure fall — NOT a real eval score
  reward_trajectory     : list (len == steps) of per-step mean group reward
  kl_trajectory         : list (len == steps) of per-step k3 KL estimate
  policy_score_trajectory : list (len == steps) of the converging policy_score
  advantage_trajectory  : list (len == steps) of per-step mean |advantage|
  clip_fraction_trajectory : list (len == steps) of per-step clip_fraction
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form/Monte-Carlo-by-LCG re-implementation
  of the GRPO group-relative-advantage, PPO-clip surrogate, and k3 KL-penalty
  ARITHMETIC described in Shao et al. (2024) and used (per DeepSeek-AI 2025)
  to train DeepSeek-R1. It draws synthetic per-sample rewards and importance
  ratios from the pure-stdlib LCG PRNG below (no numpy, no stdlib `random`,
  no proprietary weights, no real policy/reward/reference model, no real
  gradient step). It is NOT a training run of DeepSeekMath or DeepSeek-R1,
  trains NOTHING, and is NEVER-CLAIMED-AS a DeepSeek-R1/DeepSeekMath training
  run. The label "MODELED" is returned verbatim and displayed verbatim by
  the surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  GRPO — group-relative advantage + PPO-clip + KL-penalty objective
  (simulated here):
    Shao, Wang, Zhu, Xu, Song, Bi, Zhang, Zhang, Li, Wu & Guo (2024)
    "DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open
    Language Models". arXiv:2402.03300. https://arxiv.org/abs/2402.03300
  DeepSeek-R1 — large-scale RL post-training using GRPO as the RL
  framework (reference only; not reproduced here):
    DeepSeek-AI (2025) "DeepSeek-R1: Incentivizing Reasoning Capability in
    LLMs via Reinforcement Learning". arXiv:2501.12948.
    https://arxiv.org/abs/2501.12948
  NEVER-CLAIMED-AS: this module is not DeepSeekMath, not DeepSeek-R1, trains
  no policy, and does not reproduce either project's code, weights, reward
  model, or measured benchmark numbers. It is a clean-room MODELED
  simulation of the shared group-advantage/PPO-clip/KL arithmetic those
  methods build on.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "DeepSeekMath (GRPO) — Shao et al. arXiv:2402.03300": "https://arxiv.org/abs/2402.03300",
    "DeepSeek-R1 — DeepSeek-AI arXiv:2501.12948": "https://arxiv.org/abs/2501.12948",
}

# PPO-clip epsilon — fixed per the GRPO/PPO papers (not user-configurable;
# it is a training-recipe constant, not a data-driven quantity).
_CLIP_EPS = 0.2

# Cap on how many per-step trajectory samples we echo back for the surface's
# scatter/HUD animation (keeps payload bounded for large `steps`).
_MAX_TRAJ_SAMPLES = 512


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# MODELED GRPO training-step simulation (deterministic)
# ---------------------------------------------------------------------------
def _sqrt(x: float) -> float:
    """Pure-stdlib Newton's-method square root (avoids importing math just
    for sqrt, keeping the module's dependency footprint minimal/explicit)."""
    if x <= 0.0:
        return 0.0
    guess = x
    for _ in range(40):
        guess = 0.5 * (guess + x / guess)
    return guess


def _exp(x: float) -> float:
    """Pure-stdlib exp via a truncated Taylor series (sufficient precision
    for the bounded log-ratio ranges used in this simulation; avoids a
    `math` import to keep the module deterministic/stdlib-minimal by
    construction, matching the sibling organs' style)."""
    # Range-reduce: exp(x) = exp(x/2^k)^(2^k), keeps the Taylor series accurate.
    k = 0
    xr = x
    while xr > 1.0 or xr < -1.0:
        xr /= 2.0
        k += 1
    term = 1.0
    total = 1.0
    for n in range(1, 25):
        term *= xr / n
        total += term
    for _ in range(k):
        total *= total
    return total


def _sample_group_rewards(rng, group_size: int, step_idx: int, total_steps: int):
    """Draw `group_size` synthetic rewards for one GRPO training step.

    Reward center drifts upward across steps (0.35 -> ~0.85), MODELING a
    policy that is gradually improving under RL pressure, with per-sample
    noise drawn from the LCG. Purely synthetic — no real rollout, no real
    reward model.
    """
    progress = step_idx / max(total_steps - 1, 1)  # 0..1 across the run
    center = 0.35 + 0.50 * progress
    rewards = []
    for _ in range(group_size):
        noise = (next(rng) - 0.5) * 0.6   # symmetric noise in [-0.3, 0.3)
        r = max(0.0, min(1.0, center + noise))
        rewards.append(r)
    return rewards


def _group_advantages(rewards):
    """A_i = (r_i - mean) / (std + eps) — the GRPO group-relative advantage,
    critic-free: the baseline is the GROUP's own mean reward, not a learned
    value function."""
    n = len(rewards)
    mean_r = sum(rewards) / max(n, 1)
    var_r = sum((r - mean_r) ** 2 for r in rewards) / max(n, 1)
    std_r = _sqrt(var_r)
    eps = 1e-6
    advantages = [(r - mean_r) / (std_r + eps) for r in rewards]
    return advantages, mean_r, std_r


def _ppo_clip_and_kl(rng, advantages, kl_beta: float, step_idx: int, total_steps: int):
    """Apply the PPO-clip surrogate + k3 KL-penalty arithmetic for one step.

    For each sample we draw a synthetic importance ratio
    ratio_i = pi_theta(o_i)/pi_theta_old(o_i) near 1.0 (small policy update
    per step, as in real PPO/GRPO minibatches), compute the clipped
    surrogate min(ratio*A, clip(ratio,1-eps,1+eps)*A), and separately draw a
    synthetic log-ratio vs the FIXED reference policy to score the k3 KL
    estimator k3 = exp(log_ratio) - log_ratio - 1 (Schulman's unbiased,
    always-nonnegative KL estimator; http://joschu.net/blog/kl-approx.html
    background note, applied per the DeepSeekMath GRPO objective which uses
    this exact estimator for its KL penalty term).
    """
    progress = step_idx / max(total_steps - 1, 1)
    # KL drift-vs-reference shrinks slightly over training as the policy
    # settles (MODELED: bounded, deterministic, decaying magnitude).
    kl_scale = 0.25 * (1.0 - 0.6 * progress)

    surrogates = []
    clipped_count = 0
    kl_terms = []
    for a_i in advantages:
        ratio = 1.0 + (next(rng) - 0.5) * 0.30       # ratio in [0.85, 1.15)
        clipped_ratio = min(max(ratio, 1.0 - _CLIP_EPS), 1.0 + _CLIP_EPS)
        unclipped_term = ratio * a_i
        clipped_term = clipped_ratio * a_i
        surrogate = min(unclipped_term, clipped_term)
        surrogates.append(surrogate)
        if clipped_ratio != ratio:
            clipped_count += 1

        log_ratio = (next(rng) - 0.5) * 2.0 * kl_scale  # log(pi/pi_ref), bounded
        k3 = _exp(log_ratio) - log_ratio - 1.0           # always >= 0
        kl_terms.append(max(0.0, k3))

    n = max(len(advantages), 1)
    mean_surrogate = sum(surrogates) / n
    clip_fraction = clipped_count / n
    mean_kl = sum(kl_terms) / n

    objective = mean_surrogate - kl_beta * mean_kl
    return objective, clip_fraction, mean_kl


def _policy_score(step_idx: int, total_steps: int, mean_reward: float, mean_kl: float, clip_fraction: float) -> float:
    """MODELED converging scalar proxy for "policy quality" in [0, 1].

    Saturates upward with training progress and mean_reward, and is damped
    slightly by KL/clip pressure (a policy churning too hard against clip or
    drifting from the reference scores marginally lower here) — a smooth,
    deterministic, monotone-trending construction for visualization only.
    It is NOT a benchmark score, NOT pass@1, NOT any real evaluation metric.
    """
    progress = step_idx / max(total_steps - 1, 1)
    saturating = 1.0 - _exp(-3.0 * progress)          # 0 -> ~0.95 as progress: 0->1
    reward_term = 0.5 * mean_reward + 0.5 * saturating
    damping = 1.0 - 0.15 * min(1.0, mean_kl) - 0.10 * clip_fraction
    damping = max(0.4, damping)
    score = max(0.0, min(1.0, reward_term * damping))
    return score


def _grpo_snapshot(seed: int = 42, group_size: int = 8, steps: int = 200, kl_beta: float = 0.04) -> dict:
    """
    Run `steps` simulated GRPO training steps, each sampling a group of
    `group_size` synthetic rewards, computing group-normalized advantages,
    applying the PPO-clip surrogate (clip_eps=0.2) plus a k3 KL penalty
    (coefficient kl_beta) against a synthetic reference policy.

    Pure stdlib; deterministic — same (seed, group_size, steps, kl_beta) ->
    identical snapshot, every time.
    """
    rng = _lcg(seed)

    reward_traj = []
    advantage_traj = []
    kl_traj = []
    clip_frac_traj = []
    policy_score_traj = []

    for step_idx in range(steps):
        rewards = _sample_group_rewards(rng, group_size, step_idx, steps)
        advantages, mean_reward, _std_r = _group_advantages(rewards)
        _objective, clip_fraction, mean_kl = _ppo_clip_and_kl(rng, advantages, kl_beta, step_idx, steps)
        mean_abs_advantage = sum(abs(a) for a in advantages) / max(len(advantages), 1)
        score = _policy_score(step_idx, steps, mean_reward, mean_kl, clip_fraction)

        reward_traj.append(mean_reward)
        advantage_traj.append(mean_abs_advantage)
        kl_traj.append(mean_kl)
        clip_frac_traj.append(clip_fraction)
        policy_score_traj.append(score)

    def _sample(seq):
        if len(seq) <= _MAX_TRAJ_SAMPLES:
            return [round(v, 6) for v in seq]
        # even stride downsample, always including the final point
        stride = max(1, len(seq) // _MAX_TRAJ_SAMPLES)
        out = [round(v, 6) for v in seq[::stride]]
        if out[-1] != round(seq[-1], 6):
            out.append(round(seq[-1], 6))
        return out

    return {
        "group_size":   group_size,
        "steps":        steps,
        "kl_beta":      round(kl_beta, 6),
        "clip_eps":     _CLIP_EPS,
        "mean_reward":        round(reward_traj[-1], 6),
        "mean_advantage":     round(advantage_traj[-1], 6),
        "kl_divergence":      round(kl_traj[-1], 6),
        "clip_fraction":      round(clip_frac_traj[-1], 6),
        "final_policy_score": round(policy_score_traj[-1], 6),
        "reward_trajectory":        _sample(reward_traj),
        "kl_trajectory":            _sample(kl_traj),
        "policy_score_trajectory":  _sample(policy_score_traj),
        "advantage_trajectory":     _sample(advantage_traj),
        "clip_fraction_trajectory": _sample(clip_frac_traj),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _ff(req: Request, key: str, default: float) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return default


def _h_reward_dynamics(req: Request):
    seed       = _ii(req, "seed",       42)
    group_size = max(2, min(_ii(req, "group_size", 8), 64))
    steps      = max(1, min(_ii(req, "steps",      200), 5000))
    kl_beta    = max(0.0, min(_ff(req, "kl_beta",  0.04), 1.0))

    snap = _grpo_snapshot(seed=seed, group_size=group_size, steps=steps, kl_beta=kl_beta)

    return JSONResponse({
        "label":     "MODELED",
        "model":     "GRPO reward dynamics: group-relative advantage + PPO-clip surrogate + k3 KL penalty (critic-free RL post-training)",
        "method":    "Shao et al. (2024) GRPO objective: A_i=(r_i-mean)/std over a sampled group; clipped surrogate min(ratio*A, clip(ratio,1-eps,1+eps)*A) with eps=0.2; k3 KL penalty k3=exp(log_ratio)-log_ratio-1 vs a fixed reference policy, weighted by kl_beta",
        "seed":      seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "GRPO group-relative-advantage, PPO-clip surrogate (clip_eps=0.2), and k3 "
            "KL-penalty ARITHMETIC introduced in Shao et al. (2024), DeepSeekMath "
            "(arXiv:2402.03300) and later used (per DeepSeek-AI 2025, arXiv:2501.12948) "
            "to train DeepSeek-R1. Synthetic per-sample rewards and importance ratios "
            "are drawn from a deterministic LCG PRNG (no numpy, no stdlib random, no "
            "proprietary weights). This module trains NO real policy, calls NO reward "
            "model, and runs NO gradient step — it is NEVER-CLAIMED-AS a DeepSeek-R1 or "
            "DeepSeekMath training run. Deterministic: same seed/group_size/steps/kl_beta "
            "-> identical snapshot. SZL claims NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_specdecode.register() / szl_testtime.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/grpo/reward-dynamics onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/grpo"
    handlers = [
        (f"{base}/reward-dynamics", _h_reward_dynamics),
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
    snap = _grpo_snapshot(seed=42, group_size=8, steps=200, kl_beta=0.04)
    print("label: MODELED")
    print("group_size:", snap["group_size"])
    print("steps:", snap["steps"])
    print("kl_beta:", snap["kl_beta"])
    print("clip_eps:", snap["clip_eps"])
    print("mean_reward:", snap["mean_reward"])
    print("mean_advantage:", snap["mean_advantage"])
    print("kl_divergence:", snap["kl_divergence"])
    print("clip_fraction:", snap["clip_fraction"])
    print("final_policy_score:", snap["final_policy_score"])
    print("reward_trajectory[:5]:", snap["reward_trajectory"][:5])
    print("reward_trajectory[-5:]:", snap["reward_trajectory"][-5:])
    print("policy_score_trajectory[:5]:", snap["policy_score_trajectory"][:5])
    print("policy_score_trajectory[-5:]:", snap["policy_score_trajectory"][-5:])
    print("kl_trajectory[:5]:", snap["kl_trajectory"][:5])
    print("kl_trajectory[-5:]:", snap["kl_trajectory"][-5:])

    # sanity: bounds
    assert 0.0 <= snap["mean_reward"] <= 1.0, "mean_reward out of [0,1]"
    assert snap["kl_divergence"] >= 0.0, "k3 KL estimate must be >= 0"
    assert 0.0 <= snap["clip_fraction"] <= 1.0, "clip_fraction out of [0,1]"
    assert 0.0 <= snap["final_policy_score"] <= 1.0, "final_policy_score out of [0,1]"
    assert all(k >= 0.0 for k in snap["kl_trajectory"]), "kl_trajectory has a negative entry"
    assert len(snap["reward_trajectory"]) == len(snap["policy_score_trajectory"]), "trajectory length mismatch"

    # sanity: policy_score should trend upward (rising), comparing early mean to late mean
    early = snap["policy_score_trajectory"][:10]
    late = snap["policy_score_trajectory"][-10:]
    assert sum(late) / len(late) > sum(early) / len(early), "policy_score did not rise over training"

    # sanity: determinism — identical seed/group_size/steps/kl_beta -> identical snapshot
    snap2 = _grpo_snapshot(seed=42, group_size=8, steps=200, kl_beta=0.04)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: different seed should (almost certainly) change the trajectory
    snap3 = _grpo_snapshot(seed=7, group_size=8, steps=200, kl_beta=0.04)
    assert snap3["reward_trajectory"] != snap["reward_trajectory"], "seed had no effect on trajectory"

    print()
    print("szl_grpo: ALL OK — deterministic, policy_score rising, kl bounded >=0, clip_fraction in [0,1].")
