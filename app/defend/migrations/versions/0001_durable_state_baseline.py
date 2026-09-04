"""0001 — durable-state seam baseline: idempotency_keys + backup_events.

Per spec #401: idempotency keys carry the request hash and stored response
with a 24h TTL; backup events carry the pg_dump SHA-256 and feed the
receipt chain as BACKUP_COMMITTED.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS idempotency_keys ("
        "key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, "
        "response TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    op.execute(
        "CREATE TABLE IF NOT EXISTS backup_events ("
        "id UUID PRIMARY KEY, dump_sha256 TEXT NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backup_events")
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
