"""Offline dispatcher contracts; synthetic bytes are not trained model evidence."""

import base64
import copy
import hashlib
import json
import socket
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from scripts import dispatch_receipt_training as dispatcher
from scripts.receipt_training_worker import canonical_bytes, canonical_sha256
from tests.test_receipt_training_worker import (
    COMMIT,
    RESERVATION,
    WORKER_PATH,
    make_manifest,
)


PRIVATE_DETAIL = "PRIVATE_PROVIDER_DETAIL_MUST_NOT_LEAK"


def minimal_safetensors_bytes():
    header = canonical_bytes(
        {
            "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": {
                "dtype": "F32",
                "shape": [1],
                "data_offsets": [0, 4],
            }
        }
    )
    return len(header).to_bytes(8, "little") + header + b"\0" * 4


def bound_adapter_config(manifest):
    hyper = manifest["hyperparameters"]
    return canonical_bytes(
        {
            "peft_type": "LORA",
            "task_type": "CAUSAL_LM",
            "bias": "none",
            "r": hyper["r"],
            "lora_alpha": hyper["lora_alpha"],
            "lora_dropout": hyper["lora_dropout"],
            "target_modules": hyper["target_modules"],
            "base_model_name_or_path": manifest["base_model"]["repo_id"],
            "revision": manifest["base_model"]["revision"],
            "inference_mode": True,
        }
    )


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def rejected(*args, **kwargs):
        raise AssertionError("NETWORK_FORBIDDEN_IN_OFFLINE_CONTRACT_TEST")

    monkeypatch.setattr(socket.socket, "connect", rejected)
    monkeypatch.setattr(socket.socket, "connect_ex", rejected)
    monkeypatch.setattr(socket, "create_connection", rejected)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert 0 <= seconds <= 15
        self.sleeps.append(seconds)
        self.now += seconds


class FakeSink:
    def __init__(self, fail_state=None):
        self.records = []
        self.fail_state = fail_state

    def emit(self, state, manifest, **fields):
        if state == self.fail_state:
            self.fail_state = None
            raise OSError(PRIVATE_DETAIL)
        record = {"state": state, "run_id": manifest["run_id"], **fields}
        self.records.append(record)
        return record


