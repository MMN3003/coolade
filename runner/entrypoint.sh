#!/usr/bin/env bash
# اصلاحیهٔ ۶ / amendment 6 — Stage 2 sandbox entrypoint.
# Runs one Claude Code turn with Bash/git ENABLED inside the isolated container.
# All inputs arrive as data via env (never interpolated into a shell command by the
# caller). Emits the same stream-json contract cli_runner already parses.
set -euo pipefail

MODEL="${SANDBOX_MODEL:-}"
PROMPT="${SANDBOX_PROMPT:-}"

# Tools: Bash + git are allowed here (the container itself is the sandbox). Web tools
# stay off — egress is locked to an allowlist anyway, and the agent shouldn't browse.
ALLOWED_TOOLS="Bash,Read,Write,Edit,Glob,Grep"
DISALLOWED_TOOLS="WebFetch,WebSearch"

# Optional git identity for commits made inside the sandbox (push target is injected
# by the backend only when configured — see sandbox_runner / TECH.md §6, git is
# parametric and disabled until git.ecobin.ir repo + scoped token are provided).
git config --global user.email "${GIT_AUTHOR_EMAIL:-assistant@ecobin.local}" || true
git config --global user.name "${GIT_AUTHOR_NAME:-EcoCode Assistant}" || true
git config --global --add safe.directory /work || true

exec claude -p "$PROMPT" \
    --output-format stream-json --verbose \
    --model "$MODEL" \
    --permission-mode acceptEdits \
    --allowedTools "$ALLOWED_TOOLS" \
    --disallowedTools "$DISALLOWED_TOOLS"
