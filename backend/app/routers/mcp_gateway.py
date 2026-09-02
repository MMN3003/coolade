"""Amendment-1 (docs/SERVICES-V2.md ب-۳) — the MCP gateway: one streamable-HTTP
MCP endpoint per organizational service, `POST /mcp/svc/{slug}`.

This is the ONLY road from a chat/workspace agent to an org system. Contract
(proved by SPK-SV1 with the real claude client — stateless JSON responses,
no SSE stream, no session id):

  auth     Bearer <workspace gateway key | personal api key> → user
  401      unknown/missing key            404  unknown or disabled service
  403      no grant (re-checked on EVERY call → revocation is immediate)
  tools/*  list filtered by grant level; calls audited (digest-only params)

Credentials are decrypted in app.services.org_services only; nothing secret
ever appears in a response body here.
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from app.db import async_session_factory
from app.models import ApiKey, GrantLevel, Service, ServiceAudit, ServiceGrant, Workspace
from app.security import hash_api_key
from app.services import org_services

router = APIRouter(prefix="/mcp/svc", tags=["mcp-gateway"])

PROTOCOL_FALLBACK = "2025-03-26"


def _rpc_result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _rpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_text(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": is_error,
    }


async def _resolve_caller(db, key: str) -> tuple[int, int | None] | None:
    """key → (user_id, workspace_id|None). Three key kinds: in-memory turn key
    (in-process chat CLI, DS6), workspace gateway key, personal API key."""
    if not key:
        return None
    turn_user = org_services.resolve_turn_key(key)
    if turn_user is not None:
        return turn_user, None
    kh = hash_api_key(key)
    ws = (
        await db.execute(select(Workspace).where(Workspace.gateway_key_hash == kh))
    ).scalar_one_or_none()
    if ws:
        return ws.user_id, ws.id
    ak = (
        await db.execute(select(ApiKey).where(ApiKey.key_hash == kh, ApiKey.is_active.is_(True)))
    ).scalar_one_or_none()
    if ak:
        return ak.user_id, None
    return None


async def _audit(
    db,
    *,
    service_id: int,
    user_id: int,
    workspace_id: int | None,
    tool: str,
    level: GrantLevel,
    digest: str | None,
    ok: bool,
    error_code: str | None,
    duration_ms: int | None,
    result_rows: int | None,
) -> None:
    db.add(
        ServiceAudit(
            service_id=service_id,
            user_id=user_id,
            workspace_id=workspace_id,
            tool=tool,
            level_used=level,
            params_digest=digest,
            ok=ok,
            error_code=error_code,
            duration_ms=duration_ms,
            result_rows=result_rows,
        )
    )
    await db.commit()


async def _handle_tools_call(
    db,
    *,
    service: Service,
    grant: ServiceGrant,
    user_id: int,
    workspace_id: int | None,
    msg: dict[str, Any],
) -> dict[str, Any]:
    params = msg.get("params") or {}
    tool = str(params.get("name", ""))
    arguments: dict[str, Any] = params.get("arguments") or {}
    digest = org_services.params_digest(arguments)
    allowed = {t["name"] for t in org_services.tools_for(service, grant.level)}
    if tool not in allowed:
        await _audit(
            db, service_id=service.id, user_id=user_id, workspace_id=workspace_id,
            tool=tool, level=grant.level, digest=digest, ok=False,
            error_code="forbidden", duration_ms=None, result_rows=None,
        )
        return _rpc_result(
            msg["id"], _tool_text({"error": "این ابزار برای سطح دسترسی شما مجاز نیست."}, is_error=True)
        )
    if not org_services.rate_limiter.allow(user_id):
        await _audit(
            db, service_id=service.id, user_id=user_id, workspace_id=workspace_id,
            tool=tool, level=grant.level, digest=digest, ok=False,
            error_code="rate_limited", duration_ms=None, result_rows=None,
        )
        return _rpc_result(
            msg["id"],
            _tool_text({"error": "سقف تعداد فراخوانی در دقیقه پر شده؛ کمی بعد دوباره تلاش کن."}, is_error=True),
        )

    started = time.monotonic()
    try:
        payload = await org_services.call_tool(service, tool, arguments)
        duration = int((time.monotonic() - started) * 1000)
        await _audit(
            db, service_id=service.id, user_id=user_id, workspace_id=workspace_id,
            tool=tool, level=grant.level, digest=digest, ok=True, error_code=None,
            duration_ms=duration, result_rows=int(payload.get("row_count") or 0),
        )
        return _rpc_result(msg["id"], _tool_text(payload))
    except org_services.SqlGuardError as exc:
        await _audit(
            db, service_id=service.id, user_id=user_id, workspace_id=workspace_id,
            tool=tool, level=grant.level, digest=digest, ok=False,
            error_code="guard_rejected", duration_ms=None, result_rows=None,
        )
        return _rpc_result(msg["id"], _tool_text({"error": str(exc)}, is_error=True))
    except Exception as exc:
        # Connector/DB failure: honest tool error, no stack/secret leakage (ب-۸).
        duration = int((time.monotonic() - started) * 1000)
        await _audit(
            db, service_id=service.id, user_id=user_id, workspace_id=workspace_id,
            tool=tool, level=grant.level, digest=digest, ok=False,
            error_code="upstream_error", duration_ms=duration, result_rows=None,
        )
        return _rpc_result(
            msg["id"],
            _tool_text(
                {"error": f"سرویس «{service.name}» در دسترس نیست ({type(exc).__name__})؛ بعداً تلاش کن."},
                is_error=True,
            ),
        )


async def _handle_rpc(
    db,
    *,
    service: Service,
    grant: ServiceGrant,
    user_id: int,
    workspace_id: int | None,
    msg: dict[str, Any],
) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    if msg_id is None:  # notifications (initialized, cancelled, …)
        return None
    if method == "initialize":
        proto = (msg.get("params") or {}).get("protocolVersion", PROTOCOL_FALLBACK)
        return _rpc_result(
            msg_id,
            {
                "protocolVersion": proto,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": f"ecocode-svc-{service.slug}", "version": "1.0"},
            },
        )
    if method == "ping":
        return _rpc_result(msg_id, {})
    if method == "tools/list":
        return _rpc_result(msg_id, {"tools": org_services.tools_for(service, grant.level)})
    if method == "tools/call":
        return await _handle_tools_call(
            db, service=service, grant=grant, user_id=user_id, workspace_id=workspace_id, msg=msg
        )
    return _rpc_error(msg_id, -32601, f"method not supported: {method}")


@router.post("/{slug}")
async def mcp_service(slug: str, request: Request):
    key = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip() or (
        request.headers.get("x-api-key") or ""
    ).strip()

    async with async_session_factory() as db:
        caller = await _resolve_caller(db, key)
        if caller is None:
            return JSONResponse({"error": "invalid or missing key"}, status_code=401)
        user_id, workspace_id = caller

        if slug == "_admin":
            # Reserved management endpoint for the service-builder assistant
            # (SV2, 2026-09-02): only admin users, tools from service_admin_tools.
            return await _handle_admin(db, request, user_id)

        service = (
            await db.execute(select(Service).where(Service.slug == slug))
        ).scalar_one_or_none()
        if service is None or not service.enabled:
            return JSONResponse({"error": "unknown service"}, status_code=404)

        # Grant re-read on EVERY request — revocation takes effect immediately,
        # independent of whatever config was synced into the workspace (ب-۳).
        grant = (
            await db.execute(
                select(ServiceGrant).where(
                    ServiceGrant.service_id == service.id, ServiceGrant.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            await _audit(
                db, service_id=service.id, user_id=user_id, workspace_id=workspace_id,
                tool="-", level=GrantLevel.read, digest=None, ok=False,
                error_code="forbidden", duration_ms=None, result_rows=None,
            )
            return JSONResponse({"error": "no grant for this service"}, status_code=403)

        try:
            body = json.loads(await request.body())
        except json.JSONDecodeError:
            return JSONResponse({"error": "bad json"}, status_code=400)

        msgs = body if isinstance(body, list) else [body]
        responses = []
        for m in msgs:
            if isinstance(m, dict):
                r = await _handle_rpc(
                    db, service=service, grant=grant, user_id=user_id,
                    workspace_id=workspace_id, msg=m,
                )
                if r is not None:
                    responses.append(r)

        if not responses:
            return Response(status_code=202)  # notification(s) only
        return JSONResponse(responses if isinstance(body, list) else responses[0])


async def _handle_admin(db, request: Request, user_id: int):
    from app.models import User, UserRole
    from app.services import service_admin_tools

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.role != UserRole.admin or not user.is_active:
        return JSONResponse({"error": "admin only"}, status_code=403)

    try:
        body = json.loads(await request.body())
    except json.JSONDecodeError:
        return JSONResponse({"error": "bad json"}, status_code=400)

    async def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
        method = msg.get("method")
        msg_id = msg.get("id")
        if msg_id is None:
            return None
        if method == "initialize":
            proto = (msg.get("params") or {}).get("protocolVersion", PROTOCOL_FALLBACK)
            return _rpc_result(
                msg_id,
                {
                    "protocolVersion": proto,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "ecocode-service-builder", "version": "1.0"},
                },
            )
        if method == "ping":
            return _rpc_result(msg_id, {})
        if method == "tools/list":
            return _rpc_result(msg_id, {"tools": service_admin_tools.ADMIN_TOOLS})
        if method == "tools/call":
            params = msg.get("params") or {}
            tool = str(params.get("name", ""))
            args = params.get("arguments") or {}
            if not org_services.rate_limiter.allow(user_id):
                return _rpc_result(
                    msg_id, _tool_text({"error": "سقف فراخوانی در دقیقه؛ کمی بعد."}, is_error=True)
                )
            try:
                result = await service_admin_tools.call_admin_tool(db, user, tool, args)
                return _rpc_result(msg_id, _tool_text(result))
            except org_services.SqlGuardError as exc:
                return _rpc_result(msg_id, _tool_text({"error": str(exc)}, is_error=True))
            except Exception as exc:
                import logging

                logging.getLogger("ecocode.mcp_gateway").exception(
                    "admin tool %s failed for user %s", tool, user_id
                )
                await db.rollback()
                return _rpc_result(
                    msg_id,
                    _tool_text({"error": f"خطای داخلی ({type(exc).__name__})."}, is_error=True),
                )
        return _rpc_error(msg_id, -32601, f"method not supported: {method}")

    msgs = body if isinstance(body, list) else [body]
    responses = [r for m in msgs if isinstance(m, dict) for r in [await handle(m)] if r is not None]
    if not responses:
        return Response(status_code=202)
    return JSONResponse(responses if isinstance(body, list) else responses[0])


@router.delete("/{slug}")
async def mcp_service_end(slug: str):  # stateless server: session end is a no-op
    return Response(status_code=200)
