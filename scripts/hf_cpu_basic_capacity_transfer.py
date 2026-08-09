#!/usr/bin/env python3
"""Governed transfer of one HF cpu-basic slot to the Killinchu Space.

This command intentionally has no repository or hardware arguments. The source,
target, hardware class, confirmation text, polling bounds, and evidence path are
compile-time constants. It is designed for the protected manual workflow and is
also independently unit-testable with an injected Hugging Face API client.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_SPACE = "SZLHOLDINGS/llm-router-live"
TARGET_SPACE = "SZLHOLDINGS/killinchu"
HARDWARE = "cpu-basic"
CONFIRMATION = (
    "TRANSFER CPU-BASIC FROM SZLHOLDINGS/llm-router-live "
    "TO SZLHOLDINGS/killinchu"
)
EVIDENCE_PATH = Path("hf-cpu-basic-capacity-transfer-evidence.json")
POLL_ATTEMPTS = 31
POLL_INTERVAL_SECONDS = 10.0
TARGET_READY_STAGES = frozenset({"BUILDING", "RUNNING"})
SOURCE_ROLLBACK_STAGES = frozenset({"BUILDING", "RUNNING"})


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_exception_type(error: BaseException | None) -> str | None:
    if error is None:
        return None
    # Never persist exception text. HTTP exceptions can contain request headers,
    # response bodies, or credentials. A bounded class name is enough to triage.
    return re.sub(r"[^A-Za-z0-9_.-]", "_", type(error).__name__)[:96]


def _field(runtime: Any, name: str) -> Any:
    if isinstance(runtime, Mapping):
        return runtime.get(name)
    return getattr(runtime, name, None)


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", value)
    rendered = str(enum_value).strip()
    return rendered or None


def _snapshot(runtime: Any) -> dict[str, str | None]:
    stage = _scalar(_field(runtime, "stage"))
    hardware = _scalar(_field(runtime, "hardware"))
    requested_hardware = _scalar(_field(runtime, "requested_hardware"))
    return {
        "stage": stage.upper() if stage is not None else None,
        "hardware": hardware.lower() if hardware is not None else None,
        "requested_hardware": (
            requested_hardware.lower()
            if requested_hardware is not None
            else None
        ),
    }


def _event(
    evidence: dict[str, Any],
    *,
    action: str,
    result: str,
    runtime: dict[str, str | None] | None = None,
    error: BaseException | None = None,
) -> None:
    entry: dict[str, Any] = {"action": action, "result": result}
    if runtime is not None:
        entry["runtime"] = runtime
    exception_type = _safe_exception_type(error)
    if exception_type is not None:
        entry["exception_type"] = exception_type
    evidence["events"].append(entry)


def _fail(
    evidence: dict[str, Any],
    code: str,
    error: BaseException | None = None,
) -> dict[str, Any]:
    evidence["result"] = "FAILED"
    evidence["failure"] = {"code": code}
    exception_type = _safe_exception_type(error)
    if exception_type is not None:
        evidence["failure"]["exception_type"] = exception_type
    evidence["completed_at"] = _utc_now()
    return evidence


def _read_runtime(api: Any, repo_id: str) -> tuple[dict[str, str | None] | None, BaseException | None]:
    try:
        return _snapshot(api.get_space_runtime(repo_id=repo_id)), None
    except Exception as error:  # API failures are evidence, never exception text.
        return None, error


def _poll_runtime(
    api: Any,
    repo_id: str,
    accepted_stages: frozenset[str],
    *,
    sleep: Callable[[float], None],
    attempts: int,
    interval_seconds: float,
) -> tuple[dict[str, str | None] | None, BaseException | None]:
    last_runtime: dict[str, str | None] | None = None
    last_error: BaseException | None = None
    for attempt in range(attempts):
        last_runtime, last_error = _read_runtime(api, repo_id)
        if (
            last_runtime is not None
            and last_runtime.get("stage") in accepted_stages
        ):
            return last_runtime, None
        if attempt + 1 < attempts:
            sleep(interval_seconds)
    return last_runtime, last_error


def _rollback_source(
    api: Any,
    evidence: dict[str, Any],
    *,
    sleep: Callable[[float], None],
    attempts: int,
    interval_seconds: float,
) -> None:
    rollback = evidence["rollback"]
    rollback["attempted"] = True
    try:
        api.restart_space(repo_id=SOURCE_SPACE)
        _event(evidence, action="source_rollback_restart", result="REQUESTED")
    except Exception as error:
        rollback["result"] = "FAILED"
        rollback["exception_type"] = _safe_exception_type(error)
        _event(
            evidence,
            action="source_rollback_restart",
            result="FAILED",
            error=error,
        )
        return

    runtime, error = _poll_runtime(
        api,
        SOURCE_SPACE,
        SOURCE_ROLLBACK_STAGES,
        sleep=sleep,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    rollback["source_runtime"] = runtime
    if runtime is not None and runtime.get("stage") in SOURCE_ROLLBACK_STAGES:
        rollback["result"] = "SUCCEEDED"
        _event(
            evidence,
            action="source_rollback_readback",
            result="VERIFIED",
            runtime=runtime,
        )
        return

    rollback["result"] = "FAILED"
    rollback["exception_type"] = _safe_exception_type(error)
    _event(
        evidence,
        action="source_rollback_readback",
        result="FAILED",
        runtime=runtime,
        error=error,
    )


def execute_transfer(
    *,
    token: str,
    confirmation: str,
    api_factory: Callable[[str], Any],
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = POLL_ATTEMPTS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Execute the fixed transfer and return secret-safe structured evidence."""

    evidence: dict[str, Any] = {
        "schema": "szl.hf-cpu-basic-capacity-transfer/v1",
        "started_at": _utc_now(),
        "completed_at": None,
        "operation": {
            "source_space": SOURCE_SPACE,
            "target_space": TARGET_SPACE,
            "hardware": HARDWARE,
        },
        "redaction": {
            "credential": "OMITTED",
            "exception_messages": "OMITTED",
            "response_bodies": "OMITTED",
        },
        "preconditions": {
            "confirmation": "UNVERIFIED",
            "credential": "UNVERIFIED",
            "source_runtime": None,
            "target_runtime": None,
        },
        "events": [],
        "rollback": {"attempted": False, "result": "NOT_REQUIRED"},
        "final": {"source_runtime": None, "target_runtime": None},
        "result": "IN_PROGRESS",
        "failure": None,
    }

    if confirmation != CONFIRMATION:
        evidence["preconditions"]["confirmation"] = "REFUSED"
        return _fail(evidence, "CONFIRMATION_MISMATCH")
    evidence["preconditions"]["confirmation"] = "MATCHED"

    normalized_token = token.rstrip("\r\n")
    if not normalized_token or "\r" in normalized_token or "\n" in normalized_token:
        evidence["preconditions"]["credential"] = "REFUSED"
        return _fail(evidence, "HF_WRITE_TOKEN_INVALID")
    evidence["preconditions"]["credential"] = "PRESENT"

    if attempts < 1 or interval_seconds < 0:
        return _fail(evidence, "INVALID_POLL_BOUND")

    try:
        api = api_factory(normalized_token)
    except Exception as error:
        return _fail(evidence, "API_CLIENT_INIT_FAILED", error)

    source_initial, source_error = _read_runtime(api, SOURCE_SPACE)
    if source_initial is None:
        return _fail(evidence, "SOURCE_PREFLIGHT_UNAVAILABLE", source_error)
    target_initial, target_error = _read_runtime(api, TARGET_SPACE)
    if target_initial is None:
        return _fail(evidence, "TARGET_PREFLIGHT_UNAVAILABLE", target_error)

    evidence["preconditions"]["source_runtime"] = source_initial
    evidence["preconditions"]["target_runtime"] = target_initial

    if source_initial.get("stage") != "RUNNING":
        return _fail(evidence, "SOURCE_NOT_RUNNING")
    if source_initial.get("hardware") != HARDWARE:
        return _fail(evidence, "SOURCE_NOT_CPU_BASIC")
    if target_initial.get("stage") != "PAUSED":
        return _fail(evidence, "TARGET_NOT_PAUSED")
    if target_initial.get("requested_hardware") != HARDWARE:
        return _fail(evidence, "TARGET_NOT_REQUESTING_CPU_BASIC")

    try:
        api.pause_space(repo_id=SOURCE_SPACE)
        _event(evidence, action="source_pause", result="REQUESTED")
    except Exception as error:
        _event(evidence, action="source_pause", result="FAILED", error=error)
        source_after_error, read_error = _read_runtime(api, SOURCE_SPACE)
        if source_after_error is not None and source_after_error.get("stage") == "PAUSED":
            _rollback_source(
                api,
                evidence,
                sleep=sleep,
                attempts=attempts,
                interval_seconds=interval_seconds,
            )
        return _fail(evidence, "SOURCE_PAUSE_FAILED", error or read_error)

    source_paused, pause_error = _poll_runtime(
        api,
        SOURCE_SPACE,
        frozenset({"PAUSED"}),
        sleep=sleep,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if source_paused is None or source_paused.get("stage") != "PAUSED":
        _event(
            evidence,
            action="source_pause_readback",
            result="FAILED",
            runtime=source_paused,
            error=pause_error,
        )
        _rollback_source(
            api,
            evidence,
            sleep=sleep,
            attempts=attempts,
            interval_seconds=interval_seconds,
        )
        return _fail(evidence, "SOURCE_PAUSE_UNVERIFIED", pause_error)
    _event(
        evidence,
        action="source_pause_readback",
        result="VERIFIED",
        runtime=source_paused,
    )

    try:
        api.restart_space(repo_id=TARGET_SPACE)
        _event(evidence, action="target_restart", result="REQUESTED")
    except Exception as error:
        _event(evidence, action="target_restart", result="FAILED", error=error)
        _rollback_source(
            api,
            evidence,
            sleep=sleep,
            attempts=attempts,
            interval_seconds=interval_seconds,
        )
        return _fail(evidence, "TARGET_RESTART_FAILED", error)

    target_started, target_error = _poll_runtime(
        api,
        TARGET_SPACE,
        TARGET_READY_STAGES,
        sleep=sleep,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if target_started is None or target_started.get("stage") not in TARGET_READY_STAGES:
        _event(
            evidence,
            action="target_restart_readback",
            result="FAILED",
            runtime=target_started,
            error=target_error,
        )
        _rollback_source(
            api,
            evidence,
            sleep=sleep,
            attempts=attempts,
            interval_seconds=interval_seconds,
        )
        return _fail(evidence, "TARGET_RESTART_UNVERIFIED", target_error)
    _event(
        evidence,
        action="target_restart_readback",
        result="VERIFIED",
        runtime=target_started,
    )

    final_source, final_source_error = _read_runtime(api, SOURCE_SPACE)
    final_target, final_target_error = _read_runtime(api, TARGET_SPACE)
    evidence["final"]["source_runtime"] = final_source
    evidence["final"]["target_runtime"] = final_target

    if final_target is None or final_target.get("stage") not in TARGET_READY_STAGES:
        _rollback_source(
            api,
            evidence,
            sleep=sleep,
            attempts=attempts,
            interval_seconds=interval_seconds,
        )
        return _fail(evidence, "FINAL_TARGET_READBACK_FAILED", final_target_error)
    if final_source is None or final_source.get("stage") != "PAUSED":
        return _fail(evidence, "FINAL_SOURCE_READBACK_FAILED", final_source_error)

    evidence["result"] = "SUCCEEDED"
    evidence["completed_at"] = _utc_now()
    return evidence


def _create_hf_api(token: str) -> Any:
    from huggingface_hub import HfApi

    return HfApi(token=token)


def _write_evidence(evidence: dict[str, Any]) -> None:
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        evidence = execute_transfer(
            token=os.environ.get("HF_WRITE_TOKEN", ""),
            confirmation=os.environ.get("HF_CAPACITY_TRANSFER_CONFIRMATION", ""),
            api_factory=_create_hf_api,
        )
    except Exception as error:
        # Preserve a secret-safe artifact even for an unexpected local defect.
        evidence = {
            "schema": "szl.hf-cpu-basic-capacity-transfer/v1",
            "started_at": _utc_now(),
            "completed_at": _utc_now(),
            "operation": {
                "source_space": SOURCE_SPACE,
                "target_space": TARGET_SPACE,
                "hardware": HARDWARE,
            },
            "redaction": {
                "credential": "OMITTED",
                "exception_messages": "OMITTED",
                "response_bodies": "OMITTED",
            },
            "result": "FAILED",
            "failure": {
                "code": "UNEXPECTED_LOCAL_FAILURE",
                "exception_type": _safe_exception_type(error),
            },
        }

    _write_evidence(evidence)
    if evidence.get("result") == "SUCCEEDED":
        print(
            "capacity transfer verified: source=PAUSED "
            "target=BUILDING_OR_RUNNING"
        )
        return 0
    print(
        "capacity transfer failed closed; inspect the redacted evidence artifact",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
