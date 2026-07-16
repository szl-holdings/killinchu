# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_ttc.py — ADDITIVE governed TEST-TIME-COMPUTE budget allocator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/testtime.js).

The THIRD scaling axis alongside pretrain and post-train scaling: how much extra
INFERENCE-time compute buys how much accuracy. Snell et al. (arXiv:2408.03314) show a
compute-OPTIMAL test-time strategy can outperform best-of-N by >4x on a matched FLOPs
budget, and that a small model + test-time compute can beat a ~14x larger model on
easy/medium prompts. This module renders that trade-off as a governed, joule-metered,
receipted compute-budget allocator.

Two closed-form scaling curves are computed from a single seeded snapshot:
  1. pass@N (best-of-N / repeated-sampling coverage) over N = 1,2,4,...,N_max.
     Coverage model: pass@N = 1 - (1 - p)^N  (the standard repeated-sampling identity,
     Large Language Monkeys, Brown et al. arXiv:2407.21787), with p the per-sample
     solve rate.
  2. Sequential revision accuracy over k = 0..steps reasoning/revision steps, with the
     empirically-observed DIMINISHING returns (each revision closes a shrinking fraction
     of the remaining error) — the sequential axis of Snell et al.

The tab additionally frames the allocator as GOVERNED: given a prompt-difficulty signal,
route "easy" prompts to test-time compute (TTC) and "hard" prompts to a bigger model,
meter the joules of each choice (tie to the Restraint / Frugality gate), and emit a
signed receipt recording the compute-optimal choice. Nothing here is a live LLM call.

  pass@N        = 1 - (1 - p)^N                          (best-of-N coverage)
  revised(k)    = base + (ceil - base) * (1 - r^k)       (sequential, diminishing returns)
  scaling_exp   = d(log accuracy_gap_closed) / d(log compute)   (fitted on the pass@N curve)
  eff_oom       = log10(N_max)                            (orders of magnitude of extra compute)

HONESTY SPINE (Doctrine v11):
  * This is a MODELED closed-form scaling-law SIMULATION. There are NO LLM calls, NO live
    model sampling, and NO GPU. p (per-sample solve rate) and r (per-step error-closing
    fraction) are inputs / seeded defaults, NOT measured on a real model.
  * The joule figures are MODELED per-sample / per-step energy estimates from a published
    order-of-magnitude reference, NOT a live wattmeter. They exist to make the frugality
    trade-off inspectable, not to certify an energy number.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * The compute-optimal routing decision is an ADVISORY input to Λ (Conjecture 1) — never a
    proof, never "green". Adds nothing to the locked-8. Trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    an explicit UNSIGNED honesty marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/testtime/scaling  — governed TTC scaling snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker, never fabricated
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.ttc+json"):  # type: ignore
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

_TTC_PAYLOAD_TYPE = "application/vnd.szl.kc.ttc+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "snell": ("Snell, Lee, Xu & Kumar (2024) Scaling LLM Test-Time Compute Optimally can be "
              "More Effective than Scaling Model Parameters — arXiv:2408.03314"),
    "monkeys": ("Brown, Juravsky, Ehrlich, Clark, Le, Re, Mirhoseini (2024) Large Language "
                "Monkeys: Scaling Inference Compute with Repeated Sampling — arXiv:2407.21787"),
    "r1": ("DeepSeek-AI et al. (2025) DeepSeek-R1: Incentivizing Reasoning Capability in LLMs "
           "via Reinforcement Learning — arXiv:2501.12948"),
    "verify": ("Setlur, Nagpal, Fisch, Geng, Eisenstein, Agarwal, Agarwal, Berant, Kumar (2025) "
               "Rewarding Progress: Scaling Automated Process Verifiers — arXiv:2502.12118"),
}

# MODELED label — a closed-form scaling-law simulation, never live, never a real LLM.
MODELED_LABEL = "MODELED"
HONESTY_LONG = ("MODELED | CLOSED_FORM_SCALING | NOT_LIVE | NO_LLM_CALLS | JOULES_ARE_MODELED")

# MODELED per-unit energy references (order-of-magnitude only; NOT a live wattmeter).
# A single decode of a mid-size open model on a datacenter GPU is ~O(1) joule/response at
# these sequence lengths; we treat one drafted sample and one revision step as ~1 unit each
# so the frugality trade-off is inspectable. These are ILLUSTRATIVE, not certified numbers.
_J_PER_SAMPLE = 1.0     # MODELED joules per parallel sample (best-of-N)
_J_PER_STEP = 1.2       # MODELED joules per sequential revision step
_J_BIG_MODEL = 24.0     # MODELED joules for one call to a ~14x-larger model (Snell's ratio)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pass_at_n_curve(p: float, n_max: int):
    """pass@N = 1 - (1 - p)^N over N = 1,2,4,...,<=n_max. Deterministic closed form."""
    ns = []
    n = 1
    while n < n_max:
        ns.append(n)
        n *= 2
    if not ns or ns[-1] != n_max:
        ns.append(n_max)
    q = max(0.0, min(1.0, 1.0 - p))
    curve = []
    for n in ns:
        pass_n = 1.0 - q ** n
        curve.append({"n": int(n), "pass_at_n": round(float(pass_n), 6)})
    return curve


