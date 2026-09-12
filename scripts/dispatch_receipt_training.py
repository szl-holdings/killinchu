#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Manual, exact-source training dispatch. Submission is never completion.

No training, Hub writes or network operations occur on import or validation-only.
The durable Hub reservation deliberately remains consumed after any uncertainty.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import functools
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import time
import unicodedata
import urllib.request

from scripts.receipt_training_worker import (
    APPROVED_RUNTIMES, ARTIFACT_NAMES, NON_RUNNABLE_TEST_RUNTIME,
    canonical_sha256, parse_json, validate_dataset_records, validate_manifest,
)

REPOSITORY = "szl-holdings/killinchu"
WORKER_PATH = "scripts/receipt_training_worker.py"
MAX_JSON = 256 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_SAFETENSORS_HEADER_BYTES = 8 * 1024 * 1024
MAX_REPO_TREE_ENTRIES = 20_000
MAX_REPO_TREE_PATH_BYTES = 2 * 1024 * 1024
MAX_REPO_PATH_BYTES = 2_048
SAFE_TENSOR_DTYPES = {"F16": 2, "BF16": 2, "F32": 4}
SHA = re.compile(r"[0-9a-f]{40}\Z")
RESULT_PREFIX = "SZL_TRAINING_RESULT="
GITHUB_ACTIONS_APP_ID = 15368
CHECK_RUNS_PER_PAGE = 50
MAX_CHECK_RUN_PAGES = 20
# This is the protected-main policy read back on 2026-09-12 plus the
# provider-free receipt-training contract introduced by this change. Required
# evidence must be an exact-name GitHub Check Run from the GitHub Actions app;
# legacy commit statuses are intentionally not accepted because they do not
# expose an equivalent, unambiguous app identity in the status response.
REQUIRED_SOURCE_CHECKS = frozenset(
    {
        "Canonical mixed-source card contract",
        "test (3.11)",
        "test (3.12)",
        "public-experience-contract",
        "Gitleaks secret scan",
        "Trivy filesystem scan",
        "Grype CVE gate (fail on HIGH/CRITICAL)",
        "Analyze (python)",
        "Analyze (actions)",
        "High-severity security regressions",
        "Shared source files in sync with a11oy",
        "check / doctrine",
        "overclaim / Governed surfaces are honest (Theorem U citation rule)",
        "offline-contract",
    }
)


class DispatchError(ValueError):
    """Only constant, non-sensitive error codes cross the CLI boundary."""


@contextlib.contextmanager
def deadline_guard(seconds: float, *, required=False):
    """Absolute wall-clock bound, including non-yielding SDK/SSE operations.

    The authorized CLI is Linux-runner-only and requires this capability before
    constructing a provider. Windows import/offline dependency-injection tests
    need no timer; they are not a supported cloud execution entry point.
    """
    if not hasattr(signal, "setitimer") or not hasattr(signal, "SIGALRM"):
        if required:
            raise DispatchError("BOUNDED_LINUX_RUNNER_REQUIRED")
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def expired(signum, frame):
        raise DispatchError("OPERATION_DEADLINE_EXCEEDED")

    signal.signal(signal.SIGALRM, expired)
    effective = min(seconds, previous_timer[0]) if previous_timer[0] > 0 else seconds
    signal.setitimer(signal.ITIMER_REAL, effective)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            # Nested operations never extend the outer deadline.
            remaining = max(0.000001, previous_timer[0] - (time.monotonic() - started))
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_timer[1])


def bounded(seconds):
    def decorate(function):
        @functools.wraps(function)
        def execute(*args, **kwargs):
            with deadline_guard(seconds):
                return function(*args, **kwargs)
        return execute
    return decorate


@contextlib.contextmanager
def cancellation_guard():
    """Turn ordinary runner signals into the same fail-closed cleanup path.

    SIGKILL, runner loss and network partitions cannot guarantee cancellation;
    the provider-side timeout remains the independent backstop.
    """
    previous = {}

    def interrupted(signum, frame):
        raise DispatchError("RUNNER_INTERRUPTED")

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DispatchError("SOURCE_REDIRECT_REJECTED")


def github_json(path: str) -> dict:
    # The workflow token needs only contents:read and checks:read. Legacy commit
    # statuses are not admission evidence because their origin cannot be bound
    # to the trusted GitHub Actions app id.
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "szl-training-dispatch",
    }
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(urllib.request.Request("https://api.github.com" + path, headers=headers), timeout=20) as response:
            raw = response.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise DispatchError("SOURCE_RESPONSE_OVERSIZED")
        result = parse_json(raw)
        if not isinstance(result, dict):
            raise DispatchError("SOURCE_RESPONSE_INVALID")
        return result
    except DispatchError:
        raise
    except Exception:
        raise DispatchError("SOURCE_READ_FAILED") from None


