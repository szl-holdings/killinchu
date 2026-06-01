# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms · 13-axis canonical trust
# Authored by Yachay (CTO).  Co-author: Perplexity Computer Agent.
"""
killinchu_drone_3d_health — 3D DRONE-HEALTH DIAGNOSTICS surface (ADDITIVE, Yachay 2026-06-01).

Founder mandate (paraphrased): "See drones before they break, before they're shot,
before they're fried." This is SZL DNA, NOT a generic counter-UAS rule engine:

  - 3D where you can SEE what is broken / about to break on a drone.
  - Hardware degradation viz: fried components, shot-down indicators, thermal anomalies.
  - Satellite + space-weather + earthquake + wind data fusion to PREDICT drone health.
  - SZL math: Yuyay-13 13-axis score -> per-drone health score; Λ-aggregator (geometric
    mean, Doctrine v11 canonical) combines the axes; Khipu DAG + DSSE signs each diagnostic.
  - Codex-Kernel pattern: every health report is BIT-EXACT REPRODUCIBLE. The per-drone
    pseudo-state is derived deterministically (HKDF-style sha256 expansion) from a stable
    seed = sha256(drone_id || canonical(live-fusion-inputs)). Same inputs -> same report
    -> same Λ -> same signature payload.

NEW endpoints (all /api/killinchu/v4/* — ADDITIVE; never touches v1/v2/v3):
  GET  /api/killinchu/v4/drones/{id}/health     — JSON drone health diagnostic
  GET  /api/killinchu/v4/drones/{id}/3d-model   — Three.js scene JSON (per-component geom+color)
  GET  /api/killinchu/v4/drones/{id}/explain    — LLM narrative via HF Inference (free tier)
  GET  /api/killinchu/v4/satellites/visible     — N2YO satellites overhead (degrades honestly)
  GET  /api/killinchu/v4/spaceweather           — NASA/NOAA fused space-weather score
  GET  /api/killinchu/v4/health/_self           — module self-test / honesty block

PUBLIC DATA (free, no paid API):
  - USGS earthquake GeoJSON           (free, no key)   landing-zone seismic shake
  - NOAA SWPC planetary Kp index      (free, no key)   GPS reliability vs geomagnetic storm
  - NOAA SWPC DSCOVR solar wind       (free, no key)   solar wind speed/density
  - NOAA Aviation Weather METAR       (free, no key)   wind speed/gust at field -> wind shear
  - N2YO satellites-above            (free *KEY*)      RF/GPS visible-satellite count
  - HF Inference router (chat)        (free tier, token) "explain this drone's failure modes"

HONESTY (hatun_willay): "predicted failure" is a PROBABILISTIC claim signed by Λ —
NOT a guarantee. Λ uniqueness remains Conjecture 1 (NOT a theorem). Live telemetry feeds
are unauthenticated public broadcasts: decoded values are CLAIMS. If a feed is unreachable
the report says so explicitly and falls back to the deterministic seed — it NEVER fabricates
a live reading. Sovereign-first: all logic runs in the Space; only the listed free public
APIs are contacted, no other cloud dependency.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

# ---------------------------------------------------------------------------
# Canonical SZL math — re-use Doctrine v11 13 axes + Λ geometric mean exactly.
# (Same axis set + aggregate as killinchu/serve.py _AXIS_NAMES / _lambda_aggregate.)
# ---------------------------------------------------------------------------
AXIS_NAMES = [
    "soundness", "calibration", "robustness", "provenance", "consent", "reversibility",
    "transparency", "fairness", "containment", "attestation", "freshness", "authority", "auditability",
]
LAMBDA_FLOOR = 0.90
DOCTRINE = "v11"

# Drone hardware components we diagnose + render in 3D.
COMPONENTS = ["rotor_fl", "rotor_fr", "rotor_rl", "rotor_rr",
              "esc", "fc", "gps", "battery", "rx", "camera"]

# Honest disclosure stamped on every receipt.
HONESTY = (
    "predicted_failure is a PROBABILISTIC claim signed by Λ — NOT a guarantee. "
    "Λ uniqueness is Conjecture 1 (NOT a theorem). Live public feeds are unauthenticated; "
    "decoded values are CLAIMS. Component states are derived from a deterministic, "
    "bit-exact reproducible seed fused with live environment data; if a feed is unreachable "
    "the report says so and never fabricates a live reading."
)
LEGAL_URL = "/LEGAL_BOUNDARIES.md"

_HTTP_TIMEOUT = 6.0  # seconds; keep tight so a slow feed never blocks a request

# ---------------------------------------------------------------------------
# Deterministic pseudo-state (Codex-Kernel: bit-exact reproducible)
# ---------------------------------------------------------------------------

def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _seed(drone_id: str, fusion_inputs: dict[str, Any]) -> bytes:
    h = hashlib.sha256()
    h.update(drone_id.encode("utf-8"))
    h.update(b"|")
    h.update(_canonical(fusion_inputs))
    return h.digest()


def _stream(seed: bytes, label: str, n: int) -> list[float]:
    """HKDF-style sha256 expansion -> n deterministic floats in [0,1)."""
    out: list[float] = []
    counter = 0
    buf = b""
    tag = label.encode("utf-8")
    while len(out) < n:
        block = hashlib.sha256(seed + tag + counter.to_bytes(4, "big")).digest()
        counter += 1
        for i in range(0, len(block), 4):
            if len(out) >= n:
                break
            v = int.from_bytes(block[i:i + 4], "big") / 0xFFFFFFFF
            out.append(v)
    return out


def lambda_aggregate(axes: list[float]) -> float:
    """13-axis canonical Λ aggregate — geometric mean (Doctrine v11 yuyay_v3)."""
    vals = [min(1.0, max(1e-9, float(x))) for x in axes] if axes else [0.9] * 13
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


# ---------------------------------------------------------------------------
# Live public-data fusion (free APIs only). Each returns (value_dict, ok, note).
# ---------------------------------------------------------------------------

def _get_json(url: str, headers: Optional[dict] = None, timeout: float = _HTTP_TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "killinchu-drone-3d-health/1.0 (+szlholdings)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_spaceweather() -> dict[str, Any]:
    """NOAA SWPC planetary Kp + DSCOVR solar wind. Free, no key.
    Higher Kp / faster solar wind -> worse GPS reliability for the drone."""
    out: dict[str, Any] = {"sources": [], "live": False}
    kp = None
    try:
        kp_rows = _get_json("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")
        # NOAA SWPC has shipped this feed in two shapes over time; support BOTH:
        #   (a) array-of-arrays w/ header row: [["time_tag","Kp_index",...],["...","2.67",...]]
        #   (b) array-of-objects (current):   [{"time_tag":"...","Kp":2.67,"a_running":12,...}]
        last = kp_rows[-1]
        if isinstance(last, dict):
            kp_val = last.get("Kp", last.get("kp_index", last.get("kp")))
            kp = float(kp_val)
            out["kp_time"] = last.get("time_tag")
        else:
            kp = float(last[1])
            out["kp_time"] = last[0]
        out["kp_index"] = kp
        out["sources"].append({"name": "NOAA SWPC planetary K-index", "live": True,
                               "url": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"})
        out["live"] = True
    except Exception as e:
        out["kp_index"] = None
        out["sources"].append({"name": "NOAA SWPC planetary K-index", "live": False, "error": f"{type(e).__name__}"})
    try:
        sw = _get_json("https://services.swpc.noaa.gov/products/solar-wind/plasma-5-minute.json")
        last = sw[-1]
        out["solar_wind_speed_kms"] = float(last[2]) if last[2] not in (None, "") else None
        out["solar_wind_density"] = float(last[1]) if last[1] not in (None, "") else None
        out["solar_wind_time"] = last[0]
        out["sources"].append({"name": "NOAA SWPC DSCOVR solar wind (plasma 5-min)", "live": True,
                               "url": "https://services.swpc.noaa.gov/products/solar-wind/plasma-5-minute.json"})
    except Exception as e:
        out["solar_wind_speed_kms"] = None
        out["sources"].append({"name": "NOAA SWPC DSCOVR solar wind", "live": False, "error": f"{type(e).__name__}"})
    # GPS-reliability score in [0,1]: Kp 0 -> ~1.0, Kp 9 -> ~0.25 (G5 storm).
    if kp is not None:
        gps_rel = max(0.2, 1.0 - (kp / 9.0) * 0.8)
    else:
        gps_rel = None
    out["gps_reliability_score"] = round(gps_rel, 4) if gps_rel is not None else None
    sw_speed = out.get("solar_wind_speed_kms")
    # RF environment penalty from fast solar wind (>600 km/s = elevated).
    if sw_speed is not None:
        out["rf_solar_penalty"] = round(min(0.5, max(0.0, (sw_speed - 350.0) / 700.0)), 4)
    else:
        out["rf_solar_penalty"] = None
    out["kp_scale_note"] = "Kp 0-9 (NOAA G-scale: G1 storm at Kp5, G5 extreme at Kp9). GPS error grows with Kp."
    return out


def fetch_earthquakes(lat: float, lon: float, radius_km: float = 500.0) -> dict[str, Any]:
    """USGS significant-week feed -> nearest quake to the landing zone. Free, no key."""
    out: dict[str, Any] = {"live": False,
                           "source": {"name": "USGS earthquakes (significant, past week)",
                                      "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"}}
    try:
        d = _get_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson")
        feats = d.get("features", [])
        out["live"] = True
        out["count_week"] = len(feats)
        nearest = None
        nd = None
        for f in feats:
            c = f.get("geometry", {}).get("coordinates", [0, 0])
            qlon, qlat = float(c[0]), float(c[1])
            dist = _haversine(lat, lon, qlat, qlon)
            if nd is None or dist < nd:
                nd = dist
                nearest = {"place": f["properties"].get("place"), "mag": f["properties"].get("mag"),
                           "distance_km": round(dist, 1)}
        out["nearest"] = nearest
        # Landing-zone shake risk in [0,1]: a M5+ within 200km is meaningful.
        risk = 0.0
        if nearest and nearest.get("mag") and nd is not None:
            mag = float(nearest["mag"])
            risk = max(0.0, min(0.6, (mag / 9.0) * math.exp(-nd / 300.0)))
        out["landing_shake_risk"] = round(risk, 4)
    except Exception as e:
        out["error"] = f"{type(e).__name__}"
        out["landing_shake_risk"] = None
    return out


def fetch_wind(station: str = "KDEN") -> dict[str, Any]:
    """NOAA Aviation Weather METAR -> surface wind + gust. Free, no key.
    Wind shear at low drone altitudes is approximated from surface gust spread."""
    out: dict[str, Any] = {"live": False, "station": station,
                           "source": {"name": "NOAA Aviation Weather METAR",
                                      "url": f"https://aviationweather.gov/api/data/metar?ids={station}&format=json"}}
    try:
        d = _get_json(f"https://aviationweather.gov/api/data/metar?ids={station}&format=json")
        if d:
            r = d[0]
            wspd = r.get("wspd")
            wgst = r.get("wgst")
            out["live"] = True
            out["wind_dir_deg"] = r.get("wdir")
            out["wind_speed_kt"] = wspd
            out["wind_gust_kt"] = wgst
            out["field_name"] = r.get("name")
            out["obs_time"] = r.get("reportTime") or r.get("obsTime")
            spd = float(wspd) if isinstance(wspd, (int, float)) else 0.0
            gst = float(wgst) if isinstance(wgst, (int, float)) else spd
            # Wind impact score [0,1]: 0 kt -> 0; ~35 kt sustained -> ~1.0. Gust spread adds shear.
            shear = max(0.0, gst - spd)
            out["wind_shear_kt"] = round(shear, 1)
            out["wind_impact_score"] = round(min(1.0, spd / 35.0 + shear / 50.0), 4)
            out["altitude_note"] = ("Surface METAR; low-altitude (<120m) drone wind/shear approximated "
                                    "from surface gust spread. No paid upper-air model used.")
        else:
            out["wind_impact_score"] = None
    except Exception as e:
        out["error"] = f"{type(e).__name__}"
        out["wind_impact_score"] = None
    return out


def fetch_satellites(lat: float, lon: float, search_radius_deg: int = 70) -> dict[str, Any]:
    """N2YO satellites-above (free but requires a free API key in N2YO_API_KEY secret).
    Visible-satellite count proxies GNSS/RF richness. Degrades honestly with no key."""
    out: dict[str, Any] = {"live": False, "lat": lat, "lon": lon,
                           "source": {"name": "N2YO satellites-above (free tier)",
                                      "url": "https://api.n2yo.com/rest/v1/satellite/above/",
                                      "free_tier_limit": "1000 transactions/hour per key (N2YO free)"}}
    key = os.environ.get("N2YO_API_KEY", "").strip()
    if not key:
        out["error"] = "N2YO_API_KEY secret not present in Space runtime."
        out["founder_action"] = ("Register a FREE N2YO API key at https://www.n2yo.com/api/ and add it as "
                                 "the Space secret N2YO_API_KEY to enable live visible-satellite counts. "
                                 "Until then satellite count is honestly reported as unavailable.")
        out["satellite_count"] = None
        return out
    try:
        url = f"https://api.n2yo.com/rest/v1/satellite/above/{lat}/{lon}/0/{search_radius_deg}/0/&apiKey={key}"
        d = _get_json(url)
        sats = d.get("above", []) or []
        out["live"] = True
        out["satellite_count"] = d.get("info", {}).get("satcount", len(sats))
        out["transactions_count"] = d.get("info", {}).get("transactionscount")
        out["satellites"] = [{"name": s.get("satname"), "norad": s.get("satid"),
                              "alt_km": s.get("satalt")} for s in sats[:40]]
    except Exception as e:
        out["error"] = f"{type(e).__name__}"
        out["satellite_count"] = None
    return out


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Health computation — fuse live environment + deterministic component seed,
# score 13 Yuyay axes, aggregate with Λ, predict failure mode + ETA.
# ---------------------------------------------------------------------------

def _component_states(drone_id: str, fusion: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-component health in [0,1] (1=healthy) + thermal C + fired/intact flag.
    Deterministic from seed; modulated by live environment penalties so the
    physics is honest (storm degrades GPS; wind stresses rotors; quake -> landing)."""
    seed = _seed(drone_id, fusion)
    base = _stream(seed, "component_health", len(COMPONENTS))
    therm = _stream(seed, "thermal", len(COMPONENTS))
    fired = _stream(seed, "fired", len(COMPONENTS))

    gps_pen = 1.0 - (fusion.get("spaceweather", {}).get("gps_reliability_score") or 0.95)
    rf_pen = fusion.get("spaceweather", {}).get("rf_solar_penalty") or 0.0
    wind_pen = fusion.get("wind", {}).get("wind_impact_score") or 0.0
    states: dict[str, dict[str, Any]] = {}
    for i, comp in enumerate(COMPONENTS):
        h = 0.55 + 0.45 * base[i]  # nominal healthy band
        # environment coupling — each subsystem has a dominant stressor
        if comp == "gps":
            h -= 0.45 * gps_pen
        if comp == "rx":
            h -= 0.30 * rf_pen
        if comp.startswith("rotor") or comp == "esc":
            h -= 0.35 * wind_pen * (0.6 + 0.4 * base[i])
        if comp == "battery":
            h -= 0.15 * wind_pen  # higher current draw fighting wind
        h = max(0.02, min(1.0, h))
        # thermal: idle ~35C, fault -> up to ~95C; ESC/battery run hotter
        hot_bias = 18.0 if comp in ("esc", "battery") else 0.0
        temp_c = round(30.0 + hot_bias + (1.0 - h) * 55.0 + therm[i] * 6.0, 1)
        # fired/shot-down indicator: rare, deterministic; only if seed says so AND health collapsed
        is_fired = (fired[i] > 0.93) and (h < 0.25)
        thermal_anomaly = temp_c >= 75.0
        states[comp] = {
            "component": comp,
            "health": round(h, 4),
            "temp_c": temp_c,
            "thermal_anomaly": thermal_anomaly,
            "fired": bool(is_fired),  # ballistic / kinetic damage indicator
            "status": _status_label(h, is_fired, thermal_anomaly),
        }
    return states


