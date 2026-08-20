import type { ChatStreamEvent } from './types';

/**
 * SSE streaming via fetch + ReadableStream, per TECH.md v1.1 §5/§8.
 *
 * We can't use `EventSource` because it only supports GET; the chat send
 * endpoint is a POST that streams the response body as `text/event-stream`.
 *
 * Protocol (§5.3): the backend runs a Claude Code CLI session and translates
 * its stream-json output into named SSE events:
 *
 *   event: start   data: {"conversation_id": 12}
 *   event: delta   data: {"text": "..."}
 *   event: tool    data: {"name": "Write", "summary": "..."}
 *   event: done    data: {"credits_used": 12.5, "files_changed": ["report.md"]}
 *   event: error   data: {"message": "پیام فارسی"}
 *
 * We parse the wire format by hand: events are separated by a blank line, each
 * event has an `event:` line and one or more `data:` lines with a JSON payload.
 */

export interface StreamChatParams {
  conversationId: number;
  content: string;
  signal?: AbortSignal;
}

const KNOWN_EVENTS = new Set(['start', 'delta', 'tool', 'done', 'error']);

function parseSseBlock(block: string): { event?: string; data: string } | null {
  const lines = block.split('\n');
  let event: string | undefined;
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join('\n') };
}

export async function* streamChatMessage(
  params: StreamChatParams
): AsyncGenerator<ChatStreamEvent, void, unknown> {
  const res = await fetch(`/api/conversations/${params.conversationId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      Accept: 'text/event-stream',
    },
    // SendMessageRequest per openapi.json: {content} only — uploaded attachments
    // are already in the user's workspace and picked up by the CLI session.
    body: JSON.stringify({ content: params.content }),
    credentials: 'same-origin',
    signal: params.signal,
  });

  if (!res.ok || !res.body) {
    // Pre-stream failure: the uniform error envelope {error:{code,message}}
    // (e.g. 429 quota_exceeded, 409 chat_busy, 403 model_not_allowed).
    let message = 'ارسال پیام ناموفق بود.';
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

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIndex: number;
      // events are separated by a blank line ("\n\n")
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawBlock = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        const parsed = parseSseBlock(rawBlock);
        if (!parsed) continue;
        try {
          const payload = JSON.parse(parsed.data) as Record<string, unknown>;
          // event name comes from the `event:` line; tolerate payloads that
          // also carry a `type` field.
          const type = parsed.event ?? (payload.type as string | undefined);
          if (!type || !KNOWN_EVENTS.has(type)) continue;
          yield { ...(payload as object), type } as ChatStreamEvent;
        } catch {
          // ignore malformed chunk
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
