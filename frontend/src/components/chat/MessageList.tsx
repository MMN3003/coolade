import { useEffect, useRef } from 'react';
import { useTheme } from '@mui/material/styles';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import ReplayIcon from '@mui/icons-material/Replay';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import { useTranslation } from 'react-i18next';
import type { Message, ThinkingLevel } from '@/api/types';
import MarkdownMessage from './MarkdownMessage';
import EmptyState from '@/components/common/EmptyState';
import { SURFACE_2 } from '@/theme/theme';

/** Local (not-yet-persisted) live turn state, driven by useConversationStream. */
export interface LiveTurnState {
  /** id of the assistant message row currently being streamed/replayed; null when idle. */
  assistantMessageId: number | null;
  text: string;
  /** pre-formatted Persian status line for the current tool_use step, if any. */
  toolStatus: string | null;
}

interface Props {
  messages: Message[];
  live: LiveTurnState;
  onRetry: (messageId: number) => void;
  /** id of a message a retry POST is in flight for (before the stream attaches). */
  retryPendingId?: number | null;
}

function thinkingLabel(t: (k: string) => string, level: ThinkingLevel): string {
  return level === 'deep' ? t('chat.thinkingDeep') : t('chat.thinkingStandard');
}

export default function MessageList({ messages, live, onRetry, retryPendingId }: Props) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);
  // PHYSICAL alignment by product decision (2026-09-01): user bubbles hug the
  // LEFT edge, assistant replies the RIGHT edge — in both fa/rtl and en/ltr.
  // Expressed via flex-start/flex-end AGAINST the theme direction because the
  // stylis RTL plugin flips physical 'left'/'right' keywords in emitted CSS
  // (verified 2026-09-02: justifyContent:'left' rendered on the right).
  const isRtl = useTheme().direction === 'rtl';
  const userJustify = isRtl ? 'flex-end' : 'flex-start'; // → physical LEFT
  const assistantJustify = isRtl ? 'flex-start' : 'flex-end'; // → physical RIGHT

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, live.text, live.toolStatus]);

  // The message row for the live/replayed turn already exists in `messages`
  // (created status='streaming' the moment the turn was accepted, or already
  // persisted before we reattached) — render it via the live overlay instead
  // of its (possibly still-empty) canonical content, so replay and a brand
  // new send look identical (TECH.md §5.3/§9).
  const liveId = live.assistantMessageId;
  const rendered = liveId ? messages.filter((m) => m.id !== liveId) : messages;
  const showLiveBubble = liveId !== null;

  const lastMessage = messages[messages.length - 1];

  if (rendered.length === 0 && !showLiveBubble) {
    return <EmptyState message={t('chat.noMessages')} />;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, p: 2, maxWidth: 760, mx: 'auto', width: '100%' }}>
      {rendered.map((m) => {
        const isUser = m.role === 'user';
        const isFailed = m.role === 'assistant' && m.status === 'failed';
        // Retry is only offered on the latest turn per the backend guard (§5.1).
        const isRetryable = isFailed && lastMessage?.id === m.id;
        const isRetrying = retryPendingId === m.id;
        const showThinkingBadge =
          m.role === 'assistant' && !isFailed && m.thinking_level && m.thinking_level !== 'off';

        return (
          <Box key={m.id} sx={{ display: 'flex', justifyContent: isUser ? userJustify : assistantJustify }}>
            <Paper
              elevation={0}
              sx={{
                px: isUser ? 2 : 1.5,
                py: 1,
                maxWidth: '88%',
                width: 'auto',
                borderRadius: 4,
                bgcolor: isUser ? SURFACE_2 : 'background.paper',
                color: 'text.primary',
                border: 1,
                borderColor: isFailed ? 'error.main' : isUser ? 'transparent' : 'divider',
              }}
            >
              {m.role === 'assistant' ? (
                isFailed ? (
                  <Box>
                    <Typography color="error.main" variant="body2">
                      {m.error_reason || t('chat.genericFailedReason')}
                    </Typography>
                    {isRetryable && (
                      <Button
                        size="small"
                        color="error"
                        variant="outlined"
                        startIcon={isRetrying ? <CircularProgress size={14} /> : <ReplayIcon fontSize="small" />}
                        disabled={isRetrying}
                        onClick={() => onRetry(m.id)}
                        sx={{ mt: 1 }}
                      >
                        {t('chat.retry')}
                      </Button>
                    )}
                  </Box>
                ) : (
                  <Box>
                    <MarkdownMessage content={m.content} />
                    {showThinkingBadge && (
                      <Chip
                        size="small"
                        variant="outlined"
                        icon={<PsychologyOutlinedIcon fontSize="inherit" />}
                        label={t('chat.thinkingBadge', { level: thinkingLabel(t, m.thinking_level!) })}
                        sx={{ mt: 1, height: 22, fontSize: '0.7rem' }}
                      />
                    )}
                  </Box>
                )
              ) : (
                <Typography sx={{ whiteSpace: 'pre-wrap' }}>{m.content}</Typography>
              )}
            </Paper>
          </Box>
        );
      })}

      {showLiveBubble && (
        <Box sx={{ display: 'flex', justifyContent: assistantJustify }}>
          <Paper
            elevation={0}
            sx={{
              px: 1.5,
              py: 1,
              maxWidth: '88%',
              width: live.text ? 'auto' : '60%',
              borderRadius: 4,
              bgcolor: 'background.paper',
              border: 1,
              borderColor: 'divider',
            }}
          >
            {live.text ? (
              <MarkdownMessage content={live.text} />
            ) : (
              !live.toolStatus && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.secondary' }}>
                  <CircularProgress size={14} />
                  <Typography variant="body2">{t('chat.assistantThinking')}</Typography>
                </Box>
              )
            )}
            {live.toolStatus && (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  color: 'text.secondary',
                  mt: live.text ? 1 : 0,
                }}
              >
                <CircularProgress size={12} />
                <Typography variant="caption">{live.toolStatus}</Typography>
              </Box>
            )}
          </Paper>
        </Box>
      )}
      <div ref={bottomRef} />
    </Box>
  );
}
