# SPDX-License-Identifier: Apache-2.0
"""killinchu_elite_wiring.py — /elite view → data-feed wiring map + honest health.

ADDITIVE. Pure stdlib. Registers read-only audit and decision-support surfaces
and touches NO existing route, view, feed, or effector. It answers operational
questions that the /elite console cannot answer about itself:

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

import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

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
#   interop-standard — exposes killinchu tracks over a real DoD/NATO interop
#                 standard (e.g. MITRE Cursor on Target / Event.xsd). XML
#                 export + schema validation + ingest are live; live transport
#                 (UDP multicast / TAK-server) is honestly labelled roadmap.

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
    "ais_aug2024": {"endpoints": ["/api/{ns}/v1/ais/sources", "/api/{ns}/v1/ais/aug2024/tracks",
                                  "/api/{ns}/v1/ais/aug2024/risk-board"],
                    "data_class": "signed-loop", "leaders": ["NOAA/MarineCadastre AIS"],
                    "note": ("Selectable NOAA Aug-2024 coastal-US AIS dataset (WarHacker) "
                             "alongside live feed -> Λ risk -> DSSE receipt. SAMPLE of real "
                             "AIS_2024_08_01 rows (NOT full month); live feed stays default.")},
    "u_fleet": {"endpoints": ["/api/{ns}/v1/fleet/all", "/api/{ns}/v1/twin/platforms"],
                "data_class": "live-feed", "leaders": ["AIS"], "note": "Fleet ops + 3D health twin over live vessels."},
    "tracks": {"endpoints": ["/api/{ns}/v1/tracks/history"], "data_class": "real-compute",
               "leaders": [], "note": "PPI radar scope; range/bearing from live air/sea picture."},
    "livepic": {"endpoints": ["/api/{ns}/v1/adsb", "/api/{ns}/v1/ais/live"], "data_class": "live-feed",
                "leaders": ["adsb.lol", "Digitraffic FI"],
                "note": "Live COP; some track positions SIMULATED over real adversary signatures."},
    "dataset_control": {"endpoints": ["/api/{ns}/v1/ais/live", "/api/{ns}/v1/ais/sources",
                                      "/api/{ns}/v1/maritime/overlays/pirate-attacks",
                                      "/api/{ns}/v1/maritime/overlays/world-port-index",
                                      "/api/{ns}/v1/cot/status"],
                        "data_class": "live-feed", "leaders": ["Digitraffic FI", "NOAA/MarineCadastre", "NGA WPI", "MITRE CoT"],
                        "note": "Unified dataset/overlay control: Live AIS (default, on main) + NOAA Aug-2024 sample (PR#133) "
                                "+ pirate/WPI overlays (PR#134) + CoT export (PR#132). Probes each route live; unmerged routes "
                                "are honestly labelled 'available when PR #N merges' (the wiring health will show them "
                                "needs-deploy until those PRs land). Additive; sample never claimed live."},
    "u_space": {"endpoints": ["/api/{ns}/v1/satellites", "/api/{ns}/v1/geoint/usgs", "/api/{ns}/v1/geoint"],
                "data_class": "live-feed", "leaders": ["CelesTrak", "USGS"],
                "note": "3D LEO globe + GEOINT + live USGS seismic."},
    "u_darkgraph": {"endpoints": ["/api/{ns}/v1/drones/database", "/api/{ns}/v1/ais/live"],
                    "data_class": "live-feed", "leaders": ["AIS"], "note": "3D threat graph + 53-class drone DB + ranking."},
    "cot_interop": {"endpoints": ["/api/{ns}/v1/cot/status", "/api/{ns}/v1/cot/export"],
                    "data_class": "interop-standard", "leaders": ["MITRE CoT", "MIL-STD-2525", "TAK"],
                    "note": "Every track emittable as standards-compliant CoT 2.0 XML (Event.xsd); "
                            "export+validate+ingest LIVE, UDP/TAK-server ROADMAP."},
    # ── COUNTER-UAS · ARMY / MARINES ──
    "osint_counter_uas": {"endpoints": ["/api/{ns}/v1/osint/feed/counter-uas"], "data_class": "live-feed",
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
    "osint_naval": {"endpoints": ["/api/{ns}/v1/osint/feed/naval"], "data_class": "live-feed",
                    "leaders": [], "note": "Live maritime/naval OSINT; sanction flags heuristic (advisory)."},
    "osint_procurement": {"endpoints": ["/api/{ns}/v1/osint/feed/procurement"], "data_class": "live-feed",
                          "leaders": [], "note": "Live DoD/SBIR signals; dollar amounts are third-party claims."},
    "osint_advisories": {"endpoints": ["/api/{ns}/v1/osint/feed/advisories"], "data_class": "live-feed",
                         "leaders": ["CISA"], "note": "Live cyber/supply-chain advisories; severity heuristic."},
    "osint_geopolitical": {"endpoints": ["/api/{ns}/v1/osint/feed/geopolitical"], "data_class": "live-feed",
                           "leaders": [], "note": "Live geopolitical/conflict timeline; third-party claims."},
    "u_intel": {"endpoints": ["/api/{ns}/v1/evidence/research", "/api/{ns}/v1/feeds/status"],
                "data_class": "live-feed", "leaders": ["CISA KEV", "NVD", "FIRST EPSS", "MITRE ATT&CK"],
                "note": "Live CISA KEV + NVD CVE + EPSS + ATT&CK technique mapping."},
    "operator_digest": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "live-feed",
                     "leaders": [], "note": "Ranked cross-vertical OSINT digest + reproducible replay hash."},
    "operator_routing": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
                      "leaders": [], "note": "Routes items to verticals; heuristic (advisory)."},
    "operator_entities": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
                       "leaders": [], "note": "Entity-relationship graph; extraction heuristic (advisory)."},
    "operator_correlate": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
                        "leaders": [], "note": "Correlates corpus vs Section-889 watch picture (advisory)."},
    "operator_watch": {"endpoints": ["/api/{ns}/v1/osint/archive/recent"], "data_class": "real-compute",
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
    # ── DYNAMICALLY-REGISTERED FORMULA / OSINT / PROTOCOL TABS ──
    # These views are attached to VIEWS at runtime by their own self-contained
    # patch blocks in killinchu_elite_console.py (regAtlas / regNeuro / regChain /
    # regEnt / regSovereignty + the osint_intel, conjecturefactory, decoders,
    # mosaic, provenance, pqc registrations). They were previously absent from the
    # wiring map, so the self-audit under-reported its own coverage. Endpoints +
    # GET-readability verified in-process against the running app.
    "atlas": {"endpoints": ["/api/{ns}/v1/scaling/summary", "/api/{ns}/v1/unified/summary",
                            "/api/{ns}/v1/cuas/summary"],
              "data_class": "leader-cited", "leaders": ["Kleiber", "Sherman-Morgan", "NIST"],
              "note": "Formula Atlas: live GET→JSON index of every formula module; honest tier read live from /summary; Λ stays Conjecture 1; SZL claims no formula as its own."},
    "neuro": {"endpoints": ["/api/{ns}/v1/neuro/summary"], "data_class": "leader-cited",
              "leaders": ["Hebb", "Oja", "Bienenstock-Cooper-Munro", "Song-Abbott STDP"],
              "note": "Neuroplasticity formulas (Hebb/Oja/BCM/STDP); EXPERIMENTAL — PROPOSED, not the formal Λ."},
    "l6chain": {"endpoints": ["/api/{ns}/v1/chain/summary"], "data_class": "signed-loop",
                "leaders": ["Denning lattice", "OSCAL"],
                "note": "Chain-of-Title (L6): assemble/verify a signed chain-of-custody; honest tier from /summary."},
    "entangle": {"endpoints": ["/api/{ns}/v1/entangle/summary"], "data_class": "leader-cited",
                 "leaders": ["Wootters concurrence", "Vidal-Werner negativity", "CHSH"],
                 "note": "Entanglement formulas (concurrence/negativity/CHSH/monogamy); capacity PROPOSED, not the formal Λ."},
    "sovereignty": {"endpoints": ["/api/{ns}/v1/allodial/summary"], "data_class": "leader-cited",
                    "leaders": ["Denning 1976", "Goguen-Meseguer 1982", "EU-CSF"],
                    "note": "Allodial AI-sovereignty lattice + non-interference + SovScore; EXPERIMENTAL/PROPOSED."},
    "mosaic": {"endpoints": ["/api/{ns}/v1/mosaic/cop"], "data_class": "real-compute",
               "leaders": [], "note": "Mosaic common-operating-picture + hull-stress/score; compute routes are POST; effector SIMULATED."},
    "provenance": {"endpoints": ["/api/{ns}/v1/receipt/ledger"], "data_class": "signed-loop",
                   "leaders": ["NIST FIPS 204"], "note": "Live signed-receipt provenance ledger (DSSE/khipu hash-chain)."},
    "osint_intel": {"endpoints": ["/api/{ns}/v1/osint/intel"], "data_class": "live-feed",
                    "leaders": [], "note": "Aggregated cross-vertical OSINT intel surface; live|cached honest label; third-party claims."},
    "conjecturefactory": {"endpoints": ["/api/{ns}/v1/conjecture-factory"], "data_class": "leader-cited",
                          "leaders": [], "note": "Honest board of OPEN factory-generated conjectures; a conjecture is NEVER a theorem; Conjecture 1 stays OPEN."},
    "pqc": {"endpoints": ["/api/{ns}/v1/cuas/pqbus"], "data_class": "signed-loop",
            "leaders": ["NIST FIPS 203/204/205"],
            "note": "Post-quantum SHA3-256 receipt bus; signature PROXY until oqs key provisioned (honest)."},
    "decoders": {"endpoints": ["/api/{ns}/v1/drones/database", "/api/{ns}/v1/samples"],
                 "data_class": "real-compute", "leaders": ["ASTM F3411 Remote ID", "DO-260 ADS-B", "MAVLink"],
                 "note": "Protocol decoders (Remote ID / ADS-B / MAVLink); decode routes are POST; broadcasts are unverified claims — a lead, not proof."},
    # ── CONSTITUTIONAL GOVERNANCE · FORMAL / LTL RING ──
    # QHAWAQ is the per-ACTION formal monitor: every proposed agent/effector action
    # is checked against LTL + predicate invariants BEFORE any (SIMULATED) effector,
    # verdict ALLOW / REQUIRE-HUMAN-CONFIRM / BLOCK + proof-trace + signed receipt
    # forwarded to the unified ledger (organ=killinchu-qhawaq). Previously absent
    # from this map even though szl_qhawaq is registered, so the self-audit under-
    # reported the formal ring. /invariants is GET (probed); /check is POST.
    "qhawaq": {"endpoints": ["/api/{ns}/v1/qhawaq/invariants", "/api/{ns}/v1/qhawaq/check"],
               "data_class": "signed-loop", "leaders": ["LTL runtime verification", "NIST AI RMF 1.0"],
               "note": ("Formal/LTL runtime constitutional ring: each proposed action is "
                        "checked BEFORE any SIMULATED effector — ALLOW / REQUIRE-HUMAN-CONFIRM "
                        "/ BLOCK + proof-trace + signed BLOCK receipt forwarded to the unified "
                        "ledger (organ=killinchu-qhawaq). Λ = Conjecture 1 (advisory); Khipu "
                        "BFT safety = Conjecture 2, liveness = Conjecture 3 — proof-deferred, "
                        "NOT proven. Effector SIMULATED human-on-loop.")},
}

# Views whose data_class is SIMULATED by doctrine (effector/weapon-target/intercept).
SIMULATED_VIEWS = sorted(k for k, v in ELITE_WIRING.items() if v["data_class"] == "SIMULATED")


# ── QHAWAQ intercept → unified ledger forward ───────────────────────────────
# The unified receipt ledger lives in the a11oy Space (szl_lake_ingest). killinchu
# forwards QHAWAQ's signed verdict/BLOCK receipts to that sink over HTTP, organ-
# tagged "killinchu-qhawaq" so the cross-organ chain stays auditable. Env-overridable;
# honest default. The intercept runs BEFORE any (SIMULATED) effector.
LEDGER_SINK_URL = (os.environ.get("SZL_LAKE_SINK_URL")
                   or "https://szlholdings-a11oy.hf.space/api/lake/v1").rstrip("/") + "/receipts"
QHAWAQ_ORGAN = "killinchu-qhawaq"
# Honest doctrine note carried on EVERY intercept response — NEVER claim BFT proven.
QHAWAQ_CONJECTURE_NOTE = "Conjecture 2/3 proof-deferred, NOT proven"


def forward_receipt_to_ledger(receipt: Dict[str, Any], organ: str = QHAWAQ_ORGAN,
                              timeout: float = 4.0) -> Dict[str, Any]:
    """Fire-and-forget POST of a signed QHAWAQ receipt to the unified ledger.

    Never raises and never blocks a governed action — a sink hiccup degrades
    honestly (status recorded; the verdict is unaffected)."""
    if not isinstance(receipt, dict):
        return {"ok": False, "reason": "receipt must be a JSON object"}
    rec = dict(receipt)
    rec.setdefault("organ", organ)
    try:
        import httpx
        with httpx.Client(timeout=timeout) as c:
            r = c.post(LEDGER_SINK_URL, json=rec)
        return {"ok": r.status_code < 400, "status": r.status_code,
                "sink": LEDGER_SINK_URL, "organ": organ}
    except Exception as e:  # honest degrade — never raise into a governed turn
        return {"ok": False, "reason": "ledger forward error: %r" % (e,),
                "sink": LEDGER_SINK_URL, "organ": organ}


def intercept_action(action: Dict[str, Any], sign_fn: Optional[Callable[[Any], dict]] = None,
                     ns: str = "killinchu", forward: bool = True) -> Dict[str, Any]:
    """QHAWAQ runtime intercept for the elite flow: check ONE proposed agent/effector
    action against the formal LTL + predicate invariants BEFORE any (SIMULATED)
    effector, and forward the signed verdict receipt to the unified ledger
    (organ=killinchu-qhawaq).

    Returns {verdict, allowed, requires_human, blocked, signed_receipt,
    ledger_forward, checks, confidence, note}. ``verdict`` is one of
    ALLOW / REQUIRE-HUMAN-CONFIRM / BLOCK. Honest: BFT safety/liveness are NOT
    proven — ``note`` says so explicitly. Never raises; if QHAWAQ is unavailable it
    FAILS CLOSED (REQUIRE-HUMAN-CONFIRM) rather than silently allowing an effector."""
    try:
        import szl_qhawaq
    except Exception as e:  # fail CLOSED — never silently allow an effector
        return {"verdict": "REQUIRE-HUMAN-CONFIRM", "allowed": False,
                "requires_human": True, "blocked": False, "signed_receipt": None,
                "ledger_forward": {"ok": False, "reason": "szl_qhawaq unavailable: %r" % (e,)},
                "note": QHAWAQ_CONJECTURE_NOTE,
                "honesty": "QHAWAQ unavailable — failing closed to human confirm; no effector."}
    try:
        result = szl_qhawaq.check_action(action, sign_fn=sign_fn, ns=ns)
    except Exception as e:  # fail CLOSED on any monitor error
        return {"verdict": "REQUIRE-HUMAN-CONFIRM", "allowed": False,
                "requires_human": True, "blocked": False, "signed_receipt": None,
                "ledger_forward": {"ok": False, "reason": "qhawaq check raised: %r" % (e,)},
                "note": QHAWAQ_CONJECTURE_NOTE,
                "honesty": "QHAWAQ monitor raised — failing closed to human confirm; no effector."}
    verdict = result.get("verdict")
    signed = result.get("signed_receipt")
    fwd = None
    if forward and isinstance(signed, dict):
        fwd = forward_receipt_to_ledger(signed, organ=QHAWAQ_ORGAN)
    return {
        "verdict": verdict,
        "allowed": verdict == "ALLOW",
        "requires_human": verdict == "REQUIRE-HUMAN-CONFIRM",
        "blocked": verdict == "BLOCK",
        "signed_receipt": signed,
        "ledger_forward": fwd,
        "checks": result.get("checks"),
        "confidence": result.get("confidence"),
        "note": QHAWAQ_CONJECTURE_NOTE,
    }


def register_intercept(app, ns: str = "killinchu",
                       sign_fn: Optional[Callable[[Any], dict]] = None) -> Dict[str, Any]:
    """Mount the QHAWAQ elite intercept route (POST). Additive; called from serve.py's
    QHAWAQ block so the REAL DSSE signer is in scope → genuinely signed receipts.

    POST /api/{ns}/v1/elite/qhawaq/intercept  body: {"action": {...}} (or the action
    object directly) → verdict + signed_receipt + ledger_forward + conjecture note."""
    try:
        from fastapi.responses import JSONResponse
    except Exception:  # pragma: no cover
        return {"registered": False, "reason": "fastapi unavailable"}

    path = "/api/%s/v1/elite/qhawaq/intercept" % ns

    @app.post(path)
    async def _elite_qhawaq_intercept(request):  # noqa: ANN202
        import asyncio
        try:
            body = await request.json()
        except Exception:
            body = {}
        action = body.get("action") if isinstance(body, dict) and "action" in body else body
        # check_action + ledger POST are blocking — run off the event loop.
        out = await asyncio.to_thread(intercept_action, action, sign_fn, ns)
        return JSONResponse(out)

    return {"registered": True, "ns": ns, "route": path, "organ": QHAWAQ_ORGAN,
            "sink": LEDGER_SINK_URL, "note": QHAWAQ_CONJECTURE_NOTE}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _expand(ep: str, ns: str) -> str:
    return ep.replace("{ns}", ns)


def _route_exists(app, path: str) -> bool:
    """True if a GET route matches this path on the app.

    Matches both literal routes and FastAPI parametrized routes (e.g. the gov
    surface is registered as ``/api/{ns}/v1/gov/{name}`` and serves
    ``/gov/chapaq-verdict`` at runtime). Current FastAPI releases can retain an
    ``include_router()`` mount as a lazy ``_IncludedRouter`` whose public
    ``path`` is ``None``. Ask each ASGI route whether it fully matches a real GET
    scope first so those mounted routes are not falsely labelled
    ``needs-deploy``. The literal/parameterized string check remains as a
    compatibility fallback for older FastAPI and lightweight test doubles.
    Never claims a route exists that the application router would not serve.
    """
    want = path.split("?", 1)[0]

    try:
        from starlette.routing import Match
    except Exception:  # pragma: no cover - string fallback remains available
        Match = None  # type: ignore[assignment]

    if Match is not None:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": want,
            "raw_path": want.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("elite-wiring-audit", 0),
            "server": ("elite-wiring-audit", 80),
            "root_path": "",
        }
        for r in getattr(app, "routes", []):
            # Restrict ASGI matching to FastAPI's pathless lazy include wrapper.
            # Asking a normal catch-all route (for example the SPA
            # ``/{full_path:path}``) would match every missing API path and paint
            # the entire audit green. Ordinary routes stay on the strict path
            # checks below.
            if (getattr(r, "path", None) is not None
                    or getattr(r, "original_router", None) is None):
                continue
            try:
                matched, _ = r.matches(scope)
                if matched == Match.FULL:
                    return True
            except Exception:
                # A third-party route without Starlette's matching contract
                # must not break the audit; the strict string fallback below
                # can still recognize ordinary FastAPI/Starlette routes.
                continue

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


def health(app, ns: str = "killinchu", probe: bool = False,
           probe_limit: Optional[int] = None) -> Dict[str, Any]:
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

    probe_cache: Dict[str, Dict[str, Any]] = {}
    unique_probes = 0
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
                if ep not in probe_cache:
                    if probe_limit is not None and unique_probes >= probe_limit:
                        probe_cache[ep] = {"status": "probe-budget-exhausted"}
                    else:
                        unique_probes += 1
                        try:
                            r = client.get(ep)
                            try:
                                body = r.json()
                            except Exception:
                                body = None
                            probe_cache[ep] = {"status": r.status_code, "body": body}
                        except Exception as e:  # pragma: no cover
                            probe_cache[ep] = {
                                "status": "probe-error",
                                "detail": str(e)[:120],
                            }
                probe_result = probe_cache[ep]
                row["status"] = probe_result["status"]
                if "detail" in probe_result:
                    row["detail"] = probe_result["detail"]
                if probe_result["status"] == 200:
                    any_200 = True
                    # Honest degrade detection on the PARSED body: a feed that
                    # answers but reports cached/empty/disabled/unreachable is
                    # 'degraded', not silently 'wired'. We inspect structured
                    # fields only (never a loose substring like 'reason', which
                    # legitimately appears inside cited source notes).
                    j = probe_result.get("body")
                    if isinstance(j, dict):
                        mode = str(j.get("mode", "")).lower()
                        status = str(j.get("status", "")).lower()
                        if (mode in {"cached", "unreachable", "self"}
                                or status in {"disabled", "unreachable", "degraded"}
                                or j.get("empty") is True
                                or j.get("degraded") is True):
                            any_degraded = True
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
        "probe_limit": probe_limit,
        "unique_probes": unique_probes,
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


__all__ = ["register", "register_intercept", "intercept_action",
           "forward_receipt_to_ledger", "audit_map", "health",
           "ELITE_WIRING", "SIMULATED_VIEWS", "QHAWAQ_ORGAN",
           "QHAWAQ_CONJECTURE_NOTE", "LEDGER_SINK_URL"]


# ---------------------------------------------------------------------------
# Decision Genome frontier: cross-tab incident command and authorization lease
# preview. This layer never executes an effector and never expands authority.
# ---------------------------------------------------------------------------
DECISION_GENOME_SCHEMA_ID = "urn:szl:contracts:decision-genome:v1"
FRONTIER_POLICY_VERSION = "killinchu-incident-command-v1"
_READ_ONLY_ACTIONS = frozenset({
    "OBSERVE",
    "OPEN_INCIDENT",
    "REQUEST_READ_ONLY_PROBE",
    "EXPORT_RECEIPT",
})


def _frontier_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _frontier_sha(value):
    import hashlib
    import json
    body = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _frontier_source_state(endpoint_rows, probe):
    rows = endpoint_rows if isinstance(endpoint_rows, list) else []
    if not rows:
        return "UNAVAILABLE"
    if any(row.get("status") == "probe-budget-exhausted"
           for row in rows if isinstance(row, dict)
           and row.get("route_registered")):
        return "CACHED"
    if any(str(row.get("status", "")).lower() in
           {"probe-error", "degraded", "unreachable", "disabled"}
           for row in rows if isinstance(row, dict)):
        return "DEGRADED"
    statuses = [row.get("status") for row in rows
                if isinstance(row, dict) and isinstance(row.get("status"), int)]
    if any(status >= 400 for status in statuses):
        return "DEGRADED"
    registered = [bool(row.get("route_registered"))
                  for row in rows if isinstance(row, dict)]
    if registered and not all(registered):
        return "UNAVAILABLE"
    registered_rows = [row for row in rows
                       if isinstance(row, dict) and row.get("route_registered")]
    if (probe and registered_rows
            and all(row.get("status") == 200 for row in registered_rows)):
        return "LIVE"
    if registered and all(registered):
        return "CACHED"
    return "UNAVAILABLE"


def incident_command(app, ns="killinchu", probe=False, probe_limit=8):
    """Project every /elite tab into one prioritized operational action queue."""
    limit = max(1, min(32, int(probe_limit)))
    wiring = health(app, ns, bool(probe), limit if probe else 0)
    probe_performed = bool(wiring.get("probed"))
    evidence_label = "MEASURED" if probe_performed else "VERIFIED"
    views = (wiring.get("views") or wiring.get("wiring")
             or wiring.get("results") or {})
    if isinstance(views, dict):
        rows = [{"view": key, **(value if isinstance(value, dict) else {})}
                for key, value in views.items()]
    elif isinstance(views, list):
        rows = [value for value in views if isinstance(value, dict)]
    else:
        rows = []

    queue = []
    for row in rows:
        endpoint_rows = row.get("endpoints", [])
        source_state = _frontier_source_state(endpoint_rows, probe_performed)
        if source_state == "UNAVAILABLE":
            priority, action = 90, "RESTORE_ROUTE_OR_SOURCE"
            approval = "maintainer"
        elif source_state == "DEGRADED":
            priority, action = 75, "INVESTIGATE_SOURCE_FRESHNESS"
            approval = "operator"
        elif source_state == "CACHED":
            priority, action = 40, "RUN_READ_ONLY_PROBE"
            approval = "operator"
        else:
            priority, action = 10, "MONITOR"
            approval = "none"
        queue.append({
            "incident_id": "wiring:%s" % str(row.get("view", row.get("id", "unknown"))),
            "view": row.get("view", row.get("id", "unknown")),
            "priority": priority,
            "source_state": source_state,
            "wiring_verdict": row.get("verdict", "unknown"),
            "recommended_action": action,
            "required_authority": approval,
            "affected_endpoints": endpoint_rows,
            "evidence_label": evidence_label,
            "executable": False,
        })
    queue.sort(key=lambda item: (-item["priority"], str(item["view"])))
    observed_at = _frontier_now()
    queue_digest = _frontier_sha(queue)
    needs_action = any(item["priority"] >= 40 for item in queue)
    if not probe_performed:
        next_allowed_action = "REQUEST_READ_ONLY_PROBE"
    elif needs_action:
        next_allowed_action = "OPEN_INCIDENT"
    else:
        next_allowed_action = "OBSERVE"
    return {
        "service": "killinchu-incident-command",
        "version": "v1",
        "schema_id": DECISION_GENOME_SCHEMA_ID,
        "policy_version": FRONTIER_POLICY_VERSION,
        "observed_at": observed_at,
        "probe_requested": bool(probe),
        "probe_performed": probe_performed,
        "probe_limit": limit,
        "unique_probes": wiring.get("unique_probes", 0),
        "evidence_label": evidence_label,
        "executable": False,
        "summary": {
            "total_views": len(queue),
            "needs_action": sum(1 for item in queue if item["priority"] >= 40),
            "live": sum(1 for item in queue if item["source_state"] == "LIVE"),
            "cached": sum(1 for item in queue if item["source_state"] == "CACHED"),
            "degraded": sum(1 for item in queue if item["source_state"] == "DEGRADED"),
            "unavailable": sum(1 for item in queue if item["source_state"] == "UNAVAILABLE"),
        },
        "queue": queue,
        "queue_digest": queue_digest,
        "next_allowed_action": next_allowed_action,
        "invariant": ("Read-only decision support only. No effector is executed; "
                      "every non-observation action requires separate authority."),
    }


def authorization_lease_preview(body, sign_fn=None):
    """Evaluate lease shape and action bounds without asserting signature validity."""
    body = body if isinstance(body, dict) else {}
    lease = body.get("lease") if isinstance(body.get("lease"), dict) else {}
    action = str(body.get("action", "")).upper()
    blockers = []
    required = ("lease_id", "issuer", "subject", "mission_id", "not_before",
                "expires_at", "max_uncertainty", "decision_digest")
    for field in required:
        if field not in lease:
            blockers.append("MISSING_%s" % field.upper())
    allowed = lease.get("allowed_actions")
    if not isinstance(allowed, list) or action not in {
            str(item).upper() for item in allowed}:
        blockers.append("ACTION_OUTSIDE_LEASE")
    if action not in _READ_ONLY_ACTIONS:
        blockers.append("EFFECTOR_ACTION_NOT_ALLOWED_IN_PREVIEW")
    decision_digest = str(body.get("decision_digest", "")).lower()
    if decision_digest != str(lease.get("decision_digest", "")).lower():
        blockers.append("DECISION_DIGEST_MISMATCH")
    try:
        import math
        uncertainty = float(body.get("uncertainty", 1.0))
        max_uncertainty = float(lease.get("max_uncertainty", 0.0))
        if (not math.isfinite(uncertainty)
                or not math.isfinite(max_uncertainty)
                or uncertainty < 0.0
                or max_uncertainty < 0.0):
            blockers.append("INVALID_UNCERTAINTY")
        elif uncertainty > max_uncertainty:
            blockers.append("UNCERTAINTY_EXCEEDS_LEASE")
    except (TypeError, ValueError):
        blockers.append("INVALID_UNCERTAINTY")
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        not_before = datetime.fromisoformat(
            str(lease.get("not_before", "")).replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(
            str(lease.get("expires_at", "")).replace("Z", "+00:00"))
        if not_before >= expires_at:
            blockers.append("INVALID_LEASE_WINDOW")
        if now < not_before:
            blockers.append("LEASE_NOT_ACTIVE")
        if now >= expires_at:
            blockers.append("LEASE_EXPIRED")
    except (TypeError, ValueError):
        blockers.append("INVALID_LEASE_TIME")
    if lease.get("revoked_at"):
        blockers.append("LEASE_REVOKED")

    # v1 deliberately does not trust a caller-asserted verification flag.
    blockers.append("CRYPTOGRAPHIC_LEASE_VERIFIER_UNAVAILABLE")
    preview = {
        "service": "killinchu-authorization-lease-preview",
        "schema_id": DECISION_GENOME_SCHEMA_ID,
        "policy_version": FRONTIER_POLICY_VERSION,
        "evaluated_at": _frontier_now(),
        "action": action,
        "verdict": "WITHHOLD" if blockers else "REVIEW_REQUIRED",
        "blockers": sorted(set(blockers)),
        "signature_verification": "UNAVAILABLE",
        "executable": False,
        "evidence_label": "VERIFIED",
        "invariant": ("Preview never executes an action and never treats caller-supplied "
                      "signature state as verification."),
    }
    preview["digest"] = _frontier_sha(preview)
    governed = intercept_action(
        {
            "action": "authorization_lease_preview",
            "requested_action": action,
            "lease_id": lease.get("lease_id"),
            "decision_digest": decision_digest,
            "preview_digest": preview["digest"],
            "executable": False,
        },
        sign_fn=sign_fn,
        forward=False,
    )
    preview["governance"] = governed
    return preview


_register_elite_wiring_base = register


def register(app, ns: str = "killinchu") -> Dict[str, Any]:
    """Register the original wiring audit plus the Decision Genome frontier."""
    import asyncio
    status = _register_elite_wiring_base(app, ns)
    base = "/api/%s/v1/elite" % ns
    incident_path = base + "/incident-command"
    lease_path = base + "/authorization/lease/preview"
    try:
        from szl_dsse import sign_payload as frontier_sign_payload
    except Exception:  # pragma: no cover - honest unsigned fallback
        frontier_sign_payload = None

    async def _incident_command(probe: bool = False,
                                probe_limit: int = 8):  # noqa: ANN202
        data = await asyncio.to_thread(
            incident_command,
            app,
            ns,
            probe,
            probe_limit,
        )
        return data

    async def _lease_preview(body: dict):  # noqa: ANN202
        return await asyncio.to_thread(
            authorization_lease_preview,
            body,
            frontier_sign_payload,
        )

    if not _route_exists(app, incident_path):
        app.add_api_route(incident_path, _incident_command, methods=["GET"])
    if not _route_exists(app, lease_path):
        app.add_api_route(lease_path, _lease_preview, methods=["POST"])
    routes = list(status.get("routes", [])) if isinstance(status, dict) else []
    routes.extend([incident_path, lease_path])
    if isinstance(status, dict):
        status["routes"] = routes
        status["decision_genome_schema_id"] = DECISION_GENOME_SCHEMA_ID
        status["frontier"] = "registered"
        return status
    return {"registered": True, "ns": ns, "routes": routes,
            "decision_genome_schema_id": DECISION_GENOME_SCHEMA_ID}


__all__.extend([
    "incident_command",
    "authorization_lease_preview",
    "DECISION_GENOME_SCHEMA_ID",
    "FRONTIER_POLICY_VERSION",
])
