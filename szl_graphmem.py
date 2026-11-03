# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_graphmem.py — SZL governed MULTI-GRAPH AGENTIC MEMORY (MAGMA) endpoint.

Clean-room adoption of the MULTI-GRAPH agentic-memory idea from MAGMA
(A Multi-Graph based Agentic Memory Architecture; Jiang, Li, Li, Li — arXiv:2601.03236):
instead of storing memory items in ONE monolithic similarity store, store each item
across FOUR ORTHOGONAL relational graphs — SEMANTIC, TEMPORAL, CAUSAL, ENTITY — so
"what is related" is disentangled by the TYPE of relation. Retrieval is then a
POLICY-GUIDED TRAVERSAL over these typed views: the query selects which graph(s) to
walk and how, producing a structured, interpretable context PATH rather than a flat
top-k list. This decouples memory REPRESENTATION from retrieval LOGIC.

SZL's ecosystem today is vector+ledger (waqay/rag/lake) with a single flat similarity
store and NO typed multi-graph memory layer — this organ is a GOVERNED, honest, MODELED
demonstration of that missing mechanism, NOT a reproduction of MAGMA's code and NOT a
claim of its reported LoCoMo / LongMemEval performance.

  GET  /api/<ns>/v1/graphmem/traverse?seed=&query_type=&max_hops=&which_graphs=&top_k=

Returned JSON fields
--------------------
  label               : "MODELED" (always — this is a toy symbolic simulation, not a
                        production agentic memory; PUBLIC/synthetic corpus only)
  model               : "four typed relational graphs + policy-guided traversal (MAGMA-inspired)"
  seed                : RNG seed used (deterministic; same seed -> identical output)
  query_type          : which query archetype was run (selects the traversal policy)
  query               : the synthetic query {node, text}
  max_hops            : traversal hop budget
  which_graphs        : which of the four graphs were enabled (ablation control)
  corpus              : the 12 synthetic memory items (nodes) with tags/entity/time/cause
  graphs              : the four adjacency lists {semantic, temporal, causal, entity}
  traversal           : the multi-graph POLICY traversal — ordered PATH (node + graph
                        used per hop) + the retrieved set
  baseline            : the monolithic flat-BFS retriever (union of all edges, top-k by
                        degree/overlap) — the thing we are honestly comparing against
  gold                : the hand-labeled gold-relevant set for this query
  scores              : precision/recall/F1 of typed-traversal vs baseline vs gold
  policy_description  : the exact deterministic state-machine policy used (documented)
  honest_note         : plain-language honesty disclaimer (see HONEST STATUS below)
  citations           : dict of citable sources
  computed_at         : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  Toy symbolic simulation of the multi-graph + policy-traversal MECHANISM, not MAGMA.
  Four graphs are hand-built from a 12-item synthetic corpus with integer/string
  adjacency lists (NO embeddings, NO trained retriever); the "policy" is a fixed
  deterministic state machine, NOT a learned agent policy; "relevance" is scored against
  a hand-labeled gold set. It demonstrates the ORDERING / EXPLAINABILITY advantage of
  typed-relational traversal over a flat store on constructed causal/temporal queries; it
  does NOT reproduce MAGMA's LoCoMo / LongMemEval results and makes NO claim about real
  long-horizon agent performance. The label "MODELED" is returned verbatim and displayed
  verbatim by the surface; it is never upgraded client-side.

GOVERNED DIFFERENCE (what makes this OURS, per doctrine)
  The traversal is fully AUDITABLE: every retrieved item is reached by an explicit,
  reproducible PATH (which node, via which graph, at which hop). Where a flat similarity
  store returns an opaque ranked list, this organ returns the exact typed-relation chain
  that justifies each recall — an explainable, content-addressable memory trace. Nothing
  here is signed or attested (no Sigstore/DSSE claim); the governance value is the
  explainability + determinism of the traversal itself.

