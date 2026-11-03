# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_moe.py — SZL MoE Sparse-Upcycling Router Simulator endpoint.

Exposes a MODELED deterministic top-K softmax router — the core dispatch
mechanism of Mixture-of-Experts (MoE) transformer layers, and the thing
"sparse upcycling" hands off to when a dense checkpoint is converted into a
sparsely-activated model — as a same-origin REST endpoint, so the MoE-router
surface organ has a live data source that is honest, deterministic, and
citable — never fabricated, never a trained checkpoint, never claimed as any
named production model's router.

  GET  /api/<ns>/v1/moe/route?seed=&tokens=&experts=&topk=

Returned JSON fields
---------------------
  label                 : "MODELED" (always — this is a simulation, not a trained model)
  model                 : name of the mechanism being simulated
  seed                  : RNG seed used (deterministic; same seed -> same run)
  tokens                : number of synthetic tokens T routed
  experts               : number of experts N in the simulated layer
  topk                  : number of experts activated per token (sparse top-K)
  routing_table         : sample of per-token routing decisions (token idx, chosen
                           expert ids, softmax weights) — truncated to a display cap
  expert_load_counts    : per-expert count of tokens routed to it (sum = tokens*topk)
  load_balance_cv       : coefficient of variation (stddev/mean) of expert_load_counts;
                           0.0 = perfectly balanced load across experts, larger = more
                           skewed ("hot expert" / load-imbalance) routing
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic closed-form simulation of a TOP-K SOFTMAX ROUTER — the
  gating mechanism used to dispatch tokens to a sparse subset of experts in a
  Mixture-of-Experts (MoE) layer — run over T synthetic tokens against N fixed
  "expert identity vectors" with a pure-stdlib deterministic LCG PRNG. Router logits
  are a deterministic dot-product between each token's embedding and each expert's
  identity vector; softmax + top-K selection are hand-rolled with math.exp/sum (no
  numpy, no torch, no trained weights of any kind). load_balance_cv is a MODELED
  descriptive statistic of the resulting expert_load_counts distribution — it
  ILLUSTRATES the load-balancing problem that sparse-upcycled and from-scratch MoE
  routers must solve, but it does NOT reproduce, benchmark, or claim parity with any
  named production router (not DeepSeekMoE, not Gemma-MoE, not GShard/Switch/Mixtral,
  not any other trained MoE). The label "MODELED" is returned verbatim and displayed
  verbatim by the surface; it is never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Sparse Upcycling — Komatsuzaki et al. (2023) "Sparse Upcycling: Training
    Mixture-of-Experts from Dense Checkpoints". ICLR 2023. arXiv:2212.05055.
    https://arxiv.org/abs/2212.05055
    Introduces sparse upcycling: initializing a sparsely-activated MoE model's
    experts from copies of a dense checkpoint's feed-forward weights, with a
    freshly (near-)randomly initialized router, then continuing training so the
    router and experts differentiate. This organ's router-load-balancing view is a
    stylized illustration of exactly the mechanism (top-K softmax router dispatch)
    that upcycled experts are routed through post-conversion.
  DeepSeekMoE — Dai et al. (2024) "DeepSeekMoE: Towards Ultimate Expert
    Specialization in Mixture-of-Experts Language Models". arXiv:2401.06066.
    https://arxiv.org/abs/2401.06066
    Fine-grained expert segmentation + shared-expert isolation for a sparse MoE
    router; motivates why load-balance across experts (this organ's
    load_balance_cv) matters for expert specialization quality. This organ does
    NOT reproduce DeepSeekMoE's architecture, weights, or reported numbers.
  Expert Upcycling — Dwivedi, Gupta, Varshney, Jayarao, Yin, Chilimbi, Huang (2026)
    "Expert Upcycling: Shifting the Compute-Efficient Frontier of Mixture-of-Experts"
    (preprint); code: https://github.com/amazon-science/expert-upcycling
    Expert Upcycling grows an existing E-expert MoE to mE experts mid-training via
    expert duplication + router extension while holding top-K routing fixed — the
    router-extension step is exactly the kind of top-K softmax dispatch this organ
    illustrates. SZL claims no affiliation with, and does not reproduce, this codebase.
  HONEST-STUB note: router logits, softmax weights, and load counts are all
    MODELED deterministic-arithmetic outputs of this file's own small pure-stdlib
    scan — NOT measured from, sampled from, or fitted to any trained MoE checkpoint.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (no numpy, no `random` module — deterministic LCG
  PRNG). Deterministic with seed. 0 runtime CDN. NEVER claimed as DeepSeekMoE,
  Gemma-MoE, or any production router.
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
    "Sparse Upcycling — Komatsuzaki et al. (2023) arXiv:2212.05055": "https://arxiv.org/abs/2212.05055",
    "DeepSeekMoE — Dai et al. (2024) arXiv:2401.06066": "https://arxiv.org/abs/2401.06066",
    "Expert Upcycling (amazon-science, code)": "https://github.com/amazon-science/expert-upcycling",
}


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no `random` module)
# ---------------------------------------------------------------------------
class _LCG:
    """Numerical-Recipes-style 32-bit linear congruential generator.
    Deterministic: same seed -> identical stream. Pure stdlib arithmetic only."""

    _A = 1664525
    _C = 1013904223
    _M = 2 ** 32

    def __init__(self, seed: int = 42):
        self._state = int(seed) % self._M

    def next_uint(self) -> int:
        self._state = (self._A * self._state + self._C) % self._M
        return self._state

    def uniform(self) -> float:
        """Uniform float in [0, 1)."""
        return self.next_uint() / self._M

    def signed_unit(self) -> float:
        """Uniform float in [-1, 1)."""
        return self.uniform() * 2.0 - 1.0


