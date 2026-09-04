#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Credential-free exact-source witness for Defensive Fusion Wave 4."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = "https://szlholdings-killinchu.hf.space"
GITHUB_API = "https://api.github.com/repos/szl-holdings/killinchu/commits/main"
FUSION_PATH = "/api/killinchu/v1/connectors/defensive_fusion/read?limit=1&q=CVE-2021-44228"
MAX_BYTES = 2_000_000


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_json(url: str, timeout: int = 30) -> tuple[int, dict[str, Any], bytes]:
    if not (url.startswith(BASE + "/") or url == GITHUB_API):
        raise ValueError("URL outside fixed witness allowlist")
    headers = {"Accept": "application/json", "User-Agent": "szl-defensive-fusion-witness/1.0"}
    if url == GITHUB_API and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers, method="GET")
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
    status, payload, _ = get_json(GITHUB_API, 20)
    if status != 200:
        raise RuntimeError(f"GitHub main returned {status}")
    sha = str(payload.get("sha") or "").lower()
    if len(sha) != 40:
        raise RuntimeError("main revision is not exact")
    return sha


def observe() -> dict[str, Any]:
    expected = expected_revision()
    status, build, build_raw = get_json(BASE + "/api/build-info", 25)
    if status != 200:
        raise RuntimeError(f"build-info returned {status}")
    observed = str((build.get("build") or {}).get("revision") or "").lower()
    if observed != expected:
        raise RuntimeError(f"source mismatch expected={expected} observed={observed}")

    fusion_status, fusion, fusion_raw = get_json(BASE + FUSION_PATH, 45)
    if fusion_status != 200:
        raise RuntimeError(f"fusion route returned {fusion_status}")
    if fusion.get("connector_id") != "defensive_fusion":
        raise RuntimeError("wrong connector identity")
    state = str(fusion.get("state") or "")
    if state not in {"connected", "error", "ready"}:
        raise RuntimeError(f"unexpected honest state {state!r}")
    records = fusion.get("records") or []
    if state == "connected":
        if len(records) != 1:
            raise RuntimeError("connected fusion must return one exact-CVE record")
        row = records[0]
        assert row["cve"] == "CVE-2021-44228"
        assert row["coverage"] in {"FULL", "PARTIAL"}
        assert row["action_authority"] == "DEFENSIVE_PRIORITIZATION_ONLY"
        assert row["human_approval_required"] is True
        assert row["exploit_content_included"] is False
        assert row["asset_scanning_performed"] is False
        assert float(row["priority_score"]) <= 0.99
        assert len(row["normalized_evidence_sha256"]) == 64
        safe_result = {
            "cve": row["cve"],
            "priority": row["priority"],
            "coverage": row["coverage"],
            "sources_measured": row["sources_measured"],
            "normalized_evidence_sha256": row["normalized_evidence_sha256"],
            "action_authority": row["action_authority"],
        }
    else:
        if records:
            raise RuntimeError("non-connected state must not fabricate records")
        safe_result = {"state": state, "record_count": 0, "note": fusion.get("note")}

    return {
        "schema": "szl.killinchu.defensive-fusion-live-witness/v1",
        "status": "PASS",
        "observed_at": now(),
        "expected_source_revision": expected,
        "observed_source_revision": observed,
        "authority": "READ_ONLY_WITNESS",
        "build_response_sha256": hashlib.sha256(build_raw).hexdigest(),
        "fusion_response_sha256": hashlib.sha256(fusion_raw).hexdigest(),
        "fusion": safe_result,
    }


def run(output: Path, retry_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, retry_seconds)
    last = "NO_ATTEMPT"
    while True:
        try:
            evidence = observe()
            output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return evidence
        except Exception as error:
            last = f"{type(error).__name__}: {error}"
            if time.monotonic() >= deadline:
                break
            time.sleep(10)
    failure = {"schema": "szl.killinchu.defensive-fusion-live-witness/v1", "status": "FAIL", "observed_at": now(), "last_error": last}
    output.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raise RuntimeError(last)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("defensive-fusion-live-witness.json"))
    parser.add_argument("--retry-seconds", type=int, default=600)
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.retry_seconds), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
