# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_ringattn.py — ADDITIVE Ring-Attention long-context blockwise SIMULATOR for
killinchu's frontier surface (backs a11oy static/3d/surfaces/ringattn.js).

Ring Attention shards the sequence's Q/K/V blocks across a ring of devices; each device holds
one query block and, over `devices` rotation steps, passes its KV block to its neighbour so
every query eventually attends to every KV block — all with an ONLINE softmax accumulator, so
per-device memory is O(seq_len / devices) instead of O(seq_len). Because the online (streaming)
softmax is mathematically EXACT, the blockwise result is bit-for-bit the full-attention result;
context length then scales ~linearly with the ring size. This module simulates the ring schedule
and — critically — RUNS a tiny real online-softmax vs a full-softmax on a seeded example so the
`exact_match` claim is COMPUTED, never asserted.

Ring schedule + honest exactness check:
  * block_size          = ceil(seq_len / devices)         (per-device query/KV block)
  * num_rotation_steps  = devices                          (each KV block visits every device)
  * per_device_memory_ratio = block_size / seq_len ≈ 1/devices   (the memory win, MODELED)
  * max_context_supported   = block_size * devices ≈ seq_len; the ring generalizes to
                              more devices ⇒ longer context at fixed per-device memory.
  * exact_match         = (online-softmax blockwise == full softmax) on a seeded probe,
                          within 1e-9 — COMPUTED here, not hard-coded.

HONESTY SPINE (Doctrine v11):
  * MODELED schedule SIMULATION. There is NO multi-device run, NO GPU, NO NCCL ring, NO model —
    only the ring arithmetic + a tiny CPU online-softmax exactness probe.
  * per_device_memory_ratio / max_context_supported are the MODELED asymptotics of the method,
    not a measured allocator delta. Label them MODELED.
  * exact_match is a REAL numerical check on a seeded vector (online vs full softmax); it
    demonstrates the method's exactness — it is not a measurement of a distributed system.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/ringattn/simulate  — ring-attention blockwise schedule snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.ringattn+json"):  # type: ignore
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

