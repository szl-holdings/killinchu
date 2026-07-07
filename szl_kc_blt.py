# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_blt.py — ADDITIVE BYTE-LATENT-TRANSFORMER entropy-patching simulator for killinchu's
frontier surface (backs a11oy static/3d/surfaces/blt.js).

The Byte Latent Transformer (BLT; Pagnoni, Pasunuru, Rodriguez et al. 2024, arXiv:2412.09871)
is a byte-level LLM that dispenses with a fixed tokenizer. Instead of tokens, it segments a raw
byte stream into dynamically sized PATCHES whose boundaries are placed where a small byte-level
entropy model predicts the next byte with HIGH entropy (i.e. surprise). Predictable runs get long
patches (cheap); complex/high-entropy regions get short patches (more compute where the data is
hard). Because the expensive latent transformer runs once per PATCH rather than per byte, the
average patch length directly sets the compute budget: fewer, longer patches = fewer latent steps.

This module reproduces the BLT entropy-patching MECHANISM deterministically over a byte string,
using the paper's "approximate monotonic constraint" boundary rule: put a patch boundary at byte
position t when the next-byte entropy H(t) exceeds a global threshold theta (global-threshold
scheme in the paper). It reports the patch count, mean/percentile patch length, the byte->patch
compression ratio, and — the SZL addition — a J/byte ENERGY RECEIPT: bytes that would each cost a
per-byte latent step under a naive byte model, versus one latent step per patch under BLT.

Deterministic entropy model (seeded, no live model):
  * a small seeded LCG PRNG assigns each byte position a MODELED next-byte entropy in [0, Hmax],
    biased by a slowly varying "context predictability" walk so entropy is autocorrelated (real
    text alternates predictable runs with surprising spans) rather than white noise.
  * boundary rule (global-threshold, per the paper): open a new patch at position t whenever
    H(t) > theta. A minimum patch length is enforced so a run of high-entropy bytes cannot make
    length-1 patches forever (mirrors BLT's practical constraint).

  patches                 = number of segments produced
  mean_patch_len          = n_bytes / patches
  compression_ratio       = n_bytes / patches           (bytes folded into one latent step)
  latent_steps_saved      = n_bytes - patches           (naive per-byte vs one-per-patch)
  E_bytelevel             = n_bytes * e_latent           (naive byte transformer: 1 latent step/byte)
  E_blt                   = patches * e_latent + n_bytes * e_entropy   (patch latent + cheap scan)
  joules_per_byte_saved   = (E_bytelevel - E_blt) / n_bytes            (the ENERGY RECEIPT)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic entropy-patching SIMULATION. NOT a trained BLT running; NO live model,
    NO GPU, NO trained local/latent transformer, NO real byte-entropy network. The per-byte
    entropies are SEEDED MODELED values, NOT emitted by a real next-byte predictor.
  * The patching RULE (global entropy threshold with a minimum patch length) is the paper's actual
    mechanism, honestly reimplemented; the numbers it produces are properties of that rule over the
    seeded entropy trace, not a measurement of any real corpus or model.
  * The joules figures are MODELED order-of-magnitude estimates, NOT a live wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present in-Space;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/blt/entropy-patch  — byte-latent entropy-patching snapshot (MODELED)

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

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.blt+json"):  # type: ignore
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

_BLT_PAYLOAD_TYPE = "application/vnd.szl.kc.blt+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "blt": ("Pagnoni, Pasunuru, Rodriguez, Nguyen, Muller, Li, Zhou, Yu, Weston, Zettlemoyer, "
            "Ghosh, Lewis, Holtzman, Iyer (2024) Byte Latent Transformer: Patches Scale Better "
            "Than Tokens — arXiv:2412.09871 — https://arxiv.org/abs/2412.09871"),
}

# MODELED label — a deterministic entropy-patching simulation, never a live model.
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | ENTROPY_PATCH_SIM | NOT_LIVE | NO_MODEL | JOULES_ARE_MODELED"

# MODELED per-unit energy references (order-of-magnitude only; NOT a live wattmeter).
_E_LATENT = 1.0       # MODELED joules per latent-transformer step (the expensive unit)
_E_ENTROPY = 0.06     # MODELED joules per byte for the tiny entropy/boundary scan (cheap)
_HMAX = 4.0           # MODELED entropy ceiling (bits-like scale) for the seeded trace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entropy_trace(rng, n_bytes: int):
    """Deterministic autocorrelated per-byte next-byte entropy in [0, _HMAX].
    A slow random walk sets a local 'predictability' baseline; each byte's entropy jitters
    around it. Real text has predictable runs and surprising spans, not white noise."""
    trace = []
    baseline = _HMAX * 0.45
    for _ in range(n_bytes):
        # slow walk of the local baseline (autocorrelation)
        baseline += (rng.random() - 0.5) * 0.35
        baseline = max(0.15, min(_HMAX - 0.15, baseline))
        # per-byte jitter around the baseline
        h = baseline + (rng.random() - 0.5) * 0.9
        h = max(0.0, min(_HMAX, h))
        trace.append(h)
    return trace


