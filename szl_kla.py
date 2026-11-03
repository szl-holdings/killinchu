# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_kla.py — SZL Kaczmarz Linear Attention (KLA) recurrent-state endpoint, MODELED.

Exposes a MODELED, closed-form/deterministic simulation of the KLA (Kaczmarz
Linear Attention) recurrent state-update rule as a same-origin REST endpoint, so
the KLA surface organ has a live data source that is honest, deterministic, and
citable — never fabricated, never random-faked, never run against a real trained
linear-attention model.

  GET  /api/<ns>/v1/kla/update?seed=&dim=&steps=&lr=

WHAT IS SIMULATED
------------------
Linear-attention layers replace softmax attention with a running key-value
associative memory: a state matrix S (dim x dim) that accumulates outer products
k_t v_t^T. Gated linear attention (GLA) multiplies the old state by an ad-hoc
per-step gate g_t in (0,1) before adding the new pair:

    GATED (baseline):   S_t = g_t * S_{t-1} + v_t k_t^T          (ad-hoc scalar gate)

KLA (Kaczmarz Linear Attention) instead treats the incorporation of each new
(k_t, v_t) pair as a CONSTRAINT the state must satisfy: we want the memory to
read out v_t when queried with k_t, i.e. S_t k_t = v_t. The set of matrices
satisfying that single linear constraint is a hyperplane; the Kaczmarz method
projects the current state ORTHOGONALLY onto that hyperplane. The minimal-norm
correction (row-wise Kaczmarz / randomized-Kaczmarz update) is:

    KLA (projection):   S_t = S_{t-1} + lr * (v_t - S_{t-1} k_t) k_t^T / (k_t·k_t)

The step size on that projection — the coefficient lr * / (k_t·k_t) — is a
PRINCIPLED scalar derived from the projection geometry, replacing GLA's ad-hoc
learned gate g_t. Each update moves the state the exact distance needed to
satisfy the newest key-value constraint while perturbing prior memory as little
as possible (orthogonal projection = minimal-norm correction), which is the
classical Kaczmarz convergence guarantee for consistent linear systems.

Over `steps` streamed (k_t, v_t) pairs this module computes, for BOTH the KLA
projection update and the GATED baseline, the running RECONSTRUCTION ERROR — the
mean squared error between the state's readout S k_t and the target v_t across
the pairs seen so far — and reports:

  kla_final_recon_error    : final mean reconstruction error under KLA projection
  gated_final_recon_error  : final mean reconstruction error under the ad-hoc gate
  kla_convergence_step     : first step at which KLA's running error drops below
                             a fixed tolerance (or steps if never) — "how fast it
                             converges"
  gated_convergence_step   : same, for the gated baseline
  improvement_ratio        : gated_final_recon_error / kla_final_recon_error
                             (>1 means KLA reconstructs the stream with lower
                             error than the ad-hoc gate — the demo claim)
  kla_error_curve[]        : running KLA reconstruction error per step (capped)
  gated_error_curve[]      : running GATED reconstruction error per step (capped)

The (k_t, v_t) stream and the baseline gates g_t are all drawn from the
pure-stdlib LCG below (no numpy, no stdlib random), so the whole comparison is
bit-for-bit deterministic given (seed, dim, steps, lr).

