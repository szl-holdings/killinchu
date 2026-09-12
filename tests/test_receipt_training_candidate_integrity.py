"""Offline candidate-container and immutable Hub-tree integrity contracts."""

import copy
import json
import socket
import sys
from types import ModuleType, SimpleNamespace

import pytest

from scripts import dispatch_receipt_training as dispatcher
from scripts.receipt_training_worker import canonical_bytes
from tests.test_receipt_training_dispatch import (
    bound_adapter_config,
    minimal_safetensors_bytes,
)
from tests.test_receipt_training_worker import COMMIT, RESERVATION, make_manifest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def rejected(*args, **kwargs):
        raise AssertionError("NETWORK_FORBIDDEN_IN_OFFLINE_CONTRACT_TEST")

    monkeypatch.setattr(socket.socket, "connect", rejected)
    monkeypatch.setattr(socket.socket, "connect_ex", rejected)
    monkeypatch.setattr(socket, "create_connection", rejected)


def safetensors(header, payload=b"\0\0\0\0"):
    encoded = canonical_bytes(header)
    return len(encoded).to_bytes(8, "little") + encoded + payload


def test_minimal_real_tensor_safetensors_is_structurally_admitted():
    dispatcher.validate_safetensors_adapter(minimal_safetensors_bytes())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\x80\x04pickle",
        (0).to_bytes(8, "little") + b"{}",
        (1000).to_bytes(8, "little") + b"{}",
        (2).to_bytes(8, "little") + b"[]" + b"data",
        safetensors({"__metadata__": {"producer": "test"}}),
        safetensors({"__metadata__": None}),
        safetensors(
            {
                "tensor": {
                    "dtype": "F32",
                    "shape": [1],
                    "data_offsets": [0, 4],
                }
            },
            b"\0\0\0\0hidden",
        ),
    ],
)
def test_safetensors_rejects_non_container_pickle_empty_and_hidden_payload(raw):
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.validate_safetensors_adapter(raw)


def test_safetensors_header_rejects_duplicate_tensor_keys():
    header = (
        b'{"tensor":{"dtype":"F32","shape":[1],"data_offsets":[0,4]},'
        b'"tensor":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}'
    )
    raw = len(header).to_bytes(8, "little") + header + b"\0" * 4
    with pytest.raises(
        dispatcher.DispatchError, match="SAFETENSORS_HEADER_INVALID"
    ):
        dispatcher.validate_safetensors_adapter(raw)


@pytest.mark.parametrize(
    "tensor,payload",
    [
        ({"dtype": "F64", "shape": [1], "data_offsets": [0, 8]}, b"\0" * 8),
        ({"dtype": "F32", "shape": [True], "data_offsets": [0, 4]}, b"\0" * 4),
        ({"dtype": "F32", "shape": [2], "data_offsets": [0, 4]}, b"\0" * 4),
        ({"dtype": "F32", "shape": [1], "data_offsets": [0, 5]}, b"\0" * 5),
        ({"dtype": "F32", "shape": [1], "data_offsets": [-1, 3]}, b"\0" * 4),
        ({"dtype": "F32", "shape": [1], "data_offsets": [0, True]}, b"\0" * 4),
        ({"dtype": "F32", "shape": [0], "data_offsets": [0, 4]}, b"\0" * 4),
    ],
)
def test_safetensors_rejects_invalid_dtype_shape_and_offsets(tensor, payload):
    with pytest.raises(dispatcher.DispatchError):
        dispatcher.validate_safetensors_adapter(safetensors({"tensor": tensor}, payload))


def test_safetensors_rejects_overlapping_tensor_ranges():
    header = {
        "one": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
        "two": {"dtype": "F32", "shape": [1], "data_offsets": [2, 6]},
    }
    with pytest.raises(dispatcher.DispatchError, match="SAFETENSORS_OFFSET_INVALID"):
        dispatcher.validate_safetensors_adapter(safetensors(header, b"\0" * 6))


def test_adapter_config_accepts_benign_extra_peft_metadata():
    manifest = make_manifest()
    config = json.loads(bound_adapter_config(manifest))
    config.update({"auto_mapping": None, "inference_mode": True})
    dispatcher.validate_adapter_config(canonical_bytes(config), manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("peft_type", "PROMPT_TUNING"),
        ("task_type", "SEQ_2_SEQ_LM"),
        ("bias", "all"),
        ("r", True),
        ("r", 999),
        ("lora_alpha", 3.0),
        ("lora_alpha", 999),
        ("lora_dropout", False),
        ("lora_dropout", 0.49),
        ("target_modules", "q_proj"),
        ("target_modules", ["q_proj", "q_proj"]),
        ("target_modules", ["k_proj"]),
        ("base_model_name_or_path", "other/base"),
        ("base_model_name_or_path", "C:/local/snapshot"),
        ("base_model_name_or_path", None),
        ("revision", "main"),
        ("revision", None),
    ],
)
def test_adapter_config_must_exactly_bind_admitted_lora(field, value):
    manifest = make_manifest()
    config = json.loads(bound_adapter_config(manifest))
    config[field] = value
    with pytest.raises(
        dispatcher.DispatchError, match="ADAPTER_CONFIG_BINDING_MISMATCH"
    ):
        dispatcher.validate_adapter_config(canonical_bytes(config), manifest)


