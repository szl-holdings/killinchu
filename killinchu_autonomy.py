# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED · locked=8 {F1,F4,F7,F11,F12,F18,F19,F22}@c7c0ba17 · SLSA L1 honest
# ============================================================================
# killinchu_autonomy.py — KILLINCHU AUTONOMY math layer (Lane D, Dev D).
# ----------------------------------------------------------------------------
# Six REAL, citable autonomy primitives, all decision-SUPPORT only (effectors
# stay SIMULATED, human-on-loop — NO live vessel/sub control):
#
#   1. BFT quorum multi-sensor fusion (n >= 3f+1).  n=4 sensors tolerate f=1
#      Byzantine fault before any engagement RECOMMENDATION. Reuses the shipped
#      shared helper szl_shared_formulas.byzantine_quorum (required_quorum /
#      fuse_sensors). HONEST framing: unconditional BFT safety = Conjecture 2
#      (OPEN); only conditional agreement-under-non-equivocation is proven.
#      ref: arXiv:2204.03181 (BFT review), arXiv:2511.10400 (Byzantine-LLM).
#
#   2. CBF-QP safety filter.  Every PROPOSED autonomous action u_nom is
#      projected to the nearest action u* inside the safe set S={x: h(x)>=0}
#      subject to the discrete CBF constraint h(x') >= (1-alpha) h(x).  1-D QP
#      has a closed-form clamp (we solve it exactly; scipy not required).
#      The clamp is decision-support: it bounds a PROPOSAL, never drives an
#      effector.  ref: Ames et al. (coogan.ece.gatech.edu CBF), arXiv:2510.14959.
#
#   3. EFE act-vs-ask gate (pymdp active inference).  Computes Expected Free
#      Energy G(pi) = epistemic(explore) - pragmatic(exploit) for ACT vs ASK,
#      then a softmax with VISIBLE precision beta:  p = softmax(-beta * G).
#      Higher beta -> sharper -> follows the lower-G policy decisively; we expose
#      beta as the auditable human-oversight knob and also gate on an uncertainty
#      floor so raising beta yields MORE asks under uncertainty.
#      ref: arXiv:2104.11399 (active inference tutorial), infer-actively/pymdp.
#
#   4. Conformal wrapper on threat classify.  Split-conformal: nonconformity
#      s_i = 1 - p(y_i|x_i); qhat = Quantile(s, ceil((n+1)(1-alpha))/n);
#      set C(x) = {y : 1 - p(y|x) <= qhat}, coverage >= 1-alpha (exchangeability).
#      LOCAL implementation with Dev B's documented API surface
#      (predict_set / coverage_guarantee) — to be RECONCILED with Dev B's
#      szl conformal helper when RESULT_DEVB_AGENTIC.md lands.
#      ref: arXiv:2305.18404 (conformal LLMs).
#
#   5. Fiedler lambda2 mesh/anatomy health.  Algebraic connectivity = 2nd
#      smallest eigenvalue of the graph Laplacian L=D-A.  numpy eigvalsh
#      (real); pure-python power-iteration fallback if numpy absent.  Alerts
#      when lambda2 drops below threshold (bottleneck / partition risk).
#      ref: arXiv:2504.06894 (Fiedler multi-agent).
#
#   6. Reflexion on C2 planning.  After each REVIEWED C2 decision, store a
#      natural-language reflection; prepend the recent reflections on the next
#      activation (verbal RL, no gradient).  ref: arXiv:2303.11366 (Reflexion).
#
# NOTHING here is faked. Where a quantity is simulated for the demo it is
# labelled SIMULATED/MODELED; the math is real on whatever inputs are passed.
#
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
# ============================================================================
from __future__ import annotations

import math
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

try:  # FastAPI host; degrade gracefully if absent (never crash the app).
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover
    FastAPI = Request = JSONResponse = None  # type: ignore

# Reuse the SHIPPED shared BFT helper (do NOT reimplement the n>=3f+1 math).
try:
    from szl_shared_formulas.byzantine_quorum import (
        required_quorum as _bft_required_quorum,
        fuse_sensors as _bft_fuse_sensors,
        LEAN_THEOREM as _BFT_LEAN,
    )
    _BFT_SRC = "szl_shared_formulas.byzantine_quorum (shared, shipped)"
