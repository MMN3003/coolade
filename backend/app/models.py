"""SQLAlchemy ORM models mirroring docs/TECH.md section 3 DDL exactly."""
from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


class AuthSource(str, enum.Enum):
    local = "local"
    ldap = "ldap"


class QuotaPeriod(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class UpstreamMode(str, enum.Enum):
    mock = "mock"
    cli_creds = "cli_creds"
    apikey = "apikey"


class MessageStatus(str, enum.Enum):
    """اصلاحیهٔ ۲ / Issue A+C (TECH.md section 3)."""

    complete = "complete"
    streaming = "streaming"
    failed = "failed"


class ThinkingLevel(str, enum.Enum):
    """اصلاحیهٔ ۲ / Issue D (TECH.md section 3, 5.7)."""

    off = "off"
    standard = "standard"
    deep = "deep"


class TeamRole(str, enum.Enum):
    """اصلاحیهٔ ۴ / Issue H (TECH.md section 3). Display/future-only — access
    enforcement is purely "is a member of team_members", never this role."""

    member = "member"
    lead = "lead"


user_role_enum = PgEnum(UserRole, name="user_role", create_type=False)
auth_source_enum = PgEnum(AuthSource, name="auth_source", create_type=False)
quota_period_enum = PgEnum(QuotaPeriod, name="quota_period", create_type=False)
upstream_mode_enum = PgEnum(UpstreamMode, name="upstream_mode", create_type=False)
message_status_enum = PgEnum(MessageStatus, name="message_status", create_type=False)
thinking_level_enum = PgEnum(ThinkingLevel, name="thinking_level", create_type=False)
team_role_enum = PgEnum(TeamRole, name="team_role", create_type=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(user_role_enum, nullable=False, default=UserRole.user)
    auth_source: Mapped[AuthSource] = mapped_column(
        auth_source_enum, nullable=False, default=AuthSource.local
    )
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # v2 — per-user total disk quota across workspaces + chat files (TECH-V2 §2.6). NULL = unlimited.
    disk_quota_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # User Plans / Tiers: the plan this user inherits from (NULL = no plan). Applying
    # a plan rewrites this user's Quota + ModelPolicy rows + max_thinking_level;
    # manual per-user edits afterwards override until the plan is re-applied.
    plan_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plans.id", ondelete="SET NULL")
    )
    # Per-user cap for the web-chat thinking-level picker (NULL = fall back to the
    # global THINKING_MAX_LEVEL env cap). Set from the plan on inheritance.
    max_thinking_level: Mapped[ThinkingLevel | None] = mapped_column(thinking_level_enum)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "auth_source <> 'local' OR password_hash IS NOT NULL", name="chk_local_has_pw"
        ),
        Index("idx_users_active", "is_active"),
    )