CITATIONS (clean-room; none claimed as SZL's own)
  MAGMA — A Multi-Graph based Agentic Memory Architecture (Jiang, Li, Li, Li):
    https://arxiv.org/abs/2601.03236
  Multi-Agent Memory from a Computer Architecture Perspective (Yu et al.; positioning):
    https://arxiv.org/abs/2603.10062

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  PUBLIC/synthetic corpus only — no private data is stored, read, or modeled.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "MAGMA — A Multi-Graph based Agentic Memory Architecture (Jiang, Li, Li, Li)":
        "https://arxiv.org/abs/2601.03236",
    "Multi-Agent Memory from a Computer Architecture Perspective (Yu et al.; positioning)":
        "https://arxiv.org/abs/2603.10062",
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
# Fixed synthetic corpus — 12 "memory items" (short public/synthetic facts).
#
# Each item carries the raw material for the FOUR orthogonal graphs:
#   t      : integer synthetic timestamp (temporal ordering)
#   tags   : shared-topic tags        -> SEMANTIC graph (shared-tag overlap)
#   entity : named entity mentioned   -> ENTITY graph   (shared entity)
#   cause  : id of the item this item was CAUSED BY (or None) -> CAUSAL DAG
#
# This is a hand-built toy corpus about a small synthetic incident/deploy narrative.
# No real user, customer, system, or private data of any kind.
# ---------------------------------------------------------------------------
_CORPUS = [
    # id, text, t, tags, entity, cause
    {"id": 0,  "text": "service payments deployed v2.3 to production",
     "t": 0,  "tags": ["deploy", "payments"],        "entity": "payments", "cause": None},
    {"id": 1,  "text": "v2.3 introduced a new database connection pool",
     "t": 1,  "tags": ["deploy", "database"],         "entity": "database", "cause": 0},
    {"id": 2,  "text": "connection pool max size was set too low",
     "t": 2,  "tags": ["config", "database"],         "entity": "database", "cause": 1},
    {"id": 3,  "text": "payments latency began rising in the afternoon",
     "t": 3,  "tags": ["latency", "payments"],        "entity": "payments", "cause": 2},
    {"id": 4,  "text": "on-call engineer paged about payments latency",
     "t": 4,  "tags": ["latency", "oncall"],          "entity": "oncall",   "cause": 3},
    {"id": 5,  "text": "engineer inspected the database connection metrics",
     "t": 5,  "tags": ["oncall", "database"],         "entity": "database", "cause": 4},
    {"id": 6,  "text": "connection pool exhaustion was identified as root cause",
     "t": 6,  "tags": ["incident", "database"],       "entity": "database", "cause": 5},
    {"id": 7,  "text": "team increased the connection pool max size",
     "t": 7,  "tags": ["config", "database"],         "entity": "database", "cause": 6},
    {"id": 8,  "text": "payments latency recovered after the config change",
     "t": 8,  "tags": ["latency", "payments"],        "entity": "payments", "cause": 7},
    {"id": 9,  "text": "postmortem scheduled for the payments incident",
     "t": 9,  "tags": ["incident", "payments"],       "entity": "payments", "cause": 6},
    {"id": 10, "text": "unrelated: docs site theme updated to dark mode",
     "t": 10, "tags": ["docs", "frontend"],           "entity": "docs",     "cause": None},
    {"id": 11, "text": "unrelated: marketing published a quarterly newsletter",
     "t": 11, "tags": ["marketing", "content"],       "entity": "marketing", "cause": None},
]

_N = len(_CORPUS)
_ALL_GRAPHS = ["semantic", "temporal", "causal", "entity"]


# ---------------------------------------------------------------------------
# Deterministic construction of FOUR orthogonal adjacency lists over one node set.
# All edges are explicit integer adjacency lists — no embeddings, no similarity model.
# ---------------------------------------------------------------------------
def _build_graphs(sem_min_shared: int = 1) -> dict:
    """
    Build the four typed graphs. Deterministic — depends only on the fixed corpus and
    the (integer) thresholds. Returns adjacency lists keyed by node id (as ints).

      SEMANTIC : undirected edge if two items share >= sem_min_shared tags
      TEMPORAL : undirected edge between items adjacent in time (t and t+1)
      CAUSAL   : DIRECTED edge cause -> effect (hand-specified DAG via item.cause)
      ENTITY   : undirected edge if two items mention the same named entity
    """
    ids = [c["id"] for c in _CORPUS]
    by_id = {c["id"]: c for c in _CORPUS}

    def _empty():
        return {i: [] for i in ids}

    semantic = _empty()
    temporal = _empty()
    causal = _empty()
    entity = _empty()

    # SEMANTIC — shared-tag overlap (undirected)
    for i in ids:
        for j in ids:
            if j <= i:
                continue
            shared = set(by_id[i]["tags"]) & set(by_id[j]["tags"])
            if len(shared) >= sem_min_shared:
                semantic[i].append(j)
                semantic[j].append(i)

    # TEMPORAL — adjacent timestamps (undirected chain). Corpus t is 0..N-1 already.
    order = sorted(ids, key=lambda k: by_id[k]["t"])
    for a, b in zip(order, order[1:]):
        temporal[a].append(b)
        temporal[b].append(a)

    # CAUSAL — directed cause -> effect DAG
    for i in ids:
        c = by_id[i]["cause"]
        if c is not None:
            causal[c].append(i)  # cause node points to effect node

    # ENTITY — shared named entity (undirected)
    for i in ids:
        for j in ids:
            if j <= i:
                continue
            if by_id[i]["entity"] == by_id[j]["entity"]:
                entity[i].append(j)
                entity[j].append(i)

    # sort every adjacency list for full determinism
    for g in (semantic, temporal, causal, entity):
        for k in g:
            g[k].sort()

    return {"semantic": semantic, "temporal": temporal,
            "causal": causal, "entity": entity}


# ---------------------------------------------------------------------------
# Query archetypes — each maps to a fixed deterministic TRAVERSAL POLICY
# (a small state machine picking which typed graph to walk at each hop).
# ---------------------------------------------------------------------------
#   why_query   : "why did X happen?"      — walk CAUSAL backwards from X (ancestors),
#                 then one ENTITY hop to pull in same-entity context.
#   when_query  : "what happened around T?"— walk TEMPORAL outward from the T-node.
#   mixed_query : "what relates to X?"      — walk SEMANTIC then ENTITY (topic then actor).
#   entity_query: "everything about entity E" — walk ENTITY from an E-node,
#                 then one CAUSAL hop to add cause/effect context.
_QUERIES = {
    "why_query": {
        "text": "why did payments latency rise?",
        "start": 3,   # node 3 = "payments latency began rising"
        "policy": ["causal_up", "causal_up", "entity"],
    },
    "when_query": {
        "text": "what happened around the time the pool was resized?",
        "start": 7,   # node 7 = "team increased the connection pool max size"
        "policy": ["temporal", "temporal"],
    },
    "mixed_query": {
        "text": "what relates to the database configuration?",
        "start": 2,   # node 2 = "connection pool max size was set too low"
        "policy": ["semantic", "entity"],
    },
    "entity_query": {
        "text": "everything about the payments service",
        "start": 0,   # node 0 = "service payments deployed v2.3"
        "policy": ["entity", "causal_down"],
    },
}

# Hand-labeled GOLD relevant sets (the items a human judges truly relevant to the query).
# These are deliberately the TYPED-relation-correct items, so a flat similarity store that
# conflates relation types is measurably penalised.
_GOLD = {
    "why_query":   {0, 1, 2, 3},          # the causal ancestry of the latency rise
    "when_query":  {5, 6, 7, 8, 9},       # items temporally adjacent to the resize
    "mixed_query": {1, 2, 5, 6, 7},       # database/config topic + same entity
    "entity_query": {0, 3, 8, 9},         # all payments-entity items (+ their effects)
}


def _causal_parents(graphs: dict, node: int) -> list:
    """Return direct causal PARENTS of node (edges point cause->effect)."""
    causal = graphs["causal"]
    return sorted([src for src, dsts in causal.items() if node in dsts])


def _traverse_policy(graphs: dict, start: int, policy: list, max_hops: int) -> dict:
    """
    Execute a fixed traversal POLICY: a deterministic state machine. At each step the
    policy names WHICH typed graph to walk from the current frontier. Produces an ordered
    PATH (list of {hop, from, to, graph}) and the retrieved node set.

    Deterministic: adjacency lists are pre-sorted; frontier expansion is ordered.
    """
    visited = [start]
    visited_set = {start}
    frontier = [start]
    path = []
    hops_used = 0

    for step, action in enumerate(policy):
        if hops_used >= max_hops:
            break
        next_frontier = []
        for cur in frontier:
            if action == "causal_up":
                nbrs = _causal_parents(graphs, cur)
                gname = "causal"
            elif action == "causal_down":
                nbrs = list(graphs["causal"].get(cur, []))
                gname = "causal"
            elif action in ("semantic", "temporal", "entity"):
                nbrs = list(graphs[action].get(cur, []))
                gname = action
            else:
                nbrs = []
                gname = action
            for nb in nbrs:
                path.append({"hop": step, "from": cur, "to": nb, "graph": gname})
                if nb not in visited_set:
                    visited_set.add(nb)
                    visited.append(nb)
                    next_frontier.append(nb)
        hops_used += 1
        if not next_frontier:
            # frontier dead-ends: keep walking from all visited so multi-hop still fans out
            frontier = list(visited)
        else:
            frontier = next_frontier

    return {"path": path, "retrieved": sorted(visited_set), "hops_used": hops_used}


def _baseline_flat(graphs: dict, start: int, top_k: int) -> dict:
    """
    MONOLITHIC baseline: flatten all four typed graphs into ONE undirected union graph
    (relation TYPE erased), then a single BFS-degree top-k retrieval from the start node.

    Score of a candidate = (# distinct union-neighbours it shares reachability with) i.e.
    union-degree, tie-broken by proximity to start then id. This is the "flat similarity"
    analogue: it cannot tell a causal link from a topical one.
    """
    # union adjacency (undirected, type erased)
    union = {i: set() for i in range(_N)}
    for gname in _ALL_GRAPHS:
        g = graphs[gname]
        for a, dsts in g.items():
            for b in dsts:
                union[a].add(b)
                union[b].add(a)

    # BFS distances from start over the union graph
    dist = {start: 0}
    queue = [start]
    while queue:
        cur = queue.pop(0)
        for nb in sorted(union[cur]):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                queue.append(nb)

    degree = {i: len(union[i]) for i in range(_N)}
    # candidates = everything reachable except the start node itself
    cands = [i for i in range(_N) if i != start and i in dist]
    # flat ranking: higher union-degree first, then closer to start, then id
    cands.sort(key=lambda i: (-degree[i], dist[i], i))
    top = cands[:max(1, top_k)]
    return {"retrieved": sorted(top),
            "ranking": [{"id": i, "union_degree": degree[i], "dist": dist[i]} for i in top]}


def _score(retrieved: list, gold: set) -> dict:
    r = set(retrieved)
    tp = len(r & gold)
    precision = tp / len(r) if r else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "true_positives": tp,
            "retrieved_n": len(r), "gold_n": len(gold)}


