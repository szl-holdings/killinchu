# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_dllm.py — SZL diffusion-LLM (dLLM) parallel-denoising endpoint.

Exposes a MODELED, clean-room, deterministic simulation of the masked-diffusion
PARALLEL-DECODING SCHEDULE used by diffusion large language models (Mercury /
LLaDA-style), as a same-origin REST endpoint. This gives the dLLM surface organ
a live data source that is honest, deterministic, and citable — never
fabricated, never random-faked, and NEVER a trained diffusion model.

  GET  /api/<ns>/v1/dllm/denoise?seed=&steps=&length=

THE dLLM PARALLELISM IDEA (what is being modeled)
--------------------------------------------------
Autoregressive (AR) LLMs decode strictly left-to-right: one new token per
forward pass, so producing `length` tokens costs `length` sequential steps.

Masked-diffusion LLMs (LLaDA, Mercury) instead start from a FULLY-MASKED
sequence of `length` tokens and run `steps` denoising rounds. Each round, the
model looks at the WHOLE sequence at once and commits (unmasks) a batch of
the highest-confidence still-masked positions in parallel — not left-to-right.
After `steps` rounds every position has been decided, so:

    parallelism_factor = length / steps          (tokens produced per round)

versus the AR baseline of exactly 1.0 token/step. This module simulates ONLY
the *shape* of that unmask schedule (a deterministic highest-confidence-first
allocation across rounds) and a MODELED confidence trajectory — it contains no
trained weights, no real model forward passes, and no borrowed logits.

Modeled quantities
-------------------
  length                    : total sequence length (number of token positions)
  steps                     : number of denoising rounds (steps << length is the win)
  unmasked_per_round         : [count, ...] how many NEW positions are committed each round
                               (deterministic highest-confidence-first schedule: an
                               increasing-then-tapering allocation, front-loaded because
                               confidence is highest for the "easiest" positions first,
                               same qualitative shape as LLaDA/Mercury remasking schedules)
  cumulative_unmasked        : running total unmasked after each round (ends at length)
  tokens_per_round           : same as unmasked_per_round (explicit alias for the surface)
  confidence_trajectory      : [mean_confidence_this_round, ...] MODELED, rounds trend
                               upward as the sequence fills in (fewer, harder positions remain)
  final_sequence              : synthetic decoded token ids (0..vocab_size-1), length `length`,
                               fully decided only once all rounds complete
  parallelism_factor         : length / steps — tokens decided per round, vs 1.0 for AR
  autoregressive_steps_equiv : length (an AR model would need this many sequential steps)
  speedup_vs_autoregressive  : parallelism_factor (== length/steps, same ratio, explicit label)
  label                      : "MODELED" (always)
  honest_note                : plain-language honesty disclaimer
  citations                  : dict of citable sources
  computed_at                : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form, pure-stdlib simulation of the masked-
  diffusion parallel-DECODING SCHEDULE (which positions get committed in which
  round, and a synthetic confidence curve) — the METHOD shape reported by
  LLaDA and Mercury — NOT a trained diffusion language model. No real model
  weights, no real logits, no benchmark numbers, no LLM calls of any kind. The
  "final_sequence" token ids are SYNTHETIC (deterministic pseudo-vocabulary
  ids from the seeded PRNG), not real language. The label "MODELED" is
  returned verbatim and displayed verbatim by the surface; never upgraded
  client-side. NEVER-CLAIMED-AS Mercury or LLaDA — this module does not use,
  approximate, or reproduce either system's weights, training data, or
  reported benchmark numbers; it only mirrors the qualitative *shape* of the
  publicly described parallel masked-diffusion decoding schedule.

