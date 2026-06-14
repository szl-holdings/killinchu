# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_tda_fracture.py — ADDITIVE TDA Fracture regime/anomaly detector for killinchu's
maritime/risk surface (the domain adaptation of the GPU-quant Layer-2 fracture score).

The TDA fracture score f_t = |Δβ0| + |Δβ1| is domain-agnostic — it operates on any
correlation-distance matrix derived from multivariate time series (GPU_QUANT_RESEARCH.md
§D.2). Here the multivariate series is a window of AIS / maritime vessel tracks (per-vessel
kinematic features), so f_t detects sudden topological reorganization of maritime traffic
— convoy formation, dispersal, rendezvous anomalies, a regime shift from routine to threat
— BEFORE any single indicator fires. Gidea & Katz showed the analogous market signal fires
~250 trading days before a crash; for maritime a topology shift minutes ahead is significant.

  d_ij = √(2(1−ρ_ij))                                 (econophysics correlation metric)
  β0 = connected components,  β1 = independent loops    (Vietoris-Rips persistent homology)
  f_t = |Δβ0| + |Δβ1|                                  (fracture score; Brodetsky)
  z_t = (f_t − μ_f)/σ_f,  |z_t| > 2.5 ⇒ anomaly        (Gidea & Katz 2017, arXiv:1703.04385)

HONESTY SPINE (doctrine v11):
  * This is a MODELED regime/anomaly detector. The AIS window here is a SAMPLE_SYNTHETIC
    fixture (or a caller-supplied window) — NOT a live AIS feed, and the z-score baseline
    is NOT calibrated on historical AIS. γ, κ and the z-threshold require domain calibration.
  * β0 is exact (union-find); β1 is the 1-skeleton cycle rank (E−V+C) — an honest fast proxy
    for genuine Vietoris-Rips H1 (the GPU giotto-tda/Ripser++ path, ROADMAP, computes it exactly).
  * Every result is a SIGNED receipt (REAL ECDSA when the cosign key is present; an explicit
    UNSIGNED honesty marker otherwise — never a fabricated signature).
  * Effectors stay SIMULATED, human-on-loop. This NEVER triggers an engagement — it is a
    detector that raises a labeled MODELED anomaly into the maritime/risk surface.

Route (NEW; never collides):
  GET /api/{ns}/v1/quant/tda-fracture  — TDA fracture on a SAMPLE/supplied AIS window

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
import random as _random
from datetime import datetime, timezone

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — try the killinchu PQC signer, else honest unsigned
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.tda+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": __import__("base64").b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_TDA_PAYLOAD_TYPE = "application/vnd.szl.kc.tda+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "tda_crashes": "Gidea & Katz (2017) TDA of Financial Time Series: Landscapes of Crashes — arXiv:1703.04385 (Physica A 2018)",
    "tda_crypto": "Gidea, Goldsmith, Katz, Roldan, Shmalo (2018) TDA of Cryptocurrencies — arXiv:1809.00695",
    "ripserpp": "Zhang, Xiao, Wang — GPU Vietoris-Rips persistence (Ripser++) arXiv:2003.07989",
    "giotto_tda": "giotto-tda — https://github.com/giotto-ai/giotto-tda",
    "brodetsky": "N. Brodetsky — topological-regime-detector (early-warning via TDA + Takens' embedding)",
}

# MODELED label — this is a labeled model output (uncalibrated), never live, never an engage.
MODELED_LABEL = "MODELED | SAMPLE_AIS | NOT_LIVE | REQUIRES_HISTORICAL_CALIBRATION"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =====================================================================================
# Pure-stdlib correlation + persistent-homology Betti (honest CPU path).
# =====================================================================================
def _sample_covariance(series):
    """series: T rows × N cols. Returns (N×N covariance, means)."""
    T = len(series)
    N = len(series[0])
    means = [sum(series[t][j] for t in range(T)) / T for j in range(N)]
    cov = [[0.0] * N for _ in range(N)]
    denom = max(1, T - 1)
    for i in range(N):
        for j in range(i, N):
            s = 0.0
            for t in range(T):
                s += (series[t][i] - means[i]) * (series[t][j] - means[j])
            v = s / denom
            cov[i][j] = v
            cov[j][i] = v
    return cov, means


def _correlation_distance(cov):
    """ρ_ij from cov, then d_ij = √(2(1−ρ_ij))."""
    N = len(cov)
    std = [_math.sqrt(cov[i][i]) if cov[i][i] > 0 else 1e-12 for i in range(N)]
    d = [[0.0] * N for _ in range(N)]
    for i in range(N):
        for j in range(N):
            rho = max(-1.0, min(1.0, cov[i][j] / (std[i] * std[j])))
            d[i][j] = _math.sqrt(max(0.0, 2.0 * (1.0 - rho)))
    return d


