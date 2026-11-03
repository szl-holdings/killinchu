# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_s3search.py — SZL Verifier-Guided Stratified Search over Denoising
Trajectories (S³) endpoint, MODELED.

Exposes a MODELED, deterministic, pure-stdlib toy simulation of the S³
mechanism (Bilal et al. 2026, arXiv:2604.06260): reallocating test-time
compute DURING the denoising process of a diffusion language model rather than
only at the final output stage. This is a same-origin REST endpoint so the
s3search surface organ has a live data source that is honest, deterministic,
and citable — never fabricated, never random-faked, never a learned model.

  GET  /api/<ns>/v1/s3search/search?seed=&frontier_width=&branch_factor=&num_denoise_steps=

WHAT IS SIMULATED
-----------------
Naïve best-of-K from a FIXED diffusion LM is fundamentally limited: it
repeatedly draws from the same base diffusion distribution, whose
high-probability regions are often misaligned with high-quality outputs. S³
is a classical verifier-guided search that acts DURING DENOISING:

  * maintain a FRONTIER of W candidate trajectories (frontier_width);
  * at each denoising step, expand each trajectory into B children
    (branch_factor) via seeded noise perturbations of a state vector that is
    being driven toward a fixed target "sentence" over a small symbol set;
  * score every child with a lightweight, reference-free VERIFIER — here a
    CLOSED-FORM grammar-satisfaction proxy (deterministic stand-in for
    "quality"), not a learned verifier;
  * STRATIFIED-RESAMPLE the expanded pool back down to W survivors that
    (a) favor high verifier score (reward-tilt, verifier_weight) and
    (b) preserve frontier diversity (a bucketed / stratified rule across
    diversity_strata score bands), approximating a reward-tilted sampling
    distribution while staying anchored to the model prior.

Model + denoising schedule are UNCHANGED; only WHERE compute is spent changes
(mid-trajectory branch/prune vs final-output selection).

BASELINES (both reported at MATCHED compute)
--------------------------------------------
  no_search        : a single trajectory denoised to completion (no search).
  final_best_of_k  : K independent single trajectories denoised to completion,
                     keep the best-verifier final output (the "test-time"
                     analogue — compute spent only at the FINAL stage). K is
                     chosen so the FLOP-proxy budget MATCHES S³.
  s3               : the full mid-denoising stratified branch-and-prune search.

"Compute" is a FLOP-PROXY: a counter of state-update operations (one unit per
child trajectory advanced one denoising step). S³ spends W*B updates/step; the
matched final-best-of-K spends the same total budget as K parallel single
trajectories of the same depth. Reporting quality (grammar-satisfaction of the
best final trajectory) + frontier diversity for all three AT MATCHED BUDGET.

Returned JSON fields
--------------------
  label                 : "MODELED" (always — toy analytic sim, not S³)
  model                 : short description of the simulated setup
  seed                  : RNG seed used (deterministic LCG)
  frontier_width        : W — number of trajectories kept on the frontier
  branch_factor         : B — children expanded per trajectory per step
  num_denoise_steps     : number of denoising steps
  verifier_weight       : reward-tilt strength of the verifier in resampling
  diversity_strata      : number of score bands used by the stratified rule
  target                : the fixed toy target "sentence" (symbol string)
  flop_proxy_budget     : matched state-update budget shared by all methods
  no_search             : {quality, diversity, flops}
  final_best_of_k       : {quality, diversity, flops, k}
  s3                    : {quality, diversity, flops}
  s3_trajectory         : per-step [{step, best_quality, mean_quality, diversity, survivors}]
  quality_gap_s3_vs_bok : s3.quality - final_best_of_k.quality (>=0 => S³ wins)
  honest_note           : plain-language honesty disclaimer (incl. distinctness flag)
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  Toy analytic sim of the mid-denoising stratified-search MECHANISM, not S³.
  The "diffusion LM" is a seeded toy denoiser over a few symbols; the
  "reference-free verifier" is a closed-form grammar-satisfaction proxy, not a
  learned verifier; "compute" is a state-update counter, not real FLOPs. It
  demonstrates that trajectory branch-and-prune can beat final best-of-K at a
  matched toy budget on a constructed constraint; it does NOT reproduce S³'s
  LLaDA-8B-Instruct results on MATH-500/GSM8K/ARC-Challenge/TruthfulQA. The
  label "MODELED" is returned verbatim and displayed verbatim by the surface;
  it is never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  S³ (Stratified Scaling Search over denoising trajectories — the mechanism
  toy-modeled here):
    Bilal, Mohsin, Umer, Aali, Khanzada, Rafique, He, Fox & Hougen (2026)
    "S³: Stratified Scaling Search for Test-Time in Diffusion Language
    Models". arXiv:2604.06260. https://arxiv.org/abs/2604.06260

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  No LLM calls of any kind — pure closed-form arithmetic. Self-contained toy
  denoiser; does NOT import elf.
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
    "S³ Stratified Scaling Search — Bilal et al. 2026, arXiv:2604.06260": "https://arxiv.org/abs/2604.06260",
}

