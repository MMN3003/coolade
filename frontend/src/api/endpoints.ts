import { api } from './client';
import type {
  AccountLimitWindow,
  AccountLimitWindowWire,
  AccountLimitsResponse,
  AccountLimitsResponseWire,
  AddQuotaBonusRequest,
  AdminModel,
  AdminModelWire,
  AdminQuota,
  AdminQuotaWire,
  AdminUsageResponse,
  AdminUsageResponseWire,
  AdminUser,
  AdminUserDetail,
  AdminUserDetailWire,
  AdminUserUsageResponse,
  AdminUserUsageResponseWire,
  AdminUserUsageQuery,
  ApiKeySummary,
  AttachmentUploadResponse,
  AuditLogEntry,
  AuditLogQuery,
  Conversation,
  ConversationDetail,
  CreateApiKeyRequest,
  CreateApiKeyResponse,
  CreateConversationRequest,
  CreateModelRequest,
  CreateUserRequest,
  FiveHourUsage,
  FiveHourUsageWire,
  HealthResponse,
  LoginRequest,
  MeResponse,
  MeResponseWire,
  NumericString,
  OkResponse,
  QuotaSummary,
  QuotaSummaryWire,
  SendMessageAccepted,
  SendMessageRequest,
  SetApiKeyRequest,
  SetModeRequest,
  SetPolicyRequest,
  SetQuotaRequest,
  UpdateConversationRequest,
  UpdateModelRequest,
  UpdateUserRequest,
  UpstreamStatus,
  UsageMeResponse,
  UsageMeResponseWire,
  WorkspaceFile,
} from './types';

// ---------- decimal-string parsing at the API boundary ----------
// The backend serializes all credit/weight decimals as strings ("28.2660").
// Components consume plain numbers; conversion happens here, once.

function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/**
 * Like `num`, but preserves `null` — needed for fields where null is
 * semantically distinct from 0 (اصلاحیهٔ ۳: `limit_credits_5h` null =
 * "unlimited / no cap set", vs 0 which is treated the same by the UI but is
 * a different wire value than "not configured").
 */
