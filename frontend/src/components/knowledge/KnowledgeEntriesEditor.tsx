import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import GavelIcon from '@mui/icons-material/GavelOutlined';
import LightbulbIcon from '@mui/icons-material/LightbulbOutlined';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesomeOutlined';
import LockIcon from '@mui/icons-material/LockOutlined';
import { useTranslation } from 'react-i18next';
import type { KnowledgeEntriesApi } from '@/api/endpoints';
import type { KnowledgeEntry, KnowledgeKind } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import EmptyState from '@/components/common/EmptyState';

interface FormState {
  kind: KnowledgeKind;
  title: string;
  content: string;
}

const emptyForm: FormState = { kind: 'knowledge', title: '', content: '' };

/**
 * amendment-7 (docs/KNOWLEDGE.md) — the one list/edit component for every
 * knowledge scope. The page decides WHICH scope by passing a `KnowledgeEntriesApi`
 * (user / user×service / team / admin variants from `knowledgeApi` /
 * `adminKnowledgeApi`); the component only knows entries. Entries flagged
 * `admin_locked` (authored by an admin about this user) render read-only.
 */
export default function KnowledgeEntriesEditor({
  api,
  queryKey,
  hint,
  dense = false,
}: {
  api: KnowledgeEntriesApi;
  queryKey: readonly unknown[];
  hint?: string;
  dense?: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const entriesQuery = useQuery({ queryKey, queryFn: api.list });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgeEntry | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeEntry | null>(null);
  const [filter, setFilter] = useState('');

  function refresh() {
    queryClient.invalidateQueries({ queryKey });
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const body = { kind: form.kind, title: form.title.trim(), content: form.content.trim() };
      return editing ? api.update(editing.id, body) : api.create(body);
    },
    onSuccess: () => {
      refresh();
      setDialogOpen(false);
      setEditing(null);
      setForm(emptyForm);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => api.update(id, { enabled }),
    onSuccess: refresh,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.remove(id),
    onSuccess: () => {
      refresh();
      setDeleteTarget(null);
    },
  });

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setDialogOpen(true);
  }

  function openEdit(e: KnowledgeEntry) {
    setEditing(e);
    setForm({ kind: e.kind, title: e.title, content: e.content });
    setDialogOpen(true);
  }

  const entries = useMemo(() => {
    const all = entriesQuery.data ?? [];
    const q = filter.trim().toLowerCase();
    return q
      ? all.filter((e) => e.title.toLowerCase().includes(q) || e.content.toLowerCase().includes(q))
      : all;
  }, [entriesQuery.data, filter]);

  const kindLabel: Record<KnowledgeKind, string> = {
    rule: t('knowledge.editor.kindRule'),
    knowledge: t('knowledge.editor.kindKnowledge'),
  };

  return (
    <Box>
      {hint && (
        <Alert severity="info" sx={{ mb: 1.5 }}>
          {hint}
        </Alert>
      )}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <TextField
          size="small"
          placeholder={t('knowledge.editor.search')}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          sx={{ flex: 1 }}
        />
        {!!entriesQuery.data?.length && (
          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
            {t('knowledge.editor.count', { count: entriesQuery.data.length })}
          </Typography>
        )}
        <Button variant="contained" size="small" startIcon={<AddIcon />} onClick={openCreate}>
          {t('knowledge.editor.add')}
        </Button>
      </Stack>

      {(toggleMutation.isError || deleteMutation.isError) && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {getErrorMessage(toggleMutation.error ?? deleteMutation.error)}
        </Alert>
      )}

      <Paper variant="outlined">
        {entriesQuery.isLoading && <LoadingState />}
        {entriesQuery.isError && (
          <ErrorState message={getErrorMessage(entriesQuery.error)} onRetry={() => entriesQuery.refetch()} />
        )}
        {entriesQuery.isSuccess && entries.length === 0 && (
          <EmptyState message={t('knowledge.editor.empty')} />
        )}
        {entries.map((e, idx) => (
          <Box
            key={e.id}
            sx={{
              p: dense ? 1.25 : 1.75,
              borderTop: idx === 0 ? 'none' : '1px solid',
              borderColor: 'divider',
              opacity: e.enabled ? 1 : 0.55,
            }}
          >
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <Box sx={{ pt: 0.25, color: e.kind === 'rule' ? 'warning.main' : 'info.main' }}>
                {e.kind === 'rule' ? <GavelIcon fontSize="small" /> : <LightbulbIcon fontSize="small" />}
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Typography fontWeight={600}>{e.title}</Typography>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={kindLabel[e.kind]}
                    color={e.kind === 'rule' ? 'warning' : 'default'}
                  />
                  {e.source === 'learned' && (
                    <Chip
                      size="small"
                      color="secondary"
                      variant="outlined"
                      icon={<AutoAwesomeIcon />}
                      label={t('knowledge.editor.learned')}
                    />
                  )}
                  {e.admin_locked && (
                    <Chip size="small" variant="outlined" icon={<LockIcon />} label={t('knowledge.editor.adminLocked')} />
                  )}
                </Stack>
                <Typography
                  variant="body2"
                  sx={{ whiteSpace: 'pre-wrap', mt: 0.5, color: 'text.primary' }}
                >
                  {e.content}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatPersianDateTime(e.updated_at)}
                </Typography>
              </Box>
              <Stack direction="row" spacing={0} alignItems="center">
                <Tooltip title={t('knowledge.editor.enabled')}>
                  <Switch
                    size="small"
                    checked={e.enabled}
                    disabled={e.admin_locked || toggleMutation.isPending}
                    onChange={(ev) => toggleMutation.mutate({ id: e.id, enabled: ev.target.checked })}
                  />
                </Tooltip>
                <Tooltip title={t('common.edit')}>
                  <span>
                    <IconButton size="small" disabled={e.admin_locked} onClick={() => openEdit(e)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title={t('common.delete')}>
                  <span>
                    <IconButton
                      size="small"
                      color="error"
                      disabled={e.admin_locked}
                      onClick={() => setDeleteTarget(e)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </Stack>
            </Stack>
          </Box>
        ))}
      </Paper>

      {/* create / edit */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editing ? t('knowledge.editor.edit') : t('knowledge.editor.add')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('knowledge.editor.kind')}
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value as KnowledgeKind })}
              helperText={
                form.kind === 'rule' ? t('knowledge.editor.kindRuleHint') : t('knowledge.editor.kindKnowledgeHint')
              }
              fullWidth
            >
              <MenuItem value="rule">{t('knowledge.editor.kindRule')}</MenuItem>
              <MenuItem value="knowledge">{t('knowledge.editor.kindKnowledge')}</MenuItem>
            </TextField>
            <TextField
              label={t('knowledge.editor.titleField')}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              inputProps={{ maxLength: 200 }}
              fullWidth
              required
              autoFocus
            />
            <TextField
              label={t('knowledge.editor.content')}
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              helperText={t('knowledge.editor.contentHint')}
              fullWidth
              multiline
              minRows={3}
              maxRows={14}
              required
            />
            {saveMutation.isError && <Alert severity="error">{getErrorMessage(saveMutation.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.title.trim() || !form.content.trim() || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* delete confirm */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('knowledge.editor.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('knowledge.editor.deleteConfirmBody', { title: deleteTarget?.title ?? '' })}
          </DialogContentText>
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
