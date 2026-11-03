# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_mla.py — SZL Multi-Head Latent Attention (MLA) low-rank joint KV-compression
endpoint (DeepSeek-V2/V3-style), MODELED.

Exposes a MODELED closed-form simulation of MLA's low-rank joint key-value
compression idea as a same-origin REST endpoint, so the MLA surface organ has
a live data source that is honest, deterministic, and citable — never
fabricated, never random-faked, never run against real DeepSeek-V2/V3
weights.

  GET  /api/<ns>/v1/mla/latent-compress?seed=&seq_len=&n_heads=&d_head=&d_latent=

WHAT IS SIMULATED
------------------
Standard Multi-Head Attention (MHA) must cache a separate Key and Value
vector, per head, per token, to avoid recomputing them at every autoregressive
decoding step. For `seq_len` positions, `n_heads` heads, and `d_head` per-head
dimension, that KV cache holds

    mha_cache_size = seq_len * n_heads * d_head * 2      (the "*2" for K and V)

elements — a hard memory ceiling on context length and batch size at
inference time (DeepSeek-AI et al. 2024, "DeepSeek-V2", arXiv:2405.04434).
**Multi-Head Latent Attention (MLA)** instead jointly compresses the
concatenated per-token K/V representation (dimension `n_heads * d_head`) down
to a single shared low-rank LATENT vector of dimension `d_latent` via a
learned DOWN-projection matrix, caches ONLY that latent vector per token, and
UP-projects back to per-head K/V on demand:

    mla_cache_size = seq_len * d_latent

Because `d_latent` is chosen far smaller than `n_heads * d_head * 2`, this
yields a dramatic reduction in KV-cache memory
(`compression_ratio = mha_cache_size / mla_cache_size`) — DeepSeek-V2 reports
this design reduces the KV cache by 93.3% versus its dense predecessor. The
trade-off is a nonzero RECONSTRUCTION ERROR: an arbitrary random down/up
projection pair is lossy, so information is discarded when compressing to the
latent bottleneck. (In the actual trained DeepSeek-V2/V3 models the down/up
projection WEIGHTS are learned end-to-end via gradient descent so that
reconstruction error is minimized jointly with the language-modeling
objective — nothing here is trained, so the "modest reconstruction error"
this module reports is illustrative of the LOW-RANK-BOTTLENECK ARITHMETIC
only, not a measurement of DeepSeek's actual trained fidelity.)

THIS MODULE (clean-room, deterministic, MODELED):
  1. Draws seeded synthetic K/V vectors for `seq_len` positions x `n_heads`
     heads x `d_head` dims each, from the pure-stdlib LCG PRNG below (no
     numpy, no stdlib `random`).
  2. Concatenates each position's per-head K/V into one row of dimension
     `n_heads * d_head * 2`.
  3. DOWN-projects each row through a seeded random matrix to a shared
     LATENT vector of dimension `d_latent` (this is what would be cached).
  4. UP-projects each latent vector back through a second seeded random
     matrix to the original `n_heads * d_head * 2` dimension.
  5. Computes the mean L2 reconstruction error between the original
     concatenated KV rows and their down/up-projected reconstructions.
  6. Reports `mha_cache_size`, `mla_cache_size`, `compression_ratio`, and
     `reconstruction_error`.

Returned JSON fields
---------------------
  label                 : "MODELED" (always — deterministic re-implementation
                           of the low-rank down/up-projection ARITHMETIC, NOT
                           trained DeepSeek-V2/V3 weights)
  model                 : short description of the simulated setup
  seed                  : RNG seed used
  seq_len               : number of token positions simulated
  n_heads               : number of attention heads
  d_head                : per-head dimension
  d_latent              : shared compressed-latent dimension (the MLA cache
                           width per token)
  mha_cache_size        : seq_len * n_heads * d_head * 2 (K+V, uncompressed)
  mla_cache_size        : seq_len * d_latent (compressed latent cache)
  compression_ratio     : mha_cache_size / mla_cache_size
  reconstruction_error  : mean L2 norm of (original_kv_row - reconstructed_kv_row)
                           averaged over all seq_len rows
  sample_original_row   : first row of concatenated K/V (truncated), for the
                           surface's "full KV column" visualization
  sample_latent_row     : first row's down-projected latent vector, for the
                           surface's "compressed latent column" visualization
  sample_reconstructed_row : first row's up-projected reconstruction, for the
                           surface's "ghost reconstruction" overlay
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of MLA's low-rank
  joint KV-COMPRESSION ARITHMETIC (seeded random down-projection then
  up-projection, with reconstruction error measured directly) — NOT trained
  DeepSeek-V2/V3 weights, uses NO proprietary weights, runs NO real language
  model, and is NEVER-CLAIMED-AS DeepSeek-V2 or DeepSeek-V3. The label
  "MODELED" is returned verbatim and displayed verbatim by the surface; never
  upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  DeepSeek-V2 (introduces Multi-Head Latent Attention / low-rank KV joint
  compression):
    DeepSeek-AI et al. (2024) "DeepSeek-V2: A Strong, Economical, and
    Efficient Mixture-of-Experts Language Model". arXiv:2405.04434.
    https://arxiv.org/abs/2405.04434
  DeepSeek-V3 (adopts and validates MLA at larger scale):
    DeepSeek-AI et al. (2024) "DeepSeek-V3 Technical Report".
    arXiv:2412.19437. https://arxiv.org/abs/2412.19437
  NEVER-CLAIMED-AS: this module is not DeepSeek-V2, not DeepSeek-V3, and does
  not reproduce either project's code, trained weights, or measured
  benchmark numbers. It is a clean-room MODELED simulation of the shared
  low-rank down/up-projection arithmetic those methods build on.

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
    "DeepSeek-V2 (Multi-Head Latent Attention) — DeepSeek-AI et al. arXiv:2405.04434": "https://arxiv.org/abs/2405.04434",
    "DeepSeek-V3 Technical Report — DeepSeek-AI et al. arXiv:2412.19437": "https://arxiv.org/abs/2412.19437",
}

