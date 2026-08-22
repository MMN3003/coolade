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
