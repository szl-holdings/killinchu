#!/usr/bin/env python3
"""Retire exact legacy Hugging Face Spaces after Killinchu convergence.

This program is intentionally not a generic deletion utility. The only provider
repositories it can mutate are the two exact thin/legacy public surfaces whose
useful capability and source history have already moved into Killinchu:

* ``SZLHOLDINGS/vessels``
* ``SZLHOLDINGS/aegis-assurance``

Sentra and IMMUNE are explicitly protected until their component engines pass
source-provenance and runtime-parity migrations. Secret values are never read;
secret *key metadata* must be empty before deletion. Every existing Space is
snapshotted and hashed before the irreversible provider call.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

SCHEMA = "szl.hf-legacy-resilience-retirement/v1"
HF_BASE = "https://huggingface.co"
KILLINCHU_SPACE = "SZLHOLDINGS/killinchu"
KILLINCHU_ORIGIN = "https://szlholdings-killinchu.hf.space"

# Exact allowlist. There is no CLI argument that can expand this set.
RETIREMENT_TARGETS: dict[str, str] = {
    "SZLHOLDINGS/vessels": "/vessels",
    "SZLHOLDINGS/aegis-assurance": "/resilience",
}

# These names are architecturally folded into Killinchu but remain migration
# sources. The deleter must never mutate them.
PROTECTED_MIGRATIONS = frozenset(
    {
        "SZLHOLDINGS/sentra",
        "SZLHOLDINGS/immune",
        "SZLHOLDINGS/immune-lattice",
    }
)

REQUIRED_RETIREMENT_GATES = frozenset(
    {
        "source_captured",
        "product_captured",
        "evidence_captured",
        "publisher_removed",
        "replacement_verified",
        "no_unique_secret_dependency",
        "secret_free_retirement_receipt",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_head(root: Path) -> str:
    value = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError(f"invalid Git source revision: {value!r}")
    return value


def _assignment_literal(source: str, name: str) -> Any:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(value)
    raise RuntimeError(f"assignment {name!r} was not found")


def verify_source_policies(killinchu_root: Path, a11oy_root: Path) -> dict[str, Any]:
    architecture = (
        killinchu_root / "docs" / "killinchu-cyber-resilience-consolidation.v1.json"
    )
    decision = killinchu_root / "docs" / "KILLINCHU-CYBER-RESILIENCE-CONSOLIDATION.md"
    vessels = killinchu_root / "docs" / "VESSELS-CONSOLIDATION.md"
    for path in (architecture, decision, vessels):
        if not path.is_file():
            raise RuntimeError(f"required Killinchu authority is missing: {path}")

    contract = json.loads(architecture.read_text(encoding="utf-8"))
    if contract.get("public_product", {}).get("huggingface_space") != KILLINCHU_SPACE:
        raise RuntimeError("Killinchu consolidation contract names the wrong replacement")
    if set(contract.get("retirement_gates", ())) != (
        REQUIRED_RETIREMENT_GATES - {"secret_free_retirement_receipt"}
    ):
        raise RuntimeError("Killinchu retirement-gate contract drifted")
    deletion = contract.get("deletion_policy", {})
    if deletion.get("delete_only_after_all_gates") is not True:
        raise RuntimeError("Killinchu contract no longer requires all deletion gates")
    if deletion.get("recreation_forbidden") is not True:
        raise RuntimeError("Killinchu contract no longer forbids legacy recreation")

    keep_path = a11oy_root / "docs" / "series-a" / "hf-space-keep-list.yaml"
    keep_text = keep_path.read_text(encoding="utf-8")
    try:
        keep_section, retire_section = keep_text.split("retire_into_killinchu:", 1)
    except ValueError as exc:
        raise RuntimeError("A11oy keep policy lacks the Killinchu retirement section") from exc
    for target in RETIREMENT_TARGETS:
        if f"- id: {target}" in keep_section:
            raise RuntimeError(f"legacy Space remains in active keeper set: {target}")
        if f"- id: {target}" not in retire_section:
            raise RuntimeError(f"legacy Space is absent from retirement policy: {target}")
    for protected in PROTECTED_MIGRATIONS:
        if f"- id: {protected}" not in retire_section:
            raise RuntimeError(f"protected migration disappeared from policy: {protected}")

    flagship_path = a11oy_root / "scripts" / "hf_publish_vertical_flagships_v4.py"
    flagship_source = flagship_path.read_text(encoding="utf-8")
    public = tuple(_assignment_literal(flagship_source, "PUBLIC_FLAGSHIP_SLUGS"))
    folded = tuple(_assignment_literal(flagship_source, "FOLDED_INTO_KILLINCHU"))
    if public != ("terra", "counsel", "finance", "lyte"):
        raise RuntimeError(f"unexpected active vertical publisher inventory: {public!r}")
    if folded != ("sentra", "vessels"):
        raise RuntimeError(f"unexpected folded vertical inventory: {folded!r}")

    packet_path = a11oy_root / ".github" / "scripts" / "publish_packet8_vertical_spaces.py"
    packet_source = packet_path.read_text(encoding="utf-8")
    if 'RETIRED_SPACE_IDS = frozenset({"SZLHOLDINGS/aegis-assurance"})' not in packet_source:
        raise RuntimeError("Packet 8 does not protect the retired Aegis Space id")
    active_packet = packet_source.split("SPACES = [", 1)[1].split("]", 1)[0]
    if "SZLHOLDINGS/aegis-assurance" in active_packet:
        raise RuntimeError("Packet 8 can still recreate Aegis assurance")

    return {
        "killinchu_policy_sha256": hashlib.sha256(architecture.read_bytes()).hexdigest(),
        "a11oy_keep_policy_sha256": hashlib.sha256(keep_path.read_bytes()).hexdigest(),
        "a11oy_public_vertical_spaces": list(public),
        "folded_into_killinchu": list(folded),
        "packet8_aegis_recreation_forbidden": True,
    }


def _build_revision(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    build = payload.get("build")
    if isinstance(build, dict):
        value = build.get("revision") or build.get("source_revision")
        if isinstance(value, str):
            return value
    for key in ("source_revision", "observed_source_revision", "revision"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def verify_live_replacement(source_sha: str, timeout_seconds: int = 300) -> dict[str, Any]:
    import requests

    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            response = requests.get(
                KILLINCHU_ORIGIN + "/api/build-info",
                headers={"Accept": "application/json", "Cache-Control": "no-cache"},
                params={"retirement_probe": time.time_ns()},
                timeout=20,
            )
            body = response.json() if response.status_code == 200 else None
            revision = _build_revision(body)
            last = {"status": response.status_code, "revision": revision}
            if response.status_code == 200 and revision == source_sha:
                break
        except (requests.RequestException, ValueError, TypeError) as exc:
            last = {"error": f"{type(exc).__name__}: {exc}"}
        time.sleep(10)
    else:
        raise RuntimeError(
            "Killinchu live source did not converge to the retiring main revision: "
            + json.dumps(last, sort_keys=True)
        )

    route_receipts: dict[str, Any] = {}
    expected_host = urlparse(KILLINCHU_ORIGIN).netloc
    for repo_id, route in RETIREMENT_TARGETS.items():
        response = requests.get(
            KILLINCHU_ORIGIN + route,
            headers={"Cache-Control": "no-cache"},
            params={"retirement_probe": time.time_ns()},
            timeout=30,
            allow_redirects=True,
        )
        final = urlparse(response.url)
        if response.status_code != 200:
            raise RuntimeError(f"replacement route failed for {repo_id}: {response.status_code}")
        if final.netloc != expected_host:
            raise RuntimeError(
                f"replacement route escaped Killinchu origin for {repo_id}: {response.url}"
            )
        if not response.content:
            raise RuntimeError(f"replacement route returned an empty body for {repo_id}")
        route_receipts[repo_id] = {
            "requested_route": route,
            "status": response.status_code,
            "final_path": final.path,
            "same_origin": True,
            "body_sha256": hashlib.sha256(response.content).hexdigest(),
            "observed_at": utc_now(),
        }

    return {
        "space": KILLINCHU_SPACE,
        "origin": KILLINCHU_ORIGIN,
        "source_revision": source_sha,
        "build_info": last,
        "routes": route_receipts,
    }


def _secret_keys(payload: Any) -> list[str]:
    if payload in (None, {}, []):
        return []
    if isinstance(payload, dict):
        if "secrets" in payload:
            return _secret_keys(payload["secrets"])
        # The Hub may return a mapping keyed by secret name.
        if all(isinstance(key, str) for key in payload):
            metadata_keys = {"key", "name", "description", "updatedAt", "createdAt"}
            if set(payload).issubset(metadata_keys):
                value = payload.get("key") or payload.get("name")
                return [str(value)] if value else []
            return sorted(str(key) for key in payload)
    if isinstance(payload, list):
        result: list[str] = []
        for item in payload:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                value = item.get("key") or item.get("name")
                if value:
                    result.append(str(value))
        return sorted(set(result))
    raise RuntimeError("unexpected Space secret-metadata payload")


def fetch_secret_key_metadata(repo_id: str, token: str) -> list[str]:
    import requests

    response = requests.get(
        f"{HF_BASE}/api/spaces/{repo_id}/secrets",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=20,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"cannot prove secret metadata for {repo_id}: HTTP {response.status_code}"
        )
    return _secret_keys(response.json())


def _runtime_storage(runtime: Any) -> Any:
    if runtime is None:
        return None
    if isinstance(runtime, dict):
        for key in ("storage", "storageTier", "persistentStorage"):
            if key in runtime:
                return runtime[key]
        return None
    for key in ("storage", "storage_tier", "persistent_storage"):
        if hasattr(runtime, key):
            return getattr(runtime, key)
    return None


def _has_persistent_storage(value: Any) -> bool:
    if value is None or value is False:
        return False
    normalized = str(value).strip().lower()
    return normalized not in {
        "",
        "none",
        "null",
        "false",
        "no_storage",
        "nostorage",
        "spacestoragetier.none",
    }


def _iter_snapshot_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == ".cache":
            continue
        yield path


def snapshot_space(repo_id: str, token: str, archive_root: Path) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    slug = repo_id.split("/", 1)[1]
    local = archive_root / slug / "repository"
    local.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        repo_type="space",
        token=token,
        local_dir=local,
    )

    files: list[dict[str, Any]] = []
    for path in _iter_snapshot_files(local):
        raw = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(local).as_posix(),
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    if not files:
        raise RuntimeError(f"refusing to delete an unsnapshotted Space: {repo_id}")

    manifest = {
        "schema": "szl.hf-space-source-snapshot/v1",
        "repo_id": repo_id,
        "observed_at": utc_now(),
        "files": files,
    }
    manifest_path = archive_root / slug / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    archive_path = archive_root / f"{slug}-pre-retirement.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(local, arcname=f"{slug}/repository", recursive=True)
        archive.add(manifest_path, arcname=f"{slug}/manifest.json")
    raw_archive = archive_path.read_bytes()
    return {
        "file_count": len(files),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "archive": archive_path.as_posix(),
        "archive_size": len(raw_archive),
        "archive_sha256": hashlib.sha256(raw_archive).hexdigest(),
    }


def retire_targets(
    token: str,
    archive_root: Path,
    dry_run: bool,
) -> list[dict[str, Any]]:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    results: list[dict[str, Any]] = []
    for repo_id, replacement_route in RETIREMENT_TARGETS.items():
        if repo_id in PROTECTED_MIGRATIONS:
            raise RuntimeError(f"protected migration entered deletion allowlist: {repo_id}")
        record: dict[str, Any] = {
            "repo_id": repo_id,
            "replacement_space": KILLINCHU_SPACE,
            "replacement_route": replacement_route,
            "started_at": utc_now(),
            "dry_run": dry_run,
        }
        exists = bool(api.repo_exists(repo_id=repo_id, repo_type="space"))
        record["existed_before"] = exists
        if not exists:
            record.update(
                {
                    "state": "ABSENT_ALREADY",
                    "deleted": False,
                    "verified_absent": True,
                    "completed_at": utc_now(),
                }
            )
            results.append(record)
            continue

        info = api.space_info(repo_id=repo_id)
        record["provider_revision_before"] = getattr(info, "sha", None)
        record["private_before"] = bool(getattr(info, "private", False))

        secret_keys = fetch_secret_key_metadata(repo_id, token)
        record["secret_key_count"] = len(secret_keys)
        record["secret_keys"] = secret_keys
        if secret_keys:
            raise RuntimeError(
                f"refusing to delete {repo_id}; Space secret metadata is not empty: {secret_keys}"
            )

        runtime = api.get_space_runtime(repo_id=repo_id)
        storage = _runtime_storage(runtime)
        record["persistent_storage_metadata"] = None if storage is None else str(storage)
        if _has_persistent_storage(storage):
            raise RuntimeError(
                f"refusing to delete {repo_id}; persistent storage is present: {storage!r}"
            )

        record["source_snapshot"] = snapshot_space(repo_id, token, archive_root)
        if dry_run:
            record.update(
                {
                    "state": "VERIFIED_DRY_RUN",
                    "deleted": False,
                    "verified_absent": False,
                    "completed_at": utc_now(),
                }
            )
            results.append(record)
            continue

        api.delete_repo(
            repo_id=repo_id,
            repo_type="space",
            missing_ok=False,
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if not api.repo_exists(repo_id=repo_id, repo_type="space"):
                break
            time.sleep(3)
        else:
            raise RuntimeError(f"provider still reports Space after deletion: {repo_id}")
        record.update(
            {
                "state": "DELETED_VERIFIED",
                "deleted": True,
                "verified_absent": True,
                "completed_at": utc_now(),
            }
        )
        results.append(record)
    return results


def write_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--killinchu-root", type=Path, default=Path("."))
    parser.add_argument("--a11oy-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "started_at": utc_now(),
        "source_revision": args.source_sha,
        "replacement_space": KILLINCHU_SPACE,
        "retirement_targets": dict(RETIREMENT_TARGETS),
        "protected_migrations": sorted(PROTECTED_MIGRATIONS),
        "required_gates": sorted(REQUIRED_RETIREMENT_GATES),
        "dry_run": bool(args.dry_run),
        "complete": False,
        "errors": [],
    }
    try:
        actual = git_head(args.killinchu_root)
        if actual != args.source_sha:
            raise RuntimeError(
                f"source revision mismatch: checkout={actual} expected={args.source_sha}"
            )
        a11oy_sha = git_head(args.a11oy_root)
        receipt["a11oy_policy_revision"] = a11oy_sha
        receipt["policy_proof"] = verify_source_policies(
            args.killinchu_root,
            args.a11oy_root,
        )
        receipt["replacement_proof"] = verify_live_replacement(args.source_sha)

        token = os.environ.get("HF_TOKEN", "").rstrip("\r\n")
        if not token:
            raise RuntimeError("HF_TOKEN is not configured")
        args.archive_root.mkdir(parents=True, exist_ok=True)
        receipt["results"] = retire_targets(token, args.archive_root, args.dry_run)
        receipt["complete"] = all(
            row.get("state")
            in {"ABSENT_ALREADY", "VERIFIED_DRY_RUN", "DELETED_VERIFIED"}
            for row in receipt["results"]
        )
        receipt["completed_at"] = utc_now()
        write_receipt(args.output, receipt)
        return 0 if receipt["complete"] else 1
    except Exception as exc:  # noqa: BLE001 - fail-closed evidence boundary
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["completed_at"] = utc_now()
        write_receipt(args.output, receipt)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
