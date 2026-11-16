"""APScheduler job: advance quota.period_start every 5 minutes (TECH.md section 5.5)."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.db import async_session_factory
from app.services.quota import run_periodic_reset
from app.services import learning, reaper

logger = logging.getLogger("coolade.scheduler")
settings = get_settings()


async def _job() -> None:
    async with async_session_factory() as db:
        try:
            advanced = await run_periodic_reset(db)
            if advanced:
                logger.info("quota periodic reset advanced %d quotas", advanced)
        except Exception:
            logger.exception("quota periodic reset failed")


async def _reaper_job() -> None:
    # v2 — idle-stop / disk-refresh / GC of workspaces (TECH-V2 §2.5/§2.6)
    try:
        await reaper.run_once()
    except Exception:
        logger.exception("workspace reaper failed")


async def _learning_job() -> None:
    # amendment-7 — learn durable facts from idle conversations (docs/KNOWLEDGE.md)
    try:
        await learning.run_once()
    except Exception:
        logger.exception("chat learning pass failed")


async def _team_learning_job() -> None:
    try:
        await learning.run_team_once()
    except Exception:
        logger.exception("team learning pass failed")


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_job, "interval", minutes=5, id="quota_reset")
    scheduler.add_job(
        _reaper_job, "interval", minutes=settings.workspace_reaper_minutes, id="workspace_reaper"
    )
    scheduler.add_job(
        _learning_job,
        "interval",
        minutes=max(1, settings.learning_interval_minutes),
        id="chat_learning",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _team_learning_job,
        "interval",
        hours=max(1, settings.team_learning_interval_hours),
        id="team_learning",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    return scheduler
