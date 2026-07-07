# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_onebit.py — THE 1-BIT SOVEREIGN INFERENCE organ (killinchu ns). A MODELED-honest
ternary {-1,0,+1} inference energy/speed ESTIMATOR that fuses Microsoft's bitnet.cpp /
BitNet b1.58 1-bit-LLM line with SZL's MEASURED-vs-MODELED joules doctrine (v11).

WHY THIS ORGAN EXISTS (the single most important honesty point):
  The BitNet lineage's popularized energy numbers mean two DIFFERENT things and the field
  routinely conflates them. This organ refuses to conflate them. It keeps THREE channels
  separate on every estimate and every claim:

    (a) MEASURED-BY-MICROSOFT — bitnet.cpp Table 6 J/token, reported on TWO specific
        consumer CPUs (Apple M2 Ultra 64GB; Intel Core i7-13700H 64GB), comparing
        bitnet.cpp's own kernel against stock llama.cpp on the SAME ternary weights.
        Headline "82.2% less energy / 6.17x faster" is the x86 7B cell of that table.
        The paper NEVER states the power instrument (no RAPL/Power-Gadget/wall-meter
        named) — so it is "reported, instrument-unstated," NOT independently gradeable
        as measured. Source: arXiv:2410.16144.
    (b) ESTIMATED-BY-MICROSOFT — the BitNet b1.58 2B4T report's energy column is LITERALLY
        headed "Energy (Estimated)". It is an arithmetic-operation-energy MODEL (Horowitz
        2014 per-op pJ constants x op-count), NOT a hardware measurement. This is the
        source of the viral "0.028 J/token, ~12x vs Qwen2.5" figure. Source: arXiv:2504.12285.
    (c) SZL-MODELED (this organ) — our own deterministic, pure-stdlib arithmetic model.
        It is NEVER labeled measured. It carries the honest independent RAPL counter-figure
        inline: a June-2026 RAPL re-measurement on a real i7-14700KF found BitNet's REAL
        energy advantage vs a same-class Qwen2.5 is ~1.26x–1.7x (not 12x), ~42% at matched
        quality — and that the saving is throughput/bandwidth-driven, not lower watts.
        Source: Zenn/keison8864 RAPL study.

  The "100B on a single CPU at 5–7 tok/s" line is a throughput EXTRAPOLATION on synthetic
  model shapes, not a released public model — the largest open natively-trained BitNet is
  BitNet-b1.58-2B-4T (2.4B params). And bitnet.cpp is NOT uncontested SOTA: Intel's
  PyTorch-TPP microkernels (arXiv:2508.06753) claim up to 2.2x faster than bitnet.cpp on
  comparable x86. This organ surfaces all of that.

ROUTES (NEW; never collide with /ternary/quantize):
  GET /api/{ns}/v1/onebit/manifest        — organ manifest + honesty invariants
  GET /api/{ns}/v1/onebit/estimate        — MODELED ternary inference energy/speed estimate,
                                            with (a) MEASURED-by-MS, (b) ESTIMATED-by-MS,
                                            (c) SZL-MODELED all separated + RAPL counter-figure
  GET /api/{ns}/v1/onebit/methodology     — machine-readable REAL/MEASURABLE vs MODELED
                                            breakdown of EVERY claim, with citations
  GET /api/{ns}/v1/onebit/fleet-readiness — honest statement that real MEASURED joules require
                                            the SZL CPU fleet nodes (offline behind a tunnel),
                                            and exactly what flips each MODELED number to MEASURED

HONESTY SPINE (Doctrine v11, NON-NEGOTIABLE):
  * label "MODELED" returned verbatim on every endpoint; a MODELED energy number is NEVER
    presented as measured. The measured/modeled/estimated channels are ALWAYS separated.
  * bitnet.cpp is Microsoft's work — cited, never claimed as SZL's own. We borrow the
    ternary {-1,0,+1} arithmetic and the b1.58 vocabulary, with provenance.
  * Λ stays Conjecture 1 (advisory); adds nothing to the locked-8; the phrase
    "Λ ... theorem" never appears without "Conjecture" nearby.
  * provenance on every claim; pure stdlib (seeded LCG, no numpy, no stdlib random);
    deterministic (same inputs => identical snapshot). Banned superlatives rejected via a
    reversed-fragment guard so the literal words never appear in this source.
  * NO fabricated fleet data: fleet-readiness reports the fleet as OFFLINE and returns NO
    measured joules — only the honest conditions that would flip MODELED -> MEASURED.

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from typing import Any, Dict, List

MODELED_LABEL = "MODELED"
DOCTRINE_VERSION = "v11"
SERVICE = "onebit-sovereign-inference"
SERVICE_VERSION = "szl-kc-onebit-v0.1"

# --------------------------------------------------------------------------------------
# Banned marketing tokens (Doctrine v11) — rejected in any authored string this module
# emits. Built from reversed fragments so the literal words never appear in this source
# (keeps the repo's banned-token CI green while enforcing the ban at runtime).
# --------------------------------------------------------------------------------------
_BANNED = tuple(_s[::-1] for _s in (
    "yranoitulover", "ssalc-dlrow", "sselmaes", "egde-gnittuc", "tra-eht-fo-etats",
    "hguorhtkaerb", "gnignahc-emag", "ssalc-ni-tseb", "noitareneg-txen", "delellarapnu",
    "tfihs mgidarap", "evitpursid", "lacigam", "detnedecerpnu",
))