def verify_source(manifest: dict, worker_bytes: bytes, get=github_json) -> None:
    source = manifest["source"]
    if source["repository"] != REPOSITORY:
        raise DispatchError("WRONG_SOURCE_REPOSITORY")
    if hashlib.sha256(worker_bytes).hexdigest() != source["worker_sha256"]:
        raise DispatchError("LOCAL_WORKER_DIGEST_MISMATCH")
    commit = get(f"/repos/{REPOSITORY}/commits/main")
    if commit.get("sha") != source["revision"]:
        raise DispatchError("STALE_SOURCE_REVISION")
    if commit.get("commit", {}).get("verification", {}).get("verified") is not True:
        raise DispatchError("SOURCE_SIGNATURE_UNVERIFIED")
    blob = get(f"/repos/{REPOSITORY}/contents/{WORKER_PATH}?ref={source['revision']}")
    try:
        if blob.get("encoding") != "base64" or blob.get("type") != "file":
            raise ValueError
        remote = base64.b64decode("".join(blob["content"].splitlines()), validate=True)
    except (KeyError, TypeError, ValueError):
        raise DispatchError("SOURCE_BLOB_INVALID") from None
    if remote != worker_bytes:
        raise DispatchError("PUBLISHED_WORKER_DIGEST_MISMATCH")


def _normalized_check_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _read_exact_sha_check_runs(revision: str, get=github_json) -> list[dict]:
    """Read one bounded, internally consistent snapshot of latest check runs."""
    observed = []
    observed_ids = set()
    total = None
    for page in range(1, MAX_CHECK_RUN_PAGES + 1):
        document = get(
            f"/repos/{REPOSITORY}/commits/{revision}/check-runs"
            f"?filter=latest&per_page={CHECK_RUNS_PER_PAGE}&page={page}"
        )
        if not isinstance(document, dict):
            raise DispatchError("SOURCE_CHECK_RESPONSE_INVALID")
        page_total = document.get("total_count")
        runs = document.get("check_runs")
        if (type(page_total) is not int or page_total < 0
                or page_total > CHECK_RUNS_PER_PAGE * MAX_CHECK_RUN_PAGES
                or not isinstance(runs, list) or len(runs) > CHECK_RUNS_PER_PAGE):
            raise DispatchError("SOURCE_CHECK_RESPONSE_INVALID")
        if total is None:
            total = page_total
        elif page_total != total:
            raise DispatchError("SOURCE_CHECK_SNAPSHOT_CHANGED")
        if len(observed) + len(runs) > total:
            raise DispatchError("SOURCE_CHECK_RESPONSE_INVALID")
        for run in runs:
            if not isinstance(run, dict):
                raise DispatchError("SOURCE_CHECK_RESPONSE_INVALID")
            run_id = run.get("id")
            name = run.get("name")
            if (type(run_id) is not int or run_id <= 0 or run_id in observed_ids
                    or not isinstance(name, str) or not name):
                raise DispatchError("SOURCE_CHECK_RESPONSE_INVALID")
            observed_ids.add(run_id)
            observed.append(run)
        if len(observed) == total:
            return observed
        if not runs:
            raise DispatchError("SOURCE_CHECK_PAGINATION_INCOMPLETE")
    raise DispatchError("SOURCE_CHECK_PAGINATION_INCOMPLETE")


def verify_required_source_checks(manifest: dict, get=github_json) -> None:
    """Require exact-SHA protected checks, successful under the trusted app."""
    revision = manifest["source"]["revision"]
    first = _read_exact_sha_check_runs(revision, get=get)
    second = _read_exact_sha_check_runs(revision, get=get)

    def canonical_snapshot(runs: list[dict]) -> tuple[tuple, ...]:
        snapshot = []
        for run in runs:
            app = run.get("app")
            status = run.get("status")
            conclusion = run.get("conclusion")
            head_sha = run.get("head_sha")
            if (
                not isinstance(app, dict)
                or type(app.get("id")) is not int
                or app["id"] <= 0
                or type(status) is not str
                or (conclusion is not None and type(conclusion) is not str)
                or type(head_sha) is not str
            ):
                raise DispatchError("SOURCE_CHECK_RESPONSE_INVALID")
            snapshot.append(
                (
                    run["id"],
                    run["name"],
                    status,
                    conclusion,
                    head_sha,
                    app["id"],
                )
            )
        return tuple(sorted(snapshot))

    if canonical_snapshot(first) != canonical_snapshot(second):
        raise DispatchError("SOURCE_CHECK_SNAPSHOT_CHANGED")
    expected_by_normalized = {
        _normalized_check_name(name): name for name in REQUIRED_SOURCE_CHECKS
    }
    matches = {name: [] for name in REQUIRED_SOURCE_CHECKS}
    for run in first:
        normalized = _normalized_check_name(run["name"])
        expected = expected_by_normalized.get(normalized)
        if expected is None:
            continue
        if run["name"] != expected:
            raise DispatchError("SOURCE_CHECK_NAME_AMBIGUOUS")
        matches[expected].append(run)
    if any(len(runs) != 1 for runs in matches.values()):
        raise DispatchError("SOURCE_CHECK_MISSING_OR_DUPLICATE")
    for run in (matches[name][0] for name in REQUIRED_SOURCE_CHECKS):
        if run.get("head_sha") != revision:
            raise DispatchError("SOURCE_CHECK_SHA_MISMATCH")
        app = run.get("app")
        if (not isinstance(app, dict)
                or app.get("id") != GITHUB_ACTIONS_APP_ID):
            raise DispatchError("SOURCE_CHECK_APP_UNTRUSTED")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise DispatchError("SOURCE_CHECK_NOT_SUCCESSFUL")


