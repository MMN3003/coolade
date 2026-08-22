"""mode `cli_creds`: TokenManager — backend owns the upstream token lifecycle (TECH.md 4.1, Issue B).

Production lesson (TECH.md changelog): the v1.1 design (one-way 60s host->container
sync, host file as source of truth) died twice — the access token expires in ~8h and
the refresh token on the host gets rotated/invalidated by other actors (e.g. the CLI
itself, or a human re-running `claude login`), so the gateway just died until a human
intervened. From this revision, **after the initial seed, backend owns the token**:

Three credential locations, three different roles:
  1. `/host_claude/.credentials.json` (read-only bind mount) — SEED ONLY. Only
     consulted for its content hash; imported into (2)+(3) only when that hash
     *changes* from the last-seeded hash (`settings.upstream.cli.host_seed_hash`).
     A manual `claude login` on the host re-seeds within ~60s; a stale host file
     never clobbers backend-managed tokens.
  2. `$HOME/.claude/.credentials.json` inside the container (the `claude_state`
     volume) — the container's own Claude Code CLI reads this directly and may
     itself refresh it mid-turn; TokenManager writes rotated tokens back here in
     Claude Code's own on-disk shape so the CLI keeps working unmodified.
  3. `settings.upstream.cli.*` (Fernet-encrypted) — survives the volume being lost;
     rehydrates (2) on startup if needed.

This module is backend-only. The litellm custom handler (different image, no DB/
crypto/credential-file access) never imports it — it asks `/internal/upstream-config`
for a resolved plaintext token instead.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("ecocode.upstream.credentials")
settings = get_settings()

# ---- legacy/simple status fields kept for the host-seed timestamp shown in the UI ----
_last_synced_at: datetime.datetime | None = None
_last_sync_error: str | None = None

# ---- TokenManager runtime state (single-process, in-memory) ----
_refresh_lock = asyncio.Lock()
_auto_refresh_state: str = "active"  # "active" | "degraded" | "failed"
_last_refresh: dict[str, Any] | None = None  # {"at": iso, "ok": bool, "error": str|None}

_REFRESH_MARGIN = datetime.timedelta(minutes=10)


def _host_creds_path() -> Path:
    return Path(settings.claude_creds_dir) / ".credentials.json"


def _container_creds_path() -> Path:
    return Path(settings.cli_home) / ".claude" / ".credentials.json"


def _assume_expiry() -> datetime.datetime:
    """Fallback when a source doesn't report an expiry: assume it's imminent so a
    refresh gets attempted soon rather than trusting an unknown-age token forever."""
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)


# ============================== on-disk (container) file ==============================


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


_TIER_KEYS = {"ratelimittier", "rate_limit_tier", "ratelimit_tier"}
_SUBSCRIPTION_KEYS = {"subscriptiontype", "subscription_type"}


def _find_account_field(node: Any, wanted_keys: set[str], depth: int = 0) -> str | None:
    """اصلاحیهٔ ۳ / Issue F honest fallback (TECH.md 4.5): Claude Code's credentials
    file shape isn't part of any contract we control, so this searches a couple of
    levels deep for a field that looks like a tier/subscription marker instead of
    assuming one exact path. Returns None (never a fabricated placeholder) if
    nothing matches — the caller shows an explicit "upstream doesn't disclose this"
    state rather than inventing a number."""
    if depth > 2 or not isinstance(node, dict):
        return None
    for key, value in node.items():
        if key.lower().replace("-", "_") in wanted_keys and isinstance(value, str) and value:
            return value
    for value in node.values():
        if isinstance(value, dict):
            found = _find_account_field(value, wanted_keys, depth + 1)
            if found:
                return found
    return None


def read_account_info() -> dict[str, str | None] | None:
    """Best-effort, honest extraction of rateLimitTier/subscriptionType from the
    credentials file the CLI already trusts — used ONLY as the Issue F fallback
    display when no anthropic-ratelimit-* header has ever been captured. Never
    fabricates a value: missing fields come back as None."""
    path = _container_creds_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return {
        "rate_limit_tier": _find_account_field(raw, _TIER_KEYS),
        "subscription_type": _find_account_field(raw, _SUBSCRIPTION_KEYS),
    }


def read_credentials() -> dict | None:
    """Read the container's own (claude_state-volume-backed) credentials file — the
    one the CLI subprocess actually uses."""
    path = _container_creds_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return _parse_raw(raw)


def _write_container_creds_file(
    access_token: str, refresh_token: str | None, expires_at: datetime.datetime
) -> None:
    """Write in Claude Code's own on-disk shape so the CLI reads it unchanged."""
    path = _container_creds_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            existing = {}
    node = existing.get("claudeAiOauth")
    if not isinstance(node, dict):
        node = {}
    node["accessToken"] = access_token
    if refresh_token:
        node["refreshToken"] = refresh_token
    node["expiresAt"] = int(expires_at.timestamp() * 1000)
    existing["claudeAiOauth"] = node
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing))
    tmp.chmod(0o600)
    tmp.replace(path)


