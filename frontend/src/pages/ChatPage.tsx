import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import { useTranslation } from 'react-i18next';
import { conversationsApi } from '@/api/endpoints';
import { streamChatMessage } from '@/api/sse';
import type { AttachmentUploadResponse, Message } from '@/api/types';
import { useAuthStore } from '@/store/authStore';
import { getErrorMessage } from '@/utils/errors';
import ConversationSidebar from '@/components/chat/ConversationSidebar';
import ModelPicker from '@/components/chat/ModelPicker';
import MessageList from '@/components/chat/MessageList';
import MessageInput from '@/components/chat/MessageInput';
import WorkspaceFilesPanel from '@/components/chat/WorkspaceFilesPanel';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

export default function ChatPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { conversationId: conversationIdParam } = useParams();
  const conversationId = conversationIdParam ? Number(conversationIdParam) : undefined;

  // Bare model keys per the contract (/api/auth/me → allowed_models: string[]).
  const allowedModels = useAuthStore((s) => s.user?.allowed_models) ?? [];

  const conversationQuery = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => conversationsApi.get(conversationId!),
    enabled: !!conversationId,
  });

  const updateModelMutation = useMutation({
    mutationFn: (modelKey: string) => conversationsApi.update(conversationId!, { model_key: modelKey }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] }),
  });

  const [newChatModelKey, setNewChatModelKey] = useState<string | null>(allowedModels[0] ?? null);
  useEffect(() => {
    if (!newChatModelKey && allowedModels.length > 0) setNewChatModelKey(allowedModels[0]);
  }, [allowedModels, newChatModelKey]);

  const selectedModelKey = conversationId ? conversationQuery.data?.model_key ?? null : newChatModelKey;

  const [optimisticUserMessage, setOptimisticUserMessage] = useState<Message | null>(null);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [pendingAttachments, setPendingAttachments] = useState<AttachmentUploadResponse[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const justCreatedIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (justCreatedIdRef.current === conversationId) {
      justCreatedIdRef.current = null;
      return;
    }
    abortControllerRef.current?.abort();
    setIsStreaming(false);
    setStreamingText(null);
    setToolStatus(null);
    setOptimisticUserMessage(null);
    setPendingAttachments([]);
    setStreamError(null);
  }, [conversationId]);

  useEffect(() => () => abortControllerRef.current?.abort(), []);

  const canonicalMessages = useMemo(() => conversationQuery.data?.messages ?? [], [conversationQuery.data]);
  const displayMessages = optimisticUserMessage ? [...canonicalMessages, optimisticUserMessage] : canonicalMessages;

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

  async function handleSend(content: string) {
    setStreamError(null);
    const id = await ensureConversationId();
    if (!id) return;

    setOptimisticUserMessage({
      id: -1,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    });
    // Uploaded attachments are already in the workspace; the send body is
    // {content} only per the contract — just clear the pending chips.
    setPendingAttachments([]);
    setIsStreaming(true);
    setStreamingText('');

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Map a CLI tool_use step (SSE `tool` event, §5.3) to a subtle Persian status line.
    function toolStatusLabel(name: string, summary: string): string {
      const known: Record<string, string> = {
        Write: t('chat.toolWrite'),
        Edit: t('chat.toolEdit'),
        Read: t('chat.toolRead'),
      };
      const base = known[name] ?? t('chat.toolWorking', { name });
      return summary ? `${base} ${summary}` : base;
    }

    try {
      for await (const event of streamChatMessage({
        conversationId: id,
        content,
        signal: controller.signal,
      })) {
        switch (event.type) {
          case 'start':
            break;
          case 'delta':
            setToolStatus(null);
            setStreamingText((prev) => (prev ?? '') + event.text);
            break;
          case 'tool':
            setToolStatus(toolStatusLabel(event.name, event.summary));
            break;
          case 'done':
            setToolStatus(null);
            // «فایل‌های من» auto-refresh when the stream finishes (change order §1).
            queryClient.invalidateQueries({ queryKey: ['workspace', 'files'] });
            break;
          case 'error':
            setStreamError(
              event.code === 'chat_busy' ? t('chat.chatBusy') : event.message || t('chat.streamError')
            );
            break;
        }
      }
    } catch (err) {
      if ((err as Error)?.name !== 'AbortError') {
        setStreamError(getErrorMessage(err, t('chat.streamError')));
      }
    } finally {
      await queryClient.invalidateQueries({ queryKey: ['conversation', id] });
      await queryClient.refetchQueries({ queryKey: ['conversation', id] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      setOptimisticUserMessage(null);
      setStreamingText(null);
      setToolStatus(null);
      setIsStreaming(false);
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
          <ModelPicker
            models={allowedModels}
            value={selectedModelKey}
            disabled={isStreaming}
            onChange={(modelKey) => {
              if (conversationId) updateModelMutation.mutate(modelKey);
              else setNewChatModelKey(modelKey);
            }}
          />
        </Toolbar>

        {noModelsAllowed && (
          <Alert severity="warning" sx={{ borderRadius: 0 }}>
            {t('chat.noModelsAllowed')}
          </Alert>
        )}
        {streamError && (
          <Alert severity="error" sx={{ borderRadius: 0 }} onClose={() => setStreamError(null)}>
            {streamError}
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
              streamingText={streamingText}
              isStreaming={isStreaming}
              toolStatus={toolStatus}
            />
          )}
        </Box>

        <MessageInput
          disabled={noModelsAllowed || !selectedModelKey}
          sending={isStreaming}
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
