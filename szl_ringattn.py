# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_ringattn.py — RING-ATTENTION LONG-CONTEXT BLOCKWISE SIMULATOR.

Exposes a MODELED, deterministic, pure-stdlib simulation of Ring Attention's
core numerical trick — blockwise online-softmax attention with key/value blocks
rotated around a logical ring of `devices` — as a same-origin/cross-origin REST
endpoint, so the ring-attention surface organ has a live data source that is
honest, deterministic, and citable — never fabricated, never a real multi-device
run, never a trained model.

  GET /api/<ns>/v1/ringattn/simulate?seed=&seq_len=&devices=&block_size=&d_head=

WHAT THIS MODELS (clean-room, cited, deterministic from seed)
---------------------------------------------------------------------------
Ring Attention (Liu, Zaharia & Abbeel 2023, arXiv:2310.01889) shards a long
sequence's Q/K/V across a logical ring of `devices`. Each device holds one
Q-block permanently and rotates KV-blocks around the ring in `devices` steps
(num_rotation_steps == devices), computing partial attention against each KV
block it sees and accumulating the result with the numerically-stable
"blockwise online-softmax" trick introduced by Blockwise Parallel Transformer
(Liu & Abbeel 2023, arXiv:2305.19370): a running max `m` and running
(unnormalized) weighted sum are updated block-by-block, rescaling the
previous partial sum whenever a new block raises the running max, so the
final normalized result is IDENTICAL to softmax computed over the full
un-blocked sequence — this is the "exactness" property Ring Attention
inherits from BPT/FlashAttention-style online softmax: it is a communication
schedule for EXACT attention, not an approximation.

This module:
  1. Builds deterministic synthetic Q/K/V for a sequence of length `seq_len`
     and head dimension `d_head`, using a pure-stdlib LCG PRNG (no numpy, no
     `random` module) seeded by `seed` — fully reproducible.
  2. Computes FULL (unblocked) softmax attention output for one query token
     directly, as the ground truth.
  3. Computes the SAME attention via blockwise online-softmax accumulation:
     the KV sequence is split into `devices` blocks of `block_size` each
     (block_size = ceil(seq_len/devices)) and "rotated" past the query one
     block at a time (num_rotation_steps == devices), updating the running
     max/sum/output accumulators after each block exactly as Ring Attention's
     per-device inner loop would.
  4. Asserts (and reports) `exact_match`: the blockwise result equals the full
     result to float precision — demonstrating Ring Attention's central
     numerical claim (exact attention, not an approximation) — while the
     per-device memory footprint is only O(seq_len/devices) instead of
     O(seq_len) (`per_device_memory_ratio = 1/devices`).

HONEST STATUS — "MODELED"
---------------------------------------------------------------------------
This is a deterministic, pure-stdlib, single-process SIMULATION of the
blockwise online-softmax accumulation math that underlies Ring Attention. It
is NOT a trained model, NOT a run of any real multi-device/multi-GPU kernel,
and is NEVER-CLAIMED-AS a production Ring Attention implementation. Query/
key/value tensors are synthetic, deterministic values from an LCG PRNG — not
real model activations. The label "MODELED" is returned verbatim in every
response and must be displayed verbatim by any surface; it is never upgraded.

CITATIONS (clean-room; none claimed as SZL's own)
---------------------------------------------------------------------------
  Ring Attention:
    Liu, H., Zaharia, M. & Abbeel, P. (2023) "Ring Attention with Blockwise
    Transformers for Near-Infinite Context." arXiv:2310.01889.
    https://arxiv.org/abs/2310.01889
  Blockwise Parallel Transformer (the online-softmax blockwise trick):
    Liu, H. & Abbeel, P. (2023) "Blockwise Parallel Transformer for Large
    Context Models." arXiv:2305.19370. https://arxiv.org/abs/2305.19370
  Reference implementation:
    haoliuhl/ringattention — https://github.com/haoliuhl/ringattention

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (no numpy, no `random` module — deterministic
  LCG PRNG, same family used by szl_neuromorphic.py / sibling organs).
  Deterministic with seed. 0 runtime CDN.
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
    "Ring Attention — Liu, Zaharia & Abbeel 2023, arXiv:2310.01889": "https://arxiv.org/abs/2310.01889",
    "Blockwise Parallel Transformer — Liu & Abbeel 2023, arXiv:2305.19370": "https://arxiv.org/abs/2305.19370",
    "Reference implementation — haoliuhl/ringattention": "https://github.com/haoliuhl/ringattention",
}

