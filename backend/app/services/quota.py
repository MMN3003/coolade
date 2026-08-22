"""Quota pre-check + periodic reset logic (TECH.md 5.1[3], 5.4, 5.8 / Issue E)."""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import quota_exceeded, quota_exceeded_5h
from app.models import Quota, QuotaPeriod, UsageLedger
from app.services.audit import record_audit

settings = get_settings()


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


async def get_5h_window_state(
    db: AsyncSession, user_id: int, window_hours: float | None = None
) -> tuple[Decimal, datetime.datetime | None]:
    """اصلاحیهٔ ۳ / Issue E (TECH.md 5.8): rolling window, no reset — usage is the
    live SUM(credits) over [now-window, now]; `reset_5h_at` (partial release — the
    window frees up as soon as the OLDEST ledger row inside it ages out) is
    MIN(created_at) + window. Single query, covered by idx_ledger_user_time."""
    hours = window_hours if window_hours is not None else settings.rolling_window_hours
    window = datetime.timedelta(hours=hours)
    now = datetime.datetime.now(datetime.timezone.utc)
    window_start = now - window
    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageLedger.credits), 0),
            func.min(UsageLedger.created_at),
        ).where(
            UsageLedger.user_id == user_id,
            UsageLedger.created_at >= window_start,
        )
    )
    used, oldest = result.one()
    reset_5h_at = (oldest + window) if oldest is not None else None
    return Decimal(used), reset_5h_at


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


@dataclasses.dataclass
class QuotaCheckResult:
    quota: Quota
    used: Decimal
    budget: Decimal
    reset_at: datetime.datetime
    used_5h: Decimal
    limit_credits_5h: Decimal | None
    reset_5h_at: datetime.datetime | None


async def check_quota(
    db: AsyncSession,
    *,
    user_id: int,
    ip_address: str | None = None,
) -> QuotaCheckResult:
    """Raise quota_exceeded / quota_exceeded_5h (429, Persian) if the user is over
    budget on EITHER cap — both are enforced on every call, from both surfaces
    (web chat + API-key passthrough, TECH.md 5.1[4]/5.2[3]/5.8). Weekly is checked
    first (unchanged behavior); the rolling 5h cap is checked second — whichever
    fills first is the one that rejects.
    """
    quota = await get_or_create_quota(db, user_id)
    used = await get_used_credits(db, user_id, quota.period_start)
    budget = quota.limit_credits + quota.bonus_credits
    reset_at = quota.period_start + period_length(quota.period)
    used_5h, reset_5h_at = await get_5h_window_state(db, user_id)

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
        raise quota_exceeded(
            "سقف مصرف دوره تمام شده است. لطفاً منتظر دورهٔ بعد بمانید یا از ادمین درخواست افزایش سهمیه کنید.",
            reset_at=reset_at.isoformat(),
        )

    limit_5h = quota.limit_credits_5h
    if limit_5h and limit_5h > 0 and used_5h >= limit_5h:
        await record_audit(
            db,
            actor_id=user_id,
            action="request.denied_quota_5h",
            target_id=user_id,
            detail={"used_5h": str(used_5h), "limit_credits_5h": str(limit_5h)},
            ip_address=ip_address,
        )
        await db.commit()
        raise quota_exceeded_5h(
            reset_5h_at=reset_5h_at.isoformat() if reset_5h_at else None,
        )

    return QuotaCheckResult(
        quota=quota,
        used=used,
        budget=budget,
        reset_at=reset_at,
        used_5h=used_5h,
        limit_credits_5h=limit_5h,
        reset_5h_at=reset_5h_at,
    )


def period_length(period: QuotaPeriod) -> relativedelta:
    if period == QuotaPeriod.daily:
        return relativedelta(days=1)
    if period == QuotaPeriod.monthly:
        return relativedelta(months=1)
    return relativedelta(weeks=1)


async def run_periodic_reset(db: AsyncSession) -> int:
    """Advance period_start for quotas whose period elapsed; zero bonus. No audit (system event).
    اصلاحیهٔ ۳ / Issue E: untouched — the rolling 5h window has no reset, it is always
    computed live from usage_ledger (TECH.md 5.8)."""
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
