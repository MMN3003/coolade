import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import Grid from '@mui/material/Grid';
import Button from '@mui/material/Button';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import DownloadIcon from '@mui/icons-material/DownloadOutlined';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  BarChart,
  Bar,
} from 'recharts';
import { useTranslation } from 'react-i18next';
import { adminUsageApi } from '@/api/endpoints';
import { formatCredits, formatPersianShortDate } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

export default function AdminUsagePage() {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ['admin', 'usage'], queryFn: adminUsageApi.summary });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />;
  const data = query.data!;

  const rankedUsers = [...data.by_user].sort((a, b) => b.credits - a.credits);

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('admin.usage.title')}
        </Typography>
        <Button
          variant="outlined"
          startIcon={<DownloadIcon />}
          component="a"
          href={adminUsageApi.exportCsvUrl()}
        >
          {t('common.export')}
        </Button>
      </Box>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="caption" color="text.secondary">
          {t('admin.usage.totalCredits')}
        </Typography>
        <Typography variant="h4" fontWeight={700}>
          {formatCredits(data.total_credits)}
        </Typography>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {t('admin.usage.dailyTrend')}
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
              {t('admin.usage.userRanking')}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>{t('common.name')}</TableCell>
                  <TableCell align="left">{t('usage.credits')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rankedUsers.map((u, idx) => (
                  <TableRow key={u.user_id}>
                    <TableCell>{idx + 1}</TableCell>
                    <TableCell>{u.username}</TableCell>
                    <TableCell align="left">{formatCredits(u.credits)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="subtitle1" fontWeight={600} gutterBottom>
              {t('admin.usage.byModel')}
            </Typography>
            <Box sx={{ width: '100%', height: 220 }}>
              <ResponsiveContainer>
                <BarChart data={data.by_model}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="model_key" />
                  <YAxis />
                  <RechartsTooltip formatter={(v: number) => [formatCredits(v), t('usage.credits')]} />
                  <Bar dataKey="credits" fill="#0277bd" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}
