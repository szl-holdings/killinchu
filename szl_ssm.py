# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_ssm.py — SZL State-Space-Model (Mamba-3 successor) sequence-mixing endpoint.

Exposes a MODELED selective state-space scan — the recurrence at the heart of
Mamba / Mamba-2 / Mamba-3 — as a same-origin REST endpoint, so the SSM surface
organ has a live data source that is honest, deterministic, and citable — never
fabricated, never random-faked.

  GET  /api/<ns>/v1/ssm/scan?seed=&seq_len=&state_dim=&task=

Returned JSON fields
---------------------
  label                    : "MODELED" (always — this is a simulation, not a trained model)
  model                    : name of the recurrence being simulated
  task                     : 'copy' | 'parity' | 'induction'
  seq_len                  : sequence length simulated
  state_dim                : hidden-state width of the SSM
  seed                     : RNG seed used (deterministic; same seed -> same run)
  real_state_accuracy      : task accuracy of the REAL-valued selective-SSM state tracker
  complex_state_accuracy   : task accuracy of the COMPLEX-valued selective-SSM state tracker
                             (the Mamba-3 addition — richer state tracking)
  compute_flops_quadratic  : MODELED FLOPs for a Transformer-style O(L^2) self-attention mixer
  compute_flops_ssm        : MODELED FLOPs for the O(L) selective-SSM scan
  throughput_ratio         : compute_flops_quadratic / compute_flops_ssm (sub-quadratic win)
  trajectory                : sampled hidden-state trajectory (real + complex magnitude) for
                              rendering a 3D ribbon of the scan over sequence steps
  honest_note              : plain-language honesty disclaimer
  citations                : dict of citable sources
  computed_at               : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic closed-form simulation of the SELECTIVE STATE-SPACE RECURRENCE
  (h_t = A*h_{t-1} + B*x_t; y_t = C*h_t, with an input-dependent/selective gate on A,B),
  run over a synthetic copy/parity/induction task with a pure-stdlib deterministic LCG
  PRNG. It is NOT a trained Mamba/Mamba-2/Mamba-3 checkpoint, NOT a measured GPU benchmark,
  and the FLOPs figures are MODELED analytic counts (L^2*d for quadratic attention vs
  L*d*n for the linear SSM scan), not profiler output. The label "MODELED" is returned
  verbatim and displayed verbatim by the surface; it is never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  Mamba — Gu & Dao (2023) "Mamba: Linear-Time Sequence Modeling with Selective State
    Spaces". arXiv:2312.00752. https://arxiv.org/abs/2312.00752
  Mamba-2 — Dao & Gu (2024) "Transformers are SSMs: Generalized Models and Efficient
    Algorithms Through Structured State Space Duality". arXiv:2405.21060.
    https://arxiv.org/abs/2405.21060
  state-spaces/mamba (official implementation, Apache-2.0):
    https://github.com/state-spaces/mamba
  Mamba-3 — Lahoti, Li, Chen, Wang, Bick, Kolter, Dao, Gu (2026) "Mamba-3: Improved
    Sequence Modeling using State Space Principles". arXiv:2603.15569 (ICLR 2026).
    https://arxiv.org/abs/2603.15569
    Mamba-3 introduces (1) exponential-trapezoidal discretization, (2) a COMPLEX-VALUED
    state update for richer state tracking (this organ's real-vs-complex contrast is
    directly inspired by that section of the paper — e.g. reported ~100% vs ~0.9% parity
    accuracy for complex- vs real-only state tracking in their ablations), and (3) a
    multi-input multi-output (MIMO) formulation. This organ models the qualitative shape
    of that real-vs-complex state-tracking gap; exact numbers are NOT reproduced from the
    paper's tables — they come from our own small deterministic pure-stdlib scan.
  HONEST-STUB note: compute_flops_* are MODELED analytic estimates (standard
    big-O accounting: O(L^2 * d) for full self-attention vs O(L * d * n) for a linear
    selective-SSM scan), not measured wall-clock or profiler FLOPs.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (no numpy, no `random` module — deterministic LCG
  PRNG). Deterministic with seed. 0 runtime CDN.
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
    "Mamba — Gu & Dao (2023) arXiv:2312.00752": "https://arxiv.org/abs/2312.00752",
    "Mamba-2 — Dao & Gu (2024) arXiv:2405.21060": "https://arxiv.org/abs/2405.21060",
    "state-spaces/mamba (official impl, Apache-2.0)": "https://github.com/state-spaces/mamba",
    "Mamba-3 — Lahoti et al. (2026) arXiv:2603.15569": "https://arxiv.org/abs/2603.15569",
}

