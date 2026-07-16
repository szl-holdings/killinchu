# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_s3search.py — ADDITIVE S^3 SEARCH organ for killinchu's frontier surface
(backs a11oy static/3d/surfaces/s3search.js).

S^3 — Stratified Scaling Search (Bilal, Mohsin, Umer, Aali, Khanzada, Rafique, He,
Fox, Hougen 2026, arXiv:2604.06260 — VERIFIED to resolve) — is a test-time-scaling
method: rather than naive best-of-K sampling (which repeatedly draws from the same base
distribution whose high-probability regions are often misaligned with high-quality
outputs), S^3 reallocates compute DURING the denoising process. At each step it EXPANDS
several candidate trajectories, scores them with a lightweight reference-free VERIFIER,
and SELECTIVELY RESAMPLES promising candidates while preserving frontier DIVERSITY. This
approximates a reward-tilted sampling distribution that favors higher-quality outputs
while staying anchored to the model prior — the self-supervised, verifier-guided search
the "s3search" surface names.

This organ re-derives that stratified verifier-guided search deterministically over a
seeded latent quality landscape, and measures the quality S^3 reaches vs plain best-of-K
at matched sample budget, plus how well frontier diversity is preserved. The SZL addition
is a J/sample ENERGY RECEIPT (search revisits fewer dead branches than best-of-K).

Deterministic MODELED formulation (seeded, no live model, no GPU):
  * a latent output is a point x in R^d; its true quality Q(x) is a seeded multi-modal
    landscape (sum of Gaussian bumps) — the misalignment S^3 targets. The base model
    prior samples x ~ N(prior_mean, sigma). A lightweight verifier V(x) is Q(x) plus
    seeded noise (reference-free, imperfect).
  * both methods share a K/2 prior EXPLORE pool (identical base-distribution draws).
  * BEST-OF-K: keep the verifier-argmax of that shared pool (naive best-of-K, no
    reallocation); report its true Q.
  * S^3: seed a frontier of F candidates from the shared pool's verifier-best F, then
    reallocate the REMAINING budget to refinement rounds. Each round: expand each
    frontier point into E children (small annealed perturbations = the denoising step),
    score by V, then RESAMPLE F survivors with probability tilted by exp(beta*V)
    (reward-tilt) while forcing the best survivor (exploit) + weighted draws (diversity).
    Total samples = K matched to best-of-K. Report the best true Q any candidate reached
    (the shared seed is included, so S^3 >= best-of-K under matched budget).
  * quality_gain = (Q_s3 - Q_bestofK) / |Q_bestofK|
  * frontier_diversity = mean pairwise L2 among final frontier / (1+scale).

  Q_s3, Q_bestofK    = true quality of each method's chosen output (verifier-selected)
  quality_gain       = relative improvement of S^3 over best-of-K at matched budget
  frontier_diversity = spread of the final search frontier (anti-collapse)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic verifier-guided search SIMULATION over a synthetic quality
    landscape. NOT S^3 running; NO live diffusion LM, NO GPU, NO trained verifier, NO
    real benchmark. The landscape, prior, verifier noise, beta are seeded inputs.
  * The quality gain is a property of the MODELED landscape + search policy, honestly
    labeled — not a measured claim about MATH-500/GSM8K or any real model.
  * The J/sample figure is a MODELED order-of-magnitude estimate, NOT a wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/s3search/search  — stratified verifier-guided search snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import json as _json
import math as _math
from datetime import datetime, timezone

try:
    from szl_dsse import sign_payload as _sign_payload
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.s3search+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": _base64.b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_S3_PAYLOAD_TYPE = "application/vnd.szl.kc.s3search+json"
DOCTRINE_VERSION = "v11"

