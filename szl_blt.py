# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_blt.py — SZL Byte Latent Transformer (BLT) entropy-patching endpoint
(Meta FAIR tokenizer-free dynamic byte-patching idea), MODELED.

Exposes a MODELED, deterministic, pure-stdlib simulation of the *dynamic
entropy-patching* idea at the heart of Meta FAIR's Byte Latent Transformer
(BLT) as a same-origin REST endpoint, so the BLT surface organ has a live
data source that is honest, deterministic, and citable — never fabricated,
never claimed as a run of the real trained BLT entropy model.

  GET  /api/<ns>/v1/blt/entropy-patch?seed=&text=&threshold=

WHAT IS SIMULATED
------------------
BLT (Pagnoni, Pasunuru, Rodriguez et al. 2024, Meta FAIR) replaces
fixed-vocabulary tokenization with *dynamic, learned byte-patching*: bytes
are grouped into variable-length patches whose boundaries are placed where
the entropy of the next-byte prediction spikes (i.e. where the sequence is
"surprising" / hard to predict). Predictable spans (low next-byte entropy)
are folded into long patches — spending little compute per byte — while
unpredictable spans (high next-byte entropy) get short patches — spending
more compute per byte, exactly where it is needed. This module does NOT run
BLT's learned entropy model (a small trained transformer in the real paper).
Instead it builds a fully deterministic, closed-form STAND-IN entropy signal
directly from the input text itself:

  1. Build an ORDER-2 MARKOV byte model: for every byte trigram (b[i-2],
     b[i-1]) -> b[i] observed in the input text, count occurrences.
  2. For every position i (i>=2), compute the Shannon entropy, in bits, of
     the conditional next-byte distribution P(b[i] | b[i-2], b[i-1]) as
     estimated by those trigram counts:
         H(i) = - sum_v P(v) * log2(P(v))   over observed next-byte values v
     following the given 2-byte context. Positions with only one possible
     continuation in the training-by-itself model have H = 0 bits (fully
     predictable); positions where the same 2-byte context was followed by
     many different bytes elsewhere in the text have higher H (surprising).
  3. Walk the entropy series left to right; place a PATCH BOUNDARY
     immediately after byte i whenever H(i) > threshold (a local entropy
     spike = high surprise = a natural place to start a new patch, per the
     BLT entropy-patching heuristic). This yields variable-length patches:
     long runs of low-entropy (predictable) bytes collapse into a single
     big patch; high-entropy spans fragment into many small patches.
  4. Report compute_savings_ratio = num_bytes / num_patches — a MODELED
     proxy for the BLT claim that patches (not bytes) are the primary unit
     of compute, so fewer/larger patches on predictable spans means less
     compute spent per byte of input (BLT report up to ~50% FLOP savings at
     inference vs. token-based models at matched quality; this ratio is a
     clean-room proxy for that intuition, NOT a reproduction of their
     measured number).

This module trains its own tiny entropy model FROM THE SAME TEXT it
patches (a self-referential, in-context statistic) purely so the endpoint
is deterministic and dependency-free (no corpus, no numpy, no network, no
trained weights) — it is explicitly NOT the trained cross-entropy/next-byte
model BLT actually uses (which is trained on a large byte corpus, held
separate from the sequence being patched). See HONEST STATUS below.

