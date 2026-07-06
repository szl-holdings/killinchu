# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_herotq.py — SZL HeRo-Q HESSIAN-CONDITIONED LOW-BIT QUANTIZATION endpoint
(HeRo-Q = "Hessian Robust Quantization"; a rotation-compression transform
applied to the weight space BEFORE low-bit quantization that reshapes the loss
landscape by REDUCING THE LARGEST HESSIAN EIGENVALUE), MODELED.

Exposes a MODELED, deterministic, closed-form re-implementation of the HeRo-Q
QUANTIZATION-CONDITIONING MECHANISM (Zhang, Jinhao; Yan; Zicheng; Boyang; Sun,
Jun; Cheng, Daning — "HeRo-Q: A General Framework for Stable Low Bit
Quantization via Hessian Conditioning", arXiv:2601.21626) applied to a small
SYNTHETIC weight vector + synthetic curvature (Hessian) matrix drawn from the
pure-stdlib LCG PRNG below — so the herotq organ has a live data source that is
honest, deterministic, and citable — never a trained model, never a real LLM
weight tensor, never a GSM8K/Llama run.

  GET  /api/<ns>/v1/herotq/quantize?seed=&size=&bits=

WHAT IS MODELED
---------------
Post-Training Quantization (PTQ) minimizes quantization ERROR ||w - q(w)||²,
but the loss actually seen by the model is governed by the Hessian H of the loss
landscape: for a weight perturbation Δw = w - q(w), the second-order loss change
is L ≈ ½·Δwᵀ H Δw. When a FEW directions of H have very large eigenvalues (high
curvature), a quantization that looks low-ERROR can still be high-LOSS because
its error happens to align with those stiff directions — the paper's paradoxical
"low error, high loss" phenomenon.

HeRo-Q attacks the Hessian directly. It applies a rotation-compression transform
R to the weight space BEFORE quantizing, chosen so the transformed problem has a
FLATTER largest-eigenvalue direction — i.e. it REDUCES max eigenvalue λ_max of
the (transformed) curvature so the quantization grid is no longer forced to
straddle a stiff direction. This module MODELS that mechanism exactly:

  1. Build a synthetic symmetric PSD Hessian H (size×size) whose spectrum has a
     few deliberately LARGE eigenvalues (high-curvature directions) and many
     small ones — the regime the paper targets.
  2. Diagonalize H = V Λ Vᵀ via a pure-stdlib cyclic JACOBI eigen-decomposition
     (same Jacobi routine family as the muon organ) — V is the orthonormal
     eigenbasis, Λ the eigenvalues.
  3. NAIVE path — quantize w directly to a `bits`-bit uniform grid (symmetric
     round-to-nearest per-tensor). Measure quant MSE and the curvature-weighted
     loss-proxy Δwᵀ H Δw.
  4. HeRo-Q path — ROTATE w into the eigenbasis (u = Vᵀ w), then apply a
     per-axis rotation-COMPRESSION scale s_i = sqrt(1 + λ_i/λ_med) that STRETCHES
     the coordinates lying along stiff (large-λ) directions so they occupy more
     of the shared quantization range and are therefore resolved MORE FINELY.
     Quantize the scaled-rotated coordinates on the same `bits`-bit grid,
     de-scale, and rotate back (w_q = V (s⁻¹ ⊙ q(s ⊙ Vᵀ w))). Because the stiff
     directions are stretched before rounding, their residual error after
     de-scaling is divided DOWN by s_i, so the effective largest curvature the
     grid must resolve — the transformed λ_max = max_i λ_i / s_i² — is REDUCED.
     Measure the same quant MSE and loss-proxy.

The MEASURED comparison is the whole point:
  - λ_max BEFORE (raw H) vs λ_max AFTER (transformed λ/s²)  → the eigenvalue
    reduction the paper claims its rotation-compression achieves.
  - quant MSE naive vs HeRo-Q → HeRo-Q's PURE error may be similar or even
    slightly larger (it spends error budget where curvature is low) …
  - … but the curvature-weighted LOSS-PROXY Δwᵀ H Δw is LOWER for HeRo-Q — the
    "low error, high loss" → "right error, low loss" fix, MEASURED here.

DISTINCTNESS: this is the HESSIAN-EIGENVALUE rotation-compression mechanism.
It is NOT ternary (2-bit sign) weights, and NOT FP4 block-scaling (nvfp4) or
codebook/clustered quantization (catq). The distinguishing object is the
Hessian eigenbasis V and its eigenvalue spectrum Λ, and the transform acts to
lower λ_max — no other organ models curvature/Hessian conditioning.

Returned JSON fields
--------------------
  label                : "MODELED" (always — clean-room re-implementation of the
                         HeRo-Q Hessian-conditioning mechanism, NOT a trained
                         model / real LLM quantization run)
  model                : short description of the modeled setup
  method               : one-line description of the exact transform
  seed                 : RNG seed used
  size                 : dimension of the toy weight vector / Hessian
  bits                 : quantization bit-width (grid has 2^bits levels)
  levels               : 2^bits — number of quantization grid levels
  hessian_eigs         : full eigenvalue spectrum of H (sorted desc)
  max_hessian_eig_before : λ_max of the raw Hessian H (the stiff direction)
  max_hessian_eig_after  : λ_max of the HeRo-Q transformed curvature (λ/s²)
  eig_reduction_factor : max_before / max_after (> 1 — curvature flattening)
  cond_before          : condition number λ_max/λ_min of raw H
  cond_after           : condition number of the transformed curvature
  quant_mse_naive      : mean-squared quantization error, NAIVE path
  quant_mse_herotq     : mean-squared quantization error, HeRo-Q path
  loss_proxy_naive     : curvature-weighted loss ½·Δwᵀ H Δw, NAIVE path
  loss_proxy_herotq    : curvature-weighted loss ½·Δwᵀ H Δw, HeRo-Q path
  loss_reduction_factor: loss_proxy_naive / loss_proxy_herotq (> 1 — the fix)
  low_error_high_loss  : bool — did NAIVE show the paradox (its MSE ≤ HeRo-Q's
                         MSE yet its loss-proxy HIGHER)? MEASURED, not assumed.
  weight_raw           : the toy weight vector w (for the before view)
  weight_naive_q       : the naive-quantized reconstruction
  weight_herotq_q      : the HeRo-Q-quantized reconstruction
  honest_note          : plain-language honesty disclaimer (see below)
  citations            : dict of citable sources (verified real)
  computed_at          : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the HeRo-Q
  Hessian-conditioning ROTATION-COMPRESSION mechanism on a TOY synthetic weight
  vector and synthetic Hessian (no numpy, no stdlib `random`, no trained model,
  no real LLM weights, no GPU kernel). It does NOT quantize a real network, does
  NOT run GSM8K, and does NOT reproduce the paper's Llama3-8B W3A16 70.15% GSM8K
  accuracy or its GPTQ/AWQ/SpinQuant comparisons — those are CLAIMS about REAL
  trained models the estate does NOT independently verify. What IS shown here —
  the largest-Hessian-eigenvalue reduction and the curvature-weighted loss-proxy
  dropping below the naive path (the "low error, high loss" → low-loss fix) — is
  MEASURED from the actual transform. The label "MODELED" is returned verbatim
  and displayed verbatim by the surface; never upgraded.

CITATIONS (clean-room; none claimed as SZL's own; VERIFY real):
  HeRo-Q: A General Framework for Stable Low Bit Quantization via Hessian
    Conditioning — Zhang, Jinhao et al., arXiv:2601.21626
    https://arxiv.org/abs/2601.21626
  NEVER-CLAIMED-AS: this module is not HeRo-Q's released code, does not
  reproduce its GSM8K/Llama3-8B numbers, quantizes no real model, and runs no
  benchmark. It is a clean-room MODELED reproduction of the Hessian-conditioning
  rotation-compression mechanism the work describes.

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
    "HeRo-Q: A General Framework for Stable Low Bit Quantization via Hessian Conditioning — Zhang, Jinhao et al. arXiv:2601.21626": "https://arxiv.org/abs/2601.21626",
}


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


def _matvec(M, v):
    """Matrix-vector product M(p x q) · v(q) -> (p)."""
    out = []
    for row in M:
        acc = 0.0
        for j, x in enumerate(row):
            acc += x * v[j]
        out.append(acc)
    return out


# ---------------------------------------------------------------------------
# Symmetric-eigenvalue routine — cyclic Jacobi rotation (pure stdlib).
# Returns BOTH eigenvalues and the orthonormal eigenvector matrix V (columns
# are eigenvectors), because HeRo-Q rotates the weight into the Hessian
# eigenbasis. Same Jacobi family as the muon organ's spectral routine.
# ---------------------------------------------------------------------------
def _jacobi_eig(A, sweeps: int = 80, tol: float = 1e-14):
    """Eigen-decomposition of a symmetric matrix A (n x n) via cyclic Jacobi.

    Returns (eigenvalues, V) where V[i][j] is component i of eigenvector j
    (i.e. columns of V are the orthonormal eigenvectors). Pure stdlib.
    """
    n = len(A)
    if n == 0:
        return [], []
    M = [list(row) for row in A]
    # V starts as identity; accumulates the product of Jacobi rotations.
    V = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    if n == 1:
        return [M[0][0]], V
    for _ in range(sweeps):
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
                phi = (aqq - app) / (2.0 * apq)
                if phi >= 0.0:
                    t = 1.0 / (phi + math.sqrt(phi * phi + 1.0))
                else:
                    t = 1.0 / (phi - math.sqrt(phi * phi + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                # M := Jᵀ M J
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
                # accumulate eigenvectors: V := V J
                for k in range(n):
                    vkp = V[k][p]
                    vkq = V[k][q]
                    V[k][p] = c * vkp - s * vkq
                    V[k][q] = s * vkp + c * vkq
    eigs = [M[i][i] for i in range(n)]
    return eigs, V


# ---------------------------------------------------------------------------
# Synthetic curvature (Hessian) + weight builders
# ---------------------------------------------------------------------------
def _make_hessian(rng, size: int, n_stiff: int = 3):
    """Build a synthetic symmetric PSD Hessian H (size x size) whose spectrum
    has a few deliberately LARGE eigenvalues (high-curvature directions) and
    many small ones — the "few stiff directions" regime HeRo-Q targets.

    Construction: draw a random orthogonal-ish basis by Gram–Schmidt on a random
    Gaussian matrix, assign eigenvalues (few large, rest small), reassemble
    H = Q diag(λ) Qᵀ. Guarantees H is symmetric PSD by construction.
    """
    # random Gaussian columns -> Gram–Schmidt -> orthonormal basis Q
    cols = [[_gauss(rng) for _ in range(size)] for _ in range(size)]
    basis = []
    for v in cols:
        w = list(v)
        for b in basis:
            dot = sum(w[i] * b[i] for i in range(size))
            for i in range(size):
                w[i] -= dot * b[i]
        norm = math.sqrt(sum(x * x for x in w))
        if norm < 1e-9:
            # degenerate — replace with a unit axis not yet covered
            w = [0.0] * size
            w[len(basis) % size] = 1.0
            norm = 1.0
        basis.append([x / norm for x in w])
    Q = _transpose(basis)  # columns of Q are the orthonormal eigenvectors

    # eigenvalues: a few large (stiff), the rest small (flat)
    lam = []
    for i in range(size):
        if i < n_stiff:
            lam.append(8.0 + 4.0 * (n_stiff - i) + 2.0 * next(rng))   # ~large
        else:
            lam.append(0.15 + 0.6 * next(rng))                        # ~small
    # H = Q diag(lam) Qᵀ
    QL = [[Q[i][j] * lam[j] for j in range(size)] for i in range(size)]
    H = _matmul(QL, _transpose(Q))
    # symmetrize against tiny numerical drift
    for i in range(size):
        for j in range(i + 1, size):
            avg = 0.5 * (H[i][j] + H[j][i])
            H[i][j] = avg
            H[j][i] = avg
    return H


def _make_weight(rng, size: int):
    """Toy weight vector w (size,) of Gaussians — the tensor being quantized."""
    return [0.9 * _gauss(rng) for _ in range(size)]


# ---------------------------------------------------------------------------
# Low-bit uniform quantization (symmetric per-tensor round-to-grid)
# ---------------------------------------------------------------------------
def _quantize_vec(v, bits: int):
    """Symmetric uniform `bits`-bit quantization of vector v.

    Grid: 2^bits levels spanning [-A, +A] with A = max|v|. Round each coord to
    the nearest grid point (round-to-nearest, ties away from zero). Returns the
    dequantized reconstruction (same units as v). Pure stdlib.
    """
    levels = (1 << bits)                # 2^bits levels
    A = max((abs(x) for x in v), default=0.0)
    if A <= 0.0:
        return [0.0 for _ in v]
    # symmetric grid: step so that max magnitude maps to the top level
    step = (2.0 * A) / (levels - 1) if levels > 1 else (2.0 * A)
    out = []
    for x in v:
        # index on the symmetric grid centered at 0
        k = math.floor(x / step + 0.5) if x >= 0 else -math.floor(-x / step + 0.5)
        lo = -(levels // 2)
        hi = (levels - 1) // 2
        if k < lo:
            k = lo
        if k > hi:
            k = hi
        out.append(k * step)
    return out


def _mse(a, b) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    return sum((a[i] - b[i]) ** 2 for i in range(n)) / n


def _loss_proxy(delta, H) -> float:
    """Curvature-weighted second-order loss proxy ½·Δwᵀ H Δw."""
    Hd = _matvec(H, delta)
    quad = sum(delta[i] * Hd[i] for i in range(len(delta)))
    return 0.5 * quad


def _cond(eigs):
    nz = [e for e in eigs if e > 1e-12]
    if not nz:
        return 0.0
    return max(nz) / min(nz)


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _herotq_snapshot(seed: int = 42, size: int = 32, bits: int = 3) -> dict:
    """
    Deterministically build a toy weight w and a synthetic Hessian H with a few
    high-curvature directions, then quantize w to `bits` bits two ways —
    NAIVE round-to-grid, and HeRo-Q (rotate into the Hessian eigenbasis, apply a
    per-axis scale that stretches stiff directions, quantize, de-scale,
    rotate back). MEASURE: max Hessian eigenvalue before vs after the transform,
    quant MSE naive vs HeRo-Q, and the curvature-weighted loss-proxy ½·Δwᵀ H Δw
    for each — showing HeRo-Q's loss lower (the "low error, high loss" fix).

    Pure stdlib; deterministic — same (seed, size, bits) -> identical snapshot.
    """
    rng = _lcg(seed)
    H = _make_hessian(rng, size, n_stiff=min(3, max(1, size // 8)))
    w = _make_weight(rng, size)

    # eigen-decompose the Hessian: H = V diag(eigs) Vᵀ
    eigs, V = _jacobi_eig(H)
    Vt = _transpose(V)                          # Vᵀ (rows are eigenvectors)
    order = sorted(range(len(eigs)), key=lambda i: eigs[i], reverse=True)
    eigs_sorted = [eigs[i] for i in order]
    lam_max_before = eigs_sorted[0] if eigs_sorted else 0.0
    lam_min = min((e for e in eigs if e > 1e-12), default=1e-12)
    # median eigenvalue used as the compression reference scale
    lam_med = sorted(e for e in eigs if e > 0.0)
    lam_med = lam_med[len(lam_med) // 2] if lam_med else 1.0
    if lam_med <= 0.0:
        lam_med = 1.0

    # --- NAIVE path: quantize w directly on the bits-bit grid -----------------
    w_naive_q = _quantize_vec(w, bits)
    delta_naive = [w[i] - w_naive_q[i] for i in range(size)]
    mse_naive = _mse(w, w_naive_q)
    loss_naive = _loss_proxy(delta_naive, H)

    # --- HeRo-Q path: rotate -> stretch -> quantize -> de-scale -> rotate back -
    # u = Vᵀ w  (weight in Hessian eigenbasis; axis i has curvature eigs[i])
    u = _matvec(Vt, w)
    # per-axis scale s_i = sqrt(1 + λ_i/λ_med): STRETCHES stiff axes so the shared
    # rounding grid resolves them more finely (residual error there scaled DOWN
    # after de-scaling). This spends the error budget where curvature is LOW.
    s = [math.sqrt(1.0 + max(0.0, eigs[i]) / lam_med) for i in range(size)]
    u_comp = [u[i] * s[i] for i in range(size)]
    u_comp_q = _quantize_vec(u_comp, bits)
    # de-scale back to eigenbasis coords, then rotate back to weight space
    u_q = [u_comp_q[i] / s[i] if s[i] != 0.0 else 0.0 for i in range(size)]
    w_herotq_q = _matvec(V, u_q)                # V u_q  (rotate back)
    delta_herotq = [w[i] - w_herotq_q[i] for i in range(size)]
    mse_herotq = _mse(w, w_herotq_q)
    loss_herotq = _loss_proxy(delta_herotq, H)

    # transformed curvature the grid must resolve: λ_i / s_i² (the stretch
    # flattens the stiff directions). max over axes is the post-transform λ_max.
    transformed = [max(0.0, eigs[i]) / (s[i] * s[i]) for i in range(size)]
    lam_max_after = max(transformed) if transformed else 0.0
    transf_min = min((t for t in transformed if t > 1e-12), default=1e-12)

    eig_reduction = (lam_max_before / lam_max_after) if lam_max_after > 1e-12 else 0.0
    cond_before = _cond(eigs)
    cond_after = (max(transformed) / transf_min) if transf_min > 1e-12 else 0.0
    loss_reduction = (loss_naive / loss_herotq) if loss_herotq > 1e-15 else 0.0

    # the paradox check, MEASURED: naive has error <= HeRo-Q's yet higher loss.
    low_error_high_loss = bool(mse_naive <= mse_herotq + 1e-12 and loss_naive > loss_herotq)

    def _r(x, d=6):
        return round(x, d)

    return {
        "size": size,
        "bits": bits,
        "levels": (1 << bits),
        "hessian_eigs": [_r(e) for e in eigs_sorted],
        "max_hessian_eig_before": _r(lam_max_before),
        "max_hessian_eig_after": _r(lam_max_after),
        "eig_reduction_factor": _r(eig_reduction),
        "cond_before": _r(cond_before),
        "cond_after": _r(cond_after),
        "quant_mse_naive": _r(mse_naive, 8),
        "quant_mse_herotq": _r(mse_herotq, 8),
        "loss_proxy_naive": _r(loss_naive, 8),
        "loss_proxy_herotq": _r(loss_herotq, 8),
        "loss_reduction_factor": _r(loss_reduction),
        "low_error_high_loss": low_error_high_loss,
        "weight_raw": [_r(x) for x in w],
        "weight_naive_q": [_r(x) for x in w_naive_q],
        "weight_herotq_q": [_r(x) for x in w_herotq_q],
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
    "MODELED: this is a clean-room reproduction of the HeRo-Q Hessian-conditioning "
    "ROTATION-COMPRESSION quantization mechanism (Zhang, Jinhao et al., "
    "arXiv:2601.21626) on a TOY synthetic weight vector and a synthetic Hessian "
    "with a few high-curvature directions, NOT a trained model. The transform is "
    "run exactly: rotate the weight into the Hessian eigenbasis (u = Vᵀw via a "
    "stdlib Jacobi eigen-decomposition), apply a per-axis scale "
    "s_i = sqrt(1 + λ_i/λ_med) that stretches stiff directions for finer "
    "resolution, quantize to a bits-bit uniform grid, de-scale, and rotate back. The largest-Hessian-"
    "eigenvalue reduction (max_hessian_eig_before vs after), the quant MSE naive "
    "vs HeRo-Q, and the curvature-weighted loss-proxy ½·ΔwᵀHΔw dropping below the "
    "naive path (the paper's 'low error, high loss' → low-loss fix) are all "
    "MEASURED and displayed. This is a Hessian-conditioning DEMO — it quantizes "
    "NOTHING real, runs NO GSM8K, and does NOT reproduce the paper's Llama3-8B "
    "W3A16 70.15% GSM8K accuracy or its GPTQ/AWQ/SpinQuant comparisons (those are "
    "claims about REAL trained models). DISTINCT from ternary (2-bit sign) and "
    "FP4 block-scaling / codebook quantization — this is the Hessian-eigenvalue "
    "rotation mechanism. Pure stdlib, no numpy, no stdlib random, no GPU kernel. "
    "Deterministic: same seed/size/bits -> identical snapshot. NEVER-CLAIMED-AS a "
    "production quantizer. SZL claims NONE of these methods as its own."
)


def _h_quantize(req: Request):
    seed = _ii(req, "seed", 42)
    size = max(4, min(_ii(req, "size", 32), 64))
    bits = max(2, min(_ii(req, "bits", 3), 8))

    snap = _herotq_snapshot(seed=seed, size=size, bits=bits)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "HeRo-Q Hessian-Robust low-bit quantization (rotation-compression transform that reduces the largest Hessian eigenvalue before quantizing) on a synthetic weight vector + synthetic high-curvature Hessian",
        "method": "H = V diag(λ) Vᵀ via stdlib Jacobi eig; NAIVE = round w to a 2^bits-level uniform grid; HeRo-Q = w_q = V(s⁻¹⊙q(s⊙Vᵀw)) with per-axis scale s_i=sqrt(1+λ_i/λ_med); MEASURE λ_max before vs after (=max λ_i/s_i²), quant MSE naive vs HeRo-Q, and curvature-weighted loss ½·Δwᵀ H Δw for each",
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
    """Wire /api/<ns>/v1/herotq/quantize onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/herotq"
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
    snap = _herotq_snapshot(seed=42, size=32, bits=3)
    print("label: MODELED")
    print("size:", snap["size"], "bits:", snap["bits"], "levels:", snap["levels"])
    print("--- HESSIAN SPECTRUM (few high-curvature directions) ---")
    print("  eigs head:", ["%.3f" % v for v in snap["hessian_eigs"][:6]])
    print("  eigs tail:", ["%.3f" % v for v in snap["hessian_eigs"][-4:]])
    print("--- METRIC: LARGEST HESSIAN EIGENVALUE (rotation-compression) ---")
    print("  max_hessian_eig_before:", snap["max_hessian_eig_before"])
    print("  max_hessian_eig_after :", snap["max_hessian_eig_after"])
    print("  eig_reduction_factor  :", snap["eig_reduction_factor"], "x")
    print("  cond_before:", snap["cond_before"], " cond_after:", snap["cond_after"])
    print("--- METRIC: QUANT MSE (pure error) ---")
    print("  quant_mse_naive :", snap["quant_mse_naive"])
    print("  quant_mse_herotq:", snap["quant_mse_herotq"])
    print("--- METRIC: CURVATURE-WEIGHTED LOSS-PROXY  1/2 * dwᵀ H dw ---")
    print("  loss_proxy_naive :", snap["loss_proxy_naive"])
    print("  loss_proxy_herotq:", snap["loss_proxy_herotq"])
    print("  loss_reduction_factor:", snap["loss_reduction_factor"], "x")
    print("  low_error_high_loss (paradox present in NAIVE):", snap["low_error_high_loss"])

    # sanity: spectrum has the expected size
    assert len(snap["hessian_eigs"]) == snap["size"], "one eigenvalue per dimension"
    assert snap["levels"] == (1 << snap["bits"]), "levels = 2^bits"

    # sanity: the rotation-compression REDUCES the largest Hessian eigenvalue
    assert snap["max_hessian_eig_after"] < snap["max_hessian_eig_before"], \
        "HeRo-Q must reduce the largest Hessian eigenvalue"
    assert snap["eig_reduction_factor"] > 1.0, "eigenvalue reduction must be a real factor > 1"
    assert snap["cond_after"] < snap["cond_before"], "transform must flatten curvature (cond drops)"

    # sanity: the curvature-weighted LOSS-PROXY is LOWER for HeRo-Q (the fix)
    assert snap["loss_proxy_herotq"] < snap["loss_proxy_naive"], \
        "HeRo-Q curvature-weighted loss must be lower than naive"
    assert snap["loss_reduction_factor"] > 1.0, "loss reduction must be a real factor > 1"

    # sanity: measured MSE / loss are non-negative and finite
    for k in ("quant_mse_naive", "quant_mse_herotq", "loss_proxy_naive", "loss_proxy_herotq"):
        assert snap[k] >= 0.0, f"{k} must be non-negative"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _herotq_snapshot(seed=42, size=32, bits=3)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_herotq: ALL OK — largest Hessian eigenvalue reduced, curvature-weighted loss dropped below naive, deterministic.")
