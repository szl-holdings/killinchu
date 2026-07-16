# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_nested.py — ADDITIVE NESTED-LEARNING multi-timescale-SCHEDULE simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/nested.js).

Nested Learning (NL; Behrouz, Razaviyayn, Zhong, Mirrokni 2025, arXiv:2512.24695; Google, presented
at NeurIPS 2025) recasts a model as a set of NESTED, multi-level optimization problems, each with
its OWN context flow and its OWN update frequency. Rather than one monolithic learner, NL stacks
levels that update at different TIMESCALES — fast inner levels that adapt quickly and slow outer
levels that consolidate — generalizing the classic short-term / long-term memory split into a
"Continuum Memory System" (their Hope model). Faster levels track recent context; slower levels
retain durable structure, mitigating catastrophic forgetting.

This module reproduces the NL multi-timescale SCHEDULE mechanism deterministically. It builds L
memory levels with geometrically increasing update periods (level k updates every base^k ticks);
each level carries an update rate that is high for fast levels (plastic) and low for slow levels
(stable). Over a seeded stream of ticks it records which levels fire, tracks each level's retained
"memory content" against a drifting target, and reports the effective learning rate per level, the
plasticity/stability spread, and — the SZL addition — a J/tick ENERGY RECEIPT versus a naive
schedule that updates every level on every tick.

Deterministic schedule model (seeded, no live model, no trained weights):
  * level k (k=0..L-1) has period P_k = base^k and rate eta_k = eta0 * decay^k.
  * at tick t, level k fires iff t % P_k == 0; on firing it moves its content toward a seeded
    drifting target by eta_k (a memory-consolidation step at that timescale).
  * fast levels fire often with large eta (adapt to recent drift); slow levels fire rarely with
    small eta (retain durable structure).

  updates_per_level[k]   = count of firings of level k over `ticks`
  effective_rate[k]      = eta_k                          (plasticity of level k)
  plasticity_stability   = eta_fast / eta_slow            (spread across the continuum)
  E_naive_schedule       = ticks * L * e_update           (every level every tick)
  E_nested_schedule      = sum_k updates_per_level[k] * e_update   (only firing levels)
  joules_per_tick_saved  = (E_naive - E_nested) / ticks    (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic multi-timescale SCHEDULE simulation. NOT the Hope / Nested-Learning model
    running; NO live model, NO GPU, NO trained weights, NO real continual-learning benchmark. The
    per-level content, targets, periods, and rates are SEEDED MODELED values, NOT measured.
  * The SCHEDULE STRUCTURE (nested levels with geometric update periods and per-level rates, a
    continuum from plastic-fast to stable-slow) is the paper's actual mechanism, honestly
    reimplemented; the numbers are properties of that schedule over the seeded drift, not a
    forgetting/accuracy claim on a real task.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/nested/schedule  — nested-learning multi-timescale schedule snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.nested+json"):  # type: ignore
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

_NL_PAYLOAD_TYPE = "application/vnd.szl.kc.nested+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "nested": ("Behrouz, Razaviyayn, Zhong, Mirrokni (2025) Nested Learning: The Illusion of Deep "
               "Learning Architectures (Google; NeurIPS 2025) — arXiv:2512.24695 — "
               "https://arxiv.org/abs/2512.24695"),
}

# MODELED label — a deterministic schedule simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | MULTITIMESCALE_SCHEDULE_SIM | NOT_LIVE | NO_MODEL | NO_WEIGHTS | JOULES_ARE_MODELED"

