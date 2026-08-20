import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import Alert from '@mui/material/Alert';
import Tooltip from '@mui/material/Tooltip';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import ContentCopyIcon from '@mui/icons-material/ContentCopyOutlined';
import AddIcon from '@mui/icons-material/Add';
import { useTranslation } from 'react-i18next';
import { keysApi } from '@/api/endpoints';
import type { ApiKeySummary } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import EmptyState from '@/components/common/EmptyState';

export default function KeysPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const listQuery = useQuery({ queryKey: ['keys'], queryFn: keysApi.list });

  const [createOpen, setCreateOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<ApiKeySummary | null>(null);

  const createMutation = useMutation({
    mutationFn: () => keysApi.create({ name: newKeyName.trim() }),
    onSuccess: (res) => {
      setCreatedKey(res.key);
      setNewKeyName('');
      queryClient.invalidateQueries({ queryKey: ['keys'] });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: number) => keysApi.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keys'] });
      setRevokeTarget(null);
    },
  });

  function handleCopy(key: string) {
    navigator.clipboard.writeText(key).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  function closeCreateDialog() {
    setCreateOpen(false);
    setCreatedKey(null);
    createMutation.reset();
  }

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('keys.title')}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          {t('keys.createKey')}
        </Button>
      </Box>

      <Paper>
        {listQuery.isLoading && <LoadingState />}
        {listQuery.isError && (
          <ErrorState message={getErrorMessage(listQuery.error)} onRetry={() => listQuery.refetch()} />
        )}
        {listQuery.data && listQuery.data.length === 0 && <EmptyState message={t('keys.noKeys')} />}
        {listQuery.data && listQuery.data.length > 0 && (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('keys.prefix')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell>{t('keys.lastUsed')}</TableCell>
                <TableCell>{t('keys.createdAt')}</TableCell>
                <TableCell align="left">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {listQuery.data.map((k) => (
                <TableRow key={k.id}>
                  <TableCell>{k.name}</TableCell>
                  <TableCell sx={{ direction: 'ltr', textAlign: 'end', fontFamily: 'monospace' }}>
                    {k.key_prefix}…
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={k.is_active ? t('common.active') : t('common.inactive')}
                      color={k.is_active ? 'success' : 'default'}
                    />
                  </TableCell>
                  <TableCell>{k.last_used_at ? formatPersianDateTime(k.last_used_at) : t('keys.never')}</TableCell>
                  <TableCell>{formatPersianDateTime(k.created_at)}</TableCell>
                  <TableCell align="left">
                    {k.is_active && (
                      <Tooltip title={t('keys.revoke')}>
                        <IconButton size="small" color="error" onClick={() => setRevokeTarget(k)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      <Dialog open={createOpen} onClose={closeCreateDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{createdKey ? t('keys.keyCreatedTitle') : t('keys.createKey')}</DialogTitle>
        <DialogContent>
          {!createdKey ? (
            <>
              <DialogContentText sx={{ mb: 2 }}>{t('keys.keyNamePlaceholder')}</DialogContentText>
              <TextField
                autoFocus
                fullWidth
                label={t('keys.keyName')}
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
              />
              {createMutation.isError && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {getErrorMessage(createMutation.error)}
                </Alert>
              )}
            </>
          ) : (
            <>
              <Alert severity="warning" sx={{ mb: 2 }}>
                {t('keys.keyCreatedWarning')}
              </Alert>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  p: 1.5,
                  bgcolor: 'action.hover',
                  borderRadius: 1,
                  direction: 'ltr',
                  fontFamily: 'monospace',
                  wordBreak: 'break-all',
                }}
              >
                <Typography sx={{ fontFamily: 'inherit', flexGrow: 1 }}>{createdKey}</Typography>
                <Tooltip title={copied ? t('common.copied') : t('common.copy')}>
                  <IconButton size="small" onClick={() => handleCopy(createdKey)}>
                    <ContentCopyIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            </>
          )}
        </DialogContent>
        <DialogActions>
          {!createdKey ? (
            <>
              <Button onClick={closeCreateDialog}>{t('common.cancel')}</Button>
              <Button
                variant="contained"
                disabled={!newKeyName.trim() || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                {t('common.create')}
              </Button>
            </>
          ) : (
            <Button onClick={closeCreateDialog} variant="contained">
              {t('common.close')}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      <Dialog open={!!revokeTarget} onClose={() => setRevokeTarget(null)}>
        <DialogTitle>{t('keys.revokeConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('keys.revokeConfirmBody')}</DialogContentText>
          {revokeMutation.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {getErrorMessage(revokeMutation.error)}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevokeTarget(null)}>{t('common.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={revokeMutation.isPending}
            onClick={() => revokeTarget && revokeMutation.mutate(revokeTarget.id)}
          >
            {t('keys.revoke')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
