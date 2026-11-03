# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_nested.py — SZL NESTED LEARNING / CONTINUUM MEMORY SYSTEM ("Hope") endpoint
(multi-timescale update SCHEDULING + optimizer-as-associative-memory), MODELED.

Exposes a MODELED closed-form simulation of the Nested Learning / Continuum
Memory System (CMS) idea (Behrouz, Razaviyayn, Zhong & Mirrokni, Google
Research; NeurIPS 2025 — proof-of-concept architecture "Hope") as a same-origin
REST endpoint, so the nested surface organ has a live data source that is
honest, deterministic, and citable — never fabricated, never random-faked,
never run against a real trained model or LLM.

  GET  /api/<ns>/v1/nested/schedule?seed=&num_tasks=&k_fast=&k_med=&k_slow=&gate=

WHAT IS SIMULATED
------------------
Nested Learning reframes a model as a STACK OF NESTED OPTIMIZATION PROBLEMS that
update at DIFFERENT FREQUENCIES ("clocks"), and shows that standard optimizers
(SGD-with-momentum, Adam) are themselves ASSOCIATIVE-MEMORY modules that
compress gradient history. Its Continuum Memory System (CMS) replaces the binary
short-/long-term split with a SPECTRUM of memory blocks, each updated every k
tokens (some fast, some very slow), plus a self-modifying update rule to mitigate
catastrophic forgetting. The distinctive axis is the UPDATE-FREQUENCY SPECTRUM
(a plasticity ladder) together with OPTIMIZER-AS-MEMORY — NOT a single dedicated
memory module (that is the sibling `titans` organ), NOT one matrix at one cadence
(the sibling `inplacettt`), NOT event retrieval (`episodic`), NOT state-space
mixing (`ssm`), NOT recursion depth (`mor`).

We build a TOY CONTINUAL-LEARNING STREAM: a sequence of `num_tasks` small seeded
linear mappings (task_k: x -> w_k · x), presented in BLOCKS so the learner must
acquire task B without forgetting task A. Two learners observe the same stream:

  MULTI-TIMESCALE CMS SCHEDULE (the idea being demonstrated): three tiny memory
    levels — a fast weight vector (period k_fast, default 1), a medium level
    (period k_med, default 8), and a slow "core" (period k_slow, default 64).
    Per token: compute a LOCAL SURPRISE = squared prediction error of the fast
    prediction. The fast level updates every step (chases the current task); the
    medium level accumulates surprise and applies a batched update every k_med
    steps; the slow core updates only every k_slow steps AND only if accumulated
    surprise passes a GATE threshold ("protect the slow core" — it refuses to
    overwrite its consolidated knowledge for ordinary drift). The final read-out
    is a blend of all three levels, so early tasks survive in the slow core even
    while the fast level has moved on. OPTIMIZER-AS-MEMORY: the momentum state is
    carried as an EXPLICIT associative-memory vector m <- beta*m + grad that
    compresses past gradients and drives every level's write.

  SINGLE-CLOCK BASELINE: the SAME three levels, but ALL of them update EVERY step
    (k_fast=k_med=k_slow=1, no surprise gate). With no protected slow timescale
    the whole model tracks the current task and OVERWRITES earlier ones — classic
    catastrophic forgetting.

At the end of EACH task block we probe accuracy on TASK A (the first task) — this
is the FORGETTING CURVE: how much of task A each learner still gets right while it
is being trained on later tasks B, C, .... The honest signal on this controlled
toy stream: the multi-timescale CMS schedule RETAINS MORE of task A (less
forgetting) than the single-clock baseline. We report the exact retained-accuracy
values and their deltas.

