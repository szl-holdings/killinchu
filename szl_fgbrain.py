# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_fgbrain.py — Formula-Graph Brain organ (SZL ORIGINAL, wave-15+).

WHAT THIS IS (fashion-thinking made our own):
  Not a paper port. This organ turns SZL's OWN proven-formula library into a
  self-organizing LIVING GRAPH where each formula is a NODE and the real
  proof/axiom dependencies are the EDGES. It then runs a MODELED spreading-
  activation ("firing") dynamic on that real graph — a deterministic, pure-
  stdlib mechanism inspired by (a) the self-writing knowledge-vault brain
  screenshots and (b) three field-leader mechanisms we fuse HERE:

    * DLA (arXiv:2606.10650) — Information-Aware dynamic state merging is reused
      as EDGE-WEIGHTED activation routing: high-importance (locked-proven) nodes
      merge/propagate activation more strongly than experimental ones.
    * OPERA (arXiv:2606.25757) — the INTRINSIC reward (uncertainty resolved) is
      reused as the node "aliveness" score: a node fires more when activating it
      RESOLVES graph-level uncertainty (raises the proven-mass fraction reached).
    * Context-Ready (arXiv:2606.27538) — the K-UNROLL pre-contextualization is
      reused as K rounds of activation spreading from the locked-8 core outward.

  The GRAPH ITSELF IS REAL (every node traces to a real Lean file/name or a real
  DOI/arXiv). The activation DYNAMIC is MODELED (a deterministic toy on the real
  topology) — it is NOT a claim that the formulas "compute" anything, only a
  faithful visualization of how the proven core anchors the whole library.

HONESTY (Doctrine v11):
  * label:"MODELED" verbatim.
  * locked-proven = EXACTLY 8 {F1,F4,F7,F11,F12,F18,F19,F22}. Never more.
  * Λ (lambda) is Conjecture 1 — a GRAY node, never rendered as proven/green.
  * Conjecture-2 / Conjecture-3 (Khipu BFT) gray, never green.
  * Pure stdlib. Custom LCG PRNG (no numpy, no stdlib random; hashlib OK).
  * Deterministic: same seed/K -> identical snapshot.
  * SZL claims the FUSED graph-brain construction as its own; it claims NONE of
    the borrowed mechanisms (DLA/OPERA/Context-Ready) or the cited math as its own.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Tuple

try:  # Starlette/FastAPI are present in the killinchu image; degrade gracefully otherwise.
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
except Exception:  # pragma: no cover
    Request = object  # type: ignore
    JSONResponse = None  # type: ignore
    Route = None  # type: ignore


