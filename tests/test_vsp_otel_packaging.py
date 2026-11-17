# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Exercise telemetry from explicit runtime COPY files, not the source checkout."""

import ast
import json
import re
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FILES = {"vsp_otel/__init__.py", "vsp_otel/middleware.py"}
DOCKERFILES = ("Dockerfile", "deploy/space/Dockerfile")


def test_production_otel_exporter_has_a_hash_locked_nonoptional_runtime_closure():
    """Real spans require SDK + proto/grpc, not just vsp_otel COPY or API."""
    sources = ROOT / "deploy/space/requirements"
    direct = (sources / "space-otel.in").read_text(encoding="utf-8")
    locked = (sources / "space-otel.txt").read_text(encoding="utf-8")
    assert "uv pip compile" in locked.splitlines()[1]
    versions = {
        "opentelemetry-api": "1.45.2",
        "opentelemetry-sdk": "1.45.2",
        "opentelemetry-exporter-otlp-proto-grpc": "1.45.2",
    }
    for name, version in versions.items():
        assert f"{name}=={version}" in direct
        # Each exact version is accompanied by a real SHA-256 hash.
        rows = locked.splitlines()
        exact = [i for i, line in enumerate(rows)
                 if line.startswith(f"{name}=={version} ")]
        assert len(exact) == 1, name
        assert "--hash=sha256:" in rows[exact[0] + 1]
        assert re.search(r"[0-9a-f]{64}", rows[exact[0] + 1]), name
        assert len(re.findall(rf"(?m)^{re.escape(name)}==", locked)) == 1
    for dependency in ("grpcio", "protobuf", "googleapis-common-protos",
                       "opentelemetry-proto", "opentelemetry-semantic-conventions"):
        assert re.search(rf"(?m)^{re.escape(dependency)}==", locked), dependency
    assert "--extra-index-url" not in locked
    assert "--trusted-host" not in locked
    for dockerfile in DOCKERFILES:
        text = (ROOT / dockerfile).read_text(encoding="utf-8")
        install = "RUN pip install --no-cache-dir --require-hashes -r /tmp/pins/space-otel.txt"
        assert text.count(install) == 1
        assert "COPY deploy/space/requirements/ /tmp/pins/" in text
        assert text.index("-r /tmp/pins/space-core.txt") < text.index(install)
        assert not any("|| true" in line for line in text.splitlines() if install in line)
        assert text.count("RUN python -c \"import grpc; from opentelemetry.sdk.trace import TracerProvider;") == 1
        assert "from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter" in text

    tracer = (ROOT / "vsp_otel/middleware.py").read_text(encoding="utf-8")
    assert "from opentelemetry.sdk.trace import TracerProvider" in tracer
    assert "from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import" in tracer
    assert "if not self.endpoint_policy[\"allowed\"]:" in tracer


def _packaged_runtime(tmp_path: Path, dockerfile: str) -> Path:
    parser = runpy.run_path(str(ROOT / ".github/shared-file-drift-check.py"))
    copied = set()
    source = (ROOT / dockerfile).read_text(encoding="utf-8")
    for instruction in parser["logical_lines"](source):
        if not instruction.upper().startswith("COPY "):
            continue
        sources = parser["parse_copy_sources"](instruction)
        selected = PACKAGE_FILES.intersection(sources)
        if not selected:
            continue
        tokens = shlex.split(instruction)
        assert not any(token.startswith("--from") for token in tokens)
        assert tokens[-1] == "./vsp_otel/"
        destination = tmp_path / "vsp_otel"
        destination.mkdir(exist_ok=True)
        for relative in selected:
            shutil.copyfile(ROOT / relative, destination / Path(relative).name)
            copied.add(relative)
    assert copied == PACKAGE_FILES, f"{dockerfile} is missing {sorted(PACKAGE_FILES - copied)}"
    return tmp_path


def _run_packaged(runtime: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(runtime), *args],
        cwd=runtime,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("entrypoint", ["serve.py", "deploy/space/serve.py"])
def test_serve_installs_the_package_guarded_by_this_contract(entrypoint):
    tree = ast.parse((ROOT / entrypoint).read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "vsp_otel.middleware"
        and any(alias.name == "install" for alias in node.names)
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
@pytest.mark.parametrize("flags", ["00", "01"])
def test_packaged_asgi_propagates_trace_without_claiming_delivery(tmp_path, dockerfile, flags):
    runtime = _packaged_runtime(tmp_path, dockerfile)
    result = _run_packaged(runtime, r'''
import json
from pathlib import Path
import sys
runtime = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(runtime))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import vsp_otel.middleware as otel
assert Path(otel.__file__).resolve().parent == runtime / "vsp_otel"
app = FastAPI()
otel.install(app, service_name="killinchu-packaging-test", endpoint=None)
@app.get("/probe")
def probe():
    return otel.status(app)
incoming = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-" + sys.argv[2]
with TestClient(app) as client:
    response = client.get("/probe", headers={"traceparent": incoming})
    assert response.status_code == 200
    parent = otel.parse_traceparent(incoming)
    child = otel.parse_traceparent(response.headers["traceparent"])
    assert child["trace_id"] == parent["trace_id"]
    assert child["parent_id"] != parent["parent_id"]
    assert child["flags"] == parent["flags"]
    body = response.json()
    assert body["propagation"] == "READY"
    assert body["export"] == "IN-PROCESS-ONLY"
    assert body["endpoint"]["state"] == "NOT-CONFIGURED"
    assert body["receipt_minted"] is False
    malformed = client.get("/probe", headers={"traceparent": "invalid"})
    assert otel.parse_traceparent(malformed.headers["traceparent"]) is not None
print(json.dumps({"packaged_import": True, "propagation": "READY", "delivery_witnessed": False}))
''', flags)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["delivery_witnessed"] is False


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_missing_packaged_module_cannot_fall_back_to_source_checkout(tmp_path, dockerfile):
    runtime = _packaged_runtime(tmp_path, dockerfile)
    (runtime / "vsp_otel/middleware.py").unlink()
    result = _run_packaged(runtime, r'''
import sys
sys.path.insert(0, sys.argv[1])
import vsp_otel.middleware
''')
    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr
    assert "vsp_otel.middleware" in result.stderr
