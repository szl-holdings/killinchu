# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_mor.py — ADDITIVE Mixture-of-Recursions (MoR) token-routing simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/mor.js).

Mixture-of-Recursions (Bae, Kim, Bayat, Kim, Ha, Schuster, Fisch, Harutyunyan, Ji, Courville, Yun
2025; arXiv:2507.10524) is a Recursive Transformer that reuses ONE shared stack of layers across
recursion steps (parameter efficiency) while a lightweight per-token ROUTER assigns each token a
recursion DEPTH (adaptive computation). Tokens that need more "thinking" recurse more times;
easy tokens exit early. Because attention at recursion depth r runs only over tokens still active
at depth r, and only their KV pairs are cached, MoR cuts both compute FLOPs and memory access
relative to running every token to full depth.

This module simulates the router + recursion budget deterministically (seeded, NO trained model):
each token gets a modeled "difficulty" score; the router assigns a recursion depth in [1, max_r]
by thresholding difficulty. It then measures the mean recursion depth, the FLOP fraction vs a
fixed-full-depth baseline (all tokens at max_r), and the KV-cache fraction saved by only caching
active tokens per depth.

Reported (field names read verbatim by mor.js):
  num_tokens           — N tokens routed
  max_recursion        — max recursion depth available
  mean_depth           — mean assigned recursion depth (MODELED)
  compute_fraction     — active-token FLOPs / full-depth FLOPs (MODELED)
  compute_saved_pct    — 1 - compute_fraction, as a percent
  kv_cache_fraction    — active-token KV entries / full-depth KV entries
  depth_histogram      — count of tokens per assigned depth

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic router + recursion-budget SIMULATION. NOT a trained MoR transformer
    running; NO shared layer stack, NO GPU, NO learned router weights. Token difficulty and the
    routing thresholds are SEEDED inputs / MODELED references, NOT measured on any real model.
  * "compute_saved_pct" is a property of the modeled routing on modeled difficulties, honestly
    labeled, not a perplexity/throughput claim about any real model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/mor/route — Mixture-of-Recursions token-routing snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "mor": ("Bae, Kim, Bayat, Kim, Ha, Schuster, Fisch, Harutyunyan, Ji, Courville, Yun (2025) "
            "Mixture-of-Recursions: Learning Dynamic Recursive Depths for Adaptive Token-Level "
            "Computation — arXiv:2507.10524 · https://arxiv.org/abs/2507.10524"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | MOR_ROUTING_SIM | NOT_LIVE | NO_MODEL | SAVINGS_ARE_MODELED"


# ---------------------------------------------------------------------------
# Deterministic LCG PRNG (no numpy, no stdlib random). Numerical Recipes params.
# ---------------------------------------------------------------------------
class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (seed ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def normal(self) -> float:
        u1 = max(1e-12, self.uniform())
        u2 = self.uniform()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + _math.exp(-x))
    z = _math.exp(x)
    return z / (1.0 + z)


def mor_route(seed: int = 42, num_tokens: int = 128, max_recursion: int = 4) -> dict:
    """Mixture-of-Recursions token-routing snapshot (MODELED).

    num_tokens    — N tokens to route.
    max_recursion — maximum recursion depth available (shared layer stack reused up to this many
                    times).
    seed          — RNG seed; identical inputs give identical output (deterministic).
    """
    N = max(1, min(8192, int(num_tokens)))
    R = max(1, min(16, int(max_recursion)))
    rng = _LCG(int(seed) * 1_000_003 + N * 131 + R * 17)

    depths = []
    histogram = {r: 0 for r in range(1, R + 1)}
    total_active = 0        # sum of recursion steps actually executed (active-token FLOP proxy)
    kv_active = 0           # KV entries cached (one per active token per depth)
    for _ in range(N):
        # Modeled token difficulty in [0,1]; router maps difficulty -> recursion depth.
        difficulty = _sigmoid(1.2 * rng.normal())
        depth = 1 + int(round(difficulty * (R - 1)))
        depth = max(1, min(R, depth))
        depths.append(depth)
        histogram[depth] += 1
        total_active += depth
        kv_active += depth      # token is cached at each depth it stays active

    mean_depth = sum(depths) / N
    # Full-depth baseline: every token recurses to max_recursion.
    full_flops = N * R
    full_kv = N * R
    compute_fraction = total_active / full_flops if full_flops else 0.0
    kv_cache_fraction = kv_active / full_kv if full_kv else 0.0
    compute_saved_pct = (1.0 - compute_fraction) * 100.0

    return {
        "service": "mixture-of-recursions-router",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/mor.js ---
        "num_tokens": int(N),
        "max_recursion": int(R),
        "mean_depth": round(float(mean_depth), 6),
        "compute_fraction": round(float(compute_fraction), 6),
        "compute_saved_pct": round(float(compute_saved_pct), 4),
        "kv_cache_fraction": round(float(kv_cache_fraction), 6),
        "depth_histogram": {str(k): int(v) for k, v in histogram.items()},
        "formulas": {
            "router": "depth_t = 1 + round(difficulty_t * (max_recursion - 1))  (per-token)",
            "compute_fraction": "sum(depth_t) / (N * max_recursion)  (active-token FLOP proxy)",
            "kv_cache_fraction": "active KV entries / (N * max_recursion)",
            "compute_saved_pct": "(1 - compute_fraction) * 100",
        },
        "compute_backend": {
            "backend": "CPU pure-Python per-token recursion-router simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic routing sim; NO trained MoR transformer, NO shared "
                            "layer stack, NO GPU, NO learned router. A trained model is ROADMAP."),
        },
        "honest_note": ("MODELED Mixture-of-Recursions routing. compute_saved_pct is a property of "
                        "the modeled router on modeled token difficulties, not a perplexity or "
                        "throughput claim about any real model."),
        "wired_into": "frontier ring — Mixture-of-Recursions token-routing surface",
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (advisory routing metrics — never autonomous)",
        "citations": {"mor": CITATIONS["mor"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/mor" % ns
    path = "%s/route" % base

    @app.get(path)
    async def _kc_mor(seed: int = 42, num_tokens: int = 128, max_recursion: int = 4):  # noqa: ANN202
        try:
            return JSONResponse(mor_route(seed=seed, num_tokens=num_tokens, max_recursion=max_recursion))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "mixture-of-recursions-router",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "mean_depth": None, "compute_saved_pct": None},
                                status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401 — Route fallback parity with template
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = mor_route(seed=42, num_tokens=128, max_recursion=4)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("num_tokens", "max_recursion"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("mean_depth", "compute_fraction", "compute_saved_pct", "kv_cache_fraction"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["depth_histogram"], dict) and r["depth_histogram"], r

    # bounds: mean depth within [1, max]; compute fraction in (0,1]; savings in [0,100).
    assert 1.0 <= r["mean_depth"] <= r["max_recursion"], r["mean_depth"]
    assert 0.0 < r["compute_fraction"] <= 1.0, r["compute_fraction"]
    assert 0.0 <= r["compute_saved_pct"] < 100.0, r["compute_saved_pct"]
    assert 0.0 < r["kv_cache_fraction"] <= 1.0, r["kv_cache_fraction"]
    assert sum(r["depth_histogram"].values()) == r["num_tokens"], r
    out["metrics"] = {"mean_depth": r["mean_depth"], "compute_fraction": r["compute_fraction"],
                      "compute_saved_pct": r["compute_saved_pct"],
                      "kv_cache_fraction": r["kv_cache_fraction"]}

    assert "2507.10524" in r["citations"]["mor"], r["citations"]

    # determinism
    r2 = mor_route(seed=42, num_tokens=128, max_recursion=4)
    assert r2["depth_histogram"] == r["depth_histogram"], "non-deterministic"
    assert r2["mean_depth"] == r["mean_depth"], "non-deterministic"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2))
    assert res["ok"] is True
    print("ALL OK", file=sys.stderr)
    print("ALL OK")
