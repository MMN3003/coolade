import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { knowledgeApi } from '@/api/endpoints';
import { useAuthStore } from '@/store/authStore';
import { getErrorMessage } from '@/utils/errors';
import KnowledgeEntriesEditor from '@/components/knowledge/KnowledgeEntriesEditor';
import LoadingState from '@/components/common/LoadingState';
import EmptyState from '@/components/common/EmptyState';

type TabKey = 'me' | 'services' | 'teams';

/**
 * «دانش من» — amendment-7 (docs/KNOWLEDGE.md). Three scopes the user can shape
 * themselves: own memory/rules (incl. learned entries), per-service notes for
 * services they hold a grant on, and their teams' shared knowledge. Plus the
 * opt-out switch for chat learning.
 */
export default function KnowledgePage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const teams = useAuthStore((s) => s.user?.teams) ?? [];
  const [tab, setTab] = useState<TabKey>('me');
  const [serviceSlug, setServiceSlug] = useState<string>('');
  const [teamId, setTeamId] = useState<number | ''>(teams[0]?.id ?? '');

  const learningQuery = useQuery({ queryKey: ['knowledge', 'me', 'learning'], queryFn: knowledgeApi.learning.get });
  const learningMutation = useMutation({
    mutationFn: (enabled: boolean) => knowledgeApi.learning.set(enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge', 'me', 'learning'] });
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
    },
  });

  const servicesQuery = useQuery({
    queryKey: ['knowledge', 'me', 'services'],
    queryFn: knowledgeApi.myServices,
    enabled: tab === 'services',
  });
  const services = servicesQuery.data ?? [];
  const effectiveSlug = serviceSlug || services[0]?.slug || '';

  const meApi = useMemo(() => knowledgeApi.me(), []);
  const serviceApi = useMemo(
    () => (effectiveSlug ? knowledgeApi.myService(effectiveSlug) : null),
    [effectiveSlug],
  );
  const teamApi = useMemo(() => (teamId !== '' ? knowledgeApi.team(Number(teamId)) : null), [teamId]);

  return (
    <Box sx={{ p: 3, maxWidth: 960, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('knowledge.title')}
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        {t('knowledge.intro')}
      </Alert>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <Box sx={{ flex: 1 }}>
            <Typography fontWeight={600}>{t('knowledge.learningTitle')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('knowledge.learningHint')}
            </Typography>
          </Box>
          <FormControlLabel
            control={
              <Switch
                checked={learningQuery.data?.enabled ?? true}
                disabled={learningQuery.isLoading || learningMutation.isPending}
                onChange={(e) => learningMutation.mutate(e.target.checked)}
              />
            }
            label={learningQuery.data?.enabled === false ? t('knowledge.learningOff') : t('knowledge.learningOn')}
          />
        </Stack>
        {learningMutation.isError && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {getErrorMessage(learningMutation.error)}
          </Alert>
        )}
      </Paper>

      <Tabs value={tab} onChange={(_e, v: TabKey) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="me" label={t('knowledge.tabMe')} />
        <Tab value="services" label={t('knowledge.tabServices')} />
        <Tab value="teams" label={t('knowledge.tabTeams')} />
      </Tabs>

      {tab === 'me' && <KnowledgeEntriesEditor api={meApi} queryKey={['knowledge', 'me', 'entries']} />}

      {tab === 'services' && (
        <Box>
          {servicesQuery.isLoading && <LoadingState />}
          {servicesQuery.isSuccess && services.length === 0 && <EmptyState message={t('knowledge.noServices')} />}
          {services.length > 0 && (
            <Stack spacing={2}>
              <TextField
                select
                size="small"
                label={t('knowledge.pickService')}
                value={effectiveSlug}
                onChange={(e) => setServiceSlug(e.target.value)}
                sx={{ maxWidth: 420 }}
              >
                {services.map((s) => (
                  <MenuItem key={s.id} value={s.slug}>
                    {s.name}
                    {s.entry_count ? ` (${s.entry_count.toLocaleString('fa-IR')})` : ''}
                  </MenuItem>
                ))}
              </TextField>
              {serviceApi && (
                <KnowledgeEntriesEditor
                  api={serviceApi}
                  queryKey={['knowledge', 'me', 'services', effectiveSlug]}
                  hint={t('knowledge.serviceNotesHint')}
                />
              )}
            </Stack>
          )}
        </Box>
      )}

      {tab === 'teams' && (
        <Box>
          {teams.length === 0 && <EmptyState message={t('knowledge.noTeams')} />}
          {teams.length > 0 && (
            <Stack spacing={2}>
              <TextField
                select
                size="small"
                label={t('knowledge.pickTeam')}
                value={teamId}
                onChange={(e) => setTeamId(Number(e.target.value))}
                sx={{ maxWidth: 420 }}
              >
                {teams.map((tm) => (
                  <MenuItem key={tm.id} value={tm.id}>
                    {tm.name}
                  </MenuItem>
                ))}
              </TextField>
              {teamApi && (
                <KnowledgeEntriesEditor
                  api={teamApi}
                  queryKey={['knowledge', 'teams', teamId]}
                  hint={t('knowledge.teamHint')}
                />
              )}
            </Stack>
          )}
        </Box>
      )}
    </Box>
  );
}
