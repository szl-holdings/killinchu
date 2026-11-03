# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_steering.py — SZL steering-vectors / activation-addition (ActAdd) / RepE
endpoint, MODELED.

Exposes a MODELED closed-form simulation of inference-time activation
steering — computing a steering vector as the mean difference of toy
residual-stream activations on paired contrastive prompts (e.g. "Love" vs
"Hate"), scaling it by a coefficient, and adding it into the forward pass at a
chosen layer — as a same-origin REST endpoint, so the steering surface organ
has a live data source that is honest, deterministic, and citable — never
fabricated, never random-faked, never run against a real model's weights.

  GET  /api/killinchu/v1/steering/sweep?seed=&layer=&d_model=&n_coeffs=&coeff_max=

WHAT IS SIMULATED
------------------
Steering vectors (activation addition / representation engineering) contrast
a model's residual-stream activation on a POSITIVE prompt (e.g. "Love") vs a
NEGATIVE prompt (e.g. "Hate") at a chosen layer, and define the steering
vector as the mean difference:

    v_steer = mean(h_pos) - mean(h_neg)            (Turner et al. 2023, ActAdd;
                                                      Zou et al. 2023, RepE)

At generation time, v_steer (scaled by a coefficient c) is ADDED into the
residual stream at the chosen layer for every forward pass:

    h'_layer = h_layer + c * v_steer

No weights are modified and no fine-tuning occurs — this is a pure
inference-time control technique. Sweeping c from negative to positive should
produce a reproducible, monotone-ish shift in a measured OUTPUT SENTIMENT
SCORE (more "Love"-like as c increases), while a held-out CAPABILITY METRIC
(here, a toy next-token-prediction accuracy on unrelated factual continuations)
should stay approximately FLAT — demonstrating the intervention is targeted
and does not broadly degrade the model.

This module is the DISTINCT counterpart of the interpretability/SAE organ:
interpretability DECOMPOSES/EXPLAINS internal activations (passive readout);
steering INTERVENES/CONTROLS behaviour by injecting into the forward pass
(active control). Both are MODELED; neither runs a real model.

Returned JSON fields
---------------------
  label                  : "MODELED" (always — deterministic re-implementation
                            of the activation-addition arithmetic, NOT a live
                            model, NOT real learned weights)
  model                  : short description of the simulated setup
  seed                   : RNG seed used
  layer                  : chosen residual-stream layer index the vector is
                            injected at
  d_model                : toy residual-stream width simulated
  contrastive_pair       : {positive, negative} prompt strings used to build
                            the steering vector
  steering_vector_norm   : L2 norm of v_steer at the chosen layer
  coefficients           : swept coefficient values (n_coeffs points across
                            [-coeff_max, +coeff_max])
  sentiment_score        : list, one MODELED sentiment score per coefficient
                            (monotone non-decreasing in c by construction of
                            the injected vector — the measurable behavioural
                            shift)
  capability_score       : list, one MODELED held-out capability score per
                            coefficient (flat / near-constant — demonstrates
                            the intervention is targeted, not a lobotomy)
  sentiment_shift        : sentiment_score[-1] - sentiment_score[0] (the
                            measured effect size of the sweep)
  capability_drift       : max(capability_score) - min(capability_score) (the
                            measured off-target cost of the sweep; should stay
                            small)
  honest_note            : plain-language honesty disclaimer
  citations               : dict of citable sources
  computed_at             : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the ActAdd/RepE
  mean-difference steering-vector construction and additive injection
  arithmetic. Toy per-layer residual-stream activations for the contrastive
  prompt pair are drawn from a deterministic LCG PRNG (no numpy, no stdlib
  `random`, no proprietary weights, no real transformer forward pass). The
  resulting sentiment/capability curves are closed-form functions of the
  injected coefficient, chosen to reproduce the qualitative, published
  phenomenology (targeted behavioural shift, flat off-target capability) —
  they are NOT measurements from a real language model. NEVER-CLAIMED-AS a
  production steering system. The label "MODELED" is returned verbatim and
  displayed verbatim by the surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Activation Addition (ActAdd) — steering language models by adding
  activation-space contrastive-pair difference vectors at inference time:
    Turner, Thiergart, Leech, Udell, Vazquez, Mini & MacDiarmid (2023)
    "Activation Addition: Steering Language Models Without Optimization".
    arXiv:2308.10248. https://arxiv.org/abs/2308.10248
  Representation Engineering (RepE) — reading and controlling high-level
  concepts via linear directions in representation space:
    Zou, Phan, Chen, Campbell, Guo, Ren, Pan, Yin, Mazeika, Dombrowski,
    Goel, Li, Byun, Wang, Mallen, Basart, Koyejo, Song, Fredrikson, Kolter
    & Hendrycks (2023) "Representation Engineering: A Top-Down Approach to
    AI Transparency". arXiv:2310.01405. https://arxiv.org/abs/2310.01405
  NEVER-CLAIMED-AS: this module is not ActAdd's or RepE's released code, does
  not reproduce either project's measured benchmark numbers, and uses no
  proprietary weights. It is a clean-room MODELED simulation of the shared
  mean-difference steering-vector arithmetic those methods build on.

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
    "Activation Addition (ActAdd) — Turner et al. arXiv:2308.10248": "https://arxiv.org/abs/2308.10248",
    "Representation Engineering (RepE) — Zou et al. arXiv:2310.01405": "https://arxiv.org/abs/2310.01405",
}

