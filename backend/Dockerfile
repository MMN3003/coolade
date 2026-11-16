FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Node 20 + Claude Code CLI, installed in-image (not host-mounted) so we control the
# glibc/runtime version (TECH.md section 1 "CLI runner").
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# v2 — docker CLI so the backend can orchestrate workspace containers (TECH-V2 §6).
# Only needed for VS Code workspaces / sandbox. Build with INSTALL_DOCKER_CLI=0 to skip it
# (smaller image, and no dependency on download.docker.com being reachable).
ARG INSTALL_DOCKER_CLI=1
RUN if [ "$INSTALL_DOCKER_CLI" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends gnupg \
        && install -m 0755 -d /etc/apt/keyrings \
        && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
        && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
        && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
        && apt-get purge -y gnupg && apt-get autoremove -y \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN useradd --create-home --home-dir /home/app --uid 1000 --shell /bin/bash app

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x /app/bin/mock-claude

# /data/teams (اصلاحیهٔ ۴ / Issue I) must exist app-owned in the image so the fresh
# teams_data named volume inherits app:app ownership on first mount — same mechanism
# as /data/users (otherwise Docker creates the empty volume's mountpoint as root and
# the app user can't mkdir /data/teams/<id>).
RUN mkdir -p /data/attachments /data/users /data/teams /home/app/.claude \
    && chown -R app:app /app /data /home/app

USER app
ENV HOME=/home/app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
