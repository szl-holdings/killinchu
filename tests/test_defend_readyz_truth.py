# SPDX-License-Identifier: Apache-2.0
"""Readiness must not turn local SQLite observation into production authority."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_defend_plane as defend


def _client(tmp_path, monkeypatch):
    path = tmp_path / "defend.sqlite3"
    monkeypatch.setenv("KILLINCHU_DEFEND_STATE_PATH", str(path))
    monkeypatch.setenv("KILLINCHU_DEFEND_SIGNING_KEY", "synthetic-test-key-long-enough")
    app = FastAPI()
    defend.register(app)
    return TestClient(app), path


def test_observation_does_not_initialize_local_store(tmp_path, monkeypatch):
    client, path = _client(tmp_path, monkeypatch)
    for route in ("/api/defend/status", "/api/defend/readyz", "/api/defend/source", "/api/defend/metrics"):
        response = client.get(route)
        assert response.status_code == (503 if route.endswith("readyz") else 200)
        assert not path.exists(), route
    status = client.get("/api/defend/status").json()
    assert status["store"]["state"] == "FAILED_CLOSED"
    assert status["production_ready"] is False
    assert status["production_receipts_ready"] is False


def test_local_store_does_not_satisfy_production_readiness_or_take_writer_lock(tmp_path, monkeypatch):
    client, path = _client(tmp_path, monkeypatch)
    defend.DefendStore(str(path))  # Explicit local writer initialization.
    writer = sqlite3.connect(path, isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        assert Path(f"{path}-wal").exists()
        start = time.monotonic()
        status_response = client.get("/api/defend/status")
        ready_response = client.get("/api/defend/readyz")
        assert time.monotonic() - start < 2
    finally:
        writer.rollback()
        writer.close()
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["store"]["state"] == "FAILED_CLOSED"
    assert status["store"]["error"] == "ACTIVE_WAL_SIDECAR"
    assert status["local_demo_readable"] is False
    assert status["production_ready"] is False
    assert status["production_receipts_ready"] is False
    assert status["workflow_operational"] is False
    assert ready_response.status_code == 503
    assert ready_response.json()["production_gate"] == "DURABLE_STATE_AND_IDENTITY_UNVERIFIED"
    assert client.get("/api/defend/status").json()["local_demo_readable"] is True


def test_clean_snapshot_read_does_not_create_wal_sidecars(tmp_path, monkeypatch):
    client, path = _client(tmp_path, monkeypatch)
    defend.DefendStore(str(path))
    sidecars = (Path(f"{path}-wal"), Path(f"{path}-shm"))
    assert all(not sidecar.exists() for sidecar in sidecars)
    actual_connect = defend.sqlite3.connect
    observed_uris = []

    def audited_connect(database, *args, **kwargs):
        if kwargs.get("uri"):
            observed_uris.append(str(database))
        return actual_connect(database, *args, **kwargs)

    monkeypatch.setattr(defend.sqlite3, "connect", audited_connect)
    for route in ("/api/defend/status", "/api/defend/readyz", "/api/defend/source", "/api/defend/metrics"):
        response = client.get(route)
        assert response.status_code == (503 if route.endswith("readyz") else 200)
        assert all(not sidecar.exists() for sidecar in sidecars)
    assert observed_uris and all(uri.endswith("?mode=ro&immutable=1") for uri in observed_uris)
    assert client.get("/api/defend/status").json()["store"]["state"] == "READABLE"


def test_deploy_expects_defend_readyz_to_fail_closed():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/hf-sync.yml").read_text(
        encoding="utf-8"
    )
    smoke_paths = next(line for line in workflow.splitlines() if "smoke-paths:" in line)
    assert "/api/defend/status" in smoke_paths
    assert "/api/defend/readyz" not in smoke_paths
    assert "Require Defend production readiness to fail closed" in workflow
    assert 'test "$code" = "503"' in workflow


def test_page_separates_signing_availability_from_production_qualification(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    status = client.get("/api/defend/status").json()
    assert status["signing"]["state"] == "HMAC_SHA256_READY"
    assert status["production_receipts_ready"] is False

    page = client.get("/defend").text
    assert "j.local_demo_readable?'readable':'unavailable'" in page
    assert "j.workflow_operational?'operational':'failed closed'" not in page
    assert "j.signing.state==='HMAC_SHA256_READY'?'available':'unavailable'" in page
    assert "j.production_receipts_ready?'qualified':'unqualified'" in page
    assert "j.production_receipts_ready?'signed':'unsigned'" not in page
