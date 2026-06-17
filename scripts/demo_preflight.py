#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
#
# killinchu demo preflight validator (Dev 8, fable-5).
#
# One-command "is killinchu demo-ready?" check. Given a live base URL it probes
# every demo-critical killinchu surface plus the new dataset/CoT/overlay
# endpoints and prints a GREEN / RED / PENDING preflight table:
#
#   * HTTP status code (the REAL code observed — never asserted)
#   * a content sanity check (CoT export is valid <event> XML, the AIS Aug-2024
#     sample board returns vessels, /elite returns the track board, a receipt
#     ledger has a khipu root, etc.)
#
# DOCTRINE v11 (honesty):
#   * REAL probes only. We never assert a 200 we did not get. The status code in
#     the table is whatever the server actually returned (or a transport error).
#   * Endpoints that only exist on an unmerged branch are labelled
#     "pending PR #N" and reported as PENDING, never RED — a 404 for an
#     un-merged route is expected, not a demo failure. If such a route DOES
#     answer (already merged), it is verified for real and shown GREEN.
#   * A green row requires BOTH a 2xx code AND a passing content check. A 2xx
#     with failing content is RED, not green.
#
# Stdlib only (urllib + xml + argparse) so it runs anywhere python3 runs:
#
#   python3 scripts/demo_preflight.py
#   python3 scripts/demo_preflight.py --base-url https://killinchu.a11oy.net
#   python3 scripts/demo_preflight.py --json            # machine-readable
#   python3 scripts/demo_preflight.py --include-pending  # probe pending routes too
#
# Exit code: 0 if no REQUIRED probe is RED, else 1. PENDING never fails the run.
#
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Optional

DEFAULT_BASE_URL = "https://killinchu.a11oy.net"
DEFAULT_TIMEOUT = 20.0

# Verdicts.
GREEN = "GREEN"
RED = "RED"
PENDING = "PENDING"  # route lives on an unmerged branch; 404 is expected, not a failure


# ---------------------------------------------------------------------------
# Probe result model
# ---------------------------------------------------------------------------
@dataclass
class ProbeResult:
    """Outcome of one probe. `status` is the REAL HTTP code (or None on a
    transport error). `verdict` is GREEN / RED / PENDING. Nothing here is ever
    fabricated: if a request failed, status is None and detail carries the
    error string."""

    name: str
    method: str
    path: str
    status: Optional[int]
    verdict: str
    detail: str
    pending_pr: Optional[int] = None
    elapsed_ms: Optional[int] = None


@dataclass
class Probe:
    """A single demo surface to check.

    content_check: given (status, body_bytes, headers) returns (ok, detail).
    It is only consulted when the HTTP layer produced a response. It must NOT
    raise — wrap risky parsing and report (False, "...") instead.

    pending_pr: if set, this route is expected to be absent on `main` until the
    named PR merges. A 404/405 then yields PENDING (not RED); a real 2xx with a
    passing content check still yields GREEN (already merged → verify for real).
    """

    name: str
    path: str
    content_check: Callable[[Optional[int], bytes, dict], tuple[bool, str]]
    method: str = "GET"
    body: Optional[bytes] = None
    headers: dict = field(default_factory=dict)
    pending_pr: Optional[int] = None
    required: bool = True


