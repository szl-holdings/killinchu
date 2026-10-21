# SPDX-License-Identifier: Apache-2.0
"""Killinchu Defend / civilian roof and building inspection rehearsal.

A bounded, civilian maintenance scenario mounted inside the existing Defend
plane (``killinchu_defend_plane``).  It reuses the plane's session scope,
SQLite store and append-only receipt chain; it is not a separate product.

Flow::

    synthetic observations -> evidence binding (source, sha256, capture time)
    -> scripted finding adapter (model id/revision + prompt revision bound)
    -> synthetic checklist retrieval with citations
    -> recommendation with heuristic uncertainty, or ABSTAIN
    -> modeled ``maintenance_review_ticket`` proposal
    -> simulated independent approval -> rehearsal only -> receipts

Truth labels carried in every payload:

* evidence and checklist are SYNTHETIC fixtures;
* findings come from a SCRIPTED deterministic rule table, not a model call;
* requester/approver identities are SIMULATED roster labels supplied by the
  caller, not authenticated principals;
* the ticket is MODELED: no ticketing system is called, nothing is actuated;
* receipts are the plane's hash chain with optional HMAC; they are not DSSE
  envelopes and production readiness stays false.

Nothing here accepts commands, URLs, credentials, device or vehicle controls,
or any targeting input.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

import killinchu_defend_plane as plane

SCENARIO = "civilian_roof_building_inspection"
SCENARIO_VERSION = "1.0.0"
ACTION_TYPE = "maintenance_review_ticket"
INSPECTION_ACTIONS = frozenset({ACTION_TYPE})
DATA_CLASS = "SYNTHETIC_FIXTURE"
SOURCE_KINDS = frozenset(
    {"fixture_photo_descriptor", "fixture_inspector_note", "fixture_moisture_reading"}
)
REQUEST_FIELDS = frozenset({"inspection_id", "site_ref", "requested_by", "data_class", "observations"})
OBSERVATION_FIELDS = frozenset(
    {"observation_id", "source_kind", "source_ref", "captured_at", "content", "sha256"}
)
MAX_OBSERVATIONS = 12
MAX_CONTENT_CHARS = 2000
MAX_EVIDENCE_AGE = timedelta(days=30)
MAX_CLOCK_SKEW = timedelta(minutes=5)
PROPOSAL_TTL = timedelta(minutes=15)
MIN_SUPPORT = 2
MIN_CONFIDENCE = 0.60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASSESSMENT_ID_RE = re.compile(r"^insa_[0-9a-f]{32}$")
INSPECTION_PROPOSAL_ID_RE = re.compile(r"^iprop_[0-9a-f]{32}$")

# ---------------------------------------------------------------------------
# Simulated identities.  These are caller-supplied labels checked against a
# fixed roster; nothing authenticates them.  See issue #399 for the real gate.
# ---------------------------------------------------------------------------
SIMULATED_ROSTER: dict[str, tuple[str, ...]] = {
    "simulated/requester-ana": ("requester",),
    "simulated/requester-ben": ("requester",),
    "simulated/approver-cruz": ("approver",),
    "simulated/approver-dee": ("approver", "requester"),
    "simulated/auditor-eli": ("auditor",),
}
IDENTITY_MODE = "SIMULATED_ROSTER_LABEL_NOT_AUTHENTICATED"

# ---------------------------------------------------------------------------
# Synthetic checklist.  Written for this demo; it is not a building code,
# standard, manufacturer instruction or insurer requirement.
# ---------------------------------------------------------------------------
CHECKLIST: dict[str, Any] = {
    "checklist_id": "synthetic-roof-envelope-checklist",
    "version": "2026-10-20.1",
    "synthetic": True,
    "label": (
        "SYNTHETIC demo checklist - not a building code, standard, "
        "manufacturer instruction or insurer requirement"
    ),
    "items": [
        {
            "item_id": "SYN-RF-01",
            "title": "Roof covering displacement",
            "finding_codes": ["ROOF_COVERING_DISPLACED"],
            "priority": "HIGH",
            "text": (
                "Missing, lifted or displaced shingles or membrane sections are "
                "recorded with location and referred for maintenance review."
            ),
        },
        {
            "item_id": "SYN-RF-02",
            "title": "Flashing separation",
            "finding_codes": ["FLASHING_SEPARATED"],
            "priority": "HIGH",
            "text": (
                "Flashing separated from chimneys, walls or roof penetrations is "
                "referred for maintenance review."
            ),
        },
        {
            "item_id": "SYN-RF-03",
            "title": "Ponding water",
            "finding_codes": ["PONDING_WATER"],
            "priority": "MEDIUM",
            "text": (
                "Standing water on low-slope areas after the expected drainage time "
                "is recorded with location and referred for review."
            ),
        },
        {
            "item_id": "SYN-RF-04",
            "title": "Gutter and drain obstruction",
            "finding_codes": ["DRAIN_OBSTRUCTED"],
            "priority": "MEDIUM",
            "text": (
                "Blocked gutters, scuppers or roof drains are referred for "
                "cleaning review before the next rainfall."
            ),
        },
        {
            "item_id": "SYN-BE-01",
            "title": "Interior moisture indication",
            "finding_codes": ["MOISTURE_ELEVATED"],
            "priority": "HIGH",
            "text": (
                "Elevated interior moisture below a roof area suggests a possible "
                "leak; pair it with exterior observations before referral."
            ),
        },
        {
            "item_id": "SYN-BE-02",
            "title": "Facade cracking",
            "finding_codes": ["FACADE_CRACK"],
            "priority": "MEDIUM",
            "text": (
                "Visible facade or parapet cracks are photographed with scale and "
                "referred for maintenance review."
            ),
        },
        {
            "item_id": "SYN-GEN-01",
            "title": "Evidence sufficiency",
            "finding_codes": [],
            "priority": "INFO",
            "text": (
                "A referral needs at least two independent, current observations "
                "that agree; otherwise collect more evidence."
            ),
        },
    ],
}
CHECKLIST_ITEMS = {item["item_id"]: item for item in CHECKLIST["items"]}
CHECKLIST_REVISION = plane._sha256(plane._canonical(CHECKLIST))
PRIORITY_ORDER = {"INFO": 0, "MEDIUM": 1, "HIGH": 2}

# ---------------------------------------------------------------------------
# Scripted finding adapter.  A deterministic rule table stands in for a vision
# or language model so the demo is reproducible offline.  Its outputs are
# labeled SCRIPTED everywhere.  A real adapter would implement the same
# interface (model_id, model_revision, prompt_revision, infer()).
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = (
    "You review one civilian roof or building-envelope observation. Return only "
    "finding codes from this list: {codes}. Report NO_DEFECT_OBSERVED when the "
    "observation states the area is intact. Do not infer beyond the observation."
)
SCRIPTED_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ROOF_COVERING_DISPLACED", ("missing shingle", "lifted shingle", "displaced shingle", "membrane lifted", "membrane tear")),
    ("FLASHING_SEPARATED", ("flashing separated", "flashing gap", "loose flashing")),
    ("PONDING_WATER", ("ponding", "standing water")),
    ("DRAIN_OBSTRUCTED", ("drain blocked", "gutter blocked", "debris in drain", "clogged gutter")),
    ("MOISTURE_ELEVATED", ("moisture elevated", "wet reading", "damp ceiling", "water stain")),
    ("FACADE_CRACK", ("facade crack", "wall crack", "parapet crack")),
)
NO_DEFECT_PHRASES = ("no visible damage", "no damage observed", "roof intact", "moisture normal", "dry reading")
NO_DEFECT = "NO_DEFECT_OBSERVED"
SOURCE_CONFIDENCE = {
    "fixture_photo_descriptor": 0.80,
    "fixture_inspector_note": 0.70,
    "fixture_moisture_reading": 0.75,
}
QUALITY_PENALTIES = (("blurry", 0.5), ("low light", 0.6), ("possible", 0.6), ("unclear", 0.5))
DEFECT_CODES = frozenset(code for code, _ in SCRIPTED_RULES)


class InspectionServiceFailure(RuntimeError):
    """The finding adapter failed; the assessment fails closed (ABSTAIN)."""

    def __init__(self, message: str, receipt: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.receipt = receipt


class UnauthorizedApprover(Exception):
    """The approver label is not an approver in the simulated roster."""


class ScriptedInspectionAdapter:
    """Deterministic keyword rules; no network and no model call."""

    model_id = "killinchu/inspection-scripted-rules"
    inference_mode = "SCRIPTED_RULES_NO_MODEL_CALL"
    output_label = "SCRIPTED"

    @property
    def model_revision(self) -> str:
        return plane._sha256(
            plane._canonical(
                {
                    "rules": [[code, list(words)] for code, words in SCRIPTED_RULES],
                    "no_defect": list(NO_DEFECT_PHRASES),
                    "source_confidence": SOURCE_CONFIDENCE,
                    "penalties": [list(item) for item in QUALITY_PENALTIES],
                }
            )
        )

    @property
    def prompt_revision(self) -> str:
        return plane._sha256(PROMPT_TEMPLATE.encode("utf-8"))

    def binding(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "prompt_revision": self.prompt_revision,
            "prompt_applied": False,
            "inference_mode": self.inference_mode,
            "output_label": self.output_label,
        }

    def infer(self, observation: dict[str, Any]) -> list[dict[str, Any]]:
        text = observation["content"].lower()
        base = SOURCE_CONFIDENCE[observation["source_kind"]]
        for phrase, factor in QUALITY_PENALTIES:
            if phrase in text:
                base *= factor
        findings: list[dict[str, Any]] = []
        for code, phrases in SCRIPTED_RULES:
            hit = next((phrase for phrase in phrases if phrase in text), None)
            if hit is not None:
                findings.append(
                    {"finding_code": code, "confidence": round(base, 4), "matched_phrase": hit}
                )
        negation = next((phrase for phrase in NO_DEFECT_PHRASES if phrase in text), None)
        if negation is not None:
            findings.append(
                {"finding_code": NO_DEFECT, "confidence": round(base, 4), "matched_phrase": negation}
            )
        return [
            {**item, "observation_id": observation["observation_id"], "output_label": self.output_label}
            for item in findings
        ]


_ADAPTER_FACTORY: Callable[[], Any] = ScriptedInspectionAdapter


def _adapter() -> Any:
    return _ADAPTER_FACTORY()


def _now() -> datetime:
    return plane._utcnow()


def _parse_time(value: str, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError(f"{field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    try:
        return parsed.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError(f"{field} is outside the supported time range") from exc


# ---------------------------------------------------------------------------
# Request normalization and evidence binding
# ---------------------------------------------------------------------------
def normalize_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    unknown = set(value) - REQUEST_FIELDS
    if unknown:
        raise ValueError(f"unsupported fields: {sorted(unknown)}")
    if value.get("data_class") != DATA_CLASS:
        raise ValueError(f"data_class must be {DATA_CLASS}; this demo accepts synthetic fixtures only")
    requested_by = plane._bounded_identifier(value.get("requested_by"), "requested_by")
    observations = value.get("observations")
    if not isinstance(observations, list) or len(observations) > MAX_OBSERVATIONS:
        raise ValueError(f"observations must be a list of at most {MAX_OBSERVATIONS} items")
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in observations:
        if not isinstance(raw, dict) or set(raw) != OBSERVATION_FIELDS:
            raise ValueError(f"each observation must contain exactly {sorted(OBSERVATION_FIELDS)}")
        observation_id = plane._bounded_identifier(raw["observation_id"], "observation_id")
        if observation_id in seen:
            raise ValueError("observation_id values must be unique")
        seen.add(observation_id)
        if not isinstance(raw["source_kind"], str) or raw["source_kind"] not in SOURCE_KINDS:
            raise ValueError(f"unsupported source_kind: {raw['source_kind']!r}")
        content = raw["content"]
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_CONTENT_CHARS:
            raise ValueError(f"content must contain 1-{MAX_CONTENT_CHARS} characters")
        declared = raw["sha256"]
        if not isinstance(declared, str) or SHA256_RE.fullmatch(declared) is None:
            raise ValueError("sha256 must be 64 lowercase hex characters")
        _parse_time(raw["captured_at"], "captured_at")
        clean.append(
            {
                "observation_id": observation_id,
                "source_kind": raw["source_kind"],
                "source_ref": plane._bounded_identifier(raw["source_ref"], "source_ref"),
                "captured_at": raw["captured_at"],
                "content": content,
                "sha256": declared,
            }
        )
    return {
        "inspection_id": plane._bounded_identifier(value.get("inspection_id"), "inspection_id"),
        "site_ref": plane._bounded_identifier(value.get("site_ref"), "site_ref"),
        "requested_by": requested_by,
        "data_class": DATA_CLASS,
        "observations": clean,
    }


def bind_evidence(observation: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Bind source, content hash and capture time; classify integrity/freshness."""
    computed = plane._sha256(observation["content"].encode("utf-8"))
    captured = _parse_time(observation["captured_at"], "captured_at")
    age = now - captured
    if age < -MAX_CLOCK_SKEW:
        freshness = "FUTURE_DATED"
    elif age > MAX_EVIDENCE_AGE:
        freshness = "STALE"
    else:
        freshness = "CURRENT"
    return {
        "observation_id": observation["observation_id"],
        "source_kind": observation["source_kind"],
        "source_ref": observation["source_ref"],
        "captured_at": observation["captured_at"],
        "declared_sha256": observation["sha256"],
        "computed_sha256": computed,
        "sha256_verified": computed == observation["sha256"],
        "age_hours": round(age.total_seconds() / 3600.0, 3),
        "freshness": freshness,
        "data_class": DATA_CLASS,
    }


