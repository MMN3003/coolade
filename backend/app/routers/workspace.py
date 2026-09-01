from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.cli_runner import workspace_dir
from app.deps import client_ip, get_current_user, get_db
from app.errors import bad_request, not_found
from app.file_store import encode_file_id, resolve_writable_path
from app.models import User
from app.schemas import WorkspaceFileContentOut, WorkspaceFileOut, WorkspaceFileSaveIn
from app.services.audit import record_audit
from app.workspace_files import guess_mime, list_workspace_files, resolve_file_id
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

# Max size the web editor will read/save as text. Bigger files stay downloadable
# via the binary endpoint but are not opened in Monaco.
_MAX_EDIT_BYTES = 1_000_000


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


@router.get("/files/{file_id}/content", response_model=WorkspaceFileContentOut)
async def read_file_content(
    file_id: str, user: User = Depends(get_current_user)
) -> WorkspaceFileContentOut:
    """اصلاحیهٔ ۶ / amendment 6: read a workspace file as UTF-8 text for the web editor.
    Rejects binary (non-UTF-8) files; truncates over the edit cap."""
    path = resolve_file_id(user.id, file_id)
    if path is None:
        raise not_found("فایل یافت نشد.")
    raw = path.read_bytes()
    truncated = len(raw) > _MAX_EDIT_BYTES
    raw = raw[:_MAX_EDIT_BYTES]
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise bad_request("این فایل متنی نیست و در ادیتور باز نمی‌شود.")
    ws = workspace_dir(user.id)
    relpath = str(path.relative_to(ws.resolve()))
    return WorkspaceFileContentOut(
        file_id=file_id, relpath=relpath, content=content, truncated=truncated
    )


@router.put("/file", response_model=WorkspaceFileOut)
async def save_file(
    body: WorkspaceFileSaveIn,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceFileOut:
    """اصلاحیهٔ ۶ / amendment 6: create or overwrite a workspace text file from the web
    editor. Enforces the same realpath containment the CLI sandbox uses — a relpath
    escaping the user's workspace is rejected."""
    if len(body.content.encode("utf-8")) > _MAX_EDIT_BYTES:
        raise bad_request("حجم فایل برای ذخیره از حد مجاز بیشتر است.")
    ws = workspace_dir(user.id)
    target = resolve_writable_path(ws, body.relpath)
    if target is None:
        raise bad_request("مسیر فایل نامعتبر است یا خارج از فضای کاری شماست.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    stat = target.stat()
    relpath = str(target.relative_to(ws.resolve()))
    await record_audit(
        db,
        actor_id=user.id,
        action="workspace.file_save",
        target_id=user.id,
        detail={"relpath": relpath},
        ip_address=ip,
    )
    await db.commit()
    return WorkspaceFileOut(
        file_id=encode_file_id(relpath),
        name=target.name,
        relpath=relpath,
        size_bytes=stat.st_size,
        modified_at=datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc),
    )


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
