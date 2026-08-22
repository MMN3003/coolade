from __future__ import annotations

import datetime
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli_runner
from app.config import get_settings
from app.db import async_session_factory
from app.deps import client_ip, get_current_user, get_db
from app.errors import AppError, bad_request, forbidden, model_not_allowed, not_found
from app.models import Attachment, Conversation, Message, Model, ModelPolicy, User
from app.schemas import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    SendMessageRequest,
)
from app.services import ledger
from app.services.quota import check_quota

router = APIRouter(prefix="/api", tags=["conversations"])
settings = get_settings()


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


async def _get_owned_conversation(db: AsyncSession, user: User, conversation_id: int) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id or conv.deleted_at is not None:
        raise not_found("گفتگو یافت نشد.")
    return conv


def _conv_to_out(conv: Conversation, model_key: str | None) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        model_key=model_key,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    stmt = (
        select(Conversation, Model.model_key)
        .join(Model, Model.id == Conversation.model_id, isouter=True)
        .where(Conversation.user_id == user.id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if q:
        stmt = stmt.where(Conversation.title.ilike(f"%{q}%"))
    result = await db.execute(stmt)
    return [_conv_to_out(conv, model_key) for conv, model_key in result.all()]


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    result = await db.execute(select(Model).where(Model.model_key == body.model_key))
    model = result.scalar_one_or_none()
    if not model or not model.is_enabled:
        raise model_not_allowed("این مدل یافت نشد یا غیرفعال است.")
    policy = await db.execute(
        select(ModelPolicy).where(ModelPolicy.user_id == user.id, ModelPolicy.model_id == model.id)
    )
    if policy.scalar_one_or_none() is None:
        raise model_not_allowed("این مدل برای شما مجاز نیست.")

    conv = Conversation(user_id=user.id, title=body.title or "گفتگوی جدید", model_id=model.id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return _conv_to_out(conv, model.model_key)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailOut:
    conv = await _get_owned_conversation(db, user, conversation_id)
    model_key = None
    if conv.model_id:
        model = await db.get(Model, conv.model_id)
        model_key = model.model_key if model else None
    msgs = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    out = _conv_to_out(conv, model_key)
    return ConversationDetailOut(**out.model_dump(), messages=list(msgs.scalars().all()))


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: int,
    body: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = await _get_owned_conversation(db, user, conversation_id)
    if body.title is not None:
        conv.title = body.title
    model_key = None
    if body.model_key is not None:
        result = await db.execute(select(Model).where(Model.model_key == body.model_key))
        model = result.scalar_one_or_none()
        if not model or not model.is_enabled:
            raise model_not_allowed("این مدل یافت نشد یا غیرفعال است.")
        policy = await db.execute(
            select(ModelPolicy).where(
                ModelPolicy.user_id == user.id, ModelPolicy.model_id == model.id
            )
        )
        if policy.scalar_one_or_none() is None:
            raise model_not_allowed("این مدل برای شما مجاز نیست.")
        conv.model_id = model.id
        model_key = model.model_key
    else:
        if conv.model_id:
            m = await db.get(Model, conv.model_id)
            model_key = m.model_key if m else None
    conv.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    await db.refresh(conv)
    return _conv_to_out(conv, model_key)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await _get_owned_conversation(db, user, conversation_id)
    conv.deleted_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    conv = await _get_owned_conversation(db, user, conversation_id)
    if not conv.model_id:
        raise bad_request("ابتدا مدلی برای این گفتگو انتخاب کنید.")
    model = await db.get(Model, conv.model_id)
    if not model or not model.is_enabled:
        raise model_not_allowed()
    policy = await db.execute(
        select(ModelPolicy).where(ModelPolicy.user_id == user.id, ModelPolicy.model_id == model.id)
    )
    if policy.scalar_one_or_none() is None:
        raise model_not_allowed("این مدل برای شما مجاز نیست.")

    await check_quota(db, user_id=user.id, ip_address=ip)

    if not cli_runner.try_acquire_conversation(conv.id):
        raise AppError(409, "chat_busy", "پاسخ قبلی در این گفتگو هنوز در حال پردازش است.")

    user_msg = Message(conversation_id=conv.id, role="user", content=body.content)
    db.add(user_msg)
    conv.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()

    resume_sid = conv.cli_session_id
    upstream_model = model.upstream_model
    model_id = model.id
    conv_id = conv.id
    user_id = user.id

    async def event_stream():
        assistant_text_parts: list[str] = []
        content_blocks: list[dict] = []
        files_changed: list[str] = []
        session_id_captured: str | None = None
        try:
            async for ev in cli_runner.run_conversation_turn(
                user_id=user_id,
                conversation_id=conv_id,
                prompt=body.content,
                upstream_model=upstream_model,
                resume_session_id=resume_sid,
            ):
                etype = ev["event"]
                if etype == "start":
                    session_id_captured = ev.get("session_id")
                    yield _sse("start", {"conversation_id": conv_id})
                elif etype == "delta":
                    assistant_text_parts.append(ev["text"])
                    yield _sse("delta", {"text": ev["text"]})
                elif etype == "tool":
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "name": ev["name"],
                            "summary": ev["summary"],
                            "file_path": ev.get("file_path"),
                        }
                    )
                    if ev.get("file_path"):
                        files_changed.append(ev["file_path"])
                    yield _sse("tool", {"name": ev["name"], "summary": ev["summary"]})
                elif etype == "done":
                    usage = ev["usage"]
                    async with async_session_factory() as sdb:
                        m = await sdb.get(Model, model_id)
                        entry = await ledger.record_usage(
                            sdb,
                            user_id=user_id,
                            model=m,
                            surface="web_chat",
                            input_tokens=usage["input_tokens"],
                            output_tokens=usage["output_tokens"],
                            cache_read_tokens=usage["cache_read_tokens"],
                            cache_write_tokens=usage["cache_write_tokens"],
                            request_id=ev.get("session_id") or session_id_captured,
                        )
                        final_text = ev.get("result_text") or "".join(assistant_text_parts)
                        assistant_msg = Message(
                            conversation_id=conv_id,
                            role="assistant",
                            content=final_text,
                            content_blocks={"tool_uses": content_blocks} if content_blocks else None,
                        )
                        sdb.add(assistant_msg)
                        conv_row = await sdb.get(Conversation, conv_id)
                        if conv_row:
                            sid = ev.get("session_id") or session_id_captured
                            # Persist also when it CHANGED: the runner may have
                            # rebuilt the session after a stale --resume (CLI
                            # session state lost) — the new id must replace the
                            # dead one or every later turn would re-trigger the
                            # fallback.
                            if sid and sid != conv_row.cli_session_id:
                                conv_row.cli_session_id = sid
                            conv_row.updated_at = datetime.datetime.now(datetime.timezone.utc)
                        credits_used = str(entry.credits)
                        await sdb.commit()
                    yield _sse(
                        "done",
                        {
                            "credits_used": credits_used,
                            "files_changed": list(dict.fromkeys(files_changed)),
                        },
                    )
                elif etype == "error":
                    yield _sse("error", {"message": ev.get("message", "خطای نامشخص رخ داد.")})
        finally:
            cli_runner.release_conversation(conv_id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]+")


def _sanitize_filename(name: str) -> str:
    base = os.path.basename(name) or "file"
    cleaned = _SAFE_FILENAME_RE.sub("_", base)
    return cleaned[:200] or "file"


ALLOWED_ATTACHMENT_MIME_PREFIXES = ("text/", "image/", "application/pdf")
ALLOWED_ATTACHMENT_EXTRA_MIMES = {
    "application/json",
    "application/x-python",
    "application/javascript",
    "application/octet-stream",
}


@router.post("/conversations/{conversation_id}/attachments")
async def upload_attachment(
    conversation_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await _get_owned_conversation(db, user, conversation_id)
    ws = cli_runner.workspace_dir(user.id)
    uploads_dir = ws / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise bad_request("حجم فایل بیش از سقف مجاز است.")

    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if not (
        mime_type.startswith(ALLOWED_ATTACHMENT_MIME_PREFIXES)
        or mime_type in ALLOWED_ATTACHMENT_EXTRA_MIMES
    ):
        raise bad_request("نوع فایل مجاز نیست.")

    safe_name = _sanitize_filename(file.filename or "file")
    stored_name = f"{uuid.uuid4().hex[:12]}_{safe_name}"
    dest = uploads_dir / stored_name
    dest.write_bytes(content)

    relpath = str(dest.relative_to(ws))
    attachment = Attachment(
        conversation_id=conv.id,
        filename=safe_name,
        mime_type=mime_type,
        size_bytes=len(content),
        storage_path=relpath,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return {"id": attachment.id, "filename": attachment.filename, "size_bytes": attachment.size_bytes}


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise not_found("فایل یافت نشد.")
    conv = await db.get(Conversation, attachment.conversation_id)
    if not conv or conv.user_id != user.id:
        raise forbidden("دسترسی به این فایل مجاز نیست.")

    ws = cli_runner.workspace_dir(user.id)
    real_root = Path(os.path.realpath(ws))
    candidate = Path(os.path.realpath(ws / attachment.storage_path))
    if candidate != real_root and real_root not in candidate.parents:
        raise not_found("فایل یافت نشد.")
    if not candidate.is_file():
        raise not_found("فایل یافت نشد.")
    return FileResponse(candidate, filename=attachment.filename, media_type=attachment.mime_type)