def retrieve_checklist(finding_code: str) -> list[dict[str, Any]]:
    """Exact finding-code retrieval over the bundled synthetic checklist."""
    return [
        {
            "checklist_id": CHECKLIST["checklist_id"],
            "checklist_version": CHECKLIST["version"],
            "checklist_revision": CHECKLIST_REVISION,
            "item_id": item["item_id"],
            "title": item["title"],
            "quote": item["text"],
            "synthetic": True,
        }
        for item in CHECKLIST["items"]
        if finding_code in item["finding_codes"]
    ]


def grounding_errors(recommendation: dict[str, Any] | None, evidence: list[dict[str, Any]]) -> list[str]:
    """Check every claim cites a matching checklist item and verified evidence."""
    if not recommendation:
        return []
    verified = {item["observation_id"] for item in evidence if item["sha256_verified"]}
    errors: list[str] = []
    for claim in recommendation.get("claims", []):
        code = claim.get("finding_code")
        citations = claim.get("citations") or []
        if not citations:
            errors.append(f"{code}: no checklist citation")
        for citation in citations:
            item = CHECKLIST_ITEMS.get(citation.get("item_id"))
            if item is None:
                errors.append(f"{code}: cites unknown item {citation.get('item_id')}")
            elif code not in item["finding_codes"]:
                errors.append(f"{code}: cited item {item['item_id']} does not cover this finding")
            elif citation.get("quote") != item["text"] or citation.get("checklist_revision") != CHECKLIST_REVISION:
                errors.append(f"{code}: citation text or revision does not match the checklist")
        support = claim.get("evidence") or []
        if not support:
            errors.append(f"{code}: no evidence reference")
        for observation_id in support:
            if observation_id not in verified:
                errors.append(f"{code}: evidence {observation_id} is not hash-verified")
    return errors


def _interval(confidence: float, support: int) -> list[float]:
    half = 0.25 / math.sqrt(max(1, support))
    return [round(max(0.0, confidence - half), 4), round(min(1.0, confidence + half), 4)]


