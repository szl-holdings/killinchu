# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_formalmath.py — ADDITIVE FORMAL-MATH PREMISE-RETRIEVAL simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/formalmath.js).

In formal theorem proving (Lean 4), the dominant bottleneck is PREMISE SELECTION: given the
current proof goal, retrieve the small set of library lemmas/definitions ("premises") that a
tactic will actually need out of a corpus of ~10^5 candidates. LeanDojo/ReProver (Yang, Swope, Gu
et al. 2023, arXiv:2306.15626) treats this as dense retrieval: embed the goal and every premise,
rank premises by cosine similarity to the goal, and feed the top-k into the prover. DeepSeek-
Prover-V2 (Ren, Shao, Song et al. 2025, arXiv:2504.21801) then decomposes a hard theorem into
subgoals and proves them with retrieved premises, integrating informal and formal reasoning.

This module reproduces the premise-RETRIEVAL mechanism deterministically. It builds a seeded
premise corpus with MODELED embeddings, embeds a MODELED goal, ranks premises by cosine
similarity, and reports retrieval quality against a seeded ground-truth "used premises" set:
Recall@k, precision@k, MRR, and nDCG@k over a top-k cut. The SZL addition is a J/query ENERGY
RECEIPT: dense retrieval of a k-premise context vs. feeding the whole library to the prover.

