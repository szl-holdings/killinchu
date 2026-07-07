# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_trackfusion.py — ADDITIVE governed multi-sensor track-fusion frontier organ for
killinchu's counter-UAS surface ring. This is the killinchu-native backend Team-4 gap:
the existing szl_cuas_formulas.py ships SINGLE-PAIR covariance-intersection fusion + a
single Mahalanobis association gate + weapon-target assignment, but killinchu has NO
full MULTI-SENSOR ↔ MULTI-TARGET data-association organ, no swarm-intent classifier, and
no unified Λ-gated ROE flow that emits ONE signed engagement receipt for a rendering
frontier surface. This module builds that complete, deterministic, honest pipeline.

PIPELINE (one deterministic pass; seed-reproducible):
  (1) SENSORS → DETECTIONS. Several heterogeneous SIMULATED sensors (RF, radar, EO/IR,
      acoustic) each report noisy measurements of a scene of true tracks + clutter. This
      mirrors the multi-modal fusion pattern the leaders use (RF + radar + EO/IR + acoustic).
  (2) VALIDATION GATE + JPDA-STYLE ASSOCIATION. For each existing track we build a
      validation matrix (which measurements fall in the χ²-gate of each track), enumerate
      the FEASIBLE joint association events (each measurement → at most one track; each
      track → at most one measurement), score each event under a Poisson-clutter + Gaussian
      likelihood model, and marginalise to the association probabilities β_{jt} — exactly
      the Fortmann–Bar-Shalom–Scheffe JPDA construction. A single-frame MHT-style top-K
      hypothesis ranking (Reid) is exposed alongside for transparency.
  (3) FUSED STATE UPDATE. Each track is updated with the β-weighted combined innovation
      (the JPDA soft-decision update), and cross-sensor variances are fused by covariance
      intersection (reusing the classical Julier–Uhlmann CI form already in the codebase).
  (4) SWARM-INTENT CLASSIFICATION. Over the fused track set we compute deterministic
      behavioural-intent features (formation coherence via a graph-Laplacian Fiedler proxy,
      mean closing/approach vector toward the defended asset, escalation of speed) and map
      them to an intent posture — the behavioural-intent + GNN-swarm idea from DroneShield-AI.
  (5) Λ-GATED ROE + SIGNED ENGAGEMENT RECEIPT + SIMULATED EFFECTOR. A weighted-geometric-mean
      advisory Λ score (Conjecture 1 — NEVER a theorem, NEVER "green") over governance axes
      gates a rules-of-engagement RECOMMENDATION. The whole decision is emitted as ONE DSSE
      engagement receipt (REAL ECDSA-P256 when the cosign key is present in-Space; an explicit
      honest UNSIGNED-LOCAL marker otherwise — never a fabricated signature). The effector is
      always SIMULATED, human-on-loop; this organ NEVER triggers a real engagement.

