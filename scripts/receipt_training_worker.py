#!/usr/bin/env python3
"""Source-bound text SFT candidate worker; importing this module has no side effects.

Only a reviewed, concrete manifest can run. A measured loss is not independent
quality evidence. Candidate publication never grants deployment or promotion.
Dependencies must already exist in the digest-pinned job image; no runtime pip.
"""

from __future__ import annotations

from collections.abc import Mapping
import contextlib
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from types import MappingProxyType
import unicodedata
import uuid


PROFILES = {
    "khipu-frontier-35-2b": "SZLHOLDINGS/khipu-frontier-35-2b",
    "forge-frontier-35-2b": "SZLHOLDINGS/forge-frontier-35-2b",
    "willay-3": "SZLHOLDINGS/willay-3",
}
DEPENDENCIES = {
    "torch", "transformers", "trl", "peft", "datasets", "huggingface-hub",
    "trackio", "accelerate", "safetensors",
}
FLAVORS = {"t4-small", "t4-medium", "l4x1", "a10g-small", "a10g-large", "a100-large"}
MODULES = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
ARTIFACT_NAMES = {
    "adapter_model.safetensors", "adapter_config.json", "tokenizer.json",
    "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json",
    "vocab.json", "merges.txt", "tokenizer.model", "chat_template.jinja",
}
MAX_MANIFEST_BYTES = 65536
MAX_ADAPTER_CONFIG_BYTES = 256 * 1024

# Production is intentionally fail-closed until a separate signed change adds
# one attested image digest with its reviewed package versions and hardware.
# This reserved .invalid sentinel exists only so provider-free unit contracts
# can exercise the worker schema; the dispatcher must never submit it.
NON_RUNNABLE_TEST_RUNTIME = "training.invalid/receipt-training@sha256:" + "4" * 64
NON_RUNNABLE_TEST_DEPENDENCIES = MappingProxyType(
    {name: "1.2.3" for name in DEPENDENCIES}
)
NON_RUNNABLE_TEST_FLAVOR = "a10g-small"
APPROVED_RUNTIMES = MappingProxyType({})


def _require(condition, error="MANIFEST_INVALID"):
    if not condition:
        raise ValueError(error)


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names))


def _string(value, pattern, max_length=256):
    _require(type(value) is str and len(value) <= max_length)
    _require(re.fullmatch(pattern, value) is not None)


def _number(value, minimum, maximum, integer=False):
    _require(type(value) is int if integer else type(value) in (int, float))
    _require(minimum <= value <= maximum and math.isfinite(value))


def _revision(value):
    _string(value, r"[0-9a-f]{40}")
    _require(value != "0" * 40)


def _digest(value):
    _string(value, r"[0-9a-f]{64}")
    _require(value != "0" * 64)