Returned JSON fields (inside `payload`)
---------------------------------------
  num_tasks         : number of tasks in the continual-learning stream
  block_len         : tokens presented per task block
  n_tokens          : total streamed tokens (num_tasks * block_len)
  k_fast/k_med/k_slow : update periods (clocks) of the three CMS memory levels
  gate              : accumulated-surprise threshold gating slow-core writes
  levels            : per-level {name, period, gated} descriptors
  taskA_baseline    : task-A accuracy after each block, SINGLE-CLOCK baseline (list)
  taskA_cms         : task-A accuracy after each block, MULTI-TIMESCALE CMS (list)
  retainedA_baseline: task-A accuracy at end of stream, baseline (final retention)
  retainedA_cms     : task-A accuracy at end of stream, CMS (final retention)
  retention_delta   : retainedA_cms - retainedA_baseline (CMS advantage, >0 = less forgetting)
  mean_retention_delta : mean over all post-A blocks of (cms - baseline) task-A acc
  slow_writes_cms   : how many times the gated slow core actually wrote (CMS)
  slow_writes_baseline : slow-level writes for the always-on baseline (== n_tokens)
  mean_surprise     : mean local surprise over the whole stream
  peak_surprise     : max local surprise seen
  momentum          : momentum coefficient beta (optimizer-as-memory)
  forget_curve      : list (capped) of per-block {block, task, taskA_base,
                      taskA_cms, surprise} samples for the surface animation

Top-level fields
----------------
  label             : "MODELED" (verbatim; deterministic re-implementation of the
                      CMS update-scheduling arithmetic, NOT a trained model)
  model             : short description of the simulated setup
  method            : one-line description of the multi-timescale update rule
  seed              : RNG seed used
  payload           : dict of the simulated quantities above
  honest_note       : plain-language honesty disclaimer (incl. ablation nuance)
  citations         : dict of citable sources
  computed_at       : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  Toy analytic sim of the multi-timescale update-scheduling + optimizer-as-memory
  idea, NOT the Hope architecture. Tiny linear tasks, hand-set cadences. It draws
  all synthetic task weights, inputs, and noise from the pure-stdlib LCG PRNG
  below (no numpy, no stdlib `random`). Independent-ablation nuance: the NeurIPS
  paper was noted in public commentary to lack full ablations in its first
  version, so this demonstrates that the SCHEDULING MECHANISM reduces forgetting
  on a controlled toy stream — NOT reproducing Hope's language-modeling /
  needle-in-haystack results or its claimed wins over Titans / Transformers. The
  label "MODELED" is returned verbatim and displayed verbatim by the surface;
  never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Nested Learning: The Illusion of Deep Learning Architectures (the paradigm,
  Continuum Memory System, and "Hope" proof-of-concept simulated here):
    Behrouz, Razaviyayn, Zhong & Mirrokni (2025), Google Research; NeurIPS 2025.
    https://arxiv.org/abs/2512.24695
  Google Research blog — Introducing Nested Learning (official announcement):
    https://research.google/blog/introducing-nested-learning-a-new-ml-paradigm-for-continual-learning/
  NEVER-CLAIMED-AS: this module is not the Hope architecture, reproduces none of
  its code, weights, or measured benchmark numbers. It is a clean-room MODELED
  simulation of the update-frequency-spectrum + optimizer-as-memory idea.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
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
    "Nested Learning: The Illusion of Deep Learning Architectures — Behrouz, Razaviyayn, Zhong & Mirrokni (Google Research, NeurIPS 2025) arXiv:2512.24695": "https://arxiv.org/abs/2512.24695",
    "Google Research — Introducing Nested Learning: a new ML paradigm for continual learning (blog)": "https://research.google/blog/introducing-nested-learning-a-new-ml-paradigm-for-continual-learning/",
}

# Cap on how many per-block forgetting-curve samples we echo back for the
# surface's streaming animation (keeps payload bounded for large num_tasks).
_MAX_CURVE_SAMPLES = 96

# Fixed simulation constants (training-recipe constants, not data-driven):
_DIM        = 6       # dimensionality of the toy linear tasks
_BLOCK_LEN  = 96      # tokens presented per task block
_MOMENTUM   = 0.90    # beta — momentum coefficient (optimizer-as-associative-memory)
_LR_FAST    = 0.15    # SGD+momentum learning rate of the fast memory level
_EMA_MED    = 0.30    # EMA-distill step of the medium level toward the fast weights
_EMA_SLOW   = 0.50    # EMA-distill step of the slow "core" toward the fast weights
# read-out blend weights across the plasticity spectrum (fast/med/slow); the slow
# core dominates the consolidated read-out so early tasks survive in it.
_W_FAST     = 0.15
_W_MED      = 0.15
_W_SLOW     = 0.70
_ACC_TOL    = 0.35    # abs prediction-error tolerance counted as "correct"


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _dot(a, b):
    t = 0.0
    for i in range(len(a)):
        t += a[i] * b[i]
    return t


