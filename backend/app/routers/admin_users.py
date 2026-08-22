from __future__ import annotations

import csv
import datetime
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_db, require_admin
from app.errors import bad_request, not_found
from app.models import ApiKey, Model, ModelPolicy, Quota, QuotaPeriod, User, UsageLedger
from app.schemas import (
    AdminUserUsageResponse,
    FiveHourQuotaBlock,
    PolicySetRequest,
    QuotaBonusRequest,
    QuotaOut,
    QuotaSetRequest,
    UsageByKey,
    UsageByModel,
    UsageDailyPoint,
    UserCreate,
    UserDetailOut,
    UserOut,
    UserUpdate,
    WeeklyQuotaBlock,
)
from app.security import hash_password
from app.services.audit import record_audit
from app.services.litellm_client import litellm_client
from app.services.quota import get_5h_window_state, get_or_create_quota, get_used_credits, period_length

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


async def _user_detail(db: AsyncSession, user: User) -> UserDetailOut:
    result = await db.execute(
        select(Model.model_key)
        .join(ModelPolicy, ModelPolicy.model_id == Model.id)
        .where(ModelPolicy.user_id == user.id)
    )
    allowed_models = [r[0] for r in result.all()]
    quota_row = (
        await db.execute(select(Quota).where(Quota.user_id == user.id))
    ).scalar_one_or_none()
    quota = (
        QuotaOut(
            period=getattr(quota_row.period, "value", quota_row.period),
            limit_credits=quota_row.limit_credits,
            bonus_credits=quota_row.bonus_credits,
            period_start=quota_row.period_start,
            limit_credits_5h=quota_row.limit_credits_5h,
        )
        if quota_row
        else None
    )
    return UserDetailOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=getattr(user.role, "value", user.role),
        auth_source=getattr(user.auth_source, "value", user.auth_source),
        is_active=user.is_active,
        created_at=user.created_at,
        allowed_models=allowed_models,
        quota=quota,
    )


