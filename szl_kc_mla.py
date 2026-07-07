# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_mla.py — ADDITIVE MULTI-HEAD LATENT ATTENTION (MLA) KV-cache-compression simulator
for killinchu's frontier surface (backs a11oy static/3d/surfaces/mla.js).

Multi-head Latent Attention (MLA) is DeepSeek-V2's core efficiency mechanism (DeepSeek-AI
2024, "DeepSeek-V2: A Strong, Economical, and Efficient Mixture-of-Experts Language Model",
arXiv:2405.04434). Instead of caching full per-head Key/Value tensors, MLA down-projects the
hidden state into a small shared LATENT vector c^{KV} that is the only thing cached; per-head
K and V are reconstructed on the fly by up-projection. The paper reports the KV cache is
reduced by 93.3% and max generation throughput rises to 5.76x vs. DeepSeek 67B. DeepSeek-V3
(arXiv:2412.19437) carries MLA forward. This organ re-derives the low-rank compress/reconstruct
step: down-project a modeled per-token key/value to a latent of dim d_c, up-project back, and
report the cache-byte reduction, compression ratio, and reconstruction fidelity.

Deterministic MODELED low-rank KV compression (seeded, no live model):
  * per token: hidden h in R^{d}. Standard MHA caches K,V of size 2 * n_head * d_head per token.
  * MLA caches only a latent c = W_down h in R^{d_c} (d_c << n_head*d_head), plus the decoupled
    RoPE key of dim d_rope. Reconstruct kv_hat = W_up c.
  * cache_bytes_mha = tokens * 2 * n_head * d_head * bytes ; cache_bytes_mla =
    tokens * (d_c + d_rope) * bytes. compression_ratio = mha/mla.
  * reconstruction_mse = mean((kv - kv_hat)^2) over a seeded batch (a modeled fidelity check;
    a trained W_down/W_up would drive this lower — here they are seeded low-rank factors).

  c = W_down h                          (down-projection to latent, dim d_c)
  kv_hat = W_up c                       (up-projection / reconstruction)
  cache_per_token_mla = d_c + d_rope    (elements cached per token)
  compression_ratio = (2*n_head*d_head) / (d_c + d_rope)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic low-rank compress/reconstruct SIMULATION. NOT DeepSeek-V2/V3 running;
    NO live model, NO GPU, NO trained projections. Hidden states and W_down/W_up are SEEDED
    inputs, NOT learned weights.
  * Byte counts are element-count * a MODELED bytes/element (e.g. 2 for bf16); they are an
    order-of-magnitude cache-footprint estimate, NOT a live memory profiler.
  * The 93.3% / 5.76x figures are the PAPER's reported numbers, cited — not measured here.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/mla/latent-compress  — MLA KV-cache-compression snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | LOWRANK_KV_SIM | NOT_LIVE | NO_MODEL | PROJECTIONS_ARE_SEEDED"

CITATIONS = {
    "deepseekv2": ("DeepSeek-AI et al. (2024) DeepSeek-V2: A Strong, Economical, and Efficient "
                   "Mixture-of-Experts Language Model (Multi-head Latent Attention) — "
                   "https://arxiv.org/abs/2405.04434"),
    "deepseekv3": ("DeepSeek-AI et al. (2024) DeepSeek-V3 Technical Report (MLA carried "
                   "forward) — https://arxiv.org/abs/2412.19437"),
}

# Paper-reported figures (cited, NOT measured here).
_PAPER_KV_REDUCTION_PCT = 93.3
_PAPER_THROUGHPUT_X = 5.76
_BYTES_PER_ELEM = 2  # MODELED bf16 bytes/element for the footprint estimate


