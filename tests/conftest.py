# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings. ORCID: 0009-0001-0110-4173
"""Keep lean FastAPI-stub suites isolated from the installed-package suite.

The two OSINT regression modules intentionally install a tiny tuple-route
``fastapi`` stub so the dedicated offline workflow can run with pytest alone.
When the repository's full test environment has the real FastAPI package
installed, importing those modules would replace the real package in
``sys.modules`` and make later route-based suites order-dependent.

Ignore the stub-only modules before import in that environment. The dedicated
OSINT workflow does not install FastAPI, so both modules remain collected and
exercise their offline contracts normally.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_STUB_ONLY_MODULES = frozenset({"test_osint.py", "test_killinchu_archive.py"})


def _real_fastapi_is_available() -> bool:
    try:
        return importlib.util.find_spec("fastapi") is not None
    except (ImportError, ValueError):
        return False


_REAL_FASTAPI_AVAILABLE = _real_fastapi_is_available()


def pytest_ignore_collect(collection_path: Path, config: object) -> bool:
    """Prevent stub installation only when the real package suite is active."""
    del config
    return (
        _REAL_FASTAPI_AVAILABLE
        and collection_path.name in _STUB_ONLY_MODULES
    )
