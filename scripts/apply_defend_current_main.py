#!/usr/bin/env python3
"""Idempotently wire the source-bound Defend plane into current Killinchu.

This script changes only runtime assembly files. It does not modify workflow
files, provider settings, secrets, or legacy Spaces. The module and focused
tests are already staged on the feature branch; this transaction registers the
module before the SPA catch-all, adds it to both explicit Docker assemblies,
and removes the obsolete presentation-only resilience redirect.
"""
from __future__ import annotations

from pathlib import Path

REGISTRATION_MARKER = "KILLINCHU_DEFEND_PLANE_V1"
APP_ANCHOR = 'app = FastAPI(title="Killinchu — Andean Drone Intelligence", version="1.0.0")\n'
REGISTRATION = r'''

# KILLINCHU_DEFEND_PLANE_V1 — same-origin Aegis/Sentra consolidation.
# This source-bound module registers before the SPA catch-all. Failure remains
# visible through protected deployment smoke probes; no presentation fallback
# can satisfy the API contract.
try:
    import killinchu_defend_plane as _killinchu_defend_plane

    _killinchu_defend_status = _killinchu_defend_plane.register(
        app,
        ns="killinchu",
    )
    print(
        f"[killinchu] Defend plane wired ({_killinchu_defend_status})",
        file=sys.stderr,
    )
except Exception as _killinchu_defend_error:
    _killinchu_defend_status = (
        f"defend-plane-not-wired:{_killinchu_defend_error!r}"
    )
    print(
        f"[killinchu] Defend plane NOT mounted "
        f"({_killinchu_defend_error!r})",
        file=sys.stderr,
    )
'''

COPY_LINE = "COPY killinchu_defend_plane.py ./killinchu_defend_plane.py"
COPY_BLOCK = (
    "# Consolidated Aegis/Sentra capability plane — real same-origin UI, API, state and receipts.\n"
    f"{COPY_LINE}\n"
)
DOCKER_ANCHOR = "# Shared Spaces modules (Dev2+3)"
OBSOLETE_REDIRECT = '    "/resilience": "/elite",\n'


def replace_once(path: Path, old: str, new: str, *, label: str) -> bool:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one {label}; found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def wire_server(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if REGISTRATION_MARKER in text:
        return False
    return replace_once(
        path,
        APP_ANCHOR,
        APP_ANCHOR + REGISTRATION,
        label="FastAPI app anchor",
    )


def wire_dockerfile(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if COPY_LINE in text:
        return False
    return replace_once(
        path,
        DOCKER_ANCHOR,
        COPY_BLOCK + DOCKER_ANCHOR,
        label="Shared Spaces Docker anchor",
    )


def remove_obsolete_redirect(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    count = text.count(OBSOLETE_REDIRECT)
    if count == 0:
        return False
    if count != 1:
        raise SystemExit(f"{path}: duplicate obsolete resilience redirects: {count}")
    path.write_text(text.replace(OBSOLETE_REDIRECT, "", 1), encoding="utf-8")
    return True


def main() -> int:
    changes: list[str] = []
    for name in ("serve.py", "deploy/space/serve.py"):
        if wire_server(Path(name)):
            changes.append(name)
    for name in ("Dockerfile", "deploy/space/Dockerfile"):
        if wire_dockerfile(Path(name)):
            changes.append(name)
    if remove_obsolete_redirect(Path("killinchu_nav_wireup.py")):
        changes.append("killinchu_nav_wireup.py")

    for required in (
        Path("killinchu_defend_plane.py"),
        Path("tests/test_killinchu_defend_plane.py"),
        Path("tests/test_resilience_route_convergence.py"),
    ):
        if not required.is_file():
            raise SystemExit(f"required Defend artifact missing: {required}")

    print(
        "DEFEND CURRENT-MAIN WIRING "
        + ("UPDATED " + ", ".join(changes) if changes else "ALREADY EXACT")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
