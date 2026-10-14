# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Fail-closed binding of the governed code engine that serve.py mounts.

Invariant: serve.py mounts ``/api/killinchu/v1/code/*`` only from the reviewed
vendored ``a11oy_code_engine`` (the a11oy<->killinchu shared-source copy whose
bytes the payload manifest pins), and only when its ``governed_turn`` carries the
deny-by-default two-person ``allow_exec`` chokepoint. An importable
``szl_substrate`` engine is never preferred, whatever it exposes: substrate's copy
(checked at szl-substrate main ``98ebd88d``) has no ``allow_exec`` and its
``register()`` checks no operator credential.

How this is tested without importing all of serve.py:
  * ``_run_serve_block`` extracts the real code-engine block of serve.py between
    its BEGIN/END markers and executes those exact bytes in an isolated namespace
    with an inert app, signer and verifier;
  * fake ``szl_substrate`` packages and fake vendored engines are placed in
    ``sys.modules`` with ``monkeypatch`` and removed after each test;
  * the end-to-end case mounts the block on a real FastAPI app, replaces the
    model, sandbox and turn functions with recorders that fail on any side
    effect, and blocks outbound connections.

Nothing here starts a process, opens a socket or claims anything about a live
Space or deployment.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import socket
import sys
import types

import pytest

import a11oy_code_engine as vendored


ROOT = Path(__file__).resolve().parents[1]
SERVE = ROOT / "serve.py"
SERVE_ENTRYPOINTS = (SERVE, ROOT / "deploy" / "space" / "serve.py")
BEGIN = "# BEGIN: a11oy CODE — governed agentic coder"
END = "# END: a11oy CODE — killinchu"
CODE_PREFIX = "/api/killinchu/v1/code/"


def SIGN(_payload):
    return {"signed": False, "signatures": [], "honesty": "inert test signer"}


def VERIFY(_envelope):
    return {"verified": False, "honesty": "inert test verifier"}


class Recorder:
    """Stands in for ``register``; records each call and mounts nothing."""

    def __init__(self, label):
        self.label = label
        self.calls = []

    def __call__(self, app, ns, sign_fn, **kwargs):
        self.calls.append({"app": app, "ns": ns, "sign_fn": sign_fn, **kwargs})
        return {"registered_by": self.label}


def _turn_without_allow_exec(mode, prompt, sign_fn, ns, untrusted_input="",
                             run_chain=None, sandbox=False, want_model="",
                             harness_profile_id=""):
    raise AssertionError("a fake governed_turn must never be called")


def _turn_with_allow_exec(mode, prompt, sign_fn, ns, untrusted_input="",
                          run_chain=None, sandbox=False, want_model="",
                          harness_profile_id="", allow_exec=False):
    raise AssertionError("a fake governed_turn must never be called")


def _turn_allowing_exec_by_default(mode, prompt, sign_fn, ns, untrusted_input="",
                                   run_chain=None, sandbox=False, want_model="",
                                   harness_profile_id="", allow_exec=True):
    raise AssertionError("a fake governed_turn must never be called")


def _serve_block() -> str:
    source = SERVE.read_text(encoding="utf-8")
    assert source.count(BEGIN) == 1, "serve.py code-engine BEGIN marker moved or duplicated"
    assert source.count(END) == 1, "serve.py code-engine END marker moved or duplicated"
    start = source.index(BEGIN)
    end = source.index(END, start)
    return source[start:end]


def _run_serve_block(app):
    namespace = {
        "__name__": "killinchu_serve_code_engine_block",
        "app": app,
        "_killinchu_loop_sign": SIGN,
        "_killinchu_loop_verify": VERIFY,
    }
    exec(compile(_serve_block(), str(SERVE), "exec"), namespace)
    return namespace


def _no_substrate(monkeypatch):
    # ``None`` in sys.modules makes any ``szl_substrate`` import raise ImportError.
    monkeypatch.setitem(sys.modules, "szl_substrate", None)
    monkeypatch.delitem(sys.modules, "szl_substrate.a11oy_code_engine", raising=False)


def _install_substrate(monkeypatch, governed_turn):
    package = types.ModuleType("szl_substrate")
    package.__path__ = []
    engine = types.ModuleType("szl_substrate.a11oy_code_engine")
    engine.governed_turn = governed_turn
    engine.register = Recorder("szl_substrate")
    package.a11oy_code_engine = engine
    monkeypatch.setitem(sys.modules, "szl_substrate", package)
    monkeypatch.setitem(sys.modules, "szl_substrate.a11oy_code_engine", engine)
    return engine


def _install_fake_vendored(monkeypatch, governed_turn):
    engine = types.ModuleType("a11oy_code_engine")
    engine.governed_turn = governed_turn
    engine.register = Recorder("fake vendored")
    monkeypatch.setitem(sys.modules, "a11oy_code_engine", engine)
    return engine


def _record_vendored_register(monkeypatch):
    recorder = Recorder("vendored")
    monkeypatch.setattr(vendored, "register", recorder)
    return recorder


def _assert_bound_to_vendored(namespace, recorder, app):
    assert namespace["_kc_code"] is vendored
    assert recorder.calls == [{
        "app": app,
        "ns": "killinchu",
        "sign_fn": SIGN,
        "verify_fn": VERIFY,
        "signer_label": ("persistent cosign ECDSA-P256-SHA256 "
                         "(verifiable offline vs /cosign.pub)"),
    }]


def test_reviewed_vendored_engine_carries_a_deny_by_default_allow_exec():
    parameter = inspect.signature(vendored.governed_turn).parameters.get("allow_exec")
    assert parameter is not None
    assert parameter.default is False


def test_serve_binds_the_vendored_engine_when_no_substrate_is_installed(monkeypatch):
    _no_substrate(monkeypatch)
    recorder = _record_vendored_register(monkeypatch)
    app = object()
    namespace = _run_serve_block(app)
    _assert_bound_to_vendored(namespace, recorder, app)


@pytest.mark.parametrize("substrate_turn", [
    pytest.param(_turn_without_allow_exec, id="substrate-without-allow_exec"),
    pytest.param(_turn_with_allow_exec, id="substrate-with-allow_exec"),
])
def test_an_installed_substrate_engine_is_never_preferred(monkeypatch, substrate_turn):
    substrate = _install_substrate(monkeypatch, substrate_turn)
    recorder = _record_vendored_register(monkeypatch)
    app = object()
    namespace = _run_serve_block(app)
    assert substrate.register.calls == []
    _assert_bound_to_vendored(namespace, recorder, app)


@pytest.mark.parametrize("vendored_turn", [
    pytest.param(_turn_without_allow_exec, id="no-allow_exec"),
    pytest.param(_turn_allowing_exec_by_default, id="allow_exec-defaults-true"),
])
@pytest.mark.parametrize("substrate_turn", [
    pytest.param(None, id="no-substrate"),
    pytest.param(_turn_with_allow_exec, id="substrate-with-allow_exec"),
])
def test_an_engine_without_deny_by_default_allow_exec_is_never_mounted(
        monkeypatch, capsys, vendored_turn, substrate_turn):
    if substrate_turn is None:
        _no_substrate(monkeypatch)
        substrate = None
    else:
        substrate = _install_substrate(monkeypatch, substrate_turn)
    fake = _install_fake_vendored(monkeypatch, vendored_turn)
    _run_serve_block(object())
    assert fake.register.calls == []
    if substrate is not None:
        assert substrate.register.calls == []
    stderr = capsys.readouterr().err
    assert "a11oy Code engine FAILED (non-fatal)" in stderr
    assert "allow_exec" in stderr


def test_served_code_routes_keep_operator_auth_and_the_two_person_chokepoint(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import szl_operator_auth as auth

    operator = "test-only-operator"
    monkeypatch.setenv(auth.OPERATOR_KEY_ENV, operator)
    monkeypatch.setenv(auth.SECOND_APPROVER_KEY_ENV, "test-only-second-approver")

    def no_network(*_args, **_kwargs):
        raise AssertionError("offline binding tests must not open a network connection")

    monkeypatch.setattr(socket, "create_connection", no_network)

    side_effects = []

    def forbidden(category):
        def invoke(*_args, **_kwargs):
            side_effects.append(category)
            raise AssertionError(f"unauthorized side effect: {category}")
        return invoke

    observed_allow_exec = []

    def capture_turn(*_args, **kwargs):
        observed_allow_exec.append(kwargs["allow_exec"])
        return {"test_handler_reached": True, "executed": False}

    # The substrate copy that would serve the route if serve.py preferred it.
    substrate = _install_substrate(monkeypatch, _turn_without_allow_exec)
    app = FastAPI()
    namespace = _run_serve_block(app)
    assert namespace["_kc_code"] is vendored
    assert substrate.register.calls == []
    assert any(getattr(route, "path", "").startswith(CODE_PREFIX)
               for route in app.router.routes)

    # Handlers resolve these module globals per request, so patching after the
    # mount (whose capability check reads the real governed_turn) takes effect.
    monkeypatch.setattr(vendored, "_hf_chat", forbidden("model"))
    monkeypatch.setattr(vendored, "_sandbox_exec", forbidden("sandbox"))
    monkeypatch.setattr(vendored, "governed_turn", forbidden("governed-turn"))

    body = {"prompt": "print(1)", "sandbox": True, "two_person_attested": True,
            "attestation": {"operator": True}, "allow_exec": True}
    with TestClient(app) as client:
        refused = client.post(CODE_PREFIX + "run", json=body)
        assert refused.status_code == 401
        assert refused.json()["status"] == "BLOCKED"
        assert side_effects == []

        # One operator, no second approver: the body's allow_exec is ignored.
        monkeypatch.setattr(vendored, "governed_turn", capture_turn)
        single = client.post(CODE_PREFIX + "run", json=body,
                             headers={"Authorization": f"Bearer {operator}"})
        assert single.status_code == 200
    assert observed_allow_exec == [False]
    assert side_effects == []


def _imports_code_engine_from_substrate(tree) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("szl_substrate"):
            if (node.module == "szl_substrate.a11oy_code_engine"
                    or any(alias.name == "a11oy_code_engine" for alias in node.names)):
                hits.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "szl_substrate.a11oy_code_engine":
                    hits.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "szl_substrate.a11oy_code_engine" in node.value:
                hits.append(f"line {node.lineno}: string {node.value!r}")
    return hits


@pytest.mark.parametrize("entrypoint", SERVE_ENTRYPOINTS,
                         ids=lambda path: path.relative_to(ROOT).as_posix())
def test_no_serve_entrypoint_imports_the_code_engine_from_szl_substrate(entrypoint):
    tree = ast.parse(entrypoint.read_text(encoding="utf-8"), filename=str(entrypoint))
    assert _imports_code_engine_from_substrate(tree) == []