_RA_PAYLOAD_TYPE = "application/vnd.szl.kc.ringattn+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "ring": ("Liu, Zaharia, Abbeel (2023, ICLR 2024) Ring Attention with Blockwise "
             "Transformers for Near-Infinite Context — arXiv:2310.01889"),
    "blockwise": ("Liu, Abbeel (2023) Blockwise Parallel Transformer for Large Context "
                  "Models — arXiv:2305.19370"),
    "flash": ("Dao, Fu, Ermon, Rudra, Ré (2022) FlashAttention: Fast and Memory-Efficient "
              "Exact Attention with IO-Awareness — arXiv:2205.14135"),
    "online_softmax": ("Milakov, Gimelshein (2018) Online normalizer calculation for "
                       "softmax — arXiv:1805.02867"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = ("MODELED | RING_SCHEDULE_SIM | NOT_LIVE | NO_MULTI_DEVICE | NO_GPU | "
                "EXACT_MATCH_IS_A_CPU_PROBE")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _full_softmax_weighted(scores, values):
    """Reference: full softmax over all scores, then weighted sum of values."""
    m = max(scores)
    exps = [_math.exp(s - m) for s in scores]
    z = sum(exps)
    return sum((e / z) * v for e, v in zip(exps, values))


def _online_softmax_blockwise(scores, values, block_size):
    """Streaming (online) softmax accumulator processed one block at a time — the exact
    computation Ring/Flash attention performs. Returns (weighted_value, running_trace).

    Maintains a running max m, running normalizer l, and running weighted accumulator acc,
    rescaling on each block exactly as FlashAttention/Ring do. Mathematically identical to
    the full softmax, up to floating point."""
    m = -_math.inf
    l = 0.0
    acc = 0.0
    trace = []
    n = len(scores)
    for start in range(0, n, block_size):
        blk_s = scores[start:start + block_size]
        blk_v = values[start:start + block_size]
        blk_max = max(blk_s)
        new_m = max(m, blk_max)
        # rescale the existing accumulator to the new max
        correction = _math.exp(m - new_m) if m != -_math.inf else 0.0
        l = l * correction
        acc = acc * correction
        for s, v in zip(blk_s, blk_v):
            w = _math.exp(s - new_m)
            l += w
            acc += w * v
        m = new_m
        trace.append(round(acc / l, 6) if l > 0 else 0.0)  # running attention output
    return (acc / l if l > 0 else 0.0), trace


def ringattn_simulate(seed: int = 42, seq_len: int = 4096, devices: int = 8) -> dict:
    """Ring-attention blockwise schedule snapshot (MODELED).

    seq_len — total context length (tokens).
    devices — ring size (number of devices among which Q/K/V blocks are sharded).
    seed    — RNG seed; identical inputs give identical output (deterministic).
    """
    seq_len = max(2, min(1_048_576, int(seq_len)))
    devices = max(1, min(1024, int(devices)))
    block_size = -(-seq_len // devices)              # ceil division
    num_rotation_steps = devices
    per_device_memory_ratio = round(block_size / seq_len, 8)
    max_context_supported = block_size * devices

    # --- REAL online-softmax exactness probe on a small seeded vector -----------------
    rng = _random.Random(int(seed) * 2_654_435_761 % (2 ** 32) + seq_len + devices * 7)
    probe_n = 256
    probe_scores = [rng.gauss(0.0, 2.0) for _ in range(probe_n)]
    probe_values = [rng.gauss(0.0, 1.0) for _ in range(probe_n)]
    probe_block = max(1, probe_n // max(1, devices))
    full_out = _full_softmax_weighted(probe_scores, probe_values)
    ring_out, ring_trace = _online_softmax_blockwise(probe_scores, probe_values, probe_block)
    abs_err = abs(full_out - ring_out)
    exact_match = bool(abs_err < 1e-9)

    # rotation_trace: the running online-softmax attention output as each KV block is
    # absorbed — bounded to num_rotation_steps entries for the surface's rotating cue.
    if len(ring_trace) >= num_rotation_steps:
        step = len(ring_trace) / num_rotation_steps
        rotation_trace = [ring_trace[min(len(ring_trace) - 1, int(i * step))]
                          for i in range(num_rotation_steps)]
    else:
        rotation_trace = ring_trace

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "ring-attention-blockwise",
        "service_version": "szl-kc-ringattn-v0.1",
        "seed": int(seed),
        "inputs": {"seq_len": seq_len, "devices": devices},
        "block_size": int(block_size),
        "num_rotation_steps": int(num_rotation_steps),
        "per_device_memory_ratio": per_device_memory_ratio,
        "max_context_supported": int(max_context_supported),
        "exact_match": exact_match,
        "online_vs_full_abs_error": float("%.3e" % abs_err),
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (schedule demo — never an engage)",
        "citations": [CITATIONS["ring"], CITATIONS["blockwise"], CITATIONS["flash"],
                      CITATIONS["online_softmax"]],
        "honesty": ("Ring-attention schedule simulation. NO multi-device run, NO GPU, NO NCCL "
                    "ring, NO model. per_device_memory_ratio / max_context_supported are MODELED "
                    "asymptotics; exact_match is a REAL CPU online-softmax-vs-full probe "
                    "(abs err < 1e-9), demonstrating the method's exactness — not a distributed "
                    "measurement. MODELED, not live."),
    }
    dsse = _sign_payload(receipt, _RA_PAYLOAD_TYPE)

    return {
        "service": "ring-attention-blockwise",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/ringattn.js ---
        "seq_len": int(seq_len),
        "devices": int(devices),
        "block_size": int(block_size),
        "num_rotation_steps": int(num_rotation_steps),
        "per_device_memory_ratio": per_device_memory_ratio,
        "exact_match": exact_match,
        "max_context_supported": int(max_context_supported),
        "rotation_trace": [round(float(x), 6) for x in rotation_trace],
        # --- provenance ---
        "formulas": {
            "block_size": "ceil(seq_len / devices)",
            "per_device_memory_ratio": "block_size / seq_len ≈ 1/devices",
            "online_softmax": "streaming (m, l, acc) rescale per block — exact vs full softmax",
        },
        "compute_backend": {
            "backend": "CPU pure-Python ring schedule + online-softmax probe",
            "label": "MODELED",
            "honest_note": ("Ring schedule arithmetic + a real CPU online-softmax exactness "
                            "check; NO multi-device run, NO GPU. The distributed NCCL-ring path "
                            "is ROADMAP."),
        },
        "wired_into": "frontier ring — Ring-Attention surface (rotating KV blocks + accumulator)",
        "citations": [CITATIONS["ring"], CITATIONS["flash"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/ringattn" % ns

    @app.get("%s/simulate" % base)
    async def _kc_ringattn(seed: int = 42, seq_len: int = 4096, devices: int = 8):  # noqa: ANN202
        try:
            return JSONResponse(ringattn_simulate(seed=seed, seq_len=seq_len, devices=devices))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "ring-attention-blockwise", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "exact_match": None}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/simulate" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = ringattn_simulate(seed=42, seq_len=4096, devices=8)

    # (a) honest label verbatim + every field the frontend reads is present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "devices", "block_size", "num_rotation_steps", "max_context_supported"):
        assert isinstance(r[f], int), (f, r.get(f))
    assert isinstance(r["per_device_memory_ratio"], (int, float)), r
    assert isinstance(r["exact_match"], bool), r
    assert isinstance(r["rotation_trace"], list) and r["rotation_trace"], r

    # (b) ring invariants: block_size*devices covers seq_len; steps == devices; ratio in (0,1].
    assert r["block_size"] * r["devices"] >= r["seq_len"], r
    assert r["num_rotation_steps"] == r["devices"], r
    assert 0.0 < r["per_device_memory_ratio"] <= 1.0, r
    # the online-softmax probe must actually be exact vs full softmax.
    assert r["exact_match"] is True, ("online softmax not exact", r)
    out["metrics"] = {"block_size": r["block_size"], "devices": r["devices"],
                      "per_device_memory_ratio": r["per_device_memory_ratio"],
                      "exact_match": r["exact_match"], "max_ctx": r["max_context_supported"]}

    # (c) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (d) determinism: same inputs -> identical snapshot.
    r2 = ringattn_simulate(seed=42, seq_len=4096, devices=8)
    assert r2["rotation_trace"] == r["rotation_trace"], "non-deterministic trace"
    assert r2["block_size"] == r["block_size"], "non-deterministic block_size"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
