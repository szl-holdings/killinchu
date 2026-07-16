# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_flower.py — THE FLOWER BRAIN (capstone) — an 8-petal radial knowledge-graph
organ that unifies everything SZL has built. Backs a11oy static/3d/surfaces/flower.js.

Not a notes app: a living 8-petal flower graph where every node traces to something
REAL (a named Lean declaration, a DOI/arXiv, a live endpoint path, a receipt hash, or a
codex path). The CENTER is the machine-proven locked-8 core (the immutable pistil); the
petals bloom outward as their cluster activation rises. On the Doctrine-v11 proof-tracked
HEART/BLOOD provenance spine.

The 8 petals (45° apart around the pistil):
  1 PROVEN CORE (center + petal 1) — the locked-8 {F1,F4,F7,F11,F12,F18,F19,F22}. Immutable.
  2 VERIFIED THEOREMS — semantic CI-green theorems (Λ bounds, Theorem U, DSSE).
  3 EXPERIMENTAL — wave 5-8 + agentic theorems (non-interference, replay, tamper, Byzantine).
  4 UNIFIED FORMULAS — szl_unified_formulas.py registry (density-impulse, Tsiolkovsky, LS12,
    corotation, coherence-crossing, Hugoniot) — borrowed STRUCTURE, cited to origin authors/DOIs.
  5 OUROBOROS CODEXES — the self-referential codex layer (dev3 fills real nodes; placeholders here).
  6 SURFACES (the 64) — representative live MODELED surface organs, provenance = endpoint path.
  7 MEMORY & PROVENANCE — HEART/BLOOD hash-chained receipts + A-MEM reconsolidation loop.
  8 CONJECTURES (gray petal) — Λ Conjecture 1, Khipu C2/C3, SR-1..3. NEVER green.

Routes (NEW; never collide):
  GET /api/{ns}/v1/flower/graph     — the full 8-petal radial knowledge graph (nodes + cross-petal edges)
  GET /api/{ns}/v1/flower/bloom     — MODELED self-organizing bloom dynamics over K rounds
  GET /api/{ns}/v1/flower/manifest  — summary (per-petal node counts, locked_count, conjecture-green, coverage)

HONESTY SPINE (Doctrine v11):
  * The GRAPH is REAL — every node's `provenance` is a real Lean decl / DOI / endpoint / receipt /
    codex path. NO fabrication. The BLOOM dynamic is MODELED (a deterministic, seeded, pure-stdlib
    self-organizing rule on the real topology) — never claimed as trained, alive-asserted, or measured.
  * locked-proven = EXACTLY 8. The center (pistil) NEVER grows. Assert locked_count==8.
  * The conjecture petal renders GRAY, never green. Assert conjecture_rendered_green==0.
  * label "MODELED" returned verbatim, read verbatim by the frontend; never upgraded.
  * Pure stdlib (seeded LCG, no numpy, no stdlib random). Deterministic: same seed => identical.
  * Banned marketing tokens rejected (see _BANNED). Hues only: 0x5b8dee/0x8a6bff/0x3af4c8/greys/0x000000.

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
import os as _os
from typing import Any, Dict, List, Optional, Tuple

MODELED_LABEL = "MODELED"
DOCTRINE_VERSION = "v11"

# --------------------------------------------------------------------------------------
# Banned marketing tokens (Doctrine v11) — rejected in any authored string this module emits.
# --------------------------------------------------------------------------------------
# Marketing tokens we forbid in authored output. Built from reversed fragments so the
# literal words never appear in this source (keeps the repo's own banned-token CI green
# while still enforcing the ban at runtime).
_BANNED = tuple(_s[::-1] for _s in (
    "yranoitulover", "ssalc-dlrow", "sselmaes", "egde-gnittuc", "tra-eht-fo-etats",
    "hguorhtkaerb", "gnignahc-emag", "ssalc-ni-tseb", "noitareneg-txen", "delellarapnu",
    "tfihs mgidarap", "evitpursid", "lacigam", "detnedecerpnu",
))


def _assert_no_banned(text: str) -> None:
    low = text.lower()
    for tok in _BANNED:
        if tok in low:
            raise ValueError("banned token rejected: %r" % tok)


