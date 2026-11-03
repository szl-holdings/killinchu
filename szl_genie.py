# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_genie.py — SZL generative interactive world-model / latent-action grid-world endpoint.

Exposes a MODELED, toy latent-action-driven generative world-model rollout — a small,
clean-room simulation of the COMPUTATION SHAPE popularized by Google DeepMind's Genie
family (Genie, Genie 2, Genie 3) — as a same-origin REST endpoint. This is the organ's
GENERATIVE / INTERACTIVE counterpart to szl_worldmodel.py: that module MODELS a JEPA-style
PREDICTOR (given latents, predict the next latent and score prediction error). This module
instead MODELS a GENERATOR: given a small learned/clustered set of discrete latent action
codes, it deterministically GENERATES ("plays out") a brand-new grid-world state sequence,
one action at a time — i.e. it is *playable*, not merely predictive.

  GET  /api/<ns>/v1/genie/rollout?seed=&grid=&horizon=&actions=

THE GENIE PRINCIPLE (what this models, clean-room)
  Genie (Bruce, Segar, Mnih et al. 2024, arXiv:2402.15391) learns a small discrete set of
  LATENT ACTIONS in a fully unsupervised way from unlabelled video, then uses an
  autoregressive dynamics model to generate a new interactive environment frame-by-frame,
  conditioned on those latent action codes — no ground-truth action labels, no game engine.
  Genie 2 and Genie 3 (Google DeepMind blog, 2024/2025) scale this to large 3D, playable,
  minutes-long, real-time environments. This module simulates the SHAPE of that pipeline —
  (1) cluster synthetic state-transition deltas into a small codebook of latent action
  codes (k-means-style, deterministic), (2) autoregressively GENERATE a new grid-world
  state sequence by applying a sampled/requested sequence of those latent action codes to
  an evolving NxN lattice, (3) score a coherence/consistency metric for the generated
  rollout — with NO real video, NO trained tokenizer/dynamics model, and NO proprietary
  weights of any kind.

Returned JSON fields
--------------------
  label                  : "MODELED" (always — a toy simulation of the METHOD)
  model                  : "Toy latent-action grid-world generator (Genie-style, clean-room)"
  seed                   : RNG seed used (deterministic; same seed -> identical rollout)
  grid_size              : N, the generated world is an NxN state lattice
  n_latent_actions       : size of the inferred/clustered discrete latent-action codebook
  rollout_horizon        : number of generated frames/steps
  action_codes           : list[int] — the latent-action-code sequence applied, one per step
  latent_action_codebook : list of the clustered latent-action centroids (deterministic
                            k-means-style cluster of synthetic state-delta vectors)
  generated_states       : list of per-step generated grid summaries (compact stats, not
                            the full lattice, to keep payload small): mean, active_cells,
                            delta_from_prev
  coherence_score        : 0..1 MODELED consistency score — how well the generated rollout
                            stays "on-manifold" step-to-step (Genie 3's headline property is
                            multi-minute world CONSISTENCY; this is an illustrative analogue)
  honest_note            : plain-language honesty disclaimer
  citations              : dict of citable sources
  computed_at            : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form TOY latent-action grid-world — NOT a trained
  generative world model, NOT run on real video, and NOT a reproduction of Genie / Genie 2 /
  Genie 3 in any respect (no video tokenizer, no autoregressive transformer dynamics model,
  no learned latent-action model, no borrowed weights, no benchmark numbers). It is a small
  illustrative simulation of the COMPUTATION SHAPE only: cluster deltas into discrete latent
  action codes, then apply those codes to deterministically evolve a small grid. The label
  "MODELED" is returned verbatim and displayed verbatim by the surface; it is never upgraded
  client-side. SZL claims NONE of Google DeepMind's Genie methodology, code, or results as
  its own, and does not claim parity with any real Genie model.

CITATIONS (clean-room; none claimed as SZL's own):
  Genie (v1) — latent-action world model from unlabelled video:
    Bruce, Segar, Mnih et al. (2024) "Genie: Generative Interactive Environments".
    arXiv:2402.15391. https://arxiv.org/abs/2402.15391
  Genie 2 — large-scale foundation world model (Google DeepMind blog):
    https://deepmind.google/discover/blog/genie-2-a-large-scale-foundation-world-model/
  Genie 3 — a new frontier for world models (Google DeepMind blog):
    https://deepmind.google/discover/blog/genie-3-a-new-frontier-for-world-models/

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

import math
import json
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "Genie (v1) — Bruce, Segar, Mnih et al. arXiv:2402.15391": "https://arxiv.org/abs/2402.15391",
    "Genie 2 — large-scale foundation world model (Google DeepMind)": "https://deepmind.google/discover/blog/genie-2-a-large-scale-foundation-world-model/",
    "Genie 3 — a new frontier for world models (Google DeepMind)": "https://deepmind.google/discover/blog/genie-3-a-new-frontier-for-world-models/",
}


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _unit(rng) -> float:
    """Map a 0..1 LCG draw to a roughly zero-centered value in [-1, 1]."""
    return 2.0 * next(rng) - 1.0


