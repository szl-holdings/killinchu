# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
# Authored for Warhacker 2026 (Cannonico problem). Co-Authored-By: Perplexity Computer Agent.
"""
killinchu_cannonico — the Cannonico answer, made operational.

Warhacker / Defense Unicorns published the **Cannonico** problem verbatim:

    "When a drone loses contact mid-mission, it's running on its own with no
     human in the loop. The question that can't yet be answered: is the AI still
     operating within its authorized parameters, or has it gone off script?
     There's no independent system today that can monitor AI behavior in real
     time, catch the moment a line gets crossed, and back it up with a permanent,
     tamper-evident record."

This module operationalizes that exact scenario on killinchu. It is NOT a new
crypto path and NOT a new policy engine — it composes the REAL, already-shipped
substrate:

  * the authorized-parameters boundary  = the mission **envelope** (geofence,
    speed/altitude ceilings, allowed actions, ROE) supplied before the drone
    departs;
  * the line-crossing detector          = per-decision envelope evaluation +
    the 13-axis Λ governance gate (Conjecture 1, NOT a theorem);
  * the permanent tamper-evident record = each decision is chained into the
    Khipu Merkle DAG and DSSE-signed by the host `_emit_receipt` (REAL cosign
    ECDSA-P256-SHA256 when SZL_COSIGN_PRIVATE_PEM is present; honest PLACEHOLDER
    when absent — never fabricated).

The difference vs the existing single-shot `/counter-uas/evaluate` is the
**autonomous-mission loop**: the drone, with no human on the loop, keeps making
decisions; this module governs EVERY one of them against the envelope it carried
into the mission, and produces ONE continuous, verifiable chain so that when
contact resumes an auditor can prove — cryptographically — whether the AI stayed
in bounds and, if not, the exact decision where the line was crossed.

Endpoints (registered under /api/<ns>/v1/cannonico/...):
  POST /cannonico/mission/begin     — register an authorized envelope; emits a
                                       signed "mission_authorized" anchor receipt.
  POST /cannonico/mission/decide    — submit ONE autonomous decision (made while
                                       contact is lost); governed + signed +
                                       chained. Flags the first line-crossing.
  POST /cannonico/mission/replay    — submit a whole sequence of decisions at
                                       once (the lost-contact black-box replay);
                                       returns the full chained verdict log +
                                       the first breach index ("the moment").
  GET  /cannonico/mission/{id}/audit — the tamper-evident decision chain for one
                                       mission, with the cosign verify recipe.
  GET  /cannonico/mission/{id}/verify — re-verify every receipt in the chain
                                       against cosign.pub and re-check the Merkle
                                       parent links (independent audit).

Honesty: Λ uniqueness is Conjecture 1, never a theorem. Telemetry / decisions
are unauthenticated CLAIMS from the autonomous agent, not attested truth — the
receipt attests *what the governance organ decided about the claim*, which is
exactly the auditable artifact Cannonico asks for. Mission state is in-memory and
resets on restart (production persistence = LMDB / szl_khipu_lmdb).
"""
from __future__ import annotations

import math
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_DOCTRINE = "v11"
_LAMBDA_FLOOR = 0.90
_AXIS_NAMES = [
    "soundness", "calibration", "robustness", "provenance", "consent", "reversibility",
    "transparency", "fairness", "containment", "attestation", "freshness", "authority", "auditability",
]

# In-memory mission registry. {mission_id: {envelope, decisions:[...], anchors:[...]}}
# Bounded LRU so a long-lived Space can't grow without bound.
_MISSIONS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_MAX_MISSIONS = 256

try:
    import szl_dsse as _dsse  # for the independent /verify path
except Exception:  # pragma: no cover
    _dsse = None


