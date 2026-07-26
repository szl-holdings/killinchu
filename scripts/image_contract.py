#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate and verify Killinchu's deterministic container image contract.

The repository-root Dockerfile is canonical.  The Hugging Face deployment
Dockerfile is a generated, byte-for-byte mirror so the two build paths cannot
silently ship different runtimes.  The checked-in JSON manifest records the
canonical digest, every local COPY/ADD source, and every local module whose
``register*`` entrypoint is invoked by ``serve.py``.

Normal mode refreshes the mirror and manifest.  ``--check`` is read-only and
fails when either generated file is stale or when a runtime source/registered
organ is missing from the canonical image.
"""

from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable

SCHEMA_VERSION = 1
CANONICAL_DOCKERFILE = "Dockerfile"
MIRROR_DOCKERFILE = "deploy/space/Dockerfile"
MANIFEST_PATH = "deploy/image-contract.json"
ENTRYPOINT = "serve.py"
_REMOTE_SOURCE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_WAVE_ORGANS = re.compile(r"^_WAVE\d+_ORGANS$")


class ContractError(RuntimeError):
    """The checked image contract is incomplete or inconsistent."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def logical_dockerfile_lines(text: str) -> Iterable[str]:
    """Yield Dockerfile instructions with backslash continuations folded."""
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if raw.rstrip().endswith("\\"):
            buffer += raw.rstrip()[:-1] + " "
            continue
        buffer += raw
        yield buffer
        buffer = ""
    if buffer:
        yield buffer


def copy_sources(dockerfile_text: str) -> list[str]:
    """Return sorted unique local COPY/ADD sources from a Dockerfile."""
    sources: set[str] = set()
    for instruction in logical_dockerfile_lines(dockerfile_text):
        match = re.match(
            r"^\s*(COPY|ADD)\s+(.*)$", instruction, re.IGNORECASE
        )
        if not match:
            continue
        verb = match.group(1).upper()
        remainder = match.group(2).strip()
        if remainder.startswith("["):
            try:
                tokens = json.loads(remainder)
            except json.JSONDecodeError as exc:
                raise ContractError(
                    f"unparseable JSON-form {verb} instruction: {instruction}"
                ) from exc
            if not isinstance(tokens, list) or not all(
                isinstance(token, str) for token in tokens
            ):
                raise ContractError(
                    f"invalid JSON-form {verb} instruction: {instruction}"
                )
        else:
            try:
                tokens = shlex.split(remainder)
            except ValueError as exc:
                raise ContractError(
                    f"unparseable {verb} instruction: {instruction}"
                ) from exc

        real_tokens: list[str] = []
        external_stage = False
        for token in tokens:
            if token.lower().startswith("--from="):
                external_stage = True
                break
            if token.startswith("--"):
                continue
            real_tokens.append(token)
        if external_stage:
            continue
        if len(real_tokens) < 2:
            raise ContractError(
                f"{verb} instruction has no source and destination: {instruction}"
            )
        for source in real_tokens[:-1]:
            if verb == "ADD" and _REMOTE_SOURCE.match(source):
                continue
            source_posix = source.replace("\\", "/")
            trailing_slash = source_posix.endswith("/")
            normalized = PurePosixPath(source_posix).as_posix()
            if normalized.startswith("/") or ".." in PurePosixPath(normalized).parts:
                raise ContractError(
                    f"COPY/ADD source escapes the build context: {source}"
                )
            if trailing_slash and normalized != ".":
                normalized += "/"
            sources.add(normalized)
    return sorted(sources)


def _local_module(repo_root: Path, module: str) -> str | None:
    root_name = module.split(".", 1)[0]
    return root_name if (repo_root / f"{root_name}.py").is_file() else None


def registered_modules(
    serve_text: str, repo_root: Path
) -> tuple[list[str], list[str]]:
    """Find local registration modules and explicit wave organs.

    Static imports and ``from x import register...`` calls are resolved through
    the AST.  The repository's dynamic ``_WAVEn_ORGANS`` lists are also read
    from literal values, matching the runtime registration loop.  Wave entries
    are the fail-closed organ contract: unlike legacy optional imports, every
    named wave organ must exist.
    """
    try:
        tree = ast.parse(serve_text, filename=ENTRYPOINT)
    except SyntaxError as exc:
        raise ContractError(f"{ENTRYPOINT} is not valid Python: {exc}") from exc

    module_aliases: dict[str, str] = {}
    function_aliases: dict[str, str] = {}
    modules: set[str] = set()
    wave_organs: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = _local_module(repo_root, alias.name)
                if local:
                    module_aliases[alias.asname or alias.name.split(".", 1)[0]] = local
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            local = _local_module(repo_root, node.module)
            if not local:
                continue
            for alias in node.names:
                bound_name = alias.asname or alias.name
                if alias.name.startswith("register"):
                    function_aliases[bound_name] = local
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if not isinstance(value, (ast.List, ast.Tuple)):
                continue
            if not any(
                isinstance(target, ast.Name) and _WAVE_ORGANS.match(target.id)
                for target in targets
            ):
                continue
            for item in value.elts:
                if not isinstance(item, (ast.List, ast.Tuple)) or not item.elts:
                    continue
                first = item.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    local = _local_module(repo_root, first.value)
                    if not local:
                        raise ContractError(
                            f"registered organ module is missing: {first.value}.py"
                        )
                    wave_organs.add(local)
                    modules.add(local)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("register")
            and isinstance(node.func.value, ast.Name)
        ):
            module = module_aliases.get(node.func.value.id)
            if module:
                modules.add(module)
        elif isinstance(node.func, ast.Name):
            module = function_aliases.get(node.func.id)
            if module:
                modules.add(module)

    return sorted(modules), sorted(wave_organs)


