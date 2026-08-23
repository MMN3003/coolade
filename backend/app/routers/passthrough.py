"""API-key passthrough — always direct HTTP through LiteLLM (TECH.md section 5.2, amendment 1)."""
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

from app.db import async_session_factory
from app.deps import ApiKeyPrincipal, client_ip, get_api_key_principal, get_db
from app.errors import AppError, bad_request, model_not_allowed, upstream_rate_limited
from app.internal import pop_usage_report
from app.models import Model, ModelPolicy
from app.services import account_limits, ledger
from app.services.litellm_client import UpstreamServiceError, litellm_client
from app.services.quota import check_quota
from app.services.sse import iter_sse_json

router = APIRouter(prefix="/v1", tags=["passthrough"])

# Upstream HTTP status → (code, پیام) shown to the API client. Anything outside
# this map (litellm's own 500s, unexpected codes) becomes a 502 upstream_error.
# NOTE: 429 is handled separately in _upstream_error (model-aware, actionable
# message — product-owner follow-up, 2026-08-22) and intentionally absent here.
_UPSTREAM_ERRORS: dict[int, tuple[str, str]] = {
    401: ("upstream_auth_error", "احراز هویت نزد سرویس بالادستی ناموفق بود؛ تنظیمات اعتبارنامه را بررسی کنید."),
    403: ("upstream_forbidden", "سرویس بالادستی این درخواست را مجاز نمی‌داند."),
    404: ("upstream_not_found", "مدل یا مسیر درخواستی در سرویس بالادستی یافت نشد."),
    529: ("upstream_overloaded", "سرویس بالادستی زیر بار سنگین است؛ کمی بعد دوباره تلاش کنید."),
}


async def _upstream_error(
    db: AsyncSession, exc: UpstreamServiceError, model_key: str | None = None
) -> AppError:
    if exc.status_code == 429:
        # Product-owner decision (2026-08-22): keep the model, no auto-substitution —
        # just make the message actionable (name the model + a lighter suggestion +
        # the account's 5h reset time when we know it, Issue F state).
        reset_hint = await account_limits.get_5h_reset_hint(db)
        return upstream_rate_limited(model=model_key, reset_at=reset_hint)
    if exc.status_code in _UPSTREAM_ERRORS:
        code, message = _UPSTREAM_ERRORS[exc.status_code]
        return AppError(exc.status_code, code, message)
    return AppError(502, "upstream_error", "خطا در ارتباط با سرویس بالادستی رخ داد.")


async def _open_upstream_stream(body: dict[str, Any]) -> AsyncIterator[bytes]:
    """Connect to litellm's SSE stream and fail fast with the upstream status.

    litellm reports errors that happen after its StreamingResponse starts as
    HTTP 200 plus a single `data: {"error": ..., "code": "429"}` event, so peek
    at the first complete event before we commit to our own 200 stream.
    """
    stream = litellm_client.stream_chat("/chat/completions", body)
    head = b""
    while b"\n\n" not in head and len(head) < 16384:
        try:
            head += await anext(stream)
        except StopAsyncIteration:
            break
    for line in head.split(b"\n\n", 1)[0].split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:"):
            continue
        try:
            obj = json.loads(line[len(b"data:") :].strip())
        except json.JSONDecodeError:
            continue
        err = obj.get("error") if isinstance(obj, dict) else None
        if isinstance(err, dict):
            try:
                status_code = int(err.get("code") or 500)
            except (TypeError, ValueError):
                status_code = 500
            raise UpstreamServiceError(status_code, str(err.get("message") or "")[:500])

    async def _chained() -> AsyncIterator[bytes]:
        if head:
            yield head
        async for chunk in stream:
            yield chunk

    return _chained()


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


def _anthropic_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    system = body.get("system")
    if system:
        text = system if isinstance(system, str) else "\n".join(
            b.get("text", "") for b in system if isinstance(b, dict)
        )
        messages.append({"role": "system", "content": text})
    for m in body.get("messages", []):
        content = m.get("content")
        if isinstance(content, list):
            text = "\n".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            text = content
        messages.append({"role": m.get("role", "user"), "content": text})

    openai_body: dict[str, Any] = {
        "model": body["model"],
        "messages": messages,
        "stream": bool(body.get("stream", False)),
    }
    if "max_tokens" in body:
        openai_body["max_tokens"] = body["max_tokens"]
    if "temperature" in body:
        openai_body["temperature"] = body["temperature"]
    # Issue D (asymmetric vs. web chat, TECH.md 5.2): the API-key surface owns its own
    # thinking control — the client's `thinking` field (Anthropic shape, e.g.
    # {"type":"enabled","budget_tokens":N}) is forwarded UNCHANGED. We never inject it
    # on the chat's behalf here, and never strip it either.
    #
    # `allowed_openai_params` is required alongside it: our litellm_config.yaml keeps
    # `drop_params: true` gateway-wide (a real safety net — unrelated unsupported
    # params from arbitrary tools should be dropped, not 400 the whole request), and
    # litellm doesn't know our custom "ecocode-upstream" provider supports `thinking`
    # at all, so without this per-request opt-in it either silently drops the field
    # (drop_params: true) or raises UnsupportedParamsError (drop_params: false) —
    # confirmed against the live litellm proxy while implementing this. This is the
    # officially documented per-request escape hatch, not a global relaxation.
    if "thinking" in body:
        openai_body["thinking"] = body["thinking"]
        openai_body["allowed_openai_params"] = ["thinking"]
    return openai_body


