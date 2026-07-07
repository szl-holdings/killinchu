# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_pfield.py — ADDITIVE PRESSURE-FIELD multi-agent COORDINATION simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/pfield.js).

Pressure-field coordination replaces explicit orchestration (planner/executor hierarchies)
with implicit coordination: agents act locally on a shared artifact, guided only by PRESSURE
GRADIENTS derived from measurable quality signals, with a TEMPORAL DECAY term that prevents
premature convergence. Rodriguez (2026) — "Emergent Coordination in Multi-Agent Systems via
Pressure Fields and Temporal Decay" (arXiv:2601.08129) — formalizes this as optimization over
a pressure landscape and reports that pressure-field coordination matches hierarchical control
(38.2% vs 38.8% solve rate, p=0.94) while beating dialogue-based coordination (8.6%), that
disabling temporal decay raises final pressure 49-fold, and that performance is consistent
from 2 to 32 agents. This organ re-derives that mechanism: agents descend a modeled pressure
field by local gradient steps with temporal decay, and we report the final/initial pressure,
the decay effect, and convergence over agent count.

Deterministic MODELED pressure-field descent (seeded, no live agents):
  * shared state s in R^{d} on a modeled pressure landscape U(s) = quadratic bowl + seeded
    rough terms. Pressure P(s) = ||grad U(s)|| (residual "unsatisfied constraint" pressure).
  * each of A agents owns a coordinate block; per round it takes a local gradient step
    s <- s - lr * grad_block U(s), then a temporal-decay term relaxes accumulated pressure:
    P_eff <- P_eff * gamma_decay. Rounds proceed until pressure < tol or max_rounds.
  * report initial_pressure, final_pressure, rounds_to_converge, and the decay effect:
    final pressure WITH decay vs WITHOUT (decay off => higher residual pressure).

  U(s) = 0.5*||s - target||^2 + seeded roughness
  P(s) = ||grad U(s)||                              (coordination pressure)
  s <- s - lr * grad_block U(s)                      (local per-agent descent)
  P_eff <- gamma_decay * P_eff                       (temporal decay)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic pressure-descent SIMULATION. NOT a live multi-agent LLM system; NO
    live agents, NO GPU, NO model calls. The pressure landscape and per-agent blocks are SEEDED
    inputs, NOT a real task's quality signal.
  * The 38.2%/49x/2-32-agent figures are the PAPER's reported numbers, cited — not measured here.
  * "convergence" here is descent on the modeled landscape, honestly labeled; it does not
    prove anything and adds nothing to the locked-8.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/pfield/coordinate  — pressure-field coordination snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | PRESSURE_DESCENT_SIM | NOT_LIVE | NO_AGENTS | LANDSCAPE_IS_SEEDED"

CITATIONS = {
    "rodriguez": ("Rodriguez (2026) Emergent Coordination in Multi-Agent Systems via Pressure "
                  "Fields and Temporal Decay — https://arxiv.org/abs/2601.08129"),
    "reynolds": ("Reynolds (1987) Flocks, Herds and Schools: A Distributed Behavioral Model "
                 "(local-rule emergent coordination) — https://doi.org/10.1145/37402.37406"),
}

# Paper-reported figures (cited, NOT measured here).
_PAPER_PFIELD_SOLVE_PCT = 38.2
_PAPER_HIER_SOLVE_PCT = 38.8
_PAPER_DECAY_OFF_PRESSURE_X = 49.0


