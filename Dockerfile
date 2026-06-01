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
# ADDITIVE (Yachay / Provenance Hardening): cryptography for DSSE+Cosign Khipu signing.
RUN pip install --no-cache-dir "cryptography>=42.0"

# Copy the pre-built SPA to the static root.
# index.html + assets/* served directly at / and /assets/*; unknown GET -> index.html.
COPY static/ ./static/

# Copy serve orchestrator + real drone DB + real protocol decoders.
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
COPY serve.py ./serve.py
ENV PORT=7860
EXPOSE 7860

CMD ["python", "serve.py"]