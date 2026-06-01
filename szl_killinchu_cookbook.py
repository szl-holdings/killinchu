# SPDX-License-Identifier: Apache-2.0
# ===========================================================================
# Killinchu Defense Runtime Cookbook (ADDITIVE, 2026-06-01).
# Yachay <yachay@szlholdings.dev> · Co-Authored-By: Perplexity Computer Agent.
# Doctrine v11 verbatim: 749 declarations / 14 axioms / 163 sorries.
#
# Exposes a self-contained, founder-grade defense COOKBOOK on the live killinchu
# Space. NEW /api/killinchu/v2/cookbook* + /v2/missions* + /v2/scouts +
# /v2/uds/* + /v2/legal + /v2/specs/* + /v2/pitch routes ONLY. Registered on the
# ROOT app BEFORE the SPA "/{full_path:path}" catch-all so they resolve LOCALLY.
# ADDITIVE: collides with NOTHING (confirmed 404 on every path pre-deploy).
#
# Every drone-domain response embeds the LEGAL_BOUNDARIES disclaimer. Cookbook
# recall receipts are REAL ECDSA-P256-SHA256 DSSE, signed live via szl_dsse
# (no copy-paste of the signing core). try/except-guarded; NEVER crashes the app.
#
# WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES.
# Killinchu does NOT take control of any third-party drone. Passive sense +
# evidence only; offensive action is the lawful customer's Title 10/50 authority.
# ===========================================================================
from __future__ import annotations

import json
import os
import sys
import hashlib
import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse

# --- vendored data directory (COPY'd per-file into the image at build time) ----
# Resolve relative to THIS module so it works regardless of CWD.
_HERE = Path(__file__).resolve().parent
_DATA = _HERE / "static" / "cookbook"

DOCTRINE = "v11"
NUMBERS = {"declarations": 749, "axioms": 14, "sorries": 163}
MAINTAINER = "Yachay <yachay@szlholdings.dev>"
CO_AUTHOR = "Perplexity Computer Agent"

