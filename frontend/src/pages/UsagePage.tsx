import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';
import Grid from '@mui/material/Grid';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
} from 'recharts';
import { useTranslation } from 'react-i18next';
import { usageApi } from '@/api/endpoints';
import { formatCredits, formatPersianShortDate } from '@/utils/date';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import { getErrorMessage } from '@/utils/errors';

export default function UsagePage() {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ['usage', 'me'], queryFn: usageApi.me });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />;
  const data = query.data!;

  const budget = data.limit_credits + data.bonus_credits;
  const ratio = budget > 0 ? Math.min(data.used_credits / budget, 1) : 0;
  const color = ratio >= 1 ? 'error' : ratio >= 0.8 ? 'warning' : 'primary';

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('usage.title')}
      </Typography>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t(`usage.period_${data.period}`)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {formatCredits(data.used_credits)} / {formatCredits(budget)} {t('usage.credits')}
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={ratio * 100}
          color={color}
          sx={{ height: 10, borderRadius: 5 }}
        />
        <Grid container spacing={2} sx={{ mt: 2 }}>
          <Grid item xs={4}>
            <Typography variant="caption" color="text.secondary">
              {t('usage.used')}
            </Typography>
            <Typography variant="h6">{formatCredits(data.used_credits)}</Typography>
          </Grid>
          <Grid item xs={4}>
            <Typography variant="caption" color="text.secondary">
              {t('usage.limit')}
            </Typography>
            <Typography variant="h6">{formatCredits(budget)}</Typography>
          </Grid>
          <Grid item xs={4}>
            <Typography variant="caption" color="text.secondary">
              {t('usage.remaining')}
            </Typography>
            <Typography variant="h6">{formatCredits(Math.max(budget - data.used_credits, 0))}</Typography>
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {t('usage.dailyTrend')}
        </Typography>
        <Box sx={{ width: '100%', height: 260 }}>
          <ResponsiveContainer>
            <LineChart data={data.daily}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={(d) => formatPersianShortDate(d)} />
              <YAxis />
              <RechartsTooltip
                labelFormatter={(d) => formatPersianShortDate(d as string)}
                formatter={(v: number) => [formatCredits(v), t('usage.credits')]}
              />
              <Line type="monotone" dataKey="credits" stroke="#2e7d32" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      </Paper>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="subtitle1" fontWeight={600} gutterBottom>
              {t('usage.byModel')}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('common.name')}</TableCell>
                  <TableCell align="left">{t('usage.credits')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.by_model.map((m) => (
                  <TableRow key={m.model_key}>
                    <TableCell sx={{ direction: 'ltr', fontFamily: 'monospace' }}>{m.model_key}</TableCell>
                    <TableCell align="left">{formatCredits(m.credits)}</TableCell>
                  </TableRow>
                ))}
                {data.by_model.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2}>
                      <Typography variant="body2" color="text.secondary">
                        {t('common.noData')}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="subtitle1" fontWeight={600} gutterBottom>
              {t('usage.byKey')}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('common.name')}</TableCell>
                  <TableCell align="left">{t('usage.credits')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.by_key.map((k) => (
                  <TableRow key={k.api_key_id ?? 'web'}>
                    <TableCell>{k.api_key_id === null ? t('usage.webChat') : k.name}</TableCell>
                    <TableCell align="left">{formatCredits(k.credits)}</TableCell>
                  </TableRow>
                ))}
                {data.by_key.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2}>
                      <Typography variant="body2" color="text.secondary">
                        {t('common.noData')}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}
