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
 * Admin upstream connection page — TECH.md v1.1 §4/§8/§9.
 * Modes: mock / cli_creds / apikey (the old OAuth flow was removed).
 * cli_creds is credential-less from the panel's perspective: the backend reuses
 * the Claude Code credentials already on the host; when they expire the fix is
 * `claude login` on the server, so we only show status + that guidance.
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

  const isExpired = !status.connected && status.mode === 'cli_creds';

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
            label={
              status.connected
                ? t('admin.settings.connected')
                : isExpired
                  ? t('admin.settings.expired')
                  : t('admin.settings.disconnected')
            }
            color={status.connected ? 'success' : 'error'}
            size="small"
          />
          {status.expiring_soon && (
            <Chip label={t('admin.settings.expiringSoon')} color="warning" size="small" />
          )}
          <Chip label={status.mode} size="small" variant="outlined" sx={{ direction: 'ltr' }} />
        </Stack>

        {isExpired && (
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            {t('admin.settings.cliCredsReconnect')}
          </Alert>
        )}

        <Stack spacing={0.5}>
          {status.expires_at && (
            <Typography variant="body2" color="text.secondary">
              {t('admin.settings.expiresAt')}: {formatPersianDateTime(status.expires_at)}
            </Typography>
          )}
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