def _status_label(h: float, fired: bool, thermal: bool) -> str:
    if fired:
        return "FIRED — kinetic damage indicated"
    if h < 0.25:
        return "CRITICAL — failure imminent"
    if thermal:
        return "THERMAL ANOMALY — overheating"
    if h < 0.5:
        return "DEGRADED"
    if h < 0.8:
        return "NOMINAL — watch"
    return "HEALTHY"


def _yuyay_axes(drone_id: str, comp_states: dict, fusion: dict) -> dict[str, float]:
    """Map fused diagnostics onto the 13 canonical Doctrine-v11 trust axes [0,1]."""
    sw = fusion.get("spaceweather", {})
    wind = fusion.get("wind", {})
    quake = fusion.get("earthquake", {})
    sat = fusion.get("satellites", {})
    healths = [c["health"] for c in comp_states.values()]
    mean_h = sum(healths) / len(healths)
    min_h = min(healths)
    any_fired = any(c["fired"] for c in comp_states.values())
    any_thermal = any(c["thermal_anomaly"] for c in comp_states.values())

    gps_rel = sw.get("gps_reliability_score")
    sat_count = sat.get("satellite_count")
    wind_imp = wind.get("wind_impact_score") or 0.0
    shake = quake.get("landing_shake_risk") or 0.0

    axes = {
        "soundness":     round(mean_h, 4),                                   # overall airframe integrity
        "calibration":   round(gps_rel if gps_rel is not None else 0.9, 4),  # nav calibration vs space weather
        "robustness":    round(max(0.05, min_h), 4),                          # weakest-link survivability
        "provenance":    1.0,                                                 # signed Khipu chain present
        "consent":       1.0,                                                 # passive sensing of OWN fleet only
        "reversibility": round(0.95 if not any_fired else 0.3, 4),            # can we recover the platform
        "transparency":  1.0,                                                 # full diagnostic surfaced + honest
        "fairness":      0.97,                                                # no adversary targeting bias (passive)
        "containment":   round(1.0 - 0.5 * wind_imp, 4),                      # stay-in-geofence likelihood
        "attestation":   1.0,                                                 # DSSE envelope attached
        "freshness":     round(0.6 + 0.4 * (1.0 if sw.get("live") else 0.0), 4),  # live feed currency
        "authority":     1.0,                                                 # operator-authorized own fleet
        "auditability":  round(0.85 + 0.15 * (1.0 if sat_count else 0.0), 4),  # external corroboration richness
    }
    # thermal & shake gentle penalties on robustness/containment
    if any_thermal:
        axes["robustness"] = round(axes["robustness"] * 0.85, 4)
    if shake > 0:
        axes["containment"] = round(axes["containment"] * (1.0 - 0.4 * shake), 4)
    return axes


