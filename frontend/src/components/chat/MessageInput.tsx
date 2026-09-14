import { useRef, useState, type KeyboardEvent } from 'react';
import Box from '@mui/material/Box';
import InputBase from '@mui/material/InputBase';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import CircularProgress from '@mui/material/CircularProgress';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import StopRoundedIcon from '@mui/icons-material/StopRounded';
import AddIcon from '@mui/icons-material/Add';
import { useTranslation } from 'react-i18next';
import type { AttachmentUploadResponse } from '@/api/types';
import AttachmentChip from './AttachmentChip';

interface Props {
  disabled?: boolean;
  sending?: boolean;
  uploading?: boolean;
  pendingAttachments: AttachmentUploadResponse[];
  onRemovePendingAttachment: (id: number) => void;
  onAttachFile: (file: File) => void | Promise<void>;
  onSend: (content: string) => void;
  /** Stop the in-progress generation (send button morphs into a stop button). */
  onStop?: () => void;
  stopping?: boolean;
}

/**
 * Large rounded (ChatGPT/GapGPT) composer: a «+» attach control, a borderless
 * auto-growing input, and an arrow send button — all inside one pill. All the
 * behavior (Enter-to-send, disabled/sending/uploading states, pending
 * attachment chips) is unchanged; only the layout/skin is new.
 */
export default function MessageInput({
  disabled,
  sending,
  uploading,
  pendingAttachments,
  onRemovePendingAttachment,
  onAttachFile,
  onSend,
  onStop,
  stopping,
}: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleSend() {
    const trimmed = value.trim();
    // A file-only turn is fine: the backend requires text OR ≥1 attachment.
    if ((!trimmed && pendingAttachments.length === 0) || disabled || sending || uploading) return;
    onSend(trimmed);
    setValue('');
  }

  function handleKeyDown(e: KeyboardEvent<HTMLElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    // Reset first: some mobile browsers won't re-fire `change` for the same
    // file otherwise, and the upload below may take a while.
    e.target.value = '';
    for (const file of files) {
      await onAttachFile(file);
    }
  }

  const canSend = !disabled && !sending && !uploading && (!!value.trim() || pendingAttachments.length > 0);

  return (
    <Box>
      {pendingAttachments.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
          {pendingAttachments.map((a) => (
            <AttachmentChip key={a.id} attachment={a} onDelete={() => onRemovePendingAttachment(a.id)} />
          ))}
        </Box>
      )}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 0.5,
          p: 0.75,
          borderRadius: 6,
          border: 1,
          borderColor: 'divider',
          bgcolor: 'background.paper',
          transition: 'border-color .15s',
          '&:focus-within': { borderColor: 'text.secondary' },
        }}
      >
        <input ref={fileInputRef} type="file" multiple hidden onChange={handleFileChange} />
        <Tooltip title={t('chat.attachFile')}>
          <span>
            <IconButton
              size="small"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled || uploading}
              sx={{ mb: 0.25 }}
            >
              {uploading ? <CircularProgress size={20} /> : <AddIcon />}
            </IconButton>
          </span>
        </Tooltip>
        <InputBase
          multiline
          maxRows={8}
          fullWidth
          placeholder={t('chat.askQuestion')}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          sx={{ px: 0.5, py: 0.75, fontSize: '0.95rem' }}
        />
        {sending && onStop ? (
          /* Generation in progress → the action button becomes STOP (saves tokens
             on a mistaken prompt — product request 2026-09-01). */
          <Tooltip title={t('chat.stopGeneration')}>
            <span>
              <IconButton
                onClick={onStop}
                disabled={stopping}
                sx={{
                  mb: 0.25,
                  bgcolor: 'error.main',
                  color: 'error.contrastText',
                  '&:hover': { bgcolor: 'error.dark' },
                  '&.Mui-disabled': { bgcolor: 'action.hover', color: 'text.disabled' },
                }}
              >
                {stopping ? <CircularProgress size={20} /> : <StopRoundedIcon />}
              </IconButton>
            </span>
          </Tooltip>
        ) : (
          <Tooltip title={sending ? t('chat.chatBusy') : t('chat.send')}>
            <span>
              <IconButton
                onClick={handleSend}
                disabled={!canSend}
                sx={{
                  mb: 0.25,
                  bgcolor: 'primary.main',
                  color: 'primary.contrastText',
                  '&:hover': { bgcolor: 'primary.dark' },
                  '&.Mui-disabled': { bgcolor: 'action.hover', color: 'text.disabled' },
                }}
              >
                {sending ? <CircularProgress size={20} /> : <ArrowUpwardIcon />}
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
}
