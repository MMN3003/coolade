"""Web chat = one headless Claude Code CLI subprocess per user message (TECH.md section 5.1/5.4).

No resident process, no queueing beyond a global concurrency semaphore and a
hard per-conversation "only one in flight" lock (a concurrent second message
in the same conversation gets an immediate 409 chat_busy rather than
queueing — TECH.md section 5.4).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db import async_session_factory
from app.models import Setting, ThinkingLevel
from app.security import decrypt_secret
from app.services import thinking as thinking_service

logger = logging.getLogger("ecocode.cli_runner")

settings = get_settings()

_SESSION_NOT_FOUND_MARKER = "No conversation found with session ID"

_semaphore = asyncio.Semaphore(settings.cli_max_concurrency)
_busy_conversations: set[int] = set()

ALLOWED_TOOLS = "Read(./**),Write(./**),Edit(./**),Glob,Grep"
DISALLOWED_TOOLS = "Bash,WebFetch,WebSearch"


class ChatBusyError(Exception):
    """A message is already being processed for this conversation."""


def try_acquire_conversation(conversation_id: int) -> bool:
    """Atomic (no awaits) check-and-reserve. Caller must call release_conversation() when done."""
    if conversation_id in _busy_conversations:
        return False
    _busy_conversations.add(conversation_id)
    return True


def release_conversation(conversation_id: int) -> None:
    _busy_conversations.discard(conversation_id)


def workspace_dir(user_id: int) -> Path:
    user_root = Path(settings.workspace_root) / str(user_id)
    ws = user_root / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    try:
        user_root.chmod(0o700)
        ws.chmod(0o700)
    except OSError:
        pass
    real = Path(os.path.realpath(ws))
    real_root = Path(os.path.realpath(user_root))
    if real != real_root and real_root not in real.parents:
        raise RuntimeError("workspace path escaped user root")
    return ws


async def _resolve_mode() -> str:
    env_mode = os.environ.get("UPSTREAM_MODE")
    if env_mode:
        return env_mode
    async with async_session_factory() as db:
        row = await db.get(Setting, "upstream.mode")
        return row.value if row and row.value else "mock"


async def _build_env(thinking_level: ThinkingLevel) -> dict[str, str]:
    """Whitelist-only env for the CLI subprocess — never backend secrets/DB URL (TECH.md 5.4).

    Issue D: `MAX_THINKING_TOKENS` is the *mechanism* for the web-chat thinking-level
    control — env per turn, never a keyword injected into the prompt text (TECH.md 5.7).
    Unset entirely for `off` (model default, effectively no extended thinking).
    """
    env: dict[str, str] = {
        "HOME": settings.cli_home,
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"),
        "ANTHROPIC_BASE_URL": settings.upstream_base_url,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    tokens = thinking_service.max_thinking_tokens(thinking_level)
    if tokens:
        env["MAX_THINKING_TOKENS"] = str(tokens)
    if settings.http_proxy:
        env["HTTP_PROXY"] = settings.http_proxy
    if settings.https_proxy:
        env["HTTPS_PROXY"] = settings.https_proxy
    if settings.no_proxy:
        env["NO_PROXY"] = settings.no_proxy

    if not settings.mock_cli:
        mode = await _resolve_mode()
        if mode == "apikey":
            async with async_session_factory() as db:
                row = await db.get(Setting, "upstream.apikey")
                token = decrypt_secret(row.value) if row and row.value else None
            if token:
                env["ANTHROPIC_AUTH_TOKEN"] = token
        # cli_creds: nothing to add — CLI reads $HOME/.claude/.credentials.json itself.
    return env


def _build_command(prompt: str, upstream_model: str, resume_session_id: str | None) -> list[str]:
    if settings.mock_cli:
        cmd = ["python3", "/app/bin/mock-claude"]
    else:
        cmd = ["claude"]
    cmd += ["-p", prompt, "--output-format", "stream-json", "--verbose", "--model", upstream_model]
    if resume_session_id:
        cmd += ["--resume", resume_session_id]
    cmd += ["--allowedTools", ALLOWED_TOOLS, "--disallowedTools", DISALLOWED_TOOLS]
    return cmd


_WRITE_TOOL_NAMES = {"Write", "Edit"}


def _classify_result_error(subtype: str | None, errors: list[str]) -> tuple[str, str]:
    """Best-effort mapping of an upstream/CLI failure to (error_code, پیام فارسی) —
    TECH.md messages.error_code enum: quota_exceeded | upstream_rate_limited | cli_error
    | timeout | aborted_restart (timeout/aborted_restart are set elsewhere)."""
    text = (" ".join(errors or []) + " " + (subtype or "")).lower()
    if any(k in text for k in ("rate_limit", "429", "overloaded", "529")):
        return "upstream_rate_limited", "سرویس بالادستی فعلاً شلوغ است؛ کمی بعد دوباره تلاش کنید."
    if any(k in text for k in ("quota", "credit balance", "insufficient_quota", "insufficient credit")):
        return "quota_exceeded", "سهمیهٔ سرویس بالادستی تمام شده است."
    return "cli_error", "اجرای دستیار با خطا مواجه شد."


def _translate_event(obj: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    t = obj.get("type")

    if t == "system" and obj.get("subtype") == "init":
        events.append({"event": "start", "session_id": obj.get("session_id")})
        return events

    if t == "assistant":
        message = obj.get("message") or {}
        for block in message.get("content") or []:
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                events.append({"event": "delta", "text": block["text"]})
            elif btype == "tool_use":
                name = block.get("name") or "tool"
                inp = block.get("input") or {}
                file_path = inp.get("file_path") or inp.get("path")
                summary = f"{name} → {file_path}" if file_path else name
                events.append(
                    {
                        "event": "tool",
                        "name": name,
                        "summary": summary,
                        "file_path": file_path,
                        "tool_use_id": block.get("id"),
                    }
                )
        return events

    if t == "user":
        # tool_result for a previous tool_use block — internal only (never forwarded
        # as SSE); used to confirm whether a Write/Edit actually succeeded before it's
        # allowed into `files_changed` (see run_conversation_turn / the "denied write
        # must not appear" requirement).
        message = obj.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    events.append(
                        {
                            "event": "tool_result",
                            "tool_use_id": block.get("tool_use_id"),
                            "is_error": bool(block.get("is_error")),
                        }
                    )
        return events

    if t == "result":
        if obj.get("is_error"):
            cli_errors = [str(e) for e in obj.get("errors") or []]
            code, message_fa = _classify_result_error(obj.get("subtype"), cli_errors)
            events.append(
                {
                    "event": "error",
                    "code": code,
                    "message": message_fa,
                    "subtype": obj.get("subtype"),
                    "cli_errors": cli_errors,
                }
            )
            return events
        usage = obj.get("usage") or {}
        output_tokens = int(usage.get("output_tokens") or 0)
        # Defensive fold (TECH.md 5.7): if the upstream service ever reports thinking
        # tokens as a separate field, they still get weighed as output — never free.
        thinking_tokens = usage.get("thinking_tokens")
        if isinstance(thinking_tokens, (int, float)):
            output_tokens += int(thinking_tokens)
        events.append(
            {
                "event": "done",
                "usage": {
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": output_tokens,
                    "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
                    "cache_write_tokens": int(usage.get("cache_creation_input_tokens") or 0),
                },
                "result_text": obj.get("result"),
                "session_id": obj.get("session_id"),
            }
        )
        return events

    return events


async def _run_process(
    cmd: list[str], cwd: Path, env: dict[str, str], timeout: int
) -> AsyncIterator[dict[str, Any]]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    deadline = time.monotonic() + timeout
    timed_out = False
    got_terminal_event = False
    try:
        assert proc.stdout is not None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                timed_out = True
                break
            if not line:
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            for ev in _translate_event(obj):
                if ev["event"] in ("done", "error"):
                    got_terminal_event = True
                yield ev
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

    if timed_out:
        yield {
            "event": "error",
            "code": "timeout",
            "message": "اجرای دستیار بیش از حد مجاز طول کشید و متوقف شد.",
        }
    elif not got_terminal_event and proc.returncode not in (0, None):
        yield {
            "event": "error",
            "code": "cli_error",
            "message": "اجرای دستیار به‌طور غیرمنتظره متوقف شد.",
        }


def _is_session_not_found(ev: dict[str, Any]) -> bool:
    if ev.get("event") != "error":
        return False
    return any(_SESSION_NOT_FOUND_MARKER in e for e in ev.get("cli_errors") or [])


def _resolve_written_path(ws_real: Path, file_path: str) -> Path | None:
    """realpath-resolve a Write/Edit tool's reported path against the workspace root;
    return None if it escapes containment (folded-in fix: a denied/out-of-workspace
    write, e.g. /tmp/x or /etc/passwd, must never appear in files_changed)."""
    try:
        candidate = Path(file_path)
        real = Path(os.path.realpath(candidate if candidate.is_absolute() else ws_real / candidate))
    except (OSError, ValueError):
        return None
    if real != ws_real and ws_real not in real.parents:
        return None
    return real


async def run_conversation_turn(
    *,
    user_id: int,
    conversation_id: int,
    prompt: str,
    upstream_model: str,
    resume_session_id: str | None,
    thinking_level: ThinkingLevel = ThinkingLevel.standard,
) -> AsyncIterator[dict[str, Any]]:
    """Caller is responsible for the per-conversation busy reservation (see
    try_acquire_conversation/release_conversation) — kept out of this generator so the
    409 chat_busy check happens synchronously before any SSE bytes are sent.

    If the CLI no longer knows the stored session id (its session state was
    lost, e.g. container recreated before claude_state was volume-backed),
    the turn is retried ONCE without --resume: the user sees a normal stream
    on a fresh session (context loss accepted), and the caller persists the
    new session_id from the start/done events.

    The `done` event's `files_changed` list only ever contains paths from
    Write/Edit tool_use blocks that (a) got a non-error tool_result AND (b)
    realpath-resolve inside this user's workspace — a denied or out-of-workspace
    write never appears there, regardless of what the CLI attempted.
    """
    ws = workspace_dir(user_id)
    ws_real = Path(os.path.realpath(ws))
    env = await _build_env(thinking_level)
    async with _semaphore:
        resume = resume_session_id
        for attempt in (1, 2):
            cmd = _build_command(prompt, upstream_model, resume)
            # Hold back leading "start" events until real output arrives, so a
            # session-not-found first attempt is discarded invisibly and the
            # retry's own start event is the only one the caller ever sees.
            pending: list[dict[str, Any]] = []
            streamed = False
            retry = False
            pending_writes: dict[str, str] = {}  # tool_use_id -> raw file_path (unconfirmed)
            confirmed_files: list[str] = []
            async for ev in _run_process(cmd, cwd=ws, env=env, timeout=settings.cli_timeout_seconds):
                if not streamed and ev["event"] == "start":
                    pending.append(ev)
                    continue
                if attempt == 1 and resume and not streamed and _is_session_not_found(ev):
                    retry = True
                    break
                for held in pending:
                    yield held
                pending.clear()
                streamed = True

                if (
                    ev["event"] == "tool"
                    and ev.get("name") in _WRITE_TOOL_NAMES
                    and ev.get("file_path")
                    and ev.get("tool_use_id")
                ):
                    pending_writes[ev["tool_use_id"]] = ev["file_path"]
                if ev["event"] == "tool_result":
                    file_path = pending_writes.pop(ev.get("tool_use_id"), None)
                    if file_path and not ev.get("is_error"):
                        resolved = _resolve_written_path(ws_real, file_path)
                        if resolved is not None:
                            confirmed_files.append(str(resolved.relative_to(ws_real)))
                    continue  # internal-only event, never forwarded as SSE

                if ev["event"] == "done":
                    ev = dict(ev)
                    ev["files_changed"] = list(dict.fromkeys(confirmed_files))
                    ev["thinking_level"] = thinking_level.value
                yield ev
            if not retry:
                for held in pending:
                    yield held
                return
            logger.info(
                "cli session rebuild: conversation_id=%s user_id=%s stale_session_id=%s "
                "(session state not found by CLI; retrying without --resume)",
                conversation_id,
                user_id,
                resume,
            )
            resume = None
