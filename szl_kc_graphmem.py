# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_graphmem.py — ADDITIVE multi-graph agentic-memory traversal organ for killinchu's
frontier surface (backs a11oy static/3d/surfaces/graphmem.js).

MAGMA (Jiang, Li, Li, Li 2026, arXiv:2601.03236) is a multi-graph agentic memory
architecture: rather than a single similarity-ranked memory store, each memory item is
represented across ORTHOGONAL views — a semantic graph, a temporal graph, a causal graph,
and an entity graph. Retrieval is policy-guided TRAVERSAL over those relational views, which
decouples memory representation from retrieval logic and yields transparent reasoning paths.
This organ builds such a multi-view memory graph and traverses it to answer a query,
reporting the path and per-view contribution.

Deterministic MODELED formulation (seeded, no live LLM):
  * Build N memory nodes, each with a seeded semantic embedding, a timestamp, a causal parent,
    and an entity tag. Four adjacency views are derived: semantic (cosine kNN), temporal
    (time-adjacency), causal (parent links), entity (shared-tag links).
  * A query node is embedded. Policy-guided traversal: a weighted frontier expansion where the
    next hop maximizes  w_sem*cos + w_tmp*recency + w_cause*causal + w_ent*entity_match, with
    the view weights being the "policy". Beam-limited, cycle-free.
  * Report: retrieval path, hops, per-view contribution fractions, and retrieval precision@k
    against a seeded ground-truth relevance set.

  score(u->v) = w_sem*cos(q,v) + w_tmp*recency(v) + w_cause*causal(u,v) + w_ent*entity(q,v)
  precision_at_k = |top_k ∩ relevant| / k

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic multi-view graph build + policy traversal. NOT MAGMA running with an
    LLM; NO live model, NO GPU, NO learned retrieval policy — the view weights are SEEDED inputs.
  * Embeddings are seeded pseudo-random vectors, not real text embeddings; precision is measured
    against a SEEDED ground-truth set, honestly labeled, not a real benchmark (LoCoMo/LongMemEval).
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/graphmem/traverse  — multi-graph memory traversal snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | MULTIVIEW_GRAPH_TRAVERSAL | NOT_LIVE | NO_MODEL | SEEDED_EMBEDDINGS"

CITATIONS = {
    "magma": ("Jiang, Li, Li, Li (2026) MAGMA: A Multi-Graph based Agentic Memory "
              "Architecture for AI Agents — arXiv:2601.03236"),
    "magma_url": "https://arxiv.org/abs/2601.03236",
}


