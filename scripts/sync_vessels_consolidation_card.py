#!/usr/bin/env python3
"""Publish the reviewed Vessels consolidation card with a secret-free receipt.

This script changes only ``README.md`` in the existing
``SZLHOLDINGS/vessels`` Hugging Face Space. It never changes visibility,
hardware, storage, variables, secrets, or runtime files.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from huggingface_hub import HfApi

CARD_PATH = Path("docs/hf-cards/SZLHOLDINGS-vessels.README.md")
RECEIPT_PATH = Path("hf-vessels-card-receipt.json")
TARGET_REPO = "SZLHOLDINGS/vessels"
TARGET_PATH = "README.md"
REMOTE_URL = f"https://huggingface.co/spaces/{TARGET_REPO}/resolve/main/{TARGET_PATH}"
REQUIRED_MARKERS = (
    "# Vessels — consolidated into Killinchu",
    "**Status: CONSOLIDATED (2026-09-03).**",
    "SZLHOLDINGS/killinchu",
    "No live AIS feed is claimed anywhere in this estate today.",
    "it is not deleted.",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_receipt(receipt: dict[str, Any]) -> None:
    RECEIPT_PATH.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _require_reviewed_card(payload: bytes) -> None:
    text = payload.decode("utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        raise ValueError(f"reviewed consolidation card markers missing: {missing}")
    if not text.startswith("---\n") or "\nlicense: apache-2.0\n---\n" not in text:
        raise ValueError("reviewed card frontmatter or license is missing")


def main() -> int:
    source_revision = os.environ.get("GITHUB_SHA", "UNAVAILABLE")
    local_bytes = CARD_PATH.read_bytes()
    local_digest = _sha256(local_bytes)
    receipt: dict[str, Any] = {
        "schema": "szl.hf-vessels-consolidation-card/v1",
        "status": "STARTED",
        "github_repository": os.environ.get("GITHUB_REPOSITORY", "UNAVAILABLE"),
        "source_revision": source_revision,
        "target_repo": TARGET_REPO,
        "target_path": TARGET_PATH,
        "local_sha256": local_digest,
        "remote_sha256": None,
        "commit_oid": None,
        "commit_url": None,
        "visibility_changed": False,
        "hardware_changed": False,
        "secrets_recorded": False,
    }
    _write_receipt(receipt)

    try:
        _require_reviewed_card(local_bytes)
        token = os.environ.get("HF_TOKEN", "").rstrip("\r\n")
        if not token:
            raise RuntimeError("HF_TOKEN_NOT_CONFIGURED")

        commit = HfApi(token=token).upload_file(
            path_or_fileobj=local_bytes,
            path_in_repo=TARGET_PATH,
            repo_id=TARGET_REPO,
            repo_type="space",
            commit_message=(
                "docs: point Vessels to canonical Killinchu runtime"
                + (
                    f" ({source_revision[:12]})"
                    if source_revision != "UNAVAILABLE"
                    else ""
                )
            ),
            token=token,
        )

        response = requests.get(
            REMOTE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "szl-vessels-card-verifier/1",
            },
            params={"szl_source": source_revision, "t": str(time.time_ns())},
            timeout=30,
        )
        response.raise_for_status()
        remote_bytes = response.content
        remote_digest = _sha256(remote_bytes)
        if remote_digest != local_digest:
            raise RuntimeError("REMOTE_CARD_DIGEST_MISMATCH")
        _require_reviewed_card(remote_bytes)

        receipt.update(
            {
                "status": "PUBLISHED_VERIFIED",
                "remote_sha256": remote_digest,
                "commit_oid": getattr(commit, "oid", None),
                "commit_url": str(getattr(commit, "commit_url", "") or "") or None,
            }
        )
        _write_receipt(receipt)
        print(
            json.dumps(
                {
                    "status": receipt["status"],
                    "target": TARGET_REPO,
                    "sha256": remote_digest,
                    "source_revision": source_revision,
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:  # receipt intentionally records only the type
        receipt.update(
            {
                "status": "FAILED",
                "error_type": type(exc).__name__,
            }
        )
        _write_receipt(receipt)
        print(
            f"Vessels consolidation-card publication failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
