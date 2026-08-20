import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
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
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import AddIcon from '@mui/icons-material/Add';
import BlockIcon from '@mui/icons-material/BlockOutlined';
import CheckCircleIcon from '@mui/icons-material/CheckCircleOutline';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import TuneIcon from '@mui/icons-material/TuneOutlined';
import { useTranslation } from 'react-i18next';
import { adminUsersApi } from '@/api/endpoints';
import type { AdminUser, AuthSource, CreateUserRequest, UserRole } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

const emptyForm: CreateUserRequest = {
  username: '',
  password: '',
  display_name: '',
  email: '',
  role: 'user',
  auth_source: 'local',
};

export default function AdminUsersPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const listQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: adminUsersApi.list });

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateUserRequest>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);

  const createMutation = useMutation({
    mutationFn: (body: CreateUserRequest) => adminUsersApi.create(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setCreateOpen(false);
      setForm(emptyForm);
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (u: AdminUser) => adminUsersApi.update(u.id, { is_active: !u.is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminUsersApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setDeleteTarget(null);
    },
  });

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('admin.users.title')}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          {t('admin.users.createUser')}
        </Button>
      </Box>

      <Paper>
        {listQuery.isLoading && <LoadingState />}
        {listQuery.isError && (
          <ErrorState message={getErrorMessage(listQuery.error)} onRetry={() => listQuery.refetch()} />
        )}
        {listQuery.data && (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t('admin.users.username')}</TableCell>
                <TableCell>{t('admin.users.displayName')}</TableCell>
                <TableCell>{t('admin.users.role')}</TableCell>
                <TableCell>{t('admin.users.authSource')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell align="left">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {listQuery.data.map((u) => (
                <TableRow key={u.id} hover>
                  <TableCell>{u.username}</TableCell>
                  <TableCell>{u.display_name ?? '—'}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={u.role === 'admin' ? t('admin.users.roleAdmin') : t('admin.users.roleUser')}
                      color={u.role === 'admin' ? 'secondary' : 'default'}
                    />
                  </TableCell>
                  <TableCell>
                    {u.auth_source === 'ldap' ? t('admin.users.authLdap') : t('admin.users.authLocal')}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={u.is_active ? t('common.active') : t('common.inactive')}
                      color={u.is_active ? 'success' : 'default'}
                    />
                  </TableCell>
                  <TableCell>{formatPersianDateTime(u.created_at)}</TableCell>
                  <TableCell align="left">
                    <Stack direction="row" spacing={0.5}>
                      <Tooltip title={t('admin.users.editPolicyQuota')}>
                        <IconButton size="small" onClick={() => navigate(`/admin/policies?user=${u.id}`)}>
                          <TuneIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={u.is_active ? t('admin.users.deactivate') : t('admin.users.activate')}>
                        <IconButton size="small" onClick={() => toggleActiveMutation.mutate(u)}>
                          {u.is_active ? <BlockIcon fontSize="small" /> : <CheckCircleIcon fontSize="small" />}
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('common.delete')}>
                        <IconButton size="small" color="error" onClick={() => setDeleteTarget(u)}>
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

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('admin.users.createUser')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('admin.users.username')}
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('admin.users.displayName')}
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              fullWidth
            />
            <TextField
              label={t('admin.users.email')}
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              fullWidth
            />
            <TextField
              select
              label={t('admin.users.authSource')}
              value={form.auth_source}
              onChange={(e) => setForm({ ...form, auth_source: e.target.value as AuthSource })}
              fullWidth
            >
              <MenuItem value="local">{t('admin.users.authLocal')}</MenuItem>
              <MenuItem value="ldap">{t('admin.users.authLdap')}</MenuItem>
            </TextField>
            {form.auth_source === 'local' && (
              <TextField
                label={t('admin.users.password')}
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                fullWidth
                required
              />
            )}
            <TextField
              select
              label={t('admin.users.role')}
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
              fullWidth
            >
              <MenuItem value="user">{t('admin.users.roleUser')}</MenuItem>
              <MenuItem value="admin">{t('admin.users.roleAdmin')}</MenuItem>
            </TextField>
            {createMutation.isError && <Alert severity="error">{getErrorMessage(createMutation.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              !form.username || (form.auth_source === 'local' && !form.password) || createMutation.isPending
            }
            onClick={() =>
              createMutation.mutate({
                ...form,
                email: form.email?.trim() ? form.email.trim() : null,
                display_name: form.display_name?.trim() ? form.display_name.trim() : null,
              })
            }
          >
            {t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('admin.users.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('admin.users.deleteConfirmBody')}</Typography>
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
    </Box>
  );
}
