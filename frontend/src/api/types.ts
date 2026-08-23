/**
 * TypeScript types for the EcoCode backend REST contract.
 *
 * Source of truth: docs/openapi.json (exported by Dev1's FastAPI backend).
 * Reconciled against it on 2026-08-20 after integration; also validated with
 * read-only curls against the live stack.
 *
 * Conventions of the real contract worth remembering:
 *  - List endpoints return BARE ARRAYS (no pagination envelope). Paging is
 *    `limit`/`offset` query params where supported (conversations, audit).
 *  - All decimal money-like fields (credits, weights) are DECIMAL STRINGS on
 *    the wire (e.g. "28.2660"). Wire types below use `DecimalString`; the API
 *    client (endpoints.ts) converts them to numbers at the boundary, exposing
 *    the parsed `…` app types to components.
 *  - POST /api/auth/login returns {ok:true} and sets the cookie; the user
 *    object comes from a follow-up GET /api/auth/me.
 *
 * ---------------------------------------------------------------------------
 * اصلاحیهٔ ۲ (docs/TECH.md v1.2) — reconciled against openapi.json 1.2.0.
 * ---------------------------------------------------------------------------
 * اصلاحیهٔ ۳ (docs/TECH.md v1.3, Issues E/F/G) — NOT YET frozen in openapi.json
 * (still 1.2.0 on disk: no 5h fields, no account-limits, no per-user usage
 * endpoint). Dev1 is implementing the backend in parallel on the same
 * working tree; the shapes below were aligned against Dev1's in-progress
 * (uncommitted) `backend/app/schemas.py` / `routers/admin_users.py` /
 * `routers/admin_upstream.py` / `services/{quota,account_limits}.py` at the
 * time this was written, NOT just TECH.md prose — so field names should be
 * close, but this is still pre-freeze and MUST be re-verified once Dev1
 * regenerates openapi.json:
 *  - `GET /api/usage/me` / `PUT .../quota`: flat `used_5h` / `limit_credits_5h`
 *    / `reset_5h_at` (mirrors `quotas.limit_credits_5h` 1:1) — confirmed.
 *  - `GET /api/admin/upstream/account-limits`: window items use `key`
 *    (not `window`) and `reset` (not `reset_at`) — confirmed against
 *    `services/account_limits.py#get_account_limits_view`.
 *  - `GET /api/admin/users/{id}/usage`: NOT a flat superset of
 *    `UsageMeResponse` — nests `weekly: {used, limit, bonus, period,
 *    period_start, reset_at}` and `five_hour: {used_5h, limit_credits_5h,
 *    reset_5h_at}` — confirmed against `schemas.py#AdminUserUsageResponse`.
 *  - 429 error bodies for `quota_exceeded`/`quota_exceeded_5h` put
 *    `reset_at`/`reset_5h_at` NESTED inside `error` (confirmed against
 *    `errors.py#AppError.extra` / `app_error_handler`), not top-level;
 *    `client.ts#parseErrorBody` still defensively checks both.
 * ---------------------------------------------------------------------------
 */

// ---------- shared ----------

export type UserRole = 'admin' | 'user';
export type AuthSource = 'local' | 'ldap';
export type QuotaPeriod = 'daily' | 'weekly' | 'monthly';
export type UpstreamMode = 'mock' | 'cli_creds' | 'apikey';
export type Surface = 'web_chat' | 'api';
export type MessageRole = 'user' | 'assistant';

/** اصلاحیهٔ ۲ / Issue A — messages.status (TECH.md §3). */
export type MessageStatus = 'complete' | 'streaming' | 'failed';

/** اصلاحیهٔ ۲ / Issue D — thinking_level enum (TECH.md §3, §5.7). Order: off < standard < deep. */
export type ThinkingLevel = 'off' | 'standard' | 'deep';

/** اصلاحیهٔ ۲ / Issue B — auto_refresh state of the upstream TokenManager (TECH.md §4.1). */
export type AutoRefreshState = 'active' | 'degraded' | 'failed';

/** Decimal serialized as string on the wire, e.g. "0.00", "28.2660". */
export type DecimalString = string;

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
  /**
   * اصلاحیهٔ ۳ / Issue E (TECH.md §5.8, §8): 429 bodies for `quota_exceeded` /
   * `quota_exceeded_5h` carry the reset time so the client can show "تا آزاد
   * شدن پنجره صبر کنید". Confirmed (against Dev1's in-progress `errors.py`)
   * to be nested inside `error` (`error.reset_at`/`error.reset_5h_at`), not
   * top-level; kept here too as a defensive fallback in `client.ts`.
   */
  reset_at?: string | null;
  reset_5h_at?: string | null;
}

