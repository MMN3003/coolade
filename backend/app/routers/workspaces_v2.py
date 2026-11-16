"""v2 — persistent workspace REST API + nginx authz endpoint (TECH-V2 §2/§3/§4).

Distinct from the v1 `workspace.py` (which serves per-user chat FILES); this manages
first-class Workspace objects (container lifecycle) and gates code-server access.
"""
from __future__ import annotations

import datetime
import secrets

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_current_user, get_db
from app.errors import bad_request, not_found
from app.config import get_settings
from app.models import GitlabToken, User, Workspace
from app.security import decrypt_secret, encrypt_secret, hash_api_key
from app.services import workspaces as ws
from app.services.audit import record_audit

settings = get_settings()
router = APIRouter(tags=["workspaces-v2"])


# ---------- schemas ----------
class WorkspaceCreate(BaseModel):
    name: str
    kind: str = "repo"  # repo | personal
    repo_url: str | None = None
    base_branch: str | None = "main"


class WorkspaceOut(BaseModel):
    id: int
    name: str
    kind: str
    status: str
    repo_url: str | None = None
    base_branch: str | None = None
    work_branch: str | None = None
    disk_bytes: int
    last_activity_at: datetime.datetime
    created_at: datetime.datetime

    @classmethod
    def of(cls, w: Workspace) -> "WorkspaceOut":
        return cls(
            id=w.id, name=w.name, kind=w.kind, status=w.status, repo_url=w.repo_url,
            base_branch=w.base_branch, work_branch=w.work_branch, disk_bytes=w.disk_bytes,
            last_activity_at=w.last_activity_at, created_at=w.created_at,
        )


class GitlabTokenIn(BaseModel):
    token: str
    gitlab_host: str | None = None


class GitlabTokenStatus(BaseModel):
    connected: bool
    gitlab_host: str | None = None


# ---------- helpers ----------
async def _owned(db: AsyncSession, user: User, ws_id: int) -> Workspace:
    w = await db.get(Workspace, ws_id)
    if not w or w.user_id != user.id:
        raise not_found("ورک‌اسپیس یافت نشد.")
    return w


async def _running_count(db: AsyncSession) -> int:
    r = await db.execute(select(func.count()).select_from(Workspace).where(Workspace.status == "running"))
    return int(r.scalar_one())


