# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_dla.py — SZL DYNAMIC LINEAR ATTENTION (DLA) endpoint, MODELED.

Exposes a MODELED, deterministic, pure-stdlib re-implementation of the
DYNAMIC LINEAR ATTENTION multi-state memory MECHANISM (Xin Wang, Hui Shen,
Boyuan Zheng, Xueshen Liu, Minkyoung Cho, Zhongwei Wan, Zesen Zhao, Zhuoqing
Mao, Shen Yan, Mi Zhang, "Dynamic Linear Attention", arXiv:2606.10650,
2026-06-09) applied to a small SYNTHETIC token sequence drawn from the
pure-stdlib LCG PRNG below — so the DLA organ has a live data source that is
honest, deterministic, and citable — never a trained model, never a real
linear-attention forward pass, never a GPU kernel.

  GET  /api/<ns>/v1/dla/attention?seed=&L=&capacity=&d=

WHAT IS MODELED
---------------
MULTI-STATE LINEAR ATTENTION organizes the running memory of a sequence as a
set of STATES, each a summary (mean) of a contiguous block of tokens. When the
number of states would exceed a fixed CAPACITY bound, adjacent states must be
MERGED. The paper's central claim is that HOW you choose which states to merge
matters enormously for long contexts:

  FIXED-policy multi-state linear attention merges states by a fixed,
  importance-BLIND policy (here: uniform chronological chunking — split the
  sequence into `capacity` equal-width blocks and average each block). This
  irreversibly obscures the few CRITICAL "transition" tokens by blending them
  into large stable blocks, causing error to ACCUMULATE over the sequence.

  DLA replaces the fixed policy with two mechanisms:
    (i)  INFORMATION-AWARE DYNAMIC STATE MERGING — token-level information
         variation (here: |token[t] - token[t-1]|, the L2 change from the
         previous token) sets the state boundaries. High-variation tokens
         (semantic transitions) START new states and are preserved at high
         resolution; low-variation runs (stable regions) are aggressively
         summarized into single states.
    (ii) CAPACITY-BOUNDED MEMORY MODELING — the state cache is held to the
         SAME fixed `capacity` as the fixed policy by SELECTIVELY merging the
         two ADJACENT states whose combined information loss is smallest
         (the lowest-variation neighbours), repeating until |states| == cap.

This module builds a synthetic sequence X (L x d) that is mostly STABLE (small
drift) with a few high-importance TRANSITION tokens (large jumps) injected at
deterministic positions, runs BOTH the fixed-policy and the DLA merging on the
SAME sequence UNDER THE SAME capacity bound, RECONSTRUCTS each token from its
assigned state's summary, and MEASURES:
  * states_fixed vs states_dla — both == capacity (bound honoured), reported
    so the surface can show the bound is respected by both;
  * cumulative reconstruction error over the sequence for each policy
    (err_accum_fixed > err_accum_dla — DLA accumulates less);
  * info_preserved_pct — for tokens in a window AROUND the transitions, how
    much of the transition information survives each policy's summarization
    (100 * (1 - err_transition/energy_transition)); DLA higher.

Pure stdlib; deterministic — same (seed, L, capacity, d) -> identical snapshot.

Returned JSON fields
--------------------
  label                 : "MODELED" (always — clean-room mechanism reproduction,
                          NOT a trained linear-attention model)
  model                 : short description of the modeled setup
  method                : one-line description of the two merging policies
  seed                  : RNG seed used
  L, d, capacity        : sequence length, token dim, state-cache capacity bound
  n_transitions         : number of injected high-importance transition tokens
  transition_positions  : token indices of the injected transitions
  states_fixed          : number of states after fixed-policy merging (== cap)
  states_dla            : number of states after DLA merging (== cap)
  err_accum_fixed       : cumulative reconstruction error (fixed policy)
  err_accum_dla         : cumulative reconstruction error (DLA)
  err_reduction_pct     : 100*(fixed-dla)/fixed  (DLA lowers accumulated error)
  info_preserved_fixed  : % of transition information preserved (fixed policy)
  info_preserved_dla    : % of transition information preserved (DLA)
  err_curve_fixed       : per-token running cumulative error (fixed) — head
  err_curve_dla         : per-token running cumulative error (DLA) — head
  boundaries_fixed      : state boundary token-indices (fixed policy)
  boundaries_dla        : state boundary token-indices (DLA)
  info_var_head         : per-token information-variation signal — head
  honest_note           : plain-language honesty disclaimer (see below)
  citations             : dict of citable sources (verified real)
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib TOY demo of the DLA dynamic-state-merging
  MECHANISM (no numpy, no stdlib `random`, no trained model, no real linear-
  attention forward pass, no GPU kernel). A synthetic mostly-stable sequence
  with a few injected high-importance transition tokens is summarized under a
  fixed capacity bound by (a) a fixed importance-blind chunking policy and (b)
  DLA's information-aware dynamic merging; the reconstruction error accumulation
  and transition information-preservation are MEASURED and compared. It does NOT
  reproduce the paper's pre-training results across the 16 datasets / three
  categories on real linear-attention backbones — those are CLAIMS about REAL
  trained models that the estate does NOT independently verify. The label
  "MODELED" is returned verbatim and displayed verbatim by the surface; never
  upgraded.

