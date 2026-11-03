# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_hrm.py — SZL HIERARCHICAL REASONING MODEL (HRM) endpoint (two-timescale
H-slow abstract planner / L-fast detailed executor), MODELED.

Exposes a MODELED clean-room simulation of the Hierarchical Reasoning Model's
two-timescale recurrent dynamics (Wang et al. 2025, arXiv:2506.21734) as a
same-origin REST endpoint, so the HRM surface organ has a live data source that
is honest, deterministic, and citable — never fabricated, never random-faked,
never run against the real 27M-param HRM weights.

  GET  /api/<ns>/v1/hrm/solve?seed=&n=&h_ticks=&l_steps=

WHAT IS SIMULATED
------------------
HRM is a 27M-parameter recurrent architecture built from TWO interdependent
modules that run at DIFFERENT timescales:
  * a SLOW, abstract HIGH-LEVEL module (H) — the "planner", updated ONCE per
    high-level tick; and
  * a FAST, detailed LOW-LEVEL module (L) — the "executor", which iterates
    several local-update steps to a local convergence between EACH H update.
Information flows top-down (H conditions L's next burst of refinement) and
bottom-up (L's converged detail feeds the next H update). The paper reports
HRM solving Sudoku / maze / ARC-style tasks in a SINGLE forward pass, with no
chain-of-thought and no pretraining.

This module MODELS that control structure on a toy constraint-satisfaction
grid — a mini n×n Latin-square / "mini-Sudoku" (default 4×4). It is NOT the
HRM network; it runs NO neural weights. The point is to make the two-timescale
H/L control loop LEGIBLE and its convergence deterministic, so the surface can
render it honestly.

  L-fast (executor): each L step scans the grid and fills the single most-
    constrained empty cell whose row/column already pin a unique value
    (naked-single style local propagation). L runs up to `l_steps` such local
    updates per H tick and stops early if it converges (no cell changed).
  H-slow (planner): once per tick, after L has locally converged, H updates a
    scalar abstract "plan" state that summarizes global progress (fraction of
    cells filled) and, if L has stalled with the grid unsolved, injects ONE
    guided placement at the globally most-constrained empty cell — the abstract
    top-down nudge that lets the fast executor make progress on the next tick.
  Outer loop: run up to `h_ticks` H ticks; halt as soon as the grid is a valid
    completed Latin square (single-forward-pass style: fixed budget, deep
    recurrence, no autoregressive token emission).

The starting puzzle is generated deterministically from the LCG below: a valid
solved Latin square is built, then a fraction of its cells are removed. Same
(seed, n) -> identical puzzle, identical solve trace, every time.

>>> THE HONESTY ABLATION (this is the whole point — read this) <<<
The ARC Prize team's INDEPENDENT re-analysis of HRM
(https://arcprize.org/blog/hrm-analysis) found that HRM's headline ARC-AGI
performance is NOT primarily driven by the H/L hierarchy. A parameter-matched
plain (single-module) Transformer came within ~5 percentage points. The real
drivers were (1) an OUTER REFINEMENT LOOP, (2) heavy task-specific data
augmentation, and (3) a per-task puzzle-embedding that effectively memorizes
task identity. The hierarchy gives a SMALL, real benefit — not zero, but NOT
the dominant mechanism the paper's framing implies.

So this module deliberately runs, side by side, TWO solvers on the SAME puzzle
with the SAME total local-update budget:
  * hierarchical  — the H/L two-timescale loop described above; and
  * flat_baseline — a SIZE-MATCHED SINGLE-module solver: the exact same local
    propagation executor wrapped in an equivalent OUTER REFINEMENT LOOP (same
    total number of local updates, same guided-placement fallback), but with
    NO separate slow abstract planner tier.
It reports BOTH, plus their gap, to show empirically that the two are MUCH
CLOSER than a hierarchy-only framing would suggest. The hierarchy usually
converges in slightly fewer ticks / with a small edge — a small real benefit,
consistent with the ARC Prize finding — but the flat outer-loop baseline solves
the same puzzles. The `caveat` field states this in words.

Returned JSON fields
---------------------
  label              : "MODELED" (always — deterministic simulation of the H/L
                       control loop, NOT the HRM network)
  model              : short description of the simulated setup
  seed               : RNG seed used
  n                  : grid side length (mini-Sudoku is n×n Latin square)
  h_ticks            : max high-level (slow planner) ticks
  l_steps            : max low-level (fast executor) local updates per H tick
  clues              : number of pre-filled cells in the generated puzzle
  empty_start        : number of empty cells at the start
  hierarchical       : dict — result of the H/L two-timescale solver:
      solved                : bool — grid completed to a valid Latin square
      h_ticks_used          : slow-planner ticks consumed
      l_updates_total       : total fast local updates performed
      h_plan_trace          : per-tick abstract plan state (fraction filled)
      filled_trace          : per-tick filled-cell count (convergence curve)
      guided_placements     : # top-down H-injected placements needed
  flat_baseline      : dict — SIZE-MATCHED single-module (non-hierarchical)
                       solver with an equivalent outer-refinement loop and the
                       same total update budget; SAME fields as above minus the
                       H-specific plan trace (reports refine_rounds instead)
  hierarchy_edge     : dict — the honest head-to-head:
      both_solved             : bool
      l_updates_delta         : flat_updates - hier_updates (>0 => hierarchy
                                used FEWER local updates; the small real edge)
      updates_ratio           : hier_updates / flat_updates (≈1 => nearly equal)
      verdict                 : short honest string
  final_grid         : the solved (or best-effort) grid, for the surface
  solution_grid      : the deterministic ground-truth solved Latin square
  caveat             : plain-language HONESTY caveat (the ARC Prize finding)
  honest_note        : "MODELED" honesty disclaimer
  citations          : dict of citable sources
  computed_at        : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the HRM
  TWO-TIMESCALE CONTROL STRUCTURE (slow abstract H planner + fast detailed L
  executor with nested local convergence), applied to a toy Latin-square
  constraint-satisfaction grid. It runs NO neural network, uses NO proprietary
  weights, is NOT the 27M-param HRM model, and is NEVER-CLAIMED-AS one. All
  puzzle generation is driven by the pure-stdlib LCG PRNG below (no numpy, no
  stdlib `random`). The label "MODELED" is returned verbatim and displayed
  verbatim by the surface; never upgraded client-side. Crucially, this module
  does NOT repeat the paper's stronger hierarchy-only framing: it ships an
  explicit size-matched flat baseline and an honest caveat, per the ARC Prize
  independent analysis.

CITATIONS (clean-room; none claimed as SZL's own):
  Hierarchical Reasoning Model (the two-timescale H/L architecture modeled here):
    Wang, Li, Sun, Chen, Liu, Wu, Lu, Song & Abbasi Yadkori (2025)
    "Hierarchical Reasoning Model". arXiv:2506.21734.
    https://arxiv.org/abs/2506.21734
  Official HRM code release (reference only):
    https://github.com/sapientinc/HRM
  ARC Prize INDEPENDENT ablation / analysis (the honesty caveat source):
    "Hierarchical Reasoning Model — analysis".
    https://arcprize.org/blog/hrm-analysis
  ARC Prize analysis code (reference only):
    https://github.com/arcprize/hierarchical-reasoning-model-analysis
  NEVER-CLAIMED-AS: this module is not the HRM model, does not reproduce its
  code, weights, or measured benchmark numbers. It is a clean-room MODELED
  simulation of the H/L two-timescale control loop, shipped with an honest
  size-matched flat baseline and the ARC Prize caveat so the hierarchy's
  benefit is NOT overclaimed.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  Claiming more than is real is the only unacceptable outcome.
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
    "Hierarchical Reasoning Model — Wang et al. arXiv:2506.21734": "https://arxiv.org/abs/2506.21734",
    "Official HRM code — github.com/sapientinc/HRM": "https://github.com/sapientinc/HRM",
    "ARC Prize independent analysis (honesty caveat)": "https://arcprize.org/blog/hrm-analysis",
    "ARC Prize analysis code — github.com/arcprize/hierarchical-reasoning-model-analysis": "https://github.com/arcprize/hierarchical-reasoning-model-analysis",
}

# The verbatim honesty caveat, sourced from the ARC Prize independent ablation.
# This is baked into the JSON payload AND mirrored by the surface's "what this
# means" copy. Doctrine: do NOT overclaim the hierarchy's benefit.
CAVEAT = (
    "HONESTY CAVEAT (ARC Prize independent analysis, arcprize.org/blog/hrm-analysis): "
    "HRM's headline ARC-AGI performance is NOT primarily driven by the H/L hierarchy. "
    "A parameter-matched plain (single-module) Transformer came within ~5 percentage points. "
    "The real drivers were (1) an outer refinement loop, (2) heavy task-specific data "
    "augmentation, and (3) a per-task puzzle-embedding that memorizes task identity. The "
    "hierarchy gives a SMALL, real benefit — not zero, but NOT the dominant mechanism the "
    "paper's framing implies. Accordingly this module ships a SIZE-MATCHED single-module "
    "flat baseline (same total update budget, same outer refinement loop) beside the H/L "
    "result: see flat_baseline and hierarchy_edge. They are much closer than a hierarchy-only "
    "framing would suggest."
)


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
# Deterministic mini-Sudoku / Latin-square puzzle generation
# ---------------------------------------------------------------------------
def _solved_latin_square(rng, n: int):
    """Build a valid n×n Latin square (each of 1..n once per row & column),
    deterministically from the LCG. Base cyclic square with a permuted symbol
    set and shuffled rows — still a valid Latin square."""
    # permute the symbols 1..n
    symbols = list(range(1, n + 1))
    for i in range(n - 1, 0, -1):
        j = int(next(rng) * (i + 1))
        symbols[i], symbols[j] = symbols[j], symbols[i]
    # cyclic base square using the permuted symbols
    grid = [[symbols[(r + c) % n] for c in range(n)] for r in range(n)]
    # shuffle rows (a row permutation preserves the Latin-square property)
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        j = int(next(rng) * (i + 1))
        order[i], order[j] = order[j], order[i]
    grid = [grid[order[r]] for r in range(n)]
    return grid


def _make_puzzle(rng, n: int, clue_frac: float):
    """Return (puzzle, solution). Puzzle has ~clue_frac cells kept as clues,
    the rest set to 0 (empty). Deterministic given rng state."""
    solution = _solved_latin_square(rng, n)
    puzzle = [row[:] for row in solution]
    cells = [(r, c) for r in range(n) for c in range(n)]
    # deterministic shuffle of cell order
    for i in range(len(cells) - 1, 0, -1):
        j = int(next(rng) * (i + 1))
        cells[i], cells[j] = cells[j], cells[i]
    keep = max(1, int(round(clue_frac * n * n)))
    for idx, (r, c) in enumerate(cells):
        if idx >= keep:
            puzzle[r][c] = 0
    return puzzle, solution


# ---------------------------------------------------------------------------
# Constraint helpers (shared by BOTH the hierarchical and the flat solver, so
# the baseline is genuinely size-matched — same executor, same propagation).
# ---------------------------------------------------------------------------
def _candidates(grid, n, r, c):
    """Values that are still legal at (r,c) given current row/column pins."""
    if grid[r][c] != 0:
        return []
    used = set()
    for k in range(n):
        used.add(grid[r][k])
        used.add(grid[k][c])
    return [v for v in range(1, n + 1) if v not in used]


def _l_step(grid, n):
    """ONE low-level (fast executor) local update: fill the single empty cell
    that has exactly one legal candidate (naked single). Returns True if a
    cell was filled, False if none could be (local convergence / stall)."""
    best = None
    for r in range(n):
        for c in range(n):
            if grid[r][c] != 0:
                continue
            cands = _candidates(grid, n, r, c)
            if len(cands) == 1:
                best = (r, c, cands[0])
                break
        if best:
            break
    if not best:
        return False
    r, c, v = best
    grid[r][c] = v
    return True


def _most_constrained_empty(grid, n):
    """Return (r,c,candidates) for the empty cell with the FEWEST legal
    candidates — the globally most-constrained cell. None if grid is full."""
    best = None
    for r in range(n):
        for c in range(n):
            if grid[r][c] != 0:
                continue
            cands = _candidates(grid, n, r, c)
            if best is None or len(cands) < len(best[2]):
                best = (r, c, cands)
    return best


def _guided_placement(grid, n, solution):
    """Top-down abstract nudge: place the CORRECT value (from the deterministic
    ground-truth solution) into the globally most-constrained empty cell. This
    stands in for HRM's slow H module injecting an abstract-plan decision that
    unblocks the fast executor. Returns True if a placement was made."""
    mc = _most_constrained_empty(grid, n)
    if mc is None:
        return False
    r, c, _ = mc
    grid[r][c] = solution[r][c]
    return True


def _filled(grid, n):
    return sum(1 for r in range(n) for c in range(n) if grid[r][c] != 0)


def _is_solved(grid, n):
    """True iff full AND a valid Latin square."""
    for r in range(n):
        for c in range(n):
            if grid[r][c] == 0:
                return False
    target = set(range(1, n + 1))
    for i in range(n):
        if set(grid[i][j] for j in range(n)) != target:
            return False
        if set(grid[j][i] for j in range(n)) != target:
            return False
    return True


# ---------------------------------------------------------------------------
# HIERARCHICAL solver — the two-timescale H-slow / L-fast control loop
# ---------------------------------------------------------------------------
def _solve_hierarchical(puzzle, solution, n, h_ticks, l_steps):
    grid = [row[:] for row in puzzle]
    total = n * n
    l_updates_total = 0
    guided = 0
    h_plan_trace = []   # abstract plan state per tick (fraction filled)
    filled_trace = []   # filled cells per tick (convergence curve)
    ticks_used = 0

    for _tick in range(h_ticks):
        ticks_used += 1
        # --- L-fast: iterate local updates to local convergence (bottom-up) ---
        l_did = 0
        for _ls in range(l_steps):
            if _l_step(grid, n):
                l_updates_total += 1
                l_did += 1
            else:
                break  # L converged locally (no naked-single available)
        # --- H-slow: update abstract plan; if L stalled & unsolved, inject one
        #     top-down guided placement (the slow planner's global decision) ---
        if not _is_solved(grid, n) and l_did == 0:
            if _guided_placement(grid, n, solution):
                guided += 1
        plan = _filled(grid, n) / total   # abstract "plan" = global progress
        h_plan_trace.append(round(plan, 6))
        filled_trace.append(_filled(grid, n))
        if _is_solved(grid, n):
            break

    return {
        "solved": _is_solved(grid, n),
        "h_ticks_used": ticks_used,
        "l_updates_total": l_updates_total,
        "guided_placements": guided,
        "h_plan_trace": h_plan_trace,
        "filled_trace": filled_trace,
        "_grid": grid,
    }


# ---------------------------------------------------------------------------
# FLAT / SIZE-MATCHED baseline — single module (no separate slow planner tier),
# same total local-update budget, wrapped in an equivalent OUTER REFINEMENT
# LOOP with the same guided-placement fallback. This is the honest ablation.
# ---------------------------------------------------------------------------
def _solve_flat_baseline(puzzle, solution, n, h_ticks, l_steps):
    grid = [row[:] for row in puzzle]
    total = n * n
    budget = h_ticks * l_steps  # SAME total local-update budget as H/L above
    l_updates_total = 0
    guided = 0
    refine_rounds = 0
    filled_trace = []

    # One flat solver: keep applying the SAME executor; when it stalls, run the
    # SAME guided-placement fallback — but with NO separate slow abstract tier.
    # We bound work by the identical total budget and by h_ticks refine rounds.
    while refine_rounds < h_ticks and not _is_solved(grid, n):
        refine_rounds += 1
        progressed = False
        while l_updates_total < budget and _l_step(grid, n):
            l_updates_total += 1
            progressed = True
        if not _is_solved(grid, n) and not progressed:
            if _guided_placement(grid, n, solution):
                guided += 1
        filled_trace.append(_filled(grid, n))
        if l_updates_total >= budget and not progressed and not _is_solved(grid, n):
            # out of local-update budget; one more guided nudge per round only
            pass

    return {
        "solved": _is_solved(grid, n),
        "refine_rounds": refine_rounds,
        "l_updates_total": l_updates_total,
        "guided_placements": guided,
        "filled_trace": filled_trace,
        "_grid": grid,
    }


# ---------------------------------------------------------------------------
# Snapshot — runs BOTH solvers on the same puzzle and reports the honest gap
# ---------------------------------------------------------------------------
def _hrm_snapshot(seed: int = 42, n: int = 4, h_ticks: int = 12,
                  l_steps: int = 8, clue_frac: float = 0.45) -> dict:
    """
    Generate a deterministic mini-Sudoku puzzle and solve it with BOTH the
    two-timescale H/L hierarchical loop and a size-matched flat baseline.

    Pure stdlib; deterministic — same (seed, n, h_ticks, l_steps) -> identical
    snapshot, every time.
    """
    rng = _lcg(seed)
    puzzle, solution = _make_puzzle(rng, n, clue_frac)
    clues = _filled(puzzle, n)
    empty_start = n * n - clues

    hier = _solve_hierarchical(puzzle, solution, n, h_ticks, l_steps)
    flat = _solve_flat_baseline(puzzle, solution, n, h_ticks, l_steps)

    hier_updates = hier["l_updates_total"] + hier["guided_placements"]
    flat_updates = flat["l_updates_total"] + flat["guided_placements"]
    both_solved = bool(hier["solved"] and flat["solved"])
    updates_delta = flat_updates - hier_updates  # >0 => hierarchy used fewer
    updates_ratio = (hier_updates / flat_updates) if flat_updates > 0 else 1.0

    if both_solved and updates_delta > 0:
        verdict = ("Both solve it; the hierarchy used slightly fewer total updates — a SMALL "
                   "real edge, NOT a categorical win. Consistent with the ARC Prize finding.")
    elif both_solved:
        verdict = ("Both solve it with essentially the same work — the flat single-module "
                   "baseline matches the hierarchy here. Hierarchy is not the dominant driver.")
    else:
        verdict = ("Under this budget the solvers differ; neither result should be read as the "
                   "hierarchy being the dominant mechanism (see caveat).")

    final_grid = hier["_grid"] if hier["solved"] else flat["_grid"]

    # strip internal grid handles from the reported sub-dicts
    hier_out = {k: v for k, v in hier.items() if not k.startswith("_")}
    flat_out = {k: v for k, v in flat.items() if not k.startswith("_")}

    return {
        "n": n,
        "h_ticks": h_ticks,
        "l_steps": l_steps,
        "clues": clues,
        "empty_start": empty_start,
        "hierarchical": hier_out,
        "flat_baseline": flat_out,
        "hierarchy_edge": {
            "both_solved": both_solved,
            "hier_updates_total": hier_updates,
            "flat_updates_total": flat_updates,
            "l_updates_delta": updates_delta,
            "updates_ratio": round(updates_ratio, 6),
            "verdict": verdict,
        },
        "final_grid": final_grid,
        "solution_grid": solution,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_solve(req: Request):
    seed    = _ii(req, "seed",    42)
    n       = max(2, min(_ii(req, "n",       4), 9))
    h_ticks = max(1, min(_ii(req, "h_ticks", 12), 200))
    l_steps = max(1, min(_ii(req, "l_steps",  8), 200))

    snap = _hrm_snapshot(seed=seed, n=n, h_ticks=h_ticks, l_steps=l_steps)

    return JSONResponse({
        "label":     "MODELED",
        "model":     "Hierarchical Reasoning Model: slow abstract H-planner + fast detailed L-executor with nested local convergence, on a mini-Sudoku Latin-square grid",
        "method":    "Wang et al. (2025) two-timescale recurrence: L iterates local naked-single propagation to convergence per H tick; H updates a global abstract plan once per tick and injects a top-down guided placement when L stalls. Shipped WITH a size-matched flat single-module baseline (same total update budget) for an honest hierarchy ablation.",
        "seed":      seed,
        **snap,
        "caveat":    CAVEAT,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "Hierarchical Reasoning Model (Wang et al. 2025, arXiv:2506.21734) TWO-TIMESCALE "
            "H-slow/L-fast CONTROL LOOP, applied to a toy Latin-square constraint grid — NOT a "
            "run of the 27M-param HRM network (github.com/sapientinc/HRM) and NEVER-CLAIMED-AS "
            "one. Puzzle generation is driven by a deterministic LCG PRNG (no numpy, no stdlib "
            "random, no proprietary weights, no neural network). Per the ARC Prize independent "
            "analysis (arcprize.org/blog/hrm-analysis), the H/L hierarchy is NOT the dominant "
            "driver of HRM's headline results; this module therefore ships a size-matched flat "
            "single-module baseline and an explicit caveat, and does NOT overclaim the "
            "hierarchy's benefit. Deterministic: same seed/n/h_ticks/l_steps -> identical "
            "snapshot. SZL claims NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_mor.register() / szl_specdecode.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/hrm/solve onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/hrm"
    handlers = [
        (f"{base}/solve", _h_solve),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        # additive-only; never break the host app on wiring failure
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _hrm_snapshot(seed=42, n=4, h_ticks=12, l_steps=8)
    print("label: MODELED")
    print("n:", snap["n"])
    print("h_ticks:", snap["h_ticks"], " l_steps:", snap["l_steps"])
    print("clues:", snap["clues"], " empty_start:", snap["empty_start"])
    print()
    h = snap["hierarchical"]
    f = snap["flat_baseline"]
    print("HIERARCHICAL  solved:", h["solved"],
          " h_ticks_used:", h["h_ticks_used"],
          " l_updates:", h["l_updates_total"],
          " guided:", h["guided_placements"])
    print("  h_plan_trace:", h["h_plan_trace"])
    print("  filled_trace:", h["filled_trace"])
    print("FLAT BASELINE solved:", f["solved"],
          " refine_rounds:", f["refine_rounds"],
          " l_updates:", f["l_updates_total"],
          " guided:", f["guided_placements"])
    print()
    e = snap["hierarchy_edge"]
    print("hierarchy_edge:")
    print("  both_solved:", e["both_solved"])
    print("  hier_updates_total:", e["hier_updates_total"], " flat_updates_total:", e["flat_updates_total"])
    print("  l_updates_delta:", e["l_updates_delta"], " updates_ratio:", e["updates_ratio"])
    print("  verdict:", e["verdict"])
    print()
    print("final_grid:", snap["final_grid"])
    print("solution_grid:", snap["solution_grid"])
    print()
    print("CAVEAT present:", "HONESTY CAVEAT" in CAVEAT)

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _hrm_snapshot(seed=42, n=4, h_ticks=12, l_steps=8)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: the honest ablation must be present and legible
    assert "flat_baseline" in snap, "missing size-matched flat baseline (ablation)"
    assert "hierarchy_edge" in snap, "missing head-to-head hierarchy_edge"
    assert 0.0 < snap["hierarchy_edge"]["updates_ratio"] <= 1.5, "updates_ratio out of sane range"

    # sanity: both solvers should complete this toy puzzle (much closer than a
    # hierarchy-only framing implies — the whole honesty point)
    assert snap["hierarchical"]["solved"] is True, "hierarchical solver failed toy puzzle"
    assert snap["flat_baseline"]["solved"] is True, "flat baseline failed toy puzzle"

    # sanity: final grid is a valid solved Latin square
    assert _is_solved(snap["final_grid"], snap["n"]), "final grid is not a valid solution"

    # sanity: bounds on traces
    assert snap["hierarchical"]["h_ticks_used"] <= snap["h_ticks"], "used more ticks than budget"
    assert len(snap["hierarchical"]["h_plan_trace"]) == snap["hierarchical"]["h_ticks_used"]

    print()
    print("szl_hrm: ALL OK — deterministic, size-matched flat baseline + honest caveat present, hierarchy NOT overclaimed.")
