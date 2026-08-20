"""Startup seed: default model catalog (Appendix A weights) + initial admin user."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Model, User, UserRole
from app.security import hash_password

settings = get_settings()

DEFAULT_MODELS = [
    dict(
        model_key="claude-sonnet",
        display_name="Claude Sonnet",
        upstream_model="claude-sonnet",
        input_weight=Decimal("3.0"),
        output_weight=Decimal("15.0"),
        cache_read_weight=Decimal("0.3"),
        sort_order=1,
    ),
    dict(
        model_key="claude-opus",
        display_name="Claude Opus",
        upstream_model="claude-opus",
        input_weight=Decimal("15.0"),
        output_weight=Decimal("75.0"),
        cache_read_weight=Decimal("1.5"),
        sort_order=0,
    ),
    dict(
        model_key="claude-haiku",
        display_name="Claude Haiku",
        upstream_model="claude-haiku",
        input_weight=Decimal("0.6"),
        output_weight=Decimal("3.0"),
        cache_read_weight=Decimal("0.06"),
        sort_order=2,
    ),
]


async def seed_models(db: AsyncSession) -> None:
    for spec in DEFAULT_MODELS:
        existing = await db.execute(select(Model).where(Model.model_key == spec["model_key"]))
        if existing.scalar_one_or_none() is None:
            db.add(Model(**spec))
    await db.commit()


async def seed_admin(db: AsyncSession) -> None:
    existing = await db.execute(select(User).where(User.username == settings.admin_username))
    if existing.scalar_one_or_none() is not None:
        return
    admin = User(
        username=settings.admin_username,
        display_name="مدیر سیستم",
        email=settings.admin_email or None,
        role=UserRole.admin,
        password_hash=hash_password(settings.admin_password),
    )
    db.add(admin)
    await db.commit()


async def run_seed(db: AsyncSession) -> None:
    await seed_models(db)
    await seed_admin(db)