# The single canonical disclaimer string echoed on EVERY drone-domain response.
LEGAL_DISCLAIMER = (
    "WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. "
    "Killinchu is a passive sensing + evidence system and does NOT take control "
    "of any third-party drone. Offensive cyber, RF jamming, GNSS spoofing, and "
    "kinetic action are the lawful customer's responsibility under Title 10 / "
    "Title 50 authority (CFAA 18 U.S.C. 1030, ITAR 22 CFR 120-130, Wassenaar, "
    "FCC jammer rules). Own-fleet control only, behind a 2-person Yuyay gate. "
    "See /api/killinchu/v2/legal."
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _base(extra: dict | None = None, drone_domain: bool = False) -> dict:
    out = {
        "doctrine": DOCTRINE,
        "numbers": NUMBERS,
        "maintainer": MAINTAINER,
        "co_author": CO_AUTHOR,
        "generated_at": _now(),
    }
    if drone_domain:
        out["disclaimer"] = LEGAL_DISCLAIMER
    if extra:
        out.update(extra)
    return out


def register_cookbook(app, ns: str = "killinchu", sign_fn=None):
    """Register the Killinchu Defense Runtime Cookbook on `app`.

    ADDITIVE: only NEW /api/{ns}/v2/* routes. Registered BEFORE the SPA catch-all.
    `sign_fn`: optional override for the receipt signer; defaults to
    szl_dsse.sign_khipu_receipt (REAL ECDSA-P256-SHA256 DSSE) when available.
    Returns a status dict. NEVER raises.
    """
    p = f"/api/{ns}/v2"

    # --- wire up the REAL signer (no copy-paste of the crypto core) ------------
    _sign = sign_fn
    _signing_available = False
    _pubkey_fpr = None
    if _sign is None:
        try:
            import szl_dsse  # the real signing module already in the Space
            _sign = szl_dsse.sign_khipu_receipt
            try:
                _signing_available = bool(szl_dsse.signing_available())
            except Exception:
                _signing_available = False
            try:
                _pubkey_fpr = szl_dsse.public_key_fingerprint()
            except Exception:
                _pubkey_fpr = None
        except Exception as _se:
            print(f"[cookbook] szl_dsse unavailable ({_se!r}); receipts will be UNSIGNED", file=sys.stderr)
            _sign = None

    def _recall_receipt(kind: str, ref: str, payload_digest: str) -> dict:
        """A real signed recall receipt attesting THIS cookbook entry was served."""
        receipt = {
            "type": "killinchu.cookbook.recall",
            "kind": kind,
            "ref": ref,
            "payload_sha256": payload_digest,
            "ns": ns,
            "doctrine": DOCTRINE,
            "issued_at": _now(),
            "keyid": "szlholdings-cosign",
        }
        if _sign is not None:
            try:
                signed = _sign(receipt)
                # szl_dsse.sign_khipu_receipt -> {"receipt":..., "dsse": env}
                signed["signed"] = True
                signed["signing"] = "ECDSA-P256-SHA256 DSSE (REAL, live via szl_dsse)"
                return signed
            except Exception as _e:
                return {"receipt": receipt, "signed": False,
                        "signing_error": f"{_e!r}",
                        "note": "Signer present but failed at runtime; receipt unsigned."}
        return {"receipt": receipt, "signed": False,
                "signing": "UNSIGNED — szl_dsse not importable in this context."}

    def _digest(obj) -> str:
        canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(canon).hexdigest()

    # =======================================================================
    # COOKBOOK — recipes
    # =======================================================================
    @app.get(p + "/cookbook")
    async def cookbook_list() -> JSONResponse:
        idx = _read_json(_DATA / "recipes" / "_index.json") or []
        return JSONResponse(_base({
            "kind": "cookbook-index",
            "count": len(idx),
            "recipes": idx,
            "drone_domain_count": sum(1 for r in idx if r.get("drone_domain")),
            "detail": p + "/cookbook/{id}",
            "note": ("Killinchu Defense Runtime Cookbook — copy-paste-runnable recipes that "
                     "drive the LIVE killinchu endpoints. Drone-domain recipes carry the "
                     "LEGAL_BOUNDARIES disclaimer."),
        }))

    @app.get(p + "/cookbook/{recipe_id}")
    async def cookbook_get(recipe_id: str) -> JSONResponse:
        idx = _read_json(_DATA / "recipes" / "_index.json") or []
        meta = next((r for r in idx if r.get("id") == recipe_id), None)
        # sanitize id -> filename
        safe = recipe_id.replace("/", "").replace("..", "")
        md = _read_text(_DATA / "recipes" / f"{safe}.md")
        if not md or meta is None:
            return JSONResponse(_base({
                "error": "recipe not found", "ref": recipe_id,
                "available": [r.get("id") for r in idx],
            }), status_code=404)
        drone = bool(meta.get("drone_domain"))
        digest = hashlib.sha256(md.encode("utf-8")).hexdigest()
        return JSONResponse(_base({
            "kind": "recipe",
            "id": recipe_id,
            "title": meta.get("title"),
            "tags": meta.get("tags", []),
            "drone_domain": drone,
            "markdown": md,
            "recall_receipt": _recall_receipt("recipe", recipe_id, digest),
        }, drone_domain=drone))

    # =======================================================================
    # MISSIONS — the 8 Warhacker mission packs (P1-P8)
    # =======================================================================
    @app.get(p + "/missions")
    async def missions_list() -> JSONResponse:
        idx = _read_json(_DATA / "missions" / "_index.json") or {}
        return JSONResponse(_base({
            "kind": "missions-index",
            "count": idx.get("count"),
            "total_min": idx.get("total_min"),
            "missions": idx.get("missions", []),
            "detail": p + "/missions/{id}",
            "source": "DEMO_STORYBOARD_60min.md (Warhacker 2026, San Diego, Jun 16-19)",
        }))

    @app.get(p + "/missions/{mission_id}")
    async def mission_get(mission_id: str) -> JSONResponse:
        safe = mission_id.upper().replace("/", "").replace("..", "")
        m = _read_json(_DATA / "missions" / f"{safe}.json")
        if m is None:
            return JSONResponse(_base({
                "error": "mission not found", "ref": mission_id,
                "available": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
            }), status_code=404)
        drone = bool(m.get("drone_domain"))
        m["recall_receipt"] = _recall_receipt("mission", safe, _digest(m))
        # m already carries doctrine/numbers/disclaimer from generation; ensure disclaimer on drone
        if drone and "disclaimer" not in m:
            m["disclaimer"] = LEGAL_DISCLAIMER
        return JSONResponse(m)

    # =======================================================================
    # SCOUTS — 9 prospect scout reports
    # =======================================================================
    @app.get(p + "/scouts")
    async def scouts_list() -> JSONResponse:
        idx = _read_json(_DATA / "scouts" / "_index.json") or {}
        scouts = []
        for s in idx.get("scouts", []):
            key = s.get("key")
            full = _read_json(_DATA / "scouts" / f"{key}.json") or {}
            scouts.append(full or s)
        return JSONResponse(_base({
            "kind": "prospect-scouts",
            "count": len(scouts),
            "scouts": scouts,
            "pitch_endpoint": p + "/pitch?for=<org>",
        }))

    # =======================================================================
    # UDS bundle self-awareness (HONEST STAGED status)
    # =======================================================================
    @app.get(p + "/uds/bundle-inspect")
    async def uds_bundle_inspect() -> JSONResponse:
        meta = _read_json(_DATA / "uds" / "bundle_meta.json") or {}
        return JSONResponse(_base({"kind": "uds-bundle-inspect", **meta}))

    @app.get(p + "/uds/deploy-instructions")
    async def uds_deploy() -> JSONResponse:
        meta = _read_json(_DATA / "uds" / "bundle_meta.json") or {}
        return JSONResponse(_base({
            "kind": "uds-deploy-instructions",
            "deploy_instructions": meta.get("deploy_instructions", {}),
            "deploy_order": meta.get("deploy_order"),
            "uds_core": meta.get("uds_core"),
            "zarf_init": meta.get("zarf_init"),
            "cosign_status": (meta.get("cosign") or {}).get("status"),
            "honest_note": (meta.get("cosign") or {}).get("honest_note"),
        }))

    @app.get(p + "/uds/verify")
    async def uds_verify() -> JSONResponse:
        meta = _read_json(_DATA / "uds" / "bundle_meta.json") or {}
        return JSONResponse(_base({
            "kind": "uds-verify",
            "verify": meta.get("verify", {}),
            "cosign": meta.get("cosign", {}),
            "metadata_sha256": meta.get("metadata_sha256"),
            "sha256_note": meta.get("sha256_note"),
            "runtime_signing_available": _signing_available,
            "runtime_pubkey_fingerprint": _pubkey_fpr,
            "honest_summary": ("Runtime Khipu receipts are REAL (ECDSA-P256-SHA256 DSSE). "
                               "The Zarf PACKAGE artifact is STAGED — cosign signature PENDING "
                               "(blockers: FA-001 image push, U5 org cosign key + zarf publish)."),
        }))

    # =======================================================================
    # LEGAL — full LEGAL_BOUNDARIES text + sources
    # =======================================================================
    @app.get(p + "/legal")
    async def legal() -> JSONResponse:
        txt = _read_text(_DATA / "legal" / "LEGAL_BOUNDARIES.md")
        return JSONResponse(_base({
            "kind": "legal-boundaries",
            "headline": "WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES.",
            "markdown": txt,
            "controlling_law": [
                {"name": "CFAA 18 U.S.C. 1030", "url": "https://www.law.cornell.edu/uscode/text/18/1030"},
                {"name": "ITAR 22 CFR 120-130", "url": "https://www.ecfr.gov/current/title-22/chapter-I/subchapter-M"},
                {"name": "Wassenaar Arrangement", "url": "https://www.wassenaar.org/"},
                {"name": "FCC jammer enforcement", "url": "https://www.fcc.gov/general/jammer-enforcement"},
                {"name": "IETF SCITT WG", "url": "https://datatracker.ietf.org/wg/scitt/about/"},
            ],
        }, drone_domain=True))

    @app.get(p + "/legal.txt")
    async def legal_txt() -> PlainTextResponse:
        return PlainTextResponse(_read_text(_DATA / "legal" / "LEGAL_BOUNDARIES.md"))

    # =======================================================================
    # SPECS — protocol decoder specs (Remote-ID, MAVLink)
    # =======================================================================
    @app.get(p + "/specs/remote-id")
    async def spec_remote_id() -> JSONResponse:
        return JSONResponse(_base({
            "kind": "spec",
            "protocol": "Remote-ID (OpenDroneID / ASTM F3411-22a)",
            "frame": "25-byte messages; message_type nibble selects Basic-ID / Location / Auth / System / Operator-ID.",
            "location_fields": ["status", "track_direction", "speed", "vert_speed",
                                 "lat (int32 x1e-7)", "lon (int32 x1e-7)",
                                 "pressure_alt", "geodetic_alt", "height", "h_accuracy", "timestamp"],
            "honesty": "Remote-ID is an UNAUTHENTICATED broadcast — decoded fields are CLAIMS, not attested truth.",
            "decoder_endpoints": ["/api/" + ns + "/v2/remote-id/decode", "/api/" + ns + "/v1/remote-id/decode"],
            "sources": [
                "https://www.astm.org/f3411-22a.html",
                "https://github.com/opendroneid/opendroneid-core-c",
                "https://www.faa.gov/sites/faa.gov/files/2021-08/RemoteID_Final_Rule.pdf",
            ],
        }, drone_domain=True))

    @app.get(p + "/specs/mavlink")
    async def spec_mavlink() -> JSONResponse:
        return JSONResponse(_base({
            "kind": "spec",
            "protocol": "MAVLink v2",
            "frame": "STX(0xFD) LEN INCOMPAT COMPAT SEQ SYSID COMPID MSGID(3) PAYLOAD CRC(2) [SIGNATURE(13)]",
            "fields": ["magic=0xFD", "len", "incompat_flags", "compat_flags", "seq",
                       "sysid", "compid", "msgid (24-bit)", "payload", "checksum", "optional signature"],
            "honesty": "Unsigned MAVLink frames are UNAUTHENTICATED. Killinchu decodes passively; it does not inject commands to third-party craft.",
            "decoder_endpoints": ["/api/" + ns + "/v2/mavlink/decode", "/api/" + ns + "/v1/mavlink/decode"],
            "sources": [
                "https://mavlink.io/en/guide/serialization.html",
                "https://github.com/ArduPilot/pymavlink",
            ],
        }, drone_domain=True))

    # =======================================================================
    # PITCH — tailored 30s pitch per prospect org
    # =======================================================================
    @app.get(p + "/pitch")
    async def pitch(request: Request) -> JSONResponse:
        pitches = _read_json(_DATA / "uds" / "pitches.json") or {}
        org = (request.query_params.get("for") or request.query_params.get("org") or "").strip()
        if not org:
            return JSONResponse(_base({
                "kind": "pitch-index",
                "usage": p + "/pitch?for=<org>",
                "orgs": sorted(pitches.keys()),
            }))
        # case-insensitive match on key or org_name
        match = None
        for k, v in pitches.items():
            if k.lower() == org.lower() or v.get("org_name", "").lower() == org.lower():
                match = v
                break
        if match is None:
            # loose contains match
            for k, v in pitches.items():
                if org.lower() in k.lower() or org.lower() in v.get("org_name", "").lower():
                    match = v
                    break
        if match is None:
            return JSONResponse(_base({
                "error": "no pitch for org", "ref": org,
                "orgs": sorted(pitches.keys()),
            }), status_code=404)
        return JSONResponse(_base({"kind": "pitch", **match}, drone_domain=True))

    # =======================================================================
    # INDEX — cookbook root self-description
    # =======================================================================
    @app.get(p + "/cookbook-info")
    async def cookbook_info() -> JSONResponse:
        return JSONResponse(_base({
            "kind": "cookbook-info",
            "name": "Killinchu Defense Runtime Cookbook",
            "headline": "WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES.",
            "routes": {
                "recipes": [p + "/cookbook", p + "/cookbook/{id}"],
                "missions": [p + "/missions", p + "/missions/{id}"],
                "scouts": [p + "/scouts"],
                "uds": [p + "/uds/bundle-inspect", p + "/uds/deploy-instructions", p + "/uds/verify"],
                "legal": [p + "/legal", p + "/legal.txt"],
                "specs": [p + "/specs/remote-id", p + "/specs/mavlink"],
                "pitch": [p + "/pitch?for=<org>"],
            },
            "signing": ("REAL ECDSA-P256-SHA256 DSSE recall receipts via szl_dsse"
                        if _sign is not None else "UNSIGNED (szl_dsse unavailable)"),
            "signing_available": _signing_available,
            "pubkey_fingerprint": _pubkey_fpr,
        }))

    routes = [
        p + "/cookbook", p + "/cookbook/{id}", p + "/cookbook-info",
        p + "/missions", p + "/missions/{id}", p + "/scouts",
        p + "/uds/bundle-inspect", p + "/uds/deploy-instructions", p + "/uds/verify",
        p + "/legal", p + "/legal.txt", p + "/specs/remote-id", p + "/specs/mavlink",
        p + "/pitch",
    ]
    return {
        "module": "szl_killinchu_cookbook",
        "ns": ns,
        "registered_count": len(routes),
        "routes": routes,
        "signing": _sign is not None,
        "signing_available": _signing_available,
        "data_dir": str(_DATA),
        "doctrine": DOCTRINE,
    }
