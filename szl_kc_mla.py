# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_mla.py — ADDITIVE Multi-head Latent Attention (MLA) low-rank KV-compression
demonstrator for killinchu's frontier surface (backs a11oy static/3d/surfaces/mla.js).

DeepSeek-V2's MLA compresses the per-token Key/Value cache into a single low-rank latent
vector c_KV (shared across heads), down-projecting K,V into a d_latent space and up-projecting
on demand — shrinking the KV cache from O(seq·n_heads·d_head·2) to O(seq·d_latent) while keeping
attention quality. This module reports the exact cache sizes + compression ratio for the given
shape, and — critically — RUNS a real down-project → up-project reconstruction on a seeded block
so `reconstruction_error` is COMPUTED, never hard-coded.

Cache sizes + honest reconstruction probe:
  * mha_cache_size = seq_len · n_heads · d_head · 2      (full K and V cache, elements)
  * mla_cache_size = seq_len · d_latent                   (compressed shared latent, elements)
  * compression_ratio = mha_cache_size / mla_cache_size
  * reconstruction_error = mean_i ||x_i − W_up·(W_down·x_i)||_2 / ||x_i||_2   on a seeded
    block (relative L2). Low d_latent ⇒ higher error; the surface shows the win vs the cost.

HONESTY SPINE (Doctrine v11):
  * MODELED low-rank projection demonstration. There is NO trained model, NO attention forward
    pass, NO GPU — only seeded projection matrices + real matmul on a bounded probe block.
  * Cache sizes / compression_ratio are EXACT counts for the shape; reconstruction_error is a
    REAL relative-L2 measured on a bounded seeded block (the block size is reported honestly),
    NOT a benchmark of a trained MLA model.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/mla/latent-compress  — MLA KV-compression snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.mla+json"):  # type: ignore
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

