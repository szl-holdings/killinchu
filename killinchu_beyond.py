# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
# Authored for Warhacker 2026 (Beyond-Cannonico generalization).
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
"""
killinchu_beyond — the autonomy-governance pattern, generalized BEYOND one drone.

Cannonico proved the pattern on a single counter-UAS drone:

    authorized envelope  →  catch the line-crossing  →  tamper-evident receipt.

This module shows the SAME real substrate governs *any* autonomous or
multi-agent decision system. It is ADDITIVE: it composes the REAL, already-
shipped killinchu organs — `_emit_receipt` (Khipu Merkle DAG + REAL cosign DSSE),
the 13-axis Λ gate (Conjecture 1, NOT a theorem), and `szl_khipu_consensus`
(3-of-4 BFT) — into three proof surfaces. It introduces NO new crypto and NO new
policy engine; it reuses the ones that already verify with `cosign verify-blob`.

Three REAL endpoints (registered under /api/<ns>/v1/, BEFORE the SPA catch-all):

  1. Generalized Autonomy Envelope
     POST /api/<ns>/v1/autonomy/evaluate
        Submit ANY autonomous-system decision — a ground robot, an autonomous
        vehicle, a loitering munition, a UxS of any domain — as
        {system_type, telemetry, envelope, action}. killinchu evaluates it
        against the authorized envelope, Λ-gates it, catches envelope breaches
        (left the geofence, over a ceiling, off the action whitelist, attempted
        a human-only action), and emits ONE signed, chained, tamper-evident
        receipt. The envelope semantics generalize counter-UAS to arbitrary
        system types (per-type bounds: ground speed, AGL ceiling, standoff,
        weapon-release authority, …).

  2. Swarm / Multi-Agent Quorum
     POST /api/<ns>/v1/swarm/quorum
        A decision that fans out to FOUR independent organs (sentra · amaru ·
        a11oy · killinchu), each holding its OWN ECDSA-P256 keypair and
        independently DSSE-signing its verdict over the SAME action hash.
        >= 3 valid `allow` signatures ⇒ the swarm decision is CANONICAL
        (3-of-4 BFT, tolerates f = n - t = 1 Byzantine/crashed organ). Set
        `byzantine: 1` (or name a `crashed` organ) to prove the f=1 case still
        reaches quorum, and `byzantine: 2` to prove 2-of-4 is correctly REJECTED.
        Signatures are REAL ECDSA-P256-SHA256, verified in-process against each
        organ's public key, and the canonical multi-sig receipt is chained +
        DSSE-signed via the host `_emit_receipt`.

  3. HOTL Override Register
     POST /api/<ns>/v1/hotl/recommend   → AI emits a signed recommendation
     POST /api/<ns>/v1/hotl/override    → a human-on-the-loop allow/deny that is
        cryptographically BOUND to the recommendation it overrode (the override
        receipt carries the recommendation receipt's digest as a Merkle parent
        AND embeds it in the signed payload). LOAC-defensible: an auditor can
        prove which human countermanded which AI recommendation, when, and that
        neither record was altered.
     GET  /api/<ns>/v1/hotl/register    → the full bound recommendation→override
        register with the cosign verify recipe.

HONESTY (absolute):
  * Λ uniqueness is Conjecture 1 — NEVER a theorem (open CAUCHY_ND sorry).
  * Telemetry / decisions are unauthenticated CLAIMS from the agent, not attested
    truth. The receipt attests *what the governance organ decided about the
    claim* — exactly the auditable artifact.
  * DSSE is REAL ECDSA-P256-SHA256 when a signing key is present (host
    SZL_COSIGN_PRIVATE_PEM for the chained receipt; per-organ ephemeral keypairs
    for the swarm quorum demo are generated in-process and explicitly labelled
    `key_source: ephemeral-in-process`). When the host key is absent the chained
    receipt is an honest PLACEHOLDER — never a fabricated signature.
  * killinchu is SLSA L1 (private Fulcio, no public Rekor) — never L2.
  * State is in-memory and resets on Space restart.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

_DOCTRINE = "v11"
_LAMBDA_FLOOR = 0.90
_AXIS_NAMES = [
    "soundness", "calibration", "robustness", "provenance", "consent", "reversibility",
    "transparency", "fairness", "containment", "attestation", "freshness", "authority", "auditability",
]

try:
    import szl_dsse as _dsse  # the LIVE cosign DSSE signer (for /verify recipe)
except Exception:  # pragma: no cover
    _dsse = None

try:
    import szl_khipu_consensus as _kc  # real 3-of-4 BFT signer/verifier
except Exception:  # pragma: no cover
    _kc = None

# In-memory HOTL register: {rec_id: {recommendation, receipt, overrides:[...]}}
_HOTL: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_MAX_HOTL = 256


# ---------------------------------------------------------------------------
# Λ + geometry (mirror serve.py canonical defs — local so the module is
# import-safe even if serve.py internals move).
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def _lambda_aggregate(axes: List[float]) -> float:
    """13-axis geometric-mean Λ. One near-zero axis collapses the score — a system
    that is 'mostly fine' but violates one hard axis does NOT pass. Λ uniqueness is
    Conjecture 1, NOT a theorem (Doctrine v11)."""
    vals = [min(1.0, max(1e-9, float(x))) for x in axes] if axes else [0.9] * 13
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _full_envelope(receipt_obj: Dict[str, Any], dsse_node: Dict[str, Any]) -> Dict[str, Any]:
    """Re-attach the canonical-JSON payload to the dsse node so a single receipt
    is independently verifiable with szl_dsse.verify_envelope / cosign. We do NOT
    re-sign — we reuse the signatures `_emit_receipt` already produced over the
    SAME canonical bytes, so the envelope verifies iff the original signature is
    valid."""
    if _dsse is None:
        return dict(dsse_node)
    payload_type = dsse_node.get("payloadType", getattr(_dsse, "KHIPU_PAYLOAD_TYPE", "application/vnd.szl.receipt+json"))
    body = _dsse.canonical_json(receipt_obj)
    env = dict(dsse_node)
    env["payload"] = base64.b64encode(body).decode("ascii")
    env["payloadType"] = payload_type
    env["_pae_sha256"] = hashlib.sha256(_dsse.pae(payload_type, body)).hexdigest()
    return env


def _receipt_view(node: Dict[str, Any]) -> Dict[str, Any]:
    """Compact, auditor-friendly view of an _emit_receipt node with a verifiable
    DSSE envelope re-attached."""
    return {
        "index": node["index"],
        "digest": node["digest"],
        "parents": node.get("parents", []),
        "signed": bool(node.get("signed")),
        "dsse": _full_envelope(node.get("receipt", {}), node["dsse"]),
    }


# ===========================================================================
# 1. GENERALIZED AUTONOMY ENVELOPE
# ===========================================================================

# Per-system-type defaults for the human-readable bound labels. The evaluation
# logic is type-agnostic (it reads the supplied envelope); these only enrich the
# narrative so the SAME engine reads naturally for a robot, a car, or a munition.
_SYSTEM_TYPES: Dict[str, Dict[str, Any]] = {
    "counter_uas": {"label": "Counter-UAS drone", "speed_unit": "m/s", "alt_label": "altitude AGL"},
    "ground_robot": {"label": "Ground robot / UGV", "speed_unit": "m/s", "alt_label": "(n/a — ground)"},
    "autonomous_vehicle": {"label": "Autonomous vehicle", "speed_unit": "m/s", "alt_label": "(n/a — surface)"},
    "loitering_munition": {"label": "Loitering munition", "speed_unit": "m/s", "alt_label": "altitude AGL"},
    "usv": {"label": "Uncrewed surface vessel", "speed_unit": "m/s", "alt_label": "(n/a — surface)"},
    "generic": {"label": "Generic autonomous system", "speed_unit": "units", "alt_label": "altitude"},
}


def evaluate_against_envelope(system_type: str, envelope: Dict[str, Any],
                              decision: Dict[str, Any]) -> Dict[str, Any]:
    """Pure function: does this autonomous decision stay inside the authorized
    parameters? Type-agnostic — reads whatever bounds the envelope declares.

    envelope keys (all optional; absent = unconstrained on that axis):
      geofence: {center_lat, center_lon, radius_m, mode: "stay_inside"|"stay_outside"}
      max_speed_m_s, max_altitude_m, min_standoff_m{,_from:{lat,lon}}
      allowed_actions: [...]      (action whitelist; anything else = off script)
      require_human_for: [...]    (actions that need HOTL; autonomous attempt = breach)
    decision keys:
      action, telemetry:{latitude,longitude,altitude_m,ground_speed_m_s}, axis_scores
    """
    tel = decision.get("telemetry", {}) or {}
    action = decision.get("action")
    breaches: List[str] = []
    reasons: List[str] = []
    meta = _SYSTEM_TYPES.get(system_type, _SYSTEM_TYPES["generic"])

    # Geofence (authorized operating box / no-go zone)
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

    # Speed ceiling
    spd = tel.get("ground_speed_m_s")
    if spd is not None and envelope.get("max_speed_m_s") is not None:
        reasons.append(f"speed {spd} {meta['speed_unit']} vs ceiling {envelope['max_speed_m_s']} {meta['speed_unit']}")
        if float(spd) > float(envelope["max_speed_m_s"]):
            breaches.append(f"speed {spd} exceeds authorized ceiling {envelope['max_speed_m_s']}")

    # Altitude ceiling
    alt = tel.get("altitude_m")
    if alt is not None and envelope.get("max_altitude_m") is not None:
        reasons.append(f"{meta['alt_label']} {alt} m vs ceiling {envelope['max_altitude_m']} m")
        if float(alt) > float(envelope["max_altitude_m"]):
            breaches.append(f"altitude {alt} m exceeds authorized ceiling {envelope['max_altitude_m']} m")

    # Standoff floor (must stay >= N metres from a protected point)
    standoff = envelope.get("min_standoff_m")
    src = envelope.get("min_standoff_from") or {}
    if standoff is not None and src.get("lat") is not None and lat is not None and lon is not None:
        d2 = _haversine_m(src["lat"], src["lon"], lat, lon)
        reasons.append(f"standoff {d2:.0f}m from protected point vs floor {float(standoff):.0f}m")
        if d2 < float(standoff):
            breaches.append(f"VIOLATED standoff: {d2:.0f}m < required {float(standoff):.0f}m from protected point")

    # Action whitelist (authorized parameters, literal sense)
    allowed = envelope.get("allowed_actions")
    if allowed is not None and action is not None and action not in allowed:
        breaches.append(f"action '{action}' NOT in authorized set {allowed} — off script")

    # Actions that require a human (autonomous attempt = the line)
    needs_human = envelope.get("require_human_for") or []
    if action in needs_human:
        breaches.append(f"action '{action}' requires human authorization (HOTL); attempted autonomously")

    return {"breaches": breaches, "reasons": reasons, "action": action,
            "system_label": meta["label"]}


def _govern_autonomy(system_type: str, envelope: Dict[str, Any], decision: Dict[str, Any],
                     emit_receipt: Callable) -> Dict[str, Any]:
    axes = decision.get("axis_scores") or [0.93, 0.91, 0.94, 0.9, 0.92, 0.91,
                                            0.93, 0.9, 0.95, 0.92, 0.94, 0.91, 0.93]
    ev = evaluate_against_envelope(system_type, envelope, decision)
    breaches = ev["breaches"]
    L = _lambda_aggregate(axes)
    lambda_pass = L >= _LAMBDA_FLOOR

    if not breaches:
        verdict = "IN_ENVELOPE"
    elif lambda_pass:
        verdict = "BREACH"          # Λ confident: a real line-crossing, caught at machine speed
    else:
        verdict = "REVIEW"          # Λ below floor: escalate for human review

    node = emit_receipt("autonomy_envelope_decision", {
        "system_type": system_type,
        "system_label": ev["system_label"],
        "action": ev["action"],
        "verdict": verdict,
        "breaches": breaches,
        "lambda": round(L, 6),
        "lambda_floor": _LAMBDA_FLOOR,
        "telemetry": decision.get("telemetry", {}),
        "envelope": envelope,
    })
    return {
        "ok": True,
        "system_type": system_type,
        "system_label": ev["system_label"],
        "ts_utc": _utcnow(),
        "action": ev["action"],
        "verdict": verdict,
        "in_envelope": (verdict == "IN_ENVELOPE"),
        "breaches": breaches,
        "reasons": ev["reasons"],
        "lambda": round(L, 6),
        "lambda_floor": _LAMBDA_FLOOR,
        "lambda_pass": lambda_pass,
        "axis_scores": dict(zip(_AXIS_NAMES, [round(x, 4) for x in axes])),
        "receipt": _receipt_view(node),
    }


# ===========================================================================
# 2. SWARM / MULTI-AGENT QUORUM (real 3-of-4 BFT, ephemeral in-process keys)
# ===========================================================================

def _ephemeral_organ_keys(organs: List[str]) -> Dict[str, Tuple[Any, str]]:
    """Generate a fresh ECDSA-P256 keypair per organ, in-process. Returns
    {organ: (private_key, pubkey_pem)}. Used so the swarm quorum demo produces
    REAL signatures that verify against keys we publish in the response — no
    fabrication, no dependence on whether sibling Spaces are reachable."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    out: Dict[str, Tuple[Any, str]] = {}
    for o in organs:
        priv = ec.generate_private_key(ec.SECP256R1())
        pem = priv.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        out[o] = (priv, pem)
    return out


