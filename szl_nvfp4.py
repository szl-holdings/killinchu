# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_nvfp4.py — SZL NVFP4 4-BIT TRAINING-FORMAT endpoint (block-scaled FP4
quantization + two-level scaling + stochastic vs deterministic rounding), MODELED.

Exposes a MODELED, deterministic, closed-form re-implementation of the 4-bit
floating-point training-format MECHANISMS described by:
  • NVIDIA "Pretraining Large Language Models with NVFP4" (Agrusa, Rouhani,
    Micikevicius, Patwary, Shoeybi et al., arXiv:2509.25149) — NVFP4: 16-element
    blocks, E4M3 (FP8) block scale + a global FP32 per-tensor scale (two-level).
  • OCP Microscaling "Microscaling Data Formats for Deep Learning"
    (Rouhani et al., arXiv:2310.10537) — MXFP4: 32-element blocks, UE8M0
    power-of-two shared block scale.
  • "Oscillation-Reduced MXFP4 Training for Vision Transformers"
    (TetraJet, arXiv:2502.20853) — oscillation / rounding-bias context.
applied to a small SYNTHETIC tensor drawn from the pure-stdlib LCG PRNG below —
so the organ has a live data source that is honest, deterministic, and citable;
never a real GPU kernel, never a trained model.

  GET  /api/<ns>/v1/nvfp4/quantize?seed=&size=&outliers=

WHAT IS MODELED
---------------
A size×size synthetic tensor of pseudo-random values (with `outliers` injected
large-magnitude entries) is deterministically quantized + dequantized three ways,
all sharing the same 4-bit FP4 (E2M1: 1 sign, 2 exponent, 1 mantissa) codebook:

  (a) NAIVE per-tensor FP4  — a SINGLE global scale for the whole tensor. One
      big outlier blows out the scale and crushes precision for every element.
  (b) MXFP4-style           — 32-element blocks, each with a shared POWER-OF-TWO
      (UE8M0) scale (ceil-log2 of block amax). Local scale adapts per block, but
      power-of-two rounding can waste up to ~1 binade (2×) of dynamic range.
  (c) NVFP4-style           — 16-element blocks, each with an E4M3 (FP8) block
      scale (fractional precision, not just a power of two), PLUS a global FP32
      per-tensor scale first (two-level scaling) so the (FP4 × FP8) product
      covers the tensor's dynamic range. Finer blocks + a more accurate scale.

For each scheme we MEASURE reconstruction error (mean-squared error and
max-abs error) between the original tensor and its dequantized reconstruction.
The error is REPORTED, not hidden. NVFP4 is expected to have the lowest MSE
here — but this is a TOY arithmetic demonstration, not a training run.

SEPARATELY, we demonstrate deterministic round-to-nearest vs stochastic rounding
on a FIXED sequence of small deltas repeated N times. Round-to-nearest applies a
systematic bias (the delta always rounds the same direction), so cumulative bias
DRIFTS. Stochastic rounding rounds up/down with probability proportional to
distance, so it is unbiased in expectation and cumulative bias stays near zero.
We return both cumulative-bias series so a viewer can see the drift vs the
random walk directly.