CITATIONS (clean-room; none claimed as SZL's own; VERIFIED real):
  Dynamic Linear Attention — Xin Wang, Hui Shen, Boyuan Zheng, Xueshen Liu,
    Minkyoung Cho, Zhongwei Wan, Zesen Zhao, Zhuoqing Mao, Shen Yan, Mi Zhang.
    arXiv:2606.10650  https://arxiv.org/abs/2606.10650
  NEVER-CLAIMED-AS: this module is not the paper's released code, does not
  reproduce its pre-training / 16-dataset numbers, trains no model, and runs no
  real linear-attention kernel. It is a clean-room MODELED reproduction of the
  information-aware dynamic state-merging + capacity-bounded-memory MECHANISM.

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
    "Dynamic Linear Attention — Xin Wang, Hui Shen, Boyuan Zheng, Xueshen Liu, Minkyoung Cho, Zhongwei Wan, Zesen Zhao, Zhuoqing Mao, Shen Yan, Mi Zhang. arXiv:2606.10650": "https://arxiv.org/abs/2606.10650",
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
# Tiny pure-stdlib vector helpers (NO numpy)
# ---------------------------------------------------------------------------
def _l2(a) -> float:
    return math.sqrt(sum(x * x for x in a))


def _dist(a, b) -> float:
    return math.sqrt(sum((x - y) * (x - y) for x, y in zip(a, b)))


def _mean_rows(rows):
    """Column-wise mean of a list of equal-length vectors (state summary)."""
    n = len(rows)
    if n == 0:
        return []
    d = len(rows[0])
    acc = [0.0] * d
    for r in rows:
        for j in range(d):
            acc[j] += r[j]
    return [v / n for v in acc]


# ---------------------------------------------------------------------------
# Synthetic sequence: mostly-stable regions + a few high-importance transitions
# ---------------------------------------------------------------------------
def _build_sequence(rng, L: int, d: int, n_transitions: int):
    """
    Build X (L x d): a slowly-drifting stable baseline with a few large
    high-importance TRANSITION jumps injected at deterministic, evenly spaced
    positions. Returns (X, transition_positions).
    """
    # transitions placed at evenly spaced interior positions (deterministic)
    positions = []
    if n_transitions > 0:
        step = L / (n_transitions + 1)
        for k in range(1, n_transitions + 1):
            p = int(round(k * step))
            p = max(1, min(L - 1, p))
            if p not in positions:
                positions.append(p)
    posset = set(positions)

    X = []
    cur = [_gauss(rng) * 0.3 for _ in range(d)]  # baseline level
    for t in range(L):
        if t in posset:
            # high-importance transition: a large, sharp jump (new semantic level)
            jump = [_gauss(rng) * 2.4 for _ in range(d)]
            cur = [cur[j] + jump[j] for j in range(d)]
        else:
            # stable region: tiny random drift only
            drift = [_gauss(rng) * 0.06 for _ in range(d)]
            cur = [cur[j] + drift[j] for j in range(d)]
        X.append(list(cur))
    return X, positions


# ---------------------------------------------------------------------------
# Information-variation signal (token-level) — L2 change from previous token
# ---------------------------------------------------------------------------
def _info_variation(X):
    """v[t] = |X[t] - X[t-1]|  (v[0] = 0). Large at semantic transitions."""
    L = len(X)
    v = [0.0] * L
    for t in range(1, L):
        v[t] = _dist(X[t], X[t - 1])
    return v


# ---------------------------------------------------------------------------
# Merge policies -> boundaries (state = contiguous token block)
# Boundaries returned as the START index of each state; len == capacity.
# ---------------------------------------------------------------------------
def _fixed_boundaries(L: int, cap: int):
    """
    FIXED-policy (importance-blind): split the sequence into `cap` equal-width
    chronological chunks. Boundaries are evenly spaced regardless of where the
    critical transitions fall — so transitions get blended into big blocks.
    """
    cap = max(1, min(cap, L))
    bounds = sorted(set(int(round(k * L / cap)) for k in range(cap)))
    if bounds[0] != 0:
        bounds[0] = 0
        bounds = sorted(set(bounds))
    # ensure exactly `cap` states by padding/trimming deterministically
    while len(bounds) < cap:
        # insert a new boundary in the largest gap
        best_gap, best_at = -1, 1
        ext = bounds + [L]
        for i in range(len(bounds)):
            g = ext[i + 1] - ext[i]
            if g > best_gap:
                best_gap, best_at = g, ext[i] + g // 2
        if best_at in bounds or best_at <= 0 or best_at >= L:
            break
        bounds.append(best_at)
        bounds = sorted(set(bounds))
    return bounds[:cap]


def _dla_boundaries(v, cap: int):
    """
    DLA information-aware dynamic state merging + capacity-bounded memory.

    Start with a boundary at EVERY token (finest resolution). Then repeatedly
    MERGE the adjacent state pair with the SMALLEST information loss — i.e.
    remove the boundary whose token has the LOWEST information-variation v[t]
    (a stable-region token). High-variation transition tokens keep their
    boundaries until last, so they stay at high resolution. Stop when the
    number of states equals the capacity bound `cap`. This preserves the few
    critical transitions while aggressively summarizing stable runs.
    """
    L = len(v)
    cap = max(1, min(cap, L))
    # every token starts its own state
    bounds = list(range(L))
    # candidate boundaries to drop are indices 1..L-1 (index 0 always stays);
    # priority = information variation at that boundary token (drop lowest first)
    # deterministic tie-break by index.
    while len(bounds) > cap:
        # find interior boundary (not index 0) with minimal v; tie -> lowest idx
        drop = None
        drop_key = None
        for b in bounds:
            if b == 0:
                continue
            key = (v[b], b)
            if drop_key is None or key < drop_key:
                drop_key = key
                drop = b
        if drop is None:
            break
        bounds.remove(drop)
    return sorted(bounds)


# ---------------------------------------------------------------------------
# Reconstruction from state summaries + error accumulation
# ---------------------------------------------------------------------------
def _assign(L: int, bounds):
    """Map each token index -> its state id (contiguous blocks from bounds)."""
    ext = sorted(bounds) + [L]
    state_of = [0] * L
    sid = 0
    for i in range(len(ext) - 1):
        for t in range(ext[i], ext[i + 1]):
            state_of[t] = sid
        sid += 1
    return state_of, sid


def _reconstruct_and_error(X, bounds):
    """
    Summarize each state as the MEAN of its tokens, reconstruct every token as
    its state's summary, and return (recon_err_per_token, cumulative_curve,
    total_err, n_states). Cumulative curve is the running sum of per-token L2
    reconstruction error along the sequence (error accumulation).
    """
    L = len(X)
    state_of, n_states = _assign(L, bounds)
    # state summaries (means)
    buckets = [[] for _ in range(n_states)]
    for t in range(L):
        buckets[state_of[t]].append(X[t])
    summaries = [_mean_rows(b) for b in buckets]
    per_tok = [0.0] * L
    cum = [0.0] * L
    run = 0.0
    for t in range(L):
        e = _dist(X[t], summaries[state_of[t]])
        per_tok[t] = e
        run += e
        cum[t] = run
    return per_tok, cum, run, n_states


def _info_preserved(X, per_tok, positions, window: int):
    """
    Around each transition (±window tokens), compute how much of the transition
    ENERGY survived summarization:
        preserved% = 100 * (1 - sum(err^2 in window) / sum(energy^2 in window))
    where energy is |X[t] - baseline_mean| (deviation of the windowed tokens
    from their own mean). Higher = the transition detail was better kept.
    """
    L = len(X)
    idxs = set()
    for p in positions:
        for t in range(max(0, p - window), min(L, p + window + 1)):
            idxs.add(t)
    idxs = sorted(idxs)
    if not idxs:
        return 100.0
    win_tokens = [X[t] for t in idxs]
    mean_win = _mean_rows(win_tokens)
    energy = sum(_dist(X[t], mean_win) ** 2 for t in idxs)
    err = sum(per_tok[t] ** 2 for t in idxs)
    if energy <= 1e-12:
        return 100.0
    pct = 100.0 * (1.0 - err / energy)
    if pct < 0.0:
        pct = 0.0
    if pct > 100.0:
        pct = 100.0
    return pct


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _dla_snapshot(seed: int = 42, L: int = 32, capacity: int = 8, d: int = 8) -> dict:
    """
    Deterministically build a synthetic mostly-stable sequence with a few
    high-importance transition tokens, summarize it under the SAME capacity
    bound by (a) fixed importance-blind chunking and (b) DLA information-aware
    dynamic merging, then MEASURE and compare reconstruction error accumulation
    and transition information preservation.

    Pure stdlib; deterministic — same (seed, L, capacity, d) -> identical snap.
    """
    rng = _lcg(seed)
    # number of injected transitions scales with capacity but stays small;
    # deterministic function of the capacity bound.
    n_transitions = max(2, min(capacity - 1, max(2, L // 8)))
    X, positions = _build_sequence(rng, L, d, n_transitions)
    v = _info_variation(X)

    b_fixed = _fixed_boundaries(L, capacity)
    b_dla = _dla_boundaries(v, capacity)

    per_fixed, cum_fixed, err_fixed, n_fixed = _reconstruct_and_error(X, b_fixed)
    per_dla, cum_dla, err_dla, n_dla = _reconstruct_and_error(X, b_dla)

    err_reduction_pct = (
        100.0 * (err_fixed - err_dla) / err_fixed if err_fixed > 1e-12 else 0.0
    )

    window = max(1, L // 16)
    info_fixed = _info_preserved(X, per_fixed, positions, window)
    info_dla = _info_preserved(X, per_dla, positions, window)

    cap_head = min(L, 16)

    return {
        "L": L,
        "d": d,
        "capacity": capacity,
        "n_transitions": n_transitions,
        "transition_positions": positions,
        "states_fixed": n_fixed,
        "states_dla": n_dla,
        "err_accum_fixed": round(err_fixed, 6),
        "err_accum_dla": round(err_dla, 6),
        "err_reduction_pct": round(err_reduction_pct, 6),
        "info_preserved_fixed": round(info_fixed, 6),
        "info_preserved_dla": round(info_dla, 6),
        "err_curve_fixed": [round(x, 6) for x in cum_fixed[:cap_head]],
        "err_curve_dla": [round(x, 6) for x in cum_dla[:cap_head]],
        "boundaries_fixed": b_fixed,
        "boundaries_dla": b_dla,
        "info_var_head": [round(x, 6) for x in v[:cap_head]],
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
    "MODELED: this is a clean-room, pure-stdlib TOY demo of the Dynamic Linear "
    "Attention (DLA) dynamic-state-merging MECHANISM (Xin Wang et al., 'Dynamic "
    "Linear Attention', arXiv:2606.10650), NOT a trained linear-attention model. "
    "A synthetic, mostly-stable token sequence with a few injected high-importance "
    "TRANSITION tokens is summarized as a set of multi-state memory summaries under "
    "a fixed CAPACITY bound by two policies: (a) a FIXED importance-blind policy "
    "(uniform chronological chunking into `capacity` equal blocks) and (b) DLA's "
    "INFORMATION-AWARE DYNAMIC STATE MERGING + CAPACITY-BOUNDED MEMORY (start at "
    "full resolution, repeatedly merge the adjacent states with the lowest token-"
    "level information variation, preserving semantic transitions and aggressively "
    "summarizing stable runs, until |states| == capacity). Both policies honour the "
    "SAME capacity bound (states_fixed == states_dla == capacity). The cumulative "
    "reconstruction ERROR ACCUMULATION (err_accum_fixed > err_accum_dla) and the "
    "transition INFO_PRESERVED_PCT (dla higher) are MEASURED on the synthetic input. "
    "This is a MECHANISM DEMO — it trains NOTHING and does NOT reproduce the paper's "
    "pre-training results across 16 datasets / three categories on real linear-"
    "attention backbones (those are CLAIMS about REAL trained models the estate does "
    "not verify). Pure stdlib, no numpy, no stdlib random, no GPU kernel. "
    "Deterministic: same seed/L/capacity/d -> identical snapshot. NEVER-CLAIMED-AS a "
    "production attention kernel. SZL claims NONE of these methods as its own."
)


def _h_attention(req: Request):
    seed     = _ii(req, "seed", 42)
    L        = max(8, min(_ii(req, "L", 32), 128))
    capacity = max(2, min(_ii(req, "capacity", 8), L))
    d        = max(2, min(_ii(req, "d", 8), 32))

    snap = _dla_snapshot(seed=seed, L=L, capacity=capacity, d=d)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Dynamic Linear Attention (DLA) — multi-state linear-attention memory summarized under a fixed capacity bound by FIXED importance-blind chunking vs DLA information-aware dynamic state merging, on a synthetic sequence with a few high-importance transition tokens amid stable regions",
        "method": "Fixed: uniform chronological chunking into `capacity` equal blocks (importance-blind). DLA: start at full resolution, repeatedly merge adjacent states with lowest token-level information variation |X[t]-X[t-1]| (Information-Aware Dynamic State Merging), bounded to the same `capacity` (Capacity-Bounded Memory). Reconstruct each token from its state mean; MEASURE cumulative error accumulation (fixed higher) and transition info_preserved_pct (DLA higher)",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_keyless.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/dla/attention onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/dla"
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
    snap = _dla_snapshot(seed=42, L=32, capacity=8, d=8)
    print("label: MODELED")
    print("L:", snap["L"], "d:", snap["d"], "capacity:", snap["capacity"])
    print("n_transitions:", snap["n_transitions"], "at", snap["transition_positions"])
    print("--- METRIC: STATE COUNT (both bounded to capacity) ---")
    print("states_fixed:", snap["states_fixed"])
    print("states_dla:  ", snap["states_dla"])
    print("--- METRIC: ERROR ACCUMULATION (fixed should be higher) ---")
    print("err_accum_fixed:", snap["err_accum_fixed"])
    print("err_accum_dla:  ", snap["err_accum_dla"])
    print("err_reduction_pct:", snap["err_reduction_pct"], "%")
    print("--- METRIC: INFO PRESERVED AROUND TRANSITIONS (DLA higher) ---")
    print("info_preserved_fixed:", snap["info_preserved_fixed"], "%")
    print("info_preserved_dla:  ", snap["info_preserved_dla"], "%")
    print("boundaries_fixed:", snap["boundaries_fixed"])
    print("boundaries_dla:  ", snap["boundaries_dla"])

    # sanity: both policies honour the SAME capacity bound
    assert snap["states_fixed"] == snap["capacity"], "fixed must use exactly capacity states"
    assert snap["states_dla"] == snap["capacity"], "dla must use exactly capacity states"

    # sanity: DLA accumulates LESS error than the fixed importance-blind policy
    assert snap["err_accum_dla"] <= snap["err_accum_fixed"], "DLA must not accumulate more error than fixed"
    assert snap["err_reduction_pct"] >= 0.0, "err_reduction_pct must be non-negative"

    # sanity: DLA preserves MORE transition information than fixed
    assert snap["info_preserved_dla"] >= snap["info_preserved_fixed"], "DLA must preserve >= transition info than fixed"
    assert 0.0 <= snap["info_preserved_fixed"] <= 100.0, "info% out of range"
    assert 0.0 <= snap["info_preserved_dla"] <= 100.0, "info% out of range"

    # sanity: cumulative error curves are non-decreasing (accumulation)
    for curve in (snap["err_curve_fixed"], snap["err_curve_dla"]):
        for i in range(1, len(curve)):
            assert curve[i] >= curve[i - 1] - 1e-9, "error curve must be non-decreasing"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _dla_snapshot(seed=42, L=32, capacity=8, d=8)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_dla: ALL OK — same capacity bound, DLA lowers error accumulation & preserves more transition info, deterministic.")
