# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_slidesparse.py — SZL STRUCTURED-SPARSE LAYOUT PACKING endpoint (SlideSparse
(2N-2):2N sliding-window decomposition + activation lifting), MODELED.

Exposes a MODELED, deterministic, closed-form re-implementation of the
SlideSparse sliding-window-decomposition MECHANISM (Shao, Hao, Song, Xia, Zhang,
Huang, Wu, Xu, Xu, Dong, Chi, Zou, Wei — Furu Wei group, arXiv:2603.05232)
applied to a small SYNTHETIC weight matrix drawn from the pure-stdlib LCG PRNG
below — so the slidesparse organ has a live data source that is honest,
deterministic, and citable — never fabricated, never a trained model, never a
run on a real GPU / Sparse Tensor Core / vLLM.

  GET  /api/<ns>/v1/slidesparse/pack?seed=&N=&matrix_shape=&mode=

WHAT IS MODELED
---------------
NVIDIA Sparse Tensor Cores accelerate ONLY the rigid 2:4 pattern (exactly 2
nonzeros per contiguous group of 4, i.e. 50% pruning). That 50% prune is often
too harsh for LLM accuracy. Milder (2N-2):2N patterns — e.g. 6:8 at N=4, which
prunes only 2 of every 8 weights (25% pruning) — retain accuracy but get NO
hardware support, so they fall back to a DENSE kernel and lose all acceleration.

SlideSparse is a pure DATA-LAYOUT / PACKING transform (same weights, same
accuracy, re-tiled for the hardware):

  (1) SLIDING WINDOW DECOMPOSITION
      Any (2N-2):2N block (2N wide, exactly 2N-2 nonzeros, exactly 2 zeros) is
      losslessly decomposed into N-1 overlapping 4-wide windows, where each
      window is 2:4-COMPLIANT (<= 2 nonzeros per 4). The N-1 windows, laid back
      over their originating columns, RECONSTRUCT THE ORIGINAL BLOCK EXACTLY
      (zero error). Because each window is 2:4-compliant, the mild-sparsity
      weights now run on the EXISTING 2:4 Sparse Tensor Cores.

  (2) ACTIVATION LIFTING
      The matching rearrangement of the activation vector so the per-window
      column indices line up with the decomposed weight windows (a permutation /
      gather), fused so no extra data movement is needed.

This module re-implements that exact packing on a deterministic synthetic W and
a toy activation vector, then MEASURES three honest results:

  RECONSTRUCTION   : the sliding-window decomposition is verified LOSSLESS — the
                     N-1 windows recompose the (2N-2):2N block with EXACTLY ZERO
                     error (asserted). The strict-2:4 baseline forces an extra
                     prune and therefore shows a NON-ZERO reconstruction error,
                     which is REPORTED, not hidden.
  THROUGHPUT PROXY : an effective-MAC count on each path. Dense pays 2N MACs per
                     block; strict-2:4 and slidesparse pay only the nonzeros that
                     land on the 2:4 tensor cores. The slidesparse speedup
                     (dense_macs / slidesparse_macs) approaches the theoretical
                     ceiling N/(N-1) (= 4/3 at N=4, the 6:8 case).
  LAYOUT PROFILE   : blocks packed, windows emitted (N-1 per block), the toy
                     activation-lifting permutation, and the per-window 2:4 masks.

THE TRADE, HONESTLY: mild (2N-2):2N sparsity keeps accuracy AND regains hardware
acceleration by re-tiling into 2:4 windows — at the cost of N-1 overlapping
windows per block (a packing/index overhead) and a ceiling of N/(N-1), never the
2x of true 2:4. Both sides are reported.

