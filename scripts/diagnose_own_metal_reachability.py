#!/usr/bin/env python3
"""Classify *why* the own-metal box target is unreachable, instead of just timing out.

The killinchu API health check probes two targets: the published Hugging Face
Space and the own-metal box behind a Cloudflare Tunnel. When the box is down,
a generic "request error: timed out" tells an operator nothing about which of
three very different situations they are in:

1. **NXDOMAIN** — the hostname has no DNS record at all. Nobody ever wired it,
   or the record was deleted. Fixing this is a Cloudflare DNS change.
2. **Cloudflare error 1033** — the hostname resolves and Cloudflare answers,
   but no `cloudflared` connector is registered for the tunnel. The DNS is
   correct and the *box* is not running or not connected. Fixing this is on the
   machine, not in Cloudflare.
3. **Anything else** — origin reachable but erroring, TLS failure, 5xx from the
   app itself, and so on. Fixing this is in the application.

Distinguishing 1 from 2 is the whole point: they have different owners and
different fixes, and conflating them is how a red check sits unread for days.

stdlib only, by org policy. Exits 0 always — this script diagnoses, it does not
gate. The blocking gate is the primary-surface check.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

# Cloudflare's tunnel-specific error codes, as rendered in the response body.
# 1033 is the one that matters here: "Argo Tunnel error" / no connector registered.
CLOUDFLARE_TUNNEL_CODES = {
    "1033": "Cloudflare Tunnel has no registered connector — DNS is correct, the box is not connected",
    "1016": "Cloudflare origin DNS error — the tunnel hostname resolves but has no origin",
    "1000": "Cloudflare DNS points at a Cloudflare IP — misconfigured record",
}

DIAGNOSIS_DNS_MISSING = "DNS_RECORD_MISSING"
DIAGNOSIS_TUNNEL_DOWN = "TUNNEL_NOT_CONNECTED"
DIAGNOSIS_ORIGIN_ERROR = "ORIGIN_ERROR"
DIAGNOSIS_REACHABLE = "REACHABLE"
DIAGNOSIS_UNKNOWN = "UNKNOWN"
DIAGNOSIS_CUSTOM_DOMAIN_UNREGISTERED = "CUSTOM_DOMAIN_UNREGISTERED"

OWNERS = {
    DIAGNOSIS_DNS_MISSING: "Cloudflare DNS — create the record for this hostname",
    DIAGNOSIS_TUNNEL_DOWN: "own-metal box — start/reconnect cloudflared for this tunnel",
    DIAGNOSIS_ORIGIN_ERROR: "application on the box",
    DIAGNOSIS_REACHABLE: "nobody — target is reachable",
    DIAGNOSIS_UNKNOWN: "needs manual triage",
    DIAGNOSIS_CUSTOM_DOMAIN_UNREGISTERED: (
        "Hugging Face Space settings — add this hostname as a custom domain on the Space"
    ),
}

# Hugging Face serves its own 404 page when a request arrives with a Host header
# the Space does not recognise. A bare CNAME to *.hf.space is therefore not
# enough: the hostname must also be registered on the Space itself. Detecting
# this specifically matters because the fix is a Space setting, not DNS and not
# the application.
HF_404_MARKERS = ("huggingface", "hugging face")


def resolve(hostname: str) -> tuple[bool, list[str], str]:
    """Return (resolved, addresses, error)."""
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        return False, [], f"{exc.__class__.__name__}: {exc}"
    except OSError as exc:
        return False, [], f"{exc.__class__.__name__}: {exc}"
    addrs = sorted({info[4][0] for info in infos})
    return True, addrs, ""


def fetch(url: str, timeout: float) -> tuple[int, str, str]:
    """Return (status, body_prefix, error). Status 0 means no HTTP response."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "killinchu-own-metal-diagnose/1.0", "Accept": "*/*"},
    )
    # Read generously: Cloudflare's HTML interstitial puts the numeric error code
    # well past the first couple of kilobytes, so a short read silently loses the
    # single most diagnostic string in the whole response.
    max_body = 65536
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read(max_body).decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(max_body).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - body is best-effort
            pass
        return exc.code, body, ""
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as exc:
        return 0, "", f"{exc.__class__.__name__}: {exc}"


def classify(hostname: str, url: str, timeout: float) -> dict:
    resolved, addrs, dns_error = resolve(hostname)

    if not resolved:
        return {
            "hostname": hostname,
            "url": url,
            "dns_resolved": False,
            "addresses": [],
            "dns_error": dns_error,
            "http_status": None,
            "cloudflare_error_code": None,
            "diagnosis": DIAGNOSIS_DNS_MISSING,
            "owner": OWNERS[DIAGNOSIS_DNS_MISSING],
            "detail": (
                f"{hostname} does not resolve. No DNS record exists for this hostname, "
                "so no tunnel or origin can possibly answer for it."
            ),
        }

    status, body, http_error = fetch(url, timeout)

    cf_code = None
    for code in CLOUDFLARE_TUNNEL_CODES:
        if f"error code: {code}" in body:
            cf_code = code
            break

    if cf_code is not None:
        diagnosis = DIAGNOSIS_TUNNEL_DOWN if cf_code == "1033" else DIAGNOSIS_ORIGIN_ERROR
        detail = (
            f"{hostname} resolves to {', '.join(addrs)} and Cloudflare answered "
            f"HTTP {status} with error code {cf_code}: {CLOUDFLARE_TUNNEL_CODES[cf_code]}."
        )
    elif status == 530:
        # Cloudflare returns 530 as the HTTP surface for the 1033 tunnel family.
        # Trust the status even when the body was truncated or not returned, so a
        # missing interstitial cannot downgrade this to a vague ORIGIN_ERROR.
        diagnosis = DIAGNOSIS_TUNNEL_DOWN
        detail = (
            f"{hostname} resolves to {', '.join(addrs)} and Cloudflare answered HTTP 530, "
            "its surface for the 1033 tunnel family: the hostname is wired but no "
            "cloudflared connector is registered."
        )
    elif status == 0:
        diagnosis = DIAGNOSIS_UNKNOWN
        detail = f"{hostname} resolves to {', '.join(addrs)} but no HTTP response: {http_error}"
    elif 200 <= status < 400:
        diagnosis = DIAGNOSIS_REACHABLE
        detail = f"{hostname} answered HTTP {status}."
    elif status == 404 and any(m in body.lower() for m in HF_404_MARKERS):
        diagnosis = DIAGNOSIS_CUSTOM_DOMAIN_UNREGISTERED
        detail = (
            f"{hostname} resolves and reaches Hugging Face, which returned its own 404 page. "
            "The DNS record is correct but the hostname is not registered as a custom domain "
            "on the target Space, so HF does not route the Host header to it."
        )
    else:
        diagnosis = DIAGNOSIS_ORIGIN_ERROR
        detail = f"{hostname} answered HTTP {status} with no Cloudflare tunnel error code."

    return {
        "hostname": hostname,
        "url": url,
        "dns_resolved": True,
        "addresses": addrs,
        "dns_error": "",
        "http_status": status or None,
        "cloudflare_error_code": cf_code,
        "diagnosis": diagnosis,
        "owner": OWNERS[diagnosis],
        "detail": detail,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        default=[],
        help="Base URL of a target to classify (repeatable).",
    )
    ap.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout seconds.")
    ap.add_argument("--summary-file", default="", help="Optional path for a JSON summary.")
    args = ap.parse_args(argv)

    results = []
    for raw in args.url:
        base = raw.rstrip("/")
        hostname = urlparse(base).hostname or ""
        result = classify(hostname, base + "/healthz", args.timeout)
        results.append(result)

        print(f"== reachability: {hostname} ==")
        print(f"  diagnosis: {result['diagnosis']}")
        print(f"  owner:     {result['owner']}")
        print(f"  detail:    {result['detail']}")
        print()

    reachable = sum(1 for r in results if r["diagnosis"] == DIAGNOSIS_REACHABLE)
    print(f"RESULT: {reachable}/{len(results)} target(s) reachable")

    summary = {
        "checked": len(results),
        "reachable": reachable,
        "worst_diagnosis": (
            DIAGNOSIS_REACHABLE
            if reachable == len(results)
            else next(r["diagnosis"] for r in results if r["diagnosis"] != DIAGNOSIS_REACHABLE)
        ),
        "targets": results,
    }

    if args.summary_file:
        with open(args.summary_file, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, sort_keys=True)
        print(f"wrote summary -> {args.summary_file}")

    # Always 0: this script classifies, it never gates.
    return 0


if __name__ == "__main__":
    sys.exit(main())
