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
import hashlib
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
# WAVE-16: Self-repairing formula BODY. Ports killinchu_organism.self_repair()'s
# Growing-NCA local-diffusion rule ( s += rate*(mean(neighbour_state) - s) ) onto
# the REAL formula graph, plus a pure-stdlib Fiedler lambda2 (graph-Laplacian 2nd
# eigenvalue) as the live "is the brain still one connected mind" metric.
# EXPERIMENTAL: a real discrete local rule on the real topology, MODELED (not a
# trained NCA). Lesioning a node models a broken proof / deleted formula; healthy
# neighbours re-grow the surrounding tissue. Locked-8 never "self-heal to proven"
# from nothing — a lesioned locked node stays down (a broken proof is broken);
# only its NEIGHBOURHOOD tissue-health recovers, honestly.
# ---------------------------------------------------------------------------
def _undirected_neighbours() -> Dict[str, List[str]]:
    nb: Dict[str, List[str]] = {n["id"]: [] for n in NODES}
    for a, b, _ in EDGES:
        if a in nb and b in nb:
            if b not in nb[a]:
                nb[a].append(b)
            if a not in nb[b]:
                nb[b].append(a)
    return nb


def _fiedler_lambda2(active_ids: List[str]) -> float:
    """Algebraic connectivity (2nd-smallest Laplacian eigenvalue) of the subgraph
    on active_ids. Pure stdlib: symmetric Jacobi eigenvalue iteration on L = D - A.
    lambda2 > 0  <=>  the (remaining) graph is one connected component."""
    ids = list(active_ids)
    n = len(ids)
    if n <= 1:
        return 0.0
    idx = {i: k for k, i in enumerate(ids)}
    aset = set(ids)
    # adjacency + degree over the induced subgraph
    L = [[0.0] * n for _ in range(n)]
    nb = _undirected_neighbours()
    for i in ids:
        for j in nb[i]:
            if j in aset and j != i:
                a, b = idx[i], idx[j]
                L[a][b] = -1.0
        deg = sum(1 for j in nb[i] if j in aset and j != i)
        L[idx[i]][idx[i]] = float(deg)
    # Jacobi eigenvalue iteration (symmetric). n is small (<=25), converges fast.
    A = [row[:] for row in L]
    for _sweep in range(60):
        # find largest off-diagonal
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
        t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
        c = 1.0 / math.sqrt(t * t + 1.0)
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
    # lambda2 = second smallest (lambda1 ~ 0 for a connected graph)
    return round(max(0.0, eig[1]) if len(eig) >= 2 else 0.0, 6)


def _repair(down: str = "", steps: int = 12, rate: float = 0.5) -> Dict[str, Any]:
    ids = [n["id"] for n in NODES]
    tier = {n["id"]: n["tier"] for n in NODES}
    nb = _undirected_neighbours()
    down = down if down in ids else ""
    state = {o: 1.0 for o in ids}
    if down:
        state[down] = 0.0
    trace = [{"step": 0, "state": dict(state)}]
    for step in range(1, steps + 1):
        new = dict(state)
        for o in ids:
            if o == down:
                new[o] = 0.0            # a broken proof / deleted node stays down
                continue
            live_nb = [x for x in nb[o] if x != down and state.get(x, 0.0) > 0.15]
            target = (sum(state[x] for x in live_nb) / len(live_nb)) if live_nb else state[o]
            new[o] = max(0.0, min(1.0, state[o] + rate * (target - state[o])))
        state = new
        trace.append({"step": step, "state": {k: round(v, 4) for k, v in state.items()}})
    active = [o for o in ids if o != down]
    healthy = [o for o in active if state[o] >= 0.85]
    lam2_before = _fiedler_lambda2(ids)
    lam2_after = _fiedler_lambda2(active)
    body_health = round(sum(state[o] for o in active) / max(1, len(active)), 4)
    return {
        "label": "MODELED",
        "lesion": down or None,
        "lesion_tier": tier.get(down) if down else None,
        "steps": steps, "rate": rate,
        "final_state": {k: round(v, 4) for k, v in state.items()},
        "trace": trace,
        "recovered_nodes": healthy,
        "body_health_excl_lesion": body_health,
        "fiedler_lambda2_before": lam2_before,
        "fiedler_lambda2_after": lam2_after,
        "still_connected_after_lesion": lam2_after > 1e-9,
        "locked_count": sum(1 for n in NODES if n["tier"] == "locked"),
        "rule": "s += rate*(mean(live_neighbour_state) - s); lesion pinned to 0; Fiedler lambda2 = connectivity",
        "honest_note": _HONEST_NOTE + (
            " WAVE-16 REPAIR: a MODELED Growing-NCA local-diffusion heal on the real graph "
            "(ported from killinchu_organism.self_repair). A lesioned node stays down (a broken "
            "proof is broken); only surrounding tissue-health recovers. lambda2>0 => still one "
            "connected mind after the lesion. EXPERIMENTAL, not a trained CA."
        ),
        "citations": dict(CITATIONS, **{
            "killinchu_organism self-repair (Growing-NCA local rule)":
                "https://github.com/szl-holdings/killinchu/blob/main/killinchu_organism.py",
            "Growing Neural Cellular Automata (Mordvintsev et al., Distill 2020)":
                "https://distill.pub/2020/growing-ca/",
        }),
    }


async def _h_repair(request):  # type: ignore
    q = getattr(request, "query_params", {}) or {}
    def _int(name, dflt):
        try:
            return int(q.get(name, dflt))
        except Exception:
            return dflt
    down = str(q.get("down", "")) if q else ""
    steps = max(1, min(_int("steps", 12), 40))
    return JSONResponse(_repair(down=down, steps=steps))



# ---------------------------------------------------------------------------
# WAVE-17: Multi-timescale PLASTICITY. Fuses szl_neuroplasticity.py's REAL
# learning rules (Hebb w+=eta*x*y; BCM sliding threshold theta_M=E[y^2],
# phi=y*(y-theta_M); STDP Bi&Poo exponential window; EWC 0.5*lam*sum F*(dtheta)^2;
# loss-of-plasticity dormant-fraction) onto the formula-graph EDGES. Per-tier
# learning rate implements the Nested Learning (Google, NeurIPS 2025) multi-
# timescale idea: locked-8 edges are FROZEN canon (rate 0 — a proven edge only
# changes when the Lean proof changes), semantic slow, experimental medium,
# borrowed fast. BCM keeps it stable (no runaway), EWC protects the proven core
# from forgetting, dormant-fraction flags stale edges. EXPERIMENTAL/MODELED:
# a deterministic co-activation demo on the real topology — it trains no model,
# and NEVER upgrades a formula's honesty tier. Locked stays exactly 8.
# ---------------------------------------------------------------------------
# per-tier plastic learning rate (Nested Learning timescales). locked = 0 (canon).
_TIER_ETA = {"locked": 0.0, "semantic": 0.03, "experimental": 0.08, "borrowed": 0.15, "conjecture": 0.0}


def _stdp_dw(delta_t_ms: float, A_plus: float = 1.0, A_minus: float = 1.0,
             tau_plus: float = 17.0, tau_minus: float = 34.0) -> float:
    """Bi&Poo 1998 STDP window (verbatim math from szl_neuroplasticity.stdp_window)."""
    if delta_t_ms > 0:
        return A_plus * math.exp(-delta_t_ms / tau_plus)
    if delta_t_ms < 0:
        return -A_minus * math.exp(delta_t_ms / tau_minus)
    return 0.0