def assess(observations: list[dict[str, Any]], now: datetime, adapter: Any) -> dict[str, Any]:
    """Pure assessment.  Raises InspectionServiceFailure if the adapter fails."""
    evidence = [bind_evidence(item, now) for item in observations]
    model = adapter.binding()
    base = {
        "evidence": evidence,
        "model": model,
        "checklist": {
            "checklist_id": CHECKLIST["checklist_id"],
            "version": CHECKLIST["version"],
            "revision": CHECKLIST_REVISION,
            "synthetic": True,
        },
        "thresholds": {
            "min_support": MIN_SUPPORT,
            "min_confidence": MIN_CONFIDENCE,
            "max_evidence_age_days": MAX_EVIDENCE_AGE.days,
        },
        "uncertainty_method": "HEURISTIC_UNCALIBRATED",
    }

    def abstain(reasons: list[str], findings: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
        return {
            **base,
            "decision": "ABSTAIN",
            "abstain_reasons": reasons,
            "findings": findings or [],
            "recommendation": None,
            "grounding_errors": [],
            "next_step": "Collect current, independent, unmodified observations and resubmit.",
            **extra,
        }

    if not evidence:
        return abstain(["MISSING_EVIDENCE"])
    modified = [item["observation_id"] for item in evidence if not item["sha256_verified"]]
    if modified:
        return abstain(["EVIDENCE_INTEGRITY_FAILED"], modified_observations=modified)
    stale = [item["observation_id"] for item in evidence if item["freshness"] != "CURRENT"]
    if stale:
        return abstain(["STALE_EVIDENCE"], stale_observations=stale)

    # Support is counted over distinct content hashes, so the same observation
    # resubmitted under another observation_id is not independent support.
    content_of = {item["observation_id"]: item["computed_sha256"] for item in evidence}

    def independent(items: list[dict[str, Any]]) -> int:
        return len({content_of[f["observation_id"]] for f in items})

    findings: list[dict[str, Any]] = []
    try:
        for observation in observations:
            findings.extend(adapter.infer(observation))
    except Exception as exc:  # any adapter fault fails closed
        raise InspectionServiceFailure(f"finding adapter failed: {type(exc).__name__}") from None

    by_code: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        if finding.get("finding_code") not in DEFECT_CODES | {NO_DEFECT}:
            raise InspectionServiceFailure("finding adapter returned an unsupported finding code")
        by_code.setdefault(finding["finding_code"], []).append(finding)
    defects = {code: items for code, items in by_code.items() if code in DEFECT_CODES}
    negations = by_code.get(NO_DEFECT, [])

    if defects and negations:
        return abstain(
            ["CONFLICTING_EVIDENCE"],
            findings,
            conflict={
                "defect_observations": sorted({f["observation_id"] for items in defects.values() for f in items}),
                "no_defect_observations": sorted({f["observation_id"] for f in negations}),
            },
        )
    if not defects:
        if independent(negations) >= MIN_SUPPORT:
            return {
                **base,
                "decision": "NO_REFERRAL",
                "abstain_reasons": [],
                "findings": findings,
                "recommendation": None,
                "grounding_errors": [],
                "next_step": "No maintenance review proposed; observations agree the area is intact.",
            }
        return abstain(["INSUFFICIENT_EVIDENCE"], findings)

    claims: list[dict[str, Any]] = []
    unconfirmed: list[dict[str, Any]] = []
    for code in sorted(defects):
        items = defects[code]
        support = sorted({f["observation_id"] for f in items})
        mean = statistics.fmean(f["confidence"] for f in items)
        distinct = independent(items)
        confidence = round(mean * min(1.0, distinct / MIN_SUPPORT), 4)
        record = {
            "finding_code": code,
            "confidence": confidence,
            "uncertainty": round(1.0 - confidence, 4),
            "interval": _interval(confidence, distinct),
            "evidence": support,
        }
        if distinct >= MIN_SUPPORT and confidence >= MIN_CONFIDENCE:
            claims.append({**record, "citations": retrieve_checklist(code)})
        else:
            unconfirmed.append(record)
    if not claims:
        return abstain(["INSUFFICIENT_EVIDENCE"], findings, unconfirmed=unconfirmed)
    if any(not claim["citations"] for claim in claims):
        return abstain(["INSUFFICIENT_GROUNDING"], findings, unconfirmed=unconfirmed)
    priority = max(
        (CHECKLIST_ITEMS[c["item_id"]]["priority"] for claim in claims for c in claim["citations"]),
        key=PRIORITY_ORDER.__getitem__,
    )
    recommendation = {
        "action_type": ACTION_TYPE,
        "priority": priority,
        "claims": claims,
        "unconfirmed": unconfirmed,
        "summary": "Refer for human maintenance review: " + ", ".join(c["finding_code"] for c in claims),
        "output_label": model["output_label"],
    }
    errors = grounding_errors(recommendation, evidence)
    if errors:
        return abstain(["GROUNDING_CHECK_FAILED"], findings, grounding_errors=errors)
    return {
        **base,
        "decision": "RECOMMEND_REVIEW",
        "abstain_reasons": [],
        "findings": findings,
        "recommendation": recommendation,
        "grounding_errors": [],
        "next_step": "An independent approver may approve a rehearsal of the modeled ticket.",
    }


def baseline_assess(observations: list[dict[str, Any]], now: datetime, adapter: Any) -> dict[str, Any]:
    """Trivial baseline: recommend on any defect keyword, cite the first item, never abstain."""
    evidence = [bind_evidence(item, now) for item in observations]
    findings = [f for observation in observations for f in adapter.infer(observation)]
    defects = sorted({f["finding_code"] for f in findings if f["finding_code"] in DEFECT_CODES})
    if not defects:
        return {"decision": "NO_REFERRAL", "recommendation": None, "evidence": evidence, "grounding_errors": []}
    first = CHECKLIST["items"][0]
    recommendation = {
        "action_type": ACTION_TYPE,
        "claims": [
            {
                "finding_code": code,
                "evidence": [o["observation_id"] for o in observations],
                "citations": [
                    {
                        "item_id": first["item_id"],
                        "quote": first["text"],
                        "checklist_revision": CHECKLIST_REVISION,
                    }
                ],
            }
            for code in defects
        ],
    }
    return {
        "decision": "RECOMMEND_REVIEW",
        "recommendation": recommendation,
        "evidence": evidence,
        "grounding_errors": grounding_errors(recommendation, evidence),
    }


# ---------------------------------------------------------------------------
# Synthetic fixtures (used by the demo UI and the measured comparison)
# ---------------------------------------------------------------------------
def _obs(observation_id: str, kind: str, ref: str, content: str, captured: datetime, *, tamper: bool = False) -> dict[str, Any]:
    digest = plane._sha256(content.encode("utf-8"))
    return {
        "observation_id": observation_id,
        "source_kind": kind,
        "source_ref": ref,
        "captured_at": plane._rfc3339(captured),
        "content": content + (" [edited after capture]" if tamper else ""),
        "sha256": digest,
    }


PHOTO = "fixture_photo_descriptor"
NOTE = "fixture_inspector_note"
METER = "fixture_moisture_reading"
FIXTURE_SPECS: dict[str, dict[str, Any]] = {
    "happy_displaced_shingles": {
        "expected": "RECOMMEND_REVIEW",
        "obs": [
            (PHOTO, "Synthetic photo descriptor, north slope: three missing shingle tabs near ridge.", 2, False),
            (NOTE, "Synthetic inspector note: lifted shingle row and missing shingle tabs on north slope.", 3, False),
        ],
    },
    "flashing_with_moisture": {
        "expected": "RECOMMEND_REVIEW",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: flashing separated at chimney base, 2 cm gap.", 4, False),
            (NOTE, "Synthetic inspector note: loose flashing on chimney west side.", 4, False),
            (METER, "Synthetic meter reading: moisture elevated on top-floor ceiling below chimney.", 5, False),
        ],
    },
    "ponding_low_slope": {
        "expected": "RECOMMEND_REVIEW",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: ponding across 4 m2 of low-slope membrane.", 24, False),
            (PHOTO, "Synthetic photo descriptor, second angle: standing water near east scupper.", 24, False),
        ],
    },
    "drain_blocked": {
        "expected": "RECOMMEND_REVIEW",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: debris in drain at south scupper.", 6, False),
            (NOTE, "Synthetic inspector note: gutter blocked along south eave.", 6, False),
        ],
    },
    "weak_single_blurry_photo": {
        "expected": "ABSTAIN",
        "obs": [(PHOTO, "Synthetic photo descriptor (blurry): possible missing shingle near valley.", 2, False)],
    },
    "weak_possible_wording": {
        "expected": "ABSTAIN",
        "obs": [
            (PHOTO, "Synthetic photo descriptor, low light: possible wall crack at parapet.", 2, False),
            (NOTE, "Synthetic inspector note: unclear, possible facade crack, not confirmed.", 2, False),
        ],
    },
    "conflicting_photo_vs_note": {
        "expected": "ABSTAIN",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: membrane tear near HVAC curb.", 3, False),
            (NOTE, "Synthetic inspector note: roof intact, no visible damage at HVAC curb.", 3, False),
        ],
    },
    "stale_photos": {
        "expected": "ABSTAIN",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: missing shingle tabs on south slope.", 24 * 40, False),
            (NOTE, "Synthetic inspector note: displaced shingle row on south slope.", 24 * 41, False),
        ],
    },
    "future_dated_capture": {
        "expected": "ABSTAIN",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: ponding on low-slope roof.", -48, False),
            (NOTE, "Synthetic inspector note: standing water on low-slope roof.", 2, False),
        ],
    },
    "modified_evidence": {
        "expected": "ABSTAIN",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: flashing separated at skylight curb.", 2, True),
            (NOTE, "Synthetic inspector note: flashing gap at skylight.", 2, False),
        ],
    },
    "missing_evidence": {"expected": "ABSTAIN", "obs": []},
    "intact_roof": {
        "expected": "NO_REFERRAL",
        "obs": [
            (PHOTO, "Synthetic photo descriptor: roof intact, no visible damage on any slope.", 2, False),
            (NOTE, "Synthetic inspector note: no damage observed; gutters clear.", 2, False),
        ],
    },
}


