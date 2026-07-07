# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_nsa.py — ADDITIVE NATIVE-SPARSE-ATTENTION organ for killinchu's frontier
surface (backs a11oy static/3d/surfaces/nsa.js).

NSA — Native Sparse Attention (Yuan, Gao, Dai, Luo, Zhao, Zhang, Xie et al.,
DeepSeek 2025, arXiv:2502.11089) — is a natively trainable sparse-attention mechanism
for long context. It combines a dynamic hierarchical strategy: (1) coarse-grained
token COMPRESSION (block summaries for global context), (2) fine-grained token
SELECTION (keep the top-n most relevant blocks), and (3) a SLIDING WINDOW for local
precision — three branches gated together. This cuts attention FLOPs from the dense
O(L^2) toward roughly O(L * (compressed + selected + window)) while keeping quality on
64k-length sequences.

This organ re-derives the sparse-attention FLOP/quality trade-off deterministically:
for a query at the end of a length-L sequence it forms the three NSA branches over a
seeded key/query field, measures the fraction of the dense attention mass they recover
(quality proxy) and the fraction of key-value reads they touch (the sparsity / FLOP
saving). The SZL addition is a J/token ENERGY RECEIPT tied to skipped KV reads.

Deterministic MODELED formulation (seeded, no live model, no GPU):
  * a query q and L keys k_i in R^d (seeded). Dense score s_i = <q,k_i>/sqrt(d);
    dense weights = softmax(s). Blocks of size B partition the L keys.
  * COMPRESSION branch: one summary key per block (mean); score blocks, keep all as a
    coarse global read (B-fold cheaper).
  * SELECTION branch: rank blocks by summary score, keep top-n blocks' full keys.
  * WINDOW branch: keep the last w keys (local precision).
  * recovered_mass = sum of dense softmax weight over the union of selected+window keys
    (how much of the true attention the sparse read captures).
  * kv_read_fraction = |touched keys + block summaries| / L (the sparsity).

  recovered_mass    = sum_{i in touched} softmax(s)_i
  kv_read_fraction  = (selected_keys + window_keys + n_blocks_summary) / L
  flop_reduction    = 1 - kv_read_fraction
  speedup           = 1 / kv_read_fraction        (idealized attention-read speedup)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic sparse-attention SIMULATION on synthetic keys/queries. NOT
    NSA running; NO live model, NO GPU, NO trained attention, NO real KV cache. q, keys,
    block size, top-n, and window are seeded inputs / MODELED references.
  * recovered_mass / sparsity are properties of the MODELED score field, honestly
    labeled — not a measured claim about a real transformer.
  * The J/token figure is a MODELED order-of-magnitude estimate, NOT a wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/nsa/simulate  — native-sparse-attention snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.nsa+json"):  # type: ignore
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

_NSA_PAYLOAD_TYPE = "application/vnd.szl.kc.nsa+json"
DOCTRINE_VERSION = "v11"