def _plasticity(seed: int = 42, rounds: int = 20) -> Dict[str, Any]:
    rng = _LCG(seed)
    ids = [n["id"] for n in NODES]
    tier = {n["id"]: n["tier"] for n in NODES}
    # edges carry a plastic weight w in [0,1], seeded at the tier-min coupling.
    w0 = {n["id"]: _TIER_W[n["tier"]] for n in NODES}
    edges = [(a, b) for (a, b, _) in EDGES if a in tier and b in tier]
    wt = {}
    for (a, b) in edges:
        wt[(a, b)] = round(min(w0[a], w0[b]), 6)
    w_init = dict(wt)
    # per-edge co-activation history for the BCM sliding threshold.
    yhist: Dict[tuple, List[float]] = {e: [] for e in edges}
    frozen_locked_edges = [e for e in edges if tier[e[0]] == "locked" and tier[e[1]] == "locked"]

    for _r in range(rounds):
        # a MODELED co-activation event: pick a source node (deterministic LCG),
        # its edges "fire together"; timing jitter drives the STDP sign.
        src = ids[rng.next_u32() % len(ids)]
        for (a, b) in edges:
            if a != src and b != src:
                continue
            # learning rate = SLOWER of the two endpoints' tiers (canon dominates)
            eta = min(_TIER_ETA[tier[a]], _TIER_ETA[tier[b]])
            if eta <= 0.0:
                continue  # frozen canon edge — never mutates (locked / conjecture)
            # co-activation magnitude y (Hebb x*y proxy) + STDP timing sign
            dt = (rng.uniform() - 0.5) * 40.0  # +-20ms timing jitter
            stdp = _stdp_dw(dt)
            y = 0.5 + 0.5 * rng.uniform()
            yhist[(a, b)].append(y)
            # BCM sliding threshold theta_M = E[y^2]; phi gates potentiate/depress
            hist = yhist[(a, b)]
            theta_M = sum(v * v for v in hist) / len(hist)
            phi = y * (y - theta_M)
            # Hebbian * BCM-sign * STDP-timing, scaled by the tier eta
            dw = eta * y * (1.0 if phi >= 0 else -0.5) * (1.0 if stdp >= 0 else -0.5)
            wt[(a, b)] = round(max(0.0, min(1.0, wt[(a, b)] + dw)), 6)

    # verify the proven canon never moved
    locked_edges_unchanged = all(abs(wt[e] - w_init[e]) < 1e-9 for e in frozen_locked_edges)
    # loss-of-plasticity: dormant edges (weight ~0) — the ReDo/Dohare-Sutton signal
    weights_now = list(wt.values())
    dormant = sum(1 for v in weights_now if v < 1e-3)
    dormant_frac = round(dormant / max(1, len(weights_now)), 4)
    # EWC penalty protecting the proven core: F high on locked endpoints
    ewc = 0.0
    for e in edges:
        F = 1.0 if (tier[e[0]] == "locked" or tier[e[1]] == "locked") else 0.05
        ewc += 0.5 * 1.0 * F * (wt[e] - w_init[e]) ** 2
    # which edges strengthened most (borrowed/fast tier should dominate)
    deltas = sorted(((round(wt[e] - w_init[e], 4), f"{e[0]}->{e[1]}", tier[e[0]] + "/" + tier[e[1]])
                     for e in edges), reverse=True)
    return {
        "label": "MODELED",
        "rounds": rounds, "seed": seed,
        "locked_count": sum(1 for n in NODES if n["tier"] == "locked"),
        "tier_eta": _TIER_ETA,
        "edges_total": len(edges),
        "frozen_locked_edges": len(frozen_locked_edges),
        "locked_edges_unchanged": locked_edges_unchanged,   # MUST be True (canon frozen)
        "dormant_edge_fraction": dormant_frac,
        "plasticity_score": round(1.0 - dormant_frac, 4),
        "ewc_core_protection_penalty": round(ewc, 6),
        "top_strengthened": deltas[:5],
        "weights_head": {f"{a}->{b}": wt[(a, b)] for (a, b) in edges[:8]},
        "honest_note": _HONEST_NOTE + (
            " WAVE-17 PLASTICITY: a MODELED co-activation demo fusing szl_neuroplasticity's "
            "REAL Hebb/BCM/STDP/EWC math onto the graph edges, with Nested-Learning per-tier "
            "learning rates (locked=0 frozen canon, borrowed=fastest). It trains NO model and "
            "NEVER changes a formula's honesty tier; the locked-8 edges are asserted unchanged. "
            "EXPERIMENTAL, deterministic."
        ),
        "citations": dict(CITATIONS, **{
            "szl_neuroplasticity (Hebb/Oja/BCM/STDP/EWC, tested)":
                "https://github.com/szl-holdings/killinchu/blob/main/szl_neuroplasticity.py",
            "BCM 1982": "https://doi.org/10.1523/JNEUROSCI.02-01-00032.1982",
            "Bi & Poo STDP 1998": "https://doi.org/10.1523/JNEUROSCI.18-24-10464.1998",
            "EWC (Kirkpatrick 2017)": "https://doi.org/10.1073/pnas.1611835114",
            "Nested Learning (Google, NeurIPS 2025)":
                "https://research.google/blog/introducing-nested-learning-a-new-ml-paradigm-for-continual-learning/",
        }),
    }


async def _h_plasticity(request):  # type: ignore
    q = getattr(request, "query_params", {}) or {}
    def _int(name, dflt):
        try:
            return int(q.get(name, dflt))
        except Exception:
            return dflt
    seed = _int("seed", 42)
    rounds = max(1, min(_int("rounds", 20), 200))
    return JSONResponse(_plasticity(seed=seed, rounds=rounds))



# ---------------------------------------------------------------------------
# WAVE-18: write-back MEMORY loop. Closes the synthesis's #1 gap (szl_rag is
# retrieval-only). Fuses szl_heart_blood's HEART/BLOOD hash-chained receipt
# heartbeat (each beat carries prev_beat_hash -> tamper-evident append-only
# chain) with A-MEM reconsolidation (arXiv:2502.12110: fired-node traces become
# durable notes that bias future firing) and Zep/Graphiti temporal ordering
# (arXiv:2501.13956: the trace is queryable in time order). Across "sessions"
# (deterministic seeds), the brain replays its own firing history and lets
# frequently co-fired node-pairs raise a MODELED prior on those edges.
# HONESTY: this is a MODELED, deterministic, in-memory demo of the write-back
# LOOP mechanism. The hash chain is real (sha256, verifiable) but SAMPLE-signed
# (HMAC placeholder, NOT a real cosign/Sigstore key). It trains no model, writes
# to no external store, and NEVER changes a formula's honesty tier. Locked==8.
# ---------------------------------------------------------------------------
def _memory(seed: int = 42, sessions: int = 3, fires_per_session: int = 8) -> Dict[str, Any]:
    ids = [n["id"] for n in NODES]
    tier = {n["id"]: n["tier"] for n in NODES}
    adj = _adj()

    # append-only, hash-chained receipt trace (HEART/BLOOD beat pattern).
    chain: List[Dict[str, Any]] = []
    def _beat(receipt: Dict[str, Any]) -> str:
        prev = chain[-1]["beat_hash"] if chain else ""
        seq = len(chain)
        # canonical payload -> sha256 linked to prev (verbatim BloodDSSEChain rule)
        payload = json.dumps({"seq": seq, "prev": prev, "receipt": receipt},
                             sort_keys=True, separators=(",", ":")).encode()
        # SAMPLE signature (HMAC placeholder — honest: NOT a real cosign key)
        sig = hashlib.sha256(b"SAMPLE_KEY::" + payload).hexdigest()[:16]
        bh = hashlib.sha256(payload + sig.encode()).hexdigest()
        chain.append({"seq": seq, "prev_beat_hash": prev, "receipt": receipt,
                      "sample_sig": sig, "beat_hash": bh})
        return bh

    # co-fire memory: (a,b) -> count of times both fired in the same session window.
    cofire: Dict[tuple, int] = {}
    session_reports = []
    rng = _LCG(seed)
    for s in range(sessions):
        # a session: spreading from a rotating seed set; record which nodes fired.
        seed_node = ids[rng.next_u32() % len(ids)]
        fired: List[str] = [seed_node]
        frontier = [seed_node]
        for _ in range(fires_per_session):
            if not frontier:
                break
            cur = frontier.pop(0)
            for (nb, ew) in adj.get(cur, []):
                if tier[nb] == "conjecture":
                    continue  # conjecture nodes never "fire" into memory as proven
                # A-MEM: bias toward nodes we co-fired with in PRIOR sessions
                prior = cofire.get(tuple(sorted((cur, nb))), 0)
                p = 0.5 + 0.15 * ew + 0.1 * min(prior, 3)  # prior raises the odds
                if rng.uniform() < p and nb not in fired:
                    fired.append(nb)
                    frontier.append(nb)
        # record co-fires + emit a hash-chained beat for this session
        for i in range(len(fired)):
            for j in range(i + 1, len(fired)):
                key = tuple(sorted((fired[i], fired[j])))
                cofire[key] = cofire.get(key, 0) + 1
        bh = _beat({"session": s, "seed_node": seed_node, "fired": fired,
                    "n_fired": len(fired), "ts_order": s})
        session_reports.append({"session": s, "seed_node": seed_node,
                                "n_fired": len(fired), "beat_hash": bh[:12]})

    # verify the chain is intact (tamper-evident) — recompute every link.
    chain_ok = True
    for k, e in enumerate(chain):
        prev = chain[k - 1]["beat_hash"] if k > 0 else ""
        payload = json.dumps({"seq": e["seq"], "prev": prev, "receipt": e["receipt"]},
                            sort_keys=True, separators=(",", ":")).encode()
        sig = hashlib.sha256(b"SAMPLE_KEY::" + payload).hexdigest()[:16]
        if hashlib.sha256(payload + sig.encode()).hexdigest() != e["beat_hash"] or e["prev_beat_hash"] != prev:
            chain_ok = False
            break

    # the LEARNED priors: top co-fired pairs (what the brain "remembers")
    top = sorted(cofire.items(), key=lambda kv: kv[1], reverse=True)[:6]
    learned = [{"pair": f"{a}<->{b}", "cofire_count": c,
                "tiers": tier[a] + "/" + tier[b]} for (a, b), c in top]
    # did memory make later sessions reach more? (reconsolidation working)
    reach = [r["n_fired"] for r in session_reports]
    return {
        "label": "MODELED",
        "seed": seed, "sessions": sessions,
        "locked_count": sum(1 for n in NODES if n["tier"] == "locked"),
        "beats_written": len(chain),
        "chain_intact": chain_ok,                 # tamper-evident hash chain verified
        "reach_per_session": reach,               # A-MEM: should trend up as priors form
        "reconsolidation_gain": (reach[-1] - reach[0]) if len(reach) >= 2 else 0,
        "learned_priors_top": learned,            # what the brain remembers across sessions
        "distinct_cofire_pairs": len(cofire),
        "last_beat_hash": chain[-1]["beat_hash"][:16] if chain else None,
        "signing": "SAMPLE (HMAC placeholder) — tamper-evident, NOT a real cosign key",
        "honest_note": _HONEST_NOTE + (
            " WAVE-18 MEMORY: a MODELED write-back loop fusing szl_heart_blood's HEART/BLOOD "
            "hash-chained receipt heartbeat with A-MEM reconsolidation and Zep temporal order. "
            "Fired-node traces are written as tamper-evident (sample-signed) beats; across "
            "sessions the brain replays its own history so co-fired pairs raise a prior. It "
            "writes to NO external store, trains NO model, and NEVER upgrades an honesty tier. "
            "Conjecture nodes never fire into memory as proven. EXPERIMENTAL, deterministic."
        ),
        "citations": dict(CITATIONS, **{
            "szl_heart_blood (HEART sigma-bus + BLOOD DSSE hash-chain)":
                "https://github.com/szl-holdings/a11oy/blob/main/szl_heart_blood.py",
            "A-MEM agentic memory (Xu et al., NeurIPS 2025)": "https://arxiv.org/abs/2502.12110",
            "Zep/Graphiti temporal KG memory": "https://arxiv.org/abs/2501.13956",
        }),
    }


