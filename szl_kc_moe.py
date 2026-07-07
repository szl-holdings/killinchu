# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_moe.py — ADDITIVE sparse Mixture-of-Experts (MoE) top-k ROUTER simulator for
killinchu's frontier surface (backs a11oy static/3d/surfaces/moe.js).

A sparse MoE layer replaces one dense FFN with N expert FFNs and a lightweight router
(gating network) that sends each token to only its top-k experts, so per-token FLOPs stay
fixed while total parameters scale with N. Mixtral-8x7B routes each token to top-2 of 8
experts; the Switch Transformer showed a load-balancing auxiliary loss is needed or the
router collapses onto a few "hot" experts. This module runs the ROUTING half deterministically:
seeded gate logits → softmax → top-k selection → renormalized combine weights, and reports
the resulting per-expert load distribution + its coefficient of variation (the balance signal).

Deterministic routing (seeded, no trained gate):
  * gate logits g[t] = W·x[t] are SEEDED per (token, expert) — a stand-in for a trained router.
  * top-k experts per token by gate softmax; combine weights = softmax renormalized over the k.
  * expert_load_counts[e] = number of (token, expert) assignments landing on expert e.
  * load_balance_cv = std(load)/mean(load)  — 0 = perfectly balanced, higher = imbalanced/hot.

HONESTY SPINE (Doctrine v11):
  * MODELED routing SIMULATION. There is NO trained gate, NO expert FFNs, NO GPU, NO forward
    pass — only the seeded top-k router arithmetic. Gate logits are seeded, not learned.
  * The routing_table + load counts are EXACT for the seeded logits (real top-k arithmetic),
    but they are a demonstration of the MECHANISM, not a measurement of a trained model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/moe/route  — sparse MoE top-k routing snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.moe+json"):  # type: ignore
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

