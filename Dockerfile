# syntax=docker/dockerfile:1
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
#
# Killinchu HF Docker Space — Andean Drone Intelligence (vessels pivot).
#
# a11oy-style: FastAPI app, mount pre-built React SPA from /app/static, base path "/",
# SPA history fallback, /api/killinchu/v1/* endpoints, honest disclosure block.
# No Node runtime needed (pure-FastAPI backend; SPA is pre-built at deploy time).
#
# Serves:
#   /                       — SPA front door (drone intelligence landing)
#   /assets/*               — SPA JS/CSS chunks (vite base="/")
#   /drones /map /swarm ... — SPA routes (history fallback)
#   /api/killinchu/v1/*      — real protocol decoders + drone DB + counter-UAS Λ-gate
#   /api/vessels/*           — preserved aliases (vessels GREEN baseline, ADDITIVE)
#
# HF Space requirement: listen on PORT 7860.

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Python dependencies — real protocol stacks, no mocks.
RUN pip install --no-cache-dir \
    "fastapi>=0.111.0,<1.0.0" \
    "uvicorn[standard]>=0.29.0,<1.0.0" \
    "httpx>=0.27.0,<1.0.0" \
    "starlette>=0.37.0" \
    "pyModeS>=3.3.0,<4.0" \
    "pymavlink>=2.4.40"
# BE hardening: slowapi rate limiter (60/min/IP). pydantic+fastapi already present.
RUN pip install --no-cache-dir "slowapi>=0.1.9"

# Real persistent backend: psycopg (v3) so killinchu_backend is genuinely Postgres-first
# when a DATABASE_URL is configured. Pure-python wheel; if absent the backend still runs
# on durable SQLite (HF Spaces has no Postgres). `|| true` so a wheel hiccup can never
# break the image build — the backend degrades to SQLite, never crashes.
RUN pip install --no-cache-dir "psycopg[binary]>=3.1" || pip install --no-cache-dir "psycopg>=3.1" || true

# ADDITIVE (Yachay / Provenance Hardening): cryptography for DSSE+Cosign Khipu signing.
RUN pip install --no-cache-dir "cryptography>=42.0"
# ADDITIVE (Formulas real-edge-v2, Opus 4.8, 2026-06-03): numpy is REQUIRED for the real
# Kalman trajectory smoother in szl_shared_formulas/kalman.py (no pure-Python mock path).
RUN pip install --no-cache-dir "numpy>=1.26"
# ADDITIVE (Yachay / PQC): pure-Python ML-DSA-65 (NIST FIPS 204) backend for
# /khipu/sign?mode={pqc,hybrid}. liboqs (oqs-python) is preferred in prod but is
# a C lib not always installable; dilithium-py is the pure-Python fallback so
# hybrid signing works in the Space. ECDSA stays the default regardless.
RUN pip install --no-cache-dir "dilithium-py>=1.0.0"
# ADDITIVE (Wave A real-data feeds): websocket-client for the AISStream.io live
# wss vessel collector (PRIMARY keyed AIS source). Optional — the vessels feed
# degrades gracefully to the no-key Digitraffic REST fallback if this is absent
# or no AISStream key is in the Space secret store. Real data either way.
RUN pip install --no-cache-dir "websocket-client>=1.6.0" || true
# ADDITIVE (real-edge): numpy for the constant-velocity Kalman trajectory smoother
# in szl_shared_formulas/kalman.py (real linear-algebra filter, no mocks).
RUN pip install --no-cache-dir "numpy>=1.26,<3.0"

# ADDITIVE (DEV-WIRE-K R1, Opus 4.8, 2026-06-09): scipy for exact KS two-sample
# (scipy.stats.ks_2samp) in the Posture & Drift detectors; networkx for real graph
# metrics (clustering / centrality / Fiedler lambda2 / DAG integrity) in Topology &
# Health; PyYAML to parse the REAL deploy/uds-package.yaml allow rules for the
# Attack-Surface and Zero-Trust mesh graphs. ALL THREE ARE OPTIONAL — killinchu_posture
# _topology.py ships pure-python/numpy fallbacks (identical Kolmogorov asymptotic KS,
# numpy-based graph metrics, hand-rolled YAML reader) so a rebuild lag never breaks the
# surface. `|| true` keeps the build green if a wheel is unavailable.
RUN pip install --no-cache-dir "scipy>=1.11" "networkx>=3.0" "PyYAML>=6.0" || true

# Copy the pre-built SPA to the static root.
# index.html + assets/* served directly at / and /assets/*; unknown GET -> index.html.
COPY static/ ./static/

