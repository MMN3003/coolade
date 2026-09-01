"""v2 — persistent workspaces + gitlab tokens (TECH-V2 §4)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="repo"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="provisioning"),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("repo_url", sa.Text()),
        sa.Column("base_branch", sa.String(length=200)),
        sa.Column("work_branch", sa.String(length=200)),
        sa.Column("container_name", sa.String(length=120)),
        sa.Column("volume_name", sa.String(length=120)),
        sa.Column("disk_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "last_activity_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ws_user", "workspaces", ["user_id"])
    op.create_index("idx_ws_status", "workspaces", ["status"])

    op.create_table(
        "gitlab_tokens",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("token_enc", sa.Text(), nullable=False),
        sa.Column(
            "gitlab_host", sa.String(length=200), nullable=False, server_default="git.ecobin.ir"
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # per-user disk quota (TECH-V2 §2.6 / §4.1); NULL = unlimited
    op.add_column("users", sa.Column("disk_quota_bytes", sa.BigInteger()))
    # api key mode (TECH-V2 §4.1): 'claude_code' raw-relay vs legacy 'flatten'
    op.add_column(
        "api_keys",
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="claude_code"),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "mode")
    op.drop_column("users", "disk_quota_bytes")
    op.drop_table("gitlab_tokens")
    op.drop_index("idx_ws_status", table_name="workspaces")
    op.drop_index("idx_ws_user", table_name="workspaces")
    op.drop_table("workspaces")
