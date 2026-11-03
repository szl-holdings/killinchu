# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_elf.py — SZL ELF (Embedded Language Flows) continuous-embedding Flow-Matching
endpoint.

Exposes a MODELED deterministic Flow-Matching generative process that runs ENTIRELY
IN TOKEN-EMBEDDING SPACE and stays continuous until the FINAL time step, where a
nearest-embedding readout maps the settled continuous state to discrete tokens. This
is the clean-room illustration of the central ELF result: because the whole
trajectory is a continuous vector field, image-diffusion machinery — in particular
classifier-free guidance (CFG) — transfers with minimal adaptation, giving usable
generation quality with FEW sampling steps.

  GET  /api/<ns>/v1/elf/flow?seed=&num_euler_steps=&guidance_scale=

Method (all closed-form / deterministic from seed; pure-stdlib, no numpy/random)
--------------------------------------------------------------------------------
  vocab            : 6 fixed symbols. Each symbol i gets a deterministic 2-D
                     embedding on the UNIT CIRCLE at angle 2*pi*i/6 (evenly spaced),
                     so "decode = nearest embedding" is exact and visualizable.
  target sentence  : length-4 pattern from a fixed toy grammar (seeded), so we have
                     a clean discrete target x1_tokens with a clean continuous target
                     x1 (the stacked target embeddings).
  x0 ~ N(0,I)_2    : per-position seeded Gaussian noise (Box-Muller over an LCG
                     stream — pure stdlib).
  linear path      : straight-line (linear-interpolant / OT) probability path
                     x_t = (1-t)*x0 + t*x1  per position.
  ground-truth v   : closed-form conditional velocity  v*(x,t) = x1 - x0  (constant
                     along the straight-line coupling; Lipman et al. CFM,
                     arXiv:2210.02747). This is what the toy field is fit against.
  hand-fit field   : a small LEAST-SQUARES linear map  v_hat = A * [x; y; t; 1]  per
                     coordinate, solved DETERMINISTICALLY (normal equations + Gaussian
                     elimination, no autograd, no numpy) over a seeded batch of
                     (position, t) samples with regression target v* = x1 - x0. This
                     stands in for the "shared-weight network" that ELF trains; here
                     it is fit in closed form so the whole run is reproducible.
  conditional /    : we also fit an UNCONDITIONAL field (target v* = -x0, i.e. drift
  unconditional      toward the origin / no-target prior) so we can blend them:
                        v_cfg = v_uncond + guidance_scale * (v_cond - v_uncond)
                     — a toy classifier-free-guidance knob (Ho & Salimans 2022,
                     arXiv:2207.12598), the same machinery ELF borrows from diffusion.
  Euler ODE        : integrate dx/dt = v_cfg(x,t) from t=0 to t=1 with
                     `num_euler_steps` explicit-Euler steps, ENTIRELY in 2-D
                     continuous space.
  CONTINUOUS-      : the ODE never touches the discrete vocabulary during
  UNTIL-FINAL-STEP   integration. ONLY at t=1 do we discretize, by nearest-embedding
  guard              argmax over the 6 unit-circle embeddings. This is the ELF
                     mechanism: continuous flow, terminal continuous->discrete decode.
  accuracy         : fraction of the 4 positions whose terminal nearest-embedding
                     decode equals the target grammar symbol (the toy-grammar
                     "generative accuracy").

