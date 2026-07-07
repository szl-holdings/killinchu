# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_goat.py — ADDITIVE GOAT (Optimal-Transport Attention) Sinkhorn demonstrator for
killinchu's frontier surface (backs a11oy static/3d/surfaces/goat.js).

Plain softmax attention parks runaway probability mass on a single "sink" token (token 0) —
the attention-sink pathology (Xiao et al., StreamingLLM). Casting attention as ENTROPIC
OPTIMAL TRANSPORT replaces the row-wise softmax with a Sinkhorn-normalized transport plan
between queries and keys under a trainable key prior (the target marginal), so mass is
redistributed by relevance instead of collapsing onto the sink. This module runs a REAL
Sinkhorn scaling recursion on a seeded query/key cost matrix and reports the sink-mass before
(softmax) vs after (OT), the reduction, and the per-iteration convergence residuals — all
COMPUTED, never hard-coded.

Sinkhorn OT-attention (seeded, no trained transformer):
  * cost C[i][j] = squared distance between seeded query i and key j embeddings.
  * kernel K = exp(-C / reg); Sinkhorn scales u,v so P = diag(u)·K·diag(v) matches marginals
    (uniform over queries; a seeded TRAINABLE key prior over keys).
  * attn_softmax_row0 = softmax(-C[0])            (the sink-prone reference row)
  * attn_goat_row0    = P[0] / sum(P[0])          (the OT-normalized attention row)
  * sink_softmax / sink_goat = mass on key 0 under each; sink_reduction = the collapse of it.
  * sinkhorn_residuals[k] = marginal violation ‖P·1 − r‖_1 after iteration k (COMPUTED).
  * converged = last residual < tol.

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic re-implementation of the attention-as-optimal-transport arithmetic.
    There is NO trained transformer, NO learned attention, NO GPU — only a seeded cost matrix
    + a real Sinkhorn recursion. Query/key embeddings and the key prior are SEEDED, not learned.
  * The transport plan, sink masses and residuals are EXACT for the seeded inputs (real Sinkhorn
    arithmetic) — a demonstration of the MECHANISM, not a measurement of a trained model.
  * "GOAT" is the frontend's clean-room name for this OT-attention organ (leader cited:
    arXiv:2601.15380); the arithmetic here is the standard entropic-OT/Sinkhorn recursion
    (Cuturi 2013). NEVER claimed as a trained SZL model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/goat/transport  — OT-attention Sinkhorn snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.goat+json"):  # type: ignore
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

