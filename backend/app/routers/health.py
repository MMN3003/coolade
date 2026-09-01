from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_db
from app.models import Setting
from app.schemas import HealthOut
from app.upstream import credentials as cli_credentials

router = APIRouter(tags=["health"])
settings = get_settings()


async def _effective_mode(db: AsyncSession) -> str:
    env_mode = os.environ.get("UPSTREAM_MODE")
    if env_mode:
        return env_mode
    row = await db.get(Setting, "upstream.mode")
    return row.value if row and row.value else "mock"


@router.get("/api/health", response_model=HealthOut)
async def health(db: AsyncSession = Depends(get_db)) -> HealthOut:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    # اصلاحیهٔ ۵ / amendment 5: LiteLLM is no longer part of the stack (both surfaces
    # run through the Claude Code CLI). The `litellm` health field is kept as a legacy
    # constant so the schema/admin UI stay valid; it no longer probes any service.
    litellm_ok = True

    mode = await _effective_mode(db) if db_ok else settings.upstream_mode
    if mode == "mock":
        upstream_connected = True
    elif mode == "cli_creds":
        upstream_connected = cli_credentials.get_status()["connected"]
    else:  # apikey
        row = await db.get(Setting, "upstream.apikey") if db_ok else None
        upstream_connected = bool(row and row.value)

    cli_available = settings.mock_cli or shutil.which("claude") is not None

    return HealthOut(
        status="ok" if (db_ok and litellm_ok) else "degraded",
        db=db_ok,
        litellm=litellm_ok,
        upstream_mode=mode,
        upstream_connected=upstream_connected,
        cli_available=cli_available,
    )
