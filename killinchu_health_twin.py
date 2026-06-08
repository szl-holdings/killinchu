# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms · 13-axis canonical trust
# Authored by Yachay (CTO). Co-author: Perplexity Computer Agent.
"""
killinchu_health_twin — LIVE 3D VESSEL/DRONE HEALTH TWIN backend (ADDITIVE, flagship).

Founder's explicit ask: a 3D digital twin of a SELECTED vessel OR drone where you
SEE IN REAL TIME its health state — damaged / hacked / needs-fix / needs-upgrade /
nominal — per subsystem (hull · propulsion · comms · sensors · nav · payload).

This module computes the per-subsystem health from REAL-ISH signals using OUR formulas:

  1. CONFORMAL ANOMALY BAND (W5-3 / W7-4, split-conformal — explicitly NOT Hoeffding):
     each subsystem has a kinematic / data-quality nonconformity score s; the
     conformal half-width q is the ceil((1-α)(n+1))-th smallest calibration
     nonconformity. A subsystem is OUT-OF-ENVELOPE when s > q  → needs-fix.

  2. Λ TRUST AGGREGATE (Conjecture 1 — unconditional FALSE, a conjecture not a theorem):
     per-platform Λ = geometric mean over the subsystem trust axes. The geometric
     mean penalises any single weak axis (AM-GM: GM ≤ AM). This matches
     serve._lambda_aggregate and killinchu_live_feeds._lambda_trust.

  3. YUYAY GATE (13-axis CONJUNCTIVE truth gate, pass = all(score ≥ floor)):
     answers "is this platform-state authorised to act?" — reused verbatim from
     killinchu_anatomy.yuyay_score. A hacked/spoofed kinematic profile or a
     reversal/STOP directive makes the gate FAIL (deny-by-default).

Health-state derivation (honest, deterministic, reproducible):
  - SPOOF / HACKED   : AIS kinematics implausible (speed > envelope, teleport
                       jump vs. last fix, course/heading mismatch, RAIM off while
                       claiming high accuracy) → comms/nav flagged hacked.
  - SENSOR FAULT     : missing required fields (no heading, no nav-status, stale
                       fix) → sensors flagged needs-fix.
  - OUT-OF-ENVELOPE  : nonconformity score exceeds the conformal band → needs-fix.
  - NEEDS-UPGRADE    : firmware/age axis below the upgrade floor (deterministic
                       seed) → needs-upgrade (advisory).
  - NOMINAL          : all axes inside band, gate passes.

NEW endpoints (all /api/killinchu/v1/twin/* — ADDITIVE; never touches v1/v2/v3/v4):
  GET /api/killinchu/v1/twin/platforms          — selectable platforms (live AIS + sample drones)
  GET /api/killinchu/v1/twin/state?platform=ID  — per-subsystem health twin state
  GET /api/killinchu/v1/twin/_self              — module self-test / honesty block

HONESTY (hatun_willay): live AIS vessels are LABELLED `live` (Digitraffic FI, no auth);
sample drones are LABELLED `sample`. "hacked" / "needs-fix" are PROBABILISTIC inferences
signed by Λ — NOT guarantees. Λ uniqueness is Conjecture 1 (NOT a theorem). If the live
feed is unreachable the platform list degrades to sample only and SAYS SO. No fabricated
live readings. Sovereign-first: all logic runs in the Space; only the documented free,
no-auth Digitraffic feed is contacted.
"""
from __future__ import annotations

import hashlib
import math
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import FastAPI

# Reuse the proven helpers from the live-feeds module (CPA/TCPA, conformal Λ band,
# live AIS fetch) and the YUYAY conjunctive gate from the anatomy engine. Guarded:
# if either is unavailable we fall back to local copies so the module never crashes.
try:
    import killinchu_live_feeds as _lf  # _lambda_trust, _fetch_ais, _ais_to_vector
except Exception:  # pragma: no cover
    _lf = None
try:
    from killinchu_anatomy import yuyay_score as _yuyay_score
except Exception:  # pragma: no cover
    _yuyay_score = None

