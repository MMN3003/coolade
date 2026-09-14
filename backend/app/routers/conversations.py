from __future__ import annotations

import asyncio
import datetime
import json
import logging
import mimetypes
import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli_runner, turn_registry
from app.config import get_settings
from app.db import async_session_factory
from app.deps import client_ip, get_current_user, get_db
from app.errors import AppError, bad_request, forbidden, model_not_allowed, not_found
from app.models import Attachment, Conversation, Message, MessageStatus, Model, ModelPolicy, ThinkingLevel, User
from app.schemas import (
    AttachmentOut,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
    SendMessageRequest,
    TurnAcceptedOut,
)
from app.services import attachment_text, ledger, thinking as thinking_service
from app.services.quota import check_quota
from app.turn_registry import TurnState

router = APIRouter(prefix="/api", tags=["conversations"])
settings = get_settings()
logger = logging.getLogger("ecocode.conversations")


DEFAULT_TITLE = "گفتگوی جدید"


def _derive_title(content: str) -> str:
    """First non-empty line of the first message, trimmed to a short title.
    Slash commands and code still yield a sensible label; empty → default."""
    for line in (content or "").splitlines():
        line = line.strip()
        if line:
            return line[:48].strip()
    return DEFAULT_TITLE


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


# SSE keepalive cadence for GET …/stream (see stream_conversation). 15s is
# comfortably under the ~30-60s idle cut-off of mobile carriers / CDNs.
_SSE_PING_SECONDS = 15
# An SSE comment line: every compliant parser ignores it, and the browser
# client treats it as a liveness signal (frontend/src/api/sse.ts).
_SSE_PING = b": ping\n\n"


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
        thinking_level=getattr(conv.thinking_level, "value", conv.thinking_level),
        generating=turn_registry.registry.is_generating(conv.id),
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

    conv = Conversation(user_id=user.id, title=body.title or DEFAULT_TITLE, model_id=model.id)
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
    from sqlalchemy import func as sa_func

    from app.models import UsageLedger

    credits_used = (
        await db.execute(
            select(sa_func.coalesce(sa_func.sum(UsageLedger.credits), 0)).where(
                UsageLedger.conversation_id == conv.id
            )
        )
    ).scalar_one()
    attach_rows = (
        await db.execute(
            select(Attachment)
            .where(Attachment.conversation_id == conv.id, Attachment.message_id.is_not(None))
            .order_by(Attachment.id)
        )
    ).scalars().all()
    by_message: dict[int, list[AttachmentOut]] = {}
    for a in attach_rows:
        by_message.setdefault(a.message_id, []).append(AttachmentOut.model_validate(a))
    messages_out = []
    for m in msgs.scalars().all():
        mo = MessageOut.model_validate(m)
        mo.attachments = by_message.get(m.id, [])
        messages_out.append(mo)
    out = _conv_to_out(conv, model_key)
    return ConversationDetailOut(
        **out.model_dump(),
        messages=messages_out,
        credits_used=credits_used,
        cost_nudge_threshold=settings.chat_cost_nudge_credits,
    )


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
    if body.thinking_level is not None:
        conv.thinking_level = ThinkingLevel(body.thinking_level)
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