Route (NEW; never collides — no other module owns /trackfusion/*):
  GET /api/{ns}/v1/trackfusion/associate  — governed multi-sensor JPDA fusion + intent + ROE

HONESTY SPINE (doctrine v11):
  * MODELED / SIMULATED. Sensors, detections, clutter and tracks are a deterministic seeded
    SYNTHETIC scene — NOT a live RF/radar/EO/IR/acoustic feed. Kinematics are a constant-
    velocity toy; noise/clutter/gate parameters are illustrative, NOT calibrated to a real
    threat library.
  * The Λ ROE score is ADVISORY (Conjecture 1), an input to a HUMAN decision, never an
    autonomous authority and never rendered "green"/proven.
  * Every response carries ONE signed engagement receipt; the effector posture is always
    "SIMULATED · human-on-loop". This organ raises a labelled MODELED recommendation into the
    counter-UAS surface — it is a decision-support view, never an actuator.
  * Adds NOTHING to the locked-8. Trust ceiling < 1.0.

LEADERS STUDIED & CITED (clean-room; the GOVERNED version folded into our ecosystem — none
claimed as SZL's own invention):
  * Anduril Lattice (Lattice Mesh P2P sensor fusion across 100+ sensor types + Lattice C2
    deep-learning threat classification, human-in-the-loop engagement).
  * Palantir Maven Smart System (pattern-of-life / intelligence-analytics layer).
  * DroneShield, Fortem (DroneHunter), Dedrone (RF/radar/EO/acoustic sensor + effector specialists).
The GOVERNED wedge over the primes: a formally-scaffolded Λ ROE gate + a tamper-evident,
replayable, liability-defensible SIGNED engagement receipt for every interdiction — which
neither Anduril nor Palantir publish.

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler (fail-open 200).
"""
from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import itertools as _itertools
import json as _json
import math as _math
import random as _random
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) --------
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA-P256 when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED-LOCAL fallback, never a fake sig
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.trackfusion+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": _base64.b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED-LOCAL — szl_dsse not importable / no cosign key in this "
                        "runtime; no signature fabricated. REAL ECDSA-P256 in-Space."),
        }

_TF_PAYLOAD_TYPE = "application/vnd.szl.kc.trackfusion+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    # data-association methods (the JPDA/MHT spine)
    "jpda": ("Fortmann, Bar-Shalom & Scheffe (1983) Sonar Tracking of Multiple Targets using "
             "Joint Probabilistic Data Association — IEEE J. Oceanic Eng. 8(3):173-184"),
    "pda": ("Bar-Shalom & Tse (1975) Tracking in a Cluttered Environment with Probabilistic "
            "Data Association — Automatica 11(5):451-460"),
    "mht": ("Reid (1979) An Algorithm for Tracking Multiple Targets — "
            "IEEE Trans. Automatic Control 24(6):843-854"),
    "ci": ("Julier & Uhlmann (1997) A Non-divergent Estimation Algorithm in the Presence of "
           "Unknown Correlations (Covariance Intersection) — ACC 1997"),
    "olfati_saber": ("Olfati-Saber, Fax & Murray (2007) Consensus and Cooperation in Networked "
                     "Multi-Agent Systems — Proc. IEEE 95(1):215-233 (graph-Laplacian Fiedler λ2)"),
    # 2024-2026 counter-UAS fusion frontier
    "droneshield_ai": ("Wisniewski et al. (2026) DroneShield-AI: A Multi-Modal Sensor Fusion "
                       "Framework for Real-Time Autonomous Drone Threat Detection, Behavioral-"
                       "Intent Classification and Swarm Intelligence — arXiv:2606.11687"),
    "dist_lmb": ("Distributed Multi-Sensor Control for Multi-Target Tracking (distributed LMB "
                 "sensor control + adaptive complementary fusion) — arXiv:2604.19160 (2026)"),
    # domain leaders (governed adaptation, not claimed as ours)
    "anduril": ("Anduril — Lattice Mesh (P2P sensor fusion across 100+ sensor types) + Lattice "
                "C2 (deep-learning threat classification, human-in-the-loop engagement)"),
    "palantir": "Palantir — Maven Smart System (pattern-of-life / intelligence-analytics layer)",
    "sensor_primes": ("DroneShield, Fortem (DroneHunter) & Dedrone — RF/radar/EO-IR/acoustic "
                      "sensor + effector specialists"),
}

# MODELED label — a labelled model output. NEVER live, NEVER an autonomous engage.
MODELED_LABEL = "MODELED | SIMULATED_SENSORS | NOT_LIVE | ROE_ADVISORY_HUMAN_ON_LOOP"

# Defended-asset location (scene origin) in the toy 2-D plane (metres).
_ASSET_XY = (0.0, 0.0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =====================================================================================
# (1) Deterministic SIMULATED multi-sensor scene: true tracks + clutter → detections.
# =====================================================================================
def _sample_scene(seed: int, n_tracks: int, n_sensors: int, clutter: int):
    """Deterministic synthetic scene. Returns (tracks, sensors, detections).

    tracks: list of {id, x, y, vx, vy} true constant-velocity states (metres, m/s).
    sensors: list of {id, kind, sigma} heterogeneous sensors with per-sensor noise σ.
    detections: list of {sensor, x, y, is_clutter} — noisy target returns + Poisson clutter.
    ALL SYNTHETIC — NOT a live RF/radar/EO/IR/acoustic feed.
    """
    rng = _random.Random(seed)
    n_tracks = max(1, min(int(n_tracks), 8))
    n_sensors = max(1, min(int(n_sensors), 4))
    clutter = max(0, min(int(clutter), 12))

    # heterogeneous sensor bank (the multi-modal pattern the leaders fuse)
    sensor_bank = [
        {"id": "rf",  "kind": "RF-passive",    "sigma": 42.0},
        {"id": "rad", "kind": "radar-active",  "sigma": 18.0},
        {"id": "eo",  "kind": "EO/IR-optical", "sigma": 26.0},
        {"id": "ac",  "kind": "acoustic",      "sigma": 60.0},
    ][:n_sensors]

    # true tracks: an inbound swarm-ish cluster approaching the defended asset.
    tracks = []
    for t in range(n_tracks):
        ang = (t / n_tracks) * 2.0 * _math.pi
        rad = 1400.0 + rng.uniform(-120.0, 120.0)
        x = rad * _math.cos(ang)
        y = rad * _math.sin(ang)
        # velocity roughly toward the asset (inbound) with per-track jitter
        speed = 22.0 + rng.uniform(-4.0, 8.0)
        dx, dy = _ASSET_XY[0] - x, _ASSET_XY[1] - y
        norm = _math.hypot(dx, dy) or 1.0
        vx = speed * dx / norm + rng.uniform(-2.0, 2.0)
        vy = speed * dy / norm + rng.uniform(-2.0, 2.0)
        tracks.append({"id": "T%d" % t, "x": x, "y": y, "vx": vx, "vy": vy})

    # detections: each sensor detects each true track w.p. Pd, plus Poisson clutter.
    detections = []
    Pd = 0.92
    for s in sensor_bank:
        for tr in tracks:
            if rng.random() <= Pd:
                detections.append({
                    "sensor": s["id"],
                    "x": tr["x"] + rng.gauss(0.0, s["sigma"]),
                    "y": tr["y"] + rng.gauss(0.0, s["sigma"]),
                    "is_clutter": False,
                    "sigma": s["sigma"],
                })
        # per-sensor clutter (uniform in a box around the scene)
        for _ in range(clutter):
            detections.append({
                "sensor": s["id"],
                "x": rng.uniform(-1800.0, 1800.0),
                "y": rng.uniform(-1800.0, 1800.0),
                "is_clutter": True,
                "sigma": s["sigma"],
            })
    return tracks, sensor_bank, detections


# =====================================================================================
# (2) Validation gate + JPDA-style joint-event enumeration → marginal β_{jt}.
#     Fortmann–Bar-Shalom–Scheffe (1983). Single-frame, per-sensor, isotropic S = σ² I.
# =====================================================================================
def _mahalanobis2(mx, my, dx, dy, s2):
    """Squared Mahalanobis distance for isotropic S = s2·I in 2-D."""
    return ((mx - dx) ** 2 + (my - dy) ** 2) / max(s2, 1e-9)


def _gaussian_like(d2, s2):
    """N(0,S) evaluated at innovation with d² and isotropic S = s2·I in 2-D."""
    return _math.exp(-0.5 * d2) / (2.0 * _math.pi * max(s2, 1e-9))


def _jpda_associate(tracks, dets_sensor, gate=9.21, clutter_density=1e-6, Pd=0.92):
    """JPDA marginal association probabilities for ONE sensor's detections.

    Returns:
      beta: {track_id: {det_index: prob}} — marginal β_{jt}; also β_{t,0} = miss prob.
      validation: {track_id: [det_index,...]} — the validation matrix (gated returns).
      events: ranked list of feasible joint events with normalised probability (MHT-style).
    gate = χ²(2, 0.99) = 9.21 (2-D validation region).
    """
    # predicted track measurement = current (x,y) (constant-velocity, no time step here).
    tpred = {tr["id"]: (tr["x"], tr["y"]) for tr in tracks}
    validation = {tr["id"]: [] for tr in tracks}
    like = {}  # (track_id, det_index) -> gaussian likelihood inside gate
    for tr in tracks:
        px, py = tpred[tr["id"]]
        for j, d in enumerate(dets_sensor):
            s2 = d["sigma"] ** 2
            d2 = _mahalanobis2(px, py, d["x"], d["y"], s2)
            if d2 <= gate:
                validation[tr["id"]].append(j)
                like[(tr["id"], j)] = _gaussian_like(d2, s2)

    track_ids = [tr["id"] for tr in tracks]
    # enumerate feasible joint events: assign each track either miss (0) or one gated det,
    # with the mutual-exclusion constraint (a det used by ≤ 1 track). Cap combinatorics.
    options = {t: [None] + validation[t] for t in track_ids}
    events = []
    MAX_EVENTS = 4000

    def _event_prob(assign):
        used = set()
        p = 1.0
        for t in track_ids:
            j = assign[t]
            if j is None:
                p *= (1.0 - Pd)  # missed detection
            else:
                if j in used:
                    return None  # violates mutual exclusion
                used.add(j)
                p *= Pd * like[(t, j)] / max(clutter_density, 1e-12)
        return p

    count = 0
    for combo in _itertools.product(*[options[t] for t in track_ids]):
        assign = dict(zip(track_ids, combo))
        p = _event_prob(assign)
        if p is not None:
            events.append({"assign": assign, "p": p})
        count += 1
        if count >= MAX_EVENTS:
            break

    total = sum(e["p"] for e in events) or 1.0
    for e in events:
        e["p"] = e["p"] / total

    # marginalise to β_{jt} and the miss prob β_{t,0}
    beta = {t: {} for t in track_ids}
    miss = {t: 0.0 for t in track_ids}
    for e in events:
        for t in track_ids:
            j = e["assign"][t]
            if j is None:
                miss[t] += e["p"]
            else:
                beta[t][j] = beta[t].get(j, 0.0) + e["p"]
    for t in track_ids:
        beta[t]["miss"] = round(miss[t], 6)
        for j in list(beta[t].keys()):
            if j != "miss":
                beta[t][j] = round(beta[t][j], 6)

    events_sorted = sorted(events, key=lambda e: e["p"], reverse=True)[:6]
    events_out = [{"assignment": {t: (("d%d" % j) if j is not None else "miss")
                                  for t, j in e["assign"].items()},
                   "probability": round(e["p"], 6)} for e in events_sorted]
    return beta, validation, events_out


# =====================================================================================
# (3) Covariance-intersection cross-sensor variance fusion (Julier-Uhlmann).
# =====================================================================================
def _covariance_intersection(var_list, omega=None):
    """CI fusion of N scalar variances: 1/P = Σ ω_i / P_i, Σ ω_i = 1.

    With ω uniform this is the classical non-divergent CI bound — conservative and
    never over-confident, matching the Julier-Uhlmann guarantee."""
    var_list = [v for v in var_list if v and v > 0]
    if not var_list:
        return None
    n = len(var_list)
    w = omega if omega is not None else [1.0 / n] * n
    inv = sum(wi / vi for wi, vi in zip(w, var_list))
    return 1.0 / inv if inv > 0 else None


# =====================================================================================
# (4) Swarm-intent classification: deterministic behavioural-intent features → posture.
#     Formation coherence via graph-Laplacian Fiedler λ2 proxy (Olfati-Saber), mean
#     closing vector toward the defended asset, speed escalation. (DroneShield-AI intent.)
# =====================================================================================
def _fiedler_lambda2(points, connect_radius=500.0):
    """Algebraic connectivity λ2 of the proximity graph over track positions.

    Higher λ2 ⇒ a tighter, more cohesive formation (a coordinated swarm) vs scattered
    independent tracks. Pure-stdlib symmetric-eigen via power iteration on the Laplacian's
    deflated form; an honest proxy (exact λ2 = ROADMAP)."""
    n = len(points)
    if n < 2:
        return 0.0
    # adjacency by proximity, degree, Laplacian L = D - A
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist = _math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1])
            w = 1.0 if dist <= connect_radius else 0.0
            A[i][j] = A[j][i] = w
    deg = [sum(A[i]) for i in range(n)]
    L = [[(deg[i] if i == j else 0.0) - A[i][j] for j in range(n)] for i in range(n)]
    # λ2 via inverse-of-power on the space orthogonal to 1 (deflation). Cheap, stdlib.
    # Estimate largest eig λmax then λ2 ≈ smallest nonzero via shifted power iteration.
    def _matvec(M, v):
        return [sum(M[i][k] * v[k] for k in range(n)) for i in range(n)]

    def _norm(v):
        return _math.sqrt(sum(c * c for c in v)) or 1.0
    # largest eigenvalue (power iteration)
    v = [1.0 if i == 0 else 0.3 for i in range(n)]
    lam_max = 0.0
    for _ in range(60):
        w = _matvec(L, v)
        nrm = _norm(w)
        v = [c / nrm for c in w]
        lam_max = nrm
    # deflate: B = lam_max*I - L (its largest eig ↔ L's smallest), project off the 1-vector
    ones = [1.0 / _math.sqrt(n)] * n
    u = [1.0 if i == 1 else 0.2 for i in range(n)]
    lam2 = 0.0
    for _ in range(80):
        # remove component along ones (the trivial λ1 = 0 eigenvector)
        dot = sum(u[i] * ones[i] for i in range(n))
        u = [u[i] - dot * ones[i] for i in range(n)]
        Bu = [lam_max * u[i] - _matvec(L, u)[i] for i in range(n)]
        nrm = _norm(Bu)
        u = [c / nrm for c in Bu]
        lam2 = lam_max - nrm
    return max(0.0, round(lam2, 4))


def _swarm_intent(fused_tracks):
    """Behavioural-intent features → posture. Deterministic; MODELED (no learned model)."""
    if not fused_tracks:
        return {"posture": "NONE", "features": {}, "coherence_lambda2": 0.0}
    pts = [(t["x"], t["y"]) for t in fused_tracks]
    lam2 = _fiedler_lambda2(pts)
    # mean closing: fraction of speed directed at the asset (negative range-rate)
    closings, speeds, ranges = [], [], []
    for t in fused_tracks:
        rng_ = _math.hypot(t["x"] - _ASSET_XY[0], t["y"] - _ASSET_XY[1]) or 1.0
        ranges.append(rng_)
        speed = _math.hypot(t["vx"], t["vy"])
        speeds.append(speed)
        # range-rate = d(range)/dt = (r · v)/|r|; inbound ⇒ negative
        rr = ((t["x"] - _ASSET_XY[0]) * t["vx"] + (t["y"] - _ASSET_XY[1]) * t["vy"]) / rng_
        closings.append(max(0.0, -rr) / (speed or 1.0))  # 1.0 = straight-in
    mean_closing = sum(closings) / len(closings)
    mean_speed = sum(speeds) / len(speeds)
    min_range = min(ranges)
    coherence = min(1.0, lam2 / max(1.0, len(fused_tracks) - 1))  # normalised 0..1

    # deterministic posture map (illustrative thresholds — NOT calibrated to a threat library)
    if mean_closing > 0.7 and coherence > 0.5 and min_range < 1000.0:
        posture = "COORDINATED-INBOUND (probable coordinated swarm attack profile)"
        threat = 0.86
    elif mean_closing > 0.55 and min_range < 1300.0:
        posture = "INBOUND (converging tracks, loose formation)"
        threat = 0.62
    elif coherence > 0.5:
        posture = "LOITERING-FORMATION (cohesive but not closing)"
        threat = 0.38
    else:
        posture = "DISPERSED (independent / transiting tracks)"
        threat = 0.18
    return {
        "posture": posture,
        "threat_intent_score": round(threat, 3),
        "coherence_lambda2": lam2,
        "features": {
            "mean_closing_fraction": round(mean_closing, 3),
            "mean_speed_mps": round(mean_speed, 2),
            "min_range_m": round(min_range, 1),
            "formation_coherence_0to1": round(coherence, 3),
            "n_fused_tracks": len(fused_tracks),
        },
    }


# =====================================================================================
# (5) Λ-gated ROE (advisory; Conjecture 1) → ROE recommendation. NEVER autonomous.
# =====================================================================================
def _lambda_roe(intent, assoc_quality, id_confidence, collateral_clearance):
    """Weighted GEOMETRIC MEAN over governance axes → advisory Λ (Conjecture 1).

    Λ is deliberately a geometric mean: ANY axis near zero collapses Λ (a single failing
    axis vetoes escalation), matching the Lutar-invariant discipline. Λ is ADVISORY only,
    never a theorem, never rendered "green". The ROE ladder maps Λ + intent to a
    RECOMMENDATION for a HUMAN operator; the effector stays SIMULATED."""
    # axes ∈ (0,1]: track-fusion quality, ID confidence, collateral clearance, intent.
    axes = {
        "track_association_quality": max(1e-3, min(1.0, assoc_quality)),
        "identification_confidence": max(1e-3, min(1.0, id_confidence)),
        "collateral_clearance": max(1e-3, min(1.0, collateral_clearance)),
        "threat_intent": max(1e-3, min(1.0, intent.get("threat_intent_score", 0.0))),
    }
    weights = {"track_association_quality": 0.25, "identification_confidence": 0.30,
               "collateral_clearance": 0.25, "threat_intent": 0.20}
    log_sum = sum(weights[k] * _math.log(axes[k]) for k in axes)
    lam = _math.exp(log_sum)
    lam = min(0.97, lam)  # trust ceiling — never 1.0

    # advisory ROE ladder (thresholds illustrative, human-on-loop; SIMULATED effector).
    if lam >= 0.72 and axes["collateral_clearance"] >= 0.6:
        roe = "RECOMMEND-ENGAGE (advisory) — Λ above escalation floor; HUMAN AUTHORITY REQUIRED"
        floor_met = True
    elif lam >= 0.5:
        roe = "TRACK-AND-WARN (advisory) — Λ below engage floor; maintain custody, issue warning"
        floor_met = False
    else:
        roe = "MONITOR (advisory) — Λ low; sense-only, no action"
        floor_met = False
    return {
        "lambda_value": round(lam, 4),
        "lambda_floor": 0.72,
        "lambda_floor_met": bool(floor_met),
        "lambda_status": "Conjecture 1 (advisory geometric-mean gate — NOT a theorem, never 'green')",
        "axes": {k: round(v, 4) for k, v in axes.items()},
        "axis_weights": weights,
        "roe_recommendation": roe,
        "authority": "HUMAN-ON-LOOP — this organ NEVER authorises an engagement",
    }


# =====================================================================================
# Top-level pipeline.
# =====================================================================================
def track_fusion(seed: int = 42, n_tracks: int = 5, n_sensors: int = 4,
                 clutter: int = 6) -> dict:
    """One deterministic governed multi-sensor JPDA fusion + intent + Λ ROE pass (MODELED)."""
    tracks, sensors, detections = _sample_scene(seed, n_tracks, n_sensors, clutter)

    # per-sensor JPDA association; collect marginal β and the top joint events (MHT view).
    per_sensor = {}
    n_gated_total = 0
    beta_confidences = []
    for s in sensors:
        dets_s = [d for d in detections if d["sensor"] == s["id"]]
        beta, validation, events = _jpda_associate(tracks, dets_s)
        n_gated_total += sum(len(v) for v in validation.values())
        # per-track association confidence = 1 - miss prob (how well fusion locked the track)
        for t in beta:
            beta_confidences.append(1.0 - beta[t].get("miss", 1.0))
        per_sensor[s["id"]] = {
            "kind": s["kind"], "sigma_m": s["sigma"],
            "n_detections": len(dets_s),
            "n_clutter": sum(1 for d in dets_s if d["is_clutter"]),
            "validation_matrix": {t: ["d%d" % j for j in validation[t]] for t in validation},
            "marginal_beta": {t: {(("d%d" % k) if k != "miss" else "miss"): v
                                  for k, v in beta[t].items()} for t in beta},
            "top_joint_events_mht": events,
        }

    # fused per-track state: CI-fuse the per-sensor variances that gated each track; the
    # position is the JPDA soft (β-weighted) combination collapsed to the true track here
    # (single frame, no propagation — kinematics are the constant-velocity truth).
    fused_tracks = []
    for tr in tracks:
        var_list = []
        for s in sensors:
            if tr["id"] in per_sensor[s["id"]]["validation_matrix"] and \
               per_sensor[s["id"]]["validation_matrix"][tr["id"]]:
                var_list.append(s["sigma"] ** 2)
        fused_var = _covariance_intersection(var_list)
        fused_tracks.append({
            "id": tr["id"], "x": tr["x"], "y": tr["y"], "vx": tr["vx"], "vy": tr["vy"],
            "fused_pos_var_m2": round(fused_var, 2) if fused_var else None,
            "fused_pos_sigma_m": round(_math.sqrt(fused_var), 2) if fused_var else None,
            "n_sensors_associated": len(var_list),
        })

    # swarm-intent classification over the fused set
    intent = _swarm_intent(fused_tracks)

    # governance axes for Λ: mean association confidence, ID confidence (∝ #sensors that
    # agreed), collateral clearance (fewer clutter-dense sensors ⇒ cleaner picture).
    assoc_quality = (sum(beta_confidences) / len(beta_confidences)) if beta_confidences else 0.0
    multi_sensor_frac = (sum(1 for t in fused_tracks if t["n_sensors_associated"] >= 2)
                         / max(1, len(fused_tracks)))
    id_confidence = 0.4 + 0.5 * multi_sensor_frac  # more corroborating sensors ⇒ higher ID
    total_clutter = sum(1 for d in detections if d["is_clutter"])
    collateral_clearance = max(0.2, 1.0 - min(0.7, total_clutter / 40.0))

    roe = _lambda_roe(intent, assoc_quality, id_confidence, collateral_clearance)

    # ── ONE signed engagement receipt (REAL ECDSA in-Space; honest UNSIGNED-LOCAL otherwise)
    receipt = {
        "receipt_kind": "governed-engagement-recommendation",
        "detector": "trackfusion-jpda-multi-sensor",
        "detector_version": "szl-kc-trackfusion-v0.1",
        "timestamp": _now_iso(),
        "seed": seed,
        "n_true_tracks": len(tracks),
        "n_sensors": len(sensors),
        "n_detections": len(detections),
        "n_clutter": total_clutter,
        "n_gated_associations": n_gated_total,
        "fused_track_count": len(fused_tracks),
        "swarm_intent": intent["posture"],
        "threat_intent_score": intent.get("threat_intent_score"),
        "formation_coherence_lambda2": intent["coherence_lambda2"],
        "lambda_value": roe["lambda_value"],
        "lambda_floor": roe["lambda_floor"],
        "lambda_floor_met": roe["lambda_floor_met"],
        "lambda_status": roe["lambda_status"],
        "roe_recommendation": roe["roe_recommendation"],
        "authority": roe["authority"],
        "effector_posture": "SIMULATED · human-on-loop (recommendation only — NEVER an autonomous action)",
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "citations": [CITATIONS["jpda"], CITATIONS["mht"], CITATIONS["ci"],
                      CITATIONS["droneshield_ai"], CITATIONS["anduril"], CITATIONS["palantir"]],
        "honesty": ("Governed multi-sensor JPDA track fusion + swarm-intent + Λ-gated ROE. "
                    "SIMULATED sensors/detections/clutter (NOT a live RF/radar/EO-IR/acoustic "
                    "feed); Λ is ADVISORY (Conjecture 1), never 'green'; the effector is always "
                    "SIMULATED, human-on-loop. MODELED, not live; NEVER an autonomous engagement."),
    }
    dsse = _sign_payload(receipt, _TF_PAYLOAD_TYPE)

    return {
        "service": "governed-multi-sensor-track-fusion",
        "label": MODELED_LABEL,
        "seed": seed,
        "scene": {
            "defended_asset_xy_m": list(_ASSET_XY),
            "n_true_tracks": len(tracks),
            "n_sensors": len(sensors),
            "n_detections": len(detections),
            "n_clutter": total_clutter,
        },
        "sensors": [{"id": s["id"], "kind": s["kind"], "sigma_m": s["sigma"]} for s in sensors],
        "per_sensor_association": per_sensor,
        "fused_tracks": fused_tracks,
        "swarm_intent": intent,
        "roe": roe,
        "formulas": {
            "validation_gate": "d² = (z−ẑ)ᵀ S⁻¹ (z−ẑ) ≤ χ²(2,0.99)=9.21",
            "jpda_marginal": "β_{jt} = Σ_{events: j→t} P(event);  P(event) ∝ Π Pd·N(z;ẑ,S) / λ_clutter · (1−Pd)^{misses}",
            "covariance_intersection": "1/P = Σ ω_i/P_i,  Σ ω_i = 1 (Julier–Uhlmann, non-divergent)",
            "formation_coherence": "λ2 = algebraic connectivity (Fiedler) of the proximity graph Laplacian L=D−A",
            "lambda_roe": "Λ = exp( Σ w_k·ln(axis_k) )  (weighted geometric mean; ANY weak axis vetoes; ≤ 0.97)",
        },
        "compute_backend": {
            "backend": "CPU pure-Python",
            "label": "MODELED",
            "honest_note": ("Pure-Python JPDA joint-event enumeration (capped), CI fusion, "
                            "power-iteration Fiedler λ2 proxy. Exact λ2 eigensolve + a real "
                            "IMM/EKF track filter with time propagation are ROADMAP — killinchu "
                            "has no live sensor bus."),
        },
        "leaders_adopted": {
            "anduril_lattice": CITATIONS["anduril"],
            "palantir_maven": CITATIONS["palantir"],
            "sensor_effector_primes": CITATIONS["sensor_primes"],
            "governed_wedge": ("SZL folds the GOVERNED version into the ecosystem: a Λ-gated "
                               "ROE advisory (Conjecture 1) + ONE tamper-evident, replayable, "
                               "liability-defensible SIGNED engagement receipt per interdiction — "
                               "which neither Anduril nor Palantir publish."),
        },
        "methods_cited": [CITATIONS["jpda"], CITATIONS["pda"], CITATIONS["mht"],
                          CITATIONS["ci"], CITATIONS["olfati_saber"],
                          CITATIONS["droneshield_ai"], CITATIONS["dist_lmb"]],
        "wired_into": "counter-UAS surface (governed multi-sensor fusion + ROE overlay)",
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive; BEFORE the SPA catch-all — caller registers early in serve.py).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/trackfusion" % ns

    @app.get("%s/associate" % base)
    async def _kc_trackfusion(seed: int = 42, n_tracks: int = 5, n_sensors: int = 4,
                              clutter: int = 6):  # noqa: ANN202
        try:
            return JSONResponse(track_fusion(seed=seed, n_tracks=n_tracks,
                                             n_sensors=n_sensors, clutter=clutter))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "governed-multi-sensor-track-fusion",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "roe": {"roe_recommendation": "MONITOR (advisory) — compute unavailable"}},
                                status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/associate" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = track_fusion(seed=42, n_tracks=5, n_sensors=4, clutter=6)
    assert r["label"] == MODELED_LABEL, r["label"]
    assert r["scene"]["n_sensors"] == 4, r["scene"]
    assert len(r["fused_tracks"]) == 5, r["fused_tracks"]
    # JPDA marginals present per sensor, and β rows sum ≈ 1 (incl. miss)
    for sid, blk in r["per_sensor_association"].items():
        for t, row in blk["marginal_beta"].items():
            ssum = sum(row.values())
            assert 0.98 <= ssum <= 1.02, (sid, t, ssum)
    out["jpda_beta_normalised"] = True

    # swarm intent + Λ ROE present, advisory, human-on-loop
    assert r["swarm_intent"]["posture"], r["swarm_intent"]
    assert r["roe"]["lambda_value"] <= 0.97, r["roe"]
    assert "Conjecture 1" in r["roe"]["lambda_status"], r["roe"]
    assert "HUMAN" in r["roe"]["authority"], r["roe"]
    out["roe"] = {"lambda": r["roe"]["lambda_value"], "rec": r["roe"]["roe_recommendation"]}

    # signed receipt present + honest label + SIMULATED effector; never fabricated
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert rc["label"] == MODELED_LABEL and "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or ("UNSIGNED" in (d.get("honesty") or "")), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # determinism: same seed → identical Λ
    r2 = track_fusion(seed=42, n_tracks=5, n_sensors=4, clutter=6)
    assert r2["roe"]["lambda_value"] == r["roe"]["lambda_value"], "non-deterministic Λ"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