# MODELED per-unit energy references (order-of-magnitude only; NOT a live wattmeter).
_E_UPDATE = 1.0     # MODELED joules per per-level update step


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def nested_schedule(seed: int = 42, levels: int = 5, ticks: int = 512, base: int = 2,
                    eta0: float = 0.6, decay: float = 0.5, drift: float = 0.01) -> dict:
    """Nested-learning multi-timescale schedule snapshot (MODELED).

    levels — L nested memory levels (level 0 fastest/most plastic).
    ticks  — number of stream ticks simulated.
    base   — geometric factor for update periods: level k period = base^k.
    eta0   — fastest-level update rate (plasticity).
    decay  — per-level rate decay: eta_k = eta0 * decay^k.
    drift  — per-tick drift of the seeded target (the environment changing).
    seed   — RNG seed; identical inputs give identical output (deterministic).
    """
    levels = max(1, min(24, int(levels)))
    ticks = max(1, min(1_000_000, int(ticks)))
    base = max(2, min(8, int(base)))
    eta0 = max(0.01, min(0.99, float(eta0)))
    decay = max(0.05, min(0.99, float(decay)))
    drift = max(0.0, min(0.5, float(drift)))
    rng = _random.Random(int(seed) * 1_000_003 + levels * 131 + ticks * 17 + base)

    periods = [base ** k for k in range(levels)]
    rates = [eta0 * (decay ** k) for k in range(levels)]
    content = [rng.random() * 2.0 - 1.0 for _ in range(levels)]  # each level's memory content
    target = rng.random() * 2.0 - 1.0                            # seeded drifting target
    dir_ = 1.0 if rng.random() < 0.5 else -1.0

    updates_per_level = [0 for _ in range(levels)]
    for t in range(1, ticks + 1):
        # environment drifts
        target += dir_ * drift
        if target > 1.0:
            target, dir_ = 1.0, -1.0
        elif target < -1.0:
            target, dir_ = -1.0, 1.0
        # each level fires on its own period, consolidating toward the current target
        for k in range(levels):
            if t % periods[k] == 0:
                content[k] += rates[k] * (target - content[k])
                updates_per_level[k] += 1

    # final residual to target per level (fast levels track closely; slow levels lag = stable memory)
    residual_per_level = [round(abs(target - content[k]), 6) for k in range(levels)]
    effective_rate = [round(float(rates[k]), 6) for k in range(levels)]
    plasticity_stability = (rates[0] / rates[-1]) if rates[-1] else float("inf")

    # ENERGY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    e_naive = ticks * levels * _E_UPDATE                    # every level, every tick
    e_nested = sum(updates_per_level) * _E_UPDATE           # only levels that fire
    joules_saved = e_naive - e_nested
    joules_per_tick_saved = joules_saved / ticks if ticks else 0.0
    energy_reduction_pct = (joules_saved / e_naive * 100.0) if e_naive else 0.0

    energy_receipt = {
        "joules_naive_schedule": round(float(e_naive), 4),
        "joules_nested_schedule": round(float(e_nested), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_tick_saved": round(float(joules_per_tick_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_update_modeled": _E_UPDATE,
        "energy_note": ("MODELED joules — order-of-magnitude per-update estimates, NOT a live "
                        "wattmeter. Slow levels updating rarely instead of every tick is the "
                        "compute/energy win; quantified as a receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "nested-learning-multitimescale-schedule",
        "service_version": "szl-kc-nested-v0.1",
        "seed": int(seed),
        "inputs": {"levels": levels, "ticks": ticks, "base": base, "eta0": eta0,
                   "decay": decay, "drift": drift},
        "periods": periods,
        "updates_per_level": updates_per_level,
        "effective_rate": effective_rate,
        "residual_per_level": residual_per_level,
        "plasticity_stability": round(float(plasticity_stability), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (schedule advisory — never an autonomous action)",
        "citations": [CITATIONS["nested"]],
        "honesty": ("Deterministic nested multi-timescale schedule simulation over a seeded "
                    "drifting target. NOT the Hope / Nested-Learning model running; NO live model, "
                    "NO GPU, NO trained weights, NO real continual-learning benchmark. Per-level "
                    "content/periods/rates are seeded MODELED values; the SCHEDULE structure is the "
                    "paper's mechanism, honestly reimplemented. MODELED, not live; advisory to Λ "
                    "(Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _NL_PAYLOAD_TYPE)

    return {
        "service": "nested-learning-multitimescale-schedule",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/nested.js ---
        "levels": int(levels),
        "ticks": int(ticks),
        "base": int(base),
        "eta0": round(float(eta0), 4),
        "decay": round(float(decay), 4),
        "drift": round(float(drift), 4),
        "periods": periods,                     # [int]
        "updates_per_level": updates_per_level, # [int]
        "effective_rate": effective_rate,       # [float]
        "residual_per_level": residual_per_level,  # [float]
        "plasticity_stability": round(float(plasticity_stability), 6),
        # --- SZL addition: the J/tick-saved energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "period": "level k period = base^k",
            "rate": "eta_k = eta0 * decay^k (fast levels plastic, slow levels stable)",
            "update": "level k fires at tick t iff t % base^k == 0; content += eta_k*(target-content)",
            "plasticity_stability": "eta_fast / eta_slow",
            "joules_per_tick_saved": "(E_naive - E_nested) / ticks",
            "E_naive": "ticks * levels * e_update",
            "E_nested": "sum_k updates_per_level[k] * e_update",
        },
        "compute_backend": {
            "backend": "CPU pure-Python multi-timescale schedule simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic nested-schedule sim; NO live model, NO GPU, NO trained "
                            "weights. The measured-on-a-real-Hope-model path is ROADMAP."),
        },
        "wired_into": "frontier ring — Nested-Learning surface + llm-router energy receipt",
        "citations": [CITATIONS["nested"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base_path = "/api/%s/v1/nested" % ns

    @app.get("%s/schedule" % base_path)
    async def _kc_nested(seed: int = 42, levels: int = 5, ticks: int = 512, base: int = 2,
                         eta0: float = 0.6, decay: float = 0.5, drift: float = 0.01):  # noqa: ANN202
        try:
            return JSONResponse(nested_schedule(seed=seed, levels=levels, ticks=ticks, base=base,
                                                eta0=eta0, decay=decay, drift=drift))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "nested-learning-multitimescale-schedule",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "updates_per_level": None, "plasticity_stability": None},
                                status_code=200)

    # Starlette Route fallback.
    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_nested_route(request):  # pragma: no cover — fallback path
            q = request.query_params
            try:
                return _SJSON(nested_schedule(
                    seed=int(q.get("seed", 42)),
                    levels=int(q.get("levels", 5)),
                    ticks=int(q.get("ticks", 512)),
                    base=int(q.get("base", 2)),
                    eta0=float(q.get("eta0", 0.6)),
                    decay=float(q.get("decay", 0.5)),
                    drift=float(q.get("drift", 0.01))))
            except Exception as exc:
                return _SJSON({"service": "nested-learning-multitimescale-schedule",
                               "label": MODELED_LABEL,
                               "error": "compute fail-open: %s" % (type(exc).__name__)},
                              status_code=200)

        if not any(getattr(r, "path", None) == "%s/schedule" % base_path
                   for r in getattr(app.router, "routes", [])):
            app.router.routes.append(Route("%s/schedule" % base_path, _kc_nested_route,
                                           methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": ["%s/schedule" % base_path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = nested_schedule(seed=42, levels=5, ticks=512, base=2)

    # (a) honest label verbatim + every field the frontend reads present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("levels", "ticks", "base"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("eta0", "decay", "drift", "plasticity_stability"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    for f in ("periods", "updates_per_level"):
        assert isinstance(r[f], list) and len(r[f]) == r["levels"], (f, r.get(f))
        assert all(isinstance(x, int) for x in r[f]), (f, r[f])
    for f in ("effective_rate", "residual_per_level"):
        assert isinstance(r[f], list) and len(r[f]) == r["levels"], (f, r.get(f))
        assert all(isinstance(x, (int, float)) for x in r[f]), (f, r[f])

    # (b) surface-specific invariants: periods geometric & strictly increasing; faster levels
    #     update more often; rates strictly decreasing (plastic->stable continuum); fast level
    #     tracks the target at least as closely as the slowest level.
    per = r["periods"]
    assert all(per[i] < per[i + 1] for i in range(len(per) - 1)), per
    assert per[0] == 1, per
    upl = r["updates_per_level"]
    assert all(upl[i] >= upl[i + 1] for i in range(len(upl) - 1)), upl
    rate = r["effective_rate"]
    assert all(rate[i] > rate[i + 1] for i in range(len(rate) - 1)), rate
    assert r["plasticity_stability"] > 1.0, r["plasticity_stability"]
    assert r["residual_per_level"][0] <= r["residual_per_level"][-1] + 1e-9, r["residual_per_level"]
    out["metrics"] = {"periods": per, "updates_per_level": upl,
                      "plasticity_stability": r["plasticity_stability"],
                      "residual_per_level": r["residual_per_level"]}

    # (c) energy receipt: positive joules saved on this profile.
    er = r["energy_receipt"]
    assert er["joules_saved"] > 0, er
    assert er["joules_per_tick_saved"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"joules_saved": er["joules_saved"],
                             "joules_per_tick_saved": er["joules_per_tick_saved"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical schedule.
    r2 = nested_schedule(seed=42, levels=5, ticks=512, base=2)
    assert r2["updates_per_level"] == r["updates_per_level"], "non-deterministic"
    assert r2["residual_per_level"] == r["residual_per_level"], "non-deterministic residual"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    assert res["ok"] is True
    print("ALL OK")