async def _run_turn_background(
    *,
    conversation_id: int,
    assistant_message_id: int,
    user_id: int,
    prompt: str,
    upstream_model: str,
    model_id: int,
    resume_session_id: str | None,
    thinking_level: ThinkingLevel,
    state: TurnState,
) -> None:
    """Issue A: runs a full CLI turn to completion in the background, independent of
    any client connection. Always persists the final result (or a failure) — even if
    every SSE reader disconnects mid-stream, this coroutine keeps running to FINALIZE.
    """
    assistant_text_parts: list[str] = []
    content_blocks: list[dict] = []
    files_changed: list[str] = []
    session_id_captured: str | None = None
    error_code: str | None = None
    error_reason: str | None = None
    success = False
    try:
        async for ev in cli_runner.run_conversation_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            prompt=prompt,
            upstream_model=upstream_model,
            resume_session_id=resume_session_id,
            thinking_level=thinking_level,
        ):
            # User pressed stop: break out — the generator's finally terminates the
            # CLI subprocess; the finally below persists partial text + stopped state.
            if state.cancel_requested:
                error_code = "stopped"
                error_reason = "تولید پاسخ با درخواست شما متوقف شد."
                await state.append({"event": "error", "data": {"message": error_reason, "code": "stopped"}})
                break
            etype = ev["event"]
            if etype == "start":
                session_id_captured = ev.get("session_id")
                await state.append({"event": "start", "data": {"conversation_id": conversation_id}})
            elif etype == "delta":
                assistant_text_parts.append(ev["text"])
                await state.append({"event": "delta", "data": {"text": ev["text"]}})
            elif etype == "tool":
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "name": ev["name"],
                        "summary": ev["summary"],
                        "file_path": ev.get("file_path"),
                    }
                )
                await state.append({"event": "tool", "data": {"name": ev["name"], "summary": ev["summary"]}})
            elif etype == "done":
                usage = ev["usage"]
                files_changed = ev.get("files_changed") or []
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
                        conversation_id=conversation_id,
                    )
                    final_text = ev.get("result_text") or "".join(assistant_text_parts)
                    msg = await sdb.get(Message, assistant_message_id)
                    if msg is not None:
                        msg.content = final_text
                        msg.content_blocks = {"tool_uses": content_blocks} if content_blocks else None
                        msg.status = MessageStatus.complete
                        msg.error_code = None
                        msg.error_reason = None
                    conv_row = await sdb.get(Conversation, conversation_id)
                    if conv_row:
                        sid = ev.get("session_id") or session_id_captured
                        # Persist also when it CHANGED: the runner may have rebuilt the
                        # session after a stale --resume (CLI session state lost) — the
                        # new id must replace the dead one or every later turn would
                        # re-trigger the fallback.
                        if sid and sid != conv_row.cli_session_id:
                            conv_row.cli_session_id = sid
                        conv_row.updated_at = datetime.datetime.now(datetime.timezone.utc)
                    credits_used = str(entry.credits)
                    await sdb.commit()
                success = True
                await state.append(
                    {
                        "event": "done",
                        "data": {
                            "credits_used": credits_used,
                            "files_changed": list(dict.fromkeys(files_changed)),
                            "thinking_level": ev.get("thinking_level") or thinking_level.value,
                        },
                    }
                )
            elif etype == "error":
                error_code = ev.get("code") or "cli_error"
                error_reason = ev.get("message") or "اجرای دستیار با خطا مواجه شد."
                await state.append({"event": "error", "data": {"message": error_reason}})
    except Exception:
        logger.exception("turn crashed unexpectedly: conversation_id=%s", conversation_id)
        error_code = error_code or "cli_error"
        error_reason = error_reason or "خطای غیرمنتظره‌ای در اجرای دستیار رخ داد."
        try:
            await state.append({"event": "error", "data": {"message": error_reason}})
        except Exception:  # pragma: no cover - defensive, must not crash the finally block
            pass
    finally:
        if not success:
            async with async_session_factory() as sdb:
                msg = await sdb.get(Message, assistant_message_id)
                if msg is not None and msg.status == MessageStatus.streaming:
                    msg.status = MessageStatus.failed
                    msg.error_code = error_code or "cli_error"
                    msg.error_reason = error_reason or "اجرای دستیار با خطا مواجه شد."
                    # A user-stopped turn keeps whatever text already streamed —
                    # the tokens were paid for; don't throw them away.
                    if not msg.content and assistant_text_parts:
                        msg.content = "".join(assistant_text_parts)
                    await sdb.commit()
        await state.mark_done()
        turn_registry.registry.finish(conversation_id, state)
        cli_runner.release_conversation(conversation_id)


@router.post("/conversations/{conversation_id}/stop")
async def stop_generation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """User-requested stop of the in-progress turn (saves tokens). Idempotent:
    stopping an idle conversation is a no-op, not an error — the turn may have
    just finished on its own."""
    await _get_owned_conversation(db, user, conversation_id)
    state = turn_registry.registry.get(conversation_id)
    if state is None or state.done:
        return {"ok": True, "stopped": False}
    state.cancel_requested = True
    return {"ok": True, "stopped": True}


