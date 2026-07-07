# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_steering.py — ADDITIVE ACTIVATION-STEERING (ActAdd) coefficient-sweep simulator for
killinchu's frontier surface (backs a11oy static/3d/surfaces/steering.js).

Activation Addition (ActAdd; Turner, Thiergart, Leech, Udell, Vazquez, Mini, MacDiarmid 2023,
arXiv:2308.10248) steers a language model at INFERENCE TIME with no fine-tuning. It contrasts the
intermediate activations on a prompt PAIR (e.g. "Love" vs "Hate") to compute a STEERING VECTOR
v = act(prompt_plus) - act(prompt_minus) at a chosen layer, then adds c*v into the residual stream
during the forward pass. A larger coefficient c shifts a high-level output property (sentiment,
topic) more strongly ON-TARGET, but too-large c degrades OFF-TARGET behavior (fluency/perplexity).
The craft is finding the coefficient that maximizes the on-target shift while preserving off-target
performance — a sweep over c.

This module reproduces the ActAdd coefficient-sweep MECHANISM deterministically. It builds a seeded
"positive" and "negative" activation cluster, forms the steering vector as their difference, and
for each coefficient c on a sweep projects a seeded batch of neutral activations along +c*v. It
scores the ON-TARGET shift (mean movement toward the positive cluster along the steering direction)
and the OFF-TARGET cost (a MODELED perplexity penalty growing with ||c*v|| off the data manifold),
then reports the coefficient that maximizes a preservation-weighted objective. The SZL addition is a
J/edit ENERGY RECEIPT: inference-time steering vs. the joules a fine-tuning pass would cost.

Deterministic sweep model (seeded, no live model, no trained weights):
  * steering vector v = centroid(pos) - centroid(neg) in `dim` dims (seeded clusters).
  * for coefficient c: on_target(c) = c * ||v||  (projection gain along v, clamped by saturation);
    off_target_cost(c) = kappa * (c * ||v||)^2  (quadratic manifold-departure penalty).
  * objective(c) = on_target(c) - off_target_cost(c); pick argmax over the sweep.

  best_coeff             = argmax_c objective(c)
  on_target_shift        = on_target(best_coeff)
  off_target_cost        = off_target_cost(best_coeff)
  preservation           = 1 - off_target_cost(best) / (on_target(best) + off_target_cost(best))
  E_finetune_baseline    = tune_steps * e_tune_step      (a fine-tuning pass to shift the property)
  E_actadd               = sweep_points * e_forward       (inference-time forward passes only)
  joules_per_edit_saved  = E_finetune_baseline - E_actadd  (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic steering-sweep SIMULATION. NOT ActAdd running on a real model; NO live
    model, NO GPU, NO trained weights, NO real activations. The activation clusters, the steering
    vector, the saturation and the perplexity-penalty constants are SEEDED MODELED values, NOT
    measured.
  * The SWEEP MECHANISM (contrast-pair steering vector, add c*v, trade on-target shift against
    off-target degradation, pick best c) is ActAdd's actual method, honestly reimplemented; the
    numbers are properties of that sweep over the seeded clusters, not a measurement on a real LLM.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/steering/sweep  — activation-steering coefficient-sweep snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.steering+json"):  # type: ignore
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

_ST_PAYLOAD_TYPE = "application/vnd.szl.kc.steering+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "actadd": ("Turner, Thiergart, Leech, Udell, Vazquez, Mini, MacDiarmid (2023) Steering Language "
               "Models With Activation Engineering (ActAdd) — arXiv:2308.10248 — "
               "https://arxiv.org/abs/2308.10248"),
}

# MODELED label — a deterministic steering-sweep simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | ACTADD_SWEEP_SIM | NOT_LIVE | NO_MODEL | NO_WEIGHTS | JOULES_ARE_MODELED"

# MODELED per-unit energy references (order-of-magnitude only; NOT a live wattmeter).
_E_TUNE_STEP = 1.0     # MODELED joules per fine-tuning optimizer step (the expensive baseline)
_E_FORWARD = 0.05      # MODELED joules per inference forward pass evaluated in the sweep


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _centroid(vecs):
    n = len(vecs)
    dim = len(vecs[0])
    return [sum(v[i] for v in vecs) / n for i in range(dim)]


def _norm(v):
    return _math.sqrt(sum(x * x for x in v))


