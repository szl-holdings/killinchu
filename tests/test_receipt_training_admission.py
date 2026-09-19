"""Offline, synthetic admission-gate tests; no provider or model operations."""

import copy
from types import SimpleNamespace
from unittest import mock

import pytest

from scripts import dispatch_receipt_training as dispatcher
from tests.test_receipt_training_worker import RESERVATION, WORKER_PATH, make_manifest


def check_run(name, revision, *, run_id, app_id=dispatcher.GITHUB_ACTIONS_APP_ID,
              status="completed", conclusion="success"):
    return {
        "id": run_id,
        "name": name,
        "head_sha": revision,
        "app": {"id": app_id},
        "status": status,
        "conclusion": conclusion,
    }


def check_reader(manifest, changes=None, *, extra=40):
    changes = changes or {}
    runs = []
    for run_id, name in enumerate(sorted(dispatcher.REQUIRED_SOURCE_CHECKS), 1):
        values = changes.get(name, {})
        if values is None:
            continue
        runs.append(
            check_run(
                name,
                manifest["source"]["revision"],
                run_id=run_id,
                **values,
            )
        )
    for index in range(extra):
        runs.append(
            check_run(
                f"unrelated-check-{index}",
                manifest["source"]["revision"],
                run_id=10_000 + index,
            )
        )

    def get(path):
        assert path.startswith(
            f"/repos/{dispatcher.REPOSITORY}/commits/"
            f"{manifest['source']['revision']}/check-runs?"
        )
        page = int(path.rsplit("page=", 1)[1])
        start = (page - 1) * dispatcher.CHECK_RUNS_PER_PAGE
        end = start + dispatcher.CHECK_RUNS_PER_PAGE
        return {
            "total_count": len(runs),
            "check_runs": copy.deepcopy(runs[start:end]),
        }

    return mock.Mock(side_effect=get), runs


def test_required_checks_are_exact_sha_trusted_successes_across_bounded_pages():
    manifest = make_manifest()
    get, runs = check_reader(manifest)
    dispatcher.verify_required_source_checks(manifest, get=get)
    assert len(runs) > dispatcher.CHECK_RUNS_PER_PAGE
    assert get.call_count == 4
    assert all("filter=latest" in call.args[0] for call in get.call_args_list)


@pytest.mark.parametrize(
    "change,code",
    [
        ({"app_id": 99}, "SOURCE_CHECK_APP_UNTRUSTED"),
        (
            {"status": "in_progress", "conclusion": None},
            "SOURCE_CHECK_NOT_SUCCESSFUL",
        ),
        (
            {"status": "completed", "conclusion": "neutral"},
            "SOURCE_CHECK_NOT_SUCCESSFUL",
        ),
        (
            {"status": "completed", "conclusion": "skipped"},
            "SOURCE_CHECK_NOT_SUCCESSFUL",
        ),
        (
            {"status": "completed", "conclusion": "failure"},
            "SOURCE_CHECK_NOT_SUCCESSFUL",
        ),
    ],
)
def test_required_check_rejects_untrusted_pending_or_non_success(change, code):
    manifest = make_manifest()
    target = next(iter(dispatcher.REQUIRED_SOURCE_CHECKS))
    get, _ = check_reader(manifest, {target: change}, extra=0)
    with pytest.raises(dispatcher.DispatchError, match=code):
        dispatcher.verify_required_source_checks(manifest, get=get)


def test_required_check_rejects_wrong_sha_duplicate_missing_and_confusable_name():
    manifest = make_manifest()
    target = next(iter(dispatcher.REQUIRED_SOURCE_CHECKS))

    for mutation, code in (
        ("wrong_sha", "SOURCE_CHECK_SHA_MISMATCH"),
        ("duplicate", "SOURCE_CHECK_MISSING_OR_DUPLICATE"),
        ("missing", "SOURCE_CHECK_MISSING_OR_DUPLICATE"),
        ("confusable", "SOURCE_CHECK_NAME_AMBIGUOUS"),
    ):
        _, runs = check_reader(manifest, extra=0)
        selected = next(run for run in runs if run["name"] == target)
        if mutation == "wrong_sha":
            selected["head_sha"] = "9" * 40
        elif mutation == "duplicate":
            duplicate = copy.deepcopy(selected)
            duplicate["id"] = 99_999
            runs.append(duplicate)
        elif mutation == "missing":
            runs.remove(selected)
        else:
            selected["name"] = "  " + target.upper() + "  "

        def reader(path, current=runs):
            page = int(path.rsplit("page=", 1)[1])
            start = (page - 1) * dispatcher.CHECK_RUNS_PER_PAGE
            end = start + dispatcher.CHECK_RUNS_PER_PAGE
            return {
                "total_count": len(current),
                "check_runs": copy.deepcopy(current[start:end]),
            }

        with pytest.raises(dispatcher.DispatchError, match=code):
            dispatcher.verify_required_source_checks(manifest, get=reader)


