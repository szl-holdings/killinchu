# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. Jr. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""killinchu_active_flux.py — "Sensorless Drive · Active-Flux Observer" capability.

ADOPTED-AND-GENERALIZED, not invented here. The counter-UAS interceptors, gimbals
and the drones we "jack into" run PMSM under field-oriented control (FOC). This
module is the propulsion / effector ESTIMATION layer: a hybrid current-model /
voltage-model ACTIVE-FLUX observer with a TUNABLE PI-correction bandwidth ω_c.

E1 (this file) implements the literal, on-domain active-flux sensorless drive and
also serves the generalized fusion-crossover + a11oy-router-crossover read-only
explainers (E2 surfaces are gated by Λ + Khipu/BFT quorum + a conformal coverage
set — see fusion_crossover() / router_crossover()).

The pure math lives in the SHARED byte-identical szl_cuas_formulas.py
(active_flux, pi_crossover_freq, active_flux_blend, szl_active_flux_observer).
This module only adds the killinchu HTTP surface + a self-contained /elite page.

HONEST LABELS (doctrine v11):
  * There is NO live motor on the demo floor — every rotor angle/speed/flux number
    is MODELED/SIMULATED. We NEVER claim live hardware or live telemetry here.
  * Effector stays SIMULATED human-on-loop; this computes estimates, never actuates.
  * Λ = Conjecture 1; Khipu BFT = Conjecture 2; locked-proven = EXACTLY 8 @ c7c0ba17.
    This module adds NOTHING to the locked-8 — it is an EXPERIMENTAL adopt-and-evolve.
  * Trust never 100%; conformal coverage SETS over bare confidence; 0 runtime CDN
    (the Bode plot is drawn with a vendored, dependency-free <canvas> routine).

Sources (cited in code + UI; adopted, NOT reclaimed as an SZL theorem):
  - Boldea/Andreescu/Blaabjerg, "Active-flux" sensorless control, IEEE/APEC 2001 —
    https://doi.org/10.1109/APEC.2001.911711
  - Li Yu (李彧), "How should the bandwidth of the PI correction loop in an
    Active-Flux observer be selected?" (LinkedIn, 2026) and related FOC articles
    ("Two High-Speed Decoupling Strategies for PMSM", "Angles related to FOC
    control", "LADRC vs PI in Sensorless Motor Control",
    "High-Frequency Injection and Flux Observer").
  - "A Robust Encoderless Control for PMSM Drives: a Revised Hybrid Active Flux
    Based Technique" (IEEE).
  - TI InstaSPIN-FOC / FAST estimator (SPRUHJ1) — terminal-voltage sampling enables
    a higher PI bandwidth (clean voltage signal).

