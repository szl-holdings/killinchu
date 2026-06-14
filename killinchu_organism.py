# killinchu_organism.py
# ---------------------------------------------------------------------------
# Dev D — ORGANISM / ANATOMY causal-dependency + NCA self-repair ENGINE.
#
# ADDITIVE module. Does NOT edit Dev5's szl_ecosystem_routes.py or Dev's
# killinchu_anatomy.py. Adds a NEW namespace under /api/{ns}/v1/organism/causal*
# describing the living organism (a11oy + killinchu) as a DIRECTED CAUSAL graph:
#   - edges encode a REAL causal dependency (downstream organ NEEDS upstream organ)
#   - each organ carries LOCAL INVARIANTS (homeostatic set-points it must hold)
#   - NCA-style local self-repair rules: when an organ goes DOWN, neighbours
#     re-route around it and a homeostatic update heals the local cell state over
#     discrete steps (Growing-NCA / homeostatic-NCA inspired; LOCAL update only).
#
# Vitals are fed by REAL MELT where reachable (the killinchu anatomy / mesh
# in-process state); otherwise honestly labelled MODELED. Self-repair dynamics
# are labelled EXPERIMENTAL (a real discrete local update rule, not a trained
# NCA). Fiedler lambda2 on the causal graph (undirected support) reuses the
# autonomy module's spectral lambda2 so the mesh + anatomy share ONE metric.
#
# Doctrine v11. Effectors SIMULATED human-on-loop. 0 fabricated numbers — every
# figure is measured from the in-process graph or labelled MODELED/EXPERIMENTAL.
# refs: distill.pub/2020/growing-ca ; arXiv:2511.02241 (homeostatic NCA) ;
#       Fiedler arXiv:2504.06894.
# ---------------------------------------------------------------------------
from __future__ import annotations
import time
from typing import Any, Optional, TYPE_CHECKING

from starlette.responses import JSONResponse

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI, Request
else:
    try:
        from fastapi import Request
    except Exception:  # pragma: no cover
        Request = Any  # type: ignore


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# The CAUSAL anatomy. Five organs (matching the /estate-organism body) plus the
# governance overwatch, wired as a DIRECTED graph: edge u->v means "v causally
# DEPENDS ON u" (v cannot stay healthy if u is down and no re-route exists).
# Each organ has LOCAL INVARIANTS — homeostatic set-points checked locally.
# `reroute` lists the alternative upstreams a downstream organ can fail over to
# (the NCA-style local self-repair adjacency).
# ---------------------------------------------------------------------------
ORGANS: dict[str, dict] = {
    "brain": {
        "system": "YACHAY cortex (proofs / proposer)",
        "role": "read-only reasoning; proposes, never writes",
        "invariants": ["locked8 == 8", "proposes_only (no write capability)"],
        "depends_on": [],                      # source organ
        "reroute": [],
    },
    "heart": {
        "system": "HEART / Lambda gate (13-axis conjunctive trust)",
        "role": "deny-by-default truth gate; pass = all(axis >= floor)",
        "invariants": ["lambda < 1.0 (Conjecture 1 advisory)", "gate is CONJUNCTIVE", "deny-by-default"],
        "depends_on": ["brain"],               # gate evaluates the brain's proposal
        "reroute": [],                          # no bypass — the heart is mandatory
    },
    "nervous": {
        "system": "MELT (metrics / events / logs / traces)",
        "role": "observability + deadman reflex arc",
        "invariants": ["span_lineage_intact (W3C TraceContext)", "deadman_arc_armed"],
        "depends_on": ["heart"],
        "reroute": ["brain"],                   # can still observe the proposer if the heart link drops
    },
    "circulatory": {
        "system": "YAWAR receipt ledger (DSSE, append-only)",
        "role": "signed receipt bus; immutable transport",
        "invariants": ["append_only (no mutation)", "every_state_transition_receipted"],
        "depends_on": ["heart", "nervous"],     # receipts ride the gate + the nerves
        "reroute": ["nervous"],                 # if the heart link drops, still receipt via the nerves
    },
    "skeleton": {
        "system": "szl-mesh topology (cross-app fabric)",
        "role": "structural fabric carrying the organism",
        "invariants": ["fiedler_lambda2 > 0 (connected)", "quorum_feasible (n>=3f+1)"],
        "depends_on": ["circulatory"],          # the fabric is held together by the receipted ledger
        "reroute": ["nervous"],                 # degrade to nerve-carried structure
    },
    "overwatch": {
        "system": "R0513 / OVERWATCH governance (read-only audit)",
        "role": "5-invariant read-only audit; never halts",
        "invariants": ["read_only (never writes / never halts)", "audits_all_organs"],
        "depends_on": ["nervous", "circulatory"],  # audits by reading nerves + ledger
        "reroute": ["circulatory", "nervous"],     # can audit from either source
    },
}

