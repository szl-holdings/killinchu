"""0002 — move the existing approval persistence seam under Alembic ownership.

This is the existing source-only, non-tenant-qualified schema. It does not wire
the public demo plane to PostgreSQL or establish production authorization.
An unexpected legacy table causes a conflict; no data is silently adopted.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE approval_requests ("
        "request_id TEXT PRIMARY KEY, requester TEXT NOT NULL, scope TEXT NOT NULL, "
        "justification TEXT NOT NULL, policy_mode TEXT NOT NULL, "
        "state TEXT NOT NULL, approvers TEXT NOT NULL, denier TEXT, "
        "created_at_epoch DOUBLE PRECISION NOT NULL)")


def downgrade() -> None:
    op.execute("DROP TABLE approval_requests")
