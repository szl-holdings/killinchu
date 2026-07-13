#!/usr/bin/env python3
"""Fail if Killinchu's public JSON contracts regress to SPA HTML or 404."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


CHECKS = (
    ("/health", {"schema": "szl.killinchu.health/v1", "authority_state": "READ_ONLY"}),
    (
        "/api/killinchu/v1/status",
        {"schema": "szl.killinchu.runtime-status/v1", "authority_state": "READ_ONLY"},
    ),
    (
        "/api/killinchu/v1/melt/summary",
        {"schema": "szl.killinchu.melt-summary/v1", "authority_state": "READ_ONLY"},
    ),
    (
        "/.well-known/szl-source.json",
        {"schema": "szl.deployment-source/v1", "alignment_state": "PENDING_GITHUB_SYNC"},
    ),
    ("/openapi.json", {"openapi": "3.1.0"}),
)


def evaluate(
    status_code: int,
    content_type: str,
    body: bytes,
    required: dict[str, Any],
) -> tuple[bool, str]:
    if status_code != 200:
        return False, f"HTTP {status_code}; expected 200"
    if "application/json" not in (content_type or "").lower():
        return False, f"content-type {content_type!r}; likely SPA fallback"
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return False, f"invalid JSON: {type(exc).__name__}"
    if not isinstance(payload, dict):
        return False, "JSON payload is not an object"
    for key, expected in required.items():
        if payload.get(key) != expected:
            return False, f"{key}={payload.get(key)!r}; expected {expected!r}"
    return True, "typed contract verified"


def probe(url: str, timeout: float) -> tuple[int, str, bytes, str | None]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "killinchu-contract-probe/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                response.getcode(),
                response.headers.get("Content-Type", ""),
                response.read(),
                None,
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read(), None
    except Exception as exc:
        return 0, "", b"", f"{type(exc).__name__}: {exc}"


def check(
    base_url: str,
    path: str,
    required: dict[str, Any],
    attempts: int,
    sleep_seconds: float,
    timeout: float,
) -> tuple[bool, str]:
    url = base_url.rstrip("/") + path
    last = "not attempted"
    for attempt in range(1, attempts + 1):
        code, content_type, body, error = probe(url, timeout)
        if error:
            last = error
        else:
            ok, reason = evaluate(code, content_type, body, required)
            if ok:
                return True, f"{reason} on attempt {attempt}"
            last = reason
        if attempt < attempts:
            time.sleep(sleep_seconds)
    return False, f"{last} after {attempts} attempt(s)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=15.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)

    failures: list[dict[str, str]] = []
    for path, required in CHECKS:
        ok, reason = check(
            args.base_url,
            path,
            required,
            args.attempts,
            args.sleep,
            args.timeout,
        )
        print(f"{'PASS' if ok else 'FAIL'} {path}: {reason}")
        if not ok:
            failures.append({"path": path, "reason": reason})
    print(json.dumps({"checked": len(CHECKS), "failed": failures}, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
