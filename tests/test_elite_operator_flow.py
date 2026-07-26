# SPDX-License-Identifier: Apache-2.0
"""Regression guard for the authenticated /elite operator mutation flow."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_elite_console as elite


def test_shipped_elite_console_gates_mutations_with_tab_scoped_authority():
    app = FastAPI(title="killinchu-elite-operator-flow")
    elite.register(app, ns="killinchu")

    with TestClient(app) as client:
        response = client.get("/elite")

    assert response.status_code == 200
    html = response.text
    operator_block = html.split(
        "window.__intel_operator_key=", 1
    )[1].split("window.intel_run=", 1)[0]

    # The bearer is entered at runtime and retained only for this browser tab.
    assert "window.prompt(" in operator_block
    assert "window.sessionStorage.getItem" in operator_block
    assert "window.sessionStorage.setItem" in operator_block
    assert "window.sessionStorage.removeItem" in operator_block
    assert "localStorage" not in operator_block

    # Every non-safe request is wired into both server-enforced gates.
    assert "headers.set('Authorization','Bearer '+token)" in operator_block
    assert "'Idempotency-Key'," in operator_block
    assert "method!=='GET'&&method!=='HEAD'&&method!=='OPTIONS'" in operator_block
    assert ".replace(/[^A-Za-z0-9._:-]/g,'-').slice(0,128)" in operator_block
    assert "window.crypto.randomUUID" in operator_block
    assert "window.__intel_pending_mutation_keys=Object.create(null)" in operator_block
    assert "window.intel_logical_action_key" in operator_block
    assert "delete requestOpts.logicalAction" in operator_block
    assert "if(logicalAction&&(r.ok||r.status<500))" in operator_block
    assert "delete window.__intel_pending_mutation_keys[logicalAction]" in operator_block

    # The actual shipped mutation controls still share the guarded fetch path.
    assert "await window.intel_fetch('/'+(kind==='live'?'live':'crawl/run')" in html
    assert "window.intel_fetch('/watchlists',{method:'POST'" in html
    assert "window.intel_fetch('/watchlists/'+id,{method:'DELETE'" in html
    assert "logicalAction:'intel:'+kind" in html
    assert "logicalAction:'watchlist:create'" in html
    assert "logicalAction:'watchlist:delete:'+id" in html
    assert "Authorize operator" in html
    assert "Clear operator session" in html
