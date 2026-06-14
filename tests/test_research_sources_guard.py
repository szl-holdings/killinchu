# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED 749/14/163 @ c7c0ba17 · Λ = Conjecture 1.
"""test_research_sources_guard.py — REAL CI guard for the per-tab "Research &
Sources" panel (Task #662 / killinchu_research_sources.py).

serve.py is a god-file that siblings + CI edit concurrently. This guard proves a
future edit can NOT silently drop the Research & Sources wiring or leave a tab
with no sources. It does so with NO MOCKS of the logic under test:

  * It boots the REAL serve.py app in-process via Starlette/FastAPI TestClient
    (same pattern as a11oy's test_operator_reason_envelope.py) so the actual
    registration in serve.py — not a hand-built app — is what gets exercised.
  * For a representative set of REAL /elite tab keys it asserts
    GET /api/killinchu/v1/research/{tab} returns HTTP 200, an
    application/json body (NEVER the SPA index.html shell), and >=1 source.
  * It asserts the catch-all never swallows the research route: the response is
    JSON, not text/html, and the index endpoint enumerates the source pool.
  * It asserts the front-end helper window.__renderResearch is defined in
    killinchu_elite_console.py AND that BOTH injection call sites still exist
    (drop either and tabs render an empty panel).

Pure-stdlib module under test; the only test deps are fastapi + starlette
(httpx for TestClient). Run:  pytest -q tests/test_research_sources_guard.py
"""
from __future__ import annotations

import os
import sys

import pytest

# Import the package root (serve.py + killinchu_*.py live one level up).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Point the SPA root at a real (empty) dir so import-time wiring is harmless;
# the API routes under test never touch the static tree.
os.environ.setdefault("KILLINCHU_ROOT", _ROOT)

# Skip honestly (never silently pass) if the web stack isn't installed.
pytest.importorskip("fastapi")
pytest.importorskip("starlette")
TestClient = pytest.importorskip("starlette.testclient").TestClient

import killinchu_research_sources as rs  # noqa: E402  (module under test)
import serve  # noqa: E402  (boots the REAL app + its registration)

_NS = "killinchu"
_BASE = "/api/%s/v1/research" % _NS

# Representative REAL tab keys actually rendered by the /elite console:
#   - explicit _TAB overrides (hero/maritime/swarm/naval/evidence/w910audit)
#   - keyword-fallback tabs (u_receipts->receipt, u_proofs->proof,
#     uds_package->uds, putnam->putnam, u_intel->intel)
#   - a deliberately-unknown key that must still fall to the non-empty _DEFAULT
_REPRESENTATIVE_TABS = [
    "hero_interdiction",
    "u_maritime",
    "u_swarm",
    "amaru_naval",
    "evidence",
    "w910audit",
    "u_receipts",
    "u_proofs",
    "uds_package",
    "putnam",
    "u_intel",
    "some_unmapped_tab_xyz",  # exercises the _DEFAULT fallthrough
]


@pytest.fixture(scope="module")
def client():
    return TestClient(serve.app)


def _assert_json_not_spa(resp):
    """The catch-all returns the SPA index.html (text/html) for unknown paths.
    A real research route must answer JSON — never the SPA shell."""
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    ctype = resp.headers.get("content-type", "")
    assert "application/json" in ctype, (
        f"research route fell through to a non-JSON ({ctype!r}) response — "
        "likely the SPA catch-all or a dropped registration"
    )
    body_head = resp.text.lstrip()[:64].lower()
    assert not body_head.startswith("<!doctype"), "got SPA HTML, not JSON"
    assert "<html" not in body_head, "got SPA HTML, not JSON"


def test_research_registration_is_live_on_the_real_app(client):
    """serve.py must have actually registered the research layer (try/except
    guarded — a broken import would silently skip it)."""
    r = client.get(_BASE)
    _assert_json_not_spa(r)
    j = r.json()
    assert j.get("source_pool", 0) >= 1
    assert isinstance(j.get("tabs_with_overrides"), list)
    assert j["tabs_with_overrides"], "no tab overrides registered"


@pytest.mark.parametrize("tab", _REPRESENTATIVE_TABS)
def test_every_representative_tab_has_at_least_one_source(client, tab):
    r = client.get(f"{_BASE}/{tab}")
    _assert_json_not_spa(r)
    j = r.json()
    assert j.get("tab") == tab
    srcs = j.get("sources") or []
    assert len(srcs) >= 1, f"tab {tab!r} has NO sources (would be an empty panel)"
    # every source must carry a real, non-empty url + title (no blank rows)
    for s in srcs:
        assert s.get("url"), f"tab {tab!r} source {s.get('id')!r} has no url"
        assert s.get("title"), f"tab {tab!r} source {s.get('id')!r} has no title"
    assert j.get("summary", {}).get("total") == len(srcs)


def test_default_fallthrough_is_never_empty(client):
    """Any unmapped tab still resolves to the curated _DEFAULT pool — a tab is
    never left source-less."""
    assert rs.sources_for("totally_unknown_key_42"), "_DEFAULT must be non-empty"
    r = client.get(f"{_BASE}/totally_unknown_key_42")
    _assert_json_not_spa(r)
    assert len(r.json().get("sources") or []) >= 1


def test_console_render_helper_and_both_injection_sites_present():
    """The front-end helper + BOTH injection call sites must survive edits to the
    god-file console. Dropping the helper or either call site = empty panels."""
    path = os.path.join(_ROOT, "killinchu_elite_console.py")
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()

    assert "window.__renderResearch=function(" in src, (
        "window.__renderResearch helper definition is missing from "
        "killinchu_elite_console.py"
    )
    # Each tab render must CALL the helper. There are two injection sites
    # (the primary view renderer + the globe/vbody renderer); both must remain.
    n_calls = src.count("window.__renderResearch&&window.__renderResearch(")
    assert n_calls >= 2, (
        f"expected >=2 __renderResearch injection call sites, found {n_calls} — "
        "a tab render path lost its Research & Sources panel"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
