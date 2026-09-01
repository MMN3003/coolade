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
import type { FiveHourUsage, QuotaPeriod, UsageByKey, UsageByModel, UsageDailyPoint } from '@/api/types';
import { formatCredits, formatPersianDateTime, formatPersianShortDate } from '@/utils/date';

export interface WeeklyUsageBlock {
  period: QuotaPeriod;
  period_start: string;
  limit_credits: number;
  bonus_credits: number;
  used_credits: number;
  /** اصلاحیهٔ ۳ / Issue G only — the admin per-user endpoint reports the upcoming period boundary; `/usage/me` doesn't. */
  reset_at?: string;
}

interface Props {
  weekly: WeeklyUsageBlock;
  /** اصلاحیهٔ ۳ / Issue E — null hides the "۵ ساعتهٔ اخیر" bar entirely (no cap set, or backend not yet upgraded). */
  fiveHour: FiveHourUsage | null;
  daily: UsageDailyPoint[];
  byModel: UsageByModel[];
  byKey: UsageByKey[];
}

/**
 * Shared "مصرف من" layout — used by `pages/UsagePage.tsx` (self) and
 * `pages/admin/AdminUserUsagePage.tsx` (اصلاحیهٔ ۳ / Issue G admin
 * drill-down, which TECH.md §9 explicitly asks to mirror). Keeping this in
 * one place is what makes that mirroring real instead of a copy-paste.
 */
export default function UsageReport({ weekly, fiveHour, daily, byModel, byKey }: Props) {
  const { t } = useTranslation();

  const budget = weekly.limit_credits + weekly.bonus_credits;
  const ratio = budget > 0 ? Math.min(weekly.used_credits / budget, 1) : 0;
  const color = ratio >= 1 ? 'error' : ratio >= 0.8 ? 'warning' : 'primary';

  const fiveHourLimit = fiveHour?.limit_credits_5h ?? 0;
  const fiveHourRatio = fiveHour && fiveHourLimit > 0 ? Math.min(fiveHour.used_5h / fiveHourLimit, 1) : 0;
  const fiveHourColor = fiveHourRatio >= 1 ? 'error' : fiveHourRatio >= 0.8 ? 'warning' : 'primary';

  return (
    <>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t(`usage.period_${weekly.period}`)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {formatCredits(weekly.used_credits)} / {formatCredits(budget)} {t('usage.credits')}
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
            <Typography variant="h6">{formatCredits(weekly.used_credits)}</Typography>
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
            <Typography variant="h6">{formatCredits(Math.max(budget - weekly.used_credits, 0))}</Typography>
          </Grid>
        </Grid>
        {weekly.reset_at && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
            {t('usage.periodResetsAt', { time: formatPersianDateTime(weekly.reset_at) })}
          </Typography>
        )}
      </Paper>

      {/* اصلاحیهٔ ۳ / Issue E: separate rolling 5h bar, beside the weekly one — only when a cap is actually set. */}
      {fiveHour && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('usage.fiveHourTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {formatCredits(fiveHour.used_5h)} / {formatCredits(fiveHourLimit)} {t('usage.credits')}
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={fiveHourRatio * 100}
            color={fiveHourColor}
            sx={{ height: 10, borderRadius: 5 }}
          />
          {fiveHour.reset_5h_at && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {t('usage.fiveHourResetsAround', { time: formatPersianDateTime(fiveHour.reset_5h_at) })}
            </Typography>
          )}
        </Paper>
      )}

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {t('usage.dailyTrend')}
        </Typography>
        <Box sx={{ width: '100%', height: 260 }}>
          <ResponsiveContainer>
            <LineChart data={daily}>
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
                {byModel.map((m) => (
                  <TableRow key={m.model_key}>
                    <TableCell sx={{ direction: 'ltr', fontFamily: 'monospace' }}>{m.model_key}</TableCell>
                    <TableCell align="left">{formatCredits(m.credits)}</TableCell>
                  </TableRow>
                ))}
                {byModel.length === 0 && (
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
                {byKey.map((k) => (
                  <TableRow key={k.api_key_id ?? k.name}>
                    <TableCell>{k.name}</TableCell>
                    <TableCell align="left">{formatCredits(k.credits)}</TableCell>
                  </TableRow>
                ))}
                {byKey.length === 0 && (
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
    </>
  );
}
