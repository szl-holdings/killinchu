# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_moe.py — ADDITIVE Mixture-of-Experts top-k router organ for killinchu's frontier
surface (backs a11oy static/3d/surfaces/moe.js).

Sparse Mixture-of-Experts layers replace one dense FFN with E experts and a small gating
network that routes each token to its top-k experts, so only k of E experts run per token
and compute is decoupled from parameter count. Switch Transformer (Fedus, Zoph, Shazeer 2021,
arXiv:2101.03961) popularized top-1 routing with a load-balancing auxiliary loss; Mixtral 8x7B
(Jiang et al. 2024, arXiv:2401.04088) uses top-2 of 8 experts. Sparse upcycling (Komatsuzaki
et al. 2022, arXiv:2212.05055) initializes an MoE from a dense checkpoint. The central
engineering problem is LOAD BALANCE: a router that collapses onto a few experts wastes the
rest and drops tokens past an expert's capacity.

Deterministic MODELED formulation (seeded, no live model):
  * Tokens: N seeded feature vectors. Router logits = token · gate_vector per expert, gate
    vectors seeded per expert. Softmax over logits -> routing probabilities.
  * Top-k selection: each token routed to its k highest-probability experts.
  * Capacity: each expert holds up to capacity_factor * (k*N/E) tokens; overflow tokens are
    "dropped" (routed nowhere), exactly as in the real capacity mechanism.
  * Report: per-expert load, load-balance auxiliary loss (Switch form), dropped-token rate,
    routing entropy, and the active-parameter fraction (k/E) — the compute saving.

  aux_loss  = E * sum_e ( f_e * P_e )            (Switch load-balance loss; f=frac tokens,
                                                  P=mean router prob per expert)
  drop_rate = dropped_tokens / (k * N)
  active_param_fraction = k / E                  (fraction of expert params run per token)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic top-k routing SIMULATION. NOT Mixtral/Switch running; NO live model,
    NO GPU, NO trained gate. Router logits come from seeded gate vectors, not learned weights.
  * The aux-loss and drop-rate are computed on the SIMULATED routing, honestly labeled; they
    are not measured on a real MoE forward pass.
  * "active_param_fraction = k/E" is the algorithmic compute-saving ratio, a property of sparse
    routing, not a wall-clock benchmark.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/moe/route  — Mixture-of-Experts routing snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | TOPK_ROUTING_SIM | NOT_LIVE | NO_MODEL | NO_TRAINED_GATE"

CITATIONS = {
    "switch": ("Fedus, Zoph, Shazeer (2021) Switch Transformers: Scaling to Trillion "
               "Parameter Models with Simple and Efficient Sparsity — arXiv:2101.03961"),
    "mixtral": ("Jiang et al. (2024) Mixtral of Experts — arXiv:2401.04088"),
    "upcycling": ("Komatsuzaki, Puigcerver, Lee-Thorp, Riquelme, Mustafa, Ainslie, Tay, "
                  "Dehghani, Houlsby (2022) Sparse Upcycling: Training Mixture-of-Experts "
                  "from Dense Checkpoints — arXiv:2212.05055"),
    "switch_url": "https://arxiv.org/abs/2101.03961",
    "mixtral_url": "https://arxiv.org/abs/2401.04088",
    "upcycling_url": "https://arxiv.org/abs/2212.05055",
}