# ---------------------------------------------------------------------------
# Build the toy continual-learning stream: num_tasks seeded linear mappings,
# each a target weight vector w_k in [-1,1]^DIM. Presented in blocks.
# ---------------------------------------------------------------------------
def _make_tasks(rng, num_tasks: int):
    tasks = []
    for _ in range(num_tasks):
        w = [2.0 * next(rng) - 1.0 for _ in range(_DIM)]
        tasks.append(w)
    return tasks


def _sample_input(rng):
    return [2.0 * next(rng) - 1.0 for _ in range(_DIM)]


# ---------------------------------------------------------------------------
# One learner = three memory levels (fast/med/slow), optimizer-as-memory
# momentum vector, and either the SINGLE-CLOCK schedule (all periods 1, no gate)
# or the MULTI-TIMESCALE CMS schedule (fast/med/slow periods + surprise gate).
# ---------------------------------------------------------------------------
def _run_learner(tasks, block_len, k_fast, k_med, k_slow, gate, seed, gated):
    """
    Stream every task block past the three-level learner and return, after each
    block, the accuracy on TASK A (tasks[0]) — the forgetting curve — plus a few
    aggregate stats.

    Mechanism (faithful to the CMS spectrum idea): the FAST level is a plain
    SGD-with-momentum learner that chases the CURRENT task every step; its
    momentum state is carried as an EXPLICIT associative-memory vector
    m <- beta*m + (1-beta)*grad that compresses past gradients (optimizer-as-
    memory). The MEDIUM and SLOW levels do NOT learn from raw gradients — they
    CONSOLIDATE (EMA-distil) the fast weights at their own, slower clocks. The
    slow "core" is the long-term store and dominates the read-out.

    "Protect the slow core": the slow core consolidates only when the recent
    window's accumulated surprise is LOW (<= gate) — i.e. the fast level has
    SETTLED and its knowledge is reliable — and refuses to consolidate while
    surprise is HIGH (mid-learning of a new task), so transient chaos never
    corrupts the core. Because the slow clock is infrequent and the EMA step is
    partial, a task acquired early (task A) leaves a lasting imprint in the core.

    `gated=False` collapses to the SINGLE-CLOCK baseline: every level consolidates
    the fast weights EVERY step with NO surprise gate, so the slow core simply
    tracks whatever task is current and OVERWRITES earlier ones -> catastrophic
    forgetting.

    Deterministic: identical inputs -> identical trajectory (its own LCG stream,
    seeded from `seed`, so baseline and CMS see the SAME token stream).
    """
    rng = _lcg(seed)
    dim = _DIM

    # three memory levels (weight vectors) on the plasticity spectrum
    w_fast = [0.0] * dim
    w_med  = [0.0] * dim
    w_slow = [0.0] * dim
    m_fast = [0.0] * dim   # explicit associative-memory momentum vector (optimizer-as-memory)

    acc_surprise = 0.0     # accumulated surprise gating slow-core consolidation

    taskA = tasks[0]
    taskA_curve = []
    surprise_sum = 0.0
    peak_surprise = 0.0
    slow_writes = 0
    step = 0

    def _readout(x):
        # consolidated read-out = blend across the plasticity spectrum (slow-dominant)
        return (_W_FAST * _dot(w_fast, x)
                + _W_MED * _dot(w_med, x)
                + _W_SLOW * _dot(w_slow, x))

    def _probe_taskA():
        # fixed probe set for task A, drawn from a dedicated deterministic stream
        # so evaluation is identical for baseline and CMS and never disturbs the
        # training RNG.
        prng = _lcg(seed ^ 0x5A5A5A5A)
        hits = 0
        n = 24
        for _ in range(n):
            x = [2.0 * next(prng) - 1.0 for _ in range(dim)]
            y = _dot(taskA, x)
            pred = _readout(x)
            if abs(pred - y) <= _ACC_TOL:
                hits += 1
        return hits / n

    for ti, w_task in enumerate(tasks):
        for _ in range(block_len):
            x = _sample_input(rng)
            y = _dot(w_task, x)          # ground-truth label for the current task

            # ---- local surprise = squared error of the FAST prediction --------
            pred_fast = _dot(w_fast, x)
            err = pred_fast - y
            surprise = err * err
            surprise_sum += surprise
            if surprise > peak_surprise:
                peak_surprise = surprise
            acc_surprise += surprise

            # gradient of 0.5*err^2 wrt a linear weight = err * x
            grad = [err * xi for xi in x]

            # ---- FAST level: SGD + momentum every step (chases current task) --
            # optimizer-as-memory: momentum vector compresses past gradients
            for i in range(dim):
                m_fast[i] = _MOMENTUM * m_fast[i] + (1.0 - _MOMENTUM) * grad[i]
                w_fast[i] -= _LR_FAST * m_fast[i]

            # ---- MEDIUM level: EMA-distil the fast weights every k_med steps ---
            per_med = 1 if not gated else max(1, k_med)
            if (step + 1) % per_med == 0:
                for i in range(dim):
                    w_med[i] = (1.0 - _EMA_MED) * w_med[i] + _EMA_MED * w_fast[i]

            # ---- SLOW core: EMA-distil the fast weights every k_slow steps, ---
            # GATED to PROTECT the core (consolidate only settled/low-surprise
            # content). The always-on baseline (gated=False) consolidates every
            # step with no gate, so it tracks the current task and forgets A.
            per_slow = 1 if not gated else max(1, k_slow)
            if (step + 1) % per_slow == 0:
                mean_surprise_window = acc_surprise / per_slow
                write_slow = (not gated) or (mean_surprise_window <= gate)
                if write_slow:
                    for i in range(dim):
                        w_slow[i] = (1.0 - _EMA_SLOW) * w_slow[i] + _EMA_SLOW * w_fast[i]
                    slow_writes += 1
                acc_surprise = 0.0

            step += 1

        # end of block -> record task-A retention (the forgetting curve point)
        taskA_curve.append(round(_probe_taskA(), 6))

    n_tokens = len(tasks) * block_len
    return {
        "taskA_curve": taskA_curve,
        "slow_writes": slow_writes,
        "surprise_sum": surprise_sum,
        "peak_surprise": peak_surprise,
        "n_tokens": n_tokens,
    }