# ADDITIVE (cathedral front-door hero): sovereign 3D landing matching the org card.
# Served at / by serve.py (operator one click in at /operator). The hero JS +
# vendored ES-module Three.js r160 (MIT) live under static/ (already copied above).
# NO CDN. Doctrine v11 LOCKED 749/14/163. Trust Gate = Conjecture.
# ---------------------------------------------------------------------------
# CONSOLIDATED ROOT-FILE COPY LAYERS (Docker max-depth fix, Opus 4.8).
# Docker creates one image layer per COPY. The 81 individual root-file ->
# same-name COPYs (incl. 5x redundant serve.py) were collapsed into the
# grouped multi-source COPYs below (dest is the /app WORKDIR root '.').
# IDENTICAL file set ships to IDENTICAL paths — proven by set-equality check.
# This Dockerfile STILL never uses `COPY . .`; every file is explicit.
# Subpath/dir/rename COPYs (static/, web/*, src/*, szl_connectors/*, etc.)
# are left untouched. Signed-off-by: Yachay <yachay@szlholdings.ai>
# ---------------------------------------------------------------------------
COPY cathedral.html knowledge.json operator_shell_v4.py serve.py szl_evidence_research.py szl_readiness.py szl_quantum_bio.py szl_unified_formulas.py szl_cuas_formulas.py killinchu_research_sources.py szl_contracting.py szl_conjecture_factory.py killinchu_backend.py a11oy_hf_assets.py drones_db.json killinchu_protocols.py killinchu_expansion.py killinchu_naval_haps.py szl_dsse.py szl_provenance.py LEGAL_BOUNDARIES.md ./
COPY szl_live_wires.py live_wires.html live_wires_3d.js szl_rosie_companion.py killinchu_szl_pqc_sign.py szl_rekor.py killinchu_osint.py szl_be_hardening.py szl_unay.py szl_khipu_lmdb.py szl_khipu_replicate.py szl_unay_routes.py szl_warhacker_aliases.py killinchu_genius.py killinchu_warhacker_demos.py killinchu_v3.py szl_brain.py szl_rag.py szl_formulas.py szl_understudy.py ./
COPY szl_killinchu_cookbook.py szl_uds_hardening.py killinchu_fusion.py szl_v4_fleet.py szl_ken.py killinchu_frontier_patch.py killinchu_drone_routes.py killinchu_parity.py killinchu_cannonico.py killinchu_elite_console.py _vendor_blobs.py killinchu_fleet_vessels.py killinchu_maritime_risk.py killinchu_maritime_intel.py killinchu_maritime_view.py killinchu_live_feeds.py killinchu_feeds_realdata.py killinchu_asw.py killinchu_anatomy.py killinchu_health_twin.py fleet_vessels_data.json killinchu_beyond.py szl_khipu_consensus.py killinchu_formula_endpoints.py killinchu_edge_formulas.py ./
COPY killinchu_edge_console.py szl_agentic_loop.py szl_anatomy_routes.py szl_formula_wiring.py a11oy_code_engine.py killinchu_ops_control.py szl_llm_registry.py szl_alloy_models.py a11oy_agent_loop.py a11oy_org_rag.py a11oy_mcp_client.py killinchu_mined_ops.py killinchu_resweep_ops.py killinchu_wave910.py killinchu_posture_topology.py szl_connectors_serve.py szl_connector_mcp.py szl_scaling.py szl_allodial.py szl_entanglement.py szl_neuroplasticity.py szl_chain_of_title.py ./

# ADDITIVE (Mosaic SDA elevation, 2026-06-13): SZL's sovereign Mosaic / Domain-
# Superiority organ. killinchu_mosaic.py imports szl_mosaic_core.py (the vendored
# clean-room anomaly/SDA engine). serve.py imports killinchu_mosaic via try/except;
# without these per-file COPYs (this Dockerfile never uses `COPY . .`) the import
# fails and the /api/killinchu/v1/mosaic/* endpoints + the Mosaic COP tab 404.
COPY killinchu_mosaic.py szl_mosaic_core.py ./

# ADDITIVE (live knowledge console — 2026-06-09): the generated, kernel-derived
# knowledge corpus (axioms/theorems/formulas/frameworks), byte-identical to
# a11oy's knowledge.json. serve.py serves it at /knowledge.json so the /elite
# console's loadKnowledge() renders LIVE panels instead of falling back to {}.
# COPYed to BOTH the static root (the SPA catch-all serves /app/static/*) AND
# /app root (the explicit serve.py route reads /app/knowledge.json) — mirrors
# a11oy so the surfaces never drift from the kernel. Honesty v11 preserved.
COPY knowledge.json ./static/knowledge.json

