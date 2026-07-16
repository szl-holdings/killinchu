# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_kan.py — ADDITIVE Kolmogorov-Arnold Network spline-fit organ for killinchu's
frontier surface (backs a11oy static/3d/surfaces/kan.js).

Kolmogorov-Arnold Networks (Liu et al. 2024, arXiv:2404.19756) replace the fixed node
activations of an MLP with LEARNABLE univariate functions on the edges, parametrized as
B-splines. There are no linear weight matrices; every "weight" is a 1-D spline. The design
is inspired by the Kolmogorov-Arnold representation theorem: any multivariate continuous
function f(x_1..x_n) can be written as a finite composition of continuous univariate
functions and additions. KANs stack such univariate-plus-sum layers and fit the spline
coefficients to data, giving smaller, more interpretable models than MLPs on many fits.

Deterministic MODELED formulation (seeded, no autograd, no GPU):
  * Target: a 1-D scalar function f(x) that the theorem-style KAN edge should represent —
    here a fixed smooth composite (sin + quadratic) sampled on a grid in [-1, 1].
  * Spline basis: G uniform knots -> (G-1) linear B-spline hat basis functions phi_j(x)
    (order-1 splines; deterministic, pure stdlib). The KAN edge function is
        phi(x) = sum_j c_j * B_j(x).
  * Fit: least squares for coefficients c_j via normal equations solved with a small
    pure-Python Gaussian elimination (deterministic). This is the univariate-spline-on-an-
    edge fit that is the core KAN primitive.
  * Report: RMSE of the fit, number of spline knots / basis functions, an interpretability
    proxy (fraction of coefficient L1-mass in the top-k basis functions — KANs are sparse
    and inspectable), and a parameter-count comparison to an equivalent-width MLP.

  rmse            = sqrt(mean((f(x) - phi(x))^2))
  mlp_params      = width*(1+in) + width  (a like-capacity 1-hidden-layer MLP, MODELED)
  kan_params      = (G-1) spline coefficients on the single edge
  param_ratio     = kan_params / mlp_params

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic least-squares spline fit of ONE KAN edge function. NOT the pykan
    package running; NO autograd, NO GPU, NO trained deep KAN; the spline order is 1 (linear
    hat basis), a faithful but small stand-in for the paper's higher-order B-splines.
  * The parameter-count comparison is an order-of-magnitude MODELED reference, not a measured
    benchmark against a specific MLP checkpoint.
  * The interpretability proxy is a coefficient-mass statistic, not a human study.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/kan/fit  — Kolmogorov-Arnold spline-edge fit snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | SPLINE_LSQ_FIT | NOT_LIVE | NO_AUTOGRAD | PARAMS_ARE_MODELED"

CITATIONS = {
    "kan": ("Liu, Wang, Vaidya, Ruehle, Halverson, Soljačić, Hou, Tegmark (2024) "
            "KAN: Kolmogorov-Arnold Networks — arXiv:2404.19756"),
    "kan_url": "https://arxiv.org/abs/2404.19756",
}