function numOrNull(v: NumericString | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function parseQuota(q: QuotaSummaryWire | null): QuotaSummary | null {
  if (!q) return null;
  return {
    period: q.period,
    limit_credits: num(q.limit_credits),
    bonus_credits: num(q.bonus_credits),
    used_credits: num(q.used_credits),
    period_start: q.period_start,
  };
}

function parseAdminQuota(q: AdminQuotaWire | null): AdminQuota | null {
  if (!q) return null;
  return {
    period: q.period,
    limit_credits: num(q.limit_credits),
    bonus_credits: num(q.bonus_credits),
    period_start: q.period_start,
    limit_credits_5h: numOrNull(q.limit_credits_5h),
  };
}

function parseMe(raw: MeResponseWire): MeResponse {
  return { ...raw, quota: parseQuota(raw.quota) };
}

/** اصلاحیهٔ ۳ / Issue E — null when the backend hasn't shipped the flat 5h fields yet, or no cap is set. */
function parseFiveHour(raw: FiveHourUsageWire | Pick<UsageMeResponseWire, 'used_5h' | 'limit_credits_5h' | 'reset_5h_at'>): FiveHourUsage | null {
  const limit = numOrNull(raw.limit_credits_5h);
  if (!limit) return null; // NULL/0 = unlimited per TECH.md §3/§8 — hide the bar entirely
  return {
    used_5h: num(raw.used_5h),
    limit_credits_5h: limit,
    reset_5h_at: raw.reset_5h_at ?? null,
  };
}

function parseUsageMe(raw: UsageMeResponseWire): UsageMeResponse {
  return {
    period: raw.period,
    period_start: raw.period_start,
    limit_credits: num(raw.limit_credits),
    bonus_credits: num(raw.bonus_credits),
    used_credits: num(raw.used_credits),
    by_model: raw.by_model.map((m) => ({ model_key: m.model_key, credits: num(m.credits) })),
    by_key: raw.by_key.map((k) => ({ api_key_id: k.api_key_id, name: k.name, credits: num(k.credits) })),
    daily: raw.daily.map((d) => ({ date: d.date, credits: num(d.credits) })),
    fiveHour: parseFiveHour(raw),
  };
}

function parseModel(raw: AdminModelWire): AdminModel {
  return {
    ...raw,
    input_weight: num(raw.input_weight),
    output_weight: num(raw.output_weight),
    cache_read_weight: num(raw.cache_read_weight),
  };
}

function parseAdminUsage(raw: AdminUsageResponseWire): AdminUsageResponse {
  return {
    total_credits: num(raw.total_credits),
    by_user: raw.by_user.map((u) => ({ user_id: u.user_id, username: u.username, credits: num(u.credits) })),
    by_model: raw.by_model.map((m) => ({ model_key: m.model_key, credits: num(m.credits) })),
    daily: raw.daily.map((d) => ({ date: d.date, credits: num(d.credits) })),
  };
}

/**
 * اصلاحیهٔ ۳ / Issue G — nested `weekly`/`five_hour` blocks (not a flat
 * superset of UsageMeResponse, see types.ts's file-header note).
 */
function parseAdminUserUsage(raw: AdminUserUsageResponseWire): AdminUserUsageResponse {
  const limit5h = numOrNull(raw.five_hour.limit_credits_5h);
  return {
    user_id: raw.user_id,
    username: raw.username,
    by_model: raw.by_model.map((m) => ({ model_key: m.model_key, credits: num(m.credits) })),
    by_key: raw.by_key.map((k) => ({ api_key_id: k.api_key_id, name: k.name, credits: num(k.credits) })),
    daily: raw.daily.map((d) => ({ date: d.date, credits: num(d.credits) })),
    weekly: {
      used: num(raw.weekly.used),
      limit: num(raw.weekly.limit),
      bonus: num(raw.weekly.bonus),
      period: raw.weekly.period,
      period_start: raw.weekly.period_start,
      reset_at: raw.weekly.reset_at,
    },
    fiveHour: limit5h
      ? { used_5h: num(raw.five_hour.used_5h), limit_credits_5h: limit5h, reset_5h_at: raw.five_hour.reset_5h_at }
      : null,
  };
}

/** اصلاحیهٔ ۳ / Issue F — never fabricates numbers; passes `available:false` straight through. */
function parseAccountLimitWindow(raw: AccountLimitWindowWire): AccountLimitWindow {
  return {
    key: raw.key,
    limit: numOrNull(raw.limit),
    remaining: numOrNull(raw.remaining),
    reset: raw.reset,
    unit: raw.unit,
    last_updated: raw.last_updated,
    stale: raw.stale,
  };
}

function parseAccountLimits(raw: AccountLimitsResponseWire): AccountLimitsResponse {
  return {
    available: raw.available,
    windows: (raw.windows ?? []).map(parseAccountLimitWindow),
    tier: raw.tier,
    subscription: raw.subscription,
  };
}

// ---------- auth ----------
export const authApi = {
  /** Login sets the session cookie and returns {ok}; the user comes from me(). */
  login: (body: LoginRequest) => api.post<OkResponse>('/api/auth/login', body),
  logout: () => api.post<OkResponse>('/api/auth/logout'),
  me: async (): Promise<MeResponse> => parseMe(await api.get<MeResponseWire>('/api/auth/me')),
};

// ---------- conversations ----------
export const conversationsApi = {
  /** Bare array response; limit/offset paging. */
  list: (q?: string, limit = 50, offset = 0) =>
    api.get<Conversation[]>('/api/conversations', { q, limit, offset }),
  create: (body: CreateConversationRequest) => api.post<Conversation>('/api/conversations', body),
  get: (id: number) => api.get<ConversationDetail>(`/api/conversations/${id}`),
  update: (id: number, body: UpdateConversationRequest) =>
    api.patch<Conversation>(`/api/conversations/${id}`, body),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/conversations/${id}`),
  /**
   * اصلاحیهٔ ۲ / Issue A (TECH.md §5.1, §8): accepts the turn synchronously
   * (401/403/409 chat_busy/429 before returning) and responds 202 — no SSE
   * body anymore. The caller must follow up with `GET …/stream` (see
   * `api/sse.ts#openConversationStream`) to actually see the reply.
   */
  sendMessage: (id: number, body: SendMessageRequest) =>
    api.post<SendMessageAccepted>(`/api/conversations/${id}/messages`, body),
  /**
   * اصلاحیهٔ ۲ / Issue C (TECH.md §5.1, §8): only valid on the latest message
   * when status='failed'. Reuses the same message row (reset to 'streaming')
   * — the returned `assistant_message_id` is the same id that was failed.
   * 409 `not_retryable` (not latest / not failed) or `chat_busy` (concurrent
   * retry) — both carry a Persian `error.message` per the uniform envelope.
   */
  retryMessage: (id: number, messageId: number) =>
    api.post<SendMessageAccepted>(`/api/conversations/${id}/messages/${messageId}/retry`),
  uploadAttachment: async (conversationId: number, file: File): Promise<AttachmentUploadResponse> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`/api/conversations/${conversationId}/attachments`, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: form,
      credentials: 'same-origin',
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.error?.message ?? 'آپلود فایل ناموفق بود.');
    }
    return res.json() as Promise<AttachmentUploadResponse>;
  },
  attachmentDownloadUrl: (attachmentId: number) => `/api/attachments/${attachmentId}`,
};

