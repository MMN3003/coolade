"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ecocode_env: str = "dev"
    upstream_mode: str = "mock"  # mock | cli_creds | apikey
    upstream_base_url: str = "https://claude-compat.example.com"

    # --- OAuth refresh (Issue B, TECH.md 4.1) ---
    upstream_oauth_token_url: str = ""  # empty -> default f"{upstream_base_url}/v1/oauth/token"
    upstream_oauth_client_id: str = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code's own client_id

    # --- thinking level (Issue D, TECH.md 5.7) ---
    thinking_max_level: str = "deep"  # global cap: off | standard | deep

    # --- اصلاحیهٔ ۳ / Issue E: rolling 5h window ---
    rolling_window_hours: float = 5.0

    # --- اصلاحیهٔ ۳ / Issue F: optional periodic upstream-limit probe ---
    upstream_limit_probe_enabled: bool = False
    upstream_limit_probe_interval: int = 900

    ecocode_secret_key: str = "0" * 44  # Fernet key (base64, 32 bytes) - override in prod
    session_secret: str = "dev-insecure-session-secret-change-me"

    postgres_password: str = "postgres"
    ecocode_database_url: str = (
        "postgresql+asyncpg://ecocode:ecocode@postgres:5432/ecocode"
    )
    litellm_database_url: str = "postgresql://litellm:litellm@postgres:5432/litellm"

    litellm_master_key: str = "sk-master-dev"
    litellm_base_url: str = "http://litellm:4000"

    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = ""

    ldap_enabled: bool = False
    ldap_uri: str = ""
    ldap_base_dn: str = ""
    ldap_bind_template: str = ""

    # --- CLI runner (TECH.md section 4/5) ---
    claude_creds_dir: str = "/host_claude"  # mount point of the host ~/.claude dir (:ro)
    cli_home: str = "/home/app"  # container HOME; CLI reads ~/.claude/.credentials.json from here
    cli_max_concurrency: int = 4
    cli_timeout_seconds: int = 300
    mock_cli: bool = False
    workspace_root: str = "/data/users"
    # اصلاحیهٔ ۴ / Issue H+I: /data/teams/<team_id>/memory (TECH.md section 2/3/5.9)
    teams_root: str = "/data/teams"

    # --- اصلاحیهٔ ۶ / amendment 6: Stage-2 isolated sandbox runner (Bash/git) ---
    # OFF by default. Enabling requires the egress allowlist proxy to be up (the
    # runner refuses to launch without it — see app/sandbox_runner.py).
    sandbox_enabled: bool = False
    sandbox_image: str = "ecocode-runner:latest"
    sandbox_network: str = "ecocode_sandbox_net"
    sandbox_memory: str = "1g"
    sandbox_cpus: str = "1"
    sandbox_pids_limit: int = 256
    sandbox_timeout_seconds: int = 300
    sandbox_max_concurrency: int = 2
    egress_proxy_url: str = "http://egress:8080"
    # git push target (parametric, disabled until provided): e.g. https://git.ecobin.ir/
    git_remote_base: str = ""

    # --- v2 — persistent workspaces (TECH-V2 §2/§6) ---
    workspace_image: str = "eco-ide-spike-code-server:latest"
    workspace_network: str = "ecocode_sandbox_net"
    workspace_memory: str = "2g"
    workspace_cpus: str = "2"
    workspace_pids_limit: int = 512
    workspace_idle_minutes: int = 30
    workspace_max_running: int = 4
    workspace_retention_days: int = 30      # GC abandoned stopped workspaces after this
    workspace_reaper_minutes: int = 1       # how often the reaper runs (idle-stop/GC/disk)
    workspace_volume_prefix: str = "ecows"
    # the in-workspace agent's ANTHROPIC_BASE_URL points at the backend raw relay (D2.4);
    # the relay then forwards to the real upstream below.
    workspace_relay_url: str = "http://backend:8000/relay"
    # where the relay FORWARDS to (real upstream). empty -> falls back to upstream_base_url;
    # in mock mode set to http://mock-upstream:8080.
    workspace_upstream_base_url: str = ""
    # only route workspace egress through the allowlist proxy when it's actually deployed
    # (production/sandbox profile). Off for plain dev so the container can reach the relay.
    workspace_egress_enabled: bool = False

    # --- amendment-1: organizational services / MCP gateway (docs/SERVICES-V2.md SV9) ---
    service_rate_per_min: int = 30      # gateway tool calls per user per minute
    # Max rows per run_query. Every returned row lands in the model's context
    # FOREVER (it rides along every later turn of that conversation as cache
    # writes/reads) — so the default is deliberately small; reports should
    # aggregate in SQL. Per-service override: services.config["row_limit"].
    service_sql_row_limit: int = 200
    service_sql_timeout_s: int = 15     # per-query statement timeout
    service_file_max_mb: int = 5        # max read_file size (files connector)
    service_http_timeout_s: int = 15    # http connector GET timeout
    services_root: str = "/data/services"        # published skill packages (volume)
    # gateway URL as seen by the IN-PROCESS chat CLI (same container as backend)
    service_gateway_base: str = "http://127.0.0.1:8000/mcp/svc"
    # Token economy: past this many credits in one conversation, the UI suggests
    # starting a fresh (cheaper) one. 0 disables the nudge.
    chat_cost_nudge_credits: int = 2000
    gitlab_default_host: str = "git.ecobin.ir"

    # --- amendment-7: knowledge layer (docs/KNOWLEDGE.md) ---
    # user+team rules/knowledge pack inlined into the system prompt while under
    # this many chars; knowledge beyond it spills to <ws>/.ecocode/knowledge/*.md.
    knowledge_inline_max_chars: int = 6000
    # Learning from chats: a scheduler job digests idle conversations with new
    # messages into per-user `learned` knowledge entries (users may opt out).
    learning_enabled: bool = True
    learning_interval_minutes: int = 15
    learning_idle_minutes: int = 10          # conversation must be quiet this long first
    learning_min_new_user_messages: int = 2   # …and have at least this many new user turns
    learning_max_conversations_per_run: int = 6
    learning_max_entries_per_user: int = 80   # cap on learned rows per user
    learning_model_key: str = ""              # empty -> cheapest enabled model
    # Team learning: every N hours, members' new chat messages are digested into
    # the TEAM's shared knowledge (scope team, source learned) — terminology,
    # processes, standing rules — never personal preferences.
    team_learning_enabled: bool = True
    team_learning_interval_hours: int = 6
    team_learning_min_new_messages: int = 8    # new user messages across the team
    team_learning_max_entries: int = 80        # cap on learned rows per team

    admin_username: str = "admin"
    admin_password: str = "changeme123"
    admin_email: str = ""

    attachments_dir: str = "/data/attachments"
    max_upload_bytes: int = 20 * 1024 * 1024

    cors_origins: str = ""

    @property
    def session_cookie_name(self) -> str:
        return "ecocode_session"

    @property
    def session_max_age_seconds(self) -> int:
        return 8 * 60 * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