def verify_admitted_source(manifest: dict, worker_bytes: bytes, get=github_json) -> None:
    """Bind source bytes, signature, exact current main and successful checks."""
    verify_source(manifest, worker_bytes, get=get)
    verify_required_source_checks(manifest, get=get)


def job_command(worker_bytes: bytes, expected_sha256: str) -> list[str]:
    """Embed the already source-verified worker, not a mutable remote URL."""
    encoded = base64.b64encode(worker_bytes).decode("ascii")
    bootstrap = (
        "import base64,hashlib,os,runpy,tempfile\n"
        f"b=base64.b64decode({encoded!r},validate=True)\n"
        f"assert hashlib.sha256(b).hexdigest()=={expected_sha256!r}\n"
        "d=tempfile.mkdtemp(prefix='szl-training-')\n"
        "p=os.path.join(d,'receipt_training_worker.py')\n"
        "with open(p,'xb') as f: f.write(b)\n"
        "runpy.run_path(p,run_name='__main__')\n"
    )
    return ["python", "-I", "-B", "-c", bootstrap]


def validate_safetensors_adapter(raw: bytes) -> None:
    """Structurally validate a float LoRA safetensors file without importing it.

    The dispatcher never deserializes tensors. It admits only the documented
    safetensors layout: an eight-byte little-endian JSON-header length followed
    by a duplicate-free header and a fully accounted-for tensor payload.
    """
    if type(raw) is not bytes or len(raw) <= 8:
        raise DispatchError("SAFETENSORS_INVALID")
    header_size = int.from_bytes(raw[:8], "little", signed=False)
    if not 0 < header_size <= MAX_SAFETENSORS_HEADER_BYTES:
        raise DispatchError("SAFETENSORS_HEADER_INVALID")
    payload_start = 8 + header_size
    if payload_start > len(raw):
        raise DispatchError("SAFETENSORS_HEADER_INVALID")
    try:
        header = parse_json(raw[8:payload_start])
    except ValueError:
        raise DispatchError("SAFETENSORS_HEADER_INVALID") from None
    if type(header) is not dict:
        raise DispatchError("SAFETENSORS_HEADER_INVALID")
    metadata = header.get("__metadata__")
    if "__metadata__" in header and (
        type(metadata) is not dict
        or any(type(key) is not str or type(value) is not str
               for key, value in metadata.items())
    ):
        raise DispatchError("SAFETENSORS_METADATA_INVALID")

    payload_size = len(raw) - payload_start
    intervals = []
    for name, tensor in header.items():
        if name == "__metadata__":
            continue
        try:
            name_bytes = name.encode("utf-8")
        except (AttributeError, UnicodeError):
            raise DispatchError("SAFETENSORS_TENSOR_INVALID") from None
        if not name_bytes or len(name_bytes) > 4096 or any(
            ord(character) < 32 or ord(character) == 127 for character in name
        ):
            raise DispatchError("SAFETENSORS_TENSOR_INVALID")
        if type(tensor) is not dict or set(tensor) != {
            "dtype", "shape", "data_offsets"
        }:
            raise DispatchError("SAFETENSORS_TENSOR_INVALID")
        dtype = tensor["dtype"]
        shape = tensor["shape"]
        offsets = tensor["data_offsets"]
        if type(dtype) is not str or dtype not in SAFE_TENSOR_DTYPES:
            raise DispatchError("SAFETENSORS_DTYPE_INVALID")
        if (
            type(shape) is not list
            or len(shape) > 16
            or any(type(dimension) is not int or dimension < 0 for dimension in shape)
            or type(offsets) is not list
            or len(offsets) != 2
            or any(type(offset) is not int for offset in offsets)
        ):
            raise DispatchError("SAFETENSORS_TENSOR_INVALID")
        start, end = offsets
        if not 0 <= start < end <= payload_size:
            raise DispatchError("SAFETENSORS_OFFSET_INVALID")
        elements = 1
        for dimension in shape:
            elements *= dimension
            if elements > payload_size:
                raise DispatchError("SAFETENSORS_SHAPE_INVALID")
        if elements <= 0 or end - start != elements * SAFE_TENSOR_DTYPES[dtype]:
            raise DispatchError("SAFETENSORS_SHAPE_INVALID")
        intervals.append((start, end))
    if not intervals:
        raise DispatchError("SAFETENSORS_TENSOR_REQUIRED")
    # Standard safetensors payloads contain no executable or unexplained bytes.
    # Requiring contiguous coverage rejects unaccounted or trailing payload bytes.
    cursor = 0
    for start, end in sorted(intervals):
        if start != cursor:
            raise DispatchError("SAFETENSORS_OFFSET_INVALID")
        cursor = end
    if cursor != payload_size:
        raise DispatchError("SAFETENSORS_OFFSET_INVALID")