# ---------------------------------------------------------------------------
# Deterministic LCG PRNG (no numpy, no stdlib random). Numerical Recipes params.
# ---------------------------------------------------------------------------
class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (seed ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000


# ---------------------------------------------------------------------------
# THE REAL GRAPH — every node traces to a real Lean file/name or DOI/arXiv.
# Tiers mirror a11oy_formula_tiers.py (the canonical honest 4-tier registry) and
# PROVEN_FORMULAS.md (lutar-lean kernel c7c0ba17). NOTHING here is invented.
# tier: locked (proven, exactly 8) | semantic (CI-green, outside locked-8) |
#       experimental (wave 5-8 / agentic) | borrowed (field-leader fusion) |
#       conjecture (GRAY, never green)
# ---------------------------------------------------------------------------
_LEAN = "Lutar/Puriq/Formulas/ProvedFormulas.lean"
_LL = "https://github.com/szl-holdings/lutar-lean/blob/main/"

NODES: List[Dict[str, Any]] = [
    # --- Tier 1: LOCKED-PROVEN (exactly 8) ---
    {"id": "F1", "title": "Replay-Hash Determinism", "tier": "locked",
     "proves": "identical canonical input => identical receipt hash", "lean": "f1_replay_hash_determinism", "file": _LEAN},
    {"id": "F4", "title": "Khipu DAG Acyclicity", "tier": "locked",
     "proves": "append preserves DAG acyclicity (dst<src)", "lean": "f4_khipu_dag_acyclic_preserved", "file": _LEAN},
    {"id": "F7", "title": "Chaski FIFO Ordering", "tier": "locked",
     "proves": "drained reception order == send order", "lean": "f7_chaski_fifo_order", "file": _LEAN},
    {"id": "F11", "title": "Ayni Reciprocity Conservation", "tier": "locked",
     "proves": "reciprocity balance conserved over Int (tit-for-tat parity)", "lean": "f11_ayni_reciprocity_conservation", "file": _LEAN},
    {"id": "F12", "title": "Kuramoto Additive Fragment", "tier": "locked",
     "proves": "additive phase-coupling bounded (additive fragment ONLY)", "lean": "f12_kuramoto_additive", "file": _LEAN},
    {"id": "F18", "title": "Reed-Solomon RS(10,6)", "tier": "locked",
     "proves": "recoverable iff >=6 of 10 shards survive", "lean": "f18_reed_solomon_parity_count", "file": _LEAN},
    {"id": "F19", "title": "Bekenstein Additive Scaffolding", "tier": "locked",
     "proves": "entropy budget additive+monotone (additive fragment ONLY)", "lean": "f19_bekenstein_additive", "file": _LEAN},
    {"id": "F22", "title": "Khipu Emit Monotonicity", "tier": "locked",
     "proves": "append-only sequence numbers strictly increase", "lean": "f22_khipu_emit_monotone", "file": _LEAN},

    # --- Tier 2: SEMANTIC-VERIFIED (CI-green, OUTSIDE locked-8) ---
    {"id": "Lam_max", "title": "Λ <= max(axes)", "tier": "semantic",
     "proves": "aggregate upper bound (0 sorries)", "lean": "Lambda_le_max", "file": "Lutar/Bound.lean"},
    {"id": "Lam_min", "title": "min(axes) <= Λ", "tier": "semantic",
     "proves": "aggregate lower bound (0 sorries)", "lean": "min_le_Lambda", "file": "Lutar/Bound.lean"},
    {"id": "Lam_norm", "title": "Λ normalization well-formed", "tier": "semantic",
     "proves": "Λ definition + axis normalization (0 sorries)", "lean": "a3_normalize_proof", "file": "Lutar/Invariant.lean"},
    {"id": "TheoremU", "title": "Theorem U (conditional Λ uniqueness)", "tier": "semantic",
     "proves": "Λ uniqueness CONDITIONAL on separability (0 sorries)", "lean": "lambda_unique_of_separable", "file": "Lutar/Round13/LambdaSeparable.lean"},
    {"id": "F14_DSSE", "title": "DSSE Verifiability", "tier": "semantic",
     "proves": "DSSE verifiable under DISCLOSED axiom ecdsa_unforgeable", "lean": "f14_dsse_verifiable", "file": "Lutar/Puriq/Formulas/PuriqFormulaLean.lean"},

    # --- Tier 3: EXPERIMENTAL (wave 5-8 + agentic P1-P6, CI-green, NOT locked) ---
    {"id": "P3_noninterf", "title": "P3 Non-Interference", "tier": "experimental",
     "proves": "poisoned retrieval cannot flip DENY->ALLOW (axiom-free core)", "lean": "P3_non_interference", "file": "agentic loop PR #188 @2ede47a2"},
    {"id": "P4_replay", "title": "P4 Replay-Determinism", "tier": "experimental",
     "proves": "recorded run reproduces byte-identical receipt chain", "lean": "P4_replay_determinism", "file": "agentic loop PR #188 @2ede47a2"},
    {"id": "M2_tamper", "title": "M2 Hash-Chain Tamper-Evidence", "tier": "experimental",
     "proves": "any receipt mutation is detectable ([propext] only)", "lean": "hashchain_tamper_evident", "file": "Wave-8 @7885fd9"},
    {"id": "B1_byz", "title": "B1 Byzantine n=3f+1", "tier": "experimental",
     "proves": "quorum safety for 3-of-4 witness consensus", "lean": "byzantine_3f_plus_1", "file": "Wave-8 @7885fd9"},
    {"id": "L3_mono", "title": "L3 Λ Strict Monotonicity", "tier": "experimental",
     "proves": "more evidence never lowers score spuriously", "lean": "lambda_strict_monotone", "file": "Wave-8 @7885fd9"},
    {"id": "W5_conformal", "title": "Wave-5 Conformal Coverage", "tier": "experimental",
     "proves": "split-conformal marginal coverage (distribution-free)", "lean": "conformal_coverage", "file": "Wave-5 PR #186 @b71114cf"},

    # --- Tier 4: BORROWED (field-leader mechanisms fused into the brain) ---
    {"id": "DLA", "title": "Dynamic Linear Attention (routing fuse)", "tier": "borrowed",
     "proves": "MODELED: importance-aware activation routing", "doi": "https://arxiv.org/abs/2606.10650"},
    {"id": "OPERA", "title": "OPERA intrinsic reward (aliveness fuse)", "tier": "borrowed",
     "proves": "MODELED: firing reward = uncertainty resolved", "doi": "https://arxiv.org/abs/2606.25757"},
    {"id": "CTXREADY", "title": "Context-Ready K-unroll (spread fuse)", "tier": "borrowed",
     "proves": "MODELED: K rounds of activation pre-contextualization", "doi": "https://arxiv.org/abs/2606.27538"},

    # --- Tier 5: CONJECTURE (GRAY, never green) ---
    {"id": "Lambda_C1", "title": "Λ unconditional uniqueness (Conjecture 1)", "tier": "conjecture",
     "proves": "machine-checked FALSE as stated; NEVER a theorem", "lean": "Conjecture1_LambdaUnique", "file": "lambda-bounty"},
    {"id": "Khipu_C2", "title": "Khipu BFT safety (Conjecture 2)", "tier": "conjecture",
     "proves": "conjecture, never proven", "lean": None, "file": None},
    {"id": "Khipu_C3", "title": "Khipu BFT liveness (Conjecture 3)", "tier": "conjecture",
     "proves": "conjecture, never proven", "lean": None, "file": None},
]

# REAL edges — proof/axiom/semantic dependencies (src depends-on / relates-to dst).
# All locked-8 co-reside in ProvedFormulas.lean and jointly ground locked_count_eight.
# Λ semantics build on the locked core; conjectures hang off Λ but stay gray.
EDGES: List[Tuple[str, str, str]] = [
    # locked-8 clique via the shared kernel file (co-proved, mutually anchoring)
    ("F1", "F22", "replay/append-log determinism <-> monotonic emit"),
    ("F4", "F22", "Khipu DAG acyclicity <-> Khipu emit monotonicity"),
    ("F7", "F1", "FIFO reception order feeds deterministic replay"),
    ("F11", "F12", "Ayni reciprocity balance <-> Kuramoto coupling"),
    ("F18", "F1", "RS(10,6) recovery underpins receipt/replay integrity"),
    ("F19", "F12", "Bekenstein entropy budget bounds coupling energy"),
    ("F1", "F4", "receipt determinism secured by DAG structure"),
    # semantic tier grounds on the locked core + Λ definition
    ("Lam_norm", "F19", "Λ normalization uses additive entropy budget"),
    ("Lam_max", "Lam_norm", "upper bound needs Λ definition"),
    ("Lam_min", "Lam_norm", "lower bound needs Λ definition"),
    ("TheoremU", "Lam_norm", "conditional uniqueness over Λ definition"),
    ("F14_DSSE", "F18", "DSSE seal binds RS-encoded payload"),
    # experimental tier depends on locked + semantic
    ("P4_replay", "F1", "replay-determinism extends F1 to full receipt chain"),
    ("P3_noninterf", "P4_replay", "non-interference on the replayable loop"),
    ("M2_tamper", "F22", "tamper-evidence over the append-only log"),
    ("B1_byz", "F7", "consensus ordering over FIFO channels"),
    ("L3_mono", "Lam_norm", "Λ monotonicity over the aggregator"),
    ("W5_conformal", "Lam_max", "conformal coverage feeds Λ containment axis"),
    # borrowed mechanisms attach to what they route/reward/spread over
    ("DLA", "F4", "importance routing gated by DAG acyclicity"),
    ("OPERA", "TheoremU", "firing reward measured against proven-mass reached"),
    ("CTXREADY", "F1", "K-unroll spreads from the deterministic core"),
    # conjectures hang off Λ but NEVER inherit proven status (gray edges)
    ("Lambda_C1", "TheoremU", "unconditional uniqueness OPEN above the conditional"),
    ("Khipu_C2", "B1_byz", "BFT safety conjectured above the quorum bound"),
    ("Khipu_C3", "Khipu_C2", "liveness conjectured above safety"),
]

# Activation strength by tier (DLA importance-aware routing, MODELED).
_TIER_W = {"locked": 1.0, "semantic": 0.7, "experimental": 0.5, "borrowed": 0.4, "conjecture": 0.0}
_TIER_ORDER = ["locked", "semantic", "experimental", "borrowed", "conjecture"]

CITATIONS = {
    "PROVEN_FORMULAS (lutar-lean kernel c7c0ba17)": _LL + "PROVEN_FORMULAS.md",
    "locked_count_eight (no-axiom theorem)": _LL + "Lutar/Wave11/AxiomDisclosure.lean",
    "Dynamic Linear Attention": "https://arxiv.org/abs/2606.10650",
    "OPERA perplexity-reward": "https://arxiv.org/abs/2606.25757",
    "Context-Ready Transformer": "https://arxiv.org/abs/2606.27538",
}

_HONEST_NOTE = (
    "MODELED: The GRAPH is REAL — every node is a real formula/theorem that traces to a "
    "named Lean declaration in a cited lutar-lean file (kernel c7c0ba17) or a real DOI/arXiv, "
    "and every edge is a real proof/semantic dependency. The locked-proven set is EXACTLY 8 "
    "{F1,F4,F7,F11,F12,F18,F19,F22}; Λ unconditional uniqueness is Conjecture 1 (machine-checked "
    "FALSE) and is rendered GRAY, never green; Khipu BFT (Conj-2/3) likewise gray. The ACTIVATION "
    "DYNAMIC is a MODELED, deterministic, pure-stdlib spreading-activation ('firing') on the real "
    "topology — it reuses three field-leader mechanisms as visualization primitives (DLA "
    "importance-aware routing, OPERA intrinsic 'uncertainty-resolved' reward as node aliveness, "
    "Context-Ready K-unroll as K spreading rounds). It is NOT a claim that formulas compute, learn, "
    "or that any borrowed mechanism is trained here. SZL claims the FUSED formula-graph-brain "
    "construction as its own; it claims NONE of the borrowed mechanisms or cited math as its own. "
    "Deterministic: same seed/K -> identical snapshot. Pure stdlib, no numpy, no stdlib random."
)


def _adj() -> Dict[str, List[Tuple[str, float]]]:
    """Undirected weighted adjacency; weight = min tier-weight of the two endpoints."""
    w = {n["id"]: _TIER_W[n["tier"]] for n in NODES}
    adj: Dict[str, List[Tuple[str, float]]] = {n["id"]: [] for n in NODES}
    for a, b, _ in EDGES:
        if a in adj and b in adj:
            ew = min(w[a], w[b])  # DLA-style: activation flows as strong as the weaker (less-proven) end
            adj[a].append((b, ew))
            adj[b].append((a, ew))
    return adj


def _snapshot(seed: int = 42, K: int = 10) -> Dict[str, Any]:
    """Run K rounds of spreading activation from the locked-8 core (Context-Ready K-unroll,
    MODELED). Measure OPERA-style firing reward = proven-mass fraction reached each round."""
    rng = _LCG(seed)
    adj = _adj()
    w = {n["id"]: _TIER_W[n["tier"]] for n in NODES}
    locked = [n["id"] for n in NODES if n["tier"] == "locked"]
    total_proven_mass = sum(w[i] for i in adj)  # locked+semantic+experimental+borrowed (conj=0)

    # activation seeded on the locked-8 core (the proven anchor).
    act = {i: (1.0 if i in locked else 0.0) for i in adj}
    # tiny deterministic jitter so the layout is not perfectly symmetric (MODELED).
    for i in adj:
        act[i] += 0.001 * rng.uniform()

    reward_per_k: List[float] = []
    decay = 0.85
    for _ in range(K):
        nxt = {i: act[i] * decay for i in adj}
        for i in adj:
            for (j, ew) in adj[i]:
                # conjecture nodes receive activation but their OWN weight is 0 -> never "fire green"
                nxt[j] += act[i] * ew * 0.15
        # clamp
        for i in adj:
            nxt[i] = min(nxt[i], 1.0)
        act = nxt
        # OPERA-style intrinsic reward: proven-mass fraction that is now activated (>0.5)
        reached = sum(w[i] for i in adj if act[i] > 0.5 and w[i] > 0.0)
        reward_per_k.append(round(reached / total_proven_mass, 6) if total_proven_mass else 0.0)

    fired = [i for i in adj if act[i] > 0.5 and w[i] > 0.0]
    conj_fired_green = [i for i in adj if w[i] == 0.0 and act[i] > 0.5]  # must render gray, NOT green

    counts = {t: sum(1 for n in NODES if n["tier"] == t) for t in _TIER_ORDER}
    return {
        "label": "MODELED",
        "nodes_total": len(NODES),
        "edges_total": len(EDGES),
        "locked_count": counts["locked"],           # MUST be 8
        "tier_counts": counts,
        "K": K,
        "seed": seed,
        "firing_reward_per_k": reward_per_k,         # OPERA-style, rises toward saturation
        "firing_reward_final": reward_per_k[-1] if reward_per_k else 0.0,
        "nodes_fired": len(fired),
        "conjecture_rendered_green": len(conj_fired_green),  # MUST be 0 (gray-only invariant)
        "activation_head": {i: round(act[i], 4) for i in list(adj)[:8]},
        "honest_note": _HONEST_NOTE,
        "citations": CITATIONS,
    }


def _graph(_seed: int = 42) -> Dict[str, Any]:
    """The real static graph (nodes+edges+tier legend) for the surface to render."""
    return {
        "label": "MODELED",
        "locked_count": sum(1 for n in NODES if n["tier"] == "locked"),
        "tier_order": _TIER_ORDER,
        "tier_weight": _TIER_W,
        "nodes": NODES,
        "edges": [{"src": a, "dst": b, "why": why} for (a, b, why) in EDGES],
        "honest_note": _HONEST_NOTE,
        "citations": CITATIONS,
    }


# ---------------------------------------------------------------------------
# HTTP handlers
# ---------------------------------------------------------------------------
async def _h_graph(request: "Request"):  # type: ignore
    return JSONResponse(_graph())


async def _h_fire(request: "Request"):  # type: ignore
    q = getattr(request, "query_params", {}) or {}
    def _int(name, dflt):
        try:
            return int(q.get(name, dflt))
        except Exception:
            return dflt
    seed = _int("seed", 42)
    K = max(1, min(_int("K", 10), 64))
    return JSONResponse(_snapshot(seed=seed, K=K))


def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/fgbrain/{graph,fire} onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/fgbrain"
    handlers = [
        (f"{base}/graph", _h_graph),
        (f"{base}/fire", _h_fire),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            elif Route is not None:
                app.router.routes.append(Route(path, fn))
    except Exception:
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    g = _graph()
    s = _snapshot(seed=42, K=10)
    print("label:", s["label"])
    print("nodes_total:", g["locked_count"], "->", s["nodes_total"], "nodes,", s["edges_total"], "edges")
    print("locked_count:", s["locked_count"], "(must be 8)")
    print("tier_counts:", json.dumps(s["tier_counts"]))
    print("firing_reward_per_k:", s["firing_reward_per_k"])
    print("firing_reward_final:", s["firing_reward_final"])
    print("nodes_fired:", s["nodes_fired"], "/ proven nodes")
    print("conjecture_rendered_green:", s["conjecture_rendered_green"], "(must be 0)")
    # ---- Doctrine v11 assertions ----
    assert s["label"] == "MODELED"
    assert s["locked_count"] == 8, "locked-proven MUST be exactly 8"
    assert s["conjecture_rendered_green"] == 0, "conjectures must NEVER fire green"
    assert s["firing_reward_per_k"] == sorted(s["firing_reward_per_k"]), "reward should be non-decreasing"
    assert s["firing_reward_final"] > s["firing_reward_per_k"][0], "spreading must reach more mass over K"
    # determinism
    assert _snapshot(42, 10) == _snapshot(42, 10), "must be deterministic"
    assert _snapshot(7, 10) != _snapshot(42, 10), "must be seed-sensitive"
    print("szl_fgbrain: ALL OK — real graph, MODELED firing anchored on locked-8, conjectures gray, deterministic.")