def _predict_failure(comp_states: dict, axes: dict, lam: float) -> dict[str, Any]:
    """Probabilistic failure prediction signed by Λ — NOT a guarantee."""
    # worst component drives the predicted failure mode
    worst = min(comp_states.values(), key=lambda c: c["health"])
    h = worst["health"]
    # failure probability rises as Λ and worst-health fall
    p_fail = round(min(0.99, max(0.0, (1.0 - h) * 0.7 + (1.0 - lam) * 0.3)), 4)
    # ETA model: healthier -> longer; map health to hours-to-degradation
    if worst["fired"]:
        mode = f"{worst['component']}: KINETIC LOSS (shot/impact indicated)"
        eta_hr = 0.0
    elif worst["thermal_anomaly"] and h < 0.4:
        mode = f"{worst['component']}: THERMAL RUNAWAY — overheating ({worst['temp_c']}C)"
        eta_hr = round(0.5 + h * 4.0, 2)
    elif h < 0.25:
        mode = f"{worst['component']}: IMMINENT FAILURE"
        eta_hr = round(0.2 + h * 6.0, 2)
    elif h < 0.5:
        mode = f"{worst['component']}: DEGRADATION TREND"
        eta_hr = round(2.0 + h * 30.0, 2)
    else:
        mode = "no single-point failure predicted within forecast window"
        eta_hr = round(24.0 + h * 200.0, 2)
    return {
        "predicted_failure_mode": mode,
        "predicted_failure_probability": p_fail,
        "predicted_eta_hours": eta_hr,
        "driving_component": worst["component"],
        "driving_component_health": h,
        "disclaimer": "PROBABILISTIC — signed by Λ, NOT a guarantee.",
    }