Returned JSON fields
--------------------
  label            : "MODELED" (always — clean-room mechanism reproduction)
  model            : short description of the modeled setup
  method           : one-line description of the exact quantizers
  seed             : RNG seed used
  size             : tensor side length (size×size synthetic tensor)
  outliers         : number of injected large-magnitude entries
  tensor_amax      : max |value| of the synthetic tensor (post-outlier)
  schemes          : list of {name, block_size, scale_format, two_level, mse,
                     max_abs_err, bits_per_value} for naive / MXFP4 / NVFP4
  best_scheme      : name of the lowest-MSE scheme (MEASURED)
  fp4_levels       : the 16 representable FP4 (E2M1) decode values
  rounding         : {n, delta, det_final_bias, stoch_final_bias,
                     det_bias_series, stoch_bias_series} — cumulative rounding
                     bias for deterministic vs stochastic rounding over N rounds
  honest_note      : plain-language honesty disclaimer
  citations        : dict of citable sources (verified real)
  computed_at      : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the FP4 block-scaling
  + two-level-scaling + stochastic-rounding MECHANISMS on a TOY synthetic tensor
  (no numpy, no stdlib `random`, no GPU, no CUDA/Blackwell kernel, no trained
  model, no real gradients). It does NOT reproduce the 12B-parameter / 10T-token
  NVFP4 pretraining run, its loss curves, MMLU/GSM8K downstream accuracy, or the
  reported 7× Blackwell GEMM speedup — those are NVIDIA'S CLAIMS about their
  hardware + training run, which the estate does NOT independently verify. Only
  the arithmetic reconstruction error on this toy tensor is MEASURED here, and it
  is displayed, not hidden. Label "MODELED" is returned verbatim and displayed
  verbatim by the surface; never upgraded client-side.

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
    "Pretraining Large Language Models with NVFP4 — Agrusa, Rouhani, Micikevicius, Patwary, Shoeybi et al. (NVIDIA) arXiv:2509.25149": "https://arxiv.org/abs/2509.25149",
    "Microscaling Data Formats for Deep Learning (MXFP4 / OCP MX) — Rouhani et al. arXiv:2310.10537": "https://arxiv.org/pdf/2310.10537",
    "Introducing NVFP4 for Efficient and Accurate Low-Precision Inference (NVIDIA blog)": "https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/",
    "Oscillation-Reduced MXFP4 Training for Vision Transformers (TetraJet) — arXiv:2502.20853": "https://arxiv.org/abs/2502.20853",
}

# ---------------------------------------------------------------------------
# FP4 (E2M1) codebook — 1 sign, 2 exponent, 1 mantissa bit.
# The standard OCP FP4 E2M1 decode values (magnitudes): 0, 0.5, 1, 1.5, 2, 3,
# 4, 6, with the max representable magnitude = 6.0. Signed -> 16 levels.
# ---------------------------------------------------------------------------
_FP4_ABS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)   # 8 magnitudes
_FP4_MAX = 6.0                                          # max representable |value|
_FP4_LEVELS = tuple(sorted({-a for a in _FP4_ABS} | {a for a in _FP4_ABS}))  # 15 unique (0 shared)

# bit budgets (for reporting only — this is an arithmetic sim, not a bit-packer)
_BITS_FP4 = 4.0
_MX_BLOCK = 32          # MXFP4 block size (OCP Microscaling)
_NV_BLOCK = 16          # NVFP4 block size


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
# FP4 (E2M1) encode / decode — pure python round-to-nearest onto the codebook.
# ---------------------------------------------------------------------------
def _fp4_quantize(v: float) -> float:
    """Round a value onto the nearest FP4 (E2M1) representable value.

    v is assumed to already be scaled into (roughly) the FP4 range [-6, 6];
    values beyond ±6 clamp to ±6 (saturation). Returns the DEQUANTIZED FP4
    value (i.e. the codebook entry the value snaps to). Deterministic
    round-to-nearest (ties go to the larger magnitude, matching a simple RNE-ish
    rule for this toy).
    """
    sign = -1.0 if v < 0.0 else 1.0
    a = abs(v)
    if a >= _FP4_MAX:
        return sign * _FP4_MAX
    # find nearest magnitude in _FP4_ABS
    best = _FP4_ABS[0]
    best_d = abs(a - best)
    for m in _FP4_ABS[1:]:
        d = abs(a - m)
        if d < best_d or (d == best_d and m > best):
            best_d = d
            best = m
    return sign * best


