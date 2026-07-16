# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_ternary.py — ADDITIVE TERNARY (BitNet b1.58) QUANTIZATION organ for killinchu's
frontier surface (backs a11oy static/3d/surfaces/ternary.js).

BitNet b1.58 (Ma, Wang, Ma, Wang, Wang, Huang, Dong, Wang, Xue, Wei 2024, "The Era of
1-bit LLMs", arXiv:2402.17764) quantizes every weight to the TERNARY set {-1, 0, +1}
via absmean quantization: scale the weight matrix by its mean absolute value gamma,
round each scaled weight to the nearest ternary value, and clamp to [-1,1]. Each weight
then carries log2(3) ~ 1.58 bits, and the costly FP16 multiply-accumulate becomes
integer add/subtract/skip — matching FP16 perplexity/accuracy at the same size while
cutting memory, latency, and energy. BitNet b1.58 2B4T (arXiv:2504.12285) later shipped
this at the 2B / 4T-token scale as an open native-1-bit model.

This organ re-derives absmean ternarization deterministically over a seeded weight
tensor and measures the ternary reconstruction error, the {-1,0,+1} distribution, the
bits/param and memory compression, and the MAC->add substitution rate. The SZL addition
is a J/param ENERGY RECEIPT for the ternary-vs-FP16 arithmetic + footprint.

Deterministic MODELED formulation (seeded, no live model, no real weights):
  * synthesize n_params weights w_i from a seeded pseudo-normal distribution
    (a pre-trained tensor).
  * ABSMEAN ternarization (BitNet b1.58):
        gamma = mean(|w|) + eps
        q_i   = clamp(round(w_i / gamma), -1, +1)   in {-1, 0, +1}
        dequant  wq_i = gamma * q_i
  * reconstruction error rmse = sqrt(mean((w - wq)^2)) ; cosine similarity of w vs wq.
  * sparsity = fraction q_i == 0 (these become SKIPPED MACs — pure structural saving).
  * bits/param = log2(3) ~ 1.58 ; memory compression vs FP16 = 16 / 1.58.

  gamma            = mean(|w|)                     (absmean scale)
  q_i              = clamp(round(w_i/gamma), -1, 1) (ternary)
  rmse             = sqrt(mean((w - gamma*q)^2))    (reconstruction error)
  cosine_sim       = <w, wq> / (||w|| ||wq||)       (direction preserved)
  compression_x    = 16 / 1.58                      (footprint)
  mac_to_add_rate  = fraction of MACs replaced by add/sub/skip (= 1, all of them)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic absmean-ternarization SIMULATION on synthetic weights. NOT
    BitNet running; NO live model, NO GPU, NO trained weights, NO real inference. The
    weight distribution and eps are SEEDED inputs / MODELED references, not measured.
  * The "matches FP16" claim belongs to the BitNet papers on real models; THIS organ
    only measures reconstruction fidelity of the MODELED tensor, honestly labeled — it
    makes NO accuracy claim about a real LLM.
  * bits/param and the J/param figures are MODELED order-of-magnitude estimates, NOT a
    live wattmeter or a real quantized checkpoint.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/ternary/quantize  — BitNet b1.58 ternary-quant snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.ternary+json"):  # type: ignore
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

_TERNARY_PAYLOAD_TYPE = "application/vnd.szl.kc.ternary+json"
DOCTRINE_VERSION = "v11"

CITATIONS = {
    "bitnet158": ("Ma, Wang, Ma, Wang, Wang, Huang, Dong, Wang, Xue, Wei (2024) The Era of 1-bit "
                  "LLMs: All Large Language Models are in 1.58 Bits (BitNet b1.58) — "
                  "arXiv:2402.17764 — https://arxiv.org/abs/2402.17764"),
    "bitnet2b4t": ("Ma, Wang, Huang, Zhang, Hu, Song, Xia, Wei (2025) BitNet b1.58 2B4T Technical "
                   "Report — arXiv:2504.12285 — https://arxiv.org/abs/2504.12285"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | ABSMEAN_TERNARY_SIM | NOT_LIVE | NO_MODEL | NO_WEIGHTS | BITS_ARE_MODELED"

_BITS_FP16 = 16.0
_BITS_TERNARY = 1.58                 # log2(3), the b1.58 ternary information content
_J_PER_FP16_MAC = 1.0                 # MODELED joules per FP16 multiply-accumulate (unit)
_J_PER_TERNARY_ADD = 0.10             # MODELED joules per ternary add/sub (skip == 0)


class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (int(seed) ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def normalish(self) -> float:
        return (self.uniform() + self.uniform() + self.uniform()
                + self.uniform() + self.uniform() + self.uniform()) - 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ternary_quantize(seed: int = 42, n_params: int = 4096, eps: float = 1e-5) -> dict:
    """BitNet b1.58 ternary-quantization snapshot (MODELED).

    n_params — synthetic weights in the modeled tensor.
    eps      — numerical epsilon added to the absmean scale gamma.
    seed     — RNG seed; identical inputs give identical output (deterministic).
    """
    n = max(64, min(500000, int(n_params)))
    eps = max(1e-9, min(1e-1, float(eps)))
    rng = _LCG(int(seed) * 1_000_003 + n * 131 + int(eps * 1e9) % 100003)

    # 1) synthesize a pre-trained weight tensor (pseudo-normal).
    w = [rng.normalish() for _ in range(n)]

    # 2) ABSMEAN ternarization (BitNet b1.58).
    gamma = sum(abs(v) for v in w) / n + eps
    neg = zero = pos = 0
    sq_err = 0.0
    dot = 0.0
    norm_w = 0.0
    norm_wq = 0.0
    for v in w:
        r = v / gamma
        # round-half-away-from-zero then clamp to {-1,0,+1}.
        if r >= 0.5:
            q = 1
        elif r <= -0.5:
            q = -1
        else:
            q = 0
        if q == 1:
            pos += 1
        elif q == -1:
            neg += 1
        else:
            zero += 1
        wq = gamma * q
        d = v - wq
        sq_err += d * d
        dot += v * wq
        norm_w += v * v
        norm_wq += wq * wq

    rmse = _math.sqrt(sq_err / n)
    denom = _math.sqrt(norm_w) * _math.sqrt(norm_wq)
    cosine_sim = (dot / denom) if denom > 0 else 0.0
    sparsity = zero / n

    # bits/param + footprint compression (MODELED).
    bits_per_param = _BITS_TERNARY
    compression_x = _BITS_FP16 / _BITS_TERNARY

    # arithmetic energy: every FP16 MAC becomes a ternary add/sub, and zeros are skipped.
    nonzero_frac = 1.0 - sparsity
    e_fp16 = n * _J_PER_FP16_MAC
    e_ternary = n * nonzero_frac * _J_PER_TERNARY_ADD   # skipped zeros cost ~0
    joules_saved = e_fp16 - e_ternary
    joules_saved_per_param = joules_saved / n
    energy_reduction_pct = (joules_saved / e_fp16) * 100.0 if e_fp16 else 0.0
    mac_to_add_rate = 1.0   # ALL FP16 MACs are replaced by add/sub/skip in ternary

    energy_receipt = {
        "bits_per_param_fp16": _BITS_FP16,
        "bits_per_param_ternary": bits_per_param,
        "compression_x": round(float(compression_x), 4),
        "j_per_fp16_mac_modeled": _J_PER_FP16_MAC,
        "j_per_ternary_add_modeled": _J_PER_TERNARY_ADD,
        "mac_to_add_rate": mac_to_add_rate,
        "joules_fp16_modeled": round(float(e_fp16), 4),
        "joules_ternary_modeled": round(float(e_ternary), 4),
        "joules_saved_per_param_modeled": round(float(joules_saved_per_param), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "energy_note": ("MODELED footprint + arithmetic energy — ternary carries log2(3)=1.58 "
                        "bits/param vs 16 for FP16, and every FP16 MAC becomes an add/sub (zeros "
                        "skipped). Order-of-magnitude only, NOT a live wattmeter or real checkpoint."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "bitnet-b158-ternary-quant",
        "service_version": "szl-kc-ternary-v0.1",
        "seed": int(seed),
        "inputs": {"n_params": n, "eps": eps},
        "gamma": round(float(gamma), 6),
        "rmse": round(float(rmse), 6),
        "cosine_sim": round(float(cosine_sim), 6),
        "sparsity": round(float(sparsity), 6),
        "bits_per_param": bits_per_param,
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (quant advisory — never an autonomous action)",
        "citations": [CITATIONS["bitnet158"], CITATIONS["bitnet2b4t"]],
        "honesty": ("Deterministic absmean-ternarization simulation on synthetic weights. NOT BitNet "
                    "running; NO live model, NO GPU, NO trained weights, NO real inference. Weight "
                    "distribution and eps are seeded inputs / MODELED references. The 'matches FP16' "
                    "claim belongs to the BitNet papers on real models; this organ only measures "
                    "reconstruction fidelity of the MODELED tensor, making NO accuracy claim about a "
                    "real LLM. MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _TERNARY_PAYLOAD_TYPE)

    return {
        "service": "bitnet-b158-ternary-quant",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/ternary.js ---
        "n_params": int(n),
        "eps": float(eps),
        "gamma": round(float(gamma), 6),
        "rmse": round(float(rmse), 6),
        "cosine_sim": round(float(cosine_sim), 6),
        "sparsity": round(float(sparsity), 6),
        "bits_per_param": bits_per_param,
        "compression_x": round(float(compression_x), 4),
        "ternary_histogram": {"neg": int(neg), "zero": int(zero), "pos": int(pos)},
        "mac_to_add_rate": mac_to_add_rate,
        # --- SZL addition: the bits/param + J/param energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "gamma": "mean(|w|) + eps  (absmean scale)",
            "ternary": "q = clamp(round(w/gamma), -1, +1)  in {-1,0,+1}",
            "dequant": "wq = gamma * q",
            "rmse": "sqrt(mean((w - wq)^2))",
            "cosine_sim": "<w, wq> / (||w|| ||wq||)",
            "compression_x": "16 / 1.58  (FP16 bits / ternary bits)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python absmean-ternarization simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic sim; NO live model, NO GPU, NO trained weights, NO real "
                            "inference. The measured-on-a-real-checkpoint path is ROADMAP."),
        },
        "wired_into": "frontier ring — BitNet b1.58 ternary surface + quant energy receipt",
        "citations": [CITATIONS["bitnet158"], CITATIONS["bitnet2b4t"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/ternary" % ns

    async def _kc_ternary(seed: int = 42, n_params: int = 4096, eps: float = 1e-5):  # noqa: ANN202
        try:
            return JSONResponse(ternary_quantize(seed=seed, n_params=n_params, eps=eps))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "bitnet-b158-ternary-quant",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "rmse": None, "compression_x": None},
                                status_code=200)

    try:
        app.add_api_route("%s/quantize" % base, _kc_ternary, methods=["GET"])
    except Exception:  # pragma: no cover — Starlette Route fallback
        from starlette.routing import Route

        async def _kc_ternary_route(request):
            qp = request.query_params
            return await _kc_ternary(seed=int(qp.get("seed", 42)),
                                     n_params=int(qp.get("n_params", 4096)),
                                     eps=float(qp.get("eps", 1e-5)))
        app.router.routes.append(Route("%s/quantize" % base, _kc_ternary_route, methods=["GET"]))

    return {"ok": True, "ns": ns, "routes": ["%s/quantize" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = ternary_quantize(seed=42, n_params=4096, eps=1e-5)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("gamma", "rmse", "cosine_sim", "sparsity", "compression_x"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    # ternary invariant: histogram sums to n_params; only 3 levels used.
    h = r["ternary_histogram"]
    assert h["neg"] + h["zero"] + h["pos"] == r["n_params"], r
    assert 0.0 <= r["sparsity"] <= 1.0, r
    # fidelity invariant: dequant preserves direction (positive cosine similarity).
    assert 0.0 < r["cosine_sim"] <= 1.0000001, r
    assert r["cosine_sim"] > 0.8, r
    assert r["rmse"] >= 0.0, r
    assert r["bits_per_param"] == _BITS_TERNARY, r
    out["metrics"] = {"gamma": r["gamma"], "rmse": r["rmse"], "cosine_sim": r["cosine_sim"],
                      "sparsity": r["sparsity"], "compression_x": r["compression_x"]}

    er = r["energy_receipt"]
    assert er["compression_x"] > 1.0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert er["mac_to_add_rate"] == 1.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"compression_x": er["compression_x"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc

    r2 = ternary_quantize(seed=42, n_params=4096, eps=1e-5)
    assert r2["rmse"] == r["rmse"], "non-deterministic rmse"
    assert r2["ternary_histogram"] == r["ternary_histogram"], "non-deterministic histogram"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("ALL OK")
