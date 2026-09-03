"""Offline contracts for Killinchu's cross-estate alignment surfaces."""
import asyncio
import time
from pathlib import Path

import killinchu_nav_wireup as nav
import szl_spaces_proxy as proxy
import szl_spaces_surface as surface


EXPECTED = [
    # The public Hub cut is exactly these 6 KEEP Spaces (MEASURED 2026-08-31).
    # The other 38 audited Spaces are folded: PAUSED+PRIVATE on the Hub,
    # reachable only through their documented product/proof destinations.
    ("a11oy", "a11oy", "a11oy — Command Center", "docker"),
    ("killinchu", "killinchu", "killinchu — Andean Drone Intelligence", "docker"),
    ("immune", "immune", "IMMUNE — Verifiable AI Defense Matrix", "docker"),
    ("szl-khipu", "szl-khipu", "szl-khipu", "docker"),
    ("szl-atelier", "szl-atelier", "SZL Atelier — forty-model walk", "static"),
    ("governed-receipt-verifier", "governed-receipt-verifier", "Governed Receipt Verifier", "static"),
]

# Operator destinations for the KEEP set. Not quality claims.
KEEP_DEST = {
    "a11oy": "https://a-11-oy.com",
    "killinchu": "https://szlholdings-killinchu.hf.space/elite",
    "immune": "https://a-11-oy.com/immune",
    "szl-khipu": "https://a-11-oy.com/khipu",
    "szl-atelier": "https://a11oy.net/atelier/",
    "governed-receipt-verifier": "https://a11oy.net/record/",
}

# Fold invariants: the folded set stays name-addressable on the Hub
# (paused+private) and every fold lands on a canonical origin.
FOLD_COUNT = 38
FOLD_ORIGINS = ("https://a-11-oy.com", "https://a11oy.net")
FOLD_SPOT_NAMES = {
    "yarqa", "david-leads", "anatomy", "energy-attested-runs",
    "szl-forge-lab", "llm-router-live", "holographic", "cosmos",
}


def _rows(records):
    return [(sp["name"], sp["slug"], sp["title"], sp["sdk"]) for sp in records]


def test_space_inventory_is_exact_and_shared():
    assert len(EXPECTED) == 6
    assert _rows(surface.SPACES) == EXPECTED
    assert _rows(proxy.SPACE_INVENTORY) == EXPECTED
    assert len({row[0] for row in EXPECTED}) == 6
    assert len({row[1] for row in EXPECTED}) == 6
    assert not {"cathedral", "energy", "khipu-constellation"} & set(proxy.ALL_SPACES)
    # The fold is total and disjoint: 6 KEEP + 38 FOLD = the 44 audited estate.
    keep_names = {row[0] for row in EXPECTED}
    fold_names = {sp["name"] for sp in surface.FOLD_SPACES}
    assert len(fold_names) == FOLD_COUNT
    assert not keep_names & fold_names
    assert keep_names | fold_names == set(proxy.PROXY_SPACES)
    assert len(proxy.PROXY_SPACES) == 44
    # Every fold lands on a canonical origin; nowhere else.
    for sp in surface.FOLD_SPACES:
        assert sp["action"] == "FOLD"
        assert sp["dest"].startswith(FOLD_ORIGINS)
        assert FOLD_SPOT_NAMES - fold_names == set() or True
    assert FOLD_SPOT_NAMES <= fold_names

def test_hub_inventory_ignores_org_profile_but_detects_application_drift():
    import asyncio

    class Response:
        status_code = 200

        def __init__(self, names):
            self._names = names

        def json(self):
            return [{"id": f"SZLHOLDINGS/{name}"} for name in self._names]

    class Client:
        def __init__(self, names):
            self._names = names

        async def get(self, *_args, **_kwargs):
            return Response(self._names)

    class RawResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class RawClient:
        def __init__(self, payload):
            self._payload = payload

        async def get(self, *_args, **_kwargs):
            return RawResponse(self._payload)

    canonical = [row[0] for row in EXPECTED]
    exact = asyncio.run(surface._probe_inventory(Client(canonical + ["README"])))
    drift = asyncio.run(
        surface._probe_inventory(Client(canonical[1:] + ["README", "rogue-space"]))
    )
    assert exact["state"] == "LIVE"
    assert exact["observed_count"] == len(canonical)
    assert exact["missing"] == exact["unexpected"] == []
    assert drift["state"] == "DEGRADED"
    assert drift["missing"] == [canonical[0]]
    assert drift["unexpected"] == ["rogue-space"]

    canonical_payload = [{"id": f"SZLHOLDINGS/{name}"} for name in canonical]
    malformed_payloads = [
        canonical_payload + [None],
        canonical_payload + [{}],
        canonical_payload + [{"id": 7}],
        canonical_payload + [{"id": "OTHER/rogue-space"}],
        canonical_payload + [{"id": "SZLHOLDINGS/"}],
        canonical_payload + [{"id": "SZLHOLDINGS/foo/bar"}],
    ]
    malformed_results = [
        asyncio.run(surface._probe_inventory(RawClient(payload)))
        for payload in malformed_payloads
    ]
    for result in malformed_results:
        assert result["state"] == "UNAVAILABLE"
        assert result["error"] == "hub_api_schema"
        assert result["malformed_index"] == len(canonical)
        assert "missing" not in result and "unexpected" not in result


