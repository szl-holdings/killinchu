# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_specdecode.py — SZL self-speculative multi-token decoding endpoint
(Medusa/EAGLE-style draft-then-verify), MODELED.

Exposes a MODELED closed-form simulation of speculative decoding's draft-then-
verify rejection-sampling arithmetic (Leviathan et al. 2023) as a same-origin
REST endpoint, so the speculative-decoding surface organ has a live data
source that is honest, deterministic, and citable — never fabricated, never
random-faked, never run against a real drafter/target model pair.

  GET  /api/<ns>/v1/specdecode/simulate?seed=&draft_len=&trials=

WHAT IS SIMULATED
------------------
Speculative decoding accelerates autoregressive generation by having a small,
cheap DRAFT model propose `draft_len` candidate tokens per step; the large
TARGET model then verifies all of them in a single parallel forward pass.
Each drafted token is accepted or rejected via the modified rejection-sampling
rule from Leviathan et al. (2023) that guarantees the accepted sequence is
distributed IDENTICALLY to sampling directly from the target model:

    accept token i with probability   min(1, p_target(i) / p_draft(i))

Equivalently (as implemented here, deterministically): draw q_i ~ Uniform(0,1)
via the pure-stdlib LCG below; accept if p_draft(i) <= p_target(i) (the target
finds the draft token at least as likely — always accepted), else accept with
probability p_target(i) / p_draft(i). The first rejection in a step halts the
draft window; on halt, one corrective token is always emitted from the
target's own (adjusted) distribution, so every step yields >= 1 new token.

Over `trials` simulated steps this module computes:
  mean_accept_len   : mean number of tokens ACTUALLY accepted per step
                       (bounded in [0, draft_len]; the "+1" bonus corrective
                       token per step is reported separately, matching the
                       paper's E[tokens per step] = E[accepted] + 1 identity)
  acceptance_rate   : mean_accept_len / draft_len — fraction of proposed
                       draft tokens that survive verification
  speedup_factor    : E[tokens per target forward pass] versus 1.0 for vanilla
                       token-at-a-time autoregressive decoding, i.e.
                       (mean_accept_len + 1) / 1.0 — because one target
                       forward pass verifies the whole draft window and always
                       yields at least one new token, the target model does
                       ONE forward pass per step yet emits
                       (mean_accept_len + 1) tokens on average.

LOSSLESSNESS
------------
Because acceptance uses the min(1, p_target/p_draft) rejection rule and any
rejected token is replaced by a resample from the residual distribution
max(0, p_target - p_draft) (renormalized), the accepted token stream's
marginal distribution is mathematically IDENTICAL to greedy/ancestral
sampling straight from the target model alone (Leviathan et al. 2023, Thm 1).
Speculative decoding changes ONLY the wall-clock/FLOP schedule, never the
output distribution — this module reports that identity as a fixed boolean
flag, `lossless: true`, it does not re-derive the proof.

Returned JSON fields
---------------------
  label                : "MODELED" (always — deterministic re-implementation
                          of the accept/reject arithmetic, NOT a live model)
  model                : short description of the simulated setup
  seed                 : RNG seed used
  draft_len            : gamma — number of tokens the draft proposes per step
  trials               : number of simulated draft-then-verify steps
  acceptance_rate      : mean_accept_len / draft_len (0..1)
  mean_accept_len       : mean number of draft tokens accepted per step
  mean_tokens_per_step  : mean_accept_len + 1 (includes the guaranteed
                          corrective/bonus token every step)
  speedup_factor        : mean_tokens_per_step / 1.0 — expected tokens emitted
                          per TARGET forward pass vs vanilla autoregressive
                          decoding (which emits exactly 1 token per forward
                          pass by definition)
  per_step_accept_lengths : list (capped) of accepted-length per trial, for
                          the surface's token-tree animation
  lossless              : true (rejection-sampling identity; see note above)
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form/Monte-Carlo-by-LCG re-implementation of
  the Leviathan et al. (2023) rejection-sampling ACCEPT/REJECT arithmetic for
  speculative decoding. It draws synthetic per-token draft/target
  probabilities from the pure-stdlib LCG PRNG below (no numpy, no stdlib
  `random`) and applies the exact accept/reject rule. It is NOT Medusa, NOT
  EAGLE, uses NO proprietary weights, runs NO real draft or target model, and
  is NEVER-CLAIMED-AS a production drafter. The label "MODELED" is returned
  verbatim and displayed verbatim by the surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Speculative decoding (rejection-sampling arithmetic simulated here):
    Leviathan, Kalman & Matias (2023) "Fast Inference from Transformers via
    Speculative Decoding". arXiv:2211.17192. https://arxiv.org/abs/2211.17192
  Medusa (multiple decoding heads, tree-based verification — reference only):
    Cai, Li, Geng, Peng, Lee, Chen & Dao (2024) "Medusa: Simple LLM Inference
    Acceleration Framework with Multiple Decoding Heads".
    https://github.com/FasterDecoding/Medusa
  EAGLE (feature-level extrapolation drafting — reference only):
    Li, Wei, Zhang & Zhang (2024) "EAGLE: Speculative Sampling Requires
    Rethinking Feature Uncertainty". arXiv:2401.15077.
    https://arxiv.org/abs/2401.15077
  NEVER-CLAIMED-AS: this module is not Medusa, not EAGLE, and does not
  reproduce either project's code, weights, or measured benchmark numbers. It
  is a clean-room MODELED simulation of the shared accept/reject arithmetic
  those methods build on.

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
    "Speculative Decoding — Leviathan et al. arXiv:2211.17192": "https://arxiv.org/abs/2211.17192",
    "Medusa — Cai et al., github.com/FasterDecoding/Medusa": "https://github.com/FasterDecoding/Medusa",
    "EAGLE — Li et al. arXiv:2401.15077": "https://arxiv.org/abs/2401.15077",
}

