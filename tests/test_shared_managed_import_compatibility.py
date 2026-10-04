#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Shared import-path compatibility using full source and synthetic local stores.

These tests do not enable managed storage on Killinchu or claim a live route
result. The optional policy must stay dormant outside its exact managed mode.
"""

import builtins
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANAGED = "private-dataset-v1"
MODULES = ("szl_kc_jpt", "szl_unay_routes")


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    def denied(*_args, **_kwargs):
        raise AssertionError("network/process effect forbidden in shared source compatibility tests")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("GDW_DURABLE_STORAGE", raising=False)
    monkeypatch.delenv("A11OY_SPINE_DIRS", raising=False)
    monkeypatch.setenv("JPT_LEDGER_PATH", str(tmp_path / "absent-synthetic-ledger.jsonl"))

    class Store:
        backend = "synthetic-store"

        def __init__(self, **kwargs): self.options = kwargs
        def stats(self): return {"entries": 0}

    class Replicator:
        enabled = False

        def __init__(self, **kwargs): self.options = kwargs

    # The source modules' unrelated service dependencies stay synthetic. No
    # database is opened, while their complete import and registration run.
    dependencies = {
        "fastapi": {"Request": object},
        "fastapi.responses": {"JSONResponse": lambda value, **kwargs: (value, kwargs)},
        "szl_unay": {"UnayStore": Store, "__version__": "synthetic"},
        "szl_khipu_lmdb": {"KhipuLMDB": Store},
        "szl_khipu_replicate": {"Replicator": Replicator},
        "lmdb": {"version": lambda: (0, 0, 0)},
    }
    for name, members in dependencies.items():
        module = ModuleType(name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, module)


def load_source(name, here, monkeypatch):
    """Load the full current module with a disposable deployed-file location."""
    here.mkdir(parents=True, exist_ok=True)
    path = here / (name + ".py")
    path.write_bytes((ROOT / (name + ".py")).read_bytes())
    unique = "_shared_compatibility_" + name
    spec = importlib.util.spec_from_file_location(unique, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, unique, module)
    spec.loader.exec_module(module)
    return module


def intercept_policy_import(monkeypatch, policy=None):
    original = builtins.__import__
    calls = []

    def checked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "gdw_durable_source":
            calls.append((name, tuple(fromlist), level))
            if policy is None:
                raise ModuleNotFoundError("synthetic absent managed policy", name=name)
            return policy
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", checked)
    return calls


def legacy_tree(tmp_path):
    here = tmp_path / "deploy"
    extra = tmp_path / "explicit-spine"
    siblings = [tmp_path / relative for relative in ("a11oy_pr", "src/a11oy", "a11W", "a11oy_e")]
    for path in (here, extra, *siblings): path.mkdir(parents=True)
    return here, extra, siblings


@pytest.mark.parametrize("mode", [None, "", "legacy", "private-dataset-v2", " private-dataset-v1"])
def test_jpt_legacy_search_order_and_dedup_need_no_managed_policy(tmp_path, monkeypatch, mode):
    here, extra, siblings = legacy_tree(tmp_path)
    if mode is not None: monkeypatch.setenv("GDW_DURABLE_STORAGE", mode)
    monkeypatch.setenv("A11OY_SPINE_DIRS", os.pathsep.join(map(str, [extra, here, extra, tmp_path / "missing"])))
    calls = intercept_policy_import(monkeypatch)
    module = load_source("szl_kc_jpt", here, monkeypatch)
    assert module._spine_search_dirs() == [str(here), str(extra), *map(str, siblings)]
    assert calls == []
    assert not (tmp_path / "absent-synthetic-ledger.jsonl").exists()


@pytest.mark.parametrize("mode", [None, "", "legacy", "private-dataset-v2", " private-dataset-v1"])
def test_unay_legacy_parent_and_here_precedence_need_no_managed_policy(tmp_path, monkeypatch, mode):
    here = tmp_path / "deploy"
    if mode is not None: monkeypatch.setenv("GDW_DURABLE_STORAGE", mode)
    before = list(sys.path)
    calls = intercept_policy_import(monkeypatch)
    module = load_source("szl_unay_routes", here, monkeypatch)
    assert module._IMPORT_PATHS == (str(here), str(tmp_path))
    assert sys.path == [str(tmp_path), str(here), *before]
    assert calls == []


def test_unay_keeps_existing_legacy_path_positions(tmp_path, monkeypatch):
    here = tmp_path / "deploy"
    before = [str(here), "synthetic-separator", str(tmp_path), *sys.path]
    monkeypatch.setattr(sys, "path", list(before))
    calls = intercept_policy_import(monkeypatch)
    load_source("szl_unay_routes", here, monkeypatch)
    assert sys.path == before and calls == []


@pytest.mark.parametrize("name", MODULES)
def test_explicit_managed_mode_without_policy_fails_before_path_mutation(tmp_path, monkeypatch, name):
    monkeypatch.setenv("GDW_DURABLE_STORAGE", MANAGED)
    before = list(sys.path)
    calls = intercept_policy_import(monkeypatch)
    with pytest.raises(ModuleNotFoundError) as failure:
        module = load_source(name, tmp_path / "deploy", monkeypatch)
        module._spine_search_dirs()
    assert failure.value.name == "gdw_durable_source"
    assert calls == [("gdw_durable_source", ("managed_import_paths",), 0)]
    assert sys.path == before


@pytest.mark.parametrize("name", MODULES)
def test_rejected_managed_paths_do_not_fall_back_to_legacy_roots(tmp_path, monkeypatch, name):
    class PolicyRejected(RuntimeError): pass

    requested = []

    def reject(paths):
        requested.append(list(paths))
        raise PolicyRejected("synthetic denied source root")

    here, extra, _siblings = legacy_tree(tmp_path)
    monkeypatch.setenv("GDW_DURABLE_STORAGE", MANAGED)
    monkeypatch.setenv("A11OY_SPINE_DIRS", str(extra))
    before = list(sys.path)
    calls = intercept_policy_import(monkeypatch, SimpleNamespace(managed_import_paths=reject))
    with pytest.raises(PolicyRejected):
        module = load_source(name, here, monkeypatch)
        module._spine_search_dirs()
    assert requested == [[str(here), str(extra)] if name == "szl_kc_jpt" else [str(here)]]
    assert len(calls) == 1 and sys.path == before


def test_jpt_managed_mode_uses_only_policy_result(tmp_path, monkeypatch):
    here, extra, siblings = legacy_tree(tmp_path)
    requested = []
    admitted = [str(here), str(extra)]

    def allow(paths):
        requested.append(list(paths))
        return admitted

    monkeypatch.setenv("GDW_DURABLE_STORAGE", MANAGED)
    monkeypatch.setenv("A11OY_SPINE_DIRS", str(extra))
    calls = intercept_policy_import(monkeypatch, SimpleNamespace(managed_import_paths=allow))
    module = load_source("szl_kc_jpt", here, monkeypatch)
    assert module._spine_search_dirs() is admitted
    assert requested == [[str(here), str(extra)]] and len(calls) == 1
    assert not set(map(str, siblings)).intersection(admitted)


def test_unay_managed_mode_inserts_only_policy_admitted_here(tmp_path, monkeypatch):
    here = tmp_path / "deploy"
    requested = []

    def allow(paths):
        requested.append(list(paths))
        return [str(here)]

    monkeypatch.setenv("GDW_DURABLE_STORAGE", MANAGED)
    before = list(sys.path)
    calls = intercept_policy_import(monkeypatch, SimpleNamespace(managed_import_paths=allow))
    load_source("szl_unay_routes", here, monkeypatch)
    assert requested == [[str(here)]] and len(calls) == 1
    assert sys.path == [str(here), *before] and str(tmp_path) not in sys.path


class App:
    def __init__(self):
        self.routes = []
        self.router = self

    def add_api_route(self, path, endpoint, *, methods): self.routes.append((methods[0], path))
    def add_route(self, path, endpoint, *, methods): self.routes.append((methods[0], path))

    def _decorator(self, method, path):
        def register(endpoint):
            self.routes.append((method, path))
            return endpoint
        return register

    def get(self, path): return self._decorator("GET", path)
    def post(self, path): return self._decorator("POST", path)


def test_legacy_jpt_registers_all_five_killinchu_routes_without_policy(tmp_path, monkeypatch):
    calls = intercept_policy_import(monkeypatch)
    module = load_source("szl_kc_jpt", tmp_path / "deploy", monkeypatch)
    app = App()
    paths = module.register(app, ns="killinchu")
    suffixes = ["manifest", "benchmark", "nodes", "ledger", "summary"]
    assert paths == ["/api/killinchu/v1/jpt/" + suffix for suffix in suffixes]
    assert app.routes == [("POST" if suffix == "benchmark" else "GET", path)
                          for suffix, path in zip(suffixes, paths)]
    assert calls == []


def test_legacy_unay_registers_all_twelve_killinchu_routes_without_policy(tmp_path, monkeypatch):
    calls = intercept_policy_import(monkeypatch)
    module = load_source("szl_unay_routes", tmp_path / "deploy", monkeypatch)
    monkeypatch.setattr(module, "_pick_data_dir", lambda: str(tmp_path / "synthetic-stores"))
    monkeypatch.setattr(module, "_restore_snapshot", lambda *_args: False)
    app = App()
    result = module.register(app, ns="killinchu")
    expected = [("GET", "unay/healthz"), ("GET", "unay/stats"), ("POST", "unay/remember"),
                ("POST", "unay/recall"), ("GET", "unay/recall"), ("GET", "unay/verify"),
                ("GET", "khipu/lmdb/stats"), ("POST", "khipu/lmdb/append"),
                ("GET", "khipu/lmdb/verify"), ("GET", "khipu/lmdb/tail"),
                ("POST", "khipu/replicate"), ("GET", "khipu/replicate/status")]
    assert app.routes == [(method, "/api/killinchu/v2/" + suffix) for method, suffix in expected]
    assert result["registered"] is True and result["ns"] == "killinchu"
    assert result["replication_enabled"] is False and result["snapshot_restored"] is False
    assert calls == [] and not (tmp_path / "synthetic-stores").exists()


def test_native_copy_guard_distinguishes_absent_policy_from_present_local_source(tmp_path):
    guard_path = ROOT / ".github/scripts/copy_completeness.py"
    spec = importlib.util.spec_from_file_location("_shared_copy_completeness", guard_path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    root = tmp_path / "copy-inputs"
    root.mkdir()
    entrypoints = [name + ".py" for name in MODULES]
    for relative in entrypoints:
        source = (ROOT / relative).read_text()
        assert "gdw_durable_source" in guard._extract_imports_from_source(source)
        (root / relative).write_text(source)
    absent = guard.collect_transitive_local_imports(entrypoints, str(root), guard._stdlib_names())
    assert absent == {relative: set() for relative in entrypoints}
    # A dependency becomes mandatory as soon as it is actual local source;
    # the existing guard has no special exemption for this module or branch.
    (root / "gdw_durable_source.py").write_text("# synthetic local policy\n")
    present = guard.collect_transitive_local_imports(entrypoints, str(root), guard._stdlib_names())
    assert present == {relative: {"gdw_durable_source"} for relative in entrypoints}
