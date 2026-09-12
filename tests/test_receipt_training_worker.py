"""Offline contract tests: no model imports, downloads, provider calls or training."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


WORKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "receipt_training_worker.py"
spec = importlib.util.spec_from_file_location("receipt_training_worker", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
TRAIN_RAW = b'{"text":"A receipt records source and outcome."}\n'
EVAL_RAW = b'{"text":"A hash does not prove independent approval."}\n'
RESERVATION = "6" * 40
COMMIT = "7" * 40


def make_manifest():
    """Synthetic non-runnable fixture: versions/SHAs are not provider evidence."""
    return {
        "schema_version": "szl.training.v1",
        "run_id": "412e2768-d4c4-4a93-835d-71aa49897fbc",
        "profile": "khipu-frontier-35-2b",
        "source": {"repository": "szl-holdings/killinchu", "revision": "1" * 40,
                   "worker_sha256": hashlib.sha256(WORKER_PATH.read_bytes()).hexdigest()},
        "base_model": {"repo_id": "example/tiny-base", "revision": "2" * 40},
        "dataset": {"repo_id": "example/receipt-text", "revision": "3" * 40,
                    "train_file": "train.jsonl", "train_sha256": hashlib.sha256(TRAIN_RAW).hexdigest(),
                    "train_rows": 1, "eval_file": "eval.jsonl", "eval_sha256": hashlib.sha256(EVAL_RAW).hexdigest(),
                    "eval_rows": 1, "max_file_bytes": 4096},
        "runtime": {"image": worker.NON_RUNNABLE_TEST_RUNTIME,
                    "flavor": worker.NON_RUNNABLE_TEST_FLAVOR, "timeout_seconds": 600,
                    "dependencies": dict(worker.NON_RUNNABLE_TEST_DEPENDENCIES)},
        "hyperparameters": {"seed": 42, "r": 8, "lora_alpha": 16, "lora_dropout": 0.05,
                            "lr": 0.0001, "max_steps": 2, "max_seq": 128, "batch_size": 1,
                            "gradient_accumulation_steps": 2, "weight_decay": 0.01,
                            "warmup_ratio": 0.1, "target_modules": ["q_proj", "v_proj"], "precision": "bf16"},
        "evaluation": {"max_eval_loss": 2.0},
        "output": {"repo_id": "SZLHOLDINGS/khipu-frontier-35-2b", "parent_commit": "5" * 40},
        "authorization": {"reference": "fixture-not-approved", "sha256": "8" * 64,
                          "max_cost_usd": 1, "max_hourly_usd": 1},
    }


class FakeBackend:
    def __init__(self):
        self.events = []
        self.metrics = {"train_loss": 1.0, "eval_loss": 1.5}
        self.train_raw = TRAIN_RAW
        self.eval_raw = EVAL_RAW
        self.head = RESERVATION
        self.reservation_override = None
        self.files = {}
        self.bad_artifact = None
        self.train_error = False
        self.publish_error = False
        self.drift_after_training = False

    def check_versions(self, dependencies):
        self.events.append("versions")

    def reservation_bytes(self, manifest, commit):
        self.events.append("reservation")
        return worker.canonical_bytes(self.reservation_override or {
            "schema_version": "szl.training.reservation.v1", "run_id": manifest["run_id"],
            "manifest_sha256": worker.canonical_sha256(manifest), "source_revision": manifest["source"]["revision"],
        })

    def output_head(self, manifest):
        self.events.append("head")
        return self.head

    def dataset_bytes(self, manifest, split):
        self.events.append("data:" + split)
        return self.train_raw if split == "train" else self.eval_raw

    def train(self, manifest, train, evaluation, artifact_dir):
        self.events.append("train")
        if self.train_error:
            raise RuntimeError("PRIVATE_TOKEN_AND_DATA_MUST_NOT_LEAK")
        (artifact_dir / "adapter_model.safetensors").write_bytes(b"offline-stub-not-real-weights")
        hyper = manifest["hyperparameters"]
        (artifact_dir / "adapter_config.json").write_bytes(worker.canonical_bytes({
            "peft_type": "LORA", "task_type": "CAUSAL_LM", "bias": "none",
            "r": hyper["r"], "lora_alpha": hyper["lora_alpha"],
            "lora_dropout": hyper["lora_dropout"],
            "target_modules": hyper["target_modules"],
            "base_model_name_or_path": manifest["base_model"]["repo_id"],
            "revision": manifest["base_model"]["revision"],
        }))
        if self.bad_artifact:
            (artifact_dir / self.bad_artifact).write_bytes(b"not-admitted")
        if self.drift_after_training:
            self.head = "9" * 40
        return self.metrics

    def publish(self, manifest, files, reservation_commit):
        self.events.append("publish")
        assert reservation_commit == RESERVATION
        if self.publish_error:
            raise RuntimeError("PRIVATE_TOKEN_AND_DATA_MUST_NOT_LEAK")
        self.files = {path: file.read_bytes() for path, file in files.items()}
        return COMMIT


def run(manifest=None, backend=None, **kwargs):
    manifest = make_manifest() if manifest is None else manifest
    backend = FakeBackend() if backend is None else backend
    result = worker.run_training(manifest, backend, worker_path=WORKER_PATH,
                                 source_revision=kwargs.pop("source_revision", manifest["source"]["revision"]),
                                 reservation_commit=kwargs.pop("reservation_commit", RESERVATION), **kwargs)
    return result, backend


def test_validate_round_trip_and_no_mutation():
    manifest = make_manifest()
    expected = copy.deepcopy(manifest)
    observed = worker.validate_manifest(manifest)
    assert observed == expected and manifest == expected and observed is not manifest


def test_production_runtime_allowlist_is_empty_and_arbitrary_digest_is_rejected():
    assert dict(worker.APPROVED_RUNTIMES) == {}
    manifest = make_manifest()
    manifest["runtime"]["image"] = (
        "registry.invalid/unreviewed@sha256:" + "9" * 64
    )
    with pytest.raises(ValueError, match="^RUNTIME_NOT_APPROVED$"):
        worker.validate_manifest(manifest)


def test_approved_runtime_requires_exact_dependencies_and_flavor(monkeypatch):
    manifest = make_manifest()
    image = "registry.invalid/review-fixture@sha256:" + "9" * 64
    manifest["runtime"]["image"] = image
    approval = {
        image: {
            "dependencies": dict(manifest["runtime"]["dependencies"]),
            "flavors": frozenset({manifest["runtime"]["flavor"]}),
        }
    }
    monkeypatch.setattr(worker, "APPROVED_RUNTIMES", approval)
    assert worker.validate_manifest(manifest) == manifest

    wrong_dependencies = copy.deepcopy(manifest)
    wrong_dependencies["runtime"]["dependencies"]["trl"] = "9.9.9"
    with pytest.raises(ValueError, match="^RUNTIME_APPROVAL_MISMATCH$"):
        worker.validate_manifest(wrong_dependencies)

    wrong_flavor = copy.deepcopy(manifest)
    wrong_flavor["runtime"]["flavor"] = "t4-small"
    with pytest.raises(ValueError, match="^RUNTIME_APPROVAL_MISMATCH$"):
        worker.validate_manifest(wrong_flavor)


@pytest.mark.parametrize("path,value", [
    (("schema_version",), "wrong"), (("profile",), "drone-actions"),
    (("source", "repository"), "other/repo"), (("source", "revision"), "main"),
    (("source", "worker_sha256"), "0" * 64), (("base_model", "revision"), "latest"),
    (("base_model", "repo_id"), "https://evil.invalid/model"),
    (("dataset", "train_file"), "../train.jsonl"), (("dataset", "train_file"), "data//train.jsonl"),
    (("dataset", "train_rows"), 0), (("dataset", "eval_rows"), True),
    (("runtime", "image"), "example/image:latest"), (("runtime", "flavor"), "zero-a10g"),
    (("runtime", "dependencies", "trl"), ">=1.2.3"), (("runtime", "timeout_seconds"), 10**300),
    (("hyperparameters", "r"), False), (("hyperparameters", "lr"), float("nan")),
    (("hyperparameters", "max_steps"), 0), (("hyperparameters", "precision"), "int4"),
    (("hyperparameters", "target_modules"), ["q_proj", "q_proj"]),
    (("evaluation", "max_eval_loss"), float("inf")),
    (("output", "repo_id"), "SZLHOLDINGS/willay-3"), (("output", "parent_commit"), "main"),
    (("authorization", "max_cost_usd"), 0.01), (("authorization", "reference"), "secret\nvalue"),
])
def test_invalid_fields_fail_closed(path, value):
    manifest = make_manifest()
    current = manifest
    for field in path[:-1]:
        current = current[field]
    current[path[-1]] = value
    with pytest.raises(ValueError, match="^MANIFEST_INVALID$"):
        worker.validate_manifest(manifest)


@pytest.mark.parametrize("manifest", [{}, [], None, {"schema_version": "szl.training.v1"}])
def test_missing_or_empty_manifest(manifest):
    with pytest.raises(ValueError):
        worker.validate_manifest(manifest)


def test_unknown_fields_rejected_at_every_level():
    for field in (None, "source", "base_model", "dataset", "runtime", "hyperparameters", "evaluation", "output", "authorization"):
        manifest = make_manifest()
        (manifest if field is None else manifest[field])["unexpected"] = "ignored-not-allowed"
        with pytest.raises(ValueError):
            worker.validate_manifest(manifest)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{', b'\xff'])
def test_strict_json_parser(raw):
    with pytest.raises(ValueError, match="^INVALID_JSON$"):
        worker.parse_json(raw)


def test_stale_source_rejected_before_backend():
    backend = FakeBackend()
    with pytest.raises(ValueError, match="SOURCE_REVISION_MISMATCH"):
        run(backend=backend, source_revision="9" * 40)
    assert not backend.events


def test_worker_bytes_mismatch_rejected_before_backend():
    backend = FakeBackend()
    manifest = make_manifest()
    manifest["source"]["worker_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="WORKER_HASH_MISMATCH"):
        run(manifest, backend)
    assert not backend.events


def test_reservation_binding_required_before_data_or_training():
    backend = FakeBackend()
    backend.reservation_override = {"schema_version": "szl.training.reservation.v1", "run_id": "wrong"}
    with pytest.raises(ValueError, match="RESERVATION_INVALID"):
        run(backend=backend)
    assert "train" not in backend.events and "data:train" not in backend.events


@pytest.mark.parametrize("after_training", [False, True])
def test_output_parent_drift_blocks_publication(after_training):
    backend = FakeBackend()
    if after_training:
        backend.drift_after_training = True
    else:
        backend.head = "8" * 40
    with pytest.raises(ValueError, match="OUTPUT_PARENT_MISMATCH"):
        run(backend=backend)
    assert "publish" not in backend.events
    assert ("train" in backend.events) == after_training


@pytest.mark.parametrize("raw", [b"", b'{"text":"different"}\n'])
def test_data_hash_or_empty_rejected_before_training(raw):
    backend = FakeBackend()
    backend.train_raw = raw
    with pytest.raises(ValueError, match="DATA_(SIZE_INVALID|HASH_MISMATCH)"):
        run(backend=backend)
    assert "train" not in backend.events


@pytest.mark.parametrize("raw,error", [
    (b'{"text":"a"}\n{"text":"a"}\n', "DATA_DUPLICATE_TEXT"),
    (b'{"text":"a","tool":"execute"}\n', "DATA_SCHEMA_INVALID"),
    (b'{"text":" "}\n', "DATA_TEXT_INVALID"),
    (b'{"text":8}\n', "DATA_TEXT_INVALID"),
])
def test_dataset_semantics(raw, error):
    with pytest.raises(ValueError, match=error):
        worker.validate_data(raw, hashlib.sha256(raw).hexdigest(), len(raw.splitlines()), 4096)


def test_normalized_train_eval_overlap_rejected():
    manifest = make_manifest()
    # Different bytes/hashes, identical whitespace-normalized text.
    evaluation = b'{"text":"A receipt  records source and outcome."}\n'
    manifest["dataset"]["eval_sha256"] = hashlib.sha256(evaluation).hexdigest()
    with pytest.raises(ValueError, match="DATA_TRAIN_EVAL_OVERLAP"):
        worker.validate_dataset_records(manifest, TRAIN_RAW, evaluation)


@pytest.mark.parametrize("metrics", [
    {"train_loss": float("nan"), "eval_loss": 1},
    {"train_loss": 1, "eval_loss": float("inf")},
    {"train_loss": 1, "eval_loss": -1},
    {"train_loss": 1, "eval_loss": True},
    {"train_loss": 1, "eval_loss": 2.01},
    {"train_loss": 1},
    {"train_loss": 10**300, "eval_loss": 1},
])
def test_loss_and_metric_failures_never_publish(metrics):
    backend = FakeBackend()
    backend.metrics = metrics
    with pytest.raises(ValueError):
        run(backend=backend)
    assert "publish" not in backend.events


@pytest.mark.parametrize("name", ["pytorch_model.bin", "trainer_state.json", "train.jsonl", "dataset.txt", "malicious.py"])
def test_unallowlisted_artifacts_never_publish(name):
    backend = FakeBackend()
    backend.bad_artifact = name
    with pytest.raises(ValueError, match="ARTIFACT_INVALID"):
        run(backend=backend)
    assert "publish" not in backend.events


def test_training_failure_does_not_publish():
    backend = FakeBackend()
    backend.train_error = True
    with pytest.raises(RuntimeError):
        run(backend=backend)
    assert "publish" not in backend.events


def test_publication_uncertainty_is_sanitized():
    backend = FakeBackend()
    backend.publish_error = True
    with pytest.raises(ValueError, match="^CANDIDATE_PUBLICATION_OUTCOME_UNKNOWN$"):
        run(backend=backend)


def test_candidate_receipts_cover_exact_bytes_and_do_not_grant_promotion():
    manifest = make_manifest()
    result, backend = run(manifest)
    prefix = "candidates/" + manifest["run_id"] + "/"
    assert backend.events.index("train") < backend.events.index("publish")
    assert backend.events.count("head") == 2
    assert result["commit"] == COMMIT
    assert all(path.startswith(prefix) for path in backend.files)
    receipt_raw = backend.files[prefix + "receipt.json"]
    receipt = json.loads(receipt_raw)
    assert result["receipt_sha256"] == hashlib.sha256(receipt_raw).hexdigest()
    assert receipt["authority"] == "OPERATOR_SUPPLIED_UNVERIFIED"
    assert receipt["promotion"] == "NOT_GRANTED"
    assert receipt["output"] == {**manifest["output"], "reservation_commit": RESERVATION, "prefix": prefix}
    artifacts_raw = backend.files[prefix + "artifacts.json"]
    assert receipt["artifacts_sha256"] == hashlib.sha256(artifacts_raw).hexdigest()
    for entry in json.loads(artifacts_raw)["files"]:
        raw = backend.files[prefix + entry["path"]]
        assert len(raw) == entry["size_bytes"]
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    assert json.loads(backend.files[prefix + "manifest.json"]) == manifest
    assert json.loads(backend.files[prefix + "evaluation.json"]) == receipt["evaluation"]


def test_dependency_versions_rejected_before_provider_import(monkeypatch):
    monkeypatch.setattr(worker.importlib.metadata, "version", lambda _: "0.0.0")
    backend = worker.HubBackend()
    with pytest.raises(ValueError, match="DEPENDENCY_MISMATCH"):
        backend.check_versions(make_manifest()["runtime"]["dependencies"])
    assert backend.api is None


def test_hub_publication_uses_reservation_cas_and_candidate_only(monkeypatch, tmp_path):
    calls = []
    class FakeAPI:
        def get_paths_info(self, *args, **kwargs):
            calls.append(("inspect", args, kwargs))
            return []
        def create_commit(self, **kwargs):
            calls.append(("commit", (), kwargs))
            return SimpleNamespace(oid=COMMIT)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(CommitOperationAdd=lambda **kw: kw))
    backend = worker.HubBackend()
    backend.api = FakeAPI()
    manifest = make_manifest()
    name = "candidates/" + manifest["run_id"] + "/receipt.json"
    assert backend.publish(manifest, {name: tmp_path / "receipt.json"}, RESERVATION) == COMMIT
    params = calls[-1][2]
    assert params["parent_commit"] == RESERVATION and params["revision"] == "main"
    assert params["create_pr"] is False
    assert params["operations"][0]["path_in_repo"] == name


def test_cli_failure_logs_no_exception_data(monkeypatch, capsys):
    manifest = make_manifest()
    monkeypatch.setenv("TRAINING_MANIFEST_JSON", json.dumps(manifest))
    monkeypatch.setenv("TRAINING_SOURCE_REVISION", manifest["source"]["revision"])
    monkeypatch.setenv("TRAINING_RESERVATION_COMMIT", RESERVATION)
    backend = FakeBackend()
    backend.train_error = True
    monkeypatch.setattr(worker, "HubBackend", lambda: backend)
    assert worker.main() == 1
    captured = capsys.readouterr()
    assert "PRIVATE_TOKEN" not in captured.out + captured.err
    assert captured.out.startswith("SZL_TRAINING_RESULT=")
    envelope = json.loads(captured.out.split("=", 1)[1])
    assert envelope["status"] == "FAILED" and envelope["promotion"] == "NOT_GRANTED"


def install_training_stubs(monkeypatch, tmp_path, *, eval_loss=1.5):
    """Exercise real adapter orchestration with library fakes, never GPU work."""
    calls = {}
    class Model:
        def save_pretrained(self, directory, **kwargs):
            calls["save"] = kwargs
            path = Path(directory)
            (path / "adapter_model.safetensors").write_bytes(b"offline-stub")
            (path / "adapter_config.json").write_bytes(worker.canonical_bytes({
                "peft_type": "LORA", "task_type": "CAUSAL_LM", "bias": "none",
                "r": 8, "lora_alpha": 16, "lora_dropout": 0.05,
                "target_modules": ["q_proj", "v_proj"],
                "base_model_name_or_path": "C:/untrusted/local/snapshot",
                "revision": None,
            }))
            (path / "README.md").write_text("generated; not a model card approval")
    class Tokenizer:
        pad_token = None
        eos_token = "</s>"
        eos_token_id = 2
        def encode(self, text, **kwargs):
            calls.setdefault("encoded", []).append((text, kwargs))
            return [1] + [ord(char) + 3 for char in text]
        def save_pretrained(self, directory):
            (Path(directory) / "tokenizer.json").write_bytes(b"{}")
    def load_model(directory, **kwargs):
        calls["model"] = (directory, kwargs)
        return Model()
    def load_tokenizer(directory, **kwargs):
        calls["tokenizer"] = (directory, kwargs)
        return Tokenizer()
    def snapshot(*args, **kwargs):
        calls["snapshot"] = (args, kwargs)
        return str(tmp_path / "base")
    def config(**kwargs):
        calls["config"] = kwargs
        return kwargs
    def lora(**kwargs):
        calls["lora"] = kwargs
        return kwargs
    class Trainer:
        def __init__(self, **kwargs):
            calls["trainer"] = kwargs
            self.model = kwargs["model"]
            self.train_dataset = kwargs["train_dataset"]
            self.eval_dataset = kwargs["eval_dataset"]
            self.state = SimpleNamespace(global_step=kwargs["args"]["max_steps"])
        def train(self):
            calls["train"] = True
            return SimpleNamespace(training_loss=1.0)
        def evaluate(self):
            calls["eval"] = True
            return {"eval_loss": eval_loss}
    class SafeWeights:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def keys(self):
            return ["lora_A", "lora_B"]
    modules = {
        "torch": SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, is_bf16_supported=lambda: True),
                                 bfloat16="bf16", float16="fp16", float32="fp32"),
        "trackio": SimpleNamespace(init=lambda **kw: calls.update(trackio_init=kw),
                                   log=lambda *args, **kw: calls.update(trackio_log=(args, kw)),
                                   finish=lambda: calls.update(trackio_finished=True)),
        "datasets": SimpleNamespace(Dataset=SimpleNamespace(from_list=lambda rows: rows)),
        "huggingface_hub": SimpleNamespace(snapshot_download=snapshot),
        "peft": SimpleNamespace(LoraConfig=lora),
        "safetensors": SimpleNamespace(safe_open=lambda *args, **kw: SafeWeights()),
        "transformers": SimpleNamespace(AutoModelForCausalLM=SimpleNamespace(from_pretrained=load_model),
                                        AutoTokenizer=SimpleNamespace(from_pretrained=load_tokenizer),
                                        TrainerCallback=object, set_seed=lambda value: calls.update(seed=value)),
        "trl": SimpleNamespace(SFTConfig=config, SFTTrainer=Trainer),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("HF_TOKEN", "not-a-provider-credential")
    monkeypatch.setenv("TRACKIO_SPACE_ID", "must-not-be-used")
    monkeypatch.setenv("TRACKIO_SERVER_URL", "https://must-not-be-used.invalid")
    # Register cleanup before the backend mutates these process variables.
    for key in ("TRACKIO_DIR", "HF_HUB_DISABLE_TELEMETRY", "TOKENIZERS_PARALLELISM"):
        monkeypatch.setenv(key, "test-original")
    return calls


@pytest.mark.parametrize("precision", ["bf16", "fp16", "fp32"])
def test_actual_backend_forwards_every_hyperparameter_with_remote_code_disabled(monkeypatch, tmp_path, precision):
    manifest = make_manifest()
    manifest["hyperparameters"]["precision"] = precision
    calls = install_training_stubs(monkeypatch, tmp_path)
    output = tmp_path / "artifacts"
    output.mkdir()
    observed = worker.HubBackend().train(manifest, [{"text": "train"}], [{"text": "eval"}], output)
    assert observed == {"train_loss": 1.0, "eval_loss": 1.5}
    hyper, config = manifest["hyperparameters"], calls["config"]
    assert calls["seed"] == hyper["seed"]
    for manifest_key, config_key in {
        "seed": "seed", "lr": "learning_rate", "max_steps": "max_steps", "max_seq": "max_length",
        "batch_size": "per_device_train_batch_size", "gradient_accumulation_steps": "gradient_accumulation_steps",
        "weight_decay": "weight_decay", "warmup_ratio": "warmup_ratio",
    }.items():
        assert config[config_key] == hyper[manifest_key]
    for key in ("r", "lora_alpha", "lora_dropout", "target_modules"):
        assert calls["lora"][key] == hyper[key]
    assert config["data_seed"] == hyper["seed"]
    assert config["bf16"] == (precision == "bf16") and config["fp16"] == (precision == "fp16")
    assert config["push_to_hub"] is False and config["save_strategy"] == "no"
    assert config["logging_nan_inf_filter"] is False
    assert config["dataset_kwargs"] == {"skip_prepare_dataset": True}
    assert not config["packing"] and not config["eval_packing"] and not config["padding_free"]
    assert not config["completion_only_loss"] and not config["assistant_only_loss"]
    assert calls["trainer"]["train_dataset"] == [{"input_ids": [1, 119, 117, 100, 108, 113, 2],
                                                 "attention_mask": [1] * 7}]
    assert all(kwargs == {"add_special_tokens": True, "truncation": False} for _, kwargs in calls["encoded"])
    assert calls["snapshot"][1]["revision"] == manifest["base_model"]["revision"]
    assert "*.bin" in calls["snapshot"][1]["ignore_patterns"]
    assert calls["model"][1]["trust_remote_code"] is False
    assert calls["model"][1]["local_files_only"] is True
    assert calls["model"][1]["use_safetensors"] is True
    assert calls["tokenizer"][1]["trust_remote_code"] is False
    assert calls["save"]["safe_serialization"] is True
    adapter_config = worker.parse_json((output / "adapter_config.json").read_bytes())
    assert adapter_config["base_model_name_or_path"] == manifest["base_model"]["repo_id"]
    assert adapter_config["revision"] == manifest["base_model"]["revision"]
    assert calls["trackio_init"]["space_id"] is None
    assert "TRACKIO_SPACE_ID" not in worker.os.environ and "TRACKIO_SERVER_URL" not in worker.os.environ
    assert calls["trackio_finished"] is True
    assert not (output / "README.md").exists()


@pytest.mark.parametrize("eval_loss", [float("nan"), float("inf"), 2.001])
def test_actual_backend_failed_evaluation_saves_no_candidate(monkeypatch, tmp_path, eval_loss):
    calls = install_training_stubs(monkeypatch, tmp_path, eval_loss=eval_loss)
    output = tmp_path / "artifacts"
    output.mkdir()
    with pytest.raises(ValueError):
        worker.HubBackend().train(make_manifest(), [{"text": "train"}], [{"text": "eval"}], output)
    assert "save" not in calls and list(output.iterdir()) == []
    assert calls["trackio_finished"] is True
