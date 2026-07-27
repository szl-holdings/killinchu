#!/usr/bin/env python3
"""Apply the bounded source wiring for the canonical intel-archive card."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OSINT = ROOT / "killinchu_osint.py"
DOCKERFILE = ROOT / "Dockerfile"

NEW_CARD_FUNCTION = '''def _archive_card() -> str:
    """Render the reviewed mixed-source card from one canonical source file."""
    from killinchu_intel_archive_card import render_card

    return render_card(
        prefix=_ARCHIVE_PREFIX,
        projection_schema=_ARCHIVE_PROJECTION_SCHEMA,
        cell_degrees=_ARCHIVE_CELL,
    )


'''


def patch_osint() -> bool:
    text = OSINT.read_text(encoding="utf-8")
    start_marker = "def _archive_card() -> str:\n"
    end_marker = "def _archive_ensure_public() -> bool:\n"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("could not locate the bounded _archive_card function")
    current = text[start:end]
    if current == NEW_CARD_FUNCTION:
        return False
    text = text[:start] + NEW_CARD_FUNCTION + text[end:]
    OSINT.write_text(text, encoding="utf-8")
    return True


def patch_dockerfile() -> bool:
    text = DOCKERFILE.read_text(encoding="utf-8")
    changed = False
    if "killinchu_intel_archive_card.py" not in text:
        needle = "killinchu_osint.py"
        if needle not in text:
            raise RuntimeError("Dockerfile no longer copies killinchu_osint.py")
        text = text.replace(
            needle,
            "killinchu_osint.py killinchu_intel_archive_card.py",
            1,
        )
        changed = True

    dataset_copy = (
        "COPY datasets/killinchu-osint-corpus/ "
        "./datasets/killinchu-osint-corpus/"
    )
    if dataset_copy not in text:
        lines = text.splitlines()
        insertion = next(
            (
                index + 1
                for index, line in enumerate(lines)
                if "killinchu_intel_archive_card.py" in line
                and line.lstrip().startswith("COPY ")
            ),
            None,
        )
        if insertion is None:
            raise RuntimeError("could not locate renderer COPY layer")
        lines.insert(
            insertion,
            "# Canonical mixed-source Hugging Face dataset card and rights contract.",
        )
        lines.insert(insertion + 1, dataset_copy)
        text = "\n".join(lines) + "\n"
        changed = True

    if changed:
        DOCKERFILE.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    changed = patch_osint() | patch_dockerfile()
    print("changed=true" if changed else "changed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