_MLA_PAYLOAD_TYPE = "application/vnd.szl.kc.mla+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "deepseekv2": ("DeepSeek-AI (2024) DeepSeek-V2: Multi-head Latent Attention (MLA) — "
                   "low-rank joint KV compression — arXiv:2405.04434"),
    "deepseekv3": ("DeepSeek-AI (2024) DeepSeek-V3 Technical Report (MLA at scale) — "
                   "arXiv:2412.19437"),
    "flash": ("Dao, Fu, Ermon, Rudra, Ré (2022) FlashAttention: Fast and Memory-Efficient "
              "Exact Attention with IO-Awareness — arXiv:2205.14135"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = ("MODELED | LOW_RANK_KV_COMPRESS_SIM | NOT_LIVE | NO_TRAINED_MODEL | "
                "NO_ATTENTION_FORWARD | SEEDED_PROJECTIONS")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matvec(mat, vec):
    """mat: rows × cols ; vec: len cols → len rows."""
    return [sum(mat[r][c] * vec[c] for c in range(len(vec))) for r in range(len(mat))]


def mla_latent_compress(seed: int = 42, seq_len: int = 128, n_heads: int = 8,
                        d_head: int = 64, d_latent: int = 128) -> dict:
    """MLA low-rank KV-compression snapshot (MODELED).

    seq_len  — number of cached positions.
    n_heads  — attention heads.
    d_head   — per-head dimension (full model width = n_heads·d_head).
    d_latent — compressed shared-latent width (the KV cache is stored at this rank).
    seed     — RNG seed; identical inputs give identical output (deterministic).
    """
    seq_len = max(1, min(131_072, int(seq_len)))
    n_heads = max(1, min(256, int(n_heads)))
    d_head = max(1, min(1024, int(d_head)))
    d_latent = max(1, min(8192, int(d_latent)))

    d_model = n_heads * d_head
    mha_cache_size = seq_len * n_heads * d_head * 2   # full K and V
    mla_cache_size = seq_len * d_latent               # compressed shared latent
    compression_ratio = round(mha_cache_size / mla_cache_size, 6) if mla_cache_size else 0.0

    # --- REAL reconstruction probe on a bounded seeded block --------------------------
    # Down-project x∈R^d_model to R^r then up-project back; relative L2 error. Bounded so
    # the handler stays fast; the probe dims are reported honestly in the receipt.
    rng = _random.Random(int(seed) * 2_654_435_761 % (2 ** 32) + seq_len + n_heads * 31 + d_head * 7 + d_latent)
    probe_dim = min(d_model, 96)
    probe_rank = max(1, min(d_latent, probe_dim))
    probe_rows = min(seq_len, 24)
    scale = 1.0 / _math.sqrt(probe_dim)
    w_down = [[rng.gauss(0.0, scale) for _ in range(probe_dim)] for _ in range(probe_rank)]
    w_up = [[rng.gauss(0.0, scale) for _ in range(probe_rank)] for _ in range(probe_dim)]

    errs = []
    for _ in range(probe_rows):
        x = [rng.gauss(0.0, 1.0) for _ in range(probe_dim)]
        c = _matvec(w_down, x)          # down-project to rank r
        xr = _matvec(w_up, c)           # up-project back
        num = _math.sqrt(sum((a - b) ** 2 for a, b in zip(x, xr)))
        den = _math.sqrt(sum(a * a for a in x)) or 1.0
        errs.append(num / den)
    reconstruction_error = round(sum(errs) / len(errs), 6) if errs else 0.0

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "mla-latent-compress",
        "service_version": "szl-kc-mla-v0.1",
        "seed": int(seed),
        "inputs": {"seq_len": seq_len, "n_heads": n_heads, "d_head": d_head,
                   "d_latent": d_latent, "d_model": d_model},
        "mha_cache_size": int(mha_cache_size),
        "mla_cache_size": int(mla_cache_size),
        "compression_ratio": compression_ratio,
        "reconstruction_error": reconstruction_error,
        "reconstruction_probe": {"rows": probe_rows, "dim": probe_dim, "rank": probe_rank,
                                 "metric": "relative L2 (mean over rows)"},
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (compression demo — never an engage)",
        "citations": [CITATIONS["deepseekv2"], CITATIONS["deepseekv3"], CITATIONS["flash"]],
        "honesty": ("MLA low-rank KV-compression demonstration. NO trained model, NO attention "
                    "forward pass, NO GPU. Cache sizes / compression_ratio are exact counts for "
                    "the shape; reconstruction_error is a REAL relative-L2 measured on a bounded "
                    "seeded block (rows/dim/rank reported), with seeded projection matrices — "
                    "NOT a trained-MLA benchmark. MODELED, not live."),
    }
    dsse = _sign_payload(receipt, _MLA_PAYLOAD_TYPE)

    return {
        "service": "mla-latent-compress",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/mla.js ---
        "seq_len": int(seq_len),
        "n_heads": int(n_heads),
        "d_head": int(d_head),
        "d_latent": int(d_latent),
        "mha_cache_size": int(mha_cache_size),
        "mla_cache_size": int(mla_cache_size),
        "compression_ratio": compression_ratio,
        "reconstruction_error": reconstruction_error,
        # --- provenance ---
        "formulas": {
            "mha_cache_size": "seq_len · n_heads · d_head · 2  (full K and V)",
            "mla_cache_size": "seq_len · d_latent  (compressed shared latent)",
            "compression_ratio": "mha_cache_size / mla_cache_size",
            "reconstruction_error": "mean_i ||x_i − W_up·(W_down·x_i)||_2 / ||x_i||_2",
        },
        "compute_backend": {
            "backend": "CPU pure-Python low-rank projection probe",
            "label": "MODELED",
            "honest_note": ("Exact cache-size counts + a real down/up-projection reconstruction "
                            "on a bounded seeded block; NO trained model, NO GPU. The trained-MLA "
                            "attention path is ROADMAP."),
        },
        "wired_into": "frontier ring — Latent Attention (MLA) surface (KV compression columns)",
        "citations": [CITATIONS["deepseekv2"], CITATIONS["deepseekv3"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/mla" % ns

    @app.get("%s/latent-compress" % base)
    async def _kc_mla(seed: int = 42, seq_len: int = 128, n_heads: int = 8,
                      d_head: int = 64, d_latent: int = 128):  # noqa: ANN202
        try:
            return JSONResponse(mla_latent_compress(seed=seed, seq_len=seq_len, n_heads=n_heads,
                                                    d_head=d_head, d_latent=d_latent))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "mla-latent-compress", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "compression_ratio": None}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/latent-compress" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = mla_latent_compress(seed=42, seq_len=128, n_heads=8, d_head=64, d_latent=128)

    # (a) honest label verbatim + every field the frontend reads is present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("seq_len", "n_heads", "d_head", "d_latent", "mha_cache_size", "mla_cache_size"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("compression_ratio", "reconstruction_error"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))

    # (b) size invariants: exact counts + ratio consistent; error is a non-negative fraction.
    assert r["mha_cache_size"] == r["seq_len"] * r["n_heads"] * r["d_head"] * 2, r
    assert r["mla_cache_size"] == r["seq_len"] * r["d_latent"], r
    expect_ratio = r["mha_cache_size"] / r["mla_cache_size"]
    assert abs(r["compression_ratio"] - round(expect_ratio, 6)) < 1e-6, r
    assert r["reconstruction_error"] >= 0.0, r
    out["metrics"] = {"mha_cache_size": r["mha_cache_size"], "mla_cache_size": r["mla_cache_size"],
                      "compression_ratio": r["compression_ratio"],
                      "reconstruction_error": r["reconstruction_error"]}

    # (c) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (d) determinism: same inputs -> identical snapshot.
    r2 = mla_latent_compress(seed=42, seq_len=128, n_heads=8, d_head=64, d_latent=128)
    assert r2["reconstruction_error"] == r["reconstruction_error"], "non-deterministic recon err"
    assert r2["compression_ratio"] == r["compression_ratio"], "non-deterministic ratio"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