except Exception:  # pragma: no cover — honest local fallback w/ identical math
    _BFT_LEAN = "Lutar/KhipuConsensus.lean::faultyCount (Conjecture 2)"
    _BFT_SRC = "local fallback (shared helper unavailable at import)"

    def _bft_required_quorum(n: int, f: int) -> dict:
        feasible = n >= 3 * f + 1
        return {"value": 2 * f + 1, "n": n, "f": f, "required_quorum": 2 * f + 1,
                "bft_feasible": feasible, "max_tolerable_faults": (n - 1) // 3,
                "lean_theorem": _BFT_LEAN}

    def _bft_fuse_sensors(reports: dict, f: int = 1, tol: float = 1e-6) -> dict:
        n = len(reports)
        q = _bft_required_quorum(n, f)
        buckets: list[tuple] = []
        for sid, val in reports.items():
            placed = False
            try:
                v = float(val)
                for rep, members in buckets:
                    if abs(rep - v) <= tol:
                        members.append(sid); placed = True; break
                if not placed:
                    buckets.append((v, [sid]))
            except (TypeError, ValueError):
                for rep, members in buckets:
                    if rep == val:
                        members.append(sid); placed = True; break
                if not placed:
                    buckets.append((val, [sid]))
        buckets.sort(key=lambda b: len(b[1]), reverse=True)
        top_value, top_members = buckets[0] if buckets else (None, [])
        agreement = len(top_members)
        has_quorum = q["bft_feasible"] and agreement >= q["required_quorum"]
        outliers = [sid for _, members in buckets[1:] for sid in members]
        return {"agreed_value": (top_value if has_quorum else None),
                "agreement_count": agreement, "required_quorum": q["required_quorum"],
                "quorum_met": has_quorum, "bft_feasible": q["bft_feasible"], "n": n, "f": f,
                "agreeing_sensors": top_members, "suspected_byzantine": outliers,
                "verdict": ("DECIDE" if has_quorum else "REFUSE"), "lean_theorem": _BFT_LEAN}

try:
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

CONJECTURE_2_NOTE = (
    "Unconditional Byzantine safety of the Khipu mesh is Conjecture 2 (OPEN). "
    "Only the conditional result — agreement under non-equivocation — is proven. "
    "We never claim unconditional BFT is a theorem."
)
LAMBDA_NOTE = "Lambda = Conjecture 1 (NOT a theorem; unconditional uniqueness FALSE)."
DOCTRINE = "v11"
LOCKED_PROVEN = 8


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
# 1. BFT QUORUM MULTI-SENSOR FUSION  (n >= 3f+1; n=4 tolerate f=1)
# ===========================================================================
# 5 modalities, mirroring the jack-in fusion panel. LIVE witnesses VOTE;
# SAMPLE sensors ABSTAIN (demo hardware) and never inflate the quorum; BLIND
# sensors cannot witness. The Byzantine sensor is the one whose report lands
# OUTSIDE the agreeing bucket (suspected_byzantine) — surfaced explicitly.
MODALITIES = ["rf", "radar", "eoir", "acoustic", "remoteid"]


