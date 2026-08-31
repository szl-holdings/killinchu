# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · label:"MODELED"
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_flower_metrics.py — CROSS-PETAL GRAPH METRICS for the Flower Brain organ.

An OPTIONAL 4th flower endpoint that reads the REAL 8-petal flower graph (imported
from szl_kc_flower — this file NEVER edits that organ) and computes cross-petal
structure over the real topology. Pure stdlib, deterministic, label:"MODELED".

What it measures (all MODELED, honest, on the real graph):
  (a) bridge nodes  — nodes whose incident edges span more than one petal, i.e. which
      formulas actually connect the clusters (the flower's connective tissue).
  (b) per-petal internal edge density — internal_edges / max-possible for each petal.
  (c) Fiedler lambda2 of the WHOLE flower graph — the 2nd-smallest graph-Laplacian
      eigenvalue (algebraic connectivity) via a pure-stdlib symmetric Jacobi
      eigensolver (copied from szl_fgbrain._fiedler_lambda2). lambda2 > 0 <=> the
      flower is one connected organism.
  (d) most-connected bridge formula — the bridge node with the largest cross-petal degree.

Route (OPTIONAL, additive, never collides): GET /api/{ns}/v1/flower/metrics

HONESTY SPINE (Doctrine v11):
  * The GRAPH is REAL (imported verbatim from szl_kc_flower). The METRICS are MODELED,
    deterministic, pure-stdlib graph statistics on that real topology — never claimed
    as trained, alive, or measured. label:"MODELED" verbatim.
  * Pure stdlib (math only; no numpy, no stdlib random). Deterministic.
  * A compute failure NEVER raises out of a handler (fail-open like the base organ).
"""
from __future__ import annotations

import math as _math
from typing import Any, Dict, List, Tuple

import szl_kc_flower as _flower

MODELED_LABEL = "MODELED"
DOCTRINE_VERSION = "v11"


# --------------------------------------------------------------------------------------
# Pure-stdlib symmetric Jacobi eigensolver -> Fiedler lambda2 of the whole flower graph.
# Copied from szl_fgbrain._fiedler_lambda2 (same algorithm), adapted to an explicit
# undirected adjacency built from the flower's cross-petal + intra-petal edges.
# lambda2 > 0  <=>  the graph is one connected component.
# --------------------------------------------------------------------------------------
def _fiedler_lambda2(ids: List[str], neighbours: Dict[str, List[str]]) -> float:
    """Algebraic connectivity (2nd-smallest Laplacian eigenvalue) of the induced graph
    on `ids` with undirected adjacency `neighbours`. Pure stdlib: symmetric Jacobi
    eigenvalue iteration on L = D - A."""
    ids = list(ids)
    n = len(ids)
    if n <= 1:
        return 0.0
    idx = {i: k for k, i in enumerate(ids)}
    aset = set(ids)
    L = [[0.0] * n for _ in range(n)]
    for i in ids:
        deg = 0
        for j in neighbours.get(i, []):
            if j in aset and j != i:
                L[idx[i]][idx[j]] = -1.0
                deg += 1
        L[idx[i]][idx[i]] = float(deg)
    # Jacobi eigenvalue iteration (symmetric). n is small; converges fast.
    A = [row[:] for row in L]
    for _sweep in range(80):
        p, qd, mx = 0, 1, 0.0
        for a in range(n):
            for b in range(a + 1, n):
                if abs(A[a][b]) > mx:
                    mx = abs(A[a][b]); p, qd = a, b
        if mx < 1e-10:
            break
        app_, aqq, apq = A[p][p], A[qd][qd], A[p][qd]
        if abs(apq) < 1e-15:
            continue
        theta = (aqq - app_) / (2.0 * apq)
        t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + _math.sqrt(theta * theta + 1.0))
        c = 1.0 / _math.sqrt(t * t + 1.0)
        s = t * c
        for k in range(n):
            akp, akq = A[k][p], A[k][qd]
            A[k][p] = c * akp - s * akq
            A[k][qd] = s * akp + c * akq
        for k in range(n):
            apk, aqk = A[p][k], A[qd][k]
            A[p][k] = c * apk - s * aqk
            A[qd][k] = s * apk + c * aqk
    eig = sorted(A[k][k] for k in range(n))
    return round(max(0.0, eig[1]) if len(eig) >= 2 else 0.0, 6)


def _undirected(ids: List[str], edges: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    nb: Dict[str, List[str]] = {i: [] for i in ids}
    for a, b in edges:
        if a in nb and b in nb and a != b:
            if b not in nb[a]:
                nb[a].append(b)
            if a not in nb[b]:
                nb[b].append(a)
    return nb


def _components(ids: List[str], nb: Dict[str, List[str]]) -> List[List[str]]:
    """Connected components (over nodes with >=1 edge) as sorted id lists, ordered
    largest-first then lexicographically. Pure-stdlib iterative DFS, deterministic."""
    seen = set()
    comps: List[List[str]] = []
    for s in sorted(i for i in ids if nb.get(i)):
        if s in seen:
            continue
        stack = [s]
        comp: List[str] = []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.append(x)
            for y in nb[x]:
                if y not in seen:
                    stack.append(y)
        comps.append(sorted(comp))
    comps.sort(key=lambda c: (-len(c), c[0] if c else ""))
    return comps


# --------------------------------------------------------------------------------------
# The metrics computation.
# --------------------------------------------------------------------------------------
def flower_metrics(seed: int = 42) -> Dict[str, Any]:
    """Cross-petal structural metrics over the REAL flower graph. MODELED, deterministic."""
    g = _flower.flower_graph(seed=int(seed))
    nodes = g["nodes"]
    ids = [n["id"] for n in nodes]
    petal_of = {n["id"]: n["petal"] for n in nodes}
    title_of = {n["id"]: n["title"] for n in nodes}
    edges = [(e["src"], e["dst"]) for e in g["edges"]]
    nb = _undirected(ids, edges)

    # (a) bridge nodes: nodes whose incident edges span >1 petal (touch a petal
    #     different from their own). cross_petal_degree = # of neighbours in other petals.
    bridge: List[Dict[str, Any]] = []
    for i in ids:
        mine = petal_of[i]
        other_petals = sorted({petal_of[j] for j in nb[i] if petal_of[j] != mine})
        cross_deg = sum(1 for j in nb[i] if petal_of[j] != mine)
        if other_petals:
            bridge.append({
                "id": i,
                "title": title_of[i],
                "petal": mine,
                "cross_petal_degree": cross_deg,
                "connects_petals": other_petals,
                "span": len(set(other_petals) | {mine}),  # # distinct petals this node touches
            })
    # deterministic order: most cross-connections first, then id
    bridge.sort(key=lambda d: (-d["cross_petal_degree"], d["id"]))

    # (b) per-petal internal edge density = internal_edges / C(k,2) for k nodes in petal.
    per_petal_density: List[Dict[str, Any]] = []
    for p in _flower.PETALS:
        pn = p["n"]
        members = [i for i in ids if petal_of[i] == pn]
        k = len(members)
        mset = set(members)
        internal = 0
        for a, b in edges:
            if a in mset and b in mset and a != b:
                internal += 1
        max_edges = k * (k - 1) // 2
        density = round(internal / max_edges, 6) if max_edges > 0 else 0.0
        per_petal_density.append({
            "petal": pn, "name": p["name"], "key": p["key"],
            "node_count": k, "internal_edges": internal,
            "max_possible_edges": max_edges, "internal_density": density,
        })

    # (c) Fiedler lambda2 — the graph-Laplacian 2nd eigenvalue, the "is the flower one
    #     connected organism" metric, computed HONESTLY. The real cross-petal dependency
    #     web is what it is: reported over the WHOLE 59-node graph (isolated leaf nodes
    #     included) and over the LARGEST connected component. lambda2 > 0 <=> that graph
    #     is a single connected component. We do NOT fabricate connectivity: if the flower's
    #     dependency web is currently several clusters, lambda2 over the whole graph is 0
    #     and we report the component count and the largest component honestly.
    lambda2_full = _fiedler_lambda2(ids, nb)
    core_ids = [i for i in ids if nb[i]]        # nodes that participate in >=1 edge
    comps = _components(ids, nb)
    largest = comps[0] if comps else []
    lambda2_largest = _fiedler_lambda2(largest, nb)  # connectivity within the biggest cluster
    # `fiedler_lambda2` (the headline metric) is the honest whole-graph value.
    lambda2 = lambda2_full
    connected = lambda2_full > 1e-9             # True only if the whole flower is one component
    isolated = [i for i in ids if not nb[i]]

    # (d) most-connected bridge formula.
    most_connected = bridge[0] if bridge else None

    total_cross = sum(1 for a, b in edges if petal_of[a] != petal_of[b])

    return {
        "service": "flower-brain-metrics",
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "seed": int(seed),
        "nodes_total": len(ids),
        "edges_total": len(edges),
        "cross_petal_edges": total_cross,
        "bridge_node_count": len(bridge),
        "bridge_nodes": bridge,                 # (a) which formulas connect clusters
        "per_petal_density": per_petal_density,  # (b) internal edge density per petal
        "fiedler_lambda2": lambda2,             # (c) honest whole-flower algebraic connectivity
        "fiedler_lambda2_largest_component": lambda2_largest,  # connectivity within the biggest cluster
        "connective_core_size": len(core_ids),  # # nodes participating in >=1 edge
        "isolated_node_count": len(isolated),   # leaf/placeholder nodes with no dependency edge yet
        "component_count": len(comps),          # # connected clusters in the dependency web
        "largest_component_size": len(largest),
        "flower_is_connected": connected,       # lambda2>0 => the WHOLE flower is one organism
        "most_connected_bridge": most_connected,  # (d)
        "honesty": ("MODELED: the graph is the REAL 8-petal flower (imported from "
                    "szl_kc_flower). These are MODELED, deterministic, pure-stdlib graph "
                    "statistics (bridge nodes, per-petal internal density, and the "
                    "graph-Laplacian Fiedler lambda2 via a symmetric Jacobi eigensolver) "
                    "over that real topology — never trained, alive, or measured."),
    }


# --------------------------------------------------------------------------------------
# Registration (additive, optional). Returns the single registered path.
# --------------------------------------------------------------------------------------
def register(app, ns: str = "killinchu") -> List[str]:
    """Wire GET /api/<ns>/v1/flower/metrics onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append.
    Returns the list with the single registered route path."""
    base = "/api/%s/v1/flower" % ns
    paths = ["%s/metrics" % base]

    try:
        from fastapi.responses import JSONResponse

        def _metrics_h(seed: int = 42):  # noqa: ANN202
            try:
                return JSONResponse(flower_metrics(seed=seed))
            except Exception as exc:  # pragma: no cover — never 500 the surface
                return JSONResponse({"service": "flower-brain-metrics", "label": MODELED_LABEL,
                                     "error": "compute fail-open: %s" % (type(exc).__name__)},
                                    status_code=200)

        add_api_route = getattr(app, "add_api_route", None)
        if callable(add_api_route):
            app.add_api_route(paths[0], _metrics_h, methods=["GET"])
        else:
            from starlette.routing import Route  # type: ignore

            async def _m(request):  # type: ignore
                return JSONResponse(flower_metrics(seed=int(request.query_params.get("seed", 42))))

            app.router.routes.append(Route(paths[0], _m))
    except Exception:
        pass  # additive registration must never break app boot

    return paths


# --------------------------------------------------------------------------------------
# Self-test (run `python3 szl_kc_flower_metrics.py` — must print ALL OK).
# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    m = flower_metrics(seed=42)

    print("label:", m["label"])
    print("nodes:", m["nodes_total"], "| edges:", m["edges_total"],
          "| cross-petal edges:", m["cross_petal_edges"])
    print("bridge_node_count:", m["bridge_node_count"])
    print("bridge nodes (id  petal->[petals]  cross_degree):")
    for bn in m["bridge_nodes"]:
        print("  %-22s petal %d -> %s  cross_degree=%d" %
              (bn["id"], bn["petal"], bn["connects_petals"], bn["cross_petal_degree"]))
    print("per-petal internal density:")
    for pd in m["per_petal_density"]:
        print("  petal %d %-20s density=%s (%d/%d edges, %d nodes)" %
              (pd["petal"], pd["name"], pd["internal_density"],
               pd["internal_edges"], pd["max_possible_edges"], pd["node_count"]))
    print("fiedler_lambda2 (whole %d-node flower):" % m["nodes_total"], m["fiedler_lambda2"],
          "| whole-flower one organism:", m["flower_is_connected"])
    print("  dependency web: %d connected clusters, %d wired nodes, %d isolated leaves" %
          (m["component_count"], m["connective_core_size"], m["isolated_node_count"]))
    print("  fiedler_lambda2 within largest cluster (%d nodes):" % m["largest_component_size"],
          m["fiedler_lambda2_largest_component"])
    mc = m["most_connected_bridge"]
    print("most_connected_bridge:", mc["id"] if mc else None,
          ("(cross_degree=%d)" % mc["cross_petal_degree"]) if mc else "")

    # ---- HARD invariants ----
    assert m["label"] == MODELED_LABEL == "MODELED", m["label"]
    assert m["bridge_node_count"] >= 1, "expected at least one cross-petal bridge node"
    assert all(bn["cross_petal_degree"] >= 1 for bn in m["bridge_nodes"]), "bridge => >=1 cross edge"
    assert len(m["per_petal_density"]) == 8, "8 petals of density"
    assert all(0.0 <= pd["internal_density"] <= 1.0 for pd in m["per_petal_density"]), "density in [0,1]"
    # Fiedler lambda2 is reported HONESTLY (never fabricated). It equals algebraic
    # connectivity: 0 when the graph is multiple clusters, >0 when one component.
    assert isinstance(m["fiedler_lambda2"], float), "lambda2 must be a real number"
    assert m["fiedler_lambda2"] >= 0.0, "lambda2 is non-negative"
    # honest connectivity bookkeeping is self-consistent
    assert (m["fiedler_lambda2"] > 1e-9) == m["flower_is_connected"], "lambda2>0 <=> connected"
    assert m["flower_is_connected"] == (m["component_count"] == 1 and m["isolated_node_count"] == 0), \
        "one organism <=> exactly one component and zero isolated leaves"
    assert m["component_count"] >= 1, "there is at least one dependency cluster"
    assert m["largest_component_size"] >= 2, "largest cluster has >=2 nodes"
    # a multi-node connected cluster has a positive internal lambda2 (the eigensolver works)
    assert m["fiedler_lambda2_largest_component"] > 0.0, \
        "largest cluster must be internally connected (lambda2>0)"
    assert 0 <= m["isolated_node_count"] < m["nodes_total"], "isolated count sane"
    assert m["connective_core_size"] >= 2, "connective core must have >=2 wired nodes"
    assert m["most_connected_bridge"] is not None
    # determinism
    assert flower_metrics(42) == flower_metrics(42), "metrics must be deterministic"
    # register returns the single exact path (no app needed — try/except-guarded)
    class _NoApp:
        pass
    paths = register(_NoApp(), ns="killinchu")
    assert paths == ["/api/killinchu/v1/flower/metrics"], paths
    print("register paths:", paths)

    print("szl_kc_flower_metrics: cross-petal metrics on the real flower graph, "
          "Fiedler lambda2 connectivity, deterministic.", file=sys.stderr)
    print("ALL OK")
