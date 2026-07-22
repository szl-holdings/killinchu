# SPDX-License-Identifier: Apache-2.0
"""Fail-closed checks for the public Killinchu anatomy formula taxonomy."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ELITE = ROOT / "killinchu_elite_console.py"
BLOCK_START = "anatomy-map-tab-patch ::"
BLOCK_END = "end anatomy-map-tab-patch"
LOCKED = ("F1", "F11", "F12", "F18", "F19")
EXPERIMENTAL = ("F4", "F7", "F22")
LEGACY = "F1,F4,F7,F11,F12,F18,F19,F22"


def _marker(text: str) -> str:
    start = text.index(BLOCK_START)
    end = text.index(BLOCK_END, start)
    return text[start:end]


def _active_source(text: str) -> str:
    """Exclude the immutable historical KB snapshot, not the live console."""
    return "".join(
        line for line in text.splitlines(keepends=True)
        if "window.__KB__=" not in line
    )


def _formula_ids(group: str) -> tuple[str, ...]:
    return tuple(re.findall(r"F\d+", group))


def _validate_marker(block: str) -> None:
    locked_match = re.search(r"5 LOCKED formulas \{([^}]+)\}", block)
    assert locked_match, "exact locked-five declaration is required"
    assert _formula_ids(locked_match.group(1)) == LOCKED

    experimental_match = re.search(
        r"EXPERIMENTAL / NOT LOCKED \{([^}]+)\}", block
    )
    assert experimental_match, "exact experimental/not-locked declaration is required"
    assert _formula_ids(experimental_match.group(1)) == EXPERIMENTAL
    assert set(LOCKED).isdisjoint(EXPERIMENTAL)
    assert "Conjecture 1" in block


def test_live_marker_declares_exact_disjoint_maturity_sets() -> None:
    text = ELITE.read_text(encoding="utf-8")
    _validate_marker(_marker(text))


def test_active_elite_source_has_no_legacy_locked_eight_claim() -> None:
    active = _active_source(ELITE.read_text(encoding="utf-8"))
    compact = re.sub(r"\s+", "", active)
    assert LEGACY not in compact
    assert "locked-8" not in active.lower()
    assert "exactly 8 locked" not in active.lower()


def test_marker_rejects_legacy_eight_promotion() -> None:
    block = _marker(ELITE.read_text(encoding="utf-8"))
    legacy = block.replace(
        "5 LOCKED formulas {F1,F11,F12,F18,F19}; "
        "EXPERIMENTAL / NOT LOCKED {F4,F7,F22}",
        "8 LOCKED formulas {F1,F4,F7,F11,F12,F18,F19,F22}",
    )
    try:
        _validate_marker(legacy)
    except AssertionError:
        return
    raise AssertionError("legacy locked-eight promotion must fail closed")


def test_marker_rejects_missing_experimental_set() -> None:
    block = _marker(ELITE.read_text(encoding="utf-8"))
    missing = block.replace("EXPERIMENTAL / NOT LOCKED", "source-present")
    try:
        _validate_marker(missing)
    except AssertionError:
        return
    raise AssertionError("missing experimental/not-locked label must fail closed")
