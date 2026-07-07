# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_inplacettt.py — ADDITIVE IN-PLACE TEST-TIME-TRAINING organ for killinchu's
frontier surface (backs a11oy static/3d/surfaces/inplacettt.js).

In-Place Test-Time Training (Feng, Luo, Hua, Zhang, He, Huang, Cai 2026,
arXiv:2604.06169 — VERIFIED to resolve) endows a frozen LLM with test-time adaptation
by treating the FINAL PROJECTION MATRIX of the ubiquitous MLP block as adaptable "fast
weights", updated at inference time with a next-token-prediction-aligned objective and
an efficient chunk-wise update. It is a drop-in enhancement (no retraining from
scratch), reaching strong long-context performance (contexts up to 128k) on a 4B model.
The core idea inherits Test-Time Training (Sun et al. 2020, arXiv:1909.13231): adapt a
subset of parameters on each incoming example via a self-supervised loss before
predicting.

This organ re-derives the fast-weight adaptation loop deterministically: a chunk-wise
gradient step on a projection matrix W drives down a next-token-style reconstruction
loss across a stream of context chunks, and we measure the loss trajectory, the
adaptation gain vs a frozen baseline, and stability of the fast weights.

Deterministic MODELED formulation (seeded, no live model, no GPU):
  * per chunk c: an input feature h_c in R^d and a target t_c in R^k. The fast weight
    is a projection W (k x d). Prediction yhat = W h_c ; loss L_c = ||yhat - t_c||^2.
  * IN-PLACE fast-weight step (one gradient step per chunk, chunk-wise):
        W <- W - eta * grad_W L_c ,  grad_W L_c = 2 (W h_c - t_c) h_c^T
    i.e. the classic least-squares SGD update on the ubiquitous projection matrix.
  * FROZEN baseline keeps W = W0 (no adaptation) for the same stream.
  * adaptation_gain = (mean frozen loss - mean adapted loss) / mean frozen loss.
  * stability = 1/(1 + mean step-to-step ||W_{c+1}-W_c||_F) (fast weights shouldn't
    diverge — a well-set eta keeps the in-place update contractive).

  L_c                = ||W_c h_c - t_c||^2
  W_{c+1}            = W_c - eta * 2 (W_c h_c - t_c) h_c^T   (in-place fast weight)
  adaptation_gain    = (L_frozen_mean - L_adapted_mean) / L_frozen_mean
  final_loss         = mean over last chunk-window of L_c (adapted)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic chunk-wise fast-weight SIMULATION on synthetic features.
    NOT In-Place TTT running; NO live model, NO GPU, NO trained weights, NO real
    context stream. h_c, t_c, W0, and eta are seeded inputs / MODELED references.
  * The loss reduction is a property of least-squares SGD on the MODELED stream,
    honestly labeled — not a measured claim about a real LLM on real tokens.
  * The J/adapt-step footprint is a MODELED order-of-magnitude figure, NOT a wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/inplacettt/adapt  — in-place test-time-training snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.inplacettt+json"):  # type: ignore
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

_TTT_PAYLOAD_TYPE = "application/vnd.szl.kc.inplacettt+json"
DOCTRINE_VERSION = "v11"