def test_adapter_config_rejects_duplicate_json_keys():
    manifest = make_manifest()
    raw = b'{"peft_type":"LORA","peft_type":"PROMPT_TUNING"}'
    with pytest.raises(dispatcher.DispatchError, match="ADAPTER_CONFIG_INVALID"):
        dispatcher.validate_adapter_config(raw, manifest)


class RepoFile:
    def __init__(self, path, size=4, oid="a" * 40, lfs=None):
        self.path = path
        self.size = size
        self.blob_id = oid
        self.lfs = lfs


class RepoFolder:
    def __init__(self, path, oid="b" * 40):
        self.path = path
        self.tree_id = oid


class BlobLfsInfo:
    def __init__(self, *, size, sha256, pointer_size=128):
        self.size = size
        self.sha256 = sha256
        self.pointer_size = pointer_size


class FakeTreeApi:
    def __init__(self, reservation_tree, candidate_tree, head=COMMIT):
        self.trees = {RESERVATION: reservation_tree, COMMIT: candidate_tree}
        self.head = head
        self.calls = []
        self.yielded = []

    def model_info(self, repo, revision):
        self.calls.append(("model_info", repo, revision))
        sha = self.head.pop(0) if type(self.head) is list else self.head
        return SimpleNamespace(sha=sha)

    def list_repo_tree(self, repo, **kwargs):
        self.calls.append(("list_repo_tree", repo, kwargs))
        revision = kwargs["revision"]

        def iterator():
            for entry in self.trees[revision]:
                self.yielded.append((revision, entry.path))
                yield entry

        return iterator()


def tree_entries(manifest):
    prefix = f"candidates/{manifest['run_id']}/"
    artifacts = {
        "adapter_model.safetensors",
        "adapter_config.json",
        "manifest.json",
        "evaluation.json",
    }
    old = [
        RepoFolder("existing"),
        RepoFile("README.md", size=10, oid="c" * 40),
        RepoFile(
            f".training-reservations/{manifest['run_id']}.json",
            size=128,
            oid="d" * 40,
        ),
        RepoFile(
            "existing/model.safetensors",
            size=1024,
            oid="e" * 40,
            lfs=BlobLfsInfo(size=1024, sha256="f" * 64),
        ),
    ]
    additions = [
        RepoFile(prefix + path, size=index + 1, oid=(str(index + 1) * 40)[:40])
        for index, path in enumerate(sorted(artifacts | {"artifacts.json", "receipt.json"}))
    ]
    return old, old + [RepoFolder(prefix[:-1], oid="9" * 40)] + additions, artifacts


@pytest.fixture
def fake_hf_api_module(monkeypatch):
    package = ModuleType("huggingface_hub")
    package.__path__ = []
    module = ModuleType("huggingface_hub.hf_api")
    module.RepoFile = RepoFile
    module.RepoFolder = RepoFolder
    module.BlobLfsInfo = BlobLfsInfo
    monkeypatch.setitem(sys.modules, "huggingface_hub", package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.hf_api", module)


def make_tree_provider(api):
    provider = dispatcher.HFProvider.__new__(dispatcher.HFProvider)
    provider.api = api
    provider.token = "offline-synthetic-token"
    return provider


def test_full_tree_delta_materializes_both_revisions_and_accepts_exact_closure(
    fake_hf_api_module,
):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    api = FakeTreeApi(reservation_tree, candidate_tree)
    make_tree_provider(api).verify_candidate_tree_delta(
        manifest, RESERVATION, COMMIT, artifacts
    )
    tree_calls = [call for call in api.calls if call[0] == "list_repo_tree"]
    assert [call[2]["revision"] for call in tree_calls] == [RESERVATION, COMMIT]
    assert all(call[2]["recursive"] is True for call in tree_calls)
    assert all(call[2]["expand"] is False for call in tree_calls)
    assert all(call[2]["repo_type"] == "model" for call in tree_calls)
    assert len(api.yielded) == len(reservation_tree) + len(candidate_tree)


def test_candidate_must_be_current_output_main_before_tree_reads(fake_hf_api_module):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    api = FakeTreeApi(reservation_tree, candidate_tree, head="8" * 40)
    with pytest.raises(dispatcher.DispatchError, match="CANDIDATE_NOT_CURRENT_MAIN"):
        make_tree_provider(api).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )
    assert all(call[0] != "list_repo_tree" for call in api.calls)


