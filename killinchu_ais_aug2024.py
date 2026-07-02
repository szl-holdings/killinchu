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
# If the connector module is not present in this deployment, the source is NOT
# wired here — we degrade HONESTLY (label it "unavailable"), never fabricate the
# provenance/schema. The except block defines safe placeholders so the static
# manifest can still answer 200 with an honest "not wired" label instead of 500.
NOAA_CONNECTOR_AVAILABLE = True
try:
    from szl_connectors.data_sources.ais_noaa_aug2024 import (
        NoaaAisAug2024Connector, SAMPLE_BBOX, SAMPLE_WINDOW,
        PROVENANCE_FULL, PROVENANCE_SAMPLE, NOAA_AIS_AUG01_URL, NOAA_SCHEMA,
    )
except Exception:  # pragma: no cover
    NOAA_CONNECTOR_AVAILABLE = False
    NoaaAisAug2024Connector = None  # type: ignore
    # Honest placeholders (NOT fabricated data): used only to label the source
    # as not-wired in the manifest; no vessel rows/counts are ever invented.
    SAMPLE_BBOX = None  # type: ignore
    SAMPLE_WINDOW = None  # type: ignore
    PROVENANCE_FULL = "NOAA/MarineCadastre AIS, Aug 2024, coastal US"  # type: ignore
    PROVENANCE_SAMPLE = (  # type: ignore
        "NOAA/MarineCadastre AIS (Aug 2024 coastal-US) connector not wired in "
        "this deployment"
    )
    NOAA_AIS_AUG01_URL = (  # type: ignore
        "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/AIS_2024_08_01.zip"
    )
    NOAA_SCHEMA = ()  # type: ignore

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
    """Honest manifest of selectable AIS sources. LIVE is the default.

    Each source carries an explicit honest STATUS label:
      LIVE         — a live feed wired and selectable now,
      SAMPLE       — a bounded sample of REAL rows, wired and selectable now,
      UNAVAILABLE  — connector NOT wired in this deployment (no fabrication).
    This endpoint must NEVER 500: if the NOAA connector module is absent we still
    return 200 and label that source honestly as UNAVAILABLE / not-wired.
    """
    noaa_wired = bool(NOAA_CONNECTOR_AVAILABLE)
    noaa_status = "SAMPLE" if noaa_wired else "UNAVAILABLE"
    noaa_source: dict[str, Any] = {
        "id": NOAA_SOURCE_ID,
        "label": "NOAA/MarineCadastre AIS — Aug 2024 coastal US (WarHacker dataset)",
        "status": noaa_status,
        "wired": noaa_wired,
        "available": noaa_wired,
        "endpoint": f"/api/{ns}/v1/ais/aug2024/tracks",
        "risk_endpoint": f"/api/{ns}/v1/ais/aug2024/risk-board",
        "kind": "historical-dataset",
        "live": False,
        "is_sample": noaa_wired,
        "provenance": PROVENANCE_FULL,
        "honest_label": PROVENANCE_SAMPLE,
        "dataset_url": NOAA_AIS_AUG01_URL,
        "note": (
            ("Selectable alongside the live feed. Bounded SAMPLE of REAL rows "
             "from AIS_2024_08_01.csv — NOT the full month.")
            if noaa_wired else
            ("NOAA Aug-2024 connector module is NOT deployed in this Space, so "
             "this source is not wired here. No sample rows are served and none "
             "are fabricated; select the LIVE source instead.")
        ),
    }
    sources = [
        {
            "id": LIVE_SOURCE_ID,
            "label": "Live AIS (Digitraffic) — DEFAULT",
            "status": "LIVE",
            "wired": True,
            "available": True,
            "endpoint": LIVE_ENDPOINT.format(ns=ns),
            "kind": "live-feed",
            "live": True,
            "is_sample": False,
            "note": "Live vessel positions; the default track-board source.",
        },
        noaa_source,
    ]
    wired_count = sum(1 for s in sources if s.get("wired"))
    return {
        "schema": "szl.killinchu.ais.sources/v1",
        "default": LIVE_SOURCE_ID,
        "sources_total": len(sources),
        "sources_wired": wired_count,
        "wired_summary": f"{wired_count}/{len(sources)} wired",
        "sources": sources,
        "selector": {
            "endpoint": f"/api/{ns}/v1/ais/tracks",
            "param": "source",
            "values": [LIVE_SOURCE_ID, NOAA_SOURCE_ID],
            "default": LIVE_SOURCE_ID,
        },
        "honesty": (
            "Live feed is the default and always wired. The Aug-2024 dataset is a "
            "selectable, honestly-labelled SAMPLE of real NOAA AIS when its "
            "connector is deployed; if that module is absent it is labelled "
            "UNAVAILABLE (not wired) rather than fabricated."
        ),
        "doctrine": "v11",
    }


