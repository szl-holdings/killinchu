# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_titans.py — ADDITIVE Titans neural long-term memory organ for killinchu's frontier
surface (backs a11oy static/3d/surfaces/titans.js).

Titans (Behrouz, Zhong, Mirrokni 2024/2025, arXiv:2501.00663) add a neural long-term memory
module that learns to memorize historical context AT TEST TIME. The memory is a small network
whose parameters are updated online by gradient descent on a "surprise" signal — the gradient
of an associative loss — with a MOMENTUM term (past surprise) and a FORGET/weight-decay gate.
Attention acts as short-term memory (accurate but bounded context); the neural memory acts as
persistent long-term memory, letting Titans scale to context windows beyond 2M tokens.

Deterministic MODELED formulation (seeded, no autograd, no GPU):
  * Memory as a linear associative store M (d_v x d_k): recall(k) = M · k.
  * Online write on a stream of (key, value) pairs. Surprise s_t = value - M·key (associative
    error). Update with momentum and adaptive forgetting, mirroring the paper's rule:
        S_t   = eta * S_{t-1} + theta * (v_t ⊗ k_t - (M_{t-1} k_t) ⊗ k_t)   (momentary surprise + past)
        M_t   = (1 - alpha) * M_{t-1} + S_t                                  (alpha = forget gate)
    computed by hand in pure Python (outer products, no framework).
  * Report: recall accuracy on the written pairs, mean surprise over time (should DECAY as the
    memory learns), effective memory capacity, and the forget-gate value.

  recall_error = mean || v_i - M·k_i ||   over stored pairs
  surprise_t   = || v_t - M_{t-1}·k_t ||
  retention    = 1 - recall_error / recall_error_at_start

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic online associative-memory write/recall. NOT the Titans model running;
    NO autograd, NO GPU, NO trained weights; the memory is a single linear associative store,
    a faithful but small stand-in for the paper's deep neural memory.
  * eta (momentum), theta (learning rate) and alpha (forget gate) are SEEDED inputs / MODELED
    references, not learned schedules.
  * The 2M-token context claim is a property of the PAPER, cited, not something this organ runs.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/titans/recall  — neural long-term memory recall snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | ONLINE_ASSOC_MEMORY | NOT_LIVE | NO_AUTOGRAD | NO_TRAINED_WEIGHTS"

CITATIONS = {
    "titans": ("Behrouz, Zhong, Mirrokni (2024/2025) Titans: Learning to Memorize at Test "
               "Time — arXiv:2501.00663"),
    "titans_url": "https://arxiv.org/abs/2501.00663",
}


