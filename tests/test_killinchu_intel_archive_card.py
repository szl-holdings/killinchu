import re
from pathlib import Path

import killinchu_intel_archive_card as card


def test_card_has_complete_other_license_metadata():
    text = card.render_card(
        prefix="intel",
        projection_schema="killinchu.platform-projection/v2",
        cell_degrees=1.0,
    )
    assert "license: other" in text
    license_name = next(
        line.removeprefix("license_name: ").strip()
        for line in text.splitlines()
        if line.startswith("license_name: ")
    )
    assert re.fullmatch(r"[a-z0-9.-]+", license_name)
    assert license_name == "mixed-source-terms"
    assert "license_link:" in text
    assert "intel/*.ndjson" in text
    assert "killinchu.platform-projection/v2" in text
    assert "1.00°" in text
    assert "adsb.fi" not in text


def test_source_specific_attribution_is_explicit():
    text = card.render_card()
    assert "adsb.lol" in text
    assert "Open Data Commons Open Database License 1.0" in text
    assert "Fintraffic / digitraffic.fi" in text
    assert "Creative Commons Attribution 4.0" in text
    assert "Rights remain with the original publisher" in text
    assert "not a DSSE / Ed25519 signature" in text


def test_license_contract_does_not_blanket_relicense_sources():
    text = card.render_license()
    assert "does **not** relicense third-party data" in text
    assert "does not grant a blanket license" in text
    assert "Open-web OSINT records" in text


def test_canonical_sources_are_versioned_in_repository():
    root = Path(card.__file__).resolve().parent
    assert (root / "datasets/killinchu-osint-corpus/README.md").is_file()
    assert (root / "datasets/killinchu-osint-corpus/LICENSE.md").is_file()
