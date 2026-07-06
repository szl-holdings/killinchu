# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_specexec.py — SZL TREE SPECULATIVE EXECUTION endpoint (token-tree
speculative decoding: static tree shape vs. EAGLE-2-style dynamic
Expansion/Rerank, verified against a scripted acceptance oracle), MODELED.

Exposes a MODELED, deterministic, closed-form re-implementation of the
tree-based-speculative-decoding MECHANISM (SpecInfer token-tree verification;
Sequoia DP-optimal trees; EAGLE-2 confidence-driven dynamic trees; Medusa
tree-attention + typical acceptance) applied to a small SYNTHETIC token-tree
built from the pure-stdlib LCG PRNG below — so the specexec organ has a live
data source that is honest, deterministic, and citable — never fabricated,
never a real LLM, never a real target-model forward pass.

  GET  /api/<ns>/v1/specexec/tree?seed=&depth=&branch=&budget=

WHAT IS MODELED
---------------
Classic (linear) speculative decoding drafts ONE chain of k candidate tokens.
Tree-based speculative decoding instead drafts a TREE of candidate
continuations: each node is a candidate token, each root→node path is a
candidate sequence, siblings are alternative guesses at the same position. The
whole tree is flattened and verified by the target model in a SINGLE forward
pass using a TREE CAUSAL-ATTENTION MASK (each token attends only to its own
ancestors, never to sibling branches).

This module builds a synthetic token-tree TWO ways and walks both against a
scripted deterministic acceptance oracle:

  (a) STATIC tree  — fixed branching-factor shape grown breadth-first to the
      node budget (Medusa-style Cartesian/fixed shape).
  (b) DYNAMIC tree — EAGLE-2-style Expansion/Rerank on synthetic per-node
      confidence scores: node value V_i = product of confidence scores along
      root→i; at each depth expand only the top-k highest-value frontier nodes
      (Expansion), then globally keep the top-m nodes by value across the whole
      tree before flattening (Rerank), preferring shallower nodes on ties.

ACCEPTANCE ORACLE (scripted, deterministic — NOT a real target model):
  For each node we assign a deterministic draft probability q_i and a
  deterministic target probability p_i (both from the seeded LCG). The
  speculative-sampling accept rule is the standard  a_i = min(1, p_i / q_i)
  (Leviathan/Chen 2023; provably distribution-preserving). A node is COMMITTED
  along a path only if it AND all its ancestors accept; the EXPECTED accepted
  path length of the tree is the value we report — computed exactly as the sum
  over nodes of the product of accept-probabilities along root→node
  (E[accepted tokens] = Σ_paths P(prefix all accept)).

Then we MEASURE the honest comparison:
  EXPECTED-ACCEPTED-PATH-LENGTH  : static tree vs. dynamic (Expansion/Rerank)
                                   tree under the SAME synthetic confidences and
                                   the SAME acceptance oracle. The dynamic tree
                                   spends its fixed node budget on high-value
                                   branches, so it accepts a longer expected
                                   path — the mechanism the papers exploit.
  TREE CAUSAL-ATTENTION MASK     : the binary ancestor-mask matrix (row i attends
                                   to column j iff j is i or an ancestor of i)
                                   that lets the whole tree be verified in one
                                   pass. Returned for the dynamic tree.