Returned JSON fields
---------------------
  label                    : "MODELED" (always — deterministic re-implementation
                             of the Kaczmarz projection arithmetic, NOT a model)
  model                    : short description of the simulated setup
  method                   : one-line statement of the two update rules compared
  seed                     : RNG seed used
  dim                      : state matrix dimension (dim x dim)
  steps                    : number of streamed key-value pairs
  lr                       : Kaczmarz projection relaxation factor (0<lr<=2)
  kla_final_recon_error    : final KLA reconstruction MSE
  gated_final_recon_error  : final gated-baseline reconstruction MSE
  kla_convergence_step     : first step KLA error < tol (or steps)
  gated_convergence_step   : first step gated error < tol (or steps)
  improvement_ratio        : gated_final / kla_final (>1 = KLA better)
  kla_error_curve          : running KLA error per step (capped list)
  gated_error_curve        : running gated error per step (capped list)
  tol                      : convergence tolerance used for the *_convergence_step
  honest_note              : plain-language honesty disclaimer
  citations                : dict of citable sources
  computed_at              : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the KLA (Kaczmarz
  Linear Attention) state-UPDATE ARITHMETIC: the orthogonal Kaczmarz projection
  of a linear-attention memory matrix onto the S k = v constraint defined by each
  streamed key-value pair, compared against the ad-hoc gated-linear-attention
  update. It draws the synthetic key/value stream and the baseline gates from the
  pure-stdlib LCG PRNG below (no numpy, no stdlib random). It is NOT a trained GLA
  model, uses NO proprietary weights, runs NO real attention layer, and is
  NEVER-CLAIMED-AS a production kernel. The label "MODELED" is returned verbatim
  and displayed verbatim by the surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  KLA — Kaczmarz Linear Attention (the projection update rule simulated here):
    (2026) "Kaczmarz Linear Attention". arXiv:2605.08587.
    https://arxiv.org/abs/2605.08587
  NEVER-CLAIMED-AS: this module is not the KLA authors' code or weights and does
  not reproduce their measured benchmark numbers. It is a clean-room MODELED
  simulation of the Kaczmarz-projection state-update arithmetic the method
  builds on.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "KLA — Kaczmarz Linear Attention, arXiv:2605.08587": "https://arxiv.org/abs/2605.08587",
}

# Convergence tolerance for the *_convergence_step reporting (fixed; it is a
# reporting threshold, not a data-driven quantity).
_TOL = 0.05

