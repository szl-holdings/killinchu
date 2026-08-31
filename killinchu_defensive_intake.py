#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SZL Holdings
"""Fail-closed defensive IOC intake and inert scanner-adapter planning.

This module deliberately has no scanning or enrichment capability.  It accepts
only analyst-supplied indicators, normalizes them in memory with the Python
standard library, selects adapters from a fixed allowlist, and emits an
unsigned content-addressed evidence receipt.

Security boundary (non-negotiable):

* no network or DNS access;
* no subprocess, shell, binary, plug-in, or dynamic tool execution;
* no filesystem reads or writes;
* no credentials, live targets, commands, or scanner options in the schema;
* unknown fields and unknown adapters are rejected (default deny);
* bounded request bytes, indicator count, adapter count, and value length.

The scanner adapters are metadata-only review stages for reports that were
generated elsewhere under the operator's own authorization.  Selecting one
does not invoke a scanner, parse a report, or establish authorization.

Provenance: this is a clean-room SZL implementation.  Public HackerCondor
repositories were reviewed only to understand high-level defensive tool
taxonomy.  No HackerCondor source code, content, data, or command definitions
are embedded.  The observed license boundary is exposed by
``tool_registry_document`` so it remains auditable at runtime.
"""
import hashlib
import hmac
import ipaddress
import json
import re
from collections import Counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from starlette.requests import Request


PLAN_SCHEMA = "killinchu.defensive-intake-plan/v1"
RECEIPT_SCHEMA = "killinchu.defensive-intake-receipt/v1"
REGISTRY_SCHEMA = "killinchu.defensive-tool-registry/v1"

MAX_PAYLOAD_BYTES = 65_536
MAX_INDICATORS = 100
MAX_ADAPTERS = 4
MAX_INDICATOR_VALUE_BYTES = 2_048

_ALLOWED_PAYLOAD_FIELDS = frozenset(
    {"authorization_ref", "indicators", "adapters"}
)
_ALLOWED_INDICATOR_FIELDS = frozenset({"type", "value"})
_AUTHORIZATION_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}")
_DOMAIN_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_CVE_RE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,}", re.IGNORECASE)
_HASH_LENGTHS = {"md5": 32, "sha1": 40, "sha256": 64}


SANDBOX_BOUNDARY: dict[str, bool] = {
    "network_access": False,
    "dns_resolution": False,
    "remote_content_fetch": False,
    "subprocess_execution": False,
    "shell_execution": False,
    "filesystem_reads": False,
    "filesystem_writes": False,
    "dynamic_tool_loading": False,
    "secret_access": False,
    "live_scanning": False,
    "live_targets_accepted": False,
}


_ADAPTERS: tuple[dict[str, Any], ...] = (
    {
        "id": "ioc-normalize",
        "kind": "PURE_LOCAL_TRANSFORM",
        "purpose": "Normalize analyst-supplied IOC values in memory.",
        "planner_capability": "AVAILABLE",
        "execution_capability": "MEMORY_ONLY",
        "network_access": False,
        "accepts_live_targets": False,
    },
    {
        "id": "network-scan-report-review",
        "kind": "INERT_SCANNER_RESULT_ADAPTER",
        "purpose": "Plan review of a pre-generated network scan report.",
        "planner_capability": "AVAILABLE",
        "execution_capability": "NONE",
        "network_access": False,
        "accepts_live_targets": False,
    },
    {
        "id": "file-rule-report-review",
        "kind": "INERT_SCANNER_RESULT_ADAPTER",
        "purpose": "Plan review of a pre-generated file-rule scan report.",
        "planner_capability": "AVAILABLE",
        "execution_capability": "NONE",
        "network_access": False,
        "accepts_live_targets": False,
    },
    {
        "id": "antimalware-report-review",
        "kind": "INERT_SCANNER_RESULT_ADAPTER",
        "purpose": "Plan review of a pre-generated antimalware scan report.",
        "planner_capability": "AVAILABLE",
        "execution_capability": "NONE",
        "network_access": False,
        "accepts_live_targets": False,
    },
)
_ADAPTER_BY_ID = {adapter["id"]: adapter for adapter in _ADAPTERS}