def fixture_request(name: str, now: datetime | None = None, *, requested_by: str = "simulated/requester-ana") -> dict[str, Any]:
    spec = FIXTURE_SPECS.get(name)
    if spec is None:
        raise LookupError("unknown synthetic fixture")
    now = now or _now()
    observations = [
        _obs(
            f"obs-{index + 1}",
            kind,
            f"fixture/{name}/{index + 1}",
            content,
            now - timedelta(hours=hours),
            tamper=tamper,
        )
        for index, (kind, content, hours, tamper) in enumerate(spec["obs"])
    ]
    return {
        "inspection_id": f"insp-{name.replace('_', '-')}",
        "site_ref": f"site/synthetic-{name.replace('_', '-')}",
        "requested_by": requested_by,
        "data_class": DATA_CLASS,
        "observations": observations,
    }


def compare_with_baseline(repeats: int = 20, now: datetime | None = None) -> dict[str, Any]:
    """Measured, in-process comparison on the bundled synthetic fixtures."""
    now = now or _now()
    adapter = ScriptedInspectionAdapter()
    systems = {"governed": assess, "baseline": baseline_assess}
    report: dict[str, Any] = {}
    for name, function in systems.items():
        rows = []
        latencies: list[float] = []
        for fixture, spec in FIXTURE_SPECS.items():
            observations = fixture_request(fixture, now)["observations"]
            result = None
            for _ in range(max(1, repeats)):
                started = time.perf_counter()
                result = function(observations, now, adapter)
                latencies.append((time.perf_counter() - started) * 1000.0)
            assert result is not None
            rows.append(
                {
                    "fixture": fixture,
                    "expected": spec["expected"],
                    "decision": result["decision"],
                    "match": result["decision"] == spec["expected"],
                    "grounding_errors": len(result["grounding_errors"]) if result["decision"] == "RECOMMEND_REVIEW" else 0,
                }
            )
        count = len(rows)
        latencies.sort()
        report[name] = {
            "fixtures": count,
            "decision_match_rate": round(sum(r["match"] for r in rows) / count, 4),
            "abstention_rate": round(sum(r["decision"] == "ABSTAIN" for r in rows) / count, 4),
            "unsafe_recommendations": sum(
                r["decision"] == "RECOMMEND_REVIEW" and r["expected"] != "RECOMMEND_REVIEW" for r in rows
            ),
            "grounding_errors": sum(r["grounding_errors"] for r in rows),
            "latency_ms_p50": round(statistics.median(latencies), 4),
            "latency_ms_max": round(latencies[-1], 4),
            "rows": rows,
        }
    return {
        "schema": "szl.killinchu.defend-inspection-comparison/v1",
        "truth_label": "MEASURED_ON_SYNTHETIC_FIXTURES",
        "fixture_count": len(FIXTURE_SPECS),
        "repeats_per_fixture": max(1, repeats),
        "baseline": "Recommend on any defect keyword, cite the first checklist item, never abstain.",
        "limits": [
            "Expected decisions were authored with the rules; this measures rule conformance, not real-world accuracy.",
            "Findings are SCRIPTED keyword rules; no model was evaluated.",
            "Latency is in-process wall time on the serving host, excluding storage and network.",
            "No comparison with any external or published system is made.",
        ],
        "systems": report,
    }


# ---------------------------------------------------------------------------
# Storage: extends the Defend store; shares its session-scoped receipt chain.
# ---------------------------------------------------------------------------
_STORES: dict[str, "InspectionStore"] = {}
_STORES_LOCK = threading.RLock()


