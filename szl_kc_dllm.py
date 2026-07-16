# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_dllm.py — ADDITIVE DIFFUSION-LLM (masked-denoising) reverse-process simulator for
killinchu's frontier surface (backs a11oy static/3d/surfaces/dllm.js).

Diffusion large language models generate text NOT left-to-right but by a forward MASKING
process that corrupts a clean sequence to all-mask, and a learned REVERSE process that
iteratively un-masks tokens over T denoising steps. LLaDA (Nie, Zhu, You, Zhang, Ou, Hu,
Zhou, Lin, Wen, Li 2025 — "Large Language Diffusion Models", arXiv:2502.09992) trains an
8B diffusion LM from scratch that optimizes a likelihood lower bound and matches LLaMA3 8B
in-context; it parameterizes the reverse process by a Transformer predicting masked tokens.
Earlier absorbing/masked discrete diffusion (Austin et al. D3PM arXiv:2107.03006; Lou, Meng,
Ermon SEDD arXiv:2310.16834) established the masked-token reverse chain this organ re-derives.

Deterministic MODELED reverse-denoising (seeded, no live model):
  * A sequence of L positions starts fully MASKED. Over T steps the mask ratio follows a
    cosine schedule m(t) = cos(pi/2 * t/T)^2 from 1.0 (all mask) down to 0.0 (all revealed).
  * At each step we reveal the positions whose modeled per-token confidence (a seeded logit
    magnitude) is highest among the still-masked set — the standard confidence/low-remask
    strategy. Revealed count per step = round(L*(m(t-1)-m(t))).
  * We track: tokens revealed per step, cumulative revealed, and a MODELED cross-entropy
    "denoising loss" proxy loss(t) = -mean(log sigma(confidence)) over the newly revealed
    tokens, which decays as easy (high-confidence) tokens are committed first.
  * elbo_proxy = mean over steps of loss(t) weighted by the reveal fraction (a modeled
    likelihood-lower-bound stand-in, NOT the trained ELBO).

  mask ratio schedule : m(t) = cos(pi/2 * t/T)^2
  reveal(t)           : round(L * (m(t-1) - m(t)))
  denoise_loss(t)     : -mean(log sigmoid(conf_i)) over newly revealed i
  steps_to_half       : first t with cumulative_revealed >= L/2

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic masked-denoising SIMULATION. NOT LLaDA / SEDD / D3PM running; NO
    live model, NO GPU, NO trained weights. Per-token "confidence" logits are SEEDED PRNG
    draws, NOT a real Transformer's outputs. The cosine mask schedule is the real algorithm;
    the confidence values are modeled inputs.
  * elbo_proxy and denoise_loss are MODELED order-of-magnitude proxies that make the reverse
    process inspectable; they are NOT the paper's measured likelihood bound.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/dllm/denoise  — diffusion-LLM reverse-denoising snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | MASKED_DENOISE_SIM | NOT_LIVE | NO_MODEL | ELBO_IS_PROXY"

CITATIONS = {
    "llada": ("Nie, Zhu, You, Zhang, Ou, Hu, Zhou, Lin, Wen, Li (2025) Large Language "
              "Diffusion Models (LLaDA) — https://arxiv.org/abs/2502.09992"),
    "sedd": ("Lou, Meng, Ermon (2023) Discrete Diffusion Modeling by Estimating the Ratios "
             "of the Data Distribution (SEDD) — https://arxiv.org/abs/2310.16834"),
    "d3pm": ("Austin, Johnson, Ho, Tarlow, van den Berg (2021) Structured Denoising "
             "Diffusion Models in Discrete State-Spaces (D3PM) — https://arxiv.org/abs/2107.03006"),
}


