"""
szl_interpretability.py — SZL mechanistic-interpretability / sparse-autoencoder endpoint.

Exposes a MODELED JumpReLU sparse-autoencoder (SAE) feature decomposition of a
residual-stream activation, plus per-feature causal-ablation effect sizes, as a
same-origin REST endpoint. This gives the interpretability surface organ a live
data source that is honest, deterministic, and citable — never fabricated, never
random-faked, never a real proprietary model's weights.

  GET  /api/<ns>/v1/interpretability/features?seed=&top_k=&d_model=&n_features=&theta=

Returned JSON fields
--------------------
  label                 : "MODELED" (always — this is a simulation of the METHOD, not a live LLM)
  model                 : "JumpReLU sparse autoencoder over a residual stream"
  d_model               : residual-stream width simulated
  n_dict_features       : SAE dictionary size (over-complete)
  theta                 : JumpReLU threshold (features below it are hard-zeroed)
  l0_sparsity           : fraction of dictionary features active for the probe token (0..1)
  active_features       : count of features that fired (L0)
  top_features          : list of the top-k fired features, each with:
                            feature                  : human-readable interpretation
                            activation               : SAE latent activation (post-JumpReLU)
                            causal_ablation_kl        : MODELED KL logit-shift when the feature is ablated
                            interpretation_confidence : MODELED confidence the label is faithful
  reconstruction_cos    : MODELED cosine similarity of SAE reconstruction to the input activation
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form simulation of how a JumpReLU sparse
  autoencoder decomposes a transformer's internal activations into a small set of
  human-interpretable features, and how ablating each feature causally shifts the
  output distribution (KL). It is NOT run on a real model's activations, uses no
  proprietary weights, and reports no measured logits. The label "MODELED" is
  returned verbatim and displayed verbatim by the surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Sparse autoencoders find interpretable features:
    Cunningham et al. (2023) "Sparse Autoencoders Find Highly Interpretable Features".
    arXiv:2309.08600. https://arxiv.org/abs/2309.08600
  JumpReLU SAEs:
    Rajamanoharan et al. (2024) "Jumping Ahead: Improving Reconstruction Fidelity
    with JumpReLU Sparse Autoencoders". arXiv:2407.14435. https://arxiv.org/abs/2407.14435
  Anthropic interpretability / circuit tracing:
    Anthropic "Circuits Updates — January 2025".
    https://transformer-circuits.pub/2025/january-update/index.html
  Sparse feature circuits (causal, model-agnostic):
    Marks et al. (2024) "Sparse Feature Circuits". arXiv:2406.02395.
    https://arxiv.org/abs/2406.02395

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

import math
import json
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "SAEs find interpretable features — Cunningham et al. arXiv:2309.08600": "https://arxiv.org/abs/2309.08600",
    "JumpReLU SAEs — Rajamanoharan et al. arXiv:2407.14435": "https://arxiv.org/abs/2407.14435",
    "Anthropic Circuits Updates (Jan 2025)": "https://transformer-circuits.pub/2025/january-update/index.html",
    "Sparse Feature Circuits — Marks et al. arXiv:2406.02395": "https://arxiv.org/abs/2406.02395",
}

# A curated dictionary of interpretable features the SAE is MODELED to surface.
# Each string describes what the sparse latent is modeled to detect. These are
# illustrative feature labels of the KIND real SAEs discover — not claims about
# any specific model's true internals.
_FEATURE_BANK = [
    "syntax · past-tense verb",
    "code · Python def keyword",
    "geography · US state name",
    "sentiment · negation cue",
    "arithmetic · carry operation",
    "syntax · nested-parenthesis depth",
    "entity · person vs organization",
    "safety · refusal trigger",
    "provenance · attestation token",
    "quantum · entanglement lexeme",
    "PNT · GPS-denied context",
    "biology · radical-pair mention",
    "temporal · sequence ordering",
    "dialogue · question vs statement",
    "numeric · unit-of-measure",
    "logic · conditional (if/then)",
]


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# MODELED JumpReLU SAE decomposition + causal ablation (deterministic)
# ---------------------------------------------------------------------------
def _sae_snapshot(
    seed: int = 42,
    top_k: int = 8,
    d_model: int = 512,
    n_features: int = 4096,
    theta: float = 0.15,
) -> dict:
    """
    Simulate a JumpReLU sparse autoencoder over one residual-stream activation.

    JumpReLU: latent a_i fires only if its pre-activation exceeds threshold θ,
    otherwise it is hard-zeroed. This yields high L0 sparsity (few features per
    token) which is what makes the decomposition human-interpretable.

    For each surfaced feature we also MODEL a causal-ablation effect: the KL
    divergence between the output distribution with vs. without that feature —
    the model-agnostic causal-interpretability signal (Marks et al. 2024).

    Pure stdlib; deterministic — same seed -> identical snapshot.
    """
    rng = _lcg(seed)
    theta = max(0.01, min(theta, 0.95))

    # Pre-activations for the curated feature bank (bounded 0..1, deterministic).
    pre = [next(rng) for _ in _FEATURE_BANK]

    # JumpReLU: keep only features above threshold θ.
    fired = [(name, round(a, 4)) for name, a in zip(_FEATURE_BANK, pre) if a > theta]
    fired.sort(key=lambda x: x[1], reverse=True)
    top = fired[: max(1, min(top_k, len(_FEATURE_BANK)))]

    # Causal ablation: MODELED KL logit-shift when each top feature is zeroed.
    # Higher activation -> generally larger causal effect, with deterministic spread.
    features = []
    for name, act in top:
        spread = next(rng)
        ablation_kl = round(act * (0.40 + 0.60 * spread), 4)     # MODELED effect size (nats)
        conf = round(min(0.99, 0.50 + act / 2.0), 3)             # MODELED faithfulness confidence
        features.append({
            "feature": name,
            "activation": act,
            "causal_ablation_kl": ablation_kl,
            "interpretation_confidence": conf,
        })

    active = len(fired)
    # L0 sparsity relative to the full (over-complete) dictionary — the real
    # interpretability metric: interpretability improves as this fraction shrinks.
    l0_sparsity = round(active / max(n_features, 1), 8)

    # MODELED reconstruction fidelity of the SAE (cosine of reconstruction vs input).
    # JumpReLU SAEs trade a little fidelity for far better sparsity; model ~0.90–0.98.
    recon_cos = round(0.90 + 0.08 * next(rng), 4)

    return {
        "d_model": d_model,
        "n_dict_features": n_features,
        "theta": round(theta, 4),
        "l0_sparsity": l0_sparsity,
        "active_features": active,
        "top_features": features,
        "reconstruction_cos": recon_cos,
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


def _h_features(req: Request):
    seed       = _ii(req, "seed",        42)
    top_k      = max(1, min(_ii(req, "top_k",  8), 16))
    d_model    = max(8, min(_ii(req, "d_model", 512), 8192))
    n_features = max(64, min(_ii(req, "n_features", 4096), 131072))
    theta      = max(0.01, min(_fi(req, "theta", 0.15), 0.95))

    snap = _sae_snapshot(
        seed=seed, top_k=top_k, d_model=d_model, n_features=n_features, theta=theta,
    )

    return JSONResponse({
        "label":               "MODELED",
        "model":               "JumpReLU sparse autoencoder over a residual stream",
        "method":              "JumpReLU SAE decomposition + model-agnostic causal ablation (KL)",
        "d_model":             snap["d_model"],
        "n_dict_features":     snap["n_dict_features"],
        "theta":               snap["theta"],
        "seed":                seed,
        "l0_sparsity":         snap["l0_sparsity"],
        "active_features":     snap["active_features"],
        "top_features":        snap["top_features"],
        "reconstruction_cos":  snap["reconstruction_cos"],
        "honest_note": (
            "MODELED: this is a deterministic closed-form simulation of the JumpReLU "
            "sparse-autoencoder interpretability METHOD (decompose activations into a few "
            "human-readable features, then causally ablate each and measure the KL logit-shift). "
            "It is NOT run on a real model's activations, uses NO proprietary weights, and reports "
            "NO measured logits. The feature labels illustrate the KIND of features real SAEs find; "
            "they are not claims about any specific model's internals. Deterministic: same seed -> "
            "identical snapshot. Cite: Cunningham et al. arXiv:2309.08600; Rajamanoharan et al. "
            "arXiv:2407.14435 (JumpReLU); Marks et al. arXiv:2406.02395 (sparse feature circuits); "
            "Anthropic transformer-circuits.pub. SZL claims NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_neuromorphic.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/interpretability/features onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/interpretability"
    handlers = [
        (f"{base}/features", _h_features),
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
    snap = _sae_snapshot(seed=42, top_k=8)
    print("label: MODELED")
    print("active_features:", snap["active_features"])
    print("l0_sparsity:", snap["l0_sparsity"])
    print("reconstruction_cos:", snap["reconstruction_cos"])
    for f in snap["top_features"]:
        print("  ", f["feature"], f["activation"], "KL=", f["causal_ablation_kl"])