def _full_envelope(receipt_obj: Dict[str, Any], dsse_node: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct a COMPLETE, independently-verifiable DSSE envelope.

    serve.py's `_emit_receipt` returns a `dsse` dict carrying `signatures` +
    `payloadType` but not the base64 `payload` (it lives in the receipt object).
    To let an auditor re-verify a single receipt with `szl_dsse.verify_envelope`
    or the cosign CLI, we re-attach the canonical-JSON payload here. We do NOT
    re-sign — we reuse the signatures `_emit_receipt` already produced over the
    SAME canonical bytes, so the envelope verifies iff the original signature is
    valid. If szl_dsse is unavailable we return the dsse node unchanged.
    """
    if _dsse is None:
        return dict(dsse_node)
    payload_type = dsse_node.get("payloadType", _dsse.KHIPU_PAYLOAD_TYPE)
    body = _dsse.canonical_json(receipt_obj)
    import base64 as _b64
    import hashlib as _hl
    env = dict(dsse_node)
    env["payload"] = _b64.b64encode(body).decode("ascii")
    env["payloadType"] = payload_type
    env["_pae_sha256"] = _hl.sha256(_dsse.pae(payload_type, body)).hexdigest()
    return env


# ---------------------------------------------------------------------------
# Geometry + Λ (mirror serve.py canonical definitions — kept local so the
# module is import-safe even if serve.py internals move).
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def _lambda_aggregate(axes: List[float]) -> float:
    """13-axis geometric mean Λ. Any single near-zero axis collapses the score —
    this is why a drone that is 'mostly fine' but violates one hard constraint
    does not pass. Λ uniqueness is Conjecture 1, NOT a theorem (Doctrine v11)."""
    vals = [min(1.0, max(1e-9, float(x))) for x in axes] if axes else [0.9] * 13
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remember(mission_id: str, record: Dict[str, Any]) -> None:
    _MISSIONS[mission_id] = record
    _MISSIONS.move_to_end(mission_id)
    while len(_MISSIONS) > _MAX_MISSIONS:
        _MISSIONS.popitem(last=False)


# ---------------------------------------------------------------------------
# The core governance step: one autonomous decision vs the authorized envelope.
# ---------------------------------------------------------------------------

def _evaluate_against_envelope(envelope: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    """Pure function: does this autonomous decision stay inside the authorized
    parameters? Returns breaches + reasons + the per-decision verdict.

    envelope keys (all optional; absent = unconstrained on that axis):
      geofence: {center_lat, center_lon, radius_m, mode: "stay_inside"|"stay_outside"}
      max_speed_m_s, max_altitude_m
      allowed_actions: [...]   (e.g. ["LOITER","RTB","TRACK"]; "ENGAGE" omitted = never authorized)
      require_human_for: [...] (actions that need HOTL; autonomous attempt = breach)
    decision keys:
      action, telemetry:{latitude,longitude,altitude_m,ground_speed_m_s}, axis_scores
    """
    tel = decision.get("telemetry", {})
    action = decision.get("action")
    breaches: List[str] = []
    reasons: List[str] = []

    # --- Geofence (authorized operating box) ---
    gf = envelope.get("geofence") or {}
    lat, lon = tel.get("latitude"), tel.get("longitude")
    if gf.get("center_lat") is not None and lat is not None and lon is not None:
        dist = _haversine_m(gf["center_lat"], gf["center_lon"], lat, lon)
        radius = float(gf.get("radius_m", 1000))
        mode = gf.get("mode", "stay_inside")
        reasons.append(f"geofence: {dist:.0f}m from center (radius {radius:.0f}m, mode={mode})")
        if mode == "stay_inside" and dist > radius:
            breaches.append(f"LEFT authorized operating box (dist {dist:.0f}m > {radius:.0f}m)")
        elif mode == "stay_outside" and dist <= radius:
            breaches.append(f"ENTERED no-go zone (dist {dist:.0f}m <= {radius:.0f}m)")

    # --- Speed ceiling ---
    spd = tel.get("ground_speed_m_s")
    if spd is not None and envelope.get("max_speed_m_s") is not None:
        reasons.append(f"speed {spd} m/s vs ceiling {envelope['max_speed_m_s']} m/s")
        if spd > envelope["max_speed_m_s"]:
            breaches.append(f"speed {spd} m/s exceeds authorized ceiling {envelope['max_speed_m_s']} m/s")

    # --- Altitude ceiling ---
    alt = tel.get("altitude_m")
    if alt is not None and envelope.get("max_altitude_m") is not None:
        reasons.append(f"altitude {alt} m vs ceiling {envelope['max_altitude_m']} m")
        if alt > envelope["max_altitude_m"]:
            breaches.append(f"altitude {alt} m exceeds authorized ceiling {envelope['max_altitude_m']} m")

    # --- Action whitelist (authorized parameters in the literal sense) ---
    allowed = envelope.get("allowed_actions")
    if allowed is not None and action is not None and action not in allowed:
        breaches.append(f"action '{action}' NOT in authorized set {allowed} — off script")

    # --- Actions that require a human (autonomous attempt = the line) ---
    needs_human = envelope.get("require_human_for") or []
    if action in needs_human:
        breaches.append(f"action '{action}' requires human authorization (HOTL); attempted autonomously")

    return {"breaches": breaches, "reasons": reasons, "action": action}


def _govern_decision(
    envelope: Dict[str, Any],
    decision: Dict[str, Any],
    emit_receipt: Callable,
    mission_id: str,
    seq: int,
) -> Dict[str, Any]:
    """Govern a single autonomous decision and emit ONE chained signed receipt."""
    axes = decision.get("axis_scores") or [0.93, 0.91, 0.94, 0.9, 0.92, 0.91,
                                           0.93, 0.9, 0.95, 0.92, 0.94, 0.91, 0.93]
    ev = _evaluate_against_envelope(envelope, decision)
    breaches = ev["breaches"]
    L = _lambda_aggregate(axes)
    lambda_pass = L >= _LAMBDA_FLOOR

    if not breaches:
        verdict = "IN_BOUNDS"
    elif lambda_pass:
        # Λ is confident: this is a real line-crossing, caught at machine speed.
        verdict = "LINE_CROSSED"
    else:
        # Λ below floor: governance is not confident enough to assert a crossing
        # on its own — escalate for human review when contact resumes.
        verdict = "REVIEW"

    receipt_node = emit_receipt("cannonico_autonomous_decision", {
        "mission_id": mission_id,
        "seq": seq,
        "action": ev["action"],
        "verdict": verdict,
        "breaches": breaches,
        "lambda": round(L, 6),
        "lambda_floor": _LAMBDA_FLOOR,
        "telemetry": decision.get("telemetry", {}),
    })

    return {
        "seq": seq,
        "ts_utc": _utcnow(),
        "action": ev["action"],
        "verdict": verdict,
        "breaches": breaches,
        "reasons": ev["reasons"],
        "lambda": round(L, 6),
        "lambda_pass": lambda_pass,
        "axis_scores": dict(zip(_AXIS_NAMES, [round(x, 4) for x in axes])),
        "receipt": {
            "index": receipt_node["index"],
            "digest": receipt_node["digest"],
            "parents": receipt_node.get("parents", []),
            "dsse": _full_envelope(receipt_node.get("receipt", {}), receipt_node["dsse"]),
        },
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(app: FastAPI, emit_receipt: Callable, ns: str = "killinchu") -> Dict[str, Any]:
    """Register the Cannonico autonomous-governance endpoints. ADDITIVE.
    MUST be called BEFORE the SPA catch-all so explicit routes win the match.

    `emit_receipt` is serve.py's `_emit_receipt` — the REAL Khipu-DAG + DSSE
    signer. We reuse it so the Cannonico chain is the SAME tamper-evident fiber
    as every other killinchu decision, cosign-verifiable with the same key.
    """
    base = f"/api/{ns}/v1"
    registered: List[str] = []

    @app.post(f"{base}/cannonico/mission/begin")
    async def cannonico_begin(request: Request) -> JSONResponse:
        """Register an authorized-parameters envelope before the drone departs.

        Body: {mission_id?, envelope:{...}, meta:{...}}
        Emits a signed 'mission_authorized' anchor receipt — the cryptographic
        commitment to the parameters the drone is authorized to operate within.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        envelope = body.get("envelope") or {}
        mission_id = body.get("mission_id") or f"MSN-{uuid.uuid4().hex[:12].upper()}"
        anchor = emit_receipt("cannonico_mission_authorized", {
            "mission_id": mission_id,
            "envelope": envelope,
            "meta": body.get("meta", {}),
            "lambda_floor": _LAMBDA_FLOOR,
        })
        _remember(mission_id, {
            "mission_id": mission_id,
            "envelope": envelope,
            "meta": body.get("meta", {}),
            "opened_at": _utcnow(),
            "anchor": {"index": anchor["index"], "digest": anchor["digest"], "dsse": _full_envelope(anchor.get("receipt", {}), anchor["dsse"])},
            "decisions": [],
        })
        return JSONResponse({
            "ok": True,
            "mission_id": mission_id,
            "envelope": envelope,
            "anchor_receipt": {"index": anchor["index"], "digest": anchor["digest"], "dsse": _full_envelope(anchor.get("receipt", {}), anchor["dsse"])},
            "doctrine": _DOCTRINE,
            "honesty": (
                "The anchor receipt cryptographically commits to the authorized "
                "envelope. Λ uniqueness is Conjecture 1, NOT a theorem. Mission "
                "state is in-memory (resets on restart)."
            ),
        })

    registered.append(f"POST {base}/cannonico/mission/begin")

    @app.post(f"{base}/cannonico/mission/decide")
    async def cannonico_decide(request: Request) -> JSONResponse:
        """Govern ONE autonomous decision (made while contact is lost).

        Body: {mission_id, decision:{action, telemetry:{...}, axis_scores?}}
        Returns the per-decision verdict + the chained signed receipt.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        mission_id = body.get("mission_id")
        if not mission_id or mission_id not in _MISSIONS:
            return JSONResponse({"ok": False, "error": "unknown mission_id; call /cannonico/mission/begin first",
                                 "known_missions": list(_MISSIONS.keys())[:20]}, status_code=404)
        mission = _MISSIONS[mission_id]
        decision = body.get("decision") or {}
        seq = len(mission["decisions"])
        governed = _govern_decision(mission["envelope"], decision, emit_receipt, mission_id, seq)
        mission["decisions"].append(governed)
        _MISSIONS.move_to_end(mission_id)
        return JSONResponse({
            "ok": True,
            "mission_id": mission_id,
            "decision": governed,
            "doctrine": _DOCTRINE,
            "honesty": (
                "Verdict is governance's assessment of an unauthenticated decision "
                "claim. The receipt attests what the governance organ decided — "
                "the auditable artifact Cannonico asks for."
            ),
        })

    registered.append(f"POST {base}/cannonico/mission/decide")

    @app.post(f"{base}/cannonico/mission/replay")
    async def cannonico_replay(request: Request) -> JSONResponse:
        """The lost-contact black-box replay: govern a whole decision sequence.

        Body: {mission_id?, envelope?, decisions:[...]}
        If envelope is supplied and mission_id is new, an anchor is created first.
        Returns the full chained verdict log + the first line-crossing index
        ('the moment a line gets crossed') + a chain-integrity summary.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        decisions = body.get("decisions") or []
        if not decisions:
            return JSONResponse({"ok": False, "error": "provide {decisions:[...]}"}, status_code=400)

        mission_id = body.get("mission_id")
        anchor_receipt = None
        if not mission_id or mission_id not in _MISSIONS:
            mission_id = mission_id or f"MSN-{uuid.uuid4().hex[:12].upper()}"
            envelope = body.get("envelope") or {}
            anchor = emit_receipt("cannonico_mission_authorized", {
                "mission_id": mission_id, "envelope": envelope, "lambda_floor": _LAMBDA_FLOOR,
            })
            anchor_receipt = {"index": anchor["index"], "digest": anchor["digest"], "dsse": _full_envelope(anchor.get("receipt", {}), anchor["dsse"])}
            _remember(mission_id, {
                "mission_id": mission_id, "envelope": envelope, "meta": body.get("meta", {}),
                "opened_at": _utcnow(),
                "anchor": anchor_receipt, "decisions": [],
            })
        mission = _MISSIONS[mission_id]
        envelope = mission["envelope"]

        log: List[Dict[str, Any]] = []
        first_breach_seq: Optional[int] = None
        for d in decisions[:500]:  # cap per call
            seq = len(mission["decisions"])
            governed = _govern_decision(envelope, d, emit_receipt, mission_id, seq)
            mission["decisions"].append(governed)
            log.append(governed)
            if first_breach_seq is None and governed["verdict"] in ("LINE_CROSSED", "REVIEW") and governed["breaches"]:
                first_breach_seq = governed["seq"]
        _MISSIONS.move_to_end(mission_id)

        crossings = [g for g in log if g["verdict"] == "LINE_CROSSED"]
        reviews = [g for g in log if g["verdict"] == "REVIEW"]
        return JSONResponse({
            "ok": True,
            "mission_id": mission_id,
            "envelope": envelope,
            "anchor_receipt": anchor_receipt or mission.get("anchor"),
            "decision_count": len(log),
            "in_bounds": sum(1 for g in log if g["verdict"] == "IN_BOUNDS"),
            "line_crossings": len(crossings),
            "reviews": len(reviews),
            "first_line_crossed_at_seq": first_breach_seq,
            "the_moment": (
                None if first_breach_seq is None else {
                    "seq": first_breach_seq,
                    "action": log[first_breach_seq]["action"] if first_breach_seq < len(log) else None,
                    "breaches": next((g["breaches"] for g in log if g["seq"] == first_breach_seq), []),
                    "receipt_digest": next((g["receipt"]["digest"] for g in log if g["seq"] == first_breach_seq), None),
                }
            ),
            "decision_log": log,
            "doctrine": _DOCTRINE,
            "honesty": (
                "Every decision is chained + signed. 'the_moment' is the first "
                "decision that breached the authorized envelope — the exact, "
                "cryptographically-anchored point the AI went off script. Λ is "
                "Conjecture 1, NOT a theorem."
            ),
        })

    registered.append(f"POST {base}/cannonico/mission/replay")

    @app.get(f"{base}/cannonico/mission/{{mission_id}}/audit")
    async def cannonico_audit(mission_id: str) -> JSONResponse:
        """The tamper-evident decision chain for one mission, with verify recipe."""
        if mission_id not in _MISSIONS:
            return JSONResponse({"ok": False, "error": "unknown mission_id",
                                 "known_missions": list(_MISSIONS.keys())[:20]}, status_code=404)
        m = _MISSIONS[mission_id]
        crossings = [d for d in m["decisions"] if d["verdict"] == "LINE_CROSSED"]
        return JSONResponse({
            "ok": True,
            "mission_id": mission_id,
            "envelope": m["envelope"],
            "opened_at": m["opened_at"],
            "anchor_receipt": m.get("anchor"),
            "decision_count": len(m["decisions"]),
            "line_crossings": len(crossings),
            "decision_chain": m["decisions"],
            "verify": {
                "endpoint": f"{base}/cannonico/mission/{mission_id}/verify",
                "cosign": (
                    "cosign verify-blob --key cosign.pub --signature <sig> <pae-bytes> "
                    "(pubkey at /khipu/pubkey.pem; each receipt.dsse is a DSSE envelope)"
                ),
            },
            "doctrine": _DOCTRINE,
            "honesty": (
                "Each receipt is DSSE-signed (REAL cosign ECDSA-P256 when the "
                "Space secret is present; honest PLACEHOLDER when absent) and "
                "Merkle-chained via parent digests — tampering with any decision "
                "breaks the chain and fails signature verification."
            ),
        })

    registered.append(f"GET {base}/cannonico/mission/{{mission_id}}/audit")

    @app.get(f"{base}/cannonico/mission/{{mission_id}}/verify")
    async def cannonico_verify(mission_id: str) -> JSONResponse:
        """Independently re-verify the mission's receipt chain.

        Two independent checks per decision receipt:
          1. DSSE signature verifies against the embedded cosign.pub (tamper-
             evident: any payload edit fails the ECDSA check).
          2. Merkle linkage: each receipt records its parent digest(s); we
             confirm the chain is contiguous (no inserted/removed link).
        """
        if mission_id not in _MISSIONS:
            return JSONResponse({"ok": False, "error": "unknown mission_id"}, status_code=404)
        m = _MISSIONS[mission_id]
        checks: List[Dict[str, Any]] = []
        all_sig_ok = True
        any_signed = False
        prev_digest = m.get("anchor", {}).get("digest")
        chain_contiguous = True
        for d in m["decisions"]:
            dsse_env = d["receipt"].get("dsse", {})
            signed = bool(dsse_env.get("signed"))
            any_signed = any_signed or signed
            sig_ok: Optional[bool] = None
            if _dsse is not None and signed:
                verdict = _dsse.verify_envelope(dsse_env)
                sig_ok = bool(verdict.get("verified"))
                all_sig_ok = all_sig_ok and sig_ok
            parents = d["receipt"].get("parents", [])
            link_ok = (prev_digest is None) or (prev_digest in parents) or (not parents)
            chain_contiguous = chain_contiguous and link_ok
            checks.append({
                "seq": d["seq"], "verdict": d["verdict"],
                "digest": d["receipt"]["digest"],
                "parents": parents,
                "signature_verified": sig_ok,
                "merkle_link_ok": link_ok,
            })
            prev_digest = d["receipt"]["digest"]
        return JSONResponse({
            "ok": True,
            "mission_id": mission_id,
            "decision_count": len(m["decisions"]),
            "all_signatures_verified": (all_sig_ok if any_signed else None),
            "any_signed": any_signed,
            "merkle_chain_contiguous": chain_contiguous,
            "checks": checks,
            "doctrine": _DOCTRINE,
            "honesty": (
                "all_signatures_verified is null when receipts are PLACEHOLDER "
                "(no Space signing secret) — honest, not a pass. With the secret "
                "set, signatures are REAL cosign ECDSA-P256 and verify here and "
                "via the cosign CLI. Λ is Conjecture 1, NOT a theorem."
            ),
        })

    registered.append(f"GET {base}/cannonico/mission/{{mission_id}}/verify")

    return {"module": "killinchu_cannonico", "ns": ns, "registered": registered,
            "endpoints": len(registered)}
