"""Knowledge layer — team learning cursor (docs/KNOWLEDGE.md §3b).

teams.learned_through_message_id: highest message id, across all members'
conversations, already digested into the team's learned knowledge.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("learned_through_message_id", sa.BigInteger()))


def downgrade() -> None:
    op.drop_column("teams", "learned_through_message_id")
