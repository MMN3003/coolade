"""initial schema — docs/TECH.md section 3 (v1.1, amendment 1)

Revision ID: 0001
Revises:
Create Date: 2026-08-20

"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


DDL_UP = """
CREATE TYPE user_role   AS ENUM ('admin', 'user');
CREATE TYPE auth_source AS ENUM ('local', 'ldap');
CREATE TYPE quota_period AS ENUM ('daily', 'weekly', 'monthly');
CREATE TYPE upstream_mode AS ENUM ('mock', 'cli_creds', 'apikey');

CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(150) NOT NULL UNIQUE,
    display_name    VARCHAR(255),
    email           VARCHAR(255),
    role            user_role   NOT NULL DEFAULT 'user',
    auth_source     auth_source NOT NULL DEFAULT 'local',
    password_hash   TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_local_has_pw
        CHECK (auth_source <> 'local' OR password_hash IS NOT NULL)
);
CREATE INDEX idx_users_active ON users(is_active);

CREATE TABLE api_keys (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                VARCHAR(255) NOT NULL,
    key_prefix          VARCHAR(16)  NOT NULL,
    key_hash            TEXT NOT NULL,
    litellm_key_id      TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at          TIMESTAMPTZ,
    CONSTRAINT uq_key_hash UNIQUE (key_hash)
);
CREATE INDEX idx_api_keys_user   ON api_keys(user_id);
CREATE INDEX idx_api_keys_active ON api_keys(is_active);

CREATE TABLE models (
    id                  BIGSERIAL PRIMARY KEY,
    model_key           VARCHAR(100) NOT NULL UNIQUE,
    display_name        VARCHAR(150) NOT NULL,
    upstream_model      VARCHAR(150) NOT NULL,
    input_weight        NUMERIC(10,4) NOT NULL,
    output_weight       NUMERIC(10,4) NOT NULL,
    cache_read_weight   NUMERIC(10,4) NOT NULL,
    is_enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order          INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE model_policies (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id    BIGINT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, model_id)
);

CREATE TABLE quotas (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period          quota_period NOT NULL DEFAULT 'weekly',
    limit_credits   NUMERIC(14,2) NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL DEFAULT now(),
    bonus_credits   NUMERIC(14,2) NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_quota_user UNIQUE (user_id)
);

CREATE TABLE usage_ledger (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    api_key_id          BIGINT REFERENCES api_keys(id) ON DELETE SET NULL,
    model_id            BIGINT NOT NULL REFERENCES models(id),
    surface             VARCHAR(20) NOT NULL,
    input_tokens        INT NOT NULL DEFAULT 0,
    output_tokens       INT NOT NULL DEFAULT 0,
    cache_read_tokens   INT NOT NULL DEFAULT 0,
    cache_write_tokens  INT NOT NULL DEFAULT 0,
    credits             NUMERIC(14,4) NOT NULL,
    request_id          VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ledger_user_time  ON usage_ledger(user_id, created_at);
CREATE INDEX idx_ledger_key        ON usage_ledger(api_key_id);
CREATE INDEX idx_ledger_model_time ON usage_ledger(model_id, created_at);

CREATE TABLE conversations (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(300) NOT NULL DEFAULT 'گفتگوی جدید',
    model_id        BIGINT REFERENCES models(id),
    cli_session_id  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    content_blocks  JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at);

CREATE TABLE attachments (
    id              BIGSERIAL PRIMARY KEY,
    message_id      BIGINT REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    filename        VARCHAR(500) NOT NULL,
    mime_type       VARCHAR(150) NOT NULL,
    size_bytes      BIGINT NOT NULL,
    storage_path    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_attach_conv ON attachments(conversation_id);

CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    target_id   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(80) NOT NULL,
    detail      JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_time   ON audit_log(created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);

CREATE TABLE settings (
    key             VARCHAR(120) PRIMARY KEY,
    value           TEXT,
    is_encrypted    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      BIGINT REFERENCES users(id) ON DELETE SET NULL
);
"""

DDL_DOWN = """
DROP TABLE IF EXISTS settings;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS attachments;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS conversations;
DROP TABLE IF EXISTS usage_ledger;
DROP TABLE IF EXISTS quotas;
DROP TABLE IF EXISTS model_policies;
DROP TABLE IF EXISTS models;
DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS users;
DROP TYPE IF EXISTS upstream_mode;
DROP TYPE IF EXISTS quota_period;
DROP TYPE IF EXISTS auth_source;
DROP TYPE IF EXISTS user_role;
"""


def _split_statements(sql: str) -> list[str]:
    # asyncpg's prepared-statement execute() cannot run multiple commands at once,
    # so each top-level statement must be sent separately. Our DDL has no semicolons
    # inside string literals, so a plain split is safe here.
    return [s.strip() for s in sql.split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _split_statements(DDL_UP):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _split_statements(DDL_DOWN):
        op.execute(stmt)
