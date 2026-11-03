# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_kvcache.py — SZL KV-CACHE H2O EVICTION endpoint (Heavy-Hitter Oracle runtime
cache eviction), MODELED.

Exposes a MODELED closed-form simulation of the H2O (Heavy-Hitter Oracle) KV-cache
eviction policy (Zhang et al. 2023) on a synthetic, seeded attention-mass trace, so
the KV-cache eviction surface organ has a live data source that is honest,
deterministic, and citable — never fabricated, never run against a real KV cache
or trained model.

  GET  /api/<ns>/v1/kvcache/h2o-evict?seed=&seq_len=&capacity=&window=

WHAT IS SIMULATED
------------------
During autoregressive decoding, a transformer's KV cache grows by one entry per
generated token; without eviction it grows unboundedly with `seq_len`. H2O
(Heavy-Hitter Oracle, Zhang et al. 2023, arXiv:2306.14048) observes that a small
subset of tokens ("heavy hitters") accumulate the bulk of cumulative attention
mass, and proposes retaining a KV cache of fixed `capacity` by keeping:
  (a) the top-(capacity - window) tokens by CUMULATIVE attention-mass score
      accrued so far (the heavy hitters), plus
  (b) the most recent `window` tokens (the local/recency window), following the
      complementary observation used by StreamingLLM (Xiao et al. 2023,
      arXiv:2309.17453) that recent tokens are also disproportionately attended.