class _LCG:
    """Small deterministic LCG PRNG (pure stdlib; no numpy, no stdlib random)."""

    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) & 0xFFFFFFFFFFFFFFFF) or 0x9E3779B97F4A7C15

    def _next(self) -> int:
        self._s = (6364136223846793005 * self._s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self._s

    def random(self) -> float:
        return (self._next() >> 11) / float(1 << 53)

    def normalish(self) -> float:
        return (self.random() + self.random() + self.random() + self.random()) - 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mla_latent_compress(seed: int = 42, n_head: int = 32, d_head: int = 128,
                        d_c: int = 512, d_rope: int = 64, tokens: int = 4096,
                        batch: int = 32) -> dict:
    """MLA KV-cache-compression snapshot (MODELED).

    n_head/d_head — attention head count / per-head dim (defines full-MHA KV size).
    d_c           — MLA latent (compressed KV) dimension.
    d_rope        — decoupled RoPE key dimension carried alongside the latent.
    tokens        — context length (for the cache-footprint estimate).
    batch         — number of seeded key/value vectors for the fidelity check.
    seed          — PRNG seed; deterministic.
    """
    nh = max(1, min(256, int(n_head)))
    dh = max(1, min(1024, int(d_head)))
    d_kv = 2 * nh * dh                       # full-MHA KV elements per token (K + V)
    d_c = max(1, min(d_kv, int(d_c)))
    d_rope = max(0, min(d_kv, int(d_rope)))
    tokens = max(1, min(1_000_000, int(tokens)))
    B = max(1, min(1024, int(batch)))
    rng = _LCG(int(seed) * 2_654_435_761 + nh * 131 + dh * 17 + d_c * 7 + d_rope * 3)

    # Reduce the fidelity check to a tractable modeled dimension d (<= d_kv) to keep pure-Python
    # matmuls cheap while preserving the low-rank compress/reconstruct property.
    d = min(d_kv, 128)
    dc_eff = max(1, min(d, d_c))  # effective latent dim used for the modeled reconstruction

    # seeded down/up low-rank projection factors (NOT trained): W_down d->dc_eff, W_up dc_eff->d
    W_down = [[rng.normalish() / _math.sqrt(d) for _ in range(d)] for _ in range(dc_eff)]
    W_up = [[rng.normalish() / _math.sqrt(dc_eff) for _ in range(dc_eff)] for _ in range(d)]

    total_mse = 0.0
    total_energy = 0.0
    for t in range(B):
        kv = [rng.normalish() for _ in range(d)]
        # latent c = W_down kv  (dim dc_eff)
        c = [sum(W_down[i][j] * kv[j] for j in range(d)) for i in range(dc_eff)]
        # reconstruct kv_hat = W_up c
        kv_hat = [sum(W_up[i][j] * c[j] for j in range(dc_eff)) for i in range(d)]
        total_mse += sum((kv[j] - kv_hat[j]) ** 2 for j in range(d)) / d
        total_energy += sum(v * v for v in kv) / d
        if t == 0:
            latent_preview = [round(v, 6) for v in c[:16]]

    recon_mse = total_mse / B
    mean_energy = (total_energy / B) or 1.0
    fvu = recon_mse / mean_energy

    # cache footprint (MODELED bytes = elements * bytes/element)
    cache_per_token_mha = d_kv
    cache_per_token_mla = d_c + d_rope
    compression_ratio = cache_per_token_mha / cache_per_token_mla
    bytes_mha = tokens * cache_per_token_mha * _BYTES_PER_ELEM
    bytes_mla = tokens * cache_per_token_mla * _BYTES_PER_ELEM
    kv_reduction_pct = (1.0 - bytes_mla / bytes_mha) * 100.0 if bytes_mha else 0.0

    return {
        "service": "mla-kv-latent-compress",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/mla.js ---
        "n_head": int(nh),
        "d_head": int(dh),
        "d_c": int(d_c),
        "d_rope": int(d_rope),
        "tokens": int(tokens),
        "cache_per_token_mha_elems": int(cache_per_token_mha),
        "cache_per_token_mla_elems": int(cache_per_token_mla),
        "compression_ratio": round(float(compression_ratio), 6),
        "kv_cache_bytes_mha": int(bytes_mha),
        "kv_cache_bytes_mla": int(bytes_mla),
        "kv_reduction_pct": round(float(kv_reduction_pct), 4),
        "reconstruction_mse": round(float(recon_mse), 6),
        "fraction_variance_unexplained": round(float(fvu), 6),
        "latent_preview": latent_preview,   # [float] first components of a modeled latent c
        "paper_reported": {
            "kv_reduction_pct": _PAPER_KV_REDUCTION_PCT,
            "throughput_speedup_x": _PAPER_THROUGHPUT_X,
            "note": ("Paper-reported DeepSeek-V2 figures (cited, NOT measured here): 93.3% KV "
                     "cache reduction and 5.76x max generation throughput vs. DeepSeek 67B."),
        },
        "formulas": {
            "latent": "c = W_down h  (dim d_c)",
            "reconstruction": "kv_hat = W_up c",
            "cache_per_token_mla": "d_c + d_rope",
            "compression_ratio": "(2*n_head*d_head) / (d_c + d_rope)",
            "kv_reduction_pct": "(1 - bytes_mla/bytes_mha) * 100",
        },
        "compute_backend": {
            "backend": "CPU pure-Python low-rank compress/reconstruct simulation (seeded LCG)",
            "label": "MODELED",
            "honest_note": ("Deterministic seeded low-rank down/up projection; NO DeepSeek-V2/V3, "
                            "NO live model, NO GPU, NO trained projections. Byte counts use a "
                            "MODELED bytes/element. The measured-on-a-real-model path is ROADMAP."),
        },
        "honest_note": ("MODELED MLA KV-cache low-rank compression. NOT DeepSeek-V2/V3 running; "
                        "NO live model, NO GPU, NO trained projections. Hidden states and "
                        "projections are seeded; byte counts are order-of-magnitude estimates. "
                        "93.3%/5.76x are the paper's reported figures, cited not measured. "
                        "Advisory to Λ (Conjecture 1); adds nothing to the locked-8."),
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (compression snapshot advisory — never an autonomous action)",
        "citations": {"deepseekv2": CITATIONS["deepseekv2"], "deepseekv3": CITATIONS["deepseekv3"]},
        "wired_into": "frontier ring — MLA surface (latent KV-cache compression)",
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive). Mirrors szl_kc_specdec.register exactly.
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/mla" % ns
    path = "%s/latent-compress" % base

    @app.get(path)
    async def _kc_mla(seed: int = 42, n_head: int = 32, d_head: int = 128,
                      d_c: int = 512, d_rope: int = 64, tokens: int = 4096,
                      batch: int = 32):  # noqa: ANN202
        try:
            return JSONResponse(mla_latent_compress(seed=seed, n_head=n_head, d_head=d_head,
                                                    d_c=d_c, d_rope=d_rope, tokens=tokens,
                                                    batch=batch))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "mla-kv-latent-compress",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "compression_ratio": None, "kv_reduction_pct": None},
                                status_code=200)

    try:
        from starlette.routing import Route
        from starlette.responses import JSONResponse as _SJSON

        async def _kc_mla_route(request):  # pragma: no cover
            q = request.query_params
            return _SJSON(mla_latent_compress(seed=int(q.get("seed", 42)),
                                              n_head=int(q.get("n_head", 32)),
                                              d_head=int(q.get("d_head", 128)),
                                              d_c=int(q.get("d_c", 512)),
                                              d_rope=int(q.get("d_rope", 64)),
                                              tokens=int(q.get("tokens", 4096)),
                                              batch=int(q.get("batch", 32))))

        app.router.routes.append(Route(path, _kc_mla_route, methods=["GET"]))
    except Exception:  # pragma: no cover
        pass

    return {"ok": True, "ns": ns, "routes": [path]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = mla_latent_compress(seed=42)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("n_head", "d_head", "d_c", "d_rope", "tokens", "cache_per_token_mha_elems",
              "cache_per_token_mla_elems", "kv_cache_bytes_mha", "kv_cache_bytes_mla"):
        assert isinstance(r[f], int), (f, r.get(f))
    for f in ("compression_ratio", "kv_reduction_pct", "reconstruction_mse"):
        assert isinstance(r[f], (int, float)), (f, r.get(f))
    assert isinstance(r["latent_preview"], list) and r["latent_preview"], r

    # invariants: MLA cache strictly smaller than MHA; compression > 1; reduction in (0,100).
    assert r["cache_per_token_mla_elems"] < r["cache_per_token_mha_elems"], r
    assert r["compression_ratio"] > 1.0, r
    assert 0.0 < r["kv_reduction_pct"] < 100.0, r
    assert r["kv_cache_bytes_mla"] < r["kv_cache_bytes_mha"], r
    assert r["reconstruction_mse"] > 0.0, r
    # paper figures preserved verbatim as the cited references
    assert r["paper_reported"]["kv_reduction_pct"] == 93.3, r["paper_reported"]
    assert r["paper_reported"]["throughput_speedup_x"] == 5.76, r["paper_reported"]
    out["metrics"] = {"compression_ratio": r["compression_ratio"],
                      "kv_reduction_pct": r["kv_reduction_pct"],
                      "reconstruction_mse": r["reconstruction_mse"],
                      "cache_per_token_mla_elems": r["cache_per_token_mla_elems"]}

    assert "arxiv.org/abs/2405.04434" in r["citations"]["deepseekv2"], r["citations"]
    out["citations_ok"] = True

    # determinism
    r2 = mla_latent_compress(seed=42)
    assert r2["latent_preview"] == r["latent_preview"], "non-deterministic latent"
    assert r2["reconstruction_mse"] == r["reconstruction_mse"], "non-deterministic mse"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
    print("ALL OK")