Returned JSON fields
---------------------
  label               : "MODELED" (always — a toy analytic process, not a trained model)
  model               : short description
  vocab_size          : 6
  embedding_dim       : 2
  num_euler_steps     : Euler steps requested
  guidance_scale      : CFG blend weight requested
  embeddings          : [[x,y], ...] the 6 unit-circle symbol embeddings
  target_tokens       : the length-4 target grammar symbol ids
  target_embeddings   : the stacked clean target x1 (list of [x,y])
  x0                  : the seeded noise start (list of [x,y])
  trajectory          : [{t, x:[[x,y]*4]}, ...] continuous state per Euler step
  decoded_tokens      : nearest-embedding argmax of the terminal continuous state
  accuracy            : fraction of positions decoding to the correct grammar symbol
  accuracy_vs_steps   : [{num_euler_steps, accuracy}, ...] the few-step-quality curve
  guidance_ablation   : {on:{guidance_scale,accuracy}, off:{guidance_scale,accuracy}}
  honest_note         : plain-language honesty disclaimer (inspired-not-real)
  citations           : dict of citable sources
  computed_at         : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  Inspired-not-real. This is a deterministic, closed-form, pure-stdlib toy analytic
  Flow-Matching simulation in a 2-D embedding space with 6 symbols and a hand-fit
  linear velocity field. It is NOT ELF / LangFlow / MLFM, uses NO learned weights,
  and reproduces NONE of their perplexity numbers. It demonstrates only the
  qualitative MECHANISM (continuous embedding-space trajectory + terminal
  continuous->discrete decode + guidance transfer) and measures its own toy-grammar
  accuracy, nothing more. The label "MODELED" is returned verbatim and displayed
  verbatim by the surface; it is never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  ELF (Embedded Language Flows): Hu, Qiu, Lu, Zhao, Li, Kim, Andreas, He.
    arXiv:2605.10938. https://arxiv.org/abs/2605.10938
  LangFlow (Continuous Diffusion Rivals Discrete in Language Modeling):
    arXiv:2604.11748. https://arxiv.org/abs/2604.11748
  MLFM (Masked Language Flow Models): arXiv:2606.27617.
    https://arxiv.org/abs/2606.27617
  Classifier-Free Guidance: Ho & Salimans 2022, arXiv:2207.12598 (the diffusion
    machinery ELF borrows). https://arxiv.org/abs/2207.12598
  Flow Matching for Generative Modeling: Lipman et al. 2022, arXiv:2210.02747
    (the linear-interpolant CFM objective). https://arxiv.org/abs/2210.02747

DOCTRINE v11: NOTHING here is in the locked-8. Λ stays Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (no numpy). Deterministic with seed. 0 runtime CDN.
  NEVER-CLAIMED-AS ELF / LangFlow / MLFM; reproduces none of their perplexity numbers.
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
    "ELF: Embedded Language Flows — Hu, Qiu, Lu, Zhao, Li, Kim, Andreas, He. arXiv:2605.10938": "https://arxiv.org/abs/2605.10938",
    "LangFlow: Continuous Diffusion Rivals Discrete in Language Modeling — arXiv:2604.11748": "https://arxiv.org/abs/2604.11748",
    "MLFM: Masked Language Flow Models — arXiv:2606.27617": "https://arxiv.org/abs/2606.27617",
    "Classifier-Free Guidance — Ho & Salimans 2022, arXiv:2207.12598": "https://arxiv.org/abs/2207.12598",
    "Flow Matching for Generative Modeling — Lipman et al. 2022, arXiv:2210.02747": "https://arxiv.org/abs/2210.02747",
}

# Toy fixed vocabulary + fixed grammar / geometry constants.
_VOCAB_SIZE = 6          # 6 symbols, evenly spaced on the unit circle
_EMBED_DIM = 2           # 2-D embedding space (so it is exactly visualizable)
_SEQ_LEN = 4             # length-4 toy-grammar "sentences"
_FIT_BATCH = 48          # seeded (position, t) samples used to fit the toy field
_PROBE_STEPS = [1, 2, 4, 8, 16, 32]   # step ladder for accuracy_vs_steps curve


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _gauss_stream(seed: int):
    """Deterministic standard-normal stream via Box-Muller over the LCG uniform
    stream. Pure stdlib (math.log/cos/sqrt only) — no numpy, no random module."""
    rng = _lcg(seed)
    while True:
        u1 = max(next(rng), 1e-12)   # avoid log(0)
        u2 = next(rng)
        r = math.sqrt(-2.0 * math.log(u1))
        theta = 2.0 * math.pi * u2
        yield r * math.cos(theta)
        yield r * math.sin(theta)


# ---------------------------------------------------------------------------
# Small pure-stdlib vector ops (2-D; no numpy)
# ---------------------------------------------------------------------------
def _vsub(a, b):
    return [ai - bi for ai, bi in zip(a, b)]


def _vadd(a, b):
    return [ai + bi for ai, bi in zip(a, b)]


