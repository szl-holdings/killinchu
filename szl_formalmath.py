# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_formalmath.py — SZL formal-math retrieval-augmented tactic-selection endpoint
(LeanDojo/ReProver-style premise retrieval + best-first proof-search simulation).

Exposes a MODELED, deterministic, pure-stdlib simulation of the two ideas at the
core of retrieval-augmented neural theorem proving for Lean:

  1. PREMISE RETRIEVAL — given a goal (a synthetic Lean-style proof-state string),
     retrieve the top-k most relevant premises from a small built-in toy corpus of
     Lean-style premise names (e.g. "Nat.add_comm", "List.map_cons") by COSINE
     SIMILARITY over hand-rolled bag-of-tokens vectors. Premise names are tokenized
     by splitting on '.'/'_' (mirroring Lean's dotted-namespace / snake_case naming
     convention); each premise becomes a sparse term-count dict; similarity vs the
     (tokenized) goal string is computed with plain dict-intersection dot products
     and math.sqrt norms — NO numpy, no embeddings, no neural encoder. This is a
     clean-room, hand-rolled stand-in for the *concept* of the ReProver premise
     retriever, which in the real system embeds proof states and premises with a
     trained ByT5 encoder and ranks by cosine similarity in that learned embedding
     space (Yang et al. 2023, LeanDojo/ReProver, NeurIPS 2023).

  2. BEST-FIRST PROOF SEARCH — a deterministic heapq priority queue explores a
     small synthetic tactic tree (each node = a partial proof state with a set of
     candidate child tactics/subgoals). Priority is a MODELED score: the retrieved
     premises' similarity scores BIAS which branches get expanded first (higher
     avg. premise-similarity along a branch => explored earlier), loosely echoing
     how ReProver's tactic generator conditions on retrieved premises to choose
     the next tactic, and how DeepSeek-Prover-V2 / general theorem-proving search
     loops interleave premise-conditioned tactic proposal with tree/best-first
     search (DeepSeek-AI et al. 2025, DeepSeek-Prover-V2, arXiv:2504.21801). The
     search here is a closed-form, seeded, synthetic simulation — no real Lean 4
     kernel, no real Mathlib, no tactic execution of any kind.

  GET  /api/<ns>/v1/formalmath/retrieve?seed=&goal=&corpus_size=&k=

Returned JSON fields
---------------------
  label                       : "MODELED" (always)
  model                       : short model-family name
  seed                        : RNG seed used (deterministic corpus/tree synthesis)
  goal                        : the (possibly truncated) synthetic goal string used
  corpus_size                 : number of premises in the built-in toy corpus
  k                           : number of top premises retrieved
  top_k_premises              : [{name, similarity}, ...] ranked descending
  similarity_scores           : {premise_name: cosine_similarity, ...} for the full corpus
  simulated_proof_tree_depth  : depth reached by the best-first search
  nodes_expanded              : number of tactic-tree nodes popped from the priority queue
  search_trace                : [{node_id, depth, priority, tactic, premise_bias}, ...]
                                 in pop order (bounded sample)
  method_retrieval            : plain-language description of the retrieval method
  method_search               : plain-language description of the search method
  honest_note                 : plain-language honesty disclaimer
  citations                   : dict of citable sources
  computed_at                 : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib, hand-rolled bag-of-tokens cosine-similarity
  retriever plus a deterministic heapq best-first search over a SYNTHETIC toy tactic
  tree. It is NOT connected to Lean 4, NOT connected to Mathlib, uses NO trained
  embedding model, and is NEVER-CLAIMED-AS DeepSeek-Prover or ReProver output. It is
  a clean-room simulation of the *concept* those systems popularized: retrieval of
  relevant premises to bias/guide tactic-level proof search. The label "MODELED" is
  returned verbatim and displayed verbatim by the surface; it is never upgraded
  client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  LeanDojo (data extraction + Lean interaction toolkit; premise-annotated benchmark):
    Yang, Swope, Gu, Chalamala, Song, Yu, Godil, Prenger & Anandkumar (2023)
    "LeanDojo: Theorem Proving with Retrieval-Augmented Language Models".
    NeurIPS 2023 (Datasets and Benchmarks Track).
    https://github.com/lean-dojo/LeanDojo
  ReProver (Retrieval-Augmented Prover; ByT5 dual-encoder premise retriever +
    retrieval-augmented tactic generator):
    lean-dojo/ReProver, companion implementation to the LeanDojo paper above.
    https://github.com/lean-dojo/ReProver
  DeepSeek-Prover-V2 (large-scale open formal-math LLM; subgoal decomposition +
    recursive proof search pipeline for Lean 4):
    DeepSeek-AI et al. (2025) "DeepSeek-Prover-V2: Advancing Formal Mathematical
    Reasoning via Reinforcement Learning for Subgoal Decomposition". arXiv:2504.21801.
    https://arxiv.org/abs/2504.21801
  HONEST-STUB note: the toy premise corpus, the bag-of-tokens vectorization, and the
  synthetic tactic tree / best-first priority function are SZL's own closed-form
  MODELED choices, selected to demonstrate the qualitative *shape* of retrieval-
  augmented tactic selection. They are not a re-implementation of LeanDojo's ByT5
  retriever, ReProver's tactic generator, or DeepSeek-Prover-V2's training pipeline,
  and report NONE of those systems' benchmark numbers.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (math/heapq/hashlib/collections only — no numpy).
  Deterministic with seed. 0 runtime CDN. No LLM calls of any kind. NOT connected to
  Lean 4 or Mathlib.
