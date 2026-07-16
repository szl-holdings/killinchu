# SPDX-License-Identifier: Apache-2.0
"""Regression contract for the A11oy -> Killinchu shared runtime wave 23."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi import FastAPI

import a11oy_code_engine as code_engine
import a11oy_hf_assets as hf_assets
import a11oy_org_rag as org_rag
import szl_alloy_models as alloy_models
import szl_governed_infer as governed_infer
import szl_quant_qbio_holo as qbio_rollup
import szl_quantum_bio as qbio
import szl_waqay as waqay
import szl_yupay as yupay


def _reset_rag_runtime(monkeypatch, db_path: Path) -> None:
    monkeypatch.setattr(org_rag, "RAG_DB_PATH", str(db_path))
    monkeypatch.setattr(org_rag, "_GRAPH", org_rag.OrgGraph())
    monkeypatch.setattr(org_rag, "_BUILD_META", {"built": False})
    monkeypatch.setattr(org_rag, "_REHYDRATE_ATTEMPTED", False)
    monkeypatch.setattr(org_rag, "_maybe_embedder", lambda: None)


def _stage_generation(conn, generation_id: str, body: str) -> org_rag.OrgGraph:
    graph = org_rag.OrgGraph()
    graph.add_node("szl-holdings/a11oy", "repo", repo="a11oy")
    org_rag._ingest_text(
        graph,
        conn,
        repo="a11oy",
        path="README.md",
        raw=body,
        source="test:fixture",
        category="app_code",
        embed_fn=None,
        generation_id=generation_id,
    )
    return graph


def test_missing_isolation_refuses_before_subprocess(monkeypatch) -> None:
    called = False

    def forbidden_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not start without fixed isolation")

    monkeypatch.setattr(code_engine, "resource", None)
    monkeypatch.setattr(code_engine, "_UNSHARE", None)
    monkeypatch.setattr(code_engine.subprocess, "run", forbidden_run)

    result = code_engine._sandbox_exec("print('must not execute')")

    assert called is False
    assert result["ok"] is False
    assert result["execution_state"] == "UNAVAILABLE"
    assert result["isolation"] == "UNAVAILABLE — no code executed"
    assert "POSIX_RESOURCE_LIMITS" in result["capability"]["missing"]
    assert "UNSHARE_NET_NAMESPACE" in result["capability"]["missing"]


def test_interrupted_rag_generation_never_replaces_active(monkeypatch, tmp_path) -> None:
    _reset_rag_runtime(monkeypatch, tmp_path / "rag.sqlite3")
    conn = org_rag._db()
    org_rag._init_schema(conn)
    active = org_rag._begin_generation(conn, "active")
    graph = _stage_generation(conn, active, "stable alpha evidence")
    org_rag._persist_runtime_state(
        conn,
        graph,
        {"built": True, "mode": "active", "ts": 1.0, "repos": 1, "chunks": 1},
        active,
    )
    interrupted = org_rag._begin_generation(conn, "interrupted")
    _stage_generation(conn, interrupted, "partial beta evidence")
    conn.commit()
    conn.close()

    stable = org_rag.query("stable alpha", k=2)
    partial = org_rag.query("partial beta", k=2)
    assert stable["generation_id"] == active
    assert stable["grounded_count"] == 1
    assert partial["generation_id"] == active
    assert partial["grounded_count"] == 0


def test_rag_rehydrate_detects_tampering(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "rag.sqlite3"
    _reset_rag_runtime(monkeypatch, db_path)
    conn = org_rag._db()
    org_rag._init_schema(conn)
    generation_id = org_rag._begin_generation(conn, "sealed")
    graph = _stage_generation(conn, generation_id, "sealed evidence")
    org_rag._persist_runtime_state(
        conn,
        graph,
        {"built": True, "mode": "sealed", "ts": 1.0, "repos": 1, "chunks": 1},
        generation_id,
    )
    conn.execute(
        "UPDATE org_chunks_gen SET body='tampered' WHERE generation_id=?",
        (generation_id,),
    )
    conn.commit()
    conn.close()

    _reset_rag_runtime(monkeypatch, db_path)
    assert org_rag._rehydrate_runtime_state() is False
    assert org_rag.status()["integrity_state"] == "FAILED_CLOSED"
    refused = org_rag.query("sealed", k=1)
    assert refused["ok"] is False
    assert refused["i_dont_know"] is True


def test_alloy_generation_is_receipted_before_operational(monkeypatch, tmp_path) -> None:
    receipt_log = tmp_path / "provider-receipts.jsonl"
    monkeypatch.setenv("SZL_GOVERN_INFER_LOG", str(receipt_log))
    importlib.reload(governed_infer)
    demo_id = next(
        model["model_id"]
        for model in alloy_models.ALLOY_ROSTER
        if model["tier_band"] == "demo_cpu"
    )
    monkeypatch.setattr(
        alloy_models,
        "_local_generate",
        lambda prompt, max_tokens=256: {
            "served_locally": True,
            "text": "real fixture llama.cpp output",
            "backend": "llama.cpp",
            "tower_side": False,
        },
    )

    result = alloy_models.alloy_governed_suggest(
        "receipt this generation", force_tier="demo_cpu"
    )

    assert result["served_locally"] is True
    assert result["inference_receipted"] is True
    assert result["operational"] is True
    assert result["honest_stub"] is False
    status = governed_infer.inference_receipt_status(demo_id)
    assert status["successful_receipt_count"] == 1
    assert status["chain_ok"] is True
    assert receipt_log.is_file()


def test_quantum_bio_verification_boundary_survives_rollup() -> None:
    summary = json.loads(qbio._h_summary(None).body)
    rollup = qbio_rollup._qbio_status()

    for payload in (summary, rollup):
        assert payload["verification_scope"] == "COMPUTATIONAL_REPRODUCIBILITY_ONLY"
        assert "not experimental validation" in payload["verification_boundary"]
    boundary = qbio.VERIFICATION_BOUNDARY.lower()
    assert "not an instrument measurement" in boundary
    assert "not evidence of quantum advantage" in boundary


def test_fastapi_openapi_builds_for_synced_surface_modules() -> None:
    app = FastAPI()
    hf_assets.register(app, ns="killinchu")
    qbio_rollup.register(app, ns="killinchu")
    waqay.register(app, ns="killinchu")
    yupay.register(app, ns="killinchu")

    # WAQAY/YUPAY are intentionally hidden from the public schema, but route
    # registration must still resolve every annotation and schema generation
    # must complete for the exposed assets surface.
    paths = app.openapi()["paths"]
    route_paths = {getattr(route, "path", None) for route in app.router.routes}
    assert "/api/killinchu/v1/assets/manifest" in paths
    assert "/api/killinchu/v1/qbio/status" in route_paths
    assert "/api/killinchu/v1/quant/status" in route_paths
    assert "/api/killinchu/v1/holographic/status" in route_paths
    assert "/api/killinchu/v1/waqay/doctrine" in route_paths
    assert "/api/killinchu/v1/yupay/doctrine" in route_paths
