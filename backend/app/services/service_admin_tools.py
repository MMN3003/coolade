"""Service-builder management tools (amendment-1 SV2, product decision 2026-09-02).

Exposed by the MCP gateway at the reserved slug `_admin`, ONLY to callers that
resolve to an admin user. This is what makes the «دستیار سرویس‌ساز» work: the
admin chats with their assistant, which uses these tools to create/update a
service, test its connection, publish a skill package, and grant users.

Every mutation is written to the main audit_log (actor = the admin). These are
admin-persona tools by design; the enforcement story for END USERS (grants,
read-only accounts, per-call checks) is untouched by anything here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.config import get_settings
from app.models import GrantLevel, Service, ServiceGrant, ServiceKind, User
from app.security import decrypt_secret, encrypt_secret
from app.services import org_services
from app.services.audit import record_audit

settings = get_settings()

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")

ADMIN_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_services",
        "description": "فهرست سرویس‌های سازمانی موجود (slug، نوع، وضعیت، نسخهٔ skill، تعداد گرنت).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "upsert_service",
        "description": (
            "ساخت یا ویرایش یک سرویس. برای ساخت: name و kind و conn_read الزامی است. "
            "kind یکی از sql (DSN پستگرس فقط‌خواندنی)، files (مسیر ریشهٔ فایل‌ها روی سرور)، "
            "http (JSON شامل base_url و headers اختیاری). اعتبارنامه رمز شده ذخیره می‌شود."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "شناسه [a-z0-9-]؛ برای ویرایش سرویس موجود"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "kind": {"type": "string", "enum": ["sql", "files", "http"]},
                "conn_read": {"type": "string", "description": "اتصال فقط‌خواندنی (DSN/مسیر/JSON)"},
                "enabled": {"type": "boolean"},
            },
        },
    },
    {
        "name": "test_connection",
        "description": "تست اتصال read یک سرویس (مثل دکمهٔ تست پنل ادمین).",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "publish_skill",
        "description": (
            "انتشار بستهٔ skill برای یک سرویس: نگاشت نام‌فایل→محتوا. باید SKILL.md با "
            "frontmatter (name و description دقیق برای کشف خودکار) داشته باشد. هر انتشار نسخهٔ جدید است "
            "و از نوبت بعدی به ورک‌اسپیس کاربرانِ دارای گرنت سینک می‌شود."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "files": {
                    "type": "object",
                    "description": "نگاشت نام فایل (مثل SKILL.md) به محتوای متنی",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["slug", "files"],
        },
    },
    {
        "name": "set_grant",
        "description": "دادن دسترسی یک کاربر به یک سرویس (سطح read؛ سطح write در فاز بعد فعال می‌شود).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "username": {"type": "string"},
                "level": {"type": "string", "enum": ["read"]},
            },
            "required": ["slug", "username"],
        },
    },
    {
        "name": "revoke_grant",
        "description": "لغو دسترسی یک کاربر از یک سرویس (فوری اثر می‌کند).",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}, "username": {"type": "string"}},
            "required": ["slug", "username"],
        },
    },
    {
        "name": "delete_service",
        "description": "حذف کامل یک سرویس (گرنت‌ها و سوابقش هم پاک می‌شود). فقط با تأیید صریح ادمین.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "list_users",
        "description": "فهرست کاربران فعال (برای انتخاب گرنت).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


async def _get_service(db, slug: str) -> Service | None:
    return (
        await db.execute(select(Service).where(Service.slug == slug))
    ).scalar_one_or_none()


async def call_admin_tool(db, admin: User, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Returns a JSON-able result dict; raises org_services.SqlGuardError for
    user-facing (assistant-facing) validation errors."""
    guard = org_services.SqlGuardError

    if tool == "list_services":
        rows = (await db.execute(select(Service).order_by(Service.id))).scalars().all()
        counts = dict(
            (
                await db.execute(
                    select(ServiceGrant.service_id, func.count(ServiceGrant.id)).group_by(
                        ServiceGrant.service_id
                    )
                )
            ).all()
        )
        return {
            "services": [
                {
                    "slug": s.slug,
                    "name": s.name,
                    "kind": s.kind.value if hasattr(s.kind, "value") else str(s.kind),
                    "enabled": s.enabled,
                    "skill_version": s.skill_version,
                    "grants": counts.get(s.id, 0),
                }
                for s in rows
            ]
        }

    if tool == "list_users":
        rows = (
            (await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.username)))
            .scalars()
            .all()
        )
        return {
            "users": [
                {"username": u.username, "display_name": u.display_name, "role": u.role.value}
                for u in rows
            ]
        }

    if tool == "upsert_service":
        slug = str(args.get("slug") or "").strip()
        svc = await _get_service(db, slug) if slug else None
        if svc is None:
            name = str(args.get("name") or "").strip()
            kind = str(args.get("kind") or "").strip()
            conn_read = str(args.get("conn_read") or "").strip()
            if not name or kind not in ("sql", "files", "http") or not conn_read:
                raise guard("برای ساخت سرویس جدید name و kind و conn_read الزامی است.")
            if not slug:
                slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "service"
            if not _SLUG_RE.match(slug) or slug.startswith("_"):
                raise guard("slug نامعتبر است (فقط a-z0-9-؛ بدون شروع با _).")
            if kind == "http":
                try:
                    json.loads(conn_read)["base_url"]
                except Exception:
                    raise guard('برای kind=http مقدار conn_read باید JSON با کلید base_url باشد.')
            svc = Service(
                slug=slug,
                name=name,
                description=str(args.get("description") or "") or None,
                kind=ServiceKind(kind),
                conn_read_enc=encrypt_secret(conn_read),
                created_by=admin.id,
            )
            db.add(svc)
            await db.flush()
            action = "service.create"
        else:
            if args.get("name"):
                svc.name = str(args["name"])
            if args.get("description") is not None:
                svc.description = str(args["description"]) or None
            if args.get("conn_read"):
                svc.conn_read_enc = encrypt_secret(str(args["conn_read"]))
            if args.get("enabled") is not None:
                svc.enabled = bool(args["enabled"])
            action = "service.update"
        await record_audit(
            db, actor_id=admin.id, action=action, target_id=None,
            detail={"service_id": svc.id, "slug": svc.slug, "via": "builder"},
        )
        await db.commit()
        return {"ok": True, "slug": svc.slug, "id": svc.id}

    if tool == "test_connection":
        svc = await _get_service(db, str(args.get("slug") or ""))
        if svc is None:
            raise guard("سرویسی با این slug نیست.")
        conn = decrypt_secret(svc.conn_read_enc)
        if not conn:
            raise guard("اعتبارنامهٔ ذخیره‌شده قابل رمزگشایی نیست.")
        ok, message = await org_services.test_connection(svc.kind, conn)
        return {"ok": ok, "message": message}

    if tool == "publish_skill":
        svc = await _get_service(db, str(args.get("slug") or ""))
        if svc is None:
            raise guard("سرویسی با این slug نیست.")
        files = args.get("files")
        if not isinstance(files, dict) or not files:
            raise guard("files باید نگاشت غیرخالی نام‌فایل→محتوا باشد.")
        if "SKILL.md" not in files:
            raise guard("بستهٔ skill باید SKILL.md داشته باشد.")
        for fname, content in files.items():
            if not _FILENAME_RE.match(fname):
                raise guard(f"نام فایل نامعتبر: {fname}")
            if not isinstance(content, str) or len(content) > 256 * 1024:
                raise guard(f"محتوای {fname} باید متن زیر 256KB باشد.")
        new_version = svc.skill_version + 1
        dest = Path(settings.services_root) / svc.slug / str(new_version)
        dest.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (dest / fname).write_text(content, encoding="utf-8")
        svc.skill_version = new_version
        await record_audit(
            db, actor_id=admin.id, action="service.publish_skill", target_id=None,
            detail={"service_id": svc.id, "slug": svc.slug, "version": new_version, "files": sorted(files)},
        )
        await db.commit()
        return {"ok": True, "slug": svc.slug, "skill_version": new_version}

    if tool == "delete_service":
        svc = await _get_service(db, str(args.get("slug") or ""))
        if svc is None:
            raise guard("سرویسی با این slug نیست.")
        await record_audit(
            db, actor_id=admin.id, action="service.delete", target_id=None,
            detail={"service_id": svc.id, "slug": svc.slug, "via": "builder"},
        )
        await db.delete(svc)
        await db.commit()
        return {"ok": True, "deleted": svc.slug}

    if tool in ("set_grant", "revoke_grant"):
        svc = await _get_service(db, str(args.get("slug") or ""))
        if svc is None:
            raise guard("سرویسی با این slug نیست.")
        username = str(args.get("username") or "").strip()
        target = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if target is None:
            raise guard(f"کاربری با نام {username} نیست (از list_users استفاده کن).")
        existing = (
            await db.execute(
                select(ServiceGrant).where(
                    ServiceGrant.service_id == svc.id, ServiceGrant.user_id == target.id
                )
            )
        ).scalar_one_or_none()
        if tool == "set_grant":
            if existing is None:
                db.add(
                    ServiceGrant(
                        service_id=svc.id, user_id=target.id,
                        level=GrantLevel.read, granted_by=admin.id,
                    )
                )
            action = "service.grant"
        else:
            if existing is not None:
                await db.delete(existing)
            action = "service.revoke"
        await record_audit(
            db, actor_id=admin.id, action=action, target_id=target.id,
            detail={"service_id": svc.id, "slug": svc.slug, "user": username, "via": "builder"},
        )
        await db.commit()
        return {"ok": True}

    raise guard(f"ابزار ناشناخته: {tool}")