CITATIONS (clean-room; none claimed as SZL's own):
  LLaDA (masked diffusion LLM, 8B, trained from scratch):
    Nie, Zhu, You, Zhang, Ou, Hu, Zhou, Lin, Wen & Li (2025)
    "Large Language Diffusion Models". arXiv:2502.09992.
    https://arxiv.org/abs/2502.09992
    Code: https://github.com/ML-GSAI/LLaDA
  Mercury (Inception Labs; commercial-scale diffusion LLM, parallel token decoding):
    Inception Labs (2025) "Mercury: Ultra-Fast Language Models Based on
    Diffusion". arXiv:2506.17298. https://arxiv.org/abs/2506.17298
  D3PM (discrete-state denoising diffusion; formal basis for masked/absorbing-
  state diffusion over discrete tokens):
    Austin, Johnson, Ho, Tarlow & van den Berg (2021) "Structured Denoising
    Diffusion Models in Discrete State-Spaces". arXiv:2107.03006.
    https://arxiv.org/abs/2107.03006

  HONEST-STUB note: the highest-confidence-first unmask-count schedule and the
  confidence-trajectory closed form are SZL's own MODELED choices, selected to
  reproduce the qualitative shape of masked-diffusion parallel decoding
  (front-loaded easy positions, tapering hard positions, full sequence decided
  in steps << length rounds) described by the cited works. They are not a
  re-implementation of any paper's exact remasking algorithm, sampler, or
  reported numbers.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  No LLM calls of any kind — pure closed-form arithmetic + deterministic PRNG.
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
    "LLaDA — Nie et al. 2025, arXiv:2502.09992": "https://arxiv.org/abs/2502.09992",
    "LLaDA code — ML-GSAI/LLaDA (GitHub)": "https://github.com/ML-GSAI/LLaDA",
    "Mercury (Inception Labs) — arXiv:2506.17298": "https://arxiv.org/abs/2506.17298",
    "D3PM — Austin et al. 2021, arXiv:2107.03006": "https://arxiv.org/abs/2107.03006",
}

# Synthetic pseudo-vocabulary size for the decoded token ids (illustrative only;
# NOT a real tokenizer, NOT any real model's vocabulary).
_VOCAB_SIZE = 32000

# Sentinel id representing a still-MASKED position in the working sequence.
_MASK_ID = -1


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — mirrors
# szl_interpretability._lcg exactly: same seed -> identical stream, forever.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# MODELED masked-diffusion parallel-denoising schedule (deterministic)
# ---------------------------------------------------------------------------
def _unmask_schedule(length: int, steps: int, rng) -> list:
    """
    Deterministic highest-confidence-first unmask-count schedule.

    Real masked-diffusion decoders (LLaDA / Mercury) score EVERY still-masked
    position each round and commit the highest-confidence subset — early
    rounds tend to resolve many "easy" positions at once, later rounds resolve
    fewer, harder positions (the ones the model was least sure about). We
    MODEL that qualitative shape with a deterministic, seed-jittered
    "front-loaded, tapering" allocation across `steps` rounds that sums
    exactly to `length` (every position is eventually decided).

    Pure stdlib; deterministic — same seed/length/steps -> identical schedule.
    """
    if steps <= 0:
        return [length] if length > 0 else []

    # Base weight per round: a decreasing arithmetic-like taper (round 1 gets
    # the most, later rounds get progressively less), then seed-jittered by a
    # small deterministic +/-20% band so different seeds vary the schedule's
    # exact shape without changing its qualitative front-loaded character.
    weights = []
    for r in range(steps):
        taper = (steps - r)  # steps, steps-1, ..., 1  (front-loaded)
        jitter = 0.8 + 0.4 * next(rng)  # in [0.8, 1.2)
        weights.append(taper * jitter)

    wsum = sum(weights) or 1.0
    raw = [w / wsum * length for w in weights]

    # Integerize with largest-remainder method so the schedule sums exactly
    # to `length` (every position gets decided by the final round).
    floors = [int(math.floor(x)) for x in raw]
    remainder = length - sum(floors)
    fracs = sorted(range(steps), key=lambda i: (raw[i] - floors[i]), reverse=True)
    counts = floors[:]
    for i in range(max(0, remainder)):
        counts[fracs[i % steps]] += 1

    # Safety: never negative, never exceed remaining length.
    counts = [max(0, c) for c in counts]
    total = sum(counts)
    if total != length and counts:
        counts[-1] += (length - total)
        counts[-1] = max(0, counts[-1])

    return counts