# Copy serve orchestrator + real drone DB + real protocol decoders.
# ADDITIVE (Unified Operator Shell v4, 2026-06-01, Yachay / Perplexity Computer Agent):
# v4 endpoint module + self-contained desktop shell. Per-file COPY (no `COPY . .`).
COPY web/operator.html ./web/operator.html
# OPERATOR WIDGET (2026-06-10): byte-identical to a11oy. Self-hosted in-image
# (0 CDN), served at /vendor/a11oy-operator-widget.js by serve.py. NO codenames.
COPY static-vendor/a11oy-operator-widget.js ./static-vendor/a11oy-operator-widget.js
COPY static-vendor/a11oy-operator-widget.css ./static-vendor/a11oy-operator-widget.css
# Evidence & Research backend (curated + live arXiv/GitHub). serve.py imports this;
# without this per-file COPY the import fails and /api/killinchu/v1/evidence/research 404s.
ARG EVIDENCE_FIX_BUST=1780922329
# Operational Readiness backend (deployed-vs-repo reality, live/cached/unreachable).
# serve.py imports this try/except-guarded; without this per-file COPY the import
# fails and /api/killinchu/v1/readiness 404s (falls through to the SPA shell).
ARG READINESS_FIX_BUST=1
# Research & Sources backend (Task #662, research-sources-patch) — per-tab vetted
# REAL upstream sources (UDS/Zarf/Pepr, supply-chain standards, threat/domain feeds,
# Lean/proof refs, per-subject arXiv) with an honest live reachability probe. serve.py
# imports this try/except-guarded; without this per-file COPY the import fails and
# /api/killinchu/v1/research 404s (falls through to the SPA shell).
ARG RESEARCH_SOURCES_BUST=1
# Contracting Readiness backend (SAM/CAGE + SBIR/STTR eligibility, web-sourced,
# honest verified/confirmed/needs_founder_input/needs_founder_action labels, source
# liveness probes, 0 fabricated org values). serve.py imports this try/except-guarded;
# without this per-file COPY the import fails and /api/killinchu/v1/contracting 404s.
# Real persistent backend (Postgres-first, durable-SQLite fallback). serve.py imports
# this try/except-guarded; without this per-file COPY the import fails and
# /api/killinchu/{live,crawl/run,timeline,alerts/recent,watchlists} 404 to the SPA.
ARG KILLINCHU_BACKEND_BUST=1
# dev3 HF assets instill (Knowledge & Formulas / Evidence) — app-agnostic, server-side fetch, 0 CDN.


# ADDITIVE (Yachay / Live 3D Wires, PURIQ Doctrine v12): COPY the live-wires
# module + host page + scene core so `import szl_live_wires` resolves in-container.
# Without these the register() call in the server silently fails and /live-wires
# falls through to the SPA shell. ADDITIVE ONLY. Sign: Yachay.

# ADDITIVE (Wire I): Rosie-companion module baked into the image. Yachay.
# ADDITIVE (PQC/hybrid signing): bake the signing module so `import
# killinchu_szl_pqc_sign` resolves in-container and register() wires the
# /khipu/sign endpoints. ADDITIVE ONLY. Sign: Yachay.
# ADDITIVE (Sigstore Rekor public cross-verify, Yachay — from PR #13): bake the
# Rekor client so `import szl_rekor` resolves in-container and serve.py wires
# the UDS-facing /api/killinchu/uds/v1/rekor/* endpoints. stdlib-only (reuses the
# existing cryptography install). ADDITIVE ONLY.
# OSINT verticals (amaru/rosie): public-web search/scrape via Tavily, normalize
# + sha256 provenance chain + corpus. serve.py imports this; without this
# per-file COPY the import fails and the amaru/rosie endpoints 404.
ENV PORT=7860
# BE hardening (Greene) — per-file COPY (this Dockerfile uses per-file COPY).

EXPOSE 7860