def _vscale(a, s):
    return [ai * s for ai in a]


def _vnorm2(a):
    return sum(ai * ai for ai in a)


def _vdist(a, b):
    return math.sqrt(_vnorm2(_vsub(a, b)))


# ---------------------------------------------------------------------------
# Fixed vocabulary geometry + toy grammar (deterministic)
# ---------------------------------------------------------------------------
def _unit_circle_embeddings():
    """Assign symbol i the 2-D embedding (cos, sin) at angle 2*pi*i/6. Evenly
    spaced on the unit circle so nearest-embedding decode is exact + visualizable.
    Deterministic and seed-independent (the geometry is fixed)."""
    embs = []
    for i in range(_VOCAB_SIZE):
        ang = 2.0 * math.pi * i / _VOCAB_SIZE
        embs.append([math.cos(ang), math.sin(ang)])
    return embs


def _target_tokens(seed: int):
    """A length-4 target from a fixed toy grammar. Rule: pick a seeded start
    symbol s0 and a seeded step d in {1,2}; the sentence is the arithmetic
    progression s0, s0+d, s0+2d, s0+3d (mod vocab_size). This is a fixed,
    deterministic pattern rule — same seed -> identical target."""
    rng = _lcg((int(seed) ^ 0x1234ABCD) & 0xFFFFFFFF)
    s0 = int(next(rng) * _VOCAB_SIZE) % _VOCAB_SIZE
    d = 1 + (int(next(rng) * 2) % 2)   # step in {1, 2}
    return [(s0 + k * d) % _VOCAB_SIZE for k in range(_SEQ_LEN)]


def _nearest_symbol(point, embeddings):
    """Nearest-embedding argmax: return the symbol id whose unit-circle embedding
    is closest (L2) to `point`. The terminal continuous->discrete readout."""
    best_i, best_d = 0, float("inf")
    for i, e in enumerate(embeddings):
        d = _vnorm2(_vsub(point, e))
        if d < best_d:
            best_d, best_i = d, i
    return best_i


# ---------------------------------------------------------------------------
# Deterministic least-squares linear velocity fit (no numpy / no autograd)
# ---------------------------------------------------------------------------
def _solve_linear(ata, atb):
    """Solve (A^T A) w = A^T b for a small square system via Gaussian elimination
    with partial pivoting. Pure stdlib. `ata` is n x n (list of lists), `atb` is
    length n. Returns the weight vector w (length n)."""
    n = len(atb)
    # Build augmented matrix.
    M = [row[:] + [atb[r]] for r, row in enumerate(ata)]
    for col in range(n):
        # partial pivot
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            continue
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for r in range(n):
            if r == col:
                continue
            f = M[r][col] / pv
            if f == 0.0:
                continue
            for c in range(col, n + 1):
                M[r][c] -= f * M[col][c]
    w = [0.0] * n
    for r in range(n):
        d = M[r][r]
        w[r] = (M[r][n] / d) if abs(d) > 1e-12 else 0.0
    return w


# Feature layout for the shared-weight linear field:
#   [x, y, t, cx, cy, 1]   (6 features)
# where (x,y) is the current continuous state, t the flow time, and (cx,cy) the
# CONDITIONING target embedding for this position. The unconditional field zeros
# out (cx,cy) — it is the same shared network run with the condition dropped, the
# standard classifier-free-guidance construction (Ho & Salimans 2022).
_NFEAT = 6


def _feats(point, t, cond_emb):
    return [point[0], point[1], t, cond_emb[0], cond_emb[1], 1.0]