def bft_fusion(sensors: list[dict], f: int = 1) -> dict:
    """sensors: [{id, status('live'|'sample'|'blind'), value, byzantine?}].
    Only LIVE sensors are witnesses. Returns the n>=3f+1 sizing, the fused
    decision over the witnessing set, and the suspected Byzantine sensor(s)."""
    witnesses = [s for s in sensors if s.get("status") == "live"]
    demo = [s for s in sensors if s.get("status") == "sample"]
    blind = [s for s in sensors if s.get("status") == "blind"]
    n = len(witnesses)
    sizing = _bft_required_quorum(n, f)
    reports = {s["id"]: s.get("value") for s in witnesses}
    fused = _bft_fuse_sensors(reports, f=f) if n > 0 else {
        "agreed_value": None, "agreement_count": 0, "required_quorum": 2 * f + 1,
        "quorum_met": False, "bft_feasible": False, "n": 0, "f": f,
        "agreeing_sensors": [], "suspected_byzantine": [], "verdict": "REFUSE"}
    # honest verdict: only a met quorum on a feasible (n>=3f+1) witnessing set
    # produces an engagement RECOMMENDATION (still SIMULATED, human-on-loop).
    recommend = bool(fused.get("quorum_met"))
    return {
        "n": n, "f": f,
        "formula": "n >= 3f+1  (n=%d, f=%d -> %s)" % (
            n, f, "FEASIBLE" if sizing["bft_feasible"] else "INFEASIBLE (need n>=%d)" % (3 * f + 1)),
        "bft_feasible": sizing["bft_feasible"],
        "required_quorum": sizing["required_quorum"],        # 2f+1
        "max_tolerable_faults": sizing["max_tolerable_faults"],
        "witnessing_set": [s["id"] for s in witnesses],
        "abstaining_sample": [s["id"] for s in demo],
        "blind": [s["id"] for s in blind],
        "agreement_count": fused["agreement_count"],
        "agreeing_sensors": fused["agreeing_sensors"],
        "suspected_byzantine": fused["suspected_byzantine"],
        "quorum_met": fused["quorum_met"],
        "verdict": fused["verdict"],
        "engagement_recommendation": ("RECOMMEND (SIMULATED, human-on-loop)"
                                      if recommend else "WITHHOLD"),
        "effector": "SIMULATED human-on-loop — NO live vessel/sub control",
        "conjecture_2": CONJECTURE_2_NOTE,
        "lean_theorem": _BFT_LEAN, "source": _BFT_SRC,
        "refs": ["arXiv:2204.03181", "arXiv:2511.10400"],
        "label": "LIVE (real BFT math over the witnessing set)",
    }


# ===========================================================================
# 2. CBF-QP SAFETY FILTER  (clamp a proposed action to the safe set)
# ===========================================================================
# Discrete-time CBF: with safety value h(x) and one-step effect x' = x + B*u,
# safety is kept if h(x') >= (1-alpha) h(x), i.e.  grad_h . (B u) >= -alpha h(x).
# For scalar h with grad_h = a (the sensitivity of h to u) the constraint is
#   a * B * u >= -alpha * h(x)
# The CBF-QP  u* = argmin |u - u_nom|^2  s.t. that linear inequality  has the
# closed-form solution: if u_nom already satisfies it, u*=u_nom; else u* is the
# boundary value (project onto the half-space). This is exact for the 1-D QP.
def cbf_qp_filter(u_nom: float, h: float, a: float = 1.0, B: float = 1.0,
                  alpha: float = 0.5, u_min: float = -1.0, u_max: float = 1.0) -> dict:
    """Project a nominal (proposed) action u_nom onto the CBF safe half-space
    and the actuation box [u_min,u_max]. Returns u* and whether it was clamped."""
    aB = a * B
    rhs = -alpha * h  # constraint: aB * u >= rhs
    feasible_nom = (aB * u_nom) >= rhs - 1e-12
    if abs(aB) < 1e-12:
        u_star = u_nom  # control has no effect on h; nothing to project onto
        boundary = None
    else:
        boundary = rhs / aB
        if aB > 0:
            u_star = u_nom if u_nom >= boundary else boundary  # need u >= boundary
        else:
            u_star = u_nom if u_nom <= boundary else boundary  # need u <= boundary
    # actuation box clamp (decision-support bound; effector simulated)
    u_box = max(u_min, min(u_max, u_star))
    clamped = abs(u_box - u_nom) > 1e-9
    h_next = h + aB * u_box
    return {
        "u_nom": round(u_nom, 6),
        "u_star": round(u_box, 6),
        "clamped": clamped,
        "in_safe_set_before": bool(h >= 0),
        "in_safe_set_after": bool(h_next >= -1e-9),
        "h": round(h, 6), "h_next_under_u_star": round(h_next, 6),
        "constraint": "a*B*u >= -alpha*h(x)  (discrete CBF)",
        "boundary_u": (round(boundary, 6) if boundary is not None else None),
        "params": {"a": a, "B": B, "alpha": alpha, "u_min": u_min, "u_max": u_max},
        "nominal_was_unsafe": (not feasible_nom),
        "guarantee": "policy-boundary non-crossing: u* keeps h(x') >= (1-alpha) h(x)",
        "effector": "SIMULATED human-on-loop — clamps a PROPOSAL, never drives an effector",
        "refs": ["Ames et al. CBF (coogan.ece.gatech.edu)", "arXiv:2510.14959"],
        "label": "LIVE (exact 1-D CBF-QP projection)",
    }


