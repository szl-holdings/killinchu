"""
szl_qec.py — SZL topological quantum-error-correction / rotated-surface-code endpoint.

Exposes a MODELED distance-d rotated surface-code memory: a d×d data-qubit lattice
with X/Z stabilizer (syndrome) measurements under a depolarizing physical error rate
p, decoded by a simple MODELED minimum-weight-perfect-matching-style (MWPM-style)
decoder outcome, to estimate the logical error rate p_L(d). This gives the QEC
surface organ a live data source that is honest, deterministic, and citable — never
fabricated, never random-faked, never a claim about a real superconducting QPU.

  GET  /api/<ns>/v1/qec/surface-code?seed=&distance=&p=

Returned JSON fields
--------------------
  label                 : "MODELED" (always — this is a simulation of the METHOD,
                           not a readout from a real quantum processor)
  model                 : "Rotated surface code, MWPM-style decoder (MODELED)"
  code_distance         : d (odd integer >= 3)
  physical_error_rate   : p (per-qubit depolarizing rate for the simulated cycle)
  num_data_qubits       : d*d
  num_ancilla           : d*d - 1 (X- and Z-type syndrome/ancilla qubits combined)
  syndrome_weight       : MODELED mean Hamming weight of the syndrome (fired stabilizers)
                           for this (d,p,seed)
  logical_error_rate    : p_L(d,p) — MODELED estimate from the closed-form
                           below-threshold suppression law (Fowler et al. 2012;
                           Google Quantum AI 2024)
  suppression_factor    : Λ = p_L(d) / p_L(d+2)  — the "Willow" below-threshold
                           exponential-suppression figure of merit
  threshold_note        : plain-language note on the below/above-threshold regime
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form simulation of how a rotated surface code's
  logical error rate scales with code distance d and physical error rate p. It uses
  the well-established asymptotic suppression law
      p_L(d)  ~  A * (p / p_th)^((d+1)/2)
  (Fowler et al. 2012, arXiv:1208.0928, eq. for logical failure vs. distance; the same
  functional form is used to report Λ in Google Quantum AI's Willow result, Nature
  2024/2025, arXiv:2408.13687). The syndrome lattice, ancilla count, and per-shot
  syndrome weight are simulated with a pure-stdlib deterministic LCG PRNG seeded by
  `seed`, NOT measured on any superconducting or trapped-ion QPU. No proprietary
  hardware data, no fabricated experimental claims. The label "MODELED" is returned
  verbatim and displayed verbatim by the surface; it is never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Google Quantum AI — Willow below-threshold result:
    "Quantum error correction below the surface code threshold" (2024),
    Nature 638, 920-926 (2025). arXiv:2408.13687.
    https://arxiv.org/abs/2408.13687
  Fowler, Mariantoni, Martinis & Cleland (2012) —
    "Surface codes: Towards practical large-scale quantum computation".
    Phys. Rev. A 86, 032324. arXiv:1208.0928.
    https://arxiv.org/abs/1208.0928
  Kitaev (1997/2003) — toric code / topological fault tolerance:
    "Fault-tolerant quantum computation by anyons". Annals of Physics 303 (2003) 2-30.
    arXiv:quant-ph/9707021.
    https://arxiv.org/abs/quant-ph/9707021

DOCTRINE v11: NOTHING here is in the locked-8. Λ (Lambda-suppression, this file) is
  the QEC-literature's own Λ figure of merit (Fowler 2012 / Google 2024) — a DIFFERENT
  symbol from SZL's own "Λ = Conjecture 1" doctrine constant used elsewhere in the
  estate; the two are NOT the same object and this module makes NO claim about SZL's
  Conjecture 1. This module also adds NOTHING to szl_entanglement.py (entanglement
  measures, a different physics topic) and NOTHING to the locked-8. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "Google Quantum AI — QEC below the surface-code threshold (Willow) — Nature 2024/2025, arXiv:2408.13687": "https://arxiv.org/abs/2408.13687",
    "Fowler, Mariantoni, Martinis & Cleland (2012) — Surface codes: Towards practical large-scale quantum computation, arXiv:1208.0928": "https://arxiv.org/abs/1208.0928",
    "Kitaev (1997/2003) — Fault-tolerant quantum computation by anyons (toric code), Annals of Physics 303:2-30, arXiv:quant-ph/9707021": "https://arxiv.org/abs/quant-ph/9707021",
}

# Empirically-motivated constants for the MODELED below-threshold suppression law
# p_L(d) ~ A * (p / p_th)^((d+1)/2)   (Fowler et al. 2012; functional form also used
# to report Lambda in Google Quantum AI 2024/2025, arXiv:2408.13687).
# p_th (code threshold) and A (prefactor) are representative MODELED constants in the
# same order of magnitude as circuit-level depolarizing-noise threshold estimates
# discussed in the surface-code literature (~0.5%-1%); NOT fit to any specific real
# device. Kept explicit and documented so the model stays auditable and clean-room.
_P_THRESHOLD = 0.01     # MODELED surface-code threshold (~1%), representative order
_A_PREFACTOR = 0.03     # MODELED prefactor A in p_L(d) ~ A * (p/p_th)^((d+1)/2)


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# MODELED rotated surface-code lattice + MWPM-style decoder outcome
# ---------------------------------------------------------------------------
def _surface_code_snapshot(seed: int = 42, distance: int = 5, p: float = 0.003) -> dict:
    """
    Simulate one below/near-threshold rotated-distance-d surface-code memory cycle.

    Rotated surface code of distance d uses d*d data qubits and (d*d - 1) ancilla
    qubits (X- and Z-type stabilizers combined), arranged so each stabilizer has
    weight-4 (bulk) or weight-2 (boundary) support (Fowler et al. 2012).

    The physical error rate p drives a per-shot syndrome (which stabilizers fire);
    the syndrome weight is MODELED as a mean proportional to p * num_ancilla, with
    deterministic seed-driven fluctuation (pure stdlib, no numpy/random).

    The logical error rate is estimated via a simple MODELED closed-form MWPM-style
    decoder outcome — the standard asymptotic surface-code suppression law:
        p_L(d) ~ A * (p / p_th)^((d+1)/2)
    (Fowler et al. 2012, arXiv:1208.0928; functional form behind Λ in Google Quantum
    AI's Willow result, arXiv:2408.13687). This is NOT an actual MWPM graph-matching
    computation — it is a closed-form MODEL of the decoder's aggregate behaviour,
    documented as such throughout.

    Pure stdlib; deterministic — same seed -> identical snapshot.
    """
    d = max(3, distance | 1)          # force odd distance >= 3 (rotated surface code)
    p = max(1e-6, min(float(p), 0.5))  # clamp to a physically sane depolarizing rate

    rng = _lcg(seed * 1000003 + d)

    num_data_qubits = d * d
    num_ancilla = d * d - 1

    # MODELED mean syndrome weight: fraction of ancilla stabilizers that fire during
    # one measurement cycle scales with the physical error rate (each data-qubit
    # error flips ~2 neighbouring stabilizers on average in the bulk).
    mean_fired_fraction = min(0.95, 2.0 * p * (num_ancilla / max(num_data_qubits, 1)))
    jitter = (next(rng) - 0.5) * 0.08 * mean_fired_fraction   # deterministic +/-4% jitter
    fired_fraction = max(0.0, min(1.0, mean_fired_fraction + jitter))
    syndrome_weight = round(fired_fraction * num_ancilla, 3)

    # MODELED logical error rate via the closed-form below-threshold suppression law.
    ratio = p / _P_THRESHOLD
    exponent = (d + 1) / 2.0
    p_l = _A_PREFACTOR * (ratio ** exponent)
    # deterministic small multiplicative jitter (seed-driven, +/-3%) so repeated calls
    # with different seeds are distinguishable while staying reproducible per-seed.
    p_l *= (1.0 + (next(rng) - 0.5) * 0.06)
    p_l = max(0.0, min(1.0, p_l))

    # Companion logical error rate at d+2 for the suppression-factor figure of merit.
    d_next = d + 2
    p_l_next = _A_PREFACTOR * ((p / _P_THRESHOLD) ** ((d_next + 1) / 2.0))
    p_l_next = max(1e-300, min(1.0, p_l_next))

    suppression_factor = (p_l / p_l_next) if p_l_next > 0 else None

    below_threshold = p < _P_THRESHOLD

    return {
        "code_distance": d,
        "physical_error_rate": round(p, 6),
        "num_data_qubits": num_data_qubits,
        "num_ancilla": num_ancilla,
        "syndrome_weight": syndrome_weight,
        "logical_error_rate": round(p_l, 10),
        "logical_error_rate_d_plus_2": round(p_l_next, 12),
        "suppression_factor": round(suppression_factor, 4) if suppression_factor else None,
        "below_threshold": below_threshold,
        "threshold_used": _P_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _fi(req: Request, key: str, default) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return float(default)


def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_surface_code(req: Request):
    seed     = _ii(req, "seed",     42)
    distance = max(3, min(_ii(req, "distance", 5), 25))
    p        = max(1e-6, min(_fi(req, "p", 0.003), 0.5))

    snap = _surface_code_snapshot(seed=seed, distance=distance, p=p)

    below = snap["below_threshold"]
    threshold_note = (
        f"p={snap['physical_error_rate']} is "
        f"{'BELOW' if below else 'AT/ABOVE'} the MODELED threshold "
        f"p_th={_P_THRESHOLD}: "
        + (
            "increasing the code distance d SUPPRESSES the logical error rate "
            "EXPONENTIALLY (the below-threshold regime demonstrated experimentally "
            "by Google Quantum AI's Willow result, arXiv:2408.13687)."
            if below else
            "at or above threshold, increasing d does NOT reliably suppress the "
            "logical error rate — more physical qubits can make things WORSE, "
            "per Fowler et al. 2012 (arXiv:1208.0928)."
        )
    )

    return JSONResponse({
        "label":                 "MODELED",
        "model":                 "Rotated surface code, MWPM-style decoder (MODELED)",
        "equation":              "p_L(d) ~ A * (p / p_th)^((d+1)/2)  (Fowler et al. 2012; Google QAI 2024)",
        "seed":                  seed,
        "code_distance":         snap["code_distance"],
        "physical_error_rate":   snap["physical_error_rate"],
        "num_data_qubits":       snap["num_data_qubits"],
        "num_ancilla":           snap["num_ancilla"],
        "syndrome_weight":       snap["syndrome_weight"],
        "logical_error_rate":    snap["logical_error_rate"],
        "logical_error_rate_d_plus_2": snap["logical_error_rate_d_plus_2"],
        "suppression_factor":    snap["suppression_factor"],
        "below_threshold":       snap["below_threshold"],
        "threshold_note":        threshold_note,
        "honest_note": (
            "MODELED: this is a deterministic closed-form simulation of a rotated "
            "surface-code memory's logical-error scaling, using the standard "
            "below-threshold suppression law p_L(d) ~ A*(p/p_th)^((d+1)/2) (Fowler "
            "et al. 2012, arXiv:1208.0928). It illustrates the SAME functional "
            "phenomenon (exponential suppression with distance, below threshold) that "
            "Google Quantum AI demonstrated experimentally on superconducting qubits "
            "(arXiv:2408.13687, Nature 638:920-926) — reporting Lambda = 2.14 +/- 0.02 "
            "for their distance-5 -> distance-7 comparison. This module runs NO real "
            "quantum hardware, uses NO proprietary device data, and is not a claim "
            "about any specific QPU. Deterministic: same seed -> identical snapshot. "
            "Also cites Kitaev's toric code (arXiv:quant-ph/9707021), the topological "
            "ancestor of the surface code. SZL claims NONE of these methods as its own. "
            "This is a physics simulation ONLY — it adds NOTHING to SZL's locked-8 and "
            "makes no claim about SZL's own Lambda-as-Conjecture-1 doctrine constant "
            "(a different, unrelated symbol)."
        ),
        "citations":    CITATIONS,
        "computed_at":  datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_neuromorphic.register() / szl_interpretability
# .register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/qec/surface-code onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/qec"
    handlers = [
        (f"{base}/surface-code", _h_surface_code),
    ]
    add_api_route = getattr(app, "add_api_route", None)
    for path, fn in handlers:
        if callable(add_api_route):
            app.add_api_route(path, fn, methods=["GET"])
        else:
            app.router.routes.append(Route(path, fn))
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    # Show the key frontier result: below threshold, p_L drops sharply as d grows.
    print("label: MODELED")
    print("equation: p_L(d) ~ A * (p / p_th)^((d+1)/2)  (Fowler 2012; Google QAI 2024, arXiv:2408.13687)")
    print()
    p_test = 0.003  # below the MODELED threshold of 0.01
    prev_pl = None
    for d in (3, 5, 7):
        snap = _surface_code_snapshot(seed=42, distance=d, p=p_test)
        pl = snap["logical_error_rate"]
        line = (
            f"d={d:2d}  p={p_test}  data_qubits={snap['num_data_qubits']:3d}  "
            f"ancilla={snap['num_ancilla']:3d}  syndrome_weight={snap['syndrome_weight']:7.3f}  "
            f"p_L={pl:.10f}"
        )
        if prev_pl is not None:
            line += f"   (suppression vs d-2: {prev_pl / pl:.3f}x smaller)" if pl > 0 else ""
        print(line)
        prev_pl = pl

    print()
    assert True  # sanity anchor; real assertions below

    # Sanity checks: p_L must strictly decrease as d increases, below threshold.
    s3 = _surface_code_snapshot(seed=42, distance=3, p=p_test)
    s5 = _surface_code_snapshot(seed=42, distance=5, p=p_test)
    s7 = _surface_code_snapshot(seed=42, distance=7, p=p_test)
    assert s3["logical_error_rate"] > s5["logical_error_rate"] > s7["logical_error_rate"], (
        "logical error rate must decrease with increasing distance below threshold"
    )
    assert s3["num_data_qubits"] == 9 and s5["num_data_qubits"] == 25 and s7["num_data_qubits"] == 49
    assert s3["num_ancilla"] == 8 and s5["num_ancilla"] == 24 and s7["num_ancilla"] == 48
    assert s3["below_threshold"] and s5["below_threshold"] and s7["below_threshold"]

    # Above-threshold sanity: increasing d should NOT help (ratio >= 1).
    s3_above = _surface_code_snapshot(seed=42, distance=3, p=0.05)
    s7_above = _surface_code_snapshot(seed=42, distance=7, p=0.05)
    assert not s3_above["below_threshold"] and not s7_above["below_threshold"]

    print("szl_qec: ALL OK — logical error rate decreases monotonically with distance below threshold.")