def test_space_urls_and_canonical_handoff_boundary_are_fail_closed():
    for name, slug, _title, sdk in EXPECTED:
        suffix = ".static.hf.space" if sdk == "static" else ".hf.space"
        hub_url = f"https://szlholdings-{slug}{suffix}"
        # KEEP: the Hub origin stays name-addressable; the canonical operator
        # destination is the documented product/proof path.
        assert surface.hf_url(name) == hub_url
        assert surface.canonical_url(name) == KEEP_DEST[name]
        assert surface.proxy_url(name) == KEEP_DEST[name]
        assert proxy.hf_url(slug) == hub_url
        assert surface.hf_repo_url(name) == f"https://huggingface.co/spaces/SZLHOLDINGS/{name}"
    for sp in surface.FOLD_SPACES:
        slug = sp["name"]
        suffix = ".static.hf.space" if sp["sdk"] == "static" else ".hf.space"
        hub_url = f"https://szlholdings-{slug}{suffix}"
        # FOLD: Hub URL remains derivable (paused+private), canonical handoff
        # is the fold destination on a canonical origin.
        assert surface.hf_url(slug) == hub_url
        assert proxy.hf_url(slug) == hub_url
        assert surface.canonical_url(slug) == sp["dest"]
        assert surface.canonical_url(slug).startswith(FOLD_ORIGINS)
    assert surface.hf_api_url("governed-agent-bench").endswith("/SZLHOLDINGS/governed-agent-bench")
    keep_slugs = {row[1] for row in EXPECTED}
    fold_slugs = {sp["name"] for sp in surface.FOLD_SPACES}
    assert set(proxy.PROXY_SPACES) == keep_slugs | fold_slugs
    assert len(proxy.PROXY_SPACES) == 44
    for resolver in (
        surface.hf_url,
        surface.hf_api_url,
        surface.hf_repo_url,
        surface.canonical_url,
        surface.proxy_url,
        proxy.hf_url,
    ):
        try:
            resolver("notreal")
        except ValueError as exc:
            assert "unknown Space identifier" in str(exc)
        else:
            raise AssertionError("unknown Space identifier must fail closed")


def test_tiles_and_fallback_include_all_audited_titles():
    tiles = surface._tiles_page("killinchu").decode("utf-8")
    fallback = proxy._fallback_index().decode("utf-8")
    for name, slug, title, sdk in EXPECTED:
        dest = KEEP_DEST[name]
        assert f'data-space="{slug}"' in tiles
        assert title in tiles and title in fallback
        assert f"{name} &middot; {sdk}" in tiles
        assert f"{name} &middot; {sdk}" in fallback
        # Tiles link the operator destination and the Hub repo, never the
        # legacy /spaces/ handoff path.
        assert f'href="{dest}"' in tiles
        assert f'href="{dest}"' in fallback
        assert f'href="/spaces/{slug}' not in tiles
        assert f'href="/spaces/{slug}' not in fallback
    # Fold panel honesty: the cut is measured and the fold is labelled.
    assert "Public Hub cut is 6 KEEP" in tiles
    assert "Public Hub cut is 6 KEEP" in fallback
    assert "Folded" in tiles and "PAUSED" in tiles and "PRIVATE" in tiles
    assert "38 Spaces folded" in tiles
    assert "no-store 307 handoffs" in tiles
    assert "no-store 307 handoffs" in fallback
    assert "reverse proxy" not in tiles.lower()
    assert "reverse proxy" not in fallback.lower()
    assert "all RUNNING" not in fallback
    # Folded entries stay labelled and keep their honesty notes.
    for name in FOLD_SPOT_NAMES:
        assert name in tiles and name in fallback
    energy_idx = tiles.find("energy-attested-runs")
    assert energy_idx != -1
    energy = tiles[energy_idx : energy_idx + 900]
    assert "8/8 SIMULATED" in energy
    assert "FOLD" in energy
    forge_idx = tiles.find("szl-forge-lab")
    assert forge_idx != -1
    forge = tiles[forge_idx : forge_idx + 900]
    assert "SNAPSHOT" in forge
    assert "not a trainer" in forge
    assert "not Serve Studio" in forge
    fold_by_name = {sp["name"]: sp for sp in surface.FOLD_SPACES}
    assert fold_by_name["energy-attested-runs"]["honesty"] == "8/8 SIMULATED"
    assert fold_by_name["szl-forge-lab"]["honesty"] == (
        "SNAPSHOT — not a trainer, not Serve Studio"
    )


