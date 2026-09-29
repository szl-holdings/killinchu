"""Fail-closed contract for irreversible legacy Space retirement."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "retire_legacy_resilience_spaces.py"
WORKFLOW = ROOT / ".github" / "workflows" / "retire-legacy-resilience-spaces.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("retire_resilience", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deletion_allowlist_is_exact_and_live_spaces_are_guarded_by_state() -> None:
    module = load_module()
    assert module.RETIREMENT_TARGETS == {
        "SZLHOLDINGS/vessels": "/vessels",
        "SZLHOLDINGS/aegis-assurance": "/resilience",
    }
    # Live Spaces are protected by their runtime stage, not by a typed list of
    # names that drifts from the Hub.
    assert not hasattr(module, "PROTECTED_MIGRATIONS")
    assert module.DELETABLE_STAGES == {
        "PAUSED",
        "STOPPED",
        "BUILD_ERROR",
        "RUNTIME_ERROR",
        "CONFIG_ERROR",
        "NO_APP_FILE",
    }
    assert module.KILLINCHU_SPACE == "SZLHOLDINGS/killinchu"


def test_script_has_no_arbitrary_repository_selector() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    argument_literals = {
        arg.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for arg in node.args[:1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    }
    assert "--repo-id" not in argument_literals
    assert "--space-id" not in argument_literals
    assert "--target" not in argument_literals
    assert "delete_repo(" in source
    assert "repo_id=repo_id" in source
    assert "for repo_id, replacement_route in RETIREMENT_TARGETS.items()" in source


def test_source_snapshot_secrets_and_storage_precede_deletion() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    body = source.split("def retire_targets(", 1)[1]
    stage = body.index("require_not_serving(repo_id, runtime)")
    secrets = body.index("fetch_secret_key_metadata(repo_id, token)")
    storage = body.index("_runtime_storage(runtime)")
    snapshot = body.index("snapshot_space(repo_id, token, archive_root)")
    recheck = body.index("repo_id, api.get_space_runtime(repo_id=repo_id)")
    deletion = body.index("api.delete_repo(")
    absence = body.index("if not api.repo_exists(repo_id=repo_id, repo_type=\"space\")")
    assert stage < secrets < storage < snapshot < recheck < deletion < absence
    assert "refusing to delete an unsnapshotted Space" in source
    assert "Space secret metadata is not empty" in source
    assert "persistent storage is present" in source


def test_replacement_proof_is_same_origin_and_source_bound() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        'KILLINCHU_ORIGIN + "/api/build-info"',
        "revision == source_sha",
        "allow_redirects=True",
        "final.netloc != expected_host",
        "replacement route escaped Killinchu origin",
        '"body_sha256"',
        '"SZLHOLDINGS/vessels": "/vessels"',
        '"SZLHOLDINGS/aegis-assurance": "/resilience"',
    ):
        assert marker in source


def test_policy_proof_blocks_space_recreation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        'PUBLIC_FLAGSHIP_SLUGS',
        '("terra", "sentra", "counsel", "finance", "lyte")',
        'FOLDED_INTO_KILLINCHU',
        '("vessels",)',
        'RETIRED_SPACE_IDS = frozenset({"SZLHOLDINGS/aegis-assurance"})',
        "legacy Space remains in active keeper set",
        "Packet 8 can still recreate Aegis assurance",
    ):
        assert marker in source


def test_workflow_requires_explicit_manual_retirement_at_exact_main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert trigger.count("  workflow_dispatch:") == 1
    for forbidden in ("workflow_run:", "push:", "pull_request:", "schedule:", "repository_dispatch:"):
        assert forbidden not in trigger
    assert "type: boolean\n        required: true\n        default: false" in trigger
    assert "expected_source_sha:" in trigger
    assert "type: string\n        required: true" in trigger
    condition = text.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
    assert " ".join(condition.split()) == (
        "github.event_name == 'workflow_dispatch' && "
        "github.ref == 'refs/heads/main' && "
        "inputs.confirm_retirement == true && "
        "inputs.expected_source_sha == github.sha"
    )
    for marker in (
        "SOURCE_SHA: ${{ github.sha }}",
        "ref: ${{ env.SOURCE_SHA }}",
        'test "$current_main" = "$SOURCE_SHA"',
        "repository: szl-holdings/a11oy",
        "scripts/retire_legacy_resilience_spaces.py",
        "--require-hashes --only-binary=:all:",
        "hf-legacy-resilience-retirement-${{ github.run_id }}",
    ):
        assert marker in text
    assert "environment:" not in text
    assert "delete_repo" not in text

def test_v8_topology_keeps_sentra_public_and_only_vessels_folded() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'public != ("terra", "sentra", "counsel", "finance", "lyte")' in source
    assert 'folded != ("vessels",)' in source
    assert '"SZLHOLDINGS/vessels": "/vessels"' in source
    # The deleter names no live Space id at all.
    for live in ("SZLHOLDINGS/sentra", "SZLHOLDINGS/immune", "SZLHOLDINGS/immune-lattice"):
        assert f'"{live}"' not in source


class FakeHubApi:
    """Offline stand-in for ``huggingface_hub.HfApi``; records every call."""

    def __init__(self, stages: list[object]) -> None:
        self.stages = list(stages)
        self.calls: list[str] = []
        self.deleted: list[str] = []

    def repo_exists(self, repo_id: str, repo_type: str) -> bool:
        self.calls.append(f"repo_exists:{repo_id}")
        return repo_id not in self.deleted

    def get_space_runtime(self, repo_id: str) -> SimpleNamespace:
        self.calls.append(f"get_space_runtime:{repo_id}")
        stage = self.stages.pop(0) if len(self.stages) > 1 else self.stages[0]
        return SimpleNamespace(stage=stage, storage=None)

    def space_info(self, repo_id: str) -> SimpleNamespace:
        self.calls.append(f"space_info:{repo_id}")
        return SimpleNamespace(sha="a" * 40, private=False)

    def delete_repo(self, repo_id: str, repo_type: str, missing_ok: bool) -> None:
        self.calls.append(f"delete_repo:{repo_id}")
        self.deleted.append(repo_id)


def _install_fake_hub(monkeypatch, module, api: FakeHubApi) -> list[str]:
    snapshots: list[str] = []
    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(HfApi=lambda token: api)
    )
    monkeypatch.setattr(module, "fetch_secret_key_metadata", lambda repo_id, token: [])

    def fake_snapshot(repo_id, token, archive_root):
        snapshots.append(repo_id)
        return {"archive_sha256": "0" * 64}

    monkeypatch.setattr(module, "snapshot_space", fake_snapshot)
    return snapshots


class _Stage(str):
    """Mimics huggingface_hub's ``SpaceStage`` str-enum (``.value``)."""

    @property
    def value(self) -> str:
        return str(self)


