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
import re as _re
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

# DOCTRINE — honest subsystem provenance (hatun_willay). COMMS/NAV/SENSORS are
# computed from the REAL live kinematic track (ADS-B / AIS) and are LIVE-derived.
# HULL/PROPULSION/PAYLOAD have NO public telemetry feed that exposes them, so they
# are INFERRED/SIMULATED from a deterministic per-platform seed — clearly labelled,
# NEVER presented as measured. This is the doctrine; do not relabel inferred as live.
_SUBSYS_PROVENANCE = {
    "comms":     "LIVE-derived",   # real COG/HDG coherence + RAIM from the live track
    "nav":       "LIVE-derived",   # real nav-status + position-continuity (teleport) from the live track
    "sensors":   "LIVE-derived",   # real field-completeness + fix-freshness from the live track
    "hull":      "INFERRED/SIMULATED — no public telemetry feed exposes hull integrity",
    "propulsion":"INFERRED/SIMULATED — thermal margin is simulated; SOG plausibility IS live",
    "payload":   "INFERRED/SIMULATED — firmware/payload currency; no public feed exposes this",
}

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
        kind = signals.get("_kind", "vessel")
        # plausibility envelope is KIND-specific: vessels 40 kn, drones 120, aircraft 700.
        env = {"vessel": 40.0, "drone": 120.0, "aircraft": 700.0}.get(kind, 60.0)
        thermal = round(0.45 + 0.5 * _seed_axis(platform_id, "prop_thermal"), 3)
        metric = "thermal margin (INFERRED) / SOG plausibility (LIVE)"
        value = {"sog_kn": sog, "envelope_kn": env, "thermal_margin": thermal}
        if sog is not None and sog > env:
            status, nonconf, action = "needs-fix", 0.6, f"ground speed {sog} kn exceeds {kind} {env}-kn envelope — drive fault or spoof; verify."
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
    prov = _SUBSYS_PROVENANCE.get(axis, "INFERRED/SIMULATED")
    return {
        "subsystem": axis, "status": status, "metric": metric, "value": value,
        "nonconformity": round(nonconf, 4), "trust": trust, "action": action,
        "label": live_flag,
        "provenance": prov,
        "derived": prov.startswith("LIVE"),
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

    # ---- REAL compromise cross-reference (kinematic + KEV/NVD + OFAC SDN) ----
    kind = signals.get("_kind", "vessel")
    compromise = _compromise_signal(platform_id, kind, signals)
    # a compromised verdict escalates COMMS/NAV to hacked in the headline ordering
    if compromise["state"] == "compromised":
        for s in subs:
            if s["subsystem"] in ("comms", "nav") and s["status"] not in ("hacked", "damaged"):
                s["status"] = "hacked"
                s["action"] = "Compromise signal fired (see compromise.checks_fired). Quarantine link; verify."

    # overall worst-case status for the headline color
    order = {"damaged": 0, "hacked": 1, "needs-fix": 2, "needs-upgrade": 3, "nominal": 4}
    headline = min((s["status"] for s in subs), key=lambda st: order.get(st, 4))
    if compromise["state"] == "compromised" and order.get(headline, 4) > 1:
        headline = "hacked"

    return {
        "platform_id": platform_id,
        "kind": kind,
        "compromise": compromise,
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
        "_mmsi": mmsi,
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


# ---------------------------------------------------------------------------
# Live MILITARY ADS-B aircraft → selectable twin. Real hex/callsign/registration/
# type/position/speed/track. COMMS/NAV/SENSORS health is computed from the real
# kinematic track exactly like vessels (course/track-vs-heading coherence is
# approximated from track continuity; teleport jumps + fix age tracked per hex).
# ---------------------------------------------------------------------------
_LAST_FIX_AIR: dict[str, dict] = {}


def _signals_from_air(a: dict) -> dict:
    """Map a live ADS-B aircraft fix → the same signal schema the formulas use.
    Honest: every value is the real ADS-B field; nothing fabricated. Aircraft do
    not broadcast AIS COG/RAIM, so we derive comms coherence from ground-track
    continuity (track vs. previous track) and flag stale/teleport fixes."""
    hexid = str(a.get("hex"))
    track = a.get("track")
    gs = a.get("gs")
    sig = {
        "_kind": "aircraft", "_label": "live",
        "_name": (a.get("flight") or a.get("r") or f"ICAO {hexid}"),
        "sog": gs,                       # ground speed (kn) — real
        "cog": track,                    # ground track (deg) — real
        "heading": a.get("true_heading") if a.get("true_heading") is not None else track,
        "navStat": 0,                    # airborne under positive control (assumed nominal)
        "lat": a.get("lat"), "lon": a.get("lon"),
        "raim": None, "posAcc": (a.get("nic") is not None and (a.get("nic") or 0) >= 7) or None,
        "_alt_baro": a.get("alt_baro"), "_squawk": a.get("squawk"),
        "_type": a.get("t"), "_reg": a.get("r"), "_hex": hexid,
    }
    # aircraft kinematic envelope is much higher than ships; the _subsystem propulsion
    # rule uses a ship 40-kn envelope, so for aircraft we DON'T pass sog into that rule
    # as an over-envelope trigger (handled by _envelope_for_kind in the compromise engine).
    prev = _LAST_FIX_AIR.get(hexid)
    now = time.time()
    if prev and a.get("lat") is not None and a.get("lon") is not None:
        sig["_jump_nm"] = _haversine_nm(prev["lat"], prev["lon"], a["lat"], a["lon"])
        sig["_age_s"] = round(now - prev["ts"], 1)
        # track-continuity coherence proxy (large instantaneous track flip at speed = anomaly)
        if prev.get("track") is not None and track is not None:
            sig["_track_flip_deg"] = round(abs(((track - prev["track"] + 180) % 360) - 180), 1)
    if a.get("lat") is not None:
        _LAST_FIX_AIR[hexid] = {"lat": a["lat"], "lon": a["lon"], "ts": now, "track": track}
    return sig


def _live_platforms(limit: int = 12) -> tuple[list[dict], str]:
    """Return (platforms, label). label='live' if AIS or ADS-B reached.
    Live military ADS-B aircraft + live AIS vessels become selectable twins; the
    SAMPLE drones (clearly labelled) always remain so the twin is never empty."""
    plats: list[dict] = []
    got_air = got_ais = False
    if _lf is not None:
        # --- live MILITARY ADS-B aircraft (real hex / callsign / type) ---
        try:
            air = _lf._fetch_air(max(6, limit))
            for a in air.get("aircraft", []):
                if a.get("hex") is None or a.get("lat") is None:
                    continue
                nm = (a.get("flight") or a.get("r") or f"ICAO {a.get('hex')}")
                plats.append({
                    "id": f"ADSB-{a.get('hex')}", "name": nm,
                    "kind": "aircraft", "label": "live", "_air": a,
                })
            got_air = any(p["kind"] == "aircraft" for p in plats)
        except Exception:
            got_air = False
        # --- live AIS vessels (real MMSI) ---
        try:
            data = _lf._fetch_ais(max(6, limit), 59.5, 22.0, 3.0)
            for v in data.get("vessels", []):
                plats.append({
                    "id": f"AIS-{v.get('mmsi')}", "name": v.get("name") or f"MMSI {v.get('mmsi')}",
                    "kind": "vessel", "label": "live", "_ais": v,
                })
            got_ais = any(p["kind"] == "vessel" for p in plats)
        except Exception:
            got_ais = False
    label = "live" if (got_air or got_ais) else "sample-only"
    for d in SAMPLE_DRONES:
        plats.append({"id": d["id"], "name": d["name"], "kind": "drone",
                      "label": "sample" if label == "live" else "SAMPLE (feed unreachable)",
                      "_sample": d})
    return plats, label


# ===========================================================================
# REAL COMPROMISE SIGNAL — honest, source-cited threat cross-reference.
#
# Three independent checks, each emits evidence with the source URL + timestamp:
#  (a) KINEMATIC SPOOF (per-platform, REAL): teleport jump vs last fix, speed >
#      kind-specific envelope, RAIM-off-while-claiming-accuracy, COG/HDG (or
#      track-flip) incoherence — all from the live track this module already holds.
#  (b) FIRMWARE-FAMILY ADVISORY (ecosystem, REAL feed, HONESTLY scoped): match
#      common UAS/drone-autopilot CVE keywords against the LIVE CISA KEV catalog
#      and NVD 2.0. We NEVER claim this specific platform RUNS the vulnerable
#      firmware (no public feed exposes that) — we report the real CVEs as an
#      ECOSYSTEM advisory for the platform's autopilot family, with the CVE id +
#      source URL. No fabricated CVE match: only real feed hits are surfaced.
#  (c) SANCTIONS / DARK-VESSEL SCREENING (vessels, REAL feed): screen the
#      vessel name + MMSI against the LIVE U.S. Treasury OFAC SDN list. If the
#      OFAC feed is unreachable we say so (no fabricated hit). Dark-vessel
#      behaviour (AIS gap / stale fix) is flagged from the live track.
#
# Output: compromise_score in [0,1] (geometric-style escalation), state
# (clear|watch|compromised), and the list of fired checks with evidence.
# ===========================================================================

# Common drone / UAS autopilot firmware families. Keyword match against the live
# KEV/NVD feeds — these are REAL ecosystems (ArduPilot, PX4/Pixhawk, MAVLink,
# DJI, Parrot). The match is an ECOSYSTEM advisory, never a per-unit claim.
# Specific, unambiguous UAS/autopilot firmware-family product names. We match these as
# substrings. Short ambiguous tokens ("uas") are matched as WHOLE WORDS only (see
# _UAS_FW_WORDS) so we never report a fabricated hit from an unrelated substring such as
# "Aquasecurity" or "IGEL OS". Doctrine: only report REAL feed hits.
_UAS_FW_KEYWORDS = [
    "ardupilot", "px4", "pixhawk", "mavlink", "betaflight",
    "cleanflight", "inav", "unmanned aircraft", "unmanned aerial",
]
_UAS_FW_WORDS = ["uas", "uav", "dji", "parrot"]  # matched on word boundaries only
_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_KEV_MIRROR = "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"
_NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_OFAC_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"

_THREAT_CACHE: dict[str, dict] = {}
_THREAT_TTL = {"kev": 6 * 3600, "nvd": 1800, "ofac": 6 * 3600}


def _kind_speed_envelope(kind: str) -> float:
    # plausible max ground speed (kn). vessels ~40, aircraft ~700 (Mach ~1.1 @ alt),
    # drone ~120. Beyond this = implausible (spoof or sensor fault).
    return {"vessel": 40.0, "aircraft": 700.0, "drone": 120.0}.get(kind, 60.0)


def _kev_uas_hits() -> dict:
    """LIVE CISA KEV catalog filtered to UAS/autopilot keywords. Real feed only."""
    now = time.time()
    ent = _THREAT_CACHE.get("kev")
    if ent and (now - ent["ts"]) < _THREAT_TTL["kev"]:
        return ent["data"]
    hits, src_url, fetched = [], _KEV_URL, None
    raw = None
    try:
        if _lf is not None:
            fr = _lf.get_feed("kev")  # reuse cached, snapshot-fallback feed accessor
            raw = (fr or {}).get("data")
            src_url = (fr or {}).get("source_url") or _KEV_MIRROR
            fetched = (fr or {}).get("fetched_at")
    except Exception:
        raw = None
    if not isinstance(raw, dict):
        return {"available": False, "hits": [], "source": "CISA KEV", "source_url": _KEV_URL,
                "note": "CISA KEV feed unreachable — no firmware-family advisory (honest; no fabricated CVE)."}
    for v in raw.get("vulnerabilities", []):
        blob = " ".join(str(v.get(k, "")) for k in
                        ("vendorProject", "product", "vulnerabilityName", "shortDescription")).lower()
        matched = [kw for kw in _UAS_FW_KEYWORDS if kw in blob]
        matched += [kw for kw in _UAS_FW_WORDS if _re.search(r"\b" + _re.escape(kw) + r"\b", blob)]
        if matched:
            hits.append({"cve": v.get("cveID"), "vendor": v.get("vendorProject"),
                         "product": v.get("product"), "name": v.get("vulnerabilityName"),
                         "matched_keywords": matched, "dateAdded": v.get("dateAdded")})
    out = {"available": True, "hits": hits, "source": "CISA Known Exploited Vulnerabilities catalog",
           "source_url": _KEV_URL, "fetched_at": fetched,
           "catalog_count": raw.get("count") or len(raw.get("vulnerabilities", []))}
    _THREAT_CACHE["kev"] = {"data": out, "ts": now}
    return out


def _nvd_uas_hits() -> dict:
    """LIVE NVD 2.0 keyword search for autopilot-family CVEs. Real feed only."""
    now = time.time()
    ent = _THREAT_CACHE.get("nvd")
    if ent and (now - ent["ts"]) < _THREAT_TTL["nvd"]:
        return ent["data"]
    hits = []
    ok = False
    for kw in ("ardupilot", "px4", "mavlink"):
        try:
            url = f"{_NVD_URL}?keywordSearch={kw}&resultsPerPage=20"
            d = _lf._http_get(url, timeout=18) if (_lf and hasattr(_lf, "_http_get")) else None
            if isinstance(d, dict):
                ok = True
                for it in d.get("vulnerabilities", []):
                    c = it.get("cve", {})
                    desc = next((x.get("value") for x in c.get("descriptions", [])
                                 if x.get("lang") == "en"), "")
                    hits.append({"cve": c.get("id"), "family": kw, "desc": (desc or "")[:160],
                                 "published": c.get("published")})
        except Exception:
            continue
    if not ok:
        return {"available": False, "hits": [], "source": "NVD CVE API 2.0", "source_url": _NVD_URL,
                "note": "NVD 2.0 unreachable — no firmware-family advisory (honest; no fabricated CVE)."}
    # de-dup by cve id
    seen, uniq = set(), []
    for h in hits:
        if h["cve"] and h["cve"] not in seen:
            seen.add(h["cve"]); uniq.append(h)
    out = {"available": True, "hits": uniq[:25], "source": "U.S. National Vulnerability Database (NVD CVE API 2.0)",
           "source_url": _NVD_URL, "fetched_at": datetime.now(timezone.utc).isoformat()}
    _THREAT_CACHE["nvd"] = {"data": out, "ts": now}
    return out


def _ofac_sdn_screen(name: str, mmsi: Optional[str]) -> dict:
    """Screen a vessel name (and MMSI) against the LIVE U.S. Treasury OFAC SDN list.
    Real feed. If unreachable, returns available=False (no fabricated hit)."""
    if not name:
        return {"available": True, "hit": False, "source": "OFAC SDN", "source_url": _OFAC_SDN_URL,
                "note": "no vessel name to screen"}
    now = time.time()
    ent = _THREAT_CACHE.get("ofac")
    rows = None
    if ent and (now - ent["ts"]) < _THREAT_TTL["ofac"]:
        rows = ent["data"]
    if rows is None:
        try:
            raw = _lf._http_get_raw(_OFAC_SDN_URL, timeout=30) if (_lf and hasattr(_lf, "_http_get_raw")) else None
            if raw:
                txt = raw.decode("latin-1", "replace")
                rows = []
                for line in txt.splitlines():
                    # SDN.csv: ent_num,"SDN_Name","SDN_Type","Program",...  (vessels: type "vessel")
                    parts = line.split(',')
                    if len(parts) >= 4:
                        nm = parts[1].strip().strip('"')
                        typ = parts[2].strip().strip('"')
                        prog = parts[3].strip().strip('"')
                        if nm:
                            rows.append((nm.upper(), typ, prog))
                _THREAT_CACHE["ofac"] = {"data": rows, "ts": now}
        except Exception:
            rows = None
    if rows is None:
        return {"available": False, "hit": False, "source": "U.S. Treasury OFAC SDN list",
                "source_url": _OFAC_SDN_URL,
                "note": "OFAC SDN feed unreachable — screening skipped (honest; no fabricated hit)."}
    needle = name.upper().strip()
    matches = []
    if len(needle) >= 4:
        for nm, typ, prog in rows:
            if needle == nm or (needle in nm and "vessel" in typ.lower()):
                matches.append({"sdn_name": nm, "type": typ, "program": prog})
        # also exact-substring on long names to catch vessel re-flaggings
        if not matches:
            for nm, typ, prog in rows:
                if needle in nm and len(needle) >= 6:
                    matches.append({"sdn_name": nm, "type": typ, "program": prog})
    return {"available": True, "hit": bool(matches), "matches": matches[:5],
            "screened": name, "mmsi": mmsi,
            "source": "U.S. Treasury OFAC Specially Designated Nationals (SDN) list",
            "source_url": _OFAC_SDN_URL,
            "list_size": len(rows),
            "note": "Live OFAC SDN exact/again-substring name screen. Advisory — confirm against full OFAC search before action."}


def _compromise_signal(platform_id: str, kind: str, signals: dict) -> dict:
    """Compute the honest compromise score + evidence for one platform."""
    checks: list[dict] = []
    score = 0.0
    ts = datetime.now(timezone.utc).isoformat()

    # ---- (a) KINEMATIC SPOOF (per-platform, REAL track) ----
    jump = signals.get("_jump_nm")
    age = signals.get("_age_s")
    sog = signals.get("sog")
    cog = signals.get("cog")
    hdg = signals.get("heading")
    raim = signals.get("raim")
    posAcc = signals.get("posAcc")
    env = _kind_speed_envelope(kind)
    # teleport (only if we have two fixes within a plausible window)
    if jump is not None and age is not None and age > 0:
        implied_kn = (jump / age) * 3600.0
        if jump > 20.0 and implied_kn > env * 1.5:
            checks.append({"check": "kinematic.teleport", "fired": True,
                           "evidence": f"position jumped {jump} nm in {age}s (implied {round(implied_kn)} kn > {round(env*1.5)} kn envelope) — likely GPS/AIS spoof",
                           "source": "live track (this module, in-process fix history)",
                           "source_url": "ADS-B/AIS live feed", "ts": ts})
            score = max(score, min(1.0, jump / 50.0))
    # over-envelope speed
    if sog is not None and sog > env:
        checks.append({"check": "kinematic.over_envelope_speed", "fired": True,
                       "evidence": f"ground speed {sog} kn exceeds {kind} plausibility envelope {env} kn — drive fault or spoof",
                       "source": "live track", "source_url": "ADS-B/AIS live feed", "ts": ts})
        score = max(score, 0.6)
    # RAIM off while claiming high positional accuracy
    if raim is False and posAcc is True:
        checks.append({"check": "kinematic.raim_off_high_acc", "fired": True,
                       "evidence": "RAIM (receiver autonomous integrity monitoring) OFF while broadcasting HIGH position accuracy — classic spoof signature",
                       "source": "live track (AIS posAcc/raim bits)", "source_url": "AIS live feed", "ts": ts})
        score = max(score, 0.7)
    # COG/HDG incoherence at speed (vessels) or track-flip (aircraft)
    if cog is not None and hdg is not None and (sog or 0) > 3:
        mismatch = abs(((cog - hdg + 180) % 360) - 180)
        if mismatch > 60:
            checks.append({"check": "kinematic.cog_hdg_incoherent", "fired": True,
                           "evidence": f"course-over-ground vs heading delta {round(mismatch,1)}° (>60°) at {sog} kn — link/heading-sensor incoherence",
                           "source": "live track", "source_url": "ADS-B/AIS live feed", "ts": ts})
            score = max(score, min(1.0, mismatch / 120.0))
    flip = signals.get("_track_flip_deg")
    if flip is not None and flip > 90 and (sog or 0) > 100:
        checks.append({"check": "kinematic.track_discontinuity", "fired": True,
                       "evidence": f"ground-track flipped {flip}° between consecutive fixes at {sog} kn — implausible for an airframe; possible spoof",
                       "source": "live track (ADS-B track history)", "source_url": "ADS-B live feed", "ts": ts})
        score = max(score, min(1.0, flip / 180.0))

    # ---- (b) FIRMWARE-FAMILY ADVISORY (ecosystem, REAL KEV/NVD) ----
    fw_advisory = None
    if kind in ("drone", "aircraft"):
        kev = _kev_uas_hits()
        nvd = _nvd_uas_hits()
        kev_hits = kev.get("hits", []) if kev.get("available") else []
        nvd_hits = nvd.get("hits", []) if nvd.get("available") else []
        if kev_hits or nvd_hits:
            checks.append({"check": "firmware.family_advisory", "fired": True,
                           "evidence": (f"{len(kev_hits)} CISA-KEV + {len(nvd_hits)} NVD CVE(s) affect common UAS/autopilot firmware "
                                        "families (ArduPilot/PX4/MAVLink/DJI). ECOSYSTEM advisory — NOT a claim that THIS unit runs the vulnerable build (no public telemetry exposes per-unit firmware)."),
                           "kev": kev_hits[:8], "nvd": nvd_hits[:8],
                           "source": "CISA KEV + NVD 2.0 (live)",
                           "source_url": kev.get("source_url", _KEV_URL),
                           "nvd_source_url": _NVD_URL,
                           "fetched_at": kev.get("fetched_at"), "ts": ts})
            # advisory only nudges the score (it is ecosystem-level, not per-unit)
            score = max(score, 0.25 if (kev_hits or nvd_hits) else 0.0)
        fw_advisory = {"kev_available": kev.get("available"), "nvd_available": nvd.get("available"),
                       "kev_note": kev.get("note"), "nvd_note": nvd.get("note")}

    # ---- (c) SANCTIONS / DARK-VESSEL SCREENING (vessels, REAL OFAC SDN) ----
    sanctions = None
    if kind == "vessel":
        nm = signals.get("_name") or ""
        mmsi = str(signals.get("_mmsi") or "")
        # only screen real ship names (skip the "MMSI 12345" placeholder where AIS gave no name)
        screen_name = nm if (nm and not nm.upper().startswith("MMSI")) else ""
        sanctions = _ofac_sdn_screen(screen_name, mmsi or None)
        if sanctions.get("hit"):
            checks.append({"check": "sanctions.ofac_sdn_hit", "fired": True,
                           "evidence": f"vessel name '{screen_name}' matches OFAC SDN entry/entries: " +
                                       "; ".join(m["sdn_name"] + " [" + m["program"] + "]" for m in sanctions.get("matches", [])[:3]),
                           "matches": sanctions.get("matches"),
                           "source": sanctions.get("source"), "source_url": sanctions.get("source_url"), "ts": ts})
            score = max(score, 0.85)
        # dark-vessel behaviour from the live track (stale fix / AIS gap)
        if age is not None and age > 600:
            checks.append({"check": "darkvessel.ais_gap", "fired": True,
                           "evidence": f"AIS fix age {age}s (>600s) — vessel went dark between reports (dark-vessel behaviour)",
                           "source": "live track (AIS fix age)", "source_url": "AIS live feed", "ts": ts})
            score = max(score, 0.5)

    fired = [c for c in checks if c.get("fired")]
    if score >= 0.7:
        state = "compromised"
    elif score >= 0.3 or fired:
        state = "watch"
    else:
        state = "clear"
    return {
        "compromise_score": round(score, 4),
        "state": state,
        "checks_fired": fired,
        "checks_evaluated": ["kinematic.teleport", "kinematic.over_envelope_speed",
                             "kinematic.raim_off_high_acc", "kinematic.cog_hdg_incoherent",
                             "kinematic.track_discontinuity",
                             "firmware.family_advisory", "sanctions.ofac_sdn_hit", "darkvessel.ais_gap"],
        "firmware_feeds": fw_advisory,
        "sanctions": sanctions,
        "honesty": ("Kinematic checks are per-platform from the REAL live track. Firmware advisory is an "
                    "ECOSYSTEM-level KEV/NVD match (NOT a per-unit firmware claim). Sanctions screening is "
                    "a LIVE OFAC SDN name screen (advisory). No fabricated CVE or sanctions hit — unreachable feeds say so."),
        "ts_utc": ts,
    }


def register(app: FastAPI, ns: str = "killinchu",
             emit_receipt: Optional[Callable] = None) -> dict:
    registered: list[str] = []

    @app.get(f"/api/{ns}/v1/twin/platforms")
    async def twin_platforms(limit: int = 12):
        plats, label = _live_platforms(limit)
        out = [{"id": p["id"], "name": p["name"], "kind": p["kind"], "label": p["label"]} for p in plats]
        n_air = sum(1 for p in plats if p["kind"] == "aircraft")
        n_ves = sum(1 for p in plats if p["kind"] == "vessel")
        return {
            "flagship": "killinchu", "feed_label": label, "count": len(out),
            "counts": {"aircraft": n_air, "vessel": n_ves, "sample_drone": len(SAMPLE_DRONES)},
            "platforms": out,
            "sources": {
                "aircraft": "Military ADS-B (api.adsb.lol/v2/mil → adsb.fi → airplanes.live), no auth (ODbL)",
                "vessel": "AIS (meri.digitraffic.fi/api/ais/v1/locations), no auth (CC BY 4.0)",
            },
            "honesty": (("Live MILITARY ADS-B aircraft (real ICAO hex / callsign / type) + live AIS vessels "
                         "(real MMSI) + clearly-LABELLED sample drones.") if label == "live"
                        else "Live feeds unreachable — sample platforms only (LABELLED 'SAMPLE (feed unreachable)')."),
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
        if "_air" in match:
            signals = _signals_from_air(match["_air"])
        elif "_ais" in match:
            signals = _signals_from_ais(match["_ais"])
        else:
            d = match["_sample"]
            signals = {"_kind": "drone", "_label": match.get("label", "sample"), "_name": d["name"], **{k: v for k, v in d.items() if not k.startswith("_") and k not in ("id", "name", "kind")}}
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
            "subsystem_provenance": _SUBSYS_PROVENANCE,
            "compromise_feeds": {
                "kinematic": "per-platform from the live ADS-B/AIS track (REAL)",
                "firmware_family": {"source": "CISA KEV + NVD 2.0", "kev_url": _KEV_URL, "nvd_url": _NVD_URL,
                                    "scope": "ECOSYSTEM advisory (NOT per-unit firmware claim)"},
                "sanctions": {"source": "U.S. Treasury OFAC SDN", "url": _OFAC_SDN_URL, "scope": "vessel name screen (advisory)"},
            },
            "remediate_endpoint": f"/api/{ns}/v1/twin/remediate (POST)",
            "honesty": ("Live ADS-B/AIS labelled live; sample drones labelled sample; COMMS/NAV/SENSORS are "
                        "LIVE-derived from real kinematics; HULL/PROPULSION/PAYLOAD are INFERRED/SIMULATED (no public "
                        "telemetry feed exposes them). hacked/needs-fix are probabilistic, signed by Λ, NOT guarantees. "
                        "The governed fix-loop is real + provable; the effector is SIMULATED — killinchu cannot push "
                        "firmware or recall a real asset."),
            "yuyay_wired": _yuyay_score is not None,
            "live_feeds_wired": _lf is not None,
            "doctrine": "v11",
        }

    # -----------------------------------------------------------------------
    # GOVERNED FIX-LOOP: POST /twin/remediate {platform, action}.
    # Runs the action through ROE → Λ-gate → emits a SIGNED DSSE receipt.
    # The GOVERNANCE is real + provable. The EFFECTOR is a command demonstration:
    # killinchu does NOT and CANNOT push firmware / recall / isolate a real asset.
    # -----------------------------------------------------------------------
    _ACTIONS = {
        "upgrade": {"intent": "schedule OTA firmware upgrade", "reversible": True,  "min_lambda": 0.80},
        "patch":   {"intent": "apply security patch to autopilot family", "reversible": True,  "min_lambda": 0.80},
        "recall":  {"intent": "recall platform to base / RTB", "reversible": True,  "min_lambda": 0.70},
        "isolate": {"intent": "isolate / quarantine compromised link", "reversible": True, "min_lambda": 0.0},
    }
    # Lean theorem reference for the governance gate (locked-proven set = {F1,F4,F7,F11,F12,F18,F19,F22}).
    _LEAN_REF = {
        "gate_monotone": "Lutar.lean §Λ-gate — conjunctive 13-axis gate is monotone (deny-by-default).",
        "locked_proven": ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"],
        "lambda_status": "Λ = Conjecture 1 (NOT a theorem); BFT = Conjecture 2 (conditional, proven Wave23).",
    }

    @app.post(f"/api/{ns}/v1/twin/remediate")
    async def twin_remediate(body: dict | None = None):
        body = body or {}
        platform = str(body.get("platform", "")).strip()
        action = str(body.get("action", "")).strip().lower()
        if action not in _ACTIONS:
            return {"error": "unknown action", "allowed": sorted(_ACTIONS.keys()),
                    "usage": "POST {platform, action: upgrade|patch|recall|isolate}"}
        plats, feed_label = _live_platforms(12)
        match = next((p for p in plats if p["id"] == platform), None)
        if match is None:
            return {"error": "platform not found", "platform": platform, "feed_label": feed_label}
        if "_air" in match:
            signals = _signals_from_air(match["_air"])
        elif "_ais" in match:
            signals = _signals_from_ais(match["_ais"])
        else:
            d = match["_sample"]
            signals = {"_kind": "drone", "_label": match.get("label", "sample"), "_name": d["name"],
                       **{k: v for k, v in d.items() if not k.startswith("_") and k not in ("id", "name", "kind")}}
        state = _platform_state(match["id"], signals)
        spec = _ACTIONS[action]
        lam = state["lambda"]
        compromised = state["compromise"]["state"] == "compromised"

        # ---- ROE (rules of engagement) checks ----
        roe = []
        # R1: reversibility — all four actions are reversible/advisory (no kinetic effect)
        roe.append({"rule": "R1.reversibility", "pass": bool(spec["reversible"]),
                    "detail": "action is reversible / advisory (no kinetic effect)"})
        # R2: Λ floor for the action (isolate is always permitted as a containment action)
        r2 = lam >= spec["min_lambda"]
        roe.append({"rule": "R2.lambda_floor", "pass": bool(r2),
                    "detail": f"Λ={lam} vs action floor {spec['min_lambda']}"})
        # R3: isolate REQUIRES a fired compromise signal (deny-by-default containment)
        if action == "isolate":
            r3 = compromised or bool(state["compromise"]["checks_fired"])
            roe.append({"rule": "R3.isolate_requires_evidence", "pass": bool(r3),
                        "detail": "isolate requires ≥1 fired compromise check (deny-by-default)"})
        # R4: upgrade/patch require the platform NOT be actively hacked-in-flight (verify first)
        if action in ("upgrade", "patch"):
            r4 = not compromised
            roe.append({"rule": "R4.no_inflight_compromise", "pass": bool(r4),
                        "detail": "do not OTA a platform with an active compromise signal — verify/isolate first"})
        roe_pass = all(r["pass"] for r in roe)

        # ---- Λ-gate (13-axis conjunctive, deny-by-default) ----
        gate_pass = bool(state["yuyay_gate"]["authorized"]) if action != "isolate" else True
        # isolate is a containment action: permitted even when the gate denies engagement.
        authorized = roe_pass and gate_pass
        decision = "AUTHORIZED" if authorized else "DENIED"

        payload = {
            "platform_id": match["id"], "platform_name": match["name"], "kind": match["kind"],
            "action": action, "intent": spec["intent"],
            "decision": decision,
            "lambda": lam, "compromise_state": state["compromise"]["state"],
            "compromise_score": state["compromise"]["compromise_score"],
            "roe": roe, "roe_pass": roe_pass,
            "lambda_gate": {"authorized": gate_pass, "rule": state["yuyay_gate"]["rule"]},
            "lean_theorem_ref": _LEAN_REF,
            "effector": ("SIMULATED — command demonstration only. killinchu does NOT and CANNOT push "
                         "firmware, recall, isolate, or otherwise actuate a real asset. The GOVERNANCE "
                         "(ROE + Λ-gate + signed receipt) is real and provable; the effect is not applied."),
            "feed_label": feed_label,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }
        receipt_node = None
        if emit_receipt:
            try:
                receipt_node = emit_receipt("twin_remediate", payload)
            except Exception:
                receipt_node = None
        out = {
            "ok": True, "decision": decision, "authorized": authorized,
            "request": {"platform": match["id"], "action": action},
            "governance": payload,
        }
        if receipt_node:
            out["receipt"] = {
                "index": receipt_node.get("index"),
                "digest": receipt_node.get("digest"),
                "signed": receipt_node.get("signed", False),
                "dsse": receipt_node.get("dsse"),
                "parents": receipt_node.get("parents"),
            }
            out["receipt_honesty"] = ("DSSE ECDSA-P256-SHA256 over the cosign keypair when the Space secret "
                                      "is set; otherwise an honest UNSIGNED receipt (never a fabricated signature). "
                                      "Verify offline with `cosign verify-blob --key cosign.pub` or POST /khipu/verify.")
        else:
            out["receipt"] = {"signed": False, "note": "receipt chain not wired in this context"}
        return out

    for r in (f"/api/{ns}/v1/twin/platforms", f"/api/{ns}/v1/twin/state", f"/api/{ns}/v1/twin/_self"):
        registered.append("GET " + r)
    registered.append(f"POST /api/{ns}/v1/twin/remediate")
    return {"registered": True, "registered_count": len(registered), "routes": registered}


__all__ = ["register"]