# ============================== settings (encrypted) backup ==============================


async def _get_setting(db, key: str):
    from app.models import Setting

    return await db.get(Setting, key)


async def _set_setting(db, key: str, value: str | None, *, is_encrypted: bool) -> None:
    from app.models import Setting

    row = await db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value, is_encrypted=is_encrypted))
    else:
        row.value = value
        row.is_encrypted = is_encrypted


async def _persist_to_settings(
    db, access_token: str, refresh_token: str | None, expires_at: datetime.datetime
) -> None:
    from app.security import encrypt_secret

    await _set_setting(db, "upstream.cli.access_token", encrypt_secret(access_token), is_encrypted=True)
    if refresh_token:
        await _set_setting(db, "upstream.cli.refresh_token", encrypt_secret(refresh_token), is_encrypted=True)
    await _set_setting(db, "upstream.cli.expires_at", expires_at.isoformat(), is_encrypted=False)


async def read_settings_credentials(db) -> dict | None:
    from app.security import decrypt_secret

    access_row = await _get_setting(db, "upstream.cli.access_token")
    if not access_row or not access_row.value:
        return None
    access_token = decrypt_secret(access_row.value)
    if not access_token:
        return None
    refresh_row = await _get_setting(db, "upstream.cli.refresh_token")
    refresh_token = decrypt_secret(refresh_row.value) if refresh_row and refresh_row.value else None
    expires_row = await _get_setting(db, "upstream.cli.expires_at")
    expires_at: datetime.datetime | None = None
    if expires_row and expires_row.value:
        try:
            expires_at = datetime.datetime.fromisoformat(expires_row.value)
        except ValueError:
            expires_at = None
    return {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}


async def _load_last_refresh(db) -> None:
    global _last_refresh
    row = await _get_setting(db, "upstream.cli.last_refresh")
    if row and row.value:
        try:
            _last_refresh = json.loads(row.value)
        except json.JSONDecodeError:
            _last_refresh = None


async def _save_last_refresh(db, *, ok: bool, error: str | None) -> None:
    global _last_refresh
    _last_refresh = {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ok": ok,
        "error": error,
    }
    await _set_setting(db, "upstream.cli.last_refresh", json.dumps(_last_refresh), is_encrypted=False)


# ============================== startup rehydrate ==============================


async def startup_rehydrate() -> None:
    """Reconcile the container file and the settings backup — whichever is missing
    gets reconstructed from the other; if both exist, the fresher (by expires_at)
    wins and overwrites the stale one. Then do an initial host-seed check (covers
    first-ever run, where neither of the above exists yet)."""
    from app.db import async_session_factory

    async with async_session_factory() as db:
        await _load_last_refresh(db)
        container = read_credentials()
        setting_creds = await read_settings_credentials(db)

        if container and not setting_creds:
            await _persist_to_settings(
                db, container["access_token"], container.get("refresh_token"), container.get("expires_at") or _assume_expiry()
            )
            await db.commit()
        elif setting_creds and not container:
            _write_container_creds_file(
                setting_creds["access_token"], setting_creds.get("refresh_token"), setting_creds.get("expires_at") or _assume_expiry()
            )
        elif container and setting_creds:
            c_exp = container.get("expires_at") or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
            s_exp = setting_creds.get("expires_at") or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
            if s_exp > c_exp:
                _write_container_creds_file(setting_creds["access_token"], setting_creds.get("refresh_token"), s_exp)
            elif c_exp > s_exp:
                await _persist_to_settings(db, container["access_token"], container.get("refresh_token"), c_exp)
                await db.commit()

        await maybe_seed_from_host(db)


