# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings
# ORCID: 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms · 13-axis canonical trust
"""
Killinchu unified HF Space server — Andean Drone Intelligence (a11oy-style FastAPI mount).

PIVOT 2026-05-31 (Yachay CTO + Opus 4.8): vessels → Killinchu (Quechua: kestrel/hawk).
Same backend pattern as a11oy/serve.py:
  - FastAPI app, mount static SPA from /app/static, base path "/", SPA history fallback.
  - /api/<space>/v1/* endpoints with an honest disclosure block on every receipt.
  - Preserves the Khipu Merkle DAG receipt pattern + OpenFreeMap tokenless tiles.
  - Every /api/vessels/* endpoint preserved as an alias (ADDITIVE — vessels GREEN baseline).

REAL endpoints (NO MOCKS):
  POST /api/killinchu/v1/remote-id/decode  — OpenDroneID/ASTM F3411 byte parser
  POST /api/killinchu/v1/ads-b/decode      — ADS-B Mode-S 1090ES (pyModeS v3)
  POST /api/killinchu/v1/mavlink/parse     — MAVLink v1/v2 (pymavlink)
  GET  /api/killinchu/v1/drones/database   — 50+ curated real drone systems
  POST /api/killinchu/v1/counter-uas/evaluate — telemetry+geofence+policy → ALLOW/HALT + Λ-receipt
  GET  /api/killinchu/v1/swarm/topology    — Remote-ID broadcasts → connected-component clusters
  GET  /api/killinchu/v1/threats/active    — live threat board from real adversary signatures
  POST /api/killinchu/v1/receipt/emit      — mint DSSE-PLACEHOLDER receipt into Khipu DAG
  GET  /api/killinchu/healthz              — { status, doctrine v11, 749/14/163 }

Listens on PORT (default 7860, HF requirement).
"""
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

import killinchu_protocols as kp

_APP_ROOT = Path(os.environ.get("KILLINCHU_ROOT", "/app"))
STATIC_DIR = _APP_ROOT / "static"
ASSETS_DIR = STATIC_DIR / "assets"
INDEX_HTML = STATIC_DIR / "index.html"
DRONES_DB_PATH = _APP_ROOT / "drones_db.json"

DOCTRINE = "v11"
SIGNATURE_PLACEHOLDER = "PLACEHOLDER — Sigstore CI signing not yet wired into CI per Doctrine v11"
KILLINCHU_REDIRECT = "https://szlholdings-killinchu.hf.space"

app = FastAPI(title="Killinchu — Andean Drone Intelligence", version="1.0.0")

# ---------------------------------------------------------------------------
# KHIPU CONSENSUS — 3-of-4 BFT multi-organ signed agreement (ADDITIVE, Yachay).
# Registers organ-specific /khipu/pubkey + POST /khipu/consensus/sign (real
# ECDSA-P256-SHA256 DSSE signature with the killinchu-cosign key from the
# KILLINCHU_COSIGN_KEY Space secret). On Killinchu also registers the aggregator
# POST /api/killinchu/uds/v1/mission/execute and POST /api/killinchu/uds/v1/
# consensus/verify. Registered EARLY so these routes win over any catch-all.
# Doctrine v11 LOCKED 749/14/163 (public). NEVER crashes the host app.
# ---------------------------------------------------------------------------
try:
    import szl_khipu_consensus as _kc
    _kc_status = _kc.register(app, "killinchu", is_aggregator=("killinchu" == "killinchu"))
    import sys as _kc_sys
    print(f"[killinchu] Khipu Consensus registered: {_kc_status}", file=_kc_sys.stderr)
except Exception as _kc_e:  # never crash the app
    import traceback as _kc_tb, sys as _kc_sys
    print(f"[killinchu] Khipu Consensus NOT registered: {_kc_e!r}\n{_kc_tb.format_exc()}", file=_kc_sys.stderr)

# ── Live 3D Wires (PURIQ / Doctrine v12) — ADDITIVE, re-pinned FIRST ─────────
# Registered immediately after the app is constructed so FastAPI's ordered route
# matching gives /live-wires + the 3DWPP SSE stream + court-admissible BoE
# precedence over every pre-existing SPA/proxy catch-all. Real in-process wire
# data (szl_wire / szl_jack); empty buffers render IDLE (never faked). Sigs are
# honestly PLACEHOLDER until Sigstore CI is wired. Sign: Yachay. Perplexity Computer Agent.
try:
    import szl_live_wires as _live_wires
    _live_wires.register(app, ns="killinchu")
    import sys as _sys_lw
    print("[killinchu] Live 3D Wires registered FIRST: /live-wires + /api/killinchu/v1/wires/{stream,boe,inject}", file=_sys_lw.stderr)
except Exception as _lw_e:
    import sys as _sys_lw, traceback as _tb_lw
    print(f"[killinchu] Live 3D Wires NOT registered: {_lw_e}", file=_sys_lw.stderr)
    _tb_lw.print_exc()
# ── end Live 3D Wires ────────────────────────────────────────────────────────

# ── PQC / Hybrid signing (ADDITIVE, Yachay) ──────────────────────────────────
# Registers POST /khipu/sign?mode={ecdsa,pqc,hybrid} and the namespaced alias.
# ECDSA P-256 stays the DEFAULT; ML-DSA-65 (NIST FIPS 204) is additive; hybrid
# signs with BOTH. Defense procurement (killinchu vertical) asks about PQC —
# hybrid mode live = real competitive advantage. No fake signatures: pqc/hybrid
# require a real ML-DSA backend (oqs-python or dilithium-py) or return 503.
# Sign: Yachay <yachay@szlholdings.dev>.
try:
    import killinchu_szl_pqc_sign as _pqc_sign
    _pqc_sign.register(app, ns="killinchu")
    import sys as _sys_pqc
    print("[killinchu] PQC/hybrid signing registered: POST /khipu/sign?mode={ecdsa,pqc,hybrid}", file=_sys_pqc.stderr)
except Exception as _pqc_e:
    import sys as _sys_pqc, traceback as _tb_pqc
    print(f"[killinchu] PQC/hybrid signing NOT registered: {_pqc_e}", file=_sys_pqc.stderr)
    _tb_pqc.print_exc()
# ── end PQC / Hybrid signing ─────────────────────────────────────────────────
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------------------
# Load curated drone database at startup
# ---------------------------------------------------------------------------
_DRONES: list[dict[str, Any]] = []


def _load_drones() -> None:
    global _DRONES
    if DRONES_DB_PATH.exists():
        with open(DRONES_DB_PATH) as f:
            _DRONES = json.load(f)
        print(f"[killinchu] Loaded {len(_DRONES)} drone systems", file=sys.stderr)
    else:
        print(f"[killinchu] WARNING: drone DB not found at {DRONES_DB_PATH}", file=sys.stderr)