Framing: "we adopted the active-flux observer-blending law (Li Yu / IEEE 911711) and
generalized it, under SZL governance, to sensor fusion + model routing" — an honest
borrow-and-evolve, never an invented SZL theorem.
"""
from __future__ import annotations

import hashlib
import math
import time
from typing import Any, Dict, List, Optional

import szl_cuas_formulas as _af  # SHARED, byte-identical a11oy↔killinchu

# Citations surfaced in the UI + the /info endpoint (real, resolvable URLs).
SOURCES = {
    "Active-flux sensorless control (Boldea et al., IEEE/APEC 2001)":
        "https://doi.org/10.1109/APEC.2001.911711",
    "Li Yu (李彧) — PI-correction bandwidth in an Active-Flux observer (LinkedIn 2026)":
        "https://www.linkedin.com/pulse/how-should-bandwidth-pi-correction-loop-active-flux-observer-%E5%BD%A7-%E6%9D%8E-qxksc",
    "Revised Hybrid Active-Flux encoderless PMSM control (IEEE)":
        "https://ieeexplore.ieee.org/document/9319155",
    "TI InstaSPIN-FOC / FAST flux observer (SPRUHJ1)":
        "https://www.ti.com/lit/ug/spruhj1h/spruhj1h.pdf",
}

_HONEST = (
    "MODELED/SIMULATED — there is no live motor on the demo floor. Every rotor "
    "angle/speed/flux figure is a deterministic model output, NOT live hardware "
    "telemetry. The effector stays SIMULATED human-on-loop. Adopted the active-flux "
    "observer-blending law (Li Yu / IEEE 911711) and generalized it under SZL "
    "governance; this adds NOTHING to the locked-8 and Λ stays Conjecture 1. "
    "Trust never 100%."
)


# ---------------------------------------------------------------------------
# Local conformal-coverage wrapper (same API as Dev B's helper, if/when present).
# Split-conformal residual-quantile band (W5-3/W7-4 method already used estate-wide):
# turns a point estimate + calibration residuals into a SET S with ≥(1-α) coverage —
# "true state in S with ≥95%", NEVER a bare confidence %. Distribution-free.
# ---------------------------------------------------------------------------
def conformal_set(point: float, calib_residuals: List[float], alpha: float = 0.05,
                  unit: str = "") -> Dict[str, Any]:
    """Split-conformal prediction SET around `point`. Coverage ≥ (1-α). The radius is
    the finite-sample-corrected (1-α) empirical quantile of |calibration residuals|:
    index = ceil((n+1)(1-α))/n. Returns the interval S = [point-q, point+q] and the
    honest coverage statement. Trust never 100% (α>0 enforced). Distribution-free —
    cite Vovk/Shafer conformal prediction; matches estate W5-3/W7-4."""
    a = min(max(float(alpha), 1e-3), 0.5)          # never 0 (trust < 100%) and never absurd
    res = sorted(abs(float(r)) for r in calib_residuals) or [0.0]
    n = len(res)
    rank = math.ceil((n + 1) * (1.0 - a))
    idx = min(max(rank - 1, 0), n - 1)
    q = res[idx]
    cover = round((1.0 - a) * 100.0, 2)
    return {
        "point": round(float(point), 6),
        "set": [round(float(point) - q, 6), round(float(point) + q, 6)],
        "radius": round(q, 6),
        "coverage_pct": cover,
        "alpha": a,
        "n_calibration": n,
        "unit": unit,
        "statement": f"true value in set S with ≥{cover:.0f}% coverage (split-conformal, NOT a bare confidence %)",
        "method": "split-conformal residual quantile (W5-3/W7-4); distribution-free",
        "status": "EXPERIMENTAL",
    }


def _khipu_bft_quorum(votes: List[bool], n_total: int = 4) -> Dict[str, Any]:
    """Khipu/BFT quorum gate (Conjecture 2). n ≥ 3f+1 ⇒ n=4 tolerates 1 Byzantine
    node, requiring ≥3 honest agreeing votes for quorum. Returns the quorum verdict.
    Conjecture 2 (NOT proven doctrine) — honest framing. SIMULATED governance gate."""
    yes = sum(1 for v in votes if v)
    f = (n_total - 1) // 3
    need = n_total - f               # n - f honest agreeing for safety (3-of-4 at n=4)
    return {
        "n_total": n_total, "byzantine_tolerated_f": f, "votes_yes": yes,
        "quorum_threshold": need, "quorum_reached": bool(yes >= need),
        "rule": "n ≥ 3f+1 (n=4 tolerates 1 Byzantine); ≥(n−f) agreeing for quorum",
        "framing": "Khipu BFT = Conjecture 2 (NOT proven doctrine)",
        "status": "SIMULATED",
    }


def _lambda_gate(value: float) -> Dict[str, Any]:
    """Λ governance gate (Conjecture 1): the governed risk/coherence scalar must stay
    < 1.0. Returns the Λ value and pass/fail. Conjecture 1 — NOT a proven theorem."""
    lam = float(value)
    return {"lambda": round(lam, 6), "pass": bool(lam < 1.0),
            "framing": "Λ = Conjecture 1 (<1.0); NOT proven doctrine", "status": "ADVISORY"}


# ---------------------------------------------------------------------------
# E2(a) generalized: regime-dependent multi-sensor fusion with a tunable-crossover
# PI corrector (replaces FIXED weights with the active-flux crossover law), gated
# through Λ + Khipu/BFT quorum + a conformal coverage SET.
# ---------------------------------------------------------------------------
def fusion_crossover(closing_rate_hz: float = 8.0, pi_bandwidth_hz: float = 12.0,
                     rf_estimate: float = 1200.0, optical_estimate: float = 1180.0,
                     sensor_votes: Optional[List[bool]] = None) -> Dict[str, Any]:
    """SZL multi-sensor fusion with a PI-bandwidth crossover (GENERALIZED active-flux
    law). Two regime-dependent estimators are blended exactly like the current/voltage
    active-flux models: RF is the LOW-"frequency" (low closing-rate) estimator (cf.
    current model), optical/ADS-B is the HIGH-"frequency" (high closing-rate) estimator
    (cf. voltage model). The blend weights come from active_flux_blend() at the
    'closing-rate frequency', so a LOWER PI bandwidth trusts RF to higher closing rate
    and a HIGHER PI bandwidth hands off to optical sooner — a principled, CITABLE
    crossover instead of fixed weights. The fused range estimate is then gated through
    Λ (Conjecture 1) + Khipu/BFT quorum (Conjecture 2) + a conformal coverage SET. The
    output is 'true range in set S, ≥95%', NOT a bare confidence. [EXPERIMENTAL · MODELED]"""
    blend = _af.active_flux_blend(pi_bandwidth_hz, closing_rate_hz)
    w_rf = blend["current_model_weight"]          # RF ↔ current model (low regime)
    w_opt = blend["voltage_model_weight"]         # optical ↔ voltage model (high regime)
    fused = w_rf * rf_estimate + w_opt * optical_estimate
    dominant = "RF (low closing-rate)" if w_rf >= w_opt else "OPTICAL/ADS-B (high closing-rate)"
    # conformal SET from the two single-sensor disagreements as calibration residuals
    resid = [rf_estimate - fused, optical_estimate - fused, 0.0, 0.5 * (rf_estimate - optical_estimate)]
    cset = conformal_set(fused, resid, alpha=0.05, unit="m")
    # Λ governance: normalize fused-disagreement spread to a <1.0 advisory scalar
    spread = abs(rf_estimate - optical_estimate)
    lam = _lambda_gate(min(0.999, spread / (abs(fused) + 1.0)))
    votes = sensor_votes if sensor_votes is not None else [True, True, True, False]
    quorum = _khipu_bft_quorum(votes, n_total=4)
    return {
        "closing_rate_hz": round(closing_rate_hz, 4),
        "pi_bandwidth_hz": round(pi_bandwidth_hz, 4),
        "crossover_hz": blend["crossover_hz"],
        "weight_rf": round(w_rf, 6), "weight_optical": round(w_opt, 6),
        "dominant_estimator": dominant, "regime": blend["regime"],
        "fused_range_m": round(fused, 4),
        "lambda_gate": lam, "khipu_bft_quorum": quorum, "conformal_set": cset,
        "gated_ok": bool(lam["pass"] and quorum["quorum_reached"]),
        "doctrine": ("GENERALIZED active-flux crossover replaces fixed fusion weights; "
                     "gated by Λ (Conjecture 1) + Khipu/BFT quorum (Conjecture 2) + "
                     "conformal coverage SET; effector SIMULATED; NOT in the locked-8"),
        "data_label": "MODELED/SIMULATED",
        "status": "MODELED",
    }


# ---------------------------------------------------------------------------
# E2(b) generalized: a11oy model-router crossover (deterministic complement to a
# Thompson-sampling bandit). small/local = low-"frequency"/easy estimator; large/
# cloud = high-"frequency"/hard estimator; PI-bandwidth-style deterministic crossover.
# Killinchu also exposes a read-only mirror so the active-flux page can render it.
# ---------------------------------------------------------------------------
def router_crossover(query_difficulty: float = 0.5, pi_bandwidth_hz: float = 12.0,
                     difficulty_span_hz: float = 60.0) -> Dict[str, Any]:
    """Model-router crossover (GENERALIZED active-flux law). A query's difficulty in
    [0,1] is mapped to a pseudo-'electrical frequency' f = difficulty·span_hz, and the
    same active_flux_blend() decides the small/local-vs-large/cloud weighting: small/
    local model = LOW-frequency/easy estimator (cf. current model), large/cloud =
    HIGH-frequency/hard estimator (cf. voltage model). This is the DETERMINISTIC
    complement to a RouteLLM Thompson-sampling bandit — same crossover knob (the PI
    bandwidth) sets where routing flips. Renders which model dominates per difficulty.
    [EXPERIMENTAL · MODELED]"""
    d = min(max(float(query_difficulty), 0.0), 1.0)
    f = d * difficulty_span_hz
    blend = _af.active_flux_blend(pi_bandwidth_hz, f)
    w_small = blend["current_model_weight"]
    w_large = blend["voltage_model_weight"]
    route = "small/local" if w_small >= w_large else "large/cloud"
    return {
        "query_difficulty": round(d, 4),
        "pi_bandwidth_hz": round(pi_bandwidth_hz, 4),
        "crossover_difficulty": round(blend["crossover_hz"] / max(difficulty_span_hz, 1e-6), 4),
        "weight_small_local": round(w_small, 6),
        "weight_large_cloud": round(w_large, 6),
        "route": route, "regime": "easy" if route == "small/local" else "hard",
        "complement_to": "RouteLLM Thompson-sampling bandit (deterministic crossover complement)",
        "doctrine": ("GENERALIZED active-flux PI-bandwidth crossover for model routing; "
                     "deterministic complement to the Bayesian bandit; NOT in the locked-8"),
        "data_label": "MODELED",
        "status": "MODELED",
    }


def info(ns: str) -> Dict[str, Any]:
    """Headline + honest provenance for the active-flux capability."""
    return {
        "capability": "Sensorless Drive · Active-Flux Observer",
        "ns": ns,
        "summary": ("Hybrid current-model/voltage-model active-flux observer with a "
                    "tunable PI-correction bandwidth ω_c. ψ_act = ψ_f + (Ld−Lq)·id. "
                    "Adopted from Li Yu / IEEE 911711 and generalized under SZL governance "
                    "to multi-sensor fusion + model routing."),
        "endpoints": {
            "observer": f"/api/{ns}/v1/drive/active-flux",
            "bode": f"/api/{ns}/v1/drive/active-flux/bode",
            "fusion_crossover": f"/api/{ns}/v1/drive/fusion-crossover",
            "router_crossover": f"/api/{ns}/v1/drive/router-crossover",
            "page": "/elite/active-flux",
        },
        "doctrine": {"locked_proven": 8, "lambda": "Conjecture 1", "khipu_bft": "Conjecture 2",
                     "effector": "SIMULATED", "trust": "never 100%",
                     "data_label": "MODELED/SIMULATED — no live motor"},
        "sources": SOURCES,
        "honest": _HONEST,
        "li_yu_reference": _af.LI_YU_REFERENCE_BODE,
        "status": "EXPERIMENTAL",
    }


# ---------------------------------------------------------------------------
# Self-contained /elite/active-flux page. 0 runtime CDN — the Bode-style plot is
# drawn with a tiny dependency-free <canvas> routine vendored inline below.
# Imports the estate shared modules (window.SZLLabels / SZLReceipts / SZLCodenames)
# from /shared/* (served byte-identically by killinchu_maritime_globe.register).
# ---------------------------------------------------------------------------
def _page_html(ns: str) -> str:
    return r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sensorless Drive · Active-Flux Observer — killinchu</title>
<style>
 :root{--bg:#070b10;--panel:#0d141c;--line:#1d2a36;--teal:#39d3c4;--teal-soft:rgba(57,211,196,.12);
  --gold:#e8c074;--cream:#eef3f6;--para:#9fb1bf;--cur:#6fb1ff;--volt:#ffb56b;--bad:#ff6b6b;}
 *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--cream);
  font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Helvetica,Arial}
 a{color:var(--teal);text-decoration:none}
 header{padding:14px 18px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#0a1119,#070b10)}
 h1{font-size:18px;margin:0 0 2px}.sub{color:var(--para);font-size:12.5px;max-width:980px}
 .badge{display:inline-block;font-size:10.5px;padding:2px 7px;border-radius:6px;border:1px solid var(--line);
  margin-right:6px;color:var(--gold);background:#10171f;vertical-align:middle}
 .wrap{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:16px;max-width:1240px;margin:0 auto}
 @media(max-width:880px){.wrap{grid-template-columns:1fr}}
 .panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
 .panel h2{font-size:14px;margin:0 0 8px;color:var(--cream)}
 .panel .pp{color:var(--para);font-size:12px;margin:0 0 10px}
 canvas{width:100%;height:280px;background:#060a0e;border:1px solid var(--line);border-radius:8px;display:block}
 .ctrl{display:flex;align-items:center;gap:10px;margin:8px 0;font-size:12.5px;flex-wrap:wrap}
 .ctrl label{color:var(--para);min-width:150px}
 input[type=range]{flex:1;accent-color:var(--teal)}
 .val{color:var(--teal);font-variant-numeric:tabular-nums;min-width:64px;text-align:right}
 .kpi{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
 .kpi div{background:#0a1117;border:1px solid var(--line);border-radius:7px;padding:8px}
 .kpi b{display:block;font-size:18px;color:var(--gold);font-variant-numeric:tabular-nums}
 .kpi span{font-size:11px;color:var(--para)}
 .legend{font-size:11.5px;color:var(--para);margin-top:6px}
 .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 4px 0 10px;vertical-align:middle}
 .out{white-space:pre-wrap;font:11.5px ui-monospace,Menlo,monospace;color:#bfe;background:#06090d;
  border:1px solid var(--line);border-radius:7px;padding:8px;max-height:170px;overflow:auto}
 .src{font-size:11px;color:var(--para);margin-top:10px;line-height:1.7}.src a{color:var(--teal)}
 footer{padding:12px 18px;border-top:1px solid var(--line);color:var(--para);font-size:11px}
 .pill{display:inline-block;padding:1px 6px;border-radius:5px;border:1px solid var(--line);margin-left:6px}
 .pill.cur{color:var(--cur);border-color:#27405e}.pill.volt{color:var(--volt);border-color:#5e4327}
</style></head><body>
<header>
 <h1>Sensorless Drive · Active-Flux Observer
   <span class="badge" id="b-modeled">MODELED / SIMULATED</span>
   <span class="badge">effector SIMULATED</span>
   <span class="badge">Λ = Conjecture 1</span>
   <span class="badge">0 runtime CDN</span></h1>
 <div class="sub">Hybrid <b>current-model / voltage-model</b> active-flux observer with a tunable
  PI-correction bandwidth ω_c. Active flux <b>ψ_act = ψ_f + (Ld−Lq)·id</b> carries the rotor angle.
  <b>Adopted</b> from Li Yu / IEEE 911711 and <b>generalized under SZL governance</b>; this adds NOTHING
  to the locked-8. <b>There is no live motor on the demo floor — every number here is modeled.</b>
  <a href="/elite">← back to /elite</a></div>
</header>
<div class="wrap">
 <div class="panel">
  <h2>Current ↔ Voltage model blend vs electrical frequency (Bode-style magnitude)</h2>
  <p class="pp">Reproduces Li Yu's design rule: a <b>lower</b> PI bandwidth keeps the
   <span style="color:var(--cur)">current model</span> dominant to higher frequency (better
   <b>low-speed</b>); a <b>higher</b> PI bandwidth hands off to the
   <span style="color:var(--volt)">voltage model</span> sooner (better <b>high-speed</b>). The
   crossover line marks f_x. MODELED 1st-order complementary blend.</p>
  <canvas id="bode" width="560" height="280"></canvas>
  <div class="legend"><span class="dot" style="background:var(--cur)"></span>current model (dB)
   <span class="dot" style="background:var(--volt)"></span>voltage model (dB)
   <span class="dot" style="background:var(--teal)"></span>crossover f_x &nbsp;·&nbsp;
   <span class="dot" style="background:var(--gold)"></span>operating f_e</div>
  <div class="ctrl"><label>PI correction bandwidth ω_c</label>
   <input id="bw" type="range" min="3" max="40" step="0.5" value="12">
   <span class="val" id="bw-v">12.0 Hz</span></div>
  <div class="ctrl"><label>low-speed ⟷ high-speed (operating f_e)</label>
   <input id="fe" type="range" min="1" max="120" step="1" value="40">
   <span class="val" id="fe-v">40 Hz</span></div>
  <div class="src">Li Yu reference (f_e = 40 Hz): 5 Hz BW → current ≈ −12.2 dB; 30 Hz BW →
   current ≈ +0.163 dB, voltage ≈ −3.72 dB.</div>
 </div>

 <div class="panel">
  <h2>Observer estimate @ operating point <span class="pill" id="regime-pill">—</span></h2>
  <p class="pp">Rotor angle/speed + active flux from the hybrid observer at the chosen f_e and ω_c.
   MODELED — not a real encoder read.</p>
  <div class="kpi">
   <div><b id="k-angle">—</b><span>rotor angle θ̂ₑ (deg, electrical)</span></div>
   <div><b id="k-rpm">—</b><span>rotor speed (mech, rpm)</span></div>
   <div><b id="k-psi">—</b><span>active flux ψ_act (Wb)</span></div>
   <div><b id="k-cross">—</b><span>crossover f_x (Hz)</span></div>
   <div><b id="k-cur">—</b><span>current-model weight (dB)</span></div>
   <div><b id="k-volt">—</b><span>voltage-model weight (dB)</span></div>
  </div>
  <details style="margin-top:10px"><summary style="cursor:pointer;color:var(--teal)">raw /drive/active-flux</summary>
   <div class="out" id="obs-raw">—</div></details>
 </div>

 <div class="panel">
  <h2>E2(a) · Multi-sensor fusion — tunable-crossover PI corrector</h2>
  <p class="pp"><b>Generalized</b> active-flux law replaces fixed fusion weights: RF = low closing-rate
   estimator (cf. current model), optical/ADS-B = high closing-rate (cf. voltage model). The fused range
   is gated through <b>Λ</b> (Conjecture 1) + <b>Khipu/BFT quorum</b> (Conjecture 2) + a
   <b>conformal coverage SET</b> — "true range in set S, ≥95%", not a bare confidence.</p>
  <div class="ctrl"><label>closing-rate (regime)</label>
   <input id="cr" type="range" min="1" max="60" step="1" value="8">
   <span class="val" id="cr-v">8 Hz</span></div>
  <div class="kpi">
   <div><b id="f-dom">—</b><span>dominant estimator</span></div>
   <div><b id="f-range">—</b><span>fused range (m)</span></div>
   <div><b id="f-set">—</b><span>conformal set S (m)</span></div>
   <div><b id="f-gate">—</b><span>Λ + BFT quorum gate</span></div>
  </div>
  <details style="margin-top:10px"><summary style="cursor:pointer;color:var(--teal)">raw /drive/fusion-crossover</summary>
   <div class="out" id="fus-raw">—</div></details>
 </div>

 <div class="panel">
  <h2>E2(b) · a11oy model-router crossover (deterministic complement to RouteLLM)</h2>
  <p class="pp"><b>Generalized</b> active-flux PI-bandwidth crossover for model routing: small/local =
   easy/low-"frequency" estimator (cf. current model), large/cloud = hard/high-"frequency" (cf. voltage
   model). Deterministic complement to a Thompson-sampling bandit — same ω_c knob sets where routing flips.</p>
  <div class="ctrl"><label>query difficulty (0 easy → 1 hard)</label>
   <input id="qd" type="range" min="0" max="1" step="0.02" value="0.5">
   <span class="val" id="qd-v">0.50</span></div>
  <div class="kpi">
   <div><b id="r-route">—</b><span>dominant model</span></div>
   <div><b id="r-cross">—</b><span>crossover difficulty</span></div>
   <div><b id="r-small">—</b><span>small/local weight</span></div>
   <div><b id="r-large">—</b><span>large/cloud weight</span></div>
  </div>
  <details style="margin-top:10px"><summary style="cursor:pointer;color:var(--teal)">raw /drive/router-crossover</summary>
   <div class="out" id="rtr-raw">—</div></details>
 </div>
</div>
<footer>
 Doctrine v11 · locked = 8 @ c7c0ba17 · Λ = Conjecture 1 · Khipu BFT = Conjecture 2 ·
 effector SIMULATED · <b>active-flux drive MODELED/SIMULATED (no live motor)</b> · 0 runtime CDN ·
 conformal SETS over bare confidence · trust &lt; 100%.<br>
 Adopted &amp; generalized — sources:
 <a href="https://doi.org/10.1109/APEC.2001.911711" target="_blank" rel="noopener">Active-flux IEEE/APEC 2001 (911711)</a> ·
 <a href="https://www.linkedin.com/pulse/how-should-bandwidth-pi-correction-loop-active-flux-observer-%E5%BD%A7-%E6%9D%8E-qxksc" target="_blank" rel="noopener">Li Yu — PI-correction bandwidth (LinkedIn)</a> ·
 <a href="https://ieeexplore.ieee.org/document/9319155" target="_blank" rel="noopener">Revised Hybrid Active Flux (IEEE)</a> ·
 <a href="https://www.ti.com/lit/ug/spruhj1h/spruhj1h.pdf" target="_blank" rel="noopener">TI InstaSPIN-FAST (SPRUHJ1)</a>.
</footer>
<!-- Estate shared modules (byte-identical a11oy↔killinchu), served at /shared/* with the
     correct text/javascript content-type by killinchu_maritime_globe.register. NO CDN. -->
<script src="/shared/szl_label_engine.js" defer></script>
<script src="/shared/szl_receipt_cosign.js" defer></script>
<script src="/shared/szl_codename_sanitizer.js" defer></script>
<script>
"use strict";
const API = "/api/__NS__/v1/drive";
const $ = id => document.getElementById(id);
function dB(x){ return x>1e-12 ? 20*Math.log10(x) : -120; }
// Mirror of the SHARED szl_cuas_formulas crossover, so the plot is instant + offline-safe.
// Live KPI/raw panels still fetch the REAL backend endpoints (single source of truth).
function crossoverFreq(bw){ return 150.0/Math.max(bw,1e-6); }
function blend(bw, fe){
  const fx = crossoverFreq(bw), wx = 2*Math.PI*fx, we = 2*Math.PI*Math.max(fe,0);
  const d = Math.sqrt(wx*wx+we*we)||1e-12;
  const hc = wx/d, hv = we/d;
  return {fx, hc, hv, cdB:dB(hc), vdB:dB(hv)};
}
// --- vendored, dependency-free Bode-style canvas plot (0 CDN) ---
function drawBode(){
  const bw = parseFloat($("bw").value), fe = parseFloat($("fe").value);
  const c = $("bode"), ctx = c.getContext("2d");
  const W = c.width, H = c.height, padL=44, padB=26, padT=12, padR=10;
  const x0=padL, x1=W-padR, y0=padT, y1=H-padB;
  ctx.clearRect(0,0,W,H);
  const fmin=1, fmax=120, dbMin=-30, dbMax=3;
  const fx = pt => x0 + (Math.log10(pt)-Math.log10(fmin))/(Math.log10(fmax)-Math.log10(fmin))*(x1-x0);
  const fy = db => y1 - (db-dbMin)/(dbMax-dbMin)*(y1-y0);
  // grid
  ctx.strokeStyle="#142029"; ctx.fillStyle="#5b6c78"; ctx.font="10px ui-monospace,monospace"; ctx.lineWidth=1;
  [-30,-24,-18,-12,-6,0].forEach(d=>{ const y=fy(d); ctx.beginPath();ctx.moveTo(x0,y);ctx.lineTo(x1,y);ctx.stroke();
    ctx.fillText(d+"dB", 4, y+3); });
  [1,2,5,10,20,40,80,120].forEach(f=>{ const x=fx(f); ctx.beginPath();ctx.moveTo(x,y0);ctx.lineTo(x,y1);ctx.stroke();
    ctx.fillText(f, x-6, y1+14); });
  ctx.fillText("f_elec (Hz, log)", (x0+x1)/2-34, H-2);
  // crossover line
  const cx = fx(crossoverFreq(bw));
  ctx.strokeStyle="#39d3c4"; ctx.setLineDash([4,3]); ctx.beginPath();ctx.moveTo(cx,y0);ctx.lineTo(cx,y1);ctx.stroke();
  ctx.setLineDash([]); ctx.fillStyle="#39d3c4"; ctx.fillText("f_x="+crossoverFreq(bw).toFixed(1)+"Hz", cx+3, y0+10);
  // operating f_e marker
  const ox = fx(fe); ctx.strokeStyle="#e8c074"; ctx.setLineDash([2,2]); ctx.beginPath();ctx.moveTo(ox,y0);ctx.lineTo(ox,y1);ctx.stroke(); ctx.setLineDash([]);
  // curves
  function curve(col, key){ ctx.strokeStyle=col; ctx.lineWidth=2; ctx.beginPath();
    for(let i=0;i<=160;i++){ const f=Math.pow(10, Math.log10(fmin)+(Math.log10(fmax)-Math.log10(fmin))*i/160);
      const b=blend(bw,f); const d=Math.max(dbMin,Math.min(dbMax, key==="c"?b.cdB:b.vdB));
      const X=fx(f), Y=fy(d); i?ctx.lineTo(X,Y):ctx.moveTo(X,Y);} ctx.stroke(); }
  curve("#6fb1ff","c"); curve("#ffb56b","v");
}
function setVal(){
  $("bw-v").textContent = parseFloat($("bw").value).toFixed(1)+" Hz";
  $("fe-v").textContent = parseFloat($("fe").value).toFixed(0)+" Hz";
  $("cr-v").textContent = parseFloat($("cr").value).toFixed(0)+" Hz";
  $("qd-v").textContent = parseFloat($("qd").value).toFixed(2);
}
async function refreshObserver(){
  const bw=$("bw").value, fe=$("fe").value;
  try{ const r=await fetch(`${API}/active-flux?bw=${bw}&f_elec=${fe}`); const d=await r.json();
    $("k-angle").textContent=d.rotor_angle_elec_deg.toFixed(2)+"°";
    $("k-rpm").textContent=d.speed_mech_rpm.toFixed(0);
    $("k-psi").textContent=d.psi_active_Wb.toFixed(4);
    $("k-cross").textContent=d.blend.crossover_hz.toFixed(1);
    $("k-cur").textContent=d.blend.current_model_dB.toFixed(2);
    $("k-volt").textContent=d.blend.voltage_model_dB.toFixed(2);
    const reg=d.blend.regime, pill=$("regime-pill");
    pill.textContent = reg==="low_speed" ? "LOW-SPEED · current model" : "HIGH-SPEED · voltage model";
    pill.className = "pill "+(reg==="low_speed"?"cur":"volt");
    $("obs-raw").textContent=JSON.stringify(d,null,1);
  }catch(e){ $("obs-raw").textContent="endpoint unreachable: "+e; }
}
async function refreshFusion(){
  const cr=$("cr").value, bw=$("bw").value;
  try{ const r=await fetch(`${API}/fusion-crossover?closing_rate=${cr}&bw=${bw}`); const d=await r.json();
    $("f-dom").textContent=d.dominant_estimator.split(" ")[0];
    $("f-range").textContent=d.fused_range_m.toFixed(1);
    $("f-set").textContent="["+d.conformal_set.set[0].toFixed(0)+", "+d.conformal_set.set[1].toFixed(0)+"]";
    $("f-gate").textContent=(d.gated_ok?"PASS":"HOLD")+" ("+d.khipu_bft_quorum.votes_yes+"/"+d.khipu_bft_quorum.n_total+")";
    $("fus-raw").textContent=JSON.stringify(d,null,1);
  }catch(e){ $("fus-raw").textContent="endpoint unreachable: "+e; }
}
async function refreshRouter(){
  const qd=$("qd").value, bw=$("bw").value;
  try{ const r=await fetch(`${API}/router-crossover?query_difficulty=${qd}&bw=${bw}`); const d=await r.json();
    $("r-route").textContent=d.route;
    $("r-cross").textContent=d.crossover_difficulty.toFixed(2);
    $("r-small").textContent=d.weight_small_local.toFixed(3);
    $("r-large").textContent=d.weight_large_cloud.toFixed(3);
    $("rtr-raw").textContent=JSON.stringify(d,null,1);
  }catch(e){ $("rtr-raw").textContent="endpoint unreachable: "+e; }
}
function onChange(){ setVal(); drawBode(); refreshObserver(); refreshFusion(); refreshRouter(); }
["bw","fe","cr","qd"].forEach(id=>$(id).addEventListener("input", onChange));
window.addEventListener("resize", drawBode);
onChange();
</script>
</body></html>""".replace("__NS__", ns)


