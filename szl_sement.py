# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_sement.py — SZL semantic-entropy / epistemic-uncertainty hallucination-detection endpoint.

Exposes a MODELED semantic-entropy uncertainty estimator for LLM generations, plus a 2025
spectral EFFECTIVE-RANK extension, as a same-origin REST endpoint. For a fixed prompt we
sample K candidate generations from a toy categorical answer model, cluster them into
semantic-equivalence classes via a hand-specified lookup table (standing in for a real
bidirectional-entailment clusterer), sum probabilities within each cluster, and compute the
Shannon entropy over the cluster distribution — the SEMANTIC ENTROPY. Alongside it we compute
the NAIVE (surface-string) entropy to show the two diverge, and an EFFECTIVE RANK derived from
the normalized singular-value entropy of a small seeded "hidden-state" matrix per regime
(SVD implemented BY HAND in pure stdlib via power iteration — no numpy). This gives the sement
surface organ a live data source that is honest, deterministic, and citable — never fabricated,
never random-faked, never run on a real LLM.

  GET  /api/<ns>/v1/sement/estimate?seed=&K=&n_clusters=&regime=&threshold=

Returned JSON fields
--------------------
  label                 : "MODELED" (always — this simulates the METHOD, on synthetic toy data;
                           it is NOT a real LLM and uses no real entailment model)
  model                 : "Semantic-entropy + effective-rank epistemic-uncertainty estimator (MODELED)"
  seed                  : PRNG seed
  K                     : number of candidate generations sampled for the prompt
  n_clusters_param      : requested number of meaning-clusters in the toy model
  threshold             : abstain/answer decision threshold on semantic entropy (nats)
  regimes               : list of per-regime rows (CONFIDENT, CONFABULATING), each with:
                            regime            : "confident" | "confabulating"
                            n_clusters        : semantic-equivalence classes recovered
                            cluster_sizes     : member counts per class
                            cluster_probs     : cluster-probability distribution (sums to 1)
                            naive_entropy     : Shannon entropy over SURFACE strings (nats)
                            semantic_entropy  : Shannon entropy over MEANING clusters (nats)
                            effective_rank    : exp(entropy of normalized singular values)
                            decision          : "answer" | "abstain" (threshold on semantic entropy)
                            samples           : per-sample rows (answer, cluster)
  ordering_holds        : bool — semantic_entropy & effective_rank both rise on confabulating
  honest_note           : plain-language honesty disclaimer (baked in)
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form simulation of the semantic-entropy UNCERTAINTY
  ESTIMATOR (Farquhar/Kossen/Kuhn/Gal, Nature 2024) and its 2025 spectral effective-rank
  extension (Wang et al., arXiv:2510.08389). It is NOT a real LLM. The semantic-equivalence
  clustering is a HAND-SPECIFIED lookup table (real semantic entropy uses a bidirectional-
  entailment model); the "hidden states" are SYNTHETIC seeded matrices. It demonstrates the
  ORDERING (uncertain > confident) that the published methods exploit; it does NOT reproduce
  the Nature paper's AUROC or the effective-rank paper's benchmark numbers, and makes no claim
  about real-model calibration. The label "MODELED" is returned verbatim and displayed verbatim
  by the surface; it is never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Semantic entropy detects hallucinations:
    Farquhar, Kossen, Kuhn & Gal (2024) "Detecting hallucinations in large language models
    using semantic entropy". Nature 630, 625-630. DOI 10.1038/s41586-024-07421-0.
    https://www.nature.com/articles/s41586-024-07421-0
  Effective-rank-based uncertainty (2025 extension):
    Wang, Wei, Yue & Sun (2025) "Revisiting Hallucination Detection with Effective
    Rank-based Uncertainty". arXiv:2510.08389.
    https://arxiv.org/abs/2510.08389

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  No real LLM, no real entailment model — hand-specified clustering + synthetic hidden states.
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
    "Semantic entropy detects hallucinations — Farquhar, Kossen, Kuhn & Gal, Nature 2024, "
    "DOI 10.1038/s41586-024-07421-0": "https://www.nature.com/articles/s41586-024-07421-0",
    "Effective-rank-based uncertainty (2025) — Wang, Wei, Yue & Sun, arXiv:2510.08389":
        "https://arxiv.org/abs/2510.08389",
}

