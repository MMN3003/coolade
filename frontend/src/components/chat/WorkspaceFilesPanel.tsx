import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Collapse from '@mui/material/Collapse';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import Alert from '@mui/material/Alert';
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DownloadIcon from '@mui/icons-material/DownloadOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import { workspaceApi } from '@/api/endpoints';
import type { WorkspaceFile } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${new Intl.NumberFormat('fa-IR').format(bytes)} بایت`;
  if (bytes < 1024 * 1024)
    return `${new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(bytes / 1024)} KB`;
  return `${new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(bytes / (1024 * 1024))} MB`;
}

/**
 * «فایل‌های من» — minimal collapsible panel per TECH.md v1.1 §9 (F4.6).
 * Lists the user's server-side workspace files with download + delete.
 * The chat page invalidates the ['workspace','files'] query when a chat
 * stream finishes (SSE `done` event), which auto-refreshes this list.
 */
export default function WorkspaceFilesPanel() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceFile | null>(null);

  const filesQuery = useQuery({
    queryKey: ['workspace', 'files'],
    queryFn: workspaceApi.listFiles,
  });

  const deleteMutation = useMutation({
    mutationFn: (fileId: string) => workspaceApi.remove(fileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace', 'files'] });
      setDeleteTarget(null);
    },
  });

  const files = filesQuery.data ?? [];

  return (
    <Box sx={{ borderTop: 1, borderColor: 'divider' }}>
      <Box
        onClick={() => setOpen((v) => !v)}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          py: 1,
          cursor: 'pointer',
          userSelect: 'none',
          '&:hover': { bgcolor: 'action.hover' },
        }}
      >
        <FolderOutlinedIcon fontSize="small" color="action" />
        <Typography variant="subtitle2" sx={{ flexGrow: 1 }}>
          {t('chat.myFiles')}
          {files.length > 0 && ` (${new Intl.NumberFormat('fa-IR').format(files.length)})`}
        </Typography>
        {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
      </Box>
      <Collapse in={open}>
        <Divider />
        <Box sx={{ maxHeight: 240, overflowY: 'auto' }}>
          {filesQuery.isLoading && <LoadingState />}
          {filesQuery.isError && (
            <ErrorState
              message={getErrorMessage(filesQuery.error)}
              onRetry={() => filesQuery.refetch()}
            />
          )}
          {filesQuery.isSuccess && files.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ p: 1.5, textAlign: 'center' }}>
              {t('chat.myFilesEmpty')}
            </Typography>
          )}
          {files.length > 0 && (
            <List dense disablePadding>
              {files.map((f) => (
                <ListItem
                  key={f.file_id}
                  secondaryAction={
                    <Box sx={{ display: 'flex', gap: 0.25 }}>
                      <Tooltip title={t('common.download')}>
                        <IconButton
                          size="small"
                          component="a"
                          href={workspaceApi.downloadUrl(f.file_id)}
                          download={f.name}
                        >
                          <DownloadIcon fontSize="inherit" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('common.delete')}>
                        <IconButton size="small" onClick={() => setDeleteTarget(f)}>
                          <DeleteIcon fontSize="inherit" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  }
                >
                  <ListItemText
                    primary={f.name}
                    secondary={`${formatBytes(f.size_bytes)} — ${formatPersianDateTime(f.modified_at)}`}
                    primaryTypographyProps={{ variant: 'body2', noWrap: true, sx: { direction: 'ltr', textAlign: 'end' } }}
                    secondaryTypographyProps={{ variant: 'caption' }}
                  />
                </ListItem>
              ))}
            </List>
          )}
        </Box>
      </Collapse>

      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('chat.fileDeleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('chat.fileDeleteConfirmBody', { name: deleteTarget?.name ?? '' })}
          </DialogContentText>
          {deleteMutation.isError && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {getErrorMessage(deleteMutation.error)}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>{t('common.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={deleteMutation.isPending}
            onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.file_id)}
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