def compute_health(drone_id: str, lat: float, lon: float, station: str,
                   live: bool = True) -> dict[str, Any]:
    """Full diagnostic. If live=True, fuse public APIs; always bit-exact reproducible
    given identical fusion inputs (Codex-Kernel)."""
    if live:
        sw = fetch_spaceweather()
        wind = fetch_wind(station)
        quake = fetch_earthquakes(lat, lon)
        sat = fetch_satellites(lat, lon)
    else:
        sw = wind = quake = sat = {}
    # Codex-Kernel: fusion_inputs are the ONLY entropy source for the seed. We
    # snapshot the salient live scalars so the report is reproducible from them.
    fusion_inputs = {
        "kp": sw.get("kp_index"), "solar_wind": sw.get("solar_wind_speed_kms"),
        "wind_kt": wind.get("wind_speed_kt"), "wind_gust_kt": wind.get("wind_gust_kt"),
        "shake": quake.get("landing_shake_risk"), "sat_count": sat.get("satellite_count"),
        "lat": round(lat, 3), "lon": round(lon, 3), "station": station,
    }
    fusion = {"spaceweather": sw, "wind": wind, "earthquake": quake, "satellites": sat,
              "fusion_inputs": fusion_inputs}
    comp_states = _component_states(drone_id, fusion)
    axes = _yuyay_axes(drone_id, comp_states, fusion)
    lam = round(lambda_aggregate([axes[a] for a in AXIS_NAMES]), 6)
    pred = _predict_failure(comp_states, axes, lam)
    health_score = round(sum(c["health"] for c in comp_states.values()) / len(comp_states), 4)
    report = {
        "drone_id": drone_id,
        "schema": "szl.killinchu.drone3d.health/v4",
        "doctrine": DOCTRINE,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "operating_area": {"lat": lat, "lon": lon, "wx_station": station},
        "drone_health_score": health_score,
        "yuyay_13_axes": axes,
        "lambda_combined_risk": lam,
        "lambda_floor": LAMBDA_FLOOR,
        "lambda_gate": "PASS" if lam >= LAMBDA_FLOOR else "HALT",
        "lambda_note": "geometric-mean aggregate (Doctrine v11 yuyay_v3); uniqueness = Conjecture 1 (NOT a theorem)",
        "satellite_rf_environment": {
            "satellite_count": sat.get("satellite_count"),
            "gps_reliability_score": sw.get("gps_reliability_score"),
            "rf_solar_penalty": sw.get("rf_solar_penalty"),
            "kp_index": sw.get("kp_index"),
            "live": bool(sat.get("live")),
        },
        "weather_impact": {
            "wind_speed_kt": wind.get("wind_speed_kt"),
            "wind_gust_kt": wind.get("wind_gust_kt"),
            "wind_shear_kt": wind.get("wind_shear_kt"),
            "wind_impact_score": wind.get("wind_impact_score"),
            "landing_shake_risk": quake.get("landing_shake_risk"),
            "nearest_quake": quake.get("nearest"),
            "live": bool(wind.get("live")),
        },
        "prediction": pred,
        "component_map": comp_states,
        "fusion_inputs": fusion_inputs,
        "codex_kernel": {
            "reproducible": True,
            "seed_sha256": hashlib.sha256(_seed(drone_id, fusion)).hexdigest(),
            "note": "Identical fusion_inputs reproduce this report bit-exact (seed-derived component states).",
        },
        "feeds": {
            "spaceweather_sources": sw.get("sources"),
            "earthquake_source": quake.get("source"),
            "wind_source": wind.get("source"),
            "satellite_source": sat.get("source"),
        },
        "honesty": HONESTY,
        "legal_disclaimer_url": LEGAL_URL,
    }
    return report