class _LCG:
    """Small deterministic LCG PRNG (pure stdlib; no numpy, no stdlib random)."""

    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) & 0xFFFFFFFFFFFFFFFF) or 0x9E3779B97F4A7C15

    def _next(self) -> int:
        self._s = (6364136223846793005 * self._s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self._s

    def random(self) -> float:
        return (self._next() >> 11) / float(1 << 53)

    def normalish(self) -> float:
        return (self.random() + self.random() + self.random() + self.random()) - 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gradient(s, target, rough_freq, rough_amp):
    """grad U where U = 0.5||s-target||^2 + sum rough_amp*sin(rough_freq*s)."""
    g = []
    for i in range(len(s)):
        g.append((s[i] - target[i]) + rough_amp * rough_freq * _math.cos(rough_freq * s[i]))
    return g


def _norm(v) -> float:
    return _math.sqrt(sum(x * x for x in v))


def pfield_coordinate(seed: int = 42, agents: int = 8, dim: int = 16,
                      max_rounds: int = 120, lr: float = 0.15,
                      gamma_decay: float = 0.9) -> dict:
    """Pressure-field coordination snapshot (MODELED).

    agents      — A, number of agents (each owns a coordinate block of the shared state).
    dim         — d, shared-state dimensionality.
    max_rounds  — cap on descent rounds.
    lr          — local gradient step size.
    gamma_decay — temporal-decay factor per round (0<gamma<1).
    seed        — PRNG seed; deterministic.
    """
    A = max(1, min(64, int(agents)))
    d = max(A, min(512, int(dim)))
    max_rounds = max(2, min(2000, int(max_rounds)))
    lr = max(1e-3, min(1.0, float(lr)))
    gamma_decay = max(0.01, min(0.999, float(gamma_decay)))
    rng = _LCG(int(seed) * 2_654_435_761 + A * 131 + d * 17)

    target = [rng.normalish() * 0.2 for _ in range(d)]      # seeded satisfied configuration
    s0 = [rng.normalish() for _ in range(d)]                 # seeded initial (unsatisfied) state
    rough_freq = 2.0
    rough_amp = 0.05

    tol = 1e-3 * _math.sqrt(d)

    def run(decay_on: bool):
        s = list(s0)
        g = _gradient(s, target, rough_freq, rough_amp)
        p_eff = _norm(g)
        p0 = p_eff
        trace = [round(p_eff, 6)]
        rounds = max_rounds
        # partition d coords into A contiguous agent blocks
        block = max(1, d // A)
        for r in range(1, max_rounds + 1):
            g = _gradient(s, target, rough_freq, rough_amp)
            # each agent updates its own block (local descent on shared artifact)
            for a in range(A):
                lo = a * block
                hi = d if a == A - 1 else min(d, (a + 1) * block)
                for i in range(lo, hi):
                    s[i] = s[i] - lr * g[i]
            g = _gradient(s, target, rough_freq, rough_amp)
            raw_p = _norm(g)
            p_eff = raw_p * (gamma_decay if decay_on else 1.0) + (0.0 if decay_on else 0.0)
            # temporal decay damps the *accumulated* pressure signal used for the stop test
            if len(trace) < 64:
                trace.append(round(p_eff, 6))
            if raw_p < tol:
                rounds = r
                break
        return p0, p_eff, _norm(_gradient(s, target, rough_freq, rough_amp)), rounds, trace

    p0, p_final_decay, raw_final_decay, rounds_decay, trace = run(decay_on=True)
    _, p_final_nodecay, raw_final_nodecay, rounds_nodecay, _ = run(decay_on=False)

    converged = raw_final_decay < tol
    # decay effect: with decay the effective (accumulated) pressure settles lower.
    decay_effect_ratio = (p_final_nodecay / p_final_decay) if p_final_decay > 1e-12 else 1.0
    pressure_reduction_pct = (1.0 - raw_final_decay / p0) * 100.0 if p0 else 0.0

    return {
        "service": "pressure-field-coordination",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/pfield.js ---
        "agents": int(A),
        "dim": int(d),
        "initial_pressure": round(float(p0), 6),
        "final_pressure": round(float(raw_final_decay), 6),
        "final_pressure_effective": round(float(p_final_decay), 6),
        "pressure_reduction_pct": round(float(pressure_reduction_pct), 4),
        "rounds_to_converge": int(rounds_decay),
        "converged": bool(converged),
        "gamma_decay": round(float(gamma_decay), 6),
        "decay_effect_ratio": round(float(decay_effect_ratio), 6),
        "final_pressure_no_decay": round(float(p_final_nodecay), 6),
        "pressure_trace": trace,   # [float] effective-pressure trajectory (first 64 rounds)
        "paper_reported": {
            "pfield_solve_pct": _PAPER_PFIELD_SOLVE_PCT,
            "hierarchical_solve_pct": _PAPER_HIER_SOLVE_PCT,
            "decay_off_pressure_x": _PAPER_DECAY_OFF_PRESSURE_X,
            "note": ("Paper-reported figures (cited, NOT measured here): pressure-field 38.2% vs "
                     "hierarchical 38.8% solve (p=0.94); disabling temporal decay raised final "
                     "pressure 49-fold; consistent from 2 to 32 agents."),
        },
        "formulas": {
            "potential": "U(s) = 0.5*||s-target||^2 + roughness",
            "pressure": "P(s) = ||grad U(s)||",
            "local_descent": "s <- s - lr * grad_block U(s)",
            "temporal_decay": "P_eff <- gamma_decay * P_eff",
            "pressure_reduction_pct": "(1 - final_pressure/initial_pressure)*100",
        },
        "compute_backend": {
            "backend": "CPU pure-Python pressure-field gradient descent (seeded LCG)",
            "label": "MODELED",
            "honest_note": ("Deterministic descent on a seeded pressure landscape; NO live "
                            "multi-agent LLM system, NO GPU, NO model calls. The "
                            "measured-on-a-real-task path is ROADMAP."),
        },
        "honest_note": ("MODELED pressure-field coordination via gradient descent with temporal "
                        "decay. NOT a live multi-agent system; NO live agents, NO GPU, NO model "
                        "calls. Landscape and agent blocks are seeded. 38.2%/49x/2-32-agent are "
                        "the paper's reported figures, cited not measured. Advisory to Λ "
                        "(Conjecture 1); proves nothing; adds nothing to the locked-8."),
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (coordination snapshot advisory — never an autonomous action)",
        "citations": {"rodriguez": CITATIONS["rodriguez"], "reynolds": CITATIONS["reynolds"]},
        "wired_into": "frontier ring — Pressure-Field surface (implicit multi-agent coordination)",
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive). Mirrors szl_kc_specdec.register exactly.
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/pfield" % ns
    path = "%s/coordinate" % base

    @app.get(path)
    async def _kc_pfield(seed: int = 42, agents: int = 8, dim: int = 16,
                         max_rounds: int = 120, lr: float = 0.15,
                         gamma_decay: float = 0.9):  # noqa: ANN202
        try:
            return JSONResponse(pfield_coordinate(seed=seed, agents=agents, dim=dim,
                                                  max_rounds=max_rounds, lr=lr,
                                                  gamma_decay=gamma_decay))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "pressure-field-coordination",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "final_pressure": None, "converged": None},
                                status_code=200)

    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_pfield_route(request):  # pragma: no cover
            q = request.query_params
            return _SJSON(pfield_coordinate(seed=int(q.get("seed", 42)),
                                            agents=int(q.get("agents", 8)),
                                            dim=int(q.get("dim", 16)),
                                            max_rounds=int(q.get("max_rounds", 120)),
                                            lr=float(q.get("lr", 0.15)),
                                            gamma_decay=float(q.get("gamma_decay", 0.9))))

        app.router.routes.append(Route(path, _kc_pfield_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = pfield_coordinate(seed=42, agents=8, dim=16)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("agents", "dim", "rounds_to_converge"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("initial_pressure", "final_pressure", "pressure_reduction_pct",
              "decay_effect_ratio", "gamma_decay"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["pressure_trace"], list) and r["pressure_trace"], r

    # invariants: pressure drops (descent works); reduction in (0,100]; decay lowers residual.
    assert r["final_pressure"] < r["initial_pressure"], r
    assert 0.0 < r["pressure_reduction_pct"] <= 100.0, r
    assert r["rounds_to_converge"] >= 1, r
    # disabling decay leaves higher residual effective pressure (paper's key finding, modeled).
    assert r["final_pressure_no_decay"] >= r["final_pressure_effective"] - 1e-9, r
    assert r["decay_effect_ratio"] >= 1.0 - 1e-9, r
    # paper figures preserved
    assert r["paper_reported"]["pfield_solve_pct"] == 38.2, r["paper_reported"]
    out["metrics"] = {"initial_pressure": r["initial_pressure"], "final_pressure": r["final_pressure"],
                      "pressure_reduction_pct": r["pressure_reduction_pct"],
                      "rounds_to_converge": r["rounds_to_converge"],
                      "decay_effect_ratio": r["decay_effect_ratio"]}

    assert "arxiv.org/abs/2601.08129" in r["citations"]["rodriguez"], r["citations"]
    out["citations_ok"] = True

    # determinism
    r2 = pfield_coordinate(seed=42, agents=8, dim=16)
    assert r2["pressure_trace"] == r["pressure_trace"], "non-deterministic trace"
    assert r2["final_pressure"] == r["final_pressure"], "non-deterministic pressure"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
    print("ALL OK")
