"""Isolate backend source tests from the unrelated background provider probes."""
import urllib.request

import pytest


def pytest_configure(config):
    patch = pytest.MonkeyPatch()
    patch.setenv("SZL_READINESS_WARM", "0")

    def unavailable(*args, **kwargs):
        raise OSError("provider access is blocked for offline backend source tests")

    patch.setattr(urllib.request, "urlopen", unavailable)
    import szl_readiness
    patch.setattr(szl_readiness, "_kick_background_build", lambda ns: None)
    config._szl_backend_read_offline_patch = patch


def pytest_unconfigure(config):
    patch = getattr(config, "_szl_backend_read_offline_patch", None)
    if patch is not None:
        patch.undo()
