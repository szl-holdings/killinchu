# SPDX-License-Identifier: Apache-2.0
"""Health GET must report runtime signer capability without fabricating DSSE."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from serve import app


@pytest.mark.parametrize("signer", [
    None,
    SimpleNamespace(signing_available=lambda: False),
    SimpleNamespace(signing_available=lambda: (_ for _ in ()).throw(RuntimeError("unavailable"))),
])
def test_health_does_not_claim_signing_without_runtime_capability(signer):
    with patch("serve._szl_dsse", signer):
        response = TestClient(app).get("/api/killinchu/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["signing_available"] is False
    assert body["receipt_signature"].startswith("UNSIGNED")
    assert response.headers["cache-control"] == "no-store"


def test_health_reports_capability_without_minting_receipt():
    def forbidden_sign(*_args, **_kwargs):
        raise AssertionError("Health GET must not sign receipts")

    signer = SimpleNamespace(signing_available=lambda: True, sign_payload=forbidden_sign)
    with patch("serve._szl_dsse", signer):
        response = TestClient(app).get("/api/killinchu/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["signing_available"] is True
    assert body["receipt_signature"].startswith("AVAILABLE")
    assert "verify individual receipts" in body["receipt_signature"]