@pytest.mark.parametrize(
    "document,code",
    [
        (
            {"total_count": 1001, "check_runs": []},
            "SOURCE_CHECK_RESPONSE_INVALID",
        ),
        (
            {"total_count": 1, "check_runs": []},
            "SOURCE_CHECK_PAGINATION_INCOMPLETE",
        ),
        (
            {"total_count": True, "check_runs": []},
            "SOURCE_CHECK_RESPONSE_INVALID",
        ),
    ],
)
def test_check_pagination_is_bounded_and_incomplete_snapshots_fail(document, code):
    manifest = make_manifest()
    with pytest.raises(dispatcher.DispatchError, match=code):
        dispatcher.verify_required_source_checks(
            manifest, get=lambda path: document
        )


def test_changed_pagination_snapshot_fails_closed():
    manifest = make_manifest()
    first = [
        check_run(
            f"unrelated-{index}",
            manifest["source"]["revision"],
            run_id=index + 1,
        )
        for index in range(dispatcher.CHECK_RUNS_PER_PAGE)
    ]
    documents = [
        {"total_count": 51, "check_runs": first},
        {"total_count": 52, "check_runs": []},
    ]
    with pytest.raises(
        dispatcher.DispatchError, match="SOURCE_CHECK_SNAPSHOT_CHANGED"
    ):
        dispatcher.verify_required_source_checks(
            manifest, get=mock.Mock(side_effect=documents)
        )


def test_equal_count_check_replacement_between_full_reads_fails_closed():
    manifest = make_manifest()
    _, first = check_reader(manifest)
    second = copy.deepcopy(first)
    second[-1]["id"] = 99_999
    second[-1]["name"] = "equal-count-replacement"
    documents = []
    for snapshot in (first, second):
        for start in range(0, len(snapshot), dispatcher.CHECK_RUNS_PER_PAGE):
            documents.append(
                {
                    "total_count": len(snapshot),
                    "check_runs": copy.deepcopy(
                        snapshot[start : start + dispatcher.CHECK_RUNS_PER_PAGE]
                    ),
                }
            )
    with pytest.raises(
        dispatcher.DispatchError, match="SOURCE_CHECK_SNAPSHOT_CHANGED"
    ):
        dispatcher.verify_required_source_checks(
            manifest, get=mock.Mock(side_effect=documents)
        )


def repeated_check_reader(manifest):
    _, checks = check_reader(manifest, extra=0)
    name = "Canonical mixed-source card contract"
    first = next(check for check in checks if check["name"] == name)
    first.update(check_suite={"id": 101}, started_at="2026-09-19T06:00:00Z")
    second = copy.deepcopy(first)
    second.update(id=100_001, check_suite={"id": 102},
                  started_at="2026-09-19T12:00:00Z")
    checks.append(second)
    workflows = {
        suite_id: {
            "id": 200_000 + suite_id,
            "check_suite_id": suite_id,
            "workflow_id": 1234,
            "run_number": suite_id,
            "run_attempt": 1,
            "path": dispatcher.REPEATED_CHECK_WORKFLOWS[name],
            "head_sha": manifest["source"]["revision"],
            "head_branch": "main",
            "event": "schedule",
            "repository": {"full_name": dispatcher.REPOSITORY},
        }
        for suite_id in (101, 102)
    }

    def get(path):
        if "/actions/runs?" in path:
            suite_id = int(path.split("check_suite_id=")[1].split("&")[0])
            return {"total_count": 1, "workflow_runs": [copy.deepcopy(workflows[suite_id])]}
        assert "/check-runs?filter=latest&" in path
        page = int(path.rsplit("page=", 1)[1])
        start = (page - 1) * dispatcher.CHECK_RUNS_PER_PAGE
        return {"total_count": len(checks), "check_runs": copy.deepcopy(
            checks[start:start + dispatcher.CHECK_RUNS_PER_PAGE])}

    return mock.Mock(side_effect=get), checks, workflows, first, second