# ---------------------------------------------------------------------------
# Deterministic embedding / expert-identity vector construction
# ---------------------------------------------------------------------------
_D_MODEL = 32  # fixed toy embedding width for the router's dot-product logits


def _make_expert_vectors(rng: _LCG, n_experts: int, d_model: int = _D_MODEL):
    """Each expert has a fixed, deterministic 'identity vector' in R^d_model
    (stand-in for a trained router weight column). Pure stdlib, seeded."""
    return [[rng.signed_unit() for _ in range(d_model)] for _ in range(n_experts)]


def _make_token_vectors(rng: _LCG, n_tokens: int, d_model: int = _D_MODEL):
    """Each synthetic token has a deterministic embedding in R^d_model.
    Pure stdlib, seeded — NOT drawn from any real tokenizer/model."""
    return [[rng.signed_unit() for _ in range(d_model)] for _ in range(n_tokens)]


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Pure-Python softmax (math.exp/sum only — no numpy)
# ---------------------------------------------------------------------------
def _softmax(logits):
    m = max(logits)  # numerically-stable shift
    exps = [math.exp(v - m) for v in logits]
    s = sum(exps)
    return [e / s for e in exps]


# ---------------------------------------------------------------------------
# Top-K softmax router: for each token, compute logits vs every expert
# identity vector, softmax over ALL experts, then select the top-K by weight
# (mirrors standard MoE routers: e.g. Switch/GShard-style top-K gating).
# ---------------------------------------------------------------------------
def _route_tokens(seed: int, n_tokens: int, n_experts: int, topk: int):
    rng = _LCG(seed)
    expert_vecs = _make_expert_vectors(rng, n_experts)
    token_vecs = _make_token_vectors(rng, n_tokens)

    expert_load_counts = [0] * n_experts
    routing_table = []

    for t_idx, tvec in enumerate(token_vecs):
        logits = [_dot(tvec, evec) for evec in expert_vecs]
        weights = _softmax(logits)

        # top-K selection by softmax weight (descending); ties broken by lower
        # expert index for full determinism.
        ranked = sorted(range(n_experts), key=lambda i: (-weights[i], i))
        chosen = ranked[:topk]

        for e in chosen:
            expert_load_counts[e] += 1

        routing_table.append({
            "token": t_idx,
            "chosen_experts": chosen,
            "weights": [round(weights[e], 6) for e in chosen],
        })

    return routing_table, expert_load_counts