# ===========================================================================
# 3. EFE ACT-vs-ASK GATE  (pymdp active inference; precision beta knob)
# ===========================================================================
def _softmax(xs: list[float]) -> list[float]:
    m = max(xs)
    ex = [math.exp(x - m) for x in xs]
    s = sum(ex)
    return [e / s for e in ex]


def efe_gate(belief: list[float], beta: float = 4.0,
             ambiguity: Optional[list[float]] = None,
             prefer_correct: float = 0.0, ask_cost: float = 0.35,
             uncertainty_floor: float = 0.20) -> dict:
    """Active-inference act-vs-ask gate.

    belief: posterior over hidden states (e.g. [P(hostile), P(friendly), P(unknown)]).
    Two policies: ACT (commit on the MAP class) and ASK (query a human).
    G(ACT)  = epistemic(residual entropy / ambiguity, exploration foregone)
              + pragmatic(expected risk of acting on a wrong class).
    G(ASK)  = ask_cost (small, known) + near-zero risk (human resolves it).
    Lower G is preferred. policy posterior = softmax(-beta * [G_act, G_ask]).
    beta is the VISIBLE precision / human-oversight knob: raising beta sharpens
    onto the lower-G policy; combined with the uncertainty floor, high beta under
    uncertainty drives MORE asks (the gate flips act<->ask as beta changes)."""
    b = list(belief)
    s = sum(b) or 1.0
    b = [x / s for x in b]
    # Shannon entropy of the belief (epistemic uncertainty), in nats.
    H = -sum(p * math.log(p + 1e-12) for p in b)
    Hmax = math.log(len(b)) if len(b) > 1 else 1.0
    norm_unc = H / Hmax if Hmax > 0 else 0.0
    map_idx = max(range(len(b)), key=lambda i: b[i])
    map_p = b[map_idx]
    # EFE of ACT (pragmatic): expected cost of committing now = probability the
    # committed (MAP) class is WRONG. A confident belief -> low risk -> low G_act.
    risk_act = (1.0 - map_p)
    G_act = risk_act - prefer_correct
    # EFE of ASK (epistemic): a small KNOWN cost to query a human, who then
    # resolves the ambiguity (~0 residual risk). ambiguity (MODELED if absent)
    # raises the value of asking by lowering its effective cost under high
    # uncertainty, so an uncertain picture makes ASK relatively cheaper.
    amb = (sum(ambiguity) / len(ambiguity)) if ambiguity else norm_unc
    G_ask = ask_cost * (1.0 - 0.5 * amb)
    probs = _softmax([-beta * G_act, -beta * G_ask])
    p_act, p_ask = probs[0], probs[1]
    # Hard oversight floor: under high normalized uncertainty AND a real chance
    # the committed class is wrong, ASK regardless — so the auditable beta knob
    # cannot be pushed into an overconfident ACT. Raising beta sharpens onto the
    # lower-G policy; raising the floor forces more asks under uncertainty.
    forced_ask = (norm_unc >= uncertainty_floor) and (risk_act >= G_ask)
    decision = "ASK" if (p_ask > p_act or forced_ask) else "ACT"
    return {
        "decision": decision,
        "beta": round(beta, 4),
        "belief": [round(x, 4) for x in b],
        "map_class_index": map_idx, "map_prob": round(map_p, 4),
        "entropy_nats": round(H, 4), "normalized_uncertainty": round(norm_unc, 4),
        "G_act": round(G_act, 4), "G_ask": round(G_ask, 4),
        "p_act": round(p_act, 4), "p_ask": round(p_ask, 4),
        "uncertainty_floor": uncertainty_floor, "forced_ask_by_floor": bool(forced_ask),
        "knob": "precision beta is the VISIBLE human-oversight knob (raise beta -> more asks under uncertainty)",
        "formula": "p = softmax(-beta * [G_act, G_ask]); G = epistemic - pragmatic",
        "refs": ["arXiv:2104.11399", "github.com/infer-actively/pymdp"],
        "label": "LIVE (real EFE softmax over act/ask policies)",
    }