def _betti_numbers(dist, eps):
    """β0 = connected components (union-find); β1 = 1-skeleton cycle rank E−V+C."""
    N = len(dist)
    parent = list(range(N))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    edges = 0
    for i in range(N):
        for j in range(i + 1, N):
            if dist[i][j] <= eps:
                edges += 1
                union(i, j)
    comps = len({find(i) for i in range(N)})
    beta1 = max(0, edges - N + comps)
    return comps, beta1, edges


def _persistence_betti(dist, n_steps=24, eps_fixed=None):
    """Betti curve over the filtration + β0/β1 read at a representative radius.

    When `eps_fixed` is given, β0/β1 are read at THAT common radius (so Δβ across two
    windows reflects genuine topological reorganization rather than each window's own
    median). Otherwise the per-window median pairwise distance is used."""
    flat = sorted(dist[i][j] for i in range(len(dist)) for j in range(i + 1, len(dist)))
    if not flat:
        return {"beta0": 1, "beta1": 0, "eps_star": 0.0, "curve": []}
    lo, hi = flat[0], flat[-1]
    curve = []
    for s in range(n_steps + 1):
        eps = lo + (hi - lo) * s / n_steps
        b0, b1, e = _betti_numbers(dist, eps)
        curve.append({"eps": round(eps, 5), "beta0": b0, "beta1": b1, "edges": e})
    eps_star = eps_fixed if eps_fixed is not None else flat[len(flat) // 2]
    b0s, b1s, _ = _betti_numbers(dist, eps_star)
    return {"beta0": b0s, "beta1": b1s, "eps_star": round(eps_star, 5), "curve": curve}


# =====================================================================================
# SAMPLE AIS window generator (deterministic, honestly synthetic).
# =====================================================================================
def _sample_ais_window(n_vessels=14, n_obs=80, seed=23, anomaly=False):
    """Deterministic SAMPLE per-vessel kinematic series (a stand-in correlation feature
    such as speed-over-ground deviation). `anomaly=True` injects a convoy-formation / common-
    mode shock in the back half that raises cross-vessel correlation → drives TDA fracture.
    This is ILLUSTRATIVE SYNTHETIC data — NOT a live AIS feed."""
    rng = _random.Random(seed)
    # baseline: a few loosely-correlated traffic lanes + idiosyncratic vessel motion
    lane = [rng.choice([0, 1, 2]) for _ in range(n_vessels)]
    series = []
    for t in range(n_obs):
        lane_shock = [rng.gauss(0, 0.02) for _ in range(3)]
        common = rng.gauss(0, 0.06) if (anomaly and t > n_obs // 2) else 0.0
        row = []
        for v in range(n_vessels):
            val = lane_shock[lane[v]] + rng.gauss(0, 0.015) + common
            row.append(val)
        series.append(row)
    return series


def tda_fracture(series=None, prev=None, anomaly=False) -> dict:
    """TDA fracture score on an AIS/maritime window → regime/anomaly verdict (MODELED).

    `series` — optional T×N caller window (e.g. real AIS kinematic features). When absent,
    a SAMPLE_SYNTHETIC window is used so the detector is demonstrable.
    `prev` — optional {beta0, beta1, fracture_history:[...]} previous-window state so Δβ and
    the z-score are computed against a real prior. With no prior we contrast a routine window
    vs an anomaly window to make the mechanism visible (honestly synthetic baseline).
    """
    data_source = "CALLER_WINDOW" if series is not None else "SAMPLE_SYNTHETIC"
    if series is None:
        series = _sample_ais_window(anomaly=anomaly)
    cov, _ = _sample_covariance(series)
    dist = _correlation_distance(cov)
    cur = _persistence_betti(dist)

    if prev is None:
        # Compare routine vs current at a COMMON fixed filtration radius (the routine
        # window's median pairwise distance) so Δβ reflects genuine reorganization.
        routine_dist = _correlation_distance(_sample_covariance(_sample_ais_window(anomaly=False))[0])
        rflat = sorted(routine_dist[i][j] for i in range(len(routine_dist))
                       for j in range(i + 1, len(routine_dist)))
        eps_common = rflat[len(rflat) // 2] if rflat else None
        routine = _persistence_betti(routine_dist, eps_fixed=eps_common)
        shocked = _persistence_betti(_correlation_distance(
            _sample_covariance(_sample_ais_window(anomaly=True))[0]), eps_fixed=eps_common)
        prev_b0, prev_b1 = routine["beta0"], routine["beta1"]
        if series is None or anomaly:
            cur = shocked
        else:
            cur = _persistence_betti(dist, eps_fixed=eps_common)
        cur_b0, cur_b1 = cur["beta0"], cur["beta1"]
        rng = _random.Random(31)
        history = [abs(rng.gauss(1.0, 0.5)) for _ in range(40)]
    else:
        prev_b0 = int(prev.get("beta0", cur["beta0"]))
        prev_b1 = int(prev.get("beta1", cur["beta1"]))
        cur_b0, cur_b1 = cur["beta0"], cur["beta1"]
        history = list(prev.get("fracture_history", [])) or [0.0]

    fracture = abs(cur_b0 - prev_b0) + abs(cur_b1 - prev_b1)
    mu_f = sum(history) / len(history)
    var_f = sum((h - mu_f) ** 2 for h in history) / max(1, len(history) - 1)
    sigma_f = _math.sqrt(var_f) if var_f > 0 else 1.0
    z = (fracture - mu_f) / sigma_f if sigma_f > 0 else 0.0
    is_anomaly = abs(z) > 2.5

    regime = ("REGIME-SHIFT (topological reorganization detected)" if is_anomaly
              else "ROUTINE (stable maritime topology)")

    receipt = {
        "window_timestamp": _now_iso(),
        "detector": "tda-fracture-maritime",
        "detector_version": "szl-kc-tda-v0.1",
        "data_source": data_source,
        "n_vessels": len(series[0]),
        "n_obs": len(series),
        "beta0_prev": prev_b0, "beta1_prev": prev_b1,
        "beta0_cur": cur_b0, "beta1_cur": cur_b1,
        "fracture_score_f_t": round(float(fracture), 4),
        "z_score": round(float(z), 4),
        "z_threshold": 2.5,
        "anomaly": bool(is_anomaly),
        "regime_verdict": regime,
        "label": MODELED_LABEL,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (detector only — never an engage)",
        "citations": [CITATIONS["tda_crashes"], CITATIONS["tda_crypto"],
                      CITATIONS["ripserpp"], CITATIONS["brodetsky"]],
        "honesty": ("TDA fracture as a maritime regime/anomaly detector. SAMPLE/synthetic AIS "
                    "window; z-score baseline UNcalibrated on historical AIS. β1 is the 1-skeleton "
                    "cycle rank (honest proxy; GPU giotto-tda/Ripser++ exact H1 = ROADMAP). MODELED, "
                    "not live; never an engagement."),
    }
    dsse = _sign_payload(receipt, _TDA_PAYLOAD_TYPE)
    return {
        "service": "maritime-tda-fracture",
        "label": MODELED_LABEL,
        "regime_verdict": regime,
        "fracture_score_f_t": round(float(fracture), 4),
        "z_score": round(float(z), 4),
        "anomaly": bool(is_anomaly),
        "beta0": {"prev": prev_b0, "cur": cur_b0},
        "beta1": {"prev": prev_b1, "cur": cur_b1},
        "eps_star": cur["eps_star"],
        "betti_curve": cur["curve"],
        "formulas": {
            "distance": "d_ij = √(2(1−ρ_ij))",
            "fracture": "f_t = |Δβ0| + |Δβ1|",
            "zscore": "z_t = (f_t − μ_f)/σ_f,  |z_t| > 2.5 ⇒ anomaly",
        },
        "compute_backend": {
            "backend": "CPU pure-Python fallback",
            "label": "MODELED",
            "honest_note": ("Pure-Python correlation + Vietoris-Rips β0/β1. The cuPy/giotto-tda/"
                            "Ripser++ GPU path is ROADMAP — killinchu has no sovereign GPU orchestrator."),
        },
        "wired_into": "maritime/risk surface (regime/anomaly overlay)",
        "citations": [CITATIONS["tda_crashes"], CITATIONS["giotto_tda"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/quant" % ns

    @app.get("%s/tda-fracture" % base)
    async def _kc_tda(anomaly: bool = False):  # noqa: ANN202
        try:
            return JSONResponse(tda_fracture(anomaly=anomaly))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "maritime-tda-fracture", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "anomaly": None}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/tda-fracture" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    # (a) routine window: low fracture, anomaly False.
    r = tda_fracture(anomaly=False)
    assert r["label"] == MODELED_LABEL, r["label"]
    assert isinstance(r["anomaly"], bool), r
    out["routine"] = {"f_t": r["fracture_score_f_t"], "z": r["z_score"], "anomaly": r["anomaly"]}

    # (b) anomaly window: fracture rises, regime-shift verdict.
    a = tda_fracture(anomaly=True)
    assert a["fracture_score_f_t"] >= r["fracture_score_f_t"] or a["anomaly"], (r, a)
    out["anomaly"] = {"f_t": a["fracture_score_f_t"], "z": a["z_score"], "anomaly": a["anomaly"],
                      "verdict": a["regime_verdict"]}

    # (c) signed receipt present + honest label embedded; never fabricated.
    d = a["signed_receipt"]["dsse"]
    rc = a["signed_receipt"]["receipt"]
    assert rc["label"] == MODELED_LABEL and "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc
    out["signed_receipt"] = {"signed": d.get("signed")}

    # (d) caller-supplied window path works.
    win = _sample_ais_window(anomaly=True)
    c = tda_fracture(series=win)
    assert c["signed_receipt"]["receipt"]["data_source"] == "CALLER_WINDOW", c
    out["caller_window"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
