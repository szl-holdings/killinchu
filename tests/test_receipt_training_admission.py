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