CITATIONS = {
    "inplacettt": ("Feng, Luo, Hua, Zhang, He, Huang, Cai (2026) In-Place Test-Time Training — "
                   "arXiv:2604.06169 — https://arxiv.org/abs/2604.06169"),
    "ttt": ("Sun, Wang, Liu, Miller, Efros, Hardt (2020) Test-Time Training with Self-Supervision "
            "for Generalization under Distribution Shifts — arXiv:1909.13231 — "
            "https://arxiv.org/abs/1909.13231"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | INPLACE_FASTWEIGHT_SIM | NOT_LIVE | NO_MODEL | NO_WEIGHTS | NO_GPU"

_J_PER_ADAPT_STEP = 2.0e-3


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


def _matvec(W, h):
    return [sum(W[r][c] * h[c] for c in range(len(h))) for r in range(len(W))]


def _frob_diff(A, B):
    s = 0.0
    for r in range(len(A)):
        for c in range(len(A[0])):
            d = A[r][c] - B[r][c]
            s += d * d
    return _math.sqrt(s)


def inplacettt_adapt(seed: int = 42, dim: int = 8, out_dim: int = 4,
                     n_chunks: int = 48, eta: float = 0.05) -> dict:
    """In-place test-time-training snapshot (MODELED).

    dim       — input feature dimensionality d.
    out_dim   — projection output dimensionality k (the "final projection matrix").
    n_chunks  — number of context chunks streamed (chunk-wise update count).
    eta       — fast-weight learning rate for the in-place gradient step.
    seed      — RNG seed; identical inputs give identical output (deterministic).
    """
    d = max(2, min(64, int(dim)))
    k = max(1, min(32, int(out_dim)))
    C = max(4, min(2000, int(n_chunks)))
    eta = max(1e-4, min(0.5, float(eta)))
    rng = _LCG(int(seed) * 1_000_003 + d * 131 + k * 17 + C * 7 + int(eta * 1e6))

    # A latent "true" projection W_star generates the targets from features (the
    # distribution the fast weights should adapt toward on this stream).
    W_star = [[rng.signed() for _ in range(d)] for _ in range(k)]
    # W0 starts off from W_star (distribution shift the TTT step should correct).
    W0 = [[W_star[r][c] + 0.6 * rng.signed() for c in range(d)] for r in range(k)]

    # stream of chunks (feature, target = W_star @ feature + small noise).
    chunks = []
    for _ in range(C):
        h = [rng.signed() for _ in range(d)]
        t = [sum(W_star[r][c] * h[c] for c in range(d)) + 0.05 * rng.signed() for r in range(k)]
        chunks.append((h, t))

    # ADAPTED pass: in-place chunk-wise fast-weight update.
    W = [row[:] for row in W0]
    adapted_losses = []
    frob_steps = []
    for (h, t) in chunks:
        yhat = _matvec(W, h)
        err = [yhat[r] - t[r] for r in range(k)]
        adapted_losses.append(sum(e * e for e in err))
        W_prev = [row[:] for row in W]
        # grad_W L = 2 err h^T ; in-place step.
        for r in range(k):
            g = 2.0 * err[r]
            for c in range(d):
                W[r][c] -= eta * g * h[c]
        frob_steps.append(_frob_diff(W, W_prev))

    # FROZEN baseline: no adaptation, same stream.
    frozen_losses = []
    for (h, t) in chunks:
        yhat = _matvec(W0, h)
        frozen_losses.append(sum((yhat[r] - t[r]) ** 2 for r in range(k)))

    frozen_mean = sum(frozen_losses) / C
    adapted_mean = sum(adapted_losses) / C
    adaptation_gain = (frozen_mean - adapted_mean) / frozen_mean if frozen_mean else 0.0

    window = max(1, C // 8)
    final_loss = sum(adapted_losses[-window:]) / window
    initial_loss = sum(adapted_losses[:window]) / window
    loss_reduction = (initial_loss - final_loss) / initial_loss if initial_loss else 0.0

    mean_step = sum(frob_steps) / len(frob_steps)
    stability = 1.0 / (1.0 + mean_step)

    joules_modeled = C * _J_PER_ADAPT_STEP
    energy_receipt = {
        "joules_per_adapt_step_modeled": _J_PER_ADAPT_STEP,
        "adapt_joules_modeled": round(float(joules_modeled), 6),
        "adapt_steps": C,
        "energy_note": ("MODELED per-chunk fast-weight-step compute — order-of-magnitude only, NOT "
                        "a live wattmeter. In-place adaptation is one small projection update per "
                        "chunk; this quantifies that as an advisory input, not a certified number."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "in-place-test-time-training",
        "service_version": "szl-kc-inplacettt-v0.1",
        "seed": int(seed),
        "inputs": {"dim": d, "out_dim": k, "n_chunks": C, "eta": eta},
        "frozen_mean_loss": round(float(frozen_mean), 6),
        "adapted_mean_loss": round(float(adapted_mean), 6),
        "adaptation_gain": round(float(adaptation_gain), 6),
        "loss_reduction": round(float(loss_reduction), 6),
        "final_loss": round(float(final_loss), 6),
        "stability": round(float(stability), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (adaptation advisory — never an autonomous action)",
        "citations": [CITATIONS["inplacettt"], CITATIONS["ttt"]],
        "honesty": ("Deterministic chunk-wise fast-weight simulation on synthetic features. NOT "
                    "In-Place TTT running; NO live model, NO GPU, NO trained weights, NO real context "
                    "stream. h_c, t_c, W0, eta are seeded inputs / MODELED references. The loss "
                    "reduction is a property of least-squares SGD on the MODELED stream, honestly "
                    "labeled. MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _TTT_PAYLOAD_TYPE)

    return {
        "service": "in-place-test-time-training",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/inplacettt.js ---
        "dim": int(d),
        "out_dim": int(k),
        "n_chunks": int(C),
        "eta": round(float(eta), 6),
        "frozen_mean_loss": round(float(frozen_mean), 6),
        "adapted_mean_loss": round(float(adapted_mean), 6),
        "adaptation_gain": round(float(adaptation_gain), 6),
        "loss_reduction": round(float(loss_reduction), 6),
        "initial_loss": round(float(initial_loss), 6),
        "final_loss": round(float(final_loss), 6),
        "stability": round(float(stability), 6),
        "loss_trace": [round(float(x), 4) for x in adapted_losses[:16]],
        # --- SZL addition: the adapt-step energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "loss": "L_c = ||W_c h_c - t_c||^2",
            "inplace_step": "W_{c+1} = W_c - eta * 2 (W_c h_c - t_c) h_c^T",
            "adaptation_gain": "(L_frozen_mean - L_adapted_mean) / L_frozen_mean",
            "stability": "1/(1 + mean ||W_{c+1}-W_c||_F)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python fast-weight simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic sim; NO live model, NO GPU, NO trained weights, NO real "
                            "context stream. The measured-on-a-real-LLM path is ROADMAP."),
        },
        "wired_into": "frontier ring — In-Place TTT adaptation surface + adapt energy receipt",
        "citations": [CITATIONS["inplacettt"], CITATIONS["ttt"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/inplacettt" % ns

    async def _kc_ttt(seed: int = 42, dim: int = 8, out_dim: int = 4,
                      n_chunks: int = 48, eta: float = 0.05):  # noqa: ANN202
        try:
            return JSONResponse(inplacettt_adapt(seed=seed, dim=dim, out_dim=out_dim,
                                                 n_chunks=n_chunks, eta=eta))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "in-place-test-time-training",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "adaptation_gain": None, "final_loss": None},
                                status_code=200)

    try:
        app.add_api_route("%s/adapt" % base, _kc_ttt, methods=["GET"])
    except Exception:  # pragma: no cover — Starlette Route fallback
        from starlette.routing import Route

        async def _kc_ttt_route(request):
            qp = request.query_params
            return await _kc_ttt(seed=int(qp.get("seed", 42)),
                                 dim=int(qp.get("dim", 8)),
                                 out_dim=int(qp.get("out_dim", 4)),
                                 n_chunks=int(qp.get("n_chunks", 48)),
                                 eta=float(qp.get("eta", 0.05)))
        app.router.routes.append(Route("%s/adapt" % base, _kc_ttt_route, methods=["GET"]))

    return {"ok": True, "ns": ns, "routes": ["%s/adapt" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = inplacettt_adapt(seed=42, dim=8, out_dim=4, n_chunks=48, eta=0.05)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("frozen_mean_loss", "adapted_mean_loss", "adaptation_gain",
              "loss_reduction", "final_loss", "stability"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    # adaptation invariant: in-place TTT should reduce loss vs frozen baseline.
    assert r["adapted_mean_loss"] < r["frozen_mean_loss"], r
    assert r["adaptation_gain"] > 0.0, r
    assert r["final_loss"] < r["initial_loss"], r
    assert 0.0 < r["stability"] <= 1.0, r
    out["metrics"] = {"frozen_mean_loss": r["frozen_mean_loss"],
                      "adapted_mean_loss": r["adapted_mean_loss"],
                      "adaptation_gain": r["adaptation_gain"],
                      "loss_reduction": r["loss_reduction"],
                      "stability": r["stability"]}

    er = r["energy_receipt"]
    assert er["adapt_joules_modeled"] > 0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"adapt_joules_modeled": er["adapt_joules_modeled"]}

    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc

    r2 = inplacettt_adapt(seed=42, dim=8, out_dim=4, n_chunks=48, eta=0.05)
    assert r2["adaptation_gain"] == r["adaptation_gain"], "non-deterministic gain"
    assert r2["final_loss"] == r["final_loss"], "non-deterministic final loss"
    assert r2["loss_trace"] == r["loss_trace"], "non-deterministic trace"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("ALL OK")