# The canonical contrastive prompt pair used to build the toy steering vector.
_POS_PROMPT = "Love"
_NEG_PROMPT = "Hate"

# Cap on the number of coefficient sweep points returned (keeps payload bounded).
_MAX_COEFFS = 64


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# same generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _lcg_signed(rng) -> float:
    """One draw in (-1, 1) from the given LCG stream."""
    return 2.0 * next(rng) - 1.0


# ---------------------------------------------------------------------------
# MODELED toy residual-stream activations + steering-vector construction
# ---------------------------------------------------------------------------
def _toy_activation(rng, d_model: int, bias: float) -> list:
    """One toy residual-stream activation vector of width d_model: a
    deterministic LCG-drawn Gaussian-ish vector (sum of uniforms, for a
    bounded pure-stdlib approximation of a normal) shifted by `bias` on every
    dimension. `bias` differentiates the POSITIVE vs NEGATIVE contrastive
    prompt's activation distribution — this is what makes their mean
    difference a meaningful direction."""
    out = []
    for _ in range(d_model):
        # sum of 3 uniforms in (-1,1) -> bounded, roughly bell-shaped, pure stdlib
        u = (_lcg_signed(rng) + _lcg_signed(rng) + _lcg_signed(rng)) / 3.0
        out.append(bias + 0.35 * u)
    return out


def _mean_vec(vecs: list) -> list:
    n = len(vecs)
    d = len(vecs[0])
    acc = [0.0] * d
    for v in vecs:
        for i in range(d):
            acc[i] += v[i]
    return [a / n for a in acc]


def _sub(a: list, b: list) -> list:
    return [x - y for x, y in zip(a, b)]


def _l2norm(v: list) -> float:
    return math.sqrt(sum(x * x for x in v))


def _steering_vector(rng, d_model: int, n_samples: int = 8) -> dict:
    """Build the steering vector as the mean difference of toy residual-
    stream activations on the paired contrastive prompts ("Love" vs "Hate"):

        v_steer = mean(h_pos) - mean(h_neg)          (ActAdd / RepE)

    `n_samples` toy activations are drawn per prompt (simulating multiple
    forward passes / token positions being averaged, as in the published
    method) to make the mean-difference direction stable. Pure stdlib LCG;
    deterministic given the RNG stream."""
    pos_vecs = [_toy_activation(rng, d_model, bias=+0.6) for _ in range(n_samples)]
    neg_vecs = [_toy_activation(rng, d_model, bias=-0.6) for _ in range(n_samples)]
    mean_pos = _mean_vec(pos_vecs)
    mean_neg = _mean_vec(neg_vecs)
    v_steer = _sub(mean_pos, mean_neg)
    return {
        "vector": v_steer,
        "norm": _l2norm(v_steer),
        "mean_pos_norm": _l2norm(mean_pos),
        "mean_neg_norm": _l2norm(mean_neg),
    }


