"""Knowledge layer (amendment-7, docs/KNOWLEDGE.md) — rules & knowledge at four
scopes, auto-learning from chats, dataset export.

  knowledge_entries  one row = one rule/knowledge item, scoped to exactly one of
                     service | user_service | user | team (CHECK below). `source`
                     tells manual (UI/admin/builder) from `learned` (extracted
                     from the user's own chats by the learning job) so users can
                     review what the system inferred about them.
  users.learning_enabled           per-user opt-out of chat learning
  conversations.learned_through_message_id
                                   learning-job cursor: the last message id already
                                   digested for this conversation

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

knowledge_scope = postgresql.ENUM(
    "service", "user_service", "user", "team", name="knowledge_scope", create_type=False
)
knowledge_kind = postgresql.ENUM("rule", "knowledge", name="knowledge_kind", create_type=False)
knowledge_source = postgresql.ENUM("manual", "learned", name="knowledge_source", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    knowledge_scope.create(bind, checkfirst=True)
    knowledge_kind.create(bind, checkfirst=True)
    knowledge_source.create(bind, checkfirst=True)

    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scope", knowledge_scope, nullable=False),
        sa.Column("kind", knowledge_kind, nullable=False, server_default="knowledge"),
        sa.Column("source", knowledge_source, nullable=False, server_default="manual"),
        sa.Column(
            "service_id", sa.BigInteger(), sa.ForeignKey("services.id", ondelete="CASCADE")
        ),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("team_id", sa.BigInteger(), sa.ForeignKey("teams.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        # learned entries: which conversation the fact was extracted from (review/debug).
        sa.Column(
            "learned_from_conversation_id",
            sa.BigInteger(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
        ),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(scope = 'service'      AND service_id IS NOT NULL AND user_id IS NULL     AND team_id IS NULL) OR "
            "(scope = 'user_service' AND service_id IS NOT NULL AND user_id IS NOT NULL AND team_id IS NULL) OR "
            "(scope = 'user'         AND service_id IS NULL     AND user_id IS NOT NULL AND team_id IS NULL) OR "
            "(scope = 'team'         AND service_id IS NULL     AND user_id IS NULL     AND team_id IS NOT NULL)",
            name="chk_knowledge_scope_keys",
        ),
    )
    op.create_index("idx_knowledge_service", "knowledge_entries", ["service_id"])
    op.create_index("idx_knowledge_user", "knowledge_entries", ["user_id"])
    op.create_index("idx_knowledge_team", "knowledge_entries", ["team_id"])

    op.add_column(
        "users",
        sa.Column("learning_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "conversations",
        sa.Column("learned_through_message_id", sa.BigInteger()),
    )


def downgrade() -> None:
    op.drop_column("conversations", "learned_through_message_id")
    op.drop_column("users", "learning_enabled")
    op.drop_index("idx_knowledge_team", table_name="knowledge_entries")
    op.drop_index("idx_knowledge_user", table_name="knowledge_entries")
    op.drop_index("idx_knowledge_service", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
    bind = op.get_bind()
    knowledge_source.drop(bind, checkfirst=True)
    knowledge_kind.drop(bind, checkfirst=True)
    knowledge_scope.drop(bind, checkfirst=True)