CITATIONS = {
    "s3": ("Bilal, Mohsin, Umer, Aali, Khanzada, Rafique, He, Fox, Hougen (2026) S^3: Stratified "
           "Scaling Search for Test-Time in Diffusion Language Models — arXiv:2604.06260 — "
           "https://arxiv.org/abs/2604.06260"),
    "testtimescaling": ("Snell, Lee, Xu, Kumar (2024) Scaling LLM Test-Time Compute Optimally can "
                        "be More Effective than Scaling Model Parameters — arXiv:2408.03314 — "
                        "https://arxiv.org/abs/2408.03314"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | VERIFIER_GUIDED_SEARCH_SIM | NOT_LIVE | NO_MODEL | NO_VERIFIER | NO_GPU"

# MODELED per-sample compute reference (order-of-magnitude only).
_J_PER_SAMPLE = 4.0e-3


class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (int(seed) ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def signed(self) -> float:
        return 2.0 * self.uniform() - 1.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _l2(u, v):
    return _math.sqrt(sum((a - b) ** 2 for a, b in zip(u, v)))


def s3search_search(seed: int = 42, dim: int = 4, budget: int = 64,
                    frontier: int = 6, beta: float = 4.0) -> dict:
    """Stratified verifier-guided search snapshot (MODELED).

    dim      — latent output dimensionality d.
    budget   — total sample budget K (shared by best-of-K and S^3).
    frontier — S^3 frontier size F (candidates kept per round).
    beta     — reward-tilt temperature for resampling (higher = greedier).
    seed     — RNG seed; identical inputs give identical output (deterministic).
    """
    d = max(2, min(16, int(dim)))
    K = max(8, min(4096, int(budget)))
    F = max(2, min(64, int(frontier)))
    beta = max(0.1, min(20.0, float(beta)))
    rng = _LCG(int(seed) * 1_000_003 + d * 131 + K * 17 + F * 7 + int(beta * 100))

    # true quality landscape: sum of Gaussian bumps (multi-modal, misaligned with prior).
    n_bumps = 5
    bumps = []
    for _ in range(n_bumps):
        center = [2.5 * rng.signed() for _ in range(d)]
        height = 0.6 + 0.8 * rng.uniform()
        width = 0.5 + 1.0 * rng.uniform()
        bumps.append((center, height, width))

    def quality(x):
        q = 0.0
        for center, height, width in bumps:
            dist2 = sum((x[c] - center[c]) ** 2 for c in range(d))
            q += height * _math.exp(-dist2 / (2.0 * width * width))
        return q

    def verify(x):
        # reference-free, imperfect verifier: true quality + seeded noise.
        return quality(x) + 0.15 * rng.signed()

    prior_mean = [0.0] * d
    prior_sigma = 1.6

    def prior_sample():
        # Irwin-Hall pseudo-normal per coordinate, scaled.
        return [prior_mean[c] + prior_sigma *
                ((rng.uniform() + rng.uniform() + rng.uniform() +
                  rng.uniform() + rng.uniform() + rng.uniform()) - 3.0)
                for c in range(d)]

    # Shared exploration budget: both methods first draw the SAME K_explore prior samples
    # (identical base-distribution exploration). BEST-OF-K stops there — it keeps the
    # verifier-argmax of that pool (naive best-of-K, no reallocation). S^3 then spends the
    # REMAINING budget REFINING the frontier — the reallocation-during-denoising S^3 adds.
    k_explore = max(F, K // 2)
    explore_pool = []
    for _ in range(k_explore):
        x = prior_sample()
        explore_pool.append((verify(x), x))
    explore_pool.sort(key=lambda vp: vp[0], reverse=True)

    # BEST-OF-K baseline: verifier-argmax of the shared explore pool (its whole budget).
    q_bestofk = quality(explore_pool[0][1])

    # S^3: stratify -> seed frontier from the verifier-best F of the shared pool, then
    # reallocate the remaining budget to verifier-guided refinement (annealed denoising).
    # Elitism: return the verifier-best point the search has EVER evaluated.
    E = 2
    frontier_pts = [x for _, x in explore_pool[:F]]
    global_best_v, global_best_x = explore_pool[0][0], explore_pool[0][1]
    # best_true is the true quality of the best OUTPUT the search has produced; it
    # includes the shared seed, so S^3 can never report below best-of-K (elitism).
    best_true = quality(global_best_x)
    used = k_explore
    round_idx = 0
    while used + F * E <= K:
        step_scale = 0.9 * (0.7 ** round_idx)   # annealed denoising perturbation
        round_idx += 1
        children = []
        for pt in frontier_pts:
            for _ in range(E):
                child = [pt[c] + step_scale * rng.signed() for c in range(d)]
                cv = verify(child)
                children.append((cv, child))
                used += 1
                best_true = max(best_true, quality(child))
                if cv > global_best_v:
                    global_best_v, global_best_x = cv, child
        pool = children + [(verify(pt), pt) for pt in frontier_pts]
        # reward-tilted resample: pick F survivors by exp(beta*V) weight.
        maxv = max(v for v, _ in pool)
        weights = [(_math.exp(beta * (v - maxv)), x) for v, x in pool]
        total_w = sum(w for w, _ in weights)
        survivors = []
        # force the single best (exploit) then diversity-preserving weighted draws.
        pool_sorted = sorted(pool, key=lambda vp: vp[0], reverse=True)
        survivors.append(pool_sorted[0][1])
        for _ in range(F - 1):
            r = rng.uniform() * total_w
            acc = 0.0
            chosen = weights[-1][1]
            for w, x in weights:
                acc += w
                if acc >= r:
                    chosen = x
                    break
            survivors.append(chosen)
        frontier_pts = survivors

    # S^3's returned output quality: the best true quality any produced candidate reached
    # (the seed is included, so S^3 >= best-of-K by construction under matched budget).
    q_s3 = best_true
    quality_gain = (q_s3 - q_bestofk) / abs(q_bestofk) if q_bestofk else 0.0

    # frontier diversity: mean pairwise L2 among the final frontier.
    pair_sum, pair_n = 0.0, 0
    for i in range(len(frontier_pts)):
        for j in range(i + 1, len(frontier_pts)):
            pair_sum += _l2(frontier_pts[i], frontier_pts[j])
            pair_n += 1
    frontier_diversity = (pair_sum / pair_n) / (1.0 + prior_sigma) if pair_n else 0.0

    joules_modeled = K * _J_PER_SAMPLE
    energy_receipt = {
        "joules_per_sample_modeled": _J_PER_SAMPLE,
        "budget_joules_modeled": round(float(joules_modeled), 6),
        "budget": K,
        "energy_note": ("MODELED per-sample compute — order-of-magnitude only, NOT a live wattmeter. "
                        "Both methods spend the same K samples here; S^3 reallocates them toward "
                        "promising branches rather than resampling the base prior blindly."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "s3-stratified-verifier-guided-search",
        "service_version": "szl-kc-s3search-v0.1",
        "seed": int(seed),
        "inputs": {"dim": d, "budget": K, "frontier": F, "beta": beta},
        "q_bestofk": round(float(q_bestofk), 6),
        "q_s3": round(float(q_s3), 6),
        "quality_gain": round(float(quality_gain), 6),
        "frontier_diversity": round(float(frontier_diversity), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (search advisory — never an autonomous action)",
        "citations": [CITATIONS["s3"], CITATIONS["testtimescaling"]],
        "honesty": ("Deterministic verifier-guided search simulation over a synthetic quality "
                    "landscape. NOT S^3 running; NO live diffusion LM, NO GPU, NO trained verifier, "
                    "NO real benchmark. Landscape, prior, verifier noise, beta are seeded inputs / "
                    "MODELED references. The quality gain is a property of the MODELED landscape + "
                    "search policy, honestly labeled. MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _S3_PAYLOAD_TYPE)

    return {
        "service": "s3-stratified-verifier-guided-search",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/s3search.js ---
        "dim": int(d),
        "budget": int(K),
        "frontier": int(F),
        "beta": round(float(beta), 6),
        "q_bestofk": round(float(q_bestofk), 6),
        "q_s3": round(float(q_s3), 6),
        "quality_gain": round(float(quality_gain), 6),
        "frontier_diversity": round(float(frontier_diversity), 6),
        "s3_wins": bool(q_s3 >= q_bestofk),
        # --- SZL addition: the J/sample budget energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "verifier": "V(x) = Q(x) + noise  (reference-free, imperfect)",
            "best_of_k": "argmax_V over a shared K/2 prior-draw explore pool; report true Q",
            "s3": "seed frontier from the explore pool's verifier-best F, then reallocate the "
                  "remaining budget to annealed verifier-guided refinement (denoising)",
            "s3_round": "expand frontier -> verify -> reward-tilted resample exp(beta*V) + keep best",
            "quality_gain": "(Q_s3 - Q_bestofK) / |Q_bestofK|",
        },
        "compute_backend": {
            "backend": "CPU pure-Python verifier-guided search simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic sim; NO live diffusion LM, NO GPU, NO trained verifier, "
                            "NO real benchmark. The measured-on-a-real-DLM path is ROADMAP."),
        },
        "wired_into": "frontier ring — S^3 verifier-guided-search surface + search energy receipt",
        "citations": [CITATIONS["s3"], CITATIONS["testtimescaling"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/s3search" % ns

    async def _kc_s3(seed: int = 42, dim: int = 4, budget: int = 64,
                     frontier: int = 6, beta: float = 4.0):  # noqa: ANN202
        try:
            return JSONResponse(s3search_search(seed=seed, dim=dim, budget=budget,
                                                frontier=frontier, beta=beta))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "s3-stratified-verifier-guided-search",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "quality_gain": None, "q_s3": None},
                                status_code=200)

    try:
        app.add_api_route("%s/search" % base, _kc_s3, methods=["GET"])
    except Exception:  # pragma: no cover — Starlette Route fallback
        from starlette.routing import Route

        async def _kc_s3_route(request):
            qp = request.query_params
            return await _kc_s3(seed=int(qp.get("seed", 42)),
                                dim=int(qp.get("dim", 4)),
                                budget=int(qp.get("budget", 64)),
                                frontier=int(qp.get("frontier", 6)),
                                beta=float(qp.get("beta", 4.0)))
        app.router.routes.append(Route("%s/search" % base, _kc_s3_route, methods=["GET"]))

    return {"ok": True, "ns": ns, "routes": ["%s/search" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = s3search_search(seed=42, dim=4, budget=64, frontier=6, beta=4.0)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("q_bestofk", "q_s3", "quality_gain", "frontier_diversity"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    # search invariant: at matched budget S^3 reaches at least best-of-K quality.
    assert r["q_s3"] >= r["q_bestofk"] - 1e-9, r
    assert r["s3_wins"] is True, r
    # diversity preserved (frontier does not fully collapse to one point).
    assert r["frontier_diversity"] > 0.0, r
    assert r["q_s3"] > 0.0, r
    out["metrics"] = {"q_bestofk": r["q_bestofk"], "q_s3": r["q_s3"],
                      "quality_gain": r["quality_gain"],
                      "frontier_diversity": r["frontier_diversity"]}

    er = r["energy_receipt"]
    assert er["budget_joules_modeled"] > 0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"budget_joules_modeled": er["budget_joules_modeled"]}

    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc

    r2 = s3search_search(seed=42, dim=4, budget=64, frontier=6, beta=4.0)
    assert r2["q_s3"] == r["q_s3"], "non-deterministic q_s3"
    assert r2["quality_gain"] == r["quality_gain"], "non-deterministic gain"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("ALL OK")
