#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""killinchu_mined_ops.py — MINED operational upgrades (clean-room, pure-stdlib).

ADDITIVE, self-contained, register(app, ns="killinchu")-style. NO MOCKS: every
endpoint computes real numbers from whatever real telemetry the caller submits
(or from the sample fleet, honestly labelled "sample, not a live feed").

This module ships four operational upgrades whose PATTERNS were mined from
permissive (MIT/Apache) open-source projects under the "fashion thinking"
doctrine — adopt the pattern + permissive code WITH NOTICE attribution, then
EVOLVE to our own clean-room implementation. No upstream code is copied; each
algorithm is reimplemented from scratch in pure Python (no numpy/torch needed).

================================  NOTICE  ===================================
Adopted patterns (attribution; full entries also in NOTICES.md):

1. scientific/sensor-fusion math  ← al-jshen/compute  (MIT, © 2020 Jeff Shen)
   https://github.com/al-jshen/compute
   Adopted: the *shape* of a small scientific-computing surface — linear
   solver (Cholesky / Gaussian elimination), numerical integration (trapz /
   Romberg), AR(1) Yule-Walker, OLS design+fit. Reimplemented clean in stdlib
   and EVOLVED into a maritime/orbital sensor-fusion math module: least-squares
   track fit, Cholesky-gated covariance fusion, Keplerian period (Kepler-III),
   and Romberg energy-integral for a noisy telemetry channel.

2. tactical resource / VRAM estimator ← lwaekfjlk/gpu-bartender (MIT, © 2024 Haofei Yu)
   https://github.com/lwaekfjlk/gpu-bartender
   Adopted: the component-sum VRAM model (params + activations + gradients +
   optimizer moments + CUDA-kernel floor; bytes/param by precision; transformer
   activation breakdown). Reimplemented clean and EVOLVED to an EDGE deployment
   feasibility estimator: given drone/field-Mac VRAM budget, does an inference
   (or LoRA) workload FIT? Returns per-component MiB + fit verdict + headroom.

3. swarm resilience monitor ← mcleish7/MLRC-deep-thinking (MIT, © 2021 Avi Schwarzschild)
   https://github.com/mcleish7/MLRC-deep-thinking
   Adopted: the perturbation-recovery test + Asymptotic-Alignment (AA) idea —
   inject a fault into an iterative (recurrent) process, then measure how fast /
   how completely it recovers its fixed-point. Reimplemented clean (a contractive
   consensus iteration over swarm node states) and EVOLVED into a comms/sensor
   disruption resilience monitor: perturb K nodes, run averaging-consensus
   recovery, report recovery-iterations-to-tolerance + AA-style alignment score.

4. telemetry-memory efficiency ← mcleish7/kvpress (Apache-2.0, NVIDIA/kvpress fork)
   https://github.com/mcleish7/kvpress
   Adopted: the "press" idea — score cache entries by *expected future attention*
   and prune the lowest-value entries (SnapKV / ExpectedAttention family).
   Reimplemented clean and EVOLVED into a priority-weighted telemetry-retention
   filter: score each telemetry frame by recency × magnitude-spike × source-trust,
   keep the top-budget high-value frames, prune noise — report compression ratio
   and retained-value fraction so the drone "remembers" critical sensor spikes.
=============================================================================

