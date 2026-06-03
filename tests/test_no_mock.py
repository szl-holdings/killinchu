#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""Meta-test: FAIL if any non-test edge-formula source path contains mock/fake/stub/dummy.

HONESTY OVER CHECKLIST. The real-edge formula modules must contain no mock data, fake
endpoints, or stub implementations. We grep the formula sources (excluding this test dir)
for the forbidden tokens as whole words and fail loudly if found.

Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem).
"""
from __future__ import annotations

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FORBIDDEN = re.compile(r"\b(mock|fake|stub|dummy)\b", re.IGNORECASE)

# Only scan the real-edge formula surface this PR introduces/owns.
_TARGETS = [
    "killinchu_edge_formulas.py",
    os.path.join("szl_shared_formulas", "pac_bayes.py"),
    os.path.join("szl_shared_formulas", "kalman.py"),
    os.path.join("szl_shared_formulas", "byzantine_quorum.py"),
    os.path.join("szl_shared_formulas", "__init__.py"),
]


def _scan(path: str):
    hits = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            low = line.lower()
            # Allow comments that explicitly DISCLAIM mocks/fakes (honest guards), e.g.
            # "no mocks", "no fake signatures", "not a stored mock", "never a fake".
            if re.search(r"\b(no|not a|never a|never|without)\b[^\n]*\b(mock|fake|stub|dummy)", low):
                continue
            if _FORBIDDEN.search(line):
                hits.append((i, line.rstrip()))
    return hits


def test_no_mock_in_formula_sources():
    all_hits = {}
    for rel in _TARGETS:
        p = os.path.join(_ROOT, rel)
        if not os.path.exists(p):
            continue
        h = _scan(p)
        if h:
            all_hits[rel] = h
    assert not all_hits, f"forbidden mock/fake/stub/dummy tokens found: {all_hits}"


if __name__ == "__main__":
    test_no_mock_in_formula_sources()
    print("PASS test_no_mock_in_formula_sources — no mock/fake/stub/dummy in formula sources")
