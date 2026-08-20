"""Quota pre-check + periodic reset logic (TECH.md 5.1[3], 5.4)."""
from __future__ import annotations

import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import quota_exceeded
from app.models import Quota, QuotaPeriod, UsageLedger
from app.services.audit import record_audit


async def get_used_credits(
    db: AsyncSession, user_id: int, period_start: datetime.datetime
) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(UsageLedger.credits), 0)).where(
            UsageLedger.user_id == user_id,
            UsageLedger.created_at >= period_start,
        )
    )
    return Decimal(result.scalar_one())


async def get_or_create_quota(db: AsyncSession, user_id: int) -> Quota:
    result = await db.execute(select(Quota).where(Quota.user_id == user_id))
    quota = result.scalar_one_or_none()
    if quota is None:
        quota = Quota(
            user_id=user_id,
            period=QuotaPeriod.weekly,
            limit_credits=Decimal("0"),
            period_start=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(quota)
        await db.flush()
    return quota


async def check_quota(
    db: AsyncSession,
    *,
    user_id: int,
    ip_address: str | None = None,
) -> tuple[Quota, Decimal, Decimal]:
    """Raise quota_exceeded (429, Persian) if the user is over budget.

    Returns (quota, used_credits, budget).
    """
    quota = await get_or_create_quota(db, user_id)
    used = await get_used_credits(db, user_id, quota.period_start)
    budget = quota.limit_credits + quota.bonus_credits
    if used >= budget:
        await record_audit(
            db,
            actor_id=user_id,
            action="request.denied_quota",
            target_id=user_id,
            detail={"used": str(used), "budget": str(budget)},
            ip_address=ip_address,
        )
        await db.commit()
        raise quota_exceeded("سقف مصرف دوره تمام شده است. لطفاً منتظر دورهٔ بعد بمانید یا از ادمین درخواست افزایش سهمیه کنید.")
    return quota, used, budget


def period_length(period: QuotaPeriod) -> relativedelta:
    if period == QuotaPeriod.daily:
        return relativedelta(days=1)
    if period == QuotaPeriod.monthly:
        return relativedelta(months=1)
    return relativedelta(weeks=1)


async def run_periodic_reset(db: AsyncSession) -> int:
    """Advance period_start for quotas whose period elapsed; zero bonus. No audit (system event)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    result = await db.execute(select(Quota))
    quotas = result.scalars().all()
    advanced = 0
    for quota in quotas:
        step = period_length(quota.period)
        changed = False
        while now >= quota.period_start + step:
            quota.period_start = quota.period_start + step
            quota.bonus_credits = Decimal("0")
            changed = True
        if changed:
            quota.updated_at = now
            advanced += 1
    if advanced:
        await db.commit()
    return advanced
