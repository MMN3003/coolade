import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TablePagination from '@mui/material/TablePagination';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Tooltip from '@mui/material/Tooltip';
import DownloadIcon from '@mui/icons-material/DownloadOutlined';
import { useTranslation } from 'react-i18next';
import { adminUsageApi, adminUsersApi } from '@/api/endpoints';
import type { AdminTurnsQuery, ThinkingLevel } from '@/api/types';
import { formatCredits, formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

const SURFACES = ['web_chat', 'relay', 'passthrough', 'mcp'] as const;

function fmtInt(n: number): string {
  return n.toLocaleString('fa-IR');
}

/**
 * Admin — per-message token audit (product request 2026-09-14): for every
 * billed turn, the real input/output/cache tokens, what the user was charged,
 * the model and the thinking level the turn ran with. Metadata only — the
 * message content is never fetched (TECH.md 11.1).
 */
export default function AdminTurnsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const userIdParam = searchParams.get('user_id');
  const userId = userIdParam ? Number(userIdParam) : undefined;
  const surface = searchParams.get('surface') ?? '';
  const since = searchParams.get('since') ?? '';
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);

  const query: AdminTurnsQuery = useMemo(
    () => ({
      user_id: Number.isFinite(userId) ? userId : undefined,
      surface: surface || undefined,
      since: since ? new Date(since).toISOString() : undefined,
      limit: rowsPerPage,
      offset: page * rowsPerPage,
    }),
    [userId, surface, since, page, rowsPerPage],
  );

  const usersQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: adminUsersApi.list });
  const turnsQuery = useQuery({
    queryKey: ['admin', 'usage', 'turns', query],
    queryFn: () => adminUsageApi.turns(query),
    placeholderData: (prev) => prev,
  });

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
    setPage(0);
  }

  const thinkingLabel: Record<ThinkingLevel, string> = {
    off: t('chat.thinkingOff'),
    standard: t('chat.thinkingStandard'),
    deep: t('chat.thinkingDeep'),
  };

  const data = turnsQuery.data;

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('admin.turns.title')}
        </Typography>
        <Button
          variant="outlined"
          startIcon={<DownloadIcon />}
          component="a"
          href={adminUsageApi.turnsExportCsvUrl(query)}
        >
          {t('common.export')}
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        {t('admin.turns.notice')}
      </Alert>

      <Paper variant="outlined" sx={{ p: 2, mb: 2, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <TextField
          select
          size="small"
          label={t('admin.turns.user')}
          value={userIdParam ?? ''}
          onChange={(e) => setFilter('user_id', e.target.value)}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">{t('admin.turns.allUsers')}</MenuItem>
          {(usersQuery.data ?? []).map((u) => (
            <MenuItem key={u.id} value={String(u.id)}>
              {u.display_name ? `${u.display_name} (${u.username})` : u.username}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label={t('admin.turns.surface')}
          value={surface}
          onChange={(e) => setFilter('surface', e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">{t('admin.turns.allSurfaces')}</MenuItem>
          {SURFACES.map((s) => (
            <MenuItem key={s} value={s}>
              {t(`admin.turns.surfaces.${s}`, s)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="date"
          label={t('admin.turns.since')}
          value={since}
          onChange={(e) => setFilter('since', e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
      </Paper>

      {turnsQuery.isLoading && <LoadingState />}
      {turnsQuery.isError && (
        <ErrorState message={getErrorMessage(turnsQuery.error)} onRetry={() => turnsQuery.refetch()} />
      )}

      {data && (
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 1100 }}>
            <TableHead>
              <TableRow>
                <TableCell>{t('admin.turns.time')}</TableCell>
                <TableCell>{t('admin.turns.user')}</TableCell>
                <TableCell>{t('admin.turns.surface')}</TableCell>
                <TableCell>{t('admin.turns.ref')}</TableCell>
                <TableCell>{t('admin.turns.model')}</TableCell>
                <TableCell>{t('admin.turns.thinking')}</TableCell>
                <TableCell align="left">{t('admin.turns.inputTokens')}</TableCell>
                <TableCell align="left">{t('admin.turns.outputTokens')}</TableCell>
                <TableCell align="left">{t('admin.turns.cacheTokens')}</TableCell>
                <TableCell align="left">{t('admin.turns.creditsInput')}</TableCell>
                <TableCell align="left">{t('admin.turns.creditsOutput')}</TableCell>
                <TableCell align="left">{t('admin.turns.creditsCharged')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={12} align="center" sx={{ color: 'text.secondary', py: 4 }}>
                    {t('common.noData')}
                  </TableCell>
                </TableRow>
              )}
              {data.rows.map((r) => {
                const priced = r.credits_input + r.credits_output + r.credits_cache_read;
                const drift = Math.abs(priced - r.credits) > 0.0005;
                return (
                  <TableRow key={r.id} hover>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatPersianDateTime(r.created_at)}</TableCell>
                    <TableCell>{r.username}</TableCell>
                    <TableCell>
                      <Chip size="small" variant="outlined" label={t(`admin.turns.surfaces.${r.surface}`, r.surface)} />
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap', color: 'text.secondary', fontSize: '0.8rem' }}>
                      {r.conversation_id != null ? `#${r.conversation_id}` : '—'}
                      {r.message_id != null ? ` / ${t('admin.turns.msg')} ${r.message_id}` : ''}
                    </TableCell>
                    <TableCell>
                      <Tooltip title={r.model_key}>
                        <span>{r.model_display_name}</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell>{r.thinking_level ? thinkingLabel[r.thinking_level] : '—'}</TableCell>
                    <TableCell align="left">{fmtInt(r.input_tokens)}</TableCell>
                    <TableCell align="left">{fmtInt(r.output_tokens)}</TableCell>
                    <TableCell align="left">
                      <Tooltip title={`${t('admin.turns.cacheRead')}: ${fmtInt(r.cache_read_tokens)} · ${t('admin.turns.cacheWrite')}: ${fmtInt(r.cache_write_tokens)}`}>
                        <span>{fmtInt(r.cache_read_tokens + r.cache_write_tokens)}</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell align="left">{formatCredits(r.credits_input)}</TableCell>
                    <TableCell align="left">{formatCredits(r.credits_output)}</TableCell>
                    <TableCell align="left" sx={{ fontWeight: 600 }}>
                      {drift ? (
                        <Tooltip title={t('admin.turns.driftHint', { now: formatCredits(priced) })}>
                          <span>{formatCredits(r.credits)} *</span>
                        </Tooltip>
                      ) : (
                        formatCredits(r.credits)
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={data.total}
            page={page}
            onPageChange={(_e, p) => setPage(p)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(Number(e.target.value));
              setPage(0);
            }}
            rowsPerPageOptions={[25, 50, 100, 200]}
            labelRowsPerPage={t('admin.turns.rowsPerPage')}
            labelDisplayedRows={({ from, to, count }) => `${fmtInt(from)}–${fmtInt(to)} ${t('admin.turns.of')} ${fmtInt(count)}`}
          />
        </Paper>
      )}
    </Box>
  );
}