// ---------- workspace files (F4.6) ----------
export const workspaceApi = {
  listFiles: () => api.get<WorkspaceFile[]>('/api/workspace/files'),
  downloadUrl: (fileId: string) => `/api/workspace/files/${encodeURIComponent(fileId)}`,
  remove: (fileId: string) =>
    api.delete<Record<string, unknown>>(`/api/workspace/files/${encodeURIComponent(fileId)}`),
};

// ---------- api keys ----------
export const keysApi = {
  list: () => api.get<ApiKeySummary[]>('/api/keys'),
  create: (body: CreateApiKeyRequest) => api.post<CreateApiKeyResponse>('/api/keys', body),
  revoke: (id: number) => api.delete<Record<string, unknown>>(`/api/keys/${id}`),
};

// ---------- usage (self) ----------
export const usageApi = {
  me: async (): Promise<UsageMeResponse> => parseUsageMe(await api.get<UsageMeResponseWire>('/api/usage/me')),
};

// ---------- admin: users ----------
export const adminUsersApi = {
  list: () => api.get<AdminUser[]>('/api/admin/users'),
  create: (body: CreateUserRequest) => api.post<AdminUser>('/api/admin/users', body),
  get: async (id: number): Promise<AdminUserDetail> => {
    const raw = await api.get<AdminUserDetailWire>(`/api/admin/users/${id}`);
    return { ...raw, quota: parseAdminQuota(raw.quota) };
  },
  update: (id: number, body: UpdateUserRequest) => api.patch<AdminUser>(`/api/admin/users/${id}`, body),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/admin/users/${id}`),
  /**
   * اصلاحیهٔ ۳ / Issue G (TECH.md §8, §9): per-user drill-down — "همان دادهٔ
   * «مصرف من» او، فقط متادیتا". Not yet in openapi.json; will 404 until Dev1
   * ships it (§10) — see `pages/admin/AdminUserUsagePage.tsx`.
   */
  usage: async (id: number, query?: AdminUserUsageQuery): Promise<AdminUserUsageResponse> =>
    parseAdminUserUsage(await api.get<AdminUserUsageResponseWire>(`/api/admin/users/${id}/usage`, { ...query })),
  /** اصلاحیهٔ ۳ / Issue G, "nice": single-user CSV export. */
  usageExportCsvUrl: (id: number) => `/api/admin/users/${id}/usage/export.csv`,
};

// ---------- admin: policy & quota ----------
export const adminPolicyApi = {
  setPolicy: (userId: number, body: SetPolicyRequest) =>
    api.put<Record<string, unknown>>(`/api/admin/users/${userId}/policy`, body),
  setQuota: (userId: number, body: SetQuotaRequest) =>
    api.put<Record<string, unknown>>(`/api/admin/users/${userId}/quota`, body),
  addBonus: (userId: number, body: AddQuotaBonusRequest) =>
    api.post<Record<string, unknown>>(`/api/admin/users/${userId}/quota/bonus`, body),
};

// ---------- admin: models ----------
export const adminModelsApi = {
  list: async (): Promise<AdminModel[]> =>
    (await api.get<AdminModelWire[]>('/api/admin/models')).map(parseModel),
  create: async (body: CreateModelRequest): Promise<AdminModel> =>
    parseModel(await api.post<AdminModelWire>('/api/admin/models', body)),
  update: async (id: number, body: UpdateModelRequest): Promise<AdminModel> =>
    parseModel(await api.patch<AdminModelWire>(`/api/admin/models/${id}`, body)),
};

// ---------- admin: org usage & audit ----------
export const adminUsageApi = {
  summary: async (): Promise<AdminUsageResponse> =>
    parseAdminUsage(await api.get<AdminUsageResponseWire>('/api/admin/usage')),
  exportCsvUrl: () => '/api/admin/usage/export.csv',
  /** Bare array; page with limit/offset — there is no total count. */
  auditLog: (query: AuditLogQuery) => api.get<AuditLogEntry[]>('/api/admin/audit', { ...query }),
};

// ---------- admin: upstream connection ----------
export const adminUpstreamApi = {
  status: () => api.get<UpstreamStatus>('/api/admin/upstream/status'),
  setApiKey: (body: SetApiKeyRequest) => api.put<Record<string, unknown>>('/api/admin/upstream/apikey', body),
  setMode: (body: SetModeRequest) => api.put<Record<string, unknown>>('/api/admin/upstream/mode', body),
  /**
   * اصلاحیهٔ ۳ / Issue F (TECH.md §4.5, §8): "لیمیت خود اکانت آپ‌استریم".
   * Not yet in openapi.json; will 404 until Dev1 ships it (§10) — see
   * `pages/admin/AdminUsagePage.tsx`'s account-limits card.
   */
  accountLimits: async (): Promise<AccountLimitsResponse> =>
    parseAccountLimits(await api.get<AccountLimitsResponseWire>('/api/admin/upstream/account-limits')),
};

// ---------- health ----------
export const healthApi = {
  check: () => api.get<HealthResponse>('/api/health'),
};
