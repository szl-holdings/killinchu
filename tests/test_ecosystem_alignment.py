"""Offline contracts for Killinchu's cross-estate alignment surfaces."""
import asyncio
import time
from pathlib import Path

import killinchu_nav_wireup as nav
import szl_spaces_proxy as proxy
import szl_spaces_surface as surface


EXPECTED = [
    ("a11oy", "a11oy", "a11oy — Command Center", "docker"),
    ("anatomy", "anatomy", "SZL Living Anatomy", "docker"),
    ("cosmos", "cosmos", "SZL Cosmos", "docker"),
    ("david-leads", "david-leads", "David Leads — Sovereign Insurance Intelligence", "docker"),
    ("energy-attest-holo", "energy-attest-holo", "Energy Attestation Holo", "static"),
    ("energy-attested-runs", "energy-attested-runs", "Energy-Attested Inference Runs", "static"),
    ("governed-norm-holo", "governed-norm-holo", "Governed Norms — WILLAY classifiers", "static"),
    ("governed-agent-bench", "governed-agent-bench", "Governed Agent Benchmark", "gradio"),
    ("governed-receipt-verifier", "governed-receipt-verifier", "Governed Receipt Verifier", "static"),
    ("guardrail-receipt", "guardrail-receipt", "Guardrail Decision-Receipt", "static"),
    ("hatun-mcp", "hatun-mcp", "hatun — MCP Server", "docker"),
    ("holographic", "holographic", "Holographic Estate", "docker"),
    ("immune", "immune", "IMMUNE — Verifiable AI Defense Matrix", "docker"),
    ("killinchu", "killinchu", "killinchu — Andean Drone Intelligence", "docker"),
    ("lambda-gate-holo", "lambda-gate-holo", "Λ Gate — Conjecture 1, never green", "static"),
    ("llm-router-live", "llm-router-live", "SZL LLM Router", "docker"),
    ("receipt-chain-live", "receipt-chain-live", "Receipt Chain Live", "static"),
    ("sda", "sda", "SZL SDA", "docker"),
    ("szl-blocked-live", "szl-blocked-live", "szl-blocked-live", "static"),
    ("szl-estate-live", "szl-estate-live", "Khipu Loom — Governed AI Estate", "static"),
    ("szl-forge-lab", "szl-forge-lab", "SZL Forge Lab", "static"),
    ("szl-govsign-live", "szl-govsign-live", "szl-govsign-live", "static"),
    ("szl-kernels-live", "szl-kernels-live", "SZL Kernel Operations Hub", "static"),
    ("szl-model-inference-lab", "szl-model-inference-lab", "SZL Model Inference Lab", "docker"),
    ("szl-provctl-live", "szl-provctl-live", "szl-provctl-live", "static"),
    ("yarqa", "yarqa", "yarqa — Plug-Flow Compartments (live or sample, always honest)", "docker"),
]


def _rows(records):
    return [(sp["name"], sp["slug"], sp["title"], sp["sdk"]) for sp in records]


def test_space_inventory_is_exact_and_shared():
    assert len(EXPECTED) == 26
    assert _rows(surface.SPACES) == EXPECTED
    assert _rows(proxy.SPACE_INVENTORY) == EXPECTED
    assert len({row[0] for row in EXPECTED}) == 26
    assert len({row[1] for row in EXPECTED}) == 26
    assert not {"cathedral", "energy", "khipu-constellation"} & set(proxy.ALL_SPACES)

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
        expected_url = f"https://szlholdings-{slug}{suffix}"
        assert surface.hf_url(name) == expected_url
        assert surface.canonical_url(name) == expected_url
        assert surface.proxy_url(name) == expected_url
        assert proxy.hf_url(slug) == expected_url
        assert surface.hf_repo_url(name) == f"https://huggingface.co/spaces/SZLHOLDINGS/{name}"
    assert surface.hf_api_url("governed-agent-bench").endswith("/SZLHOLDINGS/governed-agent-bench")
    assert set(proxy.PROXY_SPACES) == {row[1] for row in EXPECTED}
    assert len(proxy.PROXY_SPACES) == 26
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
        canonical = surface.hf_url(name)
        assert f'data-space="{slug}"' in tiles
        assert title in tiles and title in fallback
        assert f"{name} &middot; {sdk}" in tiles
        assert f'href="{canonical}"' in tiles
        assert f'href="{canonical}"' in fallback
        assert f'href="/spaces/{slug}' not in tiles
        assert f'href="/spaces/{slug}' not in fallback
    assert "All 26 audited Spaces" in tiles
    assert "All 26 audited Spaces" in fallback
    assert "canonical isolated Hugging Face origin" in tiles
    assert "no-store 307 handoffs" in fallback
    assert "reverse proxy" not in tiles.lower()
    assert "reverse proxy" not in fallback.lower()
    assert "all RUNNING" not in fallback


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
    assert status.startswith("ok: 26 canonical handoff spaces")
    client = TestClient(app)

    response = client.get(
        "/spaces/immune/api/events?cursor=a%2Fb&cursor=two+words",
        headers={"Cookie": "private=session", "Authorization": "Bearer private"},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == (
        "https://szlholdings-immune.hf.space/api/events?cursor=a%2Fb&cursor=two+words"
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
        "https://szlholdings-immune.hf.space/assets/app.js?build=7"
    )
    assert head.headers["cache-control"] == "no-store"
    assert client.get("/spaces/notreal", follow_redirects=False).status_code == 404
    own = client.get("/spaces/a11oy", follow_redirects=False)
    assert own.status_code == 307
    assert own.headers["location"] == "https://szlholdings-a11oy.hf.space"

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
