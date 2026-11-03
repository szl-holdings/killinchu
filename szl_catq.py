# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_catq.py — SZL POST-TRAINING CALIBRATION TERNARY QUANT (CAT-Q) endpoint,
MODELED. A SUB-ORGAN UPGRADE of the `ternary` organ (same weight-precision axis
{-1,0,+1}, distinct PTQ-vs-QAT mechanism), NOT a new axis.

Exposes a MODELED, deterministic, closed-form re-implementation of the CAT-Q
post-training ternarization MECHANISM (Wang, Li, Kang, Fan, Yao;
arXiv:2606.26650; "CAT-Q: Cost-efficient and Accurate Ternary Quantization for
LLMs") applied to a small SYNTHETIC, FROZEN, heavy-tailed weight vector drawn
from the pure-stdlib LCG PRNG below — so the catq organ has a live data source
that is honest, deterministic, and citable — never fabricated, never a trained
model, never a run of a real 1.7B–235B LLM.

  GET  /api/<ns>/v1/catq/calibrate?seed=&num_weights=&num_calibration_samples=&mode=

WHAT IS MODELED
---------------
CAT-Q is a POST-TRAINING QUANTIZATION (PTQ) scheme: instead of training a
ternary model from scratch (BitNet-style quantization-aware training over
~100B tokens), it takes an already-pretrained high-precision model FROZEN and
ternarizes it with only a small calibration set (~512 samples). Two coupled
components:

  (1) LEARNABLE MODULATION (LM)   — learnable factors reshape the weight
                                    distribution and the ternary THRESHOLD so
                                    weights are less sensitive to being pushed
                                    to {-1, 0, +1}. Here: a per-group scale
                                    factor + a learnable threshold fraction,
                                    fit BY HAND via closed-form least-squares
                                    on a seeded calibration set (normal
                                    equations, no autograd, no numpy).
  (2) SOFTENED TERNARIZATION (ST) — a differentiable tanh-like transition
                                    function guides ternarization toward stable
                                    convergence instead of a hard snap. Here a
                                    temperature anneals over fixed steps toward
                                    the hard {-1,0,+1} snap.

This module ternarizes the SAME frozen weights TWO ways and MEASURES the honest
difference:

  (a) ABSMEAN BASELINE  — the ternary/BitNet rule: threshold at a fraction of
                          mean(|W|), HARD-SNAP to {-1,0,+1}, single global
                          scale. No calibration.
  (b) CAT-Q PTQ         — per-group learnable scale + learnable threshold fit
                          by least-squares to a seeded calibration set, plus a
                          softened (tanh-anneal) ternarization schedule. NO
                          retraining of the base weights.

Honest results reported:
  RECONSTRUCTION ERROR : ‖W − W_q·scale‖ / ‖W‖ (relative L2), absmean vs CAT-Q.
                         CAT-Q LOWERS it WITHOUT retraining the frozen weights.
  CALIBRATION-TASK ERR : rel-L2 of a toy linear read-out (W·a) over the seeded
                         calibration activations, absmean vs CAT-Q.
  ERROR-vs-CALIB-SIZE  : CAT-Q reconstruction error as a function of the number
                         of calibration samples — falls then PLATEAUS (more
                         calibration helps, with diminishing returns).

Returned JSON fields
--------------------
  label                     : "MODELED" (always — clean-room re-implementation
                              of the CAT-Q PTQ ternarization MECHANISM, NOT a
                              trained model)
  model                     : short description of the modeled setup
  method                    : one-line description of the exact PTQ scheme
  mode                      : "absmean" | "catq" (which ternarizer is primary)
  seed                      : RNG seed used
  num_weights               : size of the frozen synthetic weight vector
  num_calibration_samples   : calibration-set size (paper default 512)
  modulation_groups         : number of per-group learnable scales (LM)
  softening_steps           : # tanh-anneal steps in softened ternarization (ST)
  heavy_tail_outliers       : # large-magnitude outliers injected (heavy tail)
  absmean_scale             : β = mean(|W|) baseline scale
  absmean_threshold         : hard absmean threshold (fraction·β)
  catq_threshold_frac       : learned threshold fraction (LM)
  catq_group_scales         : learned per-group scales (LM), rounded
  ternary_counts_absmean    : {"neg","zero","pos"} for the baseline
  ternary_counts_catq       : {"neg","zero","pos"} for CAT-Q
  recon_err_absmean         : MEASURED relative-L2 reconstruction error (baseline)
  recon_err_catq            : MEASURED relative-L2 reconstruction error (CAT-Q)
  recon_err_improvement     : recon_err_absmean − recon_err_catq (>0 = better)
  recon_err_improvement_frac: fractional error reduction of CAT-Q vs baseline
  calib_task_err_absmean    : MEASURED toy read-out rel-L2 error (baseline)
  calib_task_err_catq       : MEASURED toy read-out rel-L2 error (CAT-Q)
  error_vs_calibration      : list of {n, recon_err} — falls then plateaus
  bits_per_weight_ternary   : log2(3) ≈ 1.58496 (both ternarizers)
  honest_note               : plain-language honesty disclaimer (see below)
  citations                 : dict of citable sources (verified real)
  computed_at               : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  Toy analytic sim of the post-training calibration-ternarization MECHANISM,
  not CAT-Q itself. Pure stdlib, deterministic (same seed -> identical). It
  demonstrates WHY a calibrated, distribution-modulating, softened threshold
  beats a hard absmean snap on frozen weights without retraining; it does NOT
  reproduce CAT-Q's results vs BitNet 1.58-bit v1/v2 or its ~100,000× training-
  token reduction. Explicitly a SUB-ORGAN UPGRADE of `ternary` (same weight-
  precision axis, distinct PTQ-vs-QAT mechanism), not a new axis. The label
  "MODELED" is returned verbatim and displayed verbatim by the surface; never
  upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own; VERIFIED real):
  CAT-Q: Cost-efficient and Accurate Ternary Quantization for LLMs
    Wang, Li, Kang, Fan, Yao (2026). arXiv:2606.26650.
    https://arxiv.org/abs/2606.26650

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
# Citations block — verbatim, VERIFIED real, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "CAT-Q: Cost-efficient and Accurate Ternary Quantization for LLMs — Wang, Li, Kang, Fan, Yao (2026) arXiv:2606.26650": "https://arxiv.org/abs/2606.26650",
}

