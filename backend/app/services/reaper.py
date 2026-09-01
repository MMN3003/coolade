"""v2 — workspace reaper (TECH-V2 §2.5/§2.6): idle-stop, disk refresh, GC.

Runs on the shared APScheduler. Three duties each tick:
  1. idle-stop: running workspaces with no activity for `workspace_idle_minutes` → stop.
  2. disk refresh: recompute each running workspace's volume size (for the per-user quota).
  3. GC: stopped workspaces untouched for `workspace_retention_days` → delete.

Reconciliation is implicit: docker container_state is the source of truth for whether a
row's status still matches reality; a mismatch is corrected here.
"""
from __future__ import annotations

import datetime
import logging

from sqlalchemy import select

from app.config import get_settings
from app.db import async_session_factory
from app.models import Workspace
from app.services import workspaces as ws

settings = get_settings()
logger = logging.getLogger("ecocode.reaper")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def run_once() -> dict:
    stopped = deleted = refreshed = reconciled = 0
    idle_cutoff = _now() - datetime.timedelta(minutes=settings.workspace_idle_minutes)
    gc_cutoff = _now() - datetime.timedelta(days=settings.workspace_retention_days)

    async with async_session_factory() as db:
        rows = (await db.execute(select(Workspace))).scalars().all()
        for w in rows:
            try:
                state = await ws.container_state(w.id)

                # reconcile DB status with docker reality
                if w.status == "running" and state != "running":
                    w.status = "stopped"
                    reconciled += 1

                # 1. idle-stop
                if w.status == "running" and state == "running" and w.last_activity_at < idle_cutoff:
                    await ws.stop_container(w.id)
                    w.status = "stopped"
                    stopped += 1
                    continue

                # 2. disk refresh (running only; cheap enough at this scale)
                if state == "running":
                    w.disk_bytes = await ws.disk_bytes(w.id)
                    refreshed += 1

                # 3. GC abandoned stopped workspaces
                if w.status == "stopped" and w.last_activity_at < gc_cutoff:
                    # guard: never GC a repo workspace with unpushed commits
                    if w.kind == "repo" and await _has_unpushed(w.id):
                        logger.warning("reaper: skip GC of ws %s (unpushed commits)", w.id)
                    else:
                        await ws.remove_container(w.id, drop_volume=True)
                        await db.delete(w)
                        deleted += 1
            except Exception:
                logger.exception("reaper: workspace %s failed", w.id)
        await db.commit()

    if stopped or deleted or reconciled:
        logger.info(
            "reaper: stopped=%d deleted=%d reconciled=%d refreshed=%d",
            stopped, deleted, reconciled, refreshed,
        )
    return {"stopped": stopped, "deleted": deleted, "reconciled": reconciled, "refreshed": refreshed}


async def _has_unpushed(ws_id: int) -> bool:
    """True if the workspace git repo has commits not on any remote branch."""
    rc, out = await ws._run(
        "docker", "run", "--rm", "-v", f"{ws.volume_name(ws_id)}:/w:ro",
        "--entrypoint", "sh", settings.workspace_image, "-c",
        "cd /w && git log --branches --not --remotes --oneline 2>/dev/null | head -1",
        timeout=60,
    )
    return rc == 0 and bool(out.strip())
