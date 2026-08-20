import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import { useTranslation } from 'react-i18next';
import { adminModelsApi, adminPolicyApi, adminUsersApi } from '@/api/endpoints';
import type { QuotaPeriod } from '@/api/types';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

export default function AdminPoliciesPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const selectedUserId = params.get('user') ? Number(params.get('user')) : null;

  const usersQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: adminUsersApi.list });
  const modelsQuery = useQuery({ queryKey: ['admin', 'models'], queryFn: adminModelsApi.list });
  const userDetailQuery = useQuery({
    queryKey: ['admin', 'user', selectedUserId],
    queryFn: () => adminUsersApi.get(selectedUserId!),
    enabled: !!selectedUserId,
  });

  const [selectedModelKeys, setSelectedModelKeys] = useState<string[]>([]);
  const [quotaPeriod, setQuotaPeriod] = useState<QuotaPeriod>('weekly');
  const [quotaLimit, setQuotaLimit] = useState<string>('0');
  const [bonusCredits, setBonusCredits] = useState<string>('0');

  useEffect(() => {
    if (userDetailQuery.data) {
      // Contract: UserDetailOut carries allowed_models (string[]) and a nullable quota.
      setSelectedModelKeys(userDetailQuery.data.allowed_models);
      if (userDetailQuery.data.quota) {
        setQuotaPeriod(userDetailQuery.data.quota.period);
        setQuotaLimit(String(userDetailQuery.data.quota.limit_credits));
      } else {
        setQuotaPeriod('weekly');
        setQuotaLimit('0');
      }
    }
  }, [userDetailQuery.data]);

  const policyMutation = useMutation({
    mutationFn: () => adminPolicyApi.setPolicy(selectedUserId!, { model_keys: selectedModelKeys }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'user', selectedUserId] }),
  });

  const quotaMutation = useMutation({
    mutationFn: () =>
      adminPolicyApi.setQuota(selectedUserId!, { period: quotaPeriod, limit_credits: Number(quotaLimit) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'user', selectedUserId] }),
  });

  const bonusMutation = useMutation({
    mutationFn: () => adminPolicyApi.addBonus(selectedUserId!, { bonus_credits: Number(bonusCredits) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'user', selectedUserId] });
      setBonusCredits('0');
    },
  });

  function toggleModel(key: string) {
    setSelectedModelKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('admin.policies.title')}
      </Typography>

      <Paper sx={{ p: 3, mb: 3 }}>
        <TextField
          select
          label={t('admin.policies.selectUser')}
          value={selectedUserId ?? ''}
          onChange={(e) => setParams({ user: e.target.value })}
          fullWidth
          disabled={usersQuery.isLoading}
        >
          {(usersQuery.data ?? []).map((u) => (
            <MenuItem key={u.id} value={u.id}>
              {u.display_name || u.username}
            </MenuItem>
          ))}
        </TextField>
      </Paper>

      {!selectedUserId && <Typography color="text.secondary">{t('admin.policies.selectUser')}</Typography>}

      {selectedUserId && userDetailQuery.isLoading && <LoadingState />}
      {selectedUserId && userDetailQuery.isError && (
        <ErrorState message={getErrorMessage(userDetailQuery.error)} onRetry={() => userDetailQuery.refetch()} />
      )}

      {selectedUserId && userDetailQuery.data && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                {t('admin.policies.allowedModels')}
              </Typography>
              <FormGroup>
                {(modelsQuery.data ?? []).map((m) => (
                  <FormControlLabel
                    key={m.model_key}
                    control={
                      <Checkbox
                        checked={selectedModelKeys.includes(m.model_key)}
                        onChange={() => toggleModel(m.model_key)}
                      />
                    }
                    label={m.display_name}
                  />
                ))}
              </FormGroup>
              {policyMutation.isError && (
                <Alert severity="error" sx={{ mt: 1 }}>
                  {getErrorMessage(policyMutation.error)}
                </Alert>
              )}
              <Button
                variant="contained"
                sx={{ mt: 2 }}
                disabled={policyMutation.isPending}
                onClick={() => policyMutation.mutate()}
              >
                {t('common.save')}
              </Button>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                {t('admin.policies.quotaPeriod')}
              </Typography>
              <Stack spacing={2}>
                <TextField
                  select
                  label={t('admin.policies.quotaPeriod')}
                  value={quotaPeriod}
                  onChange={(e) => setQuotaPeriod(e.target.value as QuotaPeriod)}
                >
                  <MenuItem value="daily">{t('usage.period_daily')}</MenuItem>
                  <MenuItem value="weekly">{t('usage.period_weekly')}</MenuItem>
                  <MenuItem value="monthly">{t('usage.period_monthly')}</MenuItem>
                </TextField>
                <TextField
                  label={t('admin.policies.quotaLimit')}
                  type="number"
                  value={quotaLimit}
                  onChange={(e) => setQuotaLimit(e.target.value)}
                />
                {quotaMutation.isError && <Alert severity="error">{getErrorMessage(quotaMutation.error)}</Alert>}
                <Button
                  variant="contained"
                  disabled={quotaMutation.isPending}
                  onClick={() => quotaMutation.mutate()}
                >
                  {t('common.save')}
                </Button>

                <Divider sx={{ my: 1 }} />

                <Typography variant="body2" color="text.secondary">
                  {t('admin.policies.bonusCredits')}
                  {userDetailQuery.data.quota
                    ? `: ${userDetailQuery.data.quota.bonus_credits}`
                    : ''}
                </Typography>
                <TextField
                  label={t('admin.policies.bonusCredits')}
                  type="number"
                  value={bonusCredits}
                  onChange={(e) => setBonusCredits(e.target.value)}
                />
                {bonusMutation.isError && <Alert severity="error">{getErrorMessage(bonusMutation.error)}</Alert>}
                <Button
                  variant="outlined"
                  disabled={bonusMutation.isPending}
                  onClick={() => bonusMutation.mutate()}
                >
                  {t('admin.policies.addBonus')}
                </Button>
              </Stack>
            </Paper>
          </Grid>
        </Grid>
      )}
    </Box>
  );
}
