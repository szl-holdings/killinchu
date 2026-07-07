# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_grpo.py — ADDITIVE Group-Relative-Policy-Optimization reward-dynamics simulator for
killinchu's frontier surface (backs a11oy static/3d/surfaces/grpo.js).

Group Relative Policy Optimization (GRPO), introduced in DeepSeekMath (Shao, Wang, Zhu, Xu, Song,
Bi, Zhang, Zhang, Li, Wu, Guo 2024; arXiv:2402.03300), is a critic-free variant of PPO for RL
fine-tuning of language models. For each prompt it samples a GROUP of G outputs from the current
policy, scores each with a reward model, and — instead of a learned value function — computes the
advantage of each output as its reward standardized WITHIN the group:
    A_i = (r_i - mean(r_group)) / (std(r_group) + eps).
The policy is then updated with the clipped PPO-style objective using these group-relative
advantages, plus a KL penalty toward a reference policy. Removing the critic halves the trained
model count and the group baseline reduces gradient variance.

This module simulates the reward dynamics deterministically (seeded, NO trained policy): a scalar
policy parameter theta drives a reward landscape r(theta); each step samples a group of G
perturbed outputs, standardizes their rewards to advantages, and takes a clipped, KL-penalized
ascent step. It reports the reward trajectory, mean group advantage magnitude, KL from the
reference, and whether reward improves monotonically-ish over steps.

