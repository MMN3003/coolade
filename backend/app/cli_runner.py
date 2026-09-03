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
from app.team_files import team_memory_dir
from app.team_membership import member_team_rows

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


async def sync_team_links(user_id: int, cwd: Path) -> list[tuple[int, str, str]]:
    """اصلاحیهٔ ۴ / Issue I (TECH.md 5.4/5.9): called BEFORE every spawn. Makes every
    MEMBER team's shared memory visible as <cwd>/teams/<slug> -> /data/teams/<team_id>/memory
    (a symlink *under* cwd, so the existing `--allowedTools "Read(./**),Write(./**),
    Edit(./**),Glob,Grep"` already covers it — no absolute-path tool grant added).
    Removes stale links for teams the user is no longer a member of, and (re)writes
    a small generated <cwd>/teams/README.md hint (member team list + a nudge to read
    the relevant team folder before answering — the "hybrid" half of the file-visibility
    design, TECH.md 5.9).

    team_members (via member_team_rows) is authoritative — never the presence of a
    symlink already on disk — so a membership change takes effect on the user's very
    next turn. Returns the member team list; the caller also uses it to widen the
    write-containment set (see run_conversation_turn / _resolve_written_path)."""
    async with async_session_factory() as db:
        member_teams = await member_team_rows(db, user_id)

    teams_dir = cwd / "teams"
    member_slugs = {slug for _tid, slug, _name in member_teams}

    if teams_dir.exists():
        for entry in teams_dir.iterdir():
            if entry.is_symlink() and entry.name not in member_slugs:
                try:
                    entry.unlink()
                except OSError:
                    logger.warning("sync_team_links: failed to remove stale link %s", entry)

    if not member_teams:
        # Per TECH.md 5.4: a user in no team gets an empty/absent teams/ dir.
        return member_teams

    teams_dir.mkdir(exist_ok=True)
    for team_id, slug, _name in member_teams:
        target = team_memory_dir(team_id)
        link_path = teams_dir / slug
        try:
            if link_path.is_symlink():
                if os.path.realpath(link_path) != os.path.realpath(target):
                    link_path.unlink()
                    link_path.symlink_to(target)
            elif not link_path.exists():
                link_path.symlink_to(target)
            # else: an unexpected non-symlink already occupies this name — leave it
            # alone rather than clobber user data.
        except OSError:
            logger.warning("sync_team_links: failed to link team_id=%s for user_id=%s", team_id, user_id)

    readme_lines = [
        "# تیم‌های شما\n\n",
        "حافظه‌های مشترک هر تیم در پوشهٔ هم‌نامش اینجاست؛ پیش از پاسخ به سؤالات "
        "مرتبط با تیم، این پوشه را بخوان.\n\n",
    ]
    for _tid, slug, name in member_teams:
        readme_lines.append(f"- **{name}** → `./teams/{slug}/`\n")
    try:
        (teams_dir / "README.md").write_text("".join(readme_lines), encoding="utf-8")
    except OSError:
        logger.warning("sync_team_links: failed to write teams/README.md for user_id=%s", user_id)

    return member_teams


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


def _build_command(
    prompt: str,
    upstream_model: str,
    resume_session_id: str | None,
    team_dirs: list[str] | None = None,
    mcp_config_path: str | None = None,
) -> list[str]:
    if settings.mock_cli:
        cmd = ["python3", "/app/bin/mock-claude"]
    else:
        cmd = ["claude"]
    cmd += ["-p", prompt, "--output-format", "stream-json", "--verbose", "--model", upstream_model]
    # Live token streaming: without this the CLI only emits one `assistant` event per
    # COMPLETED message, so the whole reply arrived as a single delta at turn end and
    # the user saw nothing until done (reported 2026-09-01). With it, the CLI also
    # emits `stream_event` objects carrying real text_delta chunks; _translate_event
    # forwards those and SKIPS the (now duplicate) text blocks of complete messages.
    cmd += ["--include-partial-messages"]
    # acceptEdits auto-approves Write/Edit within the permitted dirs (cwd + any --add-dir
    # team memory dirs) so the agent can actually edit team memory without an interactive
    # prompt; it does NOT grant Bash/web (still in --disallowedTools) nor writes outside
    # the permitted dirs (e.g. /tmp, /etc still blocked) — verified 2026-08-23.
    cmd += ["--permission-mode", "acceptEdits"]
    # Token economy: output tokens carry the highest ledger weight (15x), so a
    # short standing instruction trims prose without touching real reports.
    cmd += [
        "--append-system-prompt",
        "پاسخ‌ها را فشرده بده: بدون مقدمه، بدون تکرار سؤال، بدون جمع‌بندی تشریفاتی. "
        "فقط وقتی صریحاً گزارش رسمی/مدیریتی یا متن بلند خواسته شده مفصل بنویس.",
    ]
    # amendment-1 / DS6: granted organizational services ride in as MCP servers.
    # --strict-mcp-config pins the turn to exactly this generated file, so no
    # stray project/user config can add unaudited servers to a governed turn.
    if mcp_config_path:
        cmd += ["--mcp-config", mcp_config_path, "--strict-mcp-config"]
    if resume_session_id:
        cmd += ["--resume", resume_session_id]
    # اصلاحیهٔ ۴ / Issue I: a symlink under cwd (teams/<slug>) is not enough — Claude Code
    # canonicalizes it to the real /data/teams/<id>/memory path, which lives OUTSIDE cwd,
    # so the CLI's own permission layer blocks it. Grant each member team dir explicitly
    # via --add-dir AND matching Read/Write/Edit allow-rules on the real path.
    allowed = ALLOWED_TOOLS
    for d in team_dirs or []:
        cmd += ["--add-dir", d]
        allowed += f",Read({d}/**),Write({d}/**),Edit({d}/**)"
    cmd += ["--allowedTools", allowed, "--disallowedTools", DISALLOWED_TOOLS]
    return cmd


