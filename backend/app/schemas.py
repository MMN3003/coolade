"""Pydantic request/response models — the contract behind docs/openapi.json."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class MeQuotaSummary(BaseModel):
    period: str
    limit_credits: Decimal
    bonus_credits: Decimal
    used_credits: Decimal
    period_start: datetime.datetime


class MeTeamOut(BaseModel):
    """اصلاحیهٔ ۴ / Issue H — TECH.md 8: `/api/auth/me` teams field."""

    id: int
    name: str
    slug: str
    role_in_team: str


class MeResponse(BaseModel):
    id: int
    username: str
    display_name: str | None
    email: str | None
    role: str
    auth_source: str
    allowed_models: list[str]
    quota: MeQuotaSummary | None
    max_thinking_level: str  # Issue D — caps the web chat thinking-level picker
    teams: list[MeTeamOut] = []  # اصلاحیهٔ ۴ / Issue H


# ---------- Conversations ----------
ThinkingLevelLiteral = Literal["off", "standard", "deep"]


class ConversationCreate(BaseModel):
    title: str | None = None
    model_key: str


class ConversationUpdate(BaseModel):
    title: str | None = None
    model_key: str | None = None
    thinking_level: ThinkingLevelLiteral | None = None  # Issue D — per-conversation default


class ConversationOut(ORMModel):
    id: int
    title: str
    model_key: str | None = None
    thinking_level: str
    generating: bool  # Issue A — sidebar spinner source (id in TurnRegistry)
    created_at: datetime.datetime
    updated_at: datetime.datetime


class MessageOut(ORMModel):
    id: int
    role: str
    content: str
    content_blocks: dict | None = None
    status: str  # Issue A/C — complete | streaming | failed
    error_code: str | None = None
    error_reason: str | None = None
    thinking_level: str | None = None  # Issue D — effective level used (badge source)
    created_at: datetime.datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []


class SendMessageRequest(BaseModel):
    content: str
    thinking_level: ThinkingLevelLiteral | None = None  # Issue D — optional override, sticky


class TurnAcceptedOut(BaseModel):
    """202 body for POST messages and POST .../retry (Issue A/C)."""

    assistant_message_id: int
    generating: bool = True
    thinking_level: str


# ---------- API keys ----------
class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiKeyOut(ORMModel):
    id: int
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime.datetime | None
    created_at: datetime.datetime


class ApiKeyCreatedOut(ApiKeyOut):
    key: str


# ---------- Usage ----------
class UsageByModel(BaseModel):
    model_key: str
    credits: Decimal


class UsageByKey(BaseModel):
    api_key_id: int | None
    name: str
    credits: Decimal


class UsageDailyPoint(BaseModel):
    date: datetime.date
    credits: Decimal


class MyUsageResponse(BaseModel):
    period: str
    period_start: datetime.datetime
    limit_credits: Decimal
    bonus_credits: Decimal
    used_credits: Decimal
    by_model: list[UsageByModel]
    by_key: list[UsageByKey]
    daily: list[UsageDailyPoint]
    # اصلاحیهٔ ۳ / Issue E — rolling 5h block, alongside the weekly one above.
    used_5h: Decimal
    limit_credits_5h: Decimal | None = None
    reset_5h_at: datetime.datetime | None = None


class UserUsageRow(BaseModel):
    user_id: int
    username: str
    credits: Decimal


class AdminUsageResponse(BaseModel):
    total_credits: Decimal
    by_user: list[UserUsageRow]
    by_model: list[UsageByModel]
    daily: list[UsageDailyPoint]


# ---------- Admin: per-user usage report (اصلاحیهٔ ۳ / Issue G) ----------
class WeeklyQuotaBlock(BaseModel):
    used: Decimal
    limit: Decimal
    bonus: Decimal
    period: str
    period_start: datetime.datetime
    reset_at: datetime.datetime


class FiveHourQuotaBlock(BaseModel):
    used_5h: Decimal
    limit_credits_5h: Decimal | None = None
    reset_5h_at: datetime.datetime | None = None


class AdminUserUsageResponse(BaseModel):
    """GET /api/admin/users/{id}/usage — same shape as "مصرف من" (MyUsageResponse)
    plus admin-only metadata, but reads ONLY usage_ledger/quotas — never
    messages/conversations.title/attachments (TECH.md 11.1 privacy rule)."""

    user_id: int
    username: str
    by_model: list[UsageByModel]
    by_key: list[UsageByKey]
    daily: list[UsageDailyPoint]
    weekly: WeeklyQuotaBlock
    five_hour: FiveHourQuotaBlock


# ---------- Admin: users ----------
class UserCreate(BaseModel):
    username: str
    display_name: str | None = None
    email: EmailStr | None = None
    role: Literal["admin", "user"] = "user"
    auth_source: Literal["local", "ldap"] = "local"
    password: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None
    password: str | None = None


class UserOut(ORMModel):
    id: int
    username: str
    display_name: str | None
    email: str | None
    role: str
    auth_source: str
    is_active: bool
    created_at: datetime.datetime


class QuotaOut(BaseModel):
    period: str
    limit_credits: Decimal
    bonus_credits: Decimal
    period_start: datetime.datetime
    # اصلاحیهٔ ۳ / Issue E
    limit_credits_5h: Decimal | None = None


class UserDetailOut(UserOut):
    allowed_models: list[str]
    quota: QuotaOut | None


# ---------- Admin: policy / quota ----------
class PolicySetRequest(BaseModel):
    model_keys: list[str]


class QuotaSetRequest(BaseModel):
    period: Literal["daily", "weekly", "monthly"]
    limit_credits: Decimal
    # اصلاحیهٔ ۳ / Issue E — NULL/absent/0 = unlimited (not enforced).
    limit_credits_5h: Decimal | None = None


class QuotaBonusRequest(BaseModel):
    bonus_credits: Decimal


# ---------- Admin: models ----------
class ModelCreate(BaseModel):
    model_key: str
    display_name: str
    upstream_model: str
    input_weight: Decimal
    output_weight: Decimal
    cache_read_weight: Decimal
    sort_order: int = 0


class ModelUpdate(BaseModel):
    display_name: str | None = None
    upstream_model: str | None = None
    input_weight: Decimal | None = None
    output_weight: Decimal | None = None
    cache_read_weight: Decimal | None = None
    is_enabled: bool | None = None
    sort_order: int | None = None


class ModelOut(ORMModel):
    id: int
    model_key: str
    display_name: str
    upstream_model: str
    input_weight: Decimal
    output_weight: Decimal
    cache_read_weight: Decimal
    is_enabled: bool
    sort_order: int


# ---------- Admin: audit ----------
class AuditLogOut(BaseModel):
    id: int
    actor_id: int | None
    actor_username: str | None = None
    target_id: int | None
    target_username: str | None = None
    action: str
    detail: dict | None
    ip_address: str | None
    created_at: datetime.datetime


# ---------- Admin: upstream ----------
class LastRefreshOut(BaseModel):
    at: str
    ok: bool
    error: str | None = None


class UpstreamStatusOut(BaseModel):
    mode: str
    connected: bool
    expires_at: datetime.datetime | None = None
    # Issue B: most upstream services don't report refresh-token expiry — null/"نامشخص" in UI.
    refresh_token_valid_until: datetime.datetime | None = None
    expiring_soon: bool = False
    last_refresh: LastRefreshOut | None = None
    auto_refresh: Literal["active", "degraded", "failed"] | None = None
    creds_source: str | None = None
    base_url: str
    last_synced: datetime.datetime | None = None
    last_checked: datetime.datetime


# ---------- Admin: upstream account limits (اصلاحیهٔ ۳ / Issue F) ----------
class AccountLimitWindow(BaseModel):
    key: str
    limit: Decimal | None = None
    remaining: Decimal | None = None
    reset: datetime.datetime | None = None
    unit: str | None = None
    last_updated: datetime.datetime
    stale: bool


class AccountLimitsOut(BaseModel):
    available: bool
    windows: list[AccountLimitWindow]
    tier: str | None = None
    subscription: str | None = None


class ApiKeySetRequest(BaseModel):
    api_key: str


class ModeSetRequest(BaseModel):
    mode: Literal["mock", "cli_creds", "apikey"]


# ---------- Workspace files ----------
class WorkspaceFileOut(BaseModel):
    file_id: str
    name: str
    relpath: str
    size_bytes: int
    modified_at: datetime.datetime


# ---------- Teams (اصلاحیهٔ ۴ / Issue H+I) ----------
TeamRoleLiteral = Literal["member", "lead"]


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str | None = None  # generated from name if absent; uniquified either way
    description: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    # slug is intentionally NOT editable here — immutable after creation (TECH.md 8).


class TeamMemberAdd(BaseModel):
    user_id: int
    role_in_team: TeamRoleLiteral = "member"


class TeamMemberOut(BaseModel):
    user_id: int
    username: str
    display_name: str | None
    role_in_team: str
    created_at: datetime.datetime


class TeamOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    member_count: int
    created_at: datetime.datetime


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut] = []


class TeamMineOut(BaseModel):
    """GET /api/teams/mine — read-only "تیم‌های من" view (TECH.md 8)."""

    id: int
    name: str
    slug: str
    role_in_team: str
    member_count: int


# ---------- Health ----------
class HealthOut(BaseModel):
    status: str
    db: bool
    litellm: bool
    upstream_mode: str
    upstream_connected: bool
    cli_available: bool


# ---------- generic ----------
class OkResponse(BaseModel):
    ok: bool = True


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
