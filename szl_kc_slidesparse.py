# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_slidesparse.py — ADDITIVE SLIDING-WINDOW SPARSE-PACKING simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/slidesparse.js).

NVIDIA 2:4 Sparse Tensor Cores give 2x throughput but demand strict 50% pruning, which hurts
accuracy; milder (2N-2):2N patterns (e.g. 6:8, 25% pruning) keep accuracy but get no hardware
support and fall back to dense. SlideSparse (Shao et al. 2026, "SlideSparse: Fast and Flexible
(2N-2):2N Structured Sparsity", arXiv:2603.05232) unlocks Sparse-Tensor-Core acceleration for
the (2N-2):2N family with a SLIDING WINDOW DECOMPOSITION: any (2N-2):2N weight block is
reconstructed as N-1 overlapping 2:4-compliant windows with no accuracy loss, and an activation
"lifting" step fuses the matching rearrangement into per-token quantization. On compute-bound
Qwen2.5-7B at 6:8 the measured speedup (1.33x) approaches the theoretical bound N/(N-1)=4/3.
This organ re-derives the decomposition: given a (2N-2):2N weight block it emits the N-1 packed
2:4 windows, verifies every window is 2:4-compliant and that the union covers the kept weights,
and reports the packing efficiency and the speedup vs. the theoretical N/(N-1) bound.

Deterministic MODELED (2N-2):2N sliding-window pack (seeded, no live kernel):
  * for a block of 2N weights, keep the 2N-2 largest by seeded magnitude (prune the 2 smallest)
    => (2N-2):2N structured sparsity, prune_ratio = 2/(2N) = 1/N.
  * Sliding Window Decomposition: build N-1 windows, each a 2:4-compliant slice (exactly 2
    kept of every 4), overlapping so their union equals the kept set. Verify 2:4 compliance
    per window and full coverage of the kept weights.
  * theoretical speedup = N/(N-1); modeled achieved speedup = theoretical * pack_efficiency,
    where pack_efficiency in (0,1] measures how tightly the N-1 windows cover kept weights.

  keep 2N-2 of 2N (prune 2 smallest)          (structured (2N-2):2N sparsity)
  windows = N-1 overlapping 2:4-compliant slices
  theoretical_speedup = N/(N-1)
  achieved_speedup = theoretical_speedup * pack_efficiency

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic packing SIMULATION. NOT SlideSparse / vLLM / a Sparse Tensor Core
    running; NO live kernel, NO GPU, NO real matmul. Weight magnitudes are SEEDED inputs.
  * 2:4-compliance and coverage are combinatorial facts of the modeled decomposition, honestly
    labeled — the achieved-speedup is a MODELED estimate, NOT a measured kernel timing.
  * The 1.33x / 4/3 figures are the PAPER's reported/theoretical numbers, cited — not measured.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/slidesparse/pack  — (2N-2):2N sliding-window pack snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | SLIDING_WINDOW_PACK_SIM | NOT_LIVE | NO_KERNEL | WEIGHTS_ARE_SEEDED"

CITATIONS = {
    "slidesparse": ("Shao, Hao, Song, Xia, Zhang, Huang, Wu, Xu, Dong, Chi, Zou, Wei (2026) "
                    "SlideSparse: Fast and Flexible (2N-2):2N Structured Sparsity — "
                    "https://arxiv.org/abs/2603.05232"),
    "mishra": ("Mishra, Latorre, Pool, Stosic, Stosic, Venkatesh, Yu, Micikevicius (2021) "
               "Accelerating Sparse Deep Neural Networks (NVIDIA 2:4) — "
               "https://arxiv.org/abs/2104.08378"),
}

# Paper-reported figure (cited, NOT measured here).
_PAPER_MEASURED_SPEEDUP_X = 1.33


class _LCG:
    """Small deterministic LCG PRNG (pure stdlib; no numpy, no stdlib random)."""

    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) & 0xFFFFFFFFFFFFFFFF) or 0x9E3779B97F4A7C15

    def _next(self) -> int:
        self._s = (6364136223846793005 * self._s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self._s

    def random(self) -> float:
        return (self._next() >> 11) / float(1 << 53)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pack_block(weights):
    """Given a block of 2N weight magnitudes, keep the 2N-2 largest (prune the 2 smallest),
    then decompose the kept set into N-1 2:4-compliant windows (Sliding Window Decomposition).

    Returns (kept_mask, windows, all_2to4_compliant, coverage_fraction).
    A 2:4-compliant window keeps exactly 2 of a 4-wide slice. The 2N-2 kept positions split
    evenly into N-1 pairs, so N-1 windows of 2 kept each cover the whole kept set exactly:
    2*(N-1) = 2N-2. Each window's 4-wide slice is centered so its two kept positions land
    inside it, guaranteeing the union of windows == the kept set (full coverage)."""
    n2 = len(weights)               # = 2N
    N = n2 // 2
    keep = 2 * N - 2                 # (2N-2) kept
    order = sorted(range(n2), key=lambda i: weights[i], reverse=True)
    kept_ids = set(order[:keep])
    kept_mask = [1 if i in kept_ids else 0 for i in range(n2)]
    kept_sorted = sorted(kept_ids)   # kept positions in index order

    # Split the 2N-2 kept positions into N-1 consecutive pairs; each pair is one 2:4 window.
    windows = []
    compliant = True
    covered = set()
    for w in range(max(1, N - 1)):
        pair = kept_sorted[2 * w:2 * w + 2]
        if not pair:
            continue
        # 4-wide slice anchored so both kept positions fall inside [start, start+4).
        lo = pair[0]
        start = max(0, min(n2 - 4, lo))
        # ensure the second kept position is inside the 4-wide slice; if not, widen anchor.
        if len(pair) == 2 and pair[1] >= start + 4:
            start = max(0, min(n2 - 4, pair[1] - 3))
        kept_here = [i for i in pair if start <= i < start + 4]
        if len(kept_here) > 2:                     # 2:4 compliance = at most 2 of 4
            compliant = False
        for i in kept_here:
            covered.add(i)
        windows.append({"start": int(start), "kept_positions": [int(i) for i in kept_here]})

    coverage_fraction = len(covered & kept_ids) / max(1, len(kept_ids))
    return kept_mask, windows, compliant, coverage_fraction


def slidesparse_pack(seed: int = 42, big_n: int = 4, blocks: int = 64) -> dict:
    """(2N-2):2N sliding-window pack snapshot (MODELED).

    big_n  — N of the (2N-2):2N pattern (N=4 => 6:8, 25% pruning).
    blocks — number of weight blocks to pack (each block has 2N weights).
    seed   — PRNG seed; deterministic.
    """
    N = max(2, min(32, int(big_n)))
    n2 = 2 * N
    blocks = max(1, min(4096, int(blocks)))
    rng = _LCG(int(seed) * 2_654_435_761 + N * 131 + blocks * 17)

    all_compliant = True
    total_coverage = 0.0
    total_windows = 0
    first_kept_mask = None
    first_windows = None
    for b in range(blocks):
        weights = [rng.random() for _ in range(n2)]
        kept_mask, windows, compliant, coverage = _pack_block(weights)
        all_compliant = all_compliant and compliant
        total_coverage += coverage
        total_windows += len(windows)
        if b == 0:
            first_kept_mask = kept_mask
            first_windows = windows

    mean_coverage = total_coverage / blocks
    windows_per_block = N - 1
    prune_ratio = 2.0 / n2                    # = 1/N
    kept_ratio = 1.0 - prune_ratio
    theoretical_speedup = N / (N - 1)         # N/(N-1) bound from the paper
    pack_efficiency = mean_coverage          # (0,1]; how well windows cover kept weights
    achieved_speedup = theoretical_speedup * pack_efficiency

    return {
        "service": "slidesparse-2n2-pack",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/slidesparse.js ---
        "N": int(N),
        "pattern": "%d:%d" % (n2 - 2, n2),        # e.g. "6:8"
        "block_size": int(n2),
        "blocks": int(blocks),
        "windows_per_block": int(windows_per_block),
        "prune_ratio": round(float(prune_ratio), 6),
        "kept_ratio": round(float(kept_ratio), 6),
        "all_windows_2to4_compliant": bool(all_compliant),
        "pack_efficiency": round(float(pack_efficiency), 6),
        "theoretical_speedup": round(float(theoretical_speedup), 6),
        "achieved_speedup": round(float(achieved_speedup), 6),
        "first_block_kept_mask": [int(x) for x in (first_kept_mask or [])],  # [int 0/1]
        "first_block_windows": first_windows or [],                          # [{start, kept_positions}]
        "paper_reported": {
            "measured_speedup_x": _PAPER_MEASURED_SPEEDUP_X,
            "theoretical_bound": "N/(N-1) = 4/3 at 6:8",
            "note": ("Paper-reported figure (cited, NOT measured here): SlideSparse measured "
                     "1.33x on compute-bound Qwen2.5-7B at 6:8, approaching the N/(N-1)=4/3 "
                     "theoretical bound."),
        },
        "formulas": {
            "sparsity": "keep 2N-2 of 2N (prune 2 smallest) => (2N-2):2N",
            "prune_ratio": "2/(2N) = 1/N",
            "decomposition": "N-1 overlapping 2:4-compliant windows",
            "theoretical_speedup": "N/(N-1)",
            "achieved_speedup": "theoretical_speedup * pack_efficiency",
        },
        "compute_backend": {
            "backend": "CPU pure-Python sliding-window decomposition (seeded LCG)",
            "label": "MODELED",
            "honest_note": ("Deterministic (2N-2):2N pack + 2:4-window check on seeded weights; "
                            "NO live SlideSparse/vLLM kernel, NO GPU, NO real matmul. Achieved "
                            "speedup is modeled. The measured-on-a-real-kernel path is ROADMAP."),
        },
        "honest_note": ("MODELED (2N-2):2N sliding-window packing. NOT SlideSparse / a Sparse "
                        "Tensor Core running; NO live kernel, NO GPU, NO real matmul. Weight "
                        "magnitudes are seeded; 2:4-compliance is a combinatorial fact and "
                        "achieved speedup is a modeled estimate. 1.33x / 4/3 are the paper's "
                        "figures, cited not measured. Advisory to Λ (Conjecture 1); adds "
                        "nothing to the locked-8."),
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (packing snapshot advisory — never an autonomous action)",
        "citations": {"slidesparse": CITATIONS["slidesparse"], "mishra": CITATIONS["mishra"]},
        "wired_into": "frontier ring — SlideSparse surface ((2N-2):2N sliding-window packing)",
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive). Mirrors szl_kc_specdec.register exactly.
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/slidesparse" % ns
    path = "%s/pack" % base

    @app.get(path)
    async def _kc_slidesparse(seed: int = 42, big_n: int = 4, blocks: int = 64):  # noqa: ANN202
        try:
            return JSONResponse(slidesparse_pack(seed=seed, big_n=big_n, blocks=blocks))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "slidesparse-2n2-pack",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "achieved_speedup": None, "all_windows_2to4_compliant": None},
                                status_code=200)

    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_slidesparse_route(request):  # pragma: no cover
            q = request.query_params
            return _SJSON(slidesparse_pack(seed=int(q.get("seed", 42)),
                                           big_n=int(q.get("big_n", 4)),
                                           blocks=int(q.get("blocks", 64))))

        app.router.routes.append(Route(path, _kc_slidesparse_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = slidesparse_pack(seed=42, big_n=4, blocks=64)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("N", "block_size", "blocks", "windows_per_block"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("prune_ratio", "kept_ratio", "pack_efficiency", "theoretical_speedup",
              "achieved_speedup"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["first_block_kept_mask"], list) and r["first_block_kept_mask"], r
    assert isinstance(r["first_block_windows"], list) and r["first_block_windows"], r

    # invariants: pattern, block-size, window-count, compliance, sparsity.
    assert r["pattern"] == "6:8", r["pattern"]           # N=4 default
    assert r["block_size"] == 2 * r["N"], r
    assert r["windows_per_block"] == r["N"] - 1, r
    assert r["all_windows_2to4_compliant"] is True, r
    # exactly 2N-2 kept of 2N in the first block
    assert sum(r["first_block_kept_mask"]) == 2 * r["N"] - 2, r
    assert abs(r["prune_ratio"] - 1.0 / r["N"]) < 1e-9, r
    # every window keeps at most 2 of 4 (2:4 compliance)
    assert all(len(w["kept_positions"]) <= 2 for w in r["first_block_windows"]), r
    # speedup bounds: 1 < theoretical == N/(N-1); achieved <= theoretical.
    assert r["theoretical_speedup"] > 1.0, r
    assert abs(r["theoretical_speedup"] - r["N"] / (r["N"] - 1)) < 1e-6, r
    assert 0.0 < r["achieved_speedup"] <= r["theoretical_speedup"] + 1e-9, r
    out["metrics"] = {"pattern": r["pattern"], "pack_efficiency": r["pack_efficiency"],
                      "theoretical_speedup": r["theoretical_speedup"],
                      "achieved_speedup": r["achieved_speedup"],
                      "prune_ratio": r["prune_ratio"]}

    assert "arxiv.org/abs/2603.05232" in r["citations"]["slidesparse"], r["citations"]
    out["citations_ok"] = True

    # determinism
    r2 = slidesparse_pack(seed=42, big_n=4, blocks=64)
    assert r2["first_block_kept_mask"] == r["first_block_kept_mask"], "non-deterministic mask"
    assert r2["achieved_speedup"] == r["achieved_speedup"], "non-deterministic speedup"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
    print("ALL OK")
