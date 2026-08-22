"""اصلاحیهٔ ۲ — Issues A/C (message status+error) and D (thinking level)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22

"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


DDL_UP = """
CREATE TYPE thinking_level AS ENUM ('off', 'standard', 'deep');
CREATE TYPE message_status AS ENUM ('complete', 'streaming', 'failed');

ALTER TABLE messages ALTER COLUMN content SET DEFAULT '';

ALTER TABLE messages ADD COLUMN status message_status NOT NULL DEFAULT 'complete';
ALTER TABLE messages ADD COLUMN error_code VARCHAR(40);
ALTER TABLE messages ADD COLUMN error_reason TEXT;
ALTER TABLE messages ADD COLUMN thinking_level thinking_level;

CREATE INDEX idx_msg_streaming ON messages(status) WHERE status = 'streaming';

ALTER TABLE conversations ADD COLUMN thinking_level thinking_level NOT NULL DEFAULT 'standard';
"""

DDL_DOWN = """
DROP INDEX IF EXISTS idx_msg_streaming;
ALTER TABLE conversations DROP COLUMN IF EXISTS thinking_level;
ALTER TABLE messages DROP COLUMN IF EXISTS thinking_level;
ALTER TABLE messages DROP COLUMN IF EXISTS error_reason;
ALTER TABLE messages DROP COLUMN IF EXISTS error_code;
ALTER TABLE messages DROP COLUMN IF EXISTS status;
DROP TYPE IF EXISTS message_status;
DROP TYPE IF EXISTS thinking_level;
"""


def _split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _split_statements(DDL_UP):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _split_statements(DDL_DOWN):
        op.execute(stmt)
