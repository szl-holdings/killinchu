# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_worldmodel.py — ADDITIVE governed WORLD-MODEL rollout for killinchu's frontier surface
(backs a11oy static/3d/surfaces/worldmodel.js).

A world model learns the dynamics of an environment in a LATENT space, then predicts the next
latent state z_{t+1} from the current latent and an action — enabling planning/rollouts without
touching the real world. DeepMind's Genie 3 generates real-time interactive worlds as a stepping
stone toward agent training; DreamerV3 learns behaviors purely inside a learned world model and
solves diverse tasks with fixed hyperparameters. This module frames killinchu's platform-dynamics
twin as a GOVERNED world-model rollout: every simulated interdiction/counterfactual is a rollout
that emits a signed receipt (Decision-Simulation against historical state — SZL innovation).

Deterministic latent rollout (seeded, no learned net):
  * A stable linear-plus-nonlinear latent dynamics operator f advances the OBSERVED (ground-truth)
    latent trajectory over `horizon` steps in `latent_dim` dimensions.
  * The PREDICTED trajectory is the model's one-step-ahead estimate zhat_{t+1} = f(z_t) + small
    seeded prediction noise — a JEPA-style predictor whose error is the "physical surprise".
  * physical_surprise[t]      = ||zhat_t - z_t||_2   (per-step prediction error / surprise)
  * prediction_error          = mean_t physical_surprise[t]      (lower is better)
  * free_energy_consistency   = MODELED on-manifold consistency in (0,1], higher = tighter fit,
                                a free-energy-style measure (surprise minimization).
  * action_anticipation_acc   = MODELED fraction of steps whose predicted action-direction sign
                                matches the observed transition (in (0,1)).

HONESTY SPINE (Doctrine v11):
  * MODELED closed-form latent-dynamics SIMULATION. This is NOT Genie 3 / DreamerV3 running; there
    is NO learned world model, NO video generation, NO GPU, NO live environment. The dynamics
    operator and the prediction noise are SEEDED — a simulation of the METHOD, not a trained model.
  * The latent trajectory is honestly synthetic. The receipt frames each rollout as a
    Decision-Simulation against (synthetic) historical state; effectors stay SIMULATED,
    human-on-loop — a rollout NEVER triggers a real action.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every rollout is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/worldmodel/predict  — governed world-model latent rollout (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.worldmodel+json"):  # type: ignore
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

_WM_PAYLOAD_TYPE = "application/vnd.szl.kc.worldmodel+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "genie3": ("Google DeepMind (2025) Genie 3: a general-purpose real-time interactive world "
               "model — https://deepmind.google/models/genie/"),
    "dreamerv3": ("Hafner, Pasukonis, Ba, Lillicrap (2023) Mastering Diverse Domains through World "
                  "Models (DreamerV3) — arXiv:2301.04104"),
    "genie1": ("Bruce, Dennis, Edwards, Parker-Holder et al. (2024) Genie: Generative Interactive "
               "Environments — arXiv:2402.15391"),
    "jepa": ("LeCun (2022) A Path Towards Autonomous Machine Intelligence (JEPA world-model "
             "framing) — OpenReview / https://openreview.net/forum?id=BZ5a1r-kVsf"),
}

# MODELED label — a closed-form latent-dynamics simulation, never a trained world model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | LATENT_ROLLOUT_SIM | NOT_LIVE | NO_LEARNED_MODEL | SYNTHETIC_LATENTS"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _l2(a, b) -> float:
    return _math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _dynamics_step(z, rng_dyn):
    """Stable latent dynamics f(z): a gentle rotation-plus-contraction with a mild
    nonlinearity. Deterministic given the seeded per-dim coefficients."""
    d = len(z)
    out = []
    for i in range(d):
        j = (i + 1) % d
        # contraction 0.94 keeps the trajectory bounded (stable dynamics); small coupling + tanh
        val = 0.94 * z[i] + 0.06 * _math.tanh(z[j]) + 0.02 * rng_dyn[i]
        out.append(val)
    return out


