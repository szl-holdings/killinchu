# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_goat.py — ADDITIVE ENTROPIC-OPTIMAL-TRANSPORT ("GOAT") attention/transport simulator
for killinchu's frontier surface (backs a11oy static/3d/surfaces/goat.js).

The GOAT paper — "You Need Better Attention Priors" (Litman, Guo 2026, arXiv:2601.15380) —
views attention through Entropic Optimal Transport (EOT): standard softmax attention is an
EOT/transport problem regularized by an IMPLICIT UNIFORM prior, and GOAT (Generalized Optimal
transport Attention with Trainable priors) replaces the uniform assumption with a learnable
prior. The underlying solver is the Sinkhorn algorithm for entropic OT (Cuturi 2013,
"Sinkhorn Distances: Lightspeed Computation of Optimal Transport", arXiv:1306.0895), which
alternately normalizes rows and columns of exp(-C/eps) toward target marginals. This organ
re-derives that mechanism: it builds a modeled cost matrix, runs Sinkhorn to a doubly-modeled
transport plan, and reports the transport cost, marginal violation, and the entropy gap
between a uniform-prior plan (plain softmax attention) and a non-uniform-prior GOAT plan.

Deterministic MODELED entropic-OT (seeded, no live model):
  * cost matrix C[i][j] = seeded modeled query/key distance in [0,1].
  * kernel K = exp(-C/eps).  Sinkhorn scaling: u <- a/(K v), v <- b/(K^T u) for N_iter,
    giving plan P = diag(u) K diag(v) with row-marginals ~ a and column-marginals ~ b.
  * a is uniform (rows/queries); b is the PRIOR over columns/keys. GOAT prior = seeded
    non-uniform b; baseline = uniform b (== plain softmax attention).
  * report transport_cost = sum(P*C), marginal_violation = max|rowsum(P)-a|, plan entropy
    H(P) = -sum P log P, and the signed entropy_gap = H_uniform - H_goat (how the learned
    prior reshapes the plan's entropy vs. plain softmax attention; sign is data-dependent).

  P = diag(u) exp(-C/eps) diag(v)     (Sinkhorn entropic-OT plan)
  transport_cost = sum_ij P_ij C_ij
  H(P) = -sum_ij P_ij log P_ij
  entropy_gap = H(P_uniform_prior) - H(P_goat_prior)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic Sinkhorn/EOT SIMULATION. NOT GOAT/FlashAttention running; NO live
    model, NO GPU, NO trained priors. The cost matrix and the GOAT prior are SEEDED inputs.
  * Sinkhorn convergence and the transport-plan properties are algebraic facts of the
    algorithm on the modeled inputs, honestly labeled — not a measured claim about a model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/goat/transport  — EOT-attention transport-plan snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | SINKHORN_EOT_SIM | NOT_LIVE | NO_MODEL | PRIOR_IS_SEEDED"

CITATIONS = {
    "goat": ("Litman, Guo (2026) You Need Better Attention Priors — Generalized Optimal "
             "transport Attention with Trainable priors (GOAT) — https://arxiv.org/abs/2601.15380"),
    "cuturi": ("Cuturi (2013) Sinkhorn Distances: Lightspeed Computation of Optimal "
               "Transport — https://arxiv.org/abs/1306.0895"),
    "peyre": ("Peyre, Cuturi (2019) Computational Optimal Transport — "
              "https://arxiv.org/abs/1803.00567"),
}


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sinkhorn(C, a, b, eps: float, iters: int):
    """Entropic-OT Sinkhorn scaling. Returns (plan P, transport_cost, marginal_violation)."""
    n = len(a)
    m = len(b)
    K = [[_math.exp(-C[i][j] / eps) for j in range(m)] for i in range(n)]
    u = [1.0] * n
    v = [1.0] * m
    for _ in range(iters):
        # u <- a / (K v)
        for i in range(n):
            s = 0.0
            Ki = K[i]
            for j in range(m):
                s += Ki[j] * v[j]
            u[i] = a[i] / s if s > 0 else 0.0
        # v <- b / (K^T u)
        for j in range(m):
            s = 0.0
            for i in range(n):
                s += K[i][j] * u[i]
            v[j] = b[j] / s if s > 0 else 0.0
    P = [[u[i] * K[i][j] * v[j] for j in range(m)] for i in range(n)]
    cost = sum(P[i][j] * C[i][j] for i in range(n) for j in range(m))
    row_viol = max(abs(sum(P[i][j] for j in range(m)) - a[i]) for i in range(n))
    return P, cost, row_viol


def _plan_entropy(P) -> float:
    h = 0.0
    for row in P:
        for p in row:
            if p > 1e-15:
                h -= p * _math.log(p)
    return h


def goat_transport(seed: int = 42, n_query: int = 8, n_key: int = 8,
                   eps: float = 0.1, iters: int = 40) -> dict:
    """EOT-attention transport-plan snapshot (MODELED).

    n_query/n_key — token counts (rows=queries, cols=keys).
    eps           — entropic regularization strength (smaller => sharper plan).
    iters         — Sinkhorn iterations.
    seed          — PRNG seed; deterministic.
    """
    N = max(2, min(64, int(n_query)))
    M = max(2, min(64, int(n_key)))
    eps = max(1e-3, min(2.0, float(eps)))
    iters = max(2, min(500, int(iters)))
    rng = _LCG(int(seed) * 1_000_003 + N * 131 + M * 17)

    C = [[rng.random() for _ in range(M)] for _ in range(N)]
    a = [1.0 / N] * N  # uniform queries

    # baseline (plain softmax attention == uniform prior over keys)
    b_uniform = [1.0 / M] * M
    # GOAT: a seeded non-uniform learnable prior over keys, normalized to sum 1.
    raw = [rng.random() + 0.05 for _ in range(M)]
    z = sum(raw)
    b_goat = [x / z for x in raw]

    P_u, cost_u, viol_u = _sinkhorn(C, a, b_uniform, eps, iters)
    P_g, cost_g, viol_g = _sinkhorn(C, a, b_goat, eps, iters)

    H_u = _plan_entropy(P_u)
    H_g = _plan_entropy(P_g)
    entropy_gap = H_u - H_g

    # attention-sink proxy: fraction of total mass on the single most-attended key (GOAT plan)
    col_mass = [sum(P_g[i][j] for i in range(N)) for j in range(M)]
    total_mass = sum(col_mass) or 1.0
    sink_fraction = max(col_mass) / total_mass

    converged = viol_g < 1e-3
    plan_row0 = [round(x, 6) for x in P_g[0]]  # a representative transport row for the surface

    return {
        "service": "eot-attention-transport",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/goat.js ---
        "n_query": int(N),
        "n_key": int(M),
        "eps": round(float(eps), 6),
        "sinkhorn_iters": int(iters),
        "transport_cost_goat": round(float(cost_g), 6),
        "transport_cost_uniform": round(float(cost_u), 6),
        "marginal_violation": round(float(viol_g), 9),
        "converged": bool(converged),
        "plan_entropy_uniform": round(float(H_u), 6),
        "plan_entropy_goat": round(float(H_g), 6),
        "entropy_gap": round(float(entropy_gap), 6),
        "attention_sink_fraction": round(float(sink_fraction), 6),
        "prior_over_keys": [round(x, 6) for x in b_goat],   # [float] the learned GOAT prior
        "transport_plan_row0": plan_row0,                    # [float] one representative row
        "formulas": {
            "kernel": "K = exp(-C/eps)",
            "sinkhorn": "u<-a/(Kv); v<-b/(K^T u); P=diag(u) K diag(v)",
            "transport_cost": "sum_ij P_ij C_ij",
            "plan_entropy": "-sum_ij P_ij log P_ij",
            "entropy_gap": "H(uniform-prior plan) - H(GOAT-prior plan)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python Sinkhorn entropic-OT solver (seeded LCG)",
            "label": "MODELED",
            "honest_note": ("Deterministic Sinkhorn on a modeled cost matrix; NO live GOAT/"
                            "FlashAttention, NO GPU, NO trained priors. Cost matrix and GOAT "
                            "prior are seeded. The measured-on-a-real-attention-layer path is "
                            "ROADMAP."),
        },
        "honest_note": ("MODELED entropic-optimal-transport view of attention. NOT GOAT running; "
                        "NO live model, NO GPU, NO trained priors. Cost matrix and prior are "
                        "seeded inputs; Sinkhorn convergence is an algorithmic fact on those "
                        "inputs. Advisory to Λ (Conjecture 1); adds nothing to the locked-8."),
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (transport snapshot advisory — never an autonomous action)",
        "citations": {"goat": CITATIONS["goat"], "cuturi": CITATIONS["cuturi"], "peyre": CITATIONS["peyre"]},
        "wired_into": "frontier ring — GOAT / EOT-attention surface (Sinkhorn transport plan)",
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive). Mirrors szl_kc_specdec.register exactly.
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/goat" % ns
    path = "%s/transport" % base

    @app.get(path)
    async def _kc_goat(seed: int = 42, n_query: int = 8, n_key: int = 8,
                       eps: float = 0.1, iters: int = 40):  # noqa: ANN202
        try:
            return JSONResponse(goat_transport(seed=seed, n_query=n_query, n_key=n_key,
                                               eps=eps, iters=iters))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "eot-attention-transport",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "transport_cost_goat": None, "converged": None},
                                status_code=200)

    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_goat_route(request):  # pragma: no cover
            q = request.query_params
            return _SJSON(goat_transport(seed=int(q.get("seed", 42)),
                                         n_query=int(q.get("n_query", 8)),
                                         n_key=int(q.get("n_key", 8)),
                                         eps=float(q.get("eps", 0.1)),
                                         iters=int(q.get("iters", 40))))

        app.router.routes.append(Route(path, _kc_goat_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = goat_transport(seed=42, n_query=8, n_key=8)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("n_query", "n_key", "sinkhorn_iters"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("transport_cost_goat", "plan_entropy_goat", "entropy_gap", "marginal_violation"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["prior_over_keys"], list) and r["prior_over_keys"], r
    assert isinstance(r["transport_plan_row0"], list) and r["transport_plan_row0"], r

    # invariants: Sinkhorn converged (row marginals matched) + prior sums to ~1.
    assert r["converged"] is True, r
    assert r["marginal_violation"] < 1e-3, r
    assert abs(sum(r["prior_over_keys"]) - 1.0) < 1e-6, sum(r["prior_over_keys"])
    # GOAT plan column marginals must match the seeded non-uniform prior (Sinkhorn target).
    assert 0.0 < r["attention_sink_fraction"] <= 1.0, r
    # the most-attended key mass equals the max of the learned prior (column marginal == b).
    assert abs(r["attention_sink_fraction"] - max(r["prior_over_keys"])) < 1e-3, \
        (r["attention_sink_fraction"], max(r["prior_over_keys"]))
    # entropy_gap is a signed, finite reported quantity.
    assert isinstance(r["entropy_gap"], (int, float)), r
    assert r["transport_cost_goat"] > 0.0, r
    out["metrics"] = {"transport_cost_goat": r["transport_cost_goat"],
                      "entropy_gap": r["entropy_gap"],
                      "attention_sink_fraction": r["attention_sink_fraction"],
                      "marginal_violation": r["marginal_violation"],
                      "plan_entropy_goat": r["plan_entropy_goat"]}

    assert "arxiv.org/abs/2601.15380" in r["citations"]["goat"], r["citations"]
    out["citations_ok"] = True

    # determinism
    r2 = goat_transport(seed=42, n_query=8, n_key=8)
    assert r2["transport_plan_row0"] == r["transport_plan_row0"], "non-deterministic plan"
    assert r2["entropy_gap"] == r["entropy_gap"], "non-deterministic entropy"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
    print("ALL OK")
