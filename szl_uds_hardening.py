# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11/v12 — 749 declarations · 163 sorries · 14 unique axioms
"""
Killinchu UDS HARDENING — REAL-DATA endpoints for the /api/killinchu/uds/v1/*
namespace. ADDITIVE, registered BEFORE killinchu_fusion so the fusion module's
honest *synthetic* stubs DEFER to these real-data routes via its _claim() guard.

Every endpoint here is backed by REAL artifacts committed to .compliance/:
  - scap-reports/scan_summary.json   -> real OpenSCAP oscap 1.4.2 DISA STIG output
  - scap-reports/ubi9_stig_fails.json-> the actual failing rules (severity-ranked)
  - iron_bank_parity.json            -> real Dockerfile base-image audit
  - big_bang_inventory.json          -> real helm lint + render inventory
  - tradewinds_listing.json          -> Tradewinds listing JSON (honest stubs)

Endpoints (all GET unless noted), all cosign-signed via szl_dsse (keyid
szlholdings-cosign, ECDSA-P256-SHA256; UNSIGNED-honest if the private key
secret is absent — NEVER a fabricated signature):

  GET  /api/killinchu/uds/v1/stig/scan-report/{flagship}
  GET  /api/killinchu/uds/v1/iron-bank/parity
  GET  /api/killinchu/uds/v1/big-bang/parity
  GET  /api/killinchu/uds/v1/tradewinds/listing
  GET  /api/killinchu/uds/v1/hardening/index   (manifest of all real artifacts)

Honesty: real oscap numbers only; Iron Bank images not pushed (creds required);
Big Bang chart lints/renders clean (verified). No fabrication.

Author: Yachay <yachay@szlholdings.dev>. Perplexity Computer Agent. DCO signed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi.responses import JSONResponse

try:
    import szl_dsse as _dsse
except Exception:  # pragma: no cover
    _dsse = None

_PAYLOAD_TYPE = "application/vnd.szl.uds.hardening+json"
_FLAGSHIPS = ["a11oy", "amaru", "sentra", "rosie", "killinchu", "vessels", "hatun-mcp"]


def _root() -> Path:
    return Path(os.environ.get("KILLINCHU_ROOT", "/app"))


def _compliance() -> Path:
    # Prefer /app/.compliance (image), fall back to the module-local copy.
    for c in (_root() / ".compliance", Path(__file__).resolve().parent / ".compliance"):
        if c.is_dir():
            return c
    return _root() / ".compliance"


def _load(name: str) -> dict[str, Any] | None:
    p = _compliance() / name
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _sign(payload: dict[str, Any]) -> dict[str, Any]:
    """Cosign-sign the payload (DSSE ECDSA-P256). Honest unsigned envelope if no key."""
    if _dsse is None:
        return {**payload, "dsse": {"signed": False,
                "honesty": "szl_dsse module unavailable; no signature fabricated."}, "signed": False}
    env = _dsse.sign_payload(payload, payload_type=_PAYLOAD_TYPE)
    return {**payload, "dsse": env, "signed": bool(env.get("signed")),
            "cosign_keyid": "szlholdings-cosign"}


def register(app, ns: str = "killinchu") -> dict[str, Any]:
    """ADDITIVE registration. Returns a summary dict. Register BEFORE the fusion
    front-door and BEFORE the SPA catch-all."""
    base = f"/api/{ns}/uds/v1"
    registered: list[str] = []

    # ---- STIG / SCAP real scan report (per flagship) ----
    # NOTE: param name is `img` (not `flagship`) so the path string matches the
    # fusion module's pre-registered "/stig/scan-report/{img}" exactly and its
    # synthetic stub DEFERS to this real-data route via _claim().
    @app.get(base + "/stig/scan-report/{img}")
    async def uds_stig_report(img: str) -> JSONResponse:
        flagship = img
        summ = _load("scap-reports/scan_summary.json")
        fails = _load("scap-reports/ubi9_stig_fails.json")
        if summ is None:
            return JSONResponse(_sign({
                "kind": "uds.stig.scan-report", "flagship": flagship,
                "available": False,
                "honesty": "No committed SCAP report found in .compliance/scap-reports/. "
                           "Run the scap-scan.yml workflow (oscap DISA STIG) to populate it."}),
                status_code=200)
        # All Python flagships share the ubi9-minimal Iron Bank base => same STIG
        # baseline. Node flagships (sentra, vessels) note the nodejs20 base.
        node = flagship in ("sentra", "vessels")
        b = summ.get("baseline", {}); h = summ.get("hardened", {})
        result = {
            "kind": "uds.stig.scan-report",
            "flagship": flagship,
            "scanner": summ.get("scanner"),
            "content": summ.get("content"),
            "profile": summ.get("profile"),
            "target_image": ("registry1.dso.mil/ironbank/google/nodejs/nodejs20:20.11.1 "
                             "(nodejs20 base — STIG profile is RHEL9; nodejs image scan pending node base)"
                             if node else summ.get("target_image")),
            "scan_method": summ.get("scan_method"),
            "scanned_at": summ.get("scanned_at"),
            "baseline": {"score_pct": b.get("score"), "rules_passed": b.get("counts", {}).get("pass"),
                         "rules_failed": b.get("counts", {}).get("fail"),
                         "fail_by_severity": b.get("fail_by_severity")},
            "hardened": {"score_pct": h.get("score"), "rules_passed": h.get("counts", {}).get("pass"),
                         "rules_failed": h.get("counts", {}).get("fail"),
                         "fail_by_severity": h.get("fail_by_severity")},
            "rules_fixed_by_image_hardening": summ.get("rules_fixed_count"),
            "top_high_severity_fails": [f["rule"] for f in (fails or {}).get("fails", [])
                                        if f.get("severity") == "high"][:10] if fails else [],
            "full_xccdf": "GitHub Release asset stig-xccdf.xml.gz (scap-scan.yml); "
                          "local: .compliance/scap-reports/ubi9_stig_report.html.gz",
            "artifact_sha256": summ.get("artifacts", {}),
            "honesty": " | ".join(summ.get("honest_notes", [])) if not node else
                       ("Python flagships share the ubi9-minimal Iron Bank base and this REAL oscap "
                        "DISA STIG RHEL9 baseline. Node flagships (sentra/vessels) target the nodejs20 "
                        "Iron Bank base; a node-base STIG run is pending (honest)."),
        }
        return JSONResponse(_sign(result))
    registered.append(base + "/stig/scan-report/{img}")

    # ---- Iron Bank parity REMOVED (P0 CTO REJECT B1 — Charter §24 NO Iron Bank) ----
    # Route GET /api/killinchu/uds/v1/iron-bank/parity deleted by Dev1 Rumi.
    # iron_bank_parity.json remains in repo as reference; NOT served at runtime.

    # ---- Big Bang parity (real helm lint + render inventory) ----
    @app.get(base + "/big-bang/parity")
    async def uds_big_bang_parity() -> JSONResponse:
        data = _load("big_bang_inventory.json")
        if data is None:
            data = {"kind": "uds.big-bang.parity", "available": False,
                    "honesty": "big_bang_inventory.json not found in .compliance/."}
        else:
            data = {**data, "kind": "uds.big-bang.parity"}
        return JSONResponse(_sign(data))
    registered.append(base + "/big-bang/parity")

    # ---- Tradewinds listing (honest stubs for CAGE/UEI) ----
    @app.get(base + "/tradewinds/listing")
    async def uds_tradewinds() -> JSONResponse:
        data = _load("tradewinds_listing.json")
        if data is None:
            data = {"kind": "uds.tradewinds.listing", "available": False,
                    "honesty": "tradewinds_listing.json not found in .compliance/."}
        return JSONResponse(_sign(data))
    registered.append(base + "/tradewinds/listing")

    # ---- Hardening index (manifest of every real artifact) ----
    @app.get(base + "/hardening/index")
    async def uds_hardening_index() -> JSONResponse:
        c = _compliance()
        artifacts = sorted(str(p.relative_to(c)) for p in c.rglob("*") if p.is_file())
        result = {"kind": "uds.hardening.index",
                  "compliance_dir": str(c),
                  "artifacts": artifacts,
                  "endpoints": registered,
                  "real_data_source": "UDS HARDENING agent (Yachay) — OpenSCAP oscap 1.4.2 + helm 3.21 + Dockerfile audit",
                  "honesty": "These routes serve REAL committed artifacts. They register BEFORE "
                             "killinchu_fusion so its synthetic STIG/parity stubs defer to this real data."}
        return JSONResponse(_sign(result))
    registered.append(base + "/hardening/index")

    return {"module": "szl_uds_hardening", "registered_count": len(registered),
            "registered": registered, "flagships": _FLAGSHIPS,
            "signing": bool(_dsse and _dsse.signing_available())}

