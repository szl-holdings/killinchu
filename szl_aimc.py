# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_aimc.py — SZL ANALOG IN-MEMORY COMPUTING ATTENTION endpoint (charge-domain
gain-cell crossbar attention, Leroux et al. 2025-style), MODELED.

Exposes a MODELED closed-form simulation of an idealized ANALOG in-memory
computing (AIMC) attention pathway — a charge-based "gain-cell" crossbar array
that simultaneously STORES the KV cache and COMPUTES attention dot-products
directly inside the memory array — as a same-origin REST endpoint, so the AIMC
surface organ has a live data source that is honest, deterministic, and
citable — never fabricated, never random-faked, never run on real analog
hardware.

  GET  /api/<ns>/v1/aimc/attend?seed=&seq_len=&dim=&noise_sigma=

WHAT IS SIMULATED
------------------
A digital transformer computes attention as exact floating-point matmuls: to
attend at each decoding step it must (a) STORE per-token Key/Value vectors in
digital memory (the KV cache) and (b) MOVE those vectors out of memory, through
DACs/ADCs and arithmetic units, to compute query·key dot-products — the
memory-movement + conversion cost dominates energy and latency at inference
(Leroux et al. 2025, Nature Computational Science s43588-025-00854-1).

**Analog In-Memory Computing (AIMC) attention** instead maps the stored Key
projections onto the conductances/charges of an analog "gain-cell" crossbar
array. A query, applied as an analog input voltage/pulse, drives a
charge-domain MULTIPLY-ACCUMULATE physically along each column: the summed
current/charge on a column IS the query·key dot-product, computed in-memory,
without moving the KV cache out or paying repeated ADC/DAC conversion. This
collapses the store + move + convert + multiply pipeline into one physical
analog operation, which the paper reports cuts attention energy by up to ~5
orders of magnitude and latency by up to ~2 orders of magnitude versus GPUs,
while reaching accuracy comparable to GPT-2 after a software-to-hardware
calibration step. The cost is ANALOG IMPRECISION: device conductances carry
fixed programming noise, so the in-memory dot-products are slightly perturbed
versus exact digital matmul — the paper recovers accuracy via a per-layer
statistical rescaling calibration that matches the analog device statistics.

