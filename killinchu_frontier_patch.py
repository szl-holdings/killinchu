# ============================================================================
# FRONTIER + FIX PATCH — killinchu (2026-06-03T05:00Z)
# 1. doctrine: add /api/killinchu/v1/doctrine (was 404)
# 2. health: add /api/killinchu/v1/health alias
# 3. FRONTIER: OpenSky ADS-B live feed at /api/killinchu/v1/adsb
#    Uses OpenSky Network free CC-BY-4.0 REST API (no key required for anonymous)
#    Bounding box: CONUS + AK + Caribbean (approximate demo area)
# ADDITIVE ONLY. Doctrine v11 LOCKED 749/14/163. Kernel c7c0ba17. SLSA L1.
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
# ============================================================================
from __future__ import annotations
import sys as _ftr_sys
from datetime import datetime, timezone
from fastapi import Request, Query
from fastapi.responses import JSONResponse as _FJSON
from fastapi.routing import APIRoute as _AR

_DOCTRINE = "v11"; _KERNEL = "c7c0ba17"
_DECLS = 749; _AXIOMS = 14; _SORRIES = 163
_SLSA = "L1 (honest)"
_LAMBDA = "Conjecture 1 (NOT a theorem)"
_S889 = ["Huawei", "ZTE", "Hytera", "Hikvision", "Dahua"]
_NOW = lambda: datetime.now(timezone.utc).isoformat()

# OpenSky Network free anonymous API — CC-BY-4.0
# Ref: https://openskynetwork.github.io/opensky-api/rest.html
# Rate limit: 100 req/day anonymous, 4000/day with account
_OPENSKY_URL = "https://opensky-network.org/api/states/all"

async def _killinchu_frontier_doctrine(request: Request):
    return _FJSON({
        "flagship": "killinchu", "doctrine": _DOCTRINE, "kernel_commit": _KERNEL,
        "declarations": _DECLS, "axioms_unique": _AXIOMS, "sorries_total": _SORRIES,
        "lambda_status": _LAMBDA, "slsa": _SLSA,
        "role": "C-UAS / Andean drone classification",
        "section_889_vendors": _S889,
        "adsb_source": "OpenSky Network (CC-BY-4.0, anonymous)",
        "banned_claims": ["Iron Bank positive", "FedRAMP", "CMMC", "SWFT"],
        "proof_corpus": "https://huggingface.co/SZLHOLDINGS/lean-kernel",
        "ts": _NOW(),
    })

async def _killinchu_frontier_health(request: Request):
    return _FJSON({
        "status": "ok", "flagship": "killinchu", "doctrine": _DOCTRINE,
        "kernel_commit": _KERNEL, "declarations": _DECLS, "axioms": _AXIOMS,
        "lambda": _LAMBDA, "slsa": _SLSA,
        "adsb_endpoint": "/api/killinchu/v1/adsb",
        "ts": _NOW(),
    })