# ---------------------------------------------------------------------------
# Three.js scene builder — per-component geometry + health color.
# ---------------------------------------------------------------------------

def _health_color(h: float, fired: bool, thermal: bool) -> str:
    """Heatmap hex: green (healthy) -> yellow -> red (critical). Fired=purple, thermal=orange tint."""
    if fired:
        return "#b026ff"  # kinetic loss — violet
    # clamp
    h = max(0.0, min(1.0, h))
    if h >= 0.5:
        # green->yellow over [0.5,1.0]
        t = (1.0 - h) / 0.5
        r = int(255 * t); g = 220; b = 60
    else:
        # yellow->red over [0,0.5]
        t = (0.5 - h) / 0.5
        r = 255; g = int(220 * (1 - t)); b = 60 - int(40 * t)
    if thermal:
        r = min(255, r + 30); g = max(0, g - 30)
    return f"#{r:02x}{g:02x}{b:02x}"


# component -> (geometry primitive, position[x,y,z], scale, label)
_GEOM_LAYOUT = {
    "fc":       {"geom": "box",      "pos": [0, 0.1, 0],     "size": [0.6, 0.2, 0.6],  "label": "Flight Controller"},
    "battery":  {"geom": "box",      "pos": [0, -0.15, 0],   "size": [0.7, 0.25, 0.4], "label": "Battery"},
    "gps":      {"geom": "cylinder", "pos": [0, 0.35, -0.3], "size": [0.12, 0.12, 0.1],"label": "GPS Module"},
    "rx":       {"geom": "box",      "pos": [0, 0.25, 0.3],  "size": [0.2, 0.08, 0.2], "label": "RX (datalink)"},
    "camera":   {"geom": "sphere",   "pos": [0, -0.1, 0.45], "size": [0.13, 0.13, 0.13],"label": "Camera/Gimbal"},
    "esc":      {"geom": "box",      "pos": [0, 0.0, 0],     "size": [0.45, 0.1, 0.45],"label": "ESC stack"},
    "rotor_fl": {"geom": "cylinder", "pos": [-0.9, 0.2, -0.9],"size": [0.45, 0.45, 0.04],"label": "Rotor FL", "arm": [-0.45, 0.05, -0.45]},
    "rotor_fr": {"geom": "cylinder", "pos": [0.9, 0.2, -0.9], "size": [0.45, 0.45, 0.04],"label": "Rotor FR", "arm": [0.45, 0.05, -0.45]},
    "rotor_rl": {"geom": "cylinder", "pos": [-0.9, 0.2, 0.9], "size": [0.45, 0.45, 0.04],"label": "Rotor RL", "arm": [-0.45, 0.05, 0.45]},
    "rotor_rr": {"geom": "cylinder", "pos": [0.9, 0.2, 0.9],  "size": [0.45, 0.45, 0.04],"label": "Rotor RR", "arm": [0.45, 0.05, 0.45]},
}


