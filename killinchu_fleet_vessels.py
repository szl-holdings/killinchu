"""
killinchu_fleet_vessels.py — FLEET (Vessels) commercial-fleet surface (GAP-1 + GAP-2).

ADDITIVE module. serve.py imports this and calls register(app) AFTER the other
routers but BEFORE the SPA catch-all. It does NOT touch any existing route.

GAP-1 — serve the REAL platform seed-data/vessels/* datasets VERBATIM as static
JSON endpoints under /api/killinchu/v1/fleet/*. These are clearly-labelled SAMPLE
fleet data, NOT a live AIS / class-society feed.

  GET /api/killinchu/v1/fleet/vessels                 -> seed-data/vessels/vessels.json
  GET /api/killinchu/v1/fleet/forecast-modules        -> seed-data/vessels/forecast-modules.json
  GET /api/killinchu/v1/fleet/predictive-maintenance  -> seed-data/vessels/predictive-maintenance.json
  GET /api/killinchu/v1/fleet/compliance-certificates -> seed-data/vessels/compliance-certificates.json
  GET /api/killinchu/v1/fleet/port-state-deficiencies -> seed-data/vessels/port-state-deficiencies.json
  GET /api/killinchu/v1/fleet/ai-briefings            -> seed-data/vessels/ai-briefings.json
  GET /api/killinchu/v1/fleet/event-logs              -> seed-data/vessels/event-logs.json
  GET /api/killinchu/v1/fleet/fleets                  -> seed-data/vessels/fleets.json
  GET /api/killinchu/v1/fleet/maintenance-logs        -> seed-data/vessels/maintenance-logs.json
  GET /api/killinchu/v1/fleet/shipment-records        -> seed-data/vessels/shipment-records.json
  GET /api/killinchu/v1/fleet/all                      -> {datasets..., honesty}

GAP-2 — the vessels vertical "Voyage Risk Exchange" governed-decision loop, ported
VERBATIM (pure functions) from platform services/verticals/vessels/{signals,forecast,
evidence,recommendations,brief}.py + contracts.py.

  GET /api/killinchu/v1/fleet/voyage-risk             -> full 5-stage loop result
                                                          (signals -> forecast -> evidence
                                                           -> recommendation w/ rollback -> brief)

Honesty doctrine (absolute): trust score Λ = Conjecture 1 (NOT a theorem); the
Recommendation is ADVISORY with a human-approval flag and a rollback path; the
datasets are sample/recorded, not a live feed.

Source provenance: github.com/szl-holdings/platform seed-data/vessels/* (datasets)
and services/verticals/vessels/* (decision loop), fetched via the GitHub contents
API and embedded verbatim.
"""
from __future__ import annotations

import json
import os
from typing import Any

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore
    JSONResponse = None  # type: ignore

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_HERE, "fleet_vessels_data.json")

HONESTY_LABEL = "Sample fleet dataset — not a live AIS/class-society feed."

# Cited real leader sources surfaced in every fleet tab payload. Live AIS and
# class-society registers are key-gated/commercial, so the datasets stay a cited
# SAMPLE — but each tab carries primary leader/standard sources (honest data_kind).
FLEET_SOURCES = [
    {"leader": "IMO (International Maritime Organization)", "kind": "SOLAS / ISM / MARPOL fleet-safety standards",
     "url": "https://www.imo.org/", "data_kind": "standard"},
    {"leader": "IACS (Int'l Assoc. of Classification Societies)", "kind": "class-society survey + certification rules",
     "url": "https://iacs.org.uk/", "data_kind": "standard"},
    {"leader": "Paris MoU on Port State Control", "kind": "port-state inspection / deficiency regime",
     "url": "https://www.parismou.org/", "data_kind": "standard"},
    {"leader": "ITU-R M.1371 AIS", "kind": "vessel cooperative-identity broadcast standard",
     "url": "https://www.itu.int/rec/R-REC-M.1371", "data_kind": "standard"},
]

# ---------------------------------------------------------------------------
# Dataset loader — read the embedded verbatim platform seed-data once.
# ---------------------------------------------------------------------------
_DATASETS: dict[str, Any] = {}


def _load() -> dict[str, Any]:
    global _DATASETS
    if _DATASETS:
        return _DATASETS
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as fh:
            _DATASETS = json.load(fh)
    except Exception:
        _DATASETS = {
            "vessels": [],
            "forecast-modules": [],
            "predictive-maintenance": [],
            "compliance-certificates": [],
            "port-state-deficiencies": [],
            "ai-briefings": [],
            "event-logs": [],
            "fleets": [],
            "maintenance-logs": [],
            "shipment-records": [],
        }
    return _DATASETS


# ---------------------------------------------------------------------------
# GAP-2 — Voyage Risk Exchange governed-decision loop (ported verbatim).
# Pure functions, no network. Mirrors platform services/verticals/vessels/*.
# ---------------------------------------------------------------------------
def _signals_collect() -> list[dict[str, object]]:
    return [
        {
            "id": "sig_vessels_eta_drift",
            "source": "ais",
            "kind": "delay_risk",
            "summary": "ETA drift +18h on charter VL-7714 since last port call",
            "weight": 0.8,
        },
        {
            "id": "sig_vessels_route_advisory",
            "source": "weather",
            "kind": "route_risk",
            "summary": "Beaufort 8 advisory active on planned routing window",
            "weight": 0.7,
        },
        {
            "id": "sig_vessels_compliance_check",
            "source": "compliance",
            "kind": "compliance_gap",
            "summary": "Sanctions screening not refreshed in last 14 days for counterparty",
            "weight": 0.85,
        },
    ]


