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
 * اصلاحیهٔ ۲ (docs/TECH.md v1.2) — NOT YET reconciled against openapi.json.
 * Dev1 is implementing the backend in parallel; docs/openapi.json on disk at
 * the time this was written is still the v1.1 shape (no /stream, no /retry,
 * no thinking_level, no generating flag). Everything below marked "اصلاحیهٔ ۲"
 * is built directly against docs/TECH.md §5.3/§8 prose and MUST be reconciled
 * (field names, exact event payloads) once Dev1 regenerates openapi.json.
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
}

export interface MeResponse extends Omit<MeResponseWire, 'quota'> {
  quota: QuotaSummary | null;
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

export interface UsageMeResponseWire {
  period: QuotaPeriod;
  period_start: string;
  limit_credits: DecimalString;
  bonus_credits: DecimalString;
  used_credits: DecimalString;
  by_model: UsageByModelWire[];
  by_key: UsageByKeyWire[];
  daily: UsageDailyPointWire[];
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
}

export interface AdminQuota {
  period: QuotaPeriod;
  limit_credits: number;
  bonus_credits: number;
  period_start: string;
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

// ---------- health ----------

export interface HealthResponse {
  status: string;
  db: boolean;
  litellm: boolean;
  upstream_mode: UpstreamMode;
  upstream_connected: boolean;
  cli_available: boolean;
}
