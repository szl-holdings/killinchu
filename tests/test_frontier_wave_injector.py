# SPDX-License-Identifier: Apache-2.0
"""Direct ASGI checks for the passive elite HTML script injector."""
from __future__ import annotations

import asyncio
import shutil
import subprocess

import pytest

from killinchu_frontier_wave_surfaces import _WaveSurfacesInjector, _js


def _run(path: str, body: bytes, *, method: str = "GET", headers=(), chunks: int = 1):
    start = {"type": "http.response.start", "status": 200, "headers": list(headers)}
    step = max(1, (len(body) + chunks - 1) // chunks)
    parts = [body[i:i + step] for i in range(0, len(body), step)] or [b""]
    emitted = [start] + [
        {"type": "http.response.body", "body": part, "more_body": i < len(parts) - 1}
        for i, part in enumerate(parts)
    ]
    received = []

    async def app(scope, receive, send):
        for message in emitted:
            await send(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        received.append(message)

    asyncio.run(_WaveSurfacesInjector(app)(
        {"type": "http", "method": method, "path": path}, receive, send
    ))
    return emitted, received


def test_non_elite_stream_delivers_start_and_first_event_before_completion():
    received = []
    start = {"type": "http.response.start", "status": 200,
             "headers": [(b"content-type", b"text/event-stream")]}
    first = {"type": "http.response.body", "body": b"data: first\n\n", "more_body": True}
    last = {"type": "http.response.body", "body": b"data: last\n\n", "more_body": False}

    async def app(scope, receive, send):
        await send(start)
        assert received == [start]
        await send(first)
        assert received == [start, first]
        await send(last)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        received.append(message)

    asyncio.run(_WaveSurfacesInjector(app)(
        {"type": "http", "method": "GET", "path": "/events"}, receive, send
    ))
    assert received == [start, first, last]


@pytest.mark.parametrize("path", ("/docs", "/elite"))
def test_unrelated_html_with_views_literal_is_unchanged(path):
    body = b'<html><script>VIEWS["example"] = {}</script></body></html>'
    emitted, received = _run(path, body, headers=[(b"content-type", b"text/html")], chunks=2)
    assert received == emitted


def test_other_route_with_deck_markers_is_unchanged():
    body = b'<html><div class="side">window.VIEWS</div></body></html>'
    emitted, received = _run("/docs", body, headers=[(b"content-type", b"text/html")])
    assert received == emitted


@pytest.mark.parametrize("path", ("/elite", "/killinchu/elite"))
def test_elite_deck_injects_once_and_corrects_length(path):
    body = b'<html><div class="side">window.VIEWS</div></body></html>'
    headers = [(b"content-type", b"text/html; charset=utf-8"),
               (b"content-length", str(len(body)).encode()), (b"x-original", b"kept")]
    _, received = _run(path, body, headers=headers, chunks=2)
    assert len(received) == 2
    injected = received[1]["body"]
    assert injected.count(b'data-kc-wave-surfaces="k5"') == 1
    assert injected.index(b'data-kc-wave-surfaces="k5"') < injected.index(b"</body>")
    assert dict(received[0]["headers"])[b"content-length"] == str(len(injected)).encode()
    assert dict(received[0]["headers"])[b"x-original"] == b"kept"
    emitted_again, received_again = _run(path, injected, headers=[
        (b"content-type", b"text/html"), (b"content-length", str(len(injected)).encode())
    ])
    assert received_again == emitted_again


def test_shipped_elite_html_is_within_limit_and_receives_script():
    import killinchu_elite_console as elite

    body = elite._CONSOLE_HTML.replace("__NS__", "killinchu").encode("utf-8")
    assert len(body) < _WaveSurfacesInjector._MAX_HTML_BYTES
    _, received = _run("/elite", body, headers=[(b"content-type", b"text/html")])
    assert received[1]["body"].count(b'data-kc-wave-surfaces="k5"') == 1


@pytest.mark.parametrize("body,headers", (
    (b'<html><div class="side">window.VIEWS</div>', [(b"content-type", b"text/html")]),
    (b"compressed", [(b"content-type", b"text/html"), (b"content-encoding", b"gzip")]),
))
def test_uninjectable_elite_response_is_preserved(body, headers):
    emitted, received = _run("/elite", body, headers=headers)
    assert received == emitted


def test_large_chunked_html_is_forwarded_unchanged():
    marker = b'<html><div class="side">window.VIEWS</div></body></html>'
    body = marker + b"x" * (_WaveSurfacesInjector._MAX_HTML_BYTES + 1 - len(marker))
    emitted, received = _run("/elite", body, headers=[(b"content-type", b"text/html")], chunks=2)
    assert received == emitted


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_frontier_script_marks_failed_fetch_as_error_and_mixed_label_as_nonlive():
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const script = fs.readFileSync(0, 'utf8');
async function render(ok, payload) {
  const live = {innerHTML: ''};
  const body = {innerHTML: ''};
  const window = {VIEWS: {}, __KC_NS: 'killinchu'};
  const document = {
    readyState: 'complete',
    querySelector: () => null,
    getElementById: id => id.endsWith('-live') ? live : body,
  };
  const sandbox = {
    window, document, console: {log() {}}, setTimeout() {},
    fetch: () => Promise.resolve({ok, status: ok ? 200 : 503,
      json: () => Promise.resolve(payload)}),
  };
  vm.runInNewContext(script, sandbox);
  await window.VIEWS.kc_onebit.render({innerHTML: ''});
  await new Promise(resolve => setImmediate(resolve));
  return live.innerHTML;
}
(async () => {
  const failed = await render(false, {});
  assert.match(failed, /ERROR/);
  assert.match(failed, /color:#ff6b6b/);
  assert.doesNotMatch(failed, /SIMULATED\/ROADMAP/);
  const failOpen = await render(true, {label: 'MODELED', error: 'compute fail-open'});
  assert.match(failOpen, /ERROR/);
  assert.match(failOpen, /response error/);
  assert.match(failOpen, /color:#ff6b6b/);
  const mixed = await render(true, {label: 'LIVE-when-reachable else SIMULATED'});
  assert.match(mixed, /color:#c9b787/);
  const conditional = await render(true, {label: 'LIVE-when-reachable'});
  assert.match(conditional, /color:#8a8f98/);
  const unmeasured = await render(true, {
    inference_state: {sovereign: true}, measured_panels: 0,
    summary: 'pending metrics',
  });
  assert.match(unmeasured, /UNLABELLED/);
  assert.match(unmeasured, /no response label/);
  assert.doesNotMatch(unmeasured, /color:#3ddc97/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(["node", "-e", harness], input=_js(), text=True,
                            encoding="utf-8",
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