HONESTY_LABEL = "MODELED"

# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no `random` module)
# ---------------------------------------------------------------------------
_LCG_A = 1103515245
_LCG_C = 12345
_LCG_M = 2 ** 31


class _LCG:
    """Minimal deterministic linear-congruential generator. Same seed -> same
    stream, forever, with no dependence on stdlib `random` or numpy."""

    __slots__ = ("state",)

    def __init__(self, seed: int):
        self.state = int(seed) % _LCG_M

    def next_float(self) -> float:
        """Uniform float in [0, 1)."""
        self.state = (_LCG_A * self.state + _LCG_C) % _LCG_M
        return self.state / _LCG_M

    def next_signed(self) -> float:
        """Uniform float in [-1, 1)."""
        return 2.0 * self.next_float() - 1.0


def _make_qkv(seed: int, seq_len: int, d_head: int):
    """Deterministic synthetic Q (single query token, d_head,), K (seq_len x
    d_head), V (seq_len x d_head) via the pure-stdlib LCG PRNG. Values are
    scaled small (±1/sqrt(d_head)-ish) to keep softmax numerically sane —
    this is purely a clean-room numerical harness, not real activations."""
    rng = _LCG(seed)
    scale = 1.0 / math.sqrt(max(d_head, 1))
    q = [rng.next_signed() * scale for _ in range(d_head)]
    K = [[rng.next_signed() * scale for _ in range(d_head)] for _ in range(seq_len)]
    V = [[rng.next_signed() for _ in range(d_head)] for _ in range(seq_len)]
    return q, K, V


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Ground truth: full (unblocked) softmax attention for one query token
# ---------------------------------------------------------------------------
def _full_attention(q, K, V, d_head: int):
    """Standard scaled-dot-product softmax attention over the ENTIRE sequence
    at once (the O(seq_len) memory baseline Ring Attention avoids). Returns
    (output_vector, running_max_used, running_sum_used)."""
    inv_sqrt_d = 1.0 / math.sqrt(max(d_head, 1))
    scores = [_dot(q, K[j]) * inv_sqrt_d for j in range(len(K))]
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    denom = sum(exps)
    out = [0.0] * d_head
    for j, w in enumerate(exps):
        wv = w / denom
        for d in range(d_head):
            out[d] += wv * V[j][d]
    return out, m, denom