# ---------------------------------------------------------------------------
# Maritime OVERLAY GeoJSON endpoints (ADDITIVE — T004 overlay contract).
# GET /api/{ns}/v1/overlays/pirate  and  /api/{ns}/v1/overlays/wpi return a
# valid GeoJSON FeatureCollection (RFC 7946) built from the REAL szl_connectors
# maritime overlay datasets (pirate_attacks / world_port_index). These reuse the
# same governed connectors as killinchu_maritime_risk (never re-implemented).
# HONESTY: each feature carries the connector's live/sample state + provenance.
# SAMPLE rows are on the REAL schema at REAL coordinates and are NEVER labelled
# LIVE; if a connector is not wired we return an EMPTY FeatureCollection labelled
# UNAVAILABLE — no fabricated features, ever.
# ---------------------------------------------------------------------------
_OVERLAY_META: dict[str, dict[str, str]] = {
    "pirate": {
        "connector": "pirate_attacks",
        "title": "Global Maritime Pirate Attacks (1993-2020)",
        "provenance": "IMB ICC / Kaggle Global Maritime Pirate Attacks schema",
        "kind": "risk_heat",
    },
    "wpi": {
        "connector": "world_port_index",
        "title": "MSI World Port Index (NGA Pub 150)",
        "provenance": "NGA MSI World Port Index (Pub 150) schema",
        "kind": "reference_ports",
    },
}


def overlay_geojson(overlay_key: str, limit: int = 50) -> dict[str, Any]:
    """Return a valid GeoJSON FeatureCollection for a maritime overlay, built
    from the REAL szl_connectors overlay connector. Never fabricates rows: if the
    connector is unavailable it returns an EMPTY FeatureCollection labelled
    honestly (never a fabricated LIVE feature)."""
    meta = _OVERLAY_META.get(overlay_key)
    fc: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    if meta is None:
        fc["error"] = f"unknown overlay '{overlay_key}'"
        fc["data_label"] = "UNAVAILABLE"
        fc["count"] = 0
        return fc
    fc["overlay"] = overlay_key
    fc["title"] = meta["title"]
    fc["overlay_kind"] = meta["kind"]
    fc["provenance"] = meta["provenance"]
    c = None
    try:
        import szl_connectors as _sc
        c = _sc.get(meta["connector"])
    except Exception as e:  # honest degrade — never fabricate
        fc["error"] = f"{type(e).__name__}: {e}"
    if c is None:
        fc["data_label"] = "UNAVAILABLE"
        fc["live"] = False
        fc["count"] = 0
        fc["note"] = ("overlay connector not wired in this deployment — no features "
                      "served and none fabricated")
        return fc
    rec = c.read({"limit": max(1, min(int(limit), 200))}).to_dict()
    records = rec.get("records", []) or []
    live = bool(rec.get("live"))
    fc["live"] = live
    fc["state"] = rec.get("state", "sample")
    fc["data_label"] = "LIVE" if live else "SAMPLE"
    fc["note"] = rec.get("note", "")
    fc["source"] = rec.get("source", meta["provenance"])
    feats: list[dict[str, Any]] = []
    for row in records:
        lat = row.get("lat", row.get("Latitude"))
        lon = row.get("lon", row.get("Longitude"))
        try:
            lonf = float(lon)
            latf = float(lat)
        except Exception:
            continue  # drop coord-less rows; never fake a coordinate
        props = {k: v for k, v in row.items()
                 if k not in ("lat", "lon", "Latitude", "Longitude")}
        props["data_label"] = fc["data_label"]
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lonf, latf]},
            "properties": props,
        })
    fc["features"] = feats
    fc["count"] = len(feats)
    return fc


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

    ov_base = f"/api/{ns}/v1/overlays"

    @router.get(ov_base + "/pirate", include_in_schema=False)
    async def _ov_geo_pirate(limit: int = 50) -> JSONResponse:
        return JSONResponse(overlay_geojson("pirate", limit),
                            media_type="application/geo+json")

    @router.get(ov_base + "/wpi", include_in_schema=False)
    async def _ov_geo_wpi(limit: int = 50) -> JSONResponse:
        return JSONResponse(overlay_geojson("wpi", limit),
                            media_type="application/geo+json")

    registered.extend([
        f"GET {base}/sources",
        f"GET {base}/aug2024/tracks",
        f"GET {base}/aug2024/risk-board",
        f"GET {base}/tracks",
        f"GET {ov_base}/pirate",
        f"GET {ov_base}/wpi",
    ])
    app.include_router(router)
    print(f"[killinchu] /ais Aug-2024 governed source registered: "
          f"{len(registered)} routes", file=sys.stderr)
    return {"module": "killinchu_ais_aug2024", "registered_count": len(registered),
            "routes": registered}


__all__ = ["register", "load_aug2024_tracks", "risk_board", "sources_manifest",
           "NOAA_SOURCE_ID", "LIVE_SOURCE_ID"]
