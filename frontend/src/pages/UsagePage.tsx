import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { usageApi } from '@/api/endpoints';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import { getErrorMessage } from '@/utils/errors';
import UsageReport from '@/components/usage/UsageReport';

export default function UsagePage() {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ['usage', 'me'], queryFn: usageApi.me });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />;
  const data = query.data!;

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('usage.title')}
      </Typography>

      <UsageReport
        weekly={{
          period: data.period,
          period_start: data.period_start,
          limit_credits: data.limit_credits,
          bonus_credits: data.bonus_credits,
          used_credits: data.used_credits,
        }}
        fiveHour={data.fiveHour}
        daily={data.daily}
        byModel={data.by_model}
        byKey={data.by_key}
      />
    </Box>
  );
}
