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

# ADDITIVE (Yachay / Provenance Hardening): cryptography for DSSE+Cosign Khipu signing.
RUN pip install --no-cache-dir "cryptography>=42.0"
# ADDITIVE (Yachay / PQC): pure-Python ML-DSA-65 (NIST FIPS 204) backend for
# /khipu/sign?mode={pqc,hybrid}. liboqs (oqs-python) is preferred in prod but is
# a C lib not always installable; dilithium-py is the pure-Python fallback so
# hybrid signing works in the Space. ECDSA stays the default regardless.
RUN pip install --no-cache-dir "dilithium-py>=1.0.0"

# Copy the pre-built SPA to the static root.
# index.html + assets/* served directly at / and /assets/*; unknown GET -> index.html.
COPY static/ ./static/

# Copy serve orchestrator + real drone DB + real protocol decoders.
# ADDITIVE (Unified Operator Shell v4, 2026-06-01, Yachay / Perplexity Computer Agent):
# v4 endpoint module + self-contained desktop shell. Per-file COPY (no `COPY . .`).
COPY operator_shell_v4.py ./operator_shell_v4.py
COPY web/operator.html ./web/operator.html
COPY serve.py ./serve.py
COPY drones_db.json ./drones_db.json
COPY killinchu_protocols.py ./killinchu_protocols.py
COPY killinchu_expansion.py ./killinchu_expansion.py
COPY killinchu_naval_haps.py ./killinchu_naval_haps.py
COPY szl_dsse.py ./szl_dsse.py
COPY szl_provenance.py ./szl_provenance.py
COPY LEGAL_BOUNDARIES.md ./LEGAL_BOUNDARIES.md


# ADDITIVE (Yachay / Live 3D Wires, PURIQ Doctrine v12): COPY the live-wires
# module + host page + scene core so `import szl_live_wires` resolves in-container.
# Without these the register() call in the server silently fails and /live-wires
# falls through to the SPA shell. ADDITIVE ONLY. Sign: Yachay.
COPY szl_live_wires.py ./szl_live_wires.py
COPY live_wires.html ./live_wires.html
COPY live_wires_3d.js ./live_wires_3d.js

# ADDITIVE (Wire I): Rosie-companion module baked into the image. Yachay.
COPY szl_rosie_companion.py ./szl_rosie_companion.py
# ADDITIVE (PQC/hybrid signing): bake the signing module so `import
# killinchu_szl_pqc_sign` resolves in-container and register() wires the
# /khipu/sign endpoints. ADDITIVE ONLY. Sign: Yachay.
COPY killinchu_szl_pqc_sign.py ./killinchu_szl_pqc_sign.py
COPY serve.py ./serve.py
ENV PORT=7860
# BE hardening (Greene) — per-file COPY (this Dockerfile uses per-file COPY).
COPY szl_be_hardening.py ./szl_be_hardening.py

EXPOSE 7860

