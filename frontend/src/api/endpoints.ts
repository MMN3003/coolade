import { api } from './client';
import type {
  AccountLimitWindow,
  AccountLimitWindowWire,
  AccountLimitsResponse,
  AccountLimitsResponseWire,
  AddQuotaBonusRequest,
  AddTeamMemberRequest,
  CreateServiceRequest,
  OrgService,
  ServiceGrant,
  ServiceGrantLevel,
  ServiceTestResult,
  UpdateServiceRequest,
  AdminModel,
  AdminModelWire,
  AdminQuota,
  AdminQuotaWire,
  AdminTeam,
  AdminTeamDetail,
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
  CreateTeamRequest,
  CreateUserRequest,
  FiveHourUsage,
  FiveHourUsageWire,
  HealthResponse,
  LoginRequest,
  MeResponse,
  MeResponseWire,
  NumericString,
  OkResponse,
  Plan,
  PlanWire,
  CreatePlanRequest,
  UpdatePlanRequest,
  QuotaSummary,
  QuotaSummaryWire,
  SendMessageAccepted,
  SendMessageRequest,
  SetApiKeyRequest,
  SetModeRequest,
  SetPolicyRequest,
  SetQuotaRequest,
  TeamMember,
  TeamMemoryFile,
  TeamMine,
  UpdateConversationRequest,
  UpdateModelRequest,
  UpdateTeamRequest,
  UpdateUserRequest,
  UpstreamStatus,
  UsageMeResponse,
  UsageMeResponseWire,
  WorkspaceFile,
  WorkspaceFileContent,
  KnowledgeEntry,
  KnowledgeEntryCreate,
  KnowledgeEntryUpdate,
  AdminConversation,
  AdminConversationDetail,
  LearningSettings,
  LearningRunResult,
  KnowledgeStats,
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
  // اصلاحیهٔ ۴ / Issue H — `teams` optional on the wire until Dev1 ships it
  // (types.ts's file-header note); default to [] so callers never null-check.
  return { ...raw, quota: parseQuota(raw.quota), teams: raw.teams ?? [] };
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

/** User Plans / Tiers — decimal credit limits parsed at the boundary like everywhere else. */
function parsePlan(raw: PlanWire): Plan {
  return {
    ...raw,
    limit_credits: num(raw.limit_credits),
    limit_credits_5h: numOrNull(raw.limit_credits_5h),
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
  /** Local accounts only — the backend rejects LDAP users with a clear message. */
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<OkResponse>('/api/auth/change-password', body),
  me: async (): Promise<MeResponse> => parseMe(await api.get<MeResponseWire>('/api/auth/me')),
};

// ---------- conversations ----------
export const conversationsApi = {
  /** Bare array response; limit/offset paging. */
  list: (q?: string, limit = 50, offset = 0) =>
    api.get<Conversation[]>('/api/conversations', { q, limit, offset }),
  create: (body: CreateConversationRequest) => api.post<Conversation>('/api/conversations', body),
  get: async (id: number): Promise<ConversationDetail> => {
    // Decimal fields arrive as strings from pydantic — normalize to numbers.
    const raw = await api.get<
      Omit<ConversationDetail, 'credits_used' | 'cost_nudge_threshold'> & {
        credits_used?: string | number;
        cost_nudge_threshold?: string | number;
      }
    >(`/api/conversations/${id}`);
    return {
      ...raw,
      credits_used: Number(raw.credits_used ?? 0),
      cost_nudge_threshold: Number(raw.cost_nudge_threshold ?? 0),
    };
  },
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
  /** Stop the in-progress turn (idempotent; the stream then emits error/stopped). */
  stopGeneration: (id: number) => api.post<{ ok: boolean; stopped: boolean }>(`/api/conversations/${id}/stop`),
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
  /** Discard a pending (not yet sent) upload; 400 once it belongs to a sent message. */
  deleteAttachment: (attachmentId: number) =>
    api.delete<{ ok: boolean }>(`/api/attachments/${attachmentId}`),
};

// ---------- workspace files (F4.6; اصلاحیهٔ ۶ web editor) ----------
export const workspaceApi = {
  listFiles: () => api.get<WorkspaceFile[]>('/api/workspace/files'),
  downloadUrl: (fileId: string) => `/api/workspace/files/${encodeURIComponent(fileId)}`,
  remove: (fileId: string) =>
    api.delete<Record<string, unknown>>(`/api/workspace/files/${encodeURIComponent(fileId)}`),
  readContent: (fileId: string) =>
    api.get<WorkspaceFileContent>(`/api/workspace/files/${encodeURIComponent(fileId)}/content`),
  save: (relpath: string, content: string) =>
    api.put<WorkspaceFile>('/api/workspace/file', { relpath, content }),
};

// ---------- teams + team shared memory (اصلاحیهٔ ۴ / Issue H+I) ----------
// See types.ts's file-header note on this section: built purely from
// TECH.md v1.4 §8 prose, `backend/` had no team files at all at the time —
// will 404 until Dev1 ships it (§10's H/I work), surfaced as the uniform
// ApiError like any other not-yet-shipped endpoint.

/** Shared multipart upload helper for both member and admin team-memory endpoints. */
async function uploadTeamMemoryFile(path: string, file: File): Promise<unknown> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    body: form,
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.error?.message ?? 'آپلود فایل ناموفق بود.');
  }
  return res.json().catch(() => undefined);
}