"""
from __future__ import annotations

import hashlib
import heapq
import math
from collections import Counter
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "LeanDojo — Yang et al. 2023, NeurIPS (Datasets and Benchmarks Track)": "https://github.com/lean-dojo/LeanDojo",
    "ReProver (Retrieval-Augmented Prover) — lean-dojo/ReProver": "https://github.com/lean-dojo/ReProver",
    "DeepSeek-Prover-V2 — DeepSeek-AI et al. 2025, arXiv:2504.21801": "https://arxiv.org/abs/2504.21801",
}

# ---------------------------------------------------------------------------
# Toy Lean-style premise corpus (clean-room, hand-authored; names ECHO Mathlib
# naming CONVENTIONS — dotted namespaces / snake_case — but are NOT extracted
# from any real Mathlib source and do not assert any real Mathlib lemma exists
# with this exact signature). Used purely as retrieval-demo vocabulary.
# ---------------------------------------------------------------------------
_TOY_CORPUS = [
    "Nat.add_comm", "Nat.add_assoc", "Nat.mul_comm", "Nat.mul_assoc",
    "Nat.zero_add", "Nat.add_zero", "Nat.succ_eq_add_one", "Nat.le_refl",
    "Nat.le_trans", "Nat.lt_irrefl", "Nat.mod_self", "Nat.div_add_mod",
    "Int.add_comm", "Int.neg_neg", "Int.sub_self", "Int.mul_comm",
    "List.map_cons", "List.map_append", "List.length_cons", "List.length_append",
    "List.reverse_reverse", "List.append_assoc", "List.mem_cons_self",
    "List.filter_append", "List.foldr_cons", "List.sum_cons",
    "Set.union_comm", "Set.inter_comm", "Set.union_assoc", "Set.subset_refl",
    "Set.mem_union", "Set.mem_inter_iff", "Set.union_empty", "Set.inter_empty",
    "Finset.sum_add_distrib", "Finset.card_union_le", "Finset.mem_filter",
    "Group.mul_left_inv", "Group.mul_assoc", "Group.one_mul", "Group.mul_one",
    "Ring.mul_add", "Ring.add_mul", "Ring.zero_mul", "Ring.mul_zero",
    "Order.le_antisymm", "Order.lt_trans", "Order.le_of_lt",
    "Continuous.comp", "Continuous.add", "Continuous.mul",
    "Topology.isOpen_union", "Topology.isOpen_inter", "Topology.isClosed_compl",
    "Real.sqrt_nonneg", "Real.add_sq", "Real.abs_le", "Real.exp_pos",
    "Polynomial.eval_add", "Polynomial.eval_mul", "Polynomial.degree_add_le",
]

_LCG_A = 1103515245
_LCG_C = 12345
_LCG_M = 2 ** 31


def _lcg_stream(seed: int, n: int):
    """Deterministic LCG stream of n floats in [0,1). Pure stdlib, no random module."""
    x = seed % _LCG_M
    out = []
    for _ in range(n):
        x = (_LCG_A * x + _LCG_C) % _LCG_M
        out.append(x / _LCG_M)
    return out


def _stable_hash01(s: str, seed: int) -> float:
    """Deterministic, seed-mixed float in [0,1) derived from sha256(s+seed).
    Pure stdlib (hashlib), used to give each toy tactic a reproducible
    'branch quality' jitter without any numpy/random dependency."""
    h = hashlib.sha256(f"{seed}:{s}".encode("utf-8")).hexdigest()
    return int(h[:12], 16) / float(16 ** 12)


# ---------------------------------------------------------------------------
# 1. Tokenization + bag-of-tokens vectorization
# ---------------------------------------------------------------------------
def _tokenize(name: str):
    """Split a Lean-style dotted/snake_case premise name (or goal string) into
    lowercase tokens on '.' and '_' boundaries. Pure stdlib string ops."""
    out = []
    for chunk in name.replace(".", " ").replace("_", " ").split():
        t = chunk.strip().lower()
        if t:
            out.append(t)
    return out


def _term_counts(tokens):
    """Sparse term-count dict (bag-of-tokens) — pure collections.Counter."""
    return dict(Counter(tokens))


def _cosine_sim(a: dict, b: dict) -> float:
    """Cosine similarity between two sparse term-count dicts. Pure math.sqrt,
    intersecting keys for the dot product — NO numpy."""
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _build_corpus(corpus_size: int):
    """Deterministic corpus slice: first corpus_size names from the toy corpus
    (stable order => stable output for a given corpus_size)."""
    n = max(1, min(corpus_size, len(_TOY_CORPUS)))
    return _TOY_CORPUS[:n]


def _retrieve_premises(goal: str, corpus_size: int, k: int, seed: int):
    corpus = _build_corpus(corpus_size)
    goal_vec = _term_counts(_tokenize(goal))

    sims = {}
    for name in corpus:
        premise_vec = _term_counts(_tokenize(name))
        sims[name] = round(_cosine_sim(goal_vec, premise_vec), 8)

    # deterministic tie-break: sort by (-similarity, name) so identical scores
    # resolve in a stable, reproducible order without relying on dict order
    # tie-break jitter (no randomness needed since name is already unique).
    ranked = sorted(corpus, key=lambda nm: (-sims[nm], nm))
    top_k = ranked[: max(1, min(k, len(corpus)))]
    top_k_premises = [{"name": nm, "similarity": sims[nm]} for nm in top_k]
    return corpus, sims, top_k_premises


# ---------------------------------------------------------------------------
# 2. Best-first proof-search simulation over a synthetic tactic tree
# ---------------------------------------------------------------------------
# Each synthetic tactic-tree node has a small fixed branching factor; tactics
# are drawn from a short deterministic pool so the tree is reproducible from
# (seed, goal, k). Retrieved premises BIAS the priority: a branch whose
# deterministic "premise_bias" token matches (prefix-overlaps) a top-k
# retrieved premise gets a priority boost, loosely modeling how a retrieval-
# augmented tactic generator would prefer branches consistent with retrieved
# premises (ReProver-style conditioning; DeepSeek-Prover-V2-style subgoal
# search). This is a MODELED heuristic, not a learned policy.
_TACTIC_POOL = [
    "rw", "simp", "ring", "linarith", "exact", "apply", "intro", "constructor",
    "cases", "induction", "omega", "field_simp", "norm_num", "unfold",
]

_BRANCH_FACTOR = 3
_MAX_DEPTH = 6
_MAX_NODES = 400


def _best_first_search(top_k_premises, seed: int, max_depth: int = _MAX_DEPTH):
    """Deterministic best-first search via heapq. Lower priority value = popped
    first (heapq is a min-heap); we define priority = -(score) so higher-score
    branches pop first. score = premise_bias_boost - depth_penalty + jitter.
    Pure stdlib: heapq only, no numpy."""
    premise_names = [p["name"] for p in top_k_premises]
    premise_sim_by_name = {p["name"]: p["similarity"] for p in top_k_premises}
    top_similarity = top_k_premises[0]["similarity"] if top_k_premises else 0.0

    # counter used to keep heap entries strictly orderable when priorities tie
    # (heapq compares tuples element-wise; a monotonically increasing tie-
    # breaker avoids comparing non-comparable dict payloads).
    counter = 0
    node_id = 0

    # root node
    root_priority = -1.0  # most-negative => highest priority => popped first
    heap = [(root_priority, counter, {"node_id": node_id, "depth": 0, "tactic": "start", "premise_bias": None})]
    counter += 1
    node_id += 1

    nodes_expanded = 0
    max_depth_reached = 0
    trace = []

    while heap and nodes_expanded < _MAX_NODES:
        priority, _, node = heapq.heappop(heap)
        nodes_expanded += 1
        depth = node["depth"]
        max_depth_reached = max(max_depth_reached, depth)

        if len(trace) < 64:  # bounded sample for payload size
            trace.append({
                "node_id": node["node_id"],
                "depth": depth,
                "priority": round(-priority, 6),
                "tactic": node["tactic"],
                "premise_bias": node["premise_bias"],
            })

        if depth >= max_depth:
            continue

        # expand a fixed branching factor of deterministic children
        for b in range(_BRANCH_FACTOR):
            child_key = f"{node['node_id']}:{b}:{depth}"
            jitter = _stable_hash01(child_key, seed)  # deterministic in [0,1)
            tactic = _TACTIC_POOL[int(jitter * len(_TACTIC_POOL)) % len(_TACTIC_POOL)]

            # premise bias: if a retrieved premise's tokens share a prefix
            # letter-family with this branch's deterministic hash, treat this
            # branch as "premise-consistent" and boost its priority by that
            # premise's similarity score (MODELED heuristic).
            bias_name = None
            bias_score = 0.0
            if premise_names:
                idx = int(jitter * 1000) % len(premise_names)
                bias_name = premise_names[idx]
                bias_score = premise_sim_by_name.get(bias_name, 0.0)

            depth_penalty = 0.08 * (depth + 1)
            score = (0.65 * bias_score) + (0.35 * top_similarity) - depth_penalty + (0.01 * jitter)
            child_priority = -score

            heapq.heappush(heap, (child_priority, counter, {
                "node_id": node_id, "depth": depth + 1, "tactic": tactic, "premise_bias": bias_name,
            }))
            counter += 1
            node_id += 1

    return {
        "simulated_proof_tree_depth": max_depth_reached,
        "nodes_expanded": nodes_expanded,
        "search_trace": trace,
    }


# ---------------------------------------------------------------------------
# Top-level model function
# ---------------------------------------------------------------------------
_DEFAULT_GOAL = "theorem add_comm_example (a b : Nat) : a + b = b + a"


def _formalmath_model(seed: int = 42, goal: str = _DEFAULT_GOAL, corpus_size: int = 24, k: int = 5) -> dict:
    goal = (goal or _DEFAULT_GOAL).strip()[:400]  # bound payload size
    corpus_size = max(1, min(int(corpus_size), len(_TOY_CORPUS)))
    k = max(1, min(int(k), corpus_size))

    corpus, sims, top_k_premises = _retrieve_premises(goal, corpus_size, k, seed)
    search = _best_first_search(top_k_premises, seed)

    return {
        "goal": goal,
        "corpus_size": len(corpus),
        "k": k,
        "top_k_premises": top_k_premises,
        "similarity_scores": sims,
        **search,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _si(req: Request, key: str, default: str) -> str:
    v = req.query_params.get(key, default)
    return v if isinstance(v, str) and v.strip() else default


def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_retrieve(req: Request):
    seed = _ii(req, "seed", 42)
    goal = _si(req, "goal", _DEFAULT_GOAL)
    corpus_size = max(1, min(_ii(req, "corpus_size", 24), len(_TOY_CORPUS)))
    k = max(1, min(_ii(req, "k", 5), corpus_size))

    m = _formalmath_model(seed=seed, goal=goal, corpus_size=corpus_size, k=k)

    return JSONResponse({
        "label": "MODELED",
        "model": "Deterministic bag-of-tokens cosine premise retrieval + best-first proof-search simulation (LeanDojo/ReProver-style)",
        "seed": seed,
        **m,
        "method_retrieval": (
            "Premise names are tokenized by splitting on '.'/'_' (Lean dotted-namespace / "
            "snake_case convention), converted to sparse term-count (bag-of-tokens) dicts, and "
            "ranked against the (tokenized) goal string by cosine similarity computed with plain "
            "dict-intersection dot products and math.sqrt norms. No embeddings, no neural encoder, "
            "no numpy — this is a hand-rolled, clean-room stand-in for the *concept* of ReProver's "
            "trained ByT5 premise retriever (Yang et al. 2023, LeanDojo/ReProver)."
        ),
        "method_search": (
            "A deterministic heapq best-first search explores a small synthetic tactic tree "
            "(fixed branching factor, deterministic per-branch tactic + premise-bias hashing via "
            "hashlib.sha256). Branches whose deterministic 'premise_bias' token matches a top-k "
            "retrieved premise get a priority boost proportional to that premise's cosine "
            "similarity, loosely modeling how a retrieval-conditioned tactic generator would "
            "prefer premise-consistent branches (ReProver-style conditioning; DeepSeek-Prover-V2 "
            "-style subgoal search, DeepSeek-AI et al. 2025, arXiv:2504.21801). Pure heapq, no "
            "learned policy, no real tactic execution."
        ),
        "honest_note": (
            "MODELED: deterministic bag-of-tokens cosine retrieval + best-first search simulation "
            "of the LeanDojo/ReProver premise-selection concept. NOT connected to Lean 4 or "
            "Mathlib. NEVER-CLAIMED-AS DeepSeek-Prover or ReProver output. The toy premise corpus, "
            "vectorization, and tactic-tree/priority function are SZL's own closed-form choices; "
            "no proprietary model, no LLM calls, no Lean kernel invocation, no re-implementation "
            "of any cited system's trained weights or benchmark numbers. Deterministic: same "
            "seed/goal/corpus_size/k -> identical output. SZL claims NONE of these methods as its "
            "own."
        ),
        "citations": CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_testtime.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/formalmath/retrieve onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/formalmath"
    handlers = [
        (f"{base}/retrieve", _h_retrieve),
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
    print("goal:", _DEFAULT_GOAL)
    print()

    m = _formalmath_model(seed=42, goal=_DEFAULT_GOAL, corpus_size=24, k=5)
    print("corpus_size:", m["corpus_size"])
    print("k:", m["k"])
    print("top_k_premises:")
    for row in m["top_k_premises"]:
        print(f"  {row['name']:<28} similarity={row['similarity']:.8f}")
    print()
    print("simulated_proof_tree_depth:", m["simulated_proof_tree_depth"])
    print("nodes_expanded:", m["nodes_expanded"])
    print("search_trace[:5]:")
    for row in m["search_trace"][:5]:
        print(f"  {row}")

    # sanity: deterministic — same inputs => identical output byte-for-byte
    m2 = _formalmath_model(seed=42, goal=_DEFAULT_GOAL, corpus_size=24, k=5)
    assert m == m2, "formalmath model is not deterministic for identical inputs!"

    # sanity: top_k_premises sorted descending by similarity
    sim_vals = [row["similarity"] for row in m["top_k_premises"]]
    assert sim_vals == sorted(sim_vals, reverse=True), f"top_k_premises not sorted descending: {sim_vals}"

    # sanity: the top-similarity premise for the add_comm goal should be a
    # commutativity-flavored premise (shares tokens 'add'/'comm' with the goal).
    top_name = m["top_k_premises"][0]["name"]
    assert "comm" in top_name.lower() or "add" in top_name.lower(), (
        f"expected an add/comm premise on top for an add_comm goal, got {top_name}"
    )

    # sanity: nodes_expanded bounded and positive; depth within configured max
    assert 0 < m["nodes_expanded"] <= _MAX_NODES
    assert 0 <= m["simulated_proof_tree_depth"] <= _MAX_DEPTH

    # sanity: cosine similarity values are all within [0,1] (bag-of-tokens, non-negative counts)
    for row in m["top_k_premises"]:
        assert 0.0 <= row["similarity"] <= 1.0 + 1e-9

    print()
    print("szl_formalmath: ALL OK — deterministic, sorted top-k, bounded search, sane similarity range.")