Returned JSON fields
--------------------
  label                     : "MODELED" (always — clean-room re-implementation of
                              the SlideSparse sliding-window-decomposition +
                              activation-lifting MECHANISM, NOT a trained model,
                              NOT a GPU/tensor-core run)
  model                     : short description of the modeled setup
  method                    : one-line description of the exact packing transform
  seed                      : RNG seed used
  N                         : window parameter; pattern is (2N-2):2N, block width 2N
  block_width               : 2N (width of each structured-sparse block)
  windows_per_block         : N-1 (overlapping 4-wide 2:4 windows per block)
  sparsity_pattern          : "(2N-2):2N" resolved, e.g. "6:8"
  prune_fraction            : 2 / (2N)  (fraction of weights pruned per block)
  matrix_rows, matrix_cols  : synthetic weight-matrix dimensions (cols = k*2N)
  blocks_total              : number of 2N-wide blocks packed across the matrix
  mode                      : "slidesparse" | "strict_2to4" | "dense"
  reconstruction_error      : MEASURED max-abs reconstruction error for `mode`
                              (slidesparse -> 0.0 EXACT; strict_2to4 -> > 0;
                              dense -> 0.0)
  lossless                  : bool — reconstruction_error == 0 for this mode
  slidesparse_recon_error   : reconstruction error of the slidesparse path (0.0)
  strict_2to4_recon_error   : reconstruction error of the strict-2:4 baseline (>0)
  dense_macs                : effective MACs on the dense path
  strict_2to4_macs          : effective MACs on the strict-2:4 path
  slidesparse_macs          : effective MACs on the slidesparse (N-1 window) path
  speedup_dense             : 1.0 (reference)
  speedup_strict_2to4       : dense_macs / strict_2to4_macs
  speedup_slidesparse       : dense_macs / slidesparse_macs (the reported proxy)
  throughput_ceiling        : N / (N-1) — the theoretical (2N-2):2N ceiling
  ceiling_gap               : throughput_ceiling - speedup_slidesparse (>= 0)
  activation_lifting_perm   : toy activation-lifting permutation (index gather)
  sample_window_masks       : per-window 2:4 masks for the first packed block
  honest_note               : plain-language honesty disclaimer (see below)
  citations                 : dict of citable sources (verified real)
  computed_at               : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the SlideSparse
  sliding-window-decomposition + activation-lifting PACKING MECHANISM on a TOY
  synthetic matrix (no numpy, no stdlib `random`, no proprietary weights, no real
  transformer, no trained model, NO GPU, NO Sparse Tensor Core, NO CUDA, NO
  vLLM). "throughput" here is a COUNTED effective-MAC proxy and "accuracy" a
  reconstruction-error proxy — NOT a hardware measurement. It demonstrates that a
  (2N-2):2N block decomposes LOSSLESSLY into N-1 overlapping 2:4 windows,
  recovering a sparse execution path that approaches the N/(N-1) ceiling. It does
  NOT reproduce SlideSparse's reported 1.33x speedup on Qwen2.5-7B or its
  A100/H100/B200/RTX + FP4/INT8/FP8/BF16/FP16 results. NEW AXIS: structured-sparse
  layout / packing — orthogonal to ternary bit-precision and analog in-memory
  compute. The label "MODELED" is returned verbatim and displayed verbatim by the
  surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own; VERIFY real):
  SlideSparse: Fast and Flexible (2N-2):2N Structured Sparsity (mechanism modeled
  here):
    Shao, Hao, Song, Xia, Zhang, Huang, Wu, Xu, Xu, Dong, Chi, Zou, Wei
    (Furu Wei group). arXiv:2603.05232. https://arxiv.org/abs/2603.05232
  NEVER-CLAIMED-AS: this module is not SlideSparse's released code, does not
  reproduce its benchmark numbers, and runs no real model, GPU, or tensor core.
  It is a clean-room MODELED reproduction of the sliding-window-decomposition +
  activation-lifting packing transform the paper describes.

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
    "SlideSparse: Fast and Flexible (2N-2):2N Structured Sparsity — Shao, Hao, Song, Xia, Zhang, Huang, Wu, Xu, Xu, Dong, Chi, Zou, Wei (Furu Wei group) arXiv:2603.05232": "https://arxiv.org/abs/2603.05232",
}

