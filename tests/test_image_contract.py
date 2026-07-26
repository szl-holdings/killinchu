# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import image_contract


def _write_minimal_repo(root: Path) -> None:
    (root / "deploy/space").mkdir(parents=True)
    (root / "alpha.py").write_text(
        "def register(app, **kwargs):\n    return app\n", encoding="utf-8"
    )
    (root / "serve.py").write_text(
        "import alpha as organ\norgan.register(None)\n", encoding="utf-8"
    )
    (root / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "COPY serve.py alpha.py ./\n"
        'CMD ["python", "serve.py"]\n',
        encoding="utf-8",
    )


def test_refresh_and_check_are_deterministic(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    image_contract.refresh(tmp_path)
    first_manifest = (tmp_path / image_contract.MANIFEST_PATH).read_bytes()

    image_contract.check(tmp_path)
    image_contract.refresh(tmp_path)

    assert (tmp_path / image_contract.MIRROR_DOCKERFILE).read_bytes() == (
        tmp_path / image_contract.CANONICAL_DOCKERFILE
    ).read_bytes()
    assert (tmp_path / image_contract.MANIFEST_PATH).read_bytes() == first_manifest
    manifest = json.loads(first_manifest)
    assert manifest["registered_organs"] == []
    assert manifest["registered_runtime_modules"] == ["alpha"]
    assert manifest["local_copy_sources"] == ["alpha.py", "serve.py"]


def test_missing_copy_source_fails(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY serve.py missing.py ./\n",
        encoding="utf-8",
    )

    with pytest.raises(image_contract.ContractError, match="sources are missing"):
        image_contract.expected_outputs(tmp_path)


def test_missing_registered_organ_fails(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / "serve.py").write_text(
        "_WAVE17_ORGANS = [('missing_organ', 'label', '/route')]\n",
        encoding="utf-8",
    )

    with pytest.raises(
        image_contract.ContractError, match="registered organ module is missing"
    ):
        image_contract.expected_outputs(tmp_path)


def test_registered_organ_without_copy_fails(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY serve.py ./\n",
        encoding="utf-8",
    )

    with pytest.raises(
        image_contract.ContractError,
        match="registered organ modules are absent",
    ):
        image_contract.expected_outputs(tmp_path)


def test_divergent_hf_dockerfile_fails(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    image_contract.refresh(tmp_path)
    (tmp_path / image_contract.MIRROR_DOCKERFILE).write_text(
        "FROM scratch\n", encoding="utf-8"
    )

    with pytest.raises(image_contract.ContractError, match="stale or divergent"):
        image_contract.check(tmp_path)


def test_divergent_manifest_fails(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    image_contract.refresh(tmp_path)
    (tmp_path / image_contract.MANIFEST_PATH).write_text("{}\n", encoding="utf-8")

    with pytest.raises(image_contract.ContractError, match="stale or divergent"):
        image_contract.check(tmp_path)


def test_checked_in_contract_is_current() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/image_contract.py"),
            "--check",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
