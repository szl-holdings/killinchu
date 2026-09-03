"""
killinchu_fleet_vessels.py — canonical commercial-fleet and voyage-risk surface.

The historical seed datasets remain available for reproducible demonstrations.
The canonical current-state endpoint is additive and consumes Killinchu's existing
real-data redundancy chain:

    AISStream (keyed) -> Digitraffic (no key) -> Kystverket (no key)
    -> optional Marinesia -> explicitly labelled SAMPLE/replay.

It also binds the public sanctions stream, the portable Anatomy/formula engine,
and the handles-only SZL Second Brain. No component is allowed to promote a
sample, model output, lexical retrieval score, or unavailable feed to LIVE truth.

Canonical endpoints:
  GET /api/killinchu/v1/fleet/voyage-risk/current
  GET /api/killinchu/v1/vertical/contract
  GET /api/killinchu/v1/vertical/runtime

Compatibility endpoint:
  GET /api/killinchu/v1/fleet/voyage-risk
      deterministic sample/replay loop retained for reproducibility.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover - pure-Python test/import fallback
    APIRouter = None  # type: ignore
    JSONResponse = None  # type: ignore

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_HERE, "fleet_vessels_data.json")

HONESTY_LABEL = "Sample fleet dataset — not a live AIS/class-society feed."
SCHEMA = "szl.killinchu.vertical-runtime/v1"
CURRENT_SCHEMA = "szl.killinchu.voyage-risk-current/v1"

YUYAY_AXES = (
    "sacred:harmlessness",
    "sacred:truthfulness",
    "struct:coherence",
    "struct:groundedness",
    "struct:calibration",
    "struct:provenance",
    "struct:reversibility",
    "struct:proportionality",
    "struct:transparency",
    "intro:T03-self-model",
    "intro:T04-value-drift",
    "intro:T09-deception-check",
    "intro:T10-power-seeking",
)

LOCKED_PROVEN = ("F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22")

FORMULA_BINDINGS = (
    {
        "name": "lambda_aggregate",
        "role": "Aggregate only measured operational sufficiency axes.",
        "application": "current voyage-risk evidence plane",
        "full_yuyay13_claimed": False,
        "honesty": "Λ uniqueness remains Conjecture 1; unmeasured axes are excluded, never imputed.",
    },
    {
        "name": "lambda_bounded",
        "role": "Verify the aggregate remains bounded by its measured inputs.",
        "application": "runtime formula guard",
        "full_yuyay13_claimed": False,
        "honesty": "A4 bound check; not a correctness or safety oracle.",
    },
    {
        "name": "khipu_merkle_root",
        "role": "Bind downstream decision receipts when a receipt chain is emitted.",
        "application": "receipt/audit plane",
        "full_yuyay13_claimed": False,
        "honesty": "A hash-chain proves integrity/origin only, never accuracy.",
    },
    {
        "name": "dsse_envelope",
        "role": "Wrap governed decisions when a real signing key is present.",
        "application": "receipt/audit plane",
        "full_yuyay13_claimed": False,
        "honesty": "Unsigned remains explicitly UNSIGNED; no signature is fabricated.",
    },
)

FLEET_SOURCES = [
    {
        "leader": "IMO (International Maritime Organization)",
        "kind": "SOLAS / ISM / MARPOL fleet-safety standards",
        "url": "https://www.imo.org/",
        "data_kind": "standard",
    },
    {
        "leader": "IACS (International Association of Classification Societies)",
        "kind": "class-society survey and certification rules",
        "url": "https://iacs.org.uk/",
        "data_kind": "standard",
    },
    {
        "leader": "Paris MoU on Port State Control",
        "kind": "port-state inspection and deficiency regime",
        "url": "https://www.parismou.org/",
        "data_kind": "standard",
    },
    {
        "leader": "ITU-R M.1371 AIS",
        "kind": "vessel cooperative-identity broadcast standard",
        "url": "https://www.itu.int/rec/R-REC-M.1371",
        "data_kind": "standard",
    },
]

DATA_SOURCE_CONTRACT = (
    {
        "id": "aisstream",
        "kind": "AIS",
        "authority": "AISStream.io",
        "credential": "optional secret",
        "coverage": "configured global theaters",
        "fallback_rank": 1,
    },
    {
        "id": "digitraffic",
        "kind": "AIS",
        "authority": "Fintraffic Digitraffic",
        "credential": "none",
        "coverage": "Finland/Baltic",
        "fallback_rank": 2,
    },
    {
        "id": "kystverket",
        "kind": "AIS",
        "authority": "Norwegian Coastal Administration",
        "credential": "none",
        "coverage": "Norwegian waters",
        "fallback_rank": 3,
    },
    {
        "id": "marinesia",
        "kind": "AIS",
        "authority": "Marinesia",
        "credential": "optional secret",
        "coverage": "provider plan",
        "fallback_rank": 4,
    },
    {
        "id": "un1718",
        "kind": "sanctions",
        "authority": "UN Security Council 1718 via OpenSanctions",
        "credential": "none",
        "coverage": "designated vessels",
        "fallback_rank": 1,
    },
    {
        "id": "noaa-ais-2024-08",
        "kind": "historical AIS",
        "authority": "NOAA MarineCadastre",
        "credential": "none",
        "coverage": "coastal United States, August 2024",
        "fallback_rank": None,
        "state": "HISTORICAL_SAMPLE",
    },
)

_DATASETS: dict[str, Any] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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


# -----------------------------------------------------------------------
# Reproducible sample/replay decision loop (compatibility).
# -----------------------------------------------------------------------
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
    del signals
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
            "id": f"ev_vessels_{signal['id']}",
            "from_signal": signal["id"],
            "source": signal["source"],
            "claim": signal["summary"],
        }
        for signal in signals
    ]


def _recommendation_build(
    *,
    signals: list[dict[str, Any]],
    forecast: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    del signals
    return {
        "id": "rec_vessels_refresh_sanctions_screen",
        "vertical": "killinchu",
        "domain": "vessels",
        "title": "Refresh sanctions screening for counterparty before bunkering",
        "owner": "vessels-ops@szl",
        "confidence": float(forecast.get("confidence", 0.6)),
        "evidence_ids": [item["id"] for item in evidence],
        "next_action": "Re-run sanctions screen and document refresh in the voyage flight recorder.",
        "rollback_path": "If the counterparty fails the refreshed screen, hold bunkering and escalate.",
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
    del signals
    return {
        "headline": recommendation["title"],
        "delay_risk": forecast.get("delay_risk"),
        "route_risk": forecast.get("route_risk"),
        "claims_risk_placeholder": forecast.get("claims_risk_placeholder"),
        "evidence_count": len(evidence),
        "next_action": recommendation["next_action"],
    }


def voyage_risk_loop() -> dict[str, Any]:
    """Run the deterministic sample/replay loop retained for compatibility."""
    signals = _signals_collect()
    forecast = _forecast_compute(signals)
    evidence = _evidence_gather(signals)
    recommendation = _recommendation_build(
        signals=signals,
        forecast=forecast,
        evidence=evidence,
    )
    brief = _brief_synthesise(
        signals=signals,
        forecast=forecast,
        evidence=evidence,
        recommendation=recommendation,
    )
    return {
        "schema": "szl.killinchu.voyage-risk-sample/v1",
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
            "Reproducible SAMPLE/REPLAY loop. The recommendation is ADVISORY, "
            "requires human approval, and does not represent a current vessel, "
            "weather, sanctions, or class-society observation."
        ),
        "data_kind": "SAMPLE",
        "sources": FLEET_SOURCES,
    }


# -----------------------------------------------------------------------
# Canonical live/current runtime.
# -----------------------------------------------------------------------
def _default_vessel_fetcher(
    theater: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    import killinchu_feeds_realdata as realdata

    return realdata._fetch_vessels(theater, limit, "all")


def _default_sanctions_fetcher() -> dict[str, Any]:
    import killinchu_feeds_realdata as realdata

    return realdata._osint_cached(
        "sanctioned_vessels",
        realdata._osint_sanctioned_vessels,
    )


def _normalize_name(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return " ".join(text.split())


def _identifier_set(value: Any) -> set[str]:
    return set(re.findall(r"\d{7,9}", str(value or "")))


def screen_track_against_sanctions(
    track: dict[str, Any],
    sanctions: dict[str, Any],
) -> dict[str, Any]:
    """Exact-name/identifier advisory screen; never a compliance clearance."""
    if not sanctions.get("live"):
        return {
            "state": "UNAVAILABLE",
            "potential_match": False,
            "clearance": False,
            "matches": [],
            "honesty": "Sanctions source unavailable; no clean result is inferred.",
        }

    raw = track.get("raw") if isinstance(track.get("raw"), dict) else {}
    track_names = {
        value
        for value in (
            _normalize_name(track.get("label")),
            _normalize_name(raw.get("name")),
            _normalize_name(raw.get("ship_name")),
        )
        if len(value) >= 4
    }
    track_ids = set()
    for value in (
        raw.get("imo"),
        raw.get("imo_number"),
        raw.get("mmsi"),
        track.get("imo"),
        track.get("mmsi"),
    ):
        track_ids.update(_identifier_set(value))

    matches: list[dict[str, Any]] = []
    for item in sanctions.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_names = {
            value
            for value in (
                _normalize_name(item.get("name")),
                *(
                    _normalize_name(alias)
                    for alias in (item.get("aliases") or [])
                ),
            )
            if len(value) >= 4
        }
        item_ids = _identifier_set(item.get("identifiers"))
        reasons = []
        if track_names and item_names and track_names.intersection(item_names):
            reasons.append("exact_normalized_name")
        if track_ids and item_ids and track_ids.intersection(item_ids):
            reasons.append("exact_identifier")
        if reasons:
            matches.append(
                {
                    "name": item.get("name"),
                    "identifiers": item.get("identifiers"),
                    "program": item.get("program"),
                    "reasons": reasons,
                }
            )

    identity_present = bool(track_names or track_ids)
    if matches:
        state = "POTENTIAL_EXACT_MATCH"
    elif identity_present:
        state = "NO_EXACT_MATCH"
    else:
        state = "UNRESOLVED_IDENTITY"

    return {
        "state": state,
        "potential_match": bool(matches),
        "clearance": False,
        "matches": matches[:10],
        "source": sanctions.get("source"),
        "source_url": sanctions.get("source_url"),
        "source_mode": sanctions.get("mode"),
        "source_fetched_at": sanctions.get("fetched_at"),
        "honesty": (
            "Exact advisory screening only. NO_EXACT_MATCH is not regulatory "
            "clearance; transliteration, beneficial ownership, stale identities, "
            "and non-vessel sanctions require separate human compliance review."
        ),
    }


def _formula_run(
    name: str,
    args: list[Any],
    runner: Callable[[str, list[Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if runner is not None:
        return runner(name, args)
    try:
        import szl_anatomy_routes

        return szl_anatomy_routes.run_one(name, args)
    except Exception as exc:
        return {
            "ok": False,
            "formula": name,
            "error": type(exc).__name__,
            "proof_status": "UNAVAILABLE",
            "honesty": "Formula engine unavailable; no score is fabricated.",
        }


def _truth_state(mode: str, tracks: list[dict[str, Any]]) -> str:
    if mode in {"live", "mixed"} and any(item.get("live") is True for item in tracks):
        return "LIVE" if mode == "live" else "MIXED"
    if mode == "sample" and tracks:
        return "SAMPLE"
    return "UNAVAILABLE"


def _brain_allowed(base_url: str) -> tuple[bool, str | None]:
    try:
        parsed = urllib.parse.urlparse(base_url)
    except ValueError:
        return False, None
    host = (parsed.hostname or "").lower()
    configured = {
        item.strip().lower()
        for item in os.environ.get("SZL_SECOND_BRAIN_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    allowed = {"szlholdings-second-brain.hf.space", *configured}
    return parsed.scheme == "https" and host in allowed, host or None


def second_brain_context(
    query: str,
    k: int = 6,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Resolve handles locally when installed, otherwise via the public Space."""
    scoped_query = f"vertical killinchu domain vessels {query}".strip()
    try:
        from second_brain import navigator_context

        payload = navigator_context(scoped_query, k=max(1, min(int(k), 12)))
        return {
            "state": payload.get("state", "UNAVAILABLE"),
            "mode": "LOCAL_SOFTWARE",
            "ready": bool(payload.get("ready")),
            "handles": payload.get("handles") or [],
            "evidence": payload.get("evidence") or [],
            "content_access": "HANDLES_ONLY",
            "query": scoped_query,
            "honesty": payload.get("honesty"),
        }
    except Exception:
        pass

    base_url = (
        os.environ.get("SZL_SECOND_BRAIN_URL")
        or "https://szlholdings-second-brain.hf.space"
    ).rstrip("/")
    allowed, host = _brain_allowed(base_url)
    if not allowed:
        return {
            "state": "UNAVAILABLE",
            "mode": "REMOTE_BLOCKED",
            "ready": False,
            "handles": [],
            "evidence": [],
            "content_access": "HANDLES_ONLY",
            "query": scoped_query,
            "host": host,
            "honesty": "Second Brain URL is outside the explicit HTTPS host allowlist.",
        }

    url = (
        f"{base_url}/api/v1/navigator?"
        + urllib.parse.urlencode(
            {"q": scoped_query, "k": max(1, min(int(k), 12))}
        )
    )
    open_url = opener or urllib.request.urlopen
    try:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "killinchu-vertical-runtime/1.0",
            },
        )
        with open_url(request, timeout=5) as response:
            raw = response.read(512_000)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("second brain response must be an object")
        return {
            "state": payload.get("state", "UNAVAILABLE"),
            "mode": "REMOTE_SOFTWARE",
            "ready": bool(payload.get("ready")),
            "handles": payload.get("handles") or [],
            "evidence": payload.get("evidence") or [],
            "content_access": "HANDLES_ONLY",
            "query": scoped_query,
            "source_url": f"{base_url}/api/v1/navigator",
            "honesty": payload.get("honesty"),
        }
    except Exception as exc:
        return {
            "state": "UNAVAILABLE",
            "mode": "REMOTE_UNAVAILABLE",
            "ready": False,
            "handles": [],
            "evidence": [],
            "content_access": "HANDLES_ONLY",
            "query": scoped_query,
            "source_url": f"{base_url}/api/v1/navigator",
            "error": type(exc).__name__,
            "honesty": (
                "Second Brain did not answer. No retrieval, grounding, or "
                "correctness claim is fabricated."
            ),
        }