@router.post("/conversations/{conversation_id}/messages", response_model=TurnAcceptedOut, status_code=202)
async def send_message(
    conversation_id: int,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> TurnAcceptedOut:
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

    # Pending uploads: the explicit ids from the client, or — for a stale/older
    # client that never sends ids — every still-unlinked upload of this conversation.
    pending_q = select(Attachment).where(
        Attachment.conversation_id == conv.id, Attachment.message_id.is_(None)
    )
    if body.attachment_ids is not None:
        # Explicit list ([] means «none») — the current client always sends it.
        pending_q = pending_q.where(Attachment.id.in_(body.attachment_ids or [-1]))
    else:
        # Legacy client: only uploads from the last two hours, so orphaned files
        # from older sessions never silently ride along.
        recent_cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        pending_q = pending_q.where(Attachment.created_at >= recent_cutoff)
    pending_attachments = list((await db.execute(pending_q.order_by(Attachment.id))).scalars().all())
    if not (body.content or "").strip() and not pending_attachments:
        cli_runner.release_conversation(conv.id)
        raise bad_request("متن پیام یا حداقل یک پیوست لازم است.")

    requested_level = ThinkingLevel(body.thinking_level) if body.thinking_level else None
    effective_level = thinking_service.effective_level(requested_level, conv.thinking_level)

    user_msg = Message(conversation_id=conv.id, role="user", content=body.content, status=MessageStatus.complete)
    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content="",
        status=MessageStatus.streaming,
        thinking_level=effective_level,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    if requested_level is not None and effective_level != conv.thinking_level:
        # Sticky default (TECH.md 5.7): the level actually used becomes the new
        # conversation default, not merely what the user asked for (which may have
        # been capped).
        conv.thinking_level = effective_level
    # Auto-title from the first user message so new chats don't all stay «گفتگوی جدید».
    # Only overrides the untouched default, never a user-set title.
    if (conv.title or "").strip() in ("", DEFAULT_TITLE):
        conv.title = _derive_title(body.content or (pending_attachments[0].filename if pending_attachments else ""))
    conv.updated_at = datetime.datetime.now(datetime.timezone.utc)
    try:
        await db.flush()
        for a in pending_attachments:
            a.message_id = user_msg.id
        await db.commit()
    except Exception:
        cli_runner.release_conversation(conv.id)
        raise
    await db.refresh(assistant_msg)
    prompt = _prompt_with_attachments(body.content, pending_attachments)

    state = turn_registry.registry.start(conv.id, assistant_msg.id)
    asyncio.create_task(
        _run_turn_background(
            conversation_id=conv.id,
            assistant_message_id=assistant_msg.id,
            user_id=user.id,
            prompt=prompt,
            upstream_model=model.upstream_model,
            model_id=model.id,
            resume_session_id=conv.cli_session_id,
            thinking_level=effective_level,
            state=state,
        )
    )
    return TurnAcceptedOut(assistant_message_id=assistant_msg.id, generating=True, thinking_level=effective_level.value)


@router.get("/conversations/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Issue A reattach protocol (TECH.md 5.1/5.3): if a turn is active, replay every
    buffered event from index 0 then keep following live until the terminal event; if
    no turn is active, emit a single `idle` event and close. Idempotent — any number of
    clients, any number of times, from any tab."""
    await _get_owned_conversation(db, user, conversation_id)
    state = turn_registry.registry.get(conversation_id)

    async def gen() -> AsyncIterator[bytes]:
        if state is None:
            yield _sse("idle", {})
            return
        idx = 0
        while True:
            async with state.condition:
                # Keepalive: while the CLI is thinking / running a tool no event
                # arrives for a long time. Mobile carrier NAT, CDNs and nginx all
                # drop an idle connection well before that, so wake up every
                # _SSE_PING_SECONDS and emit an SSE comment (ignored by parsers,
                # but keeps bytes flowing).
                ping = False
                while idx >= len(state.events) and not state.done:
                    try:
                        await asyncio.wait_for(state.condition.wait(), timeout=_SSE_PING_SECONDS)
                    except asyncio.TimeoutError:
                        ping = True
                        break
                batch = state.events[idx:]
                idx = len(state.events)
                finished = state.done and idx >= len(state.events)
            if ping and not batch:
                yield _SSE_PING
                continue
            for ev in batch:
                yield _sse(ev["event"], ev["data"])
            if finished:
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/retry",
    response_model=TurnAcceptedOut,
    status_code=202,
)
async def retry_message(
    conversation_id: int,
    message_id: int,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> TurnAcceptedOut:
    """Issue C (TECH.md 5.1): retries the failed turn IN PLACE — same assistant row,
    same id, reset to streaming — rather than creating a new message row."""
    conv = await _get_owned_conversation(db, user, conversation_id)

    # Ordered/filtered by id (monotonic BIGSERIAL), not created_at: the user+assistant
    # pair from POST messages is inserted in the same transaction and share the exact
    # same server-side now() value, so created_at alone can't disambiguate their order.
    last_msg_result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()
    target = await db.get(Message, message_id)
    if (
        target is None
        or target.conversation_id != conv.id
        or target.role != "assistant"
        or target.status != MessageStatus.failed
        or last_msg is None
        or last_msg.id != target.id
    ):
        raise AppError(409, "not_retryable", "این پیام قابل تلاش مجدد نیست.")

    prior_user_msg_result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conv.id,
            Message.role == "user",
            Message.id < target.id,
        )
        .order_by(Message.id.desc())
        .limit(1)
    )
    prior_user_msg = prior_user_msg_result.scalar_one_or_none()
    if prior_user_msg is None:
        raise AppError(409, "not_retryable", "پیام کاربر مرتبط با این نوبت یافت نشد.")

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

    # Concurrency gate (also serializes a duplicate/concurrent retry -> 409 chat_busy,
    # TECH.md's "idempotency" guarantee for this endpoint).
    if not cli_runner.try_acquire_conversation(conv.id):
        raise AppError(409, "chat_busy", "پاسخ قبلی در این گفتگو هنوز در حال پردازش است.")

    effective_level = target.thinking_level or conv.thinking_level

    # Supersede-in-place: reset the SAME row rather than delete/recreate it.
    target.status = MessageStatus.streaming
    target.content = ""
    target.content_blocks = None
    target.error_code = None
    target.error_reason = None
    conv.updated_at = datetime.datetime.now(datetime.timezone.utc)
    try:
        await db.commit()
    except Exception:
        cli_runner.release_conversation(conv.id)
        raise

    retry_prompt = _prompt_with_attachments(
        prior_user_msg.content, await _attachments_for_message(db, prior_user_msg.id)
    )
    state = turn_registry.registry.start(conv.id, target.id)
    asyncio.create_task(
        _run_turn_background(
            conversation_id=conv.id,
            assistant_message_id=target.id,
            user_id=user.id,
            prompt=retry_prompt,
            upstream_model=model.upstream_model,
            model_id=model.id,
            resume_session_id=conv.cli_session_id,
            thinking_level=effective_level,
            state=state,
        )
    )
    return TurnAcceptedOut(assistant_message_id=target.id, generating=True, thinking_level=effective_level.value)


# Unicode-aware: Persian/Arabic file names survive (\w matches any letter/digit);
# path separators, control chars and shell-hostile punctuation collapse to «_».
_SAFE_FILENAME_RE = re.compile(r"[^\w.\- ()]+", re.UNICODE)


def _sanitize_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")) or "file"
    cleaned = _SAFE_FILENAME_RE.sub("_", base).strip(" ._") or "file"
    return cleaned[:200]


def _prompt_with_attachments(content: str, attachments: list[Attachment]) -> str:
    """The CLI runs with cwd = the user's workspace, so every upload is reachable at
    its relative storage_path. Without this note the model never learns a file was
    attached at all (the send body is content-only) — that was the «attach works but
    nothing happens» bug users hit."""
    if not attachments:
        return content
    lines = [
        "",
        "",
        "[پیوست‌های این پیام — فایل‌ها در پوشهٔ کاری هستند؛ با ابزار Read بخوان و در پاسخ لحاظ کن]",
    ]
    for a in attachments:
        line = f"- {a.storage_path}  (نام اصلی: {a.filename}، نوع: {a.mime_type}، حجم: {a.size_bytes} بایت)"
        sidecar = attachment_text.sidecar_path(a.storage_path)
        if sidecar:
            line += f"  — متن استخراج‌شده: {sidecar}"
        lines.append(line)
    body = (content or "").rstrip() or "فایل(های) پیوست‌شده را بررسی کن و خلاصه/تحلیل بده."
    return body + "\n".join(lines)


async def _attachments_for_message(db: AsyncSession, message_id: int) -> list[Attachment]:
    res = await db.execute(
        select(Attachment).where(Attachment.message_id == message_id).order_by(Attachment.id)
    )
    return list(res.scalars().all())


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

    # Every file type is accepted (product request 2026-09-14: users were blocked on
    # xlsx/docx/zip because the browser-reported MIME missed the old whitelist).
    # Prefer the extension-derived type: browsers often send a generic
    # application/octet-stream, which is useless for the model's hint.
    mime_type = (
        mimetypes.guess_type(file.filename or "")[0]
        or file.content_type
        or "application/octet-stream"
    )[:150]

    safe_name = _sanitize_filename(file.filename or "file")
    stored_name = f"{uuid.uuid4().hex[:12]}_{safe_name}"
    dest = uploads_dir / stored_name
    dest.write_bytes(content)
    # Office/binary formats the CLI cannot Read directly get a best-effort .txt
    # sidecar next to them (xlsx/docx/csv …); failures are logged, never fatal.
    attachment_text.write_sidecar(dest)

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


@router.delete("/attachments/{attachment_id}")
async def delete_pending_attachment(
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a chip the user discarded BEFORE sending. Once linked to a message the
    file is part of the history and stays."""
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise not_found("پیوست یافت نشد.")
    conv = await db.get(Conversation, attachment.conversation_id)
    if not conv or conv.user_id != user.id:
        raise forbidden()
    if attachment.message_id is not None:
        raise bad_request("این پیوست قبلاً ارسال شده و قابل حذف نیست.")
    ws = cli_runner.workspace_dir(user.id)
    candidate = Path(os.path.realpath(ws / attachment.storage_path))
    if str(candidate).startswith(str(ws.resolve()) + os.sep):
        for path in (candidate, attachment_text.sidecar_for(candidate)):
            try:
                if path is not None:
                    path.unlink(missing_ok=True)
            except OSError:
                logger.warning("attachment unlink failed: %s", path, exc_info=True)
    await db.delete(attachment)
    await db.commit()
    return {"ok": True}


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
