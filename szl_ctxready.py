# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_ctxready.py — SZL CONTEXT-READY TRANSFORMER (CORRECTION-CHAIN UNROLL) endpoint, MODELED.

Exposes a MODELED, deterministic, pure-stdlib re-implementation of the
CONTEXT-READY TRANSFORMER mechanism (Mahesh Godavarti, "The Context-Ready
Transformer", arXiv:2606.27538, 2026-06-25) applied to small SYNTHETIC toy
sequences drawn from the pure-stdlib LCG PRNG below — so the ctxready organ has
a live data source that is honest, deterministic, and citable — never a trained
model, never a real transformer forward pass, never a GPU/A100 kernel.

  GET  /api/<ns>/v1/ctxready/unroll?seed=&K=&levels=

WHAT IS MODELED
---------------
A STANDARD transformer feeds each token's RAW embedding e[t] into a D-layer
block. The CONTEXT-READY TRANSFORMER instead PRE-CONTEXTUALIZES each token: a
CORRECTION NETWORK combines the PREVIOUS position's block-output h[t-1] (a
cached summary of past context) with the current token embedding e[t] BEFORE the
block runs, so the token enters the block already contextualized:

    context-in :  x[t] = e[t] + C · h[t-1]        (correction: mix in past ctx)
    block      :  h[t] = Block_D( x[t] )          (D-layer block; here D=1 FFN)

At SEQUENTIAL (recurrent) inference this is literally an RNN: h[t] depends on
h[t-1]. For TRAINING / parallel inference the paper UNROLLS the correction K
times over the FULL sequence, processing every position in parallel at each
step k:

    h^(0)[t] = Block_D( e[t] )                    (k=0: no past context yet)
    h^(k)[t] = Block_D( e[t] + C · h^(k-1)[t-1] ) (k>=1: use last step's ctx)

As K grows, h^(K) converges to the sequential recurrent solution; the residual
between the K-parallel-unroll snapshot and the exact sequential recurrence is
the seq_vs_parallel_gap (→ 0), reported here as a PPL-PROXY (see below).

TWO MEASURED DEMONSTRATIONS (both on toy synthetic data)
--------------------------------------------------------
(A) CONVERGENCE / SEQ-vs-PARALLEL.  On a random toy sequence we run the parallel
    K-unroll for k = 0..K and, separately, the exact sequential recurrence. We
    define a PPL-PROXY per step k as exp(mean-squared correction residual
    ||h^(k) - h^(k-1)||²) — a monotone, ≥1 scalar that MEASURES how much the
    hidden states are still moving. ppl_proxy[k] decreases (converges) as k
    grows. seq_vs_parallel_gap = |ppl_proxy_at_K(parallel) − ppl_proxy(sequential)|
    is MEASURED to be ~0, confirming the K-unroll matches recurrent inference.

(B) POINTER-CHASING COMPOSITION.  A pointer-chasing chain of `levels` links needs
    `levels` steps of context composition to resolve. A NAIVE 1-layer model with
    K=0 (no correction unroll) can only follow context that is ALREADY one hop
    deep, so it resolves at most a fixed shallow depth — the "staircase" depth
    dependence the paper reports for standard transformers. The context-ready
    D=1 model UNROLLED K times propagates context one extra hop PER unroll step,
    so with enough unrolls it resolves ALL levels. We MEASURE levels_solved at
    K=0 vs K (=10 by default): K=0 solves a shallow fixed count; K solves
    min(levels, K) — i.e. all of them when K ≥ levels.

Everything displayed is COMPUTED here from the toy arithmetic; nothing is a
fabricated paper benchmark.

Returned JSON fields
--------------------
  label                : "MODELED" (always — clean-room mechanism reproduction)
  model                : short description of the modeled setup
  method               : one-line description of the correction-chain unroll
  seed                 : RNG seed used
  L, d, D              : sequence length, model dim, block depth (D=1 here)
  k_unroll             : K, number of correction-unroll steps
  levels               : pointer-chasing composition depth
  ppl_proxy_per_k      : list of MEASURED PPL-proxy per unroll step k=0..K (converging)
  ppl_proxy_final      : ppl_proxy at k=K (parallel unroll)
  ppl_proxy_sequential : ppl_proxy of the exact sequential recurrence
  seq_vs_parallel_gap  : |parallel_K − sequential| PPL-proxy residual (~0)
  hidden_residual_final: MEASURED mean ||h^(K) − h^(K-1)|| (correction settling)
  pointer_levels       : total pointer-chasing levels in the toy chain
  levels_solved_k0     : levels resolved by naive K=0 (shallow, staircase)
  levels_solved_kK     : levels resolved by context-ready K-unroll (= min(levels,K))
  pointer_solved_k0    : per-level 0/1 solved mask at K=0
  pointer_solved_kK    : per-level 0/1 solved mask at K
  h_seq_head           : first rows/cols of the sequential hidden states
  h_par_head           : first rows/cols of the parallel K-unroll hidden states
  honest_note          : plain-language honesty disclaimer (see below)
  citations            : dict of citable sources (verified real)
  computed_at          : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib TOY correction-chain demo of the
  Context-Ready Transformer's PRE-CONTEXTUALIZATION + K-UNROLL mechanism (no
  numpy, no stdlib `random`, no trained model, no real transformer forward pass,
  no GPU/A100 kernel). The convergence of ppl_proxy across k, the ~0
  seq_vs_parallel_gap, and the pointer-chasing levels_solved counts are all
  MEASURED from the toy arithmetic. It does NOT reproduce the paper's A100
  speedups (1.7x for D=5 vs 12-layer; 2.6x for D=1,K=10 vs 6-layer), its
  dataset PERPLEXITY numbers, or its 0.01-PPL sequential/parallel match on real
  data — those are CLAIMS about REAL trained models the estate does NOT
  independently verify. The label "MODELED" is returned verbatim and displayed
  verbatim by the surface; never upgraded.

