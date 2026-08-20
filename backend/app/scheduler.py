"""APScheduler job: advance quota.period_start every 5 minutes (TECH.md section 5.5)."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import async_session_factory
from app.services.quota import run_periodic_reset

logger = logging.getLogger("ecocode.scheduler")


async def _job() -> None:
    async with async_session_factory() as db:
        try:
            advanced = await run_periodic_reset(db)
            if advanced:
                logger.info("quota periodic reset advanced %d quotas", advanced)
        except Exception:
            logger.exception("quota periodic reset failed")


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_job, "interval", minutes=5, id="quota_reset")
    scheduler.start()
    return scheduler