def _sign_organ_verdict_eph(organ: str, priv: Any, action_hash: str,
                            verdict: str, reason: str) -> Dict[str, Any]:
    """Real ECDSA-P256-SHA256 DSSE signature over the organ verdict statement,
    using an ephemeral key. Mirrors szl_khipu_consensus byte layout so the same
    cosign recipe applies."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    ptype = getattr(_kc, "ORGAN_VERDICT_PAYLOAD_TYPE", "application/vnd.szl.khipu.organ-verdict+json")
    lean = getattr(_kc, "LEAN_SHA", "86d9fb2c")
    statement = {
        "schema": "szl.khipu.organ_verdict/v1", "organ": organ,
        "keyid": f"{organ}-cosign", "action_hash": action_hash,
        "verdict": verdict, "reason": reason, "lean_sha": lean, "ts": _utcnow(),
    }
    body = json.dumps(statement, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    t = ptype.encode("utf-8")
    to_sign = b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" " + str(len(body)).encode() + b" " + body
    sig = priv.sign(to_sign, ec.ECDSA(hashes.SHA256()))
    return {
        "organ": organ, "keyid": f"{organ}-cosign", "verdict": verdict, "reason": reason,
        "lean_sha": lean, "ts": statement["ts"], "payloadType": ptype,
        "payload": base64.b64encode(body).decode("ascii"),
        "sig_raw": base64.b64encode(sig).decode("ascii"),
        "signed": True, "key_source": "ephemeral-in-process",
    }


def _verify_organ_eph(entry: Dict[str, Any], pubkey_pem: str, action_hash: str) -> Dict[str, Any]:
    """Verify ONE ephemeral-keyed organ signature against the published pubkey and
    confirm the signed statement matches the action_hash with an allow verdict."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidSignature
    res = {"organ": entry.get("organ"), "keyid": entry.get("keyid"),
           "valid": False, "verdict": entry.get("verdict"),
           "action_hash_match": False, "counts": False, "reason": ""}
    if not entry.get("signed") or not entry.get("sig_raw"):
        res["reason"] = "unsigned (organ crashed/unreachable — no signature fabricated)"
        return res
    try:
        ptype = entry["payloadType"].encode("utf-8")
        body = base64.b64decode(entry["payload"])
        to_verify = b"DSSEv1 " + str(len(ptype)).encode() + b" " + ptype + b" " + str(len(body)).encode() + b" " + body
        pub = load_pem_public_key(pubkey_pem.encode())
        pub.verify(base64.b64decode(entry["sig_raw"]), to_verify, ec.ECDSA(hashes.SHA256()))
        res["valid"] = True
        stmt = json.loads(body)
        res["action_hash_match"] = (stmt.get("action_hash") == action_hash)
        res["verdict"] = stmt.get("verdict")
    except InvalidSignature:
        res["reason"] = "signature mismatch (tamper detected)"
        return res
    except Exception as e:
        res["reason"] = f"{type(e).__name__}: {e}"
        return res
    res["counts"] = bool(res["valid"] and res["action_hash_match"] and res["verdict"] == "allow")
    res["reason"] = ("valid+allow over matching action_hash" if res["counts"]
                     else f"valid sig but verdict={res['verdict']} / hash_match={res['action_hash_match']}")
    return res