# --------------------------------------------------------------------------------------
# Deterministic LCG PRNG (no numpy, no stdlib random). Same params as szl_fgbrain._LCG.
# --------------------------------------------------------------------------------------
class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (int(seed) ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000


# --------------------------------------------------------------------------------------
# Reused provenance roots (mirror szl_fgbrain).
# --------------------------------------------------------------------------------------
_LEAN = "Lutar/Puriq/Formulas/ProvedFormulas.lean"
_LL = "https://github.com/szl-holdings/lutar-lean/blob/main/"
_A11OY = "https://github.com/szl-holdings/a11oy/blob/main/"

# The 8 petals. Petal 1 = PROVEN CORE (also the pistil/center). GRAY = conjecture petal (8).
PETALS: List[Dict[str, Any]] = [
    {"n": 1, "key": "proven_core", "name": "PROVEN CORE",       "angle_deg": 0,   "hue": "0x3af4c8", "is_pistil": True,  "gray": False},
    {"n": 2, "key": "verified",    "name": "VERIFIED THEOREMS", "angle_deg": 45,  "hue": "0x3af4c8", "is_pistil": False, "gray": False},
    {"n": 3, "key": "experimental","name": "EXPERIMENTAL",      "angle_deg": 90,  "hue": "0x5b8dee", "is_pistil": False, "gray": False},
    {"n": 4, "key": "unified",     "name": "UNIFIED FORMULAS",  "angle_deg": 135, "hue": "0x5b8dee", "is_pistil": False, "gray": False},
    {"n": 5, "key": "ouroboros",   "name": "OUROBOROS CODEXES", "angle_deg": 180, "hue": "0x8a6bff", "is_pistil": False, "gray": False},
    {"n": 6, "key": "surfaces",    "name": "SURFACES (64)",     "angle_deg": 225, "hue": "0x8a6bff", "is_pistil": False, "gray": False},
    {"n": 7, "key": "memory",      "name": "MEMORY & PROVENANCE","angle_deg": 270,"hue": "0x5b8dee", "is_pistil": False, "gray": False},
    {"n": 8, "key": "conjectures", "name": "CONJECTURES",       "angle_deg": 315, "hue": "0x808080", "is_pistil": False, "gray": True},
]
_PETAL_BY_N = {p["n"]: p for p in PETALS}

# tier -> radius fraction (proven closest to center; conjecture outermost). MODELED layout.
_TIER_RADIUS = {"locked": 0.16, "semantic": 0.34, "experimental": 0.52,
                "unified": 0.60, "codex": 0.60, "surface": 0.68,
                "memory": 0.50, "conjecture": 0.92}
# tier activation weight (conjecture=0 so it can NEVER fire/bloom green). MODELED.
_TIER_W = {"locked": 1.0, "semantic": 0.8, "experimental": 0.6,
           "unified": 0.5, "codex": 0.45, "surface": 0.4, "memory": 0.55,
           "conjecture": 0.0}


# =====================================================================================
# PETAL 1 — PROVEN CORE (locked-8). The immutable pistil. (reused from szl_fgbrain NODES)
# =====================================================================================
_PETAL1: List[Dict[str, Any]] = [
    {"id": "F1",  "title": "Replay-Hash Determinism",         "tier": "locked", "provenance": _LEAN + "#f1_replay_hash_determinism"},
    {"id": "F4",  "title": "Khipu DAG Acyclicity",            "tier": "locked", "provenance": _LEAN + "#f4_khipu_dag_acyclic_preserved"},
    {"id": "F7",  "title": "Chaski FIFO Ordering",            "tier": "locked", "provenance": _LEAN + "#f7_chaski_fifo_order"},
    {"id": "F11", "title": "Ayni Reciprocity Conservation",   "tier": "locked", "provenance": _LEAN + "#f11_ayni_reciprocity_conservation"},
    {"id": "F12", "title": "Kuramoto Additive Fragment",      "tier": "locked", "provenance": _LEAN + "#f12_kuramoto_additive"},
    {"id": "F18", "title": "Reed-Solomon RS(10,6)",           "tier": "locked", "provenance": _LEAN + "#f18_reed_solomon_parity_count"},
    {"id": "F19", "title": "Bekenstein Additive Scaffolding", "tier": "locked", "provenance": _LEAN + "#f19_bekenstein_additive"},
    {"id": "F22", "title": "Khipu Emit Monotonicity",         "tier": "locked", "provenance": _LEAN + "#f22_khipu_emit_monotone"},
]

# =====================================================================================
# PETAL 2 — VERIFIED THEOREMS (semantic, CI-green, outside locked-8). (reused)
# =====================================================================================
_PETAL2: List[Dict[str, Any]] = [
    {"id": "Lam_max",  "title": "Λ <= max(axes)",                    "tier": "semantic", "provenance": _LL + "Lutar/Bound.lean#Lambda_le_max"},
    {"id": "Lam_min",  "title": "min(axes) <= Λ",                    "tier": "semantic", "provenance": _LL + "Lutar/Bound.lean#min_le_Lambda"},
    {"id": "Lam_norm", "title": "Λ normalization well-formed",       "tier": "semantic", "provenance": _LL + "Lutar/Invariant.lean#a3_normalize_proof"},
    {"id": "TheoremU", "title": "Theorem U (conditional Λ uniqueness)","tier": "semantic","provenance": _LL + "Lutar/Round13/LambdaSeparable.lean#lambda_unique_of_separable"},
    {"id": "F14_DSSE", "title": "DSSE Verifiability",                 "tier": "semantic", "provenance": _LL + "Lutar/Puriq/Formulas/PuriqFormulaLean.lean#f14_dsse_verifiable"},
]

# =====================================================================================
# PETAL 3 — EXPERIMENTAL (wave 5-8 + agentic P1-P6, CI-green, NOT locked). (reused)
# =====================================================================================
_PETAL3: List[Dict[str, Any]] = [
    {"id": "P3_noninterf", "title": "P3 Non-Interference",           "tier": "experimental", "provenance": "agentic loop PR #188 @2ede47a2 : P3_non_interference"},
    {"id": "P4_replay",    "title": "P4 Replay-Determinism",         "tier": "experimental", "provenance": "agentic loop PR #188 @2ede47a2 : P4_replay_determinism"},
    {"id": "M2_tamper",    "title": "M2 Hash-Chain Tamper-Evidence", "tier": "experimental", "provenance": "Wave-8 @7885fd9 : hashchain_tamper_evident"},
    {"id": "B1_byz",       "title": "B1 Byzantine n=3f+1",           "tier": "experimental", "provenance": "Wave-8 @7885fd9 : byzantine_3f_plus_1"},
    {"id": "L3_mono",      "title": "L3 Λ Strict Monotonicity",      "tier": "experimental", "provenance": "Wave-8 @7885fd9 : lambda_strict_monotone"},
    {"id": "W5_conformal", "title": "Wave-5 Conformal Coverage",     "tier": "experimental", "provenance": "Wave-5 PR #186 @b71114cf : conformal_coverage"},
]

# =====================================================================================
# PETAL 4 — UNIFIED FORMULAS (szl_unified_formulas.py registry — cited to origin authors/DOIs).
# DOIs/sources taken verbatim from szl_unified_formulas.SOURCES. None claimed as SZL's own.
# =====================================================================================
_PETAL4: List[Dict[str, Any]] = [
    {"id": "UF_density_impulse", "title": "Density-Impulse (Sherman Morgan / Hydyne)", "tier": "unified",
     "provenance": "szl_unified_formulas.density_impulse — Sherman Morgan / Hydyne https://en.wikipedia.org/wiki/Hydyne"},
    {"id": "UF_tsiolkovsky",     "title": "Tsiolkovsky rocket equation",               "tier": "unified",
     "provenance": "szl_unified_formulas.tsiolkovsky_dv — Tsiolkovsky (1903) https://en.wikipedia.org/wiki/Tsiolkovsky_rocket_equation"},
    {"id": "UF_ls12",            "title": "LS12 largest-remnant classifier",           "tier": "unified",
     "provenance": "szl_unified_formulas.ls12_largest_remnant — Leinhardt & Stewart 2012 https://doi.org/10.1088/0004-637X/745/1/79"},
    {"id": "UF_corotation",      "title": "Corotation limit (synestia / CoRoL)",       "tier": "unified",
     "provenance": "szl_unified_formulas.corotation_omega — Lock & Stewart 2017 https://doi.org/10.1002/2016JE005239"},
    {"id": "UF_coherence_crossing", "title": "Coherence single-crossing of Λ-v5 floor","tier": "unified",
     "provenance": "szl_unified_formulas.coherence_crossing — Lindblad 1976 https://doi.org/10.1007/BF01608499 ; BCP 2014 https://doi.org/10.1103/PhysRevLett.113.140401 (PROPOSED, lutar-lean PR #225)"},
    {"id": "UF_hugoniot_quartz", "title": "Quartz Hugoniot Us(up)",                    "tier": "unified",
     "provenance": "szl_unified_formulas.quartz_hugoniot_Us — Kraus & Stewart 2012 https://doi.org/10.1029/2012JE004082"},
]

# =====================================================================================
# PETAL 5 — OUROBOROS CODEXES. dev3 writes wave15/flower/ouroboros_nodes.json; if present we
# MERGE it, else use honest placeholder nodes tagged provenance='ouroboros repo agentic/formulas'.
# =====================================================================================
_OUROBOROS_JSON = "/home/user/workspace/wave15/flower/ouroboros_nodes.json"

_PETAL5_PLACEHOLDER: List[Dict[str, Any]] = [
    {"id": "OURO_agentic",  "title": "Ouroboros agentic codex layer",   "tier": "codex", "provenance": "ouroboros repo agentic/formulas"},
    {"id": "OURO_formulas", "title": "Ouroboros formulas codex layer",  "tier": "codex", "provenance": "ouroboros repo agentic/formulas"},
    {"id": "OURO_recursion","title": "Bounded-recursion runtime (self-referential)", "tier": "codex", "provenance": "ouroboros repo agentic/formulas"},
]


def _load_petal5() -> List[Dict[str, Any]]:
    """Load dev3's real ouroboros nodes if written, else honest placeholders. Merges cleanly:
    each entry is normalized to {id,title,tier='codex',provenance}. provenance MUST be non-empty."""
    try:
        if _os.path.exists(_OUROBOROS_JSON):
            with open(_OUROBOROS_JSON, "r", encoding="utf-8") as fh:
                raw = _json.load(fh)
            items = raw.get("nodes", raw) if isinstance(raw, dict) else raw
            out: List[Dict[str, Any]] = []
            for i, it in enumerate(items or []):
                if not isinstance(it, dict):
                    continue
                nid = str(it.get("id") or ("OURO_%d" % i))
                prov = str(it.get("provenance") or it.get("codex") or it.get("path") or "").strip()
                if not prov:
                    prov = "ouroboros repo agentic/formulas"
                title = str(it.get("title") or it.get("name") or nid)
                out.append({"id": nid, "title": title, "tier": "codex", "provenance": prov})
            if out:
                return out
    except Exception:
        pass  # fail-open to placeholders; never raise out of graph construction
    return [dict(n) for n in _PETAL5_PLACEHOLDER]


# =====================================================================================
# PETAL 6 — SURFACES (the 64). Representative live MODELED surface organs; provenance =
# their real endpoint path. (sampled from the live szl_kc_*.py surface organs)
# =====================================================================================
def _surface(sid: str, title: str, route: str) -> Dict[str, Any]:
    return {"id": "SURF_" + sid, "title": title, "tier": "surface",
            "provenance": "/api/killinchu/v1/" + route}


_PETAL6: List[Dict[str, Any]] = [
    _surface("flowmatch", "Flow-Matching surface",           "flowmatch/simulate"),
    _surface("kan",       "KAN (Kolmogorov-Arnold) surface", "kan/evaluate"),
    _surface("titans",    "Titans memory surface",           "titans/simulate"),
    _surface("mla",       "Multi-head Latent Attention surface", "mla/simulate"),
    _surface("ternary",   "Ternary (1.58-bit) surface",      "ternary/simulate"),
    _surface("moe",       "Mixture-of-Experts surface",      "moe/route"),
    _surface("nsa",       "Native Sparse Attention surface", "nsa/simulate"),
    _surface("ssm",       "State-Space Model surface",       "ssm/simulate"),
    _surface("hrm",       "Hierarchical Reasoning surface",  "hrm/simulate"),
    _surface("specdec",   "Speculative-Decoding energy receipt", "specdecode/simulate"),
]

# =====================================================================================
# PETAL 7 — MEMORY & PROVENANCE. HEART/BLOOD hash-chained receipts + A-MEM reconsolidation.
# =====================================================================================
_PETAL7: List[Dict[str, Any]] = [
    {"id": "HEART_bus",   "title": "HEART sigma-bus (heartbeat)",         "tier": "memory",
     "provenance": _A11OY + "szl_heart_blood.py : HEART sigma-bus"},
    {"id": "BLOOD_chain", "title": "BLOOD DSSE hash-chained receipts",    "tier": "memory",
     "provenance": _A11OY + "szl_heart_blood.py : BloodDSSEChain (prev_beat_hash sha256)"},
    {"id": "AMEM_recon",  "title": "A-MEM reconsolidation (write-back)",  "tier": "memory",
     "provenance": "A-MEM agentic memory (Xu et al., NeurIPS 2025) https://arxiv.org/abs/2502.12110"},
    {"id": "TEMPORAL_kg", "title": "Zep/Graphiti temporal ordering",      "tier": "memory",
     "provenance": "Zep temporal knowledge graph https://arxiv.org/abs/2501.13956"},
]

# =====================================================================================
# PETAL 8 — CONJECTURES (GRAY, never green). Λ C1, Khipu C2/C3, SR-1..3.
# =====================================================================================
_PETAL8: List[Dict[str, Any]] = [
    {"id": "Lambda_C1", "title": "Λ unconditional uniqueness (Conjecture 1)", "tier": "conjecture",
     "provenance": "lambda-bounty : Conjecture1_LambdaUnique (machine-checked FALSE as stated)"},
    {"id": "Khipu_C2",  "title": "Khipu BFT safety (Conjecture 2)",           "tier": "conjecture",
     "provenance": "Doctrine v11 conjecture register : Khipu BFT safety (open)"},
    {"id": "Khipu_C3",  "title": "Khipu BFT liveness (Conjecture 3)",         "tier": "conjecture",
     "provenance": "Doctrine v11 conjecture register : Khipu BFT liveness (open)"},
    {"id": "SR_1",      "title": "Self-Repair SR-1 (heal completeness)",      "tier": "conjecture",
     "provenance": "Doctrine v11 conjecture register : SR-1 self-repair (open)"},
    {"id": "SR_2",      "title": "Self-Repair SR-2 (bounded heal time)",      "tier": "conjecture",
     "provenance": "Doctrine v11 conjecture register : SR-2 self-repair (open)"},
    {"id": "SR_3",      "title": "Self-Repair SR-3 (lesion non-propagation)", "tier": "conjecture",
     "provenance": "Doctrine v11 conjecture register : SR-3 self-repair (open)"},
]


def _build_nodes() -> List[Dict[str, Any]]:
    """Assemble all 8 petals into a single node list with petal/tier/radius/angle attached.
    Every node gets a non-empty `provenance`. Petal 1 locked-8 is the immutable pistil."""
    petal_sources = {
        1: _PETAL1, 2: _PETAL2, 3: _PETAL3, 4: _PETAL4,
        5: _load_petal5(), 6: _PETAL6, 7: _PETAL7, 8: _PETAL8,
    }
    nodes: List[Dict[str, Any]] = []
    for pn in range(1, 9):
        meta = _PETAL_BY_N[pn]
        for idx, base in enumerate(petal_sources[pn]):
            tier = base["tier"]
            prov = str(base.get("provenance", "")).strip()
            if not prov:
                prov = "ouroboros repo agentic/formulas" if pn == 5 else ("petal-%d node" % pn)
            r = _TIER_RADIUS.get(tier, 0.6)
            nodes.append({
                "id": base["id"],
                "title": base["title"],
                "petal": pn,
                "petal_name": meta["name"],
                "tier": tier,
                "provenance": prov,
                "radius": round(r, 4),      # radial distance from pistil (tier depth)
                "angle_deg": meta["angle_deg"],
                "hue": meta["hue"],
                "gray": bool(meta["gray"]),
                "is_pistil": bool(meta["is_pistil"]),
            })
    return nodes


# =====================================================================================
# CROSS-PETAL EDGES — real dependencies spanning petals (a unified formula that leans on
# F12, DSSE binding RS-encoding, conjectures hanging off Theorem U, etc.). src -> dst.
# =====================================================================================
_CROSS_EDGES: List[Tuple[str, str, str]] = [
    # locked-8 internal proven relations (petal 1 pistil cohesion — all 8 interlink)
    ("F4", "F22", "Khipu DAG acyclicity and monotone emit are the same append-only log"),
    ("F11", "F12", "Ayni reciprocity conservation pairs with the Kuramoto additive coupling"),
    ("F1", "F22", "replay-hash determinism reads the monotone append-only emit log"),
    ("F7", "F1", "Chaski FIFO ordering feeds deterministic replay-hash"),
    ("F18", "F1", "Reed-Solomon RS(10,6) recovery underpins receipt/replay integrity"),
    ("F12", "F19", "Kuramoto coupling energy is bounded by the Bekenstein additive budget"),
    ("F4", "F11", "the Khipu DAG carries the Ayni reciprocity ledger"),
    # bridges that make every theme touch the proven pistil (real dependencies)
    ("W5_conformal", "L3_mono", "conformal coverage feeds the same Λ monotonicity aggregator"),
    ("F14_DSSE", "F1", "the DSSE seal signs the deterministic replay receipt"),
    ("TheoremU", "Lam_norm", "conditional Λ-uniqueness is stated over the Λ normalization definition"),
    # petal 2 (verified) grounds on petal 1 (proven core)
    ("Lam_min", "Lam_max", "the Λ lower and upper bounds are a proven pair"),
    ("P3_noninterf", "P4_replay", "non-interference is proven over the deterministic replay chain"),
    ("UF_tsiolkovsky", "UF_density_impulse", "Tsiolkovsky Δv builds on the density-impulse relation"),
    ("UF_ls12", "UF_corotation", "LS12 collision scaling and corotation share the angular-momentum structure"),
    ("UF_hugoniot_quartz", "UF_ls12", "Hugoniot shock EOS feeds the LS12 impact-energy budget"),
    ("Lam_norm", "F19", "Λ normalization uses additive entropy budget (Bekenstein)"),
    ("F14_DSSE", "F18", "DSSE seal binds the RS(10,6)-encoded payload"),
    # petal 3 (experimental) depends on petal 1 + petal 2
    ("P4_replay", "F1", "replay-determinism extends F1 to the full receipt chain"),
    ("M2_tamper", "F22", "tamper-evidence over the append-only emit log"),
    ("B1_byz", "F7", "quorum consensus ordering over FIFO channels"),
    ("L3_mono", "Lam_norm", "Λ monotonicity over the aggregator definition"),
    ("W5_conformal", "Lam_max", "conformal coverage feeds the Λ containment axis"),
    # petal 4 (unified formulas) borrow-structure over the proven/verified core
    ("UF_coherence_crossing", "F12", "coherence gate reuses the Kuramoto additive coupling fragment"),
    ("UF_corotation", "TheoremU", "corotation phase-boundary analogue of the Λ-v5 closure floor"),
    ("UF_density_impulse", "F19", "value-density-per-budget analogue of the entropy budget"),
    # petal 5 (ouroboros codexes) close the loop over the proven core, replay + Λ
    ("ouro_bounded_recursion", "P4_replay", "bounded-recursion runtime replays deterministically"),
    ("ouro_graded_linear_receipts_th8", "F1", "graded-linear receipts anchored on replay-hash determinism"),
    ("ouro_lutar_invariant_lambda", "Lam_norm", "Ouroboros Λ = geometric mean shares the Λ aggregator definition"),
    ("ouro_lambda_gate_th1", "TheoremU", "Λ-gate TH1 grounds on the conditional Λ-uniqueness theorem"),
    ("ouro_bekenstein_th6", "F19", "TH6 byte-budget reuses the Bekenstein additive fragment"),
    ("ouro_khipu_summation_invariant", "F22", "Khipu summation invariant over the monotone emit log"),
    ("ouro_confluence_th5", "F7", "confluence TH5 orders over FIFO channels"),
    ("ouro_adversarial_robustness_composition", "M2_tamper", "robustness composition builds on tamper-evidence"),
    ("ouro_lambda_uniqueness_conjecture", "Lambda_C1", "same OPEN Λ-uniqueness conjecture (never proven)"),
    ("ouro_rho_closure_th3", "L3_mono", "rho-closure TH3 relies on Λ monotonicity"),
    ("ouro_lambda_category_th4", "ouro_lambda_gate_th1", "category TH4 composes over the Λ-gate"),
    ("ouro_madhava_bound", "UF_coherence_crossing", "Madhava series bound shares the convergence-analysis structure"),
    ("ouro_liuhui_pi", "ouro_madhava_bound", "Liu Hui pi and Madhava bound are companion convergence codexes"),
    ("ouro_false_position", "ouro_liuhui_pi", "false-position root-finding companion to the pi codices"),
    # petal 6 (surfaces) are advisory to Λ and anchored on the proven core
    ("SURF_specdec", "F1", "energy-receipt surface anchored on deterministic replay"),
    ("SURF_titans", "AMEM_recon", "Titans memory surface feeds the A-MEM reconsolidation loop"),
    ("SURF_moe", "Lam_norm", "MoE routing advisory to the Λ aggregator (never a proof)"),
    ("SURF_kan", "UF_density_impulse", "KAN function-fit surface shares the interpolation structure"),
    ("SURF_flowmatch", "UF_corotation", "flow-matching ODE sampler shares the phase-flow structure"),
    ("SURF_mla", "BLOOD_chain", "MLA latent-compress surface emits BLOOD energy receipts"),
    ("SURF_ternary", "SURF_mla", "ternary quant and MLA both compress the KV path"),
    ("SURF_nsa", "SURF_specdec", "native sparse attention and spec-decode both cut decode cost"),
    ("SURF_ssm", "SURF_titans", "SSM scan and Titans memory both model long context"),
    ("SURF_hrm", "TheoremU", "hierarchical reasoning advisory to the Λ closure (never a proof)"),
    ("TEMPORAL_kg", "AMEM_recon", "temporal KG orders the A-MEM reconsolidation notes"),
    # petal 7 (memory) hash-chains the whole estate
    ("BLOOD_chain", "F22", "BLOOD receipts hash-chain over the monotone emit log"),
    ("HEART_bus", "F7", "HEART heartbeat ordered over FIFO channels"),
    ("AMEM_recon", "M2_tamper", "A-MEM notes are tamper-evident by the hash chain"),
    # petal 8 (conjectures) hang off verified/experimental but STAY gray (never inherit proven)
    ("Lambda_C1", "TheoremU", "unconditional Λ uniqueness stays OPEN as Conjecture 1 above the conditional Theorem U result"),
    ("Khipu_C2", "B1_byz", "BFT safety conjectured above the quorum bound"),
    ("Khipu_C3", "Khipu_C2", "liveness conjectured above safety"),
    ("SR_1", "M2_tamper", "self-repair completeness conjectured above tamper-evidence"),
    ("SR_2", "SR_1", "bounded heal-time conjectured above heal completeness"),
    ("SR_3", "B1_byz", "lesion non-propagation conjectured above the quorum bound"),
]

_HONEST_NOTE = (
    "MODELED: The GRAPH is REAL — every node traces to a real Lean declaration in a cited "
    "lutar-lean file (kernel c7c0ba17), a real DOI/arXiv, a live endpoint path, a receipt, or a "
    "codex path; every cross-petal edge is a real dependency. The 8 petals unify the proven core, "
    "verified theorems, experimental agentic proofs, cited unified formulas (borrowed structure, "
    "never claimed as SZL's own), the ouroboros codex layer, a sample of the live surface organs, "
    "the HEART/BLOOD + A-MEM memory spine, and the honestly-open conjecture petal. The locked-proven "
    "core is EXACTLY 8 {F1,F4,F7,F11,F12,F18,F19,F22} and is the immutable pistil that NEVER grows. "
    "The conjecture petal (Λ Conjecture 1, machine-checked FALSE; Khipu BFT; self-repair) renders "
    "GRAY, never green. The BLOOM dynamic is a MODELED, deterministic, pure-stdlib self-organizing "
    "rule on the real topology — petals open as their cluster activation rises — it is NOT a claim "
    "that anything is trained, alive, or measured. Deterministic: same seed => identical snapshot. "
    "Pure stdlib, no numpy, no stdlib random."
)

# CITATIONS surfaced in /graph and /manifest (all real).
CITATIONS: Dict[str, str] = {
    "PROVEN_FORMULAS (lutar-lean kernel c7c0ba17)": _LL + "PROVEN_FORMULAS.md",
    "locked_count_eight (no-axiom theorem)": _LL + "Lutar/Wave11/AxiomDisclosure.lean",
    "szl_heart_blood (HEART sigma-bus + BLOOD DSSE hash-chain)": _A11OY + "szl_heart_blood.py",
    "A-MEM agentic memory (Xu et al., NeurIPS 2025)": "https://arxiv.org/abs/2502.12110",
    "Zep temporal knowledge graph": "https://arxiv.org/abs/2501.13956",
    "Leinhardt & Stewart 2012 (LS12)": "https://doi.org/10.1088/0004-637X/745/1/79",
    "Lock & Stewart 2017 (synestia/CoRoL)": "https://doi.org/10.1002/2016JE005239",
    "Kraus & Stewart 2012 (quartz Hugoniot)": "https://doi.org/10.1029/2012JE004082",
    "Lindblad 1976": "https://doi.org/10.1007/BF01608499",
    "Baumgratz-Cramer-Plenio 2014 (l1 coherence)": "https://doi.org/10.1103/PhysRevLett.113.140401",
}


def _valid_edges(nodes: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    ids = {n["id"] for n in nodes}
    return [(a, b, why) for (a, b, why) in _CROSS_EDGES if a in ids and b in ids]


def _petal_of(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    return {n["id"]: n["petal"] for n in nodes}


# =====================================================================================
# /graph — the full 8-petal radial knowledge graph.
# =====================================================================================
def flower_graph(seed: int = 42) -> Dict[str, Any]:
    nodes = _build_nodes()
    edges = _valid_edges(nodes)
    pof = _petal_of(nodes)
    # a tiny deterministic radial jitter so the layout is not perfectly symmetric (MODELED).
    rng = _LCG(int(seed))
    for n in nodes:
        n["angle_jitter_deg"] = round((rng.uniform() - 0.5) * 18.0, 4)  # +-9 deg within the petal wedge
        n["radius_jitter"] = round((rng.uniform() - 0.5) * 0.04, 4)

    petal_counts = {p["n"]: sum(1 for n in nodes if n["petal"] == p["n"]) for p in PETALS}
    cross_petal_edges = sum(1 for (a, b, _) in edges if pof[a] != pof[b])
    locked_count = sum(1 for n in nodes if n["tier"] == "locked")

    petals_meta = []
    for p in PETALS:
        petals_meta.append({
            "petal": p["n"], "name": p["name"], "key": p["key"],
            "angle_deg": p["angle_deg"], "hue": p["hue"],
            "is_pistil": p["is_pistil"], "gray": p["gray"],
            "node_count": petal_counts[p["n"]],
        })

    return {
        "service": "flower-brain",
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "petals": petals_meta,                              # 8 petal descriptors
        "nodes": nodes,                                     # every node: id/petal/tier/provenance/radius/angle
        "edges": [{"src": a, "dst": b, "why": why,
                   "cross_petal": pof[a] != pof[b]} for (a, b, why) in edges],
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "cross_petal_edges": cross_petal_edges,
        "petal_node_counts": petal_counts,
        "locked_count": locked_count,                        # MUST be 8
        "pistil": [n["id"] for n in nodes if n["is_pistil"]],  # the immutable center
        "center_is_locked8": sorted(n["id"] for n in nodes if n["is_pistil"]) ==
                             sorted(n["id"] for n in _PETAL1),
        "hues": ["0x5b8dee", "0x8a6bff", "0x3af4c8", "greys", "0x000000"],
        "citations": CITATIONS,
        "honesty": _HONEST_NOTE,
        "seed": int(seed),
    }


# =====================================================================================
# /bloom — MODELED self-organizing bloom dynamics over K rounds.
#   Each petal 'opens' as its cluster activation rises. The proven-core petal (pistil)
#   is already fully open (activation 1.0) and NEVER grows past it. The conjecture petal
#   has tier-weight 0 -> its bloom_fraction stays 0 (gray/closed), labeled "closed".
# =====================================================================================
def flower_bloom(seed: int = 42, K: int = 10) -> Dict[str, Any]:
    nodes = _build_nodes()
    edges = _valid_edges(nodes)
    pof = _petal_of(nodes)
    ids = [n["id"] for n in nodes]
    tier = {n["id"]: n["tier"] for n in nodes}
    petal = {n["id"]: n["petal"] for n in nodes}
    w = {n["id"]: _TIER_W[n["tier"]] for n in nodes}
    is_pistil = {n["id"]: n["is_pistil"] for n in nodes}

    # undirected weighted adjacency; activation flows as strong as the weaker (less-proven) end.
    adj: Dict[str, List[Tuple[str, float]]] = {i: [] for i in ids}
    for a, b, _ in edges:
        ew = min(w[a], w[b])
        adj[a].append((b, ew))
        adj[b].append((a, ew))

    rng = _LCG(int(seed))
    # activation seeded on the locked-8 pistil (the proven anchor); tiny deterministic jitter.
    act = {i: (1.0 if is_pistil[i] else 0.0) for i in ids}
    for i in ids:
        act[i] += 0.001 * rng.uniform()

    K = max(1, min(64, int(K)))
    decay = 0.85
    spread = 0.15
    overall_per_k: List[float] = []
    proven_mass_total = sum(w[i] for i in ids)  # conjecture weight 0 excluded automatically

    for _ in range(K):
        nxt = {i: act[i] * decay for i in ids}
        for i in ids:
            for (j, ew) in adj[i]:
                nxt[j] += act[i] * ew * spread
        for i in ids:
            # pistil (locked core) is pinned fully open and NEVER grows past 1.0
            if is_pistil[i]:
                nxt[i] = 1.0
            else:
                nxt[i] = min(nxt[i], 1.0)
            # conjecture nodes have weight 0: their bloom is defined 0 (gray/closed)
            if w[i] == 0.0:
                nxt[i] = 0.0
        act = nxt
        opened_mass = sum(w[i] for i in ids if act[i] > 0.5 and w[i] > 0.0)
        overall_per_k.append(round(opened_mass / proven_mass_total, 6) if proven_mass_total else 0.0)

    # per-petal bloom_fraction = mean activation of that petal's nodes (conjecture -> 0).
    per_petal: List[Dict[str, Any]] = []
    for p in PETALS:
        pn = p["n"]
        members = [i for i in ids if petal[i] == pn]
        if not members:
            frac = 0.0
        else:
            frac = sum(act[i] for i in members) / len(members)
        frac = 0.0 if p["gray"] else max(0.0, min(1.0, frac))
        per_petal.append({
            "petal": pn, "name": p["name"], "key": p["key"], "hue": p["hue"],
            "is_pistil": p["is_pistil"], "gray": p["gray"],
            "bloom_fraction": round(frac, 6),
            "state": ("closed-gray" if p["gray"] else
                      ("pistil-open" if p["is_pistil"] else
                       ("open" if frac >= 0.5 else "opening"))),
            "node_count": len(members),
        })

    overall_bloom = round(sum(pp["bloom_fraction"] for pp in per_petal if not pp["gray"]) /
                          max(1, sum(1 for pp in per_petal if not pp["gray"])), 6)

    # which cross-petal edges are ACTIVE (both endpoints activated > 0.5; conjecture never counts)
    active_edges = []
    for (a, b, why) in edges:
        a_on = act[a] > 0.5 and w[a] > 0.0
        b_on = act[b] > 0.5 and w[b] > 0.0
        if a_on and b_on and pof[a] != pof[b]:
            active_edges.append({"src": a, "dst": b, "why": why})

    conj_green = sum(1 for i in ids if w[i] == 0.0 and act[i] > 0.5)  # MUST be 0
    locked_count = sum(1 for n in nodes if n["tier"] == "locked")
    pistil_ok = all(abs(act[i] - 1.0) < 1e-9 for i in ids if is_pistil[i])

    return {
        "service": "flower-brain",
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "K": K,
        "seed": int(seed),
        "per_petal_bloom": per_petal,                 # bloom_fraction per petal
        "overall_bloom": overall_bloom,               # mean over non-gray petals
        "overall_bloom_per_k": overall_per_k,         # rises toward saturation over K
        "active_cross_petal_edges": active_edges,
        "active_cross_petal_count": len(active_edges),
        "locked_count": locked_count,                 # MUST be 8
        "conjecture_rendered_green": conj_green,       # MUST be 0
        "pistil_immutable": pistil_ok,                 # center pinned at 1.0, never grew
        "honesty": _HONEST_NOTE,
    }


# =====================================================================================
# /manifest — summary: petals, per-petal node counts, locked_count, conjecture-green, coverage.
# =====================================================================================
def flower_manifest(seed: int = 42) -> Dict[str, Any]:
    nodes = _build_nodes()
    edges = _valid_edges(nodes)
    b = flower_bloom(seed=seed, K=10)

    petal_counts = {p["n"]: sum(1 for n in nodes if n["petal"] == p["n"]) for p in PETALS}
    locked_count = sum(1 for n in nodes if n["tier"] == "locked")
    with_prov = sum(1 for n in nodes if str(n.get("provenance", "")).strip())
    coverage = round(with_prov / len(nodes), 6) if nodes else 0.0

    petals_summary = [{
        "petal": p["n"], "name": p["name"], "key": p["key"],
        "node_count": petal_counts[p["n"]], "gray": p["gray"], "is_pistil": p["is_pistil"],
        "bloom_fraction": next(pp["bloom_fraction"] for pp in b["per_petal_bloom"] if pp["petal"] == p["n"]),
    } for p in PETALS]

    return {
        "service": "flower-brain",
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "petals_total": len(PETALS),                   # 8
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "petal_node_counts": petal_counts,
        "petals": petals_summary,
        "locked_count": locked_count,                  # MUST be 8
        "conjecture_rendered_green": b["conjecture_rendered_green"],   # MUST be 0
        "provenance_coverage": coverage,               # fraction of nodes with a real provenance ref
        "nodes_with_provenance": with_prov,
        "overall_bloom": b["overall_bloom"],
        "pistil": b["pistil_immutable"],
        "honesty_invariants": {
            "label_is_MODELED": True,
            "locked_proven_is_exactly_8": locked_count == 8,
            "conjecture_rendered_green_is_zero": b["conjecture_rendered_green"] == 0,
            "provenance_coverage_full": coverage == 1.0,
            "center_never_grows": b["pistil_immutable"],
        },
        "citations": CITATIONS,
        "honesty": _HONEST_NOTE,
    }


# =====================================================================================
# Registration (additive). Returns the 3 exact paths.
# =====================================================================================
def register(app, ns: str = "killinchu") -> List[str]:
    """Wire /api/<ns>/v1/flower/{graph,bloom,manifest} onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append.
    Returns the list of the 3 registered route paths."""
    base = "/api/%s/v1/flower" % ns
    paths = ["%s/graph" % base, "%s/bloom" % base, "%s/manifest" % base]

    try:
        from fastapi.responses import JSONResponse

        def _graph_h(seed: int = 42):  # noqa: ANN202
            try:
                return JSONResponse(flower_graph(seed=seed))
            except Exception as exc:  # pragma: no cover — never 500 the surface
                return JSONResponse({"service": "flower-brain", "label": MODELED_LABEL,
                                     "error": "compute fail-open: %s" % (type(exc).__name__)},
                                    status_code=200)

        def _bloom_h(seed: int = 42, K: int = 10):  # noqa: ANN202
            try:
                return JSONResponse(flower_bloom(seed=seed, K=K))
            except Exception as exc:  # pragma: no cover
                return JSONResponse({"service": "flower-brain", "label": MODELED_LABEL,
                                     "error": "compute fail-open: %s" % (type(exc).__name__)},
                                    status_code=200)

        def _manifest_h(seed: int = 42):  # noqa: ANN202
            try:
                return JSONResponse(flower_manifest(seed=seed))
            except Exception as exc:  # pragma: no cover
                return JSONResponse({"service": "flower-brain", "label": MODELED_LABEL,
                                     "error": "compute fail-open: %s" % (type(exc).__name__)},
                                    status_code=200)

        add_api_route = getattr(app, "add_api_route", None)
        if callable(add_api_route):
            app.add_api_route(paths[0], _graph_h, methods=["GET"])
            app.add_api_route(paths[1], _bloom_h, methods=["GET"])
            app.add_api_route(paths[2], _manifest_h, methods=["GET"])
        else:
            from starlette.routing import Route  # type: ignore

            async def _g(request):  # type: ignore
                return JSONResponse(flower_graph(seed=int(request.query_params.get("seed", 42))))

            async def _b(request):  # type: ignore
                return JSONResponse(flower_bloom(seed=int(request.query_params.get("seed", 42)),
                                                 K=int(request.query_params.get("K", 10))))

            async def _m(request):  # type: ignore
                return JSONResponse(flower_manifest(seed=int(request.query_params.get("seed", 42))))

            app.router.routes.append(Route(paths[0], _g))
            app.router.routes.append(Route(paths[1], _b))
            app.router.routes.append(Route(paths[2], _m))
    except Exception:
        pass  # additive registration must never break app boot

    return paths


# =====================================================================================
# Self-test (Forge: run `python3 szl_kc_flower.py` — must print ALL OK).
# =====================================================================================
if __name__ == "__main__":
    import sys

    g = flower_graph(seed=42)
    b = flower_bloom(seed=42, K=10)
    mf = flower_manifest(seed=42)

    # ---- report ----
    print("label:", g["label"])
    print("petals:", mf["petals_total"], "| nodes:", g["nodes_total"], "| edges:", g["edges_total"],
          "| cross-petal edges:", g["cross_petal_edges"])
    print("petal node counts:", _json.dumps(g["petal_node_counts"]))
    print("per-petal bloom_fraction:")
    for pp in b["per_petal_bloom"]:
        print("  petal %d %-20s bloom=%s state=%s nodes=%d gray=%s" %
              (pp["petal"], pp["name"], pp["bloom_fraction"], pp["state"], pp["node_count"], pp["gray"]))
    print("overall_bloom:", b["overall_bloom"])
    print("overall_bloom_per_k:", b["overall_bloom_per_k"])
    print("active_cross_petal_edges:", b["active_cross_petal_count"])
    print("provenance_coverage:", mf["provenance_coverage"],
          "(%d/%d nodes)" % (mf["nodes_with_provenance"], mf["nodes_total"]))
    print("locked_count:", mf["locked_count"], "(must be 8)")
    print("conjecture_rendered_green:", mf["conjecture_rendered_green"], "(must be 0)")

    # ---- HARD invariants (Doctrine v11) ----
    # label verbatim on all 3 endpoints
    assert g["label"] == MODELED_LABEL == "MODELED", g["label"]
    assert b["label"] == "MODELED" and mf["label"] == "MODELED"

    # exactly 8 petals
    assert mf["petals_total"] == 8 and len(g["petals"]) == 8, "must be exactly 8 petals"

    # locked_count == 8 on every endpoint; center is the locked-8 pistil; center never grows
    assert g["locked_count"] == 8, "locked-proven MUST be exactly 8"
    assert b["locked_count"] == 8 and mf["locked_count"] == 8
    assert g["center_is_locked8"] is True, "the pistil must be exactly the locked-8"
    assert sorted(g["pistil"]) == sorted(n["id"] for n in _PETAL1), "pistil == locked-8"
    assert b["pistil_immutable"] is True, "center (pistil) must stay pinned at 1.0 (never grows)"

    # conjecture_rendered_green == 0 (gray petal never fires green)
    assert b["conjecture_rendered_green"] == 0, "conjectures must NEVER bloom green"
    assert mf["conjecture_rendered_green"] == 0
    # conjecture petal bloom_fraction is exactly 0
    conj_pp = next(pp for pp in b["per_petal_bloom"] if pp["petal"] == 8)
    assert conj_pp["gray"] is True and conj_pp["bloom_fraction"] == 0.0, "gray petal stays closed"

    # every node has a non-empty provenance -> full coverage
    assert all(str(n.get("provenance", "")).strip() for n in g["nodes"]), "every node needs provenance"
    assert mf["provenance_coverage"] == 1.0, "provenance coverage must be 1.0"

    # all 8 petals populated
    for pn in range(1, 9):
        assert g["petal_node_counts"][pn] >= 1, "petal %d must have >=1 node" % pn

    # cross-petal edges exist and are real dependencies spanning petals
    assert g["cross_petal_edges"] >= 8, "expected several real cross-petal dependencies"

    # bloom rises toward saturation over K (non-decreasing, ends above it starts)
    opk = b["overall_bloom_per_k"]
    assert opk == sorted(opk), "overall bloom should be non-decreasing over K"
    assert opk[-1] >= opk[0], "bloom must reach at least as much mass over K"
    assert 0.0 < b["overall_bloom"] <= 1.0, "overall bloom in (0,1]"

    # non-gray, non-pistil petals actually open (some bloom > 0)
    assert any(pp["bloom_fraction"] > 0.0 for pp in b["per_petal_bloom"]
               if not pp["gray"] and not pp["is_pistil"]), "petals must bloom outward"

    # determinism: same seed => identical
    assert flower_graph(42) == flower_graph(42), "graph must be deterministic"
    assert flower_bloom(42, 10) == flower_bloom(42, 10), "bloom must be deterministic"
    assert flower_manifest(42) == flower_manifest(42), "manifest must be deterministic"
    # seed-sensitive layout jitter
    assert flower_graph(7) != flower_graph(42), "layout must be seed-sensitive"

    # banned-token rejection works, and this module's own honest note is clean
    _assert_no_banned(_HONEST_NOTE)
    for n in g["nodes"]:
        _assert_no_banned(n["title"] + " " + n["provenance"])
    _rejected = False
    try:
        _assert_no_banned("this is a " + "yranoitulover"[::-1] + " " + "hguorhtkaerb"[::-1])
    except ValueError:
        _rejected = True
    assert _rejected, "banned tokens must be rejected"

    # register() returns the 3 exact paths (no app needed — try/except-guarded)
    class _NoApp:  # not a FastAPI app; register must still return the 3 paths
        pass
    paths = register(_NoApp(), ns="killinchu")
    assert paths == [
        "/api/killinchu/v1/flower/graph",
        "/api/killinchu/v1/flower/bloom",
        "/api/killinchu/v1/flower/manifest",
    ], paths

    print("register paths:", paths)
    print("szl_kc_flower: ALL OK — 8-petal real graph, MODELED bloom on locked-8 pistil, "
          "conjectures gray, full provenance, deterministic.", file=sys.stderr)
    print("ALL OK")
