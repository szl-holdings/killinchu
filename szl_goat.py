# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_goat.py — SZL GOAT endpoint: Generalized Optimal-transport Attention with
Trainable priors (attention-as-optimal-transport, removes attention sinks),
MODELED.

Exposes a MODELED closed-form/deterministic simulation of the GOAT attention
mechanism (Jan 2026, arXiv:2601.15380) as a same-origin REST endpoint, so the
GOAT surface organ has a live data source that is honest, deterministic, and
citable — never fabricated, never random-faked, never a run of a real
transformer forward pass with proprietary weights.

  GET  /api/<ns>/v1/goat/transport?seed=&n_q=&n_k=&iters=&reg=&prior=

WHAT IS SIMULATED
------------------
Standard scaled-dot-product attention turns query/key logits S[i,j] into a row
of attention weights via a per-query softmax:

    A_softmax[i, :] = softmax(S[i, :])

Softmax has no constraint on the COLUMN mass: in practice trained transformers
learn to dump large amounts of attention mass onto a few low-information
tokens (very often token 0 / the BOS token) — the well-documented "attention
sink" phenomenon (Xiao et al. 2023, StreamingLLM, arXiv:2309.17453). That mass
is wasted: it does not reflect query→key relevance, it just parks probability
on a null token so the rest of the row can stay sharp.

GOAT reframes each attention row as an ENTROPIC OPTIMAL-TRANSPORT problem
between the query distribution and the key distribution. Given a cost matrix
C = -S (high similarity = low transport cost), a source marginal r (uniform
over queries), and a LEARNABLE target/prior marginal c over keys, GOAT solves

    P* = argmin_{P in U(r,c)}  <P, C>  -  reg * H(P)

where U(r,c) = { P >= 0 : P·1 = r, Pᵀ·1 = c } is the transport polytope and
H(P) is the entropy of the plan. The entropic problem has the classic
Sinkhorn–Knopp closed form: with kernel K = exp(-C / reg), the optimal plan is

    P* = diag(u) · K · diag(v)

where the scaling vectors (u, v) are found by alternately renormalizing rows to
r and columns to the learnable prior c (Cuturi 2013, arXiv:1306.0895):

    u <- r  / (K   · v)        (row scaling  — enforce query marginal)
    v <- c  / (Kᵀ  · u)        (col scaling  — enforce PRIOR key marginal)

Because the COLUMN marginal is pinned to the trainable prior c (here a smooth,
near-uniform prior with NO spike on token 0), no single key can absorb runaway
mass: the sink is structurally removed. The transport plan is then row-
normalized to yield attention weights directly comparable to softmax:

    A_goat[i, :] = P*[i, :] / sum_j P*[i, j]

This module draws entirely SYNTHETIC query/key logits from the pure-stdlib LCG
PRNG below (no numpy, no stdlib `random`), deliberately injects a softmax
attention-sink bias onto token 0 (as trained transformers exhibit), then
computes BOTH the plain-softmax row weights and the GOAT Sinkhorn-OT row
weights, so the two can be shown side by side. It reports the Sinkhorn
convergence trace and a sink-metric for each.

SINK METRIC
-----------
`sink_metric` = mean attention mass landing on the sink token (token 0),
averaged over query rows: mean_i A[i, 0]. For a uniform-relevance baseline this
would be ~1/n_k; softmax pushes it far above that, GOAT pulls it back toward /
below the relevance-justified level. We report:
  sink_softmax    : mean_i A_softmax[i, 0]  (typically inflated — the sink)
  sink_goat       : mean_i A_goat[i, 0]     (typically reduced)
  sink_reduction  : 1 - sink_goat / sink_softmax   (fraction of sink removed)

CONVERGENCE
-----------
`sinkhorn_residuals` is the per-iteration max column-marginal violation
  max_j | (Pᵀ·1)[j] - c[j] |
which decreases monotonically toward 0 as the Sinkhorn iterates converge to a
plan that respects the trainable prior marginal. The surface animates this
trace as the "Sinkhorn convergence" readout.