Endpoints (all under /api/killinchu/v1/mined/*, registered EARLY before catch-all):
  POST /api/killinchu/v1/mined/scicompute      sensor-fusion / orbital math (al-jshen pattern)
  POST /api/killinchu/v1/mined/edge-estimator   edge VRAM feasibility (gpu-bartender pattern)
  POST /api/killinchu/v1/mined/swarm-resilience perturbation-recovery monitor (MLRC pattern)
  POST /api/killinchu/v1/mined/telemetry-press  priority-weighted retention (kvpress pattern)
  GET  /api/killinchu/v1/mined/index            machine-readable manifest of these upgrades

Honesty doctrine: Λ stays Conjecture 1; every advisory output is labelled. Sample
inputs are labelled "sample, not a live feed". No fabricated success: bad input
returns an honest 400/empty result, never invented numbers.

Doctrine v11 LOCKED — 749/14/163 — Λ = Conjecture 1 (NEVER a theorem).
Signed-off-by: Yachay <yachay@szlholdings.ai>
Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
from __future__ import annotations

import json
import math
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

# Universal gravitational parameter for Earth (GM_earth), m^3/s^2 — public constant.
_MU_EARTH = 3.986004418e14


# ───────────────────────── small clean-room scientific kernels ──────────────
# (Reimplemented from scratch — pattern adopted from al-jshen/compute, MIT.)

def _mat_t(A: list[list[float]]) -> list[list[float]]:
    return [list(col) for col in zip(*A)]


def _matmul(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    Bt = _mat_t(B)
    return [[sum(a * b for a, b in zip(row, col)) for col in Bt] for row in A]


def _matvec(A: list[list[float]], x: list[float]) -> list[float]:
    return [sum(a * xi for a, xi in zip(row, x)) for row in A]


def _solve_spd(A: list[list[float]], b: list[float]) -> tuple[list[float] | None, bool]:
    """Solve A x = b for a symmetric positive-definite A via Cholesky.

    Returns (solution, spd_ok). spd_ok=False (and solution=None) if A is not
    strictly SPD — an honest signal that the fusion would collapse, NOT faked.
    """
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                d = A[i][i] - s
                if d <= 1e-12:
                    return None, False
                L[i][j] = math.sqrt(d)
            else:
                L[i][j] = (A[i][j] - s) / L[j][j]
    # forward solve L y = b
    y = [0.0] * n
    for i in range(n):
        y[i] = (b[i] - sum(L[i][k] * y[k] for k in range(i))) / L[i][i]
    # back solve L^T x = y
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (y[i] - sum(L[k][i] * x[k] for k in range(i + 1, n))) / L[i][i]
    return x, True


def _ols_linear_fit(t: list[float], y: list[float]) -> dict[str, float]:
    """Ordinary least-squares line fit y = a + b t (closed form, no lib)."""
    n = len(t)
    st = sum(t); sy = sum(y)
    stt = sum(v * v for v in t); sty = sum(a * b for a, b in zip(t, y))
    denom = n * stt - st * st
    if abs(denom) < 1e-12:
        return {"a": sy / n if n else 0.0, "b": 0.0, "r2": 0.0}
    b = (n * sty - st * sy) / denom
    a = (sy - b * st) / n
    ybar = sy / n
    ss_tot = sum((v - ybar) ** 2 for v in y) or 1e-12
    ss_res = sum((y[i] - (a + b * t[i])) ** 2 for i in range(n))
    return {"a": a, "b": b, "r2": max(0.0, 1.0 - ss_res / ss_tot)}


def _romberg(f, lo: float, hi: float, max_steps: int = 6) -> float:
    """Romberg numerical integration (pattern: compute::integrate::romberg)."""
    R = [[0.0] * (max_steps) for _ in range(max_steps)]
    h = hi - lo
    R[0][0] = 0.5 * h * (f(lo) + f(hi))
    for i in range(1, max_steps):
        h *= 0.5
        s = sum(f(lo + (2 * k - 1) * h) for k in range(1, 2 ** (i - 1) + 1))
        R[i][0] = 0.5 * R[i - 1][0] + s * h
        for j in range(1, i + 1):
            R[i][j] = R[i][j - 1] + (R[i][j - 1] - R[i - 1][j - 1]) / (4 ** j - 1)
    return R[max_steps - 1][max_steps - 1]


def _ar1_yule_walker(x: list[float]) -> dict[str, float]:
    """AR(1) coefficient via Yule-Walker (lag-1 autocorrelation)."""
    n = len(x)
    if n < 3:
        return {"phi": 0.0, "mean": (sum(x) / n if n else 0.0)}
    mu = sum(x) / n
    c0 = sum((v - mu) ** 2 for v in x) / n or 1e-12
    c1 = sum((x[i] - mu) * (x[i - 1] - mu) for i in range(1, n)) / n
    return {"phi": c1 / c0, "mean": mu}


# ───────────────────────────── endpoint handlers ────────────────────────────

async def _body(request: Request) -> dict:
    try:
        raw = await request.body()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def register(app, ns: str = "killinchu") -> str:
    base = f"/api/{ns}/v1/mined"
    routes: list[str] = []

    # ---- 1. scientific / sensor-fusion / orbital compute --------------------
    @app.post(base + "/scicompute")
    async def mined_scicompute(request: Request):
        d = await _body(request)
        mode = (d.get("mode") or "track-fit").strip()
        out: dict[str, Any] = {
            "mode": mode,
            "source": "al-jshen/compute (MIT) — pattern adopted, clean-room stdlib reimpl",
            "honest": "advisory scientific compute; Λ stays Conjecture 1; not a proven guarantee",
        }
        if mode == "track-fit":
            # least-squares constant-velocity fit of a noisy 1-axis track
            t = [float(v) for v in (d.get("t") or [0, 1, 2, 3, 4])]
            y = [float(v) for v in (d.get("y") or [0.0, 9.9, 20.2, 29.7, 40.4])]
            if len(t) != len(y) or len(t) < 2:
                return JSONResponse({"error": "t and y must be equal-length arrays len>=2"}, status_code=400)
            fit = _ols_linear_fit(t, y)
            out.update({
                "fit": {"position_0": fit["a"], "velocity": fit["b"], "r2": fit["r2"]},
                "interpretation": "OLS constant-velocity track fit; velocity=b (units/step), r2=goodness",
                "sample_input": (d.get("t") is None),
            })
        elif mode == "fuse-covariance":
            # fuse two sensor estimates with their covariances (info-form), Cholesky-gated
            x1 = [float(v) for v in (d.get("x1") or [10.0, 4.0])]
            x2 = [float(v) for v in (d.get("x2") or [10.8, 3.6])]
            P1 = [[float(v) for v in row] for row in (d.get("P1") or [[0.5, 0.1], [0.1, 0.4]])]
            P2 = [[float(v) for v in row] for row in (d.get("P2") or [[0.9, 0.0], [0.0, 0.7]])]
            n = len(x1)
            # information form: P_f^{-1} = P1^{-1}+P2^{-1}; x_f = P_f (P1^{-1}x1+P2^{-1}x2)
            i1, ok1 = _solve_spd(P1, x1)
            i2, ok2 = _solve_spd(P2, x2)
            if not (ok1 and ok2):
                return JSONResponse({"error": "a sensor covariance is not SPD — fusion would collapse (honest)",
                                     "spd_ok": False}, status_code=400)
            # Build summed information matrix Pf_inv and rhs
            P1inv = [[ _solve_spd(P1, [1.0 if k == j else 0.0 for k in range(n)])[0][i]
                       for j in range(n)] for i in range(n)]
            P2inv = [[ _solve_spd(P2, [1.0 if k == j else 0.0 for k in range(n)])[0][i]
                       for j in range(n)] for i in range(n)]
            Pf_inv = [[P1inv[i][j] + P2inv[i][j] for j in range(n)] for i in range(n)]
            rhs = [sum(P1inv[i][j] * x1[j] for j in range(n)) +
                   sum(P2inv[i][j] * x2[j] for j in range(n)) for i in range(n)]
            xf, okf = _solve_spd(Pf_inv, rhs)
            if not okf:
                return JSONResponse({"error": "fused information matrix not SPD (honest)", "spd_ok": False}, status_code=400)
            out.update({
                "fused_estimate": xf,
                "spd_ok": True,
                "interpretation": "Cholesky-gated information-form covariance fusion of two sensors",
                "sample_input": (d.get("x1") is None),
            })
        elif mode == "kepler-period":
            # orbital period from semi-major axis (Kepler's third law), real physics
            a_km = float(d.get("semi_major_axis_km", 7000.0))
            a_m = a_km * 1000.0
            if a_m <= 0:
                return JSONResponse({"error": "semi_major_axis_km must be > 0"}, status_code=400)
            T = 2 * math.pi * math.sqrt(a_m ** 3 / _MU_EARTH)
            v_circ = math.sqrt(_MU_EARTH / a_m)
            out.update({
                "semi_major_axis_km": a_km,
                "orbital_period_s": T,
                "orbital_period_min": T / 60.0,
                "circular_velocity_km_s": v_circ / 1000.0,
                "interpretation": "Kepler III: T=2π√(a³/μ); μ=GM_earth=3.986004418e14 m³/s²",
                "sample_input": ("semi_major_axis_km" not in d),
            })
        elif mode == "energy-integral":
            # Romberg integral of a noisy power channel -> total energy (real numeric integration)
            samples = [float(v) for v in (d.get("power_w") or [12.0, 14.0, 19.0, 17.0, 11.0])]
            if len(samples) < 2:
                return JSONResponse({"error": "power_w must have >=2 samples"}, status_code=400)
            dt = float(d.get("dt_s", 1.0))
            # piecewise-linear interpolant for Romberg over [0, (n-1)dt]
            n = len(samples)
            def f(x: float) -> float:
                idx = min(int(x / dt), n - 2)
                frac = (x - idx * dt) / dt
                return samples[idx] * (1 - frac) + samples[idx + 1] * frac
            energy_j = _romberg(f, 0.0, (n - 1) * dt, max_steps=6)
            out.update({
                "energy_joules": energy_j,
                "energy_wh": energy_j / 3600.0,
                "ar1_phi": _ar1_yule_walker(samples)["phi"],
                "interpretation": "Romberg ∫P dt = energy; AR(1) φ = telemetry persistence",
                "sample_input": (d.get("power_w") is None),
            })
        else:
            return JSONResponse({"error": f"unknown mode '{mode}'",
                                 "modes": ["track-fit", "fuse-covariance", "kepler-period", "energy-integral"]},
                                status_code=400)
        return JSONResponse(out)
    routes.append("POST " + base + "/scicompute")

    # ---- 2. edge VRAM feasibility estimator ---------------------------------
    @app.post(base + "/edge-estimator")
    async def mined_edge_estimator(request: Request):
        d = await _body(request)
        # transformer / workload parameters (sample = a small 1.3B field model)
        num_params_b = float(d.get("num_params_billions", 1.3))
        hidden = int(d.get("hidden_size", 2048))
        heads = int(d.get("num_attention_heads", 16))
        kv_heads = int(d.get("num_key_value_heads", heads))
        inter = int(d.get("intermediate_size", hidden * 4))
        layers = int(d.get("num_layers", 24))
        vocab = int(d.get("vocab_size", 32000))
        batch = int(d.get("batch_size", 1))
        seq = int(d.get("sequence_length", 2048))
        precision = (d.get("precision") or "mixed").strip()      # mixed|full|half
        workload = (d.get("workload") or "inference").strip()    # inference|lora|full-train
        budget_gib = float(d.get("vram_budget_gib", 8.0))        # e.g. field Mac / drone SoC
        if num_params_b <= 0 or hidden <= 0 or layers <= 0:
            return JSONResponse({"error": "model dims must be > 0"}, status_code=400)

        bpp = {"mixed": 6, "full": 4, "half": 2}.get(precision, 6)
        MiB = 2 ** 20
        num_params = num_params_b * 1e9
        head_dim = hidden // max(1, heads)

        # activations breakdown (transformer; pattern from gpu-bartender, reimplemented)
        attn = (bpp * batch * seq * hidden                       # attention input
                + bpp * batch * seq * head_dim * heads           # q
                + bpp * batch * seq * head_dim * kv_heads        # k
                + bpp * batch * heads * seq * seq                # softmax out
                + bpp * batch * seq * head_dim * kv_heads        # v
                + bpp * batch * seq * heads * head_dim           # out-proj input
                + batch * heads * seq * seq                      # softmax dropout mask
                + bpp * batch * heads * seq * seq                # dropout output
                + batch * seq * hidden)                          # attention dropout
        mlp = (bpp * batch * seq * hidden + bpp * batch * seq * inter
               + bpp * batch * seq * inter + batch * seq * hidden)
        lnorm = bpp * batch * seq * hidden * 2
        activations = (attn + mlp + lnorm) * layers
        params_bytes = bpp * num_params
        cuda_floor = 1000 * MiB
        outputs = 4 * batch * seq * vocab * 2

        comp: dict[str, float] = {
            "runtime_floor_MiB": round(cuda_floor / MiB, 1),
            "weights_MiB": round(params_bytes / MiB, 1),
            "activations_MiB": round(activations / MiB, 1),
        }
        total = cuda_floor + params_bytes + activations
        if workload in ("lora", "full-train"):
            comp["outputs_MiB"] = round(outputs / MiB, 1)
            total += outputs
            if workload == "full-train":
                grads = 4 * num_params
                m1 = 4 * num_params  # Adam first moment
                m2 = 4 * num_params  # Adam second moment
                comp["gradients_MiB"] = round(grads / MiB, 1)
                comp["adam_m1_MiB"] = round(m1 / MiB, 1)
                comp["adam_m2_MiB"] = round(m2 / MiB, 1)
                total += grads + m1 + m2
            else:  # lora: only adapter grads+moments (~1% of params), much smaller
                adapter = 0.01 * num_params
                lora_extra = 4 * adapter * 3  # grad + 2 moments
                comp["lora_adapter_MiB"] = round((4 * adapter) / MiB, 1)
                comp["lora_optimizer_MiB"] = round((4 * adapter * 2) / MiB, 1)
                total += lora_extra

        total_gib = total / (2 ** 30)
        budget_bytes = budget_gib * (2 ** 30)
        fits = total <= budget_bytes
        out = {
            "source": "lwaekfjlk/gpu-bartender (MIT) — pattern adopted, clean-room reimpl",
            "honest": "advisory edge-deployment estimate; real component-sum model, not a benchmark",
            "workload": workload, "precision": precision, "bytes_per_param": bpp,
            "components_MiB": comp,
            "total_estimate_GiB": round(total_gib, 3),
            "vram_budget_GiB": budget_gib,
            "fits_on_edge": fits,
            "headroom_GiB": round(budget_gib - total_gib, 3),
            "verdict": ("FITS — deployable on this edge node" if fits
                        else "EXCEEDS budget — quantize/shrink seq or use a smaller model"),
            "sample_input": ("num_params_billions" not in d),
        }
        return JSONResponse(out)
    routes.append("POST " + base + "/edge-estimator")

    # ---- 3. swarm resilience monitor (perturbation-recovery) ----------------
    @app.post(base + "/swarm-resilience")
    async def mined_swarm_resilience(request: Request):
        d = await _body(request)
        # swarm node "mission plan" scalar states; consensus = converge to mean
        states = [float(v) for v in (d.get("node_states") or [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 10.3, 9.7])]
        n = len(states)
        if n < 2:
            return JSONResponse({"error": "need >=2 node_states"}, status_code=400)
        # perturbation: which nodes get disrupted, and by how much
        perturb_nodes = [int(i) for i in (d.get("perturb_nodes") or [0, 1])]
        perturb_mag = float(d.get("perturb_magnitude", 8.0))   # large comms/sensor disruption
        alpha = float(d.get("consensus_rate", 0.35))           # contraction step in (0,1)
        tol = float(d.get("tolerance", 0.05))
        max_iters = int(d.get("max_iters", 100))

        pre_plan = sum(states) / n  # the agreed pre-disruption mission plan
        x = list(states)
        for i in perturb_nodes:
            if 0 <= i < n:
                x[i] += perturb_mag  # inject the comms/sensor disruption
        # The swarm RE-AGREES via averaging consensus. The fixed point of a
        # doubly-stochastic averaging iteration is the current mean of states.
        # Resilience = how fast the swarm collapses its DISAGREEMENT (spread)
        # back below tolerance after the disruption — i.e. re-forms one plan.
        def _consensus_step(v: list[float]) -> list[float]:
            # symmetric ring averaging: mass-conserving, fixed point = mean(v)
            return [v[i] + alpha * (((v[(i - 1) % n] + v[(i + 1) % n]) / 2.0) - v[i]) for i in range(n)]

        def _spread(v: list[float]) -> float:
            m = sum(v) / len(v)
            return max(abs(vi - m) for vi in v)

        init_spread = _spread(x) or 1e-12
        traj_err = []
        recovered_at = None
        for it in range(max_iters):
            err = _spread(x)  # disagreement across the swarm
            traj_err.append(round(err, 5))
            if err <= tol and recovered_at is None:
                recovered_at = it
                break
            x = _consensus_step(x)
        final_err = _spread(x)
        new_plan = sum(x) / n  # the re-agreed plan after the disruption
        # Asymptotic-Alignment-style score: how completely the swarm realigned (1=perfect)
        aa_score = max(0.0, min(1.0, 1.0 - final_err / init_spread))
        out = {
            "source": "mcleish7/MLRC-deep-thinking (MIT) — perturbation-recovery + AA pattern, clean-room reimpl",
            "honest": "advisory resilience metric on a contractive consensus model; Λ stays Conjecture 1",
            "nodes": n, "perturbed_nodes": perturb_nodes, "perturb_magnitude": perturb_mag,
            "pre_disruption_plan": round(pre_plan, 4),
            "re_agreed_plan": round(new_plan, 4),
            "recovery_iterations": recovered_at if recovered_at is not None else None,
            "recovered_within_tolerance": recovered_at is not None,
            "tolerance": tol,
            "asymptotic_alignment_score": round(aa_score, 4),
            "final_error": round(final_err, 5),
            "error_trajectory": traj_err[:40],
            "metric": "swarm disagreement (max deviation from running mean) collapsing below tolerance after disruption",
            "verdict": (f"RESILIENT — swarm re-agreed a single plan in {recovered_at} iterations"
                        if recovered_at is not None else
                        "DEGRADED — did not re-agree within max_iters (raise consensus_rate or check topology)"),
            "sample_input": (d.get("node_states") is None),
        }
        return JSONResponse(out)
    routes.append("POST " + base + "/swarm-resilience")

    # ---- 4. telemetry-memory press (priority-weighted retention) ------------
    @app.post(base + "/telemetry-press")
    async def mined_telemetry_press(request: Request):
        d = await _body(request)
        # each frame: {value, source_trust(0..1), ts}; or sample stream
        frames = d.get("frames")
        sample = False
        if not frames:
            sample = True
            # sample telemetry with a couple of high-value spikes buried in noise
            import random as _r
            _r.seed(7)
            frames = []
            for i in range(60):
                base_v = 10.0 + _r.gauss(0, 0.6)
                if i in (17, 41):  # critical sensor spikes
                    base_v += 14.0
                frames.append({"value": round(base_v, 3), "source_trust": round(0.7 + 0.3 * _r.random(), 3), "ts": i})
        N = len(frames)
        if N == 0:
            return JSONResponse({"error": "no frames"}, status_code=400)
        keep_frac = float(d.get("keep_fraction", 0.4))
        keep_frac = min(1.0, max(0.02, keep_frac))
        budget = max(1, int(round(N * keep_frac)))

        vals = [float(f.get("value", 0.0)) for f in frames]
        mu = sum(vals) / N
        sd = (sum((v - mu) ** 2 for v in vals) / N) ** 0.5 or 1e-9
        ts = [float(f.get("ts", i)) for i, f in enumerate(frames)]
        tmin, tmax = min(ts), max(ts)
        tspan = (tmax - tmin) or 1.0
        # EVOLVED "expected-attention" score: magnitude-spike (z) × source-trust × recency
        scored = []
        for i, f in enumerate(frames):
            z = abs(vals[i] - mu) / sd                       # magnitude-spike (kvpress: high attention)
            trust = float(f.get("source_trust", 1.0))
            recency = 0.3 + 0.7 * ((ts[i] - tmin) / tspan)   # newer telemetry weighted higher
            score = z * trust * recency
            scored.append((score, i))
        scored.sort(reverse=True)
        kept_idx = sorted(i for _, i in scored[:budget])
        retained_value = sum(abs(vals[i] - mu) for i in kept_idx)
        total_value = sum(abs(v - mu) for v in vals) or 1e-9
        out = {
            "source": "mcleish7/kvpress (Apache-2.0) — ExpectedAttention press pattern, clean-room reimpl",
            "honest": "advisory telemetry-retention filter; lossy by design; labels what was pruned",
            "frames_in": N, "frames_kept": len(kept_idx),
            "keep_fraction": round(len(kept_idx) / N, 4),
            "compression_ratio": round(N / max(1, len(kept_idx)), 2),
            "retained_value_fraction": round(retained_value / total_value, 4),
            "kept_indices": kept_idx[:64],
            "interpretation": ("score = magnitude-spike(z) × source-trust × recency; "
                               "top-budget frames retained — critical spikes survive, noise pruned"),
            "sample_input": sample,
            "sample_note": "sample telemetry stream, not a live feed" if sample else None,
        }
        return JSONResponse(out)
    routes.append("POST " + base + "/telemetry-press")

    # ---- manifest -----------------------------------------------------------
    @app.get(base + "/index")
    async def mined_index():
        return JSONResponse({
            "module": "killinchu_mined_ops",
            "doctrine": "fashion thinking — adopt permissive pattern WITH NOTICE, then evolve; Λ=Conjecture 1",
            "upgrades": [
                {"name": "scicompute", "endpoint": base + "/scicompute",
                 "source": "al-jshen/compute", "license": "MIT",
                 "modes": ["track-fit", "fuse-covariance", "kepler-period", "energy-integral"]},
                {"name": "edge-estimator", "endpoint": base + "/edge-estimator",
                 "source": "lwaekfjlk/gpu-bartender", "license": "MIT"},
                {"name": "swarm-resilience", "endpoint": base + "/swarm-resilience",
                 "source": "mcleish7/MLRC-deep-thinking", "license": "MIT"},
                {"name": "telemetry-press", "endpoint": base + "/telemetry-press",
                 "source": "mcleish7/kvpress", "license": "Apache-2.0"},
            ],
            "routes": routes + ["GET " + base + "/index"],
        })
    routes.append("GET " + base + "/index")

    return f"mined-ops-wired:{len(routes)}-routes"