PROVENANCE_REVIEW: dict[str, Any] = {
    "review_id": "killinchu-clean-room-hackercondor-review-2026-08-31",
    "implementation": "SZL_CLEAN_ROOM",
    "third_party_code_embedded": False,
    "third_party_content_embedded": False,
    "reviewed_sources": [
        {
            "repository": "https://github.com/hackercondor/Ethical-hacking-tools",
            "observed_license": "Apache-2.0",
            "use": "TAXONOMY_REVIEW_ONLY",
            "embedded": False,
        },
        {
            "repository": "https://github.com/hackercondor/hacker101",
            "observed_license": "CC-BY-NC-SA-4.0",
            "github_license_detection": "NOASSERTION",
            "use": "EXCLUDED_FROM_IMPLEMENTATION",
            "embedded": False,
        },
        {
            "repository": "https://github.com/hackercondor/app",
            "observed_license": "NO_LICENSE_FOUND (empty repository)",
            "use": "EXCLUDED_FROM_IMPLEMENTATION",
            "embedded": False,
        },
    ],
}


class DefensiveIntakeError(ValueError):
    """A stable, non-sensitive validation error for the API boundary."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _unknown_fields(
    mapping: dict[Any, Any], allowed: frozenset[str], *, context: str
) -> list[str]:
    """Reject non-string JSON keys before comparing the strict field set."""

    if any(not isinstance(key, str) for key in mapping):
        raise DefensiveIntakeError(
            "INVALID_JSON_KEY", f"{context} field names must be strings"
        )
    return sorted(set(mapping) - allowed)


def _canonical_json(value: Any) -> bytes:
    """Return stable UTF-8 JSON used solely for local content addressing."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DefensiveIntakeError(
            "INVALID_JSON_VALUE", "payload must contain finite JSON values"
        ) from exc


def _copy_json(value: Any) -> Any:
    """Return a mutation-safe copy without importing a plug-in serializer."""

    return json.loads(_canonical_json(value).decode("utf-8"))


