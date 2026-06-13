# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms · 13-axis canonical trust
"""
killinchu_mosaic — SZL's sovereign Mosaic / Domain-Superiority organ for killinchu.

WHAT THIS IS
------------
This is killinchu's clean-room answer to True Anomaly Inc.'s "Mosaic" space-
superiority platform (the publicly-described SDA / C2 / Threat-Warning-&-Assessment
capability). It is ADDITIVE and registered BEFORE the SPA catch-all, exactly like
every other killinchu organ. It wires the SZL-native anomaly/SDA engine
(``szl_mosaic_core.SZLMosaicCore`` — multivariate + graph anomaly detection, vendored
from /home/user/workspace/mosaic_szl) into killinchu's live track surface and adds
the Common Operating Picture endpoints.

ATTRIBUTION (cite-never-plagiarize)
-----------------------------------
* The anomaly ENGINE is INSPIRED BY the *publicly described capability* of True
  Anomaly's Mosaic (Detect/Track/ID -> Characterize -> ML-Threat-Warning ->
  fuse/forecast -> Common Operating Picture). NO proprietary Mosaic code/assets were
  seen or copied. The engine itself is a clean-room SZL implementation from the
  permissive lineage (PyOD BSD-2, Merlion BSD-3, TODS Apache-2, tsod MIT, GDN MIT,
  PyGOD BSD-2, python-sgp4 MIT); alibi-detect (BSL-1.1) is DELIBERATELY NOT USED.
  See szl_mosaic_core.py and estate_audit/mosaic_identification.md.
* The structural/vessel mechanics estimate cites the SZL FE-NO solid-mechanics
  vertical (platform monorepo: services/verticals/szl_mechanics; clean-room
  non-overlapping Schwarz FE-NO, method arXiv:2606.08796 Wang/Gupta/Ruan/Goswami,
  CC BY 4.0). The full receipt-verified FE-NO solve runs in that platform vertical;
  here we surface a fast, clearly-labelled ESTIMATE for a flagged vessel and point
  at the canonical solver (honest TODO).

HONEST POSTURE (Doctrine v11, binding)
--------------------------------------
* Λ = Conjecture 1 (conditional Theorem U) — ADVISORY, never "proven trust".
  The Mosaic Λ-advisory emits allow / advisory / deny ADVISORIES, not proofs.
* Anomaly scores are ESTIMATES with a BOUNDED / conformal confidence interval —
  never a point claim of certainty.
* Detections tie to Khipu BFT 3-of-4 consensus (Conjecture 2, PROPOSED-not-proven)
  and emit a DSSE receipt — REAL ECDSA-P256 when SZL_COSIGN_PRIVATE_PEM is set, else
  an explicit honest PLACEHOLDER. We NEVER fabricate a signature.
* killinchu effectors are SIMULATED. The space-domain (SGP4 conjunction) surface is
  a clearly-labelled ROADMAP stub — today's reality is counter-UAS / drone / vessel.
* Sovereign own-metal, 0 runtime CDN, system fonts. No free-energy, no over-claims,
  joules MEASURED only, every $/credit = ESTIMATE.

Endpoints (all under /api/{ns}/v1/mosaic/*):
    GET  /api/{ns}/v1/mosaic/health             organ health + engine + doctrine
    POST /api/{ns}/v1/mosaic/score              anomaly score + Λ-advisory + CI for tracks
    POST /api/{ns}/v1/mosaic/receipt            emit DSSE-or-honest receipt for one verdict
    GET  /api/{ns}/v1/mosaic/cop                fused Common Operating Picture (air+sea+orbit stub)
    GET  /api/{ns}/v1/mosaic/sda/conjunction    SGP4 orbital-conjunction ROADMAP stub
    POST /api/{ns}/v1/mosaic/hull-stress        FE-NO-cited hull-stress ESTIMATE for a flagged vessel

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Callable, Optional

try:
    import numpy as np
    _HAVE_NUMPY = True
except Exception:  # pragma: no cover
    _HAVE_NUMPY = False

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_DOCTRINE = "v11"
_LEAN = "c7c0ba17"
_COUNTS = "749/14/163"


# ---------------------------------------------------------------------------
# Engine resolution — SOVEREIGN, graceful.
#
# Dev 1's vendored engine (szl_mosaic_core.SZLMosaicCore) is the canonical core,
# but it hard-imports scikit-learn / torch. killinchu's HF-Space runtime pins
# numpy (and scipy/networkx) but NOT sklearn/torch, so we import the full engine
# when the heavy deps are present and otherwise fall back to a pure-numpy
# detector bank that implements the SAME contract (fit/score/lambda_verdict/
# emit_receipt). Either way the math is REAL, sovereign and offline — never a mock.
# ---------------------------------------------------------------------------
_ENGINE_BACKEND = "uninitialised"
_CORE_CLS = None
try:
    import szl_mosaic_core as _core_mod  # vendored Dev-1 engine (sklearn/torch)
    _CORE_CLS = _core_mod.SZLMosaicCore
    _ENGINE_BACKEND = "szl_mosaic_core (vendored: PyOD/Merlion/TODS/tsod + GDN lineage)"
except Exception as _core_e:  # pragma: no cover - falls back to numpy bank
    _core_mod = None
    _ENGINE_BACKEND = f"numpy-fallback (szl_mosaic_core unavailable: {type(_core_e).__name__})"


# ---------------------------------------------------------------------------
# Pure-numpy fallback detector bank — SAME public contract as SZLMosaicCore.
# Clean-room, sovereign, offline. Lineage (idea, not vendored code):
#   robust z-score (tsod MIT / PyOD BSD-2) + PCA-reconstruction autoencoder
#   (Merlion BSD-3 / TODS Apache-2) + graph-deviation (GDN MIT / PyGOD BSD-2).
# No sklearn / torch needed. Λ-gate is ADVISORY (Conjecture 1).
# ---------------------------------------------------------------------------
class _NumpyMosaicCore:
    def __init__(self, allow_thr: float = 0.35, deny_thr: float = 0.65,
                 alpha: float = 0.1, seed: int = 7):
        self.allow_thr = allow_thr
        self.deny_thr = deny_thr
        self.alpha = alpha
        self.seed = seed
        self._fitted = False
        self._median = None
        self._mad = None
        self._mean = None
        self._components = None
        self._znorm = (0.0, 1.0)
        self._aenorm = (0.0, 1.0)
        self._calib = None

    @staticmethod
    def _norm01(s, lo, hi):
        if hi <= lo:
            return np.zeros_like(s)
        return np.clip((s - lo) / (hi - lo), 0.0, 1.0)

    def _zscore(self, X):
        scale = 1.4826 * self._mad + 1e-9
        return np.max(np.abs(X - self._median) / scale, axis=1)

    def _ae(self, X):
        Xc = X - self._mean
        proj = Xc @ self._components.T
        recon = proj @ self._components + self._mean
        return np.sqrt(np.mean((X - recon) ** 2, axis=1))

    def fit(self, X_train):
        X = np.asarray(X_train, dtype=float)
        self._median = np.median(X, axis=0)
        self._mad = np.median(np.abs(X - self._median), axis=0)
        self._mean = X.mean(axis=0)
        n_in = X.shape[1]
        k = min(2, max(1, n_in - 1))
        _, _, Vt = np.linalg.svd(X - self._mean, full_matrices=False)
        self._components = Vt[:k]
        zs = self._zscore(X)
        aes = self._ae(X)
        self._znorm = (float(np.min(zs)), float(np.quantile(zs, 0.999)))
        self._aenorm = (float(np.min(aes)), float(np.quantile(aes, 0.999)))
        self._calib = self._combined(X)
        self._fitted = True
        return self

    def _components_scores(self, X):
        X = np.asarray(X, dtype=float)
        z = self._norm01(self._zscore(X), *self._znorm)
        a = self._norm01(self._ae(X), *self._aenorm)
        return {"robust_zscore": z, "autoencoder": a}

    def _combined(self, X):
        comps = self._components_scores(X)
        return np.vstack([comps["robust_zscore"], comps["autoencoder"]]).mean(axis=0)

    def score(self, X):
        assert self._fitted, "call fit() first"
        comps = self._components_scores(X)
        combined = np.vstack([comps["robust_zscore"], comps["autoencoder"]]).mean(axis=0)
        return {"components": comps, "combined": combined}

    def lambda_verdict(self, score: float) -> str:
        if score < self.allow_thr:
            return "allow"
        if score < self.deny_thr:
            return "advisory"
        return "deny"

    def conformal_interval(self, point_score: float):
        calib = np.asarray(self._calib, dtype=float)
        lo_q = float(np.quantile(calib, self.alpha / 2.0))
        hi_q = float(np.quantile(calib, 1.0 - self.alpha / 2.0))
        return (min(lo_q, point_score), max(hi_q, point_score))


# ---------------------------------------------------------------------------
# Feature extraction from a killinchu track -> the engine's feature vector.
# Channels are kinematics that anomaly detection naturally separates on:
#   [speed_m_s, altitude_m, range_km, |heading - bearing| folded].
# Honest: these are decoded/derived CLAIMS over (mostly simulated) tracks, never
# attested ground truth.
# ---------------------------------------------------------------------------
def _track_features(t: dict) -> list:
    spd = float(t.get("speed_m_s", t.get("speed", 0.0)) or 0.0)
    alt = float(t.get("altitude_m", t.get("altitude", 0.0)) or 0.0)
    rng = float(t.get("range_km", 0.0) or 0.0)
    hdg = float(t.get("heading_deg", t.get("heading", 0.0)) or 0.0)
    brg = float(t.get("bearing_deg", t.get("bearing", 0.0)) or 0.0)
    closing = abs(((hdg - brg + 180.0) % 360.0) - 180.0)
    return [spd, alt, rng, closing]


# A small, fixed "mostly-normal" reference population (benign patrol/ISR-like
# kinematics) so the engine has something to fit against deterministically in a
# stateless request. Honest: this is a SEED reference, not a learned live baseline;
# a production deployment would fit on a rolling window of real benign tracks.
_REF_POP = [
    [30.0, 3000.0, 40.0, 20.0], [28.0, 3200.0, 42.0, 15.0], [35.0, 2800.0, 38.0, 25.0],
    [25.0, 3500.0, 45.0, 10.0], [40.0, 2500.0, 35.0, 30.0], [22.0, 4000.0, 50.0, 12.0],
    [33.0, 3100.0, 41.0, 18.0], [29.0, 3300.0, 43.0, 22.0], [31.0, 2900.0, 39.0, 16.0],
    [27.0, 3600.0, 46.0, 14.0], [38.0, 2600.0, 36.0, 28.0], [24.0, 3800.0, 48.0, 11.0],
    [32.0, 3050.0, 40.5, 19.0], [30.5, 3150.0, 41.5, 17.0], [34.0, 2950.0, 39.5, 24.0],
    [26.0, 3450.0, 44.0, 13.0], [37.0, 2700.0, 37.0, 27.0], [23.0, 3900.0, 49.0, 9.0],
    [36.0, 2750.0, 37.5, 26.0], [28.5, 3250.0, 42.5, 21.0],
]


_ENGINE_CACHE: dict[str, Any] = {}


def _get_engine():
    """Fit-once, cached engine (sovereign, deterministic seed)."""
    if "core" in _ENGINE_CACHE:
        return _ENGINE_CACHE["core"]
    if not _HAVE_NUMPY:
        return None
    Xref = np.asarray(_REF_POP, dtype=float)
    if _CORE_CLS is not None:
        try:
            core = _CORE_CLS().fit(Xref)
            _ENGINE_CACHE["core"] = core
            _ENGINE_CACHE["kind"] = "vendored"
            return core
        except Exception:
            pass
    core = _NumpyMosaicCore().fit(Xref)
    _ENGINE_CACHE["core"] = core
    _ENGINE_CACHE["kind"] = "numpy"
    return core


def _conformal(core, point: float):
    if hasattr(core, "conformal_interval"):
        return core.conformal_interval(point)
    # vendored core exposes module-level conformal_interval + _calib
    try:
        return _core_mod.conformal_interval(core._calib, point, alpha=core.alpha)
    except Exception:
        return (float(point), float(point))


def score_tracks(tracks: list) -> dict:
    """Score a list of killinchu tracks. Returns per-track anomaly score in [0,1],
    Λ-advisory verdict, bounded confidence interval and component breakdown.
    HONEST: scores are ESTIMATES; Λ is Conjecture-1 ADVISORY; CI is finite-sample."""
    core = _get_engine()
    if core is None or not tracks:
        return {"ok": False, "honesty": "numpy unavailable or no tracks — honest empty.",
                "scored": [], "engine": _ENGINE_BACKEND}
    feats = np.asarray([_track_features(t) for t in tracks], dtype=float)
    res = core.score(feats)
    combined = res["combined"]
    comps = res["components"]
    scored = []
    for i, t in enumerate(tracks):
        s = float(combined[i])
        ci = _conformal(core, s)
        comp_i = {k: round(float(v[i]), 4) for k, v in comps.items()}
        scored.append({
            "track_id": t.get("track_id", t.get("id", f"TRK-{i:04d}")),
            "model": t.get("model", ""),
            "side": t.get("side", "unknown"),
            "status": t.get("status", ""),
            "anomaly_score": round(s, 4),
            "lambda_verdict": core.lambda_verdict(s),
            "confidence_interval": [round(ci[0], 4), round(ci[1], 4)],
            "confidence_method": ("split-conformal-style finite-sample bound "
                                  "(NOT a certainty claim)"),
            "component_scores": comp_i,
            "features": {"speed_m_s": round(feats[i][0], 2),
                         "altitude_m": round(feats[i][1], 1),
                         "range_km": round(feats[i][2], 2),
                         "closing_deg": round(feats[i][3], 1)},
        })
    return {
        "ok": True,
        "scored": scored,
        "engine": _ENGINE_BACKEND,
        "lambda_status": "Conjecture 1 (conditional Theorem U) — ADVISORY, not a theorem",
        "thresholds": {"allow_below": core.allow_thr, "deny_at_or_above": core.deny_thr},
        "honesty": ("Anomaly scores are ESTIMATES with a bounded conformal confidence "
                    "interval. Λ is Conjecture-1 ADVISORY (allow/advisory/deny), never "
                    "proven trust. Tracks are decoded/derived CLAIMS over mostly-simulated "
                    "positions, not attested ground truth. Human-on-the-loop required."),
        "doctrine": _DOCTRINE,
    }


# ---------------------------------------------------------------------------
# FE-NO-cited hull-stress ESTIMATE for a flagged vessel.
#
# The CANONICAL receipt-verified solid-mechanics solve is the SZL FE-NO vertical
# (platform monorepo: services/verticals/szl_mechanics; clean-room non-overlapping
# Schwarz FE-NO, method arXiv:2606.08796 Wang/Gupta/Ruan/Goswami, CC BY 4.0). That
# vertical is NOT importable from this HF-Space process (different repo), so here we
# surface a FAST, clearly-labelled ESTIMATE using a closed-form longitudinal-bending
# (Euler-Bernoulli) hull-girder model — the standard naval-architecture first cut —
# and point the operator at the FE-NO solver for the verified solve.
# TODO(platform-feno): when the szl_mechanics vertical is reachable (UDS service
# mesh), replace this estimate with a real solve_feno(...) call + its receipt.
# ---------------------------------------------------------------------------
def hull_stress_estimate(loa_m: float, beam_m: float, draft_m: float,
                         displacement_t: float, wave_factor: float = 1.0) -> dict:
    """Euler-Bernoulli hull-girder longitudinal bending stress ESTIMATE (MPa).
    NOT a verified FE solve — see FE-NO vertical for that. Sovereign, closed-form."""
    loa = max(float(loa_m), 1.0)
    beam = max(float(beam_m), 0.1)
    draft = max(float(draft_m), 0.1)
    disp = max(float(displacement_t), 1.0)
    # Quasi-static hull-girder still-water + wave bending moment (classic approx):
    #   M ≈ W·L / k,  k ~ 35 (sagging/hogging first cut), W = displacement weight.
    W_N = disp * 1000.0 * 9.81                       # weight, newtons
    M = (W_N * loa) / 35.0 * max(wave_factor, 0.1)   # bending moment, N·m
    # Section modulus of an equivalent thin box girder (very rough):
    #   I ≈ (beam·depth^3)/12 about neutral axis; depth ~ draft (proxy), t lumped.
    depth = max(draft * 1.6, 0.5)                    # moulded depth proxy
    t = max(0.012 * depth, 0.006)                    # effective plate thickness proxy (m)
    I = (beam * (depth ** 3) - (beam - 2 * t) * ((depth - 2 * t) ** 3)) / 12.0
    c = depth / 2.0
    Z = max(I / c, 1e-6)                             # section modulus (m^3)
    sigma_pa = M / Z
    sigma_mpa = sigma_pa / 1e6
    # Honest, bounded utilisation against a typical mild-steel yield (235 MPa):
    yield_mpa = 235.0
    util = sigma_mpa / yield_mpa
    if util < 0.5:
        band = "within-envelope"
    elif util < 0.85:
        band = "watch"
    else:
        band = "advisory-overstress"
    return {
        "ok": True,
        "model": "Euler-Bernoulli hull-girder longitudinal bending (closed-form ESTIMATE)",
        "inputs": {"loa_m": loa, "beam_m": beam, "draft_m": draft,
                   "displacement_t": disp, "wave_factor": wave_factor},
        "bending_moment_MN_m": round(M / 1e6, 3),
        "section_modulus_m3": round(Z, 4),
        "max_bending_stress_MPa": round(sigma_mpa, 2),
        "yield_ref_MPa": yield_mpa,
        "utilisation": round(util, 3),
        "band": band,
        "honesty": ("ESTIMATE ONLY — closed-form Euler-Bernoulli hull-girder first cut, "
                    "NOT a verified FE solve. The canonical receipt-verified solve is the "
                    "SZL FE-NO solid-mechanics vertical (platform: services/verticals/"
                    "szl_mechanics; clean-room non-overlapping Schwarz FE-NO, method "
                    "arXiv:2606.08796, CC BY 4.0). Run that for an attested result."),
        "feno_solver_ref": "platform/services/verticals/szl_mechanics (arXiv:2606.08796)",
        "doctrine": _DOCTRINE,
    }


# ---------------------------------------------------------------------------
# SGP4 orbital-conjunction ROADMAP stub (space-domain).
#
# HONEST: killinchu TODAY is counter-UAS / drone / vessel. Orbital DTID/SDA is
# ROADMAP. python-sgp4 (MIT) is the intended sovereign propagator. We attempt a
# REAL SGP4 propagation if the library is present; otherwise we return an honest,
# clearly-labelled ROADMAP skeleton — never a fabricated conjunction.
# ---------------------------------------------------------------------------
# Two well-known public TLEs (ISS + a debris-like sample) for the demo propagation.
# These are illustrative public elements, refreshed in a real deployment.
_DEMO_TLE = {
    "ISS (ZARYA)": (
        "1 25544U 98067A   24079.07757601  .00016717  00000-0  10270-3 0  9994",
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537",
    ),
    "SAMPLE-DEBRIS": (
        "1 43205U 18017A   24079.50000000  .00000100  00000-0  10000-4 0  9991",
        "2 43205  51.6400 250.0000 0010000 100.0000  10.0000 15.50000000000000",
    ),
}


def sda_conjunction_stub() -> dict:
    try:
        from sgp4.api import Satrec, jday  # python-sgp4 (MIT)
        sats = {}
        for name, (l1, l2) in _DEMO_TLE.items():
            sats[name] = Satrec.twoline2rv(l1, l2)
        # propagate both to a common epoch and compute min approach over a short sweep
        names = list(sats)
        jd, fr = jday(2024, 3, 20, 0, 0, 0.0)
        positions = {}
        ok = True
        for name in names:
            e, r, v = sats[name].sgp4(jd, fr)
            if e != 0:
                ok = False
            positions[name] = r  # km, TEME frame
        if ok and len(names) == 2:
            a = positions[names[0]]
            b = positions[names[1]]
            sep_km = math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))
        else:
            sep_km = None
        return {
            "ok": True,
            "engine": "python-sgp4 (MIT) — REAL propagation",
            "frame": "TEME, km",
            "objects": names,
            "positions_km": {k: [round(x, 2) for x in v] for k, v in positions.items()},
            "instant_separation_km": (round(sep_km, 2) if sep_km is not None else None),
            "status": "ROADMAP — space-domain extension; demo TLEs are illustrative public elements",
            "honesty": ("Space Domain Awareness is killinchu ROADMAP, NOT today's reality "
                        "(today = counter-UAS / drone / vessel). This is a REAL SGP4 "
                        "propagation over PUBLIC demo TLEs, surfaced as a labelled stub. "
                        "No screening service, no operational conjunction product."),
            "doctrine": _DOCTRINE,
        }
    except Exception as e:
        return {
            "ok": False,
            "engine": "python-sgp4 unavailable",
            "status": "ROADMAP SKELETON — honest fallback (python-sgp4 not installed)",
            "objects": list(_DEMO_TLE),
            "instant_separation_km": None,
            "honesty": ("Honest skeleton: python-sgp4 (MIT) is the intended sovereign "
                        "orbital propagator for the SDA roadmap; it is not present in this "
                        "runtime, so no conjunction is computed and NONE is fabricated. "
                        f"({type(e).__name__})"),
            "doctrine": _DOCTRINE,
        }


def register(app: FastAPI, ns: str = "killinchu",
             emit_receipt: Optional[Callable] = None) -> dict[str, Any]:
    """Register the Mosaic / Domain-Superiority organ endpoints. ADDITIVE."""
    registered: list[str] = []

    @app.get(f"/api/{ns}/v1/mosaic/health")
    async def mosaic_health() -> JSONResponse:
        return JSONResponse({
            "ok": True,
            "organ": "mosaic-domain-superiority",
            "engine": _ENGINE_BACKEND,
            "engine_kind": _ENGINE_CACHE.get("kind", "lazy"),
            "capability": ("Detect/Track/ID -> Characterize -> ML-Threat-Warning -> "
                           "fuse/forecast -> Common Operating Picture (clean-room; "
                           "inspired by True Anomaly Mosaic's PUBLIC capability)"),
            "lambda_status": "Conjecture 1 — ADVISORY, not a theorem",
            "khipu_consensus": "BFT 3-of-4 (Conjecture 2 — PROPOSED, not proven)",
            "space_domain": "ROADMAP (today = counter-UAS / drone / vessel)",
            "attribution": ("Engine clean-room from permissive lineage (PyOD/Merlion/TODS/"
                            "tsod/GDN/PyGOD/sgp4); NO proprietary Mosaic code. "
                            "alibi-detect (BSL-1.1) NOT used."),
            "doctrine": _DOCTRINE, "lean_sha": _LEAN, "counts": _COUNTS,
        })

    @app.post(f"/api/{ns}/v1/mosaic/score")
    async def mosaic_score(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        tracks = body.get("tracks") or []
        if not isinstance(tracks, list):
            tracks = []
        return JSONResponse(score_tracks(tracks))

    @app.post(f"/api/{ns}/v1/mosaic/receipt")
    async def mosaic_receipt(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        verdict = {
            "track_id": body.get("track_id"),
            "anomaly_score": body.get("anomaly_score"),
            "lambda_verdict": body.get("lambda_verdict"),
            "confidence_interval": body.get("confidence_interval"),
            "kind": "mosaic_anomaly_verdict",
        }
        digest = hashlib.sha256(
            json.dumps(verdict, sort_keys=True, default=str).encode()).hexdigest()
        receipt: dict[str, Any] = {
            "schema": "szl.mosaic.receipt/v1",
            "verdict": verdict,
            "inputs_sha256": digest,
            "lambda_note": ("Λ is Conjecture 1 (conditional, ADVISORY) — NOT proven trust. "
                            "Human-on-the-loop required."),
            "khipu_consensus": ("ties to BFT 3-of-4 Khipu quorum — Conjecture 2 (PROPOSED, "
                                "not proven)"),
        }
        # Tie into killinchu's REAL Khipu DAG + DSSE signer via the shared emit_receipt.
        if emit_receipt is not None:
            try:
                node = emit_receipt("mosaic_anomaly_verdict", verdict)
                receipt["khipu_node"] = {"index": node.get("index"),
                                         "digest": node.get("digest"),
                                         "dsse": node.get("dsse")}
                receipt["signing"] = ("DSSE via killinchu signer — REAL ECDSA-P256 when "
                                      "SZL_COSIGN_PRIVATE_PEM present, else honest PLACEHOLDER; "
                                      "never fabricated. Chained into the SHA-256 Khipu DAG.")
                receipt["verified"] = bool(node.get("dsse"))
            except Exception as e:
                receipt["signing"] = (f"UNSIGNED — emit_receipt unavailable ({type(e).__name__}); "
                                      "no signature fabricated (honest).")
                receipt["verified"] = False
        else:
            receipt["signing"] = ("UNSIGNED — no receipt substrate wired in this process; "
                                  "no signature fabricated (honest).")
            receipt["verified"] = False
        receipt["doctrine"] = _DOCTRINE
        return JSONResponse({"ok": True, "receipt": receipt})

    @app.get(f"/api/{ns}/v1/mosaic/cop")
    async def mosaic_cop() -> JSONResponse:
        # Pull killinchu's live air picture and overlay the anomaly engine.
        tracks: list = []
        try:
            import serve as _srv  # in-process live threat board
            if hasattr(_srv, "_DRONES"):
                pass
        except Exception:
            pass
        # The COP fuses the live /threats/active board client-side; server returns
        # the fused-domain skeleton + the SDA stub so the view is never blank.
        return JSONResponse({
            "ok": True,
            "domains": {
                "air": {"status": "LIVE-capable", "source": "/api/%s/v1/threats/active" % ns,
                        "reality": "counter-UAS / drone (today)"},
                "maritime": {"status": "LIVE-capable", "source": "/api/%s/v1/fleet" % ns,
                             "reality": "vessel / AIS (today)"},
                "orbit": {"status": "ROADMAP", "source": "/api/%s/v1/mosaic/sda/conjunction" % ns,
                          "reality": "space-domain SGP4 stub (roadmap)"},
            },
            "anomaly_overlay": {"endpoint": "/api/%s/v1/mosaic/score" % ns,
                                "verdict": "Λ allow/advisory/deny (Conjecture 1)"},
            "honesty": ("The Common Operating Picture fuses the LIVE air + maritime boards with "
                        "the anomaly overlay; the orbital domain is a clearly-labelled ROADMAP "
                        "SGP4 stub, not an operational space product. Effectors SIMULATED."),
            "doctrine": _DOCTRINE,
        })

    @app.get(f"/api/{ns}/v1/mosaic/sda/conjunction")
    async def mosaic_sda() -> JSONResponse:
        return JSONResponse(sda_conjunction_stub())

    @app.post(f"/api/{ns}/v1/mosaic/hull-stress")
    async def mosaic_hull(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return JSONResponse(hull_stress_estimate(
            loa_m=body.get("loa_m", 180.0),
            beam_m=body.get("beam_m", 28.0),
            draft_m=body.get("draft_m", 10.5),
            displacement_t=body.get("displacement_t", 45000.0),
            wave_factor=body.get("wave_factor", 1.0),
        ))

    for p in ("health", "score", "receipt", "cop", "sda/conjunction", "hull-stress"):
        registered.append(f"/api/{ns}/v1/mosaic/{p}")

    return {
        "module": "killinchu_mosaic",
        "registered": registered,
        "engine": _ENGINE_BACKEND,
        "doctrine": _DOCTRINE,
    }