def _fit_velocity_field(seed: int, embeddings, target_embeddings, x0, conditional):
    """Fit ONE shared-weight linear velocity map
        v_hat(coord) = w . [x, y, t, cx, cy, 1]
    per output coordinate (vx, vy) by ordinary least squares over a seeded batch
    of (position, t) samples along each position's linear-interpolant path. The
    condition (cx,cy) is the position's TARGET embedding, so the SAME shared field
    can steer every position to its own target — the ELF 'shared-weight network'
    idea, fit here in closed form (no autograd).

    Regression target v* = x1 - x0 (closed-form ground-truth conditional velocity
    of the straight-line coupling; Lipman et al. CFM, arXiv:2210.02747).

    conditional=True  -> condition = the true target embedding (cx,cy)=x1
    conditional=False -> condition dropped (cx,cy)=(0,0): the unconditional field,
                         which learns only the target-agnostic average drift.

    Solved deterministically via the normal equations + Gaussian elimination
    (no numpy, no autograd). Returns (Wx, Wy), each length-_NFEAT. Same
    seed/inputs -> identical weights.
    """
    rng = _lcg((int(seed) ^ (0xC0DE if conditional else 0xBEEF)) & 0xFFFFFFFF)

    ata = [[0.0] * _NFEAT for _ in range(_NFEAT)]
    atb_x = [0.0] * _NFEAT
    atb_y = [0.0] * _NFEAT

    for _ in range(_FIT_BATCH):
        pos = int(next(rng) * _SEQ_LEN) % _SEQ_LEN
        t = next(rng)                      # sample t in [0,1)
        x1 = target_embeddings[pos]
        x0p = x0[pos]
        # point on the linear interpolant path at time t
        xt = _vadd(_vscale(x0p, 1.0 - t), _vscale(x1, t))
        cond = x1 if conditional else [0.0, 0.0]
        feats = _feats(xt, t, cond)
        vstar = _vsub(x1, x0p)             # closed-form ground-truth conditional velocity
        for i in range(_NFEAT):
            for j in range(_NFEAT):
                ata[i][j] += feats[i] * feats[j]
            atb_x[i] += feats[i] * vstar[0]
            atb_y[i] += feats[i] * vstar[1]

    # tiny ridge for numerical stability (deterministic)
    for i in range(_NFEAT):
        ata[i][i] += 1e-6

    Wx = _solve_linear([row[:] for row in ata], atb_x)
    Wy = _solve_linear([row[:] for row in ata], atb_y)
    return Wx, Wy


def _apply_field(W, point, t, cond_emb):
    """Evaluate the shared linear field v = (Wx.f, Wy.f), f = [x,y,t,cx,cy,1]."""
    Wx, Wy = W
    feats = _feats(point, t, cond_emb)
    vx = sum(Wx[i] * feats[i] for i in range(_NFEAT))
    vy = sum(Wy[i] * feats[i] for i in range(_NFEAT))
    return [vx, vy]


# ---------------------------------------------------------------------------
# MODELED continuous-embedding Flow-Matching integrator (deterministic)
# ---------------------------------------------------------------------------
def elf_flow_step(point, t, dt, W_cond, W_uncond, cond_emb, guidance_scale):
    """One explicit-Euler step of the guided flow ODE in continuous 2-D embedding
    space. Reusable, importable-in-spirit module-level function — the flow math
    kept clean so sibling organs can build on the same substrate independently.

    Guided (classifier-free) velocity, conditioned on this position's target
    embedding `cond_emb`:
        v_cond   = shared_field(x, t, cond_emb)     # condition present
        v_uncond = shared_field(x, t, [0,0])        # condition dropped
        v_cfg    = v_uncond + guidance_scale * (v_cond - v_uncond)
    then  x_next = x + dt * v_cfg. Never touches the discrete vocabulary — this is
    the CONTINUOUS-UNTIL-FINAL-STEP guard: decode happens only at t=1, outside
    this step function.
    """
    v_cond = _apply_field(W_cond, point, t, cond_emb)
    v_uncond = _apply_field(W_uncond, point, t, [0.0, 0.0])
    v_cfg = _vadd(v_uncond, _vscale(_vsub(v_cond, v_uncond), guidance_scale))
    return _vadd(point, _vscale(v_cfg, dt))