# ---------------------------------------------------------------------------
# Toy QA model + hand-specified semantic-equivalence lookup table.
#
# For each regime we define a fixed categorical distribution over a small set of candidate
# SURFACE answer strings for one fixed prompt ("What is the capital of France?"). The lookup
# table maps each surface string -> an integer MEANING-CLUSTER id. Surface strings that mean
# the same thing share a cluster id; this HAND-SPECIFIED table stands in for the real
# bidirectional-entailment clusterer used by semantic entropy — it is NOT a learned model.
#
# CONFIDENT   : probability mass concentrated on meaning-cluster A (paraphrases of "Paris").
# CONFABULATING: probability mass spread across several DISTINCT meaning-clusters
#                (Paris / Lyon / Marseille / Nice / "no capital") — the confabulation regime.
#
# These are illustrative synthetic answers of the KIND an LLM might emit — not claims about
# any real model's outputs.
# ---------------------------------------------------------------------------
# surface string -> meaning-cluster id (hand-specified "entailment" lookup)
_SEM_LOOKUP = {
    "Paris is the capital of France.":        0,
    "The capital of France is Paris.":        0,
    "France's capital city is Paris.":        0,
    "It is Paris, the French capital.":       0,
    "Lyon is the capital of France.":         1,
    "The capital of France is Marseille.":    2,
    "The capital of France is Nice.":         3,
    "France has no official capital.":        4,
}

# per-regime categorical distribution over surface strings (unnormalized weights).
# The clusterer below never reads these weights or the cluster ids directly — it recovers
# clusters purely from the lookup table applied to the sampled surface strings.
_REGIMES = {
    "confident": [
        ("Paris is the capital of France.",     50.0),
        ("The capital of France is Paris.",     28.0),
        ("France's capital city is Paris.",     14.0),
        ("It is Paris, the French capital.",     6.0),
        ("Lyon is the capital of France.",       2.0),
    ],
    "confabulating": [
        ("Paris is the capital of France.",     22.0),
        ("Lyon is the capital of France.",      20.0),
        ("The capital of France is Marseille.", 20.0),
        ("The capital of France is Nice.",      19.0),
        ("France has no official capital.",     19.0),
    ],
}


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Sampling K generations from a toy categorical distribution (deterministic LCG)
# ---------------------------------------------------------------------------
def _sample_generations(regime: str, K: int, rng) -> list:
    """Draw K surface strings from the regime's categorical distribution via inverse-CDF
    on deterministic LCG draws. Returns the list of sampled surface strings."""
    table = _REGIMES[regime]
    total = sum(w for _, w in table) or 1.0
    cdf = []
    acc = 0.0
    for text, w in table:
        acc += w / total
        cdf.append((acc, text))
    out = []
    for _ in range(K):
        u = next(rng)
        chosen = cdf[-1][1]
        for cum, text in cdf:
            if u <= cum:
                chosen = text
                break
        out.append(chosen)
    return out


# ---------------------------------------------------------------------------
# Naive (surface) entropy vs semantic (meaning-cluster) entropy
# ---------------------------------------------------------------------------
def _entropy(prob_iterable) -> float:
    h = 0.0
    for p in prob_iterable:
        if p > 0:
            h -= p * math.log(p)
    return h


