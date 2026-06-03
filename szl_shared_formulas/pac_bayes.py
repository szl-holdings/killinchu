#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""PAC-Bayes (Catoni) verdict-confidence bound — real edge use.

Killinchu emits an edge verdict Λ over noisy multi-sensor telemetry. The empirical Λ
(observed agreement rate over the sensor fusion window) is only a sample estimate of the
true verdict reliability. The Catoni PAC-Bayes bound gives a high-probability UPPER bound
on the true risk (= 1 − reliability) so the edge can attach an honest confidence interval
to every verdict instead of over-trusting a small window.

Published form (thesis_v22.pdf §2 formula table — "PAC-Bayes (Catoni/McAllester)"):
    R(Q) ≤ R̂_S(Q) + sqrt( (KL(Q‖P) + ln(2·sqrt(n)/δ)) / (2n) )

This is the McAllester/Bégin form (Bégin 2016 Cor. 6). Catoni (2007) gives the tighter
inverse-KL / exponential-moment localisation; we expose both the additive McAllester slack
(closed form, default) and a numeric Catoni inverse-binary-KL bound (tighter, monotone).

A. McAllester, "PAC-Bayesian model averaging", COLT 1999; Machine Learning 51(1):5–21 (2003).
O. Catoni, "PAC-Bayesian Supervised Classification", IMS Lecture Notes 56 (2007).

Lean theorem: ``Lutar/PACBayes.lean :: pacBayesBound_eq_add_slack`` (L165, sorry-free:
the bound equals empirical risk + the slack term) and ``pacBayesBound_mono_kl`` (L102,
monotone in KL). Permalink pinned at commit abd58d1.

CITATION: thesis_v22.pdf §2  ·  LEAN: Lutar/PACBayes.lean::pacBayesBound_eq_add_slack
"""
from __future__ import annotations

import math

CITATION = "thesis_v22.pdf §2"
LEAN_THEOREM = "Lutar/PACBayes.lean::pacBayesBound_eq_add_slack"
LEAN_PERMALINK = (
    "https://github.com/szl-holdings/lutar-lean/blob/"
    "abd58d159f1bdb79a017d71a6b94ab160ead8d9d/Lutar/PACBayes.lean#L165"
)


def mcallester_slack(n: int, kl: float, delta: float) -> float:
    """Additive McAllester/Bégin slack: sqrt((KL + ln(2·sqrt(n)/δ)) / (2n))."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not (0.0 < delta < 1.0):
        raise ValueError("delta must be in (0,1)")
    if kl < 0.0:
        raise ValueError("KL must be non-negative")
    return math.sqrt((kl + math.log(2.0 * math.sqrt(n) / delta)) / (2.0 * n))


def _kl_binary(q: float, p: float) -> float:
    """KL(q‖p) for Bernoulli params, with safe clamping."""
    eps = 1e-12
    q = min(max(q, eps), 1.0 - eps)
    p = min(max(p, eps), 1.0 - eps)
    return q * math.log(q / p) + (1.0 - q) * math.log((1.0 - q) / (1.0 - p))


def catoni_inverse_kl(emp_risk: float, n: int, kl: float, delta: float) -> float:
    """Tighter Catoni-style bound: largest p with kl(emp_risk‖p) ≤ (KL+ln(2√n/δ))/n.

    Solved by bisection (kl(q‖·) is strictly increasing in p for p>q). Returns the
    high-probability upper bound on the true risk. Monotone, real numeric solve, no mock.
    """
    if not (0.0 <= emp_risk <= 1.0):
        raise ValueError("emp_risk must be in [0,1]")
    rhs = (kl + math.log(2.0 * math.sqrt(n) / delta)) / n
    lo, hi = emp_risk, 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _kl_binary(emp_risk, mid) <= rhs:
            lo = mid
        else:
            hi = mid
    return lo


def bound(emp_risk: float, n: int, kl: float = 0.0, delta: float = 0.05,
          method: str = "mcallester") -> dict:
    """Compute the PAC-Bayes verdict-risk upper bound. Honest schema.

    emp_risk : empirical risk over the fusion window (= 1 − observed reliability).
    n        : number of telemetry samples in the window.
    kl       : KL(posterior‖prior) over verdict policies (0 ⇒ prior == posterior).
    delta    : confidence parameter (bound holds w.p. ≥ 1−δ).
    """
    slack = mcallester_slack(n, kl, delta)
    mcallester = min(1.0, emp_risk + slack)
    catoni = catoni_inverse_kl(emp_risk, n, kl, delta)
    chosen = catoni if method == "catoni" else mcallester
    confidence = max(0.0, 1.0 - chosen)
    return {
        "value": round(chosen, 6),
        "risk_upper_bound": round(chosen, 6),
        "confidence_lower_bound": round(confidence, 6),
        "empirical_risk": round(emp_risk, 6),
        "slack_mcallester": round(slack, 6),
        "bound_mcallester": round(mcallester, 6),
        "bound_catoni_invkl": round(catoni, 6),
        "n": n,
        "kl": kl,
        "delta": delta,
        "method": method,
        "citation": CITATION,
        "lean_theorem": LEAN_THEOREM,
    }


__all__ = ["bound", "mcallester_slack", "catoni_inverse_kl", "CITATION", "LEAN_THEOREM",
           "LEAN_PERMALINK"]

# Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem)
# SLSA L1 honest + L2 attested (public Sigstore+Rekor) where slsa-verifier confirms.
