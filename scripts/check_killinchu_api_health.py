#!/usr/bin/env python3
"""
check_killinchu_api_health.py — standing health check for killinchu's live API.

Doctrine v11: the deployed /api/killinchu/* endpoints must keep returning JSON
(content-type application/json) carrying the envelope {status, citations,
fetchedAt} — NOT the SPA HTML the front-door serves. This script probes one or
more live targets and FAILS (non-zero exit) if any endpoint regresses (non-200,
non-JSON content-type, unparseable body, or a missing envelope field),
tolerating transient rebuild/restart states via bounded retries.

Stdlib only (urllib) so it runs on a clean ubuntu-latest with no `pip install`
and no third-party GitHub Action (org policy: github-owned/verified actions only).

Usage:
  check_killinchu_api_health.py \
      --target box=https://killinchu.a11oy.net \
      --target hf=https://szlholdings-killinchu.hf.space \
      [--summary-file out.json] [--attempts 5] [--sleep 15] [--timeout 20]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Each endpoint + the Doctrine v11 envelope field(s) it MUST carry.
# /healthz is the lightweight liveness probe (carries `status`); the
# /api/killinchu/* endpoints carry the full {status, citations, fetchedAt}.
CHECKS = [
    {"path": "/healthz", "required": ["status"]},
    {"path": "/api/killinchu/db/health", "required": ["status", "citations", "fetchedAt"]},
    {"path": "/api/killinchu/watchlists", "required": ["status", "citations", "fetchedAt"]},
    # /elite "Research & Sources" tab data. Own shape (no v11 envelope); the
    # ``honest`` flag is the doctrine honesty marker — requiring it means a tab
    # that silently drops its honesty disclosure also turns the check red.
    {"path": "/api/killinchu/v1/research", "required": ["honest", "source_pool", "tabs_with_overrides"]},
    {"path": "/api/killinchu/v1/research/live", "required": ["honest", "tab", "sources"]},
]


def evaluate(status_code, content_type, body_bytes, required):
    """Pure check of one HTTP response. Returns (ok: bool, reason: str).

    A regression is: not 200, content-type not application/json (the SPA-HTML
    fallback returning 200), an unparseable / non-object body, or a missing
    Doctrine v11 envelope field.
    """
    if status_code != 200:
        return False, f"HTTP {status_code} (want 200)"
    ct = (content_type or "").lower()
    if "application/json" not in ct:
        return False, (
            f"content-type '{content_type or 'none'}' is not application/json "
            "(likely SPA HTML)"
        )
    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any decode/parse error is a regression
        return False, f"body is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return False, "JSON payload is not an object"
    missing = [f for f in required if f not in data]
    if missing:
        return False, f"missing Doctrine v11 envelope field(s): {', '.join(missing)}"
    return True, "ok"


def probe_once(url, timeout):
    """Single HTTP GET. Returns (status_code, content_type, body_bytes, err)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "killinchu-api-health/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.headers.get("Content-Type", ""), resp.read(), None
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            pass
        ct = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, ct, body, None
    except Exception as exc:  # noqa: BLE001 - URLError / timeout / DNS / TLS
        return 0, "", b"", str(exc)


def check_endpoint(base, path, required, attempts, sleep_s, timeout):
    """Probe one endpoint with bounded retries. Returns (ok, reason, url)."""
    url = base.rstrip("/") + path
    last = "no attempt made"
    for attempt in range(1, attempts + 1):
        code, ct, body, err = probe_once(url, timeout)
        if err is not None:
            last = f"request error: {err}"
        else:
            ok, reason = evaluate(code, ct, body, required)
            if ok:
                return True, f"200 application/json, envelope OK (attempt {attempt})", url
            last = reason
        if attempt < attempts:
            time.sleep(sleep_s)
    return False, f"{last} (sustained over {attempts} attempts)", url


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Killinchu live API health check (Doctrine v11 JSON envelope)."
    )
    ap.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="LABEL=BASE_URL",
        help="Target to probe, e.g. box=https://killinchu.a11oy.net (repeatable).",
    )
    ap.add_argument("--attempts", type=int, default=5, help="Retry attempts per endpoint (default 5).")
    ap.add_argument("--sleep", type=float, default=15.0, help="Seconds between retries (default 15).")
    ap.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout seconds (default 20).")
    ap.add_argument("--summary-file", default="", help="Optional path to write a JSON result summary.")
    args = ap.parse_args(argv)

    if not args.target:
        print("ERROR: at least one --target LABEL=BASE_URL is required", file=sys.stderr)
        return 2

    targets = []
    for t in args.target:
        if "=" not in t:
            print(f"ERROR: bad --target '{t}', expected LABEL=BASE_URL", file=sys.stderr)
            return 2
        label, base = t.split("=", 1)
        label, base = label.strip(), base.strip()
        if not label or not base:
            print(f"ERROR: bad --target '{t}', expected non-empty LABEL=BASE_URL", file=sys.stderr)
            return 2
        targets.append((label, base))

    checked = 0
    passed = 0
    failures = []
    print(
        f"Killinchu live API health check — {len(targets)} target(s) x "
        f"{len(CHECKS)} endpoint(s) (attempts={args.attempts}, sleep={args.sleep}s)"
    )
    for label, base in targets:
        print(f"\n== target: {label} ({base}) ==")
        for chk in CHECKS:
            checked += 1
            ok, reason, url = check_endpoint(
                base, chk["path"], chk["required"], args.attempts, args.sleep, args.timeout
            )
            if ok:
                passed += 1
                print(f"  PASS {chk['path']:<28} {reason}")
            else:
                print(f"  FAIL {chk['path']:<28} {reason}")
                failures.append(
                    {"target": label, "url": url, "path": chk["path"], "reason": reason}
                )

    failed = len(failures)
    print(f"\nRESULT: checked={checked} passed={passed} failed={failed}")

    summary = {"checked": checked, "passed": passed, "failed": failed, "failures": failures}
    if args.summary_file:
        with open(args.summary_file, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"Wrote summary -> {args.summary_file}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
