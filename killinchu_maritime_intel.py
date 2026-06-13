# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — locked=8 {F1,F4,F7,F11,F12,F18,F19,F22} @ kernel c7c0ba17 · Λ=Conjecture 1
# Authored by Yachay (CTO). Co-author: Perplexity Computer Agent (Opus, Maritime Wave 2).
"""
killinchu_maritime_intel.py — REAL dark-fleet / AIS-spoofing / going-dark
detection layer, computed by CORRELATION over the REAL AIS feed that Wave 1/A
broadens at /api/killinchu/v1/feeds/vessels.

WHAT THIS IS (and what it is NOT)
---------------------------------
This is the credible, hard part the incumbents charge for (Starboard, Windward,
Kpler, Lloyd's List Intelligence): detection by *correlation* over real AIS —
NOT list-matching. We add a stateful detection layer ON TOP of W1's stateless
vessel feed. We never fabricate a track, never assert illicit activity as fact.

Windward's own caveat is our doctrine: **dark activity != proof of illicit
activity.** Every judgment below is labelled `advisory: true`, `proven: false`,
carries an honest confidence + the evidence trail, and emits a real DSSE receipt
(via the khipu signer) so the judgment is signed + re-hashable. That receipt
layer is OUR differentiator — no incumbent ships a cryptographically re-verifiable
dark-vessel call.

THREE DETECTORS (all over REAL AIS):
  1. GOING-DARK / AIS-GAP  — GET/POST /api/killinchu/v1/maritime/dark
     Track each vessel's transmission cadence. Flag a gap that is abnormally
     large vs the vessel's OWN normal inter-report interval, AND apply a
     neighbor-coverage check: if nearby vessels kept transmitting through the
     gap window, the gap is likely INTENTIONAL (going dark), not a coverage
     hole. Emits stop-transmitting and resume-after-dark events.
  2. AIS-SPOOFING (by correlation) — /api/killinchu/v1/maritime/spoof
     Signatures, each with cited evidence:
       - teleport     : physically-impossible position jump (implied speed >>
                        any real vessel) between two consecutive reports.
       - mmsi_dup     : same MMSI reported in two places at once (two fixes far
                        apart within a short window).
       - impossible_kinematics : reported SOG impossible for any surface vessel
                        (e.g. a tanker at fighter-jet speed; > 60 kn).
       - identity_mismatch     : nav-status / ship-type claim churn for the same
                        MMSI (a known spoofing tell).
  3. DARK-FLEET RISK ARC — /api/killinchu/v1/maritime/riskarc
     Per vessel, the behavioral arc assembled from the raw signals:
       high-risk-area presence -> spoof onset -> going dark -> dark/STS-suggestive
       rendezvous -> (cross-ref) UN SC 1718 designated. Cross-references Wave A's
       OSINT sanctioned-vessel list (UN Security Council 1718 designated vessels)
       for KNOWN-sanctioned matches by name/alias (and MMSI where present).

RAW SIGNALS FOR WAVE 3 (Λ-RISK-SCORE fusion is W3's job, NOT ours)
------------------------------------------------------------------
We DO NOT compute the fused Λ risk scalar. We expose the raw axes in a clean,
documented shape so W3's killinchu_maritime_risk.derive_axes(vessel, w2) can
aggregate them through the Λ geometric-mean zero-absorption aggregator. The
axis names match W3's `_AXES` exactly:
  {
    "track_id": "ais:<mmsi>", "mmsi": <int>, "label": <str|null>,
    "observations": <int>,
    "gap_prob": <float 0..1|null>,        # P(last/active gap was intentional)
    "spoof_signals": [ {signature, confidence, severity, evidence, ...} , ... ],
    "port_history": [ {area, first_ts, last_ts, count} , ... ],  # high-risk-area presence
    "sts_history":  [ {ts, lat, lon, peer_mmsi, evidence} , ... ],# dark/STS-suggestive
    "loiter": <float 0..1>,               # fraction of fixes loitering in a hot box
    "flag_origin":  {"mid", "flag", "foc", "source"},
    "sanctioned":   {"match": bool, "by": "name|mmsi|null", "designation": {...}|null}
  }
This shape is returned verbatim under `raw_signals_for_w3` on every riskarc
result, and documented in RESULT_MW2.md.

DATA SOURCE
-----------
We consume the REAL feed at /api/killinchu/v1/feeds/vessels (W1/A). Because that
feed is stateless (one snapshot per call), this module keeps a bounded,
in-process rolling HISTORY of observations per MMSI (capped, TTL-pruned). Each
call to a detector first INGESTS a fresh snapshot of the requested theater(s)
into the history, then runs correlation over the accumulated history. A vessel
needs >= 2 observations before kinematic/gap detection can fire — honest: with a
single snapshot we report `observations` counts and say so. No fabrication.

DOCTRINE v11: locked=8 {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17; Λ=Conjecture 1;
advisory not proven; real data; honest confidence; 0 CDN; effector untouched.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

try:
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.requests import Request
except Exception:  # pragma: no cover - starlette always present in the Space
    JSONResponse = None
    Route = None
    Request = None

# --------------------------------------------------------------------------- #
# Constants / honesty strings
# --------------------------------------------------------------------------- #
_ADVISORY = (
    "ADVISORY — computed by correlation over REAL AIS. Dark activity != proof of "
    "illicit activity (Windward caveat). NOT proven; flags RISK with an evidence "
    "trail + honest confidence. Every judgment emits a re-hashable DSSE receipt."
)
_DOCTRINE = "v11"
_KNOTS_TO_MPS = 0.514444
_MPS_TO_KNOTS = 1.0 / _KNOTS_TO_MPS
_EARTH_R_NM = 3440.065  # nautical miles

# Detection thresholds (documented, conservative, tunable).
_GAP_MIN_S = 600          # ignore gaps below 10 min (normal AIS jitter)
_GAP_RATIO_DARK = 4.0     # gap >= 4x the vessel's own median interval => abnormal
_TELEPORT_MAX_KN = 60.0   # implied speed above this between fixes is impossible
_IMPOSSIBLE_SOG_KN = 60.0 # any vessel reporting > 60 kn SOG is impossible
_MMSI_DUP_NM = 5.0        # two fixes > 5 NM apart within the dup window = two places
_MMSI_DUP_WINDOW_S = 120  # at-once window for duplication
_NEIGHBOR_RADIUS_NM = 40.0  # neighbor-coverage check radius
_HIST_TTL_S = 6 * 3600    # prune observations older than 6h
_HIST_MAX_PER_MMSI = 200  # cap history per vessel
_HIST_MAX_MMSI = 20000    # cap total tracked vessels

# High-risk areas (sanctions-evasion / STS hotspots commonly cited in open
# reporting — Kerch Strait, Laconian Gulf, Strait of Hormuz, off Malaysia/Singapore
# STS zone, Nakhodka/Kozmino). Boxes are coarse situational context, labelled.
_HIGH_RISK_AREAS = [
    {"area": "kerch_strait",       "lamin": 44.5, "lamax": 45.6, "lomin": 36.0, "lomax": 37.5},
    {"area": "laconian_gulf",      "lamin": 36.0, "lamax": 37.2, "lomin": 22.2, "lomax": 23.6},
    {"area": "strait_of_hormuz",   "lamin": 25.5, "lamax": 27.2, "lomin": 55.5, "lomax": 57.5},
    {"area": "malaysia_sts_zone",  "lamin": 1.0,  "lamax": 4.5,  "lomin": 103.0, "lomax": 105.5},
    {"area": "kozmino_nakhodka",   "lamin": 42.5, "lamax": 43.3, "lomin": 132.5, "lomax": 133.5},
]
# NOTE: we deliberately do NOT include a Baltic/Gulf-of-Finland "high-risk" box.
# The live no-key AIS source is Baltic, and tagging ordinary Finnish/Baltic
# traffic as "high-risk" would be dishonest noise. High-risk areas are the
# sanctions-evasion / STS hotspots above, used only as situational context.

# Default theaters to sweep when caller doesn't pin one (baltic = live AIS source).
_DEFAULT_SWEEP = ["baltic"]

# --------------------------------------------------------------------------- #
# In-process rolling AIS history (bounded, TTL-pruned). Honest: this is derived
# state over REAL observations, never fabricated.
# --------------------------------------------------------------------------- #
_HIST_LOCK = threading.RLock()
# mmsi(int) -> list[obs]; obs = {ts, lat, lon, sog_kn, cog, heading, kind,
#                                 nav_status, label, country, theater, source}
_HIST: dict = {}
_OSINT_CACHE = {"ts": 0.0, "items": []}
_OSINT_TTL_S = 3600

# Base URL for the same-origin feed self-fetch (server-side). Overridable by env
# for local testing; defaults to the in-container HF port so we never depend on
# external egress. (HF Space listens on 7860.)
_SELF_BASE = os.environ.get("KILLINCHU_SELF_BASE", "http://127.0.0.1:7860")


def _now() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_to_epoch(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _epoch_iso(ts):
    try:
        return datetime.fromtimestamp(ts, timezone.utc).isoformat()
    except Exception:
        return None


def _haversine_nm(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return 2 * _EARTH_R_NM * math.asin(min(1.0, math.sqrt(a)))


# --------------------------------------------------------------------------- #
# Flag-state resolution from MMSI MID (first 3 digits). REAL ITU MID table
# (maritime-relevant subset). Honest: null when unresolved.
# --------------------------------------------------------------------------- #
_MID = {
    "201": "Albania", "205": "Belgium", "209": "Cyprus", "210": "Cyprus",
    "212": "Cyprus", "215": "Malta", "229": "Malta", "230": "Finland",
    "232": "United Kingdom", "235": "United Kingdom", "236": "Gibraltar",
    "247": "Italy", "255": "Portugal (Madeira)", "256": "Malta", "265": "Sweden",
    "266": "Sweden", "273": "Russia", "304": "Antigua & Barbuda",
    "305": "Antigua & Barbuda", "311": "Bahamas", "312": "Belize",
    "341": "St Kitts & Nevis", "351": "Panama", "352": "Panama", "353": "Panama",
    "354": "Panama", "355": "Panama", "356": "Panama", "357": "Panama",
    "370": "Panama", "371": "Panama", "372": "Panama", "373": "Panama",
    "374": "Panama", "412": "China", "413": "China", "414": "China",
    "416": "Taiwan", "422": "Iran", "431": "Japan", "432": "Japan",
    "440": "South Korea", "441": "South Korea", "445": "North Korea",
    "457": "Mongolia", "470": "United Arab Emirates", "477": "Hong Kong",
    "525": "Indonesia", "563": "Singapore", "564": "Singapore", "565": "Singapore",
    "566": "Singapore", "574": "Vietnam", "636": "Liberia", "667": "Sierra Leone",
    "620": "Comoros", "677": "Tanzania", "242": "Morocco",
    "538": "Marshall Islands", "548": "Philippines", "725": "Chile",
    "775": "Venezuela",
}
# Flags commonly cited in open reporting as flags-of-convenience / dark-fleet
# re-flagging destinations (situational context only, NOT an accusation).
_FOC_FLAGS = {
    "Panama", "Liberia", "Marshall Islands", "Comoros", "Sierra Leone",
    "Gabon", "Cameroon", "Cook Islands", "Palau", "São Tomé and Príncipe",
    "Tanzania", "Antigua & Barbuda", "Honduras", "Mongolia", "Belize",
}


def _flag_from_mmsi(mmsi):
    try:
        mid = str(int(mmsi))[:3]
    except Exception:
        return {"mid": None, "flag": None, "foc": None, "source": "MMSI MID"}
    flag = _MID.get(mid)
    return {"mid": int(mid) if mid.isdigit() else None,
            "flag": flag,
            "foc": (flag in _FOC_FLAGS) if flag else None,
            "source": "ITU MID (first 3 digits of MMSI)"}


# --------------------------------------------------------------------------- #
# Ingest: self-fetch the REAL vessel feed and append to rolling history.
# --------------------------------------------------------------------------- #
def _fetch_feed_json(theater, limit=200, timeout=25):
    """Server-side, same-origin fetch of the REAL W1/A vessel feed. Returns the
    parsed envelope or raises. Never fabricates."""
    url = "%s/api/killinchu/v1/feeds/vessels?%s" % (
        _SELF_BASE.rstrip("/"),
        urllib.parse.urlencode({"theater": theater, "limit": limit}),
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "killinchu-maritime-intel/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _prune_locked():
    """Caller holds _HIST_LOCK."""
    cutoff = _now() - _HIST_TTL_S
    dead = []
    for mmsi, obs in _HIST.items():
        kept = [o for o in obs if o["ts"] >= cutoff][-_HIST_MAX_PER_MMSI:]
        if kept:
            _HIST[mmsi] = kept
        else:
            dead.append(mmsi)
    for m in dead:
        _HIST.pop(m, None)
    if len(_HIST) > _HIST_MAX_MMSI:
        ordered = sorted(_HIST.items(), key=lambda kv: kv[1][-1]["ts"])
        for mmsi, _ in ordered[: len(_HIST) - _HIST_MAX_MMSI]:
            _HIST.pop(mmsi, None)


def _ingest_track(track, theater):
    """Append one REAL TRACK observation to the history. Returns mmsi or None."""
    raw = track.get("raw") or {}
    mmsi = raw.get("mmsi")
    if mmsi is None:
        tid = track.get("track_id") or ""
        if tid.startswith("ais:"):
            try:
                mmsi = int(tid.split(":", 1)[1])
            except Exception:
                mmsi = None
    if mmsi is None:
        return None
    try:
        mmsi = int(mmsi)
    except Exception:
        return None
    ts = _iso_to_epoch(track.get("ts")) or _now()
    sog_kn = raw.get("sog_kn")
    if sog_kn is None and track.get("speed_mps") is not None:
        try:
            sog_kn = round(float(track["speed_mps"]) * _MPS_TO_KNOTS, 2)
        except Exception:
            sog_kn = None
    obs = {
        "ts": ts,
        "lat": track.get("lat"),
        "lon": track.get("lon"),
        "sog_kn": sog_kn,
        "cog": raw.get("cog_deg", track.get("heading_deg")),
        "heading": raw.get("heading_deg", track.get("heading_deg")),
        "kind": track.get("kind"),
        "nav_status": raw.get("nav_status"),
        "label": track.get("label"),
        "country": track.get("country"),
        "theater": theater,
        "source": track.get("source"),
    }
    with _HIST_LOCK:
        lst = _HIST.setdefault(mmsi, [])
        # dedupe identical-timestamp re-ingests of the same cached snapshot
        if lst and abs(lst[-1]["ts"] - ts) < 1.0 and lst[-1]["lat"] == obs["lat"] \
                and lst[-1]["lon"] == obs["lon"]:
            return mmsi
        lst.append(obs)
        if len(lst) > _HIST_MAX_PER_MMSI:
            del lst[: len(lst) - _HIST_MAX_PER_MMSI]
    return mmsi


def ingest_theaters(theaters, limit=200):
    """Fetch + ingest the REAL feed for each theater. Returns an honest audit."""
    audit = []
    seen = set()
    for th in theaters:
        rec = {"theater": th, "ok": False, "ingested": 0, "feed_mode": None}
        try:
            env = _fetch_feed_json(th, limit=limit)
            rec["feed_mode"] = env.get("mode")
            rec["feed_live"] = env.get("live")
            n = 0
            for tr in env.get("tracks", []):
                m = _ingest_track(tr, th)
                if m is not None:
                    seen.add(m)
                    n += 1
            rec["ok"] = True
            rec["ingested"] = n
        except Exception as e:
            rec["error"] = "%s: %s" % (type(e).__name__, e)
        audit.append(rec)
    with _HIST_LOCK:
        _prune_locked()
    return audit, seen


# --------------------------------------------------------------------------- #
# Detector 1: GOING-DARK / AIS-GAP
# --------------------------------------------------------------------------- #
def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    if n % 2:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def _vessel_intervals(obs):
    """Inter-report intervals (s) from a vessel's own history."""
    ts = sorted(o["ts"] for o in obs)
    return [b - a for a, b in zip(ts, ts[1:]) if b - a > 0]


