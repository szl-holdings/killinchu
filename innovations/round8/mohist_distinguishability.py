"""
Round 8 A8-04 — MOHIST-DISTINGUISHABILITY integration stub for killinchu.
Source: Mohist Canon Jing A 88 (~350 BCE). 同/異 extensional equality.
Lean stub: lutar-lean Lutar/Innovations/round8/MohistDistinguishability.lean
Doctrine v11 | SLSA L1 honest | kernel c7c0ba17/749-14-163 untouched.

Provides extensional receipt deduplication — two receipts are the same
iff they agree on every distinguishing field (Mohist 同/異 principle).
Signed-off-by: Yachay <yachay@szlholdings.ai>
Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, eq=True)
class Receipt:
    """A receipt with two identifying tag fields (Mohist extensionality)."""
    tag_a: Any
    tag_b: Any


def mohist_same(r: Receipt, s: Receipt) -> bool:
    """True iff receipts r and s share every tag — 同 (tóng)."""
    return r == s