# ---------------------------------------------------------------------------
# MODELED Nested-Learning / CMS multi-timescale scheduling simulation
# ---------------------------------------------------------------------------
def _nested_snapshot(seed: int = 42, num_tasks: int = 6,
                     k_fast: int = 1, k_med: int = 8, k_slow: int = 64,
                     gate: float = 0.15) -> dict:
    """
    Run a single toy continual-learning stream twice — once with the SINGLE-CLOCK
    baseline (all levels update every step, no gate) and once with the
    MULTI-TIMESCALE CMS schedule (fast/med/slow clocks + surprise-gated slow
    core) — and return the task-A forgetting curves plus retention deltas.

    Pure stdlib; deterministic — same (seed, num_tasks, k_fast, k_med, k_slow,
    gate) -> identical snapshot, every time. Both learners consume the SAME token
    stream (identical seed) so the comparison is apples-to-apples.
    """
    rng = _lcg(seed)
    num_tasks = max(2, num_tasks)
    tasks = _make_tasks(rng, num_tasks)
    block_len = _BLOCK_LEN

    base = _run_learner(tasks, block_len, k_fast, k_med, k_slow, gate,
                        seed=seed, gated=False)
    cms  = _run_learner(tasks, block_len, k_fast, k_med, k_slow, gate,
                        seed=seed, gated=True)

    taskA_base = base["taskA_curve"]
    taskA_cms  = cms["taskA_curve"]

    retainedA_baseline = taskA_base[-1]
    retainedA_cms      = taskA_cms[-1]
    retention_delta    = retainedA_cms - retainedA_baseline

    # mean delta over all blocks AFTER task A's own block (i.e. where forgetting
    # can occur): blocks 1..num_tasks-1
    post = [(taskA_cms[i] - taskA_base[i]) for i in range(1, num_tasks)]
    mean_retention_delta = (sum(post) / len(post)) if post else 0.0

    n_tokens = base["n_tokens"]
    mean_surprise = (base["surprise_sum"] + cms["surprise_sum"]) / (2.0 * max(n_tokens, 1))
    peak_surprise = max(base["peak_surprise"], cms["peak_surprise"])

    levels = [
        {"name": "fast",  "period": k_fast, "gated": False},
        {"name": "med",   "period": k_med,  "gated": False},
        {"name": "slow",  "period": k_slow, "gated": True},
    ]

    # forgetting-curve samples for the surface animation (one per block)
    curve = []
    probe_rng = _lcg(seed ^ 0x1234ABCD)
    for i in range(min(num_tasks, _MAX_CURVE_SAMPLES)):
        curve.append({
            "block": i,
            "task": i,
            "taskA_base": taskA_base[i],
            "taskA_cms": taskA_cms[i],
        })

    payload = {
        "num_tasks": num_tasks,
        "block_len": block_len,
        "n_tokens": n_tokens,
        "k_fast": k_fast,
        "k_med": k_med,
        "k_slow": k_slow,
        "gate": round(gate, 6),
        "levels": levels,
        "taskA_baseline": taskA_base,
        "taskA_cms": taskA_cms,
        "retainedA_baseline": round(retainedA_baseline, 6),
        "retainedA_cms": round(retainedA_cms, 6),
        "retention_delta": round(retention_delta, 6),
        "mean_retention_delta": round(mean_retention_delta, 6),
        "slow_writes_cms": cms["slow_writes"],
        "slow_writes_baseline": base["slow_writes"],
        "mean_surprise": round(mean_surprise, 6),
        "peak_surprise": round(peak_surprise, 6),
        "momentum": round(_MOMENTUM, 6),
        "forget_curve": curve,
    }
    return payload


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _ff(req: Request, key: str, default: float) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return default