# Cap on how many per-step accepted-length samples we echo back for the
# surface's token-tree animation (keeps payload bounded for large `trials`).
_MAX_STEP_SAMPLES = 64


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
# MODELED draft-then-verify speculative decoding simulation (deterministic)
# ---------------------------------------------------------------------------
def _simulate_step(rng, draft_len: int) -> int:
    """Simulate one draft-then-verify step; return the number of draft
    tokens ACCEPTED before the first rejection (0..draft_len).

    For each of the `draft_len` proposed tokens we draw a synthetic draft
    probability p_draft and target probability p_target (both in (0,1)),
    then apply the Leviathan et al. (2023) rejection rule:
        accept if p_draft <= p_target        (target agrees at least as much)
        else accept with probability p_target / p_draft, using a fresh
             uniform draw u ~ (0,1) from the same LCG stream: accept iff
             u <= p_target / p_draft.
    The first rejection halts the window (the standard algorithm structure).
    """
    accepted = 0
    for _ in range(draft_len):
        p_draft = 0.05 + 0.90 * next(rng)     # draft-model token probability, (0.05, 0.95)
        p_target = 0.05 + 0.90 * next(rng)    # target-model token probability, (0.05, 0.95)
        if p_draft <= p_target:
            accepted += 1
            continue
        u = next(rng)
        if u <= (p_target / p_draft):
            accepted += 1
            continue
        break  # first rejection halts the draft window
    return accepted