Returned JSON fields
---------------------
  label               : "MODELED" (always — deterministic re-implementation of
                         the attention-as-OT arithmetic, NOT a live model)
  model               : short description of the simulated setup
  method              : one-line statement of the arithmetic implemented
  seed                : RNG seed used
  n_q                 : number of query rows
  n_k                 : number of key columns (token 0 is the candidate sink)
  iters               : number of Sinkhorn iterations run
  reg                 : entropic regularization strength (Sinkhorn temperature)
  prior               : "learned-smooth" — the trainable near-uniform key prior
  sink_softmax        : mean softmax attention mass on token 0 (the sink)
  sink_goat           : mean GOAT/OT attention mass on token 0
  sink_reduction      : fraction of the attention sink removed by GOAT (0..1)
  sinkhorn_residuals  : list (capped) of per-iteration column-marginal residuals
  attn_softmax_row0   : first query row's softmax attention weights (capped)
  attn_goat_row0      : first query row's GOAT/OT attention weights (capped)
  transport_marginal  : achieved column marginal of P* (capped) — should track
                        the learnable prior c
  converged           : bool — final residual below tolerance
  honest_note         : plain-language honesty disclaimer
  citations           : dict of citable sources
  computed_at         : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the GOAT
  attention-as-optimal-transport arithmetic: an entropic-OT / Sinkhorn–Knopp
  transport plan with a trainable (near-uniform, no-sink) key prior, contrasted
  against a plain softmax row that carries an injected attention sink. It draws
  synthetic query/key logits from the pure-stdlib LCG PRNG below (no numpy, no
  stdlib `random`), applies the exact Sinkhorn scaling recursion (Cuturi 2013),
  and reports the resulting sink metrics and convergence trace. It is NOT a
  trained transformer, uses NO proprietary weights, runs NO real attention
  forward pass, and is NEVER-CLAIMED-AS a production model. The label "MODELED"
  is returned verbatim and displayed verbatim by the surface; never upgraded
  client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  GOAT — Generalized Optimal-transport Attention with Trainable priors
    (attention-as-OT that removes attention sinks; the method simulated here):
    "GOAT: Generalized Optimal-transport Attention with Trainable priors"
    (Jan 2026). arXiv:2601.15380. https://arxiv.org/abs/2601.15380
  Sinkhorn distances / entropic optimal transport (the scaling recursion used):
    Cuturi (2013) "Sinkhorn Distances: Lightspeed Computation of Optimal
    Transport". arXiv:1306.0895. https://arxiv.org/abs/1306.0895
  Attention sinks (the phenomenon GOAT removes — reference only):
    Xiao, Tian, Chen, Han & Lewis (2023) "Efficient Streaming Language Models
    with Attention Sinks" (StreamingLLM). arXiv:2309.17453.
    https://arxiv.org/abs/2309.17453
  NEVER-CLAIMED-AS: this module does not reproduce any project's code, weights,
  or measured benchmark numbers. It is a clean-room MODELED simulation of the
  attention-as-optimal-transport arithmetic those works describe.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
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
    "GOAT — Generalized Optimal-transport Attention with Trainable priors, arXiv:2601.15380": "https://arxiv.org/abs/2601.15380",
    "Sinkhorn Distances — Cuturi 2013, arXiv:1306.0895": "https://arxiv.org/abs/1306.0895",
    "Attention Sinks / StreamingLLM — Xiao et al. 2023, arXiv:2309.17453": "https://arxiv.org/abs/2309.17453",
}

# Cap on how many per-row weights / residual samples we echo back to keep the
# payload bounded for large n_q / n_k / iters.
_MAX_ROW_SAMPLES = 32
_MAX_RES_SAMPLES = 64