This module builds a deterministic synthetic per-token attention-mass trace
(pure-stdlib LCG, no numpy, no stdlib `random`) over a decoding stream of
`seq_len` tokens, then evicts tokens from a bounded cache of `capacity` slots
under THREE policies, comparing the fraction of total attention mass retained
by each policy's final kept set:

  h2o             : keep top-(capacity - window) heavy hitters by cumulative
                    score + the most recent `window` tokens (Zhang et al. 2023)
  sliding_window  : keep ONLY the most recent `capacity` tokens (no heavy-hitter
                    retention at all — the naive recency-only baseline,
                    cf. Xiao et al. 2023's local-attention-only ablation)
  full_cache      : the oracle upper bound — every token ever generated is kept
                    (capacity == seq_len); mass_retained is definitionally 1.0

The reported hypothesis (MODELED, from the cited papers' claims, reproduced here
on a synthetic trace only): H2O retains materially more attention mass than a
sliding-window-only cache at the SAME memory budget, and approaches the
full-cache oracle's retained mass at a small fraction of its memory footprint.

Returned JSON fields
---------------------
  label                  : "MODELED" (always — deterministic re-implementation
                            of the H2O heavy-hitter eviction policy, NOT a real
                            KV cache or trained model)
  model                  : short description of the simulated setup
  seed                   : RNG seed used
  seq_len                : number of decoded tokens in the simulated stream
  capacity               : KV-cache slot budget (capacity <= seq_len)
  window                 : recent-token sliding-window size reserved inside capacity
  memory_ratio           : capacity / seq_len — fraction of full-cache memory used
  h2o_mass_retained      : sum(attention mass of tokens kept by H2O) / total mass
  sliding_mass_retained  : sum(attention mass of tokens kept by sliding-window-only) / total mass
  full_mass_retained     : 1.0 (oracle — every token retained, by definition)
  h2o_vs_sliding_gain    : h2o_mass_retained - sliding_mass_retained
  evicted_count          : seq_len - capacity (tokens evicted from the bounded caches)
  honest_note            : plain-language honesty disclaimer
  citations              : dict of citable sources
  computed_at            : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form re-implementation of the H2O
  heavy-hitter-retention RULE (keep top-K cumulative-score tokens + a recent
  window) applied to a synthetic per-token attention-mass trace drawn from the
  pure-stdlib LCG PRNG below (no numpy, no stdlib `random`, no proprietary
  weights, no real transformer, no real KV cache). It is NOT a production
  inference engine, NOT a run of any specific model's attention pattern, and is
  NEVER-CLAIMED-AS a production inference engine. The label "MODELED" is
  returned verbatim and displayed verbatim by the surface; never upgraded
  client-side.

CITATIONS (clean-room; none claimed as SZL's own; VERIFY real):
  H2O — Heavy-Hitter Oracle KV-cache eviction (policy modeled here):
    Zhang, Sheng, Zhou, Chen, Zheng, Cai, Song, Tian, Ré, Barrett, Wang & Chen
    (2023) "H2O: Heavy-Hitter Oracle for Efficient Generative Inference of
    Large Language Models". arXiv:2306.14048. https://arxiv.org/abs/2306.14048
  StreamingLLM — recency-window attention sink observation (reference/comparison
  baseline for the sliding-window-only policy simulated here):
    Xiao, Tian, Chen, Han & Lewis (2023) "Efficient Streaming Language Models
    with Attention Sinks". arXiv:2309.17453. https://arxiv.org/abs/2309.17453
  NEVER-CLAIMED-AS: this module is not H2O's or StreamingLLM's released code,
  does not reproduce either project's measured benchmark numbers, and runs no
  real model. It is a clean-room MODELED simulation of the shared
  heavy-hitter-vs-recency eviction arithmetic those methods describe.

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
    "H2O (Heavy-Hitter Oracle) — Zhang et al. arXiv:2306.14048": "https://arxiv.org/abs/2306.14048",
    "StreamingLLM — Xiao et al. arXiv:2309.17453": "https://arxiv.org/abs/2309.17453",
}

# Cap on how many per-token trace samples we echo back for the surface's
# token-row animation (keeps payload bounded for large `seq_len`).
_MAX_TOKEN_SAMPLES = 512


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
# MODELED synthetic attention-mass trace + H2O / sliding-window / full-cache
# eviction simulation (deterministic).
# ---------------------------------------------------------------------------
def _synthetic_attention_trace(rng, seq_len: int):
    """Draw a deterministic per-token cumulative-attention-mass trace.

    Each decoded token i receives a synthetic instantaneous attention-mass draw
    in (0, 1) from the LCG; a small fraction of tokens are boosted to emulate
    the empirically-observed "heavy hitter" phenomenon (a few tokens accumulate
    disproportionate cumulative attention over a long generation), matching the
    qualitative premise H2O exploits. Returns a list of per-token mass floats,
    length seq_len (index 0 = earliest token, index seq_len-1 = most recent).
    """
    mass = []
    for _ in range(seq_len):
        base = 0.02 + 0.10 * next(rng)          # ordinary token: small mass
        heavy_draw = next(rng)
        is_heavy = heavy_draw > 0.88              # ~12% of tokens are heavy hitters
        if is_heavy:
            base += 0.55 * next(rng)              # heavy hitters get a large boost
        mass.append(base)
    return mass


def _h2o_kept_indices(mass, capacity: int, window: int):
    """H2O policy: keep the most recent `window` tokens (always retained,
    regardless of score) plus the top-(capacity - window) REMAINING tokens by
    cumulative attention-mass score (the heavy hitters). Returns a set of kept
    token indices. Mirrors Zhang et al. (2023)'s combined heavy-hitter +
    recency retention rule."""
    n = len(mass)
    window = max(0, min(window, capacity, n))
    recent_start = max(0, n - window)
    kept = set(range(recent_start, n))            # sliding recency window
    budget = max(0, capacity - len(kept))
    if budget > 0:
        candidates = [i for i in range(n) if i not in kept]
        candidates.sort(key=lambda i: mass[i], reverse=True)
        for i in candidates[:budget]:
            kept.add(i)
    return kept


def _sliding_window_kept_indices(mass, capacity: int):
    """Naive recency-only baseline: keep ONLY the most recent `capacity`
    tokens, with no regard to cumulative attention-mass score. This is the
    ablation H2O (and StreamingLLM's local-attention-only variant) is compared
    against."""
    n = len(mass)
    cap = max(0, min(capacity, n))
    start = max(0, n - cap)
    return set(range(start, n))


def _mass_retained(mass, kept_indices) -> float:
    total = sum(mass)
    if total <= 0.0:
        return 0.0
    kept_mass = sum(mass[i] for i in kept_indices)
    return kept_mass / total


def _kvcache_snapshot(seed: int = 42, seq_len: int = 512, capacity: int = 128,
                       window: int = 32) -> dict:
    """
    Simulate a decoding stream of `seq_len` tokens against a KV cache limited
    to `capacity` slots, comparing H2O, sliding-window-only, and full-cache
    (oracle) retention of cumulative attention mass.

    Pure stdlib; deterministic — same (seed, seq_len, capacity, window) ->
    identical snapshot, every time.
    """
    rng = _lcg(seed)
    mass = _synthetic_attention_trace(rng, seq_len)

    capacity = max(1, min(capacity, seq_len))
    window = max(0, min(window, capacity))

    h2o_kept = _h2o_kept_indices(mass, capacity, window)
    sliding_kept = _sliding_window_kept_indices(mass, capacity)
    full_kept = set(range(seq_len))                # oracle: nothing evicted

    h2o_mass_retained = _mass_retained(mass, h2o_kept)
    sliding_mass_retained = _mass_retained(mass, sliding_kept)
    full_mass_retained = _mass_retained(mass, full_kept)   # == 1.0 by construction

    memory_ratio = capacity / max(seq_len, 1)
    h2o_vs_sliding_gain = h2o_mass_retained - sliding_mass_retained
    evicted_count = seq_len - capacity

    # Bounded per-token sample for the surface's 3D token-row animation:
    # mass, and which policies kept each token (evicted tokens fade+drop).
    sample_n = min(seq_len, _MAX_TOKEN_SAMPLES)
    per_token = [
        {
            "i": i,
            "mass": round(mass[i], 6),
            "h2o_kept": i in h2o_kept,
            "sliding_kept": i in sliding_kept,
        }
        for i in range(sample_n)
    ]

    return {
        "seq_len": seq_len,
        "capacity": capacity,
        "window": window,
        "memory_ratio": round(memory_ratio, 6),
        "h2o_mass_retained": round(h2o_mass_retained, 6),
        "sliding_mass_retained": round(sliding_mass_retained, 6),
        "full_mass_retained": round(full_mass_retained, 6),
        "h2o_vs_sliding_gain": round(h2o_vs_sliding_gain, 6),
        "evicted_count": evicted_count,
        "per_token": per_token,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_h2o_evict(req: Request):
    seed     = _ii(req, "seed",     42)
    seq_len  = max(1,  min(_ii(req, "seq_len",  512), 20000))
    capacity = max(1,  min(_ii(req, "capacity", 128), seq_len))
    window   = max(0,  min(_ii(req, "window",   32),  capacity))

    snap = _kvcache_snapshot(seed=seed, seq_len=seq_len, capacity=capacity, window=window)

    return JSONResponse({
        "label":     "MODELED",
        "model":     "KV-cache H2O (Heavy-Hitter Oracle) runtime eviction vs sliding-window-only vs full-cache oracle",
        "method":    "Zhang et al. (2023) H2O rule: keep top-(capacity-window) cumulative-attention-mass heavy hitters + most-recent `window` tokens; compared against a recency-only sliding-window baseline and the full-cache (no eviction) oracle",
        "seed":      seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "H2O (Heavy-Hitter Oracle) cumulative-attention-mass eviction RULE "
            "(Zhang et al. 2023, arXiv:2306.14048) applied to a SYNTHETIC per-token "
            "attention-mass trace drawn from a deterministic LCG PRNG (no numpy, no "
            "stdlib random, no proprietary weights, no real transformer, no real KV "
            "cache, no trained model). The sliding-window-only baseline reflects the "
            "recency-only ablation discussed alongside StreamingLLM (Xiao et al. 2023, "
            "arXiv:2309.17453). Deterministic: same seed/seq_len/capacity/window -> "
            "identical snapshot. NEVER-CLAIMED-AS a production inference engine. SZL "
            "claims NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_specdecode.register() / szl_testtime.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/kvcache/h2o-evict onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/kvcache"
    handlers = [
        (f"{base}/h2o-evict", _h_h2o_evict),
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
    snap = _kvcache_snapshot(seed=42, seq_len=512, capacity=128, window=32)
    print("label: MODELED")
    print("seq_len:", snap["seq_len"])
    print("capacity:", snap["capacity"])
    print("window:", snap["window"])
    print("memory_ratio:", snap["memory_ratio"])
    print("h2o_mass_retained:", snap["h2o_mass_retained"])
    print("sliding_mass_retained:", snap["sliding_mass_retained"])
    print("full_mass_retained:", snap["full_mass_retained"])
    print("h2o_vs_sliding_gain:", snap["h2o_vs_sliding_gain"])
    print("evicted_count:", snap["evicted_count"])
    print("sample per_token[:5]:", snap["per_token"][:5])

    # sanity: bounds
    assert 0.0 <= snap["h2o_mass_retained"] <= 1.0, "h2o_mass_retained out of [0,1]"
    assert 0.0 <= snap["sliding_mass_retained"] <= 1.0, "sliding_mass_retained out of [0,1]"
    assert snap["full_mass_retained"] == 1.0, "full_mass_retained (oracle) must be exactly 1.0"
    assert snap["capacity"] <= snap["seq_len"], "capacity must not exceed seq_len"
    assert snap["evicted_count"] == snap["seq_len"] - snap["capacity"], "evicted_count mismatch"

    # core claim: H2O beats sliding-window-only at the SAME memory budget.
    assert snap["h2o_mass_retained"] > snap["sliding_mass_retained"], (
        "H2O must retain more attention mass than sliding-window-only at equal capacity")
    assert snap["h2o_vs_sliding_gain"] > 0.0, "h2o_vs_sliding_gain must be positive"

    # H2O should approach (but not necessarily exceed) the full-cache oracle.
    assert snap["h2o_mass_retained"] <= snap["full_mass_retained"] + 1e-9, (
        "H2O cannot retain more mass than the full-cache oracle")

    # sanity: determinism — identical seed/seq_len/capacity/window -> identical snapshot
    snap2 = _kvcache_snapshot(seed=42, seq_len=512, capacity=128, window=32)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: a larger capacity (same seed) should not decrease retained mass
    # for either bounded policy, and evicted_count should shrink accordingly.
    snap3 = _kvcache_snapshot(seed=42, seq_len=512, capacity=256, window=32)
    assert snap3["h2o_mass_retained"] >= snap["h2o_mass_retained"] - 1e-9
    assert snap3["sliding_mass_retained"] >= snap["sliding_mass_retained"] - 1e-9
    assert snap3["evicted_count"] < snap["evicted_count"]

    print()
    print("szl_kvcache: ALL OK — H2O beats sliding-window-only, oracle bound respected, deterministic.")
