"""Organizational services (amendment-1, docs/SERVICES-V2.md §ب-۶) —
services + service_grants + service_audit.

A service = grantable bundle of (skill package, connector, access contract).
Credentials are Fernet-encrypted and only ever decrypted inside the backend
MCP gateway (mirror of D2.4). No row in service_grants = no access.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# New PG enum types owned by this revision (created/dropped here; models.py
# references them with create_type=False like every other enum).
service_kind = postgresql.ENUM("sql", "files", "http", name="service_kind", create_type=False)
grant_level = postgresql.ENUM("read", "write", name="grant_level", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    service_kind.create(bind, checkfirst=True)
    grant_level.create(bind, checkfirst=True)

    op.create_table(
        "services",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("slug", sa.String(length=60), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("kind", service_kind, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("conn_read_enc", sa.Text(), nullable=False),
        sa.Column("conn_write_enc", sa.Text()),
        sa.Column("skill_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "service_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "service_id",
            sa.BigInteger(),
            sa.ForeignKey("services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("level", grant_level, nullable=False),
        sa.Column("granted_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("service_id", "user_id", name="uq_grant"),
    )
    op.create_index("idx_grant_user", "service_grants", ["user_id"])

    op.create_table(
        "service_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "service_id",
            sa.BigInteger(),
            sa.ForeignKey("services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("workspace_id", sa.BigInteger(), sa.ForeignKey("workspaces.id", ondelete="SET NULL")),
        sa.Column("tool", sa.String(length=80), nullable=False),
        sa.Column("level_used", grant_level, nullable=False),
        sa.Column("params_digest", sa.String(length=64)),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=40)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("result_rows", sa.Integer()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_svc_audit", "service_audit", ["service_id", "created_at"])


def downgrade() -> None:
    op.drop_table("service_audit")
    op.drop_table("service_grants")
    op.drop_table("services")
    bind = op.get_bind()
    grant_level.drop(bind, checkfirst=True)
    service_kind.drop(bind, checkfirst=True)
