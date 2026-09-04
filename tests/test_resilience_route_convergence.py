"""Contract tests for Killinchu's single cyber-resilience public surface."""
from __future__ import annotations

import killinchu_nav_wireup as routes


EXPECTED_REDIRECTS = {
    "/vessels": "/elite/maritime",
    "/maritime": "/elite/maritime",
    "/airspace": "/elite#cuas_lab",
}


def test_retired_mission_pack_names_resolve_same_origin_inside_killinchu() -> None:
    for source, target in EXPECTED_REDIRECTS.items():
        assert routes._BARE_SURFACE_REDIRECTS[source] == target
        assert source.startswith("/")
        assert target.startswith("/")
        assert "://" not in target


def test_defend_and_resilience_are_real_routes_not_presentation_redirects() -> None:
    assert routes._SOURCE_NATIVE_PLANES == {"/defend"}
    assert "/resilience" not in routes._BARE_SURFACE_REDIRECTS
    assert "/defend" not in routes._BARE_SURFACE_REDIRECTS
    assert "/immune" not in routes._BARE_SURFACE_REDIRECTS


def test_legacy_space_origins_are_not_runtime_dependencies() -> None:
    source = open(routes.__file__, encoding="utf-8").read()
    for legacy_origin in (
        "szlholdings-vessels.hf.space",
        "szlholdings-sentra.hf.space",
        "szlholdings-immune.hf.space",
        "szlholdings-aegis-assurance.hf.space",
    ):
        assert legacy_origin not in source