@router.get("", response_model=list[UserOut])
async def list_users(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> list[UserOut]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.post("", response_model=UserOut)
async def create_user(
    body: UserCreate,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise bad_request("این نام کاربری قبلاً استفاده شده است.")

    if body.auth_source == "local" and not body.password:
        raise bad_request("برای کاربر محلی رمز عبور الزامی است.")

    user = User(
        username=body.username,
        display_name=body.display_name,
        email=body.email,
        role=body.role,
        auth_source=body.auth_source,
        password_hash=hash_password(body.password) if body.auth_source == "local" else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await record_audit(
        db, actor_id=admin.id, action="user.create", target_id=user.id,
        detail={"username": user.username}, ip_address=ip,
    )
    await db.commit()
    return user


@router.get("/{user_id}", response_model=UserDetailOut)
async def get_user(user_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> UserDetailOut:
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")
    return await _user_detail(db, user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        user.email = body.email
    if body.role is not None:
        user.role = body.role
    if body.password is not None:
        user.password_hash = hash_password(body.password)

    was_active = user.is_active
    if body.is_active is not None:
        user.is_active = body.is_active

    if was_active and body.is_active is False:
        keys = await db.execute(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active.is_(True)))
        for key in keys.scalars():
            key.is_active = False
            if key.litellm_key_id:
                try:
                    await litellm_client.key_delete(key.litellm_key_id)
                except Exception:
                    pass
        await record_audit(
            db, actor_id=admin.id, action="user.disable", target_id=user.id, ip_address=ip
        )

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")
    keys = await db.execute(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active.is_(True)))
    for key in keys.scalars():
        if key.litellm_key_id:
            try:
                await litellm_client.key_delete(key.litellm_key_id)
            except Exception:
                pass
    await record_audit(db, actor_id=admin.id, action="user.delete", target_id=user.id, ip_address=ip)
    await db.delete(user)
    await db.commit()
    return {"ok": True}


@router.put("/{user_id}/policy")
async def set_policy(
    user_id: int,
    body: PolicySetRequest,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")

    result = await db.execute(select(Model).where(Model.model_key.in_(body.model_keys)))
    models = list(result.scalars().all())
    found_keys = {m.model_key for m in models}
    missing = set(body.model_keys) - found_keys
    if missing:
        raise bad_request(f"مدل‌های نامعتبر: {', '.join(missing)}")

    await db.execute(delete(ModelPolicy).where(ModelPolicy.user_id == user_id))
    for m in models:
        db.add(ModelPolicy(user_id=user_id, model_id=m.id))

    keys = await db.execute(select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.is_active.is_(True)))
    for key in keys.scalars():
        if key.litellm_key_id:
            try:
                await litellm_client.key_update(key.litellm_key_id, models=list(found_keys))
            except Exception:
                pass

    await record_audit(
        db, actor_id=admin.id, action="policy.change", target_id=user_id,
        detail={"model_keys": list(found_keys)}, ip_address=ip,
    )
    await db.commit()
    return {"ok": True}


@router.put("/{user_id}/quota")
async def set_quota(
    user_id: int,
    body: QuotaSetRequest,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")
    quota = await get_or_create_quota(db, user_id)
    old_limit = quota.limit_credits
    old_limit_5h = quota.limit_credits_5h
    quota.period = QuotaPeriod(body.period)
    quota.limit_credits = body.limit_credits
    # اصلاحیهٔ ۳ / Issue E — NULL/0 = unlimited (not enforced), TECH.md 8.
    quota.limit_credits_5h = body.limit_credits_5h
    await record_audit(
        db, actor_id=admin.id, action="quota.change", target_id=user_id,
        detail={
            "old_limit": str(old_limit), "new_limit": str(body.limit_credits), "period": body.period,
            "old_limit_credits_5h": str(old_limit_5h) if old_limit_5h is not None else None,
            "new_limit_credits_5h": str(body.limit_credits_5h) if body.limit_credits_5h is not None else None,
        },
        ip_address=ip,
    )
    await db.commit()
    return {"ok": True}


@router.post("/{user_id}/quota/bonus")
async def add_quota_bonus(
    user_id: int,
    body: QuotaBonusRequest,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")
    quota = await get_or_create_quota(db, user_id)
    quota.bonus_credits = Decimal(quota.bonus_credits) + Decimal(body.bonus_credits)
    await record_audit(
        db, actor_id=admin.id, action="quota.bonus", target_id=user_id,
        detail={"bonus_credits": str(body.bonus_credits)}, ip_address=ip,
    )
    await db.commit()
    return {"ok": True}


def _default_since() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)


async def _user_usage_rows(db: AsyncSession, user_id: int, since: datetime.datetime):
    """اصلاحیهٔ ۳ / Issue G (TECH.md 11.1 privacy rule): reads ONLY usage_ledger/
    quotas — never messages/conversations.title/attachments. Same query shapes as
    GET /api/usage/me (admin_usage.py's org-wide aggregation, filtered to one user)."""
    by_model_rows = await db.execute(
        select(Model.model_key, func.coalesce(func.sum(UsageLedger.credits), 0))
        .join(Model, Model.id == UsageLedger.model_id)
        .where(UsageLedger.user_id == user_id, UsageLedger.created_at >= since)
        .group_by(Model.model_key)
    )
    by_model = [UsageByModel(model_key=r[0], credits=r[1]) for r in by_model_rows.all()]

    by_key_rows = await db.execute(
        select(UsageLedger.api_key_id, func.coalesce(func.sum(UsageLedger.credits), 0))
        .where(UsageLedger.user_id == user_id, UsageLedger.created_at >= since)
        .group_by(UsageLedger.api_key_id)
    )
    key_names = {
        k.id: k.name
        for k in (await db.execute(select(ApiKey).where(ApiKey.user_id == user_id))).scalars()
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
        .where(UsageLedger.user_id == user_id, UsageLedger.created_at >= since)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    daily = [UsageDailyPoint(date=r[0].date(), credits=r[1]) for r in daily_rows.all()]
    return by_model, by_key, daily


@router.get("/{user_id}/usage", response_model=AdminUserUsageResponse)
async def user_usage_report(
    user_id: int,
    since: datetime.datetime | None = Query(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserUsageResponse:
    """اصلاحیهٔ ۳ / Issue G: same data as the user's own "مصرف من" — daily trend +
    by_model + by_key + current 5h/weekly blocks — just admin-facing metadata.
    Never touches messages/conversations.title/attachments (TECH.md 11.1)."""
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")

    window_start = since or _default_since()
    by_model, by_key, daily = await _user_usage_rows(db, user_id, window_start)

    quota = await get_or_create_quota(db, user_id)
    used = await get_used_credits(db, user_id, quota.period_start)
    used_5h, reset_5h_at = await get_5h_window_state(db, user_id)
    reset_at = quota.period_start + period_length(quota.period)

    return AdminUserUsageResponse(
        user_id=user.id,
        username=user.username,
        by_model=by_model,
        by_key=by_key,
        daily=daily,
        weekly=WeeklyQuotaBlock(
            used=used,
            limit=quota.limit_credits,
            bonus=quota.bonus_credits,
            period=getattr(quota.period, "value", quota.period),
            period_start=quota.period_start,
            reset_at=reset_at,
        ),
        five_hour=FiveHourQuotaBlock(
            used_5h=used_5h,
            limit_credits_5h=quota.limit_credits_5h,
            reset_5h_at=reset_5h_at,
        ),
    )


@router.get("/{user_id}/usage/export.csv")
async def export_user_usage_csv(
    user_id: int,
    since: datetime.datetime | None = Query(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """اصلاحیهٔ ۳ / Issue G (nice-to-have): single-user CSV, same columns as the
    org-wide /api/admin/usage/export.csv, filtered to this user."""
    user = await db.get(User, user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")

    window_start = since or _default_since()
    rows = await db.execute(
        select(
            UsageLedger.created_at,
            Model.model_key,
            UsageLedger.surface,
            UsageLedger.input_tokens,
            UsageLedger.output_tokens,
            UsageLedger.cache_read_tokens,
            UsageLedger.credits,
        )
        .join(Model, Model.id == UsageLedger.model_id)
        .where(UsageLedger.user_id == user_id, UsageLedger.created_at >= window_start)
        .order_by(UsageLedger.created_at)
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["created_at", "username", "model_key", "surface", "input_tokens", "output_tokens", "cache_read_tokens", "credits"]
    )
    for r in rows.all():
        writer.writerow([r[0].isoformat(), user.username, r[1], r[2], r[3], r[4], r[5], str(r[6])])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=usage_{user.username}.csv"},
    )