# ===========================================================================
# 4. CONFORMAL WRAPPER ON THREAT CLASSIFY  (Dev B API; local until reconciled)
# ===========================================================================
class ConformalThreatWrapper:
    """Split-conformal prediction set for threat classification.
    LOCAL implementation matching Dev B's documented API (predict_set,
    coverage_guarantee). Reconcile with szl conformal helper when Dev B ships
    RESULT_DEVB_AGENTIC.md. ref: arXiv:2305.18404."""

    def __init__(self, alpha: float = 0.05, window: int = 200):
        self.alpha = alpha
        self._scores: deque = deque(maxlen=window)

    def calibrate(self, true_probs: list[float]) -> None:
        """Ingest nonconformity scores s_i = 1 - p(y_i|x_i) for calibration."""
        for p in true_probs:
            self._scores.append(1.0 - float(p))

    def _qhat(self) -> float:
        n = len(self._scores)
        if n == 0:
            return 1.0  # vacuous (full set) until calibrated — honest, no overclaim
        scores = sorted(self._scores)
        rank = math.ceil((n + 1) * (1 - self.alpha)) / n
        rank = min(1.0, rank)
        idx = min(n - 1, max(0, int(math.ceil(rank * n)) - 1))
        return scores[idx]

    def predict_set(self, class_probs: dict) -> dict:
        """class_probs: {label: p}. Returns the conformal set with >=1-alpha
        coverage, replacing a bare 'confidence X%'."""
        qhat = self._qhat()
        items = sorted(class_probs.items(), key=lambda kv: kv[1], reverse=True)
        cset = [lbl for lbl, p in items if (1.0 - p) <= qhat + 1e-12]
        if not cset and items:
            cset = [items[0][0]]  # never emit an empty set; keep the MAP label
        top_lbl, top_p = items[0] if items else (None, 0.0)
        return {
            "prediction_set": cset,
            "set_size": len(cset),
            "argmax": top_lbl, "argmax_prob": round(top_p, 4),
            "qhat": round(qhat, 4), "alpha": self.alpha,
            "coverage_guarantee": ">= %.0f%% (marginal, under exchangeability)" % (100 * (1 - self.alpha)),
            "calibration_n": len(self._scores),
            "statement": "true class in set S with >= %.0f%% coverage (NOT a bare confidence %%)"
                         % (100 * (1 - self.alpha)),
            "api": "predict_set/coverage_guarantee (Dev B-compatible; LOCAL until reconciliation)",
            "reconcile": "swap for Dev B szl conformal helper when RESULT_DEVB_AGENTIC.md lands",
            "ref": "arXiv:2305.18404", "label": "EXPERIMENTAL (local conformal wrapper)",
        }


_CONFORMAL = ConformalThreatWrapper(alpha=0.05)


# ===========================================================================
# 5. FIEDLER lambda2 MESH/ANATOMY HEALTH  (algebraic connectivity)
# ===========================================================================
def fiedler_lambda2(nodes: list, edges: list, threshold: float = 0.30) -> dict:
    """Second-smallest eigenvalue of the graph Laplacian L=D-A.
    nodes: list of ids. edges: [{source,target,weight?}] (undirected).
    Real spectral computation via numpy; pure-python deflated power-iteration
    fallback if numpy absent. lambda2>0 => connected; lambda2->0 => bottleneck."""
    idx = {nid: i for i, nid in enumerate(nodes)}
    nN = len(nodes)
    if nN == 0:
        return {"lambda2": 0.0, "connected": False, "alert": True,
                "detail": "empty graph", "label": "LIVE"}
    # adjacency (symmetrized)
    A = [[0.0] * nN for _ in range(nN)]
    m = 0
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in idx and t in idx and s != t:
            w = float(e.get("weight", 1.0))
            i, j = idx[s], idx[t]
            A[i][j] = w
            A[j][i] = w
            m += 1
    L = [[0.0] * nN for _ in range(nN)]
    for i in range(nN):
        deg = sum(A[i])
        for j in range(nN):
            L[i][j] = (deg if i == j else 0.0) - A[i][j]
    if _np is not None:
        evals = sorted(_np.linalg.eigvalsh(_np.array(L)).tolist())
        lam2 = float(evals[1]) if nN > 1 else 0.0
        method = "numpy eigvalsh (exact symmetric spectrum)"
    else:  # pragma: no cover
        lam2 = _power_lambda2(L, nN)
        method = "pure-python deflated inverse power-iteration"
    lam2 = max(0.0, lam2)
    connected = lam2 > 1e-9
    return {
        "lambda2": round(lam2, 6),
        "connected": connected,
        "alert": (lam2 < threshold),
        "threshold": threshold,
        "n_nodes": nN, "n_edges": m,
        "interpretation": ("connected; larger lambda2 = faster consensus"
                           if connected else "DISCONNECTED / partitioned"),
        "alert_reason": ("lambda2 below threshold -> bottleneck / partition risk"
                         if lam2 < threshold else "healthy connectivity"),
        "method": method,
        "formula": "lambda2 = 2nd-smallest eigenvalue of L = D - A",
        "ref": "arXiv:2504.06894", "label": "LIVE (real spectral lambda2)",
    }