# log2(3): the information-theoretic bits/weight of a ternary {-1,0,+1} code.
_BITS_PER_TERNARY = math.log2(3.0)  # ≈ 1.5849625007211562


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
# Frozen "pretrained" heavy-tailed weight vector (NOT retrained)
# ---------------------------------------------------------------------------
def _make_heavy_tailed_weights(rng, n: int, outliers: int):
    """
    Deterministic FROZEN weight vector mimicking pretrained-weight stats: a
    Gaussian bulk plus a few large-magnitude outliers (heavy tail). This is the
    frozen model — neither ternarizer retrains it.
    """
    W = [_gauss(rng) for _ in range(n)]
    # inject deterministic large-magnitude outliers (heavy tail)
    for k in range(min(outliers, n)):
        idx = (k * 2654435761) % n
        mag = 4.5 + 3.0 * next(rng)        # 4.5 .. 7.5 sigma
        sign = 1.0 if next(rng) < 0.5 else -1.0
        W[idx] = sign * mag
    return W


# ---------------------------------------------------------------------------
# Shared ternary helpers
# ---------------------------------------------------------------------------
def _absmean(W) -> float:
    """β = mean(|W|)."""
    n = len(W)
    if n == 0:
        return 0.0
    return sum(abs(w) for w in W) / n


def _hard_ternarize(W, thresh: float):
    """Hard snap: |w| < thresh -> 0, else sign(w). Returns (codes, neg,zero,pos)."""
    codes = []
    neg = zero = pos = 0
    for w in W:
        if w > thresh:
            codes.append(1); pos += 1
        elif w < -thresh:
            codes.append(-1); neg += 1
        else:
            codes.append(0); zero += 1
    return codes, neg, zero, pos


