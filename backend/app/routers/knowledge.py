"""amendment-7 (docs/KNOWLEDGE.md) — the ONE user-facing knowledge surface:
the person's own memory & rules (scope `user`, incl. entries the learning job
extracted from their chats).

  /api/knowledge/me            list / add own rules & knowledge
  /api/knowledge/entries/{id}  edit / delete own entries

Product decision (2026-09-10): everything else — service knowledge, per-user
notes an admin sets, team knowledge, learning switches — is admin-managed via
/api/admin/knowledge/*. Entries an admin authored ABOUT this user are visible
here but read-only (admin_locked). Chat-side «یادت باشه» (the `_me` MCP tools)
writes to the same rows.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.errors import bad_request, forbidden, not_found
from app.models import (
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeScope,
    KnowledgeSource,
    User,
    UserRole,
)
from app.schemas import (
    KnowledgeEntryCreate,
    KnowledgeEntryOut,
    KnowledgeEntryUpdate,
    OkResponse,
)
from app.services import knowledge as knowledge_service

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


# ---------------------------------------------------------------- edit/delete
async def _editable_entry(db: AsyncSession, user: User, entry_id: int) -> KnowledgeEntry:
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise not_found("مورد یافت نشد.")
    if entry.scope != KnowledgeScope.user or entry.user_id != user.id:
        raise not_found("مورد یافت نشد.")  # other scopes are admin-managed
    if (
        entry.created_by is not None
        and entry.created_by != user.id
        and entry.created_by in await _admin_ids(db)
    ):
        raise forbidden("این مورد توسط ادمین تعیین شده و فقط ادمین می‌تواند تغییرش دهد.")
    return entry


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