export interface OkResponse {
  ok: boolean;
}

// ---------- auth ----------

export interface LoginRequest {
  username: string;
  password: string;
}

/** Wire shape of MeResponse.quota (MeQuotaSummary in openapi.json). */
export interface QuotaSummaryWire {
  period: QuotaPeriod;
  limit_credits: DecimalString;
  bonus_credits: DecimalString;
  used_credits: DecimalString;
  period_start: string; // ISO datetime
}

/** Parsed app-side quota summary (credits as numbers). */
export interface QuotaSummary {
  period: QuotaPeriod;
  limit_credits: number;
  bonus_credits: number;
  used_credits: number;
  period_start: string;
}

export interface MeResponseWire {
  id: number;
  username: string;
  display_name: string | null;
  email: string | null;
  role: UserRole;
  auth_source: AuthSource;
  /** Model KEYS the user may use (bare strings, not objects). */
  allowed_models: string[];
  quota: QuotaSummaryWire | null;
  /**
   * اصلاحیهٔ ۲ / Issue D (TECH.md §8, §5.7): effective cap for this user
   * (min of THINKING_MAX_LEVEL env + optional per-user/policy cap). The
   * thinking-level picker must never offer a level above this.
   */
  max_thinking_level: ThinkingLevel;
  /**
   * اصلاحیهٔ ۴ / Issue H (TECH.md §8): "`/api/auth/me` ... +
   * teams: [{id, name, slug, role_in_team}]". Confirmed against Dev1's
   * `schemas.py#MeResponse.teams` / `MeTeamOut` (default `[]` server-side
   * too). Kept optional here defensively until `docs/openapi.json` is
   * regenerated and this is frozen; `parseMe` below defaults it to `[]`.
   */
  teams?: MeTeam[];
}

export interface MeResponse extends Omit<MeResponseWire, 'quota' | 'teams'> {
  quota: QuotaSummary | null;
  /** Always resolved to an array by `parseMe` (see MeResponseWire.teams note). */
  teams: MeTeam[];
}

// ---------- conversations / chat ----------

export interface Conversation {
  id: number;
  title: string;
  model_key: string | null;
  created_at: string;
  updated_at: string;
  /** اصلاحیهٔ ۲ / Issue A (TECH.md §5.1, §8): true iff a turn is active in the in-memory TurnRegistry. */
  generating: boolean;
  /** اصلاحیهٔ ۲ / Issue D — this conversation's sticky default thinking level. */
  thinking_level: ThinkingLevel;
}