class _LCG:
    """Small seeded linear-congruential PRNG (pure stdlib, deterministic)."""
    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)

    def random(self) -> float:
        self._s = (self._s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((self._s >> 11) & ((1 << 53) - 1)) / float(1 << 53)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _target(x: float) -> float:
    """Fixed smooth composite the KAN edge must represent (deterministic)."""
    return _math.sin(2.4 * x) + 0.5 * x * x


def _hat_basis(x: float, knots: list[float], j: int) -> float:
    """Linear B-spline (hat) basis function centered on knot j."""
    n = len(knots)
    xj = knots[j]
    left = knots[j - 1] if j - 1 >= 0 else knots[0] - (knots[1] - knots[0])
    right = knots[j + 1] if j + 1 < n else knots[-1] + (knots[-1] - knots[-2])
    if x <= left or x >= right:
        return 0.0
    if x <= xj:
        return (x - left) / (xj - left) if xj != left else 0.0
    return (right - x) / (right - xj) if right != xj else 0.0


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Deterministic Gaussian elimination with partial pivoting (pure stdlib)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        if abs(pv) < 1e-12:
            pv = 1e-12
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / pv
            for k in range(col, n + 1):
                m[r][k] -= f * m[col][k]
    return [m[i][n] / (m[i][i] if abs(m[i][i]) > 1e-12 else 1e-12) for i in range(n)]


def kan_fit(seed: int = 42, grid: int = 12, samples: int = 128, width: int = 16) -> dict:
    """Kolmogorov-Arnold spline-edge fit snapshot (MODELED).

    grid    — number of spline knots G on the KAN edge (basis = G-1 hat functions).
    samples — number of sample points of the target f(x) on [-1, 1].
    width   — width of the equivalent-capacity MLP for the parameter comparison.
    seed    — RNG seed; identical inputs give identical output (deterministic).
    """
    grid = max(3, min(64, int(grid)))
    samples = max(8, min(4096, int(samples)))
    width = max(2, min(1024, int(width)))
    rng = _LCG(int(seed) * 1_000_003 + grid * 131 + samples)

    knots = [-1.0 + 2.0 * i / (grid - 1) for i in range(grid)]
    nb = grid  # one coefficient per knot for the hat basis

    # sample points: deterministic jittered grid over [-1, 1]
    xs = []
    for i in range(samples):
        base = -1.0 + 2.0 * i / (samples - 1)
        jit = (rng.random() - 0.5) * (2.0 / samples) * 0.5
        xs.append(max(-1.0, min(1.0, base + jit)))
    ys = [_target(x) for x in xs]

    # design matrix Phi (samples x nb), then normal equations Phi^T Phi c = Phi^T y
    phi = [[_hat_basis(x, knots, j) for j in range(nb)] for x in xs]
    ata = [[0.0] * nb for _ in range(nb)]
    aty = [0.0] * nb
    for r in range(samples):
        row = phi[r]
        yr = ys[r]
        for i in range(nb):
            ri = row[i]
            if ri == 0.0:
                continue
            aty[i] += ri * yr
            for j in range(nb):
                ata[i][j] += ri * row[j]
    # tiny ridge for numerical stability (deterministic, MODELED regularizer)
    for i in range(nb):
        ata[i][i] += 1e-6
    coeffs = _solve(ata, aty)

    # RMSE of the fit
    sse = 0.0
    for r in range(samples):
        pred = sum(phi[r][j] * coeffs[j] for j in range(nb))
        sse += (ys[r] - pred) ** 2
    rmse = _math.sqrt(sse / samples)

    # interpretability proxy: fraction of L1 coefficient mass in the top-4 basis funcs
    l1 = sorted((abs(c) for c in coeffs), reverse=True)
    total_l1 = sum(l1) or 1e-12
    topk_frac = sum(l1[:4]) / total_l1

    # parameter comparison to a like-width 1-hidden-layer MLP (MODELED reference)
    mlp_params = width * (1 + 1) + width + 1  # in=1, out=1
    kan_params = nb
    param_ratio = kan_params / mlp_params

    return {
        "service": "kolmogorov-arnold-spline-fit",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/kan.js ---
        "grid": int(grid),
        "n_basis": int(nb),
        "samples": int(samples),
        "rmse": round(float(rmse), 8),
        "topk_coeff_mass_frac": round(float(topk_frac), 6),
        "kan_params": int(kan_params),
        "mlp_params": int(mlp_params),
        "param_ratio_kan_over_mlp": round(float(param_ratio), 6),
        "spline_coeffs": [round(float(c), 5) for c in coeffs[:16]],
        "knots": [round(float(k), 5) for k in knots[:16]],
        "formulas": {
            "edge_function": "phi(x) = sum_j c_j * B_j(x)  (B_j = linear hat basis)",
            "rmse": "sqrt(mean((f(x) - phi(x))^2))",
            "fit": "normal equations (Phi^T Phi + 1e-6 I) c = Phi^T y, Gaussian elimination",
            "param_ratio": "kan_params / mlp_params",
        },
        "compute_backend": {
            "backend": "CPU pure-Python least-squares hat-spline fit",
            "label": "MODELED",
            "honest_note": ("Deterministic order-1 spline fit of ONE KAN edge; NO pykan, NO "
                            "autograd, NO GPU, NO trained deep KAN. Higher-order B-splines and "
                            "a full KAN stack are ROADMAP."),
        },
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (fit advisory — never an autonomous action)",
        "wired_into": "frontier ring — Kolmogorov-Arnold surface",
        "honest_note": ("MODELED deterministic least-squares fit of one KAN spline edge. Faithful "
                        "to the paper's learnable-univariate-function-on-an-edge primitive, but "
                        "small (order-1 hat basis) and NOT the pykan package; params are a MODELED "
                        "reference. MODELED, not live; advisory to Λ (Conjecture 1)."),
        "citations": {"kan": CITATIONS["kan"], "kan_url": CITATIONS["kan_url"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/kan" % ns

    @app.get("%s/fit" % base)
    async def _kc_kan(seed: int = 42, grid: int = 12, samples: int = 128, width: int = 16):  # noqa: ANN202
        try:
            return JSONResponse(kan_fit(seed=seed, grid=grid, samples=samples, width=width))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "kolmogorov-arnold-spline-fit",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "rmse": None}, status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401
    except Exception:  # pragma: no cover
        pass
    return {"ok": True, "ns": ns, "routes": ["%s/fit" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = kan_fit(seed=42, grid=12, samples=128, width=16)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("grid", "n_basis", "samples", "kan_params", "mlp_params"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("rmse", "topk_coeff_mass_frac", "param_ratio_kan_over_mlp"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["spline_coeffs"], list) and r["spline_coeffs"], r
    assert r["rmse"] >= 0.0, r
    # a 12-knot spline should fit the smooth target reasonably well
    assert r["rmse"] < 0.25, r["rmse"]
    assert 0.0 < r["topk_coeff_mass_frac"] <= 1.0, r
    assert r["kan_params"] < r["mlp_params"], r  # KAN is more compact here
    assert "2404.19756" in r["citations"]["kan"], r
    out["metrics"] = {"rmse": r["rmse"], "topk_coeff_mass_frac": r["topk_coeff_mass_frac"],
                      "kan_params": r["kan_params"], "mlp_params": r["mlp_params"],
                      "param_ratio": r["param_ratio_kan_over_mlp"]}

    # determinism: same inputs -> identical fit
    r2 = kan_fit(seed=42, grid=12, samples=128, width=16)
    assert r2["spline_coeffs"] == r["spline_coeffs"], "non-deterministic"
    assert r2["rmse"] == r["rmse"], "non-deterministic rmse"
    out["deterministic"] = True

    p = register(_FakeApp())
    assert p["routes"] == ["/api/killinchu/v1/kan/fit"], p
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
    print("rmse=%.6f  topk_mass=%.4f  kan_params=%d  mlp_params=%d  ratio=%.4f"
          % (res["metrics"]["rmse"], res["metrics"]["topk_coeff_mass_frac"],
             res["metrics"]["kan_params"], res["metrics"]["mlp_params"],
             res["metrics"]["param_ratio"]))
    assert res["ok"]
    print("ALL OK")
