import Chip from '@mui/material/Chip';
import AttachFileIcon from '@mui/icons-material/AttachFileOutlined';
import { conversationsApi } from '@/api/endpoints';

export default function AttachmentChip({
  attachment,
  onDelete,
}: {
  attachment: { id: number; filename: string };
  onDelete?: () => void;
}) {
  return (
    <Chip
      size="small"
      icon={<AttachFileIcon fontSize="small" />}
      label={attachment.filename}
      onDelete={onDelete}
      component="a"
      href={onDelete ? undefined : conversationsApi.attachmentDownloadUrl(attachment.id)}
      target={onDelete ? undefined : '_blank'}
      rel="noopener noreferrer"
      clickable={!onDelete}
      sx={{ maxWidth: 220 }}
    />
  );
}
