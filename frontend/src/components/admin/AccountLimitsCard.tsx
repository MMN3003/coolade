import { useQuery } from '@tanstack/react-query';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid';
import LinearProgress from '@mui/material/LinearProgress';
import Alert from '@mui/material/Alert';
import { useTranslation } from 'react-i18next';
import { adminUpstreamApi } from '@/api/endpoints';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

/**
 * اصلاحیهٔ ۳ / Issue F (TECH.md §4.5, §8, §9) — "محدودیت اکانت اصلی" card on
 * `/admin/usage`. This never fabricates numbers: when `available:false` we
 * show only tier/subscription plus an explicit "upstream doesn't expose
 * this" message, never fake zeros. Endpoint not yet in openapi.json — see
 * `api/endpoints.ts#adminUpstreamApi.accountLimits`; expect 404 until Dev1
 * lands it (TECH.md §10).
 */
export default function AccountLimitsCard() {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ['admin', 'upstream', 'account-limits'],
    queryFn: adminUpstreamApi.accountLimits,
  });

  return (
    <Paper sx={{ p: 3, mb: 3 }}>
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        {t('admin.usage.accountLimitsTitle')}
      </Typography>

      {query.isLoading && <LoadingState />}
      {query.isError && (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />
      )}

      {query.data && !query.data.available && (
        <Box>
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('admin.usage.accountLimitsUnavailable')}
          </Alert>
          {(query.data.tier || query.data.subscription) && (
            <Grid container spacing={2}>
              {query.data.tier && (
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">
                    {t('admin.usage.tier')}
                  </Typography>
                  <Typography variant="body1">{query.data.tier}</Typography>
                </Grid>
              )}
              {query.data.subscription && (
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">
                    {t('admin.usage.subscription')}
                  </Typography>
                  <Typography variant="body1">{query.data.subscription}</Typography>
                </Grid>
              )}
            </Grid>
          )}
        </Box>
      )}

      {query.data && query.data.available && (
        <Grid container spacing={2}>
          {query.data.windows.map((w) => {
            const ratio =
              w.limit && w.limit > 0 && w.remaining !== null
                ? Math.max(0, Math.min(1, 1 - w.remaining / w.limit))
                : null;
            return (
              <Grid item xs={12} md={6} key={w.key}>
                <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ direction: 'ltr', textAlign: 'right', width: '100%' }}>
                      {w.key}
                    </Typography>
                    {w.stale && <Chip size="small" color="warning" label={t('admin.usage.stale')} />}
                  </Box>
                  {ratio !== null && (
                    <LinearProgress
                      variant="determinate"
                      value={ratio * 100}
                      color={ratio >= 1 ? 'error' : ratio >= 0.8 ? 'warning' : 'primary'}
                      sx={{ height: 8, borderRadius: 4, mb: 1 }}
                    />
                  )}
                  <Typography variant="body2" color="text.secondary">
                    {t('usage.limit')}: {w.limit ?? '—'} {w.unit ?? ''} · {t('usage.remaining')}: {w.remaining ?? '—'}
                  </Typography>
                  {w.reset && (
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('admin.usage.resetAt', { time: formatPersianDateTime(w.reset) })}
                    </Typography>
                  )}
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t('admin.usage.lastUpdated', { time: formatPersianDateTime(w.last_updated) })}
                  </Typography>
                </Box>
              </Grid>
            );
          })}
          {query.data.windows.length === 0 && (
            <Grid item xs={12}>
              <Typography color="text.secondary">{t('common.noData')}</Typography>
            </Grid>
          )}
        </Grid>
      )}
    </Paper>
  );
}
