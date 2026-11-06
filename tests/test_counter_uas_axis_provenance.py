# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""The 13 Λ axis scores must say where they came from.

``POST /api/killinchu/v1/counter-uas/evaluate`` falls back to a fixed prior
(every axis >= 0.90, Λ ≈ 0.922, above the 0.90 floor) when a request carries no
``axis_scores``, and ``GET /api/killinchu/v1/lambda`` always returns that same
prior. Neither response said so, so a fixed constant read like a measurement of
the submitted track. This boots the real app (no mocks) and checks the label on
the wire and in the decision receipt, then checks that both serve entrypoints
carry the same contract.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")

TestClient = pytest.importorskip("starlette.testclient").TestClient

ROOT = Path(__file__).resolve().parents[1]
# serve.py binds _APP_ROOT (static/, drones_db.json) from KILLINCHU_ROOT at
# import time; default it to this checkout like tests/test_frontier_endpoints.py
# so whichever module imports serve first, later suites see the same root.
os.environ.setdefault("KILLINCHU_ROOT", str(ROOT))

import serve  # noqa: E402

EVALUATE = "/api/killinchu/v1/counter-uas/evaluate"


@pytest.fixture(scope="module")
def client():
    # Same reason as tests/test_qa_input_hardening.py: lift the per-IP limiter
    # for this in-process client; the limiter is not what is under test.
    try:
        import szl_be_hardening
        szl_be_hardening.RATE_LIMIT_PER_MIN = 10_000_000
    except Exception:
        pass
    return TestClient(serve.app)


def test_evaluate_without_axis_scores_labels_the_fixed_prior(client):
    body = client.post(EVALUATE, json={"telemetry": {}}).json()
    assert body["axis_scores_source"] == "FIXED_DEFAULT_PRIOR"
    assert len(body["axis_scores"]) == 13


def test_evaluate_with_axis_scores_uses_and_labels_the_request(client):
    body = client.post(EVALUATE, json={"telemetry": {}, "axis_scores": [0.5] * 13}).json()
    assert body["axis_scores_source"] == "REQUEST"
    assert set(body["axis_scores"].values()) == {0.5}
    assert body["lambda"] == pytest.approx(0.5)
    assert body["lambda_pass"] is False


def test_decision_receipt_records_the_axis_source(client):
    body = client.post(EVALUATE, json={"telemetry": {}}).json()
    digest = body["lambda_receipt"]["digest"]
    node = next(n for n in reversed(serve._KHIPU_DAG) if n["digest"] == digest)
    assert node["receipt"]["kind"] == "counter_uas_decision"
    assert node["receipt"]["payload"]["axis_scores_source"] == "FIXED_DEFAULT_PRIOR"


def test_lambda_axes_endpoint_labels_its_example_scores(client):
    body = client.get("/api/killinchu/v1/lambda").json()
    assert body["axis_scores_source"] == "FIXED_DEFAULT_PRIOR"
    assert "Not a live measurement" in body["axis_scores_note"]


@pytest.mark.parametrize("entrypoint", ["serve.py", "deploy/space/serve.py"])
def test_both_serve_entrypoints_carry_the_label(entrypoint):
    source = (ROOT / entrypoint).read_text(encoding="utf-8")
    assert 'axis_scores_source = "REQUEST" if supplied_axes else "FIXED_DEFAULT_PRIOR"' in source
    assert source.count('"axis_scores_source": axis_scores_source') == 2  # response + receipt
    assert '"axis_scores_source": "FIXED_DEFAULT_PRIOR"' in source  # /v1/lambda