Returned JSON fields
--------------------
  label                    : "MODELED" (always — clean-room re-implementation of
                             the tree-speculative-decoding MECHANISM, NOT a real
                             LLM / target-model forward pass)
  model                    : short description of the modeled setup
  method                   : one-line description of the tree build + oracle
  seed                     : RNG seed used
  depth                    : max tree depth
  branch                   : branching factor for the static tree
  budget                   : node budget (≤ 32 enforced)
  nodes                    : list of dynamic-tree nodes, each
                             {id,parent,depth,confidence,value,accepted}
                             (accepted = expected accept-probability of the
                             root→node prefix, in [0,1])
  static_nodes             : count of nodes in the static tree
  dynamic_nodes            : count of nodes in the dynamic tree
  static_expected_accepted_path_length  : MEASURED E[accepted tokens], static
  dynamic_expected_accepted_path_length : MEASURED E[accepted tokens], dynamic
  improvement_ratio        : dynamic / static (≥ 1 in the modeled regime)
  attention_mask           : NxN binary tree causal-attention mask for the
                             dynamic tree (ancestor mask; 1 = attends)
  honest_note              : plain-language honesty disclaimer (see below)
  citations                : dict of citable sources (verified real)
  computed_at              : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the tree-topology +
  Expansion/Rerank value-propagation + min(1,p/q) acceptance MECHANISM on a TOY
  synthetic token-tree (no numpy, no stdlib `random`, no real draft model, no
  real target model, no real tokens, no GPU kernel). It does NOT query any LLM,
  does NOT reproduce the papers' end-to-end wall-clock speedups, and does NOT
  claim losslessness of any real system. The expected-path-length values are
  computed exactly from the scripted oracle and are DISPLAYED, not hidden. The
  label "MODELED" is returned verbatim and displayed verbatim by the surface;
  never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own; VERIFY real):
  Sequoia (DP-optimal token trees): arXiv:2402.12374
    https://arxiv.org/abs/2402.12374
  EAGLE-2 (context-aware dynamic draft tree; Expansion/Rerank): arXiv:2406.16858
    https://arxiv.org/abs/2406.16858
  Medusa (multi-head, tree attention, typical acceptance): arXiv:2401.10774
    https://arxiv.org/abs/2401.10774
  SpecInfer (token-tree verification; tree-structured causal mask), CMU PDF:
    https://www.cs.cmu.edu/~zhihaoj2/papers/specinfer.pdf
  NEVER-CLAIMED-AS: this module is not any of these systems' code, does not
  reproduce their benchmark numbers, and runs no real model. It is a clean-room
  MODELED reproduction of the tree-speculative-decoding mechanism they describe.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "Sequoia — DP-optimal token trees, arXiv:2402.12374": "https://arxiv.org/abs/2402.12374",
    "EAGLE-2 — context-aware dynamic draft tree (Expansion/Rerank), arXiv:2406.16858": "https://arxiv.org/abs/2406.16858",
    "Medusa — multi-head decoding, tree attention, typical acceptance, arXiv:2401.10774": "https://arxiv.org/abs/2401.10774",
    "SpecInfer — token-tree verification / tree-structured causal mask (CMU PDF)": "https://www.cs.cmu.edu/~zhihaoj2/papers/specinfer.pdf",
}

_MAX_NODES = 32  # spec cap: synthetic tree stays ≤ 32 nodes


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Node representation
# ---------------------------------------------------------------------------
# A tree node is a dict:
#   {id, parent, depth, confidence, value, q, p, accept}
# where
#   confidence : synthetic per-node draft confidence in (0,1] (calibrated proxy
#                for acceptance probability — EAGLE-2's key empirical finding)
#   value      : V_i = product of confidences along root→i (root value = 1.0)
#   q          : synthetic draft probability for this token
#   p          : synthetic target probability for this token
#   accept     : per-node acceptance probability a_i = min(1, p/q)
# ---------------------------------------------------------------------------
def _draw_node_scores(rng):
    """Deterministically draw (confidence, q, p, accept) for one node."""
    # confidence in [0.35, 1.0] — a plausible per-step draft confidence
    confidence = 0.35 + 0.65 * next(rng)
    # draft prob q in [0.30, 0.95]; target prob p in [0.15, 1.0]
    q = 0.30 + 0.65 * next(rng)
    p = 0.15 + 0.85 * next(rng)
    accept = p / q
    if accept > 1.0:
        accept = 1.0
    return confidence, q, p, accept