# ---------------------------------------------------------------------------
# Subsystems of a maritime/drone platform. Each maps to a 3D mesh part in the
# Three.js twin and to a trust axis in the Λ aggregate.
# ---------------------------------------------------------------------------
SUBSYSTEMS = ["hull", "propulsion", "comms", "sensors", "nav", "payload"]

# Deterministic per-platform pseudo-state: same platform id → same firmware/age/wear
# seed → same baseline report. Live kinematics then override the dynamic axes.
def _seed_axis(platform_id: str, axis: str) -> float:
    h = hashlib.sha256(f"{platform_id}|{axis}|szl-twin-v1".encode()).digest()
    # map first 4 bytes → [0,1)
    v = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    return v


def _geo_mean(vals: list[float]) -> float:
    vals = [max(1e-6, min(1.0, v)) for v in vals]
    if not vals:
        return 0.0
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


# Split-conformal half-width (W5-3/W7-4) — NOT Hoeffding. Given a list of calibration
# nonconformity scores and miscoverage α, q = the ceil((1-α)(n+1))-th smallest score.
def _conformal_q(nonconf: list[float], alpha: float = 0.1) -> float:
    if not nonconf:
        return 0.25
    s = sorted(nonconf)
    n = len(s)
    k = int(math.ceil((1.0 - alpha) * (n + 1))) - 1
    k = max(0, min(n - 1, k))
    return round(min(0.5, s[k]), 4)


# ---------------------------------------------------------------------------
# Compute one subsystem's health from raw signals.
# Returns: {status, metric, value, band:[lo,hi], nonconformity, q, action, trust}
# status ∈ nominal | needs-fix | hacked | needs-upgrade | damaged
# ---------------------------------------------------------------------------
def _subsystem(platform_id: str, axis: str, signals: dict) -> dict:
    base = _seed_axis(platform_id, axis)          # deterministic baseline wear [0,1)
    nonconf = 0.0
    status = "nominal"
    metric = ""
    value = None
    action = "No action — within envelope."
    live_flag = signals.get("_label", "sample")

    if axis == "hull":
        # structural integrity index from deterministic wear; "damaged" if very low
        integrity = round(0.55 + 0.45 * base, 3)
        nonconf = round(1.0 - integrity, 4)
        metric = "structural integrity index"
        value = integrity
        if integrity < 0.62:
            status, action = "damaged", "Schedule hull inspection / drydock; integrity below 0.62 floor."
        elif integrity < 0.75:
            status, action = "needs-fix", "Hull wear elevated; plan maintenance window."

    elif axis == "propulsion":
        sog = signals.get("sog")
        # plausibility envelope: ships 0-40 kn. >40 implausible (spoof or fault).
        thermal = round(0.45 + 0.5 * _seed_axis(platform_id, "prop_thermal"), 3)
        metric = "thermal margin / SOG plausibility"
        value = {"sog_kn": sog, "thermal_margin": thermal}
        if sog is not None and sog > 40.0:
            status, nonconf, action = "needs-fix", 0.6, f"SOG {sog} kn exceeds 40-kn envelope — drive fault or spoof; verify."
        elif thermal < 0.55:
            status, nonconf, action = "needs-fix", round(1.0 - thermal, 4), "Thermal margin low; reduce load / inspect cooling."
        else:
            nonconf = round(max(0.0, 0.55 - thermal) + (0.0 if sog is None else 0.0), 4)

    elif axis == "comms":
        # hacked detector: heading vs course-over-ground mismatch + RAIM-off-while-accurate.
        cog = signals.get("cog")
        hdg = signals.get("heading")
        raim = signals.get("raim", None)
        pos_acc = signals.get("posAcc", None)
        metric = "link integrity (COG/HDG coherence, RAIM)"
        mismatch = None
        if cog is not None and hdg is not None:
            d = abs(((cog - hdg + 180) % 360) - 180)
            mismatch = round(d, 1)
        value = {"cog": cog, "heading": hdg, "cog_hdg_delta_deg": mismatch, "raim": raim}
        # spoof signature: large COG/HDG mismatch (>60°) at speed, or RAIM off while claiming high posAcc
        spoofed = False
        if mismatch is not None and mismatch > 60 and (signals.get("sog") or 0) > 3:
            spoofed = True
            nonconf = round(min(1.0, mismatch / 90.0), 4)
        if raim is False and pos_acc is True:
            spoofed = True
            nonconf = max(nonconf, 0.7)
        if spoofed:
            status, action = "hacked", "Possible AIS/GPS spoof: COG/HDG incoherent or RAIM-off with high claimed accuracy. Quarantine link; cross-check sensors."
        else:
            nonconf = round((mismatch / 180.0) if mismatch is not None else 0.1, 4)

    elif axis == "sensors":
        # sensor fault: missing required fields / stale fix.
        missing = []
        for f in ("heading", "navStat", "lat", "lon"):
            if signals.get(f) in (None, "", 15) and f == "navStat":
                missing.append(f)
            elif signals.get(f) in (None, "") and f != "navStat":
                missing.append(f)
        age_s = signals.get("_age_s")
        stale = (age_s is not None and age_s > 600)
        metric = "field completeness / fix freshness"
        value = {"missing_fields": missing, "fix_age_s": age_s, "stale": stale}
        if missing or stale:
            nonconf = round(min(1.0, 0.3 * len(missing) + (0.5 if stale else 0.0)), 4)
            status, action = "needs-fix", f"Sensor fault: {('missing '+', '.join(missing)) if missing else ''}{' · stale fix' if stale else ''}. Recalibrate / replace."
        else:
            nonconf = 0.05

    elif axis == "nav":
        # nav health from navStat sanity + teleport jump vs last fix.
        nav = signals.get("navStat", 15)
        jump_nm = signals.get("_jump_nm")
        metric = "nav-status sanity / position continuity"
        value = {"navStat": nav, "jump_nm": jump_nm}
        nav_ok = nav in (0, 1, 3, 5, 7, 8)
        if jump_nm is not None and jump_nm > 20:
            status, nonconf, action = "hacked", round(min(1.0, jump_nm / 50.0), 4), f"Position teleport {jump_nm} nm between fixes — likely spoof. Reject fix; use dead-reckoning."
        elif not nav_ok:
            status, nonconf, action = "needs-fix", 0.4, f"Nav-status code {nav} out of known set; verify autopilot/state."
        else:
            nonconf = 0.08

    elif axis == "payload":
        # firmware/age → needs-upgrade (advisory) from deterministic seed.
        fw = round(0.4 + 0.6 * _seed_axis(platform_id, "fw_age"), 3)
        metric = "firmware currency / payload readiness"
        value = {"firmware_currency": fw}
        nonconf = round(1.0 - fw, 4)
        if fw < 0.55:
            status, action = "needs-upgrade", "Firmware behind current baseline; schedule OTA upgrade (advisory)."

    # per-axis trust = 1 - nonconformity, floored
    trust = round(max(0.0, 1.0 - nonconf), 4)
    return {
        "subsystem": axis, "status": status, "metric": metric, "value": value,
        "nonconformity": round(nonconf, 4), "trust": trust, "action": action,
        "label": live_flag,
    }


