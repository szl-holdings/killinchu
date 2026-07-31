#!/usr/bin/env python3
"""Publish a viewer-safe, source-bound snapshot of the Killinchu archive.

The raw NDJSON shards remain append-only and mixed-source.  This publisher does
not rewrite or relicense them.  It publishes a homogeneous manifest view plus
an exact Git/Hugging Face binding and verifies the immutable post-commit bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from pathlib import Path
from typing import Any

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

import killinchu_intel_archive_card as card


ROOT = Path(__file__).resolve().parent
REPO_ID = "SZLHOLDINGS/killinchu-osint-corpus"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class PublicationError(RuntimeError):
    """Raised when an exact archive publication cannot be proven."""


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def source_file(path: str) -> dict[str, Any]:
    body = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    return {"path": path, "bytes": len(body), "sha256": sha256_bytes(body)}


def archive_snapshot(api: HfApi) -> tuple[str, list[dict[str, Any]]]:
    info = api.dataset_info(REPO_ID, files_metadata=True)
    if FULL_SHA.fullmatch(str(info.sha)) is None:
        raise PublicationError("Hub archive revision is not immutable")
    shards: list[dict[str, Any]] = []
    for sibling in info.siblings or []:
        path = sibling.rfilename
        if not path.startswith("intel/") or not path.endswith(".ndjson"):
            continue
        blob_id = getattr(sibling, "blob_id", None)
        if not isinstance(blob_id, str) or not blob_id:
            raise PublicationError(f"missing immutable blob id for {path}")
        shards.append(
            {
                "path": path,
                "bytes": sibling.size,
                "git_blob_id": blob_id,
                "git_blob_hash_algorithm": "sha1",
                "rights_status": "MIXED_SOURCE_ROW_LEVEL_RIGHTS_NOT_ESTABLISHED",
                "training_eligible": False,
            }
        )
    if not shards:
        raise PublicationError("archive contains no intel NDJSON shards")
    return info.sha, sorted(shards, key=lambda item: item["path"])


def build_payloads(
    *, source_revision: str, archive_revision: str, shards: list[dict[str, Any]]
) -> dict[str, bytes]:
    source_revision = source_revision.lower()
    if FULL_SHA.fullmatch(source_revision) is None:
        raise PublicationError("source revision must be an exact 40-character Git SHA")
    manifest_rows = [
        json.dumps(
            {
                "schema": "szl.killinchu-archive-shard/v1",
                "observed_archive_revision": archive_revision,
                **shard,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for shard in shards
    ]
    manifest = ("\n".join(manifest_rows) + "\n").encode("utf-8")
    provenance = {
        "schema": "szl.dataset-source-attestation/v2",
        "dataset": REPO_ID,
        "source": {
            "repository": "szl-holdings/killinchu",
            "revision": source_revision,
            "relation": "CURRENT_ARCHIVE_WRITER_AND_PUBLICATION_CONTRACT",
            "historical_generator_lineage": "NOT_ESTABLISHED",
            "files": [
                source_file("killinchu_osint.py"),
                source_file("killinchu_intel_archive_card.py"),
                source_file("killinchu_intel_archive_publish.py"),
                source_file("datasets/killinchu-osint-corpus/README.md"),
                source_file("datasets/killinchu-osint-corpus/LICENSE.md"),
            ],
        },
        "archive": {
            "observed_revision": archive_revision,
            "shards": len(shards),
            "bytes": sum(int(item.get("bytes") or 0) for item in shards),
            "manifest_sha256": sha256_bytes(manifest),
            "file_hash_scope": "HUGGING_FACE_GIT_BLOB_SHA1_AT_IMMUTABLE_REVISION",
        },
        "license": {
            "classification": "MIXED_SOURCE_TERMS",
            "contract": "LICENSE.md",
            "row_level_rights_complete": False,
            "blanket_training_rights": False,
        },
        "viewer": {
            "config": "archive_manifest",
            "path": "viewer/archive_manifest.jsonl",
            "raw_ndjson_coerced_into_one_table": False,
        },
        "claims": {
            "record_truth": "NOT_CLAIMED",
            "reproducible_historical_generation": "NOT_CLAIMED",
            "raw_rows_training_eligible": False,
            "source_binding": "EXACT_CURRENT_WRITER_REVISION",
        },
    }
    return {
        "README.md": card.render_card().encode("utf-8"),
        "LICENSE.md": card.render_license().encode("utf-8"),
        "viewer/archive_manifest.jsonl": manifest,
        "DATASET_PROVENANCE.json": canonical_json(provenance),
    }


def publish(
    *, source_revision: str, token: str, report_path: Path, api: HfApi | None = None
) -> dict[str, Any]:
    if not token:
        raise PublicationError("HF_TOKEN is required")
    api = api or HfApi(token=token)
    archive_revision, shards = archive_snapshot(api)
    payloads = build_payloads(
        source_revision=source_revision,
        archive_revision=archive_revision,
        shards=shards,
    )
    commit = api.create_commit(
        repo_id=REPO_ID,
        repo_type="dataset",
        operations=[
            CommitOperationAdd(path_in_repo=path, path_or_fileobj=io.BytesIO(body))
            for path, body in payloads.items()
        ],
        commit_message=f"Bind archive snapshot to killinchu {source_revision[:12]}",
    )
    revision = getattr(commit, "oid", None) or api.dataset_info(REPO_ID).sha
    if FULL_SHA.fullmatch(str(revision)) is None:
        raise PublicationError("publication did not return an immutable revision")
    observed: dict[str, Any] = {}
    for path, expected in payloads.items():
        downloaded = Path(
            hf_hub_download(
                repo_id=REPO_ID,
                repo_type="dataset",
                filename=path,
                revision=revision,
                token=token,
                force_download=True,
            )
        ).read_bytes()
        if downloaded != expected:
            raise PublicationError(f"immutable readback mismatch: {path}")
        observed[path] = {"bytes": len(downloaded), "sha256": sha256_bytes(downloaded)}
    report = {
        "schema": "szl.killinchu-archive-publication/v2",
        "status": "PUBLISHED_AND_IMMUTABLE_READBACK_VERIFIED",
        "source_repository": "szl-holdings/killinchu",
        "source_revision": source_revision,
        "archive_revision_before_binding": archive_revision,
        "hf_revision_after": revision,
        "archive_shards_bound": len(shards),
        "raw_rows_training_eligible": False,
        "files": observed,
        "signed_release_receipt": "UNAVAILABLE_NO_APPROVED_OWNER_KEY_IN_WORKFLOW",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(canonical_json(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = publish(
        source_revision=args.source_revision,
        token=os.getenv("HF_TOKEN", ""),
        report_path=args.report,
    )
    print(canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
