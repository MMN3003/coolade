"""amendment-7 — the `_me` MCP server: personal-memory tools for EVERY user.

Exposed by the MCP gateway at the reserved slug `_me` (routers/mcp_gateway.py).
Caller = whoever the turn key / workspace key / API key resolves to; every tool
acts only on THAT user's own rows (scope `user`, or `user_service` for a service
they hold a grant on). This is what the eco-memory skill («یادت باشه…») calls,
so a remembered fact lands in knowledge_entries and shows up in «دانش من» —
instead of the v1 approach of hand-editing the workspace CLAUDE.md.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.models import (
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeScope,
    KnowledgeSource,
    Service,
    ServiceGrant,
    User,
)
from app.services import knowledge as knowledge_service
from app.services.org_services import SqlGuardError

MAX_USER_ENTRIES = 300

ME_TOOLS: list[dict[str, Any]] = [
    {
        "name": "remember",
        "description": (
            "یک واقعیت/ترجیح/قانون پایدار دربارهٔ کاربر را در حافظهٔ ماندگار او ذخیره می‌کند "
            "(در همهٔ گفتگوهای بعدی در اختیار توست). kind=rule برای دستورهایی که همیشه باید "
            "رعایت شوند («همیشه اعداد را ریالی بنویس»)، kind=knowledge برای دانسته‌ها "
            "(«مدیر مالی شرکت است»). اختیاری: service_slug تا فقط هنگام استفاده از آن سرویس اعمال شود."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "عنوان کوتاه (چند کلمه)"},
                "content": {"type": "string", "description": "متن کوتاه و مستقل"},
                "kind": {"type": "string", "enum": ["rule", "knowledge"]},
                "service_slug": {"type": "string", "description": "slug سرویس (اختیاری)"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "forget",
        "description": "یک مورد از حافظهٔ کاربر را حذف می‌کند (با id از list_memory).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
    {
        "name": "update_memory",
        "description": "متن/عنوان/نوع یک مورد حافظه را به‌روز می‌کند (وقتی چیزی تغییر کرده، به‌جای افزودن مورد تکراری).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "kind": {"type": "string", "enum": ["rule", "knowledge"]},
            },
            "required": ["id"],
        },
    },
    {
        "name": "list_memory",
        "description": (
            "فهرست حافظهٔ ماندگار کاربر (قوانین و دانش شخصی، شامل موارد یادگرفته‌شده از گفتگوها) "
            "و یادداشت‌های او برای سرویس‌ها."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


async def _service_for(db, user_id: int, slug: str) -> Service:
    svc = (
        await db.execute(
            select(Service)
            .join(ServiceGrant, ServiceGrant.service_id == Service.id)
            .where(Service.slug == slug, ServiceGrant.user_id == user_id, Service.enabled.is_(True))
        )
    ).scalar_one_or_none()
    if svc is None:
        raise SqlGuardError(f"سرویس «{slug}» برای این کاربر در دسترس نیست.")
    return svc


async def _own_entry(db, user_id: int, entry_id: int) -> KnowledgeEntry:
    row = await db.get(KnowledgeEntry, entry_id)
    if (
        row is None
        or row.user_id != user_id
        or row.scope not in (KnowledgeScope.user, KnowledgeScope.user_service)
    ):
        raise SqlGuardError("موردی با این id در حافظهٔ شما نیست.")
    return row


async def call_me_tool(db, user: User, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool == "list_memory":
        rows = (
            await db.execute(
                select(KnowledgeEntry, Service.slug, Service.name)
                .join(Service, Service.id == KnowledgeEntry.service_id, isouter=True)
                .where(
                    KnowledgeEntry.user_id == user.id,
                    KnowledgeEntry.scope.in_([KnowledgeScope.user, KnowledgeScope.user_service]),
                )
                .order_by(KnowledgeEntry.scope, KnowledgeEntry.sort_order, KnowledgeEntry.id)
            )
        ).all()
        return {
            "entries": [
                {
                    "id": e.id,
                    "kind": e.kind.value,
                    "source": e.source.value,
                    "enabled": e.enabled,
                    "service": slug,
                    "service_name": name,
                    "title": e.title,
                    "content": e.content,
                }
                for e, slug, name in rows
            ],
            "row_count": len(rows),
        }

    if tool == "remember":
        try:
            title = knowledge_service.clean_title(str(args.get("title") or ""))
            content = knowledge_service.clean_content(str(args.get("content") or ""))
        except ValueError as exc:
            raise SqlGuardError(str(exc))
        kind = KnowledgeKind(str(args.get("kind") or "knowledge"))
        count = (
            await db.execute(
                select(func.count(KnowledgeEntry.id)).where(KnowledgeEntry.user_id == user.id)
            )
        ).scalar_one()
        if count >= MAX_USER_ENTRIES:
            raise SqlGuardError(
                f"حافظه پر است ({MAX_USER_ENTRIES} مورد). اول موارد کهنه را با forget حذف کن."
            )
        slug = str(args.get("service_slug") or "").strip()
        entry = KnowledgeEntry(
            scope=KnowledgeScope.user_service if slug else KnowledgeScope.user,
            kind=kind,
            source=KnowledgeSource.manual,
            user_id=user.id,
            service_id=(await _service_for(db, user.id, slug)).id if slug else None,
            title=title,
            content=content,
            created_by=user.id,
        )
        db.add(entry)
        await db.commit()
        return {"ok": True, "id": entry.id, "message": "ذخیره شد."}

    if tool == "update_memory":
        entry = await _own_entry(db, user.id, int(args.get("id") or 0))
        try:
            if args.get("title"):
                entry.title = knowledge_service.clean_title(str(args["title"]))
            if args.get("content"):
                entry.content = knowledge_service.clean_content(str(args["content"]))
        except ValueError as exc:
            raise SqlGuardError(str(exc))
        if args.get("kind"):
            entry.kind = KnowledgeKind(str(args["kind"]))
        entry.updated_at = func.now()
        await db.commit()
        return {"ok": True, "id": entry.id, "message": "به‌روز شد."}

    if tool == "forget":
        entry = await _own_entry(db, user.id, int(args.get("id") or 0))
        await db.delete(entry)
        await db.commit()
        return {"ok": True, "message": "حذف شد."}

    raise SqlGuardError(f"ابزار ناشناخته: {tool}")