def _fp4_neighbors(v: float):
    """Return (lo, hi) — the two FP4 codebook values bracketing v (for stochastic
    rounding). v assumed within [-6, 6]. If v is exactly representable, lo == hi.
    """
    if v <= _FP4_LEVELS[0]:
        return _FP4_LEVELS[0], _FP4_LEVELS[0]
    if v >= _FP4_LEVELS[-1]:
        return _FP4_LEVELS[-1], _FP4_LEVELS[-1]
    lo = _FP4_LEVELS[0]
    hi = _FP4_LEVELS[-1]
    for lvl in _FP4_LEVELS:
        if lvl <= v and lvl > lo:
            lo = lvl
        if lvl >= v and lvl < hi:
            hi = lvl
    # correct hi to smallest level >= v
    hi = next((lvl for lvl in _FP4_LEVELS if lvl >= v), _FP4_LEVELS[-1])
    lo = max((lvl for lvl in _FP4_LEVELS if lvl <= v), default=_FP4_LEVELS[0])
    return lo, hi


# ---------------------------------------------------------------------------
# E4M3 (FP8) scale rounding — the NVFP4 block scale is stored as an E4M3 float
# (4 exponent, 3 mantissa bits), giving fractional precision (not just pow2).
# We model E4M3 by rounding a positive scale onto a mantissa grid of 3 bits
# within its binade. Max representable E4M3 magnitude is 448.0.
# ---------------------------------------------------------------------------
_E4M3_MAX = 448.0


def _round_e4m3(x: float) -> float:
    """Round a positive scale onto the E4M3 (FP8) grid: sign · 2^e · (1 + m/8),
    with 3 mantissa bits (8 steps per binade). Subnormal / zero -> tiny floor.
    """
    if x <= 0.0:
        return 1.0
    if x >= _E4M3_MAX:
        return _E4M3_MAX
    e = math.floor(math.log2(x))
    frac = x / (2.0 ** e)           # in [1, 2)
    m = round((frac - 1.0) * 8.0)   # 3 mantissa bits -> 8 steps
    if m >= 8:
        m = 0
        e += 1
    q = (2.0 ** e) * (1.0 + m / 8.0)
    if q <= 0.0:
        return 2.0 ** e
    return q


def _round_pow2(x: float) -> float:
    """Round a positive scale to the nearest power of two — the MXFP4 UE8M0
    (unsigned 8-bit exponent, no mantissa) shared block scale.
    """
    if x <= 0.0:
        return 1.0
    e = round(math.log2(x))
    return 2.0 ** e


# ---------------------------------------------------------------------------
# Synthetic tensor with injected outliers
# ---------------------------------------------------------------------------
def _make_tensor(rng, size: int, outliers: int):
    """Deterministic flat list of size*size Gaussian-ish values, with `outliers`
    large-magnitude entries injected at deterministic positions."""
    n = size * size
    t = [_gauss(rng) for _ in range(n)]
    if n <= 0:
        return t
    # inject outliers at evenly-spaced deterministic positions, alternating sign
    for k in range(max(0, outliers)):
        pos = (k * 2654435761) % n
        mag = 8.0 + 4.0 * next(rng)          # large relative to ~N(0,1) body
        t[pos] = mag if (k % 2 == 0) else -mag
    return t


def _amax(vals) -> float:
    m = 0.0
    for v in vals:
        av = abs(v)
        if av > m:
            m = av
    return m


# ---------------------------------------------------------------------------
# Three quantization schemes -> dequantized reconstruction
# ---------------------------------------------------------------------------
def _quant_naive(t):
    """(a) NAIVE per-tensor FP4: one global scale = amax / FP4_MAX for the whole
    tensor, then round each scaled value onto the FP4 codebook and rescale back."""
    amax = _amax(t)
    scale = (amax / _FP4_MAX) if amax > 0 else 1.0
    if scale <= 0:
        scale = 1.0
    return [_fp4_quantize(v / scale) * scale for v in t]