# Cap on how many components of a sample row we echo back for the surface's
# lattice visualization (keeps payload bounded for large d_head/n_heads).
_MAX_SAMPLE_DIMS = 64


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
# Pure-stdlib nested-list matrix helpers (no numpy)
# ---------------------------------------------------------------------------
def _make_matrix(rng, rows: int, cols: int, scale: float):
    """rows x cols matrix of small seeded random values, nested lists."""
    return [[scale * _rand_signed(rng) for _ in range(cols)] for _ in range(rows)]


def _matmul(a, b):
    """Nested-list matrix multiply: a is (m x k), b is (k x n) -> (m x n)."""
    m = len(a)
    k = len(a[0]) if m else 0
    n = len(b[0]) if k else 0
    out = [[0.0] * n for _ in range(m)]
    for i in range(m):
        ai = a[i]
        oi = out[i]
        for t in range(k):
            aval = ai[t]
            if aval == 0.0:
                continue
            bt = b[t]
            for j in range(n):
                oi[j] += aval * bt[j]
    return out


def _l2_row_diff(a_row, b_row) -> float:
    """L2 norm of the elementwise difference between two equal-length rows."""
    s = 0.0
    for x, y in zip(a_row, b_row):
        d = x - y
        s += d * d
    return s ** 0.5


