"""v2 — raw HTTP relay for in-workspace agents (TECH-V2 §0/§5, D2.4).

The Claude Code extension / headless `claude` inside a workspace container calls this
with its per-workspace gateway key as bearer. We authenticate the key against the
workspace row, enforce quota, inject the REAL upstream OAuth token (which never enters
the container), stream the response through unchanged, and record usage from the SSE
stream. This is the production form of spike/relay_spike.py.
"""
from __future__ import annotations

import json
import re
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.config import get_settings
from app.db import async_session_factory
from app.models import ApiKey, Model, ModelPolicy, Workspace
from app.security import hash_api_key
from app.services import ledger
from app.services.quota import check_quota
from app.errors import AppError

settings = get_settings()
logger = logging.getLogger("coolade.relay")
router = APIRouter(prefix="/relay/v1", tags=["relay"])

OAUTH_BETA = "oauth-2025-04-20"
_HOP = {"host", "authorization", "x-api-key", "content-length", "connection", "accept-encoding"}


def _upstream_base() -> str:
    return (settings.workspace_upstream_base_url or settings.upstream_base_url).rstrip("/")


def _resolve_upstream_token() -> str | None:
    try:
        from app.upstream import credentials

        creds = credentials.read_credentials()
        if creds and creds.get("access_token"):
            return str(creds["access_token"])
    except Exception:
        logger.exception("relay: could not resolve upstream token")
    return None