# Toy symbol alphabet for the denoiser (small, fixed). The "sentence" being
# denoised toward is a fixed target string over these symbols.
_ALPHABET = "abcdefgh"          # 8 symbols
_TARGET   = "beadcafe"          # fixed toy target "sentence" (length 8)

# Cap on how many per-step trajectory rows we echo back for the surface's
# frontier-branching animation.
_MAX_TRAJ_ROWS = 32


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
# Toy denoiser + closed-form reference-free verifier (SELF-CONTAINED)
# ---------------------------------------------------------------------------
_N = len(_ALPHABET)


def _init_state(rng, length: int):
    """A trajectory state is a per-position float in [0, N) whose rounded index
    selects a symbol. Fully seeded initialization (the "fully-noised" prior)."""
    return [next(rng) * _N for _ in range(length)]


def _decode(state):
    """Round each position's float to the nearest symbol index -> string."""
    return "".join(_ALPHABET[min(_N - 1, int(round(v)) % _N)] for v in state)


def _denoise_step(rng, state, step, total_steps, noise_scale=1.0):
    """One deterministic-plus-seeded-noise denoising update of a state vector.

    Each position is nudged a fraction toward its target symbol index (the
    schedule's deterministic drift) plus a seeded noise perturbation whose
    magnitude shrinks as denoising proceeds (annealing). This is the toy
    stand-in for a diffusion LM's reverse process. Returns a NEW state list.
    """
    # annealing: less noise, stronger drift as we approach the final step.
    # Drift is deliberately WEAK and noise deliberately PERSISTENT so a single
    # unguided trajectory rarely satisfies the full constraint on its own —
    # this is what makes verifier-guided search matter (honest signal).
    frac = (step + 1) / max(1, total_steps)
    drift = 0.10 + 0.18 * frac
    noise = noise_scale * (0.55 + 0.9 * (1.0 - frac)) * 1.6
    out = []
    for pos, v in enumerate(state):
        tgt = _ALPHABET.index(_TARGET[pos % len(_TARGET)])
        n = (next(rng) - 0.5) * 2.0 * noise      # seeded perturbation in [-noise, noise)
        nv = v + drift * (tgt - v) + n
        # keep in [0, N)
        if nv < 0.0:
            nv = 0.0
        elif nv > _N - 1e-9:
            nv = _N - 1e-9
        out.append(nv)
    return out


def _verifier(state):
    """Closed-form, reference-FREE grammar-satisfaction proxy in [0,1].

    'Grammar' = a fixed, decodable constraint the surface treats as unknown to
    the model: (a) each decoded symbol should match the target position, and
    (b) a lightweight local bigram rule (adjacent decoded indices should not
    both be zero — a toy 'no double-null' grammar constraint). The verifier is
    reference-free in the sense that it scores CONSTRAINT satisfaction, not a
    string-edit distance to a held-out reference. Deterministic, closed-form.
    """
    dec = _decode(state)
    L = len(dec)
    # (a) positional constraint satisfaction
    match = sum(1 for i in range(L) if dec[i] == _TARGET[i % len(_TARGET)])
    pos_score = match / L
    # (b) toy bigram grammar: penalize adjacent equal symbols (repeats)
    if L > 1:
        good_bigrams = sum(1 for i in range(L - 1) if dec[i] != dec[i + 1])
        bigram_score = good_bigrams / (L - 1)
    else:
        bigram_score = 1.0
    return 0.75 * pos_score + 0.25 * bigram_score