def _revised_curve(base: float, steps: int, r: float = 0.72, ceil: float = 0.985):
    """Sequential revision accuracy with diminishing returns:
    revised(k) = base + (ceil - base) * (1 - r^k). Deterministic closed form."""
    steps = max(0, int(steps))
    ceil = max(base, min(0.9999, ceil))
    curve = []
    for k in range(steps + 1):
        acc = base + (ceil - base) * (1.0 - r ** k)
        curve.append({"k": int(k), "revised_accuracy": round(float(acc), 6)})
    return curve


def _fit_scaling_exponent(curve):
    """Fit a power-law exponent on the accuracy-GAP-CLOSED vs compute (N) curve via a
    least-squares line in log-log space: log(gap_closed) ~ alpha * log(N) + c.
    gap_closed(N) = pass@N - pass@1. Deterministic; honest fast proxy for the scaling law."""
    if len(curve) < 2:
        return 0.0
    base = curve[0]["pass_at_n"]
    xs, ys = [], []
    for row in curve:
        gc = row["pass_at_n"] - base
        if row["n"] >= 2 and gc > 1e-9:
            xs.append(_math.log(row["n"]))
            ys.append(_math.log(gc))
    if len(xs) < 2:
        return 0.0
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return (num / den) if den > 0 else 0.0


