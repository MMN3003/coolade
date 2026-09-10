"""amendment-7 (docs/KNOWLEDGE.md) — admin knowledge endpoints.

  /api/admin/knowledge/services/{service_id}                 scope service
  /api/admin/knowledge/services/{service_id}/users/{user_id} scope user_service
  /api/admin/knowledge/users/{user_id}                       scope user (about a person)
  /api/admin/knowledge/teams/{team_id}                       scope team
  /api/admin/knowledge/entries/{id}                          edit/delete any entry
  /api/admin/knowledge/stats
  /api/admin/knowledge/learning        GET/PUT settings; POST …/run = manual pass
  /api/admin/knowledge/export/conversations.jsonl   chat transcripts (dataset)
  /api/admin/knowledge/export/entries.jsonl         all knowledge entries
  /api/admin/knowledge/users/{user_id}/conversations           a user's chats (audited)
  /api/admin/knowledge/conversations/{conversation_id}         one chat's messages (audited)

Exports are the seed for the product owner's «سیستم سازمانی آموزش‌دیده» plan:
plain JSONL, one conversation per line in chat format. Every export is written
to audit_log (who, filters, row count) — transcripts are people's chats.
"""
from __future__ import annotations

import datetime
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import client_ip, get_db, require_admin
from app.errors import bad_request, not_found
from app.models import (
    Conversation,
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeScope,
    KnowledgeSource,
    Message,
    MessageStatus,
    Model,
    Service,
    Team,
    User,
)
from app.schemas import (
    AdminConversationDetailOut,
    AdminConversationMessageOut,
    AdminConversationOut,
    KnowledgeEntryCreate,
    KnowledgeEntryOut,
    KnowledgeEntryUpdate,
    KnowledgeStatsOut,
    LearningRunOut,
    LearningSettingsOut,
    LearningSettingsSet,
    OkResponse,
    UserLearningSet,
)
from app.services import knowledge as knowledge_service
from app.services import learning
from app.services.audit import record_audit

router = APIRouter(prefix="/api/admin/knowledge", tags=["admin-knowledge"])
settings = get_settings()


def _out(e: KnowledgeEntry) -> KnowledgeEntryOut:
    return KnowledgeEntryOut(**knowledge_service.to_dict(e), admin_locked=False)


async def _list(db: AsyncSession, scope: KnowledgeScope, **keys) -> list[KnowledgeEntryOut]:
    stmt = select(KnowledgeEntry).where(KnowledgeEntry.scope == scope)
    for col in ("service_id", "user_id", "team_id"):
        val = keys.get(col)
        stmt = stmt.where(
            getattr(KnowledgeEntry, col).is_(None) if val is None else getattr(KnowledgeEntry, col) == val
        )
    rows = (
        await db.execute(stmt.order_by(KnowledgeEntry.sort_order, KnowledgeEntry.id))
    ).scalars().all()
    return [_out(e) for e in rows]


