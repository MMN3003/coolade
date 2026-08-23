"""Membership queries — team_members is the sole source of truth for team access
(TECH.md section 3, 5.4, 5.9, 11.1: "عضویت در team_members تنها مرز دسترسی است").
Shared by the CLI runner (symlink sync + write containment, app/cli_runner.py)
and the team-memory / admin-teams endpoints (membership guard, 404 for
non-members)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team, TeamMember


async def member_team_rows(db: AsyncSession, user_id: int) -> list[tuple[int, str, str]]:
    """[(team_id, slug, name), ...] for every team `user_id` currently belongs to."""
    result = await db.execute(
        select(Team.id, Team.slug, Team.name)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.name)
    )
    return [(r[0], r[1], r[2]) for r in result.all()]


async def is_member(db: AsyncSession, team_id: int, user_id: int) -> bool:
    result = await db.execute(
        select(TeamMember.team_id).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None