class FakeProvider:
    """Exact immutable readback with no Hub client, filesystem, or model execution."""

    def __init__(self, manifest, states=("COMPLETED",)):
        self.manifest = copy.deepcopy(manifest)
        self.states = list(states)
        self.events = []
        self.reads = []
        self.failure = None
        self.cancel_error = False
        self.prefix = f"candidates/{manifest['run_id']}/"
        measured = {
            "train_loss": 1.0,
            "eval_loss": 1.5,
            "max_eval_loss": manifest["evaluation"]["max_eval_loss"],
            "passed": True,
        }
        self.files = {
            "adapter_model.safetensors": minimal_safetensors_bytes(),
            "adapter_config.json": bound_adapter_config(manifest),
            "manifest.json": canonical_bytes(manifest),
            "evaluation.json": canonical_bytes(measured),
        }
        self.receipt = {
            "schema_version": "szl.training.receipt.v1",
            "status": "CANDIDATE_EVALUATED",
            "run_id": manifest["run_id"],
            "profile": manifest["profile"],
            "source": manifest["source"],
            "manifest_sha256": canonical_sha256(manifest),
            "output": {
                **manifest["output"],
                "reservation_commit": RESERVATION,
                "prefix": self.prefix,
            },
            "evaluation": measured,
            "authority": "OPERATOR_SUPPLIED_UNVERIFIED",
            "promotion": "NOT_GRANTED",
        }
        self.result_record = {
            "schema_version": "szl.training.worker-result.v1",
            "status": "CANDIDATE_PUBLISHED",
            "run_id": manifest["run_id"],
            "manifest_sha256": canonical_sha256(manifest),
            "output_repo": manifest["output"]["repo_id"],
            "commit": COMMIT,
            "receipt_path": self.prefix + "receipt.json",
        }
        self.tree_delta_checks = []
        self.rebind_artifacts()

    def rebind_artifacts(self):
        artifacts = {
            "files": [
                {
                    "path": name,
                    "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                for name, raw in sorted(self.files.items())
            ]
        }
        self.artifacts = artifacts
        self.artifacts_raw = canonical_bytes(artifacts)
        self.receipt["artifacts_sha256"] = hashlib.sha256(
            self.artifacts_raw
        ).hexdigest()
        self.rebind_receipt()

    def rebind_receipt(self):
        self.receipt_raw = canonical_bytes(self.receipt)
        self.result_record["receipt_sha256"] = hashlib.sha256(
            self.receipt_raw
        ).hexdigest()

    def event(self, phase):
        self.events.append(phase)
        if self.failure == phase:
            raise RuntimeError(PRIVATE_DETAIL)

    def preflight(self, manifest):
        assert manifest == self.manifest
        self.event("preflight")

    def reserve(self, manifest):
        assert manifest == self.manifest
        self.event("reserve")
        return RESERVATION

    def submit(self, manifest, worker_bytes, reservation):
        assert manifest == self.manifest
        assert reservation == RESERVATION
        assert (
            hashlib.sha256(worker_bytes).hexdigest()
            == manifest["source"]["worker_sha256"]
        )
        self.event("submit")
        return "offline-job-12345"

    def output_main_head(self, manifest):
        assert manifest == self.manifest
        return RESERVATION

    def status(self, job_id):
        assert job_id == "offline-job-12345"
        self.event("status")
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def cancel(self, job_id):
        assert job_id == "offline-job-12345"
        self.event("cancel")
        if self.cancel_error:
            raise RuntimeError(PRIVATE_DETAIL)

    def result(self, job_id):
        assert job_id == "offline-job-12345"
        self.event("result")
        return copy.deepcopy(self.result_record)

    def read_file(
        self, repo, revision, path, maximum, kind="model", expected_sha256=None
    ):
        assert repo == self.manifest["output"]["repo_id"]
        assert revision == COMMIT
        assert kind == "model"
        assert path.startswith(self.prefix)
        self.reads.append((repo, revision, path, maximum, expected_sha256))
        name = path[len(self.prefix) :]
        raw = (
            self.receipt_raw
            if name == "receipt.json"
            else (self.artifacts_raw if name == "artifacts.json" else self.files[name])
        )
        if len(raw) > maximum:
            raise dispatcher.DispatchError("ARTIFACT_SIZE_MISMATCH")
        if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise dispatcher.DispatchError("ARTIFACT_DIGEST_MISMATCH")
        return raw

    def verify_candidate_tree_delta(
        self, manifest, reservation, candidate, artifact_paths
    ):
        assert manifest == self.manifest
        assert reservation == RESERVATION
        assert candidate == COMMIT
        assert artifact_paths == set(self.files)
        self.tree_delta_checks.append(
            (reservation, candidate, frozenset(artifact_paths))
        )


@pytest.fixture
def setup_dispatch():
    manifest = make_manifest()
    provider = FakeProvider(manifest)
    sink = FakeSink()
    clock = FakeClock()
    source = mock.Mock()
    return manifest, provider, sink, clock, source


def run(setup):
    manifest, provider, sink, clock, source = setup
    return dispatcher.dispatch(
        manifest,
        WORKER_PATH.read_bytes(),
        provider,
        sink,
        source_check=source,
        clock=clock,
        sleep=clock.sleep,
    )


def source_reader(manifest, worker_bytes):
    return mock.Mock(
        side_effect=[
            {
                "sha": manifest["source"]["revision"],
                "commit": {"verification": {"verified": True}},
            },
            {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(worker_bytes).decode(),
            },
        ]
    )


def test_source_verification_binds_current_signed_main_and_exact_worker():
    manifest, raw = make_manifest(), WORKER_PATH.read_bytes()
    reader = source_reader(manifest, raw)
    dispatcher.verify_source(manifest, raw, get=reader)
    assert reader.call_count == 2
    assert reader.call_args_list[0].args[0].endswith("/commits/main")
    assert (
        reader.call_args_list[1]
        .args[0]
        .endswith("?ref=" + manifest["source"]["revision"])
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ("stale", "STALE_SOURCE_REVISION"),
        ("signature", "SOURCE_SIGNATURE_UNVERIFIED"),
        ("local", "LOCAL_WORKER_DIGEST_MISMATCH"),
        ("remote", "PUBLISHED_WORKER_DIGEST_MISMATCH"),
        ("invalid_blob", "SOURCE_BLOB_INVALID"),
    ],
)
def test_source_verification_rejects_drift_and_unverified_bytes(change, code):
    manifest, raw = make_manifest(), WORKER_PATH.read_bytes()
    commit = {
        "sha": manifest["source"]["revision"],
        "commit": {"verification": {"verified": True}},
    }
    blob = {
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(raw).decode(),
    }
    if change == "stale":
        commit["sha"] = "9" * 40
    elif change == "signature":
        commit["commit"]["verification"]["verified"] = False
    elif change == "local":
        raw += b"\n# drift\n"
    elif change == "remote":
        blob["content"] = base64.b64encode(b"different worker").decode()
    else:
        blob["content"] = "%%%"
    with pytest.raises(dispatcher.DispatchError, match=code):
        dispatcher.verify_source(
            manifest, raw, get=mock.Mock(side_effect=[commit, blob])
        )