async def _create(
    db: AsyncSession,
    request: Request,
    admin: User,
    payload: KnowledgeEntryCreate,
    scope: KnowledgeScope,
    **keys,
) -> KnowledgeEntryOut:
    try:
        title = knowledge_service.clean_title(payload.title)
        content = knowledge_service.clean_content(payload.content)
    except ValueError as exc:
        raise bad_request(str(exc))
    entry = KnowledgeEntry(
        scope=scope,
        kind=KnowledgeKind(payload.kind),
        source=KnowledgeSource.manual,
        title=title,
        content=content,
        enabled=payload.enabled,
        sort_order=payload.sort_order,
        created_by=admin.id,
        **keys,
    )
    db.add(entry)
    await db.flush()
    await record_audit(
        db, actor_id=admin.id, action="knowledge.create", target_id=keys.get("user_id"),
        detail={"id": entry.id, "scope": scope.value, **{k: v for k, v in keys.items() if v}},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(entry)
    return _out(entry)


async def _service(db: AsyncSession, service_id: int) -> Service:
    svc = await db.get(Service, service_id)
    if svc is None:
        raise not_found("سرویس یافت نشد.")
    return svc


async def _user(db: AsyncSession, user_id: int) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise not_found("کاربر یافت نشد.")
    return u


async def _team(db: AsyncSession, team_id: int) -> Team:
    t = await db.get(Team, team_id)
    if t is None:
        raise not_found("تیم یافت نشد.")
    return t


# ---------------------------------------------------------------- service scope
@router.get("/services/{service_id}", response_model=list[KnowledgeEntryOut])
async def service_entries(
    service_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[KnowledgeEntryOut]:
    await _service(db, service_id)
    return await _list(db, KnowledgeScope.service, service_id=service_id)


@router.post("/services/{service_id}", response_model=KnowledgeEntryOut)
async def add_service_entry(
    service_id: int,
    payload: KnowledgeEntryCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    await _service(db, service_id)
    return await _create(db, request, admin, payload, KnowledgeScope.service, service_id=service_id)


@router.get("/services/{service_id}/users/{user_id}", response_model=list[KnowledgeEntryOut])
async def user_service_entries(
    service_id: int,
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeEntryOut]:
    await _service(db, service_id)
    await _user(db, user_id)
    return await _list(db, KnowledgeScope.user_service, service_id=service_id, user_id=user_id)


@router.post("/services/{service_id}/users/{user_id}", response_model=KnowledgeEntryOut)
async def add_user_service_entry(
    service_id: int,
    user_id: int,
    payload: KnowledgeEntryCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    await _service(db, service_id)
    await _user(db, user_id)
    return await _create(
        db, request, admin, payload, KnowledgeScope.user_service, service_id=service_id, user_id=user_id
    )


# ---------------------------------------------------------------- user / team scope
@router.get("/users/{user_id}", response_model=list[KnowledgeEntryOut])
async def user_entries(
    user_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[KnowledgeEntryOut]:
    await _user(db, user_id)
    return await _list(db, KnowledgeScope.user, user_id=user_id)


@router.post("/users/{user_id}", response_model=KnowledgeEntryOut)
async def add_user_entry(
    user_id: int,
    payload: KnowledgeEntryCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    await _user(db, user_id)
    return await _create(db, request, admin, payload, KnowledgeScope.user, user_id=user_id)


@router.put("/users/{user_id}/learning", response_model=OkResponse)
async def set_user_learning(
    user_id: int,
    payload: UserLearningSet,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    """Admin toggles chat-learning for one user (knowledge is admin-managed;
    there is no self-service toggle)."""
    u = await _user(db, user_id)
    u.learning_enabled = payload.enabled
    await record_audit(
        db, actor_id=admin.id, action="knowledge.learning_pref", target_id=user_id,
        detail={"enabled": payload.enabled}, ip_address=client_ip(request),
    )
    await db.commit()
    return OkResponse()


@router.get("/teams/{team_id}", response_model=list[KnowledgeEntryOut])
async def team_entries(
    team_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[KnowledgeEntryOut]:
    await _team(db, team_id)
    return await _list(db, KnowledgeScope.team, team_id=team_id)


@router.post("/teams/{team_id}", response_model=KnowledgeEntryOut)
async def add_team_entry(
    team_id: int,
    payload: KnowledgeEntryCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    await _team(db, team_id)
    return await _create(db, request, admin, payload, KnowledgeScope.team, team_id=team_id)


# ---------------------------------------------------------------- edit / delete
@router.patch("/entries/{entry_id}", response_model=KnowledgeEntryOut)
async def update_entry(
    entry_id: int,
    payload: KnowledgeEntryUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise not_found("مورد یافت نشد.")
    try:
        if payload.title is not None:
            entry.title = knowledge_service.clean_title(payload.title)
        if payload.content is not None:
            entry.content = knowledge_service.clean_content(payload.content)
    except ValueError as exc:
        raise bad_request(str(exc))
    if payload.kind is not None:
        entry.kind = KnowledgeKind(payload.kind)
    if payload.enabled is not None:
        entry.enabled = payload.enabled
    if payload.sort_order is not None:
        entry.sort_order = payload.sort_order
    entry.updated_at = func.now()
    await record_audit(
        db, actor_id=admin.id, action="knowledge.update", target_id=entry.user_id,
        detail={"id": entry.id, "scope": entry.scope.value}, ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(entry)
    return _out(entry)


@router.delete("/entries/{entry_id}", response_model=OkResponse)
async def delete_entry(
    entry_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise not_found("مورد یافت نشد.")
    await record_audit(
        db, actor_id=admin.id, action="knowledge.delete", target_id=entry.user_id,
        detail={"id": entry.id, "scope": entry.scope.value, "title": entry.title},
        ip_address=client_ip(request),
    )
    await db.delete(entry)
    await db.commit()
    return OkResponse()


# ---------------------------------------------------------------- admin reads of chats
# Product decision (2026-09-10): an admin may read a user's conversations when
# needed (to understand/curate what the assistant learned). Every read is
# audit-logged with the target user and conversation id.
@router.get("/users/{user_id}/conversations", response_model=list[AdminConversationOut])
async def user_conversations(
    user_id: int,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminConversationOut]:
    await _user(db, user_id)
    msg_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id, Message.status == MessageStatus.complete)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Conversation, Model.model_key, msg_count)
            .join(Model, Model.id == Conversation.model_id, isouter=True)
            .where(Conversation.user_id == user_id, Conversation.deleted_at.is_(None))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
    ).all()
    await record_audit(
        db, actor_id=admin.id, action="knowledge.read_conversations", target_id=user_id,
        detail={"rows": len(rows)}, ip_address=client_ip(request),
    )
    await db.commit()
    return [
        AdminConversationOut(
            id=c.id, title=c.title, model_key=mk, message_count=int(n or 0),
            created_at=c.created_at, updated_at=c.updated_at,
        )
        for c, mk, n in rows
    ]


@router.get("/conversations/{conversation_id}", response_model=AdminConversationDetailOut)
async def conversation_detail(
    conversation_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminConversationDetailOut:
    row = (
        await db.execute(
            select(Conversation, User.username, Model.model_key)
            .join(User, User.id == Conversation.user_id)
            .join(Model, Model.id == Conversation.model_id, isouter=True)
            .where(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        raise not_found("گفتگو یافت نشد.")
    conv, username, model_key = row
    msgs = (
        await db.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
        )
    ).scalars().all()
    await record_audit(
        db, actor_id=admin.id, action="knowledge.read_conversation", target_id=conv.user_id,
        detail={"conversation_id": conv.id, "messages": len(msgs)}, ip_address=client_ip(request),
    )
    await db.commit()
    return AdminConversationDetailOut(
        id=conv.id, title=conv.title, model_key=model_key, message_count=len(msgs),
        created_at=conv.created_at, updated_at=conv.updated_at,
        user_id=conv.user_id, username=username,
        messages=[
            AdminConversationMessageOut(
                id=m.id, role=m.role, content=m.content,
                status=getattr(m.status, "value", str(m.status)), created_at=m.created_at,
            )
            for m in msgs
        ],
    )


# ---------------------------------------------------------------- stats / learning
@router.get("/stats", response_model=KnowledgeStatsOut)
async def stats(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> KnowledgeStatsOut:
    by_scope = dict(
        (
            await db.execute(
                select(KnowledgeEntry.scope, func.count(KnowledgeEntry.id)).group_by(KnowledgeEntry.scope)
            )
        ).all()
    )
    by_source = dict(
        (
            await db.execute(
                select(KnowledgeEntry.source, func.count(KnowledgeEntry.id)).group_by(KnowledgeEntry.source)
            )
        ).all()
    )
    conv_total = (
        await db.execute(select(func.count(Conversation.id)).where(Conversation.deleted_at.is_(None)))
    ).scalar_one()
    msg_total = (
        await db.execute(
            select(func.count(Message.id)).where(Message.status == MessageStatus.complete)
        )
    ).scalar_one()
    return KnowledgeStatsOut(
        total=sum(by_scope.values()),
        by_scope={getattr(k, "value", str(k)): v for k, v in by_scope.items()},
        by_source={getattr(k, "value", str(k)): v for k, v in by_source.items()},
        conversations_total=conv_total,
        messages_total=msg_total,
    )


async def _learning_out(db: AsyncSession) -> LearningSettingsOut:
    learned = (
        await db.execute(
            select(func.count(KnowledgeEntry.id)).where(KnowledgeEntry.source == KnowledgeSource.learned)
        )
    ).scalar_one()
    opted_out = (
        await db.execute(select(func.count(User.id)).where(User.learning_enabled.is_(False)))
    ).scalar_one()
    when, summary = await learning.last_run(db)
    t_when, t_summary = await learning.team_last_run(db)
    team_learned = (
        await db.execute(
            select(func.count(KnowledgeEntry.id)).where(
                KnowledgeEntry.source == KnowledgeSource.learned,
                KnowledgeEntry.scope == KnowledgeScope.team,
            )
        )
    ).scalar_one()
    model = await learning.resolve_model(db)
    return LearningSettingsOut(
        team_enabled=await learning.is_team_enabled(db),
        team_interval_hours=settings.team_learning_interval_hours,
        team_min_new_messages=settings.team_learning_min_new_messages,
        team_max_entries=settings.team_learning_max_entries,
        team_learned_entries=team_learned,
        team_last_run_at=t_when,
        team_last_run_summary=t_summary,
        global_enabled=await learning.is_enabled(db),
        model_key=model.model_key if model else None,
        interval_minutes=settings.learning_interval_minutes,
        idle_minutes=settings.learning_idle_minutes,
        min_new_user_messages=settings.learning_min_new_user_messages,
        max_entries_per_user=settings.learning_max_entries_per_user,
        learned_entries=learned,
        users_opted_out=opted_out,
        last_run_at=when,
        last_run_summary=summary,
    )


@router.get("/learning", response_model=LearningSettingsOut)
async def learning_settings(
    _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> LearningSettingsOut:
    return await _learning_out(db)


@router.put("/learning", response_model=LearningSettingsOut)
async def set_learning_settings(
    payload: LearningSettingsSet,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> LearningSettingsOut:
    if payload.global_enabled is not None:
        await learning.set_enabled(db, payload.global_enabled, admin.id)
    if payload.team_enabled is not None:
        await learning.set_team_enabled(db, payload.team_enabled, admin.id)
    if payload.model_key is not None:
        key = payload.model_key.strip()
        if key:
            m = (
                await db.execute(select(Model).where(Model.model_key == key, Model.is_enabled.is_(True)))
            ).scalar_one_or_none()
            if m is None:
                raise bad_request("مدل یافت نشد یا غیرفعال است.")
        await learning.set_model_key(db, key, admin.id)
    await record_audit(
        db, actor_id=admin.id, action="knowledge.learning_settings", target_id=None,
        detail=payload.model_dump(exclude_none=True), ip_address=client_ip(request),
    )
    await db.commit()
    return await _learning_out(db)


@router.post("/learning/run", response_model=LearningRunOut)
async def run_learning_now(
    request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> LearningRunOut:
    await record_audit(
        db, actor_id=admin.id, action="knowledge.learning_run", target_id=None,
        detail={}, ip_address=client_ip(request),
    )
    await db.commit()
    result = await learning.run_once(force=True, by=admin.id)
    team = await learning.run_team_once(force=True, by=admin.id)
    return LearningRunOut(
        **result,
        teams=team["teams"],
        team_entries_added=team["entries_added"],
        team_entries_updated=team["entries_updated"],
        team_errors=team["errors"],
    )


# ---------------------------------------------------------------- exports
def _parse_ts(value: str | None, name: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise bad_request(f"پارامتر {name} باید تاریخ ISO باشد.")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


@router.get("/export/conversations.jsonl")
async def export_conversations(
    request: Request,
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    min_messages: int = Query(default=2, ge=1),
    limit: int = Query(default=5000, ge=1, le=50000),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dataset export: one conversation per line —
    {"conversation_id","user_id","username","model","created_at","messages":[{"role","content"}]}.
    Only complete, non-empty messages; failed/streaming rows are skipped."""
    since_dt, until_dt = _parse_ts(since, "since"), _parse_ts(until, "until")
    stmt = (
        select(Conversation, User.username, Model.model_key)
        .join(User, User.id == Conversation.user_id)
        .join(Model, Model.id == Conversation.model_id, isouter=True)
        .where(Conversation.deleted_at.is_(None))
        .order_by(Conversation.id)
        .limit(limit)
    )
    if since_dt:
        stmt = stmt.where(Conversation.updated_at >= since_dt)
    if until_dt:
        stmt = stmt.where(Conversation.updated_at < until_dt)
    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)
    convs = (await db.execute(stmt)).all()

    lines: list[str] = []
    for conv, username, model_key in convs:
        msgs = (
            await db.execute(
                select(Message.role, Message.content)
                .where(
                    Message.conversation_id == conv.id,
                    Message.status == MessageStatus.complete,
                    Message.content != "",
                )
                .order_by(Message.id)
            )
        ).all()
        if len(msgs) < min_messages:
            continue
        rec: dict[str, Any] = {
            "conversation_id": conv.id,
            "user_id": conv.user_id,
            "username": username,
            "model": model_key,
            "created_at": conv.created_at.isoformat(),
            "messages": [{"role": r, "content": c} for r, c in msgs],
        }
        lines.append(json.dumps(rec, ensure_ascii=False))

    await record_audit(
        db, actor_id=admin.id, action="knowledge.export_conversations", target_id=user_id,
        detail={"since": since, "until": until, "rows": len(lines)}, ip_address=client_ip(request),
    )
    await db.commit()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        iter(["\n".join(lines) + ("\n" if lines else "")]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="conversations-{stamp}.jsonl"'},
    )


@router.get("/export/entries.jsonl")
async def export_entries(
    request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(
            select(KnowledgeEntry, User.username, Service.slug, Team.slug)
            .join(User, User.id == KnowledgeEntry.user_id, isouter=True)
            .join(Service, Service.id == KnowledgeEntry.service_id, isouter=True)
            .join(Team, Team.id == KnowledgeEntry.team_id, isouter=True)
            .order_by(KnowledgeEntry.id)
        )
    ).all()
    lines = []
    for e, username, svc_slug, team_slug in rows:
        d = knowledge_service.to_dict(e)
        d["created_at"] = d["created_at"].isoformat()
        d["updated_at"] = d["updated_at"].isoformat()
        d.update({"username": username, "service_slug": svc_slug, "team_slug": team_slug})
        lines.append(json.dumps(d, ensure_ascii=False))
    await record_audit(
        db, actor_id=admin.id, action="knowledge.export_entries", target_id=None,
        detail={"rows": len(lines)}, ip_address=client_ip(request),
    )
    await db.commit()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        iter(["\n".join(lines) + ("\n" if lines else "")]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="knowledge-{stamp}.jsonl"'},
    )