# ---------------------------------------------------------------------------
# MODELED latent-action clustering (k-means-style, deterministic, closed-form)
# ---------------------------------------------------------------------------
def _cluster_latent_actions(rng, n_latent_actions: int) -> list:
    """
    TOY stand-in for Genie's unsupervised latent-action model: cluster synthetic
    state-transition delta vectors (dx, dy, dstate) into a small discrete codebook.

    Real Genie learns this end-to-end from raw video with no action labels
    (Bruce, Segar, Mnih et al. 2024, arXiv:2402.15391, Sec. 3.2 "Latent Action Model").
    Here we deterministically place n_latent_actions centroids on a small ring in
    (dx, dy, dstate) delta-space — a k-means-style codebook, not a learned one.
    """
    codebook = []
    for i in range(n_latent_actions):
        ang = (i / max(n_latent_actions, 1)) * 2.0 * math.pi
        jitter = 0.12 * _unit(rng)
        dx = round(math.cos(ang + jitter), 4)
        dy = round(math.sin(ang + jitter), 4)
        dstate = round(0.4 + 0.3 * next(rng), 4)  # magnitude of state perturbation
        codebook.append({"code": i, "dx": dx, "dy": dy, "dstate": dstate})
    return codebook


# ---------------------------------------------------------------------------
# MODELED generative rollout: apply latent action codes to evolve an NxN grid
# ---------------------------------------------------------------------------
def _genie_rollout(
    seed: int = 42,
    grid: int = 8,
    horizon: int = 16,
    n_latent_actions: int = 6,
    actions: list = None,
) -> dict:
    """
    Deterministically GENERATE an interactive rollout of a toy NxN state-lattice
    "world", driven step-by-step by a sequence of discrete latent action codes.

    This mirrors the SHAPE of Genie's inference loop (Bruce, Segar, Mnih et al. 2024):
      1. A small discrete latent-action codebook exists (here: clustered, not learned).
      2. At each step, one latent action code is applied; an autoregressive dynamics
         model (here: closed-form deterministic update) generates the NEXT frame/state
         conditioned on the current state + the chosen action code.
      3. The world is GENERATED forward, action-by-action — it is playable/interactive,
         not merely a passive prediction of a pre-recorded ground-truth trajectory
         (contrast with szl_worldmodel.py's JEPA-style predictor, which scores prediction
         error against an existing observed latent path).

    Pure stdlib; deterministic — same seed + same action sequence -> identical rollout.
    """
    rng = _lcg(seed)
    grid = max(2, min(grid, 64))
    horizon = max(1, min(horizon, 128))
    n_latent_actions = max(2, min(n_latent_actions, 32))

    codebook = _cluster_latent_actions(rng, n_latent_actions)

    # Deterministic requested/sampled action-code sequence for this rollout.
    if actions:
        action_codes = [max(0, min(int(a), n_latent_actions - 1)) for a in actions][:horizon]
        while len(action_codes) < horizon:
            action_codes.append(int(next(rng) * n_latent_actions) % n_latent_actions)
    else:
        action_codes = [int(next(rng) * n_latent_actions) % n_latent_actions for _ in range(horizon)]

    # Initial NxN lattice state — deterministic seed pattern (stand-in for the first
    # generated frame conditioned on a prompt image, as in Genie 2/3's image-conditioned
    # generation).
    state = [[round(0.5 + 0.5 * math.sin((r * 1.7 + c * 2.3) + next(rng)), 4)
              for c in range(grid)] for r in range(grid)]

    def cell_mean(s):
        flat = [v for row in s for v in row]
        return round(sum(flat) / max(len(flat), 1), 5)

    def active_cells(s, thresh=0.5):
        return sum(1 for row in s for v in row if v > thresh)

    generated_states = []
    prev_mean = cell_mean(state)
    coherence_terms = []

    for t, code in enumerate(action_codes):
        act = codebook[code]
        # Autoregressive "dynamics model" step (closed-form, deterministic): the latent
        # action code's (dx, dy, dstate) perturbs the lattice by translating influence
        # along (dx, dy) and nudging cell magnitudes by dstate, generating the NEXT frame.
        new_state = [[0.0] * grid for _ in range(grid)]
        for r in range(grid):
            for c in range(grid):
                # sample source cell shifted by the latent action's direction (wrapped —
                # a toy analogue of "moving" through the generated world)
                sr = int(round(r - act["dy"] * 1.5)) % grid
                sc = int(round(c - act["dx"] * 1.5)) % grid
                base = state[sr][sc]
                drift = act["dstate"] * 0.25 * math.sin(0.5 * t + r * 0.3 + c * 0.3)
                residual = 0.03 * _unit(rng)  # bounded generative residual (irreducible variety)
                v = base + drift + residual
                new_state[r][c] = round(max(0.0, min(1.0, v)), 4)
        state = new_state

        cur_mean = cell_mean(state)
        delta = round(cur_mean - prev_mean, 5)
        generated_states.append({
            "step": t,
            "action_code": code,
            "mean": cur_mean,
            "active_cells": active_cells(state),
            "delta_from_prev": delta,
        })
        # coherence term: smaller frame-to-frame jumps => a more "on-manifold"/coherent
        # generated world (illustrative analogue of Genie 3's headline multi-minute
        # world-consistency property — NOT a reproduction of any measured benchmark).
        coherence_terms.append(abs(delta))
        prev_mean = cur_mean

    # coherence_score: 1.0 = perfectly smooth generated evolution, decaying with the
    # average magnitude of frame-to-frame jumps (bounded 0..1).
    mean_jump = sum(coherence_terms) / max(len(coherence_terms), 1)
    coherence_score = round(max(0.0, min(1.0, 1.0 - 6.0 * mean_jump)), 4)

    return {
        "grid_size": grid,
        "n_latent_actions": n_latent_actions,
        "rollout_horizon": horizon,
        "latent_action_codebook": codebook,
        "action_codes": action_codes,
        "generated_states": generated_states,
        "coherence_score": coherence_score,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _fi(req: Request, key: str, default) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return float(default)


def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _parse_actions(req: Request):
    raw = req.query_params.get("actions")
    if not raw:
        return None
    out = []
    for tok in raw.split(","):
        tok = tok.strip()
        if tok == "":
            continue
        try:
            out.append(int(float(tok)))
        except Exception:
            continue
    return out or None


def _h_rollout(req: Request):
    seed             = _ii(req, "seed",  42)
    grid             = max(2, min(_ii(req, "grid",  8), 64))
    horizon          = max(1, min(_ii(req, "horizon", 16), 128))
    n_latent_actions = max(2, min(_ii(req, "n_latent_actions", 6), 32))
    actions          = _parse_actions(req)

    roll = _genie_rollout(
        seed=seed, grid=grid, horizon=horizon,
        n_latent_actions=n_latent_actions, actions=actions,
    )

    return JSONResponse({
        "label":                    "MODELED",
        "model":                    "Toy latent-action grid-world generator (Genie-style, clean-room)",
        "method":                   "Cluster synthetic state-deltas into a discrete latent-action "
                                     "codebook, then autoregressively GENERATE a new NxN grid-world "
                                     "rollout by applying a requested/sampled action-code sequence "
                                     "(interactive/generative — distinct from a passive predictor)",
        "seed":                     seed,
        "grid_size":                roll["grid_size"],
        "n_latent_actions":         roll["n_latent_actions"],
        "rollout_horizon":          roll["rollout_horizon"],
        "latent_action_codebook":   roll["latent_action_codebook"],
        "action_codes":             roll["action_codes"],
        "generated_states":         roll["generated_states"],
        "coherence_score":          roll["coherence_score"],
        "honest_note": (
            "MODELED: this is a deterministic, closed-form TOY latent-action grid-world — "
            "NOT a trained generative world model and NOT a reproduction of Google DeepMind's "
            "Genie, Genie 2, or Genie 3 in any respect. There is NO video tokenizer, NO "
            "autoregressive transformer dynamics model, NO learned latent-action model, and NO "
            "borrowed weights or benchmark numbers. It only mimics the COMPUTATION SHAPE: cluster "
            "state-transition deltas into a small discrete latent-action codebook (k-means-style, "
            "not learned), then apply a chosen action-code sequence to deterministically generate "
            "('play out') a new grid-world state sequence, action by action. coherence_score is a "
            "MODELED illustrative analogue of world-consistency, not a measured benchmark result. "
            "Deterministic: same seed + same actions -> identical rollout. Cite: Bruce, Segar, Mnih "
            "et al. 2024 arXiv:2402.15391 (Genie); deepmind.google Genie 2 blog; deepmind.google "
            "Genie 3 blog. SZL claims NONE of Google DeepMind's Genie methodology, code, weights, "
            "or results as its own, and does not claim parity with any real Genie model."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_interpretability.register() / szl_worldmodel.register()
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/genie/rollout onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/genie"
    handlers = [
        (f"{base}/rollout", _h_rollout),
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
    roll = _genie_rollout(seed=42, grid=8, horizon=16, n_latent_actions=6)
    print("label: MODELED")
    print("grid_size:", roll["grid_size"])
    print("n_latent_actions:", roll["n_latent_actions"])
    print("rollout_horizon:", roll["rollout_horizon"])
    print("action_codes:", roll["action_codes"])
    print("coherence_score:", roll["coherence_score"])
    print("generated_states[:3]:", roll["generated_states"][:3])
    print("latent_action_codebook[0]:", roll["latent_action_codebook"][0])
