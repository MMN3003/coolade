"""Admin — teams (اصلاحیهٔ ۴ / Issue H, TECH.md section 8/10).

Slug is generated at creation (from `slug` if given, else `name`) and unique-ified;
it is immutable afterwards — it names the on-disk symlink target
(`/data/teams/<id>/memory`, exposed to members as `./teams/<slug>/`).
"""
from __future__ import annotations

import re
import shutil

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_db, require_admin
from app.errors import bad_request, not_found
from app.models import Team, TeamMember, User
from app.schemas import (
    TeamCreate,
    TeamDetailOut,
    TeamMemberAdd,
    TeamMemberOut,
    TeamOut,
    TeamUpdate,
    WorkspaceFileOut,
)
from app.services.audit import record_audit
from app.team_files import guess_mime, list_team_files, receive_upload, resolve_team_file_id, team_root_dir

router = APIRouter(prefix="/api/admin/teams", tags=["admin-teams"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return base[:80] or "team"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    candidate = base
    n = 2
    while True:
        existing = await db.execute(select(Team.id).where(Team.slug == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{n}"[:80]
        n += 1


async def _member_counts(db: AsyncSession, team_ids: list[int]) -> dict[int, int]:
    if not team_ids:
        return {}
    rows = await db.execute(
        select(TeamMember.team_id, func.count(TeamMember.user_id))
        .where(TeamMember.team_id.in_(team_ids))
        .group_by(TeamMember.team_id)
    )
    return dict(rows.all())


def _team_out(team: Team, member_count: int) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        slug=team.slug,
        description=team.description,
        member_count=member_count,
        created_at=team.created_at,
    )


async def _get_team_or_404(db: AsyncSession, team_id: int) -> Team:
    team = await db.get(Team, team_id)
    if not team:
        raise not_found("تیم یافت نشد.")
    return team


@router.get("", response_model=list[TeamOut])
async def list_teams(
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[TeamOut]:
    result = await db.execute(select(Team).order_by(Team.name))
    teams = list(result.scalars().all())
    counts = await _member_counts(db, [t.id for t in teams])
    return [_team_out(t, counts.get(t.id, 0)) for t in teams]


@router.post("", response_model=TeamOut)
async def create_team(
    body: TeamCreate,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    base_slug = _slugify(body.slug or body.name)
    slug = await _unique_slug(db, base_slug)
    team = Team(name=body.name, slug=slug, description=body.description)
    db.add(team)
    await db.commit()
    await db.refresh(team)
    await record_audit(
        db, actor_id=admin.id, action="team.create", target_id=None,
        detail={"team_id": team.id, "slug": slug, "name": team.name}, ip_address=ip,
    )
    await db.commit()
    return _team_out(team, 0)


@router.get("/{team_id}", response_model=TeamDetailOut)
async def get_team(
    team_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> TeamDetailOut:
    team = await _get_team_or_404(db, team_id)
    members_result = await db.execute(
        select(TeamMember, User.username, User.display_name)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(User.username)
    )
    member_rows = members_result.all()
    member_list = [
        TeamMemberOut(
            user_id=tm.user_id,
            username=u,
            display_name=dn,
            role_in_team=getattr(tm.role_in_team, "value", tm.role_in_team),
            created_at=tm.created_at,
        )
        for tm, u, dn in member_rows
    ]
    base = _team_out(team, len(member_list))
    return TeamDetailOut(**base.model_dump(), members=member_list)


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: int,
    body: TeamUpdate,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    team = await _get_team_or_404(db, team_id)
    if body.name is not None:
        team.name = body.name
    if body.description is not None:
        team.description = body.description
    await record_audit(
        db, actor_id=admin.id, action="team.update", target_id=None,
        detail={"team_id": team_id}, ip_address=ip,
    )
    await db.commit()
    await db.refresh(team)
    counts = await _member_counts(db, [team_id])
    return _team_out(team, counts.get(team_id, 0))


@router.delete("/{team_id}")
async def delete_team(
    team_id: int,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    team = await _get_team_or_404(db, team_id)
    slug = team.slug
    await db.delete(team)  # team_members rows CASCADE

    # DEVIATION from TECH.md section 8's admin-teams table, which says the
    # /data/teams/<id> directory is left on disk for manual cleanup (mirroring
    # user workspaces). This task's explicit Issue H brief overrides that:
    # "Delete team -> remove members + its /data/teams/<id> dir (and audit)" — so
    # the on-disk directory is removed here too, best-effort.
    dir_path = team_root_dir(team_id)
    dir_removed = False
    if dir_path.exists():
        shutil.rmtree(dir_path, ignore_errors=True)
        dir_removed = not dir_path.exists()

    await record_audit(
        db, actor_id=admin.id, action="team.delete", target_id=None,
        detail={"team_id": team_id, "slug": slug, "dir_removed": dir_removed}, ip_address=ip,
    )
    await db.commit()
    return {"ok": True}


@router.post("/{team_id}/members", response_model=TeamMemberOut)
async def add_member(
    team_id: int,
    body: TeamMemberAdd,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberOut:
    await _get_team_or_404(db, team_id)
    user = await db.get(User, body.user_id)
    if not user:
        raise not_found("کاربر یافت نشد.")
    existing = await db.get(TeamMember, {"team_id": team_id, "user_id": body.user_id})
    if existing:
        raise bad_request("کاربر از قبل عضو این تیم است.")
    member = TeamMember(team_id=team_id, user_id=body.user_id, role_in_team=body.role_in_team)
    db.add(member)
    await record_audit(
        db, actor_id=admin.id, action="team.member_add", target_id=body.user_id,
        detail={"team_id": team_id, "role_in_team": body.role_in_team}, ip_address=ip,
    )
    await db.commit()
    return TeamMemberOut(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role_in_team=body.role_in_team,
        created_at=member.created_at,
    )


@router.delete("/{team_id}/members/{user_id}")
async def remove_member(
    team_id: int,
    user_id: int,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_team_or_404(db, team_id)
    member = await db.get(TeamMember, {"team_id": team_id, "user_id": user_id})
    if not member:
        raise not_found("عضویت یافت نشد.")
    await db.delete(member)
    await record_audit(
        db, actor_id=admin.id, action="team.member_remove", target_id=user_id,
        detail={"team_id": team_id}, ip_address=ip,
    )
    await db.commit()
    return {"ok": True}


# ---------- memory (admin can manage any team's memory, no membership needed) ----------


@router.get("/{team_id}/memory/files", response_model=list[WorkspaceFileOut])
async def admin_list_memory_files(
    team_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[WorkspaceFileOut]:
    await _get_team_or_404(db, team_id)
    return [WorkspaceFileOut(**e.to_dict()) for e in list_team_files(team_id)]


@router.post("/{team_id}/memory/files", response_model=WorkspaceFileOut)
async def admin_upload_memory_file(
    team_id: int,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceFileOut:
    await _get_team_or_404(db, team_id)
    entry = await receive_upload(team_id, file)
    return WorkspaceFileOut(**entry.to_dict())


@router.get("/{team_id}/memory/files/{file_id}")
async def admin_download_memory_file(
    team_id: int,
    file_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    await _get_team_or_404(db, team_id)
    path = resolve_team_file_id(team_id, file_id)
    if path is None:
        raise not_found("فایل یافت نشد.")
    return FileResponse(path, filename=path.name, media_type=guess_mime(path))


@router.delete("/{team_id}/memory/files/{file_id}")
async def admin_delete_memory_file(
    team_id: int,
    file_id: str,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_team_or_404(db, team_id)
    path = resolve_team_file_id(team_id, file_id)
    if path is None:
        raise not_found("فایل یافت نشد.")
    path.unlink()
    await record_audit(
        db, actor_id=admin.id, action="team.memory.file_delete", target_id=None,
        detail={"team_id": team_id, "name": path.name}, ip_address=ip,
    )
    await db.commit()
    return {"ok": True}
