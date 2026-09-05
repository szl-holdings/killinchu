#!/usr/bin/env python3
"""Align the irreversible Space-retirement guard with the approved v8 topology."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "retire_legacy_resilience_spaces.py"
TEST = ROOT / "tests" / "test_legacy_resilience_space_retirement.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "# These names are architecturally folded into Killinchu but remain migration\n"
        "# sources. The deleter must never mutate them.\n",
        "# These names remain protected migration/provider sources. Sentra is now an\n"
        "# independent public flagship, while IMMUNE surfaces remain migration inputs.\n"
        "# The legacy deleter must never mutate any of them.\n",
        "protected-migration topology comment",
    )
    source = replace_once(
        source,
        '    if public != ("terra", "counsel", "finance", "lyte"):\n'
        '        raise RuntimeError(f"unexpected active vertical publisher inventory: {public!r}")\n'
        '    if folded != ("sentra", "vessels"):\n'
        '        raise RuntimeError(f"unexpected folded vertical inventory: {folded!r}")\n',
        '    if public != ("terra", "sentra", "counsel", "finance", "lyte"):\n'
        '        raise RuntimeError(f"unexpected active vertical publisher inventory: {public!r}")\n'
        '    if folded != ("vessels",):\n'
        '        raise RuntimeError(f"unexpected folded vertical inventory: {folded!r}")\n',
        "v8 vertical topology assertion",
    )
    SCRIPT.write_text(source, encoding="utf-8")

    tests = TEST.read_text(encoding="utf-8")
    tests = replace_once(
        tests,
        '        \'("terra", "counsel", "finance", "lyte")\',\n'
        "        'FOLDED_INTO_KILLINCHU',\n"
        '        \'("sentra", "vessels")\',\n',
        '        \'("terra", "sentra", "counsel", "finance", "lyte")\',\n'
        "        'FOLDED_INTO_KILLINCHU',\n"
        '        \'("vessels",)\',\n',
        "v8 topology regression markers",
    )
    addition = '''\n\ndef test_v8_topology_keeps_sentra_public_and_only_vessels_folded() -> None:\n    source = SCRIPT.read_text(encoding="utf-8")\n    assert 'public != ("terra", "sentra", "counsel", "finance", "lyte")' in source\n    assert 'folded != ("vessels",)' in source\n    assert '"SZLHOLDINGS/sentra"' in source\n    assert '"SZLHOLDINGS/vessels": "/vessels"' in source\n'''
    if "test_v8_topology_keeps_sentra_public_and_only_vessels_folded" in tests:
        raise RuntimeError("v8 topology test already exists")
    TEST.write_text(tests.rstrip() + addition.rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