class Team(Base):
    """اصلاحیهٔ ۴ / Issue H (TECH.md section 3). Slug is generated once at creation
    (routers/admin_teams.py) and immutable afterwards — it names the on-disk
    directory / symlink target (`/data/teams/<id>/memory`, `./teams/<slug>/`)."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class TeamMember(Base):
    """Many-to-many membership. Sole source of truth for team access — both the
    CLI runner's symlink sync (app/cli_runner.py::sync_team_links) and the
    /api/teams/*, /api/admin/teams/* endpoints read this table, never the
    filesystem, to decide who can reach a team's shared memory (TECH.md 5.4/5.9/11.1)."""

    __tablename__ = "team_members"

    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_in_team: Mapped[TeamRole] = mapped_column(
        team_role_enum, nullable=False, default=TeamRole.member
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_team_members_user", "user_id"),)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    litellm_key_id: Mapped[str | None] = mapped_column(Text)
    # v2 — 'claude_code' (raw relay) | 'flatten' (legacy). TECH-V2 §4.1.
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="claude_code")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_key_hash"),
        Index("idx_api_keys_user", "user_id"),
        Index("idx_api_keys_active", "is_active"),
    )


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    upstream_model: Mapped[str] = mapped_column(String(150), nullable=False)
    input_weight: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    output_weight: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    cache_read_weight: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ModelPolicy(Base):
    __tablename__ = "model_policies"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("models.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Plan(Base):
    """User Plans / Tiers — an admin-defined bundle of quota + allowed models +
    thinking cap. Users pick a plan on create/edit and inherit it (see
    app/services/plans.py::apply_plan_to_user). Editing a plan can be re-applied to
    all its members via POST /api/admin/plans/{id}/apply."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    period: Mapped[QuotaPeriod] = mapped_column(
        quota_period_enum, nullable=False, default=QuotaPeriod.monthly
    )
    limit_credits: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # NULL = no rolling 5h cap (same semantics as Quota.limit_credits_5h).
    limit_credits_5h: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_thinking_level: Mapped[ThinkingLevel] = mapped_column(
        thinking_level_enum, nullable=False, default=ThinkingLevel.standard
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class PlanModel(Base):
    """Which models a plan grants — mirrors ModelPolicy but keyed on plan, not user.
    On inheritance these rows are copied into the user's ModelPolicy rows."""

    __tablename__ = "plan_models"

    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("plans.id", ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("models.id", ondelete="CASCADE"), primary_key=True
    )


class Quota(Base):
    __tablename__ = "quotas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period: Mapped[QuotaPeriod] = mapped_column(
        quota_period_enum, nullable=False, default=QuotaPeriod.weekly
    )
    limit_credits: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    period_start: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    bonus_credits: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    # اصلاحیهٔ ۳ / Issue E: rolling 5h cap. NULL/0 = unlimited (not enforced).
    # Rolling window, no period_start/bonus semantics — usage is computed live from
    # usage_ledger over [now - ROLLING_WINDOW_HOURS, now] (TECH.md 5.8).
    limit_credits_5h: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", name="uq_quota_user"),)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    api_key_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("models.id"), nullable=False)
    surface: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_ledger_user_time", "user_id", "created_at"),
        Index("idx_ledger_key", "api_key_id"),
        Index("idx_ledger_model_time", "model_id", "created_at"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="گفتگوی جدید")
    model_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("models.id"))
    cli_session_id: Mapped[str | None] = mapped_column(Text)
    # Issue D: per-conversation default thinking level; each message may override it.
    thinking_level: Mapped[ThinkingLevel] = mapped_column(
        thinking_level_enum, nullable=False, default=ThinkingLevel.standard
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_blocks: Mapped[dict | None] = mapped_column(JSONB)
    # Issue A: assistant rows are created with status='streaming' the instant a turn
    # is accepted; 'complete'/'failed' land at FINALIZE (TECH.md section 5.1).
    status: Mapped[MessageStatus] = mapped_column(
        message_status_enum, nullable=False, default=MessageStatus.complete
    )
    # Issue C: only populated for status='failed'; cleared on retry.
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_reason: Mapped[str | None] = mapped_column(Text)
    # Issue D: the effective thinking level actually used for this turn (badge source).
    thinking_level: Mapped[ThinkingLevel | None] = mapped_column(thinking_level_enum)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_msg_conv", "conversation_id", "created_at"),
        Index(
            "idx_msg_streaming",
            "status",
            postgresql_where=text("status = 'streaming'"),
        ),
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_attach_conv", "conversation_id"),)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    target_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_audit_time", "created_at"),
        Index("idx_audit_action", "action", "created_at"),
    )


class UpstreamAccountLimit(Base):
    """اصلاحیهٔ ۳ / Issue F (TECH.md section 3, 4.5).

    State of the upstream account's OWN rate-limit windows, extracted from the
    `anthropic-ratelimit-*` response headers seen on the passthrough path (plus an
    optional periodic probe). One row per window the upstream service discloses
    (e.g. '5h', 'weekly', 'unified', or whatever it actually names its headers —
    we never assume exact names, TECH.md 4.5). State only (not a time series);
    upsert keyed by window_key. If upstream never sends such headers this table
    simply stays empty — no fabricated numbers (TECH.md's "honest design").
    """

    __tablename__ = "upstream_account_limits"

    window_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    remaining_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    reset_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    unit: Mapped[str | None] = mapped_column(String(30))
    raw_headers: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # 'passthrough' | 'probe'
    last_updated: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    upstream_request_id: Mapped[str | None] = mapped_column(String(100))


class Workspace(Base):
    """v2 — persistent per-(user × repo) coding workspace (TECH-V2 §2/§4.2).

    A workspace = an isolated Docker volume + a stop/start-able container that hosts
    code-server + the Claude Code extension. `status` tracks the lifecycle
    (provisioning→running→stopped→…); the container/volume names are derived from id.
    `kind='personal'` workspaces have no repo (general-chat shell).
    """

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="repo")  # repo | personal
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="provisioning")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    repo_url: Mapped[str | None] = mapped_column(Text)
    base_branch: Mapped[str | None] = mapped_column(String(200))
    work_branch: Mapped[str | None] = mapped_column(String(200))
    container_name: Mapped[str | None] = mapped_column(String(120))
    volume_name: Mapped[str | None] = mapped_column(String(120))
    # sha256 of the per-workspace gateway key injected into the container as
    # ANTHROPIC_AUTH_TOKEN; the raw relay authenticates model calls against this (D2.4).
    gateway_key_hash: Mapped[str | None] = mapped_column(Text)
    disk_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_activity_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_ws_user", "user_id"), Index("idx_ws_status", "status"))


class GitlabToken(Base):
    """v2 — a developer's own GitLab PAT (TECH-V2 §4.3). Stored Fernet-encrypted;
    used only to clone/push inside that user's own workspace sandbox."""

    __tablename__ = "gitlab_tokens"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    gitlab_host: Mapped[str] = mapped_column(String(200), nullable=False, default="git.ecobin.ir")
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )


class ServiceKind(str, enum.Enum):
    sql = "sql"
    files = "files"
    http = "http"


class GrantLevel(str, enum.Enum):
    read = "read"
    write = "write"


service_kind_enum = PgEnum(ServiceKind, name="service_kind", create_type=False)
grant_level_enum = PgEnum(GrantLevel, name="grant_level", create_type=False)


class Service(Base):
    """Amendment-1 (docs/SERVICES-V2.md §ب-۶) — an organizational service:
    a grantable bundle of (published skill package, connector, access contract).
    Connector credentials live ONLY here, Fernet-encrypted; they are decrypted
    solely inside the MCP gateway at call time and never enter a workspace
    container (mirror of the D2.4 upstream-token rule)."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)  # [a-z0-9-]
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[ServiceKind] = mapped_column(service_kind_enum, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Non-secret connector config (display host, limit overrides, path/method allowlist).
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    conn_read_enc: Mapped[str] = mapped_column(Text, nullable=False)
    conn_write_enc: Mapped[str | None] = mapped_column(Text)  # stays NULL until P5b
    skill_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ServiceGrant(Base):
    """Per-user access level to a service. No row = no access (default);
    the gateway re-reads this on EVERY tool call so revocation is immediate."""

    __tablename__ = "service_grants"
    __table_args__ = (UniqueConstraint("service_id", "user_id", name="uq_grant"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[GrantLevel] = mapped_column(grant_level_enum, nullable=False)
    granted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ServiceAudit(Base):
    """One row per gateway tool call. Privacy contract (SV7): read calls store
    only a params digest, never the full text; approved mutations (P5b) are the
    sole exception and live in service_mutations."""

    __tablename__ = "service_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workspaces.id", ondelete="SET NULL")
    )
    tool: Mapped[str] = mapped_column(String(80), nullable=False)
    level_used: Mapped[GrantLevel] = mapped_column(grant_level_enum, nullable=False)
    params_digest: Mapped[str | None] = mapped_column(String(64))  # sha256 hex
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    result_rows: Mapped[int | None] = mapped_column(Integer)  # rows for sql, bytes for files
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