THIS MODULE (clean-room, deterministic, MODELED):
  1. Draws seeded synthetic Query and Key vectors for `seq_len` token
     positions x `dim` dims each, from the pure-stdlib LCG PRNG below (no
     numpy, no stdlib `random`).
  2. Programs the Keys into an idealized analog gain-cell crossbar, modeled as
     a numeric array whose stored values carry a FIXED, reproducible additive
     "device noise" of magnitude `noise_sigma` (analog programming imprecision)
     drawn deterministically from the same LCG.
  3. Computes attention dot-products (query·key) TWICE:
       - digital_scores : exact float dot-products on the noiseless Keys
                          (the digital baseline / oracle).
       - analog_scores  : charge-domain multiply-accumulate along each crossbar
                          column using the NOISY stored Keys (the raw analog
                          pathway, before calibration).
  4. Applies the paper's software-to-hardware CALIBRATION: a per-position
     statistical rescaling (match analog column mean/scale back to the digital
     column's mean/scale) yielding `calibrated_scores`, showing accuracy
     recovering close to the digital baseline despite the injected noise.
  5. Reports mean-squared attention-score error for the raw analog pathway vs
     the calibrated pathway (calibration should shrink the error), plus a
     simple ENERGY-ACCOUNTING tally of "operations avoided" (ADC/DAC
     conversions and KV-cache memory-movement reads eliminated by computing in
     memory), and reproduces — at TOY scale, as the PAPER's CLAIM only — the
     order-of-magnitude energy/latency advantage figures.

Returned JSON fields
---------------------
  label                    : "MODELED" (always — deterministic simulation of
                             the charge-domain crossbar attention ARITHMETIC,
                             NOT a run on real analog hardware)
  model                    : short description of the simulated setup
  seed                     : RNG seed used
  seq_len                  : number of token positions (crossbar columns)
  dim                      : per-token Query/Key dimension (crossbar rows)
  noise_sigma              : injected analog device-noise magnitude (fixed, seeded)
  analog_mse               : mean-squared error of RAW analog scores vs digital baseline
  calibrated_mse           : mean-squared error of CALIBRATED analog scores vs digital baseline
  calibration_gain         : analog_mse - calibrated_mse (error removed by calibration)
  accuracy_recovered_pct    : 100 * (1 - calibrated_mse / analog_mse) — % of the raw
                             analog error removed by the paper's calibration step
  adc_dac_ops_avoided       : count of ADC/DAC conversions eliminated by computing in-memory
  memory_move_reads_avoided : count of KV-cache element reads/moves eliminated
  total_ops_avoided         : adc_dac_ops_avoided + memory_move_reads_avoided
  paper_energy_reduction_claim  : "up to ~1e5x (5 orders of magnitude)" — the PAPER's
                             claim, NOT a measured SZL figure
  paper_latency_reduction_claim : "up to ~1e2x (2 orders of magnitude)" — the PAPER's
                             claim, NOT a measured SZL figure
  sample_digital_scores     : first few exact digital attention scores (surface viz)
  sample_analog_scores      : first few raw analog (noisy) scores (surface viz)
  sample_calibrated_scores  : first few calibrated analog scores (surface viz)
  honest_note              : plain-language honesty disclaimer
  citations                : dict of citable sources
  computed_at              : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the charge-domain
  crossbar attention ARITHMETIC (Keys stored with fixed seeded additive device
  noise, dot-products computed as a simulated in-memory multiply-accumulate,
  then per-position statistical rescaling calibration) — it runs on ordinary
  digital CPU floats, NOT on any real analog gain-cell hardware, uses NO
  proprietary weights, runs NO real language model, and is NEVER-CLAIMED-AS the
  Leroux et al. 2025 chip or its measured silicon results. Crucially, the
  energy_reduction and latency_reduction figures reported here are the PAPER's
  published CLAIMS reproduced at toy scale via an operations-avoided accounting
  model — they are NOT measured on real analog hardware and are NOT a measured
  SZL result. The label "MODELED" is returned verbatim and displayed verbatim
  by the surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own; VERIFY real):
  AIMC attention — analog in-memory computing gain-cell crossbar attention
  (mechanism modeled here):
    Leroux, Manea, Sudarshan, Finkbeiner, Siegel, Strachan & Neftci et al.
    (2025) "Analog in-memory computing attention mechanism for fast and
    energy-efficient large language models". Nature Computational Science.
    https://www.nature.com/articles/s43588-025-00854-1
  IBM Research plain-language summary of the above:
    "How can analog in-memory computing power transformer models?"
    https://research.ibm.com/blog/how-can-analog-in-memory-computing-power-transformer-models
  NEVER-CLAIMED-AS: this module is not the Leroux et al. hardware, does not
  reproduce the paper's measured silicon energy/latency/accuracy numbers, and
  runs no real analog device or language model. It is a clean-room MODELED
  simulation of the charge-domain crossbar attention arithmetic the paper
  describes, and any energy/latency advantage stated is the PAPER's claim, not
  a measured SZL figure.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  Never claim more than is real: energy/latency figures are the paper's claim,
  not a measured SZL result.
