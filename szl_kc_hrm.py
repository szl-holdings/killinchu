# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_hrm.py — ADDITIVE HIERARCHICAL-REASONING-MODEL recurrence simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/hrm.js).

The Hierarchical Reasoning Model (HRM; Wang, Li, Sun, Chen, Liu, Wu, Lu, Song, Abbasi-Yadkori 2025,
arXiv:2506.21734) is a small (~27M-param) recurrent architecture inspired by multi-timescale
processing in the brain. It runs reasoning in a SINGLE forward pass with two interdependent
recurrent modules: a HIGH-LEVEL module (slow, abstract planning) and a LOW-LEVEL module (fast,
detailed computation). The low-level module iterates T fast steps to local equilibrium; the
high-level module then takes one slow step that resets the low-level context; this repeats for N
high-level cycles. This "hierarchical convergence" gives effective computational depth N*T without
the vanishing-gradient / early-collapse of a plain deep RNN, and reaches near-perfect accuracy on
Sudoku, maze path-finding, and ARC with only ~1000 training samples and no chain-of-thought.

This module reproduces the HRM H/L nested-recurrence MECHANISM deterministically on a seeded
constraint-satisfaction task. A low-level state vector iterates a contractive fixed-point update
(fast module) toward local equilibrium; every T steps the high-level state takes one slow update
that re-conditions the low-level target (a new subgoal). It reports high-level cycles to converge,
total low-level steps, the residual error trajectory, and — the SZL addition — a J/solve ENERGY
RECEIPT versus an explicit chain-of-thought baseline that would spend one decode step per emitted
reasoning token.

Deterministic H/L recurrence (seeded, no live model, no trained weights):
  * low-level fast update: L <- (1 - lr) * L + lr * target_H   (contractive; converges to target_H)
  * every T fast steps: high-level slow update advances target_H toward the seeded solution vector
    by a fraction `h_gain`, and the low-level residual to the *current* target is measured.
  * converged when the high-level residual to the seeded solution < tol, or N cycles exhausted.

  hl_cycles_used     = high-level cycles until convergence (<= N)
  ll_steps_total     = hl_cycles_used * T
  effective_depth    = hl_cycles_used * T                        (single forward pass, no CoT)
  final_residual     = ||target_H - solution|| at stop
  E_cot_baseline     = cot_tokens * e_decode      (explicit chain-of-thought: 1 decode/token)
  E_hrm              = ll_steps_total * e_ll_step + hl_cycles_used * e_hl_step  (recurrent, no CoT)
  joules_per_solve_saved = E_cot_baseline - E_hrm                 (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic H/L recurrence SIMULATION. NOT a trained HRM running; NO live model,
    NO GPU, NO trained weights, NO real Sudoku/ARC solving. The fixed-point update, the seeded
    solution vector, and the per-step energy constants are SEEDED MODELED values, NOT measured.
  * The RECURRENCE STRUCTURE (fast low-level loop nested under a slow high-level cycle, effective
    depth N*T in one pass) is the paper's actual mechanism, honestly reimplemented; the convergence
    numbers are properties of the seeded contraction, not an accuracy claim on a real benchmark.
  * This organ solves a SYNTHETIC seeded fixed-point, not a real puzzle; it NEVER proves anything
    and NEVER adds to the locked-8.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/hrm/solve  — hierarchical-reasoning recurrence snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
import random as _random
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker, never fabricated
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.hrm+json"):  # type: ignore
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

_HRM_PAYLOAD_TYPE = "application/vnd.szl.kc.hrm+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "hrm": ("Wang, Li, Sun, Chen, Liu, Wu, Lu, Song, Abbasi-Yadkori (2025) Hierarchical Reasoning "
            "Model — arXiv:2506.21734 — https://arxiv.org/abs/2506.21734"),
}

# MODELED label — a deterministic H/L recurrence simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | HL_RECURRENCE_SIM | NOT_LIVE | NO_MODEL | NO_WEIGHTS | JOULES_ARE_MODELED"

# MODELED per-unit energy references (order-of-magnitude only; NOT a live wattmeter).
_E_DECODE = 1.0      # MODELED joules per chain-of-thought decode step (the expensive baseline unit)
_E_LL_STEP = 0.04    # MODELED joules per low-level fast recurrent step (cheap)
_E_HL_STEP = 0.12    # MODELED joules per high-level slow cycle update


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(v):
    return _math.sqrt(sum(x * x for x in v))


