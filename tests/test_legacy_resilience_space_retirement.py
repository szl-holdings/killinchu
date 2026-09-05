"""Fail-closed contract for irreversible legacy Space retirement."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "retire_legacy_resilience_spaces.py"
WORKFLOW = ROOT / ".github" / "workflows" / "retire-legacy-resilience-spaces.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("retire_resilience", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deletion_allowlist_is_exact_and_excludes_live_migrations() -> None:
    module = load_module()
    assert module.RETIREMENT_TARGETS == {
        "SZLHOLDINGS/vessels": "/vessels",
        "SZLHOLDINGS/aegis-assurance": "/resilience",
    }
    assert module.PROTECTED_MIGRATIONS == {
        "SZLHOLDINGS/sentra",
        "SZLHOLDINGS/immune",
        "SZLHOLDINGS/immune-lattice",
    }
    assert not set(module.RETIREMENT_TARGETS) & set(module.PROTECTED_MIGRATIONS)
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
    secrets = source.index("fetch_secret_key_metadata(repo_id, token)")
    storage = source.index("api.get_space_runtime(repo_id=repo_id)")
    snapshot = source.index("snapshot_space(repo_id, token, archive_root)")
    deletion = source.index("api.delete_repo(")
    absence = source.index("if not api.repo_exists(repo_id=repo_id, repo_type=\"space\")")
    assert secrets < storage < snapshot < deletion < absence
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


def test_workflow_runs_only_after_successful_exact_source_deploy() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    required = (
        'workflows: ["Sync to HuggingFace Space"]',
        "types: [completed]",
        "branches: [main]",
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.head_branch == 'main'",
        "SOURCE_SHA: ${{ github.event.workflow_run.head_sha || github.sha }}",
        "ref: ${{ env.SOURCE_SHA }}",
        "repository: szl-holdings/a11oy",
        "scripts/retire_legacy_resilience_spaces.py",
        "hf-legacy-resilience-retirement-${{ github.run_id }}",
    )
    for marker in required:
        assert marker in text
    assert "environment:" not in text
    assert "delete_repo" not in text

def test_v8_topology_keeps_sentra_public_and_only_vessels_folded() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'public != ("terra", "sentra", "counsel", "finance", "lyte")' in source
    assert 'folded != ("vessels",)' in source
    assert '"SZLHOLDINGS/sentra"' in source
    assert '"SZLHOLDINGS/vessels": "/vessels"' in source