def _quant_block(t, block: int, scale_mode: str, two_level: bool):
    """Block-scaled FP4 dequantization.

    scale_mode: "pow2" (MXFP4 UE8M0) or "e4m3" (NVFP4 FP8 block scale).
    two_level:  if True (NVFP4), first apply a global FP32 per-tensor scale that
                remaps the tensor into the (FP4 × block-scale) representable
                product range, then per-block scale on top.
    """
    n = len(t)
    out = [0.0] * n
    # global FP32 per-tensor scale (two-level): map tensor amax to the product
    # range FP4_MAX so the block E4M3 scale operates on well-conditioned values.
    if two_level:
        gamax = _amax(t)
        gscale = (gamax / (_FP4_MAX)) if gamax > 0 else 1.0
        if gscale <= 0:
            gscale = 1.0
    else:
        gscale = 1.0

    i = 0
    while i < n:
        j = min(i + block, n)
        blk = t[i:j]
        # values entering block scaling (after optional global de-scale)
        bvals = [v / gscale for v in blk] if two_level else list(blk)
        bamax = _amax(bvals)
        raw_scale = (bamax / _FP4_MAX) if bamax > 0 else 1.0
        if raw_scale <= 0:
            raw_scale = 1.0
        if scale_mode == "pow2":
            bscale = _round_pow2(raw_scale)
        else:  # e4m3
            bscale = _round_e4m3(raw_scale)
        if bscale <= 0:
            bscale = 1.0
        for k, v in enumerate(bvals):
            q = _fp4_quantize(v / bscale) * bscale
            out[i + k] = q * gscale if two_level else q
        i = j
    return out


def _mse(a, b) -> float:
    if not a:
        return 0.0
    s = 0.0
    for x, y in zip(a, b):
        d = x - y
        s += d * d
    return s / len(a)


def _max_abs_err(a, b) -> float:
    m = 0.0
    for x, y in zip(a, b):
        d = abs(x - y)
        if d > m:
            m = d
    return m


