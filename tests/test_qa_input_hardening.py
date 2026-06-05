# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""QA input-hardening regression tests (QA squad, 2026-06-04).

While stress/edge-testing the live killinchu Space, every POST handler returned
an opaque HTTP 500 on a JSON *array* body, and the Wire I rosie-companion
handlers also 500'd on empty / malformed bodies:

  POST /api/killinchu/v1/{remote-id,ads-b,mavlink}/...   500 on array body
  POST /api/killinchu/v1/counter-uas/evaluate            500 on array body
  POST /api/killinchu/v1/rosie-companion/{ponder,...}    500 on empty/malformed/array
  POST /api/killinchu/v1/identify/with-rosie             500 on array body
  POST /api/killinchu/v1/{faa-rid/validate,mavlink/geofence}  500 on array body
  POST /api/killinchu/v4/{inbox,command}                 500 on bad input

Root cause: `await request.json()` parses a JSON array without raising, so a
subsequent `.get()` on the list raised AttributeError -> 500. The `_json_body`
helper now coerces any non-dict to {} and the bare handlers route through it.

Every public POST surface must answer with a clean 4xx (or graceful fallback)
and never a 500 on bad input. Boots the real app in-process (no mocks).
"""
import warnings

import pytest

warnings.filterwarnings("ignore")

starlette_testclient = pytest.importorskip("starlette.testclient")
TestClient = starlette_testclient.TestClient

import serve  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # The BE-hardening middleware enforces a 60/min/IP sliding-window rate limit
    # and reads RATE_LIMIT_PER_MIN live on each request. This suite fires far more
    # than 60 calls from a single client, so lift the cap for the test run only —
    # we are exercising input handling, not the limiter (429 != 500 either way).
    try:
        import szl_be_hardening
        szl_be_hardening.RATE_LIMIT_PER_MIN = 10_000_000
    except Exception:
        pass
    return TestClient(serve.app)


# Handlers whose missing-field guard returns 400 on a coerced-empty body.
PARSE_400 = [
    "/api/killinchu/v1/remote-id/decode",
    "/api/killinchu/v1/ads-b/decode",
    "/api/killinchu/v1/mavlink/parse",
    "/api/killinchu/v4/command",
]

# Handlers that gracefully fall back to defaults (200) on an empty/odd body.
GRACEFUL_200 = [
    "/api/killinchu/v1/counter-uas/evaluate",
    "/api/killinchu/v1/rosie-companion/ponder",
    "/api/killinchu/v1/rosie-companion/synthesize",
    "/api/killinchu/v1/rosie-companion/evolve",
    "/api/killinchu/v1/rosie-companion/brain-jack",
    "/api/killinchu/v1/identify/with-rosie",
    "/api/killinchu/v4/inbox",
]

# Handlers that validate a required field and answer 422 (FastAPI/Lean shape).
VALIDATED_422 = [
    "/api/killinchu/v1/faa-rid/validate",
    "/api/killinchu/v1/mavlink/geofence",
]

ALL_POST = PARSE_400 + GRACEFUL_200 + VALIDATED_422


@pytest.mark.parametrize("path", ALL_POST)
@pytest.mark.parametrize("payload", [b"", b"{not json", b"[1,2,3]"])
def test_bad_input_never_500(client, path, payload):
    r = client.post(path, content=payload)
    assert r.status_code != 500, f"{path} returned 500 on {payload!r}"


@pytest.mark.parametrize("path", ALL_POST)
def test_array_body_never_500(client, path):
    """A JSON array parses cleanly, so an unguarded .get() used to 500."""
    r = client.post(path, json=[1, 2, 3])
    assert r.status_code != 500, f"{path} returned 500 on array body"


@pytest.mark.parametrize("path", PARSE_400)
def test_parse_handlers_are_400(client, path):
    assert client.post(path, content=b"").status_code == 400
    assert client.post(path, json=[1, 2, 3]).status_code == 400


@pytest.mark.parametrize("path", GRACEFUL_200)
def test_graceful_handlers_are_200(client, path):
    assert client.post(path, content=b"").status_code == 200
    assert client.post(path, json=[1, 2, 3]).status_code == 200


@pytest.mark.parametrize("path", VALIDATED_422)
def test_validated_handlers_are_422(client, path):
    assert client.post(path, content=b"").status_code == 422
    assert client.post(path, json=[1, 2, 3]).status_code == 422


# --- valid paths still work (regression lock) -------------------------------

def test_remote_id_valid_ok(client):
    r = client.post("/api/killinchu/v1/remote-id/decode", json={"hex": "fa" * 25})
    assert r.status_code == 200


def test_counter_uas_valid_ok(client):
    r = client.post("/api/killinchu/v1/counter-uas/evaluate", json={"telemetry": {}})
    assert r.status_code == 200


def test_inbox_valid_ok(client):
    r = client.post("/api/killinchu/v4/inbox", json={"protocol": "adsb"})
    assert r.status_code == 200


def test_command_valid_ok(client):
    r = client.post("/api/killinchu/v4/command", json={"command": "noop"})
    assert r.status_code == 200


def test_rosie_ponder_valid_ok(client):
    r = client.post("/api/killinchu/v1/rosie-companion/ponder", json={"context": "x"})
    assert r.status_code == 200


# --- substrate sanity: injection string carried as opaque payload -----------

def test_inbox_injection_string_is_opaque_json(client):
    r = client.post("/api/killinchu/v4/inbox",
                    json={"protocol": "<script>alert(1)</script>", "raw": "DROP TABLE x"})
    assert r.status_code == 200
    # Served as JSON (not HTML), so any string value is inert data, not markup;
    # and the injection string round-trips as an ordinary JSON string value.
    assert r.headers.get("content-type", "").startswith("application/json")
    assert r.json().get("protocol") == "<script>alert(1)</script>"