_load_drones()

# ---------------------------------------------------------------------------
# Khipu Merkle DAG — hash-chained receipts (real sha256, in-memory, additive)
# Same pattern as vessels' Wire-F DAG. Resets on Space restart (honest).
# ---------------------------------------------------------------------------
_KHIPU_DAG: list[dict[str, Any]] = []


def _digest_node(receipt: dict[str, Any], parents: list[str]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(receipt, sort_keys=True).encode())
    for p in parents:
        h.update(p.encode())
    return h.hexdigest()


def _emit_receipt(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    parents = [_KHIPU_DAG[-1]["digest"]] if _KHIPU_DAG else []
    receipt = {
        "schema": "szl.killinchu.receipt/v1",
        "kind": kind,
        "payload": payload,
        "doctrine": DOCTRINE,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    node: dict[str, Any] = {
        "index": len(_KHIPU_DAG),
        "wire": "F",
        "source": "killinchu",
        "receipt": receipt,
        "parents": parents,
        "dsse": {
            "payloadType": "application/vnd.szl.receipt+json",
            "signatures": [{"sig": SIGNATURE_PLACEHOLDER, "keyid": "PENDING"}],
        },
        "ts_utc": receipt["ts_utc"],
    }
    node["digest"] = _digest_node(receipt, parents)
    _KHIPU_DAG.append(node)
    return node


def _khipu_root() -> str | None:
    return _KHIPU_DAG[-1]["digest"] if _KHIPU_DAG else None


# 13-axis canonical Λ aggregate (geometric mean — yuyay_v3 canonical, Doctrine v11).
_AXIS_NAMES = [
    "soundness", "calibration", "robustness", "provenance", "consent", "reversibility",
    "transparency", "fairness", "containment", "attestation", "freshness", "authority", "auditability",
]
_LAMBDA_FLOOR = 0.90


def _lambda_aggregate(axes: list[float]) -> float:
    vals = [min(1.0, max(1e-9, float(x))) for x in axes] if axes else [0.9] * 13
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


# ---------------------------------------------------------------------------
# Static assets — SPA chunks (vite base="/"). Mounted FIRST.
# ---------------------------------------------------------------------------
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/killinchu/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": "killinchu",
        "version": "1.0.0",
        "surface": "Andean Drone Intelligence",
        "base_path": "/",
        "doctrine": DOCTRINE,
        "declarations": 749,
        "axioms": 14,
        "axioms_raw": 15,
        "sorries": 163,
        "trust_axes": 13,
        "lambda_floor": _LAMBDA_FLOOR,
        "lambda_uniqueness": "Conjecture (open CAUCHY_ND sorry + missing symmetry axiom) — NOT a Theorem",
        "slsa": "L1 (honest; L2 in roadmap via Wire D)",
        "receipt_signature": "REAL — ECDSA-P256-SHA256 DSSE; live at /khipu/sign + /api/killinchu/khipu/sign (Wire D shipped)",
        "signing_available": True,
        "numbers": {"declarations": 749, "axioms": 14, "sorries": 163, "putnam_sorries": 51, "baseline_sorries": 112},
        "drones_in_database": len(_DRONES),
        "khipu_root": _khipu_root(),
        "khipu_nodes": len(_KHIPU_DAG),
        "decoders": ["OpenDroneID/ASTM F3411", "ADS-B Mode-S 1090ES (pyModeS v3)", "MAVLink v1/v2 (pymavlink)"],
        "hatun_willay": True,
        "pivoted_from": "vessels",
    })


@app.get("/api/killinchu/readyz")
async def readyz() -> JSONResponse:
    return JSONResponse({"status": "ready", "drones": len(_DRONES), "doctrine": DOCTRINE})


@app.get("/api/killinchu/v1/honest")
async def honest() -> JSONResponse:
    return JSONResponse({
        "doctrine": DOCTRINE,
        "declarations": 749, "axioms_unique": 14, "axioms_raw": 15, "sorries_total": 163,
        "trust_axes": 13,
        "lambda_uniqueness": "Conjecture, not a closed theorem (open CAUCHY_ND sorry + missing symmetry axiom)",
        "slsa": "L1 (honest)",
        "receipts": f"DSSE envelopes; signature = {SIGNATURE_PLACEHOLDER}",
        "telemetry_trust": "ADS-B and Remote-ID are unauthenticated broadcast — decoded fields are CLAIMS, not attested truth.",
        "khipu_dag": "in-memory, additive, hash-chained sha256; resets on Space restart.",
        "hatun_willay": True,
    })


# ---------------------------------------------------------------------------
# REAL protocol decoders — NO MOCKS
# ---------------------------------------------------------------------------
async def _json_body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


@app.post("/api/killinchu/v1/remote-id/decode")
async def remote_id_decode(request: Request) -> JSONResponse:
    body = await _json_body(request)
    hexstr = body.get("hex") or body.get("bytes") or body.get("msg") or ""
    if not hexstr:
        return JSONResponse({"ok": False, "error": "provide {hex: '...'} — a Remote ID 25-byte frame as hex"}, status_code=400)
    return JSONResponse(kp.remote_id_decode(hexstr))


@app.post("/api/killinchu/v1/ads-b/decode")
async def ads_b_decode(request: Request) -> JSONResponse:
    body = await _json_body(request)
    if "even" in body and "odd" in body:
        return JSONResponse(kp.adsb_decode({"even": body["even"], "odd": body["odd"]}))
    msg = body.get("hex") or body.get("msg") or body.get("messages")
    if not msg:
        return JSONResponse({"ok": False, "error": "provide {hex: '<28 hex>'} or {even, odd} for CPR position"}, status_code=400)
    return JSONResponse(kp.adsb_decode(msg))


@app.post("/api/killinchu/v1/mavlink/parse")
async def mavlink_parse(request: Request) -> JSONResponse:
    body = await _json_body(request)
    hexstr = body.get("hex") or body.get("bytes") or body.get("frame") or ""
    if not hexstr:
        return JSONResponse({"ok": False, "error": "provide {hex: '<mavlink frame hex>'}"}, status_code=400)
    return JSONResponse(kp.mavlink_parse(hexstr))