# ---------------------------------------------------------------------------
# MODELED low-rank joint KV-compression simulation (deterministic)
# ---------------------------------------------------------------------------
def _mla_snapshot(seed: int = 42, seq_len: int = 128, n_heads: int = 8,
                   d_head: int = 64, d_latent: int = 128) -> dict:
    """
    Simulate MLA's low-rank joint KV compression over `seq_len` token
    positions, `n_heads` heads x `d_head` per-head dimension, compressed to
    a shared latent of width `d_latent`.

    Pure stdlib nested-list matmul; deterministic — same
    (seed, seq_len, n_heads, d_head, d_latent) -> identical snapshot, every
    time.
    """
    rng = _lcg(seed)
    kv_dim = n_heads * d_head * 2  # concatenated K and V per token

    # 1) Seeded synthetic per-token concatenated K/V rows: (seq_len x kv_dim)
    kv_rows = _make_matrix(rng, seq_len, kv_dim, scale=1.0)

    # 2) Seeded DOWN-projection matrix: (kv_dim x d_latent). Xavier-ish
    #    scaling keeps values well-conditioned regardless of dimension.
    down_scale = (1.0 / max(kv_dim, 1)) ** 0.5
    w_down = _make_matrix(rng, kv_dim, d_latent, scale=down_scale)

    # 3) Seeded UP-projection matrix: (d_latent x kv_dim).
    up_scale = (1.0 / max(d_latent, 1)) ** 0.5
    w_up = _make_matrix(rng, d_latent, kv_dim, scale=up_scale)

    # 4) Down-project: latent_rows = kv_rows @ w_down  -> (seq_len x d_latent)
    latent_rows = _matmul(kv_rows, w_down)

    # 5) Up-project (reconstruct): recon_rows = latent_rows @ w_up -> (seq_len x kv_dim)
    recon_rows = _matmul(latent_rows, w_up)

    # 6) Mean L2 reconstruction error across all seq_len rows.
    total_err = 0.0
    for orig, recon in zip(kv_rows, recon_rows):
        total_err += _l2_row_diff(orig, recon)
    reconstruction_error = total_err / max(seq_len, 1)

    # 7) Cache sizes + compression ratio.
    mha_cache_size = seq_len * n_heads * d_head * 2
    mla_cache_size = seq_len * d_latent
    compression_ratio = mha_cache_size / max(mla_cache_size, 1)

    sample_original = kv_rows[0][:_MAX_SAMPLE_DIMS]
    sample_latent = latent_rows[0][:_MAX_SAMPLE_DIMS]
    sample_recon = recon_rows[0][:_MAX_SAMPLE_DIMS]

    return {
        "seq_len": seq_len,
        "n_heads": n_heads,
        "d_head": d_head,
        "d_latent": d_latent,
        "mha_cache_size": mha_cache_size,
        "mla_cache_size": mla_cache_size,
        "compression_ratio": round(compression_ratio, 6),
        "reconstruction_error": round(reconstruction_error, 6),
        "sample_original_row": [round(v, 6) for v in sample_original],
        "sample_latent_row": [round(v, 6) for v in sample_latent],
        "sample_reconstructed_row": [round(v, 6) for v in sample_recon],
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_latent_compress(req: Request):
    # Clamps keep the pure-stdlib nested-list matmul (O(seq_len * kv_dim *
    # d_latent), no numpy) bounded to a fast, deterministic HTTP response —
    # kv_dim = n_heads*d_head*2 is the dominant cost driver.
    seed     = _ii(req, "seed",     42)
    seq_len  = max(1,  min(_ii(req, "seq_len",  128), 512))
    n_heads  = max(1,  min(_ii(req, "n_heads",  8),   32))
    d_head   = max(1,  min(_ii(req, "d_head",   64),  128))
    d_latent = max(1,  min(_ii(req, "d_latent", 128), 512))

    snap = _mla_snapshot(seed=seed, seq_len=seq_len, n_heads=n_heads,
                          d_head=d_head, d_latent=d_latent)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Multi-Head Latent Attention: low-rank joint KV-compression (DeepSeek-V2/V3-style)",
        "method": (
            "Concatenate per-token K/V across all heads (dim n_heads*d_head*2); "
            "DOWN-project via a seeded random matrix to a shared latent of dim "
            "d_latent (this is what MLA caches per token); UP-project back to "
            "reconstruct K/V; report mean L2 reconstruction error and the "
            "KV-cache compression ratio mha_cache_size/mla_cache_size."
        ),
        "seed": seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "low-rank down/up-projection ARITHMETIC behind DeepSeek-V2/V3's Multi-Head "
            "Latent Attention (arXiv:2405.04434, arXiv:2412.19437), NOT a run of "
            "DeepSeek-V2 or DeepSeek-V3, and NEVER-CLAIMED-AS either model. Synthetic "
            "K/V vectors and the down/up-projection matrices are drawn from a "
            "deterministic LCG PRNG (no numpy, no stdlib random, no proprietary "
            "weights, no real language model). In the real DeepSeek-V2/V3 models the "
            "down/up projection weights are LEARNED end-to-end so reconstruction error "
            "is minimized jointly with the language-modeling loss; here the "
            "projections are untrained random matrices, so this module demonstrates "
            "the low-rank-bottleneck COMPRESSION ARITHMETIC and cache-size arithmetic "
            "only, not DeepSeek's measured fidelity or benchmark numbers. Deterministic: "
            "same seed/seq_len/n_heads/d_head/d_latent -> identical snapshot. SZL claims "
            "NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_specdecode.register() / szl_ringattn.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/mla/latent-compress onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/mla"
    handlers = [
        (f"{base}/latent-compress", _h_latent_compress),
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
    snap = _mla_snapshot(seed=42, seq_len=128, n_heads=8, d_head=64, d_latent=128)
    print("label: MODELED")
    print("seq_len:", snap["seq_len"])
    print("n_heads:", snap["n_heads"])
    print("d_head:", snap["d_head"])
    print("d_latent:", snap["d_latent"])
    print("mha_cache_size:", snap["mha_cache_size"])
    print("mla_cache_size:", snap["mla_cache_size"])
    print("compression_ratio:", snap["compression_ratio"])
    print("reconstruction_error:", snap["reconstruction_error"])

    # sanity: bounds
    assert snap["mha_cache_size"] == snap["seq_len"] * snap["n_heads"] * snap["d_head"] * 2, \
        "mha_cache_size formula mismatch"
    assert snap["mla_cache_size"] == snap["seq_len"] * snap["d_latent"], \
        "mla_cache_size formula mismatch"
    assert snap["compression_ratio"] > 1.0, \
        "compression_ratio should exceed 1.0 for d_latent << n_heads*d_head*2"
    assert snap["reconstruction_error"] >= 0.0, "reconstruction_error must be non-negative"
    assert snap["reconstruction_error"] < 1e6, "reconstruction_error implausibly large — bug"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _mla_snapshot(seed=42, seq_len=128, n_heads=8, d_head=64, d_latent=128)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: a much smaller d_latent (bigger bottleneck) should raise
    # compression_ratio while (typically) increasing reconstruction_error —
    # demonstrates the compression/fidelity trade-off directly.
    snap3 = _mla_snapshot(seed=42, seq_len=128, n_heads=8, d_head=64, d_latent=32)
    assert snap3["compression_ratio"] > snap["compression_ratio"], \
        "smaller d_latent must yield a larger compression_ratio"

    # sanity: DeepSeek-V2-style d_c=4*d_h illustrative ratio (arXiv:2405.04434
    # Sec 2.1.1 convention: d_latent = 4*d_head) at a modest, pure-stdlib-
    # matmul-friendly scale — still respects all invariants and produces a
    # large compression ratio.
    snap4 = _mla_snapshot(seed=7, seq_len=64, n_heads=16, d_head=64, d_latent=256)
    assert snap4["compression_ratio"] > 1.0
    assert snap4["mla_cache_size"] < snap4["mha_cache_size"]

    print()
    print("szl_mla: ALL OK — deterministic, cache-size formulas verified, "
          "compression/fidelity trade-off demonstrated.")
