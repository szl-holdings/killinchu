"""Consumer release regression: opening /elite/mesh must not sign or write.

This supplements, rather than duplicates, backend passive GET checks: the
historical defect was JavaScript POSTs issued by a read-only page navigation.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("KILLINCHU_VIEW_SOURCE") or REPO / "killinchu_mesh_view.py")
BACKEND = REPO / "killinchu_mesh.py"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _segment(start: str, end: str) -> str:
    text = _source()
    assert text.count(start) == 1, start
    assert text.count(end) == 1, end
    return text.split(start, 1)[1].split(end, 1)[0]


def test_live_route_is_advertised_but_only_get_mounts_it():
    text = _source()
    assert 'Route("/elite/mesh", _mesh_view, methods=["GET"]' in text
    assert '<a class="flag active" href="/elite/mesh">MESH</a>' in text


def test_receipts_source_is_observation_not_three_post_writes():
    body = _segment("async function loadReceipts(){", "function b64ToBytes(b64){")
    assert "getJSON('/mesh/status')" in body
    assert "postJSON(" not in body
    assert "fetch(" not in body
    assert "var seeds=" not in body
    assert "receipt_chain_depth" in body


def test_page_boot_never_implicitly_calls_quorum_or_enrollment():
    boot = _segment("/* =================== boot =================== */",
                    "window.addEventListener('resize'")
    assert "await loadTopology();" in boot
    assert "await loadReceipts();" in boot
    assert "await primeEnrollFromStatus();" in boot
    assert not re.search(r"\b(?:await\s+)?runQuorum\s*\(", boot)
    assert not re.search(r"\b(?:await\s+)?runEnroll\s*\(", boot)
    assert 'onclick="runQuorum()"' in _source()


def test_missing_or_throttled_receipt_status_is_unavailable_not_zero():
    body = _segment("async function loadReceipts(){", "function b64ToBytes(b64){")
    assert "d.__error || d.__stale || d.__throttled" in body
    assert "textContent='—'" in body
    assert "Number.isSafeInteger(d.receipt_chain_depth)" in body
    assert "depth===null?'—'" in body
    assert "_prov.receiptCount=null" in body


def test_passive_page_does_not_claim_independent_signer_or_inference():
    text = _source()
    assert 'id="mesh-passive-honesty"' in text
    assert "in-process, ephemeral harness" in text
    assert "not independently enrolled fleet evidence" in text
    assert "production Khipu inference" in text
    assert "Individual receipt listing and independently trusted signatures" in text


def test_rehash_stays_disabled_without_admitted_receipt_index():
    body = _segment("async function loadReceipts(){", "function b64ToBytes(b64){")
    assert "document.getElementById('btn-rehash').disabled=true" in body
    assert "document.getElementById('btn-tamper').disabled=true" in body
    assert "_receipts=[]" in body
    assert "No safe read-only receipt-list endpoint" in body


def test_observation_uses_existing_get_api_not_new_writer():
    backend = BACKEND.read_text(encoding="utf-8")
    assert '("/status", status_ep, ["GET"], "mesh_status")' in backend
    assert '("/write", write, ["POST"], "mesh_write")' in backend
    assert '("/quorum", quorum, ["POST"], "mesh_quorum")' in backend
    body = _segment("async function loadReceipts(){", "function b64ToBytes(b64){")
    assert "/mesh/write" in body  # explanatory text only, not a function call