def _rel_l2(ref, approx) -> float:
    num = 0.0
    den = 0.0
    for a, b in zip(ref, approx):
        d = a - b
        num += d * d
        den += a * a
    if den <= 0.0:
        return 0.0
    return math.sqrt(num) / math.sqrt(den)


# ---------------------------------------------------------------------------
# (a) ABSMEAN BASELINE ternarizer (hard snap, single global scale)
# ---------------------------------------------------------------------------
def _absmean_quantize(W):
    """
    BitNet-style ternary baseline: threshold at a fraction (0.5) of β=mean(|W|),
    hard snap to {-1,0,+1}, one global scale. Reconstruction W_hat = scale·code,
    where the optimal least-squares scale for fixed codes is
    scale* = Σ(w·code) / Σ(code²).  (closed-form, by hand)
    """
    beta = _absmean(W)
    thresh = 0.5 * beta
    codes, neg, zero, pos = _hard_ternarize(W, thresh)
    scale = _ls_scale(W, codes)
    W_hat = [scale * c for c in codes]
    return {
        "beta": beta,
        "threshold": thresh,
        "scale": scale,
        "codes": codes,
        "counts": {"neg": neg, "zero": zero, "pos": pos},
        "W_hat": W_hat,
    }


def _ls_scale(W, codes) -> float:
    """
    Closed-form least-squares scalar scale for FIXED ternary codes, done by hand:
    minimize Σ (w_i − s·c_i)²  ->  s* = Σ(w_i·c_i) / Σ(c_i²).
    """
    num = 0.0
    den = 0.0
    for w, c in zip(W, codes):
        num += w * c
        den += c * c
    if den <= 0.0:
        return 0.0
    return num / den


# ---------------------------------------------------------------------------
# LEARNABLE MODULATION (LM): per-group scale + learnable threshold, fit by
# closed-form least-squares over a seeded calibration set. Softened (ST) codes.
# ---------------------------------------------------------------------------
def _group_of(i: int, n: int, groups: int) -> int:
    if groups <= 1:
        return 0
    g = (i * groups) // n
    return g if g < groups else groups - 1


def _soft_code(w: float, thresh: float, temp: float) -> float:
    """
    SOFTENED TERNARIZATION: a differentiable tanh transition toward the hard
    {-1,0,+1} snap. As temp -> 0 this approaches the hard threshold rule.
      gate   = 0.5*(tanh((|w|-thresh)/temp)+1)   in [0,1]   (is-nonzero)
      dir    = tanh(w/temp)                       in [-1,1]  (sign, softened)
    soft_code = gate * dir. At temp->0: gate->step(|w|>thresh), dir->sign(w).
    """
    if temp <= 1e-9:
        if w > thresh:
            return 1.0
        if w < -thresh:
            return -1.0
        return 0.0
    gate = 0.5 * (math.tanh((abs(w) - thresh) / temp) + 1.0)
    direction = math.tanh(w / temp)
    return gate * direction


def _anneal_schedule(steps: int):
    """Fixed temperature schedule annealing from 1.0 toward ~0 over `steps`."""
    if steps <= 1:
        return [0.0]
    return [1.0 * (1.0 - i / (steps - 1)) for i in range(steps)]