class _LCG:
    """Small deterministic linear-congruential PRNG (numerical-recipes constants).
    Pure stdlib, no numpy, no stdlib random. Same seed => identical stream."""

    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) & 0xFFFFFFFFFFFFFFFF) or 0x9E3779B97F4A7C15

    def _next(self) -> int:
        self._s = (6364136223846793005 * self._s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self._s

    def random(self) -> float:
        return (self._next() >> 11) / float(1 << 53)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = _math.exp(-x)
        return 1.0 / (1.0 + z)
    z = _math.exp(x)
    return z / (1.0 + z)


def dllm_denoise(seed: int = 42, seq_len: int = 64, steps: int = 16) -> dict:
    """Diffusion-LLM reverse-denoising snapshot (MODELED).

    seq_len — L, number of token positions (starts fully masked).
    steps   — T, number of reverse denoising steps.
    seed    — PRNG seed; identical inputs give identical output (deterministic).
    """
    L = max(4, min(4096, int(seq_len)))
    T = max(2, min(512, int(steps)))
    rng = _LCG(int(seed) * 2_654_435_761 + L * 97 + T * 7)

    # Modeled per-token confidence logits (seeded): higher => revealed earlier.
    conf = [(_math.log(rng.random() + 1e-9) * -1.0) for _ in range(L)]  # ~exponential magnitudes
    order = sorted(range(L), key=lambda i: conf[i], reverse=True)  # reveal high-conf first

    def mask_ratio(t: int) -> float:
        return _math.cos(_math.pi / 2.0 * (t / T)) ** 2

    revealed_flags = [False] * L
    cursor = 0
    per_step_reveal = []
    per_step_loss = []
    cumulative = []
    total_rev = 0
    prev_masked = L  # m(0) = 1.0 -> all masked
    for t in range(1, T + 1):
        target_masked = int(round(L * mask_ratio(t)))
        reveal_n = max(0, prev_masked - target_masked)
        # never over-reveal past L
        reveal_n = min(reveal_n, L - cursor)
        newly = order[cursor:cursor + reveal_n]
        cursor += reveal_n
        for i in newly:
            revealed_flags[i] = True
        if newly:
            step_loss = -sum(_math.log(_sigmoid(conf[i]) + 1e-12) for i in newly) / len(newly)
        else:
            step_loss = 0.0
        total_rev += reveal_n
        per_step_reveal.append(int(reveal_n))
        per_step_loss.append(round(float(step_loss), 6))
        cumulative.append(int(total_rev))
        prev_masked = target_masked

    # commit any residual (schedule rounding) on the final step
    if cursor < L:
        newly = order[cursor:]
        extra = len(newly)
        for i in newly:
            revealed_flags[i] = True
        per_step_reveal[-1] += extra
        total_rev += extra
        cumulative[-1] = total_rev
        cursor = L

    all_revealed = all(revealed_flags)
    # ELBO proxy: reveal-fraction-weighted mean denoising loss (MODELED likelihood-bound proxy).
    denom = sum(per_step_reveal) or 1
    elbo_proxy = sum(per_step_loss[k] * per_step_reveal[k] for k in range(T)) / denom
    # steps to reveal half the sequence
    half = L / 2.0
    steps_to_half = next((k + 1 for k, c in enumerate(cumulative) if c >= half), T)
    final_loss = per_step_loss[-1]
    initial_loss = next((v for v in per_step_loss if v > 0), 0.0)

    per_step_reveal_view = [int(x) for x in per_step_reveal[:32]]
    mask_schedule_view = [round(mask_ratio(t), 6) for t in range(0, min(T, 32) + 1)]

    return {
        "service": "diffusion-llm-denoise",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/dllm.js ---
        "seq_len": int(L),
        "steps": int(T),
        "tokens_revealed_total": int(total_rev),
        "all_revealed": bool(all_revealed),
        "steps_to_half": int(steps_to_half),
        "elbo_proxy": round(float(elbo_proxy), 6),
        "initial_denoise_loss": round(float(initial_loss), 6),
        "final_denoise_loss": round(float(final_loss), 6),
        "per_step_reveal": per_step_reveal_view,          # [int]
        "per_step_denoise_loss": [round(v, 6) for v in per_step_loss[:32]],  # [float]
        "mask_ratio_schedule": mask_schedule_view,        # [float] cosine schedule
        "formulas": {
            "mask_ratio": "m(t) = cos(pi/2 * t/T)^2",
            "reveal_per_step": "round(L*(m(t-1)-m(t)))",
            "denoise_loss": "-mean(log sigmoid(confidence)) over newly revealed",
            "elbo_proxy": "reveal-weighted mean denoise_loss (MODELED likelihood-bound proxy)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python masked-denoising simulation (seeded LCG)",
            "label": "MODELED",
            "honest_note": ("Deterministic cosine-schedule un-masking sim; NO live diffusion "
                            "LM, NO GPU, NO trained weights. Confidence logits are seeded PRNG "
                            "draws. The measured-on-a-real-diffusion-LM path is ROADMAP."),
        },
        "honest_note": ("MODELED reverse-denoising of a masked diffusion LM. NOT LLaDA/SEDD/D3PM "
                        "running; NO live model, NO GPU, NO trained weights. The cosine mask "
                        "schedule is the real algorithm; confidences and the ELBO/loss proxies "
                        "are modeled. Advisory to Λ (Conjecture 1); adds nothing to the locked-8."),
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (denoising snapshot advisory — never an autonomous action)",
        "citations": {"llada": CITATIONS["llada"], "sedd": CITATIONS["sedd"], "d3pm": CITATIONS["d3pm"]},
        "wired_into": "frontier ring — Diffusion-LLM surface (masked reverse-denoising)",
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive). Mirrors szl_kc_specdec.register exactly.
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/dllm" % ns
    path = "%s/denoise" % base

    @app.get(path)
    async def _kc_dllm(seed: int = 42, seq_len: int = 64, steps: int = 16):  # noqa: ANN202
        try:
            return JSONResponse(dllm_denoise(seed=seed, seq_len=seq_len, steps=steps))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "diffusion-llm-denoise",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "elbo_proxy": None, "all_revealed": None},
                                status_code=200)

    try:  # Starlette Route fallback (mirror specdec posture)
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_dllm_route(request):  # pragma: no cover
            q = request.query_params
            return _SJSON(dllm_denoise(seed=int(q.get("seed", 42)),
                                       seq_len=int(q.get("seq_len", 64)),
                                       steps=int(q.get("steps", 16))))

        app.router.routes.append(Route(path, _kc_dllm_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = dllm_denoise(seed=42, seq_len=64, steps=16)

    # (a) honest label verbatim + typed fields the frontend reads.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f, t in (("seq_len", int), ("steps", int), ("tokens_revealed_total", int),
                 ("steps_to_half", int), ("elbo_proxy", float), ("final_denoise_loss", float)):
        assert isinstance(r[f], t) or isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["per_step_reveal"], list) and r["per_step_reveal"], r
    assert all(isinstance(x, int) for x in r["per_step_reveal"]), r["per_step_reveal"]
    assert isinstance(r["mask_ratio_schedule"], list) and r["mask_ratio_schedule"], r

    # (b) invariant: every position ends revealed; total == seq_len; loss decays.
    assert r["all_revealed"] is True, r
    assert r["tokens_revealed_total"] == r["seq_len"], r
    assert 1 <= r["steps_to_half"] <= r["steps"], r
    # mask schedule is monotone non-increasing from ~1.0
    ms = r["mask_ratio_schedule"]
    assert abs(ms[0] - 1.0) < 1e-6, ms[0]
    assert all(ms[i] >= ms[i + 1] - 1e-9 for i in range(len(ms) - 1)), ms
    # easy-first: initial denoise loss <= final denoise loss (hard tokens committed later)
    assert r["initial_denoise_loss"] <= r["final_denoise_loss"] + 1e-9, r
    out["metrics"] = {"elbo_proxy": r["elbo_proxy"], "steps_to_half": r["steps_to_half"],
                      "final_denoise_loss": r["final_denoise_loss"],
                      "tokens_revealed_total": r["tokens_revealed_total"]}

    # (c) citations are real arxiv URLs.
    assert "arxiv.org/abs/2502.09992" in r["citations"]["llada"], r["citations"]
    out["citations_ok"] = True

    # (d) determinism: same inputs -> identical reveal profile + elbo.
    r2 = dllm_denoise(seed=42, seq_len=64, steps=16)
    assert r2["per_step_reveal"] == r["per_step_reveal"], "non-deterministic reveal"
    assert r2["elbo_proxy"] == r["elbo_proxy"], "non-deterministic elbo"
    # different seed -> different confidence order (very likely different profile)
    r3 = dllm_denoise(seed=7, seq_len=64, steps=16)
    assert r3["all_revealed"] is True, r3
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
    print("ALL OK")