async def _record_ledger(
    *, user_id: int, api_key_id: int | None, model: Model, surface: str, request_id: str, fallback_usage: dict
) -> dict:
    reported = pop_usage_report(request_id)
    if reported:
        usage = {
            "input_tokens": reported["input_tokens"],
            "output_tokens": reported["output_tokens"],
            "cache_read_tokens": reported["cache_read_tokens"],
            "cache_write_tokens": reported["cache_write_tokens"],
        }
    else:
        usage = {
            "input_tokens": fallback_usage.get("prompt_tokens", 0) or 0,
            "output_tokens": fallback_usage.get("completion_tokens", 0) or 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
    async with async_session_factory() as sdb:
        m = await sdb.get(Model, model.id)
        await ledger.record_usage(
            sdb,
            user_id=user_id,
            model=m,
            surface=surface,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
            api_key_id=api_key_id,
            request_id=request_id,
        )
        await sdb.commit()
    return usage


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
    openai_body = _anthropic_to_openai(body)
    openai_body["extra_headers"] = {"x-ecocode-request-id": request_id}
    stream = bool(body.get("stream", False))
    user_id = principal.user.id
    api_key_id = principal.api_key.id
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    if not stream:
        try:
            resp = await litellm_client.call_chat("/chat/completions", openai_body)
        except UpstreamServiceError as exc:
            raise await _upstream_error(db, exc, model.model_key)
        choice = (resp.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        usage = resp.get("usage") or {}
        await _record_ledger(
            user_id=user_id,
            api_key_id=api_key_id,
            model=model,
            surface="api",
            request_id=request_id,
            fallback_usage=usage,
        )
        return JSONResponse(
            {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                },
            }
        )

    try:
        upstream = await _open_upstream_stream(openai_body)
    except UpstreamServiceError as exc:
        raise await _upstream_error(db, exc, model.model_key)

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
                    "model": body["model"],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
        )
        yield sse(
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        )

        fallback_usage: dict = {}
        async for chunk in iter_sse_json(upstream):
            if chunk is None:
                break
            choices = chunk.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": text},
                        },
                    )
            if chunk.get("usage"):
                fallback_usage = chunk["usage"]

        yield sse("content_block_stop", {"type": "content_block_stop", "index": 0})

        usage = await _record_ledger(
            user_id=user_id,
            api_key_id=api_key_id,
            model=model,
            surface="api",
            request_id=request_id,
            fallback_usage=fallback_usage,
        )
        yield sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": usage["output_tokens"]},
            },
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
    body = dict(body)
    body["extra_headers"] = {"x-ecocode-request-id": request_id}
    stream = bool(body.get("stream", False))
    user_id = principal.user.id
    api_key_id = principal.api_key.id

    if not stream:
        try:
            resp = await litellm_client.call_chat("/chat/completions", body)
        except UpstreamServiceError as exc:
            raise await _upstream_error(db, exc, model.model_key)
        await _record_ledger(
            user_id=user_id,
            api_key_id=api_key_id,
            model=model,
            surface="api",
            request_id=request_id,
            fallback_usage=resp.get("usage") or {},
        )
        return JSONResponse(resp)

    try:
        upstream = await _open_upstream_stream(body)
    except UpstreamServiceError as exc:
        raise await _upstream_error(db, exc, model.model_key)

    async def event_stream():
        fallback_usage: dict = {}
        buffer = b""
        async for raw in upstream:
            buffer += raw
            yield raw
            while b"\n\n" in buffer:
                event_bytes, buffer = buffer.split(b"\n\n", 1)
                for line in event_bytes.split(b"\n"):
                    line = line.strip()
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[len(b"data:") :].strip()
                    if payload in (b"", b"[DONE]"):
                        continue
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):
                        fallback_usage = obj["usage"]
        await _record_ledger(
            user_id=user_id,
            api_key_id=api_key_id,
            model=model,
            surface="api",
            request_id=request_id,
            fallback_usage=fallback_usage,
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