class InspectionStore(plane.DefendStore):
    def _migrate(self) -> None:
        super()._migrate()
        with self._lock:
            connection = self.connect()
            try:
                connection.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS inspection_assessments (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        inspection_id TEXT NOT NULL,
                        site_ref TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        request_hash TEXT NOT NULL,
                        assessment_json TEXT NOT NULL,
                        assessment_hash TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(scope, inspection_id)
                    );
                    CREATE TABLE IF NOT EXISTS inspection_evidence (
                        assessment_id TEXT NOT NULL REFERENCES inspection_assessments(id),
                        scope TEXT NOT NULL,
                        observation_id TEXT NOT NULL,
                        source_kind TEXT NOT NULL,
                        source_ref TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        content TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        PRIMARY KEY(assessment_id, observation_id)
                    );
                    CREATE TABLE IF NOT EXISTS inspection_proposals (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        assessment_id TEXT NOT NULL UNIQUE REFERENCES inspection_assessments(id),
                        action_type TEXT NOT NULL,
                        site_ref TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        parameters_json TEXT NOT NULL,
                        binding_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        proposal_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS inspection_approvals (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        proposal_id TEXT NOT NULL UNIQUE REFERENCES inspection_proposals(id),
                        approver TEXT NOT NULL,
                        identity_json TEXT NOT NULL,
                        approval_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS inspection_rehearsals (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        proposal_id TEXT NOT NULL UNIQUE REFERENCES inspection_proposals(id),
                        result_json TEXT NOT NULL,
                        result_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    COMMIT;
                    """
                )
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _proposal_basis(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "assessment_id": row["assessment_id"],
            "action_type": row["action_type"],
            "site_ref": row["site_ref"],
            "requested_by": row["requested_by"],
            "parameters": json.loads(str(row["parameters_json"])),
            "binding": json.loads(str(row["binding_json"])),
            "expires_at": row["expires_at"],
        }

    def _binding_problems(self, connection: sqlite3.Connection, scope: str, proposal: sqlite3.Row) -> list[str]:
        problems: list[str] = []
        if plane._sha256(plane._canonical(self._proposal_basis(proposal))) != str(proposal["proposal_hash"]):
            problems.append("PROPOSAL_HASH_MISMATCH")
        binding = json.loads(str(proposal["binding_json"]))
        assessment = connection.execute(
            "SELECT * FROM inspection_assessments WHERE scope=? AND id=?",
            (scope, str(proposal["assessment_id"])),
        ).fetchone()
        if assessment is None or plane._sha256(str(assessment["assessment_json"]).encode("utf-8")) != binding.get(
            "assessment_hash"
        ) or str(assessment["assessment_hash"]) != binding.get("assessment_hash"):
            problems.append("ASSESSMENT_HASH_MISMATCH")
        stored = {
            str(row["observation_id"]): row
            for row in connection.execute(
                "SELECT * FROM inspection_evidence WHERE scope=? AND assessment_id=?",
                (scope, str(proposal["assessment_id"])),
            ).fetchall()
        }
        bound = {item["observation_id"]: item for item in binding.get("evidence", [])}
        if set(stored) != set(bound):
            problems.append("EVIDENCE_SET_MISMATCH")
        for observation_id, item in bound.items():
            row = stored.get(observation_id)
            if row is None:
                continue
            if plane._sha256(str(row["content"]).encode("utf-8")) != item["sha256"] or str(row["sha256"]) != item["sha256"]:
                problems.append(f"EVIDENCE_MODIFIED:{observation_id}")
            if str(row["captured_at"]) != item["captured_at"] or str(row["source_ref"]) != item["source_ref"]:
                problems.append(f"EVIDENCE_METADATA_MODIFIED:{observation_id}")
        return problems

    def _quarantine(self, connection, scope, proposal, problems) -> dict[str, Any]:
        connection.execute(
            "UPDATE inspection_proposals SET state='QUARANTINED' WHERE scope=? AND id=?",
            (scope, str(proposal["id"])),
        )
        return self._receipt(
            connection,
            scope=scope,
            kind="INSPECTION_BINDING_MISMATCH",
            object_id=str(proposal["id"]),
            payload={"proposal_id": str(proposal["id"]), "problems": problems, "decision": "QUARANTINE"},
        )

    # -- workflow ----------------------------------------------------------
    def assess_and_propose(self, scope: str, request: dict[str, Any], now: datetime, adapter: Any) -> dict[str, Any]:
        request_hash = plane._sha256(plane._canonical(request))
        replay = self._replay_or_collision(scope, request, request_hash)
        if replay is not None:
            return replay
        try:
            assessment = assess(request["observations"], now, adapter)
        except InspectionServiceFailure as exc:
            with self._lock:
                connection = self.connect()
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    receipt = self._receipt(
                        connection,
                        scope=scope,
                        kind="INSPECTION_SERVICE_FAILURE",
                        object_id=plane._stable_id("insa", scope, request["inspection_id"], request_hash),
                        payload={
                            "inspection_id": request["inspection_id"],
                            "request_hash": request_hash,
                            "decision": "ABSTAIN",
                            "reason": "MODEL_SERVICE_UNAVAILABLE",
                            "detail": str(exc),
                            "persisted_assessment": False,
                        },
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.close()
            raise InspectionServiceFailure(str(exc), receipt) from None

        with self._lock:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute(
                    "SELECT 1 FROM inspection_assessments WHERE scope=? AND inspection_id=?",
                    (scope, request["inspection_id"]),
                ).fetchone():
                    # A concurrent writer won the race; answer as replay/collision.
                    connection.rollback()
                    raced = True
                else:
                    raced = False
                if raced:
                    replay = self._replay_or_collision(scope, request, request_hash)
                    if replay is None:
                        raise RuntimeError("inspection state changed during assessment")
                    return replay
                created = plane._rfc3339(now)
                assessment_id = plane._stable_id("insa", scope, request["inspection_id"], request_hash)
                assessment_json = plane._canonical(assessment).decode("utf-8")
                assessment_hash = plane._sha256(assessment_json.encode("utf-8"))
                connection.execute(
                    "INSERT INTO inspection_assessments VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        assessment_id, scope, request["inspection_id"], request["site_ref"],
                        request["requested_by"], request_hash, assessment_json, assessment_hash,
                        assessment["decision"], created,
                    ),
                )
                for observation in request["observations"]:
                    connection.execute(
                        "INSERT INTO inspection_evidence VALUES(?,?,?,?,?,?,?,?)",
                        (
                            assessment_id, scope, observation["observation_id"], observation["source_kind"],
                            observation["source_ref"], observation["captured_at"], observation["content"],
                            observation["sha256"],
                        ),
                    )
                proposal_public = None
                if assessment["decision"] == "RECOMMEND_REVIEW":
                    proposal_public = self._insert_proposal(
                        connection, scope, request, assessment, assessment_id, assessment_hash, now
                    )
                receipt = self._receipt(
                    connection,
                    scope=scope,
                    kind="INSPECTION_ASSESSMENT",
                    object_id=assessment_id,
                    payload={
                        "scenario": SCENARIO,
                        "assessment_id": assessment_id,
                        "inspection_id": request["inspection_id"],
                        "request_hash": request_hash,
                        "assessment_hash": assessment_hash,
                        "decision": assessment["decision"],
                        "abstain_reasons": assessment["abstain_reasons"],
                        "evidence": [
                            {k: e[k] for k in ("observation_id", "source_ref", "captured_at", "computed_sha256", "freshness")}
                            for e in assessment["evidence"]
                        ],
                        "model": assessment["model"],
                        "checklist_revision": CHECKLIST_REVISION,
                        "proposal_id": proposal_public["id"] if proposal_public else None,
                        "proposal_hash": proposal_public["proposal_hash"] if proposal_public else None,
                        "data_class": DATA_CLASS,
                    },
                )
                connection.commit()
                return {
                    "replayed": False,
                    "assessment_id": assessment_id,
                    "assessment_hash": assessment_hash,
                    "assessment": assessment,
                    "proposal": proposal_public,
                    "receipt": receipt,
                }
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _insert_proposal(self, connection, scope, request, assessment, assessment_id, assessment_hash, now) -> dict[str, Any]:
        recommendation = assessment["recommendation"]
        parameters = {
            "mode": "REHEARSAL_ONLY",
            "priority": recommendation["priority"],
            "claims": recommendation["claims"],
            "ticket_system": "NONE_MODELED",
            "physical_actuation": False,
            "external_effectors": False,
        }
        binding = {
            "assessment_hash": assessment_hash,
            "evidence": [
                {
                    "observation_id": e["observation_id"],
                    "source_kind": e["source_kind"],
                    "source_ref": e["source_ref"],
                    "captured_at": e["captured_at"],
                    "sha256": e["computed_sha256"],
                }
                for e in assessment["evidence"]
            ],
            "model": assessment["model"],
            "checklist_revision": CHECKLIST_REVISION,
        }
        row = {
            "assessment_id": assessment_id,
            "action_type": ACTION_TYPE,
            "site_ref": request["site_ref"],
            "requested_by": request["requested_by"],
            "parameters_json": plane._canonical(parameters).decode("utf-8"),
            "binding_json": plane._canonical(binding).decode("utf-8"),
            "expires_at": plane._rfc3339(now + PROPOSAL_TTL),
        }
        if row["action_type"] not in INSPECTION_ACTIONS:
            raise RuntimeError("internal action escaped inspection allowlist")
        proposal_hash = plane._sha256(plane._canonical(self._proposal_basis(row)))
        proposal_id = plane._stable_id("iprop", scope, assessment_id, ACTION_TYPE)
        created = plane._rfc3339(now)
        connection.execute(
            "INSERT INTO inspection_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal_id, scope, assessment_id, ACTION_TYPE, row["site_ref"], row["requested_by"],
                row["parameters_json"], row["binding_json"], "PROPOSED", proposal_hash, created, row["expires_at"],
            ),
        )
        return {
            "id": proposal_id,
            "action_type": ACTION_TYPE,
            "site_ref": row["site_ref"],
            "requested_by": row["requested_by"],
            "requester_identity_mode": IDENTITY_MODE,
            "parameters": parameters,
            "binding": binding,
            "state": "PROPOSED",
            "proposal_hash": proposal_hash,
            "expires_at": row["expires_at"],
            "can_execute": False,
        }

    def _replay_or_collision(self, scope: str, request: dict[str, Any], request_hash: str) -> dict[str, Any] | None:
        with self._lock:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM inspection_assessments WHERE scope=? AND inspection_id=?",
                    (scope, request["inspection_id"]),
                ).fetchone()
                if existing is None:
                    connection.rollback()
                    return None
                if str(existing["request_hash"]) != request_hash:
                    receipt = self._receipt(
                        connection,
                        scope=scope,
                        kind="INSPECTION_ID_COLLISION",
                        object_id=str(existing["id"]),
                        payload={
                            "inspection_id": request["inspection_id"],
                            "stored_request_hash": str(existing["request_hash"]),
                            "presented_request_hash": request_hash,
                            "decision": "QUARANTINE",
                        },
                    )
                    connection.commit()
                    return {"collision": True, "receipt": receipt}
                proposal = connection.execute(
                    "SELECT * FROM inspection_proposals WHERE scope=? AND assessment_id=?",
                    (scope, str(existing["id"])),
                ).fetchone()
                connection.commit()
                return {
                    "replayed": True,
                    "assessment_id": str(existing["id"]),
                    "assessment_hash": str(existing["assessment_hash"]),
                    "assessment": json.loads(str(existing["assessment_json"])),
                    "proposal": self._inspection_proposal_public(proposal),
                }
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _inspection_proposal_public(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "action_type": str(row["action_type"]),
            "site_ref": str(row["site_ref"]),
            "requested_by": str(row["requested_by"]),
            "requester_identity_mode": IDENTITY_MODE,
            "parameters": json.loads(str(row["parameters_json"])),
            "binding": json.loads(str(row["binding_json"])),
            "state": str(row["state"]),
            "proposal_hash": str(row["proposal_hash"]),
            "expires_at": str(row["expires_at"]),
            "can_execute": False,
        }

    def _load_proposal(self, connection, scope: str, proposal_id: str) -> sqlite3.Row:
        proposal = connection.execute(
            "SELECT * FROM inspection_proposals WHERE scope=? AND id=?",
            (scope, proposal_id),
        ).fetchone()
        if proposal is None:
            raise LookupError("inspection proposal not found in caller session")
        return proposal

    def approve_inspection(self, scope: str, proposal_id: str, approver: str, now: datetime) -> dict[str, Any]:
        roles = SIMULATED_ROSTER.get(approver)
        if roles is None or "approver" not in roles:
            raise UnauthorizedApprover("approver is not an approver in the simulated roster")
        with self._lock:
            connection = self.connect()
            failure: Exception | None = None
            try:
                connection.execute("BEGIN IMMEDIATE")
                proposal = self._load_proposal(connection, scope, proposal_id)
                if str(proposal["state"]) != "PROPOSED":
                    raise RuntimeError(f"proposal is not approvable: {proposal['state']}")
                if approver == str(proposal["requested_by"]):
                    raise PermissionError("approver must be independent from requester")
                expiry = datetime.fromisoformat(str(proposal["expires_at"]).replace("Z", "+00:00"))
                problems = self._binding_problems(connection, scope, proposal)
                if expiry <= now:
                    connection.execute(
                        "UPDATE inspection_proposals SET state='EXPIRED' WHERE scope=? AND id=?",
                        (scope, proposal_id),
                    )
                    self._receipt(
                        connection,
                        scope=scope,
                        kind="INSPECTION_PROPOSAL_EXPIRED",
                        object_id=proposal_id,
                        payload={"proposal_id": proposal_id, "expires_at": str(proposal["expires_at"]), "decision": "EXPIRED"},
                    )
                    failure = RuntimeError("proposal has expired")
                elif problems:
                    self._quarantine(connection, scope, proposal, problems)
                    failure = RuntimeError("evidence binding mismatch: " + ",".join(problems))
                if failure is not None:
                    connection.commit()
                    raise failure
                identity = {
                    "approver": approver,
                    "roles": list(roles),
                    "identity_mode": IDENTITY_MODE,
                    "authenticated": False,
                }
                approval_basis = {
                    "proposal_id": proposal_id,
                    "proposal_hash": str(proposal["proposal_hash"]),
                    "identity": identity,
                    "scope": scope,
                    "authority": "SIMULATED_HUMAN_REHEARSAL_APPROVAL",
                }
                approval_hash = plane._sha256(plane._canonical(approval_basis))
                approval_id = plane._stable_id("iappr", scope, proposal_id, approver)
                created = plane._rfc3339(now)
                connection.execute(
                    "INSERT INTO inspection_approvals VALUES(?,?,?,?,?,?,?)",
                    (approval_id, scope, proposal_id, approver, plane._canonical(identity).decode("utf-8"), approval_hash, created),
                )
                connection.execute(
                    "UPDATE inspection_proposals SET state='APPROVED_FOR_REHEARSAL' WHERE scope=? AND id=?",
                    (scope, proposal_id),
                )
                receipt = self._receipt(
                    connection,
                    scope=scope,
                    kind="INSPECTION_SIMULATED_APPROVAL",
                    object_id=approval_id,
                    payload={
                        "approval_id": approval_id,
                        "proposal_id": proposal_id,
                        "proposal_hash": str(proposal["proposal_hash"]),
                        "approval_hash": approval_hash,
                        "identity": identity,
                        "authority": "REHEARSAL_ONLY",
                    },
                )
                connection.commit()
                return {
                    "approval": {
                        "id": approval_id,
                        "proposal_id": proposal_id,
                        "approval_hash": approval_hash,
                        "identity": identity,
                        "authority": "REHEARSAL_ONLY",
                        "created_at": created,
                    },
                    "proposal_state": "APPROVED_FOR_REHEARSAL",
                    "can_execute_external_action": False,
                    "receipt": receipt,
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def rehearse_inspection(self, scope: str, proposal_id: str, now: datetime) -> dict[str, Any]:
        with self._lock:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                proposal = self._load_proposal(connection, scope, proposal_id)
                if str(proposal["state"]) != "APPROVED_FOR_REHEARSAL":
                    raise RuntimeError(f"proposal is not ready for rehearsal: {proposal['state']}")
                expiry = datetime.fromisoformat(str(proposal["expires_at"]).replace("Z", "+00:00"))
                if expiry <= now:
                    connection.execute(
                        "UPDATE inspection_proposals SET state='EXPIRED' WHERE scope=? AND id=?",
                        (scope, proposal_id),
                    )
                    self._receipt(
                        connection,
                        scope=scope,
                        kind="INSPECTION_PROPOSAL_EXPIRED",
                        object_id=proposal_id,
                        payload={"proposal_id": proposal_id, "expires_at": str(proposal["expires_at"]), "decision": "EXPIRED"},
                    )
                    connection.commit()
                    raise RuntimeError("proposal has expired")
                problems = self._binding_problems(connection, scope, proposal)
                approval = connection.execute(
                    "SELECT * FROM inspection_approvals WHERE scope=? AND proposal_id=?",
                    (scope, proposal_id),
                ).fetchone()
                if approval is None:
                    problems.append("APPROVAL_MISSING")
                else:
                    basis = {
                        "proposal_id": proposal_id,
                        "proposal_hash": str(proposal["proposal_hash"]),
                        "identity": json.loads(str(approval["identity_json"])),
                        "scope": scope,
                        "authority": "SIMULATED_HUMAN_REHEARSAL_APPROVAL",
                    }
                    if plane._sha256(plane._canonical(basis)) != str(approval["approval_hash"]):
                        problems.append("APPROVAL_HASH_MISMATCH")
                if problems:
                    self._quarantine(connection, scope, proposal, problems)
                    connection.commit()
                    raise RuntimeError("evidence binding mismatch: " + ",".join(problems))
                parameters = json.loads(str(proposal["parameters_json"]))
                binding = json.loads(str(proposal["binding_json"]))
                result = {
                    "mode": "REHEARSAL_ONLY",
                    "action_type": ACTION_TYPE,
                    "modeled_ticket": {
                        "ticket_ref": "MODELED-ONLY-" + str(proposal["proposal_hash"])[:12],
                        "title": f"Maintenance review: {proposal['site_ref']}",
                        "priority": parameters["priority"],
                        "findings": [
                            {
                                "finding_code": c["finding_code"],
                                "confidence": c["confidence"],
                                "interval": c["interval"],
                                "evidence": c["evidence"],
                                "citations": [x["item_id"] for x in c["citations"]],
                            }
                            for c in parameters["claims"]
                        ],
                        "evidence_sha256": [e["sha256"] for e in binding["evidence"]],
                        "assignee": "UNASSIGNED_MODELED",
                    },
                    "ticket_created": False,
                    "ticket_system": "NONE",
                    "physical_actuation": False,
                    "external_calls": 0,
                    "external_effectors": False,
                    "rollback_plan": [
                        "Discard the modeled ticket draft; nothing outside this store changed.",
                        "Mint a receipt recording the discard reason.",
                    ],
                    "truth_label": "MODELED",
                }
                result_hash = plane._sha256(plane._canonical(result))
                rehearsal_id = plane._stable_id("isim", scope, proposal_id, result_hash)
                created = plane._rfc3339(now)
                connection.execute(
                    "INSERT INTO inspection_rehearsals VALUES(?,?,?,?,?,?)",
                    (rehearsal_id, scope, proposal_id, plane._canonical(result).decode("utf-8"), result_hash, created),
                )
                connection.execute(
                    "UPDATE inspection_proposals SET state='REHEARSED' WHERE scope=? AND id=?",
                    (scope, proposal_id),
                )
                receipt = self._receipt(
                    connection,
                    scope=scope,
                    kind="INSPECTION_REHEARSAL_RESULT",
                    object_id=rehearsal_id,
                    payload={
                        "rehearsal_id": rehearsal_id,
                        "proposal_id": proposal_id,
                        "proposal_hash": str(proposal["proposal_hash"]),
                        "result_hash": result_hash,
                        "result": result,
                    },
                )
                connection.commit()
                return {
                    "rehearsal": {"id": rehearsal_id, "result_hash": result_hash, "created_at": created, **result},
                    "proposal_state": "REHEARSED",
                    "receipt": receipt,
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def bundle(self, scope: str, object_id: str) -> dict[str, Any]:
        """Read-only bundle for an assessment or inspection proposal id."""
        with self.read_connection() as connection:
            if INSPECTION_PROPOSAL_ID_RE.fullmatch(object_id):
                proposal = connection.execute(
                    "SELECT * FROM inspection_proposals WHERE scope=? AND id=?", (scope, object_id)
                ).fetchone()
                if proposal is None:
                    raise LookupError("inspection proposal not found in caller session")
                assessment_id = str(proposal["assessment_id"])
            else:
                assessment_id = object_id
                proposal = connection.execute(
                    "SELECT * FROM inspection_proposals WHERE scope=? AND assessment_id=?", (scope, assessment_id)
                ).fetchone()
            assessment = connection.execute(
                "SELECT * FROM inspection_assessments WHERE scope=? AND id=?", (scope, assessment_id)
            ).fetchone()
            if assessment is None:
                raise LookupError("inspection assessment not found in caller session")
            object_ids = [assessment_id]
            approval = rehearsal = None
            if proposal is not None:
                object_ids.append(str(proposal["id"]))
                approval = connection.execute(
                    "SELECT * FROM inspection_approvals WHERE scope=? AND proposal_id=?", (scope, str(proposal["id"]))
                ).fetchone()
                rehearsal = connection.execute(
                    "SELECT * FROM inspection_rehearsals WHERE scope=? AND proposal_id=?", (scope, str(proposal["id"]))
                ).fetchone()
                object_ids += [str(r["id"]) for r in (approval, rehearsal) if r is not None]
            receipts = connection.execute(
                f"SELECT id,kind,object_id,chain_hash,created_at FROM receipts WHERE scope=? AND object_id IN ({','.join('?' * len(object_ids))}) ORDER BY rowid",
                (scope, *object_ids),
            ).fetchall()
            binding_problems = self._binding_problems(connection, scope, proposal) if proposal is not None else []
            return {
                "assessment_id": assessment_id,
                "inspection_id": str(assessment["inspection_id"]),
                "decision": str(assessment["decision"]),
                "assessment": json.loads(str(assessment["assessment_json"])),
                "proposal": self._inspection_proposal_public(proposal),
                "approval": (
                    {"id": str(approval["id"]), "identity": json.loads(str(approval["identity_json"])), "created_at": str(approval["created_at"])}
                    if approval is not None
                    else None
                ),
                "rehearsal": json.loads(str(rehearsal["result_json"])) if rehearsal is not None else None,
                "binding_verified": proposal is None or not binding_problems,
                "binding_problems": binding_problems,
                "receipts": [dict(r) for r in receipts],
            }


def _store() -> InspectionStore:
    path = plane._state_path()
    with _STORES_LOCK:
        store = _STORES.get(path)
        if store is None:
            store = InspectionStore(path)
            _STORES[path] = store
        return store


def _read_store() -> InspectionStore:
    return InspectionStore(plane._state_path(), read_only=True)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
LABELS = {
    "scenario": SCENARIO,
    "data_class": DATA_CLASS,
    "inference": "SCRIPTED_RULES_NO_MODEL_CALL",
    "identities": IDENTITY_MODE,
    "action": "MODELED_TICKET_REHEARSAL_ONLY",
    "physical_actuation": False,
    "real_ticket_created": False,
    "dsse_signed": False,
    "production_ready": False,
}


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, UnauthorizedApprover):
        return JSONResponse({"error": "UNAUTHORIZED_APPROVER", "detail": str(exc), "labels": LABELS}, status_code=403)
    if isinstance(exc, InspectionServiceFailure):
        return JSONResponse(
            {
                "error": "MODEL_SERVICE_UNAVAILABLE",
                "decision": "ABSTAIN",
                "detail": str(exc),
                "receipt": exc.receipt,
                "labels": LABELS,
            },
            status_code=503,
        )
    # PermissionError subclasses OSError; it means "approver not independent".
    if isinstance(exc, (sqlite3.Error, OSError)) and not isinstance(exc, PermissionError):
        return JSONResponse({"error": "LOCAL_STORE_UNAVAILABLE", "detail": type(exc).__name__}, status_code=503)
    return plane._error(exc)


def _proposal_id(body: Any, fields: set[str]) -> str:
    if not isinstance(body, dict) or set(body) != fields:
        raise ValueError(f"body must contain exactly {sorted(fields)}")
    proposal_id = plane._bounded_identifier(body.get("proposal_id"), "proposal_id")
    if INSPECTION_PROPOSAL_ID_RE.fullmatch(proposal_id) is None:
        raise ValueError("proposal_id has an invalid shape")
    return proposal_id


async def _scenario(request: Request) -> JSONResponse:
    adapter = _adapter()
    return JSONResponse(
        {
            "schema": "szl.killinchu.defend-inspection-scenario/v1",
            "scenario_version": SCENARIO_VERSION,
            "labels": LABELS,
            "checklist": {**CHECKLIST, "revision": CHECKLIST_REVISION},
            "model": adapter.binding(),
            "prompt_template": PROMPT_TEMPLATE.format(codes=", ".join(sorted(DEFECT_CODES | {NO_DEFECT}))),
            "simulated_roster": {name: list(roles) for name, roles in SIMULATED_ROSTER.items()},
            "fixtures": {name: spec["expected"] for name, spec in FIXTURE_SPECS.items()},
            "thresholds": {
                "min_support": MIN_SUPPORT,
                "min_confidence": MIN_CONFIDENCE,
                "max_evidence_age_days": MAX_EVIDENCE_AGE.days,
                "proposal_ttl_minutes": int(PROPOSAL_TTL.total_seconds() // 60),
            },
            "allowed_actions": sorted(INSPECTION_ACTIONS),
            "truth_label": "DECLARED",
        }
    )


async def _fixture(request: Request) -> JSONResponse:
    try:
        name = plane._bounded_identifier(request.path_params.get("name"), "name")
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-inspection-fixture/v1",
                "fixture": name,
                "expected": FIXTURE_SPECS.get(name, {}).get("expected"),
                "request": fixture_request(name),
                "truth_label": "SYNTHETIC",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _assess(request: Request) -> JSONResponse:
    try:
        scope = plane._session_scope(request)
        normalized = normalize_request(await plane._json_body(request))
        result = _store().assess_and_propose(scope, normalized, _now(), _adapter())
        if result.get("collision"):
            return JSONResponse(
                {
                    "schema": "szl.killinchu.defend-inspection-assessment/v1",
                    "decision": "QUARANTINE",
                    "reason": "INSPECTION_ID_COLLISION",
                    **result,
                    "labels": LABELS,
                },
                status_code=409,
            )
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-inspection-assessment/v1",
                "decision": result["assessment"]["decision"],
                **result,
                "human_approval_required": True,
                "labels": LABELS,
                "truth_label": "SCRIPTED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _approve(request: Request) -> JSONResponse:
    try:
        scope = plane._session_scope(request)
        body = await plane._json_body(request)
        proposal_id = _proposal_id(body, {"proposal_id", "approver"})
        approver = plane._bounded_identifier(body.get("approver"), "approver")
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-inspection-approval/v1",
                **_store().approve_inspection(scope, proposal_id, approver, _now()),
                "labels": LABELS,
                "truth_label": "SIMULATED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _rehearse(request: Request) -> JSONResponse:
    try:
        scope = plane._session_scope(request)
        proposal_id = _proposal_id(await plane._json_body(request), {"proposal_id"})
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-inspection-rehearsal/v1",
                **_store().rehearse_inspection(scope, proposal_id, _now()),
                "labels": LABELS,
                "truth_label": "MODELED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _bundle(request: Request) -> JSONResponse:
    try:
        scope = plane._session_scope(request)
        object_id = plane._bounded_identifier(request.path_params.get("object_id"), "object_id")
        if ASSESSMENT_ID_RE.fullmatch(object_id) is None and INSPECTION_PROPOSAL_ID_RE.fullmatch(object_id) is None:
            raise ValueError("object_id has an invalid shape")
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-inspection-bundle/v1",
                **_read_store().bundle(scope, object_id),
                "labels": LABELS,
                "truth_label": "MEASURED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _comparison(request: Request) -> JSONResponse:
    raw = request.query_params.get("repeats", "5")
    if not raw.isdigit() or not 1 <= int(raw) <= 50:
        return JSONResponse({"error": "INVALID_REQUEST", "detail": "repeats must be 1-50"}, status_code=422)
    return JSONResponse(compare_with_baseline(int(raw)))


async def _page(request: Request) -> HTMLResponse:
    return HTMLResponse(_PAGE)


def routes(ns: str = "killinchu") -> Iterable[Route]:
    return (
        Route("/defend/inspection", _page, methods=["GET"], name=f"{ns}_defend_inspection_page"),
        Route("/api/defend/inspection/scenario", _scenario, methods=["GET"], name=f"{ns}_defend_inspection_scenario"),
        Route("/api/defend/inspection/fixtures/{name}", _fixture, methods=["GET"], name=f"{ns}_defend_inspection_fixture"),
        Route("/api/defend/inspection/assess", _assess, methods=["POST"], name=f"{ns}_defend_inspection_assess"),
        Route("/api/defend/inspection/approve", _approve, methods=["POST"], name=f"{ns}_defend_inspection_approve"),
        Route("/api/defend/inspection/rehearse", _rehearse, methods=["POST"], name=f"{ns}_defend_inspection_rehearse"),
        Route("/api/defend/inspection/bundle/{object_id}", _bundle, methods=["GET"], name=f"{ns}_defend_inspection_bundle"),
        Route("/api/defend/inspection/comparison", _comparison, methods=["GET"], name=f"{ns}_defend_inspection_comparison"),
    )


_PAGE = r"""<!doctype html>
<html lang="en" data-killinchu-defend-inspection="v1">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>Killinchu / Defend / Inspection</title>
<meta name="description" content="Civilian roof and building inspection rehearsal inside Killinchu Defend: synthetic evidence, scripted findings, cited synthetic checklist, abstention, simulated approval, modeled ticket rehearsal and receipts.">
<style>
:root{color-scheme:dark;--bg:#05080c;--panel:#0b1118;--line:#243749;--ink:#f5f8fb;--muted:#9dabb9;--gold:#d6c69a;--teal:#5fb3a3;--good:#6fae8b;--warn:#d6b06a;--bad:#d08a78}*{box-sizing:border-box;min-inline-size:0}html,body{margin:0;background:var(--bg);color:var(--ink);overflow-x:clip;font:15px/1.55 Inter,"Segoe UI",system-ui,sans-serif}.shell{width:min(100%,1180px);margin:auto;padding:clamp(24px,5vw,64px) 16px 80px}.eyebrow{color:var(--teal);font:700 11px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase}h1{margin:12px 0 14px;font-size:clamp(36px,7vw,72px);line-height:.95;letter-spacing:-.04em}.lede{max-width:70ch;color:var(--muted)}.chips{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0}.chip{border:1px solid var(--line);border-radius:999px;padding:6px 9px;font:700 10px ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--warn)}.grid{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:12px;margin-top:20px}.card{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:16px}label{display:grid;gap:6px;color:var(--muted);font:700 10px ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}select,button{font:inherit;min-height:44px;border-radius:10px;border:1px solid var(--line)}select{width:100%;background:#070b10;color:var(--ink);padding:8px 10px}button{background:var(--ink);color:#05080c;font-weight:800;padding:8px 14px;cursor:pointer}button.secondary{background:transparent;color:var(--ink)}button:disabled{opacity:.45;cursor:not-allowed}.row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}pre{margin:0;max-height:560px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;color:#cbd8e4;font:12px/1.55 ui-monospace,monospace}#verdict{font:800 18px ui-monospace,monospace;margin-bottom:8px}.notice{color:var(--muted);margin-top:18px;max-width:80ch}:focus-visible{outline:3px solid var(--teal);outline-offset:3px}@media(max-width:820px){.grid{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>
<main class="shell">
<div class="eyebrow">Defend plane / civilian scenario</div>
<h1>Roof &amp; building inspection rehearsal</h1>
<p class="lede">Synthetic observations are bound by source, SHA-256 and capture time; scripted findings are grounded in a cited synthetic checklist; the system abstains on missing, stale, conflicting, modified or insufficient evidence; a simulated independent approver can approve a rehearsal of a modeled maintenance-review ticket. Every step extends the Defend receipt chain.</p>
<div class="chips"><span class="chip">synthetic evidence</span><span class="chip">scripted findings</span><span class="chip">simulated identities</span><span class="chip">modeled ticket</span><span class="chip">rehearsal only</span><span class="chip">not production ready</span></div>
<div class="grid">
<section class="card" aria-label="Controls">
<label>Synthetic fixture<select id="fixture"></select></label>
<div class="row"><button type="button" id="assess">1. Assess</button></div>
<label>Approve as (simulated)<select id="approver"><option>simulated/approver-cruz</option><option>simulated/requester-ana</option><option>simulated/requester-ben</option></select></label>
<div class="row"><button type="button" class="secondary" id="approve" disabled>2. Approve rehearsal</button><button type="button" class="secondary" id="rehearse" disabled>3. Rehearse ticket</button></div>
<div class="row"><button type="button" class="secondary" id="verify" disabled>4. Verify last receipt</button><button type="button" class="secondary" id="bundle" disabled>Evidence bundle</button><button type="button" class="secondary" id="compare">Baseline comparison</button></div>
<p class="notice">Approving as <b>simulated/requester-ana</b> demonstrates the self-approval refusal; <b>simulated/requester-ben</b> is not an approver. Identities are roster labels, not authenticated users.</p>
</section>
<section class="card" aria-label="Output"><div id="verdict" aria-live="polite">Ready</div><pre id="output">Choose a synthetic fixture and assess it.</pre></section>
</div>
<p class="notice">Limits: no model is called, no ticketing system is contacted, nothing physical is actuated, and receipts are hash-chained (optionally HMAC) rather than DSSE-signed. Production readiness is false; see <a href="/api/defend/status" style="color:inherit">Defend status</a>.</p>
</main>
<script>
const $=id=>document.getElementById(id);const out=$('output'),verdict=$('verdict');let proposal=null,assessment=null,receipt=null;const key='killinchu-defend-session-v1';
function token(){let v=null;try{v=localStorage.getItem(key)}catch(e){}if(!v||v.length<32){const a=new Uint8Array(32);crypto.getRandomValues(a);v=Array.from(a,b=>b.toString(16).padStart(2,'0')).join('');try{localStorage.setItem(key,v)}catch(e){}}return v}
async function call(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:Object.assign({'X-SZL-Session':token()},body?{'Content-Type':'application/json'}:{}),cache:'no-store',body:body?JSON.stringify(body):undefined});let j;try{j=await r.json()}catch(e){j={error:'NON_JSON_RESPONSE'}}j._http=r.status;return j}
function show(label,j){verdict.textContent=label;out.textContent=JSON.stringify(j,null,2);if(j&&j.receipt&&j.receipt.id)receipt=j.receipt.id;$('verify').disabled=!receipt}
(async()=>{const s=await call('/api/defend/inspection/scenario');for(const [name,exp] of Object.entries(s.fixtures||{})){const o=document.createElement('option');o.value=name;o.textContent=name+' (expected '+exp+')';$('fixture').appendChild(o)}})();
$('assess').onclick=async()=>{const f=await call('/api/defend/inspection/fixtures/'+encodeURIComponent($('fixture').value));const req=f.request;req.inspection_id=req.inspection_id+'-'+Date.now().toString(36);const j=await call('/api/defend/inspection/assess',req);proposal=j.proposal&&j.proposal.state==='PROPOSED'?j.proposal.id:null;assessment=j.assessment_id||null;$('approve').disabled=!proposal;$('rehearse').disabled=true;$('bundle').disabled=!assessment;const reasons=(j.assessment&&j.assessment.abstain_reasons||[]).join(', ');show((j.decision||j.error)+(reasons?' - '+reasons:''),j)};
$('approve').onclick=async()=>{const j=await call('/api/defend/inspection/approve',{proposal_id:proposal,approver:$('approver').value});if(j._http===200){$('approve').disabled=true;$('rehearse').disabled=false}show(j.proposal_state||j.error,j)};
$('rehearse').onclick=async()=>{const j=await call('/api/defend/inspection/rehearse',{proposal_id:proposal});if(j._http===200)$('rehearse').disabled=true;show(j.proposal_state?'REHEARSED (modeled ticket, nothing created)':j.error,j)};
$('verify').onclick=async()=>{const j=await call('/api/defend/verify',{receipt_id:receipt});show(j.integrity_verified?'RECEIPT INTEGRITY VERIFIED':'RECEIPT VERIFICATION FAILED',j)};
$('bundle').onclick=async()=>{const j=await call('/api/defend/inspection/bundle/'+(proposal||assessment));show(j.binding_verified?'BUNDLE BINDING VERIFIED':(j.error||'BINDING PROBLEMS'),j)};
$('compare').onclick=async()=>{const j=await call('/api/defend/inspection/comparison?repeats=5');show('MEASURED ON SYNTHETIC FIXTURES',j)};
</script>
</body>
</html>
"""


__all__ = [
    "ACTION_TYPE",
    "CHECKLIST",
    "CHECKLIST_REVISION",
    "FIXTURE_SPECS",
    "InspectionStore",
    "ScriptedInspectionAdapter",
    "assess",
    "baseline_assess",
    "compare_with_baseline",
    "fixture_request",
    "routes",
]
