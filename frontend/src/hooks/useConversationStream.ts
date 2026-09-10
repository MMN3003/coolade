import { useCallback, useEffect, useRef, useState } from 'react';
import { openConversationStream, StreamInterruptedError } from '@/api/sse';
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
 *
 * Resilience (2026-09-10): the socket WILL die mid-turn in the real world —
 * carrier NAT / CDN idle cut-offs, a phone locking its screen, a Wi-Fi ↔ LTE
 * hand-off. Because replay-from-start is idempotent, the reader simply
 * reopens the stream (with backoff) whenever it closes without a terminal
 * event, when no bytes (not even the backend's 15s keepalive ping) arrived
 * for `STALE_AFTER_MS`, or when the tab comes back to the foreground / the
 * browser reports it is online again. The first `delta` of a replay REPLACES
 * the locally accumulated text instead of appending, so the bubble never
 * shows duplicated content and never flashes empty in between.
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
  /** true while the reader is between a dropped socket and a successful reopen. */
  reconnecting: boolean;
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
  reconnecting: false,
  thinkingLevel: null,
};

/** No event (deltas, tool steps or keepalive pings) for this long ⇒ treat the socket as dead. */
const STALE_AFTER_MS = 45_000;
/** Reconnect backoff: 1s, 2s, 4s, … capped. */
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 10_000;
/** Give up (surface an error) after this many consecutive failed reopen attempts. */
const MAX_CONSECUTIVE_FAILURES = 12;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const timer = window.setTimeout(done, ms);
    function done() {
      signal.removeEventListener('abort', done);
      window.clearTimeout(timer);
      resolve();
    }
    signal.addEventListener('abort', done, { once: true });
  });
}

export function useConversationStream() {
  const [state, setState] = useState<ConversationStreamState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);
  /** Aborts only the CURRENT socket (not the whole attach loop) — used to force a reopen. */
  const socketAbortRef = useRef<AbortController | null>(null);
  const lastEventAtRef = useRef(0);

  /** Tears down the local reader only. The server-side turn (if any) keeps running. */
  const stop = useCallback(() => {
    generationRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    socketAbortRef.current?.abort();
    socketAbortRef.current = null;
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
   * Keeps reopening the socket until a terminal event arrives (see header).
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
        reconnecting: false,
        thinkingLevel: null,
      });

      const isCurrent = () => generationRef.current === myGeneration && !controller.signal.aborted;

      (async () => {
        let failures = 0;
        let attempt = 0;
        for (;;) {
          if (!isCurrent()) return;
          if (attempt > 0) {
            setState((s) => (isCurrent() ? { ...s, reconnecting: true } : s));
            const delay = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** Math.min(failures, 6));
            await sleep(delay, controller.signal);
            if (!isCurrent()) return;
          }
          attempt += 1;

          // Per-socket abort so the stale watchdog / visibility handler can
          // force a reopen without ending the whole attach loop.
          const socket = new AbortController();
          socketAbortRef.current = socket;
          const onOuterAbort = () => socket.abort();
          controller.signal.addEventListener('abort', onOuterAbort, { once: true });
          lastEventAtRef.current = Date.now();

          // Replay semantics: the first delta after (re)opening REPLACES the
          // locally accumulated text (the server resends from event 0).
          let firstDelta = true;
          let terminal = false;
          let gotAnyEvent = false;

          try {
            for await (const event of openConversationStream({ conversationId, signal: socket.signal })) {
              if (!isCurrent()) return;
              lastEventAtRef.current = Date.now();
              if (!gotAnyEvent) {
                gotAnyEvent = true;
                failures = 0;
                setState((s) => (isCurrent() && s.reconnecting ? { ...s, reconnecting: false } : s));
              }
              switch (event.type) {
                case 'ping':
                case 'start':
                  break;
                case 'delta': {
                  const replace = firstDelta;
                  firstDelta = false;
                  setState((s) =>
                    isCurrent() ? { ...s, text: replace ? event.text : s.text + event.text, tool: null } : s
                  );
                  break;
                }
                case 'tool':
                  setState((s) =>
                    isCurrent() ? { ...s, tool: { name: event.name, summary: event.summary } } : s
                  );
                  break;
                case 'done': {
                  terminal = true;
                  const level = event.thinking_level ?? null;
                  setState((s) =>
                    isCurrent() ? { ...s, active: false, reconnecting: false, thinkingLevel: level } : s
                  );
                  await callbacks?.onDone?.(level);
                  break;
                }
                case 'error':
                  terminal = true;
                  setState((s) => (isCurrent() ? { ...s, active: false, reconnecting: false } : s));
                  await callbacks?.onError?.(event.message, event.code);
                  break;
                case 'idle':
                  terminal = true;
                  setState((s) => (isCurrent() ? { ...s, active: false, reconnecting: false } : s));
                  await callbacks?.onIdle?.();
                  break;
              }
            }
            if (terminal) return;
            // Generator returned without a terminal event and without throwing
            // (older backend) — treat like an interruption.
            failures = gotAnyEvent ? 0 : failures + 1;
          } catch (err) {
            if (!isCurrent()) return;
            const e = err as Error;
            if (e?.name === 'AbortError') {
              // Our own forced reopen (stale watchdog / visibility). Not a failure.
            } else if (e instanceof StreamInterruptedError) {
              // Socket closed mid-turn. Reattach; a socket that delivered
              // events counts as progress, so don't escalate the backoff.
              if (!gotAnyEvent) failures += 1;
            } else {
              // Network error (fetch rejected) — offline, DNS, proxy 502…
              failures += 1;
            }
          } finally {
            controller.signal.removeEventListener('abort', onOuterAbort);
            if (socketAbortRef.current === socket) socketAbortRef.current = null;
          }

          if (failures >= MAX_CONSECUTIVE_FAILURES) {
            setState((s) => (isCurrent() ? { ...s, active: false, reconnecting: false } : s));
            await callbacks?.onError?.('اتصال به سرور برقرار نشد. صفحه را تازه کنید.', 'stream_error');
            return;
          }
        }
      })();
    },
    [stop]
  );

  /** Force the current socket closed so the attach loop reopens it immediately. */
  const forceReopen = useCallback(() => {
    socketAbortRef.current?.abort();
  }, []);

  // Stale watchdog + foreground/online triggers. Only meaningful while a
  // reader is attached and the turn hasn't finished.
  const active = state.active;
  useEffect(() => {
    if (!active) return;

    const check = () => {
      if (!socketAbortRef.current) return;
      if (Date.now() - lastEventAtRef.current > STALE_AFTER_MS) forceReopen();
    };
    const timer = window.setInterval(check, 5_000);

    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      // Mobile browsers freeze/kill background fetches without signalling
      // anything; a reopen after even a short absence is cheap (replay) and
      // guarantees the bubble is current.
      if (Date.now() - lastEventAtRef.current > 5_000) forceReopen();
    };
    const onOnline = () => forceReopen();
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('online', onOnline);
    window.addEventListener('pageshow', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('online', onOnline);
      window.removeEventListener('pageshow', onVisible);
    };
  }, [active, forceReopen]);

  useEffect(() => () => stop(), [stop]);

  return { state, attach, stop, reset };
}
