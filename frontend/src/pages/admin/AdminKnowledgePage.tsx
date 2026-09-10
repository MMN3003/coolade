import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import PlayArrowIcon from '@mui/icons-material/PlayArrowOutlined';
import DownloadIcon from '@mui/icons-material/DownloadOutlined';
import { useTranslation } from 'react-i18next';
import { adminKnowledgeApi, adminModelsApi, adminServicesApi, adminTeamsApi, adminUsersApi } from '@/api/endpoints';
import type { AdminConversation, LearningRunResult } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import KnowledgeEntriesEditor from '@/components/knowledge/KnowledgeEntriesEditor';
import LoadingState from '@/components/common/LoadingState';

type TabKey = 'learning' | 'users' | 'teams' | 'services';

/**
 * `/admin/knowledge` — amendment-7 (docs/KNOWLEDGE.md). Admin view of the
 * knowledge layer: learning job settings + dataset export, and per-user /
 * per-team / per-service rule & knowledge editors (per-user-per-service lives
 * in the services page's knowledge dialog).
 */
export default function AdminKnowledgePage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabKey>('learning');

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('knowledge.admin.title')}
      </Typography>
      <Tabs value={tab} onChange={(_e, v: TabKey) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="learning" label={t('knowledge.admin.tabLearning')} />
        <Tab value="users" label={t('knowledge.admin.tabUsers')} />
        <Tab value="teams" label={t('knowledge.admin.tabTeams')} />
        <Tab value="services" label={t('knowledge.admin.tabServices')} />
      </Tabs>
      {tab === 'learning' && <LearningTab />}
      {tab === 'users' && <UsersTab />}
      {tab === 'teams' && <TeamsTab />}
      {tab === 'services' && <ServicesTab />}
    </Box>
  );
}

function StatTile({ label, value }: { label: string; value: number | string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, minWidth: 140, flex: 1 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6" fontWeight={700}>
        {typeof value === 'number' ? value.toLocaleString('fa-IR') : value}
      </Typography>
    </Paper>
  );
}

function LearningTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const statsQuery = useQuery({ queryKey: ['admin', 'knowledge', 'stats'], queryFn: adminKnowledgeApi.stats });
  const learningQuery = useQuery({
    queryKey: ['admin', 'knowledge', 'learning'],
    queryFn: adminKnowledgeApi.learning.get,
  });
  const modelsQuery = useQuery({ queryKey: ['admin', 'models'], queryFn: adminModelsApi.list });
  const [runResult, setRunResult] = useState<LearningRunResult | null>(null);
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['admin', 'knowledge'] });
  }

  const setMutation = useMutation({
    mutationFn: (body: { global_enabled?: boolean; model_key?: string | null; team_enabled?: boolean }) =>
      adminKnowledgeApi.learning.set(body),
    onSuccess: refresh,
  });
  const runMutation = useMutation({
    mutationFn: () => adminKnowledgeApi.learning.run(),
    onSuccess: (res) => {
      setRunResult(res);
      refresh();
    },
  });

  const s = learningQuery.data;
  const stats = statsQuery.data;
  const scopeLabel: Record<string, string> = {
    service: t('knowledge.admin.scopeService'),
    user_service: t('knowledge.admin.scopeUserService'),
    user: t('knowledge.admin.scopeUser'),
    team: t('knowledge.admin.scopeTeam'),
  };

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography fontWeight={600} gutterBottom>
          {t('knowledge.admin.statsTitle')}
        </Typography>
        {statsQuery.isLoading && <LoadingState />}
        {stats && (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <StatTile label={t('knowledge.admin.statTotal')} value={stats.total} />
              <StatTile label={t('knowledge.admin.statLearned')} value={stats.by_source.learned ?? 0} />
              <StatTile label={t('knowledge.admin.statConversations')} value={stats.conversations_total} />
              <StatTile label={t('knowledge.admin.statMessages')} value={stats.messages_total} />
            </Stack>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {Object.entries(stats.by_scope).map(([k, v]) => (
                <Chip key={k} size="small" variant="outlined" label={`${scopeLabel[k] ?? k}: ${v.toLocaleString('fa-IR')}`} />
              ))}
            </Stack>
          </Stack>
        )}
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography fontWeight={600}>{t('knowledge.admin.learningTitle')}</Typography>
        {learningQuery.isLoading && <LoadingState />}
        {s && (
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('knowledge.admin.learningHint', {
                interval: s.interval_minutes,
                idle: s.idle_minutes,
                min: s.min_new_user_messages,
                max: s.max_entries_per_user,
              })}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={s.global_enabled}
                    disabled={setMutation.isPending}
                    onChange={(e) => setMutation.mutate({ global_enabled: e.target.checked })}
                  />
                }
                label={t('knowledge.admin.globalEnabled')}
              />
              <TextField
                select
                size="small"
                label={t('knowledge.admin.model')}
                value={s.model_key ?? ''}
                onChange={(e) => setMutation.mutate({ model_key: e.target.value })}
                sx={{ minWidth: 260 }}
                disabled={setMutation.isPending}
              >
                <MenuItem value="">{t('knowledge.admin.modelCheapest')}</MenuItem>
                {(modelsQuery.data ?? [])
                  .filter((m) => m.is_enabled)
                  .map((m) => (
                    <MenuItem key={m.id} value={m.model_key}>
                      {m.display_name} ({m.input_weight}/{m.output_weight})
                    </MenuItem>
                  ))}
              </TextField>
              <Button
                variant="outlined"
                startIcon={<PlayArrowIcon />}
                disabled={runMutation.isPending}
                onClick={() => runMutation.mutate()}
              >
                {t('knowledge.admin.runNow')}
              </Button>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {t('knowledge.admin.lastRun')}: {s.last_run_at ? formatPersianDateTime(s.last_run_at) : t('knowledge.admin.never')}
              {s.last_run_summary ? ` — ${s.last_run_summary}` : ''}
              {' · '}
              {t('knowledge.admin.optedOut', { count: s.users_opted_out })}
            </Typography>
            {runResult && (
              <Alert severity={runResult.errors || runResult.team_errors ? 'warning' : 'success'}>
                {t('knowledge.admin.runResult', {
                  conversations: runResult.conversations,
                  added: runResult.entries_added,
                  updated: runResult.entries_updated,
                  errors: runResult.errors,
                })}{' '}
                {t('knowledge.admin.teamRunResult', {
                  teams: runResult.teams,
                  added: runResult.team_entries_added,
                  updated: runResult.team_entries_updated,
                  errors: runResult.team_errors,
                })}
              </Alert>
            )}
            {(setMutation.isError || runMutation.isError) && (
              <Alert severity="error">{getErrorMessage(setMutation.error ?? runMutation.error)}</Alert>
            )}
          </Stack>
        )}
      </Paper>

      {s && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography fontWeight={600}>{t('knowledge.admin.teamLearningTitle')}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {t('knowledge.admin.teamLearningHint', {
              interval: s.team_interval_hours,
              min: s.team_min_new_messages,
              max: s.team_max_entries,
            })}
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} sx={{ mt: 1 }}>
            <FormControlLabel
              control={
                <Switch
                  checked={s.team_enabled}
                  disabled={setMutation.isPending}
                  onChange={(e) => setMutation.mutate({ team_enabled: e.target.checked })}
                />
              }
              label={t('knowledge.admin.teamEnabled')}
            />
            <Typography variant="caption" color="text.secondary">
              {t('knowledge.admin.statLearned')}: {s.team_learned_entries.toLocaleString('fa-IR')} ·{' '}
              {t('knowledge.admin.lastRun')}:{' '}
              {s.team_last_run_at ? formatPersianDateTime(s.team_last_run_at) : t('knowledge.admin.never')}
              {s.team_last_run_summary ? ` — ${s.team_last_run_summary}` : ''}
            </Typography>
          </Stack>
        </Paper>
      )}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography fontWeight={600}>{t('knowledge.admin.datasetTitle')}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1.5 }}>
          {t('knowledge.admin.datasetHint')}
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <TextField
            size="small"
            type="date"
            label={t('knowledge.admin.since')}
            value={since}
            onChange={(e) => setSince(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            size="small"
            type="date"
            label={t('knowledge.admin.until')}
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            component="a"
            href={adminKnowledgeApi.exportConversationsUrl({ since: since || undefined, until: until || undefined })}
            download
          >
            {t('knowledge.admin.exportConversations')}
          </Button>
          <Button variant="outlined" startIcon={<DownloadIcon />} component="a" href={adminKnowledgeApi.exportEntriesUrl()} download>
            {t('knowledge.admin.exportEntries')}
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}

function UsersTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const usersQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: adminUsersApi.list });
  const [userId, setUserId] = useState<number | ''>('');
  const [showChats, setShowChats] = useState(false);
  const [openConv, setOpenConv] = useState<AdminConversation | null>(null);
  const api = useMemo(() => (userId !== '' ? adminKnowledgeApi.user(Number(userId)) : null), [userId]);
  const selected = (usersQuery.data ?? []).find((u) => u.id === userId);
  const learningMutation = useMutation({
    mutationFn: (enabled: boolean) => adminKnowledgeApi.setUserLearning(Number(userId), enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'knowledge'] });
    },
  });
  const convsQuery = useQuery({
    queryKey: ['admin', 'knowledge', 'users', userId, 'conversations'],
    queryFn: () => adminKnowledgeApi.userConversations(Number(userId)),
    enabled: userId !== '' && showChats,
  });
  const convQuery = useQuery({
    queryKey: ['admin', 'knowledge', 'conversation', openConv?.id],
    queryFn: () => adminKnowledgeApi.conversation(openConv!.id),
    enabled: !!openConv,
  });
  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
        <TextField
          select
          size="small"
          label={t('knowledge.admin.pickUser')}
          value={userId}
          onChange={(e) => {
            setUserId(Number(e.target.value));
            setShowChats(false);
          }}
          sx={{ minWidth: 320 }}
        >
          {(usersQuery.data ?? []).map((u) => (
            <MenuItem key={u.id} value={u.id}>
              {u.display_name || u.username} ({u.username})
            </MenuItem>
          ))}
        </TextField>
        {selected && (
          <FormControlLabel
            control={
              <Switch
                checked={selected.learning_enabled ?? true}
                disabled={learningMutation.isPending}
                onChange={(e) => learningMutation.mutate(e.target.checked)}
              />
            }
            label={t('knowledge.admin.userLearning')}
          />
        )}
      </Stack>
      {learningMutation.isError && <Alert severity="error">{getErrorMessage(learningMutation.error)}</Alert>}
      {api && (
        <KnowledgeEntriesEditor api={api} queryKey={['admin', 'knowledge', 'users', userId]} hint={t('knowledge.admin.userHint')} />
      )}
      {userId !== '' && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
            <Box>
              <Typography fontWeight={600}>{t('knowledge.admin.conversationsTitle')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('knowledge.admin.conversationsHint')}
              </Typography>
            </Box>
            <Button size="small" variant="outlined" onClick={() => setShowChats((v) => !v)}>
              {showChats ? t('knowledge.admin.hideConversations') : t('knowledge.admin.showConversations')}
            </Button>
          </Stack>
          {showChats && convsQuery.isLoading && <LoadingState />}
          {showChats && convsQuery.isSuccess && convsQuery.data.length === 0 && (
            <Typography color="text.secondary" sx={{ mt: 1 }}>
              {t('knowledge.admin.noConversations')}
            </Typography>
          )}
          {showChats && !!convsQuery.data?.length && (
            <List dense sx={{ mt: 1 }}>
              {convsQuery.data.map((c) => (
                <ListItemButton key={c.id} onClick={() => setOpenConv(c)}>
                  <ListItemText
                    primary={c.title}
                    secondary={`${formatPersianDateTime(c.updated_at)} · ${t('knowledge.admin.messages', { count: c.message_count })}${c.model_key ? ` · ${c.model_key}` : ''}`}
                  />
                </ListItemButton>
              ))}
            </List>
          )}
        </Paper>
      )}
      <Dialog open={!!openConv} onClose={() => setOpenConv(null)} maxWidth="md" fullWidth>
        <DialogTitle>{openConv?.title}</DialogTitle>
        <DialogContent dividers>
          {convQuery.isLoading && <LoadingState />}
          {convQuery.isError && <Alert severity="error">{getErrorMessage(convQuery.error)}</Alert>}
          <Stack spacing={1.5}>
            {(convQuery.data?.messages ?? []).map((m) => (
              <Box key={m.id} sx={{ p: 1.25, borderRadius: 1, bgcolor: m.role === 'user' ? 'action.hover' : 'transparent', border: '1px solid', borderColor: 'divider' }}>
                <Typography variant="caption" color="text.secondary">
                  {m.role === 'user' ? t('knowledge.admin.roleUser') : t('knowledge.admin.roleAssistant')} · {formatPersianDateTime(m.created_at)}
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {m.content}
                </Typography>
              </Box>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenConv(null)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

function TeamsTab() {
  const { t } = useTranslation();
  const teamsQuery = useQuery({ queryKey: ['admin', 'teams'], queryFn: adminTeamsApi.list });
  const [teamId, setTeamId] = useState<number | ''>('');
  const api = useMemo(() => (teamId !== '' ? adminKnowledgeApi.team(Number(teamId)) : null), [teamId]);
  return (
    <Stack spacing={2}>
      <TextField
        select
        size="small"
        label={t('knowledge.admin.pickTeam')}
        value={teamId}
        onChange={(e) => setTeamId(Number(e.target.value))}
        sx={{ maxWidth: 420 }}
      >
        {(teamsQuery.data ?? []).map((tm) => (
          <MenuItem key={tm.id} value={tm.id}>
            {tm.name}
          </MenuItem>
        ))}
      </TextField>
      {api && (
        <KnowledgeEntriesEditor api={api} queryKey={['admin', 'knowledge', 'teams', teamId]} hint={t('knowledge.admin.teamHint')} />
      )}
    </Stack>
  );
}

function ServicesTab() {
  const { t } = useTranslation();
  const servicesQuery = useQuery({ queryKey: ['admin', 'services'], queryFn: adminServicesApi.list });
  const [serviceId, setServiceId] = useState<number | ''>('');
  const api = useMemo(() => (serviceId !== '' ? adminKnowledgeApi.service(Number(serviceId)) : null), [serviceId]);
  return (
    <Stack spacing={2}>
      <TextField
        select
        size="small"
        label={t('knowledge.admin.pickService')}
        value={serviceId}
        onChange={(e) => setServiceId(Number(e.target.value))}
        sx={{ maxWidth: 420 }}
      >
        {(servicesQuery.data ?? []).map((s) => (
          <MenuItem key={s.id} value={s.id}>
            {s.name} ({s.slug})
          </MenuItem>
        ))}
      </TextField>
      {api && (
        <KnowledgeEntriesEditor
          api={api}
          queryKey={['admin', 'knowledge', 'services', serviceId]}
          hint={t('knowledge.admin.serviceHint')}
        />
      )}
    </Stack>
  );
}
