# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Offline contract for the shared operator table vendored from A11oy.

Only middleware admission is exercised. This does not register A11oy routes in
Killinchu, execute effectors, or supply tenant or independent plan authority.
"""

import asyncio
import json

import pytest

import szl_operator_auth as auth


PREFIX = "/api/a11oy/v1/series-a/execution-observations"
WRITES = (
    PREFIX + "/challenge",
    PREFIX + "/run",
    PREFIX + "/cancel/" + "a" * 64,
    "/api/a11oy/v2/khipu/lmdb/append",
    "/api/a11oy/v2/khipu/replicate",
    "/api/a11oy/v2/unay/remember",
)
TOKEN = "fixture-operator-no-live-authority"


@pytest.mark.parametrize("path", WRITES)
@pytest.mark.parametrize("configured,token", [(True, ""), (True, "incorrect"), (False, TOKEN)])
def test_shared_mutations_refuse_before_body_or_native_dispatch(monkeypatch, path, configured, token):
    monkeypatch.setenv(auth.OPERATOR_KEY_ENV, TOKEN if configured else "")
    sent = []

    async def receive():
        pytest.fail("Refusal must precede request-body consumption")

    async def downstream(scope, receive, send):
        pytest.fail("Refusal must precede native dispatch")

    async def send(message):
        sent.append(message)

    headers = [(b"authorization", ("Bearer " + token).encode())] if token else []
    asyncio.run(auth.OperatorGateMiddleware(downstream)(
        {"type": "http", "method": "POST", "path": path, "headers": headers}, receive, send))
    assert sent[0]["status"] == 401
    assert (b"cache-control", b"no-store") in sent[0]["headers"]
    assert json.loads(sent[1]["body"])["status"] == "BLOCKED"


@pytest.mark.parametrize("path", WRITES)
def test_operator_passes_only_the_outer_gate(monkeypatch, path):
    monkeypatch.setenv(auth.OPERATOR_KEY_ENV, TOKEN)
    reached = []

    async def downstream(scope, receive, send):
        reached.append((scope["method"], scope["path"]))

    async def unused(*args):
        pytest.fail("The admission-only fixture must not read a body or emit an effect")

    asyncio.run(auth.OperatorGateMiddleware(downstream)(
        {"type": "http", "method": "POST", "path": path,
         "headers": [(b"authorization", ("Bearer " + TOKEN).encode())]}, unused, unused))
    assert reached == [("POST", path)]


@pytest.mark.parametrize("method,path", [
    ("GET", PREFIX + "/exports/" + "a" * 64),
    ("GET", "/api/a11oy/v2/khipu/lmdb/stats"),
    ("GET", "/api/a11oy/v2/khipu/replicate/status"),
    ("GET", "/api/a11oy/v2/unay/recall"),
    ("POST", "/api/a11oy/v2/unay/recall"),
])
def test_read_contracts_are_not_reclassified_as_mutations(method, path):
    assert auth.protected_action(method, path) is None
