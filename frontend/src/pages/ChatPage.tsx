import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import { useTranslation } from 'react-i18next';
import { conversationsApi } from '@/api/endpoints';
import { ApiError } from '@/api/client';
import { useConversationStream, type ConversationStreamCallbacks } from '@/hooks/useConversationStream';
import type { AttachmentUploadResponse, Message, ThinkingLevel } from '@/api/types';
import { useAuthStore } from '@/store/authStore';
import { getErrorMessage } from '@/utils/errors';
import { formatPersianDateTime } from '@/utils/date';
import ConversationSidebar from '@/components/chat/ConversationSidebar';
import ModelPicker from '@/components/chat/ModelPicker';
import ThinkingLevelPicker from '@/components/chat/ThinkingLevelPicker';
import MessageList from '@/components/chat/MessageList';
import MessageInput from '@/components/chat/MessageInput';
import WorkspaceFilesPanel from '@/components/chat/WorkspaceFilesPanel';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

/**
 * اصلاحیهٔ ۲ / Issue A+C+D (docs/TECH.md §5.1, §5.3, §5.7, §8, §9).
 *
 * Send/retry cycle: `POST messages`/`POST .../retry` are now plain 202
 * acceptances (no inline SSE) — the reply is ALWAYS consumed via
 * `GET .../stream` afterwards (`useConversationStream`, `api/sse.ts`).
 * Opening a conversation that's already `generating` auto-attaches to the
 * same stream, replaying from the start of the turn, so a reload or a tab
 * switch never loses the in-progress reply. Switching to a DIFFERENT
 * conversation only tears down the local reader — the backend turn for the
 * conversation you left keeps running and can be reattached later.
 */