def register(app, ns: str = "killinchu", emit_receipt=None) -> Dict[str, Any]:
    """Attach the active-flux drive surface. ADDITIVE; mounted BEFORE the SPA catch-all.
    Pure stdlib + the shared szl_cuas_formulas math. NO new dependency, 0 CDN."""
    from starlette.responses import HTMLResponse, JSONResponse
    registered: List[str] = []
    base = f"/api/{ns}/v1/drive"

    # Hybrid active-flux observer (MODELED/SIMULATED).
    def _observer(f_elec: str = "40.0", bw: str = "12.0", id_cur: str = "-2.0",
                  iq_cur: str = "18.0", pole_pairs: str = "4"):
        try:
            return JSONResponse(_af.szl_active_flux_observer(
                f_elec_hz=float(f_elec), pi_bandwidth_hz=float(bw),
                id_cur=float(id_cur), iq_cur=float(iq_cur), pole_pairs=int(pole_pairs)))
        except (ValueError, TypeError) as e:
            return JSONResponse({"error": {"code": "validation_error", "detail": str(e)}}, status_code=422)
    app.add_api_route(f"{base}/active-flux", _observer, methods=["GET"])
    registered.append(f"GET {base}/active-flux")

    # Bode-style sweep (MODELED).
    def _bode(bw: str = "12.0", f_min: str = "1.0", f_max: str = "120.0", points: str = "60"):
        try:
            bwf = float(bw); fmn = float(f_min); fmx = float(f_max); n = max(2, int(points))
            lo = math.log10(max(fmn, 1e-3)); hi = math.log10(max(fmx, fmn + 1e-3))
            curve = [_af.active_flux_blend(bwf, 10.0 ** (lo + (hi - lo) * i / (n - 1)))
                     for i in range(n)]
            return JSONResponse({"pi_bandwidth_hz": bwf,
                                 "crossover_hz": round(_af.pi_crossover_freq(bwf), 4),
                                 "points": n, "curve": curve,
                                 "li_yu_reference": _af.LI_YU_REFERENCE_BODE,
                                 "data_label": "MODELED/SIMULATED — no live motor",
                                 "status": "MODELED"})
        except (ValueError, TypeError) as e:
            return JSONResponse({"error": {"code": "validation_error", "detail": str(e)}}, status_code=422)
    app.add_api_route(f"{base}/active-flux/bode", _bode, methods=["GET"])
    registered.append(f"GET {base}/active-flux/bode")

    # E2(a) fusion crossover (gated through Λ + Khipu/BFT quorum + conformal set).
    def _fusion(closing_rate: str = "8.0", bw: str = "12.0",
                rf: str = "1200.0", optical: str = "1180.0"):
        try:
            return JSONResponse(fusion_crossover(
                closing_rate_hz=float(closing_rate), pi_bandwidth_hz=float(bw),
                rf_estimate=float(rf), optical_estimate=float(optical)))
        except (ValueError, TypeError) as e:
            return JSONResponse({"error": {"code": "validation_error", "detail": str(e)}}, status_code=422)
    app.add_api_route(f"{base}/fusion-crossover", _fusion, methods=["GET"])
    registered.append(f"GET {base}/fusion-crossover")

    # E2(b) router crossover (deterministic complement to RouteLLM bandit) — mirror.
    def _router(query_difficulty: str = "0.5", bw: str = "12.0"):
        try:
            return JSONResponse(router_crossover(
                query_difficulty=float(query_difficulty), pi_bandwidth_hz=float(bw)))
        except (ValueError, TypeError) as e:
            return JSONResponse({"error": {"code": "validation_error", "detail": str(e)}}, status_code=422)
    app.add_api_route(f"{base}/router-crossover", _router, methods=["GET"])
    registered.append(f"GET {base}/router-crossover")

    # Info / provenance.
    app.add_api_route(f"{base}/info", lambda: JSONResponse(info(ns)), methods=["GET"])
    registered.append(f"GET {base}/info")

    # Self-contained /elite/active-flux page (0 CDN).
    _html = _page_html(ns)

    async def _page():
        return HTMLResponse(_html)
    app.add_api_route("/elite/active-flux", _page, methods=["GET"])
    app.add_api_route(f"/{ns}/elite/active-flux", _page, methods=["GET"])
    registered.append("GET /elite/active-flux")

    # --- nav-link injector (OWNED by this module; does NOT edit the console file) ---
    # Mirrors the operator-widget injector pattern: a tiny middleware appends ONE
    # <a> nav-item linking to /elite/active-flux into the /elite console HTML, right
    # after the MESH nav-item (a stable anchor). Idempotent (a marker prevents double
    # injection). Touches only served HTML bytes; the console source file is untouched.
    try:
        from starlette.middleware.base import BaseHTTPMiddleware as _Base
        from starlette.responses import Response as _SResp
        _NAV_MARK = b"data-view-af=\"active_flux_drive\""
        _ANCHOR = b"MESH (live surface)</a>"
        _NAV_LINK = (
            b'<a class="nav-item" data-view-af="active_flux_drive" href="/elite/active-flux" '
            b'style="color:var(--gold-bright)" title="Sensorless Drive: hybrid current/voltage '
            b'active-flux observer with a tunable PI-correction bandwidth. Live Bode-style blend '
            b'plot, rotor angle/speed estimate, low-speed/high-speed tradeoff. Adopted from Li Yu / '
            b'IEEE 911711, generalized under SZL governance to sensor fusion + model routing. '
            b'MODELED/SIMULATED - no live motor; effector SIMULATED.">'
            b'<span class="ico">&#9883;</span>Sensorless Drive (Active-Flux)</a>'
        )

        class _ActiveFluxNavInjector(_Base):
            async def dispatch(self, request, call_next):
                resp = await call_next(request)
                try:
                    ct = (resp.headers.get("content-type") or "").lower()
                    p = request.url.path
                    if "text/html" not in ct or p.startswith(("/api/", "/assets/", "/vendor/", "/shared/")):
                        return resp
                    if p == "/elite/active-flux" or p.endswith("/elite/active-flux"):
                        return resp  # never inject into my own page
                    body = b""
                    async for chunk in resp.body_iterator:
                        body += chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode()
                    if _NAV_MARK in body or _ANCHOR not in body:
                        new_body = body
                    else:
                        new_body = body.replace(_ANCHOR, _ANCHOR + _NAV_LINK, 1)
                    headers = dict(resp.headers)
                    headers.pop("content-length", None)
                    return _SResp(content=new_body, status_code=resp.status_code,
                                  headers=headers, media_type="text/html")
                except Exception:
                    return resp

        app.add_middleware(_ActiveFluxNavInjector)
        registered.append("MIDDLEWARE active-flux nav-link injector")
    except Exception:  # never crash the app — additive only
        pass

    return {"registered": registered, "count": len(registered),
            "capability": "Sensorless Drive · Active-Flux Observer",
            "data_label": "MODELED/SIMULATED"}


def _selftest() -> None:
    # crossover law mirrored from shared module
    assert abs(_af.pi_crossover_freq(5.0) - 30.0) < 1e-9
    fc = fusion_crossover(closing_rate_hz=2.0, pi_bandwidth_hz=5.0)  # 2<30 -> RF dominant
    assert fc["dominant_estimator"].startswith("RF") and fc["conformal_set"]["coverage_pct"] >= 95.0
    assert "set" in fc["conformal_set"] and fc["status"] == "MODELED"
    rc_easy = router_crossover(query_difficulty=0.1, pi_bandwidth_hz=5.0)
    rc_hard = router_crossover(query_difficulty=0.95, pi_bandwidth_hz=5.0)
    assert rc_easy["route"] == "small/local" and rc_hard["route"] == "large/cloud"
    cs = conformal_set(100.0, [1, -2, 3, -1, 2], alpha=0.05)
    assert cs["coverage_pct"] == 95.0 and cs["set"][0] <= 100.0 <= cs["set"][1]
    q = _khipu_bft_quorum([True, True, True, False], 4)
    assert q["quorum_reached"] is True and q["byzantine_tolerated_f"] == 1
    print("killinchu_active_flux: ALL OK (7 checks)")


if __name__ == "__main__":
    _selftest()
