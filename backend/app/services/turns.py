"""Turn-lifecycle helpers shared by startup recovery and Issue C retry (TECH.md 5.1, 5.4)."""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageStatus

ABORTED_RESTART_REASON = "سرویس هنگام تولید پاسخ راه‌اندازی مجدد شد."


async def mark_interrupted_streaming_as_failed(db: AsyncSession) -> int:
    """Startup recovery (TECH.md section 3/5.1): any assistant row still 'streaming'
    when the process starts belonged to a turn whose background task/registry died
    with the previous process — it can never complete. Fail it so the UI shows a
    retry button instead of waiting forever."""
    result = await db.execute(
        update(Message)
        .where(Message.status == MessageStatus.streaming)
        .values(
            status=MessageStatus.failed,
            error_code="aborted_restart",
            error_reason=ABORTED_RESTART_REASON,
        )
    )
    await db.commit()
    return result.rowcount or 0
