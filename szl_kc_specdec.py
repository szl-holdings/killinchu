# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_specdec.py — ADDITIVE SPECULATIVE-DECODING energy-receipt simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/specdecode.js).

Speculative decoding runs a cheap DRAFT model to propose gamma tokens/step, then the target
model VERIFIES them in one parallel forward pass; a rejection-sampling correction makes the
output distribution IDENTICAL to plain target-model decoding (Leviathan et al. 2023;
Chen et al. 2023). This module simulates the accept/reject process deterministically, reports
the acceptance rate, mean accepted tokens/step, throughput speedup, and — the SZL addition —
a live "J/token saved" ENERGY RECEIPT.

Recent quantization-aware frontier variants motivate the energy angle: QSpec (arXiv:2410.11305)
pairs a low-precision draft with a high-precision verify for ~1.64x lossless speedup; QuantSpec
(arXiv:2502.10424) uses a hierarchical quantized KV cache; DeepSeek-V3 (arXiv:2412.19437)
repurposes its multi-token-prediction head for ~1.8x tokens/s. Each accepted draft token is one
fewer expensive target-model decode step, so speculative decoding is a direct energy win for the
llm-router.

Deterministic accept/reject model (seeded, no live model):
  * per proposed position i in a draft of length gamma, accept with a decaying probability
    a_i = alpha^(i+1) (later draft tokens are progressively harder to accept — the standard
    empirical accept-length profile). On the first rejection the step ends; a bonus token from
    the target's own distribution is always emitted (+1), per the algorithm.
  * accepted_len per step in [0 .. gamma]; tokens emitted per step = accepted_len + 1.

  acceptance_rate     = mean(accepted_len) / gamma
  mean_tokens_per_step= mean(accepted_len + 1)
  speedup_factor      = mean_tokens_per_step / (target-forward-passes/step)   (idealized, MODELED)
  E_baseline          = tokens * e_target                        (plain target decode)
  E_spec              = steps*(e_draft*gamma + e_target)         (draft gamma + one verify/step)
  joules_per_token_saved = (E_baseline - E_spec) / tokens        (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic accept/reject SIMULATION. NOT Medusa/EAGLE/QSpec running; NO live
    model, NO GPU, NO real KV cache. alpha (per-position accept decay) and the per-token energy
    constants are SEEDED inputs / order-of-magnitude MODELED references, NOT measured.
  * "lossless" is TRUE by construction because the modeled correction is the rejection-sampling
    identity — this is a property of the ALGORITHM, honestly labeled, not a measured claim about
    a specific model.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter. They make
    the energy trade-off inspectable; they do not certify an energy number.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/specdecode/simulate  — speculative-decoding energy-receipt snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import random as _random
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker, never fabricated
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.specdec+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": __import__("base64").b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_SPEC_PAYLOAD_TYPE = "application/vnd.szl.kc.specdec+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "qspec": ("Zhao, Wan, Zhang, Wang, Zhang, Wang, Xu (2024) QSPEC: Speculative Decoding with "
              "Complementary Quantization Schemes — arXiv:2410.11305"),
    "quantspec": ("Tiwari, Xi, Wang, Xu, Hooper, Mahoney, Keutzer, Gholami, Shanbhag, Chen (2025) "
                  "QuantSpec: Self-Speculative Decoding with Hierarchical Quantized KV Cache — "
                  "arXiv:2502.10424"),
    "deepseekv3": ("DeepSeek-AI et al. (2024) DeepSeek-V3 Technical Report (MTP head repurposed "
                   "for speculative decoding) — arXiv:2412.19437"),
    "leviathan": ("Leviathan, Kalman, Matias (2023) Fast Inference from Transformers via "
                  "Speculative Decoding — arXiv:2211.17192"),
    "chen": ("Chen, Borgeaud, Irving, Lespiau, Sifre, Jumper (2023) Accelerating LLM Decoding "
             "with Speculative Sampling — arXiv:2302.01318"),
}

# MODELED label — a deterministic accept/reject simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | ACCEPT_REJECT_SIM | NOT_LIVE | NO_MODEL | JOULES_ARE_MODELED"

