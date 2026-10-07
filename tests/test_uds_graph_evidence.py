# SPDX-License-Identifier: Apache-2.0
"""Synthetic UDS evidence states for the two passive graph routes."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import killinchu_posture_topology as topology


LOAD_UDS_PACKAGE = topology._load_uds_package


EMPTY_PACKAGE = """apiVersion: uds.dev/v1alpha1
kind: Package
spec:
  network:
    allow: []
    expose: []
"""

POPULATED_PACKAGE = """apiVersion: uds.dev/v1alpha1
kind: Package
spec:
  network:
    allow:
      - direction: Ingress
        remoteNamespace: municipal-ops
        port: 443
    expose:
      - service: permit-portal
        host: portal
        port: 443
"""

ROUTES = ("/api/killinchu/v1/attack-surface/graph", "/api/killinchu/v1/zerotrust/mesh")
PACKAGE_PREFIX = "apiVersion: uds.dev/v1alpha1\nkind: Package\nspec:\n  network:\n"


def _client(path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(topology, "_load_uds_package", lambda: LOAD_UDS_PACKAGE(path))
    app = FastAPI()
    topology.register(app)
    return TestClient(app)


def test_missing_package_is_unavailable_not_measured_empty(tmp_path, monkeypatch):
    client = _client(tmp_path / "missing.yaml", monkeypatch)
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 503
        body = response.json()
        assert body["ok"] is False
        assert body["evidence_state"] == "UNAVAILABLE"
        assert body["reason_code"] == "UDS_PACKAGE_MISSING"
        assert body["empty"] is None
        assert body["empty_state"] is None
        assert "No exposures" not in response.text
        assert "No allow rules" not in response.text


@pytest.mark.parametrize(
    ("content", "reason"),
    (
        ("", "UDS_PACKAGE_EMPTY"),
        ("spec: [", "UDS_PACKAGE_INVALID_YAML"),
        ("apiVersion: uds.dev/v1alpha1\nkind: Package\nspec:\n  network:\n    allow:\n      - direction: Ingress\n        remoteNamespace: municipal-ops\n    allow: []\n", "UDS_PACKAGE_INVALID_YAML"),
        ("apiVersion: uds.dev/v1alpha1\nkind: Package\nspec:\n  network:\n    allow: {}\n", "UDS_PACKAGE_INVALID_RULES"),
        ("apiVersion: uds.dev/v1alpha1\nkind: Package\nspec:\n  network:\n    allow:\n      - port: 443\n", "UDS_PACKAGE_INVALID_RULES"),
        ("apiVersion: uds.dev/v1alpha1\nkind: Package\nspec:\n  network:\n    expose:\n      - port: 443\n", "UDS_PACKAGE_INVALID_RULES"),
    ),
)
def test_malformed_package_is_not_measured_empty(tmp_path, monkeypatch, content, reason):
    path = tmp_path / "invalid.yaml"
    path.write_text(content, encoding="utf-8")
    client = _client(path, monkeypatch)
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 503
        assert response.json()["evidence_state"] == "MALFORMED"
        assert response.json()["reason_code"] == reason
        assert response.json()["empty"] is None


def test_valid_empty_package_is_an_observed_empty_graph(tmp_path, monkeypatch):
    path = tmp_path / "empty.yaml"
    path.write_text(EMPTY_PACKAGE, encoding="utf-8")
    client = _client(path, monkeypatch)
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["evidence_state"] == "OBSERVED_EMPTY"
        assert body["empty"] is True
        assert body["empty_state"]


def test_populated_package_keeps_observed_edges(tmp_path, monkeypatch):
    path = tmp_path / "populated.yaml"
    path.write_text(POPULATED_PACKAGE, encoding="utf-8")
    client = _client(path, monkeypatch)
    attack = client.get(ROUTES[0])
    mesh = client.get(ROUTES[1])
    assert attack.status_code == mesh.status_code == 200
    assert attack.json()["evidence_state"] == "OBSERVED"
    assert attack.json()["expose_layout"] == "SPEC_NETWORK_EXPOSE"
    assert attack.json()["empty"] is False
    assert len(attack.json()["exposures"]) == 2
    assert mesh.json()["evidence_state"] == "OBSERVED"
    assert mesh.json()["empty"] is False
    assert len(mesh.json()["edges"]) == 1
    assert mesh.json()["runtime_enforcement_state"] == "UNVERIFIED"
    assert mesh.json()["edges"][0]["mtls"] == "UNVERIFIED"
    assert "mTLS enforcement were not checked" in mesh.json()["honesty"]


def test_canonical_expose_without_allow_rules_is_observed(tmp_path, monkeypatch):
    path = tmp_path / "canonical.yaml"
    path.write_text(PACKAGE_PREFIX + "    expose:\n      - service: permit-portal\n"
                    "        host: portal\n        port: 443\n", encoding="utf-8")
    client = _client(path, monkeypatch)
    attack = client.get(ROUTES[0])
    mesh = client.get(ROUTES[1])
    assert attack.status_code == mesh.status_code == 200
    assert attack.json()["evidence_state"] == "OBSERVED"
    assert attack.json()["expose_layout"] == "SPEC_NETWORK_EXPOSE"
    assert attack.json()["exposures"] == ["expose:portal"]
    assert mesh.json()["evidence_state"] == "OBSERVED_EMPTY"


@pytest.mark.parametrize(
    ("content", "reason"),
    (
        (PACKAGE_PREFIX + "    expose: []\n  expose:\n    - service: legacy\n",
         "UDS_PACKAGE_AMBIGUOUS_EXPOSE_LAYOUT"),
        (PACKAGE_PREFIX + "    allow: []\n  expose:\n    - service: legacy\n",
         "UDS_PACKAGE_LEGACY_EXPOSE_UNVERIFIED"),
    ),
)
def test_unqualified_or_conflicting_expose_layout_is_malformed(
        tmp_path, monkeypatch, content, reason):
    path = tmp_path / "layout.yaml"
    path.write_text(content, encoding="utf-8")
    client = _client(path, monkeypatch)
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 503
        assert response.json()["evidence_state"] == "MALFORMED"
        assert response.json()["reason_code"] == reason


@pytest.mark.parametrize(
    "rules",
    (
        "    allow:\n      - direction: 3\n",
        "    allow:\n      - direction: Ingress\n        remoteNamespace: []\n",
        "    allow:\n      - direction: Ingress\n        remoteGenerated: []\n",
        "    allow:\n      - direction: Ingress\n        description: {}\n",
        "    allow:\n      - direction: Ingress\n        port: .nan\n",
        "    allow:\n      - direction: Ingress\n        port: -1\n",
        "    allow:\n      - direction: Ingress\n        port: 65536\n",
        "    allow:\n      - direction: Ingress\n        port: '443'\n",
        "    allow:\n      - direction: Ingress\n        port: true\n",
        "    expose:\n      - service: portal\n        host: []\n",
        "    expose:\n      - service: {}\n        host: portal\n",
        "    expose:\n      - service: portal\n        gateway: []\n",
        "    expose:\n      - service: portal\n        description: []\n",
        "    expose:\n      - service: portal\n        port: .inf\n",
        "    expose:\n      - service: portal\n        port: 0\n",
        "    expose:\n      - service: portal\n        port: 65536\n",
        "    expose:\n      - service: portal\n        port: '443'\n",
        "    expose:\n      - service: portal\n        port: true\n",
    ),
)
def test_graph_scalar_shape_and_port_are_validated(tmp_path, monkeypatch, rules):
    path = tmp_path / "invalid-graph-field.yaml"
    path.write_text(PACKAGE_PREFIX + rules, encoding="utf-8")
    client = _client(path, monkeypatch)
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 503
        assert response.json()["evidence_state"] == "MALFORMED"
        assert response.json()["reason_code"] == "UDS_PACKAGE_INVALID_RULES"
        assert response.json()["empty"] is None


def test_allow_rule_with_ports_list_and_no_single_port_is_valid(tmp_path, monkeypatch):
    path = tmp_path / "ports-list.yaml"
    path.write_text(PACKAGE_PREFIX + "    allow:\n      - direction: Ingress\n"
                    "        remoteNamespace: municipal-ops\n        ports: [80, 443]\n",
                    encoding="utf-8")
    client = _client(path, monkeypatch)
    mesh = client.get(ROUTES[1])
    assert mesh.status_code == 200
    assert mesh.json()["evidence_state"] == "OBSERVED"
    assert mesh.json()["edges"][0]["port"] == "?"


def test_parser_absence_is_unavailable(tmp_path, monkeypatch):
    path = tmp_path / "package.yaml"
    path.write_text(EMPTY_PACKAGE, encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)
    client = _client(path, monkeypatch)
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 503
        assert response.json()["evidence_state"] == "UNAVAILABLE"
        assert response.json()["reason_code"] == "UDS_PARSER_UNAVAILABLE"


def test_pinned_package_keeps_observed_graphs_without_yaml(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "deploy" / "uds-package.yaml"
    parsed = LOAD_UDS_PACKAGE(path)
    parsed_client = _client(path, monkeypatch)
    parsed_routes = {route: parsed_client.get(route).json() for route in ROUTES}
    monkeypatch.setitem(sys.modules, "yaml", None)
    fallback = LOAD_UDS_PACKAGE(path)
    assert fallback["state"] == "OBSERVED"
    assert fallback["expose_layout"] == parsed["expose_layout"] == "SPEC_EXPOSE_PINNED_LEGACY"
    assert len(fallback["allow"]) == len(parsed["allow"]) == 4
    assert len(fallback["expose"]) == len(parsed["expose"]) == 1
    for section, fields in (
        ("allow", ("direction", "remoteNamespace", "remoteGenerated", "port", "description")),
        ("expose", ("service", "host", "gateway", "port", "description")),
    ):
        assert [{key: item[key] for key in fields if key in item} for item in fallback[section]] == [
            {key: item[key] for key in fields if key in item} for item in parsed[section]
        ]
    client = _client(path, monkeypatch)
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 200
        assert response.json() == parsed_routes[route]


def test_changed_package_cannot_use_pinned_fallback(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "deploy" / "uds-package.yaml"
    path = tmp_path / "changed.yaml"
    path.write_bytes(source.read_bytes() + b"\n# synthetic revision\n")
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert LOAD_UDS_PACKAGE(path)["reason_code"] == "UDS_PARSER_UNAVAILABLE"
