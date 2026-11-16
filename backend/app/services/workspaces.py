"""v2 — persistent workspace lifecycle (TECH-V2 §2).

Manages one long-lived, stop/start-able Docker container per workspace row, from the
unified workspace image (code-server + Claude Code). Isolation envelope is applied at
`docker run` (internal network, resource caps, no-new-privileges); the upstream token
is NOT injected here — the in-workspace agent talks to `workspace_upstream_base_url`
(the backend raw relay in a full deploy). All untrusted values go via argv `-e`, never
a shell (same safe pattern as app/sandbox_runner.py).
"""
from __future__ import annotations

import asyncio
import shlex

from app.config import get_settings

settings = get_settings()


class WorkspaceError(RuntimeError):
    pass


def container_name(ws_id: int) -> str:
    return f"{settings.workspace_volume_prefix}_{ws_id}"


def volume_name(ws_id: int) -> str:
    return f"{settings.workspace_volume_prefix}_{ws_id}"


async def _run(*argv: str, timeout: int = 120) -> tuple[int, str]:
    """Run a docker command; return (rc, combined_output). Never raises on nonzero."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "timeout"
    return proc.returncode or 0, (out or b"").decode("utf-8", "replace")


async def container_state(ws_id: int) -> str:
    """One of: running | exited | missing (docker's view, source of reconciliation)."""
    rc, out = await _run(
        "docker", "inspect", "-f", "{{.State.Status}}", container_name(ws_id), timeout=30
    )
    if rc != 0:
        return "missing"
    return out.strip() or "missing"


def _agent_env() -> dict[str, str]:
    # the agent talks to the backend RAW RELAY, never the upstream directly (D2.4).
    env = {
        "ANTHROPIC_BASE_URL": settings.workspace_relay_url,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "NO_PROXY": "localhost,127.0.0.1,backend",
    }
    if settings.workspace_egress_enabled and settings.egress_proxy_url:
        env["HTTPS_PROXY"] = settings.egress_proxy_url
        env["HTTP_PROXY"] = settings.egress_proxy_url
    return env


def _run_argv(ws_id: int, gateway_key: str) -> list[str]:
    name = container_name(ws_id)
    vol = volume_name(ws_id)
    env = _agent_env()
    env["ANTHROPIC_AUTH_TOKEN"] = gateway_key  # per-workspace key, NOT the upstream token
    argv = [
        "docker", "run", "-d",
        "--name", name,
        "--network", settings.workspace_network,
        "--memory", settings.workspace_memory,
        "--cpus", settings.workspace_cpus,
        "--pids-limit", str(settings.workspace_pids_limit),
        "--security-opt", "no-new-privileges",
        "--label", "coolade.workspace=1",
        "-v", f"{vol}:/home/coder/project",
    ]
    for k, v in env.items():
        argv += ["-e", f"{k}={v}"]
    argv.append(settings.workspace_image)
    # code-server args (image ENTRYPOINT is code-server)
    argv += [
        "--auth", "none", "--bind-addr", "0.0.0.0:8080",
        "--disable-telemetry", "--disable-update-check", "/home/coder/project",
    ]
    return argv


async def _seed_volume(ws_id: int, repo_url: str | None, base_branch: str | None,
                       git_token: str | None, git_host: str) -> str | None:
    """Populate the workspace volume before code-server starts.

    Repo kind with a token: shallow-clone into the volume. Otherwise seed a tiny
    sample so the workspace isn't empty. Returns an error string on failure, else None.
    """
    vol = volume_name(ws_id)
    # A fresh named volume is root-owned; the code-server image runs as uid 1000
    # (coder), so we run the seed/clone one-shot as root and chown to 1000 at the end.
    if repo_url and git_token:
        # Inject the token into the clone URL host (never logged). https only.
        url = repo_url
        if url.startswith("https://"):
            rest = url[len("https://"):]
            url = f"https://oauth2:{git_token}@{rest}"
        branch = shlex.quote(base_branch or "main")
        clone = (
            f"git clone --depth 1 --branch {branch} {shlex.quote(url)} /work "
            f"|| git clone --depth 1 {shlex.quote(url)} /work; "
            "rc=$?; chown -R 1000:1000 /work; exit $rc"
        )
        rc, out = await _run(
            "docker", "run", "--rm", "--user", "0:0", "--network", settings.workspace_network,
            "-v", f"{vol}:/work", "--entrypoint", "sh", settings.workspace_image,
            "-c", clone, timeout=300,
        )
        return None if rc == 0 else f"clone failed: {out[-300:]}"
    # no repo → seed a sample so both chat & dev are demonstrable
    seed = (
        'mkdir -p /work && '
        'printf "def greet(name):\\n    return \\"hello \\" + name\\n" > /work/app.py && '
        'printf "# workspace\\nاز پنل Claude Code بخواه روی app.py کار کند.\\n" > /work/README.md && '
        'chown -R 1000:1000 /work'
    )
    rc, out = await _run(
        "docker", "run", "--rm", "--user", "0:0", "-v", f"{vol}:/work",
        "--entrypoint", "sh", settings.workspace_image, "-c", seed, timeout=120,
    )
    return None if rc == 0 else f"seed failed: {out[-200:]}"


async def create_container(ws_id: int, *, gateway_key: str, repo_url: str | None,
                           base_branch: str | None, git_token: str | None,
                           git_host: str) -> None:
    """Create volume, seed/clone, then run the code-server container. Raises on failure."""
    await _run("docker", "volume", "create", volume_name(ws_id), timeout=30)
    err = await _seed_volume(ws_id, repo_url, base_branch, git_token, git_host)
    if err:
        raise WorkspaceError(err)
    # remove any stale container with the same name first (idempotent create)
    await _run("docker", "rm", "-f", container_name(ws_id), timeout=30)
    rc, out = await _run(*_run_argv(ws_id, gateway_key), timeout=120)
    if rc != 0:
        raise WorkspaceError(f"run failed: {out[-300:]}")


async def start_container(ws_id: int) -> None:
    rc, out = await _run("docker", "start", container_name(ws_id), timeout=60)
    if rc != 0:
        raise WorkspaceError(f"start failed: {out[-200:]}")


async def stop_container(ws_id: int) -> None:
    await _run("docker", "stop", container_name(ws_id), timeout=60)


async def remove_container(ws_id: int, *, drop_volume: bool) -> None:
    await _run("docker", "rm", "-f", container_name(ws_id), timeout=60)
    if drop_volume:
        await _run("docker", "volume", "rm", "-f", volume_name(ws_id), timeout=60)


async def disk_bytes(ws_id: int) -> int:
    rc, out = await _run(
        "docker", "run", "--rm", "-v", f"{volume_name(ws_id)}:/w:ro",
        "--entrypoint", "sh", settings.workspace_image, "-c", "du -sb /w | cut -f1",
        timeout=60,
    )
    try:
        return int(out.strip().split()[0]) if rc == 0 and out.strip() else 0
    except (ValueError, IndexError):
        return 0