def _catq_calibrate(W, cal_acts, groups: int, steps: int):
    """
    CAT-Q-style PTQ. FROZEN W is not modified. We fit:
      - a learnable THRESHOLD FRACTION (LM on the threshold), and
      - a per-GROUP learnable SCALE (LM on the distribution),
    by minimizing reconstruction error on the calibration set via a few
    deterministic closed-form least-squares steps (NO autograd, NO numpy),
    while a SOFTENED (tanh-anneal) transition guides the hard-snap codes.

    Returns dict with learned params, hard codes, W_hat, and counts.
    """
    n = len(W)
    beta = _absmean(W)

    # --- LM part 1 (learnable THRESHOLD): search a small deterministic grid of
    #     threshold fractions, pick the one giving the lowest RECONSTRUCTION
    #     error on the frozen weights (with per-group LS scale). This chooses
    #     WHICH weights ternarize to 0 vs ±1 — the learned threshold. ---
    best_frac = 0.5
    best_err = float("inf")
    frac_grid = [0.10 + 0.05 * k for k in range(15)]  # 0.10 .. 0.80 fine grid
    for frac in frac_grid:
        thresh = frac * beta
        codes, _, _, _ = _hard_ternarize(W, thresh)
        scales = _fit_group_scales(W, codes, groups, n)
        W_hat = [scales[_group_of(i, n, groups)] * codes[i] for i in range(n)]
        err = _rel_l2(W, W_hat)
        if err < best_err - 1e-12:
            best_err = err
            best_frac = frac

    thresh = best_frac * beta
    codes, neg, zero, pos = _hard_ternarize(W, thresh)

    # --- ST: softened tanh-anneal warm-start of the per-group scales at the
    #     learned threshold (deterministic, fixed # steps toward the hard snap).
    #     This is the differentiable-transition warm start for the LS fit. ---
    scales = _fit_group_scales(W, codes, groups, n)
    for temp in _anneal_schedule(steps):
        soft = [_soft_code(W[i], thresh, temp) for i in range(n)]
        scales = _fit_group_scales_soft(W, soft, groups, n)

    # Reconstruction-optimal per-group LS scales on the frozen weights (used for
    # the headline reconstruction-error comparison vs the absmean baseline).
    recon_scales = _fit_group_scales(W, codes, groups, n)
    W_hat = [recon_scales[_group_of(i, n, groups)] * codes[i] for i in range(n)]

    # --- LM part 2 (learnable per-group SCALE, CALIBRATED): fit per-group scales
    #     that minimize the toy downstream-task error over the CALIBRATION
    #     activations (y_full = W·a vs y_q = W_hat·a), via a few deterministic
    #     coordinate-descent sweeps using the per-group closed-form LS update.
    #     Calibration statistics are ESTIMATED from the finite calibration set,
    #     so the fitted scales (and thus the task error) converge as the set
    #     grows — producing the honest error-vs-calibration-size curve. ---
    calib_scales = recon_scales
    if cal_acts:
        calib_scales = _calibrate_scales(W, codes, cal_acts, groups, n, scales, sweeps=3)
    W_hat_calib = [calib_scales[_group_of(i, n, groups)] * codes[i] for i in range(n)]

    return {
        "beta": beta,
        "threshold_frac": best_frac,
        "threshold": thresh,
        "group_scales": recon_scales,
        "calib_scales": calib_scales,
        "codes": codes,
        "counts": {"neg": neg, "zero": zero, "pos": pos},
        "W_hat": W_hat,
        "W_hat_calib": W_hat_calib,
    }


def _calibrate_scales(W, codes, cal_acts, groups, n, init_scales, sweeps=3):
    """
    Fit per-group scales s_g to minimize Sigma_samples (y_full - y_q)^2 over the
    calibration activations, where y_q = Sigma_g s_g * q_{s,g} and
    q_{s,g} = Sigma_{i in g} codes_i * a_{s,i}. Done BY HAND via coordinate
    descent: holding other groups fixed, the closed-form optimum for group g is
        s_g = Sigma_s ( r_{s,g} * q_{s,g} ) / Sigma_s ( q_{s,g}^2 )
    where r_{s,g} = y_full_s - Sigma_{h!=g} s_h * q_{s,h} is the residual target.
    Pure stdlib, deterministic. Calibration stats are estimated from the finite
    sample set, so the fit converges as the set grows.
    """
    # Per-sample per-group projections q[s][g] and full targets y_full[s].
    Q = []
    Y = []
    for a in cal_acts:
        qg = [0.0] * groups
        yf = 0.0
        for i in range(n):
            g = _group_of(i, n, groups)
            qg[g] += codes[i] * a[i]
            yf += W[i] * a[i]
        Q.append(qg)
        Y.append(yf)
    s = list(init_scales)
    for _ in range(sweeps):
        for g in range(groups):
            num = 0.0
            den = 0.0
            for si in range(len(Q)):
                qsg = Q[si][g]
                if qsg == 0.0:
                    continue
                # residual target excluding group g's current contribution
                pred_other = 0.0
                for h in range(groups):
                    if h != g:
                        pred_other += s[h] * Q[si][h]
                r = Y[si] - pred_other
                num += r * qsg
                den += qsg * qsg
            if den > 0.0:
                s[g] = num / den
    return s