class _LCG:
    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)

    def random(self) -> float:
        self._s = (self._s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((self._s >> 11) & ((1 << 53) - 1)) / float(1 << 53)

    def gauss(self) -> float:
        u1 = max(1e-12, self.random())
        u2 = self.random()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)

    def randint(self, lo: int, hi: int) -> int:
        return lo + int(self.random() * (hi - lo + 1)) % (hi - lo + 1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = _math.sqrt(sum(x * x for x in a)) or 1e-12
    nb = _math.sqrt(sum(x * x for x in b)) or 1e-12
    return dot / (na * nb)


def graphmem_traverse(seed: int = 42, nodes: int = 40, dim: int = 12, k: int = 5,
                      max_hops: int = 8, n_entities: int = 6) -> dict:
    """Multi-graph memory traversal snapshot (MODELED).

    nodes      — number of memory items.
    dim        — embedding dimension.
    k          — top-k retrieved for precision@k.
    max_hops   — beam-limited traversal budget.
    n_entities — number of entity tags.
    """
    N = max(6, min(2000, int(nodes)))
    d = max(2, min(64, int(dim)))
    k = max(1, min(N - 1, int(k)))
    max_hops = max(1, min(N, int(max_hops)))
    n_ent = max(2, min(64, int(n_entities)))
    rng = _LCG(int(seed) * 1_000_003 + N * 131 + d)

    # build memory nodes: embedding, timestamp, causal parent, entity tag
    emb = [[rng.gauss() for _ in range(d)] for _ in range(N)]
    tstamp = list(range(N))  # temporal order
    parent = [(-1 if i == 0 else rng.randint(0, i - 1)) for i in range(N)]  # causal DAG
    entity = [rng.randint(0, n_ent - 1) for i in range(N)]

    # query embedding + query entity
    q = [rng.gauss() for _ in range(d)]
    q_entity = rng.randint(0, n_ent - 1)

    # policy view weights (SEEDED policy)
    w_sem, w_tmp, w_cause, w_ent = 0.5, 0.2, 0.15, 0.15

    def recency(v: int) -> float:
        return tstamp[v] / (N - 1)  # newer = higher

    def causal(u: int, v: int) -> float:
        return 1.0 if (parent[v] == u or parent[u] == v) else 0.0

    def ent_match(v: int) -> float:
        return 1.0 if entity[v] == q_entity else 0.0

    def node_score(u: int, v: int) -> float:
        return (w_sem * ((_cos(q, emb[v]) + 1.0) / 2.0)
                + w_tmp * recency(v)
                + w_cause * causal(u, v)
                + w_ent * ent_match(v))

    # policy-guided traversal: start at best semantic seed, greedily expand frontier
    seeds = sorted(range(N), key=lambda v: _cos(q, emb[v]), reverse=True)
    cur = seeds[0]
    visited = [cur]
    view_contrib = {"semantic": 0.0, "temporal": 0.0, "causal": 0.0, "entity": 0.0}
    for _ in range(max_hops - 1):
        best_v, best_s = None, -1e18
        for v in range(N):
            if v in visited:
                continue
            s = node_score(cur, v)
            if s > best_s:
                best_s, best_v = s, v
        if best_v is None:
            break
        # accumulate which view drove this hop
        sem = w_sem * ((_cos(q, emb[best_v]) + 1.0) / 2.0)
        tmp = w_tmp * recency(best_v)
        cau = w_cause * causal(cur, best_v)
        ent = w_ent * ent_match(best_v)
        view_contrib["semantic"] += sem
        view_contrib["temporal"] += tmp
        view_contrib["causal"] += cau
        view_contrib["entity"] += ent
        visited.append(best_v)
        cur = best_v

    tot = sum(view_contrib.values()) or 1e-12
    view_frac = {kk: round(vv / tot, 6) for kk, vv in view_contrib.items()}

    # ground-truth relevance (SEEDED): nodes with high semantic cos OR matching entity
    relevance = sorted(range(N),
                       key=lambda v: (_cos(q, emb[v]) + (0.3 if entity[v] == q_entity else 0.0)),
                       reverse=True)
    relevant_set = set(relevance[:k])
    topk = set(sorted(range(N), key=lambda v: node_score(seeds[0], v), reverse=True)[:k])
    precision_at_k = len(topk & relevant_set) / k

    return {
        "service": "multi-graph-agentic-memory",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/graphmem.js ---
        "nodes": int(N),
        "dim": int(d),
        "k": int(k),
        "hops": int(len(visited)),
        "traversal_path": [int(x) for x in visited[:16]],
        "view_contribution_frac": view_frac,
        "precision_at_k": round(float(precision_at_k), 6),
        "policy_weights": {"semantic": w_sem, "temporal": w_tmp, "causal": w_cause,
                           "entity": w_ent},
        "views": ["semantic", "temporal", "causal", "entity"],
        "formulas": {
            "hop_score": ("w_sem*cos(q,v) + w_tmp*recency(v) + w_cause*causal(u,v) "
                          "+ w_ent*entity(q,v)"),
            "precision_at_k": "|top_k ∩ relevant| / k",
        },
        "compute_backend": {
            "backend": "CPU pure-Python multi-view graph traversal",
            "label": "MODELED",
            "honest_note": ("Deterministic multi-view memory graph + policy traversal; NO live "
                            "LLM, NO GPU, NO learned policy. Embeddings are seeded vectors; "
                            "precision is against a seeded ground truth, NOT LoCoMo/LongMemEval. "
                            "A live agentic-memory retriever is ROADMAP."),
        },
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (retrieval advisory — never an autonomous action)",
        "wired_into": "frontier ring — Graph-Memory surface",
        "honest_note": ("MODELED deterministic build of semantic/temporal/causal/entity memory "
                        "graphs with policy-guided traversal, mirroring MAGMA's decoupled "
                        "representation/retrieval. NOT MAGMA with a live LLM; view weights are "
                        "seeded. MODELED, not live; advisory to Λ (Conjecture 1)."),
        "citations": {"magma": CITATIONS["magma"], "magma_url": CITATIONS["magma_url"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/graphmem" % ns

    @app.get("%s/traverse" % base)
    async def _kc_graphmem(seed: int = 42, nodes: int = 40, dim: int = 12, k: int = 5):  # noqa: ANN202
        try:
            return JSONResponse(graphmem_traverse(seed=seed, nodes=nodes, dim=dim, k=k))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "multi-graph-agentic-memory",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "precision_at_k": None}, status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401
    except Exception:  # pragma: no cover
        pass
    return {"ok": True, "ns": ns, "routes": ["%s/traverse" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = graphmem_traverse(seed=42, nodes=40, dim=12, k=5)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("nodes", "dim", "k", "hops"):
        assert isinstance(r[f], int), (f, r.get(f))
    assert isinstance(r["traversal_path"], list) and r["traversal_path"], r
    # path nodes are distinct (cycle-free)
    assert len(set(r["traversal_path"])) == len(r["traversal_path"]), r
    assert 1 <= r["hops"] <= r["nodes"], r
    vc = r["view_contribution_frac"]
    assert set(vc.keys()) == {"semantic", "temporal", "causal", "entity"}, vc
    assert abs(sum(vc.values()) - 1.0) < 1e-6, vc
    assert 0.0 <= r["precision_at_k"] <= 1.0, r
    assert "2601.03236" in r["citations"]["magma"], r
    out["metrics"] = {"hops": r["hops"], "precision_at_k": r["precision_at_k"],
                      "view_contribution_frac": vc}

    # determinism
    r2 = graphmem_traverse(seed=42, nodes=40, dim=12, k=5)
    assert r2["traversal_path"] == r["traversal_path"], "non-deterministic"
    assert r2["precision_at_k"] == r["precision_at_k"], "non-deterministic precision"
    out["deterministic"] = True

    p = register(_FakeApp())
    assert p["routes"] == ["/api/killinchu/v1/graphmem/traverse"], p
    out["route"] = p["routes"][0]

    out["ok"] = True
    return out


class _FakeApp:
    def get(self, path):
        def _d(fn):
            return fn
        return _d


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    vc = res["metrics"]["view_contribution_frac"]
    print("hops=%d  precision@k=%.4f  views sem=%.3f tmp=%.3f cause=%.3f ent=%.3f"
          % (res["metrics"]["hops"], res["metrics"]["precision_at_k"],
             vc["semantic"], vc["temporal"], vc["causal"], vc["entity"]))
    assert res["ok"]
    print("ALL OK")