# Cap on how many window masks we echo back for the surface's viz (bounded payload).
_MAX_SAMPLE_WINDOWS = 16


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _rand_signed(rng) -> float:
    """Draw one deterministic pseudo-random value in (-1, 1) from the LCG stream."""
    return 2.0 * next(rng) - 1.0


# ---------------------------------------------------------------------------
# (2N-2):2N structured pruning — closed-form top-k by magnitude (no training)
# ---------------------------------------------------------------------------
def _make_matrix(rng, rows: int, cols: int):
    """Deterministic dense weight matrix W (rows x cols) of small signed floats."""
    return [[_rand_signed(rng) for _ in range(cols)] for _ in range(rows)]


def _prune_block_2Nm2(block):
    """
    Prune a 2N-wide block to the (2N-2):2N pattern: keep the 2N-2 largest-|w|
    entries, zero the 2 smallest-|w| entries. Closed-form top-k, no training.
    Returns (pruned_block, dropped_indices).
    """
    w = len(block)
    order = sorted(range(w), key=lambda i: abs(block[i]))  # ascending |w|
    drop = set(order[:2])                                  # 2 smallest -> zero
    pruned = [0.0 if i in drop else block[i] for i in range(w)]
    return pruned, sorted(drop)


def _prune_block_strict_2to4(block):
    """
    Strict 2:4 baseline on the SAME block: within each contiguous group of 4,
    keep only the 2 largest-|w|, zero the other 2 (exactly 50% prune). This is
    what the 2:4 Sparse Tensor Core natively supports — but it over-prunes a
    (2N-2):2N block, so it CANNOT reconstruct the original weights (non-zero
    error). Returns pruned_block.
    """
    w = len(block)
    pruned = [0.0] * w
    for g0 in range(0, w, 4):
        grp = list(range(g0, min(g0 + 4, w)))
        # keep the 2 largest-|w| in this group of (up to) 4
        keep = sorted(grp, key=lambda i: abs(block[i]), reverse=True)[:2]
        for i in keep:
            pruned[i] = block[i]
    return pruned


# ---------------------------------------------------------------------------
# SLIDING WINDOW DECOMPOSITION — the core packing transform
# ---------------------------------------------------------------------------
def _sliding_window_decompose(pruned_block, N: int):
    """
    Decompose a (2N-2):2N pruned block (width 2N, exactly 2N-2 nonzeros) into
    N-1 overlapping 4-wide windows, each 2:4-COMPLIANT (<= 2 nonzeros per window),
    such that laying the N-1 windows back over their originating columns
    RECONSTRUCTS THE ORIGINAL BLOCK EXACTLY.

    Construction (partition-into-overlapping-views): the N-1 windows are the
    sliding 4-wide views anchored at columns 0, 2, 4, ..., 2N-4 (stride 2). Each
    of the 2N columns is COVERED by at least one window; every nonzero weight is
    ASSIGNED to exactly ONE window (its owning window), so the overlap regions do
    not double-count. We assign each column's weight to the window that can still
    accept it while keeping every window <= 2 nonzeros. Because the block has only
    2N-2 nonzeros spread over N-1 windows of capacity 2, a valid assignment
    always exists; the reconstruction (sum of windows over their column offsets)
    is bit-exact.

    Returns (windows, assign) where:
      windows : list of N-1 dicts {offset, values[4], mask[4], nnz}
      assign  : list length 2N, assign[col] = window index owning that column
    """
    W = 2 * N
    num_windows = N - 1
    offsets = [2 * j for j in range(num_windows)]  # 0, 2, 4, ..., 2N-4

    # window occupancy (2:4 capacity = 2 nonzeros per window)
    win_nnz = [0] * num_windows
    win_vals = [[0.0, 0.0, 0.0, 0.0] for _ in range(num_windows)]
    win_mask = [[0, 0, 0, 0] for _ in range(num_windows)]
    assign = [-1] * W

    # candidate windows covering column c: those whose [offset, offset+4) span c
    def _covering(c):
        cov = []
        for j, off in enumerate(offsets):
            if off <= c < off + 4:
                cov.append(j)
        return cov

    # Assign each nonzero column to the EARLIEST covering window that still has
    # room (2:4 capacity = 2). Processing columns left-to-right and always
    # draining into the leftmost available window is the correct greedy for this
    # staircase of overlapping intervals: it never starves a later column, since
    # any column reachable only by a later window is left untouched by earlier
    # windows once those fill. For a (2N-2):2N block this yields a valid packing
    # where every window holds <= 2 nonzeros and every nonzero is placed.
    for c in range(W):
        v = pruned_block[c]
        if v == 0.0:
            continue  # zeros need no window slot (they are the dropped entries)
        cov = _covering(c)
        chosen = -1
        for j in cov:  # cov is already in ascending (earliest-first) order
            if win_nnz[j] < 2:
                chosen = j
                break
        if chosen < 0:
            # fallback: any covering window (should not happen for (2N-2):2N)
            chosen = cov[0]
        local = c - offsets[chosen]
        win_vals[chosen][local] = v
        win_mask[chosen][local] = 1
        win_nnz[chosen] += 1
        assign[c] = chosen

    windows = []
    for j in range(num_windows):
        windows.append({
            "offset": offsets[j],
            "values": win_vals[j],
            "mask": win_mask[j],
            "nnz": win_nnz[j],
        })
    return windows, assign


