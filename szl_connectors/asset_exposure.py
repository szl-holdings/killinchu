# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SZL Holdings
"""Operator-supplied SBOM exposure correlation for Killinchu Wave 5.

This module accepts an in-memory CycloneDX or SPDX JSON document plus explicit,
operator-supplied component-to-CVE findings.  It validates every reference
before making any network call, then reuses the existing Defensive Fusion
connector to correlate official CISA KEV, NIST NVD, and FIRST EPSS evidence.

It never scans an asset, fetches a user-supplied URL, infers vulnerabilities
from package names, executes a command, or mutates a third-party system.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Callable, Iterable


SCHEMA = "szl.killinchu.sbom-exposure/v1"
FORMULA_ID = "killinchu.asset-exposure-priority/v1"
PAYLOAD_TYPE = "application/vnd.szl.killinchu.sbom-exposure+json"

MAX_BODY_BYTES = 2_000_000
MAX_COMPONENTS = 1_000
MAX_FINDINGS = 50
MAX_ACTIVE_CVES = 10

_ASSET_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}")
_ACTIVE_STATUSES = {"affected", "under_investigation"}
_CLOSED_STATUSES = {"fixed", "not_affected"}
_ALLOWED_STATUSES = _ACTIVE_STATUSES | _CLOSED_STATUSES
_EXPOSURE_VALUES = {
    "isolated": 0.0,
    "internal": 1.0 / 3.0,
    "partner": 2.0 / 3.0,
    "internet": 1.0,
}
_LANE_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "REVIEW": 4}


class ExposureInputError(ValueError):
    """Fail-closed input error emitted before official-source resolution."""

    def __init__(self, code: str, detail: str, status_code: int = 422) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class DuplicateKeyError(ValueError):
    """Raised when a submitted JSON object repeats a key."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def loads_strict(raw: bytes) -> dict[str, Any]:
    """Decode bounded, duplicate-key-rejecting UTF-8 JSON."""

    if len(raw) > MAX_BODY_BYTES:
        raise ExposureInputError(
            "BODY_TOO_LARGE",
            f"request body exceeds {MAX_BODY_BYTES} bytes",
            status_code=413,
        )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        raise ExposureInputError(
            "INVALID_JSON",
            f"strict UTF-8 JSON required: {type(exc).__name__}",
            status_code=400,
        ) from exc
    if not isinstance(value, dict):
        raise ExposureInputError(
            "INVALID_ROOT",
            "request root must be a JSON object",
            status_code=400,
        )
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _bounded_text(
    value: Any,
    *,
    field: str,
    maximum: int,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            raise ExposureInputError("MISSING_FIELD", f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ExposureInputError("INVALID_FIELD", f"{field} must be a string")
    normalized = value.strip()
    if required and not normalized:
        raise ExposureInputError("MISSING_FIELD", f"{field} is required")
    if len(normalized) > maximum:
        raise ExposureInputError(
            "FIELD_TOO_LONG",
            f"{field} exceeds {maximum} characters",
        )
    return normalized or None


def _normalize_asset(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ExposureInputError("INVALID_ASSET", "asset must be an object")

    asset_id = _bounded_text(
        raw.get("asset_id"),
        field="asset.asset_id",
        maximum=128,
        required=True,
    )
    assert asset_id is not None
    if _ASSET_ID_RE.fullmatch(asset_id) is None:
        raise ExposureInputError(
            "INVALID_ASSET_ID",
            "asset.asset_id must use letters, digits, dot, underscore, colon, or hyphen",
        )

    criticality = raw.get("criticality")
    if isinstance(criticality, bool) or not isinstance(criticality, int):
        raise ExposureInputError(
            "INVALID_CRITICALITY",
            "asset.criticality must be an integer from 1 through 5",
        )
    if criticality < 1 or criticality > 5:
        raise ExposureInputError(
            "INVALID_CRITICALITY",
            "asset.criticality must be an integer from 1 through 5",
        )

    exposure = _bounded_text(
        raw.get("exposure"),
        field="asset.exposure",
        maximum=32,
        required=True,
    )
    assert exposure is not None
    exposure = exposure.casefold()
    if exposure not in _EXPOSURE_VALUES:
        raise ExposureInputError(
            "INVALID_EXPOSURE",
            "asset.exposure must be isolated, internal, partner, or internet",
        )

    return {
        "asset_id": asset_id,
        "name": _bounded_text(
            raw.get("name"),
            field="asset.name",
            maximum=160,
        ),
        "owner": _bounded_text(
            raw.get("owner"),
            field="asset.owner",
            maximum=160,
        ),
        "environment": _bounded_text(
            raw.get("environment"),
            field="asset.environment",
            maximum=80,
        ),
        "criticality": criticality,
        "exposure": exposure,
    }


def _component_record(
    *,
    ref: str,
    name: Any,
    version: Any,
    purl: Any = None,
    component_type: Any = None,
) -> dict[str, Any]:
    normalized_ref = _bounded_text(
        ref,
        field="component reference",
        maximum=512,
        required=True,
    )
    assert normalized_ref is not None
    return {
        "ref": normalized_ref,
        "name": _bounded_text(
            name,
            field=f"component[{normalized_ref}].name",
            maximum=240,
        ),
        "version": _bounded_text(
            version,
            field=f"component[{normalized_ref}].version",
            maximum=160,
        ),
        "purl": _bounded_text(
            purl,
            field=f"component[{normalized_ref}].purl",
            maximum=512,
        ),
        "type": _bounded_text(
            component_type,
            field=f"component[{normalized_ref}].type",
            maximum=80,
        ),
    }


def _walk_cyclonedx(rows: Any) -> Iterable[dict[str, Any]]:
    if rows is None:
        return
    if not isinstance(rows, list):
        raise ExposureInputError(
            "INVALID_SBOM",
            "CycloneDX components must be an array",
        )
    for row in rows:
        if not isinstance(row, dict):
            raise ExposureInputError(
                "INVALID_SBOM",
                "every CycloneDX component must be an object",
            )
        yield row
        nested = row.get("components")
        if nested is not None:
            yield from _walk_cyclonedx(nested)


def _parse_cyclonedx(sbom: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spec_version = _bounded_text(
        sbom.get("specVersion"),
        field="sbom.specVersion",
        maximum=32,
        required=True,
    )
    assert spec_version is not None

    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _walk_cyclonedx(sbom.get("components", [])):
        ref = row.get("bom-ref") or row.get("purl")
        if not ref:
            raise ExposureInputError(
                "MISSING_COMPONENT_REF",
                "each CycloneDX component requires bom-ref or purl",
            )
        item = _component_record(
            ref=str(ref),
            name=row.get("name"),
            version=row.get("version"),
            purl=row.get("purl"),
            component_type=row.get("type"),
        )
        if item["ref"] in seen:
            raise ExposureInputError(
                "DUPLICATE_COMPONENT_REF",
                f"duplicate CycloneDX component reference: {item['ref']}",
            )
        seen.add(item["ref"])
        components.append(item)
        if len(components) > MAX_COMPONENTS:
            raise ExposureInputError(
                "TOO_MANY_COMPONENTS",
                f"SBOM exceeds {MAX_COMPONENTS} components",
            )

    metadata = sbom.get("metadata") if isinstance(sbom.get("metadata"), dict) else {}
    root_component = (
        metadata.get("component")
        if isinstance(metadata.get("component"), dict)
        else {}
    )
    identity = {
        "format": "CycloneDX",
        "version": spec_version,
        "serial_number": _bounded_text(
            sbom.get("serialNumber"),
            field="sbom.serialNumber",
            maximum=256,
        ),
        "document_name": _bounded_text(
            root_component.get("name"),
            field="sbom.metadata.component.name",
            maximum=240,
        ),
    }
    return identity, components


def _spdx_purl(row: dict[str, Any]) -> str | None:
    refs = row.get("externalRefs")
    if refs is None:
        return None
    if not isinstance(refs, list):
        raise ExposureInputError(
            "INVALID_SBOM",
            "SPDX package externalRefs must be an array",
        )
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        reference_type = str(ref.get("referenceType") or "").casefold()
        if reference_type in {"purl", "package-url"}:
            return _bounded_text(
                ref.get("referenceLocator"),
                field="SPDX purl",
                maximum=512,
            )
    return None


def _parse_spdx(sbom: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spdx_version = _bounded_text(
        sbom.get("spdxVersion"),
        field="sbom.spdxVersion",
        maximum=32,
        required=True,
    )
    assert spdx_version is not None
    if not spdx_version.startswith("SPDX-2."):
        raise ExposureInputError(
            "UNSUPPORTED_SBOM_VERSION",
            "this endpoint accepts SPDX 2.x JSON documents",
        )
    packages = sbom.get("packages", [])
    if not isinstance(packages, list):
        raise ExposureInputError(
            "INVALID_SBOM",
            "SPDX packages must be an array",
        )

    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in packages:
        if not isinstance(row, dict):
            raise ExposureInputError(
                "INVALID_SBOM",
                "every SPDX package must be an object",
            )
        ref = _bounded_text(
            row.get("SPDXID"),
            field="SPDX package SPDXID",
            maximum=512,
            required=True,
        )
        assert ref is not None
        if ref in seen:
            raise ExposureInputError(
                "DUPLICATE_COMPONENT_REF",
                f"duplicate SPDX component reference: {ref}",
            )
        seen.add(ref)
        components.append(
            _component_record(
                ref=ref,
                name=row.get("name"),
                version=row.get("versionInfo"),
                purl=_spdx_purl(row),
                component_type="package",
            )
        )
        if len(components) > MAX_COMPONENTS:
            raise ExposureInputError(
                "TOO_MANY_COMPONENTS",
                f"SBOM exceeds {MAX_COMPONENTS} components",
            )

    identity = {
        "format": "SPDX",
        "version": spdx_version,
        "serial_number": _bounded_text(
            sbom.get("documentNamespace"),
            field="sbom.documentNamespace",
            maximum=512,
        ),
        "document_name": _bounded_text(
            sbom.get("name"),
            field="sbom.name",
            maximum=240,
        ),
    }
    return identity, components


def _parse_sbom(raw: Any) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    if not isinstance(raw, dict):
        raise ExposureInputError("INVALID_SBOM", "sbom must be an object")

    if raw.get("bomFormat") == "CycloneDX":
        identity, components = _parse_cyclonedx(raw)
    elif isinstance(raw.get("spdxVersion"), str):
        identity, components = _parse_spdx(raw)
    else:
        raise ExposureInputError(
            "UNSUPPORTED_SBOM",
            "sbom must be CycloneDX JSON or SPDX 2.x JSON",
        )

    if not components:
        raise ExposureInputError(
            "EMPTY_SBOM",
            "sbom must contain at least one addressable component",
        )
    return identity, sorted(components, key=lambda item: item["ref"]), _sha256(raw)


def _normalize_findings(
    raw: Any,
    component_refs: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ExposureInputError(
            "INVALID_FINDINGS",
            "findings must be a non-empty array",
        )
    if len(raw) > MAX_FINDINGS:
        raise ExposureInputError(
            "TOO_MANY_FINDINGS",
            f"findings exceeds {MAX_FINDINGS} entries",
        )

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ExposureInputError(
                "INVALID_FINDING",
                f"findings[{index}] must be an object",
            )
        component_ref = _bounded_text(
            row.get("component_ref"),
            field=f"findings[{index}].component_ref",
            maximum=512,
            required=True,
        )
        assert component_ref is not None
        if component_ref not in component_refs:
            raise ExposureInputError(
                "UNKNOWN_COMPONENT_REF",
                f"findings[{index}] references no SBOM component: {component_ref}",
            )

        cve = _bounded_text(
            row.get("cve"),
            field=f"findings[{index}].cve",
            maximum=32,
            required=True,
        )
        assert cve is not None
        cve = cve.upper()
        if _CVE_RE.fullmatch(cve) is None:
            raise ExposureInputError(
                "INVALID_CVE",
                f"findings[{index}].cve must be one exact CVE identifier",
            )

        status = _bounded_text(
            row.get("status", "affected"),
            field=f"findings[{index}].status",
            maximum=40,
            required=True,
        )
        assert status is not None
        status = status.casefold()
        if status not in _ALLOWED_STATUSES:
            raise ExposureInputError(
                "INVALID_FINDING_STATUS",
                f"findings[{index}].status must be one of {sorted(_ALLOWED_STATUSES)}",
            )

        justification = _bounded_text(
            row.get("justification"),
            field=f"findings[{index}].justification",
            maximum=800,
        )
        if status in _CLOSED_STATUSES and not justification:
            raise ExposureInputError(
                "MISSING_JUSTIFICATION",
                f"findings[{index}] with status {status} requires justification",
            )

        normalized = {
            "component_ref": component_ref,
            "cve": cve,
            "status": status,
            "justification": justification,
            "evidence_ref": _bounded_text(
                row.get("evidence_ref"),
                field=f"findings[{index}].evidence_ref",
                maximum=512,
            ),
        }
        key = (component_ref, cve, status)
        if key in seen:
            continue
        seen.add(key)
        findings.append(normalized)

    findings.sort(
        key=lambda item: (
            item["component_ref"],
            item["cve"],
            item["status"],
        )
    )
    active_cves = {
        item["cve"]
        for item in findings
        if item["status"] in _ACTIVE_STATUSES
    }
    if len(active_cves) > MAX_ACTIVE_CVES:
        raise ExposureInputError(
            "TOO_MANY_ACTIVE_CVES",
            f"at most {MAX_ACTIVE_CVES} unique active CVEs may be resolved per request",
        )
    return findings


def prepare_payload(payload: Any) -> dict[str, Any]:
    """Validate and normalize the complete request before any source lookup."""

    if not isinstance(payload, dict):
        raise ExposureInputError("INVALID_ROOT", "request root must be an object")

    asset = _normalize_asset(payload.get("asset"))
    sbom_identity, components, sbom_sha256 = _parse_sbom(payload.get("sbom"))
    component_map = {item["ref"]: item for item in components}
    findings = _normalize_findings(
        payload.get("findings"),
        set(component_map),
    )
    active_cves = sorted(
        {
            item["cve"]
            for item in findings
            if item["status"] in _ACTIVE_STATUSES
        }
    )

    normalized_core = {
        "asset": asset,
        "sbom": {
            **sbom_identity,
            "component_count": len(components),
            "components": components,
        },
        "findings": findings,
    }
    return {
        **normalized_core,
        "sbom_input_sha256": sbom_sha256,
        "normalized_input_sha256": _sha256(normalized_core),
        "component_map": component_map,
        "active_cves": active_cves,
    }


def _fusion_record(raw: Any) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(raw, dict):
        return None, {
            "state": "ERROR",
            "coverage": "NONE",
            "note": "resolver returned a non-object",
        }
    records = raw.get("records")
    record = (
        records[0]
        if isinstance(records, list)
        and records
        and isinstance(records[0], dict)
        else None
    )
    state = str(raw.get("state") or "ERROR").upper()
    meta = {
        "state": state,
        "coverage": str(
            (record or {}).get("coverage") or "NONE"
        ).upper(),
        "note": str(raw.get("note") or "")[:500] or None,
        "source": str(raw.get("source") or "")[:300] or None,
        "live": raw.get("live") is True,
    }
    return record, meta


def _context_multiplier(asset: dict[str, Any]) -> tuple[float, dict[str, float]]:
    criticality = (asset["criticality"] - 1) / 4.0
    exposure = _EXPOSURE_VALUES[asset["exposure"]]
    multiplier = 0.55 + (0.30 * criticality) + (0.15 * exposure)
    return round(multiplier, 4), {
        "criticality_normalized": round(criticality, 4),
        "exposure_normalized": round(exposure, 4),
    }


def _score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0.0 or number > 0.99:
        return None
    return number


def _lane(
    source_priority: str,
    asset_score: float | None,
) -> str:
    priority = source_priority.upper()
    if priority == "IMMEDIATE":
        return "P0"
    if priority == "HIGH" or (
        asset_score is not None and asset_score >= 0.65
    ):
        return "P1"
    if priority == "ELEVATED" or (
        asset_score is not None and asset_score >= 0.40
    ):
        return "P2"
    if priority == "ROUTINE" and asset_score is not None:
        return "P3"
    return "REVIEW"


def compose_report(
    prepared: dict[str, Any],
    fusion_results: dict[str, Any],
    *,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Compose a deterministic evidence report from validated inputs and fusion."""

    multiplier, context = _context_multiplier(prepared["asset"])
    evaluated: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    connected = 0
    full = 0

    for finding in prepared["findings"]:
        component = prepared["component_map"][finding["component_ref"]]
        if finding["status"] not in _ACTIVE_STATUSES:
            evaluated.append(
                {
                    **finding,
                    "component": component,
                    "active": False,
                    "remediation_lane": (
                        "CLOSED" if finding["status"] == "fixed" else "VEX"
                    ),
                    "defensive_fusion": None,
                    "asset_priority_score": None,
                }
            )
            continue

        fusion_raw = fusion_results.get(finding["cve"])
        record, meta = _fusion_record(fusion_raw)
        if meta["state"] == "CONNECTED" and record is not None:
            connected += 1
        if meta["coverage"] == "FULL":
            full += 1

        source_score = _score((record or {}).get("priority_score"))
        asset_score = (
            round(min(0.99, source_score * multiplier), 4)
            if source_score is not None
            else None
        )
        source_priority = str(
            (record or {}).get("priority") or "UNAVAILABLE"
        ).upper()
        lane = _lane(source_priority, asset_score)
        row = {
            **finding,
            "component": component,
            "active": True,
            "remediation_lane": lane,
            "asset_priority_score": asset_score,
            "defensive_priority_score": source_score,
            "defensive_priority": source_priority,
            "source_coverage": meta["coverage"],
            "source_state": meta["state"],
            "source_note": meta["note"],
            "known_exploited": (record or {}).get("known_exploited"),
            "known_ransomware_use": (
                record or {}
            ).get("known_ransomware_use"),
            "cvss": (record or {}).get("cvss"),
            "epss": (record or {}).get("epss"),
            "recommended_action": (
                record or {}
            ).get("recommended_action"),
            "normalized_evidence_sha256": (
                record or {}
            ).get("normalized_evidence_sha256"),
        }
        evaluated.append(row)
        queue.append(row)

    queue.sort(
        key=lambda row: (
            _LANE_ORDER.get(row["remediation_lane"], 99),
            -(
                row["asset_priority_score"]
                if row["asset_priority_score"] is not None
                else -1.0
            ),
            row["cve"],
            row["component_ref"],
        )
    )
    lane_counts = Counter(row["remediation_lane"] for row in queue)
    active_count = len(queue)
    if active_count == 0:
        state = "NO_ACTIVE_FINDINGS"
    elif connected == active_count and full == active_count:
        state = "MEASURED"
    elif connected > 0:
        state = "PARTIAL"
    else:
        state = "UNAVAILABLE"

    evidence_core = {
        "schema": SCHEMA,
        "asset": prepared["asset"],
        "sbom": {
            key: value
            for key, value in prepared["sbom"].items()
            if key != "components"
        },
        "sbom_input_sha256": prepared["sbom_input_sha256"],
        "normalized_input_sha256": prepared["normalized_input_sha256"],
        "findings": evaluated,
        "formula": {
            "id": FORMULA_ID,
            "defensive_priority_source": (
                "killinchu.defensive-priority/v1"
            ),
            "context_multiplier": {
                "expression": (
                    "0.55 + 0.30*criticality_normalized "
                    "+ 0.15*exposure_normalized"
                ),
                "value": multiplier,
                **context,
            },
            "asset_priority_expression": (
                "defensive_priority_score * context_multiplier"
            ),
            "maximum_score": 0.99,
            "probability_claimed": False,
        },
    }
    evidence_sha256 = _sha256(evidence_core)

    return {
        **evidence_core,
        "observed_at": observed_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "state": state,
        "summary": {
            "component_count": prepared["sbom"]["component_count"],
            "finding_count": len(prepared["findings"]),
            "active_findings": active_count,
            "officially_resolved_findings": connected,
            "full_source_coverage_findings": full,
            "remediation_lanes": {
                lane: lane_counts.get(lane, 0)
                for lane in ("P0", "P1", "P2", "P3", "REVIEW")
            },
        },
        "remediation_queue": queue,
        "evidence_sha256": evidence_sha256,
        "truth_label": "OPERATOR_SUPPLIED_EXPOSURE_WITH_OFFICIAL_CVE_EVIDENCE",
        "action_authority": "DEFENSIVE_REMEDIATION_PLANNING_ONLY",
        "human_approval_required": True,
        "asset_scanning_performed": False,
        "sbom_fetched_remotely": False,
        "component_vulnerability_inference_performed": False,
        "third_party_mutation_performed": False,
        "data_persisted": False,
        "honesty": (
            "Component-to-CVE associations are operator supplied and validated "
            "against the submitted SBOM. Killinchu does not infer affected "
            "packages, inspect a live asset, or claim probability of compromise. "
            "Official source gaps remain explicit."
        ),
    }


def _resolve_live_fusion(cve: str) -> dict[str, Any]:
    from .data_sources.security import DefensiveFusionConnector

    return DefensiveFusionConnector().read({"cve": cve}).to_dict()


def _sign(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        import szl_dsse
    except Exception:
        return {
            **payload,
            "signed": False,
            "dsse": {
                "signed": False,
                "honesty": (
                    "szl_dsse unavailable; no signature fabricated"
                ),
            },
        }
    try:
        envelope = szl_dsse.sign_payload(
            payload,
            payload_type=PAYLOAD_TYPE,
        )
    except Exception as exc:
        return {
            **payload,
            "signed": False,
            "dsse": {
                "signed": False,
                "honesty": (
                    "release signing unavailable; no signature fabricated"
                ),
                "error": type(exc).__name__,
            },
        }
    return {
        **payload,
        "signed": bool(envelope.get("signed")),
        "dsse": envelope,
        "cosign_keyid": getattr(
            szl_dsse,
            "KEYID",
            "szlholdings-cosign",
        ),
    }


def contract() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "endpoint": "/api/killinchu/uds/v1/sbom/exposure/evaluate",
        "method": "POST",
        "accepted_sbom_formats": [
            "CycloneDX JSON",
            "SPDX 2.x JSON",
        ],
        "required": {
            "asset": {
                "asset_id": "stable identifier",
                "criticality": "integer 1..5",
                "exposure": sorted(_EXPOSURE_VALUES),
            },
            "sbom": "inline JSON object; never fetched from a URL",
            "findings": {
                "component_ref": "exact bom-ref, purl, or SPDXID",
                "cve": "one exact CVE-YYYY-NNNN identifier",
                "status": sorted(_ALLOWED_STATUSES),
            },
        },
        "limits": {
            "body_bytes": MAX_BODY_BYTES,
            "components": MAX_COMPONENTS,
            "findings": MAX_FINDINGS,
            "active_cves": MAX_ACTIVE_CVES,
        },
        "authority": "DEFENSIVE_REMEDIATION_PLANNING_ONLY",
        "network_boundary": (
            "only the existing source-bound CISA KEV, NIST NVD, "
            "and FIRST EPSS connector is invoked"
        ),
        "forbidden": [
            "asset scanning",
            "user-supplied URL retrieval",
            "package-to-CVE inference",
            "exploit content",
            "command execution",
            "third-party mutation",
        ],
    }


def register(
    app: Any,
    ns: str = "killinchu",
    *,
    resolver: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Register the read-only Wave 5 schema and evaluation routes."""

    from fastapi import Request
    from fastapi.responses import JSONResponse

    base = f"/api/{ns}/uds/v1/sbom/exposure"
    live_resolver = resolver or _resolve_live_fusion

    @app.get(base + "/schema")
    async def sbom_exposure_schema() -> JSONResponse:
        return JSONResponse(contract())

    @app.post(base + "/evaluate")
    async def sbom_exposure_evaluate(request: Request) -> JSONResponse:
        try:
            payload = loads_strict(await request.body())
            prepared = prepare_payload(payload)
        except ExposureInputError as exc:
            return JSONResponse(
                {
                    "schema": SCHEMA,
                    "state": "REJECTED",
                    "error": exc.code,
                    "detail": exc.detail,
                    "network_calls_performed": 0,
                },
                status_code=exc.status_code,
            )

        fusion_results: dict[str, Any] = {}
        try:
            for cve in prepared["active_cves"]:
                fusion_results[cve] = await asyncio.to_thread(
                    live_resolver,
                    cve,
                )
            report = compose_report(prepared, fusion_results)
        except Exception as exc:
            return JSONResponse(
                {
                    "schema": SCHEMA,
                    "state": "ERROR",
                    "error": "OFFICIAL_SOURCE_RESOLUTION_FAILED",
                    "detail": type(exc).__name__,
                    "action_authority": (
                        "DEFENSIVE_REMEDIATION_PLANNING_ONLY"
                    ),
                    "human_approval_required": True,
                },
                status_code=502,
            )
        return JSONResponse(_sign(report))

    registered = [
        base + "/schema",
        base + "/evaluate",
    ]
    return {
        "module": "szl_connectors.asset_exposure",
        "schema": SCHEMA,
        "registered": registered,
        "registered_count": len(registered),
        "authority": "DEFENSIVE_REMEDIATION_PLANNING_ONLY",
    }


__all__ = [
    "ExposureInputError",
    "SCHEMA",
    "compose_report",
    "contract",
    "loads_strict",
    "prepare_payload",
    "register",
]
