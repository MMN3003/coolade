"""API-key passthrough surface.

اصلاحیهٔ ۵ / amendment 5: this path no longer goes through LiteLLM. Every request
now runs as a stateless single-shot Claude Code CLI turn (cli_runner.run_oneshot_turn),
exactly like the web-chat surface — so both surfaces share the same upstream
identity. That is what removes the opus/sonnet 429: the OAuth subscription token
requires requests to carry the Claude Code identity, which the CLI always sends
and the old raw LiteLLM relay did not.

The wire contract to API clients is unchanged: `/v1/messages` speaks the Anthropic
Messages shape and `/v1/chat/completions` speaks the OpenAI Chat shape (both stream
and non-stream). The client's own multi-turn history is flattened into a single
prompt (the CLI's `-p` takes one prompt); client-supplied tool definitions are not
bridged to the CLI on this surface (documented limitation, TECH.md 5.2/5.5).
"""
from __future__ import annotations

import datetime
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli_runner
from app.db import async_session_factory
from app.deps import ApiKeyPrincipal, client_ip, get_api_key_principal, get_db
from app.errors import AppError, bad_request, model_not_allowed
from app.models import Model, ModelPolicy
from app.services import ledger
from app.services.quota import check_quota

router = APIRouter(prefix="/v1", tags=["passthrough"])


def _api_error_from_event(ev: dict[str, Any]) -> AppError:
    """Map a normalized cli_runner error event → an HTTP AppError with the same
    Persian message the web-chat surface uses (shared via cli_runner's classifier)."""
    code = ev.get("code") or "upstream_error"
    message = ev.get("message") or "خطا در ارتباط با سرویس بالادستی رخ داد."
    if code in ("upstream_rate_limited", "quota_exceeded", "quota_exceeded_5h"):
        return AppError(429, code, message)
    if code == "timeout":
        return AppError(504, "upstream_timeout", message)
    return AppError(502, code, message)


async def _load_and_check_model(db: AsyncSession, user_id: int, model_key: str) -> Model:
    result = await db.execute(select(Model).where(Model.model_key == model_key))
    model = result.scalar_one_or_none()
    if not model or not model.is_enabled:
        raise model_not_allowed(f"مدل «{model_key}» یافت نشد یا غیرفعال است.")
    policy = await db.execute(
        select(ModelPolicy).where(ModelPolicy.user_id == user_id, ModelPolicy.model_id == model.id)
    )
    if policy.scalar_one_or_none() is None:
        raise model_not_allowed("این مدل برای شما مجاز نیست.")
    return model