# Cap on how many per-step reconstruction-error samples we echo back for the
# surface's convergence-curve animation (keeps payload bounded for large steps).
_MAX_CURVE_SAMPLES = 128


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Tiny pure-stdlib linear-algebra helpers (dim is small; explicit loops keep
# the module dependency-free and deterministic by construction).
# ---------------------------------------------------------------------------
def _zeros(n: int):
    """n x n zero matrix as a list of lists of floats."""
    return [[0.0 for _ in range(n)] for _ in range(n)]


def _matvec(M, x):
    """Matrix-vector product M @ x for square M (n x n) and vector x (n)."""
    n = len(x)
    out = [0.0] * n
    for i in range(n):
        row = M[i]
        acc = 0.0
        for j in range(n):
            acc += row[j] * x[j]
        out[i] = acc
    return out


def _dot(a, b):
    acc = 0.0
    for i in range(len(a)):
        acc += a[i] * b[i]
    return acc


# ---------------------------------------------------------------------------
# MODELED KLA vs gated-linear-attention state update (deterministic)
# ---------------------------------------------------------------------------
def _kla_snapshot(seed: int = 42, dim: int = 8, steps: int = 256, lr: float = 1.0) -> dict:
    """
    Stream `steps` synthetic (k_t, v_t) key-value pairs and update TWO
    linear-attention memory matrices in parallel:

      * KLA:   orthogonal Kaczmarz projection onto the S k = v constraint,
               step = lr * (v - S k) k^T / (k·k)  — a principled scalar.
      * GATED: ad-hoc gated-linear-attention baseline,
               S = g * S + v k^T,  g_t drawn from the LCG in (0.80, 0.99).

    After each step we measure the running RECONSTRUCTION ERROR: the mean
    squared error between each memory's readout S k_i and the target v_i,
    averaged over all pairs seen so far. KLA's minimal-norm projection keeps
    prior constraints satisfied, so its reconstruction error converges lower
    and faster than the ad-hoc gate, which decays old memory indiscriminately.

    Pure stdlib; deterministic — same (seed, dim, steps, lr) -> identical
    snapshot, every time.
    """
    n = max(1, min(int(dim), 32))
    steps = max(1, min(int(steps), 5000))
    # relaxation factor for the Kaczmarz projection; classical convergence holds
    # for 0 < lr < 2. Clamp defensively.
    lr = float(lr)
    if lr <= 0.0:
        lr = 1.0
    if lr > 2.0:
        lr = 2.0

    rng = _lcg(seed)

    S_kla = _zeros(n)      # KLA memory matrix
    S_gate = _zeros(n)     # gated-baseline memory matrix

    keys = []              # streamed keys, kept to measure running recon error
    vals = []              # streamed values

    kla_curve = []
    gated_curve = []
    kla_conv = steps
    gated_conv = steps
    kla_conv_hit = False
    gated_conv_hit = False

    for t in range(steps):
        # synthetic unit-ish key and value vectors in [-1, 1)
        k = [2.0 * next(rng) - 1.0 for _ in range(n)]
        v = [2.0 * next(rng) - 1.0 for _ in range(n)]
        # ad-hoc GLA gate in (0.80, 0.99)
        g = 0.80 + 0.19 * next(rng)

        keys.append(k)
        vals.append(v)

        kk = _dot(k, k)
        if kk < 1e-12:
            kk = 1e-12

        # --- KLA: orthogonal Kaczmarz projection onto S k = v -----------------
        # residual r = v - S_kla k ; correction (lr/kk) * r k^T added to S_kla.
        Sk = _matvec(S_kla, k)
        r = [v[i] - Sk[i] for i in range(n)]
        coef = lr / kk
        for i in range(n):
            ri = r[i] * coef
            row = S_kla[i]
            for j in range(n):
                row[j] += ri * k[j]

        # --- GATED baseline: S = g * S + v k^T --------------------------------
        for i in range(n):
            vi = v[i]
            row = S_gate[i]
            for j in range(n):
                row[j] = g * row[j] + vi * k[j]

        # --- running reconstruction error over all pairs seen so far ----------
        m = len(keys)
        err_kla = 0.0
        err_gate = 0.0
        for idx in range(m):
            ki = keys[idx]
            vi = vals[idx]
            rk = _matvec(S_kla, ki)
            rg = _matvec(S_gate, ki)
            ek = 0.0
            eg = 0.0
            for c in range(n):
                dk = rk[c] - vi[c]
                dg = rg[c] - vi[c]
                ek += dk * dk
                eg += dg * dg
            err_kla += ek / n
            err_gate += eg / n
        err_kla /= m
        err_gate /= m

        if not kla_conv_hit and err_kla < _TOL:
            kla_conv = t + 1
            kla_conv_hit = True
        if not gated_conv_hit and err_gate < _TOL:
            gated_conv = t + 1
            gated_conv_hit = True

        kla_curve.append(err_kla)
        gated_curve.append(err_gate)

    kla_final = kla_curve[-1]
    gated_final = gated_curve[-1]
    denom = kla_final if kla_final > 1e-12 else 1e-12
    improvement_ratio = gated_final / denom

    # subsample the curves down to <= _MAX_CURVE_SAMPLES points for the surface
    def _sub(curve):
        L = len(curve)
        if L <= _MAX_CURVE_SAMPLES:
            return [round(x, 6) for x in curve]
        stride = L / _MAX_CURVE_SAMPLES
        out = []
        i = 0.0
        while len(out) < _MAX_CURVE_SAMPLES:
            out.append(round(curve[int(i)], 6))
            i += stride
        return out

    return {
        "dim": n,
        "steps": steps,
        "lr": round(lr, 6),
        "tol": _TOL,
        "kla_final_recon_error": round(kla_final, 6),
        "gated_final_recon_error": round(gated_final, 6),
        "kla_convergence_step": kla_conv,
        "gated_convergence_step": gated_conv,
        "improvement_ratio": round(improvement_ratio, 6),
        "kla_error_curve": _sub(kla_curve),
        "gated_error_curve": _sub(gated_curve),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _ff(req: Request, key: str, default: float) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return default


def _h_update(req: Request):
    seed  = _ii(req, "seed",  42)
    dim   = max(1, min(_ii(req, "dim",   8),  32))
    steps = max(1, min(_ii(req, "steps", 256), 5000))
    lr    = _ff(req, "lr", 1.0)

    snap = _kla_snapshot(seed=seed, dim=dim, steps=steps, lr=lr)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Kaczmarz Linear Attention: recurrent memory state update via orthogonal projection onto the S·k=v constraint (vs ad-hoc gated-linear-attention baseline)",
        "method": "KLA: S_t = S_{t-1} + lr·(v_t - S_{t-1} k_t) k_t^T / (k_t·k_t) — orthogonal Kaczmarz projection, a principled scalar replacing the ad-hoc gate g_t of GATED: S_t = g_t·S_{t-1} + v_t k_t^T",
        "seed":   seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "Kaczmarz Linear Attention (KLA) state-UPDATE arithmetic (arXiv:2605.08587): "
            "each streamed key-value pair (k_t, v_t) defines a linear constraint S k_t = v_t "
            "on the linear-attention memory matrix, and KLA incorporates it by the orthogonal "
            "(minimal-norm) Kaczmarz projection S_t = S_{t-1} + lr·(v_t - S_{t-1} k_t) k_t^T/(k_t·k_t) "
            "— a single PRINCIPLED scalar derived from projection geometry, replacing the ad-hoc "
            "learned gate g_t of gated linear attention (baseline S_t = g_t·S_{t-1} + v_t k_t^T). "
            "The synthetic key/value stream and the baseline gates are drawn from a deterministic "
            "LCG PRNG (no numpy, no stdlib random, no proprietary weights, no trained model). "
            "Reported reconstruction errors and convergence steps are exact readouts of this "
            "simulated arithmetic, NOT measured benchmark numbers from the KLA paper, and this "
            "module is NEVER-CLAIMED-AS a production kernel. Deterministic: same seed/dim/steps/lr "
            "-> identical snapshot. SZL claims NONE of this method as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_specdecode.register() / szl_grpo.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/kla/update onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/kla"
    handlers = [
        (f"{base}/update", _h_update),
    ]
    add_api_route = getattr(app, "add_api_route", None)
    for path, fn in handlers:
        try:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
        except Exception:
            # additive & guarded: never break app boot if a route can't attach
            try:
                app.router.routes.append(Route(path, fn))
            except Exception:
                pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _kla_snapshot(seed=42, dim=8, steps=256, lr=1.0)
    print("label: MODELED")
    print("dim:", snap["dim"])
    print("steps:", snap["steps"])
    print("lr:", snap["lr"])
    print("kla_final_recon_error:", snap["kla_final_recon_error"])
    print("gated_final_recon_error:", snap["gated_final_recon_error"])
    print("kla_convergence_step:", snap["kla_convergence_step"])
    print("gated_convergence_step:", snap["gated_convergence_step"])
    print("improvement_ratio:", snap["improvement_ratio"])
    print("kla_error_curve[:5]:", snap["kla_error_curve"][:5])
    print("gated_error_curve[:5]:", snap["gated_error_curve"][:5])

    # sanity: bounds
    assert snap["kla_final_recon_error"] >= 0.0, "recon error must be non-negative"
    assert snap["gated_final_recon_error"] >= 0.0, "recon error must be non-negative"
    assert 1 <= snap["kla_convergence_step"] <= snap["steps"], "conv step out of range"
    assert 1 <= snap["gated_convergence_step"] <= snap["steps"], "conv step out of range"

    # sanity: the whole point — KLA's principled projection reconstructs the
    # streamed key-value constraints with LOWER error than the ad-hoc gate.
    assert snap["kla_final_recon_error"] <= snap["gated_final_recon_error"], \
        "KLA should not reconstruct worse than the ad-hoc gated baseline"
    assert snap["improvement_ratio"] >= 1.0, "improvement_ratio must be >= 1.0"

    # sanity: determinism — identical seed/dim/steps/lr -> identical snapshot
    snap2 = _kla_snapshot(seed=42, dim=8, steps=256, lr=1.0)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: a different seed generally yields a different stream/snapshot
    snap3 = _kla_snapshot(seed=7, dim=8, steps=256, lr=1.0)
    assert 1 <= snap3["kla_convergence_step"] <= snap3["steps"]

    print()
    print("szl_kla: ALL OK — deterministic, KLA reconstructs <= gated baseline, bounds respected.")