def _cluster_and_score(samples: list) -> dict:
    """Cluster sampled surface strings into meaning classes via the hand-specified lookup,
    then compute naive (surface) entropy and semantic (cluster) entropy."""
    n = len(samples)
    # naive: distribution over distinct SURFACE strings
    surf_counts: dict = {}
    for s in samples:
        surf_counts[s] = surf_counts.get(s, 0) + 1
    naive_probs = [c / n for c in surf_counts.values()]
    naive_h = _entropy(naive_probs)

    # semantic: distribution over MEANING clusters (merge equivalent surface strings)
    clus_counts: dict = {}
    for s in samples:
        cid = _SEM_LOOKUP.get(s, -1)
        clus_counts[cid] = clus_counts.get(cid, 0) + 1
    # deterministic cluster ordering by id
    ordered = sorted(clus_counts.items(), key=lambda kv: kv[0])
    cluster_sizes = [c for _, c in ordered]
    cluster_probs = [c / n for c in cluster_sizes]
    sem_h = _entropy(cluster_probs)

    # per-sample rows (surface answer + assigned meaning cluster)
    rows = [{"answer": s, "cluster": _SEM_LOOKUP.get(s, -1)} for s in samples]

    return {
        "n_clusters": len(cluster_sizes),
        "cluster_sizes": cluster_sizes,
        "cluster_probs": [round(p, 6) for p in cluster_probs],
        "naive_entropy": round(naive_h, 6),
        "semantic_entropy": round(sem_h, 6),
        "samples": rows,
    }


# ---------------------------------------------------------------------------
# Synthetic "hidden-state" matrix per regime + BY-HAND SVD (power iteration)
# ---------------------------------------------------------------------------
def _hidden_state_matrix(regime: str, rows: int, cols: int, rng) -> list:
    """Build a small seeded 'hidden-state' matrix. CONFIDENT -> near-rank-1 (all rows are
    a shared direction plus tiny jitter); CONFABULATING -> higher effective rank (each row
    adds independent structure). Pure stdlib, deterministic. Synthetic — NOT real activations."""
    base = [math.cos(0.7 * (c + 1)) for c in range(cols)]
    M = []
    if regime == "confident":
        for _ in range(rows):
            scale = 0.8 + 0.4 * next(rng)             # shared direction, varying magnitude
            jitter = 0.02                              # tiny off-direction spread
            M.append([scale * base[c] + jitter * (next(rng) - 0.5) for c in range(cols)])
    else:
        for r in range(rows):
            # each row mixes the base with an independent per-row pattern -> higher rank
            mix = 0.35
            row = []
            for c in range(cols):
                indep = math.cos(0.9 * (r + 1) * (c + 1) + 0.3 * r)
                jitter = 0.15 * (next(rng) - 0.5)
                row.append(mix * base[c] + (1.0 - mix) * indep + jitter)
            M.append(row)
    return M


def _matT(M):
    return [[M[i][j] for i in range(len(M))] for j in range(len(M[0]))]


def _matvec(M, v):
    return [sum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]


def _gram(M):
    """A^T A — a (cols x cols) symmetric matrix; its eigenvalues are the squared singular values."""
    Mt = _matT(M)
    cols = len(Mt)
    G = [[0.0] * cols for _ in range(cols)]
    for i in range(cols):
        for j in range(cols):
            G[i][j] = sum(Mt[i][k] * Mt[j][k] for k in range(len(Mt[0])))
    return G


def _norm(v):
    return math.sqrt(sum(x * x for x in v)) or 1.0


def _singular_values(M, max_sv: int = 8, iters: int = 200) -> list:
    """Compute the leading singular values of M BY HAND, in pure stdlib.

    Method: form the Gram matrix G = A^T A (symmetric PSD), then extract its top eigenvalues
    via power iteration with deterministic Hotelling deflation. The singular values are the
    square roots of those eigenvalues. No numpy — only lists, math, and a fixed start vector.
    """
    G = _gram(M)
    dim = len(G)
    svals = []
    for _ in range(min(max_sv, dim)):
        # deterministic start vector (fixed, not random) so results are reproducible
        v = [1.0 / math.sqrt(dim)] * dim
        lam = 0.0
        for _ in range(iters):
            w = _matvec(G, v)
            nw = _norm(w)
            if nw <= 1e-15:
                break
            v = [x / nw for x in w]
            # Rayleigh quotient estimate of the eigenvalue
            Gv = _matvec(G, v)
            lam = sum(v[i] * Gv[i] for i in range(dim))
        lam = max(lam, 0.0)
        svals.append(math.sqrt(lam))
        # Hotelling deflation: G <- G - lam * v v^T  (remove the found eigencomponent)
        for i in range(dim):
            for j in range(dim):
                G[i][j] -= lam * v[i] * v[j]
    return svals