def test_mobile_tiles_nav_and_health_labels_are_reachable_and_fail_closed():
    tiles = surface._tiles_page("killinchu").decode("utf-8")
    fallback = proxy._fallback_index().decode("utf-8")
    spaces_nav = surface._nav_item().decode("utf-8")
    restraint_nav = nav._build_nav_item().decode("utf-8")
    related = nav._build_related_strip("/ecosystem").decode("utf-8")

    # 320/375px get a single shrinkable column; 768px keeps the fluid auto-fill grid.
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in tiles
    assert "grid-template-columns:repeat(auto-fill,minmax(260px,1fr))" in tiles
    assert "@media(max-width:375px)" in tiles
    assert "grid-template-columns:minmax(0,1fr)" in tiles
    assert ".sp-links a{display:inline-flex;align-items:center;min-height:44px" in tiles
    assert "overflow-wrap:anywhere" in tiles
    assert "li a{display:inline-flex;align-items:center;min-height:44px" in fallback

    # Aggregate and per-Space states are visible and use the backend's conservative labels.
    assert 'id="sp-estate-health"' in tiles and 'aria-live="polite"' in tiles
    assert "estateState(d.state,d.cached_state)" in tiles
    assert 'if(!r.ok)throw new Error("health "+r.status)' in tiles
    assert 'function healthUnavailable(){estateState("UNAVAILABLE")' in tiles
    assert '.catch(healthUnavailable)' in tiles
    assert 'UNAVAILABLE \\u00b7 health fetch failed' in tiles
    assert 'state==="LIVE"?"up":(state==="DEGRADED"?"unknown":"down")' in tiles
    assert 's.app_reachable?"up"' not in tiles

    # Injected nav destinations are real anchors, usable without onclick/keyboard emulation.
    assert spaces_nav.startswith('<a class="nav-item"')
    assert 'href="/spaces"' in spaces_nav and "onclick=" not in spaces_nav
    assert restraint_nav.startswith('<a class="nav-item"')
    assert f'href="{nav._RESTRAINT_URL}"' in restraint_nav and "onclick=" not in restraint_nav
    assert "display:flex;flex-wrap:wrap" in related
    assert "min-height:44px" in related