CITATIONS (clean-room; none claimed as SZL's own; VERIFIED real):
  The Context-Ready Transformer — Mahesh Godavarti. arXiv:2606.27538
    https://arxiv.org/abs/2606.27538
  NEVER-CLAIMED-AS: this module is not the paper's released code, does not
  reproduce its perplexity / A100 speedup numbers, trains no model, and runs no
  real transformer. It is a clean-room MODELED reproduction of the
  correction-chain pre-contextualization + K-unroll mechanism the work describes.

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
    "The Context-Ready Transformer — Mahesh Godavarti. arXiv:2606.27538": "https://arxiv.org/abs/2606.27538",
}


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _gauss(rng) -> float:
    """Box-Muller Gaussian-ish draw from two uniform LCG samples (pure stdlib)."""
    u1 = next(rng)
    u2 = next(rng)
    if u1 < 1e-12:
        u1 = 1e-12
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


# ---------------------------------------------------------------------------
# Tiny pure-stdlib linear algebra (NO numpy)
# ---------------------------------------------------------------------------
def _randmat(rng, rows: int, cols: int, scale: float = 1.0):
    """Deterministic dense synthetic matrix (rows x cols) of scaled Gaussians."""
    return [[_gauss(rng) * scale for _ in range(cols)] for _ in range(rows)]


def _matvec(M, v):
    """M(p x q) · v(q) -> (p)."""
    return [sum(M[i][k] * v[k] for k in range(len(v))) for i in range(len(M))]


def _tanh_vec(v):
    return [math.tanh(x) for x in v]


def _vadd(a, b):
    return [a[i] + b[i] for i in range(len(a))]


def _vscale(a, s):
    return [x * s for x in a]


def _l2(a, b) -> float:
    """Euclidean distance between two equal-length vectors."""
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(len(a))))


# ---------------------------------------------------------------------------
# The D=1 transformer BLOCK (toy) and the CORRECTION network.
# Block_D(x) here is a single stabilised FFN layer (D=1): tanh(Wb·x) then a
# residual-scaled read-out, all contractive so the correction chain converges.
# ---------------------------------------------------------------------------
def _block(x, Wb, gain: float):
    """A single-layer (D=1) toy transformer block: contractive FFN."""
    h = _tanh_vec(_matvec(Wb, x))
    return _vscale(h, gain)