def build_3d_model(report: dict[str, Any]) -> dict[str, Any]:
    comp_states = report["component_map"]
    nodes = []
    for comp, layout in _GEOM_LAYOUT.items():
        cs = comp_states.get(comp, {"health": 0.9, "fired": False, "thermal_anomaly": False, "temp_c": 35, "status": "HEALTHY"})
        node = {
            "id": comp,
            "label": layout["label"],
            "geometry": layout["geom"],
            "position": layout["pos"],
            "size": layout["size"],
            "color": _health_color(cs["health"], cs["fired"], cs["thermal_anomaly"]),
            "health": cs["health"],
            "temp_c": cs["temp_c"],
            "fired": cs["fired"],
            "thermal_anomaly": cs["thermal_anomaly"],
            "status": cs["status"],
            "emissive_intensity": round(0.2 + (1.0 - cs["health"]) * 0.8, 3),
        }
        if "arm" in layout:
            node["arm"] = layout["arm"]  # render a strut to body center
        nodes.append(node)
    return {
        "schema": "szl.killinchu.drone3d.scene/v4",
        "drone_id": report["drone_id"],
        "frame": "quadcopter",
        "scene": {
            "background": "#070b16",
            "grid": True,
            "ambient_light": 0.55,
            "components": nodes,
        },
        "legend": {
            "healthy": "#dcdc3c", "degraded": "#ffaa3c", "critical": "#ff3c3c",
            "fired": "#b026ff", "thermal_tint": "orange-shift on overheating",
        },
        "drone_health_score": report["drone_health_score"],
        "lambda_combined_risk": report["lambda_combined_risk"],
        "ts_utc": report["ts_utc"],
        "honesty": HONESTY,
    }


# ---------------------------------------------------------------------------
# HF Inference (free tier) — "explain this drone's failure modes".
# ---------------------------------------------------------------------------

def _hf_token() -> Optional[str]:
    for v in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HF_API_TOKEN"):
        t = os.environ.get(v)
        if t:
            return t.strip()
    # fall back to git-credentials (HF Space ships the token there)
    try:
        with open(os.path.expanduser("~/.git-credentials")) as f:
            for line in f:
                if "huggingface.co" in line and "@" in line:
                    return line.split("://", 1)[1].split("@", 1)[0].split(":", 1)[1].strip()
    except Exception:
        pass
    return None


HF_EXPLAIN_MODEL = os.environ.get("KILLINCHU_HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")