def test_legacy_space_routes_are_no_store_307_handoffs_without_proxy_bytes_or_cookies():
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    app = Starlette(
        routes=[Route("/{full_path:path}", lambda request: PlainTextResponse("SPA"))]
    )
    status = proxy.register(app, ns="killinchu")
    assert status.startswith("ok: 44 canonical handoff spaces")
    client = TestClient(app)

    response = client.get(
        "/spaces/immune/api/events?cursor=a%2Fb&cursor=two+words",
        headers={"Cookie": "private=session", "Authorization": "Bearer private"},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == (
        "https://a-11-oy.com/immune/api/events?cursor=a%2Fb&cursor=two+words"
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-szl-space-handoff"] == "canonical-origin"
    assert response.content == b""
    assert "set-cookie" not in response.headers
    assert "private" not in str(dict(response.headers)).lower()

    head = client.head("/spaces/immune/assets/app.js?build=7", follow_redirects=False)
    assert head.status_code == 307 and head.content == b""
    assert head.headers["location"] == (
        "https://a-11-oy.com/immune/assets/app.js?build=7"
    )
    assert head.headers["cache-control"] == "no-store"
    assert client.get("/spaces/notreal", follow_redirects=False).status_code == 404
    own = client.get("/spaces/a11oy", follow_redirects=False)
    assert own.status_code == 307
    assert own.headers["location"] == "https://a-11-oy.com"
    # A folded Space handoff lands on its documented destination, never on a
    # live Hub origin (the folded Space is paused+private).
    folded = client.get("/spaces/yarqa", follow_redirects=False)
    assert folded.status_code == 307
    assert folded.headers["location"] == "https://a-11-oy.com"
    assert folded.headers["cache-control"] == "no-store"
    assert folded.content == b""

    assert app.routes[0].path == "/spaces"
    assert app.routes[1].path == "/spaces/{name}"
    assert app.routes[2].path == "/spaces/{name}/{path:path}"
    source = Path(proxy.__file__).read_text(encoding="utf-8")
    assert proxy.SPACE_HANDOFF_MODE == "canonical-redirect-only/v1"
    assert "urllib.request" not in source
    assert "client.request(" not in source
    assert "upstream.content" not in source


def test_spaces_health_aggregate_is_row_derived_and_cache_is_explicit_copy():
    running = {"app_reachable": True, "app_status": 200, "stage": "RUNNING"}
    unknown = {"app_reachable": False, "stage": "unknown"}
    http_200_unknown = {"app_reachable": True, "app_status": 200, "stage": "unknown"}

    assert surface._aggregate_health_state([]) == "UNAVAILABLE"
    assert surface._aggregate_health_state([running, dict(running)]) == "LIVE"
    assert surface._aggregate_health_state([unknown, dict(unknown)]) == "UNAVAILABLE"
    assert surface._aggregate_health_state([running, unknown]) == "DEGRADED"
    assert surface._aggregate_health_state([http_200_unknown]) == "DEGRADED"
    assert surface._space_health_state(running) == "LIVE"
    assert surface._space_health_state(unknown) == "UNAVAILABLE"
    assert surface._space_health_state(http_200_unknown) == "DEGRADED"

    original_ts = surface._HEALTH_CACHE["ts"]
    original_payload = surface._HEALTH_CACHE["payload"]
    fresh = {
        "state": "LIVE",
        "count": 2,
        "spaces": [running, dict(running)],
        "fetchedAt": "2026-07-16T00:00:00Z",
    }
    try:
        surface._HEALTH_CACHE["payload"] = fresh
        surface._HEALTH_CACHE["ts"] = time.monotonic()
        cached = asyncio.run(surface.spaces_health())
    finally:
        surface._HEALTH_CACHE["ts"] = original_ts
        surface._HEALTH_CACHE["payload"] = original_payload

    assert cached is not fresh
    assert cached["state"] == "CACHED"
    assert cached["cached_state"] == "LIVE"
    assert fresh["state"] == "LIVE" and "cached_state" not in fresh


def test_killinchu_related_nav_links_public_ecosystem_and_anatomy_v5():
    related = nav._build_related_strip("/ecosystem").decode("utf-8")
    assert 'href="https://a-11-oy.com/ecosystem"' in related
    assert 'href="https://a-11-oy.com/anatomy-v5"' in related
    assert related.count("https://a-11-oy.com/ecosystem") == 1
    assert related.count("https://a-11-oy.com/anatomy-v5") == 1


def test_crawler_surface_never_presents_stopped_or_failed_as_healthy():
    source = (Path(__file__).resolve().parents[1] / "killinchu_elite_console.py").read_text(
        encoding="utf-8"
    )
    assert "var stopped=halted||!enabled||health==='disabled';" in source
    assert "if(stopped){ outcome='STOPPED'" in source
    assert "else { outcome='DEGRADED'" in source
    assert "var title='Intel feed \\u00b7 '+(stopped?'STOPPED':freshness);" in source
    assert "cell('Next run',(enabled&&!stopped)" in source
    assert "fail-closed \\u00b7 no retries" in source


if __name__ == "__main__":
    test_space_inventory_is_exact_and_shared()
    test_hub_inventory_ignores_org_profile_but_detects_application_drift()
    test_space_urls_and_canonical_handoff_boundary_are_fail_closed()
    test_tiles_and_fallback_include_all_audited_titles()
    test_mobile_tiles_nav_and_health_labels_are_reachable_and_fail_closed()
    test_legacy_space_routes_are_no_store_307_handoffs_without_proxy_bytes_or_cookies()
    test_spaces_health_aggregate_is_row_derived_and_cache_is_explicit_copy()
    test_killinchu_related_nav_links_public_ecosystem_and_anatomy_v5()
    test_crawler_surface_never_presents_stopped_or_failed_as_healthy()
    print("test_ecosystem_alignment: 8 focused offline tests passed")
