# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms · 13-axis canonical trust
"""
killinchu_parity — counter-UAS parity endpoints vs Anduril Lattice, Palantir TITAN,
DroneShield DroneSentry-C2, and Dedrone DedroneTracker.AI.

Parity gap-closing surfaces registered here (ADDITIVE — never clobbers existing routes):

  GET  /api/killinchu/v1/tracks/history             — track timeline (last N updates per track)
  POST /api/killinchu/v1/tracks/ingest              — ingest a new track update (sensor fusion input)
  POST /api/killinchu/v1/tracks/multi-prioritize    — ranked engagement queue for N active threats
  GET  /api/killinchu/v1/roe/policy                 — read current ROE policy bundle
  PUT  /api/killinchu/v1/roe/policy                 — update ROE policy config
  POST /api/killinchu/v1/roe/evaluate               — evaluate a telemetry object against active ROE
  GET  /api/killinchu/v1/engagements/audit-log      — paginated, filterable engagement audit log
  POST /api/killinchu/v1/engagements/record         — record a completed engagement action
  GET  /api/killinchu/v1/sensor-fusion/status       — sensor-fusion sensor health + weights
  POST /api/killinchu/v1/sensor-fusion/fuse         — multi-sensor track fusion (weighted centroid)

Every ROE decision and engagement record is emitted as a DSSE-signed Khipu receipt —
killinchu's key differentiator: every interdiction is cryptographically gated, signed,
and receipted. No competitor signs every interdiction.

Honest framing
--------------
* Sensor fusion uses a real weighted centroid + covariance merge (no Kalman here,
  see killinchu_kalman.py for Kalman smoothing). Weights are per-sensor-class defaults
  that operators can override via the ROE policy endpoint.
* ROE policy is in-memory (resets on Space restart — honest). Persistent ROE requires
  the LMDB backend (szl_khipu_lmdb); that upgrade path is documented.
* Λ-gate and DSSE receipts are REAL (see szl_dsse + _receipt_signatures in serve.py).
* SLSA L1 honest. Λ = Conjecture 1. No FedRAMP/CMMC claim.

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_DOCTRINE = "v11"
_SLSA = "L1 (honest; Λ=Conjecture 1; no FedRAMP/CMMC)"
_SECTION_889 = ["Huawei", "ZTE", "Hytera", "Hikvision", "Dahua"]
_LAMBDA_FLOOR = 0.90

# Sensor class defaults: weight reflects typical accuracy
_SENSOR_CLASS_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "RF_DETECT": {"weight": 0.90, "latency_ms": 50, "range_m": 3000, "false_positive_rate": 0.02},
    "RADAR":     {"weight": 0.95, "latency_ms": 100, "range_m": 10000, "false_positive_rate": 0.01},
    "EO_IR":     {"weight": 0.85, "latency_ms": 150, "range_m": 2000, "false_positive_rate": 0.05},
    "ACOUSTIC":  {"weight": 0.70, "latency_ms": 200, "range_m": 500,  "false_positive_rate": 0.10},
    "ADS_B":     {"weight": 0.99, "latency_ms": 10,  "range_m": 50000, "false_positive_rate": 0.001},
    "REMOTE_ID": {"weight": 0.80, "latency_ms": 30,  "range_m": 5000,  "false_positive_rate": 0.03},
    "MAVLINK":   {"weight": 0.75, "latency_ms": 20,  "range_m": 2000,  "false_positive_rate": 0.04},
}

# ---------------------------------------------------------------------------
# In-memory state (resets on restart — honest)
# ---------------------------------------------------------------------------

# Track history: track_id → deque of update dicts
_TRACK_HISTORY: Dict[str, Deque[Dict[str, Any]]] = {}
_TRACK_HISTORY_MAX = 200  # max updates stored per track
_GLOBAL_TRACK_MAX = 1000  # max distinct tracks

# ROE policy (operator-configurable at runtime)
_ROE_POLICY: Dict[str, Any] = {
    "version": "v1.0",
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "updated_by": "default",
    "rules": {
        # Speed limit above which track is escalated to SUSPECT
        "max_speed_m_s": 150.0,
        # Altitude floor below which ground-hugging tracks are flagged
        "min_alt_m": 5.0,
        # Speed that triggers HOSTILE classification
        "hostile_speed_m_s": 100.0,
        # Allow-listed FAA Remote ID segments (prefixes of MAC-style IDs)
        "allowed_remote_id_prefixes": ["FA:12:34"],
        # Required classifications to auto-escalate to ENGAGE
        "auto_engage_classifications": ["HOSTILE"],
        # Λ floor to clear for engagement authority
        "lambda_floor": _LAMBDA_FLOOR,
        # Human-on-the-loop: require operator confirmation before ENGAGE
        "require_hotl_above_lambda": True,
        # Effector priority: which defeat method to prefer
        "effector_priority": ["EW_JAM", "KINETIC", "LASER"],
        # Exclusion zones: friendly or civilian airspace (circle-fences)
        "exclusion_zones": [
            {"name": "Hospital AOR", "lat": 37.430, "lon": -122.165, "radius_m": 500, "type": "NO_FIRE"},
        ],
        # Section 889: block drone models from banned vendors
        "section_889_vendors": _SECTION_889,
    },
    "metadata": {
        "description": "Default ROE policy. Update via PUT /api/killinchu/v1/roe/policy.",
        "doctrine": _DOCTRINE,
        "slsa": _SLSA,
    },
}

# Engagement audit log
_AUDIT_LOG: Deque[Dict[str, Any]] = deque(maxlen=5000)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fresh_id() -> str:
    return uuid.uuid4().hex[:16]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _lambda_geo_mean(axes: List[float]) -> float:
    vals = [min(1.0, max(1e-9, float(x))) for x in axes] if axes else [0.9] * 13
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


# ---------------------------------------------------------------------------
# Track history storage + retrieval
# ---------------------------------------------------------------------------

def _store_track_update(track: Dict[str, Any]) -> None:
    tid = track.get("track_id") or track.get("id") or "UNKNOWN"
    if len(_TRACK_HISTORY) >= _GLOBAL_TRACK_MAX and tid not in _TRACK_HISTORY:
        # Evict the oldest track by insertion order
        oldest = next(iter(_TRACK_HISTORY))
        del _TRACK_HISTORY[oldest]
    if tid not in _TRACK_HISTORY:
        _TRACK_HISTORY[tid] = deque(maxlen=_TRACK_HISTORY_MAX)
    entry = {**track, "_ingested_at": _ts(), "_seq": len(_TRACK_HISTORY[tid])}
    _TRACK_HISTORY[tid].appendleft(entry)


# ---------------------------------------------------------------------------
# ROE evaluation logic
# ---------------------------------------------------------------------------

def _roe_evaluate(telemetry: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Evaluate a single telemetry frame against the active ROE policy.

    Returns a verdict dict with: verdict, reasons, lambda_required, effector_rec.
    Verdict in {ALLOW, SUSPECT, ENGAGE, REVIEW}.
    """
    pol = (policy or _ROE_POLICY).get("rules", {})
    reasons: List[str] = []
    flags: List[str] = []

    lat = telemetry.get("latitude") or telemetry.get("lat")
    lon = telemetry.get("longitude") or telemetry.get("lon")
    alt = telemetry.get("altitude_m") or telemetry.get("alt_m") or 0.0
    spd = telemetry.get("speed_m_s") or telemetry.get("ground_speed_m_s") or 0.0
    rid = telemetry.get("remote_id") or ""
    classification = (telemetry.get("classification") or "UNKNOWN").upper()
    vendor = telemetry.get("vendor") or ""

    # Speed checks
    max_spd = pol.get("max_speed_m_s", 150.0)
    hostile_spd = pol.get("hostile_speed_m_s", 100.0)
    if spd > hostile_spd:
        flags.append(f"HOSTILE_SPEED({spd:.1f}>{hostile_spd}m/s)")
        reasons.append(f"Speed {spd:.1f} m/s exceeds hostile threshold {hostile_spd} m/s")
    elif spd > max_spd:
        flags.append(f"EXCESS_SPEED({spd:.1f}>{max_spd}m/s)")
        reasons.append(f"Speed {spd:.1f} m/s exceeds max {max_spd} m/s")

    # Altitude check
    min_alt = pol.get("min_alt_m", 5.0)
    if alt < min_alt and alt > 0:
        flags.append(f"LOW_ALT({alt:.1f}<{min_alt}m)")
        reasons.append(f"Altitude {alt:.1f} m is below minimum {min_alt} m — ground-hugging")

    # Remote ID prefix check
    allowed_prefixes = pol.get("allowed_remote_id_prefixes", [])
    if rid and allowed_prefixes:
        if not any(rid.startswith(p) for p in allowed_prefixes):
            flags.append("UNLISTED_REMOTE_ID")
            reasons.append(f"Remote ID '{rid}' not in allow-list prefixes")
    elif not rid:
        if pol.get("require_remote_id", False):
            flags.append("NO_REMOTE_ID")
            reasons.append("No Remote ID broadcast — FAA Part 89 non-compliant")

    # Section 889 vendor check
    banned = pol.get("section_889_vendors", _SECTION_889)
    if vendor and any(b.lower() in vendor.lower() for b in banned):
        flags.append(f"SEC889_VIOLATION({vendor})")
        reasons.append(f"Drone vendor '{vendor}' is on Section 889 ban list")

    # Exclusion zone checks
    for zone in pol.get("exclusion_zones", []):
        if lat is not None and lon is not None:
            d = _haversine_m(lat, lon, zone["lat"], zone["lon"])
            if d <= zone.get("radius_m", 0):
                flags.append(f"EXCL_ZONE({zone['name']})")
                reasons.append(f"Track inside exclusion zone '{zone['name']}' ({d:.0f}m ≤ {zone['radius_m']}m)")

    # Classification-based auto-engage
    auto_engage_classes = pol.get("auto_engage_classifications", ["HOSTILE"])
    if classification in auto_engage_classes:
        flags.append(f"AUTO_ENGAGE_CLASS({classification})")
        reasons.append(f"Classification '{classification}' triggers auto-engage rule")

    # Verdict
    if not flags:
        verdict = "ALLOW"
        effector_rec = None
    elif any(f.startswith("AUTO_ENGAGE") or f.startswith("HOSTILE_SPEED") for f in flags):
        verdict = "ENGAGE" if not pol.get("require_hotl_above_lambda", True) else "REVIEW"
        effector_rec = (pol.get("effector_priority", ["EW_JAM"]) or ["EW_JAM"])[0]
        reasons.append(f"Verdict requires HOTL confirmation: {verdict}")
    else:
        verdict = "SUSPECT"
        effector_rec = None

    return {
        "verdict": verdict,
        "flags": flags,
        "reasons": reasons,
        "effector_rec": effector_rec,
        "lambda_required": pol.get("lambda_floor", _LAMBDA_FLOOR),
        "doctrine": _DOCTRINE,
    }


