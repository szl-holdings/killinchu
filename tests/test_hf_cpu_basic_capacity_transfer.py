from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.hf_cpu_basic_capacity_transfer import (
    CONFIRMATION,
    SOURCE_SPACE,
    TARGET_SPACE,
    execute_transfer,
)


@dataclass(frozen=True)
class Runtime:
    stage: str
    hardware: str | None
    requested_hardware: str | None


class QuotaError(RuntimeError):
    pass


class FakeApi:
    def __init__(
        self,
        *,
        source_states: list[Runtime],
        target_states: list[Runtime],
        target_restart_error: Exception | None = None,
        source_restart_error: Exception | None = None,
    ) -> None:
        self._states = {
            SOURCE_SPACE: list(source_states),
            TARGET_SPACE: list(target_states),
        }
        self.target_restart_error = target_restart_error
        self.source_restart_error = source_restart_error
        self.calls: list[tuple[str, str]] = []

    def get_space_runtime(self, *, repo_id: str) -> Runtime:
        self.calls.append(("get", repo_id))
        states = self._states[repo_id]
        if len(states) > 1:
            return states.pop(0)
        return states[0]

    def pause_space(self, *, repo_id: str) -> None:
        self.calls.append(("pause", repo_id))

    def restart_space(self, *, repo_id: str) -> None:
        self.calls.append(("restart", repo_id))
        if repo_id == TARGET_SPACE and self.target_restart_error is not None:
            raise self.target_restart_error
        if repo_id == SOURCE_SPACE and self.source_restart_error is not None:
            raise self.source_restart_error


def _runtime(
    stage: str,
    *,
    hardware: str | None = "cpu-basic",
    requested_hardware: str | None = "cpu-basic",
) -> Runtime:
    return Runtime(stage, hardware, requested_hardware)


def _run(api: FakeApi, *, token: str = "hf_test_secret") -> dict[str, Any]:
    return execute_transfer(
        token=token,
        confirmation=CONFIRMATION,
        api_factory=lambda supplied_token: api,
        sleep=lambda _: None,
        attempts=2,
        interval_seconds=0,
    )


def test_success_pauses_source_restarts_target_and_verifies_both() -> None:
    api = FakeApi(
        source_states=[_runtime("RUNNING"), _runtime("PAUSED"), _runtime("PAUSED")],
        target_states=[_runtime("PAUSED"), _runtime("BUILDING"), _runtime("RUNNING")],
    )

    evidence = _run(api)

    assert evidence["result"] == "SUCCEEDED"
    assert evidence["final"]["source_runtime"]["stage"] == "PAUSED"
    assert evidence["final"]["target_runtime"]["stage"] == "RUNNING"
    assert evidence["rollback"] == {"attempted": False, "result": "NOT_REQUIRED"}
    assert ("pause", SOURCE_SPACE) in api.calls
    assert ("restart", TARGET_SPACE) in api.calls
    assert ("restart", SOURCE_SPACE) not in api.calls


def test_confirmation_precondition_refuses_before_api_creation() -> None:
    created = False

    def api_factory(_: str) -> FakeApi:
        nonlocal created
        created = True
        raise AssertionError("API client must not be created")

    evidence = execute_transfer(
        token="hf_test_secret",
        confirmation="yes",
        api_factory=api_factory,
        sleep=lambda _: None,
    )

    assert evidence["result"] == "FAILED"
    assert evidence["failure"]["code"] == "CONFIRMATION_MISMATCH"
    assert evidence["preconditions"]["confirmation"] == "REFUSED"
    assert created is False


def test_runtime_precondition_refuses_without_mutation() -> None:
    api = FakeApi(
        source_states=[_runtime("PAUSED")],
        target_states=[_runtime("PAUSED")],
    )

    evidence = _run(api)

    assert evidence["failure"]["code"] == "SOURCE_NOT_RUNNING"
    assert all(action == "get" for action, _ in api.calls)


def test_target_quota_restart_failure_rolls_source_back() -> None:
    api = FakeApi(
        source_states=[_runtime("RUNNING"), _runtime("PAUSED"), _runtime("BUILDING")],
        target_states=[_runtime("PAUSED")],
        target_restart_error=QuotaError("quota exhausted: hf_test_secret"),
    )

    evidence = _run(api)

    assert evidence["failure"] == {
        "code": "TARGET_RESTART_FAILED",
        "exception_type": "QuotaError",
    }
    assert evidence["rollback"]["attempted"] is True
    assert evidence["rollback"]["result"] == "SUCCEEDED"
    assert ("restart", SOURCE_SPACE) in api.calls


def test_target_readback_failure_rolls_source_back() -> None:
    api = FakeApi(
        source_states=[_runtime("RUNNING"), _runtime("PAUSED"), _runtime("RUNNING")],
        target_states=[_runtime("PAUSED"), _runtime("PAUSED"), _runtime("PAUSED")],
    )

    evidence = _run(api)

    assert evidence["failure"]["code"] == "TARGET_RESTART_UNVERIFIED"
    assert evidence["rollback"]["result"] == "SUCCEEDED"


def test_rollback_failure_is_preserved_without_masking_target_failure() -> None:
    api = FakeApi(
        source_states=[_runtime("RUNNING"), _runtime("PAUSED")],
        target_states=[_runtime("PAUSED")],
        target_restart_error=QuotaError("target quota failure"),
        source_restart_error=RuntimeError("source rollback failure"),
    )

    evidence = _run(api)

    assert evidence["failure"]["code"] == "TARGET_RESTART_FAILED"
    assert evidence["rollback"] == {
        "attempted": True,
        "result": "FAILED",
        "exception_type": "RuntimeError",
    }


def test_evidence_never_contains_secret_or_exception_messages() -> None:
    secret = "hf_super_secret_capacity_token"
    api = FakeApi(
        source_states=[_runtime("RUNNING"), _runtime("PAUSED"), _runtime("BUILDING")],
        target_states=[_runtime("PAUSED")],
        target_restart_error=QuotaError(f"Authorization: Bearer {secret}"),
    )

    evidence = _run(api, token=secret)
    serialized = json.dumps(evidence, sort_keys=True)

    assert secret not in serialized
    assert "Authorization" not in serialized
    assert "Bearer" not in serialized
    assert evidence["redaction"]["credential"] == "OMITTED"
    assert evidence["redaction"]["exception_messages"] == "OMITTED"


def test_manual_workflow_is_fixed_scope_locked_and_protected_main_only() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "hf-cpu-basic-capacity-transfer.yml"
    ).read_text(encoding="utf-8")

    for contract in (
        "workflow_dispatch:",
        CONFIRMATION,
        "group: killinchu-hf-cpu-basic-capacity-transfer",
        "cancel-in-progress: false",
        "GITHUB_REF: refs/heads/main",
        "GITHUB_REF_PROTECTED: ${{ github.ref_protected }}",
        "SHARED_PUBLISHER_SHA: 55e935bc9a8d7ff7d5178af341b05f5d075b1f55",
        "SHARED_LOCK_BLOB: 9cc19359ddd5e77556740b66201096b812ef48d9",
        "HF_WRITE_TOKEN: ${{ secrets.HF_WRITE_TOKEN }}",
        "HF_CAPACITY_TRANSFER_CONFIRMATION: ${{ inputs.confirmation }}",
    ):
        assert contract in workflow

    trigger_block = workflow.split("permissions:", 1)[0]
    assert "push:" not in trigger_block
    assert "pull_request:" not in trigger_block
    assert "schedule:" not in trigger_block
    assert "source" not in workflow.split("jobs:", 1)[0]
    assert "target" not in workflow.split("jobs:", 1)[0]

