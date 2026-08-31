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
import math
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
from huggingface_hub.errors import EntryNotFoundError

import killinchu_intel_archive_card as card


ROOT = Path(__file__).resolve().parent
REPO_ID = "SZLHOLDINGS/killinchu-osint-corpus"
SOURCE_REPOSITORY = "szl-holdings/killinchu"
DEFAULT_BRANCH = "main"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
GITHUB_TIMEOUT_SECONDS = 10.0
MAX_GITHUB_RESPONSE_BYTES = 65_536
GITHUB_READ_CHUNK_BYTES = 8_192


class PublicationError(RuntimeError):
    """Raised when an exact archive publication cannot be proven."""


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def exact_revision(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or FULL_SHA.fullmatch(value) is None:
        raise PublicationError(f"{field} must be an exact lowercase 40-character Git SHA")
    return value


def github_default_branch_tip(
    *,
    token: str,
    api_url: str,
    repository: str,
    timeout_seconds: float = GITHUB_TIMEOUT_SECONDS,
    opener: Any = urllib.request.urlopen,
) -> str:
    """Read current protected main with a bounded, authenticated GitHub request."""
    if not token:
        raise PublicationError("GITHUB_TOKEN is required")
    if repository != SOURCE_REPOSITORY:
        raise PublicationError("unexpected GitHub source repository")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or float(timeout_seconds) <= 0
        or float(timeout_seconds) > 30
    ):
        raise PublicationError("GitHub timeout must be finite and bounded")
    try:
        parsed = urllib.parse.urlsplit(api_url)
        invalid_origin = (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or bool(parsed.query)
            or bool(parsed.fragment)
        )
    except (TypeError, ValueError):
        invalid_origin = True
    if invalid_origin:
        raise PublicationError("GITHUB_API_URL is not an allowed HTTPS API origin")

    expected_ref = f"refs/heads/{DEFAULT_BRANCH}"
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/repos/{repository}/git/ref/heads/{DEFAULT_BRANCH}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=float(timeout_seconds)) as response:
            if getattr(response, "status", None) != 200:
                raise PublicationError("GitHub protected-main lookup returned a non-200 status")
            body = bytearray()
            while len(body) <= MAX_GITHUB_RESPONSE_BYTES:
                remaining = MAX_GITHUB_RESPONSE_BYTES + 1 - len(body)
                chunk = response.read(min(GITHUB_READ_CHUNK_BYTES, remaining))
                if not isinstance(chunk, bytes):
                    raise PublicationError(
                        "GitHub protected-main response was not a byte stream"
                    )
                if not chunk:
                    break
                if len(chunk) > remaining:
                    raise PublicationError(
                        "GitHub protected-main response exceeded the size limit"
                    )
                body.extend(chunk)
    except PublicationError:
        raise
    except Exception as exc:
        raise PublicationError(
            f"GitHub protected-main lookup failed ({type(exc).__name__})"
        ) from None
    if len(body) > MAX_GITHUB_RESPONSE_BYTES:
        raise PublicationError("GitHub protected-main response exceeded the size limit")
    try:
        payload = json.loads(bytes(body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PublicationError("GitHub protected-main response was not valid JSON") from None
    if not isinstance(payload, dict) or payload.get("ref") != expected_ref:
        raise PublicationError("GitHub protected-main response named an unexpected ref")
    target = payload.get("object")
    if not isinstance(target, dict) or target.get("type") != "commit":
        raise PublicationError("GitHub protected-main response was not a commit ref")
    revision = target.get("sha")
    return exact_revision(revision, field="GitHub protected-main revision")


def write_evidence(report_path: Path, payload: dict[str, Any]) -> None:
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(canonical_json(payload))
    except OSError as exc:
        raise PublicationError(
            f"publication evidence persistence failed ({type(exc).__name__})"
        ) from None


def failure_evidence(
    *,
    status: str,
    stage: str,
    source_revision: str,
    archive_revision: str | None,
    mutation_outcome: str,
    failure_code: str,
    github_main_revision: str | None = None,
    hf_revision: str | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "schema": "szl.killinchu-archive-publication/v3",
        "status": status,
        "stage": stage,
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": source_revision,
        "mutation_outcome": mutation_outcome,
        "failure_code": failure_code,
        "current_main_publication": False,
        "source_binding": "NOT_ESTABLISHED",
        "signed_release_receipt": "UNAVAILABLE_NO_APPROVED_OWNER_KEY_IN_WORKFLOW",
    }
    if archive_revision is not None:
        evidence["archive_revision_before_binding"] = archive_revision
    if github_main_revision is not None:
        evidence["github_main_revision_observed"] = github_main_revision
    if hf_revision is not None:
        evidence["hf_revision_observed_after_mutation"] = hf_revision
    return evidence


def fail_with_evidence(
    *, report_path: Path, evidence: dict[str, Any], message: str
) -> None:
    try:
        write_evidence(report_path, evidence)
    except PublicationError as exc:
        raise PublicationError(f"{message}; {exc}") from None
    raise PublicationError(message)


def observe_hf_revision(api: HfApi) -> str | None:
    """Best-effort authoritative revision read after an ambiguous mutation."""
    try:
        revision = getattr(api.dataset_info(REPO_ID), "sha", None)
    except Exception:
        return None
    if isinstance(revision, str) and FULL_SHA.fullmatch(revision) is not None:
        return revision
    return None


def source_file(path: str) -> dict[str, Any]:
    body = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    return {"path": path, "bytes": len(body), "sha256": sha256_bytes(body)}


def shard_state_sha256(shards: list[dict[str, Any]]) -> str:
    """Fingerprint the raw shard state independently of binding-only commits."""
    return sha256_bytes(canonical_json(shards))


def binding_is_current(
    existing: bytes, *, source_revision: str, shards: list[dict[str, Any]]
) -> bool:
    try:
        payload = json.loads(existing)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return (
        payload.get("source", {}).get("revision") == source_revision
        and payload.get("archive", {}).get("shard_state_sha256")
        == shard_state_sha256(shards)
    )


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
            "repository": SOURCE_REPOSITORY,
            "revision": source_revision,
            "relation": "PRE_MUTATION_PROTECTED_MAIN_AUTHORIZED_ARCHIVE_CONTRACT",
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
            "shard_state_sha256": shard_state_sha256(shards),
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
            "source_binding": "PRE_MUTATION_PROTECTED_MAIN_AUTHORIZED",
        },
    }
    return {
        "README.md": card.render_card().encode("utf-8"),
        "LICENSE.md": card.render_license().encode("utf-8"),
        "viewer/archive_manifest.jsonl": manifest,
        "DATASET_PROVENANCE.json": canonical_json(provenance),
    }