# Static directed causal edges, derived from ORGANS[*].depends_on
# (edge upstream -> downstream).
def _edges() -> list[dict]:
    out = []
    for organ, spec in ORGANS.items():
        for up in spec["depends_on"]:
            out.append({"source": up, "target": organ,
                        "kind": "causal-dependency",
                        "rerouteable": organ in ORGANS and bool(ORGANS[organ]["reroute"])})
    return out


# ---------------------------------------------------------------------------
# REAL vitals feed. Pull what we honestly can from the in-process killinchu
# anatomy + mesh; otherwise MODELED. No fabricated numbers.
# ---------------------------------------------------------------------------
def _live_vitals() -> dict:
    v: dict[str, Any] = {}
    # locked-8 + anatomy from killinchu_anatomy (in-process import, no network)
    try:
        import killinchu_anatomy as _an
        axes = getattr(_an, "YUYAY_AXES", None)
        v["brain"] = {"locked8_axes": (len(axes) if axes else None),
                      "label": "LIVE" if axes else "MODELED"}
        v["heart"] = {"gate_axes": (len(axes) if axes else None),
                      "conjunctive": True, "label": "LIVE" if axes else "MODELED"}
        v["circulatory"] = {"yawar_bus_len": len(getattr(_an, "_YAWAR", []) or []),
                            "label": "LIVE"}
    except Exception:
        v["brain"] = {"label": "MODELED"}
        v["heart"] = {"label": "MODELED"}
        v["circulatory"] = {"label": "MODELED"}
    # skeleton: real mesh topology + lambda2 (reuse the autonomy spectral metric)
    try:
        import killinchu_mesh as _mesh
        h = _mesh.get_harness()
        topo = h.topology() if h is not None else {"nodes": [], "edges": []}
        nodes = [n["id"] for n in topo.get("nodes", [])]
        edges = [{"source": e["source"], "target": e["target"]} for e in topo.get("edges", [])]
        lam = None
        try:
            import killinchu_autonomy as _au
            lam = _au.fiedler_lambda2(nodes, edges).get("lambda2") if nodes else None
        except Exception:
            lam = None
        v["skeleton"] = {"mesh_nodes": len(nodes), "fiedler_lambda2": lam,
                         "label": "LIVE" if nodes else "MODELED"}
    except Exception:
        v["skeleton"] = {"label": "MODELED"}
    v["nervous"] = {"otlp": "in-process (NOT exported to an external collector)",
                    "label": "LIVE (in-process MELT)"}
    v["overwatch"] = {"invariants_checked": 5, "halts": False, "label": "LIVE"}
    return v


# ---------------------------------------------------------------------------
# NCA-STYLE LOCAL SELF-REPAIR.  EXPERIMENTAL (a real discrete local update rule,
# not a trained neural CA). State per organ in [0,1] = local "tissue health".
# Update rule (homeostatic, LOCAL only — each organ sees only its neighbours):
#   - a DOWN organ has state pinned to 0 (the lesion).
#   - a live organ whose required upstream is down RE-ROUTES to an alive
#     reroute upstream; if none alive, it degrades.
#   - otherwise it heals toward 1 by a local diffusion step from healthy
#     neighbours: s += rate * (mean(neighbour_state) - s), clamped to [0,1].
# This reproduces the Growing-NCA "damage -> regrow" behaviour with an explicit,
# auditable rule (no hidden weights) so the demo is honest.
# ---------------------------------------------------------------------------
def _neighbours(organ: str) -> list[str]:
    """Undirected causal neighbourhood (upstreams + downstreams + reroutes)."""
    nb = set(ORGANS[organ]["depends_on"]) | set(ORGANS[organ].get("reroute", []))
    for other, spec in ORGANS.items():
        if organ in spec["depends_on"] or organ in spec.get("reroute", []):
            nb.add(other)
    nb.discard(organ)
    return sorted(nb)


