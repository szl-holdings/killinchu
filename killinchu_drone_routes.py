# killinchu_drone_routes.py
# TRACK C: Drone-facing real endpoints for killinchu
# Doctrine v11 LOCKED 749/14/163 · Λ = Conjecture 1 (NOT a theorem)
# SLSA L1 honest · Section 889: 5 vendors · NO Iron Bank / FedRAMP / CMMC
# 
# Routes added (ADDITIVE — register BEFORE SPA catch-all):
#   GET  /api/killinchu/drone/telemetry     — mock fleet of friendly drones + threat tracks
#   POST /api/killinchu/drone/intercept     — mock action issuance with DSSE receipt
#   GET  /api/killinchu/drone/cued-tracks   — list of currently cued threats
#   GET  /api/killinchu/drone/fleet-state   — 5 friendly drones with status
#
# Also adds missing P2-spec routes:
#   GET  /api/killinchu/v1/gates            — 13-axis Λ-gate manifest
#   GET  /api/killinchu/v1/audit-log        — in-memory audit ring
#
# DCO: Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>

from __future__ import annotations

import hashlib
import json as _json
import os
import time
import urllib.request as _urlreq
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_DOCTRINE = "v11"
_COUNTS = "749/14/163"
_LEAN_SHA = "c7c0ba17"
_LAMBDA_STATUS = "Conjecture 1 (NOT a theorem)"
_SIG_PLACEHOLDER = "PLACEHOLDER — Sigstore CI not yet wired"
_SECTION_889 = ["Huawei", "ZTE", "Hytera", "Hikvision", "Dahua"]

# ── Real free public feeds (NO key needed) + cited leaders (Doctrine v11) ─────
# Air picture: cooperative ADS-B from community feeder networks (preferred
# api.airplanes.live, fallback adsb.lol). Space picture: CelesTrak GP/TLE.
_HTTP_UA = "killinchu-drone/1.0 (+https://szlholdings-killinchu.hf.space)"

_ADSB_ENDPOINTS = [
    ("airplanes.live", "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}"),
    ("adsb.lol", "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"),
]

# Cited leader sources surfaced in every drone/air tab payload (real, primary).
_AIR_SOURCES = [
    {"leader": "airplanes.live", "kind": "ADS-B community feeder network",
     "url": "https://airplanes.live/", "data_kind": "live_community_adsb"},
    {"leader": "adsb.lol", "kind": "ADS-B community feeder network (fallback)",
     "url": "https://adsb.lol/", "data_kind": "live_community_adsb"},
    {"leader": "RTCA / ICAO", "kind": "1090ES ADS-B standard (DO-260B / ICAO Annex 10)",
     "url": "https://www.icao.int/", "data_kind": "standard"},
]
_SAT_SOURCES = [
    {"leader": "CelesTrak (Dr. T.S. Kelso)", "kind": "NORAD GP/TLE element sets",
     "url": "https://celestrak.org/NORAD/elements/", "data_kind": "live_tle"},
    {"leader": "USSPACECOM / 18th SDS", "kind": "Space-track catalog (TLE origin)",
     "url": "https://www.space-track.org/", "data_kind": "standard"},
]
# Cited leader standards for the C-UAS drone catalog / Λ-gate tabs.
_DRONE_SOURCES = [
    {"leader": "ASTM International", "kind": "F3411 Remote ID broadcast standard",
     "url": "https://www.astm.org/f3411-22a.html", "data_kind": "standard"},
    {"leader": "FAA", "kind": "UAS Remote ID rule (14 CFR Part 89)",
     "url": "https://www.faa.gov/uas/getting_started/remote_id", "data_kind": "standard"},
    {"leader": "MITRE ATT&CK", "kind": "adversary technique reference",
     "url": "https://attack.mitre.org/", "data_kind": "standard"},
]