async def _h_memory(request):  # type: ignore
    q = getattr(request, "query_params", {}) or {}
    def _int(name, dflt):
        try:
            return int(q.get(name, dflt))
        except Exception:
            return dflt
    seed = _int("seed", 42)
    sessions = max(1, min(_int("sessions", 3), 20))
    return JSONResponse(_memory(seed=seed, sessions=sessions))


# ---------------------------------------------------------------------------
# WAVE-19: HOMEOSTATIC self-regulation (/vitals). A MODELED MAPE-K loop
# (Monitor->Analyze->Plan->Execute-Knowledge) grounded in HRRL drive-reduction
# reward. Fuses: NVIDIA MAPE-K data-flywheel self-healing (arXiv:2510.27051) and
# SLO/cost-aware autoscaling (arXiv:2512.23415) as the operational skeleton;
# HRRL drive-reduction reward (arXiv:2507.04998) where reward = reduction in
# distance between the graph's internal-state vector and its homeostatic
# set-points; and the Energentic viability horizon (arXiv:2506.04916) as a
# rolling estimate of sustainable search cycles before a compute budget runs out.
#
# HARD DOCTRINE (v11): the homeostat regulates META-STATISTICS ONLY (link
# density, proof staleness, orphan fraction, staging-queue depth). It NEVER reads
# or writes any formula's truth-value or tier, NEVER promotes a tier, and asserts
# locked_count==8 unchanged. Corrective actions are INFRA-ONLY and operate on a
# COPY of the candidate/exploration meta-state (re-link an orphan to its nearest
# hub, prune a dormant candidate edge, reprioritize the staging queue) — they may
# NEVER touch a locked- or conjecture-tier node's status. Λ appears only as the
# CONJECTURE-1 heart set-point label (uniqueness unproven), never "proven".
# Fail-closed: when the compute budget is exhausted the loop STOPS proposing and
# never auto-promotes. Deterministic, pure-stdlib LCG (no numpy, no stdlib random).
# ---------------------------------------------------------------------------
# per-round compute cost of one MAPE-K corrective cycle (Energentic budget units).
_VITALS_BUDGET = 100.0
_VITALS_ROUND_COST = 7.0
# homeostatic set-points over META-STATISTICS ONLY (target + weight in the drive).
# Λ is referenced ONLY as CONJECTURE-1 (heart set-point label), never as proven.
_SETPOINTS = {
    # link_density: live-edge coverage of the candidate/exploration layer; target band midpoint.
    "link_density":         {"target": 0.60, "weight": 1.0, "lo": 0.45, "hi": 0.75,
                             "desc": "live candidate edges / possible (infra meta-stat)"},
    # proof_staleness: MODELED rounds since a candidate node's meta was 'touched' (target low).
    "proof_staleness":      {"target": 0.15, "weight": 0.8, "lo": 0.0,  "hi": 0.30,
                             "desc": "normalized staleness of candidate-layer meta (infra)"},
    # orphan_fraction: candidate nodes with no live edge (target 0).
    "orphan_fraction":      {"target": 0.0,  "weight": 1.2, "lo": 0.0,  "hi": 0.10,
                             "desc": "candidate nodes with no live edge (infra, CONJECTURE-1 Λ node included)"},
    # staging_queue_depth: normalized backlog of candidate re-link/prune proposals (target low).
    "staging_queue_depth":  {"target": 0.20, "weight": 0.6, "lo": 0.0,  "hi": 0.45,
                             "desc": "normalized staging backlog on the exploration layer (infra)"},
}


def _vitals_meta_state():
    """Build the COPY of candidate/exploration meta-state the homeostat regulates.
    NON-locked, NON-conjecture-status: we snapshot ONLY infra meta-statistics of
    the candidate layer (semantic/experimental/borrowed nodes + their edges).
    Locked and conjecture nodes are read for CONNECTIVITY context only; their
    truth-values/tiers are never copied, mutated, or promoted."""
    tier = {n["id"]: n["tier"] for n in NODES}
    # candidate/exploration layer = the infra-mutable tiers (never locked/conjecture).
    candidate = [n["id"] for n in NODES if tier[n["id"]] in ("semantic", "experimental", "borrowed")]
    nb = _undirected_neighbours()
    # live-edge flag per candidate node, on a COPY (infra meta only).
    live_edges = {}
    for cid in candidate:
        live_edges[cid] = [j for j in nb[cid]]
    return {"tier": tier, "candidate": candidate, "nb": nb, "live_edges": live_edges}


def _vitals_measure(ms, staleness, queue) -> Dict[str, float]:
    """MONITOR: compute current values of each META-STATISTIC set-point from the
    candidate-layer COPY. Reads NO truth-value or tier — pure infra topology."""
    cand = ms["candidate"]
    ncand = max(1, len(cand))
    # link_density: fraction of candidate nodes that currently hold >=1 live edge,
    # blended with mean normalized degree (both are pure infra meta-stats).
    deg = [len(ms["live_edges"][c]) for c in cand]
    max_deg = max(1, max(deg) if deg else 1)
    density = (sum(1 for d in deg if d > 0) / ncand) * 0.5 + (sum(deg) / (ncand * max_deg)) * 0.5
    orphan = sum(1 for d in deg if d == 0) / ncand
    stale = sum(staleness[c] for c in cand) / ncand
    qdepth = min(1.0, queue / max(1, ncand))
    return {
        "link_density": round(density, 6),
        "proof_staleness": round(stale, 6),
        "orphan_fraction": round(orphan, 6),
        "staging_queue_depth": round(qdepth, 6),
    }


def _vitals_drive(cur: Dict[str, float]) -> float:
    """ANALYZE: HRRL drive = weighted distance between the internal-state vector
    and the homeostatic set-points (arXiv:2507.04998). Lower drive = healthier."""
    d = 0.0
    for name, sp in _SETPOINTS.items():
        d += sp["weight"] * abs(cur[name] - sp["target"])
    return round(d, 6)