# ---------- workspace CRUD ----------
@router.get("/api/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[WorkspaceOut]:
    r = await db.execute(
        select(Workspace).where(Workspace.user_id == user.id).order_by(Workspace.created_at.desc())
    )
    return [WorkspaceOut.of(w) for w in r.scalars().all()]


@router.post("/api/workspaces", response_model=WorkspaceOut)
async def create_workspace(
    body: WorkspaceCreate,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceOut:
    if body.kind not in ("repo", "personal"):
        raise bad_request("نوع ورک‌اسپیس نامعتبر است.")
    if body.kind == "repo" and not body.repo_url:
        raise bad_request("برای ورک‌اسپیس ریپویی، آدرس ریپو لازم است.")
    if await _running_count(db) >= settings.workspace_max_running:
        raise bad_request("ظرفیت ورک‌اسپیس‌های فعال پر است؛ یکی را متوقف کنید یا بعداً تلاش کنید.")

    # per-user disk quota (TECH-V2 §2.6) — self-service: block new when full
    if user.disk_quota_bytes:
        r = await db.execute(
            select(func.coalesce(func.sum(Workspace.disk_bytes), 0)).where(Workspace.user_id == user.id)
        )
        if int(r.scalar_one()) >= user.disk_quota_bytes:
            raise bad_request(
                "سقف فضای شما پر است — یک ورک‌اسپیس یا گفتگوی قدیمی حذف کنید یا retention را کوتاه‌تر کنید."
            )

    w = Workspace(
        user_id=user.id, kind=body.kind, status="provisioning", name=body.name,
        repo_url=body.repo_url, base_branch=body.base_branch,
    )
    db.add(w)
    await db.flush()
    w.container_name = ws.container_name(w.id)
    w.volume_name = ws.volume_name(w.id)
    gw_key = f"coolade-ws{w.id}-{secrets.token_urlsafe(24)}"
    w.gateway_key_hash = hash_api_key(gw_key)
    await db.commit()

    # resolve the user's gitlab token (if any) for cloning
    git_token = None
    git_host = settings.gitlab_default_host
    gt = await db.get(GitlabToken, user.id)
    if gt:
        git_token = decrypt_secret(gt.token_enc)
        git_host = gt.gitlab_host

    try:
        await ws.create_container(
            w.id, gateway_key=gw_key,
            repo_url=w.repo_url, base_branch=w.base_branch,
            git_token=git_token, git_host=git_host,
        )
        w.status = "running"
        w.last_activity_at = datetime.datetime.now(datetime.timezone.utc)
    except ws.WorkspaceError as e:
        w.status = "stopped"
        await db.commit()
        raise bad_request(f"ساخت ورک‌اسپیس ناموفق بود: {e}")
    await db.commit()
    await record_audit(db, actor_id=user.id, action="workspace.create", ip_address=ip)
    return WorkspaceOut.of(w)


@router.get("/api/workspaces/{ws_id}", response_model=WorkspaceOut)
async def get_workspace(
    ws_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WorkspaceOut:
    return WorkspaceOut.of(await _owned(db, user, ws_id))


@router.post("/api/workspaces/{ws_id}/resume", response_model=WorkspaceOut)
async def resume_workspace(
    ws_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WorkspaceOut:
    w = await _owned(db, user, ws_id)
    if w.status == "running" and await ws.container_state(w.id) == "running":
        return WorkspaceOut.of(w)
    if await _running_count(db) >= settings.workspace_max_running:
        raise bad_request("ظرفیت ورک‌اسپیس‌های فعال پر است.")
    try:
        await ws.start_container(w.id)
    except ws.WorkspaceError as e:
        raise bad_request(f"راه‌اندازی ناموفق: {e}")
    w.status = "running"
    w.last_activity_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    return WorkspaceOut.of(w)


@router.post("/api/workspaces/{ws_id}/stop", response_model=WorkspaceOut)
async def stop_workspace(
    ws_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WorkspaceOut:
    w = await _owned(db, user, ws_id)
    await ws.stop_container(w.id)
    w.status = "stopped"
    await db.commit()
    return WorkspaceOut.of(w)


@router.delete("/api/workspaces/{ws_id}")
async def delete_workspace(
    ws_id: int,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    w = await _owned(db, user, ws_id)
    await ws.remove_container(w.id, drop_volume=True)
    await db.delete(w)
    await db.commit()
    await record_audit(db, actor_id=user.id, action="workspace.delete", ip_address=ip)
    return {"ok": True}


# ---------- gitlab token ----------
@router.get("/api/gitlab-token", response_model=GitlabTokenStatus)
async def gitlab_token_status(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GitlabTokenStatus:
    gt = await db.get(GitlabToken, user.id)
    return GitlabTokenStatus(connected=bool(gt), gitlab_host=gt.gitlab_host if gt else None)


@router.put("/api/gitlab-token", response_model=GitlabTokenStatus)
async def set_gitlab_token(
    body: GitlabTokenIn,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> GitlabTokenStatus:
    if not body.token.strip():
        raise bad_request("توکن خالی است.")
    host = (body.gitlab_host or settings.gitlab_default_host).strip()
    gt = await db.get(GitlabToken, user.id)
    if gt:
        gt.token_enc = encrypt_secret(body.token.strip())
        gt.gitlab_host = host
    else:
        db.add(GitlabToken(user_id=user.id, token_enc=encrypt_secret(body.token.strip()), gitlab_host=host))
    await db.commit()
    await record_audit(db, actor_id=user.id, action="gitlab_token.set", ip_address=ip)
    return GitlabTokenStatus(connected=True, gitlab_host=host)


@router.delete("/api/gitlab-token")
async def delete_gitlab_token(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    gt = await db.get(GitlabToken, user.id)
    if gt:
        await db.delete(gt)
        await db.commit()
    return {"ok": True}


# ---------- nginx auth_request: gate /ide/<id>/ by session ownership ----------
@router.get("/internal/authz/workspace/{ws_id}")
async def authz_workspace(
    ws_id: int,
    response: Response,
    user: User = Depends(get_current_user),  # 401 if no valid session
    db: AsyncSession = Depends(get_db),
) -> Response:
    w = await db.get(Workspace, ws_id)
    if not w or w.user_id != user.id:
        return Response(status_code=403)
    if w.status != "running":
        return Response(status_code=409)  # frontend must resume first
    # touch activity so the idle reaper doesn't stop an actively-viewed workspace
    w.last_activity_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    r = Response(status_code=200)
    r.headers["X-Coolade-Upstream"] = f"{ws.container_name(ws_id)}:8080"
    return r
