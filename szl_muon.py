# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_muon.py — SZL MUON ORTHOGONALIZED-MOMENTUM OPTIMIZER endpoint (Muon =
"MomentUm Orthogonalized by Newton–Schulz"; the quintic Newton–Schulz
orthogonalization of a momentum-derived update matrix), MODELED.

Exposes a MODELED, deterministic, closed-form re-implementation of the Muon
optimizer's ORTHOGONALIZATION MECHANISM (Keller Jordan, Yuchen Jin, Vlado Boza,
Jiacheng You, Franz Cesista, Laker Newhouse, Jeremy Bernstein — original Muon;
Moonshot AI "Muon is Scalable for LLM Training" / Moonlight, Jingyuan Liu,
Jianlin Su, Xingcheng Yao et al., arXiv:2502.16982) applied to a small
SYNTHETIC Gaussian momentum matrix drawn from the pure-stdlib LCG PRNG below —
so the muon organ has a live data source that is honest, deterministic, and
citable — never a trained model, never a real optimizer run, never a GPU kernel.

  GET  /api/<ns>/v1/muon/orthogonalize?seed=&m=&n=&ns_steps=

WHAT IS MODELED
---------------
Muon operates only on 2D (matrix-shaped) hidden-layer parameters. Given a
momentum-derived update matrix G ∈ R^{m×n}, Muon replaces it with the nearest
semi-orthogonal matrix in Frobenius norm — i.e. UVᵀ from the SVD G = U Σ Vᵀ,
discarding the singular VALUES and keeping only the singular SUBSPACES (a
"zeroth power" / matrix-sign-like operation). Rather than a full SVD, Muon
approximates it with a QUINTIC NEWTON–SCHULZ recurrence:

  X_0   = G / ||G||_F
  A_k   = X_k X_kᵀ
  X_{k+1} = a·X_k + (b·A_k + c·A_k²)·X_k
          = a·X_k + b·(X_k X_kᵀ)·X_k + c·(X_k X_kᵀ)²·X_k

with hand-tuned, deliberately NON-convergent coefficients
(a, b, c) = (3.4445, -4.7750, 2.0315) run for ~5 steps. Each step is a matrix
polynomial applied to the singular values: for X_k = U Σ_k Vᵀ, the singular
values evolve as σ_{k+1} = a·σ_k + b·σ_k³ + c·σ_k⁵. The coefficients maximize
the slope at zero, inflating small singular values toward 1 as fast as
possible — sacrificing exact convergence (values oscillate in ~[0.68, 1.13]
rather than settling at exactly 1) in exchange for needing only ~5 iterations
instead of the 10+ a classical convergent cubic iteration would take. It runs
stably as pure matrix multiplies, GPU-friendly in bfloat16 — unlike a real SVD.

This module re-implements that EXACT recurrence on a deterministic synthetic
momentum matrix and MEASURES the spectral effect honestly. Because there is no
numpy, the singular-value spectrum at each iteration is obtained from a small
pure-stdlib symmetric-eigenvalue routine (cyclic JACOBI rotation on the Gram
matrix XᵀX; σ_i = sqrt(max(0, λ_i))). The metrics returned are:

  SV SPECTRUM       : the full singular-value spectrum of X_k at every NS
                      iteration k = 0..ns_steps (each a sorted list). At k=0
                      this is the raw (Frobenius-normalized) spectrum; by k=ns
                      the non-zero singular values cluster in the [0.68, 1.13]
                      Muon convergence band.
  CONDITION NUMBER  : κ = σ_max / σ_min of the raw (normalized) matrix vs. the
                      orthogonalized output — honestly showing spectral
                      flattening (κ collapses toward ~1), NOT a downstream loss
                      improvement (no model is trained).
  CONVERGENCE BAND  : the [0.68, 1.13] band the non-zero singular values
                      oscillate within, plus the MEASURED fraction of them that
                      actually land inside it after ns_steps.

THE MECHANISM, HONESTLY: orthogonalization flattens the singular spectrum so no
single direction dominates the update — a better-conditioned, more isotropic
step at <2% overhead over plain SGD-momentum. That spectral flattening is
MEASURED and displayed here; the "≈2× compute-optimal efficiency vs AdamW" is a
claim about a REAL trained run (Moonshot / Keller Jordan) that this toy does NOT
reproduce or verify.