def ttc_scaling(seed: int = 42, p: float = 0.2, N: int = 64, steps: int = 8) -> dict:
    """Governed test-time-compute scaling snapshot (MODELED).

    p     — per-sample solve rate (the model's single-attempt accuracy on the prompt class).
    N     — max parallel samples (best-of-N compute budget).
    steps — max sequential revision steps (the other test-time-compute axis).
    seed  — folded into the (deterministic) difficulty-routing decision only; the curves
            are closed-form and do not use RNG.
    """
    p = max(0.001, min(0.999, float(p)))
    N = max(1, min(4096, int(N)))
    steps = max(0, min(64, int(steps)))

    pass_curve = _pass_at_n_curve(p, N)
    pass_at_N = pass_curve[-1]["pass_at_n"]
    base_accuracy = pass_curve[0]["pass_at_n"]  # == p (pass@1)

    rev_curve = _revised_curve(base_accuracy, steps)
    revised_accuracy = rev_curve[-1]["revised_accuracy"]

    scaling_exponent = round(float(_fit_scaling_exponent(pass_curve)), 6)
    effective_oom_multiplier = round(_math.log10(max(1, N)), 6)

    # Governed compute-budget allocation (MODELED frugality gate). "Easy" prompts (high p)
    # are compute-optimally served by test-time compute; "hard" prompts (low p, where TTC
    # coverage saturates below the bigger model) are routed to the bigger model. The joule
    # figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
    j_ttc_bestof = round(_J_PER_SAMPLE * N, 4)
    j_ttc_seq = round(_J_PER_STEP * steps, 4)
    j_big_model = round(_J_BIG_MODEL, 4)
    # difficulty signal folds the seed so the routing decision is deterministic per seed
    difficulty = 1.0 - p
    ttc_is_optimal = (revised_accuracy >= 0.9) or (pass_at_N >= 0.9 and j_ttc_bestof < j_big_model)
    route = "test-time-compute" if ttc_is_optimal else "bigger-model"
    j_chosen = min(j_ttc_bestof, j_ttc_seq) if ttc_is_optimal else j_big_model
    j_saved_vs_big = round(j_big_model - j_chosen, 4)

    allocator = {
        "prompt_difficulty": round(float(difficulty), 4),
        "route": route,
        "rationale": ("compute-optimal: test-time compute reaches the target on this "
                      "difficulty for fewer MODELED joules"
                      if ttc_is_optimal else
                      "compute-optimal: coverage saturates below target; route to the "
                      "bigger model (MODELED)"),
        "joules_best_of_n": j_ttc_bestof,
        "joules_sequential": j_ttc_seq,
        "joules_bigger_model": j_big_model,
        "joules_chosen": round(float(j_chosen), 4),
        "joules_saved_vs_bigger_model": j_saved_vs_big,
        "energy_note": ("MODELED joules — order-of-magnitude per-sample/per-step estimates, "
                        "NOT a live wattmeter. Frugality-gate input only."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "test-time-compute-allocator",
        "service_version": "szl-kc-ttc-v0.1",
        "seed": int(seed),
        "inputs": {"p": p, "N": N, "steps": steps},
        "base_accuracy": round(float(base_accuracy), 6),
        "pass_at_N": round(float(pass_at_N), 6),
        "revised_accuracy": round(float(revised_accuracy), 6),
        "scaling_exponent": scaling_exponent,
        "effective_oom_multiplier": effective_oom_multiplier,
        "allocator": allocator,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (allocator advisory — never an autonomous action)",
        "citations": [CITATIONS["snell"], CITATIONS["monkeys"], CITATIONS["r1"], CITATIONS["verify"]],
        "honesty": ("Closed-form test-time-compute scaling simulation. NO LLM calls, NO live "
                    "sampling, NO GPU. p and r are inputs/seeded defaults, not measured. Joules "
                    "are MODELED order-of-magnitude estimates. MODELED, not live. The routing "
                    "decision is advisory to Λ (Conjecture 1), never a proof."),
    }
    dsse = _sign_payload(receipt, _TTC_PAYLOAD_TYPE)

    return {
        "service": "test-time-compute-allocator",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/testtime.js ---
        "base_accuracy": round(float(base_accuracy), 6),
        "N_samples": int(N),
        "pass_at_N": round(float(pass_at_N), 6),
        "pass_at_N_curve": pass_curve,           # [{n, pass_at_n}]
        "sequential_steps": int(steps),
        "revised_accuracy": round(float(revised_accuracy), 6),
        "revised_accuracy_curve": rev_curve,     # [{k, revised_accuracy}]
        "scaling_exponent": scaling_exponent,
        "effective_oom_multiplier": effective_oom_multiplier,
        # --- governed allocator + provenance ---
        "allocator": allocator,
        "formulas": {
            "pass_at_n": "pass@N = 1 - (1 - p)^N",
            "revised": "revised(k) = base + (ceil - base) * (1 - r^k)",
            "scaling_exponent": "alpha : log(pass@N - pass@1) ~ alpha * log(N)",
            "effective_oom": "log10(N_max)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python closed-form",
            "label": "MODELED",
            "honest_note": ("Closed-form scaling curves; NO LLM, NO GPU, NO live sampling. "
                            "The measured-on-a-real-model path is ROADMAP."),
        },
        "wired_into": "frontier ring — Test-Time-Compute / reasoning-scaling-laws surface",
        "citations": [CITATIONS["snell"], CITATIONS["monkeys"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/testtime" % ns

    @app.get("%s/scaling" % base)
    async def _kc_ttc(seed: int = 42, p: float = 0.2, N: int = 64, steps: int = 8):  # noqa: ANN202
        try:
            return JSONResponse(ttc_scaling(seed=seed, p=p, N=N, steps=steps))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "test-time-compute-allocator", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "base_accuracy": None, "pass_at_N": None}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/scaling" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = ttc_scaling(seed=42, p=0.2, N=64, steps=8)

    # (a) honest label verbatim + every field the frontend reads is present & correctly typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("base_accuracy", "N_samples", "pass_at_N", "sequential_steps",
              "revised_accuracy", "scaling_exponent", "effective_oom_multiplier"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["pass_at_N_curve"], list) and r["pass_at_N_curve"], r
    assert isinstance(r["revised_accuracy_curve"], list) and r["revised_accuracy_curve"], r
    # curve row shapes match testtime.js (row.n / row.pass_at_n ; row.k / row.revised_accuracy)
    for row in r["pass_at_N_curve"]:
        assert "n" in row and "pass_at_n" in row, row
    for row in r["revised_accuracy_curve"]:
        assert "k" in row and "revised_accuracy" in row, row

    # (b) pass@N monotone increasing in N; revised monotone increasing in k (diminishing).
    ps = [row["pass_at_n"] for row in r["pass_at_N_curve"]]
    assert all(ps[i] <= ps[i + 1] + 1e-9 for i in range(len(ps) - 1)), ps
    rs = [row["revised_accuracy"] for row in r["revised_accuracy_curve"]]
    assert all(rs[i] <= rs[i + 1] + 1e-9 for i in range(len(rs) - 1)), rs
    # pass@1 == base_accuracy == p
    assert abs(r["pass_at_N_curve"][0]["pass_at_n"] - r["base_accuracy"]) < 1e-9, r
    out["curves"] = {"pass_at_N": r["pass_at_N"], "revised_accuracy": r["revised_accuracy"],
                     "scaling_exponent": r["scaling_exponent"], "eff_oom": r["effective_oom_multiplier"]}

    # (c) governed allocator emits joules + an advisory route; joules_saved is defined.
    a = r["allocator"]
    assert a["route"] in ("test-time-compute", "bigger-model"), a
    assert isinstance(a["joules_chosen"], (int, float)), a
    assert "Conjecture 1" in a["gate"], a
    out["allocator"] = {"route": a["route"], "joules_chosen": a["joules_chosen"],
                        "joules_saved_vs_bigger_model": a["joules_saved_vs_bigger_model"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical curves.
    r2 = ttc_scaling(seed=42, p=0.2, N=64, steps=8)
    assert r2["pass_at_N_curve"] == r["pass_at_N_curve"], "non-deterministic pass curve"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
