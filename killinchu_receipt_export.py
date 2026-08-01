"""Bounded, evidence-honest Killinchu receipt export contract.

This module is deliberately pure stdlib so the export state can be tested
without importing the full FastAPI application. A transport-success response
does not imply that a receipt or signature exists: callers must inspect
``export_state``, ``receipt_available`` and ``verification.state``.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


SCHEMA = "szl.killinchu.receipt-export/v1"
DEFAULT_PUBLIC_KEY_URL = "https://szlholdings-killinchu.hf.space/cosign.pub"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base(doctrine: str, public_key_url: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ok": True,
        "doctrine": doctrine,
        "generated_at": _now_utc(),
        "public_key_url": public_key_url,
    }


def build_receipt_export(
    dag: Sequence[Mapping[str, Any]],
    *,
    index: int = -1,
    doctrine: str = "v11",
    dsse_module: Any = None,
    khipu_root: str | None = None,
    public_key_url: str = DEFAULT_PUBLIC_KEY_URL,
    ledger: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    """Return ``(body, status_code)`` for the public receipt export route.

    The empty ledger is a valid, explicit runtime state and therefore returns
    HTTP 200 with no receipt and no signature claim. A non-empty export is
    marked signed only when the configured DSSE verifier validates it.
    Out-of-range indexes are rejected rather than silently selecting a
    different receipt.
    """

    ledger_truth = dict(
        ledger
        or {
            "durability_state": "EPHEMERAL",
            "ready": True,
            "production_ready": False,
            "integrity": {"state": "NOT_VERIFIED", "verified": False},
            "replay": {"state": "NOT_APPLICABLE", "nodes": len(dag)},
        }
    )
    out = _base(doctrine, public_key_url)
    out["ledger"] = ledger_truth
    out["ledger_durability"] = ledger_truth.get("durability_state", "UNAVAILABLE")
    ledger_size = len(dag)

    if ledger_truth.get("ready") is not True:
        out.update(
            {
                "ok": False,
                "export_state": "LEDGER_UNAVAILABLE",
                "receipt_available": False,
                "ledger_size": 0,
                "node_index": None,
                "node_digest": None,
                "khipu_root": None,
                "dsse": None,
                "payload_b64": None,
                "signed": False,
                "keyid": None,
                "verification": {
                    "state": "UNAVAILABLE",
                    "verified": None,
                    "reason": "selected ledger mode is not ready",
                },
                "verify_offline": [],
                "limits": [
                    {
                        "code": "LEDGER_UNAVAILABLE",
                        "detail": "Startup replay and integrity must succeed before export.",
                    }
                ],
                "honesty": "No receipt is exported from an unready ledger.",
            }
        )
        return out, 503

    durability_limits = []
    if ledger_truth.get("durability_state") == "EPHEMERAL":
        durability_limits.append(
            {
                "code": "EPHEMERAL_LEDGER",
                "detail": "The in-memory Khipu ledger resets on Space restart.",
            }
        )

    if ledger_size == 0:
        out.update(
            {
                "export_state": "EMPTY",
                "receipt_available": False,
                "ledger_size": 0,
                "node_index": None,
                "node_digest": None,
                "khipu_root": None,
                "dsse": None,
                "payload_b64": None,
                "signed": False,
                "keyid": None,
                "verification": {
                    "state": "NOT_APPLICABLE",
                    "verified": False,
                    "reason": "no receipt exists in the in-memory ledger",
                },
                "verify_offline": [],
                "limits": [
                    {
                        "code": "NO_RECEIPTS",
                        "detail": "No receipt has been emitted since this runtime started.",
                    },
                    *durability_limits,
                ],
                "honesty": (
                    "The export route is reachable, but no receipt exists. "
                    "This response is not a receipt and carries no signature."
                ),
            }
        )
        return out, 200

    if index < -ledger_size or index >= ledger_size:
        out.update(
            {
                "ok": False,
                "export_state": "INDEX_OUT_OF_RANGE",
                "receipt_available": False,
                "ledger_size": ledger_size,
                "requested_index": index,
                "valid_index": {"min": -ledger_size, "max": ledger_size - 1},
                "signed": False,
                "verification": {
                    "state": "NOT_APPLICABLE",
                    "verified": False,
                    "reason": "requested index is outside the bounded ledger",
                },
                "limits": [
                    {
                        "code": "INDEX_OUT_OF_RANGE",
                        "detail": "Select an index inside valid_index; no fallback receipt was substituted.",
                    }
                ],
            }
        )
        return out, 422

    node = dag[index]
    receipt_obj = node.get("receipt")
    raw_dsse = node.get("dsse")
    dsse: dict[str, Any] = dict(raw_dsse) if isinstance(raw_dsse, Mapping) else {}
    raw_signatures = dsse.get("signatures")
    signatures = [dict(s) for s in raw_signatures or [] if isinstance(s, Mapping)]

    # A literal placeholder is an honesty marker, never a signature. Do not
    # expose it in the DSSE signatures array where generic clients may mistake
    # presence for cryptographic proof.
    has_placeholder = any(
        s.get("keyid") in (None, "PENDING")
        or "PLACEHOLDER" in str(s.get("sig", "")).upper()
        for s in signatures
    )
    if has_placeholder:
        signatures = []
    dsse["signatures"] = signatures

    reconstruction_error: str | None = None
    payload_b64: str | None = None
    pae_sha256: str | None = None
    if receipt_obj is None:
        reconstruction_error = "receipt object missing from ledger node"
    elif dsse_module is None:
        reconstruction_error = "DSSE module unavailable in this runtime"
    else:
        try:
            body = dsse_module.canonical_json(receipt_obj)
            payload_type = dsse.get("payloadType", "application/vnd.szl.receipt+json")
            payload_b64 = base64.b64encode(body).decode("ascii")
            pae_sha256 = hashlib.sha256(dsse_module.pae(payload_type, body)).hexdigest()
            dsse.update(
                {
                    "payloadType": payload_type,
                    "payload": payload_b64,
                    "_dsse": "DSSEv1",
                    "_pae_sha256": pae_sha256,
                }
            )
        except Exception:
            reconstruction_error = "DSSE payload reconstruction failed"

    verification: dict[str, Any]
    if not signatures:
        verification = {
            "state": "UNSIGNED",
            "verified": False,
            "reason": "no genuine signature is present",
        }
    elif reconstruction_error:
        verification = {
            "state": "UNAVAILABLE",
            "verified": None,
            "reason": reconstruction_error,
        }
    elif not hasattr(dsse_module, "verify_envelope"):
        verification = {
            "state": "UNAVAILABLE",
            "verified": None,
            "reason": "DSSE verifier unavailable in this runtime",
        }
    else:
        try:
            verdict = dsse_module.verify_envelope(dsse)
            verified = bool(isinstance(verdict, Mapping) and verdict.get("verified") is True)
            verification = {
                "state": "VERIFIED" if verified else "FAILED",
                "verified": verified,
                "reason": (
                    "signature verified against the published public key"
                    if verified
                    else str(verdict.get("reason", "signature verification failed"))
                ),
                "pae_sha256": verdict.get("pae_sha256", pae_sha256),
            }
        except Exception:
            verification = {
                "state": "UNAVAILABLE",
                "verified": None,
                "reason": "DSSE verifier raised; no signed claim emitted",
            }

    signed = verification.get("verified") is True
    dsse["signed"] = signed
    export_state = (
        "SIGNED_VERIFIED"
        if signed
        else "UNSIGNED"
        if not signatures
        else "SIGNATURE_UNVERIFIED"
    )
    keyid = signatures[0].get("keyid") if signatures else None
    limits = list(durability_limits)
    if not signed:
        limits.append(
            {
                "code": "NO_VERIFIED_SIGNATURE",
                "detail": verification["reason"],
            }
        )

    verify_offline = []
    if signed:
        verify_offline = [
            f"curl -s {public_key_url} -o cosign.pub",
            "base64 -d payload.b64 > payload.bin",
            "cosign verify-blob --key cosign.pub --signature sig.b64 payload.bin",
        ]

    out.update(
        {
            "export_state": export_state,
            "receipt_available": True,
            "ledger_size": ledger_size,
            "node_index": node.get("index", index % ledger_size),
            "node_digest": node.get("digest"),
            "khipu_root": khipu_root,
            "dsse": dsse,
            "payload_b64": payload_b64,
            "signed": signed,
            "keyid": keyid,
            "verification": verification,
            "verify_offline": verify_offline,
            "limits": limits,
            "honesty": (
                "The DSSE signature was verified against the published public key."
                if signed
                else "A receipt exists, but this response makes no verified-signature claim."
            ),
        }
    )
    return out, 200