@pytest.mark.parametrize(
    "manifest", [None, {}, [], "", {"schema_version": "szl.training.v1"}]
)
def test_invalid_manifest_never_reaches_source_or_provider(setup_dispatch, manifest):
    _, provider, sink, clock, source = setup_dispatch
    with pytest.raises(ValueError):
        run((manifest, provider, sink, clock, source))
    source.assert_not_called()
    assert provider.events == []
    assert sink.records == []


def test_initial_source_failure_prevents_reservation_and_submission(setup_dispatch):
    _, provider, sink, _, source = setup_dispatch
    source.side_effect = dispatcher.DispatchError("STALE_SOURCE_REVISION")
    with pytest.raises(dispatcher.DispatchError, match="STALE_SOURCE_REVISION"):
        run(setup_dispatch)
    assert provider.events == []
    assert sink.records == []


def test_preflight_failure_prevents_any_mutation(setup_dispatch):
    _, provider, sink, _, _ = setup_dispatch
    provider.failure = "preflight"
    with pytest.raises(RuntimeError):
        run(setup_dispatch)
    assert provider.events == ["preflight"]
    assert sink.records == []


def test_reservation_intent_must_be_durable_before_reservation(setup_dispatch):
    _, provider, sink, _, _ = setup_dispatch
    sink.fail_state = "RESERVATION_INTENT"
    with pytest.raises(OSError):
        run(setup_dispatch)
    assert provider.events == ["preflight"]


@pytest.mark.parametrize(
    "phase,state",
    [
        ("reserve", "RESERVATION_OUTCOME_UNKNOWN"),
        ("submit", "SUBMISSION_OUTCOME_UNKNOWN"),
    ],
)
def test_provider_mutation_uncertainty_is_never_retried(setup_dispatch, phase, state):
    _, provider, sink, _, _ = setup_dispatch
    provider.failure = phase
    with pytest.raises(dispatcher.DispatchError, match=state) as error:
        run(setup_dispatch)
    assert provider.events.count(phase) == 1
    assert provider.events.count("submit") == (phase == "submit")
    assert "status" not in provider.events
    assert sink.records[-1]["state"] == state
    assert sink.records[-1]["automatic_retry"] is False
    assert PRIVATE_DETAIL not in str(error.value) + json.dumps(sink.records)


def test_source_drift_after_reservation_never_submits(setup_dispatch):
    _, provider, sink, _, source = setup_dispatch
    source.side_effect = [None, dispatcher.DispatchError("STALE_SOURCE_REVISION")]
    with pytest.raises(
        dispatcher.DispatchError, match="PRE_SUBMISSION_ADMISSION_FAILED"
    ):
        run(setup_dispatch)
    assert provider.events == ["preflight", "reserve"]
    assert sink.records[-1]["state"] == "PRE_SUBMISSION_ADMISSION_FAILED"
    assert sink.records[-1]["reservation_commit"] == RESERVATION
    assert sink.records[-1]["automatic_retry"] is False


def test_submission_intent_must_be_durable_before_billable_call(setup_dispatch):
    _, provider, sink, _, _ = setup_dispatch
    sink.fail_state = "SUBMISSION_INTENT"
    with pytest.raises(OSError):
        run(setup_dispatch)
    assert provider.events == ["preflight", "reserve"]


