import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Alert from '@mui/material/Alert';
import DownloadIcon from '@mui/icons-material/DownloadOutlined';
import ReceiptLongOutlinedIcon from '@mui/icons-material/ReceiptLongOutlined';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { useTranslation } from 'react-i18next';
import { adminUsersApi } from '@/api/endpoints';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import UsageReport from '@/components/usage/UsageReport';

/**
 * اصلاحیهٔ ۳ / Issue G (TECH.md §8, §9): admin drill-down at
 * `/admin/users/:id/usage` — "همان نمای «مصرف من» کاربر … فقط متادیتا،
 * هرگز محتوای چت". Reuses `UsageReport` (the exact component `/usage`
 * renders for the user themself) so the mirroring TECH.md asks for is
 * structural, not just visual. Linked from `AdminUsersPage` (per-row action)
 * and `AdminUsagePage` (per-row action on the org ranking table).
 *
 * Endpoint `GET /api/admin/users/{id}/usage` is not yet in openapi.json —
 * expect 404 until Dev1 lands it (§10); the CSV export button links to
 * `GET .../usage/export.csv` the same way, unverified against a live backend.
 */
export default function AdminUserUsagePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { userId: userIdParam } = useParams();
  const userId = Number(userIdParam);

  const usageQuery = useQuery({
    queryKey: ['admin', 'user', userId, 'usage'],
    queryFn: () => adminUsersApi.usage(userId),
    enabled: Number.isFinite(userId),
  });

  if (!Number.isFinite(userId)) {
    return <ErrorState message={t('common.noData')} />;
  }

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconButton size="small" onClick={() => navigate('/admin/users')} aria-label={t('admin.userUsage.back')}>
            <ArrowForwardIcon fontSize="small" />
          </IconButton>
          <Typography variant="h5" fontWeight={700}>
            {t('admin.userUsage.title')}
            {usageQuery.data ? ` — ${usageQuery.data.username}` : ''}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<ReceiptLongOutlinedIcon />}
            onClick={() => navigate(`/admin/turns?user_id=${userId}`)}
          >
            {t('admin.userUsage.perMessage')}
          </Button>
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            component="a"
            href={adminUsersApi.usageExportCsvUrl(userId)}
          >
            {t('common.export')}
          </Button>
        </Box>
      </Box>

      <Alert severity="info" sx={{ mb: 3 }}>
        {t('admin.userUsage.notice')}
      </Alert>

      {usageQuery.isLoading && <LoadingState />}
      {usageQuery.isError && (
        <ErrorState message={getErrorMessage(usageQuery.error)} onRetry={() => usageQuery.refetch()} />
      )}

      {usageQuery.data && (
        <UsageReport
          weekly={{
            period: usageQuery.data.weekly.period,
            period_start: usageQuery.data.weekly.period_start,
            limit_credits: usageQuery.data.weekly.limit,
            bonus_credits: usageQuery.data.weekly.bonus,
            used_credits: usageQuery.data.weekly.used,
            reset_at: usageQuery.data.weekly.reset_at,
          }}
          fiveHour={usageQuery.data.fiveHour}
          daily={usageQuery.data.daily}
          byModel={usageQuery.data.by_model}
          byKey={usageQuery.data.by_key}
        />
      )}
    </Box>
  );
}