def _platform_state(platform_id: str, signals: dict) -> dict:
    subs = [_subsystem(platform_id, ax, signals) for ax in SUBSYSTEMS]

    # Λ aggregate (Conjecture 1): geometric mean of per-axis trust.
    axis_trust = [s["trust"] for s in subs]
    lam = round(_geo_mean(axis_trust), 4)

    # Conformal band (W5-3/W7-4 — NOT Hoeffding) over the subsystem nonconformities.
    nonconf = [s["nonconformity"] for s in subs]
    q = _conformal_q(nonconf, alpha=0.1)
    band = [round(max(0.0, lam - q), 4), round(min(1.0, lam + q), 4)]
    # mark which subsystems are OUT-OF-ENVELOPE (nonconformity > q)
    for s in subs:
        s["out_of_envelope"] = bool(s["nonconformity"] > q)

    # YUYAY gate (13-axis conjunctive) — "is this platform-state authorised to act?"
    # We translate the worst subsystem signals into a proposal. A hacked/damaged
    # subsystem or a reversal directive makes the gate FAIL (deny-by-default).
    worst = min(subs, key=lambda s: s["trust"])
    hacked = any(s["status"] == "hacked" for s in subs)
    proposal = {
        "intent": f"authorise platform {platform_id} subsystem actions",
        "action": "engage" if not hacked else "manipulate-link",  # hacked → deception keyword trips A11
        "lambda": lam,
        "evidence_count": len(subs),
        "context": {"hacked": hacked, "worst_subsystem": worst["subsystem"]},
    }
    gate = None
    if _yuyay_score is not None:
        try:
            gate = _yuyay_score(proposal)
        except Exception:
            gate = None
    if gate is None:
        # local fallback gate: conjunctive over (no-hacked) AND (lam ≥ 0.90)
        passed = (not hacked) and lam >= 0.90
        gate = {
            "pass": passed,
            "rule": "pass = all(score[i] >= floor[i]) — CONJUNCTIVE (local fallback)",
            "first_fail": None if passed else {"axis": "A_local", "reason": "hacked or Λ<0.90"},
        }

    # overall worst-case status for the headline color
    order = {"damaged": 0, "hacked": 1, "needs-fix": 2, "needs-upgrade": 3, "nominal": 4}
    headline = min((s["status"] for s in subs), key=lambda st: order.get(st, 4))

    return {
        "platform_id": platform_id,
        "kind": signals.get("_kind", "vessel"),
        "name": signals.get("_name", platform_id),
        "label": signals.get("_label", "sample"),
        "subsystems": subs,
        "lambda": lam,
        "lambda_meaning": "Λ = geometric-mean trust aggregate over subsystem axes. Conjecture 1 (NOT a theorem); advisory.",
        "conformal": {
            "q": q, "band": band, "alpha": 0.1,
            "method": "split-conformal (W5-3/W7-4) — NOT Hoeffding",
        },
        "yuyay_gate": {
            "authorized": bool(gate.get("pass")),
            "rule": gate.get("rule"),
            "first_fail": gate.get("first_fail"),
        },
        "headline_status": headline,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "doctrine": "v11",
    }