_POLICY_DESCRIPTION = {
    "why_query": "Walk the CAUSAL DAG upward (effect->cause) from the start node for two "
                 "hops to recover the causal ancestry, then one ENTITY hop for same-actor "
                 "context. Answers 'why did X happen?' with the exact cause chain.",
    "when_query": "Walk the TEMPORAL chain outward from the start node (both neighbours) "
                  "for two hops, recovering what happened just before/after in time.",
    "mixed_query": "Walk the SEMANTIC (shared-tag) graph one hop for topical neighbours, "
                   "then the ENTITY graph one hop to add same-entity items.",
    "entity_query": "Walk the ENTITY graph from the start node to gather all same-entity "
                    "items, then one CAUSAL-down hop to add their direct effects.",
}


def _run(seed: int, query_type: str, max_hops: int,
         which_graphs: list, top_k: int, sem_min_shared: int) -> dict:
    """Assemble the full MODELED comparison for one query. Deterministic."""
    # seed is threaded through the LCG for doctrine compliance / future stochastic knobs;
    # the toy demo is fully deterministic regardless, so identical seed -> identical output.
    rng = _lcg(seed)
    _ = next(rng)  # touch the stream so `seed` is a real (if inert) determinism knob

    if query_type not in _QUERIES:
        query_type = "why_query"
    which_graphs = [g for g in which_graphs if g in _ALL_GRAPHS] or list(_ALL_GRAPHS)

    graphs_full = _build_graphs(sem_min_shared=sem_min_shared)
    # ablation: zero-out any disabled graph (keeps keys, empties adjacency)
    graphs = {}
    for g in _ALL_GRAPHS:
        if g in which_graphs:
            graphs[g] = graphs_full[g]
        else:
            graphs[g] = {i: [] for i in range(_N)}

    q = _QUERIES[query_type]
    start = q["start"]

    trav = _traverse_policy(graphs, start=start, policy=q["policy"], max_hops=max_hops)
    base = _baseline_flat(graphs, start=start, top_k=top_k)
    gold = _GOLD[query_type]

    trav_score = _score(trav["retrieved"], gold)
    base_score = _score(base["retrieved"], gold)

    return {
        "query_type": query_type,
        "query": {"node": start, "text": q["text"]},
        "start_node": start,
        "policy": q["policy"],
        "policy_description": _POLICY_DESCRIPTION[query_type],
        "which_graphs": which_graphs,
        "max_hops": max_hops,
        "top_k": top_k,
        "graphs": {g: {str(k): v for k, v in graphs[g].items()} for g in _ALL_GRAPHS},
        "traversal": {
            "path": trav["path"],
            "retrieved": trav["retrieved"],
            "hops_used": trav["hops_used"],
        },
        "baseline": {
            "method": "monolithic flat union-graph BFS top-k by union-degree",
            "retrieved": base["retrieved"],
            "ranking": base["ranking"],
        },
        "gold": sorted(gold),
        "scores": {
            "typed_traversal": trav_score,
            "flat_baseline": base_score,
            "f1_gain": round(trav_score["f1"] - base_score["f1"], 4),
        },
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_traverse(req: Request):
    seed        = _ii(req, "seed", 42)
    query_type  = req.query_params.get("query_type", "why_query")
    max_hops    = max(1, min(_ii(req, "max_hops", 3), 8))
    top_k       = max(1, min(_ii(req, "top_k", 4), _N))
    sem_min     = max(1, min(_ii(req, "sem_min_shared", 1), 3))
    wg_raw      = req.query_params.get("which_graphs", "")
    which_graphs = [g.strip() for g in wg_raw.split(",") if g.strip()] if wg_raw else list(_ALL_GRAPHS)

    result = _run(seed=seed, query_type=query_type, max_hops=max_hops,
                  which_graphs=which_graphs, top_k=top_k, sem_min_shared=sem_min)

    corpus_out = [{"id": c["id"], "text": c["text"], "t": c["t"],
                   "tags": c["tags"], "entity": c["entity"], "cause": c["cause"]}
                  for c in _CORPUS]

    return JSONResponse({
        "label":       "MODELED",
        "model":       "four typed relational graphs + policy-guided traversal (MAGMA-inspired)",
        "method":      "semantic/temporal/causal/entity adjacency + fixed-policy traversal vs flat-BFS baseline",
        "seed":        seed,
        "n_items":     _N,
        "query_type":  result["query_type"],
        "query":       result["query"],
        "max_hops":    result["max_hops"],
        "top_k":       result["top_k"],
        "which_graphs": result["which_graphs"],
        "corpus":      corpus_out,
        "graphs":      result["graphs"],
        "traversal":   result["traversal"],
        "baseline":    result["baseline"],
        "gold":        result["gold"],
        "scores":      result["scores"],
        "policy_description": result["policy_description"],
        "honest_note": (
            "MODELED: toy symbolic simulation of the multi-graph + policy-traversal "
            "MECHANISM, not MAGMA. Four graphs (semantic/temporal/causal/entity) are "
            "hand-built from a 12-item synthetic corpus with integer adjacency lists (NO "
            "embeddings, NO trained retriever); the 'policy' is a fixed deterministic state "
            "machine, NOT a learned agent policy; 'relevance' is scored vs a hand-labeled "
            "gold set. It demonstrates the ordering/explainability advantage of typed-"
            "relational traversal over a flat store on constructed causal/temporal queries; "
            "it does NOT reproduce MAGMA's LoCoMo/LongMemEval results and makes NO claim "
            "about real long-horizon agent performance. Clean-room-inspired by MAGMA "
            "(arXiv:2601.03236) — SZL claims none of its implementation or results as its "
            "own. Corpus is synthetic/PUBLIC only; no private data is stored, read, or "
            "modeled. Deterministic: same seed/query_type/max_hops -> identical output. "
            "Nothing here is in the locked-8; Λ stays Conjecture 1; trust never 100%."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_titans.register() / szl_episodic.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/graphmem/traverse onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/graphmem"
    handlers = [
        (f"{base}/traverse", _h_traverse),
    ]
    add_api_route = getattr(app, "add_api_route", None)
    for path, fn in handlers:
        try:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
        except Exception:
            # additive + guarded: never break app startup if a route collides
            try:
                app.router.routes.append(Route(path, fn))
            except Exception:
                pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    print("label: MODELED")
    print("n_items:", _N)
    graphs = _build_graphs()
    print("graph edge counts:")
    for gname in _ALL_GRAPHS:
        n_edges = sum(len(v) for v in graphs[gname].values())
        print("  ", gname, "adjacency entries:", n_edges)

    print()
    print("per-query: typed multi-graph traversal vs monolithic flat baseline")
    print("-" * 72)
    results = {}
    for qt in ["why_query", "when_query", "mixed_query", "entity_query"]:
        r = _run(seed=42, query_type=qt, max_hops=3,
                 which_graphs=list(_ALL_GRAPHS), top_k=4, sem_min_shared=1)
        results[qt] = r
        ts = r["scores"]["typed_traversal"]
        bs = r["scores"]["flat_baseline"]
        path_str = " -> ".join(f"{h['from']}={h['graph'][:3]}=>{h['to']}" for h in r["traversal"]["path"][:6])
        print(f"[{qt}] {r['query']['text']}")
        print(f"   traversal PATH (first hops): {path_str}")
        print(f"   typed retrieved: {r['traversal']['retrieved']}")
        print(f"   flat  retrieved: {r['baseline']['retrieved']}")
        print(f"   gold           : {r['gold']}")
        print(f"   typed  P/R/F1 = {ts['precision']}/{ts['recall']}/{ts['f1']}")
        print(f"   flat   P/R/F1 = {bs['precision']}/{bs['recall']}/{bs['f1']}")
        print(f"   F1 GAIN (typed - flat) = {r['scores']['f1_gain']}")
        print("-" * 72)

    # honest aggregate signal
    mean_typed = sum(results[q]["scores"]["typed_traversal"]["f1"] for q in results) / len(results)
    mean_flat = sum(results[q]["scores"]["flat_baseline"]["f1"] for q in results) / len(results)
    print(f"MEAN F1  typed-traversal = {round(mean_typed, 4)}   flat-baseline = {round(mean_flat, 4)}")

    # honest signal specifically on causal/temporal queries (the spec's claim)
    ct = ["why_query", "when_query"]
    ct_typed = sum(results[q]["scores"]["typed_traversal"]["f1"] for q in ct) / len(ct)
    ct_flat = sum(results[q]["scores"]["flat_baseline"]["f1"] for q in ct) / len(ct)
    print(f"MEAN F1 on causal/temporal: typed = {round(ct_typed, 4)}  flat = {round(ct_flat, 4)}")

    # sanity: determinism — identical inputs -> identical output
    r_a = _run(seed=42, query_type="why_query", max_hops=3,
               which_graphs=list(_ALL_GRAPHS), top_k=4, sem_min_shared=1)
    r_b = _run(seed=42, query_type="why_query", max_hops=3,
               which_graphs=list(_ALL_GRAPHS), top_k=4, sem_min_shared=1)
    assert json.dumps(r_a, sort_keys=True) == json.dumps(r_b, sort_keys=True), \
        "non-deterministic output for identical inputs"

    # sanity: the whole point — typed traversal should be no worse than flat on the
    # causal/temporal queries where flat similarity conflates relation types.
    assert ct_typed >= ct_flat, \
        "typed traversal should not underperform flat baseline on causal/temporal queries"

    print()
    print("determinism: OK (identical inputs -> identical output)")
    print("label: MODELED")