# ADDITIVE (UNAY + Khipu-LMDB v2, 2026-06-01, Yachay): real durable lmdb persistence
# + optional sqlite-vss vector recall (szl_unay degrades to honest cosine-fallback if
# the extension cannot load in the slim image). Never affects existing routes.
RUN pip install --no-cache-dir "lmdb>=1.4.0" "sqlite-vss>=0.1.2"
# ADDITIVE (UNAY + Khipu-LMDB v2, 2026-06-01, Yachay / Perplexity Computer Agent):
# explicit per-file COPY (this Dockerfile does not use `COPY . .`). serve.py imports
# szl_unay_routes and calls .register(app, ns="killinchu") -> /api/killinchu/v2/unay/* +
# /api/killinchu/v2/khipu/lmdb/*. Real durable lmdb + real sqlite-vss honest fallback.
COPY szl_unay.py ./szl_unay.py
COPY szl_khipu_lmdb.py ./szl_khipu_lmdb.py
COPY szl_khipu_replicate.py ./szl_khipu_replicate.py
COPY szl_unay_routes.py ./szl_unay_routes.py
# ADDITIVE (Warhacker v2 genius pass, Yachay 2026-06-01): aliases + killinchu_genius.
# Per-file COPY (no `COPY . .`) — without these the imports fail and routes 404.
COPY szl_warhacker_aliases.py ./szl_warhacker_aliases.py
COPY killinchu_genius.py ./killinchu_genius.py
# ADDITIVE (Killinchu v3 deep C-UAS, Yachay 2026-06-01): killinchu_v3 registers
# /api/killinchu/v3/* (ingest pipelines + Kalman fusion + provenanced threat
# scoring + honest effector catalogue + airspace + boids/ORCA swarm + replay +
# daily brief) and the deep operational console at /globe/v3. Per-file COPY
# (no `COPY . .`) — without it `import killinchu_v3` fails and v3 routes 404.
COPY killinchu_v3.py ./killinchu_v3.py
# ADDITIVE (Understudy-parity, Yachay 2026-06-01): the understudy moat-fabric layer
# + its portable substrate (LLM router / agentic RAG / 23-formula registry). Explicit
# per-file COPY (this Dockerfile never uses `COPY . .`); without these `import
# szl_understudy` (and its substrate imports) fail and every /api/killinchu/v2/*
# understudy route 404s. szl_brain/szl_rag/szl_formulas are VENDORED from the
# platform monorepo (header in each file) until `pip install ./packages/*` lands.
RUN pip install --no-cache-dir "huggingface_hub>=0.23" || true
COPY szl_brain.py ./szl_brain.py
COPY szl_rag.py ./szl_rag.py
COPY szl_formulas.py ./szl_formulas.py
COPY szl_understudy.py ./szl_understudy.py
# ADDITIVE (Defense Runtime Cookbook, 2026-06-01, Yachay / Perplexity Computer Agent):
# the self-contained cookbook module. Explicit per-file COPY (this Dockerfile never uses
# `COPY . .`); without it `import szl_killinchu_cookbook` fails and every /api/killinchu/
# v2/cookbook* + /v2/missions* + /v2/scouts + /v2/uds/* + /v2/legal + /v2/specs/* +
# /v2/pitch route 404s. The vendored data lives under static/cookbook/ (already COPY'd by
# the `COPY static/ ./static/` line above). Recall receipts sign live via szl_dsse.
COPY szl_killinchu_cookbook.py ./szl_killinchu_cookbook.py
# ADDITIVE (UDS HARDENING, 2026-06-01, Yachay): real-data STIG/SCAP + Iron Bank +
# Big Bang + Tradewinds endpoints under /api/killinchu/uds/v1/*, backed by the
# committed .compliance/ artifacts (real OpenSCAP oscap output, Dockerfile audit,
# helm lint inventory). Registered BEFORE killinchu_fusion so its synthetic stubs
# defer to this real data. Per-file COPY (no `COPY . .`). Sign: Yachay.
COPY szl_uds_hardening.py ./szl_uds_hardening.py
# COPY .compliance/ ./.compliance/ — REPLACED with per-file copies that exclude
# iron_bank_parity.json (CTO P1 REJECT B1 — Charter §24 NO Iron Bank in runtime).
# iron_bank_parity.json stays in repo for reference; not baked into the served layer.
COPY .compliance/big_bang_inventory.json ./.compliance/big_bang_inventory.json
COPY .compliance/tradewinds_listing.json ./.compliance/tradewinds_listing.json
COPY .compliance/sysctl-stig.conf ./.compliance/sysctl-stig.conf
COPY .compliance/SECTION_889_REP.md ./.compliance/SECTION_889_REP.md
COPY .compliance/SLSA_LEVEL.md ./.compliance/SLSA_LEVEL.md
COPY killinchu_fusion.py ./killinchu_fusion.py
COPY serve.py ./serve.py
# ADDITIVE (V4 Fleet Panel, 2026-06-02, Dev2 Inti):
# explicit per-file COPY (this Dockerfile does not use COPY . .).
# serve.py registers /api/health + /api/killinchu/v4/fleet + /fleet (szl_v4_fleet).
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
COPY szl_v4_fleet.py ./szl_v4_fleet.py
COPY web/v4_fleet_panel.html ./web/v4_fleet_panel.html


# ADDITIVE (SZL Ken Agent Pattern v1, CTO Yachay Convergence Cycle 1, 2026-06-03):
# Explicit per-file COPY of szl_ken.py (this Dockerfile never uses `COPY . .`).
# serve.py tries `import szl_ken` at startup; without this COPY the import fails
# silently and /v1/agent/loop + /v1/mcp/tools return 404 instead of 200.
# ADDITIVE ONLY — zero existing routes touched. Doctrine v11 LOCKED 749/14/163.
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
COPY szl_ken.py ./szl_ken.py

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
COPY killinchu_formula_endpoints.py ./killinchu_formula_endpoints.py

CMD ["python", "serve.py"]