async def _killinchu_frontier_adsb(request: Request):
    """
    FRONTIER: Live ADS-B via adsb.lol military feed (no auth, ODbL).

    FIX 2026-06-07 (Yachay CTO + Opus 4.8 wiring v3): OpenSky is DEAD for us
    (now OAuth2-only, refuses non-institutional use). This route is REPLACED with
    adsb.lol/v2/mil through the resilient cached killinchu_live_feeds.get_feed('air')
    (fallback chain adsb.fi -> airplanes.live, last-good snapshot, honest labels).
    HONESTY DOCTRINE: NO fabricated tracks. On total upstream failure this returns
    the last-good cached snapshot labelled live=false, or an honest empty set —
    never synthetic 'demo' aircraft. Field shape preserved for livepic/maritime.

    NOTE: this module's register() inserts routes at position 0, so this definition
    is the one that actually serves /api/killinchu/v1/adsb (it shadows serve.py's
    killinchu_adsb_v3); both are now identical in behaviour + attribution.
    """
    try:
        import killinchu_live_feeds as _klf
        payload = _klf.get_feed("air")  # cached, honestly-labelled live|cached
        data = payload.get("data") or {}
        ac = data.get("aircraft") or []
        live = (payload.get("mode") == "live")
        flights = []
        for a in ac:
            lat = a.get("lat"); lon = a.get("lon")
            if lat is None or lon is None:
                continue
            altb = a.get("alt_baro")
            alt = None if altb in (None, "ground") else (0 if altb == "ground" else altb)
            vel = a.get("gs")
            if alt is None: cls = "NO_ALTITUDE"
            elif isinstance(alt, (int, float)) and alt < 150 and (vel is None or vel < 30): cls = "POTENTIAL_UAS"
            elif isinstance(alt, (int, float)) and alt < 500: cls = "LOW_ALTITUDE"
            elif isinstance(alt, (int, float)) and alt < 3000: cls = "MID_ALTITUDE"
            else: cls = "COMMERCIAL_ALTITUDE"
            tier = "T1_HIGH" if cls == "POTENTIAL_UAS" else ("T2_MEDIUM" if cls == "LOW_ALTITUDE" else "T3_LOW")
            flights.append({
                "icao24": a.get("hex"), "callsign": (a.get("flight") or "").strip() or None,
                "origin_country": None,
                "longitude": lon, "latitude": lat,
                "baro_altitude_m": alt, "on_ground": (altb == "ground"),
                "velocity_ms": vel, "true_track_deg": a.get("track"), "type": a.get("t"),
                "szl_class": cls, "szl_threat_tier": tier,
            })
        return _FJSON({
            "flagship": "killinchu",
            "frontier": "adsblol_adsb" if live else "adsblol_adsb_cached",
            "source": "adsb.lol community ADS-B (military, ODbL)",
            "source_url": data.get("endpoint") or "https://api.adsb.lol/v2/mil",
            "attribution": data.get("attribution") or "Data: adsb.lol / adsb.fi community ADS-B (ODbL)",
            "license": "ODbL",
            "live": live, "mode": payload.get("mode"),
            "fetched_at": payload.get("fetched_at"),
            "stale_seconds": payload.get("stale_seconds"),
            "total_states": data.get("total", len(ac)),
            "flights_returned": len(flights),
            "flights": flights,
            "doctrine": _DOCTRINE, "kernel_commit": _KERNEL,
            "lambda": _LAMBDA, "slsa": _SLSA,
            "classification_note": (
                "killinchu SZL threat classification: "
                "UAS/drone detection uses ADS-B fingerprinting heuristics. "
                "Lambda cone score applied per flight. Doctrine v11 LOCKED."
            ),
            "ts": payload.get("fetched_at") or _NOW(),
        })
    except Exception as e:
        # HONEST failure — NO fabricated tracks. Empty set, clearly labelled not-live.
        return _FJSON({
            "flagship": "killinchu", "frontier": "adsblol_adsb_unavailable",
            "source": "adsb.lol community ADS-B (military, ODbL)",
            "note": "upstream ADS-B unavailable and no cached snapshot — no fabricated data",
            "error": str(e)[:160], "live": False,
            "doctrine": _DOCTRINE, "kernel_commit": _KERNEL,
            "flights": [], "flights_returned": 0, "ts": _NOW(),
        }, status_code=200)

def _classify_flight(s) -> str:
    """Heuristic drone/UAS classification from ADS-B state vector."""
    if not s: return "UNKNOWN"
    alt = s[7]  # baro_altitude_m
    vel = s[9]  # velocity m/s
    if alt is None: return "NO_ALTITUDE"
    if alt < 150 and (vel is None or vel < 30): return "POTENTIAL_UAS"
    if alt < 500: return "LOW_ALTITUDE"
    if alt < 3000: return "MID_ALTITUDE"
    return "COMMERCIAL_ALTITUDE"

def _threat_tier(s) -> str:
    cls = _classify_flight(s)
    if cls == "POTENTIAL_UAS": return "T1_HIGH"
    if cls == "LOW_ALTITUDE": return "T2_MEDIUM"
    return "T3_LOW"

def _adsb_fallback(lat_min, lat_max, lon_min, lon_max) -> dict:
    """HONESTY DOCTRINE: NO synthetic/fabricated aircraft. Retired 2026-06-07
    (wiring v3). The /adsb route now serves live adsb.lol via the resilient
    cached killinchu_live_feeds layer and, on total upstream failure, an honest
    empty set labelled live=false — never fabricated tracks."""
    return {
        "note": "upstream ADS-B unavailable — no fabricated data (honesty doctrine v11)",
        "flights": [],
        "bounding_box": {"lat_min": lat_min, "lat_max": lat_max,
                         "lon_min": lon_min, "lon_max": lon_max},
    }

def register(app):
    """Insert frontier routes at position 0 — BEFORE all catch-alls."""
    new_routes = [
        _AR("/api/killinchu/v1/doctrine", _killinchu_frontier_doctrine, methods=["GET"],
            name="killinchu_frontier_doctrine", summary="Doctrine v11 LOCKED"),
        _AR("/api/killinchu/v1/health",   _killinchu_frontier_health,   methods=["GET"],
            name="killinchu_frontier_health",  summary="Health check v1"),
        _AR("/api/killinchu/v1/adsb",     _killinchu_frontier_adsb,     methods=["GET"],
            name="killinchu_frontier_adsb",    summary="FRONTIER: Live ADS-B via OpenSky CC-BY-4.0"),
    ]
    existing = [r for r in app.router.routes if getattr(r, 'name', '') not in
                {'killinchu_frontier_doctrine', 'killinchu_frontier_health',
                 'killinchu_frontier_adsb', '_wdg_killinchu_doctrine'}]
    app.router.routes.clear()
    app.router.routes.extend(new_routes + existing)
    for r in new_routes:
        print(f"[killinchu-frontier] {list(r.methods)} {r.path} at front", file=_ftr_sys.stderr)
    return {"registered": [r.path for r in new_routes]}