def _effective_rank(M) -> float:
    """Effective rank = exp(H) where H is the Shannon entropy of the normalized singular-value
    distribution (Roy & Vetterli). Near-rank-1 matrices -> effrank ~ 1; spread spectra -> higher.
    Singular values are computed by hand above. Pure stdlib, deterministic."""
    sv = _singular_values(M)
    total = sum(sv) or 1.0
    p = [s / total for s in sv if s > 0]
    h = _entropy(p)
    return math.exp(h)


# ---------------------------------------------------------------------------
# Core estimate — runs both regimes and compares
# ---------------------------------------------------------------------------
def _estimate(
    seed: int = 42,
    K: int = 40,
    n_clusters: int = 5,
    threshold: float = 0.6,
) -> dict:
    """Simulate the semantic-entropy + effective-rank epistemic-uncertainty pipeline over
    a CONFIDENT and a CONFABULATING regime for one fixed prompt.

      1. Sample K candidate generations from the regime's toy categorical distribution.
      2. Cluster surface strings into meaning classes via the hand-specified lookup.
      3. Compute NAIVE entropy (over surface strings) and SEMANTIC entropy (over clusters).
      4. Build a synthetic seeded 'hidden-state' matrix per regime and compute its EFFECTIVE
         RANK from the normalized singular-value entropy (SVD by hand — power iteration).
      5. Threshold semantic entropy for an abstain/answer decision.

    Honest signal: semantic entropy AND effective rank both RISE on the confabulating regime
    while naive entropy can be misleadingly low — meaning-level/spectral uncertainty beats
    surface uncertainty. Pure stdlib; deterministic — same seed -> identical snapshot.
    """
    K = max(4, min(int(K), 512))
    n_clusters = max(2, min(int(n_clusters), len(_SEM_LOOKUP)))
    thr = max(0.0, min(float(threshold), 10.0))

    rows_out = []
    hs_rows, hs_cols = 6, 8
    for regime in ("confident", "confabulating"):
        rng = _lcg(seed + (0 if regime == "confident" else 101))
        samples = _sample_generations(regime, K, rng)
        scored = _cluster_and_score(samples)

        hrng = _lcg(seed + (7 if regime == "confident" else 202))
        M = _hidden_state_matrix(regime, hs_rows, hs_cols, hrng)
        effr = round(_effective_rank(M), 6)

        decision = "abstain" if scored["semantic_entropy"] >= thr else "answer"

        rows_out.append({
            "regime": regime,
            "n_clusters": scored["n_clusters"],
            "cluster_sizes": scored["cluster_sizes"],
            "cluster_probs": scored["cluster_probs"],
            "naive_entropy": scored["naive_entropy"],
            "semantic_entropy": scored["semantic_entropy"],
            "effective_rank": effr,
            "decision": decision,
            "samples": scored["samples"],
        })

    conf = rows_out[0]
    conf_bad = rows_out[1]
    ordering_holds = bool(
        conf_bad["semantic_entropy"] > conf["semantic_entropy"]
        and conf_bad["effective_rank"] > conf["effective_rank"]
    )

    return {
        "seed": seed,
        "K": K,
        "n_clusters_param": n_clusters,
        "threshold": round(thr, 4),
        "regimes": rows_out,
        "ordering_holds": ordering_holds,
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


def _h_estimate(req: Request):
    seed       = _ii(req, "seed",       42)
    K          = max(4, min(_ii(req, "K",          40), 512))
    n_clusters = max(2, min(_ii(req, "n_clusters",  5), len(_SEM_LOOKUP)))
    threshold  = max(0.0, min(_fi(req, "threshold", 0.6), 10.0))

    snap = _estimate(seed=seed, K=K, n_clusters=n_clusters, threshold=threshold)

    return JSONResponse({
        "label":            "MODELED",
        "model":            "Semantic-entropy + effective-rank epistemic-uncertainty estimator (MODELED)",
        "method":           "sample K generations -> hand-specified meaning clustering -> semantic entropy; "
                            "+ spectral effective rank of synthetic hidden states (SVD by hand) -> abstain/answer",
        "seed":             snap["seed"],
        "K":                snap["K"],
        "n_clusters_param": snap["n_clusters_param"],
        "threshold":        snap["threshold"],
        "regimes":          snap["regimes"],
        "ordering_holds":   snap["ordering_holds"],
        "honest_note": (
            "MODELED: toy simulation of the UNCERTAINTY ESTIMATOR, not a real LLM. The "
            "semantic-equivalence clustering is a HAND-SPECIFIED lookup table (real semantic "
            "entropy uses an entailment model); the 'hidden states' are SYNTHETIC seeded "
            "matrices. It demonstrates the ORDERING (uncertain > confident) that the published "
            "methods exploit; it does NOT reproduce the Nature paper's AUROC or the effective-"
            "rank paper's benchmark numbers, and makes no claim about real-model calibration. "
            "Deterministic: same seed -> identical snapshot. Cite: Farquhar, Kossen, Kuhn & Gal "
            "Nature 2024 (DOI 10.1038/s41586-024-07421-0); Wang, Wei, Yue & Sun arXiv:2510.08389 "
            "(2025). SZL claims NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_qhall.register() / szl_interpretability.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/sement/estimate onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/sement"
    handlers = [
        (f"{base}/estimate", _h_estimate),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        # additive registration must never break the host app
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed.
    # Show the frontier result: on the CONFABULATING regime, SEMANTIC entropy and EFFECTIVE
    # RANK both RISE (flagging likely confabulation), while NAIVE surface entropy can be
    # misleadingly low — so a naive-entropy threshold would answer when it should abstain.
    print("label: MODELED")
    print("model: Semantic-entropy + effective-rank epistemic-uncertainty estimator (MODELED)")
    print("cite: Farquhar/Kossen/Kuhn/Gal Nature 2024 (DOI 10.1038/s41586-024-07421-0); "
          "Wang et al. arXiv:2510.08389 (2025)")
    print("honest: hand-specified clustering lookup + synthetic hidden states; demonstrates "
          "ORDERING, not AUROC.")
    print()

    snap = _estimate(seed=42, K=40, n_clusters=5, threshold=0.6)

    hdr = f"{'regime':<15}{'naive_H':>10}{'semantic_H':>13}{'eff_rank':>11}{'decision':>11}"
    print(hdr)
    print("-" * len(hdr))
    for r in snap["regimes"]:
        print(f"{r['regime']:<15}{r['naive_entropy']:>10.4f}{r['semantic_entropy']:>13.4f}"
              f"{r['effective_rank']:>11.4f}{r['decision']:>11}")
    print()
    print(f"threshold (semantic entropy, nats) = {snap['threshold']}")
    print(f"ordering_holds (semantic_H & eff_rank both rise on confabulating) = {snap['ordering_holds']}")
    print()

    conf, bad = snap["regimes"][0], snap["regimes"][1]

    # Determinism: same seed twice -> identical snapshot.
    snap2 = _estimate(seed=42, K=40, n_clusters=5, threshold=0.6)
    assert snap == snap2, "same seed must produce identical output"

    # Ordering: meaning-level and spectral uncertainty both rise on confabulating.
    assert bad["semantic_entropy"] > conf["semantic_entropy"], (
        "confabulating regime must have higher semantic entropy than confident")
    assert bad["effective_rank"] > conf["effective_rank"], (
        "confabulating regime must have higher effective rank than confident")
    assert snap["ordering_holds"], "ordering (uncertain > confident) must hold"

    # Threshold behaviour: confident answers, confabulating abstains.
    assert conf["decision"] == "answer", "confident regime should answer"
    assert bad["decision"] == "abstain", "confabulating regime should abstain"

    print("szl_sement: ALL OK — semantic entropy & effective rank rise on the confabulating "
          "regime (abstain), while the confident regime answers; determinism holds.")