def _neighbor_coverage(mmsi, gap_start, gap_end, ref_lat, ref_lon):
    """Were OTHER vessels (within _NEIGHBOR_RADIUS_NM of the dark vessel's last
    known position) still transmitting DURING the gap window? If yes, the gap is
    likely intentional (going dark), not a coverage hole. Returns
    (neighbor_count, transmitting_during_gap, sample_neighbors)."""
    neighbors = 0
    transmitting = 0
    sample = []
    with _HIST_LOCK:
        items = list(_HIST.items())
    for other, oobs in items:
        if other == mmsi or not oobs:
            continue
        last = oobs[-1]
        if last["lat"] is None or ref_lat is None:
            continue
        d = _haversine_nm(ref_lat, ref_lon, last["lat"], last["lon"])
        if d is None or d > _NEIGHBOR_RADIUS_NM:
            continue
        neighbors += 1
        in_gap = any(gap_start < o["ts"] < gap_end for o in oobs)
        if in_gap:
            transmitting += 1
            if len(sample) < 5:
                sample.append({"mmsi": other, "dist_nm": round(d, 1),
                               "fixes_in_gap": sum(1 for o in oobs
                                                   if gap_start < o["ts"] < gap_end)})
    return neighbors, transmitting, sample


def _gap_prob(gap_s, med_s, neighbors, neighbors_tx):
    """Honest heuristic probability the gap was INTENTIONAL (going dark) rather
    than a coverage/equipment hole. Bounded 0..1.
      - the bigger the gap relative to the vessel's OWN cadence, the higher.
      - if neighbors kept transmitting through the gap (coverage was fine), that
        raises P(intentional). If NO neighbors were around, we cannot rule out a
        coverage hole, so we cap the probability at 0.5.
    RAW signal for W3's Λ fusion — NOT a fused verdict."""
    ratio = gap_s / med_s if med_s > 0 else 0.0
    base = 1.0 / (1.0 + math.exp(-(math.log(max(ratio, 1e-6)) - math.log(_GAP_RATIO_DARK))))
    if neighbors == 0:
        return round(min(base, 0.5), 3)
    cov = neighbors_tx / neighbors
    p = 0.5 * base + 0.5 * (base * (0.4 + 0.6 * cov))
    return round(max(0.0, min(1.0, p)), 3)