def publish(
    *,
    source_revision: str,
    token: str,
    github_token: str,
    github_repository: str,
    github_api_url: str,
    report_path: Path,
    api: HfApi | None = None,
    github_tip_reader: Any = github_default_branch_tip,
) -> dict[str, Any]:
    if not token:
        raise PublicationError("HF_TOKEN is required")
    if not github_token:
        raise PublicationError("GITHUB_TOKEN is required")
    if github_repository != SOURCE_REPOSITORY:
        raise PublicationError("unexpected GitHub source repository")
    source_revision = exact_revision(source_revision, field="source revision")
    api = api or HfApi(token=token)
    try:
        archive_revision, shards = archive_snapshot(api)
        try:
            existing = Path(
                hf_hub_download(
                    repo_id=REPO_ID,
                    repo_type="dataset",
                    filename="DATASET_PROVENANCE.json",
                    revision=archive_revision,
                    token=token,
                    force_download=True,
                )
            ).read_bytes()
        except EntryNotFoundError:
            existing = b""
        already_bound = binding_is_current(
            existing, source_revision=source_revision, shards=shards
        )
        payloads = (
            {}
            if already_bound
            else build_payloads(
                source_revision=source_revision,
                archive_revision=archive_revision,
                shards=shards,
            )
        )
        operations = [
            CommitOperationAdd(path_in_repo=path, path_or_fileobj=io.BytesIO(body))
            for path, body in payloads.items()
        ]
    except Exception as exc:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="FAILED_BEFORE_MUTATION",
                stage="HF_READ_AND_RENDER",
                source_revision=source_revision,
                archive_revision=None,
                mutation_outcome="NOT_ENTERED",
                failure_code=f"HF_READ_OR_RENDER_{type(exc).__name__.upper()}",
            ),
            message="archive read or publication rendering failed before mutation",
        )

    try:
        pre_mutation_main = github_tip_reader(
            token=github_token,
            api_url=github_api_url,
            repository=github_repository,
            timeout_seconds=GITHUB_TIMEOUT_SECONDS,
        )
        pre_mutation_main = exact_revision(
            pre_mutation_main, field="GitHub protected-main revision"
        )
    except Exception as exc:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="FAILED_BEFORE_MUTATION",
                stage="PRE_MUTATION_GITHUB_REAUTHORIZATION",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="NOT_ENTERED",
                failure_code=f"GITHUB_REAUTHORIZATION_{type(exc).__name__.upper()}",
            ),
            message="protected-main reauthorization failed before mutation",
        )
    if pre_mutation_main != source_revision:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="FAILED_BEFORE_MUTATION_STALE_SOURCE",
                stage="PRE_MUTATION_GITHUB_REAUTHORIZATION",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="NOT_ENTERED",
                failure_code="GITHUB_MAIN_DRIFT",
                github_main_revision=pre_mutation_main,
            ),
            message="publication source is no longer current protected main",
        )

    if already_bound:
        report = {
            "schema": "szl.killinchu-archive-publication/v3",
            "status": "ALREADY_BOUND_NO_COMMIT",
            "stage": "CURRENT_MAIN_NOOP_VERIFIED",
            "source_repository": SOURCE_REPOSITORY,
            "source_revision": source_revision,
            "github_main_revision_observed": pre_mutation_main,
            "hf_revision": archive_revision,
            "archive_shards_bound": len(shards),
            "raw_rows_training_eligible": False,
            "shard_state_sha256": shard_state_sha256(shards),
            "mutation_outcome": "NOT_ENTERED",
            "current_main_publication": True,
            "source_binding": "EXACT_CURRENT_WRITER_REVISION",
            "signed_release_receipt": "UNAVAILABLE_NO_APPROVED_OWNER_KEY_IN_WORKFLOW",
        }
        write_evidence(report_path, report)
        return report

    try:
        commit = api.create_commit(
            repo_id=REPO_ID,
            repo_type="dataset",
            operations=operations,
            commit_message=f"Bind archive snapshot to killinchu {source_revision[:12]}",
        )
    except Exception as exc:
        observed_hf_revision = observe_hf_revision(api)
        ambiguous_main: str | None = None
        github_failure: str | None = None
        try:
            ambiguous_main = exact_revision(
                github_tip_reader(
                    token=github_token,
                    api_url=github_api_url,
                    repository=github_repository,
                    timeout_seconds=GITHUB_TIMEOUT_SECONDS,
                ),
                field="GitHub protected-main revision",
            )
        except Exception as github_exc:
            github_failure = type(github_exc).__name__.upper()
        drifted = ambiguous_main is not None and ambiguous_main != source_revision
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status=(
                    "PARTIAL_AFTER_AMBIGUOUS_MUTATION_STALE_SOURCE"
                    if drifted and observed_hf_revision is not None
                    else "MUTATION_OUTCOME_UNKNOWN_STALE_SOURCE"
                    if drifted
                    else "MUTATION_OUTCOME_UNKNOWN"
                ),
                stage="HF_CREATE_COMMIT_AMBIGUOUS",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="UNKNOWN",
                failure_code=(
                    "GITHUB_MAIN_DRIFT_AFTER_AMBIGUOUS_MUTATION"
                    if drifted
                    else f"CREATE_COMMIT_{type(exc).__name__.upper()}"
                    + (f"_GITHUB_{github_failure}" if github_failure else "")
                ),
                github_main_revision=ambiguous_main,
                hf_revision=observed_hf_revision,
            ),
            message="Hugging Face mutation outcome is unknown",
        )

    revision_value = getattr(commit, "oid", None)
    if not isinstance(revision_value, str) or FULL_SHA.fullmatch(revision_value) is None:
        observed_hf_revision = observe_hf_revision(api)
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="MUTATION_OUTCOME_UNKNOWN",
                stage="HF_CREATE_COMMIT_RESPONSE",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="UNKNOWN",
                failure_code="CREATE_COMMIT_MALFORMED_REVISION",
                hf_revision=observed_hf_revision,
            ),
            message="publication did not return an immutable revision",
        )
    revision = revision_value

    try:
        post_mutation_main = exact_revision(
            github_tip_reader(
                token=github_token,
                api_url=github_api_url,
                repository=github_repository,
                timeout_seconds=GITHUB_TIMEOUT_SECONDS,
            ),
            field="GitHub protected-main revision",
        )
    except Exception as exc:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="PARTIAL_AFTER_MUTATION",
                stage="POST_MUTATION_GITHUB_REAUTHORIZATION",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="KNOWN",
                failure_code=f"GITHUB_REAUTHORIZATION_{type(exc).__name__.upper()}",
                hf_revision=revision,
            ),
            message="protected-main reauthorization failed after mutation",
        )
    if post_mutation_main != source_revision:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="PARTIAL_AFTER_MUTATION_STALE_SOURCE",
                stage="POST_MUTATION_GITHUB_REAUTHORIZATION",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="KNOWN",
                failure_code="GITHUB_MAIN_DRIFT_AFTER_MUTATION",
                github_main_revision=post_mutation_main,
                hf_revision=revision,
            ),
            message="protected main drifted after Hugging Face mutation",
        )

    observed: dict[str, Any] = {}
    try:
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
            observed[path] = {
                "bytes": len(downloaded),
                "sha256": sha256_bytes(downloaded),
            }
    except Exception as exc:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="PARTIAL_AFTER_MUTATION",
                stage="IMMUTABLE_HF_READBACK",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="KNOWN",
                failure_code=f"IMMUTABLE_READBACK_{type(exc).__name__.upper()}",
                github_main_revision=post_mutation_main,
                hf_revision=revision,
            ),
            message="immutable Hugging Face readback failed after mutation",
        )

    try:
        final_main = exact_revision(
            github_tip_reader(
                token=github_token,
                api_url=github_api_url,
                repository=github_repository,
                timeout_seconds=GITHUB_TIMEOUT_SECONDS,
            ),
            field="GitHub protected-main revision",
        )
    except Exception as exc:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="PARTIAL_AFTER_MUTATION",
                stage="FINAL_GITHUB_REAUTHORIZATION",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="KNOWN",
                failure_code=f"GITHUB_REAUTHORIZATION_{type(exc).__name__.upper()}",
                hf_revision=revision,
            ),
            message="final protected-main reauthorization failed after mutation",
        )
    if final_main != source_revision:
        fail_with_evidence(
            report_path=report_path,
            evidence=failure_evidence(
                status="PARTIAL_AFTER_MUTATION_STALE_SOURCE",
                stage="FINAL_GITHUB_REAUTHORIZATION",
                source_revision=source_revision,
                archive_revision=archive_revision,
                mutation_outcome="KNOWN",
                failure_code="GITHUB_MAIN_DRIFT_DURING_READBACK",
                github_main_revision=final_main,
                hf_revision=revision,
            ),
            message="protected main drifted during immutable readback",
        )

    report = {
        "schema": "szl.killinchu-archive-publication/v3",
        "status": "PUBLISHED_AND_IMMUTABLE_READBACK_VERIFIED",
        "stage": "CURRENT_MAIN_PUBLICATION_VERIFIED",
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": source_revision,
        "github_main_revision_observed": final_main,
        "archive_revision_before_binding": archive_revision,
        "hf_revision_after": revision,
        "archive_shards_bound": len(shards),
        "shard_state_sha256": shard_state_sha256(shards),
        "raw_rows_training_eligible": False,
        "files": observed,
        "mutation_outcome": "KNOWN",
        "current_main_publication": True,
        "source_binding": "EXACT_CURRENT_WRITER_REVISION",
        "signed_release_receipt": "UNAVAILABLE_NO_APPROVED_OWNER_KEY_IN_WORKFLOW",
    }
    write_evidence(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--github-api-url", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = publish(
        source_revision=args.source_revision,
        token=os.getenv("HF_TOKEN", ""),
        github_token=os.getenv("GITHUB_TOKEN", ""),
        github_repository=args.github_repository,
        github_api_url=args.github_api_url,
        report_path=args.report,
    )
    print(canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