def _checked_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise DefensiveIntakeError("INVALID_INDICATOR", f"{field} must be a string")
    text = value.strip()
    if not text:
        raise DefensiveIntakeError("INVALID_INDICATOR", f"{field} must not be empty")
    if len(text.encode("utf-8")) > MAX_INDICATOR_VALUE_BYTES:
        raise DefensiveIntakeError(
            "INDICATOR_TOO_LARGE",
            f"{field} exceeds {MAX_INDICATOR_VALUE_BYTES} UTF-8 bytes",
            status_code=413,
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise DefensiveIntakeError(
            "INVALID_INDICATOR", f"{field} contains control characters"
        )
    return text


def _normalize_ip(value: str, requested_type: str = "ip") -> dict[str, str]:
    if "%" in value:
        raise DefensiveIntakeError(
            "INVALID_IP", "scoped IPv6 zone identifiers are not accepted"
        )
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise DefensiveIntakeError("INVALID_IP", "indicator is not a valid IP") from exc
    actual_type = f"ipv{address.version}"
    if requested_type in {"ipv4", "ipv6"} and requested_type != actual_type:
        raise DefensiveIntakeError(
            "IP_VERSION_MISMATCH", f"indicator is {actual_type}, not {requested_type}"
        )
    return {"type": actual_type, "value": address.compressed.lower()}


def _normalize_domain_value(value: str) -> str:
    if any(char.isspace() for char in value):
        raise DefensiveIntakeError("INVALID_DOMAIN", "domain contains whitespace")
    candidate = value.rstrip(".").lower()
    if not candidate or "." not in candidate:
        raise DefensiveIntakeError(
            "INVALID_DOMAIN", "domain must contain at least two labels"
        )
    try:
        ascii_domain = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise DefensiveIntakeError("INVALID_DOMAIN", "domain IDNA encoding failed") from exc
    if len(ascii_domain.encode("ascii")) > 253:
        raise DefensiveIntakeError("INVALID_DOMAIN", "domain exceeds 253 bytes")
    labels = ascii_domain.split(".")
    if any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        raise DefensiveIntakeError("INVALID_DOMAIN", "domain label syntax is invalid")
    try:
        ipaddress.ip_address(ascii_domain)
    except ValueError:
        return ascii_domain
    raise DefensiveIntakeError("INVALID_DOMAIN", "IP literals must use an IP type")


def _normalize_url(value: str) -> dict[str, str]:
    if "\\" in value or any(char.isspace() for char in value):
        raise DefensiveIntakeError(
            "INVALID_URL", "URL must not contain whitespace or backslashes"
        )
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise DefensiveIntakeError("INVALID_URL", "URL authority or port is invalid") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise DefensiveIntakeError("INVALID_URL", "only http and https URLs are accepted")
    if not parts.netloc or not parts.hostname:
        raise DefensiveIntakeError("INVALID_URL", "URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise DefensiveIntakeError(
            "CREDENTIALS_REJECTED", "URL userinfo and credentials are not accepted"
        )
    host = parts.hostname
    if "%" in host:
        raise DefensiveIntakeError("INVALID_URL", "scoped IPv6 hosts are not accepted")
    try:
        ip_host = ipaddress.ip_address(host)
    except ValueError:
        normalized_host = _normalize_domain_value(host)
        rendered_host = normalized_host
    else:
        normalized_host = ip_host.compressed.lower()
        rendered_host = (
            f"[{normalized_host}]" if ip_host.version == 6 else normalized_host
        )
    default_port = 80 if scheme == "http" else 443
    rendered_port = "" if port is None or port == default_port else f":{port}"
    path = parts.path or "/"
    normalized = urlunsplit(
        (scheme, f"{rendered_host}{rendered_port}", path, parts.query, "")
    )
    return {"type": "url", "value": normalized}


def _normalize_hash(value: str, hash_type: str) -> dict[str, str]:
    expected = _HASH_LENGTHS[hash_type]
    if len(value) != expected or not re.fullmatch(r"[0-9a-fA-F]+", value):
        raise DefensiveIntakeError(
            "INVALID_HASH", f"{hash_type} must be exactly {expected} hexadecimal characters"
        )
    return {"type": hash_type, "value": value.lower()}


def _normalize_cve(value: str) -> dict[str, str]:
    if not _CVE_RE.fullmatch(value):
        raise DefensiveIntakeError("INVALID_CVE", "CVE identifier syntax is invalid")
    return {"type": "cve", "value": value.upper()}


def _infer_type(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        return "url"
    if _CVE_RE.fullmatch(value):
        return "cve"
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return f"ipv{address.version}"
    for hash_type, length in _HASH_LENGTHS.items():
        if len(value) == length and re.fullmatch(r"[0-9a-fA-F]+", value):
            return hash_type
    try:
        _normalize_domain_value(value)
    except DefensiveIntakeError as exc:
        raise DefensiveIntakeError(
            "UNKNOWN_INDICATOR_TYPE",
            "indicator type could not be inferred; provide an explicit supported type",
        ) from exc
    return "domain"


def normalize_indicator(item: Any) -> dict[str, str]:
    """Normalize one IOC without resolving, fetching, scanning, or enriching."""

    if isinstance(item, str):
        value = _checked_text(item, field="indicator")
        indicator_type = _infer_type(value)
    elif isinstance(item, dict):
        unknown_fields = _unknown_fields(
            item, _ALLOWED_INDICATOR_FIELDS, context="indicator"
        )
        if unknown_fields:
            raise DefensiveIntakeError(
                "UNKNOWN_INDICATOR_FIELD",
                f"indicator contains unsupported fields: {', '.join(unknown_fields)}",
            )
        if "type" not in item or "value" not in item:
            raise DefensiveIntakeError(
                "INVALID_INDICATOR", "indicator objects require type and value"
            )
        indicator_type = _checked_text(item["type"], field="indicator.type").lower()
        value = _checked_text(item["value"], field="indicator.value")
    else:
        raise DefensiveIntakeError(
            "INVALID_INDICATOR", "each indicator must be a string or object"
        )

    if indicator_type in {"ip", "ipv4", "ipv6"}:
        return _normalize_ip(value, indicator_type)
    if indicator_type == "domain":
        return {"type": "domain", "value": _normalize_domain_value(value)}
    if indicator_type == "url":
        return _normalize_url(value)
    if indicator_type in _HASH_LENGTHS:
        return _normalize_hash(value, indicator_type)
    if indicator_type == "cve":
        return _normalize_cve(value)
    raise DefensiveIntakeError(
        "UNSUPPORTED_INDICATOR_TYPE",
        "supported types: ip, ipv4, ipv6, domain, url, md5, sha1, sha256, cve",
    )


def normalize_indicators(items: Any) -> list[dict[str, str]]:
    """Normalize, deduplicate, and deterministically sort a bounded IOC list."""

    if not isinstance(items, list):
        raise DefensiveIntakeError("INVALID_INDICATORS", "indicators must be a JSON list")
    if not items:
        raise DefensiveIntakeError("INVALID_INDICATORS", "at least one indicator is required")
    if len(items) > MAX_INDICATORS:
        raise DefensiveIntakeError(
            "TOO_MANY_INDICATORS",
            f"at most {MAX_INDICATORS} indicators are accepted",
            status_code=413,
        )
    deduplicated: dict[tuple[str, str], dict[str, str]] = {}
    for item in items:
        normalized = normalize_indicator(item)
        deduplicated[(normalized["type"], normalized["value"])] = normalized
    return [deduplicated[key] for key in sorted(deduplicated)]


def _selected_adapter_ids(raw_adapters: Any) -> list[str]:
    if raw_adapters is None:
        requested: list[Any] = []
    elif isinstance(raw_adapters, list):
        requested = raw_adapters
    else:
        raise DefensiveIntakeError("INVALID_ADAPTERS", "adapters must be a JSON list")
    if len(requested) > MAX_ADAPTERS:
        raise DefensiveIntakeError(
            "TOO_MANY_ADAPTERS",
            f"at most {MAX_ADAPTERS} adapters are accepted",
            status_code=413,
        )
    if any(not isinstance(adapter_id, str) for adapter_id in requested):
        raise DefensiveIntakeError(
            "INVALID_ADAPTERS", "every adapter id must be a string"
        )
    normalized = [adapter_id.strip() for adapter_id in requested]
    if any(not adapter_id for adapter_id in normalized):
        raise DefensiveIntakeError("INVALID_ADAPTERS", "adapter ids must not be empty")
    if len(normalized) != len(set(normalized)):
        raise DefensiveIntakeError("DUPLICATE_ADAPTER", "duplicate adapter ids are rejected")
    unknown = sorted(set(normalized) - set(_ADAPTER_BY_ID))
    if unknown:
        raise DefensiveIntakeError(
            "ADAPTER_NOT_ALLOWLISTED",
            f"adapter is not allowlisted: {', '.join(unknown)}",
        )
    review_stages = sorted(set(normalized) - {"ioc-normalize"})
    return ["ioc-normalize", *review_stages]


def _authorization_digest(value: Any) -> str:
    if not isinstance(value, str) or not _AUTHORIZATION_REF_RE.fullmatch(value):
        raise DefensiveIntakeError(
            "INVALID_AUTHORIZATION_REF",
            "authorization_ref must be 3-128 characters using letters, digits, . _ : / or -",
        )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_defensive_plan(payload: Any) -> dict[str, Any]:
    """Build a deterministic, side-effect-free plan and evidence receipt."""

    if not isinstance(payload, dict):
        raise DefensiveIntakeError("INVALID_PAYLOAD", "request body must be a JSON object")
    payload_bytes = _canonical_json(payload)
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise DefensiveIntakeError(
            "PAYLOAD_TOO_LARGE",
            f"request exceeds {MAX_PAYLOAD_BYTES} canonical UTF-8 bytes",
            status_code=413,
        )
    unknown_fields = _unknown_fields(
        payload, _ALLOWED_PAYLOAD_FIELDS, context="request"
    )
    if unknown_fields:
        raise DefensiveIntakeError(
            "UNKNOWN_PAYLOAD_FIELD",
            f"request contains unsupported fields: {', '.join(unknown_fields)}",
        )
    if "authorization_ref" not in payload:
        raise DefensiveIntakeError(
            "INVALID_AUTHORIZATION_REF", "authorization_ref is required"
        )
    if "indicators" not in payload:
        raise DefensiveIntakeError("INVALID_INDICATORS", "indicators is required")

    authorization_digest = _authorization_digest(payload["authorization_ref"])
    indicators = normalize_indicators(payload["indicators"])
    adapter_ids = _selected_adapter_ids(payload.get("adapters"))
    indicator_counts = Counter(indicator["type"] for indicator in indicators)

    workflow: list[dict[str, str]] = []
    for index, adapter_id in enumerate(adapter_ids, start=1):
        adapter = _ADAPTER_BY_ID[adapter_id]
        state = (
            "COMPLETED_MEMORY_ONLY"
            if adapter_id == "ioc-normalize"
            else "NOT_EXECUTED_PLAN_ONLY"
        )
        workflow.append(
            {
                "step": f"{index:02d}",
                "adapter_id": adapter_id,
                "adapter_kind": adapter["kind"],
                "state": state,
            }
        )

    body: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "mode": "DEFENSIVE_ANALYSIS_ONLY",
        "external_execution_state": "NOT_PERFORMED",
        "indicator_handling": {
            "role": "PASSIVE_ANALYST_SUPPLIED_EVIDENCE",
            "execution_target": False,
            "resolution_or_enrichment": "NOT_PERFORMED",
        },
        "authorization": {
            "reference_digest": {"sha256": authorization_digest},
            "verification": "NOT_PERFORMED_REFERENCE_ONLY",
            "note": "A syntactically valid reference does not establish authorization.",
        },
        "indicators": indicators,
        "indicator_summary": {
            "input_count": len(payload["indicators"]),
            "unique_count": len(indicators),
            "by_type": dict(sorted(indicator_counts.items())),
        },
        "selected_adapters": adapter_ids,
        "workflow": workflow,
        "sandbox_boundary": _copy_json(SANDBOX_BOUNDARY),
        "limits": {
            "max_payload_bytes": MAX_PAYLOAD_BYTES,
            "max_indicators": MAX_INDICATORS,
            "max_adapters": MAX_ADAPTERS,
            "max_indicator_value_bytes": MAX_INDICATOR_VALUE_BYTES,
        },
        "provenance": {
            "review_id": PROVENANCE_REVIEW["review_id"],
            "implementation": "SZL_CLEAN_ROOM",
            "third_party_code_embedded": False,
            "third_party_content_embedded": False,
        },
        "limitations": [
            "No scanner, network, DNS, enrichment, or external tool was invoked.",
            "IP and URL values are passive analyst-supplied evidence, never execution targets.",
            "Report adapters are inert planning metadata and accept no live target.",
            "MD5 and SHA-1 values are identifiers only, never cryptographic trust anchors.",
            "The receipt is unsigned and establishes content integrity only.",
        ],
    }
    digest = hashlib.sha256(_canonical_json(body)).hexdigest()
    body["receipt"] = {
        "schema": RECEIPT_SCHEMA,
        "subject": {
            "name": "killinchu-defensive-intake-plan",
            "digest": {"sha256": digest},
        },
        "signed": False,
        "signature_state": "UNAVAILABLE_NO_SIGNER",
        "authenticity": "NOT_ESTABLISHED",
        "integrity_scope": "stable UTF-8 JSON of the plan excluding receipt",
    }
    return body


def verify_plan_receipt(document: Any) -> tuple[bool, str]:
    """Verify the local content digest; never imply signature authenticity."""

    if not isinstance(document, dict):
        return False, "NOT_A_DOCUMENT"
    receipt = document.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        return False, "RECEIPT_MISSING_OR_UNSUPPORTED"
    if receipt.get("signed") is not False:
        return False, "UNSUPPORTED_SIGNATURE_CLAIM"
    try:
        claimed = receipt["subject"]["digest"]["sha256"]
    except (KeyError, TypeError):
        return False, "DIGEST_MISSING"
    if not isinstance(claimed, str) or not re.fullmatch(r"[0-9a-f]{64}", claimed):
        return False, "DIGEST_INVALID"
    body = {key: value for key, value in document.items() if key != "receipt"}
    try:
        observed = hashlib.sha256(_canonical_json(body)).hexdigest()
    except DefensiveIntakeError:
        return False, "DOCUMENT_NOT_CANONICALIZABLE"
    if not hmac.compare_digest(claimed, observed):
        return False, "DIGEST_MISMATCH"
    return True, "CONTENT_DIGEST_VERIFIED_UNSIGNED"


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for key, value in pairs:
        if key in parsed:
            raise DefensiveIntakeError(
                "DUPLICATE_JSON_KEY", "duplicate JSON object keys are rejected", 400
            )
        parsed[key] = value
    return parsed


def _reject_nonfinite_json(_value: str) -> None:
    raise DefensiveIntakeError(
        "NONFINITE_JSON_NUMBER", "NaN and Infinity are not valid intake values", 400
    )


def parse_json_body(raw_body: Any) -> Any:
    """Decode strict UTF-8 JSON with bounded bytes and duplicate-key rejection."""

    if not isinstance(raw_body, (bytes, bytearray)):
        raise DefensiveIntakeError("INVALID_BODY", "request body must be bytes", 400)
    if len(raw_body) > MAX_PAYLOAD_BYTES:
        raise DefensiveIntakeError(
            "PAYLOAD_TOO_LARGE",
            f"request exceeds {MAX_PAYLOAD_BYTES} raw bytes",
            status_code=413,
        )
    try:
        text = bytes(raw_body).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DefensiveIntakeError(
            "INVALID_BODY_ENCODING", "request body must be valid UTF-8", 400
        ) from exc
    if not text.strip():
        raise DefensiveIntakeError("MALFORMED_JSON", "request body is empty", 400)
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_json,
        )
    except DefensiveIntakeError:
        raise
    except json.JSONDecodeError as exc:
        raise DefensiveIntakeError(
            "MALFORMED_JSON", "request body is not valid JSON", 400
        ) from exc