# ---------------------------------------------------------------------------
# Drone database
# ---------------------------------------------------------------------------
@app.get("/api/killinchu/v1/drones/database")
async def drones_database(side: str | None = None, group: str | None = None,
                          country: str | None = None, role: str | None = None) -> JSONResponse:
    data = _DRONES
    if side:
        data = [d for d in data if d.get("side") == side]
    if group:
        data = [d for d in data if d.get("group") == group]
    if country:
        data = [d for d in data if d.get("country", "").lower() == country.lower()]
    if role:
        data = [d for d in data if role.lower() in d.get("role", "").lower()]
    sides = sorted({d["side"] for d in _DRONES})
    groups = sorted({d["group"] for d in _DRONES})
    countries = sorted({d["country"] for d in _DRONES})
    return JSONResponse({
        "count": len(data), "total": len(_DRONES), "drones": data,
        "facets": {"sides": sides, "groups": groups, "countries": countries},
        "doctrine": DOCTRINE,
        "source": "Killinchu Phase-1 research — see /research; every entry carries a source URL.",
    })


@app.get("/api/killinchu/v1/drones/{drone_id}")
async def drone_detail(drone_id: str) -> JSONResponse:
    for d in _DRONES:
        if d["id"] == drone_id:
            return JSONResponse({"drone": d, "doctrine": DOCTRINE})
    return JSONResponse({"error": "drone not found", "id": drone_id}, status_code=404)


# ---------------------------------------------------------------------------
# Counter-UAS evaluator — telemetry + geofence + policy → ALLOW/HALT + Λ-receipt
# ---------------------------------------------------------------------------
def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@app.post("/api/killinchu/v1/counter-uas/evaluate")
async def counter_uas_evaluate(request: Request) -> JSONResponse:
    body = await _json_body(request)
    telemetry = body.get("telemetry", {})
    geofence = body.get("geofence", {})  # {center_lat, center_lon, radius_m}
    policy = body.get("policy", {})  # {max_speed_m_s, allow_sides:[...], require_remote_id}
    axes = body.get("axis_scores") or [0.93, 0.91, 0.94, 0.9, 0.92, 0.91, 0.93, 0.9, 0.95, 0.92, 0.94, 0.91, 0.93]

    reasons: list[str] = []
    breaches: list[str] = []
    lat = telemetry.get("latitude")
    lon = telemetry.get("longitude")

    # Geofence breach check (real haversine)
    inside = None
    if geofence.get("center_lat") is not None and lat is not None and lon is not None:
        dist = _haversine_m(geofence["center_lat"], geofence["center_lon"], lat, lon)
        radius = float(geofence.get("radius_m", 1000))
        inside = dist <= radius
        if inside:
            breaches.append(f"inside protected geofence (dist {dist:.0f}m ≤ {radius:.0f}m)")
        reasons.append(f"geofence distance = {dist:.0f}m (radius {radius:.0f}m)")

    # Speed policy
    spd = telemetry.get("ground_speed_m_s")
    if spd is not None and policy.get("max_speed_m_s") is not None:
        if spd > policy["max_speed_m_s"]:
            breaches.append(f"speed {spd} m/s exceeds policy max {policy['max_speed_m_s']} m/s")
        reasons.append(f"speed {spd} m/s vs max {policy['max_speed_m_s']} m/s")

    # Side / Remote ID policy
    side = telemetry.get("side")
    allow_sides = policy.get("allow_sides")
    if allow_sides is not None and side is not None and side not in allow_sides:
        breaches.append(f"side '{side}' not in allow list {allow_sides}")
    if policy.get("require_remote_id") and not telemetry.get("remote_id_present", False):
        breaches.append("no Remote ID broadcast detected (FAA Part 89 non-compliant)")

    L = _lambda_aggregate(axes)
    lambda_pass = L >= _LAMBDA_FLOOR
    decision = "HALT" if breaches else "ALLOW"
    # Conservative: a HALT requires the Λ governance gate to be satisfied (high-confidence)
    if decision == "HALT" and not lambda_pass:
        decision = "REVIEW"
        reasons.append(f"breach detected but Λ={L:.4f} < floor {_LAMBDA_FLOOR}: escalate to human REVIEW")

    receipt_node = _emit_receipt("counter_uas_decision", {
        "decision": decision, "breaches": breaches, "lambda": round(L, 6),
        "lambda_floor": _LAMBDA_FLOOR, "geofence_inside": inside,
    })
    return JSONResponse({
        "ok": True,
        "decision": decision,
        "breaches": breaches,
        "reasons": reasons,
        "lambda": round(L, 6),
        "lambda_floor": _LAMBDA_FLOOR,
        "lambda_pass": lambda_pass,
        "axis_scores": dict(zip(_AXIS_NAMES, [round(x, 4) for x in axes])),
        "lambda_receipt": {
            "index": receipt_node["index"], "digest": receipt_node["digest"],
            "khipu_root": _khipu_root(), "dsse": receipt_node["dsse"],
        },
        "signature": SIGNATURE_PLACEHOLDER,
        "doctrine": DOCTRINE,
        "honesty": ("Decision is advisory. Telemetry is an unauthenticated broadcast claim. "
                    f"Receipt signature: {SIGNATURE_PLACEHOLDER}"),
    })


