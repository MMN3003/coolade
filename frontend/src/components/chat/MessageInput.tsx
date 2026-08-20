import { useRef, useState, type KeyboardEvent } from 'react';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import CircularProgress from '@mui/material/CircularProgress';
import SendIcon from '@mui/icons-material/Send';
import AttachFileIcon from '@mui/icons-material/AttachFileOutlined';
import { useTranslation } from 'react-i18next';
import type { AttachmentUploadResponse } from '@/api/types';
import AttachmentChip from './AttachmentChip';

interface Props {
  disabled?: boolean;
  sending?: boolean;
  uploading?: boolean;
  pendingAttachments: AttachmentUploadResponse[];
  onRemovePendingAttachment: (id: number) => void;
  onAttachFile: (file: File) => void;
  onSend: (content: string) => void;
}

export default function MessageInput({
  disabled,
  sending,
  uploading,
  pendingAttachments,
  onRemovePendingAttachment,
  onAttachFile,
  onSend,
}: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled || sending) return;
    onSend(trimmed);
    setValue('');
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onAttachFile(file);
    e.target.value = '';
  }

  return (
    <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
      {pendingAttachments.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
          {pendingAttachments.map((a) => (
            <AttachmentChip key={a.id} attachment={a} onDelete={() => onRemovePendingAttachment(a.id)} />
          ))}
        </Box>
      )}
      <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
        <input ref={fileInputRef} type="file" hidden onChange={handleFileChange} />
        <Tooltip title={t('chat.attachFile')}>
          <span>
            <IconButton
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled || uploading}
            >
              {uploading ? <CircularProgress size={20} /> : <AttachFileIcon />}
            </IconButton>
          </span>
        </Tooltip>
        <TextField
          multiline
          maxRows={8}
          fullWidth
          size="small"
          placeholder={t('chat.typeMessage')}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <Tooltip title={t('chat.send')}>
          <span>
            <IconButton
              color="primary"
              onClick={handleSend}
              disabled={disabled || sending || !value.trim()}
            >
              {sending ? <CircularProgress size={20} /> : <SendIcon />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>
    </Box>
  );
}
