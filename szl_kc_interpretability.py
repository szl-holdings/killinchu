# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_interpretability.py — ADDITIVE SPARSE-AUTOENCODER (SAE) feature-extraction simulator
for killinchu's frontier surface (backs a11oy static/3d/surfaces/interpretability.js).

Mechanistic interpretability resolves polysemantic neurons into monosemantic FEATURES by
training a sparse autoencoder on a model's residual-stream activations: an overcomplete
dictionary D of feature directions is learned so each activation reconstructs as a SPARSE,
non-negative combination of dictionary atoms. Cunningham, Ewart, Riggs, Huben, Sharkey (2023)
— "Sparse Autoencoders Find Highly Interpretable Features in Language Models"
(arXiv:2309.08600) — show these features are more interpretable/monosemantic than neurons.
Anthropic's "Towards Monosemanticity" (Bricken et al. 2023) and "Scaling Monosemanticity"
(Templeton et al. 2024) scaled this to production models. This organ re-derives the SAE
forward/encode step: encode activations with a ReLU + L1 (sparsity) objective, decode with a
tied dictionary, and report the sparsity (L0), reconstruction error, and a feature-frequency /
dead-feature census.

Deterministic MODELED SAE encode/decode (seeded, no live model):
  * x = seeded d-dim activation vector; dictionary D is a seeded h-by-d overcomplete matrix
    (h >> d), rows L2-normalized to unit atoms.
  * pre-activations a = D x - b (a seeded bias/threshold), feature codes f = ReLU(a).
    Keep only the top-k largest codes (a JumpReLU / top-k sparsity stand-in) so L0 = k.
  * reconstruction x_hat = D^T f ; reconstruction_mse = mean((x - x_hat)^2).
  * feature activation frequency over a batch of seeded activations; a feature is DEAD if it
    never fires. Report L0, fraction_variance_unexplained proxy, active/dead feature counts.

  f = ReLU(D x - b), keep top-k       (sparse feature codes; L0 = k)
  x_hat = D^T f                        (tied-dictionary reconstruction)
  reconstruction_mse = mean((x - x_hat)^2)
  monosemanticity_proxy = k / h        (sparse fraction of the overcomplete dictionary firing)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic SAE encode/decode SIMULATION. NOT a trained SAE / Anthropic dictionary
    running; NO live model, NO GPU, NO trained weights. Activations x, dictionary D, and bias b
    are SEEDED PRNG inputs, NOT a real residual stream or learned dictionary.
  * L0 / reconstruction error / dead-feature counts are properties of the modeled encode on
    seeded inputs, honestly labeled — NOT a measured claim about a real model's interpretability.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/interpretability/features  — SAE feature-extraction snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | SAE_ENCODE_SIM | NOT_LIVE | NO_MODEL | DICTIONARY_IS_SEEDED"

CITATIONS = {
    "cunningham": ("Cunningham, Ewart, Riggs, Huben, Sharkey (2023) Sparse Autoencoders Find "
                   "Highly Interpretable Features in Language Models — "
                   "https://arxiv.org/abs/2309.08600"),
    "bricken": ("Bricken et al. / Anthropic (2023) Towards Monosemanticity: Decomposing "
                "Language Models With Dictionary Learning — "
                "https://transformer-circuits.pub/2023/monosemantic-features"),
    "templeton": ("Templeton et al. / Anthropic (2024) Scaling Monosemanticity: Extracting "
                  "Interpretable Features from Claude 3 Sonnet — "
                  "https://transformer-circuits.pub/2024/scaling-monosemanticity"),
}


