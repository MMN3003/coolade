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
import Tooltip from '@mui/material/Tooltip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import GroupIcon from '@mui/icons-material/GroupOutlined';
import CableIcon from '@mui/icons-material/CableOutlined';
import { useTranslation } from 'react-i18next';
import { adminServicesApi, adminUsersApi } from '@/api/endpoints';
import type { OrgService, ServiceGrantLevel } from '@/api/types';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

interface ServiceForm {
  name: string;
  description: string;
  conn_read: string;
  conn_write: string;
  enabled: boolean;
}

const emptyForm: ServiceForm = {
  name: '',
  description: '',
  conn_read: '',
  conn_write: '',
  enabled: true,
};

export default function AdminServicesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const servicesQuery = useQuery({ queryKey: ['admin', 'services'], queryFn: adminServicesApi.list });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ServiceForm>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<OrgService | null>(null);
  const [grantsTarget, setGrantsTarget] = useState<OrgService | null>(null);
  const [snack, setSnack] = useState<string | null>(null);

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm);
    setDialogOpen(true);
  }

  function openEdit(svc: OrgService) {
    setEditingId(svc.id);
    setForm({
      name: svc.name,
      description: svc.description ?? '',
      conn_read: '',
      conn_write: '',
      enabled: svc.enabled,
    });
    setDialogOpen(true);
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      if (editingId == null) {
        return adminServicesApi.create({
          name: form.name.trim(),
          description: form.description.trim() || null,
          kind: 'sql',
          conn_read: form.conn_read.trim(),
          conn_write: form.conn_write.trim() || null,
        });
      }
      return adminServicesApi.update(editingId, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        enabled: form.enabled,
        ...(form.conn_read.trim() ? { conn_read: form.conn_read.trim() } : {}),
        ...(form.conn_write.trim() ? { conn_write: form.conn_write.trim() } : {}),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'services'] });
      setDialogOpen(false);
      setForm(emptyForm);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminServicesApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'services'] });
      setDeleteTarget(null);
    },
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => adminServicesApi.test(id),
    onSuccess: (res) => setSnack(res.message),
    onError: (err) => setSnack(getErrorMessage(err)),
  });

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('services.title')}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
          {t('services.createService')}
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        {t('services.intro')}
      </Alert>

      <Paper>
        {servicesQuery.isLoading && <LoadingState />}
        {servicesQuery.isError && (
          <ErrorState
            message={getErrorMessage(servicesQuery.error)}
            onRetry={() => servicesQuery.refetch()}
          />
        )}
        {servicesQuery.data && servicesQuery.data.length === 0 && (
          <Typography color="text.secondary" sx={{ p: 3, textAlign: 'center' }}>
            {t('services.noServices')}
          </Typography>
        )}
        {servicesQuery.data && servicesQuery.data.length > 0 && (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t('services.name')}</TableCell>
                <TableCell>{t('services.slug')}</TableCell>
                <TableCell>{t('services.kind')}</TableCell>
                <TableCell>{t('services.grantCount')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="left">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {servicesQuery.data.map((s) => (
                <TableRow key={s.id} hover>
                  <TableCell>
                    <Typography fontWeight={600}>{s.name}</Typography>
                    {s.description && (
                      <Typography variant="caption" color="text.secondary">
                        {s.description}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <code>{s.slug}</code>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={s.kind} />
                  </TableCell>
                  <TableCell>{s.grant_count.toLocaleString('fa-IR')}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={s.enabled ? t('common.active') : t('common.inactive')}
                      color={s.enabled ? 'success' : 'default'}
                    />
                  </TableCell>
                  <TableCell align="left">
                    <Stack direction="row" spacing={0.5}>
                      <Tooltip title={t('services.testConnection')}>
                        <IconButton
                          size="small"
                          disabled={testMutation.isPending}
                          onClick={() => testMutation.mutate(s.id)}
                        >
                          <CableIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('services.manageGrants')}>
                        <IconButton size="small" onClick={() => setGrantsTarget(s)}>
                          <GroupIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('common.edit')}>
                        <IconButton size="small" onClick={() => openEdit(s)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('common.delete')}>
                        <IconButton size="small" color="error" onClick={() => setDeleteTarget(s)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* Create / edit dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingId == null ? t('services.createService') : t('services.editService')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('services.name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('services.description')}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              helperText={t('services.descriptionHint')}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField select label={t('services.kind')} value="sql" fullWidth disabled>
              <MenuItem value="sql">SQL (PostgreSQL)</MenuItem>
            </TextField>
            <TextField
              label={t('services.connRead')}
              value={form.conn_read}
              onChange={(e) => setForm({ ...form, conn_read: e.target.value })}
              placeholder="postgresql://user:pass@host:5432/db"
              helperText={
                editingId == null ? t('services.connReadHint') : t('services.connRotateHint')
              }
              type="password"
              autoComplete="off"
              fullWidth
              required={editingId == null}
            />
            <TextField
              label={t('services.connWrite')}
              value={form.conn_write}
              onChange={(e) => setForm({ ...form, conn_write: e.target.value })}
              helperText={t('services.connWriteHint')}
              type="password"
              autoComplete="off"
              fullWidth
            />
            {editingId != null && (
              <FormControlLabel
                control={
                  <Switch
                    checked={form.enabled}
                    onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                  />
                }
                label={t('services.enabled')}
              />
            )}
            {saveMutation.isError && (
              <Alert severity="error">{getErrorMessage(saveMutation.error)}</Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              !form.name.trim() ||
              (editingId == null && !form.conn_read.trim()) ||
              saveMutation.isPending
            }
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('services.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('services.deleteConfirmBody', { name: deleteTarget?.name ?? '' })}
          </DialogContentText>
          {deleteMutation.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
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
            onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      {grantsTarget && (
        <GrantsDialog service={grantsTarget} onClose={() => setGrantsTarget(null)} />
      )}

      <Snackbar
        open={!!snack}
        autoHideDuration={6000}
        onClose={() => setSnack(null)}
        message={snack ?? ''}
      />
    </Box>
  );
}

function GrantsDialog({ service, onClose }: { service: OrgService; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const grantsQuery = useQuery({
    queryKey: ['admin', 'services', service.id, 'grants'],
    queryFn: () => adminServicesApi.grants(service.id),
  });
  const usersQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: adminUsersApi.list });

  const [newUserId, setNewUserId] = useState<number | ''>('');
  const [newLevel, setNewLevel] = useState<ServiceGrantLevel>('read');

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['admin', 'services', service.id, 'grants'] });
    queryClient.invalidateQueries({ queryKey: ['admin', 'services'] });
  }

  const setMutation = useMutation({
    mutationFn: ({ userId, level }: { userId: number; level: ServiceGrantLevel }) =>
      adminServicesApi.setGrant(service.id, userId, level),
    onSuccess: () => {
      refresh();
      setNewUserId('');
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (userId: number) => adminServicesApi.revokeGrant(service.id, userId),
    onSuccess: refresh,
  });

  const grantedIds = new Set((grantsQuery.data ?? []).map((g) => g.user_id));
  const candidates = (usersQuery.data ?? []).filter((u) => !grantedIds.has(u.id) && u.is_active);
  const levelLabel: Record<ServiceGrantLevel, string> = {
    read: t('services.levelRead'),
    write: t('services.levelWrite'),
  };

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('services.grantsTitle', { name: service.name })}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={1}>
            <TextField
              select
              label={t('services.user')}
              value={newUserId}
              onChange={(e) => setNewUserId(Number(e.target.value))}
              sx={{ flex: 1 }}
              size="small"
            >
              {candidates.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.display_name || u.username}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t('services.level')}
              value={newLevel}
              onChange={(e) => setNewLevel(e.target.value as ServiceGrantLevel)}
              sx={{ width: 170 }}
              size="small"
            >
              <MenuItem value="read">{t('services.levelRead')}</MenuItem>
              <MenuItem value="write" disabled>
                {t('services.levelWriteSoon')}
              </MenuItem>
            </TextField>
            <Button
              variant="contained"
              disabled={newUserId === '' || setMutation.isPending}
              onClick={() =>
                newUserId !== '' && setMutation.mutate({ userId: newUserId, level: newLevel })
              }
            >
              {t('services.grant')}
            </Button>
          </Stack>

          {grantsQuery.isLoading && <LoadingState />}
          {grantsQuery.data && grantsQuery.data.length === 0 && (
            <Typography color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
              {t('services.noGrants')}
            </Typography>
          )}
          {grantsQuery.data && grantsQuery.data.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('services.user')}</TableCell>
                  <TableCell>{t('services.level')}</TableCell>
                  <TableCell align="left" />
                </TableRow>
              </TableHead>
              <TableBody>
                {grantsQuery.data.map((g) => (
                  <TableRow key={g.user_id}>
                    <TableCell>{g.display_name || g.username}</TableCell>
                    <TableCell>
                      <Chip size="small" label={levelLabel[g.level]} color="primary" variant="outlined" />
                    </TableCell>
                    <TableCell align="left">
                      <Tooltip title={t('services.revoke')}>
                        <IconButton
                          size="small"
                          color="error"
                          disabled={revokeMutation.isPending}
                          onClick={() => revokeMutation.mutate(g.user_id)}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {(setMutation.isError || revokeMutation.isError) && (
            <Alert severity="error">
              {getErrorMessage(setMutation.error ?? revokeMutation.error)}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