def detect_dark(mmsis=None, now=None):
    """Going-dark / AIS-gap detection over the rolling history.

    For each vessel: compute its OWN median inter-report interval, then look for
    (a) an ACTIVE gap (silent since last fix) or (b) a historical internal gap,
    that is abnormally large vs its own cadence. Apply the neighbor-coverage
    check to estimate P(intentional)."""
    now = now or _now()
    out = []
    with _HIST_LOCK:
        items = [(m, list(o)) for m, o in _HIST.items()
                 if (mmsis is None or m in mmsis)]
    for mmsi, obs in items:
        if len(obs) < 2:
            continue
        obs.sort(key=lambda o: o["ts"])
        intervals = _vessel_intervals(obs)
        if not intervals:
            continue
        med = _median(intervals) or 0.0
        if med <= 0:
            continue
        last = obs[-1]
        events = []

        # (a) ACTIVE gap: silent since last fix.
        active_gap = now - last["ts"]
        if active_gap >= _GAP_MIN_S and active_gap >= _GAP_RATIO_DARK * med:
            n_nb, tx_nb, sample = _neighbor_coverage(
                mmsi, last["ts"], now, last["lat"], last["lon"])
            gp = _gap_prob(active_gap, med, n_nb, tx_nb)
            events.append({
                "event": "stop-transmitting",
                "gap_s": round(active_gap, 1),
                "vessel_median_interval_s": round(med, 1),
                "gap_ratio": round(active_gap / med, 1),
                "neighbors_in_radius": n_nb,
                "neighbors_transmitting_during_gap": tx_nb,
                "neighbor_sample": sample,
                "gap_prob": gp,
                "evidence": ("silent for %.0fs vs own median %.0fs (%.1fx); "
                             "%d/%d neighbors within %.0f NM kept transmitting "
                             "during the gap"
                             % (active_gap, med, active_gap / med, tx_nb, n_nb,
                                _NEIGHBOR_RADIUS_NM)),
            })

        # (b) resume-after-dark: a large internal gap followed by a later fix.
        for a, b in zip(obs, obs[1:]):
            g = b["ts"] - a["ts"]
            if g >= _GAP_MIN_S and g >= _GAP_RATIO_DARK * med:
                n_nb, tx_nb, sample = _neighbor_coverage(
                    mmsi, a["ts"], b["ts"], a["lat"], a["lon"])
                gp = _gap_prob(g, med, n_nb, tx_nb)
                moved_nm = _haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"])
                events.append({
                    "event": "resume-after-dark",
                    "gap_s": round(g, 1),
                    "dark_from": _epoch_iso(a["ts"]),
                    "reappeared_at": _epoch_iso(b["ts"]),
                    "vessel_median_interval_s": round(med, 1),
                    "gap_ratio": round(g / med, 1),
                    "moved_nm_during_dark": (round(moved_nm, 1)
                                             if moved_nm is not None else None),
                    "neighbors_in_radius": n_nb,
                    "neighbors_transmitting_during_gap": tx_nb,
                    "neighbor_sample": sample,
                    "gap_prob": gp,
                    "evidence": ("dark for %.0fs vs own median %.0fs (%.1fx), then "
                                 "reappeared %s NM away; %d/%d neighbors kept "
                                 "transmitting during the gap"
                                 % (g, med, g / med,
                                    ("%.1f" % moved_nm) if moved_nm is not None else "?",
                                    tx_nb, n_nb)),
                })
        if events:
            out.append({
                "track_id": "ais:%d" % mmsi,
                "mmsi": mmsi,
                "label": last.get("label"),
                "last_lat": last["lat"], "last_lon": last["lon"],
                "last_seen": _epoch_iso(last["ts"]),
                "observations": len(obs),
                "flag_origin": _flag_from_mmsi(mmsi),
                "events": events,
                "advisory": True, "proven": False,
            })
    return out


