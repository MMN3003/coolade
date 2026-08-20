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
 */

// ---------- shared ----------

export type UserRole = 'admin' | 'user';
export type AuthSource = 'local' | 'ldap';
export type QuotaPeriod = 'daily' | 'weekly' | 'monthly';
export type UpstreamMode = 'mock' | 'cli_creds' | 'apikey';
export type Surface = 'web_chat' | 'api';
export type MessageRole = 'user' | 'assistant';

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
}

export interface Message {
  id: number;
  role: MessageRole;
  content: string;
  /** e.g. {tool_uses: [...]} — structural CLI events; shape is backend-internal. */
  content_blocks?: Record<string, unknown> | null;
  created_at: string;
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
}

/** POST …/messages body — content only; attachments are implicit via upload. */
export interface SendMessageRequest {
  content: string;
}

/** Response of POST /api/conversations/{id}/attachments. */
export interface AttachmentUploadResponse {
  id: number;
  filename: string;
  size_bytes: number;
}

/**
 * SSE events streamed from POST /api/conversations/{id}/messages (§5.3).
 * Verified against backend/app/routers/conversations.py `_sse(...)` calls:
 *   start {conversation_id} · delta {text} · tool {name, summary}
 *   done {credits_used: DecimalString, files_changed: string[]} · error {message}
 */
export type ChatStreamEvent =
  | { type: 'start'; conversation_id: number }
  | { type: 'delta'; text: string }
  | { type: 'tool'; name: string; summary: string }
  | { type: 'done'; credits_used: DecimalString; files_changed: string[] }
  | { type: 'error'; message: string; code?: string };

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