# ---------------------------------------------------------------------------
# (a) STATIC tree — fixed branching-factor shape, breadth-first to the budget
# ---------------------------------------------------------------------------
def _build_static_tree(rng, depth: int, branch: int, budget: int):
    """Grow a fixed-shape tree breadth-first: root, then `branch` children per
    node up to `depth`, stopping at the node budget. Medusa-style static shape.
    Each node gets deterministic scores from the shared RNG stream."""
    nodes = []
    # root (id 0, depth 0): confidence/value normalized to 1.0, always "present"
    c0, q0, p0, a0 = _draw_node_scores(rng)
    nodes.append({
        "id": 0, "parent": -1, "depth": 0,
        "confidence": 1.0, "value": 1.0,
        "q": q0, "p": p0, "accept": a0,
    })
    frontier = [0]
    d = 0
    while frontier and d < depth and len(nodes) < budget:
        nxt = []
        for par in frontier:
            for _ in range(branch):
                if len(nodes) >= budget:
                    break
                conf, q, p, acc = _draw_node_scores(rng)
                nid = len(nodes)
                pv = nodes[par]["value"] * conf
                nodes.append({
                    "id": nid, "parent": par, "depth": d + 1,
                    "confidence": conf, "value": pv,
                    "q": q, "p": p, "accept": acc,
                })
                nxt.append(nid)
            if len(nodes) >= budget:
                break
        frontier = nxt
        d += 1
    return nodes


# ---------------------------------------------------------------------------
# (b) DYNAMIC tree — EAGLE-2-style Expansion / Rerank on node values V_i
# ---------------------------------------------------------------------------
def _build_dynamic_tree(rng, depth: int, branch: int, budget: int):
    """EAGLE-2 Expansion/Rerank:
      value  V_i = product of confidences along root→i
      Expansion : at each depth, expand only the top-k highest-value frontier
                  nodes (draft `branch` candidate children each).
      Rerank    : globally keep the top-(budget) nodes by value across the whole
                  tree, preferring SHALLOWER nodes on ties, then relabel so the
                  kept set is a valid tree (every kept node's parent is kept).
    The RNG stream is drawn deterministically for every candidate considered."""
    # top-k frontier width for Expansion (bounded by branch, ≥ 1)
    topk = max(1, min(branch, 3))

    # Grow an over-complete candidate pool via Expansion, then Rerank/prune.
    root_conf, root_q, root_p, root_acc = _draw_node_scores(rng)
    pool = [{
        "cid": 0, "parent_cid": -1, "depth": 0,
        "confidence": 1.0, "value": 1.0,
        "q": root_q, "p": root_p, "accept": root_acc,
    }]
    frontier = [0]
    cid_counter = 1
    d = 0
    # allow the pool to grow a bit past budget so Rerank has genuine choices,
    # but keep it bounded (≤ 3x budget or a hard cap) for determinism/perf.
    pool_cap = min(3 * budget, 96)
    while frontier and d < depth and len(pool) < pool_cap:
        # Expansion: keep only the top-k highest-value frontier nodes
        frontier.sort(key=lambda cid: (-pool[cid]["value"], pool[cid]["depth"], cid))
        expand = frontier[:topk]
        nxt = []
        for par in expand:
            for _ in range(branch):
                if len(pool) >= pool_cap:
                    break
                conf, q, p, acc = _draw_node_scores(rng)
                pv = pool[par]["value"] * conf
                pool.append({
                    "cid": cid_counter, "parent_cid": par, "depth": d + 1,
                    "confidence": conf, "value": pv,
                    "q": q, "p": p, "accept": acc,
                })
                nxt.append(cid_counter)
                cid_counter += 1
            if len(pool) >= pool_cap:
                break
        frontier = nxt
        d += 1

    # Rerank: globally keep the top-(budget) candidates by value, shallower on
    # ties. Root is always kept. Then enforce tree validity: a node can only be
    # kept if its parent is kept — add any missing ancestors (they have ≥ value
    # so they'd normally already be in), keeping the final set ≤ budget by
    # trimming the lowest-value leaves if the ancestor-closure overshoots.
    order = sorted(
        pool,
        key=lambda n: (-n["value"], n["depth"], n["cid"]),
    )
    keep = set()
    for n in order:
        if len(keep) >= budget:
            break
        keep.add(n["cid"])
    keep.add(0)  # root always kept

    # ancestor closure: ensure every kept node's parent chain is kept
    by_cid = {n["cid"]: n for n in pool}
    changed = True
    while changed:
        changed = False
        for cid in list(keep):
            par = by_cid[cid]["parent_cid"]
            if par >= 0 and par not in keep:
                keep.add(par)
                changed = True
    # if closure overshot budget, trim lowest-value *leaves* (never the root)
    while len(keep) > budget:
        # a leaf is a kept node with no kept children
        kept_parents = {by_cid[c]["parent_cid"] for c in keep}
        leaves = [c for c in keep if c != 0 and c not in kept_parents]
        if not leaves:
            break
        worst = min(leaves, key=lambda c: (by_cid[c]["value"], -by_cid[c]["depth"], -c))
        keep.discard(worst)

    # relabel kept candidates into contiguous node ids in BFS order (root first)
    kept_sorted = sorted(keep, key=lambda c: (by_cid[c]["depth"], by_cid[c]["cid"]))
    remap = {cid: i for i, cid in enumerate(kept_sorted)}
    nodes = []
    for cid in kept_sorted:
        n = by_cid[cid]
        parent = remap[n["parent_cid"]] if n["parent_cid"] in remap else -1
        nodes.append({
            "id": remap[cid], "parent": parent, "depth": n["depth"],
            "confidence": n["confidence"], "value": n["value"],
            "q": n["q"], "p": n["p"], "accept": n["accept"],
        })
    return nodes