async def read_bounded_json_request(request: Request) -> Any:
    """Validate transport metadata, then stream no more than MAX+1 raw bytes."""

    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    is_json = media_type == "application/json" or (
        media_type.startswith("application/") and media_type.endswith("+json")
    )
    if not is_json:
        raise DefensiveIntakeError(
            "JSON_CONTENT_TYPE_REQUIRED",
            "Content-Type must be application/json or application/*+json",
            415,
        )
    content_encoding = request.headers.get("content-encoding", "identity").strip().lower()
    if content_encoding not in {"", "identity"}:
        raise DefensiveIntakeError(
            "CONTENT_ENCODING_REJECTED", "compressed request bodies are not accepted", 415
        )
    declared_raw = request.headers.get("content-length")
    declared = None
    if declared_raw is not None:
        declared_text = declared_raw.strip()
        if not re.fullmatch(r"[0-9]+", declared_text):
            raise DefensiveIntakeError(
                "INVALID_CONTENT_LENGTH",
                "Content-Length must be a non-negative integer",
                400,
            )
        declared = int(declared_text)
        if declared > MAX_PAYLOAD_BYTES:
            raise DefensiveIntakeError(
                "PAYLOAD_TOO_LARGE",
                f"Content-Length exceeds {MAX_PAYLOAD_BYTES} bytes",
                413,
            )

    body = bytearray()
    async for chunk in request.stream():
        if not isinstance(chunk, (bytes, bytearray)):
            raise DefensiveIntakeError("INVALID_BODY", "request stream yielded non-bytes", 400)
        remaining = (MAX_PAYLOAD_BYTES + 1) - len(body)
        body.extend(chunk[:remaining])
        if len(body) > MAX_PAYLOAD_BYTES or len(chunk) > remaining:
            raise DefensiveIntakeError(
                "PAYLOAD_TOO_LARGE",
                f"request exceeds {MAX_PAYLOAD_BYTES} raw bytes",
                413,
            )
    if declared is not None and len(body) != declared:
        raise DefensiveIntakeError(
            "CONTENT_LENGTH_MISMATCH",
            "received body length does not match Content-Length",
            400,
        )
    return parse_json_body(body)


