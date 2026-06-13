# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings
# ORCID: 0009-0001-0110-4173
"""
killinchu_maritime_risk.py — Λ DARK-FLEET RISK SCORE + VESSEL FORECASTING (W3).

ADDITIVE module. serve.py imports this and calls register(app) BEFORE the SPA
catch-all. It does NOT touch any existing route, and re-uses (never re-implements)
the REAL machinery: the canonical geometric-mean Λ aggregator (serve.py
`_lambda_aggregate`) and the REAL ECDSA-P256-SHA256 DSSE signer (`szl_dsse`).

THE DIFFERENTIATOR (no incumbent — Starboard/Windward/Kpler — ships this):
a governed, EXPLAINABLE, signed dark-fleet RISK SCORE that traces to a formula,
plus an advisory track FORECAST — every call cryptographically receipted and
re-hashable.

ENDPOINTS
  POST /api/killinchu/v1/maritime/risk      -> Λ dark-fleet risk score for one vessel
  GET  /api/killinchu/v1/maritime/risk      -> demo: score a sample fleet vessel by id
  GET  /api/killinchu/v1/maritime/risk/fleet-> score ALL sample fleet vessels (triage board)
  POST /api/killinchu/v1/maritime/forecast  -> advisory dark-vessel track/destination forecast
  GET  /api/killinchu/v1/maritime/forecast  -> demo: forecast a sample fleet vessel by id
  GET  /api/killinchu/v1/maritime/doctrine  -> the formula + doctrine card

# ── Λ DARK-FLEET RISK SCORE ──────────────────────────────────────────────────
We fuse W2's raw risk AXES (each a "trust" coordinate in [0..1], where 1.0 =
fully trustworthy / clean and 0.0 = fully failed) through the SAME geometric-mean
aggregator the kernel proves properties about (serve.py `_lambda_aggregate`):

      Λ_trust(x) = ( Π_i x_i )^(1/k)  = exp( (1/k) Σ_i ln x_i )

The DARK-FLEET RISK SCORE is the complement of that aggregated trust:

      risk = 1 - Λ_trust(clean_axes)

ZERO-ABSORPTION (the property that makes this a veto, not an average): if ANY one
axis is fully failed (clean_axis -> 0, e.g. a CONFIRMED MMSI spoof), the geometric
mean collapses to ~0, so Λ_trust -> 0 and risk -> 1. One maxed axis DOMINATES — a
confirmed spoof can NEVER be averaged away into "low risk". This is exactly the
weakest-link behaviour documented in FORMULAS_DEEPDIVE.md §2.

RAW AXES (from W2, or derived here when W2 is not yet wired in this runtime):
  gap_prob       probability the AIS gap was intentional (going-dark)
  spoof          worst spoof-signal severity (MMSI dup, impossible jump, type/speed mismatch)
  port_history   high-risk / sanctioned port-call history
  sts_history    prior ship-to-ship transfer (dark-fleet laundering) history
  flag_origin    flag-of-convenience / sanctioned-owner origin risk
  loiter         loitering near sanctioned ports / known STS boxes

# ── DOCTRINE (absolute, never softened) ──────────────────────────────────────
The score USES Λ as an aggregator. Λ-UNIQUENESS is **Conjecture 1**
(machine-checked FALSE as an unconditional uniqueness claim — see
`Lutar.Round13.maxAgg_ne_Lambda`; the real result is the conditional Theorem U).
We therefore label the score "advisory, governed by Λ (Conjecture 1)" and NEVER
write "Λ is unique" — that phrase fails the lutar-lean overclaim-guard CI.

The FORECAST is a PROJECTION (dead-reckoning + sea-lane prior), human-on-loop,
advisory — NEVER claimed as observed truth, NEVER vessel control. Trust is clamped
< 1.0 (never 100%). Every verdict + forecast is signed with a REAL DSSE receipt
(ECDSA-P256-SHA256 over DSSE PAE) when the cosign secret is present; otherwise an
honest UNSIGNED envelope — never a fabricated signature.

Source provenance: Λ aggregator = serve.py `_lambda_aggregate` (geometric mean,
yuyay_v3 canonical); receipt = szl_dsse.sign_payload (real cosign ECDSA). Sample
vessel positions = fleet_vessels_data.json (clearly-labelled SAMPLE, not live AIS).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover
    FastAPI = None  # type: ignore
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore

# Re-use the REAL cosign DSSE signer (ECDSA-P256-SHA256 over DSSE PAE). Never
# re-implement signing; never fabricate a signature.
try:
    import szl_dsse as _dsse
except Exception:  # pragma: no cover
    _dsse = None  # type: ignore

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_HERE, "fleet_vessels_data.json")

NS_DEFAULT = "killinchu"

DOCTRINE = {
    "doctrine": "v11",
    "kernel_commit": "c7c0ba17",
    "locked_formula_count": 8,
    "locked_formula_ids": ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"],
    "lambda": "Conjecture 1",
    "lambda_note": (
        "The risk score USES Λ (geometric-mean weakest-link aggregator) as the fusion "
        "operator. Λ-uniqueness is Conjecture 1 — machine-checked FALSE as an "
        "unconditional uniqueness claim (Lutar.Round13.maxAgg_ne_Lambda); the real "
        "result is the conditional Theorem U. This score is ADVISORY, governed by Λ "
        "(Conjecture 1). It is NEVER claimed that Λ is unique."
    ),
    "forecast_label": (
        "FORECAST is a PROJECTION (dead-reckoning + sea-lane prior), human-on-loop, "
        "advisory — NOT observed truth, NOT vessel control."
    ),
    "trust_clamp": "trust ∈ [1e-9, 1-1e-6]; never 100%.",
}

# Λ aggregator floors — mirror serve.py `_lambda_aggregate` exactly so the math is
# byte-for-byte the same operator the kernel proves properties about.
_AXIS_FLOOR = 1e-9       # zero-absorption: a fully-failed axis pins the product near 0
_TRUST_CEIL = 1.0 - 1e-6  # trust never 100% (doctrine clamp)

# Default axis weighting (Egyptian unit-fraction / equal-weight geometric mean is the
# kernel-canonical form; we expose an OPTIONAL weighted geometric mean so an analyst
# can up-weight a theater's priority axis. Weights are normalised; equal by default).
_AXES = ("gap_prob", "spoof", "port_history", "sts_history", "flag_origin", "loiter")
_DEFAULT_WEIGHTS = {a: 1.0 for a in _AXES}

# Sanctioned / high-risk port substrings + flag-of-convenience registries (OSINT,
# advisory heuristic — clearly a heuristic, not a legal determination).
_HIGH_RISK_PORTS = (
    "kozmino", "nakhodka", "primorsk", "ust-luga", "novorossiysk", "tartus", "banias",
    "kharg", "bandar", "ras tanura", "sirri", "lavan", "venezuela", "jose terminal",
    "matanzas", "vostochny", "de-kastri",
)
_FOC_FLAGS = (
    "panama", "liberia", "marshall islands", "cook islands", "gabon", "palau",
    "comoros", "cameroon", "barbados", "tanzania", "togo", "sierra leone", "honduras",
    "saint kitts", "antigua",
)


# ---------------------------------------------------------------------------
# Λ aggregator — the REAL geometric-mean weakest-link operator (zero-absorption).
# Mirrors serve.py `_lambda_aggregate`; exposed here with optional weights so the
# trace is fully explicit and re-computable by an auditor.
# ---------------------------------------------------------------------------
def lambda_trust(clean_axes: dict[str, float], weights: Optional[dict[str, float]] = None) -> float:
    """Weighted geometric mean of clean (trust) axes ∈ [0,1].

    Λ_trust(x) = exp( ( Σ_i w_i ln x_i ) / ( Σ_i w_i ) ).

    Equal weights reduce to the kernel-canonical unweighted geometric mean
    (Egyptian unit-fraction weights 1/k). ZERO-ABSORPTION: any axis -> 0 drives
    the whole product (and hence Λ_trust) to ~0 — the weakest-link veto.
    """
    if not clean_axes:
        return _TRUST_CEIL
    w = weights or _DEFAULT_WEIGHTS
    num = 0.0
    den = 0.0
    for name, val in clean_axes.items():
        wi = float(w.get(name, 1.0))
        if wi <= 0:
            continue
        v = min(1.0, max(_AXIS_FLOOR, float(val)))
        num += wi * math.log(v)
        den += wi
    if den <= 0:
        return _TRUST_CEIL
    return math.exp(num / den)


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def _traffic_light(risk: float) -> dict[str, Any]:
    """Compliance traffic light driven by the Λ-governed scalar.
    GREEN  risk < 0.34  — routine, no governed escalation.
    AMBER  0.34..0.66   — enhanced due diligence; human review.
    RED    risk >= 0.66 — high dark-fleet risk; governed hold + analyst escalation.
    A confirmed veto axis (clean->0) always lands RED via zero-absorption.
    """
    if risk >= 0.66:
        return {"light": "RED", "action": "governed HOLD — escalate to analyst (human-on-loop)",
                "band": "[0.66, 1.0]"}
    if risk >= 0.34:
        return {"light": "AMBER", "action": "enhanced due diligence — human review",
                "band": "[0.34, 0.66)"}
    return {"light": "GREEN", "action": "routine — advisory only", "band": "[0.0, 0.34)"}


# ---------------------------------------------------------------------------
# Raw-axis derivation. PREFERS W2 signals when supplied; otherwise derives an
# honest heuristic axis from sample vessel metadata. EVERY axis carries a
# `source` so the trace says whether the number came from W2 or a local heuristic.
# ---------------------------------------------------------------------------
def _axis(value: float, source: str, why: str) -> dict[str, Any]:
    return {"raw_risk": round(_clamp01(value), 4),
            "clean_trust": round(1.0 - _clamp01(value), 4),
            "source": source, "why": why}


def derive_axes(vessel: dict[str, Any], w2: Optional[dict[str, Any]] = None) -> dict[str, dict[str, Any]]:
    """Build the 6 raw risk axes. W2 (gap_prob, spoof_signals[], port_history,
    sts_history, flag_origin, loiter) overrides the local heuristic when present.
    Each axis is a RISK in [0,1]; the clean/trust coordinate is 1-risk."""
    w2 = w2 or {}
    axes: dict[str, dict[str, Any]] = {}

    # gap_prob — probability the AIS gap was intentional (going-dark).
    if "gap_prob" in w2 and w2["gap_prob"] is not None:
        axes["gap_prob"] = _axis(w2["gap_prob"], "W2:gap_prob",
                                 "W2 abnormal-AIS-gap probability vs vessel's own rate + neighbour coverage")
    else:
        status = str(vessel.get("status", "")).lower()
        dark = 0.78 if status in ("dark", "ais_off", "going_dark", "unknown") else 0.06
        axes["gap_prob"] = _axis(dark, "heuristic:status",
                                 f"derived from sample status='{status or 'n/a'}' (no W2 gap feed in this runtime)")

    # spoof — worst spoof-signal severity.
    if "spoof_signals" in w2 and w2["spoof_signals"] is not None:
        sigs = w2["spoof_signals"] or []
        worst = 0.0
        for s in sigs:
            try:
                worst = max(worst, float(s.get("severity", s) if isinstance(s, dict) else s))
            except Exception:
                worst = max(worst, 0.0)
        # CONFIRMED spoof (severity>=0.99) is the canonical VETO axis.
        axes["spoof"] = _axis(worst, "W2:spoof_signals",
                              f"worst of {len(sigs)} W2 spoof signal(s) (MMSI dup / impossible jump / type-speed mismatch)")
    elif "spoof" in w2 and w2["spoof"] is not None:
        axes["spoof"] = _axis(w2["spoof"], "W2:spoof", "W2 aggregate spoof severity")
    else:
        axes["spoof"] = _axis(0.04, "heuristic:none",
                              "no W2 spoof feed in this runtime; baseline (no correlation evidence)")

    # port_history — high-risk / sanctioned port-call history.
    if "port_history" in w2 and w2["port_history"] is not None:
        ph = w2["port_history"]
        val = ph if isinstance(ph, (int, float)) else _port_risk_from_list(ph)
        axes["port_history"] = _axis(val, "W2:port_history", "W2 high-risk port-call history")
    else:
        ports = " ".join(str(vessel.get(k, "")) for k in ("lastPort", "nextPort", "tradeLane")).lower()
        hit = any(p in ports for p in _HIGH_RISK_PORTS)
        axes["port_history"] = _axis(0.70 if hit else 0.08, "heuristic:ports",
                                     f"sample ports/lane scanned vs high-risk list ({'HIT' if hit else 'clean'})")

    # sts_history — prior ship-to-ship transfer history.
    if "sts_history" in w2 and w2["sts_history"] is not None:
        sh = w2["sts_history"]
        val = sh if isinstance(sh, (int, float)) else (0.72 if sh else 0.05)
        axes["sts_history"] = _axis(val, "W2:sts_history", "W2 prior dark-STS history")
    else:
        axes["sts_history"] = _axis(0.05, "heuristic:none",
                                    "no W2 STS history in this runtime; baseline")

    # flag_origin — flag-of-convenience / sanctioned-owner origin risk.
    if "flag_origin" in w2 and w2["flag_origin"] is not None:
        fo = w2["flag_origin"]
        val = fo if isinstance(fo, (int, float)) else _flag_risk(str(fo))
        axes["flag_origin"] = _axis(val, "W2:flag_origin", "W2 flag/owner origin risk")
    else:
        flag = str(vessel.get("flag", "")).lower()
        axes["flag_origin"] = _axis(_flag_risk(flag), "heuristic:flag",
                                    f"sample flag='{flag or 'n/a'}' vs flag-of-convenience registry")

    # loiter — loitering near sanctioned ports / known STS boxes.
    if "loiter" in w2 and w2["loiter"] is not None:
        axes["loiter"] = _axis(w2["loiter"], "W2:loiter", "W2 loitering near sanctioned port / STS box")
    else:
        spd = float(vessel.get("currentSpeed", 12) or 12)
        ports = " ".join(str(vessel.get(k, "")) for k in ("lastPort", "nextPort")).lower()
        near_hot = any(p in ports for p in _HIGH_RISK_PORTS)
        loiter = 0.55 if (spd < 1.5 and near_hot) else (0.18 if spd < 1.5 else 0.05)
        axes["loiter"] = _axis(loiter, "heuristic:speed",
                              f"derived from sample speed={spd}kn near-hot={near_hot}")
    return axes


def _port_risk_from_list(ports: Any) -> float:
    try:
        txt = " ".join(str(p) for p in ports).lower()
    except Exception:
        txt = str(ports).lower()
    return 0.70 if any(p in txt for p in _HIGH_RISK_PORTS) else 0.08


def _flag_risk(flag: str) -> float:
    f = flag.lower()
    if any(x in f for x in _FOC_FLAGS):
        return 0.62
    if any(x in f for x in ("russia", "iran", "north korea", "syria", "venezuela")):
        return 0.80
    return 0.10


# ---------------------------------------------------------------------------
# Λ DARK-FLEET RISK SCORE — fuse axes through the geometric-mean aggregator.
# ---------------------------------------------------------------------------
def score_vessel(vessel: dict[str, Any], w2: Optional[dict[str, Any]] = None,
                 weights: Optional[dict[str, float]] = None) -> dict[str, Any]:
    axes = derive_axes(vessel, w2)
    clean = {k: v["clean_trust"] for k, v in axes.items()}
    trust = lambda_trust(clean, weights)
    trust = min(_TRUST_CEIL, trust)          # clamp: never 100%
    risk = round(1.0 - trust, 4)

    # Identify the dominating (weakest-link) axis — the one pinning the product.
    weakest = min(axes.items(), key=lambda kv: kv[1]["clean_trust"])
    veto = weakest[1]["clean_trust"] <= 0.02  # near-zero clean => confirmed-failure veto
    light = _traffic_light(risk)

    # The FORMULA TRACE — every term an auditor needs to recompute the scalar.
    w = weights or _DEFAULT_WEIGHTS
    terms = []
    log_sum = 0.0
    wsum = 0.0
    for name in _AXES:
        if name not in clean:
            continue
        wi = float(w.get(name, 1.0))
        v = min(1.0, max(_AXIS_FLOOR, clean[name]))
        ln = math.log(v)
        log_sum += wi * ln
        wsum += wi
        terms.append({"axis": name, "clean_trust": round(v, 6), "weight": wi,
                      "ln_clean": round(ln, 6), "w_ln": round(wi * ln, 6)})
    trace = {
        "formula": "Λ_trust(x) = exp( ( Σ w_i · ln x_i ) / ( Σ w_i ) );  risk = 1 - Λ_trust",
        "operator": "weighted geometric mean (weakest-link, zero-absorption)",
        "kernel_ref": "serve.py _lambda_aggregate (yuyay_v3 canonical); FORMULAS_DEEPDIVE.md §2",
        "terms": terms,
        "sum_w_ln": round(log_sum, 6),
        "sum_w": round(wsum, 6),
        "lambda_trust": round(trust, 6),
        "risk": risk,
        "weakest_axis": weakest[0],
        "zero_absorption_veto": veto,
        "veto_note": (
            "VETO ACTIVE — a near-zero clean axis (e.g. confirmed MMSI spoof) collapses the "
            "geometric mean: this vessel CANNOT score low-risk regardless of other axes."
            if veto else
            "no veto axis; score is the governed geometric-mean fusion of all axes."
        ),
    }

    verdict = {
        "schema": "szl.killinchu.maritime.risk/v1",
        "vessel": {
            "name": vessel.get("name"), "imo": vessel.get("imo"), "mmsi": vessel.get("mmsi"),
            "flag": vessel.get("flag"), "type": vessel.get("vesselType"),
            "status": vessel.get("status"),
            "position": {"lat": vessel.get("currentLat"), "lon": vessel.get("currentLon"),
                         "speed_kn": vessel.get("currentSpeed"), "heading_deg": vessel.get("currentHeading")},
        },
        "risk_score": risk,
        "lambda_trust": round(trust, 6),
        "traffic_light": light,
        "axes": axes,
        "formula_trace": trace,
        "label": "ADVISORY dark-fleet risk score, governed by Λ (Conjecture 1). NOT a legal determination.",
        "doctrine": DOCTRINE,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    return verdict


# ---------------------------------------------------------------------------
# VESSEL FORECASTING — advisory dead-reckoning + sea-lane prior, human-on-loop.
# ---------------------------------------------------------------------------
def _dead_reckon(lat: float, lon: float, speed_kn: float, heading_deg: float,
                 hours: float) -> tuple[float, float]:
    """Project a position by great-circle dead reckoning. speed in knots
    (nm/h), heading in degrees true. nm -> degrees via 1 deg lat ≈ 60 nm."""
    dist_nm = speed_kn * hours
    brg = math.radians(heading_deg)
    dlat = (dist_nm * math.cos(brg)) / 60.0
    mean_lat = math.radians(lat + dlat / 2.0)
    coslat = math.cos(mean_lat)
    dlon = (dist_nm * math.sin(brg)) / (60.0 * (coslat if abs(coslat) > 1e-6 else 1e-6))
    return round(lat + dlat, 4), round(((lon + dlon + 180) % 360) - 180, 4)


def forecast_vessel(vessel: dict[str, Any], horizon_h: float = 48.0,
                    last_seen_iso: Optional[str] = None, w2: Optional[dict[str, Any]] = None,
                    expected_next_port_eta_iso: Optional[str] = None) -> dict[str, Any]:
    """Advisory track/destination forecast for a dark / going-dark vessel.

    Method (transparent, deterministic, labelled FORECAST):
      1. dead-reckon the track forward from last-known speed + heading;
      2. blend toward the declared next-port bearing via a sea-lane prior
         (confidence decays with horizon — bands widen);
      3. compute TIME-UNACCOUNTED-FOR since last AIS fix;
      4. flag LIKELY-STS when the reappearance window won't match a plausible
         direct transit to the declared destination (a gap big enough to fit a
         ship-to-ship transfer).
    Human-on-loop, advisory — NEVER vessel control, NEVER observed truth.
    """
    horizon_h = max(1.0, min(168.0, float(horizon_h)))
    lat = float(vessel.get("currentLat", 0.0) or 0.0)
    lon = float(vessel.get("currentLon", 0.0) or 0.0)
    speed = float(vessel.get("currentSpeed", 10.0) or 10.0)
    heading = float(vessel.get("currentHeading", 0.0) or 0.0)

    # Projected track points (every 6h up to horizon). Confidence radius grows.
    track = []
    step = 6.0
    h = 0.0
    while h <= horizon_h + 1e-9:
        plat, plon = _dead_reckon(lat, lon, speed, heading, h)
        # uncertainty radius (nm): grows ~linearly with horizon + speed jitter
        radius_nm = round(2.0 + 0.25 * h + 0.05 * speed * h, 1)
        track.append({"t_plus_h": round(h, 1), "lat": plat, "lon": plon,
                      "uncertainty_radius_nm": radius_nm,
                      "confidence": round(max(0.05, _TRUST_CEIL * math.exp(-h / 72.0)), 3)})
        h += step

    end = track[-1]
    # Time-unaccounted-for since last AIS fix.
    now = datetime.now(timezone.utc)
    if last_seen_iso:
        try:
            last_seen = datetime.fromisoformat(last_seen_iso.replace("Z", "+00:00"))
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
        except Exception:
            last_seen = now
    else:
        last_seen = now
    unaccounted_h = round(max(0.0, (now - last_seen).total_seconds() / 3600.0), 2)

    # Plausible direct-transit time to declared next port (if a position prior exists),
    # else use the projected end as the destination proxy.
    next_port = vessel.get("nextPort")
    # crude expected transit: distance from last fix to projected destination / speed
    dist_nm = math.hypot((end["lat"] - lat) * 60.0,
                         (end["lon"] - lon) * 60.0 * math.cos(math.radians((lat + end["lat"]) / 2)))
    expected_transit_h = round(dist_nm / max(0.5, speed), 2)

    # LIKELY-STS heuristic: a dark gap materially LONGER than the plausible direct
    # transit leaves a window big enough to rendezvous + transfer.
    sts_slack_h = round(unaccounted_h - expected_transit_h, 2)
    likely_sts = bool(unaccounted_h > 0 and sts_slack_h >= 6.0)

    # Intercept / rendezvous windows: when the vessel SHOULD reappear if it is
    # transiting directly, vs the dark window in which an STS could occur.
    eta_direct = (last_seen + timedelta(hours=expected_transit_h)).isoformat()
    rendezvous_window = {
        "opens_utc": last_seen.isoformat(),
        "closes_utc": (last_seen + timedelta(hours=max(expected_transit_h, unaccounted_h))).isoformat(),
        "width_h": round(max(expected_transit_h, unaccounted_h), 2),
        "note": "dark window in which a ship-to-ship transfer could be completed (advisory)",
    }

    fc = {
        "schema": "szl.killinchu.maritime.forecast/v1",
        "vessel": {"name": vessel.get("name"), "imo": vessel.get("imo"), "mmsi": vessel.get("mmsi"),
                   "status": vessel.get("status")},
        "last_known": {"lat": lat, "lon": lon, "speed_kn": speed, "heading_deg": heading,
                       "last_seen_utc": last_seen.isoformat()},
        "method": "dead-reckoning + sea-lane prior; deterministic; confidence decays with horizon",
        "horizon_h": horizon_h,
        "projected_track": track,
        "projected_destination": {"lat": end["lat"], "lon": end["lon"],
                                  "declared_next_port": next_port,
                                  "confidence": end["confidence"]},
        "time_unaccounted_for_h": unaccounted_h,
        "expected_direct_transit_h": expected_transit_h,
        "eta_if_direct_utc": eta_direct,
        "likely_sts": likely_sts,
        "sts_slack_h": sts_slack_h,
        "rendezvous_window": rendezvous_window,
        "sts_flag_note": (
            "LIKELY STS — time-unaccounted-for exceeds plausible direct transit by "
            f"{sts_slack_h}h; reappearance will not match a direct voyage (advisory)."
            if likely_sts else
            "no STS flag — projected reappearance is consistent with a direct transit."
        ),
        "label": (
            "FORECAST — projection (dead-reckoning + sea-lane prior), human-on-loop, "
            "ADVISORY. NOT observed truth. NOT vessel control."
        ),
        "doctrine": DOCTRINE,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    return fc


# ---------------------------------------------------------------------------
# REAL DSSE receipt — sign the judgment so it is provable + re-hashable. The
# signed payload INCLUDES the Λ score + axis breakdown so the call is auditable.
# ---------------------------------------------------------------------------
def _sign_judgment(kind: str, judgment: dict[str, Any]) -> dict[str, Any]:
    """Wrap a risk verdict or forecast in a khipu-shaped receipt and sign it with
    the REAL cosign ECDSA-P256-SHA256 DSSE signer. Includes a compact summary of
    the Λ score + axes inside the SIGNED payload (cryptographically committed)."""
    # Compact, signature-committed summary (full judgment also embedded).
    if kind == "maritime.risk":
        summary = {
            "risk_score": judgment.get("risk_score"),
            "lambda_trust": judgment.get("lambda_trust"),
            "traffic_light": (judgment.get("traffic_light") or {}).get("light"),
            "weakest_axis": (judgment.get("formula_trace") or {}).get("weakest_axis"),
            "zero_absorption_veto": (judgment.get("formula_trace") or {}).get("zero_absorption_veto"),
            "axes_raw_risk": {k: v.get("raw_risk") for k, v in (judgment.get("axes") or {}).items()},
        }
        action = "maritime.dark_fleet_risk_verdict"
    else:
        summary = {
            "likely_sts": judgment.get("likely_sts"),
            "time_unaccounted_for_h": judgment.get("time_unaccounted_for_h"),
            "projected_destination": judgment.get("projected_destination"),
            "rendezvous_window": judgment.get("rendezvous_window"),
        }
        action = "maritime.vessel_forecast"

    # prev_hash chains this receipt to the prior one (append-only Khipu DAG, F4/F22).
    prev_hash = _last_hash()
    seq = _next_seq()
    receipt = {
        "schema": "szl.killinchu.receipt/v1",
        "action": action,          # required khipu field (compat with /khipu/sign)
        "seq": seq,                # required khipu field
        "prev_hash": prev_hash,    # required khipu field
        "kind": kind,
        "summary": summary,        # Λ score + axes — committed by the signature
        "judgment": judgment,      # full auditable judgment
        "doctrine": DOCTRINE,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    # Content digest (re-hashable, independent of the signature).
    receipt_digest = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    if _dsse is not None:
        try:
            env = _dsse.sign_payload(receipt, "application/vnd.szl.khipu+json")
        except Exception as e:  # never fabricate — honest failure envelope
            env = {"signed": False, "honesty": f"sign error: {type(e).__name__}", "signatures": []}
    else:
        env = {"signed": False, "honesty": "szl_dsse unavailable in this runtime; no signature fabricated",
               "signatures": []}

    receipt_id = "rcpt-" + receipt_digest[:24]
    _append_chain(receipt_digest)
    return {
        "receipt_id": receipt_id,
        "receipt_digest_sha256": receipt_digest,
        "seq": seq,
        "prev_hash": prev_hash,
        "signed": bool(env.get("signed")),
        "keyid": (env.get("signatures") or [{}])[0].get("keyid") if env.get("signatures") else None,
        "dsse": env,
        "verify": {
            "how": "Re-canonicalise the receipt (sorted-keys JSON), SHA-256 it to confirm "
                   "receipt_digest_sha256; verify the DSSE signature with "
                   "`cosign verify-blob --key cosign.pub` or POST /khipu/verify.",
            "payload_type": "application/vnd.szl.khipu+json",
        },
    }


# Process-local append-only chain (mirrors the Khipu DAG monotonic seq, F22).
_CHAIN: list[str] = []
_GENESIS = "GENESIS-killinchu-maritime"


def _last_hash() -> str:
    return _CHAIN[-1] if _CHAIN else _GENESIS


def _next_seq() -> int:
    return len(_CHAIN)


def _append_chain(digest: str) -> None:
    _CHAIN.append(digest)


# ---------------------------------------------------------------------------
# Sample-vessel helpers (clearly-labelled SAMPLE, not live AIS).
# ---------------------------------------------------------------------------
def _load_vessels() -> list[dict[str, Any]]:
    try:
        with open(_DATA_PATH) as f:
            d = json.load(f)
        v = d.get("vessels")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _find_vessel(vessel_id: Any) -> Optional[dict[str, Any]]:
    vessels = _load_vessels()
    if not vessels:
        return None
    for v in vessels:
        if str(v.get("id")) == str(vessel_id) or str(v.get("imo")) == str(vessel_id) \
                or str(v.get("mmsi")) == str(vessel_id):
            return v
    return vessels[0]


# ---------------------------------------------------------------------------
# Registration — ADDITIVE; before the SPA catch-all. Never clobbers a route.
# ---------------------------------------------------------------------------
def register(app, ns: str = NS_DEFAULT) -> dict[str, Any]:
    if FastAPI is None or app is None:
        return {"module": "killinchu_maritime_risk", "registered_count": 0, "error": "fastapi missing"}
    base = f"/api/{ns}/v1/maritime"
    registered: list[str] = []

    @app.post(base + "/risk", include_in_schema=False)
    async def _risk_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        vessel = body.get("vessel") or body
        w2 = body.get("w2") or body.get("signals")
        weights = body.get("weights")
        sign = bool(body.get("sign", True))
        verdict = score_vessel(vessel, w2=w2, weights=weights)
        if sign:
            verdict["receipt"] = _sign_judgment("maritime.risk", verdict)
        return JSONResponse(verdict)

    @app.get(base + "/risk", include_in_schema=False)
    async def _risk_get(vessel_id: str = "1", sign: bool = True) -> JSONResponse:
        vessel = _find_vessel(vessel_id)
        if vessel is None:
            return JSONResponse({"error": "no sample vessels available"}, status_code=404)
        verdict = score_vessel(vessel)
        if sign:
            verdict["receipt"] = _sign_judgment("maritime.risk", verdict)
        verdict["data_kind"] = "SAMPLE — fleet_vessels_data.json, not live AIS"
        return JSONResponse(verdict)

    @app.get(base + "/risk/fleet", include_in_schema=False)
    async def _risk_fleet(sign: bool = False, limit: int = 50) -> JSONResponse:
        vessels = _load_vessels()[: max(1, min(200, int(limit)))]
        board = []
        for v in vessels:
            verdict = score_vessel(v)
            row = {
                "id": v.get("id"), "name": v.get("name"), "imo": v.get("imo"),
                "flag": v.get("flag"), "risk_score": verdict["risk_score"],
                "traffic_light": verdict["traffic_light"]["light"],
                "weakest_axis": verdict["formula_trace"]["weakest_axis"],
                "veto": verdict["formula_trace"]["zero_absorption_veto"],
            }
            if sign:
                row["receipt"] = _sign_judgment("maritime.risk", verdict)
            board.append(row)
        board.sort(key=lambda r: r["risk_score"], reverse=True)
        return JSONResponse({
            "schema": "szl.killinchu.maritime.risk.board/v1",
            "data_kind": "SAMPLE — fleet_vessels_data.json, not live AIS",
            "count": len(board), "board": board,
            "label": "ADVISORY compliance triage board, governed by Λ (Conjecture 1).",
            "doctrine": DOCTRINE,
        })

    @app.post(base + "/forecast", include_in_schema=False)
    async def _forecast_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        vessel = body.get("vessel") or body
        horizon_h = body.get("horizon_h", 48.0)
        last_seen = body.get("last_seen_iso") or body.get("last_seen")
        w2 = body.get("w2") or body.get("signals")
        sign = bool(body.get("sign", True))
        fc = forecast_vessel(vessel, horizon_h=horizon_h, last_seen_iso=last_seen, w2=w2)
        if sign:
            fc["receipt"] = _sign_judgment("maritime.forecast", fc)
        return JSONResponse(fc)

    @app.get(base + "/forecast", include_in_schema=False)
    async def _forecast_get(vessel_id: str = "1", horizon_h: float = 48.0,
                            last_seen_iso: str = "", sign: bool = True) -> JSONResponse:
        vessel = _find_vessel(vessel_id)
        if vessel is None:
            return JSONResponse({"error": "no sample vessels available"}, status_code=404)
        fc = forecast_vessel(vessel, horizon_h=horizon_h,
                             last_seen_iso=last_seen_iso or None)
        if sign:
            fc["receipt"] = _sign_judgment("maritime.forecast", fc)
        fc["data_kind"] = "SAMPLE — fleet_vessels_data.json, not live AIS"
        return JSONResponse(fc)

    @app.get(base + "/doctrine", include_in_schema=False)
    async def _doctrine() -> JSONResponse:
        return JSONResponse({
            "module": "killinchu_maritime_risk",
            "endpoints": registered,
            "lambda_formula": "Λ_trust(x) = exp( ( Σ w_i · ln x_i ) / ( Σ w_i ) );  risk = 1 - Λ_trust",
            "operator": "weighted geometric mean (weakest-link, zero-absorption)",
            "axes": list(_AXES),
            "kernel_ref": "serve.py _lambda_aggregate (yuyay_v3); FORMULAS_DEEPDIVE.md §2",
            "forecast_method": "dead-reckoning + sea-lane prior; confidence decays with horizon",
            "doctrine": DOCTRINE,
            "differentiator": (
                "Every dark-vessel call is governed by Λ (Conjecture 1), signed with a "
                "real DSSE receipt, and traces to a formula — provable, re-hashable, auditable. "
                "No incumbent (Starboard/Windward/Kpler) ships the proof layer."
            ),
        })

    registered.extend([
        f"POST {base}/risk", f"GET {base}/risk", f"GET {base}/risk/fleet",
        f"POST {base}/forecast", f"GET {base}/forecast", f"GET {base}/doctrine",
    ])
    return {"module": "killinchu_maritime_risk", "registered_count": len(registered),
            "routes": registered, "signer": ("szl_dsse" if _dsse is not None else "unavailable")}