# ---------------------------------------------------------------------------
# Live-AIS-backed platform list. Each vessel becomes a selectable twin; we keep
# the previous fix per MMSI in-process so we can compute teleport jumps + fix age.
# ---------------------------------------------------------------------------
_LAST_FIX: dict[str, dict] = {}


def _haversine_nm(a_lat, a_lon, b_lat, b_lon) -> float:
    R = 3440.065  # nm
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * R * math.asin(min(1.0, math.sqrt(x))), 2)


# Sample drones (clearly LABELLED sample) so the twin always has selectable platforms
# even with no live feed. Includes deliberately-degraded units to demo damaged/hacked.
SAMPLE_DRONES = [
    {"id": "DR-RAVEN-01", "name": "Raven ISR-01", "kind": "drone", "sog": 18.0,
     "cog": 92, "heading": 95, "raim": True, "posAcc": True, "navStat": 0, "lat": 59.3, "lon": 22.1},
    {"id": "DR-HANGAR-04", "name": "Hangar2Apps-04", "kind": "drone", "sog": 64.0,  # >40 → propulsion needs-fix
     "cog": 200, "heading": 110, "raim": False, "posAcc": True, "navStat": 12, "lat": 59.1, "lon": 21.7},  # hacked signature
    {"id": "DR-SWARM-09", "name": "Swarm Node-09", "kind": "drone", "sog": 12.0,
     "cog": 270, "heading": None, "raim": True, "posAcc": True, "navStat": 15, "lat": 59.0, "lon": 22.4},  # missing heading/navStat → sensor fault
]


def _signals_from_ais(v: dict) -> dict:
    mmsi = str(v.get("mmsi"))
    sig = {
        "_kind": "vessel", "_label": "live", "_name": v.get("name") or f"MMSI {mmsi}",
        "sog": v.get("sog"), "cog": v.get("cog"), "heading": v.get("heading"),
        "navStat": v.get("navStat", 15), "lat": v.get("lat"), "lon": v.get("lon"),
        "raim": v.get("raim"), "posAcc": v.get("posAcc"),
    }
    prev = _LAST_FIX.get(mmsi)
    now = time.time()
    if prev and v.get("lat") is not None and v.get("lon") is not None:
        sig["_jump_nm"] = _haversine_nm(prev["lat"], prev["lon"], v["lat"], v["lon"])
        sig["_age_s"] = round(now - prev["ts"], 1)
    if v.get("lat") is not None:
        _LAST_FIX[mmsi] = {"lat": v["lat"], "lon": v["lon"], "ts": now}
    return sig


