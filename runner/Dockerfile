# اصلاحیهٔ ۶ / amendment 6 — Stage 2 sandbox runner image.
# A throwaway per-session container that runs the Claude Code CLI with Bash/git
# ENABLED. Isolation comes from HOW the backend launches it (no creds/DB mount,
# read-only rootfs, resource limits, and an egress-allowlist-only network) — NOT
# from disabling tools. See backend/app/sandbox_runner.py and docs/TECH.md §6.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg git openssh-client \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /home/runner --uid 1000 --shell /bin/bash runner

COPY entrypoint.sh /usr/local/bin/sandbox-entrypoint
RUN chmod +x /usr/local/bin/sandbox-entrypoint

USER runner
ENV HOME=/home/runner
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/sandbox-entrypoint"]
