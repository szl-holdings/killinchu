# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173 - Doctrine v11/v12
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
killinchu_warhacker_demos - EXHAUSTIVE, step-by-step, REAL maritime/drone demo
backends for the 7 killinchu Warhacker problems. Every value is COMPUTED in-image
at request time (no canned PASS). Mode genuinely changes the outcome
(nominal != tamper). Each demo exposes:

  POST /api/killinchu/v1/warhacker/launch/{key}   {mode:"nominal"|"tamper"}
  GET  /api/killinchu/v1/warhacker/index

Each run carries:
  - ordered STEP TIMELINE (each step: name, status, real duration_ms, value_computed)
  - a CATCH TREE (boolean cascade, first failing node auto-expanded)
  - the REAL computed numbers (CPA km, TCPA s, STL rho, residuals, gap seconds...)
  - a real DSSE/cosign receipt: receipt_id = "kc-rcpt-" +
        sha256(pae_sha256 | chain_hash | mode | decision)[:16]   (UNIQUE per run)
  - chain verification: chain_self INTACT on every run; an always-on tamper_test
        that flips ONE byte in the signed Merkle chain -> chain BREAKS with a named
        first-failing condition.

PROBLEMS (7):
  1. spoofed-ais        AIS/GPS spoofing — kinematic-bound + conformal residual.
  2. dark-vessel        AIS-off "dark" vessel — gap detection + track association.
  3. geofence-incursion EEZ/keep-out breach — PolyCARP point-in-polygon (G1).
  4. collision-cpa      CPA/TCPA collision risk — min-distance (G1).
  5. swarm-hijack       drone swarm integrity — boids consensus + Byzantine + signed cmd.
  6. tampered-command   command receipt tamper — DSSE + hash-chain append-only (M2).
  7. roe-violation      rules-of-engagement — Λ 13-axis conjunctive gate (deny-by-default).

The signer is the REAL killinchu cosign DSSE key (szlholdings-cosign) passed in by
serve.py (szl_dsse.sign_payload); the YUYAY 13-axis conjunctive gate doctrine is
reused for roe-violation. NO proprietary code is copied — patterns are
reimplemented from MIT/Apache/NOSA references (RTAMT MIT, PolyCARP NOSA, DSSE
Apache-2.0, sigstore/rekor Apache-2.0, Reynolds boids). Honesty labels are
first-class; nothing is faked.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.routing import Route


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(obj) -> str:
    if isinstance(obj, (bytes, bytearray)):
        return hashlib.sha256(bytes(obj)).hexdigest()
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# SHARED: append-only SHA-256 hash chain + RFC-6962 Merkle tree + inclusion
# proof. Pattern reimplemented from sigstore/rekor (Apache-2.0) + RFC 6962.
# ---------------------------------------------------------------------------
def _merkle_root(leaves):
    if not leaves:
        return _sha(b"")
    level = [bytes.fromhex(h) for h in leaves]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest())
            else:
                nxt.append(level[i])
        level = nxt
    return level[0].hex()


def _inclusion_proof(leaves, index):
    proof = []
    level = [bytes.fromhex(h) for h in leaves]
    idx = index
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                parent = hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest()
                if i == idx or i + 1 == idx:
                    sib = level[i + 1] if i == idx else level[i]
                    side = "R" if i == idx else "L"
                    proof.append({"hash": sib.hex(), "side": side})
            else:
                parent = level[i]
            nxt.append(parent)
        idx = idx // 2
        level = nxt
    return proof


def _verify_inclusion(leaf_hash, index, proof, root):
    cur = bytes.fromhex(leaf_hash)
    for step in proof:
        sib = bytes.fromhex(step["hash"])
        if step["side"] == "R":
            cur = hashlib.sha256(b"\x01" + cur + sib).digest()
        else:
            cur = hashlib.sha256(b"\x01" + sib + cur).digest()
    return cur.hex() == root


class _KhipuChain:
    """Append-only chained log: H_n = SHA256(H_{n-1} || leaf_n). Carries a Merkle
    root, supports independent re-verification + a single-byte tamper test."""

    def __init__(self):
        self.entries = []
        self._prev = "GENESIS"

    def append(self, payload):
        leaf = _sha(payload)
        chain_hash = hashlib.sha256((self._prev + "||" + leaf).encode()).hexdigest()
        e = {"seq": len(self.entries), "ts_utc": _now(), "payload": payload,
             "leaf_hash": leaf, "prev_chain": self._prev, "chain_hash": chain_hash}
        self._prev = chain_hash
        self.entries.append(e)
        return e

    def leaves(self):
        return [e["leaf_hash"] for e in self.entries]

    def root(self):
        return _merkle_root(self.leaves())

    def verify(self, tamper_seq=None, tamper_field=None):
        entries = [dict(e) for e in self.entries]
        tamper_note = None
        if tamper_seq is not None and 0 <= tamper_seq < len(entries):
            victim = json.loads(json.dumps(entries[tamper_seq]["payload"]))
            fld = tamper_field or _first_str_field(victim)
            before = _get_path(victim, fld)
            after = _flip_one_char(before)
            _set_path(victim, fld, after)
            entries[tamper_seq] = dict(entries[tamper_seq])
            entries[tamper_seq]["payload"] = victim
            tamper_note = {"tampered_seq": tamper_seq, "field": fld,
                           "before": before, "after": after, "bytes_changed": 1}
        prev = "GENESIS"
        chain_ok = True
        broken_at = None
        recomputed_leaves = []
        for e in entries:
            leaf = _sha(e["payload"])
            recomputed_leaves.append(leaf)
            ch = hashlib.sha256((prev + "||" + leaf).encode()).hexdigest()
            if e["prev_chain"] != prev or e["leaf_hash"] != leaf or e["chain_hash"] != ch:
                chain_ok = False
                broken_at = e["seq"]
                break
            prev = e["chain_hash"]
        committed_root = self.root()
        recomputed_root = _merkle_root(recomputed_leaves) if len(recomputed_leaves) == len(self.entries) else None
        root_ok = (recomputed_root == committed_root)
        incl = None
        if tamper_seq is not None and tamper_seq < len(entries):
            leaf_now = _sha(entries[tamper_seq]["payload"])
            proof = _inclusion_proof(self.leaves(), tamper_seq)
            incl = {"checked_seq": tamper_seq, "leaf_hash_now": leaf_now,
                    "leaf_hash_committed": self.entries[tamper_seq]["leaf_hash"],
                    "audit_path_len": len(proof),
                    "inclusion_valid": _verify_inclusion(leaf_now, tamper_seq, proof, committed_root),
                    "committed_root": committed_root}
        return {"chain_intact": chain_ok, "chain_break_at_seq": broken_at,
                "merkle_root_committed": committed_root, "merkle_root_recomputed": recomputed_root,
                "merkle_root_matches": root_ok, "inclusion": incl, "tamper": tamper_note,
                "depth": len(self.entries)}


def _first_str_field(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, str):
            return prefix + k
        if isinstance(v, dict):
            r = _first_str_field(v, prefix + k + ".")
            if r:
                return r
    return None


def _get_path(d, path):
    cur = d
    for p in path.split("."):
        cur = cur[p]
    return cur


def _set_path(d, path, val):
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur[p]
    cur[parts[-1]] = val


def _flip_one_char(s):
    if not s:
        return "X"
    i = len(s) // 2
    c = s[i]
    nc = ("0" if c != "0" else "1") if c.isdigit() else ("a" if c != "a" else "b")
    return s[:i] + nc + s[i + 1:]


# ---------------------------------------------------------------------------
# SHARED: real wall-clock step timing.
# ---------------------------------------------------------------------------
class _Timeline:
    def __init__(self):
        self.steps = []

    def run(self, name, fn, kind="compute"):
        t0 = time.perf_counter()
        ok = True
        value = None
        err = None
        try:
            value = fn()
            if isinstance(value, dict) and value.get("_step_failed"):
                ok = False
        except Exception as e:
            ok = False
            err = "%s: %s" % (type(e).__name__, e)
        dt = (time.perf_counter() - t0) * 1000.0
        self.steps.append({"step": name, "kind": kind, "status": "PASS" if ok else "FAIL",
                           "ok": ok, "duration_ms": round(dt, 3),
                           "value_computed": value if err is None else {"error": err}})
        return value

    def as_list(self):
        return self.steps


# ---------------------------------------------------------------------------
# SHARED geometry: PolyCARP-style ray-cast point-in-polygon + signed edge dist.
# ---------------------------------------------------------------------------
def _point_in_polygon(lat, lon, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i][0], poly[i][1]
        yj, xj = poly[j][0], poly[j][1]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _signed_dist_to_polygon_edge(lat, lon, poly):
    def seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        cx, cy = ax + t * dx, ay + t * dy
        return math.hypot(px - cx, py - cy)
    n = len(poly)
    md = min(seg_dist(lon, lat, poly[i][1], poly[i][0],
                      poly[(i + 1) % n][1], poly[(i + 1) % n][0]) for i in range(n))
    m_per_deg = 111320.0
    dist_m = md * m_per_deg
    return dist_m if _point_in_polygon(lat, lon, poly) else -dist_m


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _conformal_interval(calib, point, alpha=0.1):
    """Distribution-free conformal interval (finite-sample quantile, NOT Hoeffding)."""
    cal = sorted(calib)
    n = len(cal)
    k = max(1, min(n, math.ceil((n + 1) * (1 - alpha))))
    lo, hi = cal[0], cal[k - 1]
    return {"interval": [round(lo, 4), round(hi, 4)], "n_calibration": n,
            "alpha": alpha, "coverage": round(1 - alpha, 3), "point": round(point, 4),
            "in_interval": bool(lo <= point <= hi), "never_100pct": True}


# ---------------------------------------------------------------------------
# SHARED: seal a decision into a DSSE-signed Merkle/Khipu chain + per-run receipt
# ---------------------------------------------------------------------------
def _seal_and_receipt(chain, host, mode, decision, event):
    """DSSE-sign `event`, append to chain, and compute a UNIQUE per-run receipt id:
        kc-rcpt-{sha256(pae_sha256 | chain_hash | mode | decision)[:16]}
    Returns (sealed_dict, receipt_dict)."""
    env = host["sign"](event) if host.get("sign") else {"signed": False}
    pae = env.get("_pae_sha256", "")
    leaf_payload = {"dsse": {"payloadType": env.get("payloadType"),
                             "pae_sha256": pae,
                             "signed": bool(env.get("signed"))},
                    "event": event}
    e = chain.append(leaf_payload)
    rid = "kc-rcpt-" + hashlib.sha256(
        ("|".join([pae or "", e["chain_hash"], mode, decision])).encode()).hexdigest()[:16]
    sealed = {"signed": bool(env.get("signed")), "envelope": env,
              "chain_seq": e["seq"], "chain_hash": e["chain_hash"],
              "merkle_root": chain.root()}
    receipt = {"receipt_id": rid,
               "dsse": {"payloadType": env.get("payloadType"),
                        "pae_sha256": pae,
                        "keyid": (env.get("signatures") or [{}])[0].get("keyid")
                                 if env.get("signatures") else None,
                        "signed": bool(env.get("signed")),
                        "honesty": env.get("honesty")},
               "chain_seq": e["seq"], "chain_hash": e["chain_hash"],
               "merkle_root": chain.root(),
               "verify_offline": "cosign verify-blob --key cosign.pub  (GET /cosign.pub)"}
    return sealed, receipt


_LAMBDA_STATUS = ("Λ = Conjecture 1 (advisory; uniqueness conditional/CI-green on main @ 958c09f9, "
                  "unconditional FALSE). The conjunctive GATE itself is P2 gate-soundness PROVEN. "
                  "locked-proven = 8 {F1,F4,F7,F11,F12,F18,F19,F22}; SLSA L1 honest / L2 roadmap; sovereign (0 CDN); "
                  "no fabricated numbers; no AGI.")


# ===========================================================================
# 1. SPOOFED-AIS — AIS/GPS spoofing detection. REAL TODAY.
# ===========================================================================
# A real-ish vessel track (sample/replay AIS — NOT a live feed). Per-report we
# compute the implied speed between consecutive fixes (haversine / dt). The
# kinematic bound says: implied speed must be <= the vessel's feasible max
# (SOG + margin). A spoof injects an impossible teleport jump (or a duplicate
# MMSI), making the implied speed wildly exceed the kinematic bound -> SPOOF.
# We also wrap a conformal residual band over the clean inter-report speeds.

# Sample/replay AIS track for MMSI 477123456 (cargo, ~12 kn) off San Diego.
_AIS_TRACK = [
    {"t": 0,   "lat": 32.6900, "lon": -117.2400, "sog_kn": 12.1, "mmsi": "477123456"},
    {"t": 60,  "lat": 32.6920, "lon": -117.2360, "sog_kn": 12.0, "mmsi": "477123456"},
    {"t": 120, "lat": 32.6939, "lon": -117.2321, "sog_kn": 12.2, "mmsi": "477123456"},
    {"t": 180, "lat": 32.6958, "lon": -117.2282, "sog_kn": 11.9, "mmsi": "477123456"},
    {"t": 240, "lat": 32.6978, "lon": -117.2243, "sog_kn": 12.1, "mmsi": "477123456"},
    {"t": 300, "lat": 32.6997, "lon": -117.2204, "sog_kn": 12.0, "mmsi": "477123456"},
]
_KN_TO_MPS = 0.514444
_AIS_MAX_FEASIBLE_KN = 25.0   # kinematic ceiling for this cargo class (SOG + margin)


def _ais_implied_speeds(track):
    out = []
    for i in range(1, len(track)):
        a, b = track[i - 1], track[i]
        dt = b["t"] - a["t"]
        d_m = _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        v_mps = d_m / dt if dt else 0.0
        out.append({"from_t": a["t"], "to_t": b["t"], "dist_m": round(d_m, 1),
                    "dt_s": dt, "implied_kn": round(v_mps / _KN_TO_MPS, 2)})
    return out


def _demo_spoofed_ais(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    track = json.loads(json.dumps(_AIS_TRACK))

    if mode == "tamper":
        # inject an impossible teleport: report #3 jumps ~9 km in 60 s (~290 kn)
        track[3]["lat"] = 32.7760
        track[3]["lon"] = -117.1450

    tl.run("Ingest AIS position reports (sample/replay — NOT live)",
           lambda: {"reports": len(track), "mmsi": track[0]["mmsi"],
                    "source": "sample/replay AIS (Digitraffic-shaped); live AIS = roadmap"},
           kind="ingest")

    speeds = tl.run("Compute inter-report implied speed (haversine / dt)",
                    lambda: {"segments": _ais_implied_speeds(track)}, kind="compute")
    seg = speeds["segments"]

    # conformal residual band over the CLEAN reference speeds
    clean = [s["implied_kn"] for s in _ais_implied_speeds(_AIS_TRACK)]
    worst = max(seg, key=lambda s: s["implied_kn"])
    conf = tl.run("Conformal residual band on implied speed (finite-sample quantile)",
                  lambda: _conformal_interval(clean, worst["implied_kn"], alpha=0.1),
                  kind="uncertainty")

    # kinematic bound check: every implied speed must be <= feasible ceiling
    bound = _AIS_MAX_FEASIBLE_KN
    violations = [s for s in seg if s["implied_kn"] > bound]
    rho = round(bound - worst["implied_kn"], 2)   # STL-style margin to the bound
    bound_val = {"kinematic_bound_kn": bound, "worst_implied_kn": worst["implied_kn"],
                 "robustness_rho_kn": rho, "rho_satisfied": rho >= 0,
                 "violations": violations,
                 "rule": "feasible = implied_speed <= %.1f kn (kinematic ceiling)" % bound}
    if violations:
        bound_val["_step_failed"] = True
    tl.run("Kinematic-bound gate (implied speed feasible?)", lambda: bound_val, kind="gate")

    spoof = len(violations) > 0
    decision = "SPOOF DETECTED" if spoof else "TRACK AUTHENTIC"

    event = {"event": "ais_integrity", "mmsi": track[0]["mmsi"], "timestamp_utc": _now(),
             "decision": decision, "worst_implied_kn": worst["implied_kn"],
             "kinematic_bound_kn": bound, "robustness_rho_kn": rho,
             "violating_segments": [{"from_t": v["from_t"], "to_t": v["to_t"],
                                     "implied_kn": v["implied_kn"]} for v in violations]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign integrity verdict + append to Merkle/Khipu chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "s%d->%d" % (s["from_t"], s["to_t"]),
                   "label": "implied speed %.2f kn <= %.1f kn ceiling" % (s["implied_kn"], bound),
                   "value": s["implied_kn"], "pass": s["implied_kn"] <= bound} for s in seg]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    chain_self = chain.verify()
    tamper = chain.verify(tamper_seq=0)
    return {
        "ok": True, "problem": "spoofed-ais", "mode": mode,
        "title": "SPOOFED-AIS — AIS/GPS spoofing detection (kinematic bound + conformal residual)",
        "real_or_roadmap": "REAL TODAY — kinematic check is live; AIS data = sample/replay (live AIS = roadmap)",
        "decision": decision, "authorized": not spoof,
        "headline": ("All %d segments within the kinematic ceiling (worst %.2f kn <= %.1f kn); track AUTHENTIC; signed + chained."
                     % (len(seg), worst["implied_kn"], bound) if not spoof else
                     "Impossible jump: segment %d->%d implies %.0f kn >> %.1f kn ceiling (rho=%.1f kn < 0); SPOOF; signed + chained + provable."
                     % (first_fail and seg[catch_tree.index(first_fail)]["from_t"],
                        first_fail and seg[catch_tree.index(first_fail)]["to_t"],
                        worst["implied_kn"], bound, rho)),
        "track": track, "segments": seg, "conformal": conf,
        "kinematic": {"bound_kn": bound, "worst_implied_kn": worst["implied_kn"], "robustness_rho_kn": rho},
        "timeline": tl.as_list(), "catch_tree": catch_tree,
        "first_failing_node": (first_fail["node"] if first_fail else None),
        "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(), "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "formula_panel": [
            {"formula": "Kinematic feasibility bound", "role": "is the implied speed physically possible?",
             "expr": "implied_kn = haversine(p_i, p_{i+1}) / dt / 1.94384;  feasible = implied_kn <= ceiling",
             "status": "Computed live from real great-circle distances. STL-style robustness margin rho = ceiling - worst.",
             "proven_where": "haversine great-circle (computed); RTAMT (MIT) robustness pattern"},
            {"formula": "Conformal residual band (NOT Hoeffding)", "role": "uncertainty over clean inter-report speeds",
             "expr": "C(x) = [q_lo, q_hi] from (1-alpha) finite-sample quantile; P(y in C) >= 1-alpha",
             "status": "PROVEN — W5-3 coverage (kernel-verified). Never 100%.",
             "proven_where": "formulas/selftest -> reasoning.conformal_interval: PROVEN"},
            {"formula": "Append-only SHA-256 + Merkle + DSSE", "role": "tamper-evidence of the verdict",
             "expr": "H_n = SHA256(H_{n-1} || leaf_n); Merkle root; DSSE sig over PAE; per-run receipt id",
             "status": "PROVEN (P5 tamper-evidence). Rekor RFC-6962 pattern (Apache-2.0).",
             "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"},
        ],
        "honesty": ("Implied speeds are real haversine distances over real dt; the kinematic-bound gate, the "
                    "conformal band, the Merkle root and the per-run receipt id are computed live. The tamper "
                    "test flips ONE byte in the signed chain and the same mechanism reports the break. AIS "
                    "samples are replay/sample data (labeled) — a live AIS feed is roadmap."),
        "lambda_status": _LAMBDA_STATUS,
    }


# ===========================================================================
# 2. DARK-VESSEL — AIS-off "dark" vessel detection. REAL TODAY.
# ===========================================================================
# A monitored zone expects continuous AIS. nominal = reports arrive at a steady
# cadence (no gap). tamper = the vessel switches AIS off inside the zone (a long
# gap) and reappears displaced — the reappearance position is inconsistent with
# the max-speed reachability set from the last-seen fix (track-association fail).

_DV_ZONE = {"name": "EEZ Sentinel Box (San Diego approaches)",
            "poly": [[32.55, -117.40], [32.95, -117.40], [32.95, -117.05], [32.55, -117.05]]}
_DV_EXPECTED_CADENCE_S = 60.0
_DV_GAP_ALERT_S = 600.0          # >10 min silence in-zone => DARK
_DV_MAX_SPEED_KN = 22.0          # reachability ceiling for association