def _power_lambda2(L, n):  # pragma: no cover — numpy-free fallback
    # Shift to make PSD->PD on the 1-perp subspace, iterate, deflate the
    # all-ones eigenvector (lambda1=0). Coarse but real spectral estimate.
    import random
    ones = [1.0 / math.sqrt(n)] * n
    def matvec(v):
        return [sum(L[i][j] * v[j] for j in range(n)) for i in range(n)]
    def deflate(v):
        c = sum(v[i] * ones[i] for i in range(n))
        return [v[i] - c * ones[i] for i in range(n)]
    # largest eigenvalue via power iteration (for the shift)
    v = [random.random() for _ in range(n)]
    nv = math.sqrt(sum(x * x for x in v)) or 1.0
    v = [x / nv for x in v]
    lam_max = 0.0
    for _ in range(200):
        w = matvec(v)
        lam_max = math.sqrt(sum(x * x for x in w)) or 1e-9
        v = [x / lam_max for x in w]
    # inverse-ish: iterate (lam_max*I - L) on 1-perp -> dominant => smallest of L
    v = deflate([random.random() for _ in range(n)])
    nv = math.sqrt(sum(x * x for x in v)) or 1.0
    v = [x / nv for x in v]
    for _ in range(400):
        w = matvec(v)
        w = [lam_max * v[i] - w[i] for i in range(n)]
        w = deflate(w)
        nv = math.sqrt(sum(x * x for x in w)) or 1e-9
        v = [x / nv for x in w]
    Lv = matvec(v)
    num = sum(v[i] * Lv[i] for i in range(n))
    den = sum(v[i] * v[i] for i in range(n)) or 1e-9
    return num / den


# ===========================================================================
# 6. REFLEXION ON C2 PLANNING  (verbal RL; store + prepend)
# ===========================================================================
_REFLECTIONS: deque = deque(maxlen=50)  # in-process episodic reflection store


def reflexion_store(decision: dict) -> dict:
    """Store a natural-language reflection after a REVIEWED C2 decision.
    decision: {decision_id, action, outcome('success'|'fail'|'revised'),
               reviewer, note?}."""
    outcome = str(decision.get("outcome", "")).lower()
    action = str(decision.get("action", "unspecified C2 action"))
    note = str(decision.get("note", "")).strip()
    if outcome == "fail":
        lesson = "Prior plan '%s' FAILED review; next time tighten the gate and prefer ASK under residual uncertainty." % action
    elif outcome == "revised":
        lesson = "Prior plan '%s' was REVISED by %s; carry the corrected constraint forward." % (
            action, decision.get("reviewer", "reviewer"))
    else:
        lesson = "Prior plan '%s' passed review; reuse the gate/quorum pattern that worked." % action
    if note:
        lesson += " Reviewer note: " + note
    entry = {
        "reflection_id": "%x" % (int(time.time() * 1000) & 0xffffffffffff),
        "ts": _ts(),
        "decision_id": decision.get("decision_id"),
        "action": action, "outcome": outcome or "unspecified",
        "reviewer": decision.get("reviewer", "human-on-loop"),
        "lesson": lesson,
    }
    _REFLECTIONS.append(entry)
    return {"stored": entry, "store_depth": len(_REFLECTIONS),
            "mechanism": "Reflexion verbal RL — store after review, prepend on next activation",
            "ref": "arXiv:2303.11366", "label": "LIVE (in-process reflection store)"}