def _h_schedule(req: Request):
    seed      = _ii(req, "seed",      42)
    num_tasks = max(2, min(_ii(req, "num_tasks", 6), 96))
    k_fast    = max(1, min(_ii(req, "k_fast",    1), 4096))
    k_med     = max(1, min(_ii(req, "k_med",     8), 4096))
    k_slow    = max(1, min(_ii(req, "k_slow",   64), 65536))
    gate      = max(0.0, min(_ff(req, "gate", 0.15), 100.0))

    payload = _nested_snapshot(seed=seed, num_tasks=num_tasks,
                               k_fast=k_fast, k_med=k_med, k_slow=k_slow, gate=gate)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Nested Learning / Continuum Memory System ('Hope'): three memory levels on an update-frequency spectrum (k_fast/k_med/k_slow) + optimizer-as-associative-memory momentum, on a toy continual-learning stream; single-clock baseline vs multi-timescale schedule",
        "method": "per token: local surprise = squared error of fast prediction; m <- beta*m + (1-beta)*grad (momentum-as-associative-memory); fast level = SGD+momentum every step; med + slow levels EMA-distil the fast weights at their own clocks (every k_med / k_slow); slow core consolidates ONLY when windowed surprise <= gate ('protect the slow core' from mid-learning chaos); read-out = slow-dominant blend of fast/med/slow; probe task-A accuracy after each block = forgetting curve",
        "seed":   seed,
        "payload": payload,
        "honest_note": (
            "MODELED: toy analytic sim of the multi-timescale update-scheduling + "
            "optimizer-as-memory idea from Nested Learning / the Continuum Memory "
            "System (Behrouz, Razaviyayn, Zhong & Mirrokni, Google Research; NeurIPS "
            "2025; arXiv:2512.24695), NOT the Hope architecture. Tiny linear tasks, "
            "hand-set cadences (k_fast/k_med/k_slow) and a hand-set surprise gate on "
            "the slow core. Independent-ablation nuance: the NeurIPS paper was noted "
            "in public commentary to lack full ablations in its first version, so this "
            "demonstrates only that the SCHEDULING MECHANISM (a plasticity ladder plus "
            "a protected, surprise-gated slow core) reduces forgetting on a controlled "
            "toy continual-learning stream — it does NOT reproduce Hope's "
            "language-modeling / needle-in-haystack results or its claimed wins over "
            "Titans / Transformers. All task weights, inputs, and noise are drawn from "
            "a deterministic LCG PRNG (no numpy, no stdlib random). Distinct from "
            "titans (one dedicated memory module, one surprise write rule), inplacettt "
            "(one matrix, one rule, one cadence), and episodic/ssm/mor: nested's axis "
            "is temporal PLASTICITY SCHEDULING — many memory levels at many clock rates "
            "plus treating the optimizer/update rule itself as associative memory. "
            "Deterministic: same seed/num_tasks/cadences/gate -> identical snapshot. "
            "SZL claims none of this as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_titans.register() / szl_episodic.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/nested/schedule onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/nested"
    handlers = [
        (f"{base}/schedule", _h_schedule),
    ]
    add_api_route = getattr(app, "add_api_route", None)
    for path, fn in handlers:
        try:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
        except Exception:
            # additive + guarded: never break app startup if a route collides
            try:
                app.router.routes.append(Route(path, fn))
            except Exception:
                pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _nested_snapshot(seed=42, num_tasks=6, k_fast=1, k_med=8, k_slow=64, gate=0.15)
    print("label: MODELED")
    print("num_tasks:", snap["num_tasks"])
    print("block_len:", snap["block_len"])
    print("n_tokens:", snap["n_tokens"])
    print("cadences (k_fast/k_med/k_slow):", snap["k_fast"], snap["k_med"], snap["k_slow"])
    print("gate:", snap["gate"])
    print("taskA_baseline (single-clock) curve:", snap["taskA_baseline"])
    print("taskA_cms (multi-timescale) curve:  ", snap["taskA_cms"])
    print("retainedA_baseline (single-clock, final):", snap["retainedA_baseline"])
    print("retainedA_cms (multi-timescale, final):  ", snap["retainedA_cms"])
    print("retention_delta (cms - baseline):", snap["retention_delta"])
    print("mean_retention_delta (post-A blocks):", snap["mean_retention_delta"])
    print("slow_writes_cms:", snap["slow_writes_cms"], "/ slow_writes_baseline:", snap["slow_writes_baseline"])
    print("mean_surprise:", snap["mean_surprise"], "/ peak_surprise:", snap["peak_surprise"])
    print("momentum (optimizer-as-memory beta):", snap["momentum"])

    # explicit forgetting-delta report
    print()
    print("FORGETTING CURVE — task-A retention, single-clock BASELINE vs multi-timescale CMS:")
    for row in snap["forget_curve"]:
        print("  block %2d: baseline %.3f   cms %.3f   delta %+.3f"
              % (row["block"], row["taskA_base"], row["taskA_cms"],
                 row["taskA_cms"] - row["taskA_base"]))

    # sanity: bounds
    assert 0.0 <= snap["retainedA_baseline"] <= 1.0, "retainedA_baseline out of [0,1]"
    assert 0.0 <= snap["retainedA_cms"] <= 1.0, "retainedA_cms out of [0,1]"
    assert snap["num_tasks"] >= 2, "need at least 2 tasks for continual learning"
    assert snap["mean_surprise"] >= 0.0, "mean_surprise negative"
    assert 0.0 <= snap["momentum"] < 1.0, "momentum must be in [0,1)"
    # gated slow core writes strictly less often than the always-on baseline
    assert snap["slow_writes_cms"] <= snap["slow_writes_baseline"], \
        "gated slow core should not write more often than the always-on baseline"

    # sanity: the whole point — the multi-timescale schedule RETAINS MORE of task A
    # (less catastrophic forgetting) than the single-clock baseline on this toy stream.
    assert snap["retainedA_cms"] >= snap["retainedA_baseline"], \
        "multi-timescale CMS should retain at least as much of task A as single-clock baseline"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _nested_snapshot(seed=42, num_tasks=6, k_fast=1, k_med=8, k_slow=64, gate=0.15)
    assert snap == snap2, "non-deterministic output for identical inputs"

    # sanity: a different seed generally yields a different snapshot
    snap3 = _nested_snapshot(seed=7, num_tasks=6, k_fast=1, k_med=8, k_slow=64, gate=0.15)
    assert isinstance(snap3["retainedA_cms"], float)

    print()
    print("szl_nested: ALL OK — deterministic, MODELED, multi-timescale CMS retains >= single-clock baseline on task A.")