export default function ChatPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { conversationId: conversationIdParam } = useParams();
  const conversationId = conversationIdParam ? Number(conversationIdParam) : undefined;

  const allowedModels = useAuthStore((s) => s.user?.allowed_models) ?? [];
  // Issue D: cap from /api/auth/me. Falls back to 'standard' (the DB default)
  // if the field isn't present yet — e.g. against a not-yet-upgraded backend.
  const maxThinkingLevel: ThinkingLevel = useAuthStore((s) => s.user?.max_thinking_level) ?? 'standard';

  const conversationQuery = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => conversationsApi.get(conversationId!),
    enabled: !!conversationId,
  });

  const updateModelMutation = useMutation({
    mutationFn: (modelKey: string) => conversationsApi.update(conversationId!, { model_key: modelKey }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] }),
  });

  // Issue D: selecting a level is sticky — persisted as the conversation's
  // default via PATCH, and applied to the next message via the body field.
  const updateThinkingLevelMutation = useMutation({
    mutationFn: (level: ThinkingLevel) => conversationsApi.update(conversationId!, { thinking_level: level }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] }),
  });

  const [newChatModelKey, setNewChatModelKey] = useState<string | null>(allowedModels[0] ?? null);
  useEffect(() => {
    if (!newChatModelKey && allowedModels.length > 0) setNewChatModelKey(allowedModels[0]);
  }, [allowedModels, newChatModelKey]);

  const [newChatThinkingLevel, setNewChatThinkingLevel] = useState<ThinkingLevel>('standard');

  const selectedModelKey = conversationId ? conversationQuery.data?.model_key ?? null : newChatModelKey;
  const selectedThinkingLevel: ThinkingLevel = conversationId
    ? conversationQuery.data?.thinking_level ?? 'standard'
    : newChatThinkingLevel;

  const [optimisticUserMessage, setOptimisticUserMessage] = useState<Message | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [retryPendingId, setRetryPendingId] = useState<number | null>(null);
  const [pendingAttachments, setPendingAttachments] = useState<AttachmentUploadResponse[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  // اصلاحیهٔ ۳ / Issue E: when a send/retry hits the rolling 5h cap (§5.8),
  // best-effort disable the send button until the window partially frees up
  // (mirrors "retry button disabled until reset_5h_at" for the failed-bubble
  // case — this rejection happens at the pre-check §5.1[۴], before any
  // message row/retry-bubble exists, so there is no bubble to attach the
  // disabled state to; the composer itself is the closest equivalent).
  const [quota5hBlockedUntil, setQuota5hBlockedUntil] = useState<string | null>(null);

  const stream = useConversationStream();
  const justCreatedIdRef = useRef<number | null>(null);
  const autoAttachedForRef = useRef<number | null>(null);

  // Finalize a turn (done/error/idle): refresh canonical messages + sidebar +
  // quota, then drop the local live overlay. `stream.reset()` only tears down
  // OUR reader; the turn itself is already finished server-side by this point.
  async function finishTurn(invalidateFiles: boolean) {
    if (conversationId) {
      await queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] });
      await queryClient.refetchQueries({ queryKey: ['conversation', conversationId] });
    }
    queryClient.invalidateQueries({ queryKey: ['conversations'] });
    queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
    if (invalidateFiles) queryClient.invalidateQueries({ queryKey: ['workspace', 'files'] });
    setOptimisticUserMessage(null);
    stream.reset();
  }

  const streamCallbacks: ConversationStreamCallbacks = {
    onDone: () => finishTurn(true),
    onError: (message) => {
      // The failure is persisted server-side (status='failed' + error_reason)
      // and will render as a retry-able bubble once we refetch; surface the
      // raw message too so a pre-persistence failure (e.g. the /stream
      // endpoint itself not existing yet on an un-upgraded backend) isn't silent.
      setSendError(message);
      return finishTurn(false);
    },
    onIdle: () => finishTurn(false),
  };

  // Conversation switch: tear down OUR reader only — the other conversation's
  // turn (if any) keeps running server-side and can be reattached later.
  useEffect(() => {
    if (justCreatedIdRef.current === conversationId) {
      justCreatedIdRef.current = null;
      return;
    }
    stream.reset();
    setOptimisticUserMessage(null);
    setPendingAttachments([]);
    setSendError(null);
    setRetryPendingId(null);
    setQuota5hBlockedUntil(null);
    autoAttachedForRef.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => () => stream.stop(), []); // eslint-disable-line react-hooks/exhaustive-deps

  // اصلاحیهٔ ۳ / Issue E: auto-clear the composer lock once the rolling
  // window has (at least partially) freed up, so the user isn't stuck
  // disabled forever without touching anything.
  useEffect(() => {
    if (!quota5hBlockedUntil) return;
    const ms = new Date(quota5hBlockedUntil).getTime() - Date.now();
    if (ms <= 0) {
      setQuota5hBlockedUntil(null);
      return;
    }
    const timer = window.setTimeout(() => setQuota5hBlockedUntil(null), ms);
    return () => window.clearTimeout(timer);
  }, [quota5hBlockedUntil]);

  // Opening a conversation that's already generating: auto-attach and replay
  // from the start of the turn (TECH.md §9 — "انگار هیچ‌وقت قطع نشده").
  useEffect(() => {
    if (!conversationId || !conversationQuery.data) return;
    if (stream.state.assistantMessageId !== null) return; // already attached/attaching
    if (autoAttachedForRef.current === conversationId) return; // already tried this navigation
    const data = conversationQuery.data;
    const lastMsg = data.messages[data.messages.length - 1];
    const isGenerating = data.generating || (lastMsg?.role === 'assistant' && lastMsg.status === 'streaming');
    if (isGenerating) {
      autoAttachedForRef.current = conversationId;
      stream.attach(conversationId, lastMsg?.role === 'assistant' ? lastMsg.id : null, streamCallbacks);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, conversationQuery.data]);

  const canonicalMessages = useMemo(() => conversationQuery.data?.messages ?? [], [conversationQuery.data]);
  const displayMessages = optimisticUserMessage ? [...canonicalMessages, optimisticUserMessage] : canonicalMessages;

  const isBusy = stream.state.assistantMessageId !== null;
  const quota5hBlocked = !!quota5hBlockedUntil && new Date(quota5hBlockedUntil).getTime() > Date.now();

  /** اصلاحیهٔ ۳ / Issue E (TECH.md §5.8): the distinct 5h-cap message, with the reset time appended if known. */
  function describeQuota5hError(err: ApiError): string {
    return err.reset5hAt
      ? t('chat.quotaExceeded5hWithReset', { time: formatPersianDateTime(err.reset5hAt) })
      : t('chat.quotaExceeded5h');
  }

  async function ensureConversationId(): Promise<number | null> {
    if (conversationId) return conversationId;
    if (!newChatModelKey) return null;
    const conv = await conversationsApi.create({ model_key: newChatModelKey });
    justCreatedIdRef.current = conv.id;
    queryClient.invalidateQueries({ queryKey: ['conversations'] });
    navigate(`/chat/${conv.id}`, { replace: true });
    return conv.id;
  }

  async function handleAttachFile(file: File) {
    setUploadError(null);
    const id = await ensureConversationId();
    if (!id) return;
    setUploading(true);
    try {
      const attachment = await conversationsApi.uploadAttachment(id, file);
      setPendingAttachments((prev) => [...prev, attachment]);
    } catch (err) {
      setUploadError(getErrorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  function toolStatusLabel(tool: { name: string; summary: string } | null): string | null {
    if (!tool) return null;
    const known: Record<string, string> = {
      Write: t('chat.toolWrite'),
      Edit: t('chat.toolEdit'),
      Read: t('chat.toolRead'),
    };
    const base = known[tool.name] ?? t('chat.toolWorking', { name: tool.name });
    return tool.summary ? `${base} ${tool.summary}` : base;
  }

  async function handleSend(content: string) {
    setSendError(null);
    const id = await ensureConversationId();
    if (!id) return;

    setOptimisticUserMessage({
      id: -1,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      status: 'complete',
    });
    // Uploaded attachments are already in the workspace; the send body only
    // needs {content, thinking_level?} per the contract — just clear the chips.
    setPendingAttachments([]);

    try {
      const accepted = await conversationsApi.sendMessage(id, {
        content,
        thinking_level: selectedThinkingLevel,
      });
      stream.attach(id, accepted.assistant_message_id, streamCallbacks);
    } catch (err) {
      setOptimisticUserMessage(null);
      if (err instanceof ApiError && err.code === 'chat_busy') {
        setSendError(t('chat.chatBusy'));
      } else if (err instanceof ApiError && err.code === 'quota_exceeded_5h') {
        // اصلاحیهٔ ۳ / Issue E: distinct copy from the weekly quota_exceeded
        // message (§5.8) + best-effort composer lock until reset_5h_at.
        setSendError(describeQuota5hError(err));
        if (err.reset5hAt) setQuota5hBlockedUntil(err.reset5hAt);
      } else {
        setSendError(getErrorMessage(err, t('chat.streamError')));
      }
    }
  }

  async function handleRetry(messageId: number) {
    if (!conversationId || isBusy) return;
    setSendError(null);
    setRetryPendingId(messageId);
    try {
      const accepted = await conversationsApi.retryMessage(conversationId, messageId);
      stream.attach(conversationId, accepted.assistant_message_id, streamCallbacks);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'chat_busy') {
        setSendError(t('chat.chatBusy'));
      } else if (err instanceof ApiError && err.code === 'not_retryable') {
        setSendError(t('chat.notRetryable'));
      } else if (err instanceof ApiError && err.code === 'quota_exceeded_5h') {
        setSendError(describeQuota5hError(err));
        if (err.reset5hAt) setQuota5hBlockedUntil(err.reset5hAt);
      } else {
        setSendError(getErrorMessage(err));
      }
    } finally {
      setRetryPendingId(null);
    }
  }

  function handleThinkingLevelChange(level: ThinkingLevel) {
    if (conversationId) {
      updateThinkingLevelMutation.mutate(level);
    } else {
      setNewChatThinkingLevel(level);
    }
  }

  const noModelsAllowed = allowedModels.length === 0;

  return (
    <Box sx={{ display: 'flex', height: '100%' }}>
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          borderInlineEnd: 1,
          borderColor: 'divider',
        }}
      >
        <Box sx={{ flexGrow: 1, minHeight: 0 }}>
          <ConversationSidebar activeId={conversationId} />
        </Box>
        <WorkspaceFilesPanel />
      </Box>
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Toolbar
          variant="dense"
          sx={{ borderBottom: 1, borderColor: 'divider', gap: 2, justifyContent: 'space-between' }}
        >
          <Typography variant="subtitle1" noWrap fontWeight={600}>
            {conversationQuery.data?.title ?? t('chat.untitled')}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <ThinkingLevelPicker
              value={selectedThinkingLevel}
              maxLevel={maxThinkingLevel}
              disabled={isBusy}
              onChange={handleThinkingLevelChange}
            />
            <ModelPicker
              models={allowedModels}
              value={selectedModelKey}
              disabled={isBusy}
              onChange={(modelKey) => {
                if (conversationId) updateModelMutation.mutate(modelKey);
                else setNewChatModelKey(modelKey);
              }}
            />
          </Box>
        </Toolbar>

        {noModelsAllowed && (
          <Alert severity="warning" sx={{ borderRadius: 0 }}>
            {t('chat.noModelsAllowed')}
          </Alert>
        )}
        {sendError && (
          <Alert severity="error" sx={{ borderRadius: 0 }} onClose={() => setSendError(null)}>
            {sendError}
          </Alert>
        )}
        {uploadError && (
          <Alert severity="error" sx={{ borderRadius: 0 }} onClose={() => setUploadError(null)}>
            {uploadError}
          </Alert>
        )}

        <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
          {conversationId && conversationQuery.isLoading && <LoadingState />}
          {conversationId && conversationQuery.isError && (
            <ErrorState onRetry={() => conversationQuery.refetch()} />
          )}
          {(!conversationId || conversationQuery.data) && (
            <MessageList
              messages={displayMessages}
              live={{
                assistantMessageId: stream.state.assistantMessageId,
                text: stream.state.text,
                toolStatus: toolStatusLabel(stream.state.tool),
              }}
              onRetry={handleRetry}
              retryPendingId={retryPendingId}
            />
          )}
        </Box>

        <MessageInput
          disabled={noModelsAllowed || !selectedModelKey || quota5hBlocked}
          sending={isBusy}
          uploading={uploading}
          pendingAttachments={pendingAttachments}
          onRemovePendingAttachment={(id) =>
            setPendingAttachments((prev) => prev.filter((a) => a.id !== id))
          }
          onAttachFile={handleAttachFile}
          onSend={handleSend}
        />
      </Box>
    </Box>
  );
}