# Sinkhorn convergence tolerance on the column-marginal violation.
_SINKHORN_TOL = 1e-6


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
# small pure-Python linear-algebra helpers (row-major lists of lists / lists)
# ---------------------------------------------------------------------------
def _softmax_row(logits: list) -> list:
    """Numerically stable per-row softmax."""
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    z = sum(exps)
    if z <= 0.0:
        n = len(logits)
        return [1.0 / n] * n
    return [e / z for e in exps]


def _build_logits(rng, n_q: int, n_k: int, sink_bias: float) -> list:
    """Synthetic query/key attention logits S[i][j] in a bounded range, with a
    deliberate additive sink bias on key column 0 for EVERY query row — this is
    the trained-transformer attention-sink pathology GOAT is designed to fix.
    Deterministic given the LCG stream."""
    S = []
    for _i in range(n_q):
        row = []
        for j in range(n_k):
            base = -2.0 + 4.0 * next(rng)          # relevance logit in (-2, 2)
            if j == 0:
                base += sink_bias                  # inject the sink on token 0
            row.append(base)
        S.append(row)
    return S


def _learnable_prior(n_k: int) -> list:
    """Trainable target/key prior marginal c for the transport plan. Modeled as
    a smooth, near-uniform prior with NO spike on token 0 — this is precisely
    what pins the column mass and structurally removes the sink. Normalized to
    sum to 1. Deterministic (a fixed smooth shape, no RNG)."""
    # gentle cosine ripple around uniform so the prior is non-degenerate yet
    # carries no privileged mass on any single (esp. the sink) token.
    raw = [1.0 + 0.15 * math.cos(2.0 * math.pi * j / max(n_k, 1)) for j in range(n_k)]
    z = sum(raw)
    return [x / z for x in raw]


def _sinkhorn_ot(S: list, prior: list, reg: float, iters: int):
    """Entropic optimal-transport attention via the Sinkhorn–Knopp scaling
    recursion (Cuturi 2013). Cost C = -S (high similarity -> low cost); source
    marginal r is uniform over queries; target marginal c is the learnable
    key prior. Returns (P, residuals) where P is the transport plan (row-major
    n_q x n_k) and residuals is the per-iteration max column-marginal violation.

    Pure stdlib; deterministic given S, prior, reg, iters.
    """
    n_q = len(S)
    n_k = len(S[0]) if n_q else 0
    r = [1.0 / n_q] * n_q                          # uniform source (query) marginal
    c = list(prior)                                # learnable target (key) marginal

    # kernel K = exp(-C / reg) = exp(S / reg), numerically stabilized per matrix
    smax = max(max(row) for row in S)
    K = [[math.exp((S[i][j] - smax) / reg) for j in range(n_k)] for i in range(n_q)]

    u = [1.0] * n_q
    v = [1.0] * n_k
    residuals = []

    def _marginal_violation() -> float:
        """max marginal violation of the CURRENT plan P=diag(u)K diag(v):
        max( max_i |(P 1)[i]-r[i]| , max_j |(P^T 1)[j]-c[j]| ). This is the
        honest Sinkhorn convergence residual — it starts large (marginals not
        yet satisfied) and decreases monotonically toward 0 as (u,v) converge."""
        mv = 0.0
        for i in range(n_q):
            rowsum = 0.0
            for j in range(n_k):
                rowsum += u[i] * K[i][j] * v[j]
            mv = max(mv, abs(rowsum - r[i]))
        for j in range(n_k):
            colsum = 0.0
            for i in range(n_q):
                colsum += u[i] * K[i][j] * v[j]
            mv = max(mv, abs(colsum - c[j]))
        return mv

    for _ in range(iters):
        # record the residual BEFORE this iteration's correction, so the trace
        # shows the full decreasing convergence curve (not just the tail).
        residuals.append(_marginal_violation())
        if residuals[-1] < _SINKHORN_TOL:
            break
        # u <- r / (K v)      (row scaling: enforce uniform query marginal)
        for i in range(n_q):
            kv = 0.0
            Ki = K[i]
            for j in range(n_k):
                kv += Ki[j] * v[j]
            u[i] = r[i] / kv if kv > 0.0 else 0.0
        # v <- c / (Kᵀ u)     (col scaling: enforce learnable PRIOR key marginal)
        for j in range(n_k):
            ku = 0.0
            for i in range(n_q):
                ku += K[i][j] * u[i]
            v[j] = c[j] / ku if ku > 0.0 else 0.0

    # assemble plan P = diag(u) K diag(v)
    P = [[u[i] * K[i][j] * v[j] for j in range(n_k)] for i in range(n_q)]
    return P, residuals