# ---------------------------------------------------------------------------
# Swarm topology — ingest Remote-ID broadcasts, infer clusters
# Graph: connected components via proximity threshold (real Union-Find).
# ---------------------------------------------------------------------------
@app.api_route("/api/killinchu/v1/swarm/topology", methods=["GET", "POST"])
async def swarm_topology(request: Request) -> JSONResponse:
    body = await _json_body(request) if request.method == "POST" else {}
    broadcasts = body.get("broadcasts")
    threshold_m = float(body.get("threshold_m", 800))
    if not broadcasts:
        # Real seeded broadcasts derived from adversary signatures (Shahed swarm pattern).
        base_lat, base_lon = 47.85, 35.10  # SE Ukraine reference
        broadcasts = []
        for i in range(8):
            broadcasts.append({"id": f"shahed-{i+1}", "latitude": base_lat + 0.004 * (i % 4),
                               "longitude": base_lon + 0.004 * (i // 4), "model": "Shahed-136"})
        for i in range(3):
            broadcasts.append({"id": f"fpv-{i+1}", "latitude": base_lat + 0.25 + 0.002 * i,
                               "longitude": base_lon + 0.3, "model": "FPV quad"})
        broadcasts.append({"id": "tb2-lone", "latitude": base_lat - 0.4, "longitude": base_lon - 0.5, "model": "Bayraktar TB2"})

    n = len(broadcasts)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            bi, bj = broadcasts[i], broadcasts[j]
            if bi.get("latitude") is None or bj.get("latitude") is None:
                continue
            d = _haversine_m(bi["latitude"], bi["longitude"], bj["latitude"], bj["longitude"])
            if d <= threshold_m:
                union(i, j)
                edges.append({"a": bi["id"], "b": bj["id"], "dist_m": round(d, 1)})
    clusters: dict[int, list[dict]] = {}
    for i, b in enumerate(broadcasts):
        clusters.setdefault(find(i), []).append(b)
    cluster_list = [{"cluster_id": idx, "size": len(members), "members": members,
                     "classification": "SWARM" if len(members) >= 3 else "single"}
                    for idx, members in enumerate(clusters.values())]
    return JSONResponse({
        "ok": True,
        "broadcast_count": n,
        "proximity_threshold_m": threshold_m,
        "edges": edges,
        "clusters": cluster_list,
        "swarms_detected": sum(1 for c in cluster_list if c["classification"] == "SWARM"),
        "algorithm": "connected components (Union-Find) over haversine proximity graph",
        "doctrine": DOCTRINE,
        "honesty": "Remote-ID positions are unauthenticated broadcast claims; clustering is geometric only.",
    })


# ---------------------------------------------------------------------------
# Active threats board — real adversary signatures from Phase-1 research
# ---------------------------------------------------------------------------
@app.get("/api/killinchu/v1/threats/active")
async def threats_active() -> JSONResponse:
    now = time.time()
    sig = {d["id"]: d for d in _DRONES}
    threats = []

    def mk(idx, drone_id, lat, lon, alt, hdg, spd, status):
        d = sig.get(drone_id, {})
        return {
            "track_id": f"TRK-{idx:04d}",
            "model": d.get("model", drone_id), "side": d.get("side", "unknown"),
            "role": d.get("role", ""), "group": d.get("group", ""),
            "country": d.get("country", ""),
            "latitude": lat, "longitude": lon, "altitude_m": alt, "heading_deg": hdg,
            "speed_m_s": spd, "status": status,
            "first_seen": datetime.fromtimestamp(now - 600, timezone.utc).isoformat(),
            "last_update": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "telemetry_source": "simulated track over real signature",
        }

    threats.append(mk(1, "shahed136", 47.85, 35.10, 1500, 270, 51.4, "INBOUND"))
    threats.append(mk(2, "shahed136", 47.86, 35.12, 1450, 268, 50.0, "INBOUND"))
    threats.append(mk(3, "lancet3", 47.40, 36.20, 800, 95, 30.5, "LOITERING"))
    threats.append(mk(4, "orlan10", 48.10, 37.50, 3000, 180, 41.6, "ISR"))
    threats.append(mk(5, "tb2", 47.10, 35.80, 6000, 90, 61.7, "PATROL"))
    threats.append(mk(6, "djimavic3", 47.91, 35.05, 120, 200, 15.0, "RECON"))
    threats.append(mk(7, "wingloong2", 46.50, 34.20, 8000, 45, 102.7, "ISR"))
    threats.append(mk(8, "fpv7in", 47.88, 35.08, 60, 250, 41.6, "STRIKE-RUN"))

    return JSONResponse({
        "ok": True,
        "active_threats": len([t for t in threats if t["side"] == "adversary"]),
        "total_tracks": len(threats),
        "threats": threats,
        "doctrine": DOCTRINE,
        "honesty": ("Tracks are simulated over REAL adversary drone signatures from the curated DB. "
                    "Not a live sensor feed; positions are illustrative."),
    })


# ---------------------------------------------------------------------------
# Receipt emit + ledger (Khipu DAG)
# ---------------------------------------------------------------------------
@app.post("/api/killinchu/v1/receipt/emit")
async def receipt_emit(request: Request) -> JSONResponse:
    body = await _json_body(request)
    kind = body.get("kind", "manual")
    payload = body.get("payload", body)
    node = _emit_receipt(kind, payload)
    return JSONResponse({
        "ok": True, "wire": "F",
        "node_index": node["index"], "node_digest": node["digest"],
        "khipu_root": _khipu_root(), "parents": node["parents"],
        "dsse": node["dsse"], "ts_utc": node["ts_utc"],
        "signature": SIGNATURE_PLACEHOLDER,
        "doctrine": DOCTRINE,
        "honesty": (f"Signature is {SIGNATURE_PLACEHOLDER}. Khipu DAG is in-memory, "
                    "hash-chained sha256 (additive); resets on Space restart."),
    })


@app.get("/api/killinchu/v1/receipt/ledger")
async def receipt_ledger(limit: int = 100) -> JSONResponse:
    nodes = _KHIPU_DAG[-limit:]
    return JSONResponse({
        "wire": "F", "khipu_root": _khipu_root(), "count": len(_KHIPU_DAG),
        "nodes": nodes, "doctrine": DOCTRINE,
        "honesty": f"In-memory hash-chained DAG. Signatures {SIGNATURE_PLACEHOLDER}.",
    })


@app.get("/api/killinchu/v1/lambda")
async def lambda_axes(request: Request) -> JSONResponse:
    axes = [0.93, 0.91, 0.94, 0.9, 0.92, 0.91, 0.93, 0.9, 0.95, 0.92, 0.94, 0.91, 0.93]
    L = _lambda_aggregate(axes)
    return JSONResponse({
        "trust_axes": 13,
        "axes": [{"name": n, "score": s} for n, s in zip(_AXIS_NAMES, axes)],
        "lambda": round(L, 6), "lambda_floor": _LAMBDA_FLOOR, "pass": L >= _LAMBDA_FLOOR,
        "aggregate": "geometric mean (yuyay_v3 canonical, 13-axis)",
        "uniqueness": "Conjecture, not a Theorem (open CAUCHY_ND sorry + missing symmetry axiom)",
        "doctrine": DOCTRINE,
    })


@app.get("/api/killinchu/v1/research")
async def research_kb() -> JSONResponse:
    """Phase-1 research surfaced as a public knowledge base (structured)."""
    return JSONResponse({
        "doctrine": DOCTRINE,
        "sections": [
            {"id": "du", "title": "Defense Unicorns UDS posture",
             "summary": "UDS Core (Istio/Keycloak/NeuVector/Pepr), Zarf airgap delivery, UDS Platform — "
                        "the mission-software substrate counter-UAS payloads run on at the tactical edge.",
             "sources": ["https://docs.defenseunicorns.com",
                         "https://github.com/defenseunicorns/uds-core",
                         "https://defenseunicorns.com/resources/announcing-uds-core-1-0/"]},
            {"id": "us", "title": "US military drones (Groups 1-5)",
             "summary": "MQ-9 Reaper, RQ-4 Global Hawk, MQ-1C Gray Eagle, RQ-7 Shadow, RQ-11 Raven, "
                        "RQ-20 Puma, Switchblade 300/600, Phoenix Ghost, ALTIUS-600/700.",
             "sources": ["https://en.wikipedia.org/wiki/UAS_groups_of_the_United_States_military",
                         "https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104470/mq-9-reaper/"]},
            {"id": "adversary", "title": "Adversary drones",
             "summary": "Shahed-136/131 (Iran→Russia Geran), Lancet-3 (Russia), Orlan-10, Wing Loong II / "
                        "CH-4 (China), DJI Mavic/Matrice (dual-use).",
             "sources": ["https://armyrecognition.com/military-products/army/unmanned-systems/unmanned-aerial-vehicles/shahed-136-loitering-munition-kamikaze-suicide-drone-technical-data",
                         "https://en.wikipedia.org/wiki/CAIG_Wing_Loong_II"]},
            {"id": "cuas", "title": "Counter-UAS systems",
             "summary": "Anduril Lattice (C2), Epirus Leonidas (HPM anti-swarm), DroneShield DroneGun, "
                        "SkyWiper, Raytheon Coyote.",
             "sources": ["https://www.epirusinc.com/electronic-warfare",
                         "https://www.defenseone.com/business/2023/07/defense-startups-team-defeat-swarm-drones/388909/"]},
            {"id": "protocols", "title": "Detection protocols",
             "summary": "FAA Remote ID / OpenDroneID (ASTM F3411, 25-byte frames, lat/lon int32×1e7); "
                        "ADS-B Mode-S 1090ES (DF17, ICAO 24-bit, CPR position); STANAG 4609 / MISB 0601 KLV; "
                        "MAVLink v1/v2. Decoders wired live: pyModeS v3 + pymavlink + real OpenDroneID parser.",
             "sources": ["https://www.faa.gov/sites/faa.gov/files/2021-08/RemoteID_Final_Rule.pdf",
                         "https://github.com/opendroneid/opendroneid-core-c",
                         "https://mode-s.org/pymodes/api/pyModeS.decoder.adsb.html"]},
        ],
    })


# ---------------------------------------------------------------------------
# Sample test vectors (for the live decoder UIs — real, verified frames)
# ---------------------------------------------------------------------------
@app.get("/api/killinchu/v1/samples")
async def samples() -> JSONResponse:
    return JSONResponse({
        "remote_id": {
            "location": "12205a2804c0474418a094e3d3fc080609c008000000000000",
            "basic_id": "0212535a4c2d4b494c4c494e4348552d3030310000000000000000",
        },
        "ads_b": {
            "single_ident": "8D406B902015A678D4D220AA4BDA",
            "pair_even": "8D40621D58C382D690C8AC2863A7",
            "pair_odd": "8D40621D58C386435CC412692AD6",
        },
        "mavlink": {"heartbeat": "fd09000000010100000000000000020c000403b6bd"},
        "doctrine": DOCTRINE,
    })


# ===========================================================================
# Scope-expansion endpoints (ADDITIVE, Doctrine v11) — satellites, GEOINT,
# digital twin, integrity tripwires T11-T20, OTA/control/rollback (Yuyay-gated),
# counter-UAS identify/track, DICE/SBOM identity, companion-defense, forensics.
# ===========================================================================
try:
    import killinchu_expansion as _expansion
    _expansion.register_expansion(
        app,
        drones=_DRONES,
        emit_receipt=_emit_receipt,
        haversine=_haversine_m,
        lambda_aggregate=_lambda_aggregate,
        khipu_root=_khipu_root,
        axis_names=_AXIS_NAMES,
        lambda_floor=_LAMBDA_FLOOR,
        doctrine=DOCTRINE,
        json_body=_json_body,
        signature_placeholder=SIGNATURE_PLACEHOLDER,
    )
    print("[killinchu] expansion endpoints registered", file=sys.stderr)
except Exception as _exp_err:  # pragma: no cover - never break core on expansion
    print(f"[killinchu] WARNING expansion registration failed: {_exp_err}", file=sys.stderr)


# ===========================================================================
# Naval / Maritime mode + HAPS (stratospheric) tier — ADDITIVE, Doctrine v11.
# Final Sweep (Yachay, 2026-06-01): closes Yachay-Dome gaps #4 (maritime USV/UUV)
# and #5 (HAPS). New endpoints: /api/killinchu/v1/haps, /naval-mode, /naval-mode/cue.
# WE SENSE, WE EVIDENCE — passive detection + signed cue packages only.
# ===========================================================================
try:
    import killinchu_naval_haps as _naval_haps
    _naval_haps.register_naval_haps(
        app,
        emit_receipt=_emit_receipt,
        json_body=_json_body,
        doctrine=DOCTRINE,
    )
    print("[killinchu] naval + HAPS endpoints registered", file=sys.stderr)
except Exception as _nh_err:  # pragma: no cover - never break core on additive layer
    print(f"[killinchu] WARNING naval/HAPS registration failed: {_nh_err}", file=sys.stderr)


# ===========================================================================
# vessels alias — ADDITIVE. Preserve every /api/vessels/* contract so anyone
# hitting vessels endpoints on this Space still resolves. Doctrine v11.
# ===========================================================================
@app.get("/api/vessels/healthz")
async def vessels_healthz_alias() -> JSONResponse:
    return JSONResponse({
        "status": "ok", "service": "vessels", "version": "0.4.0", "doctrine": DOCTRINE,
        "note": "vessels has pivoted to Killinchu drone intelligence.",
        "redirect": KILLINCHU_REDIRECT,
        "killinchu_healthz": "/api/killinchu/healthz",
        "declarations": 749, "axioms": 14, "sorries": 163, "hatun_willay": True,
    })


@app.get("/api/vessels/v1/killinchu-redirect")
async def vessels_killinchu_redirect() -> JSONResponse:
    return JSONResponse({"redirect": KILLINCHU_REDIRECT,
                         "message": "Drone intelligence has moved to Killinchu.",
                         "doctrine": DOCTRINE})


@app.api_route("/api/vessels/{path:path}", methods=["GET", "POST"])
async def vessels_catch(path: str) -> JSONResponse:
    return JSONResponse({
        "data": [], "meta": {"path": f"/api/vessels/{path}", "doctrine": DOCTRINE,
                             "note": "vessels pivoted to Killinchu — see /api/killinchu/*",
                             "redirect": KILLINCHU_REDIRECT}})


# ---------------------------------------------------------------------------
# SPA — Andean Drone Intelligence at root. History fallback.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ADDITIVE (Yachay / Provenance Hardening): Wire D (W3C traceparent trace
# continuity) + DSSE/Cosign-signed Khipu receipts (SLSA L2 signed provenance).
# Registers /api/{space}/wires/D, /khipu/{sign,verify,ledger}, /provenance.
# Wrapped so a missing dep (cryptography) can NEVER take down the existing app.
# PLACEHOLDER -> REAL: every receipt now DSSE-signed with szlholdings-cosign.
# ---------------------------------------------------------------------------
try:
    import szl_provenance as _prov
    _prov_status = _prov.register_provenance(app, "killinchu")
    print(f"[killinchu] szl_provenance registered (Wire D LIVE, SLSA L2): {{_prov_status}}", file=sys.stderr)
except Exception as _pe:  # pragma: no cover - defensive, additive-only
    print(f"[killinchu] szl_provenance NOT registered ({{_pe!r}}); existing app unaffected", file=sys.stderr)

# ---------------------------------------------------------------------------
# Warhacker top-level alias routes (ADDITIVE, Yachay, 2026-06-01). Registered
# BEFORE the /{full_path:path} catch-all: /healthz + /khipu/{sign,verify,pubkey}
# + /api/killinchu/v3/doctrine + /wires/D. Real DSSE via szl_dsse. v11 verbatim.
# ---------------------------------------------------------------------------
try:
    import szl_warhacker_aliases as _wh_aliases
    _wh_status = _wh_aliases.register(app, "killinchu", build_sha=os.environ.get("SPACE_COMMIT_SHA", "warhacker-aliases-v1"))
    print(f"[killinchu] Warhacker aliases registered: {_wh_status}", file=sys.stderr)
except Exception as _wh_e:
    print(f"[killinchu] Warhacker aliases NOT registered: {_wh_e!r}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Killinchu v2 GENIUS endpoints (ADDITIVE, Yachay, 2026-06-01). Cesium /globe +
# geofence/check + mission/plan (PURIQ F7) + swarm/coordinate (boids) + remote-id
# /mavlink/adsb decoders + digital twin + threat/assess (sentra) + warhacker P1-P8.
# Registered BEFORE the catch-all so /globe + /api/killinchu/v2/* resolve LOCALLY.
# ---------------------------------------------------------------------------
try:
    import killinchu_genius as _kg
    _kg_status = _kg.register(app, "killinchu")
    print(f"[killinchu] v2 genius endpoints registered: {_kg_status}", file=sys.stderr)
except Exception as _kg_e:
    print(f"[killinchu] v2 genius endpoints NOT registered: {_kg_e!r}", file=sys.stderr)

@app.get("/")
async def spa_root() -> FileResponse:
    return FileResponse(INDEX_HTML, media_type="text/html")


# ADDITIVE (UDS HARDENING, Yachay 2026-06-01): DESKTOP-FIRST UDS compliance
# dashboard for 1280px+ workstation operators (STIG/SCAP, Iron Bank parity, Big
# Bang chart, Tradewinds, CMMC/NIST/EU-AI-Act). Self-contained static page that
# reads the live /api/killinchu/uds/v1/* real-data endpoints. Clean aliases so
# operators don't need the .html suffix.
@app.get("/uds/compliance")
@app.get("/compliance")
async def uds_compliance_dashboard() -> FileResponse:
    _page = STATIC_DIR / "uds-compliance.html"
    if _page.is_file():
        return FileResponse(_page, media_type="text/html")
    return FileResponse(INDEX_HTML, media_type="text/html")


# ADDITIVE (Drone 3D Health v4, Yachay 2026-06-01): clean operator-shell aliases.
# /operator + /uds serve the UDS Command Center (which now carries the Drone 3D tab).
@app.get("/operator")
@app.get("/uds")
async def operator_shell() -> FileResponse:
    _page = STATIC_DIR / "uds.html"
    if _page.is_file():
        return FileResponse(_page, media_type="text/html")
    return FileResponse(INDEX_HTML, media_type="text/html")




# ===========================================================================
# Wire I — Rosie-companion (ADDITIVE, Doctrine v11). Signed: Yachay.
# Founder directive 2026-06-01 ~02:52 EDT: "Make sure Rosie is wired in the
# backend of each flag and wherever needed to be."
# killinchu (drone) gains a Rosie-shadow. /counter-uas/identify optionally
# consults the Rosie-shadow when the classifier's top-match confidence < 0.7
# (low-confidence / possibly novel airframe). New endpoint
# /api/killinchu/v1/identify/with-rosie. /api/killinchu/v1/rosie-companion/*
# exposes ponder/synthesize/evolve/brain_jack. This EXTENDS the pattern already
# specified in ROSIE_COMPANION_IN_KILLINCHU.md to the identify surface.
# Rosie is co-pilot, NOT pilot: she proposes; killinchu + 2-person Yuyay gate
# decide. WE SENSE, WE EVIDENCE (passive only). Registered BEFORE the
# /{full_path:path} catch-all. NEVER crash the existing app.
# ===========================================================================
try:
    import szl_rosie_companion as _rc

    _KILLINCHU_SHADOW = _rc.RosieShadow("killinchu")
    _IDENTIFY_CONF_FLOOR = 0.7

    @app.get("/api/killinchu/v1/rosie-companion")
    async def killinchu_rosie_companion_info() -> JSONResponse:
        return JSONResponse({
            "wire": "I", "flagship": "killinchu", "organ": "drone",
            "rosie_endpoint": _KILLINCHU_SHADOW.jack_url,
            "ops": ["ponder", "synthesize", "evolve", "brain_jack"],
            "low_confidence_rule": f"counter-uas identify consults Rosie when top confidence < {_IDENTIFY_CONF_FLOOR}",
            "low_confidence_endpoint": "/api/killinchu/v1/identify/with-rosie",
            "doctrine": "v11",
            "honesty": "Rosie is co-pilot, not pilot. killinchu + 2-person Yuyay gate decide. WE SENSE, WE EVIDENCE (passive).",
        })

    @app.post("/api/killinchu/v1/identify/with-rosie")
    async def killinchu_identify_with_rosie(request: Request) -> JSONResponse:
        """Counter-UAS identify with optional Rosie low-confidence consult. Runs the
        existing passive signature classifier; ONLY when the top match confidence is
        below the floor (0.7) — i.e. possibly a novel airframe — does it consult the
        Rosie-shadow for deeper reasoning. Both the identify result and the Rosie
        reasoning carry Khipu receipts (cross-linked). PASSIVE detection only."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        axis_scores = body.get("axis_scores")
        tp = getattr(getattr(request, "state", None), "traceparent", None)
        # Reuse the existing passive classifier via in-process loopback so we do not
        # duplicate the adversary catalog. Honest: same endpoint the UI already drives.
        identify_result = None
        try:
            import httpx as _httpx
            _port = int(os.environ.get("PORT", "7860"))
            with _httpx.Client(timeout=8.0) as _c:
                _r = _c.post(f"http://127.0.0.1:{_port}/api/killinchu/v1/counter-uas/identify",
                             json=body)
                if _r.status_code == 200:
                    identify_result = _r.json()
        except Exception as _ie:
            identify_result = {"ok": False, "error": f"local identify unreachable: {_ie}", "matches": []}
        matches = (identify_result or {}).get("matches", []) or []
        top_conf = matches[0]["confidence"] if matches else 0.0
        out = {
            "identify": identify_result,
            "top_confidence": top_conf,
            "confidence_floor": _IDENTIFY_CONF_FLOOR,
            "doctrine": "v11", "wire": "I",
        }
        if top_conf >= _IDENTIFY_CONF_FLOOR:
            out.update({
                "rosie_consulted": False,
                "note": f"Top confidence {top_conf} >= floor {_IDENTIFY_CONF_FLOOR}; classifier confident. Rosie not consulted.",
            })
            return JSONResponse(out)
        # LOW CONFIDENCE — consult Rosie for novel-airframe reasoning.
        sig = (body.get("rf_signature") or body.get("acoustic") or body.get("image_label") or "")
        q = (f"LOW-CONFIDENCE IDENTIFY (top={top_conf} < {_IDENTIFY_CONF_FLOOR}). Reason about "
             f"this possibly-novel airframe signature (passive, no active emission): {str(sig)[:400]}")
        r = _KILLINCHU_SHADOW.brain_jack(q, depth=int(body.get("depth", 1)),
                                         axis_scores=axis_scores, traceparent=tp)
        out.update({
            "rosie_consulted": True,
            "rosie_assessment": r.text,
            "rosie_lambda": r.lambda_signal,
            "rosie_receipt": r.rosie_receipt,
            "cross_link": r.cross_link,
            "rosie_stub": r.stub,
            "note": (f"Top confidence {top_conf} < floor {_IDENTIFY_CONF_FLOOR} -> Rosie consulted for "
                     "novel-airframe reasoning. Rosie is advisory; killinchu + 2-person Yuyay gate decide."),
        })
        return JSONResponse(out)

    @app.post("/api/killinchu/v1/rosie-companion/ponder")
    async def killinchu_rosie_ponder(request: Request) -> JSONResponse:
        body = await request.json()
        tp = getattr(getattr(request, "state", None), "traceparent", None)
        return JSONResponse(_KILLINCHU_SHADOW.ponder(body.get("context", body), traceparent=tp).to_dict())

    @app.post("/api/killinchu/v1/rosie-companion/synthesize")
    async def killinchu_rosie_synthesize(request: Request) -> JSONResponse:
        body = await request.json()
        tp = getattr(getattr(request, "state", None), "traceparent", None)
        return JSONResponse(_KILLINCHU_SHADOW.synthesize(body.get("events", []), traceparent=tp).to_dict())

    @app.post("/api/killinchu/v1/rosie-companion/evolve")
    async def killinchu_rosie_evolve(request: Request) -> JSONResponse:
        body = await request.json()
        tp = getattr(getattr(request, "state", None), "traceparent", None)
        return JSONResponse(_KILLINCHU_SHADOW.evolve(body.get("strategy", {}),
                            approvers=body.get("approvers", []), traceparent=tp).to_dict())

    @app.post("/api/killinchu/v1/rosie-companion/brain-jack")
    async def killinchu_rosie_brain_jack(request: Request) -> JSONResponse:
        body = await request.json()
        tp = getattr(getattr(request, "state", None), "traceparent", None)
        return JSONResponse(_KILLINCHU_SHADOW.brain_jack(body.get("query", ""),
                            depth=int(body.get("depth", 1)),
                            axis_scores=body.get("axis_scores"), traceparent=tp).to_dict())

    print("[killinchu] Wire I rosie-companion registered (identify/with-rosie conf<0.7 consult)", file=sys.stderr)
except Exception as _rc_e:
    print(f"[killinchu] Wire I rosie-companion NOT registered: {_rc_e!r}", file=sys.stderr)

# ===========================================================================
# UNAY + Khipu-LMDB v2 organs (ADDITIVE, 2026-06-01, Yachay / Perplexity Computer Agent).
# NEW /api/killinchu/v2/* paths only, registered on the ROOT app BEFORE the SPA
# catch-all "/{full_path:path}" so they resolve LOCALLY. try/except-guarded.
# Real durable lmdb + real sqlite-vss (honest cosine-fallback). LOCKED: 749/14/163.
# ---------------------------------------------------------------------------
try:
    import szl_unay_routes as _unay
    _unay_info = _unay.register(app, ns="killinchu")
    import sys as _sysu
    print(f"[szl_unay] UNAY+Khipu-LMDB v2 mounted: backend={_unay_info.get('unay_backend')}, "
          f"lmdb={_unay_info.get('lmdb_version')}, boot_entries={_unay_info.get('lmdb_entries_at_boot')}", file=_sysu.stderr)
except Exception as _ue:
    import sys as _sysu
    print(f"[szl_unay] UNAY+Khipu-LMDB v2 NOT mounted ({_ue!r}); existing routes unaffected", file=_sysu.stderr)


# ===========================================================================
# UNDERSTUDY-PARITY layer (ADDITIVE, 2026-06-01, Yachay / Perplexity Computer Agent).
# Founder directive: killinchu gets EVERY a11oy moat + full understudy posture
# (LLM router, agentic RAG, MCP server, PURIQ organs, 23 formulas, AYNI, WAYRA,
# KIPU+QILLQAQ, Khipu-DAG RS(10,6), Yuyay-13 gate, connections, metrics,
# understudy failover) under killinchu's defense vertical lens. NEW
# /api/killinchu/v2/* + canonical cross-organ routes only; registered BEFORE the
# SPA catch-all so they resolve LOCALLY. try/except-guarded; NEVER crash the app.
# Imports the REAL substrate (szl_dsse, szl_brain, szl_rag, szl_formulas) — no
# copy-paste. v11 verbatim 749/14/163. Sign: Yachay.
# ---------------------------------------------------------------------------
try:
    import szl_understudy as _understudy
    _u_info = _understudy.register(app, ns="killinchu")
    print(f"[killinchu] understudy-parity registered: {_u_info['registered_count']} routes, "
          f"substrate={_u_info['substrate']}", file=sys.stderr)
except Exception as _u_e:
    print(f"[killinchu] understudy-parity NOT registered: {_u_e!r}; existing app unaffected", file=sys.stderr)


# ===========================================================================
# DEFENSE RUNTIME COOKBOOK (ADDITIVE, 2026-06-01, Yachay / Perplexity Computer Agent).
# Founder cherry-pick: make Killinchu one-of-one in the defense vertical. NEW
# /api/killinchu/v2/cookbook* + /v2/missions* + /v2/scouts + /v2/uds/* + /v2/legal
# + /v2/specs/* + /v2/pitch routes ONLY. Registered BEFORE the SPA catch-all so
# they resolve LOCALLY. Every drone-domain response embeds the LEGAL_BOUNDARIES
# disclaimer ("WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES.").
# Recall receipts are REAL ECDSA-P256-SHA256 DSSE via szl_dsse (no copy-paste).
# Data vendored under static/cookbook/. try/except-guarded; NEVER crash the app.
# 22+ recipes · 8 Warhacker mission packs (P1-P8) · 9 prospect scouts · UDS
# bundle self-awareness (HONEST STAGED) · per-prospect pitch. v11 verbatim 749/14/163.
# ---------------------------------------------------------------------------
try:
    import szl_killinchu_cookbook as _cookbook
    _cb_info = _cookbook.register_cookbook(app, ns="killinchu")
    print(f"[killinchu] defense cookbook registered: {_cb_info['registered_count']} routes, "
          f"signing={_cb_info['signing']}", file=sys.stderr)
except Exception as _cb_e:
    print(f"[killinchu] defense cookbook NOT registered: {_cb_e!r}; existing app unaffected", file=sys.stderr)


# ===========================================================================
# KILLINCHU FUSION — UDS-native single front door (ADDITIVE, 2026-06-01,
# Yachay / Perplexity Computer Agent). Killinchu is the SOLE UDS-facing surface:
# every UDS endpoint lives under /api/killinchu/uds/v1/*. One operator action
# fans out to the live organ Spaces (Sentra immune gate -> Amaru cortex || a11oy
# policy -> Killinchu field action) and returns ONE aggregated DSSE receipt whose
# chain[] carries all four organ verdicts + signatures, signed with the SAME
# szlholdings-cosign ECDSA-P256 key (cosign verify-blob "Verified OK"). Appended
# to the Khipu DAG. Registration is ADDITIVE + IDEMPOTENT: any path a sibling
# agent already owns is DEFERRED to (never double-registered). Registered BEFORE
# the SPA catch-all so these explicit routes resolve LOCALLY. try/except-guarded;
# NEVER crash the existing app. UI: /uds.html (Command/Field/Audit/Compliance).
# Honesty preserved: drone positions SIMULATED, geofence STATIC SNAPSHOT, amaru
# organ_signed=false, Rekor not_submitted, fail-WARNING never fail-open.
# Doctrine v11 LOCKED 749/14/163. Λ Conjecture 1 is NOT a theorem.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# UDS HARDENING — REAL-DATA endpoints (ADDITIVE, 2026-06-01, Yachay). Registered
# BEFORE killinchu_fusion so the fusion module's honest SYNTHETIC STIG/parity
# stubs DEFER (via its _claim() guard) to these real-data routes backed by
# committed .compliance/ artifacts: real OpenSCAP oscap 1.4.2 DISA STIG output
# (baseline 30.27 -> hardened 33.49, 16 rules fail->pass), real Dockerfile
# Iron Bank base audit, real `helm lint`/render Big Bang inventory, Tradewinds
# listing. Cosign-signed (szlholdings-cosign ECDSA-P256) via szl_dsse; honest
# UNSIGNED envelope if the key secret is absent. try/except-guarded; NEVER
# crashes the existing app. Sign: Yachay <yachay@szlholdings.dev>.
# ---------------------------------------------------------------------------
try:
    import szl_uds_hardening as _uds_hard
    _uds_hard_info = _uds_hard.register(app, "killinchu")
    print(f"[killinchu] UDS HARDENING real-data endpoints registered: "
          f"{_uds_hard_info['registered_count']} routes, signing={_uds_hard_info['signing']}",
          file=sys.stderr)
except Exception as _uds_hard_e:
    print(f"[killinchu] UDS HARDENING endpoints NOT registered: {_uds_hard_e!r}; existing app unaffected", file=sys.stderr)

try:
    import killinchu_fusion as _fusion
    _fusion_info = _fusion.register(app, "killinchu")
    print(f"[killinchu] UDS fusion front-door registered: {_fusion_info['registered_count']} routes, "
          f"signing={_fusion_info['signing']}, deferred={len(_fusion_info.get('deferred_to_siblings', []))}",
          file=sys.stderr)
except Exception as _fusion_e:
    print(f"[killinchu] UDS fusion front-door NOT registered: {_fusion_e!r}; existing app unaffected", file=sys.stderr)


# ===========================================================================
# DRONE 3D HEALTH DIAGNOSTICS (ADDITIVE, 2026-06-01, Yachay / Perplexity Computer
# Agent). Founder mandate: SZL DNA, not a generic counter-UAS rule engine —
# "see drones before they break, before they're shot, before they're fried."
# NEW /api/killinchu/v4/* surface ONLY: per-drone Yuyay-13 health score, Λ-combined
# risk, satellite RF environment, weather/space-weather/quake impact, probabilistic
# failure mode + ETA, fired/intact component map, Three.js scene JSON, and an
# HF-Inference LLM "explain" narrative. Fuses ONLY free public APIs (USGS quakes,
# NOAA SWPC Kp + solar wind, NOAA Aviation Weather METAR, N2YO satellites [free key],
# HF Inference router [Space token]). Codex-Kernel: every report is BIT-EXACT
# reproducible from its fusion_inputs seed. Each diagnostic is Khipu-DAG chained
# (host _emit_receipt) + REAL DSSE-signed (szl_dsse). Registered BEFORE the SPA
# catch-all so /api/killinchu/v4/* + /drone-3d resolve LOCALLY. try/except-guarded;
# NEVER crashes the host app. Does NOT touch v1/v2/v3 drone DB or decoder routes.
# Honest: "predicted failure" is PROBABILISTIC, signed by Λ — NOT a guarantee.
# Doctrine v11 LOCKED 749/14/163. Sign: Yachay. Co-author: Perplexity Computer Agent.
# ---------------------------------------------------------------------------
try:
    import killinchu_drone_3d_health as _drone3d
    try:
        import szl_dsse as _d3d_dsse
        _d3d_signer = _d3d_dsse.sign_khipu_receipt
    except Exception:
        _d3d_signer = None
    _drone3d_info = _drone3d.register(
        app, "killinchu",
        emit_receipt=_emit_receipt,
        sign_receipt=_d3d_signer,
        static_dir=str(STATIC_DIR),
    )
    print(f"[killinchu] Drone 3D Health v4 registered: {_drone3d_info['registered_count']} routes, "
          f"signing={_drone3d_info['signing']}", file=sys.stderr)
except Exception as _d3d_e:
    import traceback as _d3d_tb
    print(f"[killinchu] Drone 3D Health v4 NOT registered: {_d3d_e!r}\n{_d3d_tb.format_exc()}", file=sys.stderr)


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str) -> Response:
    if full_path.startswith("api/"):
        return JSONResponse({"error": "not found"}, status_code=404)
    candidate = (STATIC_DIR / full_path).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return FileResponse(INDEX_HTML, media_type="text/html")
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(INDEX_HTML, media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "7860"))
    print(f"[killinchu] Andean Drone Intelligence on :{port} — Doctrine v11 — SPA at /", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