def test_repeated_scheduled_contract_selects_newer_success_after_older_failure():
    manifest = make_manifest()
    get, checks, _, older, _ = repeated_check_reader(manifest)
    older["conclusion"] = "failure"
    checks.reverse()  # Provider order does not select the winning execution.
    dispatcher.verify_required_source_checks(manifest, get=get)
    assert sum("/check-runs?" in c.args[0] for c in get.call_args_list) == 3
    assert sum("/actions/runs?" in c.args[0] for c in get.call_args_list) == 4


@pytest.mark.parametrize("status,conclusion", [
    ("queued", None), ("in_progress", None), ("completed", "failure"),
    ("completed", "cancelled"), ("completed", "skipped"), ("completed", "neutral"),
])
def test_newer_repeat_cannot_hide_behind_an_older_success(status, conclusion):
    manifest = make_manifest()
    get, _, _, _, newer = repeated_check_reader(manifest)
    newer.update(status=status, conclusion=conclusion)
    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_NOT_SUCCESSFUL"):
        dispatcher.verify_required_source_checks(manifest, get=get)


def test_late_retry_of_older_workflow_number_is_the_newest_invocation():
    manifest = make_manifest()
    get, _, workflows, older, _ = repeated_check_reader(manifest)
    older.update(started_at="2026-09-19T18:00:00Z", conclusion="failure")
    workflows[101]["run_attempt"] = 2
    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_NOT_SUCCESSFUL"):
        dispatcher.verify_required_source_checks(manifest, get=get)


def test_same_second_failure_cannot_be_masked_by_larger_successful_id():
    manifest = make_manifest()
    get, _, _, older, newer = repeated_check_reader(manifest)
    older.update(started_at=newer["started_at"], conclusion="failure")
    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_NOT_SUCCESSFUL"):
        dispatcher.verify_required_source_checks(manifest, get=get)


@pytest.mark.parametrize("change", [
    {"path": ".github/workflows/untrusted.yml"}, {"workflow_id": 999},
    {"head_sha": "9" * 40}, {"head_branch": "feature"},
    {"event": "pull_request"}, {"check_suite_id": 999},
    {"repository": {"full_name": "other/repository"}},
    {"run_number": True}, {"run_attempt": 0}, {"id": -1},
])
def test_repeat_requires_one_bound_main_workflow_identity(change):
    manifest = make_manifest()
    get, _, workflows, _, _ = repeated_check_reader(manifest)
    workflows[102].update(change)
    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_WORKFLOW_UNVERIFIED"):
        dispatcher.verify_required_source_checks(manifest, get=get)


@pytest.mark.parametrize("value", [None, "yesterday", "2026-02-30T12:00:00Z"])
def test_repeat_timestamp_uncertainty_fails_closed(value):
    manifest = make_manifest()
    get, _, _, _, newer = repeated_check_reader(manifest)
    newer["started_at"] = value
    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_INVOCATION_INVALID"):
        dispatcher.verify_required_source_checks(manifest, get=get)


def test_repeat_metadata_readback_movement_fails_closed():
    manifest = make_manifest()
    original, _, workflows, _, _ = repeated_check_reader(manifest)
    reads = 0

    def get(path):
        nonlocal reads
        if "/actions/runs?" in path:
            reads += 1
            if reads == 3:
                workflows[101]["run_attempt"] = 2
        return original(path)

    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_SNAPSHOT_CHANGED"):
        dispatcher.verify_required_source_checks(manifest, get=get)


def test_repeat_final_check_snapshot_detects_a_new_attempt_during_metadata_reads():
    manifest = make_manifest()
    original, _, _, _, newer = repeated_check_reader(manifest)

    def get(path):
        result = original(path)
        if "/actions/runs?" in path:
            newer["status"] = "in_progress"
            newer["conclusion"] = None
        return result

    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_SNAPSHOT_CHANGED"):
        dispatcher.verify_required_source_checks(manifest, get=get)


def test_non_allowlisted_required_name_still_rejects_duplicates():
    manifest = make_manifest()
    get, checks = check_reader(manifest, extra=0)
    duplicate = copy.deepcopy(next(check for check in checks if check["name"] == "offline-contract"))
    duplicate["id"] = 100_001
    checks.append(duplicate)
    with pytest.raises(dispatcher.DispatchError, match="SOURCE_CHECK_MISSING_OR_DUPLICATE"):
        dispatcher.verify_required_source_checks(manifest, get=get)