def _specdecode_snapshot(seed: int = 42, draft_len: int = 5, trials: int = 256) -> dict:
    """
    Run `trials` simulated draft-then-verify steps with a `draft_len`-token
    draft window each, using the pure-stdlib LCG for all randomness.

    Pure stdlib; deterministic — same (seed, draft_len, trials) -> identical
    snapshot, every time.
    """
    rng = _lcg(seed)
    lengths = [_simulate_step(rng, draft_len) for _ in range(trials)]

    total_accepted = sum(lengths)
    mean_accept_len = total_accepted / max(trials, 1)
    acceptance_rate = mean_accept_len / max(draft_len, 1)

    # Every step guarantees >= 1 new token (the corrective/bonus token drawn
    # from the target's own distribution, even if all draft tokens reject).
    mean_tokens_per_step = mean_accept_len + 1.0

    # speedup_factor: expected tokens emitted per TARGET forward pass, vs the
    # fixed baseline of 1.0 token per forward pass for vanilla autoregressive
    # decoding (one token-at-a-time serial pass = 1 token, always).
    speedup_factor = mean_tokens_per_step / 1.0

    sample = lengths[:_MAX_STEP_SAMPLES]

    return {
        "draft_len": draft_len,
        "trials": trials,
        "acceptance_rate": round(acceptance_rate, 6),
        "mean_accept_len": round(mean_accept_len, 6),
        "mean_tokens_per_step": round(mean_tokens_per_step, 6),
        "speedup_factor": round(speedup_factor, 6),
        "per_step_accept_lengths": sample,
        "lossless": True,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_simulate(req: Request):
    seed      = _ii(req, "seed",      42)
    draft_len = max(1, min(_ii(req, "draft_len", 5), 32))
    trials    = max(1, min(_ii(req, "trials",   256), 20000))

    snap = _specdecode_snapshot(seed=seed, draft_len=draft_len, trials=trials)

    return JSONResponse({
        "label":     "MODELED",
        "model":     "Self-speculative multi-token decoding: draft-then-verify rejection sampling (Medusa/EAGLE-style)",
        "method":    "Leviathan et al. (2023) accept/reject rule: accept if p_draft<=p_target, else accept w.p. p_target/p_draft; first rejection halts window; +1 guaranteed corrective token per step",
        "seed":      seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "Leviathan et al. (2023) speculative-decoding ACCEPT/REJECT rejection-sampling "
            "arithmetic (arXiv:2211.17192), NOT a run of Medusa (github.com/FasterDecoding/Medusa) "
            "or EAGLE (arXiv:2401.15077), and NEVER-CLAIMED-AS a production drafter. Synthetic "
            "per-token draft/target probabilities are drawn from a deterministic LCG PRNG (no "
            "numpy, no stdlib random, no proprietary weights, no real draft or target model). "
            "The accept/reject rule itself is the exact rejection-sampling identity from the "
            "cited paper, which guarantees the accepted token stream is distributed IDENTICALLY "
            "to sampling directly from the target model — speculative decoding changes only the "
            "compute schedule, never the output distribution. This module reports that identity "
            "as a fixed flag (lossless=true); it does not re-derive the proof. Deterministic: "
            "same seed/draft_len/trials -> identical snapshot. SZL claims NONE of these methods "
            "as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_interpretability.register() / szl_testtime.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/specdecode/simulate onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/specdecode"
    handlers = [
        (f"{base}/simulate", _h_simulate),
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
    snap = _specdecode_snapshot(seed=42, draft_len=5, trials=256)
    print("label: MODELED")
    print("draft_len:", snap["draft_len"])
    print("trials:", snap["trials"])
    print("acceptance_rate:", snap["acceptance_rate"])
    print("mean_accept_len:", snap["mean_accept_len"])
    print("mean_tokens_per_step:", snap["mean_tokens_per_step"])
    print("speedup_factor:", snap["speedup_factor"])
    print("lossless:", snap["lossless"])
    print("sample per_step_accept_lengths[:10]:", snap["per_step_accept_lengths"][:10])

    # sanity: bounds
    assert 0.0 <= snap["acceptance_rate"] <= 1.0, "acceptance_rate out of [0,1]"
    assert 0.0 <= snap["mean_accept_len"] <= snap["draft_len"], "mean_accept_len out of bounds"
    assert snap["speedup_factor"] >= 1.0, "speedup_factor must be >= 1.0 (>=1 token/step always)"

    # sanity: determinism — identical seed/draft_len/trials -> identical snapshot
    snap2 = _specdecode_snapshot(seed=42, draft_len=5, trials=256)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: longer draft window with same seed should not raise acceptance_rate
    # above 1.0 and should still respect 0<=mean_accept_len<=draft_len.
    snap3 = _specdecode_snapshot(seed=42, draft_len=8, trials=256)
    assert 0.0 <= snap3["mean_accept_len"] <= snap3["draft_len"]

    print()
    print("szl_specdecode: ALL OK — deterministic, lossless flag set, bounds respected.")