class _LCG:
    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)

    def random(self) -> float:
        self._s = (self._s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((self._s >> 11) & ((1 << 53) - 1)) / float(1 << 53)

    def gauss(self) -> float:
        # Box-Muller from two uniforms (deterministic)
        u1 = max(1e-12, self.random())
        u2 = self.random()
        return _math.sqrt(-2.0 * _math.log(u1)) * _math.cos(2.0 * _math.pi * u2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _softmax(xs: list[float]) -> list[float]:
    m = max(xs)
    ex = [_math.exp(x - m) for x in xs]
    s = sum(ex) or 1e-12
    return [e / s for e in ex]


def moe_route(seed: int = 42, experts: int = 8, top_k: int = 2, tokens: int = 512,
              dim: int = 16, capacity_factor: float = 1.25) -> dict:
    """Mixture-of-Experts routing snapshot (MODELED).

    experts         — E, number of experts.
    top_k           — k experts per token (Switch=1, Mixtral=2).
    tokens          — N tokens routed.
    dim             — token feature dimension.
    capacity_factor — per-expert capacity multiplier over the balanced share.
    """
    E = max(2, min(256, int(experts)))
    k = max(1, min(E, int(top_k)))
    N = max(8, min(20000, int(tokens)))
    d = max(2, min(256, int(dim)))
    cf = max(0.5, min(4.0, float(capacity_factor)))
    rng = _LCG(int(seed) * 1_000_003 + E * 131 + N)

    # seeded gate vectors per expert
    gates = [[rng.gauss() for _ in range(d)] for _ in range(E)]

    capacity = int(_math.ceil(cf * (k * N) / E))
    load = [0] * E
    prob_sum = [0.0] * E
    frac_count = [0] * E
    dropped = 0
    total_assign = 0

    for _ in range(N):
        tok = [rng.gauss() for _ in range(d)]
        logits = [sum(tok[j] * gates[e][j] for j in range(d)) for e in range(E)]
        probs = _softmax(logits)
        # top-k experts by prob
        order = sorted(range(E), key=lambda e: probs[e], reverse=True)[:k]
        for e in order:
            prob_sum[e] += probs[e]
            frac_count[e] += 1
            total_assign += 1
            if load[e] < capacity:
                load[e] += 1
            else:
                dropped += 1

    # Switch load-balance aux loss: E * sum_e f_e * P_e
    f = [frac_count[e] / (k * N) for e in range(E)]          # fraction of routed slots -> e
    P = [prob_sum[e] / N for e in range(E)]                  # mean router prob mass -> e
    aux_loss = E * sum(f[e] * P[e] for e in range(E))

    drop_rate = dropped / (k * N)
    active_param_fraction = k / E

    # routing entropy over the load distribution (bits): high = well balanced
    tot_load = sum(load) or 1
    ent = 0.0
    for e in range(E):
        p = load[e] / tot_load
        if p > 0:
            ent -= p * _math.log2(p)
    max_ent = _math.log2(E)
    balance_score = ent / max_ent if max_ent > 0 else 0.0

    return {
        "service": "mixture-of-experts-router",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/moe.js ---
        "experts": int(E),
        "top_k": int(k),
        "tokens": int(N),
        "capacity_per_expert": int(capacity),
        "expert_load": [int(x) for x in load],
        "aux_load_balance_loss": round(float(aux_loss), 6),
        "dropped_token_rate": round(float(drop_rate), 6),
        "routing_balance_score": round(float(balance_score), 6),
        "active_param_fraction": round(float(active_param_fraction), 6),
        "compute_saving_pct": round(float((1.0 - active_param_fraction) * 100.0), 3),
        "formulas": {
            "aux_load_balance_loss": "E * sum_e (f_e * P_e)  (Switch)",
            "dropped_token_rate": "dropped / (k * N)",
            "active_param_fraction": "k / E",
            "balance_score": "entropy(load) / log2(E)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python top-k routing simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic top-k routing sim; NO Mixtral/Switch, NO GPU, NO "
                            "trained gate. Router logits come from seeded gate vectors. A "
                            "measured MoE forward pass is ROADMAP."),
        },
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (routing advisory — never an autonomous action)",
        "wired_into": "frontier ring — Mixture-of-Experts surface + llm-router",
        "honest_note": ("MODELED deterministic top-k MoE routing over seeded gate vectors. "
                        "Load balance, drop rate and active-param fraction are computed on the "
                        "SIMULATED routing, not a live model. MODELED, not live; advisory to "
                        "Λ (Conjecture 1)."),
        "citations": {"switch": CITATIONS["switch"], "mixtral": CITATIONS["mixtral"],
                      "upcycling": CITATIONS["upcycling"],
                      "switch_url": CITATIONS["switch_url"], "mixtral_url": CITATIONS["mixtral_url"],
                      "upcycling_url": CITATIONS["upcycling_url"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/moe" % ns

    @app.get("%s/route" % base)
    async def _kc_moe(seed: int = 42, experts: int = 8, top_k: int = 2, tokens: int = 512):  # noqa: ANN202
        try:
            return JSONResponse(moe_route(seed=seed, experts=experts, top_k=top_k, tokens=tokens))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "mixture-of-experts-router",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "aux_load_balance_loss": None}, status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401
    except Exception:  # pragma: no cover
        pass
    return {"ok": True, "ns": ns, "routes": ["%s/route" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = moe_route(seed=42, experts=8, top_k=2, tokens=512)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("experts", "top_k", "tokens", "capacity_per_expert"):
        assert isinstance(r[f], int), (f, r.get(f))
    assert isinstance(r["expert_load"], list) and len(r["expert_load"]) == r["experts"], r
    assert all(isinstance(x, int) and x >= 0 for x in r["expert_load"]), r
    assert 0.0 <= r["dropped_token_rate"] <= 1.0, r
    assert 0.0 <= r["routing_balance_score"] <= 1.0, r
    assert abs(r["active_param_fraction"] - 2.0 / 8.0) < 1e-9, r
    assert r["aux_load_balance_loss"] > 0.0, r
    # sum of expert loads never exceeds slots assigned
    assert sum(r["expert_load"]) <= r["top_k"] * r["tokens"], r
    assert "2212.05055" in r["citations"]["upcycling"], r
    assert "2101.03961" in r["citations"]["switch"], r
    out["metrics"] = {"aux_load_balance_loss": r["aux_load_balance_loss"],
                      "dropped_token_rate": r["dropped_token_rate"],
                      "routing_balance_score": r["routing_balance_score"],
                      "active_param_fraction": r["active_param_fraction"],
                      "compute_saving_pct": r["compute_saving_pct"]}

    # determinism
    r2 = moe_route(seed=42, experts=8, top_k=2, tokens=512)
    assert r2["expert_load"] == r["expert_load"], "non-deterministic"
    assert r2["aux_load_balance_loss"] == r["aux_load_balance_loss"], "non-deterministic aux"
    out["deterministic"] = True

    p = register(_FakeApp())
    assert p["routes"] == ["/api/killinchu/v1/moe/route"], p
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
    print("aux_loss=%.4f  drop_rate=%.4f  balance=%.4f  active_frac=%.4f  saving=%.1f%%"
          % (res["metrics"]["aux_load_balance_loss"], res["metrics"]["dropped_token_rate"],
             res["metrics"]["routing_balance_score"], res["metrics"]["active_param_fraction"],
             res["metrics"]["compute_saving_pct"]))
    assert res["ok"]
    print("ALL OK")