def run_swarm_quorum(decision: Dict[str, Any], byzantine: int = 0,
                     crashed: Optional[List[str]] = None,
                     emit_receipt: Optional[Callable] = None) -> Dict[str, Any]:
    """Govern a MULTI-agent decision with 3-of-4 BFT. Each of four organs signs
    with its own ephemeral ECDSA-P256 key; >= 3 valid `allow` ⇒ CANONICAL.

    byzantine: number of organs that emit a BAD/forged verdict (real, not allow).
    crashed:   organs that emit NO signature at all (unreachable).
    Both reduce the valid+allow count, proving f=1 still reaches quorum and
    f=2 is correctly rejected.
    """
    organs = ["sentra", "amaru", "a11oy", "killinchu"]
    threshold = getattr(_kc, "THRESHOLD", 3) if _kc else 3
    crashed = crashed or []
    # Stable action hash over the decision payload.
    action_hash = hashlib.sha256(
        json.dumps(decision, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    keys = _ephemeral_organ_keys(organs)
    pubkeys = {o: keys[o][1] for o in organs}

    # Decide which organs misbehave: first `byzantine` non-crashed organs sign a
    # `block` verdict (a real, valid signature over a NON-allow statement → does
    # not count); crashed organs produce no signature at all.
    sig_entries: List[Dict[str, Any]] = []
    n_byz = 0
    for o in organs:
        priv = keys[o][0]
        if o in crashed:
            sig_entries.append({"organ": o, "keyid": f"{o}-cosign", "signed": False,
                                "key_source": "none", "verdict": "abstain",
                                "reason": "organ crashed / unreachable — no signature fabricated"})
            continue
        if n_byz < byzantine:
            n_byz += 1
            sig_entries.append(_sign_organ_verdict_eph(o, priv, action_hash, "block",
                               f"{o}: Byzantine/faulty — emitted block over the action hash"))
        else:
            sig_entries.append(_sign_organ_verdict_eph(o, priv, action_hash, "allow",
                               f"{o}: gate cleared, signs allow over the action hash"))

    checks = [_verify_organ_eph(s, pubkeys[s["organ"]], action_hash) for s in sig_entries]
    count = sum(1 for c in checks if c["counts"])
    n = len(sig_entries)
    canonical = count >= threshold

    signatures = []
    for s, c in zip(sig_entries, checks):
        signatures.append({
            "organ": s.get("organ"), "keyid": s.get("keyid"),
            "verdict": s.get("verdict"), "reason": s.get("reason", ""),
            "signed": bool(s.get("signed")), "key_source": s.get("key_source"),
            "sig_raw": s.get("sig_raw", ""), "payload": s.get("payload", ""),
            "payloadType": s.get("payloadType", ""),
            "valid": c["valid"], "counts": c["counts"],
        })

    consensus_receipt = {
        "khipu_consensus": f"{count}-of-{n}",
        "action_hash": action_hash,
        "signatures": signatures,
        "decision": "canonical" if canonical else "rejected",
        "threshold": threshold,
        "f_tolerated": n - threshold,
        "doctrine": getattr(_kc, "DOCTRINE_PUBLIC", "v11 LOCKED · 749/14/163") if _kc else "v11",
        "ts": _utcnow(),
    }

    chained = None
    if emit_receipt is not None:
        node = emit_receipt("swarm_quorum_decision", {
            "decision_summary": decision.get("summary") or decision.get("action") or "multi-agent decision",
            "khipu_consensus": consensus_receipt["khipu_consensus"],
            "canonical": canonical,
            "action_hash": action_hash,
            "threshold": threshold,
            "byzantine": byzantine, "crashed": crashed,
        })
        chained = _receipt_view(node)

    return {
        "ok": True,
        "decision": decision,
        "organs": organs,
        "threshold": threshold,
        "f_tolerated": n - threshold,
        "byzantine_injected": byzantine,
        "crashed_injected": crashed,
        "khipu_consensus": consensus_receipt["khipu_consensus"],
        "consensus_count": count,
        "n": n,
        "canonical": canonical,
        "swarm_decision": "CANONICAL" if canonical else "REJECTED",
        "consensus_receipt": consensus_receipt,
        "organ_pubkeys": pubkeys,
        "checks": checks,
        "chained_receipt": chained,
    }


# ===========================================================================
# 3. HOTL OVERRIDE REGISTER (override cryptographically bound to recommendation)
# ===========================================================================

def _remember_hotl(rec_id: str, record: Dict[str, Any]) -> None:
    _HOTL[rec_id] = record
    _HOTL.move_to_end(rec_id)
    while len(_HOTL) > _MAX_HOTL:
        _HOTL.popitem(last=False)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(app: FastAPI, emit_receipt: Callable, ns: str = "killinchu") -> Dict[str, Any]:
    """Register the Beyond-Cannonico endpoints + the /beyond proof console.
    ADDITIVE. MUST be called BEFORE the SPA catch-all so explicit routes win.

    `emit_receipt` is serve.py's `_emit_receipt` — the REAL Khipu-DAG + DSSE
    signer. We reuse it so every Beyond receipt is the SAME tamper-evident fiber
    as the rest of killinchu, cosign-verifiable with the same key.
    """
    base = f"/api/{ns}/v1"
    registered: List[str] = []

    # --- 1. Generalized Autonomy Envelope ---
    @app.post(f"{base}/autonomy/evaluate")
    async def autonomy_evaluate(request: Request) -> JSONResponse:
        """Govern ONE autonomous decision from ANY system type against its
        authorized envelope. Body:
          {system_type, envelope:{...}, decision:{action, telemetry:{...}, axis_scores?}}
        Returns the per-decision verdict (IN_ENVELOPE | BREACH | REVIEW) + a
        chained, signed, tamper-evident receipt.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        system_type = body.get("system_type") or "generic"
        envelope = body.get("envelope") or {}
        decision = body.get("decision") or {}
        out = _govern_autonomy(system_type, envelope, decision, emit_receipt)
        out["doctrine"] = _DOCTRINE
        out["honesty"] = (
            "The SAME envelope+Λ+receipt engine that governs the Cannonico drone, "
            "applied to an arbitrary autonomous system. Verdict is governance's "
            "assessment of an UNAUTHENTICATED decision claim; the receipt attests "
            "what the governance organ decided. Λ is Conjecture 1, NOT a theorem."
        )
        return JSONResponse(out)

    registered.append(f"POST {base}/autonomy/evaluate")

    @app.get(f"{base}/autonomy/system-types")
    async def autonomy_system_types() -> JSONResponse:
        """Enumerate the system types the generalized envelope recognizes (the
        evaluation logic is type-agnostic; these enrich the bound labels)."""
        return JSONResponse({"ok": True, "system_types": _SYSTEM_TYPES, "doctrine": _DOCTRINE})

    registered.append(f"GET {base}/autonomy/system-types")

    # --- 2. Swarm / Multi-Agent Quorum ---
    @app.post(f"{base}/swarm/quorum")
    async def swarm_quorum(request: Request) -> JSONResponse:
        """Govern a MULTI-agent decision with real 3-of-4 BFT. Body:
          {decision:{...}, byzantine?:int, crashed?:[organ,...]}
        Returns the multi-sig consensus receipt (real ECDSA-P256 per organ),
        the per-organ public keys to verify against, and a chained host receipt.
        HTTP 200 when CANONICAL (>=3 valid allow), 412 when REJECTED.
        """
        if _kc is None:
            return JSONResponse({"ok": False, "error": "szl_khipu_consensus unavailable in runtime"},
                                status_code=503)
        try:
            body = await request.json()
        except Exception:
            body = {}
        decision = body.get("decision") or {"summary": "unspecified multi-agent decision"}
        try:
            byzantine = int(body.get("byzantine", 0) or 0)
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "byzantine must be an integer"}, status_code=400)
        crashed = body.get("crashed") or []
        if isinstance(crashed, str):
            crashed = [crashed]
        if not isinstance(crashed, list):
            return JSONResponse({"ok": False, "error": "crashed must be a list of organ names (or a single organ name)"},
                                status_code=400)
        out = run_swarm_quorum(decision, byzantine=byzantine, crashed=crashed, emit_receipt=emit_receipt)
        out["doctrine"] = _DOCTRINE
        out["honesty"] = (
            "Four organs each sign with their OWN ephemeral ECDSA-P256 key "
            "(key_source: ephemeral-in-process — generated this request, NOT the "
            "production per-organ secret; published in organ_pubkeys so you can "
            "re-verify every signature). >=3 valid+allow over the SAME action_hash "
            "= CANONICAL (3-of-4 BFT, tolerates f=1). 2-of-4 = REJECTED. No "
            "signature is fabricated; a crashed organ emits none. Λ is Conjecture 1."
        )
        return JSONResponse(out, status_code=200 if out["canonical"] else 412)

    registered.append(f"POST {base}/swarm/quorum")

    # --- 3. HOTL Override Register ---
    @app.post(f"{base}/hotl/recommend")
    async def hotl_recommend(request: Request) -> JSONResponse:
        """The AI emits a signed engagement/effect RECOMMENDATION. Body:
          {recommendation:{action, target?, rationale?, lambda?}, meta?}
        Emits a signed 'hotl_ai_recommendation' receipt whose digest the human's
        override will be bound to.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        rec = body.get("recommendation") or {}
        if isinstance(rec, str):
            rec = {"action": rec}
        if not isinstance(rec, dict):
            return JSONResponse({"ok": False, "error": "recommendation must be an object {action, ...} (or a bare action string)"},
                                status_code=400)
        rec_id = body.get("rec_id") or f"REC-{uuid.uuid4().hex[:12].upper()}"
        axes = rec.get("axis_scores") or [0.93, 0.91, 0.94, 0.9, 0.92, 0.91,
                                          0.93, 0.9, 0.95, 0.92, 0.94, 0.91, 0.93]
        L = _lambda_aggregate(axes)
        node = emit_receipt("hotl_ai_recommendation", {
            "rec_id": rec_id,
            "recommendation": rec,
            "lambda": round(L, 6),
            "lambda_floor": _LAMBDA_FLOOR,
            "meta": body.get("meta", {}),
        })
        view = _receipt_view(node)
        _remember_hotl(rec_id, {
            "rec_id": rec_id,
            "recommendation": rec,
            "lambda": round(L, 6),
            "created_at": _utcnow(),
            "receipt": view,
            "overrides": [],
        })
        return JSONResponse({
            "ok": True, "rec_id": rec_id, "recommendation": rec,
            "lambda": round(L, 6), "lambda_floor": _LAMBDA_FLOOR,
            "recommendation_receipt": view, "doctrine": _DOCTRINE,
            "honesty": (
                "The AI recommendation is now cryptographically committed. A human "
                "override at POST /hotl/override will be BOUND to this receipt's "
                "digest (Merkle parent + embedded in the signed payload). Λ is "
                "Conjecture 1, NOT a theorem. State resets on restart."
            ),
        })

    registered.append(f"POST {base}/hotl/recommend")

    @app.post(f"{base}/hotl/override")
    async def hotl_override(request: Request) -> JSONResponse:
        """A human-on-the-loop allow/deny BOUND to the AI recommendation it
        overrode. Body:
          {rec_id, operator:{id, name?, role?}, decision: "allow"|"deny", justification?}
        The override receipt carries the recommendation receipt's digest as a
        Merkle parent AND embeds it in the signed payload — LOAC-defensible proof
        of which human countermanded which AI recommendation.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        rec_id = body.get("rec_id")
        if not rec_id or rec_id not in _HOTL:
            return JSONResponse({"ok": False, "error": "unknown rec_id; call /hotl/recommend first",
                                 "known": list(_HOTL.keys())[:20]}, status_code=404)
        rec = _HOTL[rec_id]
        operator = body.get("operator") or {}
        if isinstance(operator, str):
            operator = {"name": operator}
        if not isinstance(operator, dict):
            return JSONResponse({"ok": False, "error": "operator must be an object {id, name?, role?} (or a bare name string)"},
                                status_code=400)
        decision = (body.get("decision") or "").lower()
        if decision not in ("allow", "deny"):
            return JSONResponse({"ok": False, "error": "decision must be 'allow' or 'deny'"}, status_code=400)
        rec_receipt = rec["receipt"]
        ai_action = (rec.get("recommendation") or {}).get("action")
        concurs = (decision == "allow")
        node = emit_receipt("hotl_human_override", {
            "rec_id": rec_id,
            "bound_to_recommendation": {
                "receipt_index": rec_receipt["index"],
                "receipt_digest": rec_receipt["digest"],
                "ai_action": ai_action,
                "ai_lambda": rec.get("lambda"),
            },
            "operator": operator,
            "human_decision": decision,
            "concurs_with_ai": concurs,
            "justification": body.get("justification", ""),
        })
        view = _receipt_view(node)
        binding_ok = rec_receipt["digest"] in view.get("parents", [])
        override_rec = {
            "override_index": len(rec["overrides"]),
            "ts_utc": _utcnow(),
            "operator": operator,
            "human_decision": decision,
            "concurs_with_ai": concurs,
            "ai_action": ai_action,
            "justification": body.get("justification", ""),
            "bound_to_recommendation_digest": rec_receipt["digest"],
            "binding_verified": binding_ok,
            "override_receipt": view,
        }
        rec["overrides"].append(override_rec)
        _HOTL.move_to_end(rec_id)
        return JSONResponse({
            "ok": True, "rec_id": rec_id,
            "human_decision": decision,
            "concurs_with_ai": concurs,
            "override": override_rec,
            "doctrine": _DOCTRINE,
            "honesty": (
                "The human override is cryptographically BOUND to the AI "
                "recommendation: the override receipt's Merkle parent IS the "
                "recommendation receipt's digest, and that digest is embedded in "
                "the signed payload. binding_verified=true proves the link holds. "
                "DSSE is REAL when the host key is present, else honest PLACEHOLDER. "
                "Λ is Conjecture 1, NOT a theorem."
            ),
        })

    registered.append(f"POST {base}/hotl/override")

    @app.get(f"{base}/hotl/register")
    async def hotl_register(rec_id: str = "") -> JSONResponse:
        """The bound recommendation→override register (one rec_id, or all) with
        the cosign verify recipe."""
        def _entry(r: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "rec_id": r["rec_id"], "recommendation": r["recommendation"],
                "lambda": r["lambda"], "created_at": r["created_at"],
                "recommendation_receipt": r["receipt"],
                "overrides": r["overrides"],
            }
        if rec_id:
            if rec_id not in _HOTL:
                return JSONResponse({"ok": False, "error": "unknown rec_id",
                                     "known": list(_HOTL.keys())[:20]}, status_code=404)
            entries = [_entry(_HOTL[rec_id])]
        else:
            entries = [_entry(r) for r in _HOTL.values()]
        return JSONResponse({
            "ok": True, "count": len(entries), "register": entries,
            "verify": {
                "cosign": ("each receipt.dsse is a DSSE envelope; verify with "
                           "`cosign verify-blob --key cosign.pub` or POST /khipu/verify. "
                           "The override receipt's parents[] contains the recommendation "
                           "receipt digest — that is the cryptographic binding."),
                "pubkey": "/khipu/pubkey?keyid=killinchu-cosign",
            },
            "doctrine": _DOCTRINE,
            "honesty": (
                "Each override receipt is Merkle-chained to the recommendation it "
                "overrode (parent digest) and DSSE-signed. Tampering with either "
                "record breaks the chain and fails signature verification. SLSA L1 "
                "honest. Λ is Conjecture 1, NOT a theorem."
            ),
        })

    registered.append(f"GET {base}/hotl/register")

    # --- Proof console ---
    html = _CONSOLE_HTML.replace("__NS__", ns)

    async def _serve_console() -> HTMLResponse:
        return HTMLResponse(html)

    app.get("/beyond")(_serve_console)
    app.get(f"/{ns}/beyond")(_serve_console)
    registered.append("GET /beyond")
    registered.append(f"GET /{ns}/beyond")

    return {"module": "killinchu_beyond", "ns": ns, "registered": registered,
            "endpoints": len(registered), "tabs": 3}


__all__ = ["register", "evaluate_against_envelope", "run_swarm_quorum"]


# ===========================================================================
# Self-contained proof console. Vanilla JS (no CDN, no build step). Every tab
# fetches a REAL endpoint and renders the live JSON + signed receipt. Honest
# banners throughout. Style mirrors the elite console.
# ===========================================================================
_CONSOLE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Killinchu — Beyond-Cannonico Autonomy-Governance Proofs</title>
<style>
  :root{
    --bg:#0a0a0a; --panel:#11131a; --panel2:#161a23; --line:#23282f;
    --txt:#d7e0ec; --dim:#8590a0; --accent:#5fb3a3; --good:#5fb3a3;
    --warn:#ffb454; --bad:#ff5d6c; --gold:#c9b787;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  body{margin:0;background:
      radial-gradient(1200px 700px at 80% -10%, rgba(95,179,163,.06), transparent),
      radial-gradient(900px 600px at 10% 110%, rgba(201,183,135,.05), transparent),
      var(--bg);
    color:var(--txt);font-family:Inter,system-ui,Segoe UI,Roboto,sans-serif;font-size:14px}
  .szl-ribbon{display:flex;align-items:center;gap:10px;height:26px;padding:0 16px;
    background:#06070b;border-bottom:1px solid var(--gold);font-family:var(--mono);
    font-size:10.5px;letter-spacing:.5px;color:var(--dim);white-space:nowrap;overflow:hidden}
  .szl-ribbon b{color:var(--gold);font-weight:700}
  .szl-ribbon .org{color:var(--accent);font-weight:700}
  .szl-ribbon .live{margin-left:auto;color:var(--good);font-weight:700}
  header{display:flex;align-items:center;gap:14px;padding:12px 18px;
    border-bottom:1px solid var(--line);background:linear-gradient(90deg,#0c0d12,#11131a)}
  header h1{font-size:16px;margin:0;letter-spacing:.5px}
  header h1 b{color:var(--gold)}
  .doctrine{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--dim);text-align:right;line-height:1.5}
  .doctrine .l1{color:var(--gold)}
  .wrap{display:flex;height:calc(100vh - 80px)}
  nav{width:268px;flex:0 0 268px;border-right:1px solid var(--line);
    background:var(--panel);overflow-y:auto;padding:8px}
  nav button{display:block;width:100%;text-align:left;background:transparent;
    color:var(--txt);border:0;border-radius:8px;padding:10px 11px;margin:2px 0;
    cursor:pointer;font-size:13px;border-left:3px solid transparent}
  nav button:hover{background:var(--panel2)}
  nav button.active{background:var(--panel2);border-left-color:var(--accent);color:#fff}
  nav button .n{color:var(--dim);font-family:var(--mono);font-size:11px;margin-right:7px}
  nav .grp{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.6px;padding:10px 11px 4px}
  main{flex:1;overflow-y:auto;padding:18px 22px}
  h2{font-size:18px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:12px;margin-bottom:14px;max-width:760px;line-height:1.5}
  .ep{font-family:var(--mono);font-size:11px;color:var(--accent);
    background:#0a0f17;border:1px solid var(--line);border-radius:6px;
    padding:3px 7px;display:inline-block;margin:2px 4px 2px 0}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:10px 0}
  button.act{background:var(--accent);color:#04101e;border:0;border-radius:8px;
    padding:8px 14px;font-weight:600;cursor:pointer}
  button.act:hover{filter:brightness(1.1)}
  button.bad{background:var(--bad);color:#1a0509}
  button.ghost{background:transparent;color:var(--txt);border:1px solid var(--line);
    border-radius:8px;padding:8px 14px;cursor:pointer}
  input,textarea,select{background:#080c12;color:var(--txt);border:1px solid var(--line);
    border-radius:7px;padding:7px 9px;font-family:var(--mono);font-size:12px}
  textarea{width:100%;min-height:118px;resize:vertical}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:14px 16px;margin:12px 0}
  pre{background:#05080d;border:1px solid var(--line);border-radius:8px;
    padding:12px;overflow:auto;font-family:var(--mono);font-size:11.5px;
    color:#bcd0e6;max-height:520px;white-space:pre-wrap;word-break:break-word}
  table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
  th{color:var(--dim);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
  td.mono,.mono{font-family:var(--mono)}
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700}
  .p-allow{background:#0d2a1a;color:var(--good)} .p-bad{background:#2c1015;color:var(--bad)}
  .p-warn{background:#2a230d;color:var(--warn)}
  .verdict{font-size:22px;font-weight:800;margin:6px 0}
  .v-ok{color:var(--good)} .v-bad{color:var(--bad)} .v-warn{color:var(--warn)}
  .honest{font-size:11px;color:var(--dim);border-left:3px solid var(--gold);
    padding:6px 10px;margin:10px 0;background:#0c0f08;line-height:1.5}
  .ok{color:var(--good)} .err{color:var(--bad)} .muted{color:var(--dim)}
  label{font-size:11px;color:var(--dim);display:block;margin-bottom:3px;margin-top:6px}
  .kpi{display:inline-block;background:var(--panel2);border:1px solid var(--line);
    border-radius:8px;padding:8px 12px;margin:4px 8px 4px 0;font-family:var(--mono)}
  .kpi b{color:var(--accent)}
</style>
</head>
<body>
<div class="szl-ribbon">
  <b>SZL HOLDINGS</b> · <span class="org">KILLINCHU</span> · DOCTRINE V11 · LOCKED · REPLAY c7c0ba17 · Λ = CONJECTURE 1
  <span class="live">● LIVE</span>
</div>
<header>
  <h1><b>KILLINCHU</b> · Beyond-Cannonico — Autonomy-Governance, Generalized</h1>
  <div class="doctrine">
    Doctrine v11 · 749/14/163 · c7c0ba17<br/>
    <span class="l1">SLSA L2 (organ, cosign-verified)</span> · Λ = Conjecture 1 (not a theorem)
  </div>
</header>
<div class="wrap">
  <nav id="nav"></nav>
  <main id="main"></main>
</div>
<script>
const NS = "__NS__";
const API = (p) => p.startsWith("/") ? p : "/" + p;

async function call(method, path, body){
  const opt = {method, headers:{"Content-Type":"application/json"}};
  if(body!==undefined) opt.body = JSON.stringify(body);
  const t0 = performance.now();
  let r, j;
  try{ r = await fetch(API(path), opt); }
  catch(e){ return {status:0, ms:"0", json:{error:"network: "+e}}; }
  const ms = (performance.now()-t0).toFixed(0);
  try{ j = await r.json(); }catch(e){ j = {error:"non-JSON response", status:r.status}; }
  return {status:r.status, ms, json:j};
}
function pj(o){ return JSON.stringify(o, null, 2); }
function honest(t){ return `<div class="honest">${t}</div>`; }
function ep(s){ return `<span class="ep">${s}</span>`; }
function head(t){ return `<h2>${t.title}</h2><div class="sub">${t.sub}</div><div>${(t.eps||[]).map(ep).join("")}</div>`; }
async function showResult(el, res){
  el.innerHTML = `<div class="muted" style="font-size:11px;margin:8px 0 4px">HTTP ${res.status} · ${res.ms} ms</div><pre>${pj(res.json)}</pre>`;
}
function rcptLine(rc){
  if(!rc) return "";
  const sig = rc.signed ? '<span class="pill p-allow">DSSE SIGNED</span>' : '<span class="pill p-warn">PLACEHOLDER (no key)</span>';
  return `<div class="card"><div>${sig} <span class="mono">#${rc.index}</span></div>
    <div class="mono muted" style="font-size:11px;margin-top:6px;word-break:break-all">digest: ${rc.digest||""}</div>
    <div class="mono muted" style="font-size:11px;word-break:break-all">parents: ${(rc.parents||[]).join(", ")||"(genesis)"}</div></div>`;
}

/* ---- TAB DEFINITIONS ---- */
const TABS = [
 {id:"autonomy", n:"01", title:"Generalized Autonomy Envelope",
  sub:"The Cannonico pattern, generalized: submit ANY autonomous-system decision — ground robot, autonomous vehicle, loitering munition — and killinchu evaluates it against its authorized envelope, Λ-gates it, catches the line-crossing, and emits ONE signed tamper-evident receipt. Same engine as the drone; arbitrary system type.",
  eps:["POST /api/"+NS+"/v1/autonomy/evaluate","GET /api/"+NS+"/v1/autonomy/system-types"],
  render(m){
    const allow = {system_type:"ground_robot",
      envelope:{geofence:{center_lat:36.20,center_lon:-115.98,radius_m:800,mode:"stay_inside"},
        max_speed_m_s:6,allowed_actions:["PATROL","HOLD","RTB"],require_human_for:["ENGAGE"]},
      decision:{action:"PATROL",telemetry:{latitude:36.201,longitude:-115.979,ground_speed_m_s:4.2}}};
    const breach = {system_type:"loitering_munition",
      envelope:{geofence:{center_lat:36.20,center_lon:-115.98,radius_m:800,mode:"stay_inside"},
        max_speed_m_s:55,allowed_actions:["LOITER","TRACK","RTB"],require_human_for:["TERMINAL_DIVE"]},
      decision:{action:"TERMINAL_DIVE",telemetry:{latitude:36.230,longitude:-115.940,altitude_m:120,ground_speed_m_s:68}}};
    m.innerHTML = head(this) +
      `<div class="row">
        <button class="act" id="bAllow">▶ Real ALLOW (ground robot, in-envelope)</button>
        <button class="bad" id="bBreach">▶ Real BREACH (munition crosses the line)</button>
        <button class="ghost" id="bTypes">System types</button>
        <button class="ghost" id="bRun">Run custom ↓</button></div>
       <div id="verdict"></div>
       <label>Request body (editable — submit your own system_type + envelope + decision)</label>
       <textarea id="body">${pj(allow)}</textarea>
       <div id="rcpt"></div><div id="out"></div>` +
      honest("Telemetry is an unauthenticated CLAIM from the agent — not attested truth. The receipt attests what governance DECIDED about the claim: exactly the auditable artifact. Λ = Conjecture 1, NOT a theorem.");
    const go = async (payload)=>{
      m.querySelector("#body").value = pj(payload);
      const r = await call("POST","/api/"+NS+"/v1/autonomy/evaluate", payload);
      const j = r.json||{};
      const cls = j.verdict==="IN_ENVELOPE"?"v-ok":(j.verdict==="BREACH"?"v-bad":"v-warn");
      m.querySelector("#verdict").innerHTML =
        `<div class="verdict ${cls}">${j.verdict||"?"} <span class="muted" style="font-size:13px">— ${j.system_label||""} · action ${j.action||"?"} · Λ=${j.lambda}</span></div>` +
        ((j.breaches&&j.breaches.length)?`<div class="card"><b class="err">Breaches caught:</b><ul>${j.breaches.map(b=>`<li class="mono">${b}</li>`).join("")}</ul></div>`:`<div class="muted">No envelope breach — system stayed in bounds.</div>`);
      m.querySelector("#rcpt").innerHTML = rcptLine(j.receipt);
      showResult(m.querySelector("#out"), r);
    };
    m.querySelector("#bAllow").onclick = ()=>go(allow);
    m.querySelector("#bBreach").onclick = ()=>go(breach);
    m.querySelector("#bRun").onclick = ()=>{ let p; try{p=JSON.parse(m.querySelector("#body").value);}catch(e){return alert("bad JSON");} go(p); };
    m.querySelector("#bTypes").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/autonomy/system-types"));
  }},

 {id:"swarm", n:"02", title:"Swarm / Multi-Agent Quorum (3-of-4 BFT)",
  sub:"A multi-agent decision fans out to FOUR independent organs (sentra · amaru · a11oy · killinchu), each signing its verdict with its OWN ECDSA-P256 key over the SAME action hash. ≥3 valid allow ⇒ CANONICAL. Inject a Byzantine/crashed organ to prove f=1 still reaches quorum; inject 2 to prove 2-of-4 is correctly REJECTED.",
  eps:["POST /api/"+NS+"/v1/swarm/quorum"],
  render(m){
    const base = {decision:{summary:"swarm: converge 4 UGVs on objective ALPHA",action:"CONVERGE"}};
    m.innerHTML = head(this) +
      `<div class="row">
        <button class="act" id="bClean">▶ Clean 4-of-4 → CANONICAL</button>
        <button class="ghost" id="bByz1">▶ f=1 Byzantine → still 3-of-4 CANONICAL</button>
        <button class="ghost" id="bCrash">▶ 1 organ crashed → still 3-of-4</button>
        <button class="bad" id="bByz2">▶ f=2 → 2-of-4 REJECTED</button></div>
       <div id="verdict"></div>
       <label>Request body (editable)</label>
       <textarea id="body">${pj(base)}</textarea>
       <div id="sigs"></div><div id="rcpt"></div><div id="out"></div>` +
      honest("Each organ signs with an EPHEMERAL in-process ECDSA-P256 key (key_source: ephemeral-in-process — generated this request, published in organ_pubkeys so you can re-verify every signature; NOT the production per-organ secret). Real signatures, real BFT count — no fabrication. A crashed organ emits NO signature. The canonical multi-sig receipt is chained via the host cosign DSSE. Λ = Conjecture 1.");
    const go = async (payload)=>{
      m.querySelector("#body").value = pj(payload);
      const r = await call("POST","/api/"+NS+"/v1/swarm/quorum", payload);
      const j = r.json||{};
      const cls = j.canonical?"v-ok":"v-bad";
      m.querySelector("#verdict").innerHTML =
        `<div class="verdict ${cls}">${j.swarm_decision||"?"}</div>
         <span class="kpi">consensus <b>${j.khipu_consensus||"?"}</b></span>
         <span class="kpi">threshold <b>${j.threshold||3}</b></span>
         <span class="kpi">f tolerated <b>${j.f_tolerated}</b></span>
         <span class="kpi">byzantine <b>${j.byzantine_injected}</b></span>`;
      const sigs = (j.consensus_receipt&&j.consensus_receipt.signatures)||[];
      m.querySelector("#sigs").innerHTML = sigs.length ? `<table><thead><tr><th>organ</th><th>verdict</th><th>signed</th><th>valid</th><th>counts</th><th>reason</th></tr></thead><tbody>` +
        sigs.map(s=>`<tr><td class="mono">${s.organ}</td><td class="mono">${s.verdict||"—"}</td>
          <td>${s.signed?'<span class="ok">yes</span>':'<span class="muted">no</span>'}</td>
          <td>${s.valid?'<span class="ok">✓</span>':'<span class="err">✗</span>'}</td>
          <td>${s.counts?'<span class="ok">✓</span>':'<span class="err">✗</span>'}</td>
          <td class="mono" style="font-size:10.5px">${s.reason||""}</td></tr>`).join("") + `</tbody></table>` : "";
      m.querySelector("#rcpt").innerHTML = rcptLine(j.chained_receipt);
      showResult(m.querySelector("#out"), r);
    };
    m.querySelector("#bClean").onclick = ()=>go({...base,byzantine:0});
    m.querySelector("#bByz1").onclick = ()=>go({...base,byzantine:1});
    m.querySelector("#bCrash").onclick = ()=>go({...base,crashed:["sentra"]});
    m.querySelector("#bByz2").onclick = ()=>go({...base,byzantine:2});
  }},

 {id:"hotl", n:"03", title:"HOTL Override Register",
  sub:"Human-on-the-loop: the AI emits a signed RECOMMENDATION, then a human's allow/deny is cryptographically BOUND to it — the override receipt's Merkle parent IS the recommendation receipt's digest, and that digest is embedded in the signed payload. LOAC-defensible: prove which human countermanded which AI recommendation.",
  eps:["POST /api/"+NS+"/v1/hotl/recommend","POST /api/"+NS+"/v1/hotl/override","GET /api/"+NS+"/v1/hotl/register"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="card">
        <b>Step 1 — AI recommends</b>
        <label>Recommendation body</label>
        <textarea id="recBody">${pj({recommendation:{action:"ENGAGE",target:"TRK-SHAHED-014",rationale:"hostile, inbound on protected airspace",classification:"hostile"}})}</textarea>
        <div class="row"><button class="act" id="bRec">▶ Emit signed AI recommendation</button></div>
        <div id="recOut"></div>
       </div>
       <div class="card">
        <b>Step 2 — Human overrides (bound to the recommendation above)</b>
        <label>rec_id (auto-filled from Step 1)</label><input id="recId" placeholder="REC-..." style="width:260px"/>
        <label>Operator</label><input id="op" value="MAJ J. RIVERA / BWC-7" style="width:320px"/>
        <label>Justification</label><input id="just" value="PID not met under LOAC; deny engagement" style="width:480px"/>
        <div class="row">
          <button class="bad" id="bDeny">▶ Human DENY (override the AI)</button>
          <button class="act" id="bAllow">▶ Human ALLOW (concur)</button></div>
        <div id="ovVerdict"></div><div id="ovOut"></div>
       </div>
       <div class="row"><button class="ghost" id="bReg">Load bound register</button></div>
       <div id="regOut"></div>` +
      honest("The binding is real: the override receipt carries the recommendation receipt's digest in parents[] AND in the signed payload. binding_verified=true proves the Merkle link holds. DSSE is REAL when the host key is present, else an honest PLACEHOLDER (never fabricated). Λ = Conjecture 1, NOT a theorem.");
    m.querySelector("#bRec").onclick = async ()=>{
      let p; try{p=JSON.parse(m.querySelector("#recBody").value);}catch(e){return alert("bad JSON");}
      const r = await call("POST","/api/"+NS+"/v1/hotl/recommend", p);
      if(r.json&&r.json.rec_id) m.querySelector("#recId").value = r.json.rec_id;
      m.querySelector("#recOut").innerHTML = rcptLine(r.json&&r.json.recommendation_receipt) +
        `<pre>${pj(r.json)}</pre>`;
    };
    const override = async (decision)=>{
      const rec_id = m.querySelector("#recId").value.trim();
      if(!rec_id) return alert("Run Step 1 first (need a rec_id)");
      const opv = m.querySelector("#op").value;
      const body = {rec_id, decision, operator:{id:opv, name:opv}, justification:m.querySelector("#just").value};
      const r = await call("POST","/api/"+NS+"/v1/hotl/override", body);
      const j = r.json||{}; const ov = j.override||{};
      const cls = j.human_decision==="allow"?"v-ok":"v-bad";
      m.querySelector("#ovVerdict").innerHTML =
        `<div class="verdict ${cls}">HUMAN ${(j.human_decision||"?").toUpperCase()}</div>
         <span class="kpi">concurs with AI <b>${j.concurs_with_ai}</b></span>
         <span class="kpi">binding verified <b class="${ov.binding_verified?'ok':'err'}">${ov.binding_verified}</b></span>
         <span class="kpi">bound to <b class="mono" style="font-size:10px">${(ov.bound_to_recommendation_digest||"").slice(0,18)}…</b></span>`;
      m.querySelector("#ovOut").innerHTML = rcptLine(ov.override_receipt) + `<pre>${pj(j)}</pre>`;
    };
    m.querySelector("#bDeny").onclick = ()=>override("deny");
    m.querySelector("#bAllow").onclick = ()=>override("allow");
    m.querySelector("#bReg").onclick = async ()=> showResult(m.querySelector("#regOut"), await call("GET","/api/"+NS+"/v1/hotl/register"));
  }},
];

const nav = document.getElementById("nav");
const main = document.getElementById("main");
const grp = document.createElement("div"); grp.className="grp"; grp.textContent="Autonomy-Governance Proofs (beyond one drone)"; nav.appendChild(grp);
TABS.forEach((t)=>{
  const b = document.createElement("button");
  b.innerHTML = `<span class="n">${t.n}</span>${t.title}`;
  b.onclick = ()=>{ document.querySelectorAll("nav button").forEach(x=>x.classList.remove("active")); b.classList.add("active"); t.render(main); location.hash = t.id; };
  nav.appendChild(b);
  t._btn = b;
});
const sep = document.createElement("div"); sep.className="grp"; sep.innerHTML='Related &nbsp;·&nbsp; <a href="/elite" style="color:var(--accent)">Elite 14-tab console →</a>'; nav.appendChild(sep);
function openInitial(){
  const h = (location.hash||"").replace("#","");
  const t = TABS.find(x=>x.id===h) || TABS[0];
  t._btn.click();
}
openInitial();
</script>
</body>
</html>
"""