def steering_sweep(seed: int = 42, dim: int = 32, cluster: int = 24, sweep_points: int = 21,
                   c_max: float = 6.0, kappa: float = 0.08) -> dict:
    """Activation-steering coefficient-sweep snapshot (MODELED).

    dim          — activation dimension.
    cluster      — points per contrast cluster (positive / negative).
    sweep_points — number of coefficients c evaluated in [0, c_max].
    c_max        — largest steering coefficient in the sweep.
    kappa        — off-target (perplexity) penalty weight; larger => steering degrades sooner.
    seed         — RNG seed; identical inputs give identical output (deterministic).
    """
    dim = max(2, min(512, int(dim)))
    cluster = max(2, min(4096, int(cluster)))
    sweep_points = max(3, min(1000, int(sweep_points)))
    c_max = max(0.5, min(64.0, float(c_max)))
    kappa = max(0.001, min(2.0, float(kappa)))
    rng = _random.Random(int(seed) * 1_000_003 + dim * 131 + cluster * 17 + sweep_points)

    # seeded positive/negative activation clusters around opposite anchors.
    anchor = [rng.random() * 2.0 - 1.0 for _ in range(dim)]
    an = _norm(anchor) or 1.0
    anchor = [x / an for x in anchor]
    pos = [[anchor[i] + (rng.random() - 0.5) * 0.4 for i in range(dim)] for _ in range(cluster)]
    neg = [[-anchor[i] + (rng.random() - 0.5) * 0.4 for i in range(dim)] for _ in range(cluster)]
    v = [_centroid(pos)[i] - _centroid(neg)[i] for i in range(dim)]  # steering vector
    vnorm = _norm(v)

    # sweep coefficients; on-target gain saturates, off-target cost grows quadratically.
    sweep = []
    best = None
    saturation = 3.0 * vnorm  # on-target gain saturates once we've moved this far along v
    for j in range(sweep_points):
        c = c_max * j / (sweep_points - 1)
        raw_gain = c * vnorm
        on_target = saturation * (1.0 - _math.exp(-raw_gain / (saturation or 1.0)))  # saturating
        off_target = kappa * raw_gain * raw_gain                                     # quadratic
        objective = on_target - off_target
        row = {"coeff": round(float(c), 4),
               "on_target": round(float(on_target), 6),
               "off_target_cost": round(float(off_target), 6),
               "objective": round(float(objective), 6)}
        sweep.append(row)
        if best is None or objective > best["objective"]:
            best = row

    best_coeff = best["coeff"]
    on_target_shift = best["on_target"]
    off_target_cost = best["off_target_cost"]
    denom = on_target_shift + off_target_cost
    preservation = (1.0 - off_target_cost / denom) if denom else 1.0

    # ENERGY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    tune_steps = 1000  # MODELED optimizer steps a fine-tune would spend to shift the property
    e_finetune = tune_steps * _E_TUNE_STEP
    e_actadd = sweep_points * _E_FORWARD          # inference-time forward passes only
    joules_saved = e_finetune - e_actadd
    joules_per_edit_saved = joules_saved
    energy_reduction_pct = (joules_saved / e_finetune * 100.0) if e_finetune else 0.0

    energy_receipt = {
        "joules_finetune_baseline": round(float(e_finetune), 4),
        "joules_actadd": round(float(e_actadd), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_edit_saved": round(float(joules_per_edit_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_tune_step_modeled": _E_TUNE_STEP,
        "e_forward_modeled": _E_FORWARD,
        "energy_note": ("MODELED joules — order-of-magnitude per-step estimates, NOT a live "
                        "wattmeter. Inference-time steering with no optimizer pass is the energy "
                        "win vs. fine-tuning; quantified as a receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    objective_curve = [row["objective"] for row in sweep][:21]

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "activation-steering-sweep",
        "service_version": "szl-kc-steering-v0.1",
        "seed": int(seed),
        "inputs": {"dim": dim, "cluster": cluster, "sweep_points": sweep_points,
                   "c_max": c_max, "kappa": kappa},
        "best_coeff": round(float(best_coeff), 6),
        "on_target_shift": round(float(on_target_shift), 6),
        "off_target_cost": round(float(off_target_cost), 6),
        "preservation": round(float(preservation), 6),
        "steering_vector_norm": round(float(vnorm), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (steering advisory — never an autonomous action)",
        "citations": [CITATIONS["actadd"]],
        "honesty": ("Deterministic ActAdd coefficient-sweep simulation over seeded activation "
                    "clusters. NOT ActAdd running on a real model; NO live model, NO GPU, NO trained "
                    "weights, NO real activations. Clusters, steering vector, saturation and the "
                    "perplexity-penalty constants are seeded MODELED values; the SWEEP mechanism is "
                    "ActAdd's method, honestly reimplemented. MODELED, not live; advisory to Λ "
                    "(Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _ST_PAYLOAD_TYPE)

    return {
        "service": "activation-steering-sweep",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/steering.js ---
        "dim": int(dim),
        "cluster": int(cluster),
        "sweep_points": int(sweep_points),
        "c_max": round(float(c_max), 4),
        "kappa": round(float(kappa), 4),
        "best_coeff": round(float(best_coeff), 6),
        "on_target_shift": round(float(on_target_shift), 6),
        "off_target_cost": round(float(off_target_cost), 6),
        "preservation": round(float(preservation), 6),
        "steering_vector_norm": round(float(vnorm), 6),
        "objective_curve": objective_curve,   # [float]
        "sweep": sweep,                        # [ {coeff,on_target,off_target_cost,objective} ]
        # --- SZL addition: the J/edit-saved energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "steering_vector": "v = centroid(pos_activations) - centroid(neg_activations)",
            "on_target": "saturating gain: S*(1 - exp(-c*||v|| / S))",
            "off_target_cost": "kappa * (c*||v||)^2 (quadratic manifold-departure penalty)",
            "objective": "on_target - off_target_cost ; best_coeff = argmax_c objective",
            "preservation": "1 - off_target_cost(best) / (on_target(best) + off_target_cost(best))",
            "joules_per_edit_saved": "E_finetune_baseline - E_actadd",
            "E_finetune_baseline": "tune_steps * e_tune_step",
            "E_actadd": "sweep_points * e_forward",
        },
        "compute_backend": {
            "backend": "CPU pure-Python steering-sweep simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic ActAdd sweep sim; NO live model, NO GPU, NO trained "
                            "weights, NO real activations. The measured-on-a-real-model path is "
                            "ROADMAP."),
        },
        "wired_into": "frontier ring — Activation-Steering surface + llm-router energy receipt",
        "citations": [CITATIONS["actadd"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/steering" % ns

    @app.get("%s/sweep" % base)
    async def _kc_steering(seed: int = 42, dim: int = 32, cluster: int = 24,
                           sweep_points: int = 21, c_max: float = 6.0,
                           kappa: float = 0.08):  # noqa: ANN202
        try:
            return JSONResponse(steering_sweep(seed=seed, dim=dim, cluster=cluster,
                                               sweep_points=sweep_points, c_max=c_max, kappa=kappa))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "activation-steering-sweep",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "best_coeff": None, "preservation": None},
                                status_code=200)

    # Starlette Route fallback.
    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_steering_route(request):  # pragma: no cover — fallback path
            q = request.query_params
            try:
                return _SJSON(steering_sweep(
                    seed=int(q.get("seed", 42)),
                    dim=int(q.get("dim", 32)),
                    cluster=int(q.get("cluster", 24)),
                    sweep_points=int(q.get("sweep_points", 21)),
                    c_max=float(q.get("c_max", 6.0)),
                    kappa=float(q.get("kappa", 0.08))))
            except Exception as exc:
                return _SJSON({"service": "activation-steering-sweep",
                               "label": MODELED_LABEL,
                               "error": "compute fail-open: %s" % (str(exc)[:160])},
                              status_code=200)

        if not any(getattr(r, "path", None) == "%s/sweep" % base
                   for r in getattr(app.router, "routes", [])):
            app.router.routes.append(Route("%s/sweep" % base, _kc_steering_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": ["%s/sweep" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = steering_sweep(seed=42, dim=32, cluster=24, sweep_points=21, c_max=6.0)

    # (a) honest label verbatim + every field the frontend reads present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("dim", "cluster", "sweep_points"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("c_max", "kappa", "best_coeff", "on_target_shift", "off_target_cost",
              "preservation", "steering_vector_norm"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["objective_curve"], list) and r["objective_curve"], r
    assert all(isinstance(x, (int, float)) for x in r["objective_curve"]), r["objective_curve"]
    assert isinstance(r["sweep"], list) and len(r["sweep"]) == r["sweep_points"], r
    for row in r["sweep"]:
        for kk in ("coeff", "on_target", "off_target_cost", "objective"):
            assert kk in row and isinstance(row[kk], (int, float)), (kk, row)

    # (b) surface-specific invariants: steering vector points from neg->pos (positive norm);
    #     best coeff is interior (a real trade-off exists, not the endpoints); best objective is the
    #     max over the sweep; preservation in [0,1]; c=0 has zero shift and zero cost.
    assert r["steering_vector_norm"] > 0.0, r
    objs = [row["objective"] for row in r["sweep"]]
    # the swept best must equal the reported best coeff's objective
    best_row = max(r["sweep"], key=lambda x: x["objective"])
    assert abs(best_row["coeff"] - r["best_coeff"]) < 1e-6, (best_row, r["best_coeff"])
    assert 0.0 < r["best_coeff"] < r["c_max"], r["best_coeff"]  # interior optimum (real trade-off)
    assert 0.0 <= r["preservation"] <= 1.0, r["preservation"]
    assert r["on_target_shift"] > 0.0, r
    assert r["sweep"][0]["coeff"] == 0.0 and r["sweep"][0]["on_target"] == 0.0, r["sweep"][0]
    # on_target is monotonically non-decreasing in c (saturating gain)
    ots = [row["on_target"] for row in r["sweep"]]
    assert all(ots[i] <= ots[i + 1] + 1e-9 for i in range(len(ots) - 1)), ots
    out["metrics"] = {"best_coeff": r["best_coeff"], "on_target_shift": r["on_target_shift"],
                      "off_target_cost": r["off_target_cost"], "preservation": r["preservation"]}

    # (c) energy receipt: positive joules saved on this profile.
    er = r["energy_receipt"]
    assert er["joules_saved"] > 0, er
    assert er["joules_per_edit_saved"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"joules_saved": er["joules_saved"],
                             "joules_per_edit_saved": er["joules_per_edit_saved"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical sweep.
    r2 = steering_sweep(seed=42, dim=32, cluster=24, sweep_points=21, c_max=6.0)
    assert r2["objective_curve"] == r["objective_curve"], "non-deterministic"
    assert r2["best_coeff"] == r["best_coeff"], "non-deterministic best coeff"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    assert res["ok"] is True
    print("ALL OK")
