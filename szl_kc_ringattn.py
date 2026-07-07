# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_ringattn.py — ADDITIVE RING-ATTENTION distribution simulator for killinchu's frontier
surface (backs a11oy static/3d/surfaces/ringattn.js).

Ring Attention with Blockwise Transformers (Liu, Zaharia, Abbeel 2023, arXiv:2310.01889) lets a
Transformer handle sequences up to device-count times longer than a single device allows. The
sequence is split into blocks, one block of query/key/value per device arranged in a RING. Each
device computes blockwise attention over its local query against the KV block it currently holds,
then passes its KV block to the next device in the ring while receiving the previous device's KV
block. After N-1 such rotations every query has attended to every KV block — exact attention, no
approximation — and crucially the KV-block COMMUNICATION is overlapped with the blockwise attention
COMPUTATION, so the ring hop is (near-)free when compute per block dominates comm per block.

This module reproduces the Ring Attention SCHEDULE and its overlap economics deterministically. For
a sequence of length S split across N devices (block = S/N per device), it walks the N-step ring:
each step does one block-block attention (compute time t_comp) while shipping one KV block
(comm time t_comm); the step cost is max(t_comp, t_comp is hidden under? ) — modeled as
max(t_comp, t_comm) when overlapped. It reports the max context reachable, the per-device memory
(vs. a single device holding the whole sequence), the overlap efficiency, and — the SZL addition —
a J/token ENERGY RECEIPT from distributing the KV memory instead of replicating the full sequence.

Deterministic ring model (seeded, no live model, no real kernels):
  * block_len = ceil(S / N); per device holds one block of KV (memory ~ block_len).
  * ring has N steps; each step: compute one block-block attention (t_comp) overlapped with one
    KV-block send/recv (t_comm). overlapped step cost = max(t_comp, t_comm).
  * t_comp scales with block_len^~ (blockwise attention over local block); t_comm scales with
    block_len (one KV block moved). A small seeded jitter models real link/compute variance.

  block_len            = ceil(S / N)
  max_context          = N * block_len_single           (device_count times longer, per the paper)
  mem_per_device_ratio = block_len / S                  (fraction of full-sequence KV per device)
  overlap_efficiency   = sum(t_comp) / sum(max(t_comp, t_comm))   (1.0 == comm fully hidden)
  E_replicated         = N * S * e_kv_slot              (each device holds the whole sequence)
  E_ring               = N * block_len * e_kv_slot      (each device holds one block)
  joules_per_token_saved = (E_replicated - E_ring) / S   (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic ring-schedule SIMULATION. NOT Ring Attention running on real devices; NO
    live model, NO GPU, NO NCCL/collective, NO real attention kernels. block times and link speeds
    are SEEDED MODELED values, NOT measured.
  * The RING SCHEDULE (N blocks rotating, exact attention after N-1 hops, comm overlapped with
    compute) is the paper's actual mechanism, honestly reimplemented; the numbers are properties of
    that schedule under the seeded costs, not a wall-clock measurement on a real cluster.
  * "exact attention" is TRUE by construction (every query sees every KV block after the ring
    completes) — a property of the ALGORITHM, honestly labeled, not a measured accuracy claim.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/ringattn/simulate  — ring-attention distribution snapshot (MODELED)

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

_RING_PAYLOAD_TYPE = "application/vnd.szl.kc.ringattn+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "ringattn": ("Liu, Zaharia, Abbeel (2023) Ring Attention with Blockwise Transformers for "
                 "Near-Infinite Context — arXiv:2310.01889 — https://arxiv.org/abs/2310.01889"),
}

# MODELED label — a deterministic ring-schedule simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | RING_SCHEDULE_SIM | NOT_LIVE | NO_MODEL | NO_COLLECTIVE | JOULES_ARE_MODELED"

