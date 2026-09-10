import type { ChatStreamEvent } from './types';

/**
 * SSE streaming via fetch + ReadableStream, per docs/TECH.md v1.2 §5.3/§8/§9
 * (اصلاحیهٔ ۲ / Issue A).
 *
 * We can't use `EventSource` because in the general case we also need to
 * distinguish a pre-stream JSON error body from an actual event stream, and
 * historically this project's send call was a POST; keeping the same
 * hand-rolled parser for the new GET stream keeps both paths consistent.
 *
 * Protocol (§5.3): `GET /api/conversations/{id}/stream` is the ONLY way the
 * browser ever consumes a turn's output now. `POST …/messages` and
 * `POST …/retry` are plain JSON calls that return 202 immediately — see
 * `conversationsApi.sendMessage` / `retryMessage` in `./endpoints`. Opening
 * this stream:
 *   - if a turn is active: replays the whole in-memory ring buffer from the
 *     first event (including `start`), then follows live until `done`/`error`.
 *     Reattach is idempotent and works from any tab, any number of times.
 *   - if no turn is active: emits a single `event: idle` and closes — the
 *     caller already has the persisted messages from `GET /conversations/{id}`.
 *
 *   event: start   data: {"conversation_id": 12}
 *   event: delta   data: {"text": "..."}
 *   event: tool    data: {"name": "Write", "summary": "..."}
 *   event: done    data: {"credits_used": "12.5", "files_changed": ["report.md"], "thinking_level": "standard"}
 *   event: error   data: {"message": "پیام فارسی", "code": "cli_error"}
 *   event: idle    data: {}
 *
 * We parse the wire format by hand: events are separated by a blank line, each
 * event has an `event:` line and one or more `data:` lines with a JSON payload.
 */

export interface OpenStreamParams {
  conversationId: number;
  signal?: AbortSignal;
}

const KNOWN_EVENTS = new Set(['start', 'delta', 'tool', 'done', 'error', 'idle']);
const TERMINAL_EVENTS = new Set(['done', 'error', 'idle']);

function parseSseBlock(block: string): { event?: string; data: string; comment: boolean } | null {
  const lines = block.split('\n');
  let event: string | undefined;
  let comment = false;
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    else if (line.startsWith(':')) comment = true; // SSE comment — the backend's keepalive ping
  }
  if (dataLines.length === 0 && !event) return comment ? { data: '{}', comment } : null;
  return { event, data: dataLines.join('\n') || '{}', comment: false };
}

/**
 * Thrown by `openConversationStream` when the socket closes before a terminal
 * event (`done`/`error`/`idle`) arrived — proxy idle timeout, mobile radio
 * hand-off, tab backgrounded by the OS… The turn itself is still running
 * server-side, so the right reaction is to reattach (replay is idempotent),
 * not to show an error. `useConversationStream` does that with backoff.
 */
export class StreamInterruptedError extends Error {
  constructor() {
    super('stream closed before a terminal event');
    this.name = 'StreamInterruptedError';
  }
}

/**
 * Opens (or reattaches to) the SSE stream for a conversation's current turn.
 * Safe to call repeatedly / from multiple mounts — the backend buffer is
 * replayed from the start each time, so there is no "missed the beginning"
 * failure mode when reattaching after navigating away and back.
 */
export async function* openConversationStream(
  params: OpenStreamParams
): AsyncGenerator<ChatStreamEvent, void, unknown> {
  const res = await fetch(`/api/conversations/${params.conversationId}/stream`, {
    method: 'GET',
    headers: {
      Accept: 'text/event-stream',
      'X-Requested-With': 'XMLHttpRequest',
    },
    credentials: 'same-origin',
    signal: params.signal,
  });

  if (!res.ok || !res.body) {
    let message = 'اتصال به استریم پاسخ ناموفق بود.';
    let code: string | undefined = 'stream_error';
    try {
      const body = await res.json();
      if (body?.error?.message) message = body.error.message;
      if (body?.error?.code) code = body.error.code;
    } catch {
      /* non-JSON error body, keep default message */
    }
    yield { type: 'error', message, code };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let terminal = false;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      // CRLF-tolerant: some proxies re-emit lines with \r\n.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');

      let sepIndex: number;
      // events are separated by a blank line ("\n\n")
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawBlock = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        const parsed = parseSseBlock(rawBlock);
        if (!parsed) continue;
        if (parsed.comment) {
          yield { type: 'ping' };
          continue;
        }
        try {
          const payload = JSON.parse(parsed.data) as Record<string, unknown>;
          // event name comes from the `event:` line; tolerate payloads that
          // also carry a `type` field.
          const type = parsed.event ?? (payload.type as string | undefined);
          if (!type || !KNOWN_EVENTS.has(type)) continue;
          if (TERMINAL_EVENTS.has(type)) terminal = true;
          yield { ...(payload as object), type } as ChatStreamEvent;
          if (terminal) return;
        } catch {
          // ignore malformed chunk
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
  if (!terminal) throw new StreamInterruptedError();
}