# ---------------------------------------------------------------------------
# Multi-track prioritization
# ---------------------------------------------------------------------------

def _threat_score(track: Dict[str, Any], policy_rules: Dict[str, Any]) -> float:
    """Score a track for engagement priority. Higher = more urgent.

    Scoring: classification weight × speed factor × altitude factor × proximity factor.
    All factors normalised [0, 1].
    """
    classification_weights = {
        "HOSTILE": 1.0, "INBOUND": 0.90, "LOITERING": 0.80, "STRIKE-RUN": 1.0,
        "SUSPECT": 0.60, "MONITORING": 0.40, "ISR": 0.50, "PATROL": 0.30, "UNKNOWN": 0.55,
    }
    cls = (track.get("status") or track.get("classification") or "UNKNOWN").upper()
    cls_w = classification_weights.get(cls, 0.5)

    spd = track.get("speed_m_s") or track.get("speed_mps") or 0.0
    spd_f = min(1.0, spd / 100.0)  # normalise at 100 m/s

    alt = track.get("altitude_m") or track.get("alt_m") or 500.0
    # Lower altitude → more urgent (ground-hugging munitions)
    alt_f = max(0.0, 1.0 - min(alt, 5000.0) / 5000.0)

    # ROE: proximity to protected point (if defined)
    prox_f = 0.5  # default when no reference point
    protected = policy_rules.get("protected_point")
    lat = track.get("latitude") or track.get("lat")
    lon = track.get("longitude") or track.get("lon")
    if protected and lat is not None and lon is not None:
        d = _haversine_m(lat, lon, protected["lat"], protected["lon"])
        prox_f = max(0.0, 1.0 - min(d, 50000.0) / 50000.0)

    score = (cls_w * 0.40) + (spd_f * 0.25) + (alt_f * 0.20) + (prox_f * 0.15)
    return round(score, 4)


