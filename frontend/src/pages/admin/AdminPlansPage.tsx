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
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import OutlinedInput from '@mui/material/OutlinedInput';
import Checkbox from '@mui/material/Checkbox';
import ListItemText from '@mui/material/ListItemText';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import GroupAddIcon from '@mui/icons-material/GroupAddOutlined';
import { useTranslation } from 'react-i18next';
import { adminModelsApi, plansApi } from '@/api/endpoints';
import { FEATURE_KEYS, type FeatureKey, type Plan, type ThinkingLevel } from '@/api/types';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

interface PlanForm {
  name: string;
  description: string;
  limit_credits: string;
  limit_credits_5h: string;
  max_thinking_level: ThinkingLevel;
  is_active: boolean;
  model_ids: number[];
  features: FeatureKey[];
}

const emptyForm: PlanForm = {
  name: '',
  description: '',
  limit_credits: '0',
  limit_credits_5h: '',
  max_thinking_level: 'standard',
  is_active: true,
  model_ids: [],
  features: [...FEATURE_KEYS],
};

/** Sidebar labels double as the feature names (nav.* keys). */
const FEATURE_LABEL_KEY: Record<FeatureKey, string> = {
  workspaces: 'nav.workspaces',
  cli: 'nav.cli',
  usage: 'nav.usage',
  keys: 'nav.keys',
  teams: 'nav.teams',
  knowledge: 'nav.knowledge',
};

