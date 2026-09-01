"""اصلاحیهٔ ۶ / amendment 6 — Stage 2: run a Claude Code turn inside an ISOLATED
per-session container instead of in-process, so Bash/git can be enabled safely.

Security model (why this is not just `--disallowedTools` flipped):
  * The turn runs in a throwaway `docker run` container, NOT the backend — so a
    malicious command / prompt-injection cannot touch the backend's DB, the OAuth
    credential file, or other users' data (none are mounted).
  * Rootfs is read-only; only the user's own workspace is bind-mounted rw at /work;
    /tmp and $HOME are size-capped tmpfs.
  * Resource caps: memory, cpus, pids-limit; `no-new-privileges`; all caps dropped.
  * Network: the container is attached to an INTERNAL docker network with no direct
    internet — its only egress is the allowlist proxy (HTTPS_PROXY). The injected
    upstream token can therefore only reach the allowed upstream host, nowhere else.
  * ALL untrusted values (prompt, model) are passed as `-e VAR=value` items in the
    argv list — never interpolated into a shell — so there is no command injection.

Disabled by default (`SANDBOX_ENABLED=0`). It refuses to run unless an egress proxy
is configured, because running with the upstream token but unrestricted egress would
let the sandbox exfiltrate the token — the one thing this design must prevent.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.cli_runner import _translate_event, workspace_dir
from app.config import get_settings
from app.models import ThinkingLevel
from app.services import thinking as thinking_service

settings = get_settings()

# Independent concurrency cap for sandbox containers (they are heavier than in-proc runs).
_sandbox_semaphore = asyncio.Semaphore(getattr(settings, "sandbox_max_concurrency", 2))


class SandboxDisabledError(RuntimeError):
    """Stage-2 sandbox is not enabled / not safely configured."""


def _resolve_upstream_token() -> str | None:
    try:
        from app.upstream import credentials

        creds = credentials.read_credentials()
        if creds and creds.get("access_token"):
            return str(creds["access_token"])
    except Exception:
        pass
    return None


def _build_sandbox_env(upstream_model: str, thinking_level: ThinkingLevel) -> dict[str, str]:
    env: dict[str, str] = {
        "SANDBOX_MODEL": upstream_model,
        "ANTHROPIC_BASE_URL": settings.upstream_base_url,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        # Egress is CONNECT-only through the allowlist proxy.
        "HTTPS_PROXY": settings.egress_proxy_url,
        "HTTP_PROXY": settings.egress_proxy_url,
    }
    token = _resolve_upstream_token()
    if token:
        env["ANTHROPIC_AUTH_TOKEN"] = token
    tokens = thinking_service.max_thinking_tokens(thinking_level)
    if tokens:
        env["MAX_THINKING_TOKENS"] = str(tokens)
    return env


def _docker_argv(*, name: str, workspace_real: Path, env: dict[str, str]) -> list[str]:
    argv = [
        "docker", "run", "--rm", "-i",
        "--name", name,
        "--network", settings.sandbox_network,
        "--user", "1000:1000",
        "--read-only",
        "--tmpfs", "/tmp:size=64m,exec",
        "--tmpfs", "/home/runner:size=128m,exec",
        "--memory", settings.sandbox_memory,
        "--cpus", settings.sandbox_cpus,
        "--pids-limit", str(settings.sandbox_pids_limit),
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "-v", f"{workspace_real}:/work",
    ]
    for k, v in env.items():
        argv += ["-e", f"{k}={v}"]
    argv.append(settings.sandbox_image)
    return argv


async def run_sandbox_turn(
    *,
    user_id: int,
    upstream_model: str,
    prompt: str,
    thinking_level: ThinkingLevel = ThinkingLevel.standard,
) -> AsyncIterator[dict[str, Any]]:
    """Yields the same normalized events (start/delta/tool/done/error) as the
    in-process runner, but executed inside an isolated sandbox container."""
    if not settings.sandbox_enabled:
        raise SandboxDisabledError("sandbox runner is disabled (SANDBOX_ENABLED=0)")
    if not settings.egress_proxy_url:
        # Refuse to run with the upstream token but no egress restriction.
        raise SandboxDisabledError("refusing to run sandbox without an egress allowlist proxy")

    ws_real = Path(workspace_dir(user_id)).resolve()
    env = _build_sandbox_env(upstream_model, thinking_level)
    env["SANDBOX_PROMPT"] = prompt
    name = f"ecosbx_{user_id}_{uuid.uuid4().hex[:10]}"
    argv = _docker_argv(name=name, workspace_real=ws_real, env=env)

    async with _sandbox_semaphore:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        deadline = time.monotonic() + settings.sandbox_timeout_seconds
        timed_out = False
        got_terminal = False
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
                for ev in _translate_event(obj, upstream_model=upstream_model):
                    if ev["event"] in ("done", "error"):
                        got_terminal = True
                    yield ev
        finally:
            # Kill the container by name (terminating the docker client alone may leave
            # the container running).
            await _docker_kill(name)
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=10)
                except asyncio.TimeoutError:
                    proc.kill()

        if timed_out:
            yield {
                "event": "error",
                "code": "timeout",
                "message": "اجرای دستیار در سندباکس بیش از حد مجاز طول کشید و متوقف شد.",
            }
        elif not got_terminal and proc.returncode not in (0, None):
            yield {
                "event": "error",
                "code": "cli_error",
                "message": "اجرای دستیار در سندباکس به‌طور غیرمنتظره متوقف شد.",
            }


async def _docker_kill(name: str) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "kill", name,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
    except Exception:
        pass