Returned JSON fields
---------------------
  label                  : "MODELED" (always)
  model                  : short description of the simulated setup
  seed                   : RNG seed (reserved; entropy model is
                            deterministically derived from `text`, not from
                            the seed — seed is accepted for API convention
                            and future stochastic-tie-break use, but the
                            core algorithm below is already fully
                            deterministic given `text` and `threshold`)
  threshold              : entropy threshold in bits used for patch cuts
  text_len               : length of the input text in BYTES (UTF-8)
  num_patches            : number of variable-length patches produced
  avg_patch_len          : text_len / num_patches
  patch_boundaries       : sorted list of byte indices where a new patch
                            begins (0 always included)
  entropy_series         : sampled (byte_index, entropy_bits) pairs — the
                            per-position next-byte Shannon entropy, capped
                            to a bounded sample count for payload size
  compute_savings_ratio  : text_len / num_patches (>1 whenever patches are,
                            on average, longer than 1 byte)
  honest_note            : plain-language honesty disclaimer
  citations              : dict of citable sources
  computed_at            : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib, order-2 Markov byte-entropy
  re-implementation of the *dynamic entropy-patching heuristic* described
  in the BLT paper (place a patch boundary at a next-byte entropy spike).
  It is NOT the trained BLT entropy model, uses NO Meta FAIR weights, runs
  NO real BLT encoder/decoder/global-transformer, and is NEVER-CLAIMED-AS
  Meta FAIR BLT. The entropy model here is fit on-the-fly from trigram
  counts of the very text being patched (a simple, fully transparent,
  reproducible statistic) — the real BLT trains a small byte-level
  transformer on a large external corpus to predict next-byte entropy
  in-context. The label "MODELED" is returned verbatim and displayed
  verbatim by the surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Byte Latent Transformer (entropy-patching idea simulated here):
    Pagnoni, Pasunuru, Rodriguez, Nguyen, Muller, Li, Zhou, Yu, Weston,
    Zettlemoyer, Ghosh, Lewis, Holtzman & Iyer (2024), Meta FAIR,
    "Byte Latent Transformer: Patches Scale Better Than Tokens".
    arXiv:2412.09871. https://arxiv.org/abs/2412.09871
  Reference implementation (reference only; NOT executed here):
    Meta FAIR, github.com/facebookresearch/blt.
    https://github.com/facebookresearch/blt
  NEVER-CLAIMED-AS: this module is not BLT, does not reproduce BLT's
  trained entropy model, code, weights, or measured benchmark numbers. It
  is a clean-room MODELED simulation of the shared entropy-spike
  dynamic-patching idea BLT is built on.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (math/collections only). Deterministic
  given (text, threshold). 0 runtime CDN.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "Byte Latent Transformer — Pagnoni et al. (Meta FAIR) arXiv:2412.09871": "https://arxiv.org/abs/2412.09871",
    "BLT reference implementation — github.com/facebookresearch/blt": "https://github.com/facebookresearch/blt",
}

# Cap on how many (byte_index, entropy_bits) samples we echo back for the
# surface's ribbon animation (keeps payload bounded for large `text`).
_MAX_ENTROPY_SAMPLES = 512

# Built-in sample text used when `text` query param is absent — deliberately
# mixes a long predictable run ("aaaa...") with a higher-entropy, more
# "surprising" span so the demo shows both big and small patches.
_SAMPLE_TEXT = (
    "the quick brown fox jumps over the lazy dog. "
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
    "byte latent transformers patch bytes not tokens, dynamically, "
    "entropy spikes 7g#Q9!zK&3xM@2pL^7vB signal surprising regions "
    "while predictable spans like the repeated letters above collapse "
    "into one large patch, saving compute exactly where prediction "
    "is easy and spending it exactly where prediction is hard."
)


# ---------------------------------------------------------------------------
# Order-2 Markov byte-entropy model (pure stdlib: math + collections only)
# ---------------------------------------------------------------------------
def _build_trigram_counts(data: bytes) -> dict:
    """Count byte trigrams: for every position i>=2, context (b[i-2], b[i-1])
    -> Counter of observed b[i] values. Pure stdlib, O(n)."""
    counts: dict = defaultdict(lambda: defaultdict(int))
    n = len(data)
    for i in range(2, n):
        ctx = (data[i - 2], data[i - 1])
        counts[ctx][data[i]] += 1
    return counts


