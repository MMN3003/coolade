from __future__ import annotations

import csv
import datetime
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.models import AuditLog, Model, User, UsageLedger
from app.schemas import (
    AdminTurnRow,
    AdminTurnsResponse,
    AdminUsageResponse,
    AuditLogOut,
    UsageByModel,
    UsageDailyPoint,
    UserUsageRow,
)
from app.services.ledger import credit_breakdown

router = APIRouter(prefix="/api/admin", tags=["admin-usage"])


def _default_since() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)


@router.get("/usage", response_model=AdminUsageResponse)
async def admin_usage(
    since: datetime.datetime | None = Query(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUsageResponse:
    period_start = since or _default_since()

    total_row = await db.execute(
        select(func.coalesce(func.sum(UsageLedger.credits), 0)).where(
            UsageLedger.created_at >= period_start
        )
    )
    total_credits = total_row.scalar_one()

    by_user_rows = await db.execute(
        select(User.id, User.username, func.coalesce(func.sum(UsageLedger.credits), 0))
        .join(UsageLedger, UsageLedger.user_id == User.id)
        .where(UsageLedger.created_at >= period_start)
        .group_by(User.id, User.username)
        .order_by(func.sum(UsageLedger.credits).desc())
    )
    by_user = [UserUsageRow(user_id=r[0], username=r[1], credits=r[2]) for r in by_user_rows.all()]

    by_model_rows = await db.execute(
        select(Model.model_key, func.coalesce(func.sum(UsageLedger.credits), 0))
        .join(UsageLedger, UsageLedger.model_id == Model.id)
        .where(UsageLedger.created_at >= period_start)
        .group_by(Model.model_key)
    )
    by_model = [UsageByModel(model_key=r[0], credits=r[1]) for r in by_model_rows.all()]

    day_expr = func.date_trunc("day", UsageLedger.created_at)
    daily_rows = await db.execute(
        select(day_expr, func.coalesce(func.sum(UsageLedger.credits), 0))
        .where(UsageLedger.created_at >= period_start)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    daily = [UsageDailyPoint(date=r[0].date(), credits=r[1]) for r in daily_rows.all()]

    return AdminUsageResponse(total_credits=total_credits, by_user=by_user, by_model=by_model, daily=daily)


def _turns_query(
    *,
    user_id: int | None,
    surface: str | None,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
):
    q = (
        select(UsageLedger, User.username, Model)
        .join(User, User.id == UsageLedger.user_id)
        .join(Model, Model.id == UsageLedger.model_id)
    )
    if user_id is not None:
        q = q.where(UsageLedger.user_id == user_id)
    if surface:
        q = q.where(UsageLedger.surface == surface)
    if since is not None:
        q = q.where(UsageLedger.created_at >= since)
    if until is not None:
        q = q.where(UsageLedger.created_at < until)
    return q


def _turn_row(entry: UsageLedger, username: str, model: Model) -> AdminTurnRow:
    parts = credit_breakdown(model, entry.input_tokens, entry.output_tokens, entry.cache_read_tokens)
    return AdminTurnRow(
        id=entry.id,
        created_at=entry.created_at,
        user_id=entry.user_id,
        username=username,
        surface=entry.surface,
        conversation_id=entry.conversation_id,
        message_id=entry.message_id,
        model_key=model.model_key,
        model_display_name=model.display_name,
        thinking_level=entry.thinking_level,
        input_tokens=entry.input_tokens,
        output_tokens=entry.output_tokens,
        cache_read_tokens=entry.cache_read_tokens,
        cache_write_tokens=entry.cache_write_tokens,
        credits=entry.credits,
        credits_input=parts["input"],
        credits_output=parts["output"],
        credits_cache_read=parts["cache_read"],
    )


@router.get("/usage/turns", response_model=AdminTurnsResponse)
async def admin_usage_turns(
    user_id: int | None = Query(default=None),
    surface: str | None = Query(default=None),
    since: datetime.datetime | None = Query(default=None),
    until: datetime.datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminTurnsResponse:
    """Per-message token audit: real tokens vs credits charged, model and thinking
    level, newest first. Metadata only — never chat content (TECH.md 11.1)."""
    base = _turns_query(user_id=user_id, surface=surface, since=since, until=until)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(UsageLedger.created_at.desc(), UsageLedger.id.desc()).limit(limit).offset(offset))
    return AdminTurnsResponse(total=total, rows=[_turn_row(e, u, m) for e, u, m in rows.all()])


@router.get("/usage/turns/export.csv")
async def export_usage_turns_csv(
    user_id: int | None = Query(default=None),
    surface: str | None = Query(default=None),
    since: datetime.datetime | None = Query(default=None),
    until: datetime.datetime | None = Query(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    base = _turns_query(user_id=user_id, surface=surface, since=since, until=until)
    rows = await db.execute(base.order_by(UsageLedger.created_at.desc(), UsageLedger.id.desc()).limit(20000))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "ledger_id", "created_at", "user_id", "username", "surface", "conversation_id", "message_id",
        "model_key", "thinking_level", "input_tokens", "output_tokens", "cache_read_tokens",
        "cache_write_tokens", "credits_charged", "credits_input_now", "credits_output_now", "credits_cache_read_now",
    ])
    for e, u, m in rows.all():
        r = _turn_row(e, u, m)
        writer.writerow([
            r.id, r.created_at.isoformat(), r.user_id, r.username, r.surface, r.conversation_id or "",
            r.message_id or "", r.model_key, r.thinking_level or "", r.input_tokens, r.output_tokens,
            r.cache_read_tokens, r.cache_write_tokens, r.credits, r.credits_input, r.credits_output,
            r.credits_cache_read,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage_turns.csv"},
    )


@router.get("/usage/export.csv")
async def export_usage_csv(
    since: datetime.datetime | None = Query(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    period_start = since or _default_since()
    rows = await db.execute(
        select(
            UsageLedger.created_at,
            User.username,
            Model.model_key,
            UsageLedger.surface,
            UsageLedger.input_tokens,
            UsageLedger.output_tokens,
            UsageLedger.cache_read_tokens,
            UsageLedger.credits,
        )
        .join(User, User.id == UsageLedger.user_id)
        .join(Model, Model.id == UsageLedger.model_id)
        .where(UsageLedger.created_at >= period_start)
        .order_by(UsageLedger.created_at)
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["created_at", "username", "model_key", "surface", "input_tokens", "output_tokens", "cache_read_tokens", "credits"]
    )
    for r in rows.all():
        writer.writerow([r[0].isoformat(), r[1], r[2], r[3], r[4], r[5], r[6], str(r[7])])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage.csv"},
    )


@router.get("/audit", response_model=list[AuditLogOut])
async def list_audit(
    action: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    since: datetime.datetime | None = Query(default=None),
    until: datetime.datetime | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogOut]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where((AuditLog.actor_id == user_id) | (AuditLog.target_id == user_id))
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at <= until)

    rows = (await db.execute(stmt)).scalars().all()

    user_ids = {r.actor_id for r in rows if r.actor_id} | {r.target_id for r in rows if r.target_id}
    usernames: dict[int, str] = {}
    if user_ids:
        users = await db.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
        usernames = dict(users.all())

    return [
        AuditLogOut(
            id=r.id,
            actor_id=r.actor_id,
            actor_username=usernames.get(r.actor_id) if r.actor_id else None,
            target_id=r.target_id,
            target_username=usernames.get(r.target_id) if r.target_id else None,
            action=r.action,
            detail=r.detail,
            ip_address=str(r.ip_address) if r.ip_address else None,
            created_at=r.created_at,
        )
        for r in rows
    ]