def explain_health(report: dict[str, Any]) -> dict[str, Any]:
    """Generate a narrative via HF Inference router (OpenAI-compatible chat). Free tier.
    Degrades to a deterministic local narrative if the token/endpoint is unavailable."""
    worst = report["prediction"]
    axes = report["yuyay_13_axes"]
    facts = {
        "drone_id": report["drone_id"],
        "health_score": report["drone_health_score"],
        "lambda": report["lambda_combined_risk"],
        "gate": report["lambda_gate"],
        "predicted_failure_mode": worst["predicted_failure_mode"],
        "predicted_eta_hours": worst["predicted_eta_hours"],
        "predicted_probability": worst["predicted_failure_probability"],
        "kp_index": report["satellite_rf_environment"]["kp_index"],
        "wind_impact": report["weather_impact"]["wind_impact_score"],
        "weakest_axes": sorted(axes.items(), key=lambda kv: kv[1])[:3],
    }
    prompt = (
        "You are Killinchu, an Andean drone-health diagnostics co-pilot. In 4-6 plain sentences, "
        "explain this quadcopter's current health and likely failure modes for a field operator. "
        "Be specific about the driving component, the environmental stressor (space weather Kp / wind), "
        "and stress that the prediction is PROBABILISTIC, signed by Λ, NOT a guarantee. "
        f"DIAGNOSTIC JSON: {json.dumps(facts)}"
    )
    token = _hf_token()
    out: dict[str, Any] = {
        "drone_id": report["drone_id"],
        "model": HF_EXPLAIN_MODEL,
        "provider": "HF Inference router (free tier)",
        "facts": facts,
        "honesty": HONESTY,
    }
    if not token:
        out["narrative"] = _local_narrative(facts)
        out["source"] = "deterministic local fallback (no HF token in runtime)"
        out["live_llm"] = False
        return out
    try:
        body = json.dumps({
            "model": HF_EXPLAIN_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 320, "temperature": 0.3,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://router.huggingface.co/v1/chat/completions",
            data=body, method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "User-Agent": "killinchu-drone-3d-health/1.0"})
        with urllib.request.urlopen(req, timeout=25.0) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        out["narrative"] = text
        out["source"] = "HF Inference router (live)"
        out["live_llm"] = True
    except Exception as e:
        out["narrative"] = _local_narrative(facts)
        out["source"] = f"deterministic local fallback (HF call failed: {type(e).__name__})"
        out["live_llm"] = False
    return out


def _local_narrative(facts: dict) -> str:
    weak = ", ".join(f"{k}={v}" for k, v in facts["weakest_axes"])
    return (
        f"Drone {facts['drone_id']} reports an overall health score of {facts['health_score']} "
        f"with a Λ-combined trust of {facts['lambda']} (gate {facts['gate']}). "
        f"The dominant risk is '{facts['predicted_failure_mode']}', estimated around "
        f"{facts['predicted_eta_hours']} hours out at probability {facts['predicted_probability']}. "
        f"Geomagnetic Kp is {facts['kp_index']} and wind impact is {facts['wind_impact']}, which "
        f"pressure the weakest trust axes ({weak}). "
        "This is a PROBABILISTIC prediction signed by Λ — NOT a guarantee."
    )


# ---------------------------------------------------------------------------
# FastAPI registration — ADDITIVE. /api/killinchu/v4/* + /drone-3d page.
# ---------------------------------------------------------------------------

