"""mode `cli_creds`: reuse Claude Code's own host credential file (TECH.md section 4.1).

The host's `~/.claude/.credentials.json` is bind-mounted read-only into this
container at `settings.claude_creds_dir` (default `/host_claude`). Claude Code
CLI needs to *write* to its config directory though, so a read-only mount of
$HOME/.claude itself is not enough — instead we one-way sync the credentials
file from the read-only host mount into the container's own HOME every 60s
(and once at startup). The host stays the source of truth; if `claude login`
refreshes the token on the host, the container picks it up within 60s.

This module is backend-only. The litellm custom handler (mounted in the
litellm container, a different image with no access to this package) never
imports it directly — it asks backend's `/internal/upstream-config` endpoint
for a resolved, plaintext access token instead. That keeps the litellm
container a dumb HTTP relay with no credential-file or DB access of its own.
"""
from __future__ import annotations

import datetime
import json
import logging
import shutil
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger("ecocode.upstream.credentials")
settings = get_settings()

_last_synced_at: datetime.datetime | None = None
_last_sync_error: str | None = None


def _host_creds_path() -> Path:
    return Path(settings.claude_creds_dir) / ".credentials.json"


def _container_creds_path() -> Path:
    return Path(settings.cli_home) / ".claude" / ".credentials.json"


def sync_once() -> bool:
    """Copy the host credential file into the container HOME. Returns True on success."""
    global _last_synced_at, _last_sync_error
    src = _host_creds_path()
    dst = _container_creds_path()
    if not src.exists():
        _last_sync_error = "فایل اعتبارنامه روی هاست یافت نشد."
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = dst.with_suffix(".tmp")
        shutil.copyfile(src, tmp)
        tmp.chmod(0o600)
        tmp.replace(dst)
        _last_synced_at = datetime.datetime.now(datetime.timezone.utc)
        _last_sync_error = None
        return True
    except OSError as exc:  # pragma: no cover - defensive
        _last_sync_error = str(exc)
        logger.warning("credential sync failed: %s", exc)
        return False


def _parse_raw(raw: dict) -> dict | None:
    # Claude Code's on-disk shape: {"claudeAiOauth": {"accessToken": ..., "refreshToken": ...,
    # "expiresAt": <ms epoch>, "scopes": [...]}}. Be defensive about shape drift (TECH.md R3).
    node = raw.get("claudeAiOauth") if isinstance(raw, dict) else None
    if not isinstance(node, dict):
        node = raw if isinstance(raw, dict) else None
    if not node:
        return None

    access_token = node.get("accessToken") or node.get("access_token")
    if not access_token:
        return None

    refresh_token = node.get("refreshToken") or node.get("refresh_token")

    expires_at: datetime.datetime | None = None
    raw_expires = node.get("expiresAt", node.get("expires_at"))
    if isinstance(raw_expires, (int, float)):
        # heuristics: milliseconds vs seconds epoch
        ts = raw_expires / 1000 if raw_expires > 10**12 else raw_expires
        expires_at = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    elif isinstance(raw_expires, str):
        try:
            expires_at = datetime.datetime.fromisoformat(raw_expires.replace("Z", "+00:00"))
        except ValueError:
            expires_at = None

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    }


def read_credentials() -> dict | None:
    path = _container_creds_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return _parse_raw(raw)


def get_status() -> dict:
    creds = read_credentials()
    now = datetime.datetime.now(datetime.timezone.utc)
    connected = creds is not None and (
        creds.get("expires_at") is None or creds["expires_at"] > now
    )
    expiring_soon = bool(
        creds
        and creds.get("expires_at")
        and creds["expires_at"] <= now + datetime.timedelta(minutes=30)
    )
    return {
        "connected": connected,
        "expires_at": creds.get("expires_at") if creds else None,
        "expiring_soon": expiring_soon,
        "creds_source": str(_host_creds_path()),
        "last_synced": _last_synced_at,
        "last_sync_error": _last_sync_error,
    }


async def periodic_sync_task(interval_seconds: int = 60) -> None:
    """Run forever: sync at startup, then every `interval_seconds`."""
    import asyncio

    while True:
        await asyncio.to_thread(sync_once)
        await asyncio.sleep(interval_seconds)
