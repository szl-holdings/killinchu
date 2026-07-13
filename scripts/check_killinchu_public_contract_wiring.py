#!/usr/bin/env python3
"""Fail closed when Killinchu's critical contract is not source-complete."""
from __future__ import annotations

import argparse
import json
import pathlib


def evaluate(repo_root: pathlib.Path) -> list[str]:
    errors: list[str] = []
    module = repo_root / "killinchu_public_contracts.py"
    serve = repo_root / "serve.py"
    docker = repo_root / "Dockerfile"
    workflow = repo_root / ".github" / "workflows" / "hf-sync.yml"

    for path in (module, serve, docker, workflow):
        if not path.is_file():
            errors.append(f"missing required source: {path.relative_to(repo_root)}")
    if errors:
        return errors

    serve_text = serve.read_text(encoding="utf-8")
    import_marker = "import killinchu_public_contracts as _killinchu_public_contracts"
    register_marker = '_killinchu_public_contracts.register(app, ns="killinchu")'
    entrypoint = 'if __name__ == "__main__":'
    for marker in (import_marker, register_marker):
        if serve_text.count(marker) != 1:
            errors.append(f"serve.py must contain exactly one {marker!r}")
    if all(marker in serve_text for marker in (import_marker, register_marker, entrypoint)):
        if not (
            serve_text.index(import_marker)
            < serve_text.index(register_marker)
            < serve_text.index(entrypoint)
        ):
            errors.append("public contracts must register before the server entrypoint")

    docker_text = docker.read_text(encoding="utf-8")
    docker_marker = "COPY killinchu_public_contracts.py ./"
    if docker_text.count(docker_marker) != 1:
        errors.append(f"Dockerfile must contain exactly one {docker_marker!r}")

    workflow_text = workflow.read_text(encoding="utf-8")
    for marker in (
        "check_killinchu_public_contract_wiring.py",
        "check_killinchu_public_contracts.py",
        "post-deploy-contracts:",
    ):
        if marker not in workflow_text:
            errors.append(f"hf-sync workflow missing {marker!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path("."))
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    errors = evaluate(root)
    print(json.dumps({"schema": "szl.killinchu.contract-wiring-check/v1", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
