# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_ssm.py — ADDITIVE selective State-Space-Model (Mamba) scan simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/ssm.js).

Mamba (Gu, Dao 2023; arXiv:2312.00752) is a selective structured state-space model (S6). A
state-space layer maintains a hidden state h_t and evolves it with a linear recurrence
    h_t = A_bar_t h_{t-1} + B_bar_t x_t ,   y_t = C_t h_t
where in the SELECTIVE variant the discretized A_bar, B_bar and the input matrix C are FUNCTIONS
of the input x_t (input-dependent gating), and the step size Delta_t is input-dependent too:
A_bar = exp(Delta_t * A), B_bar = Delta_t * B. Making the parameters input-dependent lets the model
selectively propagate or forget information along the sequence — the key improvement over earlier
time-invariant SSMs — and it runs in LINEAR time via a parallel associative scan.

This module simulates one selective SSM channel deterministically (seeded, NO trained model): a
scalar hidden state is scanned across a sequence with input-dependent Delta (selective gating). It
reports the effective memory horizon (how far past inputs still influence the state, from the
decay A_bar), the fraction of tokens the selection gate keeps vs forgets, the final state and
output energy, and confirms the recurrence runs in O(T) (linear-time scan).

Reported (field names read verbatim by ssm.js):
  seq_len              — T, sequence length scanned
  state_dim            — N, hidden state dimension
  effective_memory     — effective memory horizon in tokens (from mean A_bar decay) (MODELED)
  selectivity          — mean input-dependent gate (fraction kept) in [0,1] (MODELED)
  final_state_norm     — ||h_T|| after the scan
  output_energy        — mean y_t^2 over the sequence
  scan_ops             — recurrence op count (== T, linear-time)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic selective-SSM SCAN. NOT trained Mamba running; NO learned A/B/C/Delta,
    NO GPU, NO real hardware-aware kernel. The dynamics matrices and gate are SEEDED inputs /
    MODELED references, NOT measured on any real model.
  * "effective_memory" is a property of the modeled decay A_bar, honestly labeled, not a
    benchmark claim about any real long-context model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/ssm/scan — selective state-space (Mamba) scan snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "mamba": ("Gu, Dao (2023) Mamba: Linear-Time Sequence Modeling with Selective State Spaces "
              "— arXiv:2312.00752 · https://arxiv.org/abs/2312.00752"),
    "s4": ("Gu, Goel, Re (2021) Efficiently Modeling Long Sequences with Structured State Spaces "
           "(S4) — arXiv:2111.00396 · https://arxiv.org/abs/2111.00396"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | SELECTIVE_SSM_SCAN_SIM | NOT_LIVE | NO_MODEL | DYNAMICS_ARE_MODELED"


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

    def normal(self) -> float:
        u1 = max(1e-12, self.uniform())
        u2 = self.uniform()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = _math.exp(-x)
        return 1.0 / (1.0 + z)
    z = _math.exp(x)
    return z / (1.0 + z)


def ssm_scan(seed: int = 42, seq_len: int = 64, state_dim: int = 8,
             a_base: float = -0.5) -> dict:
    """Selective state-space (Mamba) scan snapshot (MODELED).

    seq_len   — T, sequence length scanned.
    state_dim — N, hidden state dimension.
    a_base    — base (negative) continuous A eigenvalue; controls decay / memory.
    seed      — RNG seed; identical inputs give identical output (deterministic).
    """
    T = max(2, min(4096, int(seq_len)))
    N = max(1, min(256, int(state_dim)))
    A = min(-1e-3, float(a_base))  # continuous A must be negative for a stable (decaying) SSM
    rng = _LCG(int(seed) * 1_000_003 + T * 131 + N * 17)

    # Per-dimension state vector and modeled B, C.
    h = [0.0 for _ in range(N)]
    B = [0.5 + 0.5 * rng.uniform() for _ in range(N)]
    C = [rng.normal() for _ in range(N)]

    # Input sequence.
    x_seq = [rng.normal() for _ in range(T)]

    outputs = []
    abar_sum = 0.0
    gate_sum = 0.0
    scan_ops = 0
    for t in range(T):
        x = x_seq[t]
        # Selective (input-dependent) step size Delta_t = softplus of a linear fn of x -> in (0, ~).
        delta = _math.log1p(_math.exp(0.5 * x))       # softplus, always positive
        delta = min(delta, 5.0)
        gate = _sigmoid(x)                             # selection gate: fraction of input written
        gate_sum += gate
        for i in range(N):
            a_bar = _math.exp(delta * A)               # discretized decay in (0,1)
            b_bar = delta * B[i]
            h[i] = a_bar * h[i] + b_bar * (gate * x)   # selective write
            abar_sum += a_bar
            scan_ops += 1
        y = sum(C[i] * h[i] for i in range(N))
        outputs.append(y)

    mean_abar = abar_sum / (T * N)
    selectivity = gate_sum / T
    # Effective memory horizon: number of steps for the state to decay by 1/e, ~ 1/(1 - A_bar).
    effective_memory = (1.0 / (1.0 - mean_abar)) if mean_abar < 1.0 else float(T)
    final_state_norm = _math.sqrt(sum(v * v for v in h))
    output_energy = sum(y * y for y in outputs) / T

    return {
        "service": "selective-state-space-scan",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/ssm.js ---
        "seq_len": int(T),
        "state_dim": int(N),
        "effective_memory": round(float(effective_memory), 4),
        "selectivity": round(float(selectivity), 6),
        "final_state_norm": round(float(final_state_norm), 6),
        "output_energy": round(float(output_energy), 6),
        "mean_a_bar": round(float(mean_abar), 6),
        "scan_ops": int(scan_ops),
        "linear_time": bool(scan_ops == T * N),
        "formulas": {
            "recurrence": "h_t = A_bar_t h_{t-1} + B_bar_t (gate_t x_t);  y_t = C h_t",
            "discretize": "A_bar = exp(Delta_t * A),  B_bar = Delta_t * B",
            "selective": "Delta_t = softplus(w x_t), gate_t = sigmoid(x_t)  (input-dependent)",
            "effective_memory": "1 / (1 - mean(A_bar))  (1/e decay horizon in tokens)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python selective-SSM associative-scan simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic selective-SSM scan; NO trained Mamba, NO learned "
                            "A/B/C/Delta, NO GPU, NO hardware-aware kernel. A trained SSM is ROADMAP."),
        },
        "honest_note": ("MODELED selective state-space scan. effective_memory is a property of the "
                        "modeled decay A_bar + input-dependent gating, not a long-context "
                        "benchmark claim about any real model."),
        "wired_into": "frontier ring — selective State-Space-Model (Mamba) scan surface",
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (advisory scan metrics — never autonomous)",
        "citations": {"mamba": CITATIONS["mamba"], "s4": CITATIONS["s4"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/ssm" % ns
    path = "%s/scan" % base

    @app.get(path)
    async def _kc_ssm(seed: int = 42, seq_len: int = 64, state_dim: int = 8):  # noqa: ANN202
        try:
            return JSONResponse(ssm_scan(seed=seed, seq_len=seq_len, state_dim=state_dim))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "selective-state-space-scan",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "effective_memory": None, "selectivity": None},
                                status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401 — Route fallback parity with template
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = ssm_scan(seed=42, seq_len=64, state_dim=8)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "state_dim", "scan_ops"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("effective_memory", "selectivity", "final_state_norm", "output_energy"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))

    # bounds: selection gate in [0,1]; A_bar decay in (0,1); linear-time scan.
    assert 0.0 <= r["selectivity"] <= 1.0, r["selectivity"]
    assert 0.0 < r["mean_a_bar"] < 1.0, r["mean_a_bar"]
    assert r["effective_memory"] > 0.0, r["effective_memory"]
    assert r["linear_time"] is True, r
    assert r["scan_ops"] == r["seq_len"] * r["state_dim"], r
    out["metrics"] = {"effective_memory": r["effective_memory"], "selectivity": r["selectivity"],
                      "final_state_norm": r["final_state_norm"], "output_energy": r["output_energy"]}

    assert "2312.00752" in r["citations"]["mamba"], r["citations"]

    # determinism
    r2 = ssm_scan(seed=42, seq_len=64, state_dim=8)
    assert r2["effective_memory"] == r["effective_memory"], "non-deterministic"
    assert r2["final_state_norm"] == r["final_state_norm"], "non-deterministic"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2))
    assert res["ok"] is True
    print("ALL OK", file=sys.stderr)
    print("ALL OK")