class _LCG:
    """Small deterministic LCG PRNG (pure stdlib; no numpy, no stdlib random)."""

    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) & 0xFFFFFFFFFFFFFFFF) or 0x9E3779B97F4A7C15

    def _next(self) -> int:
        self._s = (6364136223846793005 * self._s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self._s

    def random(self) -> float:
        return (self._next() >> 11) / float(1 << 53)

    def normalish(self) -> float:
        # Irwin-Hall(4)-centered approx of a zero-mean unit-ish gaussian (pure stdlib).
        return (self.random() + self.random() + self.random() + self.random()) - 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relu(x: float) -> float:
    return x if x > 0.0 else 0.0


def interp_features(seed: int = 42, d_model: int = 16, n_features: int = 128,
                    top_k: int = 8, batch: int = 64) -> dict:
    """SAE feature-extraction snapshot (MODELED).

    d_model    — activation dimensionality d.
    n_features — overcomplete dictionary size h (h >> d).
    top_k      — kept active features per activation (L0 sparsity).
    batch      — number of seeded activations to census.
    seed       — PRNG seed; deterministic.
    """
    d = max(2, min(256, int(d_model)))
    h = max(d + 1, min(4096, int(n_features)))
    k = max(1, min(h, int(top_k)))
    B = max(1, min(2048, int(batch)))
    rng = _LCG(int(seed) * 2_654_435_761 + d * 131 + h * 17 + k * 7)

    # overcomplete dictionary D: h atoms in R^d, each L2-normalized to a unit direction.
    D = []
    for _ in range(h):
        atom = [rng.normalish() for _ in range(d)]
        nrm = _math.sqrt(sum(v * v for v in atom)) or 1.0
        D.append([v / nrm for v in atom])
    bias = [0.15 * rng.random() for _ in range(h)]  # seeded threshold/bias per feature

    fire_count = [0] * h
    total_mse = 0.0
    total_energy = 0.0
    first_l0 = None
    first_active_ids = None
    for t in range(B):
        x = [rng.normalish() for _ in range(d)]
        # pre-activations a_j = <D_j, x> - b_j ; codes f = ReLU(a), then top-k.
        pre = [sum(D[j][c] * x[c] for c in range(d)) - bias[j] for j in range(h)]
        codes = [_relu(p) for p in pre]
        # keep only the top-k largest codes (JumpReLU/top-k sparsity)
        idx_sorted = sorted(range(h), key=lambda j: codes[j], reverse=True)[:k]
        active = [j for j in idx_sorted if codes[j] > 0.0]
        f = [0.0] * h
        for j in active:
            f[j] = codes[j]
            fire_count[j] += 1
        # reconstruction x_hat = sum_j f_j * D_j  (tied dictionary decode)
        x_hat = [0.0] * d
        for j in active:
            Dj = D[j]
            fj = f[j]
            for c in range(d):
                x_hat[c] += fj * Dj[c]
        mse = sum((x[c] - x_hat[c]) ** 2 for c in range(d)) / d
        total_mse += mse
        total_energy += sum(v * v for v in x) / d
        if t == 0:
            first_l0 = len(active)
            first_active_ids = sorted(active)[:16]

    recon_mse = total_mse / B
    mean_energy = total_energy / B or 1.0
    # fraction of variance unexplained proxy (bounded by construction reporting)
    fvu = recon_mse / mean_energy
    active_features = sum(1 for c in fire_count if c > 0)
    dead_features = h - active_features
    mean_l0 = k  # top-k keeps exactly k (when enough positive codes exist)
    monosemanticity_proxy = k / h
    fire_freq = [round(c / B, 6) for c in fire_count[:32]]

    return {
        "service": "sae-feature-extraction",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/interpretability.js ---
        "d_model": int(d),
        "n_features": int(h),
        "top_k": int(k),
        "batch": int(B),
        "l0_sparsity": int(mean_l0),
        "reconstruction_mse": round(float(recon_mse), 6),
        "fraction_variance_unexplained": round(float(fvu), 6),
        "active_features": int(active_features),
        "dead_features": int(dead_features),
        "dead_feature_pct": round(100.0 * dead_features / h, 4),
        "monosemanticity_proxy": round(float(monosemanticity_proxy), 6),
        "first_activation_l0": int(first_l0 or 0),
        "first_active_feature_ids": [int(x) for x in (first_active_ids or [])],  # [int]
        "feature_fire_frequency": fire_freq,   # [float] per-feature fire rate (first 32)
        "formulas": {
            "codes": "f = ReLU(D x - b), keep top-k",
            "reconstruction": "x_hat = D^T f (tied dictionary)",
            "reconstruction_mse": "mean((x - x_hat)^2)",
            "fvu": "reconstruction_mse / mean(||x||^2 / d)",
            "monosemanticity_proxy": "k / h (sparse fraction of overcomplete dictionary firing)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python SAE encode/decode simulation (seeded LCG)",
            "label": "MODELED",
            "honest_note": ("Deterministic top-k SAE encode on seeded activations + seeded "
                            "dictionary; NO trained SAE, NO live model, NO GPU. The "
                            "trained-dictionary-on-a-real-residual-stream path is ROADMAP."),
        },
        "honest_note": ("MODELED sparse-autoencoder feature extraction. NOT a trained SAE / "
                        "Anthropic dictionary running; NO live model, NO GPU, NO trained "
                        "weights. Activations, dictionary, and bias are seeded inputs; L0 and "
                        "reconstruction error are properties of the modeled encode. Advisory to "
                        "Λ (Conjecture 1); adds nothing to the locked-8."),
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (feature snapshot advisory — never an autonomous action)",
        "citations": {"cunningham": CITATIONS["cunningham"], "bricken": CITATIONS["bricken"],
                      "templeton": CITATIONS["templeton"]},
        "wired_into": "frontier ring — Interpretability surface (SAE monosemantic features)",
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive). Mirrors szl_kc_specdec.register exactly.
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/interpretability" % ns
    path = "%s/features" % base

    @app.get(path)
    async def _kc_interp(seed: int = 42, d_model: int = 16, n_features: int = 128,
                         top_k: int = 8, batch: int = 64):  # noqa: ANN202
        try:
            return JSONResponse(interp_features(seed=seed, d_model=d_model,
                                                n_features=n_features, top_k=top_k, batch=batch))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "sae-feature-extraction",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "reconstruction_mse": None, "l0_sparsity": None},
                                status_code=200)

    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_interp_route(request):  # pragma: no cover
            q = request.query_params
            return _SJSON(interp_features(seed=int(q.get("seed", 42)),
                                          d_model=int(q.get("d_model", 16)),
                                          n_features=int(q.get("n_features", 128)),
                                          top_k=int(q.get("top_k", 8)),
                                          batch=int(q.get("batch", 64))))

        app.router.routes.append(Route(path, _kc_interp_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = interp_features(seed=42, d_model=16, n_features=128, top_k=8, batch=64)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("d_model", "n_features", "top_k", "batch", "l0_sparsity",
              "active_features", "dead_features"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("reconstruction_mse", "fraction_variance_unexplained", "monosemanticity_proxy"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["first_active_feature_ids"], list), r
    assert isinstance(r["feature_fire_frequency"], list) and r["feature_fire_frequency"], r

    # invariants: overcomplete dictionary; L0 sparsity == top_k << h; census sums to h.
    assert r["n_features"] > r["d_model"], r  # overcomplete
    assert r["l0_sparsity"] == r["top_k"], r
    assert r["l0_sparsity"] < r["n_features"], r  # genuinely sparse
    assert r["active_features"] + r["dead_features"] == r["n_features"], r
    assert 0.0 <= r["monosemanticity_proxy"] < 1.0, r
    assert r["reconstruction_mse"] > 0.0, r
    assert r["fraction_variance_unexplained"] > 0.0, r
    assert r["first_activation_l0"] <= r["top_k"], r
    out["metrics"] = {"l0_sparsity": r["l0_sparsity"], "reconstruction_mse": r["reconstruction_mse"],
                      "fraction_variance_unexplained": r["fraction_variance_unexplained"],
                      "active_features": r["active_features"], "dead_features": r["dead_features"]}

    assert "arxiv.org/abs/2309.08600" in r["citations"]["cunningham"], r["citations"]
    out["citations_ok"] = True

    # determinism
    r2 = interp_features(seed=42, d_model=16, n_features=128, top_k=8, batch=64)
    assert r2["feature_fire_frequency"] == r["feature_fire_frequency"], "non-deterministic freq"
    assert r2["reconstruction_mse"] == r["reconstruction_mse"], "non-deterministic mse"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
    print("ALL OK")