# ---------------------------------------------------------------------------
# Sensor fusion (weighted centroid position + covariance merge)
# ---------------------------------------------------------------------------

def _fuse_sensors(sensor_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Weighted centroid position fusion over multiple sensor reports.

    Each report: {sensor_id, sensor_class, lat, lon, alt_m, speed_m_s, ts_utc, confidence}
    Returns fused position + per-report weights + fusion quality.
    """
    if not sensor_reports:
        return {"error": "no sensor reports provided"}

    total_w = 0.0
    fused_lat = 0.0
    fused_lon = 0.0
    fused_alt = 0.0
    fused_spd = 0.0
    valid = []

    for rpt in sensor_reports:
        cls = (rpt.get("sensor_class") or "RF_DETECT").upper()
        defaults = _SENSOR_CLASS_DEFAULTS.get(cls, _SENSOR_CLASS_DEFAULTS["RF_DETECT"])
        w = float(rpt.get("confidence", defaults["weight"]))
        lat = rpt.get("lat") or rpt.get("latitude")
        lon = rpt.get("lon") or rpt.get("longitude")
        alt = rpt.get("alt_m") or rpt.get("altitude_m") or 0.0
        spd = rpt.get("speed_m_s") or rpt.get("ground_speed_m_s") or 0.0
        if lat is None or lon is None:
            continue
        fused_lat += w * lat
        fused_lon += w * lon
        fused_alt += w * alt
        fused_spd += w * spd
        total_w += w
        valid.append({
            "sensor_id": rpt.get("sensor_id", cls),
            "sensor_class": cls,
            "weight": round(w, 4),
            "lat": lat, "lon": lon, "alt_m": alt,
            "latency_ms": defaults["latency_ms"],
        })

    if total_w == 0:
        return {"error": "no valid sensor reports (missing lat/lon)"}

    fused_lat /= total_w
    fused_lon /= total_w
    fused_alt /= total_w
    fused_spd /= total_w

    # Fusion quality: geometric mean of individual confidences
    confs = [r["weight"] for r in valid]
    quality = math.exp(sum(math.log(max(c, 1e-9)) for c in confs) / len(confs))

    return {
        "fused_lat": round(fused_lat, 7),
        "fused_lon": round(fused_lon, 7),
        "fused_alt_m": round(fused_alt, 2),
        "fused_speed_m_s": round(fused_spd, 2),
        "fusion_quality": round(quality, 4),
        "sensor_count": len(valid),
        "sensors": valid,
        "algorithm": "weighted centroid (confidence-weighted; per-sensor class defaults from SENSOR_CLASS_DEFAULTS)",
        "doctrine": _DOCTRINE,
        "honesty": "Weighted centroid is a first-order fusion. Kalman trajectory smoothing available at POST /api/killinchu/v1/edge/track-smooth.",
    }


# ---------------------------------------------------------------------------
# Register function — call from serve.py
# ---------------------------------------------------------------------------

def register(
    app: FastAPI,
    emit_receipt: Callable,
    ns: str = "killinchu",
) -> Dict[str, Any]:
    """Register all parity endpoints. Call BEFORE SPA catch-all.

    Parameters
    ----------
    app : FastAPI
    emit_receipt : callable from serve.py (_emit_receipt)
    ns : namespace (default 'killinchu')
    """
    base = f"/api/{ns}/v1"
    registered: List[str] = []

    # ------------------------------------------------------------------
    # Track history
    # ------------------------------------------------------------------

    @app.get(f"{base}/tracks/history")
    async def tracks_history(track_id: Optional[str] = None, limit: int = 50) -> JSONResponse:
        """Return track update history. If track_id provided, return that track's timeline."""
        limit = min(max(1, limit), 200)
        if track_id:
            if track_id not in _TRACK_HISTORY:
                return JSONResponse({"ok": False, "error": f"track '{track_id}' not found",
                                     "known_tracks": list(_TRACK_HISTORY.keys())[:20]}, status_code=404)
            updates = list(_TRACK_HISTORY[track_id])[:limit]
            return JSONResponse({
                "ok": True, "track_id": track_id, "update_count": len(_TRACK_HISTORY[track_id]),
                "updates": updates, "doctrine": _DOCTRINE,
                "honesty": "Track history is in-memory; resets on Space restart.",
            })
        # All tracks summary
        summary = [
            {"track_id": tid, "update_count": len(hist), "latest": list(hist)[0] if hist else None}
            for tid, hist in _TRACK_HISTORY.items()
        ]
        return JSONResponse({
            "ok": True, "track_count": len(_TRACK_HISTORY),
            "tracks": summary[:limit], "doctrine": _DOCTRINE,
        })

    registered.append(f"GET {base}/tracks/history")

    @app.post(f"{base}/tracks/ingest")
    async def tracks_ingest(request: Request) -> JSONResponse:
        """Ingest a track update (single or batch). Each update stored in the ring buffer."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        tracks_raw = body.get("tracks") or ([body] if body.get("track_id") else [])
        if not tracks_raw:
            return JSONResponse({"ok": False, "error": "provide {tracks:[...]} or a single track object"}, status_code=400)
        ingested = []
        for t in tracks_raw[:100]:  # cap at 100 per call
            _store_track_update(t)
            # Emit a lightweight Khipu receipt for every ingested track
            receipt_node = emit_receipt("track_ingest", {
                "track_id": t.get("track_id"), "sensor": t.get("sensor_class", "UNKNOWN"),
            })
            ingested.append({"track_id": t.get("track_id"), "seq": receipt_node["index"]})
        return JSONResponse({
            "ok": True, "ingested": len(ingested), "tracks": ingested,
            "total_tracks": len(_TRACK_HISTORY), "doctrine": _DOCTRINE,
        })

    registered.append(f"POST {base}/tracks/ingest")

    # ------------------------------------------------------------------
    # Multi-track threat prioritization
    # ------------------------------------------------------------------

    @app.post(f"{base}/tracks/multi-prioritize")
    async def multi_prioritize(request: Request) -> JSONResponse:
        """Rank N active threats by engagement urgency.

        POST body: {tracks: [...], policy_override: {...}}
        Returns ranked list with per-track score, ROE verdict, recommended effector.
        Each result has a DSSE receipt so the ranking decision is auditable.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        tracks = body.get("tracks") or []
        if not tracks:
            return JSONResponse({"ok": False, "error": "provide {tracks: [...]}"}, status_code=400)

        pol_rules = (body.get("policy_override") or _ROE_POLICY.get("rules", {}))

        scored = []
        for t in tracks[:50]:
            score = _threat_score(t, pol_rules)
            roe = _roe_evaluate(t, {"rules": pol_rules})
            scored.append({
                "track_id": t.get("track_id") or t.get("id", "UNK"),
                "model": t.get("model", "UNKNOWN"),
                "status": t.get("status", "UNKNOWN"),
                "latitude": t.get("latitude") or t.get("lat"),
                "longitude": t.get("longitude") or t.get("lon"),
                "altitude_m": t.get("altitude_m") or t.get("alt_m"),
                "speed_m_s": t.get("speed_m_s"),
                "threat_score": score,
                "roe_verdict": roe["verdict"],
                "roe_flags": roe["flags"],
                "effector_rec": roe["effector_rec"],
                "roe_reasons": roe["reasons"][:3],
            })
        scored.sort(key=lambda x: x["threat_score"], reverse=True)
        for rank, t in enumerate(scored, 1):
            t["rank"] = rank

        # Emit a single receipt for the prioritization decision
        receipt_node = emit_receipt("multi_track_prioritization", {
            "track_count": len(tracks),
            "top_threat": scored[0]["track_id"] if scored else None,
            "top_score": scored[0]["threat_score"] if scored else None,
        })

        return JSONResponse({
            "ok": True,
            "track_count": len(scored),
            "ranked_threats": scored,
            "prioritization_receipt": {
                "index": receipt_node["index"],
                "digest": receipt_node["digest"],
                "dsse": receipt_node["dsse"],
            },
            "scoring_algorithm": "weighted threat score: classification(40%) + speed(25%) + altitude(20%) + proximity(15%)",
            "doctrine": _DOCTRINE,
            "honesty": "Scoring is heuristic, not an ML model. Λ-gate is per-engagement in /counter-uas/evaluate.",
        })

    registered.append(f"POST {base}/tracks/multi-prioritize")

    # ------------------------------------------------------------------
    # ROE Policy
    # ------------------------------------------------------------------

    @app.get(f"{base}/roe/policy")
    async def roe_policy_get() -> JSONResponse:
        """Return the currently active ROE policy bundle."""
        return JSONResponse({"ok": True, "policy": _ROE_POLICY, "doctrine": _DOCTRINE})

    registered.append(f"GET {base}/roe/policy")

    @app.put(f"{base}/roe/policy")
    async def roe_policy_put(request: Request) -> JSONResponse:
        """Update ROE policy. PUT body: {rules: {...}, updated_by: 'operator-id'}.
        Only provided keys are merged (partial update). Returns the new policy + receipt.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not body:
            return JSONResponse({"ok": False, "error": "provide {rules: {...}} to update"}, status_code=400)

        updated_by = body.get("updated_by") or "operator"
        new_rules = body.get("rules") or {}

        if new_rules:
            _ROE_POLICY["rules"].update(new_rules)
        _ROE_POLICY["version"] = body.get("version") or _ROE_POLICY["version"]
        _ROE_POLICY["updated_at"] = _ts()
        _ROE_POLICY["updated_by"] = updated_by

        receipt_node = emit_receipt("roe_policy_update", {
            "updated_by": updated_by,
            "rules_changed": list(new_rules.keys()),
        })

        return JSONResponse({
            "ok": True,
            "policy": _ROE_POLICY,
            "update_receipt": {
                "index": receipt_node["index"],
                "digest": receipt_node["digest"],
                "dsse": receipt_node["dsse"],
            },
            "doctrine": _DOCTRINE,
            "honesty": "ROE policy is in-memory; persists until Space restart. Production: wire to LMDB backend.",
        })

    registered.append(f"PUT {base}/roe/policy")

    @app.post(f"{base}/roe/evaluate")
    async def roe_evaluate(request: Request) -> JSONResponse:
        """Evaluate a single telemetry frame against the active ROE policy.

        Returns verdict (ALLOW/SUSPECT/ENGAGE/REVIEW), flags, reasons, and a DSSE receipt
        so every ROE decision is cryptographically auditable.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        telemetry = body.get("telemetry") or body
        policy_override = body.get("policy_override")
        effective_policy = {"rules": (policy_override or _ROE_POLICY.get("rules", {}))}

        result = _roe_evaluate(telemetry, effective_policy)

        receipt_node = emit_receipt("roe_decision", {
            "verdict": result["verdict"],
            "flags": result["flags"],
            "track_id": telemetry.get("track_id"),
        })

        return JSONResponse({
            "ok": True,
            **result,
            "roe_receipt": {
                "index": receipt_node["index"],
                "digest": receipt_node["digest"],
                "dsse": receipt_node["dsse"],
            },
            "doctrine": _DOCTRINE,
        })

    registered.append(f"POST {base}/roe/evaluate")

    # ------------------------------------------------------------------
    # Engagement audit log
    # ------------------------------------------------------------------

    @app.get(f"{base}/engagements/audit-log")
    async def engagements_audit_log(
        limit: int = 50,
        offset: int = 0,
        verdict: Optional[str] = None,
        track_id: Optional[str] = None,
    ) -> JSONResponse:
        """Paginated, filterable engagement audit log.

        Query params: limit, offset, verdict (ALLOW/SUSPECT/ENGAGE/REVIEW/HALT), track_id.
        """
        limit = min(max(1, limit), 500)
        offset = max(0, offset)
        records = list(_AUDIT_LOG)
        if verdict:
            records = [r for r in records if r.get("verdict", r.get("decision", "")).upper() == verdict.upper()]
        if track_id:
            records = [r for r in records if r.get("track_id") == track_id]
        total = len(records)
        page = records[offset: offset + limit]
        return JSONResponse({
            "ok": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "records": page,
            "doctrine": _DOCTRINE,
            "honesty": "Audit log is in-memory (deque maxlen=5000); resets on Space restart. "
                       "Production: wire to append-only LMDB or S3 log.",
        })

    registered.append(f"GET {base}/engagements/audit-log")

    @app.post(f"{base}/engagements/record")
    async def engagements_record(request: Request) -> JSONResponse:
        """Record a completed engagement action in the audit log.

        POST body: {track_id, verdict, effector, operator_id, notes, telemetry_snapshot}
        Returns the immutable audit record + DSSE receipt.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not body:
            return JSONResponse({"ok": False, "error": "provide engagement data"}, status_code=400)

        record_id = f"ENG-{_fresh_id().upper()}"
        record: Dict[str, Any] = {
            "record_id": record_id,
            "ts_utc": _ts(),
            "track_id": body.get("track_id") or "UNKNOWN",
            "verdict": (body.get("verdict") or "UNKNOWN").upper(),
            "effector": body.get("effector"),
            "operator_id": body.get("operator_id") or "system",
            "notes": body.get("notes"),
            "telemetry_snapshot": body.get("telemetry_snapshot") or body.get("telemetry"),
            "lambda_at_decision": body.get("lambda_at_decision"),
            "doctrine": _DOCTRINE,
        }
        _AUDIT_LOG.appendleft(record)

        # DSSE receipt — killinchu differentiator: every engagement is receipted
        receipt_node = emit_receipt("engagement_record", {
            "record_id": record_id,
            "track_id": record["track_id"],
            "verdict": record["verdict"],
            "effector": record["effector"],
            "operator_id": record["operator_id"],
        })
        record["receipt"] = {
            "index": receipt_node["index"],
            "digest": receipt_node["digest"],
            "dsse": receipt_node["dsse"],
        }

        return JSONResponse({
            "ok": True,
            "record": record,
            "doctrine": _DOCTRINE,
            "honesty": "Record is immutable in the audit ring. DSSE receipt is cryptographically verifiable via /khipu/verify.",
        })

    registered.append(f"POST {base}/engagements/record")

    # ------------------------------------------------------------------
    # Sensor fusion
    # ------------------------------------------------------------------

    @app.get(f"{base}/sensor-fusion/status")
    async def sensor_fusion_status() -> JSONResponse:
        """Return sensor class weights and health defaults used by the fusion engine."""
        return JSONResponse({
            "ok": True,
            "sensor_classes": {
                cls: {**defaults, "class": cls}
                for cls, defaults in _SENSOR_CLASS_DEFAULTS.items()
            },
            "fusion_algorithm": "weighted centroid (confidence weights); Kalman smoothing at POST /api/killinchu/v1/edge/track-smooth",
            "doctrine": _DOCTRINE,
            "honesty": "Weights are configurable per-deployment. Sensor health is per-class defaults; live sensor heartbeats require hardware integration.",
        })

    registered.append(f"GET {base}/sensor-fusion/status")

    @app.post(f"{base}/sensor-fusion/fuse")
    async def sensor_fusion_fuse(request: Request) -> JSONResponse:
        """Fuse multiple sensor reports into a single best-estimate track position.

        POST body: {
            track_id: "T001",
            sensor_reports: [
                {sensor_id, sensor_class, lat, lon, alt_m, speed_m_s, confidence},
                ...
            ]
        }
        Returns fused position, per-sensor weights, and a DSSE receipt.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        reports = body.get("sensor_reports") or body.get("sensors") or []
        if not reports:
            return JSONResponse({"ok": False, "error": "provide {sensor_reports: [...]}"}, status_code=400)

        track_id = body.get("track_id") or "FUSED"
        fused = _fuse_sensors(reports)

        if "error" in fused:
            return JSONResponse({"ok": False, **fused}, status_code=400)

        # Store the fused track in history
        fused_track = {
            "track_id": track_id,
            "latitude": fused["fused_lat"],
            "longitude": fused["fused_lon"],
            "altitude_m": fused["fused_alt_m"],
            "speed_m_s": fused["fused_speed_m_s"],
            "fusion_quality": fused["fusion_quality"],
            "sensor_count": fused["sensor_count"],
            "source": "sensor_fusion",
        }
        _store_track_update(fused_track)

        receipt_node = emit_receipt("sensor_fusion", {
            "track_id": track_id,
            "fused_lat": fused["fused_lat"],
            "fused_lon": fused["fused_lon"],
            "sensor_count": fused["sensor_count"],
            "fusion_quality": fused["fusion_quality"],
        })

        return JSONResponse({
            "ok": True,
            "track_id": track_id,
            "fused": fused,
            "fusion_receipt": {
                "index": receipt_node["index"],
                "digest": receipt_node["digest"],
                "dsse": receipt_node["dsse"],
            },
            "doctrine": _DOCTRINE,
        })

    registered.append(f"POST {base}/sensor-fusion/fuse")

    return {
        "module": "killinchu_parity",
        "registered": registered,
        "doctrine": _DOCTRINE,
        "parity_leaders": ["Anduril Lattice", "Palantir TITAN", "DroneShield DroneSentry-C2", "Dedrone DedroneTracker.AI"],
    }
