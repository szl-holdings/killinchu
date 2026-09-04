"""Lock the persisted Killinchu Defend migration and retirement contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_migration_receipt_binds_one_product_and_one_capability_plane() -> None:
    receipt = json.loads(
        (ROOT / "docs" / "DEFEND_PLANE_MIGRATION_RECEIPT.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["public_product"] == "Killinchu"
    assert receipt["portfolio_name"] == "Aegis"
    assert receipt["capability_source_name"] == "Sentra"
    assert receipt["source_repository"] == "szl-holdings/szl-defensive-control-plane"
    assert len(receipt["source_revision"]) == 40
    assert receipt["effectors_enabled"] is False
    assert receipt["arbitrary_command_execution"] is False
    assert receipt["human_approval_required"] is True
    assert receipt["former_space_state"] == "RETIRE_ONLY_AFTER_LIVE_PARITY_PROOF"


def test_contract_names_every_live_and_compatibility_route() -> None:
    receipt = json.loads(
        (ROOT / "docs" / "DEFEND_PLANE_MIGRATION_RECEIPT.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(receipt["public_routes"]) == {
        "/resilience",
        "/defend",
        "/aegis",
        "/sentra",
        "/api/defend/status",
        "/api/defend/source",
    }
    documentation = (
        ROOT / "docs" / "DEFEND_PLANE_OPERATIONAL_CONTRACT.md"
    ).read_text(encoding="utf-8")
    for route in receipt["public_routes"]:
        assert f"`{route}`" in documentation