# ---------------------------------------------------------------------------
# Blockwise online-softmax accumulation — the Ring Attention / BPT trick
# ---------------------------------------------------------------------------
def _blockwise_ring_attention(q, K, V, d_head: int, devices: int, block_size: int):
    """Simulate KV-blocks rotating around a logical ring of `devices` devices,
    `devices` rotation steps total (num_rotation_steps == devices), each step
    absorbing one KV block of size <= block_size. Maintains the numerically
    stable running-max/running-sum online-softmax accumulator (Milakov &
    Gimelshein 2018 "online softmax" trick, as adopted by Blockwise Parallel
    Transformer / FlashAttention / Ring Attention) so the final result is
    mathematically IDENTICAL to full unblocked softmax attention, while never
    materializing more than one KV block (block_size rows) at a time — i.e.
    O(seq_len/devices) memory per device instead of O(seq_len).

    Returns (output_vector, num_steps, per_step_trace) where per_step_trace
    is a list of {step, running_max, running_sum} snapshots for visualization.
    """
    inv_sqrt_d = 1.0 / math.sqrt(max(d_head, 1))
    seq_len = len(K)

    running_max = -math.inf
    running_sum = 0.0
    running_out = [0.0] * d_head
    trace = []

    step = 0
    start = 0
    while start < seq_len:
        end = min(start + block_size, seq_len)
        block_scores = [_dot(q, K[j]) * inv_sqrt_d for j in range(start, end)]
        block_max = max(block_scores)
        new_max = max(running_max, block_max)

        # Rescale the previous accumulator if the running max increased
        # (the numerically-stable online-softmax correction).
        if running_max != -math.inf:
            correction = math.exp(running_max - new_max)
        else:
            correction = 0.0

        block_exp_sum = 0.0
        block_weighted = [0.0] * d_head
        for local_j, global_j in enumerate(range(start, end)):
            w = math.exp(block_scores[local_j] - new_max)
            block_exp_sum += w
            for d in range(d_head):
                block_weighted[d] += w * V[global_j][d]

        running_sum = running_sum * correction + block_exp_sum
        for d in range(d_head):
            running_out[d] = running_out[d] * correction + block_weighted[d]
        running_max = new_max

        step += 1
        trace.append({
            "step": step,
            "block_start": start,
            "block_end": end,
            "block_len": end - start,
            "running_max": round(running_max, 6),
            "running_sum": round(running_sum, 6),
        })
        start = end

    out = [v / running_sum for v in running_out]
    return out, step, trace


