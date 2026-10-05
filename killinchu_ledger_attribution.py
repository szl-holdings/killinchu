"""Bind existing hardening reads to Killinchu's canonical receipt ledger.

The shared backend store remains a separate diagnostic store. Reading these
routes cannot activate, replay, provision, sign, or append to either store.
"""

import json
from collections.abc import Callable, Mapping
from typing import Any

from fastapi.responses import JSONResponse

from killinchu_ledger import DURABLE_EXTERNAL, EPHEMERAL, READINESS_SCHEMA


def _unavailable() -> dict[str, Any]:
    return {
        "schema": READINESS_SCHEMA,
        "durability_state": "UNAVAILABLE",
        "ready": False,
        "production_ready": False,
        "persistence_scope": "UNSPECIFIED",
        "reason": "canonical receipt ledger readiness is unavailable",
    }


def _canonical_read(provider: Callable[[], Mapping[str, Any]] | None) -> dict[str, Any]:
    try:
        if not callable(provider):
            return _unavailable()
        state = dict(provider())
        if (
            state.get("schema") != READINESS_SCHEMA
            or type(state.get("ready")) is not bool
            or type(state.get("production_ready")) is not bool
            or state.get("durability_state") not in {EPHEMERAL, DURABLE_EXTERNAL, "UNAVAILABLE"}
        ):
            return _unavailable()
        if state["production_ready"] and (
            state["ready"] is not True
            or state["durability_state"] != DURABLE_EXTERNAL
            or state.get("production_readiness_basis") != "EXPLICIT_ADAPTER_CONTRACT"
        ):
            return _unavailable()
        if state["ready"] and state.get("integrity", {}).get("verified") is not True:
            return _unavailable()
        # The provider contract is secret-free JSON. Copy it without retaining
        # mutable adapter objects; malformed/non-finite values fail closed.
        return json.loads(json.dumps(state, allow_nan=False))
    except Exception:
        return _unavailable()


def harden_with_canonical_ledger(
    app: Any,
    harden: Callable[..., Mapping[str, Any]],
    *,
    ledger_readiness: Callable[[], Mapping[str, Any]] | None,
) -> Mapping[str, Any]:
    """Use the original route registrations and preserve all hardening gates."""
    route_class = app.router.route_class
    ready_paths = {"/readyz", "/api/killinchu/v1/readyz"}
    honest_paths = {"/honest", "/api/killinchu/v1/honest"}

    class CanonicalLedgerRoute(route_class):
        def get_route_handler(self):
            original = super().get_route_handler()
            if self.path not in ready_paths | honest_paths or "GET" not in self.methods:
                return original

            async def canonical_read(request):
                ledger = _canonical_read(ledger_readiness)
                if ledger["durability_state"] == "UNAVAILABLE":
                    return JSONResponse(
                        {"status": "unavailable", "organ": "killinchu", "ledger": ledger,
                         "ledger_role": "CANONICAL_RECEIPT_LEDGER", "receipt_minted": False},
                        status_code=503, headers={"cache-control": "no-store"},
                    )
                response = await original(request)
                try:
                    body = json.loads(response.body)
                    if not isinstance(body, dict):
                        raise ValueError("hardening read must return an object")
                except Exception:
                    return JSONResponse(
                        {"status": "unavailable", "organ": "killinchu", "ledger": ledger,
                         "reason": "backend diagnostic response is unavailable",
                         "receipt_minted": False},
                        status_code=503, headers={"cache-control": "no-store"},
                    )
                headers = {key: value for key, value in response.headers.items()
                           if key.lower() not in {"content-length", "content-type"}}
                headers["cache-control"] = "no-store"
                if self.path in ready_paths:
                    diagnostic = {
                        "ledger_role": "BACKEND_HARDENING_DIAGNOSTIC_STORE",
                        "backend": body.get("khipu_backend"),
                        "depth": body.get("khipu_depth"),
                        "chain_ok": body.get("khipu_chain_ok"),
                        "first_break_seq": body.get("khipu_first_break_seq"),
                        "provider_persistence": "UNKNOWN",
                        "production_ready": False,
                    }
                    ready = ledger["ready"] is True and response.status_code == 200
                    body = {
                        "status": "ready" if ready else "unavailable", "organ": "killinchu",
                        "doctrine": body.get("doctrine"), "ledger": ledger,
                        "ledger_role": "CANONICAL_RECEIPT_LEDGER",
                        "backend_store_diagnostics": diagnostic,
                        "receipt_minted": False,
                    }
                    return JSONResponse(body, status_code=200 if ready else 503, headers=headers)
                labels = body.get("honest_labels")
                if not isinstance(labels, dict):
                    labels = {}
                labels["persistence"] = (
                    "Canonical receipt ledger: " + ledger["durability_state"]
                    + "; scope=" + str(ledger.get("persistence_scope", "UNSPECIFIED"))
                    + "; production_ready=" + str(ledger["production_ready"])
                    + ". Backend hardening storage is a separate diagnostic store."
                )
                body.update(honest_labels=labels, ledger=ledger,
                            ledger_role="CANONICAL_RECEIPT_LEDGER", receipt_minted=False)
                status = response.status_code if response.status_code >= 400 else (
                    200 if ledger["ready"] else 503
                )
                return JSONResponse(body, status_code=status, headers=headers)

            return canonical_read

    app.router.route_class = CanonicalLedgerRoute
    try:
        return harden(app, organ="killinchu")
    finally:
        app.router.route_class = route_class