def _matching_paths(repo_root: Path, source: str) -> list[Path]:
    pattern = str(repo_root / Path(*PurePosixPath(source).parts))
    if any(char in source for char in "*?[]"):
        return [Path(match) for match in glob.glob(pattern)]
    path = Path(pattern)
    return [path] if path.exists() else []


def validate_copy_sources(repo_root: Path, sources: list[str]) -> None:
    missing = [source for source in sources if not _matching_paths(repo_root, source)]
    if missing:
        details = "\n".join(f"  - {source}" for source in missing)
        raise ContractError(f"canonical Dockerfile COPY/ADD sources are missing:\n{details}")


def source_covers_path(source: str, target: str) -> bool:
    """Return whether a COPY source includes a repo-relative target path."""
    source_path = PurePosixPath(source)
    target_path = PurePosixPath(target)
    if source_path.as_posix() in {".", "./"}:
        return True
    if any(char in source for char in "*?[]"):
        return target_path.match(source)
    if source.endswith("/"):
        try:
            target_path.relative_to(source_path)
            return True
        except ValueError:
            return False
    return source_path == target_path


def validate_registered_modules(modules: list[str], sources: list[str]) -> None:
    missing = [
        f"{module}.py"
        for module in modules
        if not any(source_covers_path(source, f"{module}.py") for source in sources)
    ]
    if missing:
        details = "\n".join(f"  - {path}" for path in missing)
        raise ContractError(
            "registered organ modules are absent from canonical Dockerfile COPY:\n"
            f"{details}"
        )


def expected_outputs(repo_root: Path) -> tuple[bytes, bytes]:
    canonical_path = repo_root / CANONICAL_DOCKERFILE
    entrypoint_path = repo_root / ENTRYPOINT
    if not canonical_path.is_file():
        raise ContractError(f"canonical Dockerfile is missing: {CANONICAL_DOCKERFILE}")
    if not entrypoint_path.is_file():
        raise ContractError(f"registration entrypoint is missing: {ENTRYPOINT}")

    canonical_bytes = canonical_path.read_bytes()
    canonical_text = canonical_bytes.decode("utf-8")
    sources = copy_sources(canonical_text)
    validate_copy_sources(repo_root, sources)
    registered, organs = registered_modules(
        entrypoint_path.read_text(encoding="utf-8"), repo_root
    )
    validate_registered_modules(registered, sources)

    digest = sha256_bytes(canonical_bytes)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "canonical_dockerfile": {
            "path": CANONICAL_DOCKERFILE,
            "sha256": digest,
        },
        "entrypoint": ENTRYPOINT,
        "hf_deploy_dockerfile": {
            "generated_from": CANONICAL_DOCKERFILE,
            "path": MIRROR_DOCKERFILE,
            "sha256": digest,
        },
        "local_copy_sources": sources,
        "registered_runtime_modules": registered,
        "registered_organs": organs,
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return canonical_bytes, manifest_bytes


def refresh(repo_root: Path) -> None:
    mirror_bytes, manifest_bytes = expected_outputs(repo_root)
    mirror_path = repo_root / MIRROR_DOCKERFILE
    manifest_path = repo_root / MANIFEST_PATH
    mirror_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    mirror_path.write_bytes(mirror_bytes)
    manifest_path.write_bytes(manifest_bytes)
    print(
        "image-contract: generated "
        f"{MIRROR_DOCKERFILE} and {MANIFEST_PATH}"
    )


def check(repo_root: Path) -> None:
    expected_mirror, expected_manifest = expected_outputs(repo_root)
    stale: list[str] = []
    for relative_path, expected in (
        (MIRROR_DOCKERFILE, expected_mirror),
        (MANIFEST_PATH, expected_manifest),
    ):
        path = repo_root / relative_path
        if not path.is_file() or path.read_bytes() != expected:
            stale.append(relative_path)
    if stale:
        details = "\n".join(f"  - {path}" for path in stale)
        raise ContractError(
            "generated image contract is stale or divergent:\n"
            f"{details}\n"
            "run: python scripts/image_contract.py"
        )
    manifest = json.loads(expected_manifest)
    print(
        "image-contract: PASS "
        f"({len(manifest['local_copy_sources'])} COPY/ADD sources, "
        f"{len(manifest['registered_runtime_modules'])} registration modules, "
        f"{len(manifest['registered_organs'])} wave organs, "
        "HF deploy Dockerfile byte-identical)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify without changing generated files",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.check:
            check(root)
        else:
            refresh(root)
    except (ContractError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"image-contract: FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