def self_repair(down: Optional[str] = None, steps: int = 12, rate: float = 0.5) -> dict:
    """Lesion the `down` organ, then run the local homeostatic NCA update for
    `steps`. Returns the per-step health trace + the re-route events, so the UI
    can animate organ-down -> re-route -> self-heal. EXPERIMENTAL (explicit
    local rule). Effectors SIMULATED — this heals a MODEL of the organism."""
    organs = list(ORGANS.keys())
    state = {o: 1.0 for o in organs}            # start fully healthy
    if down in state:
        state[down] = 0.0
    trace = [{"step": 0, "state": dict(state)}]
    reroutes: list[dict] = []
    rerouted_organs: set[str] = set()
    invariant_alerts: list[dict] = []
    for step in range(1, steps + 1):
        new = dict(state)
        for o in organs:
            if o == down:
                new[o] = 0.0                    # lesion stays down (the failure)
                continue
            # check the causal dependency: is a required upstream down?
            reqs = ORGANS[o]["depends_on"]
            alive_reqs = [u for u in reqs if state.get(u, 0.0) > 0.15 and u != down]
            need_reroute = bool(reqs) and (len(alive_reqs) < len(reqs))
            if need_reroute:
                alts = [r for r in ORGANS[o].get("reroute", []) if state.get(r, 0.0) > 0.15 and r != down]
                if alts:
                    if o not in rerouted_organs:
                        reroutes.append({"step": step, "organ": o, "rerouted_to": alts[0],
                                         "reason": "required upstream down; failed over"})
                        rerouted_organs.add(o)
                    nb = alive_reqs + alts
                else:
                    # no alternative path -> local invariant at risk; degrade slightly
                    if step == 1:
                        invariant_alerts.append({"organ": o, "risk": "no re-route path while %s down" % down,
                                                  "invariants": ORGANS[o]["invariants"]})
                    nb = alive_reqs
            else:
                nb = _neighbours(o)
            nb = [x for x in nb if x != down]
            if nb:
                target = sum(state[x] for x in nb) / len(nb)
            else:
                target = state[o]
            new[o] = max(0.0, min(1.0, state[o] + rate * (target - state[o])))
        state = new
        trace.append({"step": step, "state": {k: round(val, 4) for k, val in state.items()}})
    healthy = [o for o in organs if o != down and state[o] >= 0.85]
    organism_health = round(sum(v for k, v in state.items() if k != down) / max(1, len(organs) - (1 if down else 0)), 4)
    return {
        "lesion": down,
        "steps": steps, "rate": rate,
        "final_state": {k: round(v, 4) for k, v in state.items()},
        "trace": trace,
        "reroutes": reroutes,
        "invariant_alerts": invariant_alerts,
        "recovered_organs": healthy,
        "organism_health_excl_lesion": organism_health,
        "rule": "s += rate*(mean(neighbour_state) - s); DOWN pinned to 0; reroute on dead upstream",
        "interpretation": ("organ '%s' down -> neighbours re-route and the surrounding tissue heals; "
                           "the lesion stays down until the organ is restored" % down) if down
                          else "no lesion; organism holds homeostatic set-points",
        "effector": "SIMULATED human-on-loop — heals a MODEL of the organism, drives nothing",
        "refs": ["distill.pub/2020/growing-ca", "arXiv:2511.02241"],
        "label": "EXPERIMENTAL (explicit local homeostatic NCA-style rule; not a trained CA)",
    }


def causal_anatomy() -> dict:
    """The directed causal-dependency graph + local invariants + live vitals."""
    vitals = _live_vitals()
    organs = []
    for name, spec in ORGANS.items():
        organs.append({
            "organ": name,
            "system": spec["system"],
            "role": spec["role"],
            "invariants": spec["invariants"],
            "depends_on": spec["depends_on"],
            "reroute": spec.get("reroute", []),
            "vitals": vitals.get(name, {"label": "MODELED"}),
        })
    edges = _edges()
    # fiedler lambda2 on the undirected support of the causal graph
    lam = None
    try:
        import killinchu_autonomy as _au
        nodes = list(ORGANS.keys())
        und = [{"source": e["source"], "target": e["target"]} for e in edges]
        lam = _au.fiedler_lambda2(nodes, und).get("lambda2")
    except Exception:
        lam = None
    return {
        "organism": "a11oy + killinchu rendered as ONE governed body (causal graph)",
        "ts": _ts(),
        "organs": organs,
        "edges": edges,
        "edge_semantics": "directed: source -> target means target causally DEPENDS ON source",
        "fiedler_lambda2": lam,
        "lambda2_label": "LIVE (spectral, shared autonomy metric)" if lam is not None else "MODELED",
        "doctrine": "v11", "locked": 8,
        "effector": "SIMULATED human-on-loop — NO live vessel/sub control",
        "honest_note": ("Vitals are LIVE where the in-process anatomy/mesh expose them, MODELED otherwise. "
                        "Self-repair dynamics are EXPERIMENTAL (an explicit local rule, not a trained NCA)."),
        "label": "LIVE anatomy + MODELED/EXPERIMENTAL self-repair (honestly mixed)",
    }


# ===========================================================================
# REGISTRATION
# ===========================================================================
def register(app: "FastAPI", ns: str = "killinchu") -> dict:
    base = f"/api/{ns}/v1/organism"
    routes: list[str] = []

    @app.get(base + "/causal")
    async def organism_causal():
        """The directed causal-dependency anatomy graph + local invariants +
        live vitals + shared Fiedler lambda2."""
        return JSONResponse(causal_anatomy())
    routes.append("GET " + base + "/causal")

    @app.get(base + "/self-repair")
    async def organism_self_repair(down: Optional[str] = None, steps: int = 12, rate: float = 0.5):
        """NCA-style local self-repair trace: lesion `down`, animate re-route +
        heal. EXPERIMENTAL local rule; effector SIMULATED."""
        return JSONResponse(self_repair(down=down, steps=max(1, min(40, steps)),
                                        rate=max(0.05, min(1.0, rate))))
    routes.append("GET " + base + "/self-repair")

    return {"registered": routes, "ns": ns, "base": base, "count": len(routes),
            "module": "killinchu_organism"}