export interface Message {
  id: number;
  role: MessageRole;
  content: string;
  /** e.g. {tool_uses: [...]} — structural CLI events; shape is backend-internal. */
  content_blocks?: Record<string, unknown> | null;
  created_at: string;
  /** اصلاحیهٔ ۲ / Issue A — 'streaming' from the moment a turn is accepted until 'complete'/'failed'. */
  status: MessageStatus;
  /** اصلاحیهٔ ۲ / Issue C — only set when status='failed'. */
  error_code?: string | null;
  error_reason?: string | null;
  /** اصلاحیهٔ ۲ / Issue D — effective thinking level used for this assistant turn; null/absent for user rows. */
  thinking_level?: ThinkingLevel | null;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface CreateConversationRequest {
  title?: string;
  model_key: string;
}

export interface UpdateConversationRequest {
  title?: string;
  model_key?: string;
  /** اصلاحیهٔ ۲ / Issue D — updates the conversation's sticky default (TECH.md §8, §9). */
  thinking_level?: ThinkingLevel;
}

/**
 * POST …/messages body (اصلاحیهٔ ۲ / TECH.md §8). `thinking_level` is optional —
 * omission means "use the conversation's current default".
 */
export interface SendMessageRequest {
  content: string;
  thinking_level?: ThinkingLevel;
}

/**
 * اصلاحیهٔ ۲ / Issue A: POST …/messages and POST …/retry now return 202, not
 * an inline SSE stream (TECH.md §5.1, §8). The actual streamed reply is
 * always consumed separately via GET …/stream.
 */
export interface SendMessageAccepted {
  assistant_message_id: number;
  generating: true;
  /** Effective level for this turn (TECH.md §8's example includes it on the send response). */
  thinking_level?: ThinkingLevel;
}

/** Response of POST /api/conversations/{id}/attachments. */
export interface AttachmentUploadResponse {
  id: number;
  filename: string;
  size_bytes: number;
}

/**
 * اصلاحیهٔ ۲ — SSE events from GET /api/conversations/{id}/stream (TECH.md §5.3, §8).
 * `POST …/messages` no longer streams inline; every send/retry is followed by
 * opening this endpoint, which replays the whole turn's buffered events from
 * the start (including `start`) and then follows live until `done`/`error`.
 * When no turn is active it emits a single `idle` event and closes.
 */
export type ChatStreamEvent =
  | { type: 'start'; conversation_id: number }
  | { type: 'delta'; text: string }
  | { type: 'tool'; name: string; summary: string }
  | { type: 'done'; credits_used: DecimalString; files_changed: string[]; thinking_level?: ThinkingLevel }
  | { type: 'error'; message: string; code?: string }
  | { type: 'idle' };

// ---------- workspace files (F4.6) ----------

export interface WorkspaceFile {
  file_id: string;
  name: string;
  relpath: string;
  size_bytes: number;
  modified_at: string;
}

// ---------- teams + team shared memory (اصلاحیهٔ ۴ / Issue H+I) ----------
//
// NOT YET in openapi.json (still 1.3.0 on disk — no /api/teams*,
// /api/admin/teams* paths in it yet). `backend/` had no team files at all
// when this section was first drafted (built purely from TECH.md v1.4 §3/§8
// prose); Dev1's `routers/teams.py` + `routers/admin_teams.py` +
// `schemas.py` landed in parallel shortly after and were read (read-only,
// per the frontend/backend boundary) to cross-check every shape below —
// confirmed field-for-field against `schemas.py`'s `TeamMineOut`,
// `MeTeamOut`, `TeamMemberOut` (incl. `created_at`), `TeamOut`,
// `TeamDetailOut`, `TeamCreate`, `TeamUpdate`, `TeamMemberAdd`, and the
// reused `WorkspaceFileOut` for team-memory files. Still MUST be re-verified
// once Dev1 regenerates `docs/openapi.json` (source of truth per the task
// brief) — this is a same-tree read, not a frozen contract.

export type TeamRoleInTeam = 'member' | 'lead';

/** GET /api/teams/mine item (TECH.md §8: «تیم‌های من»). */
export interface TeamMine {
  id: number;
  name: string;
  slug: string;
  role_in_team: TeamRoleInTeam;
  member_count: number;
}

/**
 * `teams` array on `MeResponse` (TECH.md §8's `/api/auth/me` example):
 * `{id, name, slug, role_in_team}` — no `member_count` per that prose (only
 * `TeamMine` from `/api/teams/mine` carries it).
 */
export interface MeTeam {
  id: number;
  name: string;
  slug: string;
  role_in_team: TeamRoleInTeam;
}

/**
 * GET /api/teams/{id}/members item, and the `members` array nested in
 * `AdminTeamDetail`. TECH.md §8: "متادیتا: username/display_name/role_in_team".
 */
export interface TeamMember {
  user_id: number;
  username: string;
  display_name: string | null;
  role_in_team: TeamRoleInTeam;
  created_at: string;
}

/** GET /api/admin/teams item — "لیست تیم‌ها + شمار اعضا" (TECH.md §8). */
export interface AdminTeam {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  member_count: number;
  created_at: string;
}

/** GET /api/admin/teams/{id} — "جزئیات + اعضا" (TECH.md §8). */
export interface AdminTeamDetail extends AdminTeam {
  members: TeamMember[];
}

/**
 * POST /api/admin/teams body (TECH.md §8): "slug اگر نبود از name تولید و
 * یکتاسازی می‌شود" — `slug` is optional on create.
 */
export interface CreateTeamRequest {
  name: string;
  slug?: string;
  description?: string | null;
}

/**
 * PATCH /api/admin/teams/{id} body — slug is immutable after creation
 * (TECH.md §8: "slug پس از ساخت ثابت است — چون نام پوشهٔ symlink").
 */
export interface UpdateTeamRequest {
  name?: string;
  description?: string | null;
}

/** POST /api/admin/teams/{id}/members body. */
export interface AddTeamMemberRequest {
  user_id: number;
  role_in_team?: TeamRoleInTeam;
}

/**
 * Team-memory file list/upload responses reuse the exact `WorkspaceFile`
 * shape (TECH.md §8: "همان شکل workspace files") for both the member
 * (`/api/teams/{id}/memory/files`) and admin
 * (`/api/admin/teams/{id}/memory/files`) endpoint families.
 */
export type TeamMemoryFile = WorkspaceFile;

// ---------- API keys ----------

export interface ApiKeySummary {
  id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface CreateApiKeyRequest {
  name: string;
}

export interface CreateApiKeyResponse extends ApiKeySummary {
  key: string; // full secret, shown only once
}

// ---------- usage (self) ----------

export interface UsageByModelWire {
  model_key: string;
  credits: DecimalString;
}

export interface UsageByModel {
  model_key: string;
  credits: number;
}

export interface UsageByKeyWire {
  api_key_id: number | null; // null = web chat
  name: string;
  credits: DecimalString;
}

export interface UsageByKey {
  api_key_id: number | null;
  name: string;
  credits: number;
}

export interface UsageDailyPointWire {
  date: string; // YYYY-MM-DD
  credits: DecimalString;
}

export interface UsageDailyPoint {
  date: string;
  credits: number;
}

/**
 * اصلاحیهٔ ۳ / Issue E (TECH.md §5.8, §8): rolling 5h block. `limit_credits_5h`
 * null/0 = unlimited (no cap set) → UI must hide the 5h bar entirely.
 * `reset_5h_at` is the "partial freeing" time (§5.8: when the oldest credit
 * inside the window ages out), null when nothing is in the window yet.
 */
export interface FiveHourUsageWire {
  used_5h: DecimalString;
  limit_credits_5h: DecimalString | null;
  reset_5h_at: string | null;
}

export interface FiveHourUsage {
  used_5h: number;
  limit_credits_5h: number | null;
  reset_5h_at: string | null;
}

export interface UsageMeResponseWire {
  period: QuotaPeriod;
  period_start: string;
  limit_credits: DecimalString;
  bonus_credits: DecimalString;
  used_credits: DecimalString;
  by_model: UsageByModelWire[];
  by_key: UsageByKeyWire[];
  daily: UsageDailyPointWire[];
  /** اصلاحیهٔ ۳ / Issue E — flat fields per §8, absent/null on a not-yet-upgraded backend. */
  used_5h?: DecimalString | null;
  limit_credits_5h?: DecimalString | null;
  reset_5h_at?: string | null;
}

export interface UsageMeResponse {
  period: QuotaPeriod;
  period_start: string;
  limit_credits: number;
  bonus_credits: number;
  used_credits: number;
  by_model: UsageByModel[];
  by_key: UsageByKey[];
  daily: UsageDailyPoint[];
  /** اصلاحیهٔ ۳ / Issue E — null when the backend hasn't shipped this yet, or no cap is set. */
  fiveHour: FiveHourUsage | null;
}

// ---------- admin: users ----------

export interface AdminUser {
  id: number;
  username: string;
  display_name: string | null;
  email: string | null;
  role: UserRole;
  auth_source: AuthSource;
  is_active: boolean;
  created_at: string;
}

/** Wire quota of UserDetailOut (QuotaOut) — note: NO used_credits here. */
export interface AdminQuotaWire {
  period: QuotaPeriod;
  limit_credits: DecimalString;
  bonus_credits: DecimalString;
  period_start: string;
  /** اصلاحیهٔ ۳ / Issue E (TECH.md §3 quotas.limit_credits_5h) — null/absent = unlimited. */
  limit_credits_5h?: DecimalString | null;
}

export interface AdminQuota {
  period: QuotaPeriod;
  limit_credits: number;
  bonus_credits: number;
  period_start: string;
  limit_credits_5h: number | null;
}

export interface AdminUserDetailWire extends AdminUser {
  allowed_models: string[];
  quota: AdminQuotaWire | null;
}

export interface AdminUserDetail extends AdminUser {
  allowed_models: string[];
  quota: AdminQuota | null;
}

export interface CreateUserRequest {
  username: string;
  password?: string; // required for local users
  display_name?: string | null;
  email?: string | null;
  role: UserRole;
  auth_source: AuthSource;
}

export interface UpdateUserRequest {
  role?: UserRole;
  is_active?: boolean;
  password?: string;
  display_name?: string;
  email?: string;
}

// ---------- admin: policy & quota ----------

export interface SetPolicyRequest {
  model_keys: string[];
}

export interface SetQuotaRequest {
  period: QuotaPeriod;
  limit_credits: number; // accepted as number|string server-side
  /**
   * اصلاحیهٔ ۳ / Issue E (TECH.md §8): `PUT .../quota` "now accepts
   * limit_credits_5h". null/omitted/0 = unlimited (no 5h cap enforced).
   */
  limit_credits_5h?: number | null;
}

export interface AddQuotaBonusRequest {
  bonus_credits: number;
}

// ---------- admin: models ----------

export interface AdminModelWire {
  id: number;
  model_key: string;
  display_name: string;
  upstream_model: string;
  input_weight: DecimalString;
  output_weight: DecimalString;
  cache_read_weight: DecimalString;
  is_enabled: boolean;
  sort_order: number;
}

export interface AdminModel {
  id: number;
  model_key: string;
  display_name: string;
  upstream_model: string;
  input_weight: number;
  output_weight: number;
  cache_read_weight: number;
  is_enabled: boolean;
  sort_order: number;
}

/** ModelCreate — no is_enabled field on create (server defaults to enabled). */
export interface CreateModelRequest {
  model_key: string;
  display_name: string;
  upstream_model: string;
  input_weight: number;
  output_weight: number;
  cache_read_weight: number;
  sort_order?: number;
}

/** ModelUpdate — model_key is immutable after create. */
export interface UpdateModelRequest {
  display_name?: string;
  upstream_model?: string;
  input_weight?: number;
  output_weight?: number;
  cache_read_weight?: number;
  is_enabled?: boolean;
  sort_order?: number;
}

// ---------- admin: org usage & audit ----------

export interface AdminUsageByUserWire {
  user_id: number;
  username: string;
  credits: DecimalString;
}

export interface AdminUsageByUser {
  user_id: number;
  username: string;
  credits: number;
}

export interface AdminUsageResponseWire {
  total_credits: DecimalString;
  by_user: AdminUsageByUserWire[];
  by_model: UsageByModelWire[];
  daily: UsageDailyPointWire[];
}

export interface AdminUsageResponse {
  total_credits: number;
  by_user: AdminUsageByUser[];
  by_model: UsageByModel[];
  daily: UsageDailyPoint[];
}

// ---------- admin: per-user usage report (اصلاحیهٔ ۳ / Issue G) ----------

/**
 * `weekly` block of `GET /api/admin/users/{id}/usage` — note the field names
 * differ from `UsageMeResponse` (`used`/`limit`/`bonus`, not
 * `used_credits`/`limit_credits`/`bonus_credits`), and it additionally
 * reports `reset_at` (the upcoming period boundary, `period_start +
 * period_length`) which the self-service `/usage/me` endpoint does not.
 * Confirmed against Dev1's in-progress `schemas.py#WeeklyQuotaBlock`.
 */
export interface WeeklyQuotaBlockWire {
  used: DecimalString;
  limit: DecimalString;
  bonus: DecimalString;
  period: QuotaPeriod;
  period_start: string;
  reset_at: string;
}

export interface WeeklyQuotaBlock {
  used: number;
  limit: number;
  bonus: number;
  period: QuotaPeriod;
  period_start: string;
  reset_at: string;
}

/**
 * `GET /api/admin/users/{id}/usage` (TECH.md §8, §9): "همان دادهٔ «مصرف من»
 * او، فقط متادیتا". NOT a flat superset of `UsageMeResponse` — nests
 * `weekly`/`five_hour` blocks (confirmed against Dev1's in-progress
 * `schemas.py#AdminUserUsageResponse`). The admin drill-down page
 * (`AdminUserUsagePage.tsx`) maps this onto `UsageReport`'s flat props so it
 * still visually mirrors `/usage` as §9 asks. NOT yet in openapi.json — see
 * the file-header note.
 */
export interface AdminUserUsageResponseWire {
  user_id: number;
  username: string;
  by_model: UsageByModelWire[];
  by_key: UsageByKeyWire[];
  daily: UsageDailyPointWire[];
  weekly: WeeklyQuotaBlockWire;
  five_hour: FiveHourUsageWire;
}

export interface AdminUserUsageResponse {
  user_id: number;
  username: string;
  by_model: UsageByModel[];
  by_key: UsageByKey[];
  daily: UsageDailyPoint[];
  weekly: WeeklyQuotaBlock;
  /** null when no 5h cap is set — same "hide the bar" convention as `UsageMeResponse.fiveHour`. */
  fiveHour: FiveHourUsage | null;
}

/** `GET /api/admin/users/{id}/usage` query — §8 mentions `?since=`. */
export interface AdminUserUsageQuery {
  since?: string;
}

export interface AuditLogEntry {
  id: number;
  actor_id: number | null;
  actor_username?: string | null;
  target_id: number | null;
  target_username?: string | null;
  action: string;
  detail: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

/** GET /api/admin/audit query — limit/offset paging, no total in response. */
export interface AuditLogQuery {
  action?: string;
  user_id?: number;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

// ---------- admin: upstream connection ----------

/** اصلاحیهٔ ۲ / Issue B (TECH.md §4.1) — result of the most recent auto-refresh attempt. */
export interface LastRefreshInfo {
  at: string | null;
  ok: boolean | null;
  error: string | null;
}

export interface UpstreamStatus {
  mode: UpstreamMode;
  connected: boolean;
  expires_at: string | null;
  expiring_soon: boolean;
  /** cli_creds only: path of the mounted host credentials file. */
  creds_source: string | null;
  base_url: string;
  last_synced: string | null;
  last_checked: string;
  /**
   * اصلاحیهٔ ۲ / Issue B — new fields per TECH.md §4.1's revised
   * GET /api/admin/upstream/status example. `refresh_token_valid_until` is
   * null on most upstreams (they don't report refresh-token expiry) → UI
   * shows «نامشخص». `auto_refresh` drives the conditional CTA (§9): only
   * show «claude login روی سرور» when 'degraded' or 'failed'.
   */
  refresh_token_valid_until: string | null;
  last_refresh: LastRefreshInfo | null;
  auto_refresh: AutoRefreshState;
}

export interface SetApiKeyRequest {
  api_key: string;
}

export interface SetModeRequest {
  mode: UpstreamMode;
}

// ---------- admin: upstream account limits (اصلاحیهٔ ۳ / Issue F) ----------

/**
 * One window of `GET /api/admin/upstream/account-limits` (TECH.md §4.5, §8).
 * Field names confirmed against Dev1's in-progress
 * `services/account_limits.py#get_account_limits_view` — note it's `key`
 * (not `window`) and `reset` (not `reset_at`), which reads slightly
 * differently from §4.5's prose sketch. `limit`/`remaining` are in whatever
 * unit the upstream's `anthropic-ratelimit-*` headers report
 * (tokens/requests/credits — see `unit`), NOT necessarily EcoCode credits,
 * so `NumericString` (not `DecimalString`) is used defensively — the parser
 * (endpoints.ts) accepts either a number or a decimal-string on the wire
 * (the DB column is `NUMERIC`, which the JSON encoder may or may not stringify).
 */
export type NumericString = string | number;

export interface AccountLimitWindowWire {
  key: string; // '5h' | 'weekly' | 'unified' | ... (defensive: not a closed enum, §4.5)
  limit: NumericString | null;
  remaining: NumericString | null;
  reset: string | null;
  unit: string | null;
  last_updated: string;
  stale: boolean;
}

export interface AccountLimitWindow {
  key: string;
  limit: number | null;
  remaining: number | null;
  reset: string | null;
  unit: string | null;
  last_updated: string;
  stale: boolean;
}

/**
 * §4.5/§8: "اگر آپ‌استریم هدری نداده → available:false + tier/subscription از
 * credentials". When `available` is false, `windows` is expected empty and
 * the UI must show the honest "سرویس بالادستی این اطلاعات را ارائه نمی‌کند"
 * message + tier/subscription instead of fabricating zeros.
 */
export interface AccountLimitsResponseWire {
  available: boolean;
  windows: AccountLimitWindowWire[];
  tier: string | null;
  subscription: string | null;
}

export interface AccountLimitsResponse {
  available: boolean;
  windows: AccountLimitWindow[];
  tier: string | null;
  subscription: string | null;
}

// ---------- health ----------

export interface HealthResponse {
  status: string;
  db: boolean;
  litellm: boolean;
  upstream_mode: UpstreamMode;
  upstream_connected: boolean;
  cli_available: boolean;
}