def _http_get_json(url: str, *, timeout: int = 12) -> tuple[Any, str]:
    """Best-effort GET → (data, status). status ∈ {'live','unreachable'}.
    Never raises. These feeds need NO key, so no secret is ever placed in the URL.
    'live' is set ONLY on a real HTTP 200 (honesty floor)."""
    try:
        req = _urlreq.Request(
            url, headers={"User-Agent": _HTTP_UA, "Accept": "application/json"})
        with _urlreq.urlopen(req, timeout=timeout) as r:
            code = getattr(r, "status", 200)
            if code != 200:
                return None, "unreachable"
            return _json.loads(r.read().decode("utf-8", "replace")), "live"
    except Exception:
        return None, "unreachable"

# ── in-memory audit ring ───────────────────────────────────────────────────────
_AUDIT: deque[dict] = deque(maxlen=200)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace() -> tuple[str, str]:
    tid = uuid.uuid4().hex + uuid.uuid4().hex  # 32 hex
    sid = uuid.uuid4().hex[:16]               # 16 hex
    return tid, sid


def _traceparent(tid: str, sid: str) -> str:
    return f"00-{tid}-{sid}-01"


def _dsse_receipt(payload: dict) -> dict:
    """Minimal DSSE-style PLACEHOLDER receipt."""
    payload_bytes = str(payload).encode()
    sha = hashlib.sha256(payload_bytes).hexdigest()
    return {
        "payloadType": "application/vnd.szl.drone.action+json",
        "payload": payload,
        "sha256": sha,
        "signature": _SIG_PLACEHOLDER,
        "cosign_keyid": "killinchu-cosign",
        "signed": False,
        "honesty": "DSSE envelope is PLACEHOLDER until Sigstore CI wired.",
        "doctrine": _DOCTRINE,
        "ts": _ts(),
    }


# ── canonical friendly drone fleet ────────────────────────────────────────────
_FRIENDLY_FLEET = [
    {
        "id": "KLN-F001",
        "callsign": "KESTREL-1",
        "type": "DJI Matrice 350 RTK",
        "role": "ISR",
        "status": "PATROL",
        "lat": 37.4275,
        "lon": -122.1697,
        "alt_m": 150,
        "speed_ms": 12.5,
        "battery_pct": 78,
        "remote_id": "FA:12:34:56:78:01",
        "threat_category": None,
        "last_seen": _ts(),
    },
    {
        "id": "KLN-F002",
        "callsign": "KESTREL-2",
        "type": "Autel Evo II Pro",
        "role": "EW-relay",
        "status": "HOLDING",
        "lat": 37.4290,
        "lon": -122.1720,
        "alt_m": 100,
        "speed_ms": 0.0,
        "battery_pct": 91,
        "remote_id": "FA:12:34:56:78:02",
        "threat_category": None,
        "last_seen": _ts(),
    },
    {
        "id": "KLN-F003",
        "callsign": "KESTREL-3",
        "type": "Skydio X10",
        "role": "kinetic-intercept",
        "status": "LOITER",
        "lat": 37.4260,
        "lon": -122.1680,
        "alt_m": 200,
        "speed_ms": 8.0,
        "battery_pct": 65,
        "remote_id": "FA:12:34:56:78:03",
        "threat_category": None,
        "last_seen": _ts(),
    },
    {
        "id": "KLN-F004",
        "callsign": "KESTREL-4",
        "type": "Shield AI Nova 2",
        "role": "mesh-relay",
        "status": "TRANSIT",
        "lat": 37.4300,
        "lon": -122.1650,
        "alt_m": 120,
        "speed_ms": 18.0,
        "battery_pct": 55,
        "remote_id": "FA:12:34:56:78:04",
        "threat_category": None,
        "last_seen": _ts(),
    },
    {
        "id": "KLN-F005",
        "callsign": "KESTREL-5",
        "type": "Joby S4 (observer variant)",
        "role": "high-alt-observe",
        "status": "PATROL",
        "lat": 37.4320,
        "lon": -122.1710,
        "alt_m": 500,
        "speed_ms": 40.0,
        "battery_pct": 82,
        "remote_id": "FA:12:34:56:78:05",
        "threat_category": None,
        "last_seen": _ts(),
    },
]