def test_output_main_drift_during_tree_read_fails_closed(fake_hf_api_module):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    api = FakeTreeApi(reservation_tree, candidate_tree, head=[COMMIT, "8" * 40])
    with pytest.raises(dispatcher.DispatchError, match="CANDIDATE_NOT_CURRENT_MAIN"):
        make_tree_provider(api).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )
    assert len([call for call in api.calls if call[0] == "list_repo_tree"]) == 2


@pytest.mark.parametrize(
    "mutation",
    ["delete", "size", "blob", "lfs_sha", "lfs_size"],
)
def test_reservation_tree_files_must_remain_byte_identical(
    fake_hf_api_module, mutation
):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    candidate_tree = copy.deepcopy(candidate_tree)
    if mutation == "delete":
        candidate_tree = [entry for entry in candidate_tree if entry.path != "README.md"]
    elif mutation == "size":
        next(entry for entry in candidate_tree if entry.path == "README.md").size += 1
    elif mutation == "blob":
        next(entry for entry in candidate_tree if entry.path == "README.md").blob_id = "8" * 40
    elif mutation == "lfs_sha":
        next(entry for entry in candidate_tree if entry.path == "existing/model.safetensors").lfs.sha256 = "8" * 64
    else:
        next(entry for entry in candidate_tree if entry.path == "existing/model.safetensors").lfs.size += 1
    api = FakeTreeApi(reservation_tree, candidate_tree)
    with pytest.raises(dispatcher.DispatchError, match="RESERVATION_TREE_CHANGED"):
        make_tree_provider(api).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )


@pytest.mark.parametrize("mutation", ["outside_addition", "missing", "extra_candidate"])
def test_candidate_tree_allows_exact_declared_additions_only(
    fake_hf_api_module, mutation
):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    candidate_tree = list(candidate_tree)
    prefix = f"candidates/{manifest['run_id']}/"
    if mutation == "outside_addition":
        candidate_tree.append(RepoFile("unrelated.bin", oid="7" * 40))
    elif mutation == "missing":
        candidate_tree = [
            entry for entry in candidate_tree
            if entry.path != prefix + "adapter_config.json"
        ]
    else:
        candidate_tree.append(RepoFile(prefix + "undeclared.bin", oid="7" * 40))
    with pytest.raises(dispatcher.DispatchError, match="CANDIDATE_TREE_DELTA_INVALID"):
        make_tree_provider(FakeTreeApi(reservation_tree, candidate_tree)).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )


def test_candidate_prefix_must_be_absent_at_reservation(fake_hf_api_module):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    reservation_tree.append(
        RepoFile(f"candidates/{manifest['run_id']}/old.json", oid="7" * 40)
    )
    candidate_tree.append(copy.deepcopy(reservation_tree[-1]))
    with pytest.raises(
        dispatcher.DispatchError, match="CANDIDATE_PREFIX_ALREADY_PRESENT"
    ):
        make_tree_provider(FakeTreeApi(reservation_tree, candidate_tree)).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )


@pytest.mark.parametrize("mutation", ["duplicate", "invalid_path", "unexpected"])
def test_tree_snapshot_rejects_ambiguous_or_unexpected_sdk_entries(
    fake_hf_api_module, mutation
):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    if mutation == "duplicate":
        reservation_tree.append(RepoFile("README.md", oid="7" * 40))
    elif mutation == "invalid_path":
        reservation_tree.append(RepoFile("../escape", oid="7" * 40))
    else:
        reservation_tree.append(SimpleNamespace(path="unexpected"))
    with pytest.raises(dispatcher.DispatchError):
        make_tree_provider(FakeTreeApi(reservation_tree, candidate_tree)).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )


def test_tree_caps_entries_and_total_path_bytes(fake_hf_api_module, monkeypatch):
    manifest = make_manifest()
    reservation_tree, candidate_tree, artifacts = tree_entries(manifest)
    monkeypatch.setattr(dispatcher, "MAX_REPO_TREE_ENTRIES", 2)
    with pytest.raises(
        dispatcher.DispatchError, match="REPO_TREE_ENTRY_LIMIT_EXCEEDED"
    ):
        make_tree_provider(FakeTreeApi(reservation_tree, candidate_tree)).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )
    monkeypatch.setattr(dispatcher, "MAX_REPO_TREE_ENTRIES", 20_000)
    monkeypatch.setattr(dispatcher, "MAX_REPO_TREE_PATH_BYTES", 5)
    with pytest.raises(
        dispatcher.DispatchError, match="REPO_TREE_PATH_LIMIT_EXCEEDED"
    ):
        make_tree_provider(FakeTreeApi(reservation_tree, candidate_tree)).verify_candidate_tree_delta(
            manifest, RESERVATION, COMMIT, artifacts
        )


def test_production_runtime_approval_stays_fail_closed():
    assert dict(dispatcher.APPROVED_RUNTIMES) == {}