# ADDITIVE (UNAY + Khipu-LMDB v2, 2026-06-01, Yachay): real durable lmdb persistence
# + optional sqlite-vss vector recall (szl_unay degrades to honest cosine-fallback if
# the extension cannot load in the slim image). Never affects existing routes.
RUN pip install --no-cache-dir "lmdb>=1.4.0" "sqlite-vss>=0.1.2"
# ADDITIVE (Mosaic SDA elevation, 2026-06-13): python-sgp4 (MIT) is the sovereign
# orbital propagator for the space-domain ROADMAP conjunction stub. Guarded with
# `|| true` so a wheel/build hiccup never breaks the image — killinchu_mosaic falls
# back to an honest ROADMAP SKELETON when sgp4 is absent (no conjunction fabricated).
RUN pip install --no-cache-dir "sgp4>=2.20" || true
# ADDITIVE (UNAY + Khipu-LMDB v2, 2026-06-01, Yachay / Perplexity Computer Agent):
# explicit per-file COPY (this Dockerfile does not use `COPY . .`). serve.py imports
# szl_unay_routes and calls .register(app, ns="killinchu") -> /api/killinchu/v2/unay/* +
# /api/killinchu/v2/khipu/lmdb/*. Real durable lmdb + real sqlite-vss honest fallback.
# ADDITIVE (Warhacker v2 genius pass, Yachay 2026-06-01): aliases + killinchu_genius.
# Per-file COPY (no `COPY . .`) — without these the imports fail and routes 404.
# ADDITIVE (Killinchu maritime/drone Warhacker demo suite, 2026-06-06): 7 mode-aware
# demos at /api/killinchu/v1/warhacker/launch/{key}. Per-file COPY (no `COPY . .`).
# ADDITIVE (Killinchu v3 deep C-UAS, Yachay 2026-06-01): killinchu_v3 registers
# /api/killinchu/v3/* (ingest pipelines + Kalman fusion + provenanced threat
# scoring + honest effector catalogue + airspace + boids/ORCA swarm + replay +
# daily brief) and the deep operational console at /globe/v3. Per-file COPY
# (no `COPY . .`) — without it `import killinchu_v3` fails and v3 routes 404.
# ADDITIVE (Understudy-parity, Yachay 2026-06-01): the understudy moat-fabric layer
# + its portable substrate (LLM router / agentic RAG / 23-formula registry). Explicit
# per-file COPY (this Dockerfile never uses `COPY . .`); without these `import
# szl_understudy` (and its substrate imports) fail and every /api/killinchu/v2/*
# understudy route 404s. szl_brain/szl_rag/szl_formulas are VENDORED from the
# platform monorepo (header in each file) until `pip install ./packages/*` lands.
RUN pip install --no-cache-dir "huggingface_hub>=0.23" || true
# ADDITIVE (Defense Runtime Cookbook, 2026-06-01, Yachay / Perplexity Computer Agent):
# the self-contained cookbook module. Explicit per-file COPY (this Dockerfile never uses
# `COPY . .`); without it `import szl_killinchu_cookbook` fails and every /api/killinchu/
# v2/cookbook* + /v2/missions* + /v2/scouts + /v2/uds/* + /v2/legal + /v2/specs/* +
# /v2/pitch route 404s. The vendored data lives under static/cookbook/ (already COPY'd by
# the `COPY static/ ./static/` line above). Recall receipts sign live via szl_dsse.
# ADDITIVE (UDS HARDENING, 2026-06-01, Yachay): real-data STIG/SCAP + Iron Bank +
# Big Bang + Tradewinds endpoints under /api/killinchu/uds/v1/*, backed by the
# committed .compliance/ artifacts (real OpenSCAP oscap output, Dockerfile audit,
# helm lint inventory). Registered BEFORE killinchu_fusion so its synthetic stubs
# defer to this real data. Per-file COPY (no `COPY . .`). Sign: Yachay.
# COPY .compliance/ ./.compliance/ — REPLACED with per-file copies that exclude
# iron_bank_parity.json (CTO P1 REJECT B1 — Charter §24 NO Iron Bank in runtime).
# iron_bank_parity.json stays in repo for reference; not baked into the served layer.
COPY .compliance/big_bang_inventory.json ./.compliance/big_bang_inventory.json
COPY .compliance/tradewinds_listing.json ./.compliance/tradewinds_listing.json
COPY .compliance/sysctl-stig.conf ./.compliance/sysctl-stig.conf
COPY .compliance/SECTION_889_REP.md ./.compliance/SECTION_889_REP.md
COPY .compliance/SLSA_LEVEL.md ./.compliance/SLSA_LEVEL.md
# ADDITIVE (V4 Fleet Panel, 2026-06-02, Dev2 Inti):
# explicit per-file COPY (this Dockerfile does not use COPY . .).
# serve.py registers /api/health + /api/killinchu/v4/fleet + /fleet (szl_v4_fleet).
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
COPY web/v4_fleet_panel.html ./web/v4_fleet_panel.html


# ADDITIVE (SZL Ken Agent Pattern v1, CTO Yachay Convergence Cycle 1, 2026-06-03):
# Explicit per-file COPY of szl_ken.py (this Dockerfile never uses `COPY . .`).
# serve.py tries `import szl_ken` at startup; without this COPY the import fails
# silently and /v1/agent/loop + /v1/mcp/tools return 404 instead of 200.
# ADDITIVE ONLY — zero existing routes touched. Doctrine v11 LOCKED 749/14/163.
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>

