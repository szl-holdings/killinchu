#!/usr/bin/env python3
"""Verify a source-bound refusal; success never means public readiness."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import killinchu_public_route_repair as risk

_KNOWN_REFUSALS = {
    "CI_ATTESTATION_EVIDENCE_UNPROVED", "OPTION_A_REVIEW_EXPIRED",
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(path: Path):
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ValueError("JSON body exceeds 64 KiB")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=risk._reject_non_finite_json_constant,
                      parse_float=risk._parse_finite_json_float)


def expected_refusal(contract, today: date) -> str:
    # Validate the complete checked-in policy before its date gate can mask a
    # malformed control/exception. This does not renew its review deadline.
    for check_date in (risk._OPTION_A_REVIEW_DUE - timedelta(days=1), today):
        try:
            risk._validate_public_risk_contract(contract, today=check_date)
        except risk._PublicRiskContractError as exc:
            if exc.state != "UNAVAILABLE" or exc.reason_code not in _KNOWN_REFUSALS:
                raise ValueError("unexpected checked-in public-risk contract") from exc
            reason = exc.reason_code
        else:
            raise ValueError("public-risk contract no longer requires the expected refusal")
    return reason


def verify(payload, *, http_status: str, source_sha: str, contract, today: date) -> str:
    if http_status != "503":
        raise ValueError("public risk must return HTTP 503")
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None or source_sha == "0" * 40:
        raise ValueError("an exact source SHA is required")
    reason = expected_refusal(contract, today)
    if not isinstance(payload, dict) or payload.get("schema") != "szl.killinchu-public-risk-transition-status/v1":
        raise ValueError("unexpected public-risk response schema")
    if payload.get("state") != "UNAVAILABLE" or payload.get("reason_code") != reason:
        raise ValueError("public risk does not match the dated fail-closed reason")
    observation = payload.get("runtime_observation")
    source = observation.get("source") if isinstance(observation, dict) else None
    if not isinstance(source, dict) or source.get("state") != "OBSERVED" or source.get("revision") != source_sha:
        raise ValueError("public-risk response is not bound to the deployed source")
    return reason


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("--http-status", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    try:
        reason = verify(read_json(args.body), http_status=args.http_status,
                        source_sha=args.source_sha,
                        contract=read_json(ROOT / "public-risk-transition.json"),
                        today=risk._utc_today())
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"public-risk refusal verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified HTTP 503 UNAVAILABLE ({reason}); public readiness is not granted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
