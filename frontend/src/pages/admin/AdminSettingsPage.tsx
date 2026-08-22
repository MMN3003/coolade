import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import Chip from '@mui/material/Chip';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import Divider from '@mui/material/Divider';
import { useTranslation } from 'react-i18next';
import { adminUpstreamApi } from '@/api/endpoints';
import type { UpstreamMode } from '@/api/types';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

/**
 * Admin upstream connection page — TECH.md v1.2 §4.1/§8/§9 (اصلاحیهٔ ۲ / Issue B).
 * Modes: mock / cli_creds / apikey (the old OAuth flow was removed).
 *
 * cli_creds now OWNS its token lifecycle server-side (seed-once from the host
 * file, then the backend refreshes itself before expiry) instead of relying
 * on a human re-running `claude login` after every ~8h expiry. The panel's
 * job changed accordingly: show the four status facts from the revised
 * GET /api/admin/upstream/status (token valid-until, refresh-token
 * valid-until — often unknown, last refresh attempt, auto_refresh state) and
 * only surface the «claude login روی سرور» CTA when auto_refresh is actually
 * stuck (`degraded`/`failed`) — normal operation asks nothing of the admin.
 */
export default function AdminSettingsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ['admin', 'upstream', 'status'],
    queryFn: adminUpstreamApi.status,
    refetchInterval: 60_000, // creds sync happens server-side every 60s; keep status fresh
  });

  const [apiKeyValue, setApiKeyValue] = useState('');
  const [modeValue, setModeValue] = useState<UpstreamMode>('cli_creds');

  // Initialize the mode selector from the server once status arrives.
  useEffect(() => {
    if (statusQuery.data) setModeValue(statusQuery.data.mode);
  }, [statusQuery.data]);

  const setApiKeyMutation = useMutation({
    mutationFn: () => adminUpstreamApi.setApiKey({ api_key: apiKeyValue }),
    onSuccess: () => {
      setApiKeyValue('');
      queryClient.invalidateQueries({ queryKey: ['admin', 'upstream', 'status'] });
    },
  });

  const setModeMutation = useMutation({
    mutationFn: () => adminUpstreamApi.setMode({ mode: modeValue }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'upstream', 'status'] }),
  });

  if (statusQuery.isLoading) return <LoadingState />;
  if (statusQuery.isError) {
    return <ErrorState message={getErrorMessage(statusQuery.error)} onRetry={() => statusQuery.refetch()} />;
  }
  const status = statusQuery.data!;

  // اصلاحیهٔ ۲ / Issue B: the CTA is driven by auto_refresh, not `connected`
  // alone — normal operation (auto refresh working) never prompts the admin.
  const autoRefresh = status.auto_refresh;
  const showLoginCta = autoRefresh === 'degraded' || autoRefresh === 'failed';
  const autoRefreshColor: 'success' | 'warning' | 'error' =
    autoRefresh === 'active' ? 'success' : autoRefresh === 'degraded' ? 'warning' : 'error';
  const autoRefreshLabel =
    autoRefresh === 'active'
      ? t('admin.settings.autoRefreshActive')
      : autoRefresh === 'degraded'
        ? t('admin.settings.autoRefreshDegraded')
        : t('admin.settings.autoRefreshFailed');

  return (
    <Box sx={{ p: 3, maxWidth: 800, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('admin.settings.title')}
      </Typography>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {t('admin.settings.connectionStatus')}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
          <Chip
            label={status.connected ? t('admin.settings.connected') : t('admin.settings.disconnected')}
            color={status.connected ? 'success' : 'error'}
            size="small"
          />
          {status.expiring_soon && (
            <Chip label={t('admin.settings.expiringSoon')} color="warning" size="small" />
          )}
          <Chip label={autoRefreshLabel} color={autoRefreshColor} size="small" variant="outlined" />
          <Chip label={status.mode} size="small" variant="outlined" sx={{ direction: 'ltr' }} />
        </Stack>

        {showLoginCta && (
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            {t('admin.settings.autoRefreshCta')}
          </Alert>
        )}

        <Stack spacing={0.5}>
          <Typography variant="body2" color="text.secondary">
            {t('admin.settings.expiresAt')}:{' '}
            {status.expires_at ? formatPersianDateTime(status.expires_at) : t('admin.settings.unknownValue')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('admin.settings.refreshTokenValidUntil')}:{' '}
            {status.refresh_token_valid_until
              ? formatPersianDateTime(status.refresh_token_valid_until)
              : t('admin.settings.unknownValue')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('admin.settings.lastRefresh')}:{' '}
            {status.last_refresh?.at ? (
              <>
                {formatPersianDateTime(status.last_refresh.at)} —{' '}
                {status.last_refresh.ok ? (
                  <Box component="span" sx={{ color: 'success.main' }}>
                    {t('admin.settings.lastRefreshOk')}
                  </Box>
                ) : (
                  <Box component="span" sx={{ color: 'error.main' }}>
                    {t('admin.settings.lastRefreshFailed')}
                    {status.last_refresh.error ? `: ${status.last_refresh.error}` : ''}
                  </Box>
                )}
              </>
            ) : (
              t('admin.settings.unknownValue')
            )}
          </Typography>
          {status.base_url && (
            <Typography variant="body2" color="text.secondary">
              {t('admin.settings.baseUrl')}:{' '}
              <Box component="span" sx={{ direction: 'ltr', unicodeBidi: 'embed', fontFamily: 'monospace' }}>
                {status.base_url}
              </Box>
            </Typography>
          )}
          {status.creds_source && (
            <Typography variant="body2" color="text.secondary">
              {t('admin.settings.credsSource')}:{' '}
              <Box component="span" sx={{ direction: 'ltr', unicodeBidi: 'embed', fontFamily: 'monospace' }}>
                {status.creds_source}
              </Box>
            </Typography>
          )}
          {status.last_synced && (
            <Typography variant="body2" color="text.secondary">
              {t('admin.settings.lastSynced')}: {formatPersianDateTime(status.last_synced)}
            </Typography>
          )}
        </Stack>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {t('admin.settings.modeCliCreds')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('admin.settings.cliCredsHint')}
        </Typography>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {t('admin.settings.modeApikey')}
        </Typography>
        <Stack direction="row" spacing={2}>
          <TextField
            label={t('admin.settings.apiKeyLabel')}
            type="password"
            value={apiKeyValue}
            onChange={(e) => setApiKeyValue(e.target.value)}
            fullWidth
          />
          <Button
            variant="contained"
            disabled={!apiKeyValue || setApiKeyMutation.isPending}
            onClick={() => setApiKeyMutation.mutate()}
          >
            {t('admin.settings.saveApiKey')}
          </Button>
        </Stack>
        {setApiKeyMutation.isError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {getErrorMessage(setApiKeyMutation.error)}
          </Alert>
        )}
      </Paper>

      <Paper sx={{ p: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {t('admin.settings.mode')}
        </Typography>
        <Stack direction="row" spacing={2}>
          <TextField
            select
            value={modeValue}
            onChange={(e) => setModeValue(e.target.value as UpstreamMode)}
            sx={{ minWidth: 280 }}
          >
            <MenuItem value="cli_creds">{t('admin.settings.modeCliCreds')}</MenuItem>
            <MenuItem value="apikey">{t('admin.settings.modeApikey')}</MenuItem>
            <MenuItem value="mock">{t('admin.settings.modeMock')}</MenuItem>
          </TextField>
          <Button
            variant="outlined"
            disabled={setModeMutation.isPending || modeValue === status.mode}
            onClick={() => setModeMutation.mutate()}
          >
            {t('admin.settings.switchMode')}
          </Button>
        </Stack>
        {setModeMutation.isError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {getErrorMessage(setModeMutation.error)}
          </Alert>
        )}
        <Divider sx={{ my: 2 }} />
        <Typography variant="caption" color="text.secondary">
          {t('common.status')}: {status.mode}
        </Typography>
      </Paper>
    </Box>
  );
}
