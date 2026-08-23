import { useEffect, useState } from 'react';
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
import Autocomplete from '@mui/material/Autocomplete';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import Divider from '@mui/material/Divider';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import GroupOutlinedIcon from '@mui/icons-material/GroupOutlined';
import FolderSharedOutlinedIcon from '@mui/icons-material/FolderSharedOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import PersonRemoveIcon from '@mui/icons-material/PersonRemoveOutlined';
import { useTranslation } from 'react-i18next';
import { adminTeamsApi, adminUsersApi } from '@/api/endpoints';
import type { AdminTeam, AdminUser, CreateTeamRequest, TeamRoleInTeam, UpdateTeamRequest } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

const emptyForm: CreateTeamRequest = { name: '', slug: '', description: '' };

/**
 * `/admin/teams` — CRUD for teams + member management (TECH.md v1.4 §9,
 * Issue H). Delete/create/rename mirror `AdminUsersPage`'s table+dialog
 * pattern; the members dialog lazily fetches `GET /api/admin/teams/{id}`
 * (only place the full member list is needed) and offers an autocomplete of
 * users not already on the team to add.
 */
export default function AdminTeamsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const teamsQuery = useQuery({ queryKey: ['admin', 'teams'], queryFn: adminTeamsApi.list });

  const [formOpen, setFormOpen] = useState(false);
  const [editingTeam, setEditingTeam] = useState<AdminTeam | null>(null);
  const [form, setForm] = useState<CreateTeamRequest>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<AdminTeam | null>(null);
  const [membersTeam, setMembersTeam] = useState<AdminTeam | null>(null);

  function invalidateTeams() {
    queryClient.invalidateQueries({ queryKey: ['admin', 'teams'] });
  }

  const createMutation = useMutation({
    mutationFn: (body: CreateTeamRequest) => adminTeamsApi.create(body),
    onSuccess: () => {
      invalidateTeams();
      setFormOpen(false);
      setForm(emptyForm);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: UpdateTeamRequest }) => adminTeamsApi.update(id, body),
    onSuccess: () => {
      invalidateTeams();
      setFormOpen(false);
      setEditingTeam(null);
      setForm(emptyForm);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminTeamsApi.remove(id),
    onSuccess: () => {
      invalidateTeams();
      setDeleteTarget(null);
    },
  });

  function openCreate() {
    setEditingTeam(null);
    setForm(emptyForm);
    setFormOpen(true);
  }

  function openEdit(team: AdminTeam) {
    setEditingTeam(team);
    setForm({ name: team.name, slug: team.slug, description: team.description ?? '' });
    setFormOpen(true);
  }

  function submitForm() {
    if (editingTeam) {
      updateMutation.mutate({
        id: editingTeam.id,
        body: { name: form.name, description: form.description?.trim() ? form.description.trim() : null },
      });
    } else {
      createMutation.mutate({
        name: form.name,
        slug: form.slug?.trim() ? form.slug.trim() : undefined,
        description: form.description?.trim() ? form.description.trim() : null,
      });
    }
  }

  const formMutation = editingTeam ? updateMutation : createMutation;

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('admin.teams.title')}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
          {t('admin.teams.createTeam')}
        </Button>
      </Box>

      <Paper>
        {teamsQuery.isLoading && <LoadingState />}
        {teamsQuery.isError && (
          <ErrorState message={getErrorMessage(teamsQuery.error)} onRetry={() => teamsQuery.refetch()} />
        )}
        {teamsQuery.data && (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t('admin.teams.name')}</TableCell>
                <TableCell>{t('admin.teams.slug')}</TableCell>
                <TableCell>{t('admin.teams.description')}</TableCell>
                <TableCell>{t('admin.teams.membersCount')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell align="left">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {teamsQuery.data.map((team) => (
                <TableRow key={team.id} hover>
                  <TableCell>{team.name}</TableCell>
                  <TableCell sx={{ direction: 'ltr', textAlign: 'end' }}>{team.slug}</TableCell>
                  <TableCell sx={{ maxWidth: 260 }}>
                    <Typography variant="body2" color="text.secondary" noWrap title={team.description ?? ''}>
                      {team.description || '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={new Intl.NumberFormat('fa-IR').format(team.member_count)} />
                  </TableCell>
                  <TableCell>{formatPersianDateTime(team.created_at)}</TableCell>
                  <TableCell align="left">
                    <Stack direction="row" spacing={0.5}>
                      <Tooltip title={t('admin.teams.edit')}>
                        <IconButton size="small" onClick={() => openEdit(team)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('admin.teams.manageMembers')}>
                        <IconButton size="small" onClick={() => setMembersTeam(team)}>
                          <GroupOutlinedIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('admin.teams.memory')}>
                        <IconButton size="small" onClick={() => navigate(`/admin/teams/${team.id}/memory`)}>
                          <FolderSharedOutlinedIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('common.delete')}>
                        <IconButton size="small" color="error" onClick={() => setDeleteTarget(team)}>
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

      {/* Create/edit dialog */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingTeam ? t('admin.teams.editTeam') : t('admin.teams.createTeam')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('admin.teams.name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
              required
            />
            {!editingTeam && (
              <TextField
                label={t('admin.teams.slug')}
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                helperText={t('admin.teams.slugHint')}
                fullWidth
                sx={{ direction: 'ltr' }}
              />
            )}
            <TextField
              label={t('admin.teams.description')}
              value={form.description ?? ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              fullWidth
              multiline
              minRows={2}
            />
            {formMutation.isError && <Alert severity="error">{getErrorMessage(formMutation.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!form.name || formMutation.isPending} onClick={submitForm}>
            {editingTeam ? t('common.save') : t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('admin.teams.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {t('admin.teams.deleteConfirmBody', { name: deleteTarget?.name ?? '' })}
          </Typography>
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

      {/* Members management */}
      <TeamMembersDialog team={membersTeam} onClose={() => setMembersTeam(null)} />
    </Box>
  );
}

function TeamMembersDialog({ team, onClose }: { team: AdminTeam | null; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [role, setRole] = useState<TeamRoleInTeam>('member');

  const detailQuery = useQuery({
    queryKey: ['admin', 'team', team?.id, 'detail'],
    queryFn: () => adminTeamsApi.get(team!.id),
    enabled: !!team,
  });
  const usersQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: adminUsersApi.list, enabled: !!team });

  useEffect(() => {
    setSelectedUser(null);
    setRole('member');
  }, [team?.id]);

  function invalidate() {
    if (!team) return;
    queryClient.invalidateQueries({ queryKey: ['admin', 'team', team.id, 'detail'] });
    queryClient.invalidateQueries({ queryKey: ['admin', 'teams'] });
  }

  const addMutation = useMutation({
    mutationFn: () => adminTeamsApi.addMember(team!.id, { user_id: selectedUser!.id, role_in_team: role }),
    onSuccess: () => {
      invalidate();
      setSelectedUser(null);
      setRole('member');
    },
  });

  const removeMutation = useMutation({
    mutationFn: (userId: number) => adminTeamsApi.removeMember(team!.id, userId),
    onSuccess: invalidate,
  });

  const memberIds = new Set((detailQuery.data?.members ?? []).map((m) => m.user_id));
  const candidates = (usersQuery.data ?? []).filter((u) => !memberIds.has(u.id));

  return (
    <Dialog open={!!team} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{team ? t('admin.teams.membersTitle', { name: team.name }) : ''}</DialogTitle>
      <DialogContent>
        {detailQuery.isLoading && <LoadingState />}
        {detailQuery.isError && (
          <ErrorState message={getErrorMessage(detailQuery.error)} onRetry={() => detailQuery.refetch()} />
        )}
        {detailQuery.data && (
          <>
            <List dense disablePadding>
              {detailQuery.data.members.length === 0 && (
                <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                  {t('admin.teams.noMembers')}
                </Typography>
              )}
              {detailQuery.data.members.map((m) => (
                <ListItem
                  key={m.user_id}
                  secondaryAction={
                    <Tooltip title={t('admin.teams.removeMember')}>
                      <IconButton
                        size="small"
                        edge="end"
                        disabled={removeMutation.isPending}
                        onClick={() => removeMutation.mutate(m.user_id)}
                      >
                        <PersonRemoveIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  }
                >
                  <ListItemText
                    primary={m.display_name || m.username}
                    secondary={m.role_in_team === 'lead' ? t('admin.teams.roleLead') : t('admin.teams.roleMember')}
                  />
                </ListItem>
              ))}
            </List>

            <Divider sx={{ my: 2 }} />

            <Typography variant="subtitle2" gutterBottom>
              {t('admin.teams.addMember')}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <Autocomplete
                sx={{ flexGrow: 1 }}
                options={candidates}
                value={selectedUser}
                onChange={(_, value) => setSelectedUser(value)}
                getOptionLabel={(u) => u.display_name || u.username}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                noOptionsText={t('admin.teams.allUsersAlreadyMembers')}
                renderInput={(params) => <TextField {...params} label={t('admin.teams.selectUser')} />}
              />
              <TextField
                select
                label={t('admin.teams.role')}
                value={role}
                onChange={(e) => setRole(e.target.value as TeamRoleInTeam)}
                sx={{ minWidth: 140 }}
              >
                <MenuItem value="member">{t('admin.teams.roleMember')}</MenuItem>
                <MenuItem value="lead">{t('admin.teams.roleLead')}</MenuItem>
              </TextField>
              <Button
                variant="contained"
                disabled={!selectedUser || addMutation.isPending}
                onClick={() => addMutation.mutate()}
              >
                {t('common.add')}
              </Button>
            </Stack>
            {addMutation.isError && (
              <Alert severity="error" sx={{ mt: 1.5 }}>
                {getErrorMessage(addMutation.error)}
              </Alert>
            )}
            {removeMutation.isError && (
              <Alert severity="error" sx={{ mt: 1.5 }}>
                {getErrorMessage(removeMutation.error)}
              </Alert>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
