from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models import ApiKey, Model, User, UsageLedger
from app.schemas import MyUsageResponse, UsageByKey, UsageByModel, UsageDailyPoint
from app.services.quota import get_5h_window_state, get_or_create_quota, get_used_credits

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/me", response_model=MyUsageResponse)
async def my_usage(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MyUsageResponse:
    quota = await get_or_create_quota(db, user.id)
    used = await get_used_credits(db, user.id, quota.period_start)
    used_5h, reset_5h_at = await get_5h_window_state(db, user.id)

    by_model_rows = await db.execute(
        select(Model.model_key, func.coalesce(func.sum(UsageLedger.credits), 0))
        .join(Model, Model.id == UsageLedger.model_id)
        .where(UsageLedger.user_id == user.id, UsageLedger.created_at >= quota.period_start)
        .group_by(Model.model_key)
    )
    by_model = [UsageByModel(model_key=r[0], credits=r[1]) for r in by_model_rows.all()]

    by_key_rows = await db.execute(
        select(UsageLedger.api_key_id, func.coalesce(func.sum(UsageLedger.credits), 0))
        .where(UsageLedger.user_id == user.id, UsageLedger.created_at >= quota.period_start)
        .group_by(UsageLedger.api_key_id)
    )
    key_names = {
        k.id: k.name
        for k in (
            await db.execute(select(ApiKey).where(ApiKey.user_id == user.id))
        ).scalars()
    }
    by_key = [
        UsageByKey(
            api_key_id=r[0],
            name=key_names.get(r[0], "چت وب") if r[0] else "چت وب",
            credits=r[1],
        )
        for r in by_key_rows.all()
    ]

    day_expr = func.date_trunc("day", UsageLedger.created_at)
    daily_rows = await db.execute(
        select(day_expr, func.coalesce(func.sum(UsageLedger.credits), 0))
        .where(UsageLedger.user_id == user.id, UsageLedger.created_at >= quota.period_start)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    daily = [UsageDailyPoint(date=r[0].date(), credits=r[1]) for r in daily_rows.all()]

    return MyUsageResponse(
        period=getattr(quota.period, "value", quota.period),
        period_start=quota.period_start,
        limit_credits=quota.limit_credits,
        bonus_credits=quota.bonus_credits,
        used_credits=used,
        by_model=by_model,
        by_key=by_key,
        daily=daily,
        used_5h=used_5h,
        limit_credits_5h=quota.limit_credits_5h,
        reset_5h_at=reset_5h_at,
    )