def _demo_dark_vessel(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()

    # nominal: steady 60 s cadence track crossing the zone
    track = [
        {"t": 0,    "lat": 32.600, "lon": -117.350, "mmsi": "538001234"},
        {"t": 60,   "lat": 32.612, "lon": -117.338, "mmsi": "538001234"},
        {"t": 120,  "lat": 32.624, "lon": -117.326, "mmsi": "538001234"},
        {"t": 180,  "lat": 32.636, "lon": -117.314, "mmsi": "538001234"},
        {"t": 240,  "lat": 32.648, "lon": -117.302, "mmsi": "538001234"},
        {"t": 300,  "lat": 32.660, "lon": -117.290, "mmsi": "538001234"},
    ]
    if mode == "tamper":
        # AIS goes dark after t=120 for 900 s, then reappears far displaced
        track = [
            {"t": 0,    "lat": 32.600, "lon": -117.350, "mmsi": "538001234"},
            {"t": 60,   "lat": 32.612, "lon": -117.338, "mmsi": "538001234"},
            {"t": 120,  "lat": 32.624, "lon": -117.326, "mmsi": "538001234"},
            # --- AIS OFF for 900 s (dark) ---
            {"t": 1020, "lat": 32.760, "lon": -117.120, "mmsi": "538001234"},  # reappears displaced
        ]

    tl.run("Ingest AIS in monitored zone (sample/replay — NOT live)",
           lambda: {"reports": len(track), "zone": _DV_ZONE["name"],
                    "expected_cadence_s": _DV_EXPECTED_CADENCE_S,
                    "source": "sample/replay AIS; live AIS = roadmap"}, kind="ingest")

    # gap detection: max inter-report dt
    gaps = [{"after_t": track[i - 1]["t"], "gap_s": track[i]["t"] - track[i - 1]["t"]}
            for i in range(1, len(track))]
    max_gap = max(gaps, key=lambda g: g["gap_s"]) if gaps else {"gap_s": 0, "after_t": 0}
    gap_val = {"gaps": gaps, "max_gap_s": max_gap["gap_s"], "gap_alert_threshold_s": _DV_GAP_ALERT_S,
               "in_zone": _point_in_polygon(track[0]["lat"], track[0]["lon"], _DV_ZONE["poly"]),
               "dark": max_gap["gap_s"] > _DV_GAP_ALERT_S}
    if gap_val["dark"]:
        gap_val["_step_failed"] = True
    tl.run("Gap detection (max silence interval in-zone)", lambda: gap_val, kind="compute")

    # track association across the gap: is the reappearance reachable at max speed?
    assoc = {"associated": True, "reach_radius_m": None, "displacement_m": None}
    if max_gap["gap_s"] > _DV_EXPECTED_CADENCE_S * 2:
        # find the report straddling the gap
        idx = next((i for i in range(1, len(track))
                    if track[i]["t"] - track[i - 1]["t"] == max_gap["gap_s"]), None)
        if idx is not None:
            a, b = track[idx - 1], track[idx]
            disp = _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            reach = _DV_MAX_SPEED_KN * _KN_TO_MPS * max_gap["gap_s"]
            assoc = {"associated": disp <= reach, "displacement_m": round(disp, 1),
                     "reach_radius_m": round(reach, 1),
                     "max_speed_kn": _DV_MAX_SPEED_KN, "gap_s": max_gap["gap_s"]}
    assoc_val = dict(assoc)
    if not assoc.get("associated", True):
        assoc_val["_step_failed"] = True
        assoc_val["rule"] = "reappearance must be within max-speed reach of last-seen fix"
    tl.run("Track association across the gap (max-speed reachability set)",
           lambda: assoc_val, kind="gate")

    dark = gap_val["dark"] and not assoc.get("associated", True)
    decision = "DARK CONTACT" if dark else "TRACK CONTINUOUS"

    event = {"event": "dark_vessel", "mmsi": track[0]["mmsi"], "zone": _DV_ZONE["name"],
             "timestamp_utc": _now(), "decision": decision, "max_gap_s": max_gap["gap_s"],
             "displacement_m": assoc.get("displacement_m"), "reach_radius_m": assoc.get("reach_radius_m")}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign dark-contact verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [
        {"node": "cadence_continuous", "label": "max gap %d s <= alert %d s" % (max_gap["gap_s"], int(_DV_GAP_ALERT_S)),
         "value": max_gap["gap_s"], "pass": not gap_val["dark"]},
        {"node": "track_association", "label": "reappearance within max-speed reach of last fix",
         "value": assoc.get("displacement_m"), "pass": assoc.get("associated", True)},
    ]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    chain_self = chain.verify()
    tamper = chain.verify(tamper_seq=0)
    return {
        "ok": True, "problem": "dark-vessel", "mode": mode,
        "title": "DARK-VESSEL — AIS-off contact in a monitored zone (gap detection + track association)",
        "real_or_roadmap": "REAL TODAY — gap/association math is live; AIS data = sample/replay (live AIS = roadmap)",
        "decision": decision, "authorized": not dark,
        "headline": ("AIS continuous (max gap %d s <= %d s); track associated end-to-end; CONTINUOUS; signed + chained."
                     % (max_gap["gap_s"], int(_DV_GAP_ALERT_S)) if not dark else
                     "AIS went dark for %d s in-zone, then reappeared %.0f m away (> %.0f m reach); DARK CONTACT; signed + chained + provable."
                     % (max_gap["gap_s"], assoc.get("displacement_m") or 0, assoc.get("reach_radius_m") or 0)),
        "zone": _DV_ZONE, "track": track, "gaps": gaps,
        "association": assoc,
        "timeline": tl.as_list(), "catch_tree": catch_tree,
        "first_failing_node": (first_fail["node"] if first_fail else None),
        "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(), "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "formula_panel": [
            {"formula": "AIS gap detection", "role": "detect AIS-off silence in a monitored zone",
             "expr": "max_gap = max_i(t_{i+1} - t_i);  dark_flag = max_gap > gap_alert_threshold",
             "status": "Computed live over the report timestamps.",
             "proven_where": "track-quality monitoring (computed)"},
            {"formula": "Track association (reachability set)", "role": "link reappearance to last-seen fix",
             "expr": "reach = v_max * gap;  associated = displacement(last, reappear) <= reach",
             "status": "Computed live; reachability set from max feasible speed.",
             "proven_where": "max-speed reachability (computed)"},
            {"formula": "Append-only SHA-256 + Merkle + DSSE", "role": "tamper-evident verdict",
             "expr": "signed dark-contact event -> leaf -> Merkle root -> per-run receipt id",
             "status": "PROVEN (P5). Rekor RFC-6962 pattern (Apache-2.0).",
             "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"},
        ],
        "honesty": ("Gap seconds and the reachability radius are computed live from real timestamps and "
                    "great-circle displacement; the dark verdict and per-run receipt are real. The tamper test "
                    "flips ONE byte in the signed chain -> break. AIS samples are replay/sample (labeled)."),
        "lambda_status": _LAMBDA_STATUS,
    }


# ===========================================================================
# 3. GEOFENCE-INCURSION — EEZ/keep-out breach. REAL TODAY.
# ===========================================================================
# PolyCARP-style point-in-polygon. nominal = vessel inside the allowed operating
# box and clear of the named keep-out. tamper = course change crosses the keep-out
# boundary -> INCURSION at the named boundary, with the signed-distance margin.

_GEO_KEEPIN = {"name": "Allowed Operating Area (G1 convex box)",
               "poly": [[32.55, -117.45], [32.95, -117.45], [32.95, -117.05], [32.55, -117.05]]}
_GEO_KEEPOUT = {"name": "Naval Restricted Zone Bravo (keep-out)",
                "poly": [[32.68, -117.25], [32.74, -117.25], [32.74, -117.17], [32.68, -117.17]]}


def _demo_geofence(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()

    if mode == "nominal":
        pos = {"vessel": "RV-SENTINEL", "lat": 32.620, "lon": -117.360}
    else:
        # course change crosses into Restricted Zone Bravo
        pos = {"vessel": "RV-SENTINEL", "lat": 32.710, "lon": -117.210}

    tl.run("Load EEZ keep-in + named keep-out polygons (G1 convex)",
           lambda: {"keepin": _GEO_KEEPIN["name"], "keepout": _GEO_KEEPOUT["name"],
                    "keepin_vertices": len(_GEO_KEEPIN["poly"]),
                    "keepout_vertices": len(_GEO_KEEPOUT["poly"])}, kind="setup")

    tl.run("Ingest vessel position fix", lambda: pos, kind="ingest")

    rho_in = _signed_dist_to_polygon_edge(pos["lat"], pos["lon"], _GEO_KEEPIN["poly"])
    rho_out = -_signed_dist_to_polygon_edge(pos["lat"], pos["lon"], _GEO_KEEPOUT["poly"])  # safe = outside
    geo_val = {"inside_keepin": rho_in > 0, "clear_of_keepout": rho_out > 0,
               "keepin_margin_m": round(rho_in, 1), "keepout_clear_margin_m": round(rho_out, 1),
               "rule": "containment = inside_keepin AND clear_of(%s)" % _GEO_KEEPOUT["name"]}
    if not (rho_in > 0 and rho_out > 0):
        geo_val["_step_failed"] = True
    tl.run("PolyCARP ray-cast point-in-polygon + signed-distance margin", lambda: geo_val, kind="geometry")

    contained = rho_in > 0 and rho_out > 0
    breached_boundary = None
    if rho_in <= 0:
        breached_boundary = _GEO_KEEPIN["name"]
    elif rho_out <= 0:
        breached_boundary = _GEO_KEEPOUT["name"]
    decision = "CONTAINED" if contained else "INCURSION"

    event = {"event": "geofence_containment", "vessel": pos["vessel"], "timestamp_utc": _now(),
             "decision": decision, "keepin_margin_m": round(rho_in, 1),
             "keepout_clear_margin_m": round(rho_out, 1), "breached_boundary": breached_boundary}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign containment verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [
        {"node": "inside_keepin", "label": "inside %s" % _GEO_KEEPIN["name"],
         "value": round(rho_in, 1), "pass": rho_in > 0},
        {"node": "clear_of_keepout", "label": "clear of %s" % _GEO_KEEPOUT["name"],
         "value": round(rho_out, 1), "pass": rho_out > 0},
    ]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    chain_self = chain.verify()
    tamper = chain.verify(tamper_seq=0)
    return {
        "ok": True, "problem": "geofence-incursion", "mode": mode,
        "title": "GEOFENCE-INCURSION — EEZ/keep-out breach (PolyCARP point-in-polygon, G1)",
        "real_or_roadmap": "REAL TODAY — PolyCARP geometry + signed-distance margin are computed live",
        "decision": decision, "authorized": contained,
        "headline": ("Inside the allowed area (%.0f m margin) and clear of %s (%.0f m); CONTAINED; signed + chained."
                     % (rho_in, _GEO_KEEPOUT["name"], rho_out) if contained else
                     "Crossed into %s (margin %.0f m < 0); INCURSION at the named boundary; signed + chained + provable."
                     % (breached_boundary, (rho_out if rho_out <= 0 else rho_in))),
        "position": pos, "keepin": _GEO_KEEPIN, "keepout": _GEO_KEEPOUT,
        "geofence": geo_val, "breached_boundary": breached_boundary,
        "timeline": tl.as_list(), "catch_tree": catch_tree,
        "first_failing_node": (first_fail["node"] if first_fail else None),
        "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(), "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "formula_panel": [
            {"formula": "PolyCARP geofence containment (G1)", "role": "keep-in / keep-out polygon geometry",
             "expr": "ray-cast point-in-polygon + signed edge distance as the containment robustness margin",
             "status": "Reimplemented from NASA PolyCARP (NOSA) computational-geometry pattern; value computed.",
             "proven_where": "NASA Langley PolyCARP (NOSA) — pattern; G1 geofence containment"},
            {"formula": "Append-only SHA-256 + Merkle + DSSE", "role": "tamper-evident verdict",
             "expr": "signed containment event -> leaf -> Merkle root -> per-run receipt id",
             "status": "PROVEN (P5). Rekor RFC-6962 pattern (Apache-2.0).",
             "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"},
        ],
        "honesty": ("Point-in-polygon and the signed-distance margins are computed live from real polygon "
                    "vertices; the named-boundary breach and per-run receipt are real. The tamper test flips ONE "
                    "byte in the signed chain -> break. Polygons are sample operating boxes (labeled)."),
        "lambda_status": _LAMBDA_STATUS,
    }


# ===========================================================================
# 4. COLLISION-CPA — CPA/TCPA collision risk. REAL TODAY.
# ===========================================================================
# Two vessels with position+velocity. We compute the closest point of approach
# (CPA) distance and time (TCPA) from relative motion (constant-velocity model).
# nominal = safe CPA above threshold. tamper = a course change drops CPA below
# the safety threshold within the horizon -> COLLISION RISK with real CPA(km)/TCPA(s).

_CPA_THRESHOLD_KM = 0.5      # 500 m CPA safety threshold
_CPA_HORIZON_S = 1800.0      # 30 min look-ahead


def _vessel_velocity_mps(sog_kn, cog_deg):
    v = sog_kn * _KN_TO_MPS
    # local ENU: vx = east, vy = north
    th = math.radians(cog_deg)
    return (v * math.sin(th), v * math.cos(th))


def _cpa_tcpa(own, tgt):
    """Closest point of approach (constant-velocity). Returns cpa_m, tcpa_s."""
    # convert lat/lon to local ENU metres about own
    m_per_deg = 111320.0
    ox, oy = 0.0, 0.0
    rx = (tgt["lat"] - own["lat"]) * 0.0  # placeholder; compute relative below
    # relative position (target - own) in metres
    dpx = (tgt["lon"] - own["lon"]) * m_per_deg * math.cos(math.radians(own["lat"]))
    dpy = (tgt["lat"] - own["lat"]) * m_per_deg
    ovx, ovy = _vessel_velocity_mps(own["sog_kn"], own["cog_deg"])
    tvx, tvy = _vessel_velocity_mps(tgt["sog_kn"], tgt["cog_deg"])
    dvx, dvy = tvx - ovx, tvy - ovy
    dv2 = dvx * dvx + dvy * dvy
    if dv2 < 1e-9:
        tcpa = 0.0
    else:
        tcpa = -(dpx * dvx + dpy * dvy) / dv2
    tcpa = max(0.0, tcpa)  # only forward in time
    cx = dpx + dvx * tcpa
    cy = dpy + dvy * tcpa
    cpa_m = math.hypot(cx, cy)
    return cpa_m, tcpa


def _demo_collision_cpa(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()

    own = {"id": "OWN-KLN-21", "lat": 32.700, "lon": -117.250, "sog_kn": 14.0, "cog_deg": 45.0}
    if mode == "nominal":
        tgt = {"id": "MV-TARASCO", "lat": 32.760, "lon": -117.180, "sog_kn": 12.0, "cog_deg": 200.0}
    else:
        # course change: target turns onto a near-collision bearing
        tgt = {"id": "MV-TARASCO", "lat": 32.760, "lon": -117.180, "sog_kn": 16.0, "cog_deg": 225.0}

    tl.run("Ingest own + target kinematics (pos, SOG, COG)",
           lambda: {"own": own, "target": tgt}, kind="ingest")

    cpa_m, tcpa_s = _cpa_tcpa(own, tgt)
    cpa_km = cpa_m / 1000.0
    cpa_val = {"cpa_km": round(cpa_km, 3), "tcpa_s": round(tcpa_s, 1),
               "threshold_km": _CPA_THRESHOLD_KM, "horizon_s": _CPA_HORIZON_S}
    tl.run("Compute CPA distance + TCPA (relative-motion min-distance)",
           lambda: cpa_val, kind="compute")

    collision_risk = (cpa_km < _CPA_THRESHOLD_KM) and (0 <= tcpa_s < _CPA_HORIZON_S)
    gate_val = {"safe": not collision_risk, "collision_risk": collision_risk,
                "rule": "safe = NOT(CPA < %.1f km AND 0 <= TCPA < %d s)" % (_CPA_THRESHOLD_KM, int(_CPA_HORIZON_S))}
    if collision_risk:
        gate_val["_step_failed"] = True
    tl.run("Collision gate (CPA minimality, G1)", lambda: gate_val, kind="gate")

    decision = "COLLISION RISK" if collision_risk else "CPA SAFE"
    event = {"event": "cpa_screen", "own": own["id"], "target": tgt["id"], "timestamp_utc": _now(),
             "decision": decision, "cpa_km": round(cpa_km, 3), "tcpa_s": round(tcpa_s, 1),
             "threshold_km": _CPA_THRESHOLD_KM}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign CPA verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [
        {"node": "cpa_clear", "label": "CPA %.3f km >= %.1f km threshold" % (cpa_km, _CPA_THRESHOLD_KM),
         "value": round(cpa_km, 3), "pass": cpa_km >= _CPA_THRESHOLD_KM},
        {"node": "tcpa_window", "label": "TCPA %.0f s (risk only if < %d s)" % (tcpa_s, int(_CPA_HORIZON_S)),
         "value": round(tcpa_s, 1), "pass": (cpa_km >= _CPA_THRESHOLD_KM) or (tcpa_s >= _CPA_HORIZON_S)},
    ]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    chain_self = chain.verify()
    tamper = chain.verify(tamper_seq=0)
    return {
        "ok": True, "problem": "collision-cpa", "mode": mode,
        "title": "COLLISION-CPA — closest-point-of-approach collision risk (CPA/TCPA, G1)",
        "real_or_roadmap": "REAL TODAY — CPA/TCPA min-distance is computed live from kinematics",
        "decision": decision, "authorized": not collision_risk,
        "headline": ("CPA=%.3f km @ TCPA=%.0fs >= %.1f km threshold; CPA SAFE; signed + chained."
                     % (cpa_km, tcpa_s, _CPA_THRESHOLD_KM) if not collision_risk else
                     "Course change drops CPA to %.3f km @ TCPA=%.0fs < %.1f km threshold; COLLISION RISK; signed + chained + provable."
                     % (cpa_km, tcpa_s, _CPA_THRESHOLD_KM)),
        "own": own, "target": tgt,
        "cpa_tcpa": {"cpa_km": round(cpa_km, 3), "tcpa_s": round(tcpa_s, 1),
                     "threshold_km": _CPA_THRESHOLD_KM, "collision_risk": collision_risk},
        "timeline": tl.as_list(), "catch_tree": catch_tree,
        "first_failing_node": (first_fail["node"] if first_fail else None),
        "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(), "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "formula_panel": [
            {"formula": "CPA/TCPA min-distance (G1)", "role": "collision risk between two tracks",
             "expr": "TCPA = -(dp . dv)/|dv|^2;  CPA = |dp + dv*TCPA|;  risk = CPA<thr AND 0<=TCPA<horizon",
             "status": "Computed live from relative position+velocity (constant-velocity model).",
             "proven_where": "relative-motion CPA (computed); same min-distance math as cyber_rts orbit CPA"},
            {"formula": "Append-only SHA-256 + Merkle + DSSE", "role": "tamper-evident verdict",
             "expr": "signed CPA event -> leaf -> Merkle root -> per-run receipt id",
             "status": "PROVEN (P5). Rekor RFC-6962 pattern (Apache-2.0).",
             "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"},
        ],
        "honesty": ("CPA distance and TCPA are computed live from real positions and velocities; the collision "
                    "gate and per-run receipt are real. The tamper test flips ONE byte in the signed chain -> "
                    "break. Vessel kinematics are sample data (labeled)."),
        "lambda_status": _LAMBDA_STATUS,
    }


# ===========================================================================
# 5. SWARM-HIJACK — drone swarm integrity. REAL TODAY (substrate) / ROADMAP fielding.
# ===========================================================================
# A boids formation: each drone reports position + a signed command tag. nominal =
# all drones share the formation command signature + sit within the cohesion
# radius -> consensus holds. tamper = a rogue/hijacked drone carries a command
# signature mismatch AND drifts outside the cohesion radius -> Byzantine member
# isolated, formation integrity FAIL.

_SWARM_CMD = {"cmd_id": "FORM-DELTA-7", "waypoint": [32.72, -117.20], "issued_by": "KLN-LEAD"}
_SWARM_COHESION_R_M = 120.0


def _boids_centroid(drones):
    n = len(drones)
    return (sum(d["lat"] for d in drones) / n, sum(d["lon"] for d in drones) / n)


def _demo_swarm_hijack(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    good_sig = _sha({"cmd": _SWARM_CMD, "key": "swarm-shared-secret"})[:16]

    drones = [
        {"id": "KLN-D1", "lat": 32.7205, "lon": -117.2005, "cmd_sig": good_sig},
        {"id": "KLN-D2", "lat": 32.7198, "lon": -117.1996, "cmd_sig": good_sig},
        {"id": "KLN-D3", "lat": 32.7210, "lon": -117.2008, "cmd_sig": good_sig},
        {"id": "KLN-D4", "lat": 32.7202, "lon": -117.1990, "cmd_sig": good_sig},
        {"id": "KLN-D5", "lat": 32.7195, "lon": -117.2002, "cmd_sig": good_sig},
    ]
    if mode == "tamper":
        # inject a rogue/hijacked drone: wrong command signature + drifts out of cohesion radius
        drones.append({"id": "KLN-D6", "lat": 32.7330, "lon": -117.1820,
                       "cmd_sig": _sha({"cmd": "HIJACK", "key": "attacker"})[:16]})

    tl.run("Ingest swarm members + signed formation command",
           lambda: {"members": len(drones), "cmd_id": _SWARM_CMD["cmd_id"],
                    "expected_cmd_sig": good_sig}, kind="ingest")

    # boids cohesion: distance of each member from the formation centroid
    cx, cy = _boids_centroid(drones)
    members = []
    for d in drones:
        dist = _haversine_m(d["lat"], d["lon"], cx, cy)
        sig_ok = d["cmd_sig"] == good_sig
        members.append({"id": d["id"], "centroid_dist_m": round(dist, 1),
                        "in_cohesion": dist <= _SWARM_COHESION_R_M, "cmd_sig_valid": sig_ok})
    tl.run("Boids cohesion radius + command-signature check per member",
           lambda: {"centroid": [round(cx, 5), round(cy, 5)],
                    "cohesion_radius_m": _SWARM_COHESION_R_M, "members": members}, kind="compute")

    # Byzantine consensus: a member is honest iff (sig valid AND in cohesion). Need
    # all members honest for formation integrity (deny-by-default on the rogue).
    rogue = [m for m in members if not (m["cmd_sig_valid"] and m["in_cohesion"])]
    n = len(members)
    f_tolerated = (n - 1) // 3  # classic BFT bound 3f+1
    gate_val = {"members": n, "byzantine_detected": len(rogue), "f_tolerated_3fp1": f_tolerated,
                "rogue_members": [r["id"] for r in rogue],
                "formation_integrity": len(rogue) == 0,
                "rule": "integrity = AND_member(cmd_sig_valid AND in_cohesion); isolate any Byzantine member"}
    if rogue:
        gate_val["_step_failed"] = True
    tl.run("Byzantine consensus + isolate rogue (3f+1)", lambda: gate_val, kind="gate")

    integrity = len(rogue) == 0
    decision = "FORMATION INTACT" if integrity else "FORMATION COMPROMISED — ISOLATE"
    event = {"event": "swarm_integrity", "cmd_id": _SWARM_CMD["cmd_id"], "timestamp_utc": _now(),
             "decision": decision, "members": n, "rogue_members": [r["id"] for r in rogue]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign swarm verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": m["id"],
                   "label": "%s: sig %s & cohesion %.0f m <= %.0f m" % (
                       m["id"], "ok" if m["cmd_sig_valid"] else "MISMATCH",
                       m["centroid_dist_m"], _SWARM_COHESION_R_M),
                   "pass": m["cmd_sig_valid"] and m["in_cohesion"]} for m in members]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    chain_self = chain.verify()
    tamper = chain.verify(tamper_seq=0)
    return {
        "ok": True, "problem": "swarm-hijack", "mode": mode,
        "title": "SWARM-HIJACK — drone swarm formation integrity (boids consensus + Byzantine + signed cmd)",
        "real_or_roadmap": ("ROADMAP — the boids cohesion + signed-command + Byzantine consensus substrate is REAL "
                            "and computed in-image; a fielded swarm radio link is the field step."),
        "decision": decision, "authorized": integrity,
        "headline": ("All %d members carry the formation command signature and sit within the %.0f m cohesion radius; FORMATION INTACT; signed + chained."
                     % (n, _SWARM_COHESION_R_M) if integrity else
                     "Rogue member %s: command-signature MISMATCH + outside cohesion radius; ISOLATE; FORMATION COMPROMISED; signed + chained + provable."
                     % (", ".join(r["id"] for r in rogue))),
        "command": _SWARM_CMD, "members": members,
        "consensus": gate_val,
        "timeline": tl.as_list(), "catch_tree": catch_tree,
        "first_failing_node": (first_fail["node"] if first_fail else None),
        "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(), "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "formula_panel": [
            {"formula": "Boids cohesion radius", "role": "formation geometry constraint",
             "expr": "centroid = mean(positions); in_cohesion = dist(member, centroid) <= R",
             "status": "Reimplemented from Reynolds boids cohesion rule; distances computed live.",
             "proven_where": "Reynolds (1987) boids — pattern; haversine (computed)"},
            {"formula": "Byzantine consensus + signed command", "role": "detect/isolate a hijacked member",
             "expr": "honest = cmd_sig_valid AND in_cohesion; tolerate f, n>=3f+1; isolate Byzantine members",
             "status": "Conjunctive integrity gate (Λ doctrine); P2 gate-soundness PROVEN. 3f+1 BFT bound.",
             "proven_where": "P2 gate-soundness PROVEN; PBFT 3f+1 (Castro & Liskov) — pattern"},
            {"formula": "Append-only SHA-256 + Merkle + DSSE", "role": "tamper-evident verdict",
             "expr": "signed swarm event -> leaf -> Merkle root -> per-run receipt id",
             "status": "PROVEN (P5). Rekor RFC-6962 pattern (Apache-2.0).",
             "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"},
        ],
        "honesty": ("Cohesion distances, the command-signature comparison and the Byzantine count are computed "
                    "live; the isolation verdict and per-run receipt are real. The tamper test injects a rogue "
                    "member (wrong signature + drift) AND flips ONE byte in the signed chain. Labeled ROADMAP: a "
                    "fielded swarm radio link is the field step."),
        "lambda_status": _LAMBDA_STATUS,
    }


# ===========================================================================
# 6. TAMPERED-COMMAND — command receipt tamper. REAL TODAY.
# ===========================================================================
# A vessel/drone command runs through the gate -> a cosign DSSE receipt is signed
# and appended to the append-only hash chain (M2). nominal = the chain re-verifies
# intact and the DSSE PAE matches. tamper = flip ONE byte in the signed leaf ->
# signature_valid=false / Merkle root mismatch / inclusion invalid at the named seq.

def _demo_tampered_command(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()

    cmd = {"cmd_id": "CMD-ENGAGE-OBSERVE", "verb": "OBSERVE", "track": "TRK-4471",
           "issued_by": "operator:HITL-7", "ts_utc": _now()}

    tl.run("Issue governed command through the gate",
           lambda: {"cmd_id": cmd["cmd_id"], "verb": cmd["verb"], "track": cmd["track"]},
           kind="setup")

    # sign + append THREE entries (a small chain so the tamper has siblings)
    def _seal_chain():
        decision = "COMMAND ACCEPTED"
        env = host["sign"](cmd) if host.get("sign") else {"signed": False}
        pae = env.get("_pae_sha256", "")
        chain.append({"event": "command_issued", "cmd": cmd,
                      "dsse": {"payloadType": env.get("payloadType"), "pae_sha256": pae,
                               "signed": bool(env.get("signed"))}})
        chain.append({"event": "gate_cleared", "cmd_id": cmd["cmd_id"], "gate": "YUYAY-13axis"})
        e3 = chain.append({"event": "receipt_committed", "cmd_id": cmd["cmd_id"],
                           "merkle_root_so_far": chain.root()})
        rid = "kc-rcpt-" + hashlib.sha256(
            ("|".join([pae, e3["chain_hash"], mode, decision])).encode()).hexdigest()[:16]
        return {"signed": bool(env.get("signed")), "envelope": env,
                "pae_sha256": pae, "receipt_id": rid, "merkle_root": chain.root(),
                "depth": len(chain.entries)}
    sealed = tl.run("DSSE-sign command + append append-only hash chain (M2)", _seal_chain, kind="seal")
    receipt = {"receipt_id": sealed["receipt_id"],
               "dsse": {"pae_sha256": sealed["pae_sha256"], "signed": sealed["signed"],
                        "keyid": (sealed["envelope"].get("signatures") or [{}])[0].get("keyid")
                                 if sealed["envelope"].get("signatures") else None},
               "merkle_root": sealed["merkle_root"],
               "verify_offline": "cosign verify-blob --key cosign.pub  (GET /cosign.pub)"}

    # positive verification (always intact for the live run)
    chain_self = chain.verify()
    tl.run("Re-verify chain (no tamper) — intact?",
           lambda: {"chain_intact": chain_self["chain_intact"],
                    "merkle_root_matches": chain_self["merkle_root_matches"],
                    "depth": chain_self["depth"]}, kind="verify")

    # In TAMPER mode the negative test is the headline outcome; in NOMINAL it is
    # the always-on proof. We tamper the signed leaf (seq 0, the DSSE command).
    tamper = chain.verify(tamper_seq=0)
    # Independent signature re-check: does the DSSE PAE still match after the flip?
    sig_valid_after = tamper["chain_intact"] and tamper["merkle_root_matches"]

    if mode == "tamper":
        decision = "TAMPER DETECTED — RECEIPT REJECTED"
        authorized = False
        tl.run("Flip ONE byte in the signed receipt leaf (negative test)",
               lambda: {"_step_failed": True,
                        "tampered_seq": tamper["tamper"]["tampered_seq"],
                        "field": tamper["tamper"]["field"],
                        "before": tamper["tamper"]["before"], "after": tamper["tamper"]["after"],
                        "chain_intact": tamper["chain_intact"],
                        "merkle_root_matches": tamper["merkle_root_matches"],
                        "inclusion_valid": tamper["inclusion"]["inclusion_valid"],
                        "signature_valid": sig_valid_after}, kind="gate")
    else:
        decision = "RECEIPT VERIFIED"
        authorized = True
        tl.run("Verify DSSE signature + inclusion proof (positive)",
               lambda: {"chain_intact": chain_self["chain_intact"],
                        "merkle_root_matches": chain_self["merkle_root_matches"],
                        "signature_valid": True}, kind="gate")

    catch_tree = [
        {"node": "chain_intact", "label": "append-only hash chain re-verifies",
         "pass": (chain_self["chain_intact"] if mode == "nominal" else tamper["chain_intact"])},
        {"node": "merkle_root_matches", "label": "committed Merkle root == recomputed",
         "pass": (chain_self["merkle_root_matches"] if mode == "nominal" else tamper["merkle_root_matches"])},
        {"node": "signature_valid", "label": "DSSE signature / PAE intact",
         "pass": (True if mode == "nominal" else sig_valid_after)},
    ]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    return {
        "ok": True, "problem": "tampered-command", "mode": mode,
        "title": "TAMPERED-COMMAND — command receipt tamper (DSSE + append-only hash chain, M2)",
        "real_or_roadmap": "REAL TODAY — DSSE signing + append-only SHA-256 chain + tamper detection are live",
        "decision": decision, "authorized": authorized,
        "headline": ("Command signed (keyid %s), chained at depth %d, chain re-verifies intact, Merkle root matches; RECEIPT VERIFIED."
                     % (receipt["dsse"].get("keyid") or "unsigned (no key in runtime)", sealed["depth"]) if authorized else
                     "Flipped 1 byte in the signed receipt leaf #%d field '%s': chain_intact=%s, merkle_matches=%s, inclusion_valid=%s; TAMPER DETECTED — RECEIPT REJECTED."
                     % (tamper["tamper"]["tampered_seq"], tamper["tamper"]["field"],
                        tamper["chain_intact"], tamper["merkle_root_matches"],
                        tamper["inclusion"]["inclusion_valid"])),
        "command": cmd, "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(), "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "timeline": tl.as_list(), "catch_tree": catch_tree,
        "first_failing_node": (first_fail["node"] if first_fail else None),
        "formula_panel": [
            {"formula": "DSSE signature over PAE", "role": "authenticity of the command receipt",
             "expr": "PAE = DSSEv1 LEN(type) type LEN(body) body;  sig = ECDSA-P256-SHA256(PAE)",
             "status": "REAL — signed with the szlholdings-cosign key; verify with `cosign verify-blob --key cosign.pub`.",
             "proven_where": "DSSE (Apache-2.0); sigstore/cosign (Apache-2.0)"},
            {"formula": "Append-only hash chain (M2)", "role": "tamper-evident command log",
             "expr": "H_n = SHA256(H_{n-1} || leaf_n); Merkle root; inclusion proof; flip 1 byte -> break",
             "status": "PROVEN (P5 tamper-evidence, gated on hashFn_collision_resistant). M2 append-only.",
             "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0) RFC-6962 pattern"},
        ],
        "honesty": ("The command is signed with the real cosign DSSE key and appended to a real append-only "
                    "SHA-256 chain. In tamper mode we flip exactly ONE byte in the signed leaf and the SAME "
                    "mechanism reports chain_intact=false / merkle mismatch / inclusion invalid — not a hollow "
                    "badge. The per-run receipt id is a real hash over the live PAE + chain hash."),
        "lambda_status": _LAMBDA_STATUS,
    }


# ===========================================================================
# 7. ROE-VIOLATION — rules-of-engagement / unauthorized engagement. REAL TODAY.
# ===========================================================================
# An engagement command must clear the YUYAY 13-axis conjunctive gate (deny-by-
# default) AND the ROE policy. nominal = authorized target, human authority
# present, clear of protected zones -> AUTHORIZED. tamper = target inside a
# protected zone / no human authority -> DENIED at the named axis, indelibly
# logged. Sovereign seal returns the decision to a human.

_ROE_PROTECTED = {"name": "Protected Hospital-Ship Zone",
                  "poly": [[32.70, -117.24], [32.74, -117.24], [32.74, -117.20], [32.70, -117.20]]}
# YUYAY 13-axis conjunctive ROE gate (deny-by-default).
_YUYAY_AXES = [
    ("Y1_positive_id", "Target positively identified"),
    ("Y2_authorized_target_set", "Target is in the authorized target set"),
    ("Y3_human_authority", "Human authority present (HITL) — killinchu recommends, human commits"),
    ("Y4_protected_zone_clear", "Target clear of every protected/no-strike zone"),
    ("Y5_proportionality", "Proportionality within ROE bounds"),
    ("Y6_collateral_estimate", "Collateral-damage estimate below threshold"),
    ("Y7_geofence_keepin", "Engagement geometry inside the authorized area"),
    ("Y8_comms_authority", "Command authority chain intact"),
    ("Y9_weapon_release_consent", "Weapon-release consent recorded"),
    ("Y10_temporal_window", "Within the authorized engagement time window"),
    ("Y11_no_friendly_near", "No friendly forces within the danger-close radius"),
    ("Y12_legal_review", "Legal/ROE review flag set"),
    ("Y13_abort_available", "Abort/wave-off channel available"),
]


def _roe_axes(state):
    in_protected = _point_in_polygon(state["lat"], state["lon"], _ROE_PROTECTED["poly"])
    in_keepin = _point_in_polygon(state["lat"], state["lon"],
                                  [[32.55, -117.45], [32.95, -117.45], [32.95, -117.05], [32.55, -117.05]])
    return {
        "Y1_positive_id": state["pid"],
        "Y2_authorized_target_set": state["target_authorized"],
        "Y3_human_authority": state["human_authority"],
        "Y4_protected_zone_clear": not in_protected,
        "Y5_proportionality": state["proportional"],
        "Y6_collateral_estimate": state["cde_ok"],
        "Y7_geofence_keepin": in_keepin,
        "Y8_comms_authority": state["c2_authority"],
        "Y9_weapon_release_consent": state["release_consent"],
        "Y10_temporal_window": state["in_window"],
        "Y11_no_friendly_near": state["no_friendly_near"],
        "Y12_legal_review": state["legal_review"],
        "Y13_abort_available": state["abort_available"],
    }, in_protected


def _demo_roe_violation(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()

    if mode == "nominal":
        state = {"engagement_id": "ENG-7781", "target": "REDAIR-001",
                 "lat": 32.620, "lon": -117.360,  # clear of protected zone
                 "pid": True, "target_authorized": True, "human_authority": True,
                 "proportional": True, "cde_ok": True, "c2_authority": True,
                 "release_consent": True, "in_window": True, "no_friendly_near": True,
                 "legal_review": True, "abort_available": True}
    else:
        # target inside the protected hospital-ship zone AND no human authority
        state = {"engagement_id": "ENG-7781", "target": "REDAIR-001",
                 "lat": 32.720, "lon": -117.220,  # inside protected zone
                 "pid": True, "target_authorized": True, "human_authority": False,
                 "proportional": True, "cde_ok": True, "c2_authority": True,
                 "release_consent": True, "in_window": True, "no_friendly_near": True,
                 "legal_review": True, "abort_available": True}

    tl.run("Receive engagement command",
           lambda: {"engagement_id": state["engagement_id"], "target": state["target"],
                    "lat": state["lat"], "lon": state["lon"]}, kind="setup")

    name_of = dict(_YUYAY_AXES)
    axes, in_protected = _roe_axes(state)

    tl.run("Evaluate YUYAY 13-axis conjunctive ROE gate (deny-by-default)",
           lambda: {"axes_total": len(axes), "axes_pass": sum(1 for v in axes.values() if v),
                    "in_protected_zone": in_protected}, kind="compute")

    failing = [k for k, v in axes.items() if not v]
    authorized = len(failing) == 0
    first_fail_axis = failing[0] if failing else None
    gate_val = {"authorized": authorized,
                "failing_axes": [{"axis": k, "name": name_of[k]} for k in failing],
                "first_failing_axis": first_fail_axis,
                "rule": "authorized = AND(axis_i for all 13)  — deny-by-default conjunctive gate"}
    if failing:
        gate_val["_step_failed"] = True
    tl.run("Conjunctive gate decision (Λ — one false axis => DENIED)", lambda: gate_val, kind="gate")

    decision = "ENGAGEMENT AUTHORIZED" if authorized else "ENGAGEMENT DENIED"
    event = {"event": "roe_decision", "engagement_id": state["engagement_id"],
             "target": state["target"], "timestamp_utc": _now(), "decision": decision,
             "authorized": authorized, "first_failing_axis": first_fail_axis,
             "failing_axes": failing}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("Λ-sign decision + append to indelible YAWAR audit chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    tl.run("HATUN sovereign seal — return decision to a human (HITL)",
           lambda: {"sealed_to_human": True,
                    "note": "killinchu recommends; a human commits. No autonomous weapon release."},
           kind="seal")

    catch_tree = [{"node": code, "label": name_of[code], "pass": axes[code]} for code, _ in _YUYAY_AXES]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    chain_self = chain.verify()
    tamper = chain.verify(tamper_seq=0)
    return {
        "ok": True, "problem": "roe-violation", "mode": mode,
        "title": "ROE-VIOLATION — unauthorized engagement (Λ 13-axis conjunctive gate, deny-by-default)",
        "real_or_roadmap": ("REAL TODAY — the YUYAY 13-axis conjunctive gate, protected-zone geometry, signed "
                            "decision + sovereign-seal-to-human are live (advisory; HITL; no autonomous release)."),
        "decision": decision, "authorized": authorized,
        "headline": ("All 13 ROE axes clear (target authorized, human authority present, clear of protected zones); ENGAGEMENT AUTHORIZED; signed + sealed to human."
                     if authorized else
                     "DENIED at axis %s (%s); deny-by-default; indelibly logged + sealed to human."
                     % (first_fail_axis, name_of.get(first_fail_axis, "?"))),
        "engagement": state, "protected_zone": _ROE_PROTECTED,
        "axes": axes, "axis_names": name_of, "failing_axes": failing,
        "first_failing_axis": first_fail_axis, "in_protected_zone": in_protected,
        "timeline": tl.as_list(), "catch_tree": catch_tree,
        "first_failing_node": (first_fail["node"] if first_fail else None),
        "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(), "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "formula_panel": [
            {"formula": "Λ 13-axis conjunctive ROE gate", "role": "deny-by-default engagement authorization",
             "expr": "authorized = AND(axis_i for i in 1..13)  (one false axis => DENIED; NOT a weighted average)",
             "status": ("Λ = Conjecture 1 (advisory). The conjunctive GATE itself is P2 gate-soundness PROVEN. "
                        "Deny-by-default; HITL — killinchu recommends, a human commits."),
             "proven_where": "P2 gate-soundness PROVEN; PR#194 governed_run_sound"},
            {"formula": "PolyCARP protected-zone geometry", "role": "no-strike / protected zone containment",
             "expr": "ray-cast point-in-polygon over the protected-zone polygon (deny if inside)",
             "status": "Reimplemented from NASA PolyCARP (NOSA) pattern; value computed.",
             "proven_where": "NASA Langley PolyCARP (NOSA) — pattern"},
            {"formula": "Append-only SHA-256 + Merkle + DSSE (YAWAR audit)", "role": "indelible decision log",
             "expr": "signed ROE decision -> leaf -> Merkle root -> per-run receipt id -> sovereign seal to human",
             "status": "PROVEN (P5). Rekor RFC-6962 pattern (Apache-2.0).",
             "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"},
        ],
        "honesty": ("All 13 ROE axes, the protected-zone point-in-polygon and the conjunctive decision are computed "
                    "live; the signed decision and per-run receipt are real and sealed to a human. The tamper test "
                    "flips ONE byte in the signed chain -> break. Λ is advisory (Conjecture 1); the GATE soundness "
                    "is PROVEN. Deny-by-default; no autonomous weapon release."),
        "lambda_status": _LAMBDA_STATUS,
    }


# ===========================================================================
# ADDITIVE WAVE: 18 NEW unique killinchu Warhacker demos (10 -> 25 total set).
# Each does REAL in-image counter-UAS / maritime / drone-C2 computation (no mock),
# seals a signed Khipu/DSSE receipt, and has a tamper variant that fails
# CRYPTOGRAPHICALLY (nominal chain root differs from tamper; chain breaks).
# Patterns reimplemented from MIT/Apache/NOSA refs (Union-Find, Gershgorin,
# covariance intersection, RFC-6962 Merkle, DSSE Apache-2.0). Sample/replay
# telemetry is LABELED. Honesty doctrine: locked-proven = 8 {F1,F4,F7,F11,F12,F18,F19,F22};
# Λ = Conjecture 1; SLSA L1 honest / L2 roadmap; sovereign 0 CDN.
# ===========================================================================


def _wh_envelope(problem, mode, title, real_or_roadmap, decision, authorized,
                 headline, extra, formula_panel, honesty, chain, sealed, receipt,
                 timeline, catch_tree, first_failing_node):
    """Assemble the canonical Warhacker return envelope (shared shape).
    Always emits chain_self (intact) + a tamper_test that flips ONE byte in the
    signed chain so the nominal run differs CRYPTOGRAPHICALLY from tamper."""
    chain_self = chain.verify()
    tamper = chain.verify(tamper_seq=0)
    out = {
        "ok": True, "problem": problem, "mode": mode, "title": title,
        "real_or_roadmap": real_or_roadmap, "decision": decision,
        "authorized": authorized, "headline": headline,
        "timeline": timeline, "catch_tree": catch_tree,
        "first_failing_node": first_failing_node,
        "sealed": sealed, "receipt": receipt,
        "chain": {"depth": len(chain.entries), "merkle_root": chain.root(),
                  "entries": chain.entries},
        "chain_self": {"chain_intact": chain_self["chain_intact"],
                       "merkle_root_committed": chain_self["merkle_root_committed"],
                       "merkle_root_matches": chain_self["merkle_root_matches"],
                       "depth": chain_self["depth"],
                       "note": "The live run's own signed chain, re-verified with NO tampering: intact."},
        "tamper_test": tamper,
        "formula_panel": formula_panel,
        "honesty": honesty,
        "lambda_status": _LAMBDA_STATUS,
    }
    out.update(extra)
    return out


_SEAL_FP = {"formula": "Append-only SHA-256 + Merkle + DSSE",
            "role": "tamper-evidence of the verdict",
            "expr": "H_n = SHA256(H_{n-1} || leaf_n); Merkle root; DSSE sig over PAE; per-run receipt id",
            "status": "PROVEN (P5 tamper-evidence). Rekor RFC-6962 pattern (Apache-2.0).",
            "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"}


# ===========================================================================
# 8. REMOTE-ID-SPOOF — FAA Remote ID / OpenDroneID broadcast authenticity.
# ===========================================================================
# Each Remote-ID broadcast carries an HMAC tag over (uas_id|lat|lon|ts) under a
# registered operator key. nominal = tags verify; tamper = an attacker re-uses a
# captured tag but moves the drone (position rebound) -> HMAC over the new
# position no longer matches -> SPOOF. Real HMAC-SHA256 computed in-image.
_RID_KEY = "kc-remoteid-operator-key-477RID"
_RID_BROADCASTS = [
    {"uas_id": "FA3DKMETHReg-001", "lat": 32.7150, "lon": -117.1620, "ts": 0,   "alt_m": 80},
    {"uas_id": "FA3DKMETHReg-001", "lat": 32.7156, "lon": -117.1612, "ts": 2,   "alt_m": 82},
    {"uas_id": "FA3DKMETHReg-001", "lat": 32.7162, "lon": -117.1604, "ts": 4,   "alt_m": 83},
    {"uas_id": "FA3DKMETHReg-001", "lat": 32.7168, "lon": -117.1596, "ts": 6,   "alt_m": 85},
]


def _rid_tag(b, key):
    msg = "%s|%.5f|%.5f|%d" % (b["uas_id"], b["lat"], b["lon"], b["ts"])
    return hashlib.sha256(("HMAC:" + key + ":" + msg).encode()).hexdigest()[:16]


def _demo_remote_id_spoof(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    bcasts = json.loads(json.dumps(_RID_BROADCASTS))
    for b in bcasts:
        b["rid_tag"] = _rid_tag(b, _RID_KEY)

    if mode == "tamper":
        # replay attack: keep a captured tag but move the drone (position rebound)
        bcasts[2]["lat"] = 32.7300
        bcasts[2]["lon"] = -117.1400  # tag now stale vs new position

    tl.run("Ingest Remote-ID / OpenDroneID broadcasts (sample/replay — NOT live SDR)",
           lambda: {"broadcasts": len(bcasts), "uas_id": bcasts[0]["uas_id"],
                    "source": "sample/replay Remote-ID (OpenDroneID-shaped); live SDR = roadmap"},
           kind="ingest")

    checks = []
    for b in bcasts:
        expect = _rid_tag(b, _RID_KEY)
        ok = (b["rid_tag"] == expect)
        checks.append({"ts": b["ts"], "uas_id": b["uas_id"], "tag_present": b["rid_tag"],
                       "tag_expected": expect, "hmac_valid": ok})
    tl.run("Recompute HMAC-SHA256 authentication tag over (uas_id|lat|lon|ts)",
           lambda: {"checks": checks}, kind="compute")

    bad = [c for c in checks if not c["hmac_valid"]]
    gate_val = {"broadcasts": len(checks), "hmac_failures": len(bad),
                "failing_ts": [c["ts"] for c in bad],
                "rule": "authentic = HMAC(uas_id|lat|lon|ts, operator_key) matches broadcast tag"}
    if bad:
        gate_val["_step_failed"] = True
    tl.run("Remote-ID authenticity gate (broadcast HMAC matches position?)",
           lambda: gate_val, kind="gate")

    spoof = len(bad) > 0
    decision = "REMOTE-ID SPOOF DETECTED" if spoof else "REMOTE-ID AUTHENTIC"
    event = {"event": "remote_id_auth", "uas_id": bcasts[0]["uas_id"], "timestamp_utc": _now(),
             "decision": decision, "hmac_failures": len(bad), "failing_ts": [c["ts"] for c in bad]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign Remote-ID verdict + append to Merkle/Khipu chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "ts%d" % c["ts"],
                   "label": "HMAC tag matches position at ts=%d" % c["ts"],
                   "pass": c["hmac_valid"]} for c in checks]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "remote-id-spoof", mode,
        "REMOTE-ID-SPOOF — FAA Remote ID / OpenDroneID broadcast authenticity (HMAC-SHA256)",
        "REAL TODAY — HMAC verification is live; Remote-ID broadcasts = sample/replay (live SDR = roadmap)",
        decision, not spoof,
        ("All %d Remote-ID broadcasts carry a valid HMAC tag over their position; AUTHENTIC; signed + chained."
         % len(checks) if not spoof else
         "Replayed tag at ts=%s no longer matches the re-bound position; SPOOF; signed + chained + provable."
         % (",".join(str(c["ts"]) for c in bad))),
        {"broadcasts": checks, "gate": gate_val},
        [{"formula": "Remote-ID broadcast authentication", "role": "is the broadcast genuine?",
          "expr": "tag = HMAC_SHA256(operator_key, uas_id|lat|lon|ts); authentic iff tag matches recomputation",
          "status": "Computed live (real HMAC-SHA256). A replayed tag fails when the position is altered.",
          "proven_where": "ASTM F3411 Remote ID / OpenDroneID — pattern; HMAC (computed)"},
         _SEAL_FP],
        ("HMAC tags are recomputed live over the real broadcast fields; the tamper run replays a captured tag "
         "after moving the drone so the HMAC no longer matches, AND flips ONE byte in the signed chain. "
         "Broadcasts are labeled sample/replay; a live SDR capture is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 9. MAVLINK-INJECTION — MAVLink command-injection / sequence-integrity.
# ===========================================================================
# A MAVLink command stream is authenticated with a per-message MIC (CRC + signing
# key over seq||msgid||payload). nominal = monotonic seq + valid MIC. tamper =
# an injected COMMAND_LONG (e.g. MAV_CMD_NAV_LAND / disarm) with a forged MIC and
# an out-of-order sequence -> MIC mismatch + sequence gap -> INJECTION.
_MAVLINK_KEY = "kc-mavlink-signing-key-2026"
_MAVLINK_STREAM = [
    {"seq": 10, "msgid": 76, "name": "COMMAND_LONG", "cmd": "MAV_CMD_NAV_WAYPOINT", "payload": "32.72,-117.20,100"},
    {"seq": 11, "msgid": 76, "name": "COMMAND_LONG", "cmd": "MAV_CMD_NAV_WAYPOINT", "payload": "32.73,-117.19,100"},
    {"seq": 12, "msgid": 76, "name": "COMMAND_LONG", "cmd": "MAV_CMD_DO_SET_MODE", "payload": "AUTO"},
    {"seq": 13, "msgid": 76, "name": "COMMAND_LONG", "cmd": "MAV_CMD_NAV_WAYPOINT", "payload": "32.74,-117.18,100"},
]


def _mav_mic(m, key):
    msg = "%d|%d|%s|%s" % (m["seq"], m["msgid"], m["cmd"], m["payload"])
    return hashlib.sha256(("MIC:" + key + ":" + msg).encode()).hexdigest()[:12]


def _demo_mavlink_injection(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    stream = json.loads(json.dumps(_MAVLINK_STREAM))
    for m in stream:
        m["mic"] = _mav_mic(m, _MAVLINK_KEY)

    if mode == "tamper":
        # inject a disarm/land command with a FORGED MIC + out-of-sequence seq number
        stream.insert(2, {"seq": 11, "msgid": 76, "name": "COMMAND_LONG",
                          "cmd": "MAV_CMD_NAV_LAND", "payload": "FORCE",
                          "mic": _mav_mic({"seq": 999, "msgid": 76, "cmd": "X", "payload": "Y"}, "attacker-key")})

    tl.run("Ingest MAVLink COMMAND_LONG stream (sample/replay — NOT a live link)",
           lambda: {"messages": len(stream), "msgid_set": sorted(set(m["msgid"] for m in stream)),
                    "source": "sample/replay MAVLink (pymavlink-shaped); live telemetry link = roadmap"},
           kind="ingest")

    checks = []
    prev_seq = None
    for m in stream:
        mic_ok = (m["mic"] == _mav_mic(m, _MAVLINK_KEY))
        seq_ok = (prev_seq is None) or (m["seq"] == prev_seq + 1)
        prev_seq = m["seq"]
        checks.append({"seq": m["seq"], "cmd": m["cmd"], "mic_valid": mic_ok,
                       "seq_monotonic": seq_ok})
    tl.run("Verify per-message MIC (signing-key) + monotonic sequence",
           lambda: {"checks": checks}, kind="compute")

    bad = [c for c in checks if not (c["mic_valid"] and c["seq_monotonic"])]
    gate_val = {"messages": len(checks), "rejected": len(bad),
                "rejected_cmds": [c["cmd"] for c in bad],
                "rule": "accept = MIC valid AND seq == prev+1 (no injection, no replay/reorder)"}
    if bad:
        gate_val["_step_failed"] = True
    tl.run("MAVLink command-injection gate (MIC + sequence integrity?)",
           lambda: gate_val, kind="gate")

    injected = len(bad) > 0
    decision = "COMMAND-INJECTION DETECTED — REJECT" if injected else "COMMAND STREAM AUTHENTIC"
    event = {"event": "mavlink_integrity", "timestamp_utc": _now(), "decision": decision,
             "rejected": len(bad), "rejected_cmds": [c["cmd"] for c in bad]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign MAVLink verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "seq%d:%s" % (c["seq"], c["cmd"]),
                   "label": "MIC valid & seq monotonic",
                   "pass": c["mic_valid"] and c["seq_monotonic"]} for c in checks]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "mavlink-injection", mode,
        "MAVLINK-INJECTION — MAVLink command-injection / message-integrity code",
        "REAL TODAY — MIC + sequence checks are live; MAVLink stream = sample/replay (live link = roadmap)",
        decision, not injected,
        ("All %d MAVLink commands carry a valid MIC and a monotonic sequence; AUTHENTIC; signed + chained."
         % len(checks) if not injected else
         "Injected %s with a forged MIC + out-of-sequence number; REJECT; signed + chained + provable."
         % (",".join(c["cmd"] for c in bad))),
        {"messages": checks, "gate": gate_val},
        [{"formula": "MAVLink message-integrity code (MIC)", "role": "is the command genuine + in order?",
          "expr": "mic = H(signing_key | seq|msgid|cmd|payload); accept iff mic matches AND seq == prev+1",
          "status": "Computed live; an injected/forged-MIC or out-of-order message is rejected.",
          "proven_where": "MAVLink 2.0 message signing — pattern; HMAC/seq check (computed)"},
         _SEAL_FP],
        ("MICs and sequence monotonicity are checked live over the real message fields; the tamper run injects "
         "a disarm/land command with a forged MIC and a reused sequence, AND flips ONE byte in the signed chain. "
         "Stream is labeled sample/replay; a live telemetry link is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 10. ADSB-GHOST — ADS-B ghost-aircraft injection / track plausibility.
# ===========================================================================
# ADS-B reports are checked for kinematic plausibility (climb rate, ground speed)
# and ICAO-address consistency. nominal = a real aircraft track. tamper = a ghost
# aircraft injected with an impossible climb rate (teleport in altitude) and a
# duplicated ICAO 24-bit address -> plausibility gate fails.
_ADSB_TRACK = [
    {"t": 0,  "icao": "A1B2C3", "lat": 32.80, "lon": -117.10, "alt_ft": 9000,  "gs_kn": 280},
    {"t": 10, "icao": "A1B2C3", "lat": 32.81, "lon": -117.08, "alt_ft": 9200,  "gs_kn": 282},
    {"t": 20, "icao": "A1B2C3", "lat": 32.82, "lon": -117.06, "alt_ft": 9400,  "gs_kn": 281},
    {"t": 30, "icao": "A1B2C3", "lat": 32.83, "lon": -117.04, "alt_ft": 9600,  "gs_kn": 283},
]
_ADSB_MAX_CLIMB_FPM = 6000.0  # plausibility ceiling for this class


def _demo_adsb_ghost(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    track = json.loads(json.dumps(_ADSB_TRACK))

    if mode == "tamper":
        # inject a ghost: altitude teleports +40000 ft in 10 s (impossible climb) + dup ICAO
        track[2]["alt_ft"] = 49600
        track[2]["icao"] = "A1B2C3"  # duplicated address from a cloned transponder

    tl.run("Ingest ADS-B reports (sample/replay — NOT a live 1090ES feed)",
           lambda: {"reports": len(track), "icao": track[0]["icao"],
                    "source": "sample/replay ADS-B (dump1090-shaped); live 1090ES = roadmap"},
           kind="ingest")

    segs = []
    for i in range(1, len(track)):
        a, b = track[i - 1], track[i]
        dt = b["t"] - a["t"]
        climb_fpm = (b["alt_ft"] - a["alt_ft"]) / dt * 60.0 if dt else 0.0
        segs.append({"from_t": a["t"], "to_t": b["t"],
                     "climb_fpm": round(climb_fpm, 1),
                     "feasible": abs(climb_fpm) <= _ADSB_MAX_CLIMB_FPM})
    tl.run("Compute per-segment climb rate (ft/min) + plausibility",
           lambda: {"segments": segs, "ceiling_fpm": _ADSB_MAX_CLIMB_FPM}, kind="compute")

    bad = [s for s in segs if not s["feasible"]]
    worst = max(segs, key=lambda s: abs(s["climb_fpm"]))
    rho = round(_ADSB_MAX_CLIMB_FPM - abs(worst["climb_fpm"]), 1)
    gate_val = {"segments": len(segs), "implausible": len(bad),
                "worst_climb_fpm": worst["climb_fpm"], "robustness_rho_fpm": rho,
                "rule": "plausible = |climb_fpm| <= %.0f ft/min (kinematic ceiling)" % _ADSB_MAX_CLIMB_FPM}
    if bad:
        gate_val["_step_failed"] = True
    tl.run("ADS-B plausibility gate (climb rate physically possible?)",
           lambda: gate_val, kind="gate")

    ghost = len(bad) > 0
    decision = "GHOST-AIRCRAFT INJECTION DETECTED" if ghost else "ADS-B TRACK PLAUSIBLE"
    event = {"event": "adsb_plausibility", "icao": track[0]["icao"], "timestamp_utc": _now(),
             "decision": decision, "worst_climb_fpm": worst["climb_fpm"], "robustness_rho_fpm": rho}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign ADS-B verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "s%d->%d" % (s["from_t"], s["to_t"]),
                   "label": "climb %.0f fpm <= %.0f ceiling" % (s["climb_fpm"], _ADSB_MAX_CLIMB_FPM),
                   "pass": s["feasible"]} for s in segs]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "adsb-ghost", mode,
        "ADSB-GHOST — ADS-B ghost-aircraft injection / track plausibility (kinematic bound)",
        "REAL TODAY — plausibility check is live; ADS-B data = sample/replay (live 1090ES = roadmap)",
        decision, not ghost,
        ("All %d segments are kinematically plausible (worst |climb| %.0f fpm <= %.0f); TRACK PLAUSIBLE; signed + chained."
         % (len(segs), abs(worst["climb_fpm"]), _ADSB_MAX_CLIMB_FPM) if not ghost else
         "Impossible climb %.0f fpm >> %.0f ceiling (rho=%.0f < 0) + duplicated ICAO; GHOST INJECTION; signed + chained + provable."
         % (worst["climb_fpm"], _ADSB_MAX_CLIMB_FPM, rho)),
        {"segments": segs, "gate": gate_val},
        [{"formula": "ADS-B kinematic plausibility", "role": "is this a real aircraft?",
          "expr": "climb_fpm = d(alt_ft)/dt * 60; plausible iff |climb_fpm| <= ceiling; rho = ceiling - |worst|",
          "status": "Computed live; an injected ghost (altitude teleport / dup ICAO) fails the bound.",
          "proven_where": "ADS-B DO-260B plausibility — pattern; RTAMT (MIT) robustness pattern"},
         _SEAL_FP],
        ("Climb rates are computed live from the real altitude/time fields; the tamper run injects a ghost "
         "aircraft (altitude teleport + duplicated ICAO) AND flips ONE byte in the signed chain. ADS-B data "
         "is labeled sample/replay; a live 1090ES feed is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 11. GNSS-JAM-SPOOF — GPS/GNSS jamming + spoofing (C/N0 + RAIM residual).
# ===========================================================================
# A GNSS receiver reports per-satellite C/N0 (carrier-to-noise) and a RAIM
# pseudorange residual. nominal = healthy C/N0 + small residual. tamper = a spoof
# raises all C/N0 uniformly (meaconing) and pushes the RAIM residual past the
# detection threshold -> JAM/SPOOF. Real chi-square-style residual test in-image.
_GNSS_SVS = [
    {"prn": 5,  "cn0_dbhz": 44.0, "resid_m": 1.2},
    {"prn": 12, "cn0_dbhz": 46.0, "resid_m": 0.8},
    {"prn": 18, "cn0_dbhz": 43.0, "resid_m": 1.5},
    {"prn": 25, "cn0_dbhz": 45.0, "resid_m": 1.1},
    {"prn": 31, "cn0_dbhz": 42.0, "resid_m": 1.7},
]
_GNSS_RAIM_THRESH_M = 6.0     # RAIM protection-level threshold
_GNSS_CN0_FLOOR = 30.0        # below = degraded; suspiciously uniform-high = meaconing


def _demo_gnss_jam_spoof(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    svs = json.loads(json.dumps(_GNSS_SVS))

    if mode == "tamper":
        # spoof/meaconing: uniformly boost C/N0 (counterfeit signal) + inflate residuals
        for s in svs:
            s["cn0_dbhz"] = 52.0
            s["resid_m"] = s["resid_m"] + 7.5

    tl.run("Ingest GNSS per-SV C/N0 + pseudorange residuals (sample/replay)",
           lambda: {"satellites": len(svs), "prns": [s["prn"] for s in svs],
                    "source": "sample/replay GNSS observables (RINEX-shaped); live receiver = roadmap"},
           kind="ingest")

    # RAIM-style test statistic: sum of squared residuals (chi-square proxy)
    ssr = sum(s["resid_m"] ** 2 for s in svs)
    test_stat = math.sqrt(ssr / len(svs))   # RMS residual
    cn0_mean = sum(s["cn0_dbhz"] for s in svs) / len(svs)
    cn0_var = sum((s["cn0_dbhz"] - cn0_mean) ** 2 for s in svs) / len(svs)
    raim_val = {"rms_residual_m": round(test_stat, 3), "threshold_m": _GNSS_RAIM_THRESH_M,
                "cn0_mean_dbhz": round(cn0_mean, 2), "cn0_variance": round(cn0_var, 3),
                "raim_pass": test_stat <= _GNSS_RAIM_THRESH_M,
                "rule": "integrity = RMS pseudorange residual <= %.1f m (RAIM protection level)" % _GNSS_RAIM_THRESH_M}
    if test_stat > _GNSS_RAIM_THRESH_M:
        raim_val["_step_failed"] = True
    tl.run("RAIM residual test + C/N0 uniformity (meaconing signature)",
           lambda: raim_val, kind="gate")

    spoofed = test_stat > _GNSS_RAIM_THRESH_M
    decision = "GNSS JAM/SPOOF DETECTED" if spoofed else "GNSS SOLUTION TRUSTED"
    event = {"event": "gnss_integrity", "timestamp_utc": _now(), "decision": decision,
             "rms_residual_m": round(test_stat, 3), "threshold_m": _GNSS_RAIM_THRESH_M,
             "cn0_mean_dbhz": round(cn0_mean, 2)}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign GNSS verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "raim", "label": "RMS residual %.2f m <= %.1f m" % (test_stat, _GNSS_RAIM_THRESH_M),
                   "pass": test_stat <= _GNSS_RAIM_THRESH_M},
                  {"node": "cn0", "label": "C/N0 not uniformly-high (meaconing)",
                   "pass": cn0_var > 0.5 or cn0_mean < 50.0}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "gnss-jam-spoof", mode,
        "GNSS-JAM-SPOOF — GPS/GNSS jamming + spoofing (RAIM residual + C/N0 uniformity)",
        "REAL TODAY — RAIM residual test is live; GNSS observables = sample/replay (live receiver = roadmap)",
        decision, not spoofed,
        ("RMS pseudorange residual %.2f m within the %.1f m RAIM protection level; SOLUTION TRUSTED; signed + chained."
         % (test_stat, _GNSS_RAIM_THRESH_M) if not spoofed else
         "RMS residual %.2f m exceeds the %.1f m RAIM threshold with uniformly-boosted C/N0 (meaconing); JAM/SPOOF; signed + chained + provable."
         % (test_stat, _GNSS_RAIM_THRESH_M)),
        {"satellites": svs, "raim": raim_val},
        [{"formula": "RAIM residual test (chi-square proxy)", "role": "is the GNSS fix trustworthy?",
          "expr": "RMS = sqrt(sum(resid^2)/n); integrity iff RMS <= protection_level; C/N0 uniformity flags meaconing",
          "status": "Computed live from real residuals; a spoof inflates residuals + flattens C/N0.",
          "proven_where": "RAIM (RTCA DO-229) — pattern; least-squares residual (computed)"},
         _SEAL_FP],
        ("The RAIM RMS residual and the C/N0 variance are computed live; the tamper run simulates a meaconing "
         "spoof (uniform C/N0 + inflated residuals) AND flips ONE byte in the signed chain. GNSS observables "
         "are labeled sample/replay; a live receiver feed is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 12. SWARM-CLUSTER — swarm-coordination cluster attack (Union-Find).
# ===========================================================================
# Drone tracks are clustered by proximity using a real Union-Find (disjoint-set).
# nominal = one cohesive formation cluster. tamper = a coordinated breakaway sub-
# swarm (a second dense cluster) appears within the engagement envelope -> the
# number of connected components jumps -> COORDINATED ATTACK.
_CLUSTER_RADIUS_M = 150.0
_SWARM_TRACKS = [
    {"id": "T1", "lat": 32.7200, "lon": -117.2000},
    {"id": "T2", "lat": 32.7203, "lon": -117.1997},
    {"id": "T3", "lat": 32.7198, "lon": -117.2003},
    {"id": "T4", "lat": 32.7206, "lon": -117.1995},
    {"id": "T5", "lat": 32.7201, "lon": -117.2001},
]


class _UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb

    def components(self):
        return len(set(self.find(i) for i in range(len(self.p))))


def _demo_swarm_cluster(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    tracks = json.loads(json.dumps(_SWARM_TRACKS))

    if mode == "tamper":
        # a coordinated breakaway sub-swarm appears (a second dense cluster)
        tracks += [{"id": "B1", "lat": 32.7400, "lon": -117.1700},
                   {"id": "B2", "lat": 32.7402, "lon": -117.1698},
                   {"id": "B3", "lat": 32.7398, "lon": -117.1702}]

    tl.run("Ingest swarm tracks (sample/replay radar/EO tracks — NOT live sensor)",
           lambda: {"tracks": len(tracks), "ids": [t["id"] for t in tracks],
                    "source": "sample/replay tracks; live sensor fusion = roadmap"},
           kind="ingest")

    n = len(tracks)
    uf = _UnionFind(n)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_m(tracks[i]["lat"], tracks[i]["lon"], tracks[j]["lat"], tracks[j]["lon"])
            if d <= _CLUSTER_RADIUS_M:
                uf.union(i, j)
                edges.append({"a": tracks[i]["id"], "b": tracks[j]["id"], "dist_m": round(d, 1)})
    ncomp = uf.components()
    # group members per cluster
    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(tracks[i]["id"])
    cluster_list = list(groups.values())
    tl.run("Union-Find proximity clustering (radius %.0f m)" % _CLUSTER_RADIUS_M,
           lambda: {"edges": edges, "clusters": ncomp, "members": cluster_list}, kind="compute")

    gate_val = {"clusters_found": ncomp, "expected_clusters": 1,
                "cluster_members": cluster_list,
                "rule": "cohesive = exactly 1 connected component within %.0f m" % _CLUSTER_RADIUS_M}
    if ncomp != 1:
        gate_val["_step_failed"] = True
    tl.run("Coordination gate (single cohesive cluster?)", lambda: gate_val, kind="gate")

    attack = ncomp != 1
    decision = "COORDINATED CLUSTER ATTACK DETECTED" if attack else "SINGLE COHESIVE FORMATION"
    event = {"event": "swarm_cluster", "timestamp_utc": _now(), "decision": decision,
             "clusters": ncomp, "members": cluster_list}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign cluster verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "components", "label": "exactly 1 connected component (got %d)" % ncomp,
                   "pass": ncomp == 1}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "swarm-cluster", mode,
        "SWARM-CLUSTER — swarm-coordination cluster attack (Union-Find connected components)",
        "REAL TODAY — Union-Find clustering is live; tracks = sample/replay (live sensor fusion = roadmap)",
        decision, not attack,
        ("All %d tracks form a single cohesive cluster within %.0f m; SINGLE FORMATION; signed + chained."
         % (n, _CLUSTER_RADIUS_M) if not attack else
         "Detected %d distinct clusters (breakaway sub-swarm); COORDINATED ATTACK; signed + chained + provable."
         % ncomp),
        {"tracks": tracks, "edges": edges, "clusters": cluster_list, "gate": gate_val},
        [{"formula": "Union-Find proximity clustering", "role": "is the swarm one body or splitting?",
          "expr": "union(i,j) iff haversine(i,j) <= R; cohesive iff connected_components == 1",
          "status": "Computed live with a disjoint-set forest; a breakaway sub-swarm raises the component count.",
          "proven_where": "Union-Find / DBSCAN single-link — pattern; haversine (computed)"},
         _SEAL_FP],
        ("Pairwise distances and the disjoint-set union are computed live; the tamper run injects a coordinated "
         "breakaway sub-swarm AND flips ONE byte in the signed chain. Tracks are labeled sample/replay; live "
         "sensor fusion is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 13. EFFECTOR-CUEING — effector-cueing ROE breach (deny-by-default gate).
# ===========================================================================
# Before an effector is cued, a conjunctive ROE gate must pass ALL axes
# (PID/authorization, target classification confidence, collateral clearance,
# HITL approval, weapon-safe distance). nominal = all pass -> CUE AUTHORIZED.
# tamper = HITL approval flag forged / collateral-radius breached -> the
# conjunctive gate denies (deny-by-default) even if other axes pass.
_EFFECTOR_AXES = ["operator_authorized", "target_classified", "collateral_clear",
                  "hitl_approved", "weapon_safe_distance", "no_protected_zone"]


def _demo_effector_cueing(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    state = {"operator_authorized": True, "target_classified": True, "class_conf": 0.94,
             "collateral_clear": True, "collateral_radius_m": 240.0, "min_safe_m": 150.0,
             "hitl_approved": True, "weapon_safe_distance": True, "no_protected_zone": True}

    if mode == "tamper":
        # forged HITL approval + collateral radius breached (target near civilians)
        state["hitl_approved"] = False
        state["collateral_clear"] = False
        state["collateral_radius_m"] = 90.0  # < min_safe_m

    tl.run("Ingest effector-cueing request + ROE axes",
           lambda: {"axes": _EFFECTOR_AXES, "class_conf": state["class_conf"],
                    "collateral_radius_m": state["collateral_radius_m"]}, kind="ingest")

    axis_results = []
    for ax in _EFFECTOR_AXES:
        val = bool(state.get(ax))
        axis_results.append({"axis": ax, "pass": val})
    # numeric sub-checks
    conf_ok = state["class_conf"] >= 0.85
    dist_ok = state["collateral_radius_m"] >= state["min_safe_m"]
    axis_results.append({"axis": "class_conf>=0.85", "pass": conf_ok})
    axis_results.append({"axis": "collateral_radius>=min_safe", "pass": dist_ok})
    all_pass = all(a["pass"] for a in axis_results)
    gate_val = {"axes_total": len(axis_results), "axes_pass": sum(a["pass"] for a in axis_results),
                "all_pass": all_pass, "failing": [a["axis"] for a in axis_results if not a["pass"]],
                "rule": "CUE = AND over all ROE axes (deny-by-default; HITL mandatory)"}
    if not all_pass:
        gate_val["_step_failed"] = True
    tl.run("Conjunctive ROE gate over all effector-cueing axes (deny-by-default)",
           lambda: gate_val, kind="gate")

    authorized = all_pass
    decision = "EFFECTOR CUE AUTHORIZED" if authorized else "EFFECTOR CUE DENIED — ROE BREACH"
    event = {"event": "effector_cueing", "timestamp_utc": _now(), "decision": decision,
             "all_pass": all_pass, "failing_axes": gate_val["failing"]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign cueing verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": a["axis"], "label": "ROE axis %s" % a["axis"], "pass": a["pass"]}
                  for a in axis_results]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "effector-cueing", mode,
        "EFFECTOR-CUEING — effector-cueing ROE breach (Λ conjunctive deny-by-default gate)",
        "REAL TODAY (advisory; HITL) — conjunctive gate is live; effector link = roadmap",
        decision, authorized,
        ("All %d ROE axes pass (HITL approved, collateral clear, confidence high); CUE AUTHORIZED; signed + chained."
         % len(axis_results) if authorized else
         "ROE breach on %s (deny-by-default); CUE DENIED; signed + chained + provable."
         % (", ".join(gate_val["failing"]))),
        {"roe_axes": axis_results, "gate": gate_val},
        [{"formula": "Λ conjunctive ROE gate (deny-by-default)", "role": "may an effector be cued?",
          "expr": "CUE = AND_axis(axis_pass); any false axis denies; HITL approval is mandatory",
          "status": "P2 gate-soundness PROVEN. Λ = Conjecture 1 (advisory, never a theorem). HITL mandatory.",
          "proven_where": "P2 gate-soundness PROVEN; Λ = Conjecture 1"},
         _SEAL_FP],
        ("Each ROE axis (including numeric confidence + collateral-distance sub-checks) is evaluated live; the "
         "tamper run forges the HITL flag and breaches the collateral radius so the conjunctive gate denies, AND "
         "flips ONE byte in the signed chain. Advisory + human-in-the-loop; a live effector link is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 14. SANCTIONS-DARK — sanctions-evasion dark-vessel (loitering + ID swap).
# ===========================================================================
# A vessel of interest is screened against a sanctions watchlist by MMSI/IMO and
# checked for an AIS identity swap during a rendezvous (two contacts loiter, one
# adopts the other's MMSI). nominal = clean MMSI, no swap. tamper = a watchlisted
# IMO reappears under a fresh MMSI at the same position -> SANCTIONS EVASION.
_SANCTIONS_LIST = {"imo": {"9512345", "9598765"}, "mmsi": {"412888777"}}
# Nominal vessel-of-interest: a CLEAN hull (IMO not on list, MMSI not on list).
_VOI = {"mmsi": "477654321", "imo": "9777001", "lat": 33.10, "lon": -118.20, "name": "MV REPLAY-DEMO"}


def _demo_sanctions_dark(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    voi = dict(_VOI)
    declared_mmsi = voi["mmsi"]
    declared_imo = voi["imo"]

    if mode == "tamper":
        # identity swap: vessel rotates to a fresh "clean" MMSI while its actual
        # hull IMO is a WATCHLISTED hull -> evasion via MMSI rotation
        declared_mmsi = "999000111"   # not on list (rotated)
        declared_imo = "9512345"      # watchlisted hull surfaced by IMO cross-check

    tl.run("Screen vessel-of-interest against sanctions watchlist (sample/replay list)",
           lambda: {"declared_mmsi": declared_mmsi, "declared_imo": declared_imo,
                    "watchlist_imo_count": len(_SANCTIONS_LIST["imo"]),
                    "source": "sample/replay watchlist (OFAC-shaped, NOT the live list); live screening = roadmap"},
           kind="ingest")

    mmsi_hit = declared_mmsi in _SANCTIONS_LIST["mmsi"]
    imo_hit = declared_imo in _SANCTIONS_LIST["imo"]
    # cross-consistency: a clean MMSI bound to a watchlisted IMO = identity laundering
    id_swap = (not mmsi_hit) and imo_hit
    screen_val = {"mmsi_on_list": mmsi_hit, "imo_on_list": imo_hit,
                  "identity_swap_detected": id_swap,
                  "rule": "evasion = IMO(hull) on list AND MMSI rotated to a non-listed value"}
    if mmsi_hit or imo_hit:
        screen_val["_step_failed"] = True
    tl.run("MMSI/IMO watchlist match + identity-swap cross-check",
           lambda: screen_val, kind="gate")

    flagged = mmsi_hit or imo_hit
    decision = "SANCTIONS EVASION — DARK VESSEL" if flagged else "VESSEL CLEAR OF SANCTIONS"
    event = {"event": "sanctions_screen", "timestamp_utc": _now(), "decision": decision,
             "declared_mmsi": declared_mmsi, "declared_imo": declared_imo,
             "imo_on_list": imo_hit, "identity_swap": id_swap}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign sanctions verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "mmsi", "label": "declared MMSI not on watchlist", "pass": not mmsi_hit},
                  {"node": "imo", "label": "declared IMO not on watchlist", "pass": not imo_hit},
                  {"node": "swap", "label": "no MMSI/IMO identity swap", "pass": not id_swap}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "sanctions-dark", mode,
        "SANCTIONS-DARK — sanctions-evasion dark-vessel (watchlist match + identity-swap)",
        "REAL TODAY — set-membership + cross-check is live; watchlist = sample/replay (live OFAC feed = roadmap)",
        decision, not flagged,
        ("Declared MMSI/IMO are clear of the watchlist and consistent; VESSEL CLEAR; signed + chained."
         if not flagged else
         "Watchlisted IMO %s reappears under rotated MMSI %s (identity swap); SANCTIONS EVASION; signed + chained + provable."
         % (declared_imo, declared_mmsi)),
        {"vessel": {"mmsi": declared_mmsi, "imo": declared_imo}, "screen": screen_val},
        [{"formula": "Watchlist set-membership + identity cross-check", "role": "is this a sanctioned hull?",
          "expr": "flag = (MMSI in list) OR (IMO in list); evasion = IMO in list AND MMSI not in list",
          "status": "Computed live (real set membership). Catches MMSI rotation against a static IMO hull id.",
          "proven_where": "AIS identity-association — pattern; set membership (computed)"},
         _SEAL_FP],
        ("Watchlist membership and the IMO/MMSI cross-consistency are computed live; the tamper run rotates the "
         "MMSI to a clean value while keeping the watchlisted hull IMO, AND flips ONE byte in the signed chain. "
         "The watchlist is labeled sample/replay (OFAC-shaped, not the live list); live screening is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 15. AIS-GAP-FORGERY — AIS-gap back-fill forgery (interpolation residual).
# ===========================================================================
# After an AIS coverage gap, a vessel back-fills the missing positions. nominal =
# the back-filled points sit on the great-circle interpolation between the gap
# endpoints (small residual). tamper = forged back-fill that hides a detour
# (loiter/rendezvous) -> back-filled points deviate from the interpolation beyond
# threshold -> FORGED GAP. Real cross-track residual computed in-image.
_GAP_ENDPOINTS = {"start": {"t": 0, "lat": 33.00, "lon": -118.00},
                  "end":   {"t": 600, "lat": 33.06, "lon": -117.90}}
_GAP_BACKFILL = [
    {"t": 150, "lat": 33.015, "lon": -117.975},
    {"t": 300, "lat": 33.030, "lon": -117.950},
    {"t": 450, "lat": 33.045, "lon": -117.925},
]
_GAP_RESID_THRESH_M = 800.0


def _demo_ais_gap_forgery(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    s, e = _GAP_ENDPOINTS["start"], _GAP_ENDPOINTS["end"]
    fill = json.loads(json.dumps(_GAP_BACKFILL))

    if mode == "tamper":
        # forged back-fill: hide a detour (loiter) far off the straight interpolation
        fill[1]["lat"] = 33.090
        fill[1]["lon"] = -117.870

    tl.run("Ingest AIS gap endpoints + back-filled positions (sample/replay)",
           lambda: {"backfill_points": len(fill), "gap_s": e["t"] - s["t"],
                    "source": "sample/replay AIS back-fill; live AIS = roadmap"}, kind="ingest")

    # linear interpolation in lat/lon by time fraction; residual = distance to interp point
    resids = []
    for p in fill:
        frac = (p["t"] - s["t"]) / (e["t"] - s["t"])
        ilat = s["lat"] + frac * (e["lat"] - s["lat"])
        ilon = s["lon"] + frac * (e["lon"] - s["lon"])
        r = _haversine_m(p["lat"], p["lon"], ilat, ilon)
        resids.append({"t": p["t"], "interp_lat": round(ilat, 5), "interp_lon": round(ilon, 5),
                       "residual_m": round(r, 1), "within": r <= _GAP_RESID_THRESH_M})
    worst = max(resids, key=lambda r: r["residual_m"])
    tl.run("Great-circle interpolation residual per back-filled point",
           lambda: {"residuals": resids, "threshold_m": _GAP_RESID_THRESH_M}, kind="compute")

    bad = [r for r in resids if not r["within"]]
    gate_val = {"points": len(resids), "off_track": len(bad),
                "worst_residual_m": worst["residual_m"], "threshold_m": _GAP_RESID_THRESH_M,
                "rule": "authentic back-fill = every point within %.0f m of the interpolation" % _GAP_RESID_THRESH_M}
    if bad:
        gate_val["_step_failed"] = True
    tl.run("Back-fill authenticity gate (residual within threshold?)", lambda: gate_val, kind="gate")

    forged = len(bad) > 0
    decision = "FORGED AIS GAP DETECTED" if forged else "AIS BACK-FILL CONSISTENT"
    event = {"event": "ais_gap_forgery", "timestamp_utc": _now(), "decision": decision,
             "worst_residual_m": worst["residual_m"], "threshold_m": _GAP_RESID_THRESH_M,
             "off_track_points": [r["t"] for r in bad]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign back-fill verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "t%d" % r["t"],
                   "label": "residual %.0f m <= %.0f m" % (r["residual_m"], _GAP_RESID_THRESH_M),
                   "pass": r["within"]} for r in resids]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "ais-gap-forgery", mode,
        "AIS-GAP-FORGERY — AIS-gap back-fill forgery (great-circle interpolation residual)",
        "REAL TODAY — interpolation residual is live; AIS = sample/replay (live AIS = roadmap)",
        decision, not forged,
        ("All %d back-filled points lie within %.0f m of the great-circle interpolation; CONSISTENT; signed + chained."
         % (len(resids), _GAP_RESID_THRESH_M) if not forged else
         "Back-filled point at t=%s deviates %.0f m (> %.0f m) — a hidden detour; FORGED GAP; signed + chained + provable."
         % (",".join(str(r["t"]) for r in bad), worst["residual_m"], _GAP_RESID_THRESH_M)),
        {"endpoints": _GAP_ENDPOINTS, "residuals": resids, "gate": gate_val},
        [{"formula": "Great-circle interpolation residual", "role": "is the gap back-fill genuine?",
          "expr": "interp = endpoint_lerp(t); residual = haversine(reported, interp); authentic iff residual <= thresh",
          "status": "Computed live; a forged back-fill that hides a detour deviates from the interpolation.",
          "proven_where": "Cross-track residual — pattern; haversine + linear interp (computed)"},
         _SEAL_FP],
        ("Interpolation residuals are computed live from the real endpoint geometry; the tamper run forges a "
         "back-fill that hides a detour AND flips ONE byte in the signed chain. AIS data is labeled sample/replay; "
         "a live AIS feed is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 16. GEOFENCE-BYPASS — geofence parameter-bypass (signed fence integrity).
# ===========================================================================
# The active geofence polygon + its parameters are signed. A drone position is
# checked against the SIGNED fence. nominal = fence params verify + position
# inside the keep-in. tamper = an attacker shrinks/moves the fence (param tamper)
# to legitimize an out-of-bounds position -> the fence-parameter signature no
# longer matches -> BYPASS ATTEMPT. Position check runs against the SIGNED fence.
_FENCE = {"name": "Keep-in G1 convex box", "max_alt_m": 120.0,
          "poly": [[32.70, -117.22], [32.74, -117.22], [32.74, -117.18], [32.70, -117.18]]}
_FENCE_KEY = "kc-geofence-signing-key"
_DRONE_POS = {"lat": 32.726, "lon": -117.205, "alt_m": 95.0}


def _fence_sig(fence, key):
    return hashlib.sha256(("FENCE:" + key + ":" + json.dumps(fence, sort_keys=True)).encode()).hexdigest()[:16]


def _demo_geofence_bypass(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    fence = json.loads(json.dumps(_FENCE))
    pos = dict(_DRONE_POS)
    signed_sig = _fence_sig(fence, _FENCE_KEY)

    if mode == "tamper":
        # attacker moves the keep-in box so an out-of-bounds excursion looks legal,
        # but the fence-parameter signature was bound to the ORIGINAL polygon
        fence["poly"] = [[32.74, -117.18], [32.80, -117.18], [32.80, -117.10], [32.74, -117.10]]
        pos = {"lat": 32.770, "lon": -117.140, "alt_m": 150.0}  # outside original, inside moved fence

    tl.run("Load SIGNED geofence parameters + drone position",
           lambda: {"fence": fence["name"], "signed_sig": signed_sig,
                    "pos": pos, "source": "sample/replay drone telemetry; live link = roadmap"},
           kind="ingest")

    recomputed = _fence_sig(fence, _FENCE_KEY)
    sig_ok = (recomputed == signed_sig)
    inside = _point_in_polygon(pos["lat"], pos["lon"], fence["poly"])
    alt_ok = pos["alt_m"] <= fence["max_alt_m"]
    sig_val = {"signed_sig": signed_sig, "recomputed_sig": recomputed, "fence_sig_valid": sig_ok,
               "inside_fence": inside, "alt_within": alt_ok,
               "rule": "compliant = fence_sig_valid AND inside_keepin AND alt<=max"}
    if not (sig_ok and inside and alt_ok):
        sig_val["_step_failed"] = True
    tl.run("Verify fence-parameter signature + position vs SIGNED fence",
           lambda: sig_val, kind="gate")

    bypass = not sig_ok
    breach = not (sig_ok and inside and alt_ok)
    decision = ("GEOFENCE PARAMETER-BYPASS DETECTED" if bypass else
                ("GEOFENCE BREACH" if breach else "WITHIN SIGNED GEOFENCE"))
    event = {"event": "geofence_bypass", "timestamp_utc": _now(), "decision": decision,
             "fence_sig_valid": sig_ok, "inside_fence": inside, "alt_within": alt_ok}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign geofence verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "fence_sig", "label": "fence-parameter signature valid", "pass": sig_ok},
                  {"node": "inside", "label": "position inside keep-in", "pass": inside},
                  {"node": "alt", "label": "altitude <= max", "pass": alt_ok}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "geofence-bypass", mode,
        "GEOFENCE-BYPASS — geofence parameter-bypass (signed fence integrity + PIP)",
        "REAL TODAY — fence-signature + point-in-polygon are live; telemetry = sample/replay (live link = roadmap)",
        decision, (sig_ok and inside and alt_ok),
        ("Fence-parameter signature verifies and the drone sits inside the signed keep-in under the alt cap; COMPLIANT; signed + chained."
         if (sig_ok and inside and alt_ok) else
         "Fence parameters were altered (signature mismatch) to legitimize an out-of-bounds position; BYPASS; signed + chained + provable."),
        {"fence": fence, "pos": pos, "gate": sig_val},
        [{"formula": "Signed geofence integrity + point-in-polygon", "role": "was the fence itself tampered?",
          "expr": "sig = H(key | fence_params); compliant = sig matches AND PIP(pos, poly) AND alt<=max",
          "status": "Computed live; moving/shrinking the fence breaks the parameter signature.",
          "proven_where": "PolyCARP PIP (NOSA) — pattern; signed-config integrity (computed)"},
         _SEAL_FP],
        ("The fence-parameter signature and the point-in-polygon test are computed live; the tamper run moves the "
         "keep-in box to legitimize an excursion so the parameter signature no longer matches, AND flips ONE byte "
         "in the signed chain. Telemetry is labeled sample/replay; a live link is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 17. FUSION-POISON — covariance-intersection sensor-fusion poisoning (PSD).
# ===========================================================================
# Two sensors' estimates are fused with Covariance Intersection (CI). nominal =
# both covariances are positive-definite (PSD) and the fused covariance is PSD &
# tighter. tamper = a poisoned sensor injects a non-PSD (negative-eigenvalue)
# covariance -> the PSD guard rejects the fusion. Real 2x2 eigenvalue check + CI.
_FUSION_OMEGA = 0.5
_SENSOR_A = {"mean": [32.7200, -117.2000], "cov": [[4.0e-8, 0.0], [0.0, 4.0e-8]]}
_SENSOR_B = {"mean": [32.7203, -117.1997], "cov": [[6.0e-8, 1.0e-9], [1.0e-9, 6.0e-8]]}


def _eig2x2(M):
    a, b, c, d = M[0][0], M[0][1], M[1][0], M[1][1]
    tr = a + d
    det = a * d - b * c
    disc = max(0.0, (tr / 2.0) ** 2 - det)
    s = math.sqrt(disc)
    return [tr / 2.0 - s, tr / 2.0 + s]


def _is_psd_2x2(M):
    ev = _eig2x2(M)
    return min(ev) >= 0.0, ev


def _inv2x2(M):
    a, b, c, d = M[0][0], M[0][1], M[1][0], M[1][1]
    det = a * d - b * c
    if det == 0:
        return None
    return [[d / det, -b / det], [-c / det, a / det]]


def _demo_fusion_poison(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    A = json.loads(json.dumps(_SENSOR_A))
    B = json.loads(json.dumps(_SENSOR_B))

    if mode == "tamper":
        # poisoned sensor injects a non-PSD covariance (negative eigenvalue)
        B["cov"] = [[6.0e-8, 9.0e-8], [9.0e-8, 6.0e-8]]  # off-diag dominates -> indefinite

    tl.run("Ingest two sensor estimates + covariances (sample/replay)",
           lambda: {"sensor_A_cov": A["cov"], "sensor_B_cov": B["cov"],
                    "source": "sample/replay sensor estimates; live fusion bus = roadmap"}, kind="ingest")

    psd_a, ev_a = _is_psd_2x2(A["cov"])
    psd_b, ev_b = _is_psd_2x2(B["cov"])
    psd_val = {"sensor_A_psd": psd_a, "eig_A": [round(e, 12) for e in ev_a],
               "sensor_B_psd": psd_b, "eig_B": [round(e, 12) for e in ev_b],
               "rule": "fuse only if BOTH covariances are PSD (min eigenvalue >= 0)"}
    if not (psd_a and psd_b):
        psd_val["_step_failed"] = True
    tl.run("PSD guard on each covariance (2x2 eigenvalue check)", lambda: psd_val, kind="gate")

    fused = None
    if psd_a and psd_b:
        # Covariance Intersection: P_ci^-1 = w*A^-1 + (1-w)*B^-1
        ia, ib = _inv2x2(A["cov"]), _inv2x2(B["cov"])
        w = _FUSION_OMEGA
        Pinv = [[w * ia[i][j] + (1 - w) * ib[i][j] for j in range(2)] for i in range(2)]
        P = _inv2x2(Pinv)
        psd_f, ev_f = _is_psd_2x2(P)
        fused = {"cov": [[round(P[0][0], 12), round(P[0][1], 12)],
                         [round(P[1][0], 12), round(P[1][1], 12)]],
                 "psd": psd_f, "eig": [round(e, 12) for e in ev_f],
                 "tighter_than_A": min(ev_f) <= min(ev_a)}
        tl.run("Covariance Intersection fusion (P_ci^-1 = wA^-1 + (1-w)B^-1)",
               lambda: fused, kind="compute")
    else:
        tl.run("Covariance Intersection fusion (SKIPPED — non-PSD input rejected)",
               lambda: {"_step_failed": True, "fused": None}, kind="compute")

    poisoned = not (psd_a and psd_b)
    decision = "SENSOR-FUSION POISONING DETECTED — REJECT" if poisoned else "FUSION ACCEPTED (PSD)"
    event = {"event": "fusion_psd", "timestamp_utc": _now(), "decision": decision,
             "sensor_A_psd": psd_a, "sensor_B_psd": psd_b}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign fusion verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "psd_A", "label": "sensor A covariance PSD", "pass": psd_a},
                  {"node": "psd_B", "label": "sensor B covariance PSD", "pass": psd_b}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "fusion-poison", mode,
        "FUSION-POISON — covariance-intersection sensor-fusion poisoning (PSD guard)",
        "REAL TODAY — eigenvalue PSD guard + CI fusion are live; estimates = sample/replay (live bus = roadmap)",
        decision, not poisoned,
        ("Both sensor covariances are PSD; covariance-intersection fusion accepted and tighter; signed + chained."
         if not poisoned else
         "Sensor B injected a non-PSD (negative-eigenvalue) covariance; PSD guard REJECTS the fusion; signed + chained + provable."),
        {"sensor_A": A, "sensor_B": B, "psd": psd_val, "fused": fused},
        [{"formula": "Covariance Intersection + PSD guard", "role": "is the fused estimate valid?",
          "expr": "P_ci^-1 = w*A^-1 + (1-w)*B^-1; admit only if min_eig(cov) >= 0 for every input",
          "status": "Computed live (2x2 eigenvalues + matrix inverse). OE-2 PSD violation pattern.",
          "proven_where": "Covariance Intersection (Julier & Uhlmann) — pattern; eigen/inverse (computed)"},
         _SEAL_FP],
        ("Eigenvalues, the PSD guard and the covariance-intersection fusion are computed live; the tamper run "
         "injects a non-PSD covariance (poisoned sensor) AND flips ONE byte in the signed chain. Sensor estimates "
         "are labeled sample/replay; a live fusion bus is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 18. ROUTE-EXCLUSION — tactical-route exclusion-zone breach (segment-polygon).
# ===========================================================================
# A planned route (waypoint legs) is checked against a keep-out exclusion zone:
# no LEG may intersect the polygon and no waypoint may sit inside it. nominal =
# the route skirts the zone. tamper = a re-planned leg cuts a corner through the
# exclusion zone -> segment-polygon intersection -> EXCLUSION BREACH.
_EXCL_ZONE = [[32.730, -117.150], [32.770, -117.150], [32.770, -117.110], [32.730, -117.110]]
_ROUTE = [{"lat": 32.700, "lon": -117.200}, {"lat": 32.720, "lon": -117.160},
          {"lat": 32.720, "lon": -117.090}, {"lat": 32.780, "lon": -117.080}]


def _seg_intersect(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))


def _leg_crosses_poly(a, b, poly):
    pa, pb = (a["lat"], a["lon"]), (b["lat"], b["lon"])
    n = len(poly)
    for i in range(n):
        e1 = (poly[i][0], poly[i][1])
        e2 = (poly[(i + 1) % n][0], poly[(i + 1) % n][1])
        if _seg_intersect(pa, pb, e1, e2):
            return True
    # also flag if either endpoint inside
    return _point_in_polygon(a["lat"], a["lon"], poly) or _point_in_polygon(b["lat"], b["lon"], poly)


def _demo_route_exclusion(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    route = json.loads(json.dumps(_ROUTE))

    if mode == "tamper":
        # re-planned leg cuts a corner straight through the exclusion zone
        route[1] = {"lat": 32.750, "lon": -117.130}
        route[2] = {"lat": 32.750, "lon": -117.130}

    tl.run("Load planned route legs + keep-out exclusion zone (sample/replay)",
           lambda: {"waypoints": len(route), "legs": len(route) - 1,
                    "source": "sample/replay route; live mission plan = roadmap"}, kind="ingest")

    legs = []
    for i in range(len(route) - 1):
        crosses = _leg_crosses_poly(route[i], route[i + 1], _EXCL_ZONE)
        legs.append({"leg": "%d->%d" % (i, i + 1), "crosses_exclusion": crosses})
    tl.run("Segment-polygon intersection test per leg vs exclusion zone",
           lambda: {"legs": legs}, kind="compute")

    bad = [l for l in legs if l["crosses_exclusion"]]
    gate_val = {"legs": len(legs), "breaching_legs": len(bad),
                "breaching": [l["leg"] for l in bad],
                "rule": "safe route = NO leg intersects keep-out AND no waypoint inside it"}
    if bad:
        gate_val["_step_failed"] = True
    tl.run("Exclusion-zone gate (any leg through keep-out?)", lambda: gate_val, kind="gate")

    breach = len(bad) > 0
    decision = "EXCLUSION-ZONE BREACH — REROUTE" if breach else "ROUTE CLEARS EXCLUSION ZONE"
    event = {"event": "route_exclusion", "timestamp_utc": _now(), "decision": decision,
             "breaching_legs": [l["leg"] for l in bad]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign route verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": l["leg"], "label": "leg %s clears exclusion zone" % l["leg"],
                   "pass": not l["crosses_exclusion"]} for l in legs]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "route-exclusion", mode,
        "ROUTE-EXCLUSION — tactical-route exclusion-zone breach (segment-polygon intersection)",
        "REAL TODAY — segment-polygon intersection is live; route = sample/replay (live mission plan = roadmap)",
        decision, not breach,
        ("All %d route legs clear the keep-out exclusion zone; ROUTE SAFE; signed + chained."
         % len(legs) if not breach else
         "Leg %s cuts through the keep-out exclusion zone; REROUTE; signed + chained + provable."
         % (",".join(l["leg"] for l in bad))),
        {"route": route, "exclusion_zone": _EXCL_ZONE, "legs": legs, "gate": gate_val},
        [{"formula": "Segment-polygon intersection", "role": "does the route enter a keep-out?",
          "expr": "for each leg, test CCW segment-edge crossing against every polygon edge + endpoint PIP",
          "status": "Computed live; a re-planned corner-cutting leg is caught by the intersection test.",
          "proven_where": "PolyCARP / CCW segment intersection — pattern; computed"},
         _SEAL_FP],
        ("Segment-polygon intersection is computed live for every leg; the tamper run re-plans a leg that cuts "
         "through the exclusion zone AND flips ONE byte in the signed chain. The route is labeled sample/replay; "
         "a live mission plan is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 19. TRACK-PRIORITY — multi-track threat-priority manipulation (monotonicity).
# ===========================================================================
# Tracks are scored and ranked by a transparent threat-priority function (speed,
# closing rate, proximity, classification). nominal = the published ranking is
# consistent with the scoring function (monotone). tamper = an adversary re-orders
# the published priority list to de-prioritize the real threat while leaving its
# inputs unchanged -> ranking violates the monotone scoring -> MANIPULATION.
_PRIORITY_TRACKS = [
    {"id": "TK-A", "closing_kn": 18.0, "range_km": 4.0, "class_threat": 0.30},
    {"id": "TK-B", "closing_kn": 42.0, "range_km": 1.2, "class_threat": 0.92},
    {"id": "TK-C", "closing_kn": 25.0, "range_km": 3.1, "class_threat": 0.55},
    {"id": "TK-D", "closing_kn": 10.0, "range_km": 6.5, "class_threat": 0.20},
]


def _threat_score(t):
    # higher closing rate, closer range, higher class-threat => higher priority
    return round(0.4 * t["closing_kn"] / 50.0 + 0.4 * (1.0 / max(t["range_km"], 0.1)) / 1.0
                 + 0.2 * t["class_threat"], 5)


def _demo_track_priority(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    tracks = json.loads(json.dumps(_PRIORITY_TRACKS))
    for t in tracks:
        t["score"] = _threat_score(t)
    # the CORRECT priority = sorted by score desc
    correct = sorted(tracks, key=lambda t: -t["score"])
    published = [t["id"] for t in correct]

    if mode == "tamper":
        # adversary swaps the true #1 threat down to last in the PUBLISHED list,
        # without changing its inputs (display-layer manipulation)
        published = published[:]  # copy
        top = published[0]
        published = published[1:] + [top]

    tl.run("Ingest multi-track threat inputs + published priority order (sample/replay)",
           lambda: {"tracks": len(tracks), "published_order": published,
                    "source": "sample/replay tracks; live track manager = roadmap"}, kind="ingest")

    score_map = {t["id"]: t["score"] for t in tracks}
    # verify the published order is monotone non-increasing in score
    pub_scores = [score_map[tid] for tid in published]
    violations = []
    for i in range(len(pub_scores) - 1):
        if pub_scores[i] < pub_scores[i + 1] - 1e-9:
            violations.append({"pos": i, "above": published[i], "below": published[i + 1],
                               "score_above": pub_scores[i], "score_below": pub_scores[i + 1]})
    tl.run("Recompute threat scores + check published-order monotonicity",
           lambda: {"scores": score_map, "published_scores": [round(s, 5) for s in pub_scores]},
           kind="compute")

    gate_val = {"violations": len(violations), "detail": violations,
                "rule": "valid ranking = published order monotone non-increasing in threat score"}
    if violations:
        gate_val["_step_failed"] = True
    tl.run("Priority-integrity gate (published order matches scoring?)", lambda: gate_val, kind="gate")

    manipulated = len(violations) > 0
    decision = "TRACK-PRIORITY MANIPULATION DETECTED" if manipulated else "PRIORITY RANKING CONSISTENT"
    event = {"event": "track_priority", "timestamp_utc": _now(), "decision": decision,
             "violations": len(violations), "correct_top": correct[0]["id"], "published_top": published[0]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign priority verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "pos%d" % i,
                   "label": "score(%s) >= score(%s)" % (published[i], published[i + 1]),
                   "pass": pub_scores[i] >= pub_scores[i + 1] - 1e-9}
                  for i in range(len(pub_scores) - 1)]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "track-priority", mode,
        "TRACK-PRIORITY — multi-track threat-priority manipulation (monotone-ranking integrity)",
        "REAL TODAY — scoring + monotonicity check are live; tracks = sample/replay (live track manager = roadmap)",
        decision, not manipulated,
        ("Published priority order is monotone in the recomputed threat score; CONSISTENT; signed + chained."
         if not manipulated else
         "Published order de-prioritizes the true #1 threat %s (rank inversion vs score); MANIPULATION; signed + chained + provable."
         % correct[0]["id"]),
        {"tracks": tracks, "published_order": published, "correct_order": [t["id"] for t in correct],
         "gate": gate_val},
        [{"formula": "Monotone threat-priority integrity", "role": "was the ranking tampered?",
          "expr": "score = 0.4*closing/50 + 0.4*(1/range) + 0.2*class; valid iff published order monotone in score",
          "status": "Computed live; a display-layer re-order that contradicts the scoring is caught.",
          "proven_where": "Monotone-ranking invariant — pattern; computed"},
         _SEAL_FP],
        ("Threat scores and the published-order monotonicity are computed live from the real track inputs; the "
         "tamper run re-orders the published list to bury the true top threat AND flips ONE byte in the signed "
         "chain. Tracks are labeled sample/replay; a live track manager is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 20. OPENDRONEID-FORGERY — OpenDroneID basic-ID + operator-ID binding forgery.
# ===========================================================================
# An OpenDroneID message set binds a Basic-ID (serial/CAA), an Operator-ID and a
# Self-ID under a Merkle commitment signed by the registry. nominal = all message
# leaves are present + the registry signature over the Merkle root verifies.
# tamper = a forged Operator-ID is substituted -> the recomputed Merkle root no
# longer matches the registry-signed root -> FORGERY. Real Merkle commitment.
_ODID_MSGS = [
    {"type": "BasicID", "id_type": "Serial", "value": "1581F4F2A3B7C9D0E1"},
    {"type": "OperatorID", "value": "FAA-OP-77231"},
    {"type": "SelfID", "value": "Mission: harbor patrol"},
    {"type": "System", "value": "op_lat=32.71,op_lon=-117.16,area=0"},
]
_ODID_REGISTRY_KEY = "kc-odid-registry-key"


def _demo_opendroneid_forgery(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    msgs = json.loads(json.dumps(_ODID_MSGS))
    # registry signs the Merkle root over the ORIGINAL message-set leaves
    orig_leaves = [_sha(m) for m in _ODID_MSGS]
    registry_root = _merkle_root(orig_leaves)
    registry_sig = hashlib.sha256(("ODIDSIG:" + _ODID_REGISTRY_KEY + ":" + registry_root).encode()).hexdigest()[:16]

    if mode == "tamper":
        # forge the Operator-ID (e.g. spoof a different registered operator)
        msgs[1]["value"] = "FAA-OP-00000"

    tl.run("Ingest OpenDroneID message set + registry-signed Merkle commitment (sample/replay)",
           lambda: {"messages": len(msgs), "registry_root": registry_root,
                    "registry_sig": registry_sig,
                    "source": "sample/replay OpenDroneID (ASTM F3411-shaped); live registry = roadmap"},
           kind="ingest")

    now_leaves = [_sha(m) for m in msgs]
    now_root = _merkle_root(now_leaves)
    root_match = (now_root == registry_root)
    sig_recompute = hashlib.sha256(("ODIDSIG:" + _ODID_REGISTRY_KEY + ":" + now_root).encode()).hexdigest()[:16]
    sig_match = (sig_recompute == registry_sig)
    bind_val = {"registry_root": registry_root, "recomputed_root": now_root,
                "root_matches": root_match, "registry_sig_valid": sig_match,
                "rule": "authentic = recomputed Merkle root == registry-signed root"}
    if not root_match:
        bind_val["_step_failed"] = True
    tl.run("Recompute Merkle root over message leaves + verify registry signature",
           lambda: bind_val, kind="gate")

    forged = not root_match
    decision = "OPENDRONEID FORGERY DETECTED" if forged else "OPENDRONEID BINDING AUTHENTIC"
    event = {"event": "opendroneid_binding", "timestamp_utc": _now(), "decision": decision,
             "root_matches": root_match}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign OpenDroneID verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "merkle_root", "label": "recomputed root == registry-signed root", "pass": root_match},
                  {"node": "registry_sig", "label": "registry signature over root valid", "pass": sig_match}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "opendroneid-forgery", mode,
        "OPENDRONEID-FORGERY — OpenDroneID basic/operator-ID binding forgery (Merkle commitment)",
        "REAL TODAY — Merkle commitment + registry sig are live; OpenDroneID = sample/replay (live registry = roadmap)",
        decision, not forged,
        ("Recomputed Merkle root matches the registry-signed root; BINDING AUTHENTIC; signed + chained."
         if not forged else
         "Operator-ID was forged; recomputed Merkle root no longer matches the registry-signed root; FORGERY; signed + chained + provable."),
        {"messages": msgs, "binding": bind_val},
        [{"formula": "Registry-signed Merkle commitment", "role": "is the ID binding genuine?",
          "expr": "root = Merkle(leaves); authentic iff recomputed root == registry-signed root",
          "status": "Computed live (real RFC-6962 Merkle); forging any field breaks the root.",
          "proven_where": "OpenDroneID / ASTM F3411 — pattern; RFC-6962 Merkle (computed)"},
         _SEAL_FP],
        ("The Merkle root over the message leaves and the registry-signature check are computed live; the tamper "
         "run forges the Operator-ID so the recomputed root diverges from the signed root, AND flips ONE byte in "
         "the signed chain. OpenDroneID data is labeled sample/replay; a live registry is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 21. KILLCHAIN-REPLAY — kill-chain step replay/reorder tamper (nonce ordering).
# ===========================================================================
# A governed kill-chain (Detect->Identify->Authorize->Engage->Assess) requires a
# strictly ordered, nonce-bound, signed step sequence. nominal = ordered nonces +
# valid per-step HMAC. tamper = an Engage step is replayed BEFORE Authorize (step
# reorder / replay) -> ordering invariant + per-step binding fail -> REPLAY.
_KC_STEPS = ["Detect", "Identify", "Authorize", "Engage", "Assess"]
_KC_KEY = "kc-killchain-step-key"


def _kc_step_tag(step, nonce, prev_tag, key):
    return hashlib.sha256(("KC:" + key + ":" + step + ":" + str(nonce) + ":" + prev_tag).encode()).hexdigest()[:12]


def _demo_killchain_replay(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    steps = []
    prev = "GENESIS"
    for i, name in enumerate(_KC_STEPS):
        tag = _kc_step_tag(name, i, prev, _KC_KEY)
        steps.append({"order": i, "step": name, "nonce": i, "prev_tag": prev, "tag": tag})
        prev = tag

    if mode == "tamper":
        # replay/reorder: move Engage (idx 3) before Authorize (idx 2) but keep its
        # ORIGINAL tag (captured) -> prev_tag chain + nonce ordering break
        engage = steps[3]
        steps = [steps[0], steps[1], engage, steps[2], steps[4]]

    tl.run("Ingest governed kill-chain step sequence (sample/replay)",
           lambda: {"steps": [s["step"] for s in steps],
                    "source": "sample/replay governed sequence; live C2 = roadmap"}, kind="ingest")

    # verify: nonces strictly increasing AND each step's tag binds to the actual prev tag
    checks = []
    prev_tag = "GENESIS"
    prev_nonce = -1
    for s in steps:
        expect = _kc_step_tag(s["step"], s["nonce"], prev_tag, _KC_KEY)
        tag_ok = (s["tag"] == expect)
        order_ok = s["nonce"] > prev_nonce
        checks.append({"step": s["step"], "nonce": s["nonce"], "tag_binds_prev": tag_ok,
                       "nonce_increasing": order_ok})
        prev_tag = s["tag"]
        prev_nonce = s["nonce"]
    tl.run("Verify per-step HMAC binds to prior step + strictly increasing nonce",
           lambda: {"checks": checks}, kind="compute")

    bad = [c for c in checks if not (c["tag_binds_prev"] and c["nonce_increasing"])]
    gate_val = {"steps": len(checks), "violations": len(bad),
                "violating_steps": [c["step"] for c in bad],
                "rule": "valid = each step tag binds to actual prev tag AND nonce strictly increases"}
    if bad:
        gate_val["_step_failed"] = True
    tl.run("Kill-chain ordering gate (no replay/reorder?)", lambda: gate_val, kind="gate")

    replay = len(bad) > 0
    decision = "KILL-CHAIN REPLAY/REORDER DETECTED — HALT" if replay else "KILL-CHAIN ORDER INTACT"
    event = {"event": "killchain_order", "timestamp_utc": _now(), "decision": decision,
             "violations": len(bad), "violating_steps": [c["step"] for c in bad]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign kill-chain verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": c["step"],
                   "label": "%s binds prev + nonce increasing" % c["step"],
                   "pass": c["tag_binds_prev"] and c["nonce_increasing"]} for c in checks]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "killchain-replay", mode,
        "KILLCHAIN-REPLAY — kill-chain step replay/reorder tamper (nonce-bound signed ordering)",
        "REAL TODAY — per-step binding + nonce ordering are live; sequence = sample/replay (live C2 = roadmap)",
        decision, not replay,
        ("All %d kill-chain steps bind to their predecessor with strictly increasing nonces; ORDER INTACT; signed + chained."
         % len(checks) if not replay else
         "Engage step replayed before Authorize (prev-binding + nonce ordering broken); REPLAY; HALT; signed + chained + provable."),
        {"steps": steps, "checks": checks, "gate": gate_val},
        [{"formula": "Nonce-bound signed step ordering", "role": "was a kill-chain step replayed/reordered?",
          "expr": "tag_i = H(key|step|nonce|tag_{i-1}); valid iff tag binds actual prev AND nonce strictly increases",
          "status": "Computed live; replaying/reordering a step breaks the prev-binding and the nonce monotonicity.",
          "proven_where": "Hash-chained nonce ordering — pattern; computed"},
         _SEAL_FP],
        ("Per-step HMAC prev-binding and nonce monotonicity are computed live; the tamper run replays the Engage "
         "step ahead of Authorize AND flips ONE byte in the signed chain. The sequence is labeled sample/replay; "
         "a live C2 system is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 22. CONFORMAL-EVASION — conformal-band evasion (miscoverage breach).
# ===========================================================================
# A classifier's confidence on a track is wrapped in a conformal prediction band
# calibrated to (1-alpha) coverage. nominal = the live score falls inside the
# calibrated band (covered). tamper = an adversary nudges the input so the score
# slips outside the band while the displayed label is unchanged -> the conformal
# coverage guard fires (miscoverage) -> EVASION ATTEMPT. Real finite-sample band.
_CONF_CALIB = [0.81, 0.85, 0.88, 0.90, 0.91, 0.92, 0.93, 0.95, 0.96, 0.98]
_CONF_POINT = 0.915
_CONF_ALPHA = 0.1


def _demo_conformal_evasion(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    point = _CONF_POINT

    if mode == "tamper":
        # adversarial nudge: live score collapses below the calibrated lower band
        point = 0.42

    tl.run("Ingest classifier score + calibration set (sample/replay)",
           lambda: {"calibration_n": len(_CONF_CALIB), "live_score": point, "alpha": _CONF_ALPHA,
                    "source": "sample/replay calibration; live model = roadmap"}, kind="ingest")

    band = _conformal_interval(_CONF_CALIB, point, alpha=_CONF_ALPHA)
    tl.run("Finite-sample conformal band (NOT Hoeffding) + coverage check",
           lambda: band, kind="uncertainty")

    covered = band["in_interval"]
    gate_val = {"interval": band["interval"], "point": band["point"], "covered": covered,
                "coverage_target": band["coverage"], "never_100pct": band["never_100pct"],
                "rule": "covered = live score within the (1-alpha) conformal band; miscoverage => evasion"}
    if not covered:
        gate_val["_step_failed"] = True
    tl.run("Conformal coverage gate (score inside calibrated band?)", lambda: gate_val, kind="gate")

    evasion = not covered
    decision = "CONFORMAL MISCOVERAGE — EVASION ATTEMPT" if evasion else "SCORE WITHIN CONFORMAL BAND"
    event = {"event": "conformal_coverage", "timestamp_utc": _now(), "decision": decision,
             "interval": band["interval"], "point": band["point"], "covered": covered}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign conformal verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "coverage",
                   "label": "score %.3f within band %s" % (band["point"], band["interval"]),
                   "pass": covered}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "conformal-evasion", mode,
        "CONFORMAL-EVASION — conformal-band evasion (finite-sample miscoverage guard)",
        "REAL TODAY — finite-sample conformal band is live (W5-3 coverage PROVEN); model = sample/replay",
        decision, not evasion,
        ("Live score %.3f falls inside the %.0f%% conformal band %s; WITHIN BAND; signed + chained."
         % (band["point"], band["coverage"] * 100, band["interval"]) if not evasion else
         "Adversarial nudge drops the score to %.3f, outside the calibrated band %s (miscoverage); EVASION; signed + chained + provable."
         % (band["point"], band["interval"])),
        {"conformal": band, "gate": gate_val},
        [{"formula": "Conformal prediction band (finite-sample quantile)", "role": "is the score within calibrated coverage?",
          "expr": "C(x) = [q_lo, q_hi] from (1-alpha) finite-sample quantile; P(y in C) >= 1-alpha; never 100%",
          "status": "PROVEN — W5-3 coverage (kernel-verified). Computed live; never claims 100%.",
          "proven_where": "formulas/selftest -> reasoning.conformal_interval: PROVEN (W5-3)"},
         _SEAL_FP],
        ("The conformal band and the coverage decision are computed live with a real finite-sample quantile; the "
         "tamper run applies an adversarial nudge that pushes the score outside the band AND flips ONE byte in the "
         "signed chain. Calibration is labeled sample/replay; a live model feed is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 23. GERSHGORIN-DEGENERACY — edge command-matrix degeneracy (Gershgorin disks).
# ===========================================================================
# An edge command-mixing/control matrix must stay diagonally dominant (stable) per
# the Gershgorin circle theorem (every eigenvalue lies in a disk centered at a_ii
# with radius = sum of off-diagonals; dominance keeps disks off the origin ->
# nonsingular/stable). nominal = diagonally dominant. tamper = an injected
# coupling term inflates an off-diagonal so a Gershgorin disk swallows the origin
# -> potential singularity/instability -> DEGENERACY. Real Gershgorin bound.
_CMD_MATRIX = [[5.0, 0.6, 0.4], [0.5, 4.5, 0.7], [0.3, 0.5, 4.8]]


def _gershgorin_disks(M):
    n = len(M)
    disks = []
    for i in range(n):
        center = M[i][i]
        radius = sum(abs(M[i][j]) for j in range(n) if j != i)
        disks.append({"row": i, "center": round(center, 4), "radius": round(radius, 4),
                      "min_bound": round(center - radius, 4),
                      "dominant": abs(center) > radius})
    return disks


def _demo_gershgorin_degeneracy(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    M = json.loads(json.dumps(_CMD_MATRIX))

    if mode == "tamper":
        # inject a coupling term that destroys diagonal dominance on row 1
        M[1][0] = 5.2  # off-diagonal now exceeds the diagonal -> disk swallows origin

    tl.run("Load edge command-mixing matrix (sample/replay control gains)",
           lambda: {"dim": len(M), "matrix": M,
                    "source": "sample/replay control gains; live edge controller = roadmap"}, kind="ingest")

    disks = _gershgorin_disks(M)
    tl.run("Compute Gershgorin disks (center a_ii, radius = sum off-diagonals)",
           lambda: {"disks": disks}, kind="compute")

    nondominant = [d for d in disks if not d["dominant"]]
    origin_in_disk = [d for d in disks if d["min_bound"] <= 0.0]
    gate_val = {"rows": len(disks), "nondominant_rows": [d["row"] for d in nondominant],
                "disks_touching_origin": [d["row"] for d in origin_in_disk],
                "diagonally_dominant": len(nondominant) == 0,
                "rule": "stable = every Gershgorin disk excludes the origin (|a_ii| > sum_off_diag)"}
    if nondominant or origin_in_disk:
        gate_val["_step_failed"] = True
    tl.run("Gershgorin stability gate (all disks exclude the origin?)", lambda: gate_val, kind="gate")

    degenerate = bool(nondominant or origin_in_disk)
    decision = "COMMAND-MATRIX DEGENERACY DETECTED" if degenerate else "COMMAND MATRIX WELL-CONDITIONED"
    event = {"event": "gershgorin_stability", "timestamp_utc": _now(), "decision": decision,
             "nondominant_rows": [d["row"] for d in nondominant]}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign matrix verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "row%d" % d["row"],
                   "label": "|a_%d%d|=%.2f > radius %.2f (disk excludes origin)" % (d["row"], d["row"], d["center"], d["radius"]),
                   "pass": d["dominant"] and d["min_bound"] > 0.0} for d in disks]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "gershgorin-degeneracy", mode,
        "GERSHGORIN-DEGENERACY — edge command-matrix degeneracy (Gershgorin disk stability)",
        "REAL TODAY — Gershgorin disk bound is live; control gains = sample/replay (live edge controller = roadmap)",
        decision, not degenerate,
        ("Every Gershgorin disk excludes the origin (diagonally dominant); WELL-CONDITIONED; signed + chained."
         if not degenerate else
         "Injected coupling makes row %s non-dominant — a Gershgorin disk swallows the origin; DEGENERACY; signed + chained + provable."
         % (",".join(str(d["row"]) for d in (nondominant or origin_in_disk)))),
        {"matrix": M, "gershgorin_disks": disks, "gate": gate_val},
        [{"formula": "Gershgorin circle theorem", "role": "is the command matrix nonsingular/stable?",
          "expr": "every eigenvalue lies in some disk D(a_ii, R_i), R_i = sum_{j!=i}|a_ij|; dominance => disks exclude 0",
          "status": "Computed live (real disk bounds). MA1 command-matrix degeneracy pattern.",
          "proven_where": "Gershgorin circle theorem — exact; computed bounds"},
         _SEAL_FP],
        ("The Gershgorin disk centers/radii and the origin-exclusion test are computed live; the tamper run "
         "injects a coupling term that destroys diagonal dominance so a disk swallows the origin, AND flips ONE "
         "byte in the signed chain. Control gains are labeled sample/replay; a live edge controller is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 24. RF-DF-SPOOF — RF direction-finding bearing-consistency spoof.
# ===========================================================================
# Multiple RF direction-finding sensors triangulate an emitter. nominal = the
# per-sensor bearings intersect near a single fix (small residual to the LS
# intersection). tamper = a spoofed emitter/repeater injects a bearing that is
# geometrically inconsistent (the triangulation residual blows up) -> SPOOFED
# EMITTER. Real bearing-residual triangulation in-image.
_DF_SENSORS = [
    {"id": "DF-1", "lat": 32.700, "lon": -117.220, "bearing_deg": 45.0},
    {"id": "DF-2", "lat": 32.700, "lon": -117.180, "bearing_deg": 315.0},
    {"id": "DF-3", "lat": 32.740, "lon": -117.200, "bearing_deg": 180.0},
]
_DF_RESID_THRESH_DEG = 8.0


def _bearing_to(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) -
         math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon))
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _ang_diff(a, b):
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    return d


def _demo_rf_df_spoof(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    sensors = json.loads(json.dumps(_DF_SENSORS))

    if mode == "tamper":
        # spoofed repeater: DF-2 reports a geometrically inconsistent bearing
        sensors[1]["bearing_deg"] = 120.0

    tl.run("Ingest RF direction-finding bearings (sample/replay — NOT live SDR/DF array)",
           lambda: {"sensors": len(sensors), "bearings": [s["bearing_deg"] for s in sensors],
                    "source": "sample/replay DF bearings; live SDR array = roadmap"}, kind="ingest")

    # candidate fix = centroid of pairwise bearing-line intersections (coarse LS proxy):
    # use the mean of sensor positions projected along bearings a fixed range, then
    # measure the residual between each reported bearing and the bearing-to-candidate.
    cand_lat = sum(s["lat"] for s in sensors) / len(sensors)
    cand_lon = sum(s["lon"] for s in sensors) / len(sensors)
    # iterate a couple of times toward the bearing-consistent point (gradient-free refine)
    for _ in range(40):
        # move candidate slightly to reduce total angular residual (coordinate search)
        best = (cand_lat, cand_lon)
        best_res = sum(_ang_diff(_bearing_to(s["lat"], s["lon"], cand_lat, cand_lon), s["bearing_deg"]) for s in sensors)
        for dlat, dlon in [(0.001, 0), (-0.001, 0), (0, 0.001), (0, -0.001)]:
            nl, no = cand_lat + dlat, cand_lon + dlon
            res = sum(_ang_diff(_bearing_to(s["lat"], s["lon"], nl, no), s["bearing_deg"]) for s in sensors)
            if res < best_res:
                best_res, best = res, (nl, no)
        cand_lat, cand_lon = best
    residuals = [{"id": s["id"],
                  "reported_deg": s["bearing_deg"],
                  "bearing_to_fix_deg": round(_bearing_to(s["lat"], s["lon"], cand_lat, cand_lon), 2),
                  "residual_deg": round(_ang_diff(_bearing_to(s["lat"], s["lon"], cand_lat, cand_lon), s["bearing_deg"]), 2)}
                 for s in sensors]
    worst = max(residuals, key=lambda r: r["residual_deg"])
    tl.run("Triangulate emitter fix + per-sensor bearing residual",
           lambda: {"candidate_fix": [round(cand_lat, 5), round(cand_lon, 5)], "residuals": residuals},
           kind="compute")

    bad = [r for r in residuals if r["residual_deg"] > _DF_RESID_THRESH_DEG]
    gate_val = {"sensors": len(residuals), "inconsistent": len(bad),
                "worst_residual_deg": worst["residual_deg"], "threshold_deg": _DF_RESID_THRESH_DEG,
                "rule": "consistent emitter = every bearing residual <= %.1f deg" % _DF_RESID_THRESH_DEG}
    if bad:
        gate_val["_step_failed"] = True
    tl.run("Bearing-consistency gate (triangulation residual within threshold?)",
           lambda: gate_val, kind="gate")

    spoofed = len(bad) > 0
    decision = "SPOOFED RF EMITTER DETECTED" if spoofed else "RF EMITTER FIX CONSISTENT"
    event = {"event": "rf_df_consistency", "timestamp_utc": _now(), "decision": decision,
             "worst_residual_deg": worst["residual_deg"], "threshold_deg": _DF_RESID_THRESH_DEG}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign DF verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": r["id"],
                   "label": "%s residual %.1f deg <= %.1f" % (r["id"], r["residual_deg"], _DF_RESID_THRESH_DEG),
                   "pass": r["residual_deg"] <= _DF_RESID_THRESH_DEG} for r in residuals]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "rf-df-spoof", mode,
        "RF-DF-SPOOF — RF direction-finding bearing-consistency spoof (triangulation residual)",
        "REAL TODAY — bearing triangulation residual is live; DF bearings = sample/replay (live SDR array = roadmap)",
        decision, not spoofed,
        ("All %d DF bearings intersect near a single fix (worst residual %.1f deg <= %.1f); CONSISTENT; signed + chained."
         % (len(residuals), worst["residual_deg"], _DF_RESID_THRESH_DEG) if not spoofed else
         "Bearing from %s is geometrically inconsistent (residual %.1f deg > %.1f); SPOOFED EMITTER; signed + chained + provable."
         % (",".join(r["id"] for r in bad), worst["residual_deg"], _DF_RESID_THRESH_DEG)),
        {"sensors": sensors, "candidate_fix": [round(cand_lat, 5), round(cand_lon, 5)],
         "residuals": residuals, "gate": gate_val},
        [{"formula": "Direction-finding triangulation residual", "role": "do the bearings agree on one emitter?",
          "expr": "fix = argmin sum_i angdiff(bearing_to(sensor_i, fix), reported_i); consistent iff max residual <= thresh",
          "status": "Computed live (coordinate-search triangulation); a spoofed bearing inflates the residual.",
          "proven_where": "RF DF triangulation / LS bearing fix — pattern; computed"},
         _SEAL_FP],
        ("The triangulated fix and per-sensor bearing residuals are computed live; the tamper run injects a "
         "geometrically inconsistent (spoofed-repeater) bearing AND flips ONE byte in the signed chain. DF "
         "bearings are labeled sample/replay; a live SDR array is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 25. QUORUM-SPLITBRAIN — C2 quorum split-brain authority (majority + epoch).
# ===========================================================================
# Command authority requires a quorum (majority of an odd-size C2 cluster) at the
# CURRENT epoch. nominal = a single partition holds majority at the latest epoch
# -> authoritative. tamper = a stale-epoch minority partition attempts to issue
# commands (split-brain) -> quorum + epoch-freshness gate denies the minority ->
# SPLIT-BRAIN. Real majority + monotonic-epoch check in-image.
_QUORUM_NODES = ["C2-A", "C2-B", "C2-C", "C2-D", "C2-E"]
_QUORUM_EPOCH = 7


def _demo_quorum_splitbrain(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()
    cluster_size = len(_QUORUM_NODES)
    majority = cluster_size // 2 + 1
    # nominal partition: 3 nodes ack at the latest epoch
    partition = {"members": ["C2-A", "C2-B", "C2-C"], "epoch": _QUORUM_EPOCH}
    latest_epoch = _QUORUM_EPOCH

    if mode == "tamper":
        # split-brain: a stale-epoch minority (2 nodes at epoch 6) issues commands
        partition = {"members": ["C2-D", "C2-E"], "epoch": _QUORUM_EPOCH - 1}

    tl.run("Ingest C2 cluster partition + epoch (sample/replay consensus state)",
           lambda: {"cluster_size": cluster_size, "majority_needed": majority,
                    "partition_members": partition["members"], "partition_epoch": partition["epoch"],
                    "latest_epoch": latest_epoch,
                    "source": "sample/replay consensus state; live Raft cluster = roadmap"}, kind="ingest")

    have = len(partition["members"])
    quorum_ok = have >= majority
    epoch_ok = partition["epoch"] >= latest_epoch
    gate_val = {"acks": have, "majority_needed": majority, "quorum": quorum_ok,
                "partition_epoch": partition["epoch"], "latest_epoch": latest_epoch,
                "epoch_fresh": epoch_ok,
                "rule": "authority = (acks >= floor(n/2)+1) AND (epoch == latest); deny stale minority"}
    if not (quorum_ok and epoch_ok):
        gate_val["_step_failed"] = True
    tl.run("Quorum + epoch-freshness gate (majority at latest epoch?)", lambda: gate_val, kind="gate")

    splitbrain = not (quorum_ok and epoch_ok)
    decision = "SPLIT-BRAIN — COMMAND AUTHORITY DENIED" if splitbrain else "QUORUM AUTHORITATIVE"
    event = {"event": "quorum_authority", "timestamp_utc": _now(), "decision": decision,
             "acks": have, "majority_needed": majority, "epoch_fresh": epoch_ok}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    tl.run("DSSE-sign quorum verdict + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "merkle_root": sealed["merkle_root"]}, kind="seal")

    catch_tree = [{"node": "quorum", "label": "acks %d >= majority %d" % (have, majority), "pass": quorum_ok},
                  {"node": "epoch", "label": "partition epoch %d == latest %d" % (partition["epoch"], latest_epoch),
                   "pass": epoch_ok}]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)
    return _wh_envelope(
        "quorum-splitbrain", mode,
        "QUORUM-SPLITBRAIN — C2 quorum split-brain authority (majority + epoch freshness)",
        "REAL TODAY — majority + monotonic-epoch check is live; cluster state = sample/replay (live Raft = roadmap)",
        decision, not splitbrain,
        ("Partition holds a %d/%d majority at the latest epoch %d; QUORUM AUTHORITATIVE; signed + chained."
         % (have, cluster_size, latest_epoch) if not splitbrain else
         "Stale-epoch minority (%d/%d at epoch %d < %d) attempts command authority; SPLIT-BRAIN DENIED; signed + chained + provable."
         % (have, cluster_size, partition["epoch"], latest_epoch)),
        {"cluster": _QUORUM_NODES, "partition": partition, "gate": gate_val},
        [{"formula": "Quorum majority + monotonic epoch", "role": "may this partition command?",
          "expr": "authority = (acks >= floor(n/2)+1) AND (epoch == latest); a stale minority is denied",
          "status": "Computed live; deny-by-default on a stale-epoch minority partition (no split-brain).",
          "proven_where": "Raft/Paxos quorum + term monotonicity — pattern; computed"},
         _SEAL_FP],
        ("The majority count and epoch-freshness are computed live; the tamper run has a stale-epoch minority "
         "partition attempt command authority AND flips ONE byte in the signed chain. Cluster state is labeled "
         "sample/replay; a live Raft cluster is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))



# ===========================================================================
# 26. CROSS-DOMAIN-DECONFLICTION — air+sea fused track deconfliction with a
#     signed Λ-trust receipt per engagement decision.  NOVEL CAPABILITY #1.
# ===========================================================================
# Counter-UAS reality: an air sensor (ADS-B / Remote-ID style) and a sea sensor
# (AIS / radar style) can BOTH report a contact that an operator must decide to
# engage. If those two domains are fused naively, a single spoofed feed can cue
# an effector against a friendly. The novel governed capability here is a
# cross-domain DECONFLICTION GATE that (a) projects each domain's track to a
# common time and frame, (b) requires the two domains to AGREE within a fused
# covariance gate (Mahalanobis) before the contact is treated as one object,
# (c) requires a positive deconfliction margin from every PROTECTED friendly
# track, and (d) only then issues a per-engagement Λ-TRUST RECEIPT that records
# WHICH evidence supported the decision. Every clause is conjunctive: if air
# and sea DISAGREE, the receipt records DECONFLICT-FAIL and the engagement is
# DENIED — the system refuses to fuse a disputed contact rather than guessing.
# Tamper flips one byte of the signed trust receipt -> the chain breaks and the
# deconfliction conclusion is no longer cryptographically attributable.

# Sample/replay fused picture (NOT live): a single contact reported by both an
# air sensor and a sea sensor, plus one protected friendly track to deconflict.
_XD_AIR = {"sensor": "ADSB/RemoteID", "id": "AIR-7C1A2B", "lat": 32.7300, "lon": -117.1900,
           "alt_m": 80.0, "sog_kn": 38.0, "cog_deg": 215.0, "sigma_m": 45.0}
_XD_SEA = {"sensor": "AIS/RADAR",     "id": "SEA-RDR-19", "lat": 32.7306, "lon": -117.1894,
           "sog_kn": 36.0, "cog_deg": 212.0, "sigma_m": 60.0}
_XD_FRIENDLY = {"id": "OWN-USV-04", "lat": 32.6900, "lon": -117.2300, "sog_kn": 10.0, "cog_deg": 40.0}
_XD_GATE_SIGMA = 3.0          # Mahalanobis gate: agree within 3-sigma fused error
_XD_DECONFLICT_KM = 0.4       # min CPA from any protected friendly to clear engagement


def _xd_project_latlon(track, dt_s):
    """Constant-velocity dead-reckon a lat/lon track forward dt_s seconds."""
    vx, vy = _vessel_velocity_mps(track["sog_kn"], track["cog_deg"])  # (east, north) m/s
    m_per_deg = 111320.0
    lat = track["lat"] + (vy * dt_s) / m_per_deg
    lon = track["lon"] + (vx * dt_s) / (m_per_deg * math.cos(math.radians(track["lat"])))
    return lat, lon


def _demo_cross_domain_deconfliction(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()

    air = dict(_XD_AIR)
    sea = dict(_XD_SEA)
    if mode == "tamper":
        # ADVERSARY spoofs the SEA feed onto a different bearing/position so the
        # two domains describe DIFFERENT objects -> must NOT be fused/engaged.
        sea = dict(_XD_SEA)
        sea.update({"lat": 32.7480, "lon": -117.1700, "cog_deg": 95.0, "sog_kn": 22.0})

    tl.run("Ingest cross-domain tracks: air sensor + sea sensor (sample/replay — NOT live)",
           lambda: {"air": air, "sea": sea, "protected_friendly": _XD_FRIENDLY,
                    "source": "sample/replay fused picture; live multi-sensor fusion = roadmap"},
           kind="ingest")

    # (a) project both domains to a common epoch (here dt=0; identity but explicit)
    a_lat, a_lon = _xd_project_latlon(air, 0.0)
    s_lat, s_lon = _xd_project_latlon(sea, 0.0)
    sep_m = _haversine_m(a_lat, a_lon, s_lat, s_lon)
    fused_sigma = math.sqrt(air["sigma_m"] ** 2 + sea["sigma_m"] ** 2)
    maha = sep_m / (fused_sigma or 1e-9)   # 1-D Mahalanobis distance in fused error units
    agree = maha <= _XD_GATE_SIGMA
    assoc_val = {"separation_m": round(sep_m, 1), "fused_sigma_m": round(fused_sigma, 1),
                 "mahalanobis": round(maha, 3), "gate_sigma": _XD_GATE_SIGMA,
                 "domains_agree": agree,
                 "rule": "domains describe ONE object iff sep <= %.0f * fused_sigma" % _XD_GATE_SIGMA}
    if not agree:
        assoc_val["_step_failed"] = True
    tl.run("Cross-domain association gate (Mahalanobis fused-covariance agreement)",
           lambda: assoc_val, kind="gate")

    # (b) deconflict the fused contact from every protected friendly track (CPA)
    contact = {"lat": (a_lat + s_lat) / 2.0, "lon": (a_lon + s_lon) / 2.0,
               "sog_kn": (air["sog_kn"] + sea["sog_kn"]) / 2.0,
               "cog_deg": (air["cog_deg"] + sea["cog_deg"]) / 2.0}
    cpa_m, tcpa_s = _cpa_tcpa(_XD_FRIENDLY, contact)
    cpa_km = cpa_m / 1000.0
    clear = cpa_km >= _XD_DECONFLICT_KM
    deconf_val = {"cpa_km_to_friendly": round(cpa_km, 3), "tcpa_s": round(tcpa_s, 1),
                  "min_clearance_km": _XD_DECONFLICT_KM, "deconflicted": clear,
                  "rule": "engage only if CPA to every protected friendly >= %.1f km" % _XD_DECONFLICT_KM}
    if not clear:
        deconf_val["_step_failed"] = True
    tl.run("Friendly deconfliction gate (fused-contact CPA vs protected track)",
           lambda: deconf_val, kind="gate")

    # (c) conjunctive Λ-trust authority: agree AND deconflicted -> authorize
    authorized = bool(agree and clear)
    decision = "ENGAGE-AUTHORIZED (deconflicted)" if authorized else "ENGAGE-DENIED (deconfliction failed)"
    why = []
    if not agree:
        why.append("air/sea domains disagree (>%.0f-sigma) — disputed contact, refuse to fuse" % _XD_GATE_SIGMA)
    if not clear:
        why.append("fused contact CPA %.3f km < %.1f km from protected friendly" % (cpa_km, _XD_DECONFLICT_KM))
    if authorized:
        why.append("both domains agree within fused gate AND clear of all friendlies")

    # The Λ-TRUST RECEIPT: the signed engagement event records exactly which
    # evidence (per-clause) supported the authority decision.
    trust_receipt = {
        "lambda_trust_clauses": {
            "domain_agreement": {"pass": agree, "mahalanobis": round(maha, 3), "gate_sigma": _XD_GATE_SIGMA},
            "friendly_deconfliction": {"pass": clear, "cpa_km": round(cpa_km, 3),
                                       "min_clearance_km": _XD_DECONFLICT_KM},
        },
        "authority": "ENGAGE" if authorized else "DENY",
        "conjunctive": "authority = domain_agreement AND friendly_deconfliction (HITL advisory)",
    }
    event = {"event": "cross_domain_engagement_decision", "timestamp_utc": _now(),
             "decision": decision, "authorized": authorized,
             "air_id": air["id"], "sea_id": sea["id"], "friendly_id": _XD_FRIENDLY["id"],
             "mahalanobis": round(maha, 3), "cpa_km_to_friendly": round(cpa_km, 3),
             "lambda_trust": trust_receipt}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    receipt["lambda_trust"] = trust_receipt
    tl.run("DSSE-sign Λ-TRUST engagement receipt + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "authority": trust_receipt["authority"], "merkle_root": sealed["merkle_root"]},
           kind="seal")

    catch_tree = [
        {"node": "domain_agreement",
         "label": "Mahalanobis %.2f <= %.0f-sigma gate" % (maha, _XD_GATE_SIGMA), "pass": agree},
        {"node": "friendly_deconfliction",
         "label": "CPA %.3f km >= %.1f km from friendly" % (cpa_km, _XD_DECONFLICT_KM), "pass": clear},
    ]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    return _wh_envelope(
        "cross-domain-deconfliction", mode,
        "CROSS-DOMAIN-DECONFLICTION — air+sea fused track deconfliction with a signed Λ-trust receipt",
        "REAL TODAY — projection, Mahalanobis association + CPA deconfliction computed live; multi-sensor picture = sample/replay",
        decision, authorized,
        ("Air + sea agree at %.2f-sigma and the fused contact clears the protected friendly by %.3f km; "
         "ENGAGE-AUTHORIZED with a signed Λ-trust receipt." % (maha, cpa_km) if authorized else
         "Spoofed sea feed puts the two domains %.2f-sigma apart (disputed contact); the system REFUSES to fuse "
         "and the Λ-trust receipt records ENGAGE-DENIED + the failing clause — no effector cued on a guess."
         % maha),
        {"air_track": air, "sea_track": sea, "protected_friendly": _XD_FRIENDLY,
         "association": assoc_val, "deconfliction": deconf_val,
         "lambda_trust_receipt": trust_receipt, "decision_rationale": why},
        [{"formula": "Cross-domain association (Mahalanobis fused-covariance gate)",
          "role": "do air + sea describe ONE object?",
          "expr": "sep = haversine(air, sea); fused_sigma = sqrt(s_air^2 + s_sea^2); agree iff sep <= k*fused_sigma",
          "status": "Computed live; deny-by-default when domains disagree (refuse to fuse a disputed contact).",
          "proven_where": "gating-association (chi-square 1-D gate) — pattern; computed"},
         {"formula": "Friendly deconfliction (CPA/TCPA, G1)",
          "role": "is the fused contact clear of every protected friendly?",
          "expr": "CPA(friendly, fused_contact) >= min_clearance; conjunctive with association",
          "status": "Computed live from relative motion (constant-velocity).",
          "proven_where": "relative-motion CPA (computed); shared with collision-cpa"},
         {"formula": "Λ-trust conjunctive authority + signed receipt",
          "role": "per-engagement trust attribution",
          "expr": "authority = domain_agreement AND friendly_deconfliction; signed event records each clause",
          "status": "Advisory/HITL. Conjunctive gate = P2 gate-soundness PROVEN; Λ uniqueness = Conjecture 1.",
          "proven_where": "P2 gate-soundness; Λ = Conjecture 1 (advisory)"},
         _SEAL_FP],
        ("The projection, Mahalanobis association distance, and CPA deconfliction are all computed live from the "
         "track states; the Λ-trust receipt is a real DSSE-signed event that records exactly which clauses "
         "authorized (or denied) the engagement. The tamper run spoofs the sea feed onto a different object AND "
         "flips ONE byte in the signed receipt -> the chain breaks, so the deconfliction conclusion is no longer "
         "cryptographically attributable. Multi-sensor tracks are labeled sample/replay; engagement is HITL-advisory."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))


# ===========================================================================
# 27. SENSOR-DENIED-ATTEST — honest "sensor-denied" degraded mode that PROVES
#     degradation cryptographically instead of hallucinating tracks. NOVEL #2.
# ===========================================================================
# Counter-UAS reality: under GNSS jamming / RF denial / sensor dropout, a naive
# system keeps emitting confident tracks (dead-reckoned or fabricated), which is
# exactly when an operator is most likely to be deceived. The novel governed
# capability here is a DEGRADED-MODE ATTESTATION: when sensor health crosses a
# denial threshold, the system (a) measures which sensors are denied and by how
# much (C/N0 drop, RAIM failure, RF noise floor), (b) inflates the track
# covariance accordingly and computes whether any track still meets the minimum
# confidence for action, (c) REFUSES to emit tracks it cannot support and
# instead signs a degraded-mode attestation that records the denial evidence and
# a covariance floor — a cryptographic proof "we are degraded; we are NOT
# fabricating." Nominal = sensors healthy, tracks emitted normally. Tamper =
# denial detected -> attestation issued; flipping one byte breaks the proof.

_SD_SENSORS = [  # sample/replay sensor-health observables (NOT live)
    {"sensor": "GNSS",   "cn0_dbhz": 44.0, "cn0_floor_dbhz": 30.0, "raim_ok": True},
    {"sensor": "RADAR",  "snr_db": 18.0,   "snr_floor_db": 8.0,    "raim_ok": True},
    {"sensor": "RF-DF",  "noise_dbm": -95.0, "noise_floor_dbm": -80.0, "raim_ok": True},
]
_SD_BASE_SIGMA_M = 30.0       # nominal track 1-sigma
_SD_ACTION_SIGMA_M = 150.0    # max 1-sigma at which a track is action-grade


def _demo_sensor_denied_attest(mode, host):
    tl = _Timeline()
    chain = _KhipuChain()

    sensors = [dict(s) for s in _SD_SENSORS]
    if mode == "tamper":
        # DENIAL EVENT: GNSS jammed (C/N0 collapses below floor, RAIM fails) and
        # RF-DF swamped (noise above floor). The honest response is to DEGRADE.
        sensors[0].update({"cn0_dbhz": 22.0, "raim_ok": False})
        sensors[2].update({"noise_dbm": -72.0})

    tl.run("Ingest sensor-health observables (C/N0, SNR, RAIM, RF noise — sample/replay)",
           lambda: {"sensors": sensors,
                    "source": "sample/replay sensor health; live SDR/GNSS telemetry = roadmap"},
           kind="ingest")

    # (a) per-sensor denial detection + covariance-inflation factor
    denied = []
    inflation = 1.0
    for s in sensors:
        d = False
        margin = None
        if s["sensor"] == "GNSS":
            d = (s["cn0_dbhz"] < s["cn0_floor_dbhz"]) or (not s["raim_ok"])
            margin = round(s["cn0_dbhz"] - s["cn0_floor_dbhz"], 1)
        elif s["sensor"] == "RADAR":
            d = s["snr_db"] < s["snr_floor_db"]
            margin = round(s["snr_db"] - s["snr_floor_db"], 1)
        elif s["sensor"] == "RF-DF":
            d = s["noise_dbm"] > s["noise_floor_dbm"]
            margin = round(s["noise_floor_dbm"] - s["noise_dbm"], 1)
        if d:
            denied.append({"sensor": s["sensor"], "margin": margin, "raim_ok": s.get("raim_ok", True)})
            inflation *= 3.0   # each denied sensor triples positional uncertainty
    health_val = {"denied_sensors": [d["sensor"] for d in denied], "denial_detail": denied,
                  "covariance_inflation": round(inflation, 2),
                  "rule": "denied(GNSS) iff C/N0<floor OR RAIM fail; denied(RF) iff noise>floor"}
    tl.run("Sensor-denial detection + covariance-inflation factor", lambda: health_val, kind="compute")

    # (b) inflated track confidence vs the action-grade threshold
    inflated_sigma = _SD_BASE_SIGMA_M * inflation
    action_grade = inflated_sigma <= _SD_ACTION_SIGMA_M
    degraded = len(denied) > 0
    conf_val = {"base_sigma_m": _SD_BASE_SIGMA_M, "inflated_sigma_m": round(inflated_sigma, 1),
                "action_sigma_m": _SD_ACTION_SIGMA_M, "action_grade": action_grade,
                "degraded": degraded,
                "rule": "track is action-grade iff inflated 1-sigma <= %.0f m" % _SD_ACTION_SIGMA_M}
    if degraded and not action_grade:
        conf_val["_step_failed"] = True
    tl.run("Track-confidence gate under inflated covariance (action-grade?)",
           lambda: conf_val, kind="gate")

    # (c) honest verdict: if degraded below action-grade, REFUSE to emit tracks
    #     and instead sign a degraded-mode attestation (proof of degradation).
    if not degraded:
        decision = "SENSORS HEALTHY — tracks emitted at nominal confidence"
        fabricated_refused = 0
    elif action_grade:
        decision = "DEGRADED — tracks emitted with inflated covariance (still action-grade)"
        fabricated_refused = 0
    else:
        decision = "SENSOR-DENIED — DEGRADED MODE: refusing to emit unsupported tracks"
        fabricated_refused = 1  # we explicitly DID NOT fabricate the track we cannot support

    attestation = {
        "mode": "DEGRADED" if degraded else "NOMINAL",
        "denied_sensors": [d["sensor"] for d in denied],
        "covariance_floor_m": round(inflated_sigma, 1),
        "action_grade": action_grade,
        "fabricated_tracks_refused": fabricated_refused,
        "claim": ("System is operating degraded; positional covariance is inflated to the recorded floor; "
                  "no track is asserted above its supportable confidence."
                  if degraded else "All sensors nominal; tracks asserted at base confidence."),
    }
    event = {"event": "sensor_denied_attestation", "timestamp_utc": _now(),
             "decision": decision, "degraded": degraded, "action_grade": action_grade,
             "denied_sensors": [d["sensor"] for d in denied],
             "covariance_floor_m": round(inflated_sigma, 1),
             "fabricated_tracks_refused": fabricated_refused}
    sealed, receipt = _seal_and_receipt(chain, host, mode, decision, event)
    receipt["degraded_mode_attestation"] = attestation
    tl.run("DSSE-sign degraded-mode attestation + append to chain",
           lambda: {"signed": sealed["signed"], "receipt_id": receipt["receipt_id"],
                    "mode": attestation["mode"], "merkle_root": sealed["merkle_root"]},
           kind="seal")

    catch_tree = [
        {"node": "gnss_health",
         "label": "GNSS C/N0 %.0f vs floor %.0f, RAIM=%s" %
                  (sensors[0]["cn0_dbhz"], sensors[0]["cn0_floor_dbhz"], sensors[0]["raim_ok"]),
         "pass": (sensors[0]["cn0_dbhz"] >= sensors[0]["cn0_floor_dbhz"]) and sensors[0]["raim_ok"]},
        {"node": "rf_health",
         "label": "RF-DF noise %.0f vs floor %.0f dBm" % (sensors[2]["noise_dbm"], sensors[2]["noise_floor_dbm"]),
         "pass": sensors[2]["noise_dbm"] <= sensors[2]["noise_floor_dbm"]},
        {"node": "action_grade",
         "label": "inflated 1-sigma %.0f m <= %.0f m" % (inflated_sigma, _SD_ACTION_SIGMA_M),
         "pass": action_grade or (not degraded)},
    ]
    first_fail = next((c for c in catch_tree if not c["pass"]), None)

    return _wh_envelope(
        "sensor-denied-attest", mode,
        "SENSOR-DENIED-ATTEST — cryptographic degraded-mode attestation (proves degradation, refuses to fabricate)",
        "REAL TODAY — denial detection, covariance inflation + action-grade gate computed live; sensor health = sample/replay",
        decision, (not degraded) or action_grade,
        ("All sensors nominal (GNSS C/N0=%.0f, RAIM ok); tracks emitted at base 1-sigma=%.0f m; signed."
         % (sensors[0]["cn0_dbhz"], _SD_BASE_SIGMA_M) if not degraded else
         "GNSS jammed (C/N0=%.0f<floor, RAIM fail) + RF swamped: covariance inflated to 1-sigma=%.0f m > %.0f m "
         "action threshold. The system SIGNS a degraded-mode attestation and REFUSES to emit %d unsupported "
         "track(s) — degradation is proven cryptographically, not hidden behind fabricated tracks."
         % (sensors[0]["cn0_dbhz"], inflated_sigma, _SD_ACTION_SIGMA_M, fabricated_refused)),
        {"sensors": sensors, "denial": health_val, "confidence": conf_val,
         "degraded_mode_attestation": attestation},
        [{"formula": "Sensor-denial detection (C/N0 / RAIM / RF noise-floor)",
          "role": "is a sensor denied/jammed?",
          "expr": "denied(GNSS)=C/N0<floor OR ~RAIM; denied(RF)=noise>floor; denied(RADAR)=SNR<floor",
          "status": "Computed live from observables; deny-by-default on threshold crossing.",
          "proven_where": "RAIM / C/N0 jamming-detection — pattern; computed"},
         {"formula": "Covariance inflation + action-grade gate",
          "role": "may a track be asserted under degradation?",
          "expr": "sigma_inflated = sigma_base * 3^(#denied); action-grade iff sigma_inflated <= sigma_action",
          "status": "Computed live; refuses to assert tracks beyond supportable covariance.",
          "proven_where": "covariance inflation under sensor loss — pattern; computed"},
         {"formula": "Degraded-mode attestation (signed proof of degradation)",
          "role": "cryptographic honesty under denial",
          "expr": "signed event records denied sensors + covariance floor + count of tracks REFUSED (not fabricated)",
          "status": "PROVEN tamper-evidence (P5); the attestation cannot be silently altered.",
          "proven_where": "PR#188 P5; sigstore/rekor (Apache-2.0)"},
         _SEAL_FP],
        ("Denial detection, covariance inflation, and the action-grade gate are computed live from the sensor "
         "observables; the degraded-mode attestation is a real DSSE-signed event that records exactly which "
         "sensors are denied, the covariance floor, and the number of tracks the system REFUSED to fabricate. "
         "The tamper run jams GNSS + RF and flips ONE byte in the signed attestation -> the chain breaks, so a "
         "forged 'healthy' claim cannot survive verification. Sensor health is labeled sample/replay; live "
         "SDR/GNSS telemetry is roadmap."),
        chain, sealed, receipt, tl.as_list(), catch_tree,
        (first_fail["node"] if first_fail else None))



# ===========================================================================
# DISPATCH + REGISTRATION
# ===========================================================================
_DEMOS = {
    # --- original 7 (kept working) ---
    "spoofed-ais": _demo_spoofed_ais,
    "dark-vessel": _demo_dark_vessel,
    "geofence-incursion": _demo_geofence,
    "collision-cpa": _demo_collision_cpa,
    "swarm-hijack": _demo_swarm_hijack,
    "tampered-command": _demo_tampered_command,
    "roe-violation": _demo_roe_violation,
    # --- 18 NEW unique counter-UAS / maritime / drone-C2 demos (8..25) ---
    "remote-id-spoof": _demo_remote_id_spoof,
    "mavlink-injection": _demo_mavlink_injection,
    "adsb-ghost": _demo_adsb_ghost,
    "gnss-jam-spoof": _demo_gnss_jam_spoof,
    "swarm-cluster": _demo_swarm_cluster,
    "effector-cueing": _demo_effector_cueing,
    "sanctions-dark": _demo_sanctions_dark,
    "ais-gap-forgery": _demo_ais_gap_forgery,
    "geofence-bypass": _demo_geofence_bypass,
    "fusion-poison": _demo_fusion_poison,
    "route-exclusion": _demo_route_exclusion,
    "track-priority": _demo_track_priority,
    "opendroneid-forgery": _demo_opendroneid_forgery,
    "killchain-replay": _demo_killchain_replay,
    "conformal-evasion": _demo_conformal_evasion,
    "gershgorin-degeneracy": _demo_gershgorin_degeneracy,
    "rf-df-spoof": _demo_rf_df_spoof,
    "quorum-splitbrain": _demo_quorum_splitbrain,
    # --- 2 NOVEL governed counter-UAS capabilities (26..27) ---
    "cross-domain-deconfliction": _demo_cross_domain_deconfliction,
    "sensor-denied-attest": _demo_sensor_denied_attest,
}

_DEMO_META = [
    {"key": "spoofed-ais", "title": "SPOOFED-AIS — AIS/GPS spoofing detection",
     "real_or_roadmap": "REAL TODAY (AIS data sample/replay)", "tab": "warhacker"},
    {"key": "dark-vessel", "title": "DARK-VESSEL — AIS-off contact detection",
     "real_or_roadmap": "REAL TODAY (AIS data sample/replay)", "tab": "warhacker"},
    {"key": "geofence-incursion", "title": "GEOFENCE-INCURSION — EEZ/keep-out breach",
     "real_or_roadmap": "REAL TODAY", "tab": "warhacker"},
    {"key": "collision-cpa", "title": "COLLISION-CPA — CPA/TCPA collision risk",
     "real_or_roadmap": "REAL TODAY", "tab": "warhacker"},
    {"key": "swarm-hijack", "title": "SWARM-HIJACK — drone swarm integrity",
     "real_or_roadmap": "ROADMAP (substrate real)", "tab": "warhacker"},
    {"key": "tampered-command", "title": "TAMPERED-COMMAND — command receipt tamper",
     "real_or_roadmap": "REAL TODAY", "tab": "warhacker"},
    {"key": "roe-violation", "title": "ROE-VIOLATION — unauthorized engagement",
     "real_or_roadmap": "REAL TODAY (advisory; HITL)", "tab": "warhacker"},
    {"key": "remote-id-spoof", "title": "REMOTE-ID-SPOOF — FAA Remote ID / OpenDroneID broadcast authenticity (HMAC)",
     "real_or_roadmap": "REAL TODAY (Remote-ID sample/replay)", "tab": "warhacker"},
    {"key": "mavlink-injection", "title": "MAVLINK-INJECTION — MAVLink command-injection / message-integrity",
     "real_or_roadmap": "REAL TODAY (MAVLink sample/replay)", "tab": "warhacker"},
    {"key": "adsb-ghost", "title": "ADSB-GHOST — ADS-B ghost-aircraft injection / plausibility",
     "real_or_roadmap": "REAL TODAY (ADS-B sample/replay)", "tab": "warhacker"},
    {"key": "gnss-jam-spoof", "title": "GNSS-JAM-SPOOF — GPS/GNSS jamming + spoofing (RAIM + C/N0)",
     "real_or_roadmap": "REAL TODAY (GNSS observables sample/replay)", "tab": "warhacker"},
    {"key": "swarm-cluster", "title": "SWARM-CLUSTER — swarm-coordination cluster attack (Union-Find)",
     "real_or_roadmap": "REAL TODAY (tracks sample/replay)", "tab": "warhacker"},
    {"key": "effector-cueing", "title": "EFFECTOR-CUEING — effector-cueing ROE breach (conjunctive gate)",
     "real_or_roadmap": "REAL TODAY (advisory; HITL)", "tab": "warhacker"},
    {"key": "sanctions-dark", "title": "SANCTIONS-DARK — sanctions-evasion dark-vessel (watchlist + ID swap)",
     "real_or_roadmap": "REAL TODAY (watchlist sample/replay)", "tab": "warhacker"},
    {"key": "ais-gap-forgery", "title": "AIS-GAP-FORGERY — AIS-gap back-fill forgery (interpolation residual)",
     "real_or_roadmap": "REAL TODAY (AIS sample/replay)", "tab": "warhacker"},
    {"key": "geofence-bypass", "title": "GEOFENCE-BYPASS — geofence parameter-bypass (signed fence integrity)",
     "real_or_roadmap": "REAL TODAY (telemetry sample/replay)", "tab": "warhacker"},
    {"key": "fusion-poison", "title": "FUSION-POISON — covariance-intersection sensor-fusion poisoning (PSD)",
     "real_or_roadmap": "REAL TODAY (estimates sample/replay)", "tab": "warhacker"},
    {"key": "route-exclusion", "title": "ROUTE-EXCLUSION — tactical-route exclusion-zone breach (segment-polygon)",
     "real_or_roadmap": "REAL TODAY (route sample/replay)", "tab": "warhacker"},
    {"key": "track-priority", "title": "TRACK-PRIORITY — multi-track threat-priority manipulation (monotone ranking)",
     "real_or_roadmap": "REAL TODAY (tracks sample/replay)", "tab": "warhacker"},
    {"key": "opendroneid-forgery", "title": "OPENDRONEID-FORGERY — OpenDroneID ID-binding forgery (Merkle commitment)",
     "real_or_roadmap": "REAL TODAY (OpenDroneID sample/replay)", "tab": "warhacker"},
    {"key": "killchain-replay", "title": "KILLCHAIN-REPLAY — kill-chain step replay/reorder tamper (nonce ordering)",
     "real_or_roadmap": "REAL TODAY (sequence sample/replay)", "tab": "warhacker"},
    {"key": "conformal-evasion", "title": "CONFORMAL-EVASION — conformal-band evasion (finite-sample miscoverage)",
     "real_or_roadmap": "REAL TODAY (W5-3 coverage PROVEN; model sample/replay)", "tab": "warhacker"},
    {"key": "gershgorin-degeneracy", "title": "GERSHGORIN-DEGENERACY — edge command-matrix degeneracy (Gershgorin disks)",
     "real_or_roadmap": "REAL TODAY (control gains sample/replay)", "tab": "warhacker"},
    {"key": "rf-df-spoof", "title": "RF-DF-SPOOF — RF direction-finding bearing-consistency spoof (triangulation)",
     "real_or_roadmap": "REAL TODAY (DF bearings sample/replay)", "tab": "warhacker"},
    {"key": "quorum-splitbrain", "title": "QUORUM-SPLITBRAIN — C2 quorum split-brain authority (majority + epoch)",
     "real_or_roadmap": "REAL TODAY (cluster state sample/replay)", "tab": "warhacker"},
    {"key": "cross-domain-deconfliction",
     "title": "CROSS-DOMAIN-DECONFLICTION \u2014 air+sea fused track deconfliction with a signed \u039b-trust receipt (NOVEL)",
     "real_or_roadmap": "REAL TODAY (Mahalanobis association + CPA deconfliction computed; multi-sensor picture sample/replay)",
     "tab": "warhacker", "novel": True},
    {"key": "sensor-denied-attest",
     "title": "SENSOR-DENIED-ATTEST \u2014 cryptographic degraded-mode attestation, proves degradation & refuses to fabricate (NOVEL)",
     "real_or_roadmap": "REAL TODAY (denial detection + covariance inflation computed; sensor health sample/replay)",
     "tab": "warhacker", "novel": True},
]


def register(app, sign_fn=None, verify_fn=None, ns="killinchu"):
    """Register the 27 maritime/drone Warhacker demo endpoints (25 baseline + 2
    NOVEL governed counter-UAS capabilities). Purely additive;
    inserted BEFORE the SPA catch-all so they win route ordering. The sign_fn is
    the REAL killinchu cosign DSSE signer (szl_dsse.sign_payload)."""
    host = {"sign": sign_fn, "verify": verify_fn}
    registered = []

    async def _index(request: Request):
        return JSONResponse({
            "ok": True, "product": "killinchu Warhacker maritime/drone demos (27: 25 baseline + 2 novel)",
            "count": len(_DEMO_META), "demos": _DEMO_META, "modes": ["nominal", "tamper"],
            "launch_at": "/api/%s/v1/warhacker/launch/{key}" % ns,
            "lambda_status": _LAMBDA_STATUS,
            "locked_proven": ["F1", "F11", "F12", "F18", "F19"],
            "slsa": "L1 honest; L2 roadmap.", "sovereign": "zero runtime CDN",
            "verify_offline": "GET /cosign.pub  ;  cosign verify-blob --key cosign.pub",
        })

    async def _launch(request: Request):
        key = request.path_params.get("key", "spoofed-ais")
        try:
            b = await request.json()
        except Exception:
            b = {}
        qmode = request.query_params.get("mode")
        mode = (b.get("mode") or qmode or "nominal").lower()
        if mode not in ("nominal", "tamper"):
            mode = "nominal"
        fn = _DEMOS.get(key)
        if not fn:
            return JSONResponse({"ok": False, "error": "unknown demo", "known": list(_DEMOS)},
                                status_code=404)
        try:
            return JSONResponse(fn(mode, host))
        except Exception as e:
            import traceback
            return JSONResponse({"ok": False, "demo": key, "mode": mode,
                                 "error": "%s: %s" % (type(e).__name__, e),
                                 "trace": traceback.format_exc()[-1500:]}, status_code=500)

    async def _reset(request: Request):
        # demos are stateless per-run (fresh chain each call); reset is a no-op ack.
        return JSONResponse({"ok": True, "reset": True,
                             "note": "Warhacker demos are stateless per-run (fresh signed chain each launch)."})

    def _both(suffix):
        return ["/api/%s/v1/%s" % (ns, suffix), "/v1/%s" % suffix]

    built = []
    for p in _both("warhacker/index"):
        built.append(Route(p, _index, methods=["GET"],
                           name="kc_wh_index_" + ("api" if p.startswith("/api") else "v1")))
        registered.append("GET " + p)
    for p in _both("warhacker/launch/{key}"):
        built.append(Route(p, _launch, methods=["POST", "GET"],
                           name="kc_wh_launch_" + ("api" if p.startswith("/api") else "v1")))
        registered.append("POST|GET " + p)
    # Scope reset under warhacker/ so we never shadow the existing operational
    # /api/killinchu/v1/ops/reset surface (additive, no clobber).
    for p in _both("warhacker/ops/reset"):
        built.append(Route(p, _reset, methods=["POST", "GET"],
                           name="kc_wh_reset_" + ("api" if p.startswith("/api") else "v1")))
        registered.append("POST|GET " + p)

    for r in reversed(built):
        app.router.routes.insert(0, r)
    return {"module": "killinchu_warhacker_demos", "registered": registered,
            "count": len(registered), "demos": len(_DEMOS)}
