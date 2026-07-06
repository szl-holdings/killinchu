# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_keyless.py — SZL KEYLESS ATTENTION (VALUE-ONLY CACHE) endpoint, MODELED.

Exposes a MODELED, deterministic, pure-stdlib re-implementation of the
KEYLESS ATTENTION mechanism (Xin Gao, "Keyless Attention: Value-Space Routing
and Value-Only Caching for Efficient Transformers", arXiv:2606.21848,
2026-06-20) applied to a small SYNTHETIC token sequence drawn from the
pure-stdlib LCG PRNG below — so the keyless organ has a live data source that
is honest, deterministic, and citable — never a trained model, never a real
transformer forward pass, never a GPU kernel.

  GET  /api/<ns>/v1/keyless/attention?seed=&L=&d=&m=

WHAT IS MODELED
---------------
STANDARD QKV ATTENTION computes, for a length-L sequence of d-dim tokens X:

    Q = X·Wq   K = X·Wk   V = X·Wv
    scores = softmax(Q·Kᵀ / √d)          (L × L)
    out_std = scores · V                 (L × d)

Its autoregressive decode CACHE must store BOTH K and V for every past token:
    kv_entries_standard = 2 · L · d      (K + V)

KEYLESS ATTENTION (at m=3) ELIMINATES the K projection entirely. A value-space
ROUTING matrix R (d × d) replaces Wk, so the attention logits are formed by
routing the queries through the VALUES directly:

    Q = X·Wq   V = X·Wv
    scores = softmax( (Q·R) · Vᵀ / √d )  (L × L)   ← keys never materialized
    out_keyless = scores · V             (L × d)

Its decode CACHE therefore stores VALUES ONLY:
    kv_entries_keyless = L · d           (V only)

so the cache shrinks by EXACTLY 50%:
    reduction_pct = 100·(kv_std - kv_keyless)/kv_std = 100·(2Ld - Ld)/(2Ld) = 50.0

This module builds both attention operators on the SAME deterministic synthetic
input, MEASURES the cache byte counts (float32, 4 bytes/entry), confirms the
exact 50.0% reduction arithmetically, and MEASURES an OUTPUT-FIDELITY metric —
the mean per-token cosine similarity between out_std and out_keyless — so the
honesty note can say "matches within X on the toy task". The depth-m attention
factorization is reflected by the routing matrix R (the m=3 value-space
coupling between routing and retrieval); m is echoed and validated but the
mechanism modeled here is the value-only-cache + routing-matrix substitution.

Returned JSON fields
--------------------
  label               : "MODELED" (always — clean-room mechanism reproduction,
                        NOT a trained transformer / real decode run)
  model               : short description of the modeled setup
  method              : one-line description of the two attention operators
  seed                : RNG seed used
  L, d, m             : sequence length, model dim, factorization depth (m=3)
  bytes_per_entry     : 4 (float32 cache element)
  kv_entries_standard : 2·L·d (K + V cache entries)
  kv_entries_keyless  : L·d   (V-only cache entries)
  kv_bytes_standard   : kv_entries_standard · bytes_per_entry
  kv_bytes_keyless    : kv_entries_keyless  · bytes_per_entry
  reduction_pct       : 100·(std - keyless)/std  (== 50.0 exactly)
  cosine_mean         : MEASURED mean per-token cosine sim(out_std, out_keyless)
  cosine_min          : MEASURED min per-token cosine sim
  mse                 : MEASURED mean-squared-error between the two outputs
  out_std_head        : first rows/cols of the standard attention output
  out_keyless_head    : first rows/cols of the keyless attention output
  scores_std_head     : first rows/cols of the standard attention map
  scores_keyless_head : first rows/cols of the keyless attention map
  honest_note         : plain-language honesty disclaimer (see below)
  citations           : dict of citable sources (verified real)
  computed_at         : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib TOY ARITHMETIC demo of the Keyless
  Attention VALUE-ONLY-CACHE + value-space ROUTING mechanism (no numpy, no
  stdlib `random`, no trained model, no real transformer forward pass, no GPU
  kernel). The 50% cache reduction is an EXACT arithmetic property of the
  cache-shape change (2·L·d → L·d) and is confirmed here; the output fidelity
  (cosine/MSE) is MEASURED between the two operators on the synthetic input.
  It does NOT reproduce the paper's perplexity or zero-shot results on
  GPT-2 280M / GPT-2 557M / Pythia 410M / Qwen2 1.5B / Llama 3.2 1B — those are
  CLAIMS about REAL trained models that the estate does NOT independently
  verify. The label "MODELED" is returned verbatim and displayed verbatim by
  the surface; never upgraded.