def validate_adapter_config(raw: bytes, manifest: dict) -> None:
    """Bind the published PEFT LoRA configuration to admitted hyperparameters."""
    try:
        config = parse_json(raw)
    except ValueError:
        raise DispatchError("ADAPTER_CONFIG_INVALID") from None
    if type(config) is not dict:
        raise DispatchError("ADAPTER_CONFIG_INVALID")
    hyper = manifest["hyperparameters"]
    if (
        config.get("peft_type") != "LORA"
        or type(config.get("peft_type")) is not str
        or config.get("task_type") != "CAUSAL_LM"
        or type(config.get("task_type")) is not str
        or config.get("bias") != "none"
        or type(config.get("bias")) is not str
        or type(config.get("r")) is not int
        or config["r"] != hyper["r"]
        or type(config.get("lora_alpha")) is not int
        or config["lora_alpha"] != hyper["lora_alpha"]
        or type(config.get("base_model_name_or_path")) is not str
        or config["base_model_name_or_path"] != manifest["base_model"]["repo_id"]
        or type(config.get("revision")) is not str
        or config["revision"] != manifest["base_model"]["revision"]
    ):
        raise DispatchError("ADAPTER_CONFIG_BINDING_MISMATCH")
    dropout = config.get("lora_dropout")
    if (
        type(dropout) not in (int, float)
        or not math.isfinite(dropout)
        or dropout != hyper["lora_dropout"]
    ):
        raise DispatchError("ADAPTER_CONFIG_BINDING_MISMATCH")
    modules = config.get("target_modules")
    admitted_modules = hyper["target_modules"]
    if (
        type(modules) is not list
        or any(type(module) is not str for module in modules)
        or len(modules) != len(set(modules))
        or sorted(modules) != sorted(admitted_modules)
    ):
        raise DispatchError("ADAPTER_CONFIG_BINDING_MISMATCH")


class ReceiptSink:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.sequence = 0

    def emit(self, state: str, manifest: dict | None, **fields) -> dict:
        record = {
            "schema_version": "szl.training.dispatch.v1",
            "state": state,
            "timestamp_unix": time.time(),
            "run_id": manifest.get("run_id") if manifest else None,
            "manifest_sha256": canonical_sha256(manifest) if manifest else None,
            "authority": "OPERATOR_SUPPLIED_UNVERIFIED",
            "promotion": "NOT_GRANTED",
            **fields,
        }
        self.sequence += 1
        path = self.directory / f"{self.sequence:03d}-{state}.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        return record


