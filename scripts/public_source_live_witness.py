#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Credential-free live witness for Killinchu Public Source Fabric v1.

The witness performs GET requests only against two fixed origins: GitHub's API
for the protected-main revision and the public Killinchu Space for deployment
identity and public-source contracts. It neither accepts arbitrary target URLs
nor records source bodies, sanctions names, credentials, or personal data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = "https://szlholdings-killinchu.hf.space"
SCHEMA = "szl.killinchu.public-source-fabric/v1"
WITNESS_SCHEMA = "szl.killinchu.public-source-live-witness/v1"
USER_AGENT = "szl-killinchu-public-source-live-witness/1.0"
SOURCE_IDS = {
    "cisa-kev",
    "nsa-advisories",
    "cia-public-stories",
    "ofac-sdn",
    "un-dprk-1718",
    "cert-ua-advisories",
    "ukraine-open-data-metadata",
    "china-cac-notices",
}
MAX_RESPONSE_BYTES = 5_000_000
PROHIBITED_CONTENT_KEYS = (
    "active_force_geolocation",
    "target_or_strike_packages",
    "leaked_or_stolen_data",
    "credentials_or_personal_dossiers",
    "malware_or_exploit_payloads",
    "dark_web_collection",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def request_json(url: str, timeout: int = 45) -> tuple[int, dict[str, Any], bytes]:
    """GET one fixed witness URL and return bounded JSON, including HTTP errors."""
    allowed_prefixes = (
        f"{BASE}/",
        os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/") + "/",
    )
    if not url.startswith(allowed_prefixes):
        raise ValueError("witness URL is outside the fixed origin allowlist")
    headers = {
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "User-Agent": USER_AGENT,
    }
    if url.startswith(allowed_prefixes[1]):
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        status = int(error.code)
        raw = error.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("response exceeded the witness size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as error:
        raise RuntimeError(
            f"non-JSON response: {type(error).__name__}"
        ) from error
    if not isinstance(payload, dict):
        raise RuntimeError("witness response is not a JSON object")
    return status, payload, raw


def current_main() -> str:
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    repository = os.environ.get("GITHUB_REPOSITORY", "szl-holdings/killinchu")
    status, payload, _raw = request_json(
        f"{api_url}/repos/{repository}/commits/main",
        timeout=20,
    )
    if status != 200:
        raise RuntimeError(f"GitHub main lookup returned HTTP {status}")
    revision = str(payload.get("sha") or "").lower()
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise RuntimeError("GitHub did not return an exact main revision")
    return revision


def expected_revision() -> str:
    event_name = os.environ.get("EVENT_NAME", "")
    workflow_head = os.environ.get("WORKFLOW_HEAD_SHA", "").strip().lower()
    main = current_main()
    if event_name != "workflow_run" or len(workflow_head) != 40:
        return main
    if workflow_head != main:
        raise RuntimeError(
            "refusing stale post-deployment witness: "
            f"workflow_head={workflow_head} current_main={main}"
        )
    return workflow_head


def _require_policy(payload: dict[str, Any]) -> None:
    assert payload.get("schema") == SCHEMA
    assert payload.get("state") == "DECLARED"
    assert payload.get("action_authority") == "NONE"
    policy = payload.get("policy") or {}
    network = policy.get("network") or {}
    content = policy.get("content") or {}
    authority = policy.get("authority") or {}
    assert network.get("method") == "GET_ONLY"
    assert network.get("arbitrary_url_input") is False
    assert network.get("authentication_bypass") is False
    assert network.get("credential_use") is False
    assert network.get("protected_resources") is False
    for key in PROHIBITED_CONTENT_KEYS:
        assert content.get(key) == "PROHIBITED", (key, content.get(key))
    assert authority.get("action_authority") == "NONE"
    assert authority.get("automated_targeting") is False
    assert authority.get("automated_enforcement") is False
    assert authority.get("human_review_required") is True


def _require_sources(payload: dict[str, Any]) -> set[str]:
    assert payload.get("schema") == SCHEMA
    assert payload.get("source_count") == len(SOURCE_IDS)
    assert payload.get("action_authority") == "NONE"
    rows = payload.get("sources") or []
    observed = {
        str(row.get("source_id")) for row in rows if isinstance(row, dict)
    }
    assert observed == SOURCE_IDS, (observed, SOURCE_IDS)
    assert all(
        str(row.get("url") or "").startswith("https://")
        and str(row.get("classification") or "")
        for row in rows
    )
    return observed


def _require_health(payload: dict[str, Any]) -> None:
    assert payload.get("schema") == SCHEMA
    assert payload.get("total_sources") == len(SOURCE_IDS)
    assert payload.get("state") in {"UNTESTED", "CACHED"}
    assert payload.get("action_authority") == "NONE"
    rows = payload.get("sources") or []
    assert len(rows) == len(SOURCE_IDS)
    assert all(
        isinstance(row, dict)
        and row.get("mode") in {"UNTESTED", "CACHED"}
        for row in rows
    )


def _require_cisa(status: int, payload: dict[str, Any]) -> None:
    assert status in {200, 503}
    assert payload.get("schema") == SCHEMA
    assert payload.get("source_id") == "cisa-kev"
    assert payload.get("mode") in {"LIVE", "CACHED", "UNAVAILABLE"}
    assert payload.get("action_authority") == "NONE"
    assert len(payload.get("items") or []) <= 1
    if payload.get("mode") in {"LIVE", "CACHED"}:
        assert status == 200
        assert len(str(payload.get("content_sha256") or "")) == 64
    else:
        assert status == 503
        assert not (payload.get("items") or [])


def _require_sanctions(status: int, payload: dict[str, Any]) -> None:
    assert status in {200, 503}
    assert payload.get("verdict") in {
        "POSSIBLE_MATCH",
        "NO_EXACT_MATCH",
        "BLOCKED_PENDING",
    }
    assert payload.get("verdict") != "CLEAR"
    assert payload.get("action_authority") == "NONE"
    assert payload.get("manual_review_required") is True
    if payload.get("verdict") == "BLOCKED_PENDING":
        assert status == 503
    else:
        assert status == 200


def observe(expected: str) -> dict[str, Any]:
    build_status, build, build_raw = request_json(f"{BASE}/api/build-info", 25)
    if build_status != 200:
        raise RuntimeError(f"build-info HTTP {build_status}")
    live_revision = str((build.get("build") or {}).get("revision") or "").lower()
    if live_revision != expected:
        raise RuntimeError(
            f"live revision mismatch: expected={expected} observed={live_revision}"
        )

    policy_status, policy, policy_raw = request_json(
        f"{BASE}/api/killinchu/v1/osint/public/policy", 25
    )
    sources_status, sources, sources_raw = request_json(
        f"{BASE}/api/killinchu/v1/osint/public/sources", 25
    )
    health_status, health, health_raw = request_json(
        f"{BASE}/api/killinchu/v1/osint/public/health", 25
    )
    cisa_status, cisa, cisa_raw = request_json(
        f"{BASE}/api/killinchu/v1/osint/public/source/cisa-kev?limit=1", 45
    )
    sanctions_query = urllib.parse.urlencode(
        {"name": "SZL PUBLIC SOURCE WITNESS NONMATCH"}
    )
    sanctions_status, sanctions, sanctions_raw = request_json(
        f"{BASE}/api/killinchu/v1/osint/public/sanctions/screen?{sanctions_query}",
        90,
    )

    assert policy_status == 200
    assert sources_status == 200
    assert health_status == 200
    _require_policy(policy)
    source_ids = _require_sources(sources)
    _require_health(health)
    _require_cisa(cisa_status, cisa)
    _require_sanctions(sanctions_status, sanctions)

    return {
        "schema": WITNESS_SCHEMA,
        "observed_at": utc_now(),
        "space": "SZLHOLDINGS/killinchu",
        "origin": BASE,
        "expected_source_revision": expected,
        "observed_source_revision": live_revision,
        "status": "PASS",
        "authority": "READ_ONLY_WITNESS",
        "action_authority": "NONE",
        "contracts": {
            "build": {
                "http": build_status,
                "sha256": hashlib.sha256(build_raw).hexdigest(),
            },
            "policy": {
                "http": policy_status,
                "sha256": hashlib.sha256(policy_raw).hexdigest(),
            },
            "sources": {
                "http": sources_status,
                "source_ids": sorted(source_ids),
                "sha256": hashlib.sha256(sources_raw).hexdigest(),
            },
            "health": {
                "http": health_status,
                "state": health.get("state"),
                "tested_sources": health.get("tested_sources"),
                "sha256": hashlib.sha256(health_raw).hexdigest(),
            },
            "cisa_kev": {
                "http": cisa_status,
                "mode": cisa.get("mode"),
                "item_count": cisa.get("item_count"),
                "returned_item_count": cisa.get("returned_item_count"),
                "content_sha256": cisa.get("content_sha256"),
                "response_sha256": hashlib.sha256(cisa_raw).hexdigest(),
            },
            "sanctions_screen": {
                "http": sanctions_status,
                "verdict": sanctions.get("verdict"),
                "coverage": sanctions.get("coverage"),
                "sources_available": sanctions.get("sources_available"),
                "receipt_sha256": sanctions.get("receipt_sha256"),
                "response_sha256": hashlib.sha256(sanctions_raw).hexdigest(),
            },
        },
        "prohibited_capabilities_observed": [],
    }


def run(output: Path, retry_seconds: int = 420) -> dict[str, Any]:
    expected = expected_revision()
    deadline = time.monotonic() + max(0, retry_seconds)
    last_error = "NO_ATTEMPT"
    while True:
        try:
            evidence = observe(expected)
            output.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return evidence
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            if time.monotonic() >= deadline:
                break
            time.sleep(10)
    failure = {
        "schema": WITNESS_SCHEMA,
        "observed_at": utc_now(),
        "space": "SZLHOLDINGS/killinchu",
        "origin": BASE,
        "expected_source_revision": expected,
        "status": "FAIL",
        "last_error": last_error,
        "action_authority": "NONE",
    }
    output.write_text(
        json.dumps(failure, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raise RuntimeError(last_error)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public-source-live-witness.json"),
    )
    parser.add_argument("--retry-seconds", type=int, default=420)
    args = parser.parse_args()
    evidence = run(args.output, retry_seconds=args.retry_seconds)
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
