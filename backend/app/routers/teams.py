"""User-facing team endpoints (اصلاحیهٔ ۴ / Issue H+I, TECH.md section 8):
GET .../mine, GET .../members (member-only), and the team shared-memory file
endpoints. Membership is enforced via team_members (404 — not 403 — for
non-members, so team existence isn't leaked, TECH.md 8/11.1). Admins may manage
any team's memory too; see routers/admin_teams.py, which shares the same
app/team_files.py helpers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_current_user, get_db
from app.errors import not_found
from app.models import Team, TeamMember, User
from app.schemas import TeamMemberOut, TeamMineOut, WorkspaceFileOut
from app.services.audit import record_audit
from app.team_files import guess_mime, list_team_files, receive_upload, resolve_team_file_id
from app.team_membership import is_member

router = APIRouter(prefix="/api/teams", tags=["teams"])


def _is_admin(user: User) -> bool:
    return getattr(user.role, "value", user.role) == "admin"


async def _require_membership(db: AsyncSession, team_id: int, user: User) -> Team:
    """404 (not 403) for non-members so team existence isn't leaked (TECH.md 8/11.1).
    Admins bypass the membership check but the team must still exist."""
    team = await db.get(Team, team_id)
    if not team:
        raise not_found("تیم یافت نشد.")
    if not _is_admin(user) and not await is_member(db, team_id, user.id):
        raise not_found("تیم یافت نشد.")
    return team


@router.get("/mine", response_model=list[TeamMineOut])
async def my_teams(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TeamMineOut]:
    result = await db.execute(
        select(Team.id, Team.name, Team.slug, TeamMember.role_in_team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .order_by(Team.name)
    )
    rows = result.all()
    if not rows:
        return []
    team_ids = [r[0] for r in rows]
    counts_result = await db.execute(
        select(TeamMember.team_id, func.count(TeamMember.user_id))
        .where(TeamMember.team_id.in_(team_ids))
        .group_by(TeamMember.team_id)
    )
    counts = dict(counts_result.all())
    return [
        TeamMineOut(
            id=r[0],
            name=r[1],
            slug=r[2],
            role_in_team=getattr(r[3], "value", r[3]),
            member_count=counts.get(r[0], 0),
        )
        for r in rows
    ]


@router.get("/{team_id}/members", response_model=list[TeamMemberOut])
async def team_members(
    team_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TeamMemberOut]:
    await _require_membership(db, team_id, user)
    result = await db.execute(
        select(TeamMember, User.username, User.display_name)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(User.username)
    )
    return [
        TeamMemberOut(
            user_id=tm.user_id,
            username=username,
            display_name=display_name,
            role_in_team=getattr(tm.role_in_team, "value", tm.role_in_team),
            created_at=tm.created_at,
        )
        for tm, username, display_name in result.all()
    ]


@router.get("/{team_id}/memory/files", response_model=list[WorkspaceFileOut])
async def list_memory_files(
    team_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[WorkspaceFileOut]:
    await _require_membership(db, team_id, user)
    return [WorkspaceFileOut(**e.to_dict()) for e in list_team_files(team_id)]


@router.post("/{team_id}/memory/files", response_model=WorkspaceFileOut)
async def upload_memory_file(
    team_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceFileOut:
    await _require_membership(db, team_id, user)
    entry = await receive_upload(team_id, file)
    return WorkspaceFileOut(**entry.to_dict())


@router.get("/{team_id}/memory/files/{file_id}")
async def download_memory_file(
    team_id: int,
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    await _require_membership(db, team_id, user)
    path = resolve_team_file_id(team_id, file_id)
    if path is None:
        raise not_found("فایل یافت نشد.")
    return FileResponse(path, filename=path.name, media_type=guess_mime(path))


@router.delete("/{team_id}/memory/files/{file_id}")
async def delete_memory_file(
    team_id: int,
    file_id: str,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_membership(db, team_id, user)
    path = resolve_team_file_id(team_id, file_id)
    if path is None:
        raise not_found("فایل یافت نشد.")
    path.unlink()
    await record_audit(
        db,
        actor_id=user.id,
        action="team.memory.file_delete",
        target_id=None,
        detail={"team_id": team_id, "name": path.name},
        ip_address=ip,
    )
    await db.commit()
    return {"ok": True}