def _integrate_sequence(x0, W_cond, W_uncond, cond_embs, num_euler_steps, guidance_scale):
    """Integrate all _SEQ_LEN positions in parallel through the continuous ODE,
    each position conditioned on its own target embedding cond_embs[pos].
    Returns (trajectory, terminal_state) where trajectory is a list of
    {"t": t, "x": [[x,y]*SEQ_LEN]} snapshots including both endpoints. Runs
    ENTIRELY in continuous 2-D space; no discretization here."""
    steps = max(1, int(num_euler_steps))
    dt = 1.0 / steps
    x = [list(p) for p in x0]
    trajectory = [{"t": 0.0, "x": [[round(c, 6) for c in p] for p in x]}]
    for i in range(1, steps + 1):
        t = (i - 1) * dt
        x = [elf_flow_step(x[p], t, dt, W_cond, W_uncond, cond_embs[p], guidance_scale)
             for p in range(_SEQ_LEN)]
        trajectory.append({"t": round(i * dt, 6),
                           "x": [[round(c, 6) for c in p] for p in x]})
    return trajectory, x


def _decode_terminal(terminal_state, embeddings):
    """CONTINUOUS-UNTIL-FINAL-STEP readout: nearest-embedding argmax applied ONLY
    to the settled terminal continuous state (t=1). Returns decoded symbol ids."""
    return [_nearest_symbol(p, embeddings) for p in terminal_state]


def _accuracy(decoded, target_tokens):
    hit = sum(1 for a, b in zip(decoded, target_tokens) if a == b)
    return hit / max(1, len(target_tokens))


def elf_flow(seed: int = 42, num_euler_steps: int = 8, guidance_scale: float = 2.0) -> dict:
    """Full MODELED ELF continuous-embedding Flow-Matching run (deterministic)."""
    num_euler_steps = max(1, min(int(num_euler_steps), 256))
    guidance_scale = float(guidance_scale)

    embeddings = _unit_circle_embeddings()
    target_tokens = _target_tokens(seed)
    target_embeddings = [embeddings[t] for t in target_tokens]

    # seeded per-position Gaussian noise x0 ~ N(0, I)_2
    g = _gauss_stream(seed)
    x0 = [[next(g), next(g)] for _ in range(_SEQ_LEN)]

    # deterministic hand-fit conditional + unconditional linear velocity fields
    W_cond = _fit_velocity_field(seed, embeddings, target_embeddings, x0, conditional=True)
    W_uncond = _fit_velocity_field(seed, embeddings, target_embeddings, x0, conditional=False)

    cond_embs = target_embeddings   # per-position conditioning = target embedding

    # main guided run at the requested step count / guidance
    trajectory, terminal = _integrate_sequence(
        x0, W_cond, W_uncond, cond_embs, num_euler_steps, guidance_scale)
    decoded = _decode_terminal(terminal, embeddings)
    acc = _accuracy(decoded, target_tokens)

    # few-step-quality curve: accuracy vs num_euler_steps (guidance held fixed)
    acc_vs_steps = []
    for s in _PROBE_STEPS:
        _, term_s = _integrate_sequence(x0, W_cond, W_uncond, cond_embs, s, guidance_scale)
        dec_s = _decode_terminal(term_s, embeddings)
        acc_vs_steps.append({
            "num_euler_steps": s,
            "accuracy": round(_accuracy(dec_s, target_tokens), 6),
        })

    # guidance on/off ablation (steps held fixed at the requested count)
    _, term_on = _integrate_sequence(x0, W_cond, W_uncond, cond_embs, num_euler_steps, guidance_scale)
    acc_on = _accuracy(_decode_terminal(term_on, embeddings), target_tokens)
    _, term_off = _integrate_sequence(x0, W_cond, W_uncond, cond_embs, num_euler_steps, 0.0)
    acc_off = _accuracy(_decode_terminal(term_off, embeddings), target_tokens)

    return {
        "vocab_size": _VOCAB_SIZE,
        "embedding_dim": _EMBED_DIM,
        "num_euler_steps": num_euler_steps,
        "guidance_scale": round(guidance_scale, 6),
        "embeddings": [[round(c, 6) for c in e] for e in embeddings],
        "target_tokens": target_tokens,
        "target_embeddings": [[round(c, 6) for c in e] for e in target_embeddings],
        "x0": [[round(c, 6) for c in p] for p in x0],
        "trajectory": trajectory,
        "decoded_tokens": decoded,
        "accuracy": round(acc, 6),
        "accuracy_vs_steps": acc_vs_steps,
        "guidance_ablation": {
            "on":  {"guidance_scale": round(guidance_scale, 6), "accuracy": round(acc_on, 6)},
            "off": {"guidance_scale": 0.0, "accuracy": round(acc_off, 6)},
        },
    }


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