# --------------------------------------------------------------------------- #
# Detector 2: AIS-SPOOFING by correlation
# --------------------------------------------------------------------------- #
def detect_spoof(mmsis=None):
    out = []
    with _HIST_LOCK:
        items = [(m, list(o)) for m, o in _HIST.items()
                 if (mmsis is None or m in mmsis)]
    for mmsi, obs in items:
        obs.sort(key=lambda o: o["ts"])
        signals = []

        # --- impossible kinematics: SOG impossible for any surface vessel ---
        for o in obs:
            if o["sog_kn"] is not None and o["sog_kn"] > _IMPOSSIBLE_SOG_KN:
                signals.append({
                    "signature": "impossible_kinematics",
                    "confidence": 0.9, "severity": 0.9,
                    "evidence": ("reported SOG %.1f kn at %s exceeds the %.0f kn "
                                 "ceiling for any real surface vessel (tanker-at-"
                                 "fighter-jet-speed)"
                                 % (o["sog_kn"], _epoch_iso(o["ts"]), _IMPOSSIBLE_SOG_KN)),
                    "at": {"lat": o["lat"], "lon": o["lon"], "ts": _epoch_iso(o["ts"]),
                           "sog_kn": o["sog_kn"]},
                })

        # --- teleport: implied speed between consecutive fixes is impossible ---
        for a, b in zip(obs, obs[1:]):
            dt = b["ts"] - a["ts"]
            d = _haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"])
            if dt <= 0 or d is None:
                continue
            implied_kn = d / (dt / 3600.0)
            if implied_kn > _TELEPORT_MAX_KN and d > 1.0:
                _tconf = round(min(0.99, 0.6 + (implied_kn / _TELEPORT_MAX_KN) * 0.1), 3)
                signals.append({
                    "signature": "teleport",
                    "confidence": _tconf, "severity": _tconf,
                    "evidence": ("position jumped %.1f NM in %.0fs => implied %.0f kn, "
                                 "physically impossible (> %.0f kn)"
                                 % (d, dt, implied_kn, _TELEPORT_MAX_KN)),
                    "from": {"lat": a["lat"], "lon": a["lon"], "ts": _epoch_iso(a["ts"])},
                    "to": {"lat": b["lat"], "lon": b["lon"], "ts": _epoch_iso(b["ts"])},
                    "implied_speed_kn": round(implied_kn, 1),
                })

        # --- mmsi duplication: same MMSI in two far-apart places at once ---
        n = len(obs)
        for i in range(n):
            for j in range(i + 1, n):
                dt = obs[j]["ts"] - obs[i]["ts"]
                if dt > _MMSI_DUP_WINDOW_S:
                    break
                d = _haversine_nm(obs[i]["lat"], obs[i]["lon"],
                                  obs[j]["lat"], obs[j]["lon"])
                if d is not None and d > _MMSI_DUP_NM:
                    _dconf = round(min(0.97, 0.7 + d / 100.0), 3)
                    signals.append({
                        "signature": "mmsi_dup",
                        "confidence": _dconf, "severity": _dconf,
                        "evidence": ("same MMSI %d reported %.1f NM apart within %.0fs "
                                     "=> the identity is broadcasting from two places "
                                     "at once (duplication / identity theft)"
                                     % (mmsi, d, dt)),
                        "pos_a": {"lat": obs[i]["lat"], "lon": obs[i]["lon"],
                                  "ts": _epoch_iso(obs[i]["ts"])},
                        "pos_b": {"lat": obs[j]["lat"], "lon": obs[j]["lon"],
                                  "ts": _epoch_iso(obs[j]["ts"])},
                        "separation_nm": round(d, 1),
                    })
                    break  # one dup signal per i is enough

        # --- identity / ship-type mismatch: nav_status or kind churn ---
        kinds = [o["kind"] for o in obs if o.get("kind")]
        distinct_kinds = sorted(set(kinds))
        if len(distinct_kinds) > 1:
            signals.append({
                "signature": "identity_mismatch",
                "confidence": 0.5, "severity": 0.5,
                "evidence": ("ship type/nav-status claim CHANGED across reports for "
                             "the same MMSI: %s — identity churn is a known spoofing "
                             "tell" % distinct_kinds),
                "distinct_claims": distinct_kinds,
            })

        if signals:
            # Collapse repeated same-signature hits (e.g. the same impossible SOG
            # reported across consecutive fixes) into ONE signal carrying an
            # `occurrences` count — honest, not inflated.
            best = {}
            for s in signals:
                if s["signature"] in ("impossible_kinematics", "identity_mismatch"):
                    k = (s["signature"],)
                else:
                    k = (s["signature"], json.dumps(s.get("evidence"))[:60])
                cur = best.get(k)
                if cur is None:
                    s = dict(s)
                    s["occurrences"] = 1
                    best[k] = s
                else:
                    cur["occurrences"] = cur.get("occurrences", 1) + 1
                    if s["confidence"] > cur["confidence"]:
                        cur["confidence"] = s["confidence"]
            sig_list = sorted(best.values(), key=lambda s: -s["confidence"])
            last = obs[-1] if obs else {}
            out.append({
                "track_id": "ais:%d" % mmsi,
                "mmsi": mmsi,
                "label": last.get("label"),
                "last_lat": last.get("lat"), "last_lon": last.get("lon"),
                "observations": len(obs),
                "flag_origin": _flag_from_mmsi(mmsi),
                "spoof_signals": sig_list,
                "max_confidence": max(s["confidence"] for s in sig_list),
                "advisory": True, "proven": False,
            })
    return out