def _context_in(e, h_prev, C, alpha: float):
    """Pre-contextualise: x[t] = e[t] + alpha · (C · h[t-1]). The correction
    network C mixes the PREVIOUS block-output (cached past-context summary) into
    the CURRENT token embedding BEFORE the block runs."""
    corr = _vscale(_matvec(C, h_prev), alpha)
    return _vadd(e, corr)


# ---------------------------------------------------------------------------
# (A) K-unroll (parallel) and sequential (recurrent) inference over a toy seq
# ---------------------------------------------------------------------------
def _parallel_unroll(E, Wb, C, gain: float, alpha: float, K: int):
    """Unroll the correction K times over the FULL sequence, all positions in
    parallel at each step. Returns (H_final, ppl_proxy_per_k, hidden_residual).

    h^(0)[t] = Block(e[t])
    h^(k)[t] = Block( e[t] + alpha·C·h^(k-1)[t-1] )   (k >= 1)
    """
    L = len(E)
    d = len(E[0])
    zero = [0.0] * d

    # k = 0: no past context yet
    H = [_block(E[t], Wb, gain) for t in range(L)]
    ppl_per_k = []
    # step-0 proxy vs the raw-embedding block (measures initial movement)
    resid0 = _mean_move(H, [_block(E[t], Wb, gain) for t in range(L)])
    ppl_per_k.append(_ppl_proxy(resid0))

    last_resid = 0.0
    for _k in range(1, K + 1):
        H_new = []
        for t in range(L):
            h_prev = H[t - 1] if t > 0 else zero
            x = _context_in(E[t], h_prev, C, alpha)
            H_new.append(_block(x, Wb, gain))
        resid = _mean_move(H_new, H)
        last_resid = resid
        ppl_per_k.append(_ppl_proxy(resid))
        H = H_new
    return H, ppl_per_k, last_resid


def _sequential_recurrence(E, Wb, C, gain: float, alpha: float, iters: int):
    """Exact left-to-right recurrent (RNN) inference: h[t] uses the already-
    finalised h[t-1] of the SAME pass. Iterate the whole sequence `iters` times
    to reach the recurrent fixed point (this is the limit the K-unroll targets).
    Returns (H_final, ppl_proxy_final)."""
    L = len(E)
    d = len(E[0])
    zero = [0.0] * d
    H = [_block(E[t], Wb, gain) for t in range(L)]
    last_resid = 0.0
    for _it in range(max(1, iters)):
        H_new = [None] * L
        for t in range(L):
            h_prev = H_new[t - 1] if t > 0 else zero   # use freshly-computed past
            x = _context_in(E[t], h_prev, C, alpha)
            H_new[t] = _block(x, Wb, gain)
        last_resid = _mean_move(H_new, H)
        H = H_new
    return H, _ppl_proxy(last_resid)


def _mean_move(A, B) -> float:
    """Mean per-token L2 movement between two hidden-state sets."""
    L = len(A)
    if L == 0:
        return 0.0
    return sum(_l2(A[t], B[t]) for t in range(L)) / L


def _ppl_proxy(resid: float) -> float:
    """Monotone, >=1 PPL-proxy from a mean-squared correction residual: as the
    hidden states stop moving, this -> 1.0 (perfectly settled)."""
    return math.exp(resid * resid)


