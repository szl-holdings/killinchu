# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# killinchu.lambda_calc — REAL Λ computation for the edge organ.
#
# Λ is the SZL trust aggregator.  This module computes a verdict score in [0, 1]
# from a vector of trust-axis scores, gated by a McAllester PAC-Bayes upper bound
# on the generalisation gap of the per-axis estimators.  NO MOCKS, NO SHORTCUTS:
# every number below is produced by the formulas, never hard-coded.
#
# DOCTRINE HONESTY:
#   - Λ remains **Conjecture 1**, NOT a theorem.  `lambda_aggregate` (weighted
#     geometric mean) is PROVEN monotone/homogeneous (A1–A4) but the UNIQUENESS
#     of the aggregator is an open CAUCHY_ND sorry — we never claim otherwise.
#   - The PAC-Bayes term is a genuine statistical *upper bound* on risk; it is a
#     bound, not a guarantee.  We surface it explicitly.
#
# References (thesis v22, ch. PAC-Bayes edge admission):
#   McAllester (1999) "PAC-Bayesian Model Averaging"; Maurer (2004) bound:
#       KL(emp_risk || true_risk) <= ( KL(Q||P) + ln(2 sqrt(n)/delta) ) / n
#   We invert the binary-KL bound to an additive penalty kl_inv() and subtract it
#   from the empirical trust to obtain a *certified-floor* Λ.
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Sequence

# 13 canonical trust axes (sacred ×2 floor .95, structural ×7 floor .90,
# introspection ×4 / HUKLLA floor .90).  Mirror of szl_formulas axis taxonomy.
AXIS_NAMES = (
    "soundness", "calibration", "robustness", "provenance", "consent",
    "reversibility", "transparency", "fairness", "containment", "attestation",
    "freshness", "authority", "auditability",
)
# Sacred axes carry double weight (they gate hard).
_SACRED = {"soundness", "containment"}
LAMBDA_FLOOR = 0.70  # canonical edge-admission floor


def lambda_aggregate(axes: Sequence[float], weights: Sequence[float] | None = None) -> float:
    """Weighted GEOMETRIC mean over [0,1] axis scores — the canonical Λ form.

    PROVEN A1 monotone, A2 homogeneous, A3 idempotent, A4 bounded (Lean A1–A4).
    UNIQUENESS = Conjecture 1 (open CAUCHY_ND sorry).  Geometric mean => one zero
    axis drives Λ to 0 (no averaging away a hard failure)."""
    if not axes:
        raise ValueError("lambda_aggregate: empty axis vector")
    if any((a < 0.0 or a > 1.0) for a in axes):
        raise ValueError("lambda_aggregate: axis scores must lie in [0,1]")
    if weights is None:
        weights = [2.0 if AXIS_NAMES[i] in _SACRED else 1.0
                   for i in range(len(axes))] if len(axes) == len(AXIS_NAMES) \
                  else [1.0] * len(axes)
    if len(weights) != len(axes):
        raise ValueError("lambda_aggregate: weights/axes length mismatch")
    w_sum = float(sum(weights))
    if w_sum <= 0:
        raise ValueError("lambda_aggregate: non-positive weight sum")
    # geometric mean = exp( sum w_i ln x_i / sum w_i ); clamp ln(0) honestly.
    acc = 0.0
    for x, w in zip(axes, weights):
        if x <= 0.0:
            return 0.0  # hard-fail axis collapses Λ — by design.
        acc += w * math.log(x)
    return math.exp(acc / w_sum)


def kl_bernoulli(q: float, p: float) -> float:
    """Binary KL divergence KL(q || p) in nats. Used by the PAC-Bayes inversion."""
    eps = 1e-12
    q = min(max(q, eps), 1 - eps)
    p = min(max(p, eps), 1 - eps)
    return q * math.log(q / p) + (1 - q) * math.log((1 - q) / (1 - p))