# ADDITIVE (Missing modules fix, 2026-06-04, Perplexity Computer Agent):
# killinchu_frontier_patch.py: registers /api/killinchu/v1/{doctrine,health,adsb} at route 0.
# killinchu_drone_routes.py: registers /api/killinchu/drone/{telemetry,intercept,cued-tracks,fleet-state}.
# szl_khipu_consensus.py: Khipu multi-organ consensus (killinchu is aggregator).
# All three are imported via try/except in serve.py — missing files cause silent warn, not crash.
# Per-file COPY (this Dockerfile never uses `COPY . .`).
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# killinchu_cannonico.py: lost-contact autonomous-drone governance loop (Warhacker
# Cannonico bullseye). serve.py imports it via try/except after killinchu_parity;
# without this COPY the /api/killinchu/v1/cannonico/* routes fall through to the SPA.
# killinchu_elite_console.py: a11oy-elite 14-tab operator console. serve.py imports
# it via try/except; per-file COPY (this Dockerfile never uses `COPY . .`).
# ADDITIVE (sovereign/air-gap viz, no-CDN): base64 of the binary vendored assets
# (globe earth-night texture + 20 KaTeX woff2 fonts) shipped as TEXT. The elite
# console imports `_vendor_blobs` and serves them at /vendor/earth-night.jpg and
# /vendor/fonts/*; without this COPY the import fails and those routes 404 (the
# *.js/*.css libs come from `COPY static/ ./static/`). Per-file COPY (no `COPY . .`).
# ADDITIVE (FLEET vessels/drones, GAP-1+GAP-2): per-file COPY of the FLEET (Vessels)
# module + its embedded verbatim platform seed-data. serve.py imports
# killinchu_fleet_vessels and front-inserts its 12 routes under /api/killinchu/v1/fleet/*
# (vessels, forecast-modules, predictive-maintenance, compliance-certificates,
# port-state-deficiencies, ai-briefings, event-logs, fleets, maintenance-logs,
# shipment-records, all, voyage-risk); without these COPYs the import fails and every
# fleet route falls through to the SPA catch-all (404). This Dockerfile never uses
# `COPY . .` — every file is explicit. fleet_vessels_data.json carries all 10 datasets
# embedded verbatim, so the 4 new endpoints need no new COPY line. Cache-bust: full-vessels-2026-06-06
# Live data proxies (Digitraffic FI AIS + adsb.lol military) — per-file COPY.
# Without this `import killinchu_live_feeds` fails and /ais/live + /air/live 404.
# Bundled on-disk snapshots for the live-data layer (cached fallback). If any
# upstream feed (Digitraffic AIS / adsb.lol / celestrak / rekor / kev / osv /
# prometheus) is unreachable, get_feed() serves the in-image snapshot labelled
# 'cached' — NEVER fabricated. KILLINCHU_LIVE_SNAPSHOTS defaults to /app/live_snapshots.
COPY live_snapshots/ ./live_snapshots/
# SZL Agent Body anatomy engine (YUYAY gate + YAWAR bus + organism pipeline) —
# per-file COPY. Without this `import killinchu_anatomy` fails and the organism
# pipeline endpoints 404.
# killinchu_health_twin.py: flagship LIVE 3D vessel/drone HEALTH TWIN backend.
# Computes per-subsystem health (hull/propulsion/comms/sensors/nav/payload) from
# real-ish signals using OUR formulas: split-conformal band (W5-3/W7-4, NOT
# Hoeffding), Λ geometric-mean trust aggregate (Conjecture 1), and the YUYAY
# 13-axis conjunctive gate. Reuses live Digitraffic AIS via killinchu_live_feeds.
# serve.py imports via try/except; without this COPY the /api/killinchu/v1/twin/*
# routes fall through to the SPA catch-all.
# killinchu_beyond.py: Beyond-Cannonico proof console — autonomy-governance
# generalized beyond one drone (autonomy envelope · 3-of-4 swarm quorum · HOTL
# override register). serve.py imports it via try/except; without this COPY the
# /api/killinchu/v1/{autonomy,swarm,hotl}/* routes fall through to the SPA.

# ADDITIVE (Formulas → Ecosystem echo, Opus 4.8, 2026-06-03): per-file COPY of the
# shared formulas package + endpoint shim (this Dockerfile never uses `COPY . .`).
# serve.py imports killinchu_formula_endpoints which imports szl_shared_formulas.* —
# without these COPYs the import fails and /api/killinchu/v1/formula/* fall through.
# Echoes a11oy front-door formulas: Welford + Bloom. thesis_v22.pdf §2 + real Lean.
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
COPY szl_shared_formulas/__init__.py ./szl_shared_formulas/__init__.py
COPY szl_shared_formulas/welford.py ./szl_shared_formulas/welford.py
COPY szl_shared_formulas/bloom_filter.py ./szl_shared_formulas/bloom_filter.py

# ADDITIVE (Killinchu Closeout, Opus 4.8, 2026-06-03): per-file COPY of the
# REAL-EDGE surface — the three extra shared formulas (PAC-Bayes + Kalman +
# Byzantine quorum), the real edge package (src/killinchu/*), the real-edge
# formula endpoint shim, the premium edge console deck, and the no-mock tests.
# This Dockerfile NEVER uses `COPY . .` — every file is copied explicitly.
# serve.py imports killinchu_edge_formulas which imports
# szl_shared_formulas.{pac_bayes,kalman,byzantine_quorum}; without these COPYs
# the import fails and /api/killinchu/v1/edge/* fall through to the SPA shell.
# NO MOCKS — real flight-dynamics sim, real ECDSA-P256 DSSEv1, real Khipu DAG,
# real Kalman (numpy).
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
COPY szl_shared_formulas/pac_bayes.py ./szl_shared_formulas/pac_bayes.py
COPY szl_shared_formulas/kalman.py ./szl_shared_formulas/kalman.py
COPY szl_shared_formulas/byzantine_quorum.py ./szl_shared_formulas/byzantine_quorum.py
COPY src/killinchu/__init__.py ./src/killinchu/__init__.py
COPY src/killinchu/lambda_calc.py ./src/killinchu/lambda_calc.py
COPY src/killinchu/dsse.py ./src/killinchu/dsse.py
COPY src/killinchu/khipu.py ./src/killinchu/khipu.py
COPY src/killinchu/edge.py ./src/killinchu/edge.py
COPY src/killinchu/simulator.py ./src/killinchu/simulator.py
COPY web/console.html ./web/console.html
COPY web/console.js ./web/console.js