def worldmodel_predict(seed: int = 42, horizon: int = 12, latent_dim: int = 16) -> dict:
    """Governed world-model latent rollout snapshot (MODELED).

    horizon    — rollout length (steps).
    latent_dim — dimensionality of the latent state (frontend projects first 3 dims to XYZ).
    seed       — RNG seed; identical inputs give identical output (deterministic).
    """
    horizon = max(2, min(200, int(horizon)))
    latent_dim = max(3, min(256, int(latent_dim)))
    rng = _random.Random(int(seed) * 2_654_435_761 % (2 ** 32) + horizon * 97 + latent_dim)

    # fixed per-dim dynamics coupling (seeded, deterministic) so f is stable & reproducible
    rng_dyn = [rng.uniform(-1.0, 1.0) for _ in range(latent_dim)]

    # initial ground-truth latent
    z = [rng.uniform(-0.6, 0.6) for _ in range(latent_dim)]

    observed = [list(z)]
    for _ in range(horizon):
        z = _dynamics_step(z, rng_dyn)
        observed.append(list(z))

    # PREDICTED one-step-ahead trajectory: zhat_{t+1} = f(z_t) + seeded prediction noise.
    # The noise magnitude grows very slightly with the horizon (compounding uncertainty),
    # so physical surprise rises later in the rollout — the honest world-model behavior.
    predicted = []
    surprise = []
    for t in range(len(observed) - 1):
        base = _dynamics_step(observed[t], rng_dyn)  # the model's clean prediction
        noise_scale = 0.03 + 0.010 * t
        zhat = [base[i] + rng.gauss(0.0, noise_scale) for i in range(latent_dim)]
        predicted.append(zhat)
        surprise.append(round(float(_l2(zhat, observed[t + 1])), 6))

    prediction_error = round(sum(surprise) / len(surprise), 6) if surprise else 0.0

    # free-energy-style consistency in (0,1]: higher when mean surprise is small (on-manifold).
    free_energy_consistency = round(1.0 / (1.0 + prediction_error), 6)

    # action-anticipation accuracy (MODELED): fraction of steps where the predicted transition
    # direction (sign of dim-0 delta) matches the observed transition direction.
    hits = 0
    total = 0
    for t in range(len(predicted)):
        pred_delta = predicted[t][0] - observed[t][0]
        obs_delta = observed[t + 1][0] - observed[t][0]
        total += 1
        if (pred_delta >= 0) == (obs_delta >= 0):
            hits += 1
    action_anticipation_acc = round(hits / total, 6) if total else 0.0

    # round the emitted latents so the JSON is compact (frontend uses first 3 dims for XYZ)
    def _round_traj(traj):
        return [[round(float(v), 5) for v in vec] for vec in traj]

    observed_latents = _round_traj(observed)
    predicted_latents = _round_traj(predicted)

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "governed-world-model-rollout",
        "service_version": "szl-kc-worldmodel-v0.1",
        "seed": int(seed),
        "inputs": {"horizon": horizon, "latent_dim": latent_dim},
        "prediction_error": prediction_error,
        "free_energy_consistency": free_energy_consistency,
        "action_anticipation_acc": action_anticipation_acc,
        "rollout_kind": "Decision-Simulation against (synthetic) historical latent state",
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": ("SIMULATED · human-on-loop (rollout advisory — a simulated "
                             "interdiction NEVER triggers a real action)"),
        "citations": [CITATIONS["genie3"], CITATIONS["dreamerv3"], CITATIONS["genie1"],
                      CITATIONS["jepa"]],
        "honesty": ("Closed-form latent-dynamics world-model rollout. NOT Genie 3 / DreamerV3 "
                    "running; NO learned model, NO video generation, NO GPU, NO live environment. "
                    "Dynamics operator and prediction noise are seeded; latents are synthetic. "
                    "MODELED, not live; a governed rollout advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _WM_PAYLOAD_TYPE)

    return {
        "service": "governed-world-model-rollout",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/worldmodel.js ---
        "prediction_error": prediction_error,
        "physical_surprise": surprise,                 # [float] per-step L2
        "action_anticipation_acc": action_anticipation_acc,
        "free_energy_consistency": free_energy_consistency,
        "observed_latents": observed_latents,          # [[float...]] (first 3 dims -> XYZ)
        "predicted_latents": predicted_latents,        # [[float...]]
        "rollout_horizon": int(horizon),
        "latent_dim": int(latent_dim),
        # --- governed-rollout provenance ---
        "formulas": {
            "surprise": "physical_surprise[t] = ||zhat_t - z_t||_2",
            "prediction_error": "mean_t physical_surprise[t]",
            "free_energy_consistency": "1 / (1 + prediction_error)",
            "dynamics": "z_{t+1} = 0.94*z + 0.06*tanh(z_shift) + coupling  (stable)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python latent-dynamics rollout",
            "label": "MODELED",
            "honest_note": ("Closed-form stable latent dynamics; NO learned world model, NO "
                            "video, NO GPU. The trained-world-model (Genie/Dreamer) path is ROADMAP."),
        },
        "wired_into": "frontier ring — World-Model surface (governed counterfactual rollout)",
        "citations": [CITATIONS["genie3"], CITATIONS["dreamerv3"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/worldmodel" % ns

    @app.get("%s/predict" % base)
    async def _kc_worldmodel(seed: int = 42, horizon: int = 12, latent_dim: int = 16):  # noqa: ANN202
        try:
            return JSONResponse(worldmodel_predict(seed=seed, horizon=horizon, latent_dim=latent_dim))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "governed-world-model-rollout", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "prediction_error": None, "free_energy_consistency": None},
                                status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/predict" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = worldmodel_predict(seed=42, horizon=12, latent_dim=16)

    # (a) honest label verbatim + every field the frontend reads is present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("prediction_error", "action_anticipation_acc", "free_energy_consistency"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["rollout_horizon"], int) and isinstance(r["latent_dim"], int), r
    assert isinstance(r["physical_surprise"], list) and r["physical_surprise"], r
    assert isinstance(r["observed_latents"], list) and r["observed_latents"], r
    assert isinstance(r["predicted_latents"], list) and r["predicted_latents"], r
    # each latent vector has >= 3 dims (frontend projects first 3 to XYZ)
    assert all(len(v) >= 3 for v in r["observed_latents"]), "observed latent dim < 3"
    assert all(len(v) >= 3 for v in r["predicted_latents"]), "predicted latent dim < 3"
    assert len(r["observed_latents"]) == r["rollout_horizon"] + 1, r
    assert len(r["predicted_latents"]) == r["rollout_horizon"], r
    assert len(r["physical_surprise"]) == r["rollout_horizon"], r

    # (b) bounds: consistency in (0,1]; action acc in [0,1]; surprise non-negative.
    assert 0.0 < r["free_energy_consistency"] <= 1.0, r["free_energy_consistency"]
    assert 0.0 <= r["action_anticipation_acc"] <= 1.0, r["action_anticipation_acc"]
    assert r["prediction_error"] >= 0.0, r
    assert all(s >= 0.0 for s in r["physical_surprise"]), r["physical_surprise"]
    out["metrics"] = {"prediction_error": r["prediction_error"],
                      "free_energy_consistency": r["free_energy_consistency"],
                      "action_anticipation_acc": r["action_anticipation_acc"],
                      "n_steps": len(r["physical_surprise"])}

    # (c) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (d) determinism: same inputs -> identical trajectory.
    r2 = worldmodel_predict(seed=42, horizon=12, latent_dim=16)
    assert r2["observed_latents"] == r["observed_latents"], "non-deterministic observed"
    assert r2["physical_surprise"] == r["physical_surprise"], "non-deterministic surprise"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
