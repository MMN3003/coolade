"""usage_ledger.message_id + thinking_level — per-message admin token audit.

Backfill is best-effort: for existing web_chat rows the assistant message is the
latest one in that conversation created at or before the ledger row (turns are
serialised per conversation, so this is exact except for the rare retry).

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_ledger",
        sa.Column("message_id", sa.BigInteger(), sa.ForeignKey("messages.id", ondelete="SET NULL")),
    )
    op.add_column("usage_ledger", sa.Column("thinking_level", sa.String(20)))
    op.create_index("idx_ledger_message", "usage_ledger", ["message_id"])
    op.execute(
        """
        UPDATE usage_ledger l
        SET message_id = (
            SELECT m.id FROM messages m
            WHERE m.conversation_id = l.conversation_id
              AND m.role = 'assistant'
              AND m.created_at <= l.created_at
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT 1
        )
        WHERE l.message_id IS NULL AND l.conversation_id IS NOT NULL AND l.surface = 'web_chat'
        """
    )
    op.execute(
        """
        UPDATE usage_ledger l
        SET thinking_level = m.thinking_level::text
        FROM messages m
        WHERE l.message_id = m.id AND l.thinking_level IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("idx_ledger_message", table_name="usage_ledger")
    op.drop_column("usage_ledger", "thinking_level")
    op.drop_column("usage_ledger", "message_id")
