# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_kvcache.py — ADDITIVE H2O HEAVY-HITTER KV-CACHE-EVICTION simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/kvcache.js).

H2O (Heavy-Hitter Oracle; Zhang, Sheng, Zhou, Chen, Zheng, Cai, Song, Tian, Ré, Barrett, Wang,
Chen 2023, arXiv:2306.14048) shrinks the transformer KV cache during generation. Its observation:
a small fraction of tokens ("Heavy Hitters", H2) accumulate most of the attention mass, and
removing them badly hurts quality — while most tokens contribute little and can be evicted. H2O
keeps a fixed-size cache holding a balance of RECENT tokens plus the accumulated-attention HEAVY
HITTERS, evicting the lowest-score non-recent token when the budget is exceeded. It frames eviction
as a dynamic-submodular problem and shows large throughput gains at a fixed cache budget.

This module reproduces the H2O eviction POLICY deterministically. It streams a seeded sequence of
tokens, accumulates a MODELED attention score per cached token (heavy hitters get large recurring
mass), and applies the H2O rule: always keep the last `recent` tokens; when the cache exceeds the
budget, evict the non-recent token with the lowest accumulated attention score. It reports the
cache hit-rate on true heavy hitters, the retained-attention-mass fraction (quality proxy), the
memory saved vs. a full cache, and — the SZL addition — a J/token ENERGY RECEIPT from the smaller
KV footprint.

Deterministic eviction model (seeded, no live model, no real attention):
  * each token i gets a MODELED "true importance" from a heavy-tailed seeded distribution; a small
    set are designated heavy hitters (large recurring attention mass).
  * per step: append the new token's KV; add its incoming attention to cached tokens' scores;
    if cache size > budget, evict the lowest-score token OUTSIDE the recent window.

  hh_retention        = fraction of true heavy hitters still resident at end of stream
  retained_mass_frac  = kept accumulated attention mass / total accumulated attention mass
  memory_reduction    = 1 - budget / seq_len
  E_full_cache        = seq_len * e_kv_slot          (dense cache: one slot per token, all steps)
  E_h2o               = budget  * e_kv_slot          (fixed-budget cache)
  joules_per_token_saved = (E_full_cache - E_h2o) / seq_len   (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic eviction SIMULATION. NOT H2O running inside a real model; NO live model,
    NO GPU, NO real KV cache, NO real attention scores. The per-token importances and the heavy-
    hitter set are SEEDED MODELED values, NOT measured attention.
  * The eviction POLICY (fixed budget = recent window + top accumulated-attention heavy hitters,
    evict lowest non-recent score) is H2O's actual mechanism, honestly reimplemented; the numbers
    are properties of that policy over the seeded stream, not a benchmark result on a real model.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/kvcache/h2o-evict  — H2O heavy-hitter eviction snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.kvcache+json"):  # type: ignore
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

_KV_PAYLOAD_TYPE = "application/vnd.szl.kc.kvcache+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "h2o": ("Zhang, Sheng, Zhou, Chen, Zheng, Cai, Song, Tian, Ré, Barrett, Wang, Chen (2023) "
            "H2O: Heavy-Hitter Oracle for Efficient Generative Inference of Large Language Models "
            "— arXiv:2306.14048 — https://arxiv.org/abs/2306.14048"),
}

# MODELED label — a deterministic eviction simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | H2O_EVICTION_SIM | NOT_LIVE | NO_MODEL | NO_KV_CACHE | JOULES_ARE_MODELED"

