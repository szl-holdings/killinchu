#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""killinchu_edge_console.py — premium live edge command deck (ADDITIVE, static).

Serves the premium Counter-UAS command deck. The live verdict surface
(/api/killinchu/v1/edge/3d + /stream/verdicts) is provided by the REAL EDGE ORGAN
block in serve.py over the same src/killinchu package + flight simulator; this
module only mounts the deck assets so they resolve LOCALLY (not via the SPA
catch-all):

  GET  /console        premium edge deck (web/console.html)
  GET  /console.js     deck logic (web/console.js)

HONESTY (HONESTY OVER CHECKLIST):
  Every verdict the deck renders is a REAL PAC-Bayes certified-floor Λ over a REAL
  ECDSA-P256 DSSEv1 signature, chained into a REAL hash-chained Khipu DAG, computed
  live over a SIMULATED Andean drone flight (simulated=true — real flight-dynamics,
  RF path-loss + no-fly polygon, NOT a connected drone). NO MOCKS.

Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem).
SLSA L1 honest (killinchu never claims L2 unless independently verified).
Signed-off-by: Yachay <yachay@szlholdings.ai>
Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
from __future__ import annotations

import sys
from pathlib import Path


def register(app, ns: str = "killinchu") -> str:
    """Mount the premium console deck assets (additive, static)."""
    from fastapi.responses import FileResponse, JSONResponse

    web_dir = Path(__file__).resolve().parent / "web"
    if not (web_dir / "console.html").is_file():
        web_dir = Path("/app/web")

    @app.get("/console")
    @app.get("/console.html")
    @app.get(f"/{ns}/console")
    async def _console():
        p = web_dir / "console.html"
        if p.is_file():
            return FileResponse(p, media_type="text/html")
        return JSONResponse({"error": "console.html missing"}, status_code=404)

    @app.get("/console.js")
    async def _console_js():
        p = web_dir / "console.js"
        if p.is_file():
            return FileResponse(p, media_type="application/javascript")
        return JSONResponse({"error": "console.js missing"}, status_code=404)

    return f"premium-deck-wired:{ns} (/console + /console.js)"


__all__ = ["register"]

# Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem)
# SLSA L1 honest (killinchu never claims L2 unless independently verified).