export default function AdminPlansPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const plansQuery = useQuery({ queryKey: ['admin', 'plans'], queryFn: plansApi.list });
  const modelsQuery = useQuery({ queryKey: ['admin', 'models'], queryFn: adminModelsApi.list });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<PlanForm>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<Plan | null>(null);
  const [applyTarget, setApplyTarget] = useState<Plan | null>(null);
  const [snack, setSnack] = useState<string | null>(null);

  const thinkingLabel: Record<ThinkingLevel, string> = {
    off: t('chat.thinkingOff'),
    standard: t('chat.thinkingStandard'),
    deep: t('chat.thinkingDeep'),
  };

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm);
    setDialogOpen(true);
  }

  function openEdit(plan: Plan) {
    setEditingId(plan.id);
    setForm({
      name: plan.name,
      description: plan.description ?? '',
      limit_credits: String(plan.limit_credits),
      limit_credits_5h: plan.limit_credits_5h != null ? String(plan.limit_credits_5h) : '',
      max_thinking_level: plan.max_thinking_level,
      is_active: plan.is_active,
      model_ids: plan.model_ids,
      // null on the wire = legacy «everything»; the form always edits an explicit list.
      features: plan.features ?? [...FEATURE_KEYS],
    });
    setDialogOpen(true);
  }

  function buildBody() {
    return {
      name: form.name.trim(),
      description: form.description.trim() ? form.description.trim() : null,
      limit_credits: Number(form.limit_credits),
      limit_credits_5h: form.limit_credits_5h.trim() === '' ? null : Number(form.limit_credits_5h),
      max_thinking_level: form.max_thinking_level,
      is_active: form.is_active,
      model_ids: form.model_ids,
      features: form.features,
    };
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      editingId == null ? plansApi.create(buildBody()) : plansApi.update(editingId, buildBody()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'plans'] });
      setDialogOpen(false);
      setForm(emptyForm);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => plansApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'plans'] });
      setDeleteTarget(null);
    },
  });

  const applyMutation = useMutation({
    mutationFn: (id: number) => plansApi.apply(id),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'plans'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setSnack(t('plans.applyDone', { count: res.applied_to }));
      setApplyTarget(null);
    },
  });

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('plans.title')}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
          {t('plans.createPlan')}
        </Button>
      </Box>

      <Paper>
        {plansQuery.isLoading && <LoadingState />}
        {plansQuery.isError && (
          <ErrorState message={getErrorMessage(plansQuery.error)} onRetry={() => plansQuery.refetch()} />
        )}
        {plansQuery.data && plansQuery.data.length === 0 && (
          <Typography color="text.secondary" sx={{ p: 3, textAlign: 'center' }}>
            {t('plans.noPlans')}
          </Typography>
        )}
        {plansQuery.data && plansQuery.data.length > 0 && (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t('plans.name')}</TableCell>
                <TableCell>{t('plans.monthlyLimit')}</TableCell>
                <TableCell>{t('plans.limit5h')}</TableCell>
                <TableCell>{t('plans.modelsCount')}</TableCell>
                <TableCell>{t('plans.maxThinking')}</TableCell>
                <TableCell>{t('plans.membersCount')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="left">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {plansQuery.data.map((p) => (
                <TableRow key={p.id} hover>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>{p.limit_credits.toLocaleString('fa-IR')}</TableCell>
                  <TableCell>
                    {p.limit_credits_5h != null ? p.limit_credits_5h.toLocaleString('fa-IR') : '∞'}
                  </TableCell>
                  <TableCell>{p.model_ids.length.toLocaleString('fa-IR')}</TableCell>
                  <TableCell>{thinkingLabel[p.max_thinking_level]}</TableCell>
                  <TableCell>{p.member_count.toLocaleString('fa-IR')}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={p.is_active ? t('common.active') : t('common.inactive')}
                      color={p.is_active ? 'success' : 'default'}
                    />
                  </TableCell>
                  <TableCell align="left">
                    <Stack direction="row" spacing={0.5}>
                      <Tooltip title={t('common.edit')}>
                        <IconButton size="small" onClick={() => openEdit(p)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('plans.applyToMembers')}>
                        <IconButton size="small" onClick={() => setApplyTarget(p)}>
                          <GroupAddIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('common.delete')}>
                        <IconButton size="small" color="error" onClick={() => setDeleteTarget(p)}>
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
        <DialogTitle>{editingId == null ? t('plans.createPlan') : t('plans.editPlan')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('plans.name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('plans.description')}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField
              label={t('plans.monthlyLimit')}
              type="number"
              value={form.limit_credits}
              onChange={(e) => setForm({ ...form, limit_credits: e.target.value })}
              fullWidth
            />
            <TextField
              label={t('plans.limit5h')}
              type="number"
              value={form.limit_credits_5h}
              onChange={(e) => setForm({ ...form, limit_credits_5h: e.target.value })}
              helperText={t('plans.limit5hHint')}
              placeholder="∞"
              fullWidth
            />
            <FormControl fullWidth>
              <InputLabel id="plan-models-label">{t('plans.models')}</InputLabel>
              <Select
                labelId="plan-models-label"
                multiple
                value={form.model_ids}
                onChange={(e) => setForm({ ...form, model_ids: e.target.value as number[] })}
                input={<OutlinedInput label={t('plans.models')} />}
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {(selected as number[]).map((id) => {
                      const m = (modelsQuery.data ?? []).find((mm) => mm.id === id);
                      return <Chip key={id} size="small" label={m ? m.display_name : id} />;
                    })}
                  </Box>
                )}
              >
                {(modelsQuery.data ?? []).map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    <Checkbox checked={form.model_ids.includes(m.id)} />
                    <ListItemText primary={m.display_name} secondary={m.upstream_model} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="plan-features-label">{t('plans.features')}</InputLabel>
              <Select
                labelId="plan-features-label"
                multiple
                value={form.features}
                onChange={(e) => {
                  const v = e.target.value;
                  const list = (typeof v === 'string' ? v.split(',') : v) as FeatureKey[];
                  setForm({ ...form, features: FEATURE_KEYS.filter((k) => list.includes(k)) });
                }}
                input={<OutlinedInput label={t('plans.features')} />}
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {(selected as FeatureKey[]).map((k) => (
                      <Chip key={k} size="small" label={t(FEATURE_LABEL_KEY[k])} />
                    ))}
                  </Box>
                )}
              >
                {FEATURE_KEYS.map((k) => (
                  <MenuItem key={k} value={k}>
                    <Checkbox checked={form.features.includes(k)} />
                    <ListItemText primary={t(FEATURE_LABEL_KEY[k])} />
                  </MenuItem>
                ))}
              </Select>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                {t('plans.featuresHint')}
              </Typography>
            </FormControl>
            <TextField
              select
              label={t('plans.maxThinking')}
              value={form.max_thinking_level}
              onChange={(e) =>
                setForm({ ...form, max_thinking_level: e.target.value as ThinkingLevel })
              }
              fullWidth
            >
              <MenuItem value="off">{t('chat.thinkingOff')}</MenuItem>
              <MenuItem value="standard">{t('chat.thinkingStandard')}</MenuItem>
              <MenuItem value="deep">{t('chat.thinkingDeep')}</MenuItem>
            </TextField>
            <FormControlLabel
              control={
                <Switch
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                />
              }
              label={t('plans.isActive')}
            />
            {saveMutation.isError && <Alert severity="error">{getErrorMessage(saveMutation.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.name.trim() || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('plans.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('plans.deleteConfirmBody', { name: deleteTarget?.name ?? '' })}
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

      {/* Apply-to-members confirm */}
      <Dialog open={!!applyTarget} onClose={() => setApplyTarget(null)}>
        <DialogTitle>{t('plans.applyConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('plans.applyConfirmBody', { count: applyTarget?.member_count ?? 0 })}
          </DialogContentText>
          {applyMutation.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {getErrorMessage(applyMutation.error)}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApplyTarget(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={applyMutation.isPending}
            onClick={() => applyTarget && applyMutation.mutate(applyTarget.id)}
          >
            {t('plans.applyToMembers')}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        autoHideDuration={4000}
        onClose={() => setSnack(null)}
        message={snack ?? ''}
      />
    </Box>
  );
}