@pytest.mark.parametrize(
    "stage",
    [
        "RUNNING",
        _Stage("RUNNING"),
        "running",
        "RUNNING_BUILDING",
        "RUNNING_APP_STARTING",
        "APP_STARTING",
        "BUILDING",
        "SLEEPING",
        "SOME_FUTURE_STAGE",
        None,
        "",
    ],
)
def test_retire_refuses_a_running_or_unknown_space_before_any_other_call(
    monkeypatch, tmp_path, stage
) -> None:
    module = load_module()
    api = FakeHubApi([stage])
    snapshots = _install_fake_hub(monkeypatch, module, api)

    with pytest.raises(
        RuntimeError,
        match="refusing to delete SZLHOLDINGS/vessels; live runtime stage",
    ):
        module.retire_targets("synthetic-token", tmp_path, dry_run=False)

    # Refused on the runtime read: no metadata, snapshot or delete call happened.
    assert api.calls == [
        "repo_exists:SZLHOLDINGS/vessels",
        "get_space_runtime:SZLHOLDINGS/vessels",
    ]
    assert snapshots == []
    assert api.deleted == []


def test_retire_refuses_a_space_restarted_during_the_snapshot(monkeypatch, tmp_path) -> None:
    module = load_module()
    # PAUSED when first read, RUNNING again at the pre-delete re-check.
    api = FakeHubApi(["PAUSED", "RUNNING"])
    snapshots = _install_fake_hub(monkeypatch, module, api)

    with pytest.raises(RuntimeError, match="live runtime stage is RUNNING"):
        module.retire_targets("synthetic-token", tmp_path, dry_run=False)

    assert snapshots == ["SZLHOLDINGS/vessels"]
    assert api.deleted == []


def test_retire_only_deletes_an_idle_space(monkeypatch, tmp_path) -> None:
    module = load_module()
    api = FakeHubApi(["PAUSED"])
    _install_fake_hub(monkeypatch, module, api)

    results = module.retire_targets("synthetic-token", tmp_path, dry_run=False)

    assert [row["state"] for row in results] == ["DELETED_VERIFIED", "DELETED_VERIFIED"]
    assert all(row["runtime_stage_before"] == "PAUSED" for row in results)
    assert all(row["runtime_stage_at_delete"] == "PAUSED" for row in results)
    assert api.deleted == list(module.RETIREMENT_TARGETS)


def test_retire_dry_run_on_running_space_is_also_refused(monkeypatch, tmp_path) -> None:
    module = load_module()
    api = FakeHubApi(["RUNNING"])
    snapshots = _install_fake_hub(monkeypatch, module, api)

    with pytest.raises(RuntimeError, match="live runtime stage is RUNNING"):
        module.retire_targets("synthetic-token", tmp_path, dry_run=True)
    assert snapshots == []
    assert api.deleted == []


def test_absent_legacy_space_is_reported_without_runtime_or_delete_calls(
    monkeypatch, tmp_path
) -> None:
    module = load_module()
    api = FakeHubApi(["RUNNING"])
    api.deleted = list(module.RETIREMENT_TARGETS)
    _install_fake_hub(monkeypatch, module, api)

    results = module.retire_targets("synthetic-token", tmp_path, dry_run=False)

    assert [row["state"] for row in results] == ["ABSENT_ALREADY", "ABSENT_ALREADY"]
    assert all(call.startswith("repo_exists:") for call in api.calls)