# ============================== seed-on-change from host ==============================


async def maybe_seed_from_host(db) -> bool:
    """Import the host credential file into (container file + settings) ONLY when its
    content hash differs from the last-seeded hash. Returns True if it (re)seeded."""
    global _last_synced_at, _last_sync_error
    src = _host_creds_path()
    if not src.exists():
        _last_sync_error = "فایل اعتبارنامه روی هاست یافت نشد."
        return False
    try:
        raw_bytes = src.read_bytes()
    except OSError as exc:  # pragma: no cover - defensive
        _last_sync_error = str(exc)
        logger.warning("host credential read failed: %s", exc)
        return False

    new_hash = hashlib.sha256(raw_bytes).hexdigest()
    hash_row = await _get_setting(db, "upstream.cli.host_seed_hash")
    if hash_row and hash_row.value == new_hash:
        return False  # unchanged since last seed — never clobber backend-managed tokens

    try:
        raw = json.loads(raw_bytes)
    except json.JSONDecodeError:
        _last_sync_error = "فایل اعتبارنامهٔ هاست JSON معتبر نیست."
        logger.warning("host credential file is not valid JSON; skipping reseed")
        return False
    parsed = _parse_raw(raw)
    if not parsed:
        _last_sync_error = "شکل فایل اعتبارنامهٔ هاست ناشناخته است."
        logger.warning("host credential file has unrecognized shape; skipping reseed")
        return False

    expires_at = parsed.get("expires_at") or _assume_expiry()
    _write_container_creds_file(parsed["access_token"], parsed.get("refresh_token"), expires_at)
    await _persist_to_settings(db, parsed["access_token"], parsed.get("refresh_token"), expires_at)
    await _set_setting(db, "upstream.cli.host_seed_hash", new_hash, is_encrypted=False)
    await db.commit()

    _last_synced_at = datetime.datetime.now(datetime.timezone.utc)
    _last_sync_error = None
    # A fresh manual `claude login` on the host is a strong signal that whatever
    # previously made auto-refresh degraded/failed is no longer relevant — give it
    # another chance rather than staying stuck until a restart.
    global _auto_refresh_state
    _auto_refresh_state = "active"
    logger.info("re-seeded upstream credentials from host file (hash changed)")
    return True


# ============================== auto-refresh ==============================


def _best_known(container: dict | None, setting_creds: dict | None) -> dict | None:
    if container and setting_creds:
        c_exp = container.get("expires_at") or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        s_exp = setting_creds.get("expires_at") or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        return container if c_exp >= s_exp else setting_creds
    return container or setting_creds


async def maybe_refresh(db) -> None:
    """Proactive refresh when <10min to expiry (TECH.md 4.1 step 2), single-flight."""
    global _auto_refresh_state
    if _auto_refresh_state == "degraded":
        return  # endpoint proven incompatible; only a fresh host-seed re-enables this

    creds = _best_known(read_credentials(), await read_settings_credentials(db))
    if not creds:
        return
    expires_at = creds.get("expires_at")
    if expires_at and expires_at > datetime.datetime.now(datetime.timezone.utc) + _REFRESH_MARGIN:
        return

    async with _refresh_lock:
        # Re-check under the lock — another coroutine may have just refreshed.
        creds = _best_known(read_credentials(), await read_settings_credentials(db))
        expires_at = creds.get("expires_at") if creds else None
        if expires_at and expires_at > datetime.datetime.now(datetime.timezone.utc) + _REFRESH_MARGIN:
            return

        # Re-read the container file first: the CLI subprocess itself may already have
        # refreshed it mid-turn (TECH.md 4.1 step 2, first bullet).
        fresh_container = read_credentials()
        fc_exp = fresh_container.get("expires_at") if fresh_container else None
        if fresh_container and fc_exp and (not expires_at or fc_exp > expires_at):
            await _persist_to_settings(db, fresh_container["access_token"], fresh_container.get("refresh_token"), fc_exp)
            await db.commit()
            await _save_last_refresh(db, ok=True, error=None)
            await db.commit()
            return

        if not creds or not creds.get("refresh_token"):
            await _save_last_refresh(db, ok=False, error="بدون refresh token در دسترس")
            await db.commit()
            return

        await _do_http_refresh(db, creds["refresh_token"])