export const teamsApi = {
  /** «تیم‌های من» — read-only list of the current user's teams. */
  mine: () => api.get<TeamMine[]>('/api/teams/mine'),
  /** Members of a team the current user belongs to (404 if not a member — TECH.md §8). */
  members: (id: number) => api.get<TeamMember[]>(`/api/teams/${id}/members`),
  memory: {
    list: (id: number) => api.get<TeamMemoryFile[]>(`/api/teams/${id}/memory/files`),
    upload: (id: number, file: File) => uploadTeamMemoryFile(`/api/teams/${id}/memory/files`, file),
    downloadUrl: (id: number, fileId: string) =>
      `/api/teams/${id}/memory/files/${encodeURIComponent(fileId)}`,
    remove: (id: number, fileId: string) =>
      api.delete<Record<string, unknown>>(`/api/teams/${id}/memory/files/${encodeURIComponent(fileId)}`),
  },
};

// ---------- admin: teams (اصلاحیهٔ ۴ / Issue H) ----------
export const adminTeamsApi = {
  list: () => api.get<AdminTeam[]>('/api/admin/teams'),
  create: (body: CreateTeamRequest) => api.post<AdminTeam>('/api/admin/teams', body),
  get: (id: number) => api.get<AdminTeamDetail>(`/api/admin/teams/${id}`),
  update: (id: number, body: UpdateTeamRequest) => api.patch<AdminTeam>(`/api/admin/teams/${id}`, body),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/admin/teams/${id}`),
  addMember: (id: number, body: AddTeamMemberRequest) =>
    api.post<Record<string, unknown>>(`/api/admin/teams/${id}/members`, body),
  removeMember: (id: number, userId: number) =>
    api.delete<Record<string, unknown>>(`/api/admin/teams/${id}/members/${userId}`),
  /** Admin can manage any team's shared memory without needing membership (TECH.md §8). */
  memory: {
    list: (id: number) => api.get<TeamMemoryFile[]>(`/api/admin/teams/${id}/memory/files`),
    upload: (id: number, file: File) => uploadTeamMemoryFile(`/api/admin/teams/${id}/memory/files`, file),
    downloadUrl: (id: number, fileId: string) =>
      `/api/admin/teams/${id}/memory/files/${encodeURIComponent(fileId)}`,
    remove: (id: number, fileId: string) =>
      api.delete<Record<string, unknown>>(`/api/admin/teams/${id}/memory/files/${encodeURIComponent(fileId)}`),
  },
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

// ---------- admin: plans (User Plans / Tiers) ----------
export const plansApi = {
  list: async (): Promise<Plan[]> => (await api.get<PlanWire[]>('/api/admin/plans')).map(parsePlan),
  get: async (id: number): Promise<Plan> => parsePlan(await api.get<PlanWire>(`/api/admin/plans/${id}`)),
  create: async (body: CreatePlanRequest): Promise<Plan> =>
    parsePlan(await api.post<PlanWire>('/api/admin/plans', body)),
  update: async (id: number, body: UpdatePlanRequest): Promise<Plan> =>
    parsePlan(await api.patch<PlanWire>(`/api/admin/plans/${id}`, body)),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/admin/plans/${id}`),
  /** Re-apply this plan to all its members (rewrites their quota + models + thinking cap). */
  apply: (id: number) => api.post<{ ok: boolean; applied_to: number }>(`/api/admin/plans/${id}/apply`),
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

