# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
killinchu_ais_aug2024.py — NOAA/MarineCadastre AIS (Aug 2024, coastal US) as a
SELECTABLE governed source on the elite track board.

This is the WarHacker "Maritime AIS Data August 2024 (coastal US)" dataset, wired
genuinely (real NOAA schema, real rows) ALONGSIDE the existing live AIS feed. The
LIVE feed stays the DEFAULT; this is selectable via ?source=noaa_ais_aug2024.

ADDITIVE module. serve.py imports this and calls register(app, ns) BEFORE the SPA
catch-all. It does NOT touch any existing route. It REUSES (never re-implements):
  • the NOAA connector  szl_connectors.data_sources.ais_noaa_aug2024 (real schema,
    real rows, honest SAMPLE labelling),
  • the Λ dark-fleet risk scorer killinchu_maritime_risk.score_vessel (governed,
    geometric-mean weakest-link), and its REAL DSSE receipt signer (_sign_judgment).

ENDPOINTS (base = /api/{ns}/v1/ais)
  GET  /ais/sources            -> selectable source manifest (live = default)
  GET  /ais/aug2024/tracks     -> normalized REAL NOAA Aug-2024 tracks (bounded sample)
  GET  /ais/aug2024/risk-board -> each NOAA vessel scored by Λ risk (governed/receipted)
  GET  /ais/tracks             -> SELECTOR: ?source=live|noaa_ais_aug2024 (live default)

HONESTY DOCTRINE (absolute, doctrine v11):
  The Aug-2024 dataset shipped here is a BOUNDED SAMPLE of REAL rows from the real
  AIS_2024_08_01.csv (US NE coastal bbox, first hour) — NOT the full multi-GB month.
  Labelled "(sample)" everywhere. The risk score is ADVISORY, governed by Λ
  (Conjecture 1), signed with a real DSSE receipt when the cosign secret is present
  (else an honest UNSIGNED envelope — never a fabricated signature). No fabricated
  vessel rows, counts, joules, receipts, or hashes — ever.