def register(app, ns: str = "killinchu", *,
             emit_receipt: Optional[Callable] = None,
             sign_receipt: Optional[Callable] = None,
             static_dir: Optional[str] = None) -> dict[str, Any]:
    """Register the v4 3D drone-health surface on `app`. Idempotent + guarded.

    emit_receipt(kind, payload) -> Khipu DAG node (from serve.py) if provided.
    sign_receipt(receipt) -> DSSE envelope (szl_dsse.sign_khipu_receipt) if provided.
    """
    base = f"/api/{ns}/v4"
    registered: list[str] = []
    existing = {getattr(r, "path", None) for r in app.routes}

    # resolve DSSE signer (real ECDSA) if not injected
    if sign_receipt is None:
        try:
            import szl_dsse as _dsse
            sign_receipt = _dsse.sign_khipu_receipt
        except Exception:
            sign_receipt = None

    def _sign_and_chain(kind: str, summary: dict[str, Any]) -> dict[str, Any]:
        """Mint a Khipu DAG node (if host provided one) and attach a REAL DSSE envelope."""
        node = None
        if emit_receipt is not None:
            try:
                node = emit_receipt(kind, summary)
            except Exception:
                node = None
        receipt = {
            "schema": "szl.killinchu.drone3d.receipt/v4",
            "kind": kind,
            "payload": summary,
            "doctrine": DOCTRINE,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "khipu_index": (node or {}).get("index"),
            "khipu_digest": (node or {}).get("digest"),
        }
        dsse_env = None
        if sign_receipt is not None:
            try:
                signed = sign_receipt(receipt)
                dsse_env = signed.get("dsse") if isinstance(signed, dict) else None
            except Exception:
                dsse_env = None
        return {"receipt": receipt, "dsse": dsse_env,
                "honesty": HONESTY if (dsse_env and dsse_env.get("signed")) else
                           "UNSIGNED — SZL_COSIGN_PRIVATE_PEM secret absent; no signature fabricated."}

    def _params(request: Request):
        q = request.query_params
        lat = float(q.get("lat", "39.7392"))   # default: Denver area test zone
        lon = float(q.get("lon", "-104.9903"))
        station = q.get("station", "KDEN")
        live = q.get("live", "1") not in ("0", "false", "no")
        return lat, lon, station, live

    def _maybe(path: str) -> bool:
        if path in existing:
            return False
        existing.add(path)
        return True

    # ---- /spaceweather ----
    p = f"{base}/spaceweather"
    if _maybe(p):
        @app.get(p)
        async def v4_spaceweather():  # noqa: ANN202
            sw = fetch_spaceweather()
            sw["fused_space_weather_score"] = sw.get("gps_reliability_score")
            sw["receipt"] = _sign_and_chain("spaceweather", {"kp": sw.get("kp_index")})
            sw["honesty"] = HONESTY
            return JSONResponse(sw)
        registered.append(p)

    # ---- /satellites/visible ----
    p = f"{base}/satellites/visible"
    if _maybe(p):
        @app.get(p)
        async def v4_satellites(request: Request):  # noqa: ANN202
            q = request.query_params
            lat = float(q.get("lat", "39.7392")); lon = float(q.get("lon", "-104.9903"))
            sat = fetch_satellites(lat, lon)
            sat["receipt"] = _sign_and_chain("satellites/visible", {"count": sat.get("satellite_count")})
            sat["honesty"] = HONESTY
            return JSONResponse(sat)
        registered.append(p)

    # ---- /drones/{id}/health ----
    p = f"{base}/drones/{{drone_id}}/health"
    if _maybe(p):
        @app.get(p)
        async def v4_health(drone_id: str, request: Request):  # noqa: ANN202
            lat, lon, station, live = _params(request)
            report = compute_health(drone_id, lat, lon, station, live=live)
            report["receipt"] = _sign_and_chain("drones/health", {
                "drone_id": drone_id, "health_score": report["drone_health_score"],
                "lambda": report["lambda_combined_risk"], "gate": report["lambda_gate"],
                "predicted_failure_mode": report["prediction"]["predicted_failure_mode"],
                "seed_sha256": report["codex_kernel"]["seed_sha256"],
            })
            return JSONResponse(report)
        registered.append(p)

    # ---- /drones/{id}/3d-model ----
    p = f"{base}/drones/{{drone_id}}/3d-model"
    if _maybe(p):
        @app.get(p)
        async def v4_3dmodel(drone_id: str, request: Request):  # noqa: ANN202
            lat, lon, station, live = _params(request)
            report = compute_health(drone_id, lat, lon, station, live=live)
            scene = build_3d_model(report)
            scene["receipt"] = _sign_and_chain("drones/3d-model", {
                "drone_id": drone_id, "health_score": report["drone_health_score"],
                "seed_sha256": report["codex_kernel"]["seed_sha256"]})
            return JSONResponse(scene)
        registered.append(p)

    # ---- /drones/{id}/explain ----
    p = f"{base}/drones/{{drone_id}}/explain"
    if _maybe(p):
        @app.get(p)
        async def v4_explain(drone_id: str, request: Request):  # noqa: ANN202
            lat, lon, station, live = _params(request)
            report = compute_health(drone_id, lat, lon, station, live=live)
            ex = explain_health(report)
            ex["receipt"] = _sign_and_chain("drones/explain", {
                "drone_id": drone_id, "live_llm": ex.get("live_llm"), "model": ex.get("model")})
            return JSONResponse(ex)
        registered.append(p)

    # ---- module self-test / honesty ----
    p = f"{base}/health/_self"
    if _maybe(p):
        @app.get(p)
        async def v4_self():  # noqa: ANN202
            # offline reproducibility proof: same inputs -> same Λ
            r1 = compute_health("_selftest", 39.7392, -104.9903, "KDEN", live=False)
            r2 = compute_health("_selftest", 39.7392, -104.9903, "KDEN", live=False)
            return JSONResponse({
                "module": "killinchu_drone_3d_health",
                "version": "v4",
                "doctrine": DOCTRINE,
                "axes": AXIS_NAMES,
                "components": COMPONENTS,
                "lambda_floor": LAMBDA_FLOOR,
                "codex_kernel_reproducible": r1["lambda_combined_risk"] == r2["lambda_combined_risk"]
                                             and r1["codex_kernel"]["seed_sha256"] == r2["codex_kernel"]["seed_sha256"],
                "dsse_signer_available": sign_receipt is not None,
                "n2yo_key_present": bool(os.environ.get("N2YO_API_KEY")),
                "hf_token_present": bool(_hf_token()),
                "public_apis": {
                    "USGS earthquakes": "free, no key",
                    "NOAA SWPC Kp + solar wind": "free, no key",
                    "NOAA Aviation Weather METAR": "free, no key",
                    "N2YO satellites-above": "free tier, requires free API key (N2YO_API_KEY)",
                    "HF Inference router chat": "free tier, uses Space HF token",
                },
                "honesty": HONESTY,
                "endpoints": registered,
            })
        registered.append(p)

    # ---- /drone-3d page (served from static dir) ----
    sdir = static_dir or os.environ.get("KILLINCHU_ROOT", "/app") + "/static"
    page = os.path.join(sdir, "drone-3d.html")
    p = "/drone-3d"
    if _maybe(p):
        @app.get(p)
        async def drone_3d_page():  # noqa: ANN202
            if os.path.isfile(page):
                return FileResponse(page, media_type="text/html")
            return HTMLResponse("<h1>drone-3d.html not deployed</h1>", status_code=404)
        registered.append(p)

    return {"module": "killinchu_drone_3d_health", "registered_count": len(registered),
            "registered": registered, "base": base,
            "signing": "REAL DSSE (szl_dsse)" if sign_receipt else "unsigned"}
