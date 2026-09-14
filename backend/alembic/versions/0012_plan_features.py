"""User Plans — per-plan feature visibility (plans.features).

JSON list of feature keys (app/services/features.py) the plan's members may see;
NULL keeps the pre-existing behaviour (everything visible).

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("features", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "features")