class HFProvider:
    def __init__(self, token: str):
        from huggingface_hub import HfApi
        self.api = HfApi(endpoint="https://huggingface.co", token=token)
        self.token = token

    @bounded(180)
    def preflight(self, manifest: dict) -> None:
        # The worker schema's .invalid fixture is deliberately parseable for
        # provider-free tests, but no manifest reaches a provider unless its
        # immutable image digest has a source-reviewed runtime approval.
        image = manifest["runtime"]["image"]
        if image == NON_RUNNABLE_TEST_RUNTIME or image not in APPROVED_RUNTIMES:
            raise DispatchError("RUNTIME_NOT_APPROVED_FOR_SUBMISSION")
        for field, kind in (("base_model", "model"), ("dataset", "dataset")):
            spec = manifest[field]
            info = self.api.repo_info(spec["repo_id"], repo_type=kind, revision=spec["revision"])
            if info.sha != spec["revision"]:
                raise DispatchError("INPUT_REVISION_MISMATCH")
        output = manifest["output"]
        if self.api.model_info(output["repo_id"]).sha != output["parent_commit"]:
            raise DispatchError("OUTPUT_PARENT_DRIFT")
        if self.api.file_exists(output["repo_id"], f".training-reservations/{manifest['run_id']}.json", revision=output["parent_commit"]):
            raise DispatchError("RUN_ALREADY_RESERVED")
        # Verify bounded dataset bytes before any billable submission. Semantic
        # row/split validation is repeated independently inside the worker.
        data = {}
        for split in ("train", "eval"):
            dataset = manifest["dataset"]
            data[split] = self.read_file(dataset["repo_id"], dataset["revision"], dataset[f"{split}_file"], dataset["max_file_bytes"], "dataset", dataset[f"{split}_sha256"])
        validate_dataset_records(manifest, data["train"], data["eval"])

    @bounded(60)
    def reserve(self, manifest: dict) -> str:
        from huggingface_hub import CommitOperationAdd
        record = {
            "schema_version": "szl.training.reservation.v1",
            "run_id": manifest["run_id"],
            "manifest_sha256": canonical_sha256(manifest),
            "source_revision": manifest["source"]["revision"],
        }
        raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        result = self.api.create_commit(
            manifest["output"]["repo_id"], repo_type="model",
            operations=[CommitOperationAdd(path_in_repo=f".training-reservations/{manifest['run_id']}.json", path_or_fileobj=raw)],
            parent_commit=manifest["output"]["parent_commit"],
            commit_message=f"Reserve training run {manifest['run_id']}",
        )
        sha = result.oid
        if (not isinstance(sha, str) or not SHA.fullmatch(sha)
                or sha in ("0" * 40, manifest["output"]["parent_commit"])):
            raise DispatchError("RESERVATION_OUTCOME_UNKNOWN")
        observed = self.read_file(manifest["output"]["repo_id"], sha, f".training-reservations/{manifest['run_id']}.json", MAX_JSON)
        if parse_json(observed) != record:
            raise DispatchError("RESERVATION_READBACK_FAILED")
        return sha

    @bounded(60)
    def submit(self, manifest: dict, worker_bytes: bytes, reservation: str) -> str:
        runtime = manifest["runtime"]
        info = self.api.run_job(
            namespace="SZLHOLDINGS", image=runtime["image"],
            command=job_command(worker_bytes, manifest["source"]["worker_sha256"]),
            flavor=runtime["flavor"], timeout=runtime["timeout_seconds"],
            env={"TRAINING_MANIFEST_JSON": json.dumps(manifest, sort_keys=True, allow_nan=False),
                 "TRAINING_SOURCE_REVISION": manifest["source"]["revision"],
                 "TRAINING_RESERVATION_COMMIT": reservation},
            secrets={"HF_TOKEN": self.token},
        )
        if not isinstance(info.id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,128}", info.id):
            raise DispatchError("SUBMISSION_OUTCOME_UNKNOWN")
        return info.id

    @bounded(30)
    def output_main_head(self, manifest: dict) -> str:
        """Read the output model's explicit main head for pre-billable CAS."""
        sha = self.api.model_info(
            manifest["output"]["repo_id"], revision="main"
        ).sha
        if (not isinstance(sha, str) or not SHA.fullmatch(sha)
                or sha == "0" * 40):
            raise DispatchError("OUTPUT_HEAD_READ_INVALID")
        return sha

    @bounded(30)
    def status(self, job_id: str) -> str:
        return self.api.inspect_job(job_id=job_id, namespace="SZLHOLDINGS").status.stage

    @bounded(30)
    def cancel(self, job_id: str) -> None:
        self.api.cancel_job(job_id=job_id, namespace="SZLHOLDINGS")

    @bounded(60)
    def result(self, job_id: str) -> dict:
        found = []
        total = 0
        for count, entry in enumerate(self.api.fetch_job_logs(job_id=job_id, namespace="SZLHOLDINGS")):
            line = entry if isinstance(entry, str) else getattr(entry, "data", None)
            if not isinstance(line, str):
                raise DispatchError("JOB_LOG_FORMAT_INVALID")
            total += len(line.encode("utf-8"))
            if count >= 10000 or total > MAX_LOG_BYTES:
                raise DispatchError("JOB_LOG_LIMIT_EXCEEDED")
            for item in line.splitlines():
                if item.startswith(RESULT_PREFIX):
                    found.append(parse_json(item[len(RESULT_PREFIX):]))
        if len(found) != 1 or not isinstance(found[0], dict):
            raise DispatchError("WORKER_RESULT_MISSING_OR_DUPLICATE")
        return found[0]

    @bounded(180)
    def verify_candidate_tree_delta(
        self,
        manifest: dict,
        reservation: str,
        candidate: str,
        artifact_paths: set[str],
    ) -> None:
        """Prove a bounded content delta without claiming commit ancestry.

        huggingface_hub 0.36.2 exposes immutable tree entries but not candidate
        commit-parent metadata. The worker's parent_commit CAS and this exact
        full-tree closure are independent evidence; neither is described as a
        direct-parent proof.
        """
        from huggingface_hub.hf_api import BlobLfsInfo, RepoFile, RepoFolder

        repo = manifest["output"]["repo_id"]
        head = self.api.model_info(repo, revision="main").sha
        if head != candidate:
            raise DispatchError("CANDIDATE_NOT_CURRENT_MAIN")

        def safe_path(value) -> tuple[str, int]:
            if type(value) is not str or not value or "\\" in value:
                raise DispatchError("REPO_TREE_PATH_INVALID")
            try:
                encoded = value.encode("utf-8")
            except UnicodeError:
                raise DispatchError("REPO_TREE_PATH_INVALID") from None
            path = PurePosixPath(value)
            if (
                len(encoded) > MAX_REPO_PATH_BYTES
                or path.is_absolute()
                or str(path) != value
                or value.endswith("/")
                or any(part in ("", ".", "..") for part in path.parts)
                or any(ord(character) < 32 or ord(character) == 127
                       for character in value)
            ):
                raise DispatchError("REPO_TREE_PATH_INVALID")
            return value, len(encoded)

        def oid(value, code):
            if (
                type(value) is not str
                or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None
                or set(value) == {"0"}
            ):
                raise DispatchError(code)
            return value

        def snapshot(revision: str) -> tuple[dict[str, tuple], set[str]]:
            files = {}
            seen_paths = set()
            path_bytes = 0
            entries = self.api.list_repo_tree(
                repo,
                repo_type="model",
                revision=revision,
                recursive=True,
                expand=False,
                token=self.token,
            )
            for index, entry in enumerate(entries, start=1):
                if index > MAX_REPO_TREE_ENTRIES:
                    raise DispatchError("REPO_TREE_ENTRY_LIMIT_EXCEEDED")
                if type(entry) not in (RepoFile, RepoFolder):
                    raise DispatchError("REPO_TREE_ENTRY_INVALID")
                path, encoded_size = safe_path(entry.path)
                path_bytes += encoded_size
                if path_bytes > MAX_REPO_TREE_PATH_BYTES:
                    raise DispatchError("REPO_TREE_PATH_LIMIT_EXCEEDED")
                if path in seen_paths:
                    raise DispatchError("REPO_TREE_DUPLICATE_PATH")
                seen_paths.add(path)
                if type(entry) is RepoFolder:
                    oid(entry.tree_id, "REPO_TREE_FOLDER_INVALID")
                    continue
                if type(entry.size) is not int or not 0 <= entry.size < 2**63:
                    raise DispatchError("REPO_TREE_FILE_INVALID")
                blob_id = oid(entry.blob_id, "REPO_TREE_FILE_INVALID")
                lfs_sha = None
                lfs_size = None
                if entry.lfs is not None:
                    if (
                        type(entry.lfs) is not BlobLfsInfo
                        or type(entry.lfs.size) is not int
                        or not 0 <= entry.lfs.size < 2**63
                        or type(entry.lfs.pointer_size) is not int
                        or entry.lfs.pointer_size <= 0
                    ):
                        raise DispatchError("REPO_TREE_LFS_INVALID")
                    lfs_sha = oid(entry.lfs.sha256, "REPO_TREE_LFS_INVALID")
                    if len(lfs_sha) != 64:
                        raise DispatchError("REPO_TREE_LFS_INVALID")
                    lfs_size = entry.lfs.size
                files[path] = (path, entry.size, blob_id, lfs_sha, lfs_size)
            return files, seen_paths

        reservation_files, reservation_paths = snapshot(reservation)
        candidate_files, _ = snapshot(candidate)
        if self.api.model_info(repo, revision="main").sha != candidate:
            raise DispatchError("CANDIDATE_NOT_CURRENT_MAIN")
        prefix = f"candidates/{manifest['run_id']}/"
        if any(path == prefix[:-1] or path.startswith(prefix)
               for path in reservation_paths):
            raise DispatchError("CANDIDATE_PREFIX_ALREADY_PRESENT")
        for path, identity in reservation_files.items():
            if candidate_files.get(path) != identity:
                raise DispatchError("RESERVATION_TREE_CHANGED")
        expected_additions = {
            prefix + path for path in artifact_paths | {"artifacts.json", "receipt.json"}
        }
        if set(candidate_files) - set(reservation_files) != expected_additions:
            raise DispatchError("CANDIDATE_TREE_DELTA_INVALID")

    @bounded(180)
    def read_file(self, repo: str, revision: str, path: str, maximum: int, kind="model", expected_sha256=None) -> bytes:
        from huggingface_hub import hf_hub_download
        infos = self.api.get_paths_info(repo, [path], repo_type=kind, revision=revision)
        if len(infos) != 1 or type(infos[0].size) is not int or not 0 < infos[0].size <= maximum:
            raise DispatchError("ARTIFACT_SIZE_OR_PATH_INVALID")
        local = hf_hub_download(repo, path, repo_type=kind, revision=revision, endpoint="https://huggingface.co", token=self.token)
        with open(local, "rb") as stream:
            raw = stream.read(maximum + 1)
        if len(raw) != infos[0].size or len(raw) > maximum:
            raise DispatchError("ARTIFACT_SIZE_MISMATCH")
        if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise DispatchError("ARTIFACT_DIGEST_MISMATCH")
        return raw