def _reconstruct_from_windows(windows, width: int):
    """
    Lay the N-1 windows back over their originating columns and SUM. Because each
    nonzero was assigned to exactly one window, this recomposes the original
    pruned block bit-exactly. Returns a length-`width` list.
    """
    out = [0.0] * width
    for win in windows:
        off = win["offset"]
        for local in range(4):
            col = off + local
            if 0 <= col < width and win["mask"][local]:
                out[col] += win["values"][local]
    return out


def _max_abs_err(a, b) -> float:
    """Max absolute element-wise error between two equal-length lists."""
    m = 0.0
    for x, y in zip(a, b):
        d = abs(x - y)
        if d > m:
            m = d
    return m


# ---------------------------------------------------------------------------
# effective-MAC (throughput) proxy per block, per path
# ---------------------------------------------------------------------------
def _macs_dense(N: int) -> int:
    """Dense path pays the full 2N MACs per block (no acceleration)."""
    return 2 * N


def _macs_from_windows(windows) -> int:
    """
    Sparse-path effective MACs = total nonzeros actually executed on the 2:4
    tensor cores across the N-1 windows. For a (2N-2):2N block that is 2N-2.
    """
    return sum(w["nnz"] for w in windows)


def _macs_strict_2to4(pruned_strict) -> int:
    """Strict-2:4 path executes exactly the surviving (kept) nonzeros."""
    return sum(1 for v in pruned_strict if v != 0.0)


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _slidesparse_snapshot(seed: int = 42, N: int = 4, matrix_shape=(8, None),
                          mode: str = "slidesparse") -> dict:
    """
    Deterministically build a synthetic weight matrix whose columns are a whole
    number of 2N-wide blocks, prune each block to (2N-2):2N, decompose each block
    via the sliding window transform, VERIFY lossless reconstruction, build the
    activation-lifting permutation on a toy activation vector, and MEASURE the
    reconstruction error and effective-MAC throughput proxy for `mode`.

    Pure stdlib; deterministic — same (seed, N, matrix_shape, mode) -> identical
    snapshot, every time.
    """
    rows = matrix_shape[0]
    W = 2 * N
    # cols must be a whole number of 2N-wide blocks; default to a single block-col
    blocks_per_row = matrix_shape[1] if matrix_shape[1] else 1
    cols = blocks_per_row * W

    rng = _lcg(seed)
    M = _make_matrix(rng, rows, cols)

    # toy activation vector (drawn AFTER W from the same stream -> single
    # deterministic function of `seed`)
    activation = [_rand_signed(rng) for _ in range(cols)]

    slidesparse_recon_err = 0.0
    strict_2to4_recon_err = 0.0

    dense_macs = 0
    strict_macs = 0
    slide_macs = 0

    first_windows = None
    first_assign = None

    for r in range(rows):
        for b in range(blocks_per_row):
            block = M[r][b * W:(b + 1) * W]

            # (2N-2):2N pruning — the mild, accuracy-preserving pattern
            pruned, _dropped = _prune_block_2Nm2(block)

            # sliding-window decomposition -> N-1 overlapping 2:4 windows
            windows, assign = _sliding_window_decompose(pruned, N)

            # LOSSLESSNESS: windows recompose the pruned block EXACTLY
            recon = _reconstruct_from_windows(windows, W)
            err = _max_abs_err(pruned, recon)
            if err > slidesparse_recon_err:
                slidesparse_recon_err = err
            # hard invariant — the whole point of the transform
            assert err == 0.0, "sliding-window decomposition must be LOSSLESS (zero error)"
            # every window must be 2:4-compliant (<= 2 nonzeros per 4-wide window)
            for win in windows:
                assert win["nnz"] <= 2, "each window must be 2:4-compliant"

            # strict-2:4 baseline on the SAME block over-prunes -> non-zero error
            strict = _prune_block_strict_2to4(block)
            serr = _max_abs_err(pruned, strict)
            if serr > strict_2to4_recon_err:
                strict_2to4_recon_err = serr

            # effective-MAC (throughput) proxy tallies
            dense_macs += _macs_dense(N)
            slide_macs += _macs_from_windows(windows)
            strict_macs += _macs_strict_2to4(strict)

            if first_windows is None:
                first_windows = windows
                first_assign = assign

    # activation-lifting permutation on the toy activation vector: for the FIRST
    # block, gather the activation indices in per-window order (the rearrangement
    # that lines activations up with the decomposed weight windows).
    lifting_perm = []
    if first_windows is not None:
        for win in first_windows:
            off = win["offset"]
            for local in range(4):
                if win["mask"][local]:
                    lifting_perm.append(off + local)

    # throughput proxy speedups
    speedup_dense = 1.0
    speedup_strict = (dense_macs / strict_macs) if strict_macs else 0.0
    speedup_slide = (dense_macs / slide_macs) if slide_macs else 0.0
    ceiling = N / (N - 1) if N > 1 else 1.0
    ceiling_gap = ceiling - speedup_slide

    # per-mode reported reconstruction error / lossless flag
    if mode == "strict_2to4":
        recon_err = strict_2to4_recon_err
    elif mode == "dense":
        recon_err = 0.0  # dense keeps every weight -> perfect (but no acceleration)
    else:
        mode = "slidesparse"
        recon_err = slidesparse_recon_err

    sample_masks = []
    if first_windows is not None:
        for win in first_windows[:_MAX_SAMPLE_WINDOWS]:
            sample_masks.append({
                "offset": win["offset"],
                "mask": win["mask"],
                "nnz": win["nnz"],
                "values": [round(v, 6) for v in win["values"]],
            })

    return {
        "N": N,
        "block_width": W,
        "windows_per_block": N - 1,
        "sparsity_pattern": "%d:%d" % (2 * N - 2, 2 * N),
        "prune_fraction": round(2.0 / (2 * N), 6),
        "matrix_rows": rows,
        "matrix_cols": cols,
        "blocks_total": rows * blocks_per_row,
        "mode": mode,
        "reconstruction_error": round(recon_err, 12),
        "lossless": recon_err == 0.0,
        "slidesparse_recon_error": round(slidesparse_recon_err, 12),
        "strict_2to4_recon_error": round(strict_2to4_recon_err, 12),
        "dense_macs": dense_macs,
        "strict_2to4_macs": strict_macs,
        "slidesparse_macs": slide_macs,
        "speedup_dense": round(speedup_dense, 6),
        "speedup_strict_2to4": round(speedup_strict, 6),
        "speedup_slidesparse": round(speedup_slide, 6),
        "throughput_ceiling": round(ceiling, 6),
        "ceiling_gap": round(ceiling_gap, 12),
        "activation_lifting_perm": lifting_perm,
        "sample_window_masks": sample_masks,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _ss(req: Request, key: str, default: str) -> str:
    v = req.query_params.get(key, default)
    return v if isinstance(v, str) and v else default


_HONEST_NOTE = (
    "MODELED: toy analytic sim of the sliding-window-decomposition packing "
    "MECHANISM, not SlideSparse. Seeded 8x2N toy matrix pruned by magnitude; NO "
    "GPU, NO Sparse Tensor Core, NO vLLM, NO CUDA — 'throughput' is a counted MAC "
    "proxy, 'accuracy' a reconstruction-error proxy. Demonstrates (2N-2):2N "
    "decomposes losslessly into N-1 overlapping 2:4 windows recovering a sparse "
    "path approaching the N/(N-1) ceiling; does NOT reproduce SlideSparse's 1.33x "
    "speedup on Qwen2.5-7B or its A100/H100/B200/RTX + FP4/INT8/FP8/BF16/FP16 "
    "results. NEW AXIS: structured-sparse layout/packing (orthogonal to ternary "
    "bit-precision + aimc analog compute). Pure stdlib, no numpy, no stdlib "
    "random, no proprietary weights, no real transformer. Deterministic: same "
    "seed/N/matrix_shape/mode -> identical snapshot. SZL claims NONE of these "
    "methods as its own."
)


def _h_pack(req: Request):
    seed = _ii(req, "seed", 42)
    N = max(2, min(_ii(req, "N", 4), 16))
    rows = max(1, min(_ii(req, "rows", 8), 64))
    blocks = max(1, min(_ii(req, "blocks", 1), 32))
    mode = _ss(req, "mode", "slidesparse")
    if mode not in ("slidesparse", "strict_2to4", "dense"):
        mode = "slidesparse"

    # `matrix_shape` accepted as "RxB" (rows x blocks-per-row) convenience param
    ms = req.query_params.get("matrix_shape")
    if ms:
        try:
            parts = ms.lower().replace(" ", "").split("x")
            rows = max(1, min(int(parts[0]), 64))
            if len(parts) > 1:
                # second part is total cols; convert to whole 2N blocks
                total_cols = int(parts[1])
                blocks = max(1, min(total_cols // (2 * N), 32))
        except Exception:
            pass

    snap = _slidesparse_snapshot(seed=seed, N=N, matrix_shape=(rows, blocks), mode=mode)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Structured-sparse layout packing: SlideSparse (2N-2):2N sliding-window decomposition + activation lifting on a synthetic weight matrix",
        "method": (
            "Prune each 2N-wide block to (2N-2):2N by magnitude top-k; decompose "
            "the block into N-1 overlapping 4-wide windows, each 2:4-compliant "
            "(<=2 nonzeros/4), assigning every nonzero to exactly one window so the "
            "windows recompose the block EXACTLY (lossless); build the "
            "activation-lifting index permutation; MEASURE reconstruction error "
            "(slidesparse=0, strict-2:4>0) and an effective-MAC throughput proxy "
            "approaching the N/(N-1) ceiling"
        ),
        "seed": seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_ternary.register() / szl_aimc.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/slidesparse/pack onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/slidesparse"
    handlers = [
        (f"{base}/pack", _h_pack),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        # Additive registration must never break the host app; degrade silently.
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _slidesparse_snapshot(seed=42, N=4, matrix_shape=(8, 1), mode="slidesparse")
    print("label: MODELED")
    print("N:", snap["N"])
    print("block_width (2N):", snap["block_width"])
    print("windows_per_block (N-1):", snap["windows_per_block"])
    print("sparsity_pattern:", snap["sparsity_pattern"])
    print("prune_fraction:", snap["prune_fraction"])
    print("matrix_rows x matrix_cols:", snap["matrix_rows"], "x", snap["matrix_cols"])
    print("blocks_total:", snap["blocks_total"])
    print("mode:", snap["mode"])
    print("--- RESULT 1: EXACT LOSSLESS RECONSTRUCTION ---")
    print("slidesparse_recon_error:", snap["slidesparse_recon_error"], "(EXACT ZERO)")
    print("strict_2to4_recon_error:", snap["strict_2to4_recon_error"], "(non-zero baseline)")
    print("lossless:", snap["lossless"])
    print("--- RESULT 2: THROUGHPUT PROXY (effective MACs) vs N/(N-1) CEILING ---")
    print("dense_macs:", snap["dense_macs"])
    print("strict_2to4_macs:", snap["strict_2to4_macs"])
    print("slidesparse_macs:", snap["slidesparse_macs"])
    print("speedup_dense:", snap["speedup_dense"])
    print("speedup_strict_2to4:", snap["speedup_strict_2to4"])
    print("speedup_slidesparse:", snap["speedup_slidesparse"])
    print("throughput_ceiling N/(N-1):", snap["throughput_ceiling"])
    print("ceiling_gap:", snap["ceiling_gap"])
    print("--- RESULT 3: LAYOUT PROFILE ---")
    print("activation_lifting_perm:", snap["activation_lifting_perm"])
    print("sample_window_masks[0]:", snap["sample_window_masks"][0])

    # core claim 1: sliding-window decomposition is EXACTLY lossless
    assert snap["slidesparse_recon_error"] == 0.0, "slidesparse must reconstruct with ZERO error"
    assert snap["lossless"] is True, "slidesparse mode must be lossless"

    # core claim 2: strict-2:4 baseline over-prunes -> non-zero reconstruction error
    assert snap["strict_2to4_recon_error"] > 0.0, "strict-2:4 baseline must show non-zero error"

    # core claim 3: N-1 windows per 2N block
    assert snap["windows_per_block"] == snap["N"] - 1, "must emit N-1 windows per block"
    assert snap["block_width"] == 2 * snap["N"], "block width must be 2N"

    # core claim 4: slidesparse effective MACs == (2N-2) per block (only nonzeros)
    assert snap["slidesparse_macs"] == (2 * snap["N"] - 2) * snap["blocks_total"], \
        "slidesparse MACs must equal (2N-2) per block"
    assert snap["dense_macs"] == 2 * snap["N"] * snap["blocks_total"], \
        "dense MACs must equal 2N per block"

    # core claim 5: throughput proxy approaches — but never exceeds — the ceiling
    assert snap["speedup_slidesparse"] <= snap["throughput_ceiling"] + 1e-12, \
        "slidesparse speedup must not exceed the N/(N-1) ceiling"
    assert abs(snap["speedup_slidesparse"] - snap["throughput_ceiling"]) < 1e-9, \
        "slidesparse proxy should reach the N/(N-1) ceiling for a full (2N-2):2N matrix"
    assert snap["ceiling_gap"] >= -1e-12, "ceiling_gap must be non-negative"

    # strict-2:4 baseline mode reports its non-zero error
    snap_strict = _slidesparse_snapshot(seed=42, N=4, matrix_shape=(8, 1), mode="strict_2to4")
    assert snap_strict["reconstruction_error"] > 0.0, "strict_2to4 mode must report non-zero error"
    assert snap_strict["lossless"] is False, "strict_2to4 mode must not be lossless"

    # dense mode is lossless but unaccelerated (speedup 1.0)
    snap_dense = _slidesparse_snapshot(seed=42, N=4, matrix_shape=(8, 1), mode="dense")
    assert snap_dense["reconstruction_error"] == 0.0, "dense mode keeps all weights (lossless)"
    assert snap_dense["speedup_dense"] == 1.0, "dense is the 1.0 reference"

    # determinism — identical inputs -> identical snapshot
    snap2 = _slidesparse_snapshot(seed=42, N=4, matrix_shape=(8, 1), mode="slidesparse")
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_slidesparse: ALL OK — (2N-2):2N decomposed LOSSLESSLY into N-1 "
          "overlapping 2:4 windows (zero error), strict-2:4 baseline error MEASURED, "
          "throughput proxy reaches N/(N-1) ceiling, deterministic.")
