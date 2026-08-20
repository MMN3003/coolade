import { useEffect, useRef } from 'react';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import type { Message } from '@/api/types';
import MarkdownMessage from './MarkdownMessage';
import EmptyState from '@/components/common/EmptyState';
import { useTranslation } from 'react-i18next';

interface Props {
  messages: Message[];
  streamingText: string | null;
  isStreaming: boolean;
  /** Subtle inline status for CLI tool_use steps (SSE `tool` event, §5.3). */
  toolStatus?: string | null;
}

export default function MessageList({ messages, streamingText, isStreaming, toolStatus }: Props) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, streamingText]);

  if (messages.length === 0 && !isStreaming) {
    return <EmptyState message={t('chat.noMessages')} />;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, p: 2, maxWidth: 900, mx: 'auto', width: '100%' }}>
      {messages.map((m) => (
        <Box
          key={m.id}
          sx={{
            display: 'flex',
            justifyContent: m.role === 'user' ? 'flex-start' : 'flex-start',
          }}
        >
          <Paper
            elevation={0}
            sx={{
              px: 2,
              py: 1.25,
              maxWidth: '85%',
              bgcolor: m.role === 'user' ? 'primary.main' : 'background.paper',
              color: m.role === 'user' ? 'primary.contrastText' : 'text.primary',
              border: m.role === 'assistant' ? 1 : 0,
              borderColor: 'divider',
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              ms: m.role === 'user' ? 'auto' : 0,
            }}
          >
            {m.role === 'assistant' ? (
              <MarkdownMessage content={m.content} />
            ) : (
              <Typography sx={{ whiteSpace: 'pre-wrap' }}>{m.content}</Typography>
            )}
          </Paper>
        </Box>
      ))}

      {isStreaming && (
        <Box sx={{ display: 'flex' }}>
          <Paper
            elevation={0}
            sx={{
              px: 2,
              py: 1.25,
              maxWidth: '85%',
              border: 1,
              borderColor: 'divider',
              alignSelf: 'flex-start',
            }}
          >
            {streamingText ? (
              <MarkdownMessage content={streamingText} />
            ) : (
              !toolStatus && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.secondary' }}>
                  <CircularProgress size={14} />
                  <Typography variant="body2">{t('chat.assistantThinking')}</Typography>
                </Box>
              )
            )}
            {toolStatus && (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  color: 'text.secondary',
                  mt: streamingText ? 1 : 0,
                }}
              >
                <CircularProgress size={12} />
                <Typography variant="caption">{toolStatus}</Typography>
              </Box>
            )}
          </Paper>
        </Box>
      )}
      <div ref={bottomRef} />
    </Box>
  );
}