# MODELED per-unit references (order-of-magnitude only; NOT measured).
_E_KV_SLOT = 1.0        # MODELED joules to hold one KV slot on a device for the pass
_T_COMP_UNIT = 1.0      # MODELED compute time per KV-slot of blockwise attention
_T_COMM_UNIT = 0.7      # MODELED comm time per KV-slot to ship a block to the next ring device


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ringattn_simulate(seed: int = 42, seq_len: int = 32768, devices: int = 8,
                      single_device_cap: int = 4096) -> dict:
    """Ring-attention distribution snapshot (MODELED).

    seq_len            — total sequence length distributed across the ring.
    devices            — N, ring size (device count).
    single_device_cap  — max context a single device could hold (for the max-context comparison).
    seed               — RNG seed; identical inputs give identical output (deterministic).
    """
    seq_len = max(8, min(100_000_000, int(seq_len)))
    devices = max(1, min(4096, int(devices)))
    single_device_cap = max(1, min(seq_len, int(single_device_cap)))
    rng = _random.Random(int(seed) * 1_000_003 + seq_len % 1_000_003 + devices * 131)

    block_len = _math.ceil(seq_len / devices)
    max_context = devices * single_device_cap   # device_count times longer, per the paper
    mem_per_device_ratio = block_len / seq_len

    # walk the ring: N steps, each overlaps one block-block attention with one KV-block hop.
    sum_comp = 0.0
    sum_overlapped = 0.0
    step_costs = []
    for _step in range(devices):
        jitter_c = 1.0 + (rng.random() - 0.5) * 0.06
        jitter_m = 1.0 + (rng.random() - 0.5) * 0.06
        t_comp = _T_COMP_UNIT * block_len * jitter_c
        t_comm = _T_COMM_UNIT * block_len * jitter_m
        overlapped = max(t_comp, t_comm)   # comm hidden under compute when compute dominates
        sum_comp += t_comp
        sum_overlapped += overlapped
        if len(step_costs) < 16:
            step_costs.append(round(float(overlapped), 4))

    overlap_efficiency = (sum_comp / sum_overlapped) if sum_overlapped else 0.0
    exact_attention = True  # every query attends to every KV block after N-1 rotations

    # ENERGY / MEMORY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    e_replicated = devices * seq_len * _E_KV_SLOT     # each device holds the whole sequence
    e_ring = devices * block_len * _E_KV_SLOT         # each device holds one block
    joules_saved = e_replicated - e_ring
    joules_per_token_saved = joules_saved / seq_len if seq_len else 0.0
    energy_reduction_pct = (joules_saved / e_replicated * 100.0) if e_replicated else 0.0

    energy_receipt = {
        "joules_replicated": round(float(e_replicated), 4),
        "joules_ring": round(float(e_ring), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_token_saved": round(float(joules_per_token_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_kv_slot_modeled": _E_KV_SLOT,
        "energy_note": ("MODELED joules — order-of-magnitude per-slot estimates, NOT a live "
                        "wattmeter. Each device holding one block instead of the whole sequence is "
                        "the memory/energy win; quantified as a receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "ring-attention-distribution",
        "service_version": "szl-kc-ringattn-v0.1",
        "seed": int(seed),
        "inputs": {"seq_len": seq_len, "devices": devices, "single_device_cap": single_device_cap},
        "block_len": int(block_len),
        "ring_steps": int(devices),
        "max_context": int(max_context),
        "mem_per_device_ratio": round(float(mem_per_device_ratio), 6),
        "overlap_efficiency": round(float(overlap_efficiency), 6),
        "exact_attention": bool(exact_attention),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (distribution advisory — never an autonomous action)",
        "citations": [CITATIONS["ringattn"]],
        "honesty": ("Deterministic ring-schedule simulation. NOT Ring Attention running on real "
                    "devices; NO live model, NO GPU, NO collective, NO real kernels. Block/link "
                    "costs are seeded MODELED values; the RING SCHEDULE is the paper's mechanism, "
                    "honestly reimplemented. 'exact attention' is a property of the ALGORITHM. "
                    "MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _RING_PAYLOAD_TYPE)

    return {
        "service": "ring-attention-distribution",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/ringattn.js ---
        "seq_len": int(seq_len),
        "devices": int(devices),
        "single_device_cap": int(single_device_cap),
        "block_len": int(block_len),
        "ring_steps": int(devices),
        "max_context": int(max_context),
        "mem_per_device_ratio": round(float(mem_per_device_ratio), 6),
        "overlap_efficiency": round(float(overlap_efficiency), 6),
        "exact_attention": bool(exact_attention),
        "step_costs": step_costs,   # [float]
        # --- SZL addition: the J/token-saved energy/memory receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "block_len": "ceil(seq_len / devices)",
            "ring_steps": "devices (N-1 rotations complete exact attention, plus local block)",
            "max_context": "devices * single_device_cap (device_count times longer)",
            "mem_per_device_ratio": "block_len / seq_len",
            "overlap_efficiency": "sum(t_comp) / sum(max(t_comp, t_comm))",
            "joules_per_token_saved": "(E_replicated - E_ring) / seq_len",
            "E_replicated": "devices * seq_len * e_kv_slot",
            "E_ring": "devices * block_len * e_kv_slot",
        },
        "compute_backend": {
            "backend": "CPU pure-Python ring-schedule simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic ring-schedule sim; NO live model, NO GPU, NO collective, "
                            "NO real kernels. The measured-on-a-real-cluster path is ROADMAP."),
        },
        "wired_into": "frontier ring — Ring-Attention surface + llm-router energy receipt",
        "citations": [CITATIONS["ringattn"]],
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
    async def _kc_ringattn(seed: int = 42, seq_len: int = 32768, devices: int = 8,
                           single_device_cap: int = 4096):  # noqa: ANN202
        try:
            return JSONResponse(ringattn_simulate(seed=seed, seq_len=seq_len, devices=devices,
                                                  single_device_cap=single_device_cap))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "ring-attention-distribution",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "max_context": None, "overlap_efficiency": None},
                                status_code=200)

    # Starlette Route fallback.
    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_ringattn_route(request):  # pragma: no cover — fallback path
            q = request.query_params
            try:
                return _SJSON(ringattn_simulate(
                    seed=int(q.get("seed", 42)),
                    seq_len=int(q.get("seq_len", 32768)),
                    devices=int(q.get("devices", 8)),
                    single_device_cap=int(q.get("single_device_cap", 4096))))
            except Exception as exc:
                return _SJSON({"service": "ring-attention-distribution",
                               "label": MODELED_LABEL,
                               "error": "compute fail-open: %s" % (str(exc)[:160])},
                              status_code=200)

        if not any(getattr(r, "path", None) == "%s/simulate" % base
                   for r in getattr(app.router, "routes", [])):
            app.router.routes.append(Route("%s/simulate" % base, _kc_ringattn_route,
                                           methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": ["%s/simulate" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = ringattn_simulate(seed=42, seq_len=32768, devices=8, single_device_cap=4096)

    # (a) honest label verbatim + every field the frontend reads present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "devices", "single_device_cap", "block_len", "ring_steps", "max_context"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("mem_per_device_ratio", "overlap_efficiency"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["exact_attention"], bool), r
    assert isinstance(r["step_costs"], list) and r["step_costs"], r
    assert all(isinstance(x, (int, float)) for x in r["step_costs"]), r["step_costs"]

    # (b) surface-specific invariants: block covers the sequence; ring rotates N steps; max context
    #     is device_count times longer; per-device memory is a small fraction of the full sequence;
    #     comm is overlapped (efficiency in (0,1]); attention is exact.
    assert r["block_len"] * r["devices"] >= r["seq_len"], r
    assert r["ring_steps"] == r["devices"], r
    assert r["max_context"] == r["devices"] * r["single_device_cap"], r
    assert r["max_context"] > r["single_device_cap"], r  # ring extends reachable context
    assert 0.0 < r["mem_per_device_ratio"] <= 1.0, r
    assert r["mem_per_device_ratio"] < 1.0, r  # distributing beats a single device holding all
    assert 0.0 < r["overlap_efficiency"] <= 1.0, r["overlap_efficiency"]
    assert r["exact_attention"] is True, r
    out["metrics"] = {"block_len": r["block_len"], "max_context": r["max_context"],
                      "mem_per_device_ratio": r["mem_per_device_ratio"],
                      "overlap_efficiency": r["overlap_efficiency"]}

    # (c) energy/memory receipt: positive joules saved on this profile.
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
    r2 = ringattn_simulate(seed=42, seq_len=32768, devices=8, single_device_cap=4096)
    assert r2["step_costs"] == r["step_costs"], "non-deterministic"
    assert r2["overlap_efficiency"] == r["overlap_efficiency"], "non-deterministic overlap"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    assert res["ok"] is True
    print("ALL OK")