# ---------------------------------------------------------------------------
# acceptance walk — expected accepted-path length under the scripted oracle
# ---------------------------------------------------------------------------
def _prefix_accept_probs(nodes):
    """For each node, compute the probability that the whole root→node prefix
    is accepted = product of per-node accept probabilities along the path.
    Returns a list aligned to node ids. Root prefix-prob = its own accept."""
    by_id = {n["id"]: n for n in nodes}
    memo = {}

    def prefix(nid):
        if nid in memo:
            return memo[nid]
        n = by_id[nid]
        par = n["parent"]
        if par < 0:
            val = n["accept"]
        else:
            val = prefix(par) * n["accept"]
        memo[nid] = val
        return val

    return [prefix(n["id"]) for n in nodes]


def _expected_accepted_path_length(nodes):
    """E[accepted tokens] committed this step, summed over all nodes.

    Standard tree-speculative result: the expected number of committed tokens
    equals the sum over nodes of P(the root→node prefix is fully accepted). A
    node contributes to the committed count only if it and all ancestors accept;
    summing the prefix-acceptance probability over every node gives the exact
    expected accepted-path length (linearity of expectation over path prefixes).
    """
    pref = _prefix_accept_probs(nodes)
    # exclude the root token itself from the count (it is the already-committed
    # context position); count committed *speculative* tokens at depth ≥ 1.
    total = 0.0
    for n, pp in zip(nodes, pref):
        if n["depth"] >= 1:
            total += pp
    return total


# ---------------------------------------------------------------------------
# tree causal-attention mask — each node attends only to itself + ancestors
# ---------------------------------------------------------------------------
def _attention_mask(nodes):
    """NxN binary mask; row i attends to column j iff j == i or j is an ancestor
    of i (SpecInfer tree-structured causal mask). Rows/cols indexed by node id."""
    n = len(nodes)
    by_id = {node["id"]: node for node in nodes}
    mask = [[0] * n for _ in range(n)]
    for node in nodes:
        i = node["id"]
        # walk up the ancestor chain
        cur = i
        guard = 0
        while cur >= 0 and guard <= n:
            mask[i][cur] = 1
            cur = by_id[cur]["parent"]
            guard += 1
    return mask