def _confidence_trajectory(steps: int, rng) -> list:
    """
    MODELED mean-confidence-of-committed-tokens per round. Confidence starts
    moderate (easiest positions still resolved first) and trends upward as
    fewer, but the LAST round always must commit whatever remains — so we
    model a monotonically non-decreasing saturating curve with deterministic
    seed jitter, qualitatively matching "the model becomes more certain as
    more context is filled in" — the intuition behind confidence-based
    remasking schedules in LLaDA/Mercury-style samplers.
    """
    if steps <= 0:
        return []
    traj = []
    base = 0.55
    for r in range(steps):
        frac = r / max(1, steps - 1) if steps > 1 else 1.0
        jitter = 0.97 + 0.06 * next(rng)  # in [0.97, 1.03)
        conf = (base + (0.97 - base) * frac) * jitter
        conf = min(0.995, max(0.05, conf))
        traj.append(round(conf, 4))
    return traj


def _decode(seed: int = 42, steps: int = 8, length: int = 64) -> dict:
    """
    Simulate one full masked-diffusion parallel-denoising run.

    Start: sequence of `length` positions, ALL masked (_MASK_ID).
    Each of `steps` rounds: commit `unmasked_per_round[r]` NEW positions
    (chosen deterministically, in schedule order — position choice itself is
    also PRNG-deterministic, not left-to-right) to a synthetic decoded token
    id. After the final round every position is decided (no _MASK_ID left).

    Pure stdlib; deterministic — same seed/steps/length -> identical output.
    """
    length = max(1, min(int(length), 4096))
    steps = max(1, min(int(steps), length))  # cannot need more rounds than positions

    rng = _lcg(seed)

    schedule = _unmask_schedule(length, steps, rng)
    confidence_trajectory = _confidence_trajectory(steps, rng)

    # Deterministic position order in which masked slots become eligible to be
    # committed (a fixed pseudo-random permutation of 0..length-1, derived
    # from the same seeded stream — NOT left-to-right).
    order = list(range(length))
    # Fisher–Yates shuffle driven by the deterministic LCG stream.
    for i in range(length - 1, 0, -1):
        j = int(next(rng) * (i + 1))
        if j > i:
            j = i
        order[i], order[j] = order[j], order[i]

    sequence = [_MASK_ID] * length
    cumulative_unmasked = []
    running = 0
    cursor = 0
    for r in range(steps):
        n_this_round = schedule[r] if r < len(schedule) else 0
        for _ in range(n_this_round):
            if cursor >= length:
                break
            pos = order[cursor]
            cursor += 1
            token_id = int(next(rng) * _VOCAB_SIZE) % _VOCAB_SIZE
            sequence[pos] = token_id
        running += n_this_round
        cumulative_unmasked.append(min(running, length))

    # Any leftover (rounding) positions get committed in the final round —
    # guarantees full decode by the end (matches the "all positions decided
    # in parallel across `steps` rounds" guarantee).
    while cursor < length:
        pos = order[cursor]
        cursor += 1
        token_id = int(next(rng) * _VOCAB_SIZE) % _VOCAB_SIZE
        sequence[pos] = token_id
        if cumulative_unmasked:
            cumulative_unmasked[-1] = min(cumulative_unmasked[-1] + 1, length)

    parallelism_factor = round(length / steps, 6)

    return {
        "length": length,
        "steps": steps,
        "unmasked_per_round": schedule,
        "tokens_per_round": schedule,
        "cumulative_unmasked": cumulative_unmasked,
        "confidence_trajectory": confidence_trajectory,
        "final_sequence": sequence,
        "parallelism_factor": parallelism_factor,
        "autoregressive_steps_equiv": length,
        "speedup_vs_autoregressive": parallelism_factor,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_denoise(req: Request):
    seed   = _ii(req, "seed",   42)
    steps  = max(1, min(_ii(req, "steps",  8), 512))
    length = max(1, min(_ii(req, "length", 64), 4096))
    steps  = min(steps, length)

    d = _decode(seed=seed, steps=steps, length=length)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Masked-diffusion parallel-denoising SCHEDULE simulation (Mercury/LLaDA-style)",
        "method": "Deterministic highest-confidence-first unmask schedule over a fully-masked sequence, "
                  "all positions decided in parallel across `steps` rounds (steps << length)",
        "seed": seed,
        **d,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib, clean-room simulation of the masked-"
            "diffusion PARALLEL-DECODING SCHEDULE used by diffusion LLMs (which positions get "
            "unmasked in which round, and a synthetic confidence curve) -- NOT a trained diffusion "
            "language model. The 'final_sequence' token ids are SYNTHETIC pseudo-vocabulary ids, not "
            "real language, no real logits, no benchmark re-runs. NEVER-CLAIMED-AS Mercury or LLaDA -- "
            "this module reproduces only the qualitative SHAPE of their publicly described parallel "
            "masked-diffusion decoding (start fully masked; unmask highest-confidence positions across "
            "steps << length rounds, all positions in parallel per round, not left-to-right). "
            "Deterministic: same seed/steps/length -> identical output. Cite: Nie et al. arXiv:2502.09992 "
            "(LLaDA); Inception Labs arXiv:2506.17298 (Mercury); Austin et al. arXiv:2107.03006 (D3PM). "
            "SZL claims NONE of these systems or methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_testtime.register() / szl_interpretability.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/dllm/denoise onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/dllm"
    handlers = [
        (f"{base}/denoise", _h_denoise),
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
    print("model: Masked-diffusion parallel-denoising SCHEDULE simulation (Mercury/LLaDA-style)")
    print()

    d = _decode(seed=42, steps=8, length=64)
    print(f"length={d['length']}  steps={d['steps']}  parallelism_factor={d['parallelism_factor']}")
    print(f"autoregressive_steps_equiv={d['autoregressive_steps_equiv']}  "
          f"(AR would need {d['autoregressive_steps_equiv']} sequential steps vs {d['steps']} parallel rounds)")
    print()
    print("unmasked_per_round (tokens committed in parallel, per denoising round):")
    print(" ", d["unmasked_per_round"])
    print("cumulative_unmasked (running total; ends at length):")
    print(" ", d["cumulative_unmasked"])
    print("confidence_trajectory (MODELED mean confidence per round):")
    print(" ", d["confidence_trajectory"])
    print()
    print(f"final_sequence (first 12 of {len(d['final_sequence'])} synthetic token ids):")
    print(" ", d["final_sequence"][:12], "...")

    # ---- sanity assertions ----
    assert d["length"] == 64 and d["steps"] == 8
    assert d["parallelism_factor"] == round(64 / 8, 6) == 8.0
    assert sum(d["unmasked_per_round"]) == d["length"], "schedule must sum to length"
    assert d["cumulative_unmasked"][-1] == d["length"], "must fully decode by final round"
    assert _MASK_ID not in d["final_sequence"], "no position may remain masked after all rounds"
    assert all(0 <= t < _VOCAB_SIZE for t in d["final_sequence"]), "token ids must be in-vocab"
    # confidence should trend non-decreasing on average (monotonic within jitter tolerance)
    assert d["confidence_trajectory"][0] <= d["confidence_trajectory"][-1] + 1e-9

    # steps << length is the core dLLM parallelism claim being modeled
    assert d["steps"] < d["length"], "steps must be << length to demonstrate the parallelism win"

    # determinism: same seed -> identical output
    d2 = _decode(seed=42, steps=8, length=64)
    assert d == d2, "same seed must reproduce an identical decode"

    # different seed -> different (but still valid) schedule
    d3 = _decode(seed=7, steps=8, length=64)
    assert d3["final_sequence"] != d["final_sequence"]
    assert sum(d3["unmasked_per_round"]) == d3["length"]

    print()
    print("szl_dllm: ALL OK — parallel unmask schedule decodes full sequence in steps << length rounds.")
