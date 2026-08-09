import asyncio

import killinchu_spaces_adapter as adapter
import szl_spaces_proxy as proxy
import szl_spaces_surface as surface


adapter.configure_proxy(proxy)
adapter.configure_surface(surface)


def test_adapter_keeps_shared_inventory_policy_out_of_shared_files():
    proxy_names = [row["name"] for row in proxy.SPACE_INVENTORY]
    surface_names = [row["name"] for row in surface.SPACES]
    assert proxy_names == surface_names
    assert len(surface_names) == 26
    assert "README" not in surface_names
    assert "governed-agent-bench" in surface_names
    assert surface._PROBE_TIMEOUT == 2.0
    assert surface._HF_API_TIMEOUT == 2.0


def test_adapter_projects_custom_domain_and_keeps_pending_fail_closed():
    row = {
        "slug": "a11oy",
        "stage": "unknown",
        "app_reachable": True,
        "contract_state": "LIVE",
    }
    surface._apply_hf_runtime(
        row,
        {
            "runtime": {
                "stage": "RUNNING",
                "domains": [{"domain": "a-11-oy.com", "stage": "PENDING"}],
            }
        },
    )
    assert row["custom_domain"] == {
        "domain": "a-11-oy.com",
        "provider_stage": "PENDING",
        "state": "DEGRADED",
        "source": "hf-api",
    }
    assert surface._space_health_state(row) == "DEGRADED"


def test_adapter_retries_transient_contract_probe_then_closes_circuit(monkeypatch):
    class Response:
        status_code = 503

        @staticmethod
        def json():
            return None

    class Client:
        async def get(self, *_args, **_kwargs):
            return Response()

    surface._CONTRACT_CIRCUITS.clear()
    monkeypatch.setattr(
        surface,
        "_urllib_probe",
        lambda *_args: (200, {"schema": "expected/v1"}),
    )
    result = asyncio.run(
        surface._probe_contract(
            Client(),
            {
                "id": "adapter-retry",
                "url": "https://example.invalid/contract",
                "expected": {"schema": "expected/v1"},
            },
        )
    )
    assert result["state"] == "LIVE"
    assert result["attempts"] == 2
    assert result["probe_via"] == "urllib"
    assert result["circuit_state"] == "CLOSED"