# ADDITIVE (Governed Agent Loop, 2026-06-06): the operational RAG -> tool-call ->
# policy/trust gate -> signed-receipt loop + canonical live MCP + consumer UI.
# This Dockerfile NEVER uses `COPY . .` — every file is explicit. Without this
# line `import szl_agentic_loop` fails silently and /mcp/, /ask-and-act 404.
# Receipts are signed with the persistent cosign ECDSA-P256-SHA256 key (szl_dsse).
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# szl_anatomy_routes: backs the canonical formula MCP tools (list_formulas/run_formula/
# formula_proof_status) in szl_agentic_loop; byte-identical with a11oy. Deps: szl_formulas only.

# Formula-wiring module (ADDITIVE 2026-06-06): registers the kernel-verified theorem
# mechanisms as live executable checks + the /api/<ns>/v1/formulas/* endpoints
# (selftest, proof-summary). BYTE-IDENTICAL across a11oy + killinchu (single source of
# truth). This Dockerfile NEVER uses `COPY . .` -- without this line
# `import szl_formula_wiring` fails silently and the formula endpoints 404.
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# a11oy Code engine (PORTED 2026-06-06): governed coder (chat/code/research),
# C20/W7-5 router, W5-3/W7-4 conformal, real sandbox, per-run-GENESIS receipts.
# Imports szl_llm_registry (COPY'd below) for the OPEN-WEIGHT roster.
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>

# ADDITIVE (Operational Control Surfaces, 2026-06-06): makes VESSELS and DRONES
# genuinely operational — select a track -> issue a governed command -> deny-by-
# default policy/kernel gate -> genuinely cosign-signed receipt -> track STATE
# updates. Every control action is wrapped in the governed-run loop (P1-P6) so
# 'operate' = 'governed + receipted'. Self-contained operator UI at /ops + /control.
# This Dockerfile NEVER uses `COPY . .` — every file is explicit. Without this line
# `import killinchu_ops_control` fails silently and /ops + /api/killinchu/v1/ops/* 404.
# Receipts are signed with the persistent cosign ECDSA-P256-SHA256 key (szl_dsse).
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>

# ---------------------------------------------------------------------------
# OPEN-WEIGHT ALLOY MODEL LAYER (model-integration squad, 2026-06-06; PORTED from a11oy)
# Same open-weight alloy forged into a11oy, ported to killinchu. Per-file COPY
# (this Dockerfile NEVER uses `COPY . .`). Without these, `import szl_alloy_models`
# fails silently and /api/killinchu/v1/alloy/* 404.
#   * szl_alloy_models.py : roster + C20/W7-5 router + W5-3/W7-4 conformal +
#     C10-C12 consensus + governed suggest (honest tower-side label; output never faked).
#   * szl_llm_registry.py : the LLM registry the alloy roster UNIFIES into (one roster).
# OPEN-WEIGHT only, NO closed weights, NO keys; weights NOT redistributed.
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
# ADDITIVE (a11oy Code agentic core, 2026-06-10): the GENUINELY-agentic loop + agentic
# RAG + MCP client are SHARED canonical modules forged in a11oy and shipped BYTE-IDENTICAL
# into killinchu for drift-free parity. killinchu does NOT host a11oy_code_orchestrator.py
# (a11oy-specific), so nothing here imports them at boot, but they MUST be present and
# byte-identical with a11oy. All three are stdlib-only at import time (szl_brain/szl_rag/
# httpx/faiss are lazy + guarded). szl_rag.py is already COPY'd above (line ~189). Per-file
# COPY (this Dockerfile never uses `COPY . .`).
# EGRESS FIX (2026-06-10): the org-RAG full build runs INSIDE this HF Space,
# which can reach huggingface.co but NOT api.github.com (Space egress is
# GitHub-blocked). Bundle the REAL highest-value files of the four GitHub-only
# corpus categories (thesis/formulas/doctrine/lean) in-image so a11oy_org_rag.py
# ingests them when GitHub is unreachable. corpus/INDEX.json records each file's
# real origin repo+path+blob_sha+commit_sha; chunks cite bundled:<repo>@<sha>:<path>
# (real files, honest provenance, NOT fabricated). BYTE-IDENTICAL across a11oy &
# killinchu. Per-file/dir COPY (this Dockerfile does not use COPY . .).
COPY corpus/ ./corpus/
# ADDITIVE (MINED ops upgrades, 2026-06-07): four license-vetted operational/efficiency
# surfaces (pattern-mined clean-room WITH NOTICE: al-jshen/compute MIT, gpu-bartender MIT,
# MLRC-deep-thinking MIT, kvpress Apache-2.0). serve.py imports killinchu_mined_ops via
# try/except and register()s POST /api/killinchu/v1/mined/{scicompute,edge-estimator,
# swarm-resilience,telemetry-press} + GET .../index. Per-file COPY (this Dockerfile NEVER
# uses `COPY . .`); without it `import killinchu_mined_ops` fails and every mined route 404s.
# Pure-stdlib, additive; Lambda stays Conjecture 1; no fabricated data.