def _forecast_compute(signals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "horizon": "next_voyage",
        "method": "voyage-risk-baseline-v0",
        "delay_risk": "elevated",
        "route_risk": "moderate",
        "claims_risk_placeholder": "watch",
        "confidence": 0.6,
    }


def _evidence_gather(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"ev_vessels_{s['id']}",
            "from_signal": s["id"],
            "source": s["source"],
            "claim": s["summary"],
        }
        for s in signals
    ]


def _recommendation_build(
    *, signals: list[dict[str, Any]], forecast: dict[str, Any], evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    # Mirrors contracts.Recommendation dataclass shape (to_dict()).
    return {
        "id": "rec_vessels_refresh_sanctions_screen",
        "vertical": "vessels",
        "title": "Refresh sanctions screening for counterparty before bunkering",
        "owner": "vessels-ops@szl",
        "confidence": float(forecast.get("confidence", 0.6)),
        "evidence_ids": [e["id"] for e in evidence],
        "next_action": "Re-run sanctions screen and document refresh in voyage flight recorder.",
        "rollback_path": "If counterparty fails refreshed screen, hold bunkering and escalate to compliance.",
        "requires_human_approval": True,
        "input_class": "vessels_voyage_signals_v1",
        "output_class": "voyage_risk_recommendation_v1",
    }


def _brief_synthesise(
    *,
    signals: list[dict[str, Any]],
    forecast: dict[str, Any],
    evidence: list[dict[str, Any]],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "headline": recommendation["title"],
        "delay_risk": forecast.get("delay_risk"),
        "route_risk": forecast.get("route_risk"),
        "claims_risk_placeholder": forecast.get("claims_risk_placeholder"),
        "evidence_count": len(evidence),
        "next_action": recommendation["next_action"],
    }


def voyage_risk_loop() -> dict[str, Any]:
    """Run the full 5-stage governed-decision loop and return every stage."""
    signals = _signals_collect()
    forecast = _forecast_compute(signals)
    evidence = _evidence_gather(signals)
    recommendation = _recommendation_build(signals=signals, forecast=forecast, evidence=evidence)
    brief = _brief_synthesise(
        signals=signals, forecast=forecast, evidence=evidence, recommendation=recommendation
    )
    return {
        "stages": ["signals", "forecast", "evidence", "recommendation", "brief"],
        "signals": signals,
        "forecast": forecast,
        "evidence": evidence,
        "recommendation": recommendation,
        "brief": brief,
        "trust_gate": {
            "lambda_status": "Conjecture 1 (advisory, NOT a theorem)",
            "advisory": True,
        },
        "honesty": (
            "Voyage Risk Exchange — governed-decision loop ported verbatim from the "
            "platform vessels vertical (signals -> forecast -> evidence -> recommendation "
            "-> brief). The recommendation is ADVISORY and requires human approval; the "
            "trust score is a documented Conjecture, not a proven oracle. Sample inputs."
        ),
        "data_kind": "sample_fleet_cited",
        "sources": FLEET_SOURCES,
        "source": "platform services/verticals/vessels/{signals,forecast,evidence,recommendations,brief}.py",
    }


# ---------------------------------------------------------------------------
# Route registration (ADDITIVE).
# ---------------------------------------------------------------------------
def register(app) -> dict[str, Any]:
    if APIRouter is None:
        return {"module": "killinchu_fleet_vessels", "registered_count": 0, "error": "fastapi missing"}

    data = _load()
    router = APIRouter()
    base = "/api/killinchu/v1/fleet"
    registered: list[str] = []

    def _serve(key: str):
        async def _h() -> JSONResponse:
            return JSONResponse(
                {"data": data.get(key, []), "data_kind": "sample_fleet_cited",
                 "honesty": HONESTY_LABEL, "source_key": key, "sources": FLEET_SOURCES}
            )
        return _h

    for key, path in [
        ("vessels", "/vessels"),
        ("forecast-modules", "/forecast-modules"),
        ("predictive-maintenance", "/predictive-maintenance"),
        ("compliance-certificates", "/compliance-certificates"),
        ("port-state-deficiencies", "/port-state-deficiencies"),
        ("ai-briefings", "/ai-briefings"),
        ("event-logs", "/event-logs"),
        ("fleets", "/fleets"),
        ("maintenance-logs", "/maintenance-logs"),
        ("shipment-records", "/shipment-records"),
    ]:
        router.add_api_route(f"{base}{path}", _serve(key), methods=["GET"])
        registered.append(f"{base}{path}")

    @router.get(f"{base}/all")
    async def _all() -> JSONResponse:
        return JSONResponse({
            "datasets": data,
            "counts": {k: (len(v) if isinstance(v, list) else None) for k, v in data.items()},
            "data_kind": "sample_fleet_cited",
            "honesty": HONESTY_LABEL,
            "sources": FLEET_SOURCES,
            "source": "github.com/szl-holdings/platform seed-data/vessels/*",
        })
    registered.append(f"{base}/all")

    @router.get(f"{base}/voyage-risk")
    async def _voyage() -> JSONResponse:
        return JSONResponse(voyage_risk_loop())
    registered.append(f"{base}/voyage-risk")

    app.include_router(router)
    return {"module": "killinchu_fleet_vessels", "registered_count": len(registered), "routes": registered}