# MODELED per-token energy references (order-of-magnitude only; NOT a live wattmeter).
# One target-model decode step is the expensive unit; the draft model is cheaper by a factor.
_E_TARGET = 1.0          # MODELED joules per target-model forward pass (the expensive unit)
_E_DRAFT = 0.18          # MODELED joules per draft-model token (cheap, quantized-draft style)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _simulate_steps(rng, gamma: int, trials: int, alpha: float):
    """Deterministic per-step accepted-length simulation.
    For each trial (one decode step): walk positions 0..gamma-1, accept position i with
    probability alpha^(i+1); stop at the first rejection. accepted_len in [0, gamma]."""
    accepted = []
    for _ in range(trials):
        acc = 0
        for i in range(gamma):
            if rng.random() <= alpha ** (i + 1):
                acc += 1
            else:
                break
        accepted.append(acc)
    return accepted


def specdec_simulate(seed: int = 42, draft_len: int = 6, trials: int = 256,
                     alpha: float = 0.82) -> dict:
    """Speculative-decoding energy-receipt snapshot (MODELED).

    draft_len — gamma, draft tokens proposed per step.
    trials    — number of decode steps simulated (the more, the tighter the mean).
    alpha     — per-position base accept probability (draft/target agreement); seeded input.
    seed      — RNG seed; identical inputs give identical output (deterministic).
    """
    gamma = max(1, min(32, int(draft_len)))
    trials = max(1, min(20000, int(trials)))
    alpha = max(0.05, min(0.999, float(alpha)))
    rng = _random.Random(int(seed) * 1_000_003 + gamma * 131 + trials)

    accepted = _simulate_steps(rng, gamma, trials, alpha)
    n = len(accepted)
    mean_accept_len = sum(accepted) / n
    acceptance_rate = mean_accept_len / gamma
    # tokens emitted per step = accepted_len + 1 (the always-emitted bonus/correction token)
    total_tokens = sum(a + 1 for a in accepted)
    mean_tokens_per_step = total_tokens / n

    # Idealized throughput speedup: plain decoding emits 1 token per target forward pass;
    # speculative decoding emits mean_tokens_per_step per ONE target verify pass. MODELED.
    speedup_factor = mean_tokens_per_step / 1.0

    # ENERGY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    e_baseline = total_tokens * _E_TARGET                     # plain target decode, 1 pass/token
    e_spec = n * (_E_DRAFT * gamma + _E_TARGET)               # draft gamma + one verify per step
    joules_saved = e_baseline - e_spec
    joules_per_token_saved = joules_saved / total_tokens if total_tokens else 0.0
    energy_reduction_pct = (joules_saved / e_baseline * 100.0) if e_baseline else 0.0

    # per_step_accept_lengths: the most recent representative steps (up to what the tab renders).
    per_step_accept_lengths = [int(a) for a in accepted[:16]]

    energy_receipt = {
        "joules_baseline_plain_decode": round(float(e_baseline), 4),
        "joules_speculative_decode": round(float(e_spec), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_token_saved": round(float(joules_per_token_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_target_per_pass_modeled": _E_TARGET,
        "e_draft_per_token_modeled": _E_DRAFT,
        "energy_note": ("MODELED joules — order-of-magnitude per-pass/per-token estimates, NOT a "
                        "live wattmeter. Each accepted draft token is one fewer target decode step; "
                        "this quantifies that as an energy-receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "speculative-decoding-energy-receipt",
        "service_version": "szl-kc-specdec-v0.1",
        "seed": int(seed),
        "inputs": {"draft_len": gamma, "trials": trials, "alpha": alpha},
        "acceptance_rate": round(float(acceptance_rate), 6),
        "mean_accept_len": round(float(mean_accept_len), 6),
        "mean_tokens_per_step": round(float(mean_tokens_per_step), 6),
        "speedup_factor": round(float(speedup_factor), 6),
        "lossless": True,
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (energy-receipt advisory — never an autonomous action)",
        "citations": [CITATIONS["qspec"], CITATIONS["quantspec"], CITATIONS["deepseekv3"],
                      CITATIONS["leviathan"], CITATIONS["chen"]],
        "honesty": ("Deterministic accept/reject speculative-decoding simulation. NOT Medusa/EAGLE/"
                    "QSpec running; NO live model, NO GPU, NO real KV cache. alpha and the per-token "
                    "energy constants are seeded inputs / MODELED references, not measured. 'lossless' "
                    "is a property of the rejection-sampling ALGORITHM, honestly labeled. MODELED, not "
                    "live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _SPEC_PAYLOAD_TYPE)

    return {
        "service": "speculative-decoding-energy-receipt",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/specdecode.js ---
        "draft_len": int(gamma),
        "trials": int(trials),
        "acceptance_rate": round(float(acceptance_rate), 6),
        "mean_accept_len": round(float(mean_accept_len), 6),
        "mean_tokens_per_step": round(float(mean_tokens_per_step), 6),
        "speedup_factor": round(float(speedup_factor), 6),
        "per_step_accept_lengths": per_step_accept_lengths,   # [int]
        "lossless": True,
        # --- SZL addition: the J/token-saved energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "acceptance_rate": "mean(accepted_len) / gamma",
            "mean_tokens_per_step": "mean(accepted_len + 1)",
            "speedup": "mean_tokens_per_step per one target verify pass (idealized)",
            "joules_per_token_saved": "(E_baseline - E_spec) / tokens",
            "E_baseline": "tokens * e_target",
            "E_spec": "steps * (e_draft * gamma + e_target)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python accept/reject simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic accept/reject sim; NO live model, NO GPU, NO real KV "
                            "cache. The measured-on-a-real-draft/verify-pair path is ROADMAP."),
        },
        "wired_into": "frontier ring — Speculative-Decoding surface + llm-router energy receipt",
        "citations": [CITATIONS["qspec"], CITATIONS["quantspec"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/specdecode" % ns

    @app.get("%s/simulate" % base)
    async def _kc_specdec(seed: int = 42, draft_len: int = 6, trials: int = 256):  # noqa: ANN202
        try:
            return JSONResponse(specdec_simulate(seed=seed, draft_len=draft_len, trials=trials))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "speculative-decoding-energy-receipt",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "acceptance_rate": None, "speedup_factor": None},
                                status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/simulate" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = specdec_simulate(seed=42, draft_len=6, trials=256)

    # (a) honest label verbatim + every field the frontend reads is present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f, t in (("draft_len", int), ("trials", int), ("acceptance_rate", float),
                 ("mean_accept_len", float), ("mean_tokens_per_step", float),
                 ("speedup_factor", float)):
        assert isinstance(r[f], t) or isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["per_step_accept_lengths"], list) and r["per_step_accept_lengths"], r
    assert all(isinstance(x, int) for x in r["per_step_accept_lengths"]), r["per_step_accept_lengths"]
    assert r["lossless"] is True, r
    # accepted lengths never exceed gamma
    assert all(0 <= x <= r["draft_len"] for x in r["per_step_accept_lengths"]), r

    # (b) sane bounds: 0 < acceptance_rate < 1 ; speedup > 1 (spec decode should help here).
    assert 0.0 < r["acceptance_rate"] < 1.0, r["acceptance_rate"]
    assert r["speedup_factor"] > 1.0, r["speedup_factor"]
    assert 0.0 < r["mean_accept_len"] <= r["draft_len"], r
    out["metrics"] = {"acceptance_rate": r["acceptance_rate"], "mean_accept_len": r["mean_accept_len"],
                      "mean_tokens_per_step": r["mean_tokens_per_step"], "speedup": r["speedup_factor"]}

    # (c) energy receipt: positive joules saved + positive J/token saved on this profile.
    er = r["energy_receipt"]
    assert er["joules_saved"] > 0, er
    assert er["joules_per_token_saved"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"joules_saved": er["joules_saved"],
                             "joules_per_token_saved": er["joules_per_token_saved"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical accepted-length profile.
    r2 = specdec_simulate(seed=42, draft_len=6, trials=256)
    assert r2["per_step_accept_lengths"] == r["per_step_accept_lengths"], "non-deterministic"
    assert r2["acceptance_rate"] == r["acceptance_rate"], "non-deterministic rate"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