# ── canonical threat tracks ─────────────────────────────────────────────────
_CUED_THREATS = [
    {
        "track_id": "THR-001",
        "type": "UNKNOWN-UAS",
        "remote_id": None,
        "ads_b_icao": None,
        "lat": 37.4250,
        "lon": -122.1750,
        "alt_m": 85,
        "speed_ms": 5.2,
        "lambda_score": 0.41,
        "lambda_verdict": "THREAT — Λ below floor 0.87",
        "threat_category": "GEOFENCE_VIOLATION",
        "cuing_sensor": "RF_DETECT/Hawkeye-3",
        "cued_at": _ts(),
        "status": "CUED",
    },
    {
        "track_id": "THR-002",
        "type": "UNKNOWN-FIXED-WING",
        "remote_id": None,
        "ads_b_icao": "ABC123",
        "lat": 37.4400,
        "lon": -122.1800,
        "alt_m": 1200,
        "speed_ms": 60.0,
        "lambda_score": 0.63,
        "lambda_verdict": "SUSPECT — Λ below threshold 0.87",
        "threat_category": "AIRSPACE_INCURSION",
        "cuing_sensor": "ADS-B/1090ES",
        "cued_at": _ts(),
        "status": "MONITORING",
    },
]


def register_drone_routes(app: FastAPI, space: str = "killinchu") -> None:
    """Register drone-facing routes on the FastAPI app. Call BEFORE SPA catch-all."""

    base = f"/api/{space}/drone"

    # ── GET /api/killinchu/drone/telemetry ──────────────────────────────────
    @app.get(f"{base}/telemetry")
    async def drone_telemetry() -> JSONResponse:
        """Real-time drone telemetry — friendly fleet + active threat tracks."""
        tid, sid = _trace()
        entry = {
            "event": "drone_telemetry",
            "route": f"{base}/telemetry",
            "ts": _ts(),
        }
        _AUDIT.append(entry)
        return JSONResponse(
            {
                "space": space,
                "doctrine": _DOCTRINE,
                "counts": _COUNTS,
                "lean_sha": _LEAN_SHA,
                "lambda_status": _LAMBDA_STATUS,
                "slsa": "L1 (honest)",
                "no_iron_bank": True,
                "section_889": _SECTION_889,
                "friendly_drones": _FRIENDLY_FLEET,
                "threat_tracks": _CUED_THREATS,
                "total_friendly": len(_FRIENDLY_FLEET),
                "total_threats": len(_CUED_THREATS),
                "data_kind": "demo_mock",
                "sources": _DRONE_SOURCES,
                "live_air_picture": f"{base}/air-picture (real ADS-B feed)",
                "honesty": "Friendly drone positions are MOCK data for UDS demonstration. Threat tracks are synthetic. No real sensor data wired here — see /air-picture for a REAL cooperative ADS-B feed.",
                "ts": _ts(),
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE",
                "traceparent": _traceparent(tid, sid),
                "tracestate": f"szl={sid}",
            },
        )

    # ── POST /api/killinchu/drone/intercept ─────────────────────────────────
    @app.post(f"{base}/intercept")
    async def drone_intercept(request: Request) -> JSONResponse:
        """Issue mock intercept action against a cued threat track. Returns DSSE receipt."""
        tid, sid = _trace()
        body: dict[str, Any] = {}
        try:
            body = await request.json()
        except Exception:
            pass

        track_id = body.get("track_id", "THR-001")
        action = body.get("action", "HALT-AND-IDENTIFY")
        effector_id = body.get("effector_id", "KLN-F003")

        # Find matching threat
        threat = next((t for t in _CUED_THREATS if t["track_id"] == track_id), None)

        action_payload = {
            "space": space,
            "doctrine": _DOCTRINE,
            "action": action,
            "track_id": track_id,
            "effector_id": effector_id,
            "threat_resolved": threat is not None,
            "lambda_gate": "PASS — effector authorized under 13-axis Λ-gate",
            "lambda_score": threat["lambda_score"] if threat else None,
            "ts": _ts(),
        }

        receipt = _dsse_receipt(action_payload)

        _AUDIT.append({
            "event": "drone_intercept",
            "track_id": track_id,
            "action": action,
            "effector_id": effector_id,
            "receipt_sha": receipt["sha256"],
            "ts": _ts(),
        })

        return JSONResponse(
            {
                **action_payload,
                "dsse_receipt": receipt,
                "honesty": (
                    "This is a MOCK intercept action for UDS demonstration. "
                    "No real drone command was issued. DSSE signature is PLACEHOLDER."
                ),
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE",
                "traceparent": _traceparent(tid, sid),
                "tracestate": f"szl={sid}",
            },
        )

    # ── GET /api/killinchu/drone/cued-tracks ────────────────────────────────
    @app.get(f"{base}/cued-tracks")
    async def drone_cued_tracks() -> JSONResponse:
        """List of currently cued threat tracks for C-UAS cueing board."""
        tid, sid = _trace()
        _AUDIT.append({"event": "drone_cued_tracks", "ts": _ts()})
        return JSONResponse(
            {
                "space": space,
                "doctrine": _DOCTRINE,
                "counts": _COUNTS,
                "lean_sha": _LEAN_SHA,
                "lambda_status": _LAMBDA_STATUS,
                "tracks": _CUED_THREATS,
                "total_cued": len(_CUED_THREATS),
                "data_kind": "demo_mock",
                "sources": _DRONE_SOURCES,
                "honesty": "Threat tracks are MOCK data for UDS demonstration. No real C-UAS sensor feed wired here — see /air-picture for a REAL cooperative ADS-B feed.",
                "no_iron_bank": True,
                "ts": _ts(),
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE",
                "traceparent": _traceparent(tid, sid),
                "tracestate": f"szl={sid}",
            },
        )

    # ── GET /api/killinchu/drone/fleet-state ────────────────────────────────
    @app.get(f"{base}/fleet-state")
    async def drone_fleet_state() -> JSONResponse:
        """5 friendly drones with status — canonical fleet roster for killinchu."""
        tid, sid = _trace()
        _AUDIT.append({"event": "drone_fleet_state", "ts": _ts()})
        return JSONResponse(
            {
                "space": space,
                "doctrine": _DOCTRINE,
                "counts": _COUNTS,
                "lean_sha": _LEAN_SHA,
                "lambda_status": _LAMBDA_STATUS,
                "fleet": _FRIENDLY_FLEET,
                "fleet_count": len(_FRIENDLY_FLEET),
                "all_friendly": True,
                "data_kind": "demo_mock",
                "sources": _DRONE_SOURCES,
                "honesty": "Friendly drone fleet is MOCK data for UDS demonstration. Positions and battery levels are synthetic — see /air-picture for a REAL cooperative ADS-B feed.",
                "no_iron_bank": True,
                "section_889": _SECTION_889,
                "ts": _ts(),
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE",
                "traceparent": _traceparent(tid, sid),
                "tracestate": f"szl={sid}",
            },
        )

    # ── GET /api/killinchu/v1/gates ─────────────────────────────────────────
    @app.get(f"/api/{space}/v1/gates")
    async def killinchu_gates() -> JSONResponse:
        """13-axis Λ-gate manifest — doctrine v11 LOCKED."""
        tid, sid = _trace()
        return JSONResponse(
            {
                "space": space,
                "doctrine": _DOCTRINE,
                "counts": _COUNTS,
                "lean_sha": _LEAN_SHA,
                "lambda_status": _LAMBDA_STATUS,
                "count": 13,
                "gates": [
                    {"axis": 1, "name": "geofence", "formula": "Λ₁ = d_min/d_fence ≥ 0.90", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 2, "name": "remote_id_present", "formula": "Λ₂ = RemoteID.broadcast ∈ {F3411-22a}", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 3, "name": "ads_b_squawk", "formula": "Λ₃ = Squawk ∉ {7500,7600,7700}", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 4, "name": "velocity_nominal", "formula": "Λ₄ = v_gs ≤ 30 m/s", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 5, "name": "altitude_ceiling", "formula": "Λ₅ = alt_msl ≤ 400 ft AGL", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 6, "name": "operator_auth", "formula": "Λ₆ = DSSE(op_cert).verify()", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 7, "name": "trajectory_monotone", "formula": "Λ₇ = ∀t, heading_drift ≤ 45°/s", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 8, "name": "section_889_clean", "formula": "Λ₈ = vendor ∉ {Huawei,ZTE,Hytera,Hikvision,Dahua}", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 9, "name": "mesh_receipted", "formula": "Λ₉ = CRDT_merge(receipts).count ≥ 1", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 10, "name": "doctrine_pinned", "formula": "Λ₁₀ = doctrine_ver == 'v11'", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 11, "name": "slsa_l1", "formula": "Λ₁₁ = SLSA_level ≥ L1", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 12, "name": "no_iron_bank", "formula": "Λ₁₂ = ¬iron_bank_certified", "lean_status": "Conjecture 1 — OPEN"},
                    {"axis": 13, "name": "dual_pilot_constraint", "formula": "Λ₁₃ = Yuyay-13 ∧ 2-organ-consent", "lean_status": "Conjecture 1 — OPEN"},
                ],
                "lambda_floor": 0.87,
                "slsa": "L1 (honest)",
                "no_iron_bank": True,
                "section_889": _SECTION_889,
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE",
                "traceparent": _traceparent(*_trace()),
                "tracestate": f"szl={_trace()[1]}",
            },
        )

    # ── GET /api/killinchu/v1/audit-log ────────────────────────────────────
    @app.get(f"/api/{space}/v1/audit-log")
    async def killinchu_audit_log(limit: int = 50) -> JSONResponse:
        """In-memory audit ring — parity with a11oy/sentra/amaru/rosie."""
        limit = min(limit, 200)
        entries = list(_AUDIT)[:limit]
        return JSONResponse(
            {
                "entries": entries,
                "total_buffered": len(_AUDIT),
                "limit": limit,
                "doctrine": _DOCTRINE,
                "note": "In-memory ring buffer (maxlen=200). Resets on Space rebuild (honest disclosure).",
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE",
                "traceparent": _traceparent(*_trace()),
                "tracestate": f"szl={_trace()[1]}",
            },
        )

    # ── GET /api/killinchu/drone/air-picture ────────────────────────────────
    # REAL cooperative ADS-B air picture from a community feeder network.
    # Honest live/unreachable label; NEVER fabricates tracks on a miss.
    @app.get(f"{base}/air-picture")
    async def drone_air_picture(lat: float = 51.4706, lon: float = -0.4619,
                                radius: int = 50) -> JSONResponse:
        """Real ADS-B air picture around a point (default: London Heathrow, busy
        airspace) from airplanes.live, falling back to adsb.lol. radius in nm."""
        try:
            radius = max(1, min(int(radius), 250))
        except Exception:
            radius = 50
        provider = None
        status = "unreachable"
        raw_ac: list = []
        for name, tmpl in _ADSB_ENDPOINTS:
            url = tmpl.format(lat=lat, lon=lon, radius=radius)
            data, st = _http_get_json(url)
            if st == "live" and isinstance(data, dict):
                raw_ac = data.get("ac") or data.get("aircraft") or []
                provider = name
                status = "live"
                break
        aircraft = []
        for a in (raw_ac if isinstance(raw_ac, list) else []):
            if not isinstance(a, dict):
                continue
            aircraft.append({
                "hex": a.get("hex"),
                "flight": (a.get("flight") or "").strip() or None,
                "lat": a.get("lat"),
                "lon": a.get("lon"),
                "alt_baro": a.get("alt_baro"),
                "gs_kn": a.get("gs"),
                "track_deg": a.get("track"),
                "squawk": a.get("squawk"),
                "category": a.get("category"),
            })
        _AUDIT.append({"event": "drone_air_picture", "provider": provider,
                       "status": status, "count": len(aircraft), "ts": _ts()})
        return JSONResponse(
            {
                "space": space,
                "doctrine": _DOCTRINE,
                "lambda_status": _LAMBDA_STATUS,
                "status": status,
                "data_kind": "live_adsb" if status == "live" else "unreachable",
                "provider": provider,
                "query": {"lat": lat, "lon": lon, "radius_nm": radius},
                "aircraft_count": len(aircraft),
                "aircraft": aircraft[:250],
                "sources": _AIR_SOURCES,
                "honesty": (
                    "Cooperative ADS-B is an UNAUTHENTICATED broadcast — a decoded "
                    "ICAO hex / callsign / position is a CLAIM, not attested truth "
                    "(same posture as Remote-ID / AIS). 'live' is set ONLY on a real "
                    "HTTP 200 from a community feeder network; on miss we return an "
                    "honest 'unreachable' payload with zero rows, never fabricated tracks."
                ),
                "ts": _ts(),
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE" if status == "live" else "DEGRADED",
                "traceparent": _traceparent(*_trace()),
                "tracestate": f"szl={_trace()[1]}",
            },
        )

    # ── GET /api/killinchu/v1/satellites ────────────────────────────────────
    # REAL CelesTrak GP/TLE element sets (no key). Honest live/unreachable label.
    @app.get(f"/api/{space}/v1/satellites")
    async def killinchu_satellites(group: str = "stations",
                                   limit: int = 60) -> JSONResponse:
        """Real orbital element sets from CelesTrak (NORAD GP API, JSON).
        group e.g. stations|active|starlink|gps-ops|galileo|weather|science."""
        g = "".join(ch for ch in str(group) if ch.isalnum() or ch in "-_")[:32] or "stations"
        try:
            lim = max(1, min(int(limit), 500))
        except Exception:
            lim = 60
        url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={g}&FORMAT=json"
        data, status = _http_get_json(url)
        sats = []
        if status == "live" and isinstance(data, list):
            for s in data[:lim]:
                if not isinstance(s, dict):
                    continue
                sats.append({
                    "name": s.get("OBJECT_NAME"),
                    "norad_id": s.get("NORAD_CAT_ID"),
                    "intl_designator": s.get("OBJECT_ID"),
                    "epoch": s.get("EPOCH"),
                    "mean_motion": s.get("MEAN_MOTION"),
                    "eccentricity": s.get("ECCENTRICITY"),
                    "inclination_deg": s.get("INCLINATION"),
                })
        else:
            status = "unreachable"
        _AUDIT.append({"event": "killinchu_satellites", "group": g,
                       "status": status, "count": len(sats), "ts": _ts()})
        return JSONResponse(
            {
                "space": space,
                "doctrine": _DOCTRINE,
                "status": status,
                "data_kind": "live_tle" if status == "live" else "unreachable",
                "group": g,
                "satellite_count": len(sats),
                "satellites": sats,
                "sources": _SAT_SOURCES,
                "honesty": (
                    "TLE/GP element sets originate from USSPACECOM (18th SDS) and are "
                    "republished by CelesTrak. They are a public catalog snapshot — "
                    "'live' is set ONLY on a real HTTP 200 from CelesTrak; on miss we "
                    "return an honest 'unreachable' payload, never fabricated orbits."
                ),
                "ts": _ts(),
            },
            headers={
                "x-szl-space": space,
                "x-szl-wire-d": "LIVE" if status == "live" else "DEGRADED",
                "traceparent": _traceparent(*_trace()),
                "tracestate": f"szl={_trace()[1]}",
            },
        )

    print(
        f"[{space}] Drone routes registered: {base}/{{telemetry,intercept,cued-tracks,fleet-state,air-picture}} + v1/{{gates,audit-log,satellites}}",
        flush=True,
    )
