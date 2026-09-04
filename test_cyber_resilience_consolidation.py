"""Contract tests for the single Killinchu cyber-resilience product boundary."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "docs" / "killinchu-cyber-resilience-consolidation.v1.json"
DECISION = ROOT / "docs" / "KILLINCHU-CYBER-RESILIENCE-CONSOLIDATION.md"
PUBLIC_SPACE = "SZLHOLDINGS/killinchu"
LEGACY_SPACES = {
    "SZLHOLDINGS/vessels",
    "SZLHOLDINGS/sentra",
    "SZLHOLDINGS/immune",
    "SZLHOLDINGS/immune-lattice",
    "SZLHOLDINGS/aegis-assurance",
}
ALLOWED_STATES = {
    "LIVE",
    "MIGRATION_REQUIRED",
    "INTEGRATION_REQUIRED",
    "REFERENCE_CLEANUP_REQUIRED",
    "PARITY_AUDIT_REQUIRED",
    "DELETE_READY_AFTER_REFERENCE_CLEANUP",
}


def _load() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_one_public_killinchu_runtime() -> None:
    document = _load()
    product = document["public_product"]
    assert product["name"] == "Killinchu"
    assert product["huggingface_space"] == PUBLIC_SPACE
    assert product["public_runtime_count"] == 1
    assert document["portfolio"] == {
        "internal_name": "Aegis",
        "external_product": False,
        "separate_space_allowed": False,
    }


def test_capability_planes_are_modules_not_competing_products() -> None:
    document = _load()
    planes = {plane["id"]: plane for plane in document["capability_planes"]}
    assert set(planes) == {"sentra", "immune", "vessels", "counter-uas", "evidence"}
    assert planes["sentra"]["source_repository"] == (
        "szl-holdings/szl-defensive-control-plane"
    )
    assert planes["immune"]["source_repository"] == "szl-holdings/immune"
    assert planes["vessels"]["source_repository"] == "szl-holdings/killinchu"
    for plane in planes.values():
        assert plane["retirement_state"] in ALLOWED_STATES
        assert PUBLIC_SPACE not in plane["legacy_spaces"]
        assert plane["target_routes"]
        assert all(route.startswith("/") for route in plane["target_routes"])


def test_every_known_legacy_space_is_accounted_for() -> None:
    document = _load()
    observed = {
        space
        for plane in document["capability_planes"]
        for space in plane["legacy_spaces"]
    }
    observed.update(adapter["space"] for adapter in document["thin_adapters"])
    assert observed == LEGACY_SPACES
    assert all(
        adapter["state"] in ALLOWED_STATES for adapter in document["thin_adapters"]
    )


def test_irreversible_deletion_is_fully_gated() -> None:
    document = _load()
    required = {
        "source_captured",
        "product_captured",
        "evidence_captured",
        "publisher_removed",
        "replacement_verified",
        "no_unique_secret_dependency",
    }
    assert set(document["retirement_gates"]) == required
    policy = document["deletion_policy"]
    assert policy["irreversible"] is True
    assert policy["delete_only_after_all_gates"] is True
    assert policy["replacement_space"] == PUBLIC_SPACE
    assert policy["secret_free_receipt_required"] is True
    assert policy["recreation_forbidden"] is True


def test_decision_preserves_defensive_truth_boundary() -> None:
    document = _load()
    boundary = document["truth_boundary"]
    assert boundary["defensive_only"] is True
    assert boundary["arbitrary_command_execution"] is False
    assert boundary["civilian_targeting"] is False
    assert boundary["simulated_range_must_be_labeled"] is True
    assert boundary["live_connectors_require_current_observation"] is True

    decision = DECISION.read_text(encoding="utf-8")
    for marker in (
        "SOLE PUBLIC RUNTIME",
        "product-boundary decision",
        "must not iframe, reverse-proxy, or depend at runtime on the retired Spaces",
        "Deletion is irreversible",
        "Publisher removed",
        "A healthy endpoint proves reachability",
    ):
        assert marker in decision
