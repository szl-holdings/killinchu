"""Killinchu policy adapter for the A11oy-owned Spaces modules.

``szl_spaces_proxy.py`` and ``szl_spaces_surface.py`` are shared source files and
must remain byte-identical to their canonical A11oy counterparts. This module
owns the intentionally different Killinchu policy: the regular-Space inventory,
short probe budget, inventory closure, bounded contract retries/circuits, and
A11oy custom-domain evidence.

Canonical source snapshot:
    szl-holdings/a11oy@fd0dfbc336bbaadebd8b8cb6d8908ade804b25bb
"""

from __future__ import annotations

import asyncio
import time
from typing import Any


CANONICAL_A11OY_SOURCE = "fd0dfbc336bbaadebd8b8cb6d8908ade804b25bb"
_ORG = "SZLHOLDINGS"
_HF_LIST_URL = f"https://huggingface.co/api/spaces?author={_ORG}&limit=1000&full=true"
_PROBE_TIMEOUT = 2.0
_HF_API_TIMEOUT = 2.0
_CONTRACT_ATTEMPTS = 2
_CONTRACT_FAILURE_THRESHOLD = 2
_CONTRACT_CIRCUIT_COOLDOWN = 30.0
_CUSTOM_DOMAINS = {"a11oy": "a-11-oy.com"}
_GOVERNED_AGENT_BENCH = {
    "name": "governed-agent-bench",
    "slug": "governed-agent-bench",
    "title": "Governed Agent Benchmark",
    "sdk": "gradio",
}