def _build_axes(
    *,
    tracks: list[dict[str, Any]],
    data_state: str,
    sanctions: dict[str, Any],
    recommendation: dict[str, Any],
) -> list[dict[str, Any]]:
    count = len(tracks)
    truth_fields = ("source", "source_url", "provenance", "ts", "live")
    provenance_ratio = (
        sum(
            1
            for track in tracks
            if all(field in track and track.get(field) is not None for field in truth_fields)
        )
        / count
        if count
        else 0.0
    )
    no_label_mismatch = all(
        not (track.get("live") is True and "sample" in str(track.get("source", "")).lower())
        for track in tracks
    )
    observed: dict[str, tuple[float, str]] = {
        "sacred:harmlessness": (
            1.0 if recommendation.get("requires_human_approval") else 0.0,
            "advisory-only recommendation; physical action remains human-authorized",
        ),
        "sacred:truthfulness": (
            provenance_ratio,
            "fraction of tracks carrying source/source_url/provenance/timestamp/live labels",
        ),
        "struct:groundedness": (
            1.0 if data_state == "LIVE" else 0.8 if data_state == "MIXED" else 0.45 if data_state == "SAMPLE" else 0.0,
            f"current AIS evidence state={data_state}",
        ),
        "struct:provenance": (
            provenance_ratio,
            "record-level provenance completeness",
        ),
        "struct:reversibility": (
            1.0 if recommendation.get("rollback_path") else 0.0,
            "rollback path present in recommendation envelope",
        ),
        "struct:transparency": (
            1.0,
            "signals, assessment, sources tried, formula result, and gaps are returned",
        ),
        "intro:T09-deception-check": (
            1.0 if no_label_mismatch else 0.0,
            "guard rejects LIVE records whose source identifies them as sample",
        ),
    }
    if sanctions.get("live"):
        observed["struct:coherence"] = (
            1.0,
            "AIS and sanctions evidence are both available for cross-check",
        )

    rows = []
    for axis in YUYAY_AXES:
        if axis in observed:
            value, basis = observed[axis]
            rows.append(
                {
                    "axis": axis,
                    "state": "MEASURED_PROXY",
                    "value": round(max(0.0, min(1.0, float(value))), 6),
                    "basis": basis,
                }
            )
        else:
            rows.append(
                {
                    "axis": axis,
                    "state": "UNMEASURED",
                    "value": None,
                    "basis": "No defensible runtime measurement in this request; excluded from Λ.",
                }
            )
    return rows