async def _do_http_refresh(db, refresh_token: str) -> None:
    global _auto_refresh_state
    url = settings.upstream_oauth_token_url or f"{settings.upstream_base_url}/v1/oauth/token"
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.upstream_oauth_client_id,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        await _save_last_refresh(db, ok=False, error=str(exc))
        await db.commit()
        logger.warning("upstream token refresh request failed: %s", exc)
        return

    if resp.status_code == 401 or (resp.status_code == 400 and "invalid_grant" in resp.text.lower()):
        _auto_refresh_state = "failed"
        await _save_last_refresh(db, ok=False, error=f"refresh token rejected ({resp.status_code})")
        await db.commit()
        logger.error("upstream refresh token rejected — auto-refresh disabled: %s", resp.text[:300])
        return

    if resp.status_code >= 400:
        _auto_refresh_state = "degraded"
        await _save_last_refresh(db, ok=False, error=f"unexpected refresh endpoint response ({resp.status_code})")
        await db.commit()
        logger.error(
            "upstream oauth refresh endpoint incompatible — degrading to host-sync only: %s",
            resp.text[:300],
        )
        return

    try:
        data = resp.json()
        new_access = data["access_token"]
    except (json.JSONDecodeError, KeyError, ValueError):
        _auto_refresh_state = "degraded"
        await _save_last_refresh(db, ok=False, error="unrecognized refresh response shape")
        await db.commit()
        logger.error("upstream oauth refresh endpoint returned unrecognized shape — degrading")
        return

    new_refresh = data.get("refresh_token") or refresh_token
    expires_in = data.get("expires_in")
    try:
        expires_at = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=int(expires_in))
            if expires_in
            else _assume_expiry()
        )
    except (TypeError, ValueError):
        expires_at = _assume_expiry()

    _write_container_creds_file(new_access, new_refresh, expires_at)
    await _persist_to_settings(db, new_access, new_refresh, expires_at)
    _auto_refresh_state = "active"
    await _save_last_refresh(db, ok=True, error=None)
    await db.commit()
    logger.info("upstream token refreshed; new expiry=%s", expires_at.isoformat())


# ============================== status + periodic loop ==============================


def get_status() -> dict:
    creds = read_credentials()
    now = datetime.datetime.now(datetime.timezone.utc)
    connected = (
        creds is not None
        and (creds.get("expires_at") is None or creds["expires_at"] > now)
        and _auto_refresh_state != "failed"
    )
    expiring_soon = bool(
        creds and creds.get("expires_at") and creds["expires_at"] <= now + datetime.timedelta(minutes=30)
    )
    return {
        "connected": connected,
        "expires_at": creds.get("expires_at") if creds else None,
        "refresh_token_valid_until": None,  # most upstream services don't report this
        "expiring_soon": expiring_soon,
        "last_refresh": _last_refresh,
        "auto_refresh": _auto_refresh_state,
        "creds_source": "backend-managed (seeded from /host_claude)",
        "last_synced": _last_synced_at,
        "last_sync_error": _last_sync_error,
    }


async def periodic_task(interval_seconds: int = 60) -> None:
    """Run forever: seed-on-change check + proactive refresh check, every interval."""
    from app.db import async_session_factory

    while True:
        try:
            async with async_session_factory() as db:
                await maybe_seed_from_host(db)
                await maybe_refresh(db)
        except Exception:  # pragma: no cover - defensive, must never kill the loop
            logger.exception("credentials periodic task iteration failed")
        await asyncio.sleep(interval_seconds)