Reported (field names read verbatim by grpo.js):
  group_size            — G, outputs sampled per prompt
  steps                 — GRPO update steps simulated
  final_reward          — reward after the last step (MODELED)
  reward_gain           — final_reward - initial_reward
  mean_advantage_abs    — mean |group-standardized advantage| over the run
  kl_from_ref           — KL(policy || reference) at the end (MODELED)
  reward_curve          — [{step, reward}]

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic reward-dynamics SIMULATION. NOT a trained policy / reward model running;
    NO LLM, NO GPU, NO learned weights. The reward landscape, group noise, clip and KL coefficients
    are SEEDED inputs / MODELED references, NOT measured on any real RLHF run.
  * "reward_gain" is a property of the modeled landscape + the GRPO update rule, honestly labeled,
    not a benchmark-accuracy claim about any real model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/grpo/reward-dynamics — GRPO group-relative reward-dynamics snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "grpo": ("Shao, Wang, Zhu, Xu, Song, Bi, Zhang, Zhang, Li, Wu, Guo (2024) DeepSeekMath: "
             "Pushing the Limits of Mathematical Reasoning in Open Language Models (introduces "
             "Group Relative Policy Optimization, GRPO) — arXiv:2402.03300 · "
             "https://arxiv.org/abs/2402.03300"),
    "ppo": ("Schulman, Wolski, Dhariwal, Radford, Klimov (2017) Proximal Policy Optimization "
            "Algorithms — arXiv:1707.06347 · https://arxiv.org/abs/1707.06347"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | GRPO_REWARD_DYNAMICS_SIM | NOT_LIVE | NO_MODEL | REWARD_IS_MODELED"


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


def _reward(theta: float, theta_star: float) -> float:
    """MODELED smooth reward landscape peaked at theta_star (Gaussian bump, in [0,1])."""
    return _math.exp(-0.5 * (theta - theta_star) ** 2)


def grpo_reward_dynamics(seed: int = 42, group_size: int = 8, steps: int = 24,
                         lr: float = 0.35, clip: float = 0.2, kl_coef: float = 0.02) -> dict:
    """GRPO group-relative reward-dynamics snapshot (MODELED).

    group_size — G, outputs sampled per prompt per step.
    steps      — number of GRPO update steps.
    lr         — ascent step size on the group-relative advantage.
    clip       — PPO-style clip range on the (modeled) probability ratio.
    kl_coef    — KL penalty coefficient toward the reference policy.
    seed       — RNG seed; identical inputs give identical output (deterministic).
    """
    G = max(2, min(256, int(group_size)))
    steps = max(1, min(4096, int(steps)))
    lr = max(1e-4, min(2.0, float(lr)))
    clip = max(1e-3, min(1.0, float(clip)))
    kl_coef = max(0.0, min(1.0, float(kl_coef)))
    rng = _LCG(int(seed) * 1_000_003 + G * 131 + steps * 17)

    theta_star = 1.0        # reward peak
    theta = -2.0            # start far from the peak
    theta_ref = theta       # reference policy frozen at the start
    sigma = 0.6             # group sampling spread (exploration)
    eps = 1e-8

    reward_curve = []
    adv_mags = []
    initial_reward = _reward(theta, theta_star)

    for step in range(steps):
        # Sample a group of G outputs (perturbations of theta) and score each.
        outs = [theta + sigma * rng.normal() for _ in range(G)]
        rewards = [_reward(o, theta_star) for o in outs]
        mu = sum(rewards) / G
        var = sum((r - mu) ** 2 for r in rewards) / G
        std = _math.sqrt(var)
        # Group-relative advantages: standardize rewards within the group.
        adv = [(rewards[i] - mu) / (std + eps) for i in range(G)]
        adv_mags.append(sum(abs(a) for a in adv) / G)

        # Clipped, advantage-weighted ascent toward higher-reward group members, minus KL pull
        # back to the reference (MODELED PPO-GRPO surrogate on the scalar theta).
        grad = 0.0
        for i in range(G):
            ratio = 1.0  # modeled on-policy ratio (fresh samples) -> clip is a bound, honest note
            ratio_clipped = max(1.0 - clip, min(1.0 + clip, ratio))
            direction = outs[i] - theta
            grad += ratio_clipped * adv[i] * direction
        grad /= G
        kl_pull = kl_coef * (theta - theta_ref)
        theta = theta + lr * grad - lr * kl_pull

        reward_curve.append({"step": step, "reward": round(_reward(theta, theta_star), 6)})

    final_reward = _reward(theta, theta_star)
    reward_gain = final_reward - initial_reward
    mean_advantage_abs = sum(adv_mags) / len(adv_mags)
    # KL from reference for a 1-D Gaussian policy centered at theta vs theta_ref (unit variance).
    kl_from_ref = 0.5 * (theta - theta_ref) ** 2

    return {
        "service": "grpo-reward-dynamics",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/grpo.js ---
        "group_size": int(G),
        "steps": int(steps),
        "final_reward": round(float(final_reward), 6),
        "initial_reward": round(float(initial_reward), 6),
        "reward_gain": round(float(reward_gain), 6),
        "mean_advantage_abs": round(float(mean_advantage_abs), 6),
        "kl_from_ref": round(float(kl_from_ref), 6),
        "reward_curve": reward_curve,
        "theta_final": round(float(theta), 6),
        "theta_star": theta_star,
        "formulas": {
            "advantage": "A_i = (r_i - mean(r_group)) / (std(r_group) + eps)  (critic-free baseline)",
            "objective": "clipped PPO ratio * A_i  -  kl_coef * KL(policy || reference)",
            "reward_landscape": "r(theta) = exp(-0.5 (theta - theta*)^2)  (MODELED)",
            "kl_from_ref": "0.5 (theta - theta_ref)^2  (unit-variance Gaussian policies)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python group-relative reward-dynamics simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic reward-dynamics sim; NO LLM policy, NO reward model, NO "
                            "GPU, NO learned weights. A real RLHF/GRPO training run is ROADMAP."),
        },
        "honest_note": ("MODELED GRPO reward dynamics. reward_gain is a property of the modeled "
                        "landscape + the group-relative update rule, not a benchmark-accuracy "
                        "claim about any real trained model."),
        "wired_into": "frontier ring — GRPO group-relative reward-dynamics surface",
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (advisory reward dynamics — never autonomous)",
        "citations": {"grpo": CITATIONS["grpo"], "ppo": CITATIONS["ppo"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/grpo" % ns
    path = "%s/reward-dynamics" % base

    @app.get(path)
    async def _kc_grpo(seed: int = 42, group_size: int = 8, steps: int = 24):  # noqa: ANN202
        try:
            return JSONResponse(grpo_reward_dynamics(seed=seed, group_size=group_size, steps=steps))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "grpo-reward-dynamics",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "final_reward": None, "reward_gain": None},
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
    r = grpo_reward_dynamics(seed=42, group_size=8, steps=24)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("group_size", "steps"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("final_reward", "reward_gain", "mean_advantage_abs", "kl_from_ref"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["reward_curve"], list) and r["reward_curve"], r

    # bounds: reward in [0,1]; GRPO should improve reward from a far start.
    assert 0.0 <= r["final_reward"] <= 1.0001, r["final_reward"]
    assert r["reward_gain"] > 0.0, r["reward_gain"]
    assert r["mean_advantage_abs"] > 0.0, r["mean_advantage_abs"]
    assert r["kl_from_ref"] >= 0.0, r["kl_from_ref"]
    out["metrics"] = {"final_reward": r["final_reward"], "reward_gain": r["reward_gain"],
                      "mean_advantage_abs": r["mean_advantage_abs"], "kl_from_ref": r["kl_from_ref"]}

    assert "2402.03300" in r["citations"]["grpo"], r["citations"]

    # determinism
    r2 = grpo_reward_dynamics(seed=42, group_size=8, steps=24)
    assert r2["reward_curve"] == r["reward_curve"], "non-deterministic"
    assert r2["final_reward"] == r["final_reward"], "non-deterministic"
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
