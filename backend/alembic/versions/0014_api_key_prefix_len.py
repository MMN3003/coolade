"""Widen api_keys.key_prefix: the prefix now follows APP_SLUG ("<slug>_live_xxxx").

Revision ID: 0014
Revises: 0013
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("api_keys", "key_prefix", type_=sa.String(64), existing_type=sa.String(16), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("api_keys", "key_prefix", type_=sa.String(16), existing_type=sa.String(64), existing_nullable=False)