def _adapt_inventory(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    names = [row.get("name") for row in rows]
    if (
        names.count("README") != 1
        or names.count("governed-receipt-verifier") != 1
        or "governed-agent-bench" in names
    ):
        raise RuntimeError("unexpected canonical A11oy Spaces inventory")
    adapted = []
    for row in rows:
        if row.get("name") == "README":
            continue
        if row.get("name") == "governed-receipt-verifier":
            adapted.append(dict(_GOVERNED_AGENT_BENCH))
        adapted.append(dict(row))
    return adapted


def _adapt_sequence(value: Any) -> Any:
    def replace(item: Any) -> Any:
        if isinstance(item, dict) and item.get("name") == "README":
            return dict(_GOVERNED_AGENT_BENCH)
        if item == "README":
            return _GOVERNED_AGENT_BENCH["name"]
        if item == "readme":
            return _GOVERNED_AGENT_BENCH["slug"]
        return item

    if isinstance(value, list):
        return [replace(item) for item in value]
    if isinstance(value, tuple):
        return tuple(replace(item) for item in value)
    if isinstance(value, set):
        return {replace(item) for item in value}
    if isinstance(value, frozenset):
        return frozenset(replace(item) for item in value)
    return value


def configure_proxy(proxy: Any) -> None:
    """Apply Killinchu inventory policy to one canonical proxy module."""
    if getattr(proxy, "_killinchu_spaces_adapter_installed", False):
        return
    inventory = _adapt_inventory(proxy.SPACE_INVENTORY)
    proxy.SPACE_INVENTORY = inventory
    proxy._SPACE_BY_NAME = {row["name"]: row for row in inventory}
    proxy._SPACE_BY_SLUG = {row["slug"]: row for row in inventory}
    proxy.ALL_SPACES = [row["slug"] for row in inventory]
    if hasattr(proxy, "PROXY_SPACES"):
        proxy.PROXY_SPACES = _adapt_sequence(proxy.PROXY_SPACES)
    if hasattr(proxy, "HANDOFF_SPACES"):
        proxy.HANDOFF_SPACES = _adapt_sequence(proxy.HANDOFF_SPACES)
    proxy._killinchu_spaces_adapter_installed = True


def configure_surface(surface: Any) -> None:
    """Apply Killinchu health policy to one canonical surface module."""
    if getattr(surface, "_killinchu_spaces_adapter_installed", False):
        return

    spaces = _adapt_inventory(surface.SPACES)
    surface.SPACES = spaces
    surface._SPACE_BY_NAME = {row["name"]: row for row in spaces}
    surface._SPACE_BY_SLUG = {row["slug"]: row for row in spaces}
    surface._PROBE_TIMEOUT = _PROBE_TIMEOUT
    surface._HF_API_TIMEOUT = _HF_API_TIMEOUT
    circuits: dict[str, dict[str, Any]] = {}

    def apply_hf_runtime(result: dict[str, Any], data: Any) -> None:
        if not isinstance(data, dict):
            return
        runtime = data.get("runtime") or {}
        stage = runtime.get("stage")
        if isinstance(stage, str) and stage:
            result["stage"] = stage

        domains = []
        for item in runtime.get("domains") or []:
            if not isinstance(item, dict) or not isinstance(item.get("domain"), str):
                continue
            domains.append(
                {
                    "domain": item["domain"],
                    "provider_stage": str(item.get("stage") or "unknown").upper(),
                }
            )
        if domains:
            result["domains"] = domains

        expected = _CUSTOM_DOMAINS.get(result["slug"])
        if expected:
            observed = next(
                (item for item in domains if item["domain"] == expected), None
            )
            provider_stage = observed["provider_stage"] if observed else "UNKNOWN"
            result["custom_domain"] = {
                "domain": expected,
                "provider_stage": provider_stage,
                "state": (
                    "LIVE"
                    if provider_stage == "READY"
                    else "DEGRADED" if observed else "UNAVAILABLE"
                ),
                "source": "hf-api",
            }

    async def probe_inventory(client: Any) -> dict[str, Any]:
        status = None
        data = None
        via = None
        if client is not None:
            try:
                response = await asyncio.wait_for(
                    client.get(
                        _HF_LIST_URL,
                        timeout=_HF_API_TIMEOUT,
                        headers={"User-Agent": "szl-spaces-surface/1.0"},
                    ),
                    timeout=_HF_API_TIMEOUT,
                )
                status = response.status_code
                data = response.json() if status == 200 else None
                via = "httpx"
            except Exception:
                status = None
        if status is None:
            try:
                status, data = await asyncio.wait_for(
                    surface._to_thread(
                        surface._urllib_probe,
                        _HF_LIST_URL,
                        _HF_API_TIMEOUT,
                        True,
                    ),
                    timeout=_HF_API_TIMEOUT,
                )
                via = "urllib"
            except Exception as exc:
                return {
                    "schema": "szl.hf-space-inventory/v1",
                    "state": "UNAVAILABLE",
                    "canonical_count": len(surface.SPACES),
                    "error": type(exc).__name__,
                }

        if status != 200:
            return {
                "schema": "szl.hf-space-inventory/v1",
                "state": "UNAVAILABLE",
                "canonical_count": len(surface.SPACES),
                "http_status": status,
                "source": via,
                "error": "hub_api_http_status",
            }
        if not isinstance(data, list):
            return {
                "schema": "szl.hf-space-inventory/v1",
                "state": "UNAVAILABLE",
                "canonical_count": len(surface.SPACES),
                "http_status": status,
                "source": via,
                "error": "hub_api_schema",
            }

        observed = set()
        for index, item in enumerate(data):
            identity = item.get("id") if isinstance(item, dict) else None
            if not isinstance(identity, str) or not identity.startswith(_ORG + "/"):
                return {
                    "schema": "szl.hf-space-inventory/v1",
                    "state": "UNAVAILABLE",
                    "canonical_count": len(surface.SPACES),
                    "http_status": status,
                    "source": via,
                    "error": "hub_api_schema",
                    "malformed_index": index,
                }
            name = identity.split("/", 1)[1]
            if not name or "/" in name:
                return {
                    "schema": "szl.hf-space-inventory/v1",
                    "state": "UNAVAILABLE",
                    "canonical_count": len(surface.SPACES),
                    "http_status": status,
                    "source": via,
                    "error": "hub_api_schema",
                    "malformed_index": index,
                }
            if name != "README":
                observed.add(name)
        expected = set(surface._SPACE_BY_NAME)
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        return {
            "schema": "szl.hf-space-inventory/v1",
            "state": "LIVE" if not missing and not unexpected else "DEGRADED",
            "canonical_count": len(expected),
            "observed_count": len(observed),
            "missing": missing,
            "unexpected": unexpected,
            "http_status": status,
            "source": via,
        }

    def contract_circuit(contract_id: str) -> dict[str, Any]:
        return circuits.setdefault(
            contract_id, {"failures": 0, "open_until": 0.0}
        )

    async def contract_attempt(
        client: Any, contract: dict[str, Any], attempt: int
    ) -> tuple[int, Any, str]:
        if client is not None and attempt == 1:
            response = await client.get(
                contract["url"], timeout=_PROBE_TIMEOUT, follow_redirects=True
            )
            return (
                response.status_code,
                response.json() if 200 <= response.status_code < 300 else None,
                "httpx",
            )
        status, data = await surface._to_thread(
            surface._urllib_probe, contract["url"], _PROBE_TIMEOUT, True
        )
        return int(status), data, "urllib"

    async def probe_contract(
        client: Any, contract: dict[str, Any]
    ) -> dict[str, Any]:
        now = time.monotonic()
        circuit = contract_circuit(contract["id"])
        if circuit["open_until"] > now:
            return {
                "id": contract["id"],
                "url": contract["url"],
                "state": "UNAVAILABLE",
                "probe_state": "CIRCUIT_OPEN",
                "attempts": 0,
                "retry_after_s": round(circuit["open_until"] - now, 3),
            }

        status = None
        data = None
        via = None
        error = None
        attempts = 0
        for attempt in range(1, _CONTRACT_ATTEMPTS + 1):
            attempts = attempt
            try:
                status, data, via = await asyncio.wait_for(
                    contract_attempt(client, contract, attempt),
                    timeout=_PROBE_TIMEOUT,
                )
            except Exception as exc:
                error = type(exc).__name__
                continue

            expected = contract["expected"]
            matches = isinstance(data, dict) and all(
                data.get(key) == value for key, value in expected.items()
            )
            if 200 <= int(status) < 300 and matches:
                circuit.update({"failures": 0, "open_until": 0.0})
                return {
                    "id": contract["id"],
                    "url": contract["url"],
                    "state": "LIVE",
                    "probe_state": "OBSERVED",
                    "http_status": status,
                    "expected": expected,
                    "probe_via": via,
                    "attempts": attempts,
                    "circuit_state": "CLOSED",
                }
            error = (
                "ContractMismatch"
                if 200 <= int(status) < 300
                else "HTTPStatus"
            )
            if int(status) < 500 and int(status) != 429:
                break

        circuit["failures"] += 1
        if circuit["failures"] >= _CONTRACT_FAILURE_THRESHOLD:
            circuit["open_until"] = time.monotonic() + _CONTRACT_CIRCUIT_COOLDOWN
        return {
            "id": contract["id"],
            "url": contract["url"],
            "state": "UNAVAILABLE",
            "probe_state": "FAILED",
            "http_status": status,
            "expected": contract["expected"],
            "probe_via": via,
            "attempts": attempts,
            "error": error or "Unavailable",
            "circuit_state": (
                "OPEN" if circuit["open_until"] > time.monotonic() else "CLOSED"
            ),
        }

    def space_health_state(space: dict[str, Any]) -> str:
        reachable = bool(space.get("app_reachable"))
        stage = str(space.get("stage") or "unknown").upper()
        contract_state = str(space.get("contract_state") or "LIVE").upper()
        custom_domain_state = str(
            (space.get("custom_domain") or {}).get("state") or "LIVE"
        ).upper()
        if (
            reachable
            and stage in surface._RUNNING_STAGES
            and contract_state == "LIVE"
            and custom_domain_state == "LIVE"
        ):
            return "LIVE"
        if (
            not reachable
            and stage == "UNKNOWN"
            and contract_state in {"LIVE", "UNAVAILABLE"}
        ):
            return "UNAVAILABLE"
        return "DEGRADED"

    async def probe_one(client: Any, sp: dict[str, str]) -> dict[str, Any]:
        name = sp["name"]
        slug = sp["slug"]
        result: dict[str, Any] = {
            "name": name,
            "slug": slug,
            "title": sp["title"],
            "sdk": sp["sdk"],
            "url": surface.hf_url(name),
            "canonical_url": surface.canonical_url(name),
            "proxy_url": surface.proxy_url(name),
            "own_host": slug in surface._OWN_HOST,
            "stage": "unknown",
            "stage_source": "hf-api",
            "app_reachable": False,
        }
        probed = False
        if client is not None:
            try:
                response = await client.request(
                    "HEAD",
                    surface.hf_url(name) + "/",
                    timeout=_PROBE_TIMEOUT,
                    follow_redirects=True,
                )
                result["app_reachable"] = bool(response.status_code < 500)
                result["app_status"] = response.status_code
                result["probe_via"] = "httpx"
                probed = True
            except Exception:
                try:
                    response = await client.get(
                        surface.hf_url(name) + "/",
                        timeout=_PROBE_TIMEOUT,
                        follow_redirects=True,
                    )
                    result["app_reachable"] = bool(response.status_code < 500)
                    result["app_status"] = response.status_code
                    result["probe_via"] = "httpx"
                    probed = True
                except Exception:
                    probed = False
        if not probed:
            try:
                status, _ = await surface._to_thread(
                    surface._urllib_probe,
                    surface.hf_url(name) + "/",
                    _PROBE_TIMEOUT,
                    False,
                )
                result["app_reachable"] = bool(status < 500)
                result["app_status"] = status
                result["probe_via"] = "urllib"
            except Exception as exc:
                result["app_reachable"] = False
                result["probe_error"] = type(exc).__name__

        got_stage = False
        if client is not None:
            try:
                response = await client.get(
                    surface.hf_api_url(name),
                    timeout=_HF_API_TIMEOUT,
                    headers={"User-Agent": "szl-spaces-surface/1.0"},
                )
                if response.status_code == 200:
                    apply_hf_runtime(result, response.json())
                    got_stage = True
                else:
                    result["stage_http"] = response.status_code
                    got_stage = True
            except Exception:
                got_stage = False
        if not got_stage:
            try:
                status, data = await surface._to_thread(
                    surface._urllib_probe,
                    surface.hf_api_url(name),
                    _HF_API_TIMEOUT,
                    True,
                )
                if status == 200 and isinstance(data, dict):
                    apply_hf_runtime(result, data)
                else:
                    result["stage_http"] = status
            except Exception as exc:
                result["stage_error"] = type(exc).__name__

        contracts = await surface._probe_contracts(client, slug)
        if contracts:
            result["contracts"] = contracts
            live_count = sum(item["state"] == "LIVE" for item in contracts)
            result["contract_state"] = (
                "LIVE"
                if live_count == len(contracts)
                else "UNAVAILABLE" if live_count == 0 else "DEGRADED"
            )
        result["state"] = space_health_state(result)
        return result

    async def spaces_health() -> dict[str, Any]:
        now = time.monotonic()
        if (
            surface._HEALTH_CACHE["payload"] is not None
            and (now - surface._HEALTH_CACHE["ts"]) < surface._HEALTH_CACHE_TTL
        ):
            cached = surface._HEALTH_CACHE["payload"]
            return {
                **cached,
                "state": "CACHED",
                "cached_state": cached.get("state", "UNAVAILABLE"),
            }

        client = surface._resolve_client()
        results = await asyncio.gather(
            probe_inventory(client),
            *[probe_one(client, sp) for sp in surface.SPACES],
        )
        inventory = results[0]
        rows = list(results[1:])
        aggregate_state = surface._aggregate_health_state(rows)
        if aggregate_state == "LIVE" and inventory["state"] != "LIVE":
            aggregate_state = "DEGRADED"

        payload = {
            "state": aggregate_state,
            "count": len(rows),
            "inventory": inventory,
            "spaces": rows,
            "labels": {
                "state": "Fresh: LIVE only when every app is reachable and HF reports RUNNING; otherwise DEGRADED or UNAVAILABLE. TTL reuse is CACHED with cached_state.",
                "space_state": "LIVE requires app_reachable:true plus HF stage RUNNING and every configured exact API contract LIVE; partial evidence is DEGRADED",
                "contract_state": "Anatomy and SDA validate exact stable JSON markers on their public dependency routes; a root-page 200 cannot override a failed contract",
                "inventory": "LIVE only when the canonical regular-Space set exactly equals the public Hub API set; README is a special organization surface, not an application Space",
                "custom_domain": "HF API provider state; PENDING remains DEGRADED even when a separate edge currently routes traffic",
                "stage": "HF API runtime.stage (https://huggingface.co/api/spaces/SZLHOLDINGS/<name>)",
                "app_reachable": "REAL server-side HEAD/GET probe of the canonical Space app",
                "degrade": "stage:'unknown' + app_reachable:false; never fabricated",
            },
            "note": "Server-side probed; 0 browser CDN. Honest LIVE/DEGRADED/UNAVAILABLE; cache reuse is explicitly CACHED.",
            "doctrine": surface._DOCTRINE,
            "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        surface._HEALTH_CACHE["payload"] = payload
        surface._HEALTH_CACHE["ts"] = now
        return payload

    surface._apply_hf_runtime = apply_hf_runtime
    surface._probe_inventory = probe_inventory
    surface._CONTRACT_CIRCUITS = circuits
    surface._contract_circuit = contract_circuit
    surface._contract_attempt = contract_attempt
    surface._probe_contract = probe_contract
    surface._space_health_state = space_health_state
    surface._probe_one = probe_one
    surface.spaces_health = spaces_health
    surface._killinchu_spaces_adapter_installed = True


def register_proxy(app: Any, proxy: Any, ns: str = "killinchu") -> str:
    configure_proxy(proxy)
    return proxy.register(app, ns=ns)


def register_surface(app: Any, surface: Any, ns: str = "killinchu") -> str:
    configure_surface(surface)
    return surface.register(app, ns=ns)