CITATIONS = {
    "nsa": ("Yuan, Gao, Dai, Luo, Zhao, Zhang, Xie, Wei, Wang, Xiao, Wang, Ruan, Zhang, Liang, "
            "Zeng (2025) Native Sparse Attention: Hardware-Aligned and Natively Trainable Sparse "
            "Attention (DeepSeek) — arXiv:2502.11089 — https://arxiv.org/abs/2502.11089"),
    "flashattn": ("Dao, Fu, Ermon, Rudra, Ré (2022) FlashAttention: Fast and Memory-Efficient "
                  "Exact Attention with IO-Awareness — arXiv:2205.14135 — "
                  "https://arxiv.org/abs/2205.14135"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | SPARSE_ATTENTION_SIM | NOT_LIVE | NO_MODEL | NO_KV_CACHE | NO_GPU"

# MODELED per-KV-read energy reference (order-of-magnitude only).
_J_PER_KV_READ = 2.0e-6


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


def _softmax(scores):
    m = max(scores)
    exps = [_math.exp(s - m) for s in scores]
    z = sum(exps)
    return [e / z for e in exps]


def nsa_simulate(seed: int = 42, seq_len: int = 512, dim: int = 16,
                 block: int = 16, top_n: int = 8, window: int = 32) -> dict:
    """Native-sparse-attention snapshot (MODELED).

    seq_len — context length L.
    dim     — key/query dimensionality d.
    block   — block size B for compression + selection branches.
    top_n   — number of blocks kept by the selection branch.
    window  — sliding-window size w (local branch).
    seed    — RNG seed; identical inputs give identical output (deterministic).
    """
    L = max(32, min(8192, int(seq_len)))
    d = max(2, min(64, int(dim)))
    B = max(2, min(max(2, L // 2), int(block)))
    rng = _LCG(int(seed) * 1_000_003 + L * 131 + d * 17 + B * 7)

    # query at the sequence end + L keys. Give recent keys a mild relevance boost and
    # plant a few relevant blocks far away (so selection must find them).
    q = [rng.signed() for _ in range(d)]
    keys = []
    for i in range(L):
        base = [rng.signed() for _ in range(d)]
        keys.append(base)
    # plant: make a handful of blocks strongly align with q so the true attention mass
    # concentrates on a small, recoverable set (as in real long-context retrieval).
    n_blocks = (L + B - 1) // B
    planted = set()
    for _ in range(min(4, n_blocks)):
        blk = rng.next_u32() % n_blocks
        planted.add(blk)
        for j in range(blk * B, min(L, (blk + 1) * B)):
            keys[j] = [q[c] * 2.6 + 0.08 * rng.signed() for c in range(d)]

    inv = 1.0 / _math.sqrt(d)
    dense_scores = [sum(q[c] * keys[i][c] for c in range(d)) * inv for i in range(L)]
    dense_w = _softmax(dense_scores)

    top_n = max(1, min(n_blocks, int(top_n)))
    w = max(1, min(L, int(window)))

    # COMPRESSION: block summaries (mean key) -> block scores.
    block_scores = []
    for b in range(n_blocks):
        lo, hi = b * B, min(L, (b + 1) * B)
        summ = [sum(keys[j][c] for j in range(lo, hi)) / (hi - lo) for c in range(d)]
        block_scores.append((sum(q[c] * summ[c] for c in range(d)) * inv, b))

    # SELECTION: top-n blocks by summary score -> their full keys.
    top_blocks = [b for _, b in sorted(block_scores, key=lambda x: x[0], reverse=True)[:top_n]]
    selected = set()
    for b in top_blocks:
        for j in range(b * B, min(L, (b + 1) * B)):
            selected.add(j)

    # WINDOW: last w keys.
    for j in range(max(0, L - w), L):
        selected.add(j)

    recovered_mass = sum(dense_w[j] for j in selected)
    selected_keys = len(selected)
    # KV reads touched: full keys in the union + one summary read per block (compression).
    kv_reads = selected_keys + n_blocks
    kv_read_fraction = kv_reads / L
    flop_reduction = max(0.0, 1.0 - kv_read_fraction)
    speedup = (1.0 / kv_read_fraction) if kv_read_fraction > 0 else 0.0

    # recall of planted (relevant) blocks by the selection branch.
    planted_hit = len(planted & set(top_blocks)) / len(planted) if planted else 1.0

    joules_dense = L * _J_PER_KV_READ
    joules_nsa = kv_reads * _J_PER_KV_READ
    joules_saved = joules_dense - joules_nsa
    energy_reduction_pct = (joules_saved / joules_dense) * 100.0 if joules_dense else 0.0

    energy_receipt = {
        "joules_per_kv_read_modeled": _J_PER_KV_READ,
        "joules_dense_modeled": round(float(joules_dense), 8),
        "joules_nsa_modeled": round(float(joules_nsa), 8),
        "joules_saved_modeled": round(float(joules_saved), 8),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "energy_note": ("MODELED per-KV-read energy — order-of-magnitude only, NOT a live wattmeter. "
                        "Each skipped key is one fewer attention read; this quantifies that as an "
                        "advisory input, not a certified number."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "native-sparse-attention",
        "service_version": "szl-kc-nsa-v0.1",
        "seed": int(seed),
        "inputs": {"seq_len": L, "dim": d, "block": B, "top_n": top_n, "window": w},
        "recovered_mass": round(float(recovered_mass), 6),
        "kv_read_fraction": round(float(kv_read_fraction), 6),
        "flop_reduction": round(float(flop_reduction), 6),
        "speedup": round(float(speedup), 6),
        "planted_block_recall": round(float(planted_hit), 6),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (sparse-attention advisory — never autonomous)",
        "citations": [CITATIONS["nsa"], CITATIONS["flashattn"]],
        "honesty": ("Deterministic sparse-attention simulation on synthetic keys/queries. NOT NSA "
                    "running; NO live model, NO GPU, NO trained attention, NO real KV cache. q, keys, "
                    "block size, top-n, window are seeded inputs / MODELED references. recovered_mass "
                    "and sparsity are properties of the MODELED score field, honestly labeled. "
                    "MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _NSA_PAYLOAD_TYPE)

    return {
        "service": "native-sparse-attention",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/nsa.js ---
        "seq_len": int(L),
        "dim": int(d),
        "block": int(B),
        "top_n": int(top_n),
        "window": int(w),
        "n_blocks": int(n_blocks),
        "selected_keys": int(selected_keys),
        "kv_reads": int(kv_reads),
        "recovered_mass": round(float(recovered_mass), 6),
        "kv_read_fraction": round(float(kv_read_fraction), 6),
        "flop_reduction": round(float(flop_reduction), 6),
        "speedup": round(float(speedup), 6),
        "planted_block_recall": round(float(planted_hit), 6),
        # --- SZL addition: the J/token KV-read energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "dense": "softmax(<q,k_i>/sqrt(d)) over all L keys",
            "branches": "compression (block summaries) + selection (top-n blocks) + sliding window",
            "recovered_mass": "sum of dense softmax weight over touched keys",
            "kv_read_fraction": "(selected + window + n_block_summaries) / L",
            "speedup": "1 / kv_read_fraction (idealized attention-read speedup)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python sparse-attention simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic sim; NO live model, NO GPU, NO trained attention, NO real "
                            "KV cache. The measured-on-a-real-transformer path is ROADMAP."),
        },
        "wired_into": "frontier ring — Native Sparse Attention surface + attention energy receipt",
        "citations": [CITATIONS["nsa"], CITATIONS["flashattn"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/nsa" % ns

    async def _kc_nsa(seed: int = 42, seq_len: int = 512, dim: int = 16,
                      block: int = 16, top_n: int = 8, window: int = 32):  # noqa: ANN202
        try:
            return JSONResponse(nsa_simulate(seed=seed, seq_len=seq_len, dim=dim,
                                             block=block, top_n=top_n, window=window))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "native-sparse-attention",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "recovered_mass": None, "speedup": None},
                                status_code=200)

    try:
        app.add_api_route("%s/simulate" % base, _kc_nsa, methods=["GET"])
    except Exception:  # pragma: no cover — Starlette Route fallback
        from starlette.routing import Route

        async def _kc_nsa_route(request):
            qp = request.query_params
            return await _kc_nsa(seed=int(qp.get("seed", 42)),
                                 seq_len=int(qp.get("seq_len", 512)),
                                 dim=int(qp.get("dim", 16)),
                                 block=int(qp.get("block", 16)),
                                 top_n=int(qp.get("top_n", 8)),
                                 window=int(qp.get("window", 32)))
        app.router.routes.append(Route("%s/simulate" % base, _kc_nsa_route, methods=["GET"]))

    return {"ok": True, "ns": ns, "routes": ["%s/simulate" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = nsa_simulate(seed=42, seq_len=512, dim=16, block=16, top_n=8, window=32)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("recovered_mass", "kv_read_fraction", "flop_reduction", "speedup"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    # sparsity invariant: NSA reads fewer than all keys => speedup > 1.
    assert 0.0 < r["kv_read_fraction"] < 1.0, r
    assert r["speedup"] > 1.0, r
    assert 0.0 < r["flop_reduction"] < 1.0, r
    # quality invariant: the sparse read recovers a large share of the dense mass.
    assert 0.0 < r["recovered_mass"] <= 1.0000001, r
    assert r["recovered_mass"] > 0.5, r
    assert r["kv_reads"] <= r["seq_len"] + r["n_blocks"], r
    out["metrics"] = {"recovered_mass": r["recovered_mass"],
                      "kv_read_fraction": r["kv_read_fraction"],
                      "flop_reduction": r["flop_reduction"],
                      "speedup": r["speedup"],
                      "planted_block_recall": r["planted_block_recall"]}

    er = r["energy_receipt"]
    assert er["joules_saved_modeled"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"energy_reduction_pct": er["energy_reduction_pct"]}

    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc

    r2 = nsa_simulate(seed=42, seq_len=512, dim=16, block=16, top_n=8, window=32)
    assert r2["recovered_mass"] == r["recovered_mass"], "non-deterministic recovered_mass"
    assert r2["kv_read_fraction"] == r["kv_read_fraction"], "non-deterministic sparsity"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("ALL OK")