# ---------------------------------------------------------------------------
# HTTP (stdlib, no external deps)
# ---------------------------------------------------------------------------
def http_request(
    url: str,
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[Optional[int], bytes, dict]:
    """Perform one request. Returns (status, body, headers).

    status is the REAL HTTP code. On an HTTP error response (4xx/5xx) we still
    return the real code and body (urllib raises HTTPError which carries both).
    On a transport-level failure (DNS, TLS, timeout) status is None and the
    body carries the error text. This function never raises."""

    req = urllib.request.Request(url, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    req.add_header("User-Agent", "killinchu-demo-preflight/1.0 (+doctrine-v11)")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted base URL)
            data = resp.read()
            return resp.status, data, dict(resp.headers)
    except urllib.error.HTTPError as e:
        # Real HTTP error code + body — honest, this is a real observed status.
        try:
            data = e.read()
        except Exception:
            data = b""
        return e.code, data, dict(e.headers or {})
    except Exception as e:  # transport error: DNS/TLS/timeout/connection reset
        return None, ("transport error: %s" % e).encode("utf-8"), {}


# ---------------------------------------------------------------------------
# Verdict logic (pure — unit tested)
# ---------------------------------------------------------------------------
def classify(
    status: Optional[int],
    content_ok: bool,
    content_detail: str,
    pending_pr: Optional[int],
) -> tuple[str, str]:
    """Decide the verdict for one probe from its REAL status + content check.

    Rules (Doctrine v11 — never fake green):
      * 2xx AND content_ok            -> GREEN
      * 2xx AND NOT content_ok        -> RED   (got a page, but wrong shape)
      * 404/405 AND pending_pr set    -> PENDING (route not on main yet)
      * anything else                 -> RED
    Returns (verdict, detail)."""

    if status is not None and 200 <= status < 300:
        if content_ok:
            return GREEN, content_detail
        return RED, "HTTP %d but content check failed: %s" % (status, content_detail)

    if pending_pr is not None and status in (404, 405):
        return PENDING, "not on main yet (pending PR #%d); HTTP %d" % (pending_pr, status)

    if status is None:
        return RED, content_detail  # transport error text
    return RED, "unexpected HTTP %d: %s" % (status, content_detail)


def run_probe(base_url: str, probe: Probe, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    url = base_url.rstrip("/") + probe.path
    t0 = time.monotonic()
    status, body, headers = http_request(
        url, method=probe.method, body=probe.body, headers=probe.headers, timeout=timeout
    )
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if status is not None and 200 <= status < 300:
        try:
            content_ok, content_detail = probe.content_check(status, body, headers)
        except Exception as e:  # a content check must never crash the run
            content_ok, content_detail = False, "content check raised: %r" % e
    else:
        # No 2xx body to validate; carry the transport/error text through.
        content_ok = False
        content_detail = body.decode("utf-8", "replace")[:200] if body else "no response body"

    verdict, detail = classify(status, content_ok, content_detail, probe.pending_pr)
    return ProbeResult(
        name=probe.name,
        method=probe.method,
        path=probe.path,
        status=status,
        verdict=verdict,
        detail=detail,
        pending_pr=probe.pending_pr,
        elapsed_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Content sanity checks (each returns (ok, detail); must not raise on bad input)
# ---------------------------------------------------------------------------
def _json_load(body: bytes):
    return json.loads(body.decode("utf-8", "replace"))


def check_nonempty_html(_s, body, _h) -> tuple[bool, str]:
    text = body.decode("utf-8", "replace")
    low = text.lower()
    if "<html" in low or "<!doctype html" in low or "<div" in low:
        return True, "HTML page (%d bytes)" % len(body)
    return False, "not HTML (%d bytes)" % len(body)


def check_elite_board(_s, body, _h) -> tuple[bool, str]:
    text = body.decode("utf-8", "replace")
    low = text.lower()
    if "<html" not in low and "<!doctype" not in low:
        return False, "not an HTML document (%d bytes)" % len(body)
    # The track/governance board mentions killinchu / counter-uas / track somewhere.
    for marker in ("killinchu", "counter-uas", "track", "elite", "governance"):
        if marker in low:
            return True, "track board HTML (marker=%r, %d bytes)" % (marker, len(body))
    return False, "HTML but no board marker (%d bytes)" % len(body)


def check_healthz(_s, body, _h) -> tuple[bool, str]:
    try:
        d = _json_load(body)
    except Exception as e:
        return False, "not JSON: %s" % e
    if str(d.get("status", "")).lower() in ("ok", "ready", "healthy"):
        return True, "status=%s service=%s" % (d.get("status"), d.get("service", "?"))
    return False, "status field missing/unexpected: %r" % d.get("status")


def check_json_has(keys: tuple[str, ...]) -> Callable:
    def _chk(_s, body, _h) -> tuple[bool, str]:
        try:
            d = _json_load(body)
        except Exception as e:
            return False, "not JSON: %s" % e
        if not isinstance(d, dict):
            return False, "JSON is not an object (%s)" % type(d).__name__
        missing = [k for k in keys if k not in d]
        if missing:
            return False, "missing keys: %s" % ", ".join(missing)
        return True, "keys present: %s" % ", ".join(keys)

    return _chk


def _count_list(d) -> Optional[int]:
    """Find a plausible vessel/track list in a JSON payload and return its len."""
    if isinstance(d, list):
        return len(d)
    if isinstance(d, dict):
        for key in ("vessels", "tracks", "records", "rows", "data", "items",
                    "results", "sources", "drones", "threats", "ports", "attacks"):
            v = d.get(key)
            if isinstance(v, list):
                return len(v)
        # nested {"data": {"tracks": [...]}}
        for v in d.values():
            if isinstance(v, dict):
                n = _count_list(v)
                if n is not None:
                    return n
    return None


def check_has_vessels(_s, body, _h) -> tuple[bool, str]:
    try:
        d = _json_load(body)
    except Exception as e:
        return False, "not JSON: %s" % e
    n = _count_list(d)
    if n is None:
        return False, "no vessel/track list found in payload"
    if n <= 0:
        return False, "list present but EMPTY (0 vessels)"
    return True, "%d vessels/tracks returned" % n


def check_cot_xml(_s, body, _h) -> tuple[bool, str]:
    """CoT export must be parseable XML containing at least one <event> with a
    <point> carrying lat/lon attributes (CoT 2.0 shape)."""
    text = body.decode("utf-8", "replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return False, "not well-formed XML: %s" % e
    events = []
    if root.tag == "event":
        events = [root]
    else:
        events = root.findall(".//event")
    if not events:
        return False, "XML parsed but no <event> element found (root=%s)" % root.tag
    ev = events[0]
    pt = ev.find("point")
    if pt is None:
        return False, "<event> has no <point> child"
    if "lat" not in pt.attrib or "lon" not in pt.attrib:
        return False, "<point> missing lat/lon attrs"
    return True, "%d CoT <event>(s); first uid=%s lat=%s lon=%s" % (
        len(events), ev.get("uid", "?"), pt.get("lat"), pt.get("lon"),
    )


def check_receipt_ledger(_s, body, _h) -> tuple[bool, str]:
    """The ledger endpoint is healthy if it returns the khipu DAG envelope
    (wire/khipu_root/count/nodes). An EMPTY ledger (khipu_root=null, count=0) is
    the HONEST reset state — the in-memory DAG resets on Space restart and is
    only populated once a /beyond demo emits a receipt — so an empty-but-
    well-formed ledger is GREEN, not RED. We only fail if the envelope shape is
    wrong or count/nodes disagree (a fabrication tell)."""
    try:
        d = _json_load(body)
    except Exception as e:
        return False, "not JSON: %s" % e
    if "khipu_root" not in d or "count" not in d or "nodes" not in d:
        return False, "ledger envelope missing khipu_root/count/nodes"
    count = d.get("count")
    nodes = d.get("nodes")
    if not isinstance(nodes, list) or count != len(nodes):
        return False, "count=%r disagrees with nodes=%s (fabrication tell)" % (
            count, len(nodes) if isinstance(nodes, list) else type(nodes).__name__)
    root = d.get("khipu_root")
    if count == 0:
        return True, "ledger live, empty (count=0, in-memory DAG reset — honest)"
    return True, "khipu_root=%s count=%s" % (str(root)[:16], count)


def check_pem(_s, body, _h) -> tuple[bool, str]:
    text = body.decode("utf-8", "replace")
    if "BEGIN PUBLIC KEY" in text or "BEGIN CERTIFICATE" in text:
        return True, "PEM public key served (%d bytes)" % len(body)
    return False, "not a PEM (%d bytes)" % len(body)


# ---------------------------------------------------------------------------
# Probe catalogue — the demo run-of-show surfaces
# ---------------------------------------------------------------------------
def build_probes() -> list[Probe]:
    return [
        # --- core demo surfaces (must be on main / live) ---
        Probe("elite track board", "/elite", check_elite_board),
        Probe("health", "/api/killinchu/healthz", check_healthz),
        Probe("ready", "/api/killinchu/readyz", check_healthz),
        Probe("honesty manifest", "/api/killinchu/v1/honest",
              check_json_has(("doctrine_lock", "honest_labels"))),
        Probe("version", "/api/killinchu/v1/version",
              check_json_has(("doctrine",)), required=False),
        Probe("doctrine card", "/api/killinchu/v1/doctrine",
              check_json_has(("doctrine",)), required=False),
        Probe("Λ aggregator", "/api/killinchu/v1/lambda",
              check_json_has(("doctrine",)), required=False),
        Probe("drone database", "/api/killinchu/v1/drones/database",
              check_has_vessels),
        Probe("active threats", "/api/killinchu/v1/threats/active",
              check_has_vessels, required=False),
        # --- receipts / verify-it-yourself ---
        Probe("receipt ledger", "/api/killinchu/v1/receipt/ledger",
              check_receipt_ledger),
        Probe("cosign public key", "/cosign.pub", check_pem, required=False),

        # --- NEW dataset/CoT/overlay endpoints (may be pending PR) ---
        # AIS Aug-2024 dataset — PR #133 (feat/ais-aug2024-dataset-d1)
        Probe("AIS source manifest", "/api/killinchu/v1/ais/sources",
              check_json_has(("sources",)), pending_pr=133, required=False),
        Probe("AIS Aug-2024 tracks", "/api/killinchu/v1/ais/aug2024/tracks",
              check_has_vessels, pending_pr=133, required=False),
        Probe("AIS Aug-2024 risk board", "/api/killinchu/v1/ais/aug2024/risk-board?sign=true",
              check_has_vessels, pending_pr=133, required=False),
        # CoT interop — PR #132 (feat/cot-interop)
        Probe("CoT export (all tracks)", "/api/killinchu/v1/cot/export",
              check_cot_xml, pending_pr=132, required=False),
        Probe("CoT status manifest", "/api/killinchu/v1/cot/status",
              check_json_has(("live",)), pending_pr=132, required=False),
        # Pirate / WPI overlays — PR #134 (feat/pirate-wpi-overlays)
        Probe("maritime overlays", "/api/killinchu/v1/maritime/overlays",
              check_json_has(("doctrine",)), pending_pr=134, required=False),
        Probe("pirate-attacks overlay", "/api/killinchu/v1/maritime/overlays/pirate-attacks",
              check_has_vessels, pending_pr=134, required=False),
        Probe("world port index overlay", "/api/killinchu/v1/maritime/overlays/world-port-index",
              check_has_vessels, pending_pr=134, required=False),
    ]


# ---------------------------------------------------------------------------
# Table rendering (pure — unit tested)
# ---------------------------------------------------------------------------
_VERDICT_ICON = {GREEN: "GREEN", RED: "RED  ", PENDING: "PEND "}


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def render_table(results: list[ProbeResult], use_color: bool = False) -> str:
    """Render the preflight results as a fixed-width text table. Pure string
    function so it can be unit tested without any network."""

    name_w = max([len("SURFACE")] + [len(r.name) for r in results])
    path_w = min(42, max([len("PATH")] + [len(r.path) for r in results]))

    def color(verdict: str, text: str) -> str:
        if not use_color:
            return text
        code = {GREEN: "\033[32m", RED: "\033[31m", PENDING: "\033[33m"}.get(verdict, "")
        return "%s%s\033[0m" % (code, text) if code else text

    lines = []
    header = "%-6s  %-*s  %-5s  %-*s  %s" % (
        "STATE", name_w, "SURFACE", "HTTP", path_w, "PATH", "CONTENT CHECK / DETAIL"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in results:
        http = str(r.status) if r.status is not None else "ERR"
        state = color(r.verdict, _VERDICT_ICON.get(r.verdict, r.verdict))
        row = "%-6s  %-*s  %-5s  %-*s  %s" % (
            state, name_w, r.name, http, path_w, _truncate(r.path, path_w),
            _truncate(r.detail, 70),
        )
        lines.append(row)
    return "\n".join(lines)


def summarize(results: list[ProbeResult]) -> dict:
    """Aggregate counts. A run is demo-ready (ok=True) when no REQUIRED probe
    is RED. PENDING never fails the run."""
    counts = {GREEN: 0, RED: 0, PENDING: 0}
    required_red = 0
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    # required_red counted separately against the probe catalogue below
    return {"counts": counts, "required_red": required_red, "total": len(results)}


def compute_exit(results: list[ProbeResult], probes: list[Probe]) -> tuple[bool, int]:
    """Return (demo_ready, count_of_required_reds). A required probe that is RED
    blocks the demo. PENDING and optional reds do not."""
    by_name = {p.name: p for p in probes}
    required_reds = [
        r for r in results
        if r.verdict == RED and by_name.get(r.name, Probe("", "", lambda *a: (True, ""))).required
    ]
    return (len(required_reds) == 0, len(required_reds))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="killinchu demo preflight validator (honest GREEN/RED/PENDING table).",
    )
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help="live base URL (default: %(default)s)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help="per-request timeout seconds (default: %(default)s)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    ap.add_argument("--include-pending", action="store_true",
                    help="(default on) probe pending-PR routes too; they never fail the run")
    args = ap.parse_args(argv)

    probes = build_probes()
    results = [run_probe(args.base_url, p, timeout=args.timeout) for p in probes]
    demo_ready, required_reds = compute_exit(results, probes)
    summary = summarize(results)

    if args.json:
        out = {
            "base_url": args.base_url,
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "demo_ready": demo_ready,
            "required_reds": required_reds,
            "summary": summary["counts"],
            "results": [vars(r) for r in results],
            "doctrine": "v11 — real probes only; pending-PR routes labelled, never faked green",
        }
        print(json.dumps(out, indent=2))
        return 0 if demo_ready else 1

    use_color = sys.stdout.isatty() and not args.no_color
    print("killinchu demo preflight — base: %s" % args.base_url)
    print("generated (UTC): %s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    print()
    print(render_table(results, use_color=use_color))
    print()
    c = summary["counts"]
    print("Summary: %d GREEN · %d RED · %d PENDING (of %d probes)"
          % (c.get(GREEN, 0), c.get(RED, 0), c.get(PENDING, 0), summary["total"]))
    if required_reds:
        print("DEMO NOT READY — %d REQUIRED surface(s) RED." % required_reds)
    else:
        print("DEMO READY — no required surface is RED. "
              "(PENDING rows await their PR; not a failure.)")
    print("Doctrine v11: every HTTP code above is the REAL observed code; "
          "pending-PR routes are labelled, never asserted green.")
    return 0 if demo_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