Deterministic retrieval model (seeded, no live model, no embeddings network):
  * a small seeded LCG PRNG builds `corpus_size` premise embeddings on the unit sphere in `dim`
    dimensions; a subset of `n_relevant` premises are the ground-truth "used premises" for the
    goal and are placed at a controlled cosine offset from the goal embedding (so retrieval is
    non-trivial but learnable — mirrors a trained retriever's separation).
  * rank all premises by cosine(goal, premise) descending; the top-k is the retrieved context.

  recall_at_k    = |retrieved_topk ∩ relevant| / |relevant|
  precision_at_k = |retrieved_topk ∩ relevant| / k
  mrr            = 1 / (rank of first relevant premise)
  ndcg_at_k      = DCG@k / IDCG@k     (binary relevance)
  E_full_context = corpus_size * e_premise_token   (naive: whole library into the prover)
  E_retrieved    = corpus_size * e_embed + k * e_premise_token  (embed-scan + top-k only)
  joules_per_query_saved = E_full_context - E_retrieved          (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic retrieval SIMULATION. NOT ReProver / DeepSeek-Prover-V2 running; NO live
    model, NO GPU, NO trained embeddings, NO Lean kernel, NO real mathlib corpus. The embeddings
    and the ground-truth relevant set are SEEDED MODELED values, NOT produced by a real retriever.
  * The retrieval RULE (cosine ranking + top-k, with Recall@k/MRR/nDCG scoring) is the field's
    actual premise-selection mechanism, honestly reimplemented; the numbers are properties of that
    rule over the seeded corpus, not a benchmark result on real mathlib.
  * This organ NEVER proves anything and NEVER adds to the locked-8; it only RETRIEVES candidate
    premises. Proof search is out of scope and explicitly ROADMAP.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/formalmath/retrieve  — premise-retrieval quality snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
import random as _random
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker, never fabricated
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.formalmath+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": __import__("base64").b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_FM_PAYLOAD_TYPE = "application/vnd.szl.kc.formalmath+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "leandojo": ("Yang, Swope, Gu, Chalamala, Song, Yu, Godil, Prenger, Anandkumar (2023) LeanDojo: "
                 "Theorem Proving with Retrieval-Augmented Language Models (ReProver premise "
                 "selection) — arXiv:2306.15626 — https://arxiv.org/abs/2306.15626"),
    "prover2": ("Ren, Shao, Song, Xin, Wang, Zhao, Zhang, Fu, Zhu, Yang, Wu, Gou, Ma, Tang, Liu, "
                "Gao, Guo, Ruan (2025) DeepSeek-Prover-V2: Advancing Formal Mathematical Reasoning "
                "via RL for Subgoal Decomposition — arXiv:2504.21801 — "
                "https://arxiv.org/abs/2504.21801"),
}

# MODELED label — a deterministic retrieval simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | PREMISE_RETRIEVAL_SIM | NOT_LIVE | NO_MODEL | NO_PROOF | JOULES_ARE_MODELED"

# MODELED per-unit energy references (order-of-magnitude only; NOT a live wattmeter).
_E_PREMISE_TOKEN = 1.0    # MODELED joules to push one premise through the prover context
_E_EMBED = 0.03           # MODELED joules to embed+score one premise in the retriever (cheap)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unit_vec(rng, dim: int):
    v = [rng.random() * 2.0 - 1.0 for _ in range(dim)]
    nrm = _math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / nrm for x in v]


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = _math.sqrt(sum(x * x for x in a)) or 1.0
    nb = _math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def formalmath_retrieve(seed: int = 42, corpus_size: int = 512, dim: int = 16,
                        n_relevant: int = 8, k: int = 16, separation: float = 0.4) -> dict:
    """Premise-retrieval quality snapshot (MODELED).

    corpus_size — number of candidate premises in the seeded library.
    dim         — MODELED embedding dimension.
    n_relevant  — ground-truth number of premises actually used by the goal's proof.
    k           — top-k retrieved into the prover context.
    separation  — how far relevant premises are pulled toward the goal (retriever quality knob).
    seed        — RNG seed; identical inputs give identical output (deterministic).
    """
    corpus_size = max(8, min(200_000, int(corpus_size)))
    dim = max(4, min(256, int(dim)))
    n_relevant = max(1, min(corpus_size, int(n_relevant)))
    k = max(1, min(corpus_size, int(k)))
    separation = max(0.0, min(0.95, float(separation)))
    rng = _random.Random(int(seed) * 1_000_003 + corpus_size * 131 + k * 17 + dim)

    goal = _unit_vec(rng, dim)
    relevant_ids = set()
    # deterministically choose the relevant premise ids
    while len(relevant_ids) < n_relevant:
        relevant_ids.add(rng.randrange(corpus_size))

    scored = []  # (premise_id, cosine)
    for pid in range(corpus_size):
        base = _unit_vec(rng, dim)
        if pid in relevant_ids:
            # pull relevant premise toward the goal (retriever separates them)
            mixed = [(1.0 - separation) * base[i] + separation * goal[i] for i in range(dim)]
            nrm = _math.sqrt(sum(x * x for x in mixed)) or 1.0
            emb = [x / nrm for x in mixed]
        else:
            emb = base
        scored.append((pid, _cosine(goal, emb)))

    scored.sort(key=lambda t: t[1], reverse=True)
    ranked_ids = [pid for pid, _ in scored]
    topk = ranked_ids[:k]
    topk_set = set(topk)

    hits = len(topk_set & relevant_ids)
    recall_at_k = hits / len(relevant_ids)
    precision_at_k = hits / k

    # MRR: reciprocal rank of the first relevant premise in the full ranking.
    mrr = 0.0
    for rank, pid in enumerate(ranked_ids, start=1):
        if pid in relevant_ids:
            mrr = 1.0 / rank
            break

    # nDCG@k with binary relevance.
    dcg = 0.0
    for i, pid in enumerate(topk):
        if pid in relevant_ids:
            dcg += 1.0 / _math.log2(i + 2)
    ideal_hits = min(k, len(relevant_ids))
    idcg = sum(1.0 / _math.log2(i + 2) for i in range(ideal_hits))
    ndcg_at_k = (dcg / idcg) if idcg else 0.0

    top_cosines = [round(float(c), 5) for _, c in scored[:min(16, k)]]

    # ENERGY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    e_full = corpus_size * _E_PREMISE_TOKEN                          # whole library into prover
    e_retrieved = corpus_size * _E_EMBED + k * _E_PREMISE_TOKEN      # embed-scan + top-k only
    joules_saved = e_full - e_retrieved
    joules_per_query_saved = joules_saved
    energy_reduction_pct = (joules_saved / e_full * 100.0) if e_full else 0.0

    energy_receipt = {
        "joules_full_context": round(float(e_full), 4),
        "joules_retrieved": round(float(e_retrieved), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_query_saved": round(float(joules_per_query_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_premise_token_modeled": _E_PREMISE_TOKEN,
        "e_embed_modeled": _E_EMBED,
        "energy_note": ("MODELED joules — order-of-magnitude per-premise estimates, NOT a live "
                        "wattmeter. Retrieving a k-premise context instead of the whole library is "
                        "the energy win; quantified as a receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "formal-math-premise-retrieval",
        "service_version": "szl-kc-formalmath-v0.1",
        "seed": int(seed),
        "inputs": {"corpus_size": corpus_size, "dim": dim, "n_relevant": n_relevant,
                   "k": k, "separation": separation},
        "recall_at_k": round(float(recall_at_k), 6),
        "precision_at_k": round(float(precision_at_k), 6),
        "mrr": round(float(mrr), 6),
        "ndcg_at_k": round(float(ndcg_at_k), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (retrieval advisory — never an autonomous action)",
        "citations": [CITATIONS["leandojo"], CITATIONS["prover2"]],
        "honesty": ("Deterministic dense premise-retrieval simulation over a seeded premise corpus. "
                    "NOT ReProver / DeepSeek-Prover-V2 running; NO live model, NO GPU, NO trained "
                    "embeddings, NO Lean kernel, NO real mathlib. This organ RETRIEVES candidates "
                    "only; it NEVER proves anything and NEVER adds to the locked-8. MODELED, not "
                    "live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _FM_PAYLOAD_TYPE)

    return {
        "service": "formal-math-premise-retrieval",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/formalmath.js ---
        "corpus_size": int(corpus_size),
        "dim": int(dim),
        "n_relevant": int(n_relevant),
        "k": int(k),
        "separation": round(float(separation), 4),
        "recall_at_k": round(float(recall_at_k), 6),
        "precision_at_k": round(float(precision_at_k), 6),
        "mrr": round(float(mrr), 6),
        "ndcg_at_k": round(float(ndcg_at_k), 6),
        "hits_at_k": int(hits),
        "top_cosines": top_cosines,   # [float]
        "proves_nothing": True,
        "locked_proven": 8,
        # --- SZL addition: the J/query-saved energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "recall_at_k": "|topk ∩ relevant| / |relevant|",
            "precision_at_k": "|topk ∩ relevant| / k",
            "mrr": "1 / rank(first relevant premise)",
            "ndcg_at_k": "DCG@k / IDCG@k (binary relevance)",
            "ranking": "premises sorted by cosine(goal, premise) descending",
            "joules_per_query_saved": "E_full_context - E_retrieved",
            "E_full_context": "corpus_size * e_premise_token",
            "E_retrieved": "corpus_size * e_embed + k * e_premise_token",
        },
        "compute_backend": {
            "backend": "CPU pure-Python dense-retrieval simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic cosine-ranking retrieval sim; NO live model, NO GPU, NO "
                            "trained embeddings, NO Lean kernel. Proof search is ROADMAP; this "
                            "organ never proves and never adds to the locked-8."),
        },
        "wired_into": "frontier ring — Formal-Math premise-retrieval surface + llm-router energy receipt",
        "citations": [CITATIONS["leandojo"], CITATIONS["prover2"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/formalmath" % ns

    @app.get("%s/retrieve" % base)
    async def _kc_formalmath(seed: int = 42, corpus_size: int = 512, dim: int = 16,
                             n_relevant: int = 8, k: int = 16,
                             separation: float = 0.4):  # noqa: ANN202
        try:
            return JSONResponse(formalmath_retrieve(seed=seed, corpus_size=corpus_size, dim=dim,
                                                    n_relevant=n_relevant, k=k,
                                                    separation=separation))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "formal-math-premise-retrieval",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "recall_at_k": None, "mrr": None},
                                status_code=200)

    # Starlette Route fallback.
    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_formalmath_route(request):  # pragma: no cover — fallback path
            q = request.query_params
            try:
                return _SJSON(formalmath_retrieve(
                    seed=int(q.get("seed", 42)),
                    corpus_size=int(q.get("corpus_size", 512)),
                    dim=int(q.get("dim", 16)),
                    n_relevant=int(q.get("n_relevant", 8)),
                    k=int(q.get("k", 16)),
                    separation=float(q.get("separation", 0.4))))
            except Exception as exc:
                return _SJSON({"service": "formal-math-premise-retrieval",
                               "label": MODELED_LABEL,
                               "error": "compute fail-open: %s" % (str(exc)[:160])},
                              status_code=200)

        if not any(getattr(r, "path", None) == "%s/retrieve" % base
                   for r in getattr(app.router, "routes", [])):
            app.router.routes.append(Route("%s/retrieve" % base, _kc_formalmath_route,
                                           methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": ["%s/retrieve" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = formalmath_retrieve(seed=42, corpus_size=512, dim=16, n_relevant=8, k=16)

    # (a) honest label verbatim + every field the frontend reads present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("corpus_size", "dim", "n_relevant", "k", "hits_at_k", "locked_proven"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k", "separation"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["top_cosines"], list) and r["top_cosines"], r
    assert all(isinstance(x, (int, float)) for x in r["top_cosines"]), r["top_cosines"]

    # (b) surface-specific invariants: metrics in [0,1]; retrieval beats random; never proves;
    #     locked-8 untouched; cosines sorted descending.
    for m in ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"):
        assert 0.0 <= r[m] <= 1.0, (m, r[m])
    assert r["hits_at_k"] <= r["n_relevant"], r
    # a working retriever must beat the random-recall baseline k/corpus_size
    assert r["recall_at_k"] > r["k"] / r["corpus_size"], (r["recall_at_k"], r["k"], r["corpus_size"])
    assert r["proves_nothing"] is True, r
    assert r["locked_proven"] == 8, r
    tc = r["top_cosines"]
    assert all(tc[i] >= tc[i + 1] - 1e-9 for i in range(len(tc) - 1)), tc
    out["metrics"] = {"recall_at_k": r["recall_at_k"], "precision_at_k": r["precision_at_k"],
                      "mrr": r["mrr"], "ndcg_at_k": r["ndcg_at_k"], "hits_at_k": r["hits_at_k"]}

    # (c) energy receipt: positive joules saved on this profile.
    er = r["energy_receipt"]
    assert er["joules_saved"] > 0, er
    assert er["joules_per_query_saved"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"joules_saved": er["joules_saved"],
                             "joules_per_query_saved": er["joules_per_query_saved"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical retrieval.
    r2 = formalmath_retrieve(seed=42, corpus_size=512, dim=16, n_relevant=8, k=16)
    assert r2["top_cosines"] == r["top_cosines"], "non-deterministic"
    assert r2["recall_at_k"] == r["recall_at_k"], "non-deterministic recall"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    assert res["ok"] is True
    print("ALL OK")
