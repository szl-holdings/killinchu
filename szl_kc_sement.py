# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_sement.py — ADDITIVE Semantic-Entropy / Effective-Rank epistemic-uncertainty
estimator for killinchu's frontier ring (backs static/3d/surfaces/sement.js in the a11oy repo).

WHAT THIS IS
  A deterministic, seeded SIMULATION of the semantic-entropy hallucination-detection METHOD
  (Farquhar, Kossen, Kuhn & Gal, Nature 2024) plus the 2025 spectral effective-rank signal
  (Wang, Wei, Yue & Sun, arXiv:2510.08389). For one fixed prompt it synthesizes K candidate
  "answers" per regime (seeded), groups answers that MEAN THE SAME THING into semantic-
  equivalence clusters, and scores:

    naive_entropy     = Shannon entropy over SURFACE strings (nats)   — can be misleadingly low
    semantic_entropy  = Shannon entropy over MEANING clusters (nats)  — the honest signal
    effective_rank    = exp(entropy of normalized singular values) of synthetic hidden states
    decision          = "answer" if semantic_entropy < threshold else "abstain"

  It contrasts a CONFIDENT regime (answers collapse to one meaning; low semantic entropy →
  ANSWER) against a CONFABULATING regime (answers scatter across contradictory meanings; high
  semantic entropy + high effective rank → ABSTAIN), demonstrating the ORDERING the published
  methods exploit: semantic entropy AND effective rank both RISE on confabulation even when
  naive surface entropy stays low.

FRAMING — ADVISORY INPUT TO Λ (CONJECTURE 1), NOT A PROOF
  The abstain/answer gate here is an ADVISORY epistemic-uncertainty input to Λ (Conjecture 1),
  never a theorem, never "green". High semantic entropy raises Λ-risk toward its <1.0 ceiling;
  it never certifies a generation as safe. Trust never 100%.

WHAT THIS IS NOT (honesty spine, doctrine v11)
  * MODELED / EXPERIMENTAL — a SIMULATION of the METHOD on SYNTHETIC toy data. It is NOT live
    model sampling and NOT a real LLM. The semantic-equivalence clustering is a HAND-SPECIFIED
    deterministic assignment (real semantic entropy uses a trained bidirectional-entailment
    model); the "hidden states" behind the effective rank are SYNTHETIC seeded matrices.
  * It faithfully demonstrates the ORDERING (uncertain > confident) but does NOT reproduce the
    Nature paper's AUROC or the effective-rank paper's benchmark numbers, and makes NO claim
    about real-model calibration. Read the honesty label VERBATIM; sement.js never upgrades it.
  * Adds NOTHING to the locked-8. Emits an honest UNSIGNED receipt marker locally (REAL DSSE
    only in-Space when the cosign key is present; a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/sement/estimate?seed=<int>&K=<int>&n_clusters=<int>&threshold=<float>

Sources (cited in code + response; adopted, NOT reclaimed as an SZL theorem):
  - Farquhar, Kossen, Kuhn & Gal (2024) "Detecting hallucinations in large language models
    using semantic entropy". Nature 630, 625-630. DOI 10.1038/s41586-024-07421-0 —
    https://www.nature.com/articles/s41586-024-07421-0
  - Wang, Wei, Yue & Sun (2025) "Revisiting Hallucination Detection with Effective Rank-based
    Uncertainty". arXiv:2510.08389 — https://arxiv.org/abs/2510.08389

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import json as _json
import math as _math
import random as _random
from datetime import datetime, timezone
from typing import Any, Dict, List

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker otherwise
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.sement+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": _base64.b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_SEMENT_PAYLOAD_TYPE = "application/vnd.szl.kc.sement+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "semantic_entropy": ("Farquhar, Kossen, Kuhn & Gal (2024) \"Detecting hallucinations in "
                         "large language models using semantic entropy\", Nature 630, 625-630, "
                         "DOI 10.1038/s41586-024-07421-0 — "
                         "https://www.nature.com/articles/s41586-024-07421-0"),
    "effective_rank": ("Wang, Wei, Yue & Sun (2025) \"Revisiting Hallucination Detection with "
                       "Effective Rank-based Uncertainty\", arXiv:2510.08389 — "
                       "https://arxiv.org/abs/2510.08389"),
}