Returned JSON fields
--------------------
  label                : "MODELED" (always — clean-room re-implementation of the
                         Muon Newton–Schulz orthogonalization mechanism, NOT a
                         trained model / optimizer run)
  model                : short description of the modeled setup
  method               : one-line description of the exact recurrence
  seed                 : RNG seed used
  m, n                 : synthetic momentum-matrix dimensions
  ns_steps             : number of Newton–Schulz iterations run (k = 0..ns_steps)
  coeffs               : {"a","b","c"} — the quintic NS coefficients used
  frob_norm_raw        : Frobenius norm of the raw momentum matrix G
  aspect_scale         : max(1, m/n)^0.5 aspect-ratio scaling factor (Muon)
  rank                 : min(m, n) — number of singular values tracked
  sv_spectrum          : list (len ns_steps+1) of per-iteration singular-value
                         spectra (each a sorted-desc list of `rank` floats)
  sv_iter0             : convenience alias — the raw (k=0) spectrum
  sv_final             : convenience alias — the k=ns_steps spectrum
  cond_raw             : condition number κ of the raw normalized matrix
  cond_ortho           : condition number κ of the orthogonalized output
  cond_improvement     : cond_raw / cond_ortho (≥ 1 — spectral flattening factor)
  band_lo, band_hi     : the [0.68, 1.13] Muon oscillation band bounds
  frac_in_band         : MEASURED fraction of final non-zero σ inside the band
  sv_min_final         : min non-zero singular value at k=ns_steps
  sv_max_final         : max singular value at k=ns_steps
  matrix_raw           : the raw normalized matrix X_0 (for the before heatmap)
  matrix_ortho         : the orthogonalized output X_ns (for the after heatmap)
  honest_note          : plain-language honesty disclaimer (see below)
  citations            : dict of citable sources (verified real)
  computed_at          : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the Muon quintic
  Newton–Schulz ORTHOGONALIZATION mechanism on a TOY synthetic momentum matrix
  (no numpy, no stdlib `random`, no trained model, no optimizer run, no GPU
  kernel, no bfloat16 hardware). It does NOT train anything, does NOT reproduce
  the NanoGPT/CIFAR speedrun records, and does NOT reproduce Moonshot's ~2×
  compute-efficiency result — those are CLAIMS about REAL training runs that
  the estate does NOT independently verify. What IS shown here — the singular
  spectrum flattening toward the [0.68, 1.13] band and the condition-number
  collapse — is MEASURED from the actual recurrence. The label "MODELED" is
  returned verbatim and displayed verbatim by the surface; never upgraded.

CITATIONS (clean-room; none claimed as SZL's own; VERIFY real):
  Muon: An optimizer for hidden layers in neural networks — Keller Jordan et al.
    (blog + reference code): https://kellerjordan.github.io/posts/muon/
  Muon is Scalable for LLM Training (Moonlight) — Jingyuan Liu, Jianlin Su,
    Xingcheng Yao et al., Moonshot AI. arXiv:2502.16982
    https://arxiv.org/abs/2502.16982
  KellerJordan/Muon reference implementation (GitHub):
    https://github.com/KellerJordan/Muon
  NEVER-CLAIMED-AS: this module is not Muon's released code, does not reproduce
  its speedrun/scaling numbers, trains no model, and runs no optimizer. It is a
  clean-room MODELED reproduction of the Newton–Schulz orthogonalization the
  work describes.

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
    "Muon: An optimizer for hidden layers in neural networks — Keller Jordan et al. (blog + reference code)": "https://kellerjordan.github.io/posts/muon/",
    "Muon is Scalable for LLM Training (Moonlight) — Jingyuan Liu, Jianlin Su, Xingcheng Yao et al. (Moonshot AI) arXiv:2502.16982": "https://arxiv.org/abs/2502.16982",
    "KellerJordan/Muon reference implementation (GitHub)": "https://github.com/KellerJordan/Muon",
}

# The hand-tuned, deliberately non-convergent quintic Newton–Schulz coefficients
# used by Muon (Keller Jordan). Chosen to maximize slope at zero so small
# singular values inflate toward 1 fast; values then oscillate in ~[0.68, 1.13].
_NS_A = 3.4445
_NS_B = -4.7750
_NS_C = 2.0315

# The Muon singular-value oscillation band (non-convergent by design).
_BAND_LO = 0.68
_BAND_HI = 1.13


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
def _make_momentum(rng, m: int, n: int):
    """Deterministic dense synthetic momentum matrix G (m x n) of Gaussians."""
    return [[_gauss(rng) for _ in range(n)] for _ in range(m)]