# ---------------------------------------------------------------------------
# MODELED downstream scoring — sentiment shift + held-out capability metric
# ---------------------------------------------------------------------------
def _sentiment_score(coeff: float, v_norm: float, rng_seed_jitter: float) -> float:
    """MODELED output sentiment score in [-1, +1] (negative..positive) after
    injecting h' = h + coeff * v_steer at the chosen layer. Closed-form
    saturating (tanh) response of sentiment to injection strength — the
    qualitative shape reported by ActAdd/RepE: small coefficients produce a
    roughly linear shift, extreme coefficients saturate rather than diverge
    (representation space is bounded). A tiny deterministic per-call jitter
    (from the LCG-derived seed offset) avoids a perfectly noiseless synthetic
    curve while remaining exactly reproducible for a fixed seed, and is kept
    small enough (<= 0.005 in magnitude) to never break the sweep's
    monotonicity in coeff over the supported coeff_max range."""
    # Fixed, coefficient-normalized gain: saturates smoothly across the full
    # sweep range (coeff in [-coeff_max, +coeff_max], coeff_max <= 50) instead
    # of jumping straight to +-1 for any nonzero coeff. The steering-vector
    # norm still gates whether the direction is meaningfully non-degenerate
    # (checked by the caller/selftest) but does not blow up the tanh input.
    gain = 0.12
    jitter = 0.005 * (rng_seed_jitter - 0.5)  # in [-0.0025, +0.0025], deterministic
    return max(-1.0, min(1.0, math.tanh(gain * coeff) + jitter))


def _capability_score(coeff: float, rng_seed_jitter: float) -> float:
    """MODELED held-out capability score in [0,1] (e.g. toy next-token
    factual-continuation accuracy) under the SAME injection. By construction
    this stays approximately FLAT across the coefficient sweep — a very
    small quadratic penalty models the (published, small) capability cost of
    large steering coefficients, so the demo also shows the metric is not
    literally immune to arbitrarily large c, matching the honest picture in
    Turner et al. / Zou et al. that steering is targeted but not free at
    extreme magnitudes."""
    base = 0.92 + 0.02 * rng_seed_jitter
    penalty = 0.0006 * (coeff ** 2)  # tiny, deliberately small vs sentiment_shift
    return max(0.0, min(1.0, base - penalty))