_MOE_PAYLOAD_TYPE = "application/vnd.szl.kc.moe+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "mixtral": ("Jiang, Sablayrolles, Roux, Mensch et al. (2024) Mixtral of Experts "
                "(8x7B, top-2 of 8 routing) — arXiv:2401.04088"),
    "switch": ("Fedus, Zoph, Shazeer (2021) Switch Transformers: Scaling to Trillion "
               "Parameter Models with Simple and Efficient Sparsity (load-balancing "
               "auxiliary loss) — arXiv:2101.03961"),
    "upcycling": ("Komatsuzaki, Puigcerver, Lee-Thorp et al. (2022/2023) Sparse Upcycling: "
                  "Training Mixture-of-Experts from Dense Checkpoints — arXiv:2212.05055"),
    "deepseekv2": ("DeepSeek-AI (2024) DeepSeek-V2: fine-grained + shared-expert MoE with "
                   "device-limited routing — arXiv:2405.04434"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | TOPK_ROUTER_SIM | NOT_LIVE | NO_TRAINED_GATE | NO_EXPERT_FFN | SEEDED_LOGITS"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _softmax(xs):
    m = max(xs)
    exps = [_math.exp(x - m) for x in xs]
    s = sum(exps) or 1.0
    return [e / s for e in exps]


def moe_route(seed: int = 42, tokens: int = 64, experts: int = 8, topk: int = 2) -> dict:
    """Sparse MoE top-k routing snapshot (MODELED).

    tokens  — number of tokens routed this snapshot.
    experts — number of experts N.
    topk    — experts activated per token (k).
    seed    — RNG seed; identical inputs give identical output (deterministic).
    """
    tokens = max(1, min(4096, int(tokens)))
    experts = max(2, min(256, int(experts)))
    topk = max(1, min(experts, int(topk)))
    rng = _random.Random(int(seed) * 2_654_435_761 % (2 ** 32) + tokens * 131 + experts * 17 + topk)

    # A mild seeded per-expert bias so the load is realistically uneven (some experts run
    # "hotter") — the honest reason a load-balancing auxiliary loss exists in real MoE.
    expert_bias = [rng.gauss(0.0, 0.6) for _ in range(experts)]

    routing_table = []
    load_counts = [0] * experts
    for t in range(tokens):
        # seeded gate logits g[t][e] (stand-in for a trained router W·x)
        logits = [rng.gauss(0.0, 1.0) + expert_bias[e] for e in range(experts)]
        order = sorted(range(experts), key=lambda e: logits[e], reverse=True)
        chosen = order[:topk]
        # combine weights = softmax renormalized over ONLY the chosen k (Mixtral-style)
        chosen_logits = [logits[e] for e in chosen]
        weights = _softmax(chosen_logits)
        for e in chosen:
            load_counts[e] += 1
        routing_table.append({
            "token": t,
            "chosen_experts": [int(e) for e in chosen],
            "weights": [round(float(w), 5) for w in weights],
        })

    mean_load = sum(load_counts) / experts
    var_load = sum((c - mean_load) ** 2 for c in load_counts) / experts
    std_load = _math.sqrt(var_load)
    load_balance_cv = round(std_load / mean_load, 6) if mean_load > 0 else 0.0
    min_load = min(load_counts)
    max_load = max(load_counts)

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "moe-topk-router",
        "service_version": "szl-kc-moe-v0.1",
        "seed": int(seed),
        "inputs": {"tokens": tokens, "experts": experts, "topk": topk},
        "expert_load_counts": load_counts,
        "load_balance_cv": load_balance_cv,
        "min_expert_load": int(min_load),
        "max_expert_load": int(max_load),
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (router demo — never an engage)",
        "citations": [CITATIONS["mixtral"], CITATIONS["switch"], CITATIONS["upcycling"],
                      CITATIONS["deepseekv2"]],
        "honesty": ("Sparse MoE top-k router simulation. NO trained gate, NO expert FFNs, NO "
                    "forward pass, NO GPU. Gate logits are seeded; the top-k arithmetic and "
                    "load counts are exact for those seeded logits. MODELED, not live."),
    }
    dsse = _sign_payload(receipt, _MOE_PAYLOAD_TYPE)

    return {
        "service": "moe-topk-router",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/moe.js ---
        "tokens": int(tokens),
        "experts": int(experts),
        "topk": int(topk),
        "routing_table": routing_table,          # [{token, chosen_experts, weights}]
        "expert_load_counts": load_counts,        # [int] per-expert final load
        "load_balance_cv": load_balance_cv,       # std/mean of load
        "min_expert_load": int(min_load),
        "max_expert_load": int(max_load),
        # --- provenance ---
        "formulas": {
            "gate": "top-k(softmax(W·x));  combine = softmax renormalized over the chosen k",
            "load_balance_cv": "std(expert_load_counts) / mean(expert_load_counts)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python top-k router",
            "label": "MODELED",
            "honest_note": ("Seeded gate logits + exact top-k routing arithmetic; NO trained "
                            "gate, NO expert FFNs, NO GPU. The trained-MoE forward path is ROADMAP."),
        },
        "wired_into": "frontier ring — MoE Router surface (expert-load heat-surface)",
        "citations": [CITATIONS["mixtral"], CITATIONS["switch"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/moe" % ns

    @app.get("%s/route" % base)
    async def _kc_moe(seed: int = 42, tokens: int = 64, experts: int = 8, topk: int = 2):  # noqa: ANN202
        try:
            return JSONResponse(moe_route(seed=seed, tokens=tokens, experts=experts, topk=topk))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "moe-topk-router", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "load_balance_cv": None}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/route" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = moe_route(seed=42, tokens=64, experts=8, topk=2)

    # (a) honest label verbatim + every field the frontend reads is present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("tokens", "experts", "topk"):
        assert isinstance(r[f], int), (f, r.get(f))
    assert isinstance(r["load_balance_cv"], (int, float)), r
    assert isinstance(r["routing_table"], list) and len(r["routing_table"]) == r["tokens"], r
    assert isinstance(r["expert_load_counts"], list) and len(r["expert_load_counts"]) == r["experts"], r

    # (b) routing invariants: each token picks exactly topk distinct experts; weights sum ~1.
    for row in r["routing_table"]:
        assert len(row["chosen_experts"]) == r["topk"], row
        assert len(set(row["chosen_experts"])) == r["topk"], ("dup expert", row)
        assert all(0 <= e < r["experts"] for e in row["chosen_experts"]), row
        assert abs(sum(row["weights"]) - 1.0) < 1e-6, ("weights !~ 1", row)
    # total assignments == tokens*topk; load counts consistent.
    assert sum(r["expert_load_counts"]) == r["tokens"] * r["topk"], r
    assert r["load_balance_cv"] >= 0.0, r
    out["metrics"] = {"load_balance_cv": r["load_balance_cv"],
                      "min_load": r["min_expert_load"], "max_load": r["max_expert_load"],
                      "loads": r["expert_load_counts"]}

    # (c) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (d) determinism: same inputs -> identical routing.
    r2 = moe_route(seed=42, tokens=64, experts=8, topk=2)
    assert r2["routing_table"] == r["routing_table"], "non-deterministic routing"
    assert r2["expert_load_counts"] == r["expert_load_counts"], "non-deterministic load"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