VALID_TASKS = ("copy", "parity", "induction")


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no `random` module)
# ---------------------------------------------------------------------------
class _LCG:
    """Numerical-Recipes-style 32-bit linear congruential generator.
    Deterministic: same seed -> identical stream. Pure stdlib arithmetic only."""

    _A = 1664525
    _C = 1013904223
    _M = 2 ** 32

    def __init__(self, seed: int = 42):
        self._state = int(seed) % self._M

    def next_uint(self) -> int:
        self._state = (self._A * self._state + self._C) % self._M
        return self._state

    def uniform(self) -> float:
        """Uniform float in [0, 1)."""
        return self.next_uint() / self._M

    def bit(self) -> int:
        """Deterministic pseudo-random bit in {0, 1}."""
        return self.next_uint() & 1

    def signed_unit(self) -> float:
        """Uniform float in [-1, 1)."""
        return self.uniform() * 2.0 - 1.0


# ---------------------------------------------------------------------------
# Synthetic task generation (pure stdlib, deterministic from seed)
# ---------------------------------------------------------------------------
def _make_task_sequence(rng: _LCG, seq_len: int, task: str):
    """
    Build a binary input sequence x[0..L-1] in {0,1} and the target label(s) for the
    chosen synthetic task:
      copy       : target = x[0] (must be "remembered" across the whole sequence)
      parity     : target = XOR of all bits seen so far (running parity) — requires
                   genuine state-tracking, not just fading memory
      induction  : after a special "trigger" bit appears once mid-sequence, the target
                   at the final step = the bit that originally followed the trigger
                   (classic induction-head task; requires precise recall of a token
                   at an arbitrary earlier position, gated by a match)
    Returns (x: list[int], target: int, meta: dict)
    """
    x = [rng.bit() for _ in range(seq_len)]

    if task == "copy":
        target = x[0]
        meta = {"probe": "final output should equal x[0]"}
    elif task == "parity":
        p = 0
        for b in x:
            p ^= b
        target = p
        meta = {"probe": "final output should equal running XOR of all bits"}
    else:  # induction
        # place a trigger at a deterministic-but-seeded position in the first half;
        # the token immediately after the trigger is the value the model must recall
        # when the trigger reappears near the end of the sequence.
        trig_pos = 1 + (rng.next_uint() % max(1, seq_len // 2 - 1))
        recall_val = x[trig_pos + 1] if trig_pos + 1 < seq_len else x[-1]
        # force the trigger to reappear at the last position so "recall" is well-defined
        x[trig_pos] = 1
        x[-1] = 1
        target = recall_val
        meta = {"trigger_pos": trig_pos, "probe": "final output should equal token after first trigger"}

    return x, target, meta


# ---------------------------------------------------------------------------
# Selective SSM scan: REAL-valued state tracker
#   h_t = a_t * h_{t-1} + b_t * x_t     (a_t, b_t are input-dependent / "selective")
#   y_t = c * h_t
# ---------------------------------------------------------------------------
def _scan_real(x, state_dim: int, rng: _LCG):
    """Real-valued selective-SSM recurrence over a binary sequence.
    A, B, C are deterministic per-channel parameters (seeded); the gate on A/B is
    input-dependent ("selective"), mirroring Mamba's selection mechanism. State is a
    real vector of width state_dim. Returns (trajectory, final_readout)."""
    A = [0.55 + 0.4 * rng.uniform() for _ in range(state_dim)]   # decay in (0.55, 0.95)
    B = [0.5 + 0.5 * rng.uniform() for _ in range(state_dim)]
    C = [rng.signed_unit() for _ in range(state_dim)]

    h = [0.0] * state_dim
    traj = []
    for x_t in x:
        # selective gate: input-dependent scaling of A and B (Mamba-style selection),
        # real-valued only — no phase/rotation available to preserve sign/parity info.
        gate = 0.5 + 0.5 * x_t  # in {0.5, 1.0}, input-dependent
        for i in range(state_dim):
            h[i] = (A[i] * gate) * h[i] + (B[i] * gate) * (1.0 if x_t else -1.0)
        y = sum(c * hi for c, hi in zip(C, h))
        traj.append(list(h))

    readout = sum(c * hi for c, hi in zip(C, h))
    return traj, readout


# ---------------------------------------------------------------------------
# Selective SSM scan: COMPLEX-valued state tracker (the Mamba-3 addition)
#   h_t = (a_t * e^{i*theta_t}) * h_{t-1} + b_t * x_t     (complex state, rotation = phase)
#   y_t = Re(c * h_t)
# The complex phase lets the state ROTATE rather than just decay, which is exactly the
# mechanism Mamba-3 (arXiv:2603.15569) adds to recover state-tracking tasks like parity
# that a purely real (non-negative-eigenvalue) diagonal SSM provably cannot solve.
# ---------------------------------------------------------------------------
def _scan_complex(x, state_dim: int, rng: _LCG):
    """Complex-valued selective-SSM recurrence: state carries magnitude AND phase,
    enabling rotation-based state tracking (parity/induction) that real-only diagonal
    SSMs struggle with. Pure stdlib complex arithmetic (Python's built-in `complex`).

    Mamba-3 (arXiv:2603.15569, Sec. 3.2) motivates the complex-valued state update
    precisely because a real-valued diagonal SSM with non-negative eigenvalues can only
    ever *decay* its state monotonically and provably cannot represent input-triggered
    SIGN FLIPS needed for exact parity/state-tracking. A complex eigenvalue ON THE UNIT
    CIRCLE (magnitude ~1, pure rotation) can flip the state's real part by a fixed
    ROTATION rather than a decayed blend: rotating by exactly pi (180 degrees) whenever
    a "1" token is seen, and by (a small seeded, near-zero) angle otherwise, turns the
    real part of the state into an EXACT running-XOR / parity register -- the sign of
    h.real flips if and only if the running parity flips. A real-only diagonal state
    cannot represent this exact flip (it can only shrink toward zero), which is the
    qualitative gap this scan models -- a stylized, honest illustration of the
    real-vs-complex state-tracking gap reported in the paper's own ablations (parity
    accuracy jumps from near-chance to ~100% with the complex-valued update)."""
    # near-unit magnitude per channel (very light decay only, NOT the dominant effect --
    # rotation, not magnitude, carries the state-tracking signal here).
    A_mag = [0.985 + 0.01 * rng.uniform() for _ in range(state_dim)]
    # per-channel small base phase drift for a "0" input (near 0, seeded for diversity);
    # a "1" input adds a full pi rotation on top of this -- the input SELECTS the angle,
    # which is the "selective" part of the recurrence a real-valued SSM cannot express.
    theta0 = [0.05 * rng.signed_unit() for _ in range(state_dim)]
    # per-channel initial phase offset (so channels don't all start identically aligned)
    phase_init = [math.pi * rng.uniform() for _ in range(state_dim)]
    C_re = [0.6 + 0.4 * rng.uniform() for _ in range(state_dim)]

    h = [complex(math.cos(p), math.sin(p)) for p in phase_init]  # unit-magnitude init
    traj = []
    for x_t in x:
        extra = math.pi if x_t else 0.0
        new_h = [0j] * state_dim
        for i in range(state_dim):
            ang = theta0[i] + extra
            rot = complex(math.cos(ang), math.sin(ang))
            new_h[i] = (A_mag[i]) * rot * h[i]
        h = new_h
        traj.append([abs(hi) for hi in h])  # magnitude per channel, for rendering

    # readout: weighted sum of the real part across channels, relative to each channel's
    # own initial real part -- this cancels the arbitrary per-channel initial phase and
    # leaves a clean sign flip that tracks parity (or the relevant state-tracking signal).
    # Convention: h.real >= 0 (relative to each channel's own initial phase sign)
    # corresponds to EVEN running parity (target bit 0); h.real < 0 to ODD parity
    # (target bit 1). We negate so the shared _accuracy_from_readout() convention
    # (readout >= 0 -> predict 1) lines up: readout should be NEGATIVE for even
    # parity (target 0) and POSITIVE for odd parity (target 1).
    readout = -sum(c * (hi.real) * (1.0 if math.cos(p) >= 0 else -1.0)
                   for c, hi, p in zip(C_re, h, phase_init))
    return traj, readout


def _accuracy_from_readout(readout: float, target: int) -> int:
    """Binarize a real-valued readout with sign threshold at 0; 1 if it matches target."""
    pred = 1 if readout >= 0 else 0
    return 1 if pred == target else 0


# ---------------------------------------------------------------------------
# Task-level evaluation: run many seeded trials, report mean accuracy
# ---------------------------------------------------------------------------
def _evaluate(seed: int, seq_len: int, state_dim: int, task: str, n_trials: int = 24):
    real_correct = 0
    complex_correct = 0
    sample_traj_real = None
    sample_traj_complex = None
    sample_x = None
    sample_target = None
    sample_meta = None

    for trial in range(n_trials):
        # deterministic per-trial seed derived from base seed (no randomness beyond LCG)
        trial_seed = (seed * 1_000_003 + trial * 97 + 1) % (2 ** 32)
        gen_rng = _LCG(trial_seed)
        x, target, meta = _make_task_sequence(gen_rng, seq_len, task)

        real_rng = _LCG(trial_seed ^ 0x5EED0001)
        traj_r, readout_r = _scan_real(x, state_dim, real_rng)
        real_correct += _accuracy_from_readout(readout_r, target)

        complex_rng = _LCG(trial_seed ^ 0x5EED0002)
        traj_c, readout_c = _scan_complex(x, state_dim, complex_rng)
        complex_correct += _accuracy_from_readout(readout_c, target)

        if trial == 0:
            sample_traj_real = traj_r
            sample_traj_complex = traj_c
            sample_x = x
            sample_target = target
            sample_meta = meta

    real_acc = round(real_correct / n_trials, 6)
    complex_acc = round(complex_correct / n_trials, 6)

    return {
        "real_state_accuracy": real_acc,
        "complex_state_accuracy": complex_acc,
        "n_trials": n_trials,
        "sample_input": sample_x,
        "sample_target": sample_target,
        "sample_meta": sample_meta,
        "sample_trajectory_real": sample_traj_real,
        "sample_trajectory_complex": sample_traj_complex,
    }


# ---------------------------------------------------------------------------
# MODELED compute-cost accounting: O(L^2) quadratic attention vs O(L) SSM scan
# ---------------------------------------------------------------------------
def _compute_flops(seq_len: int, state_dim: int, d_model: int = 256):
    """
    Standard big-O analytic accounting (MODELED, not profiled):
      Quadratic (Transformer self-attention): dominant term ~ 2 * L^2 * d_model
        (QK^T and softmax*V passes scale with L^2).
      Linear (selective SSM scan): dominant term ~ 2 * L * d_model * state_dim
        (per-step state update + readout scale with L, not L^2).
    """
    flops_quadratic = 2.0 * (seq_len ** 2) * d_model
    flops_ssm = 2.0 * seq_len * d_model * state_dim
    throughput_ratio = round(flops_quadratic / flops_ssm, 4) if flops_ssm > 0 else None
    return {
        "compute_flops_quadratic": flops_quadratic,
        "compute_flops_ssm": flops_ssm,
        "d_model_assumed": d_model,
        "throughput_ratio": throughput_ratio,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _si(req: Request, key: str, default: str) -> str:
    try:
        v = str(req.query_params.get(key, default)).strip().lower()
        return v if v else default
    except Exception:
        return default


def _h_scan(req: Request):
    seed       = _ii(req, "seed", 42)
    seq_len    = max(4, min(_ii(req, "seq_len", 32), 256))
    state_dim  = max(1, min(_ii(req, "state_dim", 16), 64))
    task       = _si(req, "task", "parity")
    if task not in VALID_TASKS:
        task = "parity"

    ev = _evaluate(seed=seed, seq_len=seq_len, state_dim=state_dim, task=task)
    flops = _compute_flops(seq_len=seq_len, state_dim=state_dim)

    return JSONResponse({
        "label":       "MODELED",
        "model":       "Selective state-space scan (Mamba/Mamba-2/Mamba-3-style): "
                       "h_t = A(x_t)*h_{t-1} + B(x_t)*x_t; y_t = C*h_t",
        "task":        task,
        "seq_len":     seq_len,
        "state_dim":   state_dim,
        "seed":        seed,
        "n_trials":    ev["n_trials"],
        "real_state_accuracy":    ev["real_state_accuracy"],
        "complex_state_accuracy": ev["complex_state_accuracy"],
        "compute_flops_quadratic": flops["compute_flops_quadratic"],
        "compute_flops_ssm":       flops["compute_flops_ssm"],
        "throughput_ratio":        flops["throughput_ratio"],
        "d_model_assumed":         flops["d_model_assumed"],
        "sample": {
            "input_bits":        ev["sample_input"],
            "target":            ev["sample_target"],
            "meta":              ev["sample_meta"],
            "trajectory_real":       ev["sample_trajectory_real"],
            "trajectory_complex_magnitude": ev["sample_trajectory_complex"],
        },
        "honest_note": (
            "MODELED: this is a deterministic closed-form simulation of the SELECTIVE "
            "state-space recurrence at the heart of Mamba/Mamba-2/Mamba-3 — NOT a trained "
            "checkpoint, NOT a measured GPU benchmark. real_state_accuracy vs "
            "complex_state_accuracy contrasts a REAL-valued diagonal state (decay-only) "
            "against a COMPLEX-valued state (decay + rotation/phase) on a synthetic "
            f"'{task}' task; the complex-valued update is the Mamba-3 (arXiv:2603.15569) "
            "addition for richer state tracking. compute_flops_quadratic / "
            "compute_flops_ssm are MODELED analytic FLOP counts (O(L^2*d) self-attention "
            "vs O(L*d*n) linear SSM scan), not profiler output. Deterministic: same seed "
            "-> identical run. Pure stdlib LCG PRNG (no numpy, no random module). "
            "Cite also: Gu & Dao arXiv:2312.00752 (Mamba); Dao & Gu arXiv:2405.21060 "
            "(Mamba-2); state-spaces/mamba github.com/state-spaces/mamba (Apache-2.0). "
            "SZL claims NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_neuromorphic.register() / szl_episodic.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/ssm/scan onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/ssm"
    handlers = [
        (f"{base}/scan", _h_scan),
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
    ev = _evaluate(seed=42, seq_len=32, state_dim=16, task="parity", n_trials=24)
    flops = _compute_flops(seq_len=32, state_dim=16)
    print("task: parity")
    print("real_state_accuracy:", ev["real_state_accuracy"])
    print("complex_state_accuracy:", ev["complex_state_accuracy"])
    print("compute_flops_quadratic:", flops["compute_flops_quadratic"])
    print("compute_flops_ssm:", flops["compute_flops_ssm"])
    print("throughput_ratio:", flops["throughput_ratio"])
    print("sample_input[:8]:", ev["sample_input"][:8])
    print("sample_target:", ev["sample_target"])
    print("label: MODELED")

    # also smoke-test copy and induction tasks briefly
    for t in ("copy", "induction"):
        ev_t = _evaluate(seed=7, seq_len=32, state_dim=16, task=t, n_trials=24)
        print(f"[{t}] real_state_accuracy={ev_t['real_state_accuracy']} "
              f"complex_state_accuracy={ev_t['complex_state_accuracy']}")
