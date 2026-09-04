#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SZL Holdings
"""Credential-free exact-source witness for Asset Exposure Wave 5."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.request


BASE = "https://szlholdings-killinchu.hf.space"
GITHUB_API = "https://api.github.com/repos/szl-holdings/killinchu/commits/main"
BUILD_URL = BASE + "/api/build-info"
EXPOSURE_URL = BASE + "/api/killinchu/uds/v1/sbom/exposure/evaluate"
MAX_BYTES = 2_000_000

WITNESS_ASSET = "witness:synthetic:wave5"
WITNESS_COMPONENT = "pkg:maven/log4j-core@2.14.1"
WITNESS_CVE = "CVE-2021-44228"
WITNESS_PAYLOAD = {
    "asset": {
        "asset_id": WITNESS_ASSET,
        "name": "Synthetic Wave 5 Witness",
        "owner": "SZL Public Verification",
        "environment": "synthetic",
        "criticality": 5,
        "exposure": "internet",
    },
    "sbom": {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:szl-wave5-live-witness",
        "metadata": {
            "component": {
                "name": "synthetic-wave5-witness",
            }
        },
        "components": [
            {
                "type": "library",
                "bom-ref": WITNESS_COMPONENT,
                "name": "log4j-core",
                "version": "2.14.1",
                "purl": WITNESS_COMPONENT,
            }
        ],
    },
    "findings": [
        {
            "component_ref": WITNESS_COMPONENT,
            "cve": WITNESS_CVE,
            "status": "affected",
            "evidence_ref": "synthetic-public-witness",
        }
    ],
}


def now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _request_json(
    url: str,
    *,
    method: str,
    body: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any], bytes]:
    allowed = {
        (GITHUB_API, "GET"),
        (BUILD_URL, "GET"),
        (EXPOSURE_URL, "POST"),
    }
    if (url, method) not in allowed:
        raise ValueError("request outside fixed witness allowlist")
    if body is not None and len(body) > MAX_BYTES:
        raise ValueError("witness request exceeded limit")

    headers = {
        "Accept": "application/json",
        "User-Agent": "szl-asset-exposure-witness/1.0",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if url == GITHUB_API and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        headers["X-GitHub-Api-Version"] = "2022-11-28"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read(MAX_BYTES + 1)

    if len(raw) > MAX_BYTES:
        raise RuntimeError("witness response exceeded limit")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("witness response is not an object")
    return status, payload, raw


def expected_revision() -> str:
    status, payload, _ = _request_json(
        GITHUB_API,
        method="GET",
        timeout=20,
    )
    if status != 200:
        raise RuntimeError(f"GitHub main returned {status}")
    sha = str(payload.get("sha") or "").lower()
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise RuntimeError("main revision is not an exact lowercase SHA")
    return sha


def _digest(value: Any, field: str) -> str:
    digest = str(value or "").lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise RuntimeError(f"{field} is not a lowercase SHA-256 digest")
    return digest


def _validate_exposure(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "szl.killinchu.sbom-exposure/v1":
        raise RuntimeError("wrong Wave 5 schema")
    state = str(payload.get("state") or "").upper()
    if state not in {"MEASURED", "PARTIAL", "UNAVAILABLE"}:
        raise RuntimeError(f"unexpected Wave 5 state: {state!r}")

    asset = payload.get("asset")
    if not isinstance(asset, dict) or asset.get("asset_id") != WITNESS_ASSET:
        raise RuntimeError("witness asset identity was not preserved")
    if payload.get("action_authority") != "DEFENSIVE_REMEDIATION_PLANNING_ONLY":
        raise RuntimeError("wrong Wave 5 authority")
    if payload.get("human_approval_required") is not True:
        raise RuntimeError("human approval boundary missing")
    for field in (
        "asset_scanning_performed",
        "sbom_fetched_remotely",
        "component_vulnerability_inference_performed",
        "third_party_mutation_performed",
        "data_persisted",
    ):
        if payload.get(field) is not False:
            raise RuntimeError(f"unsafe or missing boundary: {field}")
    if payload.get("truth_label") != (
        "OPERATOR_SUPPLIED_EXPOSURE_WITH_OFFICIAL_CVE_EVIDENCE"
    ):
        raise RuntimeError("wrong Wave 5 truth label")

    formula = payload.get("formula")
    if not isinstance(formula, dict):
        raise RuntimeError("formula evidence is missing")
    if formula.get("id") != "killinchu.asset-exposure-priority/v1":
        raise RuntimeError("wrong Wave 5 formula identity")
    if formula.get("probability_claimed") is not False:
        raise RuntimeError("Wave 5 must not claim probability")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("Wave 5 summary is missing")
    if summary.get("component_count") != 1:
        raise RuntimeError("witness SBOM component count drifted")
    if summary.get("finding_count") != 1 or summary.get("active_findings") != 1:
        raise RuntimeError("witness finding count drifted")

    queue = payload.get("remediation_queue")
    if not isinstance(queue, list) or len(queue) != 1:
        raise RuntimeError("Wave 5 must return one witness queue item")
    row = queue[0]
    if not isinstance(row, dict):
        raise RuntimeError("Wave 5 queue item is not an object")
    if row.get("component_ref") != WITNESS_COMPONENT:
        raise RuntimeError("witness component reference drifted")
    if row.get("cve") != WITNESS_CVE:
        raise RuntimeError("witness CVE drifted")
    if row.get("active") is not True:
        raise RuntimeError("witness finding unexpectedly inactive")
    lane = str(row.get("remediation_lane") or "")
    if lane not in {"P0", "P1", "P2", "P3", "REVIEW"}:
        raise RuntimeError("invalid remediation lane")
    score = row.get("asset_priority_score")
    if score is not None and not 0.0 <= float(score) <= 0.99:
        raise RuntimeError("asset priority score is outside its bound")

    if state == "MEASURED":
        if summary.get("officially_resolved_findings") != 1:
            raise RuntimeError("measured report lacks one resolved finding")
        if summary.get("full_source_coverage_findings") != 1:
            raise RuntimeError("measured report lacks full source coverage")
        if row.get("source_state") != "CONNECTED":
            raise RuntimeError("measured queue item is not connected")
        if row.get("source_coverage") != "FULL":
            raise RuntimeError("measured queue item lacks full source coverage")
    elif state == "UNAVAILABLE":
        if lane != "REVIEW" or score is not None:
            raise RuntimeError("unavailable evidence must remain REVIEW without score")

    return {
        "state": state,
        "asset_id": asset["asset_id"],
        "cve": row["cve"],
        "component_ref": row["component_ref"],
        "remediation_lane": lane,
        "asset_priority_score": score,
        "defensive_priority": row.get("defensive_priority"),
        "source_state": row.get("source_state"),
        "source_coverage": row.get("source_coverage"),
        "evidence_sha256": _digest(
            payload.get("evidence_sha256"),
            "evidence_sha256",
        ),
        "normalized_input_sha256": _digest(
            payload.get("normalized_input_sha256"),
            "normalized_input_sha256",
        ),
        "sbom_input_sha256": _digest(
            payload.get("sbom_input_sha256"),
            "sbom_input_sha256",
        ),
        "action_authority": payload["action_authority"],
    }


def observe() -> dict[str, Any]:
    expected = expected_revision()
    build_status, build, build_raw = _request_json(
        BUILD_URL,
        method="GET",
        timeout=25,
    )
    if build_status != 200:
        raise RuntimeError(f"build-info returned {build_status}")
    observed = str((build.get("build") or {}).get("revision") or "").lower()
    if observed != expected:
        raise RuntimeError(
            f"source mismatch expected={expected} observed={observed}"
        )

    request_raw = json.dumps(
        WITNESS_PAYLOAD,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    exposure_status, exposure, exposure_raw = _request_json(
        EXPOSURE_URL,
        method="POST",
        body=request_raw,
        timeout=60,
    )
    if exposure_status != 200:
        raise RuntimeError(f"asset exposure route returned {exposure_status}")
    safe_result = _validate_exposure(exposure)

    return {
        "schema": "szl.killinchu.asset-exposure-live-witness/v1",
        "status": "PASS",
        "observed_at": now(),
        "expected_source_revision": expected,
        "observed_source_revision": observed,
        "authority": "READ_ONLY_SYNTHETIC_WITNESS",
        "request_sha256": hashlib.sha256(request_raw).hexdigest(),
        "build_response_sha256": hashlib.sha256(build_raw).hexdigest(),
        "exposure_response_sha256": hashlib.sha256(exposure_raw).hexdigest(),
        "exposure": safe_result,
    }


def run(output: Path, retry_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, retry_seconds)
    last = "NO_ATTEMPT"
    while True:
        try:
            evidence = observe()
            output.write_text(
                json.dumps(
                    evidence,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            return evidence
        except Exception as error:
            last = f"{type(error).__name__}: {error}"
            if time.monotonic() >= deadline:
                break
            time.sleep(10)

    failure = {
        "schema": "szl.killinchu.asset-exposure-live-witness/v1",
        "status": "FAIL",
        "observed_at": now(),
        "last_error": last,
    }
    output.write_text(
        json.dumps(failure, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raise RuntimeError(last)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("asset-exposure-live-witness.json"),
    )
    parser.add_argument("--retry-seconds", type=int, default=600)
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.retry_seconds), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