def _frob_norm(M) -> float:
    total = 0.0
    for row in M:
        for v in row:
            total += v * v
    return math.sqrt(total)


def _scale(M, s: float):
    return [[v * s for v in row] for row in M]


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


def _gram(X):
    """Return XᵀX (n x n), the smaller symmetric Gram matrix (n = cols)."""
    return _matmul(_transpose(X), X)


# ---------------------------------------------------------------------------
# Symmetric-eigenvalue routine — cyclic Jacobi rotation (pure stdlib).
# Used to extract the singular-value spectrum of X via eig(XᵀX): the
# eigenvalues λ_i of the (symmetric PSD) Gram matrix give σ_i = sqrt(max(0,λ_i)).
# ---------------------------------------------------------------------------
def _jacobi_eigenvalues(A, sweeps: int = 60, tol: float = 1e-12):
    """Eigenvalues of a symmetric matrix A (n x n) via cyclic Jacobi rotations.

    Returns a list of eigenvalues (unordered). Pure stdlib; deterministic.
    """
    n = len(A)
    if n == 0:
        return []
    if n == 1:
        return [A[0][0]]
    # work on a mutable copy
    M = [list(row) for row in A]
    for _ in range(sweeps):
        # measure off-diagonal magnitude
        off = 0.0
        for p in range(n):
            for q in range(p + 1, n):
                off += M[p][q] * M[p][q]
        if off <= tol:
            break
        for p in range(n):
            for q in range(p + 1, n):
                apq = M[p][q]
                if abs(apq) <= 1e-300:
                    continue
                app = M[p][p]
                aqq = M[q][q]
                # Jacobi rotation angle
                phi = (aqq - app) / (2.0 * apq)
                if phi >= 0.0:
                    t = 1.0 / (phi + math.sqrt(phi * phi + 1.0))
                else:
                    t = 1.0 / (phi - math.sqrt(phi * phi + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                # apply rotation to rows/cols p,q of M (M := Jᵀ M J)
                for k in range(n):
                    mkp = M[k][p]
                    mkq = M[k][q]
                    M[k][p] = c * mkp - s * mkq
                    M[k][q] = s * mkp + c * mkq
                for k in range(n):
                    mpk = M[p][k]
                    mqk = M[q][k]
                    M[p][k] = c * mpk - s * mqk
                    M[q][k] = s * mpk + c * mqk
    return [M[i][i] for i in range(n)]


def _singular_values(X, rank: int):
    """Singular-value spectrum of X (m x n) via eig(XᵀX), sorted descending.

    Picks the smaller of the two Gram matrices (XᵀX is n x n; XXᵀ is m x m)
    for speed — both share the non-zero eigenvalues.
    """
    m = len(X)
    n = len(X[0]) if X else 0
    if m <= n:
        G = _matmul(X, _transpose(X))  # m x m
    else:
        G = _gram(X)                    # n x n
    lam = _jacobi_eigenvalues(G)
    svals = sorted((math.sqrt(v) if v > 0.0 else 0.0 for v in lam), reverse=True)
    # keep exactly `rank` values (pad with zeros if the Gram side was larger)
    if len(svals) < rank:
        svals = svals + [0.0] * (rank - len(svals))
    return svals[:rank]


# ---------------------------------------------------------------------------
# Quintic Newton–Schulz orthogonalization step (the EXACT Muon recurrence)
# ---------------------------------------------------------------------------
def _ns_step(X, a: float, b: float, c: float):
    """One Muon Newton–Schulz iteration:

        A   = X Xᵀ
        X'  = a·X + (b·A + c·A²)·X
            = a·X + b·A·X + c·A·(A·X)

    Pure matmuls; no SVD, no numpy.
    """
    Xt = _transpose(X)
    A = _matmul(X, Xt)          # m x m
    AX = _matmul(A, X)          # m x n
    A2X = _matmul(A, AX)        # m x n  == A²X
    m = len(X)
    n = len(X[0]) if X else 0
    out = [[a * X[i][j] + b * AX[i][j] + c * A2X[i][j] for j in range(n)] for i in range(m)]
    return out


def _cond_number(svals) -> float:
    """κ = σ_max / σ_min over the NON-ZERO singular values (guarded)."""
    nz = [v for v in svals if v > 1e-12]
    if not nz:
        return 0.0
    smax = max(nz)
    smin = min(nz)
    if smin <= 0.0:
        return float("inf")
    return smax / smin


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _muon_snapshot(seed: int = 42, m: int = 32, n: int = 32, ns_steps: int = 5) -> dict:
    """
    Deterministically build a synthetic momentum matrix G, Frobenius-normalize
    it (X_0 = G/||G||_F), run the Muon quintic Newton–Schulz recurrence for
    k = 0..ns_steps, record the singular-value spectrum at every iteration, and
    MEASURE the condition number raw vs orthogonalized plus the fraction of
    final singular values inside the [0.68, 1.13] Muon oscillation band.

    Pure stdlib; deterministic — same (seed, m, n, ns_steps) -> identical snapshot.
    """
    rng = _lcg(seed)
    G = _make_momentum(rng, m, n)
    frob = _frob_norm(G)
    if frob <= 0.0:
        frob = 1.0
    X = _scale(G, 1.0 / frob)     # X_0 = G / ||G||_F
    rank = min(m, n)

    a, b, c = _NS_A, _NS_B, _NS_C

    sv_spectrum = []
    Xk = X
    # k = 0 spectrum (raw normalized), then ns_steps iterations
    sv_spectrum.append([round(v, 6) for v in _singular_values(Xk, rank)])
    for _ in range(max(0, ns_steps)):
        Xk = _ns_step(Xk, a, b, c)
        sv_spectrum.append([round(v, 6) for v in _singular_values(Xk, rank)])

    raw_sv = _singular_values(X, rank)
    final_sv = _singular_values(Xk, rank)

    cond_raw = _cond_number(raw_sv)
    cond_ortho = _cond_number(final_sv)
    cond_improvement = (cond_raw / cond_ortho) if cond_ortho > 0.0 else 0.0

    nz_final = [v for v in final_sv if v > 1e-9]
    in_band = sum(1 for v in nz_final if _BAND_LO <= v <= _BAND_HI)
    frac_in_band = (in_band / len(nz_final)) if nz_final else 0.0

    sv_min_final = min(nz_final) if nz_final else 0.0
    sv_max_final = max(final_sv) if final_sv else 0.0

    aspect_scale = math.sqrt(max(1.0, m / n)) if n > 0 else 1.0

    # trimmed matrices for the before/after heatmap (cap emitted size for payload)
    cap = 32
    def _trim(M):
        return [[round(v, 6) for v in row[:cap]] for row in M[:cap]]

    return {
        "m": m,
        "n": n,
        "ns_steps": ns_steps,
        "coeffs": {"a": a, "b": b, "c": c},
        "frob_norm_raw": round(frob, 6),
        "aspect_scale": round(aspect_scale, 6),
        "rank": rank,
        "sv_spectrum": sv_spectrum,
        "sv_iter0": sv_spectrum[0],
        "sv_final": sv_spectrum[-1],
        "cond_raw": round(cond_raw, 6),
        "cond_ortho": round(cond_ortho, 6),
        "cond_improvement": round(cond_improvement, 6),
        "band_lo": _BAND_LO,
        "band_hi": _BAND_HI,
        "frac_in_band": round(frac_in_band, 6),
        "sv_min_final": round(sv_min_final, 6),
        "sv_max_final": round(sv_max_final, 6),
        "matrix_raw": _trim(X),
        "matrix_ortho": _trim(Xk),
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
    "MODELED: this is a clean-room reproduction of the Muon quintic "
    "Newton–Schulz ORTHOGONALIZATION mechanism (Keller Jordan et al.; Moonshot "
    "AI 'Muon is Scalable for LLM Training' / Moonlight, arXiv:2502.16982) on a "
    "TOY synthetic momentum matrix, NOT a trained model. The recurrence "
    "X_{k+1} = a·X + b·(XXᵀ)X + c·(XXᵀ)²X with a=3.4445 b=-4.7750 c=2.0315 is "
    "run exactly; the singular spectrum flattening toward the [0.68, 1.13] "
    "oscillation band and the condition-number collapse are MEASURED and "
    "displayed (see cond_raw / cond_ortho / frac_in_band). This is a "
    "Newton–Schulz DEMO — it trains NOTHING, reproduces NO speedrun/scaling "
    "numbers, and does NOT verify the '≈2× compute-optimal efficiency vs "
    "AdamW' claim (that is a claim about a REAL training run). Pure stdlib, no "
    "numpy, no stdlib random, no GPU kernel, no bfloat16 hardware. "
    "Deterministic: same seed/m/n/ns_steps -> identical snapshot. "
    "NEVER-CLAIMED-AS a production optimizer. SZL claims NONE of these methods "
    "as its own."
)


def _h_orthogonalize(req: Request):
    seed     = _ii(req, "seed",      42)
    m        = max(2, min(_ii(req, "m",        32), 64))
    n        = max(2, min(_ii(req, "n",        32), 64))
    ns_steps = max(0, min(_ii(req, "ns_steps",  5), 12))

    snap = _muon_snapshot(seed=seed, m=m, n=n, ns_steps=ns_steps)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Muon Orthogonalized-Momentum Optimizer (quintic Newton–Schulz orthogonalization of a momentum-derived update matrix) on a synthetic Gaussian momentum matrix",
        "method": "X_0 = G/||G||_F; A = X Xᵀ; X_{k+1} = a·X + b·(X Xᵀ)X + c·(X Xᵀ)²X with (a,b,c)=(3.4445,-4.7750,2.0315) for k=0..ns_steps; singular-value spectrum per iteration via stdlib Jacobi eig(XᵀX); condition number raw vs orthogonalized; non-convergent [0.68,1.13] band",
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
    """Wire /api/<ns>/v1/muon/orthogonalize onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/muon"
    handlers = [
        (f"{base}/orthogonalize", _h_orthogonalize),
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
    snap = _muon_snapshot(seed=42, m=32, n=32, ns_steps=5)
    print("label: MODELED")
    print("m:", snap["m"], "n:", snap["n"], "ns_steps:", snap["ns_steps"])
    print("coeffs:", snap["coeffs"])
    print("frob_norm_raw:", snap["frob_norm_raw"])
    print("aspect_scale:", snap["aspect_scale"])
    print("rank:", snap["rank"])
    print("--- SV SPECTRUM PER NEWTON–SCHULZ ITERATION ---")
    for k, sv in enumerate(snap["sv_spectrum"]):
        head = sv[:6]
        print(f"  k={k}: min={min([v for v in sv if v>1e-9], default=0.0):.4f} "
              f"max={max(sv):.4f}  head={['%.3f'%v for v in head]}")
    print("--- METRIC: CONDITION NUMBER (spectral flattening) ---")
    print("cond_raw:", snap["cond_raw"])
    print("cond_ortho:", snap["cond_ortho"])
    print("cond_improvement:", snap["cond_improvement"], "x")
    print("--- METRIC: [0.68, 1.13] CONVERGENCE BAND ---")
    print("band:", [snap["band_lo"], snap["band_hi"]])
    print("frac_in_band:", snap["frac_in_band"])
    print("sv_min_final:", snap["sv_min_final"], "sv_max_final:", snap["sv_max_final"])

    # sanity: spectrum recorded at every iteration k=0..ns_steps
    assert len(snap["sv_spectrum"]) == snap["ns_steps"] + 1, "one spectrum per iteration incl. k=0"
    for sv in snap["sv_spectrum"]:
        assert len(sv) == snap["rank"], "each spectrum has `rank` singular values"

    # sanity: orthogonalization FLATTENS the spectrum -> condition number drops
    assert snap["cond_ortho"] > 0.0, "orthogonalized condition number must be measured"
    assert snap["cond_ortho"] < snap["cond_raw"], "Newton–Schulz must flatten the spectrum (κ drops)"
    assert snap["cond_improvement"] > 1.0, "condition-number improvement must be a real factor > 1"

    # sanity: final non-zero singular values land in the Muon oscillation band
    assert 0.0 <= snap["frac_in_band"] <= 1.0, "frac_in_band out of range"
    assert snap["frac_in_band"] > 0.5, "most final singular values should sit in [0.68, 1.13]"
    assert snap["band_lo"] <= snap["sv_max_final"] <= snap["band_hi"] + 0.05, "max σ near the upper band"

    # sanity: coefficients are the exact hand-tuned Muon quintic constants
    assert snap["coeffs"] == {"a": 3.4445, "b": -4.7750, "c": 2.0315}, "Muon NS coefficients"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _muon_snapshot(seed=42, m=32, n=32, ns_steps=5)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_muon: ALL OK — Newton–Schulz orthogonalized, spectrum flattened toward [0.68,1.13], κ collapsed, deterministic.")
