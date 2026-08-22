import { useCallback, useEffect, useRef, useState } from 'react';
import { openConversationStream } from '@/api/sse';
import type { ThinkingLevel } from '@/api/types';

/**
 * اصلاحیهٔ ۲ / Issue A (docs/TECH.md §5.1, §5.3, §8, §9) — owns the browser
 * side of "a turn runs independently of the client". This hook only manages
 * the LOCAL SSE reader (fetch + ReadableStream over GET …/stream); it never
 * starts or cancels the turn itself — that already happened server-side via
 * POST …/messages or POST …/retry (202) before `attach` is called, or is
 * simply still running from a previous page load.
 *
 * Switching conversations (or navigating away) must not lose the OTHER
 * conversation's in-progress output, because it keeps running on the
 * backend regardless of whether anyone is listening — so `attach`/`stop`
 * only ever tear down *this* reader; reopening the conversation later
 * reattaches and replays from the start of the turn (§5.3's replay
 * contract), which is why we don't need to persist any local buffer here.
 */

export interface ToolStep {
  name: string;
  summary: string;
}

export interface ConversationStreamState {
  /** conversation this reader is attached to; null when idle/detached. */
  conversationId: number | null;
  /** the assistant message row currently receiving live/replayed text. */
  assistantMessageId: number | null;
  text: string;
  tool: ToolStep | null;
  /** true while the reader is open and no terminal event (done/error/idle) has arrived yet. */
  active: boolean;
  thinkingLevel: ThinkingLevel | null;
}

export interface ConversationStreamCallbacks {
  /** Turn finished successfully — caller should refetch canonical messages, then usually call `reset()`. */
  onDone?: (thinkingLevel: ThinkingLevel | null) => void | Promise<void>;
  /** Turn failed — the message row is now status='failed' server-side; caller should refetch to show it. */
  onError?: (message: string, code?: string) => void | Promise<void>;
  /** No active turn (nothing to reattach to). */
  onIdle?: () => void | Promise<void>;
}

const INITIAL_STATE: ConversationStreamState = {
  conversationId: null,
  assistantMessageId: null,
  text: '',
  tool: null,
  active: false,
  thinkingLevel: null,
};

export function useConversationStream() {
  const [state, setState] = useState<ConversationStreamState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);

  /** Tears down the local reader only. The server-side turn (if any) keeps running. */
  const stop = useCallback(() => {
    generationRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  /** Aborts any current reader and clears local state (e.g. on conversation switch). */
  const reset = useCallback(() => {
    stop();
    setState(INITIAL_STATE);
  }, [stop]);

  /**
   * Opens GET …/stream for `conversationId` and consumes it: replay-from-start
   * if a turn is active, or a single `idle` event if not. Safe to call again
   * for a new send/retry — it tears down any prior reader for this hook first.
   */
  const attach = useCallback(
    (conversationId: number, assistantMessageId: number | null, callbacks?: ConversationStreamCallbacks) => {
      stop();
      const myGeneration = generationRef.current;
      const controller = new AbortController();
      abortRef.current = controller;

      setState({
        conversationId,
        assistantMessageId,
        text: '',
        tool: null,
        active: true,
        thinkingLevel: null,
      });

      const isCurrent = () => generationRef.current === myGeneration && !controller.signal.aborted;

      (async () => {
        try {
          for await (const event of openConversationStream({ conversationId, signal: controller.signal })) {
            if (!isCurrent()) return;
            switch (event.type) {
              case 'start':
                break;
              case 'delta':
                setState((s) => (isCurrent() ? { ...s, text: s.text + event.text, tool: null } : s));
                break;
              case 'tool':
                setState((s) =>
                  isCurrent() ? { ...s, tool: { name: event.name, summary: event.summary } } : s
                );
                break;
              case 'done': {
                const level = event.thinking_level ?? null;
                setState((s) => (isCurrent() ? { ...s, active: false, thinkingLevel: level } : s));
                await callbacks?.onDone?.(level);
                break;
              }
              case 'error':
                setState((s) => (isCurrent() ? { ...s, active: false } : s));
                await callbacks?.onError?.(event.message, event.code);
                break;
              case 'idle':
                setState((s) => (isCurrent() ? { ...s, active: false } : s));
                await callbacks?.onIdle?.();
                break;
            }
          }
        } catch (err) {
          if ((err as Error)?.name !== 'AbortError' && isCurrent()) {
            setState((s) => ({ ...s, active: false }));
            await callbacks?.onError?.((err as Error)?.message ?? 'خطای استریم', 'stream_error');
          }
        }
      })();
    },
    [stop]
  );

  useEffect(() => () => stop(), [stop]);

  return { state, attach, stop, reset };
}