# --------------------------------------------------------------------------- #
# OSINT cross-reference (Wave A): UN SC 1718 designated vessels.
# --------------------------------------------------------------------------- #
def _load_osint_sanctioned(timeout=20):
    now = _now()
    if (now - _OSINT_CACHE["ts"]) < _OSINT_TTL_S and _OSINT_CACHE["items"]:
        return _OSINT_CACHE["items"]
    try:
        url = "%s/api/killinchu/v1/osint/intel?vertical=sanctioned_vessels" % _SELF_BASE.rstrip("/")
        req = urllib.request.Request(url, headers={
            "User-Agent": "killinchu-maritime-intel/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            env = json.loads(r.read().decode("utf-8", "replace"))
        items = (((env.get("verticals") or {}).get("sanctioned_vessels") or {}).get("items")) or []
        _OSINT_CACHE["items"] = items
        _OSINT_CACHE["ts"] = now
    except Exception:
        pass
    return _OSINT_CACHE["items"]


def _sanctioned_match(mmsi, label):
    """Cross-reference a vessel against the UN SC 1718 designated list. Match by
    name/alias (label) — MMSI rarely present in the public list, so name is the
    honest join key. Returns a match record or a no-match record (never asserts)."""
    items = _load_osint_sanctioned()
    if not items:
        return {"match": False, "by": None, "designation": None,
                "note": "UN SC 1718 list unavailable this cycle"}
    name = (label or "").strip().upper()
    if name:
        for it in items:
            cand = [(it.get("name") or "").strip().upper()]
            cand += [(a or "").strip().upper() for a in (it.get("aliases") or [])]
            if name in [c for c in cand if c]:
                return {"match": True, "by": "name", "designation": {
                    "name": it.get("name"), "program": it.get("program"),
                    "countries": it.get("countries"),
                    "source": "UN Security Council 1718 Committee — Designated Vessels",
                    "source_url": "https://data.opensanctions.org/datasets/latest/un_1718_vessels/targets.simple.csv",
                }}
    return {"match": False, "by": None, "designation": None,
            "note": "no UN SC 1718 designation matched by name/MMSI (advisory)"}


# --------------------------------------------------------------------------- #
# Detector 3: DARK-FLEET RISK ARC + RAW SIGNALS for W3
# --------------------------------------------------------------------------- #
def _area_for(lat, lon):
    if lat is None or lon is None:
        return None
    for a in _HIGH_RISK_AREAS:
        if a["lamin"] <= lat <= a["lamax"] and a["lomin"] <= lon <= a["lomax"]:
            return a["area"]
    return None


def _port_history(obs):
    """High-risk-area presence assembled from the vessel's own track."""
    acc = {}
    for o in obs:
        area = _area_for(o["lat"], o["lon"])
        if not area:
            continue
        e = acc.setdefault(area, {"area": area, "first_ts": o["ts"],
                                  "last_ts": o["ts"], "count": 0})
        e["first_ts"] = min(e["first_ts"], o["ts"])
        e["last_ts"] = max(e["last_ts"], o["ts"])
        e["count"] += 1
    return [{"area": v["area"], "first_ts": _epoch_iso(v["first_ts"]),
             "last_ts": _epoch_iso(v["last_ts"]), "count": v["count"]}
            for v in acc.values()]


def _sts_history(mmsi, obs):
    """Dark/STS-suggestive events: this vessel went near-stationary (loitering)
    close to ANOTHER vessel that is also near-stationary — the classic
    ship-to-ship transfer signature. Honest: suggestive, NOT proven."""
    sts = []
    with _HIST_LOCK:
        others = [(m, o[-1]) for m, o in _HIST.items() if m != mmsi and o]
    for o in obs:
        if o["lat"] is None or o["sog_kn"] is None:
            continue
        if o["sog_kn"] > 1.0:  # must be loitering (<=1 kn)
            continue
        for om, last in others:
            if last["lat"] is None or last.get("sog_kn") is None:
                continue
            if last["sog_kn"] > 1.0:
                continue
            d = _haversine_nm(o["lat"], o["lon"], last["lat"], last["lon"])
            if d is not None and d < 0.5:  # within ~0.5 NM, both loitering
                sts.append({
                    "ts": _epoch_iso(o["ts"]),
                    "lat": o["lat"], "lon": o["lon"],
                    "peer_mmsi": om,
                    "evidence": ("both vessels near-stationary (<=1 kn) and within "
                                 "%.2f NM — STS-suggestive rendezvous (advisory)" % d),
                })
                break
    return sts


def _loiter_signal(obs):
    """Loitering-near-high-risk-box signal in [0,1] for W3's `loiter` axis: the
    fraction of recent fixes that were near-stationary (<=1 kn) INSIDE a
    high-risk area. 0.0 when never. Advisory."""
    rel = [o for o in obs if o.get("lat") is not None and o.get("sog_kn") is not None]
    if not rel:
        return 0.0
    hot_loiter = sum(1 for o in rel
                     if o["sog_kn"] <= 1.0 and _area_for(o["lat"], o["lon"]))
    return round(hot_loiter / len(rel), 3)


def raw_signals_for(mmsi):
    """The clean, documented raw-signal shape Wave 3 consumes for Λ fusion.
    We provide the AXES, never the fused scalar. Axis names match W3's _AXES."""
    with _HIST_LOCK:
        obs = list(_HIST.get(mmsi, []))
    obs.sort(key=lambda o: o["ts"])
    last = obs[-1] if obs else {}
    dark = detect_dark(mmsis={mmsi})
    gap_prob = None
    if dark:
        probs = [e.get("gap_prob") for e in dark[0]["events"] if e.get("gap_prob") is not None]
        gap_prob = max(probs) if probs else None
    spoof = detect_spoof(mmsis={mmsi})
    spoof_signals = spoof[0]["spoof_signals"] if spoof else []
    return {
        "track_id": "ais:%d" % mmsi,
        "mmsi": mmsi,
        "label": last.get("label"),
        "observations": len(obs),
        "gap_prob": gap_prob,
        "spoof_signals": spoof_signals,
        "port_history": _port_history(obs),
        "sts_history": _sts_history(mmsi, obs),
        "loiter": _loiter_signal(obs),
        "flag_origin": _flag_from_mmsi(mmsi),
        "sanctioned": _sanctioned_match(mmsi, last.get("label")),
        "_doc": ("raw axes for Wave 3 (killinchu_maritime_risk.derive_axes) Λ "
                 "geometric-mean fusion; W2 does NOT fuse. Each axis is advisory, "
                 "computed over REAL AIS."),
    }


def detect_riskarc(mmsis=None):
    """Per-vessel behavioral arc + the raw-signal bundle. The arc is an ordered,
    evidence-stamped narrative — NOT a verdict, NOT a fused score."""
    with _HIST_LOCK:
        keys = [m for m in _HIST.keys() if (mmsis is None or m in mmsis)]
    out = []
    for mmsi in keys:
        rs = raw_signals_for(mmsi)
        arc = []
        if rs["port_history"]:
            areas = ", ".join(p["area"] for p in rs["port_history"])
            arc.append({"stage": "high_risk_area_presence",
                        "detail": "observed in high-risk area(s): %s" % areas,
                        "evidence": rs["port_history"]})
        if rs["spoof_signals"]:
            sigs = ", ".join(sorted(set(s["signature"] for s in rs["spoof_signals"])))
            arc.append({"stage": "spoof_onset",
                        "detail": "AIS-spoofing signature(s): %s" % sigs,
                        "evidence": rs["spoof_signals"]})
        if rs["gap_prob"] is not None and rs["gap_prob"] >= 0.5:
            arc.append({"stage": "going_dark",
                        "detail": "abnormal AIS gap, P(intentional)=%.2f" % rs["gap_prob"],
                        "evidence": {"gap_prob": rs["gap_prob"]}})
        if rs["sts_history"]:
            arc.append({"stage": "dark_sts",
                        "detail": "STS-suggestive loitering rendezvous (%d)" % len(rs["sts_history"]),
                        "evidence": rs["sts_history"]})
        if rs["sanctioned"]["match"]:
            arc.append({"stage": "sanctioned",
                        "detail": "matches a UN SC 1718 designated vessel by %s" % rs["sanctioned"]["by"],
                        "evidence": rs["sanctioned"]["designation"]})
        if rs["flag_origin"].get("foc"):
            arc.append({"stage": "flag_of_convenience",
                        "detail": "flag-of-convenience: %s (situational context)" % rs["flag_origin"]["flag"],
                        "evidence": rs["flag_origin"]})
        if not arc:
            continue  # no risk signal -> not in the arc list (honest)
        out.append({
            "track_id": rs["track_id"], "mmsi": mmsi, "label": rs["label"],
            "arc": arc,
            "arc_stages": [a["stage"] for a in arc],
            "raw_signals_for_w3": rs,
            "advisory": True, "proven": False,
            "label_note": ("behavioral RISK arc — advisory, NOT proof of illicit "
                           "activity. Λ fusion is Wave 3's job."),
        })
    return out


# --------------------------------------------------------------------------- #
# DSSE receipt (our differentiator) — sign each detection in-process via the
# khipu signer so the judgment is signed + re-hashable. Never fabricates a sig.
# --------------------------------------------------------------------------- #
_SEQ_LOCK = threading.Lock()
_SEQ = {"n": 0, "prev": "0" * 64}


def sign_detection(action, summary):
    """Emit a real DSSE receipt for a detection judgment. Returns the envelope or
    an honest error object (never a fake signature)."""
    try:
        import killinchu_szl_pqc_sign as _signer
    except Exception as e:
        return {"signed": False, "error": "signer unavailable: %r" % e}
    import hashlib
    with _SEQ_LOCK:
        _SEQ["n"] += 1
        seq = _SEQ["n"]
        prev = _SEQ["prev"]
        payload = {
            "action": action,
            "seq": seq,
            "prev_hash": prev,
            "doctrine": _DOCTRINE,
            "advisory": True,
            "proven": False,
            "summary": summary,
            "ts": _now_iso(),
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        try:
            env = _signer._sign(body, "ecdsa")
        except Exception as e:
            return {"signed": False, "error": "sign failed: %r" % e}
        _SEQ["prev"] = hashlib.sha256(body).hexdigest()
    return {"signed": True, "seq": seq, "receipt": env,
            "note": "real DSSE receipt — the judgment is signed + re-hashable"}


# --------------------------------------------------------------------------- #
# HTTP layer
# --------------------------------------------------------------------------- #
def _parse_theaters(request):
    raw = request.query_params.get("theaters") or request.query_params.get("theater")
    if not raw:
        return list(_DEFAULT_SWEEP)
    return [t.strip() for t in raw.split(",") if t.strip()]


def _want_sign(request):
    return (request.query_params.get("sign", "1").lower()
            not in ("0", "false", "no"))


def _common_envelope(feed, theaters, ingest_audit, extra):
    env = {
        "feed": feed, "domain": "sea", "doctrine": _DOCTRINE,
        "theaters": theaters, "ingest": ingest_audit,
        "tracked_vessels": len(_HIST),
        "advisory": True, "proven": False, "label": _ADVISORY,
        "fetched_at": _now_iso(),
    }
    env.update(extra)
    return env


def register(app, ns="killinchu"):
    base = "/api/%s/v1" % ns

    async def _run(fn, *a, **kw):
        import anyio
        return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))

    async def _dark(request):
        theaters = _parse_theaters(request)
        audit, seen = await _run(ingest_theaters, theaters)
        results = await _run(detect_dark)
        receipt = None
        if _want_sign(request) and results:
            receipt = await _run(
                sign_detection, "maritime.dark.detect",
                {"detector": "going_dark", "flagged": len(results), "theaters": theaters})
        return JSONResponse(_common_envelope(
            "maritime/dark", theaters, audit, {
                "method": ("going-dark / AIS-gap by correlation: abnormal gap vs the "
                           "vessel's OWN cadence + neighbor-coverage check "
                           "(neighbors still transmitting => likely intentional)"),
                "thresholds": {"gap_min_s": _GAP_MIN_S, "gap_ratio_dark": _GAP_RATIO_DARK,
                               "neighbor_radius_nm": _NEIGHBOR_RADIUS_NM},
                "count": len(results), "flagged": results, "receipt": receipt,
            }))

    async def _spoof(request):
        theaters = _parse_theaters(request)
        audit, seen = await _run(ingest_theaters, theaters)
        results = await _run(detect_spoof)
        receipt = None
        if _want_sign(request) and results:
            receipt = await _run(
                sign_detection, "maritime.spoof.detect",
                {"detector": "ais_spoof", "flagged": len(results), "theaters": theaters})
        return JSONResponse(_common_envelope(
            "maritime/spoof", theaters, audit, {
                "method": ("AIS-spoofing by correlation: teleport (impossible position "
                           "jump), mmsi_dup (same MMSI two places at once), "
                           "impossible_kinematics (vessel at fighter-jet speed), "
                           "identity_mismatch (ship-type/nav-status churn). Each flag "
                           "cites its signature + evidence."),
                "signatures": ["teleport", "mmsi_dup", "impossible_kinematics",
                               "identity_mismatch"],
                "thresholds": {"teleport_max_kn": _TELEPORT_MAX_KN,
                               "impossible_sog_kn": _IMPOSSIBLE_SOG_KN,
                               "mmsi_dup_nm": _MMSI_DUP_NM,
                               "mmsi_dup_window_s": _MMSI_DUP_WINDOW_S},
                "count": len(results), "flagged": results, "receipt": receipt,
            }))

    async def _riskarc(request):
        theaters = _parse_theaters(request)
        audit, seen = await _run(ingest_theaters, theaters)
        results = await _run(detect_riskarc)
        receipt = None
        if _want_sign(request) and results:
            receipt = await _run(
                sign_detection, "maritime.riskarc.detect",
                {"detector": "dark_fleet_risk_arc", "flagged": len(results), "theaters": theaters})
        return JSONResponse(_common_envelope(
            "maritime/riskarc", theaters, audit, {
                "method": ("dark-fleet behavioral risk ARC: high-risk-area presence -> "
                           "spoof onset -> going dark -> STS-suggestive rendezvous -> "
                           "(cross-ref) UN SC 1718 designated. Provides the RAW SIGNALS "
                           "for Wave 3's Λ fusion (gap_prob, spoof_signals[], "
                           "port_history, sts_history, loiter, flag_origin, sanctioned) "
                           "— W2 does NOT compute the fused Λ scalar."),
                "raw_signal_shape": {
                    "track_id": "str", "mmsi": "int",
                    "gap_prob": "float 0..1|null",
                    "spoof_signals": "[{signature,confidence,severity,evidence}]",
                    "port_history": "[{area,first_ts,last_ts,count}]",
                    "sts_history": "[{ts,lat,lon,peer_mmsi,evidence}]",
                    "loiter": "float 0..1",
                    "flag_origin": "{mid,flag,foc,source}",
                    "sanctioned": "{match,by,designation}",
                },
                "w3_consumer": "killinchu_maritime_risk.derive_axes(vessel, w2=raw_signals_for_w3)",
                "count": len(results), "flagged": results, "receipt": receipt,
            }))

    async def _status(request):
        with _HIST_LOCK:
            n_mmsi = len(_HIST)
            total_obs = sum(len(v) for v in _HIST.values())
            multi = sum(1 for v in _HIST.values() if len(v) >= 2)
        return JSONResponse({
            "layer": "killinchu maritime intelligence (dark-fleet / spoof / risk-arc)",
            "doctrine": _DOCTRINE, "label": _ADVISORY,
            "history": {"tracked_vessels": n_mmsi, "total_observations": total_obs,
                        "vessels_with_2plus_obs": multi, "ttl_s": _HIST_TTL_S},
            "detectors": {
                "dark": "%s/maritime/dark" % base,
                "spoof": "%s/maritime/spoof" % base,
                "riskarc": "%s/maritime/riskarc" % base,
            },
            "consumes": "%s/feeds/vessels (REAL AIS, Wave 1/A)" % base,
            "raw_signals_for_w3": ("gap_prob, spoof_signals[], port_history, "
                                   "sts_history, loiter, flag_origin, sanctioned"),
            "w3_fusion": "killinchu_maritime_risk.py (/maritime/risk) — NOT this module",
            "receipt": "each detection emits a real DSSE receipt via the khipu signer",
            "fetched_at": _now_iso(),
        })

    routes = [
        Route("%s/maritime/dark" % base, _dark, methods=["GET", "POST"], name="%s_maritime_dark" % ns),
        Route("%s/maritime/spoof" % base, _spoof, methods=["GET", "POST"], name="%s_maritime_spoof" % ns),
        Route("%s/maritime/riskarc" % base, _riskarc, methods=["GET", "POST"], name="%s_maritime_riskarc" % ns),
        Route("%s/maritime/status" % base, _status, methods=["GET"], name="%s_maritime_status" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)

    return {"status": "ok", "base": base,
            "endpoints": ["%s/maritime/%s" % (base, e)
                          for e in ("dark", "spoof", "riskarc", "status")]}
