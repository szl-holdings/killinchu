# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. -- SZL Holdings. ORCID 0009-0001-0110-4173
"""Contract tests for the Killinchu Immune organ mount (fold migration of
SZLHOLDINGS/immune per the a11oy keep-list: state MIGRATION_REQUIRED,
target_route https://szlholdings-killinchu.hf.space/immune)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import szl_immune


def _client() -> TestClient:
    app = FastAPI()
    result = szl_immune.register(app, ns="killinchu")
    assert result["ok"] is True
    assert result["ns"] == "killinchu"
    return TestClient(app)


def test_register_mounts_both_prefixes() -> None:
    app = FastAPI()
    result = szl_immune.register(app, ns="killinchu")
    assert result["ok"] is True
    paths = {getattr(r, "path", "") for r in app.router.routes}
    for p in (
        "/v1/immune/healthz",
        "/v1/immune/status",
        "/v1/immune/gates",
        "/v1/immune/threats",
        "/v1/immune/feed",
        "/v1/immune/verdict",
        "/v1/immune/verify",
        "/api/killinchu/v1/immune/healthz",
        "/api/killinchu/v1/immune/verdict",
    ):
        assert p in paths, p
    assert result["routes"], result


def test_healthz_is_fail_closed() -> None:
    r = _client().get("/v1/immune/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "immune"
    assert body["fail_closed"] is True


def test_status_and_verify_use_khipu_chain() -> None:
    c = _client()
    st = c.get("/v1/immune/status")
    assert st.status_code == 200
    sb = st.json()
    assert sb["ok"] is True
    assert sb["role"].startswith("fail-closed egress gate")
    v = c.get("/v1/immune/verify")
    assert v.status_code == 200
    assert v.json()["ok"] is True


def test_verdict_deny_on_threat_with_receipt_and_header() -> None:
    c = _client()
    r = c.post(
        "/v1/immune/verdict",
        json={"action": {"cmd": "DROP TABLE users"}, "request_id": "t1"},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["decision"] == "deny"
    assert b["khipu_receipt"]["digest"]
    assert r.headers.get("x-szl-immune-decision") == "deny"


def test_verdict_allow_clean_action() -> None:
    c = _client()
    r = c.post(
        "/v1/immune/verdict",
        json={"action": {"cmd": "echo hello"}, "request_id": "t2"},
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "allow"


def test_module_selftest_passes() -> None:
    out = szl_immune._selftest()
    assert out["threat_deny"] and out["clean_allow"]
    assert out["lambda_floor_deny"] and out["size_guard_deny"]
    assert out["chain_verified"] and out["no_codename_leak"]