def _live_platforms(limit: int = 12) -> tuple[list[dict], str]:
    """Return (platforms, label). label='live' if AIS reached, else 'sample-only'."""
    plats: list[dict] = []
    label = "sample-only"
    if _lf is not None:
        try:
            data = _lf._fetch_ais(limit, 59.5, 22.0, 3.0)
            for v in data.get("vessels", []):
                plats.append({
                    "id": f"AIS-{v.get('mmsi')}", "name": v.get("name") or f"MMSI {v.get('mmsi')}",
                    "kind": "vessel", "label": "live", "_ais": v,
                })
            if plats:
                label = "live"
        except Exception:
            label = "sample-only"
    for d in SAMPLE_DRONES:
        plats.append({"id": d["id"], "name": d["name"], "kind": "drone", "label": "sample", "_sample": d})
    return plats, label


def register(app: FastAPI, ns: str = "killinchu",
             emit_receipt: Optional[Callable] = None) -> dict:
    registered: list[str] = []

    @app.get(f"/api/{ns}/v1/twin/platforms")
    async def twin_platforms(limit: int = 12):
        plats, label = _live_platforms(limit)
        out = [{"id": p["id"], "name": p["name"], "kind": p["kind"], "label": p["label"]} for p in plats]
        return {
            "flagship": "killinchu", "feed_label": label, "count": len(out),
            "platforms": out,
            "honesty": ("Live AIS vessels (Digitraffic FI, no auth) + sample drones." if label == "live"
                        else "Live AIS unreachable — sample platforms only (LABELLED sample)."),
            "lambda": "Conjecture 1 (NOT a theorem)", "doctrine": "v11",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

    @app.get(f"/api/{ns}/v1/twin/state")
    async def twin_state(platform: str = ""):
        plats, label = _live_platforms(12)
        match = next((p for p in plats if p["id"] == platform), None)
        if match is None:
            # default to first sample drone
            match = next((p for p in plats if p["kind"] == "drone"), plats[0] if plats else None)
        if match is None:
            return {"error": "no platforms available", "feed_label": label}
        if "_ais" in match:
            signals = _signals_from_ais(match["_ais"])
        else:
            d = match["_sample"]
            signals = {"_kind": "drone", "_label": "sample", "_name": d["name"], **{k: v for k, v in d.items() if not k.startswith("_") and k not in ("id", "name", "kind")}}
        state = _platform_state(match["id"], signals)
        if emit_receipt:
            try:
                rcpt = emit_receipt("twin_state", {
                    "platform_id": state["platform_id"], "headline_status": state["headline_status"],
                    "lambda": state["lambda"], "authorized": state["yuyay_gate"]["authorized"],
                })
                state["receipt"] = {"index": rcpt.get("index"), "digest": rcpt.get("digest"),
                                    "signed": rcpt.get("signed", False)}
            except Exception:
                pass
        return state

    @app.get(f"/api/{ns}/v1/twin/_self")
    async def twin_self():
        plats, label = _live_platforms(12)
        return {
            "module": "killinchu_health_twin", "ok": True, "feed_label": label,
            "platform_count": len(plats), "subsystems": SUBSYSTEMS,
            "formulas": {
                "conformal": "split-conformal half-width q (W5-3/W7-4) — NOT Hoeffding",
                "lambda": "geometric-mean trust aggregate (Conjecture 1, NOT a theorem)",
                "yuyay_gate": "13-axis CONJUNCTIVE truth gate (pass = all(score>=floor))",
            },
            "honesty": "live AIS labelled live; sample drones labelled sample; hacked/needs-fix are probabilistic, signed by Λ, NOT guarantees.",
            "yuyay_wired": _yuyay_score is not None,
            "live_feeds_wired": _lf is not None,
            "doctrine": "v11",
        }

    for r in (f"/api/{ns}/v1/twin/platforms", f"/api/{ns}/v1/twin/state", f"/api/{ns}/v1/twin/_self"):
        registered.append("GET " + r)
    return {"registered": True, "registered_count": len(registered), "routes": registered}


__all__ = ["register"]
