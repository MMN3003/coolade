"""amendment-7 (docs/KNOWLEDGE.md) — user-facing knowledge endpoints («دانش من»).

  /api/knowledge/me                    own rules/knowledge (scope user), incl. learned
  /api/knowledge/me/services           services I hold a grant on (+ my entry counts)
  /api/knowledge/me/services/{slug}    my notes for that service (scope user_service)
  /api/knowledge/teams/{team_id}       my team's shared rules/knowledge (members)
  /api/knowledge/entries/{id}          edit/delete — ownership rules below
  /api/knowledge/me/learning           opt in/out of chat learning

Ownership: a user may edit/delete entries in their own scopes EXCEPT ones an
admin authored about them (admin_locked) — those are org policy for that
person. Team entries: any member may edit (same last-writer-wins spirit as the
team memory folder). Admins go through /api/admin/knowledge/* instead.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_current_user, get_db
from app.errors import bad_request, forbidden, not_found
from app.models import (
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeScope,
    KnowledgeSource,
    Service,
    ServiceGrant,
    Team,
    User,
    UserRole,
)
from app.schemas import (
    KnowledgeEntryCreate,
    KnowledgeEntryOut,
    KnowledgeEntryUpdate,
    LearningPrefOut,
    LearningPrefSet,
    MyServiceOut,
    OkResponse,
)
from app.services import knowledge as knowledge_service
from app.services.audit import record_audit
from app.team_membership import is_member

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _is_admin(user: User) -> bool:
    return getattr(user.role, "value", user.role) == "admin"


async def _admin_ids(db: AsyncSession) -> set[int]:
    rows = await db.execute(select(User.id).where(User.role == UserRole.admin))
    return {r[0] for r in rows.all()}


def _out(e: KnowledgeEntry, admin_ids: set[int], viewer: User) -> KnowledgeEntryOut:
    locked = (
        e.created_by is not None
        and e.created_by in admin_ids
        and e.created_by != viewer.id
        and not _is_admin(viewer)
    )
    return KnowledgeEntryOut(**knowledge_service.to_dict(e), admin_locked=locked)


async def _list(db: AsyncSession, viewer: User, **where) -> list[KnowledgeEntryOut]:
    stmt = select(KnowledgeEntry)
    for col, val in where.items():
        stmt = stmt.where(getattr(KnowledgeEntry, col) == val)
    rows = (
        await db.execute(stmt.order_by(KnowledgeEntry.sort_order, KnowledgeEntry.id))
    ).scalars().all()
    admin_ids = await _admin_ids(db)
    return [_out(e, admin_ids, viewer) for e in rows]


def _apply_create(
    payload: KnowledgeEntryCreate, *, scope: KnowledgeScope, creator: User, **keys
) -> KnowledgeEntry:
    try:
        title = knowledge_service.clean_title(payload.title)
        content = knowledge_service.clean_content(payload.content)
    except ValueError as exc:
        raise bad_request(str(exc))
    return KnowledgeEntry(
        scope=scope,
        kind=KnowledgeKind(payload.kind),
        source=KnowledgeSource.manual,
        title=title,
        content=content,
        enabled=payload.enabled,
        sort_order=payload.sort_order,
        created_by=creator.id,
        **keys,
    )


async def _granted_service(db: AsyncSession, user: User, slug: str) -> Service:
    svc = (
        await db.execute(
            select(Service)
            .join(ServiceGrant, ServiceGrant.service_id == Service.id)
            .where(Service.slug == slug, ServiceGrant.user_id == user.id, Service.enabled.is_(True))
        )
    ).scalar_one_or_none()
    if svc is None:
        raise not_found("سرویس یافت نشد.")  # 404 not 403: don't leak existence
    return svc


async def _member_team(db: AsyncSession, user: User, team_id: int) -> Team:
    team = await db.get(Team, team_id)
    if team is None or (not _is_admin(user) and not await is_member(db, team_id, user.id)):
        raise not_found("تیم یافت نشد.")
    return team


# ---------------------------------------------------------------- me
@router.get("/me", response_model=list[KnowledgeEntryOut])
async def my_entries(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[KnowledgeEntryOut]:
    return await _list(db, user, scope=KnowledgeScope.user, user_id=user.id)


@router.post("/me", response_model=KnowledgeEntryOut)
async def add_my_entry(
    payload: KnowledgeEntryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    entry = _apply_create(payload, scope=KnowledgeScope.user, creator=user, user_id=user.id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _out(entry, set(), user)


@router.get("/me/services", response_model=list[MyServiceOut])
async def my_services(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[MyServiceOut]:
    rows = (
        await db.execute(
            select(Service, ServiceGrant.level)
            .join(ServiceGrant, ServiceGrant.service_id == Service.id)
            .where(ServiceGrant.user_id == user.id, Service.enabled.is_(True))
            .order_by(Service.name)
        )
    ).all()
    counts = dict(
        (
            await db.execute(
                select(KnowledgeEntry.service_id, func.count(KnowledgeEntry.id))
                .where(
                    KnowledgeEntry.scope == KnowledgeScope.user_service,
                    KnowledgeEntry.user_id == user.id,
                )
                .group_by(KnowledgeEntry.service_id)
            )
        ).all()
    )
    return [
        MyServiceOut(
            id=s.id,
            slug=s.slug,
            name=s.name,
            description=s.description,
            kind=getattr(s.kind, "value", str(s.kind)),
            level=getattr(level, "value", str(level)),
            entry_count=counts.get(s.id, 0),
        )
        for s, level in rows
    ]


@router.get("/me/services/{slug}", response_model=list[KnowledgeEntryOut])
async def my_service_entries(
    slug: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[KnowledgeEntryOut]:
    svc = await _granted_service(db, user, slug)
    return await _list(
        db, user, scope=KnowledgeScope.user_service, user_id=user.id, service_id=svc.id
    )


@router.post("/me/services/{slug}", response_model=KnowledgeEntryOut)
async def add_my_service_entry(
    slug: str,
    payload: KnowledgeEntryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    svc = await _granted_service(db, user, slug)
    entry = _apply_create(
        payload, scope=KnowledgeScope.user_service, creator=user, user_id=user.id, service_id=svc.id
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _out(entry, set(), user)


@router.get("/me/learning", response_model=LearningPrefOut)
async def my_learning(user: User = Depends(get_current_user)) -> LearningPrefOut:
    return LearningPrefOut(enabled=bool(user.learning_enabled))


@router.put("/me/learning", response_model=LearningPrefOut)
async def set_my_learning(
    payload: LearningPrefSet,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LearningPrefOut:
    row = await db.get(User, user.id)
    row.learning_enabled = payload.enabled
    await record_audit(
        db, actor_id=user.id, action="knowledge.learning_pref", target_id=user.id,
        detail={"enabled": payload.enabled}, ip_address=client_ip(request),
    )
    await db.commit()
    return LearningPrefOut(enabled=payload.enabled)


# ---------------------------------------------------------------- teams
@router.get("/teams/{team_id}", response_model=list[KnowledgeEntryOut])
async def team_entries(
    team_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[KnowledgeEntryOut]:
    await _member_team(db, user, team_id)
    return await _list(db, user, scope=KnowledgeScope.team, team_id=team_id)


@router.post("/teams/{team_id}", response_model=KnowledgeEntryOut)
async def add_team_entry(
    team_id: int,
    payload: KnowledgeEntryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    await _member_team(db, user, team_id)
    entry = _apply_create(payload, scope=KnowledgeScope.team, creator=user, team_id=team_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _out(entry, set(), user)


# ---------------------------------------------------------------- edit/delete
async def _editable_entry(db: AsyncSession, user: User, entry_id: int) -> KnowledgeEntry:
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise not_found("مورد یافت نشد.")
    if _is_admin(user):
        return entry
    if entry.scope in (KnowledgeScope.user, KnowledgeScope.user_service):
        if entry.user_id != user.id:
            raise not_found("مورد یافت نشد.")
        if (
            entry.created_by is not None
            and entry.created_by != user.id
            and entry.created_by in await _admin_ids(db)
        ):
            raise forbidden("این مورد توسط ادمین تعیین شده و فقط ادمین می‌تواند تغییرش دهد.")
        return entry
    if entry.scope == KnowledgeScope.team:
        if entry.team_id is None or not await is_member(db, entry.team_id, user.id):
            raise not_found("مورد یافت نشد.")
        return entry
    raise not_found("مورد یافت نشد.")  # service scope: admin only


@router.patch("/entries/{entry_id}", response_model=KnowledgeEntryOut)
async def update_entry(
    entry_id: int,
    payload: KnowledgeEntryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryOut:
    entry = await _editable_entry(db, user, entry_id)
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
    await db.commit()
    await db.refresh(entry)
    return _out(entry, await _admin_ids(db), user)


@router.delete("/entries/{entry_id}", response_model=OkResponse)
async def delete_entry(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    entry = await _editable_entry(db, user, entry_id)
    await db.delete(entry)
    await db.commit()
    return OkResponse()
