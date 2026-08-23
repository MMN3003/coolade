"""اصلاحیهٔ ۳ / Issue F (TECH.md 4.5, 6.1): the upstream account's OWN rate-limit
state, captured honestly from `anthropic-ratelimit-*` response headers on the
passthrough path — never a fabricated number.

Two responsibilities:
  1. Parse + upsert into `upstream_account_limits` (called by the internal
     `/internal/upstream-limits` endpoint the litellm handler fire-and-forgets to).
  2. Build the admin-facing view (`GET /api/admin/upstream/account-limits`), with an
     honest `available=false` + credentials-derived tier/subscription fallback when
     no headers have ever been seen.

Also owns the optional periodic probe (`UPSTREAM_LIMIT_PROBE_ENABLED`, default off):
a tiny `max_tokens=1` request purely to read headers when web-chat/passthrough
traffic has gone quiet — never charged to any user's ledger (there is no user).
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Model, UpstreamAccountLimit

logger = logging.getLogger("ecocode.upstream.account_limits")
settings = get_settings()

# Defensive: capture the whole `anthropic-ratelimit-*` family without assuming exact
# names (TECH.md 4.5) — a 3rd-party Claude-compatible service may name windows
# differently. Confirmed live against the real upstream (verification, 2026-08-22):
# it uses the newer "unified" scheme — `anthropic-ratelimit-unified-5h-status`,
# `...-5h-utilization`, `...-5h-reset` — NOT the classic `-limit`/`-remaining`
# counters. Both shapes are handled below; unmatched metric suffixes are still
# preserved verbatim in raw_headers for defense.
_RATELIMIT_RE = re.compile(
    r"^anthropic-ratelimit-(.+)-(limit|remaining|reset|status|utilization)$", re.IGNORECASE
)

STALE_THRESHOLD = datetime.timedelta(minutes=15)


def parse_ratelimit_headers(raw_headers: dict[str, str]) -> dict[str, dict[str, str]]:
    """Group `anthropic-ratelimit-<window>-<metric>` headers by window key.
    Headers that don't match this shape (unexpected variants) are still preserved
    verbatim in `raw_headers` on whatever window rows get upserted, for defense."""
    windows: dict[str, dict[str, str]] = {}
    for name, value in raw_headers.items():
        m = _RATELIMIT_RE.match(name.strip().lower())
        if not m:
            continue
        window_key, metric = m.group(1), m.group(2).lower()
        windows.setdefault(window_key, {})[metric] = value
    return windows


def _to_decimal(v: str | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, ValueError):
        return None


def _parse_reset(v: str | None) -> datetime.datetime | None:
    if not v:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(v), tz=datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass
    try:
        return datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _infer_unit(window_key: str) -> str | None:
    wk = window_key.lower()
    if "token" in wk:
        return "tokens"
    if "request" in wk:
        return "requests"
    return None


async def record_raw_headers(
    db: AsyncSession,
    raw_headers: dict[str, str],
    *,
    source: str,
    upstream_request_id: str | None,
) -> int:
    """Parse + upsert (one row per window_key). Returns the number of windows parsed
    (0 if the upstream response carried no anthropic-ratelimit-* headers at all —
    the table then simply stays empty/unchanged, TECH.md's honest-degrade path)."""
    windows = parse_ratelimit_headers(raw_headers)
    if not windows:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    for window_key, metrics in windows.items():
        row = await db.get(UpstreamAccountLimit, window_key)
        if row is None:
            row = UpstreamAccountLimit(window_key=window_key, source=source)
            db.add(row)
        limit_value = _to_decimal(metrics.get("limit"))
        remaining_value = _to_decimal(metrics.get("remaining"))
        reset_at = _parse_reset(metrics.get("reset"))
        unit = _infer_unit(window_key)

        if limit_value is None and remaining_value is None:
            # Unified scheme: no absolute numbers, just a 0..1 "utilization" (how
            # much of the window is used). Surface it honestly as a fraction
            # (limit=1.00, remaining=1-utilization) rather than leaving the window
            # blank — labelled unit="fraction" so it's never confused with a real
            # token/request count.
            utilization = _to_decimal(metrics.get("utilization"))
            if utilization is not None:
                limit_value = Decimal("1")
                remaining_value = max(Decimal("0"), Decimal("1") - utilization)
                unit = "fraction"

        if limit_value is not None:
            row.limit_value = limit_value
        if remaining_value is not None:
            row.remaining_value = remaining_value
        if reset_at is not None:
            row.reset_at = reset_at
        row.unit = unit
        row.raw_headers = raw_headers
        row.source = source
        row.last_updated = now
        row.upstream_request_id = upstream_request_id
    await db.commit()
    return len(windows)


async def get_5h_reset_hint(db: AsyncSession) -> str | None:
    """Best-effort "HH:MM" for the account's 5h rate-limit window reset, if we've
    ever captured an `anthropic-ratelimit-*-5h-reset` header (Issue F state above).
    Used to append an "آزاد شدن حدود HH:MM" hint onto the improved 429 message —
    product-owner follow-up folded into اصلاحیهٔ ۴ work (2026-08-22); shared by both
    routers/passthrough.py and cli_runner.py's _classify_result_error."""
    rows = (await db.execute(select(UpstreamAccountLimit))).scalars().all()
    for r in rows:
        if "5h" in r.window_key.lower() and r.reset_at:
            return r.reset_at.strftime("%H:%M")
    return None


async def get_account_limits_view(db: AsyncSession) -> dict[str, Any]:
    rows = (await db.execute(select(UpstreamAccountLimit))).scalars().all()
    now = datetime.datetime.now(datetime.timezone.utc)
    windows = [
        {
            "key": r.window_key,
            "limit": r.limit_value,
            "remaining": r.remaining_value,
            "reset": r.reset_at,
            "unit": r.unit,
            "last_updated": r.last_updated,
            "stale": (now - r.last_updated) > STALE_THRESHOLD,
        }
        for r in rows
    ]
    available = len(windows) > 0
    tier: str | None = None
    subscription: str | None = None
    if not available:
        # Honest fallback (TECH.md 4.5): no header ever seen → only whatever the
        # credentials file itself discloses, never an invented number.
        from app.upstream import credentials as cli_credentials

        info = cli_credentials.read_account_info()
        if info:
            tier = info.get("rate_limit_tier")
            subscription = info.get("subscription_type")
    return {"available": available, "windows": windows, "tier": tier, "subscription": subscription}


# ============================== optional periodic probe (default OFF) ==============================


async def _resolve_probe_target(db: AsyncSession) -> dict[str, Any] | None:
    """Mirrors /internal/upstream-config's resolution logic in-process (no HTTP hop
    needed — this runs inside backend already) — mock mode is skipped, there's
    nothing meaningful to probe."""
    import os

    from app.models import Setting
    from app.security import decrypt_secret
    from app.upstream import credentials as cli_credentials

    env_mode = os.environ.get("UPSTREAM_MODE")
    if env_mode:
        mode = env_mode
    else:
        row = await db.get(Setting, "upstream.mode")
        mode = row.value if row and row.value else "mock"

    if mode == "mock":
        return None

    if mode == "apikey":
        row = await db.get(Setting, "upstream.apikey")
        api_key = decrypt_secret(row.value) if row and row.value else None
        if not api_key:
            return None
        return {"base_url": settings.upstream_base_url, "api_key": api_key, "auth_header": "x-api-key", "oauth_beta": False}

    # cli_creds
    creds = cli_credentials.read_credentials()
    if not creds or not creds.get("access_token"):
        return None
    return {
        "base_url": settings.upstream_base_url,
        "api_key": creds["access_token"],
        "auth_header": "bearer",
        "oauth_beta": True,
    }


async def probe_once(db: AsyncSession) -> bool:
    """Tiny max_tokens=1 request purely to read rate-limit headers — no ledger entry
    (there's no user to charge; this is account-level telemetry, TECH.md 4.5).
    Returns True if headers were captured and parsed."""
    cfg = await _resolve_probe_target(db)
    if cfg is None:
        return False

    model_row = (
        await db.execute(select(Model).where(Model.is_enabled.is_(True)).order_by(Model.input_weight.asc()).limit(1))
    ).scalar_one_or_none()
    upstream_model = model_row.upstream_model if model_row else "claude-3-5-haiku-20241022"

    headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
    if cfg["auth_header"] == "bearer":
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
        if cfg.get("oauth_beta"):
            headers["anthropic-beta"] = "oauth-2025-04-20"
    else:
        headers["x-api-key"] = cfg["api_key"]

    body = {
        "model": upstream_model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "."}],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{cfg['base_url']}/v1/messages", json=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("account-limit probe request failed: %s", exc)
        return False

    raw = {k: v for k, v in resp.headers.items() if k.lower().startswith("anthropic-ratelimit")}
    if not raw:
        return False
    parsed = await record_raw_headers(db, raw, source="probe", upstream_request_id=resp.headers.get("request-id"))
    return parsed > 0


async def periodic_probe_task(interval_seconds: int) -> None:
    """Runs forever while UPSTREAM_LIMIT_PROBE_ENABLED=true (default false, TECH.md 4.5)."""
    from app.db import async_session_factory

    while True:
        try:
            async with async_session_factory() as db:
                await probe_once(db)
        except Exception:  # pragma: no cover - defensive, must never kill the loop
            logger.exception("account-limit periodic probe iteration failed")
        await asyncio.sleep(interval_seconds)