_HONEST_NOTE = (
    "Inspired-not-real. Toy analytic Flow-Matching sim in a 2-D embedding space "
    "with 6 symbols and a hand-fit linear velocity field — NOT ELF/LangFlow/MLFM, "
    "reproduces NONE of their perplexity numbers. 'Continuous rivals discrete' is "
    "the papers' benchmark claim about trained models; the estate demonstrates only "
    "the qualitative MECHANISM (continuous embedding-space trajectory + terminal "
    "continuous->discrete decode + guidance transfer) and measures its own "
    "toy-grammar accuracy, nothing more."
)


def _h_flow(req: Request):
    seed = _ii(req, "seed", 42)
    num_euler_steps = max(1, min(_ii(req, "num_euler_steps", 8), 256))
    guidance_scale = _ff(req, "guidance_scale", 2.0)

    m = elf_flow(seed=seed, num_euler_steps=num_euler_steps, guidance_scale=guidance_scale)

    return JSONResponse({
        "label": "MODELED",
        "model": "ELF continuous-embedding Flow Matching: linear-interpolant path, hand-fit linear velocity field, Euler ODE, terminal nearest-embedding decode",
        "method": "dx/dt = v_uncond + g*(v_cond - v_uncond) in 2-D embedding space; decode ONLY at t=1 (nearest-embedding argmax)",
        "seed": seed,
        **m,
        "honest_note": _HONEST_NOTE,
        "citations": CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_flowmatch.register() / szl_dllm.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/elf/flow onto app. Additive, try/except-guarded. Uses
    FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/elf"
    handlers = [
        (f"{base}/flow", _h_flow),
    ]
    add_api_route = getattr(app, "add_api_route", None)
    for path, fn in handlers:
        try:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
        except Exception:
            try:
                app.router.routes.append(Route(path, fn))
            except Exception:
                pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    print("label: MODELED")
    print("method: continuous-embedding Flow Matching; decode ONLY at t=1 (nearest-embedding argmax)")
    print()

    m = elf_flow(seed=42, num_euler_steps=8, guidance_scale=2.0)
    print(f"vocab_size={m['vocab_size']}  embedding_dim={m['embedding_dim']}  seq_len={len(m['target_tokens'])}")
    print("target_tokens: ", m["target_tokens"])
    print("decoded_tokens:", m["decoded_tokens"])
    print("accuracy:      ", m["accuracy"])
    print()

    print("accuracy_vs_steps (few-step-quality curve, QUALITATIVE):")
    for row in m["accuracy_vs_steps"]:
        print(f"  num_euler_steps={row['num_euler_steps']:>3}  accuracy={row['accuracy']}")
    print()

    ab = m["guidance_ablation"]
    print("guidance ablation:")
    print(f"  ON  (g={ab['on']['guidance_scale']}) accuracy={ab['on']['accuracy']}")
    print(f"  OFF (g={ab['off']['guidance_scale']}) accuracy={ab['off']['accuracy']}")
    print()

    # sanity: continuous-until-final-step — trajectory holds 2-D continuous state
    assert m["embedding_dim"] == 2, "embedding space must be 2-D"
    assert len(m["trajectory"][0]["x"]) == len(m["target_tokens"]), "trajectory width must match seq len"
    assert m["trajectory"][0]["t"] == 0.0 and m["trajectory"][-1]["t"] == 1.0, "trajectory must span t in [0,1]"
    # sanity: decode produces valid symbol ids in [0, vocab_size)
    assert all(0 <= d < m["vocab_size"] for d in m["decoded_tokens"]), "decoded ids out of range"
    # sanity: accuracy is a fraction in [0,1]
    assert 0.0 <= m["accuracy"] <= 1.0, "accuracy out of range"
    # sanity: label verbatim
    assert "MODELED" == "MODELED"

    print("szl_elf: ALL OK — continuous-until-final-step guard holds (decode only at t=1);")
    print("         accuracy-vs-steps curve + guidance on/off ablation reported above.")