_WRITE_TOOL_NAMES = {"Write", "Edit"}


def _classify_result_error(
    subtype: str | None,
    errors: list[str],
    *,
    upstream_model: str | None = None,
    reset_hint: str | None = None,
) -> tuple[str, str]:
    """Best-effort mapping of an upstream/CLI failure to (error_code, پیام فارسی) —
    TECH.md messages.error_code enum: quota_exceeded | upstream_rate_limited | cli_error
    | timeout | aborted_restart (timeout/aborted_restart are set elsewhere).

    An upstream rate-limit (429/overloaded) maps to error_code=upstream_rate_limited
    with the SAME actionable message as the API-key surface (model name + lighter-model
    suggestion + account 5h reset hint when known) — product-owner follow-up
    (2026-08-22); shared wording lives in app.errors.upstream_rate_limited_message so
    both the failed message row (Issue C retry bubble) and passthrough agree."""
    text = (" ".join(errors or []) + " " + (subtype or "")).lower()
    if any(k in text for k in ("rate_limit", "429", "overloaded", "529")):
        from app.errors import upstream_rate_limited_message

        return "upstream_rate_limited", upstream_rate_limited_message(
            model=upstream_model, reset_at=reset_hint
        )
    if any(k in text for k in ("quota", "credit balance", "insufficient_quota", "insufficient credit")):
        return "quota_exceeded", "سهمیهٔ سرویس بالادستی تمام شده است."
    return "cli_error", "اجرای دستیار با خطا مواجه شد."