# ADDITIVE (RE-SWEEP wave-2 ops, 2026-06-07): three license-vetted operational surfaces
# (pattern-mined clean-room WITH NOTICE: anvaka/ngraph.path MIT, rowanwins/visibility-graph
# MIT, ft2023/IRanker-demo MIT, al-jshen/adaptive MIT). serve.py imports killinchu_resweep_ops
# via try/except and register()s POST /api/killinchu/v1/resweep/{route,threat-rank,
# adaptive-sample} + GET .../index. Per-file COPY (this Dockerfile NEVER uses `COPY . .`);
# without it `import killinchu_resweep_ops` fails and every resweep route 404s.
# Pure-stdlib, additive; Lambda stays Conjecture 1; no fabricated data.

# ADDITIVE (Wave9 + Wave10 EXPERIMENTAL theorems, 2026-06-08): six killinchu-targeted
# theorem families PROVEN on lutar-lean main (Wave9 PR #199 merged @ 66735bf; Wave10
# PR #200) as EXPERIMENTAL · CI-green — kernel-verified, NOT locked. serve.py imports
# killinchu_wave910 via try/except and register()s POST /api/killinchu/v1/wave910/
# {stl-robustness,covariance-intersection,gershgorin,mesh-resilience,audit-receipts,
# quorum-consensus} + GET .../index + .../selftest. Per-file COPY (this Dockerfile NEVER
# uses `COPY . .`); without it `import killinchu_wave910` fails and every wave910 route 404s.
# Pure-stdlib, additive; locked-proven stays EXACTLY 8 {F1,F4,F7,F11,F12,F18,F19,F22}; Λ = Conjecture 1.

# ADDITIVE (DEV-WIRE-K R1, Opus 4.8, 2026-06-09): Posture & Drift + Topology &
# Health + Attack-Surface + Zero-Trust surfaces. serve.py imports
# killinchu_posture_topology via try/except and front-inserts GET
# /api/killinchu/v1/{posture/drift,topology/health,attack-surface/graph,
# zerotrust/mesh}. This Dockerfile NEVER uses `COPY . .` — every file is explicit;
# WITHOUT this line `import killinchu_posture_topology` fails (ModuleNotFoundError)
# and all four routes 404. Real PSI+KS(scipy.stats.ks_2samp)+vendored-ADWIN drift
# on live ADS-B; real graph metrics (Fiedler λ2 etc.) via networkx/numpy fallback;
# Attack-Surface + Zero-Trust mesh from REAL deploy/uds-package.yaml. NO fabricated
# data; honest empty states; organ role names (Operator/Provenance Anchor/Policy);
# locked-proven stays EXACTLY 8 {F1,F4,F7,F11,F12,F18,F19,F22}; Λ = Conjecture 1.
# ADDITIVE (DEV-WIRE-K R1): the REAL UDS Package CR consumed by the Attack-Surface
# and Zero-Trust mesh endpoints (killinchu_posture_topology._load_uds_package reads
# /app/deploy/uds-package.yaml). This Dockerfile NEVER uses `COPY . .`; WITHOUT this
# line the file is absent in-image and both tabs honestly render the empty state
# instead of the real allow/expose graph. Real allow rules only — no invented CVEs.
COPY deploy/uds-package.yaml ./deploy/uds-package.yaml