def _formula_assessment(
    axes: list[dict[str, Any]],
    runner: Callable[[str, list[Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    measured = [row["value"] for row in axes if row.get("value") is not None]
    if not measured:
        return {
            "state": "UNAVAILABLE",
            "full_yuyay13": None,
            "partial_operational_lambda": None,
            "axis_coverage": 0.0,
            "honesty": "No measured axes; no Λ is fabricated.",
        }
    result = _formula_run("lambda_aggregate", [measured], runner=runner)
    value = result.get("result") if result.get("ok") else None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        bounded = _formula_run("lambda_bounded", [measured], runner=runner)
        aggregate = round(float(value), 6)
    else:
        bounded = {
            "ok": False,
            "formula": "lambda_bounded",
            "proof_status": "UNAVAILABLE",
        }
        aggregate = None
    return {
        "state": "COMPUTED_PARTIAL" if aggregate is not None else "UNAVAILABLE",
        "full_yuyay13": None,
        "partial_operational_lambda": aggregate,
        "measured_axis_count": len(measured),
        "axis_count": len(YUYAY_AXES),
        "axis_coverage": round(len(measured) / len(YUYAY_AXES), 6),
        "aggregate": result,
        "bound_check": bounded,
        "lambda_uniqueness": "Conjecture 1 — OPEN",
        "locked_proven_formula_ids": list(LOCKED_PROVEN),
        "honesty": (
            "Only measured runtime proxies are aggregated. UNMEASURED axes "
            "remain null and are excluded. This is not a full Yuyay-13 score, "
            "not a probability of correctness, and not an authorization."
        ),
    }


def _risk_level(
    tracks: list[dict[str, Any]],
    screens: list[dict[str, Any]],
    data_state: str,
) -> str:
    if data_state == "UNAVAILABLE":
        return "UNAVAILABLE"
    if data_state == "SAMPLE":
        return "DEMONSTRATION"
    if any(item.get("potential_match") for item in screens):
        return "CRITICAL_REVIEW"
    dark = sum(
        1
        for track in tracks
        if isinstance(track.get("dark_fleet"), dict)
        and track["dark_fleet"].get("flag")
    )
    not_under_command = sum(
        1
        for track in tracks
        if "not under command" in str(track.get("kind", "")).lower()
    )
    if not_under_command or dark > max(2, len(tracks) // 5):
        return "HIGH_REVIEW"
    if dark:
        return "ELEVATED_REVIEW"
    return "MONITOR"


def _anatomy_state(
    *,
    data_state: str,
    sanctions_state: str,
    brain: dict[str, Any],
    formula: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    organs = [
        {
            "organ": "EYES_EARS",
            "role": "AIS and public-source sensing",
            "state": data_state,
            "evidence": "/api/killinchu/v1/feeds/vessels",
        },
        {
            "organ": "IMMUNE",
            "role": "sanctions and anomaly screening",
            "state": sanctions_state,
            "evidence": "/api/killinchu/v1/osint/intel?vertical=sanctioned_vessels",
        },
        {
            "organ": "BRAIN",
            "role": "handles-only grounded retrieval",
            "state": brain.get("state", "UNAVAILABLE"),
            "evidence": brain.get("source_url") or "local second_brain package",
        },
        {
            "organ": "SKELETON",
            "role": "formula and doctrine contract",
            "state": formula.get("state", "UNAVAILABLE"),
            "evidence": "/api/killinchu/v1/formulas",
        },
        {
            "organ": "HEART",
            "role": "governed decision loop",
            "state": "LIVE" if recommendation.get("requires_human_approval") else "HALT",
            "evidence": "current response recommendation envelope",
        },
        {
            "organ": "HANDS",
            "role": "operator-authorized execution only",
            "state": "HUMAN_LOCK",
            "evidence": recommendation.get("next_action"),
        },
        {
            "organ": "MEMORY",
            "role": "evidence digest and downstream receipt binding",
            "state": "HASHED_NOT_SIGNED",
            "evidence": "response evidence_digest",
        },
    ]
    return {
        "schema": "szl.anatomy.vertical-binding/v1",
        "state": "DEGRADED" if any(
            item["state"] in {"UNAVAILABLE", "HALT"} for item in organs
        ) else "OPERATIONAL",
        "organs": organs,
        "honesty": (
            "Organ state is derived from this request's evidence. DOWN or "
            "UNAVAILABLE remains visible; no fabricated calm."
        ),
    }


def build_current_voyage_risk(
    theater: str = "baltic",
    limit: int = 40,
    query: str = "current maritime risk sanctions dark vessel voyage",
    *,
    vessel_fetcher: Callable[
        [str, int],
        tuple[list[dict[str, Any]], list[dict[str, Any]], str],
    ]
    | None = None,
    sanctions_fetcher: Callable[[], dict[str, Any]] | None = None,
    brain_fetcher: Callable[[str, int], dict[str, Any]] | None = None,
    formula_runner: Callable[[str, list[Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a current, evidence-labelled governed voyage-risk observation."""
    bounded_limit = max(1, min(int(limit), 200))
    fetch_vessels = vessel_fetcher or _default_vessel_fetcher
    fetch_sanctions = sanctions_fetcher or _default_sanctions_fetcher
    fetch_brain = brain_fetcher or second_brain_context

    try:
        tracks, sources_tried, mode = fetch_vessels(theater, bounded_limit)
    except Exception as exc:
        tracks, sources_tried, mode = [], [
            {
                "source": "Killinchu vessel redundancy chain",
                "ok": False,
                "error": type(exc).__name__,
            }
        ], "unavailable"
    data_state = _truth_state(mode, tracks)

    try:
        sanctions = fetch_sanctions()
        if not isinstance(sanctions, dict):
            raise TypeError("sanctions fetcher must return an object")
    except Exception as exc:
        sanctions = {
            "live": False,
            "mode": "unreachable",
            "items": [],
            "count": 0,
            "error": type(exc).__name__,
            "honesty": "Sanctions source unavailable; no result is inferred.",
        }
    sanctions_state = (
        "LIVE"
        if sanctions.get("live") and sanctions.get("mode") == "live"
        else "CACHED"
        if sanctions.get("live")
        else "UNAVAILABLE"
    )

    screens = [
        screen_track_against_sanctions(track, sanctions)
        for track in tracks
    ]
    potential_matches = [
        {
            "track_id": track.get("track_id"),
            "label": track.get("label"),
            "screen": screen,
        }
        for track, screen in zip(tracks, screens)
        if screen.get("potential_match")
    ]
    dark_tracks = [
        track
        for track in tracks
        if isinstance(track.get("dark_fleet"), dict)
        and track["dark_fleet"].get("flag")
    ]

    signals = [
        {
            "id": "sig_current_track_count",
            "kind": "coverage",
            "value": len(tracks),
            "state": data_state,
            "source": "Killinchu AIS redundancy chain",
        },
        {
            "id": "sig_dark_fleet_advisories",
            "kind": "behavioral_anomaly",
            "value": len(dark_tracks),
            "state": "ADVISORY",
            "source": "deterministic heuristic over returned AIS tracks",
        },
        {
            "id": "sig_sanctions_exact_matches",
            "kind": "compliance_review",
            "value": len(potential_matches),
            "state": sanctions_state,
            "source": sanctions.get("source"),
        },
        {
            "id": "sig_unresolved_flag_states",
            "kind": "identity_quality",
            "value": sum(1 for track in tracks if not track.get("country")),
            "state": data_state,
            "source": "AIS MMSI MID resolution",
        },
    ]

    risk_level = _risk_level(tracks, screens, data_state)
    recommendation = {
        "id": f"rec_killinchu_vessels_{_canonical_sha256(signals)[:16]}",
        "vertical": "killinchu",
        "domain": "vessels",
        "title": (
            "Escalate exact sanctions match to a human compliance officer"
            if potential_matches
            else "Review current AIS anomalies and retain monitoring"
            if data_state in {"LIVE", "MIXED"}
            else "Restore current AIS coverage before making an operational decision"
        ),
        "owner": "vessels-ops@szl",
        "confidence": None,
        "evidence_ids": [signal["id"] for signal in signals],
        "next_action": (
            "Open the evidence bundle, validate vessel identity, and obtain "
            "human approval before any hold, routing, or counterparty action."
        ),
        "rollback_path": (
            "Cancel the proposed operational change and return to monitor-only "
            "state if identity, provenance, or current-data checks fail."
        ),
        "requires_human_approval": True,
        "input_class": "killinchu_current_maritime_observation_v1",
        "output_class": "killinchu_human_review_recommendation_v1",
        "automation_authority": "NONE",
    }

    axes = _build_axes(
        tracks=tracks,
        data_state=data_state,
        sanctions=sanctions,
        recommendation=recommendation,
    )
    formula = _formula_assessment(axes, runner=formula_runner)
    brain = fetch_brain(query, 6)
    if not isinstance(brain, dict):
        brain = {
            "state": "UNAVAILABLE",
            "ready": False,
            "handles": [],
            "honesty": "Second Brain fetcher returned an invalid payload.",
        }

    evidence = {
        "data_state": data_state,
        "mode": mode,
        "theater": theater,
        "tracks": tracks,
        "sources_tried": sources_tried,
        "sanctions": {
            key: sanctions.get(key)
            for key in (
                "live",
                "mode",
                "fetched_at",
                "source",
                "source_url",
                "count",
                "error",
            )
        },
        "potential_matches": potential_matches,
        "signals": signals,
        "formula": formula,
        "second_brain": brain,
    }
    evidence_digest = _canonical_sha256(evidence)
    anatomy = _anatomy_state(
        data_state=data_state,
        sanctions_state=sanctions_state,
        brain=brain,
        formula=formula,
        recommendation=recommendation,
    )

    stages = [
        {"stage": "INGEST", "state": data_state, "evidence": "AIS redundancy chain"},
        {"stage": "TRANSFORM", "state": "COMPUTED", "evidence": "TRACK normalization"},
        {"stage": "ANALYZE", "state": formula.get("state"), "evidence": "partial measured-axis Λ"},
        {"stage": "DECIDE", "state": "ADVISORY", "evidence": recommendation["id"]},
        {"stage": "APPROVE", "state": "HUMAN_REQUIRED", "evidence": "Human Lock"},
        {"stage": "EXECUTE", "state": "NOT_AUTHORIZED", "evidence": "automation_authority=NONE"},
        {"stage": "VERIFY", "state": "HASHED", "evidence": evidence_digest},
        {"stage": "AUDIT", "state": "AVAILABLE", "evidence": "sources/signals/formula returned"},
        {"stage": "DELIVER", "state": "CURRENT_RESPONSE", "evidence": CURRENT_SCHEMA},
    ]

    return {
        "schema": CURRENT_SCHEMA,
        "vertical": "killinchu",
        "domain": "vessels",
        "canonical_product": True,
        "generated_at": _now_iso(),
        "theater": theater,
        "risk_level": risk_level,
        "current_data": {
            "state": data_state,
            "mode": mode,
            "track_count": len(tracks),
            "live_track_count": sum(1 for track in tracks if track.get("live") is True),
            "sample_track_count": sum(1 for track in tracks if track.get("live") is not True),
            "sources_tried": sources_tried,
        },
        "signals": signals,
        "assessment": {
            "kind": "CURRENT_DETERMINISTIC_ASSESSMENT",
            "prediction": None,
            "prediction_state": "NOT_MODELLED",
            "dark_fleet_advisory_count": len(dark_tracks),
            "sanctions_potential_match_count": len(potential_matches),
            "honesty": (
                "A current assessment is not a voyage forecast. No statistical "
                "delay, casualty, or route prediction is claimed here."
            ),
        },
        "sanctions": {
            "state": sanctions_state,
            "source": sanctions.get("source"),
            "source_url": sanctions.get("source_url"),
            "fetched_at": sanctions.get("fetched_at"),
            "potential_matches": potential_matches,
            "clearance": False,
            "honesty": (
                "Advisory exact-match screen only. Human compliance review remains mandatory."
            ),
        },
        "formula": formula,
        "axes": axes,
        "second_brain": brain,
        "anatomy": anatomy,
        "recommendation": recommendation,
        "business_observability_loop": stages,
        "evidence_digest": evidence_digest,
        "receipt_state": "HASHED_NOT_SIGNED",
        "gaps": {
            "beneficial_ownership_graph": {
                "state": "UNAVAILABLE",
                "required_before_claim": True,
                "reason": (
                    "An operator-reported graph helper exists in source, but no authenticated, "
                    "runtime-bound, independently verified ownership source is attached here. "
                    "Corporate registries and beneficial ownership require licensed/"
                    "jurisdiction-specific sources and entity-resolution controls."
                ),
            },
            "class_society_status": {
                "state": "UNAVAILABLE",
                "required_before_claim": True,
            },
            "global_current_ais_without_key": {
                "state": "PARTIAL",
                "reason": (
                    "No-key current AIS is geographically bounded; global/current "
                    "coverage requires an authorized provider credential."
                ),
            },
        },
        "honesty": (
            "LIVE means a current upstream fetch returned records for this theater. "
            "SAMPLE means bundled replay. UNAVAILABLE remains unavailable. Broadcast "
            "AIS fields are cooperative claims and may be stale, spoofed, or incomplete. "
            "This endpoint makes recommendations only; it authorizes no physical action."
        ),
    }


def vertical_contract() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "vertical": {
            "id": "killinchu",
            "title": "Killinchu",
            "role": "Defense and autonomous-systems command vertical",
            "domains": ["counter_uas", "vessels"],
            "vessels_consolidated": True,
            "standalone_vessels_product": False,
        },
        "data_sources": list(DATA_SOURCE_CONTRACT),
        "formula_bindings": list(FORMULA_BINDINGS),
        "second_brain": {
            "contract": "szl.brain.navigator-context/v1",
            "content_access": "HANDLES_ONLY",
            "local_preferred": True,
            "remote_default": "https://szlholdings-second-brain.hf.space/api/v1/navigator",
            "score_is_correctness": False,
        },
        "anatomy": {
            "contract": "szl.anatomy.vertical-binding/v1",
            "required_organs": [
                "EYES_EARS",
                "IMMUNE",
                "BRAIN",
                "SKELETON",
                "HEART",
                "HANDS",
                "MEMORY",
            ],
        },
        "doctrine": {
            "version": "v11",
            "locked_proven_formula_ids": list(LOCKED_PROVEN),
            "lambda_uniqueness": "Conjecture 1 — OPEN",
        },
        "canonical_current_endpoint": "/api/killinchu/v1/fleet/voyage-risk/current",
        "compatibility_sample_endpoint": "/api/killinchu/v1/fleet/voyage-risk",
        "honesty": (
            "Contract registration is not runtime readiness. Use /vertical/runtime "
            "or /fleet/voyage-risk/current for request-level evidence."
        ),
    }


def register(app) -> dict[str, Any]:
    if APIRouter is None:
        return {
            "module": "killinchu_fleet_vessels",
            "registered_count": 0,
            "error": "fastapi missing",
        }

    data = _load()
    router = APIRouter()
    base = "/api/killinchu/v1/fleet"
    registered: list[str] = []

    def _serve(key: str):
        async def _handler() -> JSONResponse:
            return JSONResponse(
                {
                    "data": data.get(key, []),
                    "data_kind": "SAMPLE",
                    "honesty": HONESTY_LABEL,
                    "source_key": key,
                    "sources": FLEET_SOURCES,
                }
            )

        return _handler

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
        return JSONResponse(
            {
                "datasets": data,
                "counts": {
                    key: len(value) if isinstance(value, list) else None
                    for key, value in data.items()
                },
                "data_kind": "SAMPLE",
                "honesty": HONESTY_LABEL,
                "sources": FLEET_SOURCES,
                "source": "github.com/szl-holdings/platform seed-data/vessels/*",
            }
        )

    registered.append(f"{base}/all")

    @router.get(f"{base}/voyage-risk")
    async def _voyage_sample() -> JSONResponse:
        return JSONResponse(voyage_risk_loop())

    registered.append(f"{base}/voyage-risk")

    @router.get(f"{base}/voyage-risk/current")
    async def _voyage_current(
        theater: str = "baltic",
        limit: int = 40,
        q: str = "current maritime risk sanctions dark vessel voyage",
    ) -> JSONResponse:
        import anyio

        payload = await anyio.to_thread.run_sync(
            lambda: build_current_voyage_risk(
                theater=theater,
                limit=limit,
                query=q,
            )
        )
        return JSONResponse(payload)

    registered.append(f"{base}/voyage-risk/current")

    @router.get("/api/killinchu/v1/vertical/contract")
    async def _contract() -> JSONResponse:
        return JSONResponse(vertical_contract())

    registered.append("/api/killinchu/v1/vertical/contract")

    @router.get("/api/killinchu/v1/vertical/runtime")
    async def _runtime(
        theater: str = "baltic",
        limit: int = 20,
        q: str = "current killinchu vessels operating picture",
    ) -> JSONResponse:
        import anyio

        payload = await anyio.to_thread.run_sync(
            lambda: build_current_voyage_risk(
                theater=theater,
                limit=limit,
                query=q,
            )
        )
        return JSONResponse(
            {
                "schema": SCHEMA,
                "contract": vertical_contract(),
                "runtime": payload,
                "state": payload["anatomy"]["state"],
                "generated_at": payload["generated_at"],
            }
        )

    registered.append("/api/killinchu/v1/vertical/runtime")

    app.include_router(router)
    return {
        "module": "killinchu_fleet_vessels",
        "registered_count": len(registered),
        "routes": registered,
        "canonical_vertical": "killinchu",
        "domains": ["counter_uas", "vessels"],
    }


__all__ = [
    "DATA_SOURCE_CONTRACT",
    "FORMULA_BINDINGS",
    "YUYAY_AXES",
    "build_current_voyage_risk",
    "register",
    "screen_track_against_sanctions",
    "second_brain_context",
    "vertical_contract",
    "voyage_risk_loop",
]
