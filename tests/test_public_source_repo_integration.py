"""Repository-level contracts for the installed public-source frontier."""
from __future__ import annotations

import json
from pathlib import Path

import killinchu_public_source_fabric as fabric
import killinchu_vessels_screening as screening

ROOT = Path(__file__).resolve().parents[1]


def test_serve_registers_the_fixed_public_source_fabric_before_existing_osint():
    source = (ROOT / "serve.py").read_text(encoding="utf-8")
    marker = "# SZL PUBLIC SOURCE FABRIC V1"
    existing = "import killinchu_osint as _killinchu_osint"
    assert source.count(marker) == 1
    assert source.index(marker) < source.index(existing)
    assert "_killinchu_public_source_fabric.register(" in source
    assert 'app, ns="killinchu"' in source
    assert "_killinchu_public_source_fabric.start_warmer()" in source


def test_canonical_image_contains_connector_and_screening_store():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    mirror = (ROOT / "deploy/space/Dockerfile").read_text(encoding="utf-8")
    assert dockerfile == mirror
    for module in (
        "killinchu_public_source_fabric.py",
        "killinchu_vessels_screening.py",
    ):
        assert dockerfile.count(module) == 1, module

    manifest = json.loads((ROOT / "deploy/image-contract.json").read_text(encoding="utf-8"))
    sources = manifest["local_copy_sources"]
    assert "killinchu_public_source_fabric.py" in sources
    assert "killinchu_vessels_screening.py" in sources
    assert "killinchu_public_source_fabric" in manifest["registered_runtime_modules"]


def test_screening_loader_preserves_source_provenance_and_old_default():
    saved = screening._LISTS.copy()
    screening._LISTS.clear()
    try:
        old = screening.load_screening_list("operator-test", ["Operator Entity"])
        official = screening.load_screening_list(
            "official:test",
            ["Official Entity"],
            source="Official Test Authority | https://example.invalid/list.xml",
            truth_label="REPORTED",
        )
        assert old["source"] == "operator-supplied"
        assert official["source"].startswith("Official Test Authority")
        hit = screening.screen_entity("OFFICIAL ENTITY")
        assert hit["result"] == "HIT"
        assert hit["hits"][0]["source"].startswith("Official Test Authority")
        assert isinstance(screening.healthz()["sources"], list)
    finally:
        screening._LISTS.clear()
        screening._LISTS.update(saved)


def test_public_routes_and_policy_have_no_action_authority():
    from fastapi import FastAPI

    app = FastAPI()
    installed = fabric.register(app)
    assert len(installed) == 5
    for route in app.routes:
        if route.path in installed:
            assert route.methods == {"GET"}
    index = fabric.source_index()
    assert index["policy"]["authority"]["action_authority"] == "NONE"
    assert index["policy"]["content"]["active_force_geolocation"] == "PROHIBITED"
