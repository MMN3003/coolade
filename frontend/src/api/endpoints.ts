import { api } from './client';
import type {
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
  HealthResponse,
  LoginRequest,
  MeResponse,
  MeResponseWire,
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
  };
}

function parseMe(raw: MeResponseWire): MeResponse {
  return { ...raw, quota: parseQuota(raw.quota) };
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
};

// ---------- health ----------
export const healthApi = {
  check: () => api.get<HealthResponse>('/api/health'),
};