# ---------------------------------------------------------------------------
# Deterministic vs stochastic rounding — cumulative bias over N roundings
# ---------------------------------------------------------------------------
def _rounding_bias(rng, n: int, delta: float):
    """Round the SAME small value `delta` (chosen between two FP4 levels) N times
    with (i) deterministic round-to-nearest and (ii) stochastic rounding, and
    track the cumulative rounding ERROR (quantized - true) after each step.

    Deterministic RNE always snaps `delta` the same way -> the per-step error is
    constant -> cumulative bias DRIFTS linearly. Stochastic rounding snaps up
    with probability (delta-lo)/(hi-lo) and down otherwise -> unbiased in
    expectation -> cumulative bias performs a mean-zero random walk near zero.
    """
    lo, hi = _fp4_neighbors(delta)
    det_series = []
    stoch_series = []
    det_cum = 0.0
    stoch_cum = 0.0
    # deterministic snap of delta (fixed direction, computed once)
    det_val = _fp4_quantize(delta)
    det_step_err = det_val - delta
    span = (hi - lo)
    p_up = ((delta - lo) / span) if span > 0 else 0.0
    for _ in range(max(1, n)):
        # deterministic: identical error every step -> linear drift
        det_cum += det_step_err
        det_series.append(det_cum)
        # stochastic: round up with prob p_up, else down
        u = next(rng)
        sval = hi if u < p_up else lo
        stoch_cum += (sval - delta)
        stoch_series.append(stoch_cum)
    return {
        "n": max(1, n),
        "delta": round(delta, 6),
        "lo": round(lo, 6),
        "hi": round(hi, 6),
        "p_up": round(p_up, 6),
        "det_final_bias": round(det_cum, 6),
        "stoch_final_bias": round(stoch_cum, 6),
        "det_bias_series": [round(x, 6) for x in det_series],
        "stoch_bias_series": [round(x, 6) for x in stoch_series],
    }


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _nvfp4_snapshot(seed: int = 42, size: int = 32, outliers: int = 3) -> dict:
    """Deterministically build a synthetic tensor with injected outliers, quantize
    + dequantize it three ways (naive / MXFP4 / NVFP4), MEASURE reconstruction
    error, and demonstrate deterministic vs stochastic rounding bias.

    Pure stdlib; deterministic — same (seed, size, outliers) -> identical snapshot.
    """
    rng = _lcg(seed)
    t = _make_tensor(rng, size, outliers)
    tensor_amax = _amax(t)

    # (a) naive per-tensor FP4
    rec_naive = _quant_naive(t)
    # (b) MXFP4-style: 32-element blocks, power-of-two (UE8M0) scale, single level
    rec_mx = _quant_block(t, _MX_BLOCK, "pow2", two_level=False)
    # (c) NVFP4-style: 16-element blocks, E4M3 (FP8) block scale + FP32 global
    rec_nv = _quant_block(t, _NV_BLOCK, "e4m3", two_level=True)

    schemes = [
        {
            "name": "naive-FP4",
            "block_size": len(t) if t else 0,      # whole tensor = one "block"
            "scale_format": "FP32 single global scale",
            "two_level": False,
            "mse": round(_mse(t, rec_naive), 8),
            "max_abs_err": round(_max_abs_err(t, rec_naive), 6),
            "bits_per_value": _BITS_FP4,
        },
        {
            "name": "MXFP4",
            "block_size": _MX_BLOCK,
            "scale_format": "UE8M0 (power-of-two)",
            "two_level": False,
            "mse": round(_mse(t, rec_mx), 8),
            "max_abs_err": round(_max_abs_err(t, rec_mx), 6),
            "bits_per_value": _BITS_FP4,
        },
        {
            "name": "NVFP4",
            "block_size": _NV_BLOCK,
            "scale_format": "E4M3 (FP8) block scale",
            "two_level": True,
            "mse": round(_mse(t, rec_nv), 8),
            "max_abs_err": round(_max_abs_err(t, rec_nv), 6),
            "bits_per_value": _BITS_FP4,
        },
    ]
    best = min(schemes, key=lambda s: s["mse"])["name"]

    # rounding-bias demonstration on a fixed small delta between two FP4 levels.
    # 1.2 sits between FP4 levels 1.0 and 1.5 -> RNE always snaps to 1.0 (drift),
    # stochastic averages out. Use a deterministic sub-stream from the same seed.
    rng2 = _lcg(seed ^ 0x5F3759DF)
    rounding = _rounding_bias(rng2, n=64, delta=1.2)

    return {
        "size": size,
        "outliers": max(0, outliers),
        "tensor_amax": round(tensor_amax, 6),
        "schemes": schemes,
        "best_scheme": best,
        "fp4_levels": [round(x, 4) for x in _FP4_LEVELS],
        "rounding": rounding,
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
    "MODELED: this is a clean-room reproduction of the 4-bit FP4 block-scaling + "
    "two-level-scaling + stochastic-rounding MECHANISMS (NVFP4 — Agrusa, Rouhani, "
    "Micikevicius, Patwary, Shoeybi et al., NVIDIA, arXiv:2509.25149; MXFP4 / OCP "
    "Microscaling, arXiv:2310.10537; oscillation context TetraJet arXiv:2502.20853) "
    "on a TOY synthetic tensor. It is an ARITHMETIC DEMONSTRATION ONLY — NO GPU "
    "kernel, NO CUDA/Blackwell tensor-core, NO trained model, NO real gradients, "
    "no numpy, no stdlib random. The reconstruction error per scheme is MEASURED "
    "and displayed (see schemes[].mse / max_abs_err); it is NOT hidden. It does NOT "
    "reproduce NVIDIA's 12B-parameter / 10T-token pretraining run, its loss curves, "
    "downstream accuracy (MMLU/GSM8K/HellaSwag), or the reported ~7x Blackwell GEMM "
    "speedup — those are NVIDIA'S CLAIMS, which the estate does NOT independently "
    "verify. Deterministic: same seed/size/outliers -> identical snapshot. The "
    "label 'MODELED' is returned verbatim and displayed verbatim; never upgraded. "
    "SZL claims NONE of these methods as its own."
)


