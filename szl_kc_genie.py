# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_genie.py — ADDITIVE GENIE-STYLE WORLD-MODEL ROLLOUT organ for killinchu's
frontier surface (backs a11oy static/3d/surfaces/genie.js).

Genie (Bruce, Dennis, Edwards, Parker-Holder et al., DeepMind 2024, arXiv:2402.15391)
is a generative interactive environment: an 11B-parameter foundation world model
learned unsupervised from unlabelled internet videos. It has three parts — a
spatiotemporal video TOKENIZER, an autoregressive DYNAMICS model, and a LATENT ACTION
model that infers a small discrete action codebook (|A| latent actions) with NO
ground-truth action labels. A user picks a latent action per frame and Genie rolls the
world forward frame-by-frame. This organ re-derives that control loop deterministically:
a learned-latent action codebook drives a stable latent DYNAMICS map, and we measure
how controllable and how consistent the rollout is.

Deterministic MODELED formulation (seeded, no live model, no video, no GPU):
  * latent state z_t in R^d. A fixed contractive dynamics operator A (spectral radius
    rho < 1) plus a per-action shift b(a) advances the latent: z_{t+1} = A z_t + b(a_t).
  * a latent-action codebook of |A| discrete actions, each a seeded shift vector b(a).
  * ACTION CONTROLLABILITY: how distinguishable the |A| next-states are from a shared
    z_t — mean pairwise L2 between {z_t stepped by each action}, normalized. Higher =
    the latent actions actually steer the world (Genie's key property).
  * ROLLOUT CONSISTENCY: contraction keeps ||z_t|| bounded; we report the trajectory
    energy decay and the free-energy-style consistency 1/(1+drift) where drift is the
    step-to-step change once a fixed action is held (a stable world settles).
  * ACTION-ANTICIPATION accuracy: given an observed next-latent, recover which codebook
    action best explains it (argmin over predicted shifts) vs the true action.

  controllability      = mean_pairwise_L2(next states over actions) / (1 + ||z||)
  rollout_consistency  = mean_t 1/(1 + ||z_{t+1}-z_t|| under held action)
  action_anticip_acc   = fraction of steps whose true action is argmin-recovered
  spectral_radius rho  = max |eigen-proxy| of A (reported < 1 => stable)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic latent-dynamics SIMULATION framed as a GOVERNED rollout.
    NOT Genie running; NO learned world model, NO video tokenizer, NO trained latent
    action model, NO GPU. Latents, the codebook, and A are synthetic seeded inputs.
  * Controllability / consistency / anticipation are properties of the MODELED linear
    dynamics, honestly labeled — not measured on a real environment.
  * Every simulated interdiction is a Decision-Simulation receipt vs a synthetic state;
    the effector is SIMULATED · human-on-loop, never autonomous.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/genie/rollout  — latent-action world-model rollout snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import json as _json
import math as _math
from datetime import datetime, timezone

try:
    from szl_dsse import sign_payload as _sign_payload
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.genie+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": _base64.b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_GENIE_PAYLOAD_TYPE = "application/vnd.szl.kc.genie+json"
DOCTRINE_VERSION = "v11"

CITATIONS = {
    "genie": ("Bruce, Dennis, Edwards, Parker-Holder, Shi, Hughes et al. (2024) Genie: "
              "Generative Interactive Environments (DeepMind, 11B foundation world model) — "
              "arXiv:2402.15391 — https://arxiv.org/abs/2402.15391"),
    "dreamerv3": ("Hafner, Pasukonis, Ba, Lillicrap (2023) Mastering Diverse Domains through "
                  "World Models (DreamerV3) — arXiv:2301.04104 — https://arxiv.org/abs/2301.04104"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | LATENT_DYNAMICS_SIM | NOT_LIVE | NO_WORLD_MODEL | NO_VIDEO | NO_GPU"

# MODELED per-rollout-step compute reference (order-of-magnitude only; NOT a wattmeter).
_J_PER_LATENT_STEP = 5.0e-3


class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (int(seed) ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def signed(self) -> float:
        return 2.0 * self.uniform() - 1.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _l2(u, v):
    return _math.sqrt(sum((a - b) ** 2 for a, b in zip(u, v)))


def _norm(u):
    return _math.sqrt(sum(a * a for a in u))


def genie_rollout(seed: int = 42, dim: int = 8, n_actions: int = 6,
                  horizon: int = 32, rho: float = 0.85) -> dict:
    """Latent-action world-model rollout snapshot (MODELED).

    dim       — latent dimensionality d.
    n_actions — |A|, size of the learned latent-action codebook.
    horizon   — rollout length (frames stepped).
    rho       — target spectral radius of the contractive dynamics (< 1 => stable).
    seed      — RNG seed; identical inputs give identical output (deterministic).
    """
    d = max(2, min(64, int(dim)))
    na = max(2, min(32, int(n_actions)))
    H = max(4, min(512, int(horizon)))
    rho = max(0.05, min(0.99, float(rho)))
    rng = _LCG(int(seed) * 1_000_003 + d * 131 + na * 17 + H * 7 + int(rho * 1000))

    # Diagonal contractive dynamics A: entries in [-rho, rho] => spectral radius <= rho.
    A = [rho * (0.5 + 0.5 * rng.uniform()) * (1.0 if rng.uniform() < 0.5 else -1.0)
         for _ in range(d)]
    spectral_radius = max(abs(a) for a in A)

    # Latent-action codebook: na seeded shift vectors b(a).
    codebook = [[rng.signed() for _ in range(d)] for _ in range(na)]

    def step(z, a_idx):
        b = codebook[a_idx]
        return [A[i] * z[i] + b[i] for i in range(d)]

    # 1) controllability: from a shared z0, how distinguishable are the na next-states?
    z0 = [rng.signed() for _ in range(d)]
    nexts = [step(z0, a) for a in range(na)]
    pair_sum, pair_n = 0.0, 0
    for i in range(na):
        for j in range(i + 1, na):
            pair_sum += _l2(nexts[i], nexts[j])
            pair_n += 1
    mean_pair = pair_sum / pair_n if pair_n else 0.0
    controllability = mean_pair / (1.0 + _norm(z0))

    # 2) rollout with a scripted action sequence; track consistency + energy decay.
    z = list(z0)
    action_seq = [rng.next_u32() % na for _ in range(H)]
    energies = [_norm(z)]
    drifts = []
    prev = list(z)
    obs = []  # (true_action, observed_next) for anticipation
    for t in range(H):
        a = action_seq[t]
        z2 = step(z, a)
        drifts.append(_l2(z2, prev) / (1.0 + _norm(prev)))
        obs.append((a, z2, list(z)))
        prev = list(z2)
        z = z2
        energies.append(_norm(z))
    rollout_consistency = sum(1.0 / (1.0 + dft) for dft in drifts) / len(drifts)

    # 3) action-anticipation: recover the action that best explains each observed next.
    correct = 0
    for true_a, z_next, z_prev in obs:
        best_a, best_err = 0, None
        for a in range(na):
            pred = step(z_prev, a)
            err = _l2(pred, z_next)
            if best_err is None or err < best_err:
                best_err, best_a = err, a
        if best_a == true_a:
            correct += 1
    action_anticipation_acc = correct / len(obs)

    energy_decay = energies[-1] / energies[0] if energies[0] else 0.0
    free_energy_consistency = 1.0 / (1.0 + (sum(drifts) / len(drifts)))

    joules_modeled = H * _J_PER_LATENT_STEP
    energy_receipt = {
        "joules_per_latent_step_modeled": _J_PER_LATENT_STEP,
        "rollout_joules_modeled": round(float(joules_modeled), 6),
        "steps": H,
        "energy_note": ("MODELED per-latent-step compute — order-of-magnitude only, NOT a live "
                        "wattmeter. A latent rollout is far cheaper than pixel simulation; this "
                        "quantifies that as an advisory input, not a certified number."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "genie-latent-world-model-rollout",
        "service_version": "szl-kc-genie-v0.1",
        "seed": int(seed),
        "inputs": {"dim": d, "n_actions": na, "horizon": H, "rho": rho},
        "spectral_radius": round(float(spectral_radius), 6),
        "controllability": round(float(controllability), 6),
        "rollout_consistency": round(float(rollout_consistency), 6),
        "action_anticipation_acc": round(float(action_anticipation_acc), 6),
        "free_energy_consistency": round(float(free_energy_consistency), 6),
        "energy_decay": round(float(energy_decay), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (rollout advisory — never an autonomous action)",
        "citations": [CITATIONS["genie"], CITATIONS["dreamerv3"]],
        "honesty": ("Deterministic latent-dynamics rollout simulation. NOT Genie running; NO learned "
                    "world model, NO video tokenizer, NO trained latent-action model, NO GPU, NO live "
                    "environment. Latents, codebook, and A are synthetic seeded inputs. Controllability/"
                    "consistency/anticipation are properties of the MODELED linear dynamics. MODELED, "
                    "not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _GENIE_PAYLOAD_TYPE)

    return {
        "service": "genie-latent-world-model-rollout",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/genie.js ---
        "dim": int(d),
        "n_actions": int(na),
        "horizon": int(H),
        "rho": round(float(rho), 6),
        "spectral_radius": round(float(spectral_radius), 6),
        "controllability": round(float(controllability), 6),
        "rollout_consistency": round(float(rollout_consistency), 6),
        "action_anticipation_acc": round(float(action_anticipation_acc), 6),
        "free_energy_consistency": round(float(free_energy_consistency), 6),
        "energy_decay": round(float(energy_decay), 6),
        "latent_energy_trace": [round(float(e), 4) for e in energies[:16]],
        "stable": bool(spectral_radius < 1.0),
        # --- SZL addition: the latent-step energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "dynamics": "z_{t+1} = A z_t + b(a_t)  (contractive A, spectral radius < 1)",
            "controllability": "mean_pairwise_L2(next states over actions) / (1 + ||z||)",
            "rollout_consistency": "mean_t 1/(1 + ||z_{t+1}-z_t||_norm)",
            "action_anticipation_acc": "fraction of steps whose true action is argmin-recovered",
        },
        "compute_backend": {
            "backend": "CPU pure-Python latent-dynamics simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic sim; NO learned world model, NO video, NO GPU, NO live "
                            "environment. The measured-on-a-real-world-model path is ROADMAP."),
        },
        "wired_into": "frontier ring — Genie latent-rollout surface + governed decision-sim receipt",
        "citations": [CITATIONS["genie"], CITATIONS["dreamerv3"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/genie" % ns

    async def _kc_genie(seed: int = 42, dim: int = 8, n_actions: int = 6,
                        horizon: int = 32, rho: float = 0.85):  # noqa: ANN202
        try:
            return JSONResponse(genie_rollout(seed=seed, dim=dim, n_actions=n_actions,
                                              horizon=horizon, rho=rho))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "genie-latent-world-model-rollout",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "controllability": None, "rollout_consistency": None},
                                status_code=200)

    try:
        app.add_api_route("%s/rollout" % base, _kc_genie, methods=["GET"])
    except Exception:  # pragma: no cover — Starlette Route fallback
        from starlette.routing import Route

        async def _kc_genie_route(request):
            qp = request.query_params
            return await _kc_genie(seed=int(qp.get("seed", 42)),
                                   dim=int(qp.get("dim", 8)),
                                   n_actions=int(qp.get("n_actions", 6)),
                                   horizon=int(qp.get("horizon", 32)),
                                   rho=float(qp.get("rho", 0.85)))
        app.router.routes.append(Route("%s/rollout" % base, _kc_genie_route, methods=["GET"]))

    return {"ok": True, "ns": ns, "routes": ["%s/rollout" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = genie_rollout(seed=42, dim=8, n_actions=6, horizon=32, rho=0.85)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("controllability", "rollout_consistency", "action_anticipation_acc",
              "free_energy_consistency", "spectral_radius"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    # stability invariant: contractive dynamics keeps spectral radius < 1.
    assert r["spectral_radius"] < 1.0, r["spectral_radius"]
    assert r["stable"] is True, r
    assert r["controllability"] > 0.0, r
    assert 0.0 <= r["action_anticipation_acc"] <= 1.0, r
    assert 0.0 < r["rollout_consistency"] <= 1.0, r
    assert 0.0 < r["free_energy_consistency"] <= 1.0, r
    # contraction => trajectory energy stays bounded (does not blow up).
    assert r["latent_energy_trace"][-1] <= r["latent_energy_trace"][0] * 5.0, r
    out["metrics"] = {"controllability": r["controllability"],
                      "rollout_consistency": r["rollout_consistency"],
                      "action_anticipation_acc": r["action_anticipation_acc"],
                      "spectral_radius": r["spectral_radius"]}

    er = r["energy_receipt"]
    assert er["rollout_joules_modeled"] > 0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"rollout_joules_modeled": er["rollout_joules_modeled"]}

    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc

    r2 = genie_rollout(seed=42, dim=8, n_actions=6, horizon=32, rho=0.85)
    assert r2["controllability"] == r["controllability"], "non-deterministic controllability"
    assert r2["action_anticipation_acc"] == r["action_anticipation_acc"], "non-deterministic anticip"
    assert r2["latent_energy_trace"] == r["latent_energy_trace"], "non-deterministic trace"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("ALL OK")