def _coefficient_of_variation(counts):
    """Population stddev / mean of expert_load_counts (pure stdlib, no numpy).
    0.0 = perfectly balanced load; larger = more skewed ('hot expert') routing.
    Undefined (returns 0.0) if mean is 0 (e.g. n_experts > tokens*topk edge case
    is impossible here since every token always selects exactly topk experts,
    but we guard anyway for topk=0 degenerate input)."""
    n = len(counts)
    if n == 0:
        return 0.0
    mean = sum(counts) / n
    if mean == 0:
        return 0.0
    variance = sum((c - mean) ** 2 for c in counts) / n
    stddev = math.sqrt(variance)
    return round(stddev / mean, 6)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
_ROUTING_TABLE_SAMPLE_CAP = 40  # cap the sample returned in the JSON payload


def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_route(req: Request):
    seed    = _ii(req, "seed", 42)
    tokens  = max(1, min(_ii(req, "tokens", 64), 2048))
    experts = max(2, min(_ii(req, "experts", 8), 128))
    topk    = max(1, min(_ii(req, "topk", 2), experts))

    routing_table, expert_load_counts = _route_tokens(
        seed=seed, n_tokens=tokens, n_experts=experts, topk=topk,
    )
    cv = _coefficient_of_variation(expert_load_counts)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Deterministic top-K softmax MoE router (dot-product logits vs "
                  "fixed expert identity vectors; pure-Python softmax; top-K dispatch)",
        "seed":    seed,
        "tokens":  tokens,
        "experts": experts,
        "topk":    topk,
        "routing_table": routing_table[:_ROUTING_TABLE_SAMPLE_CAP],
        "routing_table_sample_note": (
            f"showing first {min(_ROUTING_TABLE_SAMPLE_CAP, tokens)} of {tokens} "
            "routed tokens"
        ),
        "expert_load_counts": expert_load_counts,
        "load_balance_cv": cv,
        "honest_note": (
            "MODELED: deterministic top-K softmax router simulation illustrating "
            "sparse-upcycling load balance; NOT a trained MoE; NEVER-CLAIMED-AS "
            "DeepSeekMoE/Gemma-MoE/any production router. Router logits are a "
            "deterministic dot-product between seeded synthetic token embeddings and "
            "seeded synthetic expert identity vectors; softmax and top-K selection are "
            "hand-rolled pure-Python (math.exp/sum), no numpy, no torch, no trained "
            "weights. load_balance_cv is the coefficient of variation (population "
            "stddev/mean) of expert_load_counts: 0.0 = perfectly balanced routing "
            "across experts, larger values indicate 'hot expert' load imbalance — the "
            "exact problem sparse-upcycled and from-scratch MoE routers must solve. "
            "Deterministic: same seed/tokens/experts/topk -> identical run. Pure "
            "stdlib LCG PRNG (no numpy, no random module). Cite also: Komatsuzaki et "
            "al. arXiv:2212.05055 (Sparse Upcycling); Dai et al. arXiv:2401.06066 "
            "(DeepSeekMoE); github.com/amazon-science/expert-upcycling (Expert "
            "Upcycling). SZL claims NONE of these methods, models, or codebases as "
            "its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_ssm.register() / szl_testtime.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/moe/route onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/moe"
    handlers = [
        (f"{base}/route", _h_route),
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
    routing_table, expert_load_counts = _route_tokens(
        seed=42, n_tokens=64, n_experts=8, topk=2,
    )
    cv = _coefficient_of_variation(expert_load_counts)
    print("tokens: 64, experts: 8, topk: 2, seed: 42")
    print("expert_load_counts:", expert_load_counts)
    print("load_balance_cv:", cv)
    print("sample routing_table[:3]:", routing_table[:3])
    print("label: MODELED")

    # determinism check: same seed/params -> identical output
    routing_table2, expert_load_counts2 = _route_tokens(
        seed=42, n_tokens=64, n_experts=8, topk=2,
    )
    assert expert_load_counts == expert_load_counts2, "determinism check FAILED"
    assert routing_table == routing_table2, "determinism check FAILED"
    print("determinism check: OK (identical output for identical seed/params)")

    # a second seed/shape combo, to show the shape generalizes
    rt2, counts2 = _route_tokens(seed=7, n_tokens=128, n_experts=16, topk=4)
    print(f"[seed=7, tokens=128, experts=16, topk=4] load_balance_cv="
          f"{_coefficient_of_variation(counts2)} sum_counts={sum(counts2)} "
          f"expected_sum={128*4}")