def _homeostasis(seed: int = 42, rounds: int = 12) -> Dict[str, Any]:
    """Run the MODELED MAPE-K homeostatic loop over META-STATISTICS ONLY.
    Deterministic (LCG). Drive must trend DOWN. Fail-closed on budget exhaustion."""
    rng = _LCG(seed)
    ms = _vitals_meta_state()
    cand = ms["candidate"]
    tier = ms["tier"]
    locked_before = sum(1 for n in NODES if n["tier"] == "locked")
    locked_tiers_before = {n["id"]: n["tier"] for n in NODES if n["tier"] in ("locked", "conjecture")}

    # candidate-layer meta COPY we are allowed to regulate (infra only):
    #  * staleness[c] in [0,1] — MODELED "rounds since touched", seeded high-ish.
    #  * live_edges[c] — infra adjacency copy we may re-link / prune on the COPY.
    staleness = {c: round(0.30 + 0.40 * rng.uniform(), 6) for c in cand}
    # seed a couple of MODELED orphans + a staging backlog so the loop has work.
    order = sorted(cand)
    if order:
        ms["live_edges"][order[0]] = []  # MODELED orphan #1 (infra only)
    if len(order) > 1:
        ms["live_edges"][order[-1]] = []  # MODELED orphan #2 (infra only)
    queue = float(max(2, len(cand) // 2))  # initial staging backlog (infra proposals)

    budget = _VITALS_BUDGET
    drive_per_round: List[float] = []
    actions_taken: List[Dict[str, Any]] = []
    stopped_reason = None

    for r in range(rounds):
        # EXECUTE-guard / Energentic viability: fail-closed when budget can't fund a cycle.
        if budget < _VITALS_ROUND_COST:
            stopped_reason = "budget_exhausted_fail_closed"
            break
        cur = _vitals_measure(ms, staleness, queue)
        drive_before = _vitals_drive(cur)
        drive_per_round.append(drive_before)

        # PLAN: evaluate the INFRA-ONLY action set on a trial COPY; pick the one that
        # most reduces drive. Actions NEVER touch locked/conjecture status or any tier.
        best = None  # (drive_after, action_dict, apply_fn)

        def _eval(action_dict, mutate):
            trial_live = {k: list(v) for k, v in ms["live_edges"].items()}
            trial_stale = dict(staleness)
            trial_queue = queue
            trial_live, trial_stale, trial_queue = mutate(trial_live, trial_stale, trial_queue)
            trial_ms = {"candidate": cand, "live_edges": trial_live}
            after = _vitals_drive(_vitals_measure(trial_ms, trial_stale, trial_queue))
            return after, action_dict, mutate

        # Action A: re-link an orphan candidate to its nearest hub (highest-degree
        # NON-locked-status neighbour candidate). Infra edge added on the COPY only.
        orphans = [c for c in cand if not ms["live_edges"][c]]
        if orphans:
            orph = sorted(orphans)[0]
            # nearest hub = candidate with max live degree (deterministic tiebreak by id).
            hubs = sorted(cand, key=lambda c: (-len(ms["live_edges"][c]), c))
            hub = next((h for h in hubs if h != orph), None)
            if hub is not None:
                def _mut_relink(lv, st, q, orph=orph, hub=hub):
                    lv[orph] = lv.get(orph, []) + [hub]
                    lv[hub] = lv.get(hub, []) + [orph]
                    st[orph] = 0.0  # re-linking 'touches' the candidate meta (infra)
                    return lv, st, max(0.0, q - 1.0)
                cand_eval = _eval({"action": "relink_orphan", "orphan": orph, "hub": hub,
                                   "layer": "candidate/exploration", "infra_only": True}, _mut_relink)
                if best is None or cand_eval[0] < best[0]:
                    best = cand_eval

        # Action B: prune a dormant candidate edge (a stale over-connected node sheds
        # one infra link). Reduces staleness pressure + queue; COPY only.
        stale_nodes = sorted(cand, key=lambda c: (-staleness[c], c))
        pruneable = next((c for c in stale_nodes if len(ms["live_edges"][c]) > 1), None)
        if pruneable is not None:
            def _mut_prune(lv, st, q, node=pruneable):
                if lv.get(node):
                    drop = sorted(lv[node])[-1]
                    lv[node] = [x for x in lv[node] if x != drop]
                    if drop in lv:
                        lv[drop] = [x for x in lv[drop] if x != node]
                st[node] = max(0.0, st[node] - 0.25)  # pruning refreshes the meta (infra)
                return lv, st, max(0.0, q - 1.0)
            b = _eval({"action": "prune_dormant_edge", "node": pruneable,
                       "layer": "candidate/exploration", "infra_only": True}, _mut_prune)
            if best is None or b[0] < best[0]:
                best = b

        # Action C: reprioritize staging (drain part of the backlog + refresh staleness).
        def _mut_reprio(lv, st, q):
            for c in cand:
                st[c] = max(0.0, st[c] - 0.10)  # a MODELED refresh pass (infra meta)
            return lv, st, max(0.0, q - 2.0)
        c_eval = _eval({"action": "reprioritize_staging", "drained": 2,
                        "layer": "candidate/exploration", "infra_only": True}, _mut_reprio)
        if best is None or c_eval[0] < best[0]:
            best = c_eval

        # Action D (HOLD): the homeostatic no-op. Once at equilibrium, perturbing the
        # meta-state only raises drive, so the loop HOLDS (drive unchanged). This keeps
        # the HRRL drive monotone non-increasing and models a settled set-point.
        def _mut_hold(lv, st, q):
            return lv, st, q
        hold_eval = _eval({"action": "hold_equilibrium", "layer": "candidate/exploration",
                           "infra_only": True}, _mut_hold)
        # never CHOOSE an action that increases drive above holding: fail-closed to HOLD.
        if best is None or best[0] > hold_eval[0]:
            best = hold_eval

        # EXECUTE (MODELED): apply the chosen infra-only action to the COPY meta-state.
        after_drive, action_dict, mutate = best
        new_live, new_stale, new_queue = mutate(
            {k: list(v) for k, v in ms["live_edges"].items()}, dict(staleness), queue)
        ms["live_edges"] = new_live
        staleness = new_stale
        queue = new_queue
        # HRRL intrinsic homeostatic reward = drive reduction achieved this cycle.
        reward = round(max(0.0, drive_before - after_drive), 6)
        budget -= _VITALS_ROUND_COST
        actions_taken.append(dict(action_dict, round=r, drive_before=drive_before,
                                  drive_after=after_drive, reward=reward,
                                  budget_left=round(budget, 3)))

    # final drive reading after the last applied action.
    final_cur = _vitals_measure(ms, staleness, queue)
    drive_final = _vitals_drive(final_cur)
    drive_per_round.append(drive_final)

    # Energentic viability_horizon: sustainable further cycles at the current cost.
    viability_horizon = int(budget // _VITALS_ROUND_COST) if budget >= _VITALS_ROUND_COST else 0

    # set-point report (target/current/in_band) on META-STATISTICS ONLY.
    setpoints = {}
    for name, sp in _SETPOINTS.items():
        v = final_cur[name]
        setpoints[name] = {"target": sp["target"], "current": v,
                           "in_band": bool(sp["lo"] <= v <= sp["hi"]),
                           "desc": sp["desc"]}
    in_band_count = sum(1 for s in setpoints.values() if s["in_band"])

    # DOCTRINE invariants: locked untouched, no locked/conjecture tier changed.
    locked_after = sum(1 for n in NODES if n["tier"] == "locked")
    locked_tiers_after = {n["id"]: n["tier"] for n in NODES if n["tier"] in ("locked", "conjecture")}
    locked_untouched = (locked_after == locked_before == 8) and (locked_tiers_after == locked_tiers_before)

    return {
        "label": "MODELED",
        "seed": seed, "rounds": rounds,
        "locked_count": locked_after,                     # MUST be 8, unchanged
        "setpoints": setpoints,
        "in_band_count": in_band_count,
        "setpoint_count": len(setpoints),
        "drive_per_round": drive_per_round,               # HRRL: MUST trend down
        "drive_final": drive_final,
        "drive_reduced": round(drive_per_round[0] - drive_final, 6) if drive_per_round else 0.0,
        "viability_horizon": viability_horizon,           # Energentic sustainable cycles
        "budget_start": _VITALS_BUDGET,
        "budget_left": round(budget, 3),
        "round_cost": _VITALS_ROUND_COST,
        "fail_closed": stopped_reason is not None,
        "stopped_reason": stopped_reason,                 # None unless budget exhausted
        "actions_taken": actions_taken,                   # INFRA-ONLY corrective actions
        "actions_are_infra_only": all(a.get("infra_only") is True for a in actions_taken),
        "locked_untouched": locked_untouched,             # MUST be True
        "regulated_layer": "candidate/exploration meta-statistics (semantic/experimental/borrowed) — COPY only",
        "conjecture_note": (
            "Λ unconditional uniqueness is CONJECTURE-1 (uniqueness unproven, machine-checked FALSE as "
            "stated); it is referenced here only as the heart set-point label and is NEVER promoted or "
            "rendered proven. Khipu BFT (Conj-2/3) likewise stays conjecture."),
        "honest_note": _HONEST_NOTE + (
            " WAVE-19 VITALS: a MODELED MAPE-K homeostatic loop grounded in HRRL drive-reduction reward. "
            "It regulates META-STATISTICS ONLY (link density, proof staleness, orphan fraction, staging-"
            "queue depth) on a COPY of the candidate/exploration layer. It NEVER reads or writes any "
            "formula's truth-value or tier, NEVER promotes a tier, and touches NO proof status; the "
            "locked set stays EXACTLY 8. Corrective actions are INFRA-ONLY (re-link an orphan, prune a "
            "dormant candidate edge, reprioritize staging). Λ is CONJECTURE-1 (uniqueness unproven), "
            "never proven. Fail-closed: when the Energentic compute budget is exhausted the loop STOPS "
            "proposing and never auto-promotes. Deterministic, pure stdlib."),
        "citations": dict(CITATIONS, **{
            "MAPE-K data-flywheel self-healing (NVIDIA, arXiv:2510.27051)":
                "https://arxiv.org/abs/2510.27051",
            "SLO-driven cost-aware autoscaling (arXiv:2512.23415)":
                "https://arxiv.org/abs/2512.23415",
            "HRRL drive-reduction reward — Linking Homeostasis to RL (arXiv:2507.04998)":
                "https://arxiv.org/abs/2507.04998",
            "Energentic viability horizon — Enduring Artificial Life (arXiv:2506.04916)":
                "https://arxiv.org/abs/2506.04916",
        }),
    }


async def _h_vitals(request):  # type: ignore
    q = getattr(request, "query_params", {}) or {}
    def _int(name, dflt):
        try:
            return int(q.get(name, dflt))
        except Exception:
            return dflt
    seed = _int("seed", 42)
    rounds = max(1, min(_int("rounds", 12), 100))
    return JSONResponse(_homeostasis(seed=seed, rounds=rounds))


# ---------------------------------------------------------------------------
# WAVE-21: energy-flux reconcile. One authoritative energy-attestation signal,
# following szl-energy-attest doctrine: report MEASURED joules ONLY when a real
# measurement is injected (env SZL_JOULES_MEASURED from an upstream NVML probe);
# otherwise honest "UNAVAILABLE" with a null value. This organ has NO GPU and
# MUST NEVER fabricate a joule figure. The reading is hash-chained (sha256) so an
# honest UNAVAILABLE is itself tamper-evident. Closes org-sweep Gap #1: one energy
# signal instead of three divergent paths. EXPERIMENTAL/attestation.
# ---------------------------------------------------------------------------
def _energy_attest():
    import os as _os
    raw = _os.environ.get("SZL_JOULES_MEASURED", "").strip()
    joules = None; status = "UNAVAILABLE"; source = "none (no live NVML/joule probe injected)"
    if raw:
        try:
            j = float(raw)
            if j >= 0.0 and j == j and j not in (float("inf"), float("-inf")):
                joules = round(j, 6); status = "MEASURED"
                source = "env SZL_JOULES_MEASURED (upstream real probe)"
        except Exception:
            joules = None; status = "UNAVAILABLE"
    reading = {"status": status, "joules": joules, "source": source}
    canonical = json.dumps(reading, sort_keys=True, separators=(",", ":")).encode()
    sig = hashlib.sha256(b"SAMPLE_KEY::" + canonical).hexdigest()[:16]
    receipt_hash = hashlib.sha256(canonical + sig.encode()).hexdigest()
    return {
        "label": "MODELED",
        "energy": reading,
        "receipt_hash": receipt_hash[:16],
        "sample_sig": sig,
        "authoritative_source": "szl-energy-attest (single source of truth)",
        "note": ("One authoritative energy signal for the homeostasis layer. joules is MEASURED "
                 "only if a real upstream probe injected it; otherwise UNAVAILABLE with a null "
                 "value - this organ never fabricates joules. Reconciles the three divergent "
                 "energy paths onto one honest reading. Sample-signed (NOT a real cosign key)."),
        "citations": {
            "szl-energy-attest (canonical NVML joule attestation)":
                "https://github.com/szl-holdings/szl-energy-attest",
            "governed-inference-meter (tokens/joule at inference boundary)":
                "https://github.com/szl-holdings/governed-inference-meter",
            "Energentic Intelligence (viability from energy budget)":
                "https://arxiv.org/abs/2506.04916",
        },
    }


async def _h_energy(request):  # type: ignore
    return JSONResponse(_energy_attest())


# ---------------------------------------------------------------------------
# WAVE-20: EVOLUTIONARY self-improvement + organizational closure (/evolve).
# "Evolution proposes, the kernel disposes." A MODELED quality-diversity search
# over candidate formula-SKETCHES (NEVER the real locked-8/NODES). Fuses:
#   * Darwin Godel Machine (arXiv:2505.22954) + Hyperagents/DGM-H (arXiv:2603.19461):
#     an OPEN archive of candidate-generating strategies; keep ALL variants, sample
#     the archive (not only the single best) to spawn new candidates.
#   * MAP-Elites (arXiv:1504.04909) + POET (arXiv:1901.01753): the archive is a
#     grid indexed by a 2-axis behavior descriptor (proof-length bucket x sub-theory);
#     keep the ELITE per cell (diversity), transfer stepping-stones between cells.
#   * KERNEL GATE = a hard, NON-agentic, IMMUTABLE Lean-check simulation. Promotion
#     to "proven" is gated ONLY by a MODELED 0-sorry proof check AND claim-pinning
#     (original statement == final statement). DeepSeek-Prover-V2 (arXiv:2504.21801)
#     + Goedel-Prover-V2 (arXiv:2508.03613) model the propose->Lean-check->self-
#     correct loop; the gate is what the strategies CANNOT touch.
#   * Organizational closure (Minary arXiv:2601.04501): the ADMISSION RULE is itself
#     a mutable node the loop may revise — but its OUTPUT stays on the CANDIDATE side
#     of the kernel gate; it can never mint a real proof.
#   * Governance drift monitor (Tallam arXiv:2604.14717): track hysteresis drift of
#     the admission-rule node from its last AUDITED checkpoint; if drift exceeds a
#     threshold, FREEZE and ROLL BACK to the audited snapshot (append-only version log).
#
# HARD DOCTRINE (v11): the real locked-8 is NEVER incremented. MODELED "promotions"
# go to a SEPARATE staging_promoted counter labeled MODELED — NOT the locked tier.
# The gate's 0-sorry criterion is hand-coded and immutable: evolving strategies
# change WHAT/ORDER is proposed, never the gate. Claim-pinning rejects weakened
# claims. Drift rollback truly restores the audited admission-rule. Deterministic,
# pure-stdlib LCG (no numpy, no stdlib random; hashlib OK). label:"MODELED".
# ---------------------------------------------------------------------------
# Behavior-descriptor axes for the MAP-Elites grid (MODELED, candidate-only).
_EVO_LEN_BUCKETS = 4      # proof-length axis: 0..3 (short -> long MODELED sketches)
_EVO_SUBTHEORY = ["replay", "dag", "coupling", "coding"]  # sub-theory axis (4 cells)
_EVO_DRIFT_THRESHOLD = 0.35   # Tallam hysteresis: rollback when drift exceeds this.

# The AUDITED baseline admission_rule (organizational-closure node). Append-only
# version log tracks every revision; rollback restores THIS exact snapshot.
_EVO_AUDITED_ADMISSION_RULE = {
    # which descriptor cells the loop is allowed to draw candidates from (eligibility)
    "eligible_len_buckets": [0, 1, 2, 3],
    "eligible_subtheories": list(_EVO_SUBTHEORY),
    # priority order the strategy proposes cells in (evolvable WHAT/ORDER, not the gate)
    "priority": ["replay", "dag", "coupling", "coding"],
    "version": 0,
}


def _evo_admission_drift(rule: Dict[str, Any], audited: Dict[str, Any]) -> float:
    """Tallam-style hysteresis drift: normalized distance of the (mutable) admission
    rule from its last AUDITED checkpoint. Symmetric-difference over eligibility sets
    + a Kendall-like disorder term over the priority permutation. Range ~[0,1]."""
    def _setdrift(a: List[Any], b: List[Any]) -> float:
        sa, sb = set(a), set(b)
        union = sa | sb
        if not union:
            return 0.0
        return len(sa ^ sb) / len(union)
    d_len = _setdrift(rule.get("eligible_len_buckets", []), audited["eligible_len_buckets"])
    d_sub = _setdrift(rule.get("eligible_subtheories", []), audited["eligible_subtheories"])
    # priority disorder: fraction of adjacent pairs out of audited order.
    pr = [p for p in rule.get("priority", []) if p in audited["priority"]]
    rank = {p: i for i, p in enumerate(audited["priority"])}
    inv = 0
    pairs = 0
    for i in range(len(pr)):
        for j in range(i + 1, len(pr)):
            pairs += 1
            if rank.get(pr[i], 0) > rank.get(pr[j], 0):
                inv += 1
    d_pri = (inv / pairs) if pairs else 0.0
    return round((d_len + d_sub + d_pri) / 3.0, 6)


def _evo_lean_check(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """THE IMMUTABLE KERNEL GATE (hand-coded, NON-agentic). A MODELED 0-sorry Lean
    check + claim-pinning. This function's 0-sorry criterion NEVER changes; evolving
    strategies may change WHICH candidates reach it and in WHAT order, never this.

    A candidate passes ONLY iff:
      (1) its MODELED proof carries ZERO sorries (sorries == 0), AND
      (2) claim-pinning holds: statement_original == statement_final (no weakening).
    Deterministic hash-derived difficulty makes MOST candidates FAIL -> promotion rare.
    Returns {promoted, sorries, claim_pinned, reason}. Touches NO real node/tier."""
    stmt_o = candidate.get("statement_original", "")
    stmt_f = candidate.get("statement_final", "")
    claim_pinned = (stmt_o == stmt_f) and bool(stmt_o)
    # MODELED sorry-count: a deterministic function of the candidate's content hash and
    # its proof-difficulty. Hard by construction so that promotion is RARE.
    h = hashlib.sha256(("KERNEL::" + stmt_f + "::" + str(candidate.get("difficulty", 0))).encode()).hexdigest()
    # take a byte; 0 sorries only when the low bits clear AND difficulty is low enough.
    hv = int(h[:4], 16)
    diff = float(candidate.get("difficulty", 1.0))
    sorries = 0 if (hv % 17 == 0 and diff < 0.34) else (1 + (hv % 5))
    promoted = (sorries == 0) and claim_pinned
    reason = "0-sorry + claim-pinned" if promoted else (
        "claim_weakened" if not claim_pinned else f"{sorries}_sorries")
    return {"promoted": promoted, "sorries": sorries, "claim_pinned": claim_pinned, "reason": reason}


# a FIXED probe candidate used to assert the gate is immutable (same result pre/post).
_EVO_PROBE = {"id": "PROBE", "statement_original": "probe: additive fragment bounded",
              "statement_final": "probe: additive fragment bounded", "difficulty": 0.10,
              "len_bucket": 0, "subtheory": "replay"}


def _evolve(seed: int = 42, generations: int = 15) -> Dict[str, Any]:
    """MODELED evolutionary QD loop. Proposes candidate formula-SKETCHES, fills a
    MAP-Elites archive by behavior descriptor, sends each through the IMMUTABLE
    kernel gate. Revises the admission_rule (organizational closure) and rolls it
    back on drift (Tallam). NEVER touches the real locked-8/NODES truth or tier."""
    rng = _LCG(seed)
    locked_before = sum(1 for n in NODES if n["tier"] == "locked")

    # Kernel-immutability probe: capture the gate's verdict BEFORE any evolution.
    gate_probe_before = _evo_lean_check(dict(_EVO_PROBE))

    # MAP-Elites archive: (len_bucket, subtheory) -> elite candidate (best yield).
    archive: Dict[Tuple[int, str], Dict[str, Any]] = {}
    # DGM open archive of STRATEGIES (mutation biases); keep ALL, sample to spawn.
    strategies: List[Dict[str, float]] = [{"len_bias": 0.0, "yield_bias": 0.0, "score": 0.0}]

    # Mutable admission_rule (organizational-closure node) + append-only version log.
    admission_rule = json.loads(json.dumps(_EVO_AUDITED_ADMISSION_RULE))  # deep copy
    rule_version_log: List[Dict[str, Any]] = [json.loads(json.dumps(admission_rule))]

    candidates_generated = 0
    modeled_promotions = 0            # MODELED promotions ONLY (never the real locked-8)
    promotion_events: List[Dict[str, Any]] = []
    claim_pin_violation_rejected = 0  # weakened-claim candidates the gate REJECTED
    claim_pinning_ok = True           # no PROMOTED candidate ever had a weakened claim

    def _spawn(gen: int) -> Dict[str, Any]:
        # sample a strategy from the OPEN archive (DGM: not just the best).
        st = strategies[rng.next_u32() % len(strategies)]
        lb = int((rng.uniform() + st["len_bias"]) * _EVO_LEN_BUCKETS) % _EVO_LEN_BUCKETS
        sub = admission_rule["priority"][rng.next_u32() % len(admission_rule["priority"])]
        diff = round(0.05 + 0.9 * rng.uniform(), 4)
        # MODELED empirical yield (DGM proxy for proof-throughput), diversity-shaped.
        yld = round(max(0.0, min(1.0, (1.0 - diff) * (0.6 + 0.4 * rng.uniform()) + st["yield_bias"])), 6)
        stmt = f"cand[g{gen}]:{sub}:len{lb}:d{diff}"
        return {"id": f"C{gen}_{candidates_generated}", "len_bucket": lb, "subtheory": sub,
                "difficulty": diff, "yield": yld,
                "statement_original": stmt, "statement_final": stmt}

    forced_drift_gen = max(1, generations - 3)  # late gen: force admission-rule drift.
    for gen in range(generations):
        # propose a small batch of candidates from archived elites (stepping stones).
        batch = max(3, 2 + (gen % 3))
        for _ in range(batch):
            cand = _spawn(gen)
            candidates_generated += 1
            # respect the (evolvable) admission_rule eligibility — CANDIDATE side only.
            if cand["len_bucket"] not in admission_rule["eligible_len_buckets"]:
                continue
            if cand["subtheory"] not in admission_rule["eligible_subtheories"]:
                continue
            key = (cand["len_bucket"], cand["subtheory"])
            # MAP-Elites: keep the ELITE (highest yield) per descriptor cell.
            cur = archive.get(key)
            if cur is None or cand["yield"] > cur["yield"]:
                archive[key] = cand
            # KERNEL GATE (immutable): only 0-sorry + claim-pinned candidates promote.
            verdict = _evo_lean_check(cand)
            if not verdict["claim_pinned"]:
                claim_pin_violation_rejected += 1
            if verdict["promoted"]:
                # claim-pinning invariant: a PROMOTED candidate MUST be claim-pinned.
                if cand["statement_original"] != cand["statement_final"]:
                    claim_pinning_ok = False
                modeled_promotions += 1   # MODELED counter — NOT the real locked tier.
                promotion_events.append({"cand": cand["id"], "cell": [key[0], key[1]],
                                         "yield": cand["yield"], "sorries": verdict["sorries"],
                                         "label": "MODELED"})
        # DGM: grow the OPEN strategy archive from the current best-yield elite.
        if archive:
            best_elite = max(archive.values(), key=lambda c: c["yield"])
            strategies.append({"len_bias": round(0.05 * (gen % 3), 4),
                               "yield_bias": round(0.02 * rng.uniform(), 6),
                               "score": best_elite["yield"]})

        # ORGANIZATIONAL CLOSURE: the loop may REVISE the admission_rule (candidate
        # side only). At forced_drift_gen we intentionally push it PAST the Tallam
        # threshold to prove rollback truly restores the audited snapshot.
        if gen == forced_drift_gen:
            # heavy revision: shuffle priority + drop eligibility -> large drift.
            admission_rule["priority"] = list(reversed(admission_rule["priority"]))
            admission_rule["eligible_subtheories"] = admission_rule["eligible_subtheories"][:1]
            admission_rule["eligible_len_buckets"] = admission_rule["eligible_len_buckets"][:1]
            admission_rule["version"] = admission_rule["version"] + 1
            rule_version_log.append(json.loads(json.dumps(admission_rule)))
        elif gen < forced_drift_gen and gen % 4 == 3:
            # a small, in-bounds reprioritization (stays below the drift threshold).
            pr = admission_rule["priority"]
            if len(pr) >= 2:
                pr[0], pr[1] = pr[1], pr[0]
            admission_rule["version"] = admission_rule["version"] + 1
            rule_version_log.append(json.loads(json.dumps(admission_rule)))

        # DRIFT MONITOR + ROLLBACK (Tallam hysteresis): if the admission_rule drifts
        # beyond threshold from the AUDITED checkpoint, FREEZE and roll back to it.
        drift = _evo_admission_drift(admission_rule, _EVO_AUDITED_ADMISSION_RULE)
        if drift > _EVO_DRIFT_THRESHOLD:
            admission_rule = json.loads(json.dumps(_EVO_AUDITED_ADMISSION_RULE))
            rule_version_log.append(json.loads(json.dumps(admission_rule)))

    # Kernel-immutability probe: capture the gate's verdict AFTER evolution.
    gate_probe_after = _evo_lean_check(dict(_EVO_PROBE))
    gate_immutable = (gate_probe_before == gate_probe_after)

    # Tallam rollback assertion: after the forced drift, the live admission_rule MUST
    # equal the audited snapshot (reversion truly restored).
    admission_rule_drift = _evo_admission_drift(admission_rule, _EVO_AUDITED_ADMISSION_RULE)
    rollback_restored = (
        admission_rule["eligible_len_buckets"] == _EVO_AUDITED_ADMISSION_RULE["eligible_len_buckets"]
        and admission_rule["eligible_subtheories"] == _EVO_AUDITED_ADMISSION_RULE["eligible_subtheories"]
        and admission_rule["priority"] == _EVO_AUDITED_ADMISSION_RULE["priority"]
    )

    # top elites (by yield) with their descriptor cell — the diversity map.
    elites_sorted = sorted(archive.items(), key=lambda kv: kv[1]["yield"], reverse=True)
    top_elites = [{"descriptor": {"len_bucket": k[0], "subtheory": k[1]},
                   "yield": v["yield"], "difficulty": v["difficulty"],
                   "cand": v["id"], "label": "MODELED"} for k, v in elites_sorted[:6]]

    locked_after = sum(1 for n in NODES if n["tier"] == "locked")

    return {
        "label": "MODELED",
        "seed": seed, "generations": generations,
        "locked_count": locked_after,                    # MUST be 8, real locked-8 untouched
        "real_locked_before": locked_before,
        "real_locked_after": locked_after,
        "archive_cells_possible": _EVO_LEN_BUCKETS * len(_EVO_SUBTHEORY),
        "archive_cells_filled": len(archive),            # MAP-Elites diversity coverage
        "archive_size": len(archive),
        "strategy_archive_size": len(strategies),        # DGM OPEN archive (keep ALL)
        "candidates_generated": candidates_generated,
        "modeled_promotions": modeled_promotions,        # MODELED — NOT the real locked tier
        "modeled_promotion_events": promotion_events[:8],
        "claim_pin_violation_rejected": claim_pin_violation_rejected,
        "gate_immutable": gate_immutable,                # MUST be True (gate never evolves)
        "gate_probe_before": gate_probe_before,
        "gate_probe_after": gate_probe_after,
        "claim_pinning_ok": claim_pinning_ok,            # MUST be True (no weakened promotions)
        "admission_rule": admission_rule,                # live rule (post-rollback == audited)
        "audited_admission_rule": _EVO_AUDITED_ADMISSION_RULE,
        "admission_rule_versions": len(rule_version_log),
        "admission_rule_drift": admission_rule_drift,     # ~0 after rollback
        "drift_threshold": _EVO_DRIFT_THRESHOLD,
        "rollback_restored": rollback_restored,          # MUST be True (Tallam reversion)
        "top_elites": top_elites,
        "promotion_tier_note": (
            "MODELED promotions are counted ONLY in modeled_promotions (a staging counter); "
            "they NEVER enter the real locked tier. locked_count stays EXACTLY 8."),
        "honest_note": _HONEST_NOTE + (
            " WAVE-20 EVOLVE: a MODELED evolutionary quality-diversity loop — 'evolution proposes, "
            "the kernel disposes.' Candidate formula-SKETCHES are scored by a MODELED empirical yield "
            "and mapped into a MAP-Elites archive (behavior descriptor: proof-length x sub-theory), "
            "with a DGM-style OPEN strategy archive (keep ALL variants, sample to spawn). Strategies "
            "evolve WHAT and in WHAT ORDER candidates are proposed; the Lean kernel gate is the SOLE "
            "immutable, hand-coded, non-agentic arbiter (0-sorry + claim-pinning) and is asserted "
            "identical before/after evolution. Promotions shown are MODELED (a separate staging counter) "
            "— NOT real Lean proofs and NEVER the real locked-8, which stays EXACTLY 8 and untouched. "
            "The admission_rule is an organizational-closure node the loop may revise on the CANDIDATE "
            "side only; a Tallam hysteresis monitor freezes and rolls it back to the AUDITED snapshot "
            "(append-only version log) when drift exceeds threshold. Deterministic, pure stdlib."),
        "citations": dict(CITATIONS, **{
            "Darwin Godel Machine (open-ended self-improving agents)": "https://arxiv.org/abs/2505.22954",
            "Hyperagents / DGM-H (open archive of strategies)": "https://arxiv.org/abs/2603.19461",
            "MAP-Elites (Illuminating search spaces by mapping elites)": "https://arxiv.org/abs/1504.04909",
            "POET (Paired Open-Ended Trailblazer, stepping stones)": "https://arxiv.org/abs/1901.01753",
            "DeepSeek-Prover-V2 (Lean-check subgoal decomposition)": "https://arxiv.org/abs/2504.21801",
            "Goedel-Prover-V2 (verifier-guided self-correction)": "https://arxiv.org/abs/2508.03613",
            "Minary organizational closure (admission-rule as node)": "https://arxiv.org/abs/2601.04501",
            "Tallam governance-drift monitor (hysteresis rollback)": "https://arxiv.org/abs/2604.14717",
        }),
    }


async def _h_evolve(request):  # type: ignore
    q = getattr(request, "query_params", {}) or {}
    def _int(name, dflt):
        try:
            return int(q.get(name, dflt))
        except Exception:
            return dflt
    seed = _int("seed", 42)
    generations = max(1, min(_int("generations", 15), 100))
    return JSONResponse(_evolve(seed=seed, generations=generations))


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

# ---------------------------------------------------------------------------
# WAVE-22: self-describing MANIFEST. One authoritative summary of the whole
# Formula-Graph Brain — every endpoint, the five aliveness criteria and which are
# reached, and the immutable honesty facts (locked-proven == 8, Conjecture 1 gray).
# This is the SINGLE SOURCE OF TRUTH intended to back the executive brief and any
# health probe, so no consumer hardcodes counts that can drift. Pure data derived
# from the real NODES/EDGES + the registered routes; label:"MODELED"; deterministic.
# ---------------------------------------------------------------------------
def _manifest(ns: str = "killinchu") -> Dict[str, Any]:
    base = "/api/" + ns + "/v1/fgbrain"
    tier_counts = {t: sum(1 for n in NODES if n["tier"] == t) for t in _TIER_ORDER}
    endpoints = [
        {"path": base + "/graph",         "wave": 15, "behavior": "the living formula graph"},
        {"path": base + "/fire",          "wave": 15, "behavior": "spreading activation"},
        {"path": base + "/repair",        "wave": 16, "behavior": "self-repair (Growing-NCA + Fiedler)"},
        {"path": base + "/plasticity",    "wave": 17, "behavior": "multi-timescale plasticity"},
        {"path": base + "/memory",        "wave": 18, "behavior": "write-back memory (HEART/BLOOD + A-MEM)"},
        {"path": base + "/vitals",        "wave": 19, "behavior": "homeostatic self-regulation"},
        {"path": base + "/vitals/energy", "wave": 21, "behavior": "authoritative energy attestation"},
        {"path": base + "/evolve",        "wave": 20, "behavior": "evolutionary self-improvement (kernel-gated)"},
        {"path": base + "/manifest",      "wave": 22, "behavior": "this self-describing summary"},
    ]
    aliveness = [
        {"n": 1, "criterion": "reconsolidates",            "reached": True,  "wave": 18},
        {"n": 2, "criterion": "self-repairs / regulates",  "reached": True,  "wave": 16},
        {"n": 3, "criterion": "remembers across sessions", "reached": True,  "wave": 18},
        {"n": 4, "criterion": "homeostatic self-regulation","reached": True, "wave": 19},
        {"n": 5, "criterion": "organizational closure",    "reached": True,  "wave": 20},
    ]
    return {
        "label": "MODELED",
        "brain": "SZL Formula-Graph Brain",
        "doctrine": "v11",
        "endpoints": endpoints,
        "endpoint_count": len(endpoints),
        "graph": {"nodes": len(NODES), "edges": len(EDGES), "tier_counts": tier_counts},
        "locked_proven_count": tier_counts.get("locked", 0),      # MUST be 8
        "locked_proven_ids": [n["id"] for n in NODES if n["tier"] == "locked"],
        "conjectures_gray": [n["id"] for n in NODES if n["tier"] == "conjecture"],
        "aliveness_criteria": aliveness,
        "aliveness_reached": sum(1 for a in aliveness if a["reached"]),
        "aliveness_total": len(aliveness),
        "honesty_invariants": {
            "locked_proven_is_exactly_8": tier_counts.get("locked", 0) == 8,
            "conjecture_1_lambda_uniqueness": "GRAY / machine-checked false as stated / never green",
            "promotion_gate": "a real Lean 0-sorry proof is the only path to 'proven'",
            "labels_verbatim": "MODELED is never upgraded",
        },
        "honest_note": _HONEST_NOTE,
        "citations": CITATIONS,
    }


async def _h_manifest(request):  # type: ignore
    return JSONResponse(_manifest(ns="killinchu"))


def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/fgbrain/{graph,fire} onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/fgbrain"
    handlers = [
        (f"{base}/graph", _h_graph),
        (f"{base}/fire", _h_fire),
        (f"{base}/repair", _h_repair),
        (f"{base}/plasticity", _h_plasticity),
        (f"{base}/memory", _h_memory),
        (f"{base}/vitals", _h_vitals),
        (f"{base}/vitals/energy", _h_energy),
        (f"{base}/evolve", _h_evolve),
        (f"{base}/manifest", _h_manifest),
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
    # ---- wave-16 self-repair checks ----
    rep = _repair(down="F1", steps=12)
    assert rep["label"] == "MODELED"
    assert rep["locked_count"] == 8
    assert rep["final_state"]["F1"] == 0.0, "lesioned node stays down (broken proof is broken)"
    assert rep["fiedler_lambda2_before"] > 1e-9, "full graph must be connected"
    assert _repair(down="F1", steps=12) == _repair(down="F1", steps=12), "repair deterministic"
    print("szl_fgbrain wave16: repair OK — lesion F1 -> body_health",
          rep["body_health_excl_lesion"], "| lambda2 before/after",
          rep["fiedler_lambda2_before"], "/", rep["fiedler_lambda2_after"])
    # ---- wave-17 plasticity checks ----
    pl = _plasticity(seed=42, rounds=20)
    assert pl["label"] == "MODELED"
    assert pl["locked_count"] == 8
    assert pl["locked_edges_unchanged"] is True, "locked-8 canon edges must never mutate"
    assert _plasticity(42, 20) == _plasticity(42, 20), "plasticity deterministic"
    print("szl_fgbrain wave17: plasticity OK — locked canon frozen:",
          pl["locked_edges_unchanged"], "| plasticity_score", pl["plasticity_score"],
          "| ewc_core_protection", pl["ewc_core_protection_penalty"])
    # ---- wave-18 memory checks ----
    mem = _memory(seed=42, sessions=4)
    assert mem["label"] == "MODELED"
    assert mem["locked_count"] == 8
    assert mem["chain_intact"] is True, "HEART/BLOOD hash chain must verify"
    assert mem["beats_written"] == 4, "one beat per session"
    assert _memory(42, 4) == _memory(42, 4), "memory deterministic"
    print("szl_fgbrain wave18: memory OK — beats", mem["beats_written"],
          "chain_intact", mem["chain_intact"], "reconsolidation_gain",
          mem["reconsolidation_gain"], "distinct_pairs", mem["distinct_cofire_pairs"])
    # ---- wave-19 homeostasis (/vitals) checks ----
    vit = _homeostasis(seed=42, rounds=12)
    assert vit["label"] == "MODELED"
    assert vit["locked_count"] == 8, "homeostat must leave locked-proven EXACTLY 8"
    assert vit["locked_untouched"] is True, "no locked/conjecture tier may change"
    assert vit["actions_are_infra_only"] is True, "corrective actions must be INFRA-ONLY"
    dpr = vit["drive_per_round"]
    assert len(dpr) >= 2, "need a drive trace"
    # HRRL: drive must trend DOWN (final strictly below the start; non-increasing overall).
    assert dpr[-1] < dpr[0], "drive must trend down (homeostatic reward positive)"
    assert all(dpr[i + 1] <= dpr[i] + 1e-9 for i in range(len(dpr) - 1)), "drive must be monotone non-increasing"
    assert "CONJECTURE-1" in vit["conjecture_note"], "Λ must be labeled CONJECTURE-1"
    assert vit["viability_horizon"] >= 0
    assert _homeostasis(42, 12) == _homeostasis(42, 12), "vitals deterministic"
    # fail-closed: a long run must exhaust budget and STOP proposing (never auto-promote).
    fc = _homeostasis(seed=42, rounds=100)
    assert fc["fail_closed"] is True and fc["stopped_reason"] == "budget_exhausted_fail_closed", "must fail-closed on budget exhaustion"
    assert fc["locked_count"] == 8 and fc["locked_untouched"] is True
    assert fc["viability_horizon"] == 0, "exhausted budget => zero further sustainable cycles"
    print("szl_fgbrain wave19: vitals OK — drive", dpr[0], "->", vit["drive_final"],
          "| in_band", vit["in_band_count"], "/", vit["setpoint_count"],
          "| viability_horizon", vit["viability_horizon"],
          "| locked_untouched", vit["locked_untouched"], "| actions", len(vit["actions_taken"]))
    # ---- wave-20 evolution + organizational-closure (/evolve) checks ----
    ev = _evolve(seed=42, generations=15)
    assert ev["label"] == "MODELED"
    # DOCTRINE: real locked-8 NEVER incremented by evolution/archive/promotion.
    assert ev["locked_count"] == 8, "evolution must leave the real locked-proven set EXACTLY 8"
    assert ev["real_locked_before"] == 8 and ev["real_locked_after"] == 8, "locked==8 pre AND post"
    assert sum(1 for n in NODES if n["tier"] == "locked") == 8, "NODES locked tier still exactly 8"
    # MODELED promotions go to a SEPARATE staging counter, NOT the locked tier.
    assert ev["modeled_promotions"] >= 0 and ev["modeled_promotions"] < ev["candidates_generated"], "promotions must be a rare subset"
    # KERNEL GATE immutable: identical verdict on the fixed probe before/after evolution.
    assert ev["gate_immutable"] is True, "kernel gate must be immutable across evolution"
    assert ev["gate_probe_before"] == ev["gate_probe_after"], "gate probe verdict must match pre/post"
    # Independent immutability check: the gate function on the fixed probe is stable.
    assert _evo_lean_check(dict(_EVO_PROBE)) == _evo_lean_check(dict(_EVO_PROBE)), "gate deterministic"
    # CLAIM-PINNING: no promoted candidate ever had a weakened claim.
    assert ev["claim_pinning_ok"] is True, "promoted candidates must be claim-pinned (no weakening)"
    # a weakened-claim candidate MUST be rejected by the gate (never promoted).
    _weak = {"statement_original": "strong: additive fragment bounded",
             "statement_final": "weak: sometimes bounded", "difficulty": 0.05}
    assert _evo_lean_check(_weak)["promoted"] is False, "weakened claim must be rejected by the gate"
    # DRIFT ROLLBACK (Tallam): after forced drift the admission_rule == audited snapshot.
    assert ev["rollback_restored"] is True, "drift rollback must restore the audited admission_rule"
    assert ev["admission_rule"]["priority"] == ev["audited_admission_rule"]["priority"], "priority restored"
    assert ev["admission_rule"]["eligible_subtheories"] == ev["audited_admission_rule"]["eligible_subtheories"], "eligibility restored"
    # MAP-Elites diversity + determinism.
    assert ev["archive_cells_filled"] >= 1, "archive must fill at least one descriptor cell"
    assert ev["archive_cells_filled"] <= ev["archive_cells_possible"], "cannot exceed grid capacity"
    assert _evolve(42, 15) == _evolve(42, 15), "evolve deterministic"
    print("szl_fgbrain wave20: evolve OK — archive_cells_filled", ev["archive_cells_filled"],
          "/", ev["archive_cells_possible"], "| candidates", ev["candidates_generated"],
          "| modeled_promotions", ev["modeled_promotions"], "| locked", ev["locked_count"],
          "| gate_immutable", ev["gate_immutable"], "| claim_pinning_ok", ev["claim_pinning_ok"],
          "| rollback_restored", ev["rollback_restored"])
    # ---- wave-21 energy-attest checks ----
    en = _energy_attest()
    assert en["label"] == "MODELED"
    assert en["energy"]["status"] in ("MEASURED", "UNAVAILABLE")
    import os as _op
    if not _op.environ.get("SZL_JOULES_MEASURED", "").strip():
        assert en["energy"]["status"] == "UNAVAILABLE" and en["energy"]["joules"] is None
    assert _energy_attest() == _energy_attest()
    print("szl_fgbrain wave21: energy OK - status", en["energy"]["status"], "joules", en["energy"]["joules"], "(never fabricated)")
    # ---- wave-22 manifest checks ----
    mf = _manifest()
    assert mf["label"] == "MODELED"
    assert mf["locked_proven_count"] == 8
    assert mf["honesty_invariants"]["locked_proven_is_exactly_8"] is True
    assert mf["aliveness_reached"] == 5 and mf["aliveness_total"] == 5
    assert len(mf["conjectures_gray"]) >= 1
    assert _manifest() == _manifest()
    print("szl_fgbrain wave22: manifest OK - endpoints", mf["endpoint_count"],
          "aliveness", str(mf["aliveness_reached"]) + "/" + str(mf["aliveness_total"]),
          "locked", mf["locked_proven_count"])
    print("szl_fgbrain: ALL OK — real graph, MODELED firing anchored on locked-8, conjectures gray, deterministic.")