def tool_registry_document() -> dict[str, Any]:
    """Return the fixed allowlist and the clean-room license review record."""

    return {
        "schema": REGISTRY_SCHEMA,
        "policy": {
            "default_deny": True,
            "unknown_adapters": "REJECTED",
            "scanner_execution": "DISABLED",
            "live_scanning": False,
            "authorization_enforcement": "EXTERNAL_TO_THIS_PLANNER",
        },
        "adapters": _copy_json(_ADAPTERS),
        "sandbox_boundary": _copy_json(SANDBOX_BOUNDARY),
        "provenance_review": _copy_json(PROVENANCE_REVIEW),
    }


def register(app: Any, ns: str = "killinchu") -> dict[str, Any]:
    """Register read-only registry and side-effect-free planning endpoints."""

    from fastapi.responses import JSONResponse

    namespace = str(ns).strip().strip("/").lower()
    if not re.fullmatch(r"[a-z0-9-]+", namespace):
        raise ValueError("namespace must contain only lowercase letters, digits, or hyphens")
    base = f"/api/{namespace}/v1/defensive-intake"
    routes = [f"GET {base}/tools", f"POST {base}/plan"]

    @app.get(f"{base}/tools")
    async def _defensive_tools() -> dict[str, Any]:
        return tool_registry_document()

    @app.post(f"{base}/plan")
    async def _defensive_plan(request: Request):
        try:
            payload = await read_bounded_json_request(request)
            return build_defensive_plan(payload)
        except DefensiveIntakeError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {"code": exc.code, "message": exc.message},
                    "external_execution_state": "NOT_PERFORMED",
                },
                status_code=exc.status_code,
            )

    return {
        "registered": routes,
        "mode": "DEFENSIVE_ANALYSIS_ONLY",
        "scanner_execution": "DISABLED",
    }


__all__ = [
    "DefensiveIntakeError",
    "MAX_ADAPTERS",
    "MAX_INDICATORS",
    "MAX_INDICATOR_VALUE_BYTES",
    "MAX_PAYLOAD_BYTES",
    "PLAN_SCHEMA",
    "PROVENANCE_REVIEW",
    "RECEIPT_SCHEMA",
    "REGISTRY_SCHEMA",
    "SANDBOX_BOUNDARY",
    "build_defensive_plan",
    "normalize_indicator",
    "normalize_indicators",
    "parse_json_body",
    "read_bounded_json_request",
    "register",
    "tool_registry_document",
    "verify_plan_receipt",
]
