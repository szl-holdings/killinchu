# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_elf.py — ADDITIVE Embedded-Language-Flows (Flow Matching) integrator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/elf.js).

ELF: Embedded Language Flows (Hu, Qiu, Lu, Zhao, Li, Kim, Andreas, He 2026, arXiv:2605.10938)
is a continuous diffusion/flow language model that stays in a continuous EMBEDDING space and
uses continuous-time FLOW MATCHING, only mapping to discrete tokens at the final step. Flow
Matching (Lipman et al. 2023, arXiv:2210.02747) learns a time-dependent velocity field v_t(x)
whose ODE  dx/dt = v_t(x)  transports a simple base distribution (noise) at t=0 to the data
distribution at t=1 along straight conditional paths. This organ integrates such a flow ODE
deterministically and reports how well noise is transported onto target embeddings.

Deterministic MODELED formulation (seeded, no neural net):
  * Target: K seeded points in a d-dim embedding space (the "data" the flow should reach).
  * Base: seeded noise samples at t=0. Conditional flow-matching velocity for the linear
    (optimal-transport) path x_t = (1-t)*x0 + t*x1 is the constant field v = x1 - x0. We use
    a MODELED marginal velocity: at a point x and time t, v(x,t) points toward the nearest
    target's straight-line path, a deterministic stand-in for the learned velocity field.
  * Integrate the ODE with fixed-step Euler over `steps` from t=0 to t=1 (few-step sampling,
    the ELF selling point). Report transport error to nearest target and the straightness of
    each trajectory (flow matching's straight paths => fewer steps needed).

  x_{t+dt} = x_t + dt * v(x_t, t)
  transport_error = mean min_k || x_1 - target_k ||
  straightness    = ||x_1 - x_0|| / path_length      (1.0 == perfectly straight)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic ODE integration of a HAND-BUILT velocity field. NOT ELF running; NO
    trained flow-matching network, NO GPU, NO real embeddings/tokenizer. The velocity field is
    a nearest-target transport rule, a faithful but small stand-in for the learned field.
  * "few-step sampling" here means a small fixed Euler step count; it is not a benchmarked NFE
    against ELF on a real dataset.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/elf/flow  — flow-matching transport snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | FLOW_ODE_INTEGRATION | NOT_LIVE | NO_TRAINED_FIELD | NO_GPU"

CITATIONS = {
    "elf": ("Hu, Qiu, Lu, Zhao, Li, Kim, Andreas, He (2026) ELF: Embedded Language Flows — "
            "arXiv:2605.10938"),
    "elf_url": "https://arxiv.org/abs/2605.10938",
    "flow_matching": ("Lipman, Chen, Ben-Hamu, Nickel, Le (2023) Flow Matching for Generative "
                      "Modeling — arXiv:2210.02747"),
    "flow_matching_url": "https://arxiv.org/abs/2210.02747",
}


class _LCG:
    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)

    def random(self) -> float:
        self._s = (self._s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((self._s >> 11) & ((1 << 53) - 1)) / float(1 << 53)

    def gauss(self) -> float:
        u1 = max(1e-12, self.random())
        u2 = self.random()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dist(a: list[float], b: list[float]) -> float:
    return _math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def elf_flow(seed: int = 42, dim: int = 6, targets: int = 4, particles: int = 32,
             steps: int = 8) -> dict:
    """Flow-matching transport snapshot (MODELED).

    dim       — embedding dimension.
    targets   — number of data-mode target embeddings.
    particles — noise samples transported by the flow.
    steps     — Euler integration steps from t=0 to t=1 (few-step sampling).
    """
    d = max(2, min(64, int(dim)))
    K = max(1, min(64, int(targets)))
    P = max(2, min(4096, int(particles)))
    steps = max(1, min(512, int(steps)))
    rng = _LCG(int(seed) * 1_000_003 + d * 131 + P * 17 + steps)

    # data-mode targets and their radius scale
    tgt = [[3.0 * rng.gauss() for _ in range(d)] for _ in range(K)]
    # base noise particles at t=0
    x0 = [[rng.gauss() for _ in range(d)] for _ in range(P)]

    # MARGINAL flow-matching velocity: rather than an oracle straight line to one endpoint,
    # the marginal field at (x, t) is a softmin-weighted blend of the conditional velocities
    # toward every target, weighted by current proximity. This produces a curved trajectory
    # (like a real learned marginal field) that still converges onto a data mode. We integrate
    # the ODE with fixed-step Euler.
    dt = 1.0 / steps
    beta = 2.0  # softmin sharpness (MODELED)
    transport_errors = []
    straightness_vals = []
    final_states = []
    for p in range(P):
        start = x0[p][:]
        x = start[:]
        path_len = 0.0
        prev = x[:]
        for _s in range(steps):
            # softmin weights over targets by distance -> marginal velocity
            dists = [_dist(x, tgt[kk]) for kk in range(K)]
            mind = min(dists)
            ws = [_math.exp(-beta * (dd - mind)) for dd in dists]
            sw = sum(ws) or 1e-12
            v = [0.0] * d
            for kk in range(K):
                w = ws[kk] / sw
                for i in range(d):
                    v[i] += w * (tgt[kk][i] - x[i])
            x = [x[i] + dt * v[i] for i in range(d)]
            path_len += _dist(prev, x)
            prev = x[:]
        # transport error to nearest actual target after integration
        err = min(_dist(x, tgt[kk]) for kk in range(K))
        transport_errors.append(err)
        straight = (_dist(start, x) / path_len) if path_len > 1e-12 else 1.0
        straightness_vals.append(min(1.0, straight))
        if p < 8:
            final_states.append([round(float(z), 4) for z in x])

    transport_error = sum(transport_errors) / P
    mean_straightness = sum(straightness_vals) / P

    # baseline: distance from noise to nearest target BEFORE the flow (for a reduction figure)
    base_err = sum(min(_dist(x0[p], tgt[kk]) for kk in range(K)) for p in range(P)) / P
    error_reduction_pct = (1.0 - transport_error / base_err) * 100.0 if base_err > 1e-12 else 0.0

    return {
        "service": "embedded-language-flows",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/elf.js ---
        "dim": int(d),
        "targets": int(K),
        "particles": int(P),
        "steps": int(steps),
        "transport_error": round(float(transport_error), 6),
        "baseline_error": round(float(base_err), 6),
        "error_reduction_pct": round(float(error_reduction_pct), 3),
        "mean_straightness": round(float(mean_straightness), 6),
        "final_states_sample": final_states,
        "formulas": {
            "ode_step": "x_{t+dt} = x_t + dt * v(x_t, t)",
            "marginal_velocity": "v(x,t) = sum_k softmin_k(||x-t_k||) * (t_k - x)  (marginal FM field)",
            "transport_error": "mean_p min_k || x_1 - target_k ||",
            "straightness": "||x1 - x0|| / path_length  (1.0 == straight)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python fixed-step Euler ODE integration",
            "label": "MODELED",
            "honest_note": ("Deterministic ODE integration of a HAND-BUILT nearest-target "
                            "velocity field; NO trained flow-matching net, NO GPU, NO real "
                            "embeddings/tokenizer. A learned velocity field + real tokens are "
                            "ROADMAP."),
        },
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (flow advisory — never an autonomous action)",
        "wired_into": "frontier ring — Embedded-Language-Flows surface",
        "honest_note": ("MODELED deterministic flow-matching ODE integration in a continuous "
                        "embedding space, mirroring ELF's continuous-flow-then-decode design. "
                        "The velocity field is hand-built (nearest-target OT path), NOT trained. "
                        "MODELED, not live; advisory to Λ (Conjecture 1)."),
        "citations": {"elf": CITATIONS["elf"], "elf_url": CITATIONS["elf_url"],
                      "flow_matching": CITATIONS["flow_matching"],
                      "flow_matching_url": CITATIONS["flow_matching_url"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/elf" % ns

    @app.get("%s/flow" % base)
    async def _kc_elf(seed: int = 42, dim: int = 6, targets: int = 4, particles: int = 32,
                      steps: int = 8):  # noqa: ANN202
        try:
            return JSONResponse(elf_flow(seed=seed, dim=dim, targets=targets,
                                         particles=particles, steps=steps))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "embedded-language-flows",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "transport_error": None}, status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401
    except Exception:  # pragma: no cover
        pass
    return {"ok": True, "ns": ns, "routes": ["%s/flow" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = elf_flow(seed=42, dim=6, targets=4, particles=32, steps=8)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("dim", "targets", "particles", "steps"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("transport_error", "baseline_error", "mean_straightness"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["final_states_sample"], list) and r["final_states_sample"], r
    assert r["transport_error"] >= 0.0, r
    # the flow must transport noise closer to the targets than baseline
    assert r["transport_error"] < r["baseline_error"], r
    assert r["error_reduction_pct"] > 0.0, r
    # linear OT paths are straight
    assert 0.0 <= r["mean_straightness"] <= 1.0 + 1e-9, r
    assert r["mean_straightness"] > 0.5, r
    assert "2605.10938" in r["citations"]["elf"], r
    out["metrics"] = {"transport_error": r["transport_error"], "baseline_error": r["baseline_error"],
                      "error_reduction_pct": r["error_reduction_pct"],
                      "mean_straightness": r["mean_straightness"]}

    # determinism
    r2 = elf_flow(seed=42, dim=6, targets=4, particles=32, steps=8)
    assert r2["final_states_sample"] == r["final_states_sample"], "non-deterministic"
    assert r2["transport_error"] == r["transport_error"], "non-deterministic error"
    out["deterministic"] = True

    p = register(_FakeApp())
    assert p["routes"] == ["/api/killinchu/v1/elf/flow"], p
    out["route"] = p["routes"][0]

    out["ok"] = True
    return out


class _FakeApp:
    def get(self, path):
        def _d(fn):
            return fn
        return _d


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    m = res["metrics"]
    print("transport_err=%.4f  baseline=%.4f  reduction=%.1f%%  straightness=%.4f"
          % (m["transport_error"], m["baseline_error"], m["error_reduction_pct"],
             m["mean_straightness"]))
    assert res["ok"]
    print("ALL OK")