def _row_normalize(P: list) -> list:
    """Row-normalize a transport plan into attention weights comparable to the
    softmax rows: A[i, :] = P[i, :] / sum_j P[i, j]."""
    A = []
    for row in P:
        z = sum(row)
        if z <= 0.0:
            n = len(row)
            A.append([1.0 / n] * n)
        else:
            A.append([x / z for x in row])
    return A


def _mean_col0(A: list) -> float:
    """Mean attention mass on the sink token (column 0) across query rows."""
    if not A:
        return 0.0
    return sum(row[0] for row in A) / len(A)


# ---------------------------------------------------------------------------
# MODELED attention-as-optimal-transport snapshot (deterministic)
# ---------------------------------------------------------------------------
def _goat_snapshot(seed: int = 42, n_q: int = 12, n_k: int = 16,
                   iters: int = 40, reg: float = 1.0,
                   sink_bias: float = 3.0) -> dict:
    """
    Build synthetic logits (with an injected token-0 sink), then compute BOTH
    plain-softmax attention and GOAT Sinkhorn-OT attention against a learnable
    smooth key prior. Report sink metrics + Sinkhorn convergence trace.

    Pure stdlib; deterministic — same (seed, n_q, n_k, iters, reg) -> identical
    snapshot, every time.
    """
    rng = _lcg(seed)
    S = _build_logits(rng, n_q, n_k, sink_bias)

    # plain softmax attention (carries the injected sink)
    A_soft = [_softmax_row(S[i]) for i in range(n_q)]

    # GOAT: optimal-transport attention with a trainable smooth key prior
    prior = _learnable_prior(n_k)
    P, residuals = _sinkhorn_ot(S, prior, reg, iters)
    A_goat = _row_normalize(P)

    sink_soft = _mean_col0(A_soft)
    sink_goat = _mean_col0(A_goat)
    sink_reduction = (1.0 - sink_goat / sink_soft) if sink_soft > 0.0 else 0.0

    # achieved transport column marginal (should track the learnable prior)
    col_marg = []
    for j in range(n_k):
        col_marg.append(sum(P[i][j] for i in range(n_q)))

    converged = bool(residuals and residuals[-1] < _SINKHORN_TOL)

    return {
        "n_q": n_q,
        "n_k": n_k,
        "iters": iters,
        "reg": round(reg, 6),
        "prior": "learned-smooth",
        "sink_softmax": round(sink_soft, 6),
        "sink_goat": round(sink_goat, 6),
        "sink_reduction": round(sink_reduction, 6),
        "sinkhorn_residuals": [round(x, 9) for x in residuals[:_MAX_RES_SAMPLES]],
        "attn_softmax_row0": [round(x, 6) for x in A_soft[0][:_MAX_ROW_SAMPLES]],
        "attn_goat_row0": [round(x, 6) for x in A_goat[0][:_MAX_ROW_SAMPLES]],
        "transport_marginal": [round(x, 6) for x in col_marg[:_MAX_ROW_SAMPLES]],
        "converged": converged,
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


def _h_transport(req: Request):
    seed  = _ii(req, "seed",  42)
    n_q   = max(1, min(_ii(req, "n_q",   12), 64))
    n_k   = max(2, min(_ii(req, "n_k",   16), 64))
    iters = max(1, min(_ii(req, "iters", 40), 500))
    reg   = min(max(_ff(req, "reg", 1.0), 1e-3), 10.0)

    snap = _goat_snapshot(seed=seed, n_q=n_q, n_k=n_k, iters=iters, reg=reg)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "GOAT: attention reframed as entropic optimal transport (Sinkhorn) with a trainable key prior that removes attention sinks",
        "method": "cost C=-S; source marginal uniform over queries, target marginal = learnable smooth key prior; Sinkhorn scaling u<-r/(Kv), v<-c/(K^T u) with K=exp(S/reg); plan row-normalized to attention weights; softmax row carries an injected token-0 sink for contrast",
        "seed":   seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the GOAT "
            "attention-as-optimal-transport arithmetic (arXiv:2601.15380) — an entropic-OT / "
            "Sinkhorn-Knopp transport plan (Cuturi 2013, arXiv:1306.0895) whose column marginal "
            "is pinned to a trainable near-uniform key prior, which structurally removes the "
            "'attention sink' (Xiao et al. 2023, arXiv:2309.17453) that a plain softmax row dumps "
            "onto token 0. Synthetic query/key logits are drawn from a deterministic LCG PRNG (no "
            "numpy, no stdlib random, no proprietary weights, no real transformer forward pass). "
            "The Sinkhorn recursion and softmax are the exact arithmetic from the cited works; SZL "
            "claims NONE of these methods as its own and reproduces NO project's code, weights, or "
            "measured benchmarks. Deterministic: same seed/n_q/n_k/iters/reg -> identical snapshot."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_specdecode.register() / szl_grpo.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/goat/transport onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/goat"
    handlers = [
        (f"{base}/transport", _h_transport),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        # additive + guarded: never break the host app on wiring failure
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _goat_snapshot(seed=42, n_q=12, n_k=16, iters=40, reg=1.0)
    print("label: MODELED")
    print("n_q:", snap["n_q"])
    print("n_k:", snap["n_k"])
    print("iters:", snap["iters"])
    print("reg:", snap["reg"])
    print("prior:", snap["prior"])
    print("sink_softmax:", snap["sink_softmax"])
    print("sink_goat:", snap["sink_goat"])
    print("sink_reduction:", snap["sink_reduction"])
    print("converged:", snap["converged"])
    print("sinkhorn_residuals[:6]:", snap["sinkhorn_residuals"][:6])
    print("attn_softmax_row0[:6]:", snap["attn_softmax_row0"][:6])
    print("attn_goat_row0[:6]:", snap["attn_goat_row0"][:6])

    # sanity: probability rows sum to ~1
    assert abs(sum(snap["attn_softmax_row0"]) - 1.0) < 0.05 or len(snap["attn_softmax_row0"]) < snap["n_k"], "softmax row not normalized"
    # sanity: sink metrics are valid probabilities in [0,1]
    assert 0.0 <= snap["sink_softmax"] <= 1.0, "sink_softmax out of [0,1]"
    assert 0.0 <= snap["sink_goat"] <= 1.0, "sink_goat out of [0,1]"
    # sanity: GOAT reduces the sink relative to softmax (the whole point)
    assert snap["sink_goat"] <= snap["sink_softmax"], "GOAT did not reduce the attention sink"
    assert 0.0 <= snap["sink_reduction"] <= 1.0, "sink_reduction out of [0,1]"
    # sanity: Sinkhorn residuals are monotonically non-increasing (convergence)
    res = snap["sinkhorn_residuals"]
    assert all(res[k + 1] <= res[k] + 1e-9 for k in range(len(res) - 1)), "Sinkhorn residuals not decreasing"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _goat_snapshot(seed=42, n_q=12, n_k=16, iters=40, reg=1.0)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: a different seed changes the logits yet the GOAT invariant holds
    snap3 = _goat_snapshot(seed=7, n_q=12, n_k=16, iters=40, reg=1.0)
    assert 0.0 <= snap3["sink_goat"] <= snap3["sink_softmax"], "GOAT invariant broken on alt seed"
    assert snap3 != snap, "different seed must change the snapshot"

    print()
    print("szl_goat: ALL OK — deterministic, sink reduced by GOAT, Sinkhorn converging.")
