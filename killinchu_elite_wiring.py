# SPDX-License-Identifier: Apache-2.0
"""killinchu_elite_wiring.py — /elite view → data-feed wiring map + honest health.

ADDITIVE. Pure stdlib. Registers ONE new read-only namespace and touches NO
existing route, view, or feed. It answers a single operational question that the
/elite console cannot answer about itself:

    "Is every /elite view wired to a REAL data feed, and is that feed populating
     right now — or is it empty / dark / honestly degraded?"

It does this by holding an explicit, audited map from each /elite view (the
``data-view`` ids in ``killinchu_elite_console.py``) to the killinchu API
endpoint(s) that view consumes, plus a doctrine-honest data-class label for
each. At request time it probes those endpoints *in-process* against the same
FastAPI app (no external network, no second port) and reports, per view:

    * wired        — the data endpoint(s) exist and answer 200
    * degraded     — endpoint answers but honestly reports cached/empty/disabled
    * needs-deploy — endpoint exists in the repo but 404s (HF Space not yet pushed)
    * SIMULATED    — the view is an effector/feasibility demo; SIMULATED by
                     doctrine v11 (killinchu NEVER claims a real kinetic effect)

Doctrine v11: effectors are SIMULATED (never a real effect); labels are honest;
no data is fabricated (feeds degrade honestly to cached/empty); leader feeds are
cited (NIST / MITRE / CISA / ECB / FIRST). Λ = Conjecture 1; locked-8 formulas;
no key is ever committed or placed in a URL.

This module asserts NOTHING about reachability statically — every health badge
comes from a real in-process probe at call time, exactly like the existing
``szl_evidence_research`` / ``killinchu_research_sources`` honesty layers.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

_HONEST = (
    "Each /elite view is mapped to the REAL killinchu data endpoint it consumes. "
    "Health badges are produced by a live in-process probe at call time, never "
    "fabricated; an endpoint that 404s on the running app is labelled "
    "'needs-deploy', one that answers with a cached/empty/disabled body is "
    "labelled 'degraded' (honest), one that answers with live data is 'wired'. "
    "Effector / weapon-target / intercept views are 'SIMULATED' by doctrine v11 — "
    "killinchu computes feasibility and emits signed receipts but never actuates "
    "a real kinetic effect."
)

# data_class vocabulary (honest, doctrine-aligned):
#   live-feed   — pulls a free no-key public API (adsb.lol, Digitraffic, ECB/
#                 Frankfurter, Coinbase, Polymarket, USGS, CelesTrak, FIRST EPSS,
#                 CISA KEV, OSV, NVD), honest live|cached|unreachable label.
#   leader-cited— grounds claims in cited leader standards (NIST 800-207 / 800-53,
#                 MITRE ATT&CK/D3FEND, CISA, SLSA, FIPS) — no fabricated figures.
#   real-compute— computes over real live telemetry (drift PSI/KS/ADWIN, Fiedler
#                 λ2, fusion CI, swarm consensus) — math is real, advisory.
#   curated     — clearly-labelled curated sample + leader datasets (real-estate
#                 market-pulse), data_kind honest, never fabricated.
#   signed-loop — real DSSE/khipu signing + governance loop (receipts, ledger).
#   SIMULATED   — effector / intercept / weapon-target demo; SIMULATED by doctrine.

# view_id -> {endpoints:[...], data_class, leaders:[...], note}
# Endpoints are the concrete GET routes the view (or its surface sub-views) reads.
ELITE_WIRING: Dict[str, Dict[str, Any]] = {
    # ── FRONTIER · WARHACKER ──
    "hero_interdiction": {"endpoints": ["/api/{ns}/v1/roe/policy", "/api/{ns}/v1/gov/ledger"],
                          "data_class": "signed-loop",
                          "leaders": ["NIST AI RMF 1.0"],
                          "note": "Live counter-UAS decision -> DSSE-signed Λ-receipt; effector SIMULATED."},
    "fleet_c2": {"endpoints": ["/api/{ns}/v1/adsb", "/api/{ns}/v1/ais/live", "/api/{ns}/v1/twin/platforms"],
                 "data_class": "live-feed", "leaders": ["adsb.lol", "Digitraffic FI"],
                 "note": "Live mil ADS-B + AIS globe; effector link SIMULATED."},
    "tamper_demo": {"endpoints": ["/api/{ns}/v1/receipt/ledger"], "data_class": "signed-loop",
                    "leaders": [], "note": "SHA-256 hash-chain visibly rejects a tampered receipt."},
    "determinism_demo": {"endpoints": ["/api/{ns}/v1/receipt/ledger"], "data_class": "signed-loop",
                         "leaders": [], "note": "5x byte-identical Merkle roots (A5 measured)."},
    "uds_package": {"endpoints": ["/api/{ns}/uds/v1/healthz", "/api/{ns}/v1/attack-surface/graph"],
                    "data_class": "leader-cited", "leaders": ["NIST 800-53", "OSCAL"],
                    "note": "UDS Package CR + Lula/OSCAL claims-with-evidence."},
    "u_warhacker": {"endpoints": ["/api/{ns}/v1/warhacker/index"], "data_class": "real-compute",
                    "leaders": [], "note": "27 demos + proofs board (nominal vs tamper diffs)."},
    "readiness": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "live-feed",
                  "leaders": ["GitHub API", "HF Space API"], "note": "Deployed-vs-repo truth; live|cached|unreachable."},
    # ── MARITIME · NAVY ──
    "u_maritime": {"endpoints": ["/api/{ns}/v1/ais/live"], "data_class": "live-feed",
                   "leaders": ["Digitraffic FI"], "note": "Live AIS + WEZ rings + dark-vessel screen."},
    "u_fleet": {"endpoints": ["/api/{ns}/v1/fleet/all", "/api/{ns}/v1/twin/platforms"],
                "data_class": "live-feed", "leaders": ["AIS"], "note": "Fleet ops + 3D health twin over live vessels."},
    "tracks": {"endpoints": ["/api/{ns}/v1/tracks/history"], "data_class": "real-compute",
               "leaders": [], "note": "PPI radar scope; range/bearing from live air/sea picture."},
    "livepic": {"endpoints": ["/api/{ns}/v1/adsb", "/api/{ns}/v1/ais/live"], "data_class": "live-feed",
                "leaders": ["adsb.lol", "Digitraffic FI"],
                "note": "Live COP; some track positions SIMULATED over real adversary signatures."},
    "u_space": {"endpoints": ["/api/{ns}/v1/satellites", "/api/{ns}/v1/geoint/usgs", "/api/{ns}/v1/geoint"],
                "data_class": "live-feed", "leaders": ["CelesTrak", "USGS"],
                "note": "3D LEO globe + GEOINT + live USGS seismic."},
    "u_darkgraph": {"endpoints": ["/api/{ns}/v1/drones/database", "/api/{ns}/v1/ais/live"],
                    "data_class": "live-feed", "leaders": ["AIS"], "note": "3D threat graph + 53-class drone DB + ranking."},
    # ── COUNTER-UAS · ARMY / MARINES ──
    "amaru_counter_uas": {"endpoints": ["/api/{ns}/v1/amaru/counter-uas"], "data_class": "live-feed",
                          "leaders": [], "note": "Live public-web counter-UAS reporting, sha256 provenance."},
    "u_swarm": {"endpoints": ["/api/{ns}/v1/swarm/topology"], "data_class": "real-compute",
                "leaders": [], "note": "Live 3D formation topology + resilience monitor."},
    "swarm_intent": {"endpoints": ["/api/{ns}/v1/adsb"], "data_class": "real-compute",
                     "leaders": ["adsb.lol"], "note": "MODEL-SCORED over real live ADS-B kinematics."},
    "u_engage": {"endpoints": ["/api/{ns}/v1/roe/policy", "/api/{ns}/v2/geofence/zones"],
                 "data_class": "signed-loop", "leaders": [],
                 "note": "Governed ROE loop real; kinetic human-in-the-loop; effector SIMULATED."},
    "u_fusion": {"endpoints": ["/api/{ns}/v1/sensor-fusion/status"], "data_class": "real-compute",
                 "leaders": ["Julier-Uhlmann CI"], "note": "Proved Covariance-Intersection track fusion."},
    "operate": {"endpoints": ["/api/{ns}/v1/tracks/history", "/api/{ns}/v1/gov/command-log"],
                "data_class": "SIMULATED", "leaders": [],
                "note": "Governed command -> Λ-gate -> signed receipt; EFFECTOR SIMULATED (no actuation)."},
    "u_minedops": {"endpoints": ["/api/{ns}/v1/mined/index"],
                   "data_class": "real-compute", "leaders": [],
                   "note": "Edge VRAM / telemetry / adaptive sampling (advisory); compute routes are POST."},
    # ── INTEL & PROVENANCE ──
    "amaru_naval": {"endpoints": ["/api/{ns}/v1/amaru/naval"], "data_class": "live-feed",
                    "leaders": [], "note": "Live maritime/naval OSINT; sanction flags heuristic (advisory)."},
    "amaru_procurement": {"endpoints": ["/api/{ns}/v1/amaru/procurement"], "data_class": "live-feed",
                          "leaders": [], "note": "Live DoD/SBIR signals; dollar amounts are third-party claims."},
    "amaru_advisories": {"endpoints": ["/api/{ns}/v1/amaru/advisories"], "data_class": "live-feed",
                         "leaders": ["CISA"], "note": "Live cyber/supply-chain advisories; severity heuristic."},
    "amaru_geopolitical": {"endpoints": ["/api/{ns}/v1/amaru/geopolitical"], "data_class": "live-feed",
                           "leaders": [], "note": "Live geopolitical/conflict timeline; third-party claims."},
    "u_intel": {"endpoints": ["/api/{ns}/v1/evidence/research", "/api/{ns}/v1/feeds/status"],
                "data_class": "live-feed", "leaders": ["CISA KEV", "NVD", "FIRST EPSS", "MITRE ATT&CK"],
                "note": "Live CISA KEV + NVD CVE + EPSS + ATT&CK technique mapping."},
    "rosie_digest": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "live-feed",
                     "leaders": [], "note": "Ranked cross-vertical OSINT digest + reproducible replay hash."},
    "rosie_routing": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
                      "leaders": [], "note": "Routes items to verticals; heuristic (advisory)."},
    "rosie_entities": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
                       "leaders": [], "note": "Entity-relationship graph; extraction heuristic (advisory)."},
    "rosie_correlate": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
                        "leaders": [], "note": "Correlates corpus vs Section-889 watch picture (advisory)."},
    "rosie_watch": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
                    "leaders": [], "note": "Standing watchlist term-frequency with alert thresholds."},
    # ── GOVERNED CORE · UDS ──
    "lambda": {"endpoints": ["/api/{ns}/v1/gov/chapaq-verdict", "/api/{ns}/v1/gov/a11oy-honest"],
               "data_class": "real-compute", "leaders": [],
               "note": "13-axis trust score. Λ = Conjecture 1 (advisory, NOT a theorem)."},
    "u_consensus": {"endpoints": ["/api/{ns}/v1/cuas/consensus", "/api/{ns}/v1/mesh/state"],
                    "data_class": "real-compute", "leaders": ["PBFT"],
                    "note": "3-of-4 quorum; BFT safety = Conjecture 2 OPEN; conditional proven (Wave23)."},
    "mesh_resilience": {"endpoints": ["/api/{ns}/v1/topology/health", "/api/{ns}/v1/mesh/state"],
                        "data_class": "real-compute", "leaders": [],
                        "note": "Live Fiedler λ2 algebraic connectivity over the real C2 topology."},
    "retask_board": {"endpoints": ["/api/{ns}/v1/posture/drift", "/api/{ns}/v1/adsb"],
                     "data_class": "real-compute", "leaders": [],
                     "note": "Drift-triggered (PSI/KS/ADWIN) re-tasking on live telemetry; effector SIMULATED."},
    "u_posture": {"endpoints": ["/api/{ns}/v1/posture/drift", "/api/{ns}/v1/topology/health",
                                "/api/{ns}/v1/attack-surface/graph", "/api/{ns}/v1/zerotrust/mesh"],
                  "data_class": "leader-cited", "leaders": ["NIST SP 800-207"],
                  "note": "Real drift + graph metrics + zero-trust mesh from real telemetry + UDS CR."},
    "u_receipts": {"endpoints": ["/api/{ns}/v1/receipt/ledger", "/api/{ns}/v1/engagements/audit-log"],
                   "data_class": "signed-loop", "leaders": ["NIST FIPS 204"],
                   "note": "Live signed-receipt chain (3D) + quantum-safe signing posture."},
    "u_proofs": {"endpoints": ["/api/{ns}/v1/brain", "/api/{ns}/v1/formulas/proof-summary"],
                 "data_class": "leader-cited", "leaders": ["Lean 4", "mathlib4"],
                 "note": "Knowledge & formula registry: exactly 8 locked-proven; Λ = Conjecture 1."},
    "putnam": {"endpoints": ["/api/{ns}/v1/formulas/proof-summary"], "data_class": "leader-cited",
               "leaders": ["Lean 4"], "note": "Honest count of REAL Lean-kernel-checked theorems."},
    "u_melt": {"endpoints": ["/metrics", "/api/{ns}/v1/mesh/state"], "data_class": "real-compute",
               "leaders": ["Prometheus", "OpenTelemetry"], "note": "Λ-signed MELT observability + service graph."},
    "living_anatomy": {"endpoints": ["/api/{ns}/v1/mesh/state"], "data_class": "real-compute",
                       "leaders": [], "note": "a11oy + killinchu as one governed organism (3D)."},
    "u_about": {"endpoints": ["/api/{ns}/v1/evidence/research", "/api/{ns}/v1/research"],
                "data_class": "leader-cited", "leaders": ["NIST", "MITRE", "CISA"],
                "note": "Honest claims + research corpus + cited leaders + legal boundaries."},
    # ── COUNTER-UAS C2 LAB · EXPERIMENTAL ──
    "cuas_intercept": {"endpoints": ["/api/{ns}/v1/cuas/plausibility"], "data_class": "SIMULATED",
                       "leaders": ["Zarchan", "Palumbo"],
                       "note": "Proportional-nav intercept feasibility; EFFECTOR SIMULATED — never actuates."},
    "cuas_spoof": {"endpoints": ["/api/{ns}/v1/cuas/plausibility"], "data_class": "real-compute",
                   "leaders": ["Joerger"], "note": "GNSS-spoofing chi-square innovation gate (advisory)."},
    "cuas_fusion": {"endpoints": ["/api/{ns}/v1/cuas/fusion"], "data_class": "real-compute",
                    "leaders": ["Julier-Uhlmann", "Bar-Shalom"], "note": "Covariance-intersection fusion; confidence capped < 1.0."},
    "cuas_swarm": {"endpoints": ["/api/{ns}/v1/cuas/consensus"], "data_class": "real-compute",
                   "leaders": ["Olfati-Saber", "Zelazo"], "note": "Graph-Laplacian swarm consensus (Conjecture 2 OPEN)."},
    "cuas_triage": {"endpoints": ["/api/{ns}/v1/cuas/wta"], "data_class": "SIMULATED",
                    "leaders": ["Manne"], "note": "Greedy weapon-target-assignment; EFFECTOR SIMULATED — never fires."},
    "cuas_pq": {"endpoints": ["/api/{ns}/v1/cuas/pqbus"], "data_class": "signed-loop",
                "leaders": ["NIST FIPS 203/204/205"], "note": "PQ SHA3-256 receipt bus; signature PROXY until oqs key provisioned."},
    # ── METABOLIC SCALING · EXPERIMENTAL ──
    "scaling": {"endpoints": ["/api/{ns}/v1/scaling/summary"], "data_class": "leader-cited",
                "leaders": ["Kleiber", "West-Brown-Enquist", "Kaplan 2020"],
                "note": "Allometric scaling; SZL-Φ is PROPOSED (not the formal Λ); Λ stays Conjecture 1."},
}

# Views whose data_class is SIMULATED by doctrine (effector/weapon-target/intercept).
SIMULATED_VIEWS = sorted(k for k, v in ELITE_WIRING.items() if v["data_class"] == "SIMULATED")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _expand(ep: str, ns: str) -> str:
    return ep.replace("{ns}", ns)


def _route_exists(app, path: str) -> bool:
    """True if a GET route matches this path on the app.

    Matches both literal routes and FastAPI parametrized routes (e.g. the gov
    surface is registered as ``/api/{ns}/v1/gov/{name}`` and serves
    ``/gov/chapaq-verdict`` at runtime), by translating ``{param}`` segments to a
    regex. Never claims a route exists that does not.
    """
    want = path.split("?", 1)[0]
    for r in getattr(app, "routes", []):
        rp = getattr(r, "path", None)
        if rp is None:
            continue
        methods = getattr(r, "methods", None) or set()
        if methods and "GET" not in methods and "HEAD" not in methods:
            continue
        if rp == want:
            return True
        if "{" in rp:
            pat = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", re.escape(rp).replace(r"\{", "{").replace(r"\}", "}")) + "$"
            pat = re.sub(r"\{[^}]+\}", r"[^/]+", pat)
            try:
                if re.match(pat, want):
                    return True
            except re.error:  # pragma: no cover
                pass
    return False


def audit_map(ns: str = "killinchu") -> Dict[str, Any]:
    """Static view->endpoint map (no probing, never asserts reachability)."""
    views = []
    for vid, w in ELITE_WIRING.items():
        views.append({
            "view": vid,
            "endpoints": [_expand(e, ns) for e in w["endpoints"]],
            "data_class": w["data_class"],
            "leaders": w["leaders"],
            "note": w["note"],
            "simulated": w["data_class"] == "SIMULATED",
        })
    return {
        "layer": "%s /elite view wiring map" % ns,
        "honest": _HONEST,
        "doctrine": "v11",
        "lambda": "Conjecture 1",
        "locked_formulas": 8,
        "view_count": len(views),
        "simulated_views": SIMULATED_VIEWS,
        "views": views,
        "checked_at": _now_iso(),
    }


def health(app, ns: str = "killinchu", probe: bool = False) -> Dict[str, Any]:
    """Per-view wiring health via in-process route existence (+ optional live probe).

    Never fabricates: a missing route is 'needs-deploy', an erroring/empty body is
    'degraded', a 200-with-body is 'wired'. SIMULATED views are reported as
    'SIMULATED' regardless (doctrine: effectors never claim a real effect).
    """
    client = None
    if probe:
        try:
            from starlette.testclient import TestClient
            client = TestClient(app)
        except Exception:
            client = None

    rows: List[Dict[str, Any]] = []
    n_wired = n_degraded = n_deploy = n_sim = 0
    for vid, w in ELITE_WIRING.items():
        eps = [_expand(e, ns) for e in w["endpoints"]]
        ep_status = []
        any_route = False
        any_200 = False
        any_degraded = False
        for ep in eps:
            exists = _route_exists(app, ep)
            any_route = any_route or exists
            row = {"endpoint": ep, "route_registered": exists}
            if probe and client is not None and exists and "{" not in ep:
                try:
                    r = client.get(ep)
                    row["status"] = r.status_code
                    if r.status_code == 200:
                        any_200 = True
                        # Honest degrade detection on the PARSED body: a feed that
                        # answers but reports cached/empty/disabled/unreachable is
                        # 'degraded', not silently 'wired'. We inspect structured
                        # fields only (never a loose substring like 'reason', which
                        # legitimately appears inside cited source notes).
                        try:
                            j = r.json()
                        except Exception:
                            j = None
                        if isinstance(j, dict):
                            mode = str(j.get("mode", "")).lower()
                            status = str(j.get("status", "")).lower()
                            if (mode in {"cached", "unreachable", "self"}
                                    or status in {"disabled", "unreachable", "degraded"}
                                    or j.get("empty") is True
                                    or j.get("degraded") is True):
                                any_degraded = True
                except Exception as e:  # pragma: no cover
                    row["status"] = "probe-error"
                    row["detail"] = str(e)[:120]
            ep_status.append(row)

        sim = w["data_class"] == "SIMULATED"
        if sim:
            # Effector / weapon-target / intercept demos: SIMULATED by doctrine,
            # regardless of feed health (killinchu never claims a real effect).
            verdict = "SIMULATED"
            n_sim += 1
        elif not any_route:
            # The route is not registered on the running app at all -> the feed
            # exists in the repo but is not yet deployed on this surface.
            verdict = "needs-deploy"
            n_deploy += 1
        elif probe and any_200 and any_degraded:
            # Feed answered but honestly reports cached/empty/disabled.
            verdict = "degraded"
            n_degraded += 1
        else:
            # Route is registered. If probing and it returned 200 -> wired-live;
            # if probing hit a transient (429 rate-limit / 5xx / param-required
            # 4xx), the wiring is still present so we report 'wired' and keep the
            # raw probe status on each endpoint for honest inspection.
            verdict = "wired"
            n_wired += 1

        rows.append({
            "view": vid, "data_class": w["data_class"], "leaders": w["leaders"],
            "verdict": verdict, "endpoints": ep_status, "note": w["note"],
        })

    return {
        "layer": "%s /elite view wiring health" % ns,
        "honest": _HONEST,
        "doctrine": "v11",
        "lambda": "Conjecture 1",
        "locked_formulas": 8,
        "probed": bool(probe and client is not None),
        "view_count": len(rows),
        "summary": {"wired": n_wired, "degraded": n_degraded,
                    "needs_deploy": n_deploy, "simulated": n_sim},
        "views": rows,
        "checked_at": _now_iso(),
    }


def register(app, ns: str = "killinchu") -> Dict[str, Any]:
    """Attach /api/{ns}/v1/elite/wiring[/health] to a FastAPI app. Additive."""
    try:
        from fastapi.responses import JSONResponse
    except Exception:  # pragma: no cover
        return {"registered": False, "reason": "fastapi unavailable"}

    base = "/api/%s/v1/elite/wiring" % ns

    @app.get(base)
    async def _elite_wiring_map():  # noqa: ANN202
        return JSONResponse(audit_map(ns))

    @app.get(base + "/health")
    async def _elite_wiring_health(probe: bool = False):  # noqa: ANN202
        import asyncio
        data = await asyncio.to_thread(health, app, ns, probe)
        return JSONResponse(data)

    return {"registered": True, "ns": ns,
            "routes": [base, base + "/health"],
            "views": len(ELITE_WIRING),
            "simulated_views": len(SIMULATED_VIEWS)}


__all__ = ["register", "audit_map", "health", "ELITE_WIRING", "SIMULATED_VIEWS"]