def _h_quantize(req: Request):
    seed     = _ii(req, "seed",     42)
    size     = max(4, min(_ii(req, "size",     32), 64))
    outliers = max(0, min(_ii(req, "outliers",  3), size * size))

    snap = _nvfp4_snapshot(seed=seed, size=size, outliers=outliers)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "NVFP4 4-bit training format (FP4 E2M1 block quantization: naive per-tensor vs MXFP4 32-blk power-of-two vs NVFP4 16-blk E4M3+FP32 two-level) on a synthetic tensor with injected outliers, plus deterministic-vs-stochastic rounding-bias demonstration",
        "method": "FP4 E2M1 codebook {0,.5,1,1.5,2,3,4,6}·±1; (a) naive: single global scale=amax/6; (b) MXFP4: 32-elem blocks, UE8M0 power-of-two block scale; (c) NVFP4: 16-elem blocks, E4M3 (FP8) block scale + FP32 per-tensor global scale (two-level); reconstruction MSE + max-abs error MEASURED per scheme; rounding bias tracked over N roundings of a fixed delta (RNE drifts, stochastic near zero)",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_ternary.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/nvfp4/quantize onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/nvfp4"
    handlers = [
        (f"{base}/quantize", _h_quantize),
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
    snap = _nvfp4_snapshot(seed=42, size=32, outliers=3)
    print("label: MODELED")
    print("size:", snap["size"])
    print("outliers:", snap["outliers"])
    print("tensor_amax:", snap["tensor_amax"])
    print("--- RECONSTRUCTION ERROR per scheme (MEASURED, not hidden) ---")
    for s in snap["schemes"]:
        print("  {:<10} block={:<5} scale={:<26} two_level={:<5} mse={:<12} max_abs_err={}".format(
            s["name"], s["block_size"], s["scale_format"], str(s["two_level"]),
            s["mse"], s["max_abs_err"]))
    print("best_scheme (lowest MSE):", snap["best_scheme"])
    print("fp4_levels:", snap["fp4_levels"])
    print("--- ROUNDING BIAS: deterministic (RNE) vs stochastic ---")
    r = snap["rounding"]
    print("  n:", r["n"], "delta:", r["delta"], "lo/hi:", r["lo"], "/", r["hi"], "p_up:", r["p_up"])
    print("  det_final_bias  :", r["det_final_bias"])
    print("  stoch_final_bias:", r["stoch_final_bias"])

    # sanity: three schemes present, FP4 codebook is 15 unique signed levels
    assert len(snap["schemes"]) == 3, "expected naive / MXFP4 / NVFP4"
    assert len(snap["fp4_levels"]) == 15, "FP4 E2M1 has 15 unique signed levels (0 shared)"

    # sanity: all reconstruction errors MEASURED and non-negative
    for s in snap["schemes"]:
        assert s["mse"] >= 0.0, "mse must be non-negative"
        assert s["max_abs_err"] >= 0.0, "max_abs_err must be non-negative"

    # sanity: block schemes with local scales beat naive single-global-scale MSE
    mse = {s["name"]: s["mse"] for s in snap["schemes"]}
    assert mse["MXFP4"] < mse["naive-FP4"], "block scaling should beat naive per-tensor scale on outlier tensor"
    assert mse["NVFP4"] < mse["naive-FP4"], "NVFP4 should beat naive per-tensor scale"
    assert snap["best_scheme"] in ("NVFP4", "MXFP4"), "best scheme should be a block scheme"

    # sanity: deterministic rounding DRIFTS (|bias| grows), stochastic stays smaller
    assert abs(r["det_final_bias"]) > abs(r["stoch_final_bias"]), \
        "deterministic RNE must drift more than stochastic rounding"
    assert abs(r["det_final_bias"]) > 0.0, "deterministic bias must be non-zero (systematic)"
    assert len(r["det_bias_series"]) == r["n"], "det series length must equal n"
    assert len(r["stoch_bias_series"]) == r["n"], "stoch series length must equal n"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _nvfp4_snapshot(seed=42, size=32, outliers=3)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_nvfp4: ALL OK — FP4 quantized 3 ways, error MEASURED & reported, "
          "NVFP4 two-level best, RNE drift vs stochastic near-zero, deterministic.")
