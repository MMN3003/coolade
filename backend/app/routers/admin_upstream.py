from __future__ import annotations

import datetime
import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import client_ip, get_db, require_admin
from app.models import Setting, User
from app.schemas import ApiKeySetRequest, ModeSetRequest, UpstreamStatusOut
from app.security import encrypt_secret
from app.services.audit import record_audit
from app.upstream import credentials as cli_credentials

router = APIRouter(prefix="/api/admin/upstream", tags=["admin-upstream"])
settings = get_settings()


async def _effective_mode(db: AsyncSession) -> str:
    env_mode = os.environ.get("UPSTREAM_MODE")
    if env_mode:
        return env_mode
    row = await db.get(Setting, "upstream.mode")
    return row.value if row and row.value else "mock"


@router.get("/status", response_model=UpstreamStatusOut)
async def upstream_status(
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> UpstreamStatusOut:
    mode = await _effective_mode(db)
    now = datetime.datetime.now(datetime.timezone.utc)

    if mode == "mock":
        return UpstreamStatusOut(
            mode="mock", connected=True, base_url="http://mock-upstream:8080", last_checked=now
        )

    if mode == "cli_creds":
        status = cli_credentials.get_status()
        return UpstreamStatusOut(
            mode="cli_creds",
            connected=status["connected"],
            expires_at=status["expires_at"],
            expiring_soon=status["expiring_soon"],
            creds_source=status["creds_source"],
            base_url=settings.upstream_base_url,
            last_synced=status["last_synced"],
            last_checked=now,
        )

    # apikey
    row = await db.get(Setting, "upstream.apikey")
    return UpstreamStatusOut(
        mode="apikey",
        connected=bool(row and row.value),
        base_url=settings.upstream_base_url,
        last_checked=now,
    )


@router.put("/apikey")
async def set_apikey(
    body: ApiKeySetRequest,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    encrypted = encrypt_secret(body.api_key)
    row = await db.get(Setting, "upstream.apikey")
    if row is None:
        row = Setting(key="upstream.apikey", value=encrypted, is_encrypted=True, updated_by=admin.id)
        db.add(row)
    else:
        row.value = encrypted
        row.is_encrypted = True
        row.updated_by = admin.id
    await record_audit(db, actor_id=admin.id, action="upstream.apikey_set", ip_address=ip)
    await db.commit()
    return {"ok": True}


@router.put("/mode")
async def set_mode(
    body: ModeSetRequest,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(Setting, "upstream.mode")
    old_mode = row.value if row else None
    if row is None:
        row = Setting(key="upstream.mode", value=body.mode, updated_by=admin.id)
        db.add(row)
    else:
        row.value = body.mode
        row.updated_by = admin.id
    await record_audit(
        db,
        actor_id=admin.id,
        action="upstream.mode_change",
        detail={"old_mode": old_mode, "new_mode": body.mode},
        ip_address=ip,
    )
    await db.commit()
    return {"ok": True}
