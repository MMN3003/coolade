from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.deps import client_ip, get_current_user, get_db
from app.errors import not_found
from app.models import User
from app.schemas import WorkspaceFileOut
from app.services.audit import record_audit
from app.workspace_files import guess_mime, list_workspace_files, resolve_file_id
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("/files", response_model=list[WorkspaceFileOut])
async def list_files(user: User = Depends(get_current_user)) -> list[WorkspaceFileOut]:
    entries = list_workspace_files(user.id)
    return [WorkspaceFileOut(**e.to_dict()) for e in entries]


@router.get("/files/{file_id}")
async def download_file(file_id: str, user: User = Depends(get_current_user)) -> FileResponse:
    path = resolve_file_id(user.id, file_id)
    if path is None:
        raise not_found("فایل یافت نشد.")
    return FileResponse(path, filename=path.name, media_type=guess_mime(path))


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    path = resolve_file_id(user.id, file_id)
    if path is None:
        raise not_found("فایل یافت نشد.")
    path.unlink()
    await record_audit(
        db,
        actor_id=user.id,
        action="workspace.file_delete",
        target_id=user.id,
        detail={"name": path.name},
        ip_address=ip,
    )
    await db.commit()
    return {"ok": True}