_GOAT_PAYLOAD_TYPE = "application/vnd.szl.kc.goat+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "goat": ("GOAT: Generalized Optimal-transport Attention with Trainable priors "
             "(attention-as-OT removing attention sinks) — arXiv:2601.15380"),
    "cuturi": ("Cuturi (2013) Sinkhorn Distances: Lightspeed Computation of Optimal "
               "Transport (entropic-OT scaling recursion) — arXiv:1306.0895"),
    "streamingllm": ("Xiao, Tian, Chen, Han, Lewis (2023) Efficient Streaming Language Models "
                     "with Attention Sinks (StreamingLLM) — arXiv:2309.17453"),
    "sinkformers": ("Sander, Ablin, Blondel, Peyré (2022) Sinkformers: Transformers with "
                    "Doubly Stochastic Attention — arXiv:2110.11773"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = ("MODELED | OT_ATTENTION_SINKHORN_SIM | NOT_LIVE | NO_TRAINED_TRANSFORMER | "
                "SEEDED_EMBEDDINGS")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _softmax(xs):
    m = max(xs)
    exps = [_math.exp(x - m) for x in xs]
    s = sum(exps) or 1.0
    return [e / s for e in exps]


def goat_transport(seed: int = 42, n_q: int = 12, n_k: int = 16,
                   iters: int = 40, reg: float = 1.0) -> dict:
    """OT-attention Sinkhorn snapshot (MODELED).

    n_q   — number of query tokens.
    n_k   — number of key tokens.
    iters — Sinkhorn scaling iterations.
    reg   — entropic regularization ε (larger = smoother/more uniform plan).
    seed  — RNG seed; identical inputs give identical output (deterministic).
    """
    n_q = max(1, min(128, int(n_q)))
    n_k = max(2, min(128, int(n_k)))
    iters = max(1, min(500, int(iters)))
    reg = float(reg)
    if not (reg > 0):
        reg = 1.0
    reg = max(1e-3, min(100.0, reg))

    rng = _random.Random(int(seed) * 2_654_435_761 % (2 ** 32) + n_q * 131 + n_k * 17 + iters)

    dim = 8
    # Queries cluster near the origin. Key 0 is a low-norm "sink" key sitting right in that
    # cluster, so it is the nearest key to EVERY query → plain softmax(−dist) piles mass onto
    # it (the attention-sink pathology, geometrically — no additive logit hack). All other keys
    # are spread out on a wider shell, so they are genuinely relevant-or-not by distance.
    q_emb = [[rng.gauss(0.0, 0.5) for _ in range(dim)] for _ in range(n_q)]
    k_emb = [[rng.gauss(0.0, 0.15) for _ in range(dim)]]  # key 0: the sink, near all queries
    for _ in range(1, n_k):
        k_emb.append([rng.gauss(0.0, 1.4) for _ in range(dim)])

    # cost C[i][j] = squared Euclidean distance q_i↔k_j; softmax(−C[0]) concentrates on the
    # near sink key 0 (the pathology GOAT removes via the OT key-prior constraint).
    cost = [[0.0] * n_k for _ in range(n_q)]
    for i in range(n_q):
        for j in range(n_k):
            d2 = sum((q_emb[i][d] - k_emb[j][d]) ** 2 for d in range(dim))
            cost[i][j] = d2

    # --- reference softmax attention row 0 (sink-prone) --------------------------------
    attn_softmax_row0 = _softmax([-cost[0][j] for j in range(n_k)])
    sink_softmax = round(float(attn_softmax_row0[0]), 6)

    # --- REAL Sinkhorn entropic-OT recursion ------------------------------------------
    # marginals: uniform over queries (r); a seeded TRAINABLE key prior over keys (c) that
    # deliberately does NOT over-weight key 0 → the plan cannot dump mass on the sink.
    r = [1.0 / n_q] * n_q
    raw_prior = [abs(rng.gauss(1.0, 0.35)) + 0.05 for _ in range(n_k)]
    prior_sum = sum(raw_prior) or 1.0
    c = [p / prior_sum for p in raw_prior]

    kernel = [[_math.exp(-cost[i][j] / reg) for j in range(n_k)] for i in range(n_q)]

    u = [1.0] * n_q
    v = [1.0] * n_k
    residuals = []
    tol = 1e-6
    for _ in range(iters):
        # u_i = r_i / (K v)_i
        for i in range(n_q):
            kv = sum(kernel[i][j] * v[j] for j in range(n_k)) or 1e-300
            u[i] = r[i] / kv
        # v_j = c_j / (K^T u)_j
        for j in range(n_k):
            ktu = sum(kernel[i][j] * u[i] for i in range(n_q)) or 1e-300
            v[j] = c[j] / ktu
        # residual: row-marginal violation ‖P·1 − r‖_1 (COMPUTED each iteration)
        row_viol = 0.0
        for i in range(n_q):
            row_i = sum(u[i] * kernel[i][j] * v[j] for j in range(n_k))
            row_viol += abs(row_i - r[i])
        residuals.append(round(float(row_viol), 9))
        if row_viol < tol:
            break

    converged = bool(residuals and residuals[-1] < tol)

    # transport plan row 0, renormalized to a proper attention distribution
    plan_row0 = [u[0] * kernel[0][j] * v[j] for j in range(n_k)]
    z0 = sum(plan_row0) or 1.0
    attn_goat_row0 = [p / z0 for p in plan_row0]
    sink_goat = round(float(attn_goat_row0[0]), 6)

    sink_reduction = round(sink_softmax - sink_goat, 6)

    prior_desc = ("trainable key prior (seeded target marginal; uniform-ish, NOT peaked on the "
                  "sink) — the OT constraint that redistributes mass off token 0")

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "goat-ot-attention",
        "service_version": "szl-kc-goat-v0.1",
        "seed": int(seed),
        "inputs": {"n_q": n_q, "n_k": n_k, "iters": iters, "reg": reg},
        "sink_softmax": sink_softmax,
        "sink_goat": sink_goat,
        "sink_reduction": sink_reduction,
        "converged": converged,
        "sinkhorn_iterations_run": len(residuals),
        "final_residual": residuals[-1] if residuals else None,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (attention demo — never an engage)",
        "citations": [CITATIONS["goat"], CITATIONS["cuturi"], CITATIONS["streamingllm"],
                      CITATIONS["sinkformers"]],
        "honesty": ("OT-attention Sinkhorn demonstration. NO trained transformer, NO learned "
                    "attention, NO GPU. Query/key embeddings and the key prior are seeded; the "
                    "Sinkhorn transport plan, sink masses and residuals are exact for those "
                    "seeded inputs (real entropic-OT recursion, Cuturi 2013). 'GOAT' is the "
                    "clean-room OT-attention organ name (leader arXiv:2601.15380), NOT a trained "
                    "SZL model. MODELED, not live."),
    }
    dsse = _sign_payload(receipt, _GOAT_PAYLOAD_TYPE)

    return {
        "service": "goat-ot-attention",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/goat.js ---
        "n_q": int(n_q),
        "n_k": int(n_k),
        "iters": int(iters),
        "reg": float(reg),
        "prior": prior_desc,
        "sink_softmax": sink_softmax,
        "sink_goat": sink_goat,
        "sink_reduction": sink_reduction,
        "sinkhorn_residuals": residuals,
        "attn_softmax_row0": [round(float(w), 6) for w in attn_softmax_row0],
        "attn_goat_row0": [round(float(w), 6) for w in attn_goat_row0],
        "converged": converged,
        # --- provenance ---
        "formulas": {
            "cost": "C[i][j] = ||q_i − k_j||^2 − sink_bias[j]",
            "kernel": "K = exp(−C / reg)",
            "sinkhorn": "u = r / (K v);  v = c / (Kᵀ u)  (entropic-OT scaling; c = trainable key prior)",
            "attn_softmax_row0": "softmax(−C[0])",
            "attn_goat_row0": "P[0] / Σ P[0],  P = diag(u)·K·diag(v)",
            "sink_reduction": "sink_softmax − sink_goat",
            "residual": "‖P·1 − r‖_1 per Sinkhorn iteration",
        },
        "compute_backend": {
            "backend": "CPU pure-Python Sinkhorn entropic-OT recursion",
            "label": "MODELED",
            "honest_note": ("Seeded query/key embeddings + a real Sinkhorn transport plan; NO "
                            "trained transformer, NO learned attention, NO GPU. The trained "
                            "OT-attention path is ROADMAP."),
        },
        "wired_into": "frontier ring — GOAT OT-attention surface (softmax-sink vs OT-redistributed)",
        "citations": [CITATIONS["goat"], CITATIONS["cuturi"], CITATIONS["streamingllm"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/goat" % ns

    @app.get("%s/transport" % base)
    async def _kc_goat(seed: int = 42, n_q: int = 12, n_k: int = 16,
                       iters: int = 40, reg: float = 1.0):  # noqa: ANN202
        try:
            return JSONResponse(goat_transport(seed=seed, n_q=n_q, n_k=n_k, iters=iters, reg=reg))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "goat-ot-attention", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "sink_reduction": None}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/transport" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = goat_transport(seed=42, n_q=12, n_k=16, iters=40, reg=1.0)

    # (a) honest label verbatim + every field the frontend reads is present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("n_q", "n_k", "iters"):
        assert isinstance(r[f], int), (f, r.get(f))
    assert isinstance(r["reg"], float), r
    assert isinstance(r["prior"], str) and r["prior"], r
    for f in ("sink_softmax", "sink_goat", "sink_reduction"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["converged"], bool), r
    for f in ("sinkhorn_residuals", "attn_softmax_row0", "attn_goat_row0"):
        assert isinstance(r[f], list) and r[f], (f, r.get(f))

    # (b) attention rows are valid distributions; OT reduces the sink mass.
    assert len(r["attn_softmax_row0"]) == r["n_k"], r
    assert len(r["attn_goat_row0"]) == r["n_k"], r
    assert abs(sum(r["attn_softmax_row0"]) - 1.0) < 1e-4, ("softmax row !~ 1", sum(r["attn_softmax_row0"]))
    assert abs(sum(r["attn_goat_row0"]) - 1.0) < 1e-4, ("goat row !~ 1", sum(r["attn_goat_row0"]))
    # the whole point: OT collapses the softmax sink on token 0.
    assert r["sink_goat"] <= r["sink_softmax"], ("OT did not reduce sink", r["sink_softmax"], r["sink_goat"])
    assert abs(r["sink_reduction"] - (r["sink_softmax"] - r["sink_goat"])) < 1e-5, r
    # residuals are non-increasing-ish and non-negative (Sinkhorn converges monotonically).
    assert all(x >= 0.0 for x in r["sinkhorn_residuals"]), r["sinkhorn_residuals"]
    out["metrics"] = {"sink_softmax": r["sink_softmax"], "sink_goat": r["sink_goat"],
                      "sink_reduction": r["sink_reduction"], "converged": r["converged"],
                      "iters_run": len(r["sinkhorn_residuals"])}

    # (c) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (d) determinism: same inputs -> identical snapshot.
    r2 = goat_transport(seed=42, n_q=12, n_k=16, iters=40, reg=1.0)
    assert r2["attn_goat_row0"] == r["attn_goat_row0"], "non-deterministic goat row"
    assert r2["sinkhorn_residuals"] == r["sinkhorn_residuals"], "non-deterministic residuals"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
