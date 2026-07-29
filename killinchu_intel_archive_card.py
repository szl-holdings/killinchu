#!/usr/bin/env python3
"""Render the canonical Killinchu intel-archive card and rights contract.

Pure stdlib. Runtime publication and CI publication both consume the same source
files, preventing the Hugging Face card from drifting away from reviewed source.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "datasets" / "killinchu-osint-corpus"
CARD_SOURCE = SOURCE_DIR / "README.md"
LICENSE_SOURCE = SOURCE_DIR / "LICENSE.md"
DEFAULT_PROJECTION_SCHEMA = "killinchu.platform-projection/v2"


def _read_required(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"canonical dataset source is empty: {path}")
    return text


def render_card(
    *,
    prefix: str = "intel",
    projection_schema: str = DEFAULT_PROJECTION_SCHEMA,
    cell_degrees: float = 1.0,
) -> str:
    prefix = str(prefix).strip().strip("/") or "intel"
    projection_schema = str(projection_schema).strip()
    if not projection_schema:
        raise ValueError("projection_schema must not be empty")
    cell = max(1.0, float(cell_degrees))

    text = _read_required(CARD_SOURCE)
    replacements = {
        "{{ARCHIVE_PREFIX}}": prefix,
        "{{PROJECTION_SCHEMA}}": projection_schema,
        "{{ARCHIVE_CELL}}": f"{cell:.2f}",
    }
    for marker, value in replacements.items():
        text = text.replace(marker, value)
    if "{{" in text or "}}" in text:
        raise RuntimeError("unresolved dataset-card template marker")

    required = (
        "license: other",
        "license_name:",
        "license_link:",
        "Open Data Commons Open Database License 1.0",
        "Creative Commons Attribution 4.0",
        "Fintraffic / digitraffic.fi",
        "source-specific",
        "HMAC pseudonyms",
        "not attested",
        "not a DSSE / Ed25519 signature",
    )
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"canonical card is missing required marker: {marker}")
    return text.rstrip() + "\n"


def render_license() -> str:
    text = _read_required(LICENSE_SOURCE)
    required = (
        "Open Database License 1.0",
        "Creative Commons Attribution 4.0",
        "Fintraffic / digitraffic.fi",
        "Open-web OSINT records",
        "does not grant a blanket license",
    )
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"canonical license is missing required marker: {marker}")
    return text.rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-out", type=Path)
    parser.add_argument("--license-out", type=Path)
    parser.add_argument("--prefix", default="intel")
    parser.add_argument("--projection-schema", default=DEFAULT_PROJECTION_SCHEMA)
    parser.add_argument("--cell-degrees", type=float, default=1.0)
    args = parser.parse_args()

    card = render_card(
        prefix=args.prefix,
        projection_schema=args.projection_schema,
        cell_degrees=args.cell_degrees,
    )
    license_text = render_license()
    if args.card_out:
        args.card_out.parent.mkdir(parents=True, exist_ok=True)
        args.card_out.write_text(card, encoding="utf-8")
    else:
        print(card, end="")
    if args.license_out:
        args.license_out.parent.mkdir(parents=True, exist_ok=True)
        args.license_out.write_text(license_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