def test_submitted_receipt_failure_attempts_cancellation_and_preserves_job_identity(
    setup_dispatch,
):
    _, provider, sink, _, _ = setup_dispatch
    sink.fail_state = "SUBMITTED"
    with pytest.raises(dispatcher.DispatchError):
        run(setup_dispatch)
    assert provider.events.count("submit") == 1
    assert provider.events.count("cancel") == 1
    assert sink.records[-1]["job_id"] == "offline-job-12345"
    assert sink.records[-1]["automatic_retry"] is False


@pytest.mark.parametrize(
    "state", ["ERROR", "CANCELED", "CANCELLED", "DELETED", "ALIEN", "", None]
)
@pytest.mark.parametrize("cancel_error", [False, True])
def test_failure_or_unknown_job_state_never_certifies_candidate(
    setup_dispatch, state, cancel_error
):
    _, provider, sink, _, _ = setup_dispatch
    provider.states = [state]
    provider.cancel_error = cancel_error
    with pytest.raises(
        dispatcher.DispatchError, match="TRAINING_NOT_VERIFIED"
    ) as error:
        run(setup_dispatch)
    assert provider.events.count("reserve") == 1
    assert provider.events.count("submit") == 1
    assert provider.events.count("cancel") == 1
    assert "result" not in provider.events
    assert sink.records[-1]["state"] == "FAILED_OR_UNKNOWN"
    assert sink.records[-1]["cancellation"] == (
        "UNCONFIRMED" if cancel_error else "REQUESTED"
    )
    assert sink.records[-1]["automatic_retry"] is False
    assert PRIVATE_DETAIL not in str(error.value) + json.dumps(sink.records)


def test_monitor_timeout_is_bounded_and_cancellation_is_only_requested(setup_dispatch):
    manifest, provider, sink, clock, _ = setup_dispatch
    provider.states = ["RUNNING"]
    with pytest.raises(dispatcher.DispatchError, match="TRAINING_NOT_VERIFIED"):
        run(setup_dispatch)
    assert clock.now == manifest["runtime"]["timeout_seconds"] + 120
    assert provider.events.count("submit") == 1
    assert provider.events.count("cancel") == 1
    assert sink.records[-1]["cancellation"] == "REQUESTED"
    assert sink.records[-1]["automatic_retry"] is False


@pytest.mark.parametrize("phase", ["status", "result"])
def test_monitor_or_result_read_failure_stays_unknown_and_sanitized(
    setup_dispatch, phase
):
    _, provider, sink, _, _ = setup_dispatch
    provider.failure = phase
    with pytest.raises(
        dispatcher.DispatchError, match="TRAINING_NOT_VERIFIED"
    ) as error:
        run(setup_dispatch)
    assert provider.events.count("cancel") == 1
    assert PRIVATE_DETAIL not in str(error.value) + json.dumps(sink.records)


def test_success_requires_one_submission_and_independent_immutable_hash_readback(
    setup_dispatch,
):
    manifest, provider, sink, clock, source = setup_dispatch
    provider.states = ["PENDING", "SCHEDULING", "STARTING", "RUNNING", "COMPLETED"]
    result = run(setup_dispatch)
    assert result["state"] == "CANDIDATE_VERIFIED"
    assert result["commit"] == COMMIT
    assert result["artifact_count"] == 4
    assert source.call_count == 2
    assert provider.events.count("reserve") == 1
    assert provider.events.count("submit") == 1
    assert "cancel" not in provider.events
    assert clock.sleeps == [15] * 4
    assert len(provider.reads) == 6
    assert len(provider.tree_delta_checks) == 1
    assert {row[1] for row in provider.reads} == {COMMIT}
    assert {row[0] for row in provider.reads} == {manifest["output"]["repo_id"]}
    assert all(isinstance(row[4], str) and len(row[4]) == 64 for row in provider.reads)
    assert [row["state"] for row in sink.records] == [
        "RESERVATION_INTENT",
        "RESERVED",
        "SUBMISSION_INTENT",
        "SUBMITTED",
        "CANDIDATE_VERIFIED",
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "COMPLETED"),
        ("output_repo", "SZLHOLDINGS/wrong-output"),
        ("manifest_sha256", "9" * 64),
        ("run_id", "wrong-run"),
        ("receipt_path", "receipt.json"),
        ("commit", "main"),
        ("receipt_sha256", "bad"),
    ],
)
def test_worker_result_binding_mismatches_fail(setup_dispatch, field, value):
    manifest, provider, _, _, _ = setup_dispatch
    provider.result_record[field] = value
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("manifest_sha256", "9" * 64),
        ("profile", "wrong-profile"),
        ("source", {}),
        ("authority", "APPROVED"),
        ("promotion", "GRANTED"),
    ],
)
def test_receipt_semantic_binding_mismatches_fail_even_with_valid_receipt_hash(
    setup_dispatch, field, value
):
    manifest, provider, _, _, _ = setup_dispatch
    provider.receipt[field] = value
    provider.rebind_receipt()
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


