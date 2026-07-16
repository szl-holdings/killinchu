# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_rauq.py — ADDITIVE Recurrent Attention-based Uncertainty Quantification (RAUQ) scorer for
killinchu's frontier surface (backs a11oy static/3d/surfaces/rauq.js).

RAUQ (Vazhentsev, Rvanova, Kuzmin, Fadeeva, Lazichny, Panchenko, Panov, Baldwin, Sachan, Nakov,
Shelmanov 2025; arXiv:2505.20045, "Uncertainty-Aware Attention Heads: Efficient Unsupervised
Uncertainty Quantification for LLMs") is an unsupervised, single-forward-pass hallucination
detector for white-box LLMs. Its observation: for certain "uncertainty-aware" attention heads, the
attention weight a token pays to its PRECEDING token systematically DROPS during incorrect
generations. RAUQ (a) auto-selects such heads, (b) recurrently aggregates, per generated token, a
confidence that combines the token log-probability with the selected head's attention-to-previous
weight, and (c) rolls these into a sequence-level uncertainty score in one pass, at <1% latency
overhead and with no labels.

This module simulates the RAUQ score deterministically (seeded, NO LLM): it generates a sequence
of modeled per-token log-probs and per-head attention-to-previous weights for a "confident" run
and a "hallucinated" run (where attention-to-previous drops on wrong tokens). It selects the most
uncertainty-aware head, aggregates the recurrent per-token confidence g_t = alpha * a_prev_t +
(1-alpha) * exp(logprob_t), and reports the sequence uncertainty u = 1 - mean(g_t) for each run,
plus the separation (hallucinated_u - confident_u) — the mechanism-level reason RAUQ discriminates.

Reported (field names read verbatim by rauq.js):
  seq_len                 — T generated tokens scored
  num_heads               — attention heads considered
  selected_head           — index of the auto-selected uncertainty-aware head
  uncertainty_confident   — RAUQ sequence uncertainty on the confident run (MODELED)
  uncertainty_halluc      — RAUQ sequence uncertainty on the hallucinated run (MODELED)
  separation              — halluc - confident (higher == better discrimination)
  token_uncertainty       — per-token uncertainty (1 - g_t) on the hallucinated run

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic uncertainty-scoring SIMULATION. NOT an LLM running; NO real attention
    weights, NO GPU, NO trained model. The log-probs and attention profiles are SEEDED inputs /
    MODELED references, NOT measured on any real generation.
  * "separation" is a property of the modeled runs + the RAUQ aggregation, honestly labeled, not
    an AUROC / hallucination-detection claim about any real model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/rauq/score — RAUQ attention-based uncertainty snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "rauq": ("Vazhentsev, Rvanova, Kuzmin, Fadeeva, Lazichny, Panchenko, Panov, Baldwin, Sachan, "
             "Nakov, Shelmanov (2025) Uncertainty-Aware Attention Heads: Efficient Unsupervised "
             "Uncertainty Quantification for LLMs (RAUQ) — arXiv:2505.20045 · "
             "https://arxiv.org/abs/2505.20045"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | RAUQ_UNCERTAINTY_SIM | NOT_LIVE | NO_MODEL | SCORES_ARE_MODELED"


# ---------------------------------------------------------------------------
# Deterministic LCG PRNG (no numpy, no stdlib random). Numerical Recipes params.
# ---------------------------------------------------------------------------
class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (seed ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def normal(self) -> float:
        u1 = max(1e-12, self.uniform())
        u2 = self.uniform()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _gen_run(rng, T: int, H: int, hallucinated: bool):
    """Return per-token (logprob, [attn_to_prev per head]) for one run.
    In the hallucinated run, the uncertainty-aware head's attention-to-previous DROPS and
    log-probs fall on the 'wrong' tokens."""
    logprobs = []
    attn = []  # attn[t] = list over heads of attention-to-previous weight in [0,1]
    aware_head = H - 1  # last head is the modeled uncertainty-aware one
    for t in range(T):
        wrong = hallucinated and (rng.uniform() < 0.4)  # some tokens are wrong in a bad run
        lp = -0.05 - 0.03 * abs(rng.normal()) if not wrong else -1.2 - 0.5 * abs(rng.normal())
        logprobs.append(lp)
        row = []
        for hh in range(H):
            base = 0.55 + 0.15 * rng.uniform()
            if hh == aware_head and wrong:
                base *= 0.35   # the signature drop in attention to the preceding token
            row.append(_clip01(base))
        attn.append(row)
    return logprobs, attn, aware_head


def _rauq_sequence(logprobs, attn, head, alpha: float):
    """Recurrent per-token confidence g_t = alpha*attn_to_prev + (1-alpha)*exp(logprob);
    sequence uncertainty = 1 - mean(g_t). Returns (uncertainty, per_token_uncertainty)."""
    T = len(logprobs)
    g = []
    for t in range(T):
        conf = alpha * attn[t][head] + (1.0 - alpha) * _math.exp(logprobs[t])
        g.append(_clip01(conf))
    mean_g = sum(g) / T
    per_token_u = [round(1.0 - x, 6) for x in g]
    return 1.0 - mean_g, per_token_u


def rauq_score(seed: int = 42, seq_len: int = 32, num_heads: int = 8,
               alpha: float = 0.6) -> dict:
    """RAUQ attention-based uncertainty snapshot (MODELED).

    seq_len   — T generated tokens scored.
    num_heads — attention heads considered for the uncertainty-aware selection.
    alpha     — weight on attention-to-previous vs token log-prob in the recurrent confidence.
    seed      — RNG seed; identical inputs give identical output (deterministic).
    """
    T = max(2, min(2048, int(seq_len)))
    H = max(1, min(128, int(num_heads)))
    alpha = max(0.0, min(1.0, float(alpha)))
    rng = _LCG(int(seed) * 1_000_003 + T * 131 + H * 17)

    lp_c, at_c, aware = _gen_run(rng, T, H, hallucinated=False)
    lp_h, at_h, _ = _gen_run(rng, T, H, hallucinated=True)

    # Head auto-selection: pick the head with the largest mean attention-to-previous gap between
    # confident and hallucinated runs (the "uncertainty-aware" head). For the modeled runs this is
    # the seeded aware head, but we select it honestly by the same criterion RAUQ uses.
    best_head = 0
    best_gap = -1.0
    for hh in range(H):
        mc = sum(row[hh] for row in at_c) / T
        mh = sum(row[hh] for row in at_h) / T
        gap = mc - mh
        if gap > best_gap:
            best_gap = gap
            best_head = hh

    u_conf, _ = _rauq_sequence(lp_c, at_c, best_head, alpha)
    u_hal, per_token_u = _rauq_sequence(lp_h, at_h, best_head, alpha)
    separation = u_hal - u_conf

    return {
        "service": "rauq-uncertainty-quantification",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/rauq.js ---
        "seq_len": int(T),
        "num_heads": int(H),
        "selected_head": int(best_head),
        "alpha": float(alpha),
        "uncertainty_confident": round(float(u_conf), 6),
        "uncertainty_halluc": round(float(u_hal), 6),
        "separation": round(float(separation), 6),
        "token_uncertainty": per_token_u[:32],
        "aware_head_modeled": int(aware),
        "formulas": {
            "confidence": "g_t = alpha * attn_to_prev_t + (1 - alpha) * exp(logprob_t)",
            "sequence_uncertainty": "u = 1 - mean(g_t)  (single forward pass)",
            "head_selection": "argmax_h (mean attn_to_prev on correct - on incorrect)  (unsupervised)",
            "separation": "uncertainty_halluc - uncertainty_confident",
        },
        "compute_backend": {
            "backend": "CPU pure-Python recurrent attention-uncertainty simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic uncertainty-scoring sim; NO LLM, NO real attention "
                            "weights, NO GPU, NO trained model. A white-box LLM path is ROADMAP."),
        },
        "honest_note": ("MODELED RAUQ uncertainty. separation is a property of the modeled "
                        "confident/hallucinated runs + the recurrent aggregation, not an AUROC or "
                        "hallucination-detection claim about any real model."),
        "wired_into": "frontier ring — RAUQ attention-based uncertainty-quantification surface",
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (advisory uncertainty — never autonomous)",
        "citations": {"rauq": CITATIONS["rauq"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/rauq" % ns
    path = "%s/score" % base

    @app.get(path)
    async def _kc_rauq(seed: int = 42, seq_len: int = 32, num_heads: int = 8):  # noqa: ANN202
        try:
            return JSONResponse(rauq_score(seed=seed, seq_len=seq_len, num_heads=num_heads))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "rauq-uncertainty-quantification",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "uncertainty_halluc": None, "separation": None},
                                status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401 — Route fallback parity with template
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = rauq_score(seed=42, seq_len=32, num_heads=8)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "num_heads", "selected_head"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("uncertainty_confident", "uncertainty_halluc", "separation"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["token_uncertainty"], list) and r["token_uncertainty"], r

    # bounds: uncertainties in [0,1]; hallucinated run should score MORE uncertain (separation>0).
    assert 0.0 <= r["uncertainty_confident"] <= 1.0, r["uncertainty_confident"]
    assert 0.0 <= r["uncertainty_halluc"] <= 1.0, r["uncertainty_halluc"]
    assert r["separation"] > 0.0, r["separation"]
    assert 0 <= r["selected_head"] < r["num_heads"], r
    out["metrics"] = {"uncertainty_confident": r["uncertainty_confident"],
                      "uncertainty_halluc": r["uncertainty_halluc"],
                      "separation": r["separation"], "selected_head": r["selected_head"]}

    assert "2505.20045" in r["citations"]["rauq"], r["citations"]

    # determinism
    r2 = rauq_score(seed=42, seq_len=32, num_heads=8)
    assert r2["separation"] == r["separation"], "non-deterministic"
    assert r2["token_uncertainty"] == r["token_uncertainty"], "non-deterministic"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2))
    assert res["ok"] is True
    print("ALL OK", file=sys.stderr)
    print("ALL OK")
