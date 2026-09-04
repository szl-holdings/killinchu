#!/usr/bin/env python3
"""Snapshot and retire only the former SZLHOLDINGS/sentra Space.

This is an exact-target migration transaction, not a generic deletion tool. It
requires the current Killinchu protected-main revision to be live, source-bound,
and serving the same-origin Defend plane. It preserves the complete current
Sentra repository in the public creator-profile Command Centre, verifies every
archived byte, checks secret-key and storage safety, deletes the former Space,
verifies provider absence, and publishes a final secret-free receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, HfHubHTTPError, snapshot_download

TARGET = "SZLHOLDINGS/sentra"
REPLACEMENT = "SZLHOLDINGS/killinchu"
COMMAND_CENTRE = "betterwithage/szl-command-centre"
EXPECTED_IDENTITY = "betterwithage"
SOURCE_AUTHORITY = "szl-holdings/szl-defensive-control-plane"
BASE_URL = "https://szlholdings-killinchu.hf.space"
GITHUB_RAW = "https://raw.githubusercontent.com"
TOKEN = os.environ["HF_TOKEN"].rstrip("\r\n")
SOURCE_SHA = os.environ["GITHUB_SHA"].lower()
WORKFLOW_RUN_ID = os.environ.get("GITHUB_RUN_ID", "")
api = HfApi(token=TOKEN)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get(url: str, *, accept: str = "application/json", timeout: int = 25) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": "szl-sentra-retirement/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.headers.get("content-type", ""), response.read(4_000_000)


def get_json(path: str) -> dict[str, Any]:
    status, content_type, raw = get(BASE_URL + path)
    if status != 200 or "json" not in content_type.lower():
        raise RuntimeError(f"replacement route is not JSON 200: {path}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"replacement route returned non-object JSON: {path}")
    return value


def stage(runtime: object) -> str:
    value = getattr(runtime, "stage", None)
    return str(getattr(value, "value", value) or "UNKNOWN").upper()


def metadata_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value}
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            if isinstance(item, str):
                keys.add(item)
            elif isinstance(item, dict):
                key = item.get("key") or item.get("name")
                if key:
                    keys.add(str(key))
            else:
                key = getattr(item, "key", None) or getattr(item, "name", None)
                if key:
                    keys.add(str(key))
        return keys
    return set()


def verify_publishers() -> dict[str, str]:
    urls = {
        "a11oy_entrypoint": (
            f"{GITHUB_RAW}/szl-holdings/a11oy/main/"
            "scripts/hf_publish_vertical_flagships_v4.py"
        ),
        "a11oy_topology": (
            f"{GITHUB_RAW}/szl-holdings/a11oy/main/"
            "docs/estate/PUBLIC_VERTICAL_TOPOLOGY.md"
        ),
        "vertical_services_writer": (
            f"{GITHUB_RAW}/szl-holdings/vertical-services/main/"
            ".github/workflows/hf-space.yml"
        ),
        "killinchu_writer": (
            f"{GITHUB_RAW}/szl-holdings/killinchu/main/"
            ".github/workflows/hf-sync.yml"
        ),
    }
    texts: dict[str, str] = {}
    for name, url in urls.items():
        status, _, raw = get(url, accept="text/plain")
        if status != 200:
            raise RuntimeError(f"publisher authority unavailable: {name}")
        texts[name] = raw.decode("utf-8")

    entry = texts["a11oy_entrypoint"]
    if 'PUBLIC_FLAGSHIP_SLUGS = ("terra", "counsel", "finance", "lyte")' not in entry:
        raise RuntimeError("A11oy independent-Space allowlist drifted")
    if 'FOLDED_INTO_KILLINCHU = ("sentra", "vessels")' not in entry:
        raise RuntimeError("A11oy no longer records Sentra as folded into Killinchu")
    topology = texts["a11oy_topology"]
    if "Aegis, Sentra, Immune and Vessels" not in topology or "inside Killinchu" not in topology:
        raise RuntimeError("public vertical topology does not close the Sentra fold")
    if "hf-repo: SZLHOLDINGS/vertical-services" not in texts["vertical_services_writer"]:
        raise RuntimeError("Vertical Services writer target drifted")
    if "hf-repo: SZLHOLDINGS/killinchu" not in texts["killinchu_writer"]:
        raise RuntimeError("Killinchu writer target drifted")
    return {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in texts.items()}


def verify_replacement() -> dict[str, Any]:
    if len(SOURCE_SHA) != 40 or any(char not in "0123456789abcdef" for char in SOURCE_SHA):
        raise RuntimeError("workflow source revision is not an exact SHA-1")
    info = api.repo_info(repo_id=REPLACEMENT, repo_type="space")
    if bool(getattr(info, "private", False)):
        raise RuntimeError("replacement Space is private")
    runtime_stage = stage(api.get_space_runtime(repo_id=REPLACEMENT))
    if runtime_stage != "RUNNING":
        raise RuntimeError(f"replacement Space is not RUNNING: {runtime_stage}")

    build = get_json("/api/build-info")
    observed = str(
        (build.get("build") or {}).get("revision")
        or build.get("gitSha")
        or build.get("source_revision")
        or ""
    ).lower()
    if observed != SOURCE_SHA:
        raise RuntimeError(f"replacement source mismatch: {observed} != {SOURCE_SHA}")

    status = get_json("/api/defend/status")
    source = get_json("/api/defend/source")
    required = {
        "public_product": "Killinchu",
        "capability_plane": "Defend",
        "effectors_enabled": False,
        "human_approval_required": True,
        "arbitrary_command_execution": False,
    }
    for key, expected in required.items():
        if status.get(key) != expected:
            raise RuntimeError(f"Defend status mismatch: {key}={status.get(key)!r}")
    if source.get("source_repository") != SOURCE_AUTHORITY:
        raise RuntimeError("Defend source authority mismatch")
    source_revision = str(source.get("source_revision") or "")
    if len(source_revision) != 40:
        raise RuntimeError("Defend source authority is not revision-bound")
    if source.get("integration_mode") != "SOURCE_BOUND_PORT":
        raise RuntimeError("Defend integration mode drifted")

    html_status, html_type, raw = get(BASE_URL + "/defend", accept="text/html")
    text = raw.decode("utf-8", errors="replace").lower()
    if html_status != 200 or "html" not in html_type.lower():
        raise RuntimeError("Defend UI is not HTML 200")
    for marker in ("killinchu defend", "human approval", "rollback", "receipt"):
        if marker not in text:
            raise RuntimeError(f"Defend UI marker missing: {marker}")
    return {
        "space_revision": str(getattr(info, "sha", "") or ""),
        "source_revision": observed,
        "runtime_stage": runtime_stage,
        "defend_source_revision": source_revision,
        "status_sha256": hashlib.sha256(
            json.dumps(status, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "source_sha256": hashlib.sha256(
            json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "ui_sha256": hashlib.sha256(raw).hexdigest(),
    }


def source_exists() -> bool:
    try:
        api.repo_info(repo_id=TARGET, repo_type="space")
        return True
    except HfHubHTTPError as exc:
        if getattr(exc.response, "status_code", None) == 404:
            return False
        raise


def snapshot_source(root: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    info = api.repo_info(repo_id=TARGET, repo_type="space")
    source_revision = str(getattr(info, "sha", "") or "")
    if len(source_revision) != 40:
        raise RuntimeError("former Sentra Space lacks an exact revision")

    runtime = api.get_space_runtime(repo_id=TARGET)
    storage = getattr(runtime, "storage", None)
    if storage not in (None, "", False):
        raise RuntimeError(f"former Sentra Space has attached storage: {storage!r}")

    sentra_secrets = metadata_keys(api.get_space_secrets(TARGET))
    killinchu_secrets = metadata_keys(api.get_space_secrets(REPLACEMENT))
    missing_secret_contracts = sentra_secrets - killinchu_secrets
    if missing_secret_contracts:
        raise RuntimeError(
            "former Sentra Space has secret-key contracts absent from Killinchu: "
            + ", ".join(sorted(missing_secret_contracts))
        )

    local = Path(
        snapshot_download(
            repo_id=TARGET,
            repo_type="space",
            revision=source_revision,
            token=TOKEN,
            local_dir=root / "source",
            force_download=True,
        )
    )
    files: list[dict[str, Any]] = []
    for path in sorted(local.rglob("*")):
        if not path.is_file() or ".cache" in path.parts or ".git" in path.parts:
            continue
        relative = path.relative_to(local).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    if not files:
        raise RuntimeError("refusing to retire an empty or unreadable source snapshot")
    metadata = {
        "private": bool(getattr(info, "private", False)),
        "sdk": getattr(info, "sdk", None),
        "runtime_stage": stage(runtime),
        "storage": None,
        "secret_keys": sorted(sentra_secrets),
        "replacement_secret_keys": sorted(killinchu_secrets),
        "secret_values_read": False,
    }
    return source_revision, files, metadata


def archive_and_verify(
    root: Path,
    source_revision: str,
    files: list[dict[str, Any]],
    metadata: dict[str, Any],
    replacement: dict[str, Any],
    publisher_hashes: dict[str, str],
) -> tuple[str, str]:
    source = root / "source"
    prefix = f"archive/sentra-final/{source_revision}"
    manifest = {
        "schema": "szl.hf-space-source-snapshot/v1",
        "captured_at": now(),
        "source_repo_id": TARGET,
        "source_revision": source_revision,
        "replacement_repo_id": REPLACEMENT,
        "replacement_routes": ["/resilience", "/defend", "/aegis", "/sentra"],
        "source_authority": SOURCE_AUTHORITY,
        "workflow_source_revision": SOURCE_SHA,
        "workflow_run_id": WORKFLOW_RUN_ID,
        "metadata": metadata,
        "replacement_evidence": replacement,
        "publisher_authority_sha256": publisher_hashes,
        "file_count": len(files),
        "bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    manifest_path = source / "SZL_SENTRA_FINAL_SNAPSHOT_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = files + [{
        "path": "SZL_SENTRA_FINAL_SNAPSHOT_MANIFEST.json",
        "bytes": manifest_path.stat().st_size,
        "sha256": sha256(manifest_path),
    }]
    commit = api.upload_folder(
        repo_id=COMMAND_CENTRE,
        repo_type="space",
        folder_path=str(source),
        path_in_repo=prefix,
        commit_message=f"Preserve final Sentra Space snapshot {source_revision[:12]}",
    )
    archive_revision = str(commit.oid)
    verify_root = Path(
        snapshot_download(
            repo_id=COMMAND_CENTRE,
            repo_type="space",
            revision=archive_revision,
            token=TOKEN,
            allow_patterns=[f"{prefix}/**"],
            local_dir=root / "verify",
            force_download=True,
        )
    ) / prefix
    failures = []
    for item in expected:
        path = verify_root / item["path"]
        if not path.is_file():
            failures.append(f"missing:{item['path']}")
        elif sha256(path) != item["sha256"]:
            failures.append(f"hash:{item['path']}")
    if failures:
        raise RuntimeError(f"Command Centre read-back failed: {failures[:20]}")
    return archive_revision, prefix


def verify_absent() -> None:
    for _ in range(12):
        if not source_exists():
            return
        time.sleep(5)
    raise RuntimeError("former Sentra Space still exists after delete_repo")


def publish_final_receipt(receipt: dict[str, Any], root: Path) -> str:
    path = root / "SZL_SENTRA_SPACE_RETIREMENT_RECEIPT.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    commit = api.upload_file(
        repo_id=COMMAND_CENTRE,
        repo_type="space",
        path_or_fileobj=str(path),
        path_in_repo=f"receipts/sentra-retirement-{receipt['source_revision']}.json",
        commit_message=f"Publish verified Sentra retirement receipt {receipt['source_revision'][:12]}",
    )
    revision = str(commit.oid)
    remote = Path(
        snapshot_download(
            repo_id=COMMAND_CENTRE,
            repo_type="space",
            revision=revision,
            token=TOKEN,
            allow_patterns=[f"receipts/sentra-retirement-{receipt['source_revision']}.json"],
            local_dir=root / "receipt-verify",
            force_download=True,
        )
    ) / f"receipts/sentra-retirement-{receipt['source_revision']}.json"
    if not remote.is_file() or sha256(remote) != sha256(path):
        raise RuntimeError("final retirement receipt failed remote read-back")
    return revision


def main() -> int:
    if not TOKEN:
        raise RuntimeError("HF_TOKEN is not configured")
    identity = api.whoami(token=TOKEN)
    identity_name = str(identity.get("name") or identity.get("fullname") or "")
    if identity_name.lower() != EXPECTED_IDENTITY:
        raise RuntimeError(
            f"wrong Hugging Face identity: expected {EXPECTED_IDENTITY}, got {identity_name!r}"
        )

    publisher_hashes = verify_publishers()
    replacement = verify_replacement()
    root = Path(tempfile.mkdtemp(prefix="szl-sentra-retire-"))
    try:
        if not source_exists():
            receipt = {
                "schema": "szl.hf-space-retirement/v1",
                "state": "ALREADY_ABSENT_VERIFIED",
                "completed_at": now(),
                "target": TARGET,
                "replacement": REPLACEMENT,
                "replacement_evidence": replacement,
                "publisher_authority_sha256": publisher_hashes,
                "workflow_source_revision": SOURCE_SHA,
                "workflow_run_id": WORKFLOW_RUN_ID,
                "source_revision": "ALREADY_ABSENT",
                "secret_values_read": False,
            }
            path = root / "SZL_SENTRA_SPACE_RETIREMENT_RECEIPT.json"
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            output = Path(os.environ.get("RETIREMENT_RECEIPT_PATH", "sentra-retirement-receipt.json"))
            shutil.copyfile(path, output)
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return 0

        source_revision, files, metadata = snapshot_source(root)
        archive_revision, archive_prefix = archive_and_verify(
            root,
            source_revision,
            files,
            metadata,
            replacement,
            publisher_hashes,
        )
        # Recheck immutable source at the irreversible boundary.
        current = str(api.repo_info(repo_id=TARGET, repo_type="space").sha)
        if current != source_revision:
            raise RuntimeError(
                f"former Sentra Space changed during preservation: {source_revision} -> {current}"
            )

        api.delete_repo(repo_id=TARGET, repo_type="space", missing_ok=False)
        verify_absent()
        receipt = {
            "schema": "szl.hf-space-retirement/v1",
            "state": "DELETED_AND_VERIFIED",
            "completed_at": now(),
            "target": TARGET,
            "source_revision": source_revision,
            "source_file_count": len(files),
            "source_bytes": sum(item["bytes"] for item in files),
            "source_metadata": metadata,
            "archive": {
                "repo_id": COMMAND_CENTRE,
                "revision": archive_revision,
                "prefix": archive_prefix,
                "readback_verified": True,
            },
            "replacement": REPLACEMENT,
            "replacement_routes": ["/resilience", "/defend", "/aegis", "/sentra"],
            "replacement_evidence": replacement,
            "publisher_authority_sha256": publisher_hashes,
            "provider_absence_verified": True,
            "secret_values_read": False,
            "workflow_source_revision": SOURCE_SHA,
            "workflow_run_id": WORKFLOW_RUN_ID,
        }
        receipt_revision = publish_final_receipt(receipt, root)
        receipt["final_receipt_revision"] = receipt_revision
        output = Path(os.environ.get("RETIREMENT_RECEIPT_PATH", "sentra-retirement-receipt.json"))
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
