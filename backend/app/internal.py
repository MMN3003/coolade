"""Internal-only endpoints used by the litellm custom upstream handler (passthrough path only).

Not part of the public API contract (docs/TECH.md section 8) — never exposed
through nginx, only reachable on the internal docker network by the litellm
container. Protected with a shared-secret bearer token (the litellm master
key, which the litellm container already holds).

Two purposes:
  1. Resolve the *effective* upstream mode + credentials (env overrides the
     runtime `settings` table — TECH.md section 4) so the litellm custom
     handler stays a dumb HTTP relay with no DB/crypto/credential-file
     access of its own — it only ever talks to `$UPSTREAM_BASE_URL` and to
     this endpoint.
  2. Receive the *authoritative* usage numbers straight from the upstream
     HTTP response (including cache_read/cache_write tokens) via a
     side-channel keyed by request_id, because the abstraction litellm
     exposes for custom-provider streaming chunks does not carry those
     fields. This guarantees usage_ledger fidelity for the passthrough path
     regardless of what litellm's own OpenAI-shaped streaming usage block
     contains (TECH.md R4 / "usage_ledger منبع حقیقت سهمیه است").

Note: the web-chat surface never goes through litellm at all (TECH.md
section 5, amendment 1) — its usage comes straight from the CLI runner's
`result` event and is recorded directly by app/cli_runner.py.
"""
from __future__ import annotations

import os
import time
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db import async_session_factory
from app.models import Setting
from app.security import decrypt_secret
from app.upstream import credentials as cli_credentials

router = APIRouter(prefix="/internal", tags=["internal"])
settings = get_settings()

_MAX_REPORTS = 5000
_usage_reports: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def _check_secret(authorization: str | None) -> None:
    expected = f"Bearer {settings.litellm_master_key}"
    if not authorization or authorization != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


class UsageReport(BaseModel):
    request_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    upstream_request_id: str | None = None


@router.post("/usage-report")
async def usage_report(
    body: UsageReport, authorization: str | None = Header(default=None)
) -> dict[str, bool]:
    _check_secret(authorization)
    _usage_reports[body.request_id] = {
        "input_tokens": body.input_tokens,
        "output_tokens": body.output_tokens,
        "cache_read_tokens": body.cache_read_tokens,
        "cache_write_tokens": body.cache_write_tokens,
        "upstream_request_id": body.upstream_request_id,
        "_ts": time.time(),
    }
    while len(_usage_reports) > _MAX_REPORTS:
        _usage_reports.popitem(last=False)
    return {"ok": True}


def pop_usage_report(request_id: str) -> dict[str, Any] | None:
    return _usage_reports.pop(request_id, None)


class UpstreamLimitsReport(BaseModel):
    """اصلاحیهٔ ۳ / Issue F (TECH.md 4.5, 6.1): the litellm handler fire-and-forgets
    the raw `anthropic-ratelimit-*` response headers here after every passthrough
    call; parsing into window/limit/remaining/reset stays in backend (one place),
    not in the handler (which remains a dumb relay)."""

    raw_headers: dict[str, str]
    upstream_request_id: str | None = None
    source: str = "passthrough"


@router.post("/upstream-limits")
async def upstream_limits(
    body: UpstreamLimitsReport, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    _check_secret(authorization)
    from app.services import account_limits

    async with async_session_factory() as db:
        parsed = await account_limits.record_raw_headers(
            db, body.raw_headers, source=body.source, upstream_request_id=body.upstream_request_id
        )
    return {"ok": True, "windows_parsed": parsed}


class UpstreamConfigOut(BaseModel):
    mode: str
    base_url: str
    api_key: str | None = None
    auth_header: str | None = None  # "bearer" | "x-api-key" | None
    oauth_beta: bool = False
    # model_key (litellm model group) → upstream model id, e.g.
    # "claude-sonnet" → "claude-sonnet-5". The handler must apply this before
    # relaying, otherwise internal keys leak upstream and 404 (model not found).
    model_map: dict[str, str] = {}


async def _model_map(db) -> dict[str, str]:
    from sqlalchemy import select

    from app.models import Model

    rows = (await db.execute(select(Model.model_key, Model.upstream_model))).all()
    return {key: upstream for key, upstream in rows}


@router.get("/upstream-config", response_model=UpstreamConfigOut)
async def upstream_config(authorization: str | None = Header(default=None)) -> UpstreamConfigOut:
    _check_secret(authorization)

    env_mode = os.environ.get("UPSTREAM_MODE")
    async with async_session_factory() as db:
        if env_mode:
            mode = env_mode
        else:
            row = await db.get(Setting, "upstream.mode")
            mode = row.value if row and row.value else "mock"

        model_map = await _model_map(db)

        if mode == "mock":
            return UpstreamConfigOut(
                mode="mock",
                base_url=os.environ.get("MOCK_UPSTREAM_BASE", "http://mock-upstream:8080"),
                model_map=model_map,
            )

        if mode == "apikey":
            api_key: str | None = None
            row = await db.get(Setting, "upstream.apikey")
            if row and row.value:
                api_key = decrypt_secret(row.value)
            return UpstreamConfigOut(
                mode="apikey",
                base_url=settings.upstream_base_url,
                api_key=api_key,
                auth_header="x-api-key",
                model_map=model_map,
            )

        # cli_creds
        creds = cli_credentials.read_credentials()
        token = creds["access_token"] if creds else None
        return UpstreamConfigOut(
            mode="cli_creds",
            base_url=settings.upstream_base_url,
            api_key=token,
            auth_header="bearer",
            oauth_beta=True,
            model_map=model_map,
        )
