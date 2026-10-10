# SPDX-License-Identifier: Apache-2.0
"""Receipt conservation uses key membership, not a missing-key null match."""

from __future__ import annotations

from szl_provenance import derive_receipt_conservation


DIGEST = "ab" * 32


def _node(receipt: dict, digest: object = DIGEST) -> dict:
    return {"digest": digest, "receipt": receipt, "signed": False}


def test_field_membership_rejects_a_missing_null_and_keeps_python_equality() -> None:
    cases = (
        ({}, {"digest": None}, False),
        ({"digest": None}, {"digest": None}, True),
        ({"digest": "abc"}, {"digest": "abc"}, True),
        ({"digest": "abc"}, {"digest": "def"}, False),
        ({"digest": "abc"}, {"digest": "abc", "revision": None}, False),
        ({"digest": "abc", "revision": "r1"}, {"digest": "abc"}, True),
        ({"enabled": False, "count": 0}, {"enabled": False, "count": 0}, True),
        ({}, {}, True),
        ({"value": True}, {"value": 1}, True),
    )
    for stored, expected, want in cases:
        result = derive_receipt_conservation(expected, _node(stored))
        assert result["receipts_in"] == 1
        assert result["receipts_in_eq_out"] is want
        assert result["receipts_out"] == (1 if want else 0)


def test_missing_or_malformed_digest_does_not_conserve() -> None:
    submitted = {"digest": "abc"}
    for digest in ("", "AB" * 32, "ab" * 31, None, True, 1):
        result = derive_receipt_conservation(submitted, _node({"digest": "abc"}, digest))
        assert result["receipts_in_eq_out"] is False
        assert result["receipts_out"] == 0