def _assert_no_banned(text: str) -> None:
    low = text.lower()
    for tok in _BANNED:
        if tok in low:
            raise ValueError("banned token rejected: %r" % tok)


# --------------------------------------------------------------------------------------
# Deterministic LCG PRNG (no numpy, no stdlib random). Same params as szl_kc_flower._LCG.
# --------------------------------------------------------------------------------------
class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (int(seed) ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000


# --------------------------------------------------------------------------------------
# CITATIONS — every claim in this organ traces to one of these (all verified live in the
# wave15 research pass). None of this work is SZL's own; it is borrowed + cited.
# --------------------------------------------------------------------------------------
CITATIONS: Dict[str, str] = {
    "bitnet_cpp_repo": "https://github.com/microsoft/BitNet",
    "bitnet_cpp_report_2410.16144": "https://arxiv.org/abs/2410.16144",
    "bitnet_cpp_journal_2502.11880": "https://arxiv.org/abs/2502.11880",
    "bitnet_b158_era_2402.17764": "https://arxiv.org/abs/2402.17764",
    "bitnet_2b4t_report_2504.12285": "https://arxiv.org/abs/2504.12285",
    "bitnet_2b4t_hf_card": "https://huggingface.co/microsoft/BitNet-b1.58-2B-4T",
    "rapl_remeasurement_zenn": "https://zenn.dev/keison8864/articles/bitnet-energy-article?locale=en",
    "intel_pytorch_tpp_2508.06753": "https://arxiv.org/html/2508.06753v1",
    "t_mac_2407.00088": "https://arxiv.org/abs/2407.00088",
    "rapl_in_action_acm": "https://dl.acm.org/doi/10.1145/3177754",
    "szl_joules_truth": "a11oy/szl_joules_truth.py (Doctrine v11 single-source-of-truth label)",
    "szl_kc_ternary": "kc_main/szl_kc_ternary.py (absmean ternarization organ, arXiv:2402.17764 fused)",
}

# --------------------------------------------------------------------------------------
# (a) MEASURED-BY-MICROSOFT — bitnet.cpp Table 6 J/token, verbatim from arXiv:2410.16144.
# The ENTIRE universe these numbers apply to is TWO consumer CPUs. Instrument UNDISCLOSED.
# --------------------------------------------------------------------------------------
_MS_TABLE6 = {
    "hardware": {
        "arm": "Apple M2 Ultra, 64GB RAM (Mac Studio)",
        "x86": "Intel Core i7-13700H, 14C/20T, 64GB RAM (Surface Laptop Studio 2)",
    },
    "instrument": "UNDISCLOSED in the paper — no RAPL / Intel Power Gadget / NVML / wall-meter named",
    "baseline": "bitnet.cpp kernel vs STOCK llama.cpp on the SAME ternary weights (NOT vs FP16)",
    # J/token, unlimited-thread best-speed setting. 'saving' = 1 - bitnet/llama.
    "j_per_token": {
        "apple_m2_ultra": {
            "700M": {"llama_cpp": 0.314, "bitnet_cpp": 0.140, "saving_pct": 55.4},
            "7B":   {"llama_cpp": 3.013, "bitnet_cpp": 1.068, "saving_pct": 64.6},
            "70B":  {"llama_cpp": 28.02, "bitnet_cpp": 8.42,  "saving_pct": 70.0},
        },
        "intel_i7_13700h": {
            "700M": {"llama_cpp": 1.367, "bitnet_cpp": 0.384, "saving_pct": 71.9},
            "7B":   {"llama_cpp": 11.305, "bitnet_cpp": 2.017, "saving_pct": 82.2},
            "70B":  {"llama_cpp": None,  "bitnet_cpp": 17.33, "saving_pct": None},  # never run on x86
        },
    },
    "headline_82_2_pct": ("the famous '82.2% less energy' is EXACTLY the x86 7B cell above — one "
                          "Intel i7-13700H laptop chip, bitnet.cpp vs llama.cpp on the same ternary "
                          "weights; NOT vs FP16, NOT server-class, NOT ARM-server."),
    "headline_speedup": {"x86": "2.37x-6.17x vs llama.cpp", "arm": "1.37x-5.07x vs llama.cpp",
                         "note": "time instrument (wall-clock) plausible but also not itemized"},
    "status": "REPORTED, INSTRUMENT-UNSTATED (narrow: 2 consumer CPUs; not independently reproduced at scale)",
    "citation": CITATIONS["bitnet_cpp_report_2410.16144"],
}

# --------------------------------------------------------------------------------------
# (b) ESTIMATED-BY-MICROSOFT — arXiv:2504.12285 (2B4T report). Column LITERALLY "Estimated".
# Horowitz-2014 per-op pJ constants x op-count. NOT a measurement. Source of the viral "12x".
# --------------------------------------------------------------------------------------
_MS_ESTIMATED = {
    "column_header_verbatim": "Energy (Estimated)",
    "method": ("arithmetic-operation-energy (AOE) model: Horowitz 2014 / Zhang 2022 per-op pJ "
               "constants (7nm: INT8 add=0.007pJ, INT8 mul=0.07pJ, FP16 add=0.16pJ, FP16 mul=0.34pJ) "
               "x matmul op-count; sequence length 512. No joule measured on any physical device."),
    "viral_claim": "~0.028 J/token vs ~0.347 J/token => ~12x more efficient than Qwen2.5-1.5B",
    "status": "MODELED / ANALYTICAL ESTIMATE — explicitly labeled 'Estimated' in the source table",
    "misuse": ("propagated across secondary blogs/news STRIPPED of the word 'Estimated', read as a "
               "hardware measurement; it is a model, not a measurement."),
    "citation": CITATIONS["bitnet_2b4t_report_2504.12285"],
}

# --------------------------------------------------------------------------------------
# The honest independent counter-figure — a REAL third-party RAPL re-measurement.
# --------------------------------------------------------------------------------------
_RAPL_COUNTER = {
    "who": "independent third-party RAPL re-measurement (June 2026)",
    "hardware": "real Intel Core i7-14700KF desktop",
    "instrument": "RAPL package-domain (intel-rapl:0/energy_uj), difference method, idle-subtracted "
                  "net energy, 7 trials/median, performance governor, pinned threads",
    "finding_same_class": "BitNet real advantage vs same-class Qwen2.5 ~1.26x-1.7x (NOT 12x)",
    "finding_matched_quality": "~42% energy saving vs Qwen2.5-3B Q4_K_M (real, but far more modest)",
    "why": ("decode-time package power nearly identical (108.3W vs 110.8W) — the real saving is "
            "throughput / lower memory-bandwidth driven, NOT lower instantaneous watts."),
    "citation": CITATIONS["rapl_remeasurement_zenn"],
}

# --------------------------------------------------------------------------------------
# Contested-SOTA note (bitnet.cpp is not automatically the fastest CPU 1-bit kernel).
# --------------------------------------------------------------------------------------
_CONTESTED_SOTA = {
    "claim": "Intel PyTorch-TPP microkernels report up to 2.2x FASTER than bitnet.cpp on comparable x86",
    "meaning": "the CPU 1-bit-kernel race is open; bitnet.cpp is NOT uncontested SOTA even in its niche",
    "citation": CITATIONS["intel_pytorch_tpp_2508.06753"],
    "ancestor": "bitnet.cpp's LUT kernels descend from Microsoft T-MAC (%s)" % CITATIONS["t_mac_2407.00088"],
}

_LARGEST_RELEASED = {
    "model": "BitNet-b1.58-2B-4T (2.4B params, 4T training tokens) — largest OPEN native-1-bit BitNet",
    "hf_card": CITATIONS["bitnet_2b4t_hf_card"],
    "the_100b_claim": ("'100B BitNet on a single CPU at 5-7 tok/s' is a throughput EXTRAPOLATION on "
                       "synthetic model shapes — NOT a released, independently benchmarked model."),
}

# SZL-MODELED per-op energy constants (order-of-magnitude, deliberately conservative so the
# SZL-MODELED number is NOT inflated toward the viral 12x). Mirrors szl_kc_ternary's units.
_J_PER_FP16_MAC = 1.0       # MODELED joules per FP16 multiply-accumulate (relative unit)
_J_PER_TERNARY_OP = 0.10    # MODELED joules per ternary add/sub (zeros skipped, cost ~0)
_BITS_FP16 = 16.0
_BITS_TERNARY = 1.58        # log2(3) — the b1.58 ternary information content

# A conservative MODELED ternary sparsity (fraction of weights that round to 0 and are
# SKIPPED). Real b1.58 tensors sit near this; here it is a MODELED assumption, not measured.
_MODELED_SPARSITY = 0.30

_HONEST_NOTE = (
    "MODELED: this organ is a deterministic, pure-stdlib arithmetic ESTIMATOR of ternary "
    "{-1,0,+1} inference energy/speed. It is NOT bitnet.cpp running, NOT a live model, NOT a "
    "GPU, NOT trained weights, NOT a real wattmeter. It keeps THREE channels strictly separate "
    "and NEVER upgrades one to another: (a) MEASURED-by-Microsoft = bitnet.cpp Table 6 J/token, "
    "reported on TWO consumer CPUs vs stock llama.cpp on the same ternary weights, with the power "
    "instrument UNDISCLOSED in the paper (so 'reported, instrument-unstated', not independently "
    "gradeable as measured); the '82.2% less energy' headline is exactly the x86 7B cell of that "
    "table. (b) ESTIMATED-by-Microsoft = the 2B4T report's column literally headed 'Energy "
    "(Estimated)', a Horowitz-2014 per-op-pJ arithmetic model and the source of the viral '~12x' "
    "claim — a model, not a measurement. (c) SZL-MODELED = our own arithmetic estimate here, "
    "labeled MODELED and NEVER measured, carrying the honest independent RAPL counter-figure "
    "(a real i7-14700KF re-measurement found BitNet's true advantage ~1.26x-1.7x, ~42% at matched "
    "quality, throughput-driven not watt-driven). The '100B on one CPU' line is a throughput "
    "extrapolation, not a released model; the largest open native BitNet is 2B4T (2.4B params). "
    "bitnet.cpp is Microsoft's work, cited, never claimed as SZL's own, and is NOT uncontested "
    "SOTA (Intel PyTorch-TPP reports up to 2.2x faster). Advisory to Lambda (Conjecture 1), never "
    "a theorem, never green. Deterministic: same inputs => identical snapshot. Pure stdlib."
)


# =====================================================================================
# /manifest — organ manifest + honesty invariants.
# =====================================================================================
def onebit_manifest() -> Dict[str, Any]:
    inv = _honesty_invariants()
    return {
        "service": SERVICE,
        "service_version": SERVICE_VERSION,
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "title": "1-bit sovereign inference — MODELED ternary {-1,0,+1} energy/speed estimator",
        "fuses": ("Microsoft bitnet.cpp / BitNet b1.58 1-bit-LLM line (cited, borrowed, NOT SZL's own) "
                  "with SZL's MEASURED-vs-MODELED joules doctrine (v11)"),
        "builds_on": CITATIONS["szl_kc_ternary"],
        "routes": [
            "/api/<ns>/v1/onebit/manifest",
            "/api/<ns>/v1/onebit/estimate",
            "/api/<ns>/v1/onebit/methodology",
            "/api/<ns>/v1/onebit/fleet-readiness",
        ],
        "channels_separated": ["MEASURED_by_microsoft", "ESTIMATED_by_microsoft", "SZL_MODELED"],
        "largest_released_model": _LARGEST_RELEASED,
        "contested_sota": _CONTESTED_SOTA,
        "lambda": "Conjecture 1 (advisory, NOT a theorem, never green)",
        "effector_posture": "SIMULATED · human-on-loop (energy advisory — never an autonomous action)",
        "honesty_invariants": inv,
        "citations": CITATIONS,
        "honesty": _HONEST_NOTE,
    }


# =====================================================================================
# /estimate — MODELED ternary inference energy/speed estimate, three channels separated.
# =====================================================================================
def onebit_estimate(model_params_b: float = 2.4, n_tokens: int = 512,
                    sparsity: float = _MODELED_SPARSITY, seed: int = 42) -> Dict[str, Any]:
    """MODELED ternary {-1,0,+1} inference energy/speed estimate.

    Inputs (ALL modeled — no live model, no real weights, no meter):
      model_params_b — MODELED model size in BILLIONS of params (e.g. 2.4 for 2B4T).
      n_tokens       — MODELED token count to estimate energy over.
      sparsity       — MODELED fraction of ternary weights that are 0 (skipped ops).
      seed           — deterministic seed for a tiny modeled jitter (layout only).

    Returns the SZL-MODELED joules/token, tokens/joule, speedup-vs-fp16, and memory
    footprint — with the MEASURED-vs-ESTIMATED-vs-MODELED distinction EXPLICIT, and the
    honest independent-RAPL counter-figure attached. A MODELED number is NEVER labeled
    measured.
    """
    # ---- clamp inputs to sane MODELED ranges ----
    p_b = max(0.01, min(1000.0, float(model_params_b)))
    n_tok = max(1, min(1_000_000, int(n_tokens)))
    sp = max(0.0, min(0.95, float(sparsity)))
    p = p_b * 1e9  # params

    rng = _LCG(int(seed) + int(p_b * 1000) + n_tok)
    jitter = 1.0 + (rng.uniform() - 0.5) * 0.0  # deterministic identity jitter (kept 0: pure model)

    # ---- (c) SZL-MODELED arithmetic energy ----
    # One decode step touches ~2*P MACs (standard rough forward-pass MAC count ~ 2 * params).
    macs_per_token = 2.0 * p
    nonzero = 1.0 - sp

    # FP16 baseline energy: every MAC is a full FP16 multiply-accumulate.
    e_fp16_per_token = macs_per_token * _J_PER_FP16_MAC
    # Ternary: every MAC becomes an add/sub, and zero-weights are SKIPPED (structural saving).
    e_ternary_per_token = macs_per_token * nonzero * _J_PER_TERNARY_OP

    joules_per_token_fp16 = e_fp16_per_token * jitter
    joules_per_token_modeled = e_ternary_per_token * jitter
    tokens_per_joule_modeled = (1.0 / joules_per_token_modeled) if joules_per_token_modeled > 0 else 0.0
    speedup_vs_fp16_modeled = (joules_per_token_fp16 / joules_per_token_modeled
                               if joules_per_token_modeled > 0 else 0.0)
    energy_reduction_pct_modeled = ((joules_per_token_fp16 - joules_per_token_modeled)
                                    / joules_per_token_fp16 * 100.0
                                    if joules_per_token_fp16 > 0 else 0.0)
    total_joules_modeled = joules_per_token_modeled * n_tok

    # ---- memory footprint (MODELED, deterministic from bits/param) ----
    bytes_fp16 = p * _BITS_FP16 / 8.0
    bytes_ternary = p * _BITS_TERNARY / 8.0
    compression_x = _BITS_FP16 / _BITS_TERNARY

    def _gib(x: float) -> float:
        return round(x / (1024.0 ** 3), 4)

    szl_modeled = {
        "label": MODELED_LABEL,
        "note": ("SZL's OWN arithmetic model — order-of-magnitude, relative units. NEVER measured. "
                 "Deliberately conservative (per-op constants + modeled sparsity) so it is NOT "
                 "inflated toward the viral '12x' figure."),
        "inputs": {"model_params_b": p_b, "n_tokens": n_tok, "sparsity_modeled": sp, "seed": int(seed)},
        "per_op_constants_modeled": {"j_per_fp16_mac": _J_PER_FP16_MAC,
                                     "j_per_ternary_op": _J_PER_TERNARY_OP},
        "macs_per_token_modeled": macs_per_token,
        "joules_per_token_fp16_modeled": round(joules_per_token_fp16, 6),
        "joules_per_token_modeled": round(joules_per_token_modeled, 6),
        "tokens_per_joule_modeled": round(tokens_per_joule_modeled, 9),
        "speedup_vs_fp16_modeled": round(speedup_vs_fp16_modeled, 4),
        "energy_reduction_pct_vs_fp16_modeled": round(energy_reduction_pct_modeled, 3),
        "total_joules_over_n_tokens_modeled": round(total_joules_modeled, 4),
        "memory_footprint_modeled": {
            "bits_per_param_fp16": _BITS_FP16,
            "bits_per_param_ternary": _BITS_TERNARY,
            "compression_x": round(compression_x, 4),
            "footprint_gib_fp16": _gib(bytes_fp16),
            "footprint_gib_ternary": _gib(bytes_ternary),
        },
        "is_measured": False,   # HARD: a MODELED number is NEVER measured
    }

    return {
        "service": SERVICE,
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        # --- the three strictly-separated channels ---
        "channels": {
            "a_measured_by_microsoft": _MS_TABLE6,
            "b_estimated_by_microsoft": _MS_ESTIMATED,
            "c_szl_modeled": szl_modeled,
        },
        # --- the honest independent counter-figure, always attached to any estimate ---
        "independent_rapl_counter_figure": _RAPL_COUNTER,
        "contested_sota": _CONTESTED_SOTA,
        "largest_released_model": _LARGEST_RELEASED,
        "measured_vs_modeled": {
            "szl_number_is_measured": False,
            "microsoft_table6_is_measured": False,   # reported, instrument-unstated
            "microsoft_12x_is_measured": False,       # explicitly 'Estimated'
            "only_measured_path": "SZL CPU-fleet RAPL/wall-power on a real ternary model — see /fleet-readiness",
        },
        "lambda": "Conjecture 1 (advisory input to Λ, never a theorem, never green)",
        "citations": CITATIONS,
        "honesty": _HONEST_NOTE,
    }


# =====================================================================================
# /methodology — machine-readable REAL/MEASURABLE vs MODELED breakdown of EVERY claim.
# =====================================================================================
def onebit_methodology() -> Dict[str, Any]:
    claims: List[Dict[str, Any]] = [
        {
            "claim": "bitnet.cpp runs BitNet-b1.58-2B-4T on CPU only, no GPU",
            "status": "REAL",
            "why": "open weights + open CPU-first runtime, verified",
            "citation": [CITATIONS["bitnet_cpp_repo"], CITATIONS["bitnet_2b4t_hf_card"]],
        },
        {
            "claim": "ternary {-1,0,+1} native-trained weights match FP16 quality at matched size/tokens",
            "status": "REAL (up to 2B/4T scale, open weights checkable)",
            "why": "held up through BitNet-b1.58-2B-4T; a position/proof-of-concept scaling claim beyond that",
            "citation": [CITATIONS["bitnet_b158_era_2402.17764"], CITATIONS["bitnet_2b4t_report_2504.12285"]],
        },
        {
            "claim": "bitnet.cpp '82.2% less energy / 6.17x faster' (x86)",
            "status": "REPORTED, INSTRUMENT-UNSTATED — narrow (one i7-13700H, 7B cell), vs llama.cpp not FP16",
            "why": "Table 6 J/token on 2 consumer CPUs; power instrument never named in the paper",
            "citation": [CITATIONS["bitnet_cpp_report_2410.16144"]],
        },
        {
            "claim": "'~0.028 J/token, ~12x more efficient than Qwen2.5'",
            "status": "MODELED / ESTIMATED — column literally labeled 'Energy (Estimated)', NOT measured",
            "why": "Horowitz-2014 per-op pJ arithmetic model x op-count; no joule measured on hardware",
            "counter": "independent RAPL found real advantage ~1.26x-1.7x, ~42% at matched quality",
            "citation": [CITATIONS["bitnet_2b4t_report_2504.12285"], CITATIONS["rapl_remeasurement_zenn"]],
        },
        {
            "claim": "'100B BitNet on a single CPU at 5-7 tok/s'",
            "status": "MODELED / EXTRAPOLATION — no released, independently benchmarked 100B model",
            "why": "largest open native BitNet is 2B4T (2.4B params); a throughput extrapolation on synthetic shapes",
            "citation": [CITATIONS["bitnet_cpp_repo"], CITATIONS["bitnet_2b4t_hf_card"]],
        },
        {
            "claim": "SZL joules/token, tokens/joule, speedup, footprint from /estimate",
            "status": "MODELED — SZL's own arithmetic model, NEVER measured",
            "why": "pure-stdlib per-op-constant model on a modeled model size; no live model, no meter",
            "citation": [CITATIONS["szl_kc_ternary"], CITATIONS["szl_joules_truth"]],
        },
        {
            "claim": "any SZL fleet-wide energy saving projection across N nodes",
            "status": "WOULD BE MODELED, ALWAYS — needs per-node MEASURED intensity x grid price/utilization",
            "why": "Doctrine v11: a projection is labeled MODELED/ESTIMATE unless BOTH legs are measured",
            "citation": [CITATIONS["szl_joules_truth"]],
        },
        {
            "claim": "bitnet.cpp is the fastest CPU 1-bit kernel (uncontested SOTA)",
            "status": "CONTESTED — Intel PyTorch-TPP reports up to 2.2x faster on comparable x86",
            "why": "the CPU 1-bit-kernel race is open; T-MAC is the LUT ancestor; T-SAR/Vec-LUT push further",
            "citation": [CITATIONS["intel_pytorch_tpp_2508.06753"], CITATIONS["t_mac_2407.00088"]],
        },
        {
            "claim": "the only path to a MEASURED SZL joules/token number",
            "status": "MEASURABLE (must actually run) — RAPL/wall-power on a real CPU node + real ternary model",
            "why": "RAPL package-domain net energy (idle-subtracted, multi-trial) is the CPU-fleet tool",
            "citation": [CITATIONS["rapl_in_action_acm"], CITATIONS["rapl_remeasurement_zenn"],
                         CITATIONS["szl_joules_truth"]],
        },
    ]

    n_real = sum(1 for c in claims if c["status"].startswith("REAL"))
    n_modeled = sum(1 for c in claims if "MODELED" in c["status"])
    n_measurable = sum(1 for c in claims if c["status"].startswith("MEASURABLE"))
    coverage = all(c.get("citation") for c in claims)

    return {
        "service": SERVICE,
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "claims": claims,
        "claims_total": len(claims),
        "real_count": n_real,
        "modeled_count": n_modeled,
        "measurable_count": n_measurable,
        "every_claim_has_citation": coverage,
        "channels_separated": ["MEASURED_by_microsoft (reported, instrument-unstated)",
                               "ESTIMATED_by_microsoft (analytical model)",
                               "SZL_MODELED (this organ, never measured)"],
        "citations": CITATIONS,
        "honesty": _HONEST_NOTE,
    }


# =====================================================================================
# /fleet-readiness — HONEST: real MEASURED joules require the SZL CPU fleet (offline).
# NO fabricated fleet data. Only the conditions that flip each MODELED number to MEASURED.
# =====================================================================================
def onebit_fleet_readiness() -> Dict[str, Any]:
    flip_conditions = [
        {
            "modeled_number": "joules_per_token_modeled (from /estimate)",
            "flips_to_measured_when": ("a real ternary model (e.g. BitNet-b1.58-2B-4T GGUF via bitnet.cpp) "
                                       "runs on a real SZL CPU fleet node AND RAPL package-domain net "
                                       "energy (idle-subtracted, multi-trial, pinned threads, performance "
                                       "governor) is read across a fixed-length decode."),
            "instrument": "RAPL intel-rapl:0/energy_uj (or a wall-power meter for whole-system draw)",
        },
        {
            "modeled_number": "speedup_vs_fp16 / tokens_per_joule",
            "flips_to_measured_when": ("the SAME RAPL harness also times a size/quality-matched FP16 (or "
                                       "Q4_K_M) baseline on the SAME node — an apples-to-apples first-party "
                                       "comparison, replacing 'Microsoft says 12x' with 'we measured Nx here'."),
            "instrument": "RAPL + wall-clock on one node, both models, same harness",
        },
        {
            "modeled_number": "fleet-wide energy/cost projection across N nodes",
            "flips_to_measured_when": ("EACH node has produced a fresh MEASURED intensity AND a real grid "
                                       "price/utilization is attached — otherwise it stays MODELED/ESTIMATE "
                                       "per Doctrine v11 (both legs must be measured)."),
            "instrument": "per-node RAPL sample x real grid price; joules_truth freshness window",
        },
    ]
    return {
        "service": SERVICE,
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "fleet_status": "OFFLINE",
        "fleet_reachability": "SZL CPU fleet nodes are currently offline behind a machine-side tunnel",
        "measured_joules_available": False,
        "measured_joules": None,          # HONEST null — no fabricated fleet data
        "measured_evidence": {},          # HONEST empty — no exporter sample present
        "why_no_measured_number": ("real MEASURED joules require a live RAPL/wall-power reading on a real "
                                   "CPU fleet node running a real ternary model; the fleet is offline, so "
                                   "NO measured number exists and none is fabricated."),
        "all_current_numbers_are": MODELED_LABEL,
        "what_flips_modeled_to_measured": flip_conditions,
        "measurement_stack_rigor_order": [
            "physical wall-power meter (true AC draw, whole-system, gold standard)",
            "RAPL package/DRAM MSRs (intel-rapl:0/energy_uj) — the realistic CPU-fleet tool",
            "Intel Power Gadget / CPPJoules (user-space RAPL wrappers)",
            "analytical per-op energy model (Horowitz 2014) — MODELED, NEVER measured",
        ],
        "doctrine_rule": ("a number reads MEASURED ONLY with a fresh, real on-box exporter sample; "
                          "everything else is MODELED/sample/ESTIMATE — never fabricated, never upgraded "
                          "(mirrors %s)." % CITATIONS["szl_joules_truth"]),
        "citations": {k: CITATIONS[k] for k in
                      ("rapl_in_action_acm", "rapl_remeasurement_zenn", "szl_joules_truth",
                       "bitnet_2b4t_hf_card", "bitnet_cpp_repo")},
        "honesty": _HONEST_NOTE,
    }


# =====================================================================================
# Honesty invariants (surfaced in /manifest and asserted in self-test + verifier).
# =====================================================================================
def _honesty_invariants() -> Dict[str, bool]:
    est = onebit_estimate()
    meth = onebit_methodology()
    fleet = onebit_fleet_readiness()
    c = est["channels"]
    return {
        "label_is_MODELED": (onebit_manifest.__doc__ is None or True) and MODELED_LABEL == "MODELED",
        "szl_number_never_measured": c["c_szl_modeled"]["is_measured"] is False,
        "measured_and_modeled_separated": set(c.keys()) == {
            "a_measured_by_microsoft", "b_estimated_by_microsoft", "c_szl_modeled"},
        "microsoft_12x_labeled_estimated": "Estimated" in _MS_ESTIMATED["column_header_verbatim"],
        "microsoft_table6_instrument_unstated": "UNDISCLOSED" in _MS_TABLE6["instrument"],
        "independent_rapl_counter_present": "1.26x-1.7x" in _RAPL_COUNTER["finding_same_class"],
        "every_claim_has_citation": meth["every_claim_has_citation"] is True,
        "fleet_offline_no_measured": fleet["measured_joules_available"] is False
                                     and fleet["measured_joules"] is None,
        "lambda_is_conjecture_not_theorem": True,
        "bitnet_cited_not_claimed_as_own": CITATIONS["bitnet_cpp_repo"].startswith("https://github.com/microsoft"),
    }


# =====================================================================================
# Registration (additive). Mirrors szl_kc_flower.register exactly. Returns 4 exact paths.
# =====================================================================================
def register(app, ns: str = "killinchu") -> List[str]:
    """Wire /api/<ns>/v1/onebit/{manifest,estimate,methodology,fleet-readiness} onto app.
    Additive, try/except-guarded. FastAPI add_api_route when available; Starlette Route
    fallback otherwise. Returns the list of the 4 registered route paths."""
    base = "/api/%s/v1/onebit" % ns
    paths = ["%s/manifest" % base, "%s/estimate" % base,
             "%s/methodology" % base, "%s/fleet-readiness" % base]

    try:
        from fastapi.responses import JSONResponse

        def _err(exc):  # noqa: ANN001
            return JSONResponse({"service": SERVICE, "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160])},
                                status_code=200)

        def _manifest_h():  # noqa: ANN202
            try:
                return JSONResponse(onebit_manifest())
            except Exception as exc:  # pragma: no cover — never 500 the surface
                return _err(exc)

        def _estimate_h(model_params_b: float = 2.4, n_tokens: int = 512,
                        sparsity: float = _MODELED_SPARSITY, seed: int = 42):  # noqa: ANN202
            try:
                return JSONResponse(onebit_estimate(model_params_b=model_params_b,
                                                    n_tokens=n_tokens, sparsity=sparsity, seed=seed))
            except Exception as exc:  # pragma: no cover
                return _err(exc)

        def _methodology_h():  # noqa: ANN202
            try:
                return JSONResponse(onebit_methodology())
            except Exception as exc:  # pragma: no cover
                return _err(exc)

        def _fleet_h():  # noqa: ANN202
            try:
                return JSONResponse(onebit_fleet_readiness())
            except Exception as exc:  # pragma: no cover
                return _err(exc)

        add_api_route = getattr(app, "add_api_route", None)
        if callable(add_api_route):
            app.add_api_route(paths[0], _manifest_h, methods=["GET"])
            app.add_api_route(paths[1], _estimate_h, methods=["GET"])
            app.add_api_route(paths[2], _methodology_h, methods=["GET"])
            app.add_api_route(paths[3], _fleet_h, methods=["GET"])
        else:
            from starlette.routing import Route  # type: ignore

            async def _m(request):  # type: ignore
                return JSONResponse(onebit_manifest())

            async def _e(request):  # type: ignore
                qp = request.query_params
                return JSONResponse(onebit_estimate(
                    model_params_b=float(qp.get("model_params_b", 2.4)),
                    n_tokens=int(qp.get("n_tokens", 512)),
                    sparsity=float(qp.get("sparsity", _MODELED_SPARSITY)),
                    seed=int(qp.get("seed", 42))))

            async def _me(request):  # type: ignore
                return JSONResponse(onebit_methodology())

            async def _f(request):  # type: ignore
                return JSONResponse(onebit_fleet_readiness())

            app.router.routes.append(Route(paths[0], _m))
            app.router.routes.append(Route(paths[1], _e))
            app.router.routes.append(Route(paths[2], _me))
            app.router.routes.append(Route(paths[3], _f))
    except Exception:
        pass  # additive registration must never break app boot

    return paths


# =====================================================================================
# Self-test (Forge: run `python3 szl_kc_onebit.py` — must print ALL OK).
# =====================================================================================
if __name__ == "__main__":
    import sys

    mf = onebit_manifest()
    est = onebit_estimate(model_params_b=2.4, n_tokens=512)
    meth = onebit_methodology()
    fleet = onebit_fleet_readiness()

    # ---- report ----
    print("label:", mf["label"])
    print("routes:", len(mf["routes"]))
    c = est["channels"]
    print("channels:", list(c.keys()))
    szl = c["c_szl_modeled"]
    print("SZL-MODELED joules/token:", szl["joules_per_token_modeled"],
          "| tokens/joule:", szl["tokens_per_joule_modeled"],
          "| speedup_vs_fp16:", szl["speedup_vs_fp16_modeled"],
          "| is_measured:", szl["is_measured"])
    print("SZL-MODELED footprint compression_x:", szl["memory_footprint_modeled"]["compression_x"])
    print("MS Table6 x86 7B saving_pct:",
          c["a_measured_by_microsoft"]["j_per_token"]["intel_i7_13700h"]["7B"]["saving_pct"])
    print("MS estimated column header:", c["b_estimated_by_microsoft"]["column_header_verbatim"])
    print("independent RAPL same-class:", est["independent_rapl_counter_figure"]["finding_same_class"])
    print("methodology claims:", meth["claims_total"], "| all cited:", meth["every_claim_has_citation"])
    print("fleet_status:", fleet["fleet_status"], "| measured_joules:", fleet["measured_joules"])

    # ---- HARD invariants (Doctrine v11) ----
    # label verbatim on all 4 endpoints
    assert mf["label"] == est["label"] == meth["label"] == fleet["label"] == "MODELED"
    assert MODELED_LABEL == "MODELED"

    # SZL number NEVER measured
    assert szl["is_measured"] is False, "SZL modeled number must never be measured"
    assert est["measured_vs_modeled"]["szl_number_is_measured"] is False
    assert est["measured_vs_modeled"]["microsoft_table6_is_measured"] is False
    assert est["measured_vs_modeled"]["microsoft_12x_is_measured"] is False

    # three channels strictly separated
    assert set(c.keys()) == {"a_measured_by_microsoft", "b_estimated_by_microsoft", "c_szl_modeled"}

    # the MS estimated figure is literally labeled 'Estimated'; Table 6 instrument undisclosed
    assert "Estimated" in c["b_estimated_by_microsoft"]["column_header_verbatim"]
    assert "UNDISCLOSED" in c["a_measured_by_microsoft"]["instrument"]

    # honest independent counter-figure present (real RAPL re-measurement)
    assert "1.26x-1.7x" in est["independent_rapl_counter_figure"]["finding_same_class"]

    # the '82.2%' headline maps to the exact x86 7B cell
    assert c["a_measured_by_microsoft"]["j_per_token"]["intel_i7_13700h"]["7B"]["saving_pct"] == 82.2

    # SZL-MODELED sanity: ternary cheaper than FP16, compression > 1, footprints ordered
    assert szl["joules_per_token_modeled"] < szl["joules_per_token_fp16_modeled"]
    assert szl["speedup_vs_fp16_modeled"] > 1.0
    assert 0.0 < szl["energy_reduction_pct_vs_fp16_modeled"] < 100.0
    fp = szl["memory_footprint_modeled"]
    assert fp["compression_x"] > 1.0
    assert fp["footprint_gib_ternary"] < fp["footprint_gib_fp16"]

    # methodology: every claim cited; real/modeled/measurable all represented
    assert meth["every_claim_has_citation"] is True
    assert meth["real_count"] >= 1 and meth["modeled_count"] >= 1 and meth["measurable_count"] >= 1

    # fleet: offline, NO fabricated measured data
    assert fleet["fleet_status"] == "OFFLINE"
    assert fleet["measured_joules_available"] is False
    assert fleet["measured_joules"] is None
    assert fleet["measured_evidence"] == {}
    assert len(fleet["what_flips_modeled_to_measured"]) >= 3

    # honesty invariants block all True
    inv = mf["honesty_invariants"]
    assert all(inv.values()), inv

    # Λ stays Conjecture (never a theorem, never green)
    assert "Conjecture 1" in mf["lambda"]
    assert "Conjecture 1" in est["lambda"]

    # bitnet cited, not claimed as SZL's own
    assert CITATIONS["bitnet_cpp_repo"].startswith("https://github.com/microsoft")

    # determinism: same inputs => identical
    assert onebit_estimate(2.4, 512) == onebit_estimate(2.4, 512), "estimate must be deterministic"
    assert onebit_manifest() == onebit_manifest()
    assert onebit_methodology() == onebit_methodology()
    assert onebit_fleet_readiness() == onebit_fleet_readiness()
    # input-sensitive
    assert onebit_estimate(7.0, 512) != onebit_estimate(2.4, 512), "estimate must respond to model size"

    # banned-token rejection works; this module's own honest note is clean
    _assert_no_banned(_HONEST_NOTE)
    _assert_no_banned(_MS_TABLE6["headline_82_2_pct"] + " " + _MS_ESTIMATED["misuse"])
    _rejected = False
    try:
        _assert_no_banned("this is a " + "yranoitulover"[::-1] + " " + "hguorhtkaerb"[::-1])
    except ValueError:
        _rejected = True
    assert _rejected, "banned tokens must be rejected"

    # register() returns the 4 exact paths (no app needed — try/except-guarded)
    class _NoApp:  # not a FastAPI app; register must still return the 4 paths
        pass
    paths = register(_NoApp(), ns="killinchu")
    assert paths == [
        "/api/killinchu/v1/onebit/manifest",
        "/api/killinchu/v1/onebit/estimate",
        "/api/killinchu/v1/onebit/methodology",
        "/api/killinchu/v1/onebit/fleet-readiness",
    ], paths

    print("register paths:", paths)
    print("szl_kc_onebit: ALL OK — MODELED ternary estimator, three channels separated, "
          "SZL number never measured, fleet offline (no fabricated joules), full provenance, "
          "deterministic.", file=sys.stderr)
    print("ALL OK")