def verify_candidate(manifest: dict, reservation: str, result: dict, provider) -> dict:
    expected = {
        "schema_version": "szl.training.worker-result.v1", "status": "CANDIDATE_PUBLISHED",
        "run_id": manifest["run_id"], "manifest_sha256": canonical_sha256(manifest),
        "output_repo": manifest["output"]["repo_id"],
        "receipt_path": f"candidates/{manifest['run_id']}/receipt.json",
    }
    if any(result.get(k) != value for k, value in expected.items()):
        raise DispatchError("WORKER_RESULT_BINDING_MISMATCH")
    commit = result.get("commit")
    if (not isinstance(commit, str) or not SHA.fullmatch(commit)
            or commit in ("0" * 40, reservation, manifest["output"]["parent_commit"])):
        raise DispatchError("IMMUTABLE_OUTPUT_COMMIT_REQUIRED")
    digest = result.get("receipt_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise DispatchError("RECEIPT_DIGEST_REQUIRED")
    repo = expected["output_repo"]
    receipt = parse_json(provider.read_file(repo, commit, expected["receipt_path"], MAX_JSON, expected_sha256=digest))
    if (receipt.get("schema_version") != "szl.training.receipt.v1"
            or receipt.get("status") != "CANDIDATE_EVALUATED"
            or receipt.get("run_id") != manifest["run_id"]
            or receipt.get("manifest_sha256") != canonical_sha256(manifest)
            or receipt.get("source") != manifest["source"]
            or receipt.get("profile") != manifest["profile"]
            or receipt.get("authority") != "OPERATOR_SUPPLIED_UNVERIFIED"
            or receipt.get("promotion") != "NOT_GRANTED"):
        raise DispatchError("RECEIPT_BINDING_MISMATCH")
    output = receipt.get("output", {})
    prefix = f"candidates/{manifest['run_id']}/"
    if output != {"repo_id": repo, "parent_commit": manifest["output"]["parent_commit"], "reservation_commit": reservation, "prefix": prefix}:
        raise DispatchError("RECEIPT_OUTPUT_MISMATCH")
    eval_record = receipt.get("evaluation", {})
    for key in ("train_loss", "eval_loss", "max_eval_loss"):
        value = eval_record.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise DispatchError("INVALID_EVALUATION_METRIC")
    if (eval_record.get("passed") is not True or eval_record["max_eval_loss"] != manifest["evaluation"]["max_eval_loss"]
            or eval_record["eval_loss"] > eval_record["max_eval_loss"]):
        raise DispatchError("EVALUATION_GATE_FAILED")
    artifacts_digest = receipt.get("artifacts_sha256")
    if not isinstance(artifacts_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", artifacts_digest):
        raise DispatchError("ARTIFACT_MANIFEST_DIGEST_REQUIRED")
    artifacts_raw = provider.read_file(repo, commit, prefix + "artifacts.json", MAX_JSON, expected_sha256=artifacts_digest)
    artifacts = parse_json(artifacts_raw)
    # The worker's artifact list is verified independently, not trusted because
    # the job status says COMPLETED. Receipt/manifest shapes are checked below.
    entries = artifacts.get("files")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise DispatchError("ARTIFACT_MANIFEST_INVALID")
    paths = set()
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if (not isinstance(path, str) or path not in ARTIFACT_NAMES | {"manifest.json", "evaluation.json"}
                or path in paths):
            raise DispatchError("ARTIFACT_PATH_INVALID")
        paths.add(path)
        size, sha = entry.get("size_bytes"), entry.get("sha256")
        if type(size) is not int or not 0 < size <= MAX_ARTIFACT_BYTES or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise DispatchError("ARTIFACT_ENTRY_INVALID")
        raw = provider.read_file(repo, commit, prefix + path, size, expected_sha256=sha)
        if len(raw) != size:
            raise DispatchError("ARTIFACT_SIZE_MISMATCH")
        if path == "manifest.json" and canonical_sha256(parse_json(raw)) != canonical_sha256(manifest):
            raise DispatchError("PUBLISHED_MANIFEST_MISMATCH")
        if path == "evaluation.json" and canonical_sha256(parse_json(raw)) != canonical_sha256(eval_record):
            raise DispatchError("PUBLISHED_EVALUATION_MISMATCH")
        if path == "adapter_model.safetensors":
            validate_safetensors_adapter(raw)
        if path == "adapter_config.json":
            validate_adapter_config(raw, manifest)
    if not {"adapter_model.safetensors", "adapter_config.json", "manifest.json", "evaluation.json"} <= paths:
        raise DispatchError("REQUIRED_ARTIFACTS_MISSING")
    provider.verify_candidate_tree_delta(manifest, reservation, commit, paths)
    return {"commit": commit, "receipt_sha256": digest, "artifact_count": len(paths)}


def dispatch(manifest: dict, worker_bytes: bytes, provider, sink, *, source_check=verify_admitted_source, clock=time.monotonic, sleep=time.sleep) -> dict:
    manifest = validate_manifest(manifest)
    source_check(manifest, worker_bytes)
    provider.preflight(manifest)
    sink.emit("RESERVATION_INTENT", manifest)
    try:
        reservation = provider.reserve(manifest)
    except Exception:
        sink.emit("RESERVATION_OUTCOME_UNKNOWN", manifest, automatic_retry=False)
        raise DispatchError("RESERVATION_OUTCOME_UNKNOWN") from None
    sink.emit("RESERVED", manifest, reservation_commit=reservation)
    # Recheck source/check evidence and output CAS immediately before the
    # billable operation. Any uncertainty consumes the reservation and requires
    # an explicitly reviewed fresh run; it never reaches a submit call.
    try:
        source_check(manifest, worker_bytes)
        if provider.output_main_head(manifest) != reservation:
            raise DispatchError("OUTPUT_HEAD_NOT_RESERVATION")
    except Exception:
        try:
            sink.emit(
                "PRE_SUBMISSION_ADMISSION_FAILED",
                manifest,
                reservation_commit=reservation,
                automatic_retry=False,
            )
        except Exception:
            pass
        raise DispatchError("PRE_SUBMISSION_ADMISSION_FAILED") from None
    sink.emit("SUBMISSION_INTENT", manifest, reservation_commit=reservation)
    try:
        job_id = provider.submit(manifest, worker_bytes, reservation)
    except Exception:
        sink.emit("SUBMISSION_OUTCOME_UNKNOWN", manifest, reservation_commit=reservation, automatic_retry=False)
        raise DispatchError("SUBMISSION_OUTCOME_UNKNOWN") from None
    try:
        sink.emit("SUBMITTED", manifest, job_id=job_id, reservation_commit=reservation)
        deadline = clock() + manifest["runtime"]["timeout_seconds"] + 120
        while True:
            if clock() >= deadline:
                raise DispatchError("MONITOR_TIMEOUT")
            state = provider.status(job_id)
            if state == "COMPLETED":
                break
            if state in {"ERROR", "CANCELED", "CANCELLED", "DELETED"}:
                raise DispatchError("JOB_TERMINAL_FAILURE")
            if state not in {"RUNNING", "STARTING", "SCHEDULING", "PENDING"}:
                raise DispatchError("JOB_STATE_UNKNOWN")
            sleep(min(15, max(0, deadline - clock())))
        observed = verify_candidate(manifest, reservation, provider.result(job_id), provider)
        return sink.emit("CANDIDATE_VERIFIED", manifest, job_id=job_id, reservation_commit=reservation, **observed)
    except Exception:
        cancellation = "UNCONFIRMED"
        try:
            provider.cancel(job_id)
            cancellation = "REQUESTED"
        except Exception:
            pass
        try:
            sink.emit("FAILED_OR_UNKNOWN", manifest, job_id=job_id, reservation_commit=reservation, cancellation=cancellation, automatic_retry=False)
        except Exception:
            # The provider cancellation attempt must happen even when local
            # storage is unavailable. Never retry a submission from this state.
            pass
        raise DispatchError("TRAINING_NOT_VERIFIED") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-env", default="INPUT_TRAINING_MANIFEST")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--receipt-dir", type=Path, default=Path("training-receipts"))
    args = parser.parse_args()
    manifest = None
    sink = None
    try:
        sink = ReceiptSink(args.receipt_dir)
        if args.manifest:
            with args.manifest.open("rb") as stream:
                raw = stream.read(32769)
        else:
            raw = os.environ.get(args.manifest_env, "").encode()
        if not raw or len(raw) > 32768:
            raise DispatchError("MANIFEST_ABSENT_OR_OVERSIZED")
        manifest = validate_manifest(parse_json(raw))
        if not args.submit:
            sink.emit("VALIDATED_NOT_SUBMITTED", manifest)
            print("VALIDATED_NOT_SUBMITTED")
            return 0
        required = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REF": "refs/heads/main"}
        if any(os.environ.get(k) != v for k, v in required.items()) or os.environ.get("GITHUB_SHA") != manifest["source"]["revision"]:
            raise DispatchError("EXACT_MAIN_DISPATCH_REQUIRED")
        if os.environ.get("INPUT_PROFILE") != manifest["profile"]:
            raise DispatchError("PROFILE_MISMATCH")
        token = os.environ.get("HF_TOKEN")
        if not token:
            raise DispatchError("HF_TOKEN_REQUIRED")
        worker_path = Path(__file__).with_name("receipt_training_worker.py")
        if worker_path.is_symlink():
            raise DispatchError("WORKER_SYMLINK_REJECTED")
        with cancellation_guard(), deadline_guard(manifest["runtime"]["timeout_seconds"] + 600, required=True):
            result = dispatch(manifest, worker_path.read_bytes(), HFProvider(token), sink)
        print(json.dumps({k: result[k] for k in ("state", "run_id", "job_id", "commit", "promotion")}, sort_keys=True))
        return 0
    except Exception:
        if sink is not None:
            try:
                sink.emit("DISPATCH_FAILED", manifest, detail="Inspect sanitized phase receipts; no automatic retry.")
            except Exception:
                pass
        print("DISPATCH_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