class _LCG:
    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)

    def random(self) -> float:
        self._s = (self._s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((self._s >> 11) & ((1 << 53) - 1)) / float(1 << 53)

    def gauss(self) -> float:
        u1 = max(1e-12, self.random())
        u2 = self.random()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unit(v: list[float]) -> list[float]:
    n = _math.sqrt(sum(x * x for x in v)) or 1e-12
    return [x / n for x in v]


def titans_recall(seed: int = 42, d: int = 8, patterns: int = 8, epochs: int = 8,
                  eta: float = 0.6, theta: float = 0.35, alpha: float = 0.03) -> dict:
    """Titans neural long-term memory recall snapshot (MODELED).

    d        — key/value dimension.
    patterns — number of distinct (key, value) associations the memory must retain.
    epochs   — passes over the pattern set (test-time memorization; surprise decays).
    eta      — momentum on past surprise (S_{t-1} carry).
    theta    — learning rate on momentary surprise.
    alpha    — forget gate (weight decay of the memory per step).
    """
    d = max(2, min(64, int(d)))
    patterns = max(2, min(256, int(patterns)))
    epochs = max(2, min(256, int(epochs)))
    eta = max(0.0, min(0.95, float(eta)))
    theta = max(1e-3, min(1.0, float(theta)))
    alpha = max(0.0, min(0.5, float(alpha)))
    rng = _LCG(int(seed) * 1_000_003 + d * 131 + patterns * 17 + epochs)

    # generate distinct unit keys and values (deterministic); a bounded set to memorize
    keys = [_unit([rng.gauss() for _ in range(d)]) for _ in range(patterns)]
    vals = [_unit([rng.gauss() for _ in range(d)]) for _ in range(patterns)]

    M = [[0.0] * d for _ in range(d)]      # d_v x d_k associative store
    S = [[0.0] * d for _ in range(d)]      # surprise momentum state
    surprise_trace = []

    def _mv(mat, x):
        return [sum(mat[i][j] * x[j] for j in range(d)) for i in range(d)]

    # test-time memorization: repeatedly present the bounded pattern set (Titans learns
    # to memorize at test time). Surprise on each presentation should DECAY over epochs.
    for _ep in range(epochs):
        ep_surprise = 0.0
        for t in range(patterns):
            k = keys[t]
            v = vals[t]
            pred = _mv(M, k)                                  # M_{t-1} · k
            err = [v[i] - pred[i] for i in range(d)]          # momentary surprise vector
            ep_surprise += _math.sqrt(sum(e * e for e in err))
            # S_t = eta*S_{t-1} + theta*(err ⊗ k)
            for i in range(d):
                ei = err[i]
                for j in range(d):
                    S[i][j] = eta * S[i][j] + theta * ei * k[j]
            # M_t = (1-alpha)*M_{t-1} + S_t
            for i in range(d):
                for j in range(d):
                    M[i][j] = (1.0 - alpha) * M[i][j] + S[i][j]
        surprise_trace.append(ep_surprise / patterns)

    # recall error over all stored pairs after training
    rec_errs = []
    for t in range(patterns):
        pred = _mv(M, keys[t])
        rec_errs.append(_math.sqrt(sum((vals[t][i] - pred[i]) ** 2 for i in range(d))))
    recall_error = sum(rec_errs) / patterns
    recall_accuracy = max(0.0, 1.0 - recall_error / 2.0)   # unit vectors -> max dist ~2

    surprise_start = surprise_trace[0]
    surprise_end = surprise_trace[-1]
    surprise_decay = 1.0 - (surprise_end / surprise_start) if surprise_start > 1e-9 else 0.0

    return {
        "service": "titans-neural-long-term-memory",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/titans.js ---
        "dim": int(d),
        "patterns": int(patterns),
        "epochs": int(epochs),
        "recall_error": round(float(recall_error), 6),
        "recall_accuracy": round(float(recall_accuracy), 6),
        "mean_surprise_start": round(float(surprise_start), 6),
        "mean_surprise_end": round(float(surprise_end), 6),
        "surprise_decay_frac": round(float(surprise_decay), 6),
        "forget_gate_alpha": round(float(alpha), 6),
        "momentum_eta": round(float(eta), 6),
        "surprise_trace": [round(float(s), 5) for s in surprise_trace[:16]],
        "formulas": {
            "recall": "recall(k) = M · k",
            "surprise": "s_t = || v_t - M_{t-1}·k_t ||",
            "momentum": "S_t = eta*S_{t-1} + theta*(err ⊗ k)",
            "write": "M_t = (1 - alpha)*M_{t-1} + S_t",
        },
        "compute_backend": {
            "backend": "CPU pure-Python online associative memory",
            "label": "MODELED",
            "honest_note": ("Deterministic single-layer associative store with momentum + forget "
                            "gate; NO autograd, NO GPU, NO trained deep memory. The 2M-token "
                            "context result belongs to the paper, cited — this organ does not "
                            "run it. Deep neural memory is ROADMAP."),
        },
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (recall advisory — never an autonomous action)",
        "wired_into": "frontier ring — Titans long-term memory surface",
        "honest_note": ("MODELED online associative-memory write/recall mirroring the Titans "
                        "surprise + momentum + forget update rule at small scale. NOT the Titans "
                        "model; eta/theta/alpha are seeded inputs. MODELED, not live; advisory to "
                        "Λ (Conjecture 1)."),
        "citations": {"titans": CITATIONS["titans"], "titans_url": CITATIONS["titans_url"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/titans" % ns

    @app.get("%s/recall" % base)
    async def _kc_titans(seed: int = 42, d: int = 8, patterns: int = 8, epochs: int = 8):  # noqa: ANN202
        try:
            return JSONResponse(titans_recall(seed=seed, d=d, patterns=patterns, epochs=epochs))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "titans-neural-long-term-memory",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "recall_accuracy": None}, status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401
    except Exception:  # pragma: no cover
        pass
    return {"ok": True, "ns": ns, "routes": ["%s/recall" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = titans_recall(seed=42, d=8, patterns=8, epochs=8)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("dim", "patterns", "epochs"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("recall_error", "recall_accuracy", "surprise_decay_frac", "forget_gate_alpha"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["surprise_trace"], list) and r["surprise_trace"], r
    assert 0.0 <= r["recall_accuracy"] <= 1.0, r
    # surprise should decay as the memory learns
    assert r["mean_surprise_end"] < r["mean_surprise_start"], r
    assert r["surprise_decay_frac"] > 0.0, r
    assert "2501.00663" in r["citations"]["titans"], r
    out["metrics"] = {"recall_error": r["recall_error"], "recall_accuracy": r["recall_accuracy"],
                      "mean_surprise_start": r["mean_surprise_start"],
                      "mean_surprise_end": r["mean_surprise_end"],
                      "surprise_decay_frac": r["surprise_decay_frac"]}

    # determinism
    r2 = titans_recall(seed=42, d=8, patterns=8, epochs=8)
    assert r2["surprise_trace"] == r["surprise_trace"], "non-deterministic"
    assert r2["recall_error"] == r["recall_error"], "non-deterministic recall"
    out["deterministic"] = True

    p = register(_FakeApp())
    assert p["routes"] == ["/api/killinchu/v1/titans/recall"], p
    out["route"] = p["routes"][0]

    out["ok"] = True
    return out


class _FakeApp:
    def get(self, path):
        def _d(fn):
            return fn
        return _d


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("recall_acc=%.4f  recall_err=%.4f  surprise_start=%.4f  surprise_end=%.4f  decay=%.4f"
          % (res["metrics"]["recall_accuracy"], res["metrics"]["recall_error"],
             res["metrics"]["mean_surprise_start"], res["metrics"]["mean_surprise_end"],
             res["metrics"]["surprise_decay_frac"]))
    assert res["ok"]
    print("ALL OK")
