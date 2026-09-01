"""v2 — per-workspace gateway key hash (raw relay auth, TECH-V2 §5.2/D2.4)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("gateway_key_hash", sa.Text()))


def downgrade() -> None:
    op.drop_column("workspaces", "gateway_key_hash")