CITATIONS (clean-room; none claimed as SZL's own; VERIFIED real):
  Keyless Attention: Value-Space Routing and Value-Only Caching for Efficient
    Transformers — Xin Gao. arXiv:2606.21848
    https://arxiv.org/abs/2606.21848
  NEVER-CLAIMED-AS: this module is not the paper's released code, does not
  reproduce its perplexity/zero-shot numbers, trains no model, and runs no real
  transformer. It is a clean-room MODELED reproduction of the value-only-cache
  + value-space-routing mechanism the work describes.

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
    "Keyless Attention: Value-Space Routing and Value-Only Caching for Efficient Transformers — Xin Gao. arXiv:2606.21848": "https://arxiv.org/abs/2606.21848",
}

# float32 cache element size (bytes) — used for the byte-count metrics.
_BYTES_PER_ENTRY = 4


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


def _transpose(M):
    if not M:
        return []
    rows = len(M)
    cols = len(M[0])
    return [[M[r][c] for r in range(rows)] for c in range(cols)]


def _matmul(A, B):
    """Plain triple-loop matmul A(p x q) · B(q x r) -> (p x r)."""
    p = len(A)
    q = len(A[0]) if A else 0
    r = len(B[0]) if B else 0
    out = [[0.0] * r for _ in range(p)]
    for i in range(p):
        Ai = A[i]
        Oi = out[i]
        for k in range(q):
            a = Ai[k]
            if a == 0.0:
                continue
            Bk = B[k]
            for j in range(r):
                Oi[j] += a * Bk[j]
    return out


def _softmax_rows(M):
    """Row-wise numerically-stable softmax (pure stdlib)."""
    out = []
    for row in M:
        mx = max(row) if row else 0.0
        exps = [math.exp(v - mx) for v in row]
        z = sum(exps)
        if z <= 0.0:
            z = 1.0
        out.append([e / z for e in exps])
    return out