def _extract_usage(sse_text: str) -> dict:
    out: dict = {}
    for m in re.finditer(r'"usage"\s*:\s*\{', sse_text):
        depth, i = 0, m.end() - 1
        for j in range(i, len(sse_text)):
            if sse_text[j] == "{":
                depth += 1
            elif sse_text[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        for k, v in json.loads(sse_text[i : j + 1]).items():
                            if isinstance(v, int) and v:
                                out[k] = max(out.get(k, 0), v)
                    except Exception:
                        pass
                    break
    return out


def _extract_key(request: Request) -> str:
    return (request.headers.get("authorization") or "").removeprefix("Bearer ").strip() or (
        request.headers.get("x-api-key") or ""
    ).strip()


async def _resolve_user_id(db, key: str) -> int | None:
    if not key:
        return None
    kh = hash_api_key(key)
    ws = (
        await db.execute(select(Workspace).where(Workspace.gateway_key_hash == kh))
    ).scalar_one_or_none()
    if ws:
        return ws.user_id
    ak = (
        await db.execute(select(ApiKey).where(ApiKey.key_hash == kh, ApiKey.is_active.is_(True)))
    ).scalar_one_or_none()
    return ak.user_id if ak else None


def _model_obj(m: Model) -> dict:
    return {
        "type": "model",
        # canonical Anthropic id (what the client sends back in `model`); the POST
        # handler resolves it via Model.upstream_model.
        "id": m.upstream_model or m.model_key,
        "display_name": m.display_name,
        "created_at": m.created_at.isoformat() if getattr(m, "created_at", None) else "2025-01-01T00:00:00Z",
    }


@router.get("/models")
async def relay_list_models(request: Request):
    """Anthropic-compatible model list so GUI clients (Claude Desktop, etc.) can
    populate their model picker instead of 404-ing on connect. Filtered to the
    caller's allowed models when the key identifies a user that has an explicit
    policy; otherwise every enabled model (ACL is still enforced at send time)."""
    key = _extract_key(request)
    async with async_session_factory() as db:
        user_id = await _resolve_user_id(db, key)
        allowed: set[int] | None = None
        if user_id is not None:
            pols = (
                await db.execute(
                    select(ModelPolicy.model_id).where(ModelPolicy.user_id == user_id)
                )
            ).scalars().all()
            if pols:
                allowed = set(pols)
        rows = (
            await db.execute(
                select(Model).where(Model.is_enabled.is_(True)).order_by(Model.sort_order, Model.id)
            )
        ).scalars().all()
    if allowed is not None:
        rows = [m for m in rows if m.id in allowed]
    data = [_model_obj(m) for m in rows]
    return JSONResponse(
        {
            "data": data,
            "has_more": False,
            "first_id": data[0]["id"] if data else None,
            "last_id": data[-1]["id"] if data else None,
        }
    )


@router.get("/models/{model_id}")
async def relay_get_model(model_id: str, request: Request):
    async with async_session_factory() as db:
        m = (
            await db.execute(select(Model).where(Model.upstream_model == model_id))
        ).scalar_one_or_none()
        if m is None:
            m = (
                await db.execute(select(Model).where(Model.model_key == model_id))
            ).scalar_one_or_none()
    if m is None or not m.is_enabled:
        return JSONResponse(
            {"type": "error", "error": {"type": "not_found_error", "message": f"model: {model_id}"}},
            status_code=404,
        )
    return JSONResponse(_model_obj(m))


@router.post("/messages")
async def relay_messages(request: Request):
    # Claude Code sends `Authorization: Bearer`; Cline / Anthropic-SDK tools send
    # `x-api-key`. Accept either so any Anthropic-compatible client works.
    key = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip() or (
        request.headers.get("x-api-key") or ""
    ).strip()
    if not key:
        return JSONResponse({"error": "missing key"}, status_code=401)

    async with async_session_factory() as db:
        kh = hash_api_key(key)
        # (a) workspace gateway key (in-container agent) OR (b) personal API key
        # (Claude Code on the developer's own machine — the "CLI path", no container).
        wsrow = (
            await db.execute(select(Workspace).where(Workspace.gateway_key_hash == kh))
        ).scalar_one_or_none()
        if wsrow:
            user_id = wsrow.user_id
            surface = "ide"       # in-container workspace agent
            api_key_id = None     # workspaces authenticate via gateway_key_hash, not an ApiKey row
        else:
            ak = (
                await db.execute(
                    select(ApiKey).where(ApiKey.key_hash == kh, ApiKey.is_active.is_(True))
                )
            ).scalar_one_or_none()
            if not ak:
                return JSONResponse({"error": "invalid key"}, status_code=401)
            user_id = ak.user_id
            surface = "api"       # developer's own machine (CLI path)
            api_key_id = ak.id    # attribute usage to this personal key (shown under "my keys")

        body = await request.body()
        try:
            payload = json.loads(body)
            model_key = payload.get("model", "")
        except Exception:
            payload, model_key = {}, ""

        # ACL + quota (same governance as every other surface)
        model = None
        if model_key:
            mres = await db.execute(select(Model).where(Model.upstream_model == model_key))
            model = mres.scalar_one_or_none()
            if model is None:
                mres = await db.execute(select(Model).where(Model.model_key == model_key))
                model = mres.scalar_one_or_none()
        if model is not None:
            pol = await db.execute(
                select(ModelPolicy).where(
                    ModelPolicy.user_id == user_id, ModelPolicy.model_id == model.id
                )
            )
            if pol.scalar_one_or_none() is None:
                return JSONResponse({"error": "model not allowed"}, status_code=403)
        try:
            await check_quota(db, user_id=user_id)
        except AppError as e:
            return JSONResponse({"error": e.message}, status_code=e.status_code)

    token = _resolve_upstream_token()
    if not token:
        return JSONResponse({"error": "upstream token unavailable"}, status_code=502)

    up_headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    up_headers["Authorization"] = f"Bearer {token}"
    beta = up_headers.get("anthropic-beta", "")
    if OAUTH_BETA not in beta:
        up_headers["anthropic-beta"] = f"{beta},{OAUTH_BETA}" if beta else OAUTH_BETA
    up_headers.setdefault("anthropic-version", "2023-06-01")

    url = f"{_upstream_base()}/v1/messages"
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
    # open the upstream response first so we can mirror its real status + content-type
    # (SSE vs JSON); aiter_bytes() below yields DECOMPRESSED bytes (httpx adds its own
    # accept-encoding), so we stream plain text the client can parse.
    req = client.build_request("POST", url, content=body, headers=up_headers)
    resp = await client.send(req, stream=True)
    media = resp.headers.get("content-type", "text/event-stream")

    async def stream():
        captured: list[bytes] = []
        try:
            async for chunk in resp.aiter_bytes():
                captured.append(chunk)
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()
            # record usage from the stream (best-effort; never breaks the response)
            if model is not None and resp.status_code == 200:
                usage = _extract_usage(b"".join(captured).decode("utf-8", "replace"))
                if usage:
                    try:
                        async with async_session_factory() as sdb:
                            m = await sdb.get(Model, model.id)
                            await ledger.record_usage(
                                sdb, user_id=user_id, model=m, surface=surface,
                                api_key_id=api_key_id,
                                input_tokens=int(usage.get("input_tokens", 0) or 0),
                                output_tokens=int(usage.get("output_tokens", 0) or 0),
                                cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                                cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
                            )
                            await sdb.commit()
                    except Exception:
                        logger.exception("relay: usage recording failed")

    return StreamingResponse(stream(), status_code=resp.status_code, media_type=media)