# Honesty label — read VERBATIM by sement.js and displayed as-is; never upgraded.
# EXPERIMENTAL tier: a synthetic-demo simulation of the method, NOT live model sampling.
MODELED_LABEL = "MODELED"

HONEST_NOTE = (
    "MODELED / EXPERIMENTAL — a deterministic SIMULATION of the semantic-entropy method "
    "(Farquhar et al., Nature 2024) plus the 2025 spectral effective-rank signal (Wang et al., "
    "arXiv:2510.08389) on SYNTHETIC toy data. This is NOT live model sampling and NOT a real "
    "LLM: the semantic-equivalence clustering is a HAND-SPECIFIED deterministic assignment "
    "(real semantic entropy uses a trained bidirectional-entailment model) and the hidden "
    "states are SYNTHETIC seeded matrices. It faithfully demonstrates the ORDERING (uncertain "
    "> confident) the published methods exploit but does NOT reproduce their AUROC or benchmark "
    "numbers and makes no claim about real-model calibration. The abstain/answer gate is an "
    "ADVISORY epistemic-uncertainty input to Λ (Conjecture 1), NOT a proof and never 'green'. "
    "Adds nothing to the locked-8; trust never 100%."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _shannon_entropy_nats(probs: List[float]) -> float:
    """Shannon entropy in nats over a probability vector (ignores zero-mass entries)."""
    h = 0.0
    for p in probs:
        if p > 0.0:
            h -= p * _math.log(p)
    return h


def _counts_to_probs(counts: List[int]) -> List[float]:
    total = sum(counts)
    if total <= 0:
        return [0.0 for _ in counts]
    return [c / total for c in counts]


def _effective_rank(singular_values: List[float]) -> float:
    """Effective rank = exp(H(p)) where p = normalized singular values and H is Shannon
    entropy in nats (Roy & Vetterli 2007; the spectral uncertainty signal in Wang et al.
    2025). Higher spread of energy across singular values -> higher effective rank."""
    s = [abs(float(v)) for v in singular_values]
    tot = sum(s)
    if tot <= 0:
        return 1.0
    p = [v / tot for v in s]
    return _math.exp(_shannon_entropy_nats(p))


def _synthetic_singular_values(rng: _random.Random, dim: int, concentrated: bool) -> List[float]:
    """SYNTHETIC seeded singular-value spectrum for a stand-in hidden-state matrix.
    `concentrated=True` (confident regime) puts most energy in the top component -> low
    effective rank; `concentrated=False` (confabulating) spreads energy -> high eff-rank."""
    if concentrated:
        # steep decay: one dominant direction
        base = [(0.82 ** i) * (1.0 + 0.05 * rng.random()) for i in range(dim)]
    else:
        # near-flat spectrum: energy spread across many directions
        base = [(0.97 ** i) * (1.0 + 0.35 * rng.random()) for i in range(dim)]
    return sorted((abs(b) for b in base), reverse=True)


def _regime_estimate(seed: int, K: int, n_clusters: int, threshold: float,
                     regime: str) -> Dict[str, Any]:
    """Deterministic per-regime semantic-entropy estimate on synthetic toy answers.

    CONFIDENT: the K synthetic answers collapse to (almost) ONE meaning-cluster -> low
    semantic entropy -> ANSWER. CONFABULATING: the K answers scatter across all n_clusters
    contradictory meanings -> high semantic entropy + high effective rank -> ABSTAIN.
    naive_entropy is computed over SURFACE strings and is deliberately kept modest on the
    confabulating regime to reproduce the published 'surface entropy misleads' effect."""
    confab = (regime == "confabulating")
    # distinct seed stream per regime so the two regimes are independent + reproducible
    rng = _random.Random((int(seed) * 1000003) ^ (0xC04FAB if confab else 0xC047FD))

    K = max(2, int(K))
    nc = max(1, min(int(n_clusters), 12))

    # --- semantic (meaning) clustering: HAND-SPECIFIED deterministic assignment ---------
    # Confident: a strong dominant meaning-cluster absorbs ~all K samples (one or two
    # stragglers). Confabulating: samples are spread across all nc meaning-clusters.
    sem_counts = [0] * nc
    if not confab:
        for k in range(K):
            # ~90% land in cluster 0 (the agreed meaning); the rest scatter a little
            c = 0 if rng.random() < 0.90 else rng.randrange(nc)
            sem_counts[c] += 1
    else:
        for k in range(K):
            # roughly uniform scatter across all contradictory meanings
            sem_counts[rng.randrange(nc)] += 1
    # guarantee at least one occupied cluster
    if sum(sem_counts) == 0:
        sem_counts[0] = K
    sem_probs = _counts_to_probs(sem_counts)
    semantic_entropy = _shannon_entropy_nats(sem_probs)
    clusters_recovered = sum(1 for c in sem_counts if c > 0)

    # --- naive (surface-string) entropy: many distinct surface forms even when meaning
    #     is one. Confident: moderate surface variety but one meaning. Confabulating: we
    #     keep surface entropy DELIBERATELY MODEST (fewer distinct surface buckets than
    #     meaning clusters) to reproduce the 'surface entropy misleads' phenomenon.
    if not confab:
        surface_buckets = min(K, max(2, nc))
        surf_counts = [0] * surface_buckets
        for k in range(K):
            surf_counts[rng.randrange(surface_buckets)] += 1
    else:
        # confabulating: surface collapses into a few confident-sounding phrasings
        surface_buckets = max(2, nc // 2)
        surf_counts = [0] * surface_buckets
        for k in range(K):
            # skew toward a couple of dominant phrasings -> misleadingly LOW naive entropy
            b = 0 if rng.random() < 0.55 else rng.randrange(surface_buckets)
            surf_counts[b] += 1
    naive_entropy = _shannon_entropy_nats(_counts_to_probs(surf_counts))

    # --- spectral effective rank of SYNTHETIC hidden states -----------------------------
    sv = _synthetic_singular_values(rng, dim=max(4, nc + 3), concentrated=(not confab))
    effective_rank = _effective_rank(sv)

    # --- gate/verdict vs threshold (advisory input to Λ) --------------------------------
    thr = float(threshold)
    decision = "abstain" if semantic_entropy >= thr else "answer"

    return {
        # --- fields sement.js reads per regime (regimes[] entry) ---------------------
        "regime": regime,                              # "confident" | "confabulating"
        "naive_entropy": round(float(naive_entropy), 6),
        "semantic_entropy": round(float(semantic_entropy), 6),
        "effective_rank": round(float(effective_rank), 6),
        "decision": decision,                          # "answer" | "abstain"
        "n_clusters": int(clusters_recovered),         # meaning-clusters recovered
        # --- brief-requested detail: cluster probabilities + gate/verdict -------------
        "clusters": sem_counts,                        # per-meaning-cluster sample counts
        "probs": [round(p, 6) for p in sem_probs],     # cluster probability vector
        "gate": {"threshold": round(thr, 6), "verdict": decision,
                 "semantic_entropy": round(float(semantic_entropy), 6),
                 "framing": "advisory input to Λ (Conjecture 1), NOT a proof; never 'green'"},
    }


def sement_estimate(seed: int = 42, K: int = 40, n_clusters: int = 5,
                    threshold: float = 0.6) -> Dict[str, Any]:
    """Deterministic semantic-entropy uncertainty estimate over a CONFIDENT and a
    CONFABULATING regime. Returns EXACTLY the JSON shape sement.js reads (label, K,
    threshold, ordering_holds, regimes[]) plus the brief-requested top-level fields
    (clusters, probs, semantic_entropy, gate/verdict, honest_note). [MODELED / EXPERIMENTAL]"""
    s = int(seed)
    K = max(2, int(K))
    nc = max(1, min(int(n_clusters), 12))
    thr = float(threshold)

    confident = _regime_estimate(s, K, nc, thr, "confident")
    confabulating = _regime_estimate(s, K, nc, thr, "confabulating")

    # ORDERING the published methods exploit: semantic entropy AND effective rank both rise
    # on the confabulating regime relative to the confident one.
    ordering_holds = bool(
        confabulating["semantic_entropy"] > confident["semantic_entropy"]
        and confabulating["effective_rank"] > confident["effective_rank"]
    )

    # top-level advisory Λ input: the confabulating regime's semantic entropy is the
    # conservative epistemic-uncertainty signal that raises Λ-risk toward the <1.0 ceiling.
    top_gate_verdict = confabulating["decision"]

    payload = {
        # --- EXACTLY the fields sement.js reads (top-level) --------------------------
        "label": MODELED_LABEL,                        # read VERBATIM; never upgraded
        "seed": s,
        "K": K,                                        # candidate generations per regime
        "n_clusters": nc,                              # requested meaning-cluster count
        "threshold": round(thr, 6),                    # abstain/answer threshold (nats)
        "ordering_holds": ordering_holds,              # semantic H & eff-rank both rise
        "regimes": [confident, confabulating],         # [{regime, naive_entropy, ...}, ...]
        "honest_note": HONEST_NOTE,                    # honest, read-as-is
        # --- brief-requested top-level fields (advisory Λ input) ----------------------
        # surface the confabulating regime's cluster structure at the root as the headline
        # uncertainty case that feeds Λ; per-regime detail lives inside regimes[].
        "clusters": confabulating["clusters"],
        "probs": confabulating["probs"],
        "semantic_entropy": confabulating["semantic_entropy"],
        "gate": {"threshold": round(thr, 6), "verdict": top_gate_verdict,
                 "semantic_entropy": confabulating["semantic_entropy"],
                 "framing": "advisory input to Λ (Conjecture 1), NOT a proof; never 'green'"},
        "verdict": top_gate_verdict,
        # --- provenance / doctrine ----------------------------------------------------
        "lambda_advisory": {
            "framing": ("semantic entropy is an ADVISORY epistemic-uncertainty input to Λ "
                        "(Conjecture 1); high semantic entropy raises Λ-risk toward its <1.0 "
                        "ceiling — it NEVER certifies a generation as safe, never 'green'"),
            "trust": "never 100%",
        },
        "doctrine": {
            "version": DOCTRINE_VERSION,
            "locked_proven": 8,
            "lambda": "Conjecture 1 (advisory, never 'green'; NOT a theorem)",
            "adds_to_locked_8": False,
        },
        "citations": [CITATIONS["semantic_entropy"], CITATIONS["effective_rank"]],
        "service": "sement-estimate",
        "computed_at": _now_iso(),
    }
    return payload


def _service_response(seed: int = 42, K: int = 40, n_clusters: int = 5,
                      threshold: float = 0.6) -> Dict[str, Any]:
    """Wrap sement_estimate() with an honest (UNSIGNED-locally) DSSE receipt marker.
    Every field sement.js reads stays at the response root (the surface also accepts a
    nested payload.* mirror), so the frontend renders directly off the root."""
    payload = sement_estimate(seed=seed, K=K, n_clusters=n_clusters, threshold=threshold)
    dsse = _sign_payload(payload, _SEMENT_PAYLOAD_TYPE)
    out = dict(payload)
    out["signed_receipt"] = {"dsse": dsse}
    return out


def info(ns: str) -> Dict[str, Any]:
    return {
        "capability": "Semantic-Entropy · Effective-Rank Epistemic Uncertainty (MODELED)",
        "ns": ns,
        "endpoint": "/api/%s/v1/sement/estimate" % ns,
        "params": {"seed": "int (default 42)", "K": "int candidate generations (default 40)",
                   "n_clusters": "int meaning-clusters (default 5)",
                   "threshold": "float abstain threshold in nats (default 0.6)"},
        "label": MODELED_LABEL,
        "honest_note": HONEST_NOTE,
        "citations": [CITATIONS["semantic_entropy"], CITATIONS["effective_rank"]],
        "doctrine": {"locked_proven": 8, "lambda": "Conjecture 1 (advisory)", "trust": "never 100%",
                     "data_label": "MODELED / EXPERIMENTAL — synthetic demo, NOT live model sampling"},
        "status": "MODELED",
    }


# =====================================================================================
# Registration (additive; routes win over the SPA catch-all when registered earlier).
# =====================================================================================
def register(app, ns: str = "killinchu") -> Dict[str, Any]:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/sement" % ns

    @app.get("%s/estimate" % base)
    async def _kc_sement(seed: int = 42, K: int = 40, n_clusters: int = 5,
                         threshold: float = 0.6):  # noqa: ANN202
        try:
            return JSONResponse(_service_response(seed=seed, K=K, n_clusters=n_clusters,
                                                  threshold=threshold))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "sement-estimate", "label": MODELED_LABEL,
                                 "honest_note": HONEST_NOTE,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "ordering_holds": None}, status_code=200)

    @app.get("%s/info" % base)
    async def _kc_sement_info():  # noqa: ANN202
        try:
            return JSONResponse(info(ns))
        except Exception as exc:  # pragma: no cover
            return JSONResponse({"service": "sement-info", "label": MODELED_LABEL,
                                 "error": type(exc).__name__}, status_code=200)

    return {"ok": True, "ns": ns,
            "routes": ["%s/estimate" % base, "%s/info" % base],
            "data_label": MODELED_LABEL}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    r = sement_estimate(seed=42, K=40, n_clusters=5, threshold=0.6)

    # (a) exact top-level frontend shape.
    for f in ("label", "K", "threshold", "ordering_holds", "regimes",
              "semantic_entropy", "clusters", "probs", "gate", "honest_note"):
        assert f in r, ("missing frontend field: %s" % f)
    assert r["label"] == "MODELED", r["label"]
    assert isinstance(r["regimes"], list) and len(r["regimes"]) == 2, r

    # (b) per-regime shape exactly as sement.js reads.
    regs = {rr["regime"]: rr for rr in r["regimes"]}
    assert set(regs.keys()) == {"confident", "confabulating"}, regs.keys()
    for rr in r["regimes"]:
        for f in ("regime", "naive_entropy", "semantic_entropy", "effective_rank",
                  "decision", "n_clusters"):
            assert f in rr, ("regime missing field: %s" % f)
        assert rr["decision"] in ("answer", "abstain"), rr["decision"]

    conf, confab = regs["confident"], regs["confabulating"]

    # (c) the honest ORDERING: semantic entropy & effective rank BOTH rise on confabulating.
    assert confab["semantic_entropy"] > conf["semantic_entropy"], (conf, confab)
    assert confab["effective_rank"] > conf["effective_rank"], (conf, confab)
    assert r["ordering_holds"] is True, r["ordering_holds"]
    out["ordering"] = {"conf_sem": conf["semantic_entropy"], "confab_sem": confab["semantic_entropy"],
                       "conf_effr": conf["effective_rank"], "confab_effr": confab["effective_rank"]}

    # (d) gate/verdict: confident -> answer, confabulating -> abstain at default threshold.
    assert conf["decision"] == "answer", conf
    assert confab["decision"] == "abstain", confab
    out["verdicts"] = {"confident": conf["decision"], "confabulating": confab["decision"]}

    # (e) surface-entropy-misleads: naive entropy on confabulating is NOT the dominant signal.
    assert confab["semantic_entropy"] > confab["naive_entropy"], confab
    out["surface_misleads"] = {"confab_naive": confab["naive_entropy"],
                               "confab_semantic": confab["semantic_entropy"]}

    # (f) determinism.
    r2 = sement_estimate(seed=42, K=40, n_clusters=5, threshold=0.6)
    assert r2["regimes"] == r["regimes"], "not deterministic"
    out["deterministic"] = True

    # (g) honest UNSIGNED (or REAL signed) receipt marker present; never fabricated.
    sr = _service_response(seed=42, K=40, n_clusters=5, threshold=0.6)
    dsse = sr["signed_receipt"]["dsse"]
    assert dsse.get("_pae_sha256"), dsse
    assert dsse.get("signed") is True or "UNSIGNED" in (dsse.get("honesty") or ""), dsse
    out["signed_receipt"] = {"signed": dsse.get("signed")}

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