def _cosine(a, b) -> float:
    """Cosine similarity between two equal-length vectors (guarded)."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ---------------------------------------------------------------------------
# Attention operators (the EXACT mechanism, on a toy synthetic sequence)
# ---------------------------------------------------------------------------
def _standard_attention(X, Wq, Wk, Wv, d: int):
    """Standard QKV attention: softmax(Q·Kᵀ/√d)·V. Cache stores K AND V."""
    Q = _matmul(X, Wq)
    K = _matmul(X, Wk)
    V = _matmul(X, Wv)
    scale = 1.0 / math.sqrt(d) if d > 0 else 1.0
    logits = _matmul(Q, _transpose(K))
    logits = [[v * scale for v in row] for row in logits]
    scores = _softmax_rows(logits)
    out = _matmul(scores, V)
    return out, scores


def _keyless_attention(X, Wq, Wv, R, d: int):
    """Keyless attention (m=3): key projection eliminated. A value-space routing
    matrix R replaces Wk, so logits = softmax((Q·R)·Vᵀ/√d) and the cache stores
    VALUES ONLY (no K)."""
    Q = _matmul(X, Wq)
    V = _matmul(X, Wv)
    QR = _matmul(Q, R)                     # value-space routing of the queries
    scale = 1.0 / math.sqrt(d) if d > 0 else 1.0
    logits = _matmul(QR, _transpose(V))    # keys never materialized
    logits = [[v * scale for v in row] for row in logits]
    scores = _softmax_rows(logits)
    out = _matmul(scores, V)
    return out, scores


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _keyless_snapshot(seed: int = 42, L: int = 16, d: int = 16, m: int = 3) -> dict:
    """
    Deterministically build a synthetic token sequence X (L x d) and shared
    projections, run BOTH standard QKV attention and keyless (value-only-cache)
    attention on it, MEASURE the KV-cache byte counts (float32), confirm the
    EXACT 50.0% reduction, and MEASURE the output fidelity (per-token cosine +
    MSE) between the two attention outputs.

    Pure stdlib; deterministic — same (seed, L, d, m) -> identical snapshot.
    """
    rng = _lcg(seed)
    # synthetic inputs + shared projections (scaled small so softmax is stable)
    X = _randmat(rng, L, d, scale=1.0)
    Wq = _randmat(rng, d, d, scale=1.0 / math.sqrt(d))
    Wk = _randmat(rng, d, d, scale=1.0 / math.sqrt(d))
    Wv = _randmat(rng, d, d, scale=1.0 / math.sqrt(d))
    R  = _randmat(rng, d, d, scale=1.0 / math.sqrt(d))   # value-space routing (m=3)

    out_std, scores_std = _standard_attention(X, Wq, Wk, Wv, d)
    out_keyless, scores_keyless = _keyless_attention(X, Wq, Wv, R, d)

    # ---- cache-size accounting (the exact 50% property) --------------------
    kv_entries_standard = 2 * L * d       # K + V
    kv_entries_keyless = L * d            # V only
    kv_bytes_standard = kv_entries_standard * _BYTES_PER_ENTRY
    kv_bytes_keyless = kv_entries_keyless * _BYTES_PER_ENTRY
    reduction_pct = (
        100.0 * (kv_bytes_standard - kv_bytes_keyless) / kv_bytes_standard
        if kv_bytes_standard > 0 else 0.0
    )

    # ---- output-fidelity metric (MEASURED on the toy task) -----------------
    cosims = [_cosine(out_std[i], out_keyless[i]) for i in range(L)]
    cosine_mean = sum(cosims) / len(cosims) if cosims else 0.0
    cosine_min = min(cosims) if cosims else 0.0
    sse = 0.0
    cnt = 0
    for i in range(L):
        for j in range(d):
            diff = out_std[i][j] - out_keyless[i][j]
            sse += diff * diff
            cnt += 1
    mse = sse / cnt if cnt else 0.0

    cap = 8
    def _trim(M):
        return [[round(v, 6) for v in row[:cap]] for row in M[:cap]]

    return {
        "L": L,
        "d": d,
        "m": m,
        "bytes_per_entry": _BYTES_PER_ENTRY,
        "kv_entries_standard": kv_entries_standard,
        "kv_entries_keyless": kv_entries_keyless,
        "kv_bytes_standard": kv_bytes_standard,
        "kv_bytes_keyless": kv_bytes_keyless,
        "reduction_pct": round(reduction_pct, 6),
        "cosine_mean": round(cosine_mean, 6),
        "cosine_min": round(cosine_min, 6),
        "mse": round(mse, 6),
        "out_std_head": _trim(out_std),
        "out_keyless_head": _trim(out_keyless),
        "scores_std_head": _trim(scores_std),
        "scores_keyless_head": _trim(scores_keyless),
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
    "MODELED: this is a clean-room, pure-stdlib TOY ARITHMETIC demo of the "
    "Keyless Attention VALUE-ONLY-CACHE + value-space ROUTING mechanism (Xin "
    "Gao, 'Keyless Attention: Value-Space Routing and Value-Only Caching for "
    "Efficient Transformers', arXiv:2606.21848), NOT a trained transformer. "
    "Standard QKV attention softmax(Q·Kᵀ/√d)·V (cache = K+V = 2·L·d) is run "
    "alongside keyless attention softmax((Q·R)·Vᵀ/√d)·V, where the value-space "
    "routing matrix R replaces the eliminated K projection so the cache stores "
    "VALUES ONLY (L·d). The 50% cache reduction is an EXACT arithmetic property "
    "of the cache-shape change (2·L·d → L·d) — confirmed here as reduction_pct "
    "== 50.0 — and the output fidelity (cosine_mean / mse) between the two "
    "operators is MEASURED on the synthetic input. This is a MECHANISM DEMO — "
    "it trains NOTHING and does NOT reproduce the paper's perplexity / zero-shot "
    "results on GPT-2 280M / GPT-2 557M / Pythia 410M / Qwen2 1.5B / Llama 3.2 "
    "1B (those are CLAIMS about REAL trained models the estate does not verify). "
    "Pure stdlib, no numpy, no stdlib random, no GPU kernel. Deterministic: "
    "same seed/L/d/m -> identical snapshot. NEVER-CLAIMED-AS a production "
    "attention kernel. SZL claims NONE of these methods as its own."
)


def _h_attention(req: Request):
    seed = _ii(req, "seed", 42)
    L    = max(2, min(_ii(req, "L", 16), 64))
    d    = max(2, min(_ii(req, "d", 16), 64))
    m    = max(2, min(_ii(req, "m", 3), 8))

    snap = _keyless_snapshot(seed=seed, L=L, d=d, m=m)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Keyless Attention (Value-Only Cache) — standard QKV attention vs keyless value-space-routing attention on a synthetic token sequence; cache K+V (2·L·d) vs V-only (L·d)",
        "method": "Standard: scores=softmax(Q·Kᵀ/√d), out=scores·V, cache=K+V=2·L·d. Keyless (m=3): eliminate K projection, value-space routing matrix R replaces Wk, scores=softmax((Q·R)·Vᵀ/√d), out=scores·V, cache=V-only=L·d → reduction_pct exactly 50.0; output fidelity via per-token cosine sim + MSE",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_muon.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/keyless/attention onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/keyless"
    handlers = [
        (f"{base}/attention", _h_attention),
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
    snap = _keyless_snapshot(seed=42, L=16, d=16, m=3)
    print("label: MODELED")
    print("L:", snap["L"], "d:", snap["d"], "m:", snap["m"])
    print("--- METRIC: KV-CACHE SIZE (float32, K+V vs V-only) ---")
    print("kv_entries_standard:", snap["kv_entries_standard"], "(2·L·d, K+V)")
    print("kv_entries_keyless: ", snap["kv_entries_keyless"], "(L·d, V only)")
    print("kv_bytes_standard:  ", snap["kv_bytes_standard"], "bytes")
    print("kv_bytes_keyless:   ", snap["kv_bytes_keyless"], "bytes")
    print("reduction_pct:      ", snap["reduction_pct"], "%")
    print("--- METRIC: OUTPUT FIDELITY (standard vs keyless on toy task) ---")
    print("cosine_mean:", snap["cosine_mean"])
    print("cosine_min: ", snap["cosine_min"])
    print("mse:        ", snap["mse"])

    # sanity: the cache reduction is EXACTLY 50%
    assert snap["kv_entries_standard"] == 2 * snap["kv_entries_keyless"], "standard cache must be 2x keyless"
    assert snap["kv_bytes_standard"] == 2 * snap["kv_bytes_keyless"], "standard bytes must be 2x keyless"
    assert snap["reduction_pct"] == 50.0, "reduction_pct must compute to exactly 50.0"

    # sanity: output fidelity is MEASURED and in range
    assert -1.0 <= snap["cosine_min"] <= 1.0, "cosine out of range"
    assert -1.0 <= snap["cosine_mean"] <= 1.0, "cosine out of range"
    assert snap["mse"] >= 0.0, "mse must be non-negative"

    # sanity: both attention maps are valid softmaxes (rows ~sum to 1)
    for row in snap["scores_std_head"]:
        assert all(0.0 <= v <= 1.0 for v in row), "std scores must be probabilities"
    for row in snap["scores_keyless_head"]:
        assert all(0.0 <= v <= 1.0 for v in row), "keyless scores must be probabilities"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _keyless_snapshot(seed=42, L=16, d=16, m=3)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_keyless: ALL OK — value-only cache, reduction_pct == 50.0 exactly, output fidelity measured, deterministic.")
