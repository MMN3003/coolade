"""User plans / tiers — plans + plan_models + users.plan_id/max_thinking_level

Named admin-defined plans (quota + allowed models + thinking cap). Creating or
editing a user with a plan inherits the plan onto that user; editing a plan can
be re-applied to all its members.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# Existing PG enum types (created in 0001/0002) — REFERENCE ONLY, never recreate.
quota_period = postgresql.ENUM("daily", "weekly", "monthly", name="quota_period", create_type=False)
thinking_level = postgresql.ENUM("off", "standard", "deep", name="thinking_level", create_type=False)


# 4 default plans. Models are linked DEFENSIVELY by `models.upstream_model` — only
# rows that actually exist in `models` get a plan_models entry (a fresh DB with the
# legacy seed catalog will simply link none). monthly limit / 5h limit / thinking.
DEFAULT_PLANS = [
    {
        "name": "توسعه‌دهنده", "slug": "developer",
        "limit_credits": "300000", "limit_credits_5h": "25000",
        "max_thinking_level": "deep", "sort_order": 0,
        "models": ["claude-opus-4-8", "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"],
    },
    {
        "name": "تحلیل‌گر", "slug": "analyst",
        "limit_credits": "120000", "limit_credits_5h": "12000",
        "max_thinking_level": "standard", "sort_order": 1,
        "models": ["claude-sonnet-5", "claude-haiku-4-5-20251001", "claude-opus-4-8"],
    },
    {
        "name": "چت عمومی", "slug": "chat",
        "limit_credits": "40000", "limit_credits_5h": "6000",
        "max_thinking_level": "standard", "sort_order": 2,
        "models": ["claude-sonnet-5", "claude-haiku-4-5-20251001"],
    },
    {
        "name": "سبک/مهمان", "slug": "light",
        "limit_credits": "15000", "limit_credits_5h": "3000",
        "max_thinking_level": "off", "sort_order": 3,
        "models": ["claude-haiku-4-5-20251001", "claude-sonnet-5"],
    },
]


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("period", quota_period, nullable=False, server_default="monthly"),
        sa.Column("limit_credits", sa.Numeric(14, 2), nullable=False),
        sa.Column("limit_credits_5h", sa.Numeric(14, 2)),
        sa.Column("max_thinking_level", thinking_level, nullable=False, server_default="standard"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "plan_models",
        sa.Column(
            "plan_id", sa.BigInteger(), sa.ForeignKey("plans.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "model_id", sa.BigInteger(), sa.ForeignKey("models.id", ondelete="CASCADE"), primary_key=True
        ),
    )

    op.add_column(
        "users", sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("plans.id", ondelete="SET NULL"))
    )
    op.add_column("users", sa.Column("max_thinking_level", thinking_level))

    # ---- seed the 4 default plans + defensively link their models ----
    bind = op.get_bind()
    insert_plan = sa.text(
        """
        INSERT INTO plans (name, slug, description, period, limit_credits,
                           limit_credits_5h, max_thinking_level, is_active, sort_order, created_at)
        VALUES (:name, :slug, NULL, CAST(:period AS quota_period), :limit_credits,
                :limit_credits_5h, CAST(:mtl AS thinking_level), true, :sort_order, now())
        RETURNING id
        """
    )
    link_model = sa.text(
        "INSERT INTO plan_models (plan_id, model_id) "
        "SELECT :plan_id, id FROM models WHERE upstream_model = :upstream"
    )
    for p in DEFAULT_PLANS:
        plan_id = bind.execute(
            insert_plan,
            {
                "name": p["name"],
                "slug": p["slug"],
                "period": "monthly",
                "limit_credits": p["limit_credits"],
                "limit_credits_5h": p["limit_credits_5h"],
                "mtl": p["max_thinking_level"],
                "sort_order": p["sort_order"],
            },
        ).scalar()
        for upstream in p["models"]:
            bind.execute(link_model, {"plan_id": plan_id, "upstream": upstream})


def downgrade() -> None:
    op.drop_column("users", "max_thinking_level")
    op.drop_column("users", "plan_id")
    op.drop_table("plan_models")
    op.drop_table("plans")
