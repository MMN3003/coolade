import type { ApiErrorBody } from './types';

/**
 * Centralized API client per TECH.md §8.
 *
 * - All calls are relative paths (`/api/...`, `/v1/...`) — same-origin, so no
 *   CORS config and no need for `credentials: 'include'` (default `same-origin`
 *   already sends the session cookie).
 * - TECH.md §7.1 requires `X-Requested-With` on mutating requests as a
 *   lightweight CSRF mitigation (paired with SameSite=Lax cookies).
 * - Errors follow the uniform envelope `{ error: { code, message } }`; we throw
 *   an `ApiError` carrying both so callers can render `message` (Persian) and
 *   branch on `code`.
 */

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** Fired whenever a request comes back 401 so the app shell can redirect to /login. */
export type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler;
}

const DEFAULT_ERROR_MESSAGE = 'خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.';

async function parseErrorBody(res: Response): Promise<ApiError> {
  let code = 'unknown_error';
  let message = DEFAULT_ERROR_MESSAGE;
  try {
    const body = (await res.json()) as ApiErrorBody;
    if (body?.error?.message) message = body.error.message;
    if (body?.error?.code) code = body.error.code;
  } catch {
    // body wasn't JSON (e.g. proxy/nginx error page) — keep defaults
    if (res.status === 404) message = 'یافت نشد.';
    if (res.status >= 500) message = 'خطای سرور. لطفاً بعداً دوباره تلاش کنید.';
  }
  return new ApiError(res.status, code, message);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  // Backend middleware (backend/app/main.py) enforces this header on mutating
  // /api/* requests; we send it on ALL fetch-based calls for uniformity.
  // (Plain <a href> downloads are GET navigations and exempt server-side.)
  const headers: Record<string, string> = { 'X-Requested-With': 'XMLHttpRequest' };

  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  const res = await fetch(buildUrl(path, options.query), {
    method,
    headers,
    body,
    credentials: 'same-origin',
    signal: options.signal,
  });

  if (res.status === 401) {
    onUnauthorized?.();
  }

  if (!res.ok) {
    throw await parseErrorBody(res);
  }

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    return (await res.json()) as T;
  }
  // non-JSON success (e.g. CSV) — callers that need this use `requestBlob` instead
  return undefined as T;
}

async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const res = await fetch(buildUrl(path, options.query), {
    method: options.method ?? 'GET',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    credentials: 'same-origin',
    signal: options.signal,
  });
  if (res.status === 401) onUnauthorized?.();
  if (!res.ok) throw await parseErrorBody(res);
  return res.blob();
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal) =>
    request<T>(path, { method: 'GET', query, signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', body, signal }),
  put: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'PUT', body, signal }),
  patch: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'PATCH', body, signal }),
  delete: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: 'DELETE', signal }),
  blob: (path: string, query?: RequestOptions['query']) => requestBlob(path, { query }),
};

export { parseErrorBody };