class AdmissionSink:
    def __init__(self):
        self.records = []

    def emit(self, state, manifest, **fields):
        record = {"state": state, **fields}
        self.records.append(record)
        return record


class AdmissionProvider:
    def __init__(self, *, head=RESERVATION, head_error=False):
        self.head = head
        self.head_error = head_error
        self.events = []

    def preflight(self, manifest):
        self.events.append("preflight")

    def reserve(self, manifest):
        self.events.append("reserve")
        return RESERVATION

    def output_main_head(self, manifest):
        self.events.append("output_main_head")
        if self.head_error:
            raise RuntimeError("PRIVATE PROVIDER DETAIL")
        return self.head

    def submit(self, manifest, worker_bytes, reservation):
        self.events.append("submit")
        raise AssertionError("submission must remain unreachable in this test")


@pytest.mark.parametrize(
    "head,head_error", [("9" * 40, False), (RESERVATION, True)]
)
def test_output_head_drift_or_read_uncertainty_consumes_claim_and_submits_zero(
    head, head_error
):
    manifest = make_manifest()
    provider = AdmissionProvider(head=head, head_error=head_error)
    sink = AdmissionSink()
    source = mock.Mock()
    with pytest.raises(
        dispatcher.DispatchError, match="PRE_SUBMISSION_ADMISSION_FAILED"
    ) as error:
        dispatcher.dispatch(
            manifest,
            WORKER_PATH.read_bytes(),
            provider,
            sink,
            source_check=source,
        )
    assert source.call_count == 2
    assert provider.events == ["preflight", "reserve", "output_main_head"]
    assert all(record["state"] != "SUBMISSION_INTENT" for record in sink.records)
    assert sink.records[-1] == {
        "state": "PRE_SUBMISSION_ADMISSION_FAILED",
        "reservation_commit": RESERVATION,
        "automatic_retry": False,
    }
    assert "PRIVATE" not in str(error.value) + repr(sink.records)


def test_second_exact_source_check_failure_submits_zero_and_is_sanitized():
    manifest = make_manifest()
    provider = AdmissionProvider()
    sink = AdmissionSink()
    source = mock.Mock(
        side_effect=[
            None,
            dispatcher.DispatchError("SOURCE_CHECK_NOT_SUCCESSFUL"),
        ]
    )
    with pytest.raises(
        dispatcher.DispatchError, match="PRE_SUBMISSION_ADMISSION_FAILED"
    ):
        dispatcher.dispatch(
            manifest,
            WORKER_PATH.read_bytes(),
            provider,
            sink,
            source_check=source,
        )
    assert provider.events == ["preflight", "reserve"]
    assert sink.records[-1]["state"] == "PRE_SUBMISSION_ADMISSION_FAILED"
    assert sink.records[-1]["automatic_retry"] is False


def test_real_provider_output_head_read_is_explicit_main_and_validated():
    manifest = make_manifest()
    provider = dispatcher.HFProvider.__new__(dispatcher.HFProvider)
    provider.api = mock.Mock()
    provider.api.model_info.return_value = SimpleNamespace(sha=RESERVATION)
    assert provider.output_main_head(manifest) == RESERVATION
    assert provider.api.model_info.call_args.kwargs == {"revision": "main"}
    assert provider.api.model_info.call_args.args == (
        manifest["output"]["repo_id"],
    )
    provider.api.model_info.return_value = SimpleNamespace(sha="main")
    with pytest.raises(
        dispatcher.DispatchError, match="OUTPUT_HEAD_READ_INVALID"
    ):
        provider.output_main_head(manifest)


@pytest.mark.parametrize(
    "image",
    [
        dispatcher.NON_RUNNABLE_TEST_RUNTIME,
        "example.invalid/unreviewed@sha256:" + "7" * 64,
    ],
)
def test_unapproved_runtime_is_rejected_before_any_provider_read(image):
    manifest = make_manifest()
    manifest["runtime"]["image"] = image
    provider = dispatcher.HFProvider.__new__(dispatcher.HFProvider)
    provider.api = mock.Mock()
    with pytest.raises(
        dispatcher.DispatchError, match="RUNTIME_NOT_APPROVED_FOR_SUBMISSION"
    ):
        provider.preflight(manifest)
    provider.api.assert_not_called()