def _patch(trace, theta: float, min_len: int):
    """Global-threshold entropy patching (per the BLT paper): open a new patch boundary at a
    position whose entropy exceeds theta, subject to a minimum patch length. Returns patch
    lengths."""
    lengths = []
    cur = 0
    for h in trace:
        cur += 1
        if h > theta and cur >= min_len:
            lengths.append(cur)
            cur = 0
    if cur > 0:
        lengths.append(cur)
    return lengths


def _percentile(sorted_vals, q: float):
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def blt_entropy_patch(seed: int = 42, n_bytes: int = 2048, theta: float = 2.4,
                      min_len: int = 2) -> dict:
    """Byte-latent entropy-patching snapshot (MODELED).

    n_bytes  — length of the seeded byte stream to patch.
    theta    — global entropy threshold; a byte above it opens a new patch boundary.
    min_len  — minimum patch length (mirrors BLT's practical constraint).
    seed     — RNG seed; identical inputs give identical output (deterministic).
    """
    n_bytes = max(16, min(1_000_000, int(n_bytes)))
    theta = max(0.1, min(_HMAX - 0.05, float(theta)))
    min_len = max(1, min(64, int(min_len)))
    rng = _random.Random(int(seed) * 1_000_003 + n_bytes * 131 + int(theta * 1000))

    trace = _entropy_trace(rng, n_bytes)
    lengths = _patch(trace, theta, min_len)
    patches = len(lengths)
    mean_patch_len = n_bytes / patches if patches else float(n_bytes)
    compression_ratio = n_bytes / patches if patches else float(n_bytes)
    latent_steps_saved = n_bytes - patches

    srt = sorted(lengths)
    p50 = _percentile(srt, 0.50)
    p95 = _percentile(srt, 0.95)
    max_len = float(srt[-1]) if srt else 0.0

    mean_entropy = sum(trace) / len(trace)
    high_entropy_frac = sum(1 for h in trace if h > theta) / len(trace)

    # ENERGY RECEIPT (MODELED joules — order-of-magnitude, NOT a live wattmeter).
    e_bytelevel = n_bytes * _E_LATENT                        # naive: one latent step per byte
    e_blt = patches * _E_LATENT + n_bytes * _E_ENTROPY       # one latent step per patch + scan
    joules_saved = e_bytelevel - e_blt
    joules_per_byte_saved = joules_saved / n_bytes if n_bytes else 0.0
    energy_reduction_pct = (joules_saved / e_bytelevel * 100.0) if e_bytelevel else 0.0

    patch_len_head = [int(x) for x in lengths[:16]]

    energy_receipt = {
        "joules_bytelevel_naive": round(float(e_bytelevel), 4),
        "joules_blt": round(float(e_blt), 4),
        "joules_saved": round(float(joules_saved), 4),
        "joules_per_byte_saved": round(float(joules_per_byte_saved), 6),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "e_latent_step_modeled": _E_LATENT,
        "e_entropy_scan_per_byte_modeled": _E_ENTROPY,
        "energy_note": ("MODELED joules — order-of-magnitude per-step/per-byte estimates, NOT a "
                        "live wattmeter. Each byte folded into a longer patch is one fewer latent "
                        "step; this quantifies that as an energy-receipt input to the llm-router."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "byte-latent-entropy-patching",
        "service_version": "szl-kc-blt-v0.1",
        "seed": int(seed),
        "inputs": {"n_bytes": n_bytes, "theta": theta, "min_len": min_len},
        "patches": int(patches),
        "mean_patch_len": round(float(mean_patch_len), 6),
        "compression_ratio": round(float(compression_ratio), 6),
        "latent_steps_saved": int(latent_steps_saved),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (entropy-patching advisory — never an autonomous action)",
        "citations": [CITATIONS["blt"]],
        "honesty": ("Deterministic global-threshold entropy-patching simulation over a seeded "
                    "byte-entropy trace. NOT a trained BLT running; NO live model, NO GPU, NO real "
                    "byte-entropy network. Per-byte entropies are seeded MODELED values; the "
                    "patching RULE is the paper's mechanism, honestly reimplemented. MODELED, not "
                    "live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _BLT_PAYLOAD_TYPE)

    return {
        "service": "byte-latent-entropy-patching",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/blt.js ---
        "n_bytes": int(n_bytes),
        "theta": round(float(theta), 4),
        "min_len": int(min_len),
        "patches": int(patches),
        "mean_patch_len": round(float(mean_patch_len), 6),
        "compression_ratio": round(float(compression_ratio), 6),
        "latent_steps_saved": int(latent_steps_saved),
        "patch_len_p50": round(float(p50), 4),
        "patch_len_p95": round(float(p95), 4),
        "patch_len_max": round(float(max_len), 4),
        "mean_byte_entropy": round(float(mean_entropy), 6),
        "high_entropy_fraction": round(float(high_entropy_frac), 6),
        "patch_len_head": patch_len_head,   # [int]
        # --- SZL addition: the J/byte-saved energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "mean_patch_len": "n_bytes / patches",
            "compression_ratio": "n_bytes / patches (bytes folded into one latent step)",
            "boundary_rule": "open new patch at byte t when H(t) > theta and cur_len >= min_len",
            "latent_steps_saved": "n_bytes - patches",
            "joules_per_byte_saved": "(E_bytelevel - E_blt) / n_bytes",
            "E_bytelevel": "n_bytes * e_latent",
            "E_blt": "patches * e_latent + n_bytes * e_entropy",
        },
        "compute_backend": {
            "backend": "CPU pure-Python entropy-patching simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic entropy-patching sim; NO live model, NO GPU, NO trained "
                            "byte-entropy network. The measured-on-a-real-BLT path is ROADMAP."),
        },
        "wired_into": "frontier ring — Byte-Latent-Transformer surface + llm-router energy receipt",
        "citations": [CITATIONS["blt"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/blt" % ns

    @app.get("%s/entropy-patch" % base)
    async def _kc_blt(seed: int = 42, n_bytes: int = 2048, theta: float = 2.4,
                      min_len: int = 2):  # noqa: ANN202
        try:
            return JSONResponse(blt_entropy_patch(seed=seed, n_bytes=n_bytes, theta=theta,
                                                  min_len=min_len))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "byte-latent-entropy-patching",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "patches": None, "compression_ratio": None},
                                status_code=200)

    # Starlette Route fallback (mirror specdec shape).
    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_blt_route(request):  # pragma: no cover — fallback path
            q = request.query_params
            try:
                return _SJSON(blt_entropy_patch(
                    seed=int(q.get("seed", 42)),
                    n_bytes=int(q.get("n_bytes", 2048)),
                    theta=float(q.get("theta", 2.4)),
                    min_len=int(q.get("min_len", 2))))
            except Exception as exc:
                return _SJSON({"service": "byte-latent-entropy-patching",
                               "label": MODELED_LABEL,
                               "error": "compute fail-open: %s" % (str(exc)[:160])},
                              status_code=200)

        if not any(getattr(r, "path", None) == "%s/entropy-patch" % base
                   for r in getattr(app.router, "routes", [])):
            app.router.routes.append(Route("%s/entropy-patch" % base, _kc_blt_route,
                                           methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": ["%s/entropy-patch" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = blt_entropy_patch(seed=42, n_bytes=2048, theta=2.4, min_len=2)

    # (a) honest label verbatim + every field the frontend reads present & typed.
    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("n_bytes", "patches", "min_len", "latent_steps_saved"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("theta", "mean_patch_len", "compression_ratio", "mean_byte_entropy",
              "high_entropy_fraction"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["patch_len_head"], list) and r["patch_len_head"], r
    assert all(isinstance(x, int) for x in r["patch_len_head"]), r["patch_len_head"]

    # (b) surface-specific invariants: patches in (0, n_bytes]; compression >= 1; savings >= 0;
    #     every patch length >= min_len except possibly the final tail patch.
    assert 0 < r["patches"] <= r["n_bytes"], r
    assert r["compression_ratio"] >= 1.0, r["compression_ratio"]
    assert r["latent_steps_saved"] == r["n_bytes"] - r["patches"], r
    assert r["latent_steps_saved"] >= 0, r
    assert 0.0 <= r["high_entropy_fraction"] <= 1.0, r
    assert all(x >= r["min_len"] for x in r["patch_len_head"][:-1]) or len(r["patch_len_head"]) == 1, r
    out["metrics"] = {"patches": r["patches"], "mean_patch_len": r["mean_patch_len"],
                      "compression_ratio": r["compression_ratio"],
                      "latent_steps_saved": r["latent_steps_saved"]}

    # (c) energy receipt: positive joules saved + positive J/byte saved on this profile.
    er = r["energy_receipt"]
    assert er["joules_saved"] > 0, er
    assert er["joules_per_byte_saved"] > 0, er
    assert 0.0 < er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"joules_saved": er["joules_saved"],
                             "joules_per_byte_saved": er["joules_per_byte_saved"],
                             "energy_reduction_pct": er["energy_reduction_pct"]}

    # (d) signed receipt present + honest label embedded; signature never fabricated.
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (e) determinism: same inputs -> identical patch profile.
    r2 = blt_entropy_patch(seed=42, n_bytes=2048, theta=2.4, min_len=2)
    assert r2["patch_len_head"] == r["patch_len_head"], "non-deterministic"
    assert r2["compression_ratio"] == r["compression_ratio"], "non-deterministic ratio"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    assert res["ok"] is True
    print("ALL OK")