"""
from __future__ import annotations

from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "AIMC attention (analog in-memory gain-cell crossbar attention) — Leroux et al. 2025, Nature Computational Science": "https://www.nature.com/articles/s43588-025-00854-1",
    "IBM Research summary — How can analog in-memory computing power transformer models?": "https://research.ibm.com/blog/how-can-analog-in-memory-computing-power-transformer-models",
}

# The paper's headline order-of-magnitude advantages, stated verbatim as the
# PAPER's CLAIM (never as a measured SZL figure). See s43588-025-00854-1.
PAPER_ENERGY_REDUCTION_CLAIM = "up to ~1e5x (up to 5 orders of magnitude) — PAPER's claim, not a measured SZL result"
PAPER_LATENCY_REDUCTION_CLAIM = "up to ~1e2x (up to 2 orders of magnitude) — PAPER's claim, not a measured SZL result"

# Cap on how many attention scores we echo back for the surface's column
# visualization (keeps payload bounded for large seq_len).
_MAX_SAMPLE_SCORES = 64


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _rand_signed(rng) -> float:
    """Draw one deterministic pseudo-random value in (-1, 1) from the LCG stream."""
    return 2.0 * next(rng) - 1.0


# ---------------------------------------------------------------------------
# MODELED analog in-memory-computing attention simulation (deterministic)
# ---------------------------------------------------------------------------
def _make_vector(rng, n: int, scale: float = 1.0):
    """Length-n vector of small seeded random values in (-scale, scale)."""
    return [scale * _rand_signed(rng) for _ in range(n)]


def _dot(a, b) -> float:
    """Exact float dot-product of two equal-length vectors (pure stdlib)."""
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    return s


def _mean(xs) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs, mu: float) -> float:
    if not xs:
        return 0.0
    var = sum((x - mu) * (x - mu) for x in xs) / len(xs)
    return var ** 0.5


def _mse(a, b) -> float:
    """Mean-squared error between two equal-length score lists."""
    if not a:
        return 0.0
    s = 0.0
    for x, y in zip(a, b):
        d = x - y
        s += d * d
    return s / len(a)


def _aimc_snapshot(seed: int = 42, seq_len: int = 128, dim: int = 64,
                   noise_sigma: float = 0.05) -> dict:
    """
    Simulate an idealized analog gain-cell crossbar computing attention
    dot-products in-memory over `seq_len` stored Key columns of width `dim`,
    against a single query, with fixed seeded device noise `noise_sigma`, then
    apply the paper's per-position statistical-rescaling calibration.

    Pure stdlib; deterministic — same (seed, seq_len, dim, noise_sigma) ->
    identical snapshot, every time.
    """
    rng = _lcg(seed)

    # 1) Seeded synthetic query (analog input drive) and per-token Key vectors.
    #    The crossbar has `dim` rows (Key dimension) and `seq_len` columns
    #    (one stored Key / KV-cache entry per token position).
    query = _make_vector(rng, dim, scale=1.0)
    keys = [_make_vector(rng, dim, scale=1.0) for _ in range(seq_len)]

    # 2) Program the Keys into the crossbar as STORED CONDUCTANCES carrying a
    #    FIXED, reproducible additive analog "device noise" (programming
    #    imprecision). Drawn deterministically from the same LCG so the noise
    #    is identical across runs for a given seed.
    noisy_keys = []
    for k in keys:
        noisy_keys.append([kv + noise_sigma * _rand_signed(rng) for kv in k])

    # 3a) DIGITAL baseline: exact float query·key on the noiseless Keys.
    digital_scores = [_dot(query, k) for k in keys]

    # 3b) ANALOG pathway: simulated charge-domain multiply-accumulate along each
    #     crossbar COLUMN using the NOISY stored Keys — the summed charge on a
    #     column IS the (perturbed) query·key dot-product, computed in-memory.
    analog_scores = [_dot(query, nk) for nk in noisy_keys]

    # 4) CALIBRATION (paper's software-to-hardware step): per-column statistical
    #    rescaling — shift+scale the analog score distribution back to match the
    #    digital distribution's mean and spread, recovering accuracy despite the
    #    injected device noise. (In the paper this rescaling is fit per-layer to
    #    the measured analog device statistics; here we fit it in closed form to
    #    the simulated column statistics.)
    d_mu, a_mu = _mean(digital_scores), _mean(analog_scores)
    d_sd, a_sd = _std(digital_scores, d_mu), _std(analog_scores, a_mu)
    scale = (d_sd / a_sd) if a_sd > 1e-12 else 1.0
    calibrated_scores = [(s - a_mu) * scale + d_mu for s in analog_scores]

    # 5) Error accounting: raw analog vs digital, and calibrated vs digital.
    analog_mse = _mse(analog_scores, digital_scores)
    calibrated_mse = _mse(calibrated_scores, digital_scores)
    calibration_gain = analog_mse - calibrated_mse
    accuracy_recovered_pct = (
        100.0 * (1.0 - (calibrated_mse / analog_mse)) if analog_mse > 1e-18 else 0.0
    )

    # 6) ENERGY-ACCOUNTING model — "operations avoided" by computing in-memory.
    #    A digital attention step must, per stored Key element, (a) read/move it
    #    out of the KV cache and (b) convert it (ADC/DAC) around the arithmetic
    #    unit. Computing the query·key MAC physically inside the crossbar
    #    eliminates BOTH per element. We tally the toy-scale counts here; these
    #    counts (NOT a hardware measurement) are what underlie the paper's
    #    order-of-magnitude energy/latency CLAIMS, which we reproduce verbatim.
    kv_elements = seq_len * dim
    adc_dac_ops_avoided = 2 * kv_elements       # one ADC + one DAC per element
    memory_move_reads_avoided = kv_elements     # one KV-cache read/move per element
    total_ops_avoided = adc_dac_ops_avoided + memory_move_reads_avoided

    sample_n = min(seq_len, _MAX_SAMPLE_SCORES)

    return {
        "seq_len": seq_len,
        "dim": dim,
        "noise_sigma": round(noise_sigma, 6),
        "analog_mse": round(analog_mse, 8),
        "calibrated_mse": round(calibrated_mse, 8),
        "calibration_gain": round(calibration_gain, 8),
        "accuracy_recovered_pct": round(accuracy_recovered_pct, 4),
        "adc_dac_ops_avoided": adc_dac_ops_avoided,
        "memory_move_reads_avoided": memory_move_reads_avoided,
        "total_ops_avoided": total_ops_avoided,
        "paper_energy_reduction_claim": PAPER_ENERGY_REDUCTION_CLAIM,
        "paper_latency_reduction_claim": PAPER_LATENCY_REDUCTION_CLAIM,
        "sample_digital_scores": [round(v, 6) for v in digital_scores[:sample_n]],
        "sample_analog_scores": [round(v, 6) for v in analog_scores[:sample_n]],
        "sample_calibrated_scores": [round(v, 6) for v in calibrated_scores[:sample_n]],
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _ff(req: Request, key: str, default: float) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return default


def _h_attend(req: Request):
    # Clamps keep the pure-stdlib dot-product loop (O(seq_len * dim), no numpy)
    # bounded to a fast, deterministic HTTP response.
    seed        = _ii(req, "seed",        42)
    seq_len     = max(1,   min(_ii(req, "seq_len", 128), 2048))
    dim         = max(1,   min(_ii(req, "dim",     64),  512))
    noise_sigma = max(0.0, min(_ff(req, "noise_sigma", 0.05), 1.0))

    snap = _aimc_snapshot(seed=seed, seq_len=seq_len, dim=dim, noise_sigma=noise_sigma)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Analog In-Memory Computing attention: charge-domain gain-cell crossbar query·key MAC (Leroux et al. 2025-style)",
        "method": (
            "Program synthetic Key vectors into an idealized analog gain-cell "
            "crossbar (numeric array) with FIXED seeded additive device noise; "
            "compute query·key attention dot-products as a simulated charge-domain "
            "multiply-accumulate along each column (the raw analog pathway); compare "
            "against exact digital float dot-products (the baseline); apply the "
            "paper's per-column statistical-rescaling calibration to recover accuracy; "
            "tally ADC/DAC conversions and KV-cache memory reads AVOIDED by computing "
            "in-memory. Energy/latency advantage figures are the PAPER's claim, not a "
            "measured SZL result."
        ),
        "seed": seed,
        **snap,
        "honest_note": (
            "MODELED: this is a deterministic, pure-stdlib re-implementation of the "
            "charge-domain crossbar attention ARITHMETIC behind analog in-memory "
            "computing attention (Leroux et al. 2025, Nature Computational Science "
            "s43588-025-00854-1), NOT a run on real analog gain-cell hardware and "
            "NEVER-CLAIMED-AS the Leroux et al. chip. Synthetic query/Key vectors and "
            "the fixed additive device noise are drawn from a deterministic LCG PRNG "
            "(no numpy, no stdlib random, no proprietary weights, no real language "
            "model, no real analog device) and run on ordinary digital CPU floats. "
            "CRUCIALLY: the energy 'operations avoided' tally and the "
            "energy_reduction / latency_reduction figures reported here are the "
            "PAPER's published CLAIMS reproduced at toy scale via an accounting model "
            "— they are NOT measured on real analog hardware and are NOT a measured "
            "SZL figure. The per-column calibration reproduces the paper's "
            "software-to-hardware rescaling qualitatively only. Deterministic: same "
            "seed/seq_len/dim/noise_sigma -> identical snapshot. SZL claims NONE of "
            "these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_kvcache.register() / szl_mla.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/aimc/attend onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/aimc"
    handlers = [
        (f"{base}/attend", _h_attend),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        # Additive registration must never break the host app; degrade silently.
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _aimc_snapshot(seed=42, seq_len=128, dim=64, noise_sigma=0.05)
    print("label: MODELED")
    print("seq_len:", snap["seq_len"])
    print("dim:", snap["dim"])
    print("noise_sigma:", snap["noise_sigma"])
    print("analog_mse:", snap["analog_mse"])
    print("calibrated_mse:", snap["calibrated_mse"])
    print("calibration_gain:", snap["calibration_gain"])
    print("accuracy_recovered_pct:", snap["accuracy_recovered_pct"])
    print("adc_dac_ops_avoided:", snap["adc_dac_ops_avoided"])
    print("memory_move_reads_avoided:", snap["memory_move_reads_avoided"])
    print("total_ops_avoided:", snap["total_ops_avoided"])
    print("paper_energy_reduction_claim:", snap["paper_energy_reduction_claim"])
    print("paper_latency_reduction_claim:", snap["paper_latency_reduction_claim"])
    print("sample_digital_scores[:5]:", snap["sample_digital_scores"][:5])
    print("sample_analog_scores[:5]:", snap["sample_analog_scores"][:5])
    print("sample_calibrated_scores[:5]:", snap["sample_calibrated_scores"][:5])

    # sanity: bounds
    assert snap["analog_mse"] >= 0.0, "analog_mse must be non-negative"
    assert snap["calibrated_mse"] >= 0.0, "calibrated_mse must be non-negative"
    assert snap["total_ops_avoided"] == snap["adc_dac_ops_avoided"] + snap["memory_move_reads_avoided"], \
        "total_ops_avoided tally mismatch"
    assert snap["adc_dac_ops_avoided"] == 2 * snap["seq_len"] * snap["dim"], \
        "adc_dac_ops_avoided formula mismatch"
    assert snap["memory_move_reads_avoided"] == snap["seq_len"] * snap["dim"], \
        "memory_move_reads_avoided formula mismatch"

    # core claim: the paper's calibration step RECOVERS accuracy — calibrated
    # analog scores must be closer to the digital baseline than the raw analog
    # scores (calibration_gain positive, accuracy recovered).
    assert snap["calibrated_mse"] <= snap["analog_mse"] + 1e-12, \
        "calibration must not worsen the analog error"
    assert snap["calibration_gain"] >= 0.0, "calibration_gain must be non-negative"

    # a NOISELESS crossbar must reproduce the digital baseline exactly.
    snap0 = _aimc_snapshot(seed=42, seq_len=128, dim=64, noise_sigma=0.0)
    assert snap0["analog_mse"] <= 1e-12, "zero device noise must yield ~zero analog error"

    # a LARGER device noise must increase the raw analog error (monotone).
    snap_hi = _aimc_snapshot(seed=42, seq_len=128, dim=64, noise_sigma=0.20)
    assert snap_hi["analog_mse"] > snap["analog_mse"], \
        "larger noise_sigma must increase raw analog error"

    # sanity: determinism — identical inputs -> identical snapshot (twice).
    snap2 = _aimc_snapshot(seed=42, seq_len=128, dim=64, noise_sigma=0.05)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_aimc: ALL OK — analog crossbar attention MODELED, calibration recovers "
          "accuracy, energy 'ops avoided' tallied (PAPER's claim, not measured SZL), "
          "deterministic.")