# MODELED per-unit energy references (order-of-magnitude only; NOT a live wattmeter).
_E_KV_SLOT = 1.0     # MODELED joules to hold+attend one KV cache slot for the generation


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kvcache_h2o_evict(seed: int = 42, seq_len: int = 1024, budget: int = 256,
                      recent: int = 64, n_heavy: int = 32) -> dict:
    """H2O heavy-hitter KV-cache eviction snapshot (MODELED).

    seq_len  — number of tokens streamed through generation.
    budget   — fixed KV cache size (slots).
    recent   — size of the always-kept recent window.
    n_heavy  — number of true heavy-hitter tokens seeded into the stream.
    seed     — RNG seed; identical inputs give identical output (deterministic).
    """
    seq_len = max(16, min(1_000_000, int(seq_len)))
    budget = max(4, min(seq_len, int(budget)))
    recent = max(1, min(budget, int(recent)))
    n_heavy = max(1, min(seq_len, int(n_heavy)))
    rng = _random.Random(int(seed) * 1_000_003 + seq_len * 131 + budget * 17 + recent)

    # seeded heavy-hitter set + per-token base incoming attention weight.
    heavy = set()
    while len(heavy) < n_heavy:
        heavy.add(rng.randrange(seq_len))
    base_weight = []
    for i in range(seq_len):
        w = rng.random() ** 3  # heavy-tailed: most tokens small
        if i in heavy:
            w += 3.0 + rng.random() * 2.0  # heavy hitters carry large recurring mass
        base_weight.append(w)

    # stream tokens; accumulate attention scores; evict lowest non-recent when over budget.
    scores = {}          # token_id -> accumulated attention score (resident tokens only)
    total_mass = 0.0     # total attention mass ever generated (for retained-mass fraction)
    for i in range(seq_len):
        # each new token distributes incoming attention over resident tokens by their base weight.
        incoming = base_weight[i]
        total_mass += incoming
        # add the new token to the cache
        scores[i] = scores.get(i, 0.0) + incoming
        # every resident token also accrues a little ongoing mass proportional to its base weight
        for tid in list(scores.keys()):
            add = base_weight[tid] * 0.02
            scores[tid] += add
            total_mass += add
        # evict if over budget: drop lowest-score token OUTSIDE the recent window.
        if len(scores) > budget:
            recent_floor = i - recent + 1
            evictable = [(tid, s) for tid, s in scores.items() if tid < recent_floor]
            if evictable:
                victim = min(evictable, key=lambda t: t[1])[0]
                del scores[victim]
            else:
                # all resident tokens are recent; drop the globally lowest (degenerate budget)
                victim = min(scores.items(), key=lambda t: t[1])[0]
                del scores[victim]

    resident = set(scores.keys())
    hh_resident = len(resident & heavy)
    hh_retention = hh_resident / len(heavy)
    retained_mass = sum(scores.values())
    retained_mass_frac = retained_mass / total_mass if total_mass else 0.0
    memory_reduction = 1.0 - budget / seq_len

    # top resident tokens by score (what the tab renders).
    top_resident = sorted(scores.items(), key=lambda t: t[1], reverse=True)[:16]
    top_resident_scores = [round(float(s), 5) for _, s in top_resident]

    # ENERGY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    e_full = seq_len * _E_KV_SLOT     # dense cache: one slot per token
    e_h2o = budget * _E_KV_SLOT       # fixed-budget cache
    joules_saved = e_full - e_h2o
    joules_per_token_saved = joules_saved / seq_len if seq_len else 0.0
    energy_reduction_pct = (joules_saved / e_full * 100.0) if e_full else 0.0

    energy_receipt = {
        "joules_full_cache": round(float(e_full), 4),
        "joules_h2o": round(float(e_h2o), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_token_saved": round(float(joules_per_token_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_kv_slot_modeled": _E_KV_SLOT,
        "energy_note": ("MODELED joules — order-of-magnitude per-slot estimates, NOT a live "
                        "wattmeter. A fixed KV budget instead of a growing dense cache is the "
                        "memory/energy win; quantified as a receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "h2o-heavy-hitter-eviction",
        "service_version": "szl-kc-kvcache-v0.1",
        "seed": int(seed),
        "inputs": {"seq_len": seq_len, "budget": budget, "recent": recent, "n_heavy": n_heavy},
        "hh_retention": round(float(hh_retention), 6),
        "retained_mass_frac": round(float(retained_mass_frac), 6),
        "memory_reduction": round(float(memory_reduction), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (eviction advisory — never an autonomous action)",
        "citations": [CITATIONS["h2o"]],
        "honesty": ("Deterministic H2O eviction-policy simulation over a seeded token stream. NOT "
                    "H2O running inside a real model; NO live model, NO GPU, NO real KV cache, NO "
                    "real attention. Per-token importances and the heavy-hitter set are seeded "
                    "MODELED values; the eviction POLICY is H2O's mechanism, honestly "
                    "reimplemented. MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _KV_PAYLOAD_TYPE)

    return {
        "service": "h2o-heavy-hitter-eviction",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/kvcache.js ---
        "seq_len": int(seq_len),
        "budget": int(budget),
        "recent": int(recent),
        "n_heavy": int(n_heavy),
        "hh_retention": round(float(hh_retention), 6),
        "hh_resident": int(hh_resident),
        "retained_mass_frac": round(float(retained_mass_frac), 6),
        "memory_reduction": round(float(memory_reduction), 6),
        "resident_count": int(len(resident)),
        "top_resident_scores": top_resident_scores,   # [float]
        # --- SZL addition: the J/token-saved energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "policy": "keep last `recent` tokens + evict lowest accumulated-attention non-recent",
            "hh_retention": "|resident ∩ heavy_hitters| / |heavy_hitters|",
            "retained_mass_frac": "kept accumulated attention mass / total attention mass",
            "memory_reduction": "1 - budget / seq_len",
            "joules_per_token_saved": "(E_full_cache - E_h2o) / seq_len",
            "E_full_cache": "seq_len * e_kv_slot",
            "E_h2o": "budget * e_kv_slot",
        },
        "compute_backend": {
            "backend": "CPU pure-Python eviction-policy simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic H2O eviction sim; NO live model, NO GPU, NO real KV "
                            "cache, NO real attention. The measured-on-a-real-model path is "
                            "ROADMAP."),
        },
        "wired_into": "frontier ring — KV-Cache H2O surface + llm-router energy receipt",
        "citations": [CITATIONS["h2o"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/kvcache" % ns

    @app.get("%s/h2o-evict" % base)
    async def _kc_kvcache(seed: int = 42, seq_len: int = 1024, budget: int = 256,
                          recent: int = 64, n_heavy: int = 32):  # noqa: ANN202
        try:
            return JSONResponse(kvcache_h2o_evict(seed=seed, seq_len=seq_len, budget=budget,
                                                  recent=recent, n_heavy=n_heavy))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "h2o-heavy-hitter-eviction",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "hh_retention": None, "memory_reduction": None},
                                status_code=200)

    # Starlette Route fallback.
    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_kvcache_route(request):  # pragma: no cover — fallback path
            q = request.query_params
            try:
                return _SJSON(kvcache_h2o_evict(
                    seed=int(q.get("seed", 42)),
                    seq_len=int(q.get("seq_len", 1024)),
                    budget=int(q.get("budget", 256)),
                    recent=int(q.get("recent", 64)),
                    n_heavy=int(q.get("n_heavy", 32))))
            except Exception as exc:
                return _SJSON({"service": "h2o-heavy-hitter-eviction",
                               "label": MODELED_LABEL,
                               "error": "compute fail-open: %s" % (str(exc)[:160])},
                              status_code=200)

        if not any(getattr(r, "path", None) == "%s/h2o-evict" % base
                   for r in getattr(app.router, "routes", [])):
            app.router.routes.append(Route("%s/h2o-evict" % base, _kc_kvcache_route,
                                           methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": ["%s/h2o-evict" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = kvcache_h2o_evict(seed=42, seq_len=1024, budget=256, recent=64, n_heavy=32)

    # (a) honest label verbatim + every field the frontend reads present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "budget", "recent", "n_heavy", "hh_resident", "resident_count"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("hh_retention", "retained_mass_frac", "memory_reduction"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["top_resident_scores"], list) and r["top_resident_scores"], r
    assert all(isinstance(x, (int, float)) for x in r["top_resident_scores"]), r

    # (b) surface-specific invariants: cache never exceeds budget; heavy hitters retained better
    #     than the memory budget would give at random; mass mostly retained; sorted scores.
    assert r["resident_count"] <= r["budget"], r
    assert 0.0 <= r["hh_retention"] <= 1.0, r
    assert 0.0 <= r["retained_mass_frac"] <= 1.0, r
    assert 0.0 < r["memory_reduction"] < 1.0, r
    # H2O should retain heavy hitters far better than a random budget/seq_len fraction
    assert r["hh_retention"] > r["budget"] / r["seq_len"], (r["hh_retention"], r["budget"], r["seq_len"])
    # and it should retain most of the attention mass despite dropping most tokens
    assert r["retained_mass_frac"] > 0.5, r["retained_mass_frac"]
    ts = r["top_resident_scores"]
    assert all(ts[i] >= ts[i + 1] - 1e-9 for i in range(len(ts) - 1)), ts
    out["metrics"] = {"hh_retention": r["hh_retention"], "retained_mass_frac": r["retained_mass_frac"],
                      "memory_reduction": r["memory_reduction"], "resident_count": r["resident_count"]}

    # (c) energy receipt: positive joules saved on this profile.
    er = r["energy_receipt"]
    assert er["joules_saved"] > 0, er
    assert er["joules_per_token_saved"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"joules_saved": er["joules_saved"],
                             "joules_per_token_saved": er["joules_per_token_saved"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical result.
    r2 = kvcache_h2o_evict(seed=42, seq_len=1024, budget=256, recent=64, n_heavy=32)
    assert r2["top_resident_scores"] == r["top_resident_scores"], "non-deterministic"
    assert r2["hh_retention"] == r["hh_retention"], "non-deterministic retention"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    assert res["ok"] is True
    print("ALL OK")