def _l2_diff(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# ---------------------------------------------------------------------------
# Simulation orchestrator
# ---------------------------------------------------------------------------
def simulate(seed: int = 42, seq_len: int = 4096, devices: int = 8,
             block_size: int | None = None, d_head: int = 64) -> dict:
    """Run the full simulate-and-verify pipeline. Deterministic: same
    (seed, seq_len, devices, block_size, d_head) -> byte-identical output."""
    seq_len = max(devices, seq_len)
    if block_size is None or block_size <= 0:
        block_size = max(1, math.ceil(seq_len / devices))

    q, K, V = _make_qkv(seed, seq_len, d_head)

    full_out, full_max, full_sum = _full_attention(q, K, V, d_head)
    block_out, num_steps, trace = _blockwise_ring_attention(q, K, V, d_head, devices, block_size)

    diff = _l2_diff(full_out, block_out)
    exact_match = diff < 1e-9

    per_device_memory_ratio = round(1.0 / devices, 8)
    # max_context_supported: Ring Attention's headline claim — context length
    # scales linearly with device count vs. a fixed single-device baseline
    # capacity (MODELED single-device baseline = 8192 tokens, a representative
    # single-accelerator KV-cache-bound figure used purely for illustration).
    single_device_baseline_tokens = 8192
    max_context_supported = single_device_baseline_tokens * devices

    return {
        "label": HONESTY_LABEL,
        "model": "Ring Attention: blockwise online-softmax exact-attention accumulation over a logical device ring",
        "method": (
            "KV blocks rotate around a ring of `devices` devices in `devices` steps "
            "(num_rotation_steps == devices); each step updates a numerically-stable "
            "running-max/running-sum online-softmax accumulator (Blockwise Parallel "
            "Transformer, arXiv:2305.19370), yielding attention output IDENTICAL to "
            "full unblocked softmax (Ring Attention, arXiv:2310.01889) at "
            "O(seq_len/devices) memory per device instead of O(seq_len)."
        ),
        "seed": seed,
        "seq_len": seq_len,
        "devices": devices,
        "block_size": block_size,
        "d_head": d_head,
        "num_rotation_steps": num_steps,
        "per_device_memory_ratio": per_device_memory_ratio,
        "exact_match": bool(exact_match),
        "l2_diff_blockwise_vs_full": round(diff, 12),
        "full_attention_running_max": round(full_max, 6),
        "full_attention_running_sum": round(full_sum, 6),
        "single_device_baseline_tokens": single_device_baseline_tokens,
        "max_context_supported": max_context_supported,
        "rotation_trace": trace[:64],  # capped for payload size
        "full_output_sample": [round(x, 6) for x in full_out[:8]],
        "blockwise_output_sample": [round(x, 6) for x in block_out[:8]],
        "honest_note": (
            "MODELED: deterministic blockwise online-softmax simulation of ring-"
            "attention's exact-attention accumulation; NOT a trained model or real "
            "multi-device kernel; NEVER-CLAIMED-AS a production ring-attention "
            "implementation. Q/K/V are synthetic deterministic values from a pure-"
            "stdlib LCG PRNG (no numpy, no `random` module), not real model "
            "activations. exact_match compares the blockwise-accumulated result to "
            "full unblocked softmax attention computed on the SAME synthetic Q/K/V "
            "in-process (single process, not a real multi-device run) — it "
            "demonstrates the accumulation algebra is exact, not that this module "
            "ran on `devices` physical accelerators. Cite Liu, Zaharia & Abbeel 2023 "
            "(arXiv:2310.01889, Ring Attention) and Liu & Abbeel 2023 (arXiv:2305.19370, "
            "Blockwise Parallel Transformer). SZL claims NONE of these methods as its own."
        ),
        "citations": CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_simulate(req: Request):
    seed = _ii(req, "seed", 42)
    seq_len = max(8, min(_ii(req, "seq_len", 4096), 1_048_576))
    devices = max(2, min(_ii(req, "devices", 8), 256))
    block_size_raw = _ii(req, "block_size", 0)
    block_size = block_size_raw if block_size_raw > 0 else None
    d_head = max(4, min(_ii(req, "d_head", 64), 256))

    result = simulate(seed=seed, seq_len=seq_len, devices=devices,
                       block_size=block_size, d_head=d_head)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_neuromorphic.register() / sibling organs exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/ringattn/simulate onto app. Additive, try/except-
    guarded at the call site. Uses FastAPI add_api_route when available;
    falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/ringattn"
    handlers = [
        (f"{base}/simulate", _h_simulate),
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
    r = simulate(seed=42, seq_len=4096, devices=8, d_head=64)
    print("label:", r["label"])
    print("seq_len:", r["seq_len"])
    print("devices:", r["devices"])
    print("block_size:", r["block_size"])
    print("num_rotation_steps:", r["num_rotation_steps"])
    print("per_device_memory_ratio:", r["per_device_memory_ratio"])
    print("exact_match:", r["exact_match"])
    print("l2_diff_blockwise_vs_full:", r["l2_diff_blockwise_vs_full"])
    print("max_context_supported:", r["max_context_supported"])

    # --- assertions proving exactness + determinism + doctrine compliance ---
    assert r["label"] == "MODELED"
    assert r["exact_match"] is True, "blockwise result MUST equal full-attention result"
    assert r["l2_diff_blockwise_vs_full"] < 1e-9
    assert r["num_rotation_steps"] == r["devices"], "num_rotation_steps must equal devices"
    assert abs(r["per_device_memory_ratio"] - 1.0 / r["devices"]) < 1e-12
    assert r["max_context_supported"] == 8192 * r["devices"]

    # determinism: same seed/params -> byte-identical result
    r2 = simulate(seed=42, seq_len=4096, devices=8, d_head=64)
    assert r["blockwise_output_sample"] == r2["blockwise_output_sample"]
    assert r["full_output_sample"] == r2["full_output_sample"]
    assert r["rotation_trace"] == r2["rotation_trace"]

    # different device counts must still be exact (varies block partitioning)
    for dv in (2, 4, 16, 32):
        rr = simulate(seed=7, seq_len=2048, devices=dv, d_head=32)
        assert rr["exact_match"] is True, f"failed exactness at devices={dv}"
        assert rr["num_rotation_steps"] == dv

    # non-divisible seq_len/devices edge case (uneven last block)
    ru = simulate(seed=3, seq_len=1000, devices=7, d_head=16)
    assert ru["exact_match"] is True

    print("\nszl_ringattn: ALL OK — exactness, determinism, and bounds all asserted.")