def _content_to_text(content: Any) -> str:
    """Flatten an OpenAI/Anthropic message `content` (str or block list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                # OpenAI blocks use {"type":"text","text":...}; Anthropic text blocks the same.
                if b.get("type") in (None, "text") and b.get("text"):
                    parts.append(b["text"])
        return "\n".join(parts)
    return "" if content is None else str(content)


def _anthropic_messages_to_prompt(body: dict[str, Any]) -> str:
    parts: list[str] = []
    system = body.get("system")
    if system:
        parts.append(_content_to_text(system))
    for m in body.get("messages", []):
        text = _content_to_text(m.get("content"))
        if not text:
            continue
        role = m.get("role", "user")
        parts.append(text if role == "user" else f"{role.capitalize()}: {text}")
    return "\n\n".join(p for p in parts if p)


def _openai_messages_to_prompt(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for m in body.get("messages", []):
        text = _content_to_text(m.get("content"))
        if not text:
            continue
        role = m.get("role", "user")
        if role == "system":
            parts.append(text)
        elif role == "user":
            parts.append(text)
        else:
            parts.append(f"{role.capitalize()}: {text}")
    return "\n\n".join(p for p in parts if p)


async def _record_api_usage(
    *, user_id: int, api_key_id: int | None, model_id: int, request_id: str, usage: dict[str, Any]
) -> dict[str, int]:
    resolved = {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "cache_read_tokens": int(usage.get("cache_read_tokens", 0) or 0),
        "cache_write_tokens": int(usage.get("cache_write_tokens", 0) or 0),
    }
    async with async_session_factory() as sdb:
        m = await sdb.get(Model, model_id)
        await ledger.record_usage(
            sdb,
            user_id=user_id,
            model=m,
            surface="api",
            input_tokens=resolved["input_tokens"],
            output_tokens=resolved["output_tokens"],
            cache_read_tokens=resolved["cache_read_tokens"],
            cache_write_tokens=resolved["cache_write_tokens"],
            api_key_id=api_key_id,
            request_id=request_id,
        )
        await sdb.commit()
    return resolved


async def _peek_cli_stream(
    gen: AsyncIterator[dict[str, Any]],
) -> tuple[list[dict[str, Any]], AsyncIterator[dict[str, Any]]]:
    """Advance the CLI turn until the first text delta (or a terminal event), so an
    error that arrives before any output surfaces as a real HTTP status instead of an
    empty 200 stream (fail-fast, parity with the old LiteLLM peek). Raises AppError
    if an `error` event arrives before any delta. Returns (buffered_events, gen) where
    the caller replays buffered_events then keeps consuming gen."""
    buffered: list[dict[str, Any]] = []
    async for ev in gen:
        e = ev.get("event")
        if e == "delta":
            buffered.append(ev)
            return buffered, gen
        if e == "error":
            raise _api_error_from_event(ev)
        if e == "done":
            buffered.append(ev)
            return buffered, gen
        # start / tool events: not forwarded to API clients, keep advancing.
    return buffered, gen


@router.get("/models")
async def list_models(
    principal: ApiKeyPrincipal = Depends(get_api_key_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Model.model_key)
        .join(ModelPolicy, ModelPolicy.model_id == Model.id)
        .where(ModelPolicy.user_id == principal.user.id, Model.is_enabled.is_(True))
    )
    return {
        "object": "list",
        "data": [{"id": key, "object": "model", "owned_by": "ecocode"} for (key,) in result.all()],
    }


@router.post("/messages", response_model=None)
async def anthropic_messages(
    request: Request,
    principal: ApiKeyPrincipal = Depends(get_api_key_principal),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    if "model" not in body:
        raise bad_request("model الزامی است.")
    model = await _load_and_check_model(db, principal.user.id, body["model"])
    await check_quota(db, user_id=principal.user.id, ip_address=ip)

    principal.api_key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()

    request_id = uuid.uuid4().hex
    prompt = _anthropic_messages_to_prompt(body)
    stream = bool(body.get("stream", False))
    user_id = principal.user.id
    api_key_id = principal.api_key.id
    model_id = model.id
    model_key = body["model"]
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    gen = cli_runner.run_oneshot_turn(
        user_id=user_id, upstream_model=model.upstream_model, prompt=prompt
    )

    if not stream:
        text_parts: list[str] = []
        usage: dict[str, Any] = {}
        async for ev in gen:
            e = ev.get("event")
            if e == "delta":
                text_parts.append(ev.get("text", ""))
            elif e == "error":
                raise _api_error_from_event(ev)
            elif e == "done":
                usage = ev.get("usage") or {}
        recorded = await _record_api_usage(
            user_id=user_id, api_key_id=api_key_id, model_id=model_id,
            request_id=request_id, usage=usage,
        )
        return JSONResponse(
            {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "model": model_key,
                "content": [{"type": "text", "text": "".join(text_parts)}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": recorded["input_tokens"],
                    "output_tokens": recorded["output_tokens"],
                },
            }
        )

    buffered, gen = await _peek_cli_stream(gen)

    async def event_stream():
        def sse(event: str, data: dict) -> bytes:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()

        yield sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": model_key,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
        )
        yield sse(
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        )

        usage: dict[str, Any] = {}
        for ev in buffered:
            if ev.get("event") == "delta" and ev.get("text"):
                yield sse(
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 0,
                     "delta": {"type": "text_delta", "text": ev["text"]}},
                )
            elif ev.get("event") == "done":
                usage = ev.get("usage") or {}
        async for ev in gen:
            e = ev.get("event")
            if e == "delta" and ev.get("text"):
                yield sse(
                    "content_block_delta",
                    {"type": "content_block_delta", "index": 0,
                     "delta": {"type": "text_delta", "text": ev["text"]}},
                )
            elif e == "error":
                # Error mid-stream (after headers): surface as an Anthropic `error` event.
                yield sse("error", {"type": "error",
                                    "error": {"type": ev.get("code"), "message": ev.get("message")}})
                return
            elif e == "done":
                usage = ev.get("usage") or {}

        yield sse("content_block_stop", {"type": "content_block_stop", "index": 0})
        recorded = await _record_api_usage(
            user_id=user_id, api_key_id=api_key_id, model_id=model_id,
            request_id=request_id, usage=usage,
        )
        yield sse(
            "message_delta",
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": recorded["output_tokens"]}},
        )
        yield sse("message_stop", {"type": "message_stop"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    request: Request,
    principal: ApiKeyPrincipal = Depends(get_api_key_principal),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    if "model" not in body:
        raise bad_request("model الزامی است.")
    model = await _load_and_check_model(db, principal.user.id, body["model"])
    await check_quota(db, user_id=principal.user.id, ip_address=ip)

    principal.api_key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()

    request_id = uuid.uuid4().hex
    prompt = _openai_messages_to_prompt(body)
    stream = bool(body.get("stream", False))
    user_id = principal.user.id
    api_key_id = principal.api_key.id
    model_id = model.id
    model_key = body["model"]
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    gen = cli_runner.run_oneshot_turn(
        user_id=user_id, upstream_model=model.upstream_model, prompt=prompt
    )

    if not stream:
        text_parts: list[str] = []
        usage: dict[str, Any] = {}
        async for ev in gen:
            e = ev.get("event")
            if e == "delta":
                text_parts.append(ev.get("text", ""))
            elif e == "error":
                raise _api_error_from_event(ev)
            elif e == "done":
                usage = ev.get("usage") or {}
        recorded = await _record_api_usage(
            user_id=user_id, api_key_id=api_key_id, model_id=model_id,
            request_id=request_id, usage=usage,
        )
        return JSONResponse(
            {
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": model_key,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "".join(text_parts)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": recorded["input_tokens"],
                    "completion_tokens": recorded["output_tokens"],
                    "total_tokens": recorded["input_tokens"] + recorded["output_tokens"],
                },
            }
        )

    buffered, gen = await _peek_cli_stream(gen)

    async def event_stream():
        def chunk(delta: dict, finish_reason: str | None = None) -> bytes:
            payload = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_key,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            }
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

        yield chunk({"role": "assistant", "content": ""})

        usage: dict[str, Any] = {}
        for ev in buffered:
            if ev.get("event") == "delta" and ev.get("text"):
                yield chunk({"content": ev["text"]})
            elif ev.get("event") == "done":
                usage = ev.get("usage") or {}
        async for ev in gen:
            e = ev.get("event")
            if e == "delta" and ev.get("text"):
                yield chunk({"content": ev["text"]})
            elif e == "error":
                yield f"data: {json.dumps({'error': {'code': ev.get('code'), 'message': ev.get('message')}}, ensure_ascii=False)}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return
            elif e == "done":
                usage = ev.get("usage") or {}

        yield chunk({}, finish_reason="stop")
        yield b"data: [DONE]\n\n"
        await _record_api_usage(
            user_id=user_id, api_key_id=api_key_id, model_id=model_id,
            request_id=request_id, usage=usage,
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