def _shannon_entropy_bits(dist: dict) -> float:
    """Shannon entropy in bits of a discrete distribution given as raw
    counts (dict value -> count). H = -sum p*log2(p)."""
    total = sum(dist.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for c in dist.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return h


def _entropy_series(data: bytes) -> list:
    """Per-position next-byte Shannon entropy (bits), for i in [2, n).
    Position i's entropy is computed from the GLOBAL trigram-count table
    built over the whole text (order-2 Markov model trained on the text
    itself), so repeated contexts elsewhere in the text inform the entropy
    at each occurrence — deterministic, pure stdlib."""
    counts = _build_trigram_counts(data)
    series = []
    n = len(data)
    for i in range(2, n):
        ctx = (data[i - 2], data[i - 1])
        h = _shannon_entropy_bits(counts[ctx])
        series.append(h)
    return series


def _patch_boundaries(series: list, threshold: float, text_len: int) -> list:
    """Walk the entropy series; place a boundary at byte index (i+2)
    whenever H(i) > threshold (entropy spike = high surprise = new patch).
    Index 0 is always a boundary (the start of the first patch). Series
    index j corresponds to byte index (j+2) because entropy is only
    defined for i>=2 (order-2 context needs 2 preceding bytes)."""
    boundaries = [0]
    for j, h in enumerate(series):
        if h > threshold:
            byte_idx = j + 2
            if byte_idx < text_len:
                boundaries.append(byte_idx)
    # de-dup + sort (monotonic by construction, but guard anyway)
    return sorted(set(boundaries))


def _patch_lengths(boundaries: list, text_len: int) -> list:
    lengths = []
    for k in range(len(boundaries)):
        start = boundaries[k]
        end = boundaries[k + 1] if k + 1 < len(boundaries) else text_len
        lengths.append(max(0, end - start))
    return lengths


def _blt_snapshot(text: str, threshold: float = 2.5) -> dict:
    """
    Run the order-2 Markov byte-entropy dynamic-patching simulation over
    `text`, cutting a new patch boundary wherever next-byte Shannon entropy
    exceeds `threshold` bits.

    Pure stdlib; deterministic — same (text, threshold) -> identical
    snapshot, every time.
    """
    data = text.encode("utf-8", errors="replace")
    text_len = len(data)

    if text_len < 3:
        # Degenerate short input: no order-2 context possible; the whole
        # thing is one patch.
        return {
            "text_len": text_len,
            "threshold": round(threshold, 6),
            "num_patches": 1 if text_len > 0 else 0,
            "avg_patch_len": float(text_len),
            "patch_boundaries": [0] if text_len > 0 else [],
            "entropy_series": [],
            "compute_savings_ratio": float(text_len) if text_len > 0 else 0.0,
        }

    series = _entropy_series(data)
    boundaries = _patch_boundaries(series, threshold, text_len)
    lengths = _patch_lengths(boundaries, text_len)
    num_patches = len(boundaries)
    avg_patch_len = text_len / max(num_patches, 1)
    compute_savings_ratio = text_len / max(num_patches, 1)

    # Sample the entropy series (index offset by 2 to map back to byte
    # index) down to a bounded number of points for the ribbon animation.
    n_series = len(series)
    if n_series <= _MAX_ENTROPY_SAMPLES:
        sample_idx = range(n_series)
    else:
        step = n_series / _MAX_ENTROPY_SAMPLES
        sample_idx = [int(k * step) for k in range(_MAX_ENTROPY_SAMPLES)]
    entropy_sample = [[j + 2, round(series[j], 6)] for j in sample_idx]

    return {
        "text_len": text_len,
        "threshold": round(threshold, 6),
        "num_patches": num_patches,
        "avg_patch_len": round(avg_patch_len, 6),
        "patch_boundaries": boundaries,
        "entropy_series": entropy_sample,
        "compute_savings_ratio": round(compute_savings_ratio, 6),
        "_patch_lengths_sample": lengths[:_MAX_ENTROPY_SAMPLES],
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


def _h_entropy_patch(req: Request):
    seed = _ii(req, "seed", 42)
    text = req.query_params.get("text", None)
    if not text:
        text = _SAMPLE_TEXT
    # cap absurdly large inputs to keep the endpoint fast/bounded
    text = text[:20000]
    threshold = _ff(req, "threshold", 2.5)
    threshold = max(0.0, min(threshold, 16.0))

    snap = _blt_snapshot(text=text, threshold=threshold)

    return JSONResponse({
        "label": "MODELED",
        "model": "Tokenizer-free dynamic byte-patching driven by an order-2 Markov byte-entropy model (BLT entropy-patching idea)",
        "method": (
            "Order-2 Markov byte trigram counts -> per-position next-byte Shannon entropy "
            "H(i) in bits -> patch boundary placed wherever H(i) > threshold (entropy spike). "
            "compute_savings_ratio = text_len / num_patches."
        ),
        "seed": seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib order-2 Markov byte-entropy "
            "simulation of the Byte Latent Transformer (BLT) dynamic-patching IDEA "
            "(Pagnoni et al. 2024, Meta FAIR, arXiv:2412.09871) — NOT a run of the trained "
            "BLT entropy model, NOT github.com/facebookresearch/blt executed, uses NO Meta "
            "FAIR weights, and is NEVER-CLAIMED-AS Meta FAIR BLT. The entropy signal here is "
            "fit on-the-fly from trigram counts of the very text being patched (fully "
            "transparent, reproducible, dependency-free), whereas the real BLT trains a "
            "small byte-level transformer on a large external corpus to predict next-byte "
            "entropy in-context. Deterministic: same text/threshold -> identical snapshot. "
            "SZL claims NONE of these methods as its own."
        ),
        "citations": CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_specdecode.register() / szl_interpretability.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/blt/entropy-patch onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/blt"
    handlers = [
        (f"{base}/entropy-patch", _h_entropy_patch),
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
    snap = _blt_snapshot(text=_SAMPLE_TEXT, threshold=2.5)
    print("label: MODELED")
    print("text_len:", snap["text_len"])
    print("threshold:", snap["threshold"])
    print("num_patches:", snap["num_patches"])
    print("avg_patch_len:", snap["avg_patch_len"])
    print("compute_savings_ratio:", snap["compute_savings_ratio"])
    print("patch_boundaries[:10]:", snap["patch_boundaries"][:10])
    print("entropy_series[:10]:", snap["entropy_series"][:10])

    # sanity: bounds
    assert snap["text_len"] > 0, "text_len must be > 0"
    assert 0 < snap["num_patches"] < snap["text_len"], "num_patches must be in (0, text_len)"
    assert snap["compute_savings_ratio"] > 1.0, "compute_savings_ratio must be > 1.0 for this sample"
    assert snap["avg_patch_len"] == snap["compute_savings_ratio"], "avg_patch_len must equal compute_savings_ratio by definition"
    assert snap["patch_boundaries"][0] == 0, "first boundary must be byte index 0"
    assert snap["patch_boundaries"] == sorted(snap["patch_boundaries"]), "boundaries must be sorted"
    assert len(set(snap["patch_boundaries"])) == len(snap["patch_boundaries"]), "boundaries must be unique"
    for h_pair in snap["entropy_series"]:
        assert h_pair[1] >= 0.0, "entropy must be non-negative"

    # sanity: determinism — identical text/threshold -> identical snapshot
    snap2 = _blt_snapshot(text=_SAMPLE_TEXT, threshold=2.5)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: raising threshold should never INCREASE num_patches (fewer or
    # equal entropy spikes clear a higher bar)
    snap3 = _blt_snapshot(text=_SAMPLE_TEXT, threshold=5.0)
    assert snap3["num_patches"] <= snap["num_patches"], "higher threshold must not increase num_patches"
    assert snap3["compute_savings_ratio"] >= snap["compute_savings_ratio"], "higher threshold must not decrease compute_savings_ratio"

    # sanity: lower threshold should never DECREASE num_patches
    snap4 = _blt_snapshot(text=_SAMPLE_TEXT, threshold=0.5)
    assert snap4["num_patches"] >= snap["num_patches"], "lower threshold must not decrease num_patches"

    # sanity: degenerate very-short text still returns a sane single patch
    snap5 = _blt_snapshot(text="ab", threshold=2.5)
    assert snap5["num_patches"] == 1 and snap5["text_len"] == 2

    print()
    print("szl_blt: ALL OK — deterministic, num_patches < text_len, compute_savings_ratio > 1, bounds respected.")
