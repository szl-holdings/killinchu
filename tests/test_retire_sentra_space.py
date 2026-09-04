"""Static safety gates for the exact former-Sentra retirement transaction."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "retire_sentra_space.py"
WORKFLOW = ROOT / ".github" / "workflows" / "retire-sentra-space.yml"


def constants() -> dict[str, object]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return values


def test_operator_has_one_exact_target_and_one_replacement() -> None:
    values = constants()
    assert values["TARGET"] == "SZLHOLDINGS/sentra"
    assert values["REPLACEMENT"] == "SZLHOLDINGS/killinchu"
    assert values["COMMAND_CENTRE"] == "betterwithage/szl-command-centre"
    assert values["SOURCE_AUTHORITY"] == "szl-holdings/szl-defensive-control-plane"


def test_preservation_and_live_proof_precede_delete() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.index("publisher_hashes = verify_publishers()") < text.index("api.delete_repo(")
    assert text.index("replacement = verify_replacement()") < text.index("api.delete_repo(")
    assert text.index("archive_and_verify(") < text.rindex("api.delete_repo(")
    assert text.index("current != source_revision") < text.rindex("api.delete_repo(")
    assert text.rindex("api.delete_repo(") < text.index("verify_absent()", text.rindex("api.delete_repo("))
    assert "secret_values_read\": False" in text


def test_workflow_has_no_caller_supplied_target() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch: {}" in text
    assert "retire_sentra_space.py" in text
    assert "target:" not in text.lower()
    assert "HF_ORG_TOKEN" in text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text


def test_operator_proves_same_origin_defend_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for route in ("/defend", "/api/defend/status", "/api/defend/source"):
        assert route in text
    for boundary in (
        '"effectors_enabled": False',
        '"human_approval_required": True',
        '"arbitrary_command_execution": False',
    ):
        assert boundary in text