// ---------- v2 workspaces (persistent per-repo coding environments) ----------
export interface WorkspaceV2 {
  id: number;
  name: string;
  kind: string; // 'repo' | 'personal'
  status: string; // provisioning | running | stopped | ...
  repo_url: string | null;
  base_branch: string | null;
  work_branch: string | null;
  disk_bytes: number;
  last_activity_at: string;
  created_at: string;
}
export interface GitlabTokenStatus {
  connected: boolean;
  gitlab_host: string | null;
}
export const workspacesV2Api = {
  list: () => api.get<WorkspaceV2[]>('/api/workspaces'),
  create: (body: { name: string; kind: string; repo_url?: string | null; base_branch?: string | null }) =>
    api.post<WorkspaceV2>('/api/workspaces', body),
  resume: (id: number) => api.post<WorkspaceV2>(`/api/workspaces/${id}/resume`),
  stop: (id: number) => api.post<WorkspaceV2>(`/api/workspaces/${id}/stop`),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/workspaces/${id}`),
  gitlabStatus: () => api.get<GitlabTokenStatus>('/api/gitlab-token'),
  setGitlab: (body: { token: string; gitlab_host?: string }) =>
    api.put<GitlabTokenStatus>('/api/gitlab-token', body),
  clearGitlab: () => api.delete<Record<string, unknown>>('/api/gitlab-token'),
};

// ---------- admin: organizational services (amendment-1) ----------
export const adminServicesApi = {
  list: () => api.get<OrgService[]>('/api/admin/services'),
  create: (body: CreateServiceRequest) => api.post<OrgService>('/api/admin/services', body),
  update: (id: number, body: UpdateServiceRequest) =>
    api.patch<OrgService>(`/api/admin/services/${id}`, body),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/admin/services/${id}`),
  test: (id: number) => api.post<ServiceTestResult>(`/api/admin/services/${id}/test`),
  grants: (id: number) => api.get<ServiceGrant[]>(`/api/admin/services/${id}/grants`),
  setGrant: (id: number, userId: number, level: ServiceGrantLevel) =>
    api.put<{ ok: boolean }>(`/api/admin/services/${id}/grants/${userId}`, { level }),
  revokeGrant: (id: number, userId: number) =>
    api.delete<Record<string, unknown>>(`/api/admin/services/${id}/grants/${userId}`),
};

// ---------- amendment-7: knowledge layer (docs/KNOWLEDGE.md) ----------
export interface KnowledgeEntriesApi {
  list: () => Promise<KnowledgeEntry[]>;
  create: (body: KnowledgeEntryCreate) => Promise<KnowledgeEntry>;
  update: (id: number, body: KnowledgeEntryUpdate) => Promise<KnowledgeEntry>;
  remove: (id: number) => Promise<unknown>;
}