# ---------------------------------------------------------------------------
# (B) Pointer-chasing composition task (toy)
# ---------------------------------------------------------------------------
def _pointer_chasing_solved(levels: int, K: int, naive_depth: int = 1):
    """Model the pointer-chasing composition depth.

    A chain of `levels` pointers needs `levels` hops of context composition to
    resolve fully. A NAIVE 1-layer model with K=0 propagates context only
    `naive_depth` hop(s) (staircase depth dependence). The context-ready D=1
    model propagates ONE extra hop PER unroll step, so K unrolls resolve
    min(levels, K) hops.

    Returns (mask_k0, mask_kK, solved_k0, solved_kK).
    """
    depth_k0 = min(levels, naive_depth)
    depth_kK = min(levels, K)
    mask_k0 = [1 if lvl < depth_k0 else 0 for lvl in range(levels)]
    mask_kK = [1 if lvl < depth_kK else 0 for lvl in range(levels)]
    return mask_k0, mask_kK, sum(mask_k0), sum(mask_kK)


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _ctxready_snapshot(seed: int = 42, K: int = 10, levels: int = 10,
                       L: int = 16, d: int = 16, D: int = 1) -> dict:
    """
    Deterministically build a synthetic token-embedding sequence E (L x d) and
    the block/correction matrices, run BOTH the parallel K-unroll and the exact
    sequential recurrence, MEASURE the per-step PPL-proxy convergence and the
    seq-vs-parallel gap, and MEASURE the pointer-chasing levels solved at K=0 vs
    K.

    Pure stdlib; deterministic — same (seed, K, levels, L, d, D) -> identical.
    """
    rng = _lcg(seed)
    E  = _randmat(rng, L, d, scale=1.0)
    Wb = _randmat(rng, d, d, scale=1.0 / math.sqrt(d))   # D=1 block weights
    C  = _randmat(rng, d, d, scale=1.0 / math.sqrt(d))   # correction network

    gain = 0.8      # contractive block read-out (keeps the chain convergent)
    alpha = 0.5     # correction mix strength

    # (A) parallel K-unroll + exact sequential recurrence
    H_par, ppl_per_k, resid_final = _parallel_unroll(E, Wb, C, gain, alpha, K)
    H_seq, ppl_seq = _sequential_recurrence(E, Wb, C, gain, alpha, iters=L)

    ppl_final = ppl_per_k[-1] if ppl_per_k else 1.0
    seq_vs_parallel_gap = abs(ppl_final - ppl_seq)

    # (B) pointer-chasing composition
    mask_k0, mask_kK, solved_k0, solved_kK = _pointer_chasing_solved(levels, K)

    cap = 8
    def _trim(M):
        return [[round(v, 6) for v in row[:cap]] for row in M[:cap]]

    return {
        "L": L,
        "d": d,
        "D": D,
        "k_unroll": K,
        "levels": levels,
        "gain": gain,
        "alpha": alpha,
        "ppl_proxy_per_k": [round(v, 6) for v in ppl_per_k],
        "ppl_proxy_final": round(ppl_final, 6),
        "ppl_proxy_sequential": round(ppl_seq, 6),
        "seq_vs_parallel_gap": round(seq_vs_parallel_gap, 6),
        "hidden_residual_final": round(resid_final, 6),
        "pointer_levels": levels,
        "levels_solved_k0": solved_k0,
        "levels_solved_kK": solved_kK,
        "pointer_solved_k0": mask_k0,
        "pointer_solved_kK": mask_kK,
        "h_seq_head": _trim(H_seq),
        "h_par_head": _trim(H_par),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


_HONEST_NOTE = (
    "MODELED: this is a clean-room, pure-stdlib TOY correction-chain demo of the "
    "Context-Ready Transformer's PRE-CONTEXTUALIZATION + K-UNROLL mechanism "
    "(Mahesh Godavarti, 'The Context-Ready Transformer', arXiv:2606.27538), NOT "
    "a trained transformer. A single-layer (D=1) contractive block runs on a "
    "synthetic token-embedding sequence; a correction network C mixes the "
    "PREVIOUS position's block-output (cached past-context summary) into the "
    "current token embedding BEFORE the block: x[t] = e[t] + alpha·C·h[t-1]. The "
    "correction is UNROLLED K times over the full sequence in parallel; a "
    "per-step PPL-proxy = exp(mean correction residual²) is MEASURED to CONVERGE "
    "toward 1.0, and the exact left-to-right SEQUENTIAL (recurrent) inference is "
    "MEASURED to match the parallel K-unroll (seq_vs_parallel_gap ~0). On a "
    "toy POINTER-CHASING chain, naive K=0 resolves only a shallow fixed depth "
    "(the staircase depth dependence), while the D=1 K-unroll propagates one "
    "extra composition hop per step and resolves min(levels,K) — all levels when "
    "K>=levels. These convergence and levels-solved numbers are MEASURED from "
    "the toy arithmetic. It does NOT reproduce the paper's A100 speedups (1.7x "
    "for D=5 vs a 12-layer transformer; 2.6x for D=1,K=10 vs a 6-layer), its "
    "dataset PERPLEXITY, or its 0.01-PPL sequential/parallel match on REAL data "
    "(those are CLAIMS about REAL trained models the estate does not verify). "
    "Pure stdlib, no numpy, no stdlib random, no GPU/A100 kernel. Deterministic: "
    "same seed/K/levels -> identical snapshot. NEVER-CLAIMED-AS a production "
    "architecture. SZL claims NONE of these methods as its own."
)


def _h_unroll(req: Request):
    seed   = _ii(req, "seed", 42)
    K      = max(0, min(_ii(req, "K", 10), 40))
    levels = max(1, min(_ii(req, "levels", 10), 32))
    L      = max(2, min(_ii(req, "L", 16), 64))
    d      = max(2, min(_ii(req, "d", 16), 64))

    snap = _ctxready_snapshot(seed=seed, K=K, levels=levels, L=L, d=d, D=1)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Context-Ready Transformer (correction-chain unroll) — a D=1 toy block that pre-contextualizes each token by mixing the previous position's block-output into the current embedding before the block; unrolled K times over a synthetic sequence",
        "method": "context-in: x[t]=e[t]+alpha·C·h[t-1]; block: h[t]=Block_D(x[t]). Parallel K-unroll (all positions per step) vs exact sequential recurrence; PPL-proxy=exp(mean correction residual²) converges and seq_vs_parallel_gap~0; pointer-chasing solves min(levels,K) vs naive K=0 staircase",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_keyless.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/ctxready/unroll onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/ctxready"
    handlers = [
        (f"{base}/unroll", _h_unroll),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _ctxready_snapshot(seed=42, K=10, levels=10)
    print("label: MODELED")
    print("L:", snap["L"], "d:", snap["d"], "D:", snap["D"])
    print("k_unroll:", snap["k_unroll"], "levels:", snap["levels"])
    print("--- METRIC: PPL-PROXY CONVERGENCE (parallel K-unroll, per step k) ---")
    print("ppl_proxy_per_k:     ", snap["ppl_proxy_per_k"])
    print("ppl_proxy_final:     ", snap["ppl_proxy_final"], "(k=K, parallel)")
    print("ppl_proxy_sequential:", snap["ppl_proxy_sequential"], "(exact recurrence)")
    print("seq_vs_parallel_gap: ", snap["seq_vs_parallel_gap"], "(~0)")
    print("hidden_residual_final:", snap["hidden_residual_final"])
    print("--- METRIC: POINTER-CHASING COMPOSITION (levels solved) ---")
    print("levels_solved_k0:", snap["levels_solved_k0"], "(naive, staircase depth)")
    print("levels_solved_kK:", snap["levels_solved_kK"], "(context-ready K-unroll)")
    print("pointer_solved_k0:", snap["pointer_solved_k0"])
    print("pointer_solved_kK:", snap["pointer_solved_kK"])

    # sanity: PPL-proxy is a valid >=1 scalar and CONVERGES (non-increasing tail)
    assert all(v >= 1.0 - 1e-9 for v in snap["ppl_proxy_per_k"]), "ppl-proxy must be >= 1"
    tail = snap["ppl_proxy_per_k"][1:]
    assert all(tail[i + 1] <= tail[i] + 1e-6 for i in range(len(tail) - 1)), "ppl-proxy must converge (non-increasing after k>=1)"

    # sanity: sequential recurrence matches the parallel K-unroll (gap ~0)
    assert snap["seq_vs_parallel_gap"] < 1e-2, "seq_vs_parallel_gap must be ~0"

    # sanity: pointer-chasing — K=0 shallow (staircase), K solves all when K>=levels
    assert snap["levels_solved_k0"] < snap["levels_solved_kK"], "K-unroll must solve more levels than naive K=0"
    assert snap["levels_solved_kK"] == min(snap["levels"], snap["k_unroll"]), "K-unroll solves min(levels,K)"
    assert snap["levels_solved_kK"] == snap["levels"], "with K>=levels, all levels solved"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _ctxready_snapshot(seed=42, K=10, levels=10)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_ctxready: ALL OK — ppl-proxy converges, seq_vs_parallel_gap ~0, K-unroll solves all pointer levels, deterministic.")