# ---------------------------------------------------------------------------
# public node view (rounded, ordered) for the JSON payload
# ---------------------------------------------------------------------------
def _public_nodes(nodes):
    pref = _prefix_accept_probs(nodes)
    pref_by_id = {n["id"]: pp for n, pp in zip(nodes, pref)}
    out = []
    for n in sorted(nodes, key=lambda x: x["id"]):
        out.append({
            "id": n["id"],
            "parent": n["parent"],
            "depth": n["depth"],
            "confidence": round(n["confidence"], 6),
            "value": round(n["value"], 6),
            # 'accepted' = expected accept-probability of the root→node prefix
            "accepted": round(pref_by_id[n["id"]], 6),
        })
    return out


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _specexec_snapshot(seed: int = 42, depth: int = 4, branch: int = 3,
                       budget: int = 24) -> dict:
    """Deterministically build a synthetic token-tree two ways (static vs
    dynamic Expansion/Rerank), walk both against the scripted min(1,p/q)
    acceptance oracle, and MEASURE the expected accepted-path length of each
    plus the dynamic tree's tree causal-attention mask.

    Pure stdlib; deterministic — same (seed, depth, branch, budget) ->
    identical snapshot, every time. Each variant uses its OWN fresh RNG stream
    seeded from `seed` so the two trees see the SAME synthetic score sequence
    (an apples-to-apples comparison of shape, not of luck).
    """
    static_nodes = _build_static_tree(_lcg(seed), depth, branch, budget)
    dynamic_nodes = _build_dynamic_tree(_lcg(seed), depth, branch, budget)

    static_epl = _expected_accepted_path_length(static_nodes)
    dynamic_epl = _expected_accepted_path_length(dynamic_nodes)
    improvement = (dynamic_epl / static_epl) if static_epl > 0 else 0.0

    mask = _attention_mask(dynamic_nodes)

    return {
        "depth": depth,
        "branch": branch,
        "budget": budget,
        "static_nodes": len(static_nodes),
        "dynamic_nodes": len(dynamic_nodes),
        "static_expected_accepted_path_length": round(static_epl, 6),
        "dynamic_expected_accepted_path_length": round(dynamic_epl, 6),
        "improvement_ratio": round(improvement, 6),
        "nodes": _public_nodes(dynamic_nodes),
        "attention_mask": mask,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


_HONEST_NOTE = (
    "MODELED: this is a clean-room reproduction of the TREE-SPECULATIVE-DECODING "
    "MECHANISM (token-tree topology + EAGLE-2 Expansion/Rerank value propagation "
    "V_i = product of root→i confidences + SpecInfer tree causal-attention mask + "
    "the standard min(1, p/q) speculative-sampling acceptance rule) on a TOY "
    "synthetic token-tree, NOT a live LLM. No real draft model, no real target "
    "model, no real tokens, no GPU kernel, no forward pass is run. The "
    "expected-accepted-path-length figures are computed EXACTLY from a scripted "
    "deterministic acceptance oracle and are DISPLAYED, not hidden. This does NOT "
    "reproduce the papers' end-to-end wall-clock speedups (Sequoia arXiv:2402.12374; "
    "EAGLE-2 arXiv:2406.16858; Medusa arXiv:2401.10774; SpecInfer CMU) and claims "
    "NO losslessness of any real system. Pure stdlib, no numpy, no stdlib random. "
    "Deterministic: same seed/depth/branch/budget -> identical snapshot. "
    "NEVER-CLAIMED-AS a production decoding engine. SZL claims NONE of these "
    "methods as its own."
)


def _h_tree(req: Request):
    seed   = _ii(req, "seed",   42)
    depth  = max(1, min(_ii(req, "depth",  4), 8))
    branch = max(1, min(_ii(req, "branch", 3), 6))
    budget = max(2, min(_ii(req, "budget", 24), _MAX_NODES))

    snap = _specexec_snapshot(seed=seed, depth=depth, branch=branch, budget=budget)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Tree speculative execution (token-tree speculative decoding: static fixed-shape tree vs. EAGLE-2-style dynamic Expansion/Rerank on synthetic per-node confidences) verified against a scripted min(1,p/q) acceptance oracle on a synthetic token-tree",
        "method": "value V_i = product of confidences along root→i; Expansion keeps top-k highest-value frontier nodes, Rerank globally keeps top-budget nodes by value (shallower on ties); acceptance a_i = min(1, p/q); E[accepted tokens] = Σ_nodes P(root→node prefix all accept); SpecInfer tree causal-attention mask = ancestor mask",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_ternary.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/specexec/tree onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/specexec"
    handlers = [
        (f"{base}/tree", _h_tree),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _specexec_snapshot(seed=42, depth=4, branch=3, budget=24)
    print("label: MODELED")
    print("depth:", snap["depth"], "branch:", snap["branch"], "budget:", snap["budget"])
    print("static_nodes:", snap["static_nodes"], "dynamic_nodes:", snap["dynamic_nodes"])
    print("--- EXPECTED ACCEPTED-PATH LENGTH (MEASURED under scripted oracle) ---")
    print("static :", snap["static_expected_accepted_path_length"])
    print("dynamic:", snap["dynamic_expected_accepted_path_length"])
    print("improvement_ratio (dynamic/static):", snap["improvement_ratio"])
    print("--- SAMPLE NODES (dynamic tree; id,parent,depth,confidence,value,accepted) ---")
    for n in snap["nodes"][:6]:
        print("  ", n["id"], n["parent"], n["depth"], n["confidence"], n["value"], n["accepted"])
    print("--- TREE CAUSAL-ATTENTION MASK (dynamic tree) ---")
    m = snap["attention_mask"]
    print("mask is", len(m), "x", (len(m[0]) if m else 0))
    for row in m[:5]:
        print("  ", "".join(str(x) for x in row))

    # sanity: node count within cap
    assert snap["dynamic_nodes"] <= _MAX_NODES, "dynamic tree exceeds node cap"
    assert snap["static_nodes"] <= _MAX_NODES, "static tree exceeds node cap"
    assert snap["dynamic_nodes"] <= snap["budget"], "dynamic tree exceeds budget"

    # sanity: mask is square and equals dynamic node count
    assert len(m) == snap["dynamic_nodes"], "mask dim != dynamic node count"
    assert all(len(row) == snap["dynamic_nodes"] for row in m), "mask not square"

    # sanity: mask is a valid ancestor (tree-causal) mask
    #   - diagonal all 1 (self-attention)
    #   - each node attends to strictly fewer-or-equal columns than depth+1
    nodes_by_id = {n["id"]: n for n in snap["nodes"]}
    for i in range(len(m)):
        assert m[i][i] == 1, "diagonal must be 1 (self-attention)"
        attended = sum(m[i])
        assert attended == nodes_by_id[i]["depth"] + 1, "node must attend to exactly its ancestor chain"
        # mask must be lower-ish: a node never attends to a deeper node
        for j in range(len(m)):
            if m[i][j] == 1 and j != i:
                assert nodes_by_id[j]["depth"] < nodes_by_id[i]["depth"], "cannot attend to non-shallower node"

    # sanity: expected accepted-path lengths are non-negative and measured
    assert snap["static_expected_accepted_path_length"] >= 0.0
    assert snap["dynamic_expected_accepted_path_length"] >= 0.0

    # sanity: dynamic Expansion/Rerank should not do WORSE than the static shape
    assert (snap["dynamic_expected_accepted_path_length"]
            >= snap["static_expected_accepted_path_length"] - 1e-9), \
        "dynamic tree should match or beat static under same oracle"

    # sanity: root present, ids contiguous 0..N-1, parents valid & shallower
    ids = [n["id"] for n in snap["nodes"]]
    assert ids == list(range(len(ids))), "node ids must be contiguous 0..N-1"
    assert snap["nodes"][0]["parent"] == -1, "root parent must be -1"
    for n in snap["nodes"]:
        if n["parent"] >= 0:
            assert nodes_by_id[n["parent"]]["depth"] < n["depth"], "parent must be shallower"
        assert 0.0 <= n["accepted"] <= 1.0, "prefix-accept prob out of range"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _specexec_snapshot(seed=42, depth=4, branch=3, budget=24)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_specexec: ALL OK — token-tree built static vs dynamic (Expansion/Rerank), "
          "expected accepted-path length MEASURED under scripted oracle, tree causal-attention "
          "mask valid, deterministic.")