def hrm_solve(seed: int = 42, dim: int = 12, n_cycles: int = 16, t_low: int = 8,
              lr: float = 0.55, h_gain: float = 0.32, tol: float = 0.02) -> dict:
    """Hierarchical-reasoning recurrence snapshot (MODELED).

    dim       — dimension of the seeded constraint-satisfaction state.
    n_cycles  — N, maximum high-level (slow) cycles.
    t_low     — T, low-level (fast) steps per high-level cycle.
    lr        — low-level contraction rate toward the current high-level target.
    h_gain    — high-level step fraction toward the seeded solution vector.
    tol       — convergence tolerance on the high-level residual.
    seed      — RNG seed; identical inputs give identical output (deterministic).
    """
    dim = max(2, min(256, int(dim)))
    n_cycles = max(1, min(4096, int(n_cycles)))
    t_low = max(1, min(1024, int(t_low)))
    lr = max(0.01, min(0.99, float(lr)))
    h_gain = max(0.01, min(0.99, float(h_gain)))
    tol = max(1e-6, min(1.0, float(tol)))
    rng = _random.Random(int(seed) * 1_000_003 + dim * 131 + n_cycles * 17 + t_low)

    # seeded task: solution vector on the unit sphere; start far from it.
    solution = [rng.random() * 2.0 - 1.0 for _ in range(dim)]
    sn = _norm(solution) or 1.0
    solution = [x / sn for x in solution]
    target_h = [rng.random() * 2.0 - 1.0 for _ in range(dim)]   # high-level state (subgoal target)
    low = [rng.random() * 2.0 - 1.0 for _ in range(dim)]        # low-level fast state

    residual_trace = []
    hl_cycles_used = 0
    ll_steps_total = 0
    ll_final_residual = None
    for _c in range(n_cycles):
        hl_cycles_used += 1
        # low-level fast loop: contract toward the current high-level target.
        for _t in range(t_low):
            low = [(1.0 - lr) * low[i] + lr * target_h[i] for i in range(dim)]
            ll_steps_total += 1
        ll_final_residual = _norm([low[i] - target_h[i] for i in range(dim)])
        # high-level slow step: advance the target toward the seeded solution.
        target_h = [target_h[i] + h_gain * (solution[i] - target_h[i]) for i in range(dim)]
        hl_residual = _norm([target_h[i] - solution[i] for i in range(dim)])
        residual_trace.append(round(float(hl_residual), 6))
        if hl_residual < tol:
            break

    final_residual = residual_trace[-1] if residual_trace else 1.0
    converged = final_residual < tol
    effective_depth = ll_steps_total   # single forward pass, no CoT tokens emitted

    # ENERGY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    # CoT baseline: an explicit reasoning trace would emit ~effective_depth decode steps.
    cot_tokens = effective_depth
    e_cot = cot_tokens * _E_DECODE
    e_hrm = ll_steps_total * _E_LL_STEP + hl_cycles_used * _E_HL_STEP
    joules_saved = e_cot - e_hrm
    joules_per_solve_saved = joules_saved
    energy_reduction_pct = (joules_saved / e_cot * 100.0) if e_cot else 0.0

    energy_receipt = {
        "joules_cot_baseline": round(float(e_cot), 4),
        "joules_hrm": round(float(e_hrm), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_solve_saved": round(float(joules_per_solve_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_decode_step_modeled": _E_DECODE,
        "e_ll_step_modeled": _E_LL_STEP,
        "e_hl_step_modeled": _E_HL_STEP,
        "energy_note": ("MODELED joules — order-of-magnitude per-step estimates, NOT a live "
                        "wattmeter. HRM reaches effective depth N*T in one forward pass without "
                        "emitting chain-of-thought tokens; this quantifies that as an energy "
                        "receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "hierarchical-reasoning-recurrence",
        "service_version": "szl-kc-hrm-v0.1",
        "seed": int(seed),
        "inputs": {"dim": dim, "n_cycles": n_cycles, "t_low": t_low, "lr": lr,
                   "h_gain": h_gain, "tol": tol},
        "hl_cycles_used": int(hl_cycles_used),
        "ll_steps_total": int(ll_steps_total),
        "effective_depth": int(effective_depth),
        "final_residual": round(float(final_residual), 6),
        "converged": bool(converged),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (recurrence advisory — never an autonomous action)",
        "citations": [CITATIONS["hrm"]],
        "honesty": ("Deterministic high/low nested-recurrence simulation on a seeded fixed-point "
                    "task. NOT a trained HRM running; NO live model, NO GPU, NO trained weights, "
                    "NO real Sudoku/ARC solving. The recurrence STRUCTURE is the paper's mechanism, "
                    "honestly reimplemented; convergence is a property of the seeded contraction. "
                    "This organ solves a synthetic fixed-point only; it NEVER proves anything and "
                    "NEVER adds to the locked-8. MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _HRM_PAYLOAD_TYPE)

    return {
        "service": "hierarchical-reasoning-recurrence",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/hrm.js ---
        "dim": int(dim),
        "n_cycles": int(n_cycles),
        "t_low": int(t_low),
        "lr": round(float(lr), 4),
        "h_gain": round(float(h_gain), 4),
        "tol": round(float(tol), 6),
        "hl_cycles_used": int(hl_cycles_used),
        "ll_steps_total": int(ll_steps_total),
        "effective_depth": int(effective_depth),
        "final_residual": round(float(final_residual), 6),
        "ll_final_residual": round(float(ll_final_residual or 0.0), 6),
        "converged": bool(converged),
        "residual_trace": residual_trace,   # [float], high-level residual per cycle
        "proves_nothing": True,
        "locked_proven": 8,
        # --- SZL addition: the J/solve-saved energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "ll_update": "L <- (1 - lr) * L + lr * target_H  (fast, contractive)",
            "hl_update": "target_H <- target_H + h_gain * (solution - target_H)  (slow)",
            "effective_depth": "hl_cycles_used * t_low (single forward pass, no CoT)",
            "converged": "high-level residual to solution < tol",
            "joules_per_solve_saved": "E_cot_baseline - E_hrm",
            "E_cot_baseline": "effective_depth * e_decode",
            "E_hrm": "ll_steps_total * e_ll_step + hl_cycles_used * e_hl_step",
        },
        "compute_backend": {
            "backend": "CPU pure-Python H/L nested-recurrence simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic fixed-point recurrence sim; NO live model, NO GPU, NO "
                            "trained weights, NO real puzzle. The measured-on-a-real-HRM path is "
                            "ROADMAP; this organ never proves and never adds to the locked-8."),
        },
        "wired_into": "frontier ring — Hierarchical-Reasoning surface + llm-router energy receipt",
        "citations": [CITATIONS["hrm"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/hrm" % ns

    @app.get("%s/solve" % base)
    async def _kc_hrm(seed: int = 42, dim: int = 12, n_cycles: int = 16, t_low: int = 8,
                      lr: float = 0.55, h_gain: float = 0.32, tol: float = 0.02):  # noqa: ANN202
        try:
            return JSONResponse(hrm_solve(seed=seed, dim=dim, n_cycles=n_cycles, t_low=t_low,
                                          lr=lr, h_gain=h_gain, tol=tol))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "hierarchical-reasoning-recurrence",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "hl_cycles_used": None, "converged": None},
                                status_code=200)

    # Starlette Route fallback.
    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_hrm_route(request):  # pragma: no cover — fallback path
            q = request.query_params
            try:
                return _SJSON(hrm_solve(
                    seed=int(q.get("seed", 42)),
                    dim=int(q.get("dim", 12)),
                    n_cycles=int(q.get("n_cycles", 16)),
                    t_low=int(q.get("t_low", 8)),
                    lr=float(q.get("lr", 0.55)),
                    h_gain=float(q.get("h_gain", 0.32)),
                    tol=float(q.get("tol", 0.02))))
            except Exception as exc:
                return _SJSON({"service": "hierarchical-reasoning-recurrence",
                               "label": MODELED_LABEL,
                               "error": "compute fail-open: %s" % (str(exc)[:160])},
                              status_code=200)

        if not any(getattr(r, "path", None) == "%s/solve" % base
                   for r in getattr(app.router, "routes", [])):
            app.router.routes.append(Route("%s/solve" % base, _kc_hrm_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": ["%s/solve" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = hrm_solve(seed=42, dim=12, n_cycles=16, t_low=8)

    # (a) honest label verbatim + every field the frontend reads present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("dim", "n_cycles", "t_low", "hl_cycles_used", "ll_steps_total",
              "effective_depth", "locked_proven"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("lr", "h_gain", "tol", "final_residual", "ll_final_residual"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["residual_trace"], list) and r["residual_trace"], r
    assert all(isinstance(x, (int, float)) for x in r["residual_trace"]), r["residual_trace"]
    assert isinstance(r["converged"], bool), r

    # (b) surface-specific invariants: nested depth = cycles*T; hierarchical convergence (the
    #     residual trace is monotonically non-increasing — the point of the H/L structure);
    #     never proves; locked-8 untouched.
    assert r["hl_cycles_used"] <= r["n_cycles"], r
    assert r["ll_steps_total"] == r["hl_cycles_used"] * r["t_low"], r
    assert r["effective_depth"] == r["ll_steps_total"], r
    tr = r["residual_trace"]
    assert all(tr[i] >= tr[i + 1] - 1e-9 for i in range(len(tr) - 1)), tr
    assert r["converged"] is True, r  # this profile is designed to converge
    assert r["final_residual"] < r["tol"], (r["final_residual"], r["tol"])
    assert r["proves_nothing"] is True and r["locked_proven"] == 8, r
    out["metrics"] = {"hl_cycles_used": r["hl_cycles_used"], "ll_steps_total": r["ll_steps_total"],
                      "effective_depth": r["effective_depth"], "final_residual": r["final_residual"],
                      "converged": r["converged"]}

    # (c) energy receipt: positive joules saved on this profile.
    er = r["energy_receipt"]
    assert er["joules_saved"] > 0, er
    assert er["joules_per_solve_saved"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"joules_saved": er["joules_saved"],
                             "joules_per_solve_saved": er["joules_per_solve_saved"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical trajectory.
    r2 = hrm_solve(seed=42, dim=12, n_cycles=16, t_low=8)
    assert r2["residual_trace"] == r["residual_trace"], "non-deterministic"
    assert r2["final_residual"] == r["final_residual"], "non-deterministic residual"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    assert res["ok"] is True
    print("ALL OK")