def test_receipt_output_reservation_must_match(setup_dispatch):
    manifest, provider, _, _, _ = setup_dispatch
    provider.receipt["output"]["reservation_commit"] = "9" * 40
    provider.rebind_receipt()
    with pytest.raises(dispatcher.DispatchError, match="RECEIPT_OUTPUT_MISMATCH"):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize("digest", [None, "", "wrong", "9" * 64])
def test_artifact_manifest_digest_is_mandatory_and_verified(setup_dispatch, digest):
    manifest, provider, _, _, _ = setup_dispatch
    if digest is None:
        del provider.receipt["artifacts_sha256"]
    else:
        provider.receipt["artifacts_sha256"] = digest
    provider.rebind_receipt()
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize("filename", ["manifest.json", "evaluation.json"])
def test_artifact_digest_tampering_fails_before_candidate_verification(
    setup_dispatch, filename
):
    manifest, provider, _, _, _ = setup_dispatch
    provider.files[filename] += b" "
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize("filename", ["manifest.json", "evaluation.json"])
def test_correct_hashes_cannot_hide_semantically_wrong_manifest_or_evaluation(
    setup_dispatch, filename
):
    manifest, provider, _, _, _ = setup_dispatch
    content = json.loads(provider.files[filename])
    if filename == "manifest.json":
        content["hyperparameters"]["seed"] += 1
    else:
        content["eval_loss"] = 0.01
    provider.files[filename] = canonical_bytes(content)
    provider.rebind_artifacts()
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("train_loss", True),
        ("train_loss", -1),
        ("train_loss", "1"),
        ("eval_loss", False),
        ("eval_loss", -1),
        ("eval_loss", "1"),
        ("eval_loss", 3),
        ("max_eval_loss", 3),
        ("passed", False),
        ("passed", 1),
    ],
)
def test_invalid_or_failing_metrics_rejected(setup_dispatch, field, value):
    manifest, provider, _, _, _ = setup_dispatch
    provider.receipt["evaluation"][field] = value
    provider.rebind_receipt()
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_metrics_never_verify(setup_dispatch, value):
    manifest, provider, _, _, _ = setup_dispatch
    provider.receipt["evaluation"]["eval_loss"] = value
    provider.receipt_raw = json.dumps(provider.receipt, allow_nan=True).encode()
    provider.result_record["receipt_sha256"] = hashlib.sha256(
        provider.receipt_raw
    ).hexdigest()
    with pytest.raises(ValueError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


def test_missing_required_artifact_is_not_a_verified_candidate(setup_dispatch):
    manifest, provider, _, _, _ = setup_dispatch
    del provider.files["adapter_model.safetensors"]
    provider.rebind_artifacts()
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


def test_completed_job_with_invalid_artifacts_is_failed_not_verified(setup_dispatch):
    _, provider, sink, _, _ = setup_dispatch
    provider.files["evaluation.json"] += b"tamper"
    with pytest.raises(dispatcher.DispatchError, match="TRAINING_NOT_VERIFIED"):
        run(setup_dispatch)
    assert sink.records[-1]["state"] == "FAILED_OR_UNKNOWN"
    assert all(record["state"] != "CANDIDATE_VERIFIED" for record in sink.records)


def test_receipt_sink_is_append_only_and_cannot_reuse_directory(tmp_path):
    directory = tmp_path / "receipts"
    sink = dispatcher.ReceiptSink(directory)
    manifest = make_manifest()
    record = sink.emit("VALIDATED_NOT_SUBMITTED", manifest)
    assert record["authority"] == "OPERATOR_SUPPLIED_UNVERIFIED"
    assert record["promotion"] == "NOT_GRANTED"
    assert record["manifest_sha256"] == canonical_sha256(manifest)
    assert (
        json.loads((directory / "001-VALIDATED_NOT_SUBMITTED.json").read_text())
        == record
    )
    with pytest.raises(FileExistsError):
        dispatcher.ReceiptSink(directory)


def test_job_command_embeds_worker_bytes_without_mutable_download():
    raw = b"raise SystemExit(0)\n"
    command = dispatcher.job_command(raw, hashlib.sha256(raw).hexdigest())
    assert command[:4] == ["python", "-I", "-B", "-c"]
    assert base64.b64encode(raw).decode() in command[4]
    assert hashlib.sha256(raw).hexdigest() in command[4]
    assert "https://" not in command[4]


def test_cli_empty_manifest_records_failure_without_provider(
    tmp_path, monkeypatch, capsys
):
    directory = tmp_path / "receipts"
    monkeypatch.setattr("sys.argv", ["dispatch", "--receipt-dir", str(directory)])
    monkeypatch.delenv("INPUT_TRAINING_MANIFEST", raising=False)
    with mock.patch.object(dispatcher, "HFProvider") as provider:
        assert dispatcher.main() == 1
    provider.assert_not_called()
    assert capsys.readouterr().out.strip() == "DISPATCH_FAILED"
    receipt = json.loads((directory / "001-DISPATCH_FAILED.json").read_text())
    assert receipt["state"] == "DISPATCH_FAILED"
    assert receipt["run_id"] is None


def test_cli_validation_only_does_not_construct_provider(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INPUT_TRAINING_MANIFEST", json.dumps(make_manifest()))
    monkeypatch.setattr(
        "sys.argv", ["dispatch", "--receipt-dir", str(tmp_path / "receipts")]
    )
    with mock.patch.object(dispatcher, "HFProvider") as provider:
        assert dispatcher.main() == 0
    provider.assert_not_called()
    assert capsys.readouterr().out.strip() == "VALIDATED_NOT_SUBMITTED"


def test_provider_api_explicitly_binds_huggingface_origin(monkeypatch):
    constructor = mock.Mock()
    monkeypatch.setenv("HF_ENDPOINT", "https://untrusted.example.test")
    with mock.patch.dict(
        sys.modules, {"huggingface_hub": SimpleNamespace(HfApi=constructor)}
    ):
        dispatcher.HFProvider("synthetic-test-token")
    assert constructor.call_args.kwargs["endpoint"] == "https://huggingface.co"
    assert constructor.call_args.kwargs["token"] == "synthetic-test-token"


def test_provider_download_explicitly_binds_origin_and_immutable_revision(
    tmp_path, monkeypatch
):
    raw = b"synthetic-bytes"
    artifact = tmp_path / "fixture.bin"
    artifact.write_bytes(raw)
    download = mock.Mock(return_value=str(artifact))
    provider = dispatcher.HFProvider.__new__(dispatcher.HFProvider)
    provider.token = "synthetic-test-token"
    provider.api = mock.Mock()
    provider.api.get_paths_info.return_value = [
        SimpleNamespace(size=len(raw), path="fixture.bin")
    ]
    monkeypatch.setenv("HF_ENDPOINT", "https://untrusted.example.test")
    with mock.patch.dict(
        sys.modules, {"huggingface_hub": SimpleNamespace(hf_hub_download=download)}
    ):
        observed = provider.read_file(
            "SZLHOLDINGS/khipu-frontier-35-2b",
            COMMIT,
            "fixture.bin",
            100,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )
    assert observed == raw
    assert download.call_args.kwargs["endpoint"] == "https://huggingface.co"
    assert download.call_args.kwargs["revision"] == COMMIT
    assert download.call_args.kwargs["token"] == "synthetic-test-token"


@pytest.mark.parametrize("commit", [RESERVATION, "5" * 40, "0" * 40])
def test_candidate_commit_must_be_new_and_nonzero(setup_dispatch, commit):
    manifest, provider, _, _, _ = setup_dispatch
    provider.result_record["commit"] = commit
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )
    assert provider.reads == []


@pytest.mark.parametrize(
    "filename", ["worker.py", "adapter_model.bin", "arbitrary.txt", "config.pkl"]
)
def test_artifact_names_are_explicitly_allowlisted(setup_dispatch, filename):
    manifest, provider, _, _, _ = setup_dispatch
    provider.files[filename] = b"unapproved-file"
    provider.rebind_artifacts()
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize(
    "document", ["receipt.json", "artifacts.json", "manifest.json", "evaluation.json"]
)
def test_duplicate_json_keys_cannot_hide_conflicting_receipt_evidence(
    setup_dispatch, document
):
    manifest, provider, _, _, _ = setup_dispatch
    if document == "receipt.json":
        provider.receipt_raw = b'{"status":"FAILED",' + provider.receipt_raw[1:]
        provider.result_record["receipt_sha256"] = hashlib.sha256(
            provider.receipt_raw
        ).hexdigest()
    elif document == "artifacts.json":
        provider.artifacts_raw = b'{"files":[],' + provider.artifacts_raw[1:]
        provider.receipt["artifacts_sha256"] = hashlib.sha256(
            provider.artifacts_raw
        ).hexdigest()
        provider.rebind_receipt()
    else:
        duplicate = (
            b'{"run_id":"different",'
            if document == "manifest.json"
            else b'{"eval_loss":999,'
        )
        provider.files[document] = duplicate + provider.files[document][1:]
        provider.rebind_artifacts()
    with pytest.raises(ValueError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )


@pytest.mark.parametrize(
    "logs",
    [
        [
            dispatcher.RESULT_PREFIX
            + '{"status":"FAILED","status":"CANDIDATE_PUBLISHED"}'
        ],
        [dispatcher.RESULT_PREFIX + "{}", dispatcher.RESULT_PREFIX + "{}"],
        ["no result envelope"],
        [dispatcher.RESULT_PREFIX + "[]"],
        [dispatcher.RESULT_PREFIX + '{"metric":NaN}'],
    ],
)
def test_job_log_results_reject_ambiguous_or_missing_json(logs):
    provider = dispatcher.HFProvider.__new__(dispatcher.HFProvider)
    provider.api = mock.Mock()
    provider.api.fetch_job_logs.return_value = logs
    with pytest.raises(ValueError):
        provider.result("offline-job-12345")


def test_job_log_scan_bounds_bytes_without_real_provider(monkeypatch):
    provider = dispatcher.HFProvider.__new__(dispatcher.HFProvider)
    provider.api = mock.Mock()
    provider.api.fetch_job_logs.return_value = ["a" * 33]
    monkeypatch.setattr(dispatcher, "MAX_LOG_BYTES", 32)
    with pytest.raises(dispatcher.DispatchError, match="JOB_LOG_LIMIT_EXCEEDED"):
        provider.result("offline-job-12345")


def test_final_receipt_sink_failure_cannot_report_success(setup_dispatch):
    _, provider, sink, _, _ = setup_dispatch
    sink.fail_state = "CANDIDATE_VERIFIED"
    with pytest.raises(dispatcher.DispatchError, match="TRAINING_NOT_VERIFIED"):
        run(setup_dispatch)
    assert provider.events.count("submit") == 1
    assert provider.events.count("cancel") == 1
    assert sink.records[-1]["state"] == "FAILED_OR_UNKNOWN"
    assert sink.records[-1]["job_id"] == "offline-job-12345"
    assert all(record["state"] != "CANDIDATE_VERIFIED" for record in sink.records)


@pytest.mark.parametrize(
    "filename,field,value",
    [
        ("manifest.json", "batch_size", True),
        ("manifest.json", "seed", 42.0),
        ("evaluation.json", "passed", 1),
    ],
)
def test_python_numeric_equality_cannot_weaken_published_json_types(
    setup_dispatch, filename, field, value
):
    manifest, provider, _, _, _ = setup_dispatch
    content = json.loads(provider.files[filename])
    if filename == "manifest.json":
        content["hyperparameters"][field] = value
    else:
        content[field] = value
    provider.files[filename] = canonical_bytes(content)
    provider.rebind_artifacts()
    with pytest.raises(ValueError):
        dispatcher.verify_candidate(
            manifest, RESERVATION, provider.result_record, provider
        )
