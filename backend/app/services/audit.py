"""Audit log writer. Never stores chat content — metadata only (TECH.md 3, 11.1)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record_audit(
    db: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    target_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        actor_id=actor_id,
        target_id=target_id,
        action=action,
        detail=detail,
        ip_address=ip_address if ip_address and ip_address != "unknown" else None,
    )
    db.add(entry)
    await db.flush()
