import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import CircularProgress from '@mui/material/CircularProgress';
import UploadFileIcon from '@mui/icons-material/UploadFileOutlined';
import DownloadIcon from '@mui/icons-material/DownloadOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import type { TeamMemoryFile } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import EmptyState from '@/components/common/EmptyState';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${new Intl.NumberFormat('fa-IR').format(bytes)} بایت`;
  if (bytes < 1024 * 1024)
    return `${new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(bytes / 1024)} KB`;
  return `${new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(bytes / (1024 * 1024))} MB`;
}

export interface TeamMemoryApi {
  list: () => Promise<TeamMemoryFile[]>;
  upload: (file: File) => Promise<unknown>;
  downloadUrl: (fileId: string) => string;
  remove: (fileId: string) => Promise<unknown>;
}

/**
 * «حافظهٔ مشترک تیم» file manager — TECH.md v1.4 §9 (Issue I): "کامپوننت
 * فایل‌منیجرِ همان «فایل‌های من»" (list name/size/modified + download/delete),
 * extended with upload since the team-memory panel needs it (unlike the
 * chat sidebar's `WorkspaceFilesPanel`, which is read/delete-only). Used by
 * both `/teams/:id/memory` (member) and `/admin/teams/:id/memory` (admin,
 * "بدون نیاز به عضویت") — the two pages differ only in which `api` (and
 * `queryKey`) they pass in, per TECH.md §10: "ادمین از /admin/teams هم به
 * همان کامپوننت (root تیم) دسترسی دارد."
 */
export default function TeamMemoryManager({
  api,
  queryKey,
}: {
  api: TeamMemoryApi;
  queryKey: readonly unknown[];
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deleteTarget, setDeleteTarget] = useState<TeamMemoryFile | null>(null);

  const filesQuery = useQuery({ queryKey, queryFn: api.list });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.upload(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const deleteMutation = useMutation({
    mutationFn: (fileId: string) => api.remove(fileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      setDeleteTarget(null);
    },
  });

  function handleFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) uploadMutation.mutate(file);
  }

  const files = filesQuery.data ?? [];

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 2 }}>
        {t('teams.memory.lastWriterWins')}
      </Alert>

      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1.5 }}>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          onChange={handleFilePicked}
          data-testid="team-memory-file-input"
        />
        <Button
          variant="contained"
          startIcon={uploadMutation.isPending ? <CircularProgress size={16} color="inherit" /> : <UploadFileIcon />}
          disabled={uploadMutation.isPending}
          onClick={() => fileInputRef.current?.click()}
        >
          {t('teams.memory.upload')}
        </Button>
      </Box>

      {uploadMutation.isError && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {getErrorMessage(uploadMutation.error)}
        </Alert>
      )}

      <Paper variant="outlined">
        {filesQuery.isLoading && <LoadingState />}
        {filesQuery.isError && (
          <ErrorState message={getErrorMessage(filesQuery.error)} onRetry={() => filesQuery.refetch()} />
        )}
        {filesQuery.isSuccess && files.length === 0 && <EmptyState message={t('teams.memory.empty')} />}
        {files.length > 0 && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('chat.fileSize')}</TableCell>
                <TableCell>{t('chat.fileModified')}</TableCell>
                <TableCell align="left">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {files.map((f) => (
                <TableRow key={f.file_id} hover>
                  <TableCell sx={{ direction: 'ltr', textAlign: 'end' }}>{f.name}</TableCell>
                  <TableCell>{formatBytes(f.size_bytes)}</TableCell>
                  <TableCell>{formatPersianDateTime(f.modified_at)}</TableCell>
                  <TableCell align="left">
                    <Tooltip title={t('common.download')}>
                      <IconButton size="small" component="a" href={api.downloadUrl(f.file_id)} download={f.name}>
                        <DownloadIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('common.delete')}>
                      <IconButton size="small" onClick={() => setDeleteTarget(f)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('teams.memory.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('teams.memory.deleteConfirmBody', { name: deleteTarget?.name ?? '' })}
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
