import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import TextField from '@mui/material/TextField';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Button from '@mui/material/Button';
import { useTranslation } from 'react-i18next';
import { adminUsageApi } from '@/api/endpoints';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { formatPersianDateTime } from '@/utils/date';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import EmptyState from '@/components/common/EmptyState';

export default function AdminAuditPage() {
  const { t } = useTranslation();
  const [actionFilter, setActionFilter] = useState('');
  const [userFilter, setUserFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const debouncedAction = useDebouncedValue(actionFilter, 300);
  const debouncedUser = useDebouncedValue(userFilter, 300);

  // Contract: bare array with limit/offset paging and NO total count →
  // simple prev/next paging; "next" stays enabled while a full page came back.
  const query = useQuery({
    queryKey: ['admin', 'audit', debouncedAction, debouncedUser, page],
    queryFn: () =>
      adminUsageApi.auditLog({
        action: debouncedAction || undefined,
        user_id: debouncedUser ? Number(debouncedUser) : undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }),
  });

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('admin.audit.title')}
      </Typography>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2}>
          <TextField
            size="small"
            label={t('admin.audit.filterAction')}
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
              setPage(1);
            }}
          />
          <TextField
            size="small"
            type="number"
            label={t('admin.audit.filterUser')}
            value={userFilter}
            onChange={(e) => {
              setUserFilter(e.target.value);
              setPage(1);
            }}
          />
        </Stack>
      </Paper>

      <Paper>
        {query.isLoading && <LoadingState />}
        {query.isError && <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />}
        {query.data && query.data.length === 0 && page === 1 && <EmptyState message={t('common.noData')} />}
        {query.data && (query.data.length > 0 || page > 1) && (
          <>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('admin.audit.time')}</TableCell>
                  <TableCell>{t('admin.audit.action')}</TableCell>
                  <TableCell>{t('admin.audit.actor')}</TableCell>
                  <TableCell>{t('admin.audit.target')}</TableCell>
                  <TableCell>{t('admin.audit.ip')}</TableCell>
                  <TableCell>{t('admin.audit.detail')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {query.data.map((entry) => (
                  <TableRow key={entry.id} hover>
                    <TableCell>{formatPersianDateTime(entry.created_at)}</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', direction: 'ltr' }}>{entry.action}</TableCell>
                    <TableCell>{entry.actor_username ?? entry.actor_id ?? '—'}</TableCell>
                    <TableCell>{entry.target_username ?? entry.target_id ?? '—'}</TableCell>
                    <TableCell sx={{ direction: 'ltr' }}>{entry.ip_address ?? '—'}</TableCell>
                    <TableCell sx={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {entry.detail ? JSON.stringify(entry.detail) : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Stack direction="row" spacing={1} justifyContent="center" sx={{ p: 1.5 }}>
              <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t('common.back')}
              </Button>
              <Typography variant="body2" sx={{ alignSelf: 'center' }}>
                {new Intl.NumberFormat('fa-IR').format(page)}
              </Typography>
              <Button
                size="small"
                disabled={query.data.length < pageSize}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('common.next')}
              </Button>
            </Stack>
          </>
        )}
      </Paper>
    </Box>
  );
}
