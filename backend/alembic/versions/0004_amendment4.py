"""اصلاحیهٔ ۴ — Issue H (teams + team_members). Issue I (team shared memory) adds
no schema — membership (team_members) is its sole source of truth on disk too
(TECH.md section 3/5.9).

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-22

"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


DDL_UP = """
CREATE TABLE teams (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    slug        VARCHAR(80)  NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE team_role AS ENUM ('member', 'lead');

CREATE TABLE team_members (
    team_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_in_team team_role NOT NULL DEFAULT 'member',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id)
);

CREATE INDEX idx_team_members_user ON team_members(user_id);
"""

DDL_DOWN = """
DROP INDEX IF EXISTS idx_team_members_user;
DROP TABLE IF EXISTS team_members;
DROP TYPE IF EXISTS team_role;
DROP TABLE IF EXISTS teams;
"""


def _split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _split_statements(DDL_UP):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _split_statements(DDL_DOWN):
        op.execute(stmt)
