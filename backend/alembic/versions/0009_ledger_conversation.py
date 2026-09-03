"""Token economy: attribute usage to conversations.

usage_ledger.conversation_id lets the UI show the cumulative cost of a
conversation (the strongest lever against endless mega-conversations: make
the cost visible and nudge a fresh chat). Nullable — relay/api surfaces
have no conversation.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_ledger",
        sa.Column(
            "conversation_id",
            sa.BigInteger(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("idx_ledger_conversation", "usage_ledger", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("idx_ledger_conversation", table_name="usage_ledger")
    op.drop_column("usage_ledger", "conversation_id")