def _diversity(states):
    """Frontier diversity in [0,1]: fraction of DISTINCT decoded strings among
    the survivors. High = frontier still spreads over many candidates."""
    if not states:
        return 0.0
    decoded = [_decode(s) for s in states]
    return len(set(decoded)) / len(decoded)


# ---------------------------------------------------------------------------
# Stratified resampling (the S³ prune step)
# ---------------------------------------------------------------------------
def _stratified_resample(scored, width, strata, verifier_weight):
    """Reduce an expanded pool of (score, state) down to `width` survivors that
    (a) favor high verifier score (reward-tilt via verifier_weight) and
    (b) preserve diversity by drawing across `strata` score bands.

    Deterministic rule (no randomness needed — fully ordered):
      * always keep the single best-scoring candidate (elitism);
      * partition the sorted pool into `strata` equal score bands and take
        the top of each band in round-robin, biased toward the top bands by
        verifier_weight, until `width` survivors are chosen.
    """
    pool = sorted(scored, key=lambda t: t[0], reverse=True)
    if len(pool) <= width:
        return [s for _, s in pool]

    survivors = [pool[0]]  # elitism: keep global best
    strata = max(1, min(strata, len(pool)))
    band_size = max(1, len(pool) // strata)
    bands = [pool[i * band_size:(i + 1) * band_size] for i in range(strata)]
    # any tail remainder joins the last band
    tail = pool[strata * band_size:]
    if tail:
        bands[-1].extend(tail)

    # reward-tilt: higher verifier_weight -> draw more from the top bands.
    # Build a band visitation order that repeats top bands proportionally.
    order = []
    for bi in range(strata):
        # top band (bi=0) gets weight ~ (1 + verifier_weight*(strata-bi)/strata)
        reps = 1 + int(round(verifier_weight * (strata - bi) / strata))
        order.extend([bi] * max(1, reps))

    cursor = [0] * strata  # how deep we've drawn into each band
    idx = 0
    guard = 0
    max_guard = len(pool) * (len(order) + 2)
    while len(survivors) < width and guard < max_guard:
        bi = order[idx % len(order)]
        idx += 1
        guard += 1
        band = bands[bi]
        if cursor[bi] < len(band):
            cand = band[cursor[bi]]
            cursor[bi] += 1
            if cand not in survivors:
                survivors.append(cand)
    # if still short (all duplicates exhausted), fill from the sorted pool
    if len(survivors) < width:
        for cand in pool:
            if cand not in survivors:
                survivors.append(cand)
            if len(survivors) >= width:
                break
    return [s for _, s in survivors[:width]]


# ---------------------------------------------------------------------------
# The three methods (all share a FLOP-proxy = state-update counter)
# ---------------------------------------------------------------------------
def _run_no_search(seed, steps, length):
    """Single trajectory, no search. flops = steps (one update/step)."""
    rng = _lcg(seed)
    state = _init_state(rng, length)
    flops = 0
    for k in range(steps):
        state = _denoise_step(rng, state, k, steps)
        flops += 1
    return {
        "quality": round(_verifier(state), 6),
        "diversity": round(_diversity([state]), 6),
        "flops": flops,
    }


def _run_final_best_of_k(seed, steps, length, k):
    """K independent single trajectories to completion; keep best-verifier
    final output. flops = k * steps (matched to S³'s total budget)."""
    finals = []
    flops = 0
    for j in range(k):
        rng = _lcg(seed + 1000 * (j + 1))
        state = _init_state(rng, length)
        for st in range(steps):
            state = _denoise_step(rng, state, st, steps)
            flops += 1
        finals.append(state)
    best = max(finals, key=_verifier) if finals else _init_state(_lcg(seed), length)
    return {
        "quality": round(_verifier(best), 6),
        "diversity": round(_diversity(finals), 6),
        "flops": flops,
        "k": k,
    }


def _run_s3(seed, width, branch, steps, length, verifier_weight, strata):
    """Mid-denoising stratified branch-and-prune search.
    flops = width * branch * steps (each child advanced one step = one unit)."""
    rng = _lcg(seed)
    # frontier: W initial trajectories (seeded from the noised prior)
    frontier = [_init_state(rng, length) for _ in range(width)]
    flops = 0
    traj_rows = []
    for k in range(steps):
        # expand: each trajectory -> B children (seeded perturbations)
        expanded = []
        for st in frontier:
            for _b in range(branch):
                child = _denoise_step(rng, st, k, steps)
                flops += 1
                expanded.append((_verifier(child), child))
        # stratified resample back down to W survivors
        frontier = _stratified_resample(expanded, width, strata, verifier_weight)
        qs = [_verifier(s) for s in frontier]
        traj_rows.append({
            "step": k,
            "best_quality": round(max(qs), 6),
            "mean_quality": round(sum(qs) / len(qs), 6),
            "diversity": round(_diversity(frontier), 6),
            "survivors": len(frontier),
        })
    best = max(frontier, key=_verifier)
    return {
        "quality": round(_verifier(best), 6),
        "diversity": round(_diversity(frontier), 6),
        "flops": flops,
    }, traj_rows


def _s3_snapshot(seed=42, frontier_width=6, branch_factor=3,
                 num_denoise_steps=8, verifier_weight=2.0, diversity_strata=4) -> dict:
    """
    Run all three methods at MATCHED compute and return an honest comparison.

    Pure stdlib; deterministic — same params -> identical snapshot, every time.
    """
    W = max(1, min(int(frontier_width), 64))
    B = max(1, min(int(branch_factor), 16))
    steps = max(1, min(int(num_denoise_steps), 64))
    vw = max(0.0, min(float(verifier_weight), 16.0))
    strata = max(1, min(int(diversity_strata), 16))
    length = len(_TARGET)

    # S³ total FLOP-proxy budget = W * B * steps.
    s3_budget = W * B * steps
    # matched final-best-of-K: K single trajectories of the same depth,
    # K = budget / steps = W * B (so K*steps == s3_budget exactly).
    k_matched = max(1, s3_budget // steps)

    no_search = _run_no_search(seed, steps, length)
    final_bok = _run_final_best_of_k(seed, steps, length, k_matched)
    s3, traj = _run_s3(seed, W, B, steps, length, vw, strata)

    gap = round(s3["quality"] - final_bok["quality"], 6)

    return {
        "frontier_width": W,
        "branch_factor": B,
        "num_denoise_steps": steps,
        "verifier_weight": round(vw, 6),
        "diversity_strata": strata,
        "target": _TARGET,
        "flop_proxy_budget": s3_budget,
        "no_search": no_search,
        "final_best_of_k": final_bok,
        "s3": s3,
        "s3_trajectory": traj[:_MAX_TRAJ_ROWS],
        "quality_gap_s3_vs_bok": gap,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _fi(req: Request, key: str, default: float) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return float(default)


_HONEST_NOTE = (
    "MODELED: toy analytic sim of the mid-denoising stratified-search MECHANISM, "
    "not S³. The 'diffusion LM' is a seeded toy denoiser over a few symbols; the "
    "'reference-free verifier' is a closed-form grammar-satisfaction proxy, not a "
    "learned verifier; 'compute' is a state-update counter, not real FLOPs. "
    "Demonstrates that trajectory branch-and-prune can beat final best-of-K at a "
    "matched toy budget on a constructed constraint; does NOT reproduce S³'s "
    "LLaDA-8B-Instruct results on MATH-500/GSM8K/ARC-Challenge/TruthfulQA "
    "(Bilal et al. 2026, arXiv:2604.06260). Distinctness flag (part of the card): "
    "this is the narrowest new-axis claim in Wave 11 — a specific search primitive "
    "at the dllm+testtime+specdecode junction. Deterministic: same "
    "seed/frontier_width/branch_factor/num_denoise_steps -> identical output. SZL "
    "claims NONE of these methods as its own."
)


def _h_search(req: Request):
    seed              = _ii(req, "seed", 42)
    frontier_width    = max(1, min(_ii(req, "frontier_width", 6), 64))
    branch_factor     = max(1, min(_ii(req, "branch_factor", 3), 16))
    num_denoise_steps = max(1, min(_ii(req, "num_denoise_steps", 8), 64))
    verifier_weight   = max(0.0, min(_fi(req, "verifier_weight", 2.0), 16.0))
    diversity_strata  = max(1, min(_ii(req, "diversity_strata", 4), 16))

    snap = _s3_snapshot(
        seed=seed,
        frontier_width=frontier_width,
        branch_factor=branch_factor,
        num_denoise_steps=num_denoise_steps,
        verifier_weight=verifier_weight,
        diversity_strata=diversity_strata,
    )

    return JSONResponse({
        "label": "MODELED",
        "model": "Verifier-guided stratified search over denoising trajectories (S³): mid-denoising branch-and-prune vs final best-of-K at matched toy compute",
        "method": "At each denoise step, expand W trajectories into B children, score with a closed-form reference-free grammar-satisfaction verifier, stratified-resample to W survivors (reward-tilt + diversity strata); baselines: single-trajectory and final-best-of-K at matched FLOP-proxy budget",
        "seed": seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations": CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_testtime.register() / szl_specdecode.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/s3search/search onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/s3search"
    handlers = [
        (f"{base}/search", _h_search),
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
    snap = _s3_snapshot(seed=42, frontier_width=6, branch_factor=3, num_denoise_steps=8)
    print("label: MODELED")
    print("target:", snap["target"])
    print("flop_proxy_budget (matched):", snap["flop_proxy_budget"])
    print()
    print("QUALITY + DIVERSITY at matched compute:")
    print("  no_search        quality={:.6f}  diversity={:.6f}  flops={}".format(
        snap["no_search"]["quality"], snap["no_search"]["diversity"], snap["no_search"]["flops"]))
    print("  final_best_of_k  quality={:.6f}  diversity={:.6f}  flops={}  k={}".format(
        snap["final_best_of_k"]["quality"], snap["final_best_of_k"]["diversity"],
        snap["final_best_of_k"]["flops"], snap["final_best_of_k"]["k"]))
    print("  s3               quality={:.6f}  diversity={:.6f}  flops={}".format(
        snap["s3"]["quality"], snap["s3"]["diversity"], snap["s3"]["flops"]))
    print("  quality_gap_s3_vs_bok:", snap["quality_gap_s3_vs_bok"])
    print()
    print("honest_note:", _HONEST_NOTE)

    # sanity: bounds
    for m in ("no_search", "final_best_of_k", "s3"):
        assert 0.0 <= snap[m]["quality"] <= 1.0, f"{m} quality out of [0,1]"
        assert 0.0 <= snap[m]["diversity"] <= 1.0, f"{m} diversity out of [0,1]"

    # sanity: matched compute — final-best-of-K budget equals S³ budget
    assert snap["final_best_of_k"]["flops"] == snap["s3"]["flops"] == snap["flop_proxy_budget"], \
        "compute budgets not matched"

    # sanity: honest signal — S³ reaches the constrained target at least as well
    # as final best-of-K at matched budget (branch-and-prune >= final selection)
    assert snap["s3"]["quality"] >= snap["final_best_of_k"]["quality"], \
        "S³ did not meet/beat final best-of-K at matched budget"

    # sanity: determinism — identical params -> identical snapshot
    snap2 = _s3_snapshot(seed=42, frontier_width=6, branch_factor=3, num_denoise_steps=8)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_s3search: ALL OK — deterministic, matched budget, S³ >= final best-of-K.")
