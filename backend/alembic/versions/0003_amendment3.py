"""اصلاحیهٔ ۳ — Issue E (5h rolling quota column) and Issue F (upstream_account_limits table)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-22

"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


DDL_UP = """
ALTER TABLE quotas ADD COLUMN limit_credits_5h NUMERIC(14,2);

CREATE TABLE upstream_account_limits (
    window_key      VARCHAR(40) PRIMARY KEY,
    limit_value     NUMERIC(18,2),
    remaining_value NUMERIC(18,2),
    reset_at        TIMESTAMPTZ,
    unit            VARCHAR(30),
    raw_headers     JSONB,
    source          VARCHAR(20) NOT NULL,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
    upstream_request_id VARCHAR(100)
);
"""

DDL_DOWN = """
DROP TABLE IF EXISTS upstream_account_limits;
ALTER TABLE quotas DROP COLUMN IF EXISTS limit_credits_5h;
"""


def _split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _split_statements(DDL_UP):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _split_statements(DDL_DOWN):
        op.execute(stmt)