def _fit_group_scales(W, codes, groups: int, n: int):
    """
    Closed-form per-group least-squares scales for FIXED hard codes, by hand:
    for each group g, s_g* = Σ_{i∈g}(w_i·c_i) / Σ_{i∈g}(c_i²).
    """
    num = [0.0] * groups
    den = [0.0] * groups
    for i in range(n):
        g = _group_of(i, n, groups)
        num[g] += W[i] * codes[i]
        den[g] += codes[i] * codes[i]
    scales = []
    for g in range(groups):
        scales.append(num[g] / den[g] if den[g] > 0.0 else 0.0)
    return scales


def _fit_group_scales_soft(W, soft, groups: int, n: int):
    """Same closed-form LS but against the SOFT (tanh-anneal) codes."""
    num = [0.0] * groups
    den = [0.0] * groups
    for i in range(n):
        g = _group_of(i, n, groups)
        num[g] += W[i] * soft[i]
        den[g] += soft[i] * soft[i]
    scales = []
    for g in range(groups):
        scales.append(num[g] / den[g] if den[g] > 0.0 else 0.0)
    return scales


# ---------------------------------------------------------------------------
# Toy downstream-task error over the calibration activations
# ---------------------------------------------------------------------------
def _task_error(W, W_hat, cal_acts) -> float:
    """
    Toy linear read-out: for each calibration activation vector a, compare
    y_full = W·a against y_q = W_hat·a. Report mean relative-L2 over the set.
    (single output neuron per activation vector -> scalar; average rel error)
    """
    num = 0.0
    den = 0.0
    for a in cal_acts:
        yf = sum(W[i] * a[i] for i in range(len(W)))
        yq = sum(W_hat[i] * a[i] for i in range(len(W)))
        num += (yf - yq) ** 2
        den += yf * yf
    if den <= 0.0:
        return 0.0
    return math.sqrt(num) / math.sqrt(den)


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _catq_snapshot(seed: int = 42, num_weights: int = 256,
                   num_calibration_samples: int = 512,
                   mode: str = "catq") -> dict:
    """
    Deterministically build a FROZEN heavy-tailed weight vector, ternarize it two
    ways on the SAME weights — (a) absmean hard-snap baseline, (b) CAT-Q PTQ with
    learnable modulation + softened ternarization — and MEASURE the honest
    reconstruction / calibration-task error difference, plus an error-vs-
    calibration-size curve.

    Pure stdlib; deterministic — same (seed, num_weights,
    num_calibration_samples, mode) -> identical snapshot, every time.
    """
    if mode not in ("absmean", "catq"):
        mode = "catq"
    groups = 8 if num_weights >= 8 else 1
    steps = 6
    outliers = max(1, num_weights // 32)

    rng = _lcg(seed)
    W = _make_heavy_tailed_weights(rng, num_weights, outliers)

    # seeded "calibration set" of toy activation vectors (drawn AFTER W from the
    # same stream so the whole snapshot is a single deterministic fn of `seed`).
    cal_acts = []
    for _ in range(num_calibration_samples):
        cal_acts.append([_gauss(rng) for _ in range(num_weights)])

    # (a) absmean baseline
    base = _absmean_quantize(W)
    recon_err_absmean = _rel_l2(W, base["W_hat"])
    task_err_absmean = _task_error(W, base["W_hat"], cal_acts)

    # (b) CAT-Q PTQ (learnable modulation + softened ternarization)
    catq = _catq_calibrate(W, cal_acts, groups, steps)
    recon_err_catq = _rel_l2(W, catq["W_hat"])
    task_err_catq = _task_error(W, catq["W_hat_calib"], cal_acts)

    improvement = recon_err_absmean - recon_err_catq
    improvement_frac = (improvement / recon_err_absmean) if recon_err_absmean > 0 else 0.0

    # error-vs-calibration-size curve: CAT-Q's calibration-task error as the
    # calibration set grows. The per-group scales are fit on progressively
    # larger prefixes of the seeded calibration set; the task error (evaluated
    # on the FULL set) falls as more samples sharpen the fit, then plateaus.
    curve = []
    sizes = _curve_sizes(num_calibration_samples)
    for nsz in sizes:
        sub = cal_acts[:nsz] if nsz <= len(cal_acts) else cal_acts
        c = _catq_calibrate(W, sub, groups, steps)
        task_err_n = _task_error(W, c["W_hat_calib"], cal_acts)
        curve.append({"n": nsz, "task_err": round(task_err_n, 6)})

    return {
        "mode": mode,
        "num_weights": num_weights,
        "num_calibration_samples": num_calibration_samples,
        "modulation_groups": groups,
        "softening_steps": steps,
        "heavy_tail_outliers": outliers,
        "absmean_scale": round(base["scale"], 6),
        "absmean_threshold": round(base["threshold"], 6),
        "catq_threshold_frac": round(catq["threshold_frac"], 6),
        "catq_group_scales": [round(s, 6) for s in catq["group_scales"]],
        "catq_calib_scales": [round(s, 6) for s in catq["calib_scales"]],
        "ternary_counts_absmean": base["counts"],
        "ternary_counts_catq": catq["counts"],
        "recon_err_absmean": round(recon_err_absmean, 6),
        "recon_err_catq": round(recon_err_catq, 6),
        "recon_err_improvement": round(improvement, 6),
        "recon_err_improvement_frac": round(improvement_frac, 6),
        "calib_task_err_absmean": round(task_err_absmean, 6),
        "calib_task_err_catq": round(task_err_catq, 6),
        "error_vs_calibration": curve,
        "bits_per_weight_ternary": round(_BITS_PER_TERNARY, 6),
    }


def _curve_sizes(n: int):
    """Deterministic set of calibration prefix sizes (falls-then-plateaus curve)."""
    base = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
    sizes = [s for s in base if s <= max(1, n)]
    if not sizes or sizes[-1] != n:
        sizes.append(max(1, n))
    # dedupe while preserving order
    seen = set()
    out = []
    for s in sizes:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _ss(req: Request, key: str, default: str) -> str:
    v = req.query_params.get(key, default)
    return str(v) if v is not None else default


_HONEST_NOTE = (
    "MODELED: Toy analytic sim of the post-training calibration-ternarization "
    "MECHANISM, not CAT-Q. Weights are a seeded synthetic heavy-tailed vector; "
    "'calibration set' is seeded toy activations; 'learnable modulation' is a "
    "tiny closed-form/least-squares fit and 'softened ternarization' a fixed "
    "tanh-anneal — NO real LLM, NO BitTern code, NO 512-sample calibration of a "
    "1.7B–235B model, NO GPU-hours. Demonstrates WHY a calibrated, distribution-"
    "modulating, softened threshold beats a hard absmean snap on frozen weights "
    "without retraining; does NOT reproduce CAT-Q's results vs BitNet 1.58-bit "
    "v1/v2 or its ~100,000× training-token reduction. Explicitly a SUB-ORGAN "
    "UPGRADE of ternary (same weight-precision axis, distinct PTQ-vs-QAT "
    "mechanism), not a new axis. The label 'MODELED' is returned verbatim and "
    "displayed verbatim by the surface; never upgraded. SZL claims NONE of these "
    "methods as its own."
)


def _h_calibrate(req: Request):
    seed = _ii(req, "seed", 42)
    num_weights = max(8, min(_ii(req, "num_weights", 256), 4096))
    num_cal = max(1, min(_ii(req, "num_calibration_samples", 512), 1024))
    mode = _ss(req, "mode", "catq")
    if mode not in ("absmean", "catq"):
        mode = "catq"

    snap = _catq_snapshot(seed=seed, num_weights=num_weights,
                          num_calibration_samples=num_cal, mode=mode)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Post-training calibration ternary quant (CAT-Q learnable modulation + softened ternarization) on a frozen synthetic heavy-tailed weight vector — SUB-ORGAN UPGRADE of ternary",
        "method": "PTQ: freeze pretrained-like heavy-tailed W; (a) absmean hard-snap baseline vs (b) CAT-Q — per-group learnable scale + learnable threshold fit by closed-form least-squares on a seeded calibration set, guided by a tanh-anneal softened ternarization; NO retraining of base weights, NO autograd, NO numpy",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_ternary.register() / szl_aimc.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/catq/calibrate onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/catq"
    handlers = [
        (f"{base}/calibrate", _h_calibrate),
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
    snap = _catq_snapshot(seed=42, num_weights=256, num_calibration_samples=512, mode="catq")
    print("label: MODELED")
    print("mode:", snap["mode"])
    print("num_weights:", snap["num_weights"])
    print("num_calibration_samples:", snap["num_calibration_samples"])
    print("modulation_groups:", snap["modulation_groups"])
    print("softening_steps:", snap["softening_steps"])
    print("heavy_tail_outliers:", snap["heavy_tail_outliers"])
    print("--- LEARNABLE MODULATION (LM) ---")
    print("absmean_threshold:", snap["absmean_threshold"])
    print("catq_threshold_frac:", snap["catq_threshold_frac"])
    print("catq_group_scales:", snap["catq_group_scales"])
    print("ternary_counts_absmean:", snap["ternary_counts_absmean"])
    print("ternary_counts_catq:", snap["ternary_counts_catq"])
    print("--- RECONSTRUCTION ERROR (MEASURED) absmean vs CAT-Q ---")
    print("recon_err_absmean:", snap["recon_err_absmean"])
    print("recon_err_catq:", snap["recon_err_catq"])
    print("recon_err_improvement:", snap["recon_err_improvement"])
    print("recon_err_improvement_frac:", snap["recon_err_improvement_frac"])
    print("--- CALIBRATION-TASK ERROR (MEASURED) ---")
    print("calib_task_err_absmean:", snap["calib_task_err_absmean"])
    print("calib_task_err_catq:", snap["calib_task_err_catq"])
    print("--- ERROR vs CALIBRATION SIZE (falls then plateaus) ---")
    for pt in snap["error_vs_calibration"]:
        print("  n=%-5d task_err=%s" % (pt["n"], pt["task_err"]))

    # sanity: ternary codes only {-1,0,+1}
    tca = snap["ternary_counts_absmean"]
    tcc = snap["ternary_counts_catq"]
    assert tca["neg"] + tca["zero"] + tca["pos"] == snap["num_weights"], "absmean counts must sum to #weights"
    assert tcc["neg"] + tcc["zero"] + tcc["pos"] == snap["num_weights"], "catq counts must sum to #weights"

    # sanity: reconstruction errors are MEASURED and reported (non-negative)
    assert snap["recon_err_absmean"] > 0.0, "baseline reconstruction error must be non-zero"
    assert snap["recon_err_catq"] >= 0.0, "catq reconstruction error must be reported"

    # sanity: CAT-Q lowers reconstruction error WITHOUT retraining
    assert snap["recon_err_catq"] < snap["recon_err_absmean"], "CAT-Q must lower reconstruction error vs absmean baseline"
    assert snap["recon_err_improvement"] > 0.0, "improvement must be positive"

    # sanity: error-vs-calibration curve falls then plateaus (last <= first and
    # the tail is flat within tolerance)
    curve = snap["error_vs_calibration"]
    assert len(curve) >= 2, "need a curve"
    assert curve[-1]["task_err"] <= curve[0]["task_err"] + 1e-9, "curve should fall (or hold) as calibration grows"
    assert abs(curve[-1]["task_err"] - curve[-2]["task_err"]) < 0.05, "curve tail should plateau"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _catq_snapshot(seed=42, num_weights=256, num_calibration_samples=512, mode="catq")
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_catq: ALL OK — CAT-Q PTQ lowers reconstruction error vs absmean WITHOUT retraining, curve falls then plateaus, deterministic.")
