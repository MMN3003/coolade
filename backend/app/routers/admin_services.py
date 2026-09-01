"""Admin — organizational services catalog + grants (amendment-1, SV1/SV3).

Credentials are write-only: accepted on create/update, Fernet-encrypted at
rest, decrypted only inside the MCP gateway's connector layer — no endpoint
here (or anywhere) ever returns them.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_db, require_admin
from app.errors import bad_request, not_found
from app.models import GrantLevel, Service, ServiceGrant, ServiceKind, User
from app.schemas import (
    OkResponse,
    ServiceCreate,
    ServiceGrantOut,
    ServiceGrantSet,
    ServiceOut,
    ServiceTestOut,
    ServiceUpdate,
)
from app.security import decrypt_secret, encrypt_secret
from app.services import org_services
from app.services.audit import record_audit

router = APIRouter(prefix="/api/admin/services", tags=["admin-services"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return base[:60] or "service"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    candidate = base
    n = 2
    while True:
        if (
            await db.execute(select(Service.id).where(Service.slug == candidate))
        ).scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{n}"[:60]
        n += 1


async def _grant_counts(db: AsyncSession, service_ids: list[int]) -> dict[int, int]:
    if not service_ids:
        return {}
    rows = await db.execute(
        select(ServiceGrant.service_id, func.count(ServiceGrant.id))
        .where(ServiceGrant.service_id.in_(service_ids))
        .group_by(ServiceGrant.service_id)
    )
    return dict(rows.all())


def _service_out(svc: Service, grant_count: int) -> ServiceOut:
    return ServiceOut(
        id=svc.id,
        slug=svc.slug,
        name=svc.name,
        description=svc.description,
        kind=svc.kind.value if hasattr(svc.kind, "value") else str(svc.kind),
        enabled=svc.enabled,
        config=svc.config or {},
        has_write_conn=bool(svc.conn_write_enc),
        skill_version=svc.skill_version,
        grant_count=grant_count,
        created_at=svc.created_at,
    )


async def _get_service(db: AsyncSession, service_id: int) -> Service:
    svc = (
        await db.execute(select(Service).where(Service.id == service_id))
    ).scalar_one_or_none()
    if svc is None:
        raise not_found("سرویس یافت نشد.")
    return svc


@router.get("", response_model=list[ServiceOut])
async def list_services(
    _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[ServiceOut]:
    services = (await db.execute(select(Service).order_by(Service.id))).scalars().all()
    counts = await _grant_counts(db, [s.id for s in services])
    return [_service_out(s, counts.get(s.id, 0)) for s in services]


@router.post("", response_model=ServiceOut)
async def create_service(
    payload: ServiceCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ServiceOut:
    if payload.kind != "sql":
        raise bad_request("در این نسخه فقط connector نوع sql پشتیبانی می‌شود (P5a).")
    slug = await _unique_slug(db, _slugify(payload.slug or payload.name))
    svc = Service(
        slug=slug,
        name=payload.name,
        description=payload.description,
        kind=ServiceKind(payload.kind),
        config=payload.config or {},
        conn_read_enc=encrypt_secret(payload.conn_read),
        conn_write_enc=encrypt_secret(payload.conn_write) if payload.conn_write else None,
        created_by=admin.id,
    )
    db.add(svc)
    await db.flush()
    await record_audit(
        db, actor_id=admin.id, action="service.create", target_id=svc.id,
        detail={"slug": slug, "kind": payload.kind}, ip_address=client_ip(request),
    )
    await db.commit()
    return _service_out(svc, 0)


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    service_id: int,
    payload: ServiceUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ServiceOut:
    svc = await _get_service(db, service_id)
    changed: list[str] = []
    if payload.name is not None:
        svc.name = payload.name
        changed.append("name")
    if payload.description is not None:
        svc.description = payload.description
        changed.append("description")
    if payload.enabled is not None:
        svc.enabled = payload.enabled
        changed.append("enabled")
    if payload.config is not None:
        svc.config = payload.config
        changed.append("config")
    if payload.conn_read:
        svc.conn_read_enc = encrypt_secret(payload.conn_read)
        changed.append("conn_read")
    if payload.conn_write:
        svc.conn_write_enc = encrypt_secret(payload.conn_write)
        changed.append("conn_write")
    await record_audit(
        db, actor_id=admin.id, action="service.update", target_id=svc.id,
        detail={"slug": svc.slug, "fields": changed}, ip_address=client_ip(request),
    )
    await db.commit()
    counts = await _grant_counts(db, [svc.id])
    return _service_out(svc, counts.get(svc.id, 0))


@router.delete("/{service_id}", response_model=OkResponse)
async def delete_service(
    service_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    svc = await _get_service(db, service_id)
    await record_audit(
        db, actor_id=admin.id, action="service.delete", target_id=svc.id,
        detail={"slug": svc.slug}, ip_address=client_ip(request),
    )
    await db.delete(svc)  # grants/audit cascade
    await db.commit()
    return OkResponse()


@router.post("/{service_id}/test", response_model=ServiceTestOut)
async def test_service(
    service_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ServiceTestOut:
    svc = await _get_service(db, service_id)
    dsn = decrypt_secret(svc.conn_read_enc)
    if not dsn:
        return ServiceTestOut(ok=False, message="اعتبارنامهٔ ذخیره‌شده قابل رمزگشایی نیست.")
    ok, message = await org_services.test_connection(svc.kind, dsn)
    return ServiceTestOut(ok=ok, message=message)


# ---------------------------------------------------------------- grants
@router.get("/{service_id}/grants", response_model=list[ServiceGrantOut])
async def list_grants(
    service_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ServiceGrantOut]:
    await _get_service(db, service_id)
    rows = await db.execute(
        select(ServiceGrant, User)
        .join(User, User.id == ServiceGrant.user_id)
        .where(ServiceGrant.service_id == service_id)
        .order_by(User.username)
    )
    return [
        ServiceGrantOut(
            user_id=u.id,
            username=u.username,
            display_name=u.display_name,
            level=g.level.value if hasattr(g.level, "value") else str(g.level),
            created_at=g.created_at,
        )
        for g, u in rows.all()
    ]


@router.put("/{service_id}/grants/{user_id}", response_model=OkResponse)
async def set_grant(
    service_id: int,
    user_id: int,
    payload: ServiceGrantSet,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    svc = await _get_service(db, service_id)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("کاربر یافت نشد.")
    existing = (
        await db.execute(
            select(ServiceGrant).where(
                ServiceGrant.service_id == service_id, ServiceGrant.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.level = GrantLevel(payload.level)
    else:
        db.add(
            ServiceGrant(
                service_id=service_id,
                user_id=user_id,
                level=GrantLevel(payload.level),
                granted_by=admin.id,
            )
        )
    await record_audit(
        db, actor_id=admin.id, action="service.grant", target_id=service_id,
        detail={"slug": svc.slug, "user_id": user_id, "level": payload.level},
        ip_address=client_ip(request),
    )
    await db.commit()
    return OkResponse()


@router.delete("/{service_id}/grants/{user_id}", response_model=OkResponse)
async def revoke_grant(
    service_id: int,
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    svc = await _get_service(db, service_id)
    await db.execute(
        delete(ServiceGrant).where(
            ServiceGrant.service_id == service_id, ServiceGrant.user_id == user_id
        )
    )
    await record_audit(
        db, actor_id=admin.id, action="service.revoke", target_id=service_id,
        detail={"slug": svc.slug, "user_id": user_id}, ip_address=client_ip(request),
    )
    await db.commit()
    return OkResponse()