def _translate_event(
    obj: dict[str, Any],
    *,
    upstream_model: str | None = None,
    reset_hint: str | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    t = obj.get("type")

    if t == "system" and obj.get("subtype") == "init":
        events.append({"event": "start", "session_id": obj.get("session_id")})
        return events

    if t == "stream_event":
        # --include-partial-messages: the raw Anthropic SSE event is nested under
        # `event`. Only text deltas become UI deltas; thinking/other deltas are
        # internal. (Complete `assistant` messages still follow — their text
        # blocks are skipped below to avoid double-emitting the same content.)
        inner = obj.get("event") or {}
        if inner.get("type") == "content_block_delta":
            delta = inner.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                events.append({"event": "delta", "text": delta["text"]})
        return events

    if t == "assistant":
        message = obj.get("message") or {}
        for block in message.get("content") or []:
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                # Text already streamed via stream_event deltas above — emitting it
                # here again would duplicate every reply. Tool_use blocks are NOT
                # covered by partial deltas, so they still translate below.
                continue
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
            code, message_fa = _classify_result_error(
                obj.get("subtype"), cli_errors,
                upstream_model=upstream_model, reset_hint=reset_hint,
            )
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
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    *,
    upstream_model: str | None = None,
    reset_hint: str | None = None,
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
            for ev in _translate_event(
                obj, upstream_model=upstream_model, reset_hint=reset_hint
            ):
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


def _resolve_written_path(
    roots: list[tuple[Path, str | None]], base: Path, file_path: str
) -> tuple[Path, str] | None:
    """realpath-resolve a Write/Edit tool's reported path against the containment
    ROOT UNION (اصلاحیهٔ ۴ / Issue I, TECH.md 5.4: workspace ∪ realpath(/data/teams/<tid>/memory)
    for every team the user is currently a member of); return None if it escapes
    every root in the union (folded-in fix, pre-اصلاحیهٔ ۴: a denied/out-of-workspace
    write, e.g. /tmp/x or /etc/passwd, must never appear in files_changed).

    `roots` is `[(ws_real, None)] + [(team_memory_real, "teams/<slug>"), ...]` — the
    label (when set) is prefixed onto the returned display-relpath so a team-memory
    write shows as "teams/hr/notes.md" rather than escaping relative_to(ws_real)."""
    try:
        candidate = Path(file_path)
        real = Path(os.path.realpath(candidate if candidate.is_absolute() else base / candidate))
    except (OSError, ValueError):
        return None
    for root, label in roots:
        if real == root or root in real.parents:
            rel = real.relative_to(root)
            display = str(rel) if label is None else str(Path(label) / rel)
            return real, display
    return None


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
    # اصلاحیهٔ ۴ / Issue I: sync <cwd>/teams/<slug> symlinks to CURRENT membership
    # before spawn, and widen the write-containment set to workspace ∪ member team
    # memory dirs (TECH.md 5.4/5.9).
    member_teams = await sync_team_links(user_id, ws)
    containment_roots: list[tuple[Path, str | None]] = [(ws_real, None)]
    team_dirs: list[str] = []
    for team_id, slug, _name in member_teams:
        team_real = Path(os.path.realpath(team_memory_dir(team_id)))
        containment_roots.append((team_real, f"teams/{slug}"))
        team_dirs.append(str(team_real))
    # amendment-1 / DS6: sync granted services (skills → <ws>/.claude/skills,
    # per-turn MCP config with a fresh turn key). Failure never blocks the turn —
    # the user just chats without service tools this once.
    mcp_config_path: str | None = None
    service_allowed_tools: list[str] = []
    try:
        from app.services.service_sync import sync_service_access

        mcp_config_path, service_allowed_tools = await sync_service_access(user_id, ws)
    except Exception:  # pragma: no cover - degrade gracefully, never kill a turn
        logger.exception("service sync failed for user %s", user_id)
    # Account 5h reset hint for the actionable upstream-429 message (product-owner
    # follow-up, 2026-08-22) — read once up front; the CLI turn itself has no DB.
    reset_hint: str | None = None
    try:
        from app.services import account_limits

        async with async_session_factory() as db:
            reset_hint = await account_limits.get_5h_reset_hint(db)
    except Exception:  # pragma: no cover - telemetry only, never block a turn
        reset_hint = None
    async with _semaphore:
        resume = resume_session_id
        for attempt in (1, 2):
            cmd = _build_command(prompt, upstream_model, resume, team_dirs, mcp_config_path)
            if service_allowed_tools:
                # Permission rules prepared by the sync (mcp__<server> per granted
                # service + Skill when any skill is synced); single comma-joined
                # arg — the flag is variadic and must not swallow following args.
                cmd += ["--allowedTools", ",".join(service_allowed_tools)]
            # Hold back leading "start" events until real output arrives, so a
            # session-not-found first attempt is discarded invisibly and the
            # retry's own start event is the only one the caller ever sees.
            pending: list[dict[str, Any]] = []
            streamed = False
            retry = False
            pending_writes: dict[str, str] = {}  # tool_use_id -> raw file_path (unconfirmed)
            confirmed_files: list[str] = []
            async for ev in _run_process(
                cmd, cwd=ws, env=env, timeout=settings.cli_timeout_seconds,
                upstream_model=upstream_model, reset_hint=reset_hint,
            ):
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
                        resolved = _resolve_written_path(containment_roots, ws_real, file_path)
                        if resolved is not None:
                            _real, display = resolved
                            confirmed_files.append(display)
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


async def run_oneshot_turn(
    *,
    user_id: int,
    upstream_model: str,
    prompt: str,
    thinking_level: ThinkingLevel = ThinkingLevel.off,
) -> AsyncIterator[dict[str, Any]]:
    """Stateless single-shot CLI turn for the API-key passthrough surface
    (اصلاحیهٔ ۵ / amendment 5: /v1/* now runs through the Claude Code CLI, not
    LiteLLM — so both surfaces share the same upstream identity and the OAuth
    subscription's "must look like Claude Code" gate is satisfied uniformly,
    which is what made opus/sonnet return 429 on the old passthrough path).

    Unlike run_conversation_turn there is NO conversation, NO --resume/session
    persistence, and NO per-conversation busy lock: each API request is
    independent and the client is expected to carry its own history in the
    request body (the caller flattens it into `prompt`). Team memory is not
    mounted on this surface. Concurrency is still bounded by the shared global
    _semaphore. Yields the same normalized events (start/delta/tool/done/error)
    as run_conversation_turn so the caller can reshape them into the OpenAI /
    Anthropic wire formats the API client expects."""
    ws = workspace_dir(user_id)
    env = await _build_env(thinking_level)
    # Account 5h reset hint for the actionable upstream-429 message (parity with
    # run_conversation_turn) — read once up front; the CLI turn itself has no DB.
    reset_hint: str | None = None
    try:
        from app.services import account_limits

        async with async_session_factory() as db:
            reset_hint = await account_limits.get_5h_reset_hint(db)
    except Exception:  # pragma: no cover - telemetry only, never block a turn
        reset_hint = None
    async with _semaphore:
        cmd = _build_command(prompt, upstream_model, None, None)
        async for ev in _run_process(
            cmd,
            cwd=ws,
            env=env,
            timeout=settings.cli_timeout_seconds,
            upstream_model=upstream_model,
            reset_hint=reset_hint,
        ):
            yield ev