const userEntryOps = {
  update: (id: number, body: KnowledgeEntryUpdate) =>
    api.patch<KnowledgeEntry>(`/api/knowledge/entries/${id}`, body),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/knowledge/entries/${id}`),
};

const adminEntryOps = {
  update: (id: number, body: KnowledgeEntryUpdate) =>
    api.patch<KnowledgeEntry>(`/api/admin/knowledge/entries/${id}`, body),
  remove: (id: number) => api.delete<Record<string, unknown>>(`/api/admin/knowledge/entries/${id}`),
};

export const knowledgeApi = {
  /** «حافظه و قوانین من» — own rules/knowledge (scope user), incl. learned entries. */
  me: (): KnowledgeEntriesApi => ({
    list: () => api.get<KnowledgeEntry[]>('/api/knowledge/me'),
    create: (body) => api.post<KnowledgeEntry>('/api/knowledge/me', body),
    ...userEntryOps,
  }),
};

export const adminKnowledgeApi = {
  service: (serviceId: number): KnowledgeEntriesApi => ({
    list: () => api.get<KnowledgeEntry[]>(`/api/admin/knowledge/services/${serviceId}`),
    create: (body) => api.post<KnowledgeEntry>(`/api/admin/knowledge/services/${serviceId}`, body),
    ...adminEntryOps,
  }),
  userService: (serviceId: number, userId: number): KnowledgeEntriesApi => ({
    list: () =>
      api.get<KnowledgeEntry[]>(`/api/admin/knowledge/services/${serviceId}/users/${userId}`),
    create: (body) =>
      api.post<KnowledgeEntry>(`/api/admin/knowledge/services/${serviceId}/users/${userId}`, body),
    ...adminEntryOps,
  }),
  user: (userId: number): KnowledgeEntriesApi => ({
    list: () => api.get<KnowledgeEntry[]>(`/api/admin/knowledge/users/${userId}`),
    create: (body) => api.post<KnowledgeEntry>(`/api/admin/knowledge/users/${userId}`, body),
    ...adminEntryOps,
  }),
  team: (teamId: number): KnowledgeEntriesApi => ({
    list: () => api.get<KnowledgeEntry[]>(`/api/admin/knowledge/teams/${teamId}`),
    create: (body) => api.post<KnowledgeEntry>(`/api/admin/knowledge/teams/${teamId}`, body),
    ...adminEntryOps,
  }),
  stats: () => api.get<KnowledgeStats>('/api/admin/knowledge/stats'),
  setUserLearning: (userId: number, enabled: boolean) =>
    api.put<{ ok: boolean }>(`/api/admin/knowledge/users/${userId}/learning`, { enabled }),
  /** Audited admin reads of a user's chats (docs/KNOWLEDGE.md §6). */
  userConversations: (userId: number) =>
    api.get<AdminConversation[]>(`/api/admin/knowledge/users/${userId}/conversations`),
  conversation: (conversationId: number) =>
    api.get<AdminConversationDetail>(`/api/admin/knowledge/conversations/${conversationId}`),
  learning: {
    get: () => api.get<LearningSettings>('/api/admin/knowledge/learning'),
    set: (body: { global_enabled?: boolean; model_key?: string | null; team_enabled?: boolean }) =>
      api.put<LearningSettings>('/api/admin/knowledge/learning', body),
    run: () => api.post<LearningRunResult>('/api/admin/knowledge/learning/run'),
  },
  exportConversationsUrl: (params?: { since?: string; until?: string; user_id?: number }) => {
    const q = new URLSearchParams();
    if (params?.since) q.set('since', params.since);
    if (params?.until) q.set('until', params.until);
    if (params?.user_id) q.set('user_id', String(params.user_id));
    const qs = q.toString();
    return `/api/admin/knowledge/export/conversations.jsonl${qs ? `?${qs}` : ''}`;
  },
  exportEntriesUrl: () => '/api/admin/knowledge/export/entries.jsonl',
};