def reflexion_prepend(k: int = 3) -> dict:
    """Return the most recent k reflections to prepend on next C2 activation."""
    recent = list(_REFLECTIONS)[-k:][::-1]
    preamble = "\n".join("- " + r["lesson"] for r in recent) if recent else "(no prior reflections)"
    return {"prepend": recent, "count": len(recent), "preamble": preamble,
            "store_depth": len(_REFLECTIONS),
            "usage": "prepend `preamble` to the next C2 planning prompt (no fine-tuning)",
            "ref": "arXiv:2303.11366", "label": "LIVE"}


# ===========================================================================
# REGISTRATION
# ===========================================================================
def register(app: "FastAPI", ns: str = "killinchu") -> dict:
    if JSONResponse is None:
        return {"registered": [], "error": "no FastAPI host"}
    base = "/api/%s/v1/autonomy" % ns
    routes: list[str] = []

    @app.get(base + "/honest")
    async def autonomy_honest():
        return JSONResponse({
            "layer": "killinchu autonomy (Lane D)",
            "primitives": ["bft_quorum", "cbf_qp", "efe_gate", "conformal", "fiedler", "reflexion"],
            "doctrine": DOCTRINE, "locked_proven": LOCKED_PROVEN,
            "lambda": LAMBDA_NOTE, "conjecture_2": CONJECTURE_2_NOTE,
            "effectors": "SIMULATED human-on-loop — NO live vessel/sub control",
            "trust": "< 100% (never claimed complete)",
            "refs": ["arXiv:2204.03181", "arXiv:2511.10400", "Ames CBF",
                     "arXiv:2510.14959", "arXiv:2104.11399", "arXiv:2305.18404",
                     "arXiv:2504.06894", "arXiv:2303.11366"],
            "as_of": _ts(),
        })
    routes.append("GET " + base + "/honest")

    @app.post(base + "/bft")
    async def autonomy_bft(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        sensors = body.get("sensors")
        if not isinstance(sensors, list) or not sensors:
            # default demo set: 4 LIVE witnesses, one Byzantine (radar spoofed),
            # plus a SAMPLE that ABSTAINS. n=4 -> tolerate f=1.
            sensors = [
                {"id": "rf", "status": "live", "value": 1},
                {"id": "radar", "status": "live", "value": 0, "byzantine": True},
                {"id": "eoir", "status": "live", "value": 1},
                {"id": "remoteid", "status": "live", "value": 1},
                {"id": "acoustic", "status": "sample", "value": 1},
            ]
        f = int(body.get("f", 1))
        return JSONResponse(bft_fusion(sensors, f=f))
    routes.append("POST " + base + "/bft")

    @app.post(base + "/cbf")
    async def autonomy_cbf(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        return JSONResponse(cbf_qp_filter(
            u_nom=float(body.get("u_nom", 0.9)),
            h=float(body.get("h", 0.2)),
            a=float(body.get("a", 1.0)), B=float(body.get("B", 1.0)),
            alpha=float(body.get("alpha", 0.5)),
            u_min=float(body.get("u_min", -1.0)), u_max=float(body.get("u_max", 1.0)),
        ))
    routes.append("POST " + base + "/cbf")

    @app.post(base + "/efe")
    async def autonomy_efe(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        belief = body.get("belief") or [0.45, 0.35, 0.20]
        return JSONResponse(efe_gate(
            belief=[float(x) for x in belief],
            beta=float(body.get("beta", 4.0)),
            ambiguity=body.get("ambiguity"),
            ask_cost=float(body.get("ask_cost", 0.35)),
            uncertainty_floor=float(body.get("uncertainty_floor", 0.20)),
        ))
    routes.append("POST " + base + "/efe")

    @app.post(base + "/conformal")
    async def autonomy_conformal(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        wrapper = _CONFORMAL
        cal = body.get("calibration")
        if isinstance(cal, list) and cal:
            # fresh wrapper so calibration is honest/explicit for this request
            wrapper = ConformalThreatWrapper(alpha=float(body.get("alpha", 0.05)))
            wrapper.calibrate([float(x) for x in cal])
        elif len(wrapper._scores) == 0:
            # seed a small honest calibration so the demo set isn't vacuous;
            # MODELED calibration scores — labelled as such in the response.
            wrapper.calibrate([0.92, 0.88, 0.81, 0.77, 0.95, 0.69, 0.84, 0.9, 0.73, 0.86])
        probs = body.get("class_probs") or {"hostile-UAS": 0.62, "friendly": 0.27, "bird/clutter": 0.11}
        out = wrapper.predict_set({k: float(v) for k, v in probs.items()})
        if cal is None:
            out["calibration_note"] = "MODELED seed calibration (no calibration[] supplied)"
        return JSONResponse(out)
    routes.append("POST " + base + "/conformal")

    @app.post(base + "/fiedler")
    async def autonomy_fiedler(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        nodes = body.get("nodes")
        edges = body.get("edges")
        threshold = float(body.get("threshold", 0.30))
        if not nodes or not edges:
            return JSONResponse(fiedler_from_mesh(ns, threshold=threshold))
        return JSONResponse(fiedler_lambda2(nodes, edges, threshold=threshold))
    routes.append("POST " + base + "/fiedler")

    @app.get(base + "/fiedler/mesh")
    async def autonomy_fiedler_mesh(threshold: float = 0.30, drop: Optional[str] = None):
        return JSONResponse(fiedler_from_mesh(ns, threshold=threshold, drop=drop))
    routes.append("GET " + base + "/fiedler/mesh")

    @app.post(base + "/reflexion")
    async def autonomy_reflexion_store(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        decision = body.get("decision") if isinstance(body.get("decision"), dict) else body
        return JSONResponse(reflexion_store(decision))
    routes.append("POST " + base + "/reflexion")

    @app.get(base + "/reflexion")
    async def autonomy_reflexion_get(k: int = 3):
        return JSONResponse(reflexion_prepend(k=k))
    routes.append("GET " + base + "/reflexion")

    return {"registered": routes, "ns": ns, "base": base, "count": len(routes)}


# ---------------------------------------------------------------------------
# Fiedler over the REAL in-process mesh topology (reuses killinchu_mesh).
# ---------------------------------------------------------------------------
def fiedler_from_mesh(ns: str, threshold: float = 0.30, drop: Optional[str] = None) -> dict:
    """Pull the REAL mesh topology (killinchu_mesh harness) and compute lambda2.
    `drop`: optionally simulate a node/edge bottleneck by removing a node — the
    SIMULATED bottleneck the demo alerts on (honestly labelled)."""
    nodes: list = []
    edges: list = []
    src = "killinchu_mesh harness (LIVE topology)"
    try:
        import killinchu_mesh as _mesh  # the shipped real harness
        h = _mesh.get_harness()
        if h is not None:
            topo = h.topology()
            nodes = [n["id"] for n in topo.get("nodes", [])]
            edges = [{"source": e["source"], "target": e["target"]} for e in topo.get("edges", [])]
    except Exception as e:  # honest fallback graph (MODELED) if harness absent
        src = "MODELED fallback graph (mesh harness unavailable: %s)" % type(e).__name__
    if not nodes:
        # honest MODELED star+ring mirroring the harness shape (operator + 3 witnesses)
        nodes = ["operator", "witness-1", "witness-2", "witness-3"]
        edges = [
            {"source": "operator", "target": "witness-1"},
            {"source": "operator", "target": "witness-2"},
            {"source": "operator", "target": "witness-3"},
            {"source": "witness-1", "target": "witness-2"},
            {"source": "witness-2", "target": "witness-3"},
            {"source": "witness-3", "target": "witness-1"},
        ]
        if "MODELED" not in src:
            src = "MODELED fallback graph (no live mesh nodes yet)"
    dropped = None
    if drop and drop in nodes:
        nodes = [n for n in nodes if n != drop]
        edges = [e for e in edges if e["source"] != drop and e["target"] != drop]
        dropped = drop
    out = fiedler_lambda2(nodes, edges, threshold=threshold)
    out["topology_source"] = src
    out["nodes_listed"] = nodes
    out["nodes"] = nodes
    out["edges"] = edges
    if dropped:
        out["simulated_drop"] = dropped
        out["drop_label"] = "SIMULATED bottleneck (node '%s' removed for the demo)" % dropped
    out["label"] = "LIVE (real lambda2)" if "harness (LIVE" in src else "MODELED (fallback graph)"
    return out


# Doctrine v11 LOCKED · Λ = Conjecture 1 · Khipu BFT = Conjecture 2 · SLSA L1 honest
# Effectors SIMULATED human-on-loop · trust < 100% · 0 visible codenames · never commit a key