Source provenance: NOAA / Marine Cadastre AIS (marinecadastre.gov / coast.noaa.gov),
AIS_2024_08_01.zip, coastal United States, August 2024.
"""
from __future__ import annotations

import os
import sys
from typing import Any

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore

# Reuse the real NOAA connector (real schema + real rows + honest labelling).
try:
    from szl_connectors.data_sources.ais_noaa_aug2024 import (
        NoaaAisAug2024Connector, SAMPLE_BBOX, SAMPLE_WINDOW,
        PROVENANCE_FULL, PROVENANCE_SAMPLE, NOAA_AIS_AUG01_URL, NOAA_SCHEMA,
    )
except Exception:  # pragma: no cover
    NoaaAisAug2024Connector = None  # type: ignore

# Reuse the governed Λ risk scorer + its REAL DSSE receipt signer.
try:
    import killinchu_maritime_risk as _risk
except Exception:  # pragma: no cover
    _risk = None  # type: ignore

NS_DEFAULT = "killinchu"

# The live AIS feed is the DEFAULT source; this dataset is selectable alongside it.
LIVE_SOURCE_ID = "live"
LIVE_ENDPOINT = "/api/{ns}/v1/live/ais"
NOAA_SOURCE_ID = "noaa_ais_aug2024"


def _connector() -> Any | None:
    if NoaaAisAug2024Connector is None:
        return None
    return NoaaAisAug2024Connector()


def load_aug2024_tracks(*, limit: int | None = None,
                        fetch: bool = False) -> dict[str, Any]:
    """Return normalized REAL NOAA Aug-2024 tracks (bounded sample) + honest meta."""
    c = _connector()
    if c is None:
        return {"error": "NOAA AIS connector unavailable", "vessels": [],
                "total": 0, "data_kind": "unavailable"}
    q: dict[str, Any] = {}
    if limit is not None:
        q["limit"] = limit
    if fetch:
        q["fetch"] = True
    rec = c.read(q)
    return {
        "source_id": NOAA_SOURCE_ID,
        "source": rec.source,
        "provenance": PROVENANCE_FULL,
        "honest_label": PROVENANCE_SAMPLE,
        "is_sample": rec.state.value == "sample",
        "live": rec.live,
        "state": rec.state.value,
        "bbox": SAMPLE_BBOX,
        "window": SAMPLE_WINDOW,
        "schema": list(NOAA_SCHEMA),
        "note": rec.note,
        "fetched_at": rec.fetched_at,
        "total": len(rec.records),
        "vessels": rec.records,
        "dataset_url": NOAA_AIS_AUG01_URL,
    }


def risk_board(*, limit: int | None = 60, sign: bool = False,
               fetch: bool = False) -> dict[str, Any]:
    """Score each REAL NOAA Aug-2024 vessel through the governed Λ risk scorer.

    Reuses killinchu_maritime_risk.score_vessel (geometric-mean weakest-link) and
    its real DSSE receipt signer — same governance path as the live feed's board.
    """
    data = load_aug2024_tracks(limit=limit, fetch=fetch)
    vessels = data.get("vessels", [])
    if _risk is None:
        return {**data, "error": "maritime risk scorer unavailable", "board": []}
    board: list[dict[str, Any]] = []
    for v in vessels:
        verdict = _risk.score_vessel(v)
        row = {
            "mmsi": v.get("mmsi"), "name": v.get("name"), "imo": v.get("imo"),
            "vesselType": v.get("vesselType"), "status": v.get("status"),
            "lat": v.get("currentLat"), "lon": v.get("currentLon"),
            "sog": v.get("currentSpeed"), "cog": v.get("cog"),
            "risk_score": verdict["risk_score"],
            "lambda_trust": verdict["lambda_trust"],
            "traffic_light": verdict["traffic_light"]["light"],
            "weakest_axis": verdict["formula_trace"]["weakest_axis"],
            "veto": verdict["formula_trace"]["zero_absorption_veto"],
            "baseDateTime": v.get("baseDateTime"),
        }
        if sign:
            row["receipt"] = _risk._sign_judgment("maritime.risk", verdict)
        board.append(row)
    board.sort(key=lambda r: (r["risk_score"] or 0.0), reverse=True)
    return {
        "schema": "szl.killinchu.ais.aug2024.risk.board/v1",
        "source_id": NOAA_SOURCE_ID,
        "source": data.get("source"),
        "honest_label": PROVENANCE_SAMPLE,
        "is_sample": data.get("is_sample"),
        "data_kind": "noaa_ais_aug2024_sample",
        "bbox": SAMPLE_BBOX, "window": SAMPLE_WINDOW,
        "count": len(board), "board": board,
        "label": ("ADVISORY dark-fleet risk triage over REAL NOAA Aug-2024 coastal-US "
                  "AIS (sample), governed by Λ (Conjecture 1). NOT a legal determination."),
        "signed": bool(sign),
        "doctrine": _risk.DOCTRINE if _risk is not None else None,
    }


def sources_manifest(ns: str = NS_DEFAULT) -> dict[str, Any]:
    """Honest manifest of selectable AIS sources. LIVE is the default."""
    return {
        "schema": "szl.killinchu.ais.sources/v1",
        "default": LIVE_SOURCE_ID,
        "sources": [
            {
                "id": LIVE_SOURCE_ID,
                "label": "Live AIS (Digitraffic) — DEFAULT",
                "endpoint": LIVE_ENDPOINT.format(ns=ns),
                "kind": "live-feed",
                "live": True,
                "is_sample": False,
                "note": "Live vessel positions; the default track-board source.",
            },
            {
                "id": NOAA_SOURCE_ID,
                "label": "NOAA/MarineCadastre AIS — Aug 2024 coastal US (WarHacker dataset)",
                "endpoint": f"/api/{ns}/v1/ais/aug2024/tracks",
                "risk_endpoint": f"/api/{ns}/v1/ais/aug2024/risk-board",
                "kind": "historical-dataset",
                "live": False,
                "is_sample": True,
                "provenance": PROVENANCE_FULL,
                "honest_label": PROVENANCE_SAMPLE,
                "dataset_url": NOAA_AIS_AUG01_URL,
                "note": ("Selectable alongside the live feed. Bounded SAMPLE of REAL "
                         "rows from AIS_2024_08_01.csv — NOT the full month."),
            },
        ],
        "selector": {
            "endpoint": f"/api/{ns}/v1/ais/tracks",
            "param": "source",
            "values": [LIVE_SOURCE_ID, NOAA_SOURCE_ID],
            "default": LIVE_SOURCE_ID,
        },
        "honesty": ("Live feed is the default; the Aug-2024 dataset is a selectable, "
                    "honestly-labelled SAMPLE of real NOAA AIS. No fabricated rows."),
    }


# ---------------------------------------------------------------------------
# Route registration (ADDITIVE).
# ---------------------------------------------------------------------------
def register(app, ns: str = NS_DEFAULT) -> dict[str, Any]:
    if APIRouter is None or app is None:
        return {"module": "killinchu_ais_aug2024", "registered_count": 0,
                "error": "fastapi missing"}
    router = APIRouter()
    base = f"/api/{ns}/v1/ais"
    registered: list[str] = []

    @router.get(base + "/sources", include_in_schema=False)
    async def _sources() -> JSONResponse:
        return JSONResponse(sources_manifest(ns))

    @router.get(base + "/aug2024/tracks", include_in_schema=False)
    async def _aug_tracks(limit: int = 200, fetch: bool = False) -> JSONResponse:
        return JSONResponse(load_aug2024_tracks(limit=max(1, min(2000, int(limit))),
                                                fetch=bool(fetch)))

    @router.get(base + "/aug2024/risk-board", include_in_schema=False)
    async def _aug_risk(limit: int = 60, sign: bool = False,
                        fetch: bool = False) -> JSONResponse:
        return JSONResponse(risk_board(limit=max(1, min(500, int(limit))),
                                       sign=bool(sign), fetch=bool(fetch)))

    @router.get(base + "/tracks", include_in_schema=False)
    async def _selector(source: str = LIVE_SOURCE_ID, limit: int = 200) -> JSONResponse:
        # Live stays the default; only the explicit NOAA selection diverts here.
        if source == NOAA_SOURCE_ID:
            return JSONResponse(load_aug2024_tracks(
                limit=max(1, min(2000, int(limit)))))
        # Default → point caller at the canonical live feed (do NOT shadow it).
        return JSONResponse({
            "source_id": LIVE_SOURCE_ID,
            "redirect": LIVE_ENDPOINT.format(ns=ns),
            "note": ("Live AIS is the default source — fetch it at the live endpoint. "
                     "Pass ?source=noaa_ais_aug2024 for the Aug-2024 dataset."),
            "default": True,
        })

    registered.extend([
        f"GET {base}/sources",
        f"GET {base}/aug2024/tracks",
        f"GET {base}/aug2024/risk-board",
        f"GET {base}/tracks",
    ])
    app.include_router(router)
    print(f"[killinchu] /ais Aug-2024 governed source registered: "
          f"{len(registered)} routes", file=sys.stderr)
    return {"module": "killinchu_ais_aug2024", "registered_count": len(registered),
            "routes": registered}


__all__ = ["register", "load_aug2024_tracks", "risk_board", "sources_manifest",
           "NOAA_SOURCE_ID", "LIVE_SOURCE_ID"]
