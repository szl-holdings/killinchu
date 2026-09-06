# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DURABLE = ROOT / "docs" / "DEFEND_DURABLE_STATE.md"
IDENTITY = ROOT / "docs" / "DEFEND_IDENTITY.md"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing production seam specification: {path}"
    value = path.read_text(encoding="utf-8")
    assert value.strip(), f"empty production seam specification: {path}"
    return value


def test_durable_state_rejects_unverified_space_database_topology() -> None:
    source = _text(DURABLE)
    required = (
        "external managed PostgreSQL 16 or newer",
        "DATABASE_URL",
        "TLS-verified PostgreSQL connection",
        "HTTPS database gateway/data API",
        "SQLite remains supported only for tests",
        "production_durable_state: NOT_VERIFIED",
        "public_effectors: DISABLED",
        "BACKUP_COMMITTED",
        "SERIALIZABLE",
        "REPEATABLE READ",
        "/api/defend/readyz",
    )
    for marker in required:
        assert marker in source

    rejected_claims = (
        "production uses a PostgreSQL sidecar",
        "Hugging Face provides a PersistentVolumeClaim",
        "Hugging Face Space provides a Postgres sidecar",
    )
    for claim in rejected_claims:
        assert claim not in source


def test_identity_spec_pins_immutable_tenant_scoped_authority() -> None:
    source = _text(IDENTITY)
    required = (
        "OIDC_ISSUER_URL",
        "OIDC_CLIENT_ID",
        "only `RS256` or `ES256`",
        "`none` and all symmetric `HS*` algorithms are rejected",
        "`principal_id` as UUIDv5",
        "`tenant_id` comes from one configured provider claim",
        "Deny-by-default RBAC",
        "12 hours of inactivity",
        "7 days absolute",
        "production_oidc: NOT_VERIFIED",
        "production_tenant_isolation: NOT_VERIFIED",
        "production_rbac: NOT_VERIFIED",
        "public_effectors: DISABLED",
    )
    for marker in required:
        assert marker in source


def test_spec_language_never_claims_live_production_completion() -> None:
    combined = _text(DURABLE) + "\n" + _text(IDENTITY)
    assert "deployed production durability is NOT VERIFIED" in combined
    assert "deployed identity is NOT VERIFIED" in combined
    assert "production-ready: true" not in combined
    assert "public_effectors: ENABLED" not in combined