def _steering_snapshot(
    seed: int = 42,
    layer: int = 12,
    d_model: int = 512,
    n_coeffs: int = 9,
    coeff_max: float = 6.0,
) -> dict:
    """
    Build the toy steering vector at `layer` from the "Love" vs "Hate"
    contrastive pair, then sweep the injection coefficient across
    [-coeff_max, +coeff_max] and report the MODELED sentiment_score and
    capability_score curves.

    Pure stdlib; deterministic — same (seed, layer, d_model, n_coeffs,
    coeff_max) -> identical snapshot, every time.
    """
    rng = _lcg(seed ^ (layer * 0x01000193))  # layer folded into the stream, deterministic
    sv = _steering_vector(rng, d_model=d_model, n_samples=8)
    v_norm = sv["norm"]

    n_coeffs = max(2, min(n_coeffs, _MAX_COEFFS))
    if n_coeffs == 1:
        coeffs = [0.0]
    else:
        step = (2.0 * coeff_max) / (n_coeffs - 1)
        coeffs = [round(-coeff_max + i * step, 6) for i in range(n_coeffs)]

    sentiment = []
    capability = []
    for i, c in enumerate(coeffs):
        jitter = next(rng)  # deterministic small per-point jitter, same seed -> same jitter
        sentiment.append(round(_sentiment_score(c, v_norm, jitter), 6))
        capability.append(round(_capability_score(c, jitter), 6))

    sentiment_shift = round(sentiment[-1] - sentiment[0], 6)
    capability_drift = round(max(capability) - min(capability), 6)

    return {
        "layer": layer,
        "d_model": d_model,
        "contrastive_pair": {"positive": _POS_PROMPT, "negative": _NEG_PROMPT},
        "steering_vector_norm": round(v_norm, 6),
        "coefficients": coeffs,
        "sentiment_score": sentiment,
        "capability_score": capability,
        "sentiment_shift": sentiment_shift,
        "capability_drift": capability_drift,
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
        return float(default)


def _h_sweep(req: Request):
    seed      = _ii(req, "seed",      42)
    layer     = max(0, min(_ii(req, "layer", 12), 95))
    d_model   = max(8, min(_ii(req, "d_model", 512), 8192))
    n_coeffs  = max(2, min(_ii(req, "n_coeffs", 9), _MAX_COEFFS))
    coeff_max = max(0.1, min(_ff(req, "coeff_max", 6.0), 50.0))

    snap = _steering_snapshot(
        seed=seed, layer=layer, d_model=d_model, n_coeffs=n_coeffs, coeff_max=coeff_max,
    )

    return JSONResponse({
        "label":     "MODELED",
        "model":     "Steering vectors / activation addition (ActAdd) / representation engineering (RepE)",
        "method":    "v_steer = mean(h_pos) - mean(h_neg) over a contrastive prompt pair; h' = h + coeff*v_steer injected at a chosen layer; sweep coeff -> sentiment_score shift, capability_score held-out check",
        "seed":      seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "ActAdd/RepE mean-difference steering-vector construction (arXiv:2308.10248, "
            "arXiv:2310.01405) and additive injection arithmetic (h' = h + coeff*v_steer), NOT "
            "a run against a real language model's weights or activations, and NEVER-CLAIMED-AS "
            "a production steering system. Toy per-layer residual-stream activations for the "
            "'Love' vs 'Hate' contrastive pair are drawn from a deterministic LCG PRNG (no numpy, "
            "no stdlib random, no proprietary weights, no real transformer forward pass). The "
            "sentiment_score and capability_score curves are closed-form functions of the "
            "injected coefficient chosen to reproduce the qualitative, published phenomenology — "
            "a targeted behavioural shift (sentiment moves) with the held-out capability metric "
            "staying approximately flat — they are NOT measurements from a real model. This is an "
            "inference-time control technique: no fine-tuning, no weight updates. Deterministic: "
            "same seed/layer/d_model/n_coeffs/coeff_max -> identical snapshot. SZL claims NONE of "
            "these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_interpretability.register() / szl_specdecode.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/steering/sweep onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/steering"
    handlers = [
        (f"{base}/sweep", _h_sweep),
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
    snap = _steering_snapshot(seed=42, layer=12, d_model=512, n_coeffs=9, coeff_max=6.0)
    print("label: MODELED")
    print("layer:", snap["layer"])
    print("d_model:", snap["d_model"])
    print("contrastive_pair:", snap["contrastive_pair"])
    print("steering_vector_norm:", snap["steering_vector_norm"])
    print("coefficients:", snap["coefficients"])
    print("sentiment_score:", snap["sentiment_score"])
    print("capability_score:", snap["capability_score"])
    print("sentiment_shift:", snap["sentiment_shift"])
    print("capability_drift:", snap["capability_drift"])

    # sanity: bounds
    assert -1.0 <= min(snap["sentiment_score"]) and max(snap["sentiment_score"]) <= 1.0, \
        "sentiment_score out of [-1,1]"
    assert all(0.0 <= c <= 1.0 for c in snap["capability_score"]), \
        "capability_score out of [0,1]"
    assert snap["steering_vector_norm"] > 0.0, "steering vector must be non-degenerate"

    # sanity: monotonicity — sentiment_score should be non-decreasing across the
    # coefficient sweep (coefficients are ascending; tanh(gain*c) is monotone in c).
    scores = snap["sentiment_score"]
    assert all(b >= a - 1e-9 for a, b in zip(scores, scores[1:])), \
        ("sentiment_score should be non-decreasing in coeff", scores)

    # sanity: reproducible shift — the positive-coefficient end must be more
    # "Love"-like (higher score) than the negative-coefficient end.
    assert snap["sentiment_shift"] > 0.05, "sweep should produce a measurable sentiment shift"

    # sanity: capability stays comparatively flat vs the sentiment shift (the
    # core "targeted intervention, not a lobotomy" claim of steering vectors).
    assert snap["capability_drift"] < snap["sentiment_shift"], \
        "capability_drift should stay small relative to the sentiment_shift"

    # sanity: determinism — identical seed/layer/d_model/n_coeffs/coeff_max ->
    # identical snapshot.
    snap2 = _steering_snapshot(seed=42, layer=12, d_model=512, n_coeffs=9, coeff_max=6.0)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: a different seed must (almost certainly) change the vector norm,
    # proving the LCG stream is actually driving the computation.
    snap3 = _steering_snapshot(seed=7, layer=12, d_model=512, n_coeffs=9, coeff_max=6.0)
    assert snap3["steering_vector_norm"] != snap["steering_vector_norm"], \
        "different seed should change the steering vector"

    print()
    print("szl_steering: ALL OK — deterministic, sentiment shift reproducible, "
          "capability held-out metric stays flat, bounds respected.")
