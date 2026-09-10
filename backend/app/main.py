"""EcoCode Gateway backend — FastAPI app entrypoint."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import async_session_factory
from app.errors import AppError, app_error_handler, unhandled_error_handler, validation_error_handler
from app.internal import router as internal_router
from app.routers import (
    admin_knowledge,
    admin_models,
    admin_plans,
    admin_services,
    admin_teams,
    admin_upstream,
    admin_usage,
    admin_users,
    auth,
    conversations,
    health,
    keys,
    knowledge,
    mcp_gateway,
    relay,
    teams,
    usage,
    workspace,
    workspaces_v2,
)
from app.scheduler import start_scheduler
from app.seed import run_seed
from app.services import account_limits
from app.services.turns import mark_interrupted_streaming_as_failed
from app.upstream import credentials as cli_credentials

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ecocode")

settings = get_settings()

_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session_factory() as db:
        await run_seed(db)
        recovered = await mark_interrupted_streaming_as_failed(db)
        if recovered:
            logger.warning("startup recovery: marked %d interrupted turn(s) as failed/aborted_restart", recovered)

    await cli_credentials.startup_rehydrate()
    _background_tasks.append(asyncio.create_task(cli_credentials.periodic_task(60)))

    # اصلاحیهٔ ۳ / Issue F: optional periodic probe to refresh upstream_account_limits
    # when passthrough traffic has gone quiet — off by default (TECH.md 4.5).
    if settings.upstream_limit_probe_enabled:
        _background_tasks.append(
            asyncio.create_task(account_limits.periodic_probe_task(settings.upstream_limit_probe_interval))
        )

    scheduler = start_scheduler()

    yield

    scheduler.shutdown(wait=False)
    for task in _background_tasks:
        task.cancel()


app = FastAPI(title="EcoCode Gateway", version="1.4.0", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def require_ajax_header_for_cookie_mutations(request: Request, call_next):
    """TECH.md 7.1: mutating /api/* (cookie-auth) requests must carry X-Requested-With."""
    if (
        request.url.path.startswith("/api/")
        and not request.url.path.startswith("/api/health")
        and request.method in ("POST", "PUT", "PATCH", "DELETE")
        and "x-requested-with" not in {k.lower() for k in request.headers.keys()}
    ):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "missing_header",
                    "message": "هدر X-Requested-With الزامی است.",
                }
            },
        )
    return await call_next(request)


app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(workspace.router)
app.include_router(workspaces_v2.router)
app.include_router(teams.router)
app.include_router(knowledge.router)
app.include_router(keys.router)
app.include_router(usage.router)
# v2 — the old CLI-wrapping web service (/v1 passthrough for Cline) is removed
# (PRD-V2 L1/decision-2). Only the raw relay (/relay/v1) remains for agents.
app.include_router(relay.router)
app.include_router(mcp_gateway.router)
app.include_router(admin_users.router)
app.include_router(admin_services.router)
app.include_router(admin_knowledge.router)
app.include_router(admin_teams.router)
app.include_router(admin_models.router)
app.include_router(admin_plans.router)
app.include_router(admin_usage.router)
app.include_router(admin_upstream.router)
app.include_router(internal_router)