def kl_inverse_upper(emp: float, bound: float) -> float:
    """Largest p in [emp,1] with KL(emp || p) <= bound (Maurer/Langford inversion).

    Solved by bisection — a real numeric solve, not a closed-form approximation."""
    if bound <= 0:
        return emp
    lo, hi = emp, 1.0
    for _ in range(60):  # 60 bisection steps => ~1e-18 precision
        mid = 0.5 * (lo + hi)
        if kl_bernoulli(emp, mid) > bound:
            hi = mid
        else:
            lo = mid
    return lo


def pac_bayes_penalty(n: int, kl_qp: float, delta: float = 0.05) -> float:
    """McAllester/Maurer PAC-Bayes complexity term: (KL(Q||P)+ln(2√n/δ))/n.

    n   = number of telemetry observations fused into this verdict
    kl_qp = KL(posterior || prior) over the axis-estimator weights (nats)
    delta = confidence parameter (default 95%)."""
    if n <= 0:
        raise ValueError("pac_bayes_penalty: n must be positive")
    if delta <= 0 or delta >= 1:
        raise ValueError("pac_bayes_penalty: delta in (0,1)")
    return (kl_qp + math.log(2.0 * math.sqrt(n) / delta)) / n


@dataclass
class LambdaVerdict:
    lambda_value: float          # certified-floor Λ in [0,1]
    lambda_empirical: float      # raw weighted geo-mean (pre-PAC-Bayes)
    pac_bayes_penalty: float     # complexity term (nats)
    certified_floor: float       # KL-inverted lower confidence floor
    decision: str                # ALLOW | REVIEW | DENY
    n_observations: int
    delta: float
    axes: dict = field(default_factory=dict)
    doctrine: str = "v11"
    lambda_status: str = "Conjecture 1 — NOT a theorem (open CAUCHY_ND sorry)"

    def to_dict(self) -> dict:
        return {
            "lambda_value": round(self.lambda_value, 6),
            "lambda_empirical": round(self.lambda_empirical, 6),
            "pac_bayes_penalty": round(self.pac_bayes_penalty, 6),
            "certified_floor": round(self.certified_floor, 6),
            "decision": self.decision,
            "n_observations": self.n_observations,
            "delta": self.delta,
            "axes": {k: round(v, 4) for k, v in self.axes.items()},
            "lambda_floor": LAMBDA_FLOOR,
            "doctrine": self.doctrine,
            "lambda_status": self.lambda_status,
            "honesty": ("Λ is a PAC-Bayes *certified-floor* lower confidence bound, "
                        "not a guarantee. Λ uniqueness is Conjecture 1."),
        }


def compute_lambda(axis_scores: dict[str, float], n_observations: int,
                   kl_qp: float = 0.5, delta: float = 0.05) -> LambdaVerdict:
    """Full edge Λ pipeline: weighted geo-mean → PAC-Bayes certified floor → decision.

    axis_scores : {axis_name: score in [0,1]} measured from telemetry.
    n_observations : count of fused telemetry samples (drives the bound tightness).
    kl_qp : KL(posterior||prior) of the axis-estimator ensemble (nats).
    """
    names = list(axis_scores.keys())
    vals = [axis_scores[k] for k in names]
    emp = lambda_aggregate(vals,
                           weights=[2.0 if n in _SACRED else 1.0 for n in names])
    penalty = pac_bayes_penalty(n_observations, kl_qp, delta)
    # Certified floor: invert binary-KL bound from the empirical Λ downward.
    # We bound the *risk* (1-emp) upward then map back to a trust floor.
    risk_upper = kl_inverse_upper(1.0 - emp, penalty)
    floor = max(0.0, 1.0 - risk_upper)
    lam = min(emp, floor)  # report the conservative (certified) value
    if lam >= 0.90:
        decision = "ALLOW"
    elif lam >= LAMBDA_FLOOR:
        decision = "REVIEW"
    else:
        decision = "DENY"
    return LambdaVerdict(
        lambda_value=lam, lambda_empirical=emp, pac_bayes_penalty=penalty,
        certified_floor=floor, decision=decision, n_observations=n_observations,
        delta=delta, axes=axis_scores,
    )