def _repo(value):
    _string(value, r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
    _require(".." not in value and "--" not in value)


def _data_path(value):
    _string(value, r"[A-Za-z0-9][A-Za-z0-9_./-]*\.jsonl")
    path = PurePosixPath(value)
    _require(not path.is_absolute() and str(path) == value)
    _require(all(part not in (".", "..") for part in path.parts))


def _validate_runtime_approval(runtime):
    image = runtime["image"]
    dependencies = runtime["dependencies"]
    flavor = runtime["flavor"]
    if image == NON_RUNNABLE_TEST_RUNTIME:
        _require(
            dependencies == dict(NON_RUNNABLE_TEST_DEPENDENCIES)
            and flavor == NON_RUNNABLE_TEST_FLAVOR,
            "TEST_RUNTIME_CONTRACT_MISMATCH",
        )
        return
    approval = APPROVED_RUNTIMES.get(image)
    _require(
        isinstance(approval, Mapping)
        and set(approval) == {"dependencies", "flavors"},
        "RUNTIME_NOT_APPROVED",
    )
    approved_dependencies = approval["dependencies"]
    approved_flavors = approval["flavors"]
    _require(
        isinstance(approved_dependencies, Mapping)
        and set(approved_dependencies) == DEPENDENCIES
        and type(approved_flavors) is frozenset
        and bool(approved_flavors)
        and approved_flavors <= FLAVORS,
        "RUNTIME_APPROVAL_INVALID",
    )
    _require(
        dependencies == approved_dependencies and flavor in approved_flavors,
        "RUNTIME_APPROVAL_MISMATCH",
    )


def canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("INVALID_JSON") from None


def canonical_sha256(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def parse_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("INVALID_JSON") from None


def validate_manifest(manifest):
    """Strict admission syntax, not verification of human authority or data rights."""
    _keys(manifest, ("schema_version", "run_id", "profile", "source", "base_model",
                     "dataset", "runtime", "hyperparameters", "evaluation", "output",
                     "authorization"))
    _require(manifest["schema_version"] == "szl.training.v1")
    _string(manifest["run_id"], r"[0-9a-f-]{36}")
    try:
        run_id = uuid.UUID(manifest["run_id"])
    except ValueError:
        raise ValueError("MANIFEST_INVALID") from None
    _require(str(run_id) == manifest["run_id"] and run_id.int != 0)
    _require(type(manifest["profile"]) is str and manifest["profile"] in PROFILES)
    source = manifest["source"]
    _keys(source, ("repository", "revision", "worker_sha256"))
    _require(source["repository"] == "szl-holdings/killinchu")
    _revision(source["revision"])
    _digest(source["worker_sha256"])
    base = manifest["base_model"]
    _keys(base, ("repo_id", "revision"))
    _repo(base["repo_id"])
    _revision(base["revision"])
    data = manifest["dataset"]
    _keys(data, ("repo_id", "revision", "train_file", "train_sha256", "train_rows",
                 "eval_file", "eval_sha256", "eval_rows", "max_file_bytes"))
    _repo(data["repo_id"])
    _revision(data["revision"])
    for split in ("train", "eval"):
        _data_path(data[split + "_file"])
        _digest(data[split + "_sha256"])
        _number(data[split + "_rows"], 1, 1000000, integer=True)
    _require(data["train_file"] != data["eval_file"])
    _require(data["train_sha256"] != data["eval_sha256"])
    _number(data["max_file_bytes"], 1, 64 * 1024 * 1024, integer=True)
    runtime = manifest["runtime"]
    _keys(runtime, ("image", "flavor", "timeout_seconds", "dependencies"))
    _string(runtime["image"], r"[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}")
    _require(not runtime["image"].endswith("0" * 64))
    _require(type(runtime["flavor"]) is str and runtime["flavor"] in FLAVORS)
    _number(runtime["timeout_seconds"], 300, 14400, integer=True)
    _keys(runtime["dependencies"], DEPENDENCIES)
    for version in runtime["dependencies"].values():
        _string(version, r"[0-9]+\.[0-9]+\.[0-9]+(?:\+[A-Za-z0-9.]+)?", 64)
    _validate_runtime_approval(runtime)
    hyper = manifest["hyperparameters"]
    _keys(hyper, ("seed", "r", "lora_alpha", "lora_dropout", "lr", "max_steps",
                  "max_seq", "batch_size", "gradient_accumulation_steps",
                  "weight_decay", "warmup_ratio", "target_modules", "precision"))
    for field, low, high in (("seed", 0, 2**32 - 1), ("r", 1, 256),
                             ("lora_alpha", 1, 1024), ("max_steps", 1, 100000),
                             ("max_seq", 16, 32768), ("batch_size", 1, 64),
                             ("gradient_accumulation_steps", 1, 1024)):
        _number(hyper[field], low, high, integer=True)
    for field, low, high in (("lora_dropout", 0, 0.5), ("lr", 1e-8, 0.01),
                             ("weight_decay", 0, 1), ("warmup_ratio", 0, 0.5)):
        _number(hyper[field], low, high)
    modules = hyper["target_modules"]
    _require(type(modules) is list and 1 <= len(modules) <= len(MODULES))
    _require(all(type(item) is str and item in MODULES for item in modules))
    _require(len(set(modules)) == len(modules))
    _require(hyper["precision"] in ("bf16", "fp16", "fp32"))
    _keys(manifest["evaluation"], ("max_eval_loss",))
    _number(manifest["evaluation"]["max_eval_loss"], 0.000001, 100)
    output = manifest["output"]
    _keys(output, ("repo_id", "parent_commit"))
    _require(output["repo_id"] == PROFILES[manifest["profile"]])
    _revision(output["parent_commit"])
    auth = manifest["authorization"]
    _keys(auth, ("reference", "sha256", "max_cost_usd", "max_hourly_usd"))
    _string(auth["reference"], r"[A-Za-z0-9][A-Za-z0-9_./:#-]{0,255}")
    _digest(auth["sha256"])
    _number(auth["max_cost_usd"], 0.01, 10000)
    _number(auth["max_hourly_usd"], 0.01, 1000)
    _require(auth["max_cost_usd"] >= auth["max_hourly_usd"] * runtime["timeout_seconds"] / 3600)
    _require(len(canonical_bytes(manifest)) <= MAX_MANIFEST_BYTES)
    return parse_json(canonical_bytes(manifest))


def validate_data(raw, expected_hash, expected_rows, max_bytes):
    _require(type(raw) is bytes and 0 < len(raw) <= max_bytes, "DATA_SIZE_INVALID")
    _require(hashlib.sha256(raw).hexdigest() == expected_hash, "DATA_HASH_MISMATCH")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        raise ValueError("DATA_ENCODING_INVALID") from None
    _require(len(lines) == expected_rows, "DATA_ROWS_MISMATCH")
    result, identities = [], set()
    for line in lines:
        row = parse_json(line)
        _require(type(row) is dict and set(row) == {"text"}, "DATA_SCHEMA_INVALID")
        text = row["text"]
        _require(type(text) is str and 0 < len(text.strip()) <= 1000000, "DATA_TEXT_INVALID")
        try:
            identity = hashlib.sha256(unicodedata.normalize("NFKC", " ".join(text.split())).encode()).hexdigest()
        except UnicodeError:
            raise ValueError("DATA_ENCODING_INVALID") from None
        _require(identity not in identities, "DATA_DUPLICATE_TEXT")
        identities.add(identity)
        result.append(row)
    return result, identities


def validate_metrics(metrics, threshold):
    _require(type(metrics) is dict and set(metrics) == {"train_loss", "eval_loss"}, "METRICS_INVALID")
    for loss in metrics.values():
        _require(type(loss) in (int, float) and 0 <= loss <= 1e100 and math.isfinite(loss), "LOSS_INVALID")
    _require(metrics["eval_loss"] <= threshold, "EVALUATION_THRESHOLD_FAILED")
    return {**metrics, "max_eval_loss": threshold, "passed": True}


def validate_dataset_records(manifest, train_raw, eval_raw):
    """CPU-only preflight usable by the dispatcher before any billable submission."""
    manifest = validate_manifest(manifest)
    data = manifest["dataset"]
    train, train_ids = validate_data(train_raw, data["train_sha256"], data["train_rows"], data["max_file_bytes"])
    evaluation, eval_ids = validate_data(eval_raw, data["eval_sha256"], data["eval_rows"], data["max_file_bytes"])
    _require(train_ids.isdisjoint(eval_ids), "DATA_TRAIN_EVAL_OVERLAP")
    return train, evaluation


def prepare_tokenized_splits(tokenizer, train, evaluation, max_length):
    """Admit exactly the causal-LM input sequences passed to SFT.

    The pinned tokenizer inserts its normal special tokens. We append one EOS
    only if absent, then keep the first max_length tokens. SFT receives these
    input_ids with its own preparation/packing disabled, not the original text.
    Exact token equality is a leakage check, not semantic held-out independence.
    """
    eos = getattr(tokenizer, "eos_token_id", None)
    _require(type(eos) is int and 0 <= eos < 2**31, "TOKENIZER_EOS_INVALID")
    _require(type(max_length) is int and 2 <= max_length <= 32768, "TOKEN_LENGTH_INVALID")
    splits, identities = [], []
    for rows in (train, evaluation):
        prepared, seen = [], set()
        _require(type(rows) is list and bool(rows), "TOKEN_DATA_EMPTY")
        for row in rows:
            _require(type(row) is dict and set(row) == {"text"} and type(row["text"]) is str,
                     "TOKEN_DATA_SCHEMA_INVALID")
            try:
                tokens = tokenizer.encode(row["text"], add_special_tokens=True, truncation=False)
            except Exception:
                raise ValueError("TOKENIZATION_FAILED") from None
            _require(type(tokens) is list and all(type(token) is int and 0 <= token < 2**31 for token in tokens),
                     "TOKENIZATION_INVALID")
            if not tokens or tokens[-1] != eos:
                tokens = [*tokens, eos]
            tokens = tokens[:max_length]
            _require(len(tokens) >= 2, "TOKEN_SEQUENCE_TOO_SHORT")
            identity = canonical_sha256(tokens)
            _require(identity not in seen, "TOKEN_DUPLICATE_EFFECTIVE_SEQUENCE")
            seen.add(identity)
            prepared.append({"input_ids": tokens, "attention_mask": [1] * len(tokens)})
        splits.append(prepared)
        identities.append(seen)
    _require(identities[0].isdisjoint(identities[1]), "TOKEN_TRAIN_EVAL_OVERLAP")
    return splits[0], splits[1]


def verify_prepared_dataset(observed, expected):
    """Fail if the pinned trainer changes the already-checked model inputs."""
    _require(len(observed) == len(expected), "TRAINER_INPUT_DRIFT")
    for index, expected_row in enumerate(expected):
        _require(observed[index] == expected_row, "TRAINER_INPUT_DRIFT")


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_adapter_config(path, manifest):
    """Replace PEFT's local snapshot reference with the admitted immutable base."""
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "ADAPTER_CONFIG_INVALID")
    _require(0 < path.stat().st_size <= MAX_ADAPTER_CONFIG_BYTES,
             "ADAPTER_CONFIG_INVALID")
    with path.open("rb") as stream:
        raw = stream.read(MAX_ADAPTER_CONFIG_BYTES + 1)
    _require(0 < len(raw) <= MAX_ADAPTER_CONFIG_BYTES, "ADAPTER_CONFIG_INVALID")
    config = parse_json(raw)
    _require(type(config) is dict, "ADAPTER_CONFIG_INVALID")
    config["base_model_name_or_path"] = manifest["base_model"]["repo_id"]
    config["revision"] = manifest["base_model"]["revision"]
    normalized = canonical_bytes(config)
    _require(len(normalized) <= MAX_ADAPTER_CONFIG_BYTES, "ADAPTER_CONFIG_INVALID")
    temporary = path.with_name(".adapter_config.normalized.json")
    with temporary.open("xb") as stream:
        stream.write(normalized)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    with path.open("rb") as stream:
        readback = stream.read(MAX_ADAPTER_CONFIG_BYTES + 1)
    observed = parse_json(readback)
    _require(
        observed == config
        and type(observed.get("base_model_name_or_path")) is str
        and observed["base_model_name_or_path"] == manifest["base_model"]["repo_id"]
        and type(observed.get("revision")) is str
        and observed["revision"] == manifest["base_model"]["revision"],
        "ADAPTER_CONFIG_BINDING_MISMATCH",
    )
    return observed


def run_training(manifest, backend, *, worker_path, source_revision, reservation_commit):
    """Injected backend is for offline contract tests; CLI always uses HubBackend."""
    manifest = validate_manifest(manifest)
    _require(source_revision == manifest["source"]["revision"], "SOURCE_REVISION_MISMATCH")
    _require(not Path(worker_path).is_symlink(), "WORKER_HASH_MISMATCH")
    _require(_file_hash(Path(worker_path)) == manifest["source"]["worker_sha256"], "WORKER_HASH_MISMATCH")
    _revision(reservation_commit)
    _require(reservation_commit != manifest["output"]["parent_commit"], "RESERVATION_INVALID")
    backend.check_versions(manifest["runtime"]["dependencies"])
    reservation = parse_json(backend.reservation_bytes(manifest, reservation_commit))
    _require(reservation == {
        "schema_version": "szl.training.reservation.v1", "run_id": manifest["run_id"],
        "manifest_sha256": canonical_sha256(manifest), "source_revision": source_revision,
    }, "RESERVATION_INVALID")
    _require(backend.output_head(manifest) == reservation_commit, "OUTPUT_PARENT_MISMATCH")
    train, evaluation = validate_dataset_records(manifest, backend.dataset_bytes(manifest, "train"),
                                                 backend.dataset_bytes(manifest, "eval"))
    with tempfile.TemporaryDirectory(prefix="szl-receipt-training-") as temporary:
        directory = Path(temporary)
        artifact_dir = directory / "artifacts"
        artifact_dir.mkdir()
        metrics = backend.train(manifest, train, evaluation, artifact_dir)
        measured = validate_metrics(metrics, manifest["evaluation"]["max_eval_loss"])
        files = {}
        for path in artifact_dir.iterdir():
            _require(path.name in ARTIFACT_NAMES and path.is_file() and not path.is_symlink(), "ARTIFACT_INVALID")
            _require(0 < path.stat().st_size <= 512 * 1024**2, "ARTIFACT_SIZE_INVALID")
            files[path.name] = path
        _require({"adapter_model.safetensors", "adapter_config.json"} <= set(files), "ARTIFACTS_MISSING")
        for name, content in (("manifest.json", manifest), ("evaluation.json", measured)):
            path = directory / name
            path.write_bytes(canonical_bytes(content))
            files[name] = path
        artifacts = {"files": [{"path": name, "sha256": _file_hash(path), "size_bytes": path.stat().st_size}
                                for name, path in sorted(files.items())]}
        prefix = "candidates/" + manifest["run_id"] + "/"
        receipt = {
            "schema_version": "szl.training.receipt.v1", "status": "CANDIDATE_EVALUATED",
            "run_id": manifest["run_id"], "profile": manifest["profile"], "source": manifest["source"],
            "manifest_sha256": canonical_sha256(manifest),
            "output": {**manifest["output"], "reservation_commit": reservation_commit, "prefix": prefix},
            "evaluation": measured,
            "artifacts_sha256": canonical_sha256(artifacts),
            "authority": "OPERATOR_SUPPLIED_UNVERIFIED", "promotion": "NOT_GRANTED",
        }
        for name, content in (("artifacts.json", artifacts), ("receipt.json", receipt)):
            path = directory / name
            path.write_bytes(canonical_bytes(content))
            files[name] = path
        _require(backend.output_head(manifest) == reservation_commit, "OUTPUT_PARENT_MISMATCH")
        try:
            commit = backend.publish(manifest, {prefix + name: path for name, path in files.items()},
                                     reservation_commit)
        except Exception:
            raise ValueError("CANDIDATE_PUBLICATION_OUTCOME_UNKNOWN") from None
        _require(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
                 "CANDIDATE_PUBLICATION_OUTCOME_UNKNOWN")
        _require(commit not in (manifest["output"]["parent_commit"], reservation_commit),
                 "CANDIDATE_PUBLICATION_OUTCOME_UNKNOWN")
        return {
            "schema_version": "szl.training.worker-result.v1", "status": "CANDIDATE_PUBLISHED",
            "run_id": manifest["run_id"], "manifest_sha256": canonical_sha256(manifest),
            "output_repo": manifest["output"]["repo_id"], "commit": commit,
            "receipt_path": prefix + "receipt.json", "receipt_sha256": canonical_sha256(receipt),
        }


class HubBackend:
    """Actual provider adapter. Constructed only by the executable entry point."""

    def __init__(self):
        self.api = None

    def check_versions(self, dependencies):
        try:
            versions = {name: importlib.metadata.version(name) for name in DEPENDENCIES}
        except importlib.metadata.PackageNotFoundError:
            raise ValueError("DEPENDENCY_MISMATCH") from None
        _require(versions == dependencies, "DEPENDENCY_MISMATCH")
        _require(bool(os.environ.get("HF_TOKEN")), "TOKEN_MISSING")
        from huggingface_hub import HfApi
        self.api = HfApi(endpoint="https://huggingface.co", token=os.environ["HF_TOKEN"])

    def output_head(self, manifest):
        return self.api.model_info(manifest["output"]["repo_id"], revision="main").sha

    def _read_file(self, repo_id, revision, name, max_bytes, repo_type):
        from huggingface_hub import hf_hub_download
        info = self.api.get_paths_info(repo_id, [name], revision=revision, repo_type=repo_type)
        _require(len(info) == 1 and getattr(info[0], "path", None) == name, "DATA_FILE_MISSING")
        size = getattr(info[0], "size", None)
        _require(type(size) is int and 0 < size <= max_bytes, "DATA_SIZE_INVALID")
        path = hf_hub_download(repo_id, name, repo_type=repo_type, revision=revision,
                               endpoint="https://huggingface.co", token=os.environ["HF_TOKEN"])
        with open(path, "rb") as stream:
            raw = stream.read(max_bytes + 1)
        _require(len(raw) == size, "DATA_SIZE_INVALID")
        return raw

    def reservation_bytes(self, manifest, reservation_commit):
        return self._read_file(manifest["output"]["repo_id"], reservation_commit,
                               ".training-reservations/" + manifest["run_id"] + ".json",
                               MAX_MANIFEST_BYTES, "model")

    def dataset_bytes(self, manifest, split):
        data = manifest["dataset"]
        return self._read_file(data["repo_id"], data["revision"], data[split + "_file"],
                               data["max_file_bytes"], "dataset")

    def train(self, manifest, train, evaluation, artifact_dir):
        # Keep metrics local. No Trackio server, Space, Bucket, or Dataset creation.
        for name in tuple(os.environ):
            if name.startswith("TRACKIO_"):
                os.environ.pop(name)
        os.environ["TRACKIO_DIR"] = str(artifact_dir.parent / "trackio")
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        import torch
        import trackio
        from datasets import Dataset
        from huggingface_hub import snapshot_download
        from peft import LoraConfig
        from safetensors import safe_open
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback, set_seed
        from trl import SFTConfig, SFTTrainer

        hyper = manifest["hyperparameters"]
        _require(torch.cuda.is_available(), "GPU_UNAVAILABLE")
        if hyper["precision"] == "bf16":
            _require(torch.cuda.is_bf16_supported(), "PRECISION_UNAVAILABLE")
        set_seed(hyper["seed"])
        model_dir = snapshot_download(
            manifest["base_model"]["repo_id"], revision=manifest["base_model"]["revision"],
            endpoint="https://huggingface.co", token=os.environ["HF_TOKEN"],
            allow_patterns=["*.safetensors", "*.json", "tokenizer.model", "vocab.txt", "merges.txt"],
            ignore_patterns=["*.py", "*.bin", "*.pkl", "*.pt", "*.pth"],
        )
        tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
        if tokenizer.pad_token is None:
            _require(tokenizer.eos_token is not None, "TOKENIZER_INVALID")
            tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "right"
        token_train, token_eval = prepare_tokenized_splits(tokenizer, train, evaluation, hyper["max_seq"])
        dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[hyper["precision"]]
        model = AutoModelForCausalLM.from_pretrained(model_dir, local_files_only=True,
                                                    trust_remote_code=False, use_safetensors=True,
                                                    torch_dtype=dtype)

        class LocalMetrics(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                selected = {}
                for key in ("loss", "grad_norm", "learning_rate", "eval_loss"):
                    if logs and key in logs:
                        value = logs[key]
                        _require(type(value) in (int, float) and math.isfinite(value), "LOSS_INVALID")
                        selected[key] = value
                if selected:
                    trackio.log(selected, step=state.global_step)

        trackio.init(project="szl-receipt-training", name=manifest["run_id"], space_id=None,
                     config={"manifest_sha256": canonical_sha256(manifest)})
        try:
            trainer = SFTTrainer(
                model=model, processing_class=tokenizer,
                train_dataset=Dataset.from_list(token_train), eval_dataset=Dataset.from_list(token_eval),
                peft_config=LoraConfig(r=hyper["r"], lora_alpha=hyper["lora_alpha"],
                                       lora_dropout=hyper["lora_dropout"], bias="none", task_type="CAUSAL_LM",
                                       target_modules=hyper["target_modules"]),
                args=SFTConfig(
                    output_dir=str(artifact_dir.parent / "checkpoints"),
                    seed=hyper["seed"], data_seed=hyper["seed"], learning_rate=hyper["lr"],
                    max_steps=hyper["max_steps"], max_length=hyper["max_seq"],
                    per_device_train_batch_size=hyper["batch_size"],
                    per_device_eval_batch_size=hyper["batch_size"],
                    gradient_accumulation_steps=hyper["gradient_accumulation_steps"],
                    weight_decay=hyper["weight_decay"], warmup_ratio=hyper["warmup_ratio"],
                    bf16=hyper["precision"] == "bf16", fp16=hyper["precision"] == "fp16",
                    optim="adamw_torch", lr_scheduler_type="linear", dataset_text_field="text",
                    dataset_kwargs={"skip_prepare_dataset": True},
                    packing=False, eval_packing=False, padding_free=False,
                    completion_only_loss=False, assistant_only_loss=False,
                    save_strategy="no", eval_strategy="no", logging_steps=1,
                    logging_nan_inf_filter=False, report_to="none", disable_tqdm=True,
                    push_to_hub=False, save_safetensors=True,
                ), callbacks=[LocalMetrics()],
            )
            verify_prepared_dataset(trainer.train_dataset, token_train)
            verify_prepared_dataset(trainer.eval_dataset, token_eval)
            trained = trainer.train()
            metrics = {"train_loss": trained.training_loss, "eval_loss": trainer.evaluate()["eval_loss"]}
            validate_metrics(metrics, manifest["evaluation"]["max_eval_loss"])
            _require(trainer.state.global_step == hyper["max_steps"], "TRAINING_STEPS_MISMATCH")
            trackio.log(metrics, step=trainer.state.global_step)
            trainer.model.save_pretrained(str(artifact_dir), safe_serialization=True)
            normalize_adapter_config(artifact_dir / "adapter_config.json", manifest)
            tokenizer.save_pretrained(str(artifact_dir))
            # PEFT writes a generated README; it is not part of the candidate contract.
            generated_card = artifact_dir / "README.md"
            if generated_card.exists():
                generated_card.unlink()
            with safe_open(str(artifact_dir / "adapter_model.safetensors"), framework="pt") as weights:
                _require(bool(list(weights.keys())), "ARTIFACTS_MISSING")
            return metrics
        finally:
            trackio.finish()

    def publish(self, manifest, files, reservation_commit):
        from huggingface_hub import CommitOperationAdd
        # Refuse reusing a prior run prefix, even when the caller supplies its new head.
        prefix = "candidates/" + manifest["run_id"]
        existing = self.api.get_paths_info(manifest["output"]["repo_id"], [prefix],
                                           revision=reservation_commit, repo_type="model")
        _require(not existing, "CANDIDATE_ALREADY_EXISTS")
        commit = self.api.create_commit(
            repo_id=manifest["output"]["repo_id"], repo_type="model", revision="main",
            parent_commit=reservation_commit, create_pr=False,
            operations=[CommitOperationAdd(path_in_repo=name, path_or_fileobj=path)
                        for name, path in sorted(files.items())],
            commit_message="Add evaluated candidate " + manifest["run_id"],
        )
        return commit.oid


def main():
    try:
        raw = os.environ.get("TRAINING_MANIFEST_JSON", "")
        _require(0 < len(raw.encode("utf-8")) <= MAX_MANIFEST_BYTES, "MANIFEST_MISSING_OR_OVERSIZE")
        manifest = validate_manifest(parse_json(raw))
        # Dependencies may emit unexpected details: only the final envelope is logged.
        with open(os.devnull, "w", encoding="utf-8") as quiet:
            with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                result = run_training(manifest, HubBackend(), worker_path=__file__,
                                      source_revision=os.environ.get("TRAINING_SOURCE_REVISION", ""),
                                      reservation_commit=os.environ.get("TRAINING_RESERVATION_COMMIT", ""))
    except Exception:
        print("SZL_TRAINING_RESULT=" + json.dumps({"schema_version": "szl.training.worker-result.v1", "status": "FAILED",
                          "error": "TRAINING_FAILED_REQUIRES_RECEIPT_READBACK", "promotion": "NOT_GRANTED"}))
        return 1
    print("SZL_TRAINING_RESULT=" + json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