# ---------------------------------------------------------------------------
# ADDITIVE (SZL Enterprise Connector Framework, 2026-06-10, founder directive):
# per-file COPY of the connector framework (this Dockerfile NEVER uses `COPY . .`).
# serve.py imports szl_connectors_serve (try/except); without these COPYs the import
# fails and /api/killinchu/connectors + /integrations 404. Shared byte-identical w/ a11oy.
# Cache-bust: szl-connectors-2026-06-10
COPY szl_connectors/__init__.py ./szl_connectors/__init__.py
COPY szl_connectors/base.py ./szl_connectors/base.py
COPY szl_connectors/bindings.py ./szl_connectors/bindings.py
COPY szl_connectors/comms/__init__.py ./szl_connectors/comms/__init__.py
COPY szl_connectors/comms/comms_connectors.py ./szl_connectors/comms/comms_connectors.py
COPY szl_connectors/crm/__init__.py ./szl_connectors/crm/__init__.py
COPY szl_connectors/crm/crm_connectors.py ./szl_connectors/crm/crm_connectors.py
COPY szl_connectors/data_sources/__init__.py ./szl_connectors/data_sources/__init__.py
COPY szl_connectors/data_sources/geo.py ./szl_connectors/data_sources/geo.py
COPY szl_connectors/data_sources/macro.py ./szl_connectors/data_sources/macro.py
COPY szl_connectors/data_sources/maritime_air.py ./szl_connectors/data_sources/maritime_air.py
COPY szl_connectors/data_sources/research.py ./szl_connectors/data_sources/research.py
COPY szl_connectors/data_sources/security.py ./szl_connectors/data_sources/security.py
COPY szl_connectors/erp/__init__.py ./szl_connectors/erp/__init__.py
COPY szl_connectors/erp/erpnext.py ./szl_connectors/erp/erpnext.py
COPY szl_connectors/erp/odoo.py ./szl_connectors/erp/odoo.py
COPY szl_connectors/erp/others.py ./szl_connectors/erp/others.py
COPY szl_connectors/erp/sap_s4.py ./szl_connectors/erp/sap_s4.py
COPY szl_connectors/governance.py ./szl_connectors/governance.py
COPY szl_connectors/identity/__init__.py ./szl_connectors/identity/__init__.py
COPY szl_connectors/identity/identity_connectors.py ./szl_connectors/identity/identity_connectors.py
COPY szl_connectors/itsm/__init__.py ./szl_connectors/itsm/__init__.py
COPY szl_connectors/itsm/itsm_connectors.py ./szl_connectors/itsm/itsm_connectors.py
COPY szl_connectors/oauth.py ./szl_connectors/oauth.py
COPY szl_connectors/observability/__init__.py ./szl_connectors/observability/__init__.py
COPY szl_connectors/observability/observability_connectors.py ./szl_connectors/observability/observability_connectors.py
COPY szl_connectors/ready.py ./szl_connectors/ready.py
COPY szl_connectors/registry.py ./szl_connectors/registry.py
COPY szl_connectors/storage/__init__.py ./szl_connectors/storage/__init__.py
COPY szl_connectors/storage/storage_connectors.py ./szl_connectors/storage/storage_connectors.py
COPY szl_connectors/warehouse/__init__.py ./szl_connectors/warehouse/__init__.py
COPY szl_connectors/warehouse/warehouse_connectors.py ./szl_connectors/warehouse/warehouse_connectors.py
COPY pages/integrations.html ./pages/integrations.html

# ADDITIVE (Task: HF Dataset Bucket Foundation): the ONE shared Hugging Face
# 'bucket' client both flagships reuse. Durable, append-only, idempotent
# (content-addressed dedup), offline-tolerant local queue + flush, rate-aware
# batched Hub commits. Pure stdlib + huggingface_hub (lazy). BYTE-IDENTICAL
# across a11oy + killinchu (shared-file-drift enforces it via this COPY list).
# This Dockerfile never uses `COPY . .` — without this line `import
# szl_hf_bucket` fails. Imported lazily by callers; no boot-time side effects.
COPY szl_hf_bucket.py szl_metrics_prom.py ./

# ADDITIVE (Task MW5: 3D HOLOGRAPHIC MARITIME GLOBE): self-contained WebGL2
# holographic globe view for the /elite surface (+ /jackin/globe alias). Plots
# REAL vessel + aircraft tracks at true lat/lon with motion plus honestly-
# labelled dark-halo / spoof-arc / Λ-risk / forecast-cone intel layers
# (INFERENCE/FORECAST today; auto-upgrades to backend LIVE when the W2/W3
# maritime endpoints are reachable + advertised). 0 runtime CDN — the entire
# engine + landmask + styles are vendored inline as base64-embedded HTML. This
# Dockerfile never uses `COPY . .`; without this line `import
# killinchu_maritime_globe` in serve.py fails (registration is guarded, so the
# app still boots, but the globe route would be absent). Imported once at boot;
# no network side effects.
COPY killinchu_maritime_globe.py ./

CMD ["python", "serve.py"]


# Build cache-bust 2026-06-13T20:55Z (MW5 maritime globe): COPY killinchu_maritime_globe.py
# into /app so serve.py can import+register the holographic globe at /elite/globe.

# Build cache-bust 2026-06-06T09:10Z (model-integration squad): PORTED OPEN-WEIGHT ALLOY
# MODEL LAYER from a11oy -> COPY szl_alloy_models.py + szl_llm_registry.py; serve.py
# registers alloy under /api/killinchu/v1/alloy/* (C20/W7-5 router, W5-3/W7-4 conformal,
# C10-C12 consensus; DeepSeek-Coder-V2 CODE_PRIMARY; honest tower-side; never faked).

# Build cache-bust 2026-06-07T05:00Z (MINED ops squad): COPY killinchu_mined_ops.py
# into /app so serve.py can import+register the 4 mined operational/efficiency surfaces.


